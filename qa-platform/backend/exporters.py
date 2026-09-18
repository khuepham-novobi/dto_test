"""Excel and Markdown exporters for the test-case registry and run results.

Everything here is built from what the store already persists — the workbook
registry and the recorded executions. Nothing is recomputed or inferred, so an
exported file and the dashboard always agree.

The run export (:func:`run_workbook`) fills a COPY of the source workbook
rather than inventing its own layout: QA plans the session in
``DataOne_v19_Test_Suite_and_Workflows_v1.0.xlsx`` and signs it off in the
same file, so a run must hand back that shape — same nine sheets, same
columns, same live ``Suite Overview`` counts. The original on disk is never
written to (Read Me: the workbook is the source of truth).

openpyxl is already a dependency (scripts/sync_registry.py reads the workbook
with it); write support needs no new package.
"""
from __future__ import annotations

import io
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

# Same id shape the store indexes executions by — one definition, so a
# traceability block that maps to a workbook row here maps there too.
from backend.store import _TC_ID_RE as TC_ID_RE

ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------- styling
HEAD_FILL = PatternFill("solid", fgColor="1F3247")
HEAD_FONT = Font(color="FFFFFF", bold=True, size=10)
WRAP = Alignment(vertical="top", wrap_text=True)
TOP = Alignment(vertical="top")

#: Cell tint per canonical status. Keeps a 3,000-row sheet scannable without
#: the reader having to build their own conditional formatting.
STATUS_FILL = {
    "PASS": "1E7A3C", "PASSED": "1E7A3C",
    "FAIL": "A32B22", "FAILED": "A32B22",
    "ERROR": "9A5B12", "BLOCKED": "5B2F73",
    "SKIPPED": "6B5D12", "NOT_RUN": "3A4552",
    "NOT_IMPLEMENTED": "3A4552", "MANUAL": "3A4552",
    "NOT_APPLICABLE": "3A4552", "RUNNING": "1B4C77", "QUEUED": "3A4552",
}


def _ts(value) -> str:
    if not value:
        return ""
    return datetime.fromtimestamp(
        float(value), tz=timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")


def _flat(value) -> str:
    """Anything the store may hold in a column into a single Excel cell.

    Excel rejects control characters and caps a cell at 32,767 characters; a
    long traceback silently corrupts the file without this.
    """
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        value = ", ".join(str(v) for v in value)
    elif isinstance(value, dict):
        value = json.dumps(value, ensure_ascii=False, default=str)
    text = str(value)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", text)
    return text[:32000] + (" ...[truncated]" if len(text) > 32000 else "")


def _sheet(wb, title: str, columns: list, rows: list,
           status_cols: tuple = (), freeze: str = "A2",
           table_name: str | None = None):
    """One formatted sheet. `columns` is [(header, width), ...]."""
    ws = wb.create_sheet(title[:31])
    ws.append([c[0] for c in columns])
    for i, (_, width) in enumerate(columns, start=1):
        ws.column_dimensions[get_column_letter(i)].width = width
    for cell in ws[1]:
        cell.fill, cell.font, cell.alignment = HEAD_FILL, HEAD_FONT, WRAP
    for row in rows:
        ws.append([_flat(v) for v in row])
    for r in range(2, ws.max_row + 1):
        for c in range(1, len(columns) + 1):
            cell = ws.cell(row=r, column=c)
            cell.alignment = WRAP if columns[c - 1][1] > 40 else TOP
            if c in status_cols:
                colour = STATUS_FILL.get(str(cell.value).strip().upper())
                if colour:
                    cell.fill = PatternFill("solid", fgColor=colour)
                    cell.font = Font(color="FFFFFF", bold=True, size=10)
    ws.freeze_panes = freeze
    # An Excel table gives the reader filter dropdowns for free. Skipped on an
    # empty sheet: a table with a header row and no body row is invalid and
    # Excel refuses to open the file.
    if table_name and ws.max_row > 1:
        ref = "A1:%s%d" % (get_column_letter(len(columns)), ws.max_row)
        table = Table(displayName=table_name, ref=ref)
        table.tableStyleInfo = TableStyleInfo(
            name="TableStyleMedium2", showRowStripes=True)
        ws.add_table(table)
    return ws


def _new_workbook() -> Workbook:
    """A workbook with openpyxl's default sheet removed.

    Dropping it up front means sheets land in creation order, so Summary is
    the tab the file opens on without any move_sheet juggling.
    """
    wb = Workbook()
    del wb[wb.sheetnames[0]]
    return wb


def _save(wb) -> bytes:
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ------------------------------------------------- full test-case registry
TC_COLUMNS = [
    ("Test Case ID", 18), ("Workflow", 18), ("Workflow Name", 30),
    ("Seq", 6), ("Title", 52), ("Priority", 9), ("Test Type", 16),
    ("Role", 18), ("Modules", 26), ("Suite", 16), ("Suite Name", 24),
    ("Execution Phase", 16), ("In Scope", 9),
    ("Automation Type", 16), ("Automation Status", 18), ("Automation Wave", 16),
    ("Automation Approach", 46), ("Automated By", 30), ("Related Tests", 24),
    ("Odoo 17", 12), ("Odoo 19", 12), ("Last Execution", 18),
    ("Description / User story", 60), ("Preconditions", 50), ("Steps", 70),
    ("Expected Result", 70), ("v19 Watch", 44), ("Related Features", 24),
    ("Source Notes", 34), ("Workbook", 34), ("Sheet", 22), ("Row", 7),
    ("Test Execution Row", 10),
]


def testcases_workbook(store, in_scope_only: bool = True) -> bytes:
    """Every workbook test case, one row each, plus a per-workflow summary.

    The Expected Result column is carried verbatim from the workbook, which is
    the source of truth (AUTOMATION_CONVENTIONS hard rule 2) — the exporter
    reads it and never rewrites it.
    """
    cases = store.test_cases_list(in_scope_only=in_scope_only)
    features = store.feature_summary(in_scope_only=in_scope_only)

    wb = _new_workbook()

    # --- summary sheet, so the file opens on the number people ask for first
    ws = wb.create_sheet("Summary")
    ws.column_dimensions["A"].width = 34
    ws.column_dimensions["B"].width = 58
    ws["A1"] = "DataOne 17 -> 19 — Test Case Registry"
    ws["A1"].font = Font(bold=True, size=14)
    meta = [
        ("Exported at", datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")),
        ("Scope", "In-scope workflows only" if in_scope_only
                  else "Every workflow in the workbook"),
        ("Workflows", len(features)),
        ("Test cases", len(cases)),
        ("Automatable", sum(f["automatable"] for f in features)),
        ("Automated", sum(f["automated"] for f in features)),
        ("Source workbook", cases[0]["source_workbook"] if cases else ""),
    ]
    for i, (k, v) in enumerate(meta, start=3):
        ws.cell(row=i, column=1, value=k).font = Font(bold=True)
        ws.cell(row=i, column=2, value=_flat(v))

    counts: dict = {}
    for tc in cases:
        for env in ("v17", "v19"):
            counts.setdefault(env, {})
            s = tc[env + "_status"]
            counts[env][s] = counts[env].get(s, 0) + 1
    row = len(meta) + 5
    ws.cell(row=row, column=1, value="Latest status").font = Font(bold=True, size=12)
    row += 1
    ws.cell(row=row, column=1, value="Status").font = Font(bold=True)
    ws.cell(row=row, column=2, value="Odoo 17").font = Font(bold=True)
    ws.cell(row=row, column=3, value="Odoo 19").font = Font(bold=True)
    ws.column_dimensions["C"].width = 14
    for status in sorted(set(counts.get("v17", {})) | set(counts.get("v19", {}))):
        row += 1
        ws.cell(row=row, column=1, value=status)
        ws.cell(row=row, column=2, value=counts.get("v17", {}).get(status, 0))
        ws.cell(row=row, column=3, value=counts.get("v19", {}).get(status, 0))

    # --- one row per test case
    _sheet(wb, "Test Cases", TC_COLUMNS, [[
        tc["test_case_id"], tc["feature_id"], tc["feature_name"], tc["seq"],
        tc["title"], tc["priority"], tc["test_type"], tc["role"], tc["modules"],
        tc["suite"], tc["suite_name"], tc["execution_phase"],
        "Yes" if tc["in_scope"] else "No",
        tc["automation_type"], tc["automation_status"], tc["automation_wave"],
        tc["automation_approach"], tc["automated_test_ids"],
        tc["related_test_ids"], tc["v17_status"], tc["v19_status"],
        tc["last_execution_id"], tc["description"], tc["preconditions"],
        tc["steps"], tc["expected_result"], tc["v19_watch"],
        tc["related_features"], tc["source_notes"], tc["source_workbook"],
        tc["source_sheet"], tc["source_row"], tc["test_execution_row"],
    ] for tc in cases], status_cols=(20, 21), table_name="TestCases")

    # --- per-workflow rollup
    _sheet(wb, "Workflows", [
        ("Workflow", 18), ("Name", 40), ("Business Purpose", 70),
        ("Key Modules", 34), ("Primary Roles", 28), ("Test Cases", 11),
        ("Automatable", 12), ("Automated", 11), ("Coverage %", 11),
        ("P0", 6), ("P1", 6), ("P2", 6), ("P3", 6),
        ("v19 PASS", 10), ("v19 FAIL", 10), ("v19 BLOCKED", 12),
        ("v19 ERROR", 10), ("v17 PASS", 10), ("v17 FAIL", 10),
    ], [[
        f["feature_id"], f["name"], f["business_purpose"], f["key_modules"],
        f["primary_roles"], f["total"], f["automatable"], f["automated"],
        f["coverage_pct"],
        f["priorities"].get("P0", 0), f["priorities"].get("P1", 0),
        f["priorities"].get("P2", 0), f["priorities"].get("P3", 0),
        f["v19"].get("PASS", 0), f["v19"].get("FAIL", 0),
        f["v19"].get("BLOCKED", 0), f["v19"].get("ERROR", 0),
        f["v17"].get("PASS", 0), f["v17"].get("FAIL", 0),
    ] for f in features], table_name="Workflows")

    return _save(wb)


# ---------------------------------------------------------- run detail xlsx
#: The workbook the registry is synced from, and the sheet QA executes on.
TEMPLATE_FILENAME = "DataOne_v19_Test_Suite_and_Workflows_v1.0.xlsx"
TEMPLATE_GLOB = "DataOne_v19_Test_Suite_and_Workflows_v1.0*.xlsx"
EXEC_SHEET = "Test Execution"

#: Only this environment is written back. The workbook's "Odoo 17 Result"
#: column is the Phase-0a MANUAL baseline (Read Me, step 4) — an automated
#: run must never overwrite it, so a v17 run fills nothing.
EXEC_ENVIRONMENT = "odoo19"

#: Columns the fill touches, found by header text rather than by letter — a
#: column inserted in a later workbook revision must not silently shift the
#: write onto its neighbour.
EXEC_RESULT = "Result"
EXEC_RUN_DATE = "Run Date"
EXEC_TESTER = "Tester"
EXEC_OUTCOME = "Odoo 19 Result"
EXEC_TC_ID = "TC ID"

#: Result is a locked dropdown — "Not Run,Pass,Fail,Blocked,N/A" — so the
#: five platform statuses have to land inside that vocabulary. ERROR maps to
#: Fail: on this sheet anything that did not pass is a failure, and the raw
#: status is preserved verbatim in the Odoo 19 Result cell beside it.
EXEC_RESULT_VALUE = {
    "PASSED": "Pass", "FAILED": "Fail", "ERROR": "Fail",
    "BLOCKED": "Blocked", "SKIPPED": "N/A",
}

#: Worst-first. One workbook case can be covered by several automated tests;
#: the sheet carries one verdict, and the worst outcome is the honest one.
EXEC_PRECEDENCE = ("FAILED", "ERROR", "BLOCKED", "SKIPPED", "PASSED")

#: Read Me, step 3: "cells auto-colour: Pass=green, Fail=red, Blocked=orange".
#: The workbook ships no conditional formatting, so the fill is applied here.
EXEC_FILL = {"Pass": "1E7A3C", "Fail": "A32B22",
             "Blocked": "C55A11", "N/A": "595959"}

DEFAULT_TESTER = "QA Automation Platform"


class TemplateUnusable(RuntimeError):
    """The run export cannot keep the workbook's shape, and says why.

    Distinct from the KeyError a missing run raises, so the API can answer
    404 for "no such run" and 503 — with something actionable — for "the
    workbook this export is built on is absent or has changed shape".
    """


class TemplateMissing(TemplateUnusable, FileNotFoundError):
    """No source workbook found in any of the searched locations."""


class TemplateInvalid(TemplateUnusable):
    """A workbook was found, but it is not the sheet this export writes to."""


def _registry_workbook():
    """The file scripts/sync_registry.py last read, if it recorded one.

    Last resort only. The fill matches rows by the TC ID written in the sheet
    itself, never by a row number carried in from the registry, so the export
    does not depend on this file — it is a fallback for a host that has the
    workbook nowhere else.
    """
    try:
        reg = json.loads((ROOT / "data" / "test_registry.json")
                         .read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return Path(reg["workbook"]) if reg.get("workbook") else None


def _template_path() -> Path:
    """Locate the source workbook. Checked in order, first hit wins:

    1. ``$QA_WORKBOOK`` — an explicit path, for a non-standard deployment.
    2. ``data/`` beside the database — the operational default. Dropping the
       current workbook revision here is how an operator pins the template.
    3. ``/workbook/`` — the read-only mount docker-compose provides.
    4. ``~/Downloads/`` — where scripts/sync_registry.py looks by default.
    5. whatever the registry was synced from, which may be an older revision.
    6. a working copy such as ``... v1.0 (4).xlsx`` in any of those
       directories, newest first, so a freshly downloaded revision is picked
       up without anyone having to rename it.

    The file is only ever read; the fill happens on the in-memory copy.
    """
    dirs = [ROOT / "data", Path("/workbook"), Path.home() / "Downloads"]
    exact = []
    if os.environ.get("QA_WORKBOOK", "").strip():
        exact.append(Path(os.environ["QA_WORKBOOK"].strip()))
    exact += [d / TEMPLATE_FILENAME for d in dirs]
    registry = _registry_workbook()
    if registry:
        exact.append(registry)
    for path in exact:
        try:
            if path.is_file():
                return path
        except OSError:
            continue

    pool: list = []
    for d in dirs:
        try:
            pool += [p for p in d.glob(TEMPLATE_GLOB) if p.is_file()]
        except OSError:
            continue
    if pool:
        return max(pool, key=lambda p: p.stat().st_mtime)
    raise TemplateMissing(
        "Source workbook not found. Put %s in %s, or point QA_WORKBOOK at it."
        % (TEMPLATE_FILENAME, ROOT / "data"))


def _tc_index(details: list) -> dict:
    """workbook TC id -> the run results that cover it."""
    by_tc: dict = {}
    for d in details:
        for raw in (d.get("traceability") or {}).get("tc_ids", []):
            m = TC_ID_RE.search(str(raw))
            if m:
                by_tc.setdefault(m.group(0), []).append(d)
    return by_tc


def _worst(results: list):
    """The result that decides the cell: worst status, latest of its kind."""
    def rank(d):
        status = d["status"]
        order = (EXEC_PRECEDENCE.index(status)
                 if status in EXEC_PRECEDENCE else len(EXEC_PRECEDENCE))
        return (order, -(d["finished_at"] or 0))
    return sorted(results, key=rank)[0]


def _outcome_text(results: list, run: dict) -> str:
    """What the environment actually did — the evidence half of the row.

    Read Me, step 3: "On Fail record Odoo 19 Result and the Defect ID". A
    pass gets the same treatment, so a reviewer can tell a case that asserted
    something from one that merely did not crash.
    """
    lines = []
    for d in sorted(results, key=lambda x: x["test_id"]):
        failed = sum(1 for a in d["assertions"] if not a["passed"])
        head = "%s · %s" % (d["status"], d["test_id"])
        if d["status"] == "PASSED":
            lines.append("%s — %d step(s), %d assertion(s), all passed"
                         % (head, len(d["steps"]), len(d["assertions"])))
            continue
        parts = [head]
        if d.get("failed_step"):
            parts.append("failed step: %s" % d["failed_step"])
        if d.get("expected") or d.get("actual"):
            parts.append("expected %s / got %s"
                         % (d.get("expected") or "—",
                            d.get("actual") or "—"))
        if d.get("skip_reason"):
            parts.append("reason: %s" % d["skip_reason"])
        if d.get("error"):
            parts.append("error: %s" % str(d["error"]).strip().splitlines()[0])
        if failed:
            parts.append("%d assertion(s) failed" % failed)
        lines.append(" · ".join(parts))
    lines.append("[%s · %s · %s]" % (
        run["id"], run["env_name"],
        _ts(run["finished_at"] or run["started_at"])))
    text = "\n".join(lines)
    return text[:2000] + (" ...[truncated]" if len(text) > 2000 else "")


def _fill_execution_sheet(ws, details: list, run: dict, tester: str) -> dict:
    """Write this run onto the workbook's manual-test sheet, in place.

    Rows are located by their own ``TC ID`` cell, never by a row number
    carried in from the registry: the sheet validates the mapping itself, so
    a workbook revision that reorders rows cannot put a verdict on the wrong
    case. Only the four execution columns are touched — every other cell,
    and the Suite Overview formulas that count them, are left alone.
    """
    headers = {str(c.value).strip(): c.column for c in ws[1] if c.value}
    missing = [h for h in (EXEC_TC_ID, EXEC_RESULT, EXEC_RUN_DATE,
                           EXEC_TESTER, EXEC_OUTCOME) if h not in headers]
    if missing:
        raise TemplateInvalid("%s sheet has no column(s): %s"
                              % (EXEC_SHEET, ", ".join(missing)))

    rows = {}
    for r in range(2, ws.max_row + 1):
        tc_id = ws.cell(row=r, column=headers[EXEC_TC_ID]).value
        if tc_id:
            rows[str(tc_id).strip()] = r

    by_tc = _tc_index(details)
    audit = {"covered": len(by_tc), "filled": 0, "unmapped": [],
             "results_without_tc": 0, "values": {}}
    for d in details:
        if not any(TC_ID_RE.search(str(x))
                   for x in (d.get("traceability") or {}).get("tc_ids", [])):
            audit["results_without_tc"] += 1

    for tc_id, results in sorted(by_tc.items()):
        row = rows.get(tc_id)
        if not row:
            audit["unmapped"].append(tc_id)
            continue
        decisive = _worst(results)
        value = EXEC_RESULT_VALUE.get(decisive["status"], "Not Run")
        when = max((r["finished_at"] or r["started_at"] or 0)
                   for r in results) or run["finished_at"] or run["started_at"]

        cell = ws.cell(row=row, column=headers[EXEC_RESULT])
        cell.value = value
        colour = EXEC_FILL.get(value)
        if colour:
            cell.fill = PatternFill("solid", fgColor=colour)
            cell.font = Font(name=cell.font.name or "Arial",
                             sz=cell.font.sz or 10, color="FFFFFF", bold=True)

        date_cell = ws.cell(row=row, column=headers[EXEC_RUN_DATE])
        date_cell.value = (datetime.fromtimestamp(float(when), tz=timezone.utc)
                           .astimezone().date()) if when else None
        date_cell.number_format = "yyyy-mm-dd"

        ws.cell(row=row, column=headers[EXEC_TESTER]).value = tester
        ws.cell(row=row, column=headers[EXEC_OUTCOME]).value = _flat(
            _outcome_text(results, run))

        audit["filled"] += 1
        audit["values"][value] = audit["values"].get(value, 0) + 1
    return audit


def _run_summary_sheet(wb, run: dict, details: list, note: list) -> None:
    """The run's own header block, appended after the workbook's sheets."""
    ws = wb.create_sheet("Run Summary")
    ws.column_dimensions["A"].width = 28
    ws.column_dimensions["B"].width = 96
    ws["A1"] = "Run " + run["id"]
    ws["A1"].font = Font(bold=True, size=14)
    duration = ((run["finished_at"] or 0) - (run["started_at"] or 0)) \
        if run["started_at"] and run["finished_at"] else 0
    meta = [
        ("Label", run["label"]), ("Environment", run["env_name"]),
        ("Mode", run["mode"]), ("Status", run["status"]),
        ("Started", _ts(run["started_at"])),
        ("Finished", _ts(run["finished_at"])),
        ("Wall clock", "%.1f min" % (duration / 60) if duration else ""),
        ("Tests planned", run["total"]), ("Results recorded", len(details)),
        ("Exported at",
         datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")),
    ]
    for i, (k, v) in enumerate(meta, start=3):
        ws.cell(row=i, column=1, value=k).font = Font(bold=True)
        ws.cell(row=i, column=2, value=_flat(v))

    row = len(meta) + 4
    ws.cell(row=row, column=1, value="By status").font = Font(bold=True, size=12)
    by_status: dict = {}
    for d in details:
        by_status[d["status"]] = by_status.get(d["status"], 0) + 1
    for status, n in sorted(by_status.items(), key=lambda kv: -kv[1]):
        row += 1
        cell = ws.cell(row=row, column=1, value=status)
        colour = STATUS_FILL.get(status.upper())
        if colour:
            cell.fill = PatternFill("solid", fgColor=colour)
            cell.font = Font(color="FFFFFF", bold=True)
        ws.cell(row=row, column=2, value=n)

    row += 2
    ws.cell(row=row, column=1,
            value="Test Execution fill").font = Font(bold=True, size=12)
    for k, v in note:
        row += 1
        ws.cell(row=row, column=1, value=k).font = Font(bold=True)
        ws.cell(row=row, column=2, value=_flat(v)).alignment = WRAP


def _run_detail_sheets(wb, details: list) -> None:
    """Results, steps and assertions — the evidence behind every verdict."""
    _sheet(wb, "Run Results", [
        ("Result ID", 18), ("Test ID", 24), ("Name", 54), ("Workflow", 18),
        ("Workbook TCs", 22), ("Priority", 9), ("Kind", 8), ("Status", 12),
        ("Duration (s)", 12), ("Failed Step", 46), ("Expected", 46),
        ("Actual", 46), ("Error", 70), ("Skip / Block Reason", 60),
        ("Steps", 8), ("Assertions", 11), ("Failed Assertions", 16),
        ("Started", 20), ("Finished", 20),
    ], [[
        d["id"], d["test_id"], d["name"], d["workflow"],
        ", ".join(str(x) for x in (d["traceability"] or {}).get("tc_ids", [])),
        d["priority"], d["kind"], d["status"],
        round((d["duration_ms"] or 0) / 1000, 1),
        d["failed_step"], d["expected"], d["actual"], d["error"],
        d["skip_reason"], len(d["steps"]), len(d["assertions"]),
        sum(1 for a in d["assertions"] if not a["passed"]),
        _ts(d["started_at"]), _ts(d["finished_at"]),
    ] for d in details], status_cols=(8,), table_name="Results")

    _sheet(wb, "Run Steps", [
        ("Test ID", 24), ("Result ID", 18), ("#", 5), ("Step", 74),
        ("Status", 12), ("Duration (s)", 12), ("Error", 80),
    ], [[
        d["test_id"], d["id"], s["idx"], s["name"], s["status"],
        round((s["duration_ms"] or 0) / 1000, 2), s["error"],
    ] for d in details for s in d["steps"]],
        status_cols=(5,), table_name="Steps")

    _sheet(wb, "Run Assertions", [
        ("Test ID", 24), ("Result ID", 18), ("Assertion", 60),
        ("Passed", 9), ("Expected", 60), ("Actual", 60),
    ], [[
        d["test_id"], d["id"], a["name"], "PASS" if a["passed"] else "FAIL",
        a["expected"], a["actual"],
    ] for d in details for a in d["assertions"]],
        status_cols=(4,), table_name="Assertions")


def run_workbook(store, run_id: str, tester: str | None = None) -> bytes:
    """One run, written back onto a copy of the source workbook.

    What comes out is the workbook QA already plans the session in — its nine
    sheets, its columns, its live Suite Overview counts — with four columns
    of the ``Test Execution`` sheet filled from this run: Result, Run Date,
    Tester and Odoo 19 Result. Run Summary, Run Results, Run Steps and Run
    Assertions are appended after them, so the evidence behind every verdict
    travels in the same file.

    Only an ``odoo19`` run writes: Odoo 17 Result is the manual Phase-0a
    baseline and is never touched. A run on any other environment still
    exports, with the execution columns left as the workbook has them and the
    reason stated on Run Summary.
    """
    run = store.run(run_id)
    if not run:
        raise KeyError(run_id)
    details = [store.result(r["id"]) for r in run["results"]]
    details = [d for d in details if d]

    path = _template_path()
    wb = load_workbook(path)
    if EXEC_SHEET not in wb.sheetnames:
        raise TemplateInvalid("%s has no '%s' sheet" % (path.name, EXEC_SHEET))

    tester = (tester or os.environ.get("QA_TESTER") or DEFAULT_TESTER).strip()
    note = [("Source workbook", str(path)),
            ("Target sheet", EXEC_SHEET),
            ("Columns written", ", ".join(
                (EXEC_RESULT, EXEC_RUN_DATE, EXEC_TESTER, EXEC_OUTCOME))),
            ("Tester", tester)]

    if run["environment"] == EXEC_ENVIRONMENT:
        audit = _fill_execution_sheet(wb[EXEC_SHEET], details, run, tester)
        note += [
            ("Rows filled", "%d of %d workbook case(s) this run covers"
             % (audit["filled"], audit["covered"])),
            ("Result values", ", ".join(
                "%s %d" % (k, v) for k, v in sorted(audit["values"].items()))
             or "none"),
            ("Status mapping",
             "PASSED -> Pass, FAILED -> Fail, ERROR -> Fail, "
             "BLOCKED -> Blocked, SKIPPED -> N/A. The raw platform status is "
             "kept verbatim in Odoo 19 Result."),
            ("Several tests per case",
             "Worst status wins (FAILED > ERROR > BLOCKED > SKIPPED > "
             "PASSED); every covering test is listed in Odoo 19 Result."),
        ]
        if audit["unmapped"]:
            note.append(("TC ids not on the sheet",
                         ", ".join(sorted(audit["unmapped"]))))
        if audit["results_without_tc"]:
            note.append(("Results with no workbook TC id",
                         "%d - on Run Results, with no sheet row to fill"
                         % audit["results_without_tc"]))
    else:
        note.append((
            "Nothing written",
            "This run executed on %s. Only %s runs fill the execution "
            "columns: Odoo 17 Result is the manual Phase-0a baseline "
            "(Read Me, step 4) and an automated run must not overwrite it."
            % (run["env_name"], EXEC_ENVIRONMENT)))

    _run_summary_sheet(wb, run, details, note)
    _run_detail_sheets(wb, details)
    return _save(wb)


# ------------------------------------------------------- markdown reports
def _cell(value, limit: int = 300) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")[:limit]


def _md_result(d, heading: str = "##") -> list:
    """One result, fully expanded. Shared by the per-case and per-run report."""
    tc_ids = ", ".join(str(x) for x in (d["traceability"] or {}).get("tc_ids", []))
    out = ["%s `%s` — %s" % (heading, d["test_id"], d["name"]), "",
           "| | |", "|---|---|",
           "| Status | **%s** |" % d["status"],
           "| Result ID | `%s` |" % d["id"],
           "| Workflow | %s |" % d["workflow"]]
    if tc_ids:
        out.append("| Workbook test cases | %s |" % tc_ids)
    out += ["| Priority | %s |" % d["priority"],
            "| Kind | %s |" % d["kind"],
            "| Duration | %.1fs |" % ((d["duration_ms"] or 0) / 1000),
            "| Finished | %s |" % _ts(d["finished_at"]), ""]

    if d.get("skip_reason"):
        out += [heading + "# Reason", "", d["skip_reason"], ""]
    if d.get("failed_step"):
        out += [heading + "# Failed step", "", "`%s`" % d["failed_step"], ""]
    if d.get("expected") or d.get("actual"):
        out += [heading + "# Expected vs actual", "", "```",
                "expected: %s" % d.get("expected"),
                "actual:   %s" % d.get("actual"), "```", ""]
    if d.get("error"):
        out += [heading + "# Error", "", "```", str(d["error"])[:6000], "```", ""]

    if d["steps"]:
        out += [heading + "# Steps", "",
                "| # | Step | Status | Time | Error |", "|---|---|---|---|---|"]
        for s in d["steps"]:
            mark = {"PASSED": "PASS", "FAILED": "FAIL",
                    "SKIPPED": "SKIP"}.get(s["status"], "-")
            out.append("| %s | %s | %s | %.2fs | %s |" % (
                s["idx"], _cell(s["name"] or ""), mark,
                (s["duration_ms"] or 0) / 1000, _cell(s["error"] or "", 200)))
        out.append("")

    if d["assertions"]:
        out += [heading + "# Assertions", "",
                "| | Assertion | Expected | Actual |", "|---|---|---|---|"]
        for a in d["assertions"]:
            out.append("| %s | %s | `%s` | `%s` |" % (
                "PASS" if a["passed"] else "FAIL", _cell(a["name"]),
                _cell(a["expected"]), _cell(a["actual"])))
        out.append("")

    if d["artifacts"]:
        out += [heading + "# Artifacts", ""]
        out += ["- %s: `%s`" % (a["type"], a["name"]) for a in d["artifacts"]]
        out.append("")
    return out


def result_markdown(store, result_id: str) -> str:
    d = store.result(result_id)
    if not d:
        raise KeyError(result_id)
    run = d.get("run") or {}
    head = ["# %s — %s" % (d["test_id"], d["status"]), "",
            "Run `%s` on **%s** · exported %s" % (
                d["run_id"], run.get("env_name", ""),
                datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")), ""]
    return "\n".join(head + _md_result(d, heading="##")) + "\n"


def run_markdown(store, run_id: str, only: str | None = None) -> str:
    """Every case in a run, fully expanded.

    `only` filters by status (e.g. "FAILED,ERROR") so a triage reader can pull
    just the cases that need attention without a second tool.
    """
    run = store.run(run_id)
    if not run:
        raise KeyError(run_id)
    wanted = {s.strip().upper() for s in only.split(",")} if only else None
    details = [store.result(r["id"]) for r in run["results"]]
    details = [d for d in details if d and (not wanted or d["status"] in wanted)]

    by_status: dict = {}
    for r in run["results"]:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1

    out = ["# Run %s — detailed report" % run_id, "",
           "**%s**" % run["label"], "",
           "| | |", "|---|---|",
           "| Environment | %s |" % run["env_name"],
           "| Status | %s |" % run["status"],
           "| Started | %s |" % _ts(run["started_at"]),
           "| Finished | %s |" % _ts(run["finished_at"]),
           "| Tests | %s |" % run["total"], ""]
    if by_status:
        out += ["| Status | Count |", "|---|---|"]
        out += ["| %s | %s |" % (k, v)
                for k, v in sorted(by_status.items(), key=lambda kv: -kv[1])]
        out.append("")
    if wanted:
        out += ["> Filtered to **%s** — %d of %d cases." % (
            ", ".join(sorted(wanted)), len(details), len(run["results"])), ""]

    out += ["## Contents", ""]
    out += ["- `%s` — %s" % (d["test_id"], d["status"]) for d in details]
    out.append("")
    for d in details:
        out += ["---", ""] + _md_result(d, heading="##")
    return "\n".join(out) + "\n"
