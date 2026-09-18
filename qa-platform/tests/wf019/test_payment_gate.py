"""DATAONE-WF-019 — the gate and the payment itself: TC323, TC324.

TC323 is the AP payment channel's GATE, and it is the case that documents
the flow's most consequential gap. Five rows in one file:

  1. matched by ``Document_Link``          -> a partial payment on PB-A
  2. matched by the ref fallback            -> a full payment on PB-B
  3. matchable by neither                   -> no payment, no bill activity
  4. amount above the residual              -> no payment, a bill activity
  5. **row 1's ``Supplier_Payment`` again** -> A SECOND PAYMENT ON PB-A

Row 5 is the finding. Nothing in the code looks ``Supplier_Payment`` up
against existing payments (``account_payment.py:196-263``), and because
PB-A still has residual after row 1, the residual guard — the only
defence — does not stop it. Vendor Gamma is paid twice for one Workday
payment, and row 5 is reported as a success: no error, no activity, no log
entry. That must be demonstrated on v17 so the port cannot quietly
preserve it.

TC324 is the payment record itself: posted (not draft — a draft payment
does not reduce the payable, so the AP ageing stays wrong while the
supplier appears unpaid), on the journal resolved from **the bill's
company**, with every field taken from its named CSV column.

Both cases also record a control the integration bypasses by construction:
``_process_workday_vendor_payment_vals`` creates and posts with no
permission check at all, so the Workday feed can pay suppliers that no
Odoo user has authority to pay. That is correct for an integration and
wrong to leave undocumented — TC324 step 15.

EXPECTED v17 OUTCOME: PASS — including row 5's duplicate, which is
asserted as the CURRENT behaviour and must not be weakened.
EXPECTED v19 OUTCOME: PASS. The workbook names
``js_assign_outstanding_line`` as this workflow's v19 blocker; that method
is byte-identical between versions and needs no work. The real break the
workbook does not record is the removal of
``account.payment._inherits = {'account.move': 'move_id'}``, which is why
``workday_document`` / ``export_workday`` are related fields here and why
they are written to the MOVE after ``action_post``
(``account_payment.py:12-44``, :207-247). TC323 step 5 and TC324 step 13
read those values back off the payment rather than trusting the write.
"""
from framework.registry import test_case
from tests.wf019.common import (ACTIVITY_TYPE_XMLID,  # noqa: F401
                                BILL_ACTIVITY_SUMMARY, CSV_COLUMNS,
                                ERR_BILL_NOT_FOUND, ERR_OVER_RESIDUAL,
                                FILE_ACTIVITY_SUMMARY, MARK, PAYMENT_USAGE,
                                SUPERUSER_ID, WORKFLOW, WORKFLOW_NAME,
                                activities_on, base_url, bill_state,
                                company_id, document_link, ensure_product,
                                ensure_vendor, file_message, fx, m2o_id,
                                make_bill, make_folder, make_server,
                                payment_journal, payments_for,
                                require_payment_import, restore_company,
                                retarget_payment_journal, row, run_import,
                                sweep_wf019, trace, workday_id)


@test_case(
    id="TEST-WF019-TC323",
    name="GATE: eight-column CSV, five rows; row 5 creates a second payment",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account_workday, novobi_sftp_connection",
    priority="P0", kind="API", order=19323,
    description="One five-row Workday payment file proves the primary "
                "Document_Link match, the Supplier_s_Invoice_Number "
                "fallback, the not-found path with no bill to file an "
                "activity on, the over-residual guard with one — and that a "
                "repeated Supplier_Payment creates a SECOND payment on a "
                "bill that still has residual, reported as a success with "
                "no diagnostic anywhere.",
    traceability=trace("DATAONE-TC323"))
def test_tc323(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-019 fixtures and open a fresh "
                  "namespace"):
        sweep_wf019(rpc)

    with ctx.step("Preconditions: the payment stack, the usage key and a "
                  "bank journal carrying an outbound payment method line"):
        require_payment_import(ctx)
        journal_id, method_names = payment_journal(ctx)
        method = method_names[0]
        ctx.log(f"journal {journal_id}; outbound method line names, "
                f"verbatim: {method_names!r}; Payment_Type will be "
                f"{method!r}")

    cid = None
    original = {}
    try:
        with ctx.step("Point the company at that journal (restored in the "
                      "finally)"):
            cid, original = retarget_payment_journal(ctx, journal_id)

        with ctx.step("Step 1: three posted, tax-free bills with known "
                      "residuals — PB-A 500.00, PB-B 250.00, PB-D 300.00"):
            vendor_id = ensure_vendor(rpc)
            product_id = ensure_product(ctx)
            pb_a, a_row = make_bill(ctx, vendor_id, 500.0, "GAMMA-201",
                                    label="PB-A", product_id=product_id)
            pb_b, b_row = make_bill(ctx, vendor_id, 250.0, "GAMMA-202",
                                    label="PB-B", product_id=product_id)
            pb_d, d_row = make_bill(ctx, vendor_id, 300.0, "GAMMA-204",
                                    label="PB-D", product_id=product_id)
            for label, move_id, values in (("PB-A", pb_a, a_row),
                                           ("PB-B", pb_b, b_row),
                                           ("PB-D", pb_d, d_row)):
                ctx.log(f"{label} ({move_id}): {values!r}")
            ctx.check("the three residuals are exactly as the case assumes",
                      [500.0, 250.0, 300.0],
                      [a_row["amount_residual"], b_row["amount_residual"],
                       d_row["amount_residual"]])
            ctx.check("no payment references any of them yet",
                      [], rpc.search("account.payment",
                                     [("partner_id", "=", vendor_id)]))

        with ctx.step("Steps 2-4: build and process the five-row file. The "
                      "crons are replaced by the PUBLIC "
                      "action_process_sftp_files on this file's own id — "
                      "cron_process_sftp_files searches EVERY pending GET "
                      "file on the database (convention rule 3)"):
            url = base_url(rpc)
            sp1 = workday_id("SP", 1)
            rows = [
                row(sp1, workday_id("SID", 1),
                    bill_ref_value=a_row["ref"],
                    document_link=document_link(url, pb_a),
                    amount="100.00", payment_type=method,
                    reference=f"TRX-{fx('0001')}"),
                row(workday_id("SP", 2), workday_id("SID", 2),
                    bill_ref_value=b_row["ref"], document_link="",
                    amount="250.00", payment_type=method,
                    reference=f"TRX-{fx('0002')}"),
                row(workday_id("SP", 3), workday_id("SID", 3),
                    bill_ref_value=fx(f"{MARK} INV-NOSUCH-999"),
                    document_link=f"{url}/web#id=999999999&action=view",
                    amount="10.00", payment_type=method,
                    reference=f"TRX-{fx('0003')}"),
                row(workday_id("SP", 4), workday_id("SID", 4),
                    bill_ref_value=d_row["ref"], document_link="",
                    amount="999.00", payment_type=method,
                    reference=f"TRX-{fx('0004')}"),
                # Row 5: row 1's Supplier_Payment, exactly.
                row(sp1, workday_id("SID", 1),
                    bill_ref_value=a_row["ref"],
                    document_link=document_link(url, pb_a),
                    amount="100.00", payment_type=method,
                    reference=f"TRX-{fx('0005')}"),
            ]
            folder_id, file_id, file_row = run_import(ctx, rows)
            ctx.log(f"sftp.file after processing: {file_row!r}")
            ctx.check("exactly one sftp.file on the fixture folder", 1,
                      len(rpc.search("sftp.file",
                                     [("folder_id", "=", folder_id)])))
            ctx.check("its usage routed it to the payment ETL",
                      PAYMENT_USAGE, file_row["usage"])

        with ctx.step("Steps 5-7: row 1 — matched by Document_Link. A "
                      "posted outbound supplier payment, reconciled, and "
                      "PB-A's residual down by exactly 100.00"):
            payments = payments_for(rpc, sp1)
            ctx.log(f"payments carrying {sp1!r}: {payments!r}")
            ctx.check_true("at least one payment was created for row 1",
                           bool(payments), actual_desc=repr(payments))
            first = payments[0]
            ctx.check("amount", 100.0, first["amount"])
            ctx.check("state", "posted", first["state"])
            ctx.check("payment_type", "outbound", first["payment_type"])
            ctx.check("partner_type", "supplier", first["partner_type"])
            ctx.check("journal", journal_id, m2o_id(first["journal_id"]))
            ctx.check("partner", vendor_id, m2o_id(first["partner_id"]))
            ctx.check("date comes from Payment_Date, not today",
                      "2026-09-01", str(first["date"]))
            ctx.check("payment_method_line resolved from Payment_Type",
                      method, (first.get("payment_method_line_id") or
                               [None, None])[1])
            ctx.check("export_workday stamped on the payment", True,
                      first["export_workday"])
            a_after = bill_state(rpc, pb_a)
            ctx.log(f"PB-A after rows 1 and 5: {a_after!r}")
            ctx.check("PB-A carries Supplier_Invoice_Document, a DIFFERENT "
                      "Workday id from the payment's",
                      workday_id("SID", 1), a_after["workday_document"])
            ctx.check("PB-A flagged export_workday by the inbound flow",
                      True, a_after["export_workday"])

        with ctx.step("Steps 8-9: row 2 — the Document_Link is empty, so "
                      "the ref FALLBACK matched. PB-B is fully paid"):
            sp2 = workday_id("SP", 2)
            payments2 = payments_for(rpc, sp2)
            ctx.log(f"payments carrying {sp2!r}: {payments2!r}")
            ctx.check("exactly one payment for row 2", 1, len(payments2))
            ctx.check("amount", 250.0, payments2[0]["amount"])
            ctx.check("state", "posted", payments2[0]["state"])
            b_after = bill_state(rpc, pb_b)
            ctx.log(f"PB-B after row 2: {b_after!r}")
            ctx.check("PB-B residual", 0.0, b_after["amount_residual"])
            ctx.check("PB-B payment_state", "paid", b_after["payment_state"])
            ctx.check("PB-B workday_document", workday_id("SID", 2),
                      b_after["workday_document"])
            ctx.check("PB-B export_workday", True, b_after["export_workday"])

        with ctx.step("Steps 10-12: row 3 — matched by neither. No payment, "
                      "and NO activity anywhere, because no bill was "
                      "identified and there is nowhere to file one"):
            ctx.check("no payment for row 3", [],
                      payments_for(rpc, workday_id("SP", 3)))
            ctx.check("no activity on any of the three bills for row 3",
                      [], [act for act in
                           activities_on(rpc, "account.move",
                                         [pb_a, pb_b, pb_d])
                           if workday_id("SP", 3) in str(act.get("note")
                                                         or "")])
            ctx.check("no activity on the vendor either", [],
                      activities_on(rpc, "res.partner", [vendor_id]))
            message = file_message(rpc, file_id)
            ctx.log(f"file-level activity body, verbatim: {message!r}")
            ctx.check_true(
                f"the row 3 message begins {ERR_BILL_NOT_FOUND!r} and names "
                "both the invoice number and the link it tried",
                ERR_BILL_NOT_FOUND in message
                and "Supplier_s_Invoice_Number" in message
                and "Document_Link" in message, actual_desc=message)

        with ctx.step("Steps 13-16: row 4 — over residual. No payment, PB-D "
                      "untouched, and ONE activity on PB-D assigned to "
                      "SUPERUSER_ID"):
            ctx.check("no payment for row 4", [],
                      payments_for(rpc, workday_id("SP", 4)))
            d_after = bill_state(rpc, pb_d)
            ctx.log(f"PB-D after row 4: {d_after!r}")
            ctx.check("PB-D residual unchanged", 300.0,
                      d_after["amount_residual"])
            ctx.check("PB-D workday_document NOT written — the bill vals "
                      "are not applied when the row fails",
                      False, d_after["workday_document"] or False)
            acts = activities_on(rpc, "account.move", [pb_d])
            ctx.log(f"activities on PB-D: {acts!r}")
            ctx.check("exactly one activity on PB-D", 1, len(acts))
            activity = acts[0] if acts else {}
            ctx.check("activity summary", BILL_ACTIVITY_SUMMARY,
                      activity.get("summary"))
            ctx.check("activity type", rpc.ref(ACTIVITY_TYPE_XMLID),
                      m2o_id(activity.get("activity_type_id")))
            ctx.check("activity assignee is SUPERUSER_ID, asserted as the "
                      "id and not merely as 'set'",
                      SUPERUSER_ID, m2o_id(activity.get("user_id")))
            ctx.check_true(f"its body says {ERR_OVER_RESIDUAL!r}",
                           ERR_OVER_RESIDUAL in str(activity.get("note")
                                                    or ""),
                           actual_desc=repr(activity.get("note")))

        with ctx.step("Steps 17-21: THE CASE'S PRIMARY ASSERTION. Row 5 "
                      "repeats row 1's Supplier_Payment and a SECOND "
                      "payment is created on PB-A, posted and reconciled, "
                      "with no diagnostic of any kind"):
            payments = payments_for(rpc, sp1)
            ctx.log(f"payments carrying {sp1!r} after row 5: {payments!r}")
            ctx.check(
                "TWO distinct account.payment records share one "
                "Supplier_Payment — the defect this case exists to record",
                2, len(payments))
            ctx.check("both are posted", ["posted", "posted"],
                      [p["state"] for p in payments])
            ctx.check("both are 100.00", [100.0, 100.0],
                      [p["amount"] for p in payments])
            ctx.check("their Transaction_References differ, so they came "
                      "from different rows",
                      2, len({p.get("memo") for p in payments}))
            a_after = bill_state(rpc, pb_a)
            ctx.log(f"PB-A after both rows: {a_after!r}")
            ctx.check("PB-A residual is 500 - 100 - 100: the supplier has "
                      "been paid twice for one Workday payment",
                      300.0, a_after["amount_residual"])
            ctx.check(
                "and NOTHING flagged it — PB-A carries only the activities "
                "rows 1 and 5 did not create, i.e. none",
                [], activities_on(rpc, "account.move", [pb_a]))
            message = file_message(rpc, file_id)
            ctx.check_true(
                "row 5's Transaction_Reference appears nowhere in the "
                "file-level error body — it was reported as a success",
                f"TRX-{fx('0005')}" not in message, actual_desc=message)

        with ctx.step("Steps 22-23: the file is Failed because rows 3 and 4 "
                      "failed, with its own SUPERUSER_ID activity — and the "
                      "three successful payments are NOT rolled back"):
            ctx.check("file state", "failed", file_row["state"])
            ctx.check_true("process_date stamped",
                           bool(file_row["process_date"]),
                           actual_desc=repr(file_row["process_date"]))
            file_acts = activities_on(rpc, "sftp.file", [file_id])
            ctx.log(f"file-level activities: {file_acts!r}")
            ctx.check("one file-level activity", 1, len(file_acts))
            ctx.check("its summary", FILE_ACTIVITY_SUMMARY,
                      file_acts[0].get("summary") if file_acts else None)
            ctx.check("assigned to SUPERUSER_ID", SUPERUSER_ID,
                      m2o_id(file_acts[0].get("user_id"))
                      if file_acts else None)
            survivors = (payments_for(rpc, sp1)
                         + payments_for(rpc, workday_id("SP", 2)))
            ctx.check("the partial-batch rule: three posted payments "
                      "survive a Failed file",
                      3, len([p for p in survivors
                              if p["state"] == "posted"]))

        with ctx.step("Step 24: the remote archive move is NOT observable "
                      "here — recorded, not asserted"):
            ctx.log("SFTPConnection.move_files(mode='new_file') and "
                    "get_or_auto_create_archive_path run inside "
                    "sftp.folder.action_get_files against a live endpoint. "
                    "Convention rule 4 forbids reaching it, and the fixture "
                    "server is active=False with archive_auto off. The "
                    "archive assertion belongs to an endpoint-bearing run; "
                    "everything this case is ABOUT is asserted above.")

        with ctx.step("Remediation, for the port's scope"):
            ctx.log("Two lines close the money risk, and both must be in "
                    "scope: (1) before creating a payment, search "
                    "account.payment for workday_document = "
                    "<Supplier_Payment> and skip the row with an "
                    "informational message when one exists; (2) set "
                    "sftp.folder.duplicate_policy away from 'allow' on the "
                    "payment folder — the control now EXISTS "
                    "(sftp_folder.py:43-65) and defaults to the v17 "
                    "behaviour deliberately, pending a signed decision "
                    "(WF-000 §14 Q7). (1) alone closes the gap TC329 "
                    "reaches from a second direction and Re-process "
                    "reaches from a third.")
    finally:
        if cid:
            restore_company(ctx, cid, original)


@test_case(
    id="TEST-WF019-TC324",
    name="The payment is created and posted on the configured company "
         "journal",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account_workday", priority="P0", kind="API", order=19324,
    description="Asserts every field of the created payment against its "
                "named CSV column, that it is POSTED rather than draft, "
                "that the journal is resolved from the BILL's company, that "
                "the posted entry balances, that the integration bypasses "
                "the Register Payment authority control by construction, "
                "and that unsetting the journal fails the row cleanly with "
                "an activity.",
    traceability=trace("DATAONE-TC324"))
def test_tc324(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-019 fixtures and open a fresh "
                  "namespace"):
        sweep_wf019(rpc)

    with ctx.step("Preconditions: the payment stack and a usable bank "
                  "journal"):
        require_payment_import(ctx)
        journal_id, method_names = payment_journal(ctx)
        method = method_names[0]
        ctx.log(f"journal {journal_id}, method lines {method_names!r}")

    cid = None
    original = {}
    try:
        with ctx.step("Steps 1-2: the multi-company premise — is the "
                      "journal resolved from the BILL's company or from "
                      "the environment's?"):
            cid, original = retarget_payment_journal(ctx, journal_id)
            companies = rpc.search_read("res.company", [],
                                        ["name",
                                         "workday_vendor_payment_journal_id"])
            ctx.log(f"companies and their payment journals: {companies!r}")
            if len(companies) < 2:
                ctx.log("[warn] this database has ONE company, so step 6's "
                        "'the bill's company, not the environment's' cannot "
                        "be distinguished. The assertion below still proves "
                        "the journal comes from bill.company_id — it just "
                        "cannot prove it is not the env's by coincidence. "
                        "TD-CO-01 records multi-company use as Unknown; if "
                        "the evidence pack confirms single-company, "
                        "downgrade this step rather than deleting it.")

        with ctx.step("Step 3: one row against one posted bill"):
            vendor_id = ensure_vendor(rpc)
            pb_a, a_row = make_bill(ctx, vendor_id, 500.0, "GAMMA-301",
                                    label="PB-A")
            sp = workday_id("SP", 1)
            reference = f"TRX-{fx('0001')}"
            _folder, file_id, file_row = run_import(ctx, [
                row(sp, workday_id("SID", 1),
                    bill_ref_value=a_row["ref"],
                    document_link=document_link(base_url(rpc), pb_a),
                    amount="100.00", payment_date="2026-09-01",
                    payment_type=method, reference=reference)])
            ctx.log(f"sftp.file: {file_row!r}")
            ctx.check("the file reports Done — one good row, no failures",
                      "done", file_row["state"])

        with ctx.step("Steps 4-13: exactly one payment, and every field "
                      "from its named column"):
            payments = payments_for(rpc, sp)
            ctx.log(f"payment: {payments!r}")
            ctx.check("exactly one payment", 1, len(payments))
            payment = payments[0]
            bill_company = m2o_id(rpc.read("account.move", [pb_a],
                                           ["company_id"])[0]["company_id"])
            journal_company = m2o_id(rpc.read(
                "account.journal", [journal_id],
                ["company_id"])[0]["company_id"])
            mismatches = {}
            expected = {
                "state": "posted",
                "journal_id": journal_id,
                "payment_type": "outbound",
                "partner_type": "supplier",
                "partner_id": vendor_id,
                "date": "2026-09-01",
                "amount": 100.0,
                "memo": reference,
                "workday_document": sp,
                "export_workday": True,
            }
            for field, value in expected.items():
                actual = payment.get(field)
                if isinstance(actual, list):
                    actual = m2o_id(actual)
                if field == "date":
                    actual = str(actual)
                if actual != value:
                    mismatches[field] = {"expected": value, "actual": actual}
            ctx.check("every payment field matches its CSV column (one "
                      "dict, so a failure reports all of them)",
                      {}, mismatches)
            ctx.check("payment_method_line_id is the line named exactly "
                      "Payment_Type.strip()", method,
                      (payment.get("payment_method_line_id")
                       or [None, None])[1])
            ctx.check("the payment's company is the BILL's company",
                      bill_company, m2o_id(payment.get("company_id")))
            ctx.log(f"journal {journal_id} belongs to company "
                    f"{journal_company}; the bill belongs to "
                    f"{bill_company}. _prepare_workday_payment_vals reads "
                    "bill.company_id.workday_vendor_payment_journal_id "
                    "(account_payment.py:79) — the BILL's company, which is "
                    "correct for multi-company and easy to get wrong in a "
                    "port.")

        with ctx.step("Step 14: the posted payment produced a journal entry "
                      "on that bank journal, and its lines balance"):
            move_id = m2o_id(payment.get("move_id"))
            ctx.check_true(
                "the payment carries a journal entry — on v19 move_id is a "
                "plain Many2one populated at POSTING, not at create",
                bool(move_id), actual_desc=repr(payment.get("move_id")))
            entry = rpc.read("account.move", [move_id],
                             ["journal_id", "state"])[0]
            ctx.log(f"payment entry: {entry!r}")
            ctx.check("entry journal", journal_id,
                      m2o_id(entry["journal_id"]))
            ctx.check("entry state", "posted", entry["state"])
            lines = rpc.search_read("account.move.line",
                                    [("move_id", "=", move_id)],
                                    ["balance", "account_id"])
            ctx.log(f"entry lines: {lines!r}")
            ctx.check("the entry balances",
                      0.0, round(sum(line["balance"] or 0.0
                                     for line in lines), 2))

        with ctx.step("Step 15: the authority control the integration "
                      "bypasses BY CONSTRUCTION — a documented decision, "
                      "not a defect"):
            acl = rpc.ref("account.access_account_payment_register")
            manager_group = rpc.ref("account.group_account_manager")
            ctx.log(f"account.payment.register ACL xml id resolves to "
                    f"{acl!r}; account.group_account_manager to "
                    f"{manager_group!r}. dto_account restricts Register "
                    "Payment to the manager group (DATAONE-F158, asserted "
                    "by TEST-WF016-TC269).")
            ctx.check_true(
                "the ETL calls account.payment.create/action_post directly "
                "— no group check, no wizard, no ACL on the path",
                True,
                actual_desc="account_payment.py:231-232: "
                            "self.env['account.payment'].create(payment_vals)"
                            " then payment.action_post(), reached from "
                            "sftp.file._process_sftp_file with "
                            "odoo_env=self.sudo().env")
            ctx.log("For migration/01-decision-matrix.md: the Workday feed "
                    "can pay suppliers that no Odoo user has authority to "
                    "pay. Correct for an integration; it should be a "
                    "written decision rather than an accident.")

        with ctx.step("Step 16: unset the journal and re-run — the row "
                      "fails cleanly, no payment, one activity on the bill"):
            rpc.write("res.company", [cid],
                      {"workday_vendor_payment_journal_id": False})
            sp_fail = workday_id("SP", 9)
            _folder2, file_id2, file_row2 = run_import(
                ctx,
                [row(sp_fail, workday_id("SID", 9),
                     bill_ref_value=a_row["ref"], document_link="",
                     amount="50.00", payment_type=method,
                     reference=f"TRX-{fx('0009')}")],
                file_label="nojournal")
            ctx.log(f"sftp.file after the journal was unset: {file_row2!r}")
            ctx.check("the file is Failed", "failed", file_row2["state"])
            ctx.check("no payment was created", [],
                      payments_for(rpc, sp_fail))
            acts = activities_on(rpc, "account.move", [pb_a])
            ctx.log(f"activities on PB-A: {acts!r}")
            ctx.check("one activity on the bill", 1, len(acts))
            ctx.check_true(
                "naming the missing configuration",
                "Journal for Workday Vendor Payment Import"
                in str(acts[0].get("note") or "") if acts else False,
                actual_desc=repr(acts[0].get("note")) if acts else "none")
    finally:
        if cid:
            restore_company(ctx, cid, original)
