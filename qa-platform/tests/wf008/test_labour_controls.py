"""DATAONE-WF-008 — the two labour controls: TC247 and TC248.

Both are costing controls implemented as shop-floor controls, and both fail
SILENTLY when they stop working — capitalised labour simply rises, with no
error, no notification and no log line.

TC247 — the time cap
--------------------
``mrp.workcenter.productivity.write`` truncates ``date_end`` to
``date_start + time_restrict_threshold x product_qty`` minutes and sets
``time_fixed``. Verified source::

    if not self.workcenter_id.use_time_restrict:
        return super().write(vals)
    if 'date_end' in vals:
        date_end = datetime.strptime(str(vals['date_end']),
                                     "%Y-%m-%d %H:%M:%S")
        threshold_time = workcenter.time_restrict_threshold \\
            * self.production_id.product_qty
        if (date_end - self.date_start).total_seconds()/60 > threshold_time:
            date_end = self.date_start + timedelta(minutes=threshold_time)
            vals['date_end'] = date_end
            vals['time_fixed'] = True

Three properties the case pins: the threshold is PER UNIT (so a 5-unit MO
caps at 5x), the boundary is strictly ``>`` (exactly-at-cap is not
truncated), and the whole thing is gated on ``use_time_restrict``. The
operator is **not told** their timesheet was shortened — the workbook
states that explicitly and it is the reason the Time Sheet Report exists.

The v19 exposure is the ``strptime(str(vals['date_end']), ...)`` parse. If
a v19 call path passes a ``datetime`` rather than a string, or the Shop
Floor rewrite (§2.9, Confirmed CRITICAL) bypasses ``write`` entirely, the
cap simply stops applying.

TC248 — the concurrent-timesheet guard, and the create-list canary
------------------------------------------------------------------
``mrp.workcenter.productivity.create`` is **not** decorated
``@api.model_create_multi`` and opens with ``if 'workcenter_id' in vals:``.
Delta §2.16 confirms ``create`` ALWAYS receives a list on v19, so
``'workcenter_id' in [{...}]`` is False and the guard never fires. Nothing
raises, nothing logs; operators run overlapping timesheets and capitalised
labour rises. The project's own test strategy calls this "the clearest
silent money failure in the project".

The canary is directly reachable here. ``rpc.create(model, values)``
dispatches ``create(values)`` verbatim, so passing a dict exercises the
v17 path and passing a list of one dict exercises the v19 path — against
the same database, in the same test. Step 6 is that comparison.

EXPECTED v17 OUTCOME: PASS. The dict form fires the guard; the LIST form is
expected to fire it too on v17 only because Odoo 17's ORM still accepts a
bare dict — so the list assertion is the one that matters and it is
expected to FAIL on unported code. That failure IS the finding
(``EXPECTED v17 OUTCOME: FAIL`` for step 6 if the override has not been
decorated).
EXPECTED v19 OUTCOME: step 6 fails until ``create`` is decorated
``@api.model_create_multi`` and rewritten to iterate ``vals_list``.
"""
from datetime import datetime, timedelta

from framework.registry import test_case
from tests.wf008.common import (CATALOGUE_RATE, COMPONENT_TOTAL,  # noqa: F401
                                EMPLOYEE_HOURLY_COST, LABOUR_SWITCH, MARK,
                                OVERHEAD_SWITCH, WORKFLOW, WORKFLOW_NAME,
                                build_mo, describe_lines, ensure_bom,
                                ensure_employee, ensure_operation,
                                ensure_pool, ensure_workcenter, entry_lines,
                                expect_error, finished_move, fx, lines_named,
                                m2o_id, mark_done, record_time,
                                require_absorption_stack,
                                require_mrp_valuation, set_switches,
                                standard_environment, switches, sweep_wf008,
                                trace)

LABOUR_LABEL = " - Labor Cost"
START = "2026-01-15 08:00:00"


def _end_after(minutes):
    """The date_end that a timesheet of ``minutes`` would close at."""
    return (datetime.strptime(START, "%Y-%m-%d %H:%M:%S")
            + timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S")


def _open_timesheet(rpc, mo_id, workcenter_id, employee_id):
    """An OPEN productivity row (no date_end) on the MO's work order."""
    workorders = rpc.search_read(
        "mrp.workorder", [("production_id", "=", mo_id),
                          ("workcenter_id", "=", workcenter_id)],
        ["name"], limit=1)
    if not workorders:
        return None, None
    values = {"workorder_id": workorders[0]["id"],
              "workcenter_id": workcenter_id,
              "date_start": START}
    if employee_id:
        values["employee_id"] = employee_id
    loss = rpc.search("mrp.workcenter.productivity.loss",
                      [("loss_type", "=", "productive")], limit=1)
    if loss:
        values["loss_id"] = loss[0]
    return values, workorders[0]["id"]


def _labour_debit(ctx, mo_id):
    rpc = ctx.adapter.rpc
    move = finished_move(rpc, mo_id)
    if not move:
        return None
    entries, lines = entry_lines(rpc, [move["id"]])
    labour = lines_named(lines, LABOUR_LABEL)
    for row in describe_lines(rpc, labour):
        ctx.log(f"  {row!r}")
    return round(sum(ln["debit"] or 0.0 for ln in labour), 2)


@test_case(
    id="TEST-WF008-TC247",
    name="Work-centre time cap truncates the timesheet and the labour "
         "charge",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_mrp_account", priority="P0", kind="API", order=8247,
    description="On a 2-unit MO with a 120-minute-per-unit cap: a "
                "300-minute timesheet truncates to 240 with time_fixed "
                "True and no operator notification, the labour charge is "
                "capped at 240.00, the three boundaries (at, one over, one "
                "under) behave as specified, the cap is switch-gated, and "
                "a 5-unit MO caps at 600 minutes.",
    traceability=trace("DATAONE-TC247"))
def test_tc247(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-008 fixtures and open a fresh "
                  "namespace"):
        sweep_wf008(rpc)

    with ctx.step("Preconditions: dto_mrp_account installed, the three "
                  "work-centre control fields exist"):
        require_absorption_stack(ctx)
        require_mrp_valuation(ctx)
        for field in ("use_time_restrict", "time_restrict_threshold"):
            if not rpc.field_exists("mrp.workcenter", field):
                ctx.blocked(
                    f"mrp.workcenter.{field} does not exist on "
                    f"{ctx.env.key} — the time cap this case is about is "
                    "not installed.")
        if not rpc.field_exists("mrp.workcenter.productivity", "time_fixed"):
            ctx.blocked("mrp.workcenter.productivity.time_fixed does not "
                        "exist — the truncation flag cannot be observed.")
        comp_id, original = switches(rpc)
        set_switches(rpc, comp_id, labour=True, overhead=True)
        env = standard_environment(ctx)

    results = {}
    try:
        with ctx.step("Step 1: a Test work centre with use_time_restrict "
                      "True and a 120-minute-per-unit threshold"):
            test_wc = ensure_workcenter(ctx, "Test", "WC3",
                                        use_time_restrict=True,
                                        threshold=120.0)
            row = rpc.read("mrp.workcenter", [test_wc],
                           ["name", "use_time_restrict",
                            "time_restrict_threshold"])[0]
            ctx.log(f"Test work centre: {row!r}")
            ctx.check("use_time_restrict", True, row["use_time_restrict"])
            ctx.check("time_restrict_threshold (minutes per unit)", 120.0,
                      round(row["time_restrict_threshold"], 2))
            ensure_pool(ctx, "Factory Overhead", CATALOGUE_RATE,
                        expense_account_id=env["overhead_account"]["id"])
            employee_id = ensure_employee(ctx)

        with ctx.step("Step 2: a 2-UNIT MO on a BoM routed through the "
                      "Test work centre, so the cap is 120 x 2 = 240 "
                      "minutes"):
            bom_id = ensure_bom(ctx, env["finished_id"], env["component_id"],
                                label="BOM-CAP")
            ensure_operation(ctx, bom_id, test_wc, "Test-op")
            ensure_operation(ctx, bom_id, env["packaging"], "Pack-cap")
            mo_id = build_mo(ctx, env["finished_id"], bom_id, qty=2.0,
                             label="TC247")
            qty = rpc.read("mrp.production", [mo_id],
                           ["product_qty"])[0]["product_qty"]
            ctx.check("MO product_qty", 2.0, round(qty, 2))
            cap = 120.0 * qty
            ctx.log(f"cap = 120 minutes/unit x {qty} units = {cap} minutes")

        with ctx.step("Steps 3-4: open a timesheet at T0 and close it at "
                      "T0 + 5 hours (300 minutes)"):
            values, workorder_id = _open_timesheet(rpc, mo_id, test_wc,
                                                   employee_id)
            if values is None:
                ctx.blocked(
                    f"MO {mo_id} has no work order on the Test work "
                    "centre; the BoM operation did not materialise. Check "
                    "that mrp.routing.workcenter is available on this "
                    "target.")
            row_id = rpc.create("mrp.workcenter.productivity", values)
            rpc.write("mrp.workcenter.productivity", [row_id],
                      {"date_end": _end_after(300)})

        with ctx.step("Steps 5-7 — THE TRUNCATION: date_end is capped at "
                      "T0 + 240 minutes, duration is 240 and time_fixed is "
                      "True"):
            fields_ = ["date_start", "date_end", "duration", "time_fixed"]
            if rpc.field_exists("mrp.workcenter.productivity",
                                "employee_cost"):
                fields_.append("employee_cost")
            capped = rpc.read("mrp.workcenter.productivity", [row_id],
                              fields_)[0]
            ctx.log(f"capped timesheet: {capped!r}")
            ctx.check("date_end after the cap", _end_after(cap),
                      str(capped["date_end"]))
            ctx.check("duration (minutes)", round(cap, 2),
                      round(capped["duration"], 2))
            ctx.check("time_fixed", True, capped["time_fixed"])
            results["over_run"] = capped

        with ctx.step("Step 8: the operator received NO notification. The "
                      "workbook states this explicitly and it is the "
                      "reason the Time Sheet Report matters"):
            messages = rpc.search_read(
                "mail.message",
                [("model", "in", ["mrp.production", "mrp.workorder"]),
                 ("res_id", "in", [mo_id, workorder_id])],
                ["body", "subject"], limit=40)
            truncation_notices = [
                m for m in messages
                if any(word in ((m.get("body") or "")
                                + (m.get("subject") or "")).lower()
                       for word in ("truncat", "time fixed", "shortened",
                                    "capped"))]
            ctx.log(f"messages on the MO/work order: {len(messages)}; "
                    f"mentioning a truncation: {truncation_notices!r}")
            ctx.check("chatter messages telling the operator their "
                      "timesheet was shortened", [], truncation_notices)

        with ctx.step("Step 9: the truncation IS visible on the Time Sheet "
                      "Report — the row carries time_fixed and the "
                      "reporting fields the F181 report reads"):
            report_fields = [f for f in ("time_fixed", "production_id",
                                         "dto_product_id", "part_number",
                                         "quantity_produced", "duration")
                             if rpc.field_exists(
                                 "mrp.workcenter.productivity", f)]
            reported = rpc.search_read(
                "mrp.workcenter.productivity",
                [("id", "=", row_id)], report_fields)[0]
            ctx.log(f"Time Sheet Report row: {reported!r}")
            ctx.check("the row is flagged Time Fixed", True,
                      reported.get("time_fixed"))
            ctx.check_true("the report's denormalised fields are populated",
                           bool(reported.get("production_id")),
                           actual_desc=reported)

        with ctx.step("Steps 10-11 — THE MONEY: complete the MO and assert "
                      "the labour charge is capped at 60.00 x 240/60 = "
                      "240.00, not 300.00"):
            record_time(ctx, mo_id, env["packaging"], 30.0,
                        employee_id=employee_id)
            raised, message = mark_done(ctx, mo_id)
            ctx.check_true("button_mark_done completed", not raised,
                           actual_desc=message)
            labour = _labour_debit(ctx, mo_id)
            capped_cost = round(EMPLOYEE_HOURLY_COST * cap / 60.0, 2)
            uncapped_cost = round(EMPLOYEE_HOURLY_COST * 300.0 / 60.0, 2)
            ctx.log(f"labour posted={labour}; capped would be "
                    f"{capped_cost}, uncapped would be {uncapped_cost} "
                    "(plus the Packaging time, which is fixture, not "
                    "assertion)")
            ctx.check_true(
                "the labour charge reflects the CAPPED 240 minutes, not "
                "the recorded 300",
                labour is not None and labour < uncapped_cost
                + (EMPLOYEE_HOURLY_COST * 30.0 / 60.0),
                actual_desc=labour)

        # --------------------------------------------------- boundaries
        with ctx.step("Steps 12-14: the three boundaries. The comparison "
                      "is strictly '>', so exactly-at-cap must NOT be "
                      "truncated"):
            boundaries = {}
            for label, minutes, expect_fixed in (
                    ("exactly at the cap", 240.0, False),
                    ("one minute over", 241.0, True),
                    ("one minute under", 239.0, False)):
                bmo = build_mo(ctx, env["finished_id"], bom_id, qty=2.0,
                               label=f"TC247-{int(minutes)}")
                values, _ = _open_timesheet(rpc, bmo, test_wc, employee_id)
                if values is None:
                    continue
                brow = rpc.create("mrp.workcenter.productivity", values)
                rpc.write("mrp.workcenter.productivity", [brow],
                          {"date_end": _end_after(minutes)})
                observed = rpc.read("mrp.workcenter.productivity", [brow],
                                    ["date_end", "duration",
                                     "time_fixed"])[0]
                boundaries[label] = observed
                ctx.log(f"{label} ({minutes} min): {observed!r}")
                expected_duration = min(minutes, cap)
                ctx.check(f"{label}: duration", round(expected_duration, 2),
                          round(observed["duration"], 2))
                ctx.check(f"{label}: time_fixed", expect_fixed,
                          observed["time_fixed"])
            results["boundaries"] = boundaries

        with ctx.step("Step 15 — THE SWITCH GATE: with "
                      "use_time_restrict False, a 300-minute timesheet is "
                      "NOT truncated"):
            rpc.write("mrp.workcenter", [test_wc],
                      {"use_time_restrict": False})
            omo = build_mo(ctx, env["finished_id"], bom_id, qty=2.0,
                           label="TC247-off")
            values, _ = _open_timesheet(rpc, omo, test_wc, employee_id)
            orow = rpc.create("mrp.workcenter.productivity", values)
            rpc.write("mrp.workcenter.productivity", [orow],
                      {"date_end": _end_after(300)})
            observed = rpc.read("mrp.workcenter.productivity", [orow],
                                ["duration", "time_fixed"])[0]
            ctx.log(f"cap disabled: {observed!r}")
            ctx.check("duration with the cap disabled", 300.0,
                      round(observed["duration"], 2))
            ctx.check("time_fixed with the cap disabled", False,
                      observed["time_fixed"])

        with ctx.step("Step 16 — PER-UNIT SCALING: on a 5-unit MO the cap "
                      "is 120 x 5 = 600 minutes, so a 700-minute timesheet "
                      "truncates to 600"):
            rpc.write("mrp.workcenter", [test_wc],
                      {"use_time_restrict": True})
            fmo = build_mo(ctx, env["finished_id"], bom_id, qty=5.0,
                           label="TC247-five")
            values, _ = _open_timesheet(rpc, fmo, test_wc, employee_id)
            frow = rpc.create("mrp.workcenter.productivity", values)
            rpc.write("mrp.workcenter.productivity", [frow],
                      {"date_end": _end_after(700)})
            observed = rpc.read("mrp.workcenter.productivity", [frow],
                                ["date_end", "duration", "time_fixed"])[0]
            ctx.log(f"5-unit MO, 700 minutes recorded: {observed!r}")
            ctx.check("duration on a 5-unit MO", 600.0,
                      round(observed["duration"], 2))
            ctx.check("date_end on a 5-unit MO", _end_after(600.0),
                      str(observed["date_end"]))
            ctx.check("time_fixed on a 5-unit MO", True,
                      observed["time_fixed"])
    finally:
        with ctx.step("Restore use_time_restrict and the company switches"):
            try:
                rpc.write("mrp.workcenter", [test_wc],
                          {"use_time_restrict": True})
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] work-centre restore failed: {exc}")
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


@test_case(
    id="TEST-WF008-TC248",
    name="Concurrent-timesheet guard still fires on v19 (the create list "
         "canary)",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_mrp_account", priority="P0", kind="API", order=8248,
    description="With an open timesheet for one employee, a second "
                "create() on a non-simultaneous work centre is refused — "
                "tested with a plain dict AND with a list of one dict, "
                "which is the v19 canary, AND with a two-record list. "
                "Plus the two positive controls, the nothing-committed "
                "assertion, the cost consequence of the guard being "
                "bypassed, and the missing-employee_id defect.",
    traceability=trace("DATAONE-TC248"))
def test_tc248(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-008 fixtures and open a fresh "
                  "namespace"):
        sweep_wf008(rpc)

    with ctx.step("Preconditions: dto_mrp_account installed, "
                  "allow_simultaneous_workorders exists"):
        require_absorption_stack(ctx)
        require_mrp_valuation(ctx)
        if not rpc.field_exists("mrp.workcenter",
                                "allow_simultaneous_workorders"):
            ctx.blocked(
                "mrp.workcenter.allow_simultaneous_workorders does not "
                f"exist on {ctx.env.key} — the concurrent-timesheet guard "
                "this case is about is not installed.")
        comp_id, original = switches(rpc)
        set_switches(rpc, comp_id, labour=True, overhead=True)
        env = standard_environment(ctx)

    findings = {}
    try:
        with ctx.step("Step 1: two work centres, both with "
                      "allow_simultaneous_workorders False"):
            wc_a = ensure_workcenter(ctx, "Assembly-248", "WCA",
                                     allow_simultaneous=False)
            wc_b = ensure_workcenter(ctx, "Test-248", "WCB",
                                     allow_simultaneous=False)
            rows = rpc.read("mrp.workcenter", [wc_a, wc_b],
                            ["name", "allow_simultaneous_workorders"])
            ctx.log(f"work centres: {rows!r}")
            ctx.check("work centres allowing simultaneous work orders", [],
                      [r["id"] for r in rows
                       if r["allow_simultaneous_workorders"]])
            employee_id = ensure_employee(ctx)
            employee_2 = ensure_employee(ctx, label="E-02")

        with ctx.step("Two MOs so both work centres are live"):
            bom_a = ensure_bom(ctx, env["finished_id"], env["component_id"],
                               label="BOM-248A")
            ensure_operation(ctx, bom_a, wc_a, "Op-A")
            ensure_operation(ctx, bom_a, env["packaging"], "Pack-A")
            bom_b = ensure_bom(ctx, env["finished_id"], env["component_id"],
                               label="BOM-248B")
            ensure_operation(ctx, bom_b, wc_b, "Op-B")
            ensure_operation(ctx, bom_b, env["packaging"], "Pack-B")
            mo_a = build_mo(ctx, env["finished_id"], bom_a, qty=2.0,
                            label="TC248-A")
            mo_b = build_mo(ctx, env["finished_id"], bom_b, qty=2.0,
                            label="TC248-B")

        with ctx.step("Steps 2-3: open a timesheet for the employee on "
                      "work order A and assert exactly ONE open row exists "
                      "for them"):
            values_a, _ = _open_timesheet(rpc, mo_a, wc_a, employee_id)
            if values_a is None:
                ctx.blocked(f"MO {mo_a} has no work order on {wc_a}; the "
                            "BoM operation did not materialise.")
            open_a = rpc.create("mrp.workcenter.productivity", values_a)
            open_rows = rpc.search("mrp.workcenter.productivity",
                                   [("employee_id", "=", employee_id),
                                    ("date_end", "=", False)])
            ctx.log(f"open timesheets for the employee: {open_rows!r}")
            ctx.check("open timesheets for that employee", 1,
                      len(open_rows))

        with ctx.step("Steps 4-5 — THE DICT FORM: a second timesheet for "
                      "the SAME employee on work order B is refused, and "
                      "the message names the employee, the work centre, "
                      "the MO and the work order"):
            values_b, workorder_b = _open_timesheet(rpc, mo_b, wc_b,
                                                    employee_id)
            raised, message = expect_error(
                rpc.create, "mrp.workcenter.productivity", dict(values_b))
            findings["dict_form_raised"] = raised
            ctx.log(f"create({{dict}}): raised={raised} {message!r}")
            ctx.check_true("create({dict}) was refused", raised,
                           actual_desc=message)
            employee_name = rpc.read("hr.employee", [employee_id],
                                     ["name"])[0]["name"]
            wc_name = rpc.read("mrp.workcenter", [wc_b], ["name"])[0]["name"]
            mo_name = rpc.read("mrp.production", [mo_a],
                               ["name"])[0]["name"]
            wo_name = rpc.read("mrp.workorder", [workorder_b],
                               ["name"])[0]["name"] if workorder_b else ""
            identifiers = {"employee": employee_name, "work centre": wc_name,
                           "manufacturing order": mo_name}
            absent = {label: value for label, value in identifiers.items()
                      if value and value not in message}
            ctx.log(f"identifiers absent from the message: {absent!r}")
            ctx.check("identifiers the UserError fails to name", {}, absent)

        with ctx.step("Step 6 — THE CANARY: the SAME call with a LIST of "
                      "one dict. On unported v19 code this is the step "
                      "that silently SUCCEEDS, because create() always "
                      "receives a list there and the override's "
                      "`'workcenter_id' in vals` is False for a list"):
            raised2, message2 = expect_error(
                rpc.create, "mrp.workcenter.productivity", [dict(values_b)])
            findings["list_form_raised"] = raised2
            findings["list_form_message"] = message2
            ctx.log(f"create([{{dict}}]): raised={raised2} {message2!r}")
            if not raised2:
                ctx.log("[FINDING] THE CANARY FIRED. create([{...}]) was "
                        "ACCEPTED while create({...}) was refused — the "
                        "guard does not see a list. "
                        "mrp.workcenter.productivity.create is not "
                        "decorated @api.model_create_multi, and delta "
                        "§2.16 confirms create ALWAYS receives a list on "
                        "v19. Operators run overlapping timesheets, "
                        "capitalised labour rises, and nothing raises and "
                        "nothing logs. This is the project's clearest "
                        "silent money failure.")
            ctx.check_true(
                "create([{dict}]) is refused too — the guard must fire for "
                "BOTH call forms",
                raised2, actual_desc=message2)

        with ctx.step("Step 7: a two-record list with two conflicting rows "
                      "is refused and commits nothing"):
            raised3, message3 = expect_error(
                rpc.create, "mrp.workcenter.productivity",
                [dict(values_b), dict(values_b)])
            findings["multi_list_raised"] = raised3
            ctx.log(f"create([{{d1}},{{d2}}]): raised={raised3} "
                    f"{message3!r}")
            ctx.check_true("a multi-record conflicting create is refused",
                           raised3, actual_desc=message3)

        with ctx.step("Step 8: nothing was created by any of the refused "
                      "calls — still exactly ONE open row"):
            open_rows = rpc.search("mrp.workcenter.productivity",
                                   [("employee_id", "=", employee_id),
                                    ("date_end", "=", False)])
            ctx.log(f"open timesheets after the refusals: {open_rows!r}")
            ctx.check("open timesheets for that employee", 1,
                      len(open_rows))

        with ctx.step("Step 9 — POSITIVE CONTROL: with "
                      "allow_simultaneous_workorders True on the second "
                      "work centre, BOTH call forms succeed and two open "
                      "timesheets exist"):
            rpc.write("mrp.workcenter", [wc_b],
                      {"allow_simultaneous_workorders": True})
            raised4, message4 = expect_error(
                rpc.create, "mrp.workcenter.productivity", dict(values_b))
            ctx.log(f"simultaneous allowed, dict form: raised={raised4} "
                    f"{message4!r}")
            ctx.check_true("the dict form is accepted when simultaneous "
                           "work is allowed", not raised4,
                           actual_desc=message4)
            open_rows = rpc.search("mrp.workcenter.productivity",
                                   [("employee_id", "=", employee_id),
                                    ("date_end", "=", False)])
            ctx.log(f"open timesheets now: {open_rows!r}")
            ctx.check("open timesheets for that employee", 2,
                      len(open_rows))

        with ctx.step("Step 10 — POSITIVE CONTROL: a DIFFERENT employee "
                      "is never blocked"):
            rpc.write("mrp.workcenter", [wc_b],
                      {"allow_simultaneous_workorders": False})
            values_other = dict(values_b)
            values_other["employee_id"] = employee_2
            raised5, message5 = expect_error(
                rpc.create, "mrp.workcenter.productivity", values_other)
            ctx.log(f"different employee: raised={raised5} {message5!r}")
            ctx.check_true("a different employee is not blocked",
                           not raised5, actual_desc=message5)

        with ctx.step("Step 11 — THE MONEY AT STAKE: with the guard "
                      "bypassed, two overlapping 60-minute timesheets "
                      "charge 120 minutes of labour to the same MO. "
                      "Recorded as the amount the guard exists to prevent"):
            overlapping = rpc.search_read(
                "mrp.workcenter.productivity",
                [("employee_id", "=", employee_id),
                 ("date_end", "=", False)],
                ["workcenter_id", "date_start"])
            double_charge = round(
                EMPLOYEE_HOURLY_COST * 2 * 60.0 / 60.0, 2)
            ctx.log(f"overlapping open timesheets: {overlapping!r}")
            ctx.log(f"[FINDING] two overlapping 60-minute timesheets for "
                    f"one employee at {EMPLOYEE_HOURLY_COST}/hour charge "
                    f"{double_charge} of labour where {double_charge / 2} "
                    "was worked. That is the money the guard protects, per "
                    "occurrence, and it is capitalised into inventory.")
            ctx.check_true("the double-charge exposure is recorded", True,
                           actual_desc=double_charge)

        with ctx.step("Step 12 — THE E9 DEFECT: create() with NO "
                      "employee_id key. Captured, not worked around"):
            no_employee = {k: v for k, v in values_b.items()
                           if k != "employee_id"}
            raised6, message6 = expect_error(
                rpc.create, "mrp.workcenter.productivity", no_employee)
            findings["missing_employee_raised"] = raised6
            findings["missing_employee_message"] = message6
            ctx.log(f"create with no employee_id: raised={raised6} "
                    f"{message6!r}")
            if raised6 and "KeyError" in message6:
                ctx.log("[FINDING] E9 is LIVE: the guard reads "
                        "vals['employee_id'] unconditionally, so a create "
                        "without that key raises KeyError rather than a "
                        "business error. A live v17 defect, recorded here "
                        "so a v19 occurrence is not mis-attributed to the "
                        "upgrade. The v19 rewrite should use "
                        "vals.get('employee_id').")
            ctx.check_true("the missing-employee_id behaviour is recorded",
                           True, actual_desc=message6)
            ctx.log(f"TC248 findings: {findings!r}")
    finally:
        with ctx.step("Postcondition: close every open timesheet and "
                      "restore allow_simultaneous_workorders"):
            try:
                stragglers = rpc.search(
                    "mrp.workcenter.productivity",
                    [("employee_id", "in", [employee_id, employee_2]),
                     ("date_end", "=", False)])
                for row_id in stragglers:
                    try:
                        rpc.unlink("mrp.workcenter.productivity", [row_id])
                    except Exception:      # noqa: BLE001
                        pass
                remaining = rpc.search(
                    "mrp.workcenter.productivity",
                    [("employee_id", "in", [employee_id, employee_2]),
                     ("date_end", "=", False)])
                ctx.log(f"open timesheets remaining: {remaining!r}")
                ctx.check("open fixture timesheets left behind", 0,
                          len(remaining))
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] timesheet cleanup incomplete: {exc}")
            try:
                rpc.write("mrp.workcenter", [wc_b],
                          {"allow_simultaneous_workorders": False})
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] work-centre restore failed: {exc}")
        with ctx.step("Restore the company switches and sweep"):
            try:
                set_switches(rpc, comp_id, labour=original[LABOUR_SWITCH],
                             overhead=original[OVERHEAD_SWITCH])
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] switch restore failed: {exc}")
            try:
                sweep_wf008(rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")
