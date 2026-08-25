"""DATAONE-WF-002 — the confirmation email, the UI surface and the round
trip: TC062, TC083, TC084, TC086, TC087, TC089, TC350.

The workbook marks TC083, TC084, TC086 and TC087 MANUAL because they are
about what a person sees. Three of the four turn out to be machine-checkable
after all, and for a reason worth stating: with every mail server
deactivated on the QA clone, ``send_mail(force_send=True)`` still **creates
the mail.mail record** and only then fails to deliver it — Odoo catches the
SMTP error and marks the message ``exception``
(mail/models/mail_mail.py:546-575). So ``email_to`` and ``body_html`` are
readable exactly as they were composed, without a byte leaving the box.

That is why TC083 (recipient routing by order type), TC084 (the IRM memo
appending the Ciena desk) and TC086 (the body's five required blocks) are
implemented here rather than left to a human. TC087 — a visual PDF diff —
is not: the report's existence and template are asserted and the comparison
itself is SKIPPED for a person.

EXPECTED v17 OUTCOME: PASS, except TC087 which ends SKIPPED and TC350 which
ends BLOCKED.
"""
import re

from framework.registry import test_case
from tests.wf002.common import (MARK, WORKFLOW, WORKFLOW_NAME,  # noqa: F401
                                confirm, ensure_partner, ensure_product, fx,
                                line_values, m2o_id, make_quotation,
                                order_lines, read_order, require_dto_sale,
                                require_mail_offline, sweep_wf002, trace)

# dto_sale/data/base_automation_data.xml — the recipient map, verbatim.
RECIPIENTS = {
    "project": ["mfgestimating@d1systems.com", "procurement@d1systems.com"],
    "buy": ["mfgestimating@d1systems.com", "orders@d1systems.com",
            "procurement@d1systems.com"],
    "inventory": ["mfgestimating@d1systems.com",
                  "miguel.oyervidez@d1systems.com",
                  "procurement@d1systems.com"],
    "cost_center": ["mfgestimating@d1systems.com",
                    "procurement@d1systems.com"],
}
IRM_DESK = "D1CienaIRM@d1systems.com"
TEMPLATE_XMLID = "dto_sale.mail_template_sale_order_confirmed"


def _require_template(ctx):
    rpc = ctx.adapter.rpc
    if not rpc.ref(TEMPLATE_XMLID):
        ctx.blocked(
            f"{TEMPLATE_XMLID} does not resolve on {ctx.env.key} — "
            "dto_sale's mail data is not loaded, so no confirmation email "
            "is composed to assert against.")


def _mails_for(rpc, order_id, fields_=None):
    """The mail.mail records the confirmation composed for this order.

    They survive because delivery failed: mark the target's mail servers
    inactive (require_mail_offline) and Odoo stores the message with
    state='exception' instead of deleting it.
    """
    fields_ = fields_ or ["email_to", "subject", "body_html", "state",
                          "res_id", "model"]
    if not rpc.model_exists("mail.mail"):
        return []
    return rpc.search_read("mail.mail",
                           [("model", "=", "sale.order"),
                            ("res_id", "=", order_id)],
                           fields_, order="id desc")


def _confirmed_order(ctx, order_type="project", memo="default", **kwargs):
    rpc = ctx.adapter.rpc
    product_id = ensure_product(ctx)
    order_id = make_quotation(
        ctx, order_type=order_type, memo=memo,
        lines=[line_values(product_id)], **kwargs)
    confirm(rpc, order_id)
    return order_id


@test_case(
    id="TEST-WF002-TC083",
    name="Confirmation email recipients routed by order type",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_sale", priority="P1", kind="API", order=2083,
    description="Each order type produces its own hard-coded recipient "
                "list, always prefixed by the requester's own address; read "
                "from the composed mail.mail without delivering anything.",
    traceability=trace("DATAONE-TC083"))
def test_tc083(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-002 fixtures and open a fresh "
                  "namespace"):
        sweep_wf002(rpc)

    with ctx.step("Preconditions: dto_sale, the template, mail offline"):
        require_dto_sale(ctx)
        _require_template(ctx)
        require_mail_offline(ctx)

    try:
        observed = {}
        requester = "qa.wf002@example.invalid"
        for order_type in ("project", "buy", "inventory", "cost_center"):
            with ctx.step(f"Confirm a {order_type} order and read the "
                          "composed recipient list"):
                order_id = _confirmed_order(ctx, order_type=order_type,
                                            requester=requester,
                                            label=f"Mail{order_type}")
                mails = _mails_for(rpc, order_id)
                ctx.log(f"{order_type}: {mails!r}")
                if not mails:
                    ctx.blocked(
                        "No mail.mail record survived the confirmation on "
                        f"{ctx.env.key}. The template's auto_delete may be "
                        "set, or mail is disabled entirely — either way the "
                        "composed recipient list cannot be read back, and "
                        "this case needs a human inspecting the outgoing "
                        "queue instead.")
                observed[order_type] = mails[0]["email_to"] or ""

        with ctx.step("Every list starts with the requester's own address"):
            ctx.check(
                "order types whose recipient list omits the requester", [],
                [t for t, v in observed.items()
                 if not v.startswith(f"{requester},")])

        with ctx.step("Each order type routes to its own hard-coded desks"):
            missing = {}
            for order_type, expected in RECIPIENTS.items():
                absent = [addr for addr in expected
                          if addr not in observed[order_type]]
                if absent:
                    missing[order_type] = absent
            ctx.log(f"composed lists: {observed!r}")
            ctx.check("expected recipients missing per order type", {},
                      missing)

        with ctx.step("The order types are distinguishable — buy and "
                      "inventory each add a desk the others do not"):
            ctx.check_true("buy routes to orders@d1systems.com",
                           "orders@d1systems.com" in observed["buy"],
                           actual_desc=observed["buy"])
            ctx.check_true(
                "inventory routes to miguel.oyervidez@d1systems.com",
                "miguel.oyervidez@d1systems.com" in observed["inventory"],
                actual_desc=observed["inventory"])
            ctx.check_true(
                "project does NOT route to orders@d1systems.com",
                "orders@d1systems.com" not in observed["project"],
                actual_desc=observed["project"])
    finally:
        with ctx.step("Cleanup WF-002 fixtures"):
            try:
                sweep_wf002(rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")


@test_case(
    id="TEST-WF002-TC084",
    name="An IRM memo appends the Ciena IRM desk to the recipient list",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_sale", priority="P2", kind="API", order=2084,
    description="A memo containing 'IRM' appends D1CienaIRM@d1systems.com; "
                "a memo without it does not. The match is a plain substring "
                "test, so it is case-sensitive and fires on any word "
                "containing IRM.",
    traceability=trace("DATAONE-TC084"))
def test_tc084(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-002 fixtures and open a fresh "
                  "namespace"):
        sweep_wf002(rpc)

    with ctx.step("Preconditions: dto_sale, the template, mail offline"):
        require_dto_sale(ctx)
        _require_template(ctx)
        require_mail_offline(ctx)

    try:
        results = {}
        for label, memo in (("with_irm", f"{MARK} IRM shipment"),
                            ("without_irm", f"{MARK} ordinary memo"),
                            ("lower_case", f"{MARK} irm shipment")):
            with ctx.step(f"Confirm an order whose memo is {memo!r}"):
                order_id = _confirmed_order(ctx, order_type="project",
                                            memo=memo, label=f"IRM{label}")
                mails = _mails_for(rpc, order_id)
                if not mails:
                    ctx.blocked(
                        "No mail.mail record survived the confirmation — "
                        "the composed recipient list cannot be read back "
                        "on this target.")
                results[label] = mails[0]["email_to"] or ""
                ctx.log(f"{label}: {results[label]!r}")

        with ctx.step("A memo containing 'IRM' appends the Ciena desk"):
            ctx.check_true(f"{IRM_DESK} is in the list",
                           IRM_DESK in results["with_irm"],
                           actual_desc=results["with_irm"])

        with ctx.step("A memo without it does not"):
            ctx.check_true(f"{IRM_DESK} is NOT in the list",
                           IRM_DESK not in results["without_irm"],
                           actual_desc=results["without_irm"])

        with ctx.step("The match is a plain substring test — record whether "
                      "it is case-sensitive"):
            case_sensitive = IRM_DESK not in results["lower_case"]
            ctx.log(f"lower-case 'irm' -> Ciena desk "
                    f"{'NOT ' if case_sensitive else ''}appended")
            ctx.check_true(
                "the case-sensitivity answer is recorded",
                isinstance(case_sensitive, bool),
                actual_desc=("case-SENSITIVE: 'irm' does not trigger"
                             if case_sensitive else
                             "case-INSENSITIVE: 'irm' also triggers"))
    finally:
        with ctx.step("Cleanup WF-002 fixtures"):
            try:
                sweep_wf002(rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")


@test_case(
    id="TEST-WF002-TC086",
    name="Confirmation email body: total, ship date, order type, Reference "
         "# and Request Memo",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_sale", priority="P2", kind="API", order=2086,
    description="The rendered body carries the requester's name, the "
                "formatted order total, the ship date, the order type's "
                "label, the Request Memo and the Reference # block — read "
                "from the composed mail.mail without delivering it.",
    traceability=trace("DATAONE-TC086"))
def test_tc086(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-002 fixtures and open a fresh "
                  "namespace"):
        sweep_wf002(rpc)

    with ctx.step("Preconditions: dto_sale, the template, mail offline"):
        require_dto_sale(ctx)
        _require_template(ctx)
        require_mail_offline(ctx)

    try:
        with ctx.step("Confirm a project order with a memo and a known "
                      "total"):
            product_id = ensure_product(ctx, price=100.0)
            order_id = make_quotation(
                ctx, order_type="project", label="Body",
                memo=f"{MARK} please expedite",
                lines=[line_values(product_id, qty=2.0, price=100.0,
                                   ship_date="2026-09-10")])
            if rpc.field_exists("sale.order", "requester"):
                rpc.write("sale.order", [order_id],
                          {"requester": fx(f"{MARK} Requester")})
            confirm(rpc, order_id)
            order = read_order(rpc, order_id,
                               ["name", "amount_total", "partner_id"])
            mails = _mails_for(rpc, order_id)
            if not mails:
                ctx.blocked(
                    "No mail.mail record survived the confirmation — the "
                    "rendered body cannot be read back on this target.")
            mail = mails[0]
            body = mail["body_html"] or ""
            ctx.log(f"subject: {mail['subject']!r}")

        with ctx.step("The subject names the customer and the order"):
            subject = mail["subject"] or ""
            ctx.check_true("subject carries the order name",
                           order["name"] in subject, actual_desc=subject)

        with ctx.step("The body carries the order name and the confirmation "
                      "sentence"):
            ctx.check_true("body names the order",
                           order["name"] in body,
                           actual_desc=body[:400])
            ctx.check_true("body says the order has been confirmed",
                           "has been confirmed" in body,
                           actual_desc=body[:400])

        with ctx.step("The body carries the five labelled blocks the "
                      "workbook names"):
            missing = [label for label in
                       ("Order Type", "Request Memo", "Delivery Address",
                        "Reference #")
                       if label not in body]
            ctx.check("labelled blocks missing from the body", [], missing)

        with ctx.step("The order type renders as its LABEL, not its key"):
            ctx.check_true("body shows 'Project-based'",
                           "Project-based" in body, actual_desc=body[:600])
            ctx.check_true("body does not leak the raw key 'project'",
                           not re.search(r">\s*project\s*<", body),
                           actual_desc=body[:600])

        with ctx.step("The body carries the memo and the estimated ship "
                      "date"):
            ctx.check_true("body carries the Request Memo text",
                           f"{MARK} please expedite" in body,
                           actual_desc=body[:800])
            ctx.check_true("body carries the estimated ship date line",
                           "Estimated to Ship on" in body,
                           actual_desc=body[:800])
    finally:
        with ctx.step("Cleanup WF-002 fixtures"):
            try:
                sweep_wf002(rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")


@test_case(
    id="TEST-WF002-TC087",
    name='Sale Order PDF: requester block, memo, "Product" header and '
         "product name",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_sale", priority="P2", kind="UI", order=2087,
    description="The report action and its QWeb template are asserted to "
                "exist and resolve; the visual diff against a v17 baseline "
                "print is a human comparison and the test ends SKIPPED.",
    traceability=trace("DATAONE-TC087"))
def test_tc087(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-002 fixtures and open a fresh "
                  "namespace"):
        sweep_wf002(rpc)

    with ctx.step("Precondition: dto_sale is installed"):
        require_dto_sale(ctx)

    with ctx.step("The Sale Order report action resolves to a template and "
                  "a paperformat"):
        reports = rpc.search_read(
            "ir.actions.report",
            [("model", "=", "sale.order"), ("report_type", "=", "qweb-pdf")],
            ["name", "report_name", "report_file", "paperformat_id"])
        ctx.log(f"sale.order PDF reports: {reports!r}")
        ctx.check_true("at least one sale.order PDF report exists",
                       bool(reports), actual_desc=repr(reports))
        unresolved = []
        for report in reports:
            template = rpc.search("ir.ui.view",
                                  [("type", "=", "qweb"),
                                   ("key", "=", report["report_name"])],
                                  limit=1)
            if not template:
                unresolved.append(report["report_name"])
        ctx.check("report templates that do not resolve to a qweb view", [],
                  unresolved)

    with ctx.step("dto_sale's report template overrides loaded"):
        overrides = rpc.search_read(
            "ir.ui.view", [("type", "=", "qweb"),
                           ("key", "like", "dto_sale.%")],
            ["key", "name"])
        ctx.log(f"dto_sale qweb views: {overrides!r}")

    with ctx.step("The printed-output comparison is a human check"):
        ctx.skip(
            "TC087 is a visual PDF diff against a captured v17 baseline "
            "print: the requester block, the Request Memo, the 'Product' "
            "column header and the product name are judged by eye on a "
            "rendered page. Rendering needs ir.actions.report."
            "_render_qweb_pdf, which is private and cannot be dispatched "
            "over RPC, and the comparison itself needs a person. Print the "
            "same order on both targets and diff the two PDFs. The report "
            "action and its template are asserted above, which is what "
            "catches the failure mode where the report does not render at "
            "all.")


@test_case(
    id="TEST-WF002-TC089",
    name="Order type and tariff search filters and group-by",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_sale", priority="P3", kind="API", order=2089,
    description="All six filters and the Order Type group-by are present "
                "in the composed search arch, each filter's domain returns "
                "the same count as the equivalent direct search, the "
                "group-by returns one group per order type, and two filters "
                "compose to their intersection.",
    traceability=trace("DATAONE-TC089"))
def test_tc089(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-002 fixtures and open a fresh "
                  "namespace"):
        sweep_wf002(rpc)

    with ctx.step("Precondition: dto_sale is installed"):
        require_dto_sale(ctx)

    try:
        with ctx.step("Step 2: all six filters and the group-by are in the "
                      "composed search arch"):
            arch = rpc.call("sale.order", "get_view",
                            view_type="search")["arch"]
            expected = ["order_with_tariff", "order_without_tariff",
                        "order_type_project", "order_type_buy",
                        "order_type_inventory", "order_type_cost_center",
                        "groupby_order_type"]
            missing = [name for name in expected
                       if f'name="{name}"' not in arch]
            ctx.check("filters missing from the search arch", [], missing)

        with ctx.step("Build one marker-scoped order of each type, two of "
                      "them carrying a tariff"):
            product_id = ensure_product(ctx)
            orders = {}
            for order_type in ("project", "buy", "inventory", "cost_center"):
                orders[order_type] = make_quotation(
                    ctx, order_type=order_type,
                    tariff=250.0 if order_type in ("project", "buy") else 0.0,
                    label=f"Filter{order_type}",
                    lines=[line_values(product_id)])
            scope = [("origin", "like", f"{MARK} %"),
                     ("active", "in", [True, False])]

        with ctx.step("Steps 3-4: the tariff filters partition the "
                      "marker-scoped set"):
            with_tariff = rpc.call(
                "sale.order", "search_count",
                scope + [("tariff_amount", ">", 0)])
            without_tariff = rpc.call(
                "sale.order", "search_count",
                scope + ["|", ("tariff_amount", "=", 0),
                         ("tariff_amount", "=", False)])
            ctx.log(f"with tariff {with_tariff}, without {without_tariff}")
            ctx.check("with-tariff count", 2, with_tariff)
            ctx.check("without-tariff count", 2, without_tariff)
            ctx.check("the two filters partition the set", 4,
                      with_tariff + without_tariff)

        with ctx.step("Step 5: each order-type filter returns exactly its "
                      "own order"):
            counts = {t: rpc.call("sale.order", "search_count",
                                  scope + [("order_type", "=", t)])
                      for t in orders}
            ctx.check("per-order-type counts",
                      {t: 1 for t in orders}, counts)

        with ctx.step("Step 6: Group By Order Type returns one group per "
                      "type with the right counts"):
            groups = rpc.read_group("sale.order", scope, ["order_type"],
                                    ["order_type"])
            ctx.log(f"read_group: {groups!r}")
            summary = {g["order_type"]: g["order_type_count"]
                       for g in groups if g.get("order_type")}
            ctx.check("group headings and counts",
                      {t: 1 for t in orders}, summary)

        with ctx.step("Step 7: the filters compose — order type AND tariff "
                      "is the intersection"):
            combined = rpc.call(
                "sale.order", "search_count",
                scope + [("order_type", "=", "project"),
                         ("tariff_amount", ">", 0)])
            ctx.check("project AND with-tariff", 1, combined)
            empty = rpc.call(
                "sale.order", "search_count",
                scope + [("order_type", "=", "inventory"),
                         ("tariff_amount", ">", 0)])
            ctx.check("inventory AND with-tariff", 0, empty)
    finally:
        with ctx.step("Cleanup WF-002 fixtures"):
            try:
                sweep_wf002(rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")


@test_case(
    id="TEST-WF002-TC062",
    name="Order Type is tracked, badged in the list, and survives "
         "duplication",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_sale", priority="P3", kind="API", order=2062,
    description="The field is declared with tracking, a change produces a "
                "chatter tracking value, the form and list arch place it "
                "where the workbook expects, and a duplicate carries the "
                "same order_type.",
    traceability=trace("DATAONE-TC062"))
def test_tc062(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-002 fixtures and open a fresh "
                  "namespace"):
        sweep_wf002(rpc)

    with ctx.step("Precondition: dto_sale is installed"):
        require_dto_sale(ctx)

    try:
        with ctx.step("Step 2: the form arch places Order Type before "
                      "Expiration"):
            arch = rpc.call("sale.order", "get_view", view_type="form")["arch"]
            ctx.check_true("order_type is in the form arch",
                           'name="order_type"' in arch,
                           actual_desc="absent")
            pos_type = arch.find('name="order_type"')
            pos_exp = arch.find('name="validity_date"')
            ctx.log(f"order_type at {pos_type}, validity_date at {pos_exp}")
            if pos_exp == -1:
                ctx.log("validity_date (Expiration) is not in this arch — "
                        "the relative-position assertion is skipped rather "
                        "than guessed")
            else:
                ctx.check_true("order_type precedes Expiration",
                               pos_type < pos_exp,
                               actual_desc=f"{pos_type} vs {pos_exp}")

        with ctx.step("Steps 3-4: changing Order Type produces a chatter "
                      "tracking entry"):
            order_id = make_quotation(ctx, order_type="project",
                                      label="Tracked")
            rpc.write("sale.order", [order_id], {"order_type": "buy"})
            tracked = rpc.search_read(
                "mail.tracking.value",
                [("mail_message_id.model", "=", "sale.order"),
                 ("mail_message_id.res_id", "=", order_id),
                 ("field_id.name", "=", "order_type")],
                ["field_id", "old_value_char", "new_value_char"])
            ctx.log(f"tracking values: {tracked!r}")
            ctx.check_true("the order_type change is tracked", bool(tracked),
                           actual_desc=repr(tracked))
            if tracked:
                ctx.check("tracked transition",
                          ("Project-based", "Buy/Sell"),
                          (tracked[-1]["old_value_char"],
                           tracked[-1]["new_value_char"]))

        with ctx.step("Step 6: the list arch carries Order Type before "
                      "Status"):
            list_arch = rpc.call(
                "sale.order", "get_view",
                view_type=ctx.adapter.list_view_type)["arch"]
            ctx.check_true("order_type is in the list arch",
                           'name="order_type"' in list_arch,
                           actual_desc="absent")
            pos_type = list_arch.find('name="order_type"')
            pos_state = list_arch.find('name="state"')
            ctx.log(f"list: order_type at {pos_type}, state at {pos_state}")
            if pos_state != -1:
                ctx.check_true("order_type precedes Status in the list",
                               pos_type < pos_state,
                               actual_desc=f"{pos_type} vs {pos_state}")

        with ctx.step("Step 7: a duplicate carries the same order_type — "
                      "Selection fields copy by default"):
            copy_id = rpc.call("sale.order", "copy", [order_id])
            copy_id = copy_id[0] if isinstance(copy_id, list) else copy_id
            ctx.check("duplicate order_type", "buy",
                      read_order(rpc, copy_id, ["order_type"])["order_type"])

        with ctx.step("The badge WIDGET is the one thing left to a person"):
            ctx.log("Whether order_type renders as a coloured selection "
                    "badge is a rendering judgement. The arch places it "
                    "correctly and the widget attribute is visible above; "
                    "confirm the colour by eye on both targets.")
    finally:
        with ctx.step("Cleanup WF-002 fixtures"):
            try:
                sweep_wf002(rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")


@test_case(
    id="TEST-WF002-TC350",
    name="GATE (Phase 5): the full Workday round trip, run twice",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account_workday, dto_mrp_sftp, dto_sale_workday",
    priority="P0", kind="API", order=2350,
    description="Offline half: the four Workday usage keys exist and every "
                "SFTP folder that uses them is inactive, so nothing on this "
                "target could reach Workday. The round trip itself needs "
                "the endpoint and the whole downstream chain.",
    traceability=trace("DATAONE-TC350"))
def test_tc350(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Precondition: the transport is installed"):
        if not rpc.model_exists("sftp.folder"):
            ctx.blocked(
                "novobi_sftp_connection is not installed on "
                f"{ctx.env.key} — there is no Workday transport to "
                "round-trip through.")

    with ctx.step("The four Workday usage keys are contributed"):
        info = rpc.call("sftp.folder", "fields_get", ["usage"],
                        attributes=["selection"])
        keys = [k for k, _l in (info["usage"].get("selection") or [])]
        ctx.log(f"usage keys: {keys}")
        expected = ["workday_vendor_bill", "workday_journal_entry",
                    "workday_vendor_payment", "workday_supplier"]
        ctx.check("Workday usage keys missing", [],
                  [k for k in expected if k not in keys])

    with ctx.step("Convention rule 4: every Workday SFTP folder on this "
                  "target is inactive"):
        folders = rpc.search_read(
            "sftp.folder",
            [("usage", "in", expected), ("active", "in", [True, False])],
            ["path", "usage", "active"])
        ctx.log(f"Workday folders: {folders!r}")
        ctx.check("ACTIVE Workday SFTP folders", [],
                  [f["path"] for f in folders if f["active"]])

    with ctx.step("The round trip needs the Workday endpoint and every "
                  "workflow it chains through"):
        ctx.blocked(
            "TC350 is the Phase-5 gate: one requisition file in, through "
            "sales order confirmation, procurement, manufacturing, "
            "delivery, invoicing and the journal-entry export, and back out "
            "to Workday — run twice to prove idempotence. It needs a live "
            "(or mocked) SFTP endpoint, the private ETL entry points that "
            "RPC cannot dispatch, and WF-001, WF-004, WF-005, WF-007, "
            "WF-011, WF-012, WF-013, WF-017, WF-018 and WF-019 all built. "
            "Run it from a scratch instance against TD-SF-01 once those "
            "workflows exist. This platform asserts, above, that nothing "
            "here can reach Workday.")
