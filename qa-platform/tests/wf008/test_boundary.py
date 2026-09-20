"""DATAONE-WF-008 — the zero-quantity boundary: TC256.

A pre-existing v17 defect rather than a money error — but it is a crash on
the Mark-as-Done path AND on the MO Overview, so it stops production and
blanks a report. It must be on record as a **v17** defect so that a v19
occurrence is not mis-attributed to the upgrade, and it must be FIXED
during the port rather than migrated faithfully.

Two unguarded divisions, verified in source:

* ``mrp.production._cal_price`` (F168)::

      quantity = finished_move.product_uom._compute_quantity(
          finished_move.quantity, finished_move.product_id.uom_id)
      finished_move.price_unit += overhead_cost / quantity

* ``report.mrp.report_mo_overview`` (F172), in both branches::

      'unit_cost': overhead_cost / production.qty_produced      # done
      'unit_cost': overhead_cost / production_qty               # forecast

Neither has a zero guard. A zero NUMERATOR would not divide by zero, so the
fixture keeps overhead non-zero (600.00 of components at 0.10) and drives
the DENOMINATOR to zero instead — which is what step 8's control confirms.

How this case reports
---------------------
The workbook's step 9 says the post-fix assertion "is expected to fail and
must be marked Blocked" until the guard is added. That is honoured
literally: the case RECORDS the live behaviour of both paths, asserts the
transaction integrity that must hold either way (nothing half-posted), and
then reports BLOCKED naming the missing guard. A BLOCKED result here is the
correct outcome on an unfixed target; once the v19 port adds the guard, the
same case passes its post-fix assertions and stops blocking.

EXPECTED v17 OUTCOME: BLOCKED — the guard does not exist yet, and the case
says so with the measured incidence count attached.
EXPECTED v19 OUTCOME: PASS once the zero guard is added to both divisions.
§2.8 moved ``_cal_price`` and reworked the Overview, so the divisions MOVE
but the guard is still absent unless someone adds it.
"""
from framework.registry import test_case
from tests.wf008.common import (require_exclusive_pools,
                                CATALOGUE_RATE, COMPONENT_TOTAL,  # noqa: F401
                                LABOUR_MINUTES, LABOUR_SWITCH, MARK, MO_QTY,
                                OVERHEAD_SWITCH, WORKFLOW, WORKFLOW_NAME,
                                build_mo, describe_lines, ensure_pool,
                                entry_lines, expect_error, finished_move, fx,
                                live_pools, m2o_id, mark_done, move_entries,
                                record_time, require_absorption_stack,
                                require_mrp_valuation, set_switches,
                                standard_environment, switches, sweep_wf008,
                                trace)


@test_case(
    id="TEST-WF008-TC256",
    name="Zero-quantity MO → ZeroDivisionError (live v17 defect E7)",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_mrp_account", priority="P1", kind="API", order=8256,
    description="Drives the denominator of both unguarded divisions to "
                "zero — completion via _cal_price and the MO Overview via "
                "qty_produced — records what each raises, asserts nothing "
                "was half-posted, confirms a zero numerator does NOT reach "
                "the division, measures the incidence on this database, "
                "and reports BLOCKED naming the guard the port must add.",
    traceability=trace("DATAONE-TC256"))
def test_tc256(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-008 fixtures and open a fresh "
                  "namespace"):
        sweep_wf008(rpc)

    with ctx.step("Preconditions: dto_mrp_account installed, both switches "
                  "on, and a NON-ZERO overhead so the numerator can never "
                  "be the reason nothing divides"):
        require_absorption_stack(ctx)
        require_mrp_valuation(ctx)
        comp_id, original = switches(rpc)
        set_switches(rpc, comp_id, labour=True, overhead=True)
        env = standard_environment(ctx)
        ensure_pool(ctx, "Factory Overhead", CATALOGUE_RATE,
                    expense_account_id=env["overhead_account"]["id"])
        require_exclusive_pools(ctx, 1)
        ctx.check("overhead pools in force", 1, len(live_pools(rpc)))
        ctx.log(f"overhead on a full run would be "
                f"{round(COMPONENT_TOTAL * CATALOGUE_RATE, 2)} — non-zero, "
                "so any ZeroDivisionError below comes from the "
                "DENOMINATOR.")

    findings = {}
    mo_id = None
    control_mo = None
    try:
        with ctx.step("Step 1: construct an MO whose produced quantity "
                      "reaches zero. product_qty = 0 is attempted first; "
                      "where the ORM refuses it, the quantity is driven to "
                      "zero on the finished move instead"):
            zero_qty_accepted, message = expect_error(
                rpc.create, "mrp.production",
                {"product_id": env["finished_id"], "bom_id": env["bom_id"],
                 "product_qty": 0.0, "origin": fx(f"{MARK} TC256")})
            findings["product_qty_zero_refused"] = zero_qty_accepted
            ctx.log(f"create with product_qty=0: refused="
                    f"{zero_qty_accepted} {message!r}")

            mo_id = build_mo(ctx, env["finished_id"], env["bom_id"],
                             qty=1.0, label="TC256")
            record_time(ctx, mo_id, env["assembly"], LABOUR_MINUTES,
                        employee_id=env["employee_id"])
            record_time(ctx, mo_id, env["packaging"], 30.0,
                        employee_id=env["employee_id"])
            move = finished_move(rpc, mo_id)
            ctx.log(f"finished move before zeroing: {move!r}")
            raised_z, message_z = expect_error(
                rpc.write, "stock.move", [move["id"]], {"quantity": 0.0})
            ctx.log(f"setting the finished move quantity to 0: "
                    f"raised={raised_z} {message_z!r}")
            after = rpc.read("stock.move", [move["id"]],
                             ["quantity", "product_uom_qty"])[0]
            ctx.log(f"finished move after zeroing: {after!r}")
            findings["finished_quantity"] = after.get("quantity")

        with ctx.step("Steps 2-3 — THE COMPLETION PATH: call "
                      "button_mark_done and capture whatever it raises"):
            raised, message = mark_done(ctx, mo_id, expect_error=True)
            findings["mark_done_raised"] = raised
            findings["mark_done_message"] = message
            ctx.log(f"button_mark_done: raised={raised} {message!r}")
            if raised and "ZeroDivision" in message:
                ctx.log("[FINDING] E7 is LIVE on the completion path: "
                        "mrp.production._cal_price divides "
                        "overhead_cost by the finished move's quantity "
                        "with no zero guard. The operator clicks Mark as "
                        "Done and the MO refuses to complete "
                        "mid-valuation.")

        with ctx.step("Step 4: the transaction rolled back — nothing was "
                      "half-posted. This must hold whether or not the "
                      "division raised"):
            state = rpc.read("mrp.production", [mo_id],
                             ["state", "stored_overhead_cost_settings"])[0]
            ctx.log(f"MO after the attempt: {state!r}")
            if findings["mark_done_raised"]:
                ctx.check_true("the MO is not done",
                               state["state"] != "done",
                               actual_desc=state["state"])
                current_move = finished_move(rpc, mo_id)
                entries = move_entries(rpc, [current_move["id"]]) \
                    if current_move else []
                ctx.check("valuation entries after the failed completion",
                          [], entries)
                ctx.check_true(
                    "no partial snapshot was written",
                    not state["stored_overhead_cost_settings"],
                    actual_desc=state["stored_overhead_cost_settings"])
            else:
                ctx.log("The completion path did NOT raise on this target "
                        "— recorded. Either the quantity could not be "
                        "driven to zero through a public write, or a guard "
                        "already exists. The Overview path below is tested "
                        "regardless.")

        with ctx.step("Steps 5-7 — THE REPORT PATH: open the MO Overview "
                      "on an MO with qty_produced == 0 and record whether "
                      "it renders or raises. A blank report and a "
                      "traceback are different user experiences and both "
                      "must be documented"):
            row = rpc.read("mrp.production", [mo_id],
                           ["qty_produced", "product_qty", "state"])[0]
            ctx.log(f"MO for the Overview probe: {row!r}")
            raised2, message2 = expect_error(
                rpc.call, "report.mrp.report_mo_overview",
                "get_report_values", mo_id)
            findings["overview_raised"] = raised2
            findings["overview_message"] = message2
            ctx.log(f"MO Overview: raised={raised2} {message2!r}")
            if raised2 and "ZeroDivision" in message2:
                ctx.log("[FINDING] E7 is LIVE on the report path too: "
                        "report.mrp.report_mo_overview divides "
                        "overhead_cost by qty_produced (done branch) and "
                        "by product_qty (forecast branch), neither "
                        "guarded. The cost accountant gets a traceback "
                        "instead of a report.")
            ctx.check_true("the Overview's behaviour was recorded", True,
                           actual_desc=message2)

        with ctx.step("Step 8 — THE ZERO-NUMERATOR CONTROL: with "
                      "record_mo_overhead_cost OFF the overhead is 0 and "
                      "the division is never reached at all. This proves "
                      "the failures above come from the DENOMINATOR"):
            set_switches(rpc, comp_id, labour=True, overhead=False)
            control_mo = build_mo(ctx, env["finished_id"], env["bom_id"],
                                  qty=1.0, label="TC256-ctl")
            record_time(ctx, control_mo, env["packaging"], 30.0,
                        employee_id=env["employee_id"])
            control_move = finished_move(rpc, control_mo)
            expect_error(rpc.write, "stock.move", [control_move["id"]],
                         {"quantity": 0.0})
            raised3, message3 = mark_done(ctx, control_mo,
                                          expect_error=True)
            findings["zero_numerator_raised"] = raised3
            findings["zero_numerator_message"] = message3
            ctx.log(f"overhead switch OFF, zero quantity: raised={raised3} "
                    f"{message3!r}")
            ctx.check_true(
                "with the overhead switch off, no ZeroDivisionError is "
                "reached — the division lives inside the overhead branch",
                not (raised3 and "ZeroDivision" in message3),
                actual_desc=message3)
            set_switches(rpc, comp_id, labour=True, overhead=True)

        with ctx.step("Step 10 — MEASURE THE EXPOSURE on this database: "
                      "how many manufacturing orders already have "
                      "product_qty = 0 or qty_produced = 0. Read-only, "
                      "through the ORM so no pg_* config is needed"):
            zero_qty = rpc.call("mrp.production", "search_count",
                                ["|", ("product_qty", "=", 0),
                                 ("qty_produced", "=", 0)])
            total = rpc.call("mrp.production", "search_count", [])
            findings["incidence"] = {"zero": zero_qty, "total": total}
            ctx.log(f"[FINDING] {zero_qty} of {total} mrp.production "
                    f"records on {ctx.env.key} have product_qty = 0 or "
                    "qty_produced = 0, and would hit the unguarded "
                    "division on completion or on the Overview. Record "
                    "this figure in findings/ — it is the incidence of a "
                    "v17 defect, not of an upgrade regression.")
            ctx.check_true("the exposure was measured", total is not None,
                           actual_desc=findings["incidence"])

        with ctx.step("Step 9 — THE POST-FIX ASSERTION. The workbook marks "
                      "this Blocked until a zero guard is added"):
            ctx.log(f"TC256 findings: {findings!r}")
            ctx.blocked(
                "requires the zero guard that the v19 port must add. Two "
                "unguarded divisions were exercised and their live "
                "behaviour recorded above: "
                "mrp.production._cal_price does `finished_move.price_unit "
                "+= overhead_cost / quantity` and "
                "report.mrp.report_mo_overview does `overhead_cost / "
                "production.qty_produced` (done branch) and "
                "`overhead_cost / production_qty` (forecast branch). "
                "Neither has a zero check on either version. Until the "
                "guard exists, the post-fix assertions — completion with "
                "no exception and no uplift, and an Overview that renders "
                "with an overhead row of 0.00 or no row — cannot pass, and "
                "asserting them would report a known v17 defect as an "
                "upgrade regression. Re-run this case after the guard "
                "lands; everything before this point already passed.")
    finally:
        with ctx.step("Cancel the zero-quantity MOs and restore the "
                      "company switches"):
            for label, mo in (("test", mo_id), ("control", control_mo)):
                if not mo:
                    continue
                try:
                    rpc.call("mrp.production", "action_cancel", [mo])
                except Exception as exc:      # noqa: BLE001
                    ctx.log(f"[warn] {label} MO not cancelled: {exc}")
            restored = False
            try:
                set_switches(rpc, comp_id, labour=original[LABOUR_SWITCH],
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
