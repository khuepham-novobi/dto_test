"""Shared business fixtures for the DataOne workflow suites.

Several workflows need the same expensive setup — a storable product with
stock, a confirmed sales order, a validated outgoing delivery, a posted
customer invoice — and they need it built the same way on Odoo 17 and 19.
Building it once here keeps the version differences in ``adapters/`` and
out of the test bodies (convention: "no version branches in test bodies").

Everything here is version-agnostic. The two places the versions genuinely
differ are already absorbed:

* storable-product values come from ``ctx.adapter.storable_product_values()``
  (v17 ``type='product'``; v19 ``type='consu'`` + ``is_storable=True``);
* the list view type comes from ``ctx.adapter.list_view_type``.

Verified against both trees:

* ``stock.quant.inventory_quantity_auto_apply`` exists on v17
  (stock_quant.py:102) and v19 (:100) with an inverse that applies the count
  immediately — the cleanest programmatic way to stock a product without
  driving the inventory-adjustment wizard;
* ``stock.picking.button_validate`` is public on v17 (stock_picking.py:1131)
  and v19 (:1413);
* ``stock.move.picked`` exists on v17 (stock_move.py:111) and v19 (:121).

Safety: nothing here touches a record it did not create. Stock is written
only for the caller's own product, and only in the warehouse's own stock
location.
"""
from __future__ import annotations

from adapters.base import OdooRPCError
from framework.fg_common import m2o_id


def stock_location(rpc, company_id=None) -> int | None:
    """The default internal stock location of the company's warehouse."""
    domain = [("active", "=", True)]
    if company_id:
        domain.append(("company_id", "in", [company_id, False]))
    warehouses = rpc.search_read("stock.warehouse", domain, ["lot_stock_id"],
                                 limit=1)
    if warehouses:
        return m2o_id(warehouses[0]["lot_stock_id"])
    internal = rpc.search("stock.location",
                          [("usage", "=", "internal")], limit=1)
    return internal[0] if internal else None


def set_stock(ctx, product_id: int, quantity: float,
              location_id: int | None = None) -> int | None:
    """Put ``quantity`` of ``product_id`` on hand, and return the quant id.

    Uses ``inventory_quantity_auto_apply``, whose inverse applies the count
    straight away — no wizard, no scheduled action. Returns None (having
    logged the reason) when the environment has no usable stock location, so
    the caller can decide whether that is fatal.
    """
    rpc = ctx.adapter.rpc
    location_id = location_id or stock_location(rpc)
    if not location_id:
        ctx.log("[warn] no internal stock location found — stock not set")
        return None
    found = rpc.search("stock.quant",
                       [("product_id", "=", product_id),
                        ("location_id", "=", location_id)], limit=1)
    if found:
        rpc.write("stock.quant", found,
                  {"inventory_quantity_auto_apply": quantity})
        return found[0]
    return rpc.create("stock.quant", {
        "product_id": product_id,
        "location_id": location_id,
        "inventory_quantity_auto_apply": quantity,
    })


def order_pickings(rpc, order_id: int, code: str = "outgoing") -> list:
    """The pickings a sales order generated, filtered by operation code."""
    if not rpc.field_exists("stock.picking", "sale_id"):
        return []
    domain = [("sale_id", "=", order_id)]
    rows = rpc.search_read("stock.picking", domain,
                           ["name", "state", "picking_type_id"])
    if not rows:
        return []
    type_ids = {m2o_id(r["picking_type_id"]) for r in rows}
    types = rpc.read("stock.picking.type", sorted(t for t in type_ids if t),
                     ["code"])
    by_type = {t["id"]: t["code"] for t in types}
    return [r for r in rows
            if by_type.get(m2o_id(r["picking_type_id"])) == code]


def validate_picking(ctx, picking_id: int, full: bool = True):
    """Set the done quantities and validate a picking.

    Returns whatever ``button_validate`` returned — ``True`` on a clean
    validation, or an action dict when Odoo wants a wizard (a backorder
    confirmation, typically, which only appears for a partial transfer).
    With ``full=True`` every move is completed, so no backorder wizard is
    expected; the return value is logged either way so a surprise is visible
    in the execution record.
    """
    rpc = ctx.adapter.rpc
    moves = rpc.search_read("stock.move",
                            [("picking_id", "=", picking_id)],
                            ["product_uom_qty", "quantity", "product_id"])
    for move in moves:
        values = {"picked": True}
        if full:
            values["quantity"] = move["product_uom_qty"]
        rpc.write("stock.move", [move["id"]], values)
    result = rpc.call("stock.picking", "button_validate", [picking_id])
    ctx.log(f"button_validate({picking_id}) -> {result!r}")
    if isinstance(result, dict) and result.get("res_model"):
        ctx.log(f"[warn] validation asked for a {result['res_model']} "
                "wizard; the picking is NOT done")
    return result


def deliver_order(ctx, order_id: int) -> list:
    """Validate every outgoing picking of a confirmed order.

    Returns the picking rows after validation so the caller can assert on
    their state rather than trusting the call.
    """
    rpc = ctx.adapter.rpc
    pickings = order_pickings(rpc, order_id)
    for picking in pickings:
        if picking["state"] in ("done", "cancel"):
            continue
        try:
            rpc.call("stock.picking", "action_assign", [picking["id"]])
        except OdooRPCError as exc:
            ctx.log(f"[warn] action_assign on {picking['name']}: {exc}")
        validate_picking(ctx, picking["id"])
    return order_pickings(rpc, order_id)


def order_invoices(rpc, order_id: int, fields_=None) -> list:
    fields_ = fields_ or ["name", "state", "move_type", "amount_total",
                          "invoice_date"]
    invoice_ids = rpc.read("sale.order", [order_id],
                           ["invoice_ids"])[0]["invoice_ids"]
    if not invoice_ids:
        return []
    return rpc.read("account.move", invoice_ids, fields_)


# The wizard refuses to run when the order has nothing invoiceable - a
# delivery-policy product with nothing delivered, typically. Odoo raises a
# UserError, not an empty result: sale.order._nothing_to_invoice_error_message
# (v19 sale/models/sale_order.py:1485, v17 :1233), whose text is identical on
# both versions. Callers of create_invoice() already branch on a None return,
# so the refusal is translated into that rather than surfacing as an
# AUTOMATION_ERROR that hides whatever the case was actually asserting.
NOTHING_TO_INVOICE = (
    "no items are available to invoice",
    "nothing to invoice",
    "no invoiceable line",
    "invoicing policy",
)


def create_invoice(ctx, order_id: int) -> int | None:
    """Create the customer invoice for a confirmed order, without posting.

    Uses ``sale.advance.payment.inv`` — the wizard the Create Invoice button
    drives — because ``sale.order._create_invoices`` is private and cannot
    be dispatched over RPC.

    Returns ``None`` (having logged the reason) when Odoo refuses because
    there is nothing invoiceable yet, so the caller can decide whether that
    is fatal — ``sell_and_invoice`` treats it as BLOCKED, TC070/TC094 treat
    it as "the invoice half is not applicable here".
    """
    rpc = ctx.adapter.rpc
    wizard_id = rpc.call(
        "sale.advance.payment.inv", "create",
        {"advance_payment_method": "delivered"},
        context={"active_model": "sale.order", "active_ids": [order_id],
                 "active_id": order_id})
    try:
        rpc.call("sale.advance.payment.inv", "create_invoices", [wizard_id],
                 context={"active_model": "sale.order",
                          "active_ids": [order_id],
                          "active_id": order_id})
    except OdooRPCError as exc:
        message = str(exc).lower()
        if not any(token in message for token in NOTHING_TO_INVOICE):
            raise
        ctx.log(f"[warn] create_invoices refused for sale.order {order_id}: "
                f"{exc}")
        return None
    invoices = order_invoices(rpc, order_id, ["id", "state"])
    return invoices[-1]["id"] if invoices else None
