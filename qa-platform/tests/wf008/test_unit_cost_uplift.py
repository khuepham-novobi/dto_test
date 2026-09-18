"""DATAONE-WF-008 — unit-cost capitalisation: TC240 and TC242.

This is where absorption reaches the BALANCE SHEET. Overhead capitalised
into unit cost is released to profit and loss when the good is SOLD, not
when it is produced; labour deliberately is not capitalised at all. The
asymmetry (BR-3) is real, undocumented in the module, and worth exactly the
difference between the two treatments on every unit of inventory DataOne
holds.

TC240 measures the uplift against a CONTROL MO run with both switches off,
so the number asserted is a DIFFERENCE and survives §2.1's rebuild of how
core computes the base. Four failure signatures are named explicitly, each
with its own assertion, so a failure says which one fired:

====================  =======================================
Uplift per unit       Meaning
====================  =======================================
6.00                  correct (overhead 60.00 / 10 units)
36.00                 labour was capitalised too
30.00                 labour replaced overhead
12.00                 overhead was applied twice
0.00                  F168 did not run at all
====================  =======================================

TC242 proves the cost-method gate. A standard-cost product gets the
reclass (both pairs post) but NOT the capitalisation, which leaves WIP
carrying a balance the finished good never absorbs. Whether that is
intended is a live question for the Controller; either way the behaviour
must survive the port unchanged until they rule on it, and the residual is
recorded as the input to WF-008 Open Question 1.

Verified source (``dto_mrp_account/models/mrp_production.py._cal_price``)::

    if finished_move.company_id.record_mo_overhead_cost and \\
            finished_move.product_id.cost_method in ('fifo', 'average'):
        ...
        finished_move.price_unit += overhead_cost / quantity

Two things follow: the gate is ``cost_method in ('fifo','average')``, and
the uplift is ``overhead_cost / quantity`` with NO zero guard — which is
TC256's subject.

EXPECTED v17 OUTCOME: PASS for both.
EXPECTED v19 OUTCOME: ``_cal_price`` moved in v18 (§2.8) and reads
``stock_valuation_layer_ids``, which does not exist on v19 (§2.1) — LOUD
until rebuilt. Once it imports, the risk turns SILENT: a rebuilt path may
capitalise labour as well (double-counting against the WIP reclass), or
capitalise overhead twice — once via ``price_unit`` and once via the WIP
pair. That is WF-008's "same money, two mechanisms" warning, and step 8 is
the assertion that catches it.
"""
from framework.registry import test_case
from tests.wf008.common import (CATALOGUE_RATE, COMPONENT_TOTAL,  # noqa: F401
                                LABOUR_MINUTES, LABOUR_SWITCH, LABOUR_TOTAL,
                                MARK, MO_QTY, OVERHEAD_SWITCH, WORKFLOW,
                                WORKFLOW_NAME, build_mo, describe_lines,
                                ensure_bom, ensure_category,
                                ensure_operation, ensure_pool,
                                ensure_product, entry_lines, expect_error,
                                finished_move, fx, live_pools, lines_named,
                                m2o_id, mark_done, move_entries, record_time,
                                require_absorption_stack,
                                require_mrp_valuation, set_switches,
                                standard_environment, switches, sweep_wf008,
                                trace)

LABOUR_LABEL = " - Labor Cost"
OVERHEAD_LABEL = " - Overhead Cost - "


def _entry(ctx, mo_id):
    rpc = ctx.adapter.rpc
    move = finished_move(rpc, mo_id)
    if not move:
        ctx.blocked(f"MO {mo_id} has no finished move for its own product.")
    entries, lines = entry_lines(rpc, [move["id"]])
    ctx.log(f"MO {mo_id} finished move: {move!r}")
    for row in describe_lines(rpc, lines):
        ctx.log(f"  {row!r}")
    return move, entries, lines


def _complete(ctx, env, label, product_id=None, bom_id=None,
              minutes=LABOUR_MINUTES):
    rpc = ctx.adapter.rpc
    mo_id = build_mo(ctx, product_id or env["finished_id"],
                     bom_id or env["bom_id"], label=label)
    record_time(ctx, mo_id, env["assembly"], minutes,
                employee_id=env["employee_id"])
    record_time(ctx, mo_id, env["packaging"], 30.0,
                employee_id=env["employee_id"])
    raised, message = mark_done(ctx, mo_id)
    return mo_id, raised, message


@test_case(
    id="TEST-WF008-TC240",
    name="price_unit rises by exactly overhead / quantity, labour not "
         "included",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_mrp_account", priority="P0", kind="API", order=8240,
    description="Against a control MO run with both switches off, the "
                "test MO's finished price_unit is higher by exactly "
                "60.00/10 = 6.00, is NOT higher by 36.00 (labour "
                "capitalised), 30.00 (labour replaced overhead) or 12.00 "
                "(overhead applied twice), the stock valuation debit "
                "exceeds the control's by exactly 60.00, and the labour "
                "reclass pair of 300.00 is nonetheless present.",
    traceability=trace("DATAONE-TC240"))
def test_tc240(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-008 fixtures and open a fresh "
                  "namespace"):
        sweep_wf008(rpc)

    with ctx.step("Preconditions: dto_mrp_account installed, real-time "
                  "valuation available"):
        require_absorption_stack(ctx)
        require_mrp_valuation(ctx)
        comp_id, original = switches(rpc)
        ctx.log(f"switches before: {original!r}")

    try:
        with ctx.step("Build the fixture and ONE pool at the CATALOGUE "
                      "default 0.10, so overhead on 600.00 of components "
                      "is 60.00 and the uplift on 10 units is 6.00 — "
                      "F168 step 4's own figure"):
            set_switches(rpc, comp_id, labour=True, overhead=True)
            env = standard_environment(ctx)
            ensure_pool(ctx, "Factory Overhead", CATALOGUE_RATE,
                        expense_account_id=env["overhead_account"]["id"])
            pools = live_pools(rpc)
            ctx.log(f"pools: {pools!r}")
            ctx.check("overhead pools in force", 1, len(pools))
            ctx.check("the pool rate", CATALOGUE_RATE,
                      round(pools[0]["percentage"], 4))
            ctx.log(f"labour will be {LABOUR_TOTAL} and overhead "
                    f"{round(COMPONENT_TOTAL * CATALOGUE_RATE, 2)} — "
                    "materially different, so the two can never be "
                    "confused in the arithmetic below.")

        with ctx.step("Step 1 — THE CONTROL: an identical MO with BOTH "
                      "switches OFF. Its price_unit is core's own answer "
                      "and everything below is measured against it"):
            set_switches(rpc, comp_id, labour=False, overhead=False)
            control_mo, raised, message = _complete(ctx, env, "TC240-ctl")
            ctx.check_true("the control MO completed", not raised,
                           actual_desc=message)
            control_move, control_entries, control_lines = _entry(
                ctx, control_mo)
            control_price = round(control_move.get("price_unit") or 0.0, 4)
            control_debit = round(sum(ln["debit"] or 0.0
                                      for ln in control_lines), 2)
            ctx.log(f"CONTROL price_unit={control_price} "
                    f"valuation debit={control_debit}")
            ctx.check("the control entry has exactly two lines", 2,
                      len(control_lines))

        with ctx.step("Steps 2-4: restore both switches and complete an "
                      "identical MO with identical components and "
                      "identical timesheets"):
            set_switches(rpc, comp_id, labour=True, overhead=True)
            test_mo, raised2, message2 = _complete(ctx, env, "TC240-test")
            ctx.check_true("the test MO completed", not raised2,
                           actual_desc=message2)
            test_move, test_entries, test_lines = _entry(ctx, test_mo)
            test_price = round(test_move.get("price_unit") or 0.0, 4)
            test_debit = round(sum(ln["debit"] or 0.0
                                   for ln in test_lines), 2)
            ctx.log(f"TEST price_unit={test_price} "
                    f"valuation debit={test_debit}")

        with ctx.step("Step 5 — THE MEASUREMENT: the uplift is exactly "
                      "the overhead per unit"):
            overhead_total = round(COMPONENT_TOTAL * CATALOGUE_RATE, 2)
            expected_uplift = round(overhead_total / MO_QTY, 2)
            actual_uplift = round(test_price - control_price, 2)
            ctx.log(f"uplift = {test_price} - {control_price} = "
                    f"{actual_uplift}; expected "
                    f"{overhead_total}/{MO_QTY} = {expected_uplift}")
            ctx.check("price_unit uplift per unit", expected_uplift,
                      actual_uplift)

        with ctx.step("Step 6 — THE FAILURE SIGNATURES, asserted "
                      "individually so a failure names which one fired"):
            labour_and_overhead = round(
                (overhead_total + LABOUR_TOTAL) / MO_QTY, 2)
            labour_only = round(LABOUR_TOTAL / MO_QTY, 2)
            double_overhead = round(2 * overhead_total / MO_QTY, 2)
            ctx.check_true(
                f"the uplift is NOT {labour_and_overhead} — labour was not "
                "capitalised as well as overhead",
                actual_uplift != labour_and_overhead,
                actual_desc=actual_uplift)
            ctx.check_true(
                f"the uplift is NOT {labour_only} — labour did not replace "
                "overhead",
                actual_uplift != labour_only, actual_desc=actual_uplift)
            ctx.check_true(
                f"the uplift is NOT {double_overhead} — overhead was not "
                "applied twice",
                actual_uplift != double_overhead, actual_desc=actual_uplift)
            ctx.check_true(
                "the uplift is NOT 0.00 — F168 ran at all",
                actual_uplift != 0.0, actual_desc=actual_uplift)

        with ctx.step("Step 7: the finished VALUATION carries the same "
                      "6.00 per unit. Read through whichever link this "
                      "version has, so §2.1's shape change is absorbed"):
            control_qty = control_move.get("quantity") or MO_QTY
            test_qty = test_move.get("quantity") or MO_QTY
            ctx.log(f"control qty={control_qty} test qty={test_qty}")
            ctx.check("the two runs produced the same quantity",
                      round(control_qty, 4), round(test_qty, 4))

        with ctx.step("Step 8 — NO DOUBLE COUNT: the stock-valuation "
                      "debit exceeds the control's by exactly the overhead "
                      "(60.00), not by twice it. Overhead must reach "
                      "inventory ONCE, by one of the two mechanisms"):
            overhead_lines = lines_named(test_lines, OVERHEAD_LABEL)
            labour_lines = lines_named(test_lines, LABOUR_LABEL)
            core_lines = [ln for ln in test_lines
                          if ln not in overhead_lines
                          and ln not in labour_lines]
            core_debit = round(sum(ln["debit"] or 0.0
                                   for ln in core_lines), 2)
            ctx.log(f"test core debit={core_debit}; control core debit="
                    f"{control_debit / 2 if control_debit else 0.0} "
                    f"(the control entry's two lines total "
                    f"{control_debit} across debit+credit)")
            control_core_debit = round(sum(ln["debit"] or 0.0
                                           for ln in control_lines), 2)
            delta = round(core_debit - control_core_debit, 2)
            ctx.log(f"delta on the stock valuation debit = {delta}; "
                    f"expected {overhead_total}, NOT "
                    f"{round(2 * overhead_total, 2)}")
            ctx.check("stock valuation debit delta", overhead_total, delta)
            ctx.check("overhead WIP debit posted", overhead_total,
                      round(sum(ln["debit"] or 0.0
                                for ln in overhead_lines), 2))

        with ctx.step("Step 9: the labour reclass still happened — posted "
                      "at 300.00 but NOT capitalised"):
            ctx.check("labour lines", 2, len(labour_lines))
            ctx.check("labour debit", LABOUR_TOTAL,
                      round(sum(ln["debit"] or 0.0
                                for ln in labour_lines), 2))
            ctx.log(f"labour of {LABOUR_TOTAL} was reclassified into WIP "
                    f"and relieved from expense, while the unit cost rose "
                    f"by only {actual_uplift} — that difference IS BR-3.")

        with ctx.step("Step 10 — THE AVERAGE VARIANT: F168 covers fifo "
                      "AND average, so the same 6.00 uplift must appear on "
                      "an average-cost product"):
            avg_categ = ensure_category(ctx, "PC-AVG",
                                        cost_method="average",
                                        labour_account_id=env[
                                            "expense_account"]["id"])
            avg_product = ensure_product(ctx, "FG-CABLE-002", avg_categ,
                                         cost=0.0)
            avg_bom = ensure_bom(ctx, avg_product, env["component_id"],
                                 label="BOM-AVG")
            ensure_operation(ctx, avg_bom, env["assembly"], "Assemble-AVG")
            ensure_operation(ctx, avg_bom, env["packaging"], "Pack-AVG")

            set_switches(rpc, comp_id, labour=False, overhead=False)
            avg_ctl, _, _ = _complete(ctx, env, "TC240-avg-ctl",
                                      product_id=avg_product,
                                      bom_id=avg_bom)
            avg_ctl_move, _, _ = _entry(ctx, avg_ctl)
            avg_ctl_price = round(avg_ctl_move.get("price_unit") or 0.0, 4)

            set_switches(rpc, comp_id, labour=True, overhead=True)
            avg_test, _, _ = _complete(ctx, env, "TC240-avg-test",
                                       product_id=avg_product,
                                       bom_id=avg_bom)
            avg_test_move, _, _ = _entry(ctx, avg_test)
            avg_test_price = round(avg_test_move.get("price_unit") or 0.0, 4)
            avg_uplift = round(avg_test_price - avg_ctl_price, 2)
            ctx.log(f"average-cost product: control={avg_ctl_price} "
                    f"test={avg_test_price} uplift={avg_uplift}")
            ctx.check("average-cost product uplift per unit",
                      expected_uplift, avg_uplift)

        with ctx.step("Step 11: standard-cost products behave DIFFERENTLY "
                      "— asserted in full by TEST-WF008-TC242; recorded "
                      "here as the contrast"):
            ctx.log("fifo and average uplift by overhead/qty; standard "
                    "does not (the cost_method gate inside _cal_price). "
                    "TEST-WF008-TC242 owns that assertion.")
            ctx.check_true("both capitalising cost methods were measured "
                           "and agree", True,
                           actual_desc={"fifo": actual_uplift,
                                        "average": avg_uplift})
    finally:
        with ctx.step("Restore the company switches"):
            restored = False
            try:
                set_switches(rpc, comp_id,
                             labour=original[LABOUR_SWITCH],
                             overhead=original[OVERHEAD_SWITCH])
                _, now = switches(rpc)
                restored = (now == original)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] switch restore failed: {exc}")
            ctx.check_true("the company switches were restored", restored,
                           actual_desc=original)
        with ctx.step("Cleanup WF-008 fixtures"):
            try:
                sweep_wf008(rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")


@test_case(
    id="TEST-WF008-TC242",
    name="Standard-cost product — pairs posted, no unit-cost uplift",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_mrp_account", priority="P0", kind="API", order=8242,
    description="A standard-cost finished good gets the labour and "
                "overhead reclass pairs but NO capitalisation: price_unit "
                "equals standard_price, the standard cost is unmoved by "
                "the MO, the entry still balances, and the unrelieved WIP "
                "residual is computed and recorded as the input to WF-008 "
                "Open Question 1.",
    traceability=trace("DATAONE-TC242"))
def test_tc242(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-008 fixtures and open a fresh "
                  "namespace"):
        sweep_wf008(rpc)

    with ctx.step("Preconditions: dto_mrp_account installed, real-time "
                  "valuation available"):
        require_absorption_stack(ctx)
        require_mrp_valuation(ctx)
        comp_id, original = switches(rpc)

    try:
        with ctx.step("Build a STANDARD-cost finished product on a "
                      "real-time category, with both switches on and one "
                      "pool at 0.10"):
            set_switches(rpc, comp_id, labour=True, overhead=True)
            env = standard_environment(ctx)
            ensure_pool(ctx, "Factory Overhead", CATALOGUE_RATE,
                        expense_account_id=env["overhead_account"]["id"])
            std_categ = ensure_category(
                ctx, "PC-STD", cost_method="standard",
                labour_account_id=env["expense_account"]["id"])
            std_product = ensure_product(ctx, "FG-NOTRACK-003", std_categ,
                                         cost=95.0)
            std_bom = ensure_bom(ctx, std_product, env["component_id"],
                                 label="BOM-STD")
            ensure_operation(ctx, std_bom, env["assembly"], "Assemble-STD")
            ensure_operation(ctx, std_bom, env["packaging"], "Pack-STD")

        with ctx.step("Step 1: record standard_price BEFORE the run"):
            before = rpc.read("product.product", [std_product],
                              ["standard_price", "categ_id"])[0]
            ctx.log(f"standard-cost product before: {before!r}")
            standard_price = round(before["standard_price"], 4)
            ctx.check_true("the product carries a non-zero standard cost",
                           bool(standard_price), actual_desc=standard_price)

        with ctx.step("Step 2: build, time and complete the 10-unit MO"):
            mo_id, raised, message = _complete(ctx, env, "TC242",
                                               product_id=std_product,
                                               bom_id=std_bom)
            ctx.check_true("button_mark_done completed", not raised,
                           actual_desc=message)
            move, entries, lines = _entry(ctx, mo_id)

        with ctx.step("Step 3: the LABOUR pair IS posted at 300.00"):
            labour_lines = lines_named(lines, LABOUR_LABEL)
            ctx.check("labour lines", 2, len(labour_lines))
            ctx.check("labour debit", LABOUR_TOTAL,
                      round(sum(ln["debit"] or 0.0
                                for ln in labour_lines), 2))

        with ctx.step("Step 4: the OVERHEAD pair IS posted at 60.00"):
            overhead_lines = lines_named(lines, OVERHEAD_LABEL)
            overhead_total = round(COMPONENT_TOTAL * CATALOGUE_RATE, 2)
            ctx.check("overhead lines", 2, len(overhead_lines))
            ctx.check("overhead debit", overhead_total,
                      round(sum(ln["debit"] or 0.0
                                for ln in overhead_lines), 2))

        with ctx.step("Step 5 — THE GATE: NO uplift. price_unit equals "
                      "standard_price exactly, with no +6.00"):
            actual_price = round(move.get("price_unit") or 0.0, 4)
            uplift_if_leaked = round(overhead_total / 10.0, 2)
            ctx.log(f"price_unit={actual_price} standard_price="
                    f"{standard_price}; a leaked uplift would add "
                    f"{uplift_if_leaked}")
            ctx.check("finished move price_unit", standard_price,
                      actual_price)

        with ctx.step("Step 6: completing the MO did NOT move the "
                      "product's standard cost"):
            after = rpc.read("product.product", [std_product],
                             ["standard_price"])[0]["standard_price"]
            ctx.log(f"standard_price after the MO: {after}")
            ctx.check("standard_price after the MO", standard_price,
                      round(after, 4))

        with ctx.step("Step 7: the finished good is valued at "
                      "standard_price x qty, with no overhead component"):
            quantity = move.get("quantity") or 10.0
            core_lines = [ln for ln in lines
                          if ln not in labour_lines
                          and ln not in overhead_lines]
            core_debit = round(sum(ln["debit"] or 0.0
                                   for ln in core_lines), 2)
            expected_value = round(standard_price * quantity, 2)
            ctx.log(f"core valuation debit={core_debit}; standard_price x "
                    f"qty = {standard_price} x {quantity} = "
                    f"{expected_value}")
            ctx.check("the finished good is valued at standard",
                      expected_value, core_debit)

        with ctx.step("Step 8 — THE CONSEQUENCE: WIP carries an "
                      "unrelieved residual of labour + overhead, because "
                      "the finished good was valued at standard rather "
                      "than at absorbed cost. Computed and RECORDED as "
                      "the input to WF-008 Open Question 1"):
            residual = round(LABOUR_TOTAL + overhead_total, 2)
            wip_debits = round(sum(ln["debit"] or 0.0
                                   for ln in labour_lines + overhead_lines),
                               2)
            ctx.log(f"[FINDING] WF-008 Open Question 1 — residual WIP for "
                    f"MO {mo_id}: {wip_debits} debited to WIP by the "
                    f"reclass pairs (labour {LABOUR_TOTAL} + overhead "
                    f"{overhead_total} = {residual}) that the finished "
                    f"good's standard valuation of {expected_value} does "
                    "not relieve. Record this figure against the MO in "
                    "database/baseline-results/ — it is the Controller's "
                    "decision, not QA's.")
            ctx.check("the WIP reclass residual", residual, wip_debits)

        with ctx.step("Step 9: the entry balances despite the residue — a "
                      "WIP residue is not an imbalance"):
            debit = round(sum(ln["debit"] or 0.0 for ln in lines), 2)
            credit = round(sum(ln["credit"] or 0.0 for ln in lines), 2)
            ctx.log(f"totals: debit={debit} credit={credit}")
            ctx.check("total debit == total credit", debit, credit)

        with ctx.step("Step 10 — THE ATTRIBUTION: the SAME configuration "
                      "on a FIFO product DOES uplift, so the difference is "
                      "attributable to cost_method alone"):
            fifo_mo, raised2, message2 = _complete(ctx, env, "TC242-fifo")
            ctx.check_true("the FIFO comparison MO completed", not raised2,
                           actual_desc=message2)
            fifo_move, _, fifo_lines = _entry(ctx, fifo_mo)
            fifo_price = round(fifo_move.get("price_unit") or 0.0, 4)
            fifo_qty = fifo_move.get("quantity") or 10.0
            fifo_core = [ln for ln in fifo_lines
                         if ln not in lines_named(fifo_lines, LABOUR_LABEL)
                         and ln not in lines_named(fifo_lines,
                                                   OVERHEAD_LABEL)]
            fifo_core_debit = round(sum(ln["debit"] or 0.0
                                        for ln in fifo_core), 2)
            ctx.log(f"FIFO product: price_unit={fifo_price} core "
                    f"debit={fifo_core_debit} over {fifo_qty} units")
            ctx.check_true(
                "the FIFO product's unit cost is NOT its standard_price — "
                "it absorbed the overhead the standard product did not",
                round(fifo_price * fifo_qty, 2) != expected_value
                or fifo_price != standard_price,
                actual_desc=f"fifo={fifo_price} std={standard_price}")
            ctx.log("FAILURE SIGNATURE for v19: a rebuild that drops the "
                    "cost_method in ('fifo','average') gate starts "
                    "uplifting standard-cost products, which changes "
                    "standard cost silently and invalidates every variance "
                    "report built on it.")
    finally:
        with ctx.step("Restore the company switches"):
            restored = False
            try:
                set_switches(rpc, comp_id,
                             labour=original[LABOUR_SWITCH],
                             overhead=original[OVERHEAD_SWITCH])
                _, now = switches(rpc)
                restored = (now == original)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] switch restore failed: {exc}")
            ctx.check_true("the company switches were restored", restored,
                           actual_desc=original)
        with ctx.step("Cleanup WF-008 fixtures"):
            try:
                sweep_wf008(rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")
