"""Shared fixtures/helpers for the FG suites.

Everything the suites create is namespaced:
  * record names start with the feature marker, e.g. "FG01 ..."
  * QA barcodes live in the 9001xxxxxx range
  * the dedicated plain internal user is QA_USER_LOGIN

sweep() removes leftovers from previous runs *that match the markers only*,
making every test idempotent and repeatable. Pre-existing business records
are never touched.
"""
from __future__ import annotations

from adapters.base import OdooRPC, OdooRPCError

QA_USER_LOGIN = "qa.auto.internal"
QA_USER_NAME = "QA AUTO Internal User"
# test-only credential for the disposable QA clone databases
QA_USER_PASSWORD = "QaAuto-2026!"


def user_groups_field(rpc: OdooRPC) -> str:
    """Name of the groups m2m on res.users for the environment behind `rpc`.

    Odoo 19 renamed `res.users.groups_id` to `group_ids`. The suites run
    against BOTH v17 and v19, so neither name can be hardcoded: writing
    `groups_id` on v19 fails with

        Invalid field 'groups_id' in 'res.users'

    which is what turned TC270, TC271 and TC272 into ERRORs on RUN-7197CCBB
    rather than letting them assert anything about the ACLs they exist to test.
    """
    return "group_ids" if rpc.field_exists("res.users", "group_ids") else "groups_id"


def sweep_products(rpc: OdooRPC, name_prefix: str):
    """Delete (or archive when referenced) templates/variants created by a
    previous run of a suite, identified by the name prefix."""
    for model in ("product.product", "product.template"):
        ids = rpc.search(model, [("name", "like", f"{name_prefix}%"),
                                 ("active", "in", [True, False])])
        if not ids:
            continue
        try:
            rpc.call(model, "unlink", ids)
        except OdooRPCError:
            # referenced somewhere (stock moves, orders): archive instead
            try:
                rpc.write(model, ids, {"active": False})
            except OdooRPCError:
                pass


def sweep_model(rpc: OdooRPC, model: str, domain: list):
    ids = rpc.search(model, domain)
    if ids:
        try:
            rpc.call(model, "unlink", ids)
        except OdooRPCError:
            pass


def ensure_qa_user(rpc: OdooRPC) -> int:
    """Create (or reuse) a plain internal user (base.group_user only)."""
    found = rpc.search("res.users", [("login", "=", QA_USER_LOGIN),
                                     ("active", "in", [True, False])], limit=1)
    if found:
        rpc.write("res.users", found, {"active": True,
                                       "password": QA_USER_PASSWORD})
        return found[0]
    group_user = rpc.ref("base.group_user")
    return rpc.create("res.users", {
        "name": QA_USER_NAME,
        "login": QA_USER_LOGIN,
        "password": QA_USER_PASSWORD,
        user_groups_field(rpc): [(6, 0, [group_user])],
    })


def rpc_as_qa_user(env) -> OdooRPC:
    """A second RPC session authenticated as the plain internal user."""
    import copy
    qa_env = copy.copy(env)
    qa_env.username = QA_USER_LOGIN
    qa_env.password = QA_USER_PASSWORD
    return OdooRPC(qa_env)


def require_mail_offline(ctx):
    """BLOCK the test when the target could actually deliver email.

    Several DataOne flows fire outbound mail as a side effect of a normal
    business action — dto_sale's confirmation automation calls
    ``template.send_mail(order.id, force_send=True, ...)`` with a hard-coded
    recipient list (mfgestimating@, procurement@, orders@ … and
    D1CienaIRM@ when the memo mentions IRM). Confirming a fixture order on a
    database with a reachable mail server would therefore send real email to
    real people.

    A neutralized QA clone has every ``ir.mail_server`` deactivated (see
    docs/AUTOMATION_CONVENTIONS.md, "Environment facts"), in which case
    ``mail.mail.send()`` fails to connect, marks the message ``exception``
    and the business action proceeds — nothing leaves the box. This probe
    makes that a checked precondition instead of an assumption: if any mail
    server is active, the test reports BLOCKED rather than risking delivery.

    Convention rule 4.
    """
    rpc = ctx.adapter.rpc
    if not rpc.model_exists("ir.mail_server"):
        return
    live = rpc.search_read("ir.mail_server", [("active", "=", True)],
                           ["name", "smtp_host"])
    if live:
        ctx.blocked(
            f"{len(live)} ir.mail_server record(s) are ACTIVE on "
            f"{ctx.env.key} (db={ctx.env.db}): "
            f"{[(s['name'], s['smtp_host']) for s in live]}. This test "
            "confirms a sale order, which fires dto_sale's confirmation "
            "automation and calls send_mail(force_send=True) against a "
            "hard-coded d1systems.com recipient list. Deactivate every mail "
            "server on the QA clone before running it — the platform will "
            "not risk delivering real email.")


#: Cached per (base_url, db) — the lookup costs two RPC round trips and every
#: fixture in every suite needs the same answer.
_CATEG_CACHE: dict = {}


def default_categ_id(rpc: OdooRPC) -> int | None:
    """A product category id that is safe to create a product with.

    ``product.template.categ_id`` is REQUIRED. Core's default reads
    ``product.product_category_all`` through ``env.ref(...,
    raise_if_not_found=False)``, so when that external id is absent the
    default silently resolves to nothing and every product create fails with

        Missing required value for the field 'Product Category' (categ_id)

    Measured on d1v19 restored from d1systems-uat-37509933: the category row
    ("All", id 1) is present but its ir_model_data row is gone, so the xmlid
    resolves to nothing. The previous restore still had it — which is why the
    whole of WF-002 went from PASSED to ERROR on a database with identical
    business data.

    A fixture must not depend on an ambient default it does not control, so
    this resolves a category explicitly and every caller passes it. Returns
    None only when the database has no product category at all, in which case
    the caller should let the server raise rather than invent one.
    """
    env = getattr(rpc, "env", None)
    key = (getattr(env, "base_url", ""), getattr(env, "db", ""))
    if key in _CATEG_CACHE:
        return _CATEG_CACHE[key]

    categ_id = None
    ref = rpc.ref("product.product_category_all")
    if ref and rpc.search("product.category", [("id", "=", ref)]):
        categ_id = ref
    if categ_id is None:
        # Fall back to the lowest-id root category, which on a stock Odoo is
        # the same "All" record the xmlid would have pointed at.
        roots = rpc.search_read("product.category", [("parent_id", "=", False)],
                                ["id"], order="id", limit=1)
        if roots:
            categ_id = roots[0]["id"]
    if categ_id is None:
        any_categ = rpc.search_read("product.category", [], ["id"],
                                    order="id", limit=1)
        categ_id = any_categ[0]["id"] if any_categ else None

    _CATEG_CACHE[key] = categ_id
    return categ_id


def with_categ(rpc: OdooRPC, values: dict) -> dict:
    """Add an explicit ``categ_id`` unless the caller already chose one."""
    if not values.get("categ_id"):
        categ_id = default_categ_id(rpc)
        if categ_id:
            values["categ_id"] = categ_id
    return values
