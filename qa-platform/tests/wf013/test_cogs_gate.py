"""DATAONE-WF-013 — the two gates: TC221, TC222.

TC221 proves the ``skip_invoice_sync`` trick still works: the posted move
must carry **two** ``asset_receivable`` lines, equal and opposite, exactly
one of them ``is_cogs``. Odoo's default behaviour is to merge receivable
lines into one with a zero balance, and ``dto_account_cogs`` avoids that by
creating its reversal lines with ``skip_invoice_sync=True`` in context. One
merged line, or two lines with ``is_cogs`` false on both, is a FAIL even
though the invoice posted and was numbered.

TC222 is the highest-value test in the whole wave. ``dto_account_cogs``
overrides two hooks that Odoo 19 renamed and removed:

* ``_stock_account_prepare_anglo_saxon_out_lines_vals`` — v17
  ``stock_account/models/account_move.py:79``; on v19 the caller invokes
  ``_stock_account_prepare_realtime_out_lines_vals`` (:68) instead;
* ``_stock_account_get_anglo_saxon_price_unit`` — v17 ``:310`` and
  ``sale_stock:151``; **gone** on v19, replaced by ``_get_cogs_value()``
  under ``_get_anglo_saxon_price_ctx()`` (:122, :163).

Neither override raises on v19. They simply stop being called, and the
COGS/Interim analytic distribution and the project price basis vanish
**silently**. TC222 asserts four sentinels that only the overrides can
produce, so a dead override fails loudly instead.

EXPECTED v17 OUTCOME: PASS for both.
EXPECTED v19 OUTCOME: TC222 FAILS at sentinel 1 (the COGS basis reverts to
the FIFO cost) and sentinel 2 (the Interim distribution empties) until
``dto_account_cogs`` is ported to the new hook names. That failure IS the
finding.
"""
from framework.registry import test_case
from tests.wf013.common import (ANGLO_SAXON_HOOKS, MARK,  # noqa: F401
                                WORKFLOW, WORKFLOW_NAME,
                                accrued_revenue_account,
                                ensure_analytic_account, ensure_product, fx,
                                lines_by_account_type, m2o_id, move_lines,
                                realtime_category, require_anglo_saxon,
                                require_cogs_analytic_accounts,
                                require_cogs_stack, require_mail_offline,
                                sell_and_invoice, sweep_wf013, trace)

PROJECT_PLAN = "dto_account.project_analytic_plan"


def _accounts_in(distribution) -> set:
    """The analytic account ids named by a distribution map.

    The key is a comma-joined id list ("22,23": 100), which is exactly what
    ``_prepare_analytic_distribution`` produces.
    """
    result = set()
    for key in (distribution or {}):
        for part in str(key).split(","):
            part = part.strip()
            if part.isdigit():
                result.add(int(part))
    return result


def _hook_expectations(ctx):
    """The hook names this Odoo version actually calls."""
    return ANGLO_SAXON_HOOKS.get(ctx.env.version, ANGLO_SAXON_HOOKS["17"])


@test_case(
    id="TEST-WF013-TC221",
    name="GATE: skip_invoice_sync still produces two asset_receivable lines "
         "on v19",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account_cogs", priority="P0", kind="API", order=13221,
    description="One receivable line before posting, two after — equal and "
                "opposite, exactly one is_cogs; one display_type='cogs' "
                "revenue reversal; income nets to zero and the move "
                "balances.",
    traceability=trace("DATAONE-TC221"))
def test_tc221(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-013 fixtures and open a fresh "
                  "namespace"):
        sweep_wf013(rpc)

    with ctx.step("Preconditions: dto_account_cogs, anglo-saxon "
                  "accounting, the five analytic xmlids, mail offline"):
        require_cogs_stack(ctx)
        require_anglo_saxon(ctx)
        require_cogs_analytic_accounts(ctx)
        require_mail_offline(ctx)
        category = realtime_category(ctx)
        if category is None:
            ctx.blocked(
                "No product.category on this database uses real-time "
                "valuation. Without one the invoice produces no "
                "anglo-saxon COGS lines at all, and every assertion in "
                "this case would be vacuous.")
        ctx.log(f"valuation category: {category!r}")

    try:
        with ctx.step("Steps 1-2: sell and deliver a buy-type order, then "
                      "create its invoice WITHOUT posting"):
            product_id = ensure_product(ctx, price=10.0, cost=9.0,
                                        categ_id=category["id"])
            contract = ensure_analytic_account(
                rpc, "dto_account.customer_contract_analytic_plan",
                "Contract Gate")
            order_id, invoice_id = sell_and_invoice(
                ctx, order_type="buy",
                analytic={str(contract): 100},
                product_id=product_id, price=10.0, label="Gate221",
                post=False)

        with ctx.step("Step 3: the draft move carries exactly ONE "
                      "asset_receivable line"):
            grouped = lines_by_account_type(rpc, invoice_id)
            draft_ar = grouped.get("asset_receivable", [])
            ctx.log(f"draft receivable lines: {draft_ar!r}")
            ctx.check("asset_receivable lines before posting", 1,
                      len(draft_ar))

        with ctx.step("Step 4: post the invoice"):
            rpc.call("account.move", "action_post", [invoice_id])
            move = rpc.read("account.move", [invoice_id],
                            ["state", "name"])[0]
            ctx.log(f"posted move: {move!r}")
            ctx.check("move state", "posted", move["state"])

        with ctx.step("Steps 5-7 — THE GATE: two asset_receivable lines "
                      "after posting, not one merged line"):
            grouped = lines_by_account_type(rpc, invoice_id)
            ar = grouped.get("asset_receivable", [])
            ctx.log(f"posted receivable lines: {ar!r}")
            ctx.check("asset_receivable lines after posting", 2, len(ar))

        with ctx.step("Step 8: the two balances are equal and opposite"):
            balances = sorted(round(ln["balance"], 2) for ln in ar)
            ctx.check("receivable balances sum to zero", 0.0,
                      round(sum(balances), 2))
            ctx.check("receivable balances", [-10.0, 10.0], balances)

        with ctx.step("Step 9 — THE GATE: exactly ONE of the two is "
                      "is_cogs, not zero and not two"):
            ctx.check("is_cogs receivable lines", 1,
                      len([ln for ln in ar if ln["is_cogs"]]))

        with ctx.step("Step 10: the revenue reversal exists with "
                      "display_type 'cogs', is_cogs True and a 10.00 "
                      "debit"):
            reversal = [ln for ln in move_lines(rpc, invoice_id)
                        if ln["display_type"] == "cogs" and ln["is_cogs"]]
            ctx.log(f"revenue reversal lines: {reversal!r}")
            ctx.check("display_type='cogs' is_cogs lines", 1, len(reversal))
            ctx.check("revenue reversal debit", 10.0,
                      round(reversal[0]["debit"], 2))

        with ctx.step("Step 11: the income account nets to zero across the "
                      "whole move"):
            income = grouped.get("income", [])
            ctx.log(f"income lines: {income!r}")
            ctx.check("income net balance", 0.0,
                      round(sum(ln["balance"] for ln in income), 2))

        with ctx.step("Step 12: the move balances"):
            all_lines = move_lines(rpc, invoice_id)
            ctx.check("move net balance", 0.0,
                      round(sum(ln["balance"] for ln in all_lines), 2))
    finally:
        with ctx.step("Cleanup WF-013 fixtures"):
            try:
                sweep_wf013(rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")


@test_case(
    id="TEST-WF013-TC222",
    name="The renamed anglo-saxon hook override actually executes on v19",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account, dto_account_cogs", priority="P0", kind="API",
    order=13222,
    description="Four sentinels only the overrides can produce: the COGS "
                "basis at the sales price rather than the FIFO cost, the "
                "Interim distribution being exactly {Consumables, CC "
                "202000}, the COGS distribution merging the SO's Project "
                "account with Consumables, and neither distribution being "
                "empty. On v19 the two hooks were renamed and removed, so a "
                "dead override fails here instead of silently.",
    traceability=trace("DATAONE-TC222"))
def test_tc222(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-013 fixtures and open a fresh "
                  "namespace"):
        sweep_wf013(rpc)

    with ctx.step("Preconditions: dto_account_cogs, anglo-saxon "
                  "accounting, the five analytic xmlids, mail offline"):
        require_cogs_stack(ctx)
        require_anglo_saxon(ctx)
        refs = require_cogs_analytic_accounts(ctx)
        require_mail_offline(ctx)
        category = realtime_category(ctx)
        if category is None:
            ctx.blocked(
                "No product.category uses real-time valuation, so no "
                "anglo-saxon COGS/Interim pair is produced and the "
                "sentinels cannot be observed.")

    with ctx.step("Record which hook names THIS Odoo version calls — the "
                  "rename is the whole point of the case"):
        hooks = _hook_expectations(ctx)
        basis_hook = hooks["price_unit"] or (
            "_get_cogs_value (the v17 _stock_account_get_anglo_saxon_"
            "price_unit is gone)")
        ctx.log("Odoo {} calls {!r} for the out-lines hook and {!r} for the "
                "COGS basis.".format(ctx.env.version, hooks["prepare"],
                                     basis_hook))
        ctx.log("dto_account_cogs overrides the v17 names. On v19 those "
                "overrides are never called and fail SILENTLY — the "
                "sentinels below are what make that loud.")

    try:
        with ctx.step("Step 1: record the sentinel analytic accounts"):
            consumables = refs[
                "dto_account.analytic_account_spend_category_consumables"]
            cc202000 = refs[
                "dto_account.analytic_account_cost_center_202000"]
            ctx.log(f"Consumables={consumables}, CC202000={cc202000}")

        with ctx.step("Steps 2-3: sell, deliver and post a PROJECT order "
                      "whose line carries its own Project account"):
            product_id = ensure_product(ctx, price=10.0, cost=9.0,
                                        categ_id=category["id"])
            project_account = ensure_analytic_account(rpc, PROJECT_PLAN,
                                                      "Project 222")
            order_id, invoice_id = sell_and_invoice(
                ctx, order_type="project",
                analytic={str(project_account): 100},
                product_id=product_id, price=10.0, label="Hook222")
            ctx.check("move state", "posted",
                      rpc.read("account.move", [invoice_id],
                               ["state"])[0]["state"])

        with ctx.step("Steps 4-5: locate the COGS / Interim pair and split "
                      "it by sign"):
            pair = [ln for ln in move_lines(rpc, invoice_id)
                    if not ln["display_type"] and not ln["is_cogs"]
                    and (ln["debit"] or ln["credit"])]
            grouped = lines_by_account_type(rpc, invoice_id)
            account_types = {
                m2o_id(ln["account_id"]): key
                for key, lines in grouped.items() for ln in lines}
            pair = [ln for ln in pair
                    if account_types.get(m2o_id(ln["account_id"]))
                    not in ("income", "asset_receivable")]
            ctx.log(f"COGS/Interim candidates: {pair!r}")
            if len(pair) != 2:
                ctx.blocked(
                    f"Expected exactly one COGS/Interim pair, found "
                    f"{len(pair)}: {pair!r}. The anglo-saxon lines were "
                    "not produced on this database — check the product "
                    "category's valuation setting and the delivered "
                    "quantity before reading anything into the sentinels.")
            interim = [ln for ln in pair if ln["credit"] > 0][0]
            cogs = [ln for ln in pair if ln["debit"] > 0][0]
            ctx.log(f"interim={interim!r}; cogs={cogs!r}")

        with ctx.step("SENTINEL 1 — the basis override ran: the COGS debit "
                      "is the SALES price 10.00. A value of 9.00 is the "
                      "FIFO cost and means the override is dead"):
            ctx.check("COGS debit (sales-price basis for a project order)",
                      10.0, round(cogs["debit"], 2))

        with ctx.step("SENTINEL 2 — the analytic override ran: the Interim "
                      "distribution is EXACTLY {Consumables, CC 202000}, "
                      "and the SO line's own Project account is absent"):
            interim_accounts = _accounts_in(interim["analytic_distribution"])
            ctx.log(f"interim distribution: "
                    f"{interim['analytic_distribution']!r} -> "
                    f"{sorted(interim_accounts)}")
            ctx.check("Interim analytic accounts",
                      sorted({consumables, cc202000}),
                      sorted(interim_accounts))
            ctx.check_true(
                "the SO line's Project account is absent from Interim",
                project_account not in interim_accounts,
                actual_desc=sorted(interim_accounts))

        with ctx.step("SENTINEL 3 — the COGS-line merge order: the "
                      "distribution includes BOTH the SO line's Project "
                      "account and Consumables"):
            cogs_accounts = _accounts_in(cogs["analytic_distribution"])
            ctx.log(f"cogs distribution: "
                    f"{cogs['analytic_distribution']!r} -> "
                    f"{sorted(cogs_accounts)}")
            ctx.check("accounts missing from the COGS distribution", [],
                      [a for a in (project_account, consumables)
                       if a not in cogs_accounts])

        with ctx.step("SENTINEL 4 — neither distribution is empty. An "
                      "empty dict on either is the dead-override "
                      "signature"):
            ctx.check("empty analytic distributions", [],
                      [name for name, line in
                       (("interim", interim), ("cogs", cogs))
                       if not line["analytic_distribution"]])
    finally:
        with ctx.step("Cleanup WF-013 fixtures"):
            try:
                sweep_wf013(rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")
