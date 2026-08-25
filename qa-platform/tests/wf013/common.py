"""Shared fixtures and helpers for the DATAONE-WF-013 suite
(Customer Invoice Posting: COGS and Revenue Recognition).

Owning workflow: DATAONE-WF-013, build order 20 (Stage 5 — the rebuild),
effective risk CRITICAL, 47 h. It owns 39 workbook test cases, 30 of them
P0 — the largest and highest-risk block in the wave.

The finding this suite exists to catch
--------------------------------------
``dto_account_cogs`` and ``dto_account`` both override
``_stock_account_prepare_anglo_saxon_out_lines_vals``, and
``dto_account_cogs`` also overrides
``_stock_account_get_anglo_saxon_price_unit``. Verified against both trees:

============================================  ======================  ======================
Method                                        Odoo 17                 Odoo 19
============================================  ======================  ======================
_stock_account_prepare_anglo_saxon_out_        stock_account/models/   **renamed** to
lines_vals                                    account_move.py:79      _stock_account_prepare_
                                                                      realtime_out_lines_vals
                                                                      (:68)
_stock_account_get_anglo_saxon_price_unit      stock_account/models/   **removed**; replaced
                                              account_move.py:310,    by _get_cogs_value() +
                                              sale_stock:151          _get_anglo_saxon_price_
                                                                      ctx() (:122, :163)
============================================  ======================  ======================

Neither override raises on v19 — they simply **stop being called**. The
COGS and Interim analytic distribution, and the project / inventory /
cost_center price rules, disappear silently. TC222 is the case that catches
it, and it is the highest-value test in this suite.

Environment dependencies
------------------------
The COGS cases need a database configured for anglo-saxon accounting with
real-time valuation, an ``asset_receivable`` account coded ``12500``, and
the five analytic accounts ``dto_account_cogs`` resolves by xmlid (shipped
in ``dto_account/data/account.analytic.account.csv``). Every one of those
is probed up front and produces a precise BLOCKED reason rather than an
obscure failure deep in a posting.

Safety
------
Posting a customer invoice is preceded by confirming its sales order, which
fires ``dto_sale``'s confirmation automation and its hard-coded
d1systems.com recipient list. Every fixture that confirms therefore goes
through ``require_mail_offline`` and carries a non-empty
``memo_to_suppliers`` — see ``tests/wf002/common.py`` for why.
"""
from __future__ import annotations

import uuid

from adapters.base import OdooRPCError
from framework.dto_fixtures import (create_invoice, deliver_order,  # noqa: F401
                                    order_invoices, set_stock)
from framework.fg_common import m2o_id, make_trace  # noqa: F401
from framework.qa_fixtures import (require_mail_offline,  # noqa: F401
                                   sweep_model, sweep_products)

WORKFLOW = "DATAONE-WF-013"
WORKFLOW_NAME = "Customer Invoice Posting: COGS and Revenue Recognition"
FEATURE = ("DATAONE-WF-013 Customer Invoice Posting: COGS and Revenue "
           "Recognition")
MARK = "WF013"

trace = make_trace(FEATURE)

# The v17 hook names dto_account_cogs / dto_account override, and what v19
# renamed them to. TC222 turns this table into an assertion.
ANGLO_SAXON_HOOKS = {
    "17": {
        "prepare": "_stock_account_prepare_anglo_saxon_out_lines_vals",
        "price_unit": "_stock_account_get_anglo_saxon_price_unit",
    },
    "19": {
        "prepare": "_stock_account_prepare_realtime_out_lines_vals",
        "price_unit": None,     # removed; _get_cogs_value takes its place
    },
}

# dto_account_cogs/models/account_move.py:160-174 — resolved by env.ref(),
# so a missing one makes every customer-invoice post raise.
COGS_ANALYTIC_XMLIDS = [
    "dto_account.analytic_account_revenue_category_service_sales",
    "dto_account.analytic_account_cost_center_180008",
    "dto_account.analytic_account_revenue_category_manufacturing_sales",
    "dto_account.analytic_account_spend_category_consumables",
    "dto_account.analytic_account_cost_center_202000",
]

# dto_account_cogs/models/account_move.py:213 — the AR redirect target.
ACCRUED_REVENUE_CODE = "12500"

# dto_account/security/ir.model.access.csv — the account.move delete rule.
MOVE_UNLINK_GROUP = "base.group_system"
MOVE_NO_UNLINK_GROUPS = ["account.group_account_invoice",
                         "purchase.group_purchase_user"]

_TOKEN = "init"


def fixture_token() -> str:
    return _TOKEN


def fx(name: str) -> str:
    return f"{name} [{_TOKEN}]"


def sweep_wf013(rpc):
    """Open a fresh fixture namespace, then remove marker-scoped leftovers.

    Posted journal entries cannot be unlinked, and delivered stock moves
    cannot be undone. The sweep is therefore best-effort by design: it
    resets what it can to draft and removes what it may, and the fresh
    token guarantees anything that survives cannot collide with this
    execution's assertions.
    """
    global _TOKEN
    _TOKEN = uuid.uuid4().hex[:6]

    moves = rpc.search("account.move", [("ref", "like", f"{MARK} %")]) \
        if rpc.field_exists("account.move", "ref") else []
    invoice_moves = rpc.search(
        "account.move", [("invoice_origin", "like", f"{MARK} %")])
    for move_id in set(moves) | set(invoice_moves):
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
    sweep_model(rpc, "res.partner", [("name", "like", f"{MARK} %"),
                                     ("user_ids", "=", False),
                                     ("active", "in", [True, False])])
    sweep_model(rpc, "account.analytic.account",
                [("name", "like", f"{MARK} %"),
                 ("active", "in", [True, False])])


# ---------------------------------------------------------------- probes
def require_cogs_stack(ctx):
    """BLOCK unless dto_account_cogs is installed."""
    rpc = ctx.adapter.rpc
    if not rpc.field_exists("account.move.line", "is_cogs"):
        ctx.blocked(
            "account.move.line.is_cogs does not exist on "
            f"{ctx.env.key} (db={ctx.env.db}) — dto_account_cogs is not "
            "installed, so none of WF-013's reversal behaviour exists to "
            "be tested.")
    if not rpc.field_exists("sale.order", "order_type"):
        ctx.blocked(
            "sale.order.order_type does not exist — dto_sale is not "
            "installed, and every COGS rule in WF-013 branches on it.")


def require_anglo_saxon(ctx):
    """BLOCK unless the company uses anglo-saxon accounting.

    ``_prepare_reverse_revenue_lines_vals`` skips every move whose company
    has ``anglo_saxon_accounting`` off, so the whole suite would silently
    assert nothing.
    """
    rpc = ctx.adapter.rpc
    company_id = m2o_id(rpc.read("res.users", [rpc.uid],
                                 ["company_id"])[0]["company_id"])
    row = rpc.read("res.company", [company_id],
                   ["name", "anglo_saxon_accounting"])[0]
    if not row.get("anglo_saxon_accounting"):
        ctx.blocked(
            f"Company {row['name']!r} has anglo_saxon_accounting OFF on "
            f"{ctx.env.key}. dto_account_cogs._prepare_reverse_revenue_"
            "lines_vals skips every move in that case, so the reversal "
            "lines this workflow is about are never created and the test "
            "would assert nothing.")
    return company_id


def require_cogs_analytic_accounts(ctx):
    """BLOCK unless all five env.ref() targets resolve.

    A missing one makes ``_post`` raise on every customer invoice, which is
    exactly the failure mode TC229 describes.
    """
    rpc = ctx.adapter.rpc
    missing = [x for x in COGS_ANALYTIC_XMLIDS if not rpc.ref(x)]
    if missing:
        ctx.blocked(
            "These analytic-account xmlids do not resolve on "
            f"{ctx.env.key}: {', '.join(missing)}. dto_account_cogs "
            "resolves them with env.ref() during _post, so while they are "
            "missing EVERY customer-invoice post raises ValueError. Load "
            "dto_account/data/account.analytic.account.csv before running "
            "WF-013.")
    return {x: rpc.ref(x) for x in COGS_ANALYTIC_XMLIDS}


def accrued_revenue_account(rpc):
    """The 12500 asset_receivable account the AR redirect targets, or None."""
    rows = rpc.search_read("account.account",
                           [("code", "=", ACCRUED_REVENUE_CODE),
                            ("account_type", "=", "asset_receivable")],
                           ["code", "name"], limit=1)
    return rows[0] if rows else None


def realtime_category(ctx):
    """A product category with real-time valuation, or None.

    Without one the invoice produces no anglo-saxon COGS lines at all, so
    every COGS assertion would be vacuous.
    """
    rpc = ctx.adapter.rpc
    if not rpc.field_exists("product.category", "property_valuation"):
        return None
    rows = rpc.search_read("product.category",
                           [("property_valuation", "=", "real_time")],
                           ["name", "property_cost_method"], limit=1)
    return rows[0] if rows else None


# -------------------------------------------------------------- fixtures
def ensure_partner(rpc, label="Customer") -> int:
    name = fx(f"{MARK} {label}")
    found = rpc.search("res.partner", [("name", "=", name)], limit=1)
    return found[0] if found else rpc.create("res.partner", {"name": name})


def ensure_product(ctx, label="Item", price=10.0, cost=9.0,
                   categ_id=None) -> int:
    """A storable product priced 10.00 with a standard cost of 9.00 — the
    shape the module's own docstring uses for its worked example."""
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
    tmpl_id = rpc.create("product.template", values)
    variant = rpc.search_read("product.product",
                              [("product_tmpl_id", "=", tmpl_id)],
                              ["id"], limit=1)
    return variant[0]["id"]


def ensure_analytic_account(rpc, plan_xmlid, label) -> int:
    plan_id = rpc.ref(plan_xmlid)
    name = fx(f"{MARK} {label}")
    found = rpc.search("account.analytic.account",
                       [("name", "=", name), ("plan_id", "=", plan_id)],
                       limit=1)
    if found:
        return found[0]
    return rpc.create("account.analytic.account",
                      {"name": name, "plan_id": plan_id})


def make_sale_order(ctx, order_type="project", analytic=None, qty=1.0,
                    price=10.0, product_id=None, label="Order",
                    partner_id=None):
    """A confirmable DataOne sales order of the given type.

    Carries everything the three confirmation gates need: a promised ship
    date on every line, a requester email, and a non-empty memo (without
    which dto_sale's confirmation automation raises TypeError — see
    DATAONE-TC085).
    """
    rpc = ctx.adapter.rpc
    partner_id = partner_id or ensure_partner(rpc)
    product_id = product_id or ensure_product(ctx)
    line = {"product_id": product_id, "product_uom_qty": qty,
            "price_unit": price, "requested_delivery_date": "2099-12-31"}
    if analytic:
        line["analytic_distribution"] = analytic
    values = {
        "partner_id": partner_id,
        "origin": fx(f"{MARK} {label}"),
        "order_type": order_type,
        "order_line": [(0, 0, line)],
    }
    if rpc.field_exists("sale.order", "requester_email"):
        values["requester_email"] = "qa.wf013@example.invalid"
    if rpc.field_exists("sale.order", "memo_to_suppliers"):
        values["memo_to_suppliers"] = f"{MARK} QA memo"
    return rpc.create("sale.order", values)


def sell_and_invoice(ctx, order_type="project", analytic=None, qty=1.0,
                     price=10.0, product_id=None, label="Order",
                     stock_qty=100.0, post=True):
    """The full WF-013 fixture: stock -> confirm -> deliver -> invoice
    [-> post]. Returns (order_id, invoice_id).

    Every step goes through a public entry point, and every one is checked,
    so a failure is attributed to the step that caused it rather than
    surfacing later as a missing journal item.
    """
    rpc = ctx.adapter.rpc
    product_id = product_id or ensure_product(ctx)
    set_stock(ctx, product_id, stock_qty)

    order_id = make_sale_order(ctx, order_type=order_type, analytic=analytic,
                               qty=qty, price=price, product_id=product_id,
                               label=label)
    rpc.call("sale.order", "action_confirm", [order_id])
    state = rpc.read("sale.order", [order_id], ["state"])[0]["state"]
    if state != "sale":
        ctx.blocked(f"The {order_type} fixture order did not confirm "
                    f"(state={state!r}) — the COGS assertions need a "
                    "delivered, invoiced order.")

    pickings = deliver_order(ctx, order_id)
    if pickings and any(p["state"] != "done" for p in pickings):
        ctx.blocked(
            "The outgoing picking did not reach 'done' "
            f"({pickings!r}). Anglo-saxon COGS lines are only produced for "
            "delivered quantities, so the assertions would be vacuous.")

    invoice_id = create_invoice(ctx, order_id)
    if not invoice_id:
        ctx.blocked(
            f"No customer invoice was produced for the {order_type} "
            "fixture order. Check the product's invoicing policy and the "
            "delivered quantity on this database.")
    rpc.write("account.move", [invoice_id],
              {"invoice_date": "2026-01-15"})
    if post:
        rpc.call("account.move", "action_post", [invoice_id])
    return order_id, invoice_id


def move_lines(rpc, move_id, fields_=None):
    fields_ = fields_ or ["name", "account_id", "display_type", "debit",
                          "credit", "balance", "quantity", "price_unit",
                          "analytic_distribution", "is_cogs", "product_id"]
    return rpc.search_read("account.move.line", [("move_id", "=", move_id)],
                           fields_, order="id")


def lines_by_account_type(rpc, move_id):
    """{account_type: [line dicts]} for one move."""
    lines = move_lines(rpc, move_id)
    account_ids = sorted({m2o_id(ln["account_id"]) for ln in lines
                          if m2o_id(ln["account_id"])})
    types = {a["id"]: a["account_type"] for a in
             rpc.read("account.account", account_ids, ["account_type"])}
    grouped: dict = {}
    for line in lines:
        key = types.get(m2o_id(line["account_id"]), "unknown")
        grouped.setdefault(key, []).append(line)
    return grouped


def expect_error(rpc_callable, *args, **kwargs):
    try:
        rpc_callable(*args, **kwargs)
        return False, "no error raised"
    except OdooRPCError as exc:
        return True, str(exc)
