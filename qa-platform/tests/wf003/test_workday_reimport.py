"""DATAONE-WF-003 — Workday re-import creates a revision: TC338.

Feasibility: **blocked stub with an asserted offline half.**

The re-import path runs entirely through private methods —
``sftp.file._process_sftp_file`` -> the ETL processor ->
``sale.order._transform_workday_requisition_to_sale_order_vals`` ->
``_process_workday_sale_order_vals``. Odoo refuses to dispatch any method
whose name starts with an underscore over RPC
(``check_method_name``, v17 odoo/models.py:145; v19
odoo/orm/utils.py:69 / ``service.model.get_public_method``), and the
transform's return value carries a recordset that cannot be JSON-marshalled
in any case. Driving the flow therefore needs either the Workday SFTP
endpoint or an in-process TransactionCase — both outside this platform's
contract, which never starts a server or reaches an external host
(convention rule 4).

What IS asserted here, before the block, is the half that does not need the
endpoint and that the end-to-end test would otherwise take on faith:

* the revision stack is installed at all (workbook precondition E5 — the
  single fact that decides whether WF-003 exists on v19);
* ``sale.order.internal_memo``, the matching key the import searches on;
* the exact matching domain's *search* behaviour against a real lineage:
  ``name = memo OR name like 'memo-%'`` must resolve to the newest revision,
  which is what makes step 15 extend the chain (-02) instead of forking a
  duplicate lineage;
* ``imported_from_workday`` is ``copy=False``
  (dto_sale_workday/models/sale_order.py:19-22), so a revision does NOT
  inherit the flag through copy(). Step 16 ("True on every revision in the
  chain") therefore holds only because
  ``_prepare_workday_sales_order_values`` writes it explicitly on every
  pass — a subtlety TC095's source notes ask to be recorded separately;
* the SFTP connector is inactive on this QA target, proving the test cannot
  and did not reach Workday.

EXPECTED v17 OUTCOME: BLOCKED (after the offline assertions pass).
EXPECTED v19 OUTCOME: BLOCKED — and for a second, harder reason: without an
OCA 19.0 base_revision, dto_sale_workday does not import at all
(@api.returns at base_revision.py:66), so WF-001 and WF-003 are both dead.
That is workbook precondition E5 and a week-one business decision, not a
test defect.
"""
from framework.registry import test_case
from tests.wf003.common import (MARK, WORKFLOW, WORKFLOW_NAME,  # noqa: F401
                                fx, m2o_id, make_quotation, read_order,
                                require_revision_stack, revision_of,
                                set_sent, sweep_wf003, trace)

SFTP_USAGE = "workday_requisition"


@test_case(
    id="TEST-WF003-TC338",
    name="Re-import of an unconfirmed order creates a revision, cancels and "
         "archives the old",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_sale_workday", priority="P0", kind="API", order=3338,
    description="Offline half of the Workday re-import gate: the revision "
                "stack, the internal_memo matching key, the "
                "name-or-name-like domain resolving to the newest revision "
                "(so a re-import extends the chain instead of forking it), "
                "imported_from_workday being copy=False, and the SFTP "
                "connector being inactive. The ETL round trip itself needs "
                "the Workday endpoint and is BLOCKED.",
    traceability=trace("DATAONE-TC338"))
def test_tc338(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-003 fixtures and open a fresh "
                  "namespace"):
        sweep_wf003(rpc)

    with ctx.step("Workbook precondition E5: base_revision and "
                  "sale_order_revision are installed and functioning"):
        require_revision_stack(ctx)

    with ctx.step("dto_sale_workday is installed: internal_memo (the "
                  "matching key) and imported_from_workday exist on "
                  "sale.order"):
        for field in ("internal_memo", "imported_from_workday",
                      "requester_email"):
            ctx.check_true(f"sale.order.{field} exists",
                           rpc.field_exists("sale.order", field),
                           actual_desc=("present" if
                                        rpc.field_exists("sale.order", field)
                                        else "ABSENT — dto_sale_workday is "
                                             "not installed"))

    with ctx.step("Step 16 subtlety: imported_from_workday is copy=False, "
                  "so a revision does not inherit it through copy()"):
        # Read from ir.model.fields.copied, NOT from fields_get: `copy` is
        # not a field description attribute on either version — there is no
        # _description_copy property (v17 odoo/fields.py:858-871, v19
        # odoo/orm/fields.py:888-901) — so fields_get(attributes=["copy"])
        # returns nothing for it. ir.model.fields.copied is reflected
        # straight from bool(field.copy) (v17 ir_model.py:1119, v19
        # ir_model.py:1186) and is the ORM-level answer this step wants.
        rows = rpc.search_read("ir.model.fields",
                               [("model", "=", "sale.order"),
                                ("name", "=", "imported_from_workday")],
                               ["name", "copied", "ttype"])
        ctx.log(f"ir.model.fields: {rows!r}")
        ctx.check("imported_from_workday is reflected once", 1, len(rows))
        ctx.check("imported_from_workday copy flag", False,
                  rows[0]["copied"])
        ctx.log("=> step 16 ('True on every revision in the chain') holds "
                "only because the import writes the flag explicitly on "
                "every pass, not because copy() carries it")

    with ctx.step("Build a real lineage to exercise the import's matching "
                  "domain: SO-A, then one revision"):
        order_id, _snapshot = make_quotation(ctx, label="WdyReimport")
        so_a = read_order(rpc, order_id, ["name"])["name"]
        memo = so_a
        set_sent(rpc, order_id)
        rpc.call("sale.order", "create_revision", [order_id])
        rev1_id = revision_of(rpc, order_id)
        rev1 = read_order(rpc, rev1_id, ["name", "state", "active"])
        ctx.check("revision name", f"{so_a}-01", rev1["name"])

    try:
        with ctx.step("Steps 6-8: the superseded order is cancelled AND "
                      "archived; the revision is the draft current one"):
            src = read_order(rpc, order_id,
                             ["state", "active", "current_revision_id"])
            ctx.check("SO-A state", "cancel", src["state"])
            ctx.check("SO-A active", False, src["active"])
            ctx.check("SO-A current_revision_id", rev1_id,
                      m2o_id(src["current_revision_id"]))
            ctx.check("revision state", "draft", rev1["state"])
            ctx.check("revision active", True, rev1["active"])

        with ctx.step("Step 15: the import's matching domain "
                      "(name = memo OR name like 'memo-%') resolves to the "
                      "newest revision, so a re-import extends the chain "
                      "rather than forking a duplicate lineage"):
            # the exact domain from
            # dto_sale_workday/models/sale_order.py:236-240
            matched = rpc.search(
                "sale.order",
                ["|", ("name", "=", memo), ("name", "like", f"{memo}-%")],
                limit=1)
            ctx.check_true("the domain matched a record", bool(matched),
                           actual_desc=f"matched ids {matched}")
            matched_name = read_order(rpc, matched[0], ["name"])["name"]
            ctx.log(f"domain matched {matched_name}")
            ctx.check_true(
                "the match is a member of the SO-A lineage",
                matched_name.startswith(memo),
                actual_desc=matched_name)
            lineage = rpc.search(
                "sale.order",
                [("unrevisioned_name", "=", memo),
                 ("active", "in", [True, False])])
            ctx.check("lineage size after one revision", 2, len(lineage))

        with ctx.step("Step 11: the Prev. revisions stat button on the "
                      "revision resolves to SO-A"):
            listed = rpc.search("sale.order",
                                [("current_revision_id", "=", rev1_id),
                                 ("active", "in", [True, False])])
            ctx.check("stat button resolves to", [order_id], listed)

        with ctx.step("Step 10: both chatters carry the revision notice"):
            notice = f"New revision created: {rev1['name']}"
            for label, rec_id in (("SO-A", order_id),
                                  ("revision", rev1_id)):
                bodies = [m["body"] or "" for m in rpc.search_read(
                    "mail.message",
                    [("model", "=", "sale.order"), ("res_id", "=", rec_id)],
                    ["body"], order="id")]
                ctx.check_true(f"{label} chatter carries the notice",
                               any(notice in b for b in bodies),
                               actual_desc=f"{len(bodies)} message(s)")

        with ctx.step("Convention rule 4: the Workday SFTP connector is "
                      "inactive on this QA target, so nothing here could "
                      "reach the endpoint"):
            if not rpc.model_exists("sftp.folder"):
                ctx.log("sftp.folder is absent — novobi_sftp_connection is "
                        "not installed on this target")
            else:
                folders = rpc.search_read(
                    "sftp.folder",
                    [("usage", "=", SFTP_USAGE),
                     ("active", "in", [True, False])],
                    ["path", "active", "usage"])
                ctx.log(f"workday_requisition folders: {folders!r}")
                live = [f for f in folders if f["active"]]
                ctx.check("active workday_requisition SFTP folders", [],
                          [f["path"] for f in live])

        with ctx.step("Steps 2-5, 9, 12-14 and 17 need the Workday SFTP "
                      "endpoint"):
            ctx.blocked(
                "The re-import round trip runs through private methods "
                "(sftp.file._process_sftp_file -> the ETL processor -> "
                "sale.order._transform_workday_requisition_to_sale_order_"
                "vals -> _process_workday_sale_order_vals). Odoo refuses "
                "to dispatch underscore-prefixed methods over RPC "
                "(check_method_name), and the transform returns a "
                "recordset that cannot be JSON-marshalled, so the "
                "line-reconciliation branches (step 12), the zero/negative "
                "price carry-forward (step 13), the partner_id vs "
                "partner_shipping_id rule (step 14) and the sftp.file Done "
                "state (step 17) cannot be driven from here. Run them as "
                "an in-process TransactionCase in dto_sale_workday, or "
                "against a mocked SFTP sandbox. The revision mechanics they "
                "depend on are asserted above and in TEST-WF003-TC095 / "
                "TC096.")
    finally:
        with ctx.step("Cleanup WF-003 fixtures"):
            try:
                sweep_wf003(rpc)
            except Exception as exc:      # noqa: BLE001 — never mask a verdict
                ctx.log(f"[warn] cleanup incomplete: {exc}")
