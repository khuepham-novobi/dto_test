# DataOne 17 → 19 — In-Scope Workflow Summary

Generated 2026-09-18 17:29. Source: persisted executions in `data/results.db` + the workbook-synced registry (355 in-scope test cases across 24 workflows).

## Headline numbers

- **Total cases:** 355
- **Automated (covered by platform tests):** 337
- **Manual-only:** 23
- **Blocked (any environment):** 61
- **Odoo 17:** PASS 54 / FAIL 18
- **Odoo 19:** PASS 144 / FAIL 140
- **Regression candidates:** 16 (pending triage)
- **Fixed cases:** 6
- **Automation coverage:** 94.9% of all in-scope cases (337/355)
- **Execution coverage:** v17 28.2% (100/355) · v19 94.9% (337/355)

## Classification totals

| Classification | Count |
|---|---:|
| SAME_BEHAVIOR | 38 |
| REGRESSION_CANDIDATE | 16 |
| FIXED | 6 |
| SAME_FAILURE | 11 |
| BLOCKED | 61 |
| NOT_COMPARED | 223 |

## Per workflow

| Workflow | Name | TCs | Automated | v17 P/F | v19 P/F | Regr. cand. | Fixed |
|---|---|---:|---:|---|---|---:|---:|
| DATAONE-WF-001 | Workday requisition → sales order (inbound | 7 | 7 | 0/0 | 3/4 | 0 | 0 |
| DATAONE-WF-002 | Quotation → sales order confirmation | 37 | 37 | 29/6 | 31/4 | 1 | 3 |
| DATAONE-WF-003 | Quotation revision | 6 | 6 | 0/6 | 2/4 | 0 | 2 |
| DATAONE-WF-005 | Manufacturing Order Planning & Work-Order  | 10 | 6 | 0/0 | 5/0 | 0 | 0 |
| DATAONE-WF-006 | Manufacturing Execution on the Shop Floor | 14 | 8 | 0/0 | 8/0 | 0 | 0 |
| DATAONE-WF-007 | MO Completion, Serial-Number Generation &  | 17 | 12 | 0/0 | 2/7 | 0 | 0 |
| DATAONE-WF-008 | Manufacturing Cost Absorption (Labour and  | 23 | 23 | 2/0 | 2/20 | 2 | 0 |
| DATAONE-WF-009 | Component Shortage Auto-Substitution | 8 | 8 | 0/0 | 6/2 | 0 | 0 |
| DATAONE-WF-010 | MO Test-Result Attachment Import ("Product | 7 | 7 | 0/0 | 1/5 | 0 | 0 |
| DATAONE-WF-011 | Delivery, Boxing, Blind Ship & Packing Doc | 19 | 19 | 0/0 | 7/9 | 0 | 0 |
| DATAONE-WF-012 | Auto-Invoicing on Delivery Validation | 4 | 4 | 1/0 | 0/4 | 1 | 0 |
| DATAONE-WF-013 | Customer Invoice Posting: COGS and Revenue | 32 | 32 | 11/2 | 9/9 | 7 | 0 |
| DATAONE-WF-015 | Per-Line Receipt, Quality Check & Packing  | 21 | 20 | 0/0 | 3/14 | 0 | 0 |
| DATAONE-WF-016 | Vendor Bill Entry & Posting | 18 | 18 | 2/0 | 4/13 | 2 | 0 |
| DATAONE-WF-017 | Journal Entry Export to Workday | 13 | 13 | 0/0 | 5/5 | 0 | 0 |
| DATAONE-WF-018 | Vendor Bill Export to Workday | 12 | 10 | 0/0 | 1/5 | 0 | 0 |
| DATAONE-WF-019 | Vendor Payment Import from Workday | 8 | 8 | 0/0 | 1/6 | 0 | 0 |
| DATAONE-WF-020 | Supplier Master Import from Workday | 18 | 18 | 7/4 | 7/8 | 1 | 1 |
| DATAONE-WF-021 | Cycle Counting and Inventory Adjustment | 13 | 13 | 2/0 | 1/10 | 2 | 0 |
| DATAONE-WF-022 | Scrap with Defect Coding and Approval | 7 | 7 | 0/0 | 5/1 | 0 | 0 |
| DATAONE-WF-024 | RMA: Customer and Vendor Returns | 8 | 8 | 0/0 | 2/5 | 0 | 0 |
| DATAONE-WF-025 | Gross Requirements Planning | 7 | 7 | 0/0 | 5/0 | 0 | 0 |
| DATAONE-WF-026 | Historical Data Migration Import | 23 | 23 | 0/0 | 18/4 | 0 | 0 |
| DATAONE-WF-027 | Management Reporting | 23 | 23 | 0/0 | 16/1 | 0 | 0 |

## Reading guide

- v19 executions are BLOCKED until a local Odoo 19 environment exists — the v19 side of every comparison is pending, so regression candidates cannot exist yet by construction.
- v17 FAILs where the workbook expectation encodes the v19 target state (formalized fields, ACL decision #4, DW-fixes, the v19 discount formula) are the *documented baseline*, expected to classify as FIXED once v19 runs.
- Evidence per execution (steps, assertions, logs, screenshots, baselines) is in the web UI: test case → EVIDENCE.
