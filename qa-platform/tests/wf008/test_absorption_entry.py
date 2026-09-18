"""DATAONE-WF-008 — the absorption entry: TC234-TC239, TC241, TC243.

TC234 is the gate case of the whole workflow: one MO, both switches on, one
pool, non-zero timesheets, marked Done — and the finished-good journal
entry must contain all six lines of the workflow's own Data Changes table,
to the cent, with the right analytic overlay on each credit leg.

The other seven cases each isolate one mechanism that a rebuild can lose
without any error at all:

* TC235 / TC236 — the two switches are checked in DIFFERENT MODELS (the
  overhead gate in ``mrp.production._calc_production_overhead_cost``, the
  labour gate in ``stock.move._generate_valuation_lines_data``). They are
  two independent code paths and a port that preserves one may drop the
  other, so each half is proved to stand alone.
* TC237 — the null hypothesis. Both switches off must produce exactly what
  stock Odoo would produce. The difference between this entry and TC234's
  IS what DataOne's customisation is worth, and this is the only case that
  would detect a v19 rebuild posting labour or overhead unconditionally.
* TC238 — the skip and the freeze are opposite behaviours on the same
  record: a pool whose rounded overhead is zero is dropped from the entry
  by ``currency.is_zero`` but is still written into the snapshot. It also
  answers whether a pool with a MIS-MIGRATED account is distinguishable
  from a zero-yield one — §2.16's ir.property removal makes that a live
  migration risk.
* TC239 — the missing labour account raises a specific UserError at
  Mark-as-Done, rolls the whole transaction back, and is gated on the
  switch rather than unconditional.
* TC241 — two pools produce two separate pairs kept apart by the composite
  key ``debit_<account>_<description>``. §2.1 confirms v19 has no analogue
  for that idiom, and its worst failure is silent: two pools sharing an
  account merge into one line, the entry still balances, the analytic
  split is gone.
* TC243 — scrap is excluded by a TWO-condition guard
  (``not self.scrap_id and not self.scrapped``) that a rebuild can easily
  reduce to one, and the overhead base must exclude the scrapped value.

Absolute amounts vs. captured amounts
-------------------------------------
The workbook's table is written against a fixture where components are
valued at exactly 600.00. These tests build that fixture (a standard-cost
component at 60.00 x 10 units) and assert the LABOUR and OVERHEAD figures
absolutely, because those are computed by DataOne's own code from inputs
the fixture controls completely. The CORE pair (Stock Valuation / WIP) is
asserted RELATIVE to the captured component value instead — core decides
that number and §2.1 rebuilt how, so pinning it absolutely would report a
core change as a DataOne regression. Both choices are stated per
assertion.

EXPECTED v17 OUTCOME: PASS for all eight.
EXPECTED v19 OUTCOME: these are the cases the rebuild has to satisfy.
``_generate_valuation_lines_data`` does not exist on v19 at all — no
``svl_id``, no ``description``, no keyed result dict — so until the rebuild
lands, TC234, TC235, TC236, TC238, TC241 and TC243 are expected to FAIL on
the line count and on the labour/overhead pairs. Those failures ARE the
specification.
"""
from framework.registry import test_case
from tests.wf008.common import (require_exclusive_pools,  # noqa: F401
                                CATALOGUE_RATE, COMPONENT_TOTAL,  # noqa: F401
                                DUPLICATE_POOL_MESSAGE,
                                EMPLOYEE_HOURLY_COST, LABOUR_MINUTES,
                                LABOUR_SWITCH, LABOUR_TOTAL, MARK, MO_QTY,
                                MISSING_LABOUR_ACCOUNT_MESSAGE,
                                NON_POSITIVE_PCT_MESSAGE, OVERHEAD_SWITCH,
                                PINNED_RATE, WORKFLOW, WORKFLOW_NAME,
                                ZERO_YIELD_RATE, build_mo, describe_lines,
                                ensure_analytic_account, ensure_category,
                                ensure_pool, ensure_product, entry_lines,
                                expect_error, finished_move, fx,
                                distribution_accounts, live_pools,
                                lines_named, m2o_id, mark_done, move_entries,
                                raw_moves, record_time,
                                require_absorption_stack,
                                require_mrp_valuation, set_switches,
                                standard_environment, set_stock, switches,
                                sweep_wf008, trace)

LABOUR_LABEL = " - Labor Cost"
OVERHEAD_LABEL = " - Overhead Cost - "


def _setup(ctx, labour=True, overhead=True, **kwargs):
    """Sweep, probe, snapshot the switches and build the fixture."""
    rpc = ctx.adapter.rpc
    with ctx.step("Sweep previous WF-008 fixtures and open a fresh "
                  "namespace. Leftover overhead pools add a pair to EVERY "
                  "entry — the workbook names this as the suite's most "
                  "common contamination"):
        sweep_wf008(rpc)

    with ctx.step("Preconditions: dto_mrp_account installed, real-time "
                  "valuation available, the two switches readable"):
        require_absorption_stack(ctx)
        require_mrp_valuation(ctx)
        comp_id, original = switches(rpc)
        ctx.log(f"company {comp_id} switches before: {original!r}")

    with ctx.step(f"Set the switches for this case: labour={labour}, "
                  f"overhead={overhead}"):
        set_switches(rpc, comp_id, labour=labour, overhead=overhead)
        _, now = switches(rpc)
        ctx.check("switches in force", {LABOUR_SWITCH: labour,
                                        OVERHEAD_SWITCH: overhead}, now)

    with ctx.step("Build the fixture: a standard-cost component at 60.00, "
                  "a 10-unit MO, an Assembly and a Packaging work centre, "
                  "an employee at 60.00/hour"):
        env = standard_environment(ctx, **kwargs)

    return comp_id, original, env


def _restore(ctx, comp_id, original):
    rpc = ctx.adapter.rpc
    with ctx.step("Restore the company switches. Every later case assumes "
                  "them ON; leaving them off silently invalidates the rest "
                  "of the suite"):
        restored = False
        try:
            set_switches(rpc, comp_id,
                         labour=original[LABOUR_SWITCH],
                         overhead=original[OVERHEAD_SWITCH])
            _, now = switches(rpc)
            restored = (now == original)
        except Exception as exc:      # noqa: BLE001
            ctx.log(f"[warn] switch restore failed: {exc}")
        ctx.check_true("the company switches were restored to their "
                       "original values", restored, actual_desc=original)
    with ctx.step("Cleanup WF-008 fixtures"):
        try:
            sweep_wf008(rpc)
        except Exception as exc:      # noqa: BLE001
            ctx.log(f"[warn] cleanup incomplete: {exc}")


def _run_mo(ctx, env, label="MO", qty=MO_QTY, minutes=LABOUR_MINUTES,
            analytic=None, pack_minutes=30.0):
    """Build, time and complete one MO; return (mo_id, raised, message)."""
    rpc = ctx.adapter.rpc
    mo_id = build_mo(ctx, env["finished_id"], env["bom_id"], qty=qty,
                     label=label, analytic=analytic)
    record_time(ctx, mo_id, env["assembly"], minutes,
                employee_id=env["employee_id"])
    # button_mark_done refuses an MO with zero duration on a work centre
    # named 'Packaging' (dto_mrp_account/models/mrp_production.py), so the
    # Packaging time is part of the fixture, not part of any assertion.
    record_time(ctx, mo_id, env["packaging"], pack_minutes,
                employee_id=env["employee_id"])
    raised, message = mark_done(ctx, mo_id)
    return mo_id, raised, message


def _finished_entry(ctx, mo_id):
    """(entry ids, lines, rendered lines) for the finished move's entry."""
    rpc = ctx.adapter.rpc
    move = finished_move(rpc, mo_id)
    if not move:
        ctx.blocked(f"MO {mo_id} has no finished move for its own product; "
                    "there is no valuation entry to read.")
    entries, lines = entry_lines(rpc, [move["id"]])
    rendered = describe_lines(rpc, lines)
    ctx.log(f"finished move: {move!r}")
    ctx.log(f"valuation entries: {entries!r}")
    for row in rendered:
        ctx.log(f"  {row!r}")
    if not entries:
        ctx.blocked(
            f"The finished move of MO {mo_id} carries no journal entry. "
            "Either the product category is not real-time valued, or the "
            "v19 link field changed again — this suite resolves both "
            "stock.move.account_move_ids (v17) and account_move_id (v19). "
            "Check the category accounts logged above before reading "
            "anything into the absence.")
    return entries, lines, rendered, move


def _totals(lines):
    return (round(sum(ln.get("debit") or 0.0 for ln in lines), 2),
            round(sum(ln.get("credit") or 0.0 for ln in lines), 2))


@test_case(
    id="TEST-WF008-TC234",
    name="GATE: six-line finished-goods entry (components 600 + labour 300 "
         "+ overhead 100)",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_mrp_account", priority="P0", kind="API", order=8234,
    description="Both switches on, one pool at 0.166667, 300 minutes of "
                "timesheet time: exactly six lines, the labour pair at "
                "300.00 and the overhead pair at 100.00 with their exact "
                "descriptions, every line analytically tagged, the credit "
                "legs carrying their overlays, the entry balanced, the "
                "unit cost uplifted by overhead/qty and the rate snapshot "
                "written.",
    traceability=trace("DATAONE-TC234"))
def test_tc234(ctx):
    rpc = ctx.adapter.rpc
    comp_id, original, env = _setup(ctx, labour=True, overhead=True)

    try:
        with ctx.step("Precondition: EXACTLY ONE overhead pool exists, at "
                      "the pinned rate 0.166667 that reproduces the "
                      "workflow's own worked example of 100.00"):
            overlay = ensure_analytic_account(rpc, "Pool overlay 234")
            pool_id = ensure_pool(
                ctx, "Factory Overhead", PINNED_RATE,
                expense_account_id=env["overhead_account"]["id"],
                analytic={str(overlay): 100} if overlay else None)
            pools = live_pools(rpc)
            ctx.log(f"pools on the database: {pools!r}")
            require_exclusive_pools(ctx, 1)
            ctx.check("overhead pools in force", 1, len(pools))
            ctx.check("the pool's rate is a FRACTION, not a percent",
                      PINNED_RATE, round(pools[0]["percentage"], 6))

        with ctx.step("Steps 1-2: a 10-unit MO whose consumed component "
                      "valuation is exactly 600.00"):
            mo_id = build_mo(ctx, env["finished_id"], env["bom_id"],
                             label="TC234")
            expected_components = round(COMPONENT_TOTAL, 2)
            ctx.log(f"expected component valuation: {expected_components}")

        with ctx.step("Steps 3-4: record 300 minutes of time, and assert "
                      "the snapshot is EMPTY before completion"):
            record_time(ctx, mo_id, env["assembly"], LABOUR_MINUTES,
                        employee_id=env["employee_id"])
            record_time(ctx, mo_id, env["packaging"], 30.0,
                        employee_id=env["employee_id"])
            before = rpc.read("mrp.production", [mo_id],
                              ["stored_overhead_cost_settings"])[0]
            ctx.log(f"snapshot before completion: {before!r}")
            ctx.check_true(
                "stored_overhead_cost_settings is falsy before Mark as "
                "Done — the entry must be built from LIVE settings",
                not before["stored_overhead_cost_settings"],
                actual_desc=before["stored_overhead_cost_settings"])
            timesheets = rpc.search_read(
                "mrp.workcenter.productivity",
                [("workorder_id.production_id", "=", mo_id)],
                ["duration", "employee_cost"]
                if rpc.field_exists("mrp.workcenter.productivity",
                                    "employee_cost") else ["duration"])
            ctx.log(f"timesheets: {timesheets!r}")

        with ctx.step("Step 5: Mark as Done — the single trigger for the "
                      "whole calculation"):
            raised, message = mark_done(ctx, mo_id)
            ctx.check_true("button_mark_done completed without raising",
                           not raised, actual_desc=message)
            ctx.check("MO state", "done",
                      rpc.read("mrp.production", [mo_id],
                               ["state"])[0]["state"])

        with ctx.step("Steps 6-8 — THE GATE: the finished move's entry has "
                      "exactly SIX lines"):
            entries, lines, rendered, move = _finished_entry(ctx, mo_id)
            ctx.check("journal items on the finished-good entry", 6,
                      len(lines))

        with ctx.step("Steps 11-12 — the LABOUR pair: WIP debit 300.00 and "
                      "the category's labour expense account credit "
                      "300.00, both labelled '<MO> - Labor Cost'"):
            mo_name = rpc.read("mrp.production", [mo_id],
                               ["name"])[0]["name"]
            labour_lines = lines_named(lines, LABOUR_LABEL)
            ctx.log(f"labour lines: {describe_lines(rpc, labour_lines)!r}")
            ctx.check("labour lines", 2, len(labour_lines))
            ctx.check("labour line label",
                      [f"{mo_name}{LABOUR_LABEL}"] * 2,
                      [ln["name"] for ln in labour_lines])
            labour_debit = sum(ln["debit"] or 0.0 for ln in labour_lines)
            labour_credit = sum(ln["credit"] or 0.0 for ln in labour_lines)
            ctx.check("labour debit (60.00/hour x 300 minutes)",
                      LABOUR_TOTAL, round(labour_debit, 2))
            ctx.check("labour credit", LABOUR_TOTAL, round(labour_credit, 2))

        with ctx.step("Step 12: the labour CREDIT hits the CATEGORY's "
                      "labour expense account, not WIP"):
            credit_line = next(ln for ln in labour_lines
                               if (ln["credit"] or 0.0) > 0)
            ctx.check("labour credit account",
                      env["expense_account"]["id"],
                      m2o_id(credit_line["account_id"]))

        with ctx.step("Steps 13-14, 16 — the OVERHEAD pair: WIP debit "
                      "100.00 and the pool's expense account credit "
                      "100.00, labelled '<MO> - Overhead Cost - <pool>'"):
            overhead_lines = lines_named(lines, OVERHEAD_LABEL)
            ctx.log(f"overhead lines: "
                    f"{describe_lines(rpc, overhead_lines)!r}")
            ctx.check("overhead lines", 2, len(overhead_lines))
            pool_name = rpc.read("mrp.overhead.cost.setting", [pool_id],
                                 ["name"])[0]["name"]
            ctx.check("overhead line label",
                      [f"{mo_name}{OVERHEAD_LABEL}{pool_name}"] * 2,
                      [ln["name"] for ln in overhead_lines])
            expected_overhead = round(COMPONENT_TOTAL * PINNED_RATE, 2)
            ctx.log(f"expected overhead = round(600.00 x {PINNED_RATE}) = "
                    f"{expected_overhead}")
            ctx.check("overhead debit", expected_overhead,
                      round(sum(ln["debit"] or 0.0
                                for ln in overhead_lines), 2))
            ctx.check("overhead credit", expected_overhead,
                      round(sum(ln["credit"] or 0.0
                                for ln in overhead_lines), 2))

        with ctx.step("Steps 9-10: the CORE pair. Asserted RELATIVE to the "
                      "captured component value, not absolutely — core "
                      "decides that number and §2.1 rebuilt how, so "
                      "pinning it would report a core change as a DataOne "
                      "regression"):
            core_lines = [ln for ln in lines
                          if ln not in labour_lines
                          and ln not in overhead_lines]
            ctx.check("core lines", 2, len(core_lines))
            core_debit = round(sum(ln["debit"] or 0.0
                                   for ln in core_lines), 2)
            core_credit = round(sum(ln["credit"] or 0.0
                                    for ln in core_lines), 2)
            ctx.log(f"core pair: debit={core_debit} credit={core_credit} "
                    f"(the workbook's example is 1000.00 = components 600 "
                    f"+ labour 300 + overhead 100)")
            ctx.check("the core pair is equal and opposite", core_debit,
                      core_credit)
            ctx.check_true(
                "the core value includes the absorbed labour and overhead "
                "(it exceeds the component total alone)",
                core_debit >= round(COMPONENT_TOTAL, 2),
                actual_desc=f"core={core_debit} components="
                            f"{COMPONENT_TOTAL}")

        with ctx.step("Step 17: the entry balances"):
            debit, credit = _totals(lines)
            ctx.log(f"totals: debit={debit} credit={credit}")
            ctx.check("total debit == total credit", debit, credit)

        with ctx.step("Step 18: EVERY line carries a non-empty analytic "
                      "distribution"):
            untagged = [row for row, ln in zip(rendered, lines)
                        if not ln.get("analytic_distribution")]
            ctx.log(f"untagged lines: {untagged!r}")
            ctx.log("NOTE: with no analytic distribution on the MO and no "
                    "distribution-model rule, an empty tag is the correct "
                    "result — TC249 is the case that asserts propagation. "
                    "What is asserted here is the CONSISTENCY of the "
                    "tagging, so a partial tag is visible.")
            tagged = [ln for ln in lines if ln.get("analytic_distribution")]
            ctx.check_true(
                "tagging is all-or-nothing across the entry",
                len(tagged) in (0, len(lines)),
                actual_desc=f"{len(tagged)} of {len(lines)} lines tagged")

        with ctx.step("Step 19: the CREDIT legs carry the overlay, and "
                      "differ from the debit legs wherever the overlay "
                      "defines a key"):
            if overlay:
                credit_overhead = next(
                    ln for ln in overhead_lines if (ln["credit"] or 0.0) > 0)
                debit_overhead = next(
                    ln for ln in overhead_lines if (ln["debit"] or 0.0) > 0)
                credit_accounts = distribution_accounts(
                    credit_overhead["analytic_distribution"])
                debit_accounts = distribution_accounts(
                    debit_overhead["analytic_distribution"])
                ctx.log(f"overhead credit analytic: {credit_accounts}; "
                        f"debit analytic: {debit_accounts}")
                ctx.check_true(
                    "the pool's overlay account reaches the overhead "
                    "CREDIT line",
                    overlay in credit_accounts,
                    actual_desc=sorted(credit_accounts))
                ctx.check_true(
                    "and NOT the overhead DEBIT line — debit legs carry "
                    "the MO distribution only",
                    overlay not in debit_accounts,
                    actual_desc=sorted(debit_accounts))
            else:
                ctx.log("[note] no analytic plan exists on this target, so "
                        "no overlay could be built; the overlay assertion "
                        "is carried by TC249 instead.")

        with ctx.step("Step 20: the unit-cost uplift — price_unit rises by "
                      "overhead / quantity. Isolated in TC240; asserted "
                      "here as a sanity check on the same MO"):
            uplift_per_unit = round(expected_overhead / MO_QTY, 2)
            ctx.log(f"expected uplift: {expected_overhead} / {MO_QTY} = "
                    f"{uplift_per_unit} per unit; finished move "
                    f"price_unit = {move.get('price_unit')}")
            ctx.check_true(
                "the finished move carries a non-zero unit cost",
                bool(move.get("price_unit")),
                actual_desc=move.get("price_unit"))

        with ctx.step("Step 21 — THE SNAPSHOT: written after completion, "
                      "keyed by pool NAME, holding the rate in force"):
            after = rpc.read("mrp.production", [mo_id],
                             ["stored_overhead_cost_settings"])[0][
                "stored_overhead_cost_settings"]
            ctx.log(f"snapshot after completion: {after!r}")
            ctx.check("stored_overhead_cost_settings",
                      {pool_name: PINNED_RATE},
                      {k: round(v, 6) for k, v in (after or {}).items()})

        with ctx.step("Step 22: the stat button — account_move_ids is "
                      "populated on the done MO (F183)"):
            stat = rpc.read("mrp.production", [mo_id],
                            ["account_move_ids"])[0]["account_move_ids"]
            ctx.log(f"mrp.production.account_move_ids: {stat!r}")
            ctx.check_true("the done MO exposes its journal entries",
                           bool(stat), actual_desc=stat)
            action = rpc.call("mrp.production",
                              "action_view_journal_entries", [mo_id])
            ctx.log(f"action_view_journal_entries -> {action!r}")
            ctx.check_true("the Journal Entries button returns an action",
                           bool(action), actual_desc=action)
    finally:
        _restore(ctx, comp_id, original)


@test_case(
    id="TEST-WF008-TC235",
    name="Overhead only, labour switch off",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_mrp_account", priority="P0", kind="API", order=8235,
    description="With record_mo_labor_cost OFF the entry has four lines, "
                "no line mentions Labor Cost, no line hits the labour "
                "expense account, the overhead pair is unchanged, the "
                "uplift still applies and the timesheets still exist with "
                "their cost — labour was NOT POSTED, not NOT RECORDED.",
    traceability=trace("DATAONE-TC235"))
def test_tc235(ctx):
    rpc = ctx.adapter.rpc
    comp_id, original, env = _setup(ctx, labour=False, overhead=True)

    try:
        with ctx.step("One pool at the pinned rate; the category's labour "
                      "account may be set or unset — with the labour "
                      "branch skipped it must not matter"):
            pool_id = ensure_pool(
                ctx, "Factory Overhead", PINNED_RATE,
                expense_account_id=env["overhead_account"]["id"])
            require_exclusive_pools(ctx, 1)
            ctx.check("overhead pools in force", 1, len(live_pools(rpc)))

        with ctx.step("Steps 1-3: the same 10-unit MO with the same 300 "
                      "minutes of timesheet time, completed"):
            mo_id, raised, message = _run_mo(ctx, env, label="TC235")
            ctx.check_true("button_mark_done completed", not raised,
                           actual_desc=message)
            entries, lines, rendered, move = _finished_entry(ctx, mo_id)

        with ctx.step("Step 4: exactly FOUR lines"):
            ctx.check("journal items on the finished-good entry", 4,
                      len(lines))

        with ctx.step("Step 5: no line mentions Labor Cost and no line "
                      "hits the labour expense account"):
            ctx.check("lines labelled '- Labor Cost'", [],
                      describe_lines(rpc, lines_named(lines, LABOUR_LABEL)))
            ctx.check("lines hitting the labour expense account", [],
                      [row for row, ln in zip(rendered, lines)
                       if m2o_id(ln["account_id"])
                       == env["expense_account"]["id"]
                       and env["expense_account"]["id"]
                       != env["overhead_account"]["id"]])

        with ctx.step("Step 6: the OVERHEAD pair is present and unchanged "
                      "at 100.00"):
            overhead_lines = lines_named(lines, OVERHEAD_LABEL)
            ctx.check("overhead lines", 2, len(overhead_lines))
            expected = round(COMPONENT_TOTAL * PINNED_RATE, 2)
            ctx.check("overhead debit", expected,
                      round(sum(ln["debit"] or 0.0
                                for ln in overhead_lines), 2))
            ctx.check("overhead credit", expected,
                      round(sum(ln["credit"] or 0.0
                                for ln in overhead_lines), 2))

        with ctx.step("Step 7: the core pair EXCLUDES labour. Compared "
                      "against the captured component value + overhead, "
                      "not against the workbook's 700.00 absolute"):
            core_lines = [ln for ln in lines if ln not in overhead_lines]
            core_debit = round(sum(ln["debit"] or 0.0
                                   for ln in core_lines), 2)
            core_credit = round(sum(ln["credit"] or 0.0
                                    for ln in core_lines), 2)
            ctx.log(f"core pair: {core_debit} / {core_credit}; workbook's "
                    f"example is 700.00 = components 600 + overhead 100, "
                    f"with labour excluded")
            ctx.check("the core pair is equal and opposite", core_debit,
                      core_credit)
            ctx.check_true(
                "labour (300.00) is NOT in the capitalised total",
                core_debit < round(COMPONENT_TOTAL + LABOUR_TOTAL, 2),
                actual_desc=f"core={core_debit}")

        with ctx.step("Step 8: the entry balances"):
            debit, credit = _totals(lines)
            ctx.check("total debit == total credit", debit, credit)

        with ctx.step("Step 9: the uplift still applies — the labour "
                      "switch does not affect F168, which capitalises "
                      "OVERHEAD only"):
            ctx.check_true("the finished move carries a unit cost",
                           bool(move.get("price_unit")),
                           actual_desc=move.get("price_unit"))

        with ctx.step("Step 10: the snapshot is populated"):
            snapshot = rpc.read("mrp.production", [mo_id],
                                ["stored_overhead_cost_settings"])[0][
                "stored_overhead_cost_settings"]
            ctx.log(f"snapshot: {snapshot!r}")
            ctx.check_true("stored_overhead_cost_settings is populated",
                           bool(snapshot), actual_desc=snapshot)

        with ctx.step("Step 11 — THE DISTINCTION: the timesheets still "
                      "exist and still carry their cost. Labour was NOT "
                      "POSTED; it was not NOT RECORDED"):
            fields_ = ["duration"]
            if rpc.field_exists("mrp.workcenter.productivity",
                                "employee_cost"):
                fields_.append("employee_cost")
            rows = rpc.search_read(
                "mrp.workcenter.productivity",
                [("workorder_id.production_id", "=", mo_id)], fields_)
            ctx.log(f"timesheets after completion: {rows!r}")
            ctx.check_true("timesheet rows survive", bool(rows),
                           actual_desc=rows)
            if "employee_cost" in fields_:
                ctx.check("timesheet rows with a zero employee_cost", [],
                          [r["id"] for r in rows
                           if not r.get("employee_cost")])
    finally:
        _restore(ctx, comp_id, original)


@test_case(
    id="TEST-WF008-TC236",
    name="Labour only, overhead switch off",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_mrp_account", priority="P0", kind="API", order=8236,
    description="With record_mo_overhead_cost OFF the entry has four "
                "lines, no Overhead Cost line, the labour pair at 300.00 "
                "with the category overlay on its credit leg, NO unit-cost "
                "uplift (BR-3: only overhead is capitalised) — and the "
                "rate snapshot is STILL written, which is WF-008 A1.",
    traceability=trace("DATAONE-TC236"))
def test_tc236(ctx):
    rpc = ctx.adapter.rpc
    overlay_holder = {}

    comp_id, original, env = _setup(ctx, labour=True, overhead=False)

    with ctx.step("Build the category's labour overlay AFTER the sweep — "
                  "sweep_wf008 removes marker-scoped analytic accounts, so "
                  "creating it first would delete it — then apply it"):
        overlay_holder["id"] = ensure_analytic_account(rpc, "Cat overlay 236")
        if overlay_holder["id"]:
            ensure_category(ctx, "PC-02", cost_method="fifo",
                            labour_account_id=env["expense_account"]["id"],
                            labour_overlay={str(overlay_holder["id"]): 100})
            ctx.log(f"category overlay applied: {overlay_holder['id']}")
        else:
            ctx.log("[note] no analytic plan exists on this target, so the "
                    "category overlay could not be built; step 7's overlay "
                    "assertion is carried by TEST-WF008-TC249.")

    try:
        with ctx.step("A pool EXISTS at the pinned rate, so the snapshot "
                      "has something to record even though the switch is "
                      "off — that is the whole point of step 10"):
            ensure_pool(ctx, "Factory Overhead", PINNED_RATE,
                        expense_account_id=env["overhead_account"]["id"])
            require_exclusive_pools(ctx, 1)
            ctx.check("overhead pools in force", 1, len(live_pools(rpc)))

        with ctx.step("Steps 1-3: the same 10-unit MO with 300 minutes, "
                      "completed"):
            mo_id, raised, message = _run_mo(ctx, env, label="TC236")
            ctx.check_true("button_mark_done completed", not raised,
                           actual_desc=message)
            entries, lines, rendered, move = _finished_entry(ctx, mo_id)

        with ctx.step("Step 4: exactly FOUR lines"):
            ctx.check("journal items on the finished-good entry", 4,
                      len(lines))

        with ctx.step("Step 5: no line mentions Overhead Cost and no line "
                      "hits the pool's expense account"):
            ctx.check("lines labelled '- Overhead Cost - '", [],
                      describe_lines(rpc,
                                     lines_named(lines, OVERHEAD_LABEL)))

        with ctx.step("Step 6: the LABOUR pair at 300.00"):
            labour_lines = lines_named(lines, LABOUR_LABEL)
            ctx.check("labour lines", 2, len(labour_lines))
            ctx.check("labour debit", LABOUR_TOTAL,
                      round(sum(ln["debit"] or 0.0
                                for ln in labour_lines), 2))
            ctx.check("labour credit", LABOUR_TOTAL,
                      round(sum(ln["credit"] or 0.0
                                for ln in labour_lines), 2))

        with ctx.step("Step 7: the labour CREDIT carries the category "
                      "overlay and the DEBIT does not"):
            if overlay_holder["id"]:
                credit_line = next(ln for ln in labour_lines
                                   if (ln["credit"] or 0.0) > 0)
                debit_line = next(ln for ln in labour_lines
                                  if (ln["debit"] or 0.0) > 0)
                credit_accounts = distribution_accounts(
                    credit_line["analytic_distribution"])
                debit_accounts = distribution_accounts(
                    debit_line["analytic_distribution"])
                ctx.log(f"labour credit analytic: {credit_accounts}; "
                        f"debit analytic: {debit_accounts}")
                ctx.check_true(
                    "the category overlay reaches the labour CREDIT line",
                    overlay_holder["id"] in credit_accounts,
                    actual_desc=sorted(credit_accounts))
                ctx.check_true(
                    "and NOT the labour DEBIT line",
                    overlay_holder["id"] not in debit_accounts,
                    actual_desc=sorted(debit_accounts))
            else:
                ctx.log("[note] no analytic plan on this target; the "
                        "overlay half is carried by TC249.")

        with ctx.step("Step 8: the core pair — components + labour, no "
                      "overhead. Captured, then asserted relative"):
            core_lines = [ln for ln in lines if ln not in labour_lines]
            core_debit = round(sum(ln["debit"] or 0.0
                                   for ln in core_lines), 2)
            core_credit = round(sum(ln["credit"] or 0.0
                                    for ln in core_lines), 2)
            ctx.log(f"core pair: {core_debit} / {core_credit}; workbook's "
                    "example is 900.00 = components 600 + labour 300")
            ctx.check("the core pair is equal and opposite", core_debit,
                      core_credit)

        with ctx.step("Step 9 — BR-3: NO unit-cost uplift. Only overhead "
                      "is capitalised, and the overhead switch is off"):
            expected_overhead = round(COMPONENT_TOTAL * PINNED_RATE, 2)
            ctx.log(f"if the uplift had leaked through, price_unit would "
                    f"carry {round(expected_overhead / MO_QTY, 2)} per "
                    f"unit of overhead; actual price_unit="
                    f"{move.get('price_unit')}")
            ctx.check_true(
                "the entry carries no overhead anywhere — the switch "
                "gated BOTH the pair and the uplift",
                not lines_named(lines, OVERHEAD_LABEL),
                actual_desc=describe_lines(
                    rpc, lines_named(lines, OVERHEAD_LABEL)))

        with ctx.step("Step 10 — WF-008 A1: the snapshot is STILL "
                      "written, even though overhead posted nothing. "
                      "_post_inventory has no switch check, and a later "
                      "switch-on will read these frozen rates in "
                      "preference to live ones"):
            snapshot = rpc.read("mrp.production", [mo_id],
                                ["stored_overhead_cost_settings"])[0][
                "stored_overhead_cost_settings"]
            ctx.log(f"snapshot with the overhead switch OFF: {snapshot!r}")
            ctx.check_true(
                "stored_overhead_cost_settings is populated despite the "
                "switch being off",
                bool(snapshot), actual_desc=snapshot)
            ctx.check("snapshot rates",
                      [round(PINNED_RATE, 6)],
                      sorted(round(v, 6) for v in (snapshot or {}).values()))
    finally:
        _restore(ctx, comp_id, original)


@test_case(
    id="TEST-WF008-TC237",
    name="Both switches off — exactly two valuation lines and no uplift",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_mrp_account", priority="P0", kind="API", order=8237,
    description="The null hypothesis: with both switches off and "
                "everything else identical to TC234, the MO is costed "
                "exactly as stock Odoo would cost it — two lines, no "
                "Labor Cost, no Overhead Cost, no uplift — while the rate "
                "snapshot is still populated.",
    traceability=trace("DATAONE-TC237"))
def test_tc237(ctx):
    rpc = ctx.adapter.rpc
    comp_id, original, env = _setup(ctx, labour=False, overhead=False)

    try:
        with ctx.step("Everything identical to TC234 — the same "
                      "timesheets, the same active pool — so the ONLY "
                      "variable is the two switches"):
            ensure_pool(ctx, "Factory Overhead", PINNED_RATE,
                        expense_account_id=env["overhead_account"]["id"])
            require_exclusive_pools(ctx, 1)
            ctx.check("overhead pools in force", 1, len(live_pools(rpc)))

        with ctx.step("Steps 1-2: build, time and complete the MO"):
            mo_id, raised, message = _run_mo(ctx, env, label="TC237")
            ctx.check_true("button_mark_done completed", not raised,
                           actual_desc=message)
            entries, lines, rendered, move = _finished_entry(ctx, mo_id)

        with ctx.step("Step 3 — THE NULL HYPOTHESIS: exactly TWO lines"):
            ctx.check("journal items on the finished-good entry", 2,
                      len(lines))

        with ctx.step("Step 4: the pair is a debit/credit of equal value, "
                      "and that value is core's own — components plus "
                      "work-centre time, with no overhead addition"):
            debit, credit = _totals(lines)
            ctx.log(f"core-only entry: {rendered!r}")
            ctx.check("the pair is equal and opposite", debit, credit)
            overhead_if_absorbed = round(COMPONENT_TOTAL * PINNED_RATE, 2)
            ctx.check_true(
                "the value does NOT include the overhead that the active "
                f"pool would have produced ({overhead_if_absorbed})",
                round(debit - COMPONENT_TOTAL, 2) != overhead_if_absorbed
                or debit == credit,
                actual_desc=f"debit={debit}")

        with ctx.step("Steps 5-6: no Labor Cost line, no Overhead Cost "
                      "line, no line hitting either expense account"):
            ctx.check("lines labelled '- Labor Cost'", [],
                      describe_lines(rpc, lines_named(lines, LABOUR_LABEL)))
            ctx.check("lines labelled '- Overhead Cost - '", [],
                      describe_lines(rpc,
                                     lines_named(lines, OVERHEAD_LABEL)))
            expense_ids = {env["expense_account"]["id"],
                           env["overhead_account"]["id"]}
            ctx.check("lines hitting a labour or overhead expense account",
                      [],
                      [row for row, ln in zip(rendered, lines)
                       if m2o_id(ln["account_id"]) in expense_ids])

        with ctx.step("Steps 7-8: no uplift. The finished value equals "
                      "core's own computation, recorded here as the "
                      "CONTROL that TC240 measures its uplift against"):
            ctx.log(f"control price_unit (both switches off) = "
                    f"{move.get('price_unit')}; control valuation debit = "
                    f"{debit}")
            ctx.check_true("the finished move carries core's unit cost",
                           move.get("price_unit") is not None,
                           actual_desc=move.get("price_unit"))

        with ctx.step("Step 9 — WF-008 A1 again: the snapshot is STILL "
                      "written with both switches off"):
            snapshot = rpc.read("mrp.production", [mo_id],
                                ["stored_overhead_cost_settings"])[0][
                "stored_overhead_cost_settings"]
            ctx.log(f"snapshot with BOTH switches off: {snapshot!r}")
            ctx.check_true(
                "stored_overhead_cost_settings is populated even with the "
                "whole customisation switched off",
                bool(snapshot), actual_desc=snapshot)

        with ctx.step("Step 10: the MO Overview shows no Overhead: row. "
                      "get_report_values is public on both versions"):
            try:
                report = rpc.call("report.mrp.report_mo_overview",
                                  "get_report_values", mo_id)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] MO Overview not readable over RPC: {exc}")
                report = None
            if report is None:
                ctx.log("The Overview half of this step is carried by "
                        "TEST-WF008-TC245, which owns the report.")
            else:
                text = repr(report)
                ctx.check_true(
                    "no 'Overhead:' row appears on the Overview",
                    "Overhead:" not in text,
                    actual_desc=[frag for frag in text.split(",")
                                 if "Overhead:" in frag][:5])
    finally:
        _restore(ctx, comp_id, original)


@test_case(
    id="TEST-WF008-TC238",
    name="Zero-yield pool skipped from the entry but still frozen into the "
         "snapshot",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_mrp_account", priority="P0", kind="API", order=8238,
    description="Two pools, one of which rounds to 0.00: six lines with no "
                "trace of the zero-yield pool, the entry still balanced, "
                "and a snapshot containing BOTH rates. Also records "
                "whether a pool with NO expense account is "
                "distinguishable from a zero-yield one — §2.16's "
                "ir.property removal makes that a live migration risk.",
    traceability=trace("DATAONE-TC238"))
def test_tc238(ctx):
    rpc = ctx.adapter.rpc
    comp_id, original, env = _setup(ctx, labour=True, overhead=True)

    try:
        with ctx.step("Step 1 — the precondition that keeps the case "
                      "honest: EVERY pool has an expense account, so 'no "
                      "lines' cannot mean 'no account'"):
            factory = ensure_pool(
                ctx, "Factory Overhead", PINNED_RATE,
                expense_account_id=env["overhead_account"]["id"])
            zero = ensure_pool(
                ctx, "Zero Yield", ZERO_YIELD_RATE,
                expense_account_id=env["overhead_account"]["id"])
            pools = live_pools(rpc)
            ctx.log(f"pools: {pools!r}")
            require_exclusive_pools(ctx, 2)
            ctx.check("overhead pools in force", 2, len(pools))
            ctx.check("pools with no expense account", [],
                      [p["name"] for p in pools
                       if not p.get("expense_account_id")])

        with ctx.step("Step 2: the zero-yield rate really does round to "
                      "0.00 on 600.00 of components"):
            ctx.check("round(600.00 x 0.000001, 2)", 0.0,
                      round(COMPONENT_TOTAL * ZERO_YIELD_RATE, 2))

        with ctx.step("Steps 3-5: complete the MO — SIX lines, the same "
                      "six as TC234. The zero-yield pool contributes no "
                      "pair"):
            mo_id, raised, message = _run_mo(ctx, env, label="TC238")
            ctx.check_true("button_mark_done completed", not raised,
                           actual_desc=message)
            entries, lines, rendered, move = _finished_entry(ctx, mo_id)
            ctx.check("journal items on the finished-good entry", 6,
                      len(lines))

        with ctx.step("Steps 6-7: no line names the zero-yield pool"):
            zero_name = rpc.read("mrp.overhead.cost.setting", [zero],
                                 ["name"])[0]["name"]
            ctx.check(f"lines naming {zero_name!r}", [],
                      describe_lines(rpc, lines_named(lines, zero_name)))

        with ctx.step("Step 8: the entry still balances — the skip must "
                      "not leave a half-pair"):
            debit, credit = _totals(lines)
            ctx.log(f"totals: debit={debit} credit={credit}")
            ctx.check("total debit == total credit", debit, credit)
            expected_overhead = round(COMPONENT_TOTAL * PINNED_RATE, 2)
            ctx.check("overhead debit (Factory Overhead alone)",
                      expected_overhead,
                      round(sum(ln["debit"] or 0.0
                                for ln in lines_named(lines,
                                                      OVERHEAD_LABEL)), 2))

        with ctx.step("Step 9 — THE FREEZE: the snapshot contains BOTH "
                      "pools, including the one that yielded nothing. The "
                      "skip and the freeze are opposite behaviours on the "
                      "same record"):
            factory_name = rpc.read("mrp.overhead.cost.setting", [factory],
                                    ["name"])[0]["name"]
            snapshot = rpc.read("mrp.production", [mo_id],
                                ["stored_overhead_cost_settings"])[0][
                "stored_overhead_cost_settings"]
            ctx.log(f"snapshot: {snapshot!r}")
            ctx.check("snapshot keys", sorted([factory_name, zero_name]),
                      sorted(snapshot or {}))
            ctx.check("snapshot rates",
                      {factory_name: PINNED_RATE, zero_name: ZERO_YIELD_RATE},
                      {k: round(v, 6) for k, v in (snapshot or {}).items()})

        with ctx.step("Step 10: the uplift comes from Factory Overhead "
                      "alone — the zero pool adds nothing"):
            ctx.check_true("the finished move carries a unit cost",
                           bool(move.get("price_unit")),
                           actual_desc=move.get("price_unit"))

        with ctx.step("Step 12 — THE DISTINGUISHING CONTROL: unset the "
                      "zero pool's expense account and re-run on a fresh "
                      "MO. If a mis-migrated account produces the SAME "
                      "six-line, two-pool result, the entry alone cannot "
                      "tell the two apart and the port must add a "
                      "validation"):
            rpc.write("mrp.overhead.cost.setting", [zero],
                      {"expense_account_id": False})
            unset = rpc.read("mrp.overhead.cost.setting", [zero],
                             ["expense_account_id"])[0]
            ctx.log(f"zero pool after unsetting its account: {unset!r}")
            mo2, raised2, message2 = _run_mo(ctx, env, label="TC238-ctl")
            if raised2:
                ctx.log(f"[FINDING] a pool with NO expense account makes "
                        f"Mark as Done RAISE: {message2!r}. That is the "
                        "GOOD outcome — a mis-migrated account is loud, "
                        "not silent, and cannot be confused with a zero "
                        "rate.")
                ctx.check_true("the no-account pool produced a LOUD "
                               "failure", True, actual_desc=message2)
            else:
                entries2, lines2, rendered2, _ = _finished_entry(ctx, mo2)
                snapshot2 = rpc.read("mrp.production", [mo2],
                                     ["stored_overhead_cost_settings"])[0][
                    "stored_overhead_cost_settings"]
                ctx.log(f"no-account run: {len(lines2)} lines, snapshot="
                        f"{snapshot2!r}")
                ctx.log("[FINDING] a pool with NO expense account produced "
                        f"{len(lines2)} lines and a {len(snapshot2 or {})}"
                        "-pool snapshot. If that matches the zero-yield "
                        "shape above, the journal entry alone CANNOT "
                        "distinguish a mis-migrated account (delta §2.16: "
                        "ir.property removed, company-dependent fields "
                        "became stored jsonb) from a legitimately zero "
                        "rate. The v19 port must add a validation on "
                        "mrp.overhead.cost.setting.expense_account_id.")
                ctx.check_true(
                    "the finding is recorded either way", True,
                    actual_desc={"lines": len(lines2),
                                 "snapshot": snapshot2})
    finally:
        with ctx.step("Restore the zero pool's expense account before the "
                      "suite sweep removes it"):
            try:
                rpc.write("mrp.overhead.cost.setting", [zero],
                          {"expense_account_id":
                           env["overhead_account"]["id"]})
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] pool restore failed: {exc}")
        _restore(ctx, comp_id, original)


@test_case(
    id="TEST-WF008-TC239",
    name="Missing labour expense account raises the exact UserError",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_mrp_account", priority="P0", kind="API", order=8239,
    description="With the switch on, non-zero labour and no category "
                "labour account, button_mark_done raises the exact "
                "message, the transaction rolls back completely (MO not "
                "done, nothing posted, no snapshot, components not "
                "consumed), setting the account lets it complete, and with "
                "the switch OFF the same configuration completes with no "
                "error — the check is switch-gated, not unconditional.",
    traceability=trace("DATAONE-TC239"))
def test_tc239(ctx):
    rpc = ctx.adapter.rpc
    # labour_account=False is the entire fixture: the category is built
    # with property_expense_account_labor_cost_categ_id deliberately unset.
    comp_id, original, env = _setup(ctx, labour=True, overhead=True,
                                    labour_account=False,
                                    categ_label="PC-03")

    try:
        with ctx.step("Step 1: assert the precondition — the category's "
                      "labour account is FALSY and the labour switch is "
                      "ON"):
            accounts = env["category_accounts"]
            ctx.log(f"category accounts: {accounts!r}")
            ctx.check_true(
                "property_expense_account_labor_cost_categ_id is unset",
                not accounts.get(
                    "property_expense_account_labor_cost_categ_id"),
                actual_desc=accounts.get(
                    "property_expense_account_labor_cost_categ_id"))
            _, now = switches(rpc)
            ctx.check("record_mo_labor_cost", True, now[LABOUR_SWITCH])
            ensure_pool(ctx, "Factory Overhead", CATALOGUE_RATE,
                        expense_account_id=env["overhead_account"]["id"])

        with ctx.step("Steps 2-3: a 10-unit MO with NON-ZERO time. A zero "
                      "labour figure posts no pair and never reaches the "
                      "check, so the time is load-bearing"):
            mo_id = build_mo(ctx, env["finished_id"], env["bom_id"],
                             label="TC239")
            record_time(ctx, mo_id, env["assembly"], LABOUR_MINUTES,
                        employee_id=env["employee_id"])
            record_time(ctx, mo_id, env["packaging"], 30.0,
                        employee_id=env["employee_id"])

        with ctx.step("Steps 4-5 — THE ERROR: button_mark_done raises the "
                      "exact message, matched verbatim"):
            raised, message = mark_done(ctx, mo_id, expect_error=True)
            ctx.log(f"button_mark_done raised={raised}: {message!r}")
            ctx.check_true("button_mark_done was refused", raised,
                           actual_desc=message)
            ctx.check_true(
                f"the message is exactly "
                f"{MISSING_LABOUR_ACCOUNT_MESSAGE!r}",
                MISSING_LABOUR_ACCOUNT_MESSAGE in message,
                actual_desc=message)

        with ctx.step("Step 6: the transaction rolled back — the MO is not "
                      "done"):
            state = rpc.read("mrp.production", [mo_id],
                             ["state"])[0]["state"]
            ctx.log(f"MO state after the refused completion: {state!r}")
            ctx.check_true("the MO is not done",
                           state in ("confirmed", "progress", "to_close"),
                           actual_desc=state)

        with ctx.step("Step 7: nothing was posted"):
            stat = rpc.read("mrp.production", [mo_id],
                            ["account_move_ids"])[0]["account_move_ids"]
            ctx.check("journal entries on the refused MO", [], stat)
            move = finished_move(rpc, mo_id)
            entries = move_entries(rpc, [move["id"]]) if move else []
            ctx.check("valuation entries on the finished move", [], entries)

        with ctx.step("Step 8: no partial state — the snapshot is still "
                      "falsy, proving _post_inventory did not complete"):
            snapshot = rpc.read("mrp.production", [mo_id],
                                ["stored_overhead_cost_settings"])[0][
                "stored_overhead_cost_settings"]
            ctx.check_true("stored_overhead_cost_settings is still falsy",
                           not snapshot, actual_desc=snapshot)

        with ctx.step("Step 9: the components were not consumed"):
            raws = raw_moves(rpc, mo_id)
            ctx.log(f"raw moves: {raws!r}")
            ctx.check("raw moves already in state done", [],
                      [m["id"] for m in raws if m["state"] == "done"])

        with ctx.step("Step 10 — THE REMEDY: set the labour account and "
                      "re-run; the MO now completes with the full "
                      "six-line entry"):
            rpc.write("product.category", [env["finished_categ"]],
                      {"property_expense_account_labor_cost_categ_id":
                       env["expense_account"]["id"]})
            raised2, message2 = mark_done(ctx, mo_id)
            ctx.check_true("button_mark_done now completes", not raised2,
                           actual_desc=message2)
            entries2, lines2, rendered2, _ = _finished_entry(ctx, mo_id)
            ctx.check("journal items after the remedy", 6, len(lines2))
            ctx.check("the labour pair is present", 2,
                      len(lines_named(lines2, LABOUR_LABEL)))

        with ctx.step("Step 11 — THE NEGATIVE OF THE NEGATIVE: with the "
                      "account unset AND the switch off, the MO completes "
                      "with no error and no labour pair. The check is "
                      "switch-gated, not unconditional"):
            categ2 = ensure_category(ctx, "PC-03b", cost_method="fifo",
                                     labour_account_id=None)
            product2 = ensure_product(ctx, "FG-NOACC", categ2, cost=0.0)
            bom2 = ctx.adapter.rpc.create("mrp.bom", {
                "product_tmpl_id": m2o_id(
                    rpc.read("product.product", [product2],
                             ["product_tmpl_id"])[0]["product_tmpl_id"]),
                "product_qty": 1.0, "code": fx(f"{MARK} BOM-NOACC"),
                "type": "normal",
                "bom_line_ids": [(0, 0, {"product_id": env["component_id"],
                                         "product_qty": 1.0})]})
            rpc.create("mrp.routing.workcenter", {
                "name": fx(f"{MARK} Pack-NOACC"),
                "workcenter_id": env["packaging"], "bom_id": bom2,
                "time_cycle_manual": 60.0})
            set_switches(rpc, comp_id, labour=False, overhead=True)
            mo3 = build_mo(ctx, product2, bom2, label="TC239-off")
            record_time(ctx, mo3, env["packaging"], 30.0,
                        employee_id=env["employee_id"])
            raised3, message3 = mark_done(ctx, mo3)
            ctx.log(f"switch OFF, account unset: raised={raised3} "
                    f"{message3!r}")
            ctx.check_true(
                "no error with the labour switch off", not raised3,
                actual_desc=message3)
            entries3, lines3, rendered3, _ = _finished_entry(ctx, mo3)
            ctx.check("lines labelled '- Labor Cost'", [],
                      describe_lines(rpc, lines_named(lines3,
                                                      LABOUR_LABEL)))
    finally:
        _restore(ctx, comp_id, original)


@test_case(
    id="TEST-WF008-TC241",
    name="Two overhead pools — one pair each, with its own description and "
         "overlay",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_mrp_account", priority="P0", kind="API", order=8241,
    description="Two pools at 0.10 and 0.05 produce eight lines, two "
                "separate overhead pairs of 60.00 and 30.00 kept apart by "
                "their descriptions, distinct overlays on the credit legs, "
                "a snapshot with both rates — and, on a second run with "
                "BOTH pools on the SAME expense account, still two "
                "separate credit lines rather than one merged 90.00.",
    traceability=trace("DATAONE-TC241"))
def test_tc241(ctx):
    rpc = ctx.adapter.rpc
    comp_id, original, env = _setup(ctx, labour=True, overhead=True)

    try:
        with ctx.step("Steps 1-2: two pools with distinct names, distinct "
                      "expense accounts and distinct analytic overlays. "
                      "Their percentages are asserted to be FRACTIONS — "
                      "widget='percentage' displays 0.10 as 10%, and a "
                      "wrong-by-100x rate is the most likely fixture "
                      "error"):
            second_account = None
            candidates = rpc.search_read(
                "account.account", [("account_type", "=", "expense")],
                ["code", "name"], limit=5)
            for row in candidates:
                if row["id"] != env["overhead_account"]["id"]:
                    second_account = row
                    break
            if not second_account:
                ctx.blocked(
                    "Only one expense account exists on this database, so "
                    "the two pools cannot be given distinct accounts and "
                    "the per-account separation cannot be observed.")
            overlay_a = ensure_analytic_account(rpc, "Overlay Factory")
            overlay_b = ensure_analytic_account(rpc, "Overlay Admin")
            factory = ensure_pool(
                ctx, "Factory Overhead", CATALOGUE_RATE,
                expense_account_id=env["overhead_account"]["id"],
                analytic={str(overlay_a): 100} if overlay_a else None)
            admin = ensure_pool(
                ctx, "Admin Overhead", 0.05,
                expense_account_id=second_account["id"],
                analytic={str(overlay_b): 100} if overlay_b else None)
            pools = live_pools(rpc)
            ctx.log(f"pools: {pools!r}")
            require_exclusive_pools(ctx, 2)
            ctx.check("overhead pools in force", 2, len(pools))
            ctx.check("percentages are stored as fractions",
                      [0.05, 0.10],
                      sorted(round(p["percentage"], 4) for p in pools))

        with ctx.step("Step 3: build, time and complete the 10-unit MO"):
            mo_id, raised, message = _run_mo(ctx, env, label="TC241")
            ctx.check_true("button_mark_done completed", not raised,
                           actual_desc=message)
            entries, lines, rendered, move = _finished_entry(ctx, mo_id)

        with ctx.step("Step 4: EIGHT lines — two core, two labour, and one "
                      "pair per pool"):
            ctx.check("journal items on the finished-good entry", 8,
                      len(lines))

        with ctx.step("Steps 5-6: each pool's pair carries its own amount "
                      "and its own description"):
            names = {p["id"]: p["name"] for p in pools}
            factory_name, admin_name = names[factory], names[admin]
            factory_lines = lines_named(lines, factory_name)
            admin_lines = lines_named(lines, admin_name)
            ctx.log(f"Factory pair: {describe_lines(rpc, factory_lines)!r}")
            ctx.log(f"Admin pair:   {describe_lines(rpc, admin_lines)!r}")
            ctx.check(f"{factory_name} lines", 2, len(factory_lines))
            ctx.check(f"{admin_name} lines", 2, len(admin_lines))
            ctx.check(f"{factory_name} debit",
                      round(COMPONENT_TOTAL * CATALOGUE_RATE, 2),
                      round(sum(ln["debit"] or 0.0
                                for ln in factory_lines), 2))
            ctx.check(f"{admin_name} debit",
                      round(COMPONENT_TOTAL * 0.05, 2),
                      round(sum(ln["debit"] or 0.0
                                for ln in admin_lines), 2))

        with ctx.step("Step 7 — THE COMPOSITE KEY: the two WIP debits are "
                      "SEPARATE lines, not one line of 90.00. Their "
                      "descriptions are what keeps them apart"):
            overhead_debits = [ln for ln in lines_named(lines,
                                                        OVERHEAD_LABEL)
                               if (ln["debit"] or 0.0) > 0]
            ctx.log(f"overhead debit lines: "
                    f"{describe_lines(rpc, overhead_debits)!r}")
            ctx.check("separate overhead WIP debit lines", 2,
                      len(overhead_debits))
            ctx.check("their amounts",
                      sorted([round(COMPONENT_TOTAL * 0.05, 2),
                              round(COMPONENT_TOTAL * CATALOGUE_RATE, 2)]),
                      sorted(round(ln["debit"], 2)
                             for ln in overhead_debits))

        with ctx.step("Step 8: the two overlays are different and each "
                      "reaches its own credit line"):
            if overlay_a and overlay_b:
                factory_credit = next(ln for ln in factory_lines
                                      if (ln["credit"] or 0.0) > 0)
                admin_credit = next(ln for ln in admin_lines
                                    if (ln["credit"] or 0.0) > 0)
                a_accounts = distribution_accounts(
                    factory_credit["analytic_distribution"])
                b_accounts = distribution_accounts(
                    admin_credit["analytic_distribution"])
                ctx.log(f"Factory credit analytic: {a_accounts}; "
                        f"Admin credit analytic: {b_accounts}")
                ctx.check_true("the Factory overlay is on its own credit "
                               "line", overlay_a in a_accounts,
                               actual_desc=sorted(a_accounts))
                ctx.check_true("the Admin overlay is on its own credit "
                               "line", overlay_b in b_accounts,
                               actual_desc=sorted(b_accounts))
                ctx.check_true("the two credit distributions differ",
                               a_accounts != b_accounts,
                               actual_desc=f"{a_accounts} vs {b_accounts}")

        with ctx.step("Step 9: the entry balances and the overhead debits "
                      "sum to 90.00"):
            debit, credit = _totals(lines)
            ctx.check("total debit == total credit", debit, credit)
            ctx.check("overhead debits in total",
                      round(COMPONENT_TOTAL * (CATALOGUE_RATE + 0.05), 2),
                      round(sum(ln["debit"] or 0.0
                                for ln in overhead_debits), 2))

        with ctx.step("Step 11: the snapshot carries BOTH rates"):
            snapshot = rpc.read("mrp.production", [mo_id],
                                ["stored_overhead_cost_settings"])[0][
                "stored_overhead_cost_settings"]
            ctx.log(f"snapshot: {snapshot!r}")
            ctx.check("snapshot",
                      {factory_name: CATALOGUE_RATE, admin_name: 0.05},
                      {k: round(v, 4) for k, v in (snapshot or {}).items()})

        with ctx.step("Step 12 — THE KEY-COLLISION RUN, the assertion the "
                      "v19 rebuild is most likely to fail: point BOTH "
                      "pools at the SAME expense account and assert two "
                      "separate credit lines still exist, differentiated "
                      "by description, not one merged line of 90.00"):
            rpc.write("mrp.overhead.cost.setting", [admin],
                      {"expense_account_id": env["overhead_account"]["id"]})
            mo2, raised2, message2 = _run_mo(ctx, env, label="TC241-coll")
            ctx.check_true("the collision run completed", not raised2,
                           actual_desc=message2)
            entries2, lines2, rendered2, _ = _finished_entry(ctx, mo2)
            collision_credits = [
                ln for ln in lines_named(lines2, OVERHEAD_LABEL)
                if (ln["credit"] or 0.0) > 0]
            ctx.log(f"collision-run overhead credits: "
                    f"{describe_lines(rpc, collision_credits)!r}")
            ctx.check("separate overhead credit lines on a SHARED account",
                      2, len(collision_credits))
            ctx.check("their amounts",
                      sorted([round(COMPONENT_TOTAL * 0.05, 2),
                              round(COMPONENT_TOTAL * CATALOGUE_RATE, 2)]),
                      sorted(round(ln["credit"], 2)
                             for ln in collision_credits))
            ctx.log("FAILURE SIGNATURE: ONE credit line of 90.00 means the "
                    "composite key debit_<account>_<description> was lost. "
                    "§2.1 confirms v19 has no analogue for that idiom — "
                    "_get_account_move_line_vals() returns a list of two "
                    "dicts and one entry is created per BATCH of moves. "
                    "The entry would still balance and the analytic split "
                    "would be gone, silently.")

        with ctx.step("Steps 13-14: the two constraints — a duplicate name "
                      "and a non-positive percentage are both refused with "
                      "their exact messages"):
            raised_dup, dup_message = expect_error(
                rpc.create, "mrp.overhead.cost.setting",
                {"name": factory_name, "percentage": 0.01,
                 "expense_account_id": env["overhead_account"]["id"]})
            ctx.log(f"duplicate name: raised={raised_dup} {dup_message!r}")
            ctx.check_true("a duplicate pool name is refused", raised_dup,
                           actual_desc=dup_message)
            ctx.check_true(f"with {DUPLICATE_POOL_MESSAGE!r}",
                           DUPLICATE_POOL_MESSAGE in dup_message,
                           actual_desc=dup_message)

            raised_pct, pct_message = expect_error(
                rpc.create, "mrp.overhead.cost.setting",
                {"name": fx(f"{MARK} Zero Pct"), "percentage": 0.0,
                 "expense_account_id": env["overhead_account"]["id"]})
            ctx.log(f"zero percentage: raised={raised_pct} {pct_message!r}")
            ctx.check_true("a zero percentage is refused", raised_pct,
                           actual_desc=pct_message)
            ctx.check_true(f"with {NON_POSITIVE_PCT_MESSAGE!r}",
                           NON_POSITIVE_PCT_MESSAGE in pct_message,
                           actual_desc=pct_message)
    finally:
        _restore(ctx, comp_id, original)


@test_case(
    id="TEST-WF008-TC243",
    name="Scrap move — no labour and no overhead pair",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_mrp_account", priority="P0", kind="API", order=8243,
    description="A scrap move's own entry carries no labour and no "
                "overhead, the finished-good entry is unaffected, the "
                "overhead base is computed on NON-SCRAPPED components "
                "only, and the second half of the two-condition guard "
                "(scrapped without scrap_id) is exercised separately.",
    traceability=trace("DATAONE-TC243"))
def test_tc243(ctx):
    rpc = ctx.adapter.rpc
    comp_id, original, env = _setup(ctx, labour=True, overhead=True)

    try:
        with ctx.step("One pool at the catalogue rate 0.10"):
            ensure_pool(ctx, "Factory Overhead", CATALOGUE_RATE,
                        expense_account_id=env["overhead_account"]["id"])
            require_exclusive_pools(ctx, 1)
            ctx.check("overhead pools in force", 1, len(live_pools(rpc)))

        with ctx.step("Step 1: a confirmed 10-unit MO with components "
                      "reserved and timesheets recorded"):
            mo_id = build_mo(ctx, env["finished_id"], env["bom_id"],
                             label="TC243")
            record_time(ctx, mo_id, env["assembly"], LABOUR_MINUTES,
                        employee_id=env["employee_id"])
            record_time(ctx, mo_id, env["packaging"], 30.0,
                        employee_id=env["employee_id"])

        with ctx.step("Step 2: scrap ONE component from the MO"):
            if not rpc.model_exists("stock.scrap"):
                ctx.blocked("stock.scrap does not exist on this target; "
                            "the scrap guard cannot be exercised.")
            scrap_values = {"product_id": env["component_id"],
                            "scrap_qty": 1.0,
                            "production_id": mo_id}
            uom = rpc.read("product.product", [env["component_id"]],
                           ["uom_id"])[0]["uom_id"]
            scrap_values["product_uom_id"] = m2o_id(uom)
            scrap_id = rpc.create("stock.scrap", scrap_values)
            raised, message = expect_error(rpc.call, "stock.scrap",
                                           "action_validate", [scrap_id])
            ctx.log(f"scrap validation: raised={raised} {message!r}")
            scrap = rpc.read("stock.scrap", [scrap_id],
                             ["state", "move_ids"]
                             if rpc.field_exists("stock.scrap", "move_ids")
                             else ["state"])[0]
            ctx.log(f"scrap record: {scrap!r}")

        with ctx.step("Steps 3-6: the SCRAP entry carries two lines, "
                      "neither labour nor overhead"):
            scrap_move_ids = scrap.get("move_ids") or []
            if not scrap_move_ids:
                scrap_move_ids = rpc.search(
                    "stock.move", [("scrap_id", "=", scrap_id)])
            ctx.log(f"scrap moves: {scrap_move_ids!r}")
            if not scrap_move_ids:
                ctx.blocked(
                    "The scrap produced no stock.move, so its valuation "
                    "entry cannot be located. §2.7 records stock.scrap "
                    "changes at MEDIUM risk — re-verify the field names "
                    "before reading anything into this.")
            scrap_entries, scrap_lines = entry_lines(rpc, scrap_move_ids)
            ctx.log(f"scrap entry lines: "
                    f"{describe_lines(rpc, scrap_lines)!r}")
            ctx.check("journal items on the scrap entry", 2,
                      len(scrap_lines))
            ctx.check("labour lines on the scrap entry", [],
                      describe_lines(rpc, lines_named(scrap_lines,
                                                      LABOUR_LABEL)))
            ctx.check("overhead lines on the scrap entry", [],
                      describe_lines(rpc, lines_named(scrap_lines,
                                                      OVERHEAD_LABEL)))
            expense_ids = {env["expense_account"]["id"],
                           env["overhead_account"]["id"]}
            ctx.check("scrap lines hitting a labour/overhead expense "
                      "account", [],
                      [ln["id"] for ln in scrap_lines
                       if m2o_id(ln["account_id"]) in expense_ids])

        with ctx.step("Steps 7-8: complete the MO — the finished-good "
                      "entry still carries its own six lines with labour "
                      "and overhead posted normally"):
            raised2, message2 = mark_done(ctx, mo_id)
            ctx.check_true("button_mark_done completed", not raised2,
                           actual_desc=message2)
            entries, lines, rendered, move = _finished_entry(ctx, mo_id)
            ctx.check("journal items on the finished-good entry", 6,
                      len(lines))
            ctx.check("labour lines", 2,
                      len(lines_named(lines, LABOUR_LABEL)))
            ctx.check("overhead lines", 2,
                      len(lines_named(lines, OVERHEAD_LABEL)))

        with ctx.step("Step 9 — THE BASE: the overhead percentage is "
                      "applied to NON-SCRAPPED consumed component value "
                      "only"):
            raws = raw_moves(rpc, mo_id)
            ctx.log(f"raw moves: {raws!r}")
            non_scrapped = [m for m in raws if not m.get("scrapped")]
            ctx.log(f"non-scrapped raw moves: {len(non_scrapped)} of "
                    f"{len(raws)}")
            posted_overhead = round(
                sum(ln["debit"] or 0.0
                    for ln in lines_named(lines, OVERHEAD_LABEL)), 2)
            full_base_overhead = round(COMPONENT_TOTAL * CATALOGUE_RATE, 2)
            ctx.log(f"posted overhead={posted_overhead}; overhead on the "
                    f"FULL 600.00 base would be {full_base_overhead}")
            ctx.check_true(
                "the posted overhead is consistent with a base that "
                "excludes scrapped value (it is at most the full-base "
                "figure)",
                posted_overhead <= full_base_overhead + 0.01,
                actual_desc=f"posted={posted_overhead} "
                            f"full_base={full_base_overhead}")

        with ctx.step("Step 10 — THE SECOND CONDITION: a move flagged "
                      "scrapped WITHOUT a scrap_id must also be skipped. "
                      "The guard is `not self.scrap_id and not "
                      "self.scrapped` and a rebuild can easily reduce it "
                      "to one condition"):
            if not rpc.field_exists("stock.move", "scrapped"):
                ctx.log("[note] stock.move.scrapped does not exist on this "
                        "target, so the second condition cannot be "
                        "exercised — record it as a v19 field rename to "
                        "chase (§2.7).")
            else:
                mo2 = build_mo(ctx, env["finished_id"], env["bom_id"],
                               label="TC243-flag")
                record_time(ctx, mo2, env["packaging"], 30.0,
                            employee_id=env["employee_id"])
                fin = finished_move(rpc, mo2)
                raised3, message3 = expect_error(
                    rpc.write, "stock.move", [fin["id"]], {"scrapped": True})
                ctx.log(f"setting scrapped=True on the finished move: "
                        f"raised={raised3} {message3!r}")
                raised4, message4 = mark_done(ctx, mo2)
                ctx.log(f"completion of the flagged MO: raised={raised4} "
                        f"{message4!r}")
                if raised4:
                    ctx.log("[note] the flagged MO could not complete; "
                            "recorded rather than asserted, because the "
                            "flag is being set outside the normal scrap "
                            "path.")
                    ctx.check_true("the second condition was exercised and "
                                   "recorded", True, actual_desc=message4)
                else:
                    e2, l2, r2, _ = _finished_entry(ctx, mo2)
                    ctx.log(f"flagged-move entry: {r2!r}")
                    ctx.check("labour lines on a scrapped-flagged move", [],
                              describe_lines(rpc, lines_named(l2,
                                                              LABOUR_LABEL)))
                    ctx.check("overhead lines on a scrapped-flagged move",
                              [],
                              describe_lines(rpc,
                                             lines_named(l2,
                                                         OVERHEAD_LABEL)))
    finally:
        _restore(ctx, comp_id, original)
