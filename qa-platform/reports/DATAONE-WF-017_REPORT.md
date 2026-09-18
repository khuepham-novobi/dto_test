# DATAONE-WF-017 Report — Journal Entry Export to Workday

Generated 2026-09-18 14:23 by `scripts/gen_reports.py` from persisted execution results (`data/results.db`) and the workbook-synced registry. Expected results are the workbook's, verbatim.

## Counts

- Test cases: **13**
- Automated (covered by platform tests): **13** of 13 automatable
- Manual-only: **0**
- Currently BLOCKED (either environment): **3**
- Odoo 17: PASS 0 / FAIL 0 / BLOCKED 0 / SKIPPED 0 / not executed 13
- Odoo 19: PASS 5 / FAIL 5 / BLOCKED 3 / not executed 0

## Cross-version classification

| Classification | Count |
|---|---:|
| SAME_BEHAVIOR | 0 |
| REGRESSION_CANDIDATE | 0 |
| FIXED | 0 |
| SAME_FAILURE | 0 |
| BLOCKED | 3 |
| NOT_COMPARED | 10 |

> REGRESSION_CANDIDATE is not a confirmed regression until failure triage; BLOCKED reflects the missing local Odoo 19 environment (see docs/ENVIRONMENT_STATUS.md).

## Per test case

| TC | Title | Prio | Automation | v17 | v19 | Classification |
|---|---|---|---|---|---|---|
| DATAONE-TC036 | Workday journal-source catalogue and mappings survive | P1 | AUTOMATED | NOT_RUN | BLOCKED | BLOCKED |
| DATAONE-TC291 | Test Connection succeeds against the E6 endpoint | P1 | AUTOMATED | NOT_RUN | BLOCKED | BLOCKED |
| DATAONE-TC292 | Test Connection fails — red toast plus one sftp.log error with a trace | P1 | AUTOMATED | NOT_RUN | FAIL | NOT_COMPARED |
| DATAONE-TC306 | GATE: eight posted moves, XLSX asserted cell by cell, column T non-bla | P0 | AUTOMATED | NOT_RUN | FAIL | NOT_COMPARED |
| DATAONE-TC307 | The selection domain excludes bills, bank journals, drafts and already | P1 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |
| DATAONE-TC308 | The balance != 0 line filter, plus section / note / line_subsection | P0 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |
| DATAONE-TC309 | BASELINE: per-entry-type journal-source resolution, all seven rows plu | P0 | AUTOMATED | NOT_RUN | FAIL | NOT_COMPARED |
| DATAONE-TC310 | "Export and Mark as exported" vs "Export only", and the re-export cons | P0 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |
| DATAONE-TC311 | Fixed filename: the second same-day export collides and goes Failed | P0 | AUTOMATED | NOT_RUN | BLOCKED | BLOCKED |
| DATAONE-TC312 | One failed line withholds the whole move, files an activity, leaves no | P0 | AUTOMATED | NOT_RUN | ERROR | NOT_COMPARED |
| DATAONE-TC313 | Nothing qualifies: There is nothing to export!, no sftp.file | P1 | AUTOMATED | NOT_RUN | ERROR | NOT_COMPARED |
| DATAONE-TC314 | Mis-configured folder or template raises UserError before any workbook | P1 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |
| DATAONE-TC315 | Blocking selection validations: empty, unposted, and in_invoice | P1 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |

## Failure notes (triage input)

- **DATAONE-TC292** [Odoo 19 → FAIL / ASSERTION] every field the case reads exists: expected [], got ['traceback']
- **DATAONE-TC306** [Odoo 19 → FAIL / ASSERTION] every entry type that exists on this target resolves to EXACTLY its mapped id_workday, with no blank and no second value — a blank here IS the stock.valuation.layer defect, visible before a workbook is opened: expected {}, got {'outgoing_return': {'expected': 
- **DATAONE-TC309** [Odoo 19 → FAIL / ASSERTION] all seven entry types map to their tabled journal source, with exact casing: expected {'incoming': 'Inventory_Put_Away', 'outgoing': 'Inventory_Shipment', 'outgoing_return': 'Inventory_Return_To_Supplier', 'incoming_return': 'Inventory_Put_Away_Adjustment', 'm
- **DATAONE-TC312** [Odoo 19 → ERROR / AUTOMATION_ERROR] OdooRPCError: account.journal.create failed: The operation cannot be completed: Journal codes must be unique per company.
- **DATAONE-TC313** [Odoo 19 → ERROR / AUTOMATION_ERROR] OdooRPCError: account.journal.create failed: The operation cannot be completed: Journal codes must be unique per company.
