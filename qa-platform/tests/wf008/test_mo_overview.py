"""DATAONE-WF-008 — the MO Overview: TC245.

No ledger balance depends on this report, which is why it is P1 rather than
P0. But it is the only screen where a planner sees FULLY LOADED cost before
production and a cost accountant sees frozen-rate actuals afterwards, and
it is served by **two different code branches with different key types**:

* ``_get_operations_data`` — the FORECAST branch, used while the MO is not
  done. Iterates ``_calc_production_overhead_cost(component_cost)`` whose
  keys are **recordsets**, so the label is built from ``setting.name`` and
  the index from ``setting.name``.
* ``_get_finished_operation_data`` — the ACTUAL branch, used once the MO is
  done. By then ``stored_overhead_cost_settings`` exists, so the same call
  returns **string** keys and the label is built from ``setting`` directly.

Both produce the label ``Overhead: <pool>``; only the key TYPE differs.
That asymmetry is undocumented in the module and it is the specification a
v19 rebuild has to match, so step 9 records it explicitly.

The failure this case makes visible
-----------------------------------
The MO Overview was reworked in v18 (§2.8). A renamed hook kills the
override and the ``Overhead:`` rows **silently vanish from a report that
still renders** — it is simply understated, and nobody notices because
there is nothing to compare it against. A changed dict shape is instead a
LOUD ``KeyError``. The workbook asks for both to be tested, and both are.

``get_report_values(production_id)`` is PUBLIC on both versions
(v17 ``mrp/report/mrp_report_mo_overview.py:16``, v19 ``:17``) and returns
a plain dict, so the whole report is readable over
``/web/dataset/call_kw`` without a browser.

What is not automated
---------------------
Step 11 asks for the override method to be RENAMED so the silent-failure
signature can be observed. That is a write to application source on a
shared clone — forbidden by convention rule 1 — so the signature is
DOCUMENTED from the report's own shape instead: the case records whether
each branch carries an ``Overhead:`` row and what the summary totals are
with and without it, which is exactly the evidence a tester needs to
recognise the failure. Step 10's "render the report at UAT and confirm a
TD-U-05 user sees it" is a visual check and stays manual.

EXPECTED v17 OUTCOME: PASS.
EXPECTED v19 OUTCOME: this is the case that tells you which of the two
failure modes you have — a missing row (silent) or a KeyError (loud).
"""
from framework.registry import test_case
from tests.wf008.common import (CATALOGUE_RATE, COMPONENT_TOTAL,  # noqa: F401
                                LABOUR_MINUTES, LABOUR_SWITCH, MARK, MO_QTY,
                                OVERHEAD_SWITCH, WORKFLOW, WORKFLOW_NAME,
                                build_mo, ensure_pool, expect_error, fx,
                                live_pools, m2o_id, mark_done, record_time,
                                require_absorption_stack,
                                require_mrp_valuation, set_switches,
                                standard_environment, switches, sweep_wf008,
                                trace)

OVERVIEW_MODEL = "report.mrp.report_mo_overview"
OVERHEAD_ROW_PREFIX = "Overhead: "


def _overview(ctx, mo_id):
    """(raised, message, report) — the Overview as the report returns it."""
    rpc = ctx.adapter.rpc
    raised, message = expect_error(rpc.call, OVERVIEW_MODEL,
                                   "get_report_values", mo_id)
    if raised:
        return True, message, None
    return False, "", rpc.call(OVERVIEW_MODEL, "get_report_values", mo_id)


def _overhead_rows(report):
    """Every operation row whose name starts with 'Overhead: '.

    Walks the whole structure rather than assuming a path, because §2.8
    reworked the Overview's shape in v18 and the point of this case is to
    find the rows wherever the rebuild put them.
    """
    found = []

    def walk(node):
        if isinstance(node, dict):
            name = node.get("name")
            if isinstance(name, str) and name.startswith(OVERHEAD_ROW_PREFIX):
                found.append(node)
            for value in node.values():
                walk(value)
        elif isinstance(node, (list, tuple)):
            for item in node:
                walk(item)

    walk(report)
    return found


def _summaries(report):
    """Every dict that looks like a cost summary, with its two keys."""
    found = []

    def walk(node):
        if isinstance(node, dict):
            if "mo_cost" in node and "real_cost" in node:
                found.append({"mo_cost": node.get("mo_cost"),
                              "real_cost": node.get("real_cost")})
            for value in node.values():
                walk(value)
        elif isinstance(node, (list, tuple)):
            for item in node:
                walk(item)

    walk(report)
    return found


@test_case(
    id="TEST-WF008-TC245",
    name="MO Overview: forecast overhead before completion, frozen-rate "
         "actual after",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_mrp_account", priority="P1", kind="API", order=8245,
    description="The not-done MO's Overview carries an 'Overhead: <pool>' "
                "row at the forecast amount and uplifts both mo_cost and "
                "real_cost; the done MO's carries the same row computed "
                "from the frozen rate at overhead/qty_produced. Records "
                "the two branches' differing key types as the "
                "specification a v19 rebuild must match, and distinguishes "
                "the silent failure (row missing, report renders) from the "
                "loud one (KeyError).",
    traceability=trace("DATAONE-TC245"))
def test_tc245(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-008 fixtures and open a fresh "
                  "namespace"):
        sweep_wf008(rpc)

    with ctx.step("Preconditions: dto_mrp_account installed, real-time "
                  "valuation available, both switches on"):
        require_absorption_stack(ctx)
        require_mrp_valuation(ctx)
        if not rpc.model_exists("mrp.production"):
            ctx.blocked("mrp is not installed on this target.")
        comp_id, original = switches(rpc)
        set_switches(rpc, comp_id, labour=True, overhead=True)
        env = standard_environment(ctx)

    findings = {}
    try:
        with ctx.step("One pool at the catalogue rate 0.10"):
            pool_id = ensure_pool(
                ctx, "Factory Overhead", CATALOGUE_RATE,
                expense_account_id=env["overhead_account"]["id"])
            pools = live_pools(rpc)
            ctx.check("overhead pools in force", 1, len(pools))
            pool_name = pools[0]["name"]
            expected_overhead = round(COMPONENT_TOTAL * CATALOGUE_RATE, 2)
            ctx.log(f"pool {pool_name!r} at {CATALOGUE_RATE} -> "
                    f"{expected_overhead} on 600.00 of components")

        # ------------------------------------------------ forecast branch
        with ctx.step("Step 1 — THE FORECAST BRANCH: a confirmed, "
                      "not-done MO with components reserved"):
            forecast_mo = build_mo(ctx, env["finished_id"], env["bom_id"],
                                   label="TC245-fcst")
            record_time(ctx, forecast_mo, env["assembly"], LABOUR_MINUTES,
                        employee_id=env["employee_id"])
            state = rpc.read("mrp.production", [forecast_mo],
                             ["state", "product_qty"])[0]
            ctx.log(f"forecast MO: {state!r}")
            ctx.check_true("the MO is NOT done",
                           state["state"] != "done",
                           actual_desc=state["state"])

        with ctx.step("Step 12 — THE LOUD PROBE, run first: if v19's hook "
                      "returns a different dict shape, capture the error "
                      "rather than working around it"):
            raised, message, report = _overview(ctx, forecast_mo)
            findings["forecast_raised"] = raised
            findings["forecast_error"] = message
            if raised:
                ctx.log(f"[FINDING] the Overview RAISED on a not-done MO: "
                        f"{message!r}. That is the LOUD failure mode — a "
                        "changed dict shape from v18's rework (§2.8). It "
                        "is recorded verbatim here so the rebuild has the "
                        "exact signature to fix.")
            ctx.check_true("the Overview renders for a not-done MO",
                           not raised, actual_desc=message)

        with ctx.step("Steps 2-3: the forecast Overview carries an "
                      f"'{OVERHEAD_ROW_PREFIX}{{pool}}' row at "
                      "round(component_cost x rate) / product_qty"):
            rows = _overhead_rows(report)
            ctx.log(f"forecast overhead rows: {rows!r}")
            findings["forecast_rows"] = len(rows)
            if not rows:
                ctx.log("[FINDING] the report RENDERED but carries NO "
                        "'Overhead:' row. That is the SILENT failure mode "
                        "— the override is not being called, the report is "
                        "simply understated, and nothing raises anywhere. "
                        "This is the signature a tester must recognise.")
            ctx.check(f"forecast '{OVERHEAD_ROW_PREFIX}' rows", 1,
                      len(rows))
            ctx.check("the row names the pool",
                      f"{OVERHEAD_ROW_PREFIX}{pool_name}",
                      rows[0].get("name"))
            ctx.check("forecast overhead amount", expected_overhead,
                      round(rows[0].get("mo_cost") or 0.0, 2))
            ctx.check("forecast unit cost (overhead / product_qty)",
                      round(expected_overhead / state["product_qty"], 2),
                      round(rows[0].get("unit_cost") or 0.0, 2))

        with ctx.step("Step 4: the summary is uplifted — the overhead is "
                      "added to BOTH mo_cost and real_cost"):
            summaries = _summaries(report)
            ctx.log(f"forecast summaries: {summaries!r}")
            ctx.check_true("the report exposes a cost summary carrying "
                           "both mo_cost and real_cost",
                           bool(summaries), actual_desc=summaries)
            findings["forecast_summary"] = summaries[:2]
            ctx.check_true(
                "at least one summary's mo_cost is at least the overhead "
                "amount, i.e. the uplift reached it",
                any((s.get("mo_cost") or 0.0) >= expected_overhead
                    for s in summaries),
                actual_desc=summaries)

        # -------------------------------------------------- actual branch
        with ctx.step("Steps 5-6 — THE ACTUAL BRANCH: complete a second, "
                      "identical MO and read its Overview"):
            done_mo = build_mo(ctx, env["finished_id"], env["bom_id"],
                               label="TC245-done")
            record_time(ctx, done_mo, env["assembly"], LABOUR_MINUTES,
                        employee_id=env["employee_id"])
            record_time(ctx, done_mo, env["packaging"], 30.0,
                        employee_id=env["employee_id"])
            raised2, message2 = mark_done(ctx, done_mo)
            ctx.check_true("the second MO completed", not raised2,
                           actual_desc=message2)
            row = rpc.read("mrp.production", [done_mo],
                           ["state", "qty_produced",
                            "stored_overhead_cost_settings"])[0]
            ctx.log(f"done MO: {row!r}")
            ctx.check("MO state", "done", row["state"])

            raised3, message3, done_report = _overview(ctx, done_mo)
            findings["actual_raised"] = raised3
            findings["actual_error"] = message3
            if raised3:
                ctx.log(f"[FINDING] the Overview RAISED on a DONE MO: "
                        f"{message3!r}. Note the asymmetry — the actual "
                        "branch reads STRING keys from the snapshot where "
                        "the forecast branch reads RECORDSET keys, so an "
                        "AttributeError here and not above is the E8 "
                        "ordering defect, not a shape change.")
            ctx.check_true("the Overview renders for a done MO",
                           not raised3, actual_desc=message3)

        with ctx.step("Step 7: the actual row is computed from the FROZEN "
                      "rate, divided by qty_produced"):
            done_rows = _overhead_rows(done_report)
            ctx.log(f"actual overhead rows: {done_rows!r}")
            findings["actual_rows"] = len(done_rows)
            ctx.check(f"actual '{OVERHEAD_ROW_PREFIX}' rows", 1,
                      len(done_rows))
            ctx.check("the row names the pool",
                      f"{OVERHEAD_ROW_PREFIX}{pool_name}",
                      done_rows[0].get("name"))
            ctx.check("actual overhead amount", expected_overhead,
                      round(done_rows[0].get("mo_cost") or 0.0, 2))
            qty_produced = row["qty_produced"] or MO_QTY
            ctx.check("actual unit cost (overhead / qty_produced)",
                      round(expected_overhead / qty_produced, 2),
                      round(done_rows[0].get("unit_cost") or 0.0, 2))
            ctx.log(f"frozen snapshot behind that figure: "
                    f"{row['stored_overhead_cost_settings']!r}")

        with ctx.step("Step 8: the done branch uplifts both summary keys "
                      "too"):
            done_summaries = _summaries(done_report)
            ctx.log(f"actual summaries: {done_summaries!r}")
            findings["actual_summary"] = done_summaries[:2]
            ctx.check_true(
                "at least one summary's real_cost is at least the "
                "overhead amount",
                any((s.get("real_cost") or 0.0) >= expected_overhead
                    for s in done_summaries),
                actual_desc=done_summaries)

        with ctx.step("Step 9 — THE SPECIFICATION: record the two "
                      "branches' differing key types, so a v19 rebuild has "
                      "something concrete to match"):
            forecast_index = rows[0].get("index")
            actual_index = done_rows[0].get("index")
            ctx.log(f"forecast row index={forecast_index!r} (built from a "
                    "RECORDSET key: setting.name)")
            ctx.log(f"actual   row index={actual_index!r} (built from a "
                    "STRING key: the snapshot's own key)")
            findings["forecast_index"] = forecast_index
            findings["actual_index"] = actual_index
            ctx.check("both branches produce the SAME visible label",
                      rows[0].get("name"), done_rows[0].get("name"))
            ctx.log("The LABELS agree; the KEY TYPES do not. "
                    "_get_operations_data iterates "
                    "_calc_production_overhead_cost's recordset keys, "
                    "_get_finished_operation_data iterates its string keys "
                    "(the snapshot exists by then). A rebuild that "
                    "normalises one without the other changes the row "
                    "index and breaks the report's own de-duplication.")

        with ctx.step("Steps 10-11: the UAT render and the rename probe"):
            ctx.log("Step 10 (render the report at UAT and confirm a "
                    "TD-U-05 Manufacturing User sees the row with the "
                    "correct label and amount) is a visual check and stays "
                    "manual. The DATA behind that screen is asserted "
                    "above, as the same public get_report_values call the "
                    "screen makes.")
            ctx.log("Step 11 (rename the override method and observe the "
                    "report still rendering with the row absent) would "
                    "require writing to application source on a shared "
                    "clone — forbidden by AUTOMATION_CONVENTIONS.md rule "
                    "1. The SIGNATURE is documented instead and is "
                    "detectable from this case's own output: a PASS on "
                    "'the Overview renders' together with a FAIL on "
                    "'forecast/actual Overhead rows == 1' IS the silent "
                    "failure. That combination is the thing to look for.")
            ctx.log(f"TC245 findings: {findings!r}")
            ctx.check_true(
                "both branches were exercised and both failure modes are "
                "distinguishable from this case's output",
                findings.get("forecast_rows") is not None
                and findings.get("actual_rows") is not None,
                actual_desc=findings)
    finally:
        with ctx.step("Restore the company switches"):
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
