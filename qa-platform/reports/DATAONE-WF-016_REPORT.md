# DATAONE-WF-016 Report — Vendor Bill Entry & Posting

Generated 2026-09-18 14:23 by `scripts/gen_reports.py` from persisted execution results (`data/results.db`) and the workbook-synced registry. Expected results are the workbook's, verbatim.

## Counts

- Test cases: **18**
- Automated (covered by platform tests): **18** of 18 automatable
- Manual-only: **1**
- Currently BLOCKED (either environment): **1**
- Odoo 17: PASS 2 / FAIL 0 / BLOCKED 0 / SKIPPED 0 / not executed 16
- Odoo 19: PASS 4 / FAIL 13 / BLOCKED 1 / not executed 0

## Cross-version classification

| Classification | Count |
|---|---:|
| SAME_BEHAVIOR | 0 |
| REGRESSION_CANDIDATE | 2 |
| FIXED | 0 |
| SAME_FAILURE | 0 |
| BLOCKED | 1 |
| NOT_COMPARED | 15 |

> REGRESSION_CANDIDATE is not a confirmed regression until failure triage; BLOCKED reflects the missing local Odoo 19 environment (see docs/ENVIRONMENT_STATUS.md).

## Per test case

| TC | Title | Prio | Automation | v17 | v19 | Classification |
|---|---|---|---|---|---|---|
| DATAONE-TC049 | Open receivable and payable residuals per partner | P0 | AUTOMATED | PASS | FAIL | REGRESSION_CANDIDATE |
| DATAONE-TC050 | Reconciliation integrity | P0 | AUTOMATED | NOT_RUN | BLOCKED | BLOCKED |
| DATAONE-TC051 | Tax totals by tax and year | P0 | AUTOMATED | PASS | FAIL | REGRESSION_CANDIDATE |
| DATAONE-TC261 | A vendor bill with no attachment refuses to post, with the exact messa | P1 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |
| DATAONE-TC262 | The administrator cannot bypass the attachment gate either | P1 | AUTOMATED | NOT_RUN | FAIL | NOT_COMPARED |
| DATAONE-TC263 | On a mass post, one attachment-less bill blocks the whole batch | P1 | AUTOMATED | NOT_RUN | FAIL | NOT_COMPARED |
| DATAONE-TC264 | Uploading an attachment must make the bill postable (have_attachment r | P1 | AUTOMATED | NOT_RUN | FAIL | NOT_COMPARED |
| DATAONE-TC265 | The Have Attachment column and filter reflect the stored value | P3 | AUTOMATED | NOT_RUN | ERROR | NOT_COMPARED |
| DATAONE-TC266 | The gate does not touch customer invoices, credit notes or misc entrie | P2 | AUTOMATED | NOT_RUN | FAIL | NOT_COMPARED |
| DATAONE-TC267 | Register Payment is not rendered for a non-manager, in all three views | P1 | AUTOMATED | NOT_RUN | ERROR | NOT_COMPARED |
| DATAONE-TC268 | Register Payment is denied at the ACL layer by direct RPC | P0 | AUTOMATED | NOT_RUN | ERROR | NOT_COMPARED |
| DATAONE-TC269 | Post-install assertion: the payment-register ACL row really names the  | P0 | AUTOMATED | NOT_RUN | FAIL | NOT_COMPARED |
| DATAONE-TC275 | A vendor credit note's narration equals the company RMA terms | P2 | AUTOMATED | NOT_RUN | FAIL | NOT_COMPARED |
| DATAONE-TC276 | Duplicating a credit note refreshes the terms from the CURRENT company | P2 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |
| DATAONE-TC277 | The RMA terms are resolved in the vendor's language | P3 | AUTOMATED | NOT_RUN | ERROR | NOT_COMPARED |
| DATAONE-TC278 | The credit-note PDF prints the RMA terms below the totals | P2 | AUTOMATED | NOT_RUN | FAIL | NOT_COMPARED |
| DATAONE-TC284 | A bill line inherits the purchase line's analytic distribution at crea | P0 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |
| DATAONE-TC285 | The distribution-model rule wins on a colliding key | P0 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |

## Failure notes (triage input)

- **DATAONE-TC049** [Odoo 19 → FAIL / ASSERTION] No differences vs v17 baseline: expected [], got ['payable/TOTAL: baseline=0.0 current=-683032.62', 'payable/partner/14: baseline=0.0 current=None', 'payable/partner/155: baseline=None current=-2736.0', 'payable/partner/160: baseline=None current=-512.3', 'pay
- **DATAONE-TC051** [Odoo 19 → FAIL / ASSERTION] No differences vs v17 baseline: expected [], got ['balance/1/2026: baseline=0.0 current=None', 'balance/2/2025: baseline=0.0 current=None', 'balance/2/2026: baseline=0.0 current=None', 'count/1/2026: baseline=9 current=None', 'count/2/2025: baseline=2 current=
- **DATAONE-TC262** [Odoo 19 → FAIL / ASSERTION] have_attachment after attaching: expected True, got False
- **DATAONE-TC263** [Odoo 19 → FAIL / ASSERTION] bill A have_attachment: expected True, got False
- **DATAONE-TC264** [Odoo 19 → FAIL / ASSERTION] have_attachment after writing attachment_ids on the move: expected True, got False
- **DATAONE-TC265** [Odoo 19 → ERROR / AUTOMATION_ERROR] OdooRPCError: account.move.action_post failed: User cannot confirm the bill. The Vendor Bill requires an attachment before posting.
- **DATAONE-TC266** [Odoo 19 → FAIL / ASSERTION] ungated move types that did not post: expected {}, got {'entry': {'state': 'draft', 'why': "account.move.action_post failed: Even magicians can't post nothing!"}}
- **DATAONE-TC267** [Odoo 19 → ERROR / AUTOMATION_ERROR] OdooRPCError: account.move.action_post failed: User cannot confirm the bill. The Vendor Bill requires an attachment before posting.
- **DATAONE-TC268** [Odoo 19 → ERROR / AUTOMATION_ERROR] OdooRPCError: account.move.action_post failed: User cannot confirm the bill. The Vendor Bill requires an attachment before posting.
- **DATAONE-TC269** [Odoo 19 → FAIL / ASSERTION] groups other than Accounting Manager with access to account.payment.register: expected {}, got {'Accountant access': {'perm_read': True, 'perm_write': True, 'perm_create': True, 'perm_unlink': False}, 'Accountant lock dates': {'perm_read': True, 'perm_write': 
- **DATAONE-TC275** [Odoo 19 → FAIL / ASSERTION] required RMA elements absent from the narration: expected [], got ['15 days']
- **DATAONE-TC277** [Odoo 19 → ERROR / AUTOMATION_ERROR] OdooRPCError: account.move.get_default_narration failed: 'int' object has no attribute 'lang'
- **DATAONE-TC278** [Odoo 19 → FAIL / ASSERTION] at least one DataOne QWeb inherit of the invoice report exists — if the anchor rotted at install, there would be none: expected True, got False
