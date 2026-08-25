"""DATAONE-WF-003 — the lineage uniqueness constraint and its exact
message: TC098.

Step 1 is the assertion that actually protects against the v19 regression.
sale_order_revision overwrites ``_sql_constraints`` rather than extending
it, and Odoo merges the lists by constraint KEY
(``cls._sql_constraints[cons[0]] = cons`` over ``reversed(__base_classes)``,
odoo/models.py:819) — so the company-scoped three-column version wins over
base_revision's two-column one. If a v19 rewrite to ``models.Constraint``
drops the company scope, the constraint silently reverts to the base rule:
step 3 would still raise, with the wrong message and the wrong scope, and a
message-only test would pass in a multi-company database.

The constraint is read through ``ir.model.constraint`` rather than raw SQL
so the test needs no PostgreSQL credentials. Odoo reflects every declared
SQL constraint there with its definition, message and owning module
(base/models/ir_model.py:1826 ``_reflect_constraint``), under the name
``<table>_<key>`` — here ``sale_order_revision_unique``.

Chaining adaptation: the workbook expects TC096's three-member lineage to
already exist. Convention rule 5 forbids that dependency, so this test
rebuilds the lineage with its own execution token first.

EXPECTED v17 OUTCOME: PASS.
EXPECTED v19 OUTCOME: BLOCKED until the OCA 19.0 ports exist (E5).
"""
from framework.registry import test_case
from tests.wf003.common import (WORKFLOW, WORKFLOW_NAME,  # noqa: F401
                                expect_error, m2o_id, make_quotation,
                                read_order, require_revision_stack,
                                revision_of, set_sent, sweep_wf003, trace)

CONSTRAINT_NAME = "sale_order_revision_unique"
DATAONE_MESSAGE = "Order Reference and revision must be unique per Company."
BASE_MESSAGE = "Reference and revision must be unique."


@test_case(
    id="TEST-WF003-TC098",
    name="The lineage uniqueness constraint and its exact message",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="sale_order_revision", priority="P2", kind="DATA", order=3098,
    description="The constraint in force is unique(unrevisioned_name, "
                "revision_number, company_id) — the company-scoped version "
                "from sale_order_revision, not the two-column base one; a "
                "colliding revision_number raises with the DataOne-scoped "
                "message; a free revision_number succeeds.",
    traceability=trace("DATAONE-TC098"))
def test_tc098(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-003 fixtures and open a fresh "
                  "namespace"):
        sweep_wf003(rpc)

    with ctx.step("Precondition: the revision stack is installed"):
        require_revision_stack(ctx)

    with ctx.step("Rebuild the TC096 lineage: source, -01 and -02, all "
                  "sharing one unrevisioned_name"):
        order_id, _snapshot = make_quotation(ctx)
        base = read_order(rpc, order_id, ["name", "company_id"])
        base_name, company_id = base["name"], m2o_id(base["company_id"])
        set_sent(rpc, order_id)
        rpc.call("sale.order", "create_revision", [order_id])
        rev1_id = revision_of(rpc, order_id)
        set_sent(rpc, rev1_id)
        rpc.call("sale.order", "create_revision", [rev1_id])
        rev2_id = revision_of(rpc, rev1_id)
        lineage = rpc.search_read(
            "sale.order",
            [("unrevisioned_name", "=", base_name),
             ("active", "in", [True, False])],
            ["name", "revision_number"], order="revision_number")
        ctx.log(f"lineage: {lineage!r}")
        ctx.check("lineage revision numbers", [0, 1, 2],
                  [r["revision_number"] for r in lineage])

    stray_id = None
    try:
        with ctx.step("Step 1: the constraint in force is the "
                      "company-scoped three-column version from "
                      "sale_order_revision"):
            rows = rpc.search_read(
                "ir.model.constraint",
                [("name", "=", CONSTRAINT_NAME)],
                ["name", "definition", "message", "type", "module", "model"])
            ctx.log(f"ir.model.constraint rows: {rows!r}")
            ctx.check("exactly one reflected constraint named "
                      f"{CONSTRAINT_NAME}", 1, len(rows))
            row = rows[0]
            ctx.check("constraint type", "u", row["type"])
            ctx.check("owning module", "sale_order_revision",
                      (row["module"] or [None, None])[1])
            definition = (row["definition"] or "").lower()
            columns = [c for c in ("unrevisioned_name", "revision_number",
                                   "company_id") if c in definition]
            ctx.check("constrained column list",
                      ["unrevisioned_name", "revision_number", "company_id"],
                      columns)
            ctx.check("reflected message", DATAONE_MESSAGE, row["message"])

        with ctx.step("Steps 2-4: writing a colliding "
                      "(unrevisioned_name, revision_number, company_id) "
                      "raises with the DataOne-scoped message"):
            raised, message = expect_error(
                rpc.create, "sale.order",
                {"partner_id": rpc.read("sale.order", [order_id],
                                        ["partner_id"])[0]["partner_id"][0],
                 "company_id": company_id,
                 "order_type": "project",
                 "origin": read_order(rpc, order_id, ["origin"])["origin"],
                 "unrevisioned_name": base_name,
                 "revision_number": 2})
            ctx.log(f"raised message: {message!r}")
            ctx.check_true("colliding revision_number 2 was rejected",
                           raised, actual_desc=message)
            ctx.check_true(
                "the DataOne-scoped message is the one raised",
                DATAONE_MESSAGE in message,
                actual_desc=message)
            ctx.check_true(
                "the base module's two-column message is NOT the one raised",
                not (BASE_MESSAGE in message
                     and DATAONE_MESSAGE not in message),
                actual_desc=message)

        with ctx.step("Step 5: revision_number 3 does not yet exist, so the "
                      "same write succeeds"):
            stray_id = rpc.create("sale.order", {
                "partner_id": rpc.read("sale.order", [order_id],
                                       ["partner_id"])[0]["partner_id"][0],
                "company_id": company_id,
                "order_type": "project",
                "origin": read_order(rpc, order_id, ["origin"])["origin"],
                "unrevisioned_name": base_name,
                "revision_number": 3})
            ctx.check_true("revision_number 3 accepted", bool(stray_id),
                           actual_desc=f"created sale.order id {stray_id}")
    finally:
        with ctx.step("Cleanup: delete the step-5 stray record and the "
                      "WF-003 fixtures"):
            try:
                if stray_id:
                    rpc.call("sale.order", "unlink", [stray_id])
            except Exception as exc:      # noqa: BLE001 — never mask a verdict
                ctx.log(f"[warn] stray record {stray_id} not removed: {exc}")
            try:
                sweep_wf003(rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")
