"""Shared fixtures and helpers for the DATAONE-WF-003 suite
(Quotation revision).

Owning workflow: DATAONE-WF-003, build order 3, effective risk CRITICAL.
Modules under test: base_revision, sale_order_revision (OCA, 3rd-addons),
dto_sale (order_type / tariff_amount / copy flags), dto_sale_workday
(the re-import path).

Live-DB determinism adaptations (documented, not assertion-weakening)
---------------------------------------------------------------------
* Every fixture carries the WF003 marker plus a per-execution token in
  ``origin`` and ``client_order_ref``. The sale order's ``name`` is left to
  the ir.sequence, exactly as the workbook's "quotation SO0042" is, because
  ``unrevisioned_name`` is derived from it and the revision naming rule
  (``"%s-%02d"``) is what the tests assert. Sweeps therefore scope on
  ``origin``, never on ``name``.
* The workbook chains TC095 -> TC096 -> TC098 through a shared lineage
  ("leave both in place for TC096"). Convention rule 5 forbids one test
  depending on another's fixtures, so each test rebuilds the lineage it
  needs from scratch with its own token. The assertions are unchanged; only
  the setup is repeated.
* ``sale.order.order_type`` is ``required=True`` with no default
  (dto_sale/models/sale_order.py:17), so every quotation fixture sets it.
* ``dto_sale.action_confirm`` raises unless every line carries
  ``requested_delivery_date`` (dto_sale/models/sale_order.py:59), and
  ``dto_sale_workday.action_confirm`` raises unless ``requester_email`` is
  set (dto_sale_workday/models/sale_order.py:25). Fixtures that need a
  confirmed order supply both.

Source facts these helpers lean on (verified in DTO-Odoo/3rd-addons)
--------------------------------------------------------------------
* base_revision/models/base_revision.py
  - ``_get_new_rev_data`` names a revision ``"%s-%02d" % (unrevisioned_name,
    n)`` -> zero-padded to two digits;
  - ``copy_revision_with_context`` re-points ``old_revision_ids`` at the new
    revision and writes ``_prepare_revision_data`` on the source;
  - ``create_revision`` posts ``"New revision created: %s"`` to BOTH
    chatters and returns an act_window action;
  - base ``_sql_constraints`` = ``unique(unrevisioned_name, revision_number)``
    with the message "Reference and revision must be unique.".
* sale_order_revision/models/sale_order.py
  - overwrites ``_sql_constraints`` with
    ``unique(unrevisioned_name, revision_number, company_id)`` and the
    message "Order Reference and revision must be unique per Company.";
  - ``_prepare_revision_data`` adds ``state='cancel'`` on top of the base
    ``active=False`` / ``current_revision_id``;
  - the form inherit (view/sale_order.xml, priority 15) puts the
    "New Revision of Quotation" button in the header with
    ``invisible="state not in ['cancel' ,'sent']"`` and anchors the
    ``fa-file-archive-o`` stat button on
    ``//button[@name='action_view_invoice']``.
"""
from __future__ import annotations

import copy
import re
import uuid

from adapters.base import OdooRPC, OdooRPCError
from framework.fg_common import m2o_id, make_trace  # noqa: F401 — re-exported
from framework.qa_fixtures import sweep_model, sweep_products, with_categ

WORKFLOW = "DATAONE-WF-003"
WORKFLOW_NAME = "Quotation revision"
FEATURE = "DATAONE-WF-003 Quotation revision"
MARK = "WF003"

trace = make_trace(FEATURE)

# The five OCA modules TC014 gates on, in the workbook's own order.
OCA_MODULES = [
    "base_revision",
    "sale_order_revision",
    "queue_job",
    "base_tier_validation",
    "stock_picking_auto_create_lot",
]

# Revision plumbing the suite cannot run without.
REVISION_FIELDS = ["revision_number", "unrevisioned_name",
                   "current_revision_id", "old_revision_ids",
                   "revision_count", "has_old_revisions"]

_TOKEN = "init"


def fixture_token() -> str:
    return _TOKEN


def fx(name: str) -> str:
    """Namespace a fixture value for this execution:
    'WF003 Quote' -> 'WF003 Quote [a1b2c3]'. The MARK prefix is preserved so
    prefix sweeps keep working across executions."""
    return f"{name} [{_TOKEN}]"


def sweep_wf003(rpc):
    """Open a fresh fixture namespace, then remove marker-scoped leftovers.

    Deletion is best-effort by design: a sale order that already produced
    stock moves cannot be unlinked, so ``sweep_model`` leaves it. Because the
    new namespace is unique, anything that survives can never collide with
    this execution's assertions.
    """
    global _TOKEN
    _TOKEN = uuid.uuid4().hex[:6]

    # revisions are archived, so the sweep must see inactive records too
    for domain in (
        [("origin", "like", f"{MARK} %"), ("active", "in", [True, False])],
    ):
        ids = rpc.search("sale.order", domain)
        if ids:
            try:
                rpc.write("sale.order", ids, {"state": "draft"})
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
                                     ("user_ids", "=", False)])
    sweep_model(rpc, "account.analytic.account",
                [("name", "like", f"{MARK} %")])


# ---------------------------------------------------------------- probes
def require_revision_stack(ctx):
    """BLOCK the test when base_revision / sale_order_revision are absent.

    The whole workflow is dead without them — and on v19 that is the
    expected state until the OCA 19.0 ports exist (workbook precondition
    E5). A precise BLOCKED reason is more useful than a cascade of
    attribute errors.
    """
    rpc = ctx.adapter.rpc
    missing = [f for f in REVISION_FIELDS
               if not rpc.field_exists("sale.order", f)]
    if missing:
        ctx.blocked(
            "sale_order_revision / base_revision are not installed on "
            f"{ctx.env.key} (db={ctx.env.db}) — sale.order is missing "
            f"{', '.join(missing)}. Workbook precondition E5: the OCA 19.0 "
            "branches must be fetched and installed before WF-003 can run.")


def installed_modules(rpc, names: list[str]) -> dict:
    """name -> ir.module.module state, for the given technical names."""
    rows = rpc.search_read("ir.module.module", [("name", "in", names)],
                           ["name", "state", "latest_version"])
    return {r["name"]: r for r in rows}


# -------------------------------------------------------------- fixtures
def ensure_partner(rpc, label="Customer") -> int:
    name = fx(f"{MARK} {label}")
    found = rpc.search("res.partner", [("name", "=", name)], limit=1)
    return found[0] if found else rpc.create("res.partner", {"name": name})


def ensure_product(ctx, label="Item", price=100.0) -> int:
    """A storable product created through the version-correct field set."""
    rpc = ctx.adapter.rpc
    name = fx(f"{MARK} {label}")
    found = rpc.search_read("product.product", [("name", "=", name)],
                            ["id"], limit=1)
    if found:
        return found[0]["id"]
    values = {"name": name, "list_price": price, "sale_ok": True,
              "taxes_id": [(6, 0, [])]}
    values.update(ctx.adapter.storable_product_values())
    tmpl_id = rpc.create("product.template", with_categ(rpc, values))
    variant = rpc.search_read("product.product",
                              [("product_tmpl_id", "=", tmpl_id)],
                              ["id"], limit=1)
    return variant[0]["id"]


def ensure_analytic_account(rpc, label="Analytic") -> int:
    """An analytic account on whichever plan the database already has.

    dto_account ships named plans (project / customer contract / cost
    centre); the suite only needs *an* account to prove the copy=True flag,
    so it reuses the first available plan rather than assuming an xmlid.
    """
    name = fx(f"{MARK} {label}")
    found = rpc.search("account.analytic.account", [("name", "=", name)],
                       limit=1)
    if found:
        return found[0]
    plan = rpc.search("account.analytic.plan", [], limit=1)
    vals = {"name": name}
    if plan:
        vals["plan_id"] = plan[0]
    return rpc.create("account.analytic.account", vals)


PROJECT_PLAN_XMLID = "dto_account.project_analytic_plan"
CONTRACT_PLAN_XMLID = "dto_account.customer_contract_analytic_plan"


def gate_analytic(ctx, order_type="project"):
    """The line-level analytic distribution dto_account's confirm gate wants.

    ``_validate_analytic_distribution_project`` (dto_account/models/
    sale_order.py:83) raises ``Project is required`` unless every product
    line's ``distribution_analytic_account_ids`` sits on the Project plan;
    the ``buy`` handler (:93) does the same against Customer Contract.
    TC097 is the only WF-003 case that confirms an order, and its subject is
    the revision button, not the analytic gate — so it hands its lines a
    valid distribution rather than dying on an unrelated ValidationError.

    Returns ``None`` when the plan does not resolve (dto_account absent), so
    a target without it behaves exactly as before.
    """
    plan_xmlid = {"project": PROJECT_PLAN_XMLID,
                  "buy": CONTRACT_PLAN_XMLID}.get(order_type)
    if not plan_xmlid:
        return None
    rpc = ctx.adapter.rpc
    plan_id = rpc.ref(plan_xmlid)
    if not plan_id:
        return None
    name = fx(f"{MARK} {order_type.title()} Gate")
    found = rpc.search("account.analytic.account",
                       [("name", "=", name), ("plan_id", "=", plan_id)],
                       limit=1)
    account_id = found[0] if found else rpc.create(
        "account.analytic.account", {"name": name, "plan_id": plan_id})
    return {str(account_id): 100}


def make_quotation(ctx, order_type="project", tariff_amount=250.0,
                   lines=None, with_analytic=True, label="Quote",
                   line_analytic=None):
    """A WF-003 quotation carrying every field the revision must copy.

    ``name`` is deliberately left to the ir.sequence (the workbook's SO0042
    comes from the sequence too) because ``unrevisioned_name`` is derived
    from it in base_revision.create(). The marker lives in ``origin``.

    Returns (order_id, snapshot) where snapshot holds the four values
    TC095 step 2 records.
    """
    rpc = ctx.adapter.rpc
    partner_id = ensure_partner(rpc)
    product_id = ensure_product(ctx)
    analytic_id = ensure_analytic_account(rpc) if with_analytic else False

    if lines is None:
        lines = [(product_id, 2.0, 100.0)]
    order_line = []
    for pid, qty, price in lines:
        line_vals = {
            "product_id": pid,
            "product_uom_qty": qty,
            "price_unit": price,
            # dto_sale.action_confirm() requires this on every line
            "requested_delivery_date": "2026-12-31",
        }
        if line_analytic:
            # dto_account.action_confirm() requires this on every product
            # line of a project / buy order — see gate_analytic().
            line_vals["analytic_distribution"] = line_analytic
        order_line.append((0, 0, line_vals))

    values = {
        "partner_id": partner_id,
        "origin": fx(f"{MARK} {label}"),
        "client_order_ref": fx(f"{MARK} CORef"),
        "order_type": order_type,
        "tariff_amount": tariff_amount,
        "order_line": order_line,
    }
    if analytic_id:
        values["analytic_account_id"] = analytic_id
    if rpc.field_exists("sale.order", "requester_email"):
        # dto_sale_workday.action_confirm() requires it; harmless otherwise
        values["requester_email"] = "qa.wf003@example.invalid"
    if rpc.field_exists("sale.order", "memo_to_suppliers"):
        # dto_sale's confirmation automation runs
        #   if 'IRM' in order.memo_to_suppliers
        # (dto_sale/data/base_automation_data.xml). memo_to_suppliers is a
        # Text field defaulting to False, and `'IRM' in False` raises
        # TypeError — which aborts the confirmation. Any fixture that will
        # be confirmed must therefore carry a non-empty memo, or it fails
        # for a reason that has nothing to do with the case under test.
        # (The defect itself is DATAONE-TC085, owned by WF-002.)
        values["memo_to_suppliers"] = f"{MARK} QA memo"

    order_id = rpc.create("sale.order", values)
    snapshot = rpc.read("sale.order", [order_id],
                        ["name", "order_type", "client_order_ref",
                         "analytic_account_id", "tariff_amount"])[0]
    snapshot["analytic_account_id"] = m2o_id(snapshot["analytic_account_id"])
    return order_id, snapshot


def set_sent(rpc, order_id):
    """Put a quotation in state 'sent'.

    The workbook allows either path ("send the quotation by email, or set
    the state directly"). Writing the state directly is the one that cannot
    reach a mail server — convention rule 4.
    """
    rpc.write("sale.order", [order_id], {"state": "sent"})


def revision_of(rpc, order_id) -> int | None:
    """The revision created from ``order_id``, via its current_revision_id."""
    row = rpc.read("sale.order", [order_id], ["current_revision_id"])[0]
    return m2o_id(row["current_revision_id"])


def read_order(rpc, order_id, fields_):
    """read() that also sees archived records (a revised source is
    active=False, and read() on an archived id still works, but search does
    not — helpers here always use read/browse by id for that reason)."""
    return rpc.read("sale.order", [order_id], fields_)[0]


_TAG_RE = re.compile(r"<[^>]+>")


def plain_text(html: str) -> str:
    """A chatter body with its markup removed and whitespace collapsed.

    base_revision's v19 port posts the notice through ``_get_html_link()``
    (3rd-addons/base_revision/models/base_revision.py:151,155), so the body
    reads ``New revision created: <a ... >S06508-01</a>`` where the 17.0
    module posted ``"New revision created: %s" % copied_rec.name`` as plain
    text. The workbook's step 8 ("both chatters contain New revision
    created: SO0042-01") is about the notice, not about the markup around
    the name, so the substring test runs against the rendered text.
    """
    return " ".join(_TAG_RE.sub(" ", html or "").split())


def chatter_bodies(rpc, order_id) -> list[str]:
    msgs = rpc.search_read(
        "mail.message",
        [("model", "=", "sale.order"), ("res_id", "=", order_id)],
        ["body"], order="id")
    return [m["body"] or "" for m in msgs]


def expect_error(rpc_callable, *args, **kwargs):
    """Run an RPC call the workbook expects to raise; return
    (raised: bool, message: str)."""
    try:
        rpc_callable(*args, **kwargs)
        return False, "no error raised"
    except OdooRPCError as exc:
        return True, str(exc)


def rpc_session(env, login, password) -> OdooRPC:
    """A second RPC session authenticated as the given user."""
    user_env = copy.copy(env)
    user_env.username = login
    user_env.password = password
    return OdooRPC(user_env)
