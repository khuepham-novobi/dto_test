"""DATAONE-WF-003 — the revision lifecycle: TC095, TC096.

TC095 is the workflow's gate case: one revision must copy the DataOne
fields BY VALUE, and must cancel *and* archive the source. TC096 proves the
chain is flattened rather than nested, and that the stat button counts it.

Chaining adaptation (documented, not assertion-weakening): the workbook
hands TC095's final state to TC096 ("leave both in place for TC096").
Convention rule 5 forbids depending on another test's fixtures, so TC096
rebuilds the one-revision lineage itself before adding the second
revision. Every assertion is the workbook's.

EXPECTED v17 OUTCOME: PASS for both — base_revision and sale_order_revision
are 17.0 modules and this is their native behaviour.
EXPECTED v19 OUTCOME: BLOCKED until the OCA 19.0 ports exist (precondition
E5). Once they do, TC096 step 6 is the one to watch:
_compute_revision_count calls the public read_group() and reads
x["current_revision_id_count"] (base_revision.py:47-52) — _read_group()
returns tuples, so revision_count silently breaks and this assertion FAILS
until the compute is rewritten.
"""
from framework.registry import test_case
from tests.wf003.common import (MARK, WORKFLOW, WORKFLOW_NAME,  # noqa: F401
                                chatter_bodies, fx, m2o_id, make_quotation,
                                plain_text, read_order,
                                require_revision_stack, revision_of,
                                set_sent, sweep_wf003, trace)


@test_case(
    id="TEST-WF003-TC095",
    name="Gate case: revision -01 created, source cancelled and archived, "
         "fields copied by value",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="sale_order_revision", priority="P1", kind="API", order=3095,
    description="One revision produces <name>-01 in draft with "
                "revision_number 1; order_type, client_order_ref, "
                "analytic_account_id and tariff_amount are equal by value; "
                "the source is both cancelled and archived and points at "
                "the revision; both chatters carry the notice.",
    traceability=trace("DATAONE-TC095"))
def test_tc095(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-003 fixtures and open a fresh "
                  "namespace"):
        sweep_wf003(rpc)

    with ctx.step("Precondition: the revision stack is installed"):
        require_revision_stack(ctx)

    with ctx.step("Create the quotation and put it in state 'sent' "
                  "(revision_number 0, active, no current_revision_id)"):
        order_id, snapshot = make_quotation(ctx, order_type="project",
                                            tariff_amount=250.0)
        set_sent(rpc, order_id)
        before = read_order(rpc, order_id,
                            ["name", "state", "active", "revision_number",
                             "unrevisioned_name", "current_revision_id"])
        ctx.log(f"source order: {before['name']} (id {order_id})")
        ctx.check("source state before", "sent", before["state"])
        ctx.check("source revision_number before", 0,
                  before["revision_number"])
        ctx.check("source unrevisioned_name before", before["name"],
                  before["unrevisioned_name"])
        ctx.check("source current_revision_id before", None,
                  m2o_id(before["current_revision_id"]))

    try:
        with ctx.step("Step 2: record order_type, client_order_ref, "
                      "analytic_account_id and tariff_amount"):
            recorded = {
                "order_type": snapshot["order_type"],
                "client_order_ref": snapshot["client_order_ref"],
                "analytic_account_id": snapshot["analytic_account_id"],
                "tariff_amount": snapshot["tariff_amount"],
            }
            for key, value in recorded.items():
                ctx.log(f"  {key} = {value!r}")

        with ctx.step("Step 3: press New Revision of Quotation "
                      "(sale.order.create_revision)"):
            action = rpc.call("sale.order", "create_revision", [order_id])
            ctx.log(f"create_revision returned: {action!r}")
            new_id = revision_of(rpc, order_id)
            ctx.check_true("a revision was created", bool(new_id),
                           actual_desc=f"current_revision_id={new_id}")

        with ctx.step("Step 4: the new record is named <source>-01, "
                      "zero-padded to two digits"):
            new = read_order(rpc, new_id,
                             ["name", "state", "active", "revision_number",
                              "unrevisioned_name"])
            ctx.check("revision name", f"{before['name']}-01", new["name"])

        with ctx.step("Step 5: state 'draft', active True, revision_number "
                      "1, unrevisioned_name unchanged"):
            ctx.check("revision state", "draft", new["state"])
            ctx.check("revision active", True, new["active"])
            ctx.check("revision revision_number", 1, new["revision_number"])
            ctx.check("revision unrevisioned_name", before["name"],
                      new["unrevisioned_name"])

        with ctx.step("Step 6: all four DataOne values are equal BY VALUE "
                      "to step 2"):
            copied = read_order(rpc, new_id,
                                ["order_type", "client_order_ref",
                                 "analytic_account_id", "tariff_amount"])
            copied["analytic_account_id"] = m2o_id(
                copied["analytic_account_id"])
            mismatches = {k: {"expected": v, "actual": copied.get(k)}
                          for k, v in recorded.items()
                          if copied.get(k) != v}
            ctx.check("copied field mismatches", {}, mismatches)

        with ctx.step("Step 7: the source is state 'cancel' AND active "
                      "False, pointing at the revision"):
            after = read_order(rpc, order_id,
                               ["state", "active", "current_revision_id"])
            ctx.check("source state after", "cancel", after["state"])
            ctx.check("source active after", False, after["active"])
            ctx.check("source current_revision_id after", new_id,
                      m2o_id(after["current_revision_id"]))

        with ctx.step("Step 8: both chatters contain "
                      "'New revision created: <new name>'"):
            notice = f"New revision created: {new['name']}"
            for label, rec_id in (("source", order_id),
                                  ("revision", new_id)):
                # Matched against the rendered text, not the raw HTML: the
                # OCA 19.0 port posts the name through _get_html_link()
                # (base_revision.py:151,155) where 17.0 interpolated it as
                # plain text, so the body is
                # "New revision created: <a ...>S06508-01</a>". The
                # workbook's expectation — that both chatters carry the
                # notice naming the new record — is unchanged.
                bodies = [plain_text(b) for b in chatter_bodies(rpc, rec_id)]
                found = any(notice in b for b in bodies)
                ctx.check_true(f"{label} chatter carries the notice", found,
                               actual_desc=(f"{len(bodies)} message(s); "
                                            f"looking for {notice!r}; "
                                            f"bodies={bodies!r}"))
    finally:
        with ctx.step("Cleanup WF-003 fixtures"):
            try:
                sweep_wf003(rpc)
            except Exception as exc:      # noqa: BLE001 — never mask a verdict
                ctx.log(f"[warn] cleanup incomplete: {exc}")


@test_case(
    id="TEST-WF003-TC096",
    name="A second revision flattens the chain; the stat button lists all "
         "prior versions",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="base_revision", priority="P1", kind="API", order=3096,
    description="old_revision_ids on -02 contains BOTH earlier records "
                "(flattened, not nested); revision_count is 2 and "
                "has_old_revisions True; both priors point at -02; the "
                "stat-button action carries active_test 0 and resolves to "
                "both archived records.",
    traceability=trace("DATAONE-TC096"))
def test_tc096(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-003 fixtures and open a fresh "
                  "namespace"):
        sweep_wf003(rpc)

    with ctx.step("Precondition: the revision stack is installed"):
        require_revision_stack(ctx)

    with ctx.step("Rebuild the TC095 final state: a sent quotation revised "
                  "once (source cancelled+archived, -01 draft+active)"):
        order_id, _snapshot = make_quotation(ctx)
        base_name = read_order(rpc, order_id, ["name"])["name"]
        set_sent(rpc, order_id)
        rpc.call("sale.order", "create_revision", [order_id])
        rev1_id = revision_of(rpc, order_id)
        ctx.check("rebuilt -01 name", f"{base_name}-01",
                  read_order(rpc, rev1_id, ["name"])["name"])

    try:
        with ctx.step("Step 2: put -01 in state 'sent'"):
            set_sent(rpc, rev1_id)
            ctx.check("-01 state", "sent",
                      read_order(rpc, rev1_id, ["state"])["state"])

        with ctx.step("Step 3-4: press New Revision of Quotation; the new "
                      "record is named <source>-02"):
            rpc.call("sale.order", "create_revision", [rev1_id])
            rev2_id = revision_of(rpc, rev1_id)
            rev2 = read_order(rpc, rev2_id,
                              ["name", "state", "active", "revision_number",
                               "old_revision_ids", "revision_count",
                               "has_old_revisions"])
            ctx.check("second revision name", f"{base_name}-02",
                      rev2["name"])

        with ctx.step("Step 5: old_revision_ids contains BOTH priors — the "
                      "chain is flattened, not nested"):
            ctx.check("old_revision_ids (sorted)",
                      sorted([order_id, rev1_id]),
                      sorted(rev2["old_revision_ids"]))

        with ctx.step("Step 6: revision_count == 2 and has_old_revisions "
                      "is True"):
            ctx.check("revision_count", 2, rev2["revision_count"])
            ctx.check("has_old_revisions", True, rev2["has_old_revisions"])

        with ctx.step("Step 7: both prior records carry "
                      "current_revision_id = -02"):
            for label, rec_id in (("source", order_id), ("-01", rev1_id)):
                row = read_order(rpc, rec_id, ["current_revision_id"])
                ctx.check(f"{label} current_revision_id", rev2_id,
                          m2o_id(row["current_revision_id"]))

        with ctx.step("Step 8: the Prev. revisions stat button opens a list "
                      "containing both archived records (active_test 0)"):
            action = rpc.call("sale.order", "action_view_revisions",
                              [rev2_id])
            ctx.log(f"action_view_revisions returned: {action!r}")
            action_ctx = action.get("context") or {}
            if isinstance(action_ctx, str):
                action_ctx = {"raw": action_ctx}
            ctx.check("action passes active_test 0", 0,
                      action_ctx.get("active_test"))
            ctx.check("action defaults current_revision_id to -02", rev2_id,
                      action_ctx.get("default_current_revision_id"))
            listed = rpc.search(
                "sale.order",
                [("current_revision_id", "=", rev2_id),
                 ("active", "in", [True, False])])
            ctx.check("records the stat button resolves to (sorted)",
                      sorted([order_id, rev1_id]), sorted(listed))

        with ctx.step("The stat button carries the fa-file-archive-o icon "
                      "and the statinfo widget"):
            arch = rpc.call("sale.order", "get_view", view_type="form")["arch"]
            for needle in ('name="action_view_revisions"',
                           'icon="fa-file-archive-o"',
                           'widget="statinfo"'):
                ctx.check_true(f"form arch contains {needle}",
                               needle in arch,
                               actual_desc=("present" if needle in arch
                                            else "ABSENT — the priority-15 "
                                                 "inherit did not load"))

        with ctx.step("Exactly one member of the lineage is active and in "
                      "draft"):
            members = rpc.search_read(
                "sale.order",
                [("unrevisioned_name", "=", base_name),
                 ("active", "in", [True, False])],
                ["name", "state", "active", "revision_number"], order="id")
            ctx.log(f"lineage: {members!r}")
            live = [m for m in members
                    if m["active"] and m["state"] == "draft"]
            ctx.check("lineage size", 3, len(members))
            ctx.check("active draft members", [rev2_id],
                      [m["id"] for m in live])
    finally:
        with ctx.step("Cleanup WF-003 fixtures"):
            try:
                sweep_wf003(rpc)
            except Exception as exc:      # noqa: BLE001 — never mask a verdict
                ctx.log(f"[warn] cleanup incomplete: {exc}")
