# DATAONE-WF-021 Report — Cycle Counting and Inventory Adjustment

Generated 2026-09-18 15:44 by `scripts/gen_reports.py` from persisted execution results (`data/results.db`) and the workbook-synced registry. Expected results are the workbook's, verbatim.

## Counts

- Test cases: **13**
- Automated (covered by platform tests): **13** of 13 automatable
- Manual-only: **0**
- Currently BLOCKED (either environment): **2**
- Odoo 17: PASS 2 / FAIL 0 / BLOCKED 0 / SKIPPED 0 / not executed 11
- Odoo 19: PASS 1 / FAIL 10 / BLOCKED 2 / not executed 0

## Cross-version classification

| Classification | Count |
|---|---:|
| SAME_BEHAVIOR | 0 |
| REGRESSION_CANDIDATE | 2 |
| FIXED | 0 |
| SAME_FAILURE | 0 |
| BLOCKED | 2 |
| NOT_COMPARED | 9 |

> REGRESSION_CANDIDATE is not a confirmed regression until failure triage; BLOCKED reflects the missing local Odoo 19 environment (see docs/ENVIRONMENT_STATUS.md).

## Per test case

| TC | Title | Prio | Automation | v17 | v19 | Classification |
|---|---|---|---|---|---|---|
| DATAONE-TC025 | stock.valuation.layer disappearance: inventory value is preserved | P0 | AUTOMATED | PASS | FAIL | REGRESSION_CANDIDATE |
| DATAONE-TC034 | stock.location valuation-account collapse: two v17 columns folded into | P0 | AUTOMATED | PASS | FAIL | REGRESSION_CANDIDATE |
| DATAONE-TC055 | Cycle-count level assignments and quant scheduling | P1 | AUTOMATED | NOT_RUN | BLOCKED | BLOCKED |
| DATAONE-TC169 | The five shipped levels produce the five documented intervals from a f | P1 | AUTOMATED | NOT_RUN | ERROR | NOT_COMPARED |
| DATAONE-TC170 | Setting the category to 'Finished Goods' on the form auto-assigns Leve | P1 | AUTOMATED | NOT_RUN | ERROR | NOT_COMPARED |
| DATAONE-TC171 | A product created by import or RPC also receives Level D through creat | P1 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |
| DATAONE-TC172 | A storable product cannot be saved without a cycle-count level in the  | P1 | AUTOMATED | NOT_RUN | ERROR | NOT_COMPARED |
| DATAONE-TC173 | Level B with Last Count Date 2026-08-20 displays Scheduled Count Date  | P1 | AUTOMATED | NOT_RUN | ERROR | NOT_COMPARED |
| DATAONE-TC174 | Applying a count stamps quant and product and pushes inventory_date to | P0 | AUTOMATED | NOT_RUN | FAIL | NOT_COMPARED |
| DATAONE-TC175 | Changing a product's level re-schedules every one of its quants in the | P1 | AUTOMATED | NOT_RUN | FAIL | NOT_COMPARED |
| DATAONE-TC176 | Cycle-count columns, search fields and group-bys are available on prod | P2 | AUTOMATED | NOT_RUN | BLOCKED | BLOCKED |
| DATAONE-TC177 | v19 detector: the required-level rule must still be enforced after typ | P0 | AUTOMATED | NOT_RUN | FAIL | NOT_COMPARED |
| DATAONE-TC251 | Inventory adjustment through a tagged virtual location | P0 | AUTOMATED | NOT_RUN | ERROR | NOT_COMPARED |

## Failure notes (triage input)

- **DATAONE-TC025** [Odoo 19 → FAIL / ASSERTION] No differences vs v17 baseline: expected [], got ['internal_quant_products: baseline=39 current=947', 'internal_quant_quantity: baseline=1795.0 current=19149154.11', 'svl_model_present: baseline=None current=False', 'svl_products: baseline=17 current=None', 's
- **DATAONE-TC034** [Odoo 19 → FAIL / ASSERTION] No differences vs v17 baseline: expected [], got ["columns_present: baseline='valuation_in_account_id,valuation_out_account_id' current='valuation_account_id'", 'locations: baseline=37 current=343', 'populated/valuation_account_id: baseline=None current=0', 'p
- **DATAONE-TC169** [Odoo 19 → ERROR / AUTOMATION_ERROR] OdooRPCError: product.product.onchange failed: Contact your administrator to request access if necessary.
- **DATAONE-TC170** [Odoo 19 → ERROR / AUTOMATION_ERROR] OdooRPCError: product.product.onchange failed: Contact your administrator to request access if necessary.
- **DATAONE-TC172** [Odoo 19 → ERROR / AUTOMATION_ERROR] OdooRPCError: product.product.onchange failed: Contact your administrator to request access if necessary.
- **DATAONE-TC173** [Odoo 19 → ERROR / AUTOMATION_ERROR] OdooRPCError: product.product.onchange failed: Contact your administrator to request access if necessary.
- **DATAONE-TC174** [Odoo 19 → FAIL / ASSERTION] one valuation entry, two lines, valued at the variance times the product's cost: expected {'entries': 1, 'lines': 2, 'debit': 21.0, 'credit': 21.0}, got {'entries': 0, 'lines': 0, 'debit': 0, 'credit': 0}
- **DATAONE-TC175** [Odoo 19 → FAIL / ASSERTION] Physical Inventory lists all three quants: expected [190084, 190085, 190086, 190087], got [190085, 190086, 190087]
- **DATAONE-TC177** [Odoo 19 → FAIL / ASSERTION] storable products with no cycle-count level is zero, or equal to the recorded v17 baseline — any increase is the silent defect expressed as unscheduled products: expected True, got 'current=214 baseline=282 of 22348 storable products'
- **DATAONE-TC251** [Odoo 19 → ERROR / AUTOMATION_ERROR] OdooRPCError: account.account.search_read failed: Invalid field account.account.deprecated in condition ('deprecated', '=', False)
