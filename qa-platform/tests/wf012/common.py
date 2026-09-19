"""Shared fixtures and helpers for the DATAONE-WF-012 suite
(Auto-Invoicing on Delivery Validation).

Owning workflow: DATAONE-WF-012, build order 17, Stage 5 (the rebuild),
effective risk CRITICAL, 9.5 h, depends on WF-011. It owns 3 workbook test
cases: TC288, TC289 (both P0 INTEG) and TC290 (P2, MANUAL_ONLY).

What this workflow is
---------------------
For DataOne's three internally-funded order types — ``project``,
``inventory`` and ``cost_center`` — the shipment IS the billing event. One
warehouse click puts a numbered, posted customer invoice in the ledger.
Verified source (v19-ported tree, ``dto_sale_stock/models/stock_picking.py``)::

    def _action_done(self):
        res = super()._action_done()
        orders = self.sale_id.filtered(lambda r:
            r.order_type in ['project', 'inventory', 'cost_center']
            and r.invoice_status == 'to invoice')
        if orders:
            invoices = orders._create_invoices(final=True)
            if invoices:
                invoices.action_post()
        return res

Two things follow from that shape and both are asserted here:

* ``buy`` is deliberately excluded and must stay excluded — TC289. Widening
  the filter would push unreviewed trade invoices straight to customers.
* the ``invoice_status == 'to invoice'`` term is the idempotence guard: a
  second delivery on an already-billed order must not produce a second
  invoice — TC289 step 9.

The coupling that makes this dangerous
--------------------------------------
Nothing in the auto-invoicing mechanism itself breaks on v19. Delta §8
confirms ``stock.picking._action_done``, ``sale.order._create_invoices``,
``sale.order._prepare_invoice`` and ``account.move.action_post`` are all
unchanged. The code keeps running; what changes is **what it produces** —
the COGS basis, the Interim analytic distribution and the receivable
reversal, all of which live in WF-013.

So this suite deliberately does NOT assert the journal entry line by line.
TC288 step 10 and TC289 step 10 both defer that to the VAL suite, which is
``tests/wf013`` (``TEST-WF013-TC222`` onwards). Asserting "the delivery
worked and an invoice exists" is precisely the green signal that hides a
wrong general ledger; this suite proves the trigger, WF-013 proves the
content, and neither is acceptance evidence on its own.

What this suite DOES assert about the ledger is the one thing WF-013 cannot
see from its own fixtures: that the invoice was created and posted *by the
warehouse click*, inside the delivery transaction, with no accountant in
between — state ``posted``, a real sequence number, and no UI signal of any
kind (TC288 step 9).

Safety
------
Validating a delivery fires ``base.automation``
``dto_sale_stock.base_automation_send_email_on_sale_order_shipped`` and its
server action, which calls ``send_mail(force_send=True)`` against a
hard-coded d1systems.com recipient list. Every fixture therefore goes
through ``require_mail_offline`` and carries a non-empty
``memo_to_suppliers`` — an empty memo raises ``TypeError`` inside the
validation transaction and aborts the delivery (the E7 defect, TC290).
"""
from __future__ import annotations

import uuid

from adapters.base import OdooRPCError
from framework.dto_fixtures import (create_invoice, deliver_order,  # noqa: F401
                                    gate_analytic, order_invoices,
                                    order_pickings, set_stock,
                                    validate_picking)
from framework.fg_common import m2o_id, make_trace  # noqa: F401
from framework.qa_fixtures import (require_mail_offline,  # noqa: F401
                                   sweep_model, sweep_products, with_categ)

WORKFLOW = "DATAONE-WF-012"
WORKFLOW_NAME = "Auto-Invoicing on Delivery Validation"
FEATURE = "DATAONE-WF-012 Auto-Invoicing on Delivery Validation"
MARK = "WF012"

trace = make_trace(FEATURE)

# dto_sale_stock/models/stock_picking.py — the auto-invoice filter. These
# three auto-invoice; 'buy' does not. TC289 is the whole of this table.
AUTO_INVOICE_ORDER_TYPES = ("project", "inventory", "cost_center")
MANUAL_INVOICE_ORDER_TYPES = ("buy",)

# dto_mrp_account/models/stock_picking.py:10 — the validation gate. v19
# removed BaseModel.user_has_groups(); the ported tree calls
# self.env.user.has_group() with the same xml id.
DELIVERY_VALIDATION_GROUP = "dto_mrp_account.group_validate_delivery_orders"
DELIVERY_GATE_MESSAGE = ("Only users in the 'Validate Delivery Orders' group "
                         "can validate this picking.")

# dto_sale_stock/data/base_automation_data.xml, all under <data noupdate="1">
# — so a module upgrade does NOT refresh them and TC290 must read what the
# database actually holds, not what the source tree says.
SHIPMENT_AUTOMATION_XMLID = (
    "dto_sale_stock.base_automation_send_email_on_sale_order_shipped")
SHIPMENT_SERVER_ACTION_XMLID = (
    "dto_sale_stock.action_server_send_email_on_sale_order_shipped")
SHIPMENT_TEMPLATE_XMLID = "dto_sale_stock.mail_template_delivery_validated"

# The recipient mapping the server action codes, per order type. Verified in
# dto_sale_stock/data/base_automation_data.xml:44-52.
SHIPMENT_RECIPIENTS = {
    "project": ["mfgestimating@d1systems.com", "procurement@d1systems.com"],
    "buy": ["mfgestimating@d1systems.com", "orders@d1systems.com",
            "procurement@d1systems.com"],
    "inventory": ["mfgestimating@d1systems.com",
                  "miguel.oyervidez@d1systems.com",
                  "procurement@d1systems.com"],
    "cost_center": ["mfgestimating@d1systems.com",
                    "procurement@d1systems.com"],
}
IRM_RECIPIENT = "D1CienaIRM@d1systems.com"

_TOKEN = "init"


def fixture_token() -> str:
    return _TOKEN


def fx(name: str) -> str:
    return f"{name} [{_TOKEN}]"


def sweep_wf012(rpc):
    """Open a fresh fixture namespace, then remove marker-scoped leftovers.

    Best-effort by design: this workflow's whole point is that it POSTS
    invoices, and a posted journal entry cannot be unlinked while a done
    delivery cannot be undone. The fresh token is what guarantees isolation —
    anything that survives the sweep cannot collide with this execution's
    "exactly one invoice" assertions, because every search is token-scoped.
    """
    global _TOKEN
    _TOKEN = uuid.uuid4().hex[:6]

    invoice_moves = rpc.search(
        "account.move", [("invoice_origin", "like", f"{MARK} %")])
    for move_id in invoice_moves:
        for method in ("button_draft", "button_cancel"):
            try:
                rpc.call("account.move", method, [move_id])
            except OdooRPCError:
                pass
        try:
            rpc.call("account.move", "unlink", [move_id])
        except OdooRPCError:
            pass

    orders = rpc.search("sale.order", [("origin", "like", f"{MARK} %"),
                                       ("active", "in", [True, False])])
    if orders:
        try:
            rpc.write("sale.order", orders, {"state": "draft"})
        except OdooRPCError:
            pass
        try:
            rpc.call("sale.order", "unlink", orders)
        except OdooRPCError:
            try:
                rpc.write("sale.order", orders, {"active": False})
            except OdooRPCError:
                pass

    sweep_products(rpc, MARK)
    # make_sale_order now satisfies dto_account's Gate 2 through
    # gate_analytic(label=f"{MARK} WF012"), which CREATES analytic accounts
    # carrying MARK. No other suite sweeps them for wf012, so without this
    # every run leaks two of them. Nine sibling suites sweep the same model
    # for the same reason.
    sweep_model(rpc, "account.analytic.account",
                [("name", "like", f"{MARK} %"),
                 ("active", "in", [True, False])])
    sweep_model(rpc, "res.partner", [("name", "like", f"{MARK} %"),
                                     ("user_ids", "=", False),
                                     ("active", "in", [True, False])])


# ---------------------------------------------------------------- probes
def require_auto_invoice_stack(ctx):
    """BLOCK unless dto_sale_stock and dto_sale are installed.

    ``sale.order.order_type`` is the field the whole filter branches on. The
    field lives in ``dto_sale``; the override lives in ``dto_sale_stock``.
    Either one missing makes every assertion in this suite vacuous rather
    than failing, which is the outcome convention rule 5 exists to prevent.
    """
    rpc = ctx.adapter.rpc
    if not rpc.field_exists("sale.order", "order_type"):
        ctx.blocked(
            "sale.order.order_type does not exist on "
            f"{ctx.env.key} (db={ctx.env.db}) — dto_sale is not installed, "
            "and the auto-invoice filter in "
            "dto_sale_stock.stock.picking._action_done reads exactly that "
            "field. Without it nothing in WF-012 can be observed.")
    if not rpc.field_exists("stock.picking", "sale_id"):
        ctx.blocked(
            "stock.picking.sale_id does not exist — sale_stock is not "
            "installed, so a delivery has no order to invoice.")


def require_cogs_analytics(ctx):
    """BLOCK unless the five analytic xmlids dto_account_cogs resolves exist.

    Posting a customer invoice runs ``dto_account_cogs.account.move._post``,
    which calls ``env.ref()`` on five analytic accounts. A missing one makes
    EVERY post raise ValueError — and here the post happens inside the
    delivery transaction, so the symptom is a blocked shipment, not a
    failed invoice. Probing up front turns that into a precise BLOCKED
    reason instead of an obscure failure attributed to the warehouse.
    """
    rpc = ctx.adapter.rpc
    xmlids = [
        "dto_account.analytic_account_revenue_category_service_sales",
        "dto_account.analytic_account_cost_center_180008",
        "dto_account.analytic_account_revenue_category_manufacturing_sales",
        "dto_account.analytic_account_spend_category_consumables",
        "dto_account.analytic_account_cost_center_202000",
    ]
    missing = [x for x in xmlids if not rpc.ref(x)]
    if missing:
        ctx.blocked(
            "These analytic-account xmlids do not resolve on "
            f"{ctx.env.key}: {', '.join(missing)}. dto_account_cogs "
            "resolves them with env.ref() during _post, and WF-012 posts "
            "INSIDE the delivery transaction — so while they are missing "
            "every delivery of a project/inventory/cost_center order is "
            "blocked, not just its invoice.")


def realtime_category(ctx):
    """A fully configured real-time-valuation product.category, or None.

    Not strictly required for WF-012's own assertions (the invoice is
    created either way), but the handoff to WF-013 is only meaningful when
    the anglo-saxon COGS pair is actually produced, so the category is
    logged and preferred when one exists.
    """
    rpc = ctx.adapter.rpc
    if not rpc.field_exists("product.category", "property_valuation"):
        return None
    wanted = ["property_stock_valuation_account_id",
              "property_account_expense_categ_id"]
    fields_ = ["name"] + [f for f in wanted
                          if rpc.field_exists("product.category", f)]
    rows = rpc.search_read("product.category",
                           [("property_valuation", "=", "real_time")],
                           fields_)
    if not rows:
        return None
    complete = [r for r in rows
                if all(r.get(f) for f in wanted if f in fields_)]
    return complete[0] if complete else rows[0]


# -------------------------------------------------------------- fixtures
def ensure_partner(rpc, label="Customer") -> int:
    name = fx(f"{MARK} {label}")
    found = rpc.search("res.partner", [("name", "=", name)], limit=1)
    return found[0] if found else rpc.create("res.partner", {"name": name})


def ensure_product(ctx, label="Item", price=10.0, cost=9.0,
                   categ_id=None) -> int:
    """A storable product priced 10.00 at a cost of 9.00 — TD-P-01's shape."""
    rpc = ctx.adapter.rpc
    name = fx(f"{MARK} {label}")
    found = rpc.search_read("product.product", [("name", "=", name)],
                            ["id"], limit=1)
    if found:
        return found[0]["id"]
    values = {"name": name, "list_price": price, "standard_price": cost,
              "sale_ok": True, "purchase_ok": True, "taxes_id": [(6, 0, [])]}
    values.update(ctx.adapter.storable_product_values())
    if categ_id:
        values["categ_id"] = categ_id
    tmpl_id = rpc.create("product.template", with_categ(rpc, values))
    variant = rpc.search_read("product.product",
                              [("product_tmpl_id", "=", tmpl_id)],
                              ["id"], limit=1)
    return variant[0]["id"]


def make_sale_order(ctx, order_type="project", qty=1.0, price=10.0,
                    product_id=None, label="Order", partner_id=None,
                    memo=None, analytic=None, requester_email=None):
    """A confirmable DataOne sales order of the given type.

    Carries the three confirmation gates dto_sale enforces: a promised ship
    date on every line, a requester email, and a non-empty memo. ``memo``
    can be passed as ``""`` deliberately — that is TC290's negative fixture,
    and the resulting TypeError aborts the DELIVERY, not the confirmation.
    """
    rpc = ctx.adapter.rpc
    partner_id = partner_id or ensure_partner(rpc)
    product_id = product_id or ensure_product(ctx)
    line = {"product_id": product_id, "product_uom_qty": qty,
            "price_unit": price, "requested_delivery_date": "2099-12-31"}
    # A FOURTH confirmation gate, deployed with Stage 7: dto_account refuses
    # a 'project' order whose lines carry no account on the Project plan
    # ('Project is required') and a 'buy' order without one on the Customer
    # Contract plan ('Customer Contract is required') — see gate_analytic.
    # WF-012 asserts on what happens AFTER confirmation, so the gate is
    # satisfied here rather than fought. An explicit `analytic` still wins,
    # which is how TC289 varies it per order type.
    if analytic is None:
        analytic = gate_analytic(ctx, order_type, label=f"{MARK} WF012")
    if analytic:
        line["analytic_distribution"] = analytic
    values = {
        "partner_id": partner_id,
        "origin": fx(f"{MARK} {label}"),
        "order_type": order_type,
        "order_line": [(0, 0, line)],
    }
    if rpc.field_exists("sale.order", "requester_email"):
        values["requester_email"] = (
            requester_email or f"qa.wf012.{order_type}@example.invalid")
    if rpc.field_exists("sale.order", "memo_to_suppliers"):
        values["memo_to_suppliers"] = (
            f"{MARK} QA memo" if memo is None else memo)
    return rpc.create("sale.order", values)


def confirm_with_stock(ctx, order_type="project", qty=1.0, price=10.0,
                       product_id=None, label="Order", stock_qty=100.0,
                       memo=None, analytic=None):
    """Stock -> create -> confirm. Returns (order_id, product_id).

    Every step is checked so a failure is attributed where it happened
    rather than surfacing later as "no invoice was created".
    """
    rpc = ctx.adapter.rpc
    product_id = product_id or ensure_product(ctx, label=f"P-{order_type}")
    set_stock(ctx, product_id, stock_qty)
    order_id = make_sale_order(ctx, order_type=order_type, qty=qty,
                               price=price, product_id=product_id,
                               label=label, memo=memo, analytic=analytic)
    rpc.call("sale.order", "action_confirm", [order_id])
    state = rpc.read("sale.order", [order_id], ["state"])[0]["state"]
    if state != "sale":
        ctx.blocked(
            f"The {order_type} fixture order did not confirm "
            f"(state={state!r}). WF-012 can only be observed on a confirmed "
            "order that generated an outgoing picking.")
    return order_id, product_id


def outgoing_picking(ctx, order_id):
    """The single outgoing picking of a confirmed order, or BLOCKED."""
    rpc = ctx.adapter.rpc
    pickings = order_pickings(rpc, order_id, "outgoing")
    if not pickings:
        ctx.blocked(
            f"Order {order_id} generated no outgoing picking, so there is "
            "no delivery validation to trigger. Check the product's route "
            "and the warehouse configuration on this database.")
    return pickings[0]


def invoices_of(rpc, order_id, fields_=None):
    """The account.move records linked to a sale order, newest id last."""
    fields_ = fields_ or ["name", "state", "move_type", "amount_total",
                          "invoice_origin"]
    rows = order_invoices(rpc, order_id, fields_)
    return sorted(rows, key=lambda r: r["id"])


def expect_error(rpc_callable, *args, **kwargs):
    """(raised, message) — never let an expected failure escape as ERROR."""
    try:
        rpc_callable(*args, **kwargs)
        return False, "no error raised"
    except OdooRPCError as exc:
        return True, str(exc)
