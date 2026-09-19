"""DATAONE-WF-016 — segregation of duties: TC267, TC268, TC269.

Invoicing users raise and post invoices; only accounting managers move
money. Three cases, in ascending order of how much they actually protect:

* TC267 — the BUTTON. Decoration. Proves the views hide Register Payment
  from a non-manager.
* TC268 — the ACL, proved by behaviour. A non-manager issuing a direct
  ``call_kw`` against ``account.payment.register`` is refused. Anyone with
  a saved action, a bookmarked URL or an RPC client bypasses the button;
  the ACL is the control.
* TC269 — the ACL ROW ITSELF, proved by reading ``ir.model.data``. This is
  the one that catches the silent failure, and it is the reason the other
  two are not sufficient.

The silent failure
------------------
``dto_account/security/ir.model.access.csv`` reuses the CORE xml id
``account.access_account_payment_register``. Reusing a core id OVERWRITES
the core row, which is how DataOne narrows it from
``account.group_account_invoice`` to ``account.group_account_manager``.
If v19 renamed or dropped that id, the CSV instead creates a NEW record
owned by ``dto_account`` while the permissive core row survives — and every
invoicing user can register payments again. Delta §5 confirms the CSV
FORMAT is unchanged, which is not the same thing. No error, no log line, no
visible symptom. TC269 reads ``ir.model.data.module`` for the row and
asserts it is still ``account`` — the only observation that distinguishes
"overwritten" from "duplicated".

The view surface is version-dependent, by design
------------------------------------------------
TC267's "all three views" is a v17 statement. v17 rendered Register Payment
in the invoice form, in ``account.view_invoice_tree`` and in
``account.view_move_line_payment_tree``, and DataOne re-gated all three.
v19 removed the button from both LISTS; ``action_register_payment`` occurs
exactly twice in ``account/views/account_move_views.xml`` (:734 and :746)
and both are inside the FORM. DataOne therefore deleted its two list
inherits and gates both form buttons **by id** — because an inherit that
located by name alone would match only the first, leaving the
with-outstanding-credits button on core's wider
``account.group_account_invoice``. Net effect: unchanged or tighter, never
looser.

This is the documented exception in AUTOMATION_CONVENTIONS.md: the case's
SUBJECT is the version delta, so it reads ``ctx.env.version`` to compute
its own expected value. Nothing about how it runs changes.

EXPECTED v17 OUTCOME: PASS for all three.
EXPECTED v19 OUTCOME: PASS. TC269 FAILING on v19 is the finding — it means
the core xml id moved and the restriction silently stopped existing.
"""
from framework.registry import test_case
from tests.wf016.common import (MARK,  # noqa: F401
                                PAYMENT_REGISTER_ACL_XMLID,
                                PAYMENT_REGISTER_GROUP,
                                PAYMENT_REGISTER_MODEL,
                                PAYMENT_REGISTER_PERMS,
                                REGISTER_PAYMENT_BUTTON_IDS,
                                REGISTER_PAYMENT_VIEWS, WORKFLOW,
                                WORKFLOW_NAME, attach_to_move,
                                ensure_product, ensure_vendor, expect_error,
                                fx, m2o_id, make_bare_bill, make_user,
                                require_dto_account, session_as, sweep_wf016,
                                trace)


def _posted_unpaid_bill(ctx):
    """A posted vendor bill with a residual balance, owned by this suite."""
    rpc = ctx.adapter.rpc
    vendor_id = ensure_vendor(rpc)
    product_id = ensure_product(ctx)
    bill_id = make_bare_bill(ctx, vendor_id, product_id, label="payment")
    attach_to_move(rpc, bill_id, via="move")
    rpc.call("account.move", "action_post", [bill_id])
    row = rpc.read("account.move", [bill_id],
                   ["state", "amount_residual", "name"])[0]
    if row["state"] != "posted":
        ctx.blocked(f"The fixture vendor bill did not post ({row!r}); "
                    "there is nothing to register a payment against.")
    return bill_id, row


def _view_arch(rpc, xmlid, model, ref_rpc=None):
    """The arch of one named view, or None when the view does not exist.

    ``get_view`` is public on both versions (v17
    base/models/ir_ui_view.py:2613, v19 :3138) and takes a view id.

    ``ref_rpc`` resolves the xmlid and defaults to ``rpc``. The negatives
    below read views AS a non-manager, and a plain internal user may not
    read ir.model.data — "This operation is allowed for the following
    groups: Access Rights". Resolving the xmlid through that user therefore
    raises before any view is read, which is an artefact of HOW the view is
    named, not the access question under test. The id is resolved once as
    admin; the ARCH is still fetched as the restricted user, which is what
    the case is about.
    """
    view_id = (ref_rpc or rpc).ref(xmlid)
    if not view_id:
        return None
    try:
        return rpc.call(model, "get_view", view_id)["arch"]
    except Exception:                      # noqa: BLE001
        return None


@test_case(
    id="TEST-WF016-TC267",
    name="Register Payment is not rendered for a non-manager, in all three "
         "views",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account", priority="P1", kind="API", order=16267,
    description="Reads the rendered arch as each of three non-manager "
                "users and as an accounting manager, across the views that "
                "carry the button ON THIS VERSION (three on v17, the form "
                "alone on v19, where both of its buttons must be gated by "
                "id).",
    traceability=trace("DATAONE-TC267"))
def test_tc267(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-016 fixtures and open a fresh "
                  "namespace"):
        sweep_wf016(rpc)

    with ctx.step("Preconditions: dto_account installed"):
        require_dto_account(ctx)

    with ctx.step("Determine which views carry the button ON THIS VERSION. "
                  "v19 removed it from both lists; DataOne deleted those "
                  "two inherits rather than re-anchoring them, and gates "
                  "the form's TWO buttons by id instead"):
        version = ctx.env.version
        views = REGISTER_PAYMENT_VIEWS.get(version,
                                           REGISTER_PAYMENT_VIEWS["17"])
        ctx.log(f"Odoo {version}: the restriction is expressed in "
                f"{[v for v, _ in views]}")
        if version == "19":
            ctx.log("v19 gates account_invoice_payment_btn AND "
                    "account_invoice_payment_secondary_btn. Gating only the "
                    "first would leave any Billing user able to register a "
                    "payment on an invoice that has outstanding credits — "
                    "a silent security regression with no error.")

    try:
        with ctx.step("A posted, unpaid vendor bill and one posted customer "
                      "invoice to look at"):
            bill_id, bill = _posted_unpaid_bill(ctx)
            ctx.log(f"posted bill: {bill!r}")

        with ctx.step("Provision the four users: three non-managers "
                      "(invoicing, purchase, sales) and one accounting "
                      "manager"):
            users = {}
            for suffix, groups in (
                    ("invoicing", ["account.group_account_invoice"]),
                    ("purchase", ["purchase.group_purchase_user"]),
                    ("sales", ["sales_team.group_sale_salesman"]),
                    ("manager", ["account.group_account_manager"])):
                user_id, login = make_user(ctx, suffix, groups)
                users[suffix] = (user_id, login, session_as(ctx.env, login))
                ctx.log(f"{suffix}: uid={user_id} login={login}")

        with ctx.step("Steps 1-5 — THE NEGATIVES: the button is absent "
                      "from every relevant view for every non-manager"):
            leaks = {}
            for suffix in ("invoicing", "purchase", "sales"):
                _, login, user_rpc = users[suffix]
                for xmlid, _view_type in views:
                    model = ("account.move.line"
                             if "move_line" in xmlid else "account.move")
                    arch = _view_arch(user_rpc, xmlid, model,
                                      ref_rpc=rpc)
                    if arch is None:
                        ctx.log(f"[note] {xmlid} does not exist on "
                                f"{ctx.env.key} — expected on v19 for the "
                                "two list views.")
                        continue
                    if "action_register_payment" in arch:
                        leaks[f"{suffix}@{xmlid}"] = "button present"
            ctx.log(f"non-manager arch scan: {leaks!r}")
            ctx.check("views where a NON-MANAGER can see Register Payment",
                      {}, leaks)

        with ctx.step("Step 6 — THE POSITIVE: the manager DOES see it, so "
                      "the negatives above are the groups= gate and not a "
                      "renamed button"):
            _, _, mgr_rpc = users["manager"]
            seen = {}
            for xmlid, _view_type in views:
                model = ("account.move.line" if "move_line" in xmlid
                         else "account.move")
                arch = _view_arch(mgr_rpc, xmlid, model, ref_rpc=rpc)
                if arch is None:
                    continue
                seen[xmlid] = "action_register_payment" in arch
            ctx.log(f"manager arch scan: {seen!r}")
            ctx.check_true(
                "the manager sees Register Payment in at least one view — "
                "otherwise the negatives prove nothing",
                any(seen.values()), actual_desc=seen)

        if version == "19":
            with ctx.step("v19 only — BOTH form buttons are gated, not "
                          "just the first. This is the new delta and it is "
                          "the silent regression a name-based inherit "
                          "would cause"):
                _, _, inv_rpc = users["invoicing"]
                arch = _view_arch(inv_rpc, "account.view_move_form",
                                  "account.move", ref_rpc=rpc) or ""
                still_visible = [b for b in REGISTER_PAYMENT_BUTTON_IDS
                                 if b in arch]
                ctx.log(f"buttons still in a Billing user's arch: "
                        f"{still_visible!r}")
                ctx.check("payment buttons visible to a Billing user on v19",
                          [], still_visible)

        with ctx.step("Step 7: the manager can open the Register Payment "
                      "wizard. Done here by creating the wizard record, "
                      "which is what the button does — and is also TC268's "
                      "positive control"):
            _, _, mgr_rpc = users["manager"]
            raised, message = expect_error(
                mgr_rpc.call, PAYMENT_REGISTER_MODEL, "create",
                {}, {"active_model": "account.move",
                     "active_ids": [bill_id]})
            ctx.log(f"manager wizard create: raised={raised} {message!r}")
            ctx.check_true(
                "the manager is NOT refused at the ACL layer",
                not (raised and "access" in message.lower()),
                actual_desc=message)
    finally:
        with ctx.step("Cleanup WF-016 fixtures"):
            try:
                sweep_wf016(rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")


@test_case(
    id="TEST-WF016-TC268",
    name="Register Payment is denied at the ACL layer by direct RPC",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account", priority="P0", kind="API", order=16268,
    description="A non-manager's direct call_kw to "
                "account.payment.register create and "
                "action_create_payments is refused with an access error, "
                "no account.payment exists for the bill afterwards, and "
                "the manager's identical call succeeds.",
    traceability=trace("DATAONE-TC268"))
def test_tc268(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-016 fixtures and open a fresh "
                  "namespace"):
        sweep_wf016(rpc)

    with ctx.step("Preconditions: dto_account installed"):
        require_dto_account(ctx)

    try:
        with ctx.step("A posted, unpaid vendor bill — the thing a payment "
                      "would settle"):
            bill_id, bill = _posted_unpaid_bill(ctx)
            ctx.log(f"posted bill: {bill!r}")
            partner_id = m2o_id(rpc.read("account.move", [bill_id],
                                         ["partner_id"])[0]["partner_id"])

        with ctx.step("Step 1: authenticate a session as a NON-MANAGER "
                      "invoicing user — bypassing the UI entirely"):
            inv_uid, inv_login = make_user(
                ctx, "invoicing", ["account.group_account_invoice"])
            inv_rpc = session_as(ctx.env, inv_login)
            groups_field = ctx.adapter.user_groups_field
            manager_group = rpc.ref("account.group_account_manager")
            user_groups = rpc.read("res.users", [inv_uid],
                                   [groups_field])[0][groups_field]
            ctx.log(f"{inv_login} groups: {user_groups!r}")
            ctx.check_true(
                "the user is NOT an accounting manager — otherwise the "
                "negative proves nothing",
                manager_group not in user_groups,
                actual_desc=f"manager group {manager_group}")

        with ctx.step("Steps 2-3 — THE CONTROL: create on "
                      "account.payment.register is refused at the ACL "
                      "layer, naming the model"):
            raised, message = expect_error(
                inv_rpc.call, PAYMENT_REGISTER_MODEL, "create",
                {"payment_date": "2026-01-20"},
                {"active_model": "account.move", "active_ids": [bill_id]})
            ctx.log(f"non-manager create: raised={raised} {message!r}")
            ctx.check_true("the non-manager's create was refused", raised,
                           actual_desc=message)
            ctx.check_true(
                "the refusal is an ACCESS error naming "
                f"{PAYMENT_REGISTER_MODEL} (not a validation error)",
                ("access" in message.lower()
                 or PAYMENT_REGISTER_MODEL in message),
                actual_desc=message)

        with ctx.step("Steps 4-5: action_create_payments is refused too — "
                      "the second half of the wizard, in case only create "
                      "were gated"):
            raised2, message2 = expect_error(
                inv_rpc.call, PAYMENT_REGISTER_MODEL,
                "action_create_payments", [])
            ctx.log(f"non-manager action_create_payments: raised={raised2} "
                    f"{message2!r}")
            ctx.check_true("action_create_payments was refused too", raised2,
                           actual_desc=message2)

        with ctx.step("Step 6: ZERO account.payment records exist against "
                      "the bill"):
            payments = rpc.search_read(
                "account.payment", [("partner_id", "=", partner_id)],
                ["name", "state", "amount"])
            ctx.log(f"payments for the fixture vendor: {payments!r}")
            ctx.check("payments created by the non-manager", 0,
                      len(payments))

        with ctx.step("Steps 7-8 — THE POSITIVE CONTROL: the manager's "
                      "identical call is NOT refused, proving the refusals "
                      "above were the ACL and not a broken payload"):
            mgr_uid, mgr_login = make_user(
                ctx, "acctmgr", ["account.group_account_manager"])
            mgr_rpc = session_as(ctx.env, mgr_login)
            raised3, message3 = expect_error(
                mgr_rpc.call, PAYMENT_REGISTER_MODEL, "create",
                {"payment_date": "2026-01-20"},
                {"active_model": "account.move", "active_ids": [bill_id]})
            ctx.log(f"manager create: raised={raised3} {message3!r}")
            ctx.check_true(
                "the manager was NOT refused at the ACL layer",
                not (raised3 and "access" in message3.lower()),
                actual_desc=message3)
            ctx.log("The wizard record itself is left unconfirmed — the "
                    "workbook's postcondition is that the bill stays "
                    "UNPAID, so no payment is created here.")

        with ctx.step("The bill is still unpaid — nothing in this case "
                      "moved money"):
            after = rpc.read("account.move", [bill_id],
                             ["amount_residual", "payment_state"])[0]
            ctx.log(f"bill after the case: {after!r}")
            ctx.check_true("the bill still carries a residual balance",
                           bool(after["amount_residual"]),
                           actual_desc=after)
    finally:
        with ctx.step("Cleanup WF-016 fixtures"):
            try:
                sweep_wf016(rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")


@test_case(
    id="TEST-WF016-TC269",
    name="Post-install assertion: the payment-register ACL row really "
         "names the manager group",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account", priority="P0", kind="API", order=16269,
    description="Resolves account.access_account_payment_register, asserts "
                "it is a single ir.model.access row on "
                "account.payment.register granting "
                "account.group_account_manager 1/1/1/0, asserts the xml id "
                "is still OWNED BY THE CORE 'account' module (a DataOne-"
                "owned row means the core row survived and the restriction "
                "silently vanished), and asserts no other group holds any "
                "permission on the model.",
    traceability=trace("DATAONE-TC269"))
def test_tc269(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Preconditions: dto_account installed. This case creates "
                  "nothing and is entirely read-only"):
        require_dto_account(ctx)

    with ctx.step("Steps 1-2: the external ID resolves to exactly one "
                  "ir.model.access row"):
        module, _, name = PAYMENT_REGISTER_ACL_XMLID.partition(".")
        rows = rpc.search_read(
            "ir.model.data",
            [("module", "=", module), ("name", "=", name)],
            ["model", "res_id", "module", "name"])
        ctx.log(f"ir.model.data rows for {PAYMENT_REGISTER_ACL_XMLID}: "
                f"{rows!r}")
        ctx.check(f"ir.model.data rows named {PAYMENT_REGISTER_ACL_XMLID}",
                  1, len(rows))
        ctx.check("the xml id points at an ir.model.access record",
                  "ir.model.access", rows[0]["model"])
        acl_id = rows[0]["res_id"]

    with ctx.step("THE SILENT-FAILURE ASSERTION: the row is still owned by "
                  "the CORE 'account' module. A row owned by dto_account "
                  "means the core id moved, DataOne's CSV created a NEW "
                  "record, and the permissive core row is still in place"):
        ctx.check("owning module of the payment-register ACL row",
                  "account", rows[0]["module"])
        dto_owned = rpc.search_read(
            "ir.model.data",
            [("model", "=", "ir.model.access"),
             ("module", "=", "dto_account"),
             ("name", "like", "access_account_payment_register")],
            ["name", "res_id"])
        ctx.log(f"dto_account-owned payment-register rows: {dto_owned!r}")
        ctx.check("dto_account-owned duplicates of the payment-register "
                  "ACL", [], dto_owned)

    with ctx.step("Steps 3-5: the row names account.payment.register, "
                  "account.group_account_manager, and the 1/1/1/0 "
                  "permission set"):
        acl = rpc.read("ir.model.access", [acl_id],
                       ["name", "model_id", "group_id", "perm_read",
                        "perm_write", "perm_create", "perm_unlink",
                        "active"])[0]
        ctx.log(f"ACL row: {acl!r}")
        model_name = rpc.read("ir.model", [m2o_id(acl["model_id"])],
                              ["model"])[0]["model"]
        ctx.check("model", PAYMENT_REGISTER_MODEL, model_name)
        group_id = m2o_id(acl["group_id"])
        ctx.check("group", rpc.ref(PAYMENT_REGISTER_GROUP), group_id)
        ctx.check("permissions", PAYMENT_REGISTER_PERMS,
                  {key: acl[key] for key in PAYMENT_REGISTER_PERMS})
        ctx.check_true("the ACL row is active", acl.get("active", True),
                       actual_desc=acl.get("active"))

    with ctx.step("Steps 6-7: NO other group holds any permission on "
                  "account.payment.register. A surviving core row would "
                  "show up exactly here"):
        model_id = m2o_id(acl["model_id"])
        all_rows = rpc.search_read(
            "ir.model.access", [("model_id", "=", model_id)],
            ["name", "group_id", "perm_read", "perm_write", "perm_create",
             "perm_unlink", "active"])
        ctx.log(f"every ACL row on {PAYMENT_REGISTER_MODEL}: {all_rows!r}")
        manager_group = rpc.ref(PAYMENT_REGISTER_GROUP)
        others = {
            row["group_id"][1] if row["group_id"] else "(no group — global)":
                {perm: row[perm] for perm in PAYMENT_REGISTER_PERMS}
            for row in all_rows
            if m2o_id(row["group_id"]) != manager_group
            and any(row[perm] for perm in PAYMENT_REGISTER_PERMS)}
        ctx.check("groups other than Accounting Manager with access to "
                  f"{PAYMENT_REGISTER_MODEL}", {}, others)
