# DATAONE-WF-010 Report — MO Test-Result Attachment Import ("Production" data type)

Generated 2026-09-18 17:41 by `scripts/gen_reports.py` from persisted execution results (`data/results.db`) and the workbook-synced registry. Expected results are the workbook's, verbatim.

## Counts

- Test cases: **7**
- Automated (covered by platform tests): **7** of 7 automatable
- Manual-only: **0**
- Currently BLOCKED (either environment): **1**
- Odoo 17: PASS 0 / FAIL 0 / BLOCKED 0 / SKIPPED 0 / not executed 7
- Odoo 19: PASS 1 / FAIL 5 / BLOCKED 1 / not executed 0

## Cross-version classification

| Classification | Count |
|---|---:|
| SAME_BEHAVIOR | 0 |
| REGRESSION_CANDIDATE | 0 |
| FIXED | 0 |
| SAME_FAILURE | 0 |
| BLOCKED | 1 |
| NOT_COMPARED | 6 |

> REGRESSION_CANDIDATE is not a confirmed regression until failure triage; BLOCKED reflects the missing local Odoo 19 environment (see docs/ENVIRONMENT_STATUS.md).

## Per test case

| TC | Title | Prio | Automation | v17 | v19 | Classification |
|---|---|---|---|---|---|---|
| DATAONE-TC018 | Every third-party Python import used by custom code is importable and  | P2 | AUTOMATED | NOT_RUN | FAIL | NOT_COMPARED |
| DATAONE-TC344 | GATE: the verbatim docstring sample, matched by tier 3, both records s | P1 | AUTOMATED | NOT_RUN | FAIL | NOT_COMPARED |
| DATAONE-TC345 | Tier 1: matched via stock.lot.custom | P1 | AUTOMATED | NOT_RUN | PASS | NOT_COMPARED |
| DATAONE-TC346 | Tier 2: matched via lot_producing_id exactly | P1 | AUTOMATED | NOT_RUN | ERROR | NOT_COMPARED |
| DATAONE-TC347 | No match: the failure lists the part and the serial, no activity on an | P2 | AUTOMATED | NOT_RUN | FAIL | NOT_COMPARED |
| DATAONE-TC348 | Malformed file: the exact Cannot extract product info from file conten | P2 | AUTOMATED | NOT_RUN | FAIL | NOT_COMPARED |
| DATAONE-TC349 | v19: a trailing empty line shifts rows[-1] and attaches evidence to th | P0 | AUTOMATED | NOT_RUN | BLOCKED | BLOCKED |

## Failure notes (triage input)

- **DATAONE-TC018** [Odoo 19 → FAIL / ASSERTION] every third-party package the custom code imports is declared in some module's external_dependencies (the workbook's step 3 expectation: empty, or each remaining line justified): expected [], got ['Level', 'PIL', 'a', 'account', 'dateutil', 'lxml', 'markupsafe
- **DATAONE-TC344** [Odoo 19 → FAIL / ASSERTION] the complete stored-field dump is unchanged, excluding the mail-mixin counters and write_date: expected {}, got {'have_attachment': {'before': False, 'after': True}}
- **DATAONE-TC346** [Odoo 19 → ERROR / AUTOMATION_ERROR] OdooRPCError: mrp.production.write failed: You cannot set more than 1 lot
- **DATAONE-TC347** [Odoo 19 → FAIL / ASSERTION] the message opens a <ul> and never closes it — mrp_attachment_transformer.py:64-69 ends the f-string after the second <li>. It renders acceptably in most browsers and is still malformed; E2, recorded for the port: expected True, got '2 open, 2 closed'
- **DATAONE-TC348** [Odoo 19 → FAIL / ASSERTION] the control MO received nothing: expected [], got [{'id': 137271, 'name': 'WF010_M4_single_row.csv [60cc39]', 'res_model': 'mrp.production', 'res_id': 48018, 'file_size': 66, 'mimetype': 'text/csv'}]
