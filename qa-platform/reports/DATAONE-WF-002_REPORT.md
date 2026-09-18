# DATAONE-WF-002 Report — Quotation → sales order confirmation

Generated 2026-09-18 16:45 by `scripts/gen_reports.py` from persisted execution results (`data/results.db`) and the workbook-synced registry. Expected results are the workbook's, verbatim.

## Counts

- Test cases: **37**
- Automated (covered by platform tests): **37** of 37 automatable
- Manual-only: **5**
- Currently BLOCKED (either environment): **1**
- Odoo 17: PASS 29 / FAIL 6 / BLOCKED 1 / SKIPPED 1 / not executed 0
- Odoo 19: PASS 0 / FAIL 0 / BLOCKED 0 / not executed 0

## Cross-version classification

| Classification | Count |
|---|---:|
| SAME_BEHAVIOR | 0 |
| REGRESSION_CANDIDATE | 0 |
| FIXED | 0 |
| SAME_FAILURE | 0 |
| BLOCKED | 1 |
| NOT_COMPARED | 36 |

> REGRESSION_CANDIDATE is not a confirmed regression until failure triage; BLOCKED reflects the missing local Odoo 19 environment (see docs/ENVIRONMENT_STATUS.md).

## Per test case

| TC | Title | Prio | Automation | v17 | v19 | Classification |
|---|---|---|---|---|---|---|
| DATAONE-TC017 | Every server-action and automated-action code body compiles and contai | P1 | AUTOMATED | PASS | SKIPPED | NOT_COMPARED |
| DATAONE-TC053 | Sales order type distribution and the analytic discipline fields | P1 | AUTOMATED | FAIL | SKIPPED | NOT_COMPARED |
| DATAONE-TC057 | Mail templates, server actions and automated actions | P2 | AUTOMATED | PASS | SKIPPED | NOT_COMPARED |
| DATAONE-TC061 | Order Type is mandatory and has no default | P1 | AUTOMATED | FAIL | SKIPPED | NOT_COMPARED |
| DATAONE-TC062 | Order Type is tracked, badged in the list, and survives duplication | P3 | AUTOMATED | FAIL | SKIPPED | NOT_COMPARED |
| DATAONE-TC063 | Confirmation is blocked when a product line has no Promised Ship Date | P1 | AUTOMATED | PASS | SKIPPED | NOT_COMPARED |
| DATAONE-TC064 | Section and note lines do not block confirmation | P2 | AUTOMATED | PASS | SKIPPED | NOT_COMPARED |
| DATAONE-TC065 | Delivery Date is derived from the LATEST promised line date | P1 | AUTOMATED | PASS | SKIPPED | NOT_COMPARED |
| DATAONE-TC066 | A manually typed Delivery Date persists | P2 | AUTOMATED | PASS | SKIPPED | NOT_COMPARED |
| DATAONE-TC067 | A later line-date edit silently overwrites the manual Delivery Date | P2 | AUTOMATED | PASS | SKIPPED | NOT_COMPARED |
| DATAONE-TC068 | A negative tariff is rejected on write with the exact message | P2 | AUTOMATED | FAIL | SKIPPED | NOT_COMPARED |
| DATAONE-TC069 | A negative tariff supplied to create() is NOT blocked (defect regressi | P2 | AUTOMATED | PASS | SKIPPED | NOT_COMPARED |
| DATAONE-TC070 | Tariff Amount never affects the order total | P2 | AUTOMATED | PASS | SKIPPED | NOT_COMPARED |
| DATAONE-TC071 | Per-line delivery performance populates after the outgoing move is don | P2 | AUTOMATED | PASS | SKIPPED | NOT_COMPARED |
| DATAONE-TC072 | "Late" is unreachable at line level, and the null-commitment crash | P3 | AUTOMATED | FAIL | SKIPPED | NOT_COMPARED |
| DATAONE-TC073 | Gate 1: no requester email blocks confirmation and creates nothing | P1 | AUTOMATED | PASS | SKIPPED | NOT_COMPARED |
| DATAONE-TC074 | Gate 2: a missing analytic account blocks confirmation and creates not | P1 | AUTOMATED | PASS | SKIPPED | NOT_COMPARED |
| DATAONE-TC075 | Gate 3: the Promised Ship Date gate creates nothing downstream | P1 | AUTOMATED | PASS | SKIPPED | NOT_COMPARED |
| DATAONE-TC076 | Which gate fires first: the MRO order of the three overrides | P1 | AUTOMATED | PASS | SKIPPED | NOT_COMPARED |
| DATAONE-TC077 | Multi-record confirm: one order without a requester email blocks all | P1 | AUTOMATED | PASS | SKIPPED | NOT_COMPARED |
| DATAONE-TC078 | project: an account outside the Project plan raises "Project is requir | P1 | AUTOMATED | PASS | SKIPPED | NOT_COMPARED |
| DATAONE-TC079 | buy: the Customer Contract plan is required | P1 | AUTOMATED | PASS | SKIPPED | NOT_COMPARED |
| DATAONE-TC080 | inventory: any analytic distribution is rejected | P1 | AUTOMATED | PASS | SKIPPED | NOT_COMPARED |
| DATAONE-TC081 | cost_center: any analytic distribution is rejected | P1 | AUTOMATED | PASS | SKIPPED | NOT_COMPARED |
| DATAONE-TC082 | analytic_account_id is set from the LAST line's first account | P2 | AUTOMATED | PASS | SKIPPED | NOT_COMPARED |
| DATAONE-TC083 | Confirmation email recipients routed by order type | P1 | AUTOMATED | PASS | SKIPPED | NOT_COMPARED |
| DATAONE-TC084 | An IRM memo appends the Ciena IRM desk to the recipient list | P2 | AUTOMATED | PASS | SKIPPED | NOT_COMPARED |
| DATAONE-TC085 | An empty memo raises TypeError and aborts the confirmation | P1 | AUTOMATED | FAIL | SKIPPED | NOT_COMPARED |
| DATAONE-TC086 | Confirmation email body: total, ship date, order type, Reference # and | P2 | AUTOMATED | PASS | SKIPPED | NOT_COMPARED |
| DATAONE-TC087 | Sale Order PDF: requester block, memo, "Product" header and product na | P2 | AUTOMATED | SKIPPED | SKIPPED | NOT_COMPARED |
| DATAONE-TC089 | Order type and tariff search filters and group-by | P3 | AUTOMATED | PASS | SKIPPED | NOT_COMPARED |
| DATAONE-TC090 | The company NTT price formula is applied to the line | P3 | AUTOMATED | PASS | SKIPPED | NOT_COMPARED |
| DATAONE-TC091 | A customer formula overrides the company formula | P3 | AUTOMATED | PASS | SKIPPED | NOT_COMPARED |
| DATAONE-TC092 | An invalid formula silently falls back to the unit price | P3 | AUTOMATED | PASS | SKIPPED | NOT_COMPARED |
| DATAONE-TC093 | A manual NTT value is overwritten; a formula change is not retroactive | P3 | AUTOMATED | PASS | SKIPPED | NOT_COMPARED |
| DATAONE-TC094 | NTT Unit Price never reaches the total, the invoice, tax or margin | P2 | AUTOMATED | PASS | SKIPPED | NOT_COMPARED |
| DATAONE-TC350 | GATE (Phase 5): the full Workday round trip, run twice | P0 | AUTOMATED | BLOCKED | SKIPPED | BLOCKED |

## Failure notes (triage input)

- **DATAONE-TC053** [Odoo 19 → ERROR / AUTOMATION_ERROR] OdooRPCError: web session authentication failed: Access Denied
- **DATAONE-TC053** [Odoo 17 → FAIL / ASSERTION] anchor orders_without_type: expected 0, got 24
- **DATAONE-TC061** [Odoo 19 → ERROR / AUTOMATION_ERROR] OdooRPCError: sale.order.create failed: - delete: another model requires the record being deleted, you can archive it instead
- **DATAONE-TC061** [Odoo 17 → FAIL / ASSERTION] the create without order_type was refused: expected True, got 'no error raised'
- **DATAONE-TC062** [Odoo 19 → ERROR / AUTOMATION_ERROR] OdooRPCError: product.template.create failed: - delete: another model requires the record being deleted, you can archive it instead
- **DATAONE-TC062** [Odoo 17 → FAIL / ASSERTION] the order_type change is tracked: expected True, got '[]'
- **DATAONE-TC068** [Odoo 19 → ERROR / AUTOMATION_ERROR] OdooRPCError: product.template.create failed: - delete: another model requires the record being deleted, you can archive it instead
- **DATAONE-TC068** [Odoo 17 → FAIL / ASSERTION] the tariff change is tracked in the chatter: expected True, got '[]'
- **DATAONE-TC072** [Odoo 19 → FAIL / ASSERTION] line delivery_status for a late shipment: expected 'early', got 'late'
- **DATAONE-TC072** [Odoo 17 → FAIL / ASSERTION] line delivery_status for a late shipment: expected 'early', got 'late'
- **DATAONE-TC085** [Odoo 19 → FAIL / ASSERTION] confirmation aborted: expected True, got 'no error raised'
- **DATAONE-TC085** [Odoo 17 → FAIL / ASSERTION] the message names a bool that is not iterable: expected True, got 'sale.order.action_confirm failed: "def get_analytic_accounts(analytic_distribution_lst):\\n    unique_ids = set()\\n    for data in analytic_distribution_lst:\\n        for ids_str in data.keys
