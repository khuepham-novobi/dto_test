# DataOne 17 → 19 — In-Scope Workflow Summary

Generated 2026-09-05 04:10. Source: persisted executions in `data/results.db` + the workbook-synced registry (156 in-scope test cases across 9 workflows).

## Headline numbers

- **Total cases:** 156
- **Automated (covered by platform tests):** 141
- **Manual-only:** 15
- **Blocked (any environment):** 40
- **Odoo 17:** PASS 54 / FAIL 18
- **Odoo 19:** PASS 86 / FAIL 36
- **Regression candidates:** 16 (pending triage)
- **Fixed cases:** 6
- **Automation coverage:** 90.4% of all in-scope cases (141/156)
- **Execution coverage:** v17 64.1% (100/156) · v19 90.4% (141/156)

## Classification totals

| Classification | Count |
|---|---:|
| SAME_BEHAVIOR | 38 |
| REGRESSION_CANDIDATE | 16 |
| FIXED | 6 |
| SAME_FAILURE | 11 |
| BLOCKED | 40 |
| NOT_COMPARED | 45 |

## Per workflow

| Workflow | Name | TCs | Automated | v17 P/F | v19 P/F | Regr. cand. | Fixed |
|---|---|---:|---:|---|---|---:|---:|
| DATAONE-WF-002 | Quotation → sales order confirmation | 37 | 37 | 29/6 | 31/4 | 1 | 3 |
| DATAONE-WF-003 | Quotation revision | 6 | 6 | 0/6 | 2/4 | 0 | 2 |
| DATAONE-WF-005 | Manufacturing Order Planning & Work-Order  | 10 | 6 | 0/0 | 5/0 | 0 | 0 |
| DATAONE-WF-006 | Manufacturing Execution on the Shop Floor | 14 | 8 | 0/0 | 4/0 | 0 | 0 |
| DATAONE-WF-007 | MO Completion, Serial-Number Generation &  | 17 | 12 | 0/0 | 5/2 | 0 | 0 |
| DATAONE-WF-009 | Component Shortage Auto-Substitution | 8 | 8 | 0/0 | 6/2 | 0 | 0 |
| DATAONE-WF-013 | Customer Invoice Posting: COGS and Revenue | 39 | 39 | 18/2 | 21/16 | 14 | 0 |
| DATAONE-WF-020 | Supplier Master Import from Workday | 18 | 18 | 7/4 | 7/8 | 1 | 1 |
| DATAONE-WF-025 | Gross Requirements Planning | 7 | 7 | 0/0 | 5/0 | 0 | 0 |

## Reading guide

- v19 executions are BLOCKED until a local Odoo 19 environment exists — the v19 side of every comparison is pending, so regression candidates cannot exist yet by construction.
- v17 FAILs where the workbook expectation encodes the v19 target state (formalized fields, ACL decision #4, DW-fixes, the v19 discount formula) are the *documented baseline*, expected to classify as FIXED once v19 runs.
- Evidence per execution (steps, assertions, logs, screenshots, baselines) is in the web UI: test case → EVIDENCE.
