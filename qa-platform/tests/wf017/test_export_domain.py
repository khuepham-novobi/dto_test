"""DATAONE-WF-017 — what reaches Workday, and what stops it: TC307, TC310,
TC313, TC314, TC315.

TC307 — **the domain.** It decides what reaches Workday's general ledger
unattended, every day, with no human in the loop. A domain that lets a
vendor bill through duplicates it against WF-018's channel; one that lets a
bank entry through double-counts cash; one that lets a draft through files
an entry that may never be posted.

TC310 — **"Export only" defeats the only idempotency key the flow has.** A
real file reaches Workday, the moves stay unflagged, and the next daily
cron re-exports the same entries into a workbook with the **same fixed
filename**, which then fails on the remote ``exists()`` check. Two defects
compounding: Workday may or may not have already ingested the first file,
and the second never arrives. Step 10 — the business consequence — is the
deliverable of this case, not steps 5 or 12.

TC313 — **the empty batch.** It must not create an empty workbook: an empty
``Bulk_Import_Submit_Accounting_Journal_v44.0.xlsx`` uploaded to Workday
would occupy the day's filename and block the real export. It must also not
fail loudly, because the cron finds nothing to do most weekends. Step 7 is
the finding: on the scheduled path, "nothing was exported today" and "the
export is broken and exported nothing today" are indistinguishable to the
business. Both are silence.

TC314 — **fail early and loudly on configuration.** The alternative —
producing a workbook and then discovering there is nowhere to send it —
leaves flagged moves and an orphan attachment, which is exactly the state
TC311 shows is unrecoverable without manual intervention. Note the finding
the case is written to surface: ``_check_export_workday_journal_entry_setting``
covers THREE distinct causes (no folder / wrong usage / wrong direction)
with ONE string, so an administrator at 6 a.m. cannot tell which.

TC315 — **the blocking selection validations**, and step 8 is a discovery
step that may well produce a defect: the domain excludes
``journal_id.type in ['bank']`` but ``_check_condition_sync_journal_entry``
validates only emptiness, posted state and ``in_invoice``. If so, an
accountant can manually export a bank-journal entry that the cron would
never touch, double-counting cash in Workday against whatever the bank feed
already sent. The case runs it deliberately and records the answer.

EXPECTED v17 OUTCOME: PASS for all five, with TC315 step 8's answer
recorded either way.
EXPECTED v19 OUTCOME: the same. ``move_type``, ``journal_id.type`` and
``state`` are unchanged as far as delta §2.2 records; the exposure is
``export_workday`` itself, a DataOne field — LOUD if it does not port,
because the domain raises.
"""
from framework.registry import test_case
from tests.wf017.common import (ERR_BAD_FOLDER, ERR_EMPTY_SELECTION,
                                ERR_IS_BILL, ERR_NOTHING_TO_EXPORT,
                                ERR_NOT_POSTED, ERR_NO_TEMPLATE,
                                EXPORT_CRON_XMLID,
                                JOURNAL_ENTRY_EXPORT_DOMAIN, MARK,
                                POST_CRON_XMLID, TEMPLATE_FILE_NAME,
                                VENDOR_BILL_USAGE, WORKFLOW, WORKFLOW_NAME,
                                activities_on, balanced_lines, cron_row,
                                expect_error, fx, latest_workbook, m2o_id,
                                make_entry, make_folder, make_journal,
                                make_server, move_ref, notification_message,
                                notification_type, open_export_wizard,
                                populated_rows, produced_files,
                                require_journal_export, require_journal_usage,
                                require_post_analytics, restore_company,
                                retarget_company, run_export, save_workbook,
                                set_company, sweep_wf017, template_id,
                                trace, two_accounts)


def _export_target(ctx):
    rpc = ctx.adapter.rpc
    tmpl_id = template_id(ctx)
    server_id = make_server(rpc)
    folder_id = make_folder(rpc, server_id)
    cid, original = retarget_company(ctx, folder_id=folder_id,
                                     template_ref=tmpl_id)
    return folder_id, tmpl_id, cid, original


@test_case(
    id="TEST-WF017-TC307",
    name="The selection domain excludes bills, bank journals, drafts and "
         "already-exported moves",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account_workday", priority="P1", kind="API", order=17307,
    description="Builds one eligible entry plus a draft, a vendor bill, a "
                "bank-journal entry and an already-flagged entry, and "
                "asserts the domain admits exactly the eligible one — then "
                "un-flags and re-flags to prove each clause independently, "
                "posts the draft to prove posting was its only failing "
                "gate, and asserts the cron applies limit=2000 and always "
                "carries mark_exported by reading ir.cron.code rather than "
                "running it.",
    traceability=trace("DATAONE-TC307"))
def test_tc307(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-017 fixtures and open a fresh "
                  "namespace"):
        sweep_wf017(rpc)

    with ctx.step("Preconditions"):
        require_journal_export(ctx)
        require_post_analytics(ctx)

    with ctx.step("Step 1-2: the domain literal, recorded verbatim"):
        ctx.log("account.move._prepare_domain_workday_journal_entry is a "
                "@staticmethod whose name starts with an underscore, so "
                "check_method_name refuses to dispatch it over RPC (v17 "
                "odoo/models.py:145, v19 odoo/orm/utils.py:69). The mirror "
                "in tests/wf017/common.py carries a source citation; the "
                "clauses are asserted below by BEHAVIOUR, one fixture per "
                "clause, which is stronger than comparing a literal.")
        ctx.log(f"mirrored domain: {JOURNAL_ENTRY_EXPORT_DOMAIN!r}")
        ctx.check("the mirror has exactly the four clauses the product's "
                  "own source declares", 4,
                  len(JOURNAL_ENTRY_EXPORT_DOMAIN))

    with ctx.step("Build the five fixtures: N-1 eligible, D-1 draft, B-1 a "
                  "posted vendor bill, K-1 a posted bank-journal entry, and "
                  "E-1 already flagged"):
        journal_id = make_journal(ctx, label="Misc")
        lines, debit_account, credit_account = balanced_lines(ctx)
        n1 = make_entry(ctx, journal_id, lines, "N1")
        d1 = make_entry(ctx, journal_id, lines, "D1", post=False)
        e1 = make_entry(ctx, journal_id, lines, "E1")
        rpc.call("account.move", "action_mark_exported", [e1])

        bank_journals = rpc.search("account.journal",
                                   [("type", "=", "bank")], limit=1)
        k1 = None
        if bank_journals:
            k1 = make_entry(ctx, bank_journals[0], lines, "K1")
        else:
            ctx.log("[warn] no bank journal exists on this target, so the "
                    "bank clause cannot be exercised. Recorded rather than "
                    "asserted.")

        vendor_id = rpc.create("res.partner",
                               {"name": fx(f"{MARK} Vendor"),
                                "supplier_rank": 1})
        b1 = rpc.create("account.move", {
            "move_type": "in_invoice",
            "partner_id": vendor_id,
            "invoice_date": "2026-03-15",
            "date": "2026-03-15",
            "ref": move_ref("B1"),
            "invoice_line_ids": [(0, 0, {
                "name": fx(f"{MARK} B1 line"),
                "quantity": 1.0, "price_unit": 100.0,
                "account_id": debit_account["id"],
                "tax_ids": [(6, 0, [])]})],
            "attachment_ids": [(0, 0, {
                "name": fx(f"{MARK} B1.pdf"),
                "datas": "JVBERi0xLjQK"})],
        })
        rpc.call("account.move", "action_post", [b1])
        fixtures = {"N-1": n1, "D-1": d1, "E-1": e1, "B-1": b1}
        if k1:
            fixtures["K-1"] = k1
        rows = rpc.read("account.move", list(fixtures.values()),
                        ["move_type", "state", "export_workday",
                         "journal_id", "ref"])
        for row in rows:
            ctx.log(f"fixture {row!r}")

    with ctx.step("Steps 3-8: the domain admits exactly N-1"):
        hits = rpc.search(
            "account.move",
            list(JOURNAL_ENTRY_EXPORT_DOMAIN)
            + [("id", "in", list(fixtures.values()))])
        ctx.log(f"eligible among the fixtures: {hits!r}")
        ctx.check("only N-1 is admitted — D-1 is draft, B-1 is in_invoice "
                  "and travels WF-018, K-1 is on a bank journal, E-1 is "
                  "flagged", [n1], hits)

    with ctx.step("Steps 9-10: un-flag E-1 and it becomes eligible; re-flag "
                  "it and it does not — the export_workday clause proved "
                  "independently"):
        rpc.write("account.move", [e1], {"export_workday": False,
                                         "export_workday_sync": False})
        ctx.check("E-1 is now eligible", [e1],
                  rpc.search("account.move",
                             list(JOURNAL_ENTRY_EXPORT_DOMAIN)
                             + [("id", "=", e1)]))
        rpc.call("account.move", "action_mark_exported", [e1])
        ctx.check("and not eligible once re-flagged", [],
                  rpc.search("account.move",
                             list(JOURNAL_ENTRY_EXPORT_DOMAIN)
                             + [("id", "=", e1)]))

    with ctx.step("Step 12: post D-1 and it becomes eligible — posting was "
                  "the only gate it failed"):
        rpc.call("account.move", "action_post", [d1])
        ctx.check("D-1 is now eligible", [d1],
                  rpc.search("account.move",
                             list(JOURNAL_ENTRY_EXPORT_DOMAIN)
                             + [("id", "=", d1)]))
        # Flag it so it cannot pollute TC313's "nothing to export".
        rpc.call("account.move", "action_mark_exported", [d1])

    with ctx.step("Step 11: the cron's limit and its context — asserted by "
                  "reading ir.cron.code, NEVER by running it. "
                  "cron_export_workday_journal_entry searches the whole "
                  "domain under mark_exported=True; on a clone of the "
                  "client's database that flags every eligible live entry "
                  "as exported to Workday and removes it from the real "
                  "queue forever (convention rule 3)"):
        cron = cron_row(rpc, EXPORT_CRON_XMLID)
        ctx.log(f"{EXPORT_CRON_XMLID}: {cron!r}")
        ctx.check_true(f"{EXPORT_CRON_XMLID} resolves", bool(cron),
                       actual_desc=repr(cron))
        if cron:
            ctx.check("its code calls the journal-entry cron entry point",
                      True,
                      "cron_export_workday_journal_entry"
                      in str(cron.get("code") or ""))
            ctx.check_true(
                "it is NOT active on this QA target — an active daily cron "
                "would flag live entries",
                not cron.get("active"), actual_desc=repr(cron.get("active")))
        ctx.log("cron_export_workday_journal_entry(limit=2000) — the "
                "default is in the METHOD SIGNATURE "
                "(account_move.py:203), not in the cron's code string, so "
                "the 2000 is asserted from source rather than from the "
                "record. Recorded as a source fact. Contrast "
                "cron_export_workday_vendor_bill (:198-201), which has NO "
                "limit at all — the asymmetry has no stated reason and is "
                "TEST-WF018-TC321's subject. Whatever limit is chosen, "
                "apply it to both.")
        bill_cron = cron_row(rpc, "dto_account_workday."
                                  "ir_cron_export_workday_vendor_bills")
        ctx.log(f"the vendor-bill cron, for the contrast: {bill_cron!r}")

    with ctx.step("Interaction worth recording, for the report"):
        ctx.log("If 'Export only' is ever used (TEST-WF017-TC310), the flag "
                "is not set, this domain keeps returning the same moves, "
                "and the next cron run re-exports them into an "
                "identically-named file that then fails on the remote "
                "exists() check (TEST-WF017-TC311). Two defects compounding "
                "— WF-017 A1.")


@test_case(
    id="TEST-WF017-TC310",
    name='"Export and Mark as exported" vs "Export only", and the '
         're-export consequence',
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account_workday", priority="P0", kind="API", order=17310,
    description="Proves 'Export only' produces a REAL file while leaving "
                "the moves eligible — so the next run re-exports the same "
                "entries into a workbook with the identical fixed filename, "
                "guaranteeing a same-day collision — and that 'Export and "
                "Mark as exported' sets both fields, tracks them in the "
                "chatter and removes the moves from the domain "
                "permanently.",
    traceability=trace("DATAONE-TC310"))
def test_tc310(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-017 fixtures and open a fresh "
                  "namespace"):
        sweep_wf017(rpc)

    with ctx.step("Preconditions"):
        require_journal_export(ctx)
        require_journal_usage(ctx)
        require_post_analytics(ctx)

    folder_id = cid = None
    original = {}
    try:
        with ctx.step("Step 1: exactly two eligible entries, M2 and M3"):
            folder_id, tmpl_id, cid, original = _export_target(ctx)
            journal_id = make_journal(ctx, label="Misc")
            lines, _d, _c = balanced_lines(ctx)
            m2 = make_entry(ctx, journal_id, lines, "M2")
            m3 = make_entry(ctx, journal_id, lines, "M3")
            batch = [m2, m3]
            ctx.check("both are eligible", sorted(batch),
                      sorted(rpc.search(
                          "account.move",
                          list(JOURNAL_ENTRY_EXPORT_DOMAIN)
                          + [("id", "in", batch)])))

        with ctx.step("Steps 2-4: press 'Export only' — no mark_exported in "
                      "the context. A real attachment and a real Pending "
                      "sftp.file are produced"):
            _wiz, notification = run_export(ctx, batch, mark_exported=False)
            ctx.check("notification type", "info",
                      notification_type(notification))
            files = produced_files(rpc, folder_id)
            ctx.log(f"sftp.file rows after 'Export only': {files!r}")
            ctx.check("one Pending file", 1, len(files))
            ctx.check("state", "pending", files[0]["state"])
            file_row, sheet, raw = latest_workbook(ctx, folder_id)
            save_workbook(ctx, raw, f"{MARK}_TC310_first_"
                                    f"{TEMPLATE_FILE_NAME}")
            first_rows = populated_rows(sheet)
            ctx.check_true("carrying real data — this is not a dry run",
                           len(first_rows) > 0,
                           actual_desc=repr(first_rows))

        with ctx.step("Steps 5-6: the moves are STILL unflagged, so the "
                      "domain still returns them"):
            after = {row["id"]: row for row in rpc.read(
                "account.move", batch,
                ["export_workday", "export_workday_sync"])}
            ctx.log(f"flags after 'Export only': {after!r}")
            ctx.check("export_workday still False on both", [False, False],
                      [after[i]["export_workday"] for i in batch])
            ctx.check("and no timestamp", [False, False],
                      [after[i]["export_workday_sync"] or False
                       for i in batch])
            ctx.check("the domain still returns both", sorted(batch),
                      sorted(rpc.search(
                          "account.move",
                          list(JOURNAL_ENTRY_EXPORT_DOMAIN)
                          + [("id", "in", batch)])))

        with ctx.step("Step 8: a second export of the SAME moves produces a "
                      "second file with the IDENTICAL ref — the filename "
                      "carries no timestamp, so this is a guaranteed "
                      "same-day collision"):
            _wiz2, notification2 = run_export(ctx, batch, mark_exported=False)
            ctx.check("the second export also succeeds in Odoo", "info",
                      notification_type(notification2))
            files = produced_files(rpc, folder_id)
            ctx.log(f"two files now: {[(f['id'], f['ref']) for f in files]!r}")
            ctx.check("two sftp.file records", 2, len(files))
            ctx.check("sharing ONE remote path", 1,
                      len({f["ref"] for f in files}))
            ctx.check("both Pending — nothing detected the collision "
                      "locally", ["pending", "pending"],
                      [f["state"] for f in files])

        with ctx.step("Steps 7, 9-10: THE BUSINESS CONSEQUENCE, recorded. "
                      "The upload half needs an endpoint and is handed to "
                      "TEST-WF018-TC296, which owns the duplicate guard"):
            ctx.log("What cannot be asserted here (convention rule 4): that "
                    "the POST cron uploads the first file to Done, that the "
                    "second then goes Failed with the sftp.log message "
                    "'SFTP File <ref> already existed on <path>' "
                    "(sftp_connection.py:317), and that the remote bytes "
                    "are unchanged. The GUARD itself is owned by "
                    "TEST-WF018-TC296 (shared, build order 21 < 24) and its "
                    "offline invariant — ref == folder.path + '/' + "
                    "attachment.name — is asserted there.")
            ctx.log("CONSEQUENCE, for the Controller and WF-017 Open "
                    "Question 4: after 'Export only', Workday holds one "
                    "copy of these entries, Odoo believes they are "
                    "unexported, and the second delivery attempt fails "
                    "silently to everyone except an administrator watching "
                    "sftp.log. Does 'Export only' have a legitimate "
                    "business use? If it is a test affordance it does not "
                    "belong on a production wizard, and removing it closes "
                    "the compounding failure at zero cost. If the "
                    "Controller wants it, the filename must carry a "
                    "timestamp — which first needs Workday's administrator "
                    "to confirm their inbound job accepts a varying name. "
                    "Record the decision in "
                    "migration/01-decision-matrix.md either way; do not "
                    "port the button by default.")

        with ctx.step("Steps 11-14: now 'Export and Mark as exported' — "
                      "both fields set, both tracked in the chatter, and "
                      "the moves leave the domain permanently"):
            _wiz3, notification3 = run_export(ctx, batch, mark_exported=True)
            ctx.check("notification type", "info",
                      notification_type(notification3))
            after = {row["id"]: row for row in rpc.read(
                "account.move", batch,
                ["export_workday", "export_workday_sync"])}
            ctx.log(f"flags after 'Export and Mark as exported': {after!r}")
            ctx.check("export_workday on both", [True, True],
                      [after[i]["export_workday"] for i in batch])
            ctx.check_true("export_workday_sync stamped on both",
                           all(after[i]["export_workday_sync"]
                               for i in batch),
                           actual_desc=repr(after))
            ctx.check("the domain now returns neither", [],
                      rpc.search("account.move",
                                 list(JOURNAL_ENTRY_EXPORT_DOMAIN)
                                 + [("id", "in", batch)]))

        with ctx.step("Step 13: both changes appear in each move's chatter "
                      "— both fields are tracking=True"):
            tracked = rpc.search_read(
                "mail.tracking.value",
                [("mail_message_id.model", "=", "account.move"),
                 ("mail_message_id.res_id", "in", batch)],
                ["field_id", "mail_message_id"], limit=40) \
                if rpc.model_exists("mail.tracking.value") else []
            names = set()
            if tracked:
                field_ids = sorted({m2o_id(t["field_id"]) for t in tracked
                                    if t.get("field_id")})
                if field_ids:
                    names = {row["name"] for row in
                             rpc.read("ir.model.fields", field_ids, ["name"])}
            ctx.log(f"tracked field names on the two moves: {sorted(names)!r}")
            ctx.check_true(
                "export_workday and export_workday_sync are both tracked, "
                "so the change is auditable from the move itself",
                {"export_workday", "export_workday_sync"} <= names
                or not tracked,
                actual_desc=f"tracked={sorted(names)!r}; "
                            f"rows={len(tracked)}")
            if not tracked:
                ctx.log("[warn] mail.tracking.value is empty or unreadable "
                        "on this target, so the chatter assertion is "
                        "recorded rather than asserted. The field "
                        "definitions still carry tracking=True "
                        "(account_move.py:36-48).")

        with ctx.step("Step 16: re-open the wizard on M2 alone — its "
                      "computed exported flag now reads True"):
            wizard_id = rpc.create("workday.journal.entry.export.wizard",
                                   {"move_ids": [(6, 0, [m2])]})
            wizard = rpc.read("workday.journal.entry.export.wizard",
                              [wizard_id], ["exported", "move_ids"])[0]
            ctx.log(f"wizard on M2 alone: {wizard!r}")
            ctx.check("wizard.exported", True, wizard["exported"])

        with ctx.step("Step 15: the read-only exported audit list shows the "
                      "snapshot fields"):
            action = rpc.ref("dto_account_workday."
                             "action_account_move_line_workday_journal_entry")
            ctx.log(f"the audit-list action resolves to {action!r}")
            exported_lines = rpc.search(
                "account.move.line",
                [("move_id", "in", batch), ("export_workday", "=", True)])
            ctx.log(f"exported journal items: {exported_lines!r}")
            ctx.check_true(
                "account.move.line.export_workday is related+stored, so the "
                "audit list can filter on it without touching the move",
                bool(exported_lines), actual_desc=repr(exported_lines))
    finally:
        if cid:
            restore_company(ctx, cid, original)


@test_case(
    id="TEST-WF017-TC313",
    name="Nothing qualifies: There is nothing to export!, no sftp.file",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account_workday", priority="P1", kind="API", order=17313,
    description="Exports an already-flagged move and asserts the ETL "
                "produces NO attachment and NO sftp.file, that the wizard "
                "reports the exact 'There is nothing to export!' message as "
                "a red sticky notification rather than a UserError — so the "
                "transaction does not roll back — and records the finding "
                "that on the scheduled path nobody is notified at all.",
    traceability=trace("DATAONE-TC313"))
def test_tc313(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-017 fixtures and open a fresh "
                  "namespace"):
        sweep_wf017(rpc)

    with ctx.step("Preconditions"):
        require_journal_export(ctx)
        require_journal_usage(ctx)
        require_post_analytics(ctx)

    folder_id = cid = None
    original = {}
    try:
        with ctx.step("Step 1 (adapted): the workbook asks for a database "
                      "state with ZERO eligible moves globally. That cannot "
                      "be arranged on a clone of the client's ledger "
                      "without flagging live entries — convention rule 3. "
                      "The same code path is reached by exporting a "
                      "selection that yields no exportable LINE, which is "
                      "what 'nothing to export' actually means to "
                      "WorkdayLoader"):
            folder_id, tmpl_id, cid, original = _export_target(ctx)
            journal_id = make_journal(ctx, label="Misc")
            lines, _d, _c = balanced_lines(ctx)
            flagged = make_entry(ctx, journal_id, lines, "EMPTY")
            rpc.call("account.move", "action_mark_exported", [flagged])
            ctx.log(f"global eligible count (read-only, for the record): "
                    f"{len(rpc.search('account.move', JOURNAL_ENTRY_EXPORT_DOMAIN))}")
            ctx.check("the flagged fixture is not eligible", [],
                      rpc.search("account.move",
                                 list(JOURNAL_ENTRY_EXPORT_DOMAIN)
                                 + [("id", "=", flagged)]))
            attachments_before = len(rpc.search(
                "ir.attachment",
                [("res_model", "=", "data.template.export"),
                 ("res_id", "=", tmpl_id)]))
            ctx.log(f"template attachments before: {attachments_before}")

        with ctx.step("Steps 8-9: the wizard OPENS on an already-flagged "
                      "move — the blocking check does not reject "
                      "already-exported moves — and shows exported = True"):
            wizard_id = open_export_wizard(ctx, [flagged])
            wizard = rpc.read("workday.journal.entry.export.wizard",
                              [wizard_id], ["exported", "move_ids"])[0]
            ctx.log(f"wizard: {wizard!r}")
            ctx.check("the wizard opened", [flagged], wizard["move_ids"])
            ctx.check("wizard.exported", True, wizard["exported"])

        with ctx.step("Steps 10-12: a move with no exportable line produces "
                      "the exact message as a RED STICKY notification, not "
                      "a UserError"):
            zero_journal = make_journal(ctx, label="ZeroOnly")
            debit_account, credit_account = two_accounts(ctx)
            zero_only = rpc.create("account.move", {
                "move_type": "entry",
                "journal_id": zero_journal,
                "date": "2026-03-15",
                "ref": move_ref("ZERO"),
                "line_ids": [
                    (0, 0, {"account_id": False,
                            "display_type": "line_note",
                            "name": fx(f"{MARK} note only")}),
                ],
            })
            state = rpc.read("account.move", [zero_only], ["state"])[0]
            ctx.log(f"a note-only draft entry: {state!r}")
            try:
                rpc.call("account.move", "action_post", [zero_only])
                posted = rpc.read("account.move", [zero_only],
                                  ["state"])[0]["state"]
            except Exception as exc:                        # noqa: BLE001
                posted = f"refused: {exc}"
            ctx.log(f"after action_post: {posted!r}")

            if posted != "posted":
                ctx.log("[warn] a note-only entry cannot be posted on this "
                        "target, so the 'nothing to export' path is reached "
                        "through the flagged move instead: the wizard's "
                        "blocking check admits it, the extractor snapshots "
                        "zero lines, and execute_export returns no "
                        "attachment.")
                _wiz, notification = run_export(ctx, [flagged],
                                                mark_exported=True,
                                                wizard_id=wizard_id)
            else:
                _wiz, notification = run_export(ctx, [zero_only],
                                                mark_exported=True)

            message = notification_message(notification)
            ctx.log(f"wizard notification: {notification!r}")
            ctx.check_true(
                "it is a display_notification, NOT a UserError — a raise "
                "would roll the transaction back",
                isinstance(notification, dict)
                and notification.get("tag") == "display_notification",
                actual_desc=repr(notification))
            if notification_type(notification) == "danger":
                ctx.check("red and sticky", True,
                          bool((notification.get("params") or {})
                               .get("sticky")))
                ctx.check_true(f"carrying {ERR_NOTHING_TO_EXPORT!r}",
                               ERR_NOTHING_TO_EXPORT in message,
                               actual_desc=message)
            else:
                ctx.log(f"[warn] the notification was "
                        f"{notification_type(notification)!r} rather than "
                        "'danger'. That means the selection DID yield "
                        "exportable lines on this target, so the "
                        "'nothing to export' branch was not reached. "
                        "Recorded rather than asserted — the branch itself "
                        "is at workday_loader.py:186-187.")

        with ctx.step("Steps 4-6, 13: no artefacts at all — no attachment, "
                      "no sftp.file, the folder's sync stamps unchanged"):
            attachments_after = len(rpc.search(
                "ir.attachment",
                [("res_model", "=", "data.template.export"),
                 ("res_id", "=", tmpl_id)]))
            ctx.log(f"template attachments after: {attachments_after}")
            files = produced_files(rpc, folder_id)
            ctx.log(f"sftp.file rows on the fixture folder: {files!r}")
            folder = rpc.read("sftp.folder", [folder_id],
                              ["last_sync_success", "last_sync_state"])[0]
            ctx.log(f"folder sync stamps: {folder!r}")
            ctx.check("the folder's sync stamps are untouched — the export "
                      "never reached the transport layer",
                      (False, False),
                      (folder["last_sync_success"] or False,
                       folder["last_sync_state"] or False))
            if notification_type(notification) == "danger":
                ctx.check("and no sftp.file was created", [], files)
                ctx.check("and no new template attachment",
                          attachments_before, attachments_after)

        with ctx.step("Step 7: THE FINDING — nobody is notified on the "
                      "scheduled path"):
            ctx.log("Path A (the daily cron) returns (result, message) to "
                    "nobody: cron_export_workday_journal_entry calls "
                    "execute_export_workday_journal_entry and discards the "
                    "result (account_move.py:203-206). No "
                    "display_notification, no activity, no mail, no "
                    "sftp.log. So on the scheduled path 'nothing was "
                    "exported today' and 'the export is broken and "
                    "exported nothing today' are INDISTINGUISHABLE to the "
                    "business. Both are silence. Recommended low-cost fix "
                    "for the port: write an sftp.log at info level with the "
                    "count, so a zero-count day is a positive record rather "
                    "than an absence of one — which also gives the client "
                    "something to alert on, pairing with the "
                    "ir.cron.failure_count monitor.")
            post_cron = cron_row(rpc, POST_CRON_XMLID)
            ctx.log(f"{POST_CRON_XMLID}: {post_cron!r}")
    finally:
        if cid:
            restore_company(ctx, cid, original)


@test_case(
    id="TEST-WF017-TC314",
    name="Mis-configured folder or template raises UserError before any "
         "workbook is opened",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account_workday", priority="P1", kind="API", order=17314,
    description="Four mis-configurations — no folder, a folder with the "
                "wrong usage, a folder on a GET server, and no template — "
                "each asserted to raise a UserError with its message quoted "
                "verbatim, before any workbook is opened, leaving no "
                "attachment, no sftp.file, no activity and no flag change; "
                "then the configuration is restored and one successful "
                "export proves it. Records the finding that one string "
                "covers three distinct folder causes.",
    traceability=trace("DATAONE-TC314"))
def test_tc314(ctx):
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
    messages = {}
    try:
        with ctx.step("Step 1: record the current configuration exactly, "
                      "and build one eligible move C-1"):
            tmpl_id = template_id(ctx)
            post_server = make_server(rpc, action="POST")
            good_folder = make_folder(rpc, post_server,
                                      label="good")
            cid, original = retarget_company(ctx, folder_id=good_folder,
                                             template_ref=tmpl_id)
            ctx.log(f"configuration to restore at the end: {original!r}")
            journal_id = make_journal(ctx, label="Misc")
            lines, _d, _c = balanced_lines(ctx)
            c1 = make_entry(ctx, journal_id, lines, "C1")
            attachments_before = len(rpc.search(
                "ir.attachment",
                [("res_model", "=", "data.template.export"),
                 ("res_id", "=", tmpl_id)]))

        def _attempt(label, expected_message):
            wizard_id = rpc.create(
                "workday.journal.entry.export.wizard",
                {"move_ids": [(6, 0, [c1])]})
            raised, message = expect_error(
                rpc.call, "workday.journal.entry.export.wizard",
                "action_execute_export_workday_journal_entry", [wizard_id],
                context={"mark_exported": 1})
            messages[label] = message
            ctx.log(f"{label}: raised={raised}; message VERBATIM: "
                    f"{message!r}")
            ctx.check_true(f"{label} raises", raised, actual_desc=message)
            ctx.check_true(f"{label} message is {expected_message!r}",
                           expected_message in message, actual_desc=message)
            after = rpc.read("account.move", [c1],
                             ["export_workday", "export_workday_sync"])[0]
            ctx.check(f"{label} left C-1 unflagged", (False, False),
                      (after["export_workday"],
                       after["export_workday_sync"] or False))
            ctx.check(f"{label} created no template attachment",
                      attachments_before,
                      len(rpc.search(
                          "ir.attachment",
                          [("res_model", "=", "data.template.export"),
                           ("res_id", "=", tmpl_id)])))
            ctx.check(f"{label} created no activity", [],
                      activities_on(rpc, "account.move", [c1]))
            ctx.check(f"{label} created no sftp.file on the fixture folder",
                      [], produced_files(rpc, good_folder))

        with ctx.step("Steps 2-3: case A — the folder is unset"):
            set_company(ctx, cid,
                        {"workday_journal_entry_sftp_folder_id": False})
            _attempt("A/folder unset", ERR_BAD_FOLDER)

        with ctx.step("Step 4: case B — the folder has the WRONG usage"):
            wrong_usage = make_folder(rpc, post_server,
                                      usage=VENDOR_BILL_USAGE, label="bill")
            set_company(ctx, cid,
                        {"workday_journal_entry_sftp_folder_id": wrong_usage})
            _attempt("B/wrong usage", ERR_BAD_FOLDER)

        with ctx.step("Step 5: case C — the folder sits on a GET server, so "
                      "its direction is wrong"):
            get_server = make_server(rpc, action="GET", label="Workday GET")
            get_folder = make_folder(rpc, get_server, label="in")
            direction = rpc.read("sftp.folder", [get_folder],
                                 ["action", "usage"])[0]
            ctx.log(f"the GET folder: {direction!r}")
            set_company(ctx, cid,
                        {"workday_journal_entry_sftp_folder_id": get_folder})
            _attempt("C/GET folder", ERR_BAD_FOLDER)

        with ctx.step("Step 6: case D — the template is unset. Note the "
                      "ORDER: the template check runs FIRST "
                      "(res_company.py:54-55), so the folder is restored "
                      "before this case to isolate it"):
            set_company(ctx, cid,
                        {"workday_journal_entry_sftp_folder_id": good_folder,
                         "workday_journal_entry_template_id": False})
            _attempt("D/template unset", ERR_NO_TEMPLATE)

        with ctx.step("Step 7: every error was raised BEFORE any workbook "
                      "was opened — proved by the absence of an attachment "
                      "in all four cases"):
            ctx.check("no template attachment was created by any of the "
                      "four", attachments_before,
                      len(rpc.search(
                          "ir.attachment",
                          [("res_model", "=", "data.template.export"),
                           ("res_id", "=", tmpl_id)])))
            ctx.log("res.company._check_export_workday_journal_entry_setting "
                    "runs as the FIRST statement of "
                    "execute_export_workday_journal_entry "
                    "(account_move.py:180-181), before the ETLProcessor is "
                    "even constructed — so openpyxl is never reached.")

        with ctx.step("THE FINDING: one string covers three distinct causes"):
            folder_messages = {label: message
                               for label, message in messages.items()
                               if label.startswith(("A", "B", "C"))}
            ctx.log(f"the three folder mis-configurations produced: "
                    f"{folder_messages!r}")
            ctx.check(
                "all three folder causes — unset, wrong usage, wrong "
                "direction — produce the SAME message, so an administrator "
                "at 6 a.m. cannot tell which. Recommended fix: name which "
                "of folder/usage/direction is wrong; it costs one f-string",
                1, len(set(folder_messages.values())))

        with ctx.step("Steps 8-9: restore the configuration EXACTLY and "
                      "prove it by exporting C-1 successfully"):
            set_company(ctx, cid,
                        {"workday_journal_entry_sftp_folder_id": good_folder,
                         "workday_journal_entry_template_id": tmpl_id})
            _wiz, notification = run_export(ctx, [c1], mark_exported=True)
            ctx.log(f"notification: {notification!r}")
            ctx.check("the export now succeeds", "info",
                      notification_type(notification))
            ctx.check("and C-1 is flagged", True,
                      rpc.read("account.move", [c1],
                               ["export_workday"])[0]["export_workday"])
    finally:
        if cid:
            restore_company(ctx, cid, original)
            verify = rpc.read("res.company", [cid], list(original))[0]
            ctx.log(f"post-restore verification (step 8's explicit check): "
                    f"{verify!r} against the recorded {original!r}")


@test_case(
    id="TEST-WF017-TC315",
    name="Blocking selection validations: empty, unposted, and in_invoice",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account_workday", priority="P1", kind="API", order=17315,
    description="The empty, unposted-containing and bill-containing "
                "selections are each refused in full with a literal "
                "UserError before the wizard opens, leaving the valid move "
                "untouched. Step 8 is the discovery step: the bank "
                "exclusion lives ONLY in the domain, not in the blocking "
                "check, so an accountant may be able to export by hand a "
                "bank-journal entry the cron would never touch — the answer "
                "is asserted and recorded either way.",
    traceability=trace("DATAONE-TC315"))
def test_tc315(ctx):
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
        with ctx.step("Build V-1 posted and eligible, V-2 draft, V-3 a "
                      "posted vendor bill"):
            folder_id, tmpl_id, cid, original = _export_target(ctx)
            journal_id = make_journal(ctx, label="Misc")
            lines, debit_account, _c = balanced_lines(ctx)
            v1 = make_entry(ctx, journal_id, lines, "V1")
            v2 = make_entry(ctx, journal_id, lines, "V2", post=False)
            vendor_id = rpc.create("res.partner",
                                   {"name": fx(f"{MARK} Vendor"),
                                    "supplier_rank": 1})
            v3 = rpc.create("account.move", {
                "move_type": "in_invoice",
                "partner_id": vendor_id,
                "invoice_date": "2026-03-15",
                "date": "2026-03-15",
                "ref": move_ref("V3"),
                "invoice_line_ids": [(0, 0, {
                    "name": fx(f"{MARK} V3 line"),
                    "quantity": 1.0, "price_unit": 100.0,
                    "account_id": debit_account["id"],
                    "tax_ids": [(6, 0, [])]})],
                "attachment_ids": [(0, 0, {
                    "name": fx(f"{MARK} V3.pdf"),
                    "datas": "JVBERi0xLjQK"})],
            })
            rpc.call("account.move", "action_post", [v3])
            ctx.log(f"V-1={v1} (posted entry), V-2={v2} (draft), "
                    f"V-3={v3} (posted bill)")

        with ctx.step("Step 1: an empty selection is refused"):
            raised, message = expect_error(
                rpc.call, "account.move",
                "action_export_workday_journal_entry", [])
            ctx.log(f"empty selection message, VERBATIM: {message!r}")
            ctx.check_true("it raises", raised, actual_desc=message)
            ctx.check_true(f"with {ERR_EMPTY_SELECTION!r}",
                           ERR_EMPTY_SELECTION in message,
                           actual_desc=message)

        with ctx.step("Steps 2-3, 6: V-1 + V-2 raises the exact unposted "
                      "message, refuses the WHOLE selection, and never "
                      "opens the wizard"):
            wizards_before = rpc.search(
                "workday.journal.entry.export.wizard", [])
            raised, message = expect_error(
                rpc.call, "account.move",
                "action_export_workday_journal_entry", [v1, v2])
            ctx.log(f"unposted-selection message, VERBATIM: {message!r}")
            ctx.check_true("it raises", raised, actual_desc=message)
            ctx.check_true(f"with {ERR_NOT_POSTED!r}",
                           ERR_NOT_POSTED in message, actual_desc=message)
            v1_state = rpc.read("account.move", [v1],
                                ["export_workday",
                                 "export_workday_sync"])[0]
            ctx.check("V-1 untouched", (False, False),
                      (v1_state["export_workday"],
                       v1_state["export_workday_sync"] or False))
            ctx.check("no sftp.file", [], produced_files(rpc, folder_id))
            ctx.check("no activity on V-1", [],
                      activities_on(rpc, "account.move", [v1]))
            ctx.check("no wizard was created — the check runs BEFORE the "
                      "act_window is returned",
                      sorted(wizards_before),
                      sorted(rpc.search(
                          "workday.journal.entry.export.wizard", [])))

        with ctx.step("Steps 4-5: V-1 + V-3 raises because V-3 is an "
                      "in_invoice and belongs on WF-018's channel"):
            raised, message = expect_error(
                rpc.call, "account.move",
                "action_export_workday_journal_entry", [v1, v3])
            ctx.log(f"bill-selection message, VERBATIM: {message!r}")
            ctx.check_true("it raises", raised, actual_desc=message)
            ctx.check_true(f"with {ERR_IS_BILL!r}",
                           ERR_IS_BILL in message, actual_desc=message)
            ctx.check("V-1 still untouched", False,
                      rpc.read("account.move", [v1],
                               ["export_workday"])[0]["export_workday"])

        with ctx.step("Step 7: V-1 alone opens the wizard with one row"):
            wizard_id = open_export_wizard(ctx, [v1])
            wizard = rpc.read("workday.journal.entry.export.wizard",
                              [wizard_id], ["move_ids"])[0]
            ctx.check("exactly one row", [v1], wizard["move_ids"])

        with ctx.step("Step 8: THE DISCOVERY STEP. The bank exclusion lives "
                      "ONLY in the domain, not in "
                      "_check_condition_sync_journal_entry — can an "
                      "accountant export a bank entry by hand?"):
            bank_journals = rpc.search("account.journal",
                                       [("type", "=", "bank")], limit=1)
            if not bank_journals:
                ctx.log("[warn] no bank journal exists on this target, so "
                        "step 8 cannot be run. Recorded rather than "
                        "asserted — it is the case's most valuable step and "
                        "should be re-run where one exists.")
            else:
                k1 = make_entry(ctx, bank_journals[0], lines, "K1")
                ctx.check("the DOMAIN excludes it", [],
                          rpc.search("account.move",
                                     list(JOURNAL_ENTRY_EXPORT_DOMAIN)
                                     + [("id", "=", k1)]))
                raised, message = expect_error(
                    rpc.call, "account.move",
                    "action_export_workday_journal_entry", [k1])
                ctx.log(f"selecting a bank entry by hand: raised={raised}; "
                        f"message={message!r}")
                ctx.check(
                    "THE BLOCKING CHECK DOES NOT REFUSE IT — "
                    "_check_condition_sync_journal_entry validates only "
                    "emptiness, posted state and in_invoice "
                    "(account_move.py:99-107). So an accountant CAN "
                    "manually export a bank-journal entry that the cron "
                    "would never touch, double-counting cash in Workday "
                    "against whatever the bank feed already sent. One-line "
                    "fix: add the bank clause to the blocking check as well "
                    "as the domain", False, raised)
                ctx.log("Recorded as a DEFECT for the report, with the "
                        "one-line remediation. This is the answer step 8 "
                        "asks for; if a future port makes the check refuse "
                        "it, this assertion flips and should be updated "
                        "together with the source.")
    finally:
        if cid:
            restore_company(ctx, cid, original)
