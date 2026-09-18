# DATAONE-WF-011 Report — Delivery, Boxing, Blind Ship & Packing Documents

Generated 2026-09-18 17:41 by `scripts/gen_reports.py` from persisted execution results (`data/results.db`) and the workbook-synced registry. Expected results are the workbook's, verbatim.

## Counts

- Test cases: **19**
- Automated (covered by platform tests): **19** of 19 automatable
- Manual-only: **1**
- Currently BLOCKED (either environment): **3**
- Odoo 17: PASS 0 / FAIL 0 / BLOCKED 0 / SKIPPED 0 / not executed 19
- Odoo 19: PASS 7 / FAIL 9 / BLOCKED 3 / not executed 0

## Cross-version classification

| Classification | Count |
|---|---:|
| SAME_BEHAVIOR | 0 |
| REGRESSION_CANDIDATE | 0 |
| FIXED | 0 |
| SAME_FAILURE | 0 |
| BLOCKED | 3 |
| NOT_COMPARED | 16 |

> REGRESSION_CANDIDATE is not a confirmed regression until failure triage; BLOCKED reflects the missing local Odoo 19 environment (see docs/ENVIRONMENT_STATUS.md).

## Per test case

| TC | Title | Prio | Automation | v17 | v19 | Classification |
|---|---|---|---|---|---|---|
| DATAONE-TC011 | Every custom ir.actions.report resolves its template and paperformat,  | P1 | AUTOMATED | NOT_RUN | FAIL | NOT_COMPARED |
| DATAONE-TC054 | RMA numbers and return metadata on pickings | P1 | AUTOMATED | NOT_RUN | BLOCKED | BLOCKED |
| DATAONE-TC151 | Create Boxes generates N named boxes at the default weight and resets  | P1 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |
| DATAONE-TC152 | A second Create Boxes press destroys the existing manifest without war | P1 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |
| DATAONE-TC153 | Create Boxes with a zero count raises the exact error | P2 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |
| DATAONE-TC154 | Box weight zero is rejected; a negative weight is accepted (live v17 d | P2 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |
| DATAONE-TC155 | The Boxes section is absent on receipts and on internal transfers | P2 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |
| DATAONE-TC156 | A shipping label can be created by hand on the delivery and carries a  | P2 | AUTOMATED | NOT_RUN | BLOCKED | BLOCKED |
| DATAONE-TC157 | Transfer weight and shipping weight are hand-entered and survive line  | P2 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |
| DATAONE-TC158 | A user outside *Validate Delivery Orders* cannot validate a delivery | P0 | AUTOMATED | NOT_RUN | FAIL | NOT_COMPARED |
| DATAONE-TC159 | A member of *Validate Delivery Orders* validates the same delivery suc | P0 | AUTOMATED | NOT_RUN | FAIL | NOT_COMPARED |
| DATAONE-TC160 | A member of the inverted *Cannot edit transfers* group cannot write an | P1 | AUTOMATED | NOT_RUN | FAIL | NOT_COMPARED |
| DATAONE-TC161 | A partial delivery always creates a backorder; "No Backorder" is not o | P1 | AUTOMATED | NOT_RUN | FAIL | NOT_COMPARED |
| DATAONE-TC162 | The blind-ship flag is set on the sales order and propagates read-only | P1 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |
| DATAONE-TC163 | One Delivery Slip click prints every non-cancelled outgoing picking of | P0 | AUTOMATED | NOT_RUN | FAIL | NOT_COMPARED |
| DATAONE-TC164 | The Blind Packing Slip carries no header, no footer, no customer block | P0 | AUTOMATED | NOT_RUN | FAIL | NOT_COMPARED |
| DATAONE-TC165 | The packing slip carries the shipping/tracking/pieces/weight table and | P1 | AUTOMATED | NOT_RUN | BLOCKED | BLOCKED |
| DATAONE-TC166 | The delivery's Journal Entries stat button opens its valuation entries | P1 | AUTOMATED | NOT_RUN | FAIL | NOT_COMPARED |
| DATAONE-TC168 | Recomputing account_move_ids over several pickings does not raise a si | P1 | AUTOMATED | NOT_RUN | FAIL | NOT_COMPARED |

## Failure notes (triage input)

- **DATAONE-TC011** [Odoo 19 → FAIL / ASSERTION] every custom report's QWeb template resolves: expected [], got ['printnode_base.action_report_package_slip_zpl -> printnode_base.report_package_slip_zpl']
- **DATAONE-TC158** [Odoo 19 → FAIL / ASSERTION] the delivery is assigned, fully reserved, and its operation type is exactly stock.picking_type_out: expected {'state': 'assigned', 'picking_type_id': 2, 'reserved': [10.0]}, got {'state': 'confirmed', 'picking_type_id': 2, 'reserved': [0.0]}
- **DATAONE-TC159** [Odoo 19 → FAIL / ASSERTION] the delivery is assigned on stock.picking_type_out, fully reserved, and its order is the buy type F040 excludes (dto_sale_stock/models/stock_picking.py:16-18): expected {'state': 'assigned', 'picking_type_id': 2, 'reserved': [10.0], 'order_type': 'buy'}, got {
- **DATAONE-TC160** [Odoo 19 → FAIL / ASSERTION] both fixtures are assigned — one outgoing delivery and one incoming receipt: expected {'delivery': 'assigned', 'receipt': 'assigned'}, got {'delivery': 'confirmed', 'receipt': 'assigned'}
- **DATAONE-TC161** [Odoo 19 → FAIL / ASSERTION] the delivery is assigned with 10 units reserved: expected {'state': 'assigned', 'reserved': [10.0]}, got {'state': 'confirmed', 'reserved': [0.0]}
- **DATAONE-TC163** [Odoo 19 → FAIL / ASSERTION] PACKING SLIP occurs once per non-cancelled outgoing picking of the order: expected 2, got 0
- **DATAONE-TC164** [Odoo 19 → FAIL / ASSERTION] the company header is suppressed at source — the blind template sets report_header_style and the layout's header div renders it (report_ship_blind.xml:6; v17 web/views/report_templates.xml:492, v19 keeps the hook on external_layout_bold ONLY at :439) — and the
- **DATAONE-TC166** [Odoo 19 → FAIL / ASSERTION] the combined stock.picking form carries the fa-book Journal Entries stat button, its invisible modifier and the field that modifier reads (dto_stock/views/stock_picking_views.xml:8-18): expected {'present': True, 'type': 'object', 'class': 'oe_stat_button', 'i
- **DATAONE-TC168** [Odoo 19 → FAIL / ASSERTION] reading account_move_ids over several pickings raises nothing: expected {'raised': False, 'expected_singleton_error': False}, got {'raised': True, 'expected_singleton_error': True}
