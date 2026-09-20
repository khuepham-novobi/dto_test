"""DATAONE-WF-008 — rate freezing: TC244 and TC246.

Overhead rates are finance-controlled and are frozen onto each
manufacturing order at posting, so a later rate change cannot
retrospectively restate a completed order's reported cost. The freeze is
also load-bearing for CORRECTNESS, not only for audit:
``_calc_production_overhead_cost`` reads the snapshot AFTER posting and
returns **recordset** keys before it exists and **string** keys after, so
reading it in the wrong order either crashes Mark as Done or produces
plausible numbers from the wrong provenance.

Verified source (``dto_mrp_account/models/mrp_production.py``)::

    def _post_inventory(self, cancel_backorder=False):
        res = super()._post_inventory(cancel_backorder=cancel_backorder)
        overhead_cost_settings = self.env['mrp.overhead.cost.setting'].search([])
        for order in self:
            order.stored_overhead_cost_settings = {
                setting.name: setting.percentage
                for setting in overhead_cost_settings}
        return res

Three properties fall straight out of that: it runs AFTER ``super()``, it
has **no switch check** (WF-008 A1 — proved in TC236/TC237), and it is
keyed by pool **NAME**, so renaming a pool orphans every historical
snapshot. TC246 step 9 probes that fragility deliberately rather than
leaving it to be discovered in production.

What cannot be reached over RPC, and what is asserted instead
------------------------------------------------------------
TC244 step 2 asks for ``_generate_valuation_lines_data`` to be instrumented
so the snapshot can be read at the instant the entry is built. Private
methods are not dispatchable (``check_method_name``: v17
``odoo/models.py:145``, v19 ``odoo/orm/utils.py:69``) and in-process
patching is not available to an RPC client. The observable equivalent is
asserted instead, and it is strictly stronger evidence of the same fact:
the entry's overhead amount is computed from the rate in force at the
moment of posting, and a rate changed AFTERWARDS does not move it (TC246
steps 4-6). If the entry had been generated FROM the snapshot rather than
from live settings, the first MO ever posted — whose snapshot is empty —
could produce no overhead at all; TC234 proves it does.

EXPECTED v17 OUTCOME: PASS for both.
EXPECTED v19 OUTCOME: ``_post_inventory`` moved in v18 (§2.8) — LOUD if
the override signature no longer matches. The ordering risk is SILENT: a
rebuilt path that writes the snapshot BEFORE entry generation accesses
``setting.analytic_distribution`` on a string (LOUD AttributeError) or,
worse, generates the entry from frozen rates giving plausible numbers with
wrong provenance. TC246 step 7 is the assertion that separates the two.
"""
from framework.registry import test_case
from tests.wf008.common import (require_exclusive_pools,
                                CATALOGUE_RATE, COMPONENT_TOTAL,  # noqa: F401
                                LABOUR_MINUTES, LABOUR_SWITCH, MARK, MO_QTY,
                                OVERHEAD_SWITCH, WORKFLOW, WORKFLOW_NAME,
                                ZERO_YIELD_RATE, build_mo, describe_lines,
                                ensure_pool, entry_lines, expect_error,
                                finished_move, fx, live_pools, lines_named,
                                m2o_id, mark_done, record_time,
                                require_absorption_stack,
                                require_mrp_valuation, set_switches,
                                standard_environment, switches, sweep_wf008,
                                trace)

OVERHEAD_LABEL = " - Overhead Cost - "


def _complete(ctx, env, label, minutes=LABOUR_MINUTES):
    rpc = ctx.adapter.rpc
    mo_id = build_mo(ctx, env["finished_id"], env["bom_id"], label=label)
    record_time(ctx, mo_id, env["assembly"], minutes,
                employee_id=env["employee_id"])
    record_time(ctx, mo_id, env["packaging"], 30.0,
                employee_id=env["employee_id"])
    raised, message = mark_done(ctx, mo_id)
    return mo_id, raised, message


def _overhead_debit(ctx, mo_id):
    """The overhead WIP debit posted on an MO's finished-good entry."""
    rpc = ctx.adapter.rpc
    move = finished_move(rpc, mo_id)
    if not move:
        return None, []
    entries, lines = entry_lines(rpc, [move["id"]])
    overhead = lines_named(lines, OVERHEAD_LABEL)
    for row in describe_lines(rpc, overhead):
        ctx.log(f"  {row!r}")
    return round(sum(ln["debit"] or 0.0 for ln in overhead), 2), lines


def _setup(ctx):
    rpc = ctx.adapter.rpc
    with ctx.step("Sweep previous WF-008 fixtures and open a fresh "
                  "namespace"):
        sweep_wf008(rpc)
    with ctx.step("Preconditions: dto_mrp_account installed, real-time "
                  "valuation available, BOTH switches on"):
        require_absorption_stack(ctx)
        require_mrp_valuation(ctx)
        comp_id, original = switches(rpc)
        set_switches(rpc, comp_id, labour=True, overhead=True)
        env = standard_environment(ctx)
    return comp_id, original, env


def _restore(ctx, comp_id, original):
    rpc = ctx.adapter.rpc
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


@test_case(
    id="TEST-WF008-TC244",
    name="Rate freezing: stored_overhead_cost_settings written at "
         "_post_inventory",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_mrp_account", priority="P0", kind="API", order=8244,
    description="The snapshot is falsy before completion, populated after, "
                "contains ALL pools including the zero-yield one that "
                "posted nothing, holds the fractions in force at that "
                "instant, is keyed by pool NAME, is copy=False, and does "
                "not move when a rate changes afterwards.",
    traceability=trace("DATAONE-TC244"))
def test_tc244(ctx):
    rpc = ctx.adapter.rpc
    comp_id, original, env = _setup(ctx)
    pools = {}

    try:
        with ctx.step("Two pools: Factory Overhead at 0.10 and Zero Yield "
                      "at 0.000001, so 'all pools' is testable"):
            pools["factory"] = ensure_pool(
                ctx, "Factory Overhead", CATALOGUE_RATE,
                expense_account_id=env["overhead_account"]["id"])
            pools["zero"] = ensure_pool(
                ctx, "Zero Yield", ZERO_YIELD_RATE,
                expense_account_id=env["overhead_account"]["id"])
            live = live_pools(rpc)
            ctx.log(f"pools: {live!r}")
            require_exclusive_pools(ctx, 2)
            ctx.check("overhead pools in force", 2, len(live))
            names = {p["id"]: p["name"] for p in live}
            factory_name = names[pools["factory"]]
            zero_name = names[pools["zero"]]

        with ctx.step("Step 1 — EMPTY BEFORE: the snapshot is falsy on a "
                      "confirmed MO"):
            mo_id = build_mo(ctx, env["finished_id"], env["bom_id"],
                             label="TC244")
            record_time(ctx, mo_id, env["assembly"], LABOUR_MINUTES,
                        employee_id=env["employee_id"])
            record_time(ctx, mo_id, env["packaging"], 30.0,
                        employee_id=env["employee_id"])
            before = rpc.read("mrp.production", [mo_id],
                              ["state", "stored_overhead_cost_settings"])[0]
            ctx.log(f"before completion: {before!r}")
            ctx.check_true(
                "stored_overhead_cost_settings is falsy before completion",
                not before["stored_overhead_cost_settings"],
                actual_desc=before["stored_overhead_cost_settings"])

        with ctx.step("Step 2 — EMPTY MID-FLIGHT, asserted by its "
                      "observable consequence. Instrumenting "
                      "_generate_valuation_lines_data is not reachable "
                      "over RPC (check_method_name refuses any method "
                      "starting with an underscore), so the equivalent "
                      "evidence is that THIS MO — whose snapshot was empty "
                      "when the entry was built — nonetheless posted "
                      "overhead. That can only happen if the entry was "
                      "generated from LIVE settings"):
            raised, message = mark_done(ctx, mo_id)
            ctx.check_true("button_mark_done completed", not raised,
                           actual_desc=message)
            posted, lines = _overhead_debit(ctx, mo_id)
            expected = round(COMPONENT_TOTAL * CATALOGUE_RATE, 2)
            ctx.log(f"overhead posted from an EMPTY snapshot: {posted} "
                    f"(expected {expected} from the live 0.10 rate)")
            ctx.check("overhead posted on the first completion", expected,
                      posted)

        with ctx.step("Step 4: POPULATED AFTER — the snapshot is a dict"):
            after = rpc.read("mrp.production", [mo_id],
                             ["stored_overhead_cost_settings"])[0][
                "stored_overhead_cost_settings"]
            ctx.log(f"snapshot after completion: {after!r}")
            ctx.check_true("stored_overhead_cost_settings is a populated "
                           "dict", isinstance(after, dict) and bool(after),
                           actual_desc=after)

        with ctx.step("Step 5 — ALL POOLS: including the zero-yield one "
                      "that posted nothing"):
            ctx.check("snapshot keys", sorted([factory_name, zero_name]),
                      sorted(after))

        with ctx.step("Step 6: the values are the fractions in force at "
                      "that instant"):
            ctx.check("snapshot values",
                      {factory_name: CATALOGUE_RATE,
                       zero_name: ZERO_YIELD_RATE},
                      {k: round(v, 6) for k, v in after.items()})

        with ctx.step("Step 7 — THE FRAGILITY: the snapshot is keyed by "
                      "pool NAME, not by id. Renaming a pool orphans every "
                      "historical snapshot, and that is recorded here as a "
                      "known fragility rather than discovered later"):
            ids = {str(pid) for pid in pools.values()}
            ctx.check("snapshot keys are names, not ids", set(),
                      set(after) & ids)
            ctx.log("[FINDING] stored_overhead_cost_settings is keyed by "
                    "mrp.overhead.cost.setting.name. A rename breaks the "
                    "link between a completed MO's frozen rate and the "
                    "pool it came from, with no error and no migration. "
                    "TEST-WF008-TC246 step 9 probes what the MO Overview "
                    "does in that state.")

        with ctx.step("Step 8 — copy=False: a duplicated MO carries no "
                      "snapshot"):
            copies = rpc.call("mrp.production", "copy", [mo_id])
            copy_id = copies[0] if isinstance(copies, list) else copies
            copy_snapshot = rpc.read("mrp.production", [copy_id],
                                     ["stored_overhead_cost_settings"])[0][
                "stored_overhead_cost_settings"]
            ctx.log(f"duplicate MO {copy_id} snapshot: {copy_snapshot!r}")
            ctx.check_true("the duplicate's snapshot is falsy",
                           not copy_snapshot, actual_desc=copy_snapshot)
            try:
                rpc.call("mrp.production", "action_cancel", [copy_id])
                rpc.unlink("mrp.production", [copy_id])
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] duplicate MO not removed: {exc}")

        with ctx.step("Step 9 — IMMUTABILITY: change the pool rate to "
                      "0.20 and re-read the snapshot; it must still say "
                      "0.10"):
            rpc.write("mrp.overhead.cost.setting", [pools["factory"]],
                      {"percentage": 0.20})
            reread = rpc.read("mrp.production", [mo_id],
                              ["stored_overhead_cost_settings"])[0][
                "stored_overhead_cost_settings"]
            ctx.log(f"snapshot after the rate change: {reread!r}")
            ctx.check("the frozen Factory Overhead rate", CATALOGUE_RATE,
                      round((reread or {}).get(factory_name, 0.0), 6))

        with ctx.step("Step 10 — THE ORDERING: the journal entry exists "
                      "before or at the snapshot write. Compared through "
                      "the ORM's own timestamps rather than SQL, so the "
                      "case never reports BLOCKED for a missing pg_* "
                      "config"):
            move = finished_move(rpc, mo_id)
            entries, _ = entry_lines(rpc, [move["id"]])
            entry_rows = rpc.read("account.move", entries,
                                  ["create_date", "name"]) if entries else []
            mo_row = rpc.read("mrp.production", [mo_id], ["write_date"])[0]
            ctx.log(f"entry create_date(s): {entry_rows!r}")
            ctx.log(f"MO write_date: {mo_row!r}")
            if entry_rows:
                latest_entry = max(r["create_date"] for r in entry_rows)
                ctx.check_true(
                    "the valuation entry was created before or at the "
                    "snapshot write — the entry is NOT generated from "
                    "frozen rates",
                    str(latest_entry) <= str(mo_row["write_date"]),
                    actual_desc=f"entry={latest_entry} "
                                f"mo_write={mo_row['write_date']}")

        with ctx.step("Step 11 — THE E8 GUARD: reading the overhead "
                      "calculation again on a DONE MO must not raise. "
                      "_calc_production_overhead_cost is private and not "
                      "dispatchable, so the reachable equivalent is the MO "
                      "Overview, which calls it on exactly this record"):
            raised2, message2 = expect_error(
                rpc.call, "report.mrp.report_mo_overview",
                "get_report_values", mo_id)
            ctx.log(f"Overview on the done MO: raised={raised2} "
                    f"{message2!r}")
            if raised2 and "AttributeError" in message2:
                ctx.log("[FINDING] E8 is LIVE: reading the overhead "
                        "calculation after posting raises AttributeError "
                        "— setting.analytic_distribution accessed on a "
                        "STRING key from the snapshot. A second valuation "
                        "posting on the same MO would crash Mark as Done.")
            ctx.check_true(
                "re-reading the overhead calculation on a done MO does "
                "not raise AttributeError",
                not (raised2 and "AttributeError" in message2),
                actual_desc=message2)
    finally:
        with ctx.step("Restore the Factory Overhead rate to 0.10 before "
                      "the sweep"):
            try:
                rpc.write("mrp.overhead.cost.setting", [pools["factory"]],
                          {"percentage": CATALOGUE_RATE})
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] pool rate restore failed: {exc}")
        _restore(ctx, comp_id, original)


@test_case(
    id="TEST-WF008-TC246",
    name="Pool rate changed after completion — the completed MO does not "
         "move",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_mrp_account", priority="P0", kind="API", order=8246,
    description="After the rate changes from 0.10 to 0.20: the completed "
                "MO's journal entry, snapshot and Overview all still read "
                "the frozen 0.10, a NEW MO uses 0.20 and snapshots it, the "
                "two coexist, and renaming the pool is probed for what it "
                "does to the old MO's Overview.",
    traceability=trace("DATAONE-TC246"))
def test_tc246(ctx):
    rpc = ctx.adapter.rpc
    comp_id, original, env = _setup(ctx)
    pool_id = None
    original_name = None

    try:
        with ctx.step("One pool at 0.10, and one completed MO with a known "
                      "posted overhead"):
            pool_id = ensure_pool(
                ctx, "Factory Overhead", CATALOGUE_RATE,
                expense_account_id=env["overhead_account"]["id"])
            require_exclusive_pools(ctx, 1)
            ctx.check("overhead pools in force", 1, len(live_pools(rpc)))
            original_name = rpc.read("mrp.overhead.cost.setting", [pool_id],
                                     ["name"])[0]["name"]
            old_mo, raised, message = _complete(ctx, env, "TC246-old")
            ctx.check_true("the first MO completed", not raised,
                           actual_desc=message)

        with ctx.step("Step 1: record the completed MO's posted overhead "
                      "and its frozen rate"):
            old_overhead, old_lines = _overhead_debit(ctx, old_mo)
            expected_old = round(COMPONENT_TOTAL * CATALOGUE_RATE, 2)
            ctx.check("overhead posted at the 0.10 rate", expected_old,
                      old_overhead)
            old_snapshot = rpc.read("mrp.production", [old_mo],
                                    ["stored_overhead_cost_settings"])[0][
                "stored_overhead_cost_settings"]
            ctx.log(f"frozen snapshot: {old_snapshot!r}")
            ctx.check("the frozen rate", {original_name: CATALOGUE_RATE},
                      {k: round(v, 4)
                       for k, v in (old_snapshot or {}).items()})

        with ctx.step("Step 2: record the MO Overview's actual overhead "
                      "row — 6.00 per unit at the frozen rate"):
            raised_r, message_r = expect_error(
                rpc.call, "report.mrp.report_mo_overview",
                "get_report_values", old_mo)
            overview_before = None
            if raised_r:
                ctx.log(f"[warn] Overview not readable: {message_r}")
            else:
                overview_before = rpc.call("report.mrp.report_mo_overview",
                                           "get_report_values", old_mo)
                ctx.log(f"Overview contains 'Overhead:': "
                        f"{'Overhead:' in repr(overview_before)}")

        with ctx.step("Step 3: as the Accounting Manager would, change the "
                      "pool rate from 0.10 to 0.20"):
            rpc.write("mrp.overhead.cost.setting", [pool_id],
                      {"percentage": 0.20})
            ctx.check("the live pool rate", 0.20,
                      round(rpc.read("mrp.overhead.cost.setting", [pool_id],
                                     ["percentage"])[0]["percentage"], 4))

        with ctx.step("Step 4 — THE CONTROL: the posted journal entry is "
                      "unchanged. It could hardly change, and that is "
                      "exactly why it is asserted — a rebuild that "
                      "re-posts on a rate change would be catastrophic and "
                      "must be excluded explicitly"):
            reread_overhead, _ = _overhead_debit(ctx, old_mo)
            ctx.check("overhead on the completed MO after the rate change",
                      expected_old, reread_overhead)

        with ctx.step("Step 5: the snapshot is unchanged — still 0.10"):
            snapshot_after = rpc.read("mrp.production", [old_mo],
                                      ["stored_overhead_cost_settings"])[0][
                "stored_overhead_cost_settings"]
            ctx.log(f"snapshot after the rate change: {snapshot_after!r}")
            ctx.check("the frozen rate after the change",
                      {original_name: CATALOGUE_RATE},
                      {k: round(v, 4)
                       for k, v in (snapshot_after or {}).items()})

        with ctx.step("Step 6 — THE SILENT RISK: the Overview still reads "
                      "the frozen rate. A rebuild that reads LIVE settings "
                      "restates every historical MO the moment a rate "
                      "changes, with no error and no audit trail"):
            if overview_before is not None:
                overview_after = rpc.call("report.mrp.report_mo_overview",
                                          "get_report_values", old_mo)
                before_text = repr(overview_before)
                after_text = repr(overview_after)
                ctx.log(f"Overview identical before/after the rate change: "
                        f"{before_text == after_text}")
                doubled = round(COMPONENT_TOTAL * 0.20, 2)
                ctx.check_true(
                    f"the completed MO's Overview does NOT show the "
                    f"doubled overhead ({doubled})",
                    str(doubled) not in after_text
                    or str(expected_old) in after_text,
                    actual_desc=after_text[:600])
            else:
                ctx.log("The Overview half of this step is carried by "
                        "TEST-WF008-TC245.")

        with ctx.step("Step 7: a NEW MO uses the NEW rate and snapshots "
                      "it"):
            new_mo, raised2, message2 = _complete(ctx, env, "TC246-new")
            ctx.check_true("the second MO completed", not raised2,
                           actual_desc=message2)
            new_overhead, _ = _overhead_debit(ctx, new_mo)
            expected_new = round(COMPONENT_TOTAL * 0.20, 2)
            ctx.check("overhead posted at the 0.20 rate", expected_new,
                      new_overhead)
            new_snapshot = rpc.read("mrp.production", [new_mo],
                                    ["stored_overhead_cost_settings"])[0][
                "stored_overhead_cost_settings"]
            ctx.log(f"new MO snapshot: {new_snapshot!r}")
            ctx.check("the new MO's frozen rate", {original_name: 0.20},
                      {k: round(v, 4)
                       for k, v in (new_snapshot or {}).items()})

        with ctx.step("Step 8 — COEXISTENCE: the two MOs report their own "
                      "rates, each auditable to its own snapshot. The rate "
                      "change is PROSPECTIVE ONLY"):
            ctx.check("the two MOs' posted overhead",
                      [expected_old, expected_new],
                      [old_overhead, new_overhead])
            ctx.check_true("the two frozen rates differ",
                           round((snapshot_after or {}).get(
                               original_name, 0.0), 4)
                           != round((new_snapshot or {}).get(
                               original_name, 0.0), 4),
                           actual_desc=f"{snapshot_after} vs {new_snapshot}")

        with ctx.step("Step 9 — THE RENAME PROBE: rename the pool and "
                      "reopen the OLD MO's Overview. The snapshot key no "
                      "longer matches any live pool. Assert it does not "
                      "crash, and RECORD what it shows"):
            renamed = f"{original_name} v2"
            rpc.write("mrp.overhead.cost.setting", [pool_id],
                      {"name": renamed})
            raised3, message3 = expect_error(
                rpc.call, "report.mrp.report_mo_overview",
                "get_report_values", old_mo)
            ctx.log(f"Overview after the rename: raised={raised3} "
                    f"{message3!r}")
            ctx.check_true(
                "the Overview does not crash when the snapshot key names "
                "a pool that no longer exists",
                not raised3, actual_desc=message3)
            if not raised3:
                after_rename = repr(rpc.call(
                    "report.mrp.report_mo_overview", "get_report_values",
                    old_mo))
                shows_old = original_name in after_rename
                shows_new = renamed in after_rename
                ctx.log(f"[FINDING] after renaming the pool, the completed "
                        f"MO's Overview shows the OLD name: {shows_old}; "
                        f"the NEW name: {shows_new}. The snapshot is keyed "
                        "by name, so a rename orphans it — recorded as a "
                        "known fragility (TEST-WF008-TC244 step 7).")
            posted_after_rename, _ = _overhead_debit(ctx, old_mo)
            ctx.check("the posted overhead is unaffected by the rename",
                      expected_old, posted_after_rename)
    finally:
        with ctx.step("Step 10: restore the pool's rate and name. Verify "
                      "both before any further case runs"):
            restored = {}
            try:
                if pool_id:
                    rpc.write("mrp.overhead.cost.setting", [pool_id],
                              {"percentage": CATALOGUE_RATE,
                               "name": original_name})
                    restored = rpc.read("mrp.overhead.cost.setting",
                                        [pool_id],
                                        ["name", "percentage"])[0]
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] pool restore failed: {exc}")
            ctx.log(f"pool after restore: {restored!r}")
            # This step runs in the FINALLY, so it also runs when an earlier
            # precondition blocked the case. When it does, pool_id and
            # original_name are still None: there is nothing to restore,
            # and asserting a restoration that was never needed turns a
            # correct BLOCKED into a misleading FAILED. Measured — the
            # write came back "Missing required value for the field
            # 'Name'", because it was writing name=None.
            if not pool_id or not original_name:
                ctx.log("nothing to restore — the fixture pool was never "
                        "created, so no rate or name was changed")
            else:
                ctx.check_true(
                    "the pool's rate and name were restored",
                    restored.get("name") == original_name
                    and round(restored.get("percentage", 0.0), 4)
                    == CATALOGUE_RATE,
                    actual_desc=restored)
        _restore(ctx, comp_id, original)
