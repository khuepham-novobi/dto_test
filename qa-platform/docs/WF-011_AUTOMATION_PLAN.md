# DATAONE-WF-011 — Delivery, Boxing, Blind Ship & Packing Documents · Automation Plan

| | |
|---|---|
| Workflow | `DATAONE-WF-011` |
| Build order | 14 · Area **Inventory** |
| Effective risk | **HIGH** · fail mode **loud + silent** |
| Owns | 19 workbook test cases — **4 of them P0** (TC158, TC159, TC163, TC164) |
| Suite | `tests/wf011/` |
| Modules | `dto_stock`, `dto_sale_stock`, `dto_mrp_account`, `dto_base`, `dto_mrp`, `printnode_base`, `stock_picking_auto_create_lot`, `location_barcode_labels` |
| Source of truth | `DataOne_v19_Test_Suite_and_Workflows_v1.0.xlsx` / Automation Export |

## Result

| | Count |
|---|---:|
| Implemented | **17** |
| Blocked stub | **2** (TC156, TC164) |
| Not implemented | 0 |
| **Total** | **19** |

## Scope

**In scope.** The 19 test cases this workflow owns: the box manifest (F077),
the weight overrides (F079), the Journal Entries stat button and its compute
(F080), both picking-control groups (F179, F180), the forced backorder (F042),
blind-ship propagation (F043), the batched Delivery Slip expansion (F044), the
packing-slip body (F045), the custom report / paperformat inventory (TC011,
shared with WF-024) and the RMA metadata reconciliation (TC054, shared with
WF-024).

**Out of scope.** The auto-invoice's journal-entry *shape* (F040) belongs to
WF-012 / WF-013 and is not re-asserted here — every fixture that validates a
picking defaults to `order_type='buy'`, the one type F040 excludes, so a
delivery assertion can never fail for an accounting reason. Location print
names and label sheets (F046 / A3), standard product labels (F094), carrier
rating and tracking (F075), the return flow itself (WF-024) and the PDF's
visual layout — spacing, fonts, letterhead imagery — are other suites'.

**Assumptions.** The target is a dedicated QA clone with every
`ir.mail_server` deactivated; the printing company uses
`web.external_layout_standard`; the `admin` RPC session is `base.user_admin`,
which `dto_mrp_account` seeds into *Validate Delivery Orders*.

**Dependencies.** `dto_account`'s analytic plans must resolve for an order to
confirm; `wkhtmltopdf` must be reachable for the two printing cases;
`printnode_base` must be installed for TC156 and for TC165's label half.

## What this suite exists to catch

Four things, each verified in source rather than inferred.

**1 · The batched-print expansion is silent, and only one route reaches it.**
`dto_sale_stock/models/ir_actions_report.py:14-18` keys off two *literal*
strings and expands `res_ids` to every non-cancelled outgoing picking of the
order. It overrides `_render_qweb_pdf`, which is **private** and therefore not
RPC-dispatchable; its only public entry point is
`GET /report/pdf/<report_name>/<ids>` — `addons/web/controllers/report.py:41-44`
passes the report name in as a **string**, which is what makes the branch fire.
`/report/html/` routes to `_render_qweb_html` (`:39`), which F044 does **not**
override. Substituting the HTML route would bypass the override under test and
report a green pass for a dead feature, so TC163 never does.

**2 · v19 removed the header hook the blind slip depends on.** v17 carries
`t-att-style="report_header_style"` on all four `external_layout` header divs
(`addons/web/views/report_templates.xml:309, 368, 430, 492`). **v19 carries it
on `external_layout_bold` only** (`:439`) — standard (`:503`), boxed (`:374`),
striped (`:312`) and the three new layouts (`_folder` `:563`, `_wave` `:651`,
`_bubble` `:724`) have no such hook — and the ported
`dto_sale_stock/report/report_templates.xml` patches only the tagline and the
four footers. So on v19 the Blind Packing Slip prints **with the company header
restored** unless the company is on the bold layout. That is precisely the
"partial blind-ship success" the workbook predicts as a silent commercial
disclosure failure, now established in source.

**3 · A one-character defect blocks the v19 upgrade recompute.**
`dto_stock/models/stock_picking.py:26` reads
`StockScrap.search([('picking_id', '=', self.id)])` — `self.id`, not `res.id` —
inside `for res in self`. Any multi-record recompute of `account_move_ids`
raises `ValueError: Expected singleton` (`odoo/fields.py:5163-5174`). TC168 is
implemented as the workbook wrote it and is **expected to fail on v17**.

**4 · An unguarded truthiness test aborts deliveries.**
`dto_sale_stock/data/base_automation_data.xml:59` evaluates
`if 'IRM' in order.memo_to_suppliers:` with no guard, and
`sale.order.memo_to_suppliers` is `fields.Text`
(`dto_sale_workday/models/sale_order.py:17`) that reads `False` when NULL. An
order with an empty memo raises `TypeError` *inside the `button_validate`
transaction*. This is not a test case here — it is a **fixture constraint** on
six of them, and `make_sale_order` satisfies it unconditionally.

## Verified source facts

Every project-addon line below was read on branch **`main`** (the v17
baseline) with `git show main:<path>`; the working tree is on `UAT`, which
already carries the v19 port, so a worktree read would have measured the wrong
code. Where the two differ, both are named.

| Fact | Where |
|---|---|
| `stock.picking.box`: `_order = 'sequence, id'`, `name` Char required, `weight` Float `digits='Stock Weight'` required | `dto_stock/models/stock_picking_box.py:9-17` |
| `_check_weight` tests **`== 0`**, not `<= 0` → a negative weight is accepted; message `Weight must be greater than zero.` | `:19-23` |
| `Stock Weight` precision (`digits 2`) exists unchanged on **both** versions | `addons/product/data/product_data.xml:27-30` (v17 and v19) |
| `action_create_boxes` public: `ensure_one()`, `box_count <= 0` guard, `box_ids.unlink()`, `Box %s`, `sequence = i*10`, `box_count = 0`, **`return True`** | `dto_stock/models/stock_picking.py:31-47` |
| `action_view_journal_entries` public; domain filters **`account.move.line`** ids; `search_default_group_by_move` | `:49-63` |
| `_compute_account_move_ids` passes **`self.id`** inside `for res in self` (E-1) | `:26` |
| `weight` / `shipping_weight` redefined `compute=False, readonly=False` | `:13-14` |
| Base fields still carry a compute on both versions | v17 `stock_delivery/models/stock_picking.py:91, 97-98`; v19 `stock_delivery:25`, `stock/models/stock_picking.py:666-670` |
| Boxes section is a **modifier**: `<div invisible="picking_type_code != 'outgoing'">` | `dto_stock/views/stock_picking_views.xml:32` |
| Create Boxes button `invisible="box_count &lt;= 0"` | `:42` |
| Kanban template `<t t-name="kanban-box">` (v17) → `<t t-name="card">` (v19 port `:67`) | `:50` |
| `context={'tree_view_ref': 'dto_stock.shipping_label_tree_on_picking'}` | `:20` |
| ACL: `stock.group_stock_user` `1,1,1,1`; `base.group_user` `1,0,0,0`; PrintNode's own xml ids overwritten to `1,1,1,0` | `dto_stock/security/ir.model.access.csv:2-5` |
| `base.group_user` **implies** `printnode_security_group_user` | `printnode_base/security/security.xml:24-26` |
| `shipping.label` base model; `label_status` selection `[('active','Active'),('inactive','In Active')]`, no default | `printnode_base/models/shipping_label.py:11-60` |
| dto_stock adds `pieces` Float and `default='active'`, forces five fields `readonly=False` | `dto_stock/models/shipping_label.py:10-16` (v17 only) |
| `create=1 edit=1 editable=bottom` forced onto PrintNode's `create="false"` list; `label_status` readonly in the **list**, not the form | `dto_stock/views/shipping_label_views.xml:12-19` |
| `button_validate` group guard, raised **before** `super()`; message not `_()`-wrapped | `dto_mrp_account/models/stock_picking.py:8-13` |
| `write()` raises **unconditionally** for `group_transfers_read` members | `:17-21` |
| `group_validate_delivery_orders` seeded to `base.user_root` + `base.user_admin`, no `category_id`; `group_transfers_read` has **no** seeded users and no `ir.rule` anywhere | `dto_mrp_account/data/server_actions.xml:18-35` |
| F044's expansion, keyed on two literals, using `\|=` so nothing is duplicated | `dto_sale_stock/models/ir_actions_report.py:14-18` |
| `ship_blind` related, **not stored**, not `readonly=False` | `dto_sale_stock/models/stock_picking.py:10` |
| F040 auto-invoices `project` / `inventory` / `cost_center` only | `:12-22` |
| `header_report_name = 'PACKING SLIP'`; headers `Shipping Method` · **`Tracking/Pro Number`** · `Pieces` · `Weight`; boxes chunked 12 with padding `<td>`s; `note` and `memo_to_suppliers` paragraphs | `dto_sale_stock/report/report_delivery_document.xml:6, 13-16, 38, 46, 51-56` |
| Blind slip: `display: none;` header/footer styles, `<h2>PACKING SLIP</h2>`, three `d-none` blocks, restricted contact widget, product-reference suppression | `dto_sale_stock/report/report_ship_blind.xml:5-39` |
| Blind report action, `print_report_name`, **no** `paperformat_id` | `dto_sale_stock/report/stock_report_views.xml:3-12` |
| F048 patches `div[@name='moto']` on **standard only**, plus four footers | `dto_sale_stock/report/report_templates.xml:3-33` |
| `process_cancel_backorder` hidden with `invisible="1"`; both wizard methods are **public** | `dto_sale_stock/wizard/stock_backorder_confirmation_views.xml:8-9`; `stock/wizard/stock_backorder_confirmation.py:52, 70` |
| Backorder action dict returned by `button_validate` | `stock/models/stock_picking.py:1149-1151`, `:1230-1241` |
| `'IRM' in order.memo_to_suppliers` unguarded; `send_mail(force_send=True)` to hard-coded `@d1systems.com` | `dto_sale_stock/data/base_automation_data.xml:49-70` |
| Confirmation gates: requester email, promised ship date, analytic plan per `order_type` | `dto_sale_workday/models/sale_order.py:24-26`; `dto_sale/models/sale_order.py:59-62`; `dto_account/models/sale_order.py:11-51` |
| `order_type` selection, `required=True` | `dto_sale/models/sale_order.py:17-26` |
| RMA fields and the 19-entry `reason_for_return` selection | `stock_picking_auto_create_lot/models/stock_picking.py:9-35` |
| Three custom paperformats each `default eval="True"` on v17 | `dto_base/reports/report_views.xml:6` (main), `dto_mrp/data/report_paperformat_data.xml:5`, `location_barcode_labels/views/barcode_labels_location.xml:15` |
| No ORM constraint enforces a single default paperformat | `odoo/addons/base/models/report_paperformat.py:167-189` |
| `res.users.has_group` is **not usable over `call_kw` to ask about another user on v17** — it is `@api.model` there, so the args list is mis-applied, and `_has_group` tests `self._uid` (the session user). On v19 it is a record method with `ensure_one()` plus an `AccessError` guard against answering about another user. Membership is therefore read from the groups m2m (`common.user_has_group`) | v17 `res_users.py:1085-1086`, `:1107-1109`; v19 `:1066`, `:1074-1078`, `all_group_ids` `:258` (a **non-stored** compute, `_compute_all_group_ids` `:447-449`) |
| `stock.move.name` required on v17, **absent** on v19 (`_rec_name = 'reference'`) | v17 `stock/models/stock_move.py:30`; v19 `:22` |

## Per test case

| Group | Workbook TCs | Platform tests | What is proven |
|---|---|---|---|
| Boxing and weights | `TC151`–`TC155`, `TC157` | `TEST-WF011-TC151…155`, `TC157` | Generation, reset and ordering; the destructive second press; both guards on a zero count; zero refused / negative accepted; the section is outgoing-only; weights are operator-entered and never recomputed |
| Delivery security and backorder | `TC158`–`TC161` | `TEST-WF011-TC158…161` | Both directions of *Validate Delivery Orders* with the exact strings; the inverted *Cannot edit transfers* group on every write path; the forced backorder and the honest statement of its limit |
| Blind ship and printed documents | `TC162`–`TC165`, `TC156` | `TEST-WF011-TC162…165`, `TC156` | Related-field propagation including to a done picking; one click covering both pickings, asserted by section count; the blind slip's suppression mechanism; the packing slip's tables and grids; hand-created shipping labels |
| Valuation and reports | `TC166`, `TC168`, `TC011` | `TEST-WF011-TC166`, `TC168`, `TC011` | The stat button's action, domain, grouping and balance; the multi-record singleton defect; the report/paperformat inventory |
| Reconciliation | `TC054` | `TEST-WF011-TC054` | RMA numbers, reason taxonomy, return notes and the neighbouring DataOne picking fields, v17 → v19 |

Files: `test_boxes.py` (TC151–155, TC157) · `test_delivery_security.py`
(TC158–161) · `test_blind_ship_documents.py` (TC162–165, TC156) ·
`test_valuation_and_reports.py` (TC166, TC168, TC011) ·
`test_reconciliation.py` (TC054).

## Expected outcome per test

| Test | v17 | v19 | Why |
|---|---|---|---|
| `TC011` | **FAIL** | PASS once a single default is signed off | Step 5 asserts exactly one `default=True` paperformat; v17 has three custom claimants plus two core ones. The workbook's own live v17 defect — the assertion is not weakened |
| `TC054` | PASS (baseline captured) | PASS if nothing moved | Read-only capture; any diff is a real finding |
| `TC151` | PASS | ORM half PASS, kanban-template assertion is the split result the workbook predicts | `kanban-box` → `card` |
| `TC152` | PASS | PASS | The destructive path is ported verbatim |
| `TC153` | PASS | PASS | Nothing in the delta touches either guard |
| `TC154` | PASS | PASS | The `== 0` constraint is preserved; `Stock Weight` survives |
| `TC155` | PASS | PASS | `page[@name='extra']` confirmed present on v19 |
| `TC156` | Offline half PASS, then **BLOCKED** | **BLOCKED** | PrintNode is dropped for v19 with no replacement model |
| `TC157` | PASS | PASS | Base fields still carry a compute on v19, so the redefinition still means something |
| `TC158` | PASS | `AttributeError` on an unported file — `user_has_groups` is gone | Loud, as the workbook says |
| `TC159` | PASS | PASS | |
| `TC160` | PASS | PASS, wider blast radius — v19's `_has_group` is transitive | |
| `TC161` | PASS | PASS — core still ships `process_cancel_backorder`, so the inherit resolves | The "loud good outcome" will not occur |
| `TC162` | PASS | PASS | |
| `TC163` | PASS, or **BLOCKED** if the PDF yields no extractable signal | The predicted silent failure: renders fine, section count drops to 1 | |
| `TC164` | Structural half PASS, then **BLOCKED** | Structural half **FAIL on the header** | v19 kept the header hook on `bold` only |
| `TC165` | PASS | Boxes half PASS; label half **BLOCKED** | The table renders under `t-if="o.shipping_label_ids"` |
| `TC166` | PASS | PASS with a **lower count** | v19 batches valuation into one `account.move` |
| `TC168` | **FAIL** | **FAIL** | `self.id` instead of `res.id`; preserved deliberately in the port |

## v17 → v19 deltas that affect this suite

| Concern | Odoo 17 | Odoo 19 | Consequence here |
|---|---|---|---|
| Kanban card template | `<t t-name="kanban-box">` | `<t t-name="card">` (`kanban_arch_parser.js:8`) | TC151 step 13 — routed through `common.kanban_card_template(ctx)` |
| `external_layout` header hook | `t-att-style="report_header_style"` on all four (`:309, 368, 430, 492`) | on `bold` only (`:439`) | **TC164's silent v19 failure** |
| New layouts | — | `_folder` `:563`, `_wave` `:651`, `_bubble` `:724` | Unpatched by F048; another blind-slip exposure |
| `user_has_groups` | `odoo/models.py:1542` | **removed** | TC158 — F179's call site is the named migration item |
| `res.users` groups m2m | `groups_id` (`:384`) | `group_ids` (`:257`) | Every fixture uses `ctx.adapter.user_groups_field` |
| `_has_group` semantics | explicit membership only (`:1096-1110`) | transitive via `all_group_ids` (`:1085-1104`) | TC160's blast radius widens on v19 |
| `res.groups` | `users`, `category_id` | `user_ids`, `privilege_id` | Both WF-011 group records are `noupdate="1"` |
| List view type | `tree` | `list` | `fg_common.list_tag` / `adapter.list_view_type`; kills `xpath expr="/tree"` in `shipping_label_views.xml` |
| `tree_view_ref` | valid | `list_view_ref` | TC156 step 10's detector |
| `stock.move.name` | required (`:30`) | absent, `_rec_name='reference'` (`:22`) | `common.move_values` sets it conditionally |
| `stock.picking.shipping_weight` | `stock_delivery`, unstored compute | core `stock`, **stored** compute (`:666-670`) | The v19 upgrade recomputed it, zeroing 3,167 entered values (D-new-10) |
| `stock.move.account_move_ids` | O2M (`stock_account/models/stock_move.py:19`) | `account_move_id` M2O (`:51`) | TC166's count drops; the ported compute uses `\|` |
| `ir.actions.report.groups_id` | `:137` | `group_ids` `:182`, plus new `domain` `:192` | TC011 step 8 |
| `report.paperformat` | — | one new field `css_margins` (`:189`) | All 16 DataOne references are otherwise safe |
| `stock.picking.sale_id` | related stored (`sale_stock/models/stock.py:94`) | compute + inverse, stored (`:187`) | The related chain for `ship_blind` still resolves |
| `stock.backorder.confirmation` | `process` `:52`, `process_cancel_backorder` `:70` | `:49` / `:67`, button still present | BR-1's silent risk stands |
| `location_barcode_labels` / `printnode_base` | shipped in `3rd-addons/`, v17 builds | **purchased v19 builds are an environment precondition** (TC001 E3/E4), not a source fact | TC011 requires no module — it logs the installed set and records absent xml ids rather than BLOCKing. A bare `version: "2.0"` manifest passes v19's gate: `adapt_version` (`odoo/modules/module.py:550-568`) returns `"19.0.2.0"` and `check_version` (`:569-579`) accepts it |

## Adaptations — documented, never assertion-weakening

1. **TC054's `ship_blind` SQL cannot run.** `stock.picking.ship_blind` is a
   non-stored **related** field, so `stock_picking` has no such column on
   either version. The capture reads `sale_id.ship_blind` (stored) and records
   the order-level count beside it.
2. **TC054's `packing_slip_attachment` SQL cannot run either.** That field is
   `fields.Binary` with the default `attachment=True`
   (`dto_purchase_stock/models/stock_picking.py:14-16`;
   `odoo/fields.py:2334-2348` gives `column_type = None`), so it has no column.
   It is counted through `ir.attachment` on `res_field`. Also recorded:
   `packing_slip_attachment` and `carrier_tracking_ref` belong to
   `dto_purchase_stock` and `vendor_refund_narration` to `dto_account` — none
   of the three to the modules the workbook names.
3. **TC011 and TC054 run through the ORM, not psql**, so neither can report
   BLOCKED for a missing `pg_*` config. Everything the workbook's SQL asks for
   lives in ordinary, readable models.
4. **TC157 step 10 uses `fields_get`, not `_fields[...].compute`.** The latter
   is not reachable over RPC. The proxy asserted is `depends == []` **and**
   `store is True` **and** `readonly is False`
   (`odoo/fields.py:861-873`) — which distinguishes "compute genuinely off"
   from "compute coincidentally quiet", the workbook's stated intent.
5. **TC155's "not present in the rendered form" is asserted as a modifier.**
   BR-4 is a view modifier evaluated client-side, so the four elements exist
   in the arch for every picking type. What is asserted is the modifier
   expression byte-exact, the four elements' containment in that div, and
   step 8's `picking_type_code` values — plus step 7's anti-vacuity control,
   which is the half that actually catches the v19 failure mode.
6. **TC163 prints through `/report/pdf/`, never `/report/html/`.** The HTML
   route bypasses the override under test. Section counting uses a stdlib page
   detector first and a `zlib` text extractor second; if neither yields a
   signal the case reports BLOCKED naming the missing PDF library rather than
   asserting against an empty string.
7. **TC164 implements the suppression *mechanism* and blocks on the text.**
   Every negative in steps 5-10 and 12 is true only of the rendered PDF — in
   HTML the same content is present under `display:none` / `d-none`. The
   structural half (header style, footer style, three `d-none` blocks, the
   `<h2>`, the contact-widget options, and step 13's control) catches both
   named failure paths and is what runs.
8. **TC165 is split.** The boxes / note / memo half is unconditional; the
   shipping-label half is guarded by
   `field_exists('stock.picking', 'shipping_label_ids')` and reports BLOCKED
   on v19 with the PrintNode reason.
9. **TC165 step 9 counts populated cells, not `<td>` elements.** 13 boxes wrap
   into 2 rows of 12 and the template pads the short row
   (`report_delivery_document.xml:46`), so the grid holds 13 populated + 11
   empty = 24 `<td>`.
10. **TC168 steps 8 and 9 are recorded, not manufactured.** Step 8 needs a
    browser; its RPC equivalent is the same code path as step 4. Step 9's mass
    write does **not** reproduce the error — the compute is
    `@api.depends('state')` only, and writing `note` invalidates nothing. A
    `state` write would, but that is not a legal direct write, so the
    divergence is documented rather than forced.
11. **TC156 step 9 corrects the workbook.** `label_status` is read-only in the
    embedded **list** (`shipping_label_views.xml:12-14`), not in the form —
    dto_stock sets only `create`/`edit` on `/form`. The list is what is
    asserted.
12. **Every fixture order defaults to `order_type='buy'`** so a delivery
    assertion can never fail for an accounting reason (F040 excludes `buy`),
    and every order carries a non-empty `memo_to_suppliers`.
13. **TC154 step 9's "record in findings/"** is outside this suite's write
    scope; it is expressed as `ctx.log` plus an artifact.

## Environment dependencies — every one probed, never assumed

| Requirement | Why | Probe |
|---|---|---|
| The server loaded the **v17 checkout** | `dto.conf` points `addons_path` at the DTO-Odoo working tree, which is on branch `UAT` — the v19 port — while the baseline is branch `main` | `require_module_build` |
| Every `ir.mail_server` deactivated | Reaching `done` fires the shipment automation's `send_mail(force_send=True)` to hard-coded `@d1systems.com` addresses | `require_mail_offline`, called inside `confirm_order` and `validate_delivery` |
| Non-empty `memo_to_suppliers` on every fixture order | The unguarded `'IRM' in …` raises `TypeError` inside the validation transaction | built into `make_sale_order` |
| Company on `web.external_layout_standard` | F048 replaces `div[@name='moto']` on that layout only, so `PACKING SLIP` is absent under any other | `require_standard_layout` (blocks; never edits the company) |
| `wkhtmltopdf` reachable | TC163 / TC164 have no other route to the override | `report_pdf` blocks with the reason |
| `dto_account` analytic plans resolve | `buy` needs a contract-plan account, `project` a project-plan one, `inventory` / `cost_center` **none** | `analytic_distribution_for` |
| `dto_mrp_account` groups resolve | F179 / F180 are the whole subject of four cases | `require_delivery_groups` |
| `printnode_base` installed | TC156 and TC165's label half | `require_printnode_labels` → the D-1 BLOCKED reason |
| `dto_stock` box models present | F077 | `require_boxes` |
| `stock.picking.account_move_ids` present | F080 and the E-1 defect | `require_journal_entry_button` |

`ctx.sql` is **not** required by any case in this suite.

## `[UNVERIFIED]` claims and what would validate each

| # | Claim | What validates it |
|---|---|---|
| 1 | Which checkout `localhost:8076` actually loaded | `require_module_build` asserts `ir.module.module.latest_version` starts with the target series and logs the on-disk version beside it (`odoo/addons/base/models/ir_module.py:284-288` — the two field labels are inverted in core) |
| 2 | Whether this `wkhtmltopdf` build leaves `/Type /Page` and the text operands greppable | One real render. TC163 reports BLOCKED naming the missing PDF library if not |
| 3 | The exact refusal text for a write to a read-only related field (`ship_blind`, TC162 step 8) | Captured on the live target; not asserted from source |
| 4 | How many `report.paperformat` rows carry `default=True` on `dto_17`, and which module owns the winner | TC011 step 4 — the workbook's own open question |
| 5 | Whether anyone belongs to `dto_mrp_account.group_transfers_read` | `res_groups_users_rel` on `dto_17`. If empty, F180 is a REMOVE candidate and TC160 is retired rather than ported |
| 6 | Whether `base.automation` records are **active** on the QA clone | Read `base.automation.active`. Do **not** assume, and do **not** deactivate it — that would modify a pre-existing business record |
| 7 | `shipping.label` / `shipping_label_document` row counts on `dto_17` | WF011a-README states 0; not re-measured in this pass |
| 8 | Whether each TC163 fixture picking stays within one PDF page | wkhtmltopdf repeats the header per page, so a spill adds a second `PACKING SLIP`; the fixture keeps one line per picking |

## Open questions for the product owner

1. **Which single paperformat is the system default?** Three custom modules
   claim it today, and a Dymo-sized default leaking into invoices is the named
   risk. TC011 is the first place the project has to state one answer.
2. **Should a negative box weight be rejected?** Tightening `== 0` to `<= 0`
   changes TC154 step 8's expected result, which must then be updated with the
   decision recorded — not edited quietly to match new behaviour.
3. **Is F179's single-warehouse assumption acceptable?** A second outgoing
   operation type is entirely unprotected.
4. **Does anyone belong to *Cannot edit transfers*?** If not, F180 is a REMOVE
   candidate.
5. **TC168's governance conflict.** This case asserts "must not raise" while
   the v19 module's own probe asserts that it still does. Both cannot be
   right; the workbook expectation is immutable, so the disagreement is
   surfaced rather than resolved in a test file (WF011a-README `# D-new-11`).

## Finish check

```
venv/Scripts/python.exe -c "from framework import registry; print(len(registry.discover()))"
```
