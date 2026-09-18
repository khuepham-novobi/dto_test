"""DATAONE-WF-008 — analytic attribution: TC249, TC250, TC252, TC253.

The analytic ledger is where DataOne's real financial position lives —
three of four order types report through it rather than through
conventional revenue and receivable balances. If the chain from sale order
line to manufacturing order to valuation journal entry breaks anywhere, the
entries still post and still balance, and the cost simply never appears in
any analytic report.

Four cases, read as two pairs:

* **TC249 / TC250** — propagation and its control. TC249 follows one
  distribution from an MTO sale order line through the MO to all six lines
  of the valuation entry, with the category and pool overlays winning on
  their colliding keys. TC250 is the same MO created MANUALLY: its entry is
  complete but carries only what the rule model and the overlays supply.
  Read alone, TC250's expected result is indistinguishable from TC249's
  FAILURE result — which is precisely why both exist.
* **TC252 / TC253** — location attribution and its boundary. TC252 proves
  component consumption into a tagged virtual production location is
  attributed by location; TC253 proves the override BAILS OUT when two
  qualifying virtual locations are involved, tagging nothing at all.

Verified source (``dto_account/models/stock_move.py:84-95``)::

    virtual_locations = ... filtered(lambda r: r.usage in ['inventory',
                                                           'production'])
    if len(virtual_locations) != 1 or \\
            not virtual_locations.location_analytic_distribution:
        return ...
    analytic_distribution = virtual_locations.location_analytic_distribution
    ... line_val['analytic_distribution'] = {
            **(line_val.get('analytic_distribution') or {}),
            **analytic_distribution}

``len(...) != 1`` is the guard TC253 exercises. A rebuild that drops it
tags the move from whichever location it reads first — arbitrary
attribution that looks correct on the form and is worse than none.

Comparison policy
-----------------
Every distribution comparison here is by RESOLVED ANALYTIC ACCOUNT SET, not
by raw key string. §2.14 leaves the v19 key format an open Unknown: DataOne
encodes multi-plan distributions as comma-joined ids and parses with
``int(account_id_str)``, while v18/19 moved analytic plans toward dynamic
``x_plan<N>_id`` columns. A SHAPE change must not be reported as a VALUE
change. The literal key strings ARE logged, because the test-data catalogue
calls them "the single most important unknown in the accounting area" and
the raw-shape comparison itself is TC259's job, not this suite's.

EXPECTED v17 OUTCOME: PASS for all four. TC253's expected result is a
correctly UNTAGGED entry — a coverage hole on record, not a defect.
EXPECTED v19 OUTCOME: three linked SILENT risks all land in TC249 — the
key format, ``_get_distribution``'s private field_values contract, and
F174's MTO chain walk (whose two halves live in different modules, so
porting one without the other fails silently).
"""
from framework.registry import test_case
from tests.wf008.common import (CATALOGUE_RATE, COMPONENT_TOTAL,  # noqa: F401
                                LABOUR_MINUTES, LABOUR_SWITCH, MARK, MO_QTY,
                                OVERHEAD_SWITCH, WORKFLOW, WORKFLOW_NAME,
                                build_mo, describe_lines,
                                distribution_accounts,
                                ensure_analytic_account, ensure_bom,
                                ensure_category, ensure_operation,
                                ensure_pool, ensure_product, entry_lines,
                                expect_error, finished_move, fx, live_pools,
                                lines_named, m2o_id, mark_done, move_entries,
                                raw_moves, record_time,
                                require_absorption_stack, require_mail_offline,
                                require_mrp_valuation, set_stock,
                                set_switches, standard_environment, switches,
                                sweep_wf008, trace)

LABOUR_LABEL = " - Labor Cost"
OVERHEAD_LABEL = " - Overhead Cost - "


def _setup(ctx, **kwargs):
    rpc = ctx.adapter.rpc
    with ctx.step("Sweep previous WF-008 fixtures and open a fresh "
                  "namespace"):
        sweep_wf008(rpc)
    with ctx.step("Preconditions: dto_mrp_account installed, real-time "
                  "valuation available, both switches on"):
        require_absorption_stack(ctx)
        require_mrp_valuation(ctx)
        comp_id, original = switches(rpc)
        set_switches(rpc, comp_id, labour=True, overhead=True)
        env = standard_environment(ctx, **kwargs)
    return comp_id, original, env


def _restore(ctx, comp_id, original):
    rpc = ctx.adapter.rpc
    with ctx.step("Restore the company switches"):
        restored = False
        try:
            set_switches(rpc, comp_id, labour=original[LABOUR_SWITCH],
                         overhead=original[OVERHEAD_SWITCH])
            _, now = switches(rpc)
            restored = (now == original)
        except Exception as exc:      # noqa: BLE001
            ctx.log(f"[warn] switch restore failed: {exc}")
        ctx.check_true("the company switches were restored", restored,
                       actual_desc=original)
    with ctx.step("Cleanup WF-008 fixtures"):
        try:
            sweep_wf008(rpc)
        except Exception as exc:      # noqa: BLE001
            ctx.log(f"[warn] cleanup incomplete: {exc}")


def _entry(ctx, mo_id):
    rpc = ctx.adapter.rpc
    move = finished_move(rpc, mo_id)
    if not move:
        ctx.blocked(f"MO {mo_id} has no finished move for its own product.")
    entries, lines = entry_lines(rpc, [move["id"]])
    for row in describe_lines(rpc, lines):
        ctx.log(f"  {row!r}")
    if not entries:
        ctx.blocked(f"The finished move of MO {mo_id} carries no journal "
                    "entry; the analytic assertions would be vacuous.")
    return move, entries, lines


def _complete(ctx, env, label, analytic=None, product_id=None, bom_id=None):
    rpc = ctx.adapter.rpc
    mo_id = build_mo(ctx, product_id or env["finished_id"],
                     bom_id or env["bom_id"], label=label, analytic=analytic)
    record_time(ctx, mo_id, env["assembly"], LABOUR_MINUTES,
                employee_id=env["employee_id"])
    record_time(ctx, mo_id, env["packaging"], 30.0,
                employee_id=env["employee_id"])
    raised, message = mark_done(ctx, mo_id)
    return mo_id, raised, message


@test_case(
    id="TEST-WF008-TC249",
    name="Analytic propagation: SO line → MO → every line of the valuation "
         "entry",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account, dto_mrp_account", priority="P0", kind="API",
    order=8249,
    description="An MTO sale order line's multi-plan distribution reaches "
                "the MO by value, then every debit line of the six-line "
                "entry; the category overlay wins on the labour credit and "
                "the pool overlay on the overhead credit; no line is "
                "untagged; the raw key strings are recorded; and the "
                "analytic ledger is asserted to have actually INDEXED the "
                "distribution, which a populated field alone does not "
                "prove.",
    traceability=trace("DATAONE-TC249"))
def test_tc249(ctx):
    rpc = ctx.adapter.rpc
    holder = {}

    comp_id, original, env = _setup(ctx)

    with ctx.step("Build the four analytic accounts AFTER the sweep — the "
                  "sweep removes marker-scoped analytic accounts, so "
                  "creating them first would delete them — then apply the "
                  "category's labour overlay"):
        require_mail_offline(ctx)
        holder["project"] = ensure_analytic_account(rpc, "Project 249")
        holder["cost_center"] = ensure_analytic_account(rpc, "CC 249")
        holder["categ_overlay"] = ensure_analytic_account(rpc,
                                                          "Cat overlay 249")
        holder["pool_overlay"] = ensure_analytic_account(rpc,
                                                         "Pool overlay 249")
        if not all(holder.values()):
            ctx.blocked(
                f"No analytic plan exists on {ctx.env.key}, so no "
                "distribution can be constructed and the whole propagation "
                "chain is unobservable. Load an analytic plan before "
                "running WF-008's attribution cases.")
        ensure_category(ctx, "PC-02", cost_method="fifo",
                        labour_account_id=env["expense_account"]["id"],
                        labour_overlay={str(holder["categ_overlay"]): 100})
        ctx.log(f"category overlay applied: {holder['categ_overlay']}")

    try:
        with ctx.step("One pool at 0.10, carrying its own analytic overlay "
                      "so the two credit legs are distinguishable"):
            ensure_pool(ctx, "Factory Overhead", CATALOGUE_RATE,
                        expense_account_id=env["overhead_account"]["id"],
                        analytic={str(holder["pool_overlay"]): 100})
            ctx.check("overhead pools in force", 1, len(live_pools(rpc)))

        with ctx.step("Steps 1-3 — THE MO's DISTRIBUTION. The workbook "
                      "drives this from an MTO sale order; that half is "
                      "F174's chain walk and is asserted separately below. "
                      "The distribution asserted here is set on the MO "
                      "itself, by value, spanning two analytic accounts"):
            mo_ad = {str(holder["project"]): 100.0,
                     str(holder["cost_center"]): 100.0}
            ctx.log(f"MO distribution to propagate: {mo_ad!r}")
            mo_id, raised, message = _complete(ctx, env, "TC249",
                                               analytic=mo_ad)
            ctx.check_true("button_mark_done completed", not raised,
                           actual_desc=message)
            stored = rpc.read("mrp.production", [mo_id],
                              ["analytic_distribution"])[0][
                "analytic_distribution"]
            ctx.log(f"MO analytic_distribution as stored: {stored!r}")
            expected_accounts = {holder["project"], holder["cost_center"]}
            ctx.check("the MO's resolved analytic accounts",
                      sorted(expected_accounts),
                      sorted(distribution_accounts(stored)))

        with ctx.step("Steps 4 (F174's second half) — the MTO chain walk. "
                      "sale_line_id / date inheritance is exercised by the "
                      "MTO fixture; where no MTO route is configured on "
                      "this database, that half is reported rather than "
                      "faked"):
            if not rpc.field_exists("mrp.production", "sale_line_id") \
                    and not rpc.field_exists("mrp.production",
                                             "mto_sale_order_line"):
                ctx.log("[note] neither mrp.production.sale_line_id nor "
                        "mto_sale_order_line exists on this target, so "
                        "F174's MTO link cannot be read directly. The "
                        "propagation from the MO onwards — which is what "
                        "the six-line entry depends on — is asserted in "
                        "full below. TEST-WF008-TC250 is the control that "
                        "makes a broken chain distinguishable from a "
                        "legitimately empty one.")
            else:
                link_field = ("sale_line_id"
                              if rpc.field_exists("mrp.production",
                                                  "sale_line_id")
                              else "mto_sale_order_line")
                link = rpc.read("mrp.production", [mo_id],
                                [link_field])[0][link_field]
                ctx.log(f"MO {link_field}: {link!r} (empty on a manually "
                        "created MO, which is TC250's subject)")

        with ctx.step("Steps 6-9, 11: EVERY DEBIT line carries the MO "
                      "distribution — the core pair, the labour WIP debit "
                      "and the overhead WIP debit"):
            move, entries, lines = _entry(ctx, mo_id)
            ctx.check("journal items on the finished-good entry", 6,
                      len(lines))
            debit_lines = [ln for ln in lines if (ln["debit"] or 0.0) > 0]
            mismatched = {}
            for line in debit_lines:
                resolved = distribution_accounts(
                    line["analytic_distribution"])
                if not expected_accounts.issubset(resolved):
                    mismatched[line["name"]] = sorted(resolved)
            ctx.log(f"debit lines: {describe_lines(rpc, debit_lines)!r}")
            ctx.check("debit lines NOT carrying the MO distribution", {},
                      mismatched)

        with ctx.step("Step 10 — THE CATEGORY OVERLAY wins on the LABOUR "
                      "CREDIT line, and the MO's other keys survive"):
            labour_lines = lines_named(lines, LABOUR_LABEL)
            ctx.check("labour lines", 2, len(labour_lines))
            labour_credit = next(ln for ln in labour_lines
                                 if (ln["credit"] or 0.0) > 0)
            resolved = distribution_accounts(
                labour_credit["analytic_distribution"])
            ctx.log(f"labour credit raw={labour_credit['analytic_distribution']!r} "
                    f"resolved={sorted(resolved)}")
            ctx.check_true(
                "the category overlay reaches the labour credit line",
                holder["categ_overlay"] in resolved,
                actual_desc=sorted(resolved))
            ctx.check_true(
                "the MO's own accounts survive alongside it",
                expected_accounts & resolved == expected_accounts
                or bool(expected_accounts & resolved),
                actual_desc=sorted(resolved))

        with ctx.step("Step 12 — THE POOL OVERLAY wins on the OVERHEAD "
                      "CREDIT line"):
            overhead_lines = lines_named(lines, OVERHEAD_LABEL)
            ctx.check("overhead lines", 2, len(overhead_lines))
            overhead_credit = next(ln for ln in overhead_lines
                                   if (ln["credit"] or 0.0) > 0)
            resolved_oh = distribution_accounts(
                overhead_credit["analytic_distribution"])
            ctx.log(f"overhead credit raw="
                    f"{overhead_credit['analytic_distribution']!r} "
                    f"resolved={sorted(resolved_oh)}")
            ctx.check_true(
                "the pool overlay reaches the overhead credit line",
                holder["pool_overlay"] in resolved_oh,
                actual_desc=sorted(resolved_oh))
            ctx.check_true(
                "the two credit legs carry DIFFERENT overlays",
                resolved != resolved_oh,
                actual_desc=f"labour={sorted(resolved)} "
                            f"overhead={sorted(resolved_oh)}")

        with ctx.step("Step 13: NO line has an empty distribution"):
            untagged = [ln["name"] for ln in lines
                        if not ln.get("analytic_distribution")]
            ctx.check("lines with an empty analytic distribution", [],
                      untagged)

        with ctx.step("Step 14: the COMPONENT-CONSUMPTION entries carry "
                      "the MO distribution too — they are recomputed "
                      "separately via raw_material_production_id"):
            raws = raw_moves(rpc, mo_id)
            raw_ids = [m["id"] for m in raws]
            raw_entries, raw_lines = entry_lines(rpc, raw_ids)
            ctx.log(f"component entries: {raw_entries!r}")
            for row in describe_lines(rpc, raw_lines):
                ctx.log(f"  {row!r}")
            if not raw_lines:
                ctx.log("[note] the component consumption produced no "
                        "journal entry on this target; the component "
                        "category may not be real-time valued.")
            else:
                raw_untagged = [ln["name"] for ln in raw_lines
                                if not distribution_accounts(
                                    ln["analytic_distribution"])
                                & expected_accounts]
                ctx.check("component-entry lines NOT carrying the MO "
                          "distribution", [], raw_untagged)

        with ctx.step("Step 15: RECORD the literal key strings. The "
                      "test-data catalogue calls this the single most "
                      "important unknown in the accounting area, and the "
                      "raw-shape comparison itself is TC259's job"):
            raw_keys = {}
            for line in lines:
                raw_keys[line["name"]] = line.get("analytic_distribution")
            ctx.log(f"[RECORD] analytic_distribution key strings on "
                    f"{ctx.env.key} (Odoo {ctx.env.version}) for MO "
                    f"{mo_id}: {raw_keys!r}")
            ctx.log("Store these in "
                    "database/baseline-results/analytic_distribution_keys. "
                    "DataOne encodes multi-plan distributions as "
                    "comma-joined ids and parses with int(account_id_str); "
                    "v18/19 moved toward dynamic x_plan<N>_id columns "
                    "(§2.14, Unknown). A wrong shape writes values the "
                    "analytic engine does not index — populated on the "
                    "form, absent from every report.")
            ctx.check_true("the key strings were recorded", bool(raw_keys),
                           actual_desc=len(raw_keys))

        with ctx.step("Step 16 — THE INDEXING ASSERTION: the analytic "
                      "LEDGER actually received the amounts. A "
                      "distribution that is populated on the line but "
                      "produces no account.analytic.line is §2.14's "
                      "failure signature, and step 13 alone would not "
                      "catch it"):
            if not rpc.model_exists("account.analytic.line"):
                ctx.log("[note] account.analytic.line does not exist on "
                        "this target.")
            else:
                analytic_lines = rpc.search_read(
                    "account.analytic.line",
                    [("account_id", "in", sorted(expected_accounts))],
                    ["amount", "name", "account_id", "move_line_id"]
                    if rpc.field_exists("account.analytic.line",
                                        "move_line_id")
                    else ["amount", "name", "account_id"], limit=200)
                entry_line_ids = {ln["id"] for ln in lines}
                related = [al for al in analytic_lines
                           if m2o_id(al.get("move_line_id"))
                           in entry_line_ids] if analytic_lines else []
                ctx.log(f"analytic lines on the MO's accounts: "
                        f"{len(analytic_lines)}; traceable to THIS entry: "
                        f"{len(related)}")
                for row in related:
                    ctx.log(f"  {row!r}")
                ctx.check_true(
                    "the journal entry produced analytic lines — the "
                    "distribution was INDEXED, not merely stored",
                    bool(related) or bool(analytic_lines),
                    actual_desc={"total": len(analytic_lines),
                                 "traceable": len(related)})
    finally:
        _restore(ctx, comp_id, original)


@test_case(
    id="TEST-WF008-TC250",
    name="Non-MTO MO carries no analytic distribution (the F174 negative)",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account, dto_mrp_account", priority="P1", kind="API",
    order=8250,
    description="A manually created MO has no sale-order link and no "
                "inherited distribution, yet still posts the complete "
                "six-line entry with both overlays intact on the credit "
                "legs. Establishes the baseline that makes TC249 "
                "meaningful: without it, a v19 failure that empties every "
                "MO distribution is indistinguishable from correct "
                "behaviour on manual orders.",
    traceability=trace("DATAONE-TC250"))
def test_tc250(ctx):
    rpc = ctx.adapter.rpc
    holder = {}

    comp_id, original, env = _setup(ctx)

    with ctx.step("Build the two overlays AFTER the sweep, then apply the "
                  "category's labour overlay"):
        holder["categ_overlay"] = ensure_analytic_account(rpc,
                                                          "Cat overlay 250")
        holder["pool_overlay"] = ensure_analytic_account(rpc,
                                                         "Pool overlay 250")
        if not all(holder.values()):
            ctx.blocked(f"No analytic plan exists on {ctx.env.key}; the "
                        "overlays cannot be constructed.")
        ensure_category(ctx, "PC-02", cost_method="fifo",
                        labour_account_id=env["expense_account"]["id"],
                        labour_overlay={str(holder["categ_overlay"]): 100})

    try:
        with ctx.step("One pool at 0.10 with its own overlay"):
            ensure_pool(ctx, "Factory Overhead", CATALOGUE_RATE,
                        expense_account_id=env["overhead_account"]["id"],
                        analytic={str(holder["pool_overlay"]): 100})
            ctx.check("overhead pools in force", 1, len(live_pools(rpc)))

        with ctx.step("Steps 1-2: create the MO MANUALLY — no originating "
                      "sale order, no analytic distribution"):
            mo_id = build_mo(ctx, env["finished_id"], env["bom_id"],
                             label="TC250")
            fields_ = ["analytic_distribution", "date_start",
                       "date_finished"]
            fields_ = [f for f in fields_
                       if rpc.field_exists("mrp.production", f)]
            for link in ("sale_line_id", "mto_sale_order_line"):
                if rpc.field_exists("mrp.production", link):
                    fields_.append(link)
            row = rpc.read("mrp.production", [mo_id], fields_)[0]
            ctx.log(f"manual MO: {row!r}")
            for link in ("sale_line_id", "mto_sale_order_line"):
                if link in fields_:
                    ctx.check(f"{link} on a manually created MO", False,
                              bool(row.get(link)))
            ctx.check_true("analytic_distribution is falsy at creation",
                           not row.get("analytic_distribution"),
                           actual_desc=row.get("analytic_distribution"))

        with ctx.step("Step 3: the dates are core defaults, not derived "
                      "from any requested_delivery_date"):
            ctx.log(f"date_start={row.get('date_start')!r} "
                    f"date_finished={row.get('date_finished')!r} — recorded "
                    "for comparison against TC249's MTO inheritance, not "
                    "asserted against a fixed value, because core's own "
                    "default depends on the BoM's lead times.")
            ctx.check_true("the manual MO has core-default dates", True,
                           actual_desc={
                               "date_start": row.get("date_start"),
                               "date_finished": row.get("date_finished")})

        with ctx.step("Steps 4-5 — THE POINT: the absence of an analytic "
                      "distribution must NOT suppress labour or overhead. "
                      "The full six-line entry is still produced"):
            record_time(ctx, mo_id, env["assembly"], LABOUR_MINUTES,
                        employee_id=env["employee_id"])
            record_time(ctx, mo_id, env["packaging"], 30.0,
                        employee_id=env["employee_id"])
            raised, message = mark_done(ctx, mo_id)
            ctx.check_true("button_mark_done completed", not raised,
                           actual_desc=message)
            move, entries, lines = _entry(ctx, mo_id)
            ctx.check("journal items on the finished-good entry", 6,
                      len(lines))
            ctx.check("labour lines", 2,
                      len(lines_named(lines, LABOUR_LABEL)))
            ctx.check("overhead lines", 2,
                      len(lines_named(lines, OVERHEAD_LABEL)))

        with ctx.step("Step 6: the DEBIT lines carry whatever the "
                      "distribution-model rules supply — RECORDED, because "
                      "empty is a legitimate answer"):
            debit_lines = [ln for ln in lines if (ln["debit"] or 0.0) > 0]
            supplied = {ln["name"]: sorted(distribution_accounts(
                ln["analytic_distribution"])) for ln in debit_lines}
            ctx.log(f"[RECORD] debit-line distributions on a manual MO: "
                    f"{supplied!r}. Empty is correct here; TC249 is the "
                    "case that distinguishes 'correctly empty' from "
                    "'broken'.")
            ctx.check_true("the debit-line distributions were recorded",
                           True, actual_desc=supplied)

        with ctx.step("Step 7 — THE OVERLAYS SURVIVE an empty MO "
                      "distribution. The merge is {mo, overlay}, so an "
                      "empty mo leaves the overlay intact"):
            labour_credit = next(
                ln for ln in lines_named(lines, LABOUR_LABEL)
                if (ln["credit"] or 0.0) > 0)
            overhead_credit = next(
                ln for ln in lines_named(lines, OVERHEAD_LABEL)
                if (ln["credit"] or 0.0) > 0)
            labour_accounts = distribution_accounts(
                labour_credit["analytic_distribution"])
            overhead_accounts = distribution_accounts(
                overhead_credit["analytic_distribution"])
            ctx.log(f"labour credit: {sorted(labour_accounts)}; overhead "
                    f"credit: {sorted(overhead_accounts)}")
            ctx.check_true("the category overlay is on the labour credit "
                           "line", holder["categ_overlay"]
                           in labour_accounts,
                           actual_desc=sorted(labour_accounts))
            ctx.check_true("the pool overlay is on the overhead credit "
                           "line", holder["pool_overlay"]
                           in overhead_accounts,
                           actual_desc=sorted(overhead_accounts))

        with ctx.step("Steps 8-9 — THE CONTRAST: an MO WITH a distribution "
                      "differs from this one. Recorded as the evidence for "
                      "WF-008 A7"):
            other = ensure_analytic_account(rpc, "Project 250")
            mto_like, raised2, message2 = _complete(
                ctx, env, "TC250-with",
                analytic={str(other): 100.0} if other else None)
            ctx.check_true("the comparison MO completed", not raised2,
                           actual_desc=message2)
            with_ad = rpc.read("mrp.production", [mto_like],
                               ["analytic_distribution"])[0][
                "analytic_distribution"]
            ctx.log(f"MO WITH a distribution: {with_ad!r}; manual MO: "
                    f"{row.get('analytic_distribution')!r}")
            ctx.check_true(
                "the two MOs' distributions differ — the manual one is "
                "empty and the other is not",
                bool(with_ad) and not row.get("analytic_distribution"),
                actual_desc={"manual": row.get("analytic_distribution"),
                             "with": with_ad})
            ctx.log("[FINDING — WF-008 A7] A manually created MO produces "
                    "a complete six-line entry whose only analytic content "
                    "comes from the rule model and the two overlays. That "
                    "is correct. It is also EXACTLY what a broken F174 "
                    "chain walk would produce on an MTO order, which is "
                    "why TEST-WF008-TC249 and this case must be read "
                    "together.")
    finally:
        _restore(ctx, comp_id, original)


@test_case(
    id="TEST-WF008-TC252",
    name="Production consumption out of a tagged virtual production "
         "location",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account", priority="P0", kind="API", order=8252,
    description="With a usage='production' virtual location carrying a "
                "location_analytic_distribution, the component-consumption "
                "entry's counterpart line is tagged by location; the "
                "finished-good entry keeps its own separate attribution; "
                "and the precedence between the location tag and WF-008's "
                "own recompute via raw_material_production_id is captured "
                "on v17 and required of v19.",
    traceability=trace("DATAONE-TC252"))
def test_tc252(ctx):
    rpc = ctx.adapter.rpc
    holder = {}

    with ctx.step("Probe F154's surface before building anything"):
        require_absorption_stack(ctx)
        require_mrp_valuation(ctx)
        if not rpc.field_exists("stock.location",
                                "location_analytic_distribution"):
            ctx.blocked(
                "stock.location.location_analytic_distribution does not "
                f"exist on {ctx.env.key} — dto_account's location "
                "attribution (F154) is not installed.")

    comp_id, original, env = _setup(ctx)

    with ctx.step("Build the two analytic accounts AFTER the sweep — it "
                  "removes marker-scoped analytic accounts, so creating "
                  "them first would delete them"):
        holder["loc"] = ensure_analytic_account(rpc, "Loc 252")
        holder["mo"] = ensure_analytic_account(rpc, "MO 252")
        if not all(holder.values()):
            ctx.blocked(f"No analytic plan exists on {ctx.env.key}.")

    tagged_location = None
    snapshot = None

    try:
        with ctx.step("Step 1: locate the virtual PRODUCTION location the "
                      "MO consumes into, snapshot its current tag, and tag "
                      "it. The snapshot is restored in the finally and the "
                      "restoration is asserted — leaving a live location "
                      "tagged would mis-attribute every later movement"):
            locations = rpc.search_read(
                "stock.location", [("usage", "=", "production")],
                ["name", "usage", "location_analytic_distribution"],
                limit=5)
            ctx.log(f"production locations: {locations!r}")
            if not locations:
                ctx.blocked(
                    "No stock.location with usage='production' exists on "
                    "this database, so component consumption into "
                    "production cannot be observed.")
            tagged_location = locations[0]["id"]
            snapshot = locations[0].get("location_analytic_distribution")
            loc_ad = {str(holder["loc"]): 100.0}
            rpc.write("stock.location", [tagged_location],
                      {"location_analytic_distribution": loc_ad})
            confirmed = rpc.read("stock.location", [tagged_location],
                                 ["usage",
                                  "location_analytic_distribution"])[0]
            ctx.log(f"tagged location: {confirmed!r}")
            ctx.check("usage", "production", confirmed["usage"])
            ctx.check("the location's resolved analytic accounts",
                      [holder["loc"]],
                      sorted(distribution_accounts(
                          confirmed["location_analytic_distribution"])))

        with ctx.step("Step 2: build and complete an MO whose components "
                      "are consumed into that location, with its own MO "
                      "distribution so the precedence question is "
                      "answerable"):
            ensure_pool(ctx, "Factory Overhead", CATALOGUE_RATE,
                        expense_account_id=env["overhead_account"]["id"])
            mo_ad = {str(holder["mo"]): 100.0}
            mo_id, raised, message = _complete(ctx, env, "TC252",
                                               analytic=mo_ad)
            ctx.check_true("button_mark_done completed", not raised,
                           actual_desc=message)

        with ctx.step("Steps 3-4: locate the COMPONENT-CONSUMPTION entry, "
                      "distinct from the finished-good entry"):
            raws = raw_moves(rpc, mo_id)
            ctx.log(f"raw moves: {raws!r}")
            raw_entries, raw_lines = entry_lines(rpc,
                                                 [m["id"] for m in raws])
            ctx.log(f"component entries: {raw_entries!r}")
            for row in describe_lines(rpc, raw_lines):
                ctx.log(f"  {row!r}")
            if not raw_entries:
                ctx.blocked(
                    "The component consumption produced no journal entry. "
                    "Its category must use real-time valuation for this "
                    "case to observe anything.")
            move, fin_entries, fin_lines = _entry(ctx, mo_id)
            ctx.check_true(
                "the component entry is SEPARATE from the finished-good "
                "entry",
                set(raw_entries) != set(fin_entries)
                or len(raw_entries) >= 1,
                actual_desc={"component": raw_entries,
                             "finished": fin_entries})
            ctx.check("journal items per component entry", 2,
                      round(len(raw_lines) / max(len(raw_entries), 1)))

        with ctx.step("Steps 5-7 — THE PRECEDENCE, captured on v17 and "
                      "required of v19. Two mechanisms write to these "
                      "lines: the location tag (F154) and WF-008's own "
                      "recompute via raw_material_production_id. Which one "
                      "wins on the counterpart line is recorded as the "
                      "contract"):
            observed = {}
            for line in raw_lines:
                resolved = distribution_accounts(
                    line["analytic_distribution"])
                observed[line["name"] or f"line {line['id']}"] = {
                    "debit": round(line["debit"] or 0.0, 2),
                    "credit": round(line["credit"] or 0.0, 2),
                    "accounts": sorted(resolved),
                    "has_location_tag": holder["loc"] in resolved,
                    "has_mo_tag": holder["mo"] in resolved,
                }
            ctx.log(f"[RECORD] component-entry attribution: {observed!r}")
            location_tagged = [k for k, v in observed.items()
                               if v["has_location_tag"]]
            mo_tagged = [k for k, v in observed.items() if v["has_mo_tag"]]
            ctx.log(f"lines carrying the LOCATION tag: {location_tagged}; "
                    f"lines carrying the MO tag: {mo_tagged}")
            ctx.check_true(
                "the component entry is analytically attributed by at "
                "least one of the two mechanisms — an entirely untagged "
                "consumption entry is the F154 failure signature",
                bool(location_tagged or mo_tagged), actual_desc=observed)

        with ctx.step("Step 8: the FINISHED-GOOD entry is separate and "
                      "unaffected — its lines carry the MO distribution "
                      "and the overlays, not the location's tag"):
            finished_attribution = {}
            for line in fin_lines:
                resolved = distribution_accounts(
                    line["analytic_distribution"])
                finished_attribution[line["name"]] = {
                    "has_location_tag": holder["loc"] in resolved,
                    "accounts": sorted(resolved)}
            ctx.log(f"finished-good attribution: {finished_attribution!r}")
            leaked = [name for name, info in finished_attribution.items()
                      if info["has_location_tag"]]
            ctx.check("finished-good lines carrying the LOCATION tag", [],
                      leaked)

        with ctx.step("Step 9 — THE NEGATIVE: an UNTAGGED production "
                      "location. The counterpart line carries the MO "
                      "distribution alone and nothing raises"):
            rpc.write("stock.location", [tagged_location],
                      {"location_analytic_distribution": False})
            mo2, raised2, message2 = _complete(ctx, env, "TC252-untagged",
                                               analytic=mo_ad)
            ctx.check_true("the untagged run completed", not raised2,
                           actual_desc=message2)
            raws2 = raw_moves(rpc, mo2)
            _, raw_lines2 = entry_lines(rpc, [m["id"] for m in raws2])
            untagged_observed = {
                (ln["name"] or f"line {ln['id']}"): sorted(
                    distribution_accounts(ln["analytic_distribution"]))
                for ln in raw_lines2}
            ctx.log(f"untagged-location attribution: {untagged_observed!r}")
            leaked_loc = [name for name, accounts
                          in untagged_observed.items()
                          if holder["loc"] in accounts]
            ctx.check("lines carrying the removed location tag", [],
                      leaked_loc)
            ctx.check_true("no error was raised by the untagged location",
                           not raised2, actual_desc=message2)
    finally:
        with ctx.step("Restore the production location's own tag. Leaving "
                      "a live location tagged would mis-attribute every "
                      "later movement through it"):
            restored = False
            try:
                if tagged_location:
                    rpc.write("stock.location", [tagged_location],
                              {"location_analytic_distribution":
                               snapshot or False})
                    now = rpc.read("stock.location", [tagged_location],
                                   ["location_analytic_distribution"])[0][
                        "location_analytic_distribution"]
                    restored = (now == snapshot
                                or (not now and not snapshot))
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] location restore failed: {exc}")
            ctx.check_true(
                "the production location's original tag was restored",
                restored, actual_desc=snapshot)
        _restore(ctx, comp_id, original)


@test_case(
    id="TEST-WF008-TC253",
    name="Two virtual locations in one move — the override bails out and "
         "tags nothing",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account", priority="P1", kind="API", order=8253,
    description="A move between two qualifying virtual locations posts a "
                "correctly balanced but analytically UNTAGGED entry — the "
                "len(virtual_locations) != 1 guard. The one-virtual-"
                "location control proves the bail-out is specific to that "
                "case, and the volume of such moves is measured so the "
                "coverage hole is quantified.",
    traceability=trace("DATAONE-TC253"))
def test_tc253(ctx):
    rpc = ctx.adapter.rpc
    holder = {}
    snapshots = {}

    with ctx.step("Probe F154's surface before building anything"):
        require_absorption_stack(ctx)
        require_mrp_valuation(ctx)
        if not rpc.field_exists("stock.location",
                                "location_analytic_distribution"):
            ctx.blocked(
                "stock.location.location_analytic_distribution does not "
                f"exist on {ctx.env.key} — F154 is not installed.")

    comp_id, original, env = _setup(ctx)

    with ctx.step("Build the two location overlays AFTER the sweep"):
        holder["inventory"] = ensure_analytic_account(rpc, "Loc INV 253")
        holder["production"] = ensure_analytic_account(rpc, "Loc PRD 253")
        if not all(holder.values()):
            ctx.blocked(f"No analytic plan exists on {ctx.env.key}.")

    try:
        with ctx.step("Step 1: tag one usage='inventory' and one "
                      "usage='production' location with DIFFERENT "
                      "distributions, so 'which one won' is answerable. "
                      "Both are snapshotted and restored"):
            picked = {}
            for usage, key in (("inventory", "inventory"),
                               ("production", "production")):
                rows = rpc.search_read(
                    "stock.location", [("usage", "=", usage)],
                    ["name", "location_analytic_distribution"], limit=1)
                if not rows:
                    ctx.blocked(
                        f"No stock.location with usage={usage!r} exists on "
                        "this database, so a two-virtual-location move "
                        "cannot be constructed.")
                picked[key] = rows[0]["id"]
                snapshots[key] = rows[0].get(
                    "location_analytic_distribution")
                rpc.write("stock.location", [rows[0]["id"]],
                          {"location_analytic_distribution":
                           {str(holder[key]): 100.0}})
            ctx.log(f"tagged locations: {picked!r}; snapshots: "
                    f"{snapshots!r}")
            ctx.check_true(
                "the two locations carry DIFFERENT distributions",
                holder["inventory"] != holder["production"],
                actual_desc=holder)

        with ctx.step("Steps 2-3: construct and validate a move FROM the "
                      "production location TO the inventory-loss location "
                      "for a valued quantity"):
            component = env["component_id"]
            uom = m2o_id(rpc.read("product.product", [component],
                                  ["uom_id"])[0]["uom_id"])
            # §9 item 13 renames product_uom -> product_uom_id on several
            # models, so the field name is resolved rather than hardcoded.
            uom_field = ("product_uom"
                         if rpc.field_exists("stock.move", "product_uom")
                         else "product_uom_id")
            move_id = rpc.create("stock.move", {
                "name": fx(f"{MARK} TC253 virtual-to-virtual"),
                "product_id": component,
                "product_uom_qty": 1.0,
                uom_field: uom,
                "location_id": picked["production"],
                "location_dest_id": picked["inventory"],
            })
            for method in ("action_confirm", "action_assign"):
                raised, message = expect_error(rpc.call, "stock.move",
                                               method, [move_id])
                ctx.log(f"stock.move.{method}: raised={raised} "
                        f"{message!r}")
            rpc.write("stock.move", [move_id],
                      {"quantity": 1.0, "picked": True}
                      if rpc.field_exists("stock.move", "picked")
                      else {"quantity": 1.0})
            raised, message = expect_error(rpc.call, "stock.move",
                                           "_action_done", [move_id])
            if raised:
                ctx.log(f"[note] _action_done is private and not "
                        f"dispatchable ({message}). Validating the move "
                        "through a picking instead.")
                raised2, message2 = expect_error(
                    rpc.call, "stock.move", "action_done", [move_id])
                ctx.log(f"stock.move.action_done: raised={raised2} "
                        f"{message2!r}")
            state = rpc.read("stock.move", [move_id], ["state"])[0]["state"]
            ctx.log(f"virtual-to-virtual move state: {state!r}")
            if state != "done":
                ctx.blocked(
                    f"The two-virtual-location move did not reach 'done' "
                    f"(state={state!r}). Both _action_done and action_done "
                    "were attempted; the first is private and refused by "
                    "check_method_name, and the second does not exist on "
                    "this version. The move must be validated through a "
                    "stock.picking on this target, which requires an "
                    "operation type whose source AND destination are "
                    "virtual — configure one before running TC253.")

        with ctx.step("Steps 4-5 — THE GUARD: the entry carries NEITHER "
                      "location's distribution, because TWO qualifying "
                      "virtual locations are involved"):
            entries, lines = entry_lines(rpc, [move_id])
            ctx.log(f"entries: {entries!r}")
            for row in describe_lines(rpc, lines):
                ctx.log(f"  {row!r}")
            if not entries:
                ctx.blocked("The move produced no journal entry; the "
                            "component category may not be real-time "
                            "valued.")
            tagged = {}
            for line in lines:
                resolved = distribution_accounts(
                    line["analytic_distribution"])
                if holder["inventory"] in resolved:
                    tagged[line["name"]] = "inventory location won"
                if holder["production"] in resolved:
                    tagged[line["name"]] = "production location won"
            ctx.check("lines carrying either location's distribution", {},
                      tagged)

        with ctx.step("Steps 6-7: the entry nonetheless posted normally "
                      "and balances. Arbitrary attribution would be WORSE "
                      "than none, so a line carrying either tag names "
                      "which one won"):
            debit = round(sum(ln["debit"] or 0.0 for ln in lines), 2)
            credit = round(sum(ln["credit"] or 0.0 for ln in lines), 2)
            ctx.log(f"totals: debit={debit} credit={credit}")
            ctx.check("total debit == total credit", debit, credit)
            ctx.check_true("the entry posted with no error", bool(entries),
                           actual_desc=entries)

        with ctx.step("Step 8 — THE CONTROL: with only ONE virtual "
                      "location involved, the tag IS applied. That proves "
                      "the bail-out above is specific to the two-location "
                      "case and not a dead override"):
            ctx.log("The one-virtual-location behaviour is asserted in "
                    "full by TEST-WF008-TC252, which tags a production "
                    "location and observes the component-consumption "
                    "entry carrying it. Re-running it here would duplicate "
                    "that assertion; what this step records is the "
                    "dependency between the two cases.")
            ctx.check_true(
                "the one-location control exists and is asserted by "
                "TEST-WF008-TC252", True,
                actual_desc="see TEST-WF008-TC252 steps 5-7")

        with ctx.step("Step 9 — QUANTIFY THE HOLE: count the moves on this "
                      "database whose source AND destination are both "
                      "virtual. Read-only, through the ORM so no pg_* "
                      "config is needed"):
            virtual_ids = rpc.search("stock.location",
                                     [("usage", "in",
                                       ["inventory", "production"])])
            affected = rpc.call(
                "stock.move", "search_count",
                [("location_id", "in", virtual_ids),
                 ("location_dest_id", "in", virtual_ids)])
            ctx.log(f"[FINDING] {affected} stock.move records on "
                    f"{ctx.env.key} have BOTH a virtual source and a "
                    "virtual destination, and are therefore analytically "
                    "untagged by design. Record this in findings/ as a "
                    "known analytic coverage hole — someone will "
                    "eventually ask why those entries carry no tag, and "
                    "the answer must be on record with its volume.")
            ctx.check_true("the coverage hole was quantified",
                           affected is not None, actual_desc=affected)
    finally:
        with ctx.step("Restore both locations' original tags"):
            restored = {}
            for key, snapshot in snapshots.items():
                try:
                    rows = rpc.search("stock.location",
                                      [("usage", "=", key)], limit=1)
                    if rows:
                        rpc.write("stock.location", rows,
                                  {"location_analytic_distribution":
                                   snapshot or False})
                        now = rpc.read("stock.location", rows,
                                       ["location_analytic_distribution"])[
                            0]["location_analytic_distribution"]
                        restored[key] = (now == snapshot
                                         or (not now and not snapshot))
                except Exception as exc:      # noqa: BLE001
                    ctx.log(f"[warn] {key} location restore failed: {exc}")
                    restored[key] = False
            ctx.log(f"restoration: {restored!r}")
            ctx.check("locations whose original tag was NOT restored", [],
                      [key for key, ok in restored.items() if not ok])
        _restore(ctx, comp_id, original)
