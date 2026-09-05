# DATAONE-WF-007 Report — MO Completion, Serial-Number Generation & Labelling

Generated 2026-09-05 04:10 by `scripts/gen_reports.py` from persisted execution results (`data/results.db`) and the workbook-synced registry. Expected results are the workbook's, verbatim.

## Counts

- Test cases: **17**
- Automated (covered by platform tests): **12** of 12 automatable
- Manual-only: **5**
- Currently BLOCKED (either environment): **5**
- Odoo 17: PASS 0 / FAIL 0 / BLOCKED 0 / SKIPPED 0 / not executed 17
- Odoo 19: PASS 5 / FAIL 2 / BLOCKED 5 / not executed 5

## Cross-version classification

| Classification | Count |
|---|---:|
| SAME_BEHAVIOR | 0 |
| REGRESSION_CANDIDATE | 0 |
| FIXED | 0 |
| SAME_FAILURE | 0 |
| BLOCKED | 5 |
| NOT_COMPARED | 12 |

> REGRESSION_CANDIDATE is not a confirmed regression until failure triage; BLOCKED reflects the missing local Odoo 19 environment (see docs/ENVIRONMENT_STATUS.md).

## Per test case

| TC | Title | Prio | Automation | v17 | v19 | Classification |
|---|---|---|---|---|---|---|
| DATAONE-TC033 | lot_producing_id → lot_producing_ids: every MO that had one lot has ex | P0 | AUTOMATED | NOT_RUN | BLOCKED | BLOCKED |
| DATAONE-TC056 | Lot and serial master, including the auto_generated marker | P0 | AUTOMATED | NOT_RUN | BLOCKED | BLOCKED |
| DATAONE-TC106 | GATE Backordered MO: the auto-generated lot is renamed to match the fi | P0 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |
| DATAONE-TC107 | An operator-typed lot number is never renamed | P0 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |
| DATAONE-TC108 | An MO with no reachable sale order is numbered with the bare MO digits | P1 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |
| DATAONE-TC109 | A failed quality check suppresses automatic serial generation | P0 | AUTOMATED | NOT_RUN | FAIL | NOT_COMPARED |
| DATAONE-TC110 | The lot branch and the serial branch both produce a <SO>-<MO> number | P1 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |
| DATAONE-TC111 | v19 SILENT A serial-tracked MO with product_qty > 1 still creates a lo | P0 | AUTOMATED | NOT_RUN | FAIL | NOT_COMPARED |
| DATAONE-TC112 | With no serial sequence on the product, the UserError fallback produce | P1 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |
| DATAONE-TC113 | Mass Produce pre-fills <SO>-<MO>-001 and keeps the picked component lo | P1 | AUTOMATED | NOT_RUN | BLOCKED | BLOCKED |
| DATAONE-TC114 | An MO whose Packaging work orders have zero total duration cannot be m | P0 | AUTOMATED | NOT_RUN | BLOCKED | BLOCKED |
| DATAONE-TC115 | An MO with no Packaging work centre at all is blocked by the same rule | P0 | AUTOMATED | NOT_RUN | BLOCKED | BLOCKED |
| DATAONE-TC116 | Split-serial printing produces N labels numbered -001 … -00N against o | P1 | MANUAL_ONLY | MANUAL | MANUAL | NOT_COMPARED |
| DATAONE-TC117 | A print run of exactly one unit keeps the original lot number, unsuffi | P2 | MANUAL_ONLY | MANUAL | MANUAL | NOT_COMPARED |
| DATAONE-TC118 | The "N of M" counter appears only when Serial Numbers? is ticked | P2 | MANUAL_ONLY | MANUAL | MANUAL | NOT_COMPARED |
| DATAONE-TC119 | The Dymo PDF label carries the product barcode, MO number, production  | P1 | MANUAL_ONLY | MANUAL | MANUAL | NOT_COMPARED |
| DATAONE-TC120 | The ZPL product-label variant emits the same data as raw ZPL text | P2 | MANUAL_ONLY | MANUAL | MANUAL | NOT_COMPARED |

## Failure notes (triage input)

- **DATAONE-TC109** [Odoo 19 → FAIL / ASSERTION] still no producing lot: expected [], got [126816]
- **DATAONE-TC111** [Odoo 19 → FAIL / ASSERTION] state: expected 'done', got 'to_close'
