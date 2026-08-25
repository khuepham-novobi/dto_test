"""DATAONE-WF-002 — per-line delivery performance: TC071, TC072.

``dto_sale.sale.order.line._compute_date_difference_delivery_status``
(dto_sale/models/sale_order_line.py:45) fills ``actual_delivery_date``,
``date_difference`` and ``delivery_status`` once an outgoing move is done::

    done_moves = line.move_ids.filtered(picking_code == 'outgoing')
                              .filtered(state == 'done')
    if done_moves:
        last = max(done_moves, key=lambda x: x.id).date
        reference_date = line.requested_delivery_date or line.order_id.commitment_date.date()
        if reference_date:
            date_diff = (reference_date - last.date()).days
            line.date_difference = abs(date_diff)
            line.delivery_status = 'early' if date_diff >= 0 else 'late'

Two things follow, and the workbook asserts both:

* ``date_difference`` is an absolute magnitude, so it loses the sign;
* ``line.order_id.commitment_date.date()`` is evaluated whenever the line
  has no ``requested_delivery_date``. ``commitment_date`` is itself
  ``max(line ship dates)``, so clearing every line date makes it ``False``
  and the compute raises ``AttributeError: 'bool' object has no attribute
  'date'`` — while merely *reading* the field. That is TC072's second half
  and it is verified in source.

**Contested expectation — flagged, not silently adjusted.** TC072 step 2
expects ``delivery_status == 'early'`` for a shipment 19 days late, on the
grounds that ``late`` is dead logic. Reading the source, ``date_diff`` is
signed and the ternary is ``'early' if date_diff >= 0 else 'late'``, so a
move completed after the promised date should yield ``late``. This test
implements the workbook's expectation verbatim, as convention rule 2
requires. If it FAILS on the ``delivery_status`` assertion while
``date_difference`` matches, that is a **workbook-vs-source discrepancy for
a human to adjudicate**, not an automation defect — the docstring is the
place it is recorded.

These two cases build real stock and validate a real delivery, using
``framework/dto_fixtures.py`` so WF-013 can reuse the same fixtures. Every
record involved is this execution's own.

EXPECTED v17 OUTCOME: TC071 PASS. TC072 PASS on the AttributeError half;
the ``delivery_status == 'early'`` assertion is expected to FAIL — see
above.
"""
from framework.dto_fixtures import deliver_order, order_pickings, set_stock
from framework.registry import test_case
from tests.wf002.common import (MARK, WORKFLOW, WORKFLOW_NAME,  # noqa: F401
                                confirm, ensure_product, expect_error,
                                line_values, make_quotation, order_lines,
                                read_order, require_dto_sale,
                                require_mail_offline, sweep_wf002, trace)

LINE_FIELDS = ["actual_delivery_date", "date_difference", "delivery_status",
               "requested_delivery_date", "product_uom_qty", "qty_delivered"]


def _require_delivery_fields(ctx):
    rpc = ctx.adapter.rpc
    missing = [f for f in ("actual_delivery_date", "date_difference",
                           "delivery_status")
               if not rpc.field_exists("sale.order.line", f)]
    if missing:
        ctx.blocked(
            f"dto_sale's delivery-performance fields are missing on "
            f"{ctx.env.key}: {', '.join(missing)}.")
    if not rpc.model_exists("stock.picking"):
        ctx.blocked("stock is not installed — there is no outgoing delivery "
                    "to validate.")


@test_case(
    id="TEST-WF002-TC071",
    name="Per-line delivery performance populates after the outgoing move "
         "is done",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_sale", priority="P2", kind="API", order=2071,
    description="Before delivery the three fields are empty / no_date_set / "
                "0; after validating the outgoing picking "
                "actual_delivery_date matches the highest-id done move, "
                "date_difference is a positive magnitude and both the line "
                "and the order report a delivery status.",
    traceability=trace("DATAONE-TC071"))
def test_tc071(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-002 fixtures and open a fresh "
                  "namespace"):
        sweep_wf002(rpc)

    with ctx.step("Preconditions: dto_sale, the delivery fields, stock, "
                  "mail offline"):
        require_dto_sale(ctx)
        _require_delivery_fields(ctx)
        require_mail_offline(ctx)

    try:
        with ctx.step("Build a stocked product and confirm an order for it "
                      "with a promised ship date well in the future"):
            product_id = ensure_product(ctx, price=100.0)
            set_stock(ctx, product_id, 10.0)
            order_id = make_quotation(
                ctx, order_type="inventory", label="Delivery",
                lines=[line_values(product_id, qty=2.0, price=100.0,
                                   ship_date="2099-09-10")])
            confirm(rpc, order_id)
            ctx.check("state", "sale",
                      read_order(rpc, order_id, ["state"])["state"])

        with ctx.step("Step 1: before delivery the three fields are at "
                      "their empty defaults"):
            line = order_lines(rpc, order_id, LINE_FIELDS)[0]
            ctx.log(f"line before delivery: {line!r}")
            ctx.check("pre-delivery performance fields",
                      {"actual_delivery_date": False,
                       "delivery_status": "no_date_set",
                       "date_difference": 0.0},
                      {"actual_delivery_date": line["actual_delivery_date"],
                       "delivery_status": line["delivery_status"],
                       "date_difference": round(line["date_difference"], 2)})

        with ctx.step("Step 2: validate the outgoing picking"):
            pickings = deliver_order(ctx, order_id)
            ctx.log(f"pickings after validation: {pickings!r}")
            if not pickings:
                ctx.blocked(
                    "The confirmed order produced no outgoing picking on "
                    f"{ctx.env.key}. The delivery-performance fields only "
                    "fill from a done outgoing move, so there is nothing to "
                    "assert; check the warehouse route configuration on "
                    "this database.")
            ctx.check("picking states", ["done"] * len(pickings),
                      [p["state"] for p in pickings])

        with ctx.step("Steps 3-4: actual_delivery_date matches the date of "
                      "the highest-id done outgoing move on the line"):
            line_id = order_lines(rpc, order_id, ["id"])[0]["id"]
            moves = rpc.search_read(
                "stock.move",
                [("sale_line_id", "=", line_id), ("state", "=", "done")],
                ["date", "id"], order="id desc")
            ctx.log(f"done moves: {moves!r}")
            ctx.check_true("at least one done move exists", bool(moves),
                           actual_desc=repr(moves))
            after = order_lines(rpc, order_id, LINE_FIELDS)[0]
            ctx.log(f"line after delivery: {after!r}")
            ctx.check("actual_delivery_date",
                      str(moves[0]["date"])[:10],
                      str(after["actual_delivery_date"])[:10])

        with ctx.step("Step 5: date_difference is a positive magnitude — "
                      "the compute stores abs(date_diff)"):
            ctx.check_true("date_difference is non-negative",
                           after["date_difference"] >= 0,
                           actual_desc=repr(after["date_difference"]))

        with ctx.step("Steps 6-7: the line reports 'early' (delivered "
                      "before a 2099 promise) and the order agrees"):
            ctx.check("line delivery_status", "early",
                      after["delivery_status"])
            ctx.check("order delivery_time_status", "early",
                      read_order(rpc, order_id,
                                 ["delivery_time_status"])["delivery_time_status"])
    finally:
        with ctx.step("Cleanup WF-002 fixtures"):
            try:
                sweep_wf002(rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")


@test_case(
    id="TEST-WF002-TC072",
    name='"Late" is unreachable at line level, and the null-commitment crash',
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_sale", priority="P3", kind="API", order=2072,
    description="A shipment delivered after its promised date is expected "
                "by the workbook to still read 'early' with a positive "
                "date_difference; and a line with no promised date on an "
                "order whose commitment_date is empty makes the compute "
                "raise AttributeError while merely reading the field.",
    traceability=trace("DATAONE-TC072"))
def test_tc072(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-002 fixtures and open a fresh "
                  "namespace"):
        sweep_wf002(rpc)

    with ctx.step("Preconditions: dto_sale, the delivery fields, stock, "
                  "mail offline"):
        require_dto_sale(ctx)
        _require_delivery_fields(ctx)
        require_mail_offline(ctx)

    try:
        with ctx.step("Order A: promised in the PAST, so the delivery is "
                      "late by a wide margin"):
            product_id = ensure_product(ctx, price=100.0)
            set_stock(ctx, product_id, 20.0)
            order_a = make_quotation(
                ctx, order_type="inventory", label="LateOrder",
                lines=[line_values(product_id, qty=1.0, price=100.0,
                                   ship_date="2000-01-01")])
            confirm(rpc, order_a)
            pickings = deliver_order(ctx, order_a)
            if not pickings or any(p["state"] != "done" for p in pickings):
                ctx.blocked(
                    "The outgoing picking for order A did not reach 'done' "
                    f"on {ctx.env.key} ({pickings!r}); without a done move "
                    "the delivery-performance compute never runs.")

        with ctx.step("Steps 1-2: the line reports a positive "
                      "date_difference and, per the workbook, still "
                      "'early' — 'late' is claimed to be dead logic"):
            line = order_lines(rpc, order_a, LINE_FIELDS)[0]
            ctx.log(f"line A: {line!r}")
            ctx.check_true("date_difference is a positive magnitude",
                           line["date_difference"] > 0,
                           actual_desc=repr(line["date_difference"]))
            ctx.log("NOTE — contested expectation. The source reads "
                    "`'early' if date_diff >= 0 else 'late'` over a SIGNED "
                    "date_diff (dto_sale/models/sale_order_line.py), which "
                    "suggests a late shipment should yield 'late'. The "
                    "workbook expects 'early'. The workbook is immutable, "
                    "so the assertion below implements it verbatim; a "
                    "failure here is a workbook-vs-source discrepancy to "
                    "adjudicate, not an automation defect.")
            ctx.check("line delivery_status for a late shipment", "early",
                      line["delivery_status"])

        with ctx.step("Steps 3-4: order B — clearing every line's promised "
                      "date empties commitment_date, and the compute then "
                      "evaluates False.date()"):
            order_b = make_quotation(
                ctx, order_type="inventory", label="NullCommit",
                lines=[line_values(product_id, qty=1.0, price=100.0,
                                   ship_date="2099-09-10")])
            confirm(rpc, order_b)
            deliver_order(ctx, order_b)
            line_b = order_lines(rpc, order_b, ["id"])[0]["id"]
            rpc.write("sale.order.line", [line_b],
                      {"requested_delivery_date": False})
            rpc.write("sale.order", [order_b], {"commitment_date": False})
            state = read_order(rpc, order_b, ["commitment_date"])
            ctx.log(f"order B commitment_date: {state!r}")
            ctx.check("commitment_date is empty", False,
                      state["commitment_date"])

            raised, message = expect_error(
                rpc.read, "sale.order.line", [line_b], ["delivery_status"])
            ctx.log(f"reading delivery_status raised: {message!r}")
            ctx.check_true("reading the field raised", raised,
                           actual_desc=message)
            ctx.check_true(
                "the message names a bool with no 'date' attribute",
                "date" in message and "bool" in message,
                actual_desc=message)
    finally:
        with ctx.step("Cleanup WF-002 fixtures"):
            try:
                sweep_wf002(rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")
