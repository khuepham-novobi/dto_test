"""DATAONE-WF-002 — the confirmation gates: TC073–TC082, TC085.

Confirming a DataOne sales order passes through four guards stacked by
``_inherit`` on ``sale.order.action_confirm``:

* ``dto_sale_workday`` — requester email (dto_sale_workday/models/
  sale_order.py:25);
* ``dto_account`` — ``validate_analytic_distribution()``, dispatching to
  ``_validate_analytic_distribution_<order_type>`` (dto_account/models/
  sale_order.py:11);
* ``dto_sale`` — Promised Ship Date on every product line
  (dto_sale/models/sale_order.py:59);
* and then the ``base_automation`` that sends the confirmation email, whose
  server action crashes on an empty memo — TC085.

**v19 migration finding recorded here.** ``dto_account`` calls
``line._get_analytic_account_ids()``, which exists on Odoo 17
(``addons/analytic/models/analytic_mixin.py:159``) but is **gone on Odoo
19** — replaced by ``_get_analytic_account_ids_from_distributions(...)``
(``analytic_mixin.py:49``). All four analytic gates therefore raise
``AttributeError`` on v19 until ``dto_account`` is ported. TC074 and
TC078–TC082 are EXPECTED to ERROR there; on v17 they pass. That is a real
product finding, not an automation defect.

Every test here confirms (or tries to confirm) an order, so each one calls
``require_mail_offline`` first.

EXPECTED v17 OUTCOME: PASS for all.
EXPECTED v19 OUTCOME: TC073 and TC077 PASS; TC074 and TC078-TC082 pass once
dto_account is ported (it now is — the handlers read
``distribution_analytic_account_ids``, dto_account/models/sale_order.py:83).

**TC085 is EXPECTED to FAIL on v19, and that failure is the remediation.**
``dto_sale/migrations/19.0.0.2/post-migrate.py`` rewrites the server action
from ``if 'IRM' in order.memo_to_suppliers:`` to
``if 'IRM' in (order.memo_to_suppliers or ''):`` on every upgraded database
(decision D-19, signed, with an expected_deltas row). The TypeError this
case documents therefore no longer fires on the target: the order confirms
and one email is sent. Convention rule 2 — the workbook's expectation
describes the v17 defect and is not inverted here; the v19 run classifies it
as FIXED. Do not "repair" this test by asserting the new behaviour.
"""
from framework.registry import test_case
from tests.wf002.common import (ANALYTIC_PLANS, CONTRACT_ERROR,  # noqa: F401
                                MARK, NO_ANALYTIC_ERROR, PROJECT_ERROR,
                                REQUESTER_ERROR, SHIP_DATE_ERROR, WORKFLOW,
                                WORKFLOW_NAME, confirm, ensure_analytic_account,
                                ensure_product, expect_error, fx, line_values,
                                m2o_id, make_quotation, order_lines,
                                read_order, require_analytic_plans,
                                require_dto_sale, require_mail_offline,
                                sweep_wf002, trace)


def _downstream_counts(rpc, order_id) -> dict:
    """stock.move / mrp.production / purchase.order / stock.picking rows a
    confirmation would have produced. Every gate must leave all four at 0."""
    order = read_order(rpc, order_id, ["name"])
    line_ids = [ln["id"] for ln in order_lines(rpc, order_id, ["id"])]
    counts = {}
    if line_ids and rpc.field_exists("stock.move", "sale_line_id"):
        counts["stock.move"] = rpc.call(
            "stock.move", "search_count", [("sale_line_id", "in", line_ids)])
    else:
        counts["stock.move"] = 0
    for model in ("mrp.production", "purchase.order", "stock.picking"):
        if rpc.model_exists(model) and rpc.field_exists(model, "origin"):
            counts[model] = rpc.call(model, "search_count",
                                     [("origin", "=", order["name"])])
        else:
            counts[model] = 0
    return counts


def _distribution(account_id, percentage=100):
    """analytic_distribution is a JSON map of '<account id>' -> percentage."""
    return {str(account_id): percentage}


@test_case(
    id="TEST-WF002-TC073",
    name="Gate 1: no requester email blocks confirmation and creates nothing",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_sale_workday", priority="P1", kind="API", order=2073,
    description="The check runs before super(), so the exact "
                "ValidationError leaves the order draft with zero stock "
                "moves, manufacturing orders, purchase orders or pickings.",
    traceability=trace("DATAONE-TC073"))
def test_tc073(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-002 fixtures and open a fresh "
                  "namespace"):
        sweep_wf002(rpc)

    with ctx.step("Preconditions: dto_sale installed, mail offline"):
        require_dto_sale(ctx)
        require_mail_offline(ctx)
        if not rpc.field_exists("sale.order", "requester_email"):
            ctx.blocked(
                "sale.order.requester_email does not exist on "
                f"{ctx.env.key} — dto_sale_workday is not installed, so "
                "gate 1 does not exist to be tested.")

    try:
        with ctx.step("Steps 1-2: a quotation with an EMPTY requester "
                      "email, otherwise fully valid"):
            order_id = make_quotation(ctx, order_type="inventory",
                                      requester=None, label="NoRequester")
            ctx.check("requester_email", False,
                      read_order(rpc, order_id,
                                 ["requester_email"])["requester_email"])

        with ctx.step("Steps 3-4: Confirm raises the exact message"):
            raised, message = expect_error(confirm, rpc, order_id)
            ctx.log(f"raised: {message!r}")
            ctx.check_true("confirmation was blocked", raised,
                           actual_desc=message)
            ctx.check_true(f"message is {REQUESTER_ERROR!r}",
                           REQUESTER_ERROR in message, actual_desc=message)

        with ctx.step("Step 5: the order is still draft"):
            ctx.check("state", "draft",
                      read_order(rpc, order_id, ["state"])["state"])

        with ctx.step("Steps 6-8: nothing downstream was created — the "
                      "check runs before super()"):
            ctx.check("downstream record counts",
                      {"stock.move": 0, "mrp.production": 0,
                       "purchase.order": 0, "stock.picking": 0},
                      _downstream_counts(rpc, order_id))
    finally:
        with ctx.step("Cleanup WF-002 fixtures"):
            try:
                sweep_wf002(rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")


@test_case(
    id="TEST-WF002-TC074",
    name="Gate 2: a missing analytic account blocks confirmation and "
         "creates nothing",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account", priority="P1", kind="API", order=2074,
    description="A project order whose line carries no analytic "
                "distribution raises 'Project is required', stays draft and "
                "creates nothing; adding a Project-plan distribution lets it "
                "confirm.",
    traceability=trace("DATAONE-TC074"))
def test_tc074(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-002 fixtures and open a fresh "
                  "namespace"):
        sweep_wf002(rpc)

    with ctx.step("Preconditions: dto_sale installed, analytic plans "
                  "resolvable, mail offline"):
        require_dto_sale(ctx)
        plans = require_analytic_plans(ctx, ("project",))
        require_mail_offline(ctx)

    try:
        with ctx.step("Steps 1-2: a project order whose second line has no "
                      "analytic distribution"):
            product_id = ensure_product(ctx)
            project_account = ensure_analytic_account(rpc, plans["project"],
                                                      "Project A")
            order_id = make_quotation(
                ctx, order_type="project", label="AnalyticGate",
                lines=[line_values(product_id,
                                   analytic=_distribution(project_account)),
                       line_values(product_id)])
            lines = order_lines(rpc, order_id, ["analytic_distribution"])
            ctx.log(f"lines: {lines!r}")
            ctx.check("line 2 analytic_distribution", False,
                      lines[1]["analytic_distribution"])

        with ctx.step("Steps 3-4: Confirm raises the exact message"):
            raised, message = expect_error(confirm, rpc, order_id)
            ctx.log(f"raised: {message!r}")
            ctx.check_true("confirmation was blocked", raised,
                           actual_desc=message)
            ctx.check_true(f"message is {PROJECT_ERROR!r}",
                           PROJECT_ERROR in message, actual_desc=message)

        with ctx.step("Steps 5-6: still draft, nothing downstream"):
            ctx.check("state", "draft",
                      read_order(rpc, order_id, ["state"])["state"])
            ctx.check("downstream record counts",
                      {"stock.move": 0, "mrp.production": 0,
                       "purchase.order": 0, "stock.picking": 0},
                      _downstream_counts(rpc, order_id))

        with ctx.step("Step 7: a Project-plan distribution on line 2 lets "
                      "it confirm"):
            rpc.write("sale.order.line", [lines[1]["id"]],
                      {"analytic_distribution":
                       _distribution(project_account)})
            confirm(rpc, order_id)
            ctx.check("state", "sale",
                      read_order(rpc, order_id, ["state"])["state"])
    finally:
        with ctx.step("Cleanup WF-002 fixtures"):
            try:
                sweep_wf002(rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")


@test_case(
    id="TEST-WF002-TC075",
    name="Gate 3: the Promised Ship Date gate creates nothing downstream",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_sale", priority="P1", kind="API", order=2075,
    description="The ship-date gate leaves the order draft with zero stock "
                "moves, manufacturing orders, purchase orders and pickings.",
    traceability=trace("DATAONE-TC075"))
def test_tc075(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-002 fixtures and open a fresh "
                  "namespace"):
        sweep_wf002(rpc)

    with ctx.step("Preconditions: dto_sale installed, mail offline"):
        require_dto_sale(ctx)
        require_mail_offline(ctx)

    try:
        with ctx.step("Step 1: a quotation whose product line has no "
                      "Promised Ship Date"):
            product_id = ensure_product(ctx)
            order_id = make_quotation(
                ctx, order_type="inventory", label="ShipGate3",
                lines=[line_values(product_id, ship_date=None)])

        with ctx.step("Steps 2-3: Confirm raises the exact message"):
            raised, message = expect_error(confirm, rpc, order_id)
            ctx.log(f"raised: {message!r}")
            ctx.check_true("confirmation was blocked", raised,
                           actual_desc=message)
            ctx.check_true(f"message is {SHIP_DATE_ERROR!r}",
                           SHIP_DATE_ERROR in message, actual_desc=message)

        with ctx.step("Steps 4-8: still draft, and zero of every downstream "
                      "record type"):
            ctx.check("state", "draft",
                      read_order(rpc, order_id, ["state"])["state"])
            ctx.check("downstream record counts",
                      {"stock.move": 0, "mrp.production": 0,
                       "purchase.order": 0, "stock.picking": 0},
                      _downstream_counts(rpc, order_id))
    finally:
        with ctx.step("Cleanup WF-002 fixtures"):
            try:
                sweep_wf002(rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")


@test_case(
    id="TEST-WF002-TC076",
    name="Which gate fires first: the MRO order of the three overrides",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_sale_workday", priority="P1", kind="API", order=2076,
    description="Peeling the three gates one at a time reveals their "
                "execution order: requester email, then the analytic plan, "
                "then the Promised Ship Date — the behavioural equivalent "
                "of reading the MRO, which RPC cannot expose.",
    traceability=trace("DATAONE-TC076"))
def test_tc076(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-002 fixtures and open a fresh "
                  "namespace"):
        sweep_wf002(rpc)

    with ctx.step("Preconditions: all three gates exist, mail offline"):
        require_dto_sale(ctx)
        plans = require_analytic_plans(ctx, ("project",))
        require_mail_offline(ctx)
        if not rpc.field_exists("sale.order", "requester_email"):
            ctx.blocked(
                "dto_sale_workday is not installed, so only two of the "
                "three gates exist and their ordering cannot be "
                "established.")

    try:
        with ctx.step("Step 1: a quotation that violates ALL THREE gates at "
                      "once — no requester email, no analytic "
                      "distribution, no Promised Ship Date"):
            product_id = ensure_product(ctx)
            order_id = make_quotation(
                ctx, order_type="project", label="MRO", requester=None,
                lines=[line_values(product_id, ship_date=None)])
            line_id = order_lines(rpc, order_id, ["id"])[0]["id"]

        messages = {}
        with ctx.step("Step 2: with all three violated, the FIRST message "
                      "names the gate that runs outermost"):
            _raised, messages["all_three"] = expect_error(confirm, rpc,
                                                          order_id)
            ctx.log(f"all three violated -> {messages['all_three']!r}")
            ctx.check_true(f"first gate is {REQUESTER_ERROR!r}",
                           REQUESTER_ERROR in messages["all_three"],
                           actual_desc=messages["all_three"])

        with ctx.step("Step 3: filling only the requester email reveals the "
                      "second gate"):
            rpc.write("sale.order", [order_id],
                      {"requester_email": "qa.wf002@example.invalid"})
            _raised, messages["two_left"] = expect_error(confirm, rpc,
                                                         order_id)
            ctx.log(f"two left -> {messages['two_left']!r}")
            ctx.check_true(f"second gate is {PROJECT_ERROR!r}",
                           PROJECT_ERROR in messages["two_left"],
                           actual_desc=messages["two_left"])

        with ctx.step("Step 4: adding a valid Project distribution reveals "
                      "the third"):
            project_account = ensure_analytic_account(rpc, plans["project"],
                                                      "Project MRO")
            rpc.write("sale.order.line", [line_id],
                      {"analytic_distribution":
                       _distribution(project_account)})
            _raised, messages["one_left"] = expect_error(confirm, rpc,
                                                         order_id)
            ctx.log(f"one left -> {messages['one_left']!r}")
            ctx.check_true(f"third gate is {SHIP_DATE_ERROR!r}",
                           SHIP_DATE_ERROR in messages["one_left"],
                           actual_desc=messages["one_left"])

        with ctx.step("Step 5: satisfying the last gate lets it confirm"):
            rpc.write("sale.order.line", [line_id],
                      {"requested_delivery_date": "2026-09-10"})
            confirm(rpc, order_id)
            ctx.check("state", "sale",
                      read_order(rpc, order_id, ["state"])["state"])

        with ctx.step("Step 6: the MRO order this proves"):
            ctx.log("dto_sale_workday (requester email) is outermost, then "
                    "dto_account (analytic plan), then dto_sale (promised "
                    "ship date) — matching WF-002 BR-1, which the workbook "
                    "marks Inferred. Reading type(env['sale.order']).__mro__ "
                    "literally is not possible over RPC (Odoo dispatches no "
                    "introspection endpoint); the peel-one-gate-at-a-time "
                    "sequence above establishes the same ordering "
                    "behaviourally.")
    finally:
        with ctx.step("Cleanup WF-002 fixtures"):
            try:
                sweep_wf002(rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")


@test_case(
    id="TEST-WF002-TC077",
    name="Multi-record confirm: one order without a requester email blocks "
         "all",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_sale_workday", priority="P1", kind="API", order=2077,
    description="action_confirm() over three orders where only the third "
                "lacks a requester email raises once and leaves ALL THREE "
                "draft with no stock moves — the guard uses any() over the "
                "whole recordset before super().",
    traceability=trace("DATAONE-TC077"))
def test_tc077(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-002 fixtures and open a fresh "
                  "namespace"):
        sweep_wf002(rpc)

    with ctx.step("Preconditions: dto_sale_workday installed, mail offline"):
        require_dto_sale(ctx)
        require_mail_offline(ctx)
        if not rpc.field_exists("sale.order", "requester_email"):
            ctx.blocked("dto_sale_workday is not installed — gate 1 does "
                        "not exist to be tested across a recordset.")

    try:
        with ctx.step("Steps 1-2: three quotations, of which only the third "
                      "lacks a requester email"):
            orders = [
                make_quotation(ctx, order_type="inventory", label="Multi1"),
                make_quotation(ctx, order_type="inventory", label="Multi2"),
                make_quotation(ctx, order_type="inventory", label="Multi3",
                               requester=None),
            ]
            emails = [read_order(rpc, o, ["requester_email"])["requester_email"]
                      for o in orders]
            ctx.log(f"requester emails: {emails!r}")
            ctx.check("only the third is missing its email", False,
                      emails[2])

        with ctx.step("Steps 3-4: confirming the three together raises the "
                      "exact message"):
            raised, message = expect_error(
                rpc.call, "sale.order", "action_confirm", orders)
            ctx.log(f"raised: {message!r}")
            ctx.check_true("the batch confirm was blocked", raised,
                           actual_desc=message)
            ctx.check_true(f"message is {REQUESTER_ERROR!r}",
                           REQUESTER_ERROR in message, actual_desc=message)

        with ctx.step("Step 5: ALL THREE are still draft — including the "
                      "two that were individually valid"):
            states = [read_order(rpc, o, ["state"])["state"] for o in orders]
            ctx.check("states after the blocked batch",
                      ["draft", "draft", "draft"], states)

        with ctx.step("Step 6: zero stock moves for all three"):
            counts = {o: _downstream_counts(rpc, o)["stock.move"]
                      for o in orders}
            ctx.check("stock moves per order",
                      {o: 0 for o in orders}, counts)
    finally:
        with ctx.step("Cleanup WF-002 fixtures"):
            try:
                sweep_wf002(rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")


@test_case(
    id="TEST-WF002-TC085",
    name="An empty memo raises TypeError and aborts the confirmation",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_sale", priority="P1", kind="API", order=2085,
    description="dto_sale's confirmation automation runs "
                "`if 'IRM' in order.memo_to_suppliers`; memo_to_suppliers "
                "is a Text field defaulting to False, so an empty memo "
                "raises TypeError from the server action, rolling the whole "
                "confirmation and its procurement back. A non-empty memo "
                "confirms.",
    traceability=trace("DATAONE-TC085"))
def test_tc085(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-002 fixtures and open a fresh "
                  "namespace"):
        sweep_wf002(rpc)

    with ctx.step("Preconditions: dto_sale installed, mail offline"):
        require_dto_sale(ctx)
        require_mail_offline(ctx)
        if not rpc.field_exists("sale.order", "memo_to_suppliers"):
            ctx.blocked(
                "sale.order.memo_to_suppliers does not exist on "
                f"{ctx.env.key} — dto_sale_workday is not installed, so the "
                "automation's `'IRM' in order.memo_to_suppliers` line "
                "cannot be reached.")

    try:
        with ctx.step("Steps 1-2: a fully valid quotation whose "
                      "memo_to_suppliers is EMPTY"):
            # memo=None OMITS the field so the Text field's own default
            # (False) applies. Writing "" does NOT produce False on either
            # version — Char/Text keep the empty string through
            # convert_to_cache (v17 odoo/fields.py:1985, v19
            # odoo/orm/fields_textual.py:107, where falsy_value = '' is now
            # explicit) — and `'IRM' in ''` is a clean False, so the whole
            # premise of this case (`'IRM' in False` -> TypeError) never
            # fires. The workbook's "EMPTY" means unset, not blank-string.
            order_id = make_quotation(ctx, order_type="inventory", memo=None,
                                      label="EmptyMemo")
            ctx.check("memo_to_suppliers", False,
                      read_order(rpc, order_id,
                                 ["memo_to_suppliers"])["memo_to_suppliers"])
            mails_before = rpc.call("mail.mail", "search_count", []) \
                if rpc.model_exists("mail.mail") else 0

        with ctx.step("Steps 3-4: Confirm raises a TypeError from the "
                      "server action — 'bool' is not iterable"):
            raised, message = expect_error(confirm, rpc, order_id)
            ctx.log(f"raised: {message!r}")
            ctx.check_true("confirmation aborted", raised,
                           actual_desc=message)
            ctx.check_true(
                "the message names a bool that is not iterable",
                "not iterable" in message and "bool" in message,
                actual_desc=message)

        with ctx.step("Step 5: the order is still draft — the automation "
                      "aborted the whole transaction"):
            ctx.check("state", "draft",
                      read_order(rpc, order_id, ["state"])["state"])

        with ctx.step("Step 6: the confirmation and its procurement were "
                      "rolled back — zero of every downstream record"):
            ctx.check("downstream record counts",
                      {"stock.move": 0, "mrp.production": 0,
                       "purchase.order": 0, "stock.picking": 0},
                      _downstream_counts(rpc, order_id))

        with ctx.step("Step 7: no outgoing email was produced"):
            mails_after = rpc.call("mail.mail", "search_count", []) \
                if rpc.model_exists("mail.mail") else 0
            ctx.check("mail.mail records created by the aborted confirm", 0,
                      mails_after - mails_before)

        with ctx.step("Step 8: a non-empty memo lets the order confirm, and "
                      "one outgoing mail is queued"):
            rpc.write("sale.order", [order_id],
                      {"memo_to_suppliers": fx(f"{MARK} memo")})
            confirm(rpc, order_id)
            ctx.check("state", "sale",
                      read_order(rpc, order_id, ["state"])["state"])
            mails_final = rpc.call("mail.mail", "search_count", []) \
                if rpc.model_exists("mail.mail") else 0
            ctx.log(f"mail.mail {mails_after} -> {mails_final}")
            # The QA clone has every mail server deactivated
            # (require_mail_offline), so the record is created and then
            # marked 'exception' when delivery fails. Its existence is what
            # proves the automation ran; delivery is deliberately impossible.
            ctx.check_true("the confirmation queued one outgoing mail",
                           mails_final > mails_after,
                           actual_desc=f"{mails_final - mails_after} "
                                       "mail.mail record(s) created")
    finally:
        with ctx.step("Cleanup WF-002 fixtures"):
            try:
                sweep_wf002(rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")
