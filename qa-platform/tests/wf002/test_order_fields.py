"""DATAONE-WF-002 — the dto_sale order fields: TC061, TC063–TC070.

Order Type (mandatory, no default), the Promised Ship Date confirmation
gate and its section/note exemption, the Delivery Date derivation and its
silent-overwrite behaviour, and the Tariff Amount write guard with its
create-path hole.

Every test that confirms an order calls ``require_mail_offline`` first —
confirmation fires dto_sale's automation, which sends to a hard-coded
d1systems.com recipient list with ``force_send=True``.

EXPECTED v17 OUTCOME: PASS for all.
"""
from framework.registry import test_case
from tests.wf002.common import (MARK, SHIP_DATE_ERROR,  # noqa: F401
                                TARIFF_ERROR, WORKFLOW, WORKFLOW_NAME,
                                confirm, ensure_partner, ensure_product,
                                expect_error, fx, line_values, make_quotation,
                                order_lines, read_order, require_dto_sale,
                                require_mail_offline, sweep_wf002, trace)


@test_case(
    id="TEST-WF002-TC061",
    name="Order Type is mandatory and has no default",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_sale", priority="P1", kind="API", order=2061,
    description="order_type has no default, a create without it is refused "
                "by the ORM required check and no record is produced, and "
                "supplying 'project' saves.",
    traceability=trace("DATAONE-TC061"))
def test_tc061(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-002 fixtures and open a fresh "
                  "namespace"):
        sweep_wf002(rpc)

    with ctx.step("Precondition: dto_sale is installed"):
        require_dto_sale(ctx)

    try:
        with ctx.step("Step 4: the field has no default — default_get "
                      "returns nothing for it — and it is declared "
                      "required"):
            defaults = rpc.call("sale.order", "default_get", ["order_type"])
            ctx.log(f"default_get: {defaults!r}")
            ctx.check("order_type default", None, defaults.get("order_type"))
            info = rpc.call("sale.order", "fields_get", ["order_type"],
                            attributes=["required", "type", "selection"])
            ctx.check("order_type required", True,
                      info["order_type"]["required"])
            ctx.check("order_type selection keys",
                      ["project", "buy", "inventory", "cost_center"],
                      [k for k, _l in info["order_type"]["selection"]])

        with ctx.step("Steps 5-6: saving without an Order Type is refused "
                      "and creates nothing"):
            partner_id = ensure_partner(rpc)
            product_id = ensure_product(ctx)
            before = rpc.call("sale.order", "search_count",
                              [("origin", "like", f"{MARK} %"),
                               ("active", "in", [True, False])])
            raised, message = expect_error(
                rpc.create, "sale.order",
                {"partner_id": partner_id,
                 "origin": fx(f"{MARK} NoType"),
                 "order_line": [line_values(product_id)]})
            ctx.log(f"raised: {message!r}")
            ctx.check_true("the create without order_type was refused",
                           raised, actual_desc=message)
            after = rpc.call("sale.order", "search_count",
                             [("origin", "like", f"{MARK} %"),
                              ("active", "in", [True, False])])
            ctx.check("marker-scoped orders created by the refused save",
                      0, after - before)

        with ctx.step("Steps 7-8: supplying Order Type = Project-based "
                      "saves, and order_type reads 'project'"):
            order_id = make_quotation(ctx, order_type="project",
                                      label="TypeOK")
            ctx.check("order_type", "project",
                      read_order(rpc, order_id, ["order_type"])["order_type"])
    finally:
        with ctx.step("Cleanup WF-002 fixtures"):
            try:
                sweep_wf002(rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")


@test_case(
    id="TEST-WF002-TC063",
    name="Confirmation is blocked when a product line has no Promised Ship "
         "Date",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_sale", priority="P1", kind="API", order=2063,
    description="A product line without requested_delivery_date raises the "
                "exact ValidationError, the order stays draft, and filling "
                "the date lets it confirm.",
    traceability=trace("DATAONE-TC063"))
def test_tc063(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-002 fixtures and open a fresh "
                  "namespace"):
        sweep_wf002(rpc)

    with ctx.step("Preconditions: dto_sale installed, mail offline"):
        require_dto_sale(ctx)
        require_mail_offline(ctx)

    try:
        with ctx.step("Steps 1-2: one line with a ship date, one without"):
            product_id = ensure_product(ctx)
            order_id = make_quotation(
                ctx, order_type="inventory", label="ShipGate",
                lines=[line_values(product_id, ship_date="2026-09-10"),
                       line_values(product_id, ship_date=None)])
            lines = order_lines(rpc, order_id,
                                ["requested_delivery_date", "product_id"])
            ctx.log(f"lines: {lines!r}")
            ctx.check("line ship dates", ["2026-09-10", False],
                      [ln["requested_delivery_date"] for ln in lines])

        with ctx.step("Steps 3-4: Confirm raises the exact message"):
            raised, message = expect_error(confirm, rpc, order_id)
            ctx.log(f"raised: {message!r}")
            ctx.check_true("confirmation was blocked", raised,
                           actual_desc=message)
            ctx.check_true(f"message is {SHIP_DATE_ERROR!r}",
                           SHIP_DATE_ERROR in message, actual_desc=message)

        with ctx.step("Step 5: the order is still draft"):
            ctx.check("state after the blocked confirm", "draft",
                      read_order(rpc, order_id, ["state"])["state"])

        with ctx.step("Step 6: filling the missing date lets it confirm"):
            rpc.write("sale.order.line", [lines[1]["id"]],
                      {"requested_delivery_date": "2026-09-24"})
            confirm(rpc, order_id)
            ctx.check("state after the successful confirm", "sale",
                      read_order(rpc, order_id, ["state"])["state"])
    finally:
        with ctx.step("Cleanup WF-002 fixtures"):
            try:
                sweep_wf002(rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")


@test_case(
    id="TEST-WF002-TC064",
    name="Section and note lines do not block confirmation",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_sale", priority="P2", kind="API", order=2064,
    description="Section and note lines carry no product and no ship date; "
                "the gate filters on display_type, so confirmation "
                "succeeds.",
    traceability=trace("DATAONE-TC064"))
def test_tc064(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-002 fixtures and open a fresh "
                  "namespace"):
        sweep_wf002(rpc)

    with ctx.step("Preconditions: dto_sale installed, mail offline"):
        require_dto_sale(ctx)
        require_mail_offline(ctx)

    try:
        with ctx.step("Steps 1-2: build an order with a section, a note and "
                      "one dated product line"):
            product_id = ensure_product(ctx)
            order_id = make_quotation(
                ctx, order_type="inventory", label="Sections",
                lines=[line_values(None, display_type="line_section",
                                   name=fx(f"{MARK} Section")),
                       line_values(product_id, ship_date="2026-09-10"),
                       line_values(None, display_type="line_note",
                                   name=fx(f"{MARK} Note"))])
            lines = order_lines(rpc, order_id,
                                ["display_type", "product_id",
                                 "requested_delivery_date"])
            ctx.log(f"lines: {lines!r}")
            display = [ln for ln in lines if ln["display_type"]]
            ctx.check("section/note lines present", 2, len(display))
            ctx.check("display lines carry no product and no ship date",
                      [(False, False), (False, False)],
                      [(ln["product_id"], ln["requested_delivery_date"])
                       for ln in display])

        with ctx.step("Steps 3-4: Confirm raises nothing and the order "
                      "reaches 'sale'"):
            confirm(rpc, order_id)
            ctx.check("state", "sale",
                      read_order(rpc, order_id, ["state"])["state"])
    finally:
        with ctx.step("Cleanup WF-002 fixtures"):
            try:
                sweep_wf002(rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")


@test_case(
    id="TEST-WF002-TC065",
    name="Delivery Date is derived from the LATEST promised line date",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_sale", priority="P1", kind="API", order=2065,
    description="commitment_date is max(requested_delivery_date) across "
                "lines, recomputes when a line date drops, and empties when "
                "every line date is cleared.",
    traceability=trace("DATAONE-TC065"))
def test_tc065(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-002 fixtures and open a fresh "
                  "namespace"):
        sweep_wf002(rpc)

    with ctx.step("Precondition: dto_sale is installed"):
        require_dto_sale(ctx)

    def commitment_date():
        value = read_order(rpc, order_id, ["commitment_date"])["commitment_date"]
        return str(value)[:10] if value else value

    try:
        with ctx.step("Steps 2-5: two lines dated 2026-09-10 and "
                      "2026-09-24 give the LATER of the two"):
            product_id = ensure_product(ctx)
            order_id = make_quotation(
                ctx, order_type="inventory", label="Dates",
                lines=[line_values(product_id, ship_date="2026-09-10"),
                       line_values(product_id, ship_date="2026-09-24")])
            lines = order_lines(rpc, order_id, ["requested_delivery_date"])
            ctx.check("commitment_date from the two line dates",
                      "2026-09-24", commitment_date())

        with ctx.step("Steps 6-7: dropping the later line date recomputes "
                      "to the new maximum"):
            rpc.write("sale.order.line", [lines[1]["id"]],
                      {"requested_delivery_date": "2026-09-03"})
            ctx.check("commitment_date after the later date dropped",
                      "2026-09-10", commitment_date())

        with ctx.step("Steps 8-9: clearing every line date empties it"):
            rpc.write("sale.order.line", [ln["id"] for ln in lines],
                      {"requested_delivery_date": False})
            ctx.check("commitment_date with no line dates", False,
                      commitment_date())
    finally:
        with ctx.step("Cleanup WF-002 fixtures"):
            try:
                sweep_wf002(rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")


@test_case(
    id="TEST-WF002-TC066",
    name="A manually typed Delivery Date persists",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_sale", priority="P2", kind="API", order=2066,
    description="commitment_date is compute+store+readonly=False with an "
                "inverse that does nothing, so a written value overrides "
                "the computed one and survives a reload.",
    traceability=trace("DATAONE-TC066"))
def test_tc066(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-002 fixtures and open a fresh "
                  "namespace"):
        sweep_wf002(rpc)

    with ctx.step("Precondition: dto_sale is installed"):
        require_dto_sale(ctx)

    try:
        with ctx.step("Steps 2-4: writing 2026-10-15 directly persists "
                      "through a fresh read"):
            product_id = ensure_product(ctx)
            order_id = make_quotation(
                ctx, order_type="inventory", label="ManualDate",
                lines=[line_values(product_id, ship_date="2026-09-10"),
                       line_values(product_id, ship_date="2026-09-24")])
            rpc.write("sale.order", [order_id],
                      {"commitment_date": "2026-10-15 00:00:00"})
            first = read_order(rpc, order_id,
                               ["commitment_date"])["commitment_date"]
            ctx.check("commitment_date after the manual write",
                      "2026-10-15", str(first)[:10])
            # a second read is a fresh RPC call, i.e. a fresh transaction
            second = read_order(rpc, order_id,
                                ["commitment_date"])["commitment_date"]
            ctx.check("commitment_date after a reload", "2026-10-15",
                      str(second)[:10])
    finally:
        with ctx.step("Cleanup WF-002 fixtures"):
            try:
                sweep_wf002(rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")


@test_case(
    id="TEST-WF002-TC067",
    name="A later line-date edit silently overwrites the manual Delivery "
         "Date",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_sale", priority="P2", kind="API", order=2067,
    description="Editing any line's Promised Ship Date re-triggers the "
                "compute and discards a manually typed Delivery Date, with "
                "no warning, dialog or chatter entry of any kind.",
    traceability=trace("DATAONE-TC067"))
def test_tc067(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-002 fixtures and open a fresh "
                  "namespace"):
        sweep_wf002(rpc)

    with ctx.step("Precondition: dto_sale is installed"):
        require_dto_sale(ctx)

    try:
        with ctx.step("Steps 1-2: rebuild TC066's state — line dates "
                      "2026-09-10 / 2026-09-24 and a manual 2026-10-15"):
            product_id = ensure_product(ctx)
            order_id = make_quotation(
                ctx, order_type="inventory", label="Overwrite",
                lines=[line_values(product_id, ship_date="2026-09-10"),
                       line_values(product_id, ship_date="2026-09-24")])
            lines = order_lines(rpc, order_id, ["requested_delivery_date"])
            rpc.write("sale.order", [order_id],
                      {"commitment_date": "2026-10-15 00:00:00"})
            ctx.check("manual commitment_date is in place", "2026-10-15",
                      str(read_order(rpc, order_id,
                                     ["commitment_date"])["commitment_date"])[:10])
            messages_before = rpc.call(
                "mail.message", "search_count",
                [("model", "=", "sale.order"), ("res_id", "=", order_id)])

        with ctx.step("Steps 3-5: editing line 1's date silently overwrites "
                      "the manual value with the recomputed maximum"):
            rpc.write("sale.order.line", [lines[0]["id"]],
                      {"requested_delivery_date": "2026-09-11"})
            ctx.check("commitment_date after the line edit", "2026-09-24",
                      str(read_order(rpc, order_id,
                                     ["commitment_date"])["commitment_date"])[:10])

        with ctx.step("Step 6: no chatter entry recorded the change — the "
                      "user is told nothing"):
            messages_after = rpc.call(
                "mail.message", "search_count",
                [("model", "=", "sale.order"), ("res_id", "=", order_id)])
            tracked = rpc.search_read(
                "mail.tracking.value",
                [("mail_message_id.model", "=", "sale.order"),
                 ("mail_message_id.res_id", "=", order_id),
                 ("field_id.name", "=", "commitment_date")],
                ["field_id"])
            ctx.log(f"chatter {messages_before} -> {messages_after}; "
                    f"commitment_date tracking values: {tracked!r}")
            ctx.check("chatter entries about the overwritten date", [],
                      tracked)
    finally:
        with ctx.step("Cleanup WF-002 fixtures"):
            try:
                sweep_wf002(rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")


@test_case(
    id="TEST-WF002-TC068",
    name="A negative tariff is rejected on write with the exact message",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_sale", priority="P2", kind="API", order=2068,
    description="write() raises the exact ValidationError, nothing is "
                "stored, 0.00 is accepted, and a positive value is tracked "
                "in the chatter.",
    traceability=trace("DATAONE-TC068"))
def test_tc068(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-002 fixtures and open a fresh "
                  "namespace"):
        sweep_wf002(rpc)

    with ctx.step("Precondition: dto_sale is installed"):
        require_dto_sale(ctx)

    try:
        with ctx.step("Steps 2-4: writing -1.00 raises the exact message"):
            order_id = make_quotation(ctx, order_type="inventory",
                                      tariff=0.0, label="Tariff")
            raised, message = expect_error(
                rpc.write, "sale.order", [order_id],
                {"tariff_amount": -1.00})
            ctx.log(f"raised: {message!r}")
            ctx.check_true("the negative tariff write was refused", raised,
                           actual_desc=message)
            ctx.check_true(f"message is {TARIFF_ERROR!r}",
                           TARIFF_ERROR in message, actual_desc=message)

        with ctx.step("Step 5: nothing was written — the stored value is "
                      "still 0.00"):
            ctx.check("tariff_amount after the refused write", 0.0,
                      read_order(rpc, order_id,
                                 ["tariff_amount"])["tariff_amount"])

        with ctx.step("Step 6: exactly 0.00 is accepted"):
            rpc.write("sale.order", [order_id], {"tariff_amount": 0.0})
            ctx.check("tariff_amount", 0.0,
                      read_order(rpc, order_id,
                                 ["tariff_amount"])["tariff_amount"])

        with ctx.step("Step 7: 250.00 saves and the chatter records the "
                      "change (tracking=True)"):
            rpc.write("sale.order", [order_id], {"tariff_amount": 250.0})
            ctx.check("tariff_amount", 250.0,
                      read_order(rpc, order_id,
                                 ["tariff_amount"])["tariff_amount"])
            tracked = rpc.search_read(
                "mail.tracking.value",
                [("mail_message_id.model", "=", "sale.order"),
                 ("mail_message_id.res_id", "=", order_id),
                 ("field_id.name", "=", "tariff_amount")],
                ["field_id"])
            ctx.check_true("the tariff change is tracked in the chatter",
                           bool(tracked), actual_desc=repr(tracked))
    finally:
        with ctx.step("Cleanup WF-002 fixtures"):
            try:
                sweep_wf002(rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")


@test_case(
    id="TEST-WF002-TC069",
    name="A negative tariff supplied to create() is NOT blocked (defect "
         "regression)",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_sale", priority="P2", kind="API", order=2069,
    description="The guard lives in write() only "
                "(dto_sale/models/sale_order.py:75), so create() stores "
                "-500.00 unchallenged while a later write of the same value "
                "raises.",
    traceability=trace("DATAONE-TC069"))
def test_tc069(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-002 fixtures and open a fresh "
                  "namespace"):
        sweep_wf002(rpc)

    with ctx.step("Precondition: dto_sale is installed"):
        require_dto_sale(ctx)

    try:
        with ctx.step("Steps 1-2: create() with tariff_amount = -500.00 "
                      "does not raise"):
            order_id = make_quotation(ctx, order_type="buy", tariff=-500.0,
                                      label="NegCreate")
            ctx.check_true("the create succeeded", bool(order_id),
                           actual_desc=f"sale.order {order_id}")

        with ctx.step("Step 3: the negative value is stored"):
            ctx.check("tariff_amount stored by create", -500.0,
                      read_order(rpc, order_id,
                                 ["tariff_amount"])["tariff_amount"])

        with ctx.step("Steps 4-5: writing the same value on the same record "
                      "DOES raise — the guard is in write() only"):
            raised, message = expect_error(
                rpc.write, "sale.order", [order_id],
                {"tariff_amount": -500.0})
            ctx.log(f"raised: {message!r}")
            ctx.check_true("the write was refused", raised,
                           actual_desc=message)
            ctx.check_true(f"message is {TARIFF_ERROR!r}",
                           TARIFF_ERROR in message, actual_desc=message)
    finally:
        with ctx.step("Cleanup WF-002 fixtures"):
            try:
                sweep_wf002(rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")


@test_case(
    id="TEST-WF002-TC070",
    name="Tariff Amount never affects the order total",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_sale", priority="P2", kind="API", order=2070,
    description="tariff_amount is a standalone Monetary field with no "
                "place in any total: changing it leaves amount_untaxed, "
                "amount_tax and amount_total identical, and the value "
                "reaches no invoice line, tax or total.",
    traceability=trace("DATAONE-TC070"))
def test_tc070(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-002 fixtures and open a fresh "
                  "namespace"):
        sweep_wf002(rpc)

    with ctx.step("Preconditions: dto_sale installed, mail offline"):
        require_dto_sale(ctx)
        require_mail_offline(ctx)

    try:
        with ctx.step("Steps 1-2: record the three totals with the tariff "
                      "at 250.00"):
            product_id = ensure_product(ctx, price=100.0)
            order_id = make_quotation(
                ctx, order_type="inventory", tariff=250.0, label="TariffTot",
                lines=[line_values(product_id, qty=2.0, price=100.0)])
            before = read_order(rpc, order_id,
                                ["amount_untaxed", "amount_tax",
                                 "amount_total"])
            ctx.log(f"totals with tariff 250: {before!r}")

        with ctx.step("Steps 3-4: raising the tariff to 9999.00 leaves all "
                      "three totals unchanged"):
            rpc.write("sale.order", [order_id], {"tariff_amount": 9999.0})
            after = read_order(rpc, order_id,
                               ["amount_untaxed", "amount_tax",
                                "amount_total", "tariff_amount"])
            ctx.check("tariff_amount was written", 9999.0,
                      after["tariff_amount"])
            ctx.check("the three totals",
                      {k: before[k] for k in
                       ("amount_untaxed", "amount_tax", "amount_total")},
                      {k: after[k] for k in
                       ("amount_untaxed", "amount_tax", "amount_total")})

        with ctx.step("Steps 5-6: confirm and invoice — no invoice line, "
                      "tax or total carries the tariff value"):
            from framework.dto_fixtures import create_invoice
            confirm(rpc, order_id)
            invoice_id = create_invoice(ctx, order_id)
            if not invoice_id:
                ctx.log("no invoice was produced for this order (nothing "
                        "delivered and the policy is delivery-based) — the "
                        "invoice half is not applicable here")
            else:
                lines = rpc.search_read(
                    "account.move.line",
                    [("move_id", "=", invoice_id)],
                    ["name", "price_unit", "price_subtotal", "balance"])
                move = rpc.read("account.move", [invoice_id],
                                ["amount_untaxed", "amount_tax",
                                 "amount_total"])[0]
                ctx.log(f"invoice lines: {lines!r}; totals: {move!r}")
                hits = [ln for ln in lines
                        if 9999.0 in (ln["price_unit"],
                                      ln["price_subtotal"],
                                      abs(ln["balance"]))]
                ctx.check("invoice lines carrying the tariff value", [],
                          hits)
                ctx.check("invoice totals carrying the tariff value", [],
                          [k for k, v in move.items() if v == 9999.0])
    finally:
        with ctx.step("Cleanup WF-002 fixtures"):
            try:
                sweep_wf002(rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")
