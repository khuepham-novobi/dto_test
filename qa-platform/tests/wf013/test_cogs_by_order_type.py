"""DATAONE-WF-013 — the COGS basis and AR routing per order type:
TC223–TC227, TC233.

``dto_account_cogs`` branches on ``order_type`` in two places:

``AccountMoveLine._stock_account_get_anglo_saxon_price_unit``
(dto_account_cogs/models/account_move.py:229) sets the COGS basis —

* ``project``                    -> ``self.price_unit`` (the SALES price)
* ``inventory`` / ``cost_center`` -> ``0.0``
* anything else                   -> ``super()`` (the FIFO/AVCO cost)

``AccountMoveLine._compute_account_id`` (:206) redirects the receivable
account — any of ``project`` / ``inventory`` / ``cost_center`` on the move
sends the AR line to the ``12500`` Accrued Revenue account; a pure ``buy``
order keeps the partner's trade receivable.

Both are ``any(...)``/``in`` tests over **the whole move's** order types, so
a consolidated invoice spanning a project and a buy order applies the
project rule to every line — TC227, which the workbook flags as WF-013 Open
Question 7.

The four table cases share one parametrised body; each states its own
expectations. Amounts follow the module's own worked example: a product
sold at 10.00 with a cost of 9.00.

EXPECTED v17 OUTCOME: PASS.
EXPECTED v19 OUTCOME: FAIL — both branch points live in overrides of
methods Odoo 19 renamed or removed (see ``test_cogs_gate.py``), so the COGS
basis silently reverts to the FIFO cost for every order type. TC222 is the
case that names that finding.
"""
from framework.registry import test_case
from tests.wf013.common import (ACCRUED_REVENUE_CODE, MARK,  # noqa: F401
                                WORKFLOW, WORKFLOW_NAME,
                                accrued_revenue_account,
                                ensure_analytic_account, ensure_product,
                                lines_by_account_type, m2o_id, move_lines,
                                realtime_category, require_anglo_saxon,
                                require_cogs_analytic_accounts,
                                require_cogs_stack, require_mail_offline,
                                sell_and_invoice, sweep_wf013, trace)

PLANS = {
    "project": "dto_account.project_analytic_plan",
    "buy": "dto_account.customer_contract_analytic_plan",
}


def _prepare(ctx):
    """Shared preconditions for every table case."""
    rpc = ctx.adapter.rpc
    require_cogs_stack(ctx)
    require_anglo_saxon(ctx)
    require_cogs_analytic_accounts(ctx)
    require_mail_offline(ctx)
    category = realtime_category(ctx)
    if category is None:
        ctx.blocked(
            "No product.category uses real-time valuation on this "
            "database, so the invoice produces no anglo-saxon COGS lines "
            "and every assertion below would be vacuous.")
    return category


def _analytic_for(ctx, order_type):
    """The analytic distribution the confirmation gate requires.

    dto_account refuses a project order without a Project account and a buy
    order without a Customer Contract account, and refuses ANY distribution
    on inventory / cost_center orders.
    """
    if order_type not in PLANS:
        return None
    account = ensure_analytic_account(ctx.adapter.rpc, PLANS[order_type],
                                      f"{order_type.title()} Table")
    return {str(account): 100}, account


def _cogs_pair(ctx, invoice_id):
    """(cogs_line, interim_line) — the anglo-saxon pair, or (None, None)."""
    rpc = ctx.adapter.rpc
    grouped = lines_by_account_type(rpc, invoice_id)
    account_types = {m2o_id(ln["account_id"]): key
                     for key, lines in grouped.items() for ln in lines}
    pair = [ln for ln in move_lines(rpc, invoice_id)
            if not ln["display_type"] and not ln["is_cogs"]
            and account_types.get(m2o_id(ln["account_id"]))
            not in ("income", "asset_receivable")
            and (ln["debit"] or ln["credit"])]
    if len(pair) != 2:
        return None, None, pair
    cogs = next((ln for ln in pair if ln["debit"] > 0), None)
    interim = next((ln for ln in pair if ln["credit"] > 0), None)
    return cogs, interim, pair


def _table_case(ctx, order_type, expected_cogs_debit, expected_ar_code,
                label):
    """The shared body for TC223–TC226.

    ``expected_ar_code`` is ``None`` for "the partner's trade receivable,
    whatever it is" and a code string for the redirected 12500 account.
    """
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-013 fixtures and open a fresh "
                  "namespace"):
        sweep_wf013(rpc)

    with ctx.step("Preconditions: dto_account_cogs, anglo-saxon, the "
                  "analytic xmlids, a real-time valuation category, mail "
                  "offline"):
        category = _prepare(ctx)
        accrued = accrued_revenue_account(rpc)
        ctx.log(f"12500 Accrued Revenue: {accrued!r}")
        if expected_ar_code and accrued is None:
            ctx.blocked(
                "No asset_receivable account coded "
                f"{ACCRUED_REVENUE_CODE} exists on {ctx.env.key}. "
                f"dto_account_cogs redirects {order_type} receivable lines "
                "to it, and without the account the redirect silently "
                "no-ops (which is DATAONE-TC228's subject, not this "
                "case's).")

    with ctx.step(f"Sell, deliver and post an order_type = {order_type} "
                  "order at 10.00 with a cost of 9.00"):
        product_id = ensure_product(ctx, price=10.0, cost=9.0,
                                    categ_id=category["id"])
        analytic = _analytic_for(ctx, order_type)
        distribution = analytic[0] if analytic else None
        order_id, invoice_id = sell_and_invoice(
            ctx, order_type=order_type, analytic=distribution,
            product_id=product_id, price=10.0, label=label)
        lines = move_lines(rpc, invoice_id)
        ctx.log(f"posted lines: {lines!r}")
        ctx.check("move state", "posted",
                  rpc.read("account.move", [invoice_id],
                           ["state"])[0]["state"])

    grouped = lines_by_account_type(rpc, invoice_id)

    with ctx.step("The revenue reversal pair exists: one product line and "
                  "one display_type='cogs' is_cogs line on the income "
                  "account, netting to zero"):
        income = grouped.get("income", [])
        product_lines = [ln for ln in income
                         if ln["display_type"] == "product"]
        reversal = [ln for ln in income
                    if ln["display_type"] == "cogs" and ln["is_cogs"]]
        ctx.check("income product lines", 1, len(product_lines))
        ctx.check("income reversal lines", 1, len(reversal))
        ctx.check("income nets to zero", 0.0,
                  round(sum(ln["balance"] for ln in income), 2))

    with ctx.step("Both receivable lines exist, exactly one is_cogs, and "
                  "they net to zero"):
        ar = grouped.get("asset_receivable", [])
        ctx.check("asset_receivable lines", 2, len(ar))
        ctx.check("is_cogs receivable lines", 1,
                  len([ln for ln in ar if ln["is_cogs"]]))
        ctx.check("receivable nets to zero", 0.0,
                  round(sum(ln["balance"] for ln in ar), 2))

    with ctx.step("The receivable account is the one this order type "
                  "routes to"):
        codes = sorted({
            a["code"] for a in rpc.read(
                "account.account",
                sorted({m2o_id(ln["account_id"]) for ln in ar}), ["code"])})
        ctx.log(f"receivable account codes: {codes}")
        if expected_ar_code:
            ctx.check("receivable account codes", [expected_ar_code], codes)
        else:
            ctx.check_true(
                f"the receivable is NOT the redirected "
                f"{ACCRUED_REVENUE_CODE} account",
                ACCRUED_REVENUE_CODE not in codes, actual_desc=str(codes))

    with ctx.step("The COGS basis is the value this order type's rule "
                  "produces"):
        cogs, interim, pair = _cogs_pair(ctx, invoice_id)
        ctx.log(f"anglo-saxon pair: {pair!r}")
        if expected_cogs_debit == 0.0:
            # inventory / cost_center set the basis to 0.0, so the pair may
            # be emitted at zero or suppressed entirely — TC233 is the case
            # that decides which, and it records the answer rather than
            # assuming it.
            debits = [round(ln["debit"], 2) for ln in pair]
            ctx.check("COGS/Interim debits at a zero basis",
                      [0.0] * len(pair), debits)
        else:
            ctx.check_true("the anglo-saxon pair was produced",
                           cogs is not None and interim is not None,
                           actual_desc=repr(pair))
            ctx.check("COGS debit", expected_cogs_debit,
                      round(cogs["debit"], 2))
            ctx.check("Interim credit", expected_cogs_debit,
                      round(interim["credit"], 2))

    with ctx.step("The move balances"):
        all_lines = move_lines(rpc, invoice_id)
        ctx.check("move net balance", 0.0,
                  round(sum(ln["balance"] for ln in all_lines), 2))
        ctx.log(f"total debit {round(sum(ln['debit'] for ln in all_lines), 2)}"
                f" / credit "
                f"{round(sum(ln['credit'] for ln in all_lines), 2)}")
    return invoice_id


@test_case(
    id="TEST-WF013-TC223",
    name="COGS and revenue reversal, order_type = buy (Table A)",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account, dto_account_cogs, dto_sale", priority="P0",
    kind="API", order=13223,
    description="A buy order keeps the partner's trade receivable (NOT "
                "12500) and takes the standard FIFO/AVCO cost of 9.00 as "
                "the COGS basis, with the revenue and receivable reversal "
                "pair on top.",
    traceability=trace("DATAONE-TC223"))
def test_tc223(ctx):
    try:
        _table_case(ctx, "buy", expected_cogs_debit=9.0,
                    expected_ar_code=None, label="TableA")
    finally:
        with ctx.step("Cleanup WF-013 fixtures"):
            try:
                sweep_wf013(ctx.adapter.rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")


@test_case(
    id="TEST-WF013-TC224",
    name="COGS and revenue reversal, order_type = project (Table B)",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account, dto_account_cogs", priority="P0", kind="API",
    order=13224,
    description="A project order redirects the receivable to 12500 Accrued "
                "Revenue and takes the SALES price of 10.00 as the COGS "
                "basis, not the 9.00 cost.",
    traceability=trace("DATAONE-TC224"))
def test_tc224(ctx):
    try:
        _table_case(ctx, "project", expected_cogs_debit=10.0,
                    expected_ar_code=ACCRUED_REVENUE_CODE, label="TableB")
    finally:
        with ctx.step("Cleanup WF-013 fixtures"):
            try:
                sweep_wf013(ctx.adapter.rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")


@test_case(
    id="TEST-WF013-TC225",
    name="COGS and revenue reversal, order_type = inventory (Table C)",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account, dto_account_cogs", priority="P0", kind="API",
    order=13225,
    description="An inventory order redirects the receivable to 12500 and "
                "sets the COGS basis to 0.00 — no stock relief is booked "
                "through the invoice at all.",
    traceability=trace("DATAONE-TC225"))
def test_tc225(ctx):
    try:
        _table_case(ctx, "inventory", expected_cogs_debit=0.0,
                    expected_ar_code=ACCRUED_REVENUE_CODE, label="TableC")
    finally:
        with ctx.step("Cleanup WF-013 fixtures"):
            try:
                sweep_wf013(ctx.adapter.rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")


@test_case(
    id="TEST-WF013-TC226",
    name="COGS and revenue reversal, order_type = cost_center (Table D)",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account, dto_account_cogs, dto_sale", priority="P0",
    kind="API", order=13226,
    description="cost_center behaves identically to inventory: the "
                "receivable is redirected to 12500 and the COGS basis is "
                "0.00.",
    traceability=trace("DATAONE-TC226"))
def test_tc226(ctx):
    try:
        _table_case(ctx, "cost_center", expected_cogs_debit=0.0,
                    expected_ar_code=ACCRUED_REVENUE_CODE, label="TableD")
    finally:
        with ctx.step("Cleanup WF-013 fixtures"):
            try:
                sweep_wf013(ctx.adapter.rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")


@test_case(
    id="TEST-WF013-TC227",
    name="Consolidated invoice spanning project and buy — the project "
         "branch wins per move",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account_cogs", priority="P0", kind="API", order=13227,
    description="Both branch points test the WHOLE move's order types, so "
                "a consolidated invoice applies the project rule to the buy "
                "order's line too: the receivable goes to 12500 and BOTH "
                "COGS lines take the sales-price basis. WF-013 Open "
                "Question 7.",
    traceability=trace("DATAONE-TC227"))
def test_tc227(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-013 fixtures and open a fresh "
                  "namespace"):
        sweep_wf013(rpc)

    with ctx.step("Preconditions, plus the 12500 account the redirect "
                  "targets"):
        category = _prepare(ctx)
        accrued = accrued_revenue_account(rpc)
        if accrued is None:
            ctx.blocked(
                f"No asset_receivable account coded {ACCRUED_REVENUE_CODE} "
                "exists, so the per-move redirect this case is about "
                "cannot be observed.")

    try:
        with ctx.step("Steps 1-2: build a project order and a buy order for "
                      "the SAME customer and invoice them together"):
            from framework.dto_fixtures import (create_invoice,
                                                deliver_order, set_stock)
            from tests.wf013.common import ensure_partner, make_sale_order
            partner_id = ensure_partner(rpc, "Consolidated")
            product_id = ensure_product(ctx, price=10.0, cost=9.0,
                                        categ_id=category["id"])
            set_stock(ctx, product_id, 100.0)

            project_account = ensure_analytic_account(
                rpc, PLANS["project"], "Project 227")
            contract_account = ensure_analytic_account(
                rpc, PLANS["buy"], "Contract 227")
            order_ids = []
            for order_type, account in (("project", project_account),
                                        ("buy", contract_account)):
                order_id = make_sale_order(
                    ctx, order_type=order_type,
                    analytic={str(account): 100}, qty=1.0, price=10.0,
                    product_id=product_id, label=f"Cons{order_type}",
                    partner_id=partner_id)
                rpc.call("sale.order", "action_confirm", [order_id])
                deliver_order(ctx, order_id)
                order_ids.append(order_id)

            wizard_id = rpc.call(
                "sale.advance.payment.inv", "create",
                {"advance_payment_method": "delivered"},
                context={"active_model": "sale.order",
                         "active_ids": order_ids,
                         "active_id": order_ids[0]})
            rpc.call("sale.advance.payment.inv", "create_invoices",
                     [wizard_id],
                     context={"active_model": "sale.order",
                              "active_ids": order_ids,
                              "active_id": order_ids[0]})
            invoices = set()
            for order_id in order_ids:
                invoices.update(rpc.read("sale.order", [order_id],
                                         ["invoice_ids"])[0]["invoice_ids"])
            ctx.log(f"invoices produced: {sorted(invoices)}")
            if len(invoices) != 1:
                ctx.skip(
                    "Odoo split the two orders into "
                    f"{len(invoices)} separate invoices on this database "
                    "rather than consolidating them, so the "
                    "per-move-versus-per-line question this case asks does "
                    "not arise here. Recorded as N/A, exactly as the "
                    "workbook's step 2 instructs.")
            invoice_id = sorted(invoices)[0]

        with ctx.step("Step 3: the single move spans both order types"):
            order_types = sorted(
                rpc.read("sale.order", order_ids, ["order_type"])[i]
                ["order_type"] for i in range(len(order_ids)))
            ctx.check("order types on the consolidated move",
                      ["buy", "project"], order_types)

        with ctx.step("Step 4: BEFORE posting, the single receivable line "
                      "is already on 12500 — the redirect fires because "
                      "'project' is in the list"):
            grouped = lines_by_account_type(rpc, invoice_id)
            draft_ar = grouped.get("asset_receivable", [])
            codes = sorted({
                a["code"] for a in rpc.read(
                    "account.account",
                    sorted({m2o_id(ln["account_id"]) for ln in draft_ar}),
                    ["code"])})
            ctx.log(f"draft receivable codes: {codes}")
            ctx.check("draft receivable account codes",
                      [ACCRUED_REVENUE_CODE], codes)

        with ctx.step("Step 5: post the consolidated invoice"):
            rpc.write("account.move", [invoice_id],
                      {"invoice_date": "2026-01-15"})
            rpc.call("account.move", "action_post", [invoice_id])
            ctx.check("move state", "posted",
                      rpc.read("account.move", [invoice_id],
                               ["state"])[0]["state"])

        with ctx.step("Steps 7-8: BOTH COGS lines take the sales-price "
                      "basis of 10.00 — including the one that came from "
                      "the buy order, which has nothing to do with the "
                      "project"):
            cogs, interim, pair = _cogs_pair(ctx, invoice_id)
            ctx.log(f"anglo-saxon lines: {pair!r}")
            debits = sorted(round(ln["debit"], 2) for ln in pair
                            if ln["debit"] > 0)
            ctx.check("COGS debits on the consolidated move", [10.0, 10.0],
                      debits)

        with ctx.step("Step 9: both receivable lines are on 12500 and "
                      "neither is on the trade receivable"):
            ar = lines_by_account_type(rpc, invoice_id).get(
                "asset_receivable", [])
            codes = sorted({
                a["code"] for a in rpc.read(
                    "account.account",
                    sorted({m2o_id(ln["account_id"]) for ln in ar}),
                    ["code"])})
            ctx.check("posted receivable account codes",
                      [ACCRUED_REVENUE_CODE], codes)
            ctx.check("asset_receivable lines", 2, len(ar))

        with ctx.step("Step 10: total Interim relief is 20.00 against a "
                      "delivery debit of 18.00 — a 2.00 residue"):
            interim_credit = round(sum(ln["credit"] for ln in pair), 2)
            ctx.log(f"total Interim relief: {interim_credit}")
            ctx.check("Interim relief on the consolidated move", 20.0,
                      interim_credit)
            ctx.log("The delivery debited Interim at cost (2 x 9.00 = "
                    "18.00), so relieving 20.00 leaves a 2.00 residue on "
                    "the Stock Interim account — WF-013 Open Question 7, "
                    "recorded here for the decision matrix.")
    finally:
        with ctx.step("Cleanup WF-013 fixtures"):
            try:
                sweep_wf013(rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")


@test_case(
    id="TEST-WF013-TC233",
    name="Are zero-value COGS / Interim lines emitted on inventory orders?",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account, dto_account_cogs", priority="P1", kind="DATA",
    order=13233,
    description="With the COGS basis forced to 0.00, records whether Odoo "
                "still emits the COGS/Interim pair at zero or suppresses "
                "it entirely — the answer decides whether downstream "
                "reports see zero rows or no rows.",
    traceability=trace("DATAONE-TC233"))
def test_tc233(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-013 fixtures and open a fresh "
                  "namespace"):
        sweep_wf013(rpc)

    with ctx.step("Preconditions"):
        category = _prepare(ctx)

    try:
        with ctx.step("Sell, deliver and post an inventory order — its "
                      "COGS basis is forced to 0.00"):
            product_id = ensure_product(ctx, price=10.0, cost=9.0,
                                        categ_id=category["id"])
            order_id, invoice_id = sell_and_invoice(
                ctx, order_type="inventory", product_id=product_id,
                price=10.0, label="ZeroCogs")

        with ctx.step("Record the shape: how many COGS/Interim lines exist "
                      "and what they carry"):
            cogs, interim, pair = _cogs_pair(ctx, invoice_id)
            ctx.log(f"anglo-saxon lines on a zero-basis order: {pair!r}")
            emitted = len(pair)
            ctx.log(f"=> Odoo {'EMITS' if emitted else 'SUPPRESSES'} the "
                    f"COGS/Interim pair at a zero basis ({emitted} line(s))")

        with ctx.step("Whatever the shape, no VALUE was booked — every "
                      "anglo-saxon line is zero"):
            nonzero = [ln for ln in pair
                       if round(ln["debit"], 2) or round(ln["credit"], 2)]
            ctx.check("non-zero COGS/Interim lines on an inventory order",
                      [], nonzero)

        with ctx.step("The revenue reversal is unaffected — it does not "
                      "depend on the COGS basis"):
            grouped = lines_by_account_type(rpc, invoice_id)
            income = grouped.get("income", [])
            ctx.check("income nets to zero", 0.0,
                      round(sum(ln["balance"] for ln in income), 2))
            ctx.check("income reversal lines", 1,
                      len([ln for ln in income
                           if ln["display_type"] == "cogs"]))

        with ctx.step("The move balances"):
            all_lines = move_lines(rpc, invoice_id)
            ctx.check("move net balance", 0.0,
                      round(sum(ln["balance"] for ln in all_lines), 2))
    finally:
        with ctx.step("Cleanup WF-013 fixtures"):
            try:
                sweep_wf013(rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")
