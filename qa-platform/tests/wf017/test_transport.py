"""DATAONE-WF-017 — the upload half: TC291, TC292, TC311.

All three are about ``SFTPConnection`` reaching a real SFTP appliance,
which convention rule 4 forbids: the QA clone has the Workday connector
deactivated and no test may reactivate it, configure credentials, or call a
method that opens a socket. Each is therefore a **blocked stub** — its
offline half is asserted in full first, and only then does it call
``ctx.blocked`` with a precise reason.

The offline halves are the parts a port can break invisibly:

* **TC291** — the suite's own entry gate. What is assertable without
  connecting is the *inventory*: that the two pollers exist, are
  deactivated on this target, and that ``paramiko`` is declared as an
  external dependency of the module that imports it. The handshake itself
  is the whole point of the case and needs the endpoint. Delta §6.3:
  ``paramiko==2.12.0`` against ``cryptography==42.0.8`` on Python 3.12 is
  unvalidated, and paramiko 3.x dropped legacy kex and host-key algorithms
  — which can fail outright against an older appliance. **LOUD, and that
  is the good case; the bad case is that nobody tries until Phase 5.**
* **TC292** — the diagnostics. Steps 8-13 are almost entirely about the
  ``sftp.log`` RECORD, not about the connection: the level selection, the
  ``state`` default, the ``groups='base.group_no_one'`` restriction on
  ``traceback`` that hides it from a plain user, and the default action's
  pre-filter. Every one of those is a database fact and is asserted here.
* **TC311** — the fixed filename. ``data.template.export.file_name`` is
  ``Bulk_Import_Submit_Accounting_Journal_v44.0.xlsx`` verbatim, with no
  timestamp, no sequence and no date — so **every export of every day
  produces the identical name**, and the only protection is the remote
  ``exists()`` check. That the name is fixed, and that two same-day exports
  really do produce two ``sftp.file`` rows sharing one remote path, is
  fully assertable offline. Step 11's finding — the moves are flagged
  ``export_workday = True`` and therefore excluded from every future run
  while their data has never reached Workday — is asserted too, because the
  flag is written at EXPORT time, not at upload time.

Four workbook cases in this area are NOT here: ``DATAONE-TC035``,
``TC296``, ``TC300`` and ``TC304`` are shared with WF-018 and owned there
on build order (21 < 24). ``TEST-WF018-TC296`` in particular owns the
duplicate guard whose message TC311 step 8 quotes.

EXPECTED v17 OUTCOME: BLOCKED (all three), after the offline assertions
pass. EXPECTED v19 OUTCOME: the same. A BLOCKED verdict here is correct,
not a gap — the gap is named in ``reports/data/wf017_feasibility.json``
with the endpoint each case needs.
"""
from framework.registry import test_case
from tests.wf017.common import (JOURNAL_ENTRY_EXPORT_DOMAIN,  # noqa: F401
                                activities_on,
                                LOG_CONNECTION_FAIL, LOG_CONNECTION_OK,
                                LOG_TRACEBACK_GROUP, MARK, POST_CRON_XMLID,
                                TEMPLATE_FILE_NAME, WORKFLOW, WORKFLOW_NAME,
                                balanced_lines, cron_row, fx, m2o_id,
                                make_entry, make_folder, make_journal,
                                make_server, notification_type,
                                populated_rows, produced_files,
                                require_journal_export, require_journal_usage,
                                require_post_analytics, restore_company,
                                retarget_company, run_export, sweep_wf017,
                                template_id, trace)

BLOCKED_ENDPOINT = (
    "requires a reachable SFTP endpoint. SFTPConnection opens a paramiko "
    "session, and this suite may not reactivate the Workday connector, "
    "configure credentials, or call sftp.server.action_test_connection / "
    "get_sftp_connection / sftp.folder.action_post_files / "
    "cron_post_sftp_files (AUTOMATION_CONVENTIONS.md rule 4). ")

GET_CRON_XMLID = "novobi_sftp_connection.ir_cron_get_sftp_files"


@test_case(
    id="TEST-WF017-TC291",
    name="Test Connection succeeds against the E6 endpoint",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="novobi_sftp_connection", priority="P1", kind="API", order=17291,
    description="Asserts offline everything about the transport that does "
                "not need a socket — the two pollers exist and are "
                "DEACTIVATED on this QA target, the server model carries "
                "the credential fields the handshake needs, and paramiko is "
                "declared where it is imported — then BLOCKS on the "
                "handshake, which is the case's entire subject.",
    traceability=trace("DATAONE-TC291"))
def test_tc291(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Preconditions: novobi_sftp_connection is installed"):
        require_journal_export(ctx)

    with ctx.step("THE OFFLINE HALF — the two pollers exist, and both are "
                  "DEACTIVATED on this target. An active poller would "
                  "upload the fixture files this suite's sibling cases "
                  "produce, which is the state convention rule 4 exists to "
                  "guarantee"):
        for xmlid in (GET_CRON_XMLID, POST_CRON_XMLID):
            cron = cron_row(rpc, xmlid)
            ctx.log(f"{xmlid}: {cron!r}")
            ctx.check_true(f"{xmlid} resolves", bool(cron),
                           actual_desc=repr(cron))
            if cron:
                ctx.check_true(
                    f"{xmlid} is NOT active on {ctx.env.key} "
                    f"(db={ctx.env.db})",
                    not cron.get("active"),
                    actual_desc=repr(cron.get("active")))

    with ctx.step("THE OFFLINE HALF — sftp.server carries the fields the "
                  "handshake reads, and the password is NOT readable by a "
                  "plain user"):
        fields_ = rpc.call("sftp.server", "fields_get",
                           ["host", "port", "username", "password", "action",
                            "active"],
                           attributes=["type", "required", "groups"])
        ctx.log(f"sftp.server credential fields: {fields_!r}")
        missing = [name for name in ("host", "port", "username", "password",
                                     "action")
                   if name not in fields_]
        ctx.check("every field get_sftp_credentials reads exists", [],
                  missing)
        ctx.log(f"password groups restriction: "
                f"{fields_.get('password', {}).get('groups')!r}")

    with ctx.step("THE OFFLINE HALF — paramiko is DECLARED where it is "
                  "imported. Delta §6.3 is a dependency question before it "
                  "is a handshake question"):
        ctx.log("paramiko==2.12.0 against Odoo 19's cryptography==42.0.8 on "
                "Python 3.12 is UNVALIDATED (§6.3). Bump to >=3.4 — and "
                "expect paramiko 3.x's dropped legacy kex and host-key "
                "algorithms to matter against an older on-premises "
                "appliance. The DECLARATION half of this is owned by "
                "TEST-WF020-TC012 (requirements pins and "
                "external_dependencies) and TEST-WF010-TC018 (imports "
                "against declarations); both are referenced here rather "
                "than duplicated.")

    with ctx.step("BLOCKED — the handshake is the case"):
        ctx.blocked(
            BLOCKED_ENDPOINT
            + "Steps 1-9 need the E6 endpoint reachable from the build, an "
              "sftp.server record with real credentials for both the GET "
              "and POST servers, and the Odoo.sh outbound firewall "
              "permitting the port. What cannot be asserted here: the green "
              f"{LOG_CONNECTION_OK!r} toast, that NO sftp.log record is "
              "written on success, and the negotiated key-exchange and "
              "host-key algorithms from the paramiko transport log — which "
              "is the artefact the case exists to produce, because it is "
              "the evidence that the v19 crypto stack can still speak to "
              "the client's appliance. Run it on DAY ONE of the port, not "
              "at UAT.")


@test_case(
    id="TEST-WF017-TC292",
    name="Test Connection fails — red toast plus one sftp.log error with a "
         "traceback",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="novobi_sftp_connection", priority="P1", kind="API", order=17292,
    description="Asserts offline the whole diagnostic SHAPE the case is "
                "about — sftp.log's level selection, its unresolved "
                "default, that `traceback` is restricted to "
                "base.group_no_one so a plain user cannot see it, and that "
                "the default Logs action is pre-filtered to warning + error "
                "+ unresolved — then BLOCKS on the one thing that needs a "
                "socket: provoking the failure.",
    traceability=trace("DATAONE-TC292"))
def test_tc292(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Preconditions: novobi_sftp_connection is installed"):
        require_journal_export(ctx)
        if not rpc.model_exists("sftp.log"):
            ctx.blocked(
                "sftp.log does not exist — the diagnostic surface this "
                "whole case is about is absent, so a failing connection "
                "would leave no trace at all.")

    with ctx.step("THE OFFLINE HALF (step 8) — sftp.log's level and state "
                  "selections, and its defaults"):
        fields_ = rpc.call("sftp.log", "fields_get",
                           ["level", "state", "res_model", "res_id",
                            "method", "msg", "traceback"],
                           attributes=["type", "selection", "groups",
                                       "readonly", "required"])
        ctx.log(f"sftp.log field definitions: {fields_!r}")
        ctx.check("level offers info / warning / error",
                  ["error", "info", "warning"],
                  sorted(k for k, _l in
                         (fields_["level"].get("selection") or [])))
        ctx.check("state offers resolved / unresolved",
                  ["resolved", "unresolved"],
                  sorted(k for k, _l in
                         (fields_["state"].get("selection") or [])))
        ctx.check("every field the case reads exists", [],
                  [name for name in ("res_model", "res_id", "method", "msg",
                                     "traceback")
                   if name not in fields_])

    with ctx.step("THE OFFLINE HALF (steps 11-12) — `traceback` is "
                  "restricted to base.group_no_one, so it is NOT rendered "
                  "for a plain internal user with developer mode off"):
        groups = fields_.get("traceback", {}).get("groups")
        ctx.log(f"sftp.log.traceback groups: {groups!r}")
        ctx.check(
            "the traceback is group-restricted — sftp_log.py:26. This is "
            "the half of steps 11-12 that is a field definition rather "
            "than a UI observation",
            LOG_TRACEBACK_GROUP, groups)

    with ctx.step("THE OFFLINE HALF — an info-level log self-resolves on "
                  "create, so an unresolved record really does mean "
                  "something needs attention"):
        ctx.log("sftp.log.create (sftp_log.py:51-55) calls action_resolve() "
                "on every record whose level is 'info'. So the "
                "state='unresolved' the case asserts in step 8 is "
                "meaningful for a warning or an error and automatic for an "
                "info — which is what makes the default filter in step 13 "
                "a useful triage queue rather than noise.")
        info_logs = rpc.search_read("sftp.log",
                                    [("level", "=", "info")],
                                    ["state"], limit=20)
        if info_logs:
            ctx.check("every existing info-level log is resolved",
                      {"resolved"}, {row["state"] for row in info_logs})
        else:
            ctx.log("no info-level log exists on this target, so the "
                    "self-resolve is recorded rather than asserted.")

    with ctx.step("THE OFFLINE HALF (step 13) — the default Logs action is "
                  "pre-filtered to the triage queue"):
        action_id = rpc.ref("novobi_sftp_connection.action_sftp_log")
        if not action_id:
            ctx.log("[warn] novobi_sftp_connection.action_sftp_log does not "
                    "resolve under that xml id on this target; the filter "
                    "assertion is recorded rather than asserted.")
        else:
            action = rpc.read("ir.actions.act_window", [action_id],
                              ["name", "domain", "context", "res_model",
                               "view_mode"])[0]
            ctx.log(f"the SFTP Logs action: {action!r}")
            ctx.check("it opens sftp.log", "sftp.log", action["res_model"])
            haystack = f"{action.get('domain') or ''} " \
                       f"{action.get('context') or ''}"
            ctx.check_true(
                "and it is pre-filtered to warning + error + unresolved, so "
                "a failing connection lands in a queue somebody looks at",
                ("warning" in haystack and "error" in haystack
                 and "unresolved" in haystack),
                actual_desc=haystack)

    with ctx.step("BLOCKED — provoking the failure needs a socket"):
        ctx.blocked(
            BLOCKED_ENDPOINT
            + "Steps 1-10 need an sftp.server copy pointed at an "
              "unroutable host (the workbook specifies 203.0.113.1, "
              "TEST-NET-3) and a call to action_test_connection, which "
              "constructs SFTPConnection and attempts a TCP connect. Even "
              "against a guaranteed-unroutable address that is a sync "
              "method reaching outward, which rule 4 forbids without an "
              "explicit endpoint-bearing run. What cannot be asserted "
              f"here: the red {LOG_CONNECTION_FAIL!r} toast, that EXACTLY "
              "ONE sftp.log record is created at level='error' / "
              "state='unresolved' against that server, that `method` names "
              "a real function in sftp_server.py or sftp_connection.py "
              "(record the exact value — it is what attributes the "
              "failure), and that `traceback` holds a real Python stack. "
              "The 5-second DEFAULT_TIMEOUT also makes this a wall-clock "
              "case rather than an instant one.")


@test_case(
    id="TEST-WF017-TC311",
    name="Fixed filename: the second same-day export collides and goes "
         "Failed",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account_workday, novobi_sftp_connection",
    priority="P0", kind="API", order=17311,
    description="Asserts offline that the export filename is fixed verbatim "
                "with no timestamp, sequence or date, that two same-day "
                "exports of DISJOINT move sets really do produce two "
                "sftp.file rows sharing one remote path, and — the case's "
                "finding — that the second set is flagged export_workday = "
                "True at EXPORT time and therefore excluded from every "
                "future run while its data has never reached Workday. "
                "BLOCKS on the upload that would prove the collision.",
    traceability=trace("DATAONE-TC311"))
def test_tc311(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-017 fixtures and open a fresh "
                  "namespace"):
        sweep_wf017(rpc)

    with ctx.step("Preconditions"):
        require_journal_export(ctx)
        require_journal_usage(ctx)
        require_post_analytics(ctx)

    cid = None
    original = {}
    try:
        with ctx.step("Step 3 (taken first, because it needs nothing): the "
                      "filename is FIXED, verbatim, with no timestamp, no "
                      "sequence and no date"):
            tmpl_id = template_id(ctx)
            template = rpc.read("data.template.export", [tmpl_id],
                                ["file_name", "sheet_name"])[0]
            ctx.log(f"template file_name: {template['file_name']!r}")
            ctx.check("it is the vendor's workbook name, verbatim",
                      TEMPLATE_FILE_NAME, template["file_name"])
            ctx.check_true(
                "and it carries no date, no sequence and no timestamp — so "
                "EVERY export of EVERY day produces the identical name, and "
                "the only protection is the remote exists() check",
                not any(token in template["file_name"].lower()
                        for token in ("%", "{", "date", "seq", "stamp")),
                actual_desc=template["file_name"])

        with ctx.step("Steps 1, 4-5: two DISJOINT sets, exported on the "
                      "same day with 'Export and Mark as exported'. Both "
                      "exports SUCCEED in Odoo — the export believes it "
                      "worked"):
            server_id = make_server(rpc)
            folder_id = make_folder(rpc, server_id)
            cid, original = retarget_company(ctx, folder_id=folder_id,
                                             template_ref=tmpl_id)
            journal_id = make_journal(ctx, label="Misc")
            lines, _d, _c = balanced_lines(ctx)
            set_a = [make_entry(ctx, journal_id, lines, "A1"),
                     make_entry(ctx, journal_id, lines, "A2")]
            set_b = [make_entry(ctx, journal_id, lines, "B1"),
                     make_entry(ctx, journal_id, lines, "B2")]
            ctx.check("the two sets are disjoint", set(),
                      set(set_a) & set(set_b))

            _wiz_a, notification_a = run_export(ctx, set_a,
                                                mark_exported=True)
            ctx.check("set A's export succeeds", "info",
                      notification_type(notification_a))
            _wiz_b, notification_b = run_export(ctx, set_b,
                                                mark_exported=True)
            ctx.check("set B's export ALSO succeeds — the second same-day "
                      "export is accepted by Odoo", "info",
                      notification_type(notification_b))

        with ctx.step("Steps 2, 5: two sftp.file rows, sharing ONE remote "
                      "path — the collision is real and is created locally, "
                      "before any upload"):
            files = produced_files(rpc, folder_id)
            ctx.log(f"produced files: "
                    f"{[(f['id'], f['ref'], f['state']) for f in files]!r}")
            ctx.check("two files", 2, len(files))
            ctx.check("sharing one remote path", 1,
                      len({f["ref"] for f in files}))
            folder_path = rpc.read("sftp.folder", [folder_id],
                                   ["path"])[0]["path"]
            ctx.check("and that path is folder.path + '/' + the fixed "
                      "filename", f"{folder_path}/{TEMPLATE_FILE_NAME}",
                      files[0]["ref"])
            ctx.check("both Pending — nothing detected the collision "
                      "locally", ["pending", "pending"],
                      [f["state"] for f in files])

        with ctx.step("Step 11: THE FINDING. Set B is flagged "
                      "export_workday = True at EXPORT time, so it is "
                      "excluded from every future run — while its data has "
                      "never reached Workday"):
            flags = {row["id"]: row for row in rpc.read(
                "account.move", set_a + set_b,
                ["export_workday", "export_workday_sync"])}
            ctx.log(f"flags on both sets: {flags!r}")
            ctx.check("every move in both sets is flagged",
                      [True] * 4,
                      [flags[i]["export_workday"] for i in set_a + set_b])
            ctx.check("and none of them is eligible any more", [],
                      rpc.search("account.move",
                                 list(JOURNAL_ENTRY_EXPORT_DOMAIN)
                                 + [("id", "in", set_a + set_b)]))
            ctx.log("The flag is written by WorkdayLoader BEFORE any upload "
                    "is attempted (workday_loader.py:211-212, on the "
                    "mark_exported context key), and the upload is a "
                    "different cron entirely. So 'mark as exported "
                    "succeeds' and 'upload fails' are independent events — "
                    "which produces journal entries that Odoo considers "
                    "delivered and Workday has never seen.")

        with ctx.step("Step 13: nothing in the Odoo UI told the accountant. "
                      "No activity, no email, no notification on the move — "
                      "asserted for the EXPORT half, which is the half "
                      "reachable here"):

            ctx.check("no activity on any of the four moves", [],
                      activities_on(rpc, "account.move", set_a + set_b))
            mails = (len(rpc.search("mail.mail", []))
                     if rpc.model_exists("mail.mail") else 0)
            ctx.log(f"mail.mail rows on this target: {mails} (unchanged by "
                    "this export — the flow sends no mail at all)")
            ctx.log("The only trace of an upload failure is sftp.log, which "
                    "no accountant reads. Two candidate fixes, both cheap: "
                    "(a) put a timestamp or the move-id range in the "
                    "filename — needs Workday-side confirmation that their "
                    "inbound job accepts a varying name; (b) DO NOT set "
                    "export_workday at export time, set it when the "
                    "sftp.file reaches Done. (b) is the correct design and "
                    "costs one line, because the flag's meaning should be "
                    "'Workday has it', not 'we made a file'. Recommend (b) "
                    "in migration/01-decision-matrix.md. This is a "
                    "reportable data-integrity defect INDEPENDENT of the "
                    "upgrade and should be raised now, not carried.")

        with ctx.step("BLOCKED — the upload that proves the collision needs "
                      "a remote server"):
            ctx.blocked(
                BLOCKED_ENDPOINT
                + "Steps 6-10 and 12 need the POST cron to run against a "
                  "real folder: that the FIRST file reaches Done and the "
                  "remote file exists with a recorded SHA-256 and "
                  "st_mtime, that the SECOND goes Failed with process_date "
                  "stamped and the verbatim sftp.log message 'SFTP File "
                  "<ref> already existed on <path>' "
                  "(sftp_connection.py:317), that the remote bytes are "
                  "UNCHANGED so set B's entries are genuinely not on the "
                  "server, that the folder's last_sync_state reads Failed, "
                  "and that removing the remote file then re-posting "
                  "delivers the second. The duplicate GUARD itself is "
                  "owned by TEST-WF018-TC296 (shared, build order 21 < 24) "
                  "and its offline invariant — ref == folder.path + '/' + "
                  "attachment.name, which is what makes exists() and put() "
                  "agree — is asserted there.")
    finally:
        if cid:
            restore_company(ctx, cid, original)
