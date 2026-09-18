"""DATAONE-WF-018 — closing the loop: TC326.

Shared with DATAONE-WF-019; owned here, because WF-018 has the lower build
order (21 against 22). WF-019 references this tc_id and must not
re-implement it (AUTOMATION_CONVENTIONS.md, "Shared test cases").

Two Workday identifiers come back on every paid bill and they are
different things:

* ``Supplier_Payment``          -> ``account.payment.workday_document``
* ``Supplier_Invoice_Document`` -> ``account.move.workday_document``

They are how an auditor takes a Workday payment id, finds it in Odoo, and
walks back through the reconciliation to the bill and forward to the
``sftp.file`` that created it. Conflating them is the exact shape of a
copy-paste error in a port, and step 6 is written to fail on it.

Why this is implementable without an endpoint
---------------------------------------------
The payment extractor reads the ``sftp.file``'s *attachment*, not SFTP
(``workday_vendor_payment_extractor.py:15-22``), so the whole ETL runs off
an ``ir.attachment`` and the public ``sftp.file.action_process_sftp_files``.
SFTP is only involved in *fetching* the file onto that attachment. The
fixture server is ``active=False`` on an unroutable host and no test here
calls any connection method — convention rule 4 holds.

The semantic conflation this case exists to surface
---------------------------------------------------
``export_workday`` on a BILL means "sent to Workday by WF-018". The
inbound flow re-writes it to ``True``
(``account_payment.py:180-183``), so it also comes to mean "a payment for
it came back". Steps 11 and 12 construct the consequence deliberately: a
posted bill that was NEVER exported, referenced by a payment row, is
flagged by the import and thereby **permanently excluded from WF-018's
export domain without ever having been exported**. Workday can raise a
payable by other means, so this is reachable. The clean fix is a separate
``workday_paid`` boolean; that is a decision, not a test outcome, so the
case records it rather than judging it.

EXPECTED v17 OUTCOME: PASS.
EXPECTED v19 OUTCOME: PASS. The v19 hazard is not the workbook's
``js_assign_outstanding_line`` — that method is byte-identical between
versions. It is that v17's ``account.payment._inherits = {'account.move':
'move_id'}`` is GONE in v19, so ``workday_document`` and
``export_workday`` had to be re-declared as related fields on
``account.payment``, and the values must be written to the MOVE after the
payment posts (``account_payment.py:207-247``). Step 1 and step 10 are
what prove that landing, and they read the value back off the payment
rather than trusting the write.
"""
from framework.registry import test_case
from tests.wf018.common import (MARK, VENDOR_PAYMENT_USAGE,  # noqa: F401
                                WORKFLOW, WORKFLOW_NAME,
                                VENDOR_BILL_EXPORT_DOMAIN, activities_on,
                                ensure_product, ensure_vendor, fx,
                                latest_workbook, m2o_id, make_bill,
                                make_post_folder, make_post_server,
                                payment_journal, produced_files,
                                require_payment_import,
                                require_vendor_bill_usage,
                                require_workday_export, restore_company,
                                retarget_company, retarget_payment_journal,
                                run_export, run_payment_import, sweep_wf018,
                                template_id, trace)


def _row(bill_id, bill_ref_value, amount, supplier_payment,
         invoice_document, method_name, base_url="",
         payment_date="2026-02-01", reference=None, use_link=True):
    """One eight-column Workday payment row."""
    return {
        "Supplier_Payment": supplier_payment,
        "Supplier_Invoice_Document": invoice_document,
        "Supplier_s_Invoice_Number": bill_ref_value,
        "Document_Link": (f"{base_url}/web#id={bill_id}&model=account.move"
                          f"&view_type=form") if use_link else "",
        "Payment_Amount": amount,
        "Payment_Date": payment_date,
        "Payment_Type": method_name,
        "Transaction_Reference": reference or f"{supplier_payment}-TXN",
    }


@test_case(
    id="TEST-WF018-TC326",
    name="workday_document and export_workday stamped on both the payment "
         "and the bill",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account_workday", priority="P0", kind="DATA", order=18326,
    description="Imports two Workday payment rows against two exported "
                "bills and asserts the four stamps are the RIGHT four — the "
                "payment carries Supplier_Payment, the bill carries "
                "Supplier_Invoice_Document, and the two never match; walks "
                "the audit trail in both directions; proves nothing is "
                "stamped on a failed row; and constructs the semantic "
                "conflation that silently removes a never-exported bill "
                "from WF-018's domain.",
    traceability=trace("DATAONE-TC326", user_story="shared with "
                                                   "DATAONE-WF-019"))
def test_tc326(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-018 fixtures and open a fresh "
                  "namespace"):
        sweep_wf018(rpc)

    with ctx.step("Preconditions: the export stack, both usage keys, and a "
                  "bank journal carrying an outbound payment method line"):
        require_workday_export(ctx)
        require_vendor_bill_usage(ctx)
        require_payment_import(ctx)
        journal_id, method_name = payment_journal(ctx)
        ctx.log(f"payment journal {journal_id}, Payment_Type will be "
                f"{method_name!r}")

    cid = payment_cid = None
    original = {}
    payment_original = {}
    try:
        with ctx.step("Set up the export target and the payment journal, "
                      "both restored in the finally"):
            tmpl_id = template_id(ctx)
            server_id = make_post_server(rpc)
            folder_id = make_post_folder(rpc, server_id)
            cid, original = retarget_company(ctx, folder_id,
                                             template_ref=tmpl_id)
            payment_cid, payment_original = retarget_payment_journal(
                ctx, journal_id)
            base_url_rows = rpc.search_read(
                "ir.config_parameter", [("key", "=", "web.base.url")],
                ["value"], limit=1)
            base_url = base_url_rows[0]["value"] if base_url_rows else ""

        with ctx.step("Precondition (TC325's state): PB-A and PB-B posted, "
                      "exported by WF-018, each with a known residual"):
            vendor_id = ensure_vendor(rpc)
            product_id = ensure_product(ctx)
            line = {"product_id": product_id, "quantity": 1.0,
                    "price_unit": 100.0}
            pb_a = make_bill(ctx, vendor_id, [line], "GAMMA-201",
                             label="PB-A")
            pb_b = make_bill(ctx, vendor_id, [line], "GAMMA-202",
                             label="PB-B")
            run_export(ctx, [pb_a, pb_b], mark_exported=True)
            bills = {row["id"]: row for row in rpc.read(
                "account.move", [pb_a, pb_b],
                ["ref", "amount_residual", "amount_total", "export_workday",
                 "workday_document"])}
            for move_id, row in bills.items():
                ctx.log(f"bill {move_id}: {row!r}")
            ctx.check("both bills exported by WF-018 before any payment "
                      "arrives", [True, True],
                      [bills[pb_a]["export_workday"],
                       bills[pb_b]["export_workday"]])
            ctx.check("neither bill carries a Workday document yet",
                      [False, False],
                      [bills[pb_a]["workday_document"] or False,
                       bills[pb_b]["workday_document"] or False])

        with ctx.step("Import the payment file: row 1 matched by "
                      "Document_Link (partial), row 2 matched by the "
                      "Supplier_s_Invoice_Number fallback (full), row 4 "
                      "unmatchable"):
            rows = [
                _row(pb_a, bills[pb_a]["ref"], 40.0, "SP-0001", "SID-0001",
                     method_name, base_url=base_url, use_link=True),
                _row(pb_b, bills[pb_b]["ref"],
                     bills[pb_b]["amount_residual"], "SP-0002", "SID-0002",
                     method_name, base_url="", use_link=False),
                _row(0, fx(f"{MARK} NO-SUCH-BILL"), 10.0, "SP-0004",
                     "SID-0004", method_name, base_url="", use_link=False),
            ]
            _folder, file_id, file_row = run_payment_import(ctx, rows)
            ctx.log(f"sftp.file after processing: {file_row!r}")
            ctx.check("the file reports Failed, because row 3 could not be "
                      "matched — a per-row failure fails the WHOLE file",
                      "failed", file_row["state"])

        with ctx.step("Steps 1-2: the payment from row 1 carries "
                      "Supplier_Payment, not Supplier_Invoice_Document, and "
                      "is flagged"):
            payments = rpc.search_read(
                "account.payment",
                [("workday_document", "in", ["SP-0001", "SP-0002"])],
                ["workday_document", "export_workday", "amount", "state",
                 "partner_id", "move_id", "memo"], order="workday_document")
            ctx.log(f"payments created by the import: {payments!r}")
            ctx.check("two payments created", 2, len(payments))
            by_doc = {row["workday_document"]: row for row in payments}
            ctx.check("row 1's payment carries SP-0001", "SP-0001",
                      by_doc.get("SP-0001", {}).get("workday_document"))
            ctx.check("row 1's payment is flagged export_workday", True,
                      by_doc.get("SP-0001", {}).get("export_workday"))
            ctx.check("row 1's payment is posted", "posted",
                      by_doc.get("SP-0001", {}).get("state"))

        with ctx.step("Steps 3-5: the BILLS carry Supplier_Invoice_Document "
                      "— a DIFFERENT Workday identifier — and are flagged"):
            after = {row["id"]: row for row in rpc.read(
                "account.move", [pb_a, pb_b],
                ["workday_document", "export_workday", "amount_residual",
                 "payment_state"])}
            for move_id, row in after.items():
                ctx.log(f"bill {move_id} after the import: {row!r}")
            ctx.check("PB-A / PB-B workday_document",
                      ["SID-0001", "SID-0002"],
                      [after[pb_a]["workday_document"],
                       after[pb_b]["workday_document"]])
            ctx.check("both bills flagged export_workday", [True, True],
                      [after[pb_a]["export_workday"],
                       after[pb_b]["export_workday"]])
            ctx.check_true(
                "PB-A is partially paid and PB-B is fully paid — the "
                "reconciliation actually ran",
                after[pb_a]["amount_residual"] > 0
                and after[pb_b]["amount_residual"] == 0,
                actual_desc=repr({i: after[i]["amount_residual"]
                                  for i in (pb_a, pb_b)}))

        with ctx.step("Step 6: the two identifiers are NOT conflated — the "
                      "assertion a copy-paste error in the port would fail"):
            pairs = {
                "SP-0001": (by_doc["SP-0001"]["workday_document"],
                            after[pb_a]["workday_document"]),
                "SP-0002": (by_doc["SP-0002"]["workday_document"],
                            after[pb_b]["workday_document"]),
            }
            ctx.log(f"(payment.workday_document, bill.workday_document) per "
                    f"row: {pairs!r}")
            ctx.check(
                "each payment's Workday document differs from its bill's",
                [], [key for key, (p, b) in pairs.items() if p == b])

        with ctx.step("Step 7: the forward audit traversal — SP-0001 -> "
                      "payment -> reconciliation -> PB-A -> PB-A.ref -> what "
                      "WF-018 wrote into column BD"):
            payment = by_doc["SP-0001"]
            move_id = m2o_id(payment["move_id"])
            ctx.check_true("the payment has a journal entry (v19 populates "
                           "move_id only at posting)", bool(move_id),
                           actual_desc=repr(payment["move_id"]))
            reconciled_bills = rpc.search(
                "account.move.line",
                [("move_id", "=", move_id),
                 ("matched_debit_ids.debit_move_id.move_id", "=", pb_a)])
            reconciled_bills += rpc.search(
                "account.move.line",
                [("move_id", "=", move_id),
                 ("matched_credit_ids.credit_move_id.move_id", "=", pb_a)])
            ctx.log(f"payment lines reconciled against PB-A: "
                    f"{reconciled_bills!r}")
            ctx.check_true(
                "the payment is reconciled against PB-A, so the traversal "
                "payment -> bill resolves",
                bool(reconciled_bills), actual_desc=repr(reconciled_bills))
            _file_row, sheet, _raw = latest_workbook(ctx, folder_id)
            bd_values = [sheet[f"BD{index}"].value
                         for index in range(6, 20)
                         if sheet[f"B{index}"].value == pb_a]
            ctx.log(f"column BD for PB-A in the exported workbook: "
                    f"{bd_values!r}")
            ctx.check("PB-A.ref, the CSV's Supplier_s_Invoice_Number and "
                      "column BD are the same string",
                      [bills[pb_a]["ref"]], list(set(bd_values)))

        with ctx.step("Step 8: the reverse traversal — from the sftp.file "
                      "back to the payment, the bill and the Workday ids"):
            payment_file = rpc.read("sftp.file", [file_id],
                                    ["ref", "name", "attachment_id",
                                     "usage", "state"])[0]
            ctx.log(f"inbound sftp.file: {payment_file!r}")
            ctx.check("the inbound file carries the payment usage key",
                      VENDOR_PAYMENT_USAGE, payment_file["usage"])
            ctx.check_true(
                "its attachment is the CSV that produced the payments",
                bool(m2o_id(payment_file["attachment_id"])),
                actual_desc=repr(payment_file["attachment_id"]))
            ctx.log("Gap to record, not to assert: sftp.file carries NO "
                    "res_model/res_id back-reference for the payment usage "
                    "— the WorkdayVendorPaymentLoader never stamps one "
                    "(workday_vendor_payment_loader.py:10-21), unlike the "
                    "outbound loader which stamps the template "
                    "(workday_loader.py:129-132). The reverse traversal is "
                    "therefore by FILE CONTENT, not by a link.")

        with ctx.step("Step 9: nothing was stamped by the failed row, and "
                      "it produced no orphan payment"):
            orphans = rpc.search(
                "account.payment", [("workday_document", "=", "SP-0004")])
            ctx.check("the unmatchable row created no payment", [], orphans)
            ctx.check("no bill carries SID-0004", [],
                      rpc.search("account.move",
                                 [("workday_document", "=", "SID-0004")]))

        with ctx.step("Step 10: the stamps are written AFTER the payment "
                      "posts and reconciles — induce a failure and assert "
                      "the bill vals were not written"):
            pb_c = make_bill(ctx, vendor_id, [line], "GAMMA-203",
                             label="PB-C")
            run_export(ctx, [pb_c], mark_exported=True)
            residual = rpc.read("account.move", [pb_c],
                                ["amount_residual", "ref",
                                 "export_workday"])[0]
            over = _row(pb_c, residual["ref"],
                        residual["amount_residual"] + 500.0, "SP-0005",
                        "SID-0005", method_name, base_url="",
                        use_link=False)
            run_payment_import(ctx, [over], file_label="overpay")
            pb_c_after = rpc.read("account.move", [pb_c],
                                  ["workday_document", "amount_residual"])[0]
            ctx.log(f"PB-C after the over-amount row: {pb_c_after!r}")
            ctx.check("the residual guard fired BEFORE any stamp — the bill "
                      "carries no Workday document",
                      False, pb_c_after["workday_document"] or False)
            ctx.check("and no payment was created", [],
                      rpc.search("account.payment",
                                 [("workday_document", "=", "SP-0005")]))
            acts = activities_on(rpc, "account.move", [pb_c])
            ctx.log(f"activities on PB-C: {acts!r}")
            ctx.check_true("the rejected row filed an activity on the bill",
                           len(acts) == 1, actual_desc=repr(acts))

        with ctx.step("Steps 11-12: THE SEMANTIC CONFLATION. A posted bill "
                      "that was NEVER exported, paid from Workday, is "
                      "flagged by the INBOUND flow and thereby removed from "
                      "WF-018's export domain forever"):
            pb_n = make_bill(ctx, vendor_id, [line], "GAMMA-204",
                             label="PB-N")
            before_n = rpc.read("account.move", [pb_n],
                                ["export_workday", "export_workday_sync",
                                 "amount_residual", "ref"])[0]
            ctx.log(f"PB-N before the payment: {before_n!r}")
            ctx.check("PB-N was never exported", False,
                      before_n["export_workday"])
            ctx.check("and it IS in WF-018's export domain", [pb_n],
                      rpc.search("account.move",
                                 list(VENDOR_BILL_EXPORT_DOMAIN)
                                 + [("id", "=", pb_n)]))
            never_exported = _row(
                pb_n, before_n["ref"], before_n["amount_residual"],
                "SP-0006", "SID-0006", method_name, base_url="",
                use_link=False)
            run_payment_import(ctx, [never_exported],
                               file_label="never_exported")
            after_n = rpc.read("account.move", [pb_n],
                               ["export_workday", "export_workday_sync",
                                "workday_document"])[0]
            ctx.log(f"PB-N after the payment: {after_n!r}")
            ctx.check("the INBOUND flow set export_workday on a bill that "
                      "was never exported", True, after_n["export_workday"])
            ctx.check(
                "and export_workday_sync was NOT set — so the flag now says "
                "'exported' while the timestamp says it never was",
                False, after_n["export_workday_sync"] or False)
            ctx.check(
                "CONSEQUENCE: PB-N has left WF-018's export domain "
                "permanently, without ever having been exported",
                [], rpc.search("account.move",
                               list(VENDOR_BILL_EXPORT_DOMAIN)
                               + [("id", "=", pb_n)]))
            ctx.log("For migration/01-decision-matrix.md: one flag carries "
                    "two meanings — 'sent to Workday by WF-018' and 'paid "
                    "from Workday by WF-019'. Workday can raise a payable "
                    "by other means, so this state is reachable in "
                    "production. The clean fix is a separate workday_paid "
                    "boolean; whether the bill still NEEDS exporting once "
                    "Workday has paid it is a question for the Controller.")
    finally:
        if payment_cid:
            restore_company(ctx, payment_cid, payment_original)
        if cid:
            restore_company(ctx, cid, original)
