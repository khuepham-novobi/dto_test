"""Markdown triage report for FAILED / ERROR cases, written to be acted on.

    python scripts/gen_failure_report.py                       # newest COMPLETED run
    python scripts/gen_failure_report.py --run RUN-A --run RUN-B   # merge runs
    python scripts/gen_failure_report.py --include-blocked
    python scripts/gen_failure_report.py --out reports/FAILURES.md

Unlike reports/DATAONE-WF-NNN_REPORT.md (a status rollup for people), this
one carries what is needed to actually diagnose a case without opening the
UI: the source file and line the test lives at, its docstring — which is
where the suites record `EXPECTED v17 OUTCOME` and known-finding notes —
every step with its verdict, every assertion's expected vs actual, and the
raw error.

Cases are grouped by root-cause signature, because a hundred failures are
rarely a hundred problems: one missing fixture usually explains twenty.
"""
from __future__ import annotations

import argparse
import inspect
import json
import os
import re
import sys
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import backend.config  # noqa: F401,E402 — loads .env + config/local.yaml
from backend.config import settings  # noqa: E402
from framework import registry  # noqa: E402

API = os.environ.get("QA_API", "").rstrip("/") or f"http://127.0.0.1:{settings.server_port}"


def api(path: str):
    with urllib.request.urlopen(f"{API}{path}", timeout=180) as r:
        return json.load(r)


def source_of(test_id: str) -> tuple[str, int, str]:
    """(path relative to repo root, first line, docstring) for a test."""
    for t in registry.discover():
        if t.id != test_id:
            continue
        fn = inspect.unwrap(t.func)
        try:
            path = Path(inspect.getsourcefile(fn) or "")
            line = inspect.getsourcelines(fn)[1]
        except (OSError, TypeError):
            return ("", 0, inspect.getdoc(fn) or "")
        try:
            rel = path.relative_to(ROOT)
        except ValueError:
            rel = path
        return (str(rel).replace("\\", "/"), line, inspect.getdoc(fn) or "")
    return ("", 0, "")


# Root causes worth collapsing together. Order matters: first match wins.
SIGNATURES = [
    (re.compile(r"Database not found", re.I),
     "Target database not served (dbfilter / wrong db name)"),
    (re.compile(r"404 Not Found.*call_kw|call_kw.*404", re.I),
     "Model has no route — its module is not installed on the target"),
    (re.compile(r"Contact your administrator to request access", re.I),
     "Access rights — the run user lacks a required group"),
    (re.compile(r"real-time valuation", re.I),
     "Fixture missing: no product.category uses real-time valuation"),
    (re.compile(r"source tree is not reachable|DTO_SOURCE_ROOT", re.I),
     "DTO_SOURCE_ROOT not configured for static analysis"),
    (re.compile(r"external host|convention rule 4", re.I),
     "Deliberately not run: would reach an external host"),
    (re.compile(r"unreachable at http", re.I),
     "Target Odoo not reachable"),
    (re.compile(r"OdooRPCError", re.I), "Odoo RPC error (see per-case detail)"),
]


# "<assertion name>: expected <X>, got <Y>" — the value half makes every case
# its own group, so strip it and let cases sharing an assertion collapse.
_EXPECTED_GOT = re.compile(r"^(.*?):\s*expected\b.*$", re.S)


def signature(res: dict) -> str:
    blob = " ".join(str(res.get(k) or "") for k in
                    ("error", "skip_reason", "failed_step", "actual"))
    for rx, label in SIGNATURES:
        if rx.search(blob):
            return label
    first = (str(res.get("error") or "").strip().splitlines() or [""])[0]
    if not first:
        return "Assertion failed (no exception)"
    m = _EXPECTED_GOT.match(first)
    if m and m.group(1).strip():
        return f"Assertion: {m.group(1).strip()[:80]}"
    return first[:90]


def fence(text: str, lang: str = "") -> str:
    text = (text or "").rstrip()
    if not text:
        return "_(empty)_"
    ticks = "```"
    while ticks in text:
        ticks += "`"
    return f"{ticks}{lang}\n{text}\n{ticks}"


def render(cases: list[dict], run_ids: list[str]) -> str:
    by_status = Counter(c["status"] for c in cases)
    by_sig: dict[str, list[dict]] = defaultdict(list)
    for c in cases:
        by_sig[c["_sig"]].append(c)

    L: list[str] = []
    A = L.append
    A("# DataOne — FAILED / ERROR triage")
    A("")
    A(f"Source: {', '.join(f'`{r}`' for r in run_ids)}  ")
    A(f"Total: **{len(cases)}** cases — " +
      ", ".join(f"{k} {v}" for k, v in by_status.most_common()))
    A("")
    A("Each case below carries the source file and line, the test's "
      "docstring (where the suites record `EXPECTED v17 OUTCOME` and known "
      "findings), the failing step, expected vs actual for each assertion, "
      "and the raw error.")
    A("")
    A("> **Read the docstring before changing anything.** Many of these "
      "cases are designed to FAIL — the failure IS the finding, not an "
      "automation defect. The workbook's expected results are immutable: "
      "never weaken or invert an assertion to make a test go green "
      "(`docs/AUTOMATION_CONVENTIONS.md`, hard rule 2).")
    A("")

    A("## Grouped by root cause")
    A("")
    A("| # | Root cause | Cases |")
    A("|---|---|---:|")
    for i, (sig, group) in enumerate(
            sorted(by_sig.items(), key=lambda kv: -len(kv[1])), 1):
        A(f"| {i} | {sig} | {len(group)} |")
    A("")
    A("Work top-down: the first group usually accounts for the most cases, "
      "and a hundred failures are rarely a hundred problems.")
    A("")

    for i, (sig, group) in enumerate(
            sorted(by_sig.items(), key=lambda kv: -len(kv[1])), 1):
        A(f"## {i}. {sig}")
        A("")
        A(f"**{len(group)} case(s):** " +
          ", ".join(f"`{c['test_id']}`" for c in group))
        A("")
        for c in group:
            A(f"### {c['test_id']} — {c.get('name') or ''}")
            A("")
            A(f"- **Status:** `{c['status']}` / `{c.get('failure_class') or '—'}`")
            A(f"- **Workflow:** {c.get('workflow') or '—'}")
            if c["_file"]:
                A(f"- **Source:** `{c['_file']}:{c['_line']}`")
            tr = c.get("traceability") or {}
            if tr:
                A(f"- **Workbook:** `{json.dumps(tr, ensure_ascii=False)}`")
            if c.get("failed_step"):
                A(f"- **Failing step:** {c['failed_step']}")
            A("")
            if c["_doc"]:
                A("<details><summary>Test docstring</summary>")
                A("")
                A(fence(c["_doc"]))
                A("")
                A("</details>")
                A("")
            if c.get("error"):
                A("**Error**")
                A("")
                A(fence(str(c["error"]), "text"))
                A("")
            exp, act = c.get("expected"), c.get("actual")
            if exp or act:
                A("**Expected vs actual**")
                A("")
                A(fence(f"expected: {exp}\nactual  : {act}", "text"))
                A("")
            asserts = [a for a in (c.get("assertions") or []) if not a.get("passed")]
            if asserts:
                A("**Failed assertions**")
                A("")
                A("| Assertion | Expected | Actual |")
                A("|---|---|---|")
                for a in asserts[:12]:
                    def cell(v):
                        return str(v or "").replace("|", "\\|").replace("\n", " ")[:160]
                    A(f"| {cell(a.get('name'))} | {cell(a.get('expected'))} "
                      f"| {cell(a.get('actual'))} |")
                A("")
            steps = c.get("steps") or []
            if steps:
                A("<details><summary>Steps</summary>")
                A("")
                for s in steps:
                    mark = {"PASSED": "ok", "FAILED": "FAIL", "ERROR": "ERR"}.get(
                        s.get("status"), s.get("status") or "?")
                    A(f"- `[{mark}]` {s.get('name')}"
                      + (f" — {str(s.get('error'))[:140]}" if s.get("error") else ""))
                A("")
                A("</details>")
                A("")
            A("---")
            A("")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="append", default=[],
                    help="run id; repeat to merge several runs")
    ap.add_argument("--include-blocked", action="store_true")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    run_ids = args.run
    if not run_ids:
        runs = api("/api/runs")
        runs = runs.get("runs", runs) if isinstance(runs, dict) else runs
        done = [r for r in runs if r.get("status") == "COMPLETED"]
        if not done:
            sys.exit("No COMPLETED run to report on.")
        run_ids = [done[0]["id"]]

    wanted = {"FAILED", "ERROR"} | ({"BLOCKED"} if args.include_blocked else set())
    seen: set[str] = set()
    cases: list[dict] = []
    for rid in run_ids:
        run = api(f"/api/runs/{rid}")
        for row in (run.get("results") or []):
            if row.get("status") not in wanted:
                continue
            # A case cut short when a run was cancelled is not a real failure: it
            # never got to run. Skip those, or the report fills with "Interrupted"
            # rows that carry nothing to fix.
            if re.search(r"interrupted", str(row.get("error") or ""), re.I):
                continue
            tid = row.get("test_id")
            if tid in seen:           # same test re-run later: keep the newest
                continue
            seen.add(tid)
            full = api(f"/api/results/{row['id']}") or row
            full.setdefault("test_id", tid)
            full["_file"], full["_line"], full["_doc"] = source_of(tid)
            full["_sig"] = signature(full)
            cases.append(full)

    if not cases:
        print("  No FAILED/ERROR cases.")
        return

    cases.sort(key=lambda c: (c.get("workflow") or "", c["test_id"]))
    out = Path(args.out) if args.out else (
        ROOT / "reports" / f"FAILURES_{'_'.join(run_ids)}.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(cases, run_ids), encoding="utf-8")
    print(f"  {len(cases)} case -> {out}")
    print(f"  nhom nguyen nhan: {len({c['_sig'] for c in cases})}")


if __name__ == "__main__":
    main()
