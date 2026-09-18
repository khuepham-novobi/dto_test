# DATAONE-WF-019 Report — Vendor Payment Import from Workday

Generated 2026-09-18 14:23 by `scripts/gen_reports.py` from persisted execution results (`data/results.db`) and the workbook-synced registry. Expected results are the workbook's, verbatim.

## Counts

- Test cases: **8**
- Automated (covered by platform tests): **8** of 8 automatable
- Manual-only: **0**
- Currently BLOCKED (either environment): **0**
- Odoo 17: PASS 0 / FAIL 0 / BLOCKED 0 / SKIPPED 0 / not executed 8
- Odoo 19: PASS 0 / FAIL 8 / BLOCKED 0 / not executed 0

## Cross-version classification

| Classification | Count |
|---|---:|
| SAME_BEHAVIOR | 0 |
| REGRESSION_CANDIDATE | 0 |
| FIXED | 0 |
| SAME_FAILURE | 0 |
| BLOCKED | 0 |
| NOT_COMPARED | 8 |

> REGRESSION_CANDIDATE is not a confirmed regression until failure triage; BLOCKED reflects the missing local Odoo 19 environment (see docs/ENVIRONMENT_STATUS.md).

## Per test case

| TC | Title | Prio | Automation | v17 | v19 | Classification |
|---|---|---|---|---|---|---|
| DATAONE-TC299 | Re-process visibility and File(s) have been processed already! | P2 | AUTOMATED | NOT_RUN | FAIL | NOT_COMPARED |
| DATAONE-TC323 | GATE: eight-column CSV, five rows; row 5 creates a second payment | P0 | AUTOMATED | NOT_RUN | FAIL | NOT_COMPARED |
| DATAONE-TC324 | The payment is created and posted on the configured company journal | P0 | AUTOMATED | NOT_RUN | FAIL | NOT_COMPARED |
| DATAONE-TC325 | The payment is reconciled against the bill and the residual falls | P0 | AUTOMATED | NOT_RUN | FAIL | NOT_COMPARED |
| DATAONE-TC327 | Two-level error surfacing: an activity on the bill *and* the file Fail | P1 | AUTOMATED | NOT_RUN | FAIL | NOT_COMPARED |
| DATAONE-TC328 | A missing expected column produces a row error; a short row fails the  | P1 | AUTOMATED | NOT_RUN | FAIL | NOT_COMPARED |
| DATAONE-TC329 | A re-uploaded identical remote file is processed again — the bill is p | P0 | AUTOMATED | NOT_RUN | FAIL | NOT_COMPARED |
| DATAONE-TC330 | Row-level rejections: payment method by exact name, missing journal, e | P1 | AUTOMATED | NOT_RUN | FAIL | NOT_COMPARED |

## Failure notes (triage input)

- **DATAONE-TC299** [Odoo 19 → FAIL / ASSERTION] D1 is Done: expected 'done', got 'failed'
- **DATAONE-TC323** [Odoo 19 → FAIL / ASSERTION] state: expected 'posted', got 'paid'
- **DATAONE-TC324** [Odoo 19 → FAIL / ASSERTION] the file reports Done — one good row, no failures: expected 'done', got 'failed'
- **DATAONE-TC325** [Odoo 19 → FAIL / ASSERTION] anchor partial.residual: expected 400.0, got 500.0
- **DATAONE-TC327** [Odoo 19 → FAIL / ASSERTION] posted: expected 'posted', got 'paid'
- **DATAONE-TC328** [Odoo 19 → FAIL / ASSERTION] V4 succeeds — column order is irrelevant: expected 'done', got 'failed'
- **DATAONE-TC329** [Odoo 19 → FAIL / ASSERTION] the file is Done: expected 'done', got 'failed'
- **DATAONE-TC330** [Odoo 19 → FAIL / ASSERTION] one activity on the bill: expected 1, got 2
