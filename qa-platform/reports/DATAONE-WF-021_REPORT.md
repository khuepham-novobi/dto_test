# DATAONE-WF-021 Report — Cycle Counting and Inventory Adjustment

Generated 2026-09-18 16:45 by `scripts/gen_reports.py` from persisted execution results (`data/results.db`) and the workbook-synced registry. Expected results are the workbook's, verbatim.

## Counts

- Test cases: **13**
- Automated (covered by platform tests): **13** of 13 automatable
- Manual-only: **0**
- Currently BLOCKED (either environment): **0**
- Odoo 17: PASS 2 / FAIL 0 / BLOCKED 0 / SKIPPED 0 / not executed 11
- Odoo 19: PASS 0 / FAIL 0 / BLOCKED 0 / not executed 0

## Cross-version classification

| Classification | Count |
|---|---:|
| SAME_BEHAVIOR | 0 |
| REGRESSION_CANDIDATE | 0 |
| FIXED | 0 |
| SAME_FAILURE | 0 |
| BLOCKED | 0 |
| NOT_COMPARED | 13 |

> REGRESSION_CANDIDATE is not a confirmed regression until failure triage; BLOCKED reflects the missing local Odoo 19 environment (see docs/ENVIRONMENT_STATUS.md).

## Per test case

| TC | Title | Prio | Automation | v17 | v19 | Classification |
|---|---|---|---|---|---|---|
| DATAONE-TC025 | stock.valuation.layer disappearance: inventory value is preserved | P0 | AUTOMATED | PASS | SKIPPED | NOT_COMPARED |
| DATAONE-TC034 | stock.location valuation-account collapse: two v17 columns folded into | P0 | AUTOMATED | PASS | SKIPPED | NOT_COMPARED |
| DATAONE-TC055 | Cycle-count level assignments and quant scheduling | P1 | AUTOMATED | NOT_RUN | SKIPPED | NOT_COMPARED |
| DATAONE-TC169 | The five shipped levels produce the five documented intervals from a f | P1 | AUTOMATED | NOT_RUN | SKIPPED | NOT_COMPARED |
| DATAONE-TC170 | Setting the category to 'Finished Goods' on the form auto-assigns Leve | P1 | AUTOMATED | NOT_RUN | SKIPPED | NOT_COMPARED |
| DATAONE-TC171 | A product created by import or RPC also receives Level D through creat | P1 | AUTOMATED | NOT_RUN | SKIPPED | NOT_COMPARED |
| DATAONE-TC172 | A storable product cannot be saved without a cycle-count level in the  | P1 | AUTOMATED | NOT_RUN | SKIPPED | NOT_COMPARED |
| DATAONE-TC173 | Level B with Last Count Date 2026-08-20 displays Scheduled Count Date  | P1 | AUTOMATED | NOT_RUN | SKIPPED | NOT_COMPARED |
| DATAONE-TC174 | Applying a count stamps quant and product and pushes inventory_date to | P0 | AUTOMATED | NOT_RUN | SKIPPED | NOT_COMPARED |
| DATAONE-TC175 | Changing a product's level re-schedules every one of its quants in the | P1 | AUTOMATED | NOT_RUN | SKIPPED | NOT_COMPARED |
| DATAONE-TC176 | Cycle-count columns, search fields and group-bys are available on prod | P2 | AUTOMATED | NOT_RUN | SKIPPED | NOT_COMPARED |
| DATAONE-TC177 | v19 detector: the required-level rule must still be enforced after typ | P0 | AUTOMATED | NOT_RUN | SKIPPED | NOT_COMPARED |
| DATAONE-TC251 | Inventory adjustment through a tagged virtual location | P0 | AUTOMATED | NOT_RUN | SKIPPED | NOT_COMPARED |
