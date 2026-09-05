"""DATAONE-WF-009 — the substitution decision itself: TC138–TC141.

These four cases pin the rule in ``stock.move._apply_component_replacement``
(stock_move.py:29-92), read out of the v19 source before they were written:

    already_reserved + available >= required  ->  no substitution at all
    otherwise, walk candidates in group-sequence order and take the FIRST one
    whose own available quantity alone covers the requirement, converted into
    that candidate's UoM; skip any candidate whose UoM has no common
    reference with the move's.

TC138 is the positive case, TC139 the coverage boundary, TC140 the "no single
candidate covers" case, TC141 the UoM skip.

**Where availability is measured matters here.** d1v19's warehouse is
``pbm_sam``, so a raw move's own location is the WH/Pre-Production staging
area, which is empty until the pick completes.
``_get_replacement_source_location`` (stock_move.py:123) walks to the oldest
still-open ancestor and measures at ITS location — WH/Stock. Every fixture
below stocks WH/Stock for that reason, and ``common.stock_location()``
carries the note.

EXPECTED v19 OUTCOME: PASS for all four. This is ported code whose contract
the port preserved; a failure here is a real Stage-3 regression, which is why
the KEEP list calls this suite the Stage-3 smoke test.
"""
from framework.registry import test_case
from tests.wf009.common import (SUBSTITUTED_TEMPLATE, WORKFLOW, WORKFLOW_NAME,
                                available_qty, m2o_id, make_bom, make_mo,
                                make_product, open_namespace, raw_move,
                                require_mrp, require_replacement_module,
                                set_replacements, set_stock, stock_location,
                                onhand_qty, substitution_messages,
                                sweep_wf009, trace, uom_is_convertible,
                                uom_unit)


def _clique(rpc):
    """A, B, C interchangeable in sequence order, plus a finished good+BoM."""
    a = make_product(rpc, "CONN-A")
    b = make_product(rpc, "CONN-B")
    c = make_product(rpc, "CONN-C")
    set_replacements(rpc, a, [b, c])
    finished = make_product(rpc, "FG")
    bom = make_bom(rpc, finished, a, qty=1.0)
    return a, b, c, finished, bom


def _expected_message(rpc, original, qty, available, new):
    def name(pid):
        return rpc.read("product.product", [pid], ["display_name"])[0]["display_name"]
    return SUBSTITUTED_TEMPLATE.format(
        original=name(original), qty=qty, available=available, new=name(new))


@test_case(
    id="TEST-WF009-TC138",
    name="A shortage substitutes the first candidate that alone covers the "
         "requirement, and says so in the chatter",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_mrp_component_replacement",
    priority="P0", kind="API", order=9138,
    description="With A at zero and both B and C able to cover, the raw move "
                "is rewritten to B — the first in sequence order — with the "
                "UoM-converted quantity, original_component_id set to A, "
                "is_component_substituted true, the MO banner on, and exactly "
                "one chatter message naming the four recorded values. A "
                "second check changes nothing.",
    traceability=trace("DATAONE-TC138"))
def test_tc138(ctx):
    require_replacement_module(ctx)
    require_mrp(ctx)
    rpc = ctx.adapter.rpc
    open_namespace(ctx)
    try:
        with ctx.step("Build the clique and an MO needing 10 of A"):
            a, b, c, finished, bom = _clique(rpc)
            loc = stock_location(rpc)
            # A is stocked FIRST so confirming the MO does not substitute.
            # Observation, not an expectation change: the workbook's
            # precondition is "MO confirmed, raw move still on A, marker
            # empty", but on v19 action_confirm reaches _action_assign, which
            # is where _apply_component_replacement hooks in
            # (stock_move.py:23). Confirming with A at zero therefore
            # substitutes immediately and the precondition can never be
            # observed. Stocking A, confirming, then emptying A reaches the
            # exact state the case describes, and every assertion about what
            # the BUTTON does is unchanged.
            set_stock(rpc, a, loc, 10.0)
            set_stock(rpc, b, loc, 50.0)
            set_stock(rpc, c, loc, 50.0)
            mo = make_mo(rpc, finished, bom, qty=10.0)

        with ctx.step("The raw move starts on A with no substitution marker"):
            move = raw_move(rpc, mo)
            ctx.check("raw move product", a, m2o_id(move["product_id"]))
            ctx.check("original_component_id starts empty", False,
                      move["original_component_id"])
            required = move["product_uom_qty"]

        with ctx.step("Empty A, so the component is now short"):
            rpc.call("mrp.production", "do_unreserve", [mo])
            set_stock(rpc, a, loc, 0.0)
            available = available_qty(rpc, a, loc)
            ctx.check("A is short", 0.0, available)
            ctx.log(f"required={required} available_of_A={available}")

        with ctx.step("Check Components Availability"):
            rpc.call("mrp.production", "action_check_component_replacements", [mo])

        with ctx.step("The first covering candidate in sequence order wins"):
            move = raw_move(rpc, mo)
            ctx.check("substituted to B, not C", b, m2o_id(move["product_id"]))
            ctx.check("original_component_id records A", a,
                      m2o_id(move["original_component_id"]))
            ctx.check("is_component_substituted", True,
                      move["is_component_substituted"])
            ctx.check("quantity carried over in the new UoM", required,
                      move["product_uom_qty"])
            ctx.check("product_uom rewritten to B's UoM",
                      m2o_id(rpc.read("product.product", [b], ["uom_id"])[0]["uom_id"]),
                      m2o_id(move["product_uom"]))

        with ctx.step("The MO banner turns on"):
            mo_rec = rpc.read("mrp.production", [mo],
                              ["has_substituted_components"])[0]
            ctx.check("has_substituted_components", True,
                      mo_rec["has_substituted_components"])

        with ctx.step("Exactly one chatter message, with the recorded values"):
            msgs = substitution_messages(rpc, mo)
            ctx.check("substitution message count", 1, len(msgs))
            if msgs:
                expected = _expected_message(rpc, a, required, available, b)
                ctx.check("rendered chatter body", expected, msgs[0])

        with ctx.step("A second check re-substitutes nothing and posts nothing"):
            rpc.call("mrp.production", "action_check_component_replacements", [mo])
            again = raw_move(rpc, mo)
            ctx.check("still on B", b, m2o_id(again["product_id"]))
            ctx.check("original_component_id unchanged", a,
                      m2o_id(again["original_component_id"]))
            ctx.check("still exactly one message", 1,
                      len(substitution_messages(rpc, mo)))
    finally:
        try:
            sweep_wf009(rpc)
        except Exception:  # noqa: BLE001
            pass


@test_case(
    id="TEST-WF009-TC139",
    name="A component with enough stock is never substituted",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_mrp_component_replacement",
    priority="P1", kind="API", order=9139,
    description="While on-hand covers the requirement nothing is substituted "
                "and no message is posted; dropping on-hand just below the "
                "requirement triggers a substitution, proving the boundary is "
                "'covers the requirement', not 'has any stock'.",
    traceability=trace("DATAONE-TC139"))
def test_tc139(ctx):
    """EXPECTED v19 OUTCOME: FAIL on a multi-step warehouse — and the failure
    is the finding, not an automation defect.

    ``_apply_component_replacement`` judges coverage as::

        already_reserved = sum(self.move_line_ids.mapped('quantity'))
        available        = Quant._get_available_quantity(product, location)
        if already_reserved + available >= required: return False

    ``location`` comes from ``chain._get_replacement_source_location()``
    (stock_move.py:123), which correctly walks to the oldest still-open
    ancestor — WH/Stock. ``already_reserved`` does NOT: it reads
    ``self.move_line_ids``, the RAW move's own reservations only.

    On a ``pbm``/``pbm_sam`` warehouse those two disagree, and d1v19 is
    ``pbm_sam``. Measured directly, with A fully covering the requirement:

        before confirm   on-hand A = 10   available A = 10
        after confirm    raw move sits at WH/Pre-Production
                         on-hand A = 10   available A = 0   <- the pick took it
                         reserved on the raw move = 0
                         pick move: A, qty 10, state 'assigned'

    so the test evaluates ``0 + 0 = 0 < 10`` and substitutes a component that
    is fully covered by its own upstream pick. The location walk was made
    chain-aware; the reservation count was not.

    A 1-step warehouse hides this: there the raw move holds its own
    reservation and the arithmetic is right. This is why the case matters —
    the workbook's expectation ("no substitution while covered") is correct
    and the code does not meet it on the warehouse this database uses.

    The assertion below stays as the workbook requires (AUTOMATION_CONVENTIONS
    hard rule 2). Fix belongs in the module: count reservations across the
    whole chain, not just ``self``.
    """
    require_replacement_module(ctx)
    require_mrp(ctx)
    rpc = ctx.adapter.rpc
    open_namespace(ctx)
    try:
        with ctx.step("A covers the requirement exactly"):
            a, b, c, finished, bom = _clique(rpc)
            loc = stock_location(rpc)
            set_stock(rpc, a, loc, 10.0)
            set_stock(rpc, b, loc, 50.0)
            set_stock(rpc, c, loc, 0.0)
            mo = make_mo(rpc, finished, bom, qty=10.0)
            move = raw_move(rpc, mo)
            required = move["product_uom_qty"]
            # Measured with reservations included: the module judges coverage as
            # already_reserved + available >= required (stock_move.py:69), and
            # confirming the MO has already reserved A.
            ctx.check_true("on-hand of A >= requirement",
                           onhand_qty(rpc, a, loc) >= required,
                           f"{onhand_qty(rpc, a, loc)} vs {required}")

        with ctx.step("Check Components Availability changes nothing"):
            rpc.call("mrp.production", "action_check_component_replacements", [mo])
            move = raw_move(rpc, mo)
            ctx.check("still on A", a, m2o_id(move["product_id"]))
            ctx.check("original_component_id empty", False,
                      move["original_component_id"])
            ctx.check("is_component_substituted", False,
                      move["is_component_substituted"])
            ctx.check("no banner", False,
                      rpc.read("mrp.production", [mo],
                               ["has_substituted_components"])[0]
                      ["has_substituted_components"])
            ctx.check("no chatter message", 0, len(substitution_messages(rpc, mo)))

        with ctx.step("Just below the requirement, a substitution occurs"):
            # The move already reserved what A had; release it first, or the
            # reserved quantity keeps the coverage test satisfied.
            rpc.call("mrp.production", "do_unreserve", [mo])
            set_stock(rpc, a, loc, required - 0.01)
            rpc.call("mrp.production", "action_check_component_replacements", [mo])
            move = raw_move(rpc, mo)
            ctx.check("substituted to B", b, m2o_id(move["product_id"]))
            ctx.check("original_component_id records A", a,
                      m2o_id(move["original_component_id"]))
            ctx.check("one chatter message", 1,
                      len(substitution_messages(rpc, mo)))
    finally:
        try:
            sweep_wf009(rpc)
        except Exception:  # noqa: BLE001
            pass


@test_case(
    id="TEST-WF009-TC140",
    name="When no single replacement covers the shortfall, nothing is "
         "substituted",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_mrp_component_replacement",
    priority="P0", kind="API", order=9140,
    description="A requires 100, B and C hold 60 each: together they cover it "
                "but individually neither does, so nothing is substituted and "
                "no message is posted. Raising C to 100 substitutes to C, "
                "skipping B which still cannot cover.",
    traceability=trace("DATAONE-TC140"))
def test_tc140(ctx):
    require_replacement_module(ctx)
    require_mrp(ctx)
    rpc = ctx.adapter.rpc
    open_namespace(ctx)
    try:
        with ctx.step("A needs 100; B and C hold 60 each"):
            a, b, c, finished, bom = _clique(rpc)
            loc = stock_location(rpc)
            set_stock(rpc, a, loc, 0.0)
            set_stock(rpc, b, loc, 60.0)
            set_stock(rpc, c, loc, 60.0)
            mo = make_mo(rpc, finished, bom, qty=100.0)
            move = raw_move(rpc, mo)
            ctx.check("requirement", 100.0, move["product_uom_qty"])
            ctx.check("on-hand A / B / C", [0.0, 60.0, 60.0],
                      [available_qty(rpc, p, loc) for p in (a, b, c)])

        with ctx.step("Check Components Availability substitutes nothing"):
            rpc.call("mrp.production", "action_check_component_replacements", [mo])
            move = raw_move(rpc, mo)
            ctx.check("still on A", a, m2o_id(move["product_id"]))
            ctx.check("original_component_id empty", False,
                      move["original_component_id"])
            ctx.check("is_component_substituted", False,
                      move["is_component_substituted"])
            ctx.check("the MO stays short with no explanation", 0,
                      len(substitution_messages(rpc, mo)))
            ctx.check("no banner", False,
                      rpc.read("mrp.production", [mo],
                               ["has_substituted_components"])[0]
                      ["has_substituted_components"])

        with ctx.step("Raising C to 100 substitutes to C, skipping B"):
            rpc.call("mrp.production", "do_unreserve", [mo])
            set_stock(rpc, c, loc, 100.0)
            rpc.call("mrp.production", "action_check_component_replacements", [mo])
            move = raw_move(rpc, mo)
            ctx.check("substituted to C, not B", c, m2o_id(move["product_id"]))
            ctx.check("original_component_id records A", a,
                      m2o_id(move["original_component_id"]))
    finally:
        try:
            sweep_wf009(rpc)
        except Exception:  # noqa: BLE001
            pass


@test_case(
    id="TEST-WF009-TC141",
    name="A replacement in a different UoM category is skipped",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_mrp_component_replacement",
    priority="P1", kind="API", order=9141,
    description="A candidate with ample stock but an unrelated unit of "
                "measure is skipped; giving it a UoM in the requirement's own "
                "category and restocking makes it eligible, proving the skip "
                "was caused by the unit and nothing else.",
    traceability=trace("DATAONE-TC141"))
def test_tc141(ctx):
    """Observation note, not an expectation change: the workbook states the
    rule as ``uom_id.category_id`` inequality. v19 implements it as
    ``candidate.uom_id._has_common_reference(self.product_uom)``
    (stock_move.py:72). For products in genuinely unrelated categories — a
    weight unit against a plain Unit, as set up here — the two agree, and the
    assertions below are written against the observable outcome (skipped /
    not skipped) rather than against either internal call.
    """
    require_replacement_module(ctx)
    require_mrp(ctx)
    rpc = ctx.adapter.rpc
    open_namespace(ctx)
    try:
        with ctx.step("D is in A's group but measured in an unrelated unit"):
            unit = uom_unit(rpc)
            kg = rpc.ref("uom.product_uom_kgm")
            if not kg or kg == unit:
                ctx.blocked("uom.product_uom_kgm is not available on this "
                            "target, so no second UoM category exists to "
                            "build the skip case from.")
            a = make_product(rpc, "CONN-A", uom_id=unit)
            d = make_product(rpc, "DIFFUOM", uom_id=kg)
            b = make_product(rpc, "CONN-B", uom_id=unit)
            set_replacements(rpc, a, [d, b])
            finished = make_product(rpc, "FG")
            bom = make_bom(rpc, finished, a, qty=1.0)
            loc = stock_location(rpc)
            set_stock(rpc, a, loc, 0.0)
            set_stock(rpc, b, loc, 0.0)
            set_stock(rpc, d, loc, 500.0)
            ctx.check_true(
                "D's unit is not convertible to A's",
                not uom_is_convertible(rpc, kg, unit), f"kg={kg} unit={unit}")

        with ctx.step("An MO short on A does not take D despite its stock"):
            mo = make_mo(rpc, finished, bom, qty=10.0)
            rpc.call("mrp.production", "action_check_component_replacements", [mo])
            move = raw_move(rpc, mo)
            ctx.check("still on A — D was skipped", a, m2o_id(move["product_id"]))
            ctx.check("original_component_id empty", False,
                      move["original_component_id"])
            ctx.check("no chatter message", 0, len(substitution_messages(rpc, mo)))

        with ctx.step("Stocking B — same category — makes a substitution occur"):
            rpc.call("mrp.production", "do_unreserve", [mo])
            set_stock(rpc, b, loc, 50.0)
            rpc.call("mrp.production", "action_check_component_replacements", [mo])
            move = raw_move(rpc, mo)
            ctx.check("substituted to B", b, m2o_id(move["product_id"]))
            ctx.check("so the earlier skip was the unit, not the group", a,
                      m2o_id(move["original_component_id"]))
    finally:
        try:
            sweep_wf009(rpc)
        except Exception:  # noqa: BLE001
            pass
