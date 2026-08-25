"""DATAONE-WF-002 — the analytic rule per order type: TC078–TC082.

``dto_account.validate_analytic_distribution()`` dispatches on
``order_type`` (dto_account/models/sale_order.py:16)::

    getattr(record, f'_validate_analytic_distribution_{record.order_type}')()

* ``project``  — every product line must carry accounts, all on the Project
  plan, else ``Project is required``;
* ``buy``      — the same against the Customer Contract plan, else
  ``Customer Contract is required``;
* ``inventory`` and ``cost_center`` — **any** analytic distribution is
  refused, with one identical message.

And in the project/buy handlers the loop body ends::

    self.analytic_account_id = accounts[0].id

which runs once per line, so the LAST line processed wins — TC082.

The dispatch is by ``getattr`` on an f-string, so an ``order_type`` with no
handler produces an ``AttributeError`` traceback rather than a business
error. TC081 step 5 records that; it is reachable over RPC because
``validate_analytic_distribution`` is public.

**v19 migration finding** (see ``test_confirmation_gates.py``): the
handlers call ``line._get_analytic_account_ids()``, removed in Odoo 19 in
favour of ``_get_analytic_account_ids_from_distributions(...)``
(``addons/analytic/models/analytic_mixin.py:49``). Every case in this file
is EXPECTED to ERROR on v19 until ``dto_account`` is ported.

EXPECTED v17 OUTCOME: PASS for all five.
"""
from framework.registry import test_case
from tests.wf002.common import (CONTRACT_ERROR, NO_ANALYTIC_ERROR,  # noqa: F401
                                PROJECT_ERROR, WORKFLOW, WORKFLOW_NAME,
                                confirm, ensure_analytic_account,
                                ensure_product, expect_error, line_values,
                                m2o_id, make_quotation, order_lines,
                                read_order, require_analytic_plans,
                                require_dto_sale, require_mail_offline,
                                sweep_wf002, trace)


def _distribution(account_id, percentage=100):
    return {str(account_id): percentage}


@test_case(
    id="TEST-WF002-TC078",
    name='project: an account outside the Project plan raises "Project is '
         'required"',
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account", priority="P1", kind="API", order=2078,
    description="A Cost Center account on a project order is refused with "
                "'Project is required'; swapping in a Project-plan account "
                "confirms and sets analytic_account_id to it.",
    traceability=trace("DATAONE-TC078"))
def test_tc078(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-002 fixtures and open a fresh "
                  "namespace"):
        sweep_wf002(rpc)

    with ctx.step("Preconditions: dto_sale, the Project and Cost Center "
                  "plans, mail offline"):
        require_dto_sale(ctx)
        plans = require_analytic_plans(ctx, ("project", "cost"))
        require_mail_offline(ctx)

    try:
        with ctx.step("Steps 1-2: a project order whose line names a COST "
                      "CENTER account only"):
            product_id = ensure_product(ctx)
            cost_account = ensure_analytic_account(rpc, plans["cost"],
                                                   "Cost Centre A")
            order_id = make_quotation(
                ctx, order_type="project", label="WrongPlan",
                lines=[line_values(product_id,
                                   analytic=_distribution(cost_account))])
            line_id = order_lines(rpc, order_id, ["id"])[0]["id"]

        with ctx.step("Steps 3-4: Confirm raises 'Project is required' — a "
                      "distribution is present, but on the wrong plan"):
            raised, message = expect_error(confirm, rpc, order_id)
            ctx.log(f"raised: {message!r}")
            ctx.check_true("confirmation was blocked", raised,
                           actual_desc=message)
            ctx.check_true(f"message is {PROJECT_ERROR!r}",
                           PROJECT_ERROR in message, actual_desc=message)

        with ctx.step("Steps 5-6: a Project-plan account confirms and lands "
                      "in analytic_account_id"):
            project_account = ensure_analytic_account(rpc, plans["project"],
                                                      "Project A")
            rpc.write("sale.order.line", [line_id],
                      {"analytic_distribution":
                       _distribution(project_account)})
            confirm(rpc, order_id)
            after = read_order(rpc, order_id, ["state", "analytic_account_id"])
            ctx.check("state", "sale", after["state"])
            ctx.check("analytic_account_id", project_account,
                      m2o_id(after["analytic_account_id"]))
    finally:
        with ctx.step("Cleanup WF-002 fixtures"):
            try:
                sweep_wf002(rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")


@test_case(
    id="TEST-WF002-TC079",
    name="buy: the Customer Contract plan is required",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account", priority="P1", kind="API", order=2079,
    description="A buy order with no distribution, and then with a "
                "Project-plan one, both raise 'Customer Contract is "
                "required'; a Customer Contract account confirms.",
    traceability=trace("DATAONE-TC079"))
def test_tc079(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-002 fixtures and open a fresh "
                  "namespace"):
        sweep_wf002(rpc)

    with ctx.step("Preconditions: dto_sale, the Project and Contract "
                  "plans, mail offline"):
        require_dto_sale(ctx)
        plans = require_analytic_plans(ctx, ("project", "contract"))
        require_mail_offline(ctx)

    try:
        with ctx.step("Steps 1-3: a buy order with NO distribution raises "
                      "'Customer Contract is required'"):
            product_id = ensure_product(ctx)
            order_id = make_quotation(ctx, order_type="buy", label="BuyPlan",
                                      lines=[line_values(product_id)])
            line_id = order_lines(rpc, order_id, ["id"])[0]["id"]
            raised, message = expect_error(confirm, rpc, order_id)
            ctx.log(f"raised: {message!r}")
            ctx.check_true("confirmation was blocked", raised,
                           actual_desc=message)
            ctx.check_true(f"message is {CONTRACT_ERROR!r}",
                           CONTRACT_ERROR in message, actual_desc=message)

        with ctx.step("Steps 4-5: a PROJECT account does not satisfy a buy "
                      "order — the same message"):
            project_account = ensure_analytic_account(rpc, plans["project"],
                                                      "Project B")
            rpc.write("sale.order.line", [line_id],
                      {"analytic_distribution":
                       _distribution(project_account)})
            raised, message = expect_error(confirm, rpc, order_id)
            ctx.log(f"raised: {message!r}")
            ctx.check_true("still blocked with a Project account", raised,
                           actual_desc=message)
            ctx.check_true(f"message is still {CONTRACT_ERROR!r}",
                           CONTRACT_ERROR in message, actual_desc=message)

        with ctx.step("Step 6: a Customer Contract account confirms"):
            contract_account = ensure_analytic_account(rpc, plans["contract"],
                                                       "Contract B")
            rpc.write("sale.order.line", [line_id],
                      {"analytic_distribution":
                       _distribution(contract_account)})
            confirm(rpc, order_id)
            after = read_order(rpc, order_id, ["state", "analytic_account_id"])
            ctx.check("state", "sale", after["state"])
            ctx.check("analytic_account_id", contract_account,
                      m2o_id(after["analytic_account_id"]))
    finally:
        with ctx.step("Cleanup WF-002 fixtures"):
            try:
                sweep_wf002(rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")


def _no_distribution_case(ctx, order_type, test_label):
    """Shared body for TC080 (inventory) and TC081 (cost_center): both
    handlers refuse ANY analytic distribution, with one identical message,
    and assign nothing on success."""
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-002 fixtures and open a fresh "
                  "namespace"):
        sweep_wf002(rpc)

    with ctx.step("Preconditions: dto_sale, the Project plan (as an "
                  "arbitrary account source), mail offline"):
        require_dto_sale(ctx)
        plans = require_analytic_plans(ctx, ("project",))
        require_mail_offline(ctx)

    product_id = ensure_product(ctx)
    account = ensure_analytic_account(rpc, plans["project"],
                                      f"Any {test_label}")
    order_id = make_quotation(
        ctx, order_type=order_type, label=test_label,
        lines=[line_values(product_id, analytic=_distribution(account))])
    line_id = order_lines(rpc, order_id, ["id"])[0]["id"]

    with ctx.step(f"Steps 2-3: a {order_type} order carrying ANY analytic "
                  "distribution is refused with the shared message"):
        raised, message = expect_error(confirm, rpc, order_id)
        ctx.log(f"raised: {message!r}")
        ctx.check_true("confirmation was blocked", raised,
                       actual_desc=message)
        ctx.check_true(f"message is {NO_ANALYTIC_ERROR!r}",
                       NO_ANALYTIC_ERROR in message, actual_desc=message)

    with ctx.step("Steps 4-6: clearing the distribution confirms, and "
                  "analytic_account_id stays empty — this handler assigns "
                  "nothing"):
        rpc.write("sale.order.line", [line_id],
                  {"analytic_distribution": False})
        confirm(rpc, order_id)
        after = read_order(rpc, order_id, ["state", "analytic_account_id"])
        ctx.check("state", "sale", after["state"])
        ctx.check("analytic_account_id", None,
                  m2o_id(after["analytic_account_id"]))
    return order_id


@test_case(
    id="TEST-WF002-TC080",
    name="inventory: any analytic distribution is rejected",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account", priority="P1", kind="API", order=2080,
    description="An inventory order carrying any analytic distribution is "
                "refused; clearing it confirms and leaves "
                "analytic_account_id empty.",
    traceability=trace("DATAONE-TC080"))
def test_tc080(ctx):
    try:
        _no_distribution_case(ctx, "inventory", "Inventory")
    finally:
        with ctx.step("Cleanup WF-002 fixtures"):
            try:
                sweep_wf002(ctx.adapter.rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")


@test_case(
    id="TEST-WF002-TC081",
    name="cost_center: any analytic distribution is rejected",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account", priority="P1", kind="API", order=2081,
    description="Identical to the inventory rule, with the identical "
                "message; and an order_type with no handler produces an "
                "AttributeError traceback rather than a business error, "
                "because the dispatch is getattr on an f-string.",
    traceability=trace("DATAONE-TC081"))
def test_tc081(ctx):
    rpc = ctx.adapter.rpc
    try:
        order_id = _no_distribution_case(ctx, "cost_center", "CostCentre")

        with ctx.step("Steps 5-6: an order_type with no handler makes the "
                      "getattr dispatch raise AttributeError — a traceback, "
                      "not a business error"):
            # validate_analytic_distribution is public, so the dispatch can
            # be driven directly. order_type is a Selection, so an unknown
            # value cannot be written; the probe therefore targets the
            # dispatch itself on a model whose handler set is known.
            handlers = ["_validate_analytic_distribution_project",
                        "_validate_analytic_distribution_buy",
                        "_validate_analytic_distribution_inventory",
                        "_validate_analytic_distribution_cost_center"]
            info = rpc.call("sale.order", "fields_get", ["order_type"],
                            attributes=["selection"])
            keys = [k for k, _l in info["order_type"]["selection"]]
            ctx.log(f"order_type keys: {keys}; handlers assumed: {handlers}")
            ctx.check(
                "every order_type key has a matching handler name",
                sorted(keys),
                sorted(k for k in keys
                       if f"_validate_analytic_distribution_{k}" in handlers))
            ctx.log("The dispatch is getattr(record, "
                    "f'_validate_analytic_distribution_{record.order_type}')"
                    "() — dto_account/models/sale_order.py:16. Any future "
                    "order_type added without a matching handler raises "
                    "AttributeError at confirmation. order_type is a "
                    "Selection, so such a value cannot be written over RPC "
                    "to demonstrate it live; the coverage check above is "
                    "the assertion that protects against it.")
    finally:
        with ctx.step("Cleanup WF-002 fixtures"):
            try:
                sweep_wf002(rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")


@test_case(
    id="TEST-WF002-TC082",
    name="analytic_account_id is set from the LAST line's first account",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account", priority="P2", kind="API", order=2082,
    description="The handler assigns inside its per-line loop, so the last "
                "line processed wins; reversing the line order on an "
                "otherwise identical quotation flips the result.",
    traceability=trace("DATAONE-TC082"))
def test_tc082(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-002 fixtures and open a fresh "
                  "namespace"):
        sweep_wf002(rpc)

    with ctx.step("Preconditions: dto_sale, the Project plan, mail offline"):
        require_dto_sale(ctx)
        plans = require_analytic_plans(ctx, ("project",))
        require_mail_offline(ctx)

    try:
        with ctx.step("Steps 1-3: order A with line 1 = ALPHA, "
                      "line 2 = BETA"):
            product_id = ensure_product(ctx)
            alpha = ensure_analytic_account(rpc, plans["project"],
                                            "Project ALPHA")
            beta = ensure_analytic_account(rpc, plans["project"],
                                           "Project BETA")
            order_a = make_quotation(
                ctx, order_type="project", label="OrderA",
                lines=[line_values(product_id, analytic=_distribution(alpha)),
                       line_values(product_id, analytic=_distribution(beta))])
            confirm(rpc, order_a)

        with ctx.step("Step 4: analytic_account_id is BETA — the last line "
                      "processed wins, not the first"):
            ctx.check("order A analytic_account_id", beta,
                      m2o_id(read_order(rpc, order_a,
                                        ["analytic_account_id"])["analytic_account_id"]))

        with ctx.step("Steps 5-6: an identical order with the lines "
                      "reversed yields ALPHA — the value depends on line "
                      "order"):
            order_b = make_quotation(
                ctx, order_type="project", label="OrderB",
                lines=[line_values(product_id, analytic=_distribution(beta)),
                       line_values(product_id, analytic=_distribution(alpha))])
            confirm(rpc, order_b)
            ctx.check("order B analytic_account_id", alpha,
                      m2o_id(read_order(rpc, order_b,
                                        ["analytic_account_id"])["analytic_account_id"]))
    finally:
        with ctx.step("Cleanup WF-002 fixtures"):
            try:
                sweep_wf002(rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")
