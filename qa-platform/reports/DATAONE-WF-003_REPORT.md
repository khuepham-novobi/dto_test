# DATAONE-WF-003 Report — Quotation revision

Generated 2026-08-25 11:52 by `scripts/gen_reports.py` from persisted execution results (`data/results.db`) and the workbook-synced registry. Expected results are the workbook's, verbatim.

## Counts

- Test cases: **6**
- Automated (covered by platform tests): **6** of 6 automatable
- Manual-only: **0**
- Currently BLOCKED (either environment): **0**
- Odoo 17: PASS 0 / FAIL 0 / BLOCKED 0 / SKIPPED 0 / not executed 6
- Odoo 19: PASS 0 / FAIL 0 / BLOCKED 0 / not executed 6

## Cross-version classification

| Classification | Count |
|---|---:|
| SAME_BEHAVIOR | 0 |
| REGRESSION_CANDIDATE | 0 |
| FIXED | 0 |
| SAME_FAILURE | 0 |
| BLOCKED | 0 |
| NOT_COMPARED | 6 |

> REGRESSION_CANDIDATE is not a confirmed regression until failure triage; BLOCKED reflects the missing local Odoo 19 environment (see docs/ENVIRONMENT_STATUS.md).

## Per test case

| TC | Title | Prio | Automation | v17 | v19 | Classification |
|---|---|---|---|---|---|---|
| DATAONE-TC014 | The five OCA modules import and load on the v19 runtime | P0 | AUTOMATED | NOT_RUN | NOT_RUN | NOT_COMPARED |
| DATAONE-TC095 | Gate case: revision -01 created, source cancelled and archived, fields | P1 | AUTOMATED | NOT_RUN | NOT_RUN | NOT_COMPARED |
| DATAONE-TC096 | A second revision flattens the chain; the stat button lists all prior  | P1 | AUTOMATED | NOT_RUN | NOT_RUN | NOT_COMPARED |
| DATAONE-TC097 | The revision button appears only in sent and cancel | P2 | AUTOMATED | NOT_RUN | NOT_RUN | NOT_COMPARED |
| DATAONE-TC098 | The lineage uniqueness constraint and its exact message | P2 | AUTOMATED | NOT_RUN | NOT_RUN | NOT_COMPARED |
| DATAONE-TC338 | Re-import of an unconfirmed order creates a revision, cancels and arch | P0 | AUTOMATED | NOT_RUN | NOT_RUN | NOT_COMPARED |

## Feasibility decisions

implemented 5 · blocked_stub 1 · not_implemented 0 (details: `reports/data/wf003_feasibility.json`)
