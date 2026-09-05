# DATAONE-WF-013 Report — Customer Invoice Posting: COGS and Revenue Recognition

Generated 2026-09-05 04:10 by `scripts/gen_reports.py` from persisted execution results (`data/results.db`) and the workbook-synced registry. Expected results are the workbook's, verbatim.

## Counts

- Test cases: **39**
- Automated (covered by platform tests): **39** of 39 automatable
- Manual-only: **1**
- Currently BLOCKED (either environment): **19**
- Odoo 17: PASS 18 / FAIL 2 / BLOCKED 19 / SKIPPED 0 / not executed 0
- Odoo 19: PASS 21 / FAIL 16 / BLOCKED 2 / not executed 0

## Cross-version classification

| Classification | Count |
|---|---:|
| SAME_BEHAVIOR | 4 |
| REGRESSION_CANDIDATE | 14 |
| FIXED | 0 |
| SAME_FAILURE | 2 |
| BLOCKED | 19 |
| NOT_COMPARED | 0 |

> REGRESSION_CANDIDATE is not a confirmed regression until failure triage; BLOCKED reflects the missing local Odoo 19 environment (see docs/ENVIRONMENT_STATUS.md).

## Per test case

| TC | Title | Prio | Automation | v17 | v19 | Classification |
|---|---|---|---|---|---|---|
| DATAONE-TC007 | Every env.ref() literal in the custom code resolves against the databa | P0 | AUTOMATED | FAIL | FAIL | SAME_FAILURE |
| DATAONE-TC021 | Trial balance identical to the cent, per account | P0 | AUTOMATED | PASS | FAIL | REGRESSION_CANDIDATE |
| DATAONE-TC023 | Invoice totals by year × move_type × state | P0 | AUTOMATED | PASS | FAIL | REGRESSION_CANDIDATE |
| DATAONE-TC025 | stock.valuation.layer disappearance: inventory value is preserved | P0 | AUTOMATED | PASS | FAIL | REGRESSION_CANDIDATE |
| DATAONE-TC027 | Analytic distribution key format survived the upgrade | P0 | AUTOMATED | PASS | FAIL | REGRESSION_CANDIDATE |
| DATAONE-TC028 | Analytic distribution coverage on journal items is unchanged | P0 | AUTOMATED | PASS | FAIL | REGRESSION_CANDIDATE |
| DATAONE-TC034 | stock.location valuation-account collapse: two v17 columns folded into | P0 | AUTOMATED | PASS | FAIL | REGRESSION_CANDIDATE |
| DATAONE-TC048 | Journal-item counts and balances per journal per period | P0 | AUTOMATED | PASS | FAIL | REGRESSION_CANDIDATE |
| DATAONE-TC049 | Open receivable and payable residuals per partner | P0 | AUTOMATED | PASS | FAIL | REGRESSION_CANDIDATE |
| DATAONE-TC051 | Tax totals by tax and year | P0 | AUTOMATED | PASS | FAIL | REGRESSION_CANDIDATE |
| DATAONE-TC052 | is_cogs line population survives | P0 | AUTOMATED | PASS | FAIL | REGRESSION_CANDIDATE |
| DATAONE-TC221 | GATE: skip_invoice_sync still produces two asset_receivable lines on v | P0 | AUTOMATED | BLOCKED | PASS | BLOCKED |
| DATAONE-TC222 | The renamed anglo-saxon hook override actually executes on v19 | P0 | AUTOMATED | BLOCKED | BLOCKED | BLOCKED |
| DATAONE-TC223 | COGS and revenue reversal, order_type = buy (Table A) | P0 | AUTOMATED | BLOCKED | PASS | BLOCKED |
| DATAONE-TC224 | COGS and revenue reversal, order_type = project (Table B) | P0 | AUTOMATED | BLOCKED | PASS | BLOCKED |
| DATAONE-TC225 | COGS and revenue reversal, order_type = inventory (Table C) | P0 | AUTOMATED | BLOCKED | PASS | BLOCKED |
| DATAONE-TC226 | COGS and revenue reversal, order_type = cost_center (Table D) | P0 | AUTOMATED | BLOCKED | PASS | BLOCKED |
| DATAONE-TC227 | Consolidated invoice spanning project and buy — the project branch win | P0 | AUTOMATED | BLOCKED | PASS | BLOCKED |
| DATAONE-TC228 | Account 12500 missing — the AR redirect silently no-ops | P0 | AUTOMATED | BLOCKED | PASS | BLOCKED |
| DATAONE-TC229 | Deleted analytic xml_id — ValueError: External ID not found in the sys | P0 | AUTOMATED | PASS | PASS | SAME_BEHAVIOR |
| DATAONE-TC230 | Multi-move mass post — cross-contaminated reversal lines (E5) | P0 | AUTOMATED | BLOCKED | PASS | BLOCKED |
| DATAONE-TC231 | post → draft → post → draft cycle, run three times | P0 | AUTOMATED | BLOCKED | PASS | BLOCKED |
| DATAONE-TC232 | MRO assertion: dto_account_cogs overrides run outermost | P0 | AUTOMATED | BLOCKED | BLOCKED | BLOCKED |
| DATAONE-TC233 | Are zero-value COGS / Interim lines emitted on inventory orders? | P1 | AUTOMATED | BLOCKED | PASS | BLOCKED |
| DATAONE-TC258 | BASELINE: top 20 v17 customer invoices reproduced to the cent | P0 | AUTOMATED | PASS | FAIL | REGRESSION_CANDIDATE |
| DATAONE-TC259 | BASELINE: analytic-distribution key shapes survive on those 40 entries | P0 | AUTOMATED | PASS | FAIL | REGRESSION_CANDIDATE |
| DATAONE-TC260 | BASELINE: Stock Interim (Delivered) residue on project orders | P0 | AUTOMATED | PASS | FAIL | REGRESSION_CANDIDATE |
| DATAONE-TC270 | An Invoicing user cannot delete a journal entry | P0 | AUTOMATED | PASS | PASS | SAME_BEHAVIOR |
| DATAONE-TC271 | A Purchase user cannot delete a journal entry | P0 | AUTOMATED | PASS | PASS | SAME_BEHAVIOR |
| DATAONE-TC272 | A Settings user can delete a journal entry | P1 | AUTOMATED | FAIL | FAIL | SAME_FAILURE |
| DATAONE-TC273 | No group other than Settings holds perm_unlink on account.move | P0 | AUTOMATED | PASS | FAIL | REGRESSION_CANDIDATE |
| DATAONE-TC274 | The journal-entry Number is read-only on the form (and only there) | P3 | AUTOMATED | PASS | PASS | SAME_BEHAVIOR |
| DATAONE-TC279 | AR labels are suffixed with Project and Customer Contract names on pos | P1 | AUTOMATED | BLOCKED | PASS | BLOCKED |
| DATAONE-TC280 | Reset to draft blanks the AR labels | P1 | AUTOMATED | BLOCKED | PASS | BLOCKED |
| DATAONE-TC281 | Three post → draft → post cycles: labels do not concatenate | P1 | AUTOMATED | BLOCKED | PASS | BLOCKED |
| DATAONE-TC282 | A move with no Project or Contract account gets the empty-segment labe | P3 | AUTOMATED | BLOCKED | PASS | BLOCKED |
| DATAONE-TC283 | Both AR lines — the original and the reversal — carry the suffix | P2 | AUTOMATED | BLOCKED | PASS | BLOCKED |
| DATAONE-TC286 | Invoice lines inherit the sale line's distribution; later lines win on | P0 | AUTOMATED | BLOCKED | PASS | BLOCKED |
| DATAONE-TC287 | The post-create write also fires on lines DataOne itself created | P2 | AUTOMATED | BLOCKED | PASS | BLOCKED |

## Failure notes (triage input)

- **DATAONE-TC007** [Odoo 19 → FAIL / ASSERTION] env.ref() literals that do not resolve: expected {}, got {'base_tier_validation.view_comment_wizard': ['base_tier_validation/models/tier_validation.py:519'], 'dto_account_workday.view_workday_journal_entry_export_wizard_form': ['dto_account_workday/models/acco
- **DATAONE-TC007** [Odoo 17 → FAIL / ASSERTION] env.ref() literals that do not resolve: expected {}, got {'dto_cycle_count.cycle_count_category_level_d': ['dto_cycle_count/models/product_product.py:23', 'dto_cycle_count/models/product_product.py:67', 'dto_cycle_count/models/product_template.py:70'], 'dto_pu
- **DATAONE-TC021** [Odoo 19 → FAIL / ASSERTION] No differences vs v17 baseline: expected [], got ['account/14: baseline=0.0 current=None', 'account/189: baseline=None current=-5415078.88', 'account/19: baseline=0.0 current=None', 'account/197: baseline=None current=0.0', 'account/208: baseline=None current=
- **DATAONE-TC023** [Odoo 19 → FAIL / ASSERTION] No differences vs v17 baseline: expected [], got ['count/2021/in_invoice/cancel: baseline=None current=17', 'count/2022/in_invoice/cancel: baseline=None current=10', 'count/2023/in_invoice/cancel: baseline=None current=4', 'count/2024/in_invoice/cancel: baseli
- **DATAONE-TC025** [Odoo 19 → FAIL / ASSERTION] No differences vs v17 baseline: expected [], got ['internal_quant_products: baseline=39 current=913', 'internal_quant_quantity: baseline=1795.0 current=19149171.11', 'svl_model_present: baseline=None current=False', 'svl_products: baseline=17 current=None', 's
- **DATAONE-TC027** [Odoo 19 → FAIL / ASSERTION] No differences vs v17 baseline: expected [], got ['keys_with_1_account(s): baseline=None current=389825', 'keys_with_2_account(s): baseline=None current=136325', 'lines_with_distribution: baseline=0 current=446699']
- **DATAONE-TC028** [Odoo 19 → FAIL / ASSERTION] No differences vs v17 baseline: expected [], got ['journal_items: baseline=84 current=546489', 'with_distribution: baseline=0 current=446699', 'with_distribution/account/197: baseline=None current=14', 'with_distribution/account/208: baseline=None current=1371
- **DATAONE-TC034** [Odoo 19 → FAIL / ASSERTION] No differences vs v17 baseline: expected [], got ["columns_present: baseline='valuation_in_account_id,valuation_out_account_id' current='valuation_account_id'", 'locations: baseline=37 current=343', 'populated/valuation_account_id: baseline=None current=0', 'p
- **DATAONE-TC048** [Odoo 19 → FAIL / ASSERTION] No differences vs v17 baseline: expected [], got ['balance/1/April 2025: baseline=None current=0.0', 'balance/1/April 2026: baseline=None current=0.0', 'balance/1/August 2025: baseline=None current=0.0', 'balance/1/December 2024: baseline=None current=0.0', 'b
- **DATAONE-TC049** [Odoo 19 → FAIL / ASSERTION] No differences vs v17 baseline: expected [], got ['payable/TOTAL: baseline=0.0 current=-683032.62', 'payable/partner/14: baseline=0.0 current=None', 'payable/partner/155: baseline=None current=-2736.0', 'payable/partner/160: baseline=None current=-512.3', 'pay
- **DATAONE-TC051** [Odoo 19 → FAIL / ASSERTION] No differences vs v17 baseline: expected [], got ['balance/1/2026: baseline=0.0 current=None', 'balance/2/2025: baseline=0.0 current=None', 'balance/2/2026: baseline=0.0 current=None', 'count/1/2026: baseline=9 current=None', 'count/2/2025: baseline=2 current=
- **DATAONE-TC052** [Odoo 19 → FAIL / ASSERTION] No differences vs v17 baseline: expected [], got ['is_cogs/account/197: baseline=None current=-70.0', 'is_cogs/account/208: baseline=None current=-505413.25', 'is_cogs/account/278: baseline=None current=505483.25', 'is_cogs_accounts: baseline=0 current=3', 'is
- **DATAONE-TC258** [Odoo 19 → FAIL / ASSERTION] No differences vs v17 baseline: expected [], got ['account/INV-2024-00004/208: baseline=None current=0.0', 'account/INV-2024-00004/278: baseline=None current=0.0', 'account/INV-2024-00004/282: baseline=None current=0.0', 'account/INV-2024-00005/208: baseline=N
- **DATAONE-TC259** [Odoo 19 → FAIL / ASSERTION] No differences vs v17 baseline: expected [], got ['invoices_captured: baseline=4 current=20', 'keys_with_1_account(s): baseline=None current=1001', 'keys_with_2_account(s): baseline=None current=523', 'lines_with_distribution: baseline=0 current=1046']
- **DATAONE-TC260** [Odoo 19 → FAIL / ASSERTION] No differences vs v17 baseline: expected [], got ['interim/110200/balance: baseline=0.0 current=None', 'interim/110200/lines: baseline=0 current=None', 'interim/110300/balance: baseline=0.0 current=None', 'interim/110300/lines: baseline=0 current=None', 'inter
- **DATAONE-TC272** [Odoo 19 → FAIL / ASSERTION] the deletion succeeded: expected True, got 'account.move.unlink failed: Contact your administrator to request access if necessary.'
- **DATAONE-TC272** [Odoo 17 → FAIL / ASSERTION] the deletion succeeded: expected True, got 'account.move.unlink failed: Contact your administrator to request access if necessary.'
- **DATAONE-TC273** [Odoo 19 → FAIL / ASSERTION] groups holding perm_unlink on account.move: expected ['base.group_system'], got ['base.group_system', 'hr.group_hr_manager']
- **DATAONE-TC273** [Odoo 17 → FAIL / ASSERTION] access rows exist for account.move: expected True, got '[]'
