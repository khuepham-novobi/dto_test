"""DATAONE-WF-018 — data integrity across the upgrade: TC035.

Shared with DATAONE-WF-017; owned here, because WF-018 has the lower build
order (21 against 24). WF-017 references this tc_id and must not
re-implement it (AUTOMATION_CONVENTIONS.md, "Shared test cases").

What is actually at stake
-------------------------
``export_workday`` is the only thing standing between the cutover and a
duplicate submission to Workday's ledger. Two facts have to survive the
upgrade byte for byte:

* the set of ids ALREADY exported — anything that loses its flag is sent
  to Workday a second time;
* the set of ids WAITING to be exported — anything that gains a flag is
  never sent at all, and the ledger of record is short an entry with
  nothing in Odoo to say so.

**Aggregates are not sufficient and this case is written to say so.** Two
moves swapping flags leaves every count in step 1 unchanged while sending
one duplicate and dropping another. Only the id-set comparison catches
that, so the capture records checksummed SORTED ID LISTS, not counts.

Adaptation: ORM with SQL preferred, not SQL only
------------------------------------------------
The workbook writes seven raw queries. They are implemented through
``search``/``read_group`` here, the same adaptation ``tests/wf013`` and
``tests/wf016`` made, for one reason: a PostgreSQL-less workstation would
otherwise report BLOCKED for a missing ``pg_*`` config and this P0 would
silently never run. Every value the workbook asks for is captured; none is
weakened. Step 3's ``information_schema`` sweep is replaced by
``ir.model.fields``, which is the same inventory expressed in terms the
ORM has.

Step 5 has no v19 counterpart by construction
---------------------------------------------
The workbook's fifth query counts ``stock_valuation_layer`` links per
move, to preserve what v17 computed because v19 cannot recompute it. **The
model was DELETED in v19** — not renamed. ``dto_account_workday``'s own
``assign_workday_entry_type`` already re-derives that branch as "no stock
move + the company's stock journal" and records the measurement that
justifies it (``models/account_move.py:311-326``: 633 of 184,882 typed
entries took the v17 branch, every one ``inventory_adj`` and in the STJ
journal). The capture therefore records BOTH shapes — the SVL link counts
where the model still exists, and the re-derived population everywhere —
so the v17 answer is preserved as source material AND the re-derivation
is diffed. Where the model is absent the SVL key is recorded as the
literal string ``"model-absent"`` rather than omitted, so its
disappearance shows up as a difference rather than as silence.

Read-only. This case creates nothing, writes nothing, and never touches a
business record.

EXPECTED v17 OUTCOME: PASS — captures and persists the baseline.
EXPECTED v19 OUTCOME: PASS when the flag and the queue are identical;
BLOCKED when no v17 baseline has been captured yet. A pre-existing v17
defect this case PRESERVES rather than fixes: on a transport failure
``export_workday`` is left True while the file is Failed, so a Re-post is
the only recovery — and conversely the inbound payment flow sets the same
flag (see TEST-WF018-TC326 steps 11-12). Both are properties of the
baseline, not upgrade damage, and the diff must not be weakened to hide
them.
"""
import hashlib
import json

from framework.fg_common import reconcile
from framework.registry import test_case
from tests.wf018.common import (EXPORT_CRON_XMLID,  # noqa: F401
                                JOURNAL_CRON_XMLID, POST_CRON_XMLID,
                                VENDOR_BILL_EXPORT_DOMAIN, WORKFLOW,
                                WORKFLOW_NAME, cron_row, m2o_id,
                                require_workday_export, trace)

# account_move.py:77-83 — the journal-entry export domain, mirrored for the
# same reason as the vendor-bill one: the method is private and cannot be
# dispatched over RPC.
JOURNAL_ENTRY_EXPORT_DOMAIN = [
    ("move_type", "!=", "in_invoice"),
    ("state", "=", "posted"),
    ("export_workday", "=", False),
    ("journal_id.type", "not in", ["bank"]),
]


def _digest(values) -> str:
    """A stable checksum of a list of comparable values."""
    payload = json.dumps(values, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _capture(ctx):
    """Every figure the workbook's seven queries ask for, via the ORM."""
    rpc = ctx.adapter.rpc
    snapshot = {}

    # --- step 1: the aggregate the case is named for ---------------------
    grouped = rpc.read_group(
        "account.move", [],
        ["amount_total_signed:sum", "__count"],
        ["move_type", "export_workday", "state"], lazy=False)
    snapshot["move_aggregate"] = sorted(
        (group.get("move_type") or "",
         bool(group.get("export_workday")),
         group.get("state") or "",
         group.get("__count", 0),
         round(group.get("amount_total_signed") or 0.0, 2))
        for group in grouped)

    # --- step 2: the EXACT exported id set -------------------------------
    # This is what protects against duplicate submission. Counts cannot:
    # two moves swapping flags leaves every count above unchanged.
    exported = sorted(rpc.search("account.move",
                                 [("export_workday", "=", True)]))
    snapshot["exported.count"] = len(exported)
    snapshot["exported.id_digest"] = _digest(exported)
    snapshot["exported.first_20"] = exported[:20]
    snapshot["exported.last_20"] = exported[-20:]

    # --- step 3: the audit fields alongside the flag ---------------------
    workday_fields = rpc.search_read(
        "ir.model.fields",
        [("model", "=", "account.move"), ("name", "like", "%workday%")],
        ["name", "ttype", "store"])
    snapshot["account_move.workday_fields"] = sorted(
        (row["name"], row["ttype"]) for row in workday_fields)
    line_fields = rpc.search_read(
        "ir.model.fields",
        [("model", "=", "account.move.line"),
         ("name", "like", "export_workday%")], ["name", "ttype"])
    snapshot["account_move_line.export_workday_fields"] = sorted(
        (row["name"], row["ttype"]) for row in line_fields)

    exported_rows = rpc.search_read(
        "account.move", [("export_workday", "=", True)],
        ["export_workday_sync", "journal_id", "move_type", "state", "date"],
        order="id")
    snapshot["exported.shape_digest"] = _digest([
        (row["id"], bool(row.get("export_workday_sync")),
         m2o_id(row.get("journal_id")), row.get("move_type"),
         row.get("state"), str(row.get("date")))
        for row in exported_rows])
    snapshot["exported.without_a_sync_timestamp"] = len(
        [row for row in exported_rows if not row.get("export_workday_sync")])

    # --- step 4: the QUEUE — what is WAITING to be exported ---------------
    pending_entries = sorted(rpc.search("account.move",
                                        JOURNAL_ENTRY_EXPORT_DOMAIN))
    snapshot["pending_journal_entries.count"] = len(pending_entries)
    snapshot["pending_journal_entries.id_digest"] = _digest(pending_entries)
    snapshot["pending_journal_entries.first_20"] = pending_entries[:20]

    pending_bills = sorted(rpc.search("account.move",
                                      VENDOR_BILL_EXPORT_DOMAIN))
    snapshot["pending_vendor_bills.count"] = len(pending_bills)
    snapshot["pending_vendor_bills.id_digest"] = _digest(pending_bills)
    snapshot["pending_vendor_bills.first_20"] = pending_bills[:20]
    # The two domains must not overlap, on either version: a move in both
    # would be exported twice, once per flow, under two different column
    # contracts.
    snapshot["queues_overlap"] = len(
        set(pending_entries) & set(pending_bills))

    # --- step 5: the entry-type derivation the SVL deletion breaks -------
    if rpc.model_exists("stock.valuation.layer"):
        svl_grouped = rpc.read_group(
            "stock.valuation.layer", [("account_move_id", "!=", False)],
            ["__count"], ["account_move_id"], lazy=False)
        snapshot["svl_linked_moves.count"] = len(svl_grouped)
        snapshot["svl_linked_moves.id_digest"] = _digest(sorted(
            m2o_id(group["account_move_id"]) for group in svl_grouped
            if group.get("account_move_id")))
    else:
        # v19 DELETED the model outright. Recorded as a literal so its
        # absence appears as a DIFFERENCE, never as a missing key.
        snapshot["svl_linked_moves.count"] = "model-absent"
        snapshot["svl_linked_moves.id_digest"] = "model-absent"

    # The re-derivation that replaces it, captured on BOTH versions so the
    # populations can be compared rather than merely noted.
    entry_grouped = rpc.read_group(
        "account.move", [("entry_type", "!=", False)],
        ["__count"], ["entry_type"], lazy=False)
    snapshot["entry_type_population"] = sorted(
        (group.get("entry_type") or "", group.get("__count", 0))
        for group in entry_grouped)
    snapshot["typed_moves_without_a_journal_source"] = len(rpc.search(
        "account.move", [("entry_type", "!=", False),
                         ("journal_workday_id", "=", False)]))
    snapshot["posted_moves_with_no_entry_type_in_the_stock_journal"] = len(
        rpc.search("account.move",
                   [("state", "=", "posted"), ("entry_type", "=", False),
                    ("journal_id.type", "=", "general"),
                    ("stock_move_ids", "=", False)])
        if rpc.field_exists("account.move", "stock_move_ids") else [])

    # --- step 6: the journal-source catalogue the export writes into T ---
    if rpc.model_exists("account.journal.workday"):
        snapshot["journal_workday.count"] = len(
            rpc.search("account.journal.workday", []))
        snapshot["journal_workday_line.count"] = len(
            rpc.search("account.journal.workday.line", []))
        sources = rpc.search_read("account.journal.workday", [],
                                  ["name"], order="id")
        snapshot["journal_workday.name_digest"] = _digest(
            sorted((row.get("name") or "") for row in sources))
    else:
        snapshot["journal_workday.count"] = "model-absent"
        snapshot["journal_workday_line.count"] = "model-absent"
        snapshot["journal_workday.name_digest"] = "model-absent"

    # --- the crons that would move any of this ---------------------------
    for xmlid in (EXPORT_CRON_XMLID, JOURNAL_CRON_XMLID, POST_CRON_XMLID):
        row = cron_row(rpc, xmlid)
        snapshot[f"cron.{xmlid}.exists"] = bool(row)
        snapshot[f"cron.{xmlid}.active"] = bool(row and row.get("active"))

    return snapshot


@test_case(
    id="TEST-WF018-TC035",
    name="Workday export state (export_workday × move_type): nothing "
         "re-exported, nothing dropped",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account_workday", priority="P0", kind="DATA", order=18035,
    description="Captures the exported id set and both export queues as "
                "checksummed sorted id lists — not counts, because two "
                "moves swapping flags leaves every count unchanged while "
                "sending one duplicate and dropping another — plus the "
                "workday field inventory, the entry-type population and the "
                "journal-source catalogue, and asserts zero difference "
                "against the v17 baseline. Read-only.",
    traceability=trace("DATAONE-TC035", user_story="shared with "
                                                   "DATAONE-WF-017"))
def test_tc035(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Preconditions: dto_account_workday is installed. This "
                  "case creates nothing, writes nothing and touches no "
                  "business record"):
        require_workday_export(ctx)
        if not rpc.field_exists("account.move", "export_workday"):
            ctx.blocked(
                "account.move.export_workday does not exist on "
                f"{ctx.env.key} — the flag this whole case is about is "
                "absent, so there is no export state to compare.")

    with ctx.step("Shared-case note"):
        ctx.log("DATAONE-TC035 is shared between DATAONE-WF-018 and "
                "DATAONE-WF-017. It is implemented once, here, in the "
                "suite of the owning workflow (the lower build order). "
                "WF-017 references the same tc_id and must not "
                "re-implement it.")

    with ctx.step("Capture precondition: the export crons must be DISABLED "
                  "on both databases for the duration of the capture — a "
                  "cron firing between captures invalidates the whole case"):
        active = [xmlid for xmlid in (EXPORT_CRON_XMLID, JOURNAL_CRON_XMLID,
                                      POST_CRON_XMLID)
                  if (cron_row(rpc, xmlid) or {}).get("active")]
        ctx.log(f"Workday crons currently ACTIVE on {ctx.env.key}: "
                f"{active or 'none'}")
        ctx.check("no Workday export or POST cron is active while the "
                  "baseline is captured", [], active)

    reconcile(
        ctx, "DATAONE-TC035", _capture,
        anchors={
            # An invariant on BOTH versions, not a diff: a move cannot sit
            # in both export queues. One that did would be sent to Workday
            # twice under two different column contracts.
            "queues_overlap": 0,
        })
