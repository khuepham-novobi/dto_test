# DATAONE-WF-015 — Per-Line Receipt, Quality Check & Packing Slip · Automation Plan

| | |
|---|---|
| Workflow | `DATAONE-WF-015` |
| Build order | 12 (Purchasing / Inventory) |
| Effective risk | **CRITICAL** · fail mode **loud + silent** |
| Owns | 21 workbook test cases — **4 of them P0** |
| Suite | `tests/wf015/` |
| Modules | `dto_purchase_stock`, `stock_picking_auto_create_lot`, with `dto_base`, `dto_reports`, `printnode_base`, `location_barcode_labels` on the edges |
| Features | F063, F066, F067, F068, F069, F070, F071, F072, F075, F076, F086, F094 |

## Result

| | Count |
|---|---:|
| Implemented | **19** |
| Blocked stub | 1 (`TC210`) |
| Not implemented | 1 (`TC015`) |
| **Total** | **21** |

Per-case reasons: `reports/data/wf015_feasibility.json`.

---

## The fact that governs every test in this suite

**The addons tree on disk is already a partially-migrated v19 port, and as it
stands it cannot be loaded by Odoo 17.**

`dto_purchase_stock/__manifest__.py:9` declares `19.0.0.0`. Three independent,
verified hard failures follow:

| # | Where | Why v17 refuses it |
|---|---|---|
| 1 | `models/purchase_order.py:34` | `@api.depends('picking_ids.move_ids.account_move_id')`. `stock.move.account_move_id` is **v19-only** (`odoo-19.0/addons/stock_account/models/stock_move.py:51`); v17 has the plural `account_move_ids` One2many (`odoo-17.0/addons/stock_account/models/stock_move.py:19`). Registry-build `ValueError` — the module does not install. |
| 2 | `views/stock_picking_views.xml:36` | Root `<list>` element. v17's `ir.ui.view` has no `list` type (`ir_ui_view.py:163`). |
| 3 | `views/quality_check_views.xml:15` | Anchors `<field name="lot_ids">`. v17 Enterprise carries `lot_id` (`enterprise-17.0/quality_control/views/quality_views.xml:246`); `lot_ids` appears only on v19 (`enterprise-19.0/…:236`). The xpath resolves to nothing → install abort. |

**Consequence for automation.** Whatever the v17 target serves over RPC is an
**older installed database revision**, not this source. Every fact about the
*running* v17 instance is therefore `[UNVERIFIED]` until a live `fields_get` /
`get_view` confirms it. Every WF-015 test opens with a capability probe from
`tests/wf015/common.py` and reports **BLOCKED with a precise reason** rather
than FAIL:

```
require_dto_purchase_stock   require_packing_slip      require_print_packing_slip
require_label_wizard         require_quality_control   require_reason_for_return
require_auto_create_lot      require_journal_entries   require_carrier_fields
require_second_company       require_source_root
```

No server was started and no database was touched while this plan was written.

---

## Scope

### In scope

* The per-line receipt override (F066) and everything observable after
  `purchase.order.button_confirm`.
* The deadline-regroup engine (F067) driven through the **public**
  `purchase.order.line.write({'date_planned': …})`, including new-receipt
  creation and the cancellation of emptied receipts.
* The fully-received expected-arrival lock (F068) and its exact `UserError`.
* Packing-slip capture, its mimetype constraint and the PO stat button (F069).
* The merged packing-slip print and its `ir.attachment` (F070), offline only.
* Dymo and ZPL receipt labels rendered over the HTTP report route (F071).
* The 19-code Reason-for-Return vocabulary and its three copies (F072).
* Carrier / tracking-reference editability and chatter tracking (F075).
* The PO Journal Entries stat button union (F076).
* Auto-lot creation at validation and the tracked-without-auto-lot path (F086).
* Two read-only reconciliation cases (`TC032`, `TC047`) and the regroup
  baseline (`TC205`).

### Out of scope

* Physical label printing, scan quality, print darkness and label stock —
  the workbook marks these Manual (E8) and routes them to UIX.
* PrintNode job delivery (`TC210`) — an outbound integration, forbidden by
  convention rule 4, and deleted from the product by decision D-1.
* The procurement / licensing gate (`TC015`).
* The exact debit/credit shape of the receipt valuation entry — the workbook
  assigns it to VAL; `TC220` steps 9–10 assert reachability only.
* Core product-label templates (F094, alternative flow A1) — five xpaths that
  belong to WF-000's install smoke, not to a functional case here.
* `dto_stock`'s `_compute_account_move_ids` singleton defect (E5 / F080) — it
  lives at `dto_stock/models/stock_picking.py:32` and belongs to INV/TC167–168.

### Assumptions

* The v17 target is a dedicated `_qa` clone with crons, mail servers and the
  SFTP connector deactivated (`docs/AUTOMATION_CONVENTIONS.md`, Environment
  facts).
* A v19 *instance* may not exist; when it does not, the runner preflight marks
  those runs BLOCKED automatically. Every test is written version-aware
  regardless.

### Dependencies

* `config/local.yaml` must carry `pg_*` for `TC032` and `TC047`, and
  `DTO_SOURCE_ROOT_<version>` for the static greps.
* Odoo Enterprise `quality_control` for `TC214`.
* `img2pdf` and `Pillow` on the Odoo server for `TC209`/`TC211`.

---

## Verified source facts

Every claim below was read in the real source before any assertion was
written (hard rule 6). The same citations are carried in the docstring of
`tests/wf015/common.py`, so a test author never has to trust this document.

### `dto_purchase_stock/models/stock_picking.py`

| Fact | Line |
|---|---|
| `import img2pdf` / `from PIL import Image` — unconditional, module level | `:6-7` |
| `packing_slip_attachment_name = fields.Char(...)` | `:13` |
| `packing_slip_attachment = fields.Binary(...)` — **no `attachment=True`**, so a column, not an `ir.attachment`; `copy=True` by default | `:14-16` |
| `carrier_tracking_ref` redefinition — `copy=False, tracking=True` | `:17-19` |
| `carrier_id` redefinition — `check_company=True, tracking=True` | `:21-24` |
| `_check_packing_slip_attachment_mimetype` — `@api.constrains('packing_slip_attachment_name')`; calls `_compute_mimetype({'name': …})` | `:27-33` |
| The 10-value mimetype whitelist | `:34-39` |
| `ValidationError(_('File type is not supported. Please upload a PDF or image file'))` — **no trailing period** | `:40` |
| `_get_date_deadline` — tz-localise then `.date()` | `:42-51` |
| `action_open_receipt_product_label_layout` — PUBLIC; **replaces** `action['context']` | `:53-61` |
| `_convert_image_stream_to_pdf_stream` — PRIVATE; `UserError('Cannot convert image to PDF: …')` | `:63-85` |
| `action_print_attached_packing_slip` — PUBLIC | `:87-148` |
| …`self.filtered(lambda r: r.packing_slip_attachment)` — slipless receipts dropped **silently** | `:89` |
| …image page sized from `company_id.paperformat_id.print_page_width/height` | `:98-103` |
| …`_merge_pdfs` used as a context manager | `:107` |
| …ONE `ir.attachment`, `name='Packing Slip'`, `res_model='stock.picking'`, **no `res_id`** | `:110-117` |
| …success return is an `act_url` **and nothing else** — no toast | `:134-138` |
| …empty return: `display_notification`, message `There are no attachments to print.` (**with** the period) | `:140-147` |

### `dto_purchase_stock/models/purchase_order_line.py`

| Fact | Line |
|---|---|
| `_get_candidate_pickings_dict_to_assign` — PRIVATE | `:35-54` |
| Pool predicate `[('state','not in',('done','cancel')), ('location_dest_id.usage','in',('internal','transit','customer'))]` | `:41-44` |
| `_create_stock_moves(picking)` — ignores the argument, creates a fresh picking per line | `:56-72`, creation at `:66` |
| **No** `.filtered(lambda l: not l.display_type)` guard (core has it: v17 `purchase_stock/models/purchase_order_line.py:337`, v19 `:366`) | `:64` |
| `_update_move_date_deadline` — snapshots the pool **before** `super()` | `:74-90` (`:78-81`) |
| `_check_fully_received_lines` — `product_type in ('consu','product')` AND `order_id.state in ['purchase','done']` AND `float_compare(...) == 0` | `:92-103` |
| The exact `UserError`, an **f-string not wrapped in `_()`**, interpolating `product_id.display_name`, **no trailing period** | `:104` |
| `write` — PUBLIC; guard skipped when `product_uom` or `product_qty` is in `vals` | `:106-110` (`:107`) |

### `dto_purchase_stock/models/stock_move.py` (all private)

`_get_date_deadline` `:9-18` · `_update_picking` `:20-32` (move write `:25-27`,
move-line write `:28-30`, `empty_pickings.action_cancel()` `:31-32`) ·
`_update_date_from_date_deadline` `:34-39` ·
`_reassign_picking_by_date_deadline` `:41-66` (skip filter `:42-46`,
new-receipt branch `:60-63`).

### `dto_purchase_stock/models/purchase_order.py`

`packing_slip_receipt_ids` / `_count` non-stored computes `:10-16` ·
`account_move_ids` non-stored `:17-19` · `_compute_account_move_ids` `:32-39` ·
`_compute_receipt_with_attachment` `:41-45` ·
`action_view_packing_slip_attachments` PUBLIC `:47-60` (the literal `'tree'` at
`:53`) · `action_view_journal_entries` PUBLIC `:62-77`, returns `None` on an
empty union (`:63-64`) and has **no `ensure_one()`** (`:62`).

### Wizards and quality

| Fact | Where |
|---|---|
| `stock.picking.product.label.layout` TransientModel; `picking_id` required; `print_format` default `'dymo'`, required | `wizard/receipt_product_label_layout.py:8-19` |
| `_prepare_report_data` PRIVATE; `process` PUBLIC; `UserError('Unable to find report template for %s format')`; `close_on_report_download` | `:21-38` (`:35`, `:36-37`) |
| `quality.check.reason_for_return` — 19 values `'901'`–`'919'`, **no `required=`, no default, no tracking** | `models/quality_check.py:6-27` |
| `quality.check.wizard.confirm_fail` — PUBLIC; writes the code onto **every** `check_ids` record **before** `super()` | `wizard/quality_check_wizard.py:30-34` (`:32`, `:34`) |
| The taxonomy's **third** copy | `3rd-addons/stock_picking_auto_create_lot/models/stock_picking.py:11-33` |
| All three copies are **identical key-for-key and label-for-label** — verified programmatically, including the Unicode EN DASH (U+2013) in `'902'` where `'903'`/`'904'` use an ASCII hyphen | this run |

### Views, actions and reports

| XML id | Where | Notes |
|---|---|---|
| `view_picking_form_inherit_dto_purchase_stock` | `views/stock_picking_views.xml:3-29` | label button `:9-13` (`invisible="picking_type_code != 'incoming'"`); `readonly="0"` forcings `:15-20`; packing-slip fields `:21-27` |
| `packing_slip_attachment_tree` | `:31-42` | `priority` 1000 `:34`; root `<list … create="0" edit="0" delete="0">` `:36`; columns `:37-39` |
| `action_print_attached_packing_slip` (server action) | `:44-54` | `binding_view_types` = `list`; body just calls the public method |
| `purchase_order_form` | `views/purchase_order_views.xml:4-28` | paperclip button with `widget="statinfo"` `:15` and `groups="stock.group_stock_user"` `:14`; **Journal Entries button has no counter widget at all** — static label `:22-24`, `invisible="not account_move_ids"` `:21` |
| `quality_check_view_form_inherit_dto_purchase_stock` | `views/quality_check_views.xml:3-19` | anchors `lot_ids` `:15`; injects with `invisible="quality_state == 'pass'"` `:16` |
| `quality_check_wizard_inherit_dto_purchase_stock` | `wizard/quality_check_wizard.xml:3-14` | anchors `additional_note`; the injected field carries **no** invisible modifier |
| `action_stock_picking_product_label_layout` | `wizard/receipt_product_label_layout_views.xml:19-24` | `target=new`, **no context, no binding** |
| `report_receipt_product_label_dymo` | `reports/report_views.xml:4-12` | `qweb-pdf`; paperformat `dto_base.paperformat_dto_label_sheet_dymo` `:10`; `print_report_name` `:11`. **No groups field.** |
| `report_receipt_product_label_zpl` | `:14-21` | `qweb-text`; **no paperformat**. **No groups field.** |
| `paperformat_dto_label_sheet_dymo` | `dto_base/reports/report_views.xml:43-56` | 51 × 102 mm Landscape, margins 0, `disable_shrinking` True, dpi 96, and `default` **eval="False"** (`:45`) — a port change from the v17 `True` |
| `security/ir.model.access.csv` | `:2` | exactly ONE row: the label wizard for `base.group_user`, `1,1,1,1`. No `res.groups`, no `ir.rule` anywhere in the module. |

### The label templates (`reports/report_receipt_product_label.xml`)

* Loop: `docs → o.move_ids → move.move_line_ids` — Dymo `:56-63`, ZPL `:72-77`
  ⇒ **one label per `stock.move.line`**.
* SKU barcode + human text `:9-14`; lot from `lot_id.name or lot_name` `:18-26`;
  `received_date` `:30` set from `context_timestamp(move.date).date()
  .strftime('%m/%d/%Y')` at `:60` / `:76`.
* Dymo: `QTY:` with **no space** then `int(move_line.quantity)` `:38-40` — the
  E4 truncation defect.
* ZPL field origins: SKU `^FO270,60` `:84`; lot `^FO120,60` `:90`; date
  `^FT40,60` `:94` (leading space after `^FD`); qty `^FT40,590` with
  `QTY: ` **including** a space `:108`.
* **Three** ZPL layout branches, not the two the workbook names:
  `len(purchase_source) > 14` → `^FT40,230` `:98`; `<= 14` → `^FT40,290` `:101`;
  `purchase_source` falsy → `^FT40,380` `:106`.

### `stock_picking_auto_create_lot` (OCA)

`product.template.auto_create_lot` `models/product.py:9` ·
`stock.picking.type.auto_create_lot` `models/stock_picking_type.py:9` ·
`_get_lot_sequence` → `ir.sequence.next_by_code("stock.lot.serial")`
`models/stock_move_line.py:10-12` · `_set_auto_lot` `models/stock_picking.py:46-60`
(picking filter `:50`, line filter `:51-58`, write `:60`) · `_action_done`
`:62-64` and **PUBLIC** `button_validate` `:66-68`, both calling `_set_auto_lot`
before `super()` · `_compute_display_assign_serial` forces `False` **only** when
both flags are set `models/stock_move.py:18-22`.

---

## v17 ↔ v19 deltas that affect this suite

| Concern | Odoo 17 | Odoo 19 | Effect here |
|---|---|---|---|
| `purchase.order.picking_ids` | `@api.depends('order_line.move_ids.picking_id')`, `purchase_stock/models/purchase_order.py:19,22-25` | identical, `:22,44-47` | An empty picking is **never** on it — every receipt count in this suite reads `picking_ids` |
| `_create_picking` cleanup | none — its own empty receipt survives, `:237-261` | `created_receipt.unlink()` at `:400-401` | Counting by `origin` gives **N+1 on v17, N on v19** — a version delta that would masquerade as a regroup difference (TC201, TC205) |
| `_prepare_picking` | `:217-235`; has `date`, creates `group_id`; raises `UserError("You must set a Vendor Location for this partner %s")` at `:224` | `:358-373`; **no `date`**, uses `reference_ids` | `ensure_vendor` sets `property_stock_supplier` explicitly |
| `purchase.order.line.product_uom` | `purchase_order_line.py:34` | **`product_uom_id`** `:36` | `common.po_line_uom_field`; also silently disables half the TC206 bypass, which still tests the literal `'product_uom'` (`purchase_order_line.py:107`) |
| `purchase.order.line.product_type` | related `product_id.detailed_type` `:37` | related `product_id.type` `:38` — **survives** | The workbook's "removed in v19" claim is **wrong**; the guard's `in ('consu','product')` still matches |
| `purchase.order.line.taxes_id` | `:33` | `tax_ids` `:34` | `common.po_line_tax_field` |
| `purchase.order.line.product_qty` | compute + store + `readonly=False` `:21-22` | plain `required=True` `:23` | fixtures always pass it explicitly |
| `purchase.order.state` | includes `('done','Locked')` `:98-105` | `'done'` removed `:105-111`; `locked` Boolean `:112-115` | TC206 step 12 is **v17-only**; TC032's whole subject |
| `stock.move.account_move_ids` | One2many, `stock_account/models/stock_move.py:19` | singular `account_move_id` `:51`; inverse `account.move.stock_move_ids` `account_move.py:8` | Registry-build failure #1 above; guards TC220 |
| `stock.picking.action_cancel` | `stock/models/stock_picking.py:950-954` | `:1211-1215` — **byte-identical** | TC204 steps 4–7 hold on both |
| `stock.picking._compute_state` | stored, depends on `move_ids.picking_id`; no moves ⇒ `'draft'` `:626-673` (`:656-657`) | same shape, `:816-…` (`:845-846`) | TC204 must re-read `state` through a **fresh** query |
| `stock.move._compute_display_assign_serial` | `has_tracking == 'serial' and display_import_lot` `:206` | `display_import_lot` alone `:264` | Agrees for **serial**, differs for **lot** — TC216 pins `tracking='serial'` |
| `ir.attachment._compute_mimetype` | `ir_attachment.py:307-327` | `:353-373` — **identical** | TC208 step 8 is answered from source, not probed |
| `ir.actions.report._merge_pdfs` | `ir_actions_report.py:689` | `:795` (+ `_handle_merge_pdfs_error` `:791`) | **Not renamed.** The single positional call is compatible with both |
| `ir.actions.report` groups m2m | `groups_id` `ir_actions.py:134,170` | `group_ids` `:168,204` | **Does not touch** either label report — neither declares the field |
| `ir.ui.view.type` list value | `'tree'` `ir_ui_view.py:163` | `'list'` `:149` | `fg_common.list_tag(ctx)`; also registry failure #2 above |
| `res.users` groups m2m | `groups_id` | `group_ids` | `ctx.adapter.user_groups_field` |
| Storable product | `type='product'` | `type='consu'` + `is_storable` | `ctx.adapter.storable_product_values()` |
| `stock_delivery` picking form | `carrier_id` **and** `carrier_tracking_ref` both `readonly="state in ('done','cancel')"`, `delivery_view.xml:23,27`, injected into **every** picking form `:14-57` | `:23` keeps the first; `:28` **drops** the second | TC219 — see the correction below |
| Enterprise `quality.check` lot field | `lot_id`, `quality/models/quality.py:188`; view anchor `quality_control/views/quality_views.xml:246` | `lot_ids` Many2many; anchor `enterprise-19.0/…:236` | Registry failure #3 above; guards TC214 |
| `quality.check.wizard.confirm_fail` | `quality_control/wizard/quality_check_wizard.py:87-91` | `:97` — still public | TC214 steps 8–9 reachable on both |
| `uom.uom.rounding` | stored `uom_uom.py:66` | computed `:39` (`_compute_rounding` `:62-67`) | Still readable; TC215 step 9 reads `number_increment`, not rounding |

---

## Per test case

| Group | Workbook TCs | Platform tests | What is proven |
|---|---|---|---|
| Per-line receipts and re-promising | `TC201`–`TC204`, `TC206` | `tests/wf015/test_repromise.py` | Three receipts from a three-line PO, one line each; a re-promise relocating a move by deadline with its id and move lines intact; a new receipt when nothing matches; the emptied receipt cancelled, not deleted; the fully-received lock and its exact message |
| Packing slip | `TC207`–`TC211` | `tests/wf015/test_packing_slip.py` | PDF and JPEG accepted; every other extension refused with the exact `ValidationError`; the merged PDF, its single `ir.attachment` and its download action; PrintNode blocked; the exact "no attachments" notification |
| Labels and quality | `TC212`–`TC214` | `tests/wf015/test_labels_and_quality.py` | One Dymo label and one ZPL block **per `stock.move.line`**, with SKU, lot, date, PO and the truncated QTY; the three ZPL layout branches; the 19 codes, their propagation across `check_ids` and the three-way taxonomy comparison |
| Auto-lot | `TC215`, `TC216` | `tests/wf015/test_lots.py` | Auto lot names drawn from `stock.lot.serial`, distinct, sequence advanced by exactly N; a vendor lot surviving; a tracked product **without** the flag consuming nothing |
| Receipt fields, money, smoke | `TC219`, `TC220`, `TC015` | `tests/wf015/test_receipt_fields.py` | Carrier and tracking editable and tracked, `copy=False` on one and not the other; the Journal Entries union and its action; the commercial-module gate recorded as Manual |
| Reconciliation | `TC205`, `TC032`, `TC047` | `tests/wf015/test_reconciliation.py` | The normalised regroup baseline; the PO `'done'` → `locked` conversion and its surviving source expressions; attachment counts, bytes and checksums by model |

### Expected v17 outcome per test

| Test | Expected on v17 | Why |
|---|---|---|
| `TEST-WF015-TC015` | NOT_IMPLEMENTED | MANUAL procurement gate |
| `TEST-WF015-TC032` | **FAIL on step 8**, PASS on steps 1–7 | Three surviving `'done'` expressions in `dto_reports/views/purchase_order.xml:53,62,78`. The expectation describes the v19 target state, so rule 2 keeps it failing |
| `TEST-WF015-TC047` | PASS (baseline captured) | The F069 premise defect is **recorded**, not worked around |
| `TEST-WF015-TC201` | PASS | |
| `TEST-WF015-TC202` | PASS | |
| `TEST-WF015-TC203` | PASS | Step 12's state is a captured anchor |
| `TEST-WF015-TC204` | PASS | Step 10 asserts the verified answer (the receipt **drops off** `picking_ids`) |
| `TEST-WF015-TC205` | PASS (baseline persisted) | v19 half BLOCKED by preflight |
| `TEST-WF015-TC206` | PASS | Step 12 is v17-only and passes here; it is the step that fails on v19 |
| `TEST-WF015-TC207` | PASS | |
| `TEST-WF015-TC208` | PASS | |
| `TEST-WF015-TC209` | **FAIL on step 9**, PASS on 1–8 and 11 | No success toast exists in the code (`stock_picking.py:134-138`). Rule 2 |
| `TEST-WF015-TC210` | BLOCKED | Outbound integration; also deleted by decision D-1 |
| `TEST-WF015-TC211` | PASS | |
| `TEST-WF015-TC212` | PASS, with step 15 asserting the E4 truncation defect | `int(...)` at `:39` |
| `TEST-WF015-TC213` | PASS | |
| `TEST-WF015-TC214` | PASS, or BLOCKED with the `lot_ids`/`lot_id` anchor reason | Depends on whether the installed revision carries the field |
| `TEST-WF015-TC215` | PASS, with step 12 rewritten | `_set_quantities_to_reservation` is dead code |
| `TEST-WF015-TC216` | PASS | Step 5 captures the v17 behaviour rather than asserting a guessed literal |
| `TEST-WF015-TC219` | PASS | |
| `TEST-WF015-TC220` | PASS, or BLOCKED when `account_move_ids` is absent | |

---

## Findings this suite records

**1 — `_set_quantities_to_reservation` is dead code (TC215 step 12).**
A full-tree grep of `D:/Projects/dataone/odoo-17.0` and `D:/Projects/odoo-19.0`
returns **zero** definitions and **zero** callers of that name. The only
occurrence anywhere is the OCA override itself
(`3rd-addons/stock_picking_auto_create_lot/models/stock_move.py:26-40`), whose
first statement is `super()._set_quantities_to_reservation()` — an
`AttributeError` if it were ever invoked. The backorder-wizard suppression the
workbook attributes to it **does not happen**. The test asserts the observable
(`button_validate` on a fully quantified receipt returns `True`, not a
`stock.backorder.confirmation` act_window) and logs the finding, attributing
that outcome to nothing.

**2 — the merged-print success toast does not exist (TC209 step 9).**
`dto_purchase_stock/models/stock_picking.py:134-138` returns only an
`ir.actions.act_url`. The single `display_notification` in the method is the
*no-attachments* branch (`:140-147`). The workbook's "Either way a
`display_notification` toast confirms success" describes behaviour that is not
in the code. Implemented as a **failing assertion** per rule 2.

**3 — the mimetype guard inspects the filename, never the content (TC208
step 8).** The constraint hands `_compute_mimetype` a dict carrying only
`name` (`:31-33`), and that method sniffs bytes only when `raw` or `datas` is
present. It is byte-identical on both versions. So `evil.pdf` containing an
executable is **accepted** and a genuine PDF named `scan.dat` is **refused** —
on v17 and v19 alike. The workbook's python-magic concern does not apply. The
test asserts both directions positively.

**4 — F069 is invisible to TC047's queries.** `packing_slip_attachment` is a
plain `fields.Binary` **column** on `stock_picking` (`:14-16`), not an
`ir.attachment`. TC047 step 6's "receipt packing slips" count under
`res_model='stock.picking'` measures chatter attachments and **zero** of this
workflow. The defect is in the test case's premise; the test records it.

**5 — counting receipts by `origin` is a version trap (TC201, TC205).**
v17 leaves core's own empty receipt behind; v19 unlinks it. Every receipt count
in this suite reads `order.picking_ids`, which never contains an empty picking
on either version.

**6 — TC204 step 10's verified answer is the opposite of the obvious one.**
Because `picking_ids = order_line.move_ids.picking_id`, the emptied-and-
cancelled receipt **drops off** the purchase order's `picking_ids`. The
workbook allows "or record whether it does"; the verified behaviour is
asserted.

**7 — TC219's rationale is wrong about which readonly is forced off.**
`stock_delivery` injects its Shipping Information group into **every** picking
form (`v17 delivery_view.xml:14-57`), with `readonly="state in
('done','cancel')"` on both fields (`:23`, `:27`). DTO's unconditional
`readonly="0"` therefore keeps them editable on a **done or cancelled**
transfer — not, as the workbook says, on incoming ones. v19 keeps the first
readonly and has already dropped the second (`:23`, `:28`). Separately, two
tracked fields changed in one `write` produce **one** `mail.message` carrying
**two** `mail.tracking.value` rows, so step 6 is asserted at the tracking-value
level.

**8 — TC220's singleton defect is on the wrong model.** The `purchase.order`
compute uses `res` correctly throughout (`purchase_order.py:35-39`), so a
three-order recompute passes trivially. The `ValueError: Expected singleton`
the workbook anticipates lives at `dto_stock/models/stock_picking.py:32`, which
searches `('picking_id','=', self.id)` inside a per-record loop, and belongs to
INV/TC167–TC168. The test asserts the passing case and logs where the sibling
defect actually is. Distinct from that: `action_view_journal_entries` has no
`ensure_one()` while reading `self.account_move_ids` (`:62`), so a
multi-record call **does** raise — an assertable fact of its own.

**9 — TC220 step 3 has no counter to assert.** Unlike the paperclip button
(`views/purchase_order_views.xml:15`, `widget="statinfo"`), the Journal Entries
button carries only a static label in a `div.o_stat_info` (`:22-24`) and an
`invisible="not account_move_ids"` modifier (`:21`). The test records that as
an arch fact and asserts `len(order.account_move_ids)` directly.

**10 — TC032's grep target is undercounted by the workbook.** There are
**three** surviving `purchase.order` `'done'` expressions in
`dto_reports/views/purchase_order.xml` (`:53`, `:62`, and the
`ir.actions.act_window` domain at `:78`), not two. The `:78` hit is the one
that silently under-reports, and `dto_reports` is still `17.0.0.1`
(`__manifest__.py:10`) — unported. `dto_purchase` has no surviving PO-`'done'`
expression outside tests and a comment; its `purchase_order_line.py:60`
`x.state == 'done'` is a **stock.move** state, correct on both versions, and is
not counted.

**11 — TC213 has three ZPL layout branches, not two.** The third
(`purchase_source` falsy → `^FT40,380`, `:106`) is the default state of a
manually created PO, and the workbook does not mention it.

**12 — TC206's v19 break is loud, not silent.** The workbook classifies the
fully-received lock as silently narrowing. In fact `line.product_uom` at
`:102` no longer exists on v19 (renamed `product_uom_id`), so the first
`date_planned` write raises `AttributeError`. What genuinely narrows silently
is the `state in ['purchase','done']` test, since `'done'` is gone — a locked
order loses protection. And `product_type` does **not** break at all.

**13 — PrintNode is gone by decision (TC209 step 10, TC210, TC015 step 4).**
WF-000 decision D-1 (client, 22 Aug 2026) removed it.
`dto_purchase_stock/models/stock_picking.py:119-138` has collapsed the branch
away; `dto_base/__manifest__.py:17-45` has dropped the dependency; no DTO module
references `printnode_enabled`, the PrintNode group or `dpc_print` any more. The
v17 `printnode_base` build is still physically present at
`3rd-addons/printnode_base` (`__manifest__.py:10` = `'17.0.2.6.10'`).

**14 — four workbook v19-delta claims are wrong** and the tests do not
implement them as stated: `_merge_pdfs` was not renamed; `_compute_mimetype` is
unchanged; the `groups_id` → `group_ids` rename does not touch either label
report (neither declares the field); and `product_type` survives.

---

## `[UNVERIFIED]` claims and what would validate each

| Claim | Why it cannot be settled from source | What would validate it |
|---|---|---|
| What the **running** v17 instance actually exposes for `dto_purchase_stock` | The on-disk source cannot build the v17 registry (three failures above), so the database carries an older revision of unknown vintage | A live `fields_get('stock.picking', ['packing_slip_attachment'])`, `fields_get('purchase.order', ['account_move_ids'])`, `fields_get('quality.check', ['reason_for_return'])` and `ref('dto_purchase_stock.packing_slip_attachment_tree')` — exactly what `common.require_*` performs, reporting BLOCKED on absence |
| The `store_fname` / `checksum` that survive on the merged-print attachment | `create` passes a literal `store_fname='Packing Slip'` **and** `raw=<bytes>` (`:110-117`); Odoo recomputes both from `raw`, but which value wins is decided at runtime | Read the created `ir.attachment` back after one real invocation and capture both fields (TC209 does this and logs them) |
| Whether `'cancel'` survives a later recompute of `stock.picking.state` on the emptied receipt | `state` is a stored compute whose no-moves branch yields `'draft'`; only the recompute-then-force order inside `action_cancel` makes `'cancel'` stick | TC204 re-reads `state` through a fresh `search_read` after the re-promise — the exact condition that would expose a flip |
| The state of the receipt created by the regroup's new-receipt branch (TC203 step 12) | It is created `state='draft'` and nothing in the path calls `action_confirm()` or `_action_assign()`; the stored compute then derives it from the already-confirmed move | Captured as a reconcile anchor; the test asserts only `state not in ('draft','cancel')` |
| The exact `UserError` core raises when a tracked, non-auto-lot receipt is validated (TC216 step 5) | It is core's message, not DTO's, and depends on the picking type's lot configuration | Captured at runtime as a reconcile anchor — the workbook's own instruction is "record which, exactly" |
| Whether `.xlsx` resolves to the Office mimetype or `application/octet-stream` | `mimetypes.guess_type` depends on the **server's** registry; it returns `None` on this workstation's Python 3.12.7 | Irrelevant to the verdict — neither value is whitelisted, so TC208 asserts the **error**, never the resolved mimetype |
| Whether any `quality.point` covers the incoming operation in production | WF-015's own open question; the dataone database was not queried | A read of `quality.point.picking_type_ids` on the live database. TC214 does not depend on it — it creates its own token-namespaced point and unlinks it in `finally` |
| Whether `img2pdf` / `Pillow` are on the Odoo server | Not determinable from the addons tree | `common.require_print_packing_slip` probes whether `action_print_attached_packing_slip` dispatches, and BLOCKS naming the unconditional imports at `stock_picking.py:6-7` |
| Whether a v19 `printnode_base` / `location_barcode_labels` build exists (TC015) | Procurement, not engineering | Vendor delivery. Partly superseded by decision D-1 |
| Merged-PDF page count measured by byte scan | The QA venv has no PDF library (`requirements.txt`; confirmed by `pip list` — no `pypdf`, no `PyPDF2`) | Counting `/Type /Page` objects is a documented **heuristic**. Installing `pypdf` would make it exact; a producer that compresses the page tree into an object stream would defeat it (`_merge_pdfs` does not) |

---

## Adaptations (documented, not assertion-weakening)

1. **TC205 normalises identity out of the cross-version artefact.** The
   workbook's tuple carries `move.id` and `picking.name`; convention rule 5
   forbids relying on either, and step 12 already concedes the name.
   `common.regroup_snapshot` replaces both with deterministic per-run ordinals
   (pickings ordered by `(deadline, id)`, moves by
   `(line ordinal, product code, id)`) and records the deadline **twice** — the
   raw UTC `Datetime` and the tz-localised date the engine actually groups on.
   `pre_pickings` is built from `order.picking_ids`, never from a search on
   `origin`, so the v17 core-empty-receipt delta cannot masquerade as an engine
   difference in step 9.
2. **`res.users.tz` is pinned as a snapshot.** `common.pin_user_timezone`
   records the previous value, writes `America/Chicago`, and
   `restore_user_timezone` puts it back in a `finally` that cannot raise; the
   restoration is then asserted (the WF-013 TC228 precedent). Without it,
   TC202/TC203/TC205 depend on whoever last logged in.
3. **`stock.picking.type` is never modified.** TC215/TC216 need an incoming
   type flagged `auto_create_lot`, so `common.make_picking_type` **copies** the
   warehouse type into a token-named one. `copy` is public and marshals back as
   an id thanks to `@api.returns('self', …)` on `BaseModel.copy`.
4. **Receipts are swept through their partner, not their `origin`.**
   `_prepare_picking` stamps the PO's sequence name into `origin`, so it cannot
   carry the token; the namespaced `partner_id` and `picking_type_id` can.
5. **The merged-print attachment is swept by delta, not by name.** Its name is
   the literal `'Packing Slip'` and it has no `res_id`, so
   `common.print_attachment_ids` snapshots before the call and
   `common.sweep_new_attachments` removes only what this run created —
   deleting by name would destroy other people's rows.
6. **Label assertions run against the HTTP report route.**
   `_render_qweb_pdf` / `_render_qweb_html` / `_render_qweb_text` are private,
   but `/report/<converter>/<reportname>/<docids>` is `auth='user'` (v17
   `web/controllers/report.py:23-50`) and `_get_report` accepts a
   `report_name` (`ir_actions_report.py:565-579`). HTML carries the same
   `docs → move_ids → move_line_ids` loop as the PDF without depending on
   wkhtmltopdf; `text` returns the ZPL verbatim.
7. **TC204 step 9 is an arch-only check** — the absence of any button in
   `stock.view_picking_form` whose `invisible` expression admits
   `state == 'cancel'` — and is labelled as such rather than presented as a
   behavioural claim.
8. **TC203 step 12 and TC216 step 5 record rather than assume.** Both are
   reconcile anchors; what is *asserted* is what must hold either way.
9. **TC219 step 11 skips rather than invents.** A single-company target cannot
   express `check_company=True`, and creating a company would be a master-data
   change; `common.require_second_company` `ctx.skip`s with that reason.
10. **TC010's PrintNode group step (TC210 step 10) is not performable even
    offline.** `printnode_base/security/security.xml:24-26` adds the user group
    to `base.group_user.implied_ids`, so every internal user is implicitly a
    PrintNode user and the membership cannot simply be removed.

---

## Safety

* **Rule 3.** Every fixture carries `WF015` plus a per-execution token in a
  value the sweep matches. Nothing writes to a pre-existing
  `stock.picking.type`, `res.company`, `purchase.order` or `stock.picking`. The
  one snapshot-and-restore is `res.users.tz` (adaptation 2).
* **Rule 4.** Nothing calls `ir.attachment.dpc_print`
  (`3rd-addons/printnode_base/models/ir_attachment.py:9-44`, which pushes bytes
  to the PrintNode HTTPS API at `:31-33`), `printnode_print_b64`,
  `action_test_connection`, or any cron. TC210 asserts its offline half and
  then `ctx.blocked`s. Carrier/tracking writes post `mail.message` tracking
  rows — in-database bookkeeping that sends nothing.
* **Rule 5.** No record ids, no picking names and no time-dependent values
  cross a version boundary; every search is scoped by the execution token.
* **Teardown.** `sweep_wf015` runs children before parents (quality checks →
  quality points → pickings → purchase orders → lots/quants → products →
  operation types → carriers → partners) and is best effort by design: a
  validated receipt cannot be unlinked, and it is the fresh token, not the
  sweep, that guarantees isolation.

---

## Shared test cases

`TC032` and `TC201` also name `DATAONE-WF-014`; `TC047` also names
`dto_account` / `dto_mrp` / `dto_mrp_sftp` workflows. They are implemented once
here, in the suite of the owning workflow, and the other workflows reference
the same `tc_id` rather than re-implementing it
(`scripts/sync_registry.py:owning_workflow`).

---

## Run

```
venv/Scripts/python.exe -c "from framework import registry; print(len(registry.discover()))"
```
