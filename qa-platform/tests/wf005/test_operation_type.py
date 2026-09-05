"""DATAONE-WF-005 — operation types drive the routing: TC101–TC105.

TC101 generation, TC102 regeneration by record identity, TC103 line deletion
propagating to open MOs only, TC104 the delete guard, TC105 the no-type and
past-confirmed cases.

The generation mechanism is a COMPUTE — ``_compute_workorder_ids``
(mrp_production.py:52), ``@api.depends`` on the type's lines — so writing
``mrp_operation_type_id`` is the whole trigger and no button call exists to
press. The compute skips any MO whose state is not ``draft`` or
``confirmed``, which is what makes TC105's step 9 assertable at all.

EXPECTED v19 OUTCOME: PASS for TC101, TC103, TC104, TC105.
TC102 carries a known open defect — see its own docstring (B-24, recorded in
tools/uninstall_non_migrated.py's KEEP entry for dto_mrp: "changing an MO
Operation Type a SECOND time raises NotNullViolation on
mrp_workorder.workcenter_id. First assignment works."). The case asserts the
workbook's expectation and will surface that defect rather than accommodate
it.
"""
from adapters.base import OdooRPCError
from framework.registry import test_case
from tests.wf005.common import (ERROR_LINKED_MO, WORKFLOW, WORKFLOW_NAME,
                                m2o_id, make_bom, make_mo, make_operation_type,
                                make_product, make_workcenter,
                                open_namespace, operation_lines,
                                require_operation_types, still_exists,
                                sweep_wf005, trace, workorder_ids, workorders)


def _three_line_fixture(rpc):
    """Assembly / Test / Packaging on three work centres, plus a BoM."""
    wc_assembly = make_workcenter(rpc, "WC-ASSEMBLY")
    wc_test = make_workcenter(rpc, "WC-TEST")
    wc_pack = make_workcenter(rpc, "WC-PACKAGING")
    op_type = make_operation_type(rpc, "OT-STANDARD", [
        ("Assembly", wc_assembly, 1),
        ("Test", wc_test, 2),
        ("Packaging", wc_pack, 3),
    ])
    comp = make_product(rpc, "CMP-A")
    fg = make_product(rpc, "FG-CABLE")
    bom = make_bom(rpc, fg, comp)
    return wc_assembly, wc_test, wc_pack, op_type, fg, bom


@test_case(
    id="TEST-WF005-TC101",
    name="Assigning an MO Operation Type generates one work order per line",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_mrp",
    priority="P1", kind="API", order=5101,
    description="Setting the operation type on a draft MO produces exactly "
                "one work order per operation-type line, in line sequence, on "
                "each line's work centre, all Pending, each stamped with its "
                "source line and type.",
    traceability=trace("DATAONE-TC101"))
def test_tc101(ctx):
    require_operation_types(ctx)
    rpc = ctx.adapter.rpc
    open_namespace(ctx)
    try:
        with ctx.step("A three-line operation type and a draft MO with none set"):
            wc_a, wc_t, wc_p, op_type, fg, bom = _three_line_fixture(rpc)
            mo = make_mo(rpc, fg, bom, qty=1.0)
            ctx.check("the MO starts with no operation type", False,
                      rpc.read("mrp.production", [mo],
                               ["mrp_operation_type_id"])[0]
                      ["mrp_operation_type_id"])
            baseline = workorder_ids(rpc, mo)
            ctx.log(f"work orders before assignment: {baseline}")

        with ctx.step("Set the MO Operation Type"):
            rpc.write("mrp.production", [mo],
                      {"mrp_operation_type_id": op_type})

        with ctx.step("One work order per operation-type line"):
            lines = operation_lines(rpc, op_type)
            wos = workorders(rpc, mo)
            ctx.check("line count", 3, len(lines))
            ctx.check("work order count equals line count", len(lines), len(wos))

        with ctx.step("They read in line sequence, on the lines' work centres"):
            wos = workorders(rpc, mo)
            ctx.check("operation names in sequence",
                      ["Assembly", "Test", "Packaging"],
                      [w["name"] for w in wos])
            ctx.check("work centres in sequence", [wc_a, wc_t, wc_p],
                      [m2o_id(w["workcenter_id"]) for w in wos])

        with ctx.step("Every work order is queued, none started"):
            # Observation correction, not an expectation change. The workbook
            # asserts state == 'pending', which is v17 vocabulary: Odoo 19's
            # mrp.workorder.state selection is
            #   ('blocked', 'cancel', 'done', 'progress', 'ready')
            # — 'pending' no longer exists (addons/mrp/models/mrp_workorder.py).
            # Measured on this target, and core's own BoM-driven routing
            # behaves identically, so this is the platform's vocabulary and
            # not a dto_mrp defect:
            #   draft MO      -> Assembly ready, Test ready,   Packaging ready
            #   confirmed MO  -> Assembly ready, Test blocked, Packaging blocked
            #   core routing  -> Core A   ready, Core B blocked
            # The substance of the expectation — freshly generated, none
            # started — is asserted directly below.
            states = [w["state"] for w in workorders(rpc, mo)]
            ctx.check("all work orders are in a queued state on a draft MO",
                      ["ready"] * 3, states)
            ctx.check_true("none has been started or finished",
                           all(s not in ("progress", "done", "cancel")
                               for s in states), str(states))

        with ctx.step("Each is stamped with its source line and type"):
            wos = workorders(rpc, mo)
            ctx.check_true("every work order carries a source line",
                           all(w["mrp_operation_type_line_id"] for w in wos),
                           str([w["mrp_operation_type_line_id"] for w in wos]))
            ctx.check("every work order carries the type", [op_type] * 3,
                      [m2o_id(w["mrp_operation_type_id"]) for w in wos])
            ctx.check("the stamped lines are the type's own lines",
                      {ln["id"] for ln in operation_lines(rpc, op_type)},
                      {m2o_id(w["mrp_operation_type_line_id"]) for w in wos})
    finally:
        try:
            sweep_wf005(rpc)
        except Exception:  # noqa: BLE001
            pass


@test_case(
    id="TEST-WF005-TC102",
    name="Changing the operation type destroys the old work orders and "
         "regenerates (assert by record id)",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_mrp",
    priority="P0", kind="API", order=5102,
    description="Switching a confirmed MO from a three-line type to a "
                "two-line one leaves two work orders whose ids are disjoint "
                "from the first three, and the original three no longer exist "
                "anywhere in mrp.workorder — destroy-and-recreate, not "
                "update-in-place.",
    traceability=trace("DATAONE-TC102"))
def test_tc102(ctx):
    """EXPECTED v19 OUTCOME: this case targets a KNOWN OPEN DEFECT, B-24.

    ``tools/uninstall_non_migrated.py``'s KEEP entry for ``dto_mrp`` records
    it in the project's own words:

        "WF-005 is PARTIAL. B-24 is open — changing an MO Operation Type a
        SECOND time raises NotNullViolation on mrp_workorder.workcenter_id.
        First assignment works. If UAT exercises operation types, that is the
        failure they will hit, and it is known, not a regression from this
        deploy."

    The workbook's expectation is that the change succeeds and the old work
    orders are gone by id. That expectation is not weakened here
    (AUTOMATION_CONVENTIONS hard rule 2): the case performs the second
    assignment and asserts the required outcome, so a failure names B-24
    precisely rather than being absorbed by a softer assertion. Step 8 and
    step 9 of the workbook are the case — a count check alone would pass
    against a buggy update-in-place implementation by coincidence.
    """
    require_operation_types(ctx)
    rpc = ctx.adapter.rpc
    open_namespace(ctx)
    try:
        with ctx.step("A confirmed MO carrying the three-line type"):
            wc_a, wc_t, wc_p, op_type, fg, bom = _three_line_fixture(rpc)
            op_short = make_operation_type(rpc, "OT-SHORT", [
                ("Assembly", wc_a, 1),
                ("Packaging", wc_p, 2),
            ])
            mo = make_mo(rpc, fg, bom, qty=1.0, op_type_id=op_type)
            first_ids = workorder_ids(rpc, mo)
            ctx.check("three work orders from the first type", 3, len(first_ids))
            rpc.call("mrp.production", "action_confirm", [mo])
            ctx.check("the MO is confirmed", "confirmed",
                      rpc.read("mrp.production", [mo], ["state"])[0]["state"])
            first_ids = workorder_ids(rpc, mo)
            ctx.log(f"first generation ids: {first_ids}")

        with ctx.step("Change the MO Operation Type to the two-line one"):
            error = ""
            try:
                rpc.write("mrp.production", [mo],
                          {"mrp_operation_type_id": op_short})
            except OdooRPCError as exc:
                error = str(exc)
            ctx.check_true("the change is accepted", not error,
                           error[:220] or "no error")

        with ctx.step("Two work orders remain"):
            second_ids = workorder_ids(rpc, mo)
            ctx.check("work order count", 2, len(second_ids))

        with ctx.step("No record from the first generation survives"):
            second_ids = workorder_ids(rpc, mo)
            ctx.check("the two generations share no record id", set(),
                      set(first_ids) & set(second_ids))

        with ctx.step("The originals are gone from mrp.workorder entirely"):
            ctx.check("no orphaned rows anywhere in the table", [],
                      still_exists(rpc, "mrp.workorder", first_ids))

        with ctx.step("The survivors follow the new type's lines"):
            wos = workorders(rpc, mo)
            ctx.check("work centres in sequence", [wc_a, wc_p],
                      [m2o_id(w["workcenter_id"]) for w in wos])
            ctx.check("both carry the new type", [op_short] * 2,
                      [m2o_id(w["mrp_operation_type_id"]) for w in wos])
    finally:
        try:
            sweep_wf005(rpc)
        except Exception:  # noqa: BLE001
            pass


@test_case(
    id="TEST-WF005-TC103",
    name="Deleting an operation-type line removes the matching work order "
         "from open MOs",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_mrp",
    priority="P1", kind="API", order=5103,
    description="Deleting the middle line of a three-line type drops the "
                "matching work order from a confirmed MO, leaving the other "
                "two in sequence and Pending, while an MO past confirmed "
                "keeps its routing untouched.",
    traceability=trace("DATAONE-TC103"))
def test_tc103(ctx):
    require_operation_types(ctx)
    rpc = ctx.adapter.rpc
    open_namespace(ctx)
    try:
        with ctx.step("Two MOs on the same type: one confirmed, one frozen"):
            wc_a, wc_t, wc_p, op_type, fg, bom = _three_line_fixture(rpc)
            mo_open = make_mo(rpc, fg, bom, qty=1.0, op_type_id=op_type,
                              confirm=True)
            mo_frozen = make_mo(rpc, fg, bom, qty=1.0, op_type_id=op_type,
                                confirm=True)
            open_ids = workorder_ids(rpc, mo_open)
            frozen_ids = workorder_ids(rpc, mo_frozen)
            ctx.check("both MOs start with three work orders", [3, 3],
                      [len(open_ids), len(frozen_ids)])
            # Push the second MO past 'confirmed' so the compute skips it.
            try:
                rpc.call("mrp.production", "button_plan", [mo_frozen])
            except OdooRPCError:
                pass
            wo_ids = workorder_ids(rpc, mo_frozen)
            if wo_ids:
                try:
                    rpc.call("mrp.workorder", "button_start", [wo_ids[0]])
                except OdooRPCError:
                    pass
            frozen_state = rpc.read("mrp.production", [mo_frozen],
                                    ["state"])[0]["state"]
            frozen_ids = workorder_ids(rpc, mo_frozen)
            ctx.log(f"frozen MO state = {frozen_state}")
            if frozen_state in ("draft", "confirmed"):
                ctx.blocked(
                    f"could not move an MO past 'confirmed' (it is still "
                    f"{frozen_state!r}), so the half of this case that proves "
                    f"a frozen routing is untouched cannot be observed. "
                    f"button_plan/button_start were both attempted.")

        with ctx.step("Delete the middle line (Test, sequence 2)"):
            lines = operation_lines(rpc, op_type)
            middle = [ln for ln in lines if ln["sequence"] == 2]
            ctx.check("exactly one line at sequence 2", 1, len(middle))
            rpc.call("mrp.operation.type.line", "unlink", [middle[0]["id"]])

        with ctx.step("The open MO drops the matching work order"):
            wos = workorders(rpc, mo_open)
            ctx.check("two work orders remain", 2, len(wos))
            ctx.check_true("none is on the Test work centre",
                           wc_t not in [m2o_id(w["workcenter_id"]) for w in wos],
                           str([m2o_id(w["workcenter_id"]) for w in wos]))
            ctx.check("the survivors are Assembly then Packaging",
                      [wc_a, wc_p], [m2o_id(w["workcenter_id"]) for w in wos])
            # v19 vocabulary — see TC101: no 'pending' state exists.
            ctx.check_true("neither survivor has been started",
                           all(w["state"] not in ("progress", "done", "cancel")
                               for w in wos), str([w["state"] for w in wos]))

        with ctx.step("The frozen MO's routing is untouched"):
            ctx.check("work order ids are identical", frozen_ids,
                      workorder_ids(rpc, mo_frozen))
    finally:
        try:
            sweep_wf005(rpc)
        except Exception:  # noqa: BLE001
            pass


@test_case(
    id="TEST-WF005-TC104",
    name="An operation type referenced by any MO cannot be deleted",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_mrp",
    priority="P1", kind="API", order=5104,
    description="An unreferenced operation type deletes; one referenced by an "
                "MO raises the guard's exact message and survives; cancelling "
                "that MO does not release the reference, because the guard is "
                "state-blind.",
    traceability=trace("DATAONE-TC104"))
def test_tc104(ctx):
    require_operation_types(ctx)
    rpc = ctx.adapter.rpc
    open_namespace(ctx)
    try:
        with ctx.step("One referenced operation type and one unreferenced"):
            wc_a, wc_t, wc_p, op_type, fg, bom = _three_line_fixture(rpc)
            op_free = make_operation_type(rpc, "OT-UNREFERENCED",
                                          [("Assembly", wc_a, 1)])
            mo = make_mo(rpc, fg, bom, qty=1.0, op_type_id=op_type)
            ctx.check("the referenced type knows its MO", 1,
                      rpc.read("mrp.operation.type", [op_type],
                               ["mrp_production_ids_count"])[0]
                      ["mrp_production_ids_count"])

        with ctx.step("The unreferenced type deletes cleanly"):
            rpc.call("mrp.operation.type", "unlink", [op_free])
            ctx.check("it no longer exists", [],
                      still_exists(rpc, "mrp.operation.type", [op_free]))

        with ctx.step("The referenced type raises the guard's exact message"):
            error = ""
            try:
                rpc.call("mrp.operation.type", "unlink", [op_type])
            except OdooRPCError as exc:
                error = str(exc)
            ctx.check_true(f"UserError says {ERROR_LINKED_MO!r}",
                           ERROR_LINKED_MO in error,
                           error[:240] or "no error raised")

        with ctx.step("It survives the rolled-back transaction"):
            ctx.check("still exists", [op_type],
                      still_exists(rpc, "mrp.operation.type", [op_type]))

        with ctx.step("Cancelling the MO does not release the reference"):
            rpc.call("mrp.production", "action_cancel", [mo])
            ctx.check("the MO is cancelled", "cancel",
                      rpc.read("mrp.production", [mo], ["state"])[0]["state"])
            error = ""
            try:
                rpc.call("mrp.operation.type", "unlink", [op_type])
            except OdooRPCError as exc:
                error = str(exc)
            ctx.check_true("the same guard still fires — it is state-blind",
                           ERROR_LINKED_MO in error,
                           error[:240] or "no error raised")
            ctx.check("the type still exists", [op_type],
                      still_exists(rpc, "mrp.operation.type", [op_type]))
    finally:
        try:
            sweep_wf005(rpc)
        except Exception:  # noqa: BLE001
            pass


@test_case(
    id="TEST-WF005-TC105",
    name="An MO with no operation type keeps core's BoM-driven routing, and "
         "the field is readonly past confirmed",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_mrp",
    priority="P1", kind="API", order=5105,
    description="With no operation type set, an MO's work orders are exactly "
                "core's BoM-driven routing and none carries an "
                "operation-type line; on an MO past confirmed an RPC write of "
                "the field changes no routing, because the compute skips any "
                "state beyond confirmed.",
    traceability=trace("DATAONE-TC105"))
def test_tc105(ctx):
    require_operation_types(ctx)
    rpc = ctx.adapter.rpc
    open_namespace(ctx)
    try:
        with ctx.step("A BoM carrying core's own routing operations"):
            wc_a = make_workcenter(rpc, "WC-ASSEMBLY")
            wc_t = make_workcenter(rpc, "WC-TEST")
            comp = make_product(rpc, "CMP-A")
            fg = make_product(rpc, "FG-CABLE")
            bom = make_bom(rpc, fg, comp,
                           operations=[("Core Assembly", wc_a),
                                       ("Core Test", wc_t)])
            op_type = make_operation_type(rpc, "OT-STANDARD",
                                          [("Assembly", wc_a, 1)])

        with ctx.step("Confirm an MO with no operation type"):
            mo_c = make_mo(rpc, fg, bom, qty=1.0, confirm=True)
            wos = workorders(rpc, mo_c)
            ctx.check("core's two BoM operations produced two work orders", 2,
                      len(wos))
            ctx.check("their names are the BoM's operation names",
                      ["Core Assembly", "Core Test"],
                      sorted(w["name"] for w in wos))
            ctx.check("their work centres are the BoM's", {wc_a, wc_t},
                      {m2o_id(w["workcenter_id"]) for w in wos})

        with ctx.step("No work order carries an operation-type line"):
            ctx.check("every mrp_operation_type_line_id is empty",
                      [False, False],
                      [w["mrp_operation_type_line_id"] for w in workorders(rpc, mo_c)])

        with ctx.step("An MO past confirmed ignores an RPC write of the field"):
            mo_d = make_mo(rpc, fg, bom, qty=1.0, confirm=True)
            try:
                rpc.call("mrp.production", "button_plan", [mo_d])
            except OdooRPCError:
                pass
            wo_ids = workorder_ids(rpc, mo_d)
            if wo_ids:
                try:
                    rpc.call("mrp.workorder", "button_start", [wo_ids[0]])
                except OdooRPCError:
                    pass
            state = rpc.read("mrp.production", [mo_d], ["state"])[0]["state"]
            if state in ("draft", "confirmed"):
                ctx.blocked(
                    f"could not move an MO past 'confirmed' (still {state!r}), "
                    f"so the past-confirmed half of this case cannot be "
                    f"observed. button_plan/button_start were both attempted.")
            before = workorder_ids(rpc, mo_d)
            rpc.write("mrp.production", [mo_d],
                      {"mrp_operation_type_id": op_type})
            ctx.check("the routing is unchanged", before,
                      workorder_ids(rpc, mo_d))
            ctx.check_true(
                "no work order was stamped with the type",
                all(not w["mrp_operation_type_line_id"]
                    for w in workorders(rpc, mo_d)),
                str([w["mrp_operation_type_line_id"]
                     for w in workorders(rpc, mo_d)]))
    finally:
        try:
            sweep_wf005(rpc)
        except Exception:  # noqa: BLE001
            pass
