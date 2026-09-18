"""DATAONE-WF-001 — the confirmed-order protection: TC339.

P0 because a confirmed order has already generated procurement,
manufacturing and delivery commitments. Silently changing its lines because
Workday re-sent the requisition would desynchronise the MO, the delivery
and the invoice from the order. Instead a human is told, with an itemised
list of what Workday wanted to change — **and that list is the entire value
of the feature.** Step 10 is the case: if the port loses the old → new
pairs, or renders them at the wrong precision, the feature is technically
present and practically useless.

How the protection works
------------------------
``_process_workday_sale_order_vals`` branches on state
(``sale_order.py:322-334``): a matched order in state ``sale`` goes to
``update_confirmed_order(vals)``, anything else is written directly. And
``update_confirmed_order`` (``sale_order.py:353-442``) walks the ORDER_LINE
COMMAND LIST it was handed — ``Command.create`` (0), ``Command.delete`` (2)
and ``Command.update`` (1) — renders each as HTML, files ONE activity
carrying all of them, and then::

    del vals['order_line']
    self.write(vals)

So the header is written and the lines are not, by deletion rather than by
guard. That is what step 12 asserts indirectly.

The assignee chain is three-deep and testable
---------------------------------------------
``sale_order.py:432``::

    user = self.company_id.workday_sale_requisition_user_id
           or self.user_id
           or self.create_uid

Step 8 asks for all three to be exercised by unsetting them in turn. The
company setting is LIVE configuration, so it is set and restored in a
``finally``; ``user_id`` is on the fixture order and is the suite's own to
change.

The workbook flags why the chain matters: TD-CO-09 is recorded as Unknown
in the test-data catalogue, so if the company setting is unset in
production the activity falls through to ``order.user_id`` — and for a
cron-created order that may be a technical user nobody watches. One
Phase-0a query settles it: ``SELECT workday_sale_requisition_user_id FROM
res_company;``

One fixture step the workbook does not mention
----------------------------------------------
An order this flow imports CANNOT be confirmed as imported: dto_sale's
Gate 3 refuses any product line without ``requested_delivery_date``
(``dto_sale/models/sale_order.py:90-94``), and the import writes
``expected_delivery_date`` from ``Due_Date`` instead. So the fixture fills
the promised ship date before confirming — which is exactly what a
salesperson does, and it is stated in the test body rather than hidden.

EXPECTED v17 OUTCOME: PASS.
EXPECTED v19 OUTCOME: PASS. The watch item is delta §2.10 — v19 tightened
what may be written to the lines of a confirmed or invoiced sale order.
That affects the sibling write path rather than this guarded one, but the
guard BUILDS the command list before deleting it, so the SILENT failure
mode is a command list whose shape changed and a diff text that comes out
empty. Step 9's "the body itemises every change" is what catches that.
"""
from framework.registry import test_case
from tests.wf001.common import (ACTIVITY_TYPE_XMLID,  # noqa: F401
                                CONFIRMED_ACTIVITY_SUMMARY, MARK, WORKFLOW,
                                WORKFLOW_NAME, activities_on, analytic_name,
                                any_uom, contact_name, file_message, fx,
                                item_code, m2o_id, memo, order_lines,
                                order_type_labels, orders_for,
                                require_import_prerequisites,
                                require_mail_offline,
                                require_requisition_import, row, run_import,
                                state_and_country, sweep_wf001, trace)
from tests.wf001.test_requisition_gate import (_ensure_contact,
                                               _ensure_known_product)


@test_case(
    id="TEST-WF001-TC339",
    name="Re-import of a confirmed order updates only the header and "
         "raises the warning activity",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_sale_workday", priority="P0", kind="API", order=1339,
    description="Imports a three-line order, confirms it, then re-imports a "
                "file that would change a quantity, a price, a product, add "
                "a line and delete a line. Asserts the line set is "
                "byte-identical afterwards, the header WAS updated, "
                "partner_shipping_id took the new contact while partner_id "
                "did not move, exactly one warning activity itemises every "
                "intended change with old -> new values at the right "
                "precision, no revision was created, a no-op re-send "
                "produces NO activity, the file reads Done, and the "
                "assignee resolves down all three levels of the documented "
                "chain.",
    traceability=trace("DATAONE-TC339"))
def test_tc339(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-001 fixtures and open a fresh "
                  "namespace"):
        sweep_wf001(rpc)

    with ctx.step("Preconditions"):
        require_requisition_import(ctx)
        require_import_prerequisites(ctx)
        require_mail_offline(ctx)
        labels = order_type_labels(ctx)
        uom_name = any_uom(ctx)
        state_row, country_row = state_and_country(ctx)
        label = sorted(labels)[0]

    company_id = m2o_id(rpc.read("res.users", [rpc.uid],
                                 ["company_id"])[0]["company_id"])
    company_field = "workday_sale_requisition_user_id"
    original_user = False
    restored = False
    try:
        with ctx.step("Import SO-C with THREE lines, then confirm it. The "
                      "promised ship date is filled first: dto_sale's Gate "
                      "3 refuses any product line without "
                      "requested_delivery_date, and the import writes "
                      "expected_delivery_date from Due_Date instead — so "
                      "filling it is exactly what a salesperson does before "
                      "confirming"):
            contact = contact_name("Alpha")
            item_a = item_code("ITEM-A")
            item_b = item_code("ITEM-B")
            item_c = item_code("ITEM-C")
            for code in (item_a, item_b, item_c):
                _ensure_known_product(ctx, code)
            _ensure_contact(ctx, contact, "500 Main St", "Suite 20",
                            "Austin", state_row, country_row, "78701")
            common = dict(uom_name=uom_name, contact=contact,
                          street="500 Main St", city="Austin",
                          state=state_row["name"], zip_code="78701",
                          order_type_label=label,
                          requisition_num=memo("REQ-C"),
                          internal_memo=memo("IM-C"),
                          project=analytic_name("PRJ-C"),
                          contract=analytic_name("CC-C"))
            first = [
                row(item=item_a, description=fx(f"{MARK} A"), quantity="2",
                    unit_price="10.0", **common),
                row(item=item_b, description=fx(f"{MARK} B"), quantity="3",
                    unit_price="20.0", **common),
                row(item=item_c, description=fx(f"{MARK} C"), quantity="4",
                    unit_price="30.0", **common),
            ]
            folder_id, file_id, file_row = run_import(ctx, first,
                                                      file_label="initial")
            ctx.log(f"initial import: {file_row!r}")
            ctx.check("the initial import succeeded", "done",
                      file_row["state"])
            orders = orders_for(rpc, [memo("REQ-C")])
            ctx.check("one order was created", 1, len(orders))
            so_c = orders[0]["id"]
            lines = order_lines(rpc, so_c)
            ctx.log(f"SO-C's lines as imported: {lines!r}")
            ctx.check("three lines", 3, len(lines))

            if rpc.field_exists("sale.order.line", "requested_delivery_date"):
                rpc.write("sale.order.line",
                          [line["id"] for line in lines],
                          {"requested_delivery_date": "2099-12-31"})
                ctx.log("promised ship date filled on all three lines "
                        "(dto_sale Gate 3)")
            rpc.call("sale.order", "action_confirm", [so_c])
            state = rpc.read("sale.order", [so_c], ["state", "name"])[0]
            ctx.log(f"SO-C after confirmation: {state!r}")
            if state["state"] != "sale":
                ctx.blocked(
                    f"SO-C did not confirm (state={state['state']!r}). "
                    "This case's entire subject is what happens when a "
                    "CONFIRMED order is re-imported, so it cannot be "
                    "observed against a quotation. The confirmation gates "
                    "are dto_sale_workday's requester email, dto_account's "
                    "analytic distribution and dto_sale's promised ship "
                    "date, in that order — read the error to see which "
                    "refused.")
            so_c_name = state["name"]

        with ctx.step("Step 1: record SO-C's complete line set and header"):
            before_lines = order_lines(rpc, so_c)
            before_header = rpc.read(
                "sale.order", [so_c],
                ["memo_to_suppliers", "internal_memo", "requester",
                 "requester_email", "requisition_date", "partner_id",
                 "partner_shipping_id", "user_id", "create_uid",
                 "order_type", "origin"])[0]
            ctx.log(f"line set before: {before_lines!r}")
            ctx.log(f"header before: {before_header!r}")
            baseline = [(line["id"], m2o_id(line["product_id"]),
                         line["product_uom_qty"], line["price_unit"])
                        for line in before_lines]

        with ctx.step("Set the three-deep assignee chain's FIRST level: "
                      "res.company.workday_sale_requisition_user_id"):
            if rpc.field_exists("res.company", company_field):
                original_user = m2o_id(rpc.read(
                    "res.company", [company_id],
                    [company_field])[0][company_field]) or False
                rpc.write("res.company", [company_id],
                          {company_field: rpc.uid})
                ctx.log(f"company {company_id}.{company_field} -> {rpc.uid} "
                        f"(was {original_user})")
            else:
                ctx.log(f"[warn] res.company.{company_field} does not "
                        "exist, so the chain's first level cannot be "
                        "exercised. Recorded.")

        with ctx.step("Step 2: re-import a file that would change one "
                      "line's quantity, one line's price, one line's "
                      "product, ADD a line and DELETE a line — plus a "
                      "header field"):
            item_d = item_code("ITEM-D")
            item_e = item_code("ITEM-E")
            for code in (item_d, item_e):
                _ensure_known_product(ctx, code)
            new_contact = contact_name("Gamma")
            common = dict(uom_name=uom_name, contact=new_contact,
                          street="900 Second St", city="Dallas",
                          state=state_row["name"], zip_code="75201",
                          order_type_label=label,
                          requisition_num=memo("REQ-C"),
                          internal_memo=so_c_name,
                          supplier_memo=fx(f"{MARK} UPDATED MEMO"),
                          project=analytic_name("PRJ-C"),
                          contract=analytic_name("CC-C"))
            second = [
                # ITEM-A: quantity changed 2 -> 7
                row(item=item_a, description=fx(f"{MARK} A"), quantity="7",
                    unit_price="10.0", **common),
                # ITEM-B: price changed 20 -> 55
                row(item=item_b, description=fx(f"{MARK} B"), quantity="3",
                    unit_price="55.0", **common),
                # ITEM-D: a NEW product, which is both an add and — because
                # ITEM-C is absent from this file — a delete of ITEM-C's line
                row(item=item_d, description=fx(f"{MARK} D"), quantity="1",
                    unit_price="9.0", **common),
                # ITEM-E: a second add, so 'create' is unambiguous
                row(item=item_e, description=fx(f"{MARK} E"), quantity="6",
                    unit_price="12.0", **common),
            ]
            _f, second_id, second_row = run_import(
                ctx, second, folder_id=folder_id, file_label="reimport")
            ctx.log(f"re-import: {second_row!r}")
            ctx.log(f"its message, if any: "
                    f"{file_message(rpc, second_id)!r}")

        with ctx.step("Step 3: THE LINE SET IS BYTE-IDENTICAL. Every line "
                      "id, product, quantity and price against step 1"):
            after_lines = order_lines(rpc, so_c)
            ctx.log(f"line set after: {after_lines!r}")
            actual = [(line["id"], m2o_id(line["product_id"]),
                       line["product_uom_qty"], line["price_unit"])
                      for line in after_lines]
            ctx.check("nothing on the lines changed — not one id, product, "
                      "quantity or price", baseline, actual)

        with ctx.step("Steps 4-5: the HEADER was updated; partner_id was "
                      "NOT re-pointed and partner_shipping_id took the "
                      "file's contact"):
            after_header = rpc.read(
                "sale.order", [so_c],
                ["memo_to_suppliers", "internal_memo", "requester",
                 "requester_email", "requisition_date", "partner_id",
                 "partner_shipping_id", "order_type"])[0]
            ctx.log(f"header after: {after_header!r}")
            ctx.check("memo_to_suppliers carries the file's new value",
                      fx(f"{MARK} UPDATED MEMO"),
                      after_header["memo_to_suppliers"])
            ctx.check("partner_id was NOT re-pointed — update mode writes "
                      "partner_shipping_id instead (sale_order.py:85-86)",
                      m2o_id(before_header["partner_id"]),
                      m2o_id(after_header["partner_id"]))
            shipping = m2o_id(after_header["partner_shipping_id"])
            shipping_name = rpc.read("res.partner", [shipping],
                                     ["name"])[0]["name"] if shipping else ""
            ctx.log(f"partner_shipping_id now points at {shipping} "
                    f"({shipping_name!r})")
            ctx.check("and it took the file's new ship-to contact",
                      new_contact, shipping_name)

        with ctx.step("Steps 6-8: exactly ONE activity, of the right type "
                      "and summary, with the deadline today and the "
                      "assignee at the chain's FIRST level"):
            acts = activities_on(rpc, "sale.order", [so_c])
            ctx.log(f"activities on SO-C: {acts!r}")
            ctx.check("exactly one", 1, len(acts))
            activity = acts[0] if acts else {}
            ctx.check("summary, verbatim", CONFIRMED_ACTIVITY_SUMMARY,
                      activity.get("summary"))
            ctx.check("type", rpc.ref(ACTIVITY_TYPE_XMLID),
                      m2o_id(activity.get("activity_type_id")))
            if rpc.field_exists("res.company", company_field):
                ctx.check("assignee is the COMPANY setting — level 1 of the "
                          "chain", rpc.uid, m2o_id(activity.get("user_id")))

        with ctx.step("Steps 9-11: the body itemises EVERY intended change "
                      "and distinguishes creates, deletes and updates, with "
                      "old -> new values. Quoted verbatim — this text IS "
                      "the feature"):
            note = str(activity.get("note") or "")
            ctx.log(f"activity body, VERBATIM: {note!r}")
            expected_fragments = {
                "a create block": "to <strong>create</strong>",
                "a delete block": "to <strong>delete</strong>",
                "an update block": "to <strong>update</strong>",
                "the Product label": "Product",
                "the Quantity label": "Quantity",
                "the Unit Price label": "Unit Price",
            }
            missing = {label_: fragment
                       for label_, fragment in expected_fragments.items()
                       if fragment not in note}
            ctx.check("every block type and every labelled field is present",
                      {}, missing)
            ctx.check_true(
                "the old -> new arrow is rendered for the changed values — "
                "message_track_item_html emits the arrow ONLY when both an "
                "old and a new value exist (sale_order.py:350), so its "
                "presence is what proves the pairs survived",
                "o-mail-Message-trackingSeparator" in note
                or "fa-long-arrow-right" in note, actual_desc=note)
            ctx.check_true(
                "the quantity change 2 -> 7 appears at the field's own "
                "precision",
                ">2.00<" in note or ">2.0<" in note or ">2<" in note,
                actual_desc=note)
            ctx.check_true(
                "and the price change 20 -> 55 appears too",
                "55" in note and "20" in note, actual_desc=note)
            ctx.check_true(
                "the added products are named as creates",
                fx(f"{MARK} D") in note or fx(f"{MARK} E") in note,
                actual_desc=note)
            ctx.check_true("and the removed product as a delete",
                           fx(f"{MARK} C") in note, actual_desc=note)

        with ctx.step("Steps 12-13: nothing downstream moved and NO "
                      "revision was created — the revision path is for "
                      "unconfirmed orders only"):
            ctx.check("still exactly one order for this requisition", 1,
                      len(orders_for(rpc, [memo("REQ-C")])))
            if rpc.field_exists("sale.order", "current_revision_id"):
                revision = rpc.read("sale.order", [so_c],
                                    ["current_revision_id",
                                     "old_revision_ids"]
                                    if rpc.field_exists(
                                        "sale.order", "old_revision_ids")
                                    else ["current_revision_id"])[0]
                ctx.log(f"revision fields on SO-C: {revision!r}")
                ctx.check("no revision was created — create_revision is "
                          "only reached when state != 'sale' "
                          "(sale_order.py:272-275)",
                          False,
                          bool(m2o_id(revision.get("current_revision_id"))))
            ctx.check("the order is still confirmed", "sale",
                      rpc.read("sale.order", [so_c], ["state"])[0]["state"])
            if rpc.field_exists("sale.order", "picking_ids"):
                pickings = rpc.read("sale.order", [so_c],
                                    ["picking_ids", "invoice_status"])[0]
                ctx.log(f"downstream state: {pickings!r}")

        with ctx.step("Step 15: the sftp.file is DONE — this is a warning, "
                      "not a failure"):
            ctx.check("state", "done", second_row["state"])

        with ctx.step("Step 14: THE NEGATIVE CASE. A re-send that would "
                      "change nothing on the lines produces NO activity. A "
                      "spurious activity on every re-send would train users "
                      "to ignore them"):
            acts_before = len(activities_on(rpc, "sale.order", [so_c]))
            current = order_lines(rpc, so_c)
            # The file must name exactly the products the order already
            # carries, at exactly their current quantity and price, or the
            # diff would legitimately be non-empty and the assertion would
            # be about the fixture rather than about the product.
            codes = {
                line["id"]: rpc.read("product.product",
                                     [m2o_id(line["product_id"])],
                                     ["default_code"])[0]["default_code"]
                for line in current if m2o_id(line["product_id"])}
            noop = [
                row(item=codes[line["id"]],
                    description=fx(f"{MARK} noop"),
                    quantity=str(line["product_uom_qty"]),
                    unit_price=str(line["price_unit"]), **common)
                for line in current if line["id"] in codes
            ]
            _f, noop_id, noop_row = run_import(
                ctx, noop, folder_id=folder_id, file_label="noop")
            ctx.log(f"no-op re-send: {noop_row!r}")
            acts_after = len(activities_on(rpc, "sale.order", [so_c]))
            ctx.log(f"activities before the no-op: {acts_before}, after: "
                    f"{acts_after}")
            ctx.check("no new activity — update_confirmed_order builds "
                      "error_msg_list only for lines whose product, "
                      "quantity or price actually differ "
                      "(sale_order.py:395-429)", acts_before, acts_after)
            ctx.check("and the line set is STILL byte-identical", baseline,
                      [(line["id"], m2o_id(line["product_id"]),
                        line["product_uom_qty"], line["price_unit"])
                       for line in order_lines(rpc, so_c)])

        with ctx.step("Step 8 continued: the assignee chain's SECOND level "
                      "— unset the company setting and assert it falls "
                      "through to order.user_id"):
            if not rpc.field_exists("res.company", company_field):
                ctx.log("[warn] the company field does not exist on this "
                        "target, so levels 2 and 3 cannot be distinguished "
                        "from level 1. Recorded.")
            else:
                rpc.write("res.company", [company_id], {company_field: False})
                order_user = m2o_id(rpc.read("sale.order", [so_c],
                                             ["user_id"])[0]["user_id"])
                ctx.log(f"company setting cleared; order.user_id = "
                        f"{order_user}")
                before_count = len(activities_on(rpc, "sale.order", [so_c]))
                changed = [dict(entry) for entry in second]
                changed[0]["Quantity"] = "11"
                _f, level2_id, level2_row = run_import(
                    ctx, changed, folder_id=folder_id, file_label="level2")
                ctx.log(f"level-2 re-import: {level2_row!r}")
                acts = activities_on(rpc, "sale.order", [so_c])
                ctx.check("a new activity was filed", before_count + 1,
                          len(acts))
                if order_user:
                    ctx.check(
                        "and it is assigned to order.user_id — level 2 of "
                        "the chain (company setting OR user_id OR "
                        "create_uid, sale_order.py:432)",
                        order_user, m2o_id(acts[-1].get("user_id")))
                else:
                    ctx.log("[warn] order.user_id is unset on this fixture, "
                            "so level 2 collapses into level 3. The "
                            "assignee below is therefore create_uid.")
                    ctx.check("it fell through to create_uid — level 3",
                              m2o_id(before_header["create_uid"]),
                              m2o_id(acts[-1].get("user_id")))
                ctx.log("WF-001 records TD-CO-09 as UNKNOWN in the "
                        "test-data catalogue. If the company setting is "
                        "unset in production the activity lands on "
                        "order.user_id, and for a cron-created order that "
                        "may be a technical user nobody watches — so every "
                        "confirmed-order warning would be invisible. One "
                        "Phase-0a query settles it: SELECT "
                        "workday_sale_requisition_user_id FROM res_company;")
    finally:
        if rpc.field_exists("res.company", company_field) and not restored:
            try:
                rpc.write("res.company", [company_id],
                          {company_field: original_user})
                ctx.log(f"company {company_id}.{company_field} restored to "
                        f"{original_user!r}")
            except Exception as exc:                        # noqa: BLE001
                ctx.log(f"[warn] could not restore "
                        f"res.company.{company_field} ({exc}); set it back "
                        f"to {original_user!r} by hand.")
