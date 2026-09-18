# DATAONE-WF-012 Report — Auto-Invoicing on Delivery Validation

Generated 2026-09-18 16:39 by `scripts/gen_reports.py` from persisted execution results (`data/results.db`) and the workbook-synced registry. Expected results are the workbook's, verbatim.

## Counts

- Test cases: **4**
- Automated (covered by platform tests): **4** of 4 automatable
- Manual-only: **1**
- Currently BLOCKED (either environment): **0**
- Odoo 17: PASS 1 / FAIL 0 / BLOCKED 0 / SKIPPED 0 / not executed 3
- Odoo 19: PASS 0 / FAIL 0 / BLOCKED 0 / not executed 0

## Cross-version classification

| Classification | Count |
|---|---:|
| SAME_BEHAVIOR | 0 |
| REGRESSION_CANDIDATE | 0 |
| FIXED | 0 |
| SAME_FAILURE | 0 |
| BLOCKED | 0 |
| NOT_COMPARED | 4 |

> REGRESSION_CANDIDATE is not a confirmed regression until failure triage; BLOCKED reflects the missing local Odoo 19 environment (see docs/ENVIRONMENT_STATUS.md).

## Per test case

| TC | Title | Prio | Automation | v17 | v19 | Classification |
|---|---|---|---|---|---|---|
| DATAONE-TC023 | Invoice totals by year × move_type × state | P0 | AUTOMATED | PASS | SKIPPED | NOT_COMPARED |
| DATAONE-TC288 | Validating a project delivery creates exactly one POSTED invoice | P0 | AUTOMATED | NOT_RUN | SKIPPED | NOT_COMPARED |
| DATAONE-TC289 | inventory and cost_center auto-invoice; buy does not | P0 | AUTOMATED | NOT_RUN | SKIPPED | NOT_COMPARED |
| DATAONE-TC290 | The shipment email is routed by order type, with the Delivery Slip att | P2 | AUTOMATED | NOT_RUN | SKIPPED | NOT_COMPARED |
