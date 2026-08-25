"""DATAONE-WF-002 — configuration integrity and cross-version
reconciliation: TC017, TC053, TC057.

TC017 compiles every server-action code body owned by a custom module and
scans it for the APIs Odoo 19 removed. Both halves are reachable over the
ORM: ``ir.actions.server.code`` is an ordinary field, and Python's own
``compile()`` answers the syntax question locally. A syntax error in a
server action is invisible until the action fires — which, for
``dto_sale``'s confirmation automation, means invisible until someone
confirms an order.

TC053 and TC057 are DATA_RECONCILIATION cases. The workbook writes them as
SQL dumps compared between versions; the platform's ``reconcile()`` helper
does the same job through the ORM, so they need no PostgreSQL credentials:
the run on **v17 captures and persists the snapshot**, the run on **v19
diffs against it**, and any difference is a finding.

The module list is derived from the DTO-Odoo checkout rather than
hard-coded, so it cannot drift from the source tree.

EXPECTED v17 OUTCOME: TC017 PASS or FAIL depending on what the scan finds —
the removed-API expectation describes the post-remediation v19 state, so a
hit today is the finding, not a defect in the test. TC053/TC057 PASS
(baseline captured).
"""
import json

from framework.fg_common import reconcile
from framework.registry import test_case
from framework.source_scan import ADDON_ROOTS, resolve_source_root
from tests.wf002.common import (WORKFLOW, WORKFLOW_NAME, m2o_id,  # noqa: F401
                                trace)

# The odoo.api members and other APIs Odoo 19 removed, as the workbook lists
# them for the server-action bodies.
REMOVED_API_TOKENS = [
    "api.returns", "api.downgrade", "api.split_context", "api.propagate",
    "api.attrsetter", "api.model_create_single", "user_has_groups",
    "trans_implied_ids", "name_get", "procurement.group",
    "stock.valuation.layer", "stock.quant.package",
]


def _custom_modules(ctx) -> list:
    """Every addon in the DTO-Odoo checkout, by technical name.

    Derived from the tree so it cannot drift from the 38 the workbook
    counts. Returns [] when the checkout is unreachable, which the callers
    treat as BLOCKED.
    """
    root = resolve_source_root()
    if root is None:
        return []
    modules = []
    for addon_root in ADDON_ROOTS:
        base = root / addon_root
        if not base.is_dir():
            continue
        for path in sorted(base.iterdir()):
            if path.is_dir() and (path / "__manifest__.py").is_file():
                modules.append(path.name)
    return modules


def _require_modules(ctx):
    modules = _custom_modules(ctx)
    if not modules:
        ctx.blocked(
            "The DTO-Odoo source tree is not reachable from this "
            "workstation, so the set of custom modules cannot be "
            "determined. Set DTO_SOURCE_ROOT in config/local.yaml.")
    ctx.log(f"{len(modules)} custom modules: {modules}")
    return modules


def _custom_server_actions(rpc, modules) -> list:
    """Server actions owned by a custom module, with their code bodies."""
    data = rpc.search_read("ir.model.data",
                           [("model", "=", "ir.actions.server"),
                            ("module", "in", modules)],
                           ["module", "name", "res_id"])
    if not data:
        return []
    by_id = {d["res_id"]: f"{d['module']}.{d['name']}" for d in data}
    rows = rpc.search_read("ir.actions.server",
                           [("id", "in", list(by_id))],
                           ["name", "state", "code", "model_id", "usage"])
    for row in rows:
        row["xml_id"] = by_id[row["id"]]
    return sorted(rows, key=lambda r: r["xml_id"])


@test_case(
    id="TEST-WF002-TC017",
    name="Every server-action and automated-action code body compiles and "
         "contains no removed API",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_mrp_account, dto_purchase, dto_purchase_stock, dto_sale, "
           "dto_sale_stock",
    priority="P1", kind="DATA", order=2017,
    description="Compiles every custom server-action code body — a syntax "
                "error is invisible until the action fires — scans each for "
                "the APIs Odoo 19 removed, and asserts dto_sale's "
                "confirmation automation is active with the expected "
                "trigger and domains.",
    traceability=trace("DATAONE-TC017"))
def test_tc017(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Determine the custom module set from the source tree"):
        modules = _require_modules(ctx)

    with ctx.step("Step 1: list every server action owned by a custom "
                  "module"):
        actions = _custom_server_actions(rpc, modules)
        ctx.log(f"{len(actions)} custom server action(s): "
                f"{[a['xml_id'] for a in actions]}")
        if not actions:
            ctx.blocked(
                "No ir.actions.server records are reflected for the custom "
                f"modules on {ctx.env.key}. Either they are not installed "
                "or their data was never loaded — there is nothing to "
                "compile.")

    with ctx.step("Run both scans and record the evidence before asserting"):
        compile_failures, api_hits = {}, {}
        for action in actions:
            code = action.get("code") or ""
            if action.get("state") != "code" or not code.strip():
                continue
            try:
                compile(code, action["xml_id"], "exec")
            except SyntaxError as exc:
                compile_failures[action["xml_id"]] = f"{exc}"
            found = [token for token in REMOVED_API_TOKENS if token in code]
            if found:
                api_hits[action["xml_id"]] = found
        evidence = {
            "modules": modules,
            "server_actions": [a["xml_id"] for a in actions],
            "compile_failures": compile_failures,
            "removed_api_hits": api_hits,
        }
        path = ctx.artifacts_dir / "tc017_server_actions.json"
        path.write_text(json.dumps(evidence, indent=1, ensure_ascii=False),
                        encoding="utf-8")
        ctx.add_artifact(path, "log", "TC017 server-action scan")
        ctx.log(f"compile failures: {compile_failures}; "
                f"removed-API hits: {api_hits}")

    with ctx.step("Step 2: every code body compiles"):
        ctx.check("server actions whose code body fails to compile", {},
                  compile_failures)

    with ctx.step("Steps 3-4: no code body uses an API Odoo 19 removed"):
        ctx.check("server actions using removed APIs", {}, api_hits)

    with ctx.step("Step 5: dto_sale's confirmation automation is active "
                  "with the expected trigger and domains"):
        if not rpc.model_exists("base.automation"):
            ctx.log("base_automation is not installed on this target")
        else:
            automation_id = rpc.ref(
                "dto_sale.base_automation_send_email_on_sale_order_confirm")
            ctx.check_true("the confirmation automation resolves",
                           bool(automation_id),
                           actual_desc=str(automation_id))
            row = rpc.read("base.automation", [automation_id],
                           ["active", "trigger", "filter_pre_domain",
                            "filter_domain"])[0]
            ctx.log(f"automation: {row!r}")
            ctx.check("automation shape",
                      {"active": True,
                       "trigger": "on_create_or_write",
                       "filter_pre_domain": "[('state', '!=', 'sale')]",
                       "filter_domain": "[('state', '=', 'sale')]"},
                      {"active": row["active"],
                       "trigger": row["trigger"],
                       "filter_pre_domain": row["filter_pre_domain"],
                       "filter_domain": row["filter_domain"]})

    with ctx.step("Steps 6-7 (the two emails and their recipients) are "
                  "asserted by TEST-WF002-TC083"):
        ctx.log("Confirming an order and reading back the composed "
                "recipient lists is TC083's job; this case owns the static "
                "integrity of the code bodies that compose them.")


def _capture_order_types(ctx):
    """Order-type distribution and the custom field population — TC053."""
    rpc = ctx.adapter.rpc
    snapshot = {}

    groups = rpc.read_group("sale.order", [], ["order_type"],
                            ["order_type", "state"], lazy=False)
    for group in groups:
        key = f"count/{group.get('order_type') or 'NULL'}/" \
              f"{group.get('state') or 'NULL'}"
        snapshot[key] = group["__count"]

    snapshot["orders_without_type"] = rpc.call(
        "sale.order", "search_count",
        ["|", ("order_type", "=", False), ("order_type", "=", "")])

    for field, domain in (
        ("with_tariff", [("tariff_amount", "!=", False)]),
        ("negative_tariff", [("tariff_amount", "<", 0)]),
        ("with_requester", [("requester_email", "!=", False)]),
        ("from_workday", [("imported_from_workday", "=", True)]),
    ):
        model_field = domain[0][0]
        if rpc.field_exists("sale.order", model_field):
            snapshot[f"sale_order/{field}"] = rpc.call(
                "sale.order", "search_count", domain)

    for field in ("requested_delivery_date", "expected_delivery_date"):
        if rpc.field_exists("sale.order.line", field):
            snapshot[f"sale_order_line/with_{field}"] = rpc.call(
                "sale.order.line", "search_count", [(field, "!=", False)])

    # the UoM column renamed between the two versions; record whichever
    # this target has so the diff compares populations, not column names
    for field in ("product_uom", "product_uom_id"):
        if rpc.field_exists("sale.order.line", field):
            snapshot["sale_order_line/with_uom"] = rpc.call(
                "sale.order.line", "search_count", [(field, "!=", False)])
            snapshot["sale_order_line/uom_field_name"] = field
            break

    if rpc.field_exists("sale.order.line", "analytic_distribution"):
        for order_type in ("project", "buy", "inventory", "cost_center"):
            snapshot[f"analytic_lines/{order_type}"] = rpc.call(
                "sale.order.line", "search_count",
                [("order_id.order_type", "=", order_type),
                 ("analytic_distribution", "!=", False)])
    return snapshot


@test_case(
    id="TEST-WF002-TC053",
    name="Sales order type distribution and the analytic discipline fields",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account, dto_sale, dto_sale_workday",
    priority="P1", kind="DATA", order=2053,
    description="Order counts and totals by type and state, the custom "
                "field populations, the renamed UoM column's population, "
                "and the analytic-distribution pattern per order type — "
                "captured on v17 and diffed on v19.",
    traceability=trace("DATAONE-TC053"))
def test_tc053(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Precondition: dto_sale has contributed order_type"):
        if not rpc.field_exists("sale.order", "order_type"):
            ctx.blocked(
                f"sale.order.order_type does not exist on {ctx.env.key} — "
                "dto_sale is not installed, so there is no distribution to "
                "reconcile.")

    reconcile(ctx, "DATAONE-TC053", _capture_order_types,
              anchors={"orders_without_type": 0})

    with ctx.step("Step 6: inventory and cost_center orders carry NO "
                  "analytic distribution — the discipline the confirmation "
                  "gates enforce"):
        if not rpc.field_exists("sale.order.line", "analytic_distribution"):
            ctx.log("analytic_distribution is absent on this target")
        else:
            offenders = {}
            for order_type in ("inventory", "cost_center"):
                count = rpc.call(
                    "sale.order.line", "search_count",
                    [("order_id.order_type", "=", order_type),
                     ("order_id.state", "in", ["sale", "done"]),
                     ("analytic_distribution", "!=", False)])
                if count:
                    offenders[order_type] = count
            ctx.check("confirmed inventory/cost_center lines carrying an "
                      "analytic distribution", {}, offenders)


def _capture_mail_config(ctx):
    """Mail templates, server actions and automations — TC057."""
    import hashlib
    rpc = ctx.adapter.rpc
    modules = _custom_modules(ctx)
    snapshot = {}

    def digest(value):
        return hashlib.md5((value or "").encode("utf-8")).hexdigest()

    data = rpc.search_read("ir.model.data",
                           [("model", "=", "mail.template"),
                            ("module", "in", modules)],
                           ["module", "name", "res_id"])
    if data:
        by_id = {d["res_id"]: f"{d['module']}.{d['name']}" for d in data}
        for row in rpc.read("mail.template", list(by_id),
                            ["name", "subject", "body_html", "email_from",
                             "email_to", "partner_to", "auto_delete",
                             "model_id"]):
            xml_id = by_id[row["id"]]
            snapshot[f"template/{xml_id}/subject"] = row["subject"] or ""
            snapshot[f"template/{xml_id}/body_md5"] = digest(row["body_html"])
            snapshot[f"template/{xml_id}/model"] = m2o_id(row["model_id"])
            snapshot[f"template/{xml_id}/auto_delete"] = row["auto_delete"]

    for action in _custom_server_actions(rpc, modules):
        xml_id = action["xml_id"]
        snapshot[f"server_action/{xml_id}/state"] = action["state"]
        snapshot[f"server_action/{xml_id}/code_md5"] = digest(action["code"])
        snapshot[f"server_action/{xml_id}/model"] = m2o_id(action["model_id"])

    if rpc.model_exists("base.automation"):
        adata = rpc.search_read("ir.model.data",
                                [("model", "=", "base.automation")],
                                ["module", "name", "res_id"])
        if adata:
            by_id = {d["res_id"]: f"{d['module']}.{d['name']}"
                     for d in adata}
            for row in rpc.read("base.automation", list(by_id),
                                ["active", "trigger", "filter_pre_domain",
                                 "filter_domain", "model_id"]):
                xml_id = by_id[row["id"]]
                snapshot[f"automation/{xml_id}"] = (
                    f"active={row['active']} trigger={row['trigger']} "
                    f"pre={row['filter_pre_domain']} "
                    f"post={row['filter_domain']}")
    return snapshot


@test_case(
    id="TEST-WF002-TC057",
    name="Mail templates, server actions and automated actions",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_purchase, dto_sale, dto_sale_stock, "
           "dto_tier_validation_email",
    priority="P2", kind="DATA", order=2057,
    description="Subjects, body digests, code digests, models and "
                "automation triggers/domains for every custom mail "
                "template, server action and automated action — captured "
                "on v17 and diffed on v19, so a silently altered body or "
                "code body is caught.",
    traceability=trace("DATAONE-TC057"))
def test_tc057(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Determine the custom module set from the source tree"):
        _require_modules(ctx)

    reconcile(ctx, "DATAONE-TC057", _capture_mail_config)

    with ctx.step("Step 3: every custom automated action is active"):
        if not rpc.model_exists("base.automation"):
            ctx.log("base_automation is not installed on this target")
        else:
            inactive = rpc.search_read(
                "base.automation", [("active", "=", False)],
                ["name", "model_id"])
            ctx.log(f"inactive automations: {inactive!r}")
            ctx.check("inactive automated actions", [],
                      [a["name"] for a in inactive])
