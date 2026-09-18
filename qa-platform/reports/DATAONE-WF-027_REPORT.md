# DATAONE-WF-027 Report — Management Reporting

Generated 2026-09-18 16:45 by `scripts/gen_reports.py` from persisted execution results (`data/results.db`) and the workbook-synced registry. Expected results are the workbook's, verbatim.

## Counts

- Test cases: **23**
- Automated (covered by platform tests): **13** of 22 automatable
- Manual-only: **1**
- Currently BLOCKED (either environment): **5**
- Odoo 17: PASS 0 / FAIL 0 / BLOCKED 0 / SKIPPED 0 / not executed 23
- Odoo 19: PASS 7 / FAIL 1 / BLOCKED 5 / not executed 10

## Cross-version classification

| Classification | Count |
|---|---:|
| SAME_BEHAVIOR | 0 |
| REGRESSION_CANDIDATE | 0 |
| FIXED | 0 |
| SAME_FAILURE | 0 |
| BLOCKED | 5 |
| NOT_COMPARED | 18 |

> REGRESSION_CANDIDATE is not a confirmed regression until failure triage; BLOCKED reflects the missing local Odoo 19 environment (see docs/ENVIRONMENT_STATUS.md).

## Per test case

| TC | Title | Prio | Automation | v17 | v19 | Classification |
|---|---|---|---|---|---|---|
| DATAONE-TC013 | Every menu in the custom menu tree opens without error, as a user in t | P1 | AUTOMATED | NOT_RUN | FAIL | NOT_COMPARED |
| DATAONE-TC022 | Trial balance report export matches, v17 vs v19 | P0 | AUTOMATED | NOT_RUN | BLOCKED | BLOCKED |
| DATAONE-TC088 | "Cost Analysis View" gates the product cost-structure stat button | P2 | AUTOMATED | NOT_RUN | BLOCKED | BLOCKED |
| DATAONE-TC376 | The Reports app is visible to a "Review reports" member and absent for | P0 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |
| DATAONE-TC377 | Scrap Entries lists only posted entries whose reference contains SP-,  | P1 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| DATAONE-TC378 | Orders Completed per Day counts done MOs by finish day and silently ex | P1 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| DATAONE-TC379 | Cable Assemblies Produced reports quantity by product and week, includ | P1 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| DATAONE-TC380 | Feet of Cable Cut/Processed reports 50.0 ft in week 2026-W34 for TD-P- | P0 | PLANNED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| DATAONE-TC381 | Labor hour per assembly totals 180 minutes in week 2026-W34, split 120 | P1 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| DATAONE-TC382 | Average Assembly Time per Unit is 36.0, becomes 60.0 when an MO is fla | P1 | PLANNED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| DATAONE-TC383 | MO Actual time is 120.0 and Expected time is 72.0, and Expected does n | P1 | PLANNED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| DATAONE-TC384 | Time Sheet Report shows the four stored related columns, and the time_ | P1 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| DATAONE-TC385 | Customer Delivery Report shows only the confirmed, to-invoice order | P1 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| DATAONE-TC386 | Vendor Delivery Report shows the confirmed and the locked PO — the v19 | P0 | PLANNED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| DATAONE-TC387 | Vendor RMA and Customer RMA menus resolve and open the correct picking | P2 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |
| DATAONE-TC388 | Which ir.ui.view the standard Purchase menu actually serves for purcha | P0 | AUTOMATED | NOT_RUN | BLOCKED | BLOCKED |
| DATAONE-TC389 | BOM Lines multi-edit changes quantity on every selected line and on th | P1 | AUTOMATED | NOT_RUN | BLOCKED | BLOCKED |
| DATAONE-TC390 | Dead stock over 2026-01-01 → 2026-08-20 returns TD-P-10 and not TD-P-1 | P0 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |
| DATAONE-TC391 | Products created after the Start Date, services and consumables never  | P1 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |
| DATAONE-TC392 | A product whose only moves in the window are draft or cancelled still  | P1 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |
| DATAONE-TC393 | The dead-stock XLSX has the five named columns, two data rows and the  | P0 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |
| DATAONE-TC394 | Download Excel with xlsxwriter absent raises exactly "The xlsxwriter l | P2 | AUTOMATED | NOT_RUN | BLOCKED | BLOCKED |
| DATAONE-TC395 | An End Date earlier than the Start Date is accepted and returns every  | P1 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |

## Failure notes (triage input)

- **DATAONE-TC013** [Odoo 19 → FAIL / ASSERTION] somebody holds the group that gates the Reports app: expected True, got 'no user on this database holds dto_reports.reports_module, and the group is hidden from the Settings UI (D-new-14 deleted its category for v19), so the entire Management Reporting app is 
