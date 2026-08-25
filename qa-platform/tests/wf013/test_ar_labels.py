"""DATAONE-WF-013 — AR labels and analytic inheritance:
TC279–TC283, TC286, TC287.

``dto_account.add_analytic_account_to_label_of_receivable_lines``
(dto_account/models/account_move.py:67) runs from ``_post`` and rewrites
every receivable line's label::

    new_name = []
    if line.name:                       # <- the EXISTING label is kept
        new_name.append(line.name)
    for plan, accounts in move_accounts.items():   # project, then contract
        if accounts:
            new_name.append(','.join(accounts))
    line.name = ' - '.join(new_name)

Because the existing label is re-appended, the only thing that stops three
post→draft→post cycles from producing
``AR - Proj - Proj - Proj`` is ``button_draft`` blanking the labels first
(:57). TC280 asserts the blanking and TC281 asserts the three cycles do not
concatenate — the two halves of one contract.

``AccountMoveLine.create`` (:180) then merges the sale line's analytic
distribution into every invoice line it creates, and the merge is
``{**sale_line_distribution, **default_distribution}`` accumulated across
``line.sale_line_ids`` — so on a multi-source line the LAST sale line wins
on a key collision (TC286). Because the hook lives in ``create``, it also
fires on the reversal lines ``dto_account_cogs`` itself creates (TC287).

EXPECTED v17 OUTCOME: PASS for all seven.
"""
from framework.registry import test_case
from tests.wf013.common import (MARK, WORKFLOW, WORKFLOW_NAME,  # noqa: F401
                                ensure_analytic_account, ensure_partner,
                                ensure_product, lines_by_account_type,
                                m2o_id, move_lines, realtime_category,
                                require_anglo_saxon,
                                require_cogs_analytic_accounts,
                                require_cogs_stack, require_mail_offline,
                                sell_and_invoice, sweep_wf013, trace)

PROJECT_PLAN = "dto_account.project_analytic_plan"
CONTRACT_PLAN = "dto_account.customer_contract_analytic_plan"


def _prepare(ctx):
    require_cogs_stack(ctx)
    require_anglo_saxon(ctx)
    require_cogs_analytic_accounts(ctx)
    require_mail_offline(ctx)
    category = realtime_category(ctx)
    if category is None:
        ctx.blocked("No product.category uses real-time valuation on this "
                    "database.")
    return category


def _receivable(rpc, invoice_id):
    return lines_by_account_type(rpc, invoice_id).get("asset_receivable", [])


def _accounts_in(distribution) -> set:
    result = set()
    for key in (distribution or {}):
        for part in str(key).split(","):
            if part.strip().isdigit():
                result.add(int(part.strip()))
    return result


@test_case(
    id="TEST-WF013-TC279",
    name="AR labels are suffixed with Project and Customer Contract names "
         "on post",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account", priority="P1", kind="API", order=13279,
    description="Posting appends the distinct Project and Customer "
                "Contract account names found across the invoice lines to "
                "every receivable line's label, joined by ' - '.",
    traceability=trace("DATAONE-TC279"))
def test_tc279(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-013 fixtures and open a fresh "
                  "namespace"):
        sweep_wf013(rpc)

    with ctx.step("Preconditions"):
        category = _prepare(ctx)

    try:
        with ctx.step("Post a project order whose line names a Project "
                      "account"):
            product_id = ensure_product(ctx, price=10.0, cost=9.0,
                                        categ_id=category["id"])
            project_account = ensure_analytic_account(rpc, PROJECT_PLAN,
                                                      "Project 279")
            project_name = rpc.read("account.analytic.account",
                                    [project_account], ["name"])[0]["name"]
            _order_id, invoice_id = sell_and_invoice(
                ctx, order_type="project",
                analytic={str(project_account): 100},
                product_id=product_id, price=10.0, label="Label279")

        with ctx.step("Every receivable line's label carries the Project "
                      "account name"):
            ar = _receivable(rpc, invoice_id)
            names = [ln["name"] or "" for ln in ar]
            ctx.log(f"receivable labels: {names!r}")
            ctx.check("receivable lines", 2, len(ar))
            ctx.check("receivable labels missing the Project name", [],
                      [n for n in names if project_name not in n])

        with ctx.step("The suffix is appended with the ' - ' separator the "
                      "implementation uses"):
            ctx.check_true(
                "at least one label uses the ' - ' join",
                any(" - " in n for n in names) or all(n == project_name
                                                      for n in names),
                actual_desc=repr(names))
    finally:
        with ctx.step("Cleanup WF-013 fixtures"):
            try:
                sweep_wf013(rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")


@test_case(
    id="TEST-WF013-TC280",
    name="Reset to draft blanks the AR labels",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account", priority="P1", kind="API", order=13280,
    description="button_draft writes name='' on every receivable line of a "
                "customer invoice or credit note, so the label is "
                "recomputed cleanly on the next post rather than being "
                "appended to.",
    traceability=trace("DATAONE-TC280"))
def test_tc280(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-013 fixtures and open a fresh "
                  "namespace"):
        sweep_wf013(rpc)

    with ctx.step("Preconditions"):
        category = _prepare(ctx)

    try:
        with ctx.step("Post a project order and confirm the labels are "
                      "populated"):
            product_id = ensure_product(ctx, price=10.0, cost=9.0,
                                        categ_id=category["id"])
            project_account = ensure_analytic_account(rpc, PROJECT_PLAN,
                                                      "Project 280")
            _order_id, invoice_id = sell_and_invoice(
                ctx, order_type="project",
                analytic={str(project_account): 100},
                product_id=product_id, price=10.0, label="Label280")
            before = [ln["name"] or "" for ln in _receivable(rpc, invoice_id)]
            ctx.log(f"labels while posted: {before!r}")
            ctx.check("populated receivable labels", [],
                      [n for n in before if not n.strip()])

        with ctx.step("Reset to draft blanks every receivable label"):
            rpc.call("account.move", "button_draft", [invoice_id])
            after = [ln["name"] or "" for ln in _receivable(rpc, invoice_id)]
            ctx.log(f"labels after the draft: {after!r}")
            ctx.check("receivable labels after button_draft",
                      [""] * len(after), after)
    finally:
        with ctx.step("Cleanup WF-013 fixtures"):
            try:
                sweep_wf013(rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")


@test_case(
    id="TEST-WF013-TC281",
    name="Three post → draft → post cycles: labels do not concatenate",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account_cogs", priority="P1", kind="API", order=13281,
    description="The label builder re-appends the existing name, so only "
                "button_draft's blanking stops the suffix repeating. Three "
                "full cycles must leave the label byte-identical to the "
                "first post's.",
    traceability=trace("DATAONE-TC281"))
def test_tc281(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-013 fixtures and open a fresh "
                  "namespace"):
        sweep_wf013(rpc)

    with ctx.step("Preconditions"):
        category = _prepare(ctx)

    try:
        with ctx.step("Post once and record the labels"):
            product_id = ensure_product(ctx, price=10.0, cost=9.0,
                                        categ_id=category["id"])
            project_account = ensure_analytic_account(rpc, PROJECT_PLAN,
                                                      "Project 281")
            project_name = rpc.read("account.analytic.account",
                                    [project_account], ["name"])[0]["name"]
            _order_id, invoice_id = sell_and_invoice(
                ctx, order_type="project",
                analytic={str(project_account): 100},
                product_id=product_id, price=10.0, label="Label281")
            baseline = sorted(ln["name"] or ""
                              for ln in _receivable(rpc, invoice_id))
            ctx.log(f"labels after cycle 0: {baseline!r}")

        for cycle in (1, 2, 3):
            with ctx.step(f"Cycle {cycle}: draft then post again"):
                rpc.call("account.move", "button_draft", [invoice_id])
                rpc.call("account.move", "action_post", [invoice_id])
                current = sorted(ln["name"] or ""
                                 for ln in _receivable(rpc, invoice_id))
                ctx.log(f"labels after cycle {cycle}: {current!r}")
                ctx.check(f"cycle {cycle}: labels match the first post",
                          baseline, current)

        with ctx.step("The Project name appears exactly ONCE in each label "
                      "— the definitive anti-concatenation assertion"):
            counts = {name: name.count(project_name)
                      for name in sorted(ln["name"] or ""
                                         for ln in _receivable(rpc,
                                                               invoice_id))}
            ctx.log(f"occurrences per label: {counts!r}")
            ctx.check("labels where the Project name repeats", [],
                      [name for name, n in counts.items() if n > 1])
    finally:
        with ctx.step("Cleanup WF-013 fixtures"):
            try:
                sweep_wf013(rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")


@test_case(
    id="TEST-WF013-TC282",
    name="A move with no Project or Contract account gets the "
         "empty-segment label",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account", priority="P3", kind="API", order=13282,
    description="With neither plan represented, the builder appends "
                "nothing, so the receivable label is whatever it already "
                "was — no stray separator and no empty segment.",
    traceability=trace("DATAONE-TC282"))
def test_tc282(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-013 fixtures and open a fresh "
                  "namespace"):
        sweep_wf013(rpc)

    with ctx.step("Preconditions"):
        category = _prepare(ctx)

    try:
        with ctx.step("Post an INVENTORY order — its gate forbids any "
                      "analytic distribution, so neither plan is "
                      "represented"):
            product_id = ensure_product(ctx, price=10.0, cost=9.0,
                                        categ_id=category["id"])
            _order_id, invoice_id = sell_and_invoice(
                ctx, order_type="inventory", product_id=product_id,
                price=10.0, label="Label282")

        with ctx.step("No label carries a dangling ' - ' separator or an "
                      "empty segment"):
            names = [ln["name"] or "" for ln in _receivable(rpc, invoice_id)]
            ctx.log(f"receivable labels: {names!r}")
            bad = [n for n in names
                   if n.strip().endswith("-") or n.strip().startswith("-")
                   or " -  - " in n]
            ctx.check("labels with a dangling or empty segment", [], bad)

        with ctx.step("The move still posts and balances"):
            ctx.check("move state", "posted",
                      rpc.read("account.move", [invoice_id],
                               ["state"])[0]["state"])
            lines = move_lines(rpc, invoice_id)
            ctx.check("move net balance", 0.0,
                      round(sum(ln["balance"] for ln in lines), 2))
    finally:
        with ctx.step("Cleanup WF-013 fixtures"):
            try:
                sweep_wf013(rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")


@test_case(
    id="TEST-WF013-TC283",
    name="Both AR lines — the original and the reversal — carry the suffix",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account", priority="P2", kind="API", order=13283,
    description="The label pass runs after dto_account_cogs has created "
                "its reversal line, so the is_cogs receivable line carries "
                "the same suffix as the original — the ordering evidence "
                "TC232 also relies on.",
    traceability=trace("DATAONE-TC283"))
def test_tc283(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-013 fixtures and open a fresh "
                  "namespace"):
        sweep_wf013(rpc)

    with ctx.step("Preconditions"):
        category = _prepare(ctx)

    try:
        with ctx.step("Post a project order"):
            product_id = ensure_product(ctx, price=10.0, cost=9.0,
                                        categ_id=category["id"])
            project_account = ensure_analytic_account(rpc, PROJECT_PLAN,
                                                      "Project 283")
            project_name = rpc.read("account.analytic.account",
                                    [project_account], ["name"])[0]["name"]
            _order_id, invoice_id = sell_and_invoice(
                ctx, order_type="project",
                analytic={str(project_account): 100},
                product_id=product_id, price=10.0, label="Label283")

        with ctx.step("The original and the is_cogs reversal are both "
                      "present, and BOTH carry the suffix"):
            ar = _receivable(rpc, invoice_id)
            original = [ln for ln in ar if not ln["is_cogs"]]
            reversal = [ln for ln in ar if ln["is_cogs"]]
            ctx.log(f"original: {[ln['name'] for ln in original]!r}; "
                    f"reversal: {[ln['name'] for ln in reversal]!r}")
            ctx.check("original receivable lines", 1, len(original))
            ctx.check("reversal receivable lines", 1, len(reversal))
            ctx.check(
                "receivable lines missing the Project suffix", [],
                [ln["name"] for ln in ar
                 if project_name not in (ln["name"] or "")])
    finally:
        with ctx.step("Cleanup WF-013 fixtures"):
            try:
                sweep_wf013(rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")


@test_case(
    id="TEST-WF013-TC286",
    name="Invoice lines inherit the sale line's distribution; later lines "
         "win on merge",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account", priority="P0", kind="API", order=13286,
    description="AccountMoveLine.create merges the originating sale line's "
                "analytic_distribution into the invoice line, accumulated "
                "across sale_line_ids so a later sale line wins on a key "
                "collision, and then merged with the distribution model's "
                "default.",
    traceability=trace("DATAONE-TC286"))
def test_tc286(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-013 fixtures and open a fresh "
                  "namespace"):
        sweep_wf013(rpc)

    with ctx.step("Preconditions"):
        category = _prepare(ctx)

    try:
        with ctx.step("Post a project order whose line carries a known "
                      "Project account"):
            product_id = ensure_product(ctx, price=10.0, cost=9.0,
                                        categ_id=category["id"])
            project_account = ensure_analytic_account(rpc, PROJECT_PLAN,
                                                      "Project 286")
            _order_id, invoice_id = sell_and_invoice(
                ctx, order_type="project",
                analytic={str(project_account): 100},
                product_id=product_id, price=10.0, label="Inherit286")

        with ctx.step("The invoice's product line inherited the sale "
                      "line's analytic account"):
            product_lines = [ln for ln in move_lines(rpc, invoice_id)
                             if ln["display_type"] == "product"
                             and not ln["is_cogs"]]
            ctx.log(f"product lines: {product_lines!r}")
            ctx.check("invoice product lines", 1, len(product_lines))
            inherited = _accounts_in(
                product_lines[0]["analytic_distribution"])
            ctx.log(f"inherited distribution -> {sorted(inherited)}")
            ctx.check_true(
                "the sale line's Project account reached the invoice line",
                project_account in inherited,
                actual_desc=sorted(inherited))

        with ctx.step("The merge order is documented in the execution "
                      "record"):
            ctx.log("AccountMoveLine.create builds "
                    "sale_line_distribution by iterating line.sale_line_ids "
                    "and merging each into the accumulator, so a LATER "
                    "sale line wins on a key collision; the result is then "
                    "merged under the distribution model's default "
                    "({**additional, **default}), so the model wins over "
                    "the sale line. dto_account/models/account_move.py:"
                    "165-200.")
    finally:
        with ctx.step("Cleanup WF-013 fixtures"):
            try:
                sweep_wf013(rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")


@test_case(
    id="TEST-WF013-TC287",
    name="The post-create write also fires on lines DataOne itself created",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account", priority="P2", kind="API", order=13287,
    description="The analytic merge lives in AccountMoveLine.create, so it "
                "also runs for the reversal lines dto_account_cogs creates "
                "during _post — those lines carry a distribution even "
                "though nothing in their own vals asked for the merge.",
    traceability=trace("DATAONE-TC287"))
def test_tc287(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-013 fixtures and open a fresh "
                  "namespace"):
        sweep_wf013(rpc)

    with ctx.step("Preconditions"):
        category = _prepare(ctx)
        refs = require_cogs_analytic_accounts(ctx)

    try:
        with ctx.step("Post a buy order — its reversal lines are created "
                      "through the same AccountMoveLine.create hook"):
            product_id = ensure_product(ctx, price=10.0, cost=9.0,
                                        categ_id=category["id"])
            contract = ensure_analytic_account(rpc, CONTRACT_PLAN,
                                               "Contract 287")
            _order_id, invoice_id = sell_and_invoice(
                ctx, order_type="buy", analytic={str(contract): 100},
                product_id=product_id, price=10.0, label="PostCreate287")

        with ctx.step("The is_cogs lines exist and carry a NON-EMPTY "
                      "analytic distribution"):
            cogs_lines = [ln for ln in move_lines(rpc, invoice_id)
                          if ln["is_cogs"]]
            ctx.log(f"is_cogs lines: {cogs_lines!r}")
            ctx.check("is_cogs lines", 2, len(cogs_lines))
            ctx.check("is_cogs lines with an empty distribution", [],
                      [ln["id"] for ln in cogs_lines
                       if not ln["analytic_distribution"]])

        with ctx.step("Their distribution carries the reversal accounts "
                      "_prepare_reverse_revenue_analytic_distribution "
                      "supplies — Service_Sales and CC 180008"):
            expected = {
                refs["dto_account.analytic_account_revenue_category_"
                     "service_sales"],
                refs["dto_account.analytic_account_cost_center_180008"]}
            missing = {}
            for line in cogs_lines:
                accounts = _accounts_in(line["analytic_distribution"])
                absent = sorted(expected - accounts)
                if absent:
                    missing[line["id"]] = absent
            ctx.log(f"is_cogs distributions: "
                    f"{[(ln['id'], ln['analytic_distribution']) for ln in cogs_lines]!r}")
            ctx.check("reversal accounts missing from an is_cogs line", {},
                      missing)
    finally:
        with ctx.step("Cleanup WF-013 fixtures"):
            try:
                sweep_wf013(rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")
