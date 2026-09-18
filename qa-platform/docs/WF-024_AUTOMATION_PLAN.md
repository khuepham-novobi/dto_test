# DATAONE-WF-024 — RMA: Customer and Vendor Returns · Automation Plan

| | |
|---|---|
| Workflow | `DATAONE-WF-024` |
| Build order | 15.0 (workbook sheet) · Stage 4 — inventory movement, receipts and controls · estimate **16 h** |
| Effective risk | **CRITICAL** · fail mode **loud + silent** |
| Depends on | WF-011, WF-015 |
| Owns | 8 workbook test cases — **3 P0**, 4 P1, 1 P2 |
| Suite | `tests/wf024/` |
| Module | `stock_picking_auto_create_lot` (a forked AGPL OCA module with the whole DataOne RMA feature bolted in) |

## Result

| | Count |
|---|---:|
| Implemented | **7** |
| Blocked stub | **1** (TC186) |
| Not implemented | 0 |
| **Total** | **8** |

**TC186 is a blocked stub, not an implemented case.** Its test asserts
twelve observable facts and then ends in `ctx.blocked` (workbook steps 4–5
are the web client's evaluation of `required="True"` and no RPC path can
observe them). `framework/context.py:154-156` raises `BlockedTest`, so the
platform records the **whole case BLOCKED** — it can never report PASSED.
Counting it as implemented made this plan and the registry result disagree.
See adaptation 8 and the note for the conventions owner beneath it.

**TC187 is implemented, with a MANUAL half that is logged, not blocked.**
The byte-level `Content-Disposition` filename and the measured page size of
the produced PDF need wkhtmltopdf; the test records them with `ctx.log` in
steps 4 and 13 and never attempts `/report/pdf`, so nothing in TC187 calls
`ctx.blocked` for the PDF.

Three cases carry an **expected v19 failure** that is the finding, not a
defect in the test (TC184 step 4, TC187's render half, TC188 step 8). One is
expected to fail **by design on any rebuilt database** (TC190 step 4).

**One open decision for the conventions owner: TC185 writes a pre-existing
business record** (`res.company.vendor_refund_narration`). AUTOMATION_CONVENTIONS
hard rule 3 forbids that outright and has no sanctioned-mutation clause, so
this is an **exception awaiting approval**, not an adaptation — see
adaptation 7.

## Scope

**In scope.** The DataOne RMA half of `stock_picking_auto_create_lot`: the
`rma_number` sequence and its format, the vendor-refund narration copied onto
the return's note, the `reason_for_return` / `return_notes` pair and their
view modifiers, the `do_print_picking` report swap, the RMA menu and the
three act_window queues, and the Return-and-Replenish money leg.

**Out of scope.**

- The upstream OCA auto-lot half (F086) — `_set_auto_lot`,
  `product.auto_create_lot`, `stock.picking.type.auto_create_lot`. It has the
  module's only shipped tests and belongs to the auto-lot workflow.
- The vendor credit note carrying the same narration (F156) — that is
  `account.move._compute_narration` in `dto_account` and belongs to
  **WF-016**. This suite stops at the picking.
- The Workday vendor-bill export question (credit notes are `in_refund` and
  the export filters `in_invoice`) — Finance / WF-020.
- Layout fidelity and page-size measurement of the produced PDF — UIX, and
  MANUAL on the first pass exactly as the workbook's "Wave 1 + Manual
  (split)" states.
- Production data questions: do ids 4 and 5 in the live `dataone` database
  really mean Partners/Vendors and Partners/Customers; how many RMAs exist
  per year; are zero-priced replacement lines reconciled. All Phase-0a, all
  answered by `database/DATAONE-EVIDENCE-PACK.sql`, none part of a case.

**Assumptions.** The QA target is a dedicated `_qa` clone with every
`ir.mail_server` deactivated; `stock_picking_auto_create_lot`, `dto_account`,
`dto_sale`, `dto_sale_stock` and the `quality_control` / `dto_purchase_stock`
pair are installed. Each of those is **probed**, never assumed — see
*Environment dependencies* below.

**Dependencies.** TC190 must be executed on a **freshly rebuilt** database,
not on the production clone; that is the workbook's own precondition and the
whole point of the case.

## Correction to the workbook, carried into the suite

Workflow step 5 and TC188 step 3 say the RMA menu "exposes three actions".
**It does not.** `views/stock_picking.xml:138-140` defines exactly **one**
`menuitem` (`rma_picking`), bound to `action_picking_tree_rma`.
`action_picking_tree_rma_customer` (`:81`) and
`action_picking_tree_rma_vendor` (`:102`) are orphan `act_window` records
with no menu entry and no binding anywhere in the module — a grep of the
whole module returns only their definitions.

TC188 therefore asserts **one menuitem and three act_window records**, and
records the divergence as a finding. That is a correction to the workbook's
description of the product, not a softened expectation: the workbook's
*expected result* (the three queues exist, the all-RMAs domain is right and
correctly populated, both groups see the menu) is implemented in full.

## The four findings this suite exists to catch

### 1 — Two hard-coded location ids that cannot be right on v19 (TC190)

`views/stock_picking.xml:85` filters `('location_id','=',5)` and `:106`
filters `('location_dest_id','=',4)`, commented in the source as
`Partners/Customers` and `Partners/Vendors`.

Those numbers were only ever correct on a clean **Odoo 17** install, where
`stock/data/stock_data.xml` creates, in order: Physical Locations (`:23`),
Partners (`:28`), Virtual Locations (`:34`), **Vendors (`:41`)**, **Customers
(`:48`)** → ids 1, 2, 3, **4**, **5**.

Odoo 19 **removed the Partners parent location entirely**: the file now
creates `stock_location_suppliers` first (`:23`) and `stock_location_customers`
second (`:28`), with no parent. A fresh v19 install cannot assign 4 and 5,
and the complete names change from `Partners/Vendors` / `Partners/Customers`
to `Vendors` / `Customers`.

The *semantics* hold in both versions — a customer return's `location_id` is
the delivery's `location_dest_id`, a vendor return's `location_dest_id` is
the receipt's `location_id` (v17 `_prepare_picking_default_values:113-127`;
v19 `_prepare_picking_default_values_based_on:142-159`) — so the fix is a
one-line `ref()` swap, not a redesign. Until it lands, **both directional
menus return an empty or a wrong list with no error at all**.

### 2 — The forked report is a v19 runtime bomb (TC187)

`report/report_stockpicking_operations.xml` is a full fork of
`stock.report_picking_operations` and references five things v19 removed:

| Reference | In the fork | v17 counterpart | v19 |
|---|---|---|---|
| `stock.picking.move_ids_without_package` | `:94` | `stock/models/stock_picking.py:466` | **removed** |
| `stock.picking.move_line_ids_without_package` | `:121` | `:492` | **removed** |
| `stock.picking.package_level_ids` | `:174`, `:184` | `:523` | **removed** |
| `stock.move.product_packaging_id` / `product_packaging_qty` | `:129-135` | `stock/models/stock_move.py:182,183` | **removed** |
| `stock.quant.package` | `:186` | `stock/models/stock_quant.py:1456` | **renamed** `stock.package` (`stock/models/stock_package.py:18`) |

QWeb templates are not validated at install, so the module installs cleanly
and the report fails only when someone prints. This is the single biggest
unrepaired v19 break in the fork.

### 3 — `view_mode="tree"` survived the port (TC188)

All three act_windows still declare
`view_mode="tree,kanban,form,calendar,activity"`
(`views/stock_picking.xml:84,105,126`). `'tree'` is present in
`ir.ui.view.type`'s selection on v17
(`odoo/addons/base/models/ir_ui_view.py:163`) and **absent** on v19
(`:149`); `_check_view_mode` only rejects duplicates and spaces
(v19 `ir_actions.py:299-306`), so the record saves and the breakage surfaces
at view-resolution time. `odoo/upgrade_code/17.5-01-tree-to-list.py` is a
source rewriter, not a runtime fallback.

### 4 — A view-level requirement with nothing behind it (TC186)

`required="True"` on `reason_for_return` and `return_notes`
(`views/stock_picking.xml:12-13`) is a **client-side modifier**. There is no
`@api.constrains` and no `_sql_constraints` anywhere in the module, and
neither model field carries `required=`
(`models/stock_picking.py:11,35`). An ORM `create` with an `rma_number` and
no reason succeeds — WF-024 E2, asserted positively by TC186 step 11.

## Per test case

| Workbook TC | Platform test | Priority · kind | What is proven |
|---|---|---|---|
| `TC044` | `TEST-WF024-TC044` | P0 · DATA | The `rma_number` sequence definition, the live counter, the issued population per year, zero duplicates, the no-collision property and the four-digit overflow set — captured on v17, diffed on v19 |
| `TC184` | `TEST-WF024-TC184` | P1 · API | A wizard return is numbered `YYYY-nnn`, the prefix is the calendar year, the counter advances by exactly 1, the number is global, the readonly is view-level, and padding 3 renders `<year>-1000` |
| `TC185` | `TEST-WF024-TC185` | P1 · API | The return's `note` equals the company narration exactly, and is **not** refreshed when the company value later changes (BR-2) |
| `TC186` | `TEST-WF024-TC186` | P1 · API | Both fields are scoped to RMA pickings by one `invisible` expression, the vocabulary is exactly the 19 codes 901–919, the requirement is bypassable by the ORM, and the three taxonomy copies still agree |
| `TC187` | `TEST-WF024-TC187` | P1 · HYBRID | `do_print_picking()` branches on `rma_number`; the RMA action, the filename expression and the rendered body; the standard slip on a non-RMA picking; the paperformat is a page, not a 43 × 30 mm label |
| `TC188` | `TEST-WF024-TC188` | P2 · API | The menu, the three act_windows, the all-RMAs domain and its membership, the view modes, the two extra filters, and per-group menu visibility |
| `TC189` | `TEST-WF024-TC189` | P0 · API | Return-and-Replenish adds **exactly one** zero-priced line **per returned line**, dated today, with the right UoM, description and quantity, and no change to the order total |
| `TC190` | `TEST-WF024-TC190` | P0 · REGR | The customer and vendor queues return the right pickings on a rebuilt database — **expected to fail today** |

### Suite layout

| File | Cases |
|---|---|
| `tests/wf024/common.py` | fixtures, probes, sweeping, verbatim source constants |
| `tests/wf024/test_rma_numbering.py` | `TC184`, `TC185` |
| `tests/wf024/test_rma_fields_and_reports.py` | `TC186`, `TC187` |
| `tests/wf024/test_rma_queues.py` | `TC188`, `TC190` |
| `tests/wf024/test_return_replenish.py` | `TC189` |
| `tests/wf024/test_reconciliation.py` | `TC044` |

## Expected outcome per test

| Test | Expected on the **v17 clone** | Expected on **v19** |
|---|---|---|
| `TC044` | **PASS** — baseline captured | **PASS** if the series continued. Any diff in the definition, the frozen `number_next` column, the issued population, the duplicate set or the four-digit set is a real finding. The live counter is asserted directionally, not diffed (adaptation 18): it fails the case only when it has dropped **below** the baseline's highest issued serial |
| `TC184` | **PASS** | **FAIL at step 4** — v19 prefills the wizard quantity as `0` (`odoo-19.0/addons/stock/wizard/stock_picking_return.py:135`), so it does not "list the returnable quantities" |
| `TC185` | **PASS** | **PASS** |
| `TC186` | **PASS** for the arch, the selection, the ORM bypass and the taxonomy comparison; **BLOCKED** for steps 4–5 | same |
| `TC187` | **PASS** | **FAIL / ERROR** on the render half (finding 2); the action-selection half still passes |
| `TC188` | **PASS** | **FAIL at step 8** — `'tree'` is not a v19 view type (finding 3) |
| `TC189` | **PASS** | **PASS** if the port held; the exposure is `_create_returns_and_replenishments` calling `super()._create_return()` from a differently named method |
| `TC190` | **PASS only** if the clone still carries the original v17 install ids; **FAIL** on any rebuilt database | **FAIL** — finding 1 |

Per AUTOMATION_CONVENTIONS hard rule 2, every one of those failures is
implemented as the workbook wrote it and documented in the test docstring as
`EXPECTED v19 OUTCOME: FAIL — <why>`. None is inverted, weakened or
paraphrased.

## Version deltas that reach this suite

`adapters/` is outside this suite's write scope, so the pairs live in
`tests/wf024/common.py` and are resolved by **probing the target** — which
is stronger than a version switch, because it measures the database actually
under test rather than the label on it. No test body carries `if version`.

| Concern | Odoo 17 | Odoo 19 | Resolver in `common.py` |
|---|---|---|---|
| Wizard public "Return" | `create_returns` (`stock/wizard/stock_picking_return.py:183`) | `action_create_returns` (`:210`) | `return_confirm_method(ctx)` — reads the delivered wizard arch, which is what the DataOne xpath anchors on (`wizard/stock_picking_return_views.xml:12`) |
| Wizard private creator | `_create_returns` → **tuple** `(picking_id, pick_type_id)` (`:129`, `:181`) | `_create_return` → **recordset** (`:161`, `:187`) | not called — private |
| Prefilled return quantity | delivered − already returned (`:80-92`) | **`0`** (`:131-137`) | not adapted — it is TC184 step 4's subject |
| `sale.order.line` UoM | `product_uom` (`sale/models/sale_order_line.py:120`) | `product_uom_id` (`:132`) | `sol_uom_field(rpc)` |
| `ir.ui.menu` groups m2m | `groups_id` (`base/models/ir_ui_menu.py:32`) | `group_ids` (`:29`) | `menu_groups_field(rpc)` |
| `ir.actions.act_window` groups m2m | `groups_id` (`base/models/ir_actions.py:291`) | `group_ids` (`:329`) | `act_window_groups_field(rpc)` |
| `ir.actions.report` groups m2m | `groups_id` (`base/models/ir_actions_report.py:137`) | `group_ids` (`:182`) | `report_groups_field(rpc)` |
| Package model | `stock.quant.package` (`stock/models/stock_quant.py:1456`) | `stock.package` (`stock/models/stock_package.py:18`) | `package_model(rpc)` |
| `ir.ui.view.type` list value | `tree` (`ir_ui_view.py:163`) | `list` (`:149`) | `fg_common.list_tag` / `available_view_types(rpc)` |
| `res.users` groups m2m | `groups_id` (`res_users.py:384`) | `group_ids` (`:257`) | `ctx.adapter.user_groups_field` |
| Storable product | `type='product'` | `type='consu'` + `is_storable` | `ctx.adapter.storable_product_values()` |
| `stock.location.return_location` | present (`stock/models/stock_location.py:72`) | **removed** | not asserted |
| Return-wizard `location_id` field | present | **removed** | not written by any fixture |

Three of these are **new pairs discovered by this workflow** —
`menu_groups_field`, `act_window_groups_field`, `report_groups_field` — plus
`package_model`. They belong in `adapters/odoo17.py` / `adapters/odoo19.py`
and in the conventions table; a suite cannot write there, so they are flagged
here for the adapter owner.

## Adaptations (documented, not assertion-weakening)

1. **TC044 is reconciled through the ORM, not raw SQL.** Every figure the
   workbook's SQL selects is ORM-reachable: `number_next_actual` **is**
   `_predict_nextval` over `pg_sequences`
   (`odoo/addons/base/models/ir_sequence.py:64-84`, `:100-110`). The case
   therefore needs no `pg_*` credentials and cannot report BLOCKED for their
   absence — the same adaptation WF-013 made for its fourteen reconciliation
   cases.
2. **TC044 step 5 and TC184 step 10 measure `number_next_actual`.** For
   `implementation='standard'` the counter lives in the PostgreSQL sequence
   `ir_sequence_%03d` and `number_next` **never moves** (`:202-207`). The
   workbook's `number_next` figure is still captured and recorded; it is the
   *comparison* that uses the column which actually advances. Not a
   weakening — the opposite: the workbook's own version of step 5 measures a
   column that cannot change.
3. **TC044 step 6 is not executed.** It allocates a number in a rolled-back
   transaction; `ctx.sql` is read-only by contract
   (`framework/sqltool.py` opens with `default_transaction_read_only=on`)
   and the workbook itself records that the counter advances anyway. It
   stays a Phase-0a manual step, named in the docstring.
4. **TC184 step 13 uses `get_next_char(1000)`, not a write to
   `number_next`.** `ir.sequence.get_next_char` is public, returns a string
   and writes nothing (v17 `:241-243`, v19 `:240-242`). Writing
   `number_next` on the shared global `rma_number` sequence would modify a
   pre-existing business record, which hard rule 3 forbids outright.
5. **TC184 step 9 proves the read-only is view-level.** A real UI read-only
   check is HttpCase territory; what is asserted is the arch modifier
   `readonly="1"` (`views/stock_picking.xml:9`) **plus**
   `fields_get('stock.picking', ['rma_number'])['rma_number']['readonly']`
   being False — which is the workbook's actual point.
6. **TC185 step 10 is replaced by its static equivalent.** A scratch
   database without `dto_account` cannot be provisioned — AUTOMATION_CONVENTIONS
   says "never start a server, run a suite, or touch a database". What is
   asserted instead is fully verifiable and says the same thing:
   `__manifest__.py:14` declares exactly `["stock"]` while
   `res.company.vendor_refund_narration` exists on the target — the
   dependency is real and undeclared. The documented `AttributeError` is
   logged and recorded as a Phase-0a manual item.
7. **TC185 steps 5–9 write a PRE-EXISTING business record. This is a
   hard-rule-3 EXCEPTION AWAITING APPROVAL, not an adaptation.**
   AUTOMATION_CONVENTIONS hard rule 3 reads *"Never modify pre-existing
   business records"* and carries no sanctioned-mutation clause, so
   describing this as an adaptation (as this plan previously did) was
   wrong. The suite cannot grant itself the exemption; it is recorded here
   as open.

   *What the case does.* `res.company.vendor_refund_narration` is the only
   pre-existing business value this suite writes. It is snapshotted first,
   replaced with a token-marked value, restored by step 9 with the
   restoration **asserted**, and restored again by a `finally:` that cannot
   raise and that logs `[ALERT]` carrying the original value if even that
   fails.

   *The exposure is real while the window is open.* Every return created on
   that database meanwhile copies the token-marked terms into its `note`
   (`wizard/stock_picking_return.py:24`), and every vendor credit note its
   narration (F156). The window is therefore held to **one wizard create +
   confirm**: the second source delivery is built in the precondition step,
   before the mutation, rather than between it and the restore. Run the
   case on the dedicated `_qa` clone.

   *The two ways out, neither of which a suite may take unilaterally.*
   (a) An explicit hard-rule-3 clause for a **restorable single-field
   company setting on a dedicated clone**. (b) A second, token-named
   `res.company` whose own user runs the second return — `_create_return`
   reads `self.env.company` (`wizard/stock_picking_return.py:24`), so
   steps 6 and 8 would still assert exactly what the workbook wants. (b)
   trades this exposure for a company whose auto-created warehouse, picking
   types and sequences the sweep cannot remove, which is why it is not
   simply the better option. **Decision needed from the conventions
   owner.**
8. **TC186 steps 4–5 are a blocked half, not a passing assertion — and
   they make the whole case a blocked stub.** The required-field refusal is
   the web client evaluating the modifier; the ORM accepts the empty write.
   The arch is asserted, then `ctx.blocked` names the missing
   `@api.constrains` and the HttpCase tour that would prove the refusal.
   Because `ctx.blocked` raises `BlockedTest` (`framework/context.py:154-156`),
   the platform records the case BLOCKED whatever ran before it, so the
   feasibility file now says `blocked_stub` and the Result table above
   counts it as one.

   *Note for the conventions owner.* AUTOMATION_CONVENTIONS' feasibility
   policy scopes "blocked stub" to TCs whose essence needs an **external
   system** (Workday SFTP, a queue-job runner, PrintNode hardware). TC186
   needs none — its unreachable half is simply not observable over RPC,
   which is the shape the conventions' own "Private methods are not
   reachable" section already sanctions `ctx.blocked` for. The category
   fits the recorded outcome; the policy wording is what needs widening.
   The alternative — dropping the terminal `ctx.blocked` so the twelve real
   assertions produce a PASS — was rejected: it would let a case report
   PASSED whose workbook step 5 expectation was never tested, which reads
   as weakening under hard rule 2.
9. **TC186 accepts `required="True"` or `required="1"` and records which.**
   Both spell the same modifier; the workbook's v19 migration item 5 wants
   the literal normalised. What matters to the case — that the requirement
   is view-level — is unaffected.
10. **TC186 step 13 compares over RPC, not by grepping the source.**
    `framework.source_scan`'s default root is `DTO-Odoo`, which now holds the
    **v19** port, so grepping it during a v17 run would compare the wrong
    tree. The three declared selections are read with `fields_get` under
    `lang='en_US'` (labels are translated otherwise) and diffed as one
    mismatch dict.
11. **TC187's body assertions render HTML, not PDF.**
    `/report/html/<name>/<id>` is declared identically in both versions
    (`web/controllers/report.py:23-40`) and dispatches to
    `_render_qweb_html`, so it needs no wkhtmltopdf. `/report/pdf/...` would
    500 without it, so it is **never called**: the byte-level
    `Content-Disposition` filename, PDF text extraction and the measured
    page size of the produced PDF are a **MANUAL half that the test LOGS
    (steps 4 and 13), not a blocked one** — nothing in TC187 calls
    `ctx.blocked` for the PDF. Visual acceptance and page-size measurement
    stay MANUAL exactly as the workbook's "Wave 1 + Manual (split)" says.
12. **TC187 guards the admin trap before asserting.** `report_action()`
    returns the layout configurator instead of the report when
    `env.is_admin()` and the company has no `external_report_layout_id`
    (v17 `ir_actions_report.py:1060`, v19 `:1182`). `require_report_layout`
    measures it and the print calls run through a non-admin session.
13. **TC187 step 13 reads `paperformat_id`, not `get_paperformat()`.** The
    latter returns a recordset and cannot be marshalled over `call_kw`
    (v17 `:245`, v19 `:288`). `report.paperformat.default` is inert —
    nothing in core reads it (v17
    `odoo/addons/base/models/report_paperformat.py:171`, v19 `:170`) — so
    the assertable form is: the RMA action declares **no** paperformat, and
    the company's own format is a page, not the 43 × 30 mm label
    `location_barcode_labels/views/barcode_labels_location.xml:13-28` ships
    with `default=True`.
14. **TC188 and TC190 scope every queue search by the execution token.** The
    live all-RMAs queue holds production returns, so membership of the
    fixtures and non-membership of the plain picking are asserted — never
    "exactly N rows" (hard rule 5).
15. **TC188 step 9 reads the search view off `ir.ui.view` directly.**
    `view_picking_internal_search_inherit` carries no `inherit_id`
    (`views/stock_picking.xml:17-20`), so `get_view` would return core's
    search arch and the two RMA filters would be invisible to the test.
16. **TC189 step 13 measures the server's own `fields.Date.today()`.**
    `wizard/stock_picking_return.py:54` evaluates it in the **Odoo server
    process**, which is neither the platform host's date nor the session
    timezone's. Guessing would break across a midnight boundary; widening to
    a ±1-day window would weaken the workbook. It is read exactly instead,
    from the one core Date field defaulting to it — package `pack_date`
    (v17 `stock/models/stock_quant.py:1483`, v19
    `stock/models/stock_package.py:54`) — via a namespaced throwaway record
    that is removed immediately.
17. **TC190 step 4 is left failing.** The workbook says "Do not soften this
    case", so step 4 is a plain `ctx.check` against the literals 5 and 4,
    not a recorded observation. The domains are read verbatim off the
    `ir.actions.act_window` records and never retyped, so the test measures
    the shipped domain.
18. **TC044 does not DIFF the live PostgreSQL counter; it asserts it
    directionally.** `framework/baselines.py:47-54` `diff_counts` compares
    **every** key of the snapshot it is handed, and `number_next_actual` is
    the one key **this suite's own fixtures move**: TC184, TC185, TC188,
    TC189 and TC190 create two returns each and TC186/TC187 one each, every
    one through the real wizard, whose `_create_return` calls
    `next_by_code('rma_number')` (`wizard/stock_picking_return.py:23` →
    `models/stock_picking.py:42-44`). A PostgreSQL sequence is never rolled
    back and the sweep only deletes pickings, so the counter sits ~13
    higher after every execution while `issued_total`, `issued_by_year` and
    `duplicates` return to their pre-run values. Diffing it would have
    FAILED **every** v19 run with `number_next_actual: baseline=N
    current=N+13` — reading exactly like the silent counter reset/jump the
    case exists to catch, and manufactured by the suite itself (hard
    rule 5). `common.rma_sequence_diffable` removes it from the diffed
    snapshot; in its place step 7 asserts what the workbook's
    *expected_final_state* actually says — *"the RMA series continues from
    where v17 left it, with no duplicate and no reset"* — as **the live
    counter must still exceed every serial the stored baseline recorded as
    issued**, which consuming numbers can only make more true and a reset
    (or a restore from an older dump) makes false. `number_next` **stays
    diffed**: it cannot move for `implementation='standard'`
    (`ir_sequence.py:202-207`), so any change in it is the real finding.
    `duplicates`, `issued_by_year` and `four_digit` — workbook steps 3, 4
    and 8 — are untouched.
19. **TC184 steps 8 and 13 measure the year the way the SEQUENCE measures
    it.** `%(year)s` is interpolated from
    `datetime.now(pytz.timezone(self._context.get('tz') or 'UTC'))` —
    `_interpolation_dict` inside `_get_prefix_suffix`, v17
    `ir_sequence.py:209-239` (the assignment at `:214`), v19 `:207-238` —
    i.e. in the **calling RPC session's timezone**, inside the Odoo
    process. `fields.Date.today()` is the wrong comparator: it is plain
    `date.today()` (v17 `odoo/fields.py:2138-2143`), the Odoo *host's*
    local date with **no timezone applied**, so a UTC server and an
    `America/Chicago` session at 31 Dec 20:00 local would have the sequence
    issue `2026-001` while the probe read 2027, failing both steps for a
    non-defect (hard rule 5). `_sequence_year` therefore reads the year out
    of the live sequence's own `get_next_char` rendering **on the session
    that issued the number**; step 13 compares its two renderings against
    the year interpolated on the session that produced them. `create_date`
    remains the fallback. (Previously undocumented; the docstring's item 4.)
20. **Equality in TC185 is between two values read back over the same RPC
    session**, never against the Python literal in
    `dto_account/models/res_company.py:11-49`: both fields are
    `fields.Html` and the literal has not been through the sanitizer. See
    `[PARTIALLY VERIFIED]` claim 7. (Previously undocumented; the
    docstring's item 7.)
21. **TC189 step 1 is not impersonated as TD-U-01.** The case's subject is
    the *values of the created replacement line*, not access control —
    which is TC188's subject — and every assertion in it is identical for
    any user who can run the wizard. The step runs on the platform's
    configured session and the divergence from the workbook's `role_user`
    is **logged, not asserted away** (`test_return_replenish.py:286-292`).
    (Previously documented only in the test docstring.)
22. **Every disposable `qa.wf024.*` user is archived in its case's
    `finally`.** `common.ensure_user_in_groups` creates internal users with
    a known password, and `sweep_wf024` cannot reach `res.users` — its
    `res.partner` step is deliberately guarded with `("user_ids", "=",
    False)`, so a QA user's partner survives too. Without the teardown, six
    active internal logins were left on the clone after every run. They are
    **archived, never unlinked**: each owns chatter on the fixture
    pickings. `common.archive_qa_users` is called from the `finally` of
    TC186, TC187, TC188 and TC190 (TC184 and TC185 archive their own by
    id), and it cannot raise. `ensure_user_in_groups` reactivates a login
    it finds, so TC188 archiving `qa.wf024.u04` cannot starve TC190 of it.

## Environment dependencies — every one probed, never assumed

| Requirement | Why it matters | Probe |
|---|---|---|
| `stock_picking_auto_create_lot` installed | No `rma_number`, no taxonomy, no report, no queue to test | `require_rma_module` |
| Exactly **one** `ir.sequence` with code `rma_number` | `next_by_code` orders by `company_id` and PostgreSQL sorts NULLs last (v17 `ir_sequence.py:279-292`), so a company-scoped duplicate silently hijacks every RMA number and every numbering assertion would measure the wrong counter | `require_rma_sequence` |
| `dto_account` present | `wizard/stock_picking_return.py:24` reads `res.company.vendor_refund_narration` while the manifest declares only `stock` — WF-024 E1 | `require_vendor_narration` |
| `dto_sale` + `sale_stock` present | The replenishment leg writes `sale.order.line.requested_delivery_date` (`dto_sale`) and is gated on `picking.sale_id` (`sale_stock`) | `require_dto_sale` |
| `quality_control` + `dto_purchase_stock` present | Copies 2 and 3 of the taxonomy; without them the drift detector has one list to compare | `require_quality_taxonomy` |
| Every `ir.mail_server` deactivated | `dto_sale_stock/data/base_automation_data.xml:4-11` fires on delivery validation and calls `send_mail(force_send=True)` against hard-coded `@d1systems.com` recipients | `qa_fixtures.require_mail_offline` |
| `res.company.external_report_layout_id` set — **or** a non-admin session | Otherwise `report_action()` hands back the layout configurator instead of the report | `require_report_layout` |

## Fixture safety

1. **Namespacing.** Every record carries `WF024-<8-hex>`; every search is
   scoped by it. The live RMA population is **never** swept by
   `rma_number` — that would reach production returns, which hard rule 3
   forbids.
2. **Return pickings carry no token.** The core wizard sets
   `origin = "Return of <name>"` (v17 `:119`, v19 `:155`), so returns are
   reached through `return_id` and through the namespaced partner instead.
3. **Sweep order is children before parents**: auto-posted invoices →
   pickings and their moves (including returns) → sale orders and their
   lines (including the replenishment delivery
   `sale_stock.SaleOrderLine.create` spawns,
   `sale_stock/models/sale_order_line.py:188-191`) → quants → products →
   packages → partners → scratch sequences. Everything is best effort, in a
   `finally:` that cannot raise (`safe_sweep`).
4. **Three confirmation gates** must be satisfied by every fixture order:
   `order_type` is `required=True` (`dto_sale/models/sale_order.py:17-26`);
   every product line needs `requested_delivery_date` or
   `_dto_gate_promised_ship_date` (`:90-94`) raises `"Please enter 'Promised
   Ship Date' for all order lines."`; and the analytic gate must pass —
   `order_type='inventory'` is used because its rule is simply *no analytic
   distribution* (`dto_account/models/sale_order.py:107`), which keeps the
   fixture independent of whichever analytic plans the database has.
5. **Two documented side effects of the fixtures**, recorded rather than
   asserted away: validating a sale-linked delivery of an
   `inventory` / `project` / `cost_center` order auto-creates and **posts**
   an invoice (`dto_sale_stock/models/stock_picking.py:12-23`), and adding a
   replacement line dated today **moves** `sale.order.commitment_date`
   (`dto_sale/models/sale_order.py:27-32,54-57,101-110`).
6. **Scratch sequences never use the code `rma_number`** — see the
   environment table above.

## Verified source facts

All citations were re-read against the real trees before anything was
written (hard rule 6). Paths are relative to
`DTO-Odoo/3rd-addons/stock_picking_auto_create_lot/` unless stated.

| Fact | Where |
|---|---|
| Manifest version `19.0.1.0.0`; `depends` is exactly `["stock"]` | `__manifest__.py:7,14` |
| `rma_number` — `fields.Char`, stored, not required, not readonly | `models/stock_picking.py:9` |
| `reason_for_return` — 19-value Selection `'901'`…`'919'`, no default, not required; `902`'s label carries **U+2013 EN DASH** | `models/stock_picking.py:11-33` (verified by codepoint) |
| `return_notes` — `fields.Text` | `models/stock_picking.py:35` |
| `do_print_picking()` branches on `rma_number`; drops core's `printed=True` and its `UserError`; no `ensure_one()` | `models/stock_picking.py:37-40` vs core v17 `stock/models/stock_picking.py:909-914`, v19 `:1175-1177` |
| `_get_rma_sequence()` → `next_by_code("rma_number")` — **private** | `models/stock_picking.py:42-44` |
| The sequence: `RMA Numbers`, code `rma_number`, prefix `%(year)s-`, padding 3, increment 1, `company_id eval="False"`; `suffix` / `use_date_range` / `implementation` / `active` unset → model defaults | `data/rma_sequence.xml:5-13`; defaults v17 `odoo/addons/base/models/ir_sequence.py:134-155`, v19 `:132-152` |
| `number_next` does **not** move for `implementation='standard'`; `number_next_actual` does | `ir_sequence.py:202-207`, `:64-84`, `:100-110` |
| `get_next_char(n)` is public and writes nothing | v17 `ir_sequence.py:241-243`, v19 `:240-242` |
| `next_by_code` orders by `company_id`, NULLs last | v17 `ir_sequence.py:279-292` |
| The form inherit: `rma_number` after `partner_id`; `reason_for_return` and `return_notes` after `picking_type_id`, both `invisible="rma_number == False"` and `required="True"` | `views/stock_picking.xml:8-14` |
| Both core anchors exist in both trees | v17 `stock/views/stock_picking_views.xml:230,231`; v19 `:225,226` |
| Explicit XML modifiers survive into the delivered arch (`_modifiers_from_model` only *adds*) | v17 `odoo/addons/base/models/ir_ui_view.py:1300-1304`, v19 `:1774-1778` |
| No `@api.constrains` and no `_sql_constraints` anywhere in the module | grep of the whole module |
| The search view carries **no** `inherit_id` — a standalone hand-copy | `views/stock_picking.xml:17-20` |
| `customer_rma` filters `picking_type_code = 'incoming'`; `vendor_rma` filters `'outgoing'` — inverted against the act_window domains | `views/stock_picking.xml:31-32` vs `:85,106` |
| Three act_windows, all `view_mode="tree,kanban,form,calendar,activity"`; domains verbatim | `views/stock_picking.xml:81-137` (`:84,85`, `:105,106`, `:126,127`) |
| **One** menuitem, parent `stock.menu_stock_transfers`, sequence 19, both stock groups | `views/stock_picking.xml:138-140`; groups v17 `stock/security/stock_security.xml:20,25`, v19 `:10,16` |
| v17 location ids 1–5 in creation order; v19 removed the Partners parent | v17 `stock/data/stock_data.xml:23,28,34,41,48`; v19 `:23,28` |
| `stock.location.return_location` removed in v19 | v17 `stock/models/stock_location.py:72`; absent in v19 |
| `action_report_return` — name `RMA`, `report_name` the module's own template, `report_file` **pointing at core** (copy-paste artifact), the `print_report_name` expression | `report/stock_report_views.xml:5-10` |
| Core comparator `stock.action_report_picking`, byte-identical in both | `stock/report/stock_report_views.xml:4-13` |
| `report_action()` returns `context/data/type/report_name/report_type/report_file/name` — **no id, no xmlid** | v17 `odoo/addons/base/models/ir_actions_report.py:1049-1057`, v19 `:1171-1179` |
| The admin + missing-layout trap returns the layout configurator | v17 `:1060`, v19 `:1182` |
| The filename is built by the HTTP controller from `print_report_name` | v17 `web/controllers/report.py:128-130`, v19 `:135-136` |
| `/report/<converter>/<reportname>/<docids>` exists in both and `html` dispatches to `_render_qweb_html` | `web/controllers/report.py:23-40` (both) |
| The five v19-removed references in the forked template | `report/report_stockpicking_operations.xml:94,121,129-135,174,184,186` (counterparts in the table above) |
| `<t t-set="address" t-value="None"/>` suppresses the address block | template `:8-9`; `web.address_layout` v17 `web/views/report_templates.xml:283`, v19 `:280` |
| `<h1 t-field="o.rma_number">`, the reason/notes block, `<p t-field="o.note"/>` | template `:71`, `:86-92`, `:210` |
| The serial gate `groups="stock.group_production_lot"` | template `:96` |
| Wizard override: `_create_return` (v19) stamps `rma_number` and `note` | `wizard/stock_picking_return.py:21-25` |
| `_create_returns_and_replenishments` calls **`super()._create_return()`**, skips `quantity <= 0`, sets `price_unit = 0.0`, `requested_delivery_date = fields.Date.today()`, `name = get_product_multiline_description_sale()` | `wizard/stock_picking_return.py:27-67` (`:33`, `:43`, `:50`, `:53`, `:54`, `:55`, `:59`) |
| `create_returns_and_replenishments` is **public**, returns a dict, has no `ensure_one()`, leaks `new_picking` from its loop | `wizard/stock_picking_return.py:69-95` |
| `returned_sale_order_id` is commented out and exists nowhere in the tree | `wizard/stock_picking_return.py:66`; grep of `DTO-Odoo` |
| The extra footer button, anchored on `action_create_returns` | `wizard/stock_picking_return_views.xml:12-16` |
| Core footer order: v17 Return → **R&R** → Cancel; v19 Return → **R&R** → Return All → Return for Exchange → Discard | v17 `stock/wizard/stock_picking_return_views.xml:34-37`; v19 `:26-31` |
| v17 wizard line `quantity` has no default; v19 has `default=1` and the prefill returns `0` | v17 `stock/wizard/stock_picking_return.py:15`, `:80-92`; v19 `:14`, `:131-137` |
| `product_return_moves` is a **stored compute on `picking_id`** in both, so it materialises on create | v17 `:37`, `:46`; v19 `:103`, `:106` |
| `stock.picking.return_id` / `return_ids` exist in both | v17 `stock/models/stock_picking.py:410,412`; v19 `:566,568` |
| `stock.picking.note` is `fields.Html` in both; `printed` is a Boolean in both | v17 `:403`, `:509`; v19 `:559`, `:655` |
| `res.company.vendor_refund_narration` — `fields.Html`, default `_default_vendor_refund_narration`, whose body carries the Dallas address, the Quality Control routing and the 15-day window | `dto_account/models/res_company.py:11-54` |
| `sale.order.line.requested_delivery_date` is `dto_sale`'s, not core's | `dto_sale/models/sale_order_line.py:11-13` |
| `sale.order.order_type` is `required=True`; the promised-ship-date gate and its verbatim message | `dto_sale/models/sale_order.py:17-26`, `:88-99` |
| The analytic gate and its four verbatim messages | `dto_account/models/sale_order.py:42-52`, `:89,100,107,112` |
| Adding a line dated today recomputes `commitment_date` | `dto_sale/models/sale_order.py:27-32`, `:54-57`, `:101-110` |
| `sale_stock.SaleOrderLine.create` launches the stock rule on a confirmed order | `sale_stock/models/sale_order_line.py:188-191` |
| Delivery validation auto-creates and posts an invoice for three order types | `dto_sale_stock/models/stock_picking.py:12-23` |
| The mail automation that makes `require_mail_offline` mandatory | `dto_sale_stock/data/base_automation_data.xml:4-11` and the server action's `send_mail(force_send=True)` |
| The taxonomy's other two copies are byte-identical today | `dto_purchase_stock/models/quality_check.py:8-26`, `dto_purchase_stock/wizard/quality_check_wizard.py:8-26` (programmatically compared — all three parse to the same 19 ordered pairs) |
| `get_product_multiline_description_sale()` is public and identical in both | v17 `product/models/product_product.py:759-768`; v19 `:1140-1149` |
| `sale.order.line.price_unit` is `compute, store=True, readonly=False, precompute=True` — an explicit vals value wins | v17 `sale/models/sale_order_line.py:141-145`; v19 `:177-181` |
| `ir.ui.menu.load_menus(debug)` is a public `@api.model` returning a dict | v17 `ir_ui_menu.py:247`; v19 `:236` |
| Package `pack_date` defaults to `fields.Date.today` in both | v17 `stock/models/stock_quant.py:1483`; v19 `stock/models/stock_package.py:54` |
| Verbatim wizard error strings | `"Please specify at least one non-zero quantity."` v17 `:177` / v19 `:183`; `"You may only return Done pickings."` v17 `:52` / v19 `:114`; `"You may only return one picking at a time."` v17 `:30` / v19 `:95`; `"You have manually created product lines, please delete them to proceed."` v17 `:144` only |

## `[UNVERIFIED]` and `[PARTIALLY VERIFIED]` claims

| # | Claim | What would validate it |
|---|---|---|
| 1 | **[UNVERIFIED]** Whether `stock_picking_auto_create_lot`, `dto_account`, `dto_sale` and the `quality_control` / `dto_purchase_stock` pair are installed on the QA clone | The suite's own probes on the first run — each BLOCKS naming exactly what is missing |
| 2 | **[UNVERIFIED]** Whether the v17 clone runs the **v17** fork or the **v19** port. `dto.conf`'s addons path points at `DTO-Odoo/3rd-addons`, which now holds `19.0.1.0.0` code whose wizard xpath anchors on `action_create_returns` — a method that does not exist in v17 and would have aborted the v17 install | Read `ir_module_module.latest_version` for the module on the clone, and check which of `create_returns` / `action_create_returns` the delivered wizard arch carries. `common.return_confirm_method` probes the second half already, so the suite runs either way — but the answer must be recorded before results are interpreted |
| 3 | **[UNVERIFIED]** The real ids of `stock.stock_location_customers` and `stock.stock_location_suppliers` on the QA target (workbook TD-L-08) | TC190's own step 3 — it records them |
| 4 | **[UNVERIFIED]** `res.company.paperformat_id`, and whether any company has `external_report_layout_id` set | `require_report_layout` and `company_paperformat` measure both on the first run; the second decides whether TC187 must impersonate a non-admin |
| 5 | **[UNVERIFIED]** Whether any existing `stock_picking.rma_number` is four-digit (TC044 step 8) | The TC044 capture records the set; it is a database fact, not a source fact |
| 6 | **[UNVERIFIED]** Whether wkhtmltopdf is installed on the Odoo host | `/report/check_wkhtmltopdf`. Only the optional PDF half of TC187 depends on it; the HTML half does not |
| 7 | **[PARTIALLY VERIFIED]** Byte-exact equality of `stock.picking.note` and `res.company.vendor_refund_narration` after the Html sanitizer round trip. Both are `fields.Html` with identical sanitize defaults (`odoo-17.0/odoo/fields.py:2008-2015`), so it should hold, but sanitizer idempotence across one extra round trip is not proven from source | TC185 compares the two values **as read back over the same RPC session**, never against the Python literal in `res_company.py`, which has not been through the sanitizer. If the equality proves brittle in practice, normalise whitespace and record the adaptation in the docstring — never drop the assertion |
| 8 | **[PARTIALLY VERIFIED]** The exact v19 failure mode of `view_mode="tree"` at view-resolution time. Proven: `'tree'` is absent from `ir.ui.view.type` (v19 `ir_ui_view.py:149`) and `_check_view_mode` does not reject it (v19 `ir_actions.py:299-306`). Not traced to the raising line in `get_views` | Opening the queue on a v19 instance and recording the traceback. TC188 asserts the `view_mode` string and the selection membership, both of which are proven, so the case does not depend on the unproven half |

## Recorded observations (not failures)

- `action_report_return.report_file` is `stock.report_picking_operations` —
  core's template, not the module's own
  (`report/stock_report_views.xml:9`). A copy-paste artifact; the workbook
  says explicitly to record it, not to fail on it.
- The forked search view has already drifted from v19 core's own
  `view_picking_internal_search`
  (`odoo-19.0/addons/stock/views/stock_picking_views.xml:345-410`), which
  adds activity and date-category filters, `late_availability` and two
  group-bys, and drops `planning_issues` — which the hand-copy still
  carries.
- `dto_sequence` still declares `"17.0.0.0"` and inherits `stock.report_picking`
  (the standard slip) rather than the RMA template, so RMA PDFs have no
  SO/PO line-sequence columns.
- Printing an RMA leaves `stock.picking.printed` at `False`, because the
  override drops core's `write({'printed': True})`.
- `create_returns_and_replenishments` has no `ensure_one()` and lets
  `new_picking` leak out of its own loop — the same shape v17 had.

## Run

```bash
venv/Scripts/python.exe -c "from framework import registry; print(len(registry.discover()))"
```
