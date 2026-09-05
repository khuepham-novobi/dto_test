# DATAONE-WF-006 Report — Manufacturing Execution on the Shop Floor

Generated 2026-09-05 04:10 by `scripts/gen_reports.py` from persisted execution results (`data/results.db`) and the workbook-synced registry. Expected results are the workbook's, verbatim.

## Counts

- Test cases: **14**
- Automated (covered by platform tests): **8** of 11 automatable
- Manual-only: **3**
- Currently BLOCKED (either environment): **4**
- Odoo 17: PASS 0 / FAIL 0 / BLOCKED 0 / SKIPPED 0 / not executed 14
- Odoo 19: PASS 4 / FAIL 0 / BLOCKED 4 / not executed 6

## Cross-version classification

| Classification | Count |
|---|---:|
| SAME_BEHAVIOR | 0 |
| REGRESSION_CANDIDATE | 0 |
| FIXED | 0 |
| SAME_FAILURE | 0 |
| BLOCKED | 4 |
| NOT_COMPARED | 10 |

> REGRESSION_CANDIDATE is not a confirmed regression until failure triage; BLOCKED reflects the missing local Odoo 19 environment (see docs/ENVIRONMENT_STATUS.md).

## Per test case

| TC | Title | Prio | Automation | v17 | v19 | Classification |
|---|---|---|---|---|---|---|
| DATAONE-TC003 | The backend asset bundle builds | P0 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |
| DATAONE-TC121 | The ZPL lot label is sent straight to the printer from the Shop Floor, | P1 | MANUAL_ONLY | MANUAL | MANUAL | NOT_COMPARED |
| DATAONE-TC122 | The bin label prints WO #, QTY and DUE DATE on a 102 × 51 mm Dymo labe | P2 | MANUAL_ONLY | MANUAL | MANUAL | NOT_COMPARED |
| DATAONE-TC124 | The cut-sheet wizard is restricted to cuttable products and refuses to | P1 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |
| DATAONE-TC125 | Entering a feet value auto-fills the tolerance from the correct band,  | P1 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |
| DATAONE-TC126 | Feet convert correctly to inches and metres | P1 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |
| DATAONE-TC127 | The printed cut sheet carries the tables and the sign-off block | P2 | MANUAL_ONLY | MANUAL | MANUAL | NOT_COMPARED |
| DATAONE-TC128 | The Shop Floor board renders at all | P0 | PLANNED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| DATAONE-TC130 | All three DataOne buttons appear in the Shop Floor work-order menu and | P1 | PLANNED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| DATAONE-TC131 | The Product Documents dialog: single-doc auto-open, previews, shared l | P1 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| DATAONE-TC132 | A second concurrent timesheet for the same employee raises | P0 | AUTOMATED | NOT_RUN | BLOCKED | BLOCKED |
| DATAONE-TC133 | v19 SILENT The concurrency guard still fires when create receives a li | P0 | AUTOMATED | NOT_RUN | BLOCKED | BLOCKED |
| DATAONE-TC134 | A 5-hour timesheet on a 2-unit MO with a 120 min/unit cap records exac | P0 | AUTOMATED | NOT_RUN | BLOCKED | BLOCKED |
| DATAONE-TC135 | A closed timesheet cannot be edited except by the Change Timesheets gr | P1 | AUTOMATED | NOT_RUN | BLOCKED | BLOCKED |
