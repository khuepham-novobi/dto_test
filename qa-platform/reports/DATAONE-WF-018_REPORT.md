# DATAONE-WF-018 Report — Vendor Bill Export to Workday

Generated 2026-09-18 16:26 by `scripts/gen_reports.py` from persisted execution results (`data/results.db`) and the workbook-synced registry. Expected results are the workbook's, verbatim.

## Counts

- Test cases: **12**
- Automated (covered by platform tests): **10** of 10 automatable
- Manual-only: **1**
- Currently BLOCKED (either environment): **0**
- Odoo 17: PASS 0 / FAIL 0 / BLOCKED 0 / SKIPPED 0 / not executed 12
- Odoo 19: PASS 0 / FAIL 0 / BLOCKED 0 / not executed 2

## Cross-version classification

| Classification | Count |
|---|---:|
| SAME_BEHAVIOR | 0 |
| REGRESSION_CANDIDATE | 0 |
| FIXED | 0 |
| SAME_FAILURE | 0 |
| BLOCKED | 0 |
| NOT_COMPARED | 12 |

> REGRESSION_CANDIDATE is not a confirmed regression until failure triage; BLOCKED reflects the missing local Odoo 19 environment (see docs/ENVIRONMENT_STATUS.md).

## Per test case

| TC | Title | Prio | Automation | v17 | v19 | Classification |
|---|---|---|---|---|---|---|
| DATAONE-TC035 | Workday export state (export_workday × move_type): nothing re-exported | P0 | AUTOMATED | NOT_RUN | SKIPPED | NOT_COMPARED |
| DATAONE-TC296 | POST duplicate guard refuses to overwrite and sets the file Failed | P0 | AUTOMATED | NOT_RUN | SKIPPED | NOT_COMPARED |
| DATAONE-TC300 | Re-post returns a Failed POST file to Pending and re-uploads | P1 | AUTOMATED | NOT_RUN | SKIPPED | NOT_COMPARED |
| DATAONE-TC304 | A database-stored attachment cannot be POSTed (store_fname empty) | P2 | AUTOMATED | NOT_RUN | SKIPPED | NOT_COMPARED |
| DATAONE-TC316 | GATE: four bills, one duplicate ref dropped with the exact activity, t | P0 | AUTOMATED | NOT_RUN | SKIPPED | NOT_COMPARED |
| DATAONE-TC317 | The 20-row column contract asserted cell by cell | P0 | AUTOMATED | NOT_RUN | SKIPPED | NOT_COMPARED |
| DATAONE-TC318 | Three blocking validations, exact strings, whole selection refused | P0 | AUTOMATED | NOT_RUN | SKIPPED | NOT_COMPARED |
| DATAONE-TC319 | have_attachment = True is required by the domain — and its stale-compu | P0 | AUTOMATED | NOT_RUN | SKIPPED | NOT_COMPARED |
| DATAONE-TC320 | The wizard's amber warning rows sort to the top before anything leaves | P2 | MANUAL_ONLY | MANUAL | MANUAL | NOT_COMPARED |
| DATAONE-TC321 | The daily cron has no limit: the whole backlog in one transaction | P1 | MANUAL_ONLY | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| DATAONE-TC322 | v19: column FT and the analytic tail GG / GK go silently wrong | P0 | AUTOMATED | NOT_RUN | SKIPPED | NOT_COMPARED |
| DATAONE-TC326 | workday_document and export_workday stamped on both the payment and th | P0 | AUTOMATED | NOT_RUN | SKIPPED | NOT_COMPARED |
