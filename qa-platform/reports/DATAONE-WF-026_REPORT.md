# DATAONE-WF-026 Report — Historical Data Migration Import

Generated 2026-09-18 17:29 by `scripts/gen_reports.py` from persisted execution results (`data/results.db`) and the workbook-synced registry. Expected results are the workbook's, verbatim.

## Counts

- Test cases: **23**
- Automated (covered by platform tests): **23** of 23 automatable
- Manual-only: **1**
- Currently BLOCKED (either environment): **1**
- Odoo 17: PASS 0 / FAIL 0 / BLOCKED 0 / SKIPPED 0 / not executed 23
- Odoo 19: PASS 18 / FAIL 4 / BLOCKED 1 / not executed 0

## Cross-version classification

| Classification | Count |
|---|---:|
| SAME_BEHAVIOR | 0 |
| REGRESSION_CANDIDATE | 0 |
| FIXED | 0 |
| SAME_FAILURE | 0 |
| BLOCKED | 1 |
| NOT_COMPARED | 22 |

> REGRESSION_CANDIDATE is not a confirmed regression until failure triage; BLOCKED reflects the missing local Odoo 19 environment (see docs/ENVIRONMENT_STATUS.md).

## Per test case

| TC | Title | Prio | Automation | v17 | v19 | Classification |
|---|---|---|---|---|---|---|
| DATAONE-TC396 | Only an Inventory Manager can reach the Import Data wizard | P0 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |
| DATAONE-TC397 | The four import types map to the right models and auto-fill key_fields | P1 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |
| DATAONE-TC398 | A synchronous import of all four types produces the expected states an | P0 | AUTOMATED | NOT_RUN | FAIL | NOT_COMPARED |
| DATAONE-TC399 | GATE. Import MO → PO → SO, then invalidate and re-read: nothing change | P0 | AUTOMATED | NOT_RUN | FAIL | NOT_COMPARED |
| DATAONE-TC400 | An imported sales order generates zero deliveries and zero stock moves | P0 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |
| DATAONE-TC401 | An imported purchase order derives Effective Date and Receipt Number f | P1 | AUTOMATED | NOT_RUN | FAIL | NOT_COMPARED |
| DATAONE-TC402 | An imported manufacturing order reports the imported produced quantity | P1 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |
| DATAONE-TC403 | An unknown header column raises exactly Can not find the field "<col>" | P1 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |
| DATAONE-TC404 | An unresolvable relation value raises exactly Can not find a field <na | P1 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |
| DATAONE-TC405 | A partial x2many match raises exactly Only found N records (Expected:  | P2 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |
| DATAONE-TC406 | A missing key column raises exactly Not found key field: <field> | P1 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |
| DATAONE-TC407 | A bad relation column raises exactly Cannot find the field "<f>" or it | P2 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |
| DATAONE-TC408 | A queued import creates one job per batch on the expected channel and  | P1 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |
| DATAONE-TC409 | A queued BOM import falls back to the root channel because import_mrp_ | P2 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |
| DATAONE-TC410 | An MO CSV without a qty_produced column raises a bare KeyError | P1 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |
| DATAONE-TC451 | The jobrunner starts and logs queue job runner ready for db dataone | P0 | AUTOMATED | NOT_RUN | BLOCKED | BLOCKED |
| DATAONE-TC452 | A job progresses Pending → Enqueued → Started → Done | P0 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |
| DATAONE-TC453 | A failed job notifies every Job Queue Manager and records the tracebac | P1 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |
| DATAONE-TC454 | The Requeue Jobs wizard returns a failed job to Pending and it complet | P1 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |
| DATAONE-TC455 | The Set to Done and Cancel wizards close jobs without executing them | P2 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |
| DATAONE-TC456 | The garbage collector returns jobs Enqueued for more than 5 minutes to | P1 | AUTOMATED | NOT_RUN | FAIL | NOT_COMPARED |
| DATAONE-TC457 | The autovacuum deletes Done jobs past the channel's Removal Interval | P2 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |
| DATAONE-TC458 | Creating a queue.job directly is refused with "Queue jobs must be crea | P2 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |

## Failure notes (triage input)

- **DATAONE-TC398** [Odoo 19 → FAIL / ASSERTION] nothing downstream was created: expected {'stock.picking': 0, 'stock.move': 0, 'account.move': 0, 'procurement.group': 0, 'stock.move.line': 0}, got {'stock.picking': 4, 'stock.move': 0, 'account.move': 0, 'procurement.group': 0, 'stock.move.line': 0}
- **DATAONE-TC399** [Odoo 19 → FAIL / ASSERTION] PO receipt_number: expected 'RCPT-A, RCPT-B', got 'RCPT-B, RCPT-A'
- **DATAONE-TC401** [Odoo 19 → FAIL / ASSERTION] receipt_number: expected 'RCPT-A, RCPT-B', got 'RCPT-B, RCPT-A'
- **DATAONE-TC456** [Odoo 19 → FAIL / ASSERTION] a stuck-job collector is configured: expected True, got "crons on queue.job: ['AutoVacuum Job Queue'] — none of them requeues stuck jobs, and queue_job 19.0 defines no requeue_stuck_jobs method at all"
