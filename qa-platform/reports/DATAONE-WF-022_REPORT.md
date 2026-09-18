# DATAONE-WF-022 Report — Scrap with Defect Coding and Approval

Generated 2026-09-18 16:39 by `scripts/gen_reports.py` from persisted execution results (`data/results.db`) and the workbook-synced registry. Expected results are the workbook's, verbatim.

## Counts

- Test cases: **7**
- Automated (covered by platform tests): **7** of 7 automatable
- Manual-only: **0**
- Currently BLOCKED (either environment): **0**
- Odoo 17: PASS 0 / FAIL 0 / BLOCKED 0 / SKIPPED 0 / not executed 7
- Odoo 19: PASS 0 / FAIL 0 / BLOCKED 0 / not executed 0

## Cross-version classification

| Classification | Count |
|---|---:|
| SAME_BEHAVIOR | 0 |
| REGRESSION_CANDIDATE | 0 |
| FIXED | 0 |
| SAME_FAILURE | 0 |
| BLOCKED | 0 |
| NOT_COMPARED | 7 |

> REGRESSION_CANDIDATE is not a confirmed regression until failure triage; BLOCKED reflects the missing local Odoo 19 environment (see docs/ENVIRONMENT_STATUS.md).

## Per test case

| TC | Title | Prio | Automation | v17 | v19 | Classification |
|---|---|---|---|---|---|---|
| DATAONE-TC167 | The scrap order's Journal Entries stat button opens its write-off entr | P1 | AUTOMATED | NOT_RUN | SKIPPED | NOT_COMPARED |
| DATAONE-TC178 | Validate in the quick-scrap dialog opens the full scrap form instead o | P0 | AUTOMATED | NOT_RUN | SKIPPED | NOT_COMPARED |
| DATAONE-TC179 | Validate with a zero quantity raises the exact positive-quantity error | P2 | AUTOMATED | NOT_RUN | SKIPPED | NOT_COMPARED |
| DATAONE-TC180 | Defect code B yields *Received Damaged*, case- and whitespace-insensit | P1 | AUTOMATED | NOT_RUN | SKIPPED | NOT_COMPARED |
| DATAONE-TC181 | An unrecognised defect code yields *Unknown defect code* and is not re | P2 | AUTOMATED | NOT_RUN | SKIPPED | NOT_COMPARED |
| DATAONE-TC182 | Scrap Amount equals quantity × standard price after UoM conversion | P0 | AUTOMATED | NOT_RUN | SKIPPED | NOT_COMPARED |
| DATAONE-TC183 | The Cancelled state is reachable from Draft and is terminal | P2 | AUTOMATED | NOT_RUN | SKIPPED | NOT_COMPARED |
