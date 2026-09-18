"""DATAONE-WF-010 — how it fails: TC347 and TC348.

TC347 — **no match.** When no MO is found, the message must carry BOTH
identifiers so a human can find the unit by hand, and nothing whatever
reaches manufacturing or quality: no activity on any MO, no chatter, no
email. By construction, because no MO was identified there is nowhere to
file one. Steps 8-9 record BR-9's consequence plainly — a test result that
never attaches shows up only as a missing attachment during an audit,
possibly months later, on a unit that has already shipped.

The case also asserts a live v17 defect rather than fixing it (step 6,
E2): the failure message's HTML is **unbalanced** — a ``<ul>`` is opened
and never closed (``mrp_attachment_transformer.py:64-69``). It renders
acceptably in most browsers but it is malformed, and convention rule 2
says the workbook's expectation is implemented, not corrected. Asserting
its presence is what makes the port fix it deliberately.

TC348 — **malformed files.** The extraction is positional on a ragged file
with no header and no validation, so it can fail in several distinct ways.
All of them must produce the SAME clean prefix with the underlying error
appended, rather than a raw traceback, because the person reading it is a
production supervisor and not a developer. Step 7 is the likely finding:
the extractor checks ``if not part_number or not serial_number`` and a
whitespace-only cell is TRUTHY in Python, so it passes extraction and
fails later at matching with the far less helpful "no MO found" message. A
``.strip()`` before the falsy check costs nothing.

The message SUFFIX is the v19 watch item: delta §2.13 changes what
``_read_file`` raises (``UserError`` instead of ``ImportError`` /
``ValueError``), so the text after the colon changes while the prefix does
not. Every variant's message is logged verbatim, which is what makes the
v19 comparison a five-minute job instead of a re-derivation.

EXPECTED v17 OUTCOME: PASS for both, with the E2 unbalanced HTML present
and the whitespace-only finding recorded.
EXPECTED v19 OUTCOME: PASS. The prefix is DataOne's own string and does
not move; the suffixes are expected to differ and are recorded rather than
asserted.
"""
from framework.registry import test_case
from tests.wf010.common import (ACTIVITY_TYPE_XMLID,  # noqa: F401
                                ERR_EXTRACT_PREFIX, ERR_NO_MATCH_HEADING,
                                ERR_NO_MATCH_PART_LABEL,
                                ERR_NO_MATCH_SERIAL_LABEL,
                                FILE_ACTIVITY_SUMMARY, MARK, PART_FIELD,
                                SERIAL_FIELD, SUPERUSER_ID, WORKFLOW,
                                WORKFLOW_NAME, activities_on,
                                attachments_on_mo, could_match, file_message,
                                fx, lot_name, m2o_id, make_folder, make_lot,
                                make_mo, make_product, make_server,
                                make_sftp_file, mo_dump, mo_with_lot,
                                part_code, process_file,
                                require_mrp_attachment, run_import,
                                sample_file, serial_for, set_producing_lot,
                                sweep_wf010, trace)


@test_case(
    id="TEST-WF010-TC347",
    name="No match: the failure lists the part and the serial, no activity "
         "on any MO",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_mrp_sftp", priority="P2", kind="API", order=10347,
    description="A well-formed file matching nothing at any tier fails with "
                "both identifiers labelled in the message, both diagnostic "
                "fields populated because they are written BEFORE matching, "
                "one superuser activity on the file and NONE on any "
                "manufacturing order, no chatter and no email; the "
                "attachment survives unstamped so the evidence is not lost; "
                "and creating the missing MO then re-processing attaches it. "
                "Also records the E2 unbalanced-HTML defect and the "
                "ambiguity tie-break.",
    traceability=trace("DATAONE-TC347"))
def test_tc347(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-010 fixtures and open a fresh "
                  "namespace"):
        sweep_wf010(rpc)

    with ctx.step("Preconditions: the attachment stack"):
        require_mrp_attachment(ctx)

    with ctx.step("Step 1: a well-formed file whose part and serial match "
                  "NOTHING at any tier, including the prefix — proved, not "
                  "assumed"):
        part = part_code("-NOSUCHPART-Z")
        serial = serial_for("999/999", lot=lot_name("z"))
        mails_before = (len(rpc.search("mail.mail", []))
                        if rpc.model_exists("mail.mail") else 0)
        reachable = could_match(ctx, part, serial)
        ctx.log(f"part={part!r} serial={serial!r}")
        ctx.log(f"what each tier could reach: {reachable!r}")
        ctx.check("nothing matches at any tier",
                  ([], [], []),
                  (reachable["tier1"], reachable["tier2"],
                   reachable["tier3"]))

    with ctx.step("Steps 2-4: the file Failed with process_date stamped, "
                  "and BOTH diagnostic fields populated — they are written "
                  "before matching, so they survive the failure"):
        folder_id, file_id, file_row = run_import(
            ctx, sample_file(part, serial), file_label="nomatch")
        ctx.log(f"sftp.file: {file_row!r}")
        ctx.check("state", "failed", file_row["state"])
        ctx.check_true("process_date stamped",
                       bool(file_row["process_date"]),
                       actual_desc=repr(file_row["process_date"]))
        ctx.check(PART_FIELD, part, file_row[PART_FIELD])
        ctx.check(SERIAL_FIELD, serial, file_row[SERIAL_FIELD])
        ctx.check("and nothing was stamped with an MO",
                  (False, False),
                  (bool(file_row["res_model"]), bool(file_row["res_id"])))

    with ctx.step("Step 5: the message lists BOTH identifiers, LABELLED — "
                  "quoted verbatim, because it is the only diagnostic a "
                  "supervisor gets"):
        message = file_message(rpc, file_id)
        ctx.log(f"failure message, verbatim: {message!r}")
        missing = [fragment for fragment in
                   (ERR_NO_MATCH_HEADING, ERR_NO_MATCH_PART_LABEL, part,
                    ERR_NO_MATCH_SERIAL_LABEL, serial)
                   if fragment not in message]
        ctx.check("the message carries the heading, both labels and both "
                  "values", [], missing)

    with ctx.step("Step 6: the E2 defect — the HTML is UNBALANCED. Assert "
                  "its presence and record it so the port fixes it; do not "
                  "correct the expectation (convention rule 2)"):
        opens = message.count("<ul>")
        closes = message.count("</ul>")
        ctx.log(f"<ul> opened {opens} time(s), closed {closes} time(s)")
        ctx.check_true(
            "the message opens a <ul> and never closes it — "
            "mrp_attachment_transformer.py:64-69 ends the f-string after "
            "the second <li>. It renders acceptably in most browsers and is "
            "still malformed; E2, recorded for the port",
            opens >= 1 and closes < opens,
            actual_desc=f"{opens} open, {closes} closed")

    with ctx.step("Step 7: one 'Cannot process SFTP file' warning activity "
                  "on the FILE, assigned to SUPERUSER_ID, deadline = the "
                  "process date, carrying that message"):
        acts = activities_on(rpc, "sftp.file", [file_id])
        ctx.log(f"file-level activities: {acts!r}")
        ctx.check("exactly one", 1, len(acts))
        activity = acts[0] if acts else {}
        ctx.check("summary", FILE_ACTIVITY_SUMMARY, activity.get("summary"))
        ctx.check("type", rpc.ref(ACTIVITY_TYPE_XMLID),
                  m2o_id(activity.get("activity_type_id")))
        ctx.check("assignee is SUPERUSER_ID — the id, not merely 'set'. "
                  "activity_schedule receives an int literal (F192), which "
                  "is SILENT if it ever stops resolving",
                  SUPERUSER_ID, m2o_id(activity.get("user_id")))
        ctx.check("deadline equals the process date",
                  str(file_row["process_date"])[:10],
                  str(activity.get("date_deadline")))

    with ctx.step("Steps 8-9: NOTHING reached manufacturing or quality — "
                  "no activity on any mrp.production, no chatter, no email. "
                  "By construction, because no MO was identified"):
        mo_acts = rpc.search_read(
            "mail.activity", [("res_model", "=", "mrp.production")],
            ["res_id", "summary"], limit=20)
        ctx.log(f"activities on mrp.production anywhere: {mo_acts!r}")
        ctx.check("none of them mentions this file's part or serial",
                  [], [a for a in mo_acts
                       if part in str(a) or serial in str(a)])
        mails_after = (len(rpc.search("mail.mail", []))
                       if rpc.model_exists("mail.mail") else 0)
        ctx.log(f"mail.mail rows: {mails_before} before, {mails_after} after")
        ctx.check("no email was generated", mails_before, mails_after)
        ctx.log("BR-9's consequence, recorded plainly: nothing reaches the "
                "people who need it. A test result that never attaches "
                "shows up only as a missing attachment during an audit, "
                "possibly months later, on a unit that has already shipped. "
                "The cheap remediation is to file the activity on the "
                "product matched by PART NUMBER when the serial fails, or "
                "on a configured quality user — there is a precedent in "
                "res.company.workday_sale_requisition_user_id (WF-001).")

    with ctx.step("Steps 10-11: the attachment still exists in Odoo, "
                  "unstamped, so the evidence is not lost even though it "
                  "did not attach"):
        attachment_id = m2o_id(file_row["attachment_id"])
        attachment = rpc.read("ir.attachment", [attachment_id],
                              ["name", "res_model", "res_id", "file_size"])[0]
        ctx.log(f"attachment after the failure: {attachment!r}")
        ctx.check_true("it still holds the file bytes",
                       (attachment.get("file_size") or 0) > 0,
                       actual_desc=repr(attachment.get("file_size")))
        ctx.check("and it is NOT stamped with any manufacturing order",
                  False, attachment["res_model"] == "mrp.production")
        ctx.log("Step 10's remote-archive assertion (the file was archived "
                "at download time and is never moved back, BR-10) needs an "
                "endpoint — SFTPConnection.move_files. Recorded, not "
                "asserted; convention rule 4.")

    with ctx.step("Step 12: create the missing MO with a matching lot, "
                  "Re-process the Failed file, and assert it now attaches "
                  "and reaches Done"):
        product_id = make_product(ctx, part)
        mo_fix, lot_id = mo_with_lot(ctx, product_id, serial)
        ctx.log(f"created MO {mo_fix} producing lot {lot_id} ({serial!r})")
        rpc.call("sftp.file", "action_retry_process_sftp_files", [file_id])
        retried = rpc.read("sftp.file", [file_id],
                           ["state", "res_model", "res_id",
                            "process_date"])[0]
        ctx.log(f"after Re-process: {retried!r}")
        ctx.check("the file is now Done", "done", retried["state"])
        ctx.check("and stamped with the new MO",
                  ("mrp.production", mo_fix),
                  (retried["res_model"], retried["res_id"]))
        ctx.check("the MO carries the evidence", 1,
                  len(attachments_on_mo(rpc, mo_fix)))

    with ctx.step("Step 13: the AMBIGUITY case (E3) — two MOs both matching "
                  "the same part and serial. Which one wins, and is it "
                  "stable?"):
        ctx.log("A second stock.lot cannot carry the same (name, product) "
                "pair on every configuration, so ambiguity is constructed "
                "at the MO level instead: a second MO producing the SAME "
                "lot record.")
        mo_dup = make_mo(ctx, product_id)
        set_producing_lot(ctx, mo_dup, lot_id)
        reachable = could_match(ctx, part, serial)
        ctx.log(f"both MOs now reachable at tier 2: {reachable!r}")
        if len(reachable["tier2"]) < 2:
            ctx.log("[warn] this target refused a second MO on the same "
                    "producing lot, so the ambiguity case is not "
                    "constructible here. Recorded rather than asserted — "
                    "which is itself the answer: the database prevents it.")
        else:
            _f, amb_id, amb_row = run_import(
                ctx, sample_file(part, serial), folder_id=folder_id,
                file_label="ambiguous")
            ctx.log(f"ambiguous file landed on res_id "
                    f"{amb_row['res_id']} out of candidates "
                    f"{reachable['tier2']!r}")
            ctx.check(
                "search(limit=1) chose the LOWEST id — there is no "
                "tie-break and no warning today, and v19's default ordering "
                "could differ, so an evidence file could start attaching to "
                "a different MO after the upgrade with nothing raised",
                min(reachable["tier2"]), amb_row["res_id"])
            ctx.log("E3, recorded for the port: the winner is whatever "
                    "search() orders first. If that matters to the quality "
                    "function it needs an explicit tie-break, not a "
                    "default.")


@test_case(
    id="TEST-WF010-TC348",
    name="Malformed file: the exact Cannot extract product info from file "
         "content: message",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_mrp_sftp", priority="P2", kind="API", order=10348,
    description="Six malformed variants — a one-cell first row, a "
                "comma-leading last row, an empty file, a single-row file, "
                "a binary payload under a .csv name, and a whitespace-only "
                "part number — each asserted to fail with the SAME clean "
                "prefix and a captured suffix, with both diagnostic fields "
                "recording how far extraction got, nothing stamped onto any "
                "MO, and the separator proved to be pinned rather than "
                "sniffed.",
    traceability=trace("DATAONE-TC348"))
def test_tc348(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-010 fixtures and open a fresh "
                  "namespace"):
        sweep_wf010(rpc)

    with ctx.step("Preconditions: the attachment stack, plus one real MO so "
                  "'nothing was stamped' is a meaningful assertion rather "
                  "than vacuous"):
        require_mrp_attachment(ctx)
        part = part_code()
        prefix = lot_name()
        serial = serial_for("037/042", lot=prefix)
        product_id = make_product(ctx, part)
        mo_id, _lot = mo_with_lot(ctx, product_id, prefix)
        before_dump = mo_dump(rpc, mo_id)
        ctx.log(f"control MO {mo_id} exists and WOULD match a well-formed "
                f"file for part {part!r}")
        folder_id = make_folder(rpc, make_server(rpc))

    findings = {}

    def _variant(label, content, mimetype="text/csv"):
        file_id = make_sftp_file(rpc, folder_id, fx(f"{MARK}_{label}.csv"),
                                 content, mimetype=mimetype)
        row = process_file(ctx, file_id)
        message = file_message(rpc, file_id)
        ctx.log(f"{label}: state={row['state']!r} "
                f"{PART_FIELD}={row[PART_FIELD]!r} "
                f"{SERIAL_FIELD}={row[SERIAL_FIELD]!r}")
        ctx.log(f"{label} message, VERBATIM: {message!r}")
        findings[label] = {
            "state": row["state"],
            "part": row[PART_FIELD],
            "serial": row[SERIAL_FIELD],
            "prefix_present": ERR_EXTRACT_PREFIX in message,
            "suffix": (message.split(ERR_EXTRACT_PREFIX, 1)[1][:120]
                       if ERR_EXTRACT_PREFIX in message else ""),
            "res_id": row["res_id"],
        }
        return file_id, row, message

    with ctx.step("Steps 1-2: M1 — a first row with only one cell, so "
                  "rows[0][1] does not exist"):
        _id, row, message = _variant("M1_one_cell_header", b"PART#\nTESTER,DJ\n")
        ctx.check("the file Failed", "failed", row["state"])
        ctx.check_true(f"the message begins {ERR_EXTRACT_PREFIX!r}",
                       ERR_EXTRACT_PREFIX in message, actual_desc=message)
        ctx.log("Step 2: the two diagnostic fields hold whatever was "
                "extracted before the failure — here nothing, because the "
                "IndexError fires on rows[0][1] before either write "
                "(mrp_attachment_extractor.py:46-60).")

    with ctx.step("Step 3: M2 — a last row whose first cell is empty"):
        _id, row, message = _variant(
            "M2_empty_first_cell",
            b"PART#,ABC\nSERIAL#,INPUT\n,Fiber 1 End A,Fiber 1 End B,0.4\n")
        ctx.check("the file Failed", "failed", row["state"])
        ctx.check_true("with the same prefix and a different suffix",
                       ERR_EXTRACT_PREFIX in message, actual_desc=message)

    with ctx.step("Step 4: M3 — a completely empty file"):
        _id, row, message = _variant("M3_empty", b"")
        ctx.check("the file Failed", "failed", row["state"])
        ctx.check_true("with the same prefix",
                       ERR_EXTRACT_PREFIX in message, actual_desc=message)

    with ctx.step("Step 5: M4 — a single row. rows[0] and rows[-1] are the "
                  "SAME row, so the part comes from cell 1 and the serial "
                  "from cell 0 of one line. Record what that produces — it "
                  "is the degenerate case of TC349's positional problem"):
        _id, row, message = _variant("M4_single_row",
                                     f"{serial},{part}".encode())
        ctx.log(f"M4 outcome: {findings['M4_single_row']!r}")
        ctx.check_true(
            "the degenerate read is recorded either way: the part is cell 1 "
            "and the serial is cell 0 of the one line, so a single-row file "
            "EXTRACTS SUCCESSFULLY and then fails (or succeeds) at matching "
            "— a different message and a worse diagnostic than an "
            "extraction error",
            row["state"] in ("done", "failed"),
            actual_desc=f"state={row['state']!r}, part={row[PART_FIELD]!r}, "
                        f"serial={row[SERIAL_FIELD]!r}")
        if row[PART_FIELD]:
            ctx.check("extraction read the part from cell 1 of the only row",
                      part, row[PART_FIELD])
            ctx.check("and the serial from cell 0 of the same row", serial,
                      row[SERIAL_FIELD])

    with ctx.step("Step 6: M5 — a binary payload under a .csv name. The "
                  "reader's exception must be CAPTURED into the same "
                  "message rather than escaping"):
        binary = bytes(range(256)) * 4
        _id, row, message = _variant("M5_binary", binary,
                                     mimetype="application/octet-stream")
        ctx.check("the file Failed rather than raising out of "
                  "action_process_sftp_files", "failed", row["state"])
        ctx.check_true("and the reader's error was captured into the same "
                       "prefixed message",
                       ERR_EXTRACT_PREFIX in message, actual_desc=message)

    with ctx.step("Step 7: M6 — a whitespace-only part number. THE LIKELY "
                  "FINDING: ' ' is TRUTHY in Python, so the falsy check "
                  "does not catch it"):
        _id, row, message = _variant(
            "M6_whitespace_part",
            sample_file("   ", serial))
        ctx.log(f"M6 outcome: {findings['M6_whitespace_part']!r}")
        ctx.check_true(
            "the whitespace-only part PASSED extraction and failed at "
            "MATCHING instead — the extractor checks `if not part_number` "
            "(extractor:51) and a blank-but-present cell is truthy, so the "
            "supervisor gets 'Cannot find Manufacturing Order' rather than "
            "'Cannot extract product info'. A .strip() before the falsy "
            "check costs nothing and is the remediation",
            ERR_NO_MATCH_HEADING in message
            or ERR_EXTRACT_PREFIX in message,
            actual_desc=message)
        ctx.log(f"which message did it produce? "
                f"extract={ERR_EXTRACT_PREFIX in message}, "
                f"no-match={ERR_NO_MATCH_HEADING in message}")

    with ctx.step("Step 8: every variant left the file Failed with a "
                  "superuser activity carrying its message"):
        files = rpc.search("sftp.file", [("folder_id", "=", folder_id)])
        rows = rpc.read("sftp.file", files, ["state", "name"])
        ctx.log(f"all variant files: {rows!r}")
        unexpected = [r for r in rows if r["state"] == "pending"]
        ctx.check("none was left Pending — every variant reached a terminal "
                  "state", [], unexpected)
        failed_ids = [r["id"] for r in rows if r["state"] == "failed"]
        acts = activities_on(rpc, "sftp.file", failed_ids)
        ctx.log(f"activities across the failed variants: "
                f"{[(a['res_id'], a['summary']) for a in acts]!r}")
        ctx.check("one activity per Failed file", len(failed_ids), len(acts))
        ctx.check("every one is the superuser warning",
                  {(FILE_ACTIVITY_SUMMARY, SUPERUSER_ID)},
                  {(a["summary"], m2o_id(a["user_id"])) for a in acts})

    with ctx.step("Step 9: no attachment was stamped onto any MO and no MO "
                  "field changed"):
        ctx.check("the control MO received nothing", [],
                  attachments_on_mo(rpc, mo_id))
        after_dump = mo_dump(rpc, mo_id)
        volatile = {"write_date", "__last_update", "message_needaction",
                    "message_needaction_counter", "message_has_error",
                    "message_has_error_counter", "message_attachment_count",
                    "access_token", "activity_state",
                    "activity_date_deadline"}
        drift = {key: {"before": before_dump.get(key),
                       "after": after_dump.get(key)}
                 for key in set(before_dump) | set(after_dump)
                 if key not in volatile
                 and before_dump.get(key) != after_dump.get(key)}
        ctx.check("and no stored field on it changed", {}, drift)

    with ctx.step("Step 10: the separator is genuinely PINNED — a "
                  "tab-delimited version of the canonical file must FAIL, "
                  "confirming options={'separator': ','} is honoured and "
                  "the file is not auto-sniffed"):
        tabbed = sample_file(part, serial).replace(b",", b"\t")
        _id, row, message = _variant("M7_tab_delimited", tabbed)
        ctx.check_true(
            "the tab-delimited file did NOT attach — this is the only "
            "extractor in DataOne that pins the separator "
            "(extractor:42-45), and a sniffing reader would have parsed it",
            row["res_id"] in (False, 0, None),
            actual_desc=f"state={row['state']!r} res_id={row['res_id']!r}")

    with ctx.step("Step 11: the v17 message suffixes, captured for the v19 "
                  "comparison"):
        for label in sorted(findings):
            ctx.log(f"  {label}: state={findings[label]['state']!r} "
                    f"prefix_present={findings[label]['prefix_present']} "
                    f"suffix={findings[label]['suffix']!r}")
        ctx.log("Delta §2.13 changes what _read_file RAISES — UserError "
                "instead of ImportError / ValueError — so the text after "
                "the colon changes on v19 while the prefix does not. These "
                "captured suffixes are what makes that comparison a "
                "five-minute job rather than a re-derivation. Re-run this "
                "case on v19 and diff the log.")
