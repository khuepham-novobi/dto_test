"""Shared fixtures and helpers for the DATAONE-WF-016 suite
(Vendor Bill Entry & Posting).

Owning workflow: DATAONE-WF-016, build order 18, Stage 5 (the rebuild),
effective risk CRITICAL, 13.5 h, depends on WF-015. It owns 16 workbook
test cases (4 P0, 6 P1, 5 P2, 1 P3) and shares TC050 with WF-019.

Four independent controls, one workflow
---------------------------------------
1. **The attachment gate** (F155). ``dto_account.account.move._post``
   refuses to post any ``in_invoice`` without an attachment, with no group
   condition of any kind. Verified at
   ``dto_account/models/account_move.py:50-58``::

       def _post(self, soft=True):
           if any(not move.have_attachment for move in self.filtered(
                   lambda m: m.move_type == 'in_invoice')):
               raise UserError(_('User cannot confirm the bill. The Vendor '
                                 'Bill requires an attachment before posting.'))
           res = super(AccountMove, self)._post(soft)

   Three consequences the suite asserts separately: nobody can bypass it
   (TC262), one bad record kills a whole batch because the check is
   ``any(...)`` over ``self`` (TC263), and it must not widen past
   ``in_invoice`` — widening it would block every delivery in the business,
   because WF-012 posts customer invoices inside the delivery transaction
   (TC266).

2. **Analytic derivation** (F152). ``account.move.line.create`` blends the
   purchase line's distribution with the distribution model's, and the
   MODEL wins on a colliding plan — the opposite of what most users expect
   and surfaced nowhere in the interface (TC284, TC285).

3. **Payment segregation of duties** (F158). Register Payment belongs to
   ``account.group_account_manager``, expressed both in the views and — the
   control that actually matters — in ``ir.model.access``. TC268 proves the
   ACL by direct RPC; TC269 proves the ACL row itself, because the failure
   it guards against produces no error and no symptom (see below).

4. **Vendor RMA terms** (F156). A vendor credit note's narration is
   recomputed from ``res.company.vendor_refund_narration``, in the
   vendor's language, refreshed on copy, and printed below the totals.

The silent failure this suite exists to catch
---------------------------------------------
``dto_account/security/ir.model.access.csv`` reuses the **core** xml id
``account.access_account_payment_register``. Reusing a core id OVERWRITES
the core row. If v19 renamed or dropped that id, DataOne's CSV instead
creates a NEW row while the permissive core row survives untouched — and
every invoicing user can register payments again. Nothing raises, nothing
logs, the views still look right. Only a direct read of ``ir.model.data``
plus ``ir.model.access`` detects it, which is TC269.

Version-dependent view surface
------------------------------
TC267 is written as "all three views". That is a v17 statement. On v19 the
Register Payment button was removed from both list views
(``account.view_invoice_tree``, ``account.view_move_line_payment_tree``)
and occurs twice inside the FORM view instead
(``account/views/account_move_views.xml`` :734 and :746), so DataOne
deleted its two list inherits and gates both form buttons by id. The
restriction is unchanged or tighter, never looser. ``REGISTER_PAYMENT_VIEWS``
below encodes that per version — this is the documented exception in
AUTOMATION_CONVENTIONS.md, "a test whose subject is the version delta
itself".

Safety
------
Nothing here confirms a sale order, so ``require_mail_offline`` is not
needed for the bill cases. It IS needed for TC050, which reads live data
only, and for any case that posts against real vendors — every fixture is
namespaced and every posted move is left in place, because a posted
journal entry cannot be unlinked.
"""
from __future__ import annotations

import base64
import copy
import uuid

from adapters.base import OdooRPC, OdooRPCError
from framework.fg_common import form_arch, list_tag, m2o_id, make_trace  # noqa: F401
from framework.qa_fixtures import (require_mail_offline,  # noqa: F401
                                   sweep_model, sweep_products, with_categ)

WORKFLOW = "DATAONE-WF-016"
WORKFLOW_NAME = "Vendor Bill Entry & Posting"
FEATURE = "DATAONE-WF-016 Vendor Bill Entry & Posting"
MARK = "WF016"

trace = make_trace(FEATURE)

# dto_account/models/account_move.py:55-56 — asserted verbatim, not as a
# substring of a translated form.
ATTACHMENT_GATE_MESSAGE = ("User cannot confirm the bill. The Vendor Bill "
                           "requires an attachment before posting.")

# The gate's filter. Widening this is the catastrophic port error (TC266).
GATED_MOVE_TYPE = "in_invoice"
UNGATED_MOVE_TYPES = ("out_invoice", "out_refund", "in_refund", "entry")

# dto_account/security/ir.model.access.csv — the row that reuses a CORE
# xml id. TC269 is entirely about whether that reuse still lands.
PAYMENT_REGISTER_ACL_XMLID = "account.access_account_payment_register"
PAYMENT_REGISTER_MODEL = "account.payment.register"
PAYMENT_REGISTER_GROUP = "account.group_account_manager"
PAYMENT_REGISTER_PERMS = {"perm_read": True, "perm_write": True,
                          "perm_create": True, "perm_unlink": False}

# Where the Register Payment restriction is expressed, per version.
# v17: one form button plus two list inherits. v19: two form buttons, both
# gated by id; the list buttons no longer exist to gate.
REGISTER_PAYMENT_VIEWS = {
    "17": [("account.view_move_form", "form"),
           ("account.view_invoice_tree", "tree"),
           ("account.view_move_line_payment_tree", "tree")],
    "19": [("account.view_move_form", "form")],
}

# dto_account/views/account_move_views.xml — the two form buttons v19 has.
REGISTER_PAYMENT_BUTTON_IDS = ("account_invoice_payment_btn",
                               "account_invoice_payment_secondary_btn")

# dto_account/views/*.xml — the anchors delta §3.5 lists as rotted.
BILL_FORM_VIEW = "dto_account.view_account_move_form_dto_account"
BILL_LIST_VIEW = "dto_account.view_in_invoice_bill_tree_dto_account"
BILL_SEARCH_VIEW = "dto_account.view_in_invoice_bill_search_dto_account"
HAVE_ATTACHMENT_FILTER = "filter_have_attachment"

# res.company.vendor_refund_narration's shipped default — the four elements
# TC275 step 5 requires the printed terms to name.
RMA_MARKERS = ("DATAONE Systems", "9004 AMBASSADOR ROW, DALLAS TX 75247",
               "15 days", "Quality Control Department")

QA_PASSWORD = "QaAuto-2026!"

_TOKEN = "init"


def fixture_token() -> str:
    return _TOKEN


def fx(name: str) -> str:
    return f"{name} [{_TOKEN}]"


def sweep_wf016(rpc):
    """Open a fresh fixture namespace, then remove marker-scoped leftovers.

    Posted moves cannot be unlinked and validated receipts cannot be
    undone, so this is best-effort by design. Every assertion in the suite
    is scoped by the fresh token, so a survivor cannot contaminate a later
    run — convention rule 5.
    """
    global _TOKEN
    _TOKEN = uuid.uuid4().hex[:6]

    move_ids = set(rpc.search("account.move",
                              [("ref", "like", f"{MARK} %")])) | set(
        rpc.search("account.move", [("invoice_origin", "like", f"{MARK} %")]))
    for move_id in move_ids:
        for method in ("button_draft", "button_cancel"):
            try:
                rpc.call("account.move", method, [move_id])
            except OdooRPCError:
                pass
        try:
            rpc.call("account.move", "unlink", [move_id])
        except OdooRPCError:
            pass

    orders = rpc.search("purchase.order",
                        [("origin", "like", f"{MARK} %")])
    if orders:
        for method in ("button_cancel", "button_draft"):
            try:
                rpc.call("purchase.order", method, orders)
            except OdooRPCError:
                pass
        try:
            rpc.call("purchase.order", "unlink", orders)
        except OdooRPCError:
            pass

    sweep_model(rpc, "account.analytic.distribution.model",
                [("company_id", "!=", False),
                 ("product_categ_id.name", "like", f"{MARK} %")])
    sweep_products(rpc, MARK)
    sweep_model(rpc, "product.category", [("name", "like", f"{MARK} %")])
    sweep_model(rpc, "account.analytic.account",
                [("name", "like", f"{MARK} %"),
                 ("active", "in", [True, False])])
    sweep_model(rpc, "res.partner", [("name", "like", f"{MARK} %"),
                                     ("user_ids", "=", False),
                                     ("active", "in", [True, False])])


# ---------------------------------------------------------------- probes
def require_dto_account(ctx):
    """BLOCK unless dto_account is installed.

    ``have_attachment`` is the field the gate reads. Without it the gate
    does not exist and every negative case would pass vacuously — which is
    worse than failing.
    """
    rpc = ctx.adapter.rpc
    if not rpc.field_exists("account.move", "have_attachment"):
        ctx.blocked(
            "account.move.have_attachment does not exist on "
            f"{ctx.env.key} (db={ctx.env.db}) — dto_account is not "
            "installed, so the vendor-bill attachment gate this workflow "
            "is about does not exist to be tested.")


def require_purchase(ctx):
    rpc = ctx.adapter.rpc
    if not rpc.model_exists("purchase.order"):
        ctx.blocked("purchase is not installed — WF-016's bills are "
                    "derived from purchase orders and receipts.")


def company_id(rpc) -> int:
    return m2o_id(rpc.read("res.users", [rpc.uid],
                           ["company_id"])[0]["company_id"])


# -------------------------------------------------------------- fixtures
def ensure_vendor(rpc, label="Vendor Gamma", lang=None) -> int:
    name = fx(f"{MARK} {label}")
    found = rpc.search("res.partner", [("name", "=", name)], limit=1)
    if found:
        return found[0]
    values = {"name": name, "supplier_rank": 1}
    if lang:
        values["lang"] = lang
    return rpc.create("res.partner", values)


def ensure_category(rpc, label="Cat") -> int:
    name = fx(f"{MARK} {label}")
    found = rpc.search("product.category", [("name", "=", name)], limit=1)
    if found:
        return found[0]
    return rpc.create("product.category", {"name": name})


def ensure_product(ctx, label="CMP-CONN-A", price=25.0, categ_id=None) -> int:
    rpc = ctx.adapter.rpc
    name = fx(f"{MARK} {label}")
    found = rpc.search_read("product.product", [("name", "=", name)],
                            ["id"], limit=1)
    if found:
        return found[0]["id"]
    values = {"name": name, "standard_price": price, "list_price": price,
              "purchase_ok": True, "sale_ok": True,
              "supplier_taxes_id": [(6, 0, [])], "taxes_id": [(6, 0, [])]}
    values.update(ctx.adapter.storable_product_values())
    if categ_id:
        values["categ_id"] = categ_id
    tmpl_id = rpc.create("product.template", with_categ(rpc, values))
    variant = rpc.search_read("product.product",
                              [("product_tmpl_id", "=", tmpl_id)],
                              ["id"], limit=1)
    return variant[0]["id"]


def ensure_analytic_account(rpc, plan_xmlid, label) -> int:
    """An analytic account on a named plan, or BLOCKED-worthy None.

    The plan xmlids are DataOne's own (``dto_account``). A caller that
    cannot resolve one should say so precisely rather than silently
    creating the account on whatever plan happens to be first.
    """
    plan_id = rpc.ref(plan_xmlid)
    if not plan_id:
        return None
    name = fx(f"{MARK} {label}")
    found = rpc.search("account.analytic.account",
                       [("name", "=", name), ("plan_id", "=", plan_id)],
                       limit=1)
    if found:
        return found[0]
    return rpc.create("account.analytic.account",
                      {"name": name, "plan_id": plan_id})


def any_analytic_plan(rpc, skip_ids=()):
    """Any usable analytic plan id, for targets without DataOne's own."""
    rows = rpc.search_read("account.analytic.plan",
                           [("id", "not in", list(skip_ids))],
                           ["name"], limit=2)
    return rows


def make_purchase_order(ctx, vendor_id, product_id, qty=4.0, price=25.0,
                        analytic=None, label="PO"):
    """A confirmed purchase order with one line."""
    rpc = ctx.adapter.rpc
    line = {"product_id": product_id, "product_qty": qty,
            "price_unit": price, "name": fx(f"{MARK} {label} line")}
    if analytic:
        line["analytic_distribution"] = analytic
    order_id = rpc.create("purchase.order", {
        "partner_id": vendor_id,
        "origin": fx(f"{MARK} {label}"),
        "order_line": [(0, 0, line)],
    })
    rpc.call("purchase.order", "button_confirm", [order_id])
    state = rpc.read("purchase.order", [order_id], ["state"])[0]["state"]
    if state not in ("purchase", "done"):
        ctx.blocked(f"The fixture purchase order did not confirm "
                    f"(state={state!r}); no receipt and no bill can follow.")
    return order_id


def receive_order(ctx, order_id):
    """Validate every incoming picking of a confirmed purchase order."""
    rpc = ctx.adapter.rpc
    picking_ids = rpc.read("purchase.order", [order_id],
                           ["picking_ids"])[0]["picking_ids"]
    for picking_id in picking_ids:
        row = rpc.read("stock.picking", [picking_id], ["state"])[0]
        if row["state"] in ("done", "cancel"):
            continue
        try:
            rpc.call("stock.picking", "action_assign", [picking_id])
        except OdooRPCError:
            pass
        moves = rpc.search_read("stock.move",
                                [("picking_id", "=", picking_id)],
                                ["product_uom_qty"])
        for move in moves:
            rpc.write("stock.move", [move["id"]],
                      {"quantity": move["product_uom_qty"], "picked": True})
        try:
            rpc.call("stock.picking", "button_validate", [picking_id])
        except OdooRPCError as exc:
            ctx.log(f"[warn] receipt {picking_id} not validated: {exc}")
    return rpc.read("stock.picking", picking_ids, ["state"]) \
        if picking_ids else []


def bill_from_order(ctx, order_id, invoice_date="2026-01-15"):
    """Press Create Bill on a purchase order; return the draft bill id.

    ``purchase.order.action_create_invoice`` is public, so it dispatches
    over RPC. It returns an action dict, so the bill is located by
    ``invoice_ids`` afterwards rather than by parsing the action.
    """
    rpc = ctx.adapter.rpc
    before = set(rpc.read("purchase.order", [order_id],
                          ["invoice_ids"])[0]["invoice_ids"])
    rpc.call("purchase.order", "action_create_invoice", [order_id])
    after = set(rpc.read("purchase.order", [order_id],
                         ["invoice_ids"])[0]["invoice_ids"])
    created = sorted(after - before)
    if not created:
        ctx.blocked(
            "action_create_invoice produced no bill for purchase order "
            f"{order_id}. Check the order's qty_to_invoice and the "
            "product's purchase control policy on this database.")
    bill_id = created[0]
    values = {"invoice_date": invoice_date, "ref": fx(f"{MARK} bill")}
    rpc.write("account.move", [bill_id], values)
    return bill_id


def two_posting_accounts(ctx):
    """(debit, credit) account ids for a BALANCED miscellaneous entry.

    ``account.account.deprecated`` was REMOVED in v19 (v17
    account/models/account_account.py:48; v19 :42 keeps only ``active``,
    which search already honours through active_test), so the filter is
    applied only where the field exists.
    """
    rpc = ctx.adapter.rpc
    domain = ([("deprecated", "=", False)]
              if rpc.field_exists("account.account", "deprecated") else [])
    rows = rpc.search_read("account.account", domain, ["code"], limit=2,
                           order="code")
    if len(rows) < 2:
        ctx.blocked(
            "Fewer than two usable account.account records exist on "
            f"{ctx.env.key}; a balanced two-line 'entry' cannot be built, "
            "so the ungated-move-types case cannot run.")
    return rows[0]["id"], rows[1]["id"]


def make_bare_bill(ctx, vendor_id, product_id, price=25.0, qty=1.0,
                   move_type="in_invoice", label="bill"):
    """A draft move of the given type with one line and no attachment."""
    rpc = ctx.adapter.rpc
    values = {
        "move_type": move_type,
        "partner_id": vendor_id,
        "invoice_date": "2026-01-15",
        "ref": fx(f"{MARK} {label}"),
        "invoice_origin": fx(f"{MARK} {label}"),
        "invoice_line_ids": [(0, 0, {
            "product_id": product_id,
            "quantity": qty,
            "price_unit": price,
            "name": fx(f"{MARK} {label} line"),
            "tax_ids": [(6, 0, [])],
        })],
    }
    if move_type == "entry":
        # A miscellaneous entry has no INVOICE lines, but it still needs
        # balanced journal items: v19 refuses to post a move with no
        # non-section line — "Even magicians can't post nothing!"
        # (v19 account/models/account_move.py:5660). Popping the lines and
        # adding nothing produced an empty move that could never reach
        # 'posted', so the ungated-move-type assertion was measuring the
        # fixture rather than the gate.
        values.pop("invoice_line_ids")
        values.pop("invoice_date", None)
        debit_account, credit_account = two_posting_accounts(ctx)
        values["line_ids"] = [
            (0, 0, {"name": fx(f"{MARK} {label} debit"),
                    "account_id": debit_account, "debit": price,
                    "credit": 0.0}),
            (0, 0, {"name": fx(f"{MARK} {label} credit"),
                    "account_id": credit_account, "debit": 0.0,
                    "credit": price}),
        ]
    return rpc.create("account.move", values)


def attach_to_move(rpc, move_id, via="attachment", name=None):
    """Give a move an attachment, by either of the two paths TC264 tests.

    ``via='attachment'`` creates the ``ir.attachment`` pointing AT the move
    — the chatter path, and the one whose stored-compute invalidation is
    unreliable. ``via='move'`` writes ``attachment_ids`` on the move, the
    path expected to invalidate reliably. The difference between the two is
    the whole of TC264 step 9.
    """
    name = name or fx(f"{MARK} supplier.pdf")
    payload = base64.b64encode(b"%PDF-1.4 QA fixture").decode()
    if via == "move":
        return rpc.write("account.move", [move_id], {
            "attachment_ids": [(0, 0, {"name": name, "datas": payload})]})
    return rpc.create("ir.attachment", {
        "name": name, "datas": payload,
        "res_model": "account.move", "res_id": move_id})


def make_user(ctx, login_suffix, group_xmlids, name=None):
    """A disposable internal user in the given groups.

    ``res.users.groups_id`` (v17, base/models/res_users.py:384) became
    ``group_ids`` on v19 (:257); the name comes from the adapter so no
    version branch lives in a test body.
    """
    rpc = ctx.adapter.rpc
    groups_field = ctx.adapter.user_groups_field
    login = f"qa.wf016.{login_suffix}"
    group_ids = [rpc.ref(x) for x in ["base.group_user"] + list(group_xmlids)]
    missing = [x for x, gid in
               zip(["base.group_user"] + list(group_xmlids), group_ids)
               if not gid]
    if missing:
        ctx.blocked(f"These group xmlids do not resolve on {ctx.env.key}: "
                    f"{missing}. The segregation-of-duties cases cannot be "
                    "expressed without them.")
    found = rpc.search("res.users", [("login", "=", login),
                                     ("active", "in", [True, False])],
                       limit=1)
    if found:
        rpc.write("res.users", found,
                  {"active": True, "password": QA_PASSWORD,
                   groups_field: [(6, 0, group_ids)]})
        return found[0], login
    user_id = rpc.call("res.users", "create",
                       {"name": name or f"QA WF016 {login_suffix}",
                        "login": login, "password": QA_PASSWORD,
                        groups_field: [(6, 0, group_ids)]},
                       context={"no_reset_password": True})
    return user_id, login


def session_as(env, login) -> OdooRPC:
    user_env = copy.copy(env)
    user_env.username = login
    user_env.password = QA_PASSWORD
    return OdooRPC(user_env)


def move_lines(rpc, move_id, fields_=None):
    fields_ = fields_ or ["name", "account_id", "display_type", "debit",
                          "credit", "balance", "analytic_distribution",
                          "product_id", "purchase_line_id"]
    fields_ = [f for f in fields_
               if f == "name" or rpc.field_exists("account.move.line", f)]
    return rpc.search_read("account.move.line", [("move_id", "=", move_id)],
                           fields_, order="id")


def distribution_accounts(distribution) -> set:
    """The analytic account ids named by a distribution map.

    DataOne encodes multi-plan distributions as comma-joined ids
    (``{"22,23": 100}``). Delta §2.14 leaves that format an open Unknown on
    v19, so every comparison in this suite is by RESOLVED ACCOUNT SET, not
    by raw key string — a shape change must not be reported as a value
    change. ``__update__`` is core's merge directive, never an account.
    """
    result = set()
    for key in (distribution or {}):
        if key == "__update__":
            continue
        for part in str(key).split(","):
            part = part.strip()
            if part.isdigit():
                result.add(int(part))
    return result


def plan_of(rpc, account_ids):
    """{analytic account id: root plan id} — for collision assertions."""
    if not account_ids:
        return {}
    field = ("root_plan_id"
             if rpc.field_exists("account.analytic.account", "root_plan_id")
             else "plan_id")
    rows = rpc.read("account.analytic.account", sorted(account_ids), [field])
    return {row["id"]: m2o_id(row[field]) for row in rows}


def expect_error(rpc_callable, *args, **kwargs):
    try:
        rpc_callable(*args, **kwargs)
        return False, "no error raised"
    except OdooRPCError as exc:
        return True, str(exc)
