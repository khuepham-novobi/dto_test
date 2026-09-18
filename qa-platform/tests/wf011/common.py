"""Shared fixtures and helpers for the DATAONE-WF-011 suite
(Delivery, Boxing, Blind Ship & Packing Documents).

Owning workflow: DATAONE-WF-011, build order 14, area Inventory, effective
risk HIGH, fail mode "loud + silent". It owns 19 workbook test cases, four
of them P0 (TC158, TC159, TC163, TC164).

Everything asserted by this suite was read in the real source before a line
of it was written (AUTOMATION_CONVENTIONS hard rule 6). The v17 baseline is
the ``main`` branch of ``D:/Projects/dataone/DTO-Odoo`` (the working tree is
checked out on ``UAT``, which already carries the v19 port), so every
project-addon citation below was read with ``git show main:<path>`` and, where
the two differ, the v19 form is named as well.

What was read, and what this module therefore treats as fact
------------------------------------------------------------

``project-addons/dto_stock/models/stock_picking_box.py`` (v17 and v19 byte
identical):

* ``:9-11``   ``_name = 'stock.picking.box'``, ``_description = 'Delivery Box'``,
  ``_order = 'sequence, id'``
* ``:13-14``  ``picking_id`` M2O ``stock.picking``, ``required=True``,
  ``ondelete='cascade'``, ``index=True``
* ``:15``     ``sequence`` Integer, ``default=10``
* ``:16``     ``name = fields.Char('Box', required=True)``
* ``:17``     ``weight = fields.Float('Weight (lb)', digits='Stock Weight',
  required=True)``
* ``:19-23``  ``@api.constrains('weight')`` ``_check_weight`` — the test is
  **``rec.weight == 0``**, not ``<= 0``, so a NEGATIVE weight is accepted.
  That is the workbook's E2 / BR-6 live v17 defect and TC154 asserts it as
  the baseline. Message verbatim: ``Weight must be greater than zero.``

``digits='Stock Weight'`` resolves to the ``decimal.precision`` record
``product.decimal_stock_weight``, name ``Stock Weight``, digits ``2`` — present
unchanged in BOTH versions (``addons/product/data/product_data.xml:27-30`` on
v17 and on v19). The precision v19 dropped is ``Product Unit of Measure``,
which is a different record; TC154's ``v19_watch`` is therefore resolved.

``project-addons/dto_stock/models/stock_picking.py`` (v17):

* ``:11-12``  ``account_move_ids`` M2M ``account.move``, ``string='Journal
  Entries'``, ``compute='_compute_account_move_ids'`` — **not stored**
* ``:13-14``  ``weight`` / ``shipping_weight`` redefined ``compute=False,
  readonly=False`` (F079: operator-entered, BR-7)
* ``:16-18``  ``box_ids`` O2M, ``box_count`` Integer ``default=0``,
  ``default_box_weight`` Float ``digits='Stock Weight'``
* ``:20-29``  ``@api.depends('state')`` ``_compute_account_move_ids``; line
  ``:26`` reads ``StockScrap.search([('picking_id', '=', self.id)])`` — **``self.id``,
  not ``res.id``, inside ``for res in self``**. That is the E-1 / TC168 defect:
  any multi-record recompute raises ``ValueError: Expected singleton``
  (``odoo/fields.py:5163-5174``, ``class Id.__get__``). The v19 port preserves
  it verbatim and deliberately (WF011a-README ``# D-new-11``).
* ``:31-47``  ``action_create_boxes`` — **public**; ``ensure_one()`` ``:32``;
  ``if self.box_count <= 0: raise UserError(...)`` ``:33-34``;
  ``self.box_ids.unlink()`` ``:35`` (BR-5, destructive, unconfirmed);
  names ``_('Box %s') % i`` ``:39``; ``weight = self.default_box_weight`` ``:40``;
  ``sequence = i * 10`` ``:41``; ``self.box_count = 0`` ``:46``;
  ``return True`` ``:47`` — never an action dict, which is how TC152 proves
  "no confirmation dialog". Message verbatim:
  ``Number of Boxes must be greater than zero.``
* ``:49-63``  ``action_view_journal_entries`` — **public**, returns ``None`` when
  ``account_move_ids`` is empty ``:50-51``, else ``account.action_account_moves_all``
  with ``name``/``display_name`` = ``Journal Entries``,
  ``domain = [('id', 'in', self.account_move_ids.line_ids.ids)]`` ``:56`` (it
  filters ``account.move.line`` ids, not moves) and
  ``context = {'search_default_group_by_move': True, 'journal_type': 'general',
  'expand': True}`` ``:57-61``.

``project-addons/dto_stock/views/stock_picking_views.xml`` (v17):

* ``:3-23``  ``dto_stock.view_picking_form``, ``inherit_id="printnode_base.view_picking_form"``
  ``:6`` — the Journal Entries ``oe_stat_button`` (``icon="fa-book"``,
  ``invisible="not account_move_ids"``) at ``:10-17``, and the
  ``shipping_label_ids`` ``position="attributes"`` xpath at ``:19-21`` pinning
  ``context={'tree_view_ref': 'dto_stock.shipping_label_tree_on_picking'}``.
* ``:25-62`` ``dto_stock.view_picking_form_boxes``,
  ``inherit_id="stock.view_picking_form"`` ``:28``, xpath ``//page[@name='extra']``
  ``position="inside"`` ``:30``; ``<field name="picking_type_code" invisible="1"/>``
  ``:31``; ``<div invisible="picking_type_code != 'outgoing'">`` ``:32`` (BR-4 is a
  view MODIFIER, not conditional arch — the elements exist on every picking
  type, which is why TC155's "not present" half is browser-only and its
  step 7 control is the half that actually catches the v19 failure);
  ``box_count`` ``:36``, ``default_box_weight`` ``:37``; the ``action_create_boxes``
  button with ``invisible="box_count &lt;= 0"`` ``:40-42``; the ``box_ids`` kanban
  whose template is ``<t t-name="kanban-box">`` ``:50`` on v17 and
  ``<t t-name="card">`` on v19 (ported file ``:67``).

``project-addons/dto_stock/security/ir.model.access.csv`` (v17):

* ``:2-3`` re-declare PrintNode's OWN xml ids
  (``printnode_base.shipping_label_group_user`` and
  ``…_document_group_user``) as ``1,1,1,0`` — PrintNode ships them ``1,0,1,0``
  (``3rd-addons/printnode_base/security/ir.model.access.csv:51,53``). That
  cross-module override is F078, and v19 drops both rows.
* ``:4`` ``stock.group_stock_user`` → ``1,1,1,1`` on ``stock.picking.box``
* ``:5`` ``base.group_user`` → ``1,0,0,0`` (read only: a plain internal user
  can read a manifest but cannot create one)

``printnode_base.printnode_security_group_user`` is implied by
``base.group_user`` (``3rd-addons/printnode_base/security/security.xml:24-26``),
so every internal user is already a PrintNode user — no extra group work is
needed for TC156.

``project-addons/dto_stock/models/shipping_label.py`` — **v17 only, deleted in
the v19 port**: ``:10`` ``pieces = fields.Float('Pieces')``; ``:11-15``
``carrier_id`` / ``picking_id`` / ``tracking_numbers`` / ``label_ids`` /
``return_label_ids`` re-declared ``readonly=False``; ``:16``
``label_status = fields.Selection(default='active')``. The base model is
PrintNode's (``3rd-addons/printnode_base/models/shipping_label.py:11-60``:
``_name='shipping.label'``, ``carrier_id`` required, ``picking_id`` required with
``domain='[("picking_type_id.code", "=", "outgoing")]'``, ``label_status``
selection ``[('active','Active'), ('inactive','In Active')]`` with no default of
its own). ``stock.picking.shipping_label_ids`` is PrintNode's O2M
(``printnode_base/models/stock_picking.py:13-17``).

``project-addons/dto_mrp_account/models/stock_picking.py`` (v17, 21 lines):

* ``:8-11``  ``button_validate`` raises, **before** ``super()``, when
  ``not self.user_has_groups('dto_mrp_account.group_validate_delivery_orders')``
  **and** ``self.picking_type_id.id == self.env.ref('stock.picking_type_out').id``.
  Not wrapped in ``_()`` — assert it byte-exact:
  ``Only users in the 'Validate Delivery Orders' group can validate this picking.``
  ``self.picking_type_id`` on a multi-record set raises ``Expected singleton``:
  that is F179's live defect and the reason every case here validates ONE
  picking and asserts its type is exactly ``stock.picking_type_out`` first.
* ``:17-19`` ``write`` raises **unconditionally** (no ``vals`` inspection, every
  picking type) for a member of ``dto_mrp_account.group_transfers_read``:
  ``You are not allowed to change Transfers records.`` — also not ``_()``-wrapped.

``project-addons/dto_mrp_account/data/server_actions.xml`` (v17,
``<data noupdate="1">``): ``:18-24`` ``group_validate_delivery_orders``, name
``Validate Delivery orders`` (lowercase "orders"), **no ``category_id``**, seeded
``users`` = ``base.user_root`` + ``base.user_admin`` — so the platform's own
``admin`` session passes the F179 check and the NEGATIVE case must impersonate.
``:32-35`` ``group_transfers_read``, name ``Cannot edit transfers``,
``category_id`` = ``base.module_category_inventory_purchase``, **no seeded
users**, no ``implied_ids``, and grep confirms **no ``ir.rule`` anywhere** for
either group.

``project-addons/dto_sale_stock/models/stock_picking.py`` (v17 == v19):
``:10`` ``ship_blind = fields.Boolean(related='sale_id.ship_blind')`` — related,
**not stored, not ``readonly=False``**, which is exactly what TC162 asserts
through ``fields_get``; ``:12-22`` ``_action_done`` auto-invoices and posts for
``order_type in ('project', 'inventory', 'cost_center')`` with
``invoice_status == 'to invoice'`` (F040). ``buy`` is excluded — which is why
every fixture here that validates a picking defaults to ``order_type='buy'``
and TC159's isolation is source-correct.

``project-addons/dto_sale_stock/models/ir_actions_report.py`` (v17 == v19):
``:14-18`` — ``if isinstance(report_ref, str) and report_ref in
('stock.report_deliveryslip', 'dto_sale_stock.report_ship_blind')`` then
``pickings |= sale_pickings.sale_id.picking_ids.filtered(lambda p:
p.picking_type_code == 'outgoing' and p.state != 'cancel')``. Note ``|=``:
already-selected pickings are never duplicated (TC163 step 11 holds by
construction) and a SELECTED cancelled picking still prints. The override is
on ``_render_qweb_pdf``, which is private and therefore reachable **only**
through ``GET /report/pdf/<report_name>/<ids>``
(``addons/web/controllers/report.py:41-44`` passes a STRING ``report_ref``).
``/report/html/`` goes to ``_render_qweb_html`` (``:39``), which F044 does
**not** override — so the HTML route must never be substituted in TC163.

``project-addons/dto_sale_stock/report/report_delivery_document.xml``
(v17 == v19), inheriting ``stock.report_delivery_document``:
``:6`` ``header_report_name = 'PACKING SLIP'``; ``:9`` the
``name="shipping_label_table"`` table under ``t-if="o.shipping_label_ids"``;
``:13-16`` the four column headers — the source says **``Tracking/Pro Number``**
with a slash where the workbook prose writes a hyphen, and the source string
is what is asserted; ``:20`` one ``<tr>`` per ``shipping_label_ids`` entry;
``:31`` every row prints the SAME ``o.shipping_weight``; ``:36-49`` the boxes
grid chunked ``[o.box_ids[i:i+12] …]`` ``:38`` with padding ``<td>``s at ``:46``
(13 boxes ⇒ 2 rows, 13 populated + 11 empty = 24 ``<td>``, so TC165 step 9 must
count POPULATED cells); ``:51-56`` the ``note`` and ``memo_to_suppliers``
paragraphs.

``project-addons/dto_sale_stock/report/report_ship_blind.xml`` (v17 == v19):
``:5-8`` sets ``report_header_style`` / ``report_footer_style`` to
``display: none;``; ``:10-12`` inserts ``<h2>PACKING SLIP</h2>``; ``:15-17``
restricts the ship-to contact widget; ``:20-31`` ``class="d-none"`` on
``customer_address``, ``partner_header`` and ``div_origin``; ``:34-39`` hides
``move.product_id`` and prints ``move.product_id.name``. That product patch
covers only the NOT-done move table (core ``report_deliveryslip.xml:73``); a
**done** picking renders the aggregated move-line table, whose text is
``product_id.display_name`` (``stock/models/stock_move_line.py:823``) and
therefore still carries ``[default_code]``.

``project-addons/dto_sale_stock/report/report_templates.xml`` (v17) patches
``div[@name='moto']`` on ``external_layout_standard`` ``:4-11`` and the footer of
all four layouts ``:12-14, :18-20, :24-26, :30-32``. ``report_header_style`` is
consumed by CORE, and v17 carries it on all four header divs
(``addons/web/views/report_templates.xml:309, 368, 430, 492``). **v19 carries it
on ``external_layout_bold`` ONLY** (``:439``; measured — the other three and the
three new layouts have no such hook), so on v19 the blind slip prints with the
company header restored unless the company is on the bold layout. That is
TC164's named silent failure, established in source.

``project-addons/dto_sale_stock/wizard/stock_backorder_confirmation_views.xml``
``:8-9`` sets ``invisible="1"`` on ``//button[@name='process_cancel_backorder']``.
Core still ships that button on v19 (``stock/wizard/…_views.xml:36``), so the
inherit still resolves and BR-1's "loud good outcome" will not occur. Both
``process`` (``stock_backorder_confirmation.py:52``) and
``process_cancel_backorder`` (``:70``) are **public**, and both read
``self.env.context['button_validate_picking_ids']`` — which is why TC161 step 12
is feasible and is the documented limit of the control.

``project-addons/dto_sale_stock/data/base_automation_data.xml`` (v17) —
**the hard fixture constraint for this whole suite**. The automation
``dto_sale_stock.base_automation_send_email_on_sale_order_shipped`` fires on
``state -> done`` for pickings, and its server action's code at ``:59`` reads,
unguarded::

    if 'IRM' in order.memo_to_suppliers:

``sale.order.memo_to_suppliers`` is ``fields.Text``
(``dto_sale_workday/models/sale_order.py:17``) and reads ``False`` when NULL, so
a fixture order with an empty memo raises ``TypeError: argument of type 'bool'
is not iterable`` **inside the ``button_validate`` transaction** and aborts the
delivery. Every order built here therefore carries a non-empty
``memo_to_suppliers``. The same action calls ``send_mail(force_send=True)``
against hard-coded ``@d1systems.com`` recipients (``:49-70``), so every helper
that validates an outgoing picking with a ``sale_id`` calls
``require_mail_offline`` first (convention rule 4).

Order confirmation has three more gates, all read in source, all satisfied by
``make_sale_order``: ``requester_email`` must be set
(``dto_sale_workday/models/sale_order.py:24-26``), every line needs a
``requested_delivery_date`` (``dto_sale/models/sale_order.py:59-62``), and
``dto_account/models/sale_order.py:11-51`` demands an analytic distribution on
the plan matching ``order_type`` — ``project`` needs
``dto_account.project_analytic_plan``, ``buy`` needs
``dto_account.customer_contract_analytic_plan``, while ``inventory`` and
``cost_center`` must have **no** distribution at all.

``3rd-addons/stock_picking_auto_create_lot/models/stock_picking.py`` (v17 ==
v19): ``:9`` ``rma_number``; ``:11-33`` the 19-entry ``reason_for_return``
selection reproduced verbatim below; ``:35`` ``return_notes``; ``:66-68``
``button_validate`` calls the private ``_set_auto_lot()`` before ``super()``.

Two workbook SQL statements in TC054 cannot run as written, and the reason is
structural rather than a typo — both are adapted here and the adaptation is
recorded in the plan doc:

* ``stock_picking.ship_blind`` is a **non-stored related** field, so no such
  column exists on either version; it is read through ``sale_id.ship_blind``.
* ``stock_picking.packing_slip_attachment`` is ``fields.Binary`` with the
  default ``attachment=True`` (``dto_purchase_stock/models/stock_picking.py:14-16``;
  ``odoo/fields.py:2334-2348`` — ``column_type`` is ``None`` when attachment-backed),
  so it has no column either; it is counted through ``ir.attachment``
  (``res_model='stock.picking'``, ``res_field='packing_slip_attachment'``).

Safety
------
Every fixture is namespaced with ``WF011`` plus a per-execution token, swept
at test start and cleaned in a ``finally`` that cannot raise. Nothing here
modifies a pre-existing business record: no company, no paperformat, no
report, no live picking, no live order. ``sweep_wf011`` is best-effort by
design — a validated picking cannot be unlinked — and the fresh token is what
guarantees a survivor can never collide with this execution's assertions.
"""
from __future__ import annotations

import html as _html
import re
import uuid
import urllib.error
import zlib

from adapters.base import OdooRPC, OdooRPCError
from framework.dto_fixtures import (order_pickings, set_stock,  # noqa: F401
                                    stock_location, validate_picking)
from framework.fg_common import (form_arch, http_session, list_tag,  # noqa: F401
                                 m2o_id, make_trace, reconcile)
from framework.qa_fixtures import (QA_USER_PASSWORD,  # noqa: F401
                                   require_mail_offline, sweep_model,
                                   sweep_products, user_groups_field,
                                   with_categ)

WORKFLOW = "DATAONE-WF-011"
WORKFLOW_NAME = "Delivery, Boxing, Blind Ship & Packing Documents"
FEATURE = ("DATAONE-WF-011 Delivery, Boxing, Blind Ship & Packing "
           "Documents")
MARK = MARKER = "WF011"

trace = make_trace(FEATURE)

#: One namespace per process. Every test sweeps it open again at its own
#: first step, so no case can consume another case's fixtures (rule 5).
_TOKEN = f"{MARKER}-{uuid.uuid4().hex[:8].upper()}"

#: The modules whose behaviour this suite asserts, for the build preflight.
WF011_MODULES = ["dto_stock", "dto_sale_stock", "dto_mrp_account",
                 "dto_base", "printnode_base", "stock_picking_auto_create_lot"]

# --------------------------------------------------------------------------
# Verbatim error strings. Read from the source; never paraphrase, never
# match on a substring in place of these.
# --------------------------------------------------------------------------
#: dto_stock/models/stock_picking.py:34 — UserError, wrapped in _()
ERROR_BOX_COUNT_ZERO = "Number of Boxes must be greater than zero."
#: dto_stock/models/stock_picking_box.py:23 — ValidationError, wrapped in _()
ERROR_BOX_WEIGHT_ZERO = "Weight must be greater than zero."
#: dto_mrp_account/models/stock_picking.py:11 — UserError, NOT translated
ERROR_VALIDATE_GROUP = ("Only users in the 'Validate Delivery Orders' group "
                        "can validate this picking.")
#: dto_mrp_account/models/stock_picking.py:19 — UserError, NOT translated
ERROR_TRANSFERS_WRITE = "You are not allowed to change Transfers records."

# --------------------------------------------------------------------------
# Groups and XML ids
# --------------------------------------------------------------------------
GROUP_VALIDATE_DELIVERY = "dto_mrp_account.group_validate_delivery_orders"
GROUP_TRANSFERS_READ = "dto_mrp_account.group_transfers_read"
GROUP_STOCK_USER = "stock.group_stock_user"
GROUP_STOCK_MANAGER = "stock.group_stock_manager"
GROUP_ACCOUNT_READONLY = "account.group_account_readonly"
GROUP_INTERNAL_USER = "base.group_user"

#: dto_mrp_account/data/server_actions.xml:19 / :33 — the group LABELS, which
#: v19 keeps while moving category_id -> privilege_id and users -> user_ids.
GROUP_VALIDATE_DELIVERY_NAME = "Validate Delivery orders"
GROUP_TRANSFERS_READ_NAME = "Cannot edit transfers"

#: The single operation type F179 protects (dto_mrp_account/models/
#: stock_picking.py:9). Anything else — a second outgoing warehouse — is
#: unprotected; BR-2 and the workbook's open question.
PICKING_TYPE_OUT_XMLID = "stock.picking_type_out"

# --------------------------------------------------------------------------
# Boxes (F077)
# --------------------------------------------------------------------------
BOX_MODEL = "stock.picking.box"
BOX_FIELDS = ["picking_id", "sequence", "name", "weight"]
#: dto_stock/models/stock_picking.py:39 — _('Box %s') % i, i from 1..N
BOX_NAME_TEMPLATE = "Box %s"
#: dto_stock/models/stock_picking.py:41 — sequence = i * 10
BOX_SEQUENCE_STEP = 10
#: dto_sale_stock/report/report_delivery_document.xml:38 — chunks of 12
BOXES_PER_ROW = 12
#: dto_stock/views/stock_picking_views.xml:32 — the BR-4 modifier, verbatim
BOXES_SECTION_INVISIBLE = "picking_type_code != 'outgoing'"
#: dto_stock/views/stock_picking_views.xml:42 — note <= , so a NEGATIVE count
#: is guarded too, unlike the box-weight constraint.
CREATE_BOXES_INVISIBLE = "box_count <= 0"
CREATE_BOXES_METHOD = "action_create_boxes"
#: The four elements TC155 tracks, all of them inside the invisible <div>.
BOXES_SECTION_ELEMENTS = ["box_count", "default_box_weight", "box_ids"]


def expected_box_names(count: int) -> list[str]:
    """['Box 1', … 'Box N'] — dto_stock/models/stock_picking.py:39."""
    return [BOX_NAME_TEMPLATE % i for i in range(1, count + 1)]


def expected_box_sequences(count: int) -> list[int]:
    """[10, 20, … N*10] — dto_stock/models/stock_picking.py:41."""
    return [i * BOX_SEQUENCE_STEP for i in range(1, count + 1)]


# --------------------------------------------------------------------------
# Shipping labels (F078) — v17 only; deleted for v19 with no replacement
# --------------------------------------------------------------------------
SHIPPING_LABEL_MODEL = "shipping.label"
SHIPPING_LABEL_FIELD = "shipping_label_ids"
SHIPPING_LABEL_TREE_XMLID = "dto_stock.shipping_label_tree_on_picking"
SHIPPING_LABEL_FORM_XMLID = "dto_stock.shipping_label_form"
#: dto_stock/views/stock_picking_views.xml:20 — verbatim, including the v17
#: spelling of the key. v19 renames tree_view_ref -> list_view_ref, which is
#: TC156 step 10's detector.
SHIPPING_LABEL_TREE_CONTEXT = (
    "{'tree_view_ref': 'dto_stock.shipping_label_tree_on_picking'}")
#: printnode_base/models/shipping_label.py:54-60 — note the two-word label.
SHIPPING_LABEL_STATUS_SELECTION = [("active", "Active"),
                                   ("inactive", "In Active")]
#: dto_stock/models/shipping_label.py:16 — the default dto_stock adds.
SHIPPING_LABEL_DEFAULT_STATUS = "active"

#: The precise reason TC156 (and TC165's label half) reports BLOCKED rather
#: than FAILED. Decision D-1 (client, 22 Aug 2026) drops PrintNode for v19.
BLOCKED_PRINTNODE = (
    "requires printnode_base — shipping.label and dto_stock's `pieces` "
    "extension of it are owned by the commercial VentorTech module "
    "(3rd-addons/printnode_base/models/shipping_label.py:11-60 plus "
    "dto_stock/models/shipping_label.py:10-16, a file the v19 port deletes). "
    "Decision D-1 drops PrintNode for v19 with no replacement model, so this "
    "case is unexecutable on the v19 target and is a retire candidate "
    "(WF011a-README.md, D-new-13). The offline half is asserted above.")

# --------------------------------------------------------------------------
# Blind ship and the printed documents (F040/F043/F044/F045/F048)
# --------------------------------------------------------------------------
REPORT_DELIVERY_SLIP = "stock.report_deliveryslip"
REPORT_SHIP_BLIND = "dto_sale_stock.report_ship_blind"
ACTION_REPORT_DELIVERY = "stock.action_report_delivery"
ACTION_REPORT_SHIP_BLIND = "dto_sale_stock.action_report_ship_blind"
#: The two literals F044 keys on — dto_sale_stock/models/ir_actions_report.py:14
EXPANDED_REPORT_NAMES = (REPORT_DELIVERY_SLIP, REPORT_SHIP_BLIND)
#: report/stock_report_views.xml:9 and stock/report/stock_report_views.xml:20
BLIND_PRINT_REPORT_NAME = (
    "'Blind Packing Slip - %s - %s' % (object.partner_id.name or '', "
    "object.name)")
DELIVERY_PRINT_REPORT_NAME = (
    "'Delivery Slip - %s - %s' % (object.partner_id.name or '', object.name)")
BLIND_REPORT_TITLE = "Blind Packing Slip"
#: report_delivery_document.xml:6, rendered by F048's div[@name='moto'] patch
PACKING_SLIP_TITLE = "PACKING SLIP"
SHIPPING_TABLE_NAME = "shipping_label_table"
#: report_delivery_document.xml:13-16 — SOURCE strings. The workbook's prose
#: writes "Tracking-Pro Number"; the template says "Tracking/Pro Number".
SHIPPING_TABLE_HEADERS = ["Shipping Method", "Tracking/Pro Number",
                          "Pieces", "Weight"]
#: report_ship_blind.xml:20-31 — the blocks suppressed with class="d-none"
BLIND_HIDDEN_BLOCKS = ["customer_address", "partner_header", "div_origin"]
#: report_ship_blind.xml:16 — verbatim
BLIND_CONTACT_OPTIONS = ('{"widget": "contact", "fields": ["address"], '
                         '"no_marker": True, "phone_icons": False}')
#: report_ship_blind.xml:6-7 — the two style variables and their value
BLIND_STYLE = "display: none;"
#: The only layout whose header hook survives on v19
#: (odoo-19.0/addons/web/views/report_templates.xml:439).
LAYOUT_STANDARD = "web.external_layout_standard"
LAYOUT_BOLD = "web.external_layout_bold"
LAYOUTS_PATCHED_BY_F048 = [LAYOUT_STANDARD, LAYOUT_BOLD,
                           "web.external_layout_boxed",
                           "web.external_layout_striped"]
#: v19 additions F048 does not patch (report_templates.xml:563, :651, :724)
LAYOUTS_NEW_IN_V19 = ["web.external_layout_folder", "web.external_layout_wave",
                      "web.external_layout_bubble"]

BLOCKED_PDF_EXTRACTOR = (
    "requires a PDF text extractor — no pypdf, PyPDF2 or pdfminer is "
    "installed in the qa-platform venv and requirements.txt declares none, "
    "and the assertions this case exists for are only true of the RENDERED "
    "PDF: in the /report/html/ render the suppressed content is still "
    "present in the DOM under display:none / d-none. The suppression "
    "MECHANISM is asserted structurally above.")

# --------------------------------------------------------------------------
# Auto-invoice and order types (F040)
# --------------------------------------------------------------------------
#: dto_sale/models/sale_order.py:17-26 — verbatim keys and labels
ORDER_TYPE_SELECTION = [("project", "Project-based"), ("buy", "Buy/Sell"),
                        ("inventory", "Inventory"),
                        ("cost_center", "Cost Center")]
#: dto_sale_stock/models/stock_picking.py:16-18
AUTO_INVOICE_ORDER_TYPES = ("project", "inventory", "cost_center")
#: The one type that is NOT auto-invoiced — TC159's isolation.
ISOLATED_ORDER_TYPE = "buy"
#: dto_account/models/account_analytic_plan.py:6-12 — the plan each order
#: type's confirmation gate demands (dto_account/models/sale_order.py:19-51).
ORDER_TYPE_ANALYTIC_PLAN = {
    "project": "dto_account.project_analytic_plan",
    "buy": "dto_account.customer_contract_analytic_plan",
    "inventory": None,      # a distribution is REFUSED for these two
    "cost_center": None,
}

# --------------------------------------------------------------------------
# Backorder (F042 / BR-1)
# --------------------------------------------------------------------------
BACKORDER_MODEL = "stock.backorder.confirmation"
BACKORDER_LINE_MODEL = "stock.backorder.confirmation.line"
BACKORDER_VIEW_XMLID = "stock.view_backorder_confirmation"
BACKORDER_INHERIT_XMLID = "dto_sale_stock.dto_inherit_view_backorder_confirmation"
BACKORDER_PROCESS_BUTTON = "process"
BACKORDER_CANCEL_BUTTON = "process_cancel_backorder"
#: stock/wizard/stock_backorder_confirmation.py:61 and :71
BACKORDER_CONTEXT_KEY = "button_validate_picking_ids"

# --------------------------------------------------------------------------
# RMA / return metadata (TC054, shared with WF-024)
# --------------------------------------------------------------------------
RMA_FIELDS = ["rma_number", "reason_for_return", "return_notes"]
RMA_SEQUENCE_CODE = "rma_number"
#: stock_picking_auto_create_lot/models/stock_picking.py:13-31 — all 19,
#: verbatim (note the EN DASH in 902).
RMA_REASON_SELECTION = [
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
]
#: TC054 step 5's "other DataOne picking fields", with the module that really
#: owns each — the workbook attributes them to the two modules it names, and
#: two of them belong elsewhere.
DTO_PICKING_FIELDS = {
    "rma_number": "stock_picking_auto_create_lot",
    "reason_for_return": "stock_picking_auto_create_lot",
    "return_notes": "stock_picking_auto_create_lot",
    "ship_blind": "dto_sale_stock (related, NOT stored — no column)",
    "carrier_tracking_ref": "dto_purchase_stock (redefined tracking=True)",
    "shipping_weight": "dto_stock (compute disabled -> plain stored column)",
    "packing_slip_attachment": "dto_purchase_stock (Binary, attachment-backed "
                               "— no column)",
    "packing_slip_attachment_name": "dto_purchase_stock",
    "box_count": "dto_stock",
    "default_box_weight": "dto_stock",
}

# --------------------------------------------------------------------------
# Custom reports and paperformats (TC011)
# --------------------------------------------------------------------------
#: Module prefixes that mark a report as DataOne-owned, plus the three
#: 3rd-party modules the workbook names for this case.
CUSTOM_REPORT_MODULES = ["dto_base", "dto_mrp", "dto_purchase_stock",
                         "dto_sale_stock", "location_barcode_labels",
                         "stock_picking_auto_create_lot", "printnode_base"]
#: Read out of the source (see the module docstring's file list). Every one
#: of these is an <record model="ir.actions.report"> in the v17 tree.
CUSTOM_REPORT_XMLIDS = [
    "location_barcode_labels.barcodelabelslocation",
    "stock_picking_auto_create_lot.action_report_return",
    "dto_mrp.action_report_pick_list",
    "dto_mrp.action_report_bin_label",
    "dto_mrp.action_report_cut_sheet",
    "dto_mrp.label_lot_template_dto",
    "dto_purchase_stock.report_receipt_product_label_dymo",
    "dto_purchase_stock.report_receipt_product_label_zpl",
    "dto_sale_stock.action_report_location_barcode",
    "dto_sale_stock.action_report_ship_blind",
]
#: The three custom paperformats that each ship `default eval="True"` on the
#: v17 baseline — dto_base/reports/report_views.xml:6 (main),
#: dto_mrp/data/report_paperformat_data.xml:5,
#: location_barcode_labels/views/barcode_labels_location.xml:15.
#: Core adds base.paperformat_euro and base.paperformat_us on top, and there
#: is NO ORM constraint enforcing a single default
#: (odoo/addons/base/models/report_paperformat.py:167-189).
PAPERFORMAT_DEFAULT_CLAIMANTS = [
    "dto_base.paperformat_dto_label_sheet_dymo",
    "dto_mrp.paperformat_us_mrp",
    "location_barcode_labels.paperformat_dynamic_barcodelabels_location",
]
#: v19's only new field on report.paperformat (report_paperformat.py:189).
V19_PAPERFORMAT_NEW_FIELDS = ["css_margins"]
#: ir.actions.report.groups_id (v17 :137) -> group_ids (v19 :182), plus the
#: new v19 `domain` field (:192).
REPORT_GROUPS_FIELDS = ("groups_id", "group_ids")


# --------------------------------------------------------------------------
# Naming
# --------------------------------------------------------------------------
def fixture_token() -> str:
    return _TOKEN


def tag(name: str) -> str:
    """Namespace a fixture value for this execution: 'WF011-AB12CD34 Foo'."""
    return f"{_TOKEN} {name}"


def fx(name: str) -> str:
    """Alias of :func:`tag`, for symmetry with the other suites."""
    return tag(name)


def _safe(fn, *args, **kwargs):
    """Run a teardown step that must never raise (convention rule 3)."""
    try:
        return fn(*args, **kwargs)
    except Exception:                                   # noqa: BLE001
        return None


# --------------------------------------------------------------------------
# Preconditions — each blocks with a precise reason naming what is missing
# --------------------------------------------------------------------------
def require_module_build(ctx, modules=None):
    """BLOCK when the target runs a module build from the wrong series.

    ``dto.conf`` points ``addons_path`` at ``D:/Projects/dataone/DTO-Odoo``,
    whose working tree is checked out on ``UAT`` — the **v19 port** — while
    ``ODOO17_DB`` is the v17 baseline. A v19-coded ``dto_stock`` served by a
    v17 instance is not the baseline any WF-011 case describes, and every
    assertion here would be measuring the wrong code.

    ``ir.module.module.latest_version`` is the version the DATABASE has
    installed and ``installed_version`` is the version on disk — the labels
    are inverted in core (``odoo/addons/base/models/ir_module.py:284-288``).
    Both are logged; a mismatch between them means the server has loaded a
    checkout the database was never updated with, which is the same trap
    from the other direction.
    """
    rpc = ctx.adapter.rpc
    series = f"{ctx.env.version}."
    rows = rpc.search_read(
        "ir.module.module", [("name", "in", modules or WF011_MODULES)],
        ["name", "state", "latest_version", "installed_version"], order="name")
    wrong = []
    for row in rows:
        if row["state"] != "installed":
            continue
        ctx.log(f"  {row['name']}: db={row['latest_version']!r} "
                f"disk={row['installed_version']!r}")
        if not str(row["latest_version"] or "").startswith(series):
            wrong.append((row["name"], row["latest_version"]))
    if wrong:
        ctx.blocked(
            f"{ctx.env.key} (db={ctx.env.db}) reports Odoo {ctx.env.version} "
            f"but these modules are installed from another series: {wrong}. "
            "DTO-Odoo's working tree is on branch UAT (the v19 port) while "
            "the v17 baseline lives on branch main, and dto.conf points "
            "addons_path at that same tree — confirm which checkout the "
            "server loaded before trusting any WF-011 verdict.")
    return {r["name"]: r for r in rows}


def require_modules(ctx, names):
    """BLOCK unless every named module is installed on the target."""
    rpc = ctx.adapter.rpc
    installed = {r["name"] for r in rpc.search_read(
        "ir.module.module",
        [("name", "in", list(names)), ("state", "=", "installed")], ["name"])}
    missing = [n for n in names if n not in installed]
    if missing:
        ctx.blocked(
            f"These modules are not installed on {ctx.env.key} "
            f"(db={ctx.env.db}): {', '.join(missing)}. WF-011's behaviour is "
            "contributed by them, so the case has nothing to assert against.")


def require_boxes(ctx):
    """BLOCK unless dto_stock contributed the box manifest (F077)."""
    rpc = ctx.adapter.rpc
    missing = []
    if not rpc.model_exists(BOX_MODEL):
        missing.append(BOX_MODEL)
    for field in ("box_ids", "box_count", "default_box_weight"):
        if not rpc.field_exists("stock.picking", field):
            missing.append(f"stock.picking.{field}")
    if missing:
        ctx.blocked(
            f"dto_stock is not contributing the delivery box manifest to "
            f"{ctx.env.key} (db={ctx.env.db}) — missing: "
            f"{', '.join(missing)}. F077 (dto_stock/models/"
            "stock_picking_box.py and stock_picking.py:31-47) is the whole "
            "subject of this case.")


def require_journal_entry_button(ctx):
    """BLOCK unless dto_stock contributed the F080 stat-button compute."""
    rpc = ctx.adapter.rpc
    if not rpc.field_exists("stock.picking", "account_move_ids"):
        ctx.blocked(
            "stock.picking.account_move_ids does not exist on "
            f"{ctx.env.key} (db={ctx.env.db}) — dto_stock is not installed, "
            "so neither the Journal Entries stat button (F080) nor the "
            "self.id singleton defect it carries "
            "(dto_stock/models/stock_picking.py:26) exists to be tested.")


def require_delivery_groups(ctx):
    """BLOCK unless both dto_mrp_account picking-control groups resolve."""
    rpc = ctx.adapter.rpc
    missing = [x for x in (GROUP_VALIDATE_DELIVERY, GROUP_TRANSFERS_READ)
               if not rpc.ref(x)]
    if missing:
        ctx.blocked(
            f"These groups do not resolve on {ctx.env.key} "
            f"(db={ctx.env.db}): {', '.join(missing)}. They are declared in "
            "dto_mrp_account/data/server_actions.xml:18-35 inside "
            '<data noupdate="1">, so an absent one means dto_mrp_account is '
            "not installed and F179/F180 cannot be exercised.")
    if not rpc.ref(PICKING_TYPE_OUT_XMLID):
        ctx.blocked(
            f"{PICKING_TYPE_OUT_XMLID} does not resolve on {ctx.env.key}. "
            "dto_mrp_account/models/stock_picking.py:9 resolves it with "
            "env.ref() on every button_validate, so its absence breaks "
            "validation outright rather than failing this case.")


def require_ship_blind(ctx):
    """BLOCK unless the blind-ship flag exists on both models (F043)."""
    rpc = ctx.adapter.rpc
    missing = [f"{model}.ship_blind" for model in ("sale.order", "stock.picking")
               if not rpc.field_exists(model, "ship_blind")]
    if missing:
        ctx.blocked(
            f"dto_sale_stock is not contributing blind shipping to "
            f"{ctx.env.key} (db={ctx.env.db}) — missing: "
            f"{', '.join(missing)} (dto_sale_stock/models/sale_order.py:10 "
            "and models/stock_picking.py:10).")


def require_printnode_labels(ctx):
    """BLOCK — with the D-1 reason — unless shipping.label + pieces exist.

    On the v17 baseline this passes and the case runs in full. On v19 the
    model is gone, and the workbook's own Notes require this case to report
    BLOCKED rather than FAILED.
    """
    rpc = ctx.adapter.rpc
    if not rpc.model_exists(SHIPPING_LABEL_MODEL):
        ctx.blocked(BLOCKED_PRINTNODE + " (shipping.label does not exist)")
    if not rpc.field_exists(SHIPPING_LABEL_MODEL, "pieces"):
        ctx.blocked(BLOCKED_PRINTNODE +
                    " (shipping.label exists but dto_stock's `pieces` "
                    "extension does not)")
    if not rpc.field_exists("stock.picking", SHIPPING_LABEL_FIELD):
        ctx.blocked(BLOCKED_PRINTNODE +
                    " (stock.picking.shipping_label_ids does not exist)")


def require_sale_stack(ctx):
    """BLOCK unless a confirmable DataOne sales order can be built.

    Every gate is named with its source location so a BLOCKED reason is
    actionable rather than "the fixture failed".
    """
    rpc = ctx.adapter.rpc
    missing = []
    if not rpc.field_exists("sale.order", "order_type"):
        missing.append("sale.order.order_type (dto_sale/models/"
                       "sale_order.py:17)")
    if not rpc.field_exists("sale.order", "requester_email"):
        missing.append("sale.order.requester_email (dto_sale_workday/models/"
                       "sale_order.py:16 — action_confirm raises without it)")
    if not rpc.field_exists("sale.order", "memo_to_suppliers"):
        missing.append("sale.order.memo_to_suppliers (dto_sale_workday/models/"
                       "sale_order.py:17 — the F041 automation reads "
                       "'IRM' in it, unguarded)")
    if not rpc.field_exists("stock.picking", "sale_id"):
        missing.append("stock.picking.sale_id (sale_stock)")
    if missing:
        ctx.blocked(
            f"A DataOne sales order cannot be built on {ctx.env.key} "
            f"(db={ctx.env.db}) — missing: {'; '.join(missing)}.")


def require_blind_report(ctx):
    """BLOCK unless the two report actions this suite prints resolve."""
    rpc = ctx.adapter.rpc
    missing = [x for x in (ACTION_REPORT_DELIVERY, ACTION_REPORT_SHIP_BLIND)
               if not rpc.ref(x)]
    if missing:
        ctx.blocked(
            f"These report actions do not resolve on {ctx.env.key}: "
            f"{', '.join(missing)}. dto_sale_stock/report/"
            "stock_report_views.xml:3-12 declares the blind slip and core's "
            "stock/report/stock_report_views.xml:14-23 the delivery slip.")


def company_layout_xmlid(ctx) -> str:
    """The external report layout the printing company actually uses.

    ``web.external_layout`` t-calls ``company.external_report_layout_id.key``
    and falls back to ``web.external_layout_standard`` when it is unset
    (v17 ``addons/web/views/report_templates.xml:576-577``).
    """
    rpc = ctx.adapter.rpc
    company_id = m2o_id(rpc.read("res.users", [rpc.uid],
                                 ["company_id"])[0]["company_id"])
    row = rpc.read("res.company", [company_id],
                   ["name", "external_report_layout_id"])[0]
    view_id = m2o_id(row["external_report_layout_id"])
    if not view_id:
        return LAYOUT_STANDARD
    return (rpc.read("ir.ui.view", [view_id], ["key"])[0].get("key")
            or LAYOUT_STANDARD)


def require_standard_layout(ctx):
    """BLOCK unless the company prints on the layout F048 fully patches.

    TC163's ``PACKING SLIP`` string reaches the page ONLY through F048's
    ``div[@name='moto']`` replacement, which dto_sale_stock declares for
    ``external_layout_standard`` alone
    (dto_sale_stock/report/report_templates.xml:3-11). On any other layout
    the string is absent even when F044's expansion worked perfectly — the
    workbook's own Notes warn about exactly that confusion.
    """
    layout = company_layout_xmlid(ctx)
    ctx.log(f"company external_report_layout_id resolves to {layout!r}")
    if layout != LAYOUT_STANDARD:
        ctx.blocked(
            f"The printing company on {ctx.env.key} uses {layout!r}, not "
            f"{LAYOUT_STANDARD!r}. dto_sale_stock/report/report_templates.xml"
            ":3-11 replaces div[@name='moto'] on the STANDARD layout only, "
            "so 'PACKING SLIP' never reaches the page under any other "
            "layout and a failure here would be attributed to F044's "
            "expansion, which would be wrong. Never change the company "
            "record to satisfy this — record it and run the case on a clone "
            "configured with the standard layout.")
    return layout


# --------------------------------------------------------------------------
# Sweeping
# --------------------------------------------------------------------------
def sweep_wf011(rpc):
    """Best-effort teardown of this suite's namespace, children first.

    Order: boxes and shipping labels -> pickings -> scraps -> sale orders ->
    carriers -> quants -> products -> analytic accounts -> partners. A
    validated picking cannot be unlinked and a posted move cannot be undone,
    so the sweep resets what it can and removes what it may; the fresh
    execution token is what guarantees a survivor cannot collide with this
    run's assertions.

    Never raises — and that is enforced rather than asserted. ``_safe`` wraps
    a CALLABLE plus its arguments, so an ``rpc`` call written inside the
    argument list would be evaluated eagerly and escape the guard entirely;
    every transport call below is therefore either the ``_safe`` callable
    itself or inside its own ``try``.
    """
    picking_ids = []
    picking_ids.extend(_safe(rpc.search, "stock.picking",
                             [("origin", "like", MARKER)]) or [])
    order_ids = _safe(rpc.search, "sale.order",
                      [("origin", "like", MARKER),
                       ("active", "in", [True, False])]) or []
    if order_ids and _safe(rpc.field_exists, "stock.picking", "sale_id"):
        picking_ids.extend(
            _safe(rpc.search, "stock.picking",
                  [("sale_id", "in", order_ids)]) or [])
    picking_ids = sorted(set(picking_ids))

    if picking_ids:
        if _safe(rpc.model_exists, BOX_MODEL):
            _safe(sweep_model, rpc, BOX_MODEL,
                  [("picking_id", "in", picking_ids)])
        if _safe(rpc.model_exists, SHIPPING_LABEL_MODEL):
            _safe(sweep_model, rpc, SHIPPING_LABEL_MODEL,
                  [("picking_id", "in", picking_ids)])
        _safe(sweep_model, rpc, "stock.scrap",
              [("picking_id", "in", picking_ids)])
        for picking_id in picking_ids:
            try:
                rpc.call("stock.picking", "unlink", [picking_id])
            except Exception:                               # noqa: BLE001
                _safe(rpc.call, "stock.picking", "action_cancel", [picking_id])
                _safe(rpc.call, "stock.picking", "unlink", [picking_id])

    _safe(sweep_model, rpc, "stock.scrap", [("origin", "like", MARKER)])

    if order_ids:
        _safe(rpc.write, "sale.order", order_ids, {"state": "draft"})
        try:
            rpc.call("sale.order", "unlink", order_ids)
        except Exception:                                   # noqa: BLE001
            _safe(rpc.write, "sale.order", order_ids, {"active": False})

    if _safe(rpc.model_exists, "delivery.carrier"):
        _safe(sweep_model, rpc, "delivery.carrier",
              [("name", "like", MARKER), ("active", "in", [True, False])])

    product_ids = _safe(rpc.search, "product.product",
                        [("default_code", "like", MARKER),
                         ("active", "in", [True, False])]) or []
    if product_ids:
        _safe(sweep_model, rpc, "stock.quant",
              [("product_id", "in", product_ids)])
    _safe(sweep_products, rpc, MARKER)
    _safe(sweep_model, rpc, "product.product",
          [("default_code", "like", MARKER), ("active", "in", [True, False])])
    _safe(sweep_model, rpc, "product.template",
          [("default_code", "like", MARKER), ("active", "in", [True, False])])

    _safe(sweep_model, rpc, "account.analytic.account",
          [("name", "like", MARKER), ("active", "in", [True, False])])
    _safe(sweep_model, rpc, "res.partner",
          [("name", "like", MARKER), ("user_ids", "=", False),
           ("active", "in", [True, False])])


def open_namespace(ctx):
    """First step of every case: sweep the marker, log the token.

    The sweep is a PRECONDITION here, not a teardown, so it is wrapped the
    same way the ``finally:`` sites wrap it: a transport fault while tidying
    leftovers must surface as a logged precondition note, never as an
    AUTOMATION_ERROR charged to the case. The fresh execution token is what
    actually guarantees isolation — a survivor of a previous run cannot
    collide with this run's assertions — so an incomplete sweep is not fatal.
    """
    with ctx.step(f"Sweep previous {MARKER} fixtures and open a fresh "
                  "namespace"):
        try:
            sweep_wf011(ctx.adapter.rpc)
        except Exception as exc:                            # noqa: BLE001
            ctx.log(f"[warn] the opening sweep of {MARKER} did not complete: "
                    f"{exc!r}. Isolation still holds through the execution "
                    f"token; leftovers from a previous run are recorded, not "
                    f"asserted against.")
        ctx.log(f"fixture token = {_TOKEN}")


# --------------------------------------------------------------------------
# Users, groups, impersonation
# --------------------------------------------------------------------------
def user_login(suffix: str) -> str:
    """Stable login for a role user. Deliberately NOT token-scoped: users are
    infrastructure, reused across runs, and their groups are reset on every
    ``ensure_user`` call so membership is deterministic."""
    return f"qa.wf011.{suffix}"


def ensure_user(ctx, suffix: str, group_xmlids=()) -> tuple[int, str]:
    """A disposable internal user in exactly ``base.group_user`` + the given
    groups. Returns ``(user_id, login)``.

    The groups m2m is version-dependent (``groups_id`` on v17,
    ``group_ids`` on v19), so the name comes from
    ``ctx.adapter.user_groups_field`` and no version branch reaches a test.

    Membership is written with ``(6, 0, ids)`` — a full replace — so a user
    left in ``group_transfers_read`` by an interrupted run cannot poison the
    next one.
    """
    rpc = ctx.adapter.rpc
    groups_field = ctx.adapter.user_groups_field
    login = user_login(suffix)
    wanted = [rpc.ref(x) for x in [GROUP_INTERNAL_USER] + list(group_xmlids)]
    missing = [x for x, gid in
               zip([GROUP_INTERNAL_USER] + list(group_xmlids), wanted)
               if not gid]
    if missing:
        ctx.blocked(f"These groups do not resolve on {ctx.env.key}: "
                    f"{', '.join(missing)} — the fixture user cannot be "
                    "built with the membership the case needs.")
    wanted = [gid for gid in wanted if gid]
    found = rpc.search("res.users", [("login", "=", login),
                                     ("active", "in", [True, False])], limit=1)
    if found:
        rpc.write("res.users", found,
                  {"active": True, "password": QA_USER_PASSWORD,
                   groups_field: [(6, 0, wanted)]})
        return found[0], login
    user_id = rpc.call("res.users", "create",
                       {"name": f"QA WF011 {suffix}", "login": login,
                        "password": QA_USER_PASSWORD,
                        groups_field: [(6, 0, wanted)]},
                       context={"no_reset_password": True})
    return user_id, login


def session_as(env, login: str) -> OdooRPC:
    """A second authenticated RPC session as ``login``."""
    import copy
    user_env = copy.copy(env)
    user_env.username = login
    user_env.password = QA_USER_PASSWORD
    return OdooRPC(user_env)


def add_user_to_group(ctx, user_id: int, group_xmlid: str):
    """Add a membership AS ADMIN.

    ``group_transfers_read`` denies every ``stock.picking`` write for its
    members (dto_mrp_account/models/stock_picking.py:17-19), so membership
    must be granted and revoked through the admin session; a member cannot
    tidy up after itself.
    """
    rpc = ctx.adapter.rpc
    rpc.write("res.users", [user_id],
              {ctx.adapter.user_groups_field: [(4, rpc.ref(group_xmlid))]})


def remove_user_from_group(ctx, user_id: int, group_xmlid: str):
    """Revoke a membership AS ADMIN. Safe to call in a ``finally``."""
    rpc = ctx.adapter.rpc
    group_id = _safe(rpc.ref, group_xmlid)
    if group_id:
        _safe(rpc.write, "res.users", [user_id],
              {ctx.adapter.user_groups_field: [(3, group_id)]})


def user_group_ids(ctx, user_id: int) -> list[int]:
    field = ctx.adapter.user_groups_field
    return rpc_read_one(ctx.adapter.rpc, "res.users", user_id, [field])[field]


def user_has_group(rpc: OdooRPC, user_id: int, group_xmlid: str) -> bool:
    """Is ``user_id`` a member of ``group_xmlid``, with each version's own
    semantics, WITHOUT calling ``res.users.has_group`` over RPC.

    ``has_group`` cannot serve this on the v17 baseline. It is ``@api.model``
    there (``O17 base/models/res_users.py:1085-1086``), so ``call_kw`` routes
    it through ``_call_kw_model``, which applies the whole ``args`` list to
    the method (``O17 odoo/api.py`` / ``odoo/http.py`` model dispatch) — the
    id list lands in ``group_ext_id`` and the extra positional raises
    ``TypeError: has_group() takes 2 positional arguments but 3 were given``.
    Worse, even a correctly-shaped v17 call could not answer the question
    asked: ``_has_group`` tests ``self._uid`` (``:1107-1109``), i.e. the
    SESSION user, never the ``user_id`` argument. On v19 the same name is a
    record method with ``ensure_one()`` (``O19 :1066, 1074``) and the call
    shape does work — so routing on the method would be a version branch that
    is wrong on one side and right on the other.

    The membership read below is exact on both, and probes a CAPABILITY
    rather than a version number:

    * v17 ``_has_group`` resolves explicit membership in
      ``res_groups_users_rel`` (``:1107-1109``), which is precisely the
      ``groups_id`` m2m. The SQL itself is not transitive, but the DATA it
      reads is already expanded: ``UsersImplied.write`` re-writes
      ``groups_id`` with every ``trans_implied_ids`` of the groups just
      granted (``O17 res_users.py:1452-1470``, and ``create`` at
      ``:1441-1450``), so no expansion is needed at read time.
    * v19 ``_has_group`` resolves through ``all_group_ids``, the transitive
      closure computed by ``_compute_all_group_ids`` from
      ``group_ids.all_implied_ids`` (``O19 res_users.py:258-259, 447-449``).
      It is **not** stored — a non-stored compute is still readable over
      ``read``, which is all this helper needs — so reading that field
      reproduces v19's transitive answer.

    ``all_group_ids`` exists only on v19, so ``field_exists`` selects the
    right relation without any ``ctx.env.version`` test, and the helper works
    for an ARBITRARY user on both targets (v19's ``has_group`` additionally
    refuses to answer about another user unless the caller is internal —
    ``O19 :1075-1078`` — which this read sidesteps entirely).
    """
    group_id = rpc.ref(group_xmlid)
    if not group_id:
        return False
    field = ("all_group_ids" if rpc.field_exists("res.users", "all_group_ids")
             else user_groups_field(rpc))
    return group_id in (rpc_read_one(rpc, "res.users", user_id,
                                     [field]).get(field) or [])


def rpc_read_one(rpc: OdooRPC, model: str, res_id: int, fields_: list) -> dict:
    rows = rpc.read(model, [res_id], fields_)
    return rows[0] if rows else {}


# --------------------------------------------------------------------------
# Master-data fixtures
# --------------------------------------------------------------------------
def ensure_partner(ctx, label="Customer Alpha") -> int:
    rpc = ctx.adapter.rpc
    name = tag(label)
    found = rpc.search("res.partner", [("name", "=", name)], limit=1)
    if found:
        return found[0]
    return rpc.create("res.partner", {
        "name": name,
        "street": tag("Street"),
        "city": "Austin",
        "zip": "78701",
    })


def ensure_product(ctx, label="Widget", price=100.0, cost=60.0,
                   weight=2.0, categ_id=None) -> int:
    """A storable product under the token.

    ``weight`` is non-zero on purpose: TC157 step 6 needs the core weight
    compute's "would-be" figure to differ from the operator-entered 14.6.
    The storable shape comes from the adapter (v17 ``type='product'``, v19
    ``type='consu'`` + ``is_storable``).
    """
    rpc = ctx.adapter.rpc
    name = tag(label)
    found = rpc.search_read("product.product", [("name", "=", name)],
                            ["id"], limit=1)
    if found:
        return found[0]["id"]
    values = {"name": name, "default_code": f"{_TOKEN}-{label}",
              "list_price": price, "standard_price": cost, "weight": weight,
              "sale_ok": True, "purchase_ok": True, "taxes_id": [(6, 0, [])]}
    values.update(ctx.adapter.storable_product_values())
    if categ_id:
        values["categ_id"] = categ_id
    tmpl_id = rpc.create("product.template", with_categ(rpc, values))
    variant = rpc.search_read("product.product",
                              [("product_tmpl_id", "=", tmpl_id)], ["id"],
                              limit=1)
    return variant[0]["id"]


def ensure_service_product(ctx, label="Delivery Fee") -> int:
    rpc = ctx.adapter.rpc
    name = tag(label)
    found = rpc.search_read("product.product", [("name", "=", name)],
                            ["id"], limit=1)
    if found:
        return found[0]["id"]
    tmpl_id = rpc.create("product.template", with_categ(rpc, {
        "name": name, "default_code": f"{_TOKEN}-{label}", "type": "service",
        "list_price": 0.0, "taxes_id": [(6, 0, [])]}))
    variant = rpc.search_read("product.product",
                              [("product_tmpl_id", "=", tmpl_id)], ["id"],
                              limit=1)
    return variant[0]["id"]


def ensure_carrier(ctx, label="Carrier") -> int:
    """A ``delivery.carrier`` for the shipping-label fixtures.

    ``shipping.label.carrier_id`` is ``required=True``
    (printnode_base/models/shipping_label.py:16-21), so TC156 and TC165
    cannot create a label without one. ``delivery.carrier`` itself requires
    ``name`` and ``product_id`` (delivery/models/delivery_carrier.py:36,50).
    Nothing here rates, buys or tracks anything — the carrier record is
    inert master data (convention rule 4).
    """
    rpc = ctx.adapter.rpc
    name = tag(label)
    found = rpc.search("delivery.carrier", [("name", "=", name),
                                            ("active", "in", [True, False])],
                       limit=1)
    if found:
        return found[0]
    return rpc.create("delivery.carrier", {
        "name": name,
        "product_id": ensure_service_product(ctx, f"{label} Fee"),
        "delivery_type": "fixed",
        "fixed_price": 0.0,
    })


def ensure_analytic_account(ctx, plan_xmlid: str, label: str) -> int | None:
    rpc = ctx.adapter.rpc
    plan_id = rpc.ref(plan_xmlid)
    if not plan_id:
        ctx.log(f"[warn] analytic plan {plan_xmlid} does not resolve")
        return None
    name = tag(label)
    found = rpc.search("account.analytic.account",
                       [("name", "=", name), ("plan_id", "=", plan_id)],
                       limit=1)
    if found:
        return found[0]
    return rpc.create("account.analytic.account",
                      {"name": name, "plan_id": plan_id})


def analytic_distribution_for(ctx, order_type: str):
    """The distribution ``dto_account``'s confirmation gate demands.

    ``dto_account/models/sale_order.py:11-17`` dispatches to
    ``_validate_analytic_distribution_<order_type>``:

    * ``project``     — every line needs an account on
      ``dto_account.project_analytic_plan`` or it raises ``Project is required``
      (:19-29);
    * ``buy``         — ditto on ``dto_account.customer_contract_analytic_plan``,
      raising ``Customer Contract is required`` (:31-41);
    * ``inventory`` / ``cost_center`` — a distribution is REFUSED
      (``Analytic Distribution should not be set for this order type``,
      :43-51), so this returns ``None``.

    Returns ``{str(account_id): 100.0}`` or ``None``. When dto_account is not
    installed the gate does not exist and ``None`` is correct too.
    """
    plan_xmlid = ORDER_TYPE_ANALYTIC_PLAN.get(order_type)
    if not plan_xmlid:
        return None
    account_id = ensure_analytic_account(ctx, plan_xmlid,
                                         f"Analytic {order_type}")
    return {str(account_id): 100.0} if account_id else None


# --------------------------------------------------------------------------
# Sales orders and deliveries
# --------------------------------------------------------------------------
def make_sale_order(ctx, order_type=ISOLATED_ORDER_TYPE, product_id=None,
                    qty=10.0, price=100.0, partner_id=None, label="Order",
                    ship_blind=False, memo=None, stock_qty=100.0):
    """A confirmable DataOne sales order for this suite.

    Defaults to ``order_type='buy'`` on purpose: F040 auto-invoices and posts
    ``project`` / ``inventory`` / ``cost_center`` orders inside
    ``_action_done`` (dto_sale_stock/models/stock_picking.py:16-22), which
    would couple a delivery assertion to the whole COGS design (WF-012 /
    WF-013's subject). ``buy`` is the one type F040 excludes, which is
    exactly the isolation TC159's Notes demand.

    Carries everything the three confirmation gates need, and a NON-EMPTY
    ``memo_to_suppliers`` — without which the F041 server action's
    ``'IRM' in order.memo_to_suppliers`` raises ``TypeError`` inside the
    validation transaction and aborts the delivery
    (dto_sale_stock/data/base_automation_data.xml:59).
    """
    rpc = ctx.adapter.rpc
    partner_id = partner_id or ensure_partner(ctx)
    product_id = product_id or ensure_product(ctx)
    if stock_qty:
        set_stock(ctx, product_id, stock_qty)

    line = {"product_id": product_id, "product_uom_qty": qty,
            "price_unit": price}
    if rpc.field_exists("sale.order.line", "requested_delivery_date"):
        # dto_sale/models/sale_order.py:59-62 refuses to confirm without it
        line["requested_delivery_date"] = "2099-12-31"
    distribution = analytic_distribution_for(ctx, order_type)
    if distribution:
        line["analytic_distribution"] = distribution

    values = {"partner_id": partner_id, "origin": tag(label),
              "order_line": [(0, 0, line)]}
    if rpc.field_exists("sale.order", "order_type"):
        values["order_type"] = order_type
    if rpc.field_exists("sale.order", "requester_email"):
        values["requester_email"] = "qa.wf011@example.invalid"
    if rpc.field_exists("sale.order", "memo_to_suppliers"):
        values["memo_to_suppliers"] = memo or f"{MARKER} QA memo"
    if ship_blind and rpc.field_exists("sale.order", "ship_blind"):
        values["ship_blind"] = True
    return rpc.create("sale.order", values)


def confirm_order(ctx, order_id: int):
    """Confirm a fixture order, mail-safe.

    ``require_mail_offline`` runs first because confirmation fires dto_sale's
    own automation and its hard-coded d1systems.com recipient list
    (convention rule 4).
    """
    require_mail_offline(ctx)
    rpc = ctx.adapter.rpc
    rpc.call("sale.order", "action_confirm", [order_id])
    state = rpc.read("sale.order", [order_id], ["state"])[0]["state"]
    if state != "sale":
        ctx.blocked(
            f"The fixture sale order did not confirm (state={state!r}). "
            "dto_account/models/sale_order.py:11 validates the analytic "
            "distribution per order_type, dto_sale:59 requires a Promised "
            "Ship Date on every line and dto_sale_workday:24 a Requester "
            "Email — one of those gates refused, so there is no delivery to "
            "assert against.")
    return state


def outgoing_pickings(rpc, order_id: int) -> list[dict]:
    """The order's outgoing pickings, newest last, with the fields every
    WF-011 case reads."""
    if not rpc.field_exists("stock.picking", "sale_id"):
        return []
    rows = rpc.search_read(
        "stock.picking", [("sale_id", "=", order_id)],
        ["name", "state", "picking_type_id", "picking_type_code",
         "backorder_id", "date_done", "origin"], order="id")
    return [r for r in rows if r.get("picking_type_code") == "outgoing"]


def picking_type_out_id(rpc) -> int | None:
    """The one operation type F179 protects."""
    return rpc.ref(PICKING_TYPE_OUT_XMLID)


def picking_type_for(rpc, code: str) -> int:
    """Any picking type with this code — used for the receipt and internal
    transfer TC155 compares against."""
    if code == "outgoing":
        found = picking_type_out_id(rpc)
        if found:
            return found
    rows = rpc.search_read("stock.picking.type", [("code", "=", code)],
                           ["id"], limit=1, order="id")
    if not rows:
        raise OdooRPCError(f"no stock.picking.type with code={code!r}")
    return rows[0]["id"]


def _picking_type_locations(rpc, picking_type_id: int) -> tuple:
    row = rpc.read("stock.picking.type", [picking_type_id],
                   ["default_location_src_id", "default_location_dest_id",
                    "code"])[0]
    src = m2o_id(row["default_location_src_id"])
    dest = m2o_id(row["default_location_dest_id"])
    if not src:
        src = (stock_location(rpc) if row["code"] != "incoming"
               else _supplier_location(rpc))
    if not dest:
        dest = (_customer_location(rpc) if row["code"] == "outgoing"
                else stock_location(rpc))
    return src, dest


def _location_by_usage(rpc, usage: str) -> int | None:
    rows = rpc.search_read("stock.location", [("usage", "=", usage)],
                           ["id"], limit=1, order="id")
    return rows[0]["id"] if rows else None


def _customer_location(rpc) -> int | None:
    return rpc.ref("stock.stock_location_customers") or _location_by_usage(
        rpc, "customer")


def _supplier_location(rpc) -> int | None:
    return rpc.ref("stock.stock_location_suppliers") or _location_by_usage(
        rpc, "supplier")


def move_values(rpc, product_id: int, qty: float, src: int, dest: int,
                label="move") -> dict:
    """One ``stock.move`` create payload, version-safe.

    ``stock.move.name`` is ``required=True`` on v17
    (stock/models/stock_move.py:30) and does not exist at all on v19, where
    ``_rec_name`` is ``reference`` (:22). Setting it conditionally is what
    keeps one fixture builder working on both.
    """
    uom_id = m2o_id(rpc.read("product.product", [product_id],
                             ["uom_id"])[0]["uom_id"])
    values = {"product_id": product_id, "product_uom": uom_id,
              "product_uom_qty": qty, "location_id": src,
              "location_dest_id": dest}
    if rpc.field_exists("stock.move", "name"):
        values["name"] = tag(label)
    return values


def make_picking(ctx, code="outgoing", product_id=None, qty=10.0,
                 partner_id=None, label="Transfer", assign=True,
                 stock_qty=100.0) -> int:
    """A standalone transfer of the given operation code, ready to work on.

    Used by the cases that are about the picking itself rather than about an
    order (TC151-TC155, TC157, TC160). Outgoing transfers are created on
    ``stock.picking_type_out`` exactly, because F179's guard compares against
    that single id.
    """
    rpc = ctx.adapter.rpc
    product_id = product_id or ensure_product(ctx)
    picking_type_id = picking_type_for(rpc, code)
    src, dest = _picking_type_locations(rpc, picking_type_id)
    if stock_qty and code in ("outgoing", "internal"):
        set_stock(ctx, product_id, stock_qty, location_id=src)
    values = {"picking_type_id": picking_type_id, "location_id": src,
              "location_dest_id": dest, "origin": tag(label),
              "move_ids": [(0, 0, move_values(rpc, product_id, qty, src, dest,
                                              label))]}
    if partner_id:
        values["partner_id"] = partner_id
    picking_id = rpc.create("stock.picking", values)
    rpc.call("stock.picking", "action_confirm", [picking_id])
    if assign:
        _safe(rpc.call, "stock.picking", "action_assign", [picking_id])
    return picking_id


def picking_row(rpc, picking_id: int, fields_=None) -> dict:
    fields_ = fields_ or ["name", "state", "date_done", "picking_type_id",
                          "picking_type_code", "backorder_id", "sale_id",
                          "weight", "shipping_weight", "box_count",
                          "default_box_weight", "origin", "note"]
    available = rpc.call("stock.picking", "fields_get", fields_,
                         attributes=["type"])
    return rpc.read("stock.picking", [picking_id],
                    [f for f in fields_ if f in available])[0]


def moves_of(rpc, picking_id: int) -> list[dict]:
    return rpc.search_read("stock.move", [("picking_id", "=", picking_id)],
                           ["product_id", "product_uom_qty", "quantity",
                            "state", "picked"], order="id")


def move_lines_of(rpc, picking_id: int) -> list[dict]:
    return rpc.search_read("stock.move.line",
                           [("picking_id", "=", picking_id)],
                           ["product_id", "quantity", "state", "lot_name"],
                           order="id")


def validate_delivery(ctx, picking_id: int, qty=None):
    """Validate a picking, mail-safe, and return what ``button_validate`` gave.

    ``qty=None`` completes every move; a number short-picks the single move
    and the return value is then core's backorder-confirmation action dict
    (stock/models/stock_picking.py:1149-1151 ->
    ``_action_generate_backorder_wizard`` :1230-1241), which is fully
    observable over RPC — that dict IS TC161 steps 4-6.

    ``require_mail_offline`` first: reaching ``done`` on a picking with a
    ``sale_id`` fires dto_sale_stock's shipment automation, which calls
    ``send_mail(force_send=True)`` (convention rule 4).
    """
    require_mail_offline(ctx)
    rpc = ctx.adapter.rpc
    if qty is None:
        return validate_picking(ctx, picking_id, full=True)
    moves = moves_of(rpc, picking_id)
    if len(moves) != 1:
        ctx.blocked(
            f"The short-validation fixture expects exactly one stock.move on "
            f"picking {picking_id}, found {len(moves)} — core merges moves "
            "that share a product and the same locations, so the fixture "
            "must be rebuilt before the backorder assertions mean anything.")
    rpc.write("stock.move", [moves[0]["id"]], {"quantity": qty,
                                               "picked": True})
    result = rpc.call("stock.picking", "button_validate", [picking_id])
    ctx.log(f"button_validate({picking_id}) -> {result!r}")
    return result


def backorder_wizard(ctx, picking_id: int) -> int:
    """Build the wizard the backorder dialog is bound to.

    ``default_get`` fills ``backorder_confirmation_line_ids`` from
    ``pick_ids`` only when it is invoked (stock/wizard/
    stock_backorder_confirmation.py:29-38); an RPC ``create`` with explicit
    values does not call it, so both are written here explicitly. That
    reproduces the dialog's own state rather than relying on a default.
    """
    rpc = ctx.adapter.rpc
    return rpc.create(BACKORDER_MODEL, {
        "pick_ids": [(6, 0, [picking_id])],
        "backorder_confirmation_line_ids": [
            (0, 0, {"picking_id": picking_id, "to_backorder": True})],
    })


def process_backorder(ctx, picking_id: int, wizard_id: int | None = None):
    """Press "Create Backorder" — ``process()``, public, v17 :52 / v19 :49."""
    rpc = ctx.adapter.rpc
    wizard_id = wizard_id or backorder_wizard(ctx, picking_id)
    return rpc.call(BACKORDER_MODEL, BACKORDER_PROCESS_BUTTON, [wizard_id],
                    context={BACKORDER_CONTEXT_KEY: [picking_id]})


def cancel_backorder(ctx, picking_id: int, wizard_id: int | None = None):
    """Call ``process_cancel_backorder`` — the button F042 only HIDES.

    It is public on both versions (v17 :70, v19 :67), so RPC reaches it.
    That is BR-1's documented limit and TC161 step 12's whole point; run it
    against its own fixture, never against the picking steps 7-11 used.
    """
    rpc = ctx.adapter.rpc
    wizard_id = wizard_id or backorder_wizard(ctx, picking_id)
    return rpc.call(BACKORDER_MODEL, BACKORDER_CANCEL_BUTTON, [wizard_id],
                    context={BACKORDER_CONTEXT_KEY: [picking_id]})


def backorders_of(rpc, picking_id: int) -> list[dict]:
    """Pickings created as a backorder of this one
    (stock/models/stock_picking.py:404-408)."""
    return rpc.search_read("stock.picking",
                           [("backorder_id", "=", picking_id)],
                           ["name", "state", "picking_type_code"], order="id")


def scrap_from_picking(ctx, picking_id: int, product_id: int,
                       qty=1.0) -> int | None:
    """A ``stock.scrap`` linked to a picking — TC168 needs at least one.

    ``stock.scrap.picking_id`` is core (stock/models/stock_scrap.py:38) and
    the link is what makes ``_compute_account_move_ids``'s scrap branch run
    (dto_stock/models/stock_picking.py:26).
    """
    rpc = ctx.adapter.rpc
    if not rpc.model_exists("stock.scrap"):
        return None
    src = m2o_id(picking_row(rpc, picking_id,
                             ["location_id"]).get("location_id"))
    values = {"product_id": product_id, "scrap_qty": qty,
              "picking_id": picking_id, "origin": tag("Scrap")}
    if src:
        values["location_id"] = src
    uom_id = m2o_id(rpc.read("product.product", [product_id],
                             ["uom_id"])[0]["uom_id"])
    for uom_field in ("product_uom_id", "product_uom"):
        if rpc.field_exists("stock.scrap", uom_field):
            values[uom_field] = uom_id
            break
    return rpc.create("stock.scrap", values)


# --------------------------------------------------------------------------
# Boxes and shipping labels
# --------------------------------------------------------------------------
def create_boxes(ctx, picking_id: int, count: int, default_weight: float):
    """Set the two inputs and press Create Boxes.

    ``action_create_boxes`` returns ``True`` — never an action dict
    (dto_stock/models/stock_picking.py:47) — which is how TC152 asserts "no
    confirmation dialog was presented".
    """
    rpc = ctx.adapter.rpc
    rpc.write("stock.picking", [picking_id],
              {"box_count": count, "default_box_weight": default_weight})
    return rpc.call("stock.picking", CREATE_BOXES_METHOD, [picking_id])


def boxes_of(rpc, picking_id: int) -> list[dict]:
    """The manifest, read back in ``_order = 'sequence, id'`` order
    (stock_picking_box.py:11)."""
    return rpc.search_read(BOX_MODEL, [("picking_id", "=", picking_id)],
                           ["name", "weight", "sequence"],
                           order="sequence, id")


def make_shipping_label(ctx, picking_id: int, carrier_id: int,
                        tracking: str, pieces: float) -> int:
    """One hand-created ``shipping.label`` row — the F078 behaviour.

    PrintNode's own views forbid this (``create="false" edit="false"`` on
    ``printnode_base.shipping_label_tree``); dto_stock re-declares the fields
    ``readonly=False`` and pins an editable list on the picking form.
    """
    rpc = ctx.adapter.rpc
    return rpc.create(SHIPPING_LABEL_MODEL, {
        "picking_id": picking_id, "carrier_id": carrier_id,
        "tracking_numbers": tracking, "pieces": pieces})


def shipping_labels_of(rpc, picking_id: int) -> list[dict]:
    return rpc.search_read(SHIPPING_LABEL_MODEL,
                           [("picking_id", "=", picking_id)],
                           ["carrier_id", "tracking_numbers", "pieces",
                            "label_status"], order="id")


# --------------------------------------------------------------------------
# View arch helpers
# --------------------------------------------------------------------------
class Arch:
    """A parsed view arch with the parent lookups ElementTree lacks.

    ``get_view`` returns the fully combined arch INCLUDING inline x2many
    sub-views, which is what makes the boxes kanban template and the
    shipping-label list attributes assertable without a browser.
    ElementTree implements no ancestor axis, so the parent map is built once
    here and ``enclosing_attr`` walks it.
    """

    def __init__(self, xml_string: str):
        import xml.etree.ElementTree as ET
        self.text = xml_string
        self.root = ET.fromstring(xml_string)
        self._parents = {child: parent
                         for parent in self.root.iter()
                         for child in parent}

    def find(self, path: str):
        return self.root.find(path)

    def findall(self, path: str) -> list:
        return self.root.findall(path)

    def parent(self, element):
        return self._parents.get(element)

    def ancestors(self, element) -> list:
        chain, node = [], self._parents.get(element)
        while node is not None:
            chain.append(node)
            node = self._parents.get(node)
        return chain

    def enclosing_attr(self, element, attribute: str):
        """The nearest ancestor's value for ``attribute``, or None.

        TC151/TC155 use it for the ``invisible="picking_type_code !=
        'outgoing'"`` div that encloses the whole Boxes section
        (dto_stock/views/stock_picking_views.xml:32).
        """
        for node in self.ancestors(element):
            if attribute in node.attrib:
                return node.attrib[attribute]
        return None

    def attrs_of(self, path: str) -> dict:
        element = self.find(path)
        return dict(element.attrib) if element is not None else {}


def picking_form_arch(ctx) -> Arch:
    """The combined ``stock.picking`` form arch."""
    return Arch(form_arch(ctx, "stock.picking", "form"))


def arch_of_model(ctx, model: str, view_type="form") -> Arch:
    return Arch(form_arch(ctx, model, view_type))


def arch_of_xmlid(ctx, xmlid: str, view_type="form") -> Arch:
    """The arch of ONE named view — for ``dto_stock.shipping_label_tree_on_
    picking`` and ``stock.view_backorder_confirmation``.

    The list view type is ``tree`` on v17 and ``list`` on v19, so it is
    resolved through the adapter rather than hardcoded.
    """
    rpc = ctx.adapter.rpc
    view_id = rpc.ref(xmlid)
    if not view_id:
        ctx.blocked(f"The view {xmlid} does not resolve on {ctx.env.key} "
                    f"(db={ctx.env.db}), so its arch cannot be asserted.")
    if view_type in ("tree", "list"):
        view_type = getattr(ctx.adapter, "list_view_type", view_type)
    model = rpc.read("ir.ui.view", [view_id], ["model"])[0]["model"]
    return Arch(rpc.call(model, "get_view", view_id, view_type)["arch"])


def kanban_card_template(ctx) -> str:
    """``kanban-box`` on v17, ``card`` on v19.

    The ONE place this suite reads ``ctx.env.version``, under the convention's
    stated exception: TC151 step 13's subject IS the version delta. v17's
    ``dto_stock.view_picking_form_boxes`` declares ``<t t-name="kanban-box">``
    (views/stock_picking_views.xml:50) and the ported v19 file declares
    ``<t t-name="card">`` (:67); the parser that changed is
    ``web/static/src/views/kanban/kanban_arch_parser.js:8``. Nothing about how
    the test RUNS changes — only what it expects. When ``adapters/`` is in a
    later wave's write scope this pair belongs there and in the conventions
    table.
    """
    return "card" if ctx.env.version == "19" else "kanban-box"


# --------------------------------------------------------------------------
# Report rendering over HTTP
# --------------------------------------------------------------------------
def report_url(ctx, converter: str, report_name: str, res_ids) -> str:
    ids = ",".join(str(i) for i in res_ids)
    return f"{ctx.env.base_url}/report/{converter}/{report_name}/{ids}"


def render_report(ctx, report_name: str, res_ids, converter="pdf"):
    """GET ``/report/<converter>/<report_name>/<ids>``. Returns (status, body).

    ``converter='pdf'`` is the ONLY route that reaches F044's override:
    ``addons/web/controllers/report.py:41-44`` passes the report_name STRING
    into ``_render_qweb_pdf``, which is the private method dto_sale_stock
    inherits. ``converter='html'`` goes to ``_render_qweb_html`` (:39), which
    F044 does not override — never substitute it in a case about the
    expansion.
    """
    opener = http_session(ctx.env)
    url = report_url(ctx, converter, report_name, res_ids)
    ctx.log(f"GET {url}")
    try:
        with opener.open(url, timeout=600) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:              # 4xx/5xx carry a body
        return exc.code, exc.read()


def report_html(ctx, report_name: str, res_ids) -> str:
    status, body = render_report(ctx, report_name, res_ids, converter="html")
    if status != 200:
        ctx.blocked(
            f"GET /report/html/{report_name} returned HTTP {status} on "
            f"{ctx.env.key}. The template did not render, so nothing about "
            "its content can be asserted.")
    return body.decode("utf-8", "replace")


def report_pdf(ctx, report_name: str, res_ids) -> bytes:
    status, body = render_report(ctx, report_name, res_ids, converter="pdf")
    if status != 200 or not body.startswith(b"%PDF"):
        ctx.blocked(
            f"GET /report/pdf/{report_name} returned HTTP {status} and "
            f"{len(body)} bytes that are not a PDF on {ctx.env.key}. "
            "wkhtmltopdf must be installed and reachable (dto.conf sets "
            "bin_path); without a real PDF the expansion F044 performs "
            "cannot be observed at all, because _render_qweb_pdf is private "
            "and this route is its only public entry point.")
    return body


def save_report_artifact(ctx, name: str, data: bytes, suffix: str):
    path = ctx.artifacts_dir / f"{name}{suffix}"
    path.write_bytes(data)
    ctx.add_artifact(path, "log", f"{name}{suffix}")
    return path


_PDF_PAGE_RE = re.compile(rb"/Type\s*/Page(?![s])")
_PDF_STREAM_RE = re.compile(rb"stream\r?\n(.*?)endstream", re.DOTALL)
_PDF_LITERAL_RE = re.compile(rb"\((?:\\.|[^()\\])*\)", re.DOTALL)


def pdf_page_count(data: bytes) -> int | None:
    """Count ``/Type /Page`` objects, or None when they are not greppable.

    Font-independent, so it survives wkhtmltopdf's glyph subsetting. It does
    NOT survive cross-reference/object streams, in which case the page
    dictionaries are compressed and this returns None — the caller must then
    report BLOCKED rather than guess. [UNVERIFIED on this build until a real
    render is inspected.]
    """
    count = len(_PDF_PAGE_RE.findall(data))
    return count or None


def pdf_text(data: bytes) -> str | None:
    """Best-effort text extraction with the standard library only.

    No pypdf / PyPDF2 / pdfminer is installed in the qa-platform venv and
    ``requirements.txt`` declares none, so the FlateDecode streams are
    inflated with ``zlib`` and the parenthesised string operands collected.
    wkhtmltopdf subsets fonts and may emit hex-encoded glyph indices instead
    of ASCII, in which case this returns None and the caller must report
    BLOCKED naming the missing extractor — it must never silently assert
    against an empty string. [UNVERIFIED on this build.]
    """
    chunks = []
    for raw in _PDF_STREAM_RE.findall(data):
        try:
            chunks.append(zlib.decompress(raw))
        except zlib.error:
            continue
    if not chunks:
        return None
    out = []
    for chunk in chunks:
        for literal in _PDF_LITERAL_RE.findall(chunk):
            text = literal[1:-1]
            text = re.sub(rb"\\([()\\])", rb"\1", text)
            out.append(text.decode("latin-1", "replace"))
    text = "".join(out)
    return text if re.search(r"[A-Za-z]{3}", text) else None


# --------------------------------------------------------------------------
# HTML helpers for the rendered report body
# --------------------------------------------------------------------------
_TAG_RE = re.compile(r"<[^>]+>")
_DROP_RE = re.compile(r"<(script|style)\b.*?</\1>", re.IGNORECASE | re.DOTALL)


def html_text(fragment: str) -> str:
    """Visible text of an HTML fragment, entities resolved, whitespace
    collapsed. Used for the positive content assertions (TC165)."""
    body = _DROP_RE.sub(" ", fragment)
    body = _TAG_RE.sub(" ", body)
    return re.sub(r"\s+", " ", _html.unescape(body)).strip()


def html_elements(fragment: str, tag_name: str, attribute: str | None = None,
                  value: str | None = None) -> list[str]:
    """Outer HTML of every ``<tag_name>`` element, optionally filtered on an
    attribute value. Balanced scan, so nested tables are returned whole."""
    results = []
    open_re = re.compile(rf"<{tag_name}\b[^>]*>", re.IGNORECASE)
    token_re = re.compile(rf"<(/?){tag_name}\b[^>]*?(/?)>", re.IGNORECASE)
    for match in open_re.finditer(fragment):
        if match.group(0).rstrip().endswith("/>"):
            outer = match.group(0)
        else:
            depth, end = 0, None
            for token in token_re.finditer(fragment, match.start()):
                if token.group(2) == "/":
                    continue
                depth += -1 if token.group(1) == "/" else 1
                if depth == 0:
                    end = token.end()
                    break
            if end is None:
                continue
            outer = fragment[match.start():end]
        if attribute is not None:
            found = re.search(rf'{attribute}\s*=\s*"([^"]*)"', match.group(0))
            if not found or (value is not None and found.group(1) != value):
                continue
        results.append(outer)
    return results


def html_element(fragment: str, tag_name: str, attribute: str | None = None,
                 value: str | None = None) -> str | None:
    found = html_elements(fragment, tag_name, attribute, value)
    return found[0] if found else None


def count_tags(fragment: str, tag_name: str) -> int:
    """Opening tags of one name inside a fragment (``<td>`` cells, ``<tr>``
    rows). Self-closing tags count once, which is what the boxes grid's
    padding cells (report_delivery_document.xml:46) need."""
    return len(re.findall(rf"<{tag_name}\b", fragment, re.IGNORECASE))


def occurrences(text: str, needle: str) -> int:
    return text.count(needle)


# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------
def error_text(exc) -> str:
    """The server's own message, without the transport prefix.

    ``adapters/base.py`` formats a fault as ``"<model>.<method> failed: <last
    line>"``; this strips the prefix so a case can assert the module's string
    byte-for-byte instead of matching a substring.
    """
    text = str(exc)
    marker = " failed: "
    return text.split(marker, 1)[1].strip() if marker in text else text.strip()


def expect_error(callable_, *args, **kwargs) -> tuple[bool, str]:
    """Run something that should raise. Returns ``(raised, message)``.

    Never let a bare ``AssertionError`` out of a test: the caller feeds the
    result to ``ctx.check`` so the platform records expected vs actual.
    """
    try:
        callable_(*args, **kwargs)
        return False, "no error raised"
    except OdooRPCError as exc:
        return True, error_text(exc)


# --------------------------------------------------------------------------
# Read-only captures (TC054 / TC011)
# --------------------------------------------------------------------------
def xmlid_map(rpc, model: str, res_ids) -> dict:
    """{res_id: 'module.name'} for records that have an external id."""
    if not res_ids:
        return {}
    rows = rpc.search_read("ir.model.data",
                           [("model", "=", model), ("res_id", "in", list(res_ids))],
                           ["module", "name", "res_id"])
    return {r["res_id"]: f"{r['module']}.{r['name']}" for r in rows}


def _count(rpc, model: str, domain) -> int:
    return rpc.call(model, "search_count", domain)


def rma_capture(ctx) -> dict:
    """TC054's read-only snapshot, through the ORM.

    The workbook writes this case as five SQL statements. Two of them cannot
    run as written and the reason is structural, so both are adapted here and
    the adaptation is recorded in the plan doc rather than hidden:

    * ``count(*) FILTER (WHERE ship_blind IS TRUE) FROM stock_picking`` —
      ``stock.picking.ship_blind`` is a non-stored RELATED field
      (dto_sale_stock/models/stock_picking.py:10), so no such column exists
      on either version. It is read through ``sale_id.ship_blind``, which IS
      stored, and the order-level count is captured alongside it.
    * ``packing_slip_attachment IS NOT NULL`` — that field is
      ``fields.Binary`` with the default ``attachment=True``
      (dto_purchase_stock/models/stock_picking.py:14-16;
      ``odoo/fields.py:2334-2348`` gives ``column_type = None`` for an
      attachment-backed Binary), so it has no column either. It is counted
      through ``ir.attachment`` on ``res_field``.

    Everything here is read-only and measures the live database, which is the
    point of a reconciliation case.
    """
    rpc = ctx.adapter.rpc
    data: dict = {}
    picking_fields = rpc.call("stock.picking", "fields_get", [],
                              attributes=["type", "store", "related"])

    data["stock_picking.total"] = _count(rpc, "stock.picking", [])
    for field in RMA_FIELDS:
        present = field in picking_fields
        data[f"field_present.{field}"] = present
        data[f"count.{field}_set"] = (
            _count(rpc, "stock.picking", [(field, "!=", False)])
            if present else "FIELD ABSENT")

    for field in sorted(DTO_PICKING_FIELDS):
        data[f"field_present.{field}"] = field in picking_fields

    # ship_blind: related, not stored -> read through the order
    if "ship_blind" in rpc.call("sale.order", "fields_get", [],
                                attributes=["type"]):
        data["count.sale_order_ship_blind"] = _count(
            rpc, "sale.order", [("ship_blind", "=", True)])
        data["count.picking_of_blind_order"] = _count(
            rpc, "stock.picking", [("sale_id.ship_blind", "=", True)])
    else:
        data["count.sale_order_ship_blind"] = "FIELD ABSENT"
        data["count.picking_of_blind_order"] = "FIELD ABSENT"

    for field in ("carrier_tracking_ref", "shipping_weight"):
        data[f"count.{field}_set"] = (
            _count(rpc, "stock.picking", [(field, "!=", False)])
            if field in picking_fields else "FIELD ABSENT")

    data["count.packing_slip_attachment"] = _count(
        rpc, "ir.attachment",
        [("res_model", "=", "stock.picking"),
         ("res_field", "=", "packing_slip_attachment")])

    if "rma_number" in picking_fields and "note" in picking_fields:
        data["count.rma_with_note"] = _count(
            rpc, "stock.picking",
            [("rma_number", "!=", False), ("note", "!=", False)])

    # the reason-code taxonomy actually in use
    if "reason_for_return" in picking_fields:
        groups = rpc.read_group("stock.picking",
                                [("reason_for_return", "!=", False)],
                                ["reason_for_return"], ["reason_for_return"])
        for group in groups:
            key = group.get("reason_for_return")
            if isinstance(key, (list, tuple)):
                key = key[0]
            data[f"reason.{key}"] = group.get("reason_for_return_count",
                                              group.get("__count"))
        selection = rpc.call("stock.picking", "fields_get",
                             ["reason_for_return"],
                             attributes=["selection"])
        pairs = selection.get("reason_for_return", {}).get("selection") or []
        data["reason_selection"] = [tuple(p) for p in pairs]

    if rpc.field_exists("res.company", "vendor_refund_narration"):
        rows = rpc.search_read("res.company", [],
                               ["name", "vendor_refund_narration"], order="id")
        data["company.vendor_refund_narration_set"] = sorted(
            bool(r["vendor_refund_narration"]) for r in rows)
    else:
        data["company.vendor_refund_narration_set"] = "FIELD ABSENT"

    sequence = rpc.search_read("ir.sequence",
                               [("code", "=", RMA_SEQUENCE_CODE)],
                               ["name", "prefix", "padding"], limit=1)
    data["sequence.rma_number"] = bool(sequence)
    return data


def custom_reports_capture(ctx) -> list[dict]:
    """TC011 steps 1-3, through the ORM instead of psql.

    Everything the workbook's first three SQL statements ask for lives in
    ``ir.actions.report``, ``ir.model.data``, ``ir.ui.view`` (``type='qweb'``,
    ``key = report_name``) and ``report.paperformat`` — all ordinary,
    ORM-reachable data, so this case needs no ``pg_*`` credentials and cannot
    report BLOCKED for the lack of them.
    """
    rpc = ctx.adapter.rpc
    report_ids = rpc.search("ir.actions.report", [])
    owners = rpc.search_read("ir.model.data",
                             [("model", "=", "ir.actions.report"),
                              ("res_id", "in", report_ids)],
                             ["module", "name", "res_id"])
    by_id = {o["res_id"]: o for o in owners}
    rows = rpc.read("ir.actions.report", report_ids,
                    ["report_name", "report_type", "model", "paperformat_id",
                     "print_report_name"])
    out = []
    for row in rows:
        owner = by_id.get(row["id"])
        if not owner:
            continue
        module = owner["module"]
        if not (module in CUSTOM_REPORT_MODULES
                or module.startswith(("dto_", "novobi_"))):
            continue
        paperformat_id = m2o_id(row["paperformat_id"])
        template = rpc.search("ir.ui.view", [("type", "=", "qweb"),
                                             ("key", "=", row["report_name"])])
        out.append({
            "xml_id": f"{module}.{owner['name']}",
            "report_name": row["report_name"],
            "report_type": row["report_type"],
            "model": row["model"],
            "paperformat_id": paperformat_id,
            "paperformat_exists": bool(
                paperformat_id
                and rpc.search("report.paperformat",
                               [("id", "=", paperformat_id)])),
            "template_exists": bool(template),
            "print_report_name": row["print_report_name"],
        })
    return sorted(out, key=lambda r: r["xml_id"])


def default_paperformats(ctx) -> list[dict]:
    """Every ``report.paperformat`` flagged ``default=True``, with its owner.

    There is no ORM constraint enforcing a single default
    (``odoo/addons/base/models/report_paperformat.py:167-189``), and the v17
    baseline ships three custom claimants on top of core's own — which is
    why TC011 step 5 is EXPECTED TO FAIL there. The assertion stays as the
    workbook wrote it (rule 2); this helper only supplies the evidence.
    """
    rpc = ctx.adapter.rpc
    rows = rpc.search_read("report.paperformat", [("default", "=", True)],
                           ["name", "format", "page_width", "page_height",
                            "orientation"], order="id")
    names = xmlid_map(rpc, "report.paperformat", [r["id"] for r in rows])
    for row in rows:
        row["xml_id"] = names.get(row["id"], "(no xml_id)")
    return rows
