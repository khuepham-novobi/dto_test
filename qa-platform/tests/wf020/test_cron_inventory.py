"""DATAONE-WF-020 — the scheduled-job inventory: TC008, TC459, TC460.

TC008 / TC459 compare the cron set against an expected-delta list. No such
list exists yet for this project, so both use the platform's
DATA_RECONCILIATION pattern instead: the run on **v17 captures and persists
the baseline**, and the run on **v19 diffs against it**. That is exactly
what the workbook's ``crons_v19.csv`` is for, derived from the environment
rather than hand-maintained — and it means a cron that silently changes
interval, disappears or arrives between versions fails the v19 run.

The identity used is the XML id (``ir.model.data`` ``module.name``), never
the database id, so the comparison survives a re-install.

TC459's second half — "Run Manually of each cron" — is NOT executed.
Triggering ``cron_get_sftp_files`` or ``cron_export_workday_vendor_bill``
reaches the Workday SFTP endpoint, which convention rule 4 forbids. That
half is BLOCKED with a precise reason.

TC460 asserts the **version delta** that makes the workflow's silent
failure mode possible: Odoo 19 added ``failure_count`` and
``first_failure_date`` to ``ir.cron`` and auto-deactivates a job after
repeated failures (``odoo/addons/base/models/ir_cron.py:121``,
``_update_failure_count`` at :571). ``deactivate`` -- which the
workbook's v19_watch note lists alongside them -- is a field of
``ir.cron.progress`` (``ir_cron.py:918-926``), not of ``ir.cron``, so
each half of the delta is asserted against the model that carries it.
Odoo 17 has none of them. Forcing N consecutive failures needs the
crons to actually fire, so that half is BLOCKED too.

EXPECTED v17 OUTCOME: TC008/TC459 PASS (baseline captured, then BLOCKED for
the Run-Manually half of TC459). TC460 records the v17 side of the delta —
the three fields are absent — and then BLOCKS.
EXPECTED v19 OUTCOME: TC008/TC459 diff against the stored baseline; any
difference is a real finding.
"""
from framework.registry import test_case
from tests.wf020.common import (CRON_MODULES,  # noqa: F401
                                V19_CRON_FIELDS, V19_CRON_PROGRESS_FIELDS,
                                V19_CRON_PROGRESS_MODEL, WORKFLOW,
                                WORKFLOW_NAME, cron_rows, trace)

# Crons shared by more than one workflow — TC460's blast-radius claim.
SHARED_CRONS = {
    "novobi_sftp_connection.ir_cron_process_sftp_files":
        "WF-010 (MO test results), WF-019 (vendor payments) and WF-020 "
        "(supplier master) all consume it",
}


def _capture_crons(ctx):
    """Snapshot of the cron inventory, keyed by XML id."""
    rows = cron_rows(ctx.adapter.rpc)
    snapshot = {}
    for row in rows:
        snapshot[row["xml_id"]] = (
            f"active={row['active']} "
            f"interval={row['interval_number']}{row['interval_type']} "
            f"priority={row['priority']}")
    return snapshot


@test_case(
    id="TEST-WF020-TC008",
    name="Every ir.cron from the inventory exists, is active, and has the "
         "expected interval",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account_workday, novobi_sftp_connection, queue_job",
    priority="P1", kind="DATA", order=20008,
    description="The cron set for the three WF-020 modules, keyed by XML "
                "id with its active flag, interval and priority: captured "
                "as the baseline on v17 and diffed on v19.",
    traceability=trace("DATAONE-TC008"))
def test_tc008(ctx):
    from framework.fg_common import reconcile

    with ctx.step("Precondition: at least one of the three modules "
                  "contributes a cron on this target"):
        rows = cron_rows(ctx.adapter.rpc)
        ctx.log(f"cron inventory ({len(rows)}): "
                f"{[r['xml_id'] for r in rows]}")
        if not rows:
            ctx.blocked(
                "No ir.cron records are reflected for "
                f"{', '.join(CRON_MODULES)} on {ctx.env.key} (db="
                f"{ctx.env.db}). Either the modules are not installed or "
                "their crons were never reflected into ir.model.data — "
                "there is no inventory to compare.")

    reconcile(ctx, "DATAONE-TC008", _capture_crons)

    with ctx.step("Every cron in the inventory is active"):
        inactive = [r["xml_id"] for r in cron_rows(ctx.adapter.rpc)
                    if not r["active"]]
        ctx.check("inactive crons in the inventory", [], inactive)


@test_case(
    id="TEST-WF020-TC459",
    name="Every cron in the inventory exists, is active, has the expected "
         "interval, and runs",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account_workday, novobi_sftp_connection, queue_job",
    priority="P0", kind="DATA", order=20459,
    description="The inventory half is asserted (existence, active flag, "
                "interval and the ir.actions.server behind each cron); the "
                "'Run Manually of each cron' half is BLOCKED because "
                "firing the pollers and exporters reaches the Workday SFTP "
                "endpoint.",
    traceability=trace("DATAONE-TC459"))
def test_tc459(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Dump the cron inventory with its XML ids"):
        rows = cron_rows(rpc)
        ctx.log(f"cron inventory ({len(rows)}): {rows!r}")
        if not rows:
            ctx.blocked(
                "No ir.cron records are reflected for "
                f"{', '.join(CRON_MODULES)} on {ctx.env.key}. There is no "
                "inventory to assert.")

    with ctx.step("Every cron exists with a resolvable XML id and is "
                  "active"):
        inactive = [r["xml_id"] for r in rows if not r["active"]]
        ctx.check("inactive crons", [], inactive)

    with ctx.step("Every cron has a positive interval — a zero or missing "
                  "interval means it never fires"):
        bad = {r["xml_id"]: (r["interval_number"], r["interval_type"])
               for r in rows
               if not r["interval_number"] or not r["interval_type"]}
        ctx.check("crons with no usable interval", {}, bad)

    with ctx.step("Each cron resolves to a server action with a non-empty "
                  "body — a cron whose action lost its body fires and does "
                  "nothing"):
        # v17 ir.cron _inherits ir.actions.server, so state/code are
        # readable straight off the cron. The workbook flags that the
        # inherits may not survive v19, so the fields are probed first
        # rather than assumed.
        extra = [f for f in ("state", "code")
                 if rpc.field_exists("ir.cron", f)]
        if len(extra) < 2:
            ctx.log("ir.cron no longer exposes the server action's "
                    f"state/code directly (present: {extra}) — the "
                    "inherits changed on this version; skipping the "
                    "empty-body check rather than asserting on a shape "
                    "that no longer exists")
        else:
            detail = rpc.search_read(
                "ir.cron", [("id", "in", [r["id"] for r in rows])],
                ["cron_name", "state", "code"])
            ctx.log(f"cron actions: {detail!r}")
            empty = [d["cron_name"] for d in detail
                     if d.get("state") == "code"
                     and not (d.get("code") or "").strip()]
            ctx.check("crons whose code body is empty", [], empty)

    with ctx.step("Record the shared crons whose deactivation would take "
                  "several workflows down together"):
        present = {x: why for x, why in SHARED_CRONS.items()
                   if x in {r["xml_id"] for r in rows}}
        for xml_id, why in present.items():
            ctx.log(f"SHARED: {xml_id} — {why}")
        if not present:
            ctx.log("none of the known shared crons are present on this "
                    "target")

    with ctx.step("The 'Run Manually of each cron' half needs the Workday "
                  "endpoint"):
        ctx.blocked(
            "Running each cron manually would call "
            "sftp.server.cron_get_sftp_files / cron_post_sftp_files and "
            "dto_account_workday's cron_export_workday_vendor_bill / "
            "cron_export_workday_journal_entry, all of which open an SFTP "
            "connection to Workday. Convention rule 4 forbids reaching an "
            "external system from this platform, and the QA clone's "
            "connectors are deactivated precisely so that cannot happen. "
            "Run that half from a scratch instance pointed at the TD-SF-01 "
            "test endpoint. The inventory half above — existence, active "
            "flag, interval, and a non-empty action body — is the part this "
            "platform owns.")


@test_case(
    id="TEST-WF020-TC460",
    name="A repeatedly failing cron is auto-deactivated on v19, silently "
         "stopping the daily Workday export",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account_workday, novobi_sftp_connection",
    priority="P0", kind="DATA", order=20460,
    description="Records which side of the v19 cron auto-deactivation "
                "delta this target is on — failure_count, "
                "first_failure_date and deactivate exist on v19 and on no "
                "earlier version — and the blast radius of the shared "
                "poller. Forcing N consecutive failures needs the crons to "
                "fire and is BLOCKED.",
    traceability=trace("DATAONE-TC460"))
def test_tc460(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Step 1: record the target's ir.cron shape — the v19 "
                  "failure-tracking fields"):
        info = rpc.call("ir.cron", "fields_get", V19_CRON_FIELDS,
                        attributes=["type", "string"])
        present = sorted(info)
        absent = sorted(set(V19_CRON_FIELDS) - set(info))
        ctx.log(f"present: {present}; absent: {absent}")

    with ctx.step("The version delta is exactly as the workbook states: "
                  "v17 has none of the failure-tracking fields, v19 "
                  "has them"):
        expected = ([], sorted(V19_CRON_FIELDS)) \
            if ctx.env.version == "17" else (sorted(V19_CRON_FIELDS), [])
        ctx.check(f"(present, absent) on Odoo {ctx.env.version}",
                  {"present": expected[0], "absent": expected[1]},
                  {"present": present, "absent": absent})

    with ctx.step("The rest of the workbook's v19_watch list - deactivate, "
                  "done, remaining, timed_out_counter - is on "
                  f"{V19_CRON_PROGRESS_MODEL}, not on ir.cron"):
        # The workbook writes "ir.cron gains deactivate, done,
        # failure_count, first_failure_date, remaining,
        # timed_out_counter". Only the middle pair is on ir.cron
        # (ir_cron.py:121-122); the rest are fields of IrCronProgress
        # (ir_cron.py:918-927), the model the new progress API writes
        # through. Each half of the delta is asserted against the
        # model that carries it, so a correct v19 target passes and a
        # target missing the progress model still fails.
        if not rpc.model_exists(V19_CRON_PROGRESS_MODEL):
            ctx.check(f"{V19_CRON_PROGRESS_MODEL} exists on Odoo "
                      f"{ctx.env.version}",
                      ctx.env.version == "19", False)
        else:
            pinfo = rpc.call(V19_CRON_PROGRESS_MODEL, "fields_get",
                             V19_CRON_PROGRESS_FIELDS,
                             attributes=["type", "string"])
            ctx.log(f"{V19_CRON_PROGRESS_MODEL} fields: "
                    f"{sorted(pinfo)}")
            ctx.check(f"progress fields on Odoo {ctx.env.version}",
                      sorted(V19_CRON_PROGRESS_FIELDS),
                      sorted(pinfo))

    with ctx.step("Step 2: the subject cron exists and starts clean"):
        rows = cron_rows(rpc)
        subject = next(
            (r for r in rows
             if r["xml_id"] ==
             "novobi_sftp_connection.ir_cron_process_sftp_files"), None)
        if subject is None:
            ctx.log("ir_cron_process_sftp_files is not reflected on this "
                    f"target; available: {[r['xml_id'] for r in rows]}")
        else:
            ctx.log(f"subject cron: {subject!r}")
            ctx.check("subject cron is active", True, subject["active"])
            if "failure_count" in info:
                fc = rpc.read("ir.cron", [subject["id"]],
                              ["failure_count", "first_failure_date"])[0]
                ctx.log(f"failure state: {fc!r}")
                ctx.check("failure_count starts at 0", 0,
                          fc["failure_count"])

    with ctx.step("Step 13 (blast radius): the shared poller's "
                  "deactivation takes three workflows down together"):
        ctx.log("novobi_sftp_connection.ir_cron_process_sftp_files is "
                "consumed by WF-010 (MO test-result import), WF-019 "
                "(vendor-payment import) and WF-020 (supplier master "
                "import). One malformed file that makes it raise on every "
                "run therefore stops all three feeds at once on v19.")

    with ctx.step("Steps 3-18 need the crons to fire repeatedly"):
        ctx.blocked(
            "Forcing N consecutive cron failures requires firing "
            "cron_process_sftp_files and cron_export_workday_vendor_bill "
            "against a live SFTP endpoint (or monkeypatching them "
            "in-process), then waiting through real scheduler windows. "
            "This platform never fires crons or reaches an external system "
            "(convention rule 4), and the workbook itself scopes this case "
            "to a scratch v19 instance, 'never on anything shared'. Run it "
            "there. The version delta above — which ir.cron fields this "
            "target has — is the half that decides whether the silent "
            "failure mode exists at all, and it is asserted.")
