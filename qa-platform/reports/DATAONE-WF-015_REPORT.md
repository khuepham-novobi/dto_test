# DATAONE-WF-015 Report — Per-Line Receipt, Quality Check & Packing Slip

Generated 2026-09-18 16:03 by `scripts/gen_reports.py` from persisted execution results (`data/results.db`) and the workbook-synced registry. Expected results are the workbook's, verbatim.

## Counts

- Test cases: **21**
- Automated (covered by platform tests): **20** of 20 automatable
- Manual-only: **2**
- Currently BLOCKED (either environment): **2**
- Odoo 17: PASS 0 / FAIL 0 / BLOCKED 0 / SKIPPED 0 / not executed 21
- Odoo 19: PASS 3 / FAIL 14 / BLOCKED 2 / not executed 1

## Cross-version classification

| Classification | Count |
|---|---:|
| SAME_BEHAVIOR | 0 |
| REGRESSION_CANDIDATE | 0 |
| FIXED | 0 |
| SAME_FAILURE | 0 |
| BLOCKED | 2 |
| NOT_COMPARED | 19 |

> REGRESSION_CANDIDATE is not a confirmed regression until failure triage; BLOCKED reflects the missing local Odoo 19 environment (see docs/ENVIRONMENT_STATUS.md).

## Per test case

| TC | Title | Prio | Automation | v17 | v19 | Classification |
|---|---|---|---|---|---|---|
| DATAONE-TC015 | The two commercial modules have Odoo 19 builds and install | P0 | MANUAL_ONLY | MANUAL | MANUAL | NOT_COMPARED |
| DATAONE-TC032 | purchase.order records in state 'done' land correctly on locked | P1 | AUTOMATED | NOT_RUN | BLOCKED | BLOCKED |
| DATAONE-TC047 | Attachment counts and bytes by model | P1 | AUTOMATED | NOT_RUN | BLOCKED | BLOCKED |
| DATAONE-TC201 | A confirmed three-line PO produces three separate receipts, one per li | P0 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |
| DATAONE-TC202 | Re-promising a line relocates its move to a receipt whose deadline mat | P0 | AUTOMATED | NOT_RUN | ERROR | NOT_COMPARED |
| DATAONE-TC203 | Re-promising to a date no receipt matches creates a new receipt | P1 | AUTOMATED | NOT_RUN | ERROR | NOT_COMPARED |
| DATAONE-TC204 | A receipt left with no moves is cancelled, not deleted | P1 | AUTOMATED | NOT_RUN | ERROR | NOT_COMPARED |
| DATAONE-TC205 | Capture the v17 (picking, deadline, move) regroup baseline and replay  | P0 | AUTOMATED | NOT_RUN | ERROR | NOT_COMPARED |
| DATAONE-TC206 | The Expected Arrival date of a fully received line cannot be changed | P1 | AUTOMATED | NOT_RUN | FAIL | NOT_COMPARED |
| DATAONE-TC207 | A PDF and a whitelisted image upload as the packing slip and reach the | P2 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |
| DATAONE-TC208 | A non-PDF, non-image upload is refused with the exact error | P2 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |
| DATAONE-TC209 | The merged packing-slip print downloads one combined PDF when PrintNod | P2 | AUTOMATED | NOT_RUN | ERROR | NOT_COMPARED |
| DATAONE-TC210 | With PrintNode enabled for company, user and group, the merged PDF is  | P2 | AUTOMATED | NOT_RUN | ERROR | NOT_COMPARED |
| DATAONE-TC211 | Printing with nothing attached returns the exact "no attachments" mess | P3 | AUTOMATED | NOT_RUN | ERROR | NOT_COMPARED |
| DATAONE-TC212 | The Dymo receipt label prints exactly one label per stock.move.line | P1 | AUTOMATED | NOT_RUN | FAIL | NOT_COMPARED |
| DATAONE-TC213 | The ZPL receipt label produces the same one-per-move-line output as ra | P1 | AUTOMATED | NOT_RUN | FAIL | NOT_COMPARED |
| DATAONE-TC214 | A failed incoming quality check records one of the 19 Reason-for-Retur | P1 | AUTOMATED | NOT_RUN | ERROR | NOT_COMPARED |
| DATAONE-TC215 | Validating a receipt auto-creates lot names for auto-lot products | P1 | AUTOMATED | NOT_RUN | FAIL | NOT_COMPARED |
| DATAONE-TC216 | A tracked product without auto_create_lot still requires a manual lot  | P2 | AUTOMATED | NOT_RUN | ERROR | NOT_COMPARED |
| DATAONE-TC219 | Carrier and tracking reference are editable on a receipt and both chan | P2 | AUTOMATED | NOT_RUN | SKIPPED | NOT_COMPARED |
| DATAONE-TC220 | The purchase order's Journal Entries stat button unions valuation and  | P1 | AUTOMATED | NOT_RUN | FAIL | NOT_COMPARED |

## Failure notes (triage input)

- **DATAONE-TC202** [Odoo 19 → ERROR / AUTOMATION_ERROR] OdooRPCError: purchase.order.line.write failed: 'purchase.order.line' object has no attribute 'product_uom'
- **DATAONE-TC203** [Odoo 19 → ERROR / AUTOMATION_ERROR] OdooRPCError: purchase.order.line.write failed: 'purchase.order.line' object has no attribute 'product_uom'
- **DATAONE-TC204** [Odoo 19 → ERROR / AUTOMATION_ERROR] OdooRPCError: purchase.order.line.write failed: 'purchase.order.line' object has no attribute 'product_uom'
- **DATAONE-TC205** [Odoo 19 → ERROR / AUTOMATION_ERROR] OdooRPCError: purchase.order.line.write failed: 'purchase.order.line' object has no attribute 'product_uom'
- **DATAONE-TC206** [Odoo 19 → FAIL / ASSERTION] the server message, verbatim: expected 'Cannot update the Expected Arrival date because Product WF015-28749ADE TD-P-04 is fully received', got "'purchase.order.line' object has no attribute 'product_uom'"
- **DATAONE-TC209** [Odoo 19 → ERROR / AUTOMATION_ERROR] OdooRPCError: stock.picking.action_print_attached_packing_slip failed: unhashable type: 'list'
- **DATAONE-TC210** [Odoo 19 → ERROR / AUTOMATION_ERROR] OdooRPCError: stock.picking.action_print_attached_packing_slip failed: unhashable type: 'list'
- **DATAONE-TC211** [Odoo 19 → ERROR / AUTOMATION_ERROR] OdooRPCError: stock.picking.action_print_attached_packing_slip failed: unhashable type: 'list'
- **DATAONE-TC212** [Odoo 19 → FAIL / ASSERTION] the Dymo report rendered over /report/html: expected True, got 'HTTPError: HTTP Error 500: INTERNAL SERVER ERROR'
- **DATAONE-TC213** [Odoo 19 → FAIL / ASSERTION] the Dymo report rendered for the parity check: expected True, got 'HTTPError: HTTP Error 500: INTERNAL SERVER ERROR'
- **DATAONE-TC214** [Odoo 19 → ERROR / AUTOMATION_ERROR] OdooRPCError: quality.check.action_open_quality_check_wizard failed: Expected singleton: quality.check(2517, 2518)
- **DATAONE-TC215** [Odoo 19 → FAIL / ASSERTION] button_validate completed without raising and returned no action of any kind: expected {'raised': False, 'result': True}, got {'raised': True, 'result': None}
- **DATAONE-TC216** [Odoo 19 → ERROR / AUTOMATION_ERROR] OdooRPCError: stock.picking.create failed: The operation cannot be completed: Reference must be unique per company!
- **DATAONE-TC220** [Odoo 19 → FAIL / ASSERTION] the Journal Entries button declares NO counter field at all — only a static label in a div.o_stat_info (views/purchase_order_views.xml:22-24) — so the workbook's counter is the union's own length: expected {'journal_button_field_nodes': [], 'journal_button_sta
