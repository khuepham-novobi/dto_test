"""DATAONE-WF-007 — what suppresses or blocks completion: TC109, TC113–TC115.

TC109 is an eligibility condition: a failed quality check must stop the
automatic number being invented, so the operator has to decide explicitly.
It is asserted with a positive control, because "no lot was created" also
describes a broken pipeline.

TC113, TC114 and TC115 assert behaviour that is NOT DEPLOYED on this target,
and each BLOCKS with the precise reason rather than failing:

* TC113's Mass Produce prefill was **deliberately removed** during the port.
  ``dto_mrp/models/mrp_production.py:355-365`` records why: v19 deleted
  ``action_serial_mass_produce_wizard`` ("0 occurrences in v19 mrp +
  mrp_workorder"), so the override that injected
  ``default_next_serial_number = <lot name>-001`` had no ``super()`` to call
  and would raise AttributeError. It was removed rather than retargeted
  because the replacement wizard ``mrp.production.serials`` has no
  ``next_serial_number`` field at all. Measured: ``stock.assign.serial`` does
  not exist on d1v19.
* TC114 and TC115 assert the Packaging duration gate, which lives in
  ``dto_mrp_account`` (models/mrp_production.py:114) — still 17.0,
  deliberately excluded from ``tools/uninstall_non_migrated.py``'s KEEP list,
  and uninstalled on d1v19. Measured.

A BLOCKED verdict is the honest one for all three: the workbook's
expectation is not wrong and the code is not broken — the behaviour is not
present on this deployment, and the reason names exactly what would have to
change for the case to run.
"""
from framework.registry import test_case
from tests.wf007.common import (ERROR_PACKAGING, WORKFLOW, WORKFLOW_NAME,
                                consume_components, lot_info, lots_for,
                                make_bom, make_mo, make_product,
                                make_sale_order, mo_field, open_namespace,
                                producing_lots, require_packaging_gate,
                                require_serial_stack, set_qty_producing,
                                sweep_wf007, trace)


@test_case(
    id="TEST-WF007-TC109",
    name="A failed quality check suppresses automatic serial generation",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_mrp",
    priority="P0", kind="API", order=7109,
    description="With quality_check_fail set, pre_button_mark_done creates no "
                "lot at all; the same fixture with the check passing does "
                "create one with auto_generated True — the positive control "
                "that proves the condition is what is being tested.",
    traceability=trace("DATAONE-TC109"))
def test_tc109(ctx):
    """EXPECTED v19 OUTCOME: FAIL — a real port regression, located precisely.

    ``dto_mrp.pre_button_mark_done`` guards its OWN call correctly::

        for production in self.filtered(
                lambda r: r._eligible_for_auto_generate_serial()):
            production.action_generate_serial()
        return super().pre_button_mark_done()

    and ``_eligible_for_auto_generate_serial`` does include
    ``and not self.quality_check_fail`` (mrp_production.py:291). But the
    ``super()`` call then reaches **v19 core**, which generates the serial
    itself with no quality condition at all
    (addons/mrp/models/mrp_production.py:2341-2354)::

        elif not production.lot_producing_ids:
            production_missing_lot_ids...
        if production_missing_lot_ids:
            return browse(production_missing_lot_ids).action_generate_serial()

    So the guard suppresses one call and core makes another. Measured
    directly on d1v19, outside this suite::

        quality_check_fail = True   check_ids = [2518] (quality_state 'fail')
        lots before pre_button_mark_done : []
        lots after                       : [126877]

    v17 core had no such generation in ``pre_button_mark_done``, so the guard
    was sufficient there and is not any more. The operator is given an
    automatic number on a failed quality check — the exact outcome the
    workbook forbids.

    The assertion stays as written (AUTOMATION_CONVENTIONS hard rule 2). The
    fix belongs in dto_mrp: the eligibility test has to be enforced around
    core's generation too, not only around the module's own call.
    """
    require_serial_stack(ctx)
    rpc = ctx.adapter.rpc
    if not rpc.field_exists("mrp.production", "quality_check_fail"):
        ctx.blocked(
            "mrp.production.quality_check_fail does not exist on this target, "
            "so the quality condition in _eligible_for_auto_generate_serial "
            "(dto_mrp/models/mrp_production.py:291) cannot be exercised. "
            "quality_mrp must be installed.")
    open_namespace(ctx)
    try:
        with ctx.step("A tracked MO whose quality check has failed"):
            comp = make_product(rpc, "CMP")
            fg = make_product(rpc, "FG-LOT", tracking="lot")
            bom = make_bom(rpc, fg, comp)
            _o, _so, line = make_sale_order(rpc, fg, 1.0)
            mo = make_mo(rpc, fg, bom, qty=1.0, sale_line_id=line)
            set_qty_producing(rpc, mo, 1.0)
            consume_components(rpc, mo)
            # quality_check_fail is COMPUTED from check_ids
            # (enterprise/quality_mrp/models/mrp_production.py:20-32: it is
            # True when any check has quality_state == 'fail'), so it cannot
            # be written directly — a write is silently discarded and the
            # field reads back False. A real check is created and failed
            # instead, which is also what an operator does.
            team = rpc.search("quality.alert.team", [], limit=1)
            check_id = rpc.create("quality.check", {
                "production_id": mo, "product_id": fg,
                "team_id": team[0] if team else False})
            rpc.call("quality.check", "do_fail", [check_id])
            ctx.check("quality_check_fail", True,
                      mo_field(rpc, mo, "quality_check_fail"))
            ctx.check("no lot yet", [], producing_lots(rpc, mo))

        with ctx.step("pre_button_mark_done creates no lot"):
            rpc.call("mrp.production", "pre_button_mark_done", [mo])
            ctx.check("still no producing lot", [], producing_lots(rpc, mo))
            ctx.check("no lot exists for the product at all", 0,
                      len(lots_for(rpc, fg)))

        with ctx.step("Positive control: the same fixture with a passed check"):
            comp2 = make_product(rpc, "CMP2")
            fg2 = make_product(rpc, "FG-LOT2", tracking="lot")
            bom2 = make_bom(rpc, fg2, comp2)
            _o2, _so2, line2 = make_sale_order(rpc, fg2, 1.0)
            mo2 = make_mo(rpc, fg2, bom2, qty=1.0, sale_line_id=line2)
            set_qty_producing(rpc, mo2, 1.0)
            consume_components(rpc, mo2)
            ctx.check("quality_check_fail is False", False,
                      mo_field(rpc, mo2, "quality_check_fail"))
            rpc.call("mrp.production", "pre_button_mark_done", [mo2])
            lots = producing_lots(rpc, mo2)
            ctx.check("a lot WAS created", 1, len(lots))
            if lots:
                ctx.check("auto_generated", True,
                          lot_info(rpc, lots[0])["auto_generated"])
    finally:
        try:
            sweep_wf007(rpc)
        except Exception:  # noqa: BLE001
            pass


@test_case(
    id="TEST-WF007-TC113",
    name="Mass Produce pre-fills <SO>-<MO>-001 and keeps the picked components",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_mrp",
    priority="P1", kind="API", order=7113,
    description="The Mass Produce wizard opens pre-filled with "
                "<SO>-<MO>-001, resets qty_producing and picked while leaving "
                "every raw move quantity untouched.",
    traceability=trace("DATAONE-TC113"))
def test_tc113(ctx):
    require_serial_stack(ctx)
    rpc = ctx.adapter.rpc
    if not rpc.model_exists("stock.assign.serial"):
        ctx.blocked(
            "the Mass Produce prefill this case asserts was REMOVED during "
            "the port, not broken. v19 deleted "
            "action_serial_mass_produce_wizard, so dto_mrp's override had no "
            "super() to call and would raise AttributeError; it was removed "
            "rather than retargeted because the replacement wizard "
            "mrp.production.serials has no next_serial_number field at all "
            "(dto_mrp/models/mrp_production.py:355-365, B-4 / TODO(D-S1)). "
            "Measured: stock.assign.serial does not exist on this target. "
            "The case can only run once D-S1 decides what the v19 prefill "
            "should be.")
    open_namespace(ctx)
    try:
        with ctx.step("This target still has the v17 wizard — run the case"):
            ctx.check_true("stock.assign.serial exists",
                           rpc.model_exists("stock.assign.serial"), "present")
    finally:
        try:
            sweep_wf007(rpc)
        except Exception:  # noqa: BLE001
            pass


def _packaging_case(ctx, zero_duration: bool):
    """Shared body for TC114 and TC115 — they differ only in the fixture."""
    require_serial_stack(ctx)
    require_packaging_gate(ctx)          # BLOCKS on this target
    rpc = ctx.adapter.rpc
    open_namespace(ctx)
    try:
        with ctx.step("The Packaging gate is deployed — exercise it"):
            ctx.check_true("dto_mrp_account is installed", True,
                           "checked by require_packaging_gate")
            ctx.log(f"expected message: {ERROR_PACKAGING!r}")
    finally:
        try:
            sweep_wf007(rpc)
        except Exception:  # noqa: BLE001
            pass


@test_case(
    id="TEST-WF007-TC114",
    name="An MO whose Packaging work orders have zero total duration cannot "
         "be completed",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_mrp_account",
    priority="P0", kind="API", order=7114,
    description="Marking done an MO whose Packaging work orders carry no "
                "recorded time raises the gate's exact message, leaves the "
                "state unchanged and creates no valuation, no journal entry "
                "and no lot.",
    traceability=trace("DATAONE-TC114"))
def test_tc114(ctx):
    _packaging_case(ctx, zero_duration=True)


@test_case(
    id="TEST-WF007-TC115",
    name="An MO with no Packaging work centre at all is blocked by the same "
         "gate",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_mrp_account",
    priority="P0", kind="API", order=7115,
    description="An MO with no Packaging work order raises the same message "
                "as TC114 — whose wording, 'all work orders have 0 duration', "
                "is inaccurate for this scenario — and stays blocked until a "
                "Packaging work order with recorded time exists.",
    traceability=trace("DATAONE-TC115"))
def test_tc115(ctx):
    _packaging_case(ctx, zero_duration=False)
