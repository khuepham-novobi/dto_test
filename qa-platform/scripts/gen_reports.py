# -*- coding: utf-8 -*-
"""Generate per-workflow reports (reports/DATAONE-WF-NNN_REPORT.md) and
the in-scope summary from persisted execution results + the registry.

Everything in the reports is read back from the same rows the execution
engine wrote — nothing is synthesized.

Usage:  python scripts/gen_reports.py
"""
from __future__ import annotations

import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.config import settings                      # noqa: E402
from backend.store import Store                          # noqa: E402

REPORTS = ROOT / "reports"
FEAS_DIR = REPORTS / "data"

FAIL = {"FAIL", "ERROR"}


def classify(v17: str, v19: str) -> str:
    if "BLOCKED" in (v17, v19):
        return "BLOCKED"
    if v17 == "PASS" and v19 == "PASS":
        return "SAME_BEHAVIOR"
    if v17 == "PASS" and v19 in FAIL:
        return "REGRESSION_CANDIDATE"
    if v17 in FAIL and v19 == "PASS":
        return "FIXED"
    if v17 in FAIL and v19 in FAIL:
        return "SAME_FAILURE"
    return "NOT_COMPARED"


def load_feasibility(slug: str) -> dict:
    """{tc_id: decision} from reports/data/<slug>_feasibility.json.

    The DataOne files wrap their per-TC decisions in a "decisions" key
    alongside workflow metadata (risk, build order, key findings), so the
    map is unwrapped here; a flat file is returned as-is.
    """
    path = FEAS_DIR / f"{slug}_feasibility.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return {}
    if isinstance(data, dict) and isinstance(data.get("decisions"), dict):
        return data["decisions"]
    return {k: v for k, v in data.items() if isinstance(v, dict)}


def main():
    store = Store(settings.data_dir / "results.db")
    store.load_registry(settings.data_dir / "test_registry.json")
    features = store.feature_summary(in_scope_only=True)
    now = time.strftime("%Y-%m-%d %H:%M")
    REPORTS.mkdir(exist_ok=True)

    grand = Counter()
    cls_totals = Counter()
    per_fg_lines = []

    for f in features:
        fg = f["feature_id"]
        # DATAONE-WF-013 -> wf013; anything else -> a lower-cased slug
        parts = str(fg).split("-")
        if parts[-1].isdigit():
            slug = "wf" + parts[-1]
        else:
            slug = str(fg).lower().replace("-", "")
        tcs = store.test_cases_list(feature_id=fg)
        feas = load_feasibility(slug)

        rows, cls_counter = [], Counter()
        v17_counter, v19_counter = Counter(), Counter()
        fails = []
        for tc in tcs:
            v17, v19 = tc["v17_status"], tc["v19_status"]
            v17_counter[v17] += 1
            v19_counter[v19] += 1
            cls = classify(v17, v19)
            cls_counter[cls] += 1
            rows.append((tc, v17, v19, cls))
            if v17 in FAIL or v19 in FAIL:
                fails.append(tc)

        automated = sum(1 for tc in tcs if tc["automated_test_ids"])
        manual = sum(1 for tc in tcs if tc["automation_type"] == "MANUAL")
        automatable = f["automatable"]
        blocked_exec = sum(1 for tc in tcs
                           if "BLOCKED" in (tc["v17_status"], tc["v19_status"]))
        executed_v17 = sum(v17_counter[s] for s in
                           ("PASS", "FAIL", "ERROR", "BLOCKED", "SKIPPED"))
        executed_v19 = sum(v19_counter[s] for s in
                           ("PASS", "FAIL", "ERROR", "BLOCKED", "SKIPPED"))

        grand.update({
            "total": len(tcs), "automated": automated, "manual": manual,
            "blocked": blocked_exec,
            "v17_pass": v17_counter["PASS"],
            "v17_fail": v17_counter["FAIL"] + v17_counter["ERROR"],
            "v19_pass": v19_counter["PASS"],
            "v19_fail": v19_counter["FAIL"] + v19_counter["ERROR"],
            "executed_v17": executed_v17, "executed_v19": executed_v19,
        })
        cls_totals.update({c: n for c, n in cls_counter.items()})

        lines = [
            f"# {fg} Report — {f['name']}",
            "",
            f"Generated {now} by `scripts/gen_reports.py` from persisted "
            "execution results (`data/results.db`) and the workbook-synced "
            "registry. Expected results are the workbook's, verbatim.",
            "",
            "## Counts",
            "",
            f"- Test cases: **{len(tcs)}**",
            f"- Automated (covered by platform tests): **{automated}** "
            f"of {automatable} automatable",
            f"- Manual-only: **{manual}**",
            f"- Currently BLOCKED (either environment): **{blocked_exec}**",
            f"- Odoo 17: PASS {v17_counter['PASS']} / "
            f"FAIL {v17_counter['FAIL'] + v17_counter['ERROR']} / "
            f"BLOCKED {v17_counter['BLOCKED']} / "
            f"SKIPPED {v17_counter['SKIPPED']} / "
            f"not executed {len(tcs) - executed_v17}",
            f"- Odoo 19: PASS {v19_counter['PASS']} / "
            f"FAIL {v19_counter['FAIL'] + v19_counter['ERROR']} / "
            f"BLOCKED {v19_counter['BLOCKED']} / "
            f"not executed {len(tcs) - executed_v19}",
            "",
            "## Cross-version classification",
            "",
            "| Classification | Count |",
            "|---|---:|",
        ]
        for cls in ("SAME_BEHAVIOR", "REGRESSION_CANDIDATE", "FIXED",
                    "SAME_FAILURE", "BLOCKED", "NOT_COMPARED"):
            lines.append(f"| {cls} | {cls_counter.get(cls, 0)} |")
        lines += [
            "",
            "> REGRESSION_CANDIDATE is not a confirmed regression until "
            "failure triage; BLOCKED reflects the missing local Odoo 19 "
            "environment (see docs/ENVIRONMENT_STATUS.md).",
            "",
            "## Per test case",
            "",
            "| TC | Title | Prio | Automation | v17 | v19 | Classification |",
            "|---|---|---|---|---|---|---|",
        ]
        for tc, v17, v19, cls in rows:
            lines.append(
                f"| {tc['test_case_id']} | {tc['title'][:70]} "
                f"| {tc['priority']} "
                f"| {tc['automation_status']} | {v17} | {v19} | {cls} |")

        if fails:
            lines += ["", "## Failure notes (triage input)", ""]
            for tc in fails:
                execs = store.test_case(tc["test_case_id"])["executions"]
                # newest execution PER ENVIRONMENT — otherwise a later v19
                # BLOCKED run hides the v17 assertion that actually failed
                seen = set()
                for ex in execs:                      # already newest-first
                    env = ex.get("environment")
                    if env in seen or ex.get("canonical") not in FAIL:
                        continue
                    seen.add(env)
                    lines.append(
                        f"- **{tc['test_case_id']}** [{ex.get('env_name') or env}"
                        f" → {ex.get('canonical')}"
                        f" / {ex.get('failure_class') or '—'}] "
                        f"{(ex.get('error') or '')[:260]}")
        if feas:
            dec = Counter(v.get("decision", "?") for v in feas.values())
            lines += ["", "## Feasibility decisions",
                      "",
                      f"implemented {dec.get('implemented', 0)} · "
                      f"blocked_stub {dec.get('blocked_stub', 0)} · "
                      f"not_implemented {dec.get('not_implemented', 0)} "
                      f"(details: `reports/data/{slug}_feasibility.json`)"]
        lines.append("")
        out = REPORTS / f"{fg}_REPORT.md"
        out.write_text("\n".join(lines), encoding="utf-8")
        print(f"wrote {out}")
        per_fg_lines.append(
            f"| {fg} | {f['name'][:42]} | {len(tcs)} | {automated} "
            f"| {v17_counter['PASS']}/{v17_counter['FAIL'] + v17_counter['ERROR']} "
            f"| {v19_counter['PASS']}/{v19_counter['FAIL'] + v19_counter['ERROR']} "
            f"| {cls_counter.get('REGRESSION_CANDIDATE', 0)} "
            f"| {cls_counter.get('FIXED', 0)} |")

    total = grand["total"]
    auto_cov = round(100 * grand["automated"] / total, 1) if total else 0
    exec_cov_v17 = round(100 * grand["executed_v17"] / total, 1) if total else 0
    exec_cov_v19 = round(100 * grand["executed_v19"] / total, 1) if total else 0
    summary = [
        "# DataOne 17 → 19 — In-Scope Workflow Summary",
        "",
        f"Generated {now}. Source: persisted executions in "
        f"`data/results.db` + the workbook-synced registry "
        f"({total} in-scope test cases across {len(features)} workflows).",
        "",
        "## Headline numbers",
        "",
        f"- **Total cases:** {total}",
        f"- **Automated (covered by platform tests):** {grand['automated']}",
        f"- **Manual-only:** {grand['manual']}",
        f"- **Blocked (any environment):** {grand['blocked']}",
        f"- **Odoo 17:** PASS {grand['v17_pass']} / FAIL {grand['v17_fail']}",
        f"- **Odoo 19:** PASS {grand['v19_pass']} / FAIL {grand['v19_fail']}",
        f"- **Regression candidates:** "
        f"{cls_totals.get('REGRESSION_CANDIDATE', 0)} (pending triage)",
        f"- **Fixed cases:** {cls_totals.get('FIXED', 0)}",
        f"- **Automation coverage:** {auto_cov}% of all in-scope cases "
        f"({grand['automated']}/{total})",
        f"- **Execution coverage:** v17 {exec_cov_v17}% "
        f"({grand['executed_v17']}/{total}) · v19 {exec_cov_v19}% "
        f"({grand['executed_v19']}/{total})",
        "",
        "## Classification totals",
        "",
        "| Classification | Count |",
        "|---|---:|",
    ]
    for cls in ("SAME_BEHAVIOR", "REGRESSION_CANDIDATE", "FIXED",
                "SAME_FAILURE", "BLOCKED", "NOT_COMPARED"):
        summary.append(f"| {cls} | {cls_totals.get(cls, 0)} |")
    summary += [
        "",
        "## Per workflow",
        "",
        "| Workflow | Name | TCs | Automated | v17 P/F | v19 P/F "
        "| Regr. cand. | Fixed |",
        "|---|---|---:|---:|---|---|---:|---:|",
        *per_fg_lines,
        "",
        "## Reading guide",
        "",
        "- v19 executions are BLOCKED until a local Odoo 19 environment "
        "exists — the v19 side of every comparison is pending, so "
        "regression candidates cannot exist yet by construction.",
        "- v17 FAILs where the workbook expectation encodes the v19 target "
        "state (formalized fields, ACL decision #4, DW-fixes, the v19 "
        "discount formula) are the *documented baseline*, expected to "
        "classify as FIXED once v19 runs.",
        "- Evidence per execution (steps, assertions, logs, screenshots, "
        "baselines) is in the web UI: test case → EVIDENCE.",
        "",
    ]
    out = REPORTS / "WORKFLOW_SUMMARY.md"
    out.write_text("\n".join(summary), encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
