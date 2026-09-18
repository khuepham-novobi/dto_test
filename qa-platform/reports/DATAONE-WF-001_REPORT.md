# DATAONE-WF-001 Report — Workday requisition → sales order (inbound)

Generated 2026-09-18 16:26 by `scripts/gen_reports.py` from persisted execution results (`data/results.db`) and the workbook-synced registry. Expected results are the workbook's, verbatim.

## Counts

- Test cases: **7**
- Automated (covered by platform tests): **7** of 7 automatable
- Manual-only: **0**
- Currently BLOCKED (either environment): **0**
- Odoo 17: PASS 0 / FAIL 0 / BLOCKED 0 / SKIPPED 0 / not executed 7
- Odoo 19: PASS 2 / FAIL 3 / BLOCKED 0 / not executed 0

## Cross-version classification

| Classification | Count |
|---|---:|
| SAME_BEHAVIOR | 0 |
| REGRESSION_CANDIDATE | 0 |
| FIXED | 0 |
| SAME_FAILURE | 0 |
| BLOCKED | 0 |
| NOT_COMPARED | 7 |

> REGRESSION_CANDIDATE is not a confirmed regression until failure triage; BLOCKED reflects the missing local Odoo 19 environment (see docs/ENVIRONMENT_STATUS.md).

## Per test case

| TC | Title | Prio | Automation | v17 | v19 | Classification |
|---|---|---|---|---|---|---|
| DATAONE-TC303 | A folder with usage = 'none' leaves its files Pending forever | P2 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |
| DATAONE-TC337 | GATE: one file, two Requisition_Num, 23 columns, two draft orders | P0 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |
| DATAONE-TC339 | Re-import of a confirmed order updates only the header and raises the  | P0 | AUTOMATED | NOT_RUN | ERROR | NOT_COMPARED |
| DATAONE-TC340 | Empty Item fails the whole file with the offending row dumped into the | P1 | AUTOMATED | NOT_RUN | FAIL | NOT_COMPARED |
| DATAONE-TC341 | Empty Ship-To_Contact fails the whole file with the offending row dump | P1 | AUTOMATED | NOT_RUN | FAIL | NOT_COMPARED |
| DATAONE-TC342 | The manual upload wizard produces the same orders — and no sftp.file | P1 | AUTOMATED | NOT_RUN | SKIPPED | NOT_COMPARED |
| DATAONE-TC343 | An address typo silently auto-creates a second ship-to contact | P2 | AUTOMATED | NOT_RUN | SKIPPED | NOT_COMPARED |

## Failure notes (triage input)

- **DATAONE-TC339** [Odoo 19 → ERROR / AUTOMATION_ERROR] OdooRPCError: sale.order.action_confirm failed: Customer Contract is required
- **DATAONE-TC340** [Odoo 19 → FAIL / ASSERTION] it carries 'Item is empty': expected True, got '<p>Unknown error when sanitizing</p> || <p>SFTP File created</p> || <div style="margin:0px; padding:0px; font-size:13px">\n    Dear <span>OdooBot</span>,\n    <br><br>\n    <p>\n        <span>Administrator</span>
- **DATAONE-TC341** [Odoo 19 → FAIL / ASSERTION] every token-scoped count unchanged: expected {'sale.order': 0, 'res.partner': 1, 'product.product': 1, 'account.analytic.account': 0}, got {'sale.order': 0, 'res.partner': 1, 'product.product': 2, 'account.analytic.account': 2}
