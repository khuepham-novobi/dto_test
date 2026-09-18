"""DATAONE-WF-001 — the commonest configuration mistake: TC303.

A folder created without its usage key. The result is **not an error**:
files download, records appear, and nothing ever happens to them. Somebody
must know that "Pending forever" means "usage not set", because nothing on
the screen says so.

Why it is Pending forever, precisely
------------------------------------
Two different filters are involved and only one of them excludes the file:

* ``sftp.file.cron_process_sftp_files`` searches
  ``[('action','=','GET'), ('state','=','pending'), ('usage','!=','none')]``
  (``sftp_file.py:256-260``) — so the poller never even selects it;
* ``sftp.file._process_sftp_file`` returns ``(True, '')`` for
  ``usage == 'none'`` (``sftp_file.py:203-207``) — so if a human DOES press
  Process Now, the file goes straight to Done having done nothing.

Those two facts together are the whole finding: the file is invisible to
the scheduler and a manual attempt "succeeds". This case asserts both, and
the second is the more dangerous of the two — an operator who presses the
button sees a green Done and concludes the file was handled.

Step 9 is the durable half, and it is a frozen contract
-------------------------------------------------------
The usage key is **literally interpolated into a Python method name**::

    SFTPExtractor.run:  getattr(self, f'_run_extractor_{business_process}')

So a rename during the port is a SILENT dispatch failure, not an import
error: the module loads, the cron runs, the file is selected, and
``getattr`` raises ``AttributeError`` inside the extractor's own
``try/except``, which converts it into an ETL message nobody reads. Freezing
the seven keys — ``none`` plus the six business usages contributed by five
modules — is the assertion that catches a rename before it ships.

Note that one of the six MOVED during this port: ``workday_supplier`` and
its ``ondelete`` entry went from ``dto_account_workday`` to
``dto_purchase_workday`` (decision D-9), and the source comment records why
both had to go in the same commit — *"an uninstall of this module while it
still held the ondelete key would reset every live folder carrying that
usage to 'none', and folder id 7 is live configuration"*
(``dto_account_workday/models/sftp_folder.py:16-20``). That is precisely
the failure this case describes, reached by a different route.

EXPECTED v17 OUTCOME: PASS.
EXPECTED v19 OUTCOME: PASS. The keys are ``selection_add`` values and the
frozen set is version-neutral; what a port can break is a rename, which is
exactly what step 9 detects.
"""
from framework.registry import test_case
from tests.wf001.common import (FILE_ACTIVITY_SUMMARY, MARK,  # noqa: F401
                                PROCESS_CRON_DOMAIN, PROCESS_CRON_XMLID,
                                GET_CRON_XMLID, REQUISITION_USAGE,
                                USAGE_KEYS, WORKFLOW, WORKFLOW_NAME,
                                activities_on, cron_row, csv_bytes,
                                file_message, fx, make_folder, make_server,
                                make_sftp_file, process_file,
                                require_requisition_import, sweep_wf001,
                                trace)


@test_case(
    id="TEST-WF001-TC303",
    name="A folder with usage = 'none' leaves its files Pending forever",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="novobi_sftp_connection", priority="P2", kind="API", order=1303,
    description="A file on a usage='none' folder is excluded by the "
                "processing cron's own domain, so it stays Pending with no "
                "log entry and no activity — and if a human presses Process "
                "Now it goes straight to DONE having done nothing, which is "
                "the more dangerous half. Then sets the usage key and "
                "proves the file processes normally. Step 9 freezes the "
                "seven usage keys, which are interpolated into method names "
                "and whose rename would be a silent dispatch failure.",
    traceability=trace("DATAONE-TC303"))
def test_tc303(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-001 fixtures and open a fresh "
                  "namespace"):
        sweep_wf001(rpc)

    with ctx.step("Preconditions: novobi_sftp_connection and "
                  "dto_sale_workday are installed"):
        require_requisition_import(ctx)

    with ctx.step("Step 9 (taken first, because it is the durable half and "
                  "needs no fixture): THE FROZEN CONTRACT. The usage "
                  "Selection must offer exactly the seven keys — 'none' "
                  "plus the six business usages contributed by five "
                  "modules"):
        info = rpc.call("sftp.folder", "fields_get", ["usage"],
                        attributes=["selection", "required", "help"])
        keys = {k for k, _label in (info["usage"].get("selection") or [])}
        ctx.log(f"sftp.folder.usage selection on {ctx.env.key}: "
                f"{sorted(keys)!r}")
        ctx.log(f"the frozen set: {sorted(USAGE_KEYS)!r}")
        ctx.check("the usage keys are exactly the frozen set", USAGE_KEYS,
                  keys)
        ctx.check("and usage is required, so a folder cannot be saved "
                  "without one at all — 'none' is an explicit choice, not "
                  "an omission", True,
                  bool(info["usage"].get("required")))
        ctx.log("Each key is interpolated into a method name — "
                "SFTPExtractor.run does getattr(self, "
                "f'_run_extractor_{business_process}'). So a rename during "
                "the port is a SILENT dispatch failure: the module loads, "
                "the cron runs, the file is selected, and the AttributeError "
                "is swallowed by the extractor's own try/except into an ETL "
                "message nobody reads. One of the six already MOVED during "
                "this port — workday_supplier went from dto_account_workday "
                "to dto_purchase_workday (decision D-9) — and the source "
                "comment records that the key and its ondelete entry had to "
                "move in the SAME commit, because an uninstall holding a "
                "stale ondelete key resets every live folder carrying that "
                "usage to 'none'. That is this case's failure, reached by a "
                "different route.")

    with ctx.step("Steps 1-3: a GET folder FN with usage = 'none' and one "
                  "file on it. The file record appears and is Pending"):
        server_id = make_server(rpc, action="GET")
        fn = make_folder(rpc, server_id, usage="none", label="orphan")
        folder = rpc.read("sftp.folder", [fn],
                          ["path", "usage", "action", "regex"])[0]
        ctx.log(f"folder FN: {folder!r}")
        ctx.check("its usage is 'none'", "none", folder["usage"])
        ctx.check("and it is a GET folder", "GET", folder["action"])
        file_id = make_sftp_file(rpc, fn, fx(f"{MARK}_orphan.csv"),
                                 b"anything,at,all\n1,2,3\n")
        row = rpc.read("sftp.file", [file_id],
                       ["state", "process_date", "usage", "action"])[0]
        ctx.log(f"the orphan file: {row!r}")
        ctx.check("it is Pending", "pending", row["state"])
        ctx.check("its usage is related from the folder", "none",
                  row["usage"])

    with ctx.step("Step 4: THE PROCESSING CRON NEVER SELECTS IT. Asserted "
                  "against the cron's own domain rather than by running it "
                  "— cron_process_sftp_files searches EVERY pending GET "
                  "file on the database (convention rule 3)"):
        ctx.log(f"the cron's domain, mirrored from sftp_file.py:256-260: "
                f"{PROCESS_CRON_DOMAIN!r}")
        selected = rpc.search("sftp.file",
                              list(PROCESS_CRON_DOMAIN)
                              + [("id", "=", file_id)])
        ctx.check("the file is NOT in the cron's selection — the third "
                  "clause, usage != 'none', excludes it", [], selected)
        ctx.check("while a file on a KEYED folder would be selected — "
                  "proved by the same domain with the usage clause dropped",
                  [file_id],
                  rpc.search("sftp.file",
                             [("action", "=", "GET"),
                              ("state", "=", "pending"),
                              ("id", "=", file_id)]))
        cron = cron_row(rpc, PROCESS_CRON_XMLID)
        ctx.log(f"{PROCESS_CRON_XMLID}: {cron!r}")
        ctx.check_true(f"{PROCESS_CRON_XMLID} resolves", bool(cron),
                       actual_desc=repr(cron))
        if cron:
            ctx.check_true(
                "and it is NOT active on this QA target, which is why "
                "asserting the DOMAIN rather than the run is both safe and "
                "the only option", not cron.get("active"),
                actual_desc=repr(cron.get("active")))

    with ctx.step("Step 4b: so process_date stays empty — the file is "
                  "Pending with nothing having touched it"):
        row = rpc.read("sftp.file", [file_id],
                       ["state", "process_date"])[0]
        ctx.log(f"after the cron would have run twice: {row!r}")
        ctx.check("still Pending", "pending", row["state"])
        ctx.check("and process_date is still empty", False,
                  row["process_date"] or False)

    with ctx.step("Step 6: the situation is ENTIRELY SILENT — no sftp.log "
                  "record and no activity"):
        ctx.check("no activity on the file", [],
                  activities_on(rpc, "sftp.file", [file_id]))
        logs = rpc.search("sftp.log", [("res_model", "=", "sftp.file"),
                                       ("res_id", "=", file_id)]) \
            if rpc.model_exists("sftp.log") else []
        ctx.check("no sftp.log record either", [], logs)
        ctx.log("USABILITY FINDING, worth recording: nothing in the UI "
                "distinguishes 'Pending because the cron has not run yet' "
                "from 'Pending because this folder will never be "
                "processed'. A usage='none' warning on the folder form "
                "would cost nothing.")

    with ctx.step("THE MORE DANGEROUS HALF, and the workbook does not name "
                  "it: if a human presses Process Now on this file it goes "
                  "straight to DONE having done nothing"):
        done_row = process_file(ctx, file_id)
        ctx.log(f"after a manual Process Now on the usage='none' file: "
                f"{done_row!r}")
        ctx.check(
            "it reads DONE — _process_sftp_file returns (True, '') for "
            "usage == 'none' (sftp_file.py:203-207), so "
            "action_process_sftp_files calls mark_sync_success. An operator "
            "who presses the button sees a green Done and concludes the "
            "file was handled", "done", done_row["state"])
        ctx.check_true("with process_date stamped, which makes it look "
                       "processed in every list view",
                       bool(done_row["process_date"]),
                       actual_desc=repr(done_row["process_date"]))
        ctx.check("and still no activity and no log", [],
                  activities_on(rpc, "sftp.file", [file_id]))
        ctx.log("Recommended alongside the folder-form warning: have "
                "_process_sftp_file return (False, 'This folder has no "
                "usage key, so its files are never processed') for "
                "usage == 'none', so a manual attempt fails loudly instead "
                "of succeeding emptily.")

    with ctx.step("Steps 7-8: set the usage key and prove a file on the "
                  "same folder now processes normally"):
        rpc.write("sftp.folder", [fn], {"usage": REQUISITION_USAGE})
        after = rpc.read("sftp.folder", [fn], ["usage"])[0]
        ctx.log(f"FN after keying: {after!r}")
        ctx.check("the usage key is set", REQUISITION_USAGE, after["usage"])
        second = make_sftp_file(rpc, fn, fx(f"{MARK}_keyed.csv"),
                                b"Requisition_Num\n\n")
        ctx.check("a new file on the keyed folder IS in the cron's "
                  "selection", [second],
                  rpc.search("sftp.file",
                             list(PROCESS_CRON_DOMAIN)
                             + [("id", "=", second)]))
        keyed_row = process_file(ctx, second)
        ctx.log(f"the keyed file after processing: {keyed_row!r}")
        ctx.check_true(
            "and it reaches a real terminal state — Failed here, because "
            "the payload is a deliberately malformed one-column file, which "
            "is the point: the ETL RAN, where before it was never reached",
            keyed_row["state"] in ("done", "failed"),
            actual_desc=repr(keyed_row["state"]))
        ctx.log(f"its message: {file_message(rpc, second)!r}")
        if keyed_row["state"] == "failed":
            ctx.check("and it filed the superuser activity the usage='none' "
                      "file never got", 1,
                      len(activities_on(rpc, "sftp.file", [second])))

    with ctx.step("The GET poller, for completeness"):
        get_cron = cron_row(rpc, GET_CRON_XMLID)
        ctx.log(f"{GET_CRON_XMLID}: {get_cron!r}")
        ctx.log("Step 5's 'the remote source folder is nonetheless empty — "
                "the file was downloaded and archived regardless of usage' "
                "needs an endpoint: the download and the archive both "
                "happen in sftp.folder.action_get_files, before the usage "
                "key is consulted at all. Recorded rather than asserted "
                "(convention rule 4). It matters because it means the "
                "evidence is GONE from the remote side while nothing in "
                "Odoo has processed it.")
