# DATAONE-WF-025 Report — Gross Requirements Planning

Generated 2026-09-05 04:10 by `scripts/gen_reports.py` from persisted execution results (`data/results.db`) and the workbook-synced registry. Expected results are the workbook's, verbatim.

## Counts

- Test cases: **7**
- Automated (covered by platform tests): **7** of 7 automatable
- Manual-only: **0**
- Currently BLOCKED (either environment): **2**
- Odoo 17: PASS 0 / FAIL 0 / BLOCKED 0 / SKIPPED 0 / not executed 7
- Odoo 19: PASS 5 / FAIL 0 / BLOCKED 2 / not executed 0

## Cross-version classification

| Classification | Count |
|---|---:|
| SAME_BEHAVIOR | 0 |
| REGRESSION_CANDIDATE | 0 |
| FIXED | 0 |
| SAME_FAILURE | 0 |
| BLOCKED | 2 |
| NOT_COMPARED | 5 |

> REGRESSION_CANDIDATE is not a confirmed regression until failure triage; BLOCKED reflects the missing local Odoo 19 environment (see docs/ENVIRONMENT_STATUS.md).

## Per test case

| TC | Title | Prio | Automation | v17 | v19 | Classification |
|---|---|---|---|---|---|---|
| DATAONE-TC026 | On-hand quantity per product × location is unchanged | P0 | AUTOMATED | NOT_RUN | BLOCKED | BLOCKED |
| DATAONE-TC031 | Product type / detailed_type → type + is_storable conversion is correc | P0 | AUTOMATED | NOT_RUN | BLOCKED | BLOCKED |
| DATAONE-TC144 | Run is refused while any row is invalid, and "Remove all invalid produ | P0 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |
| DATAONE-TC145 | GATE (WF-025) The four columns, against a fixture built to distinguish | P0 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |
| DATAONE-TC146 | Availability excludes locations flagged "Ignore Quantities for Gross R | P0 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |
| DATAONE-TC147 | Reserved quantity is subtracted everywhere except in a location named  | P0 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |
| DATAONE-TC148 | v19 SILENT Storable components still appear in the report | P0 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |
