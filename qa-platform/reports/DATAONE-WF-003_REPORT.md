# DATAONE-WF-003 Report — Quotation revision

Generated 2026-09-05 04:10 by `scripts/gen_reports.py` from persisted execution results (`data/results.db`) and the workbook-synced registry. Expected results are the workbook's, verbatim.

## Counts

- Test cases: **6**
- Automated (covered by platform tests): **6** of 6 automatable
- Manual-only: **0**
- Currently BLOCKED (either environment): **0**
- Odoo 17: PASS 0 / FAIL 6 / BLOCKED 0 / SKIPPED 0 / not executed 0
- Odoo 19: PASS 2 / FAIL 4 / BLOCKED 0 / not executed 0

## Cross-version classification

| Classification | Count |
|---|---:|
| SAME_BEHAVIOR | 0 |
| REGRESSION_CANDIDATE | 0 |
| FIXED | 2 |
| SAME_FAILURE | 4 |
| BLOCKED | 0 |
| NOT_COMPARED | 0 |

> REGRESSION_CANDIDATE is not a confirmed regression until failure triage; BLOCKED reflects the missing local Odoo 19 environment (see docs/ENVIRONMENT_STATUS.md).

## Per test case

| TC | Title | Prio | Automation | v17 | v19 | Classification |
|---|---|---|---|---|---|---|
| DATAONE-TC014 | The five OCA modules import and load on the v19 runtime | P0 | AUTOMATED | FAIL | FAIL | SAME_FAILURE |
| DATAONE-TC095 | Gate case: revision -01 created, source cancelled and archived, fields | P1 | AUTOMATED | ERROR | FAIL | SAME_FAILURE |
| DATAONE-TC096 | A second revision flattens the chain; the stat button lists all prior  | P1 | AUTOMATED | ERROR | PASS | FIXED |
| DATAONE-TC097 | The revision button appears only in sent and cancel | P2 | AUTOMATED | ERROR | PASS | FIXED |
| DATAONE-TC098 | The lineage uniqueness constraint and its exact message | P2 | AUTOMATED | ERROR | FAIL | SAME_FAILURE |
| DATAONE-TC338 | Re-import of an unconfirmed order creates a revision, cancels and arch | P0 | AUTOMATED | ERROR | FAIL | SAME_FAILURE |

## Failure notes (triage input)

- **DATAONE-TC014** [Odoo 19 → FAIL / ASSERTION] modules still using other removed APIs: expected {}, got {'base_tier_validation': ['models/tier_validation.py:272', 'tests/common.py:85', 'tests/test_tier_validation.py:598', 'tests/test_tier_validation.py:653', 'tests/test_tier_validation.py:709', 'tests/test
- **DATAONE-TC014** [Odoo 17 → FAIL / ASSERTION] modules still using removed odoo.api members: expected {}, got {'base_revision': ['models/base_revision.py:66']}
- **DATAONE-TC095** [Odoo 19 → FAIL / ASSERTION] revision chatter carries the notice: expected True, got "2 message(s); looking for 'New revision created: S06309-01'; bodies=['Sales Order created', 'New revision created from: S06309']"
- **DATAONE-TC095** [Odoo 17 → ERROR / AUTOMATION_ERROR] OdooRPCError: account.analytic.plan.search failed: Contact your administrator to request access if necessary.
- **DATAONE-TC096** [Odoo 19 → ERROR / AUTOMATION_ERROR] OdooRPCError: product.template.create failed: - delete: another model requires the record being deleted, you can archive it instead
- **DATAONE-TC096** [Odoo 17 → ERROR / AUTOMATION_ERROR] OdooRPCError: account.analytic.plan.search failed: Contact your administrator to request access if necessary.
- **DATAONE-TC097** [Odoo 19 → ERROR / AUTOMATION_ERROR] OdooRPCError: product.template.create failed: - delete: another model requires the record being deleted, you can archive it instead
- **DATAONE-TC097** [Odoo 17 → ERROR / AUTOMATION_ERROR] OdooRPCError: account.analytic.plan.search failed: Contact your administrator to request access if necessary.
- **DATAONE-TC098** [Odoo 19 → FAIL / ASSERTION] owning module: expected 'sale_order_revision', got 'Sale order revisions'
- **DATAONE-TC098** [Odoo 17 → ERROR / AUTOMATION_ERROR] OdooRPCError: account.analytic.plan.search failed: Contact your administrator to request access if necessary.
- **DATAONE-TC338** [Odoo 19 → FAIL / ASSERTION] SO-A chatter carries the notice: expected True, got '4 message(s)'
- **DATAONE-TC338** [Odoo 17 → ERROR / AUTOMATION_ERROR] OdooRPCError: account.analytic.plan.search failed: Contact your administrator to request access if necessary.
