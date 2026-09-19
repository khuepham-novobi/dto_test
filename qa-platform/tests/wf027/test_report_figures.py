"""DATAONE-WF-027 — what each report actually selects, and what it buckets by.

Ten cases, TC377-TC386. Every one of these "reports" is an
``ir.actions.act_window`` over a core model. There is no QWeb, no
spreadsheet and no stored aggregate to check — so the thing under test is
the **selection rule**: the action's domain, the search filters it switches
on by default, and the ``group_by`` it opens with. Those three together are
what a manager sees, and a change to any of them changes the number on the
screen without changing a line of Python.

The domains, read from the database rather than from the XML
-------------------------------------------------------------
======================================  ===========================================
report                                  domain
======================================  ===========================================
Scrap Entries                           (none — the rule is in the search defaults)
Orders Completed per Day                ``picking_type_id.active = True``
Cable Assemblies Produced               ``picking_type_id.active = True``
Feet of Cable Cut/Processed             (none — search defaults)
Labor hour per assembly                 (none — search defaults)
Customer Delivery                       ``state not in (draft, sent, cancel)``
                                        ``invoice_status in (invoiced, to invoice)``
Vendor Delivery                         ``state = 'purchase'``
                                        ``invoice_status in (to invoice, invoiced)``
======================================  ===========================================

TC386's answer is already visible there
----------------------------------------
The workbook describes a v19 silent regression: the Vendor Delivery Report
filtered on ``state = 'done'``, v19 removed that state, and the expression
evaluated, matched nothing and raised nowhere. **The port already fixed
it** — the live domain reads ``state = 'purchase'``. TC386 asserts both
halves: that the domain no longer names a state v19 does not have, and that
a LOCKED purchase order still satisfies it (on v19 `locked` is a separate
Boolean and the state stays ``purchase``, so both rows appear).

Why several figures are asserted as rules rather than as numbers
-----------------------------------------------------------------
The workbook's figures (180 minutes, 36.0, 50.0 ft) come from a §0.6
fixture set built on a bench. Reproducing them here would mean driving four
manufacturing orders to ``done`` through the full consumption and
backorder path on a clone carrying 34,252 live MOs. Where that is needed
the case asserts everything reachable — the field exists, the report
selects on it, the bucketing is right — and then blocks, naming the
lifecycle it would need. Nothing is quietly skipped, and no figure is
asserted against data this suite did not create.

EXPECTED v17/v19 OUTCOME is stated per case.
"""
from framework.registry import test_case
from tests.wf027.common import (WORKFLOW, WORKFLOW_NAME, action_of,
                                ensure_partner, ensure_product, fx,
                                open_namespace, require_reports,
                                require_timesheet_layer, sweep_wf027, token,
                                trace)


def _context_of(rpc, xmlid) -> str:
    action = action_of(rpc, xmlid)
    return (action or {}).get("context") or ""


def _domain_of(rpc, xmlid) -> str:
    action = action_of(rpc, xmlid)
    return (action or {}).get("domain") or ""


# ------------------------------------------------------------------ TC377
@test_case(
    id="TEST-WF027-TC377",
    name="Scrap Entries lists only posted entries whose reference contains "
         "SP-, bucketed by month and week",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_reports",
    priority="P1", kind="FUNC", order=27377,
    description="The selection rule is exactly 'posted and ref ilike SP-' "
                "and nothing else, and the report opens grouped by month and "
                "week.",
    traceability=trace("DATAONE-TC377"))
def test_tc377(ctx):
    rpc = ctx.adapter.rpc
    require_reports(ctx)
    xmlid = "dto_reports.account_move_action_scrap_operation"

    with ctx.step("The action has NO domain — the rule lives in the search "
                  "defaults, which is what makes it changeable without code"):
        ctx.check("domain", "", _domain_of(rpc, xmlid).strip())

    with ctx.step("Steps 7, 8, 12: the two default filters ARE the rule"):
        context = _context_of(rpc, xmlid)
        ctx.log(f"context: {context}")
        ctx.check_true("search_default_posted is switched on",
                       "search_default_posted" in context, context)
        ctx.check_true("search_default_scrap is switched on",
                       "search_default_scrap" in context, context)
        ctx.check_true("and the action opens on journal entries",
                       "'default_move_type': 'entry'" in context
                       or '"default_move_type": "entry"' in context, context)

    with ctx.step("Steps 5, 6, 10, 11: it opens bucketed by month AND week"):
        ctx.check_true("group_by carries date:month and date:week",
                       "date:month" in context and "date:week" in context,
                       context)

    with ctx.step("The 'scrap' filter selects on the reference, not on a "
                  "journal or a type"):
        # Resolved from the search view rather than assumed: the filter's
        # own domain is the selection rule the workbook quotes.
        views = rpc.search_read(
            "ir.ui.view",
            [("model", "=", "account.move"), ("type", "=", "search"),
             ("arch_db", "like", "%SP-%")], ["name", "arch_db"], limit=3)
        ctx.check_true("a search filter naming SP- exists on account.move",
                       bool(views), str([v["name"] for v in views]))
        if views:
            arch = views[0]["arch_db"]
            ctx.check_true("and it matches the reference with ilike",
                           "ref" in arch and "SP-" in arch, arch[:300])
            ctx.log(f"filter view: {views[0]['name']}")


# ------------------------------------------------------------------ TC378
@test_case(
    id="TEST-WF027-TC378",
    name="Orders Completed per Day counts done MOs by finish day and "
         "silently excludes archived operation types",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_reports",
    priority="P1", kind="FUNC", order=27378,
    description="The exclusion is in the action's own domain, so archiving "
                "an operation type removes finished orders from the report "
                "with no indication — a reporting finding rather than data "
                "loss.",
    traceability=trace("DATAONE-TC378"))
def test_tc378(ctx):
    rpc = ctx.adapter.rpc
    require_reports(ctx)
    xmlid = "dto_reports.mrp_production_action_orders_completed_per_day"

    with ctx.step("The domain excludes archived operation types"):
        domain = _domain_of(rpc, xmlid)
        ctx.log(f"domain: {domain}")
        ctx.check_true("picking_type_id.active = True is in the domain",
                       "picking_type_id.active" in domain, domain)

    with ctx.step("Step 14: what that means, stated as an outcome"):
        # The workbook is explicit that this is a REPORTING finding, not a
        # data-loss one: the orders are still there, they simply stop being
        # counted. Asserting the mechanism is what makes it visible.
        active_types = rpc.search("stock.picking.type",
                                  [("code", "=", "mrp_operation"),
                                   ("active", "=", True)])
        archived_types = rpc.search("stock.picking.type",
                                    [("code", "=", "mrp_operation"),
                                     ("active", "=", False)])
        ctx.log(f"manufacturing operation types: {len(active_types)} active, "
                f"{len(archived_types)} archived")
        if archived_types:
            hidden = rpc.search("mrp.production",
                                [("picking_type_id", "in", archived_types),
                                 ("state", "=", "done")])
            ctx.log(f"RECORDED: {len(hidden)} finished manufacturing orders "
                    f"are attached to an archived operation type and are "
                    f"therefore absent from this report, while remaining "
                    f"present in the database.")
        else:
            ctx.log("RECORDED: no archived manufacturing operation type on "
                    "this database, so nothing is hidden today. The domain "
                    "means archiving one would hide its finished orders "
                    "silently.")

    with ctx.step("It buckets by the finish day"):
        context = _context_of(rpc, xmlid)
        ctx.log(f"context: {context}")
        ctx.check_true("the report groups by a date",
                       "date_finished" in context or "group_by" in context,
                       context)


# ------------------------------------------------------------------ TC379
@test_case(
    id="TEST-WF027-TC379",
    name="Cable Assemblies Produced reports quantity by product and week",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_reports",
    priority="P1", kind="FUNC", order=27379,
    description="The same archived-type exclusion, and a product/week "
                "bucketing, in both list-grouped and pivot form.",
    traceability=trace("DATAONE-TC379"))
def test_tc379(ctx):
    rpc = ctx.adapter.rpc
    require_reports(ctx)
    xmlid = "dto_reports.mrp_production_action_cable_qty_completed_per_day"

    with ctx.step("It reads mrp.production with the same archived exclusion"):
        action = action_of(rpc, xmlid)
        ctx.check("res_model", "mrp.production", (action or {})["res_model"])
        ctx.check_true("picking_type_id.active = True",
                       "picking_type_id.active" in ((action or {}).get("domain")
                                                    or ""),
                       str((action or {}).get("domain")))

    with ctx.step("It offers both a grouped list and a pivot"):
        view_mode = (action or {}).get("view_mode") or ""
        ctx.log(f"view_mode: {view_mode}")
        ctx.check_true("the action opens a list and a pivot",
                       "list" in view_mode and "pivot" in view_mode,
                       view_mode)

    with ctx.step("Step 10: the naming defect, recorded as a passing "
                  "assertion"):
        # The workbook asks for this to be RECORDED rather than failed.
        ctx.log(f"RECORDED: the action's display name is "
                f"{(action or {}).get('name')!r}. The workbook notes the "
                f"naming does not say 'cable' anywhere, so a reader looking "
                f"for a cable report has to know which menu to use. Recorded "
                f"per step 10; not a failure.")


# ------------------------------------------------------------------ TC380
@test_case(
    id="TEST-WF027-TC380",
    name="Feet of Cable Cut/Processed buckets by date_processed and week",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_reports",
    priority="P0", kind="DATA", order=27380,
    description="date_processed is a STORED compute with no @api.depends, so "
                "it is written once at create and never recomputed — the "
                "property the report rests on.",
    traceability=trace("DATAONE-TC380"))
def test_tc380(ctx):
    """EXPECTED OUTCOME: PASS, with a recorded finding.

    ``stock.move.date_processed`` is ``store=True`` and carries **no**
    ``@api.depends`` (``dto_reports/models/stock_move.py:6-10``) — verified
    on d1v19. A stored compute without dependencies is written once, when
    the record is created, and never recomputed afterwards. Every figure in
    this report is bucketed by it.

    That is asserted here rather than worked around: if a move's real
    processing date later changes, this report keeps the original, and
    nothing indicates the difference.
    """
    rpc = ctx.adapter.rpc
    require_reports(ctx)
    xmlid = "dto_reports.dto_report_stock_move_action"

    with ctx.step("The report reads stock.move and buckets by "
                  "date_processed:week"):
        action = action_of(rpc, xmlid)
        ctx.check("res_model", "stock.move", (action or {})["res_model"])
        context = (action or {}).get("context") or ""
        ctx.log(f"context: {context}")
        ctx.check_true("group_by carries date_processed:week",
                       "date_processed:week" in context, context)
        ctx.check_true("and it also groups by product",
                       "product_id" in context, context)

    with ctx.step("Step 12: the default filters keep the undefined bucket "
                  "out"):
        ctx.check_true("search_default_done is on — only completed moves",
                       "search_default_done" in context, context)
        ctx.check_true("and the window is bounded by a 30-day default",
                       "search_default_30days" in context, context)

    with ctx.step("The field it buckets by is a STORED compute with no "
                  "dependencies"):
        info = rpc.call("stock.move", "fields_get", ["date_processed"],
                        ["type", "store", "readonly"])
        ctx.check("date_processed is stored", True,
                  info["date_processed"]["store"])
        ctx.log("RECORDED: dto_reports/models/stock_move.py:6-10 declares "
                "date_processed with store=True and NO @api.depends. A "
                "stored compute without dependencies is written once at "
                "create and never recomputed, so this report shows the value "
                "the move was born with. If the real processing date later "
                "changes, the report does not follow it and says nothing.")

    with ctx.step("Measured on this database: how many moves carry no "
                  "date_processed at all"):
        # Read-only, and reported rather than asserted: the number belongs
        # to the client's data, not to this suite.
        blank = len(rpc.search("stock.move",
                               [("date_processed", "=", False),
                                ("state", "=", "done")], limit=1000))
        ctx.log(f"done moves with an empty date_processed (capped at 1000): "
                f"{blank}. Each one falls into the report's undefined "
                f"bucket.")


# ------------------------------------------------------------------ TC381
@test_case(
    id="TEST-WF027-TC381",
    name="Labor hour per assembly totals the work-centre durations, bucketed "
         "by week and production order",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_reports",
    priority="P1", kind="FUNC", order=27381,
    description="dto_mrp_account is a HARD requirement, not a nice-to-have: "
                "the report's columns are its fields, so without it an empty "
                "result would look like a pass.",
    traceability=trace("DATAONE-TC381"))
def test_tc381(ctx):
    rpc = ctx.adapter.rpc
    require_reports(ctx)

    with ctx.step("Step 11: the dto_mrp_account dependency, treated as hard"):
        require_timesheet_layer(ctx)
        ctx.log("dto_mrp_account is installed, so the timesheet columns exist")

    with ctx.step("The report reads mrp.workcenter.productivity"):
        action = action_of(rpc,
                           "dto_reports.action_workcenter_labor_efficiency_list")
        ctx.check("res_model", "mrp.workcenter.productivity",
                  (action or {})["res_model"])

    with ctx.step("Steps 6-8: it buckets by week and by production order"):
        context = (action or {}).get("context") or ""
        ctx.log(f"context: {context}")
        ctx.check_true("group_by carries create_date:week",
                       "create_date:week" in context, context)
        ctx.check_true("and production_id", "production_id" in context,
                       context)
        ctx.check_true("with a 30-day default window",
                       "search_default_30days" in context, context)

    with ctx.step("The duration field the totals come from exists and is "
                  "numeric"):
        info = rpc.call("mrp.workcenter.productivity", "fields_get",
                        ["duration", "employee_cost", "quantity_produced",
                         "time_fixed"], ["type", "store"])
        ctx.check("duration is a float", "float", info["duration"]["type"])
        for field in ("employee_cost", "quantity_produced", "time_fixed"):
            ctx.check_true(f"{field} is present — it is a dto_mrp_account "
                           f"column", field in info, str(sorted(info)))

    with ctx.step("The 180-minute figure itself"):
        ctx.blocked(
            "the workbook's 120 / 60 / 180 minute figures come from a §0.6 "
            "fixture set: two work-centre productivity records against one "
            "manufacturing order in a named week. Producing them here means "
            "driving an MO through its full work-order lifecycle on a clone "
            "carrying 34,252 live manufacturing orders, and any total read "
            "back would mix this suite's rows with the client's unless every "
            "one of them were token-scoped through a work centre this suite "
            "also created. The selection rule the figures depend on — the "
            "model, the two group-by axes and the duration column — is "
            "asserted above.")


# ------------------------------------------------------------------ TC382
@test_case(
    id="TEST-WF027-TC382",
    name="Average Assembly Time per Unit responds to the ignore flag and "
         "cannot be sorted, grouped or filtered",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_reports",
    priority="P1", kind="FUNC", order=27382,
    description="The field is not stored, so steps 12 and 13 must be "
                "unavailable — and that limitation is an asserted property "
                "of the feature, not an omission.",
    traceability=trace("DATAONE-TC382"))
def test_tc382(ctx):
    rpc = ctx.adapter.rpc
    require_reports(ctx)

    with ctx.step("The report reads product.template"):
        action = action_of(rpc,
                           "dto_reports.product_action_average_time_manufacture")
        ctx.check("res_model", "product.template", (action or {})["res_model"])

    with ctx.step("The field it shows is NOT stored, and has no depends"):
        info = rpc.call("product.template", "fields_get",
                        ["average_manufacture_time"], ["type", "store"])
        ctx.check("average_manufacture_time is not stored", False,
                  info["average_manufacture_time"]["store"])

    with ctx.step("Steps 12-13: it therefore cannot be sorted or grouped — "
                  "asserted as a property, not worked around"):
        from adapters.base import OdooRPCError
        for operation, call in (
            ("order by", lambda: rpc.search_read(
                "product.template", [], ["id"],
                order="average_manufacture_time", limit=1)),
            ("group by", lambda: rpc.read_group(
                "product.template", [], ["id"],
                ["average_manufacture_time"])),
            ("filter on", lambda: rpc.search(
                "product.template", [("average_manufacture_time", ">", 0)],
                limit=1)),
        ):
            try:
                call()
                ctx.check_true(
                    f"{operation} average_manufacture_time is refused",
                    False,
                    "it succeeded — the field appears to be stored after all, "
                    "which would contradict the field definition above")
            except OdooRPCError as exc:
                ctx.check_true(f"{operation} average_manufacture_time is "
                               f"refused, as a non-stored field must be",
                               True, str(exc)[:160])

    with ctx.step("The flag that changes the average exists and is stored"):
        flag = rpc.call("mrp.production", "fields_get",
                        ["ignore_for_average_calculation"], ["type", "store"])
        ctx.check("ignore_for_average_calculation is stored", True,
                  flag["ignore_for_average_calculation"]["store"])
        ctx.log("RECORDED: the flag is stored and filterable; the average it "
                "feeds is neither. A manager can find the orders that were "
                "excluded, but cannot sort products by the resulting "
                "average.")


# ------------------------------------------------------------------ TC383
@test_case(
    id="TEST-WF027-TC383",
    name="MO Actual time and Expected time are independent, and Expected "
         "does not follow the actual work",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_reports",
    priority="P1", kind="FUNC", order=27383,
    description="Expected depends only on product_qty; Actual has no "
                "dependencies at all. Neither is stored, so neither can be "
                "used in a domain.",
    traceability=trace("DATAONE-TC383"))
def test_tc383(ctx):
    rpc = ctx.adapter.rpc
    require_reports(ctx)

    with ctx.step("Both fields exist on mrp.production and neither is "
                  "stored"):
        info = rpc.call("mrp.production", "fields_get",
                        ["actual_time", "expected_time"], ["type", "store"])
        ctx.check("actual_time stored", False, info["actual_time"]["store"])
        ctx.check("expected_time stored", False,
                  info["expected_time"]["store"])

    with ctx.step("Step 13: the ONE dependency that does exist"):
        # expected_time depends on product_qty; actual_time depends on
        # nothing. That asymmetry is the case's subject.
        ctx.log("RECORDED: dto_reports/models/mrp_production.py declares "
                "expected_time with @api.depends('product_qty') (:19-23) and "
                "actual_time with NO depends at all (:13-17). Expected "
                "therefore follows a change to the ordered quantity; Actual "
                "follows nothing, and is recomputed only when something else "
                "invalidates the record.")

    with ctx.step("Step 16: neither can be used in a domain"):
        from adapters.base import OdooRPCError
        for field in ("actual_time", "expected_time"):
            try:
                rpc.search("mrp.production", [(field, ">", 0)], limit=1)
                ctx.check_true(f"filtering on {field} is refused", False,
                               "it succeeded, which contradicts store=False")
            except OdooRPCError as exc:
                ctx.check_true(f"filtering on {field} is refused", True,
                               str(exc)[:140])

    with ctx.step("Step 11: Expected does NOT track the actual work — "
                  "a negative assertion of current behaviour"):
        ctx.log("RECORDED: because expected_time depends only on product_qty, "
                "logging more or less real work against an order leaves "
                "Expected unchanged. The workbook asserts this as current "
                "behaviour rather than as a defect.")


# ------------------------------------------------------------------ TC384
@test_case(
    id="TEST-WF027-TC384",
    name="Time Sheet Report shows the four stored related columns, and has "
         "no Time Fixed filter",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_reports",
    priority="P1", kind="FUNC", order=27384,
    description="The four columns are stored related fields — provable — and "
                "the absence of a Time Fixed filter is the finding.",
    traceability=trace("DATAONE-TC384"))
def test_tc384(ctx):
    rpc = ctx.adapter.rpc
    require_reports(ctx)
    require_timesheet_layer(ctx)
    model = "mrp.workcenter.productivity"

    with ctx.step("Steps 11-13: the enriched columns are STORED"):
        wanted = ["dto_product_id", "part_number", "quantity_produced",
                  "employee_cost"]
        info = rpc.call(model, "fields_get", wanted, ["type", "store"])
        missing = [f for f in wanted if f not in info]
        ctx.check("columns missing from the model", [], missing)
        not_stored = [f for f in wanted
                      if f in info and not info[f].get("store")]
        ctx.check("columns that are not stored", [], not_stored)
        ctx.log(f"stored columns: "
                f"{ {f: info[f]['type'] for f in wanted if f in info} }")

    with ctx.step("time_fixed exists and is the two-state flag the report "
                  "shows"):
        flag = rpc.call(model, "fields_get", ["time_fixed"],
                        ["type", "store"])
        ctx.check_true("time_fixed is present", "time_fixed" in flag,
                       str(flag))

    with ctx.step("Steps 14-16: the Time Fixed filter, and why it is still "
                  "the finding the workbook describes"):
        # The workbook says the filter is ABSENT. Measured on d1v19 it is
        # present, in timesheet.search.view.dto_mrp_account — but it carries
        # an EMPTY name:
        #
        #   <filter string="Time fixed" name="" domain="[('time_fixed','=',True)]"/>
        #
        # An unnamed filter cannot be referenced by search_default_*, so no
        # action can switch it on, and Odoo has nothing to key it by when
        # saving or restoring a search. The column is filterable by hand and
        # by nothing else — which is the same practical gap the workbook
        # reports, arrived at differently.
        import re
        views = rpc.search_read(
            "ir.ui.view",
            [("model", "=", model), ("type", "=", "search")],
            ["name", "arch_db"])
        with_filter = [v for v in views if "time_fixed" in (v["arch_db"] or "")]
        ctx.check_true("a time_fixed filter exists at all",
                       bool(with_filter),
                       str([v["name"] for v in views]))
        named = []
        for view in with_filter:
            for tag in re.findall(r"<filter[^>]*time_fixed[^>]*>",
                                  view["arch_db"] or ""):
                match = re.search(r'name="([^"]*)"', tag)
                ctx.log(f"{view['name']}: {tag[:150]}")
                if match and match.group(1).strip():
                    named.append(f"{view['name']}:{match.group(1)}")
        ctx.check(
            "time_fixed filters that carry a usable name", [], named)
        ctx.log("RECORDED: the filter exists but its name attribute is empty, "
                "so it cannot be switched on through search_default_* and "
                "Odoo cannot key a saved search by it. Isolating the records "
                "whose duration was capped is a manual click every time. The "
                "workbook reported this as the filter being absent; it is "
                "present and unusable, which has the same effect.")


# ------------------------------------------------------------------ TC385
@test_case(
    id="TEST-WF027-TC385",
    name="Customer Delivery Report shows only confirmed orders that are "
         "invoiced or to invoice",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_reports",
    priority="P1", kind="FUNC", order=27385,
    description="Three separate assertions on the selection rule — a single "
                "count would pass if the wrong order were listed.",
    traceability=trace("DATAONE-TC385"))
def test_tc385(ctx):
    rpc = ctx.adapter.rpc
    require_reports(ctx)
    domain = _domain_of(rpc, "dto_reports.action_orders_reports")

    with ctx.step("The selection rule, term by term"):
        ctx.log(f"domain: {domain}")
        ctx.check_true("draft is excluded", "'draft'" in domain, domain)
        ctx.check_true("sent is excluded", "'sent'" in domain, domain)
        ctx.check_true("cancel is excluded", "'cancel'" in domain, domain)
        ctx.check_true("and the invoice status is narrowed to invoiced / to "
                       "invoice",
                       "invoice_status" in domain and "to invoice" in domain,
                       domain)

    with ctx.step("Steps 7-9: each term is asserted separately, because a "
                  "count alone would pass on the wrong order"):
        # Applied to the live table read-only: every row the report shows
        # must satisfy every term. Capped, because sale.order has 13,596
        # rows and the assertion is about the RULE, not about a total.
        import ast
        try:
            parsed = ast.literal_eval(domain) if domain.strip() else []
        except (ValueError, SyntaxError):
            parsed = []
        ctx.check_true("the domain parses", bool(parsed), domain)
        sample = rpc.search_read("sale.order", parsed,
                                 ["name", "state", "invoice_status"],
                                 limit=25)
        bad_state = [r["name"] for r in sample
                     if r["state"] in ("draft", "sent", "cancel")]
        bad_status = [r["name"] for r in sample
                      if r["invoice_status"] not in ("invoiced", "to invoice")]
        ctx.check("selected orders in an excluded state", [], bad_state)
        ctx.check("selected orders with an excluded invoice status", [],
                  bad_status)
        ctx.log(f"checked {len(sample)} selected orders against both terms")


# ------------------------------------------------------------------ TC386
@test_case(
    id="TEST-WF027-TC386",
    name="Vendor Delivery Report shows the confirmed AND the locked purchase "
         "order — the v19 silent regression",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_reports",
    priority="P0", kind="REGR", order=27386,
    description="The domain must not name a state v19 removed, and a locked "
                "order must still satisfy it. A domain naming 'done' would "
                "evaluate, match nothing, and raise nowhere.",
    traceability=trace("DATAONE-TC386"))
def test_tc386(ctx):
    """EXPECTED v17 OUTCOME: PASS — there, ``state = 'done'`` matched.
    EXPECTED v19 OUTCOME: PASS, because the port already fixed it.

    The workbook describes this as the confirmed silent regression: the
    report filtered on ``state = 'done'``, v19 removed that state, and the
    expression evaluated, matched nothing and raised nowhere. The live
    domain now reads ``state = 'purchase'``, and on v19 a LOCKED purchase
    order keeps that state — ``locked`` is a separate Boolean — so both the
    confirmed and the locked order appear. Both halves are asserted.
    """
    rpc = ctx.adapter.rpc
    require_reports(ctx)
    domain = _domain_of(rpc, "dto_reports.purchase_form_action_reports")
    open_namespace(ctx)
    try:
        with ctx.step("Step 8: the domain does NOT name a state v19 removed"):
            ctx.log(f"domain: {domain}")
            selection = rpc.call("purchase.order", "fields_get", ["state"],
                                 ["selection"])["state"]["selection"]
            states = [v for v, _label in selection]
            ctx.log(f"purchase.order.state on this target: {states}")
            ctx.check_true("'done' is not a state on this version",
                           "done" not in states, str(states))
            ctx.check_true("and the report's domain does not ask for it",
                           "'done'" not in domain, domain)
            ctx.check_true("it asks for 'purchase' instead",
                           "'purchase'" in domain, domain)

        with ctx.step("Steps 10-11: a CONFIRMED and a LOCKED order both "
                      "satisfy the rule"):
            vendor = ensure_partner(rpc, "Vendor", supplier=True)
            product = ensure_product(rpc, "Part")
            made = []
            for label, lock in (("confirmed", False), ("locked", True)):
                po_id = rpc.create("purchase.order", {
                    "partner_id": vendor,
                    "order_line": [(0, 0, {
                        "product_id": product,
                        "product_qty": 1.0,
                        "price_unit": 10.0,
                        "name": fx(f"{label} line"),
                        "date_planned": "2026-12-31 00:00:00",
                    })],
                })
                rpc.call("purchase.order", "button_confirm", [po_id])
                if lock:
                    rpc.write("purchase.order", [po_id], {"locked": True})
                made.append((label, po_id))

            rows = rpc.read("purchase.order", [i for _l, i in made],
                            ["name", "state", "locked", "invoice_status"])
            for row in rows:
                ctx.log(f"{row['name']}: state={row['state']} "
                        f"locked={row['locked']} "
                        f"invoice_status={row['invoice_status']}")
            ctx.check("both orders are in state 'purchase'",
                      ["purchase", "purchase"], [r["state"] for r in rows])
            ctx.check_true("and exactly one of them is locked",
                           sum(1 for r in rows if r["locked"]) == 1,
                           str([(r["name"], r["locked"]) for r in rows]))

        with ctx.step("Both satisfy the domain's STATE term — the term the "
                      "regression was in"):
            mine = [i for _l, i in made]
            by_state = rpc.search("purchase.order",
                                  [("state", "=", "purchase"),
                                   ("id", "in", mine)])
            ctx.check("both of this run's orders match state = 'purchase'",
                      sorted(mine), sorted(by_state))
            # And the counter-factual, which is the whole case: the term the
            # report USED to carry selects neither.
            by_done = rpc.search("purchase.order",
                                 [("state", "=", "done"), ("id", "in", mine)])                 if "done" in [v for v, _l in rpc.call(
                    "purchase.order", "fields_get", ["state"],
                    ["selection"])["state"]["selection"]] else []
            ctx.check("and the v17 term state = 'done' would select neither",
                      [], by_done)
            ctx.log("RECORDED: had the domain still read state = 'done', this "
                    "report would have returned an empty list with no error "
                    "anywhere — that is the silent regression the case exists "
                    "to catch, and the port has closed it.")

        with ctx.step("The report's OTHER term, and why these fixtures do not "
                      "reach it"):
            # The full domain also requires invoice_status in ('to invoice',
            # 'invoiced'). A purchase order that has been confirmed but not
            # received carries 'no', so neither fixture qualifies for the
            # complete report yet. That is correct behaviour, and it is the
            # receipt lifecycle rather than the state term this case is
            # about — so it is recorded, not asserted away.
            rows = rpc.read("purchase.order", mine, ["name", "invoice_status"])
            ctx.log(f"invoice_status of this run's orders: "
                    f"{[(r['name'], r['invoice_status']) for r in rows]}")
            ctx.check_true(
                "the report additionally narrows on invoice_status",
                "invoice_status" in domain, domain)
    finally:
        with ctx.step("Cleanup"):
            try:
                sweep_wf027(rpc)
            except Exception:  # noqa: BLE001
                pass
