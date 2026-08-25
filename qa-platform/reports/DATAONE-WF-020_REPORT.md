# DATAONE-WF-020 Report — Supplier Master Import from Workday

Generated 2026-08-25 11:52 by `scripts/gen_reports.py` from persisted execution results (`data/results.db`) and the workbook-synced registry. Expected results are the workbook's, verbatim.

## Counts

- Test cases: **18**
- Automated (covered by platform tests): **18** of 18 automatable
- Manual-only: **0**
- Currently BLOCKED (either environment): **0**
- Odoo 17: PASS 0 / FAIL 0 / BLOCKED 0 / SKIPPED 0 / not executed 18
- Odoo 19: PASS 0 / FAIL 0 / BLOCKED 0 / not executed 18

## Cross-version classification

| Classification | Count |
|---|---:|
| SAME_BEHAVIOR | 0 |
| REGRESSION_CANDIDATE | 0 |
| FIXED | 0 |
| SAME_FAILURE | 0 |
| BLOCKED | 0 |
| NOT_COMPARED | 18 |

> REGRESSION_CANDIDATE is not a confirmed regression until failure triage; BLOCKED reflects the missing local Odoo 19 environment (see docs/ENVIRONMENT_STATUS.md).

## Per test case

| TC | Title | Prio | Automation | v17 | v19 | Classification |
|---|---|---|---|---|---|---|
| DATAONE-TC008 | Every ir.cron from the inventory exists, is active, and has the expect | P1 | AUTOMATED | NOT_RUN | NOT_RUN | NOT_COMPARED |
| DATAONE-TC012 | The Python dependency set installs on the target Python | P0 | AUTOMATED | NOT_RUN | NOT_RUN | NOT_COMPARED |
| DATAONE-TC293 | The 5-minute GET pull creates a Pending sftp.file with an attachment a | P0 | AUTOMATED | NOT_RUN | NOT_RUN | NOT_COMPARED |
| DATAONE-TC294 | Archive-on-download, including the (YYYY-MM-DD HHMMSS UTC) collision s | P1 | AUTOMATED | NOT_RUN | NOT_RUN | NOT_COMPARED |
| DATAONE-TC295 | No archive path configured — <path>_archived is auto-created and writt | P2 | AUTOMATED | NOT_RUN | NOT_RUN | NOT_COMPARED |
| DATAONE-TC297 | Folder uniqueness constraint, including archived folders | P2 | AUTOMATED | NOT_RUN | NOT_RUN | NOT_COMPARED |
| DATAONE-TC298 | Process Now visibility and Only pending file(s) can be processed! | P2 | AUTOMATED | NOT_RUN | NOT_RUN | NOT_COMPARED |
| DATAONE-TC301 | sftp.log capture — level, method, traceback, resolve / unresolve | P2 | AUTOMATED | NOT_RUN | NOT_RUN | NOT_COMPARED |
| DATAONE-TC302 | LIVE DEFECT: a folder with a non-empty regex raises TypeError; the fil | P0 | AUTOMATED | NOT_RUN | NOT_RUN | NOT_COMPARED |
| DATAONE-TC305 | v19: repeated cron failure silently deactivates the poller | P0 | AUTOMATED | NOT_RUN | NOT_RUN | NOT_COMPARED |
| DATAONE-TC331 | GATE: nine-column CSV, five rows, one failure, no activity on any part | P0 | AUTOMATED | NOT_RUN | NOT_RUN | NOT_COMPARED |
| DATAONE-TC332 | A new vendor is created with supplier_rank = 1 and is selectable on a  | P1 | AUTOMATED | NOT_RUN | NOT_RUN | NOT_COMPARED |
| DATAONE-TC333 | An existing partner matched on ref is overwritten unconditionally, bla | P0 | AUTOMATED | NOT_RUN | NOT_RUN | NOT_COMPARED |
| DATAONE-TC334 | A blank payment term clears the value; an unresolvable term fails only | P0 | AUTOMATED | NOT_RUN | NOT_RUN | NOT_COMPARED |
| DATAONE-TC335 | "Texas (US)" resolves the state and derives the country; blank clears  | P1 | AUTOMATED | NOT_RUN | NOT_RUN | NOT_COMPARED |
| DATAONE-TC336 | The file goes Failed with no activity on any partner; re-process repai | P1 | AUTOMATED | NOT_RUN | NOT_RUN | NOT_COMPARED |
| DATAONE-TC459 | Every cron in the inventory exists, is active, has the expected interv | P0 | AUTOMATED | NOT_RUN | NOT_RUN | NOT_COMPARED |
| DATAONE-TC460 | A repeatedly failing cron is auto-deactivated on v19, silently stoppin | P0 | AUTOMATED | NOT_RUN | NOT_RUN | NOT_COMPARED |

## Feasibility decisions

implemented 13 · blocked_stub 5 · not_implemented 0 (details: `reports/data/wf020_feasibility.json`)
