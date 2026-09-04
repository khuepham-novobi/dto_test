"""DATAONE-WF-020 — the cases that genuinely need the endpoint:
TC293, TC294, TC295, TC305.

All four are **blocked stubs with an asserted offline half**. Their essence
is what the SFTP transport does against a live remote folder — downloading,
archiving with a collision suffix, auto-creating an archive directory,
surviving repeated poll failures. This platform never reaches an external
host (convention rule 4), and the QA clone's connectors are deactivated
precisely so it cannot.

What is asserted before each block is the local, observable half the
endpoint test would otherwise take on faith: that the crons exist at the
five-minute interval the workbook expects, that the record shapes and the
archive configuration are what the flow depends on, and — for TC305 —
which side of the v19 auto-deactivation delta this target is on.

EXPECTED v17 OUTCOME: BLOCKED for all four, after the offline assertions.
EXPECTED v19 OUTCOME: BLOCKED, same reason.
"""
from framework.registry import test_case
from tests.wf020.common import (MARK, V19_CRON_FIELDS,  # noqa: F401
                                V19_CRON_PROGRESS_FIELDS,
                                V19_CRON_PROGRESS_MODEL, WORKFLOW,
                                WORKFLOW_NAME, cron_rows, fx, make_folder,
                                make_server, require_sftp_stack,
                                sweep_wf020, trace)

GET_CRON = "novobi_sftp_connection.ir_cron_get_sftp_files"
PROCESS_CRON = "novobi_sftp_connection.ir_cron_process_sftp_files"

NO_ENDPOINT = (
    "This platform never opens a connection to an external host "
    "(convention rule 4), and the QA clone's SFTP connectors are "
    "deactivated so it cannot. ")


def _cron(rpc, xml_id):
    return next((r for r in cron_rows(rpc) if r["xml_id"] == xml_id), None)


@test_case(
    id="TEST-WF020-TC293",
    name="The 5-minute GET pull creates a Pending sftp.file with an "
         "attachment and a Remote Path",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="novobi_sftp_connection", priority="P0", kind="API", order=20293,
    description="Offline half: the GET poller exists at a five-minute "
                "interval and is active, and the sftp.file record shape the "
                "pull produces (ref = <folder path>/<file name>, name "
                "computed from ref, state pending, attachment linked) is "
                "verified on a locally built record. The pull itself needs "
                "the endpoint.",
    traceability=trace("DATAONE-TC293"))
def test_tc293(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-020 fixtures and open a fresh "
                  "namespace"):
        sweep_wf020(rpc)

    with ctx.step("Precondition: the transport is installed"):
        require_sftp_stack(ctx)

    try:
        with ctx.step("The GET poller exists, is active, and fires every "
                      "five minutes"):
            cron = _cron(rpc, GET_CRON)
            ctx.check_true(f"{GET_CRON} is reflected", cron is not None,
                           actual_desc=repr(cron))
            ctx.check("GET poller active", True, cron["active"])
            ctx.check("GET poller interval",
                      {"number": 5, "type": "minutes"},
                      {"number": cron["interval_number"],
                       "type": cron["interval_type"]})

        with ctx.step("The record shape the pull produces: name is computed "
                      "from the Remote Path's last segment, state defaults "
                      "to pending, and the attachment carries the payload"):
            from tests.wf020.common import make_sftp_file
            server_id = make_server(rpc, label="Pull")
            folder_id = make_folder(rpc, server_id, usage="none")
            file_name = fx(f"{MARK}_probe.csv")
            file_id = make_sftp_file(rpc, folder_id, file_name, b"a,b\n1,2\n")
            row = rpc.read("sftp.file", [file_id],
                           ["name", "ref", "state", "attachment_id",
                            "folder_id", "usage", "action"])[0]
            ctx.log(f"sftp.file: {row!r}")
            folder_path = rpc.read("sftp.folder", [folder_id],
                                   ["path"])[0]["path"]
            ctx.check("Remote Path", f"{folder_path}/{file_name}", row["ref"])
            ctx.check("name computed from the Remote Path's last segment",
                      file_name, row["name"])
            ctx.check("state on arrival", "pending", row["state"])
            ctx.check_true("an attachment is linked",
                           bool(row["attachment_id"]),
                           actual_desc=repr(row["attachment_id"]))
            ctx.check("action inherited from the server", "GET",
                      row["action"])

        with ctx.step("The download itself needs the Workday SFTP endpoint"):
            ctx.blocked(
                NO_ENDPOINT +
                "Driving the pull means sftp.server.cron_get_sftp_files -> "
                "sftp.folder.action_get_files(connection) -> "
                "SFTPConnection.get_files against a real remote folder. Run "
                "it against the TD-SF-01 test endpoint from a scratch "
                "instance. The poller's schedule and the record shape it "
                "produces are asserted above.")
    finally:
        with ctx.step("Cleanup WF-020 fixtures"):
            try:
                sweep_wf020(rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")


@test_case(
    id="TEST-WF020-TC294",
    name="Archive-on-download, including the (YYYY-MM-DD HHMMSS UTC) "
         "collision suffix",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="novobi_sftp_connection", priority="P1", kind="API", order=20294,
    description="Offline half: archive-on-download is governed by "
                "sftp.server.archive_auto (default True) and the archive "
                "path resolution order folder.archive_path -> "
                "server.archive_path -> auto-created. Moving a file twice "
                "to observe the collision suffix needs the endpoint.",
    traceability=trace("DATAONE-TC294"))
def test_tc294(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-020 fixtures and open a fresh "
                  "namespace"):
        sweep_wf020(rpc)

    with ctx.step("Precondition: the transport is installed"):
        require_sftp_stack(ctx)

    try:
        with ctx.step("archive_auto exists on sftp.server and defaults to "
                      "True — archiving is on unless someone turns it off"):
            info = rpc.call("sftp.server", "fields_get",
                            ["archive_auto", "archive_path"],
                            attributes=["type", "string"])
            ctx.log(f"server archive fields: {info!r}")
            ctx.check("archive_auto type", "boolean",
                      info["archive_auto"]["type"])
            probe = rpc.call("sftp.server", "default_get", ["archive_auto"])
            ctx.check("archive_auto default", True,
                      probe.get("archive_auto"))

        with ctx.step("The archive path resolution order the move depends "
                      "on: folder.archive_path, then server.archive_path"):
            for model in ("sftp.folder", "sftp.server"):
                fields = rpc.call(model, "fields_get", ["archive_path"],
                                  attributes=["type"])
                ctx.check_true(f"{model}.archive_path exists",
                               "archive_path" in fields,
                               actual_desc=repr(fields))

        with ctx.step("Moving a downloaded file into the archive needs the "
                      "Workday SFTP endpoint"):
            ctx.blocked(
                NO_ENDPOINT +
                "Archive-on-download and its "
                "'(YYYY-MM-DD HHMMSS UTC)' collision suffix are produced by "
                "SFTPConnection while moving a remote file, so observing "
                "them means downloading the same file name twice against a "
                "real server. Run it against TD-SF-01 from a scratch "
                "instance.")
    finally:
        with ctx.step("Cleanup WF-020 fixtures"):
            try:
                sweep_wf020(rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")


@test_case(
    id="TEST-WF020-TC295",
    name="No archive path configured — <path>_archived is auto-created and "
         "written back",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="novobi_sftp_connection", priority="P2", kind="API", order=20295,
    description="Offline half: a folder created with no archive_path, and "
                "on a server with none either, is the precondition the "
                "auto-create branch needs; the helper writes the created "
                "path back onto the folder record. Creating the remote "
                "directory needs the endpoint.",
    traceability=trace("DATAONE-TC295"))
def test_tc295(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-020 fixtures and open a fresh "
                  "namespace"):
        sweep_wf020(rpc)

    with ctx.step("Precondition: the transport is installed"):
        require_sftp_stack(ctx)

    try:
        with ctx.step("Build the precondition: neither the folder nor its "
                      "server carries an archive path"):
            server_id = make_server(rpc, label="NoArchive")
            folder_id = make_folder(rpc, server_id, usage="none")
            rows = rpc.read("sftp.folder", [folder_id],
                            ["path", "archive_path"])[0]
            server = rpc.read("sftp.server", [server_id],
                              ["archive_path"])[0]
            ctx.check("folder archive_path", False, rows["archive_path"])
            ctx.check("server archive_path", False, server["archive_path"])
            ctx.log(f"the auto-created path would be "
                    f"{rows['path']}_archived")

        with ctx.step("Creating the remote directory needs the Workday "
                      "SFTP endpoint"):
            ctx.blocked(
                NO_ENDPOINT +
                "sftp.folder.get_or_auto_create_archive_path calls "
                "connection.create_folder('<path>_archived') and writes the "
                "result back onto the folder — the branch cannot run "
                "without a connection that can create a directory. Run it "
                "against TD-SF-01. The precondition it needs (no archive "
                "path at either level) and the path it would derive are "
                "asserted above.")
    finally:
        with ctx.step("Cleanup WF-020 fixtures"):
            try:
                sweep_wf020(rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")


@test_case(
    id="TEST-WF020-TC305",
    name="v19: repeated cron failure silently deactivates the poller",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="novobi_sftp_connection", priority="P0", kind="DATA", order=20305,
    description="Offline half: which side of the v19 auto-deactivation "
                "delta this target is on, and that the GET poller is "
                "currently active with a five-minute interval — the "
                "conditions under which a persistent failure would switch "
                "it off. Forcing the failures needs the cron to fire.",
    traceability=trace("DATAONE-TC305"))
def test_tc305(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Record which ir.cron failure-tracking fields this "
                  "target has"):
        info = rpc.call("ir.cron", "fields_get", V19_CRON_FIELDS,
                        attributes=["type"])
        present = sorted(info)
        ctx.log(f"present on Odoo {ctx.env.version}: {present}")

    with ctx.step("The delta is exactly as the workbook states: v19 "
                  "added the failure-tracking fields, v17 has none"):
        # `deactivate` is NOT one of them: it is a field of
        # ir.cron.progress (ir_cron.py:918-926), not of ir.cron, so it
        # is asserted against that model below. See
        # tests/wf020/common.py:V19_CRON_FIELDS.
        expected = [] if ctx.env.version == "17" else sorted(V19_CRON_FIELDS)
        ctx.check(f"v19 failure-tracking fields on Odoo {ctx.env.version}",
                  expected, present)
        if ctx.env.version != "17" and rpc.model_exists(
                V19_CRON_PROGRESS_MODEL):
            pinfo = rpc.call(V19_CRON_PROGRESS_MODEL, "fields_get",
                             V19_CRON_PROGRESS_FIELDS,
                             attributes=["type"])
            ctx.check(f"{V19_CRON_PROGRESS_MODEL} deactivation flag",
                      sorted(V19_CRON_PROGRESS_FIELDS), sorted(pinfo))

    with ctx.step("The GET poller is active at five minutes — so a "
                  "persistent failure would be retried often enough to "
                  "cross any deactivation threshold quickly"):
        cron = _cron(rpc, GET_CRON)
        if cron is None:
            ctx.blocked(
                f"{GET_CRON} is not reflected on {ctx.env.key}; "
                "novobi_sftp_connection's cron data was not loaded, so "
                "there is no poller whose deactivation could be assessed.")
        ctx.check("GET poller active", True, cron["active"])
        ctx.check("GET poller interval",
                  {"number": 5, "type": "minutes"},
                  {"number": cron["interval_number"],
                   "type": cron["interval_type"]})

    with ctx.step("Forcing repeated failures needs the cron to fire"):
        ctx.blocked(
            NO_ENDPOINT +
            "Making cron_get_sftp_files raise on ten consecutive scheduled "
            "firings, then reading back active / failure_count / "
            "first_failure_date, requires the scheduler to actually run the "
            "job against a reachable (or deliberately unreachable) "
            "endpoint. The workbook scopes this to a scratch v19 instance. "
            "The delta that makes the silent failure possible is asserted "
            "above, and TEST-WF020-TC302 proves the defect that would "
            "trigger it.")
