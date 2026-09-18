# DATAONE-WF-018 Report — Vendor Bill Export to Workday

Generated 2026-09-18 17:29 by `scripts/gen_reports.py` from persisted execution results (`data/results.db`) and the workbook-synced registry. Expected results are the workbook's, verbatim.

## Counts

- Test cases: **12**
- Automated (covered by platform tests): **10** of 10 automatable
- Manual-only: **1**
- Currently BLOCKED (either environment): **4**
- Odoo 17: PASS 0 / FAIL 0 / BLOCKED 0 / SKIPPED 0 / not executed 12
- Odoo 19: PASS 1 / FAIL 5 / BLOCKED 4 / not executed 2

## Cross-version classification

| Classification | Count |
|---|---:|
| SAME_BEHAVIOR | 0 |
| REGRESSION_CANDIDATE | 0 |
| FIXED | 0 |
| SAME_FAILURE | 0 |
| BLOCKED | 4 |
| NOT_COMPARED | 8 |

> REGRESSION_CANDIDATE is not a confirmed regression until failure triage; BLOCKED reflects the missing local Odoo 19 environment (see docs/ENVIRONMENT_STATUS.md).

## Per test case

| TC | Title | Prio | Automation | v17 | v19 | Classification |
|---|---|---|---|---|---|---|
| DATAONE-TC035 | Workday export state (export_workday × move_type): nothing re-exported | P0 | AUTOMATED | NOT_RUN | BLOCKED | BLOCKED |
| DATAONE-TC296 | POST duplicate guard refuses to overwrite and sets the file Failed | P0 | AUTOMATED | NOT_RUN | BLOCKED | BLOCKED |
| DATAONE-TC300 | Re-post returns a Failed POST file to Pending and re-uploads | P1 | AUTOMATED | NOT_RUN | ERROR | NOT_COMPARED |
| DATAONE-TC304 | A database-stored attachment cannot be POSTed (store_fname empty) | P2 | AUTOMATED | NOT_RUN | BLOCKED | BLOCKED |
| DATAONE-TC316 | GATE: four bills, one duplicate ref dropped with the exact activity, t | P0 | AUTOMATED | NOT_RUN | FAIL | NOT_COMPARED |
| DATAONE-TC317 | The 20-row column contract asserted cell by cell | P0 | AUTOMATED | NOT_RUN | FAIL | NOT_COMPARED |
| DATAONE-TC318 | Three blocking validations, exact strings, whole selection refused | P0 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |
| DATAONE-TC319 | have_attachment = True is required by the domain — and its stale-compu | P0 | AUTOMATED | NOT_RUN | ERROR | NOT_COMPARED |
| DATAONE-TC320 | The wizard's amber warning rows sort to the top before anything leaves | P2 | MANUAL_ONLY | MANUAL | MANUAL | NOT_COMPARED |
| DATAONE-TC321 | The daily cron has no limit: the whole backlog in one transaction | P1 | MANUAL_ONLY | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| DATAONE-TC322 | v19: column FT and the analytic tail GG / GK go silently wrong | P0 | AUTOMATED | NOT_RUN | BLOCKED | BLOCKED |
| DATAONE-TC326 | workday_document and export_workday stamped on both the payment and th | P0 | AUTOMATED | NOT_RUN | FAIL | NOT_COMPARED |

## Failure notes (triage input)

- **DATAONE-TC300** [Odoo 19 → ERROR / AUTOMATION_ERROR] OdooRPCError: sftp.file.mark_sync_failed failed: 'str' object has no attribute 'date'
- **DATAONE-TC316** [Odoo 19 → FAIL / ASSERTION] the file carries exactly BB-1, BB-3 and BB-4, in selection order: expected [192795, 192797, 192798], got [192798, 192797, 192795]
- **DATAONE-TC317** [Odoo 19 → FAIL / ASSERTION] every asserted cell on row 6 carries its mapped value (one dict, so a failure reports all of them): expected {}, got {'Q': {'expected': '2026-08-01', 'actual': '2026-08-01 00:00:00'}, 'AF': {'expected': '2026-01-15', 'actual': '2026-01-15 00:00:00'}}
- **DATAONE-TC319** [Odoo 19 → ERROR / AUTOMATION_ERROR] OdooRPCError: account.move.action_post failed: User cannot confirm the bill. The Vendor Bill requires an attachment before posting.
- **DATAONE-TC326** [Odoo 19 → FAIL / ASSERTION] two payments created: expected 2, got 8
