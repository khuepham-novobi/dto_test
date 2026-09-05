"""DATAONE-WF-025 — the Available column's two rules: TC146, TC147.

Both cases are the same expression, read from
``dto_mrp/models/product_product.py:14-18``::

    stock_quants = search([('product_id', '=', product.id),
                           ('location_id.ignore_quantities_for_gross_report', '=', False),
                           ('location_id.usage', '=', 'internal'),
                           ('on_hand', '=', True)])
    quantity_available_in_stock = (
        sum(stock_quants.mapped('inventory_quantity_auto_apply'))
        - sum(stock_quants.filtered(lambda sq: sq.location_id.name != 'Input')
                          .mapped('reserved_quantity')))

TC146 is the first filter: a location flagged *Ignore Quantities for Gross
Report* drops out of the sum entirely, quantity and reservation alike.

TC147 is the second: reservations are subtracted everywhere EXCEPT where the
location's **name** is exactly ``Input``. The rule keys on the name, not on
an id or a flag, so it applies to every location called Input and stops
applying the moment one is renamed. The workbook calls that out deliberately
— "the behaviour follows the name, not the location" — and step 9 is
explicitly a failing-by-design observation that a rename silently alters
every availability figure. It is asserted here as a fact about the system,
because it IS the system's behaviour; it is not an expectation being
weakened.

EXPECTED v19 OUTCOME: PASS for both. Fixtures use their own namespaced
locations so no live location is created, flagged or renamed.
"""
from framework.registry import test_case
from tests.wf025.common import (INPUT_LOCATION_NAME, WORKFLOW, WORKFLOW_NAME,
                                add_finished_good, add_stock, component_for,
                                make_bom, make_location, make_product,
                                new_report, open_namespace, release,
                                require_gross_report, reserve, run_report,
                                stock_location, sweep_wf025, trace)


def _fixture(rpc):
    """A finished good consuming one unit of a component, plus a report."""
    comp = make_product(rpc, "CMP-A")
    fg = make_product(rpc, "FG-1")
    make_bom(rpc, fg, [(comp, 1.0)])
    return comp, fg


def _available(rpc, comp, fg, qty=1.0):
    """Run a fresh report and return the component's Available figure."""
    report = new_report(rpc)
    add_finished_good(rpc, report, fg, qty)
    run_report(rpc, report)
    row = component_for(rpc, report, comp)
    return None if row is None else row["qty_available"]


@test_case(
    id="TEST-WF025-TC146",
    name="Availability excludes locations flagged \"Ignore Quantities for "
         "Gross Report\"",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_mrp",
    priority="P0", kind="API", order=25146,
    description="With 100 in a normal location and 40 in a second, Available "
                "is 140; ticking Ignore Quantities for Gross Report on the "
                "second drops it to 100; unticking restores 140.",
    traceability=trace("DATAONE-TC146"))
def test_tc146(ctx):
    require_gross_report(ctx)
    rpc = ctx.adapter.rpc
    open_namespace(ctx)
    try:
        with ctx.step("Stock 100 in a normal location and 40 in a second"):
            comp, fg = _fixture(rpc)
            parent = stock_location(rpc)
            loc_normal = make_location(rpc, "L-NORMAL", parent_id=parent)
            loc_second = make_location(rpc, "L-SECOND", parent_id=parent,
                                       ignore_for_gross=False)
            add_stock(rpc, comp, loc_normal, 100.0)
            add_stock(rpc, comp, loc_second, 40.0)
            ctx.check("the second location starts unflagged", False,
                      rpc.read("stock.location", [loc_second],
                               ["ignore_quantities_for_gross_report"])[0]
                      ["ignore_quantities_for_gross_report"])

        with ctx.step("Available counts both locations"):
            ctx.check("Available = 100 + 40", 140.0, _available(rpc, comp, fg))

        with ctx.step("Tick Ignore Quantities for Gross Report on the second"):
            rpc.write("stock.location", [loc_second],
                      {"ignore_quantities_for_gross_report": True})
            ctx.check("Available drops to the unflagged location only", 100.0,
                      _available(rpc, comp, fg))

        with ctx.step("Unticking restores the full figure"):
            rpc.write("stock.location", [loc_second],
                      {"ignore_quantities_for_gross_report": False})
            ctx.check("Available is 140 again", 140.0,
                      _available(rpc, comp, fg))
    finally:
        try:
            sweep_wf025(rpc)
        except Exception:  # noqa: BLE001
            pass


@test_case(
    id="TEST-WF025-TC147",
    name="Reserved quantity is subtracted everywhere except in a location "
         "named Input",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_mrp",
    priority="P0", kind="API", order=25147,
    description="A reservation in a normal location reduces Available; the "
                "same reservation in a location named Input does not; the "
                "rule applies to every location with that name; renaming it "
                "makes the reservation count again.",
    traceability=trace("DATAONE-TC147"))
def test_tc147(ctx):
    require_gross_report(ctx)
    rpc = ctx.adapter.rpc
    open_namespace(ctx)
    try:
        with ctx.step("50 in a normal location and 50 in one named Input"):
            comp, fg = _fixture(rpc)
            parent = stock_location(rpc)
            loc_normal = make_location(rpc, "L-NORMAL", parent_id=parent)
            # Named literally 'Input' — that exact string is what the rule
            # keys on (product_product.py:18).
            loc_input = make_location(rpc, "L-INPUT", parent_id=parent,
                                      name=INPUT_LOCATION_NAME)
            add_stock(rpc, comp, loc_normal, 50.0)
            add_stock(rpc, comp, loc_input, 50.0)
            ctx.check("Available with nothing reserved", 100.0,
                      _available(rpc, comp, fg))

        with ctx.step("Reserve 20 in the normal location and 50 in Input"):
            hold_normal = reserve(rpc, comp, loc_normal, 20.0)
            hold_input = reserve(rpc, comp, loc_input, 50.0)
            ctx.check("only the normal reservation is subtracted", 80.0,
                      _available(rpc, comp, fg))

        with ctx.step("Releasing the normal reservation restores it"):
            release(rpc, hold_normal)
            ctx.check("Available is 100 again", 100.0,
                      _available(rpc, comp, fg))

        with ctx.step("Releasing the Input reservation changes nothing"):
            hold_normal = reserve(rpc, comp, loc_normal, 20.0)
            release(rpc, hold_input)
            ctx.check("still 80 — the Input reservation was never subtracted",
                      80.0, _available(rpc, comp, fg))

        with ctx.step("The rule applies to every location named Input"):
            hold_input = reserve(rpc, comp, loc_input, 50.0)
            loc_input2 = make_location(rpc, "L-INPUT2", parent_id=parent,
                                       name=INPUT_LOCATION_NAME)
            add_stock(rpc, comp, loc_input2, 30.0)
            hold_input2 = reserve(rpc, comp, loc_input2, 30.0)
            ctx.check("the second Input's reservation is not subtracted either",
                      110.0, _available(rpc, comp, fg))

        with ctx.step("Renaming Input to Inbound makes its reservation count"):
            # The workbook flags this as failing-by-design: it documents that
            # a rename silently alters every availability figure.
            rpc.write("stock.location", [loc_input], {"name": "Inbound"})
            ctx.check("Available falls by the now-counted 50", 60.0,
                      _available(rpc, comp, fg))

        with ctx.step("Renaming it back restores the original figure"):
            rpc.write("stock.location", [loc_input],
                      {"name": INPUT_LOCATION_NAME})
            ctx.check("Available is 110 again", 110.0,
                      _available(rpc, comp, fg))
            release(rpc, hold_normal)
            release(rpc, hold_input)
            release(rpc, hold_input2)
    finally:
        try:
            sweep_wf025(rpc)
        except Exception:  # noqa: BLE001
            pass
