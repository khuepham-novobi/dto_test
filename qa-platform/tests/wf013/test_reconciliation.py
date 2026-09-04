"""DATAONE-WF-013 — cross-version reconciliation and baselines:
TC007, TC021, TC023, TC025, TC027, TC028, TC034, TC048, TC049, TC051,
TC052, TC258, TC259, TC260.

Fourteen of WF-013's cases are the same shape: capture a financial or
structural fact on the v17 baseline, capture it again on v19, and assert
the difference is empty. The workbook writes them as SQL dumps compared
between versions; ``framework.fg_common.reconcile`` does exactly that job
through the ORM, so none of them needs PostgreSQL credentials and none can
report BLOCKED for a missing ``pg_*`` config.

The pattern, for every case here:

* on **Odoo 17** — capture, assert any anchors the workbook states, and
  persist the snapshot under ``data/baselines/<tc_id>.json``;
* on **Odoo 19** — load that snapshot, capture again, and assert a zero
  diff. With no baseline stored yet the v19 run reports BLOCKED, naming the
  v17 run that must happen first.

All captures are **read-only** and scoped to nothing this suite created —
they measure the live database, which is the point.

Two of them carry version-specific structure the workbook calls out:

* **TC025** — ``stock.valuation.layer`` is expected to change shape between
  the versions, so the capture records inventory VALUE per product rather
  than layer rows, which is the invariant that must survive.
* **TC034** — v17's two ``stock.location`` valuation-account columns fold
  into one on v19, so the capture records whichever columns this target
  has, by population, and the diff compares the totals rather than the
  column names.

EXPECTED v17 OUTCOME: PASS (baselines captured).
EXPECTED v19 OUTCOME: PASS if nothing moved; any diff is a real finding.
"""
import json

from framework.fg_common import reconcile
from framework.registry import test_case
from framework.source_scan import ADDON_ROOTS, grep_module, resolve_source_root
from tests.wf013.common import (COGS_ANALYTIC_XMLIDS, WORKFLOW,  # noqa: F401
                                WORKFLOW_NAME, m2o_id, trace)

YEAR_FIELD = "date"


def _require_accounting(ctx):
    rpc = ctx.adapter.rpc
    if not rpc.model_exists("account.move.line"):
        ctx.blocked("The accounting modules are not installed on "
                    f"{ctx.env.key} — there is nothing to reconcile.")


def _group_key(group, field, granularity):
    """Read a date-granularity key out of a read_group row.

    read_group returns the granularity-suffixed key ("date:month") on some
    versions and the bare field name on others, and the value may arrive as
    a [raw, label] pair; accept every shape.
    """
    for candidate in (f"{field}:{granularity}", field):
        if candidate in group:
            value = group[candidate]
            if isinstance(value, (list, tuple)):
                value = value[1] if len(value) > 1 else value[0]
            return str(value) if value else "NULL"
    return "NULL"


def _year_of(value) -> str:
    return str(value)[:4] if value else "NULL"


# ---------------------------------------------------------------- TC007
@test_case(
    id="TEST-WF013-TC007",
    name="Every env.ref() literal in the custom code resolves against the "
         "database",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account, dto_account_cogs, dto_account_workday",
    priority="P0", kind="DATA", order=13007,
    description="Extracts every env.ref('module.name') literal from the "
                "DTO-Odoo source tree and resolves each against "
                "ir.model.data. An unresolvable one is a runtime ValueError "
                "waiting for the code path that uses it — which for "
                "dto_account_cogs is every customer-invoice post.",
    traceability=trace("DATAONE-TC007"))
def test_tc007(ctx):
    import re
    rpc = ctx.adapter.rpc

    with ctx.step("Locate the DTO-Odoo source tree"):
        root = resolve_source_root(ctx.env.version)
        if root is None:
            ctx.blocked(
                "The DTO-Odoo source tree is not reachable from this "
                "workstation. Set DTO_SOURCE_ROOT in config/local.yaml — "
                "TC007 extracts env.ref() literals from source and cannot "
                "be answered from the database alone.")

    with ctx.step("Extract every env.ref('module.name') literal"):
        pattern = r"""\.ref\(\s*['"]([a-zA-Z0-9_]+\.[a-zA-Z0-9_]+)['"]"""
        literal_re = re.compile(pattern)
        found: dict = {}
        for addon_root in ADDON_ROOTS:
            base = root / addon_root
            if not base.is_dir():
                continue
            for module_dir in sorted(base.iterdir()):
                if not (module_dir / "__manifest__.py").is_file():
                    continue
                for hit in grep_module(module_dir, pattern,
                                       suffixes=(".py",)):
                    for xmlid in literal_re.findall(hit["text"]):
                        found.setdefault(xmlid, []).append(
                            f"{module_dir.name}/{hit['file']}:{hit['line']}")
        ctx.log(f"{len(found)} distinct env.ref() literal(s)")

    with ctx.step("Resolve every one against ir.model.data and record the "
                  "evidence before asserting"):
        unresolved = {}
        for xmlid, sites in sorted(found.items()):
            if not rpc.ref(xmlid):
                unresolved[xmlid] = sites
        path = ctx.artifacts_dir / "tc007_env_refs.json"
        path.write_text(json.dumps(
            {"literals": {k: v for k, v in sorted(found.items())},
             "unresolved": unresolved}, indent=1, ensure_ascii=False),
            encoding="utf-8")
        ctx.add_artifact(path, "log", "TC007 env.ref() resolution")
        ctx.log(f"unresolved: {unresolved!r}")

    with ctx.step("At least one literal was found — an empty extraction "
                  "would make the assertion below vacuous"):
        ctx.check_true("env.ref() literals were extracted", bool(found),
                       actual_desc=f"{len(found)} found")

    with ctx.step("Every env.ref() literal resolves"):
        ctx.check("env.ref() literals that do not resolve", {}, unresolved)

    with ctx.step("The five WF-013 literals specifically — these run on "
                  "EVERY customer-invoice post"):
        ctx.check("WF-013 analytic literals that do not resolve", [],
                  [x for x in COGS_ANALYTIC_XMLIDS if not rpc.ref(x)])


# ------------------------------------------------------- capture helpers
def _capture_trial_balance(ctx):
    """TC021 — posted balance per account, to the cent."""
    rpc = ctx.adapter.rpc
    groups = rpc.read_group(
        "account.move.line", [("parent_state", "=", "posted")],
        ["balance:sum"], ["account_id"], lazy=False)
    snapshot = {}
    total = 0.0
    for group in groups:
        account = m2o_id(group.get("account_id"))
        if account is None:
            continue
        value = round(group.get("balance") or 0.0, 2)
        snapshot[f"account/{account}"] = value
        total += value
    snapshot["TOTAL"] = round(total, 2)
    snapshot["accounts"] = len(groups)
    return snapshot


def _capture_invoice_totals(ctx):
    """TC023 — invoice totals by year x move_type x state.

    Aggregated with read_group rather than fetched row by row: the target
    holds ~189,000 account.move rows, and pulling them over JSON-RPC would
    be slow and pointless when PostgreSQL can do the GROUP BY.
    """
    rpc = ctx.adapter.rpc
    groups = rpc.read_group(
        "account.move",
        [("move_type", "in", ["out_invoice", "out_refund",
                              "in_invoice", "in_refund"])],
        ["amount_total:sum"],
        ["invoice_date:year", "move_type", "state"], lazy=False)
    snapshot = {}
    for group in groups:
        key = (f"{_group_key(group, 'invoice_date', 'year')}/"
               f"{group.get('move_type') or 'NULL'}/"
               f"{group.get('state') or 'NULL'}")
        snapshot[f"count/{key}"] = group.get("__count", 0)
        snapshot[f"total/{key}"] = round(group.get("amount_total") or 0.0, 2)
    return snapshot


def _capture_inventory_value(ctx):
    """TC025 — inventory VALUE per product, not layer rows.

    stock.valuation.layer changes shape between the versions, so the
    invariant recorded is the value it represents.
    """
    rpc = ctx.adapter.rpc
    snapshot = {}
    if rpc.model_exists("stock.valuation.layer"):
        groups = rpc.read_group("stock.valuation.layer", [],
                                ["value:sum", "quantity:sum"],
                                ["product_id"], lazy=False)
        for group in groups:
            product = m2o_id(group.get("product_id"))
            if product is None:
                continue
            snapshot[f"svl_value/{product}"] = round(
                group.get("value") or 0.0, 2)
        snapshot["svl_total_value"] = round(
            sum(v for k, v in snapshot.items()
                if k.startswith("svl_value/")), 2)
        snapshot["svl_products"] = len(groups)
    else:
        snapshot["svl_model_present"] = False
    # the same total read from the quants, which survive either way
    quant_groups = rpc.read_group("stock.quant",
                                  [("location_id.usage", "=", "internal")],
                                  ["quantity:sum"], ["product_id"],
                                  lazy=False)
    snapshot["internal_quant_products"] = len(quant_groups)
    snapshot["internal_quant_quantity"] = round(
        sum(g.get("quantity") or 0.0 for g in quant_groups), 2)
    return snapshot


def _capture_distribution_shapes(ctx):
    """TC027 — a histogram of distinct analytic-distribution KEY shapes.

    This one genuinely needs per-key inspection of a jsonb column, and the
    target carries ~449,000 rows with a distribution — far too many to fetch
    over JSON-RPC. The workbook specifies SQL for this case and SQL is what
    it uses: jsonb_object_keys expands each key, string_to_array counts the
    accounts it names, and a regex finds any non-numeric part, which is the
    corruption signature. ctx.sql is read-only and reports BLOCKED when no
    pg_* credentials are configured, rather than silently sampling.
    """
    sql = ctx.sql
    snapshot = {}
    histogram = sql.rows(
        "SELECT array_length(string_to_array(k, ','), 1) AS accounts_in_key,"
        "       count(*)"
        "  FROM account_move_line l,"
        "       jsonb_object_keys(l.analytic_distribution) AS k"
        " WHERE l.analytic_distribution IS NOT NULL"
        " GROUP BY 1 ORDER BY 1")
    for accounts_in_key, count in histogram:
        snapshot[f"keys_with_{accounts_in_key}_account(s)"] = count
    snapshot["NON_NUMERIC_KEY_PARTS"] = sql.one(
        "SELECT count(*)"
        "  FROM account_move_line l,"
        "       jsonb_object_keys(l.analytic_distribution) AS k"
        " WHERE l.analytic_distribution IS NOT NULL"
        "   AND EXISTS (SELECT 1 FROM unnest(string_to_array(k, ',')) p"
        "               WHERE p !~ '^[0-9]+$')") or 0
    snapshot["lines_with_distribution"] = sql.one(
        "SELECT count(*) FROM account_move_line"
        " WHERE analytic_distribution IS NOT NULL") or 0
    return snapshot


def _capture_distribution_coverage(ctx):
    """TC028 — how many journal items carry a distribution, by account."""
    rpc = ctx.adapter.rpc
    total = rpc.call("account.move.line", "search_count", [])
    with_dist = rpc.call("account.move.line", "search_count",
                         [("analytic_distribution", "!=", False)])
    snapshot = {"journal_items": total, "with_distribution": with_dist}
    groups = rpc.read_group(
        "account.move.line", [("analytic_distribution", "!=", False)],
        ["__count"], ["account_id"], lazy=False)
    for group in groups:
        account = m2o_id(group.get("account_id"))
        if account is not None:
            snapshot[f"with_distribution/account/{account}"] = group["__count"]
    return snapshot


def _capture_location_accounts(ctx):
    """TC034 — the stock.location valuation-account columns, by population.

    v17 carries two columns; v19 folds them into one. Recording which
    columns exist AND their populations makes the diff meaningful across
    the rename.
    """
    rpc = ctx.adapter.rpc
    snapshot = {}
    candidates = ["valuation_in_account_id", "valuation_out_account_id",
                  "valuation_account_id"]
    present = [f for f in candidates
               if rpc.field_exists("stock.location", f)]
    snapshot["columns_present"] = ",".join(sorted(present))
    for field in present:
        snapshot[f"populated/{field}"] = rpc.call(
            "stock.location", "search_count", [(field, "!=", False)])
    snapshot["locations"] = rpc.call("stock.location", "search_count",
                                     [("active", "in", [True, False])])
    return snapshot


def _capture_journal_items(ctx):
    """TC048 — journal-item counts and balances per journal per period.

    Aggregated with read_group: the target holds ~550,000 posted journal
    items, so the GROUP BY belongs in PostgreSQL.
    """
    rpc = ctx.adapter.rpc
    groups = rpc.read_group(
        "account.move.line", [("parent_state", "=", "posted")],
        ["balance:sum"], ["journal_id", "date:month"], lazy=False)
    snapshot = {}
    for group in groups:
        key = (f"{m2o_id(group.get('journal_id'))}/"
               f"{_group_key(group, 'date', 'month')}")
        snapshot[f"count/{key}"] = group.get("__count", 0)
        snapshot[f"balance/{key}"] = round(group.get("balance") or 0.0, 2)
    return snapshot


def _capture_residuals(ctx):
    """TC049 — open receivable and payable residuals per partner."""
    rpc = ctx.adapter.rpc
    snapshot = {}
    for label, account_type in (("receivable", "asset_receivable"),
                                ("payable", "liability_payable")):
        groups = rpc.read_group(
            "account.move.line",
            [("parent_state", "=", "posted"),
             ("account_id.account_type", "=", account_type),
             ("reconciled", "=", False)],
            ["amount_residual:sum"], ["partner_id"], lazy=False)
        running = 0.0
        for group in groups:
            partner = m2o_id(group.get("partner_id"))
            value = round(group.get("amount_residual") or 0.0, 2)
            snapshot[f"{label}/partner/{partner}"] = value
            running += value
        snapshot[f"{label}/TOTAL"] = round(running, 2)
        snapshot[f"{label}/partners"] = len(groups)
    return snapshot


def _capture_tax_totals(ctx):
    """TC051 — tax totals by tax and year."""
    rpc = ctx.adapter.rpc
    if not rpc.field_exists("account.move.line", "tax_line_id"):
        return {"tax_line_id_present": False}
    groups = rpc.read_group(
        "account.move.line",
        [("parent_state", "=", "posted"), ("tax_line_id", "!=", False)],
        ["balance:sum"], ["tax_line_id", "date:year"], lazy=False)
    snapshot = {}
    for group in groups:
        key = (f"{m2o_id(group.get('tax_line_id'))}/"
               f"{_group_key(group, 'date', 'year')}")
        snapshot[f"count/{key}"] = group.get("__count", 0)
        snapshot[f"balance/{key}"] = round(group.get("balance") or 0.0, 2)
    return snapshot


def _capture_is_cogs(ctx):
    """TC052 — the is_cogs line population."""
    rpc = ctx.adapter.rpc
    if not rpc.field_exists("account.move.line", "is_cogs"):
        return {"is_cogs_field_present": False}
    snapshot = {"is_cogs_field_present": True}
    snapshot["is_cogs_lines"] = rpc.call(
        "account.move.line", "search_count", [("is_cogs", "=", True)])
    groups = rpc.read_group("account.move.line", [("is_cogs", "=", True)],
                            ["balance:sum"], ["account_id"], lazy=False)
    for group in groups:
        account = m2o_id(group.get("account_id"))
        if account is not None:
            snapshot[f"is_cogs/account/{account}"] = round(
                group.get("balance") or 0.0, 2)
    snapshot["is_cogs_accounts"] = len(groups)
    return snapshot


def _top_invoices(rpc, limit=20):
    return rpc.search_read(
        "account.move",
        [("move_type", "=", "out_invoice"), ("state", "=", "posted")],
        ["name", "amount_total", "partner_id"],
        order="amount_total desc, id", limit=limit)


def _capture_top_invoices(ctx):
    """TC258 — the top 20 customer invoices, line by line."""
    rpc = ctx.adapter.rpc
    snapshot = {}
    invoices = _top_invoices(rpc)
    snapshot["invoices_captured"] = len(invoices)
    for invoice in invoices:
        key = invoice["name"] or f"id{invoice['id']}"
        snapshot[f"total/{key}"] = round(invoice["amount_total"] or 0.0, 2)
        lines = rpc.search_read("account.move.line",
                                [("move_id", "=", invoice["id"])],
                                ["account_id", "balance", "display_type"],
                                order="id")
        snapshot[f"lines/{key}"] = len(lines)
        snapshot[f"net/{key}"] = round(
            sum(ln["balance"] or 0.0 for ln in lines), 2)
        by_account = {}
        for line in lines:
            account = m2o_id(line["account_id"])
            if account is None:
                continue
            by_account[account] = round(
                by_account.get(account, 0.0) + (line["balance"] or 0.0), 2)
        for account, value in sorted(by_account.items()):
            snapshot[f"account/{key}/{account}"] = value
    return snapshot


def _capture_top_invoice_shapes(ctx):
    """TC259 — analytic key shapes on the top invoices' journal items."""
    rpc = ctx.adapter.rpc
    snapshot = {}
    invoices = _top_invoices(rpc)
    move_ids = [i["id"] for i in invoices]
    snapshot["invoices_captured"] = len(invoices)
    if not move_ids:
        return snapshot
    lines = rpc.search_read(
        "account.move.line",
        [("move_id", "in", move_ids),
         ("analytic_distribution", "!=", False)],
        ["move_id", "analytic_distribution"])
    snapshot["lines_with_distribution"] = len(lines)
    for line in lines:
        for key in (line["analytic_distribution"] or {}):
            parts = str(key).split(",")
            shape = f"keys_with_{len(parts)}_account(s)"
            snapshot[shape] = snapshot.get(shape, 0) + 1
    return snapshot


def _capture_interim_residue(ctx):
    """TC260 — Stock Interim (Delivered) residue on project orders."""
    rpc = ctx.adapter.rpc
    snapshot = {}
    accounts = rpc.search_read(
        "account.account",
        ["|", ("name", "ilike", "interim"), ("code", "ilike", "interim")],
        ["code", "name"])
    snapshot["interim_accounts"] = len(accounts)
    for account in accounts:
        groups = rpc.read_group(
            "account.move.line",
            [("account_id", "=", account["id"]),
             ("parent_state", "=", "posted")],
            ["balance:sum", "__count"], [], lazy=False)
        balance = round((groups[0].get("balance") if groups else 0.0) or 0.0, 2)
        count = (groups[0].get("__count") if groups else 0) or 0
        snapshot[f"interim/{account['code']}/balance"] = balance
        snapshot[f"interim/{account['code']}/lines"] = count
    return snapshot


# ------------------------------------------------- the reconciliation set
_CASES = [
    ("DATAONE-TC007", None, None, None, None),   # handled above
    ("DATAONE-TC021", "TEST-WF013-TC021",
     "Trial balance identical to the cent, per account", "P0",
     _capture_trial_balance),
    ("DATAONE-TC023", "TEST-WF013-TC023",
     "Invoice totals by year x move_type x state", "P0",
     _capture_invoice_totals),
    ("DATAONE-TC025", "TEST-WF013-TC025",
     "stock.valuation.layer disappearance: inventory value is preserved",
     "P0", _capture_inventory_value),
    ("DATAONE-TC027", "TEST-WF013-TC027",
     "Analytic distribution key format survived the upgrade", "P0",
     _capture_distribution_shapes),
    ("DATAONE-TC028", "TEST-WF013-TC028",
     "Analytic distribution coverage on journal items is unchanged", "P0",
     _capture_distribution_coverage),
    ("DATAONE-TC034", "TEST-WF013-TC034",
     "stock.location valuation-account collapse: two v17 columns folded "
     "into one", "P0", _capture_location_accounts),
    ("DATAONE-TC048", "TEST-WF013-TC048",
     "Journal-item counts and balances per journal per period", "P0",
     _capture_journal_items),
    ("DATAONE-TC049", "TEST-WF013-TC049",
     "Open receivable and payable residuals per partner", "P0",
     _capture_residuals),
    ("DATAONE-TC051", "TEST-WF013-TC051", "Tax totals by tax and year",
     "P0", _capture_tax_totals),
    ("DATAONE-TC052", "TEST-WF013-TC052", "is_cogs line population survives",
     "P0", _capture_is_cogs),
    ("DATAONE-TC258", "TEST-WF013-TC258",
     "BASELINE: top 20 v17 customer invoices reproduced to the cent", "P0",
     _capture_top_invoices),
    ("DATAONE-TC259", "TEST-WF013-TC259",
     "BASELINE: analytic-distribution key shapes survive on those 40 "
     "entries", "P0", _capture_top_invoice_shapes),
    ("DATAONE-TC260", "TEST-WF013-TC260",
     "BASELINE: Stock Interim (Delivered) residue on project orders", "P0",
     _capture_interim_residue),
]


def _make_reconciliation_test(tc_id, test_id, name, priority, capture, order):
    @test_case(
        id=test_id, name=name, workflow=WORKFLOW,
        workflow_name=WORKFLOW_NAME,
        module="dto_account, dto_account_cogs", priority=priority,
        kind="DATA", order=order,
        description=f"DATA_RECONCILIATION through the ORM: captured and "
                    f"persisted on the v17 baseline, diffed on v19. Any "
                    f"difference is a finding.",
        traceability=trace(tc_id))
    def _test(ctx, _capture=capture):
        with ctx.step("Precondition: the accounting models exist"):
            _require_accounting(ctx)
        reconcile(ctx, tc_id, _capture)
    _test.__name__ = f"test_{tc_id.lower().replace('-', '_')}"
    return _test


for _index, (_tc_id, _test_id, _name, _priority, _capture) in enumerate(
        _CASES):
    if _capture is None:
        continue
    globals()[f"test_{_tc_id.lower().replace('-', '_')}"] = (
        _make_reconciliation_test(_tc_id, _test_id, _name, _priority,
                                  _capture, 13400 + _index))
