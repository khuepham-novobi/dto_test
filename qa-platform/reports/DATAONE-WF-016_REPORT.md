# DATAONE-WF-016 Report — Vendor Bill Entry & Posting

Generated 2026-09-18 16:45 by `scripts/gen_reports.py` from persisted execution results (`data/results.db`) and the workbook-synced registry. Expected results are the workbook's, verbatim.

## Counts

- Test cases: **18**
- Automated (covered by platform tests): **18** of 18 automatable
- Manual-only: **1**
- Currently BLOCKED (either environment): **0**
- Odoo 17: PASS 2 / FAIL 0 / BLOCKED 0 / SKIPPED 0 / not executed 16
- Odoo 19: PASS 0 / FAIL 0 / BLOCKED 0 / not executed 0

## Cross-version classification

| Classification | Count |
|---|---:|
| SAME_BEHAVIOR | 0 |
| REGRESSION_CANDIDATE | 0 |
| FIXED | 0 |
| SAME_FAILURE | 0 |
| BLOCKED | 0 |
| NOT_COMPARED | 18 |

> REGRESSION_CANDIDATE is not a confirmed regression until failure triage; BLOCKED reflects the missing local Odoo 19 environment (see docs/ENVIRONMENT_STATUS.md).

## Per test case

| TC | Title | Prio | Automation | v17 | v19 | Classification |
|---|---|---|---|---|---|---|
| DATAONE-TC049 | Open receivable and payable residuals per partner | P0 | AUTOMATED | PASS | SKIPPED | NOT_COMPARED |
| DATAONE-TC050 | Reconciliation integrity | P0 | AUTOMATED | NOT_RUN | SKIPPED | NOT_COMPARED |
| DATAONE-TC051 | Tax totals by tax and year | P0 | AUTOMATED | PASS | SKIPPED | NOT_COMPARED |
| DATAONE-TC261 | A vendor bill with no attachment refuses to post, with the exact messa | P1 | AUTOMATED | NOT_RUN | SKIPPED | NOT_COMPARED |
| DATAONE-TC262 | The administrator cannot bypass the attachment gate either | P1 | AUTOMATED | NOT_RUN | SKIPPED | NOT_COMPARED |
| DATAONE-TC263 | On a mass post, one attachment-less bill blocks the whole batch | P1 | AUTOMATED | NOT_RUN | SKIPPED | NOT_COMPARED |
| DATAONE-TC264 | Uploading an attachment must make the bill postable (have_attachment r | P1 | AUTOMATED | NOT_RUN | SKIPPED | NOT_COMPARED |
| DATAONE-TC265 | The Have Attachment column and filter reflect the stored value | P3 | AUTOMATED | NOT_RUN | SKIPPED | NOT_COMPARED |
| DATAONE-TC266 | The gate does not touch customer invoices, credit notes or misc entrie | P2 | AUTOMATED | NOT_RUN | SKIPPED | NOT_COMPARED |
| DATAONE-TC267 | Register Payment is not rendered for a non-manager, in all three views | P1 | AUTOMATED | NOT_RUN | SKIPPED | NOT_COMPARED |
| DATAONE-TC268 | Register Payment is denied at the ACL layer by direct RPC | P0 | AUTOMATED | NOT_RUN | SKIPPED | NOT_COMPARED |
| DATAONE-TC269 | Post-install assertion: the payment-register ACL row really names the  | P0 | AUTOMATED | NOT_RUN | SKIPPED | NOT_COMPARED |
| DATAONE-TC275 | A vendor credit note's narration equals the company RMA terms | P2 | AUTOMATED | NOT_RUN | SKIPPED | NOT_COMPARED |
| DATAONE-TC276 | Duplicating a credit note refreshes the terms from the CURRENT company | P2 | AUTOMATED | NOT_RUN | SKIPPED | NOT_COMPARED |
| DATAONE-TC277 | The RMA terms are resolved in the vendor's language | P3 | AUTOMATED | NOT_RUN | SKIPPED | NOT_COMPARED |
| DATAONE-TC278 | The credit-note PDF prints the RMA terms below the totals | P2 | AUTOMATED | NOT_RUN | SKIPPED | NOT_COMPARED |
| DATAONE-TC284 | A bill line inherits the purchase line's analytic distribution at crea | P0 | AUTOMATED | NOT_RUN | SKIPPED | NOT_COMPARED |
| DATAONE-TC285 | The distribution-model rule wins on a colliding key | P0 | AUTOMATED | NOT_RUN | SKIPPED | NOT_COMPARED |
