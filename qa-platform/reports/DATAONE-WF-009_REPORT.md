# DATAONE-WF-009 Report — Component Shortage Auto-Substitution

Generated 2026-09-05 04:10 by `scripts/gen_reports.py` from persisted execution results (`data/results.db`) and the workbook-synced registry. Expected results are the workbook's, verbatim.

## Counts

- Test cases: **8**
- Automated (covered by platform tests): **8** of 8 automatable
- Manual-only: **0**
- Currently BLOCKED (either environment): **0**
- Odoo 17: PASS 0 / FAIL 0 / BLOCKED 0 / SKIPPED 0 / not executed 8
- Odoo 19: PASS 6 / FAIL 2 / BLOCKED 0 / not executed 0

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
| DATAONE-TC136 | Replacement groups are reciprocal, order-independent, and split cleanl | P1 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |
| DATAONE-TC137 | A product cannot replace itself, and cannot belong to two groups | P2 | AUTOMATED | NOT_RUN | FAIL | NOT_COMPARED |
| DATAONE-TC138 | A shortage substitutes the first candidate that alone covers the requi | P0 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |
| DATAONE-TC139 | A component with enough stock is never substituted | P1 | AUTOMATED | NOT_RUN | FAIL | NOT_COMPARED |
| DATAONE-TC140 | When no single replacement covers the shortfall, nothing is substitute | P0 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |
| DATAONE-TC141 | A replacement in a different UoM category is skipped | P1 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |
| DATAONE-TC142 | Revert restores the original component, and the move is eligible again | P1 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |
| DATAONE-TC143 | GATE (WF-009) On a 2-step warehouse the chained pick move is rewritten | P0 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |

## Failure notes (triage input)

- **DATAONE-TC137** [Odoo 19 → FAIL / ASSERTION] ValidationError says 'A product cannot be a replacement of itself.': expected True, got 'no error raised'
- **DATAONE-TC139** [Odoo 19 → FAIL / ASSERTION] still on A: expected 38463, got 38464
