# DATAONE-WF-024 Report — RMA: Customer and Vendor Returns

Generated 2026-09-18 15:44 by `scripts/gen_reports.py` from persisted execution results (`data/results.db`) and the workbook-synced registry. Expected results are the workbook's, verbatim.

## Counts

- Test cases: **8**
- Automated (covered by platform tests): **8** of 8 automatable
- Manual-only: **0**
- Currently BLOCKED (either environment): **1**
- Odoo 17: PASS 0 / FAIL 0 / BLOCKED 0 / SKIPPED 0 / not executed 8
- Odoo 19: PASS 2 / FAIL 5 / BLOCKED 1 / not executed 0

## Cross-version classification

| Classification | Count |
|---|---:|
| SAME_BEHAVIOR | 0 |
| REGRESSION_CANDIDATE | 0 |
| FIXED | 0 |
| SAME_FAILURE | 0 |
| BLOCKED | 1 |
| NOT_COMPARED | 7 |

> REGRESSION_CANDIDATE is not a confirmed regression until failure triage; BLOCKED reflects the missing local Odoo 19 environment (see docs/ENVIRONMENT_STATUS.md).

## Per test case

| TC | Title | Prio | Automation | v17 | v19 | Classification |
|---|---|---|---|---|---|---|
| DATAONE-TC044 | RMA sequence YYYY-nnn continues without collision | P0 | AUTOMATED | NOT_RUN | FAIL | NOT_COMPARED |
| DATAONE-TC184 | A return created through the wizard is numbered YYYY-nnn | P1 | AUTOMATED | NOT_RUN | FAIL | NOT_COMPARED |
| DATAONE-TC185 | The return picking's note is the company vendor-refund narration | P1 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |
| DATAONE-TC186 | Reason for Return and Return Notes are required on an RMA picking and  | P1 | AUTOMATED | NOT_RUN | BLOCKED | BLOCKED |
| DATAONE-TC187 | do_print_picking() returns the RMA report for an RMA and the standard  | P1 | AUTOMATED | NOT_RUN | FAIL | NOT_COMPARED |
| DATAONE-TC188 | The three RMA menus exist and the all-RMAs queue lists every numbered  | P2 | AUTOMATED | NOT_RUN | FAIL | NOT_COMPARED |
| DATAONE-TC189 | Return and Replenish adds exactly one zero-priced line per returned li | P0 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |
| DATAONE-TC190 | On a rebuilt database the customer and vendor RMA queues return the ri | P0 | AUTOMATED | NOT_RUN | FAIL | NOT_COMPARED |

## Failure notes (triage input)

- **DATAONE-TC044** [Odoo 19 → FAIL / ASSERTION] rma_number values issued more than once: expected [], got ['2025-031', '2025-108', '2026-123', '2026-147', '2026-162', '2026-167', '2026-172', '2026-179', '2026-181', '2026-212', '2026-214']
- **DATAONE-TC184** [Odoo 19 → FAIL / ASSERTION] the prefilled quantity per product is the returnable quantity: expected {38771: 4.0, 38772: 7.0}, got {38771: 0.0, 38772: 0.0}
- **DATAONE-TC187** [Odoo 19 → FAIL / ASSERTION] the RMA report renders (EXPECTED TO FAIL ON v19 — the forked template references move_ids_without_package, move_line_ids_without_package, package_level_ids, product_packaging_id/_qty and stock.quant.package, all removed in v19): expected 'rendered', got 'HTTPE
- **DATAONE-TC188** [Odoo 19 → FAIL / ASSERTION] the five workbook view modes are reachable from the all-RMAs action: expected {'unreachable': {}, 'declared_but_not_a_view_type': []}, got {'unreachable': {'list': "not declared in view_mode='tree,kanban,form,calendar,activity'"}, 'declared_but_not_a_view_type
- **DATAONE-TC190** [Odoo 19 → FAIL / ASSERTION] both directional domains reference the locations by xml_id, not by a literal integer: expected {}, got {'stock_picking_auto_create_lot.action_picking_tree_rma_customer': "location_id is pinned to the integer literal 5; it must resolve from ref('stock.stock_loc
