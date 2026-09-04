"""Shared fixtures and helpers for the DATAONE-WF-002 suite
(Quotation -> sales order confirmation).

Owning workflow: DATAONE-WF-002, build order 4 (Stage 1), effective risk
HIGH. Modules under test: dto_sale (order type, promised ship date, tariff,
delivery performance), dto_account (the three analytic gates),
dto_sale_workday (the requester-email gate and the memo), and
dto_sale_price_formula (NTT unit price).

The confirmation side effect every fixture must respect
-------------------------------------------------------
Confirming a sales order fires ``base_automation``
``dto_sale.base_automation_send_email_on_sale_order_confirm``, whose server
action ends in::

    if 'IRM' in order.memo_to_suppliers:
        ...
    template.send_mail(order.id, force_send=True,
                       email_values={'email_to': email_to})

Two consequences the suite is built around:

1. ``memo_to_suppliers`` is a Text field defaulting to ``False``, and
   ``'IRM' in False`` raises ``TypeError`` — which aborts the confirmation.
   That is the live defect DATAONE-TC085 documents, and it means every
   *other* fixture that will be confirmed must carry a non-empty memo or it
   fails for a reason unrelated to the case under test.
   ``make_quotation`` therefore sets one by default; TC085 passes
   ``memo=""`` deliberately.
2. The recipient list is hard-coded to real d1systems.com addresses and the
   send is ``force_send=True``. Every test that confirms an order calls
   ``require_mail_offline(ctx)`` first, which BLOCKS unless every
   ``ir.mail_server`` is deactivated. Convention rule 4.

Other confirmation preconditions, verified in source:

* ``dto_sale.action_confirm`` raises ``Please enter 'Promised Ship Date'
  for all order lines.`` unless every product line carries
  ``requested_delivery_date`` (dto_sale/models/sale_order.py:59);
* ``dto_sale_workday.action_confirm`` raises ``Please enter Requester
  email`` unless ``requester_email`` is set
  (dto_sale_workday/models/sale_order.py:25);
* ``dto_account.action_confirm`` runs ``validate_analytic_distribution()``
  first, which dispatches to
  ``_validate_analytic_distribution_<order_type>``
  (dto_account/models/sale_order.py:11).

Live-DB determinism: every fixture carries the WF002 marker plus a
per-execution token in ``origin`` and in each record's name, and sweeps
scope on those. ``sale.order.name`` is left to the sequence.
"""
from __future__ import annotations

import uuid

from adapters.base import OdooRPCError
from framework.fg_common import m2o_id, make_trace  # noqa: F401 — re-exported
from framework.qa_fixtures import (require_mail_offline,  # noqa: F401
                                   sweep_model, sweep_products)

WORKFLOW = "DATAONE-WF-002"
WORKFLOW_NAME = "Quotation → sales order confirmation"
FEATURE = "DATAONE-WF-002 Quotation → sales order confirmation"
MARK = "WF002"

trace = make_trace(FEATURE)

# dto_sale/models/sale_order.py:17 — required=True, no default.
ORDER_TYPES = ["project", "buy", "inventory", "cost_center"]

# The exact messages the workflow's gates raise.
SHIP_DATE_ERROR = "Please enter 'Promised Ship Date' for all order lines."
REQUESTER_ERROR = "Please enter Requester email"
TARIFF_ERROR = "Tariff Amount must be greater than or equal to 0."
PROJECT_ERROR = "Project is required"
CONTRACT_ERROR = "Customer Contract is required"
NO_ANALYTIC_ERROR = "Analytic Distribution should not be set for this order type"

# dto_account/models/account_analytic_plan.py:6 — the plan xmlids by key.
ANALYTIC_PLANS = {
    "project": "dto_account.project_analytic_plan",
    "contract": "dto_account.customer_contract_analytic_plan",
    "cost": "dto_account.cost_center_analytic_plan",
}

_TOKEN = "init"


def fixture_token() -> str:
    return _TOKEN


def fx(name: str) -> str:
    return f"{name} [{_TOKEN}]"


def sweep_wf002(rpc):
    """Open a fresh fixture namespace, then remove marker-scoped leftovers."""
    global _TOKEN
    _TOKEN = uuid.uuid4().hex[:6]

    ids = rpc.search("sale.order", [("origin", "like", f"{MARK} %"),
                                    ("active", "in", [True, False])])
    if ids:
        for state_reset in ({"state": "draft"},):
            try:
                rpc.write("sale.order", ids, state_reset)
            except OdooRPCError:
                pass
        try:
            rpc.call("sale.order", "unlink", ids)
        except OdooRPCError:
            try:
                rpc.write("sale.order", ids, {"active": False})
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
def require_dto_sale(ctx):
    """BLOCK when dto_sale has not contributed the workflow's fields."""
    rpc = ctx.adapter.rpc
    missing = [f for f in ("order_type", "tariff_amount")
               if not rpc.field_exists("sale.order", f)]
    missing += [f for f in ("requested_delivery_date",)
                if not rpc.field_exists("sale.order.line", f)]
    if missing:
        ctx.blocked(
            f"dto_sale is not installed on {ctx.env.key} (db={ctx.env.db}) — "
            f"missing {', '.join(missing)}. WF-002 is entirely about those "
            "fields and their confirmation gates.")


def require_analytic_plans(ctx, keys=("project", "contract")):
    """BLOCK when dto_account's analytic plans are missing.

    ``_validate_analytic_distribution_*`` resolves them through
    ``env.ref(...)``, so an absent plan raises a bare reference error rather
    than the ValidationError the workbook expects.
    """
    rpc = ctx.adapter.rpc
    resolved = {}
    for key in keys:
        plan_id = rpc.ref(ANALYTIC_PLANS[key])
        if not plan_id:
            ctx.blocked(
                f"The analytic plan {ANALYTIC_PLANS[key]} does not resolve "
                f"on {ctx.env.key}. dto_account's analytic gates dispatch "
                "through env.ref() on it, so the gate cannot be exercised "
                "until dto_account's data is loaded.")
        resolved[key] = plan_id
    return resolved


# -------------------------------------------------------------- fixtures
def ensure_partner(rpc, label="Customer", extra=None) -> int:
    name = fx(f"{MARK} {label}")
    found = rpc.search("res.partner", [("name", "=", name)], limit=1)
    if found:
        return found[0]
    values = {"name": name}
    values.update(extra or {})
    return rpc.create("res.partner", values)


def ensure_product(ctx, label="Item", price=100.0, storable=True) -> int:
    rpc = ctx.adapter.rpc
    name = fx(f"{MARK} {label}")
    found = rpc.search_read("product.product", [("name", "=", name)],
                            ["id"], limit=1)
    if found:
        return found[0]["id"]
    values = {"name": name, "list_price": price, "sale_ok": True,
              "taxes_id": [(6, 0, [])]}
    if storable:
        values.update(ctx.adapter.storable_product_values())
    else:
        values["type"] = "service"
    tmpl_id = rpc.create("product.template", values)
    variant = rpc.search_read("product.product",
                              [("product_tmpl_id", "=", tmpl_id)],
                              ["id"], limit=1)
    return variant[0]["id"]


def ensure_analytic_account(rpc, plan_id, label="Analytic") -> int:
    name = fx(f"{MARK} {label}")
    found = rpc.search("account.analytic.account",
                       [("name", "=", name), ("plan_id", "=", plan_id)],
                       limit=1)
    if found:
        return found[0]
    return rpc.create("account.analytic.account",
                      {"name": name, "plan_id": plan_id})


def gate_analytic(ctx, order_type):
    """The analytic distribution dto_account's confirmation gate demands.

    ``_validate_analytic_distribution_project`` (dto_account/models/
    sale_order.py:83) refuses a ``project`` order whose product lines carry
    no account on the Project plan, and ``_validate_analytic_distribution_buy``
    (:93) does the same against the Customer Contract plan;
    ``inventory`` and ``cost_center`` refuse ANY distribution.

    Every WF-002 case that CONFIRMS an order but whose subject is something
    else (the confirmation email, the revision button, the search filters)
    must therefore hand its product lines a valid distribution, or it fails
    on a gate that has nothing to do with what it asserts. The analytic gate
    itself is TC078-TC082's subject and those build their distributions
    explicitly — they do not call this.

    Returns ``None`` when the order type needs no distribution, or when
    dto_account's plans do not resolve on this target, so a database without
    dto_account behaves exactly as it did before.
    """
    plan_key = {"project": "project", "buy": "contract"}.get(order_type)
    if plan_key is None:
        return None
    rpc = ctx.adapter.rpc
    plan_id = rpc.ref(ANALYTIC_PLANS[plan_key])
    if not plan_id:
        return None
    account_id = ensure_analytic_account(rpc, plan_id,
                                         f"{order_type.title()} Gate")
    return {str(account_id): 100}


def line_values(product_id, qty=1.0, price=100.0, ship_date="2026-09-10",
                analytic=None, display_type=None, name=None):
    """One order-line command payload.

    ``display_type`` produces a section or note line: those carry no
    ``product_id`` and no ship date, and dto_sale's gate skips them
    (``filtered(lambda r: not r.display_type)``).
    """
    if display_type:
        return (0, 0, {"display_type": display_type,
                       "name": name or f"{MARK} {display_type}"})
    values = {"product_id": product_id, "product_uom_qty": qty,
              "price_unit": price}
    if ship_date is not None:
        values["requested_delivery_date"] = ship_date
    if analytic:
        values["analytic_distribution"] = analytic
    if name:
        values["name"] = name
    return (0, 0, values)


def make_quotation(ctx, order_type="project", lines=None, tariff=0.0,
                   memo="default", requester="qa.wf002@example.invalid",
                   label="Quote", partner_id=None, extra=None) -> int:
    """A WF-002 quotation.

    ``memo`` defaults to a non-empty marker string because the confirmation
    automation crashes on an empty one (see the module docstring). Pass
    ``memo=""`` to exercise that defect deliberately, and ``memo=None`` to
    omit the field entirely.
    """
    rpc = ctx.adapter.rpc
    partner_id = partner_id or ensure_partner(rpc)
    if lines is None:
        lines = [line_values(ensure_product(ctx))]

    values = {
        "partner_id": partner_id,
        "origin": fx(f"{MARK} {label}"),
        "order_type": order_type,
        "tariff_amount": tariff,
        "order_line": list(lines),
    }
    if requester is not None and rpc.field_exists("sale.order",
                                                  "requester_email"):
        values["requester_email"] = requester
    if memo is not None and rpc.field_exists("sale.order",
                                             "memo_to_suppliers"):
        values["memo_to_suppliers"] = (f"{MARK} QA memo"
                                       if memo == "default" else memo)
    values.update(extra or {})
    return rpc.create("sale.order", values)


def confirm(rpc, order_id):
    return rpc.call("sale.order", "action_confirm", [order_id])


def read_order(rpc, order_id, fields_):
    return rpc.read("sale.order", [order_id], fields_)[0]


def order_lines(rpc, order_id, fields_):
    return rpc.search_read("sale.order.line",
                           [("order_id", "=", order_id)],
                           fields_, order="sequence, id")


def expect_error(rpc_callable, *args, **kwargs):
    """Run an RPC call the workbook expects to raise; return
    (raised: bool, message: str)."""
    try:
        rpc_callable(*args, **kwargs)
        return False, "no error raised"
    except OdooRPCError as exc:
        return True, str(exc)
