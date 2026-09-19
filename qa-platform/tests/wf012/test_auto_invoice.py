"""DATAONE-WF-012 — the trigger: TC288 and TC289.

The whole workflow is one line of ``dto_sale_stock``::

    orders = self.sale_id.filtered(lambda r:
        r.order_type in ['project', 'inventory', 'cost_center']
        and r.invoice_status == 'to invoice')

TC288 proves the click does the work: a warehouse operator validates a
delivery and a numbered, POSTED customer invoice appears with no accountant
in between, and with no UI signal that it happened.

TC289 proves the filter is exactly those three order types and no more —
``buy`` must stay on the manual path — and that the ``invoice_status``
term makes the override idempotent, so a second delivery on an
already-billed order produces no second invoice.

What these cases deliberately do NOT assert
-------------------------------------------
The journal entry. Delta §8 confirms every method in this chain is
unchanged on v19, so the code keeps running and keeps producing a posted,
numbered invoice — while §2.2's two renamed anglo-saxon hooks silently
empty the COGS basis and the analytic distribution inside it. "The delivery
worked fine" is the exact shape of the regression. Both workbook cases end
with "hand the resulting account.move to the VAL suite"; that suite is
``tests/wf013`` and ``TEST-WF013-TC222`` is the assertion that matters.
These two cases therefore log the invoice ids they produced, for that
handoff, and assert only the trigger.

EXPECTED v17 OUTCOME: PASS for both.
EXPECTED v19 OUTCOME: PASS for both — and that is the warning, not the
reassurance. A green TC288 with a failing TEST-WF013-TC222 is the defect
this workflow exists to expose.
"""
from framework.registry import test_case
from tests.wf012.common import (AUTO_INVOICE_ORDER_TYPES,  # noqa: F401
                                DELIVERY_VALIDATION_GROUP,
                                MANUAL_INVOICE_ORDER_TYPES, MARK, WORKFLOW,
                                WORKFLOW_NAME, confirm_with_stock,
                                create_invoice, deliver_order, ensure_product,
                                fx, invoices_of, m2o_id, outgoing_picking,
                                realtime_category, require_auto_invoice_stack,
                                require_cogs_analytics, require_mail_offline,
                                sweep_wf012, trace, validate_picking)


def _preconditions(ctx):
    """Every environment fact the two cases share, probed not assumed."""
    require_auto_invoice_stack(ctx)
    require_mail_offline(ctx)
    require_cogs_analytics(ctx)
    category = realtime_category(ctx)
    if category is None:
        ctx.log("[warn] no product.category on this target uses real-time "
                "valuation. The invoice is still created and posted, so "
                "WF-012's own assertions hold — but no anglo-saxon COGS "
                "pair is produced, so the moves handed to WF-013 will not "
                "exercise TEST-WF013-TC222's sentinels.")
    else:
        ctx.log(f"valuation category: {category!r}")
    return category


@test_case(
    id="TEST-WF012-TC288",
    name="Validating a project delivery creates exactly one POSTED invoice",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_sale_stock", priority="P0", kind="API", order=12288,
    description="One warehouse click on a project order's delivery leaves "
                "the picking done and exactly one customer invoice posted "
                "and numbered, with invoice_status no longer 'to invoice' "
                "and no UI signal of any kind that it happened.",
    traceability=trace("DATAONE-TC288"))
def test_tc288(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-012 fixtures and open a fresh "
                  "namespace"):
        sweep_wf012(rpc)

    with ctx.step("Preconditions: dto_sale/dto_sale_stock, mail offline, "
                  "the five COGS analytic xmlids, a valuation category"):
        category = _preconditions(ctx)

    try:
        with ctx.step("Step 1: a confirmed project order with an assigned "
                      "outgoing picking and ZERO invoices"):
            product_id = ensure_product(
                ctx, label="P-project", price=10.0, cost=9.0,
                categ_id=category["id"] if category else None)
            order_id, _ = confirm_with_stock(
                ctx, order_type="project", product_id=product_id,
                label="TC288")
            before = invoices_of(rpc, order_id)
            ctx.log(f"invoices before validation: {before!r}")
            ctx.check("invoices before validation", 0, len(before))
            order = rpc.read("sale.order", [order_id],
                             ["invoice_status", "order_type", "name"])[0]
            ctx.log(f"order: {order!r}")
            ctx.check("order_type", "project", order["order_type"])
            # invoice_status before validation is decided by the product's
            # invoice policy, not by this workflow: 'order' bills on the
            # ordered quantity and reads 'to invoice' the moment the order is
            # confirmed, 'delivery' bills on the delivered quantity and
            # correctly reads 'no' until something is delivered. The
            # override under test reads invoice_status AFTER the picking is
            # validated, so it fires on either — and asserting one of them
            # here would only encode the target's product defaults. The
            # policy is read from the product and logged so the expectation
            # is visible rather than assumed.
            policy = rpc.read("product.product", [product_id],
                              ["invoice_policy"])[0]["invoice_policy"]
            ctx.log(f"product invoice_policy = {policy!r}")
            ctx.check(f"invoice_status before validation "
                      f"(invoice_policy={policy!r})",
                      "to invoice" if policy == "order" else "no",
                      order["invoice_status"])

        with ctx.step("Step 2: validate the outgoing picking — this single "
                      "click is the whole trigger"):
            picking = outgoing_picking(ctx, order_id)
            ctx.log(f"picking before validation: {picking!r}")
            result = validate_picking(ctx, picking["id"])
            ctx.check_true(
                "button_validate returned no wizard (the transfer is full)",
                not (isinstance(result, dict) and result.get("res_model")),
                actual_desc=repr(result))

        with ctx.step("Steps 3-4: the picking is done with date_done "
                      "stamped and its moves relieved stock"):
            picking_row = rpc.read("stock.picking", [picking["id"]],
                                   ["state", "date_done"])[0]
            ctx.log(f"picking after validation: {picking_row!r}")
            ctx.check("picking state", "done", picking_row["state"])
            ctx.check_true("date_done is stamped",
                           bool(picking_row["date_done"]),
                           actual_desc=repr(picking_row["date_done"]))
            moves = rpc.search_read("stock.move",
                                    [("picking_id", "=", picking["id"])],
                                    ["state", "quantity", "product_id"])
            ctx.log(f"moves: {moves!r}")
            ctx.check("stock moves not in state done", [],
                      [m["id"] for m in moves if m["state"] != "done"])

        with ctx.step("Steps 5-6 — THE GATE: exactly ONE account.move is "
                      "linked to the order"):
            invoices = invoices_of(rpc, order_id)
            ctx.log(f"invoices after validation: {invoices!r}")
            ctx.check("invoices after validation", 1, len(invoices))

        with ctx.step("Step 7 — THE GATE: that invoice is POSTED and "
                      "numbered; no accountant reviewed it in draft"):
            invoice = invoices[0]
            ctx.check("invoice state", "posted", invoice["state"])
            ctx.check("invoice move_type", "out_invoice",
                      invoice["move_type"])
            ctx.check_true(
                "a sequence number was allocated (name is not the '/' "
                "placeholder)",
                bool(invoice["name"]) and invoice["name"] != "/",
                actual_desc=repr(invoice["name"]))

        with ctx.step("Step 8: the order's invoice_status is no longer "
                      "'to invoice' — which is also the idempotence guard "
                      "TC289 step 9 relies on"):
            status = rpc.read("sale.order", [order_id],
                              ["invoice_status"])[0]["invoice_status"]
            ctx.log(f"invoice_status after validation: {status!r}")
            ctx.check_true("invoice_status is no longer 'to invoice'",
                           status != "to invoice", actual_desc=status)

        with ctx.step("Step 9: record the UI signal the warehouse operator "
                      "received. The workbook's expected answer is NONE"):
            ctx.log("button_validate returned "
                    f"{result!r} — no notification, no wizard, no message "
                    "naming the invoice. The operator has no way to know a "
                    "posted journal entry was just created by their click.")
            ctx.check_true(
                "no UI signal named the invoice",
                not (isinstance(result, dict)
                     and result.get("res_model") == "account.move"),
                actual_desc=repr(result))

        with ctx.step("Step 10: hand the move to the VAL suite. WF-012 "
                      "asserts the TRIGGER; tests/wf013 asserts the "
                      "CONTENT. Neither is acceptance evidence alone"):
            lines = rpc.search_read(
                "account.move.line", [("move_id", "=", invoice["id"])],
                ["name", "account_id", "debit", "credit", "display_type",
                 "analytic_distribution"], order="id")
            ctx.log(f"account.move id={invoice['id']} name={invoice['name']} "
                    f"-> {len(lines)} journal items")
            for line in lines:
                ctx.log(f"  {line!r}")
            ctx.log("DEFERRED to VAL: the line-by-line comparison against "
                    "the WF-013 project-order table, including the is_cogs "
                    "reversal pair and the account 12500 redirect, is "
                    "TEST-WF013-TC222 / TC224. Passing THIS case while "
                    "that one fails is the exact regression WF-012 exists "
                    "to expose.")
            ctx.check_true("the posted move has journal items to hand over",
                           bool(lines), actual_desc=len(lines))
    finally:
        with ctx.step("Cleanup WF-012 fixtures"):
            try:
                sweep_wf012(rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")


@test_case(
    id="TEST-WF012-TC289",
    name="inventory and cost_center auto-invoice; buy does not",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_sale_stock", priority="P0", kind="API", order=12289,
    description="Three deliveries in one run: inventory and cost_center "
                "each produce exactly one posted invoice, buy produces "
                "none and stays 'to invoice', its manual invoice lands in "
                "draft, and a second validation on an already-billed order "
                "produces no second invoice.",
    traceability=trace("DATAONE-TC289"))
def test_tc289(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-012 fixtures and open a fresh "
                  "namespace"):
        sweep_wf012(rpc)

    with ctx.step("Preconditions: dto_sale/dto_sale_stock, mail offline, "
                  "the five COGS analytic xmlids, a valuation category"):
        category = _preconditions(ctx)

    orders = {}
    try:
        with ctx.step("Build one confirmed order per order type, identical "
                      "in every respect except order_type"):
            categ_id = category["id"] if category else None
            for order_type in ("inventory", "cost_center", "buy"):
                product_id = ensure_product(
                    ctx, label=f"P-{order_type}", price=10.0, cost=9.0,
                    categ_id=categ_id)
                order_id, _ = confirm_with_stock(
                    ctx, order_type=order_type, product_id=product_id,
                    label=f"TC289-{order_type}")
                orders[order_type] = order_id
                ctx.log(f"{order_type} order id={order_id}")
            ctx.check("orders confirmed", 3, len(orders))

        # --- the two order types that must auto-invoice ----------------
        results = {}
        for step_no, order_type in ((1, "inventory"), (3, "cost_center")):
            with ctx.step(f"Steps {step_no}-{step_no + 1}: validate the "
                          f"{order_type} delivery and read its invoices"):
                picking = outgoing_picking(ctx, orders[order_type])
                validate_picking(ctx, picking["id"])
                state = rpc.read("stock.picking", [picking["id"]],
                                 ["state"])[0]["state"]
                ctx.check(f"{order_type} picking state", "done", state)
                invoices = invoices_of(rpc, orders[order_type])
                ctx.log(f"{order_type} invoices: {invoices!r}")
                results[order_type] = invoices
                ctx.check(f"{order_type}: invoice count", 1, len(invoices))
                ctx.check(f"{order_type}: invoice state", "posted",
                          invoices[0]["state"])

        # --- the order type that must NOT ------------------------------
        with ctx.step("Steps 5-6 — THE NEGATIVE: validate the buy delivery "
                      "and assert ZERO invoices were created"):
            picking = outgoing_picking(ctx, orders["buy"])
            validate_picking(ctx, picking["id"])
            state = rpc.read("stock.picking", [picking["id"]],
                             ["state"])[0]["state"]
            ctx.check("buy picking state", "done", state)
            buy_invoices = invoices_of(rpc, orders["buy"])
            ctx.log(f"buy invoices: {buy_invoices!r}")
            ctx.check("buy: invoice count after validation", 0,
                      len(buy_invoices))

        with ctx.step("Step 7: the buy order is still awaiting invoicing"):
            status = rpc.read("sale.order", [orders["buy"]],
                              ["invoice_status"])[0]["invoice_status"]
            ctx.check("buy invoice_status", "to invoice", status)

        with ctx.step("Step 8: a manually created buy invoice lands in "
                      "DRAFT — a human reviews it before it reaches the "
                      "customer"):
            manual_id = create_invoice(ctx, orders["buy"])
            if not manual_id:
                ctx.blocked(
                    "The buy order produced nothing invoiceable, so the "
                    "manual path cannot be observed. Check the product's "
                    "invoicing policy and the delivered quantity.")
            manual = rpc.read("account.move", [manual_id],
                              ["state", "name", "move_type"])[0]
            ctx.log(f"manual buy invoice: {manual!r}")
            ctx.check("manual buy invoice state", "draft", manual["state"])

        # --- idempotence ------------------------------------------------
        with ctx.step("Step 9 — THE IDEMPOTENCE GUARD: a second delivery "
                      "on the already-billed inventory order must not "
                      "produce a second invoice"):
            inv_order = orders["inventory"]
            status = rpc.read("sale.order", [inv_order],
                              ["invoice_status"])[0]["invoice_status"]
            ctx.log(f"inventory invoice_status before re-validation: "
                    f"{status!r} (the filter term that makes the override "
                    "idempotent)")
            before = len(invoices_of(rpc, inv_order))
            extra = deliver_order(ctx, inv_order)
            ctx.log(f"pickings after re-validation attempt: {extra!r}")
            after = invoices_of(rpc, inv_order)
            ctx.log(f"inventory invoices after re-validation: {after!r}")
            ctx.check("inventory: no additional invoice for already-billed "
                      "quantities", before, len(after))

        with ctx.step("Step 10: hand every resulting account.move to the "
                      "VAL suite's four-order-type comparison"):
            handover = {
                order_type: [inv["id"] for inv in invs]
                for order_type, invs in results.items()}
            handover["buy (manual, draft)"] = [manual_id]
            ctx.log(f"moves for tests/wf013: {handover!r}")
            ctx.log("DEFERRED to VAL: TEST-WF013-TC223…TC227 compare the "
                    "COGS basis and the AR redirect per order type. This "
                    "case proves only WHICH order types get an invoice.")
            ctx.check("order types that auto-invoiced",
                      ["cost_center", "inventory"],
                      sorted(results))
    finally:
        with ctx.step("Cleanup WF-012 fixtures"):
            try:
                sweep_wf012(rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")
