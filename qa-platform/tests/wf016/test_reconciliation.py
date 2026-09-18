"""DATAONE-WF-016 — reconciliation integrity: TC050.

Shared with DATAONE-WF-019; owned here because WF-016 has the lower build
order of the two in-scope workflows (AUTOMATION_CONVENTIONS.md, "Shared
test cases"). WF-019 references this tc_id and must not re-implement it.

Reconciliation is what closes an invoice against a payment. Broken
reconciliation re-opens paid invoices and the company chases customers who
already paid — so the whole reconciliation GRAPH, not just its totals, has
to survive the upgrade unchanged.

Adaptation: ORM, not raw SQL
----------------------------
The workbook writes six raw queries against ``account_partial_reconcile``,
``account_full_reconcile``, ``account_move_line`` and ``account_payment``.
They are implemented here through ``read_group``/``search_read`` instead,
the same adaptation ``tests/wf013`` made for its fourteen reconciliation
cases, for one reason: a PostgreSQL-less workstation would otherwise report
BLOCKED for a missing ``pg_*`` config and this P0 would silently never run.
Every value the workbook asks for is captured; none is weakened.

Two things the capture is deliberately careful about:

* **Step 4 — the exact pairing.** Totals can be preserved by a re-pairing
  that is nonetheless wrong. The capture records the sorted
  ``(debit_move_id, credit_move_id, amount)`` triples, hashed, so a
  re-pairing is caught even when every sum matches. Raw ids are not
  comparable across databases; what is compared is the multiset SHAPE plus
  its checksum.
* **Step 5 — the invariant.** Every fully-reconciled group must net to
  zero. That is asserted as an ANCHOR on both versions, not as a diff: a
  group that does not net to zero is broken regardless of whether the
  upgrade broke it.

Read-only. This case creates nothing, writes nothing and never touches a
business record.

EXPECTED v17 OUTCOME: PASS — captures and persists the baseline.
EXPECTED v19 OUTCOME: PASS when the graph is identical; BLOCKED when no
v17 baseline has been captured yet. The v19 watch items are in §2.3 (the
cash-basis reconciliation block in ``_post`` now runs BEFORE
``state = 'posted'``), the removal of
``_stock_account_anglo_saxon_reconcile_valuation`` from ``stock_account``,
and dto_account_cogs' ``dynamic_unlink=True`` + ``force_delete=True``
context keys in ``button_draft``/``button_cancel`` — Odoo 18 replaced the
onchange-based dynamic-line synchronisation with computed/inverse fields,
so whether those keys are still honoured is Unknown. All SILENT.
"""
import hashlib
import json

from framework.fg_common import reconcile
from framework.registry import test_case
from tests.wf016.common import (MARK, WORKFLOW, WORKFLOW_NAME,  # noqa: F401
                                m2o_id, require_dto_account, trace)


def _digest(rows) -> str:
    """A stable checksum of a list of comparable tuples."""
    payload = json.dumps(rows, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _capture(ctx):
    """Every figure the workbook's six queries ask for, via the ORM."""
    rpc = ctx.adapter.rpc
    snapshot = {}

    # --- step 1: partial reconciliations --------------------------------
    partials = rpc.search_read(
        "account.partial.reconcile", [],
        ["amount", "debit_amount_currency", "credit_amount_currency",
         "debit_move_id", "credit_move_id"])
    snapshot["partials.count"] = len(partials)
    snapshot["partials.amount"] = round(
        sum(p["amount"] or 0.0 for p in partials), 2)
    snapshot["partials.debit_cur"] = round(
        sum(p["debit_amount_currency"] or 0.0 for p in partials), 2)
    snapshot["partials.credit_cur"] = round(
        sum(p["credit_amount_currency"] or 0.0 for p in partials), 2)

    # --- step 2: full reconciliations -----------------------------------
    snapshot["full_reconciles.count"] = len(
        rpc.search("account.full.reconcile", []))
    snapshot["lines_fully_reconciled"] = len(
        rpc.search("account.move.line",
                   [("full_reconcile_id", "!=", False)]))

    # --- step 3: the reconciled flag distribution -----------------------
    reconcilable = rpc.search("account.account", [("reconcile", "=", True)])
    grouped = rpc.read_group(
        "account.move.line",
        [("move_id.state", "=", "posted"),
         ("account_id", "in", reconcilable)],
        ["balance:sum", "__count"], ["account_id", "reconciled"],
        lazy=False)
    types = {}
    account_ids = sorted({m2o_id(g["account_id"]) for g in grouped
                          if g.get("account_id")})
    if account_ids:
        types = {a["id"]: a["account_type"] for a in
                 rpc.read("account.account", account_ids, ["account_type"])}
    by_type = {}
    for group in grouped:
        key = (types.get(m2o_id(group.get("account_id")), "unknown"),
               bool(group.get("reconciled")))
        entry = by_type.setdefault(key, {"count": 0, "balance": 0.0})
        entry["count"] += group.get("__count", 0)
        entry["balance"] += group.get("balance", 0.0) or 0.0
    snapshot["reconciled_flag_distribution"] = sorted(
        (account_type, flag, entry["count"], round(entry["balance"], 2))
        for (account_type, flag), entry in by_type.items())

    # --- step 4: the exact pairing --------------------------------------
    pairing = sorted(
        (m2o_id(p["debit_move_id"]), m2o_id(p["credit_move_id"]),
         round(p["amount"] or 0.0, 2))
        for p in partials)
    snapshot["pairing.digest"] = _digest(pairing)
    snapshot["pairing.count"] = len(pairing)
    snapshot["pairing.amount_multiset"] = _digest(
        sorted(round(p["amount"] or 0.0, 2) for p in partials))

    # --- step 5: every full group nets to zero --------------------------
    groups = rpc.read_group(
        "account.move.line", [("full_reconcile_id", "!=", False)],
        ["balance:sum"], ["full_reconcile_id"], lazy=False)
    nonzero = sorted(
        (m2o_id(g["full_reconcile_id"]), round(g.get("balance", 0.0) or 0.0, 2))
        for g in groups
        if round(g.get("balance", 0.0) or 0.0, 2) != 0.0)
    snapshot["full_groups_not_netting_to_zero"] = len(nonzero)
    snapshot["full_groups_not_netting_detail"] = nonzero[:20]

    # --- step 6: payments ------------------------------------------------
    payments = rpc.search_read(
        "account.payment", [],
        ["amount", "payment_type", "partner_type", "state"])
    by_key = {}
    for payment in payments:
        key = (payment.get("state") or "", payment.get("payment_type") or "",
               payment.get("partner_type") or "")
        entry = by_key.setdefault(key, {"count": 0, "amount": 0.0})
        entry["count"] += 1
        entry["amount"] += payment.get("amount") or 0.0
    snapshot["payments"] = sorted(
        (state, ptype, partner, entry["count"], round(entry["amount"], 2))
        for (state, ptype, partner), entry in by_key.items())

    return snapshot


@test_case(
    id="TEST-WF016-TC050",
    name="Reconciliation integrity",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account, dto_account_cogs, dto_account_workday",
    priority="P0", kind="DATA", order=16050,
    description="Captures the whole reconciliation graph — partial and "
                "full reconciliations, the reconciled-flag distribution, "
                "the exact pairing as a checksum, the net-to-zero "
                "invariant and the payment population — and asserts zero "
                "difference against the v17 baseline. Read-only.",
    traceability=trace("DATAONE-TC050", user_story="shared with "
                                                   "DATAONE-WF-019"))
def test_tc050(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Preconditions: accounting installed. This case creates "
                  "nothing, writes nothing and touches no business record"):
        require_dto_account(ctx)
        for model in ("account.partial.reconcile", "account.full.reconcile",
                      "account.payment"):
            if not rpc.model_exists(model):
                ctx.blocked(
                    f"{model} does not exist on {ctx.env.key} — the "
                    "accounting module is not installed, so there is no "
                    "reconciliation graph to compare.")

    with ctx.step("Shared-case note"):
        ctx.log("DATAONE-TC050 is shared between DATAONE-WF-016 and "
                "DATAONE-WF-019. It is implemented once, here, in the "
                "suite of the owning workflow (the lower build order that "
                "is in scope). WF-019 references the same tc_id and must "
                "not re-implement it.")

    reconcile(
        ctx, "DATAONE-TC050", _capture,
        anchors={
            # Step 5's invariant: asserted on BOTH versions, not diffed. A
            # full reconciliation group that does not net to zero is broken
            # whether or not the upgrade broke it.
            "full_groups_not_netting_to_zero": 0,
        })
