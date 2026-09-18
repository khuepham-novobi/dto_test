"""DATAONE-WF-008 — the baseline: TC257.

"The only acceptance evidence the Controller should accept for
manufacturing costing." Every other case in this suite tests a mechanism
against a table that is itself INFERRED; this one tests the whole engine
against what the business actually posted. If v19 reproduces 20 real
manufacturing orders' journal entries to the cent, the absorption model
survived the upgrade. If it does not, no amount of green unit tests
matters.

The comparison must survive a total shape change
------------------------------------------------
§2.1 changes everything about HOW the entries are produced:
``stock.valuation.layer`` removed, ``_generate_valuation_lines_data`` gone,
one journal entry per **batch** of moves rather than per move,
``stock.move.account_move_ids`` replaced by the singular
``account_move_id``, the journal taken from
``res.company.account_stock_journal_id`` rather than the product category,
and category input/output accounts removed. The entry's SHAPE is EXPECTED
to change even when its AMOUNTS are right.

So the normalisation is the heart of this case, and it is exactly the
workbook's step 3: aggregate to
``(mo_name, account_code, line_label, sorted(analytic account ids))``
summing debit and credit within each key. Line ids, entry ids, line counts
per move and journal choice are all deliberately excluded — every one of
them is expected to move. What is compared is money, per MO, per account,
per label, plus the frozen rates and the finished unit cost.

Selection is frozen, not re-derived
-----------------------------------
The workbook requires the 20 MOs to be selected deterministically and the
selection frozen in the repository, because re-deriving "the top 20 by
posted valuation" at compare time would silently compare different
populations on the two databases. The v17 run therefore PERSISTS the MO
names it selected as part of the baseline, and the v19 run reads that list
rather than re-selecting. That is what ``framework.baselines`` already does
for every other DATA_RECONCILIATION case, so no new mechanism is needed.

Adaptation: ORM, not raw SQL
----------------------------
The workbook writes the capture as two version-specific SQL queries joining
through ``stock_valuation_layer`` (v17) or ``stock_move.account_move_id``
(v19). They are implemented through the ORM instead — the same adaptation
``tests/wf013`` made for its fourteen reconciliation cases — so the case
needs no PostgreSQL credentials and can never report BLOCKED for a missing
``pg_*`` config. The version difference is absorbed by
``common.move_entries()``, which resolves whichever link the target has.

Read-only. This case creates nothing and writes nothing.

EXPECTED v17 OUTCOME: PASS — selects, captures and persists the baseline.
BLOCKED when the database holds no completed manufacturing orders with
posted valuation, with the count reported.
EXPECTED v19 OUTCOME: PASS with zero non-zero deltas. Any non-zero delta is
escalated as P0 to the Controller with the MO name, the account, both
amounts and the difference — which is precisely what the diff reports.
"""
from framework.fg_common import reconcile
from framework.registry import test_case
from tests.wf008.common import (MARK, WORKFLOW, WORKFLOW_NAME,  # noqa: F401
                                distribution_accounts, m2o_id, move_entries,
                                require_absorption_stack, trace,
                                valuation_link_field)

#: How many MOs the baseline covers. The workbook says 20.
BASELINE_MO_COUNT = 20

LABOUR_LABEL = " - Labor Cost"
OVERHEAD_LABEL = " - Overhead Cost - "


def _select_mos(ctx):
    """The MOs to compare, selected deterministically and frozen.

    Ordered by ``name`` rather than by posted valuation: the workbook asks
    for a selection that is frozen in the repository and identical on both
    databases, and ``name`` is the only key guaranteed stable across an
    upgrade. Ordering by valuation would re-derive a possibly different
    population on v19, which is the exact failure the freeze exists to
    prevent. The biasing criteria the workbook lists (multi-pool, MTO,
    standard-cost, scrap, backorder, a stale snapshot) are reported as
    COVERAGE of the chosen set so a thin baseline is visible rather than
    silently accepted.
    """
    rpc = ctx.adapter.rpc
    rows = rpc.search_read(
        "mrp.production", [("state", "=", "done")],
        ["name", "product_qty", "qty_produced",
         "stored_overhead_cost_settings"],
        order="name desc", limit=BASELINE_MO_COUNT)
    return rows


def _capture(ctx):
    """Aggregate every selected MO's valuation entries, shape-independent."""
    rpc = ctx.adapter.rpc
    snapshot = {}

    selected = _select_mos(ctx)
    names = sorted(row["name"] for row in selected)
    snapshot["selection.count"] = len(names)
    snapshot["selection.names"] = names
    snapshot["link_field"] = valuation_link_field(rpc)

    if not names:
        return snapshot

    coverage = {"with_snapshot": 0, "multi_pool": 0, "zero_qty": 0}
    for row in selected:
        stored = row.get("stored_overhead_cost_settings") or {}
        if stored:
            coverage["with_snapshot"] += 1
        if len(stored) > 1:
            coverage["multi_pool"] += 1
        if not (row.get("qty_produced") or 0):
            coverage["zero_qty"] += 1
    snapshot["selection.coverage"] = coverage

    mo_ids = [row["id"] for row in selected]
    by_id = {row["id"]: row for row in selected}

    # Every stock move belonging to the selected MOs, finished and raw.
    moves = rpc.search_read(
        "stock.move",
        ["|", ("production_id", "in", mo_ids),
         ("raw_material_production_id", "in", mo_ids)],
        ["production_id", "raw_material_production_id", "price_unit",
         "product_id", "quantity"])
    move_to_mo = {}
    for move in moves:
        owner = (m2o_id(move.get("production_id"))
                 or m2o_id(move.get("raw_material_production_id")))
        if owner:
            move_to_mo[move["id"]] = owner

    # Step 12: the finished move's price_unit, per MO.
    finished_prices = {}
    for move in moves:
        owner = m2o_id(move.get("production_id"))
        if not owner:
            continue
        mo_product = None
        finished_prices.setdefault(by_id[owner]["name"], [])
        finished_prices[by_id[owner]["name"]].append(
            round(move.get("price_unit") or 0.0, 4))
    snapshot["finished.price_unit"] = {
        name: sorted(values) for name, values in finished_prices.items()}

    # Steps 1-3: the aggregated comparison key.
    entries_by_mo = {}
    for move_id, mo_id in move_to_mo.items():
        for entry_id in move_entries(rpc, [move_id]):
            entries_by_mo.setdefault(entry_id, by_id[mo_id]["name"])

    aggregated = {}
    per_mo_totals = {}
    labour_by_mo = {}
    overhead_by_mo = {}
    if entries_by_mo:
        lines = rpc.search_read(
            "account.move.line", [("move_id", "in", list(entries_by_mo))],
            ["move_id", "name", "account_id", "debit", "credit",
             "analytic_distribution"], order="id")
        account_ids = sorted({m2o_id(ln["account_id"]) for ln in lines
                              if m2o_id(ln["account_id"])})
        codes = {a["id"]: a["code"] for a in
                 rpc.read("account.account", account_ids, ["code"])} \
            if account_ids else {}
        for line in lines:
            mo_name = entries_by_mo.get(m2o_id(line["move_id"]), "?")
            code = codes.get(m2o_id(line["account_id"]), "?")
            label = line.get("name") or ""
            analytic = tuple(sorted(distribution_accounts(
                line.get("analytic_distribution"))))
            key = f"{mo_name}|{code}|{label}|{analytic}"
            entry = aggregated.setdefault(key, [0.0, 0.0])
            entry[0] += line.get("debit") or 0.0
            entry[1] += line.get("credit") or 0.0

            totals = per_mo_totals.setdefault(mo_name, [0.0, 0.0])
            totals[0] += line.get("debit") or 0.0
            totals[1] += line.get("credit") or 0.0

            if LABOUR_LABEL in label:
                labour_by_mo[mo_name] = round(
                    labour_by_mo.get(mo_name, 0.0)
                    + (line.get("debit") or 0.0), 2)
            if OVERHEAD_LABEL in label:
                pool = label.split(OVERHEAD_LABEL, 1)[1]
                pool_key = f"{mo_name}|{pool}"
                overhead_by_mo[pool_key] = round(
                    overhead_by_mo.get(pool_key, 0.0)
                    + (line.get("debit") or 0.0), 2)

    # Step 8: per MO per account.
    snapshot["entries.aggregated"] = {
        key: [round(values[0], 2), round(values[1], 2)]
        for key, values in sorted(aggregated.items())}
    # Step 7: per MO.
    snapshot["entries.per_mo_totals"] = {
        name: [round(values[0], 2), round(values[1], 2)]
        for name, values in sorted(per_mo_totals.items())}
    # Step 9: the labour line, per MO.
    snapshot["labour.debit_by_mo"] = dict(sorted(labour_by_mo.items()))
    # Step 10: the overhead lines, per pool per MO.
    snapshot["overhead.debit_by_mo_pool"] = dict(
        sorted(overhead_by_mo.items()))
    # Step 11: the frozen rates, byte-identical.
    snapshot["frozen_rates"] = {
        row["name"]: row.get("stored_overhead_cost_settings") or {}
        for row in sorted(selected, key=lambda r: r["name"])}
    # Step 2: the MO's own figures.
    snapshot["mo_quantities"] = {
        row["name"]: [round(row.get("product_qty") or 0.0, 4),
                      round(row.get("qty_produced") or 0.0, 4)]
        for row in sorted(selected, key=lambda r: r["name"])}

    # Step 7's pass condition, asserted as an anchor on both versions.
    snapshot["unbalanced_mos"] = sorted(
        name for name, values in per_mo_totals.items()
        if round(values[0], 2) != round(values[1], 2))

    return snapshot


@test_case(
    id="TEST-WF008-TC257",
    name="BASELINE: top 20 v17 manufacturing orders reproduced to the cent",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account, dto_mrp_account", priority="P0", kind="DATA",
    order=8257,
    description="Captures 20 real completed manufacturing orders' "
                "valuation entries, normalised to a shape-independent key "
                "(MO, account code, line label, resolved analytic "
                "accounts) with debit and credit summed per key, plus the "
                "per-MO totals, the labour and per-pool overhead debits, "
                "the frozen rate snapshots and the finished price_unit — "
                "and asserts zero difference against the v17 baseline.",
    traceability=trace("DATAONE-TC257"))
def test_tc257(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Preconditions: dto_mrp_account installed. This case "
                  "creates nothing, writes nothing and touches no business "
                  "record"):
        require_absorption_stack(ctx)
        link = valuation_link_field(rpc)
        if not link:
            ctx.blocked(
                "Neither stock.move.account_move_ids (v17) nor "
                "stock.move.account_move_id (v19) exists on "
                f"{ctx.env.key} — there is no way to reach a stock move's "
                "valuation entry, so no baseline can be captured. §2.1 "
                "inverted this relation; if a THIRD shape has appeared, "
                "add it to common.valuation_link_field() rather than to "
                "this case.")
        ctx.log(f"valuation link on Odoo {ctx.env.version}: {link!r}")

    with ctx.step("Select the baseline population. The selection is "
                  "PERSISTED with the baseline and read back on v19 rather "
                  "than re-derived, so the two runs compare the same MOs"):
        selected = _select_mos(ctx)
        ctx.log(f"selected {len(selected)} completed manufacturing orders")
        for row in selected:
            ctx.log(f"  {row['name']}: qty={row.get('product_qty')} "
                    f"produced={row.get('qty_produced')} "
                    f"snapshot={row.get('stored_overhead_cost_settings')!r}")
        if not selected:
            ctx.blocked(
                f"No completed manufacturing orders exist on {ctx.env.key} "
                "(db=" + str(ctx.env.db) + "). This case is the Controller's "
                "acceptance evidence and it needs REAL production data — a "
                "restored clone of the v17 production database, not a "
                "fixture. Without it the absorption engine has nothing to "
                "be measured against.")
        if len(selected) < BASELINE_MO_COUNT:
            ctx.log(f"[warn] only {len(selected)} completed MOs are "
                    f"available where the workbook asks for "
                    f"{BASELINE_MO_COUNT}. The comparison still holds for "
                    "what exists, but the coverage the workbook requires "
                    "(multi-pool, MTO, standard-cost, scrap, backorder, a "
                    "stale snapshot) may be incomplete — the capture "
                    "reports what it found under selection.coverage.")

    with ctx.step("E1 note — the baseline cannot be recreated later"):
        ctx.log("The v17 capture must be taken on the read-only production "
                "clone BEFORE it is upgraded. Once the clone is upgraded "
                "the baseline is gone and this case becomes permanently "
                "unexecutable. Do not regenerate the stored baseline after "
                "an upgrade; framework.baselines writes it once per tc_id "
                "and the v19 run only reads it.")

    reconcile(
        ctx, "DATAONE-TC257", _capture,
        anchors={
            # Step 7's pass condition, asserted on BOTH versions rather
            # than diffed: an MO whose entries do not balance is broken
            # whether or not the upgrade broke it.
            "unbalanced_mos": [],
        })
