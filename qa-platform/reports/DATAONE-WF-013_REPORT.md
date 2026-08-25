# DATAONE-WF-013 Report — Customer Invoice Posting: COGS and Revenue Recognition

Generated 2026-08-25 11:52 by `scripts/gen_reports.py` from persisted execution results (`data/results.db`) and the workbook-synced registry. Expected results are the workbook's, verbatim.

## Counts

- Test cases: **39**
- Automated (covered by platform tests): **39** of 39 automatable
- Manual-only: **1**
- Currently BLOCKED (either environment): **0**
- Odoo 17: PASS 0 / FAIL 0 / BLOCKED 0 / SKIPPED 0 / not executed 39
- Odoo 19: PASS 0 / FAIL 0 / BLOCKED 0 / not executed 39

## Cross-version classification

| Classification | Count |
|---|---:|
| SAME_BEHAVIOR | 0 |
| REGRESSION_CANDIDATE | 0 |
| FIXED | 0 |
| SAME_FAILURE | 0 |
| BLOCKED | 0 |
| NOT_COMPARED | 39 |

> REGRESSION_CANDIDATE is not a confirmed regression until failure triage; BLOCKED reflects the missing local Odoo 19 environment (see docs/ENVIRONMENT_STATUS.md).

## Per test case

| TC | Title | Prio | Automation | v17 | v19 | Classification |
|---|---|---|---|---|---|---|
| DATAONE-TC007 | Every env.ref() literal in the custom code resolves against the databa | P0 | AUTOMATED | NOT_RUN | NOT_RUN | NOT_COMPARED |
| DATAONE-TC021 | Trial balance identical to the cent, per account | P0 | AUTOMATED | NOT_RUN | NOT_RUN | NOT_COMPARED |
| DATAONE-TC023 | Invoice totals by year × move_type × state | P0 | AUTOMATED | NOT_RUN | NOT_RUN | NOT_COMPARED |
| DATAONE-TC025 | stock.valuation.layer disappearance: inventory value is preserved | P0 | AUTOMATED | NOT_RUN | NOT_RUN | NOT_COMPARED |
| DATAONE-TC027 | Analytic distribution key format survived the upgrade | P0 | AUTOMATED | NOT_RUN | NOT_RUN | NOT_COMPARED |
| DATAONE-TC028 | Analytic distribution coverage on journal items is unchanged | P0 | AUTOMATED | NOT_RUN | NOT_RUN | NOT_COMPARED |
| DATAONE-TC034 | stock.location valuation-account collapse: two v17 columns folded into | P0 | AUTOMATED | NOT_RUN | NOT_RUN | NOT_COMPARED |
| DATAONE-TC048 | Journal-item counts and balances per journal per period | P0 | AUTOMATED | NOT_RUN | NOT_RUN | NOT_COMPARED |
| DATAONE-TC049 | Open receivable and payable residuals per partner | P0 | AUTOMATED | NOT_RUN | NOT_RUN | NOT_COMPARED |
| DATAONE-TC051 | Tax totals by tax and year | P0 | AUTOMATED | NOT_RUN | NOT_RUN | NOT_COMPARED |
| DATAONE-TC052 | is_cogs line population survives | P0 | AUTOMATED | NOT_RUN | NOT_RUN | NOT_COMPARED |
| DATAONE-TC221 | GATE: skip_invoice_sync still produces two asset_receivable lines on v | P0 | AUTOMATED | NOT_RUN | NOT_RUN | NOT_COMPARED |
| DATAONE-TC222 | The renamed anglo-saxon hook override actually executes on v19 | P0 | AUTOMATED | NOT_RUN | NOT_RUN | NOT_COMPARED |
| DATAONE-TC223 | COGS and revenue reversal, order_type = buy (Table A) | P0 | AUTOMATED | NOT_RUN | NOT_RUN | NOT_COMPARED |
| DATAONE-TC224 | COGS and revenue reversal, order_type = project (Table B) | P0 | AUTOMATED | NOT_RUN | NOT_RUN | NOT_COMPARED |
| DATAONE-TC225 | COGS and revenue reversal, order_type = inventory (Table C) | P0 | AUTOMATED | NOT_RUN | NOT_RUN | NOT_COMPARED |
| DATAONE-TC226 | COGS and revenue reversal, order_type = cost_center (Table D) | P0 | AUTOMATED | NOT_RUN | NOT_RUN | NOT_COMPARED |
| DATAONE-TC227 | Consolidated invoice spanning project and buy — the project branch win | P0 | AUTOMATED | NOT_RUN | NOT_RUN | NOT_COMPARED |
| DATAONE-TC228 | Account 12500 missing — the AR redirect silently no-ops | P0 | AUTOMATED | NOT_RUN | NOT_RUN | NOT_COMPARED |
| DATAONE-TC229 | Deleted analytic xml_id — ValueError: External ID not found in the sys | P0 | AUTOMATED | NOT_RUN | NOT_RUN | NOT_COMPARED |
| DATAONE-TC230 | Multi-move mass post — cross-contaminated reversal lines (E5) | P0 | AUTOMATED | NOT_RUN | NOT_RUN | NOT_COMPARED |
| DATAONE-TC231 | post → draft → post → draft cycle, run three times | P0 | AUTOMATED | NOT_RUN | NOT_RUN | NOT_COMPARED |
| DATAONE-TC232 | MRO assertion: dto_account_cogs overrides run outermost | P0 | AUTOMATED | NOT_RUN | NOT_RUN | NOT_COMPARED |
| DATAONE-TC233 | Are zero-value COGS / Interim lines emitted on inventory orders? | P1 | AUTOMATED | NOT_RUN | NOT_RUN | NOT_COMPARED |
| DATAONE-TC258 | BASELINE: top 20 v17 customer invoices reproduced to the cent | P0 | AUTOMATED | NOT_RUN | NOT_RUN | NOT_COMPARED |
| DATAONE-TC259 | BASELINE: analytic-distribution key shapes survive on those 40 entries | P0 | AUTOMATED | NOT_RUN | NOT_RUN | NOT_COMPARED |
| DATAONE-TC260 | BASELINE: Stock Interim (Delivered) residue on project orders | P0 | AUTOMATED | NOT_RUN | NOT_RUN | NOT_COMPARED |
| DATAONE-TC270 | An Invoicing user cannot delete a journal entry | P0 | AUTOMATED | NOT_RUN | NOT_RUN | NOT_COMPARED |
| DATAONE-TC271 | A Purchase user cannot delete a journal entry | P0 | AUTOMATED | NOT_RUN | NOT_RUN | NOT_COMPARED |
| DATAONE-TC272 | A Settings user can delete a journal entry | P1 | AUTOMATED | NOT_RUN | NOT_RUN | NOT_COMPARED |
| DATAONE-TC273 | No group other than Settings holds perm_unlink on account.move | P0 | AUTOMATED | NOT_RUN | NOT_RUN | NOT_COMPARED |
| DATAONE-TC274 | The journal-entry Number is read-only on the form (and only there) | P3 | AUTOMATED | NOT_RUN | NOT_RUN | NOT_COMPARED |
| DATAONE-TC279 | AR labels are suffixed with Project and Customer Contract names on pos | P1 | AUTOMATED | NOT_RUN | NOT_RUN | NOT_COMPARED |
| DATAONE-TC280 | Reset to draft blanks the AR labels | P1 | AUTOMATED | NOT_RUN | NOT_RUN | NOT_COMPARED |
| DATAONE-TC281 | Three post → draft → post cycles: labels do not concatenate | P1 | AUTOMATED | NOT_RUN | NOT_RUN | NOT_COMPARED |
| DATAONE-TC282 | A move with no Project or Contract account gets the empty-segment labe | P3 | AUTOMATED | NOT_RUN | NOT_RUN | NOT_COMPARED |
| DATAONE-TC283 | Both AR lines — the original and the reversal — carry the suffix | P2 | AUTOMATED | NOT_RUN | NOT_RUN | NOT_COMPARED |
| DATAONE-TC286 | Invoice lines inherit the sale line's distribution; later lines win on | P0 | AUTOMATED | NOT_RUN | NOT_RUN | NOT_COMPARED |
| DATAONE-TC287 | The post-create write also fires on lines DataOne itself created | P2 | AUTOMATED | NOT_RUN | NOT_RUN | NOT_COMPARED |

## Feasibility decisions

implemented 39 · blocked_stub 0 · not_implemented 0 (details: `reports/data/wf013_feasibility.json`)
