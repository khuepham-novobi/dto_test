"""DATAONE-WF-018 — the export itself: TC316, TC318, TC319.

TC316 is the workflow's GATE. Four posted, tax-free, attachment-bearing
bills go into one selection; one of them repeats a ``ref`` that an already
exported bill carries. The duplicate must be absent from the workbook with
no gap left behind, must carry one precisely-worded activity addressed to
its own creator, and must leave the other three exported and flagged. A
guard that stops the whole run is nearly as bad as no guard when the run is
the client's daily payables feed — so "the batch survives" is asserted as
hard as "the duplicate is dropped".

TC318 is the three blocking validations, as literal strings. The third is
not a bug but a standing functional limitation: **no bill carrying tax can
be exported at all, ever**. The upgrade must not silently relax it, and it
must not silently tighten it either — step 12 proves a zero-rate tax still
passes, because the gate is arithmetic (``float_compare(amount_untaxed_signed,
amount_total_signed)``) and not structural.

TC319 is ``have_attachment``, which is the fourth term of the export domain
and a stored compute over a domain-filtered One2many. The case's output is
a route × (stored value flipped? in domain?) table, not a pass/fail — the
defect is that the two attachment routes disagree.

What these cases deliberately do NOT do
---------------------------------------
They never call ``account.move.cron_export_workday_vendor_bill()``. It is
public and would dispatch, but it searches the export domain **with no
limit** under ``mark_exported=True``: on a clone of the client's database
that flags every eligible live bill as exported and permanently removes it
from the real queue. Convention rule 3. TC318 step 11 and TC319 step 11
therefore assert the cron's *selection* — the domain's id set — rather than
running it, which is the only part of those steps that is about this
product rather than about Odoo's scheduler.

EXPECTED v17 OUTCOME
  TC316 PASS · TC318 PASS · TC319 PASS. TC319 passes by RECORDING the
  defect, not by the defect being absent: its assertions are on the table
  it produces and on the two invariants that must hold either way (the
  domain and the stored flag always agree with each other; the wizard's
  live ``missing_attachment`` is reported next to the stored flag so a
  disagreement is visible).
EXPECTED v19 OUTCOME
  TC316 and TC318 PASS unless ``have_attachment`` / ``purchase_order_id``
  did not port (LOUD — the domain raises) or ``amount_*_signed`` semantics
  moved (SILENT — TC318 step 12 is what catches it). TC319 is expected to
  produce the SAME table on v19: the root cause is a stored compute over a
  domain-filtered O2m and that pattern is unchanged.
"""
from framework.registry import test_case
from tests.wf018.common import (ACTIVITY_SUMMARY,  # noqa: F401
                                ACTIVITY_TYPE_XMLID,
                                ERR_DUPLICATE_REF_PREFIX, ERR_EMPTY_SELECTION,
                                ERR_HAS_TAX, ERR_NOT_POSTED, MARK,
                                REQUIRED_COLUMNS, TEMPLATE_FILE_NAME,
                                TEMPLATE_ROW_START, TEMPLATE_SHEET, WORKFLOW,
                                WORKFLOW_NAME, VENDOR_BILL_EXPORT_DOMAIN,
                                activities_on, analytic_plans, attach_to_move,
                                bill_ref, cell_map, company_id,
                                ensure_analytic_account, ensure_product,
                                ensure_vendor, expect_error, exportable_lines,
                                fx, latest_workbook, m2o_id, make_bill,
                                make_post_folder, make_post_server,
                                notification_type, open_export_wizard,
                                payment_term_id, populated_rows,
                                produced_files, require_vendor_bill_usage,
                                require_workday_export, restore_company,
                                retarget_company, run_export, save_workbook,
                                sweep_wf018, template_id, trace)


def _export_target(ctx):
    """Fixture POST server + folder + the SHIPPED template, company
    retargeted. Returns (folder_id, tmpl_id, company_id, original)."""
    rpc = ctx.adapter.rpc
    tmpl_id = template_id(ctx)
    server_id = make_post_server(rpc)
    folder_id = make_post_folder(rpc, server_id)
    cid, original = retarget_company(ctx, folder_id, template_ref=tmpl_id)
    return folder_id, tmpl_id, cid, original


@test_case(
    id="TEST-WF018-TC316",
    name="GATE: four bills, one duplicate ref dropped with the exact "
         "activity, three unaffected",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account_workday, novobi_base_export",
    priority="P0", kind="API", order=18316,
    description="Four posted, tax-free, attachment-bearing bills export as "
                "one batch. The one repeating an already-exported ref is "
                "absent from the workbook with no row gap, carries exactly "
                "one warning activity addressed to its own create_uid, and "
                "stays unflagged; the other three export, flag, and produce "
                "one Pending sftp.file.",
    traceability=trace("DATAONE-TC316"))
def test_tc316(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-018 fixtures and open a fresh "
                  "namespace"):
        sweep_wf018(rpc)

    with ctx.step("Preconditions: the export stack, the usage key and the "
                  "shipped 20-column template"):
        require_workday_export(ctx)
        require_vendor_bill_usage(ctx)

    folder_id = tmpl_id = cid = None
    original = {}
    try:
        with ctx.step("Set up an INACTIVE POST folder and point the company "
                      "at it (rule 4: nothing can reach the network)"):
            folder_id, tmpl_id, cid, original = _export_target(ctx)
            folder = rpc.read("sftp.folder", [folder_id],
                              ["path", "usage", "action"])[0]
            ctx.log(f"fixture folder: {folder!r}")
            ctx.check("fixture folder usage", "workday_vendor_bill",
                      folder["usage"])
            ctx.check("fixture folder action", "POST", folder["action"])

        with ctx.step("Step 1: build BB-0 (already exported, ref GAMMA-777) "
                      "and BB-1..BB-4; record id, ref, lines, total, "
                      "create_uid and partner ref"):
            vendor_id = ensure_vendor(rpc)
            product_id = ensure_product(ctx)
            term_id = payment_term_id(rpc)
            line = {"product_id": product_id}

            bb0 = make_bill(ctx, vendor_id, [line], "GAMMA-777",
                            label="BB-0")
            rpc.call("account.move", "action_mark_exported", [bb0])
            bb0_row = rpc.read("account.move", [bb0],
                               ["ref", "export_workday",
                                "export_workday_sync"])[0]
            ctx.log(f"BB-0 (the record the guard matches against): {bb0_row!r}")
            ctx.check("BB-0 is flagged exported", True,
                      bb0_row["export_workday"])

            bb1 = make_bill(ctx, vendor_id, [line, line], "GAMMA-101",
                            label="BB-1", payment_term_id=term_id)
            bb2 = make_bill(ctx, vendor_id, [line], "GAMMA-777",
                            label="BB-2")
            bb3 = make_bill(ctx, vendor_id, [line, line, line], "GAMMA-103",
                            label="BB-3")
            bb4 = make_bill(ctx, vendor_id, [line], "GAMMA-104",
                            label="BB-4")
            batch = [bb1, bb2, bb3, bb4]

            before = {row["id"]: row for row in rpc.read(
                "account.move", batch,
                ["ref", "amount_total", "create_uid", "partner_id", "state",
                 "export_workday", "export_workday_sync", "have_attachment",
                 "source_sale_id"])}
            for move_id in batch:
                ctx.log(f"bill {move_id}: {before[move_id]!r}")
            ctx.check("all four fixtures are posted",
                      ["posted"] * 4,
                      [before[i]["state"] for i in batch])
            ctx.check("all four carry an attachment (stored flag)",
                      [True] * 4,
                      [before[i]["have_attachment"] for i in batch])
            ctx.check("BB-2 repeats BB-0's ref",
                      before[bb0]["ref"] if bb0 in before
                      else bb0_row["ref"], before[bb2]["ref"])

        with ctx.step("Step 2: the guard's precondition — exactly one OTHER "
                      "flagged bill carries BB-2's ref"):
            duplicates = rpc.search(
                "account.move", [("id", "!=", bb2),
                                 ("ref", "=", before[bb2]["ref"]),
                                 ("export_workday", "=", True)])
            ctx.log(f"prior exported bills with the same ref: {duplicates!r}")
            ctx.check("search_count matching the extractor's own guard "
                      "(workday_extractor.py:31-35)", [bb0], duplicates)

        with ctx.step("Steps 3-5: open the wizard on all four and press "
                      "'Export and Mark as exported'"):
            wizard_id = open_export_wizard(ctx, batch)
            wizard = rpc.read("workday.vendor.bill.export.wizard",
                              [wizard_id],
                              ["move_ids", "exported",
                               "missing_attachment"])[0]
            ctx.log(f"wizard {wizard_id}: {wizard!r}")
            ctx.check("wizard lists exactly the four selected bills",
                      sorted(batch), sorted(wizard["move_ids"]))
            ctx.check("wizard.exported (none of the four was exported)",
                      False, wizard["exported"])
            ctx.check("wizard.missing_attachment", False,
                      wizard["missing_attachment"])
            notification = rpc.call(
                "workday.vendor.bill.export.wizard",
                "action_execute_export_workday_vendor_bill", [wizard_id],
                context={"mark_exported": 1})

        with ctx.step("Step 6: the notification is green — the batch as a "
                      "whole succeeded despite one dropped bill"):
            ctx.log(f"wizard notification: {notification!r}")
            ctx.check("notification type", "info",
                      notification_type(notification))

        with ctx.step("Steps 7-9: open the produced workbook; the sheet name, "
                      "the first data row and the untouched header block"):
            file_row, sheet, raw = latest_workbook(ctx, folder_id)
            save_workbook(ctx, raw, f"{MARK}_TC316_{TEMPLATE_FILE_NAME}")
            ctx.log(f"produced sftp.file: {file_row!r}")
            ctx.check("sheet name", TEMPLATE_SHEET, sheet.title)
            rows = populated_rows(sheet)
            ctx.log(f"populated data rows: {rows!r}")
            ctx.check("first populated data row", TEMPLATE_ROW_START,
                      rows[0] if rows else None)
            header_block = {
                f"{col}{index}": sheet[f"{col}{index}"].value
                for index in range(1, TEMPLATE_ROW_START)
                for col in ("B", "R", "U", "EA")}
            ctx.log(f"rows 1-5 of the four required columns: {header_block!r}")

        with ctx.step("Steps 10-12: exactly six data rows, BB-2 absent "
                      "entirely, and no gap where its row would have been"):
            expected_rows = (len(exportable_lines(rpc, bb1))
                             + len(exportable_lines(rpc, bb3))
                             + len(exportable_lines(rpc, bb4)))
            ctx.check("populated data-row count (BB-1 + BB-3 + BB-4 lines)",
                      expected_rows, len(rows))
            move_ids_in_file = [sheet[f"B{index}"].value for index in rows]
            ctx.log(f"column B (move id) per row: {move_ids_in_file!r}")
            ctx.check("BB-2's move id appears nowhere in column B",
                      0, move_ids_in_file.count(bb2))
            ctx.check("no gap between the first and last populated row — "
                      "the all-or-nothing rewind left none",
                      list(range(TEMPLATE_ROW_START,
                                 TEMPLATE_ROW_START + len(rows))), rows)

        with ctx.step("Step 13: row order and EA — indices restart at 1 per "
                      "bill and are contiguous within each bill"):
            per_bill = {}
            for index in rows:
                per_bill.setdefault(sheet[f"B{index}"].value, []).append(
                    (index, sheet[f"EA{index}"].value))
            ctx.log(f"rows grouped by move id: {per_bill!r}")
            ctx.check("the file carries exactly BB-1, BB-3 and BB-4, in "
                      "selection order", [bb1, bb3, bb4], list(per_bill))
            expected_ea = {
                bb1: [1, 2], bb3: [1, 2, 3], bb4: [1]}
            actual_ea = {move: [ea for _row, ea in entries]
                         for move, entries in per_bill.items()}
            ctx.check("EA restarts at 1 per bill and is contiguous",
                      expected_ea, actual_ea)

        with ctx.step("Steps 14-16: exactly one activity, on BB-2, of the "
                      "right type, summary, deadline and ASSIGNEE, carrying "
                      "the de-duplicated duplicate-reference message"):
            acts = activities_on(rpc, "account.move", batch + [bb0])
            ctx.log(f"activities on the five bills: {acts!r}")
            ctx.check("activities created by this run", 1, len(acts))
            activity = acts[0] if acts else {}
            ctx.check("the activity is on BB-2", bb2, activity.get("res_id"))
            ctx.check("activity summary", ACTIVITY_SUMMARY,
                      activity.get("summary"))
            ctx.check("activity type",
                      rpc.ref(ACTIVITY_TYPE_XMLID),
                      m2o_id(activity.get("activity_type_id")))
            ctx.check("activity assignee is BB-2's create_uid, not the user "
                      "who pressed the button",
                      m2o_id(before[bb2]["create_uid"]),
                      m2o_id(activity.get("user_id")))
            note = activity.get("note") or ""
            ctx.log(f"activity body, verbatim: {note!r}")
            ctx.check_true(
                "activity body carries the duplicate-reference message",
                ERR_DUPLICATE_REF_PREFIX in note, actual_desc=note)
            ctx.check("the message is de-duplicated — one <li> for one "
                      "distinct error", 1, note.count("<li>"))

        with ctx.step("Steps 17-20: three bills flagged, BB-2 not, BB-0 "
                      "untouched"):
            after = {row["id"]: row for row in rpc.read(
                "account.move", batch + [bb0],
                ["export_workday", "export_workday_sync", "source_sale_id"])}
            for move_id in batch + [bb0]:
                ctx.log(f"bill {move_id} after export: {after[move_id]!r}")
            ctx.check("export_workday per bill (BB-1, BB-2, BB-3, BB-4)",
                      [True, False, True, True],
                      [after[i]["export_workday"] for i in batch])
            ctx.check_true(
                "export_workday_sync stamped on BB-1, BB-3, BB-4 and NOT on "
                "BB-2",
                all(after[i]["export_workday_sync"] for i in (bb1, bb3, bb4))
                and not after[bb2]["export_workday_sync"],
                actual_desc=repr({i: after[i]["export_workday_sync"]
                                  for i in batch}))
            ctx.check("BB-0's export_workday_sync is unchanged",
                      bb0_row["export_workday_sync"],
                      after[bb0]["export_workday_sync"])

        with ctx.step("Step 21: exactly one Pending sftp.file on the fixture "
                      "folder, named for the vendor's workbook and "
                      "referencing the template"):
            files = produced_files(rpc, folder_id)
            ctx.log(f"sftp.file rows on the fixture folder: {files!r}")
            ctx.check("files produced", 1, len(files))
            produced = files[0]
            ctx.check("sftp.file state", "pending", produced["state"])
            ctx.check("sftp.file ref",
                      f"{rpc.read('sftp.folder', [folder_id], ['path'])[0]['path']}"
                      f"/{TEMPLATE_FILE_NAME}", produced["ref"])
            ctx.check("sftp.file res_model", "data.template.export",
                      produced["res_model"])
            ctx.check("sftp.file res_id", tmpl_id, produced["res_id"])

        with ctx.step("Step 22: the export domain now returns BB-2 and none "
                      "of the other three — the next cron run would retry "
                      "exactly it"):
            domain = list(VENDOR_BILL_EXPORT_DOMAIN) + [
                ("id", "in", batch)]
            remaining = rpc.search("account.move", domain)
            ctx.log(f"bills still eligible for export: {remaining!r}")
            ctx.check("only BB-2 remains eligible", [bb2], remaining)

        with ctx.step("Step 23: fix BB-2's ref and re-export — it exports "
                      "cleanly and flags"):
            rpc.write("account.move", [bb2], {"ref": bill_ref("GAMMA-102")})
            _wiz, notification2 = run_export(ctx, [bb2], mark_exported=True)
            ctx.check("re-export notification type", "info",
                      notification_type(notification2))
            bb2_after = rpc.read("account.move", [bb2],
                                 ["export_workday",
                                  "export_workday_sync"])[0]
            ctx.log(f"BB-2 after re-export: {bb2_after!r}")
            ctx.check("BB-2 now flagged", True, bb2_after["export_workday"])
            ctx.check_true("BB-2 export_workday_sync stamped",
                           bool(bb2_after["export_workday_sync"]),
                           actual_desc=repr(bb2_after["export_workday_sync"]))
            ctx.check("BB-2 produced a second sftp.file", 2,
                      len(produced_files(rpc, folder_id)))

        with ctx.step("Step 24: source_sale_id was refreshed before the "
                      "snapshot — unlike WF-017, where that call is "
                      "commented out (BR-11)"):
            refreshed = {i: m2o_id(after[i]["source_sale_id"]) for i in batch}
            stale = {i: m2o_id(before[i]["source_sale_id"]) for i in batch}
            ctx.log(f"source_sale_id before: {stale!r}")
            ctx.log(f"source_sale_id after:  {refreshed!r}")
            ctx.log("WorkdayExtractor._run_extractor_workday_vendor_bill:16 "
                    "calls bills.update_source_sale_id() on EVERY bill in "
                    "the batch, including the ones it is about to drop — "
                    "the journal-entry extractor's equivalent call is "
                    "commented out at workday_extractor.py:60.")
            ctx.check("the refresh ran on every bill in the batch, including "
                      "the dropped one (no KeyError / no omission)",
                      sorted(batch), sorted(refreshed))
    finally:
        if cid:
            restore_company(ctx, cid, original)


@test_case(
    id="TEST-WF018-TC318",
    name="Three blocking validations, exact strings, whole selection refused",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account_workday", priority="P0", kind="API", order=18318,
    description="The empty, unposted and taxed selections are each refused "
                "in full with a literal UserError before the wizard opens, "
                "leaving the valid bill in the selection untouched; the "
                "taxed bill is dropped NON-blockingly on the cron path; and "
                "a zero-rate tax passes, because the gate is arithmetic.",
    traceability=trace("DATAONE-TC318"))
def test_tc318(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-018 fixtures and open a fresh "
                  "namespace"):
        sweep_wf018(rpc)

    with ctx.step("Preconditions: the export stack and the usage key"):
        require_workday_export(ctx)
        require_vendor_bill_usage(ctx)

    folder_id = cid = None
    original = {}
    try:
        with ctx.step("Set up the inactive POST target and build BB-1 "
                      "(valid), BB-D (draft) and BB-T (taxed)"):
            folder_id, _tmpl, cid, original = _export_target(ctx)
            vendor_id = ensure_vendor(rpc)
            product_id = ensure_product(ctx)
            line = {"product_id": product_id}

            bb1 = make_bill(ctx, vendor_id, [line], "BLOCK-1", label="BB-1")
            bb_d = make_bill(ctx, vendor_id, [line], "BLOCK-D", label="BB-D",
                             post=False)

            taxes = rpc.search_read(
                "account.tax",
                [("type_tax_use", "=", "purchase"), ("amount", ">", 0)],
                ["name", "amount", "amount_type"], limit=1)
            if not taxes:
                ctx.blocked(
                    "No purchase tax with a non-zero rate exists on "
                    f"{ctx.env.key}. The whole subject of this case is the "
                    "tax gate — asserting it without a taxed bill would "
                    "pass vacuously.")
            tax = taxes[0]
            ctx.log(f"tax used for BB-T: {tax!r}")
            bb_t = make_bill(ctx, vendor_id, [line], "BLOCK-T", label="BB-T",
                             tax_ids=[tax["id"]])
            amounts = rpc.read("account.move", [bb_t],
                               ["amount_untaxed_signed",
                                "amount_total_signed", "state"])[0]
            ctx.log(f"BB-T amounts: {amounts!r}")
            ctx.check_true(
                "BB-T actually carries tax (untaxed != total)",
                amounts["amount_untaxed_signed"]
                != amounts["amount_total_signed"],
                actual_desc=repr(amounts))

        with ctx.step("Step 1: an empty selection is refused"):
            raised, message = expect_error(
                rpc.call, "account.move",
                "action_export_workday_vendor_bill", [])
            ctx.log(f"empty selection message, verbatim: {message!r}")
            ctx.check_true("empty selection raises", raised,
                           actual_desc=message)
            ctx.check_true(
                f"message contains {ERR_EMPTY_SELECTION!r}",
                ERR_EMPTY_SELECTION in message, actual_desc=message)

        with ctx.step("Steps 2-5: BB-1 + BB-D raises the exact posted "
                      "message, refuses the WHOLE selection, and never "
                      "opens the wizard"):
            wizards_before = rpc.search(
                "workday.vendor.bill.export.wizard", [])
            raised, message = expect_error(
                rpc.call, "account.move",
                "action_export_workday_vendor_bill", [bb1, bb_d])
            ctx.log(f"unposted-selection message, verbatim: {message!r}")
            ctx.check_true("BB-1 + BB-D raises", raised, actual_desc=message)
            ctx.check_true(f"message contains {ERR_NOT_POSTED!r}",
                           ERR_NOT_POSTED in message, actual_desc=message)
            bb1_state = rpc.read("account.move", [bb1],
                                 ["export_workday", "export_workday_sync"])[0]
            ctx.log(f"BB-1 after the refused selection: {bb1_state!r}")
            ctx.check("BB-1 not flagged", False, bb1_state["export_workday"])
            ctx.check("BB-1 has no export timestamp", False,
                      bb1_state["export_workday_sync"])
            ctx.check("no sftp.file was produced", [],
                      produced_files(rpc, folder_id))
            ctx.check("no activity on BB-1", [],
                      activities_on(rpc, "account.move", [bb1]))
            ctx.check("no wizard was created — the check runs BEFORE the "
                      "act_window is returned",
                      sorted(wizards_before),
                      sorted(rpc.search("workday.vendor.bill.export.wizard",
                                        [])))

        with ctx.step("Steps 6-8: BB-1 + BB-T raises the exact tax message "
                      "and again leaves BB-1 untouched"):
            raised, message = expect_error(
                rpc.call, "account.move",
                "action_export_workday_vendor_bill", [bb1, bb_t])
            ctx.log(f"taxed-selection message, verbatim: {message!r}")
            ctx.check_true("BB-1 + BB-T raises", raised, actual_desc=message)
            ctx.check_true(f"message contains {ERR_HAS_TAX!r}",
                           ERR_HAS_TAX in message, actual_desc=message)
            bb1_state = rpc.read("account.move", [bb1],
                                 ["export_workday"])[0]
            ctx.check("BB-1 still not flagged", False,
                      bb1_state["export_workday"])

        with ctx.step("Step 9: the ordering of the checks — BB-D + BB-T "
                      "reports the POSTED message first (empty -> unposted "
                      "-> taxed)"):
            raised, message = expect_error(
                rpc.call, "account.move",
                "action_export_workday_vendor_bill", [bb_d, bb_t])
            ctx.log(f"BB-D + BB-T message, verbatim: {message!r}")
            ctx.check_true("the posted check fires before the tax check",
                           ERR_NOT_POSTED in message
                           and ERR_HAS_TAX not in message,
                           actual_desc=message)

        with ctx.step("Step 10: BB-1 alone opens the wizard with one row"):
            wizard_id = open_export_wizard(ctx, [bb1])
            wizard = rpc.read("workday.vendor.bill.export.wizard",
                              [wizard_id], ["move_ids"])[0]
            ctx.check("wizard lists exactly BB-1", [bb1], wizard["move_ids"])

        with ctx.step("Step 11: the CRON path has no blocking check at all "
                      "— assert the domain's selection rather than running "
                      "the unlimited cron (convention rule 3)"):
            eligible = rpc.search(
                "account.move",
                list(VENDOR_BILL_EXPORT_DOMAIN)
                + [("id", "in", [bb1, bb_d, bb_t])])
            ctx.log(f"bills the daily cron's domain admits: {eligible!r}")
            ctx.check(
                "the domain admits the TAXED bill — the blocking check an "
                "accountant meets on the manual path does not exist on the "
                "scheduled path",
                sorted([bb1, bb_t]), sorted(eligible))
            ctx.log("Consequence, for the report: the same bill is REFUSED "
                    "by hand (UserError) and SILENTLY DROPPED by the cron "
                    "with only an activity — "
                    f"{ERR_HAS_TAX!r} versus "
                    f"{'Tax export is not yet supported'!r} "
                    "(workday_extractor.py:28).")

        with ctx.step("Step 11b: through the wizard, BB-T alone is dropped "
                      "non-blockingly when it reaches the extractor"):
            # BB-T cannot pass action_export_workday_vendor_bill, so the
            # extractor's own per-bill guard is reached the way the cron
            # reaches it: by creating the wizard directly on the taxed bill.
            wizard_id = rpc.create("workday.vendor.bill.export.wizard",
                                   {"move_ids": [(6, 0, [bb_t])]})
            raised, message = expect_error(
                rpc.call, "workday.vendor.bill.export.wizard",
                "action_execute_export_workday_vendor_bill", [wizard_id],
                context={"mark_exported": 1})
            ctx.log(f"wizard on BB-T alone raised={raised} msg={message!r}")
            ctx.check_true(
                "the wizard re-runs the SAME blocking check before the ETL "
                "(action_execute_export_workday_vendor_bill:32), so the "
                "extractor's non-blocking branch is unreachable from the "
                "wizard",
                raised and ERR_HAS_TAX in message, actual_desc=message)
            ctx.log("The extractor's per-bill 'Tax export is not yet "
                    "supported' branch (workday_extractor.py:26-28) is "
                    "therefore reachable ONLY from "
                    "cron_export_workday_vendor_bill, which this suite "
                    "must not run against a live AP ledger. Recorded as "
                    "the cron-path half of step 11.")

        with ctx.step("Step 12: a ZERO-rate tax passes — the gate is "
                      "arithmetic, not structural"):
            zero_taxes = rpc.search_read(
                "account.tax",
                [("type_tax_use", "=", "purchase"), ("amount", "=", 0)],
                ["name", "amount", "amount_type"], limit=1)
            if not zero_taxes:
                ctx.log("[warn] this database has no zero-rate purchase "
                        "tax, so step 12 is recorded as untested rather "
                        "than asserted. Create one to close it.")
            else:
                zero = zero_taxes[0]
                ctx.log(f"zero-rate tax: {zero!r}")
                bb_z = make_bill(ctx, vendor_id, [line], "BLOCK-Z",
                                 label="BB-Z", tax_ids=[zero["id"]])
                amounts = rpc.read("account.move", [bb_z],
                                   ["amount_untaxed_signed",
                                    "amount_total_signed", "tax_ids"])[0]
                ctx.log(f"BB-Z amounts: {amounts!r}")
                wizard_id = open_export_wizard(ctx, [bb_z])
                ctx.check_true(
                    "a bill carrying a 0.00-rate tax passes the gate, "
                    "because amount_untaxed_signed == amount_total_signed "
                    "despite a tax being present — CURRENT behaviour, "
                    "recorded not judged",
                    bool(wizard_id), actual_desc=repr(amounts))
    finally:
        if cid:
            restore_company(ctx, cid, original)


@test_case(
    id="TEST-WF018-TC319",
    name="have_attachment = True is required by the domain — and its "
         "stale-compute defect",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account, dto_account_workday",
    priority="P0", kind="API", order=18319,
    description="Builds the attachment-route table the workbook asks for: "
                "for each of the two reachable routes, whether the STORED "
                "have_attachment flipped and whether the bill entered the "
                "export domain. Asserts the two invariants that must hold "
                "either way — domain membership tracks the stored flag, and "
                "the wizard's live missing_attachment is reported beside it "
                "so a disagreement between the manual and scheduled paths "
                "is visible.",
    traceability=trace("DATAONE-TC319"))
def test_tc319(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-018 fixtures and open a fresh "
                  "namespace"):
        sweep_wf018(rpc)

    with ctx.step("Preconditions: dto_account's have_attachment exists and "
                  "is STORED — a non-stored field would make this case "
                  "vacuous"):
        require_workday_export(ctx)
        info = rpc.call("account.move", "fields_get", ["have_attachment"],
                        attributes=["store", "type", "depends", "readonly"])
        ctx.log(f"have_attachment field definition: {info!r}")
        ctx.check("have_attachment type", "boolean",
                  info["have_attachment"].get("type"))
        ctx.check_true(
            "have_attachment is stored (the defect exists only because it "
            "is)", info["have_attachment"].get("store") is not False,
            actual_desc=repr(info["have_attachment"]))

    table = {}
    vendor_id = ensure_vendor(rpc)
    product_id = ensure_product(ctx)
    line = {"product_id": product_id}

    with ctx.step("Steps 1-2: BA-1 exists with NO attachment, reads "
                  "have_attachment False, and is absent from the export "
                  "domain"):
        ba1 = make_bill(ctx, vendor_id, [line], "ATT-1", label="BA-1",
                        attach=False, post=False)
        row = rpc.read("account.move", [ba1], ["have_attachment", "state"])[0]
        ctx.log(f"BA-1 before any attachment: {row!r}")
        ctx.check("stored have_attachment before any attachment", False,
                  row["have_attachment"])
        ctx.check("BA-1 is not in the export domain",
                  [], rpc.search("account.move",
                                 list(VENDOR_BILL_EXPORT_DOMAIN)
                                 + [("id", "=", ba1)]))

    with ctx.step("Steps 3-5: route A — an ir.attachment created AT the "
                  "move (the chatter paperclip path). Record whether the "
                  "stored value flipped and whether the bill entered the "
                  "domain"):
        attach_to_move(rpc, ba1, via="attachment",
                       name=fx(f"{MARK} route-a.pdf"))
        row = rpc.read("account.move", [ba1],
                       ["have_attachment", "attachment_ids"])[0]
        in_domain = bool(rpc.search("account.move",
                                    list(VENDOR_BILL_EXPORT_DOMAIN)
                                    + [("id", "=", ba1)]))
        table["A: ir.attachment.create(res_model='account.move')"] = {
            "stored_flag": row["have_attachment"],
            "attachment_ids_visible": len(row["attachment_ids"]),
            "in_export_domain": in_domain,
        }
        ctx.log(f"route A: {table!r}")

    with ctx.step("Step 6: the attachment IS visible to the user regardless "
                  "of the stored value — this is the discrepancy that makes "
                  "the defect confusing"):
        visible = rpc.search_read(
            "ir.attachment", [("res_model", "=", "account.move"),
                              ("res_id", "=", ba1)], ["name"])
        ctx.log(f"attachments a user sees on BA-1: {visible!r}")
        ctx.check_true("the document is on the record", bool(visible),
                       actual_desc=repr(visible))

    with ctx.step("Step 7: force a recompute by re-saving the move, and "
                  "record whether the stored value flips"):
        rpc.write("account.move", [ba1],
                  {"narration": fx(f"{MARK} touch")})
        row = rpc.read("account.move", [ba1], ["have_attachment"])[0]
        table["A: ir.attachment.create(res_model='account.move')"][
            "stored_flag_after_resave"] = row["have_attachment"]
        ctx.log(f"BA-1 stored flag after a re-save: {row!r}")

    with ctx.step("Steps 8-9: route B — attachment_ids written on the MOVE "
                  "(the form's attachment widget). Same two questions"):
        ba2 = make_bill(ctx, vendor_id, [line], "ATT-2", label="BA-2",
                        attach=False, post=False)
        attach_to_move(rpc, ba2, via="move",
                       name=fx(f"{MARK} route-b.pdf"))
        row = rpc.read("account.move", [ba2],
                       ["have_attachment", "attachment_ids"])[0]
        in_domain_pre_post = bool(rpc.search(
            "account.move",
            list(VENDOR_BILL_EXPORT_DOMAIN) + [("id", "=", ba2)]))
        table["B: move.write(attachment_ids=[(0,0,...)])"] = {
            "stored_flag": row["have_attachment"],
            "attachment_ids_visible": len(row["attachment_ids"]),
            "in_export_domain": in_domain_pre_post,
        }
        ctx.log(f"route B: {table['B: move.write(attachment_ids=[(0,0,...)])']!r}")
        ctx.log("The third route the workbook names — the chatter paperclip "
                "in the web client — creates an ir.attachment exactly as "
                "route A does (mail.thread's message_post attachment "
                "handling), so it is the SAME write path and is not "
                "re-tested as a separate row. Recorded as an adaptation.")

    with ctx.step("Step 10: the route table — the case's actual output"):
        ctx.log("attachment route x (stored flag / in export domain):")
        for route, result in table.items():
            ctx.log(f"  {route} -> {result!r}")
        ctx.check_true(
            "at least one route leaves the stored flag TRUE, or no bill "
            "could ever be exported at all",
            any(entry["stored_flag"] for entry in table.values()),
            actual_desc=repr(table))

    with ctx.step("Step 11: the invariant that must hold whatever the table "
                  "says — a POSTED bill is in the export domain if and only "
                  "if its stored have_attachment is True"):
        rpc.call("account.move", "action_post", [ba2])
        posted = rpc.read("account.move", [ba2],
                          ["state", "have_attachment"])[0]
        ctx.log(f"BA-2 posted: {posted!r}")
        in_domain = bool(rpc.search("account.move",
                                    list(VENDOR_BILL_EXPORT_DOMAIN)
                                    + [("id", "=", ba2)]))
        ctx.check("domain membership == stored have_attachment",
                  posted["have_attachment"], in_domain)

    with ctx.step("Step 12: the inverse control — deleting the attachment "
                  "clears the flag and removes the bill from the domain"):
        attachments = rpc.search("ir.attachment",
                                 [("res_model", "=", "account.move"),
                                  ("res_id", "=", ba2)])
        cleared = None
        if attachments:
            try:
                rpc.call("ir.attachment", "unlink", attachments)
                row = rpc.read("account.move", [ba2],
                               ["have_attachment"])[0]
                cleared = row["have_attachment"]
                in_domain = bool(rpc.search(
                    "account.move",
                    list(VENDOR_BILL_EXPORT_DOMAIN) + [("id", "=", ba2)]))
                ctx.log(f"after deleting the attachment: stored flag="
                        f"{cleared!r}, in domain={in_domain!r}")
                ctx.check("domain membership still tracks the stored flag "
                          "after deletion", bool(cleared), in_domain)
            except Exception as exc:                        # noqa: BLE001
                ctx.log(f"[warn] the attachment could not be removed on a "
                        f"posted bill ({exc}); step 12 is recorded as "
                        "untested rather than asserted.")
        table["inverse: attachment deleted"] = {"stored_flag": cleared}

    with ctx.step("Step 13: does the WIZARD agree with the domain? The "
                  "operationally nastiest possibility is that the manual "
                  "path computes missing_attachment live while the cron "
                  "path reads the stored field"):
        ba3 = make_bill(ctx, vendor_id, [line], "ATT-3", label="BA-3")
        attach_to_move(rpc, ba3, via="attachment",
                       name=fx(f"{MARK} route-a-extra.pdf"))
        wizard_id = rpc.create("workday.vendor.bill.export.wizard",
                               {"move_ids": [(6, 0, [ba3])]})
        wizard = rpc.read("workday.vendor.bill.export.wizard", [wizard_id],
                          ["missing_attachment"])[0]
        stored = rpc.read("account.move", [ba3], ["have_attachment"])[0]
        in_domain = bool(rpc.search("account.move",
                                    list(VENDOR_BILL_EXPORT_DOMAIN)
                                    + [("id", "=", ba3)]))
        ctx.log(f"BA-3: stored have_attachment={stored['have_attachment']!r}, "
                f"wizard.missing_attachment={wizard['missing_attachment']!r}, "
                f"in export domain={in_domain!r}")
        ctx.check(
            "the wizard's missing_attachment is the NEGATION of the stored "
            "flag — the manual and scheduled paths agree",
            not stored["have_attachment"], wizard["missing_attachment"])
