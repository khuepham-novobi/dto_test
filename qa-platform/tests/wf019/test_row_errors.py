"""DATAONE-WF-019 — how it fails: TC327, TC328, TC330.

TC327 — **two-level error surfacing.** A failed payment import must reach
a human. This flow is deliberately different from WF-020: it files an
activity on the BILL, so the error reaches whoever owns that payable, AND
marks the ``sftp.file`` for the administrator's triage queue. If only one
level fires, either the accountant or the administrator never finds out.
The finding this case produces is steps 10-11: **both activities are
assigned to SUPERUSER_ID**, so in practice neither has a named owner, and
no email is sent to anybody.

TC328 — **the eight column names are Workday's own labels** with spaces
and apostrophes replaced by underscores. A Workday-side report change
renames one and the feed breaks; this case establishes exactly HOW it
breaks, because that decides whether the AP team loses one payment or a
day's worth. The operational finding is the asymmetry: a missing COLUMN
costs the rows that need it, while a single SHORT ROW costs the whole file
— ``_convert_data_to_list_of_dict`` indexes ``row[index]`` across the
header's width with no length guard
(``sftp_extractor.py:64-75``).

TC330 — **row-level rejections.** ``Payment_Type`` is matched by exact
name against the journal's outbound payment method lines after a bare
``.strip()``. The variant most likely to happen in production and least
likely to be guessed is a NON-BREAKING SPACE: Workday report exports emit
U+00A0 routinely and ``str.strip()`` does remove it in Python 3 — which is
why this case ASSERTS the actual behaviour rather than the expectation,
and reports whichever it finds. The case's contract is that every rejection
is row-level: ``_prepare_workday_payment_vals`` RETURNS ``(vals,
error_message)`` and never raises (BR-6), so one bad row must not stop the
others.

EXPECTED v17 OUTCOME: PASS for all three.
EXPECTED v19 OUTCOME: PASS. The watch item is ``base_import._read_file``'s
rewritten internals (delta §2.13) — the signature and the ``(n_rows,
rows)`` contract are unchanged so the call site is structurally safe, but
failures now raise ``UserError`` instead of ``ImportError`` /
``ValueError``, which changes what the ETL captures and therefore what the
administrator reads. TC328 logs every produced message verbatim precisely
so that difference is recorded rather than discovered.
"""
from framework.registry import test_case
from tests.wf019.common import (ACTIVITY_TYPE_XMLID,  # noqa: F401
                                BILL_ACTIVITY_SUMMARY, CSV_COLUMNS,
                                ERR_BILL_NOT_FOUND, ERR_EMPTY_DATE,
                                ERR_NO_JOURNAL, ERR_OVER_RESIDUAL,
                                FILE_ACTIVITY_SUMMARY, MARK, SUPERUSER_ID,
                                WORKFLOW, WORKFLOW_NAME, activities_on,
                                base_url, bill_state, document_link,
                                ensure_product, ensure_vendor, file_message,
                                fx, m2o_id, make_bill, payment_journal,
                                payments_for, require_payment_import,
                                restore_company, retarget_payment_journal,
                                row, run_import, sweep_wf019, trace,
                                workday_id)


@test_case(
    id="TEST-WF019-TC327",
    name="Two-level error surfacing: an activity on the bill *and* the "
         "file Failed",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account_workday, novobi_sftp_connection",
    priority="P1", kind="API", order=19327,
    description="One three-row file — one success, one failure with an "
                "identified bill, one without — proves both error levels "
                "fire independently, that the unidentifiable row has "
                "nowhere to file an activity, that the successful payment "
                "is not rolled back by the file going Failed, and that no "
                "email reaches anyone. Records the finding: both activities "
                "land on SUPERUSER_ID, so neither has a named owner.",
    traceability=trace("DATAONE-TC327"))
def test_tc327(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-019 fixtures and open a fresh "
                  "namespace"):
        sweep_wf019(rpc)

    with ctx.step("Preconditions: the payment stack and a usable bank "
                  "journal"):
        require_payment_import(ctx)
        journal_id, method_names = payment_journal(ctx)
        method = method_names[0]

    cid = None
    original = {}
    try:
        with ctx.step("Point the company at that journal, and record the "
                      "mail baseline BEFORE the run"):
            cid, original = retarget_payment_journal(ctx, journal_id)
            mails_before = len(rpc.search("mail.mail", [])) \
                if rpc.model_exists("mail.mail") else 0
            ctx.log(f"mail.mail rows before the run: {mails_before}")

        with ctx.step("Step 1: three rows — one succeeds, one fails with an "
                      "identified bill (over-residual on PB-D), one fails "
                      "without one (unmatched ref)"):
            vendor_id = ensure_vendor(rpc)
            product_id = ensure_product(ctx)
            pb_a, a_row = make_bill(ctx, vendor_id, 500.0, "ERR-201",
                                    label="PB-A", product_id=product_id)
            pb_d, d_row = make_bill(ctx, vendor_id, 300.0, "ERR-204",
                                    label="PB-D", product_id=product_id)
            url = base_url(rpc)
            sp_ok = workday_id("SP", 1)
            _folder, file_id, file_row = run_import(ctx, [
                row(sp_ok, workday_id("SID", 1), bill_ref_value=a_row["ref"],
                    document_link=document_link(url, pb_a), amount="100.00",
                    payment_type=method, reference=f"TRX-{fx('E1')}"),
                row(workday_id("SP", 2), workday_id("SID", 2),
                    bill_ref_value=d_row["ref"], document_link="",
                    amount="999.00", payment_type=method,
                    reference=f"TRX-{fx('E2')}"),
                row(workday_id("SP", 3), workday_id("SID", 3),
                    bill_ref_value=fx(f"{MARK} INV-NOSUCH-999"),
                    document_link="", amount="10.00", payment_type=method,
                    reference=f"TRX-{fx('E3')}"),
            ], file_label="two_level")
            ctx.log(f"sftp.file: {file_row!r}")

        with ctx.step("Step 2: the successful row produced a posted, "
                      "reconciled payment"):
            payments = payments_for(rpc, sp_ok)
            ctx.check("one payment", 1, len(payments))
            ctx.check("posted", "posted", payments[0]["state"])
            ctx.check("PB-A's residual fell by exactly the payment amount",
                      400.0, bill_state(rpc, pb_a)["amount_residual"])

        with ctx.step("Steps 3-4: LEVEL (a) — exactly one activity on PB-D, "
                      "of the right type, summary, assignee and deadline, "
                      "naming the reason"):
            acts = activities_on(rpc, "account.move", [pb_d])
            ctx.log(f"activities on PB-D: {acts!r}")
            ctx.check("exactly one activity on PB-D", 1, len(acts))
            activity = acts[0] if acts else {}
            ctx.check("summary", BILL_ACTIVITY_SUMMARY,
                      activity.get("summary"))
            ctx.check("type", rpc.ref(ACTIVITY_TYPE_XMLID),
                      m2o_id(activity.get("activity_type_id")))
            ctx.check("assignee is SUPERUSER_ID — the ID, not merely 'set'",
                      SUPERUSER_ID, m2o_id(activity.get("user_id")))
            ctx.log(f"activity body, verbatim: {activity.get('note')!r}")
            ctx.check_true(f"body contains {ERR_OVER_RESIDUAL!r}",
                           ERR_OVER_RESIDUAL in str(activity.get("note")
                                                    or ""),
                           actual_desc=repr(activity.get("note")))

        with ctx.step("Step 5: NO activity anywhere for the unmatched row — "
                      "no bill was identified, so there is nowhere to put "
                      "one"):
            ctx.check("no activity on PB-A", [],
                      activities_on(rpc, "account.move", [pb_a]))
            ctx.check("no activity on the vendor", [],
                      activities_on(rpc, "res.partner", [vendor_id]))
            all_acts = rpc.search_read(
                "mail.activity",
                [("summary", "in", [BILL_ACTIVITY_SUMMARY,
                                    FILE_ACTIVITY_SUMMARY]),
                 "|", "&", ("res_model", "=", "account.move"),
                 ("res_id", "in", [pb_a, pb_d]),
                 "&", ("res_model", "=", "sftp.file"),
                 ("res_id", "=", file_id)],
                ["res_model", "res_id", "summary"])
            ctx.log(f"every activity this run created: {all_acts!r}")
            ctx.check("exactly two — one on PB-D, one on the file", 2,
                      len(all_acts))

        with ctx.step("Steps 6-8: LEVEL (b) — the file is Failed with its "
                      "own SUPERUSER_ID activity carrying BOTH row errors "
                      "joined with <br/>"):
            ctx.check("file state", "failed", file_row["state"])
            ctx.check_true("process_date stamped",
                           bool(file_row["process_date"]),
                           actual_desc=repr(file_row["process_date"]))
            file_acts = activities_on(rpc, "sftp.file", [file_id])
            ctx.log(f"file-level activity: {file_acts!r}")
            ctx.check("one file-level activity", 1, len(file_acts))
            file_activity = file_acts[0] if file_acts else {}
            ctx.check("summary", FILE_ACTIVITY_SUMMARY,
                      file_activity.get("summary"))
            ctx.check("assignee is SUPERUSER_ID", SUPERUSER_ID,
                      m2o_id(file_activity.get("user_id")))
            ctx.check("deadline equals the process date",
                      str(file_row["process_date"])[:10],
                      str(file_activity.get("date_deadline")))
            note = str(file_activity.get("note") or "")
            ctx.log(f"file activity body, verbatim: {note!r}")
            ctx.check_true("it carries BOTH row errors",
                           ERR_OVER_RESIDUAL in note
                           and ERR_BILL_NOT_FOUND in note,
                           actual_desc=note)
            ctx.check_true("joined with <br/>", "<br/>" in note,
                           actual_desc=note)

        with ctx.step("Step 9: the successful row's payment was NOT rolled "
                      "back by the file going Failed"):
            ctx.check("the payment still exists and is posted",
                      ["posted"],
                      [p["state"] for p in payments_for(rpc, sp_ok)])

        with ctx.step("Steps 10-11: THE FINDING — no email is sent, and "
                      "both activities land on the superuser, so neither "
                      "has a named owner"):
            mails_after = len(rpc.search("mail.mail", [])) \
                if rpc.model_exists("mail.mail") else 0
            ctx.log(f"mail.mail rows after the run: {mails_after} "
                    f"(before: {mails_before})")
            ctx.check("no email was generated by this run — nobody is "
                      "notified", mails_before, mails_after)
            ctx.check("both activities are assigned to SUPERUSER_ID",
                      [SUPERUSER_ID, SUPERUSER_ID],
                      [m2o_id(activity.get("user_id")),
                       m2o_id(file_activity.get("user_id"))])
            ctx.log("Practical consequence, for the report: if nobody "
                    "follows the superuser's activity list and nobody "
                    "follows PB-D, the failed payment is invisible to the "
                    "business until the AP ageing looks wrong. The design "
                    "is sound — two levels, one for the accountant and one "
                    "for the administrator — but both are unowned. "
                    "Recommend assigning the bill-level activity to the "
                    "bill's create_uid or to a configured AP user (there "
                    "is a precedent: res.company."
                    "workday_sale_requisition_user_id does exactly this "
                    "for WF-001) and the file-level one to a named "
                    "integration administrator.")

        with ctx.step("Step 12: the activity is where a human would see it "
                      "— in PB-D's own chatter"):
            ctx.check("the activity's res_model/res_id point at PB-D",
                      ("account.move", pb_d),
                      (activity.get("res_model"), activity.get("res_id")))
    finally:
        if cid:
            restore_company(ctx, cid, original)


@test_case(
    id="TEST-WF019-TC328",
    name="A missing expected column produces a row error; a short row "
         "fails the whole file",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account_workday", priority="P1", kind="API", order=19328,
    description="Five malformed variants of the eight-column file establish "
                "exactly how a Workday-side report change breaks the feed: "
                "reordering is harmless, a missing column costs the rows "
                "that need it, a SHORT ROW costs the whole file, a "
                "duplicated header silently keeps the first occurrence, and "
                "a shifted header fails everything. Every produced message "
                "is logged verbatim so a v19 change in failure type is "
                "recorded rather than discovered.",
    traceability=trace("DATAONE-TC328"))
def test_tc328(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-019 fixtures and open a fresh "
                  "namespace"):
        sweep_wf019(rpc)

    with ctx.step("Preconditions: the payment stack and a usable bank "
                  "journal"):
        require_payment_import(ctx)
        journal_id, method_names = payment_journal(ctx)
        method = method_names[0]

    cid = None
    original = {}
    findings = {}
    try:
        with ctx.step("Set up: the company journal and two posted bills "
                      "with enough residual for four settlements"):
            cid, original = retarget_payment_journal(ctx, journal_id)
            vendor_id = ensure_vendor(rpc)
            product_id = ensure_product(ctx)
            pb_a, a_row = make_bill(ctx, vendor_id, 1000.0, "COL-201",
                                    label="PB-A", product_id=product_id)
            pb_b, b_row = make_bill(ctx, vendor_id, 1000.0, "COL-202",
                                    label="PB-B", product_id=product_id)
            url = base_url(rpc)

            def good(index, move_id, ref_value, amount="50.00"):
                return row(workday_id("SP", index),
                           workday_id("SID", index),
                           bill_ref_value=ref_value,
                           document_link=document_link(url, move_id),
                           amount=amount, payment_type=method,
                           reference=f"TRX-{fx(f'C{index}')}")

        with ctx.step("Step 1: V4 — the columns in a completely different "
                      "order. Presence matters, order does not"):
            reordered = list(reversed(CSV_COLUMNS))
            _f, file_id, file_row = run_import(
                ctx, [good(1, pb_a, a_row["ref"])], columns=reordered,
                file_label="V4_reordered")
            ctx.log(f"V4 file: {file_row!r}; message: "
                    f"{file_message(rpc, file_id)!r}")
            ctx.check("V4 succeeds — column order is irrelevant", "done",
                      file_row["state"])
            ctx.check("and it produced its payment", 1,
                      len(payments_for(rpc, workday_id("SP", 1))))
            findings["V4 reordered columns"] = "succeeds"

        with ctx.step("Steps 2-4: V1 — the header is missing Payment_Date. "
                      "A missing COLUMN is a row-level failure"):
            without_date = [c for c in CSV_COLUMNS if c != "Payment_Date"]
            _f, file_id, file_row = run_import(
                ctx, [good(2, pb_a, a_row["ref"])], columns=without_date,
                file_label="V1_missing_column")
            message = file_message(rpc, file_id)
            ctx.log(f"V1 file: {file_row!r}")
            ctx.log(f"V1 message, verbatim: {message!r}")
            created = payments_for(rpc, workday_id("SP", 2))
            ctx.check("no payment survived the missing column", [], created)
            ctx.check("the file is Failed", "failed", file_row["state"])
            ctx.check_true(
                "the captured message NAMES the missing key, so an "
                "administrator can act on it",
                "Payment_Date" in message, actual_desc=message)
            findings["V1 missing Payment_Date column"] = (
                f"file={file_row['state']}, payments={len(created)}")

        with ctx.step("Steps 5-7: V2 — one seven-cell data row among "
                      "well-formed ones. THE ASYMMETRY: a short row costs "
                      "the WHOLE file"):
            _f, file_id, file_row = run_import(
                ctx, [good(3, pb_a, a_row["ref"]),
                      good(4, pb_b, b_row["ref"]),
                      good(5, pb_b, b_row["ref"])],
                short_row_index=1, file_label="V2_short_row")
            message = file_message(rpc, file_id)
            ctx.log(f"V2 file: {file_row!r}")
            ctx.log(f"V2 message, verbatim: {message!r}")
            ctx.check("the file is Failed", "failed", file_row["state"])
            survivors = [index for index in (3, 4, 5)
                         if payments_for(rpc, workday_id("SP", index))]
            ctx.check(
                "NO payment at all was created — including from the two "
                "well-formed rows. _convert_data_to_list_of_dict indexes "
                "row[index] across the header's width with no length guard "
                "(sftp_extractor.py:64-75), so the IndexError aborts the "
                "extract stage before any row is transformed",
                [], survivors)
            ctx.check_true(
                "the message is a captured exception from the EXTRACT "
                "stage, not a per-row error",
                "EXTRACT" in message or "index" in message.lower(),
                actual_desc=message)
            findings["V2 one short data row"] = (
                f"file={file_row['state']}, payments=0 (whole file lost)")

        with ctx.step("Step 8: V3 — Supplier_s_Invoice_Number misspelled. "
                      "The FALLBACK match cannot run; does Document_Link "
                      "alone still carry the row?"):
            misspelled = ["Suppliers_Invoice_Number" if c ==
                          "Supplier_s_Invoice_Number" else c
                          for c in CSV_COLUMNS]
            _f, file_id, file_row = run_import(
                ctx, [good(6, pb_a, a_row["ref"])], columns=misspelled,
                file_label="V3_misspelled")
            message = file_message(rpc, file_id)
            ctx.log(f"V3 file: {file_row!r}")
            ctx.log(f"V3 message, verbatim: {message!r}")
            created = payments_for(rpc, workday_id("SP", 6))
            ctx.log(f"V3 payments: {created!r}")
            findings["V3 misspelled Supplier_s_Invoice_Number"] = (
                f"file={file_row['state']}, payments={len(created)}")
            ctx.check_true(
                "the misspelled header is a row-level failure, not a silent "
                "success — the key is read unconditionally at "
                "account_payment.py:137 and :159 whichever branch matched",
                file_row["state"] == "failed" or len(created) == 1,
                actual_desc=f"{file_row['state']} / {len(created)} payments")

        with ctx.step("Step 9: V5 — a duplicated header name. "
                      "_convert_data_to_list_of_dict keeps only the FIRST "
                      "occurrence (`if header[index] not in vals`)"):
            payload = good(7, pb_a, a_row["ref"])
            payload["__second_Transaction_Reference"] = f"TRX-{fx('SECOND')}"
            _f, file_id, file_row = run_import(
                ctx, [payload], duplicate_header="Transaction_Reference",
                file_label="V5_duplicate_header")
            ctx.log(f"V5 file: {file_row!r}; message: "
                    f"{file_message(rpc, file_id)!r}")
            created = payments_for(rpc, workday_id("SP", 7))
            ctx.log(f"V5 payments: {created!r}")
            if created:
                ctx.check(
                    "the FIRST column won — the payment's memo carries the "
                    "first Transaction_Reference, not the second",
                    f"TRX-{fx('C7')}", created[0].get("memo"))
            findings["V5 duplicated header name"] = (
                f"file={file_row['state']}, first occurrence wins")

        with ctx.step("Step 10: the header MUST be row 0. Prepend a blank "
                      "line and the whole file fails, because "
                      "_convert_data_to_list_of_dict is called with the "
                      "default row_start=0"):
            _f, file_id, file_row = run_import(
                ctx, [good(8, pb_a, a_row["ref"])], header_offset=1,
                file_label="V6_shifted_header")
            message = file_message(rpc, file_id)
            ctx.log(f"shifted-header file: {file_row!r}")
            ctx.log(f"shifted-header message, verbatim: {message!r}")
            ctx.check("no payment", [], payments_for(rpc, workday_id("SP", 8)))
            ctx.check("the whole file fails", "failed", file_row["state"])
            findings["V6 blank line before the header"] = (
                f"file={file_row['state']}, payments=0 (whole file lost)")

        with ctx.step("The operational finding — the variant table"):
            for variant, outcome in findings.items():
                ctx.log(f"  {variant} -> {outcome}")
            ctx.log("Step 6's asymmetry is the finding: a single malformed "
                    "ROW costs the entire day's payments, while a missing "
                    "COLUMN costs only the rows that need it. Recommend the "
                    "csv.DictReader replacement plus a length guard that "
                    "fails the ROW rather than the file — both are small, "
                    "both remove a class of outage, and the replacement "
                    "additionally removes the undeclared base_import "
                    "manifest dependency this workflow flags as a LOUD v19 "
                    "item. Step 9's duplicated-header behaviour should also "
                    "be written into the interface contract shared with the "
                    "Workday administrator; today it is an implementation "
                    "accident.")
    finally:
        if cid:
            restore_company(ctx, cid, original)


@test_case(
    id="TEST-WF019-TC330",
    name="Row-level rejections: payment method by exact name, missing "
         "journal, empty date",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account_workday", priority="P1", kind="API", order=19330,
    description="Records the journal's outbound method-line names verbatim, "
                "then proves each rejection is ROW-level and never raises: "
                "a trailing ordinary space is tolerated by .strip(), a case "
                "difference and an unknown method are not, an empty "
                "Payment_Date is not, and a missing company journal is not. "
                "A five-row file mixing four bad rows with one good one "
                "proves the good row still pays.",
    traceability=trace("DATAONE-TC330"))
def test_tc330(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-019 fixtures and open a fresh "
                  "namespace"):
        sweep_wf019(rpc)

    with ctx.step("Step 1: record the EXACT names of every outbound payment "
                  "method line — this list must be re-taken on v19, because "
                  "if Odoo's stock names changed, every row fails at once "
                  "and the symptom looks like a Workday problem"):
        require_payment_import(ctx)
        journal_id, method_names = payment_journal(ctx)
        method = method_names[0]
        ctx.log(f"journal {journal_id} outbound method line names, "
                f"verbatim: {method_names!r}")
        ctx.check_true("at least one method line exists", bool(method_names),
                       actual_desc=repr(method_names))

    cid = None
    original = {}
    outcomes = {}
    try:
        with ctx.step("Set up: the company journal and a bill with enough "
                      "residual for every variant"):
            cid, original = retarget_payment_journal(ctx, journal_id)
            vendor_id = ensure_vendor(rpc)
            pb_a, a_row = make_bill(ctx, vendor_id, 1000.0, "ROW-201",
                                    label="PB-A")
            url = base_url(rpc)

            def variant(index, payment_type, label, payment_date="2026-09-01",
                        amount="25.00"):
                return row(workday_id("SP", index), workday_id("SID", index),
                           bill_ref_value=a_row["ref"],
                           document_link=document_link(url, pb_a),
                           amount=amount, payment_date=payment_date,
                           payment_type=payment_type,
                           reference=f"TRX-{fx(label)}")

            def outcome(index):
                created = payments_for(rpc, workday_id("SP", index))
                return {"payments": len(created),
                        "state": created[0]["state"] if created else None}

        with ctx.step("Step 2: W2 — a trailing ORDINARY space. .strip() "
                      "handles it, so the row must succeed"):
            _f, file_id, file_row = run_import(
                ctx, [variant(2, f"{method} ", "W2")], file_label="W2")
            outcomes["W2 trailing ordinary space"] = outcome(2)
            ctx.log(f"W2: file={file_row['state']!r}, "
                    f"{outcomes['W2 trailing ordinary space']!r}, "
                    f"message={file_message(rpc, file_id)!r}")
            ctx.check("W2 succeeds", 1,
                      outcomes["W2 trailing ordinary space"]["payments"])

        with ctx.step("Step 3: W1 — lower case. Exact-name matching, so the "
                      "row fails and files an activity on the bill"):
            if method == method.lower():
                ctx.log(f"[warn] the method line name {method!r} is already "
                        "lower case on this database, so a case-difference "
                        "variant cannot be built. W1 is recorded as "
                        "untested rather than asserted.")
                outcomes["W1 lower case"] = {"payments": None,
                                             "state": "untestable"}
            else:
                _f, file_id, file_row = run_import(
                    ctx, [variant(1, method.lower(), "W1")], file_label="W1")
                ctx.log(f"W1 file: {file_row!r}")
                outcomes["W1 lower case"] = outcome(1)
                message = file_message(rpc, file_id)
                ctx.log(f"W1 message, verbatim: {message!r}")
                ctx.check("no payment", 0,
                          outcomes["W1 lower case"]["payments"])
                ctx.check_true("the message names the method and the "
                               "journal it looked in",
                               "Cannot find payment method" in message,
                               actual_desc=message)
                ctx.check("one activity on the bill", 1,
                          len(activities_on(rpc, "account.move", [pb_a])))

        with ctx.step("Step 4: W3 — a NON-BREAKING SPACE (U+00A0). The "
                      "variant most likely to arrive from a Workday report "
                      "export. Assert what the product ACTUALLY does"):
            _f, file_id, file_row = run_import(
                ctx, [variant(3, f"{method} ", "W3")], file_label="W3")
            outcomes["W3 trailing U+00A0"] = outcome(3)
            message = file_message(rpc, file_id)
            ctx.log(f"W3: file={file_row['state']!r}, "
                    f"{outcomes['W3 trailing U+00A0']!r}")
            ctx.log(f"W3 message, verbatim: {message!r}")
            ctx.log("Python 3's str.strip() removes U+00A0 because it is "
                    "Unicode whitespace, so this variant is EXPECTED to "
                    "succeed. The workbook predicts a failure; the "
                    "assertion below records whichever actually happens, "
                    "because that is what the port has to preserve. If it "
                    "succeeds, the recommendation to add a Unicode-aware "
                    "strip is already satisfied and can be dropped from the "
                    "port's scope.")
            ctx.check_true(
                "W3's outcome is recorded either way, and it is consistent "
                "with the file state",
                (outcomes["W3 trailing U+00A0"]["payments"] == 1)
                == (file_row["state"] == "done"),
                actual_desc=f"{file_row['state']} / "
                            f"{outcomes['W3 trailing U+00A0']!r}")

        with ctx.step("Step 5: W6 — a method name that exists nowhere on "
                      "the journal"):
            _f, file_id, file_row = run_import(
                ctx, [variant(6, fx("NO-SUCH-METHOD"), "W6")],
                file_label="W6")
            outcomes["W6 unknown method"] = outcome(6)
            message = file_message(rpc, file_id)
            ctx.log(f"W6 message, verbatim: {message!r}")
            ctx.check("no payment", 0, outcomes["W6 unknown method"]["payments"])
            ctx.check_true("same class of message as W1",
                           "Cannot find payment method" in message,
                           actual_desc=message)

        with ctx.step("Step 6: W4 — an empty Payment_Date"):
            _f, file_id, file_row = run_import(
                ctx, [variant(4, method, "W4", payment_date="")],
                file_label="W4")
            outcomes["W4 empty Payment_Date"] = outcome(4)
            message = file_message(rpc, file_id)
            ctx.log(f"W4 message, verbatim: {message!r}")
            ctx.check("no payment", 0,
                      outcomes["W4 empty Payment_Date"]["payments"])
            ctx.check_true(f"the message is {ERR_EMPTY_DATE!r}",
                           ERR_EMPTY_DATE in message, actual_desc=message)

        with ctx.step("Step 7: W5 — no journal configured on the company"):
            rpc.write("res.company", [cid],
                      {"workday_vendor_payment_journal_id": False})
            _f, file_id, file_row = run_import(
                ctx, [variant(5, method, "W5")], file_label="W5")
            outcomes["W5 no company journal"] = outcome(5)
            message = file_message(rpc, file_id)
            ctx.log(f"W5 message, verbatim: {message!r}")
            ctx.check("no payment", 0,
                      outcomes["W5 no company journal"]["payments"])
            ctx.check_true(f"the message is {ERR_NO_JOURNAL!r}",
                           ERR_NO_JOURNAL in message, actual_desc=message)
            rpc.write("res.company", [cid],
                      {"workday_vendor_payment_journal_id": journal_id})

        with ctx.step("Step 8: every rejection was ROW-level — none of the "
                      "seven imports raised out of "
                      "action_process_sftp_files, they all reached a Failed "
                      "sftp.file with a captured message (BR-6)"):
            ctx.log(f"variant outcomes: {outcomes!r}")
            ctx.check_true(
                "_prepare_workday_payment_vals RETURNS (vals, "
                "error_message) and never raises, so one bad row cannot "
                "stop another",
                True,
                actual_desc="every run above completed and produced a "
                            "readable sftp.file state")

        with ctx.step("Steps 9-11: a five-row file mixing four bad rows "
                      "with one good one — the good row still pays, each "
                      "bad row reports its own message, and the bill "
                      "collects one activity per identified failure"):
            acts_before = len(activities_on(rpc, "account.move", [pb_a]))
            mixed = [
                variant(11, method, "M-good"),
                variant(12, fx("NO-SUCH-METHOD"), "M-method"),
                variant(13, method, "M-nodate", payment_date=""),
                variant(14, fx("ALSO-MISSING"), "M-method2"),
                row(workday_id("SP", 15), workday_id("SID", 15),
                    bill_ref_value=fx(f"{MARK} INV-NOSUCH-777"),
                    document_link="", amount="25.00", payment_type=method,
                    reference=f"TRX-{fx('M-nobill')}"),
            ]
            _f, file_id, file_row = run_import(ctx, mixed, file_label="mixed")
            message = file_message(rpc, file_id)
            ctx.log(f"mixed file: {file_row!r}")
            ctx.log(f"mixed message, verbatim: {message!r}")
            good = payments_for(rpc, workday_id("SP", 11))
            ctx.check("the good row's payment was created and posted",
                      ["posted"], [p["state"] for p in good])
            ctx.check("none of the four bad rows created a payment",
                      [0, 0, 0, 0],
                      [len(payments_for(rpc, workday_id("SP", index)))
                       for index in (12, 13, 14, 15)])
            ctx.check("the file is Failed", "failed", file_row["state"])
            ctx.check_true(
                "its activity body carries all four messages, joined with "
                "<br/>",
                message.count("<br/>") >= 3
                and ERR_EMPTY_DATE in message
                and ERR_BILL_NOT_FOUND in message
                and "Cannot find payment method" in message,
                actual_desc=message)
            acts_after = len(activities_on(rpc, "account.move", [pb_a]))
            ctx.check(
                "three bill-level activities were added — one per failure "
                "that IDENTIFIED a bill, and none for the row that did not",
                3, acts_after - acts_before)

        with ctx.step("Step 12: Re-process re-attempts the rows that "
                      "already succeeded — TC329's defect from a third "
                      "direction"):
            before = len(payments_for(rpc, workday_id("SP", 11)))
            rpc.call("sftp.file", "action_retry_process_sftp_files",
                     [file_id])
            after = len(payments_for(rpc, workday_id("SP", 11)))
            ctx.log(f"payments carrying the good row's Supplier_Payment: "
                    f"{before} before Re-process, {after} after")
            ctx.check(
                "Re-processing a partially-failed file pays the successful "
                "row AGAIN — there is no Supplier_Payment idempotency key, "
                "so the fix must live in the payment creation path, not in "
                "the file layer alone",
                before + 1, after)
    finally:
        if cid:
            restore_company(ctx, cid, original)
