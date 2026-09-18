"""DATAONE-WF-016 — analytic derivation: TC284 and TC285.

Finance never re-keys analytics on a derived document. A vendor bill line
built from a purchase order inherits the buyer's coding, blended with the
firm's standing distribution rules — and the RULE wins where the two
collide. That precedence is the opposite of what most users expect (a
standing rule silently overriding an explicit, user-entered purchase-order
coding) and it is surfaced nowhere in the interface, which is exactly why
it has to be pinned by a test before the port can invert it.

Verified source (``dto_account/models/account_move.py:280-306``)::

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        for line in lines:
            if line.purchase_line_id.analytic_distribution:
                distribution = line.prepare_analytic_distribution(
                    line.product_id, line.account_id, line.company_id,
                    line.purchase_line_id.analytic_distribution)
                line.analytic_distribution = distribution
            elif line.sale_line_ids.analytic_distribution:
                ...

and the blend itself (``:192-250``), which calls the private core
``account.analytic.distribution.model._get_distribution(field_values)``
with ``product_categ_id``, ``account_prefix`` and ``company_id``.

Why the comparison is by resolved ACCOUNT SET
---------------------------------------------
DataOne encodes multi-plan distributions as comma-joined ids
(``{"22,23,24": 100}``). Delta §2.14 leaves the v19 key format an open
Unknown, and the ported ``prepare_analytic_distribution`` now routes
through core's plan-aware ``_merge_distribution`` with an ``__update__``
directive. A *shape* change is expected; a *value* change is a defect. So
every assertion here compares the resolved analytic-account ids and their
plans, never the raw key string — that raw-string comparison is a separate
reconciliation case (the workbook's TC259, owned elsewhere). The raw keys
ARE logged, so the shape change is recorded rather than lost.

Two silent v19 failure modes both land here
-------------------------------------------
1. ``_get_distribution``'s ``field_values`` keys are a private contract. If
   they changed, it returns ``{}`` and every derived line silently falls
   back to the raw source distribution — which INVERTS TC285's precedence
   with no error anywhere.
2. §2.3/§2.4 reworked invoice-line synchronisation, so F152's
   unconditional post-create write into ``analytic_distribution`` now races
   the new computed/inverse machinery.

Neither raises. Both land in Workday columns GG and GK.

EXPECTED v17 OUTCOME: PASS for both.
EXPECTED v19 OUTCOME: TC285 is the one to watch. A result equal to AD-PO
means the rule returned ``{}`` and the precedence inverted.
"""
from framework.registry import test_case
from tests.wf016.common import (MARK, WORKFLOW, WORKFLOW_NAME,  # noqa: F401
                                any_analytic_plan, bill_from_order,
                                company_id, distribution_accounts,
                                ensure_analytic_account, ensure_category,
                                ensure_product, ensure_vendor, expect_error,
                                fx, m2o_id, make_purchase_order, move_lines,
                                plan_of, receive_order, require_dto_account,
                                require_purchase, sweep_wf016, trace)

# DataOne's own plans, preferred so the fixture matches production shape.
SPEND_PLAN = "dto_account.spend_category_analytic_plan"
COST_CENTER_PLAN = "dto_account.cost_center_analytic_plan"


def _two_plans(ctx):
    """Two distinct analytic plan ids, preferring DataOne's own.

    Falls back to whatever plans the database has, because the assertions
    are about PRECEDENCE, not about which plan is involved — but the
    substitution is logged, because a single-plan database cannot express
    a collision at all.
    """
    rpc = ctx.adapter.rpc
    preferred = [rpc.ref(SPEND_PLAN), rpc.ref(COST_CENTER_PLAN)]
    resolved = [p for p in preferred if p]
    if len(resolved) == 2:
        return resolved, [SPEND_PLAN, COST_CENTER_PLAN]
    rows = any_analytic_plan(rpc)
    ctx.log(f"[note] DataOne's own analytic plans did not both resolve "
            f"({SPEND_PLAN}={preferred[0]}, {COST_CENTER_PLAN}="
            f"{preferred[1]}); falling back to {rows!r}.")
    if len(rows) < 2:
        ctx.blocked(
            f"Fewer than two analytic plans exist on {ctx.env.key}, so a "
            "colliding-plan distribution cannot be constructed and "
            "TC284/TC285 would assert nothing about precedence.")
    return [r["id"] for r in rows[:2]], [r["name"] for r in rows[:2]]


def _account_on_plan(rpc, plan_id, label):
    name = fx(f"{MARK} {label}")
    found = rpc.search("account.analytic.account",
                       [("name", "=", name), ("plan_id", "=", plan_id)],
                       limit=1)
    if found:
        return found[0]
    return rpc.create("account.analytic.account",
                      {"name": name, "plan_id": plan_id})


def _bill_line(rpc, bill_id):
    """The single product line of a derived bill."""
    lines = [ln for ln in move_lines(rpc, bill_id)
             if ln.get("product_id") and ln.get("display_type")
             in (False, "product")]
    return lines[0] if lines else None


@test_case(
    id="TEST-WF016-TC284",
    name="A bill line inherits the purchase line's analytic distribution "
         "at create",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account", priority="P0", kind="API", order=16284,
    description="With no distribution-model rule matching, a bill line "
                "created from a purchase order resolves to exactly the PO "
                "line's analytic accounts, carries purchase_line_id, and a "
                "manually added line with no purchase_line_id gets only "
                "what the rule model supplies.",
    traceability=trace("DATAONE-TC284"))
def test_tc284(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-016 fixtures and open a fresh "
                  "namespace"):
        sweep_wf016(rpc)

    with ctx.step("Preconditions: dto_account and purchase installed, two "
                  "analytic plans available"):
        require_dto_account(ctx)
        require_purchase(ctx)
        plan_ids, plan_names = _two_plans(ctx)
        ctx.log(f"plans in use: {list(zip(plan_names, plan_ids))}")
        comp_id = company_id(rpc)

    with ctx.step("Isolate this case from TC285: assert no "
                  "account.analytic.distribution.model rule matches this "
                  "fixture's own product category. A matching rule would "
                  "turn TC284 into TC285 without saying so"):
        categ_id = ensure_category(rpc, "Cat284")
        rules = rpc.search_read(
            "account.analytic.distribution.model",
            [("product_categ_id", "=", categ_id)],
            ["analytic_distribution", "account_prefix"])
        ctx.log(f"rules matching the fixture category: {rules!r}")
        ctx.check("distribution-model rules on the fixture category", [],
                  rules)

    try:
        with ctx.step("Step 1: a confirmed purchase order whose line "
                      "carries a known two-plan distribution AD-PO"):
            vendor_id = ensure_vendor(rpc)
            product_id = ensure_product(ctx, categ_id=categ_id)
            spend = _account_on_plan(rpc, plan_ids[0], "Spend284")
            cost_center = _account_on_plan(rpc, plan_ids[1], "CC284")
            ad_po = {str(spend): 100.0, str(cost_center): 100.0}
            ctx.log(f"AD-PO = {ad_po!r}")
            order_id = make_purchase_order(ctx, vendor_id, product_id,
                                           analytic=ad_po, label="TC284")
            po_line = rpc.search_read("purchase.order.line",
                                      [("order_id", "=", order_id)],
                                      ["analytic_distribution"])[0]
            ctx.log(f"PO line distribution as stored: {po_line!r}")
            ctx.check("the PO line's resolved analytic accounts",
                      sorted({spend, cost_center}),
                      sorted(distribution_accounts(
                          po_line["analytic_distribution"])))

        with ctx.step("Step 2: validate the receipt, then press Create "
                      "Bill"):
            receipts = receive_order(ctx, order_id)
            ctx.log(f"receipts: {receipts!r}")
            bill_id = bill_from_order(ctx, order_id)
            ctx.log(f"derived bill: {bill_id}")

        with ctx.step("Steps 3-4 — THE ASSERTION: the bill line resolves "
                      "to exactly the PO line's analytic accounts. The raw "
                      "key shape is LOGGED, not asserted — §2.14 leaves "
                      "the v19 format Unknown and a shape change must not "
                      "be reported as a value change"):
            line = _bill_line(rpc, bill_id)
            if line is None:
                ctx.blocked(
                    f"The derived bill {bill_id} has no product line to "
                    "read. Check the purchase order's qty_to_invoice.")
            ctx.log(f"bill line raw distribution: "
                    f"{line['analytic_distribution']!r}")
            ctx.log(f"PO line raw distribution: "
                    f"{po_line['analytic_distribution']!r}")
            resolved = distribution_accounts(line["analytic_distribution"])
            ctx.check("the bill line's resolved analytic accounts",
                      sorted({spend, cost_center}), sorted(resolved))
            ctx.check_true(
                "the distribution is not empty — an empty dict is the "
                "dead-derivation signature",
                bool(line["analytic_distribution"]),
                actual_desc=line["analytic_distribution"])
            ctx.check("resolved plans of the bill line's accounts",
                      sorted(set(plan_ids)),
                      sorted(set(plan_of(rpc, resolved).values())))

        with ctx.step("Step 5: purchase_line_id points at the source PO "
                      "line — the branch condition F152 reads"):
            if not rpc.field_exists("account.move.line", "purchase_line_id"):
                ctx.log("[note] account.move.line.purchase_line_id does not "
                        "exist on this target; purchase_stock is not "
                        "installed, so the link cannot be asserted.")
            else:
                ctx.check_true("purchase_line_id is set on the derived line",
                               bool(line.get("purchase_line_id")),
                               actual_desc=line.get("purchase_line_id"))

        with ctx.step("Step 6 — THE NEGATIVE: a manually added line with "
                      "NO purchase_line_id gets only what the rule model "
                      "supplies, which for this category is nothing"):
            rpc.write("account.move", [bill_id], {
                "invoice_line_ids": [(0, 0, {
                    "product_id": product_id,
                    "quantity": 1.0,
                    "price_unit": 25.0,
                    "name": fx(f"{MARK} manual line"),
                    "tax_ids": [(6, 0, [])],
                })]})
            manual = [ln for ln in move_lines(rpc, bill_id)
                      if "manual line" in (ln.get("name") or "")]
            ctx.log(f"manually added line: {manual!r}")
            ctx.check("manually added lines found", 1, len(manual))
            manual_resolved = distribution_accounts(
                manual[0]["analytic_distribution"])
            ctx.log(f"manual line resolved accounts: {manual_resolved!r}")
            ctx.check("the manual line did NOT inherit AD-PO", set(),
                      manual_resolved & {spend, cost_center})
    finally:
        with ctx.step("Cleanup WF-016 fixtures"):
            try:
                sweep_wf016(rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")


@test_case(
    id="TEST-WF016-TC285",
    name="The distribution-model rule wins on a colliding key",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account", priority="P0", kind="API", order=16285,
    description="With a distribution-model rule and a purchase-order line "
                "populating the SAME plan with DIFFERENT accounts, the "
                "derived bill line carries the RULE's account on that "
                "plan, is not equal to AD-PO, and still carries the "
                "PO-only plan that does not collide.",
    traceability=trace("DATAONE-TC285"))
def test_tc285(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-016 fixtures and open a fresh "
                  "namespace"):
        sweep_wf016(rpc)

    with ctx.step("Preconditions: dto_account and purchase installed, two "
                  "analytic plans available"):
        require_dto_account(ctx)
        require_purchase(ctx)
        plan_ids, plan_names = _two_plans(ctx)
        comp_id = company_id(rpc)
        ctx.log(f"plans in use: {list(zip(plan_names, plan_ids))}")

    rule_id = None
    try:
        with ctx.step("Steps 1-3: build the collision. AD-PO and AD-RULE "
                      "both populate plan[0]; AD-PO alone populates "
                      "plan[1], so the non-colliding key's survival is "
                      "observable"):
            categ_id = ensure_category(rpc, "Cat285")
            vendor_id = ensure_vendor(rpc)
            product_id = ensure_product(ctx, categ_id=categ_id)
            po_spend = _account_on_plan(rpc, plan_ids[0], "Spend285-PO")
            rule_spend = _account_on_plan(rpc, plan_ids[0], "Spend285-RULE")
            po_only = _account_on_plan(rpc, plan_ids[1], "CC285-PO-only")
            ad_po = {str(po_spend): 100.0, str(po_only): 100.0}
            ad_rule = {str(rule_spend): 100.0}
            ctx.log(f"AD-PO   = {ad_po!r}  (plan[0]={po_spend}, "
                    f"plan[1]={po_only})")
            ctx.log(f"AD-RULE = {ad_rule!r} (plan[0]={rule_spend})")
            ctx.check_true(
                "the two DO collide — same plan, different accounts",
                (plan_of(rpc, [po_spend])[po_spend]
                 == plan_of(rpc, [rule_spend])[rule_spend]
                 and po_spend != rule_spend),
                actual_desc=f"po={po_spend} rule={rule_spend}")

            rule_id = rpc.create("account.analytic.distribution.model", {
                "product_categ_id": categ_id,
                "company_id": comp_id,
                "analytic_distribution": ad_rule,
            })
            ctx.log(f"account.analytic.distribution.model {rule_id} created "
                    f"for category {categ_id}")

        with ctx.step("Step 4: confirm the order, validate the receipt, "
                      "press Create Bill"):
            order_id = make_purchase_order(ctx, vendor_id, product_id,
                                           analytic=ad_po, label="TC285")
            receipts = receive_order(ctx, order_id)
            ctx.log(f"receipts: {receipts!r}")
            bill_id = bill_from_order(ctx, order_id)

        with ctx.step("Step 5: read the derived line's distribution"):
            line = _bill_line(rpc, bill_id)
            if line is None:
                ctx.blocked(f"The derived bill {bill_id} has no product "
                            "line to read.")
            raw = line["analytic_distribution"]
            resolved = distribution_accounts(raw)
            ctx.log(f"derived line raw distribution: {raw!r}")
            ctx.log(f"derived line resolved accounts: {sorted(resolved)}")
            ctx.check_true(
                "the derived distribution is not empty — an empty dict "
                "means _get_distribution returned {} and the whole blend "
                "collapsed",
                bool(raw), actual_desc=raw)

        with ctx.step("Step 6 — THE PRECEDENCE: on the colliding plan the "
                      "result carries the RULE's account, not the buyer's"):
            ctx.check_true(
                f"the rule's account {rule_spend} is present",
                rule_spend in resolved, actual_desc=sorted(resolved))
            ctx.check_true(
                f"the PO's colliding account {po_spend} was OVERRIDDEN",
                po_spend not in resolved, actual_desc=sorted(resolved))

        with ctx.step("Step 7: the result is NOT equal to AD-PO — the "
                      "buyer's explicit value did not simply win"):
            ctx.check_true(
                "the derived distribution differs from AD-PO",
                resolved != distribution_accounts(ad_po),
                actual_desc=f"resolved={sorted(resolved)} "
                            f"ad_po={sorted(distribution_accounts(ad_po))}")
            ctx.log("FAILURE SIGNATURE: a result EQUAL to AD-PO means "
                    "account.analytic.distribution.model._get_distribution "
                    "returned {} — its field_values contract "
                    "(product_categ_id / account_prefix / company_id) is "
                    "private and delta §2.14 leaves it Unknown on v19. "
                    "Nothing raises; the precedence simply inverts.")

        with ctx.step("Step 8: the non-colliding PO-only plan SURVIVED — "
                      "the rule overrides only where it collides"):
            ctx.check_true(
                f"the PO-only account {po_only} is still present",
                po_only in resolved, actual_desc=sorted(resolved))
            ctx.check("plans represented in the derived distribution",
                      sorted(set(plan_ids)),
                      sorted(set(plan_of(rpc, resolved).values())))

        with ctx.step("Sanity: the result does not put any root plan over "
                      "100%. A composite default key overlapping a "
                      "single-plan key is the C6 risk and it raises "
                      "nothing"):
            totals = {}
            for key, percentage in (raw or {}).items():
                if key == "__update__":
                    continue
                for account in distribution_accounts({key: percentage}):
                    plan = plan_of(rpc, [account])[account]
                    totals[plan] = totals.get(plan, 0.0) + percentage
            ctx.log(f"per-plan totals: {totals!r}")
            ctx.check("root plans over 100%", [],
                      [plan for plan, total in totals.items()
                       if round(total, 2) > 100.0])
    finally:
        with ctx.step("Cleanup: remove the distribution-model rule, then "
                      "the WF-016 fixtures. Leaving the rule in place "
                      "would contaminate TC284 on the next run"):
            if rule_id:
                try:
                    rpc.unlink("account.analytic.distribution.model",
                               [rule_id])
                except Exception as exc:      # noqa: BLE001
                    ctx.log(f"[warn] rule {rule_id} not removed: {exc}")
            try:
                sweep_wf016(rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")
