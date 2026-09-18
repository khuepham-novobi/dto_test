"""DATAONE-WF-018 — the upload half: TC296, TC300, TC304.

Shared with DATAONE-WF-017; owned here, because WF-018 has the lower build
order of the two (21 against 24). WF-017 references these tc_ids and must
not re-implement them (AUTOMATION_CONVENTIONS.md, "Shared test cases").

All three cases are about ``SFTPConnection.send_files`` reaching a real
SFTP endpoint, which convention rule 4 forbids: the QA clone has the
Workday connector deactivated and no test may reactivate it, configure
credentials, or call a method that opens a socket. Each case is therefore
implemented as a **blocked stub** — its offline half is asserted in full
first, and only then does it call ``ctx.blocked`` with a precise reason.

The offline halves are not filler. Each one is the part of its case that
can be got wrong by a port without any endpoint being involved:

* **TC296** — the duplicate guard compares ``file.ref`` (a full remote
  path) with ``exists()`` while ``put()`` writes ``attachment.name``
  relative to the CWD set by ``chdir(folder.path)``
  (``sftp_connection.py:310-328``). They agree only while
  ``ref == folder.path + '/' + name``. That invariant is a **pure
  database fact** and is asserted here on the file WF-018's own export
  produced. If a port changes how ``ref`` is built, the duplicate check
  breaks without the upload breaking — the dangerous direction — and this
  assertion catches it with no endpoint at all.
* **TC300** — ``action_repost`` refuses a selection containing a Done file
  (``sftp_file.py:230-232``) before it opens any connection, so the
  guard in step 7 is fully testable offline. The grouping in step 3 is
  not.
* **TC304** — ``put()`` reads ``attachment._full_path(store_fname)``. An
  attachment stored in the database has an empty ``store_fname``. Which
  storage this instance uses is ``ir_attachment.location``, a system
  parameter — reading it is exactly the "record the current value from the
  client's environment so the risk can be closed rather than carried" the
  workbook's own notes ask for.

EXPECTED v17 OUTCOME: BLOCKED (all three), after the offline assertions
pass. EXPECTED v19 OUTCOME: the same. A BLOCKED verdict here is the
correct one, not a gap — the gap is named in
``reports/data/wf018_feasibility.json`` with the endpoint each case needs.
"""
from framework.registry import test_case
from tests.wf018.common import (MARK, POST_CRON_XMLID,  # noqa: F401
                                TEMPLATE_FILE_NAME, WORKFLOW, WORKFLOW_NAME,
                                cron_row, ensure_product, ensure_vendor,
                                expect_error, latest_workbook, m2o_id,
                                make_bill, make_post_folder, make_post_server,
                                produced_files, require_vendor_bill_usage,
                                require_workday_export, restore_company,
                                retarget_company, run_export, sweep_wf018,
                                template_id, trace)

BLOCKED_ENDPOINT = (
    "requires a reachable SFTP endpoint — SFTPConnection.send_files() opens "
    "a paramiko session (sftp_connection.py:305 self.ssh.open_sftp()) and "
    "this suite may not reactivate the Workday connector, configure "
    "credentials, or call sftp.server.get_sftp_connection / "
    "sftp.folder.action_post_files / sftp.file.action_repost / "
    "cron_post_sftp_files (AUTOMATION_CONVENTIONS.md rule 4). ")


def _one_pending_post_file(ctx):
    """Produce one real Pending POST sftp.file through WF-018's own export.

    Returns (folder_id, file_row, cid, original). The caller MUST restore
    the company in its own ``finally``.
    """
    rpc = ctx.adapter.rpc
    tmpl_id = template_id(ctx)
    server_id = make_post_server(rpc)
    folder_id = make_post_folder(rpc, server_id)
    cid, original = retarget_company(ctx, folder_id, template_ref=tmpl_id)
    vendor_id = ensure_vendor(rpc)
    product_id = ensure_product(ctx)
    bill_id = make_bill(ctx, vendor_id, [{"product_id": product_id}],
                        "POST-101", label="BB-POST")
    run_export(ctx, [bill_id], mark_exported=True)
    files = produced_files(rpc, folder_id)
    if not files:
        ctx.blocked("The export produced no sftp.file, so there is no "
                    "Pending POST record to reason about.")
    return folder_id, files[-1], cid, original


@test_case(
    id="TEST-WF018-TC296",
    name="POST duplicate guard refuses to overwrite and sets the file Failed",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="novobi_sftp_connection", priority="P0", kind="API", order=18296,
    description="Asserts offline the invariant the remote duplicate guard "
                "rests on — that sftp.file.ref equals folder.path + '/' + "
                "attachment name, because exists() checks ref while put() "
                "writes the attachment name under chdir(folder.path) — then "
                "BLOCKS on the endpoint the overwrite assertion needs.",
    traceability=trace("DATAONE-TC296", user_story="shared with "
                                                   "DATAONE-WF-017"))
def test_tc296(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-018 fixtures and open a fresh "
                  "namespace"):
        sweep_wf018(rpc)

    with ctx.step("Preconditions: the export stack and the usage key"):
        require_workday_export(ctx)
        require_vendor_bill_usage(ctx)

    cid = None
    original = {}
    try:
        with ctx.step("Produce one real Pending POST file through WF-018's "
                      "own export, against an INACTIVE fixture server"):
            folder_id, file_row, cid, original = _one_pending_post_file(ctx)
            folder = rpc.read("sftp.folder", [folder_id],
                              ["path", "action", "last_sync_state"])[0]
            ctx.log(f"folder: {folder!r}")
            ctx.log(f"pending POST file: {file_row!r}")
            ctx.check("file state", "pending", file_row["state"])
            ctx.check("file action", "POST", file_row["action"])

        with ctx.step("THE OFFLINE HALF — ref == folder.path + '/' + "
                      "attachment.name. exists() checks ref (line 316) "
                      "while put() writes attachment.name relative to "
                      "chdir(folder.path) (lines 310, 327). A port that "
                      "changes ref construction breaks the guard WITHOUT "
                      "breaking the upload — the dangerous direction"):
            attachment_id = m2o_id(file_row["attachment_id"])
            attachment = rpc.read("ir.attachment", [attachment_id],
                                  ["name", "mimetype"])[0]
            ctx.log(f"attachment: {attachment!r}")
            ctx.check("sftp.file.ref is exactly folder.path + '/' + the "
                      "attachment name the upload will write",
                      f"{folder['path']}/{attachment['name']}",
                      file_row["ref"])
            ctx.check("the attachment is named for Workday's own workbook",
                      TEMPLATE_FILE_NAME, attachment["name"])
            ctx.check("sftp.file.name is the basename of ref",
                      TEMPLATE_FILE_NAME, file_row["name"])

        with ctx.step("THE OFFLINE HALF — the filename carries no timestamp, "
                      "so every export of this flow targets the SAME remote "
                      "path. The remote exists() check is the only thing "
                      "between a second export and Workday's copy being "
                      "replaced"):
            vendor_id = ensure_vendor(rpc)
            product_id = ensure_product(ctx)
            second = make_bill(ctx, vendor_id, [{"product_id": product_id}],
                               "POST-102", label="BB-POST-2")
            run_export(ctx, [second], mark_exported=True)
            files = produced_files(rpc, folder_id)
            refs = [row["ref"] for row in files]
            ctx.log(f"refs produced by two consecutive exports: {refs!r}")
            ctx.check("two exports produced two files", 2, len(files))
            ctx.check("both target the identical remote path — the "
                      "collision this case is about is real",
                      1, len(set(refs)))

        with ctx.step("THE OFFLINE HALF — the POST cron exists and is the "
                      "only thing that would upload them"):
            cron = cron_row(rpc, POST_CRON_XMLID)
            ctx.log(f"{POST_CRON_XMLID}: {cron!r}")
            ctx.check_true(f"{POST_CRON_XMLID} resolves", bool(cron),
                           actual_desc=repr(cron))
            if cron is not None:
                ctx.check_true(
                    "the POST cron is NOT active on this QA target — rule 4 "
                    "requires the connector to be deactivated, and an "
                    "active cron would upload the fixture files this suite "
                    "produces",
                    not cron.get("active"), actual_desc=repr(cron))

        with ctx.step("BLOCKED — the remaining assertions need a remote "
                      "server"):
            ctx.blocked(
                BLOCKED_ENDPOINT
                + "Steps 1-12 additionally need a DECOY file pre-placed at "
                  f"<folder.path>/{TEMPLATE_FILE_NAME} with a recorded "
                  "SHA-256, an independent SFTP session to re-read it after "
                  "the run, and the ability to delete it and Re-post. What "
                  "cannot be asserted here: that the upload is SKIPPED not "
                  "attempted, the verbatim sftp.log message 'SFTP File "
                  "<ref> already existed on <path>' "
                  "(sftp_connection.py:317), that the remote bytes and "
                  "st_mtime are unchanged, folder.last_sync_state = "
                  "'failed', and that Re-post succeeds once the collision "
                  "is cleared.")
    finally:
        if cid:
            restore_company(ctx, cid, original)


@test_case(
    id="TEST-WF018-TC300",
    name="Re-post returns a Failed POST file to Pending and re-uploads",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="novobi_sftp_connection", priority="P1", kind="API", order=18300,
    description="Asserts offline the Done-in-selection guard that "
                "action_repost applies before it opens any connection, and "
                "that the method filters to Failed POST files only; BLOCKS "
                "on the endpoint the re-upload and the one-connection-per-"
                "server grouping assertions need.",
    traceability=trace("DATAONE-TC300", user_story="shared with "
                                                   "DATAONE-WF-017"))
def test_tc300(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-018 fixtures and open a fresh "
                  "namespace"):
        sweep_wf018(rpc)

    with ctx.step("Preconditions: the export stack and the usage key"):
        require_workday_export(ctx)
        require_vendor_bill_usage(ctx)

    cid = None
    original = {}
    try:
        with ctx.step("Produce one real POST file and drive it to Failed "
                      "WITHOUT any network — mark_sync_failed is a public "
                      "model method that writes state and files the "
                      "activity, exactly as a transport failure would"):
            folder_id, file_row, cid, original = _one_pending_post_file(ctx)
            rpc.call("sftp.file", "mark_sync_failed", [file_row["id"]],
                     "2026-01-15 09:00:00", "QA fixture: simulated "
                                            "transport failure")
            failed = rpc.read("sftp.file", [file_row["id"]],
                              ["state", "process_date", "action"])[0]
            ctx.log(f"file after mark_sync_failed: {failed!r}")
            ctx.check("state", "failed", failed["state"])
            ctx.check_true("process_date stamped",
                           bool(failed["process_date"]),
                           actual_desc=repr(failed["process_date"]))

        with ctx.step("THE OFFLINE HALF (step 7) — Re-post refuses a "
                      "selection containing a Done file, and refuses it "
                      "BEFORE opening a connection (sftp_file.py:231-232, "
                      "the first statement of action_repost)"):
            done_id = rpc.create("sftp.file", {
                "folder_id": folder_id,
                "ref": f"{rpc.read('sftp.folder', [folder_id], ['path'])[0]['path']}"
                       f"/{MARK}_already_done.xlsx",
                "state": "done",
            })
            raised, message = expect_error(
                rpc.call, "sftp.file", "action_repost",
                [file_row["id"], done_id])
            ctx.log(f"action_repost on a mixed selection: raised={raised} "
                    f"msg={message!r}")
            ctx.check_true("the mixed selection is refused", raised,
                           actual_desc=message)
            ctx.check_true(
                "with the exact 'File(s) have been processed already!' "
                "message",
                "File(s) have been processed already!" in message,
                actual_desc=message)
            still = rpc.read("sftp.file", [file_row["id"]], ["state"])[0]
            ctx.check("the Failed file was NOT flipped to pending by the "
                      "refused call", "failed", still["state"])

        with ctx.step("THE OFFLINE HALF — action_repost's own filter: only "
                      "Failed AND POST files are re-posted, so a Failed GET "
                      "file in the same selection is silently ignored "
                      "rather than uploaded"):
            ctx.log("sftp_file.py:234 — files = self.filtered(lambda file: "
                    "file.state == 'failed' and file.action == 'POST'). "
                    "The Done guard above is the only one that raises; a "
                    "Failed GET file passes the guard and is then dropped "
                    "by this filter, reaching neither the poller nor the "
                    "uploader. Recorded as a latent shape, not asserted "
                    "here, because building a GET fixture would need a "
                    "second server and proves nothing extra offline.")
            ctx.log("get_pending_files() is decorated @api.model but reads "
                    "self.file_ids (sftp_folder.py:169-171). It works today "
                    "only because it is always called on a singleton — a "
                    "latent defect to carry into the port's review.")

        with ctx.step("BLOCKED — the remaining assertions need a remote "
                      "server"):
            ctx.blocked(
                BLOCKED_ENDPOINT
                + "Steps 1-6 additionally need three Failed POST files "
                  "across two folders of one server, the paramiko DEBUG "
                  "logger on so connection opens can be counted, and an "
                  "independent SFTP session to verify the uploaded bytes. "
                  "What cannot be asserted here: that all three reach Done "
                  "with a fresh process_date, that ONE connection is opened "
                  "per SERVER rather than one per file "
                  "(sftp_file.py:237-244, odoo.tools.groupby), that the "
                  "remote bytes match the attachments, and that each "
                  "folder's last_sync_state reads Success.")
    finally:
        if cid:
            restore_company(ctx, cid, original)


@test_case(
    id="TEST-WF018-TC304",
    name="A database-stored attachment cannot be POSTed (store_fname empty)",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="novobi_sftp_connection", priority="P2", kind="API", order=18304,
    description="Records this instance's ir_attachment.location — the "
                "system parameter that decides whether the defect is latent "
                "— and asserts that the attachment WF-018 produces carries "
                "a store_fname, which is the precondition put() depends on; "
                "BLOCKS on the endpoint the upload-failure assertions need.",
    traceability=trace("DATAONE-TC304", user_story="shared with "
                                                   "DATAONE-WF-017"))
def test_tc304(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-018 fixtures and open a fresh "
                  "namespace"):
        sweep_wf018(rpc)

    with ctx.step("Preconditions: the export stack and the usage key"):
        require_workday_export(ctx)
        require_vendor_bill_usage(ctx)

    cid = None
    original = {}
    try:
        with ctx.step("THE OFFLINE HALF — record ir_attachment.location "
                      "from THIS environment. That value is what decides "
                      "whether the defect is latent or live, and the "
                      "workbook asks for it explicitly so the risk can be "
                      "closed rather than carried"):
            rows = rpc.search_read(
                "ir.config_parameter",
                [("key", "=", "ir_attachment.location")], ["value"])
            location = rows[0]["value"] if rows else "(unset — filestore)"
            ctx.log(f"ir_attachment.location on {ctx.env.key} "
                    f"(db={ctx.env.db}) = {location!r}")
            ctx.check_true(
                "this instance does NOT store attachments in the database — "
                "put() reads attachment._full_path(store_fname) and a "
                "db-stored attachment has an empty store_fname, so the "
                "export would silently never reach Workday",
                not str(location).lower().startswith("db"),
                actual_desc=repr(location))

        with ctx.step("THE OFFLINE HALF — the attachment WF-018 actually "
                      "produces is filestore-backed, i.e. put()'s "
                      "precondition holds for the real payload"):
            folder_id, file_row, cid, original = _one_pending_post_file(ctx)
            attachment_id = m2o_id(file_row["attachment_id"])
            fields_ = ["name", "type", "mimetype", "file_size"]
            for optional in ("store_fname", "db_datas"):
                if rpc.field_exists("ir.attachment", optional):
                    fields_.append(optional)
            attachment = rpc.read("ir.attachment", [attachment_id],
                                  fields_)[0]
            ctx.log(f"produced attachment: "
                    f"{ {k: v for k, v in attachment.items() if k != 'db_datas'} !r}")
            ctx.check("attachment type", "binary", attachment["type"])
            ctx.check_true("the produced workbook is not empty",
                           (attachment.get("file_size") or 0) > 0,
                           actual_desc=repr(attachment.get("file_size")))
            if "store_fname" in attachment:
                ctx.check_true(
                    "store_fname is populated — put()'s localpath resolves",
                    bool(attachment["store_fname"]),
                    actual_desc=repr(attachment["store_fname"]))
            else:
                ctx.log("[warn] ir.attachment.store_fname is not readable "
                        "over RPC on this target (it is groups-restricted "
                        "in some configurations), so the filestore check "
                        "rests on ir_attachment.location alone.")

        with ctx.step("BLOCKED — the remaining assertions need a remote "
                      "server"):
            ctx.blocked(
                BLOCKED_ENDPOINT
                + "Steps 1-6 additionally need ir_attachment.location "
                  "switched to 'db' for one attachment (which changes every "
                  "subsequent case until it is restored, so it must not be "
                  "done unattended) and a remote folder listing to prove "
                  "nothing was written. What cannot be asserted here: that "
                  "the file goes Failed rather than Done, the VERBATIM "
                  "sftp.log message — and in particular whether it is a "
                  "comprehensible business message or a raw TypeError / "
                  "FileNotFoundError, which is what decides whether the "
                  "guard is worth adding — and that Re-post succeeds after "
                  "converting the attachment back to filestore storage.")
    finally:
        if cid:
            restore_company(ctx, cid, original)
