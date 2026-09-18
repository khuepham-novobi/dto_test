"""DATAONE-WF-012 — the shipment notification: TC290.

The workbook classifies TC290 as MANUAL_ONLY, because its steps are written
as "record every recipient, the subject, and whether the Delivery Slip is
attached" — a human reading an inbox. On a neutralised QA clone the same
evidence is available without a human and without sending anything, and
that is what this case does.

Why the evidence is readable offline
------------------------------------
``mail.template.auto_delete`` is True on
``dto_sale_stock.mail_template_delivery_validated``, so a mail that SENDS is
unlinked immediately. A mail that CANNOT send is not: ``mail.mail._send``
catches the delivery failure and leaves the record in state ``exception``
with ``email_to``, ``subject``, ``body_html`` and ``attachment_ids`` intact.
The QA clone has every ``ir.mail_server`` deactivated (convention rule 4,
probed by ``require_mail_offline``), so every mail this case triggers stays
on the box and stays readable. Nothing is delivered and nothing may be
re-sent.

The three records this case reads are all under ``<data noupdate="1">``
(``dto_sale_stock/data/base_automation_data.xml``), which means **a module
upgrade does not refresh them**. Any fix made to the source tree during the
port — including the ``or ''`` guard below — stays unapplied on a database
that already has the records. So this case reads the server action's code
FROM THE DATABASE, never from the repository. That is the whole point of
asserting it at all.

The empty-memo defect (E7)
--------------------------
The server action evaluates ``'IRM' in order.memo_to_suppliers``.
``memo_to_suppliers`` is an optional Text field, so the ORM yields ``False``
on a NULL column and ``'IRM' in False`` raises ``TypeError`` — inside the
``button_validate`` transaction, which aborts the delivery. Nothing ships
and nothing is invoiced. The ported source carries
``'IRM' in (order.memo_to_suppliers or '')`` and
``dto_sale_stock/migrations/19.0.0.2/post-migrate.py`` exists solely to push
that guard onto a database the noupdate flag would otherwise protect.

This case therefore does not assume which version the target holds. It
reads the live code, records whether the guard is present, and asserts the
behaviour that must follow from what it found — guard present means the
delivery completes, guard absent means the delivery aborts and the picking
is still ``assigned``. Both are correct outcomes for their own database;
only a mismatch between the code and the behaviour is a failure.

EXPECTED v17 OUTCOME: PASS. On an unmigrated v17 clone the guard is absent
and the empty-memo delivery is expected to ABORT — that is the asserted
outcome, not an error.
EXPECTED v19 OUTCOME: PASS once post-migrate.py has run. The "Reference #"
line is the silent risk: delta §2.14 leaves the analytic key format an open
Unknown, and a changed format renders the line empty with nothing raised.
Step 4 is the assertion that catches it.
"""
from framework.registry import test_case
from tests.wf012.common import (IRM_RECIPIENT, MARK,  # noqa: F401
                                SHIPMENT_AUTOMATION_XMLID,
                                SHIPMENT_RECIPIENTS,
                                SHIPMENT_SERVER_ACTION_XMLID,
                                SHIPMENT_TEMPLATE_XMLID, WORKFLOW,
                                WORKFLOW_NAME, confirm_with_stock,
                                ensure_product, expect_error, fx,
                                gate_analytic, m2o_id,
                                outgoing_picking, realtime_category,
                                require_auto_invoice_stack,
                                require_cogs_analytics, require_mail_offline,
                                sweep_wf012, trace, validate_picking)

# The guard the port adds. Its presence in the LIVE code decides which
# behaviour the empty-memo step must assert.
MEMO_GUARD_SNIPPET = "or ''"


def _mails_for_picking(rpc, picking_id, subject_like=None):
    """Every mail.mail this picking produced, readable because it failed.

    Searched by model/res_id first; a template rendered through
    ``send_mail`` stamps ``mail.message.model``/``res_id``, and mail.mail
    carries ``mail_message_id``. Falls back to the subject when the message
    link is not populated on the target version.
    """
    fields_ = ["subject", "email_to", "state", "failure_reason",
               "attachment_ids", "body_html"]
    messages = rpc.search("mail.message", [("model", "=", "stock.picking"),
                                           ("res_id", "=", picking_id)])
    rows = []
    if messages:
        rows = rpc.search_read(
            "mail.mail", [("mail_message_id", "in", messages)], fields_)
    if not rows and subject_like:
        rows = rpc.search_read(
            "mail.mail", [("subject", "like", subject_like)], fields_)
    return rows


@test_case(
    id="TEST-WF012-TC290",
    name="The shipment email is routed by order type, with the Delivery "
         "Slip attached",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_sale_stock", priority="P2", kind="API", order=12290,
    description="Reads the LIVE noupdate=1 automation, server action and "
                "template, then validates one delivery per order type on a "
                "mail-offline clone and asserts the queued mail's "
                "recipients, subject, delivery date, non-empty Reference # "
                "and Delivery Slip attachment — plus the IRM append, the "
                "empty-memo abort, and no email for an incoming picking or "
                "a picking with no sale order.",
    traceability=trace("DATAONE-TC290"))
def test_tc290(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-012 fixtures and open a fresh "
                  "namespace"):
        sweep_wf012(rpc)

    with ctx.step("Preconditions: dto_sale_stock installed, EVERY mail "
                  "server deactivated (this case triggers real send_mail "
                  "calls), the five COGS analytic xmlids"):
        require_auto_invoice_stack(ctx)
        require_mail_offline(ctx)
        require_cogs_analytics(ctx)
        category = realtime_category(ctx)

    with ctx.step("Resolve the three noupdate=1 records. A module upgrade "
                  "does NOT refresh them, so what the database holds is "
                  "the only thing worth asserting"):
        automation_id = rpc.ref(SHIPMENT_AUTOMATION_XMLID)
        action_id = rpc.ref(SHIPMENT_SERVER_ACTION_XMLID)
        template_id = rpc.ref(SHIPMENT_TEMPLATE_XMLID)
        ctx.log(f"automation={automation_id} action={action_id} "
                f"template={template_id}")
        ctx.check("unresolved shipment xmlids", [],
                  [name for name, value in (
                      (SHIPMENT_AUTOMATION_XMLID, automation_id),
                      (SHIPMENT_SERVER_ACTION_XMLID, action_id),
                      (SHIPMENT_TEMPLATE_XMLID, template_id)) if not value])

    with ctx.step("Read the LIVE server-action code and assert the "
                  "recipient mapping literals it actually holds"):
        action = rpc.read("ir.actions.server", [action_id],
                          ["code", "state", "name"])[0]
        code = action.get("code") or ""
        ctx.check("server action state", "code", action["state"])
        missing = []
        for order_type, recipients in SHIPMENT_RECIPIENTS.items():
            for recipient in recipients:
                if recipient not in code:
                    missing.append(f"{order_type}:{recipient}")
        ctx.check("recipient literals absent from the live server action",
                  [], missing)
        ctx.check_true(f"the IRM recipient {IRM_RECIPIENT} is coded",
                       IRM_RECIPIENT in code,
                       actual_desc=IRM_RECIPIENT in code)

    with ctx.step("Record whether the LIVE code carries the empty-memo "
                  "guard. This decides what the negative step asserts"):
        guard_present = MEMO_GUARD_SNIPPET in code and "memo_to_suppliers" in code
        ctx.log(f"empty-memo guard present in the live code: {guard_present}")
        ctx.log("Guard absent  -> an order with a NULL memo must ABORT its "
                "delivery with TypeError (the E7 defect, live on an "
                "unmigrated clone).")
        ctx.log("Guard present -> the same delivery must COMPLETE "
                "(dto_sale_stock/migrations/19.0.0.2/post-migrate.py has "
                "run).")

    with ctx.step("Assert the template attaches the Delivery Slip and "
                  "carries the subject contract"):
        report_field = ("report_template_ids"
                        if rpc.field_exists("mail.template",
                                            "report_template_ids")
                        else "report_template")
        template = rpc.read("mail.template", [template_id],
                            ["subject", report_field])[0]
        ctx.log(f"template: {template!r} (report field {report_field!r})")
        ctx.check_true("the subject is '<Customer> Order for <SO> is "
                       "Shipped'",
                       "is Shipped" in (template.get("subject") or ""),
                       actual_desc=template.get("subject"))
        delivery_report = rpc.ref("stock.action_report_delivery")
        attached = template.get(report_field)
        attached_ids = (attached if isinstance(attached, list)
                        else [m2o_id(attached)] if attached else [])
        attached_ids = [i for i in attached_ids if isinstance(i, int)]
        ctx.check_true("the Delivery Slip report is attached to the "
                       "template",
                       delivery_report in attached_ids,
                       actual_desc=f"{attached_ids} vs {delivery_report}")

    try:
        # ------------------------------------------------ steps 1-4
        with ctx.step("Steps 1-4: validate one delivery per order type and "
                      "read the queued mail's recipients, subject, "
                      "delivery date and Reference # line"):
            categ_id = category["id"] if category else None
            findings = {}
            for order_type in ("project", "buy", "inventory", "cost_center"):
                product_id = ensure_product(ctx, label=f"P290-{order_type}",
                                            categ_id=categ_id)
                order_id, _ = confirm_with_stock(
                    ctx, order_type=order_type, product_id=product_id,
                    label=f"TC290-{order_type}")
                order = rpc.read("sale.order", [order_id],
                                 ["name", "requester_email"])[0]
                picking = outgoing_picking(ctx, order_id)
                validate_picking(ctx, picking["id"])
                row = rpc.read("stock.picking", [picking["id"]],
                               ["state", "date_done"])[0]
                mails = _mails_for_picking(rpc, picking["id"],
                                           subject_like=order["name"])
                findings[order_type] = {
                    "picking_state": row["state"],
                    "date_done": row["date_done"],
                    "order_name": order["name"],
                    "requester_email": order.get("requester_email"),
                    "mails": mails,
                }
                ctx.log(f"{order_type}: picking={row!r} mails={mails!r}")

            no_mail = [t for t, f in findings.items() if not f["mails"]]
            if no_mail:
                ctx.blocked(
                    "No mail.mail record survived for these order types: "
                    f"{no_mail}. The template has auto_delete=True, so a "
                    "mail that SENT is unlinked immediately — which means "
                    "this target can actually deliver email and must not "
                    "be used for WF-012. Deactivate every ir.mail_server "
                    "and re-run. (If mail is already offline, the "
                    "base.automation may simply not be firing: check "
                    f"{SHIPMENT_AUTOMATION_XMLID}.active.)")

            recipient_gaps = {}
            for order_type, found in findings.items():
                addressed = ",".join(m.get("email_to") or ""
                                     for m in found["mails"])
                expected = list(SHIPMENT_RECIPIENTS[order_type])
                if found["requester_email"]:
                    expected.append(found["requester_email"])
                absent = [r for r in expected if r not in addressed]
                if absent:
                    recipient_gaps[order_type] = {"absent": absent,
                                                  "email_to": addressed}
            ctx.check("order types whose shipment mail is missing a "
                      "recipient", {}, recipient_gaps)

            subject_gaps = {
                order_type: [m.get("subject") for m in found["mails"]]
                for order_type, found in findings.items()
                if not any("is Shipped" in (m.get("subject") or "")
                           and found["order_name"] in (m.get("subject") or "")
                           for m in found["mails"])}
            ctx.check("order types whose subject is not '<Customer> Order "
                      "for <SO number> is Shipped'", {}, subject_gaps)

        with ctx.step("Step 3: the body's delivery date matches date_done "
                      "formatted %m/%d/%Y"):
            date_gaps = {}
            for order_type, found in findings.items():
                body = " ".join(m.get("body_html") or ""
                                for m in found["mails"])
                done = (found["date_done"] or "")[:10]
                if not done:
                    continue
                year, month, day = done.split("-")
                expected = f"{month}/{day}/{year}"
                if expected not in body:
                    date_gaps[order_type] = {"expected": expected,
                                             "date_done": found["date_done"]}
            ctx.check("order types whose body does not carry date_done in "
                      "%m/%d/%Y", {}, date_gaps)

        with ctx.step("Step 4 — THE SILENT v19 RISK: the Reference # line "
                      "is non-empty. Delta §2.14 leaves the analytic key "
                      "format Unknown; a changed format empties this line "
                      "with nothing raised"):
            reference_gaps = {}
            for order_type, found in findings.items():
                body = " ".join(m.get("body_html") or ""
                                for m in found["mails"])
                if "Reference #" not in body:
                    reference_gaps[order_type] = "the label itself is absent"
            ctx.log("NOTE: what is asserted here is that the block RENDERS, "
                    "not what it contains. Since Stage 7 the project and buy "
                    "fixtures carry a gate distribution (dto_account refuses "
                    "to confirm them without one) while the inventory and "
                    "cost_center fixtures carry none — dto_account refuses "
                    "ANY distribution on those two — so the same assertion "
                    "covers a filled and an empty block. Step 4b below "
                    "asserts the content.")
            ctx.check("order types whose body has no Reference # block",
                      {}, reference_gaps)

        with ctx.step("Step 4b: an order WITH an analytic distribution "
                      "renders '<plan> - <account>' under Reference #"):
            # The account must be on the PROJECT plan. Since Stage 7,
            # dto_account/models/sale_order.py:89 raises 'Project is
            # required' when ANY account on a project order's line sits on
            # another plan, so the Spend Category account this step used
            # before can no longer reach a confirmed order at all. What is
            # asserted — that the account renders as '<plan> - <account>'
            # under Reference # — is unchanged.
            distribution = gate_analytic(ctx, "project",
                                         label=f"{MARK} WF012")
            if not distribution:
                ctx.blocked(
                    "dto_account's Project analytic plan does not resolve on "
                    f"{ctx.env.key}, so no distribution can be built for a "
                    "project order and the Reference # content cannot be "
                    "asserted.")
            analytic_id = int(next(iter(distribution)))
            product_id = ensure_product(ctx, label="P290-analytic",
                                        categ_id=categ_id)
            order_id, _ = confirm_with_stock(
                ctx, order_type="project", product_id=product_id,
                label="TC290-analytic", analytic=distribution)
            picking = outgoing_picking(ctx, order_id)
            validate_picking(ctx, picking["id"])
            order_name = rpc.read("sale.order", [order_id],
                                  ["name"])[0]["name"]
            mails = _mails_for_picking(rpc, picking["id"],
                                       subject_like=order_name)
            body = " ".join(m.get("body_html") or "" for m in mails)
            account = rpc.read("account.analytic.account", [analytic_id],
                               ["name", "plan_id"])[0]
            expected = f"{account['plan_id'][1]} - {account['name']}"
            ctx.log(f"expected Reference # content: {expected!r}")
            ctx.check_true(
                "the analytic account renders under Reference #",
                expected in body,
                actual_desc=body[-1500:] if body else "(no body)")

        # ------------------------------------------------ step 5
        with ctx.step("Step 5: a memo containing IRM appends "
                      f"{IRM_RECIPIENT}"):
            product_id = ensure_product(ctx, label="P290-irm",
                                        categ_id=categ_id)
            order_id, _ = confirm_with_stock(
                ctx, order_type="project", product_id=product_id,
                label="TC290-irm", memo=f"{MARK} IRM shipment")
            picking = outgoing_picking(ctx, order_id)
            validate_picking(ctx, picking["id"])
            order_name = rpc.read("sale.order", [order_id],
                                  ["name"])[0]["name"]
            mails = _mails_for_picking(rpc, picking["id"],
                                       subject_like=order_name)
            addressed = ",".join(m.get("email_to") or "" for m in mails)
            ctx.log(f"IRM email_to: {addressed!r}")
            ctx.check_true(f"{IRM_RECIPIENT} was appended",
                           IRM_RECIPIENT in addressed,
                           actual_desc=addressed)

        # ------------------------------------------------ steps 6-7
        with ctx.step("Steps 6-7 — THE E7 DEFECT: an order with an EMPTY "
                      "memo. The automation runs inside the validation "
                      "transaction, so the guard's absence aborts the "
                      "delivery itself"):
            product_id = ensure_product(ctx, label="P290-nomemo",
                                        categ_id=categ_id)
            order_id, _ = confirm_with_stock(
                ctx, order_type="project", product_id=product_id,
                label="TC290-nomemo", memo="")
            rpc.write("sale.order", [order_id], {"memo_to_suppliers": False})
            picking = outgoing_picking(ctx, order_id)
            raised, message = expect_error(validate_picking, ctx,
                                           picking["id"])
            state = rpc.read("stock.picking", [picking["id"]],
                             ["state"])[0]["state"]
            ctx.log(f"empty-memo validation raised={raised} "
                    f"message={message!r} picking_state={state!r}")
            if guard_present:
                ctx.check("empty-memo delivery with the guard PRESENT "
                          "completes", "done", state)
                ctx.check_true("no exception was raised", not raised,
                               actual_desc=message)
            else:
                ctx.check_true(
                    "empty-memo delivery with the guard ABSENT raises "
                    "TypeError (E7)",
                    raised and "TypeError" in message,
                    actual_desc=message)
                ctx.check("the picking did NOT ship — nothing left the "
                          "building and nothing was invoiced",
                          "assigned", state)
                invoices = rpc.read("sale.order", [order_id],
                                    ["invoice_ids"])[0]["invoice_ids"]
                ctx.check("no invoice was created by the aborted delivery",
                          [], invoices)

        # ------------------------------------------------ steps 8-9
        with ctx.step("Step 8: an INCOMING picking sends no email — the "
                      "server action filters on picking_type_code == "
                      "'outgoing'"):
            incoming_type = rpc.ref("stock.picking_type_in")
            product_id = ensure_product(ctx, label="P290-in",
                                        categ_id=categ_id)
            type_row = rpc.read("stock.picking.type", [incoming_type],
                                ["default_location_src_id",
                                 "default_location_dest_id"])[0]
            picking_in = rpc.create("stock.picking", {
                "picking_type_id": incoming_type,
                "origin": fx(f"{MARK} TC290-in"),
                "location_id": m2o_id(type_row["default_location_src_id"]),
                "location_dest_id": m2o_id(
                    type_row["default_location_dest_id"]),
                "move_ids": [(0, 0, {
                    "name": fx(f"{MARK} in"),
                    "product_id": product_id,
                    "product_uom_qty": 1.0,
                    "location_id": m2o_id(type_row["default_location_src_id"]),
                    "location_dest_id": m2o_id(
                        type_row["default_location_dest_id"]),
                })],
            })
            rpc.call("stock.picking", "action_confirm", [picking_in])
            validate_picking(ctx, picking_in)
            mails = _mails_for_picking(rpc, picking_in)
            ctx.log(f"incoming picking mails: {mails!r}")
            ctx.check("emails sent for an incoming picking", 0, len(mails))

        with ctx.step("Step 9: an OUTGOING picking with NO sale order "
                      "sends no email — the same filter requires r.sale_id"):
            outgoing_type = rpc.ref("stock.picking_type_out")
            type_row = rpc.read("stock.picking.type", [outgoing_type],
                                ["default_location_src_id",
                                 "default_location_dest_id"])[0]
            src = m2o_id(type_row["default_location_src_id"])
            dest = m2o_id(type_row["default_location_dest_id"])
            picking_out = rpc.create("stock.picking", {
                "picking_type_id": outgoing_type,
                "origin": fx(f"{MARK} TC290-nosale"),
                "location_id": src,
                "location_dest_id": dest,
                "move_ids": [(0, 0, {
                    "name": fx(f"{MARK} out"),
                    "product_id": product_id,
                    "product_uom_qty": 1.0,
                    "location_id": src,
                    "location_dest_id": dest,
                })],
            })
            rpc.call("stock.picking", "action_confirm", [picking_out])
            raised, message = expect_error(validate_picking, ctx, picking_out)
            if raised:
                ctx.log("[note] validation of the no-sale-order picking was "
                        f"refused: {message}. That is the "
                        "dto_mrp_account.group_validate_delivery_orders "
                        "gate, not the mail path.")
            mails = _mails_for_picking(rpc, picking_out)
            ctx.log(f"no-sale-order picking mails: {mails!r}")
            ctx.check("emails sent for an outgoing picking with no sale "
                      "order", 0, len(mails))
    finally:
        with ctx.step("Cleanup WF-012 fixtures"):
            try:
                sweep_wf012(rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")
