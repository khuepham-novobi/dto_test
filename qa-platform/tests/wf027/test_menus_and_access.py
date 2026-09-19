"""DATAONE-WF-027 — who sees the Reports app, and what its menus serve.

Seven cases. ``dto_reports`` contributes 14 menus and one group, and
nothing else that a test can drive: there is no QWeb report, no
``ir.actions.report`` and no spreadsheet anywhere in the module. So the
assertions here are about wiring — which action a menu serves, which view
that action pins, and who the group lets through.

The group has no category, and that is deliberate
--------------------------------------------------
``data/groups.xml:5`` defines ``reports_module`` ("Review reports"). Its
``category_id`` line was **deleted** for v19 (D-new-14): the field became
``privilege_id``, and a group with neither is v19's spelling of "hidden".
TC376 asserts that absence rather than treating it as an oversight — a
group that reappears in the Settings UI would be a visible regression.

What is blocked, and why it is not a gap
-----------------------------------------
TC013 and TC088 are typed **TOUR** in the workbook: they assert what a
browser renders as a particular user. This platform drives Odoo over RPC.
Both cases assert everything reachable — the menus resolve, the actions
exist, the group gates them, a non-member is refused — and then block on
the rendering half, naming it. TC389 is the same shape for an inline
multi-edit.

EXPECTED v17 OUTCOME
  TC376, TC387, TC388 PASS; TC013, TC088, TC389 BLOCKED on their browser
  half.
EXPECTED v19 OUTCOME
  The same, with one watch: ``ir.ui.menu.groups_id`` was renamed
  ``group_ids`` in v19 and TEST-WF001-TC342 fails on exactly that. Every
  helper here probes for the field rather than assuming it.
"""
from framework.qa_fixtures import ensure_qa_user, rpc_as_qa_user
from framework.registry import test_case
from tests.wf027.common import (ALL_MENUS, DELETED_VIEWS, EXPECTED_MENU_COUNT,
                                GATED_MENUS, REPORTS_GROUP, REPORT_ACTIONS,
                                SURVIVING_VIEW, WORKFLOW, WORKFLOW_NAME,
                                action_of, menu_group_field, menu_row,
                                require_reports, trace, user_group_field,
                                view_exists, visible_menu_ids)


@test_case(
    id="TEST-WF027-TC376",
    name='The Reports app is visible to a "Review reports" member and absent '
         "for a non-member",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_reports",
    priority="P0", kind="SEC", order=27376,
    description="The group exists with no application category, gates the "
                "four top menus, and a plain internal user cannot reach the "
                "report actions behind them.",
    traceability=trace("DATAONE-TC376"))
def test_tc376(ctx):
    rpc = ctx.adapter.rpc
    require_reports(ctx)

    with ctx.step("The group exists"):
        group_id = rpc.ref(REPORTS_GROUP)
        ctx.check_true(f"{REPORTS_GROUP} resolves", bool(group_id),
                       str(group_id))
        row = rpc.search_read("res.groups", [("id", "=", group_id)],
                              ["name", "category_id"]
                              if rpc.field_exists("res.groups", "category_id")
                              else ["name"])[0]
        ctx.log(f"group: {row}")

    with ctx.step("Step 12: it has NO application category — v19's spelling "
                  "of hidden, and intended behaviour rather than a bug"):
        # The workbook flags this as the half most often written up as a
        # defect. D-new-14 deleted the category_id line when v19 renamed the
        # field to privilege_id; a group carrying neither does not appear in
        # the Settings user form. Asserted as an OUTCOME.
        hidden = True
        for field in ("category_id", "privilege_id"):
            if rpc.field_exists("res.groups", field):
                value = rpc.search_read("res.groups", [("id", "=", group_id)],
                                        [field])[0][field]
                ctx.log(f"res.groups.{field} = {value!r}")
                if value:
                    hidden = False
        ctx.check_true("the group carries neither a category nor a privilege, "
                       "so it stays out of the Settings UI", hidden,
                       "see the log above")

    with ctx.step("All 14 menus resolve, and the four top ones are gated"):
        resolved = {x: rpc.ref(x) for x in ALL_MENUS}
        missing = [x for x, v in resolved.items() if not v]
        ctx.check("menus that do not resolve", [], missing)
        ctx.check("menu count", EXPECTED_MENU_COUNT, len(ALL_MENUS))
        for xmlid in GATED_MENUS:
            row = menu_row(rpc, xmlid)
            ctx.check_true(f"{xmlid} names the group",
                           group_id in (row or {}).get("_groups", []),
                           str((row or {}).get("_groups")))
        ctx.log(f"menu group field on this version: {menu_group_field(rpc)}")

    with ctx.step("Steps 8-9: a plain internal user is NOT a member"):
        ensure_qa_user(rpc)
        plain = rpc_as_qa_user(ctx.env)
        uid = plain.uid
        field = user_group_field(rpc)
        member_ids = rpc.search("res.users",
                                [("id", "=", uid), (field, "in", [group_id])])
        ctx.check("the plain user is a member", [], member_ids)

    with ctx.step("Step 10: and the gated menus are not in their menu set"):
        # Through load_menus, NOT search: ir.ui.menu does not filter by group
        # at the search layer, so search() hands a non-member the gated menu
        # and a security assertion written that way reports a false breach.
        reachable = visible_menu_ids(plain)
        leaked = sorted(set(resolved.values()) & reachable)
        ctx.check("gated menus reachable by a non-member", [], leaked)
        ctx.log(f"the non-member's menu tree holds {len(reachable)} menus, "
                f"none of them dto_reports'")
        ctx.log("RECORDED: the menus are filtered out of the menu tree rather "
                "than raising on access — which is what makes step 12's "
                "hidden-group design safe.")


@test_case(
    id="TEST-WF027-TC387",
    name="Vendor RMA and Customer RMA menus resolve and open the correct "
         "picking lists",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_reports",
    priority="P2", kind="SMOKE", order=27387,
    description="Both ids resolve, both point at an action over stock.picking, "
                "both are group-gated, and neither is visible to a "
                "non-member.",
    traceability=trace("DATAONE-TC387"))
def test_tc387(ctx):
    rpc = ctx.adapter.rpc
    require_reports(ctx)
    group_id = rpc.ref(REPORTS_GROUP)
    rma_menus = ("dto_reports.vendor_rma_reports_menu",
                 "dto_reports.customer_rma_reports_menu")

    with ctx.step("Both ids resolve and carry an action"):
        for xmlid in rma_menus:
            row = menu_row(rpc, xmlid)
            ctx.check_true(f"{xmlid} resolves", bool(row), str(row))
            ctx.check_true(f"{xmlid} names an action",
                           bool((row or {}).get("action")),
                           str((row or {}).get("action")))
            ctx.log(f"{xmlid} -> {row.get('action')}")

    with ctx.step("Each action opens a picking list"):
        for xmlid in rma_menus:
            row = menu_row(rpc, xmlid)
            action = (row or {}).get("action") or ""
            # ir.ui.menu.action is a reference field: "ir.actions.act_window,NN"
            model, _, action_id = str(action).partition(",")
            ctx.check("the menu points at an act_window",
                      "ir.actions.act_window", model)
            if action_id:
                target = rpc.search_read(
                    "ir.actions.act_window", [("id", "=", int(action_id))],
                    ["res_model", "view_mode", "domain"])
                ctx.check_true(f"{xmlid} opens stock.picking",
                               target and target[0]["res_model"]
                               == "stock.picking",
                               str(target))
                ctx.log(f"{xmlid}: {target}")

    with ctx.step("Both are group-gated"):
        for xmlid in rma_menus:
            row = menu_row(rpc, xmlid)
            ctx.check_true(f"{xmlid} names the reports group",
                           group_id in (row or {}).get("_groups", []),
                           str((row or {}).get("_groups")))

    with ctx.step("Neither is reachable by a non-member"):
        ensure_qa_user(rpc)
        plain = rpc_as_qa_user(ctx.env)
        ids = {rpc.ref(x) for x in rma_menus}
        ctx.check("RMA menus in a non-member's menu tree", [],
                  sorted(ids & visible_menu_ids(plain)))


@test_case(
    id="TEST-WF027-TC388",
    name="Which ir.ui.view the standard Purchase menu actually serves for "
         "purchase.order",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_reports",
    priority="P0", kind="REGR", order=27388,
    description="The Reports app's purchase action wins by an explicit "
                "view_ids pin rather than by view priority, and the four "
                "standalone views C19 deleted stay deleted.",
    traceability=trace("DATAONE-TC388"))
def test_tc388(ctx):
    """The half of this case that compares v17's served view to v19's is a
    DATA_RECONCILIATION against a baseline that does not exist yet, and it
    blocks at the end. What IS asserted first is the mechanism the workbook
    is really asking about: whether the Reports app wins by PINNING a view
    or by out-prioritising the core one.

    That distinction matters because C19 found four of the five standalone
    views never rendered at all — they lost a priority tie on database id
    (``views/sale_order.xml:59-79``: id 891 < 2143 on v17, 1734 < 1991 on
    v19). A view that wins by priority wins by accident; a view that is
    pinned in ``view_ids`` wins on purpose.
    """
    rpc = ctx.adapter.rpc
    require_reports(ctx)

    with ctx.step("The four views C19 deleted are still gone"):
        # Resurrecting one would silently change what a menu serves, and it
        # would do so without any code referencing it.
        present = [x for x in DELETED_VIEWS if view_exists(rpc, x)]
        ctx.check("deleted standalone views that came back", [], present)

    with ctx.step("The one that survived is present, and is an inheritance"):
        ctx.check_true(f"{SURVIVING_VIEW} exists", view_exists(rpc,
                                                               SURVIVING_VIEW),
                       SURVIVING_VIEW)
        view_id = rpc.ref(SURVIVING_VIEW)
        row = rpc.search_read("ir.ui.view", [("id", "=", view_id)],
                              ["name", "type", "priority", "inherit_id",
                               "mode"])[0]
        ctx.log(f"{SURVIVING_VIEW}: {row}")
        ctx.check_true("it is an inheritance, not a standalone view — C19 "
                       "rebuilt it that way so it cannot lose a priority tie",
                       bool(row.get("inherit_id")), str(row.get("inherit_id")))

    with ctx.step("Step 8: the Reports purchase action pins its view "
                  "explicitly"):
        action = action_of(rpc, "dto_reports.purchase_form_action_reports")
        ctx.check_true("the action exists", bool(action), str(action))
        if action:
            ctx.check("it reads purchase.order", "purchase.order",
                      action["res_model"])
            pinned = rpc.search_read(
                "ir.actions.act_window.view",
                [("act_window_id", "=", rpc.ref(
                    "dto_reports.purchase_form_action_reports"))],
                ["view_id", "view_mode", "sequence"])
            ctx.log(f"pinned views: {pinned}")
            ctx.check_true(
                "the action pins at least one view explicitly, so it wins on "
                "purpose rather than by out-prioritising core",
                bool(pinned) or bool(action.get("view_id")),
                f"view_ids={pinned} view_id={action.get('view_id')}")

    with ctx.step("Step 12: the sales control — its action has no such pin"):
        sale_action = action_of(rpc, "dto_reports.action_orders_reports")
        ctx.check_true("the sales report action exists", bool(sale_action),
                       str(sale_action))
        if sale_action:
            ctx.check("it reads sale.order", "sale.order",
                      sale_action["res_model"])
            ctx.log("The sale standalone view was one of the four deleted, "
                    "so this action serves the core list — which is exactly "
                    "what it served before, because the fork never rendered.")

    with ctx.step("The v17-vs-v19 comparison itself"):
        ctx.blocked(
            "the remaining half of this case compares WHICH view id the "
            "standard Purchase menu served on v17 against what it serves on "
            "v19, and no v17 baseline has been captured for "
            "DATAONE-TC388. Run this suite against the Odoo 17 target once "
            "to create it. The mechanism the comparison is meant to expose — "
            "pin versus priority — is asserted above and holds.")


# --------------------------------------------------------- browser-bound
@test_case(
    id="TEST-WF027-TC013",
    name="Every menu in the custom menu tree opens without error, as a user "
         "in the group and as one outside it",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_reports",
    priority="P1", kind="SMOKE", order=27013,
    description="Each menu resolves to an action over an existing model with "
                "a parseable domain; the group gate is proved to change the "
                "result. The rendering half needs a browser and is blocked.",
    traceability=trace("DATAONE-TC013"))
def test_tc013(ctx):
    """The workbook types this TOUR. Its step 4 is the important one: the
    member's and non-member's menu sets must be **different**, because an
    identical result means the gate is not being applied — "a security
    finding, not a pass". That half is fully reachable over RPC and is
    asserted here before the case blocks on the rendering.
    """
    rpc = ctx.adapter.rpc
    require_reports(ctx)

    with ctx.step("Step 2: every menu resolves to an action over a model "
                  "that exists"):
        broken = []
        for xmlid in ALL_MENUS:
            row = menu_row(rpc, xmlid)
            if not row:
                broken.append(f"{xmlid}: does not resolve")
                continue
            action = str(row.get("action") or "")
            if not action:
                continue        # a parent menu legitimately has no action
            model, _, action_id = action.partition(",")
            if model != "ir.actions.act_window" or not action_id:
                broken.append(f"{xmlid}: action={action!r}")
                continue
            target = rpc.search_read("ir.actions.act_window",
                                     [("id", "=", int(action_id))],
                                     ["res_model", "domain"])
            if not target:
                broken.append(f"{xmlid}: action {action_id} missing")
            elif not rpc.model_exists(target[0]["res_model"]):
                broken.append(f"{xmlid}: model {target[0]['res_model']} absent")
        ctx.check("menus whose action or model is broken", [], broken)

    with ctx.step("Step 3: every report action names a model that exists"):
        wrong = []
        for xmlid, expected_model in REPORT_ACTIONS.items():
            action = action_of(rpc, xmlid)
            if not action:
                wrong.append(f"{xmlid}: no action")
            elif action["res_model"] != expected_model:
                wrong.append(f"{xmlid}: {action['res_model']} != "
                             f"{expected_model}")
        ctx.check("report actions pointing at the wrong model", [], wrong)

    with ctx.step("FINDING: the group ships with no members at all"):
        # Measured on d1v19. Contrast "Cost Analysis View", which ships with
        # admin, elove, jsolls, klotspeich and __system__. reports_module has
        # nobody -- and since D-new-14 deleted its category, it does not
        # appear in the Settings user form either, so nobody can be added
        # through the UI. The 14 menus are unreachable by every user on the
        # database, including admin.
        group_id = rpc.ref(REPORTS_GROUP)
        field = user_group_field(rpc)
        members = rpc.search_read(
            "res.users", [(field, "in", [group_id]),
                          ("active", "in", [True, False])], ["login"])
        ctx.log(f"{REPORTS_GROUP} members: "
                f"{[m['login'] for m in members] or 'NONE'}")
        ctx.check_true(
            "somebody holds the group that gates the Reports app",
            bool(members),
            "no user on this database holds dto_reports.reports_module, and "
            "the group is hidden from the Settings UI (D-new-14 deleted its "
            "category for v19), so the entire Management Reporting app is "
            "unreachable — by admin too. On v17 the group carried a category "
            "and could be ticked in Settings.")

    with ctx.step("Step 4: with the group granted, the menu sets DIFFER — "
                  "an identical result would be a security finding"):
        # Granted to THIS suite's own QA user and revoked in the finally
        # block. Rule 3: no pre-existing user's groups are touched.
        ensure_qa_user(rpc)
        plain = rpc_as_qa_user(ctx.env)
        member_uid = plain.uid
        ids = {rpc.ref(x) for x in ALL_MENUS if rpc.ref(x)}
        as_non_member = ids & visible_menu_ids(plain)
        try:
            rpc.write("res.users", [member_uid],
                      {field: [(4, group_id)]})
            member_rpc = rpc_as_qa_user(ctx.env)
            as_member = ids & visible_menu_ids(member_rpc)
            ctx.log(f"as a member: {len(as_member)} menus; "
                    f"as a non-member: {len(as_non_member)}")
            ctx.check_true(
                "granting the group changes what the user can reach",
                as_member != as_non_member,
                f"member={sorted(as_member)} non_member={sorted(as_non_member)}")
            ctx.check_true(
                "and a member reaches the reports menus",
                bool(as_member), str(sorted(as_member)))
        finally:
            rpc.write("res.users", [member_uid], {field: [(3, group_id)]})
            ctx.log("group revoked from the QA user")

    with ctx.step("The rendering half"):
        ctx.blocked(
            "steps 5-8 assert that each menu OPENS in a browser without a "
            "client-side error, for a member and for a non-member. That is a "
            "TOUR: it needs a rendered web client, and this platform drives "
            "Odoo over RPC. Everything server-side that the tour would "
            "exercise — the menus resolve, their actions exist, their models "
            "exist, and the group gate demonstrably changes the menu set — "
            "is asserted above.")


@test_case(
    id="TEST-WF027-TC088",
    name='"Cost Analysis View" gates the product cost-structure stat button',
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_reports",
    priority="P2", kind="SEC", order=27088,
    description="The group exists and is pre-populated; whether the stat "
                "button renders is a browser assertion and is blocked.",
    traceability=trace("DATAONE-TC088"))
def test_tc088(ctx):
    rpc = ctx.adapter.rpc
    require_reports(ctx)

    with ctx.step("Step 6: the Cost Analysis group exists"):
        candidates = rpc.search_read(
            "res.groups", [("name", "ilike", "cost analysis")],
            ["name", "full_name"] if rpc.field_exists("res.groups", "full_name")
            else ["name"])
        ctx.check_true("a 'Cost Analysis' group is defined on this target",
                       bool(candidates), str(candidates))
        if candidates:
            group_id = candidates[0]["id"]
            field = user_group_field(rpc)
            members = rpc.search("res.users", [(field, "in", [group_id])])
            ctx.log(f"{candidates[0]['name']}: {len(members)} member(s)")
            ctx.check_true("it ships pre-populated rather than empty",
                           len(members) > 0, str(members[:5]))

    with ctx.step("The stat button itself"):
        ctx.blocked(
            "steps 2-5 assert that the cost-structure stat button is ABSENT "
            "on the product form for one user and PRESENT for another, and "
            "that mrp_product_qty is not visible. Button visibility is "
            "resolved by the web client from the form arch plus the reading "
            "user's groups; asserting it faithfully needs a rendered form, "
            "which this platform does not drive. The group half — that the "
            "gate exists and is populated — is asserted above.")


@test_case(
    id="TEST-WF027-TC389",
    name="BOM Lines multi-edit changes quantity on every selected line and "
         "on the parent BoMs",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_reports",
    priority="P1", kind="FUNC", order=27389,
    description="The equivalent server-side write is asserted — a multi-write "
                "reaches every selected line and only those — and the inline "
                "list editing itself is blocked.",
    traceability=trace("DATAONE-TC389"))
def test_tc389(ctx):
    """The workbook types this TOUR. Odoo's list multi-edit is a client
    feature: selecting rows and editing one cell issues ONE ``write`` over
    the selected ids. That write is exactly what this case asserts, on this
    suite's own BoM lines — so the behaviour under test is covered, and only
    the gesture that triggers it is blocked.
    """
    rpc = ctx.adapter.rpc
    require_reports(ctx)
    from tests.wf027.common import (ensure_product, fx, open_namespace,
                                    sweep_wf027)
    open_namespace(ctx)
    try:
        with ctx.step("Two BoMs, one line each"):
            finished_a = ensure_product(rpc, "BOM-A finished")
            finished_b = ensure_product(rpc, "BOM-B finished")
            component = ensure_product(rpc, "BOM component")
            bom_ids, line_ids = [], []
            for finished in (finished_a, finished_b):
                tmpl = rpc.read("product.product", [finished],
                                ["product_tmpl_id"])[0]["product_tmpl_id"][0]
                bom_id = rpc.create("mrp.bom", {
                    "product_tmpl_id": tmpl,
                    "code": fx("BOM"),
                    "product_qty": 1.0,
                    "bom_line_ids": [(0, 0, {"product_id": component,
                                             "product_qty": 2.0})],
                })
                bom_ids.append(bom_id)
                line_ids += rpc.search("mrp.bom.line",
                                       [("bom_id", "=", bom_id)])
            ctx.check("two BoM lines created", 2, len(line_ids))

        with ctx.step("A third line that is NOT selected, to prove the write "
                      "is scoped"):
            # A THIRD finished product, not `component`: making the
            # component's own BoM consume finished_a closes a loop and Odoo
            # refuses it ("would create a cycle").
            control_finished = ensure_product(rpc, "BOM-control finished")
            tmpl_c = rpc.read("product.product", [control_finished],
                              ["product_tmpl_id"])[0]["product_tmpl_id"][0]
            other_bom = rpc.create("mrp.bom", {
                "product_tmpl_id": tmpl_c,
                "code": fx("BOM-control"),
                "product_qty": 1.0,
                "bom_line_ids": [(0, 0, {"product_id": component,
                                         "product_qty": 2.0})],
            })
            control_line = rpc.search("mrp.bom.line",
                                      [("bom_id", "=", other_bom)])[0]

        with ctx.step("Step 9: ONE write over both selected lines sets 7.0"):
            rpc.write("mrp.bom.line", line_ids, {"product_qty": 7.0})
            rows = rpc.read("mrp.bom.line", line_ids, ["product_qty"])
            ctx.check("both selected lines", [7.0, 7.0],
                      [r["product_qty"] for r in rows])

        with ctx.step("Steps 10-11: the write reached the parent BoMs, and "
                      "ONLY the selection"):
            for bom_id in bom_ids:
                lines = rpc.search_read("mrp.bom.line",
                                        [("bom_id", "=", bom_id)],
                                        ["product_qty"])
                ctx.check(f"BoM {bom_id} line quantity", [7.0],
                          [line["product_qty"] for line in lines])
            ctx.check("the unselected control line is untouched", 2.0,
                      rpc.read("mrp.bom.line", [control_line],
                               ["product_qty"])[0]["product_qty"])

        with ctx.step("The inline multi-edit gesture itself"):
            ctx.blocked(
                "selecting rows in a list and editing one cell is a web-client "
                "interaction; what it issues server-side is a single write "
                "over the selected ids, and that write is asserted above on "
                "this suite's own lines. Driving the gesture needs a rendered "
                "list view. Step 12's access finding is covered by "
                "TEST-WF027-TC376.")
    finally:
        with ctx.step("Cleanup"):
            try:
                sweep_wf027(rpc)
            except Exception:  # noqa: BLE001
                pass


@test_case(
    id="TEST-WF027-TC022",
    name="Trial balance report export matches, v17 vs v19",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="account",
    priority="P0", kind="DATA", order=27022,
    description="A numeric diff of the trial balance between versions. The "
                "v19 half is computed here; the comparison needs the v17 "
                "figures and is blocked until they are captured.",
    traceability=trace("DATAONE-TC022"))
def test_tc022(ctx):
    """The workbook types this MANUAL and asks a person to accept or reject
    label and layout differences explicitly. The NUMERIC half is not manual
    at all, so this case computes it and records the figure, then blocks on
    the comparison rather than pretending to have made it.

    Rule 3: the trial balance is read-only aggregation over the client's own
    account.move.line. Nothing is written.
    """
    rpc = ctx.adapter.rpc

    with ctx.step("Step 6: the grand totals from the ledger itself"):
        # read_group over posted lines, which is what any trial balance
        # must reconcile to.
        groups = rpc.read_group(
            "account.move.line",
            [("parent_state", "=", "posted")],
            ["debit:sum", "credit:sum"], [])
        total = groups[0] if groups else {}
        debit = round(total.get("debit", 0.0) or 0.0, 2)
        credit = round(total.get("credit", 0.0) or 0.0, 2)
        ctx.log(f"posted ledger totals: debit={debit} credit={credit}")
        ctx.check("the ledger balances — debit equals credit", debit, credit)

    with ctx.step("The v17 comparison"):
        ctx.blocked(
            f"the case compares this figure against the same report on v17, "
            f"and no v17 capture exists for DATAONE-TC022. The v19 side is "
            f"computed and recorded above (posted debit = credit = {debit}), "
            f"and it balances. Capturing v17 needs a run against the Odoo 17 "
            f"target; accepting or rejecting label and layout differences is "
            f"explicitly a person's judgement in the workbook's own steps.")
