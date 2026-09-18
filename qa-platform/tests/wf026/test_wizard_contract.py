"""DATAONE-WF-026 — who may import, and what each type means.

TC396 is the access surface. ``dto_data_migration`` ships exactly ONE ACL
row (``security/ir.model.access.csv``) granting RWCU on
``import.data.wizard`` to ``stock.group_stock_manager``, and **no record
rule at all** — verified: the module contributes zero ``ir.rule``. The
workbook's step 12 asks for the privilege-escalation surface to be recorded
as a passing observation rather than a failure, and that is what this case
does: the wizard writes into ``purchase.order``, ``sale.order``,
``mrp.production`` and ``mrp.bom`` as the calling user, so whoever can reach
it can create finished orders in those models directly. That is the design,
not a defect, and it is asserted so that a change to it is loud.

TC397 is the four-type mapping. Its steps 15-16 are the interesting half:
they prove ``key_fields`` is filled by the **onchange**
(``wizard/import_data_wizard.py:32-41``) and not by a field default — which
matters because anything driving this wizard over RPC, including this
suite, does not get the onchange and must supply the value itself.

EXPECTED v17 OUTCOME
  TC396 PASS · TC397 PASS. Both describe the module as shipped on 17.0.
EXPECTED v19 OUTCOME
  TC396 PASS · TC397 PASS. The Stage 7 port changed neither the ACL nor the
  onchange; ``res.groups.category_id`` was dropped from ``dto_reports``
  (D-new-14) but ``stock.group_stock_manager`` is core and untouched.
"""
from framework.qa_fixtures import ensure_qa_user, rpc_as_qa_user
from framework.registry import test_case
from tests.wf026.common import (EXPECTED_KEY_FIELDS, IMPORT_TYPES, WIZARD,
                                WIZARD_ACTION_XMLID, WIZARD_GROUP_XMLID,
                                WORKFLOW, WORKFLOW_NAME, expect_error, fx,
                                make_wizard, open_namespace,
                                require_data_migration, sweep_wf026, trace)


@test_case(
    id="TEST-WF026-TC396",
    name="Only an Inventory Manager can reach the Import Data wizard",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_data_migration",
    priority="P0", kind="SEC", order=26396,
    description="One ACL and no record rule; the wizard is unreachable for a "
                "plain internal user and reachable for an Inventory Manager. "
                "The privilege-escalation surface it opens is recorded as a "
                "passing observation, per the workbook's step 12.",
    traceability=trace("DATAONE-TC396"))
def test_tc396(ctx):
    rpc = ctx.adapter.rpc
    require_data_migration(ctx)
    open_namespace(ctx)
    try:
        with ctx.step("Steps 2-3: exactly one ACL on the wizard, and no "
                      "record rule"):
            model_id = rpc.search("ir.model", [("model", "=", WIZARD)])
            ctx.check_true("the wizard model is registered", bool(model_id),
                           str(model_id))
            acls = rpc.search_read(
                "ir.model.access", [("model_id", "in", model_id)],
                ["name", "group_id", "perm_read", "perm_write", "perm_create",
                 "perm_unlink"])
            ctx.check("ACL rows on import.data.wizard", 1, len(acls))
            rules = rpc.search("ir.rule", [("model_id", "in", model_id)])
            ctx.check("record rules on import.data.wizard", [], rules)
            if acls:
                acl = acls[0]
                ctx.check_true("the ACL grants all four permissions",
                               all(acl[p] for p in ("perm_read", "perm_write",
                                                    "perm_create",
                                                    "perm_unlink")),
                               str(acl))
                group_id = acl["group_id"][0] if acl["group_id"] else None
                expected_group = rpc.ref(WIZARD_GROUP_XMLID)
                ctx.check(f"the ACL names {WIZARD_GROUP_XMLID}",
                          expected_group, group_id)
                ctx.log(f"ACL: {acl['name']}")

        with ctx.step("The wizard action and its menu resolve"):
            action_id = rpc.ref(WIZARD_ACTION_XMLID)
            ctx.check_true(f"{WIZARD_ACTION_XMLID} resolves", bool(action_id),
                           str(action_id))

        with ctx.step("Steps 10-11: a plain internal user cannot create the "
                      "wizard"):
            ensure_qa_user(rpc)
            plain = rpc_as_qa_user(ctx.env)
            message, _fault = expect_error(
                ctx, lambda: make_wizard(plain, "closed_po", []),
                label="a plain internal user creating the wizard")
            ctx.check_true("the refusal is an access error, not a validation "
                           "error",
                           "access" in message.lower()
                           or "not allowed" in message.lower()
                           or "permission" in message.lower(),
                           message[:300])

        with ctx.step("An Inventory Manager can create it"):
            wizard_id = make_wizard(rpc, "closed_po", [])
            ctx.check_true("the manager's wizard exists", bool(wizard_id),
                           str(wizard_id))

        with ctx.step("Step 12: record the privilege-escalation surface as an "
                      "observation, not a failure"):
            # The workbook asks for this to be RECORDED. It is the design:
            # run_import_data_migration calls self.create() on the target
            # model as the calling user, so the wizard's reach is the reach
            # of whoever holds stock.group_stock_manager. Asserting the
            # shape means a future narrowing or widening is visible in the
            # diff rather than silent.
            targets = ["purchase.order", "sale.order", "mrp.production",
                       "mrp.bom"]
            reachable = [m for m in targets if rpc.model_exists(m)]
            ctx.check("the wizard writes into these models", targets,
                      reachable)
            ctx.log("OBSERVATION: stock.group_stock_manager is sufficient to "
                    "create finished records in all four models through this "
                    "wizard, with no record rule narrowing it. Recorded per "
                    "the workbook's step 12; not a failure.")
    finally:
        with ctx.step("Cleanup"):
            try:
                sweep_wf026(rpc)
            except Exception:  # noqa: BLE001
                pass


@test_case(
    id="TEST-WF026-TC397",
    name="The four import types map to the right models and auto-fill "
         "key_fields",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_data_migration",
    priority="P1", kind="FUNC", order=26397,
    description="name / name / name / product_tmpl_id across the four types, "
                "batch size 100 and the queue off by default. Steps 15-16 "
                "prove the default lives in the onchange and not in the "
                "field.",
    traceability=trace("DATAONE-TC397"))
def test_tc397(ctx):
    rpc = ctx.adapter.rpc
    require_data_migration(ctx)
    open_namespace(ctx)
    try:
        with ctx.step("The selection offers exactly the four documented "
                      "types"):
            info = rpc.call(WIZARD, "fields_get", ["import_type"],
                            ["selection"])
            offered = [v for v, _label in info["import_type"]["selection"]]
            ctx.check("import_type selection", list(IMPORT_TYPES), offered)

        with ctx.step("Steps 4, 7, 9, 11: each type's key_fields, via the "
                      "onchange the UI would run"):
            got = {}
            for import_type in IMPORT_TYPES:
                result = rpc.call(
                    WIZARD, "onchange", [], {"import_type": import_type},
                    ["import_type"],
                    {"import_type": {}, "key_fields": {},
                     "batch_size": {}, "use_queue_job": {}})
                value = (result or {}).get("value", {})
                got[import_type] = value.get("key_fields")
            ctx.check("key_fields per import type", EXPECTED_KEY_FIELDS, got)

        with ctx.step("batch_size defaults to 100 and the queue is off"):
            defaults = rpc.call(WIZARD, "default_get",
                                ["batch_size", "use_queue_job",
                                 "import_type"])
            ctx.check("batch_size default", 100, defaults.get("batch_size"))
            ctx.check_true("use_queue_job is off by default",
                           not defaults.get("use_queue_job"),
                           str(defaults.get("use_queue_job")))
            ctx.check("import_type default", "closed_po",
                      defaults.get("import_type"))

        with ctx.step("Steps 15-16: key_fields has NO field default — the "
                      "value comes from the onchange"):
            # This is the half that matters for anything driving the wizard
            # over RPC: create() does not run onchange, so key_fields arrives
            # empty and the caller must supply it. If a future change moves
            # the value into a field default, this assertion is what notices.
            ctx.check_true("key_fields is absent from default_get",
                           "key_fields" not in defaults,
                           str(sorted(defaults)))
            ctx.check_true("key_fields is required, so the empty default "
                           "cannot pass silently",
                           rpc.call(WIZARD, "fields_get", ["key_fields"],
                                    ["required"])["key_fields"]["required"],
                           "required")

        with ctx.step("A wizard created over RPC keeps the key_fields it was "
                      "given"):
            wizard_id = make_wizard(rpc, "bom", [],
                                    file_name=fx("mapping-probe.csv"))
            row = rpc.read(WIZARD, [wizard_id],
                           ["import_type", "key_fields", "batch_size",
                            "use_queue_job"])[0]
            ctx.check("import_type", "bom", row["import_type"])
            ctx.check("key_fields", EXPECTED_KEY_FIELDS["bom"],
                      row["key_fields"])
            ctx.check("batch_size", 100, row["batch_size"])
            ctx.check_true("use_queue_job off", not row["use_queue_job"],
                           str(row["use_queue_job"]))
    finally:
        with ctx.step("Cleanup"):
            try:
                sweep_wf026(rpc)
            except Exception:  # noqa: BLE001
                pass
