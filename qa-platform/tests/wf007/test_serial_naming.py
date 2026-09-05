"""DATAONE-WF-007 — how the automatic lot number is built: TC106–TC112.

The naming contract, verified in the source and then measured end to end on
d1v19 before these cases were written:

    pre_button_mark_done()  -> a lot exists, auto_generated=True, named by
                               core (a sequence value when the product has a
                               serial sequence, or <SO>-<MO> from the
                               UserError fallback when it has none)
    button_mark_done()      -> AFTER super, the FIRST auto-generated lot is
                               renamed to _prepare_lot_name()

Measured, on a serial-tracked product with a sequence::

    MO WH-MO-11738, SO S06881
    after pre_button_mark_done : lot name = 202611801   (core's sequence)
    after button_mark_done     : lot name = S06881-11738 , auto_generated=True

That ordering is the whole point of TC106: the lot is created BEFORE
validation under a provisional name, core renames the MO while splitting the
backorder, and the post-``super()`` block corrects the SAME lot record to the
final MO name. Every case below asserts the lot by RECORD ID across that
transition, never by re-searching for a name.

**Observation note carried by TC106 and TC112.** The workbook describes the
provisional name as ``<SO>-<MO>`` at ``pre_button_mark_done`` time. On a
product that HAS a serial sequence, core's
``super()._prepare_stock_lot_values()`` succeeds and returns a sequence value
instead, so ``<SO>-<MO>`` only appears after ``button_mark_done``. The
``<SO>-<MO>`` provisional name is real, but only on the no-sequence branch —
which is exactly what TC112 isolates. Neither expectation is weakened: the
final name is asserted verbatim in both cases.

EXPECTED v19 OUTCOME: PASS.
"""
from framework.registry import test_case
from tests.wf007.common import (WORKFLOW, WORKFLOW_NAME, backorders_of,
                                consume_components, lot_info, lots_for,
                                m2o_id, make_bom, make_mo, make_product,
                                make_sale_order, mark_done,
                                mark_done_with_backorder, mo_digits, mo_field,
                                mo_name, open_namespace, producing_lots,
                                require_serial_stack, set_qty_producing,
                                sweep_wf007, trace)


def _tracked_fixture(rpc, tracking="serial", qty=1.0, with_sale=True):
    """A confirmed MO for a tracked product, optionally linked to a sale order."""
    comp = make_product(rpc, "CMP")
    fg = make_product(rpc, f"FG-{tracking.upper()}", tracking=tracking)
    bom = make_bom(rpc, fg, comp)
    so_name, line_id = "", None
    if with_sale:
        _order, so_name, line_id = make_sale_order(rpc, fg, qty)
    mo = make_mo(rpc, fg, bom, qty=qty, sale_line_id=line_id)
    return comp, fg, bom, so_name, mo


@test_case(
    id="TEST-WF007-TC106",
    name="GATE Backordered MO: the auto-generated lot is renamed to match the "
         "final MO name",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_mrp",
    priority="P0", kind="API", order=7106,
    description="Producing less than the demand splits a backorder; the same "
                "lot record, by id, ends up named <SO>-<final MO name> and "
                "keeps auto_generated True, while a second MO carries the "
                "remaining quantity.",
    traceability=trace("DATAONE-TC106"))
def test_tc106(ctx):
    require_serial_stack(ctx)
    rpc = ctx.adapter.rpc
    open_namespace(ctx)
    try:
        with ctx.step("A lot-tracked MO for 2, linked to a sale order"):
            comp, fg, bom, so_name, mo = _tracked_fixture(
                rpc, tracking="lot", qty=2.0)
            original_name = mo_name(rpc, mo)
            ctx.check("no lot yet", [], producing_lots(rpc, mo))
            ctx.check("the MO can reach its sale order", so_name,
                      (mo_field(rpc, mo, "source_sale_id") or [None, ""])[1])
            ctx.log(f"MO={original_name} SO={so_name}")

        with ctx.step("Produce 1 of the 2, so a backorder will split"):
            set_qty_producing(rpc, mo, 1.0)
            consume_components(rpc, mo, 1.0)
            rpc.call("mrp.production", "pre_button_mark_done", [mo])

        with ctx.step("A lot now exists, auto-generated, and is recorded by id"):
            lots = producing_lots(rpc, mo)
            ctx.check("exactly one producing lot", 1, len(lots))
            lot_id = lots[0]
            info = lot_info(rpc, lot_id)
            ctx.check("auto_generated", True, info["auto_generated"])
            ctx.log(f"provisional lot name = {info['name']!r}")

        with ctx.step("Complete, creating a backorder"):
            action = mark_done_with_backorder(rpc, mo)
            ctx.check("Mark as Done offered the backorder dialog",
                      "mrp.production.backorder", action.get("res_model"))

        with ctx.step("The MO was renamed by the split"):
            final_name = mo_name(rpc, mo)
            ctx.check_true("the MO name gained a split suffix",
                           final_name != original_name
                           and final_name.startswith(original_name),
                           f"{original_name!r} -> {final_name!r}")

        with ctx.step("A backorder carries the remaining quantity"):
            others = backorders_of(rpc, mo)
            ctx.check_true("a backorder MO exists", len(others) >= 1,
                           str([o["name"] for o in others]))
            if others:
                ctx.check("it carries the remaining 1", [1.0],
                          [o["product_qty"] for o in others[:1]])
                ctx.check_true("it is still open",
                               others[0]["state"] in ("confirmed", "progress"),
                               others[0]["state"])

        with ctx.step("The SAME lot record was renamed to the final MO name"):
            final_name = mo_name(rpc, mo)
            expected = f"{so_name}-{mo_digits(final_name)}"
            ctx.check("lot name, by record id", expected,
                      lot_info(rpc, lot_id)["name"])
            ctx.check("auto_generated is still True", True,
                      lot_info(rpc, lot_id)["auto_generated"])
    finally:
        try:
            sweep_wf007(rpc)
        except Exception:  # noqa: BLE001
            pass


@test_case(
    id="TEST-WF007-TC107",
    name="An operator-typed lot number is never renamed",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_mrp",
    priority="P0", kind="API", order=7107,
    description="A lot the operator created carries auto_generated False and "
                "survives a backorder split verbatim, while the MO around it "
                "is renamed; a copy of that lot does not inherit the flag.",
    traceability=trace("DATAONE-TC107"))
def test_tc107(ctx):
    """Step 7 combined with step 8 is the case: without the MO actually being
    renamed the test would be vacuous, because a lot on an un-renamed MO
    would be left alone anyway. Both halves are asserted.
    """
    require_serial_stack(ctx)
    rpc = ctx.adapter.rpc
    open_namespace(ctx)
    try:
        with ctx.step("An MO for 2 with an operator-typed lot number"):
            comp, fg, bom, so_name, mo = _tracked_fixture(
                rpc, tracking="lot", qty=2.0)
            original_name = mo_name(rpc, mo)
            typed = "OPERATOR-MANUAL-01"
            lot_id = rpc.create("stock.lot", {"name": typed, "product_id": fg})
            rpc.write("mrp.production", [mo], {"lot_producing_ids": [(6, 0, [lot_id])]})
            ctx.check("the MO carries the operator's lot", [lot_id],
                      producing_lots(rpc, mo))

        with ctx.step("It was not created by the override"):
            ctx.check("auto_generated is False", False,
                      lot_info(rpc, lot_id)["auto_generated"])

        with ctx.step("Produce 1 of 2 and complete, creating a backorder"):
            set_qty_producing(rpc, mo, 1.0)
            consume_components(rpc, mo, 1.0)
            rpc.call("mrp.production", "pre_button_mark_done", [mo])
            mark_done_with_backorder(rpc, mo)

        with ctx.step("The MO was renamed"):
            final_name = mo_name(rpc, mo)
            ctx.check_true("the MO name changed", final_name != original_name,
                           f"{original_name!r} -> {final_name!r}")

        with ctx.step("The lot was not renamed — verbatim, no suffix"):
            ctx.check("lot name", typed, lot_info(rpc, lot_id)["name"])
            ctx.check("auto_generated is still False", False,
                      lot_info(rpc, lot_id)["auto_generated"])

        with ctx.step("No additional lot was created for this MO"):
            ctx.check("producing lots", [lot_id], producing_lots(rpc, mo))
            ctx.check("lots for the product", 1, len(lots_for(rpc, fg)))

        with ctx.step("A duplicated lot does not inherit the flag (copy=False)"):
            copy_id = rpc.call("stock.lot", "copy", [lot_id])
            copy_id = copy_id[0] if isinstance(copy_id, list) else copy_id
            ctx.check("the copy's auto_generated", False,
                      lot_info(rpc, copy_id)["auto_generated"])
    finally:
        try:
            sweep_wf007(rpc)
        except Exception:  # noqa: BLE001
            pass


@test_case(
    id="TEST-WF007-TC108",
    name="An MO with no reachable sale order is numbered with the bare MO "
         "digits",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_mrp",
    priority="P1", kind="API", order=7108,
    description="With no sale order reachable the lot is named with the MO's "
                "digits alone — no prefix, no separator, no trailing dash — "
                "and the MO name is unchanged when the run completes in full.",
    traceability=trace("DATAONE-TC108"))
def test_tc108(ctx):
    """Step 9 of the workbook asks for one behaviour to be recorded verbatim:
    ``_prepare_lot_name`` does ``index = re.search(r"\\d", self.name)`` and
    then uses ``index.start()`` guarded only by ``if index``. An MO name with
    no digit at all therefore falls back to the WHOLE name rather than
    raising — the fallback is present, so the unguarded ``.start()`` is never
    reached. ``common.mo_digits()`` mirrors that exactly, and the assertion
    below is computed through it.
    """
    require_serial_stack(ctx)
    rpc = ctx.adapter.rpc
    open_namespace(ctx)
    try:
        with ctx.step("An MO with no sale order behind it"):
            comp, fg, bom, _so, mo = _tracked_fixture(
                rpc, tracking="lot", qty=1.0, with_sale=False)
            original_name = mo_name(rpc, mo)
            ctx.check("source_sale_id is empty", False,
                      mo_field(rpc, mo, "source_sale_id"))

        with ctx.step("Complete it in full"):
            set_qty_producing(rpc, mo, 1.0)
            consume_components(rpc, mo)
            mark_done(rpc, mo)

        with ctx.step("The lot is named with the bare MO digits"):
            lots = producing_lots(rpc, mo)
            ctx.check("exactly one producing lot", 1, len(lots))
            expected = mo_digits(original_name)
            ctx.check("lot name", expected, lot_info(rpc, lots[0])["name"])
            ctx.check_true("no leading dash", not expected.startswith("-"),
                           expected)
            ctx.check_true("no trailing dash", not expected.endswith("-"),
                           expected)

        with ctx.step("auto_generated is True and the MO name is unchanged"):
            lots = producing_lots(rpc, mo)
            ctx.check("auto_generated", True,
                      lot_info(rpc, lots[0])["auto_generated"])
            ctx.check("the MO was not renamed — no backorder split",
                      original_name, mo_name(rpc, mo))
    finally:
        try:
            sweep_wf007(rpc)
        except Exception:  # noqa: BLE001
            pass


@test_case(
    id="TEST-WF007-TC110",
    name="The lot branch and the serial branch both produce a <SO>-<MO> "
         "number, and an untracked MO produces none",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_mrp",
    priority="P1", kind="API", order=7110,
    description="A serial-tracked run of 1 and a lot-tracked run of 3 both "
                "produce exactly one auto-generated lot named <SO>-<MO "
                "digits>; an untracked MO produces no lot at all, which is "
                "eligibility condition 1.",
    traceability=trace("DATAONE-TC110"))
def test_tc110(ctx):
    require_serial_stack(ctx)
    rpc = ctx.adapter.rpc
    open_namespace(ctx)
    try:
        with ctx.step("Serial branch: a run of 1"):
            _c, fg_s, _b, so_s, mo_s = _tracked_fixture(
                rpc, tracking="serial", qty=1.0)
            name_s = mo_name(rpc, mo_s)
            set_qty_producing(rpc, mo_s, 1.0)
            consume_components(rpc, mo_s)
            mark_done(rpc, mo_s)
            lots = producing_lots(rpc, mo_s)
            ctx.check("one lot", 1, len(lots))
            if lots:
                info = lot_info(rpc, lots[0])
                ctx.check("serial lot name", f"{so_s}-{mo_digits(name_s)}",
                          info["name"])
                ctx.check("auto_generated", True, info["auto_generated"])

        with ctx.step("Lot branch: one lot for a whole run of 3"):
            _c, fg_l, _b, so_l, mo_l = _tracked_fixture(
                rpc, tracking="lot", qty=3.0)
            name_l = mo_name(rpc, mo_l)
            set_qty_producing(rpc, mo_l, 3.0)
            consume_components(rpc, mo_l)
            mark_done(rpc, mo_l)
            lots = producing_lots(rpc, mo_l)
            ctx.check("exactly one lot for the whole run", 1, len(lots))
            if lots:
                info = lot_info(rpc, lots[0])
                ctx.check("lot name", f"{so_l}-{mo_digits(name_l)}",
                          info["name"])
                ctx.check("auto_generated", True, info["auto_generated"])
            ctx.check("only one lot exists for the product", 1,
                      len(lots_for(rpc, fg_l)))

        with ctx.step("Untracked branch: nothing at all"):
            _c, fg_n, _b, _so, mo_n = _tracked_fixture(
                rpc, tracking="none", qty=1.0)
            set_qty_producing(rpc, mo_n, 1.0)
            consume_components(rpc, mo_n)
            mark_done(rpc, mo_n)
            ctx.check("no producing lot", [], producing_lots(rpc, mo_n))
            ctx.check("no lot was created for the product", 0,
                      len(lots_for(rpc, fg_n)))
    finally:
        try:
            sweep_wf007(rpc)
        except Exception:  # noqa: BLE001
            pass


@test_case(
    id="TEST-WF007-TC111",
    name="v19 SILENT A serial-tracked MO with product_qty > 1 still creates "
         "and attaches a lot",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_mrp",
    priority="P0", kind="API", order=7111,
    description="A serial-tracked MO for 3 reaches done AND has a lot "
                "attached; reaching done alone is what would make a failure "
                "here silent, so the attachment is asserted separately.",
    traceability=trace("DATAONE-TC111"))
def test_tc111(ctx):
    """EXPECTED v19 OUTCOME: FAIL — and the failure is the finding this case
    exists to catch.

    Measured on d1v19, serial-tracked product, ``product_qty`` 3, components
    consumed, ``qty_producing`` 3::

        after mark_done:  state = 'to_close'   lot_producing_ids = []

    Neither half of the expectation holds: no lot is created and the MO does
    not reach ``done``. ``_eligible_for_auto_generate_serial()`` passes all
    four of its conditions here, so the shortfall is downstream — v19 routes
    a serial-tracked MO through ``mrp.action_assign_serial_numbers`` and the
    replacement wizard ``mrp.production.serials``
    (dto_mrp/models/mrp_production.py:355-365, B-4 / TODO(D-S1)), which needs
    one serial PER UNIT rather than one lot for the run. With three units and
    no serials assigned the MO stays ``to_close``.

    The workbook anticipated exactly this shape — "On an unported v19: step 6
    passes, step 7 fails. That divergence is the entire purpose of the case."
    Here even step 6 fails, which is a stronger signal, so both are asserted
    separately below and neither is softened (AUTOMATION_CONVENTIONS hard
    rule 2). This is the multi-lot question the source defers to TODO(D-S2).
    """
    require_serial_stack(ctx)
    rpc = ctx.adapter.rpc
    open_namespace(ctx)
    try:
        with ctx.step("A serial-tracked MO for 3 — meaningless on quantity 1"):
            _c, fg, _b, so_name, mo = _tracked_fixture(
                rpc, tracking="serial", qty=3.0)
            ctx.check("product tracking", "serial",
                      rpc.read("product.product", [fg], ["tracking"])[0]["tracking"])
            ctx.check("product_qty", 3.0, mo_field(rpc, mo, "product_qty"))
            ctx.check("no lot yet", [], producing_lots(rpc, mo))
            lots_before = len(lots_for(rpc, fg))

        with ctx.step("Produce the full quantity and complete"):
            set_qty_producing(rpc, mo, 3.0)
            consume_components(rpc, mo)
            mark_done(rpc, mo)

        with ctx.step("The MO reached done"):
            ctx.check("state", "done", mo_field(rpc, mo, "state"))

        with ctx.step("AND a lot is attached — the assertion that is not silent"):
            lots = producing_lots(rpc, mo)
            ctx.check_true("lot_producing_ids is not empty", bool(lots),
                           str(lots))
            ctx.check_true("more lots exist than before",
                           len(lots_for(rpc, fg)) > lots_before,
                           f"{lots_before} -> {len(lots_for(rpc, fg))}")
            if lots:
                ctx.check("auto_generated", True,
                          lot_info(rpc, lots[0])["auto_generated"])
    finally:
        try:
            sweep_wf007(rpc)
        except Exception:  # noqa: BLE001
            pass


@test_case(
    id="TEST-WF007-TC112",
    name="With no serial sequence on the product, the UserError fallback "
         "produces the DataOne convention",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_mrp",
    priority="P1", kind="API", order=7112,
    description="A product with no serial sequence takes the UserError "
                "fallback branch of _prepare_stock_lot_values: no exception "
                "reaches the caller, a lot is created named <SO>-<MO digits>, "
                "and auto_generated is stamped True on both branches.",
    traceability=trace("DATAONE-TC112"))
def test_tc112(ctx):
    """This is the case where the workbook's "provisional <SO>-<MO> name at
    pre_button_mark_done" is literally true: with no sequence, core's
    ``super()._prepare_stock_lot_values()`` raises UserError, the override
    catches it and builds the name from ``_prepare_lot_name()`` itself. On a
    product that HAS a sequence the provisional name is core's sequence value
    instead, and ``<SO>-<MO>`` only appears after ``button_mark_done`` —
    measured, and noted in this module's docstring.
    """
    require_serial_stack(ctx)
    rpc = ctx.adapter.rpc
    open_namespace(ctx)
    try:
        with ctx.step("A tracked product with no serial sequence"):
            _c, fg, _b, so_name, mo = _tracked_fixture(
                rpc, tracking="lot", qty=1.0)
            for field in ("lot_sequence_id", "serial_prefix_format"):
                if rpc.field_exists("product.product", field):
                    rpc.write("product.product", [fg], {field: False})
            name = mo_name(rpc, mo)
            ctx.log(f"MO={name} SO={so_name}")

        with ctx.step("pre_button_mark_done does not raise"):
            set_qty_producing(rpc, mo, 1.0)
            error = ""
            try:
                rpc.call("mrp.production", "pre_button_mark_done", [mo])
            except Exception as exc:  # noqa: BLE001 — any escape is the failure
                error = str(exc)
            ctx.check_true("no exception reached the caller", not error,
                           error[:200] or "no error")

        with ctx.step("A lot was created and stamped auto_generated"):
            lots = producing_lots(rpc, mo)
            ctx.check("exactly one lot", 1, len(lots))
            if lots:
                ctx.check("auto_generated", True,
                          lot_info(rpc, lots[0])["auto_generated"])
                ctx.log(f"provisional name = {lot_info(rpc, lots[0])['name']!r}")

        with ctx.step("Completing gives the DataOne convention"):
            consume_components(rpc, mo)
            mark_done(rpc, mo)
            lots = producing_lots(rpc, mo)
            final_name = mo_name(rpc, mo)
            ctx.check("lot name", f"{so_name}-{mo_digits(final_name)}",
                      lot_info(rpc, lots[0])["name"] if lots else None)
            ctx.check("auto_generated survives the rename", True,
                      lot_info(rpc, lots[0])["auto_generated"] if lots else None)
    finally:
        try:
            sweep_wf007(rpc)
        except Exception:  # noqa: BLE001
            pass
