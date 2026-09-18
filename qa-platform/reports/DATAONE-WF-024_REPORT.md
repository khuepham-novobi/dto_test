# DATAONE-WF-024 Report — RMA: Customer and Vendor Returns

Generated 2026-09-18 16:45 by `scripts/gen_reports.py` from persisted execution results (`data/results.db`) and the workbook-synced registry. Expected results are the workbook's, verbatim.

## Counts

- Test cases: **8**
- Automated (covered by platform tests): **8** of 8 automatable
- Manual-only: **0**
- Currently BLOCKED (either environment): **0**
- Odoo 17: PASS 0 / FAIL 0 / BLOCKED 0 / SKIPPED 0 / not executed 8
- Odoo 19: PASS 0 / FAIL 0 / BLOCKED 0 / not executed 0

## Cross-version classification

| Classification | Count |
|---|---:|
| SAME_BEHAVIOR | 0 |
| REGRESSION_CANDIDATE | 0 |
| FIXED | 0 |
| SAME_FAILURE | 0 |
| BLOCKED | 0 |
| NOT_COMPARED | 8 |

> REGRESSION_CANDIDATE is not a confirmed regression until failure triage; BLOCKED reflects the missing local Odoo 19 environment (see docs/ENVIRONMENT_STATUS.md).

## Per test case

| TC | Title | Prio | Automation | v17 | v19 | Classification |
|---|---|---|---|---|---|---|
| DATAONE-TC044 | RMA sequence YYYY-nnn continues without collision | P0 | AUTOMATED | NOT_RUN | SKIPPED | NOT_COMPARED |
| DATAONE-TC184 | A return created through the wizard is numbered YYYY-nnn | P1 | AUTOMATED | NOT_RUN | SKIPPED | NOT_COMPARED |
| DATAONE-TC185 | The return picking's note is the company vendor-refund narration | P1 | AUTOMATED | NOT_RUN | SKIPPED | NOT_COMPARED |
| DATAONE-TC186 | Reason for Return and Return Notes are required on an RMA picking and  | P1 | AUTOMATED | NOT_RUN | SKIPPED | NOT_COMPARED |
| DATAONE-TC187 | do_print_picking() returns the RMA report for an RMA and the standard  | P1 | AUTOMATED | NOT_RUN | SKIPPED | NOT_COMPARED |
| DATAONE-TC188 | The three RMA menus exist and the all-RMAs queue lists every numbered  | P2 | AUTOMATED | NOT_RUN | SKIPPED | NOT_COMPARED |
| DATAONE-TC189 | Return and Replenish adds exactly one zero-priced line per returned li | P0 | AUTOMATED | NOT_RUN | SKIPPED | NOT_COMPARED |
| DATAONE-TC190 | On a rebuilt database the customer and vendor RMA queues return the ri | P0 | AUTOMATED | NOT_RUN | SKIPPED | NOT_COMPARED |
