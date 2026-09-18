# DATAONE-WF-021 — Cycle Counting and Inventory Adjustment · Automation Plan

| | |
|---|---|
| Workflow | `DATAONE-WF-021` |
| Build order | 13 (Inventory) |
| Effective risk | **HIGH** · fail mode **loud + silent** |
| Owns | 11 workbook test cases — **3 P0** (`TC174`, `TC177`, `TC251`) |
| Suite | `tests/wf021/` |
| Modules | `dto_cycle_count`; `dto_account` for `TC251` |
| Features | `DATAONE-F081`–`F085` (the approval half `F240`–`F250` is `[HOLD]`, descoped) |

## Result

| | Count |
|---|---:|
| Implemented | **11** |
| Blocked stub | 0 |
| Not implemented | 0 |
| **Total** | **11** |

No blocked stub is warranted anywhere in this suite. The workflow sheet's
*Integrations* section is literally **"None"**, `dto_cycle_count` ships no
cron, no server action, no record rule and no mail template, and the
*Notifications* section records that the descoped flow "posts nothing,
emails nothing and schedules no activity". Convention rule 4 is satisfied by
construction, not by a guard — `require_mail_offline` is deliberately unused
here.

## Scope

**In scope** — the five live features and the eleven cases that carry them:

| Feature | What it is |
|---|---|
| `F081` | Cycle-count categories (Levels A–E) and their intervals |
| `F082` | Auto-assign Level D to `Finished Goods` products |
| `F083` | Count rescheduling when an inventory adjustment is applied |
| `F084` | Re-schedule every quant when a product's level changes |
| `F085` | Cycle-count columns, filters and group-bys on products and quants |

**Out of scope**

- **The approval half** (`F240`–`F250`, `dto_tier_validation_quant`,
  `base_tier_validation`) — descoped. Measured on the target:
  `tier_definition`, `tier_review` and `tier_validation_exception` hold
  **0 rows** while `stock_quant.state` holds 628 `validate` + 2
  `inprogress`. The module is installed (its `state` and
  `valuation_discrepancy` columns exist) but **no definition matches**, so
  `need_validation` is always False and flow **A1** — "Apply is present and
  immediate" — is the live path. `common.py:require_no_tier_definition`
  probes that rather than assuming it, and **BLOCKS** if a definition
  appears, because the apply then happens inside the final approval and that
  path belongs to the APR suite. The four verbatim tier error strings are
  recorded as constants in `common.py` so a future APR suite need not
  re-derive them; **nothing in WF-021 asserts them**.
- **`dto_stock`** — the workbook names it as a primary module for WF-021.
  It is not one: `grep -rn "stock.quant|inventory_" dto_stock/models
  dto_stock/views` returns **zero hits**; the module contains
  `stock_picking.py`, `stock_picking_box.py` and `stock_scrap.py` only. No
  case in this suite asserts against it.
- **Back-dated apply** (`action_apply_inventory(date)`) — a NEW-suite P0 on
  v19. TC174's own notes say to *reference, not duplicate* it.
- **Performance** — Step 11 against a product with several thousand quants
  is PERF's (worst case on the target: 1,400 quants on one product, mean
  5.53 across 6,534 products).
- **Visual layout and column ordering** — the workbook assigns these to UIX
  explicitly in TC176's own notes.

**Assumptions** — each one probed, never taken on trust:

| Assumption | Probe |
|---|---|
| `dto_cycle_count` is contributing to the target | `require_cycle_count` |
| The five levels resolve by xmlid | `require_shipped_levels` |
| The acting user holds `stock.group_stock_manager` | `require_stock_manager` |
| No `tier.definition` targets `stock.quant` | `require_no_tier_definition` |
| A real-time-valuation category exists | `require_realtime_category` |
| `dto_account` contributes `location_analytic_distribution` | `require_location_analytic` |
| The server's own "today" | `server_today` — `default_get`, never the test host |

**Dependencies** — read-only PostgreSQL (`pg_*`) for `TC055` and `TC177`
step 12; configured on the target (`config/local.yaml:25-28`). `ctx.sql`
blocks by itself when absent and never falls back to a weaker assertion.

## The finding this suite exists to catch

`dto_cycle_count` carries the literal `type == 'product'` at **eight sites**,
and **Odoo 19 deleted that value**.

| | Odoo 17 | Odoo 19 |
|---|---|---|
| `product.template.type` | gains `('product','Storable Product')` via `selection_add` — `stock/models/product.py:661-663` | exactly `[('consu','Goods'),('service','Service'),('combo','Combo')]` — `product/models/product_template.py:54-65`; **no v19 addon re-adds `'product'`** |
| Storability | `type == 'product'` | `is_storable` — `stock/models/product.py:829-831` |
| `detailed_type` | present — `stock/models/product.py:658-660` | **deleted** |

The expressions still *evaluate*. `required="type == 'product'"` becomes
permanently false and `invisible="type != 'product'"` permanently true, and
both `_onchange_type` bodies stop firing. **BR-3 quietly stops being
enforced**: storable products save with no level, are never scheduled, and
the counting programme develops holes nobody can see. Nothing raises.

The eight sites, v17 (`main`):

| # | Site | Line | v17 expression | v19 port (working tree) |
|---|---|---|---|---|
| 1 | `views/product_product_views.xml` | `:10` | `invisible="type != 'product'"` | `invisible="not is_storable"` (`:18`) |
| 2 | `views/product_product_views.xml` | `:11` | `required="type == 'product'"` | `required="is_storable"` (`:20`) |
| 3 | `views/product_template_views.xml` | `:10` | `invisible="type != 'product' or …"` | `invisible="not is_storable or …"` (`:15`) |
| 4 | `views/product_template_views.xml` | `:11` | `required="type == 'product'"` | `required="is_storable"` (`:17`) |
| 5–6 | `models/product_product.py` | `:34`, `:41` | `if self.type != / == 'product':` | `@api.onchange('type','is_storable')`, keyed on `is_storable` (`:34-51`) |
| 7–8 | `models/product_template.py` | `:81`, `:88` | same | same (`:120-136`) |

`TEST-WF021-TC177` is the detector. It is the **one sanctioned
`ctx.env.version` exception** (`AUTOMATION_CONVENTIONS:143-149`) because its
subject *is* the delta: it computes the expected modifier expression per
version, so the v17 run **passes** (the v17 expressions are correct for v17,
which is what the workbook asks for) and only a genuine regression fails.

## The checkout trap — read before any source grep

```
$ git -C D:/Projects/dataone/DTO-Odoo rev-parse --abbrev-ref HEAD
UAT
```

`UAT` has merged `stage4/inventory-controls`, so the **working tree already
contains the v19 port** of `dto_cycle_count`:

- `__manifest__.py:10` → `'version': '19.0.0.0'`
- `models/stock_quant.py:23` → `def _apply_inventory(self, date=None)`
- `models/product_product.py:34` → `@api.onchange('type', 'is_storable')`
- `views/product_product_views.xml:18-20` → `invisible="not is_storable"`,
  `required="is_storable"`
- `views/cycle_count_category_views.xml:27` → `<list>`, `view_mode` `list`

**The v17 baseline is git history on `main`.** Every `main:` citation in
this document and in `tests/wf021/common.py` was read with
`git show main:project-addons/…` and cross-checked verbatim.

Consequence: a `framework.source_scan` grep of the checkout is **evidence
about the checkout, not about the running server**. `common.py:scan_cycle_count`
therefore returns the checked-out branch alongside its hits, and TC177
*reports* the scan while *asserting* the rendered arch. The authority on
what the target serves is `get_view` and `fields_get` —
`common.py:is_v19_product_shape` probes `product.template.is_storable`
directly, which cannot exist on a v17 core.

## Verified source facts

### `dto_cycle_count` (v17 = `git show main:project-addons/dto_cycle_count/…`)

| Fact | Where |
|---|---|
| `_name='cycle.count.category'`, `_order='id'` | `models/cycle_count_category.py:10,12` |
| `name` / `interval_number` / `interval_type` (`days`/`weeks`/`months`, default `days`) | `:14-20` |
| `_calculate_scheduled_count_date` — `ensure_one()`, today-fallback, `+ relativedelta(**{interval_type: interval_number})` | `:22-26` |
| The five shipped levels, `noupdate="1"`: A 1d, B 1w, C 1m, D 4m, E 6m | `data/cycle_count_category_data.xml:3, 5-33` |
| `product.product` — `cycle_count_category_id`, `last_count_date` (default today), `scheduled_count_date` | `models/product_product.py:13-15` |
| `_onchange_categ_id` — `if not level and categ_id.name == 'Finished Goods': → Level D` | `:20-23` |
| `_onchange_cycle_count_category_id` — writes only when **both** truthy (defect D-2, never clears) | `:25-29` |
| `_onchange_type` — clear on non-storable, restore from `self._origin` on storable | `:31-48` |
| `write()` — gate is `'cycle_count_category_id' in vals` (**key presence, not value change**), then `self.stock_quant_ids.sudo()` one quant at a time | `:53-61` |
| `create()` — `@api.model_create_multi`, repeats the Finished-Goods test per record | `:63-71` |
| `product.template` — the three fields are compute/inverse/search with **no `store=True`** (no SQL column) | `models/product_template.py:13-14, 17-20` |
| `variant_cycle_count_category_id` — `related='product_variant_id.cycle_count_category_id', store=True` — **the only stored template column** | `:15-16` |
| `_get_related_fields_variant_template()` appends the three names | `:99-102` |
| `stock.quant.cycle_count_category_id` — stored related → **a real column** | `models/stock_quant.py:13-14` |
| `stock.quant.last_count_date` — redefined `compute=False` → core's non-stored compute becomes **a plain writable Date column** | `:15` |
| `_apply_inventory()` — `super()`, then **four writes**: product `last_count_date` + `scheduled_count_date`, quant `last_count_date` + `inventory_date` | `:17-31` |
| ACL — exactly two rows: `base.group_user` `1,0,0,0`; `stock.group_stock_manager` `1,1,1,1` | `security/ir.model.access.csv:2-3` |
| Config surface — 9 views, 1 action, 1 menu, 2 ACL rows, **0 crons, 0 server actions, 0 record rules, 0 groups** (BR-7) | `__manifest__.py:24-42` |

### Core Odoo 17 — what the assertions land on

| Fact | Where |
|---|---|
| `_apply_inventory(self)` — **no `date` argument** on v17 | `stock/models/stock_quant.py:1050` |
| The manager gate, verbatim `'Only a stock manager can validate an inventory adjustment.'` | `:1051-1053` — **removed in v19** (`:996-1035`) |
| `action_apply_inventory(self)` — PUBLIC, returns a **wizard dict** (`stock.inventory.conflict` / `stock.track.confirmation`) instead of applying | `:445`, `:461-480`; reaches `_apply_inventory()` only at `:483` |
| **No zero-variance skip**: the `if/else` appends a `move_val` on both branches; the zero case is named `Product Quantity Confirmed` | `:1056-1066`, `:1265-1268` |
| `_apply_inventory` sets `inventory_date` from the location, then `action_clear_inventory_quantity()` — the DataOne override rewrites it afterwards | `:1071-1073` |
| `_is_inventory_mode()` = context key **and** `stock.group_stock_user` | `:1230-1235` |
| `_get_forbidden_fields_write()` — `inventory_quantity`, `last_count_date`, `inventory_date` are **not** restricted | `:360-362` |
| `inventory_diff_quantity = inventory_quantity - quantity`, stored | `:105-108`, compute `:189-192` |
| `inventory_quantity_auto_apply` carries `groups='stock.group_stock_manager'`; `inventory_quantity` has none | `:102-106`, `:99-101` |
| `cyclic_inventory_frequency` — **non-stored related, no column** | `:65` (v19 `:63`) |
| The count sheet is the `to_count` filter: `[('inventory_date','<=', context_today()…)]` | `stock/views/stock_quant_views.xml:37` (v19 `:39`) |
| `action_view_inventory()`'s own domain is only `[('location_id.usage','in',['internal','transit'])]` | `stock/models/stock_quant.py:435` |
| Unlinking a quant zeroes it and calls `_apply_inventory()` — re-entering the DataOne override | `:375-382` |
| `product.product.stock_quant_ids` = `One2many('stock.quant','product_id')` | `stock/models/product.py:29` (v19 `:50`) |
| `product.category.name` is `Char(index='trigram')` — **not translatable**, no unique constraint | `product/models/product_category.py:16` (v19 `:17`) |
| `property_stock_inventory` is `company_dependent=True` | `stock/models/product.py:668` |
| `onchange(values, field_names, fields_spec)` is PUBLIC; `value` carries only what changed | `odoo/models.py:7010`; `addons/web/models/models.py:895`, `:1086` |
| Private methods are undispatchable — `regex_private` → `AccessError` | `odoo/models.py:143-148` |

### `dto_account` — the TC251 carrier (v17 `main`)

| Fact | Where |
|---|---|
| `stock.location` gains `analytic.mixin` + `location_analytic_distribution = fields.Json(...)` | `models/stock_location.py:7-11` |
| `_account_entry_move(qty, description, svl_id, cost)` — **private**; bails when `len(virtual_locations) != 1` or no distribution; tags only lines whose account is `valuation_in_account_id` **or** `valuation_out_account_id` | `models/stock_move.py:24-46` (bail `:32-33`, test `:40`) |
| Decrease (`_is_out`) → counterpart is `location_dest_id.`**`valuation_in_account_id`** | `stock_account/models/stock_move.py:395-399`, posted at `:591` |
| Increase (`_is_in`) → counterpart is `location_id.`**`valuation_out_account_id`** | `:392-393`, posted at `:584` |
| Exactly two lines: `credit_line_vals` + `debit_line_vals` | `:441-478` |
| Early bail `if self.product_id.type != 'product': return []` | `:567-569` |
| `stock.location.valuation_in/out_account_id` | `stock_account/models/stock_location.py:10-23` |

## Per test case

| Group | Workbook TCs | Platform tests | What is proven |
|---|---|---|---|
| Levels and assignment | `TC169`–`TC173` | `tests/wf021/test_cycle_count_levels.py` | The five shipped intervals and the no-last-count fallback; Level D on the form and through `create()` with a list; the never-overwrite guard and the exact-string fragility; the required-level rule as a view modifier the ORM does not enforce; the pre-save scheduled date and its `force_save` persistence |
| Apply and re-schedule | `TC174`–`TC177` | `tests/wf021/test_cycle_count_apply.py` | **The gate**: all four date writes, the variance move line, the count-sheet behaviour, the zero-variance case; one level write rewriting every quant; the columns, search fields and group-bys; the v19 `type == 'product'` detector |
| Location analytic | `TC251` | `tests/wf021/test_inventory_adjustment.py` | Two lines, the valuation line untagged, the counterpart tagged in **both** directions, the untagged-location bail-out |
| Reconciliation | `TC055` | `tests/wf021/test_reconciliation.py` | The programme's whole state — levels, assignments, scheduling — captured on v17 and diffed on v19 |

### Feasibility decisions

| tc_id | Pri | Kind | Decision | Why |
|---|---|---|---|---|
| `TC055` | P1 | DATA | **implemented** | Read-only SQL + `reconcile()`; `pg_*` configured. Three workbook statements corrected against the real schema (below); the expected result — "all diffs empty" — untouched |
| `TC169` | P1 | API | **implemented** | Shipped data by xmlid + the arithmetic through the public `onchange`. Step 12's direct private call re-expressed, not blocked |
| `TC170` | P1 | API | **implemented** | `onchange` is RPC-public. Step 9's rename re-expressed as a namespaced duplicate named `"Finished Goods "` |
| `TC171` | P1 | DATA | **implemented** | `create()` with a list is an ORM primitive. Step 8 asserts the **actual** template-with-variant outcome |
| `TC172` | P1 | HYBRID | **implemented** | UI half on the rendered arch; the browser save-refusal is client-side and has no server string |
| `TC173` | P1 | API | **implemented** | Fully deterministic — every date supplied. Displayed **and** stored both asserted |
| `TC174` | **P0** | API | **implemented** | **The gate.** Four writes, variance move, count sheet, zero variance. Dates relational; A3 corrected |
| `TC175` | P1 | API | **implemented** | Steps 1–8, 10 direct; step 9 re-expressed; step 11 assert-or-block on a runtime group resolution |
| `TC176` | P2 | HYBRID | **implemented** | Arch + `read_group`; visual layout is explicitly UIX's. First to cut if effort is constrained |
| `TC177` | **P0** | API | **implemented** | Sanctioned `ctx.env.version` exception — the subject *is* the delta |
| `TC251` | **P0** | API | **implemented** | Private hook, public outcome. Ownership confirmed below |

### Shared test case — ownership resolved

`TC251` names both `DATAONE-WF-008` and `DATAONE-WF-021`.
`AUTOMATION_CONVENTIONS`, "Shared test cases": the case is written once, in
the suite of the workflow with the lowest build order in scope. The synced
registry already records the answer:

```
data/test_registry.json → DATAONE-TC251
  owning_workflow : DATAONE-WF-021
  shared_with     : ['DATAONE-WF-008']
```

`scripts/sync_registry.py:owning_workflow` ranks WF-021's build order 13
ahead of WF-008, which is not in the current scope extract (rank 999).
**WF-021 writes it**; WF-008 references the same `tc_id` and does not
re-implement it.

## Workbook corrections

Expected *results* are immutable (hard rule 2). What is corrected below is
only source material that is **factually wrong against the real schema or
the real source** — statements that would raise, or name the wrong object.
Each correction is repeated in the owning test's docstring.

1. **`TC055` step 3** — `stock_quant.cyclic_inventory_frequency` is a
   non-stored `related` (v17 `stock/models/stock_quant.py:65`, v19 `:63`)
   and has **no column**; selecting it raises `UndefinedColumn`. Dropped
   from the query.
2. **`TC055` step 4** — `product_template.cycle_count_category_id`,
   `last_count_date` and `scheduled_count_date` are compute/inverse/search
   with no `store=True` (`models/product_template.py:13-20`) and have **no
   columns**. The step's own parenthetical asks where the level lives; the
   answer is **`product_product.cycle_count_category_id`** (stored),
   mirrored by the stored `product_template.variant_cycle_count_category_id`
   and by `stock_quant.cycle_count_category_id`. The corrected query joins
   through `product_product`.
3. **`TC055` step 5** — `product_category.name` is not translatable in v17
   (`product/models/product_category.py:16`) or v19 (`:17`), so the column
   is `varchar` and `name->>'en_US'` raises. Compared as plain text, which
   is exactly what BR-4's Python `==` does.
4. **`TC055` step 3, volume** — the workbook dumps one row per quant;
   `stock_quant` holds **36,147** rows. The per-quant dump becomes a CSV
   **artifact** and the diffed value is the aggregate, which carries the
   same information at the granularity a diff can report.
5. **`TC174` step 15 (flow A3)** — v17 has **no zero-variance skip**: the
   `if/else` on `float_compare(inventory_diff_quantity, 0) > 0` appends a
   `move_val` on **both** branches (`stock/models/stock_quant.py:1056-1066`)
   and `_get_inventory_move_values` names the zero case
   `Product Quantity Confirmed` (`:1265-1268`). A zero-variance count **does**
   create a zero-quantity `stock.move.line` on v17. v19 adds exactly one
   skip, only under `context['from_inverse_qty']` (`:1007-1010`), which this
   path never sets. The clause this workflow owns — "the next count is still
   booked" — holds and is asserted.
6. **`TC251` step 8** — for a **decrease** the counterpart is
   `valuation_in_account_id`, not `valuation_out_account_id`
   (`stock_account/models/stock_move.py:395-399`). `valuation_out_account_id`
   is step 11's **increase** case (`:392-393`). The fixture sets **both**,
   because `dto_account` tags a line whose account is either
   (`models/stock_move.py:40`) — a fixture setting one passes step 8 and
   silently produces an untagged line at step 11.
7. **`TC176` step 6** — the `product.product` search `filter_domain` is
   `[('name', 'ilike', self)]` (`views/product_product_views.xml:25`): it
   searches the **product's own name**, not the category. Defect **D-new-6**,
   deliberately preserved by the port. The attribute is asserted literally;
   no category-name search is claimed to work through it.
8. **Workflow sheet, `dto_stock` named as a primary module** — it contains
   no quant or inventory-adjustment code at all.
9. **Workflow sheet, v19 item 9** (`read_group`, `res.users.groups_id`,
   `res.groups.users`) — `dto_cycle_count` touches none of them; they break
   `base_tier_validation` only, which is descoped.
10. **Workflow sheet, v19 item 8** (`stock.quant.package` →
    `stock.package`) — present in the **core** quant views both DataOne
    modules inherit, but neither module's own xpaths reference
    `package_id`. Not a WF-021 break.

## `[UNVERIFIED]` claims and what would settle each

| Claim | Status | What would validate it |
|---|---|---|
| **`TC251` step 10** — "an `account.analytic.line` exists for CC 202000 of 50.00" | `[UNVERIFIED]`, and likely **false as written**. `_prepare_analytic_lines` reads `self.stock_valuation_layer_ids.account_move_id.line_ids.filtered(lambda l: l.account_id == account_valuation)` (`stock_account/models/stock_move.py:433-435`) — the **valuation** line, which this override deliberately leaves untagged | Run the case and read `account.analytic.line` for the fixture's analytic accounts. The test **records** what it finds and does not assert a value the source does not support. If no analytic line exists, that is a finding for **WF-008**, not a test defect |
| **Which `dto_cycle_count` copy the running server at :8076 serves** — `main` (v17) or `UAT` (the v19 port) | `[UNVERIFIED]` by inspection. It cannot be the v19 code on a v17 core (`is_storable` does not exist in v17 `stock`), so it is almost certainly a v17 checkout or a separate deployment | Probed at runtime, not assumed: `common.py:is_v19_product_shape` calls `rpc.field_exists("product.template", "is_storable")` — False on a true v17 target |
| **Whether `admin` (uid 2) holds `stock.group_stock_manager` on `dto_17`** | `[UNVERIFIED]` | Probed by `require_stock_manager`, which BLOCKS with the verbatim v17 `UserError` string and its file:line if not |
| **Which non-stock-manager group grants `product.product` write on this target** | `[UNVERIFIED]` — it differs by version (v17 grants `stock.group_stock_manager` 1,1,1,1 at `stock/security/ir.model.access.csv:21-22`; **v19 deletes both rows**) | Resolved at runtime from `ir.model.access` by `common.py:non_manager_product_writer`. If none exists, **TC175 step 11 alone** blocks with a message naming what the target actually grants |
| **v19's first-class `Domain` handling of `ilike` against a Many2one** routed through a custom `_search` | `[UNVERIFIED]` for v19 | Re-verify on a v19 instance. Works on v17: on `stock.quant` the target is a stored m2o (core resolves `ilike` against the comodel's `_rec_name`); on `product.template` it routes through `_search_cycle_count_category_id` (`models/product_template.py:46-50`) |
| **Whether the count sheet is actually worked from `inventory_date` in practice** | `[UNVERIFIED]` — workflow-sheet Open Question 3 | Ask the warehouse supervisor. Not automatable, and it does not change any assertion: the module's job is keeping the date correct either way |

Two claims the source-verification report left `[UNVERIFIED]` were **closed
during this pass** and are now asserted as fact:

- **`TC177` step 11** — "`super()._onchange_type()` still exists in v19".
  **Verified**: core `product.template._onchange_type` is present in both
  versions — v17 `product/models/product_template.py:459` +
  `stock/models/product.py:861`; v19 `product/models/product_template.py:460`
  + `stock/models/product.py:1089`.
- **v19 re-adds `'product'` to the type selection somewhere.** **Verified
  false**: `grep -rn "selection_add=\[.*'product'" addons/*/models/*.py` over
  `D:/Projects/odoo-19.0` returns **zero hits**.

## v17 vs v19 deltas that affect this suite

| Concern | Odoo 17 | Odoo 19 | How the suite handles it |
|---|---|---|---|
| Storable product | `type='product'` (`stock/models/product.py:661`) | `type='consu'` + `is_storable` (`:829`) | `ctx.adapter.storable_product_values()` via `common.storable_values`. **TC177 is the exception** — its subject is this delta |
| `_apply_inventory` signature | `(self)` — `stock/models/stock_quant.py:1050` | `(self, date=None)` — `:996` | TC174 asserts dates **relationally**; back-dated apply is NEW's |
| Stock-manager gate on apply | present, `:1051-1053` | **removed** | `require_stock_manager` probes on both |
| Zero-variance | no skip, `:1056-1066` | one skip, only under `from_inverse_qty` (`:1007-1010`) | A3 correction, documented in TC174's docstring |
| `stock.group_stock_manager` on `product.*` | `1,1,1,1` — `stock/security/ir.model.access.csv:21-22` | **rows deleted**; only `stock.group_stock_user` `1,0,0,0` survives (`:15-16`) | Why the port added `.sudo()` at `models/stock_quant.py:58`; TC175 step 11 resolves the writer group at runtime |
| List view tag / type | `tree` (`ir_ui_view.py:163`) | `list` (`:149`) | `fg_common.list_tag` / `adapter.list_view_type` via `common.arch_of`, `common.list_root_tag` |
| `res.users` groups m2m | `groups_id` (`res_users.py:384`) | `group_ids` (`:257`) | `ctx.adapter.user_groups_field` via `common.ensure_wf021_user` |
| Product group-by anchor | `<filter name="categ_id">` — `product/views/product_views.xml:193` | **renamed** `group_by_categ_id` — `:267`; **zero** `filter name="categ_id"` remain anywhere in v19 | TC176's expectation is anchor-aware. The rename is **loud** — the view fails to load — so it cannot be missed |
| Traceability anchor | `stock/views/product_views.xml:126` | `:221`, now also `invisible="tracking == 'none'"` | TC176 asserts group **presence and order**, not the anchor's own attributes |
| Inventory list root | `<tree … editable="bottom">`, no `multi_edit`; header Apply carries `groups="stock.group_stock_manager"` — `stock/views/stock_quant_views.xml:415,421` | `<list … multi_edit="1">` `:278`; header Apply has **no `groups`** `:285`; adds `action_apply_all` `:280-284` | Arch assertions are scoped to the module's own injected nodes |
| `dto_account` valuation hook | `_account_entry_move` — `models/stock_move.py:24` | **does not exist**; hook moved to `_get_account_move_line_vals()` | TC251 is expected to ERROR on v19 until `dto_account` is ported — **loud at `super()`** |
| `stock.location` valuation accounts | two: `valuation_in/out_account_id` | folded into one `valuation_account_id` (`stock_account/models/stock_location.py:11`) | TC251's fixture sets both on v17; the v19 shape is a port task, not a test adaptation |
| `base_tier_validation` | v17 `17.0.2.1.3`, installed | **no OCA 19.0 port exists** | Descoped; no case depends on it |

## Expected outcome per test

| Test | v17 | v19 |
|---|---|---|
| `TEST-WF021-TC055` | **PASS** (baseline captured) | BLOCKED until an instance exists; then PASS unless the programme's state moved |
| `TEST-WF021-TC169` | **PASS** | PASS — the arithmetic is pure Python; a FAIL means the shipped data changed |
| `TEST-WF021-TC170` | **PASS** | PASS if the port keeps the literal compare; a step-9 FAIL means BR-4 was re-implemented, a deliberate change to record |
| `TEST-WF021-TC171` | **PASS** | PASS — the A4 gap and the list handling are both unchanged by the port |
| `TEST-WF021-TC172` | **PASS** — the modifier is present *and* the ORM leak is real, which is exactly the baseline the workbook wants | PASS only if the port reworked the modifiers to `is_storable`; the un-ported form is TC177's subject |
| `TEST-WF021-TC173` | **PASS** | PASS unless v19 changed `force_save` on a readonly field — the divergence only the displayed-**and**-stored pair catches |
| `TEST-WF021-TC174` | **PASS** — the gate the workflow is accepted on | PASS on the state; the valuation half is rewritten code, so test the money, not the mechanism |
| `TEST-WF021-TC175` | **PASS** (step 11 may report BLOCKED alone if no non-manager product-writer group exists) | PASS unless v19's recompute ordering flushes the quant's related level after the loop reads it — the full before/after map reports which quants carry the old interval |
| `TEST-WF021-TC176` | **PASS** | PASS only after the port re-anchors `//filter[@name='categ_id']`; that rename is loud |
| `TEST-WF021-TC177` | **PASS** — the v17 expressions are correct *for v17*, which is what the workbook asks ("run on v17 first to establish that the case passes there"). The expectation is computed per version, so **no `EXPECTED v17 OUTCOME: FAIL` docstring is warranted** | BLOCKED until an instance exists. Then PASS only if the type/`is_storable` rework was done across all eight sites; any FAIL is the silent defect and the failing site is named |
| `TEST-WF021-TC251` | **PASS** for steps 1–9, 11, 12. Step 10 is `[UNVERIFIED]` and **recorded, not asserted** | **ERROR** until `dto_account` is ported — `_account_entry_move` does not exist in v19. Once rebuilt the risk turns silent: the tag lands on the wrong line, both lines, or neither, which steps 7, 8 and 11 exist to separate |

No test in this suite carries an `EXPECTED v17 OUTCOME: FAIL` docstring.
Every case's expectation is either version-neutral or computed per version,
so a v17 failure is a real finding rather than a known-failing baseline.

## Safety notes

- **Never modified**: `product_category` id 10 (`Finished Goods`, 7,915
  Level-D variants), the five shipped `cycle.count.category` rows, any
  pre-existing quant, product, location or account. All live-data checks
  (`TC055`, `TC177` step 12) are read-only SQL. TC170's fragility probe
  creates a **namespaced duplicate** category rather than renaming the live
  one.
- **This suite creates no `cycle.count.category`** — it uses the shipped
  five by xmlid.
- **Quants resist clean teardown**: `_unlink_except_wrong_permission`
  (`stock/models/stock_quant.py:375-382`) zeroes `inventory_quantity` and
  calls `_apply_inventory()`, re-entering the DataOne override — which
  raises `Expected singleton` for a levelless product. `sweep_wf021`
  attempts the unlink and lets it fail; what survives is token-scoped and
  cannot collide with the next execution. `safe_sweep` is the `finally:`
  form that can never raise.
- **Nothing reaches an external system.** No mail, no SFTP, no PrintNode, no
  cron, no queue job. `ensure_wf021_user` passes `no_reset_password` so not
  even a welcome email is composed.
- **Fixtures never depend on each other.** TC173's "leave as-is for TC174"
  postcondition is deliberately not honoured (convention rule 5); every case
  builds and sweeps its own namespace.

## Run

```
venv/Scripts/python.exe -c "from framework import registry; print(len(registry.discover()))"
```
