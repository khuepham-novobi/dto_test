"""DATAONE-WF-015 — Per-Line Receipt, Quality Check & Packing Slip: fixtures.

Owning workflow: DATAONE-WF-015, build order 12, effective risk CRITICAL,
fail mode "loud + silent". It owns 21 workbook test cases, 4 of them P0.
Modules under test: ``dto_purchase_stock`` (project-addons),
``stock_picking_auto_create_lot`` (3rd-addons), with ``dto_base``,
``dto_reports``, ``printnode_base`` and ``location_barcode_labels`` on the
edges.

What was read before anything here was written (hard rule 6)
============================================================
Every model, field, method, XML id and error string this suite asserts
against was opened in the real source first. The citations below are the
evidence; nothing in this module is asserted on memory.

``project-addons/dto_purchase_stock``
-------------------------------------
``models/stock_picking.py``

* module imports ``pytz, base64, io, img2pdf, PIL.Image`` — ``:1-7``.
  ``img2pdf`` is a HARD import: absent from the server venv, the whole
  module fails to load and none of F069/F070/F071 exists at runtime.
* ``packing_slip_attachment_name`` ``fields.Char`` — ``:13``
* ``packing_slip_attachment`` ``fields.Binary`` — ``:14-16``. It declares
  **no** ``attachment=`` argument, and ``fields.Binary`` defaults to
  ``attachment=True`` (v17 ``odoo/fields.py:2334-2344``, the class attribute
  at ``:2344`` and the docstring "default: ``True``" at ``:2338``; v19
  ``odoo/orm/fields_binary.py:30-39``, attribute at ``:39``) ⇒ every stored
  payload IS an ``ir_attachment`` row carrying ``res_model='stock.picking'``,
  ``res_field='packing_slip_attachment'``, ``res_id=<picking id>`` and
  ``type='binary'`` (write path v17 ``odoo/fields.py:2457-2473``, read path
  ``:2442-2456``). It is filestore-managed and content-deduplicated —
  ``ir_attachment._file_write`` skips the write when a file of that checksum
  already exists (v17 ``base/models/ir_attachment.py:135-146``, the guard at
  ``:138``). ``copy=True`` (the ``Field`` default, not overridden) so
  ``copy()`` still duplicates the payload onto the new record, as a second
  ``ir_attachment`` row pointing at the same deduplicated file (TC207 s12).
  **This corrects an earlier premise in this module and in
  ``reports/data/wf015_feasibility.json`` that called the field "a column on
  stock_picking"; the corrected reading is the one
  ``tests/wf015/test_reconciliation.py:167-188`` already asserts.**
* ``carrier_tracking_ref`` redefinition — ``:17-19`` —
  ``Char(string='Tracking Reference', copy=False, tracking=True)``
* ``carrier_id`` redefinition — ``:21-24`` —
  ``Many2one('delivery.carrier', check_company=True, tracking=True)``
* ``_check_packing_slip_attachment_mimetype`` —
  ``@api.constrains('packing_slip_attachment_name')`` ``:27-40``. It calls
  ``ir.attachment._compute_mimetype({'name': <name>})`` with a hand-built
  dict carrying ONLY ``name``; the whitelist is ``:34-39``. The exact
  message is ``:40`` (see ``ERROR_PACKING_SLIP_MIMETYPE`` below).
* ``_get_date_deadline`` — PRIVATE — ``:42-51`` —
  ``date_deadline.astimezone(pytz.timezone(env.user.tz or 'UTC')).date()``
* ``action_open_receipt_product_label_layout`` — PUBLIC — ``:53-61``;
  it **overwrites** ``action['context']`` with ``{'default_picking_id': id}``
* ``_convert_image_stream_to_pdf_stream`` — PRIVATE — ``:63-85``; raises
  ``UserError('Cannot convert image to PDF: %s')`` on ``:85``
* ``action_print_attached_packing_slip`` — PUBLIC — ``:87-148``:
  ``self.filtered(lambda r: r.packing_slip_attachment)`` at ``:89``
  silently drops slipless receipts (TC211 s9); the image branch sizes the
  page from ``record.company_id.paperformat_id.print_page_width/height``
  (``:98-103``); ``_merge_pdfs`` is used as a context manager at ``:107``;
  ONE ``ir.attachment`` is created at ``:110-117`` with ``name='Packing
  Slip'``, ``res_model='stock.picking'`` and **no ``res_id``**; the success
  return at ``:134-138`` is an ``ir.actions.act_url`` **and nothing else** —
  there is NO ``display_notification`` toast on the success path (TC209 s9);
  the empty branch at ``:140-147`` returns the notification dict.

``models/purchase_order_line.py``

* ``_get_candidate_pickings_dict_to_assign`` — PRIVATE — ``:35-54``. Pool
  predicate verbatim ``:41-44``:
  ``[('state','not in',('done','cancel')),
  ('location_dest_id.usage','in',('internal','transit','customer'))]``
* ``_create_stock_moves(picking)`` — PRIVATE — ``:56-72``. It **ignores**
  the picking core hands in and creates a fresh one per line at ``:66``.
  It has **no** ``.filtered(lambda l: not l.display_type)`` guard, unlike
  core (v17 ``purchase_stock/models/purchase_order_line.py:338``, v19
  ``:366``) — so a section/note line also gets an empty receipt.
* ``_update_move_date_deadline(new_date)`` — PRIVATE — ``:74-90``. The
  candidate pool and the per-picking deadline map are snapshotted BEFORE
  ``super()`` (``:78-81``).
* ``_check_fully_received_lines`` — PRIVATE — ``:92-104``. Fires when
  ``product_type in ('consu','product')`` AND ``order_id.state in
  ['purchase','done']`` AND ``float_compare(product_qty, qty_received,
  precision_rounding=product_uom.rounding) == 0``.
* ``write`` — PUBLIC, RPC-reachable — ``:106-110``. The guard runs only
  when ``'date_planned' in vals and 'product_uom' not in vals and
  'product_qty' not in vals`` — the documented by-design bypass (TC206 s11).

``models/stock_move.py`` (all PRIVATE)

* ``_get_date_deadline`` ``:9-18``; ``_update_picking`` ``:20-32`` (writes
  ``picking_id`` on the moves ``:25-27`` and on their move lines ``:28-30``,
  then ``empty_pickings.action_cancel()`` ``:31-32``);
  ``_update_date_from_date_deadline`` ``:34-39`` (``move.date =
  move.date_deadline``); ``_reassign_picking_by_date_deadline``
  ``:41-66`` — skip filter ``:42-46``, new-receipt branch ``:60-63``.

``models/quality_check.py`` — ``reason_for_return`` Selection, 19 values
``'901'``–``'919'``, ``:6-27``. **Not required, no default, no tracking.**

``wizard/quality_check_wizard.py`` — the same 19 values ``:6-28``;
``confirm_fail`` — PUBLIC — ``:30-34`` writes the code onto
``self.check_ids`` (``:32``) BEFORE ``super()`` (``:34``).

``wizard/receipt_product_label_layout.py`` — ``stock.picking.product.label.
layout`` TransientModel ``:8-10``; ``picking_id`` required ``:12``;
``print_format`` Selection ``[('dymo','Dymo'),('zpl','ZPL Label')]``
``default='dymo', required=True`` ``:13-19``; ``_prepare_report_data``
PRIVATE ``:21-29``; ``process`` PUBLIC ``:31-38`` — raises
``UserError('Unable to find report template for %s format')`` ``:35``, then
``env.ref(xml_id).report_action(picking_id, data=None, config=False)``
followed by ``.update({'close_on_report_download': True})`` ``:36-37``.

``models/purchase_order.py`` — ``packing_slip_receipt_ids`` /
``packing_slip_receipt_count`` non-stored computes ``:10-16``;
``account_move_ids`` non-stored ``:17-19``; ``_compute_account_move_ids``
``:32-39``; ``_compute_receipt_with_attachment`` ``:41-45``;
``action_view_packing_slip_attachments`` PUBLIC ``:47-60`` (note the
literal ``'tree'`` at ``:53``); ``action_view_journal_entries`` PUBLIC
``:62-77`` — returns ``None`` when ``account_move_ids`` is empty
(``:63-64``) and has **no** ``ensure_one()``.

XML ids, all opened:

* ``views/stock_picking_views.xml`` — form inherit ``:3-29`` (label button
  ``:9-13`` with ``invisible="picking_type_code != 'incoming'"``; the
  ``readonly="0"`` forcings ``:15-20``; the two packing-slip fields
  ``:21-27``); ``packing_slip_attachment_tree`` ``:31-42`` (priority 1000
  ``:34``, root ``<list … create="0" edit="0" delete="0">`` ``:36``,
  columns ``:37-39``); server action ``action_print_attached_packing_slip``
  ``:44-54`` (``binding_view_types`` = ``list``).
* ``views/purchase_order_views.xml`` — the paperclip stat button ``:9-16``
  (``groups="stock.group_stock_user"`` ``:14``, ``widget="statinfo"``
  ``:15``) and the Journal Entries button ``:18-25``, which carries **no
  counter widget at all** — only ``invisible="not account_move_ids"``
  (``:21``) backed by an invisible field at ``:17`` (TC220 s3).
* ``views/quality_check_views.xml`` — anchors ``<field name="lot_ids"
  position="after">`` ``:15``; injects ``reason_for_return`` with
  ``invisible="quality_state == 'pass'"`` ``:16``.
* ``wizard/quality_check_wizard.xml`` — anchors ``additional_note`` and
  injects ``reason_for_return`` with **no** invisible modifier.
* ``wizard/receipt_product_label_layout_views.xml`` — form ``:3-17``,
  ``action_stock_picking_product_label_layout`` ``:19-24`` (target ``new``,
  **no context, no binding**).
* ``reports/report_views.xml`` — ``report_receipt_product_label_dymo``
  ``:4-12`` (qweb-pdf, paperformat ``dto_base.paperformat_dto_label_sheet_
  dymo`` ``:10``, ``print_report_name`` ``:11``) and ``…_zpl`` ``:14-21``
  (qweb-text, **no paperformat**). **Neither record declares a groups
  field** — so the v17 ``groups_id`` → v19 ``group_ids`` rename the workbook
  flags for TC212/TC213 does not touch them.
* ``reports/report_receipt_product_label.xml`` — the loop is
  ``docs → o.move_ids → move.move_line_ids`` (Dymo ``:56-63``, ZPL
  ``:72-77``) ⇒ **one label per ``stock.move.line``**. SKU barcode ``:9-14``;
  lot ``:18-26`` from ``lot_id.name or lot_name``; date ``:30`` from
  ``context_timestamp(move.date).date().strftime('%m/%d/%Y')`` set at
  ``:60``/``:76``; ``QTY:`` **with no space** then ``int(move_line.quantity)``
  at ``:38-40`` (Dymo) versus ``QTY: `` **with** a space at ``:108`` (ZPL).
  The ZPL layout has **THREE** branches, not the two the workbook names:
  ``len(purchase_source) > 14`` → ``^FT40,230`` (``:98``); ``<= 14`` →
  ``^FT40,290`` (``:101``); ``purchase_source`` falsy → ``^FT40,380``
  (``:106``).
* ``security/ir.model.access.csv`` — exactly ONE row (``:2``), the label
  wizard for ``base.group_user`` with ``1,1,1,1``. No ``res.groups``, no
  ``ir.rule`` anywhere in the module.

``dto_base/reports/report_views.xml:43-56`` — ``paperformat_dto_label_sheet_
dymo``: 51 mm × 102 mm, Landscape, all margins 0, ``disable_shrinking``
True, dpi 96, and ``default`` **eval="False"** (``:45``) — changed during
the port; the v17 record had it True.

``3rd-addons/stock_picking_auto_create_lot``
--------------------------------------------
* ``models/product.py:9`` ``product.template.auto_create_lot`` Boolean
* ``models/stock_picking_type.py:9`` ``stock.picking.type.auto_create_lot``
* ``models/stock_move_line.py:10-12`` ``_get_lot_sequence`` — PRIVATE —
  ``ir.sequence.next_by_code("stock.lot.serial")``
* ``models/stock_picking.py`` — ``rma_number`` ``:9``; the THIRD copy of the
  19-value Selection ``:11-33``; ``return_notes`` ``:35``;
  ``_set_auto_lot`` PRIVATE ``:46-60`` (picking filter ``:50``, line filter
  ``:51-58``, write ``:60``); ``_action_done`` ``:62-64`` and
  ``button_validate`` **PUBLIC** ``:66-68``, both calling ``_set_auto_lot``
  before ``super()``.
* ``models/stock_move.py:9-23`` ``_compute_display_assign_serial`` forces
  ``display_assign_serial = False`` ONLY when
  ``picking_type_id.auto_create_lot and product_id.auto_create_lot``
  (``:18-22``).
* ``models/stock_move.py:26-40`` ``_set_quantities_to_reservation`` —
  **DEAD CODE.** A full-tree grep of ``D:/Projects/dataone/odoo-17.0`` and
  ``D:/Projects/odoo-19.0`` finds **zero** definitions and zero callers of
  that name in either core; the only other hit anywhere is
  ``enterprise-17.0/delivery_sendcloud/tests/test_delivery_sendcloud.py:543``
  calling the unrelated ``action_set_quantities_to_reservation``. Its own
  first statement is ``super()._set_quantities_to_reservation()``, which
  would raise ``AttributeError`` if it were ever invoked. TC215 step 12 is
  therefore rewritten to assert the observable (no backorder wizard is
  returned) and to LOG the dead-code finding — it is never attributed to
  this override.

Core v17 ↔ v19 facts this suite depends on
------------------------------------------
* ``purchase.order.picking_ids`` is ``@api.depends('order_line.move_ids.
  picking_id')`` with ``order.picking_ids = order.order_line.move_ids.
  picking_id`` — v17 ``purchase_stock/models/purchase_order.py:36-39`` (the
  field at ``:19``), v19 ``:44-47`` (field at ``:22``). **An empty picking is never on
  ``picking_ids``.** Every "exactly N receipts" assertion in this suite
  counts ``order.picking_ids``, never ``search([('origin','=',name)])``.
* v17 ``_create_picking`` (``purchase_order.py:237-261``) leaves the empty
  receipt it created itself behind; v19 (``:375-405``) unlinks it at
  ``:400-401``. Counting by ``origin`` therefore gives N+1 on v17 and N on
  v19 — a version delta that would masquerade as a regroup difference.
* ``_prepare_picking`` — v17 ``:217-235``: keys ``picking_type_id,
  partner_id, user_id, date, origin, location_dest_id, location_id,
  company_id, state='draft'``; it raises ``UserError("You must set a Vendor
  Location for this partner %s")`` at ``:224`` when
  ``partner.property_stock_supplier`` is empty — which is why
  ``ensure_vendor`` sets that property explicitly. v19 ``:358-373`` drops
  ``date`` and uses ``reference_ids`` instead of ``group_id``.
* ``stock.picking.action_cancel`` is **byte-identical** on both versions
  (v17 ``stock/models/stock_picking.py:950-954``, v19 ``:1211-1215``):
  ``move_ids._action_cancel()``; ``write({'is_locked': True})``;
  ``filtered(lambda x: not x.move_ids).state = 'cancel'``.
* ``stock.picking._compute_state`` is stored and depends on
  ``move_ids.picking_id``; with no moves it yields ``'draft'`` (v17
  ``:656-657``, v19 ``:845-846``) — which is precisely why TC204 must read
  ``state`` back through a FRESH ``search_read`` after the re-promise.
* ``purchase.order.line.product_uom`` (v17 ``purchase_order_line.py:34``)
  → ``product_uom_id`` (v19 ``:36``). ``product_type`` SURVIVES on v19
  (``:38``, related to ``product_id.type``) — the workbook's claim that it
  was removed is wrong. ``product_qty`` loses its compute on v19 (``:23``).
* ``purchase.order.state`` loses ``('done','Locked')`` on v19 (v17
  ``purchase_order.py:98-105`` → v19 ``:105-111``) and gains
  ``locked`` Boolean (v19 ``:112-115``).
* ``ir.attachment._compute_mimetype`` is **identical** on both versions
  (v17 ``ir_attachment.py:307-327``, v19 ``:353-373``) and falls back to
  sniffing ``raw``/``datas`` only when one of those keys is present. The
  constraint passes ONLY ``name`` ⇒ **the guard inspects the filename
  extension and never the bytes**, on v17 and on v19 alike. TC208 step 8 is
  answered from source, not probed.
* ``ir.actions.report._merge_pdfs`` exists on BOTH (v17
  ``ir_actions_report.py:689``, v19 ``:795``; v19 adds
  ``_handle_merge_pdfs_error`` at ``:791``). The workbook's "renamed to
  ``odoo.tools.pdf.merge_pdf``" note is wrong.
* ``stock.move._compute_display_assign_serial``: v17
  ``stock/models/stock_move.py:206`` = ``has_tracking == 'serial' and
  display_import_lot``; v19 ``:264`` = ``display_import_lot`` alone. The two
  agree for a **serial**-tracked product and differ for a lot-tracked one,
  so TC216's fixture pins ``tracking='serial'``.
* ``stock_delivery`` injects the carrier group into **every** picking form,
  not just outgoing (v17 ``stock_delivery/views/delivery_view.xml:14-57``),
  with ``readonly="state in ('done','cancel')"`` on ``carrier_id`` (``:23``)
  and on ``carrier_tracking_ref`` (``:27``). DTO's unconditional
  ``readonly="0"`` therefore keeps them editable on a **done or cancelled**
  transfer — not, as the workbook's rationale says, on incoming ones. v19
  (``delivery_view.xml:23,28``) keeps the first readonly and has already
  dropped the second.
* Enterprise ``quality.check.lot_id`` (v17 ``quality/models/quality.py:188``,
  view anchor ``quality_control/views/quality_views.xml:246``) became
  ``lot_ids`` on v19 (``enterprise-19.0/quality_control/views/
  quality_views.xml:236``). ``quality.check.wizard.check_ids`` is
  ``Many2many('quality.check', required=True)`` on both (v17
  ``wizard/quality_check_wizard.py:13``, v19 ``:14``) and ``confirm_fail``
  stays public (v17 ``:87-91``, v19 ``:97``).
* ``quality_control.test_type_passfail`` —
  ``enterprise-17.0/quality_control/data/quality_control_data.xml:3-6``;
  ``quality.quality_alert_team0`` — ``enterprise-17.0/quality/data/
  quality_data.xml:9``.
* ``stock.lot.serial`` sequence ships in core on both (v17
  ``stock/data/stock_sequence_data.xml:38``, v19 ``:28``).
* ``stock.backorder.confirmation`` — v17
  ``stock/wizard/stock_backorder_confirmation.py:17-68``: ``pick_ids``
  Many2many (``:21``), ``process`` PUBLIC (``:52``), and the
  ``button_validate_picking_ids`` / ``picking_ids_not_to_backorder`` context
  keys (``:61-67``, consumed by ``stock_picking.py:1155-1158``).

THE RUNTIME CAVEAT THAT GOVERNS EVERY TEST IN THIS SUITE
========================================================
The addons tree on disk is **already a partially-migrated v19 port**
(``dto_purchase_stock/__manifest__.py:9`` declares ``19.0.0.0``) and, as it
stands, **cannot be loaded by Odoo 17** for three independent reasons:

1. ``models/purchase_order.py:34`` — ``@api.depends('picking_ids.move_ids.
   account_move_id')``. ``stock.move.account_move_id`` is v19-only (v19
   ``stock_account/models/stock_move.py:51``); v17 has the plural
   ``account_move_ids`` One2many (v17 ``:19``). On v17 this is a
   registry-build ``ValueError`` — the module does not install.
2. ``views/stock_picking_views.xml:36`` — a root ``<list>`` element, which
   v17's ``ir.ui.view`` has no type for.
3. ``views/quality_check_views.xml:15`` — anchors ``lot_ids``, which exists
   only on v19 Enterprise.

So whatever the v17 target serves over RPC is an **older installed database
revision**, not this source. Every fact about the RUNNING v17 instance is
therefore ``[UNVERIFIED]`` until a live ``fields_get`` / ``get_view``
confirms it, and every WF-015 test MUST open with a capability probe from
this module (``require_*``) and report **BLOCKED with a precise reason**
rather than FAIL when the contribution is absent.

Determinism and safety (hard rules 3 and 5)
===========================================
* Every fixture carries ``MARKER`` + a per-execution token in a value the
  sweep can match: the vendor partner's ``name``, the product's ``name`` and
  ``default_code``, the PO's ``origin``, the picking type's ``name``, the
  quality point's ``name``. Receipts are NOT namespaced by ``origin`` —
  ``_prepare_picking`` stamps the PO's sequence name there — so they are
  swept through their namespaced ``partner_id`` instead.
* Nothing writes to a pre-existing ``stock.picking.type``, ``res.company``
  or ``purchase.order``. Auto-lot needs an operation type flagged
  ``auto_create_lot``: ``make_picking_type`` COPIES the warehouse incoming
  type into a token-named one rather than flipping the flag on the shared
  record.
* ``pin_user_timezone`` is the single exception, and it is a snapshot: the
  acting user's ``tz`` is recorded, set, and restored by
  ``restore_user_timezone`` in a ``finally`` that cannot raise. The
  deadline-regroup engine keys on ``env.user.tz``
  (``stock_picking.py:49``/``stock_move.py:16``), so a test that does not
  pin it is not deterministic.
* The merged-print ``ir.attachment`` is created with the literal name
  ``'Packing Slip'`` and cannot be namespaced. It is therefore never swept
  by name: ``print_attachment_ids`` snapshots the ids before the call and
  ``sweep_new_attachments`` removes only the delta.
* No ``ctx.env.version`` branch belongs in a test body: storability goes
  through ``ctx.adapter.storable_product_values()``, the list tag through
  ``fg_common.list_tag(ctx)``, the groups m2m through
  ``ctx.adapter.user_groups_field``, and the PO-line UoM through
  ``po_line_uom_field`` / ``po_line_tax_field`` here.

Convention rule 4 (no outbound integrations)
============================================
No test calls ``ir.attachment.dpc_print``
(``3rd-addons/printnode_base/models/ir_attachment.py:9-44``, which pushes
bytes to the PrintNode HTTPS API through ``printer.printnode_print_b64``
at ``:31-33``), ``printnode_print_b64``, ``action_test_connection`` or any
cron *by name*. The carrier/tracking writes DO post ``mail.message``
tracking rows, which is in-database bookkeeping and sends nothing.

``dpc_print`` can nevertheless be reached INDIRECTLY, and that is what
``require_printnode_off`` exists to stop. The on-disk (UAT) source of
``stock.picking.action_print_attached_packing_slip`` returns the download
action unconditionally, but the v17 target does not run the on-disk source
— it runs an older installed revision (see the runtime caveat above), and
in that revision the method still branches::

    git -C DTO-Odoo show main:project-addons/dto_purchase_stock/models/\\
        stock_picking.py
    :119-122  if not user.has_group('printnode_base.'
                                    'printnode_security_group_user') \\
                 or not self.env.company.printnode_enabled \\
                 or not user.printnode_enabled:
    :123-127      return {'type': 'ir.actions.act_url', ...}   # download
    :128-129  else:
                  message, job_ids = attachment.dpc_print()    # OUTBOUND

The ``has_group`` leg is always satisfied — ``printnode_base/security/
security.xml:24-26`` adds ``printnode_security_group_user`` to
``base.group_user.implied_ids``, so every internal user is implicitly a
PrintNode user — so the only things standing between a merged print and an
HTTPS call to PrintNode are the two ``printnode_enabled`` flags.
``AUTOMATION_CONVENTIONS.md`` deactivates crons, mail and the Workday SFTP
connector on the QA clone; PrintNode is **not** on that list. Every test
that invokes the merged print therefore goes through
``require_print_packing_slip``, which now calls ``require_printnode_off``
and reports BLOCKED rather than firing the integration.
"""
from __future__ import annotations

import base64
import re
import uuid

from adapters.base import OdooRPCError  # noqa: F401 — re-exported
from framework.fg_common import (http_session, list_tag,  # noqa: F401
                                 m2o_id, make_trace)
from framework.qa_fixtures import (ensure_qa_user,  # noqa: F401
                                   rpc_as_qa_user, sweep_model,
                                   sweep_products, user_groups_field,
                                   with_categ)
from framework.source_scan import (grep_module, module_path,  # noqa: F401
                                   resolve_source_root, scan_modules)

WORKFLOW = "DATAONE-WF-015"
WORKFLOW_NAME = "Per-Line Receipt, Quality Check & Packing Slip"
FEATURE = f"{WORKFLOW} {WORKFLOW_NAME}"

#: Only ``tc_ids`` is consumed downstream (backend/store.py:546,
#: backend/exporters.py:274) — ``feature`` is descriptive, and the workflow id
#: is the stable form.
trace = make_trace(WORKFLOW)

MARKER = "WF015"
_TOKEN = f"{MARKER}-{uuid.uuid4().hex[:8].upper()}"


# ===========================================================================
# Verbatim strings — read from the source, never paraphrased
# ===========================================================================

#: dto_purchase_stock/models/stock_picking.py:40 — ValidationError, wrapped
#: in _(), **no trailing period**. The workbook's E1 text shows a final "."
#: because it ends a sentence; that dot is not part of the string.
ERROR_PACKING_SLIP_MIMETYPE = (
    "File type is not supported. Please upload a PDF or image file")

#: dto_purchase_stock/models/stock_picking.py:144 — the notification
#: params.message, wrapped in _(), **WITH** the trailing period.
MSG_NO_ATTACHMENTS = "There are no attachments to print."

#: dto_purchase_stock/wizard/receipt_product_label_layout.py:35 — UserError.
ERROR_NO_REPORT_TEMPLATE = "Unable to find report template for %s format"

#: dto_purchase_stock/models/stock_picking.py:85 — UserError prefix.
ERROR_IMAGE_TO_PDF_PREFIX = "Cannot convert image to PDF:"

#: dto_account/models/account_move.py:50-56 — the ``_post`` override blocks
#: posting a vendor bill
#: with no attachment. TC220's bill fixture must attach one first or the
#: whole case fails for an unrelated reason.
ERROR_BILL_REQUIRES_ATTACHMENT = (
    "User cannot confirm the bill. The Vendor Bill requires an attachment "
    "before posting.")


def fully_received_error(product_display_name: str) -> str:
    """dto_purchase_stock/models/purchase_order_line.py:104 — verbatim.

    Three properties of that line decide how a test must assert it:

    * it is an **f-string**, NOT wrapped in ``_()`` — so it is never
      translated and is byte-identical in every language;
    * it interpolates ``line.product_id.display_name``, not ``name`` — and
      ``product.product.display_name`` renders as ``[DEFAULT_CODE] Name``
      whenever the product carries an internal reference. To reproduce the
      workbook's literal "Product X" the fixture product must have **no**
      ``default_code``; otherwise assert against the display_name form.
      ``make_product(..., default_code=False)`` exists for exactly that.
    * there is **no trailing period**.
    """
    return (f"Cannot update the Expected Arrival date because Product "
            f"{product_display_name} is fully received")


#: dto_purchase_stock/models/stock_picking.py:34-39, in source order.
PACKING_SLIP_MIMETYPE_WHITELIST = (
    "application/pdf",
    "image/png", "image/jpeg", "image/gif", "image/bmp",
    "image/tiff", "image/x-xbitmap", "image/svg+xml",
    "image/heif", "image/heic",
)

#: The 19 controlled Reason-for-Return codes, verbatim from
#: dto_purchase_stock/models/quality_check.py:6-27. The identical list is
#: duplicated at dto_purchase_stock/wizard/quality_check_wizard.py:6-28 and
#: at 3rd-addons/stock_picking_auto_create_lot/models/stock_picking.py:11-33
#: — verified key-for-key and label-for-label identical across all three.
#: NOTE '902' uses a Unicode EN DASH (U+2013); '903' and '904' use an ASCII
#: hyphen. TC214 step 14's drift check compares the live selections, so the
#: dash must survive in this file unchanged.
REASON_FOR_RETURN = (
    ("901", "Vendor data entry error"),
    ("902", "Customer ordering error \u2013 provide details in notes"),
    ("903", "Damaged Product - provide detail in notes"),
    ("904", "Defective Product - provide detail in notes"),
    ("905", "End User cancelled order"),
    ("906", "Account Manager Quoted Wrong Item/Qty"),
    ("907", "Product no longer required"),
    ("908", "Purchasing Error"),
    ("909", "AM Quoted Wrong Item/Qty"),
    ("910", "Damaged/DOA"),
    ("911", "DATAONE Quoting Error"),
    ("912", "Wrong Product Shipped"),
    ("913", "Other (requires notes if selected)"),
    ("914", "Received wrong parts"),
    ("915", "Wrong pinout"),
    ("916", "Shipping error"),
    ("917", "Customer cancel order"),
    ("918", "Fail test"),
    ("919", "Wrong quantity received"),
)
REASON_CODES = tuple(key for key, _label in REASON_FOR_RETURN)

#: The three models that each carry their own copy of the taxonomy.
REASON_TAXONOMY_MODELS = ("quality.check", "quality.check.wizard",
                          "stock.picking")

#: purchase_order_line.py:43 — the candidate-picking destination usages.
CANDIDATE_DEST_USAGES = ("internal", "transit", "customer")

#: stock_move_line.py:12 (OCA) — core ships it on both versions.
LOT_SEQUENCE_CODE = "stock.lot.serial"

#: A fixed, DST-bearing timezone. The regroup engine compares
#: ``date_deadline.astimezone(env.user.tz).date()``, so the acting user's tz
#: must be pinned or TC202/TC203/TC205 are not deterministic.
PINNED_TZ = "America/Chicago"

#: stock_picking.py:111 — the literal name of the merged-print attachment.
PRINT_ATTACHMENT_NAME = "Packing Slip"


# ===========================================================================
# XML ids — every one opened in the source
# ===========================================================================
XMLID_PICKING_FORM_INHERIT = (
    "dto_purchase_stock.view_picking_form_inherit_dto_purchase_stock")
XMLID_PACKING_SLIP_TREE = "dto_purchase_stock.packing_slip_attachment_tree"
XMLID_SERVER_ACTION_PRINT = (
    "dto_purchase_stock.action_print_attached_packing_slip")
XMLID_PO_FORM_INHERIT = "dto_purchase_stock.purchase_order_form"
XMLID_QUALITY_CHECK_FORM_INHERIT = (
    "dto_purchase_stock.quality_check_view_form_inherit_dto_purchase_stock")
XMLID_QUALITY_WIZARD_INHERIT = (
    "dto_purchase_stock.quality_check_wizard_inherit_dto_purchase_stock")
XMLID_LABEL_LAYOUT_ACTION = (
    "dto_purchase_stock.action_stock_picking_product_label_layout")
XMLID_LABEL_LAYOUT_FORM = (
    "dto_purchase_stock.stock_picking_product_label_layout_view_form")
XMLID_REPORT_DYMO = "dto_purchase_stock.report_receipt_product_label_dymo"
XMLID_REPORT_ZPL = "dto_purchase_stock.report_receipt_product_label_zpl"
REPORT_NAME_DYMO = (
    "dto_purchase_stock.report_receipt_product_label_dymo_template")
REPORT_NAME_ZPL = (
    "dto_purchase_stock.report_receipt_product_label_zpl_template")
REPORT_NAME_DETAIL = (
    "dto_purchase_stock.report_receipt_product_label_detail")
XMLID_PAPERFORMAT_DYMO = "dto_base.paperformat_dto_label_sheet_dymo"
#: reports/report_views.xml:11 and :20 — the same expression on both records.
PRINT_REPORT_NAME_EXPR = "'Products Labels - %s' % (object.name)"

#: Core / Enterprise anchors used by this suite, present on both versions.
XMLID_ACTION_PICKING_TREE_ALL = "stock.action_picking_tree_all"
XMLID_ACTION_MOVES_ALL = "account.action_account_moves_all"
XMLID_GROUP_STOCK_USER = "stock.group_stock_user"
XMLID_CORE_PICKING_FORM = "stock.view_picking_form"
XMLID_QC_CHECK_FORM = "quality_control.quality_check_view_form"
XMLID_QC_WIZARD_FORM = "quality_control.view_quality_check_wizard"
XMLID_QC_TEST_TYPE_PASSFAIL = "quality_control.test_type_passfail"
XMLID_QC_TEAM = "quality.quality_alert_team0"
XMLID_PRINTNODE_GROUP_USER = "printnode_base.printnode_security_group_user"

#: TC015 — the two commercial modules and what the delivered v17 builds say.
COMMERCIAL_MODULES = ("printnode_base", "location_barcode_labels")
#: printnode_base/__manifest__.py:10 ; location_barcode_labels:6
COMMERCIAL_V17_VERSIONS = {"printnode_base": "17.0.2.6.10",
                           "location_barcode_labels": "2.0"}
#: printnode_base ships three ir.cron (data/ir_cron_data.xml:5,16,27) and two
#: res.groups (security/security.xml:10,15); security.xml:24-26 also adds the
#: user group to base.group_user.implied_ids, so on a v17 database with the
#: module installed EVERY internal user is implicitly a PrintNode user.
PRINTNODE_CRON_XMLIDS = (
    "printnode_base.printnode_limits_update_action",
    "printnode_base.printnode_releases_update_action",
    "printnode_base.printnode_clean_printjob_action",
)
PRINTNODE_GROUP_XMLIDS = (
    "printnode_base.printnode_security_group_user",
    "printnode_base.printnode_security_group_manager",
)

#: TC032 step 8 — the static grep for a surviving purchase.order 'done'
#: expression. Verified today: dto_reports/views/purchase_order.xml carries
#: THREE hits (:53, :62 and the act_window domain at :78), not the two the
#: workbook states, and dto_reports is still 17.0.0.1 (__manifest__.py:10).
#: dto_purchase has no surviving PO-'done' expression outside tests and a
#: comment; its purchase_order_line.py:60 `x.state == 'done'` is a
#: **stock.move** state, correct on both versions, and must not be counted.
PO_DONE_SCAN_MODULES = ("dto_reports", "dto_purchase")
PO_DONE_SCAN_PATTERN = r"'done'"


# ===========================================================================
# Namespacing
# ===========================================================================
def fixture_token() -> str:
    """The per-execution token every fixture in this run carries."""
    return _TOKEN


def tag(name: str) -> str:
    """Namespace a fixture label: 'WF015-1A2B3C4D <name>'."""
    return f"{_TOKEN} {name}"


#: wf013/wf020 spell the same helper ``fx``; kept as an alias so a test
#: ported between suites does not have to be rewritten.
fx = tag


def sku(label: str) -> str:
    """A namespaced internal reference: 'WF015-1A2B3C4D-<label>'."""
    return f"{_TOKEN}-{label}"


# ===========================================================================
# Preconditions — precise BLOCKED reasons, never a bare failure
# ===========================================================================
_PORT_NOTE = (
    "The on-disk dto_purchase_stock is already a v19 port "
    "(__manifest__.py:9 declares 19.0.0.0) and cannot build the registry on "
    "Odoo 17: models/purchase_order.py:34 depends on stock.move."
    "account_move_id, a v19-only field (v19 stock_account/models/"
    "stock_move.py:51; v17 has account_move_ids at :19). Whatever the v17 "
    "target serves is an older installed revision, so the contribution has "
    "to be probed rather than assumed.")


def require_dto_purchase_stock(ctx):
    """BLOCK unless dto_purchase_stock is contributing to this target."""
    rpc = ctx.adapter.rpc
    missing = []
    if not rpc.field_exists("stock.picking", "packing_slip_attachment"):
        missing.append("stock.picking.packing_slip_attachment")
    if not rpc.field_exists("purchase.order", "packing_slip_receipt_count"):
        missing.append("purchase.order.packing_slip_receipt_count")
    if missing:
        ctx.blocked(
            f"dto_purchase_stock is not contributing to {ctx.env.key} "
            f"(db={ctx.env.db}) — missing: {', '.join(missing)}. "
            f"{_PORT_NOTE}")


def require_packing_slip(ctx):
    """BLOCK unless BOTH packing-slip fields and the print method exist."""
    require_dto_purchase_stock(ctx)
    rpc = ctx.adapter.rpc
    if not rpc.field_exists("stock.picking", "packing_slip_attachment_name"):
        ctx.blocked(
            "stock.picking.packing_slip_attachment_name is absent on "
            f"{ctx.env.key}. The mimetype constraint is declared "
            "@api.constrains on that field (dto_purchase_stock/models/"
            "stock_picking.py:27), so without it nothing validates.")


def require_printnode_off(ctx):
    """BLOCK when the installed revision would take the ``dpc_print`` branch.

    Convention rule 4 forbids firing an outbound integration. The v17 target
    does not run the on-disk (UAT) source — it runs an older installed
    revision, and in that revision
    ``action_print_attached_packing_slip`` branches on three conditions
    (``main:project-addons/dto_purchase_stock/models/stock_picking.py:
    119-139``). The ``has_group`` leg is always satisfied
    (``printnode_base/security/security.xml:24-26`` adds
    ``printnode_security_group_user`` to ``base.group_user.implied_ids``), so
    the ONLY thing keeping the merged print on the download branch is the
    pair of ``printnode_enabled`` flags. With both set, the method calls
    ``attachment.dpc_print()``
    (``printnode_base/models/ir_attachment.py:9-44``), which pushes the
    merged PDF to the PrintNode HTTPS API through
    ``printer.printnode_print_b64`` (``:31-33``).

    The flags are READ, never written: enabling or disabling PrintNode on a
    real company or user is a master-data change (rule 3). When either field
    is absent (v19 dropped ``printnode_base`` under decision D-1) there is no
    branch to take and the probe passes.
    """
    rpc = ctx.adapter.rpc
    company_on = user_on = False
    if rpc.field_exists("res.company", "printnode_enabled"):
        company_on = bool(rpc.read("res.company", [own_company_id(rpc)],
                                   ["printnode_enabled"])[0]
                          ["printnode_enabled"])
    if rpc.field_exists("res.users", "printnode_enabled"):
        user_on = bool(rpc.read("res.users", [rpc.uid],
                                ["printnode_enabled"])[0]
                       ["printnode_enabled"])
    ctx.log(f"PrintNode enabling flags on {ctx.env.key}: "
            f"company={company_on}, user[{rpc.uid}]={user_on} — read only, "
            f"never written (rule 3)")
    if company_on and user_on:
        ctx.blocked(
            "res.company.printnode_enabled and res.users.printnode_enabled "
            f"are BOTH True on {ctx.env.key} (db={ctx.env.db}). The installed "
            "v17 revision of stock.picking."
            "action_print_attached_packing_slip (main:project-addons/"
            "dto_purchase_stock/models/stock_picking.py:119-139) then takes "
            "the else branch at :128-129 and calls attachment.dpc_print(), "
            "which pushes the merged PDF to the PrintNode HTTPS API via "
            "printer.printnode_print_b64 (3rd-addons/printnode_base/models/"
            "ir_attachment.py:31-33). The has_group leg cannot save it: "
            "printnode_base/security/security.xml:24-26 implies "
            "printnode_security_group_user into base.group_user. "
            "AUTOMATION_CONVENTIONS rule 4 forbids firing an outbound "
            "integration, and PrintNode is not among the connectors the QA "
            "clone deactivates. Disable PrintNode on the QA clone "
            "(res.company.printnode_enabled = False) and re-run.")


def require_print_packing_slip(ctx):
    """BLOCK unless the merged-print entry point is reachable AND inert.

    ``action_print_attached_packing_slip`` lives in a module whose top-level
    ``import img2pdf`` (stock_picking.py:6) is unconditional: if the package
    is absent from the Odoo server's venv the module never loads and the
    method is simply not there. That is a precise, actionable BLOCKED
    reason, not a failure of the feature under test.

    ``require_printnode_off`` runs last, so every case that drives the merged
    print (TC209, TC210, TC211) inherits the rule-4 guard.
    """
    require_packing_slip(ctx)
    rpc = ctx.adapter.rpc
    if not _has_method(rpc, "stock.picking",
                       "action_print_attached_packing_slip"):
        ctx.blocked(
            "stock.picking.action_print_attached_packing_slip is not "
            f"dispatchable on {ctx.env.key}. dto_purchase_stock/models/"
            "stock_picking.py:6 imports img2pdf unconditionally at module "
            "level, so a server venv without img2pdf (or without Pillow, "
            ":7) loses the whole model extension. Install img2pdf and "
            "Pillow on the Odoo server, then re-run.")
    require_printnode_off(ctx)


def require_label_wizard(ctx):
    """BLOCK unless the receipt-label wizard and both reports exist."""
    require_dto_purchase_stock(ctx)
    rpc = ctx.adapter.rpc
    missing = []
    if not rpc.model_exists("stock.picking.product.label.layout"):
        missing.append("model stock.picking.product.label.layout")
    for xmlid in (XMLID_REPORT_DYMO, XMLID_REPORT_ZPL,
                  XMLID_LABEL_LAYOUT_ACTION):
        if not rpc.ref(xmlid):
            missing.append(xmlid)
    if missing:
        ctx.blocked(
            f"The receipt label stack is incomplete on {ctx.env.key} — "
            f"missing: {', '.join(missing)}. dto_purchase_stock/wizard/ and "
            "reports/report_views.xml supply all of them.")


def require_quality_control(ctx):
    """BLOCK unless Odoo Enterprise quality_control is in the registry."""
    rpc = ctx.adapter.rpc
    missing = [m for m in ("quality.point", "quality.check",
                           "quality.check.wizard")
               if not rpc.model_exists(m)]
    if missing:
        ctx.blocked(
            f"Odoo Enterprise quality_control is not installed on "
            f"{ctx.env.key} (db={ctx.env.db}) — missing model(s): "
            f"{', '.join(missing)}. dto_purchase_stock declares it as a "
            "dependency (__manifest__.py), so this whole workflow is "
            "Enterprise-only and none of F072 exists without it.")


def require_reason_for_return(ctx):
    """BLOCK unless dto_purchase_stock added the 19-code vocabulary."""
    require_quality_control(ctx)
    rpc = ctx.adapter.rpc
    missing = [m for m in ("quality.check", "quality.check.wizard")
               if not rpc.field_exists(m, "reason_for_return")]
    if missing:
        ctx.blocked(
            "reason_for_return is absent from "
            f"{', '.join(missing)} on {ctx.env.key}. dto_purchase_stock "
            "declares it (models/quality_check.py:6, wizard/"
            "quality_check_wizard.py:6), but its quality-check view inherit "
            "anchors <field name=\"lot_ids\"> (views/quality_check_views."
            "xml:15), which exists only on v19 Enterprise "
            "(enterprise-19.0/quality_control/views/quality_views.xml:236; "
            "v17 carries lot_id at enterprise-17.0/.../quality_views.xml:"
            "246) — on v17 that inherit aborts the install.")


def require_auto_create_lot(ctx):
    """BLOCK unless the OCA auto-lot module contributed both flags."""
    rpc = ctx.adapter.rpc
    missing = [f"{model}.auto_create_lot"
               for model in ("product.template", "stock.picking.type")
               if not rpc.field_exists(model, "auto_create_lot")]
    if missing:
        ctx.blocked(
            "stock_picking_auto_create_lot is not installed on "
            f"{ctx.env.key} (db={ctx.env.db}) — missing: "
            f"{', '.join(missing)}. F086 has nothing to test without it.")
    if not rpc.search("ir.sequence", [("code", "=", LOT_SEQUENCE_CODE)],
                      limit=1):
        ctx.blocked(
            f"No ir.sequence with code {LOT_SEQUENCE_CODE!r} exists on "
            f"{ctx.env.key}. stock_picking_auto_create_lot/models/"
            "stock_move_line.py:12 draws every auto lot name from it; core "
            "ships it (v17 stock/data/stock_sequence_data.xml:38, v19 :28), "
            "so its absence is a broken database, not a test failure.")


def require_journal_entries(ctx):
    """BLOCK unless purchase.order.account_move_ids survived the port."""
    require_dto_purchase_stock(ctx)
    rpc = ctx.adapter.rpc
    if not rpc.field_exists("purchase.order", "account_move_ids"):
        ctx.blocked(
            f"purchase.order.account_move_ids is absent on {ctx.env.key}. "
            "dto_purchase_stock/models/purchase_order.py:34 depends on "
            "stock.move.account_move_id, which exists only on v19 "
            "(odoo-19.0/addons/stock_account/models/stock_move.py:51); v17 "
            "has the plural account_move_ids One2many (odoo-17.0/addons/"
            "stock_account/models/stock_move.py:19), so the current source "
            "cannot build the registry on v17 and F076 is unreachable.")


def require_carrier_fields(ctx):
    """BLOCK unless stock_delivery + the DTO redefinitions are present."""
    require_dto_purchase_stock(ctx)
    rpc = ctx.adapter.rpc
    missing = [f for f in ("carrier_id", "carrier_tracking_ref")
               if not rpc.field_exists("stock.picking", f)]
    if missing:
        ctx.blocked(
            f"stock.picking is missing {', '.join(missing)} on "
            f"{ctx.env.key} — stock_delivery is not installed, so the two "
            "fields dto_purchase_stock/models/stock_picking.py:17-24 "
            "redefines with tracking=True do not exist to be redefined.")
    if not rpc.model_exists("delivery.carrier"):
        ctx.blocked(
            "delivery.carrier is not in the registry on "
            f"{ctx.env.key} — stock_delivery / delivery is not installed.")


def require_second_company(ctx):
    """Return a second res.company id, or SKIP the step that needs one.

    TC219 step 11 asserts ``check_company=True`` on ``carrier_id``, which
    needs a carrier owned by another company. A single-company target cannot
    express that, and inventing a company would be a master-data change.
    """
    rpc = ctx.adapter.rpc
    own = own_company_id(rpc)
    others = rpc.search_read("res.company", [("id", "!=", own)], ["name"],
                             order="id", limit=1)
    if not others:
        ctx.skip(
            f"{ctx.env.key} (db={ctx.env.db}) has exactly one res.company, "
            "so the check_company=True guard on stock.picking.carrier_id "
            "(dto_purchase_stock/models/stock_picking.py:23) cannot be "
            "exercised. Creating a second company would be a master-data "
            "change, which convention rule 3 forbids.")
    return others[0]["id"]


def require_source_root(ctx):
    """Return the DTO-Odoo checkout, or BLOCK with the reason it is absent."""
    root = resolve_source_root(ctx.env.version)
    if root is None:
        ctx.blocked(
            "The DTO-Odoo source tree is not reachable from this "
            "workstation. Set DTO_SOURCE_ROOT_"
            f"{ctx.env.version} (or DTO_SOURCE_ROOT) in config/local.yaml. "
            "The static half of this case greps the custom addons and "
            "cannot fall back to a weaker assertion.")
    return root


def _has_method(rpc, model: str, method: str) -> bool:
    """True when ``model.method`` is dispatchable over RPC.

    There is no ``methods_get``, so the probe is the call itself: an
    ``AccessError`` (private name) or "does not exist" means absent, while
    any other server-side fault means the method ran and objected to the
    arguments — i.e. it exists. Called with an empty id list so nothing is
    touched either way.
    """
    try:
        rpc.call(model, method, [])
        return True
    except OdooRPCError as exc:
        text = str(exc).lower()
        return not ("does not exist" in text or "is not a valid" in text
                    or "invalid method" in text or "no attribute" in text)


# ===========================================================================
# Timezone pinning — snapshot/restore, never a silent change
# ===========================================================================
def pin_user_timezone(ctx, tz: str = PINNED_TZ):
    """Pin the acting user's ``tz`` and return ``(uid, previous_tz)``.

    The regroup engine compares deadlines as **dates in the acting user's
    timezone** (``dto_purchase_stock/models/stock_picking.py:49`` and
    ``models/stock_move.py:16``), so an unpinned ``tz`` makes TC202, TC203
    and TC205 depend on whoever last logged in.

    ``res.users`` is a pre-existing record, so this is a snapshot, not a
    change: the caller MUST call :func:`restore_user_timezone` in a
    ``finally`` that cannot raise, and should then assert the restoration —
    the WF-013 TC228 precedent.
    """
    rpc = ctx.adapter.rpc
    uid = rpc.uid
    previous = rpc.read("res.users", [uid], ["tz"])[0].get("tz") or False
    if previous != tz:
        rpc.write("res.users", [uid], {"tz": tz})
        ctx.log(f"pinned res.users[{uid}].tz {previous!r} -> {tz!r} "
                "(restored in finally)")
    return uid, previous


def restore_user_timezone(rpc, uid: int, previous) -> bool:
    """Put the acting user's ``tz`` back. Never raises."""
    try:
        rpc.write("res.users", [uid], {"tz": previous or False})
        return True
    except OdooRPCError:
        return False


def user_timezone(rpc, uid: int | None = None):
    return rpc.read("res.users", [uid or rpc.uid], ["tz"])[0].get("tz") or False


# ===========================================================================
# Sweeping — children before parents, best effort, never raises
# ===========================================================================
def marker_partner_ids(rpc) -> list:
    return rpc.search("res.partner", [("name", "like", f"{MARKER}%"),
                                      ("active", "in", [True, False])])


def marker_product_ids(rpc) -> list:
    return rpc.search("product.product",
                      [("default_code", "like", f"{MARKER}%"),
                       ("active", "in", [True, False])])


def marker_picking_type_ids(rpc) -> list:
    return rpc.search("stock.picking.type", [("name", "like", f"{MARKER}%"),
                                             ("active", "in", [True, False])])


def _try(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except OdooRPCError:
        return None


def sweep_wf015(rpc):
    """Remove this suite's leftovers, children before parents.

    Order is forced by the references: quality checks point at pickings,
    pickings at picking types and partners, purchase orders at partners,
    lots and quants at products. Confirmed purchase orders and non-draft
    pickings must be cancelled before they can be unlinked, and a done
    picking cannot be removed at all — which is why this is best effort by
    design and the per-execution token, not the sweep, is what guarantees
    isolation.
    """
    partner_ids = marker_partner_ids(rpc)
    product_ids = marker_product_ids(rpc)
    type_ids = marker_picking_type_ids(rpc)

    picking_ids = []
    if partner_ids:
        picking_ids += rpc.search("stock.picking",
                                  [("partner_id", "in", partner_ids)])
    if type_ids:
        picking_ids += rpc.search("stock.picking",
                                  [("picking_type_id", "in", type_ids)])
    picking_ids = sorted(set(picking_ids))

    # 1. quality points and their checks
    if rpc.model_exists("quality.check"):
        domain = [("name", "like", f"{MARKER}%")] if not picking_ids else \
            ["|", ("picking_id", "in", picking_ids),
             ("name", "like", f"{MARKER}%")]
        sweep_model(rpc, "quality.check", domain)
    if rpc.model_exists("quality.point"):
        sweep_model(rpc, "quality.point", [("name", "like", f"{MARKER}%"),
                                           ("active", "in", [True, False])])

    # 2. pickings: cancel, then unlink
    if picking_ids:
        _try(rpc.call, "stock.picking", "action_cancel", picking_ids)
        _try(rpc.call, "stock.picking", "unlink", picking_ids)

    # 3. purchase orders: cancel, then unlink
    if partner_ids:
        order_ids = rpc.search("purchase.order",
                               [("partner_id", "in", partner_ids)])
        if order_ids:
            _try(rpc.call, "purchase.order", "button_cancel", order_ids)
            _try(rpc.call, "purchase.order", "unlink", order_ids)

    # 4. lots and quants belonging to this suite's products
    if product_ids:
        sweep_model(rpc, "stock.lot", [("product_id", "in", product_ids)])
        sweep_model(rpc, "stock.quant", [("product_id", "in", product_ids)])

    # 5. products (unlink, else archive — sweep_products handles both)
    sweep_products(rpc, MARKER)
    sweep_model(rpc, "product.product",
                [("default_code", "like", f"{MARKER}%"),
                 ("active", "in", [True, False])])
    sweep_model(rpc, "product.template",
                [("default_code", "like", f"{MARKER}%"),
                 ("active", "in", [True, False])])

    # 6. operation types created by make_picking_type
    if type_ids:
        sweep_model(rpc, "stock.picking.type", [("id", "in", type_ids)])

    # 7. carriers, then partners
    if rpc.model_exists("delivery.carrier"):
        sweep_model(rpc, "delivery.carrier",
                    [("name", "like", f"{MARKER}%"),
                     ("active", "in", [True, False])])
    sweep_model(rpc, "res.partner", [("name", "like", f"{MARKER}%"),
                                     ("user_ids", "=", False),
                                     ("active", "in", [True, False])])


def open_namespace(ctx):
    """Sweep previous WF015 fixtures and log this execution's token."""
    with ctx.step(f"Sweep previous {MARKER} fixtures and open a fresh "
                  "namespace"):
        sweep_wf015(ctx.adapter.rpc)
        ctx.log(f"fixture token = {_TOKEN}")


# --- the one thing that cannot be namespaced -------------------------------
def print_attachment_ids(rpc) -> set:
    """Ids of every ``ir.attachment`` named 'Packing Slip'.

    ``action_print_attached_packing_slip`` hard-codes that name and sets no
    ``res_id`` (stock_picking.py:110-117), so the record carries nothing to
    namespace. Sweeping by name would delete other people's rows, which rule
    3 forbids — snapshot before the call and remove only the delta.
    """
    return set(rpc.search("ir.attachment",
                          [("name", "=", PRINT_ATTACHMENT_NAME)]))


def sweep_new_attachments(rpc, before: set) -> list:
    """Unlink only the 'Packing Slip' attachments this run created."""
    created = sorted(print_attachment_ids(rpc) - set(before))
    if created:
        _try(rpc.call, "ir.attachment", "unlink", created)
    return created


# ===========================================================================
# Version-safe field names
# ===========================================================================
def po_line_uom_field(rpc) -> str:
    """``product_uom`` on v17, ``product_uom_id`` on v19.

    v17 ``purchase/models/purchase_order_line.py:34`` vs v19 ``:36``. The
    rename also silently disables one half of the fully-received bypass:
    ``dto_purchase_stock/models/purchase_order_line.py:107`` still tests the
    literal ``'product_uom'``.
    """
    return ("product_uom_id"
            if rpc.field_exists("purchase.order.line", "product_uom_id")
            else "product_uom")


def po_line_tax_field(rpc) -> str:
    """``taxes_id`` on v17 (``purchase_order_line.py:33``), ``tax_ids`` on
    v19 (``:34``). Zeroing it keeps fixture totals deterministic."""
    return ("tax_ids" if rpc.field_exists("purchase.order.line", "tax_ids")
            else "taxes_id")


def own_company_id(rpc) -> int:
    return m2o_id(rpc.read("res.users", [rpc.uid], ["company_id"])[0]
                  ["company_id"])


def copied_id(result):
    """Normalise what ``copy()`` marshals back, across versions.

    This is the ``user_has_group`` defect class (WF-011 F-1) in a second
    guise: a method that *looks* uniformly public returns a different JSON
    shape on each target, so the naive call works on v17 and hands v19 a
    list where an id was expected.

    * **v17** — ``BaseModel.copy`` is decorated
      ``@api.returns('self', lambda value: value.id)``
      (``O17 odoo/models.py:5586-5587``). ``_call_kw_multi`` runs
      ``downgrade()`` (``O17 odoo/api.py:464-470`` → ``:334-345``), which
      applies that converter, so ``/web/dataset/call_kw`` returns an
      **int**.
    * **v19** — the decorator is gone (``O19 odoo/orm/models.py:5530``:
      ``def copy(self, default=None) -> Self``). ``call_kw`` falls through to
      ``elif isinstance(result, BaseModel): result = result.ids``
      (``O19 odoo/service/model.py:102-104``), so it returns a **list**.

    Accepting both shapes here keeps ``ctx.env.version`` out of every caller,
    the way ``po_line_uom_field`` and ``adapter.user_groups_field`` do.
    """
    if isinstance(result, (list, tuple)):
        return result[0] if result else None
    if isinstance(result, dict):
        return result.get("id")
    return result


# ===========================================================================
# Fixtures — partners, products, operation types
# ===========================================================================
def vendor_location_id(rpc) -> int | None:
    """A ``usage='supplier'`` location for ``property_stock_supplier``."""
    ref = rpc.ref("stock.stock_location_suppliers")
    if ref and rpc.search("stock.location", [("id", "=", ref)]):
        return ref
    found = rpc.search_read("stock.location", [("usage", "=", "supplier")],
                            ["id"], order="id", limit=1)
    return found[0]["id"] if found else None


def ensure_vendor(rpc, label: str = "Vendor") -> int:
    """A namespaced vendor partner with a Vendor Location set.

    ``_prepare_picking`` raises ``UserError("You must set a Vendor Location
    for this partner %s")`` when ``partner.property_stock_supplier`` is
    empty (v17 ``purchase_stock/models/purchase_order.py:224``), so the
    property is written explicitly instead of relying on a company default
    that may not exist on this database.
    """
    name = tag(f"{MARKER} {label}")
    found = rpc.search("res.partner", [("name", "=", name)], limit=1)
    if found:
        return found[0]
    values = {"name": name, "ref": sku(label), "supplier_rank": 1}
    location_id = vendor_location_id(rpc)
    if location_id and rpc.field_exists("res.partner",
                                        "property_stock_supplier"):
        values["property_stock_supplier"] = location_id
    return rpc.create("res.partner", values)


def make_product(ctx, label: str, tracking: str = "none",
                 auto_create_lot: bool = False, storable: bool = True,
                 price: float = 10.0, default_code=None,
                 service: bool = False) -> int:
    """A namespaced product variant.

    Storability goes through ``ctx.adapter.storable_product_values()``
    (v17 ``type='product'``; v19 ``type='consu'`` + ``is_storable=True``),
    so no test body carries a version branch.

    ``default_code`` defaults to the namespaced SKU because the labels in
    TC212/TC213 encode ``move_line.product_id.default_code`` and a product
    without one prints no SKU barcode at all
    (``report_receipt_product_label.xml:8``). Pass ``default_code=False``
    for TC206, where the ``UserError`` interpolates ``display_name`` and
    only a code-less product reproduces the workbook's literal "Product X"
    (``purchase_order_line.py:104``).
    """
    rpc = ctx.adapter.rpc
    values = {
        "name": tag(label),
        "list_price": price,
        "standard_price": price,
        "purchase_ok": True,
        "sale_ok": True,
        "tracking": tracking,
    }
    if default_code is not False:
        values["default_code"] = default_code or sku(label)
    if service:
        values["type"] = "service"
        values.pop("tracking", None)
    else:
        values.update(ctx.adapter.storable_product_values())
        if not storable and rpc.field_exists("product.template",
                                             "is_storable"):
            values["is_storable"] = False
    if auto_create_lot:
        if not rpc.field_exists("product.template", "auto_create_lot"):
            raise OdooRPCError(
                "product.template.auto_create_lot is absent — call "
                "require_auto_create_lot(ctx) before asking for an auto-lot "
                "product so the test reports BLOCKED, not ERROR.")
        values["auto_create_lot"] = True
    tmpl_id = rpc.create("product.template", with_categ(rpc, values))
    variant = rpc.search_read("product.product",
                              [("product_tmpl_id", "=", tmpl_id)],
                              ["id"], limit=1)
    return variant[0]["id"]


def product_row(rpc, product_id: int, fields_=None) -> dict:
    fields_ = fields_ or ["name", "default_code", "display_name", "tracking",
                          "uom_id", "type"]
    fields_ = [f for f in fields_ if rpc.field_exists("product.product", f)]
    return rpc.read("product.product", [product_id], fields_)[0]


def product_display_name(rpc, product_id: int) -> str:
    """``display_name`` as Odoo renders it — '[CODE] Name' when a code is
    set. TC206's expected message interpolates exactly this value."""
    return product_row(rpc, product_id, ["display_name"])["display_name"]


def default_picking_type(rpc, code: str = "incoming",
                         company_id: int | None = None) -> int:
    domain = [("code", "=", code)]
    if company_id:
        domain.append(("company_id", "in", [company_id, False]))
    rows = rpc.search_read("stock.picking.type", domain, ["id"], order="id",
                           limit=1)
    if not rows:
        raise OdooRPCError(f"no stock.picking.type with code={code!r}")
    return rows[0]["id"]


def make_picking_type(rpc, label: str = "IN", code: str = "incoming",
                      auto_create_lot: bool = False,
                      source_id: int | None = None) -> int:
    """A token-named operation type, copied from the warehouse's own.

    TC215/TC216 need an incoming operation type flagged
    ``auto_create_lot`` (``stock_picking_auto_create_lot/models/
    stock_picking.py:50`` gates the whole feature on it). Flipping that flag
    on the warehouse's shared type would modify a pre-existing business
    record, which rule 3 forbids — so the type is copied instead.

    ``stock.picking.type.copy`` is public, but **what it marshals back
    differs by version** — see ``copied_id``, through which both returns
    here are normalised. v17's override
    (``stock/models/stock_picking.py:169-176``) supplies its own ``name``
    and ``sequence_code`` defaults, which are overridden here so the copy is
    namespaced and its sequence prefix unique.
    """
    source_id = source_id or default_picking_type(rpc, code)
    default = {"name": tag(f"{MARKER} {label}"),
               "sequence_code": sku(label)[:16]}
    if auto_create_lot:
        default["auto_create_lot"] = True
    try:
        return copied_id(rpc.call("stock.picking.type", "copy", [source_id],
                                  default=default))
    except OdooRPCError:
        # Some databases refuse a sequence_code collision on the warehouse;
        # fall back to a plain copy and write the flags afterwards.
        new_id = copied_id(rpc.call("stock.picking.type", "copy",
                                    [source_id]))
        writable = {"name": default["name"]}
        if auto_create_lot:
            writable["auto_create_lot"] = True
        rpc.write("stock.picking.type", [new_id], writable)
        return new_id


def ensure_carrier(rpc, label: str = "Carrier",
                   company_id: int | None = None) -> int:
    """A namespaced ``delivery.carrier`` (fixed price, no external call)."""
    name = tag(f"{MARKER} {label}")
    found = rpc.search("delivery.carrier", [("name", "=", name),
                                            ("active", "in", [True, False])],
                       limit=1)
    if found:
        return found[0]
    values = {"name": name, "delivery_type": "fixed", "fixed_price": 0.0}
    product_ids = rpc.search("product.product",
                             [("type", "=", "service")], limit=1)
    if product_ids and rpc.field_exists("delivery.carrier", "product_id"):
        values["product_id"] = product_ids[0]
    if company_id:
        values["company_id"] = company_id
    return rpc.create("delivery.carrier", values)


# ===========================================================================
# Fixtures — purchase orders and receipts
# ===========================================================================
def po_line_values(ctx, product_id: int, qty: float, date_planned: str,
                   price_unit: float = 10.0, name: str | None = None) -> dict:
    """One ``purchase.order.line`` create tuple payload.

    ``name``, ``product_qty`` and ``price_unit`` are ``required=True`` on
    both versions (v17 ``purchase_order_line.py:18,21,38``; v19
    ``:19,23,39``) and v19 drops ``product_qty``'s compute (``:23``), so all
    three are supplied explicitly. The UoM key and the tax key are resolved
    per version rather than hard-coded.
    """
    rpc = ctx.adapter.rpc
    row = product_row(rpc, product_id, ["display_name", "uom_id"])
    values = {
        "product_id": product_id,
        "name": name or row["display_name"],
        "product_qty": qty,
        "price_unit": price_unit,
        "date_planned": date_planned,
        po_line_uom_field(rpc): m2o_id(row["uom_id"]),
        po_line_tax_field(rpc): [(6, 0, [])],
    }
    return values


def make_purchase_order(ctx, lines: list[dict], partner_id: int | None = None,
                        origin: str | None = None,
                        picking_type_id: int | None = None,
                        label: str = "PO") -> int:
    """A draft purchase order under this execution's namespace.

    ``origin`` is namespaced so the ZPL label's ``purchase_source`` branch
    (``report_receipt_product_label.xml:97-107``) can be steered: pass a
    value longer than 14 characters for the ``^FT40,230`` branch, 14 or
    fewer for ``^FT40,290``, and ``origin=False`` for the third,
    undocumented ``^FT40,380`` branch.
    """
    rpc = ctx.adapter.rpc
    values = {
        "partner_id": partner_id or ensure_vendor(rpc),
        "order_line": [(0, 0, line) for line in lines],
    }
    if origin is not False:
        values["origin"] = origin or tag(f"{MARKER} {label}")
    if picking_type_id:
        values["picking_type_id"] = picking_type_id
    return rpc.create("purchase.order", values)


def confirm_purchase_order(rpc, order_id: int):
    """``button_confirm`` — public on both versions."""
    return rpc.call("purchase.order", "button_confirm", [order_id])


def order_row(rpc, order_id: int, fields_=None) -> dict:
    fields_ = fields_ or ["name", "state", "origin", "partner_id",
                          "picking_ids", "picking_type_id"]
    fields_ = [f for f in fields_ if rpc.field_exists("purchase.order", f)]
    return rpc.read("purchase.order", [order_id], fields_)[0]


def order_picking_ids(rpc, order_id: int) -> list:
    """``order.picking_ids`` — the ONLY safe receipt count.

    ``picking_ids`` is ``@api.depends('order_line.move_ids.picking_id')``
    on both versions (v17 ``purchase_stock/models/purchase_order.py:36-39``,
    v19 ``:44-47``), so an empty picking is never on it. Counting by
    ``origin`` instead would report N+1 on v17 — core's own empty receipt
    (``_create_picking`` v17 ``:237-261`` has no cleanup) — and N on v19,
    which unlinks it (``:400-401``). That version delta would masquerade as
    a regroup difference in TC201 and TC205.
    """
    return sorted(rpc.read("purchase.order", [order_id],
                           ["picking_ids"])[0]["picking_ids"])


def order_line_rows(rpc, order_id: int, fields_=None) -> list:
    fields_ = fields_ or ["product_id", "product_qty", "qty_received",
                          "date_planned", "price_unit", "state"]
    fields_ = [f for f in fields_
               if rpc.field_exists("purchase.order.line", f)]
    return rpc.search_read("purchase.order.line",
                           [("order_id", "=", order_id)], fields_, order="id")


def pickings_of(rpc, picking_ids, fields_=None) -> list:
    if not picking_ids:
        return []
    fields_ = fields_ or ["name", "state", "date_deadline", "origin",
                          "partner_id", "picking_type_id", "move_ids",
                          "location_id", "location_dest_id", "is_locked",
                          "date_done", "backorder_id"]
    fields_ = [f for f in fields_ if rpc.field_exists("stock.picking", f)]
    return rpc.search_read("stock.picking", [("id", "in", list(picking_ids))],
                           fields_, order="id")


def moves_of_order(rpc, order_id: int, fields_=None) -> list:
    """Every ``stock.move`` reachable from the order's lines.

    Read through ``purchase_line_id`` rather than through the pickings, so a
    move that has just been relocated onto a brand-new receipt is still in
    the set (that is precisely TC203's subject).
    """
    line_ids = rpc.search("purchase.order.line",
                          [("order_id", "=", order_id)])
    if not line_ids:
        return []
    fields_ = fields_ or ["picking_id", "purchase_line_id", "product_id",
                          "state", "date", "date_deadline", "product_uom_qty",
                          "quantity"]
    fields_ = [f for f in fields_ if rpc.field_exists("stock.move", f)]
    return rpc.search_read("stock.move",
                           [("purchase_line_id", "in", line_ids)],
                           fields_, order="id")


def move_lines_of(rpc, move_ids, fields_=None) -> list:
    if not move_ids:
        return []
    fields_ = fields_ or ["move_id", "picking_id", "product_id", "lot_id",
                          "lot_name", "quantity", "state"]
    fields_ = [f for f in fields_ if rpc.field_exists("stock.move.line", f)]
    return rpc.search_read("stock.move.line",
                           [("move_id", "in", list(move_ids))], fields_,
                           order="id")


def repromise_line(rpc, line_id: int, new_date: str):
    """The PUBLIC entry point for the whole deadline-regroup engine.

    ``purchase.order.line.write`` (dto override at
    ``models/purchase_order_line.py:106-110``) runs
    ``_check_fully_received_lines`` and then core's write, which calls
    ``_update_move_date_deadline`` (v17 ``purchase_stock/models/
    purchase_order_line.py:95-98``) and thence the DTO override at
    ``:74-90``. Every private helper in that chain is driven from here, and
    every consequence is observable through ``stock.move`` /
    ``stock.move.line`` / ``stock.picking`` — so nothing in this suite
    re-implements one.
    """
    return rpc.write("purchase.order.line", [line_id],
                     {"date_planned": new_date})


def repromise_expecting_error(rpc, line_id: int, new_date: str) -> str:
    """Attempt a re-promise the workbook expects to be refused.

    Returns the server's message, or ``""`` when nothing was raised. Each
    RPC call is its own transaction, so a refusal really is rolled back and
    a follow-up ``read`` sees the untouched stored value (TC206 step 6).
    """
    try:
        repromise_line(rpc, line_id, new_date)
    except OdooRPCError as exc:
        return str(exc)
    return ""


def expect_error(rpc_callable, *args, **kwargs):
    """Run a call the workbook expects to raise; return (raised, message)."""
    try:
        rpc_callable(*args, **kwargs)
        return False, "no error raised"
    except OdooRPCError as exc:
        return True, str(exc)


# ===========================================================================
# Receipt processing
# ===========================================================================
def set_move_quantity(rpc, move_id: int, quantity: float, picked=True):
    """Set the received quantity on one move (v17 and v19 both have
    ``stock.move.quantity`` and ``stock.move.picked`` — v17
    ``stock_move.py:111``, v19 ``:121``)."""
    values = {"quantity": quantity}
    if rpc.field_exists("stock.move", "picked"):
        values["picked"] = picked
    return rpc.write("stock.move", [move_id], values)


def assign_picking(rpc, picking_id: int):
    for method in ("action_confirm", "action_assign"):
        _try(rpc.call, "stock.picking", method, [picking_id])


def validate_picking(rpc, picking_id: int, backorder: bool | None = True):
    """``button_validate`` — public on both versions — and the return value.

    Returns whatever the server returned: ``True``, or an action dict. A
    partially-picked receipt yields the ``stock.backorder.confirmation``
    act_window, which is a plain dict and therefore RPC-safe; feed it to
    :func:`process_backorder` (``backorder=True``) or suppress the backorder
    with ``backorder=False``, which passes the core context key
    ``picking_ids_not_to_backorder`` (v17 ``stock/models/stock_picking.py:
    1155-1158``).
    """
    if backorder is False:
        return rpc.call("stock.picking", "button_validate", [picking_id],
                        context={"picking_ids_not_to_backorder": [picking_id],
                                 "skip_backorder": True})
    return rpc.call("stock.picking", "button_validate", [picking_id])


def is_backorder_action(action) -> bool:
    return bool(isinstance(action, dict)
                and action.get("res_model") == "stock.backorder.confirmation")


def process_backorder(rpc, picking_id: int):
    """Create and ``process`` the backorder wizard for one picking.

    ``stock.backorder.confirmation`` is a TransientModel with ``pick_ids``
    Many2many (v17 ``stock/wizard/stock_backorder_confirmation.py:21``); its
    ``default_get`` builds the confirmation lines from ``pick_ids``
    (``:28-38``) and ``process`` is public (``:52``). The
    ``button_validate_picking_ids`` context key is what makes ``process``
    re-enter ``button_validate`` (``:61-67``).
    """
    wizard_id = rpc.call(
        "stock.backorder.confirmation", "create",
        {"pick_ids": [(6, 0, [picking_id])]},
        context={"button_validate_picking_ids": [picking_id]})
    return rpc.call("stock.backorder.confirmation", "process", [wizard_id],
                    context={"button_validate_picking_ids": [picking_id]})


def receive_fully(ctx, picking_id: int):
    """Assign, pick every move in full, validate. Returns the action."""
    rpc = ctx.adapter.rpc
    assign_picking(rpc, picking_id)
    for move in rpc.search_read("stock.move",
                                [("picking_id", "=", picking_id)],
                                ["product_uom_qty"], order="id"):
        set_move_quantity(rpc, move["id"], move["product_uom_qty"])
    return validate_picking(rpc, picking_id)


def lot_sequence_row(rpc, company_id: int | None = None) -> dict | None:
    """The ``stock.lot.serial`` sequence, scoped to the acting company.

    Which column to read is the reverse of the obvious guess.
    ``number_next`` is a plain **stored** Integer (v17
    ``base/models/ir_sequence.py:142``) that ``implementation='standard'``
    does not advance — the live counter lives in the PostgreSQL sequence.
    ``number_next_actual`` is the **compute** that reads it
    (``:143``, ``_get_number_next_actual`` at ``:100-110``, the
    ``_predict_nextval`` branch at ``:108-110``), so it is the reliable
    reading. Both are returned and the caller decides.
    """
    domain = [("code", "=", LOT_SEQUENCE_CODE)]
    if company_id:
        domain.append(("company_id", "in", [company_id, False]))
    fields_ = ["number_next", "number_next_actual", "number_increment",
               "prefix", "padding", "implementation", "company_id"]
    fields_ = [f for f in fields_ if rpc.field_exists("ir.sequence", f)]
    rows = rpc.search_read("ir.sequence", domain, fields_, order="id",
                           limit=1)
    return rows[0] if rows else None


def lots_named(rpc, names) -> list:
    if not names:
        return []
    return rpc.search_read("stock.lot", [("name", "in", list(names))],
                           ["name", "product_id"], order="id")


# ===========================================================================
# Packing slip payloads and the merged print
# ===========================================================================
def tiny_pdf_bytes(text: str = "WF015") -> bytes:
    """A minimal, structurally valid one-page PDF built in memory.

    Built rather than read from disk so the fixture is deterministic and the
    suite owns no binary assets. The xref offsets are computed, so the file
    really parses — ``action_print_attached_packing_slip`` feeds it to
    ``ir.actions.report._merge_pdfs`` (stock_picking.py:107), which reads it
    with a real PDF library and would reject a hand-waved blob.
    """
    safe = "".join(c for c in text
                   if 32 <= ord(c) < 127 and c not in "()\\")[:60]
    content = f"BT /F1 12 Tf 20 100 Td ({safe}) Tj ET\n".encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(content)).encode("ascii") + b" >>\nstream\n"
        + content + b"endstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += str(number).encode("ascii") + b" 0 obj\n" + body + b"\nendobj\n"
    xref_at = len(out)
    size = str(len(objects) + 1).encode("ascii")
    out += b"xref\n0 " + size + b"\n0000000000 65535 f \n"
    for offset in offsets:
        out += ("%010d 00000 n \n" % offset).encode("ascii")
    out += (b"trailer\n<< /Size " + size + b" /Root 1 0 R >>\nstartxref\n"
            + str(xref_at).encode("ascii") + b"\n%%EOF\n")
    return bytes(out)


def tiny_pdf_b64(text: str = "WF015") -> str:
    return base64.b64encode(tiny_pdf_bytes(text)).decode("ascii")


#: A 1x1 baseline JPEG. Verified: 160 bytes, SOI ff d8 … EOI ff d9, so
#: PIL.Image.open succeeds and _convert_image_stream_to_pdf_stream
#: (stock_picking.py:63-85) can convert it to RGB/JPEG and wrap it.
_TINY_JPEG_B64 = (
    "/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRof"
    "Hh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/wAALCAABAAEBAREA/8QAFAAB"
    "AAAAAAAAAAAAAAAAAAAACf/EABQQAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQEAAD8AKp//2Q=="
)


def tiny_jpeg_b64() -> str:
    return _TINY_JPEG_B64


def tiny_jpeg_bytes() -> bytes:
    return base64.b64decode(_TINY_JPEG_B64)


def tiny_blob_b64(size: int = 64) -> str:
    """Deterministic non-image, non-PDF bytes for the refused uploads.

    The constraint never looks at the bytes (see the module docstring:
    ``_compute_mimetype`` is handed only ``name``), so the content of a
    rejected upload is irrelevant — what matters is that it is fixed, so the
    test is repeatable.
    """
    return base64.b64encode(bytes(range(size % 256)) or b"\x00").decode(
        "ascii")


def attach_packing_slip(rpc, picking_id: int, filename: str,
                        payload_b64: str | None = None):
    """Write the Binary + the Char in ONE call, as the form does.

    Order matters for what the test proves. The constraint is
    ``@api.constrains('packing_slip_attachment_name')``
    (stock_picking.py:27), so writing the Binary **alone** is never
    validated at all — :func:`attach_packing_slip_payload_only` exists to
    assert exactly that.
    """
    values = {"packing_slip_attachment_name": filename}
    if payload_b64 is not None:
        values["packing_slip_attachment"] = payload_b64
    return rpc.write("stock.picking", [picking_id], values)


def attach_packing_slip_payload_only(rpc, picking_id: int, payload_b64: str):
    """Write the Binary with no filename — the unvalidated path."""
    return rpc.write("stock.picking", [picking_id],
                     {"packing_slip_attachment": payload_b64})


def packing_slip_row(rpc, picking_id: int) -> dict:
    return rpc.read("stock.picking", [picking_id],
                    ["packing_slip_attachment_name",
                     "packing_slip_attachment"])[0]


def has_packing_slip(rpc, picking_id: int) -> bool:
    return bool(packing_slip_row(rpc, picking_id)["packing_slip_attachment"])


def print_packing_slips(rpc, picking_ids):
    """Call the PUBLIC merged-print method on a list of receipts, in order.

    ``self.filtered(...)`` (stock_picking.py:89) preserves recordset order,
    which for ``browse(ids)`` is the order of the ids passed — so this is
    how TC209 step 6 controls page order. The list-bound server action
    (``views/stock_picking_views.xml:44-54``) only calls this same method,
    so driving it directly tests the same code.
    """
    return rpc.call("stock.picking", "action_print_attached_packing_slip",
                    [list(picking_ids)])


def attachment_row(rpc, attachment_id: int, fields_=None) -> dict:
    fields_ = fields_ or ["name", "type", "res_model", "res_id", "mimetype",
                          "store_fname", "file_size", "checksum"]
    fields_ = [f for f in fields_ if rpc.field_exists("ir.attachment", f)]
    return rpc.read("ir.attachment", [attachment_id], fields_)[0]


_ACT_URL_RE = re.compile(r"/web/content/(\d+)")


def attachment_id_from_action(action) -> int | None:
    """The ``ir.attachment`` id inside the returned download action.

    The success return is fixed at ``stock_picking.py:134-138``:
    ``{'type': 'ir.actions.act_url', 'url':
    '/web/content/<id>?download=true', 'target': 'self'}``.
    """
    if not isinstance(action, dict):
        return None
    match = _ACT_URL_RE.search(action.get("url") or "")
    return int(match.group(1)) if match else None


def fetch_web_content(ctx, attachment_id: int) -> bytes:
    """Download an attachment over a real, authenticated web session."""
    opener = http_session(ctx.env)
    url = (f"{ctx.env.base_url}/web/content/{attachment_id}"
           "?download=true")
    with opener.open(url, timeout=120) as response:
        return response.read()


_PDF_PAGE_RE = re.compile(rb"/Type\s*/Page(?![s])")


def pdf_page_count(data: bytes) -> int:
    """Page count by byte scan — the QA venv has no PDF library.

    ``requirements.txt`` pins fastapi / uvicorn / playwright / PyYAML /
    pydantic / openpyxl / psycopg2-binary and nothing else; ``pypdf`` and
    ``PyPDF2`` are both absent, verified by ``pip list``. Counting
    ``/Type /Page`` objects (excluding ``/Pages``) is therefore the
    available measure. It is a HEURISTIC and must be labelled as one in any
    docstring that uses it: a producer that compresses the page tree into an
    object stream would defeat it. ``_merge_pdfs`` does not, so it holds for
    the merged output this suite produces.
    """
    return len(_PDF_PAGE_RE.findall(data))


def paperformat_of_company(rpc, company_id: int | None = None) -> dict | None:
    """The company paperformat the JPEG page is sized from.

    ``action_print_attached_packing_slip`` reads
    ``record.company_id.paperformat_id.print_page_width/height``
    (stock_picking.py:98-103). Both are COMPUTED on ``report.paperformat``
    (v17 ``report_paperformat.py:188-189``, compute ``:212-213``; v19
    ``:187-188``, ``:212-213``), and a company with no paperformat yields 0,
    which makes ``img2pdf.mm_to_pt(0)`` produce a zero-size page. A test
    that asserts page geometry must check this first.
    """
    company_id = company_id or own_company_id(rpc)
    row = rpc.read("res.company", [company_id], ["paperformat_id"])[0]
    fmt_id = m2o_id(row["paperformat_id"])
    if not fmt_id:
        return None
    fields_ = ["name", "format", "page_width", "page_height",
               "print_page_width", "print_page_height", "orientation",
               "disable_shrinking", "dpi", "default"]
    fields_ = [f for f in fields_
               if rpc.field_exists("report.paperformat", f)]
    return rpc.read("report.paperformat", [fmt_id], fields_)[0]


# ===========================================================================
# Labels — the wizard and the rendered streams
# ===========================================================================
def open_label_wizard_action(rpc, picking_id: int) -> dict:
    """``action_open_receipt_product_label_layout`` — PUBLIC.

    Returns the act_window dict for
    ``dto_purchase_stock.action_stock_picking_product_label_layout`` with
    its context **replaced** by ``{'default_picking_id': id}``
    (stock_picking.py:58-60) — the action's own context is discarded, which
    is worth asserting because the action record declares none
    (wizard/receipt_product_label_layout_views.xml:19-24).
    """
    return rpc.call("stock.picking",
                    "action_open_receipt_product_label_layout", [picking_id])


def make_label_wizard(rpc, picking_id: int,
                      print_format: str | None = None) -> int:
    """Create the wizard the way the action's context would.

    ``print_format`` is left out when the caller passes None so the
    declared default (``'dymo'``, ``wizard/receipt_product_label_layout.py:
    18``) is what actually gets stored — that is TC212 step 5.
    """
    values = {"picking_id": picking_id}
    if print_format is not None:
        values["print_format"] = print_format
    return rpc.create("stock.picking.product.label.layout", values)


def run_label_wizard(rpc, wizard_id: int) -> dict:
    """``process`` — PUBLIC (receipt_product_label_layout.py:31-38)."""
    return rpc.call("stock.picking.product.label.layout", "process",
                    [wizard_id])


def report_record(rpc, xmlid: str) -> dict | None:
    """The ``ir.actions.report`` row behind an XML id.

    Read rather than inferred so TC212/TC213 can assert ``report_type``,
    ``report_name``, ``paperformat_id`` and the ``print_report_name``
    expression against the stored record.
    """
    report_id = rpc.ref(xmlid)
    if not report_id:
        return None
    fields_ = ["name", "model", "report_type", "report_name", "report_file",
               "paperformat_id", "print_report_name", "binding_model_id"]
    groups_field = report_groups_field(rpc)
    if groups_field:
        fields_.append(groups_field)
    fields_ = [f for f in fields_
               if rpc.field_exists("ir.actions.report", f)]
    return rpc.read("ir.actions.report", [report_id], fields_)[0]


def report_groups_field(rpc) -> str | None:
    """``groups_id`` on v17, ``group_ids`` on v19 — or None.

    v17 ``base/models/ir_actions.py:134`` vs v19 ``:168``. Neither WF-015
    report record declares the field (``reports/report_views.xml:4-21``), so
    the rename the workbook flags for TC212/TC213 does not touch them; the
    helper exists so a test can prove that rather than assume it.
    """
    for name in ("group_ids", "groups_id"):
        if rpc.field_exists("ir.actions.report", name):
            return name
    return None


def render_report(ctx, report_name: str, docids, converter: str = "html",
                  encoding: str = "utf-8") -> str:
    """Render a QWeb report over the authenticated HTTP report route.

    ``_render_qweb_pdf`` / ``_render_qweb_html`` / ``_render_qweb_text`` are
    private and unreachable over ``call_kw``, but the web route is not:
    ``/report/<converter>/<reportname>[/<docids>]`` with ``auth='user'``
    (v17 ``web/controllers/report.py:23-50``; v19 ``:23-…``, plus
    ``readonly=True``), and ``_get_report`` accepts a ``report_name``
    (v17 ``ir_actions_report.py:565-579``).

    ``converter='html'`` is the correct surface for the Dymo label: it
    carries the SAME ``docs → move_ids → move_line_ids`` loop as the PDF
    (``report_receipt_product_label.xml:56-63``) without depending on
    wkhtmltopdf. ``converter='text'`` returns the ZPL stream verbatim.
    """
    opener = http_session(ctx.env)
    ids = ",".join(str(i) for i in
                   (docids if isinstance(docids, (list, tuple)) else [docids]))
    url = f"{ctx.env.base_url}/report/{converter}/{report_name}/{ids}"
    with opener.open(url, timeout=180) as response:
        return response.read().decode(encoding, errors="replace")


_LABEL_SHEET_RE = re.compile(r'class="[^"]*\bo_label_sheet\b[^"]*"')


def count_label_sheets(html: str) -> int:
    """Labels in the rendered Dymo HTML.

    One ``div.o_label_sheet`` per label — the detail template's root element
    (``report_receipt_product_label.xml:5``), emitted once per
    ``stock.move.line`` by the nesting at ``:56-63``. That is the count
    TC212 step 9 distinguishes from a per-move (2) or per-unit answer.
    """
    return len(_LABEL_SHEET_RE.findall(html))


def zpl_blocks(text: str) -> list:
    """Split a ZPL stream into its ``^XA`` … ``^XZ`` label blocks.

    ``^XA`` is emitted at ``report_receipt_product_label.xml:79`` and
    ``^XZ`` at ``:109``, once per ``stock.move.line``. The template's own
    indentation and XML whitespace end up in the stream, so parse by
    delimiter rather than by exact lines.
    """
    blocks = []
    for chunk in text.split("^XA")[1:]:
        head, sep, _tail = chunk.partition("^XZ")
        if sep:
            blocks.append("^XA" + head + "^XZ")
    return blocks


#: The ZPL field origins, verbatim from the template.
ZPL_SKU_ORIGIN = "^FO270,60"          # :84
ZPL_LOT_ORIGIN = "^FO120,60"          # :90
ZPL_DATE_ORIGIN = "^FT40,60"          # :94 — note the space after ^FD
ZPL_PO_LONG_ORIGIN = "^FT40,230"      # :98  — len(purchase_source) > 14
ZPL_PO_SHORT_ORIGIN = "^FT40,290"     # :101 — len(purchase_source) <= 14
ZPL_PO_NO_SOURCE_ORIGIN = "^FT40,380"  # :106 — purchase_source falsy
ZPL_QTY_ORIGIN = "^FT40,590"          # :108
#: The Dymo template writes ``QTY:`` with NO space (:39); the ZPL template
#: writes ``QTY: `` WITH one (:108). Assert on the values, not the literals.
DYMO_QTY_PREFIX = "QTY:"
ZPL_QTY_PREFIX = "QTY: "


# ===========================================================================
# Quality control
# ===========================================================================
def quality_test_type_id(rpc) -> int | None:
    ref = rpc.ref(XMLID_QC_TEST_TYPE_PASSFAIL)
    if ref and rpc.search("quality.point.test_type", [("id", "=", ref)]):
        return ref
    rows = rpc.search_read("quality.point.test_type",
                           [("technical_name", "=", "passfail")], ["id"],
                           limit=1)
    if rows:
        return rows[0]["id"]
    rows = rpc.search_read("quality.point.test_type", [], ["id"], order="id",
                           limit=1)
    return rows[0]["id"] if rows else None


def quality_team_id(rpc) -> int | None:
    ref = rpc.ref(XMLID_QC_TEAM)
    if ref and rpc.search("quality.alert.team", [("id", "=", ref)]):
        return ref
    rows = rpc.search_read("quality.alert.team", [], ["id"], order="id",
                           limit=1)
    return rows[0]["id"] if rows else None


def make_quality_point(rpc, picking_type_id: int, product_id: int,
                       label: str = "QP", measure_on: str = "product") -> int:
    """A token-named ``quality.point`` on one operation type.

    Required on both versions: ``name`` (defaults to 'New'),
    ``picking_type_ids``, ``team_id``, ``test_type_id``, ``company_id``
    (v17 ``enterprise-17.0/quality/models/quality.py:38-67``). Scoped to a
    single product so it cannot generate checks for live receipts, and
    unlinked in the caller's ``finally``.

    WF-015's open question — which quality.point records exist in
    production, and on which operation types — is Unknown, so this creates
    its own rather than depending on one.
    """
    values = {
        "name": tag(f"{MARKER} {label}"),
        "title": tag(f"{MARKER} {label}"),
        "picking_type_ids": [(6, 0, [picking_type_id])],
        "product_ids": [(6, 0, [product_id])],
        "measure_on": measure_on,
    }
    team = quality_team_id(rpc)
    if team:
        values["team_id"] = team
    test_type = quality_test_type_id(rpc)
    if test_type:
        values["test_type_id"] = test_type
    return rpc.create("quality.point", values)


def make_quality_check(rpc, picking_id: int, product_id: int,
                       point_id: int | None = None,
                       label: str = "QC") -> int:
    """A ``quality.check`` created straight through the ORM.

    TC214 step 13 asserts ``reason_for_return`` is NOT required at model
    level (``models/quality_check.py:6-27`` declares no ``required=``), and
    the only way to show that is to create a check without one. ``team_id``
    and ``test_type_id`` ARE required (v17 ``quality/models/quality.py:
    193-194`` and ``:201-203`` in the base model — the ``required=True``
    lands on ``:194`` and ``:203`` respectively), so both are supplied.
    """
    values = {
        "name": tag(f"{MARKER} {label}"),
        "picking_id": picking_id,
        "product_id": product_id,
    }
    if point_id:
        values["point_id"] = point_id
    team = quality_team_id(rpc)
    if team:
        values["team_id"] = team
    test_type = quality_test_type_id(rpc)
    if test_type:
        values["test_type_id"] = test_type
    return rpc.create("quality.check", values)


def checks_of_picking(rpc, picking_id: int, fields_=None) -> list:
    fields_ = fields_ or ["name", "quality_state", "reason_for_return",
                          "product_id", "picking_id", "point_id",
                          "additional_note"]
    fields_ = [f for f in fields_ if rpc.field_exists("quality.check", f)]
    return rpc.search_read("quality.check", [("picking_id", "=", picking_id)],
                           fields_, order="id")


def fail_checks_with_reason(rpc, check_ids, reason_code: str,
                            additional_note: str | None = None):
    """Drive the Enterprise fail wizard the way the Fail button does.

    ``quality.check.wizard.confirm_fail`` is PUBLIC (v17
    ``enterprise-17.0/quality_control/wizard/quality_check_wizard.py:87-91``,
    v19 ``:97``) and DTO's override writes the code onto **every** record in
    ``check_ids`` (``wizard/quality_check_wizard.py:32``) BEFORE calling
    ``super()`` (``:34``) — which is what TC214 steps 8 and 9 assert.

    ``check_ids`` is ``Many2many('quality.check', required=True)`` on both
    (v17 ``:13``, v19 ``:14``), and ``current_check_id`` is what core's
    ``confirm_fail`` calls ``do_fail()`` on, so it is set as well.
    """
    check_ids = list(check_ids)
    values = {"check_ids": [(6, 0, check_ids)],
              "reason_for_return": reason_code}
    if rpc.field_exists("quality.check.wizard", "current_check_id"):
        values["current_check_id"] = check_ids[0]
    if additional_note is not None and rpc.field_exists(
            "quality.check.wizard", "additional_note"):
        values["additional_note"] = additional_note
    wizard_id = rpc.create("quality.check.wizard", values)
    return wizard_id, rpc.call("quality.check.wizard", "confirm_fail",
                               [wizard_id])


def selection_of(rpc, model: str, field: str) -> list:
    """The declared selection of a field, as ``[[key, label], …]``.

    ``fields_get`` is public on every model, so this is the reachable way to
    assert the 19 codes (TC214 step 5) and to compare the three copies of
    the taxonomy against each other (step 14) without parsing source.
    """
    info = rpc.call(model, "fields_get", [field], attributes=["selection"])
    if field not in info:
        return []
    return [list(pair) for pair in (info[field].get("selection") or [])]


# ===========================================================================
# Chatter tracking
# ===========================================================================
def tracking_values(rpc, model: str, res_id: int) -> list:
    """The ``mail.tracking.value`` rows a tracked write produced.

    ``carrier_id`` and ``carrier_tracking_ref`` gain ``tracking=True`` only
    from DTO (``models/stock_picking.py:17-24``); core declares neither
    (v17 ``stock_delivery/models/stock_picking.py:90,92``).

    Two tracked fields changed in ONE ``write`` produce ONE
    ``mail.message`` carrying TWO ``mail.tracking.value`` rows — not two
    messages. TC219 step 6's "two chatter tracking lines, one per field" is
    therefore satisfied at the tracking-VALUE level; assert these rows, not
    a message count.
    """
    message_ids = rpc.search("mail.message", [("model", "=", model),
                                              ("res_id", "=", res_id)])
    if not message_ids:
        return []
    fields_ = ["mail_message_id", "field_id", "old_value_char",
               "new_value_char", "old_value_integer", "new_value_integer"]
    fields_ = [f for f in fields_
               if rpc.field_exists("mail.tracking.value", f)]
    rows = rpc.search_read("mail.tracking.value",
                           [("mail_message_id", "in", message_ids)], fields_,
                           order="id")
    field_ids = sorted({m2o_id(r.get("field_id")) for r in rows
                        if m2o_id(r.get("field_id"))})
    names = {}
    if field_ids:
        names = {f["id"]: f["name"]
                 for f in rpc.read("ir.model.fields", field_ids, ["name"])}
    for row in rows:
        row["field_name"] = names.get(m2o_id(row.get("field_id")))
    return rows


def tracked_field_names(rpc, model: str, res_id: int) -> list:
    return sorted({r["field_name"] for r in tracking_values(rpc, model, res_id)
                   if r.get("field_name")})


# ===========================================================================
# Journal entries (F076)
# ===========================================================================
def order_account_moves(rpc, order_id: int) -> list:
    """``purchase.order.account_move_ids`` — a NON-STORED compute.

    ``read`` recomputes it (``models/purchase_order.py:17-19,32-39``), so
    there is nothing to flush. Returns the move rows, keyed for baselines by
    ``name`` rather than id (convention rule 5).
    """
    move_ids = rpc.read("purchase.order", [order_id],
                        ["account_move_ids"])[0]["account_move_ids"]
    if not move_ids:
        return []
    return rpc.search_read("account.move", [("id", "in", move_ids)],
                           ["name", "move_type", "state", "journal_id"],
                           order="id")


def view_journal_entries_action(rpc, order_id: int):
    """``action_view_journal_entries`` — PUBLIC.

    It returns ``None`` when ``account_move_ids`` is empty
    (``purchase_order.py:63-64``) and has **no** ``ensure_one()`` (``:62``)
    while reading ``self.account_move_ids``, so calling it on more than one
    order raises ``Expected singleton``. Both are assertable facts.
    """
    return rpc.call("purchase.order", "action_view_journal_entries",
                    [order_id])


def view_packing_slip_attachments_action(rpc, order_id: int):
    """``action_view_packing_slip_attachments`` — PUBLIC, ``ensure_one()``.

    Returns ``stock.action_picking_tree_all`` updated with a domain on
    ``packing_slip_receipt_ids.ids`` and ``views=[(tree_view_id, 'tree'),
    (False,'form')]`` (``purchase_order.py:47-60``). Note the **literal**
    ``'tree'`` at ``:53`` paired with a view whose root element is
    ``<list>`` (``views/stock_picking_views.xml:36``) — an internal
    inconsistency worth recording, so compare the literal separately from
    ``fg_common.list_tag(ctx)``.
    """
    return rpc.call("purchase.order", "action_view_packing_slip_attachments",
                    [order_id])


# ===========================================================================
# TC205 — the normalised regroup snapshot
# ===========================================================================
def regroup_snapshot(ctx, order_id: int) -> dict:
    """The (picking, deadline, move) baseline, with identities normalised.

    The workbook's tuple is ``(picking.name, str(picking.date_deadline),
    move.id, move.state)``. Two of those cannot cross environments:
    ``move.id`` is a database id and ``picking.name`` comes from a per-
    database sequence — convention rule 5 forbids relying on either, and
    TC205 step 12 already concedes the name prefix. So both are replaced by
    **per-run ordinals**, assigned in a deterministic order:

    * pickings are ordinalised by ``(deadline, id)`` — deadline first so the
      ordering is a property of the data, not of the insert order;
    * moves are ordinalised by ``(purchase line sequence, product code,
      id)``.

    What survives is exactly what the case is about: which moves share a
    receipt, what deadline that receipt carries, and what state everything
    is in. ``pre_pickings`` is built from ``order.picking_ids`` — never from
    a search on ``origin`` — so v17's leftover empty core receipt
    (``purchase_stock/models/purchase_order.py:237-261``, no cleanup;
    v19 unlinks it at ``:400-401``) cannot masquerade as an engine
    difference in step 9.

    The deadline is recorded twice on purpose: the raw stored UTC
    ``Datetime`` AND the tz-localised date the engine actually groups on
    (``stock_picking.py:49``). A tuple carrying only one of them is
    ambiguous.
    """
    rpc = ctx.adapter.rpc
    picking_ids = order_picking_ids(rpc, order_id)
    pickings = pickings_of(rpc, picking_ids,
                           ["name", "state", "date_deadline", "move_ids"])
    moves = moves_of_order(rpc, order_id)
    lines = order_line_rows(rpc, order_id, ["product_id", "date_planned"])

    line_ordinal = {row["id"]: index
                    for index, row in enumerate(lines, start=1)}
    picking_ordinal = {}
    for index, row in enumerate(
            sorted(pickings, key=lambda p: (str(p.get("date_deadline")),
                                            p["id"])), start=1):
        picking_ordinal[row["id"]] = index

    def _product_code(move):
        return str(move.get("product_id") and move["product_id"][1] or "")

    move_ordinal = {}
    for index, row in enumerate(
            sorted(moves, key=lambda m: (
                line_ordinal.get(m2o_id(m.get("purchase_line_id")), 0),
                _product_code(m), m["id"])), start=1):
        move_ordinal[row["id"]] = index

    tz = user_timezone(rpc)
    move_tuples = sorted(
        f"move#{move_ordinal[m['id']]}|line#"
        f"{line_ordinal.get(m2o_id(m.get('purchase_line_id')), 0)}|"
        f"picking#{picking_ordinal.get(m2o_id(m.get('picking_id')), 0)}|"
        f"deadline={m.get('date_deadline') or ''}|state={m.get('state')}"
        for m in moves)
    picking_tuples = sorted(
        f"picking#{picking_ordinal[p['id']]}|"
        f"deadline={p.get('date_deadline') or ''}|state={p.get('state')}|"
        f"moves={len(p.get('move_ids') or [])}"
        for p in pickings)

    return {
        "tz": tz,
        "picking_count": len(pickings),
        "move_count": len(moves),
        "cancelled_pickings": sum(1 for p in pickings
                                  if p.get("state") == "cancel"),
        "moves": move_tuples,
        "pickings": picking_tuples,
    }


def cancelled_empty_pickings(rpc, picking_ids) -> list:
    """Receipts left in ``cancel`` with no moves — the TC204/TC205 outcome.

    ``_update_picking`` cancels an emptied picking rather than deleting it
    (``models/stock_move.py:31-32``), and ``action_cancel`` forces
    ``state='cancel'`` after ``is_locked=True`` (v17
    ``stock/models/stock_picking.py:950-954``, byte-identical on v19).
    Always read this back through a FRESH query: ``state`` is a stored
    compute whose "no moves" branch yields ``'draft'``
    (v17 ``:656-657``), so a later recompute is exactly what would flip it.
    """
    return [p for p in pickings_of(rpc, picking_ids)
            if p.get("state") == "cancel" and not (p.get("move_ids") or [])]


# ===========================================================================
# Static source scans (TC015, TC032)
# ===========================================================================
def grep_dto(ctx, modules, pattern: str, suffixes=None) -> dict:
    """``{module: [hits] | None}`` across the DTO addon roots.

    ``None`` for a module that is not present at all, so "clean" and "not
    there" never look the same. BLOCKS with a precise reason when the source
    tree is unreachable, rather than falling back to a weaker assertion.
    """
    root = require_source_root(ctx)
    return scan_modules(root, list(modules), pattern, suffixes=suffixes)


def manifest_text(ctx, module: str) -> str | None:
    """The raw ``__manifest__.py`` of one addon, or None when absent.

    TC015 reads the delivered versions of the two commercial modules this
    way. Today the tree holds their **v17** builds — ``printnode_base``
    ``'17.0.2.6.10'`` (``__manifest__.py:10``) and
    ``location_barcode_labels`` ``"2.0"`` (``:6``) — so a static read proves
    nothing about a v19 gate; see the plan doc for why TC015 is left
    unimplemented.
    """
    root = require_source_root(ctx)
    path = module_path(root, module)
    if path is None:
        return None
    manifest = path / "__manifest__.py"
    if not manifest.is_file():
        return None
    return manifest.read_text(encoding="utf-8", errors="replace")
