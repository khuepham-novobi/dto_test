# DATAONE-WF-005 Report — Manufacturing Order Planning & Work-Order Generation

Generated 2026-09-05 04:10 by `scripts/gen_reports.py` from persisted execution results (`data/results.db`) and the workbook-synced registry. Expected results are the workbook's, verbatim.

## Counts

- Test cases: **10**
- Automated (covered by platform tests): **6** of 9 automatable
- Manual-only: **1**
- Currently BLOCKED (either environment): **1**
- Odoo 17: PASS 0 / FAIL 0 / BLOCKED 0 / SKIPPED 0 / not executed 10
- Odoo 19: PASS 5 / FAIL 0 / BLOCKED 1 / not executed 4

## Cross-version classification

| Classification | Count |
|---|---:|
| SAME_BEHAVIOR | 0 |
| REGRESSION_CANDIDATE | 0 |
| FIXED | 0 |
| SAME_FAILURE | 0 |
| BLOCKED | 1 |
| NOT_COMPARED | 9 |

> REGRESSION_CANDIDATE is not a confirmed regression until failure triage; BLOCKED reflects the missing local Odoo 19 environment (see docs/ENVIRONMENT_STATUS.md).

## Per test case

| TC | Title | Prio | Automation | v17 | v19 | Classification |
|---|---|---|---|---|---|---|
| DATAONE-TC058 | Decimal precision records, including the 'Product Unit of Measure' ren | P1 | AUTOMATED | NOT_RUN | BLOCKED | BLOCKED |
| DATAONE-TC101 | Assigning an MO Operation Type generates one work order per line | P1 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |
| DATAONE-TC102 | Changing the operation type destroys the old work orders and regenerat | P0 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |
| DATAONE-TC103 | Deleting an operation-type line removes the matching work order from o | P1 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |
| DATAONE-TC104 | An operation type referenced by any MO cannot be deleted | P2 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |
| DATAONE-TC105 | An MO with no operation type keeps core's BoM-driven routing, and the  | P1 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |
| DATAONE-TC123 | The pick list shows only not-yet-picked components, with barcodes and  | P1 | MANUAL_ONLY | MANUAL | MANUAL | NOT_COMPARED |
| DATAONE-TC129 | The Shop Floor MO card reads MO name - SO name | P1 | PLANNED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| DATAONE-TC149 | Clone Product copies the template, its cycle-count category and one Bo | P2 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| DATAONE-TC150 | With several BoMs the clone wizard asks which one to copy | P2 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
