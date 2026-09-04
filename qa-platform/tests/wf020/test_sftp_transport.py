"""DATAONE-WF-020 — the SFTP transport layer: TC297, TC298, TC301, TC302.

All four run with no endpoint. The fixture server is created inactive with
an unroutable host and is never connected to; nothing here calls
``get_sftp_connection``, ``action_test_connection`` or any ``cron_*``.

TC302 is the workflow's live-defect case and the most valuable test in this
file. On v17 ``sftp_folder.action_get_files`` ran::

    regex = self.regex and re.match(self.regex) or None

``re.match`` takes ``(pattern, string)`` — calling it with one argument
raised ``TypeError`` before the connection was ever used, aborting the
whole GET poll for that server and recording nothing anywhere.

**THE PORT HAS LANDED, so this case asserts the post-fix outcome.** The
workbook states that outcome as a REQUIRED result, not an observation:
"the port must either (a) implement the filter correctly,
re.match(self.regex, filename) applied per filename inside get_files, with
an @api.constrains validating that the pattern compiles; or (b) remove the
regex field entirely". novobi_sftp_connection took option (a) —
``action_get_files`` compiles the pattern once and hands it to
``connection.get_files(folder=..., regex=...)`` (models/sftp_folder.py:125),
and ``_check_regex`` (:95) refuses an uncompilable pattern at save time.
Steps 1-4 assert (a). The blast-radius and nothing-was-recorded steps are
unchanged and still hold: a folder with a VALID regex must now reach the
connection exactly as an empty-regex folder does.

EXPECTED v17 OUTCOME: FAIL — v17 has neither the compile fix nor the
constraint, so step 1 stores the invalid pattern instead of refusing it and
step 3 dies on ``re.match``. Convention rule 2: the expectation describes
the v19 target state and is not inverted to make v17 green.
EXPECTED v19 OUTCOME: PASS.
EXPECTED v19 OUTCOME: TC297 is the one to watch — ``_check_unique_folder``
uses ``_read_group(..., having=[('__count','>',1)])``; if the aggregate
return shape changed, the constraint silently stops matching and permits
everything.
"""
import xml.etree.ElementTree as ET

from framework.registry import test_case
from tests.wf020.common import (MARK, SUPPLIER_USAGE, WORKFLOW,  # noqa: F401
                                WORKFLOW_NAME, expect_error, fx, m2o_id,
                                make_folder, make_server, make_sftp_file,
                                require_sftp_stack, sweep_wf020, trace)

FOLDER_UNIQUE_MESSAGE = ("(Folder Path, Action, Usage Key, Regex) must be "
                         "unique per Connection")
ONLY_PENDING = "Only pending file(s) can be processed!"


def _button(arch: str, name: str):
    root = ET.fromstring(arch)
    for node in root.iter("button"):
        if node.get("name") == name:
            return node
    return None


@test_case(
    id="TEST-WF020-TC297",
    name="Folder uniqueness constraint, including archived folders",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="novobi_sftp_connection", priority="P2", kind="API", order=20297,
    description="(path, usage, action, regex) is unique per connection; "
                "changing only the usage key makes the tuple free; the "
                "constraint runs with active_test=False so an ARCHIVED "
                "folder still blocks a duplicate; another server is "
                "unaffected; un-archiving raises nothing.",
    traceability=trace("DATAONE-TC297"))
def test_tc297(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-020 fixtures and open a fresh "
                  "namespace"):
        sweep_wf020(rpc)

    with ctx.step("Precondition: the transport is installed"):
        require_sftp_stack(ctx)

    try:
        with ctx.step("Create server S1 with folder F1 (path P, usage none, "
                      "action GET, regex empty)"):
            server_a = make_server(rpc, label="S1")
            path = fx(f"/{MARK}/unique")
            f1 = make_folder(rpc, server_a, path=path, usage="none")
            ctx.check_true("F1 created", bool(f1), actual_desc=str(f1))

        with ctx.step("Steps 1-2: an identical folder on the same server is "
                      "refused with the exact message"):
            raised, message = expect_error(
                rpc.create, "sftp.folder",
                {"server_id": server_a, "path": path, "usage": "none",
                 "regex": False})
            ctx.log(f"raised: {message!r}")
            ctx.check_true("the duplicate was refused", raised,
                           actual_desc=message)
            ctx.check_true(f"message is {FOLDER_UNIQUE_MESSAGE!r}",
                           FOLDER_UNIQUE_MESSAGE in message,
                           actual_desc=message)

        with ctx.step("Step 3: the same path with a DIFFERENT usage key "
                      "saves — the tuple is the key, not the path alone"):
            selection = rpc.call("sftp.folder", "fields_get", ["usage"],
                                 attributes=["selection"])["usage"]["selection"]
            other = next((k for k, _label in selection if k != "none"), None)
            if other is None:
                ctx.blocked(
                    "sftp.folder.usage offers only 'none' on this target, so "
                    "the 'same path, different usage key' half of the tuple "
                    "cannot be exercised. Install dto_account_workday (which "
                    "contributes workday_supplier and three siblings) first.")
            ctx.log(f"second usage key: {other}")
            f2 = make_folder(rpc, server_a, path=path, usage=other)
            ctx.check_true("a folder differing only in usage saved",
                           bool(f2), actual_desc=str(f2))

        with ctx.step("Steps 4-6: delete F2, ARCHIVE F1, and assert a "
                      "duplicate is still refused — the constraint counts "
                      "archived folders"):
            rpc.call("sftp.folder", "unlink", [f2])
            rpc.write("sftp.folder", [f1], {"active": False})
            archived = rpc.read("sftp.folder", [f1], ["active"])[0]
            ctx.check("F1 is archived", False, archived["active"])
            raised, message = expect_error(
                rpc.create, "sftp.folder",
                {"server_id": server_a, "path": path, "usage": "none",
                 "regex": False})
            ctx.check_true("a duplicate of an ARCHIVED folder was refused",
                           raised, actual_desc=message)
            ctx.check_true(f"message is still {FOLDER_UNIQUE_MESSAGE!r}",
                           FOLDER_UNIQUE_MESSAGE in message,
                           actual_desc=message)

        with ctx.step("Step 7: the identical folder on a DIFFERENT server "
                      "saves — the constraint is per connection"):
            server_b = make_server(rpc, label="S2")
            f3 = make_folder(rpc, server_b, path=path, usage="none")
            ctx.check_true("the same tuple on another server saved",
                           bool(f3), actual_desc=str(f3))

        with ctx.step("Step 8: un-archiving F1 raises nothing, and the "
                      "step-7 folder still coexists"):
            rpc.write("sftp.folder", [f1], {"active": True})
            live = rpc.read("sftp.folder", [f1, f3], ["active", "path"])
            ctx.check("both folders are active",
                      [True, True], [r["active"] for r in live])
    finally:
        with ctx.step("Cleanup WF-020 fixtures"):
            try:
                sweep_wf020(rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")


@test_case(
    id="TEST-WF020-TC298",
    name="Process Now visibility and Only pending file(s) can be processed!",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="novobi_sftp_connection", priority="P2", kind="API", order=20298,
    description="Process Now / Re-process / Re-post appear only in their "
                "intended (state, action) combinations; a mixed selection "
                "is refused whole with the exact message leaving nothing "
                "partially processed; a pending file alone processes and "
                "stamps process_date.",
    traceability=trace("DATAONE-TC298"))
def test_tc298(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-020 fixtures and open a fresh "
                  "namespace"):
        sweep_wf020(rpc)

    with ctx.step("Precondition: the transport is installed"):
        require_sftp_stack(ctx)

    try:
        with ctx.step("Build three files on a usage='none' GET folder — "
                      "P1 Pending, D1 Done, F1 Failed. usage 'none' makes "
                      "processing a no-op (_process_sftp_file returns "
                      "(True, '')), so step 7 runs no ETL and touches no "
                      "business data"):
            server_id = make_server(rpc, label="Buttons")
            folder_id = make_folder(rpc, server_id, usage="none")
            p1 = make_sftp_file(rpc, folder_id, fx(f"{MARK}_p1.csv"), b"x\n")
            d1 = make_sftp_file(rpc, folder_id, fx(f"{MARK}_d1.csv"), b"x\n")
            f1 = make_sftp_file(rpc, folder_id, fx(f"{MARK}_f1.csv"), b"x\n")
            rpc.write("sftp.file", [d1], {"state": "done"})
            rpc.write("sftp.file", [f1], {"state": "failed"})
            states = {r["id"]: r["state"] for r in
                      rpc.read("sftp.file", [p1, d1, f1], ["state"])}
            ctx.check("fixture states",
                      {p1: "pending", d1: "done", f1: "failed"}, states)

        with ctx.step("Steps 1-3: the three header buttons carry the "
                      "(state, action) modifiers that define their "
                      "visibility"):
            arch = rpc.call("sftp.file", "get_view", view_type="form")["arch"]
            modifiers = {}
            for name in ("action_process_sftp_files",
                         "action_retry_process_sftp_files",
                         "action_repost"):
                node = _button(arch, name)
                ctx.check_true(f"{name} button present in the form arch",
                               node is not None,
                               actual_desc=("present" if node is not None
                                            else "ABSENT — the form did not "
                                                 "render its header"))
                modifiers[name] = node.get("invisible")
            ctx.log(f"button modifiers: {modifiers!r}")
            ctx.check("button visibility rules", {
                "action_process_sftp_files":
                    "state != 'pending' or action != 'GET'",
                "action_retry_process_sftp_files":
                    "state != 'failed' or action != 'GET'",
                "action_repost":
                    "state != 'failed' or action != 'POST'"},
                modifiers)

        with ctx.step("Steps 4-5: Process Now over a MIXED selection "
                      "(pending + done) is refused with the exact message"):
            raised, message = expect_error(
                rpc.call, "sftp.file", "action_process_sftp_files", [p1, d1])
            ctx.log(f"raised: {message!r}")
            ctx.check_true("the mixed selection was refused", raised,
                           actual_desc=message)
            ctx.check_true(f"message is {ONLY_PENDING!r}",
                           ONLY_PENDING in message, actual_desc=message)

        with ctx.step("Step 6: nothing ran — P1 is still Pending with an "
                      "empty process_date"):
            row = rpc.read("sftp.file", [p1], ["state", "process_date"])[0]
            ctx.check("P1 state after the refused batch", "pending",
                      row["state"])
            ctx.check("P1 process_date after the refused batch", False,
                      row["process_date"])

        with ctx.step("Steps 7-8: P1 alone processes and reaches Done with "
                      "process_date stamped"):
            rpc.call("sftp.file", "action_process_sftp_files", [p1])
            row = rpc.read("sftp.file", [p1], ["state", "process_date"])[0]
            ctx.check("P1 state after processing alone", "done",
                      row["state"])
            ctx.check_true("P1 process_date stamped",
                           bool(row["process_date"]),
                           actual_desc=repr(row["process_date"]))

        with ctx.step("Step 9: the same message is raised for a FAILED file "
                      "invoked through Process Now"):
            raised, message = expect_error(
                rpc.call, "sftp.file", "action_process_sftp_files", [f1])
            ctx.check_true("Process Now on a failed file was refused",
                           raised, actual_desc=message)
            ctx.check_true(f"message is {ONLY_PENDING!r}",
                           ONLY_PENDING in message, actual_desc=message)
    finally:
        with ctx.step("Cleanup WF-020 fixtures"):
            try:
                sweep_wf020(rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")


@test_case(
    id="TEST-WF020-TC301",
    name="sftp.log capture — level, method, traceback, resolve / unresolve",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="novobi_sftp_connection", priority="P2", kind="API", order=20301,
    description="The log action's default filter is warning + error + "
                "unresolved; level and state are read-only in the form; the "
                "two bound server actions flip state both ways and are "
                "bound to the list view; an info record is auto-resolved on "
                "create; traceback is developer-only.",
    traceability=trace("DATAONE-TC301"))
def test_tc301(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-020 fixtures and open a fresh "
                  "namespace"):
        sweep_wf020(rpc)

    with ctx.step("Precondition: the transport is installed"):
        require_sftp_stack(ctx)

    created = []
    try:
        with ctx.step("Step 3: the SFTP Logs action defaults to "
                      "warning + error + unresolved"):
            action_id = rpc.ref("novobi_sftp_connection.action_sftp_log")
            ctx.check_true("the SFTP Logs action exists", bool(action_id),
                           actual_desc=str(action_id))
            action = rpc.read("ir.actions.act_window", [action_id],
                              ["context", "res_model", "view_mode"])[0]
            ctx.log(f"action: {action!r}")
            for key in ("search_default_warning", "search_default_error",
                        "search_default_unresolved"):
                ctx.check_true(f"context sets {key}",
                               key in (action["context"] or ""),
                               actual_desc=action["context"])

        with ctx.step("Step 4: build two error records attributed to the "
                      "fixture server, with a method and a message"):
            server_id = make_server(rpc, label="Logs")
            for method, msg in (("get_sftp_connection",
                                 fx(f"{MARK} connection refused")),
                                ("action_post_files",
                                 fx(f"{MARK} remote file exists"))):
                # `traceback` is deliberately NOT written here.
                # sftp_log.py:26 declares it groups="base.group_no_one",
                # and that group is effective in DEBUG SESSIONS ONLY on
                # both versions (v17 odoo/models.py:1577-1581, v19
                # base/models/res_users.py:1081-1083). An ordinary RPC
                # session therefore fails the field-level check with
                # "allowed for groups 'Technical Features'" and the
                # whole create is refused. Step 11 below asserts the
                # field IS developer-only, which is the workbook's
                # point; none of the row-shape assertions read it.
                created.append(rpc.create("sftp.log", {
                    "level": "error", "res_model": "sftp.server",
                    "res_id": server_id, "method": method,
                    "msg": msg}))
            rows = rpc.read("sftp.log", created,
                            ["level", "state", "res_model", "res_id",
                             "method", "msg"])
            ctx.log(f"log rows: {rows!r}")
            mismatches = {r["id"]: r for r in rows
                          if not (r["level"] == "error"
                                  and r["state"] == "unresolved"
                                  and r["res_model"] == "sftp.server"
                                  and r["res_id"] == server_id
                                  and r["method"] and r["msg"])}
            ctx.check("log rows not matching the expected shape", {},
                      mismatches)

        with ctx.step("Step 5: level and state are read-only in the form — "
                      "they are set by code and by the two server actions "
                      "only"):
            info = rpc.call("sftp.log", "fields_get", ["level", "state"],
                            attributes=["readonly"])
            ctx.check("readonly flags",
                      {"level": True, "state": True},
                      {k: info[k]["readonly"] for k in ("level", "state")})

        with ctx.step("Steps 6-7: the Resolve action flips both records to "
                      "resolved"):
            rpc.call("sftp.log", "action_resolve", created)
            states = [r["state"] for r in
                      rpc.read("sftp.log", created, ["state"])]
            ctx.check("states after Resolve", ["resolved", "resolved"],
                      states)
            still_default = rpc.search("sftp.log",
                                       [("id", "in", created),
                                        ("state", "=", "unresolved")])
            ctx.check("records still matching the default filter", [],
                      still_default)

        with ctx.step("Step 8: Unresolve returns both to unresolved"):
            rpc.call("sftp.log", "action_unresolve", created)
            states = [r["state"] for r in
                      rpc.read("sftp.log", created, ["state"])]
            ctx.check("states after Unresolve",
                      ["unresolved", "unresolved"], states)

        with ctx.step("Both bulk actions are bound to sftp.log's LIST view "
                      "— the v19 watch item, because an un-updated binding "
                      "makes them vanish from the cog menu with no error"):
            for xmlid in ("novobi_sftp_connection.action_resolve_multi",
                          "novobi_sftp_connection.action_unresolve_multi"):
                act_id = rpc.ref(xmlid)
                ctx.check_true(f"{xmlid} exists", bool(act_id),
                               actual_desc=str(act_id))
                act = rpc.read("ir.actions.server", [act_id],
                               ["binding_model_id", "binding_view_types"])[0]
                ctx.log(f"{xmlid}: {act!r}")
                ctx.check_true(
                    f"{xmlid} is bound to the list view",
                    "list" in (act["binding_view_types"] or ""),
                    actual_desc=repr(act["binding_view_types"]))

        with ctx.step("Steps 9-10: a record created at level 'info' is "
                      "auto-resolved on create"):
            info_id = rpc.create("sftp.log", {
                "level": "info", "res_model": "sftp.server",
                "res_id": server_id, "method": "cron_get_sftp_files",
                "msg": fx(f"{MARK} informational")})
            created.append(info_id)
            ctx.check("info record state on create", "resolved",
                      rpc.read("sftp.log", [info_id], ["state"])[0]["state"])

        with ctx.step("Step 11: traceback is developer-only "
                      "(groups='base.group_no_one')"):
            tb = rpc.call("sftp.log", "fields_get", ["traceback"],
                          attributes=["groups", "type"])
            ctx.log(f"traceback field: {tb!r}")
            ctx.check("traceback groups", "base.group_no_one",
                      tb["traceback"].get("groups"))
    finally:
        with ctx.step("Cleanup WF-020 fixtures"):
            try:
                if created:
                    rpc.call("sftp.log", "unlink", created)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] log records not removed: {exc}")
            try:
                sweep_wf020(rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")


@test_case(
    id="TEST-WF020-TC302",
    name="LIVE DEFECT: a folder with a non-empty regex raises TypeError; "
         "the filter is unusable",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="novobi_sftp_connection", priority="P0", kind="API", order=20302,
    description="v17 called re.match(self.regex) with one argument, so any "
                "non-empty regex raised TypeError before the connection was "
                "touched and aborted the whole GET poll. The workbook "
                "requires the port to compile the pattern and validate it "
                "with @api.constrains: an uncompilable regex is refused at "
                "save time, and a valid one reaches the connection exactly "
                "as an empty one does.",
    traceability=trace("DATAONE-TC302"))
def test_tc302(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-020 fixtures and open a fresh "
                  "namespace"):
        sweep_wf020(rpc)

    with ctx.step("Precondition: the transport is installed"):
        require_sftp_stack(ctx)

    try:
        with ctx.step("Step 1 (required outcome (a)): a syntactically "
                      "INVALID regex is refused at save time by "
                      "@api.constrains, naming the folder and the compile "
                      "error"):
            info = rpc.call("sftp.folder", "fields_get", ["regex"],
                            attributes=["help", "string", "type"])
            ctx.log(f"regex field: {info!r}")
            server_id = make_server(rpc, label="Regex")
            raised_bad, message_bad = expect_error(
                make_folder, rpc, server_id, usage="none",
                regex="[unclosed", label="bad")
            ctx.log(f"invalid regex save: {message_bad!r}")
            ctx.check_true(
                "the invalid pattern was refused rather than stored",
                raised_bad, actual_desc=message_bad)
            ctx.check_true(
                "the message names the field and the compile error",
                "not a valid regular expression" in message_bad,
                actual_desc=message_bad)
            ctx.check("invalid-regex folders stored", 0,
                      rpc.call("sftp.folder", "search_count",
                               [("server_id", "=", server_id),
                                ("regex", "=", "[unclosed"),
                                ("active", "in", [True, False])]))

        with ctx.step("Build FA (regex empty) and FB (regex set) on the "
                      "same server"):
            fa = make_folder(rpc, server_id, usage="none", regex=False,
                             label="fa")
            fb = make_folder(rpc, server_id, usage="none",
                             regex=r"^suppliers_.*\.csv$", label="fb")
            ctx.check("FB carries the regex", r"^suppliers_.*\.csv$",
                      rpc.read("sftp.folder", [fb], ["regex"])[0]["regex"])

        with ctx.step("Steps 2-4 (required outcome (a)): driving FB's GET "
                      "no longer dies on re.match's arity — the pattern is "
                      "compiled and handed to get_files, so the call "
                      "reaches the connection. No endpoint is contacted: "
                      "the dummy connection is what fails"):
            raised_fb, message_fb = expect_error(
                rpc.call, "sftp.folder", "action_get_files", [fb], False)
            ctx.log(f"FB raised: {message_fb!r}")
            ctx.check_true("FB's GET still failed — there is no real "
                           "connection to give it", raised_fb,
                           actual_desc=message_fb)
            ctx.check_true(
                "FB did NOT fail on re.match's arity — the v17 TypeError "
                "is gone",
                not ("match()" in message_fb
                     and "missing 1 required positional argument"
                     in message_fb),
                actual_desc=message_fb)

        with ctx.step("Step 8 (the control): FA with an EMPTY regex "
                      "behaves identically — it too fails on the dummy "
                      "connection, not on the regex branch. The same "
                      "failure point with and without a pattern is what "
                      "proves the filter is applied inside get_files "
                      "rather than exploding before it"):
            raised_fa, message_fa = expect_error(
                rpc.call, "sftp.folder", "action_get_files", [fa], False)
            ctx.log(f"FA raised: {message_fa!r}")
            ctx.check_true("FA's GET also failed (no real connection given)",
                           raised_fa, actual_desc=message_fa)
            ctx.check_true(
                "FA did NOT fail on re.match — it reached the connection",
                "match()" not in message_fa,
                actual_desc=message_fa)

        with ctx.step("Steps 5-6: the TypeError is not caught into an "
                      "sftp.log record, and FB's last_sync_state was not "
                      "set to Failed — nothing recorded the failure"):
            logs = rpc.search_read(
                "sftp.log",
                [("res_model", "=", "sftp.folder"), ("res_id", "=", fb)],
                ["level", "method", "msg"])
            ctx.check("sftp.log rows written for FB", [], logs)
            folder = rpc.read("sftp.folder", [fb],
                              ["last_sync_state", "last_sync_success"])[0]
            ctx.log(f"FB folder state: {folder!r}")
            ctx.check("FB last_sync_state after the uncaught raise", False,
                      folder["last_sync_state"])

        with ctx.step("Step 7 (blast radius): no sftp.file exists for "
                      "either folder — the uncaught raise means nothing was "
                      "downloaded"):
            files = rpc.search("sftp.file",
                               [("folder_id", "in", [fa, fb]),
                                ("active", "in", [True, False])])
            ctx.check("sftp.file records created", [], files)

        with ctx.step("Step 8: clearing FB's regex changes nothing — it "
                      "already fails at the same later point FA does"):
            rpc.write("sftp.folder", [fb], {"regex": False})
            _raised, message_cleared = expect_error(
                rpc.call, "sftp.folder", "action_get_files", [fb], False)
            ctx.log(f"FB after clearing the regex: {message_cleared!r}")
            ctx.check_true(
                "with the regex cleared, FB no longer fails on re.match",
                "match()" not in message_cleared,
                actual_desc=message_cleared)

        with ctx.step("Step 9 (v19 relevance): record whether this target "
                      "auto-deactivates a repeatedly failing cron"):
            fields = rpc.call("ir.cron", "fields_get",
                              ["failure_count", "first_failure_date",
                               "deactivate"], attributes=["type"])
            present = sorted(fields)
            ctx.log(f"v19 cron failure fields present here: {present}")
            ctx.log("On v19 these exist and the poller is switched OFF "
                    "permanently after repeated failures, turning this "
                    "LOUD v17 defect into a SILENT v19 outage. Asserted in "
                    "TEST-WF020-TC460.")
    finally:
        with ctx.step("Cleanup WF-020 fixtures"):
            try:
                sweep_wf020(rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")
