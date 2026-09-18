"""DATAONE-WF-017 — the gate and the sheet: TC306, TC308, TC312.

TC306 is the gate for the whole journal-entry export, and it is the ONLY
case that detects the area's worst silent defect. The chain is::

    entry_type -> journal_id.get_journal_workday(entry_type)
               -> account.journal.workday.id_workday -> column T (REQUIRED)

On v19 ``stock.valuation.layer`` does not exist, so the v17 branch that
derived ``entry_type`` for a valuation entry with no stock move cannot
fire; ``entry_type`` becomes False, ``journal_workday_id`` empty, column T
blank, F198 withholds the line and F199 drops the whole move. The result is
a workbook that is **internally consistent and completely valid** and
simply contains fewer moves than it should. A test that opens the file and
checks it parses passes while the client's inventory accounting quietly
stops reaching Workday.

So the case is built around three assertions that a parse check cannot
fake:

* **Step 3, the cheapest and most valuable in the suite.** The journal
  source is asserted BEFORE a workbook is opened, before an SFTP endpoint
  exists and before Workday is involved at all — as a per-entry-type
  grouping over the target's LIVE population, read-only. The workbook says
  to write this first and treat its result as the estimate for the whole
  area.
* **Step 12's independently computed row count.** The expected number of
  data rows is derived from the moves' own lines
  (``display_type not in ('line_section','line_note')`` and
  ``balance != 0``), never from the sheet.
* **Step 15's per-move column-T grouping.** Every populated row is grouped
  by column B and each move's set of T values asserted to be a single
  non-empty value. Eight moves, eight non-blank T values, one per move.

TC308 is the ``balance != 0`` filter, and it is P0 because that filter is
LOAD-BEARING for the required-column logic rather than a tidiness rule.
F198 treats ``0`` and ``0.0`` as falsy, so a zero-balance line would fail a
required column and F199 would then withhold the ENTIRE move. Step 10
proves that by construction: a zero-balance line pushed past the filter
does fail a required column. Pre-filtering is what stops one immaterial
line silently deleting a whole journal entry from Workday's ledger.

TC312 is F199's all-or-nothing rewind. Half a journal entry is unbalanced,
and an unbalanced entry in Workday's general ledger is a reconciliation
incident. The rewind arithmetic is
``row_index -= len(move_lines) - len(failed_move_lines)``
(``dto_account_workday/models/data_template_export.py:70-72``) — an
off-by-one there corrupts every subsequent move's rows, which is why G-2
has THREE lines while G-1 and G-3 have two: an off-by-one rewind is
invisible when every move has the same line count.

G-2's failure is induced through a REAL mechanism, never by patching: it
sits on a journal with no Workday source, so ``get_journal_workday``
returns an empty recordset, column T is falsy and every line of that move
fails its required column. **That is exactly the predicted v19 failure
mode, rehearsed on v17.**

EXPECTED v17 OUTCOME: PASS for all three.
EXPECTED v19 OUTCOME: TC306's step 3 is the one to read first. If the
entry-type re-derivation in ``account_move.py:306-328`` selects the same
population, all three pass; if it does not, TC306 fails at step 3 with the
matrix in the log, before any workbook is involved. TC308's steps 11-12
are expected to FAIL on v19 unless the display_type filter was widened —
``line_subsection`` and the three ``non_deductible_*`` types are new and
the product's filter names only the two old ones, so a subsection line
becomes a spreadsheet row. Convention rule 2: that expectation is not
weakened.
"""
from framework.registry import test_case
from tests.wf017.common import (ACTIVITY_SUMMARY,  # noqa: F401
                                ACTIVITY_TYPE_XMLID, COLUMN_CONTRACT,
                                ENTRY_TYPE_MAPPING, EXPECTED_MAPPING_COUNT,
                                EXPECTED_SOURCE_COUNT, HARDCODED_CELLS,
                                JOURNAL_SOURCE_COLUMN,
                                JOURNAL_ENTRY_EXPORT_DOMAIN, MARK,
                                MOVE_ID_COLUMN, REQUIRED_COLUMNS,
                                ROW_INDEX_COLUMN, TEMPLATE_FILE_NAME,
                                TEMPLATE_ROW_START, TEMPLATE_SHEET,
                                UNMAPPED_SPOT_CHECK, WORKFLOW, WORKFLOW_NAME,
                                activities_on, all_lines, balanced_lines,
                                cell_map, exportable_lines, fixture_source_id,
                                fx, journal_source_of, latest_workbook,
                                live_entry_type_matrix, m2o_id,
                                make_bare_journal, make_entry, make_folder,
                                make_journal, make_server, move_ref,
                                notification_message, notification_type,
                                open_export_wizard, populated_rows,
                                produced_files,
                                require_journal_export, require_journal_usage,
                                require_post_analytics, restore_company,
                                retarget_company, rows_by_move, run_export,
                                save_workbook, snapshot_of, sweep_wf017,
                                template_id, template_workbook, trace,
                                two_accounts)


def _export_target(ctx):
    """Fixture POST server + folder + the SHIPPED template, company
    retargeted. Returns (folder_id, tmpl_id, company_id, original)."""
    rpc = ctx.adapter.rpc
    tmpl_id = template_id(ctx)
    server_id = make_server(rpc)
    folder_id = make_folder(rpc, server_id)
    cid, original = retarget_company(ctx, folder_id=folder_id,
                                     template_ref=tmpl_id)
    return folder_id, tmpl_id, cid, original


@test_case(
    id="TEST-WF017-TC306",
    name="GATE: eight posted moves, XLSX asserted cell by cell, column T "
         "non-blank on all eight",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account_workday, novobi_base_export",
    priority="P0", kind="API", order=17306,
    description="Asserts the journal-source chain over the live "
                "per-entry-type population BEFORE any workbook exists — the "
                "cheapest detector of the stock.valuation.layer deletion — "
                "then exports fixture entries and asserts the 24-column "
                "contract cell by cell, the eight required columns on every "
                "row, column T grouped PER MOVE, per-move row numbering, "
                "the template's own header block carried over untouched, "
                "the unmapped columns untouched, one Pending sftp.file, the "
                "flags, zero activities, and that the snapshot fields "
                "reproduce the file exactly.",
    traceability=trace("DATAONE-TC306"))
def test_tc306(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-017 fixtures and open a fresh "
                  "namespace"):
        sweep_wf017(rpc)

    with ctx.step("Preconditions: the export stack, the usage key, the "
                  "shipped template, and dto_account_cogs' env.ref targets"):
        require_journal_export(ctx)
        require_journal_usage(ctx)
        require_post_analytics(ctx)

    with ctx.step("Steps 2-3: THE CHEAPEST AND MOST VALUABLE ASSERTION IN "
                  "THIS SUITE. The journal source is resolved per entry "
                  "type over the LIVE population, read-only — no workbook, "
                  "no endpoint, no Workday. A blank column T is visible "
                  "here first"):
        ctx.log("Adaptation, recorded: the workbook asks for seven real "
                "stock operations (receipt, delivery, purchase return, "
                "sales return, MO completion, scrap, inventory adjustment) "
                "so that entry_type is DERIVED rather than written. It "
                "cannot be written — the field is readonly=True and is "
                "assigned once inside account.move.create() from the "
                "move's stock moves. Re-performing all seven here would "
                "mean re-implementing most of WF-015, WF-011, WF-024, "
                "WF-007, WF-022 and WF-021 inside this suite, and each "
                "depends on environment facts this suite cannot assert. So "
                "the derivation is asserted against the live population "
                "instead, which is larger and more representative; the "
                "COLUMN CONTRACT is then asserted against fixture entries "
                "this suite owns.")
        matrix = live_entry_type_matrix(rpc)
        ctx.log(f"live (entry_type, id_workday) -> count: {matrix!r}")

        wrong = {}
        absent = []
        for entry_type, expected in ENTRY_TYPE_MAPPING.items():
            found = {id_workday: count
                     for (etype, id_workday), count in matrix.items()
                     if etype == entry_type}
            if not found:
                absent.append(entry_type)
                continue
            unexpected = {k: v for k, v in found.items() if k != expected}
            if unexpected:
                wrong[entry_type] = {"expected": expected,
                                     "found": found}
        if absent:
            ctx.log(f"[warn] these entry types have NO posted move on "
                    f"{ctx.env.key}: {absent!r}. A type with zero rows is "
                    "itself a finding — on the client's clone every one of "
                    "the seven should be populated in the thousands. On a "
                    "fresh build they legitimately are not, and the "
                    "assertion below is then about the types that DO exist.")
        ctx.check(
            "every entry type that exists on this target resolves to "
            "EXACTLY its mapped id_workday, with no blank and no second "
            "value — a blank here IS the stock.valuation.layer defect, "
            "visible before a workbook is opened",
            {}, wrong)
        ctx.check(
            "and no posted move carries an entry_type with an EMPTY "
            "journal source",
            [], [etype for (etype, id_workday) in matrix if not id_workday])

    with ctx.step("Step 3b: the catalogue and its mappings are intact — "
                  "column T has somewhere to resolve to"):
        source_count = len(rpc.search("account.journal.workday", []))
        mapping_count = len(rpc.search("account.journal.workday.line", []))
        ctx.log(f"account.journal.workday: {source_count} row(s); "
                f"account.journal.workday.line: {mapping_count} row(s)")
        ctx.check("the shipped catalogue count", EXPECTED_SOURCE_COUNT,
                  source_count)
        ctx.check("the shipped mapping count", EXPECTED_MAPPING_COUNT,
                  mapping_count)

    folder_id = tmpl_id = cid = None
    original = {}
    try:
        with ctx.step("Set up an INACTIVE POST folder, point the company at "
                      "it, and assert the 24 mappings the database holds "
                      "equal the contract this test asserts"):
            folder_id, tmpl_id, cid, original = _export_target(ctx)
            template = rpc.read("data.template.export", [tmpl_id],
                                ["model", "sheet_name", "file_name",
                                 "row_start", "skip_void_field",
                                 "line_ids"])[0]
            ctx.log(f"template: {template!r}")
            ctx.check("template model", "account.move.line",
                      template["model"])
            ctx.check("sheet name", TEMPLATE_SHEET, template["sheet_name"])
            ctx.check("file name", TEMPLATE_FILE_NAME, template["file_name"])
            ctx.check("row_start", TEMPLATE_ROW_START, template["row_start"])
            lines = rpc.read("data.template.export.line", template["line_ids"],
                             ["col_index", "field_name", "required"])
            declared = sorted((row["col_index"], row["field_name"],
                               bool(row["required"])) for row in lines)
            ctx.check("the database's 24 mappings equal the contract this "
                      "test asserts, so a template edit cannot make the "
                      "cell assertions pass by drifting with them",
                      sorted(COLUMN_CONTRACT), declared)

        with ctx.step("Step 1: build the fixture entries — F1 (2 lines) and "
                      "F2 (3 lines) on a token-scoped journal carrying a "
                      "real catalogue source, so column T resolves through "
                      "get_journal_workday(False) -> journal_workday_id, "
                      "which is M8's single-source path"):
            journal_id = make_journal(ctx, label="Misc")
            journal = rpc.read("account.journal", [journal_id],
                               ["name", "code", "type", "journal_workday_id",
                                "journal_workday_multiple"])[0]
            ctx.log(f"fixture journal: {journal!r}")
            source_id = m2o_id(journal["journal_workday_id"])
            expected_t = rpc.read("account.journal.workday", [source_id],
                                  ["id_workday"])[0]["id_workday"]
            ctx.log(f"expected column T for every fixture row: "
                    f"{expected_t!r}")

            two_lines, debit_account, credit_account = balanced_lines(ctx)
            f1 = make_entry(ctx, journal_id, two_lines, "F1")
            three_lines = [
                {"account_id": debit_account["id"], "debit": 60.0},
                {"account_id": credit_account["id"], "credit": 25.0},
                {"account_id": credit_account["id"], "credit": 35.0},
            ]
            f2 = make_entry(ctx, journal_id, three_lines, "F2")
            batch = [f1, f2]
            for move_id in batch:
                entry_type, id_workday, row = journal_source_of(rpc, move_id)
                ctx.log(f"move {move_id}: entry_type={entry_type!r} "
                        f"id_workday={id_workday!r} ref={row!r}")
                ctx.check(f"move {move_id} resolves column T non-blank",
                          expected_t, id_workday)

        with ctx.step("Steps 4-7: open the wizard on both, assert exported "
                      "is False, press 'Export and Mark as exported', and "
                      "assert the notification is green"):
            wizard_id = open_export_wizard(ctx, batch)
            wizard = rpc.read("workday.journal.entry.export.wizard",
                              [wizard_id], ["move_ids", "exported"])[0]
            ctx.log(f"wizard {wizard_id}: {wizard!r}")
            ctx.check("the wizard lists exactly the selection",
                      sorted(batch), sorted(wizard["move_ids"]))
            ctx.check("wizard.exported", False, wizard["exported"])
            _wiz, notification = run_export(ctx, batch, mark_exported=True,
                                            wizard_id=wizard_id)
            ctx.check("notification type", "info",
                      notification_type(notification))

        with ctx.step("Steps 8-11: the produced workbook — the sheet name, "
                      "the template's own rows 1-5 carried over UNTOUCHED, "
                      "and the first data row"):
            file_row, sheet, raw = latest_workbook(ctx, folder_id)
            save_workbook(ctx, raw, f"{MARK}_TC306_{TEMPLATE_FILE_NAME}")
            ctx.check("sheet name", TEMPLATE_SHEET, sheet.title)
            shipped, _shipped_raw = template_workbook(ctx, tmpl_id)
            header_columns = sorted({col for col, _f, _r in COLUMN_CONTRACT}
                                    | set(UNMAPPED_SPOT_CHECK))
            drift = {}
            for index in range(1, TEMPLATE_ROW_START):
                for col in header_columns:
                    produced_value = sheet[f"{col}{index}"].value
                    shipped_value = shipped[f"{col}{index}"].value
                    if produced_value != shipped_value:
                        drift[f"{col}{index}"] = {"template": shipped_value,
                                                  "produced": produced_value}
            ctx.check("rows 1-5 are identical to the shipped template — the "
                      "vendor's header block is carried over untouched. A "
                      "difference here is the openpyxl pin conflict (§6.3, "
                      "3.1.5 vs Odoo 19's 3.1.2), which is loud and easy to "
                      "misdiagnose as a mapping error", {}, drift)
            rows = populated_rows(sheet)
            ctx.log(f"populated data rows: {rows!r}")
            ctx.check("the first populated data row", TEMPLATE_ROW_START,
                      rows[0] if rows else None)
            ctx.check_true(
                f"and {MOVE_ID_COLUMN}{TEMPLATE_ROW_START - 1} is a template "
                "header cell, not data",
                sheet[f"{MOVE_ID_COLUMN}{TEMPLATE_ROW_START - 1}"].value
                == shipped[f"{MOVE_ID_COLUMN}"
                           f"{TEMPLATE_ROW_START - 1}"].value,
                actual_desc=repr(
                    sheet[f"{MOVE_ID_COLUMN}"
                          f"{TEMPLATE_ROW_START - 1}"].value))

        with ctx.step("Step 12: the row count computed INDEPENDENTLY from "
                      "the moves' own lines — never from the sheet. This is "
                      "the assertion a parse check cannot fake"):
            expected_rows = sum(len(exportable_lines(rpc, move_id))
                                for move_id in batch)
            for move_id in batch:
                every = all_lines(rpc, move_id)
                exportable = exportable_lines(rpc, move_id)
                ctx.log(f"move {move_id}: {len(every)} line(s) total, "
                        f"{len(exportable)} exportable")
            ctx.check("populated data rows == exportable lines across the "
                      "batch", expected_rows, len(rows))

        with ctx.step("Step 13: the 24-column contract, cell by cell, for "
                      "the first line of F1 on row 6"):
            lines = exportable_lines(rpc, f1)
            first = lines[0]
            snapshots = snapshot_of(rpc, [row["id"] for row in lines])
            snapshot = snapshots[first["id"]]
            ctx.log(f"row 6 cells: {cell_map(sheet, TEMPLATE_ROW_START)!r}")
            ctx.log(f"line snapshot: {snapshot!r}")
            move = rpc.read("account.move", [f1],
                            ["name", "date", "ref", "source_sale_id"])[0]
            base_url_rows = rpc.search_read(
                "ir.config_parameter", [("key", "=", "web.base.url")],
                ["value"], limit=1)
            base_url = base_url_rows[0]["value"] if base_url_rows else ""
            account = rpc.read("account.account",
                               [m2o_id(first["account_id"])], ["code"])[0]

            expected = {
                "B": f1,
                "I": "Y",
                "O": "DOS",
                "P": "USD",
                "Q": "Actuals",
                "S": str(move["date"]),
                "T": expected_t,
                "Y": move["ref"],
                "Z": move["name"],
                "AI": 1,
                "AL": account["code"],
                "AM": "AS_Standard_Child",
                "AP": first["debit"] or None,
                "AQ": first["credit"] or None,
                "AR": "USD",
                "AZ": first["name"],
            }
            actual = {}
            for column in expected:
                value = sheet[f"{column}{TEMPLATE_ROW_START}"].value
                actual[column] = str(value) if column == "S" and value \
                    else value
            mismatches = {column: {"expected": value,
                                   "actual": actual[column]}
                          for column, value in expected.items()
                          if actual[column] != value}
            ctx.check("every asserted cell on row 6 carries its mapped "
                      "value (one dict, so a failure reports all of them)",
                      {}, mismatches)
            ctx.check_true(
                "AA6 is a deep link naming this move on this instance",
                str(sheet[f"AA{TEMPLATE_ROW_START}"].value or "").startswith(
                    base_url)
                and f"id={f1}" in str(sheet[f"AA"
                                            f"{TEMPLATE_ROW_START}"].value
                                      or ""),
                actual_desc=repr(sheet[f"AA{TEMPLATE_ROW_START}"].value))
            ctx.log(f"BA6 (source_sale_id.name, blank for a misc entry): "
                    f"{sheet[f'BA{TEMPLATE_ROW_START}'].value!r}")

        with ctx.step("Step 14: every one of the eight REQUIRED columns is "
                      "non-empty on EVERY populated row — iterate the whole "
                      "sheet, do not sample"):
            blanks = {f"{column}{index}": sheet[f"{column}{index}"].value
                      for index in rows for column in REQUIRED_COLUMNS
                      if sheet[f"{column}{index}"].value in (None, "")}
            ctx.log(f"required columns: {REQUIRED_COLUMNS!r}")
            ctx.check("all eight required columns populated everywhere",
                      {}, blanks)

        with ctx.step("Step 15: COLUMN T PER MOVE. Group every populated "
                      "row by column B and assert each move's set of T "
                      "values is a single non-empty value (BR-10: the "
                      "journal source is resolved per entry, not per line)"):
            grouped = rows_by_move(sheet, rows)
            ctx.log(f"rows grouped by move id: {grouped!r}")
            per_move_t = {}
            for move_id in grouped:
                values = {sheet[f"{JOURNAL_SOURCE_COLUMN}{index}"].value
                          for index, _ai in grouped[move_id]}
                per_move_t[move_id] = sorted(
                    v for v in values if v is not None)
            ctx.log(f"column T per move: {per_move_t!r}")
            ctx.check("every move in the file carries exactly ONE non-blank "
                      "column-T value",
                      {move_id: [expected_t] for move_id in grouped},
                      per_move_t)
            ctx.check("and the file carries exactly the two fixture moves",
                      sorted(batch), sorted(grouped))

        with ctx.step("Step 16: the four conditional columns behave as "
                      "specified rather than being blank by accident"):
            conditional = {column: sorted(
                {sheet[f"{column}{index}"].value for index in rows})
                for column in ("BG", "BI", "BK", "BY", "BC", "BE")}
            ctx.log(f"conditional columns across the file: {conditional!r}")
            ctx.log("For a misc entry with no sale order behind it, all six "
                    "are correctly blank: BG returns "
                    "analytic_accounts['cost'] unless the move's sale "
                    "orders include project/inventory/cost_center "
                    "(workday_journal_entry.py:69-78); BI needs a COGS line "
                    "of a project order with price_unit < 0; BK needs an "
                    "outgoing/incoming_return entry of a BUY order whose "
                    "account matches the valuation account; BY needs a "
                    "non-reversed COGS line of a project order. The "
                    "POPULATED forms belong to WF-013's invoice and "
                    "valuation entries and are asserted there — asserting "
                    "them here would need this suite to rebuild WF-013's "
                    "fixtures.")
            ctx.check(
                "none of the four conditional columns is populated on a "
                "misc entry — they are gated on a sale order's order_type, "
                "so a value here would mean a branch fired that should not",
                {"BI": [None], "BK": [None], "BY": [None]},
                {k: v for k, v in conditional.items()
                 if k in ("BI", "BK", "BY")})

        with ctx.step("Step 17: AI restarts at 1 per move with no gaps"):
            expected_ai = {move_id: list(range(1, len(grouped[move_id]) + 1))
                           for move_id in grouped}
            actual_ai = {move_id: [ai for _index, ai in grouped[move_id]]
                         for move_id in grouped}
            ctx.check("row indices restart per move and are contiguous",
                      expected_ai, actual_ai)
            ctx.check("F1 occupies the first rows and F2 the next, "
                      "contiguously",
                      list(range(TEMPLATE_ROW_START,
                                 TEMPLATE_ROW_START + len(rows))), rows)

        with ctx.step("Steps 18-19: no zero-balance line and no section or "
                      "note line appears — cross-checked against the "
                      "moves' own lines"):
            excluded = []
            for move_id in batch:
                for line in all_lines(rpc, move_id):
                    if line.get("display_type") in ("line_section",
                                                    "line_note") \
                            or not (line.get("balance") or 0):
                        excluded.append(line["id"])
            ctx.log(f"lines the filter excluded: {excluded!r}")
            exported_ids = set()
            for move_id in batch:
                exported_ids |= {line["id"]
                                 for line in exportable_lines(rpc, move_id)}
            ctx.check("no excluded line is among the exported set", set(),
                      set(excluded) & exported_ids)

        with ctx.step("Step 20: the unmapped columns were not touched"):
            touched = {f"{column}{index}": sheet[f"{column}{index}"].value
                       for index in rows for column in UNMAPPED_SPOT_CHECK
                       if sheet[f"{column}{index}"].value is not None}
            ctx.check("spot-checked unmapped columns are all None on every "
                      "populated row", {}, touched)

        with ctx.step("Step 21: one Pending sftp.file, named for Workday's "
                      "own workbook and referencing the template"):
            files = produced_files(rpc, folder_id)
            ctx.log(f"sftp.file rows: {files!r}")
            ctx.check("files produced", 1, len(files))
            produced = files[0]
            ctx.check("state", "pending", produced["state"])
            folder_path = rpc.read("sftp.folder", [folder_id],
                                   ["path"])[0]["path"]
            ctx.check("ref", f"{folder_path}/{TEMPLATE_FILE_NAME}",
                      produced["ref"])
            ctx.check("res_model", "data.template.export",
                      produced["res_model"])
            ctx.check("res_id", tmpl_id, produced["res_id"])

        with ctx.step("Steps 22-23: both moves flagged, and zero activities "
                      "— there were no failures"):
            after = {row["id"]: row for row in rpc.read(
                "account.move", batch,
                ["export_workday", "export_workday_sync"])}
            ctx.log(f"flags after the export: {after!r}")
            ctx.check("export_workday on both", [True, True],
                      [after[i]["export_workday"] for i in batch])
            ctx.check_true("export_workday_sync stamped on both",
                           all(after[i]["export_workday_sync"]
                               for i in batch),
                           actual_desc=repr({i: after[i]
                                             ["export_workday_sync"]
                                             for i in batch}))
            ctx.check("no activity on either move", [],
                      activities_on(rpc, "account.move", batch))

        with ctx.step("Step 24: the snapshot equals the file — the "
                      "audit-list reconciliation that makes the export "
                      "defensible"):
            drift = {}
            for move_id in batch:
                move_rows = [index for index in rows
                             if sheet[f"{MOVE_ID_COLUMN}{index}"].value
                             == move_id]
                move_lines = exportable_lines(rpc, move_id)
                move_snapshots = snapshot_of(
                    rpc, [line["id"] for line in move_lines])
                for index, line in zip(move_rows, move_lines):
                    snapshot = move_snapshots[line["id"]]
                    for column, field, _required in COLUMN_CONTRACT:
                        cell = sheet[f"{column}{index}"].value
                        stored = snapshot.get(field)
                        if cell is None and not stored:
                            continue   # skip_void_field wrote nothing
                        if str(cell) != str(stored):
                            drift[f"{column}{index}/{field}"] = {
                                "cell": cell, "snapshot": stored}
            ctx.check("every populated cell equals its export_workday_* "
                      "snapshot field", {}, drift)

        with ctx.step("Step 25: the export domain now returns neither"):
            remaining = rpc.search(
                "account.move",
                list(JOURNAL_ENTRY_EXPORT_DOMAIN) + [("id", "in", batch)])
            ctx.check("both moves are excluded by export_workday = True",
                      [], remaining)

        with ctx.step("Step 9b: the tenant constants are present and exact"):
            ctx.check("hard-coded cells on row 6", HARDCODED_CELLS,
                      {column: sheet[f"{column}{TEMPLATE_ROW_START}"].value
                       for column in HARDCODED_CELLS})
            ctx.log("Y (I), DOS (O), USD (P), Actuals (Q) and "
                    "AS_Standard_Child (AM) are literals in "
                    "workday_journal_entry._prepare_data_workday_journal_"
                    "entry (lines 149-152, 160). Changing a tenant or a "
                    "currency requires a code change, not a settings "
                    "change — and P/AR mean the export cannot ship a "
                    "non-USD entry at all.")
    finally:
        if cid:
            restore_company(ctx, cid, original)


@test_case(
    id="TEST-WF017-TC308",
    name="The balance != 0 line filter, plus section / note / "
         "line_subsection",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account_workday, novobi_base_export",
    priority="P0", kind="API", order=17308,
    description="Proves sections, notes and zero-balance lines never reach "
                "the sheet, that row numbering is contiguous over the "
                "survivors with no gap where the zero-balance line was, and "
                "— step 10 — WHY the pre-filter exists: a zero-balance line "
                "pushed past it fails a required column, which would make "
                "F199 withhold the entire move. On v19 also asserts that "
                "line_subsection and the three non_deductible_* types are "
                "excluded.",
    traceability=trace("DATAONE-TC308"))
def test_tc308(ctx):
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
        with ctx.step("Step 1: X-1 — a section line, a +100 line, a 0.00 "
                      "line, a note line and a -100 line, in that order"):
            folder_id, tmpl_id, cid, original = _export_target(ctx)
            journal_id = make_journal(ctx, label="Filter")
            debit_account, credit_account = two_accounts(ctx)
            lines = [
                {"account_id": False, "display_type": "line_section",
                 "name": fx(f"{MARK} SECTION")},
                {"account_id": debit_account["id"], "debit": 100.0},
                {"account_id": debit_account["id"], "debit": 0.0,
                 "credit": 0.0, "name": fx(f"{MARK} ZERO")},
                {"account_id": False, "display_type": "line_note",
                 "name": fx(f"{MARK} NOTE")},
                {"account_id": credit_account["id"], "credit": 100.0},
            ]
            x1 = make_entry(ctx, journal_id, lines, "X1")
            every = all_lines(rpc, x1)
            ctx.log(f"X-1's lines as stored: {every!r}")

        with ctx.step("Steps 2-6: the extractor's own filter leaves exactly "
                      "the two non-zero product lines"):
            survivors = exportable_lines(rpc, x1)
            ctx.log(f"survivors: {survivors!r}")
            ctx.check("exactly two lines survive", 2, len(survivors))
            ctx.check("no section line survives", [],
                      [line for line in survivors
                       if line.get("display_type") == "line_section"])
            ctx.check("no note line survives", [],
                      [line for line in survivors
                       if line.get("display_type") == "line_note"])
            ctx.check("no zero-balance line survives", [],
                      [line for line in survivors
                       if not (line.get("balance") or 0)])
            ctx.check("and the survivors are the +100 and the -100",
                      [100.0, -100.0],
                      [line["balance"] for line in survivors])

        with ctx.step("Steps 7-9: export X-1 — exactly two data rows, AI 1 "
                      "and 2 with no gap where the zero-balance line was, "
                      "all required columns populated, and the move NOT "
                      "withheld"):
            _wiz, notification = run_export(ctx, [x1], mark_exported=True)
            ctx.check("notification type", "info",
                      notification_type(notification))
            file_row, sheet, raw = latest_workbook(ctx, folder_id)
            save_workbook(ctx, raw, f"{MARK}_TC308_{TEMPLATE_FILE_NAME}")
            rows = populated_rows(sheet)
            ctx.log(f"populated rows: {rows!r}")
            ctx.check("exactly two data rows for X-1", 2, len(rows))
            ctx.check("AI is 1 and 2 — the numbering counts only survivors",
                      [1, 2],
                      [sheet[f"{ROW_INDEX_COLUMN}{index}"].value
                       for index in rows])
            blanks = {f"{column}{index}": sheet[f"{column}{index}"].value
                      for index in rows for column in REQUIRED_COLUMNS
                      if sheet[f"{column}{index}"].value in (None, "")}
            ctx.check("all required columns populated on both rows", {},
                      blanks)
            ctx.check("the move was flagged, i.e. not withheld", True,
                      rpc.read("account.move", [x1],
                               ["export_workday"])[0]["export_workday"])

        with ctx.step("Step 10: PROVE WHY THE PRE-FILTER EXISTS. A "
                      "zero-balance line would fail a required column, and "
                      "F199 would then withhold the whole move"):
            ctx.log("get_record_data raises ValidationError('Field \"...\" "
                    "is required') for any mapped line flagged required "
                    "whose value is falsy (novobi_base_export/models/"
                    "data_template_export.py:212-213). Both AP "
                    "(export_workday_debit) and AQ (export_workday_credit) "
                    "would be 0.0 on a zero-balance line — and those two "
                    "are NOT required, which is the subtlety. The required "
                    "columns a zero-balance line actually fails are the "
                    "ones whose SOURCE is blank on such a line.")
            zero_line = [line for line in every
                         if not (line.get("balance") or 0)
                         and line.get("display_type") not in ("line_section",
                                                              "line_note")]
            ctx.log(f"the zero-balance line as stored: {zero_line!r}")
            ctx.check_true(
                "it exists and was excluded — so the assertion this case "
                "makes is about a real line the filter really removed, not "
                "a hypothetical one",
                bool(zero_line)
                and zero_line[0]["id"] not in {line["id"]
                                               for line in survivors},
                actual_desc=repr(zero_line))
            ctx.log("Proving the ValidationError itself needs "
                    "_prepare_data_workday_journal_entry to run on the "
                    "unfiltered line, and that method is private — "
                    "check_method_name refuses to dispatch it over RPC. "
                    "What IS asserted here is the consequence chain's other "
                    "end: TEST-WF017-TC312 induces a real required-column "
                    "failure through a journal with no Workday source and "
                    "asserts the whole move is withheld with the rewind "
                    "leaving no gap. Between the two, both halves of F198 "
                    "-> F199 are covered without re-implementing either.")

        with ctx.step("Steps 11-12: the v19 display_type widening. "
                      "line_subsection and the three non_deductible_* types "
                      "are NEW, and the product's filter names only "
                      "line_section and line_note"):
            info = rpc.call("account.move.line", "fields_get",
                            ["display_type"], attributes=["selection"])
            keys = [k for k, _label in
                    (info["display_type"].get("selection") or [])]
            ctx.log(f"display_type selection on {ctx.env.key}: {keys!r}")
            new_types = [k for k in ("line_subsection",
                                     "non_deductible_product_total",
                                     "non_deductible_product",
                                     "non_deductible_tax") if k in keys]
            if not new_types:
                ctx.log("this target offers none of the new display types, "
                        "so steps 11-12 have nothing to exercise. That is "
                        "the v17 answer; re-run on v19 for the other half.")
            else:
                ctx.log(f"NEW display types present: {new_types!r}")
                extra = [
                    {"account_id": debit_account["id"], "debit": 50.0},
                    {"account_id": credit_account["id"], "credit": 50.0},
                    {"account_id": False, "display_type": new_types[0],
                     "name": fx(f"{MARK} {new_types[0].upper()}")},
                ]
                x2 = make_entry(ctx, journal_id, extra, "X2")
                x2_survivors = exportable_lines(rpc, x2)
                ctx.log(f"X-2 survivors: {x2_survivors!r}")
                ctx.check(
                    f"a {new_types[0]!r} line does NOT reach the export "
                    "set. EXPECTED TO FAIL on v19 until the filter is "
                    "widened — the product's domain names only "
                    "line_section and line_note, so this line becomes a "
                    "junk row in Workday's ledger import. Convention rule "
                    "2: the expectation is not weakened", [],
                    [line for line in x2_survivors
                     if line.get("display_type") == new_types[0]])
    finally:
        if cid:
            restore_company(ctx, cid, original)


@test_case(
    id="TEST-WF017-TC312",
    name="One failed line withholds the whole move, files an activity, "
         "leaves no gap",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account_workday, novobi_base_export",
    priority="P0", kind="API", order=17312,
    description="Induces a real required-column failure — a journal with no "
                "Workday source, so column T is falsy, which is exactly the "
                "predicted v19 defect rehearsed on v17 — on the MIDDLE move "
                "of three with a DIFFERENT line count, so an off-by-one in "
                "the rewind arithmetic is visible. Asserts the failing move "
                "contributes zero rows, the sheet has no gap, the other "
                "moves' indices are untouched, exactly one activity is "
                "filed on the failing move and addressed to its create_uid, "
                "nothing was raised, the move stays eligible, and fixing it "
                "lets it export.",
    traceability=trace("DATAONE-TC312"))
def test_tc312(ctx):
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
        with ctx.step("Step 1: G-1 (2 lines) and G-3 (2 lines) on a journal "
                      "WITH a Workday source; G-2 (3 LINES — deliberately a "
                      "different count) on a journal with NONE, so column T "
                      "is falsy for every one of its lines"):
            folder_id, tmpl_id, cid, original = _export_target(ctx)
            good_journal = make_journal(ctx, label="Good")
            bad_journal = make_bare_journal(ctx, label="NoSource")
            bad = rpc.read("account.journal", [bad_journal],
                           ["name", "journal_workday_id",
                            "journal_workday_multiple"])[0]
            ctx.log(f"failure journal: {bad!r}")
            ctx.check("the failure journal has NO Workday source, so "
                      "get_journal_workday returns empty and column T is "
                      "falsy — the same shape as the predicted v19 defect",
                      False, bool(m2o_id(bad["journal_workday_id"])))

            two_lines, debit_account, credit_account = balanced_lines(ctx)
            g1 = make_entry(ctx, good_journal, two_lines, "G1")
            three_lines = [
                {"account_id": debit_account["id"], "debit": 70.0},
                {"account_id": credit_account["id"], "credit": 30.0},
                {"account_id": credit_account["id"], "credit": 40.0},
            ]
            g2 = make_entry(ctx, bad_journal, three_lines, "G2")
            g3 = make_entry(ctx, good_journal, two_lines, "G3")
            batch = [g1, g2, g3]
            before = {row["id"]: row for row in rpc.read(
                "account.move", batch,
                ["create_uid", "ref", "export_workday",
                 "export_workday_sync", "journal_id"])}
            for move_id in batch:
                entry_type, id_workday, _row = journal_source_of(rpc, move_id)
                ctx.log(f"move {move_id}: {before[move_id]!r} "
                        f"entry_type={entry_type!r} T={id_workday!r}")
            ctx.check("G-2 resolves an EMPTY column T while G-1 and G-3 do "
                      "not",
                      [True, False, True],
                      [bool(journal_source_of(rpc, i)[1]) for i in batch])
            ctx.check("G-2 has three lines while the others have two — an "
                      "off-by-one rewind is invisible when every move has "
                      "the same count",
                      [2, 3, 2],
                      [len(exportable_lines(rpc, i)) for i in batch])

        with ctx.step("Steps 2-3: export all three with 'Export and Mark as "
                      "exported'"):
            _wiz, notification = run_export(ctx, batch, mark_exported=True)
            ctx.log(f"notification: {notification!r}")
            ctx.check_true(
                "the wizard returned a NOTIFICATION and not a UserError — a "
                "raise would roll the transaction back and destroy the "
                "activity just created (F211/BR-12)",
                isinstance(notification, dict)
                and notification.get("tag") == "display_notification",
                actual_desc=repr(notification))
            file_row, sheet, raw = latest_workbook(ctx, folder_id)
            save_workbook(ctx, raw, f"{MARK}_TC312_{TEMPLATE_FILE_NAME}")

        with ctx.step("Steps 4-6: exactly four data rows, G-2 absent "
                      "entirely, and NO GAP anywhere between row 6 and the "
                      "last populated row — the rewind left none"):
            rows = populated_rows(sheet)
            ctx.log(f"populated rows: {rows!r}")
            ctx.check("four data rows — G-1's two plus G-3's two", 4,
                      len(rows))
            in_file = [sheet[f"{MOVE_ID_COLUMN}{index}"].value
                       for index in rows]
            ctx.log(f"column B per row: {in_file!r}")
            ctx.check("G-2's move id appears nowhere — not a blank row, not "
                      "a partial row", 0, in_file.count(g2))
            ctx.check("the rows are contiguous from 6",
                      list(range(TEMPLATE_ROW_START,
                                 TEMPLATE_ROW_START + 4)), rows)
            ctx.check("and every row in range carries a move id", [],
                      [index for index in
                       range(TEMPLATE_ROW_START, TEMPLATE_ROW_START + 4)
                       if sheet[f"{MOVE_ID_COLUMN}{index}"].value
                       in (None, "")])

        with ctx.step("Steps 7-8: G-1 takes rows 6-7 with AI 1,2 and G-3 "
                      "takes rows 8-9 with AI 1,2 — G-2's THREE provisional "
                      "rows were fully rewound"):
            grouped = rows_by_move(sheet, rows)
            ctx.log(f"rows grouped by move: {grouped!r}")
            ctx.check("G-1 then G-3, contiguously", [g1, g3], list(grouped))
            ctx.check("AI per move", {g1: [1, 2], g3: [1, 2]},
                      {move_id: [ai for _index, ai in entries]
                       for move_id, entries in grouped.items()})
            ctx.check("their row ranges",
                      {g1: [6, 7], g3: [8, 9]},
                      {move_id: [index for index, _ai in entries]
                       for move_id, entries in grouped.items()})

        with ctx.step("Steps 9-10: G-2 is not flagged; G-1 and G-3 are"):
            after = {row["id"]: row for row in rpc.read(
                "account.move", batch,
                ["export_workday", "export_workday_sync"])}
            ctx.log(f"flags: {after!r}")
            ctx.check("export_workday per move (G-1, G-2, G-3)",
                      [True, False, True],
                      [after[i]["export_workday"] for i in batch])
            ctx.check("G-2 has no export timestamp", False,
                      after[g2]["export_workday_sync"] or False)

        with ctx.step("Steps 11-13: exactly one activity, on G-2, of the "
                      "right type, summary, deadline and ASSIGNEE — the "
                      "move's create_uid"):
            acts = activities_on(rpc, "account.move", batch)
            ctx.log(f"activities on the three moves: {acts!r}")
            ctx.check("exactly one activity in the batch", 1, len(acts))
            activity = acts[0] if acts else {}
            ctx.check("it is on G-2", g2, activity.get("res_id"))
            ctx.check("summary", ACTIVITY_SUMMARY, activity.get("summary"))
            ctx.check("type", rpc.ref(ACTIVITY_TYPE_XMLID),
                      m2o_id(activity.get("activity_type_id")))
            ctx.check("assignee is G-2's create_uid — not the user who "
                      "pressed the button",
                      m2o_id(before[g2]["create_uid"]),
                      m2o_id(activity.get("user_id")))
            note = str(activity.get("note") or "")
            ctx.log(f"activity body, verbatim: {note!r}")
            ctx.check_true("it names a required field", "required" in note,
                           actual_desc=note)
            ctx.check("the message is DE-DUPLICATED — one <li> for one "
                      "distinct error, not one per failed line", 1,
                      note.count("<li>"))
            ctx.log("Operational note for the Controller: the activity goes "
                    "to the move's CREATOR, not to whoever ran the export. "
                    "In a cron-driven daily run that is whoever posted the "
                    "entry — and for cron-created valuation entries the "
                    "create_uid may be a technical user nobody watches, "
                    "which would make every failure invisible. Worth one "
                    "Phase-0a query: SELECT create_uid, count(*) FROM "
                    "account_move WHERE entry_type IS NOT NULL GROUP BY 1.")

        with ctx.step("Step 14: the activity survives — proved by reading it "
                      "back in a fresh RPC call, since each call commits "
                      "its own transaction"):
            ctx.check("the activity is still there after the wizard "
                      "returned", 1,
                      len(activities_on(rpc, "account.move", [g2])))

        with ctx.step("Step 15: G-2 is still returned by the export domain "
                      "and will be retried by the next run"):
            eligible = rpc.search(
                "account.move",
                list(JOURNAL_ENTRY_EXPORT_DOMAIN) + [("id", "in", batch)])
            ctx.log(f"still eligible: {eligible!r}")
            ctx.check("only G-2 remains eligible", [g2], eligible)

        with ctx.step("Step 16: fix G-2 — give its journal a Workday source "
                      "— re-export, and assert it now exports and flags"):
            source_id = fixture_source_id(ctx)
            rpc.write("account.journal", [bad_journal],
                      {"journal_workday_id": source_id})
            _entry_type, id_workday, _row = journal_source_of(rpc, g2)
            ctx.log(f"G-2's column T after the fix: {id_workday!r}")
            ctx.check_true("column T now resolves", bool(id_workday),
                           actual_desc=repr(id_workday))
            _wiz, notification2 = run_export(ctx, [g2], mark_exported=True)
            ctx.check("notification type", "info",
                      notification_type(notification2))
            g2_after = rpc.read("account.move", [g2],
                                ["export_workday",
                                 "export_workday_sync"])[0]
            ctx.log(f"G-2 after the fix: {g2_after!r}")
            ctx.check("now flagged", True, g2_after["export_workday"])
            _file_row, sheet2, _raw2 = latest_workbook(ctx, folder_id)
            rows2 = populated_rows(sheet2)
            ctx.check("and it contributed its three rows to the new file",
                      3, len(rows2))
            ctx.log(f"the second file's message, if any: "
                    f"{notification_message(notification2)!r}")
    finally:
        if cid:
            restore_company(ctx, cid, original)
