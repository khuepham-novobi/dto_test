# DATAONE-WF-020 Report — Supplier Master Import from Workday

Generated 2026-09-05 04:10 by `scripts/gen_reports.py` from persisted execution results (`data/results.db`) and the workbook-synced registry. Expected results are the workbook's, verbatim.

## Counts

- Test cases: **18**
- Automated (covered by platform tests): **18** of 18 automatable
- Manual-only: **0**
- Currently BLOCKED (either environment): **7**
- Odoo 17: PASS 7 / FAIL 4 / BLOCKED 7 / SKIPPED 0 / not executed 0
- Odoo 19: PASS 7 / FAIL 8 / BLOCKED 3 / not executed 0

## Cross-version classification

| Classification | Count |
|---|---:|
| SAME_BEHAVIOR | 6 |
| REGRESSION_CANDIDATE | 1 |
| FIXED | 1 |
| SAME_FAILURE | 3 |
| BLOCKED | 7 |
| NOT_COMPARED | 0 |

> REGRESSION_CANDIDATE is not a confirmed regression until failure triage; BLOCKED reflects the missing local Odoo 19 environment (see docs/ENVIRONMENT_STATUS.md).

## Per test case

| TC | Title | Prio | Automation | v17 | v19 | Classification |
|---|---|---|---|---|---|---|
| DATAONE-TC008 | Every ir.cron from the inventory exists, is active, and has the expect | P1 | AUTOMATED | PASS | FAIL | REGRESSION_CANDIDATE |
| DATAONE-TC012 | The Python dependency set installs on the target Python | P0 | AUTOMATED | BLOCKED | BLOCKED | BLOCKED |
| DATAONE-TC293 | The 5-minute GET pull creates a Pending sftp.file with an attachment a | P0 | AUTOMATED | BLOCKED | FAIL | BLOCKED |
| DATAONE-TC294 | Archive-on-download, including the (YYYY-MM-DD HHMMSS UTC) collision s | P1 | AUTOMATED | BLOCKED | BLOCKED | BLOCKED |
| DATAONE-TC295 | No archive path configured — <path>_archived is auto-created and writt | P2 | AUTOMATED | BLOCKED | BLOCKED | BLOCKED |
| DATAONE-TC297 | Folder uniqueness constraint, including archived folders | P2 | AUTOMATED | PASS | PASS | SAME_BEHAVIOR |
| DATAONE-TC298 | Process Now visibility and Only pending file(s) can be processed! | P2 | AUTOMATED | PASS | PASS | SAME_BEHAVIOR |
| DATAONE-TC301 | sftp.log capture — level, method, traceback, resolve / unresolve | P2 | AUTOMATED | ERROR | ERROR | SAME_FAILURE |
| DATAONE-TC302 | LIVE DEFECT: a folder with a non-empty regex raises TypeError; the fil | P0 | AUTOMATED | FAIL | PASS | FIXED |
| DATAONE-TC305 | v19: repeated cron failure silently deactivates the poller | P0 | AUTOMATED | BLOCKED | FAIL | BLOCKED |
| DATAONE-TC331 | GATE: nine-column CSV, five rows, one failure, no activity on any part | P0 | AUTOMATED | PASS | PASS | SAME_BEHAVIOR |
| DATAONE-TC332 | A new vendor is created with supplier_rank = 1 and is selectable on a  | P1 | AUTOMATED | PASS | PASS | SAME_BEHAVIOR |
| DATAONE-TC333 | An existing partner matched on ref is overwritten unconditionally, bla | P0 | AUTOMATED | FAIL | FAIL | SAME_FAILURE |
| DATAONE-TC334 | A blank payment term clears the value; an unresolvable term fails only | P0 | AUTOMATED | PASS | PASS | SAME_BEHAVIOR |
| DATAONE-TC335 | "Texas (US)" resolves the state and derives the country; blank clears  | P1 | AUTOMATED | FAIL | FAIL | SAME_FAILURE |
| DATAONE-TC336 | The file goes Failed with no activity on any partner; re-process repai | P1 | AUTOMATED | PASS | PASS | SAME_BEHAVIOR |
| DATAONE-TC459 | Every cron in the inventory exists, is active, has the expected interv | P0 | AUTOMATED | BLOCKED | FAIL | BLOCKED |
| DATAONE-TC460 | A repeatedly failing cron is auto-deactivated on v19, silently stoppin | P0 | AUTOMATED | BLOCKED | FAIL | BLOCKED |

## Failure notes (triage input)

- **DATAONE-TC008** [Odoo 19 → FAIL / ASSERTION] No differences vs v17 baseline: expected [], got ["dto_account_workday.ir_cron_export_workday_journal_entries: baseline='active=True interval=1days priority=5' current=None", "dto_account_workday.ir_cron_export_workday_vendor_bills: baseline='active=True inter
- **DATAONE-TC293** [Odoo 19 → FAIL / ASSERTION] GET poller active: expected True, got False
- **DATAONE-TC293** [Odoo 17 → ERROR / AUTOMATION_ERROR] OdooRPCError: sftp.server.search failed: sftp.server
- **DATAONE-TC301** [Odoo 19 → ERROR / AUTOMATION_ERROR] KeyError: 'traceback'
- **DATAONE-TC301** [Odoo 17 → ERROR / AUTOMATION_ERROR] KeyError: 'traceback'
- **DATAONE-TC302** [Odoo 19 → ERROR / INTERRUPTED] Interrupted — the runner process stopped before this execution finished. Re-run the test.
- **DATAONE-TC302** [Odoo 17 → FAIL / ASSERTION] the invalid pattern was refused rather than stored: expected True, got 'no error raised'
- **DATAONE-TC305** [Odoo 19 → FAIL / ASSERTION] GET poller active: expected True, got False
- **DATAONE-TC333** [Odoo 19 → FAIL / ASSERTION] chatter messages added by the import: expected 0, got 2
- **DATAONE-TC333** [Odoo 17 → FAIL / ASSERTION] chatter messages added by the import: expected 0, got 2
- **DATAONE-TC335** [Odoo 19 → FAIL / ASSERTION] wrong-code state_id: expected 52, got None
- **DATAONE-TC335** [Odoo 17 → FAIL / ASSERTION] wrong-code state_id: expected 52, got None
- **DATAONE-TC459** [Odoo 19 → FAIL / ASSERTION] inactive crons: expected [], got ['novobi_sftp_connection.ir_cron_get_sftp_files', 'novobi_sftp_connection.ir_cron_post_sftp_files', 'novobi_sftp_connection.ir_cron_process_sftp_files', 'queue_job.ir_cron_autovacuum_queue_jobs']
- **DATAONE-TC460** [Odoo 19 → FAIL / ASSERTION] subject cron is active: expected True, got False
