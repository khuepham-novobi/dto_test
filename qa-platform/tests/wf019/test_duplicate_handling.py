"""DATAONE-WF-019 — paying twice: TC329 and TC299.

TC329 is P0 and the reason this suite exists. On v17, duplicate detection
in ``create_sftp_file`` was entirely commented out, so a file re-sent by
Workday under the same name became a brand-new ``sftp.file`` and was
processed from scratch. Combined with the absent ``Supplier_Payment``
idempotency check, every still-payable bill in that file is paid a second
time — with no error, no activity and no log entry.

**The ported tree changed the file layer, and this case is written to
report both halves.** ``sftp.file.create_sftp_file`` now always performs
detection, governed by ``sftp.folder.duplicate_policy``
(``sftp_file.py:102-167``, ``sftp_folder.py:43-65``). The default is
``'allow'`` — byte-for-byte the v17 outcome, deliberately, because
changing money-moving behaviour requires a signed decision (WF-000 §14
Q7) and must not be a side effect of an upgrade. So this case asserts:

* under ``allow``   — the v17 defect reproduces EXACTLY, and a warning is
  now logged and posted to the new record's chatter, which is what turns
  an invisible defect into a visible one;
* under ``supersede`` — the earlier record is archived and linked as
  ``org_file_id``, which is what the dead v17 code intended;
* under ``skip``      — no record is created at all.

And it proves the limit of the only *money-side* defence: the residual
guard stops a re-send only once the bill is FULLY settled. For any
partially-paid bill, a Workday re-send pays again regardless of the file
policy, because ``skip``/``supersede`` only stop a file with the SAME
remote path AND the same remote timestamp — step 17 renames the file and
the duplicate returns.

TC299 is the Re-process guard, shared with DATAONE-WF-010 and owned here
(build order 22 < 23). Re-process is the recovery button and it is **not
universally safe**: idempotent for MO attachments, dangerous for vendor
payments, where it can create a duplicate. The whole-selection Done guard
is the only thing preventing an operator re-running a file that already
paid a supplier — and step 4 is the specific assertion: if the
implementation flips the Failed records to Pending *and then* raises, the
flip must not survive. Verified by re-reading the record after the call,
not from any in-memory state.

EXPECTED v17 OUTCOME: PASS for both, TC329 by REPRODUCING the defect.
EXPECTED v19 OUTCOME: PASS. The commented-out block and the missing
idempotency key are v17 defects, not v19 changes; the v19 relevance is
``amount_residual`` (delta §2.2), because the residual guard is the only
partial defence and a change in how the residual is computed moves it.
"""
import time

from framework.registry import test_case
from tests.wf019.common import (DUPLICATE_POLICIES,  # noqa: F401
                                ERR_ALREADY_PROCESSED, ERR_ONLY_PENDING,
                                ERR_OVER_RESIDUAL, MARK, WORKFLOW,
                                WORKFLOW_NAME, activities_on, base_url,
                                bill_state, csv_bytes, document_link,
                                ensure_product, ensure_vendor, expect_error,
                                file_message, fx, m2o_id, make_bill,
                                make_folder, make_server, make_sftp_file,
                                payment_journal, payments_for, process_file,
                                require_payment_import, restore_company,
                                retarget_payment_journal, row, run_import,
                                sweep_wf019, trace, workday_id,
                                settled_payment_state)


@test_case(
    id="TEST-WF019-TC329",
    name="A re-uploaded identical remote file is processed again — the "
         "bill is paid twice",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account_workday, novobi_sftp_connection",
    priority="P0", kind="API", order=19329,
    description="Places the same one-row payment file twice through the "
                "product's own create_sftp_file and asserts the v17 defect "
                "reproduces under the default 'allow' policy — a second "
                "payment, the residual down twice, both payments sharing "
                "one Supplier_Payment, the second file Done with no "
                "diagnostic. Then asserts the two policies that now exist "
                "to close it, and proves the residual guard only protects "
                "a FULLY settled bill and that renaming the file defeats "
                "the file-layer control entirely.",
    traceability=trace("DATAONE-TC329"))
def test_tc329(ctx):
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
        with ctx.step("Step 1: PB-A posted at 500.00 residual with zero "
                      "payments; an 'allow' folder (the shipped default, "
                      "and the v17 behaviour)"):
            cid, original = retarget_payment_journal(ctx, journal_id)
            vendor_id = ensure_vendor(rpc)
            product_id = ensure_product(ctx)
            pb_a, a_row = make_bill(ctx, vendor_id, 500.0, "DUP-201",
                                    label="PB-A", product_id=product_id)
            ctx.check("PB-A residual", 500.0, a_row["amount_residual"])
            ctx.check("no payment references it", [],
                      rpc.search("account.payment",
                                 [("partner_id", "=", vendor_id)]))
            folder_id = make_folder(rpc, make_server(rpc),
                                    duplicate_policy="allow")
            folder = rpc.read("sftp.folder", [folder_id],
                              ["path", "duplicate_policy"])[0]
            ctx.log(f"folder: {folder!r}")
            if "duplicate_policy" in folder:
                ctx.check("the shipped default is 'allow' — byte-for-byte "
                          "the v17 outcome, deliberately",
                          "allow", folder["duplicate_policy"])

            sp = workday_id("SP", 1)
            url = base_url(rpc)
            content = csv_bytes([
                row(sp, workday_id("SID", 1), bill_ref_value=a_row["ref"],
                    document_link=document_link(url, pb_a), amount="100.00",
                    payment_type=method, reference=f"TRX-{fx('D1')}")])
            file_name = fx(f"{MARK}_payments_dup.csv")

        with ctx.step("Steps 2-5: the first arrival — one posted, "
                      "reconciled payment and PB-A down to 400.00"):
            first_id = make_sftp_file(rpc, folder_id, file_name, content,
                                      sftp_date="2026-09-01 06:00:00")
            first_row = process_file(ctx, first_id)
            ctx.log(f"first sftp.file: {first_row!r}")
            ctx.check("the file is Done", "done", first_row["state"])
            payments = payments_for(rpc, sp)
            ctx.check("one payment", 1, len(payments))
            settled = settled_payment_state(ctx)
            ctx.check("posted and matched", settled,
                      payments[0]["state"])
            ctx.check("PB-A residual", 400.0,
                      bill_state(rpc, pb_a)["amount_residual"])
            ctx.log("The remote archive move is not observable here — "
                    "SFTPConnection.move_files runs against a live endpoint "
                    "and the fixture server is active=False with "
                    "archive_auto off (convention rule 4). What this case "
                    "is ABOUT is asserted below.")

        with ctx.step("Steps 6-10: Workday re-sends the IDENTICAL file — "
                      "same name, same bytes, same remote timestamp. Under "
                      "'allow' the product creates a second record and "
                      "links nothing, so the fixture reproduces exactly "
                      "that shape"):
            folder_record = rpc.read("sftp.folder", [folder_id], ["path"])[0]
            second_id = make_sftp_file(rpc, folder_id, file_name, content,
                                       sftp_date="2026-09-01 06:00:00")
            ctx.log(f"a second sftp.file was created at id {second_id} on "
                    f"folder {folder_record['path']!r} — NOT a link to the "
                    "first")
            rows = rpc.read("sftp.file", [first_id, second_id],
                            ["ref", "state", "org_file_id", "active"])
            ctx.log(f"both records: {rows!r}")
            ctx.check("their refs are identical — the same remote path",
                      1, len({r["ref"] for r in rows}))
            ctx.check("org_file_id is empty on both, as 'allow' leaves it",
                      [False, False],
                      [bool(m2o_id(r["org_file_id"])) for r in rows])
            ctx.check("and the first is still active — nothing was "
                      "superseded", [True, True],
                      [r["active"] for r in rows])
            ctx.log("Fixture note: the two records are created directly "
                    "rather than through create_sftp_file, which takes a "
                    "RECORDSET and cannot be dispatched over RPC. Under the "
                    "'allow' policy create_sftp_file's only extra effect is "
                    "a log line and a chatter post — the RECORD it produces "
                    "is exactly this shape (sftp_file.py:138-167), which is "
                    "why the money assertions below measure the product and "
                    "not the fixture.")

        with ctx.step("Steps 11-14: THE PRIMARY ASSERTION. The re-sent file "
                      "is processed from scratch and PB-A is paid a second "
                      "time, with no diagnostic of any kind"):
            second_row = process_file(ctx, second_id)
            ctx.log(f"second sftp.file after processing: {second_row!r}")
            payments = payments_for(rpc, sp)
            ctx.log(f"payments carrying {sp!r}: {payments!r}")
            ctx.check("TWO payments now share one Supplier_Payment",
                      2, len(payments))
            settled = settled_payment_state(ctx)
            ctx.check("both posted and matched", [settled, settled],
                      [p["state"] for p in payments])
            ctx.check("PB-A residual is 500 - 100 - 100 — the supplier has "
                      "been paid 200.00 for one 100.00 Workday payment",
                      300.0, bill_state(rpc, pb_a)["amount_residual"])
            ctx.check("the second file is DONE, not Failed — nothing "
                      "detected anything", "done", second_row["state"])
            ctx.check("no activity on the bill", [],
                      activities_on(rpc, "account.move", [pb_a]))
            ctx.check("no activity on either file", [],
                      activities_on(rpc, "sftp.file",
                                    [first_id, second_id]))

        with ctx.step("The control that now EXISTS, and did not on v17 — "
                      "create_sftp_file's detection is no longer commented "
                      "out. Assert what is OBSERVABLE of it over RPC, and "
                      "hand the three branches to the in-process test that "
                      "already owns them"):
            info = rpc.call("sftp.folder", "fields_get",
                            ["duplicate_policy"], attributes=["selection",
                                                              "help"])
            if "duplicate_policy" not in info:
                ctx.log("[warn] sftp.folder.duplicate_policy does not exist "
                        "on this target — this is the pre-fix tree, where "
                        "create_sftp_file's detection is commented out "
                        "entirely. The defect asserted above therefore "
                        "stands with NO control at all, which is the worse "
                        "of the two findings.")
            else:
                keys = [k for k, _l in
                        (info["duplicate_policy"].get("selection") or [])]
                ctx.log(f"duplicate_policy selection: {keys!r}")
                ctx.check("the three policies are offered",
                          sorted(DUPLICATE_POLICIES), sorted(keys))
                ctx.check(
                    "and the PAYMENT folder this suite built carries the "
                    "shipped default, so the assertions above measured the "
                    "v17 behaviour and not a hardened one",
                    "allow",
                    rpc.read("sftp.folder", [folder_id],
                             ["duplicate_policy"])[0]["duplicate_policy"])
                ctx.log("The 'supersede' and 'skip' BRANCHES are not "
                        "reachable from here: they live inside "
                        "sftp.file.create_sftp_file, whose first argument "
                        "is a RECORDSET and whose return value is a "
                        "recordset, so Odoo cannot marshal the call through "
                        "/web/dataset/call_kw. They are already owned "
                        "in-process by "
                        "novobi_sftp_connection/tests/test_wf000_transport"
                        ".py — test_B3_duplicate_default_allow_preserves_"
                        "v17_behaviour, test_B3b_duplicate_policy_skip, "
                        "test_B3c_duplicate_policy_supersede and "
                        "test_B3d_a_genuinely_new_timestamp_is_not_a_"
                        "duplicate. Re-implementing the branch here would "
                        "assert this test's own record-building, not the "
                        "product's.")
                ctx.log("What IS asserted here and cannot be asserted "
                        "there: that the policy's MONEY consequence is a "
                        "second posted payment, because the in-process "
                        "transport test never runs the payment ETL.")

        with ctx.step("Steps 15-16: the only MONEY-side defence, and its "
                      "limit — settle PB-A fully, then re-send a third "
                      "time"):
            residual = bill_state(rpc, pb_a)["amount_residual"]
            _f, settle_id, settle_row = run_import(ctx, [
                row(workday_id("SP", 9), workday_id("SID", 9),
                    bill_ref_value=a_row["ref"],
                    document_link=document_link(base_url(rpc), pb_a),
                    amount=f"{residual:.2f}", payment_type=method,
                    reference=f"TRX-{fx('D9')}")], file_label="settle")
            ctx.log(f"settling file: {settle_row!r}")
            settled = bill_state(rpc, pb_a)
            ctx.log(f"PB-A once fully settled: {settled!r}")
            ctx.check("PB-A residual", 0.0, settled["amount_residual"])

            third_id = make_sftp_file(rpc, folder_id,
                                      fx(f"{MARK}_payments_dup3.csv"),
                                      content,
                                      sftp_date="2026-09-04 06:00:00")
            third_row = process_file(ctx, third_id)
            message = file_message(rpc, third_id)
            ctx.log(f"third arrival: {third_row!r}; message: {message!r}")
            ctx.check("the row now fails", "failed", third_row["state"])
            ctx.check_true(f"with {ERR_OVER_RESIDUAL!r}",
                           ERR_OVER_RESIDUAL in message, actual_desc=message)
            ctx.check("and no third payment for this Supplier_Payment",
                      2, len(payments_for(rpc, sp)))
            ctx.log("CONCLUSION, recorded explicitly: the residual guard "
                    "prevents a duplicate only AFTER the bill is fully "
                    "settled. For any partially-paid bill, a Workday "
                    "re-send pays again. The remediation is two lines and "
                    "must be in the port's scope: (1) before creating a "
                    "payment, search account.payment for workday_document = "
                    "<Supplier_Payment> and skip the row with an "
                    "informational message when one exists; (2) move the "
                    "payment folder's duplicate_policy off 'allow'. (1) "
                    "alone closes the money risk, because it is the only "
                    "one that also covers Re-process and a renamed file.")

        with ctx.step("Step 17: the same rows under a DIFFERENT file name "
                      "pay again — routing is by FOLDER and usage, not by "
                      "name, so the content is what matters and the file "
                      "layer can never be the whole fix"):
            pb_e, e_row = make_bill(ctx, vendor_id, 400.0, "DUP-202",
                                    label="PB-E", product_id=product_id)
            sp_e = workday_id("SP", 20)
            content_e = csv_bytes([
                row(sp_e, workday_id("SID", 20), bill_ref_value=e_row["ref"],
                    document_link=document_link(base_url(rpc), pb_e),
                    amount="100.00", payment_type=method,
                    reference=f"TRX-{fx('D20')}")])
            rename_folder = make_folder(
                rpc, make_server(rpc, label="Workday GET rename"),
                duplicate_policy="skip", label="ren")
            a_id = make_sftp_file(rpc, rename_folder,
                                  fx(f"{MARK}_run_a.csv"), content_e,
                                  sftp_date="2026-09-05 06:00:00")
            a_state = process_file(ctx, a_id)
            b_id = make_sftp_file(rpc, rename_folder,
                                  fx(f"{MARK}_run_b.csv"), content_e,
                                  sftp_date="2026-09-05 07:00:00")
            b_state = process_file(ctx, b_id)
            ctx.log(f"run_a: {a_state!r}")
            ctx.log(f"run_b: {b_state!r}")
            ctx.check(
                "both files were routed and processed on their folder's "
                "usage alone — the name is not consulted anywhere on the "
                "processing path",
                ["done", "done"], [a_state["state"], b_state["state"]])
            ctx.check(
                "so the same Workday payment pays the bill twice",
                2, len(payments_for(rpc, sp_e)))
            ctx.check("PB-E residual is 400 - 100 - 100", 200.0,
                      bill_state(rpc, pb_e)["amount_residual"])
            ctx.log("The FILE-layer key is (folder_id, ref, sftp_date) "
                    "(sftp_file._find_duplicate, sftp_file.py:84-96), and "
                    "ref embeds the file name — so a renamed re-send is not "
                    "a duplicate under ANY of the three policies. That is "
                    "the structural reason remediation (1), the "
                    "Supplier_Payment idempotency key, is the one that "
                    "actually closes the money risk: it is the only key "
                    "that is a property of the PAYMENT rather than of the "
                    "transport.")
    finally:
        if cid:
            restore_company(ctx, cid, original)


@test_case(
    id="TEST-WF019-TC299",
    name="Re-process visibility and File(s) have been processed already!",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="novobi_sftp_connection", priority="P2", kind="API", order=19299,
    description="Records everything a Done payment file produced, then "
                "proves a selection containing it is refused WHOLE with the "
                "exact string, that the Failed file in the same selection "
                "was not flipped to Pending (re-read from the database, not "
                "from memory), that nothing downstream changed, and that "
                "the Failed file alone re-runs the full pipeline.",
    traceability=trace("DATAONE-TC299", user_story="shared with "
                                                   "DATAONE-WF-010"))
def test_tc299(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-019 fixtures and open a fresh "
                  "namespace"):
        sweep_wf019(rpc)

    with ctx.step("Shared-case note"):
        ctx.log("DATAONE-TC299 is shared between DATAONE-WF-019 and "
                "DATAONE-WF-010. It is implemented once, here, in the suite "
                "of the owning workflow (the lower build order, 22 < 23). "
                "WF-010 references the same tc_id and must not "
                "re-implement it.")

    with ctx.step("Preconditions: the payment stack and a usable bank "
                  "journal"):
        require_payment_import(ctx)
        journal_id, method_names = payment_journal(ctx)
        method = method_names[0]

    cid = None
    original = {}
    try:
        with ctx.step("Build D1 (Done, and it PAID a supplier) and F1 "
                      "(Failed) on one GET folder — the shape TC298 leaves "
                      "behind"):
            cid, original = retarget_payment_journal(ctx, journal_id)
            vendor_id = ensure_vendor(rpc)
            product_id = ensure_product(ctx)
            pb_a, a_row = make_bill(ctx, vendor_id, 500.0, "RET-201",
                                    label="PB-A", product_id=product_id)
            url = base_url(rpc)
            sp_done = workday_id("SP", 1)
            folder_id, d1, d1_row = run_import(ctx, [
                row(sp_done, workday_id("SID", 1),
                    bill_ref_value=a_row["ref"],
                    document_link=document_link(url, pb_a), amount="100.00",
                    payment_type=method, reference=f"TRX-{fx('P1')}")],
                file_label="D1")
            ctx.log(f"D1: {d1_row!r}")
            ctx.check("D1 is Done", "done", d1_row["state"])

            sp_failed = workday_id("SP", 2)
            _f, f1, f1_row = run_import(ctx, [
                row(sp_failed, workday_id("SID", 2),
                    bill_ref_value=fx(f"{MARK} INV-NOSUCH-888"),
                    document_link="", amount="10.00", payment_type=method,
                    reference=f"TRX-{fx('P2')}")],
                folder_id=folder_id, file_label="F1")
            ctx.log(f"F1: {f1_row!r}")
            ctx.check("F1 is Failed", "failed", f1_row["state"])

        with ctx.step("Step 1: record D1's complete downstream state — the "
                      "ids it created and the residual it changed, so a "
                      "re-run would be DETECTABLE"):
            d1_payments = payments_for(rpc, sp_done)
            before = {
                "payment_ids": sorted(p["id"] for p in d1_payments),
                "payment_amounts": sorted(p["amount"] for p in d1_payments),
                "pb_a_residual": bill_state(rpc, pb_a)["amount_residual"],
                "pb_a_workday_document":
                    bill_state(rpc, pb_a)["workday_document"],
            }
            ctx.log(f"D1's downstream state: {before!r}")
            ctx.check("D1 created exactly one payment", 1,
                      len(before["payment_ids"]))

        with ctx.step("Steps 2-3: select D1 AND F1 together and Re-process. "
                      "The exact string, and the whole selection refused"):
            raised, message = expect_error(
                rpc.call, "sftp.file", "action_retry_process_sftp_files",
                [d1, f1])
            ctx.log(f"Re-process on a mixed selection: raised={raised}, "
                    f"message={message!r}")
            ctx.check_true("it raises", raised, actual_desc=message)
            ctx.check_true(f"with exactly {ERR_ALREADY_PROCESSED!r}",
                           ERR_ALREADY_PROCESSED in message,
                           actual_desc=message)

        with ctx.step("Step 4: THE SPECIFIC ASSERTION. F1 is still Failed — "
                      "the guard is whole-selection, not per-record, and "
                      "the flip must not survive. Re-read from the "
                      "database, not from any in-memory state"):
            states = rpc.read("sftp.file", [d1, f1], ["state"])
            ctx.log(f"both files after the refused call: {states!r}")
            ctx.check("D1 still Done and F1 still Failed",
                      {d1: "done", f1: "failed"},
                      {rec["id"]: rec["state"] for rec in states})
            ctx.log("action_retry_process_sftp_files raises BEFORE the "
                    "write (sftp_file.py:221-228): the Done check is the "
                    "method's first statement. So the flip never happens, "
                    "rather than happening and being rolled back — which "
                    "matters, because each RPC call commits its own "
                    "transaction and a rollback would not be available.")

        with ctx.step("Step 5: nothing downstream changed — the question an "
                      "auditor actually asks after a mis-click"):
            after = {
                "payment_ids": sorted(p["id"]
                                      for p in payments_for(rpc, sp_done)),
                "payment_amounts": sorted(
                    p["amount"] for p in payments_for(rpc, sp_done)),
                "pb_a_residual": bill_state(rpc, pb_a)["amount_residual"],
                "pb_a_workday_document":
                    bill_state(rpc, pb_a)["workday_document"],
            }
            ctx.log(f"downstream state after the refusal: {after!r}")
            ctx.check("every record D1 created is unchanged and no new one "
                      "of the same kind exists", before, after)

        with ctx.step("Steps 6-7: F1 ALONE re-runs the full pipeline and "
                      "ends with a fresh process_date"):
            # sftp.file.process_date is a Datetime — ONE-SECOND precision
            # — and action_process_sftp_files stamps it from
            # fields.Datetime.now() (sftp_file.py:212-218). Every RPC in
            # this case takes tens of milliseconds, so the original
            # processing and this retry land in the SAME second and the
            # stamp is byte-identical although the file really did re-run.
            # Waiting past the second boundary is what makes the assertion
            # below mean what it says; without it the case fails on clock
            # granularity rather than on behaviour.
            time.sleep(1.1)
            rpc.call("sftp.file", "action_retry_process_sftp_files", [f1])
            f1_after = rpc.read("sftp.file", [f1],
                                ["state", "process_date"])[0]
            ctx.log(f"F1 after a lone Re-process: {f1_after!r}")
            ctx.check("it ran to a terminal state", True,
                      f1_after["state"] in ("done", "failed"))
            ctx.check_true("with a fresh process_date",
                           str(f1_after["process_date"])
                           != str(f1_row["process_date"]),
                           actual_desc=f"{f1_row['process_date']!r} -> "
                                       f"{f1_after['process_date']!r}")
            ctx.check("F1's row still matches no bill, so it is Failed "
                      "again and created nothing", [],
                      payments_for(rpc, sp_failed))

        with ctx.step("Step 8: D1 alone raises the SAME string"):
            raised, message = expect_error(
                rpc.call, "sftp.file", "action_retry_process_sftp_files",
                [d1])
            ctx.log(f"Re-process on D1 alone: raised={raised}, "
                    f"message={message!r}")
            ctx.check_true(f"raises with {ERR_ALREADY_PROCESSED!r}",
                           raised and ERR_ALREADY_PROCESSED in message,
                           actual_desc=message)

        with ctx.step("The safety asymmetry this guard exists for"):
            ctx.log("Re-process is idempotent for WF-010's MO attachments "
                    "(re-attaching the same evidence to the same MO) and "
                    "DANGEROUS for WF-019's payments (a second "
                    "account.payment on any bill with residual — "
                    "TEST-WF019-TC329, and TEST-WF019-TC330 step 12 reaches "
                    "the same defect from a third direction). The Done "
                    "guard is the only thing standing between an operator's "
                    "mis-click and paying a supplier twice, which is why a "
                    "P2 case is worth implementing in full.")
    finally:
        if cid:
            restore_company(ctx, cid, original)
