# DATAONE-WF-008 Report — Manufacturing Cost Absorption (Labour and Overhead)

Generated 2026-09-18 17:29 by `scripts/gen_reports.py` from persisted execution results (`data/results.db`) and the workbook-synced registry. Expected results are the workbook's, verbatim.

## Counts

- Test cases: **23**
- Automated (covered by platform tests): **23** of 23 automatable
- Manual-only: **0**
- Currently BLOCKED (either environment): **1**
- Odoo 17: PASS 2 / FAIL 0 / BLOCKED 0 / SKIPPED 0 / not executed 21
- Odoo 19: PASS 2 / FAIL 20 / BLOCKED 1 / not executed 0

## Cross-version classification

| Classification | Count |
|---|---:|
| SAME_BEHAVIOR | 0 |
| REGRESSION_CANDIDATE | 2 |
| FIXED | 0 |
| SAME_FAILURE | 0 |
| BLOCKED | 1 |
| NOT_COMPARED | 20 |

> REGRESSION_CANDIDATE is not a confirmed regression until failure triage; BLOCKED reflects the missing local Odoo 19 environment (see docs/ENVIRONMENT_STATUS.md).

## Per test case

| TC | Title | Prio | Automation | v17 | v19 | Classification |
|---|---|---|---|---|---|---|
| DATAONE-TC048 | Journal-item counts and balances per journal per period | P0 | AUTOMATED | PASS | FAIL | REGRESSION_CANDIDATE |
| DATAONE-TC234 | GATE: six-line finished-goods entry (components 600 + labour 300 + ove | P0 | AUTOMATED | NOT_RUN | FAIL | NOT_COMPARED |
| DATAONE-TC235 | Overhead only, labour switch off | P0 | AUTOMATED | NOT_RUN | FAIL | NOT_COMPARED |
| DATAONE-TC236 | Labour only, overhead switch off | P0 | AUTOMATED | NOT_RUN | FAIL | NOT_COMPARED |
| DATAONE-TC237 | Both switches off — exactly two valuation lines and no uplift | P0 | AUTOMATED | NOT_RUN | FAIL | NOT_COMPARED |
| DATAONE-TC238 | Zero-yield pool skipped from the entry but still frozen into the snaps | P0 | AUTOMATED | NOT_RUN | ERROR | NOT_COMPARED |
| DATAONE-TC239 | Missing labour expense account raises the exact UserError | P0 | AUTOMATED | NOT_RUN | FAIL | NOT_COMPARED |
| DATAONE-TC240 | price_unit rises by exactly overhead ÷ quantity, labour not included | P0 | AUTOMATED | NOT_RUN | FAIL | NOT_COMPARED |
| DATAONE-TC241 | Two overhead pools — one pair each, with its own description and overl | P0 | AUTOMATED | NOT_RUN | FAIL | NOT_COMPARED |
| DATAONE-TC242 | Standard-cost product — pairs posted, no unit-cost uplift | P0 | AUTOMATED | NOT_RUN | FAIL | NOT_COMPARED |
| DATAONE-TC243 | Scrap move — no labour and no overhead pair | P0 | AUTOMATED | NOT_RUN | FAIL | NOT_COMPARED |
| DATAONE-TC244 | Rate freezing: stored_overhead_cost_settings written at _post_inventor | P0 | AUTOMATED | NOT_RUN | ERROR | NOT_COMPARED |
| DATAONE-TC245 | MO Overview: forecast overhead before completion, frozen-rate actual a | P1 | AUTOMATED | NOT_RUN | FAIL | NOT_COMPARED |
| DATAONE-TC246 | Pool rate changed after completion — the completed MO does not move | P0 | AUTOMATED | NOT_RUN | FAIL | NOT_COMPARED |
| DATAONE-TC247 | Work-centre time cap truncates the timesheet and the labour charge | P0 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |
| DATAONE-TC248 | Concurrent-timesheet guard still fires on v19 (the create list canary) | P0 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |
| DATAONE-TC249 | Analytic propagation: SO line → MO → every line of the valuation entry | P0 | AUTOMATED | NOT_RUN | FAIL | NOT_COMPARED |
| DATAONE-TC250 | Non-MTO MO carries no analytic distribution (the F174 negative) | P1 | AUTOMATED | NOT_RUN | FAIL | NOT_COMPARED |
| DATAONE-TC252 | Production consumption out of a tagged virtual production location | P0 | AUTOMATED | NOT_RUN | ERROR | NOT_COMPARED |
| DATAONE-TC253 | Two virtual locations in one move — the override bails out and tags no | P1 | AUTOMATED | NOT_RUN | ERROR | NOT_COMPARED |
| DATAONE-TC256 | Zero-quantity MO → ZeroDivisionError (live v17 defect E7) | P1 | AUTOMATED | NOT_RUN | FAIL | NOT_COMPARED |
| DATAONE-TC257 | BASELINE: top 20 v17 manufacturing orders reproduced to the cent | P0 | AUTOMATED | NOT_RUN | BLOCKED | BLOCKED |
| DATAONE-TC259 | BASELINE: analytic-distribution key shapes survive on those 40 entries | P0 | AUTOMATED | PASS | FAIL | REGRESSION_CANDIDATE |

## Failure notes (triage input)

- **DATAONE-TC048** [Odoo 19 → FAIL / ASSERTION] No differences vs v17 baseline: expected [], got ['balance/1/April 2025: baseline=None current=0.0', 'balance/1/April 2026: baseline=None current=0.0', 'balance/1/August 2025: baseline=None current=0.0', 'balance/1/December 2024: baseline=None current=0.0', 'b
- **DATAONE-TC234** [Odoo 19 → FAIL / ASSERTION] overhead pools in force: expected 1, got 7
- **DATAONE-TC235** [Odoo 19 → FAIL / ASSERTION] overhead pools in force: expected 1, got 7
- **DATAONE-TC236** [Odoo 19 → FAIL / ASSERTION] overhead pools in force: expected 1, got 7
- **DATAONE-TC237** [Odoo 19 → FAIL / ASSERTION] overhead pools in force: expected 1, got 7
- **DATAONE-TC238** [Odoo 19 → ERROR / AUTOMATION_ERROR] OdooRPCError: mrp.overhead.cost.setting.create failed: Percentage of overhead cost must be greater than 0
- **DATAONE-TC239** [Odoo 19 → FAIL / ASSERTION] button_mark_done was refused: expected True, got False
- **DATAONE-TC240** [Odoo 19 → FAIL / ASSERTION] overhead pools in force: expected 1, got 7
- **DATAONE-TC241** [Odoo 19 → FAIL / ASSERTION] overhead pools in force: expected 2, got 8
- **DATAONE-TC242** [Odoo 19 → FAIL / ASSERTION] labour lines: expected 2, got 0
- **DATAONE-TC243** [Odoo 19 → FAIL / ASSERTION] overhead pools in force: expected 1, got 7
- **DATAONE-TC244** [Odoo 19 → ERROR / AUTOMATION_ERROR] OdooRPCError: mrp.overhead.cost.setting.create failed: Percentage of overhead cost must be greater than 0
- **DATAONE-TC245** [Odoo 19 → FAIL / ASSERTION] overhead pools in force: expected 1, got 7
- **DATAONE-TC246** [Odoo 19 → FAIL / ASSERTION] the pool's rate and name were restored: expected True, got False
- **DATAONE-TC249** [Odoo 19 → FAIL / ASSERTION] overhead pools in force: expected 1, got 7
- **DATAONE-TC250** [Odoo 19 → FAIL / ASSERTION] overhead pools in force: expected 1, got 7
- **DATAONE-TC252** [Odoo 19 → ERROR / AUTOMATION_ERROR] OdooRPCError: stock.move.search_read failed: Invalid field 'scrapped' on 'stock.move'
- **DATAONE-TC253** [Odoo 19 → ERROR / AUTOMATION_ERROR] OdooRPCError: stock.move.create failed: Invalid field 'name' in 'stock.move'
- **DATAONE-TC256** [Odoo 19 → FAIL / ASSERTION] overhead pools in force: expected 1, got 7
- **DATAONE-TC259** [Odoo 19 → FAIL / ASSERTION] No differences vs v17 baseline: expected [], got ['invoices_captured: baseline=4 current=20', 'keys_with_1_account(s): baseline=None current=1001', 'keys_with_2_account(s): baseline=None current=523', 'lines_with_distribution: baseline=0 current=1046']
