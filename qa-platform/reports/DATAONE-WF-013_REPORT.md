# DATAONE-WF-013 Report — Customer Invoice Posting: COGS and Revenue Recognition

Generated 2026-09-18 16:26 by `scripts/gen_reports.py` from persisted execution results (`data/results.db`) and the workbook-synced registry. Expected results are the workbook's, verbatim.

## Counts

- Test cases: **32**
- Automated (covered by platform tests): **32** of 32 automatable
- Manual-only: **1**
- Currently BLOCKED (either environment): **19**
- Odoo 17: PASS 11 / FAIL 2 / BLOCKED 19 / SKIPPED 0 / not executed 0
- Odoo 19: PASS 0 / FAIL 0 / BLOCKED 0 / not executed 0

## Cross-version classification

| Classification | Count |
|---|---:|
| SAME_BEHAVIOR | 0 |
| REGRESSION_CANDIDATE | 0 |
| FIXED | 0 |
| SAME_FAILURE | 0 |
| BLOCKED | 19 |
| NOT_COMPARED | 13 |

> REGRESSION_CANDIDATE is not a confirmed regression until failure triage; BLOCKED reflects the missing local Odoo 19 environment (see docs/ENVIRONMENT_STATUS.md).

## Per test case

| TC | Title | Prio | Automation | v17 | v19 | Classification |
|---|---|---|---|---|---|---|
| DATAONE-TC007 | Every env.ref() literal in the custom code resolves against the databa | P0 | AUTOMATED | FAIL | SKIPPED | NOT_COMPARED |
| DATAONE-TC021 | Trial balance identical to the cent, per account | P0 | AUTOMATED | PASS | SKIPPED | NOT_COMPARED |
| DATAONE-TC027 | Analytic distribution key format survived the upgrade | P0 | AUTOMATED | PASS | SKIPPED | NOT_COMPARED |
| DATAONE-TC028 | Analytic distribution coverage on journal items is unchanged | P0 | AUTOMATED | PASS | SKIPPED | NOT_COMPARED |
| DATAONE-TC052 | is_cogs line population survives | P0 | AUTOMATED | PASS | SKIPPED | NOT_COMPARED |
| DATAONE-TC221 | GATE: skip_invoice_sync still produces two asset_receivable lines on v | P0 | AUTOMATED | BLOCKED | SKIPPED | BLOCKED |
| DATAONE-TC222 | The renamed anglo-saxon hook override actually executes on v19 | P0 | AUTOMATED | BLOCKED | SKIPPED | BLOCKED |
| DATAONE-TC223 | COGS and revenue reversal, order_type = buy (Table A) | P0 | AUTOMATED | BLOCKED | SKIPPED | BLOCKED |
| DATAONE-TC224 | COGS and revenue reversal, order_type = project (Table B) | P0 | AUTOMATED | BLOCKED | SKIPPED | BLOCKED |
| DATAONE-TC225 | COGS and revenue reversal, order_type = inventory (Table C) | P0 | AUTOMATED | BLOCKED | SKIPPED | BLOCKED |
| DATAONE-TC226 | COGS and revenue reversal, order_type = cost_center (Table D) | P0 | AUTOMATED | BLOCKED | SKIPPED | BLOCKED |
| DATAONE-TC227 | Consolidated invoice spanning project and buy — the project branch win | P0 | AUTOMATED | BLOCKED | SKIPPED | BLOCKED |
| DATAONE-TC228 | Account 12500 missing — the AR redirect silently no-ops | P0 | AUTOMATED | BLOCKED | SKIPPED | BLOCKED |
| DATAONE-TC229 | Deleted analytic xml_id — ValueError: External ID not found in the sys | P0 | AUTOMATED | PASS | SKIPPED | NOT_COMPARED |
| DATAONE-TC230 | Multi-move mass post — cross-contaminated reversal lines (E5) | P0 | AUTOMATED | BLOCKED | SKIPPED | BLOCKED |
| DATAONE-TC231 | post → draft → post → draft cycle, run three times | P0 | AUTOMATED | BLOCKED | SKIPPED | BLOCKED |
| DATAONE-TC232 | MRO assertion: dto_account_cogs overrides run outermost | P0 | AUTOMATED | BLOCKED | SKIPPED | BLOCKED |
| DATAONE-TC233 | Are zero-value COGS / Interim lines emitted on inventory orders? | P1 | AUTOMATED | BLOCKED | SKIPPED | BLOCKED |
| DATAONE-TC258 | BASELINE: top 20 v17 customer invoices reproduced to the cent | P0 | AUTOMATED | PASS | SKIPPED | NOT_COMPARED |
| DATAONE-TC260 | BASELINE: Stock Interim (Delivered) residue on project orders | P0 | AUTOMATED | PASS | SKIPPED | NOT_COMPARED |
| DATAONE-TC270 | An Invoicing user cannot delete a journal entry | P0 | AUTOMATED | PASS | SKIPPED | NOT_COMPARED |
| DATAONE-TC271 | A Purchase user cannot delete a journal entry | P0 | AUTOMATED | PASS | SKIPPED | NOT_COMPARED |
| DATAONE-TC272 | A Settings user can delete a journal entry | P1 | AUTOMATED | FAIL | SKIPPED | NOT_COMPARED |
| DATAONE-TC273 | No group other than Settings holds perm_unlink on account.move | P0 | AUTOMATED | PASS | SKIPPED | NOT_COMPARED |
| DATAONE-TC274 | The journal-entry Number is read-only on the form (and only there) | P3 | AUTOMATED | PASS | SKIPPED | NOT_COMPARED |
| DATAONE-TC279 | AR labels are suffixed with Project and Customer Contract names on pos | P1 | AUTOMATED | BLOCKED | SKIPPED | BLOCKED |
| DATAONE-TC280 | Reset to draft blanks the AR labels | P1 | AUTOMATED | BLOCKED | SKIPPED | BLOCKED |
| DATAONE-TC281 | Three post → draft → post cycles: labels do not concatenate | P1 | AUTOMATED | BLOCKED | SKIPPED | BLOCKED |
| DATAONE-TC282 | A move with no Project or Contract account gets the empty-segment labe | P3 | AUTOMATED | BLOCKED | SKIPPED | BLOCKED |
| DATAONE-TC283 | Both AR lines — the original and the reversal — carry the suffix | P2 | AUTOMATED | BLOCKED | SKIPPED | BLOCKED |
| DATAONE-TC286 | Invoice lines inherit the sale line's distribution; later lines win on | P0 | AUTOMATED | BLOCKED | SKIPPED | BLOCKED |
| DATAONE-TC287 | The post-create write also fires on lines DataOne itself created | P2 | AUTOMATED | BLOCKED | SKIPPED | BLOCKED |

## Failure notes (triage input)

- **DATAONE-TC007** [Odoo 19 → FAIL / ASSERTION] env.ref() literals that do not resolve: expected {}, got {'base_tier_validation.view_comment_wizard': ['base_tier_validation/models/tier_validation.py:519'], 'dto_reports.reports_module': ['dto_purchase/tests/test_wf014_menu.py:63'], 'location_barcode_labels.b
- **DATAONE-TC007** [Odoo 17 → FAIL / ASSERTION] env.ref() literals that do not resolve: expected {}, got {'dto_cycle_count.cycle_count_category_level_d': ['dto_cycle_count/models/product_product.py:23', 'dto_cycle_count/models/product_product.py:67', 'dto_cycle_count/models/product_template.py:70'], 'dto_pu
- **DATAONE-TC272** [Odoo 19 → FAIL / ASSERTION] the deletion succeeded: expected True, got 'account.move.unlink failed: Contact your administrator to request access if necessary.'
- **DATAONE-TC272** [Odoo 17 → FAIL / ASSERTION] the deletion succeeded: expected True, got 'account.move.unlink failed: Contact your administrator to request access if necessary.'
