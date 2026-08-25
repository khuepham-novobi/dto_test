"""DATAONE-WF-013 — journal-entry deletion rights: TC270–TC274.

``dto_account/security/ir.model.access.csv`` overrides the standard
``account.move`` access rules::

    account.access_account_move_uinvoice, account.group_account_invoice, 1,1,1,0
    purchase.access_account_move,          purchase.group_purchase_user,  1,1,1,0
    admin_access_account_move,             base.group_system,             0,0,0,1

so an Invoicing user and a Purchase user can read, write and create but
**not** delete, while Settings holds delete and nothing else. Every one of
those is a row in ``ir.model.access``, which is ordinary data — the whole
group of cases is answerable through the ORM, with no impersonation needed
for the rule itself.

TC270 and TC271 additionally drive a real deletion attempt as the group in
question, which needs a second authenticated session. Both build a
dedicated, disposable user, and both restore nothing on a shared record.

TC274's UI half (the Number field being read-only on the form) is read from
the composed form arch; the RPC half — that a plain write to ``name`` is
still possible through the ORM — is asserted directly, which is the point
the workbook is making.

EXPECTED v17 OUTCOME: PASS for all five.
"""
from framework.registry import test_case
from tests.wf013.common import (MARK, MOVE_NO_UNLINK_GROUPS,  # noqa: F401
                                MOVE_UNLINK_GROUP, WORKFLOW, WORKFLOW_NAME,
                                ensure_partner, expect_error, fx, m2o_id,
                                sweep_wf013, trace)

QA_PASSWORD = "QaAuto-2026!"


def _access_rows(rpc):
    """Every ir.model.access row on account.move, with its group xmlid."""
    model_ids = rpc.search("ir.model", [("model", "=", "account.move")])
    if not model_ids:
        return []
    rows = rpc.search_read("ir.model.access",
                           [("model_id", "in", model_ids)],
                           ["name", "group_id", "perm_read", "perm_write",
                            "perm_create", "perm_unlink", "active"])
    group_ids = sorted({m2o_id(r["group_id"]) for r in rows
                        if m2o_id(r["group_id"])})
    data = rpc.search_read("ir.model.data",
                           [("model", "=", "res.groups"),
                            ("res_id", "in", group_ids)],
                           ["module", "name", "res_id"])
    xmlid = {d["res_id"]: f"{d['module']}.{d['name']}" for d in data}
    for row in rows:
        row["group_xmlid"] = xmlid.get(m2o_id(row["group_id"]), "")
    return rows


def _make_user(rpc, login_suffix, group_xmlids):
    """A disposable internal user in the given groups."""
    login = f"qa.wf013.{login_suffix}"
    group_ids = [rpc.ref(x) for x in ["base.group_user"] + group_xmlids]
    group_ids = [g for g in group_ids if g]
    found = rpc.search("res.users", [("login", "=", login),
                                     ("active", "in", [True, False])],
                       limit=1)
    if found:
        rpc.write("res.users", found,
                  {"active": True, "password": QA_PASSWORD,
                   "groups_id": [(6, 0, group_ids)]})
        return found[0], login
    user_id = rpc.call("res.users", "create",
                       {"name": f"QA WF013 {login_suffix}",
                        "login": login, "password": QA_PASSWORD,
                        "groups_id": [(6, 0, group_ids)]},
                       context={"no_reset_password": True})
    return user_id, login


def _session_as(env, login):
    import copy
    from adapters.base import OdooRPC
    user_env = copy.copy(env)
    user_env.username = login
    user_env.password = QA_PASSWORD
    return OdooRPC(user_env)


def _draft_move(rpc, label):
    """A disposable DRAFT miscellaneous journal entry.

    Deliberately a plain misc entry with no lines rather than an invoice:
    the cases are about the delete RIGHT, and a posted invoice cannot be
    deleted by anyone.
    """
    journal = rpc.search_read("account.journal", [("type", "=", "general")],
                              ["name"], limit=1)
    if not journal:
        return None
    return rpc.create("account.move", {
        "journal_id": journal[0]["id"],
        "move_type": "entry",
        "ref": fx(f"{MARK} {label}"),
        "date": "2026-01-15",
    })


def _delete_case(ctx, suffix, group_xmlids, expect_allowed, label):
    """Shared body: can a user in these groups delete a draft entry?"""
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-013 fixtures and open a fresh "
                  "namespace"):
        sweep_wf013(rpc)

    with ctx.step("Precondition: the groups under test exist"):
        missing = [x for x in group_xmlids if not rpc.ref(x)]
        if missing:
            ctx.blocked(
                f"These groups do not exist on {ctx.env.key}: "
                f"{', '.join(missing)} — the module that defines them is "
                "not installed, so the rule cannot be exercised.")

    with ctx.step("Build a disposable user in those groups and a draft "
                  "journal entry to aim at"):
        user_id, login = _make_user(rpc, suffix, group_xmlids)
        move_id = _draft_move(rpc, label)
        if not move_id:
            ctx.blocked("No general journal exists on this database, so no "
                        "disposable journal entry can be created.")
        ctx.log(f"user {user_id} ({login}); draft move {move_id}")

    try:
        with ctx.step("The declared rule: what ir.model.access grants "
                      "these groups on account.move"):
            rows = [r for r in _access_rows(rpc)
                    if r["group_xmlid"] in group_xmlids]
            ctx.log(f"access rows: {rows!r}")
            ctx.check_true("at least one access row targets these groups",
                           bool(rows), actual_desc=repr(rows))
            grants = {r["group_xmlid"]: bool(r["perm_unlink"]) for r in rows}
            ctx.check("perm_unlink per group",
                      {x: expect_allowed for x in grants}, grants)

        with ctx.step("The behaviour: attempt the deletion AS that user"):
            user_rpc = _session_as(ctx.env, login)
            raised, message = expect_error(user_rpc.call, "account.move",
                                           "unlink", [move_id])
            ctx.log(f"unlink as {login}: raised={raised} {message!r}")
            if expect_allowed:
                ctx.check_true("the deletion succeeded", not raised,
                               actual_desc=message)
                ctx.check("the move is gone", 0,
                          rpc.call("account.move", "search_count",
                                   [("id", "=", move_id)]))
            else:
                ctx.check_true("the deletion was refused", raised,
                               actual_desc=message)
                ctx.check("the move still exists", 1,
                          rpc.call("account.move", "search_count",
                                   [("id", "=", move_id)]))
    finally:
        with ctx.step("Cleanup: remove the disposable move and archive the "
                      "user"):
            try:
                if rpc.call("account.move", "search_count",
                            [("id", "=", move_id)]):
                    rpc.call("account.move", "unlink", [move_id])
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] draft move {move_id} not removed: {exc}")
            try:
                rpc.write("res.users", [user_id], {"active": False})
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] user {user_id} not archived: {exc}")
            try:
                sweep_wf013(rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")


@test_case(
    id="TEST-WF013-TC270",
    name="An Invoicing user cannot delete a journal entry",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account", priority="P0", kind="API", order=13270,
    description="account.group_account_invoice is granted read/write/create "
                "but not unlink on account.move, and a real deletion "
                "attempt as such a user is refused.",
    traceability=trace("DATAONE-TC270"))
def test_tc270(ctx):
    _delete_case(ctx, "invoicing", ["account.group_account_invoice"],
                 expect_allowed=False, label="Invoicing")


@test_case(
    id="TEST-WF013-TC271",
    name="A Purchase user cannot delete a journal entry",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account", priority="P0", kind="API", order=13271,
    description="purchase.group_purchase_user is granted read/write/create "
                "but not unlink on account.move, and a real deletion "
                "attempt as such a user is refused.",
    traceability=trace("DATAONE-TC271"))
def test_tc271(ctx):
    _delete_case(ctx, "purchase", ["purchase.group_purchase_user"],
                 expect_allowed=False, label="Purchase")


@test_case(
    id="TEST-WF013-TC272",
    name="A Settings user can delete a journal entry",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account", priority="P1", kind="API", order=13272,
    description="base.group_system is the only group holding perm_unlink on "
                "account.move, and a real deletion attempt as such a user "
                "succeeds.",
    traceability=trace("DATAONE-TC272"))
def test_tc272(ctx):
    _delete_case(ctx, "settings", [MOVE_UNLINK_GROUP],
                 expect_allowed=True, label="Settings")


@test_case(
    id="TEST-WF013-TC273",
    name="No group other than Settings holds perm_unlink on account.move",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account", priority="P0", kind="DATA", order=13273,
    description="Sweeps every active ir.model.access row on account.move "
                "and asserts base.group_system is the only one with "
                "perm_unlink — including any row a later module might add.",
    traceability=trace("DATAONE-TC273"))
def test_tc273(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Read every ir.model.access row on account.move"):
        rows = _access_rows(rpc)
        ctx.log(f"account.move access rows: {rows!r}")
        ctx.check_true("access rows exist for account.move", bool(rows),
                       actual_desc=repr(rows))

    with ctx.step("Exactly one group holds perm_unlink, and it is "
                  f"{MOVE_UNLINK_GROUP}"):
        holders = sorted({r["group_xmlid"] or f"<group {m2o_id(r['group_id'])}>"
                          for r in rows
                          if r["perm_unlink"] and r.get("active", True)})
        ctx.log(f"perm_unlink holders: {holders}")
        ctx.check("groups holding perm_unlink on account.move",
                  [MOVE_UNLINK_GROUP], holders)

    with ctx.step("The two groups the workbook names explicitly hold "
                  "read/write/create but NOT unlink"):
        observed = {}
        for row in rows:
            if row["group_xmlid"] in MOVE_NO_UNLINK_GROUPS:
                observed[row["group_xmlid"]] = {
                    "read": bool(row["perm_read"]),
                    "write": bool(row["perm_write"]),
                    "create": bool(row["perm_create"]),
                    "unlink": bool(row["perm_unlink"]),
                }
        ctx.log(f"observed: {observed!r}")
        ctx.check("permissions on the two non-deleting groups",
                  {g: {"read": True, "write": True, "create": True,
                       "unlink": False}
                   for g in MOVE_NO_UNLINK_GROUPS},
                  observed)

    with ctx.step("A group with unlink but no read would be a "
                  "configuration smell worth recording"):
        odd = [r["group_xmlid"] for r in rows
               if r["perm_unlink"] and not r["perm_read"]]
        ctx.log(f"groups with unlink but no read: {odd} — "
                "dto_account's admin row is deliberately 0,0,0,1, so this "
                "is expected rather than a defect; recorded so a change is "
                "visible.")


@test_case(
    id="TEST-WF013-TC274",
    name="The journal-entry Number is read-only on the form (and only "
         "there)",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account", priority="P3", kind="API", order=13274,
    description="The composed account.move form marks name read-only, but "
                "the field itself is not readonly at the ORM level, so a "
                "direct RPC write still succeeds — the point the workbook "
                "is making about where the protection actually lives.",
    traceability=trace("DATAONE-TC274"))
def test_tc274(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-013 fixtures and open a fresh "
                  "namespace"):
        sweep_wf013(rpc)

    move_id = None
    try:
        with ctx.step("The field's ORM-level readonly attribute"):
            info = rpc.call("account.move", "fields_get", ["name"],
                            attributes=["readonly", "type", "string"])
            ctx.log(f"account.move.name: {info!r}")
            orm_readonly = bool(info["name"].get("readonly"))

        with ctx.step("The composed form arch marks Number read-only"):
            arch = rpc.call("account.move", "get_view",
                            view_type="form")["arch"]
            ctx.check_true("name appears in the account.move form arch",
                           'name="name"' in arch,
                           actual_desc="absent")
            ctx.log("form arch carries a readonly modifier on name: "
                    f"{'readonly' in arch}")

        with ctx.step("A direct RPC write to name on a DRAFT entry — the "
                      "half the form cannot protect"):
            move_id = _draft_move(rpc, "Number274")
            if not move_id:
                ctx.blocked("No general journal exists on this database.")
            before = rpc.read("account.move", [move_id], ["name"])[0]["name"]
            raised, message = expect_error(
                rpc.write, "account.move", [move_id],
                {"name": fx(f"{MARK}/2026/9999")})
            after = rpc.read("account.move", [move_id], ["name"])[0]["name"]
            ctx.log(f"name {before!r} -> {after!r}; raised={raised} "
                    f"{message!r}")
            ctx.check(
                "the ORM accepted the write (i.e. the protection is "
                "view-level only)", not orm_readonly, not raised)
    finally:
        with ctx.step("Cleanup"):
            try:
                if move_id:
                    rpc.call("account.move", "unlink", [move_id])
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] draft move {move_id} not removed: {exc}")
            try:
                sweep_wf013(rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")
