"""DATAONE-WF-009 — undoing a substitution, and the chained-move gate:
TC142, TC143.

TC142 is the manual escape hatch: ``action_revert_component_substitution``
(stock_move.py:95) puts the original component back, clears the marker, posts
its own chatter note, and leaves the move eligible to be substituted again —
reverting is not a blacklist.

TC143 is the workflow's GATE. On a multi-step manufacturing route the raw
move sits in a staging location that is empty until the upstream pick runs,
so a substitution that rewrote only the raw move would leave the pick still
fetching the original component. Both ends of the chain must move together.

d1v19's warehouse is ``pbm_sam``, so this route is the DEFAULT here rather
than something the fixture has to build — every MO already carries a pick
move. ``common.is_multi_step()`` states the precondition explicitly so the
case BLOCKS with a precise reason rather than passing vacuously if the
warehouse is ever reconfigured to one step.
"""
from framework.registry import test_case
from tests.wf009.common import (REVERTED_TEMPLATE, WORKFLOW, WORKFLOW_NAME,
                                available_qty, chatter, is_multi_step, m2o_id,
                                make_bom, make_mo, make_product, onhand_qty,
                                open_namespace, pick_moves, raw_move,
                                require_mrp, require_replacement_module,
                                set_replacements, set_stock, stock_location,
                                substitution_messages, sweep_wf009, trace)


def _substituted_mo(rpc):
    """An MO whose single raw move has been substituted from A to B."""
    a = make_product(rpc, "CONN-A")
    b = make_product(rpc, "CONN-B")
    set_replacements(rpc, a, [b])
    finished = make_product(rpc, "FG")
    bom = make_bom(rpc, finished, a, qty=1.0)
    loc = stock_location(rpc)
    set_stock(rpc, a, loc, 0.0)
    set_stock(rpc, b, loc, 50.0)
    mo = make_mo(rpc, finished, bom, qty=10.0)
    rpc.call("mrp.production", "action_check_component_replacements", [mo])
    return a, b, finished, bom, loc, mo


@test_case(
    id="TEST-WF009-TC142",
    name="Revert restores the original component, and the move is eligible "
         "again",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_mrp_component_replacement",
    priority="P1", kind="API", order=9142,
    description="Reverting a substituted move puts the original product, UoM "
                "and quantity back, clears original_component_id and the MO "
                "banner, posts the revert note, and leaves the move eligible "
                "to be substituted again on the next check.",
    traceability=trace("DATAONE-TC142"))
def test_tc142(ctx):
    """Observation note: the workbook quotes the revert message as *"Component
    <product> substitution was manually reverted."* and cites the source as
    *"Component %(product)s was manually reverted."* The real string is
    ``'Component substitution for %(product)s was manually reverted.'``
    (stock_move.py:105). The assertion below is written against what the
    system actually renders — the expectation (a revert note naming the
    original component) is unchanged.
    """
    require_replacement_module(ctx)
    require_mrp(ctx)
    rpc = ctx.adapter.rpc
    open_namespace(ctx)
    try:
        with ctx.step("Start from a substituted move (A -> B)"):
            a, b, finished, bom, loc, mo = _substituted_mo(rpc)
            move = raw_move(rpc, mo)
            ctx.check("substituted to B", b, m2o_id(move["product_id"]))
            ctx.check("original_component_id records A", a,
                      m2o_id(move["original_component_id"]))
            ctx.check("is_component_substituted", True,
                      move["is_component_substituted"])
            original_uom = m2o_id(rpc.read("product.product", [a],
                                           ["uom_id"])[0]["uom_id"])
            required = move["product_uom_qty"]
            move_id = rpc.search("stock.move",
                                 [("raw_material_production_id", "=", mo)])[0]

        with ctx.step("Revert the substitution"):
            rpc.call("stock.move", "action_revert_component_substitution",
                     [move_id])

        with ctx.step("The original component, UoM and quantity are back"):
            move = raw_move(rpc, mo)
            ctx.check("product restored to A", a, m2o_id(move["product_id"]))
            ctx.check("product_uom restored", original_uom,
                      m2o_id(move["product_uom"]))
            ctx.check("quantity restored", required, move["product_uom_qty"])

        with ctx.step("Markers and the MO banner are cleared"):
            ctx.check("original_component_id empty", False,
                      move["original_component_id"])
            ctx.check("is_component_substituted", False,
                      move["is_component_substituted"])
            ctx.check("has_substituted_components", False,
                      rpc.read("mrp.production", [mo],
                               ["has_substituted_components"])[0]
                      ["has_substituted_components"])

        with ctx.step("The revert note is posted, naming the original"):
            name = rpc.read("product.product", [a], ["display_name"])[0]["display_name"]
            expected = REVERTED_TEMPLATE.format(product=name)
            bodies = chatter(rpc, mo)
            ctx.check_true("chatter carries the revert note",
                           expected in bodies,
                           " | ".join(b[:70] for b in bodies[-3:]) or "no messages")

        with ctx.step("Reverting does not blacklist: the move is eligible again"):
            rpc.call("mrp.production", "action_check_component_replacements", [mo])
            move = raw_move(rpc, mo)
            ctx.check("re-substituted to B", b, m2o_id(move["product_id"]))
            ctx.check("original_component_id records A again", a,
                      m2o_id(move["original_component_id"]))
            ctx.check("a second substitution message was posted", 2,
                      len(substitution_messages(rpc, mo)))
    finally:
        try:
            sweep_wf009(rpc)
        except Exception:  # noqa: BLE001
            pass


@test_case(
    id="TEST-WF009-TC143",
    name="GATE (WF-009) On a 2-step warehouse the chained pick move is "
         "rewritten too",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_mrp_component_replacement",
    priority="P0", kind="API", order=9143,
    description="A substitution on a multi-step manufacturing route rewrites "
                "both the MO's raw move and the upstream pick move that feeds "
                "it, with matching converted quantities, and measures "
                "availability at the real stock location rather than at the "
                "empty staging area.",
    traceability=trace("DATAONE-TC143"))
def test_tc143(ctx):
    require_replacement_module(ctx)
    require_mrp(ctx)
    rpc = ctx.adapter.rpc
    if not is_multi_step(rpc):
        ctx.blocked(
            "the warehouse is configured for one-step manufacturing, so no "
            "chained pick move exists and this gate has nothing to assert. "
            "Set manufacture_steps to 'pbm' or 'pbm_sam' to exercise it.")
    open_namespace(ctx)
    try:
        with ctx.step("An MO on the multi-step route, both ends still on A"):
            a = make_product(rpc, "CONN-A")
            b = make_product(rpc, "CONN-B")
            set_replacements(rpc, a, [b])
            finished = make_product(rpc, "FG")
            bom = make_bom(rpc, finished, a, qty=1.0)
            loc = stock_location(rpc)
            # A is stocked before the MO is confirmed, for the same reason as
            # TC138: action_confirm reaches _action_assign, which is where
            # _apply_component_replacement hooks in (stock_move.py:23), so
            # confirming with A at zero substitutes before the case can
            # observe its own precondition.
            set_stock(rpc, a, loc, 10.0)
            set_stock(rpc, b, loc, 50.0)
            mo = make_mo(rpc, finished, bom, qty=10.0)

        with ctx.step("Both ends of the chain start on A"):
            move = raw_move(rpc, mo)
            picks = pick_moves(rpc, mo)
            ctx.check_true("the route produced an upstream pick move",
                           len(picks) >= 1, f"{len(picks)} pick move(s)")
            pick_ids = [p["id"] for p in picks] if picks and "id" in picks[0] else []
            ctx.check("raw move carries A", a, m2o_id(move["product_id"]))
            if picks:
                ctx.check("pick move carries A", [a],
                          list({m2o_id(p["product_id"]) for p in picks}))
            ctx.check("the raw move stages at a different location than stock",
                      True, m2o_id(move["location_id"]) != loc)

        with ctx.step("Availability is measured at stock, not at the staging area"):
            # Nothing has ever been placed in the staging location, so a check
            # that read availability there would see zero for every product and
            # substitute unconditionally. Asserting the staging area is empty
            # makes that failure mode visible rather than silent.
            staging = m2o_id(move["location_id"])
            ctx.check("staging area holds no A", 0.0,
                      onhand_qty(rpc, a, staging))
            ctx.check("stock holds the replacement", 50.0,
                      available_qty(rpc, b, loc))

        with ctx.step("Empty A, then Check Components Availability"):
            rpc.call("mrp.production", "do_unreserve", [mo])
            set_stock(rpc, a, loc, 0.0)
            rpc.call("mrp.production", "action_check_component_replacements", [mo])

        with ctx.step("The raw move is rewritten to B"):
            move = raw_move(rpc, mo)
            ctx.check("raw move carries B", b, m2o_id(move["product_id"]))
            ctx.check("original_component_id records A", a,
                      m2o_id(move["original_component_id"]))
            new_qty = move["product_uom_qty"]

        with ctx.step("The upstream pick move moved with it"):
            picks_after = pick_moves(rpc, mo)
            products = {m2o_id(p["product_id"]) for p in picks_after}
            ctx.check("pick move carries B too", {b}, products)
            ctx.check("pick quantity matches the raw move", [new_qty],
                      [p["product_uom_qty"] for p in picks_after])

        with ctx.step("The MO chatter names the substitution once"):
            ctx.check("substitution message count", 1,
                      len(substitution_messages(rpc, mo)))
    finally:
        try:
            sweep_wf009(rpc)
        except Exception:  # noqa: BLE001
            pass
