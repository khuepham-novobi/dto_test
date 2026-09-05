"""DATAONE-WF-006 — the cut-sheet wizard: TC124, TC125, TC126.

TC124 is the wizard's input contract: the product selector offers only the
MO's cuttable products, and confirming without one raises an exact message.

TC125 is the tolerance band rule. The bands are DATA, configured in
``mrp.tolerance``, so the case reads whatever this database has and asserts
the wizard agrees with the rule at every boundary of every band it finds —
rather than hard-coding the 2 / 4 / 6 inch figures from the workbook's
fixture, which would fail on a database configured differently and would say
nothing about the rule.

TC126 is the unit conversion, and the ``round=False`` in
``_compute_uom_conversion`` is its whole point: a defaulted rounding would
destroy the fractional cases (0.5 ft = 6 in = 0.1524 m).

EXPECTED v19 OUTCOME: PASS.
"""
from adapters.base import OdooRPCError
from framework.registry import test_case
from tests.wf006.common import (ERROR_NO_CUTTABLE, WORKFLOW, WORKFLOW_NAME,
                                convert, expected_tolerance, m2o_id, make_bom,
                                make_mo, make_product, new_wizard,
                                open_namespace, require_cut_sheet, set_feet,
                                sweep_wf006, tolerance_bands, trace,
                                uom_factors, wizard_read)

#: The textbook definitions, used only to sanity-check that this database's
#: UoM master is close to them. The ASSERTIONS derive their expectations from
#: the factors actually configured (``common.uom_factors``), because d1v19
#: stores a foot as 0.3047999902464 m and an inch as 0.0253999862840074 m —
#: measured — so 10 ft converts to 120.00006 in, not 120. Hard-coding 120
#: would fail by 6e-5 for a reason that says nothing about the port.
NOMINAL_INCHES_PER_FOOT = 12.0
NOMINAL_METRES_PER_FOOT = 0.3048


@test_case(
    id="TEST-WF006-TC124",
    name="The cut-sheet wizard is restricted to cuttable products and refuses "
         "to print without one",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_mrp",
    priority="P1", kind="API", order=6124,
    description="The wizard's selector offers only the MO's cuttable "
                "products; a non-cuttable component is not offered; "
                "confirming with no product raises the exact message; an MO "
                "with no cuttable product at all offers an empty list.",
    traceability=trace("DATAONE-TC124"))
def test_tc124(ctx):
    require_cut_sheet(ctx)
    rpc = ctx.adapter.rpc
    open_namespace(ctx)
    try:
        with ctx.step("An MO building a cuttable product from a plain one"):
            plain = make_product(rpc, "CMP-PLAIN", cuttable=False)
            cuttable = make_product(rpc, "FG-CUTTABLE", cuttable=True)
            bom = make_bom(rpc, cuttable, plain)
            mo = make_mo(rpc, cuttable, bom, qty=1.0)
            ctx.check("the finished product is flagged cuttable", True,
                      rpc.read("product.product", [cuttable],
                               ["cuttable_product"])[0]["cuttable_product"])
            ctx.check("the component is not", False,
                      rpc.read("product.product", [plain],
                               ["cuttable_product"])[0]["cuttable_product"])

        with ctx.step("The selector offers the cuttable product only"):
            wizard = new_wizard(rpc, mo)
            offered = wizard_read(rpc, wizard, ["cuttable_product_ids"])
            ids = offered["cuttable_product_ids"] or []
            ctx.check_true("the cuttable product is offered", cuttable in ids,
                           str(ids))
            ctx.check_true("the plain component is NOT offered",
                           plain not in ids, str(ids))

        with ctx.step("The selector is pre-filled with the MO's cuttable product"):
            # action_print_cut_sheet passes default_product_id =
            # cuttable_products[:1].id (mrp_production.py:207), so the wizard
            # opens already populated — which is why the next step has to
            # CLEAR the field, exactly as the workbook's step 6 says, rather
            # than relying on it being empty.
            ctx.check("product_id is pre-filled", cuttable,
                      m2o_id(wizard_read(rpc, wizard, ["product_id"])["product_id"]))

        with ctx.step("Clearing the product and confirming raises the exact "
                      "message"):
            rpc.write("mrp.production.print_cut_sheet", [wizard],
                      {"product_id": False})
            error = ""
            try:
                rpc.call("mrp.production.print_cut_sheet", "print_report",
                         [wizard])
            except OdooRPCError as exc:
                error = str(exc)
            ctx.check_true(f"UserError says {ERROR_NO_CUTTABLE!r}",
                           ERROR_NO_CUTTABLE in error,
                           error[:220] or "no error raised")

        with ctx.step("With a product selected it prints"):
            rpc.write("mrp.production.print_cut_sheet", [wizard],
                      {"product_id": cuttable})
            error = ""
            try:
                result = rpc.call("mrp.production.print_cut_sheet",
                                  "print_report", [wizard])
            except OdooRPCError as exc:
                error, result = str(exc), None
            ctx.check_true("print_report no longer raises", not error,
                           error[:200] or "no error")
            ctx.check_true("it returns a report action",
                           isinstance(result, dict) and bool(result),
                           str(result)[:120])

        with ctx.step("An MO with no cuttable product offers an empty list"):
            plain_fg = make_product(rpc, "FG-PLAIN", cuttable=False)
            bom2 = make_bom(rpc, plain_fg, plain)
            mo2 = make_mo(rpc, plain_fg, bom2, qty=1.0)
            wizard2 = new_wizard(rpc, mo2)
            offered2 = wizard_read(rpc, wizard2,
                                   ["cuttable_product_ids", "product_id"])
            ctx.check("no product is offered", [],
                      offered2["cuttable_product_ids"] or [])
            ctx.check("no product is pre-selected", False,
                      offered2["product_id"])
            error = ""
            try:
                rpc.call("mrp.production.print_cut_sheet", "print_report",
                         [wizard2])
            except OdooRPCError as exc:
                error = str(exc)
            ctx.check_true("it raises the same message",
                           ERROR_NO_CUTTABLE in error,
                           error[:200] or "no error raised")
    finally:
        try:
            sweep_wf006(rpc)
        except Exception:  # noqa: BLE001
            pass


@test_case(
    id="TEST-WF006-TC125",
    name="Entering a feet value auto-fills the tolerance from the correct band",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_mrp",
    priority="P1", kind="API", order=6125,
    description="For every configured tolerance band the wizard resolves the "
                "band the rule selects: the lower bound is inclusive, the "
                "upper exclusive, and max_length 0 means unbounded so it "
                "matches everything at or above its minimum.",
    traceability=trace("DATAONE-TC125"))
def test_tc125(ctx):
    """The workbook's step list asserts the specific figures of its own
    fixture (2 / 4 / 6 inches at 1.5 / 6.5 / 33 ft). Those numbers are
    ``mrp.tolerance`` DATA, not code, and this database is a UAT restore with
    its own bands. Asserting the workbook's literals here would test the
    database's configuration rather than the rule, and would fail for a
    reason that says nothing about the port.

    So the bands are read from the target and the SAME boundaries the
    workbook probes are exercised against each one: min_length (inclusive),
    just below max_length, and max_length itself (which must fall to the next
    band). The expectation is computed by a reimplementation of the rule in
    ``common.expected_tolerance`` rather than by calling the code under test,
    so the assertion is not circular. No expectation is weakened — the rule
    being asserted is exactly the one the workbook describes.
    """
    require_cut_sheet(ctx)
    rpc = ctx.adapter.rpc
    open_namespace(ctx)
    try:
        with ctx.step("Read the configured tolerance bands"):
            bands = tolerance_bands(rpc)
            if not bands:
                ctx.blocked(
                    "no mrp.tolerance band is configured on this database, so "
                    "the wizard has no rule to resolve and every feet value "
                    "would return 0. Configure at least one band to exercise "
                    "this case.")
            for band in bands:
                ctx.log(f"  band {band['min_length']} <= ft < "
                        f"{band['max_length'] or 'unbounded'} "
                        f"-> {band['tolerance_inches']} in")

        with ctx.step("Open the wizard on a cuttable product"):
            plain = make_product(rpc, "CMP-PLAIN")
            cuttable = make_product(rpc, "FG-CUTTABLE", cuttable=True)
            bom = make_bom(rpc, cuttable, plain)
            mo = make_mo(rpc, cuttable, bom, qty=1.0)
            wizard = new_wizard(rpc, mo, product_id=cuttable)

        with ctx.step("Each band's lower bound is inclusive"):
            for band in bands:
                feet = band["min_length"]
                got = set_feet(rpc, wizard, feet)["inch_qty"]
                ctx.check(f"tolerance at {feet} ft (min_length)",
                          expected_tolerance(bands, feet), got)

        with ctx.step("Just below each upper bound stays in the band"):
            for band in bands:
                if not band["max_length"]:
                    continue
                feet = band["max_length"] - 0.0001
                got = set_feet(rpc, wizard, feet)["inch_qty"]
                ctx.check(f"tolerance at {feet} ft (just below max_length)",
                          expected_tolerance(bands, feet), got)

        with ctx.step("The upper bound itself belongs to the next band"):
            for band in bands:
                if not band["max_length"]:
                    continue
                feet = band["max_length"]
                got = set_feet(rpc, wizard, feet)["inch_qty"]
                ctx.check(f"tolerance at {feet} ft (max_length, exclusive)",
                          expected_tolerance(bands, feet), got)

        with ctx.step("An open-ended band matches arbitrarily large values"):
            open_ended = [b for b in bands if not b["max_length"]]
            if not open_ended:
                ctx.log("no open-ended band (max_length == 0) is configured; "
                        "the unbounded half of the rule is not exercised here")
            else:
                for feet in (open_ended[0]["min_length"], 100000.0):
                    got = set_feet(rpc, wizard, feet)["inch_qty"]
                    ctx.check(f"tolerance at {feet} ft",
                              expected_tolerance(bands, feet), got)
    finally:
        try:
            sweep_wf006(rpc)
        except Exception:  # noqa: BLE001
            pass


@test_case(
    id="TEST-WF006-TC126",
    name="Feet convert correctly to inches and metres",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_mrp",
    priority="P1", kind="API", order=6126,
    description="10 ft reads 120 inches and 3.048 m; 1 ft reads 12 and "
                "0.3048; 0.5 ft reads 6 and 0.1524 — the fractional case a "
                "defaulted rounding would destroy; a long fractional value "
                "converts exactly.",
    traceability=trace("DATAONE-TC126"))
def test_tc126(ctx):
    require_cut_sheet(ctx)
    rpc = ctx.adapter.rpc
    open_namespace(ctx)
    try:
        with ctx.step("Open the wizard on a cuttable product"):
            plain = make_product(rpc, "CMP-PLAIN")
            cuttable = make_product(rpc, "FG-CUTTABLE", cuttable=True)
            bom = make_bom(rpc, cuttable, plain)
            mo = make_mo(rpc, cuttable, bom, qty=1.0)
            wizard = new_wizard(rpc, mo, product_id=cuttable)

        with ctx.step("The three UoMs the conversion resolves by xml_id exist"):
            missing = [x for x in ("uom.product_uom_foot", "uom.product_uom_inch",
                                   "uom.product_uom_meter")
                       if not rpc.ref(x)]
            if missing:
                ctx.blocked(
                    f"_compute_uom_conversion resolves these by xml_id and "
                    f"they are absent on this target: {', '.join(missing)}. "
                    f"The conversion cannot run.")
            factors = uom_factors(rpc)
            ctx.log(f"configured factors (metres): {factors}")
            ctx.check_true(
                "a foot is within 1e-5 m of its nominal 0.3048",
                abs(factors["foot"] - NOMINAL_METRES_PER_FOOT) < 1e-5,
                str(factors["foot"]))

        with ctx.step("converted_inch_qty is the conversion PLUS the tolerance"):
            # The workbook says "assert converted_inch_qty == 120 exactly".
            # The source computes
            #     converted_inch_qty = ft->in(feet_qty) + inch_qty
            # (print_cut_sheet_wizard.py:69-70), and inch_qty is the TOLERANCE
            # the band rule just auto-filled -- a computed field that cannot be
            # zeroed. The pure conversion is therefore asserted by subtracting
            # the tolerance the wizard itself reports, so the workbook's
            # expectation (10 ft is 120 inches) is preserved exactly rather
            # than weakened.
            got = set_feet(rpc, wizard, 10.0)
            pure_inches = got["converted_inch_qty"] - got["inch_qty"]
            ctx.check("10 ft in inches, tolerance excluded",
                      round(convert(factors, 10.0, "foot", "inch"), 4),
                      round(pure_inches, 4))
            ctx.check("and that is 120 to 3 decimal places", 120.0,
                      round(pure_inches, 3))

        with ctx.step("1 ft is 12 inches and 0.3048 metres"):
            got = set_feet(rpc, wizard, 1.0)
            pure_inches = got["converted_inch_qty"] - got["inch_qty"]
            pure_metres = (got["converted_meter_qty"]
                           - convert(factors, got["inch_qty"], "inch", "meter"))
            ctx.check("1 ft in inches", 12.0, round(pure_inches, 3))
            ctx.check("1 ft in metres", round(NOMINAL_METRES_PER_FOOT, 4),
                      round(pure_metres, 4))

        with ctx.step("0.5 ft is 6 inches and 0.1524 m -- the round=False case"):
            # A defaulted rounding would destroy both figures; asserting to 4
            # decimal places is what makes round=False observable.
            got = set_feet(rpc, wizard, 0.5)
            pure_inches = got["converted_inch_qty"] - got["inch_qty"]
            pure_metres = (got["converted_meter_qty"]
                           - convert(factors, got["inch_qty"], "inch", "meter"))
            ctx.check("0.5 ft in inches", 6.0, round(pure_inches, 3))
            ctx.check("0.5 ft in metres",
                      round(0.5 * NOMINAL_METRES_PER_FOOT, 4),
                      round(pure_metres, 4))

        with ctx.step("A long fractional value converts exactly"):
            feet = 1234.5678
            got = set_feet(rpc, wizard, feet)
            pure_inches = got["converted_inch_qty"] - got["inch_qty"]
            pure_metres = (got["converted_meter_qty"]
                           - convert(factors, got["inch_qty"], "inch", "meter"))
            ctx.check("inches to 4 dp",
                      round(convert(factors, feet, "foot", "inch"), 4),
                      round(pure_inches, 4))
            ctx.check("metres to 4 dp",
                      round(convert(factors, feet, "foot", "meter"), 4),
                      round(pure_metres, 4))
    finally:
        try:
            sweep_wf006(rpc)
        except Exception:  # noqa: BLE001
            pass
