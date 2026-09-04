"""DATAONE-WF-003 — the OCA layer gate: TC014.

The five OCA modules must import and load on the v19 runtime. This test
implements the halves that are reachable without a v19 server:

* steps 1, 2, 6 — static scans of the source tree for the APIs Odoo 19
  removed (``framework/source_scan.py``);
* step 5 — the DataOne fork of stock_picking_auto_create_lot: the RMA
  fields and the rma_number sequence, read through the ORM instead of
  information_schema so no PostgreSQL credentials are needed.

Steps 3, 4 and 7 (import probe, install into a scratch ``dataone_oca``
database, re-run the asset check) need a v19 runtime and the right to
create and drop databases. The platform has neither by contract — it never
starts a server or touches a database — so they report BLOCKED with a
precise reason after the reachable assertions have run.

Every scan result is logged and written to an evidence artifact BEFORE the
first assertion, so a failure at step 1 still leaves the full picture in
the execution record.

EXPECTED v17 OUTCOME: **FAIL at step 1.** The expectation ("clean for all
five") describes the post-remediation v19 target state; today
base_revision/models/base_revision.py carries
``@api.returns("self", lambda value: value.id)`` on copy(). That is the
workbook's headline WF-003 finding, not an automation defect — it
classifies as FIXED once the v19 port lands. Convention rule 2: the
expectation is immutable and must not be inverted to make v17 green.

Workbook note: this TC is flagged [HOLD] because base_tier_validation's
scope is a Phase-0b decision. It is implemented anyway — the other four
modules are in scope regardless, and stock_picking_auto_create_lot's fork
survives any descoping.
"""
import json

from framework.registry import test_case
from framework.source_scan import (resolve_source_root, scan_modules,
                                   summarise)
from tests.wf003.common import (OCA_MODULES, WORKFLOW,  # noqa: F401
                                WORKFLOW_NAME, installed_modules, trace)

# Step 1 — members removed from odoo.api in v19.
REMOVED_API_RE = (r"@api\.(returns|downgrade|split_context|propagate"
                  r"|attrsetter|model_create_single)\b")

# Step 2 — the other removed/renamed APIs the workbook names.
REMOVED_OTHER_RE = (r"\bgroups_id\b|\buser_has_groups\b|\btrans_implied_ids\b"
                    r"|\bname_get\b|procurement\.group"
                    r"|stock\.valuation\.layer|stock\.quant\.package")

# Step 6 — legacy front-end patterns in base_tier_validation.
LEGACY_JS_RE = r"const\s*\{\s*Component\s*\}\s*=\s*owl|jQuery|\$\("

# Step 5 — the DataOne RMA fork on stock_picking_auto_create_lot.
RMA_FIELDS = ["rma_number", "reason_for_return", "return_notes"]
RMA_SEQUENCE_CODE = "rma_number"


@test_case(
    id="TEST-WF003-TC014",
    name="The five OCA modules import and load on the v19 runtime",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="base_revision, base_tier_validation, queue_job, "
           "sale_order_revision, stock_picking_auto_create_lot",
    priority="P0", kind="DATA", order=3014,
    description="Static scan of the five OCA modules for the odoo.api "
                "members and other APIs v19 removed, the legacy OWL/jQuery "
                "patterns in base_tier_validation, and the survival of the "
                "DataOne RMA fork (fields + rma_number sequence).",
    traceability=trace("DATAONE-TC014"))
def test_tc014(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Locate the DTO-Odoo source tree"):
        root = resolve_source_root(ctx.env.version)
        if root is None:
            ctx.blocked(
                "The DTO-Odoo source tree is not reachable from this "
                "workstation. Set DTO_SOURCE_ROOT in config/local.yaml to "
                "the checkout that holds 3rd-addons/, novobi-addons/ and "
                "project-addons/ — TC014 is a static scan of that tree and "
                "cannot be answered from the database.")
        ctx.log(f"source root: {root}")

    with ctx.step("Run every scan and record the evidence before asserting"):
        api_scan = scan_modules(root, OCA_MODULES, REMOVED_API_RE,
                                suffixes=(".py",))
        other_scan = scan_modules(root, OCA_MODULES, REMOVED_OTHER_RE)
        js_scan = scan_modules(root, ["base_tier_validation"], LEGACY_JS_RE,
                               suffixes=(".js",))
        evidence = {
            "source_root": str(root),
            "step1_removed_odoo_api": api_scan,
            "step2_removed_other_api": other_scan,
            "step6_base_tier_validation_js": js_scan,
        }
        path = ctx.artifacts_dir / "tc014_scans.json"
        path.write_text(json.dumps(evidence, indent=1, ensure_ascii=False),
                        encoding="utf-8")
        ctx.add_artifact(path, "log", "TC014 static scan results")
        ctx.log(f"step 1 hits per module: {summarise(api_scan)}")
        ctx.log(f"step 2 hits per module: {summarise(other_scan)}")
        ctx.log(f"step 6 hits: {summarise(js_scan)}")
        for module, hits in api_scan.items():
            for hit in (hits or []):
                ctx.log(f"  [step1] {module}/{hit['file']}:{hit['line']}  "
                        f"{hit['text']}")

    with ctx.step("All five modules are present in the source tree"):
        missing = [m for m, hits in api_scan.items() if hits is None]
        ctx.check("modules missing from the source tree", [], missing)

    with ctx.step("Step 1: the removed odoo.api members are clean for all "
                  "five modules"):
        offenders = {m: hits for m, hits in api_scan.items() if hits}
        ctx.check("modules still using removed odoo.api members", {},
                  {m: [f"{h['file']}:{h['line']}" for h in hits]
                   for m, hits in offenders.items()})

    with ctx.step("Step 2: zero hits for the other removed APIs"):
        offenders = {m: hits for m, hits in other_scan.items() if hits}
        ctx.check("modules still using other removed APIs", {},
                  {m: [f"{h['file']}:{h['line']}" for h in hits]
                   for m, hits in offenders.items()})

    with ctx.step("Step 6: base_tier_validation carries no legacy OWL "
                  "global and no jQuery"):
        hits = js_scan.get("base_tier_validation") or []
        ctx.check("legacy front-end patterns in base_tier_validation", [],
                  [f"{h['file']}:{h['line']}  {h['text']}" for h in hits])

    with ctx.step("Step 5: the DataOne RMA fork survived — the three "
                  "stock.picking fields exist"):
        absent = [f for f in RMA_FIELDS
                  if not rpc.field_exists("stock.picking", f)]
        ctx.check("RMA fields missing from stock.picking", [], absent)

    with ctx.step("Step 5: the rma_number sequence exists with prefix "
                  "%(year)s- and padding 3"):
        rows = rpc.search_read("ir.sequence",
                               [("code", "=", RMA_SEQUENCE_CODE)],
                               ["code", "prefix", "padding"])
        ctx.log(f"ir.sequence rows: {rows!r}")
        ctx.check("rma_number sequences found", 1, len(rows))
        ctx.check("rma_number prefix", "%(year)s-", rows[0]["prefix"])
        ctx.check("rma_number padding", 3, rows[0]["padding"])

    with ctx.step("Record the installed state of the five modules on this "
                  "target"):
        states = installed_modules(rpc, OCA_MODULES)
        ctx.log(f"ir.module.module: "
                f"{ {m: r['state'] for m, r in states.items()} }")

    with ctx.step("Steps 3, 4 and 7 need a v19 runtime and a scratch "
                  "database"):
        ctx.blocked(
            "Steps 3-4 (importlib probe of the five modules on the v19 "
            "runtime, then odoo-bin -i into a scratch 'dataone_oca' "
            "database) and step 7 (re-run TC003's asset build against it) "
            "require starting a v19 server and creating/dropping a "
            "database. The platform never starts a server or touches a "
            "database by contract, and workbook precondition E5 (OCA 19.0 "
            "branches fetched, the stock_picking_auto_create_lot fork "
            "re-applied) is a prerequisite for them. Run those four steps "
            "from the v19 build pipeline; steps 1, 2, 5 and 6 above are "
            "the part this platform owns.")
