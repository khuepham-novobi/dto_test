# DATAONE-WF-003 — Quotation revision · Automation Plan

| | |
|---|---|
| Workflow | `DATAONE-WF-003` — Quotation revision |
| Build order | 3 (Stage 1 — easiest entry points) · estimate 15 h |
| Effective risk | **CRITICAL** |
| Owns | 6 workbook test cases |
| Suite | `tests/wf003/` |
| Modules | `base_revision`, `sale_order_revision` (OCA), `dto_sale`, `dto_sale_workday`, `base_tier_validation`, `queue_job`, `stock_picking_auto_create_lot` |
| Source | `DataOne_v19_Test_Suite_and_Workflows_v1.0.xlsx` / `Automation Export` |

## Result

| | Count |
|---|---:|
| Implemented | **5** |
| Blocked stub | **1** |
| Not implemented | 0 |
| **Total** | **6** |

## Per test case

| Workbook TC | Prio | Type | Platform test | Fixtures | Key assertions | EXPECTED v17 | Evidence |
|---|---|---|---|---|---|---|---|
| `DATAONE-TC014` | P0 | ORM_INTEGRATION | `TEST-WF003-TC014` | none — reads the source tree + the target's ORM | removed-`odoo.api` scan clean for all five OCA modules; other-removed-API scan zero; no legacy OWL global / jQuery in `base_tier_validation`; the three RMA fields on `stock.picking`; `rma_number` sequence prefix `%(year)s-` padding 3 | **FAIL at step 1** | `tc014_scans.json` (all scan hits, written before the first assertion) |
| `DATAONE-TC095` | P1 | FUNC | `TEST-WF003-TC095` | quotation + partner + product + analytic account, all token-namespaced | `-01` zero-padded name; revision `draft`/`active`/`revision_number 1`/`unrevisioned_name` unchanged; `order_type`, `client_order_ref`, `analytic_account_id`, `tariff_amount` equal **by value**; source `cancel` **and** `active False` pointing at the revision; notice on both chatters | PASS | execution log |
| `DATAONE-TC096` | P1 | FUNC | `TEST-WF003-TC096` | rebuilds the one-revision lineage, then revises again | `old_revision_ids` = both priors (flattened); `revision_count == 2`; `has_old_revisions`; both priors → `-02`; stat action `active_test 0` + `default_current_revision_id`; `fa-file-archive-o` + `statinfo` in the composed arch; exactly one active draft in the lineage | PASS | execution log |
| `DATAONE-TC097` | P2 | UI | `TEST-WF003-TC097` | four orders, one per state; disposable confirmed order for steps 5–6 | button present in the composed arch with label and `type=object`; visible in `sent`/`cancel` only, from its own `invisible` modifier; `create_revision()` on a **confirmed** order succeeds (no Python guard) and leaves it `cancel` + `active False` | PASS | execution log (picking count behind the cancelled order) |
| `DATAONE-TC098` | P2 | NEG | `TEST-WF003-TC098` | rebuilds the three-member lineage | constraint `sale_order_revision_unique` is `u`, owned by `sale_order_revision`, columns `unrevisioned_name, revision_number, company_id`, message `Order Reference and revision must be unique per Company.`; collision rejected with **that** message and not the base one; `revision_number 3` accepted | PASS | execution log |
| `DATAONE-TC338` | P0 | FUNC | `TEST-WF003-TC338` | real lineage built through the public `create_revision` | revision stack (E5); `internal_memo`; the import's exact match domain resolving to the newest revision; source `cancel`+`archived`; stat button → SO-A; both chatters; `imported_from_workday` `copy=False`; **no active** `workday_requisition` SFTP folder | **BLOCKED** after the offline assertions | execution log |

## Adaptations (documented, not assertion-weakening)

1. **Chained fixtures unchained.** The workbook passes a lineage from TC095 → TC096 → TC098 ("leave both in place for TC096"). Convention rule 5 forbids one test depending on another's fixtures, so TC096 and TC098 rebuild the lineage they need with their own execution token. No assertion changed.
2. **Sweeps scope on `origin`, not `name`.** `sale.order.name` is left to the `ir.sequence` because `unrevisioned_name` is derived from it in `base_revision.create()`, and the `-01` naming rule is what the tests assert. The `WF003 …[token]` marker therefore lives in `origin` and `client_order_ref`. Sweeps include `active in (True, False)` because a revised source is archived.
3. **Button visibility asserted from the arch, not a browser.** TC097 steps 1–4 read the composed form arch through `get_view()` and evaluate the button's own `invisible` modifier per state. This detects the workbook's stated v19 risk — the priority-15 inherit failing to load because its `//button[@name='action_view_invoice']` anchor rotted — at the same point a tour would.
4. **The constraint read through `ir.model.constraint`.** TC098 step 1 uses the ORM reflection table rather than `pg_constraint`, so the test needs no PostgreSQL credentials and never reports BLOCKED for a missing `pg_*` config.
5. **`information_schema` replaced by ORM introspection.** TC014 step 5 uses `field_exists` on `stock.picking` and a search on `ir.sequence` instead of the workbook's SQL, for the same reason.

## Version notes

Verified against `D:\Projects\dataone\odoo-17.0` and `D:\Projects\odoo-19.0`:

| Fact | Where |
|---|---|
| `@api.returns` on `copy()` — removed from `odoo.api` in v19 | `base_revision/models/base_revision.py` |
| `_compute_revision_count` calls the public `read_group()` and reads `x["current_revision_id_count"]` | `base_revision/models/base_revision.py:47-52` |
| `create_revision()` returns `"view_mode": "tree,form"` — no longer valid in v19 | `base_revision/models/base_revision.py` (logged as evidence in TC095, not asserted — the workbook's expected result does not cover it) |
| `_sql_constraints` merged by key over `reversed(__base_classes)`, so `sale_order_revision`'s three-column version wins | `odoo/models.py:819` (v17) |
| Constraint reflected into `ir.model.constraint` with definition, message and module | `odoo/addons/base/models/ir_model.py:1826` |
| `_prepare_revision_data` adds `state='cancel'` on top of `active=False` | `sale_order_revision/models/sale_order.py` |
| Button modifier `invisible="state not in ['cancel' ,'sent']"`, inherit `priority=15`, stat button anchored on `//button[@name='action_view_invoice']` | `sale_order_revision/view/sale_order.xml` |
| `order_type` is `required=True` with no default; `client_order_ref` and `analytic_account_id` are re-declared `copy=True` | `dto_sale/models/sale_order.py:17,33,34` |
| `imported_from_workday` is `copy=False` | `dto_sale_workday/models/sale_order.py:19-22` |
| Import match domain `name = memo OR name like 'memo-%'`; revision only when `state != 'sale'`; update mode writes `partner_shipping_id`, never `partner_id` | `dto_sale_workday/models/sale_order.py:236-247` |

## What this suite does NOT cover

- Steps 3, 4 and 7 of TC014 — the v19 importlib probe, the scratch-database install and the asset re-build. They need a v19 server and database create/drop rights; run them from the v19 build pipeline.
- The Workday ETL round trip (TC338 steps 2–5, 9, 12–14, 17): line reconciliation across the three branches, zero/negative price carry-forward, the `partner_id` vs `partner_shipping_id` rule and the `sftp.file` Done state. All behind private methods — write them as an in-process `TransactionCase` in `dto_sale_workday`, or drive a mocked SFTP sandbox.
- Whether a Python guard *should* be added to `create_revision()` (TC097 steps 5–6 demonstrate the gap). That is WF-003's open question and a business decision.

## Blocking dependency

Workbook precondition **E5** governs the whole workflow on v19: OCA 19.0 branches of `base_revision` and `sale_order_revision` must exist. Without them `dto_sale_workday` does not import, and WF-001 and WF-003 are both dead. Every test in this suite calls `require_revision_stack(ctx)` and reports BLOCKED with that reason rather than failing obscurely.

## Run

```bash
venv/Scripts/python.exe -c "from framework import registry; print(len(registry.discover()))"
```
