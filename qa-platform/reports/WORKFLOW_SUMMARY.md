# DataOne 17 → 19 — In-Scope Workflow Summary

Generated 2026-08-25 11:52. Source: persisted executions in `data/results.db` + the workbook-synced registry (100 in-scope test cases across 4 workflows).

## Headline numbers

- **Total cases:** 100
- **Automated (covered by platform tests):** 100
- **Manual-only:** 6
- **Blocked (any environment):** 0
- **Odoo 17:** PASS 0 / FAIL 0
- **Odoo 19:** PASS 0 / FAIL 0
- **Regression candidates:** 0 (pending triage)
- **Fixed cases:** 0
- **Automation coverage:** 100.0% of all in-scope cases (100/100)
- **Execution coverage:** v17 0.0% (0/100) · v19 0.0% (0/100)

## Classification totals

| Classification | Count |
|---|---:|
| SAME_BEHAVIOR | 0 |
| REGRESSION_CANDIDATE | 0 |
| FIXED | 0 |
| SAME_FAILURE | 0 |
| BLOCKED | 0 |
| NOT_COMPARED | 100 |

## Per workflow

| Workflow | Name | TCs | Automated | v17 P/F | v19 P/F | Regr. cand. | Fixed |
|---|---|---:|---:|---|---|---:|---:|
| DATAONE-WF-002 | Quotation → sales order confirmation | 37 | 37 | 0/0 | 0/0 | 0 | 0 |
| DATAONE-WF-003 | Quotation revision | 6 | 6 | 0/0 | 0/0 | 0 | 0 |
| DATAONE-WF-013 | Customer Invoice Posting: COGS and Revenue | 39 | 39 | 0/0 | 0/0 | 0 | 0 |
| DATAONE-WF-020 | Supplier Master Import from Workday | 18 | 18 | 0/0 | 0/0 | 0 | 0 |

## Reading guide

- v19 executions are BLOCKED until a local Odoo 19 environment exists — the v19 side of every comparison is pending, so regression candidates cannot exist yet by construction.
- v17 FAILs where the workbook expectation encodes the v19 target state (formalized fields, ACL decision #4, DW-fixes, the v19 discount formula) are the *documented baseline*, expected to classify as FIXED once v19 runs.
- Evidence per execution (steps, assertions, logs, screenshots, baselines) is in the web UI: test case → EVIDENCE.
