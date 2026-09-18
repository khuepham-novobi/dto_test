"""Shared fixtures and helpers for the DATAONE-WF-024 suite
(RMA: Customer and Vendor Returns).

Owning workflow: DATAONE-WF-024, build order 15.0 (workbook sheet) / Stage 4
in the registry, effective risk **CRITICAL**, fail mode "loud + silent",
estimate 16 h. Module under test: ``stock_picking_auto_create_lot`` — an
AGPL OCA fork with the whole DataOne RMA feature bolted into it.

Owns eight workbook cases: TC044, TC184, TC185, TC186, TC187, TC188, TC189,
TC190.

Everything below was read out of the real source before a line of it was
written (AUTOMATION_CONVENTIONS hard rule 6). File:line citations are the
evidence; nothing here is inferred.

The module under test
---------------------
``DTO-Odoo/3rd-addons/stock_picking_auto_create_lot/``

* ``__manifest__.py:7``  — ``"version": "19.0.1.0.0"``
* ``__manifest__.py:14`` — ``"depends": ["stock"]`` and **nothing else**,
  while the code reads ``res.company.vendor_refund_narration``
  (``dto_account``), ``sale.order.line.requested_delivery_date``
  (``dto_sale``) and ``stock.picking.sale_id`` (``sale_stock``). Three
  undeclared runtime dependencies; WF-024 E1 is the first of them.
* ``models/stock_picking.py:7``    — ``_inherit = "stock.picking"``
* ``models/stock_picking.py:9``    — ``rma_number = fields.Char(string="RMA Number")``
  (stored, **not** required, **not** readonly at model level, no tracking)
* ``models/stock_picking.py:11-33``— ``reason_for_return``, a 19-value
  Selection ``'901'``…``'919'``, **no default, not required**
* ``models/stock_picking.py:35``   — ``return_notes = fields.Text(...)``
* ``models/stock_picking.py:37-40``— ``do_print_picking()``: returns
  ``action_report_return.report_action(self)`` when ``rma_number`` is set,
  otherwise ``stock.action_report_picking``. It drops core's
  ``self.write({'printed': True})`` (v17 ``stock/models/stock_picking.py:913``,
  v19 ``:1176``) and core's "report has been deleted" ``UserError``
  (v17 ``:912``), and it has no ``ensure_one()``.
* ``models/stock_picking.py:42-44``— ``_get_rma_sequence()`` →
  ``ir.sequence.next_by_code("rma_number")``. **PRIVATE — unreachable over
  RPC.**
* ``models/stock_picking.py:46-60``— ``_set_auto_lot()`` (the upstream OCA
  half, F086), called from ``_action_done`` (``:62``) and
  ``button_validate`` (``:66``).
* ``data/rma_sequence.xml:3-13``   — ``<data noupdate="1">`` /
  ``sequence_rma_numbers``: name ``RMA Numbers``, code ``rma_number``,
  prefix ``%(year)s-``, padding ``3``, ``number_next`` 1,
  ``number_increment`` 1, ``company_id eval="False"`` (global). ``suffix``,
  ``use_date_range``, ``implementation`` and ``active`` are NOT set, so the
  model defaults apply (v17 ``odoo/addons/base/models/ir_sequence.py:134-155``,
  v19 ``:132-152``): ``suffix=False``, ``use_date_range=False``,
  ``implementation='standard'``, ``active=True``.
* ``views/stock_picking.xml:8-14`` — the form inherit: ``rma_number`` after
  ``//field[@name='partner_id']``; ``reason_for_return`` and
  ``return_notes`` after ``//field[@name='picking_type_id']``, both with
  ``invisible="rma_number == False"`` and ``required="True"`` (the literal
  string ``True``).
* ``views/stock_picking.xml:17-80``— ``view_picking_internal_search_inherit``:
  despite the name it carries **no** ``inherit_id`` — it is a standalone
  hand-copy of the core picking search, with two filters added at ``:31-32``.
* ``views/stock_picking.xml:81,102,123`` — the three ``ir.actions.act_window``
  records, all ``view_mode="tree,kanban,form,calendar,activity"``.
* ``views/stock_picking.xml:138-140``— **exactly ONE** ``menuitem``,
  ``rma_picking``, bound to ``action_picking_tree_rma``.
* ``report/stock_report_views.xml:4-13`` — ``action_report_return``.
* ``report/report_stockpicking_operations.xml:5-216`` — the forked template.
* ``wizard/stock_picking_return.py`` — the return-wizard overrides.
* ``wizard/stock_picking_return_views.xml:12-16`` — the second footer button.

Correction to the workbook, recorded here once
----------------------------------------------
Step 5 of the workflow and step 3 of TC188 say the RMA menu "exposes three
actions". It does not. ``views/stock_picking.xml`` defines **three
act_window records and one menuitem**; ``action_picking_tree_rma_customer``
and ``action_picking_tree_rma_vendor`` have no menu entry and no binding
anywhere in the module (grep of the whole module returns only their
definitions). TC188 therefore asserts one menu + three act_windows and
records the divergence — it is a finding about the product, not a softened
expectation.

The two places the fork is version-shaped
-----------------------------------------
Convention: "version-dependent behaviour goes through the adapter, never
``if version`` in a test body". ``adapters/`` is outside this suite's write
scope, so the pairs live here — resolved by **probing the target**, which is
stronger than a version switch because it measures the database actually
under test rather than the label on it:

===========================  ==================================  =========================================
Concern                      Odoo 17                             Odoo 19
===========================  ==================================  =========================================
Wizard public confirm        ``create_returns``                  ``action_create_returns``
                             (``stock/wizard/                    (``:210``); the DataOne xpath anchors on
                             stock_picking_return.py:183``)      it (``wizard/..._views.xml:12``)
Wizard private creator       ``_create_returns`` → **tuple**     ``_create_return`` → **recordset**
                             ``(picking_id, pick_type_id)``      (``:161``, ``:187``)
                             (``:129``, ``:181``)
Prefilled return quantity    delivered-minus-returned            **0** (``:131-137``)
                             (``:80-92``)
SO line UoM                  ``product_uom``                     ``product_uom_id``
                             (``sale/models/                     (``sale/models/sale_order_line.py:132``)
                             sale_order_line.py:120``)
``ir.ui.menu`` groups m2m    ``groups_id``                       ``group_ids``
                             (``base/models/ir_ui_menu.py:32``)  (``:29``)
``ir.actions.act_window``    ``groups_id``                       ``group_ids``
groups m2m                   (``base/models/ir_actions.py:291``) (``:329``)
``ir.actions.report``        ``groups_id``                       ``group_ids``
groups m2m                   (``base/models/                     (``:182``)
                             ir_actions_report.py:137``)
Package model                ``stock.quant.package``             ``stock.package``
                             (``stock/models/                    (``stock/models/stock_package.py:18``)
                             stock_quant.py:1456``)
===========================  ==================================  =========================================

What is NOT reachable over RPC (and what is asserted instead)
-------------------------------------------------------------
``_get_rma_sequence``, ``_create_return`` / ``_create_returns``,
``_create_returns_and_replenishments``, ``_set_auto_lot`` and
``ir.actions.report.get_paperformat()`` (returns a recordset) are all
private or unmarshallable. Every one of them is observed through a public
entry point instead:

* ``stock.picking.do_print_picking`` — public, returns a plain dict.
* ``stock.return.picking.create_returns`` / ``action_create_returns`` —
  public, returns a dict.
* ``stock.return.picking.create_returns_and_replenishments``
  (``wizard/stock_picking_return.py:69``) — **public**, returns a dict, so
  TC189 drives the real money leg rather than stubbing it.
* ``ir.sequence.get_next_char(number_next)`` (v17 ``:241``, v19 ``:240``) —
  public, returns a string, and writes **nothing**. It is how TC184 step 13
  proves the padding-3 overflow without touching the shared global
  sequence.
* ``ir.sequence.number_next_actual`` — computed from ``_predict_nextval``
  (v17 ``:100-110``, ``:64-84``). For ``implementation='standard'``,
  ``_next_do`` (v17 ``:202-207``) takes its value from the PostgreSQL
  sequence ``ir_sequence_%03d``, so **``number_next`` does not move** when a
  number is issued. TC044 step 5 and TC184 step 10 must read
  ``number_next_actual``.
* ``ir.ui.menu.load_menus(debug)`` (v17 ``:247``, v19 ``:236``) —
  ``@api.model``, returns a dict: the definitive per-user menu visibility.

Safety facts every fixture in this suite obeys
----------------------------------------------
1. **Validating a sale-linked delivery sends real email.**
   ``dto_sale_stock/data/base_automation_data.xml:4-11`` declares
   ``base_automation_send_email_on_sale_order_shipped``
   (``trigger='on_create_or_write'``, ``filter_pre_domain``
   ``[('state','!=','done')]``, ``filter_domain`` ``[('state','=','done')]``),
   whose server action calls ``template.send_mail(..., force_send=True, ...)``
   against hard-coded ``@d1systems.com`` addresses. Every fixture that
   validates a sale-linked delivery goes through
   ``framework.qa_fixtures.require_mail_offline`` (convention rule 4).
2. **Validating such a delivery can also POST an invoice.**
   ``dto_sale_stock/models/stock_picking.py:12-23`` — ``_action_done()``
   calls ``orders._create_invoices(final=True)`` then ``action_post()`` for
   ``order_type in ('project', 'inventory', 'cost_center')``. The sweep
   removes those invoices by ``invoice_origin``.
3. **Every fixture sale order needs three things or it cannot confirm**:
   ``order_type`` is ``required=True``
   (``dto_sale/models/sale_order.py:17-26``); every product line needs
   ``requested_delivery_date`` or ``_dto_gate_promised_ship_date``
   (``:90-94``) raises ``"Please enter 'Promised Ship Date' for all order
   lines."``; and the analytic gate
   (``dto_account/models/sale_order.py:42-52``) must be satisfied — which
   for ``order_type='inventory'`` means simply **no** analytic distribution
   on any line (``:107``).
4. **Creating a ``sale.order.line`` on a confirmed order spawns a picking.**
   ``sale_stock/models/sale_order_line.py:188-191`` calls
   ``_action_launch_stock_rule()`` from ``create``. TC189's replenishment
   line therefore produces a brand-new outgoing delivery that the sweep must
   remove.
5. **It also moves the order's commitment date.**
   ``dto_sale/models/sale_order.py:27-32`` redefines ``commitment_date`` as
   a stored compute ``@api.depends('order_line',
   'order_line.requested_delivery_date')`` (``:54-57``) returning
   ``max(requested_delivery_date)`` (``:101-110``). A real, undocumented
   side effect of Return-and-Replenish; recorded, not asserted away.
6. **Never create a second ``rma_number`` sequence.**
   ``next_by_code`` searches ``[('code','=',code), ('company_id','in',
   [company.id, False])] order='company_id'`` (v17 ``:279-292``). PostgreSQL
   sorts NULLs last, so a company-scoped duplicate would sort FIRST and
   hijack every RMA number on the target. Scratch sequences in this suite
   always use a token-scoped code, never ``rma_number``.

Verbatim error strings (read from the source, never paraphrased)
----------------------------------------------------------------
* ``"Please specify at least one non-zero quantity."`` — core wizard,
  identical in both (v17 ``:177``, v19 ``:183``).
* ``"You may only return Done pickings."`` — v17 ``:52``, v19 ``:114``.
* ``"You may only return one picking at a time."`` — v17 ``:30``, v19 ``:95``.
* ``"No products to return (only lines in Done state and not fully returned
  yet can be returned)."`` — v17 ``:68``, v19 ``:128``.
* ``"You have manually created product lines, please delete them to
  proceed."`` — v17 ``:144`` **only**; the line is gone in v19.
* ``"Please enter 'Promised Ship Date' for all order lines."`` —
  ``dto_sale/models/sale_order.py:94``.
* ``"Analytic Distribution should not be set for this order type"`` —
  ``dto_account/models/sale_order.py:107,112``.
"""
from __future__ import annotations

import copy
import json
import re
import urllib.request
import uuid
import xml.etree.ElementTree as ET

from adapters.base import OdooRPC, OdooRPCError
from framework.dto_fixtures import set_stock, validate_picking  # noqa: F401
from framework.fg_common import form_arch, m2o_id, make_trace  # noqa: F401
from framework.qa_fixtures import (require_mail_offline,  # noqa: F401
                                   sweep_model, sweep_products,
                                   user_groups_field, with_categ)

WORKFLOW = "DATAONE-WF-024"
WORKFLOW_NAME = "RMA: Customer and Vendor Returns"
MODULE = "stock_picking_auto_create_lot"

trace = make_trace(WORKFLOW)

MARKER = "WF024"
#: Per-execution fixture namespace. Every record this suite creates carries
#: it, and every search this suite makes is scoped by it, so live RMA data
#: can never leak into an assertion (convention rule 5).
_TOKEN = f"{MARKER}-{uuid.uuid4().hex[:8].upper()}"

#: Password for the disposable users TC187/TC188 impersonate.
QA_PASSWORD = "QaAuto-2026!"


def tag(name: str) -> str:
    """Namespace a fixture value for this execution."""
    return f"{_TOKEN} {name}"


def fixture_token() -> str:
    return _TOKEN


# =====================================================================
# Verbatim source constants
# =====================================================================

#: ``models/stock_picking.py:13-31``, byte for byte.
#:
#: ``902``'s label contains U+2013 EN DASH, not a hyphen — written as an
#: escape here so the value is correct whatever encoding reads this file.
#: Verified by codepoint against the source; the same 19 pairs appear
#: byte-identically in ``dto_purchase_stock/models/quality_check.py:8-26``
#: and ``dto_purchase_stock/wizard/quality_check_wizard.py:8-26``
#: (programmatically compared — all three parse to the same ordered list).
REASON_SELECTION = [
    ("901", "Vendor data entry error"),
    ("902", "Customer ordering error – provide details in notes"),
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
REASON_CODES = [key for key, _label in REASON_SELECTION]

#: The three models that each carry their own private copy of the taxonomy.
#: TC186 step 13 is the drift detector across them.
TAXONOMY_MODELS = ["stock.picking", "quality.check", "quality.check.wizard"]
TAXONOMY_FIELD = "reason_for_return"

# --- the sequence ----------------------------------------------------
RMA_SEQUENCE_CODE = "rma_number"
RMA_SEQUENCE_XMLID = f"{MODULE}.sequence_rma_numbers"

#: ``data/rma_sequence.xml:5-13`` plus the model defaults named in the module
#: docstring. These are the workbook anchors for TC044 step 1 and TC184
#: step 12.
RMA_SEQUENCE_ANCHORS = {
    "code": RMA_SEQUENCE_CODE,
    "name": "RMA Numbers",
    "prefix": "%(year)s-",
    "suffix": False,
    "padding": 3,
    "number_increment": 1,
    "implementation": "standard",
    "company_id": False,
    "use_date_range": False,
    "active": True,
}

#: TC184 step 7 / TC189 step 6 — the format the counterparty quotes.
RMA_NUMBER_PATTERN = r"^\d{4}-\d{3}$"
RMA_NUMBER_RE = re.compile(RMA_NUMBER_PATTERN)
#: TC044 step 8 — what padding 3 renders once the year passes 999.
RMA_OVERFLOW_PATTERN = r"^\d{4}-\d{4,}$"
RMA_OVERFLOW_RE = re.compile(RMA_OVERFLOW_PATTERN)
#: TC184 step 13 — the number whose rendering proves the overflow.
RMA_OVERFLOW_PROBE = 1000

# --- the views (FORM_/WIZARD_VIEW_XMLID: evidence only, unasserted) ---
FORM_VIEW_XMLID = f"{MODULE}.view_stock_picking_form_inherit"
SEARCH_VIEW_XMLID = f"{MODULE}.view_picking_internal_search_inherit"
WIZARD_VIEW_XMLID = f"{MODULE}.view_stock_return_picking_form_inherit_test"

#: ``views/stock_picking.xml:9,12,13`` — the arch modifiers exactly as
#: written. ``required`` is the literal string ``"True"``; the workbook's
#: v19 migration item 5 wants it normalised to ``"1"``, so TC186 accepts
#: either spelling and RECORDS which one the target carries. That is not a
#: weakening: both spellings mean the same modifier, and the point of the
#: step is that the requirement is view-level.
RMA_FIELD_MODIFIERS = {
    "rma_number": {"invisible": "rma_number == False", "readonly": "1"},
    "reason_for_return": {"invisible": "rma_number == False",
                          "required": "True"},
    "return_notes": {"invisible": "rma_number == False",
                     "required": "True"},
}
REQUIRED_TRUE_SPELLINGS = ("True", "1", "true")

#: ``views/stock_picking.xml:8,11`` — the two core anchors, verified present
#: in both trees: v17 ``stock/views/stock_picking_views.xml:230,231``,
#: v19 ``:225,226``. (The earlier ``full_name="partner_id"`` hits are
#: ``<widget>`` elements, not ``<field>``, so they do not capture the xpath.)
FORM_ANCHOR_RMA_NUMBER = "partner_id"
FORM_ANCHOR_REASON = "picking_type_id"

#: ``views/stock_picking.xml:31-32``. Note the inversion against the
#: act_window domains: the filter named *customer* selects **incoming**
#: pickings. TC188 step 9 records it; the two classifications disagree.
FILTER_CUSTOMER_RMA = {
    "name": "customer_rma",
    "string": "Customer RMAs",
    "domain": "[('picking_type_code', '=', 'incoming')]",
}
FILTER_VENDOR_RMA = {
    "name": "vendor_rma",
    "string": "Vendor RMAs",
    "domain": "[('picking_type_code', '=', 'outgoing')]",
}

# --- the three act_windows and the one menu --------------------------
ACTION_ALL_XMLID = f"{MODULE}.action_picking_tree_rma"
ACTION_CUSTOMER_XMLID = f"{MODULE}.action_picking_tree_rma_customer"
ACTION_VENDOR_XMLID = f"{MODULE}.action_picking_tree_rma_vendor"
ACTION_XMLIDS = [ACTION_ALL_XMLID, ACTION_CUSTOMER_XMLID, ACTION_VENDOR_XMLID]

ACTION_NAME = "RMAs"
#: ``views/stock_picking.xml:84,105,126``. NOT migrated by the WF-024 port
#: commit: ``'tree'`` is absent from ``ir.ui.view.type``'s selection on v19
#: (``odoo/addons/base/models/ir_ui_view.py:149``), while v17 still has it
#: (``:163``). ``_check_view_mode`` only rejects duplicates and spaces
#: (v19 ``ir_actions.py:299-306``), so the record saves and the breakage
#: surfaces at view-resolution time. TC188 step 8 is EXPECTED to FAIL on v19.
ACTION_VIEW_MODE = "tree,kanban,form,calendar,activity"

#: ``views/stock_picking.xml:85,106,127`` — verbatim, spacing included.
ACTION_DOMAINS = {
    ACTION_ALL_XMLID: "[('rma_number','!=',False)]",
    ACTION_CUSTOMER_XMLID: "[('rma_number','!=',False),('location_id','=',5)]",
    ACTION_VENDOR_XMLID:
        "[('rma_number','!=',False),('location_dest_id','=',4)]",
}

#: The literal integers the two directional domains hard-code, and the
#: xmlids they should have used. ``views/stock_picking.xml:85-89`` comments
#: id 5 as ``Partners/Customers``; ``:106-110`` comments id 4 as
#: ``Partners/Vendors``.
#:
#: Why those numbers were ever right: a clean **v17** install creates
#: ``stock_location_locations`` (1), ``stock_location_locations_partner``
#: (2), ``stock_location_locations_virtual`` (3),
#: ``stock_location_suppliers`` (4) and ``stock_location_customers`` (5), in
#: that order (``odoo-17.0/addons/stock/data/stock_data.xml:23,28,34,41,48``).
#: Why they cannot be right on v19: that file **removed the Partners parent
#: entirely** and now creates suppliers first and customers second
#: (``odoo-19.0/addons/stock/data/stock_data.xml:23,28``), so a fresh
#: install assigns different ids and the complete names become ``Vendors``
#: and ``Customers`` rather than ``Partners/…``. TC190 asserts the
#: workbook's expectation and is expected to fail; the fix is a one-line
#: ``ref()`` swap, because the SEMANTICS hold in both versions
#: (v17 ``_prepare_picking_default_values:113-127``;
#: v19 ``_prepare_picking_default_values_based_on:142-159``).
HARDCODED_CUSTOMER_LOCATION_ID = 5
HARDCODED_VENDOR_LOCATION_ID = 4
CUSTOMER_LOCATION_XMLID = "stock.stock_location_customers"
VENDOR_LOCATION_XMLID = "stock.stock_location_suppliers"

MENU_XMLID = f"{MODULE}.rma_picking"
MENU_NAME = "RMAs"
MENU_SEQUENCE = 19
MENU_PARENT_XMLID = "stock.menu_stock_transfers"
#: ``views/stock_picking.xml:140``. Both groups exist in both trees:
#: v17 ``stock/security/stock_security.xml:20,25``; v19 ``:10,16``.
MENU_GROUP_XMLIDS = ["stock.group_stock_manager", "stock.group_stock_user"]
STOCK_USER_GROUP = "stock.group_stock_user"
STOCK_MANAGER_GROUP = "stock.group_stock_manager"
#: ``report/report_stockpicking_operations.xml:96`` — the serial-number gate.
SERIAL_GROUP = "stock.group_production_lot"

#: The number of menuitems the module actually defines. See the correction
#: in the module docstring.
RMA_MENU_COUNT = 1
RMA_ACTION_COUNT = 3

# --- the two report actions ------------------------------------------
REPORT_RMA_XMLID = f"{MODULE}.action_report_return"
REPORT_STD_XMLID = "stock.action_report_picking"

#: ``report/stock_report_views.xml:5-9``. ``report_file`` points at CORE's
#: template rather than the module's own — a copy-paste artifact the
#: workbook explicitly says to record as an observation, not a failure.
REPORT_RMA_ACTION = {
    "name": "RMA",
    "model": "stock.picking",
    "report_type": "qweb-pdf",
    "report_name": f"{MODULE}.report_picking_return",
    "report_file": "stock.report_picking_operations",
}
#: Core comparator, byte-identical in both trees
#: (``stock/report/stock_report_views.xml:4-13``).
REPORT_STD_ACTION = {
    "name": "Picking Operations",
    "model": "stock.picking",
    "report_type": "qweb-pdf",
    "report_name": "stock.report_picking",
    "report_file": "stock.report_picking_operations",
}
#: ``report/stock_report_views.xml:10`` — verbatim.
REPORT_RMA_PRINT_REPORT_NAME = (
    "'RMA - %s - %s' % (object.partner_id.name or '', object.rma_number)")

#: What ``report_action()`` actually returns (v17
#: ``ir_actions_report.py:1049-1057``, v19 ``:1171-1179`` — identical
#: bodies). **There is no ``id`` and no xmlid key**, so TC187 discriminates
#: on these four values.
REPORT_ACTION_KEYS = ["report_name", "report_file", "name", "report_type"]

# --- the return wizard -----------------------------------------------
WIZARD_MODEL = "stock.return.picking"
WIZARD_LINE_MODEL = "stock.return.picking.line"
WIZARD_ACTION_XMLID = "stock.act_stock_return_picking"
#: ``wizard/stock_picking_return_views.xml:13-16``.
WIZARD_REPLENISH_METHOD = "create_returns_and_replenishments"
WIZARD_REPLENISH_BUTTON = "Return and Replenish"
#: v17 ``stock/wizard/stock_picking_return.py:183`` /
#: v19 ``:210``. Resolved against the target by ``return_confirm_method``.
RETURN_CONFIRM_METHODS = {"17": "create_returns", "19": "action_create_returns"}
#: ``wizard/stock_picking_return.py:87`` — the action the replenish button
#: returns. ``view_mode`` is ``'form,list,calendar'`` on the v19 fork and
#: was ``'form,tree,calendar'`` on v17, so tests compare it through
#: ``fg_common.list_tag``.
REPLENISH_ACTION_NAME = "Returned Picking"
#: ``wizard/stock_picking_return.py:79-84`` — the six search defaults the
#: method clears.
REPLENISH_CLEARED_CONTEXT_KEYS = [
    "search_default_draft", "search_default_assigned",
    "search_default_confirmed", "search_default_ready",
    "search_default_planning_issues", "search_default_available",
]
#: ``wizard/stock_picking_return.py:66`` — assigned only in a commented-out
#: line. Grep of the whole ``DTO-Odoo`` tree finds the name nowhere else, so
#: TC189 step 17 asserts its ABSENCE on both models (WF-024 E5).
MISSING_BACKLINK_FIELD = "returned_sale_order_id"

# --- error strings, verbatim — evidence only, no case triggers them --
ERROR_NON_ZERO_QTY = "Please specify at least one non-zero quantity."
ERROR_ONLY_DONE_PICKINGS = "You may only return Done pickings."
ERROR_ONE_PICKING_AT_A_TIME = "You may only return one picking at a time."
ERROR_NO_PRODUCTS_TO_RETURN = (
    "No products to return (only lines in Done state and not fully returned "
    "yet can be returned).")
#: v17 only — the line is gone from the v19 wizard.
ERROR_MANUAL_LINES = (
    "You have manually created product lines, please delete them to proceed.")
ERROR_PROMISED_SHIP_DATE = (
    "Please enter 'Promised Ship Date' for all order lines.")
ERROR_ANALYTIC_NOT_ALLOWED = (
    "Analytic Distribution should not be set for this order type")

# --- the undeclared dependencies -------------------------------------
NARRATION_FIELD = "vendor_refund_narration"
#: ``dto_account/models/res_company.py:51-54`` — ``fields.Html``, default
#: ``_default_vendor_refund_narration`` (``:11-49``). Five fragments of that
#: default, verbatim from the source, that TC185 can use to recognise it
#: without depending on whitespace.
NARRATION_FRAGMENTS = [
    "DATAONE Systems",
    "Quality Control Department",
    "9004 AMBASSADOR ROW, DALLAS TX 75247.",
    "MUST BE",
    "15 days",
]
#: ``dto_account/models/res_config_settings.py:10-13`` exposes it as a
#: related field; the settings view labels it "RMA Terms &amp; Condition".
NARRATION_SETTINGS_LABEL = "RMA Terms & Condition"
#: ``dto_sale/models/sale_order_line.py:11-13`` — NOT core. Zero hits in
#: ``odoo-17.0/addons`` or ``enterprise-17.0``.
REPLENISH_DATE_FIELD = "requested_delivery_date"
#: ``dto_sale_stock/data/base_automation_data.xml:4`` — the automation that
#: makes ``require_mail_offline`` mandatory for every sale-linked delivery.
MAIL_AUTOMATION_XMLID = (
    "dto_sale_stock.base_automation_send_email_on_sale_order_shipped")
#: ``dto_sale/models/sale_order.py:17-26`` — ``required=True``.
DEFAULT_ORDER_TYPE = "inventory"
#: A ship date far enough out that no scheduler heuristic touches it and no
#: run of this suite ever produces a different value (convention rule 5).
FIXTURE_SHIP_DATE = "2099-12-31"


# =====================================================================
# Version-safe resolvers — probes, not version switches
# =====================================================================
def return_confirm_method(ctx) -> str:
    """The wizard's public "Return" method on the target.

    Probed from the delivered ``stock.return.picking`` form arch rather than
    from ``ctx.env.version``, because the arch is what the DataOne xpath
    anchors on (``wizard/stock_picking_return_views.xml:12``) and therefore
    the thing that actually has to match. Falls back to the verified version
    table when the arch cannot be read.
    """
    try:
        names = {b.get("name") for b in arch_footer_buttons(wizard_form_arch(ctx))}
    except Exception:                                   # noqa: BLE001
        names = set()
    for candidate in ("action_create_returns", "create_returns"):
        if candidate in names:
            return candidate
    return RETURN_CONFIRM_METHODS.get(ctx.env.version, "action_create_returns")


def sol_uom_field(rpc) -> str:
    """``sale.order.line``'s UoM m2o: ``product_uom`` → ``product_uom_id``."""
    return ("product_uom_id"
            if rpc.field_exists("sale.order.line", "product_uom_id")
            else "product_uom")


def menu_groups_field(rpc) -> str:
    """``ir.ui.menu``'s groups m2m: ``groups_id`` (v17) / ``group_ids`` (v19)."""
    return ("group_ids" if rpc.field_exists("ir.ui.menu", "group_ids")
            else "groups_id")


def act_window_groups_field(rpc) -> str:
    """``ir.actions.act_window``'s groups m2m."""
    return ("group_ids"
            if rpc.field_exists("ir.actions.act_window", "group_ids")
            else "groups_id")


def report_groups_field(rpc) -> str:
    """``ir.actions.report``'s groups m2m."""
    return ("group_ids" if rpc.field_exists("ir.actions.report", "group_ids")
            else "groups_id")


def package_model(rpc) -> str | None:
    """``stock.quant.package`` (v17) / ``stock.package`` (v19), or None."""
    for model in ("stock.package", "stock.quant.package"):
        if rpc.model_exists(model):
            return model
    return None


# =====================================================================
# Preconditions — every one BLOCKS with a precise, named reason
# =====================================================================
def require_rma_module(ctx):
    """BLOCK unless the RMA fork is actually contributing to this target.

    [UNVERIFIED against the QA clone] Whether ``stock_picking_auto_create_lot``
    is installed there, and whether the clone runs the v17 fork or the v19
    port now sitting in ``DTO-Odoo/3rd-addons`` (manifest ``19.0.1.0.0``),
    is a per-database fact this probe measures instead of assuming.
    """
    rpc = ctx.adapter.rpc
    missing = [f"stock.picking.{f}" for f in
               ("rma_number", "reason_for_return", "return_notes")
               if not rpc.field_exists("stock.picking", f)]
    missing += [x for x in ([RMA_SEQUENCE_XMLID, REPORT_RMA_XMLID, MENU_XMLID]
                            + ACTION_XMLIDS)
                if not rpc.ref(x)]
    if missing:
        ctx.blocked(
            f"{MODULE} is not contributing the RMA fork to {ctx.env.key} "
            f"(db={ctx.env.db}) — missing: {', '.join(missing)}. Install the "
            "module on the QA clone before running WF-024; without it there "
            "is no RMA numbering, no reason taxonomy, no RMA report and no "
            "RMA queue to test.")


def require_rma_sequence(ctx) -> int:
    """BLOCK unless the global ``rma_number`` sequence exists. Returns its id.

    Also refuses to run when the target carries MORE than one sequence with
    that code: ``next_by_code`` orders by ``company_id`` and PostgreSQL sorts
    NULLs last, so a company-scoped duplicate silently hijacks every RMA
    number and would make every numbering assertion in this suite measure the
    wrong counter (v17 ``ir_sequence.py:279-292``).
    """
    rpc = ctx.adapter.rpc
    rows = rpc.search_read("ir.sequence",
                           [("code", "=", RMA_SEQUENCE_CODE),
                            ("active", "in", [True, False])],
                           ["id", "name", "company_id"], order="id")
    if not rows:
        ctx.blocked(
            f"No ir.sequence with code {RMA_SEQUENCE_CODE!r} on "
            f"{ctx.env.key} (db={ctx.env.db}) — "
            f"{MODULE}/data/rma_sequence.xml:5-13 has not been loaded, so "
            "stock.picking._get_rma_sequence() would return False and every "
            "return would be created unnumbered.")
    if len(rows) > 1:
        ctx.blocked(
            f"{len(rows)} ir.sequence records share code "
            f"{RMA_SEQUENCE_CODE!r} on {ctx.env.key}: {rows}. next_by_code "
            "orders by company_id and NULLs sort last, so a company-scoped "
            "duplicate takes precedence over the global RMA sequence. Every "
            "numbering assertion would measure the wrong counter — resolve "
            "the duplicate before running WF-024.")
    return rows[0]["id"]


def require_vendor_narration(ctx) -> int:
    """BLOCK unless ``dto_account`` contributed the narration. Returns the
    current company id.

    This is WF-024 E1 turned into a precondition: the module's manifest
    declares ``stock`` alone (``__manifest__.py:14``) while
    ``wizard/stock_picking_return.py:24`` reads
    ``self.env.company.vendor_refund_narration``.
    """
    rpc = ctx.adapter.rpc
    if not rpc.field_exists("res.company", NARRATION_FIELD):
        ctx.blocked(
            f"res.company.{NARRATION_FIELD} does not exist on "
            f"{ctx.env.key} (db={ctx.env.db}) — dto_account is not "
            "installed. stock_picking_auto_create_lot/wizard/"
            "stock_picking_return.py:24 reads it at return time while the "
            "manifest declares only 'stock', so creating a return on this "
            "database raises AttributeError (WF-024 E1).")
    return current_company_id(rpc)


def require_dto_sale(ctx):
    """BLOCK unless ``dto_sale`` contributed what the replenish leg writes."""
    rpc = ctx.adapter.rpc
    missing = []
    if not rpc.field_exists("sale.order", "order_type"):
        missing.append("sale.order.order_type")
    if not rpc.field_exists("sale.order.line", REPLENISH_DATE_FIELD):
        missing.append(f"sale.order.line.{REPLENISH_DATE_FIELD}")
    if not rpc.field_exists("stock.picking", "sale_id"):
        missing.append("stock.picking.sale_id")
    if missing:
        ctx.blocked(
            f"dto_sale / sale_stock are not fully contributing to "
            f"{ctx.env.key} (db={ctx.env.db}) — missing: "
            f"{', '.join(missing)}. _create_returns_and_replenishments "
            "(wizard/stock_picking_return.py:37-64) writes "
            f"{REPLENISH_DATE_FIELD} on sale.order.line and is gated on "
            "picking.sale_id, so the replenishment leg cannot be exercised.")


def require_quality_taxonomy(ctx):
    """BLOCK unless the two quality models carrying copies 2 and 3 exist."""
    rpc = ctx.adapter.rpc
    missing = [m for m in ("quality.check", "quality.check.wizard")
               if not rpc.model_exists(m)]
    missing += [f"{m}.{TAXONOMY_FIELD}" for m in
                ("quality.check", "quality.check.wizard")
                if rpc.model_exists(m)
                and not rpc.field_exists(m, TAXONOMY_FIELD)]
    if missing:
        ctx.blocked(
            "The quality half of the 19-code taxonomy is absent from "
            f"{ctx.env.key} (db={ctx.env.db}) — missing: "
            f"{', '.join(missing)}. quality_control (enterprise) and "
            "dto_purchase_stock must both be installed; without them the "
            "drift detector has only one of the three copies to compare "
            "(dto_purchase_stock/models/quality_check.py:8-26 and "
            "wizard/quality_check_wizard.py:8-26).")


def require_report_layout(ctx) -> bool:
    """True when ``do_print_picking`` will return the REPORT, not the wizard.

    ``report_action`` has an admin trap, identical in both versions (v17
    ``ir_actions_report.py:1060``, v19 ``:1182``)::

        if self.env.is_admin() and not self.env.company.external_report_layout_id \\
                and config and not discard_logo_check:
            return self._action_configure_external_report_layout(report_action)

    An admin RPC session on a company with no ``external_report_layout_id``
    therefore receives ``web.action_base_document_layout_configurator`` —
    an ``ir.actions.act_window`` — instead of the report. Returns False so
    the caller can route the call through a non-admin session
    (``rpc_as_group_user``) rather than mis-reporting the trap as a defect.
    """
    rpc = ctx.adapter.rpc
    company_id = current_company_id(rpc)
    row = rpc.read("res.company", [company_id],
                   ["name", "external_report_layout_id"])[0]
    configured = bool(m2o_id(row["external_report_layout_id"]))
    if not configured:
        ctx.log(
            f"[note] company {row['name']!r} has no external_report_layout_id; "
            "report_action() returns the layout configurator for an ADMIN "
            "session (ir_actions_report.py:1060 / :1182). The print "
            "assertions must run as a non-admin user.")
    return configured


def current_company_id(rpc) -> int:
    return m2o_id(rpc.read("res.users", [rpc.uid], ["company_id"])[0]
                  ["company_id"])


# =====================================================================
# Sweeping — children before parents, best effort, never raises
# =====================================================================
def sweep_wf024(rpc):
    """Remove every marker-scoped leftover of a previous execution.

    Order matters and follows the reference dependencies:

    1. ``account.move`` — the invoices ``dto_sale_stock._action_done``
       auto-posts (``models/stock_picking.py:12-23``) reference sale order
       lines, so they go first; posted moves are reset to draft before the
       unlink is attempted.
    2. ``stock.picking`` — including the RETURN pickings, which carry the
       core-generated origin ``"Return of <name>"`` and therefore no token.
       They are reached by ``return_id`` and by the token partner, never by
       ``rma_number``: sweeping on ``rma_number`` would reach live business
       returns, which convention rule 3 forbids outright.
    3. ``sale.order`` — after its pickings, including the replenishment
       delivery ``sale_stock.SaleOrderLine.create`` spawns
       (``sale_stock/models/sale_order_line.py:188-191``).
    4. quants, products, packages, partners, scratch sequences.

    Every step is best effort: a delivered picking cannot be unlinked and a
    posted invoice may refuse to reset. The fresh per-execution token is what
    guarantees a survivor cannot collide with this run's assertions.
    """
    partner_ids = rpc.search("res.partner",
                             [("name", "like", f"{MARKER}%"),
                              ("active", "in", [True, False])])
    product_ids = rpc.search("product.product",
                             [("default_code", "like", f"{MARKER}%"),
                              ("active", "in", [True, False])])

    # 1 — invoices auto-created and auto-posted by dto_sale_stock
    move_ids = set(rpc.search("account.move",
                              [("invoice_origin", "like", f"{MARKER}%")]))
    if partner_ids:
        move_ids |= set(rpc.search("account.move",
                                   [("partner_id", "in", partner_ids)]))
    for move_id in sorted(move_ids):
        for method in ("button_draft", "button_cancel"):
            try:
                rpc.call("account.move", method, [move_id])
            except OdooRPCError:
                pass
        try:
            rpc.call("account.move", "unlink", [move_id])
        except OdooRPCError:
            pass

    # 2 — pickings, returns of those pickings, and their moves
    picking_domain = ["|", ("origin", "like", f"{MARKER}%"),
                      ("partner_id", "in", partner_ids or [0])]
    picking_ids = set(rpc.search("stock.picking", picking_domain))
    if picking_ids:
        picking_ids |= set(rpc.search(
            "stock.picking", [("return_id", "in", sorted(picking_ids))]))
    if picking_ids:
        ids = sorted(picking_ids)
        for picking_id in ids:
            try:
                rpc.call("stock.picking", "action_cancel", [picking_id])
            except OdooRPCError:
                pass
        sweep_model(rpc, "stock.move.line", [("picking_id", "in", ids)])
        sweep_model(rpc, "stock.move", [("picking_id", "in", ids)])
        sweep_model(rpc, "stock.picking", [("id", "in", ids)])

    # 3 — sale orders (after their pickings)
    order_domain = ["|", ("origin", "like", f"{MARKER}%"),
                    ("partner_id", "in", partner_ids or [0])]
    order_ids = rpc.search("sale.order",
                           order_domain + [("active", "in", [True, False])])
    for order_id in order_ids:
        try:
            rpc.call("sale.order", "action_cancel", [order_id],
                     context={"disable_cancel_warning": True})
        except OdooRPCError:
            pass
    if order_ids:
        sweep_model(rpc, "sale.order.line", [("order_id", "in", order_ids)])
        sweep_model(rpc, "sale.order", [("id", "in", order_ids)])

    # 4 — quants, products, packages, partners, scratch sequences
    if product_ids:
        sweep_model(rpc, "stock.quant", [("product_id", "in", product_ids)])
    sweep_products(rpc, MARKER)
    sweep_model(rpc, "product.product",
                [("default_code", "like", f"{MARKER}%"),
                 ("active", "in", [True, False])])
    sweep_model(rpc, "product.template",
                [("default_code", "like", f"{MARKER}%"),
                 ("active", "in", [True, False])])
    pkg_model = package_model(rpc)
    if pkg_model:
        sweep_model(rpc, pkg_model, [("name", "like", f"{MARKER}%")])
    if partner_ids:
        sweep_model(rpc, "res.partner",
                    [("id", "in", partner_ids), ("user_ids", "=", False)])
    # Scratch sequences only ever carry a TOKEN-scoped code — never
    # 'rma_number' (see the module docstring, safety fact 6).
    sweep_model(rpc, "ir.sequence", [("code", "like", f"{MARKER}-%")])


def open_namespace(ctx):
    """Sweep leftovers and log the namespace this execution will use."""
    with ctx.step(f"Sweep previous {MARKER} fixtures and open a fresh "
                  "namespace"):
        sweep_wf024(ctx.adapter.rpc)
        ctx.log(f"fixture token = {_TOKEN}")


def safe_sweep(ctx):
    """Teardown for a ``finally:`` block. Cannot raise, by contract."""
    try:
        sweep_wf024(ctx.adapter.rpc)
    except Exception as exc:                            # noqa: BLE001
        try:
            ctx.log(f"[warn] WF-024 teardown did not complete: {exc}")
        except Exception:                               # noqa: BLE001
            pass


# =====================================================================
# Fixture builders
# =====================================================================
def ensure_partner(rpc, label="Customer") -> int:
    name = tag(label)
    found = rpc.search("res.partner", [("name", "=", name)], limit=1)
    return found[0] if found else rpc.create("res.partner", {"name": name})


def make_product(ctx, label="Item", price=10.0, cost=9.0) -> int:
    """A storable, sellable, purchasable product under the token.

    Storability goes through ``ctx.adapter.storable_product_values()``
    (v17 ``type='product'``; v19 ``type='consu'`` + ``is_storable=True``),
    so no version branch reaches a fixture. ``taxes_id`` is emptied so
    TC189's "the order total increased by 0.00" assertion cannot be
    perturbed by the database's default tax configuration.
    """
    rpc = ctx.adapter.rpc
    code = f"{_TOKEN}-{label}"
    found = rpc.search_read("product.product", [("default_code", "=", code)],
                            ["id"], limit=1)
    if found:
        return found[0]["id"]
    values = {"name": tag(label), "default_code": code,
              "list_price": price, "standard_price": cost,
              "sale_ok": True, "purchase_ok": True,
              "tracking": "none", "taxes_id": [(6, 0, [])]}
    values.update(ctx.adapter.storable_product_values())
    tmpl_id = rpc.create("product.template", with_categ(rpc, values))
    variant = rpc.search_read("product.product",
                              [("product_tmpl_id", "=", tmpl_id)],
                              ["id"], limit=1)
    return variant[0]["id"]


def product_uom_of(rpc, product_id: int) -> int:
    return m2o_id(rpc.read("product.product", [product_id],
                           ["uom_id"])[0]["uom_id"])


def picking_type(rpc, code: str) -> dict:
    """The lowest-id operation type of the given code, with its defaults."""
    rows = rpc.search_read(
        "stock.picking.type", [("code", "=", code)],
        ["id", "name", "code", "default_location_src_id",
         "default_location_dest_id", "return_picking_type_id"],
        limit=1, order="id")
    if not rows:
        raise AssertionError(f"no stock.picking.type with code={code!r}")
    return rows[0]


def warehouse_stock_location(rpc) -> int:
    rows = rpc.search_read("stock.warehouse", [], ["lot_stock_id"],
                           limit=1, order="id")
    if not rows:
        raise AssertionError("no stock.warehouse on the target")
    return m2o_id(rows[0]["lot_stock_id"])


def partner_location(rpc, xmlid: str, usage: str) -> int | None:
    """Resolve Customers / Vendors by xmlid, falling back to usage.

    ``rpc.ref`` resolves through ``ir.model.data`` and returns None when the
    xmlid is absent (``adapters/base.py:209-216``). Both xmlids exist in both
    trees; the fallback exists only so a fixture still builds on a database
    whose ``ir_model_data`` row was lost in a restore — TC190 reads the
    xmlid directly and must NOT use this fallback.
    """
    found = rpc.ref(xmlid)
    if found and rpc.search("stock.location", [("id", "=", found)]):
        return found
    rows = rpc.search_read("stock.location", [("usage", "=", usage)],
                           ["id"], limit=1, order="id")
    return rows[0]["id"] if rows else None


def customer_location(rpc) -> int | None:
    return partner_location(rpc, CUSTOMER_LOCATION_XMLID, "customer")


def vendor_location(rpc) -> int | None:
    return partner_location(rpc, VENDOR_LOCATION_XMLID, "supplier")


def _make_picking(ctx, code, product_qty, partner_id, src_id, dest_id,
                  label) -> int:
    rpc = ctx.adapter.rpc
    ptype = picking_type(rpc, code)
    src_id = src_id or m2o_id(ptype["default_location_src_id"])
    dest_id = dest_id or m2o_id(ptype["default_location_dest_id"])
    moves = []
    for product_id, qty in product_qty:
        moves.append((0, 0, {
            "product_id": product_id,
            "product_uom": product_uom_of(rpc, product_id),
            "product_uom_qty": qty,
            "location_id": src_id,
            "location_dest_id": dest_id,
        }))
    return rpc.create("stock.picking", {
        "picking_type_id": ptype["id"],
        "partner_id": partner_id,
        "location_id": src_id,
        "location_dest_id": dest_id,
        "origin": tag(label),
        "move_ids": moves,
    })


def make_receipt(ctx, product_qty, partner_id=None, label="RECEIPT",
                 validate=True) -> int:
    """A DONE incoming receipt from the Vendors location.

    This is the source picking of a **vendor** RMA: the return's
    ``location_dest_id`` becomes this receipt's ``location_id`` — the Vendors
    location — in both versions (v17
    ``_prepare_picking_default_values:113-127`` defaults the wizard's
    ``location_id`` to ``picking.location_id``; v19
    ``_prepare_picking_default_values_based_on:142-159`` sets
    ``location_dest_id = picking.location_id`` when the return type is not
    incoming).

    A receipt fires **no** outbound automation: ``dto_sale_stock``'s mail
    automation filters on ``picking_type_code == 'outgoing'`` and a
    ``sale_id``, and needs no stock on hand.
    """
    rpc = ctx.adapter.rpc
    partner_id = partner_id or ensure_partner(rpc, "Vendor")
    picking_id = _make_picking(ctx, "incoming", product_qty, partner_id,
                               vendor_location(rpc),
                               warehouse_stock_location(rpc), label)
    if validate:
        rpc.call("stock.picking", "action_confirm", [picking_id])
        validate_picking(ctx, picking_id)
    return picking_id


def make_delivery(ctx, product_qty, partner_id=None, label="DELIVERY",
                  stock_qty=None, validate=True) -> int:
    """A DONE outgoing delivery to the Customers location, with NO sale link.

    This is the source picking of a **customer** RMA: the return's
    ``location_id`` becomes this delivery's ``location_dest_id`` — the
    Customers location — in both versions.

    No ``sale_id``, therefore no ``dto_sale_stock`` mail and no auto-invoice;
    it is also the fixture TC189 step 18 needs to prove the sale leg is
    conditional. Use ``sell_and_deliver`` when a sale link IS required.
    """
    rpc = ctx.adapter.rpc
    partner_id = partner_id or ensure_partner(rpc, "Customer")
    src_id = warehouse_stock_location(rpc)
    for product_id, qty in product_qty:
        set_stock(ctx, product_id, stock_qty if stock_qty is not None
                  else qty * 10, location_id=src_id)
    picking_id = _make_picking(ctx, "outgoing", product_qty, partner_id,
                               src_id, customer_location(rpc), label)
    if validate:
        rpc.call("stock.picking", "action_confirm", [picking_id])
        try:
            rpc.call("stock.picking", "action_assign", [picking_id])
        except OdooRPCError as exc:
            ctx.log(f"[warn] action_assign on picking {picking_id}: {exc}")
        validate_picking(ctx, picking_id)
    return picking_id


def make_sale_order(ctx, lines, order_type=DEFAULT_ORDER_TYPE,
                    partner_id=None, label="SO") -> int:
    """A confirmable DataOne sale order. ``lines`` = [(product_id, qty, price)].

    Carries everything the three stacked confirmation gates need:

    * ``order_type`` — ``required=True``
      (``dto_sale/models/sale_order.py:17-26``);
    * ``requested_delivery_date`` on every product line, or
      ``_dto_gate_promised_ship_date`` (``:90-94``) raises
      ``ERROR_PROMISED_SHIP_DATE``;
    * **no** ``analytic_distribution`` — the default ``'inventory'`` type is
      the one whose analytic gate demands exactly that
      (``dto_account/models/sale_order.py:107``), which keeps the fixture
      independent of whichever analytic plans this database happens to have;
    * ``memo_to_suppliers`` when ``dto_sale_workday`` contributed it — the
      confirmation automation evaluates ``'IRM' in order.memo_to_suppliers``
      and raises TypeError on a False value (DATAONE-TC085).
    """
    rpc = ctx.adapter.rpc
    partner_id = partner_id or ensure_partner(rpc, "Customer")
    order_lines = [(0, 0, {"product_id": product_id,
                           "product_uom_qty": qty,
                           "price_unit": price,
                           REPLENISH_DATE_FIELD: FIXTURE_SHIP_DATE})
                   for product_id, qty, price in lines]
    values = {"partner_id": partner_id,
              "origin": tag(label),
              "order_type": order_type,
              "order_line": order_lines}
    if rpc.field_exists("sale.order", "requester_email"):
        values["requester_email"] = "qa.wf024@example.invalid"
    if rpc.field_exists("sale.order", "memo_to_suppliers"):
        values["memo_to_suppliers"] = f"{MARKER} QA memo"
    return rpc.create("sale.order", values)


def sell_and_deliver(ctx, lines, order_type=DEFAULT_ORDER_TYPE,
                     partner_id=None, label="SO", stock_qty=None):
    """Stock → confirm → deliver. Returns ``(order_id, picking_id)``.

    The picking it returns has ``sale_id`` set, which is what gates the whole
    replenishment leg (``wizard/stock_picking_return.py:37``).

    **Callers must run ``require_mail_offline(ctx)`` first** — validating a
    sale-linked delivery fires ``dto_sale_stock``'s automation and its
    ``send_mail(force_send=True)`` against hard-coded ``@d1systems.com``
    recipients (convention rule 4). Validation may also auto-create and POST
    an invoice (``dto_sale_stock/models/stock_picking.py:12-23``); the sweep
    removes it by ``invoice_origin``.
    """
    rpc = ctx.adapter.rpc
    for product_id, qty, _price in lines:
        set_stock(ctx, product_id,
                  stock_qty if stock_qty is not None else qty * 10)
    order_id = make_sale_order(ctx, lines, order_type=order_type,
                               partner_id=partner_id, label=label)
    rpc.call("sale.order", "action_confirm", [order_id])
    state = rpc.read("sale.order", [order_id], ["state"])[0]["state"]
    if state != "sale":
        ctx.blocked(
            f"The {order_type!r} fixture order did not confirm "
            f"(state={state!r}) on {ctx.env.key}. WF-024's replenishment "
            "leg needs a delivered, sale-linked picking; check the three "
            "DataOne confirmation gates (dto_sale_workday requester email, "
            "dto_account analytic distribution, dto_sale promised ship "
            "date).")
    pickings = rpc.search_read("stock.picking", [("sale_id", "=", order_id)],
                               ["id", "state", "picking_type_code"],
                               order="id")
    outgoing = [p for p in pickings if p["picking_type_code"] == "outgoing"]
    if not outgoing:
        ctx.blocked(
            f"Confirming the fixture order produced no outgoing picking on "
            f"{ctx.env.key} (pickings={pickings!r}). Without a delivery "
            "there is nothing to return.")
    picking_id = outgoing[0]["id"]
    try:
        rpc.call("stock.picking", "action_assign", [picking_id])
    except OdooRPCError as exc:
        ctx.log(f"[warn] action_assign on picking {picking_id}: {exc}")
    validate_picking(ctx, picking_id)
    return order_id, picking_id


def order_lines(rpc, order_id: int, fields_=None) -> list[dict]:
    fields_ = fields_ or ["product_id", "product_uom_qty", "price_unit",
                          "price_subtotal", "name", REPLENISH_DATE_FIELD,
                          sol_uom_field(rpc)]
    return rpc.search_read("sale.order.line", [("order_id", "=", order_id)],
                           fields_, order="id")


def order_total(rpc, order_id: int) -> float:
    return rpc.read("sale.order", [order_id], ["amount_total"])[0]["amount_total"]


def make_scratch_sequence(rpc, label="SEQ", prefix="%(year)s-", padding=3,
                          number_next=1) -> int:
    """A disposable, TOKEN-scoped ``ir.sequence``.

    Its ``code`` is deliberately **never** ``rma_number``: a second sequence
    with that code would sort ahead of the global one in ``next_by_code``
    (NULL company sorts last) and hijack live RMA numbering.
    """
    return rpc.create("ir.sequence", {
        "name": tag(label),
        "code": f"{MARKER}-{label}-{uuid.uuid4().hex[:6]}",
        "prefix": prefix,
        "padding": padding,
        "number_next": number_next,
        "number_increment": 1,
        "implementation": "standard",
        "company_id": False,
    })


def server_today(rpc) -> str | None:
    """The server's own ``fields.Date.today()``, read exactly.

    TC189 step 13 asserts the replacement line's
    ``requested_delivery_date`` equals *today*, where "today" is
    ``fields.Date.today()`` evaluated in the **Odoo server process**
    (``wizard/stock_picking_return.py:54``) — not the platform host's date
    and not the session timezone's date. Guessing it would make the case
    fail across a midnight boundary or a server in another timezone, and
    widening the assertion to a ±1-day window would weaken the workbook.

    So it is measured instead: the package model is the one core model with
    a Date field defaulting to ``fields.Date.today`` — ``pack_date``
    (v17 ``stock/models/stock_quant.py:1483``, v19
    ``stock/models/stock_package.py:54``). A namespaced package is created,
    its default read, and the record removed immediately; the name is
    supplied explicitly so no ``ir.sequence`` is consumed. Returns None when
    the probe is unavailable, which the caller should treat as BLOCKED
    rather than fall back to a host-side date.
    """
    model = package_model(rpc)
    if not model:
        return None
    pkg_id = None
    try:
        pkg_id = rpc.create(model, {"name": tag("TODAY-PROBE")})
        return rpc.read(model, [pkg_id], ["pack_date"])[0]["pack_date"]
    except OdooRPCError:
        return None
    finally:
        if pkg_id:
            try:
                rpc.unlink(model, [pkg_id])
            except OdooRPCError:
                pass


# =====================================================================
# The return wizard
# =====================================================================
def open_return_wizard(rpc, picking_id: int) -> int:
    """Create the ``stock.return.picking`` wizard for a done picking.

    ``product_return_moves`` is a STORED compute on ``picking_id`` in both
    versions (v17 ``:37`` + ``_compute_moves_locations:46``, v19 ``:103`` +
    ``:106``), so the lines materialise on create. The UI context is passed
    as well so the path matches what the Return button does.
    """
    return rpc.call(WIZARD_MODEL, "create", {"picking_id": picking_id},
                    context={"active_model": "stock.picking",
                             "active_id": picking_id,
                             "active_ids": [picking_id]})


def wizard_lines(rpc, wizard_id: int) -> list[dict]:
    """The wizard's return lines, with the quantity the target prefilled.

    v17 prefills the delivered-minus-already-returned quantity
    (``_prepare_stock_return_picking_line_vals_from_move:80-92``); **v19
    prefills 0** (``:131-137``). TC184 step 4 states the v17 behaviour, so
    it is EXPECTED to FAIL on v19 — read the numbers, do not adapt them.
    """
    return rpc.search_read(WIZARD_LINE_MODEL,
                           [("wizard_id", "=", wizard_id)],
                           ["product_id", "quantity", "uom_id", "move_id"],
                           order="id")


def set_return_quantities(rpc, wizard_id: int, by_product: dict) -> dict:
    """Write one return quantity per product. Returns {line_id: quantity}."""
    applied = {}
    for line in wizard_lines(rpc, wizard_id):
        product_id = m2o_id(line["product_id"])
        if product_id in by_product:
            qty = by_product[product_id]
            rpc.write(WIZARD_LINE_MODEL, [line["id"]], {"quantity": qty})
            applied[line["id"]] = qty
    return applied


def confirm_return(ctx, wizard_id: int):
    """Press "Return" through the version's own public method."""
    return ctx.adapter.rpc.call(WIZARD_MODEL, return_confirm_method(ctx),
                                [wizard_id])


def confirm_return_and_replenish(rpc, wizard_id: int):
    """Press "Return and Replenish" — the DataOne button.

    ``create_returns_and_replenishments``
    (``wizard/stock_picking_return.py:69-95``) is public and returns a plain
    dict, so it is RPC-reachable. Note it has **no** ``ensure_one()`` and
    lets ``new_picking`` leak out of its own ``for wizard in self`` loop
    (``:70-71``) — the same shape v17 had at ``:53-55``.
    """
    return rpc.call(WIZARD_MODEL, WIZARD_REPLENISH_METHOD, [wizard_id])


def action_res_id(action) -> int | None:
    return action.get("res_id") if isinstance(action, dict) else None


def return_of(rpc, source_picking_id: int, fields_=None) -> dict | None:
    """The return picking created from ``source_picking_id``.

    Found by ``stock.picking.return_id``, which both versions set in
    ``_prepare_picking_default_values`` (v17 ``:118``, v19 ``:154``) and
    which exists on both (v17 ``stock_picking.py:410``, v19 ``:566``).
    """
    rows = rpc.search_read("stock.picking",
                           [("return_id", "=", source_picking_id)],
                           fields_ or RMA_SNAPSHOT_FIELDS, order="id desc",
                           limit=1)
    return rows[0] if rows else None


#: Everything the RMA cases read off a picking, in one round trip.
RMA_SNAPSHOT_FIELDS = [
    "name", "origin", "state", "partner_id", "rma_number",
    "reason_for_return", "return_notes", "note", "printed",
    "location_id", "location_dest_id", "picking_type_id",
    "picking_type_code", "return_id",
]


def rma_snapshot(rpc, picking_id: int) -> dict:
    fields_ = list(RMA_SNAPSHOT_FIELDS)
    if rpc.field_exists("stock.picking", "sale_id"):
        fields_.append("sale_id")
    return rpc.read("stock.picking", [picking_id], fields_)[0]


def expect_error(rpc_callable, *args, **kwargs):
    """Run a call the workbook expects to raise → ``(raised, message)``.

    Convention: never raise a bare AssertionError; wrap the expected RPC
    failure and let ``ctx.check`` record expected vs actual.
    """
    try:
        rpc_callable(*args, **kwargs)
        return False, "no error raised"
    except OdooRPCError as exc:
        return True, str(exc)


# =====================================================================
# View arch helpers
# =====================================================================
def picking_form_arch(ctx) -> str:
    return form_arch(ctx, "stock.picking", "form")


def wizard_form_arch(ctx) -> str:
    return form_arch(ctx, WIZARD_MODEL, "form")


def search_view_arch(ctx) -> str:
    """The RMA queues' own search view, read from the record.

    ``view_picking_internal_search_inherit`` carries no ``inherit_id``
    (``views/stock_picking.xml:17-20``), so it is NOT part of the composed
    ``stock.picking`` search arch — ``get_view`` would return core's. The
    act_windows point at it through ``search_view_id``
    (``:93,114,129``), so it is read directly off ``ir.ui.view``.

    Both ``arch_db`` (the stored blob) and ``arch`` (the computed view) exist
    on both versions — v17 ``odoo/addons/base/models/ir_ui_view.py:172,177``,
    v19 ``:157,162`` — so the stored blob is preferred and the computed field
    is the fallback.
    """
    rpc = ctx.adapter.rpc
    view_id = rpc.ref(SEARCH_VIEW_XMLID)
    if not view_id:
        return ""
    row = rpc.read("ir.ui.view", [view_id], ["arch_db", "arch"])[0]
    return row.get("arch_db") or row.get("arch") or ""


def arch_field_attrs(arch: str, field_name: str) -> list[dict]:
    """Every ``<field name=...>`` node's attributes, in document order."""
    if not arch:
        return []
    root = ET.fromstring(arch)
    return [dict(node.attrib) for node in root.iter("field")
            if node.get("name") == field_name]


def arch_field_order(arch: str) -> list[str]:
    """The ``name`` of every ``<field>`` node, in document order.

    TC186 steps 2-3 assert the two RMA fields sit AFTER ``picking_type_id``,
    which is what the xpath says (``views/stock_picking.xml:11``).
    """
    if not arch:
        return []
    root = ET.fromstring(arch)
    return [node.get("name") or "" for node in root.iter("field")]


def arch_footer_buttons(arch: str) -> list[dict]:
    """``<footer>`` buttons in document order, attributes as written.

    The resulting order is version-shaped and verified:
    v17 ``Return`` → **Return and Replenish** → ``Cancel``
    (core ``stock/wizard/stock_picking_return_views.xml:34-37``);
    v19 ``Return`` → **Return and Replenish** → ``Return All`` →
    ``Return for Exchange`` → ``Discard`` (core ``:26-31``).
    """
    if not arch:
        return []
    root = ET.fromstring(arch)
    buttons = []
    for footer in root.iter("footer"):
        buttons.extend(dict(node.attrib) for node in footer.iter("button"))
    return buttons


def arch_filter(arch: str, name: str) -> dict | None:
    """One ``<filter name=...>`` node's attributes."""
    if not arch:
        return None
    root = ET.fromstring(arch)
    for node in root.iter("filter"):
        if node.get("name") == name:
            return dict(node.attrib)
    return None


def selection_of(rpc, model: str, field: str) -> list[list]:
    """A Selection field's ``[key, label]`` pairs, in declaration order.

    ``lang='en_US'`` is forced: ``fields_get`` returns TRANSLATED labels, and
    TC186 step 6 compares against the source literals
    (``models/stock_picking.py:13-31``).
    """
    info = rpc.call(model, "fields_get", [field], attributes=["selection"],
                    context={"lang": "en_US"})
    return (info.get(field) or {}).get("selection") or []


def taxonomy_selections(ctx) -> dict:
    """The 19-code list as each of the three models declares it.

    TC186 step 13 — the drift detector. Read over RPC, not by grepping the
    source, because ``framework.source_scan``'s default root is
    ``DTO-Odoo``, which now holds the **v19** port: grepping it during a v17
    run would compare the wrong tree.
    """
    rpc = ctx.adapter.rpc
    out = {}
    for model in TAXONOMY_MODELS:
        if rpc.model_exists(model) and rpc.field_exists(model, TAXONOMY_FIELD):
            out[model] = [list(pair) for pair in
                          selection_of(rpc, model, TAXONOMY_FIELD)]
    return out


def field_is_readonly_in_model(rpc, model: str, field: str) -> bool:
    """``fields_get``'s ``readonly`` — the MODEL-level attribute.

    TC184 step 9 and TC186 steps 4-5 both turn on the same point: the arch
    says ``readonly="1"`` / ``required="True"`` while the model field says
    nothing (``models/stock_picking.py:9,11,35``). The protection is a
    client-side view modifier, and the ORM does not enforce it.
    """
    info = rpc.call(model, "fields_get", [field], attributes=["readonly"])
    return bool((info.get(field) or {}).get("readonly"))


# =====================================================================
# Reports
# =====================================================================
def print_action(rpc, picking_id: int):
    """Call the public ``stock.picking.do_print_picking``.

    Returns the action dict. Beware the admin trap — see
    ``require_report_layout``.
    """
    return rpc.call("stock.picking", "do_print_picking", [picking_id])


def report_row(rpc, xmlid: str) -> dict | None:
    """An ``ir.actions.report`` record's assertable fields.

    ``paperformat_id`` is read rather than ``get_paperformat()``, which
    returns a recordset and cannot be marshalled over ``call_kw``
    (v17 ``ir_actions_report.py:245``, v19 ``:288``).
    """
    report_id = rpc.ref(xmlid)
    if not report_id:
        return None
    fields_ = ["name", "model", "report_type", "report_name", "report_file",
               "print_report_name", "binding_type", "paperformat_id",
               report_groups_field(rpc)]
    row = rpc.read("ir.actions.report", [report_id], fields_)[0]
    row["xmlid"] = xmlid
    return row


def company_paperformat(rpc) -> dict:
    """The paperformat the RMA report actually uses.

    ``action_report_return`` declares none (``report/stock_report_views.xml``
    has no ``paperformat_id`` field), so ``get_paperformat()`` falls back to
    ``self.env.company.paperformat_id`` (v17 ``:245-246``, v19 ``:288-289``).
    ``report.paperformat.default`` is inert — nothing in core reads it
    (v17 ``odoo/addons/base/models/report_paperformat.py:171``, v19 ``:170``)
    — so TC187 step 13 asserts on the COMPANY's format, and specifically
    that it is not the 43 x 30 mm label
    ``location_barcode_labels/views/barcode_labels_location.xml:13-28``
    ships with ``default=True``.
    """
    company_id = current_company_id(rpc)
    fmt = rpc.read("res.company", [company_id], ["paperformat_id"])[0]
    fmt_id = m2o_id(fmt["paperformat_id"])
    if not fmt_id:
        return {"company_id": company_id, "paperformat_id": False}
    row = rpc.read("report.paperformat", [fmt_id],
                   ["name", "format", "page_width", "page_height",
                    "orientation", "default"])[0]
    row["company_id"] = company_id
    return row


def session_for(env, login: str | None = None, password: str | None = None):
    """An authenticated urllib opener, optionally as another user.

    ``framework.fg_common.http_session`` always authenticates as the
    environment's own user; TC187 step 9 needs a second session in a
    different group, so this takes explicit credentials.
    """
    jar_env = copy.copy(env)
    if login:
        jar_env.username = login
        jar_env.password = password or QA_PASSWORD
    import http.cookiejar
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(jar))
    payload = json.dumps({"jsonrpc": "2.0", "params": {
        "db": jar_env.db, "login": jar_env.username,
        "password": jar_env.password}})
    req = urllib.request.Request(
        f"{jar_env.base_url}/web/session/authenticate", data=payload.encode(),
        headers={"Content-Type": "application/json"})
    res = json.loads(opener.open(req, timeout=60).read())
    if not (res.get("result") or {}).get("uid"):
        raise OdooRPCError(
            f"web session authentication failed for {jar_env.username!r} "
            f"on db {jar_env.db!r}")
    return opener


def report_html(ctx, report_name: str, res_id: int, opener=None) -> str:
    """Render a report as HTML through ``/report/html/<name>/<id>``.

    The route is declared identically in both versions
    (``web/controllers/report.py:23-40``) and dispatches to
    ``_render_qweb_html``, so it needs **no wkhtmltopdf** — which is what
    makes TC187's body assertions (steps 5-9, 12) automatable at all.
    ``/report/pdf/...`` is deliberately not used: it requires wkhtmltopdf on
    the Odoo host and 500s without it.

    **EXPECTED v19 OUTCOME: FAIL/ERROR** for
    ``stock_picking_auto_create_lot.report_picking_return``. The forked
    template references five things v19 removed —
    ``stock.picking.move_ids_without_package`` (``:94``; v17
    ``stock/models/stock_picking.py:466``),
    ``move_line_ids_without_package`` (``:121``; v17 ``:492``),
    ``package_level_ids`` (``:174,184``; v17 ``:523``),
    ``stock.move.product_packaging_id`` / ``product_packaging_qty``
    (``:129-135``; v17 ``stock/models/stock_move.py:182,183``) and
    ``stock.quant.package``, renamed to ``stock.package``
    (v19 ``stock/models/stock_package.py:18``). The module still installs —
    QWeb templates are not validated at install — so this is a runtime bomb,
    and the failure is the finding. Do not soften it.
    """
    opener = opener or session_for(ctx.env)
    url = f"{ctx.env.base_url}/report/html/{report_name}/{res_id}"
    with opener.open(url, timeout=120) as res:
        return res.read().decode("utf-8", errors="replace")


def expected_report_filename(rpc, picking_id: int) -> str:
    """What ``/report/download`` names the file, computed from the source.

    The filename is built by the HTTP controller, not by the action:
    ``safe_eval(report.print_report_name, {'object': obj, 'time': time})``
    (v17 ``web/controllers/report.py:128-130``, v19 ``:135-136``) over
    ``print_report_name`` = ``REPORT_RMA_PRINT_REPORT_NAME``.
    """
    row = rpc.read("stock.picking", [picking_id],
                   ["partner_id", "rma_number"])[0]
    partner = row["partner_id"][1] if row["partner_id"] else ""
    return f"RMA - {partner} - {row['rma_number'] or False}"


# =====================================================================
# Users, groups and menu visibility
# =====================================================================
def ensure_user_in_groups(ctx, suffix: str, group_xmlids) -> tuple[int, str]:
    """A disposable internal user in exactly the given groups.

    The m2m name comes from ``ctx.adapter.user_groups_field`` (v17
    ``res.users.groups_id``, ``base/models/res_users.py:384``; v19
    ``group_ids``, ``:257``) so no version branch reaches a test body.
    Reused across runs by login, and always rewritten to the requested set,
    which keeps TC188's three sessions independent of each other.
    """
    rpc = ctx.adapter.rpc
    groups_field = ctx.adapter.user_groups_field
    login = f"qa.wf024.{suffix}"
    group_ids = [rpc.ref(x) for x in ["base.group_user"] + list(group_xmlids)]
    group_ids = sorted({g for g in group_ids if g})
    found = rpc.search("res.users", [("login", "=", login),
                                     ("active", "in", [True, False])], limit=1)
    if found:
        rpc.write("res.users", found,
                  {"active": True, "password": QA_PASSWORD,
                   groups_field: [(6, 0, group_ids)]})
        return found[0], login
    user_id = rpc.call("res.users", "create",
                       {"name": f"QA WF024 {suffix}", "login": login,
                        "password": QA_PASSWORD,
                        groups_field: [(6, 0, group_ids)]},
                       context={"no_reset_password": True})
    return user_id, login


def rpc_as(env, login: str, password: str = QA_PASSWORD) -> OdooRPC:
    """A second RPC session authenticated as another user."""
    user_env = copy.copy(env)
    user_env.username = login
    user_env.password = password
    return OdooRPC(user_env)


def rpc_as_group_user(ctx, suffix: str, group_xmlids) -> OdooRPC:
    """Shorthand: build the user, then a session as them."""
    _uid, login = ensure_user_in_groups(ctx, suffix, group_xmlids)
    return rpc_as(ctx.env, login)


def visible_menu_ids(rpc) -> set:
    """Menu ids the session's user can actually see.

    ``ir.ui.menu.load_menus(debug)`` is ``@api.model``, public, and returns a
    dict keyed by menu id (v17 ``:247``, v19 ``:236``) — the definitive
    answer the web client itself uses. JSON turns the keys into strings, and
    both versions add a ``'root'`` entry, so both are normalised away. Falls
    back to ``search``, whose ``ir.ui.menu`` override applies the same group
    filter, if ``load_menus`` is unavailable.
    """
    try:
        menus = rpc.call("ir.ui.menu", "load_menus", False)
    except OdooRPCError:
        return set(rpc.search("ir.ui.menu", []))
    ids = set()
    if isinstance(menus, dict):
        for key in menus:
            try:
                ids.add(int(key))
            except (TypeError, ValueError):
                continue
    return ids


def menu_row(rpc, xmlid: str = MENU_XMLID) -> dict | None:
    """The RMA menuitem with its parent, sequence, action and group set."""
    menu_id = rpc.ref(xmlid)
    if not menu_id:
        return None
    fields_ = ["name", "parent_id", "sequence", "action",
               menu_groups_field(rpc)]
    row = rpc.read("ir.ui.menu", [menu_id], fields_)[0]
    row["xmlid"] = xmlid
    return row


def rma_menu_count(rpc) -> int:
    """How many ``ir.ui.menu`` records the module actually owns.

    The workbook says three actions are "exposed" by the menu; the module
    defines ONE menuitem (``views/stock_picking.xml:138-140``). TC188
    records the divergence rather than asserting the workbook's phrasing
    against a record set that cannot satisfy it.
    """
    return len(rpc.search("ir.model.data",
                          [("model", "=", "ir.ui.menu"),
                           ("module", "=", MODULE)]))


def act_window_row(rpc, xmlid: str) -> dict | None:
    """One RMA act_window's assertable fields, including its raw domain."""
    action_id = rpc.ref(xmlid)
    if not action_id:
        return None
    fields_ = ["name", "res_model", "domain", "view_mode", "context",
               "search_view_id", act_window_groups_field(rpc)]
    row = rpc.read("ir.actions.act_window", [action_id], fields_)[0]
    row["xmlid"] = xmlid
    return row


def available_view_types(rpc) -> list:
    """``ir.ui.view.type``'s selection keys on the target.

    TC188 step 8 checks every mode named in ``view_mode`` against this list.
    ``'tree'`` is present on v17 (``ir_ui_view.py:163``) and ABSENT on v19
    (``:149``), which is why the step is expected to fail there.
    """
    return [key for key, _label in selection_of(rpc, "ir.ui.view", "type")]


def queue_members(rpc, domain_str: str, scope_ids) -> list[int]:
    """Run an act_window's own domain, scoped to this execution's fixtures.

    ``domain_str`` is read verbatim off the ``ir.actions.act_window`` record
    and never retyped, so the test measures the shipped domain. The
    ``('id','in', scope_ids)`` clause is convention rule 5: the live all-RMAs
    queue contains production returns, so membership is asserted over the
    fixtures and never as "exactly N rows".
    """
    from ast import literal_eval
    domain = literal_eval(domain_str) if domain_str else []
    domain = list(domain) + [("id", "in", list(scope_ids))]
    return rpc.search("stock.picking", domain)


def domain_has_literal_location_id(domain_str: str) -> bool:
    """True when the domain pins a location to a bare integer.

    TC190 step 12 — the assertion that turns green when the fix lands.
    ``('location_id','=',5)`` and ``('location_dest_id','=',4)`` are literal
    integers in ``views/stock_picking.xml:85,106``; after the fix they must
    resolve from ``ref('stock.stock_location_customers')`` /
    ``ref('stock.stock_location_suppliers')``, at which point no integer
    literal remains in the domain text.
    """
    if not domain_str:
        return False
    return bool(re.search(
        r"'(location_id|location_dest_id)'\s*,\s*'='\s*,\s*\d+", domain_str))


# =====================================================================
# TC044 — the RMA sequence reconciliation capture
# =====================================================================
def rma_sequence_row(ctx) -> dict:
    """The ``ir.sequence`` definition, as TC044 step 1 selects it.

    ``number_next_actual`` is read alongside ``number_next`` because for
    ``implementation='standard'`` the live counter lives in the PostgreSQL
    sequence ``ir_sequence_%03d``, not in the column: ``_next_do`` calls
    ``_select_nextval`` (v17 ``ir_sequence.py:202-207``) and
    ``number_next_actual`` is computed by ``_predict_nextval``
    (``:64-84``, ``:100-110``). That is TC044 step 2's value, reached through
    the ORM instead of ``\\gexec``.
    """
    rpc = ctx.adapter.rpc
    seq_id = require_rma_sequence(ctx)
    row = rpc.read("ir.sequence", [seq_id],
                   ["code", "name", "prefix", "suffix", "padding",
                    "number_next", "number_next_actual", "number_increment",
                    "implementation", "company_id", "use_date_range",
                    "active"])[0]
    row["company_id"] = m2o_id(row["company_id"]) or False
    row["suffix"] = row.get("suffix") or False
    return row


def sequence_preview(rpc, seq_id: int, number_next: int) -> str:
    """``ir.sequence.get_next_char(n)`` — renders without consuming.

    Public on both versions (v17 ``:241-243``, v19 ``:240-242``) and its body
    is ``interpolated_prefix + '%%0%sd' % padding % number_next +
    interpolated_suffix`` — no write anywhere. This is how TC184 step 13
    proves ``<year>-1000`` without touching ``number_next`` on the shared
    global sequence (convention rule 3).
    """
    return rpc.call("ir.sequence", "get_next_char", [seq_id], number_next)


def rma_number_population(rpc) -> list[str]:
    """Every ``rma_number`` already issued on the target. READ-ONLY."""
    rows = rpc.search_read("stock.picking",
                           [("rma_number", "!=", False)],
                           ["rma_number"], order="id")
    return [r["rma_number"] for r in rows if r.get("rma_number")]


def rma_sequence_capture(ctx) -> dict:
    """The TC044 snapshot, for ``fg_common.reconcile``.

    Covers workbook steps 1-5 and 8 through the ORM. **Adaptation, recorded
    in the plan doc, not a weakening:** the workbook writes the case as raw
    SQL, but every figure it selects is ORM-reachable —
    ``number_next_actual`` IS ``_predict_nextval`` over ``pg_sequences``
    (``ir_sequence.py:64-84``) — so the case does not need ``pg_*``
    credentials and cannot report BLOCKED for their absence. This is the
    same adaptation WF-013 made for its fourteen reconciliation cases.

    **Step 6 is deliberately NOT executed.** It allocates a number in a
    rolled-back transaction; ``ctx.sql`` is read-only by contract
    (``framework/sqltool.py`` opens the connection with
    ``default_transaction_read_only=on``) and the workbook itself records
    that the counter advances anyway. It stays a Phase-0a manual step.

    Keys ``issued_by_year``, ``duplicates`` and ``four_digit`` are the
    diffable population facts; ``no_collision`` is step 5's boolean.
    """
    row = rma_sequence_row(ctx)
    numbers = rma_number_population(ctx.adapter.rpc)

    by_year: dict = {}
    for number in numbers:
        if not re.match(r"^\d{4}-\d+$", number):
            continue
        year, _, serial = number.partition("-")
        bucket = by_year.setdefault(year, {"issued": 0, "min": number,
                                           "max": number, "max_serial": 0})
        bucket["issued"] += 1
        bucket["min"] = min(bucket["min"], number)
        bucket["max"] = max(bucket["max"], number)
        bucket["max_serial"] = max(bucket["max_serial"], int(serial))

    seen: dict = {}
    for number in numbers:
        seen[number] = seen.get(number, 0) + 1
    duplicates = sorted(n for n, count in seen.items() if count > 1)

    capture = dict(row)
    capture["issued_total"] = len(numbers)
    capture["issued_by_year"] = {y: by_year[y] for y in sorted(by_year)}
    capture["duplicates"] = duplicates
    capture["four_digit"] = sorted(n for n in numbers
                                   if RMA_OVERFLOW_RE.match(n))
    capture["malformed"] = sorted(n for n in numbers
                                  if not re.match(r"^\d{4}-\d+$", n))
    capture["no_collision"] = no_collision(capture)
    return capture


def no_collision(capture: dict) -> bool:
    """TC044 step 5, measured on the column that actually moves.

    The workbook's SQL compares ``number_next`` against the highest serial
    issued this year. For ``implementation='standard'`` ``number_next`` never
    moves (``ir_sequence.py:202-207``), so the comparison is made against
    ``number_next_actual`` — the value the next ``next_by_code`` will
    actually render — while ``number_next`` is still carried in the snapshot
    so the workbook's own figure is recorded, not discarded.

    The year is the prefix the sequence itself will interpolate:
    ``%(year)s`` resolves to ``effective_date.strftime('%Y')`` in the context
    timezone (v17 ``ir_sequence.py:213-230``), and the capture reads the
    years straight out of the issued population rather than from the
    platform host's clock.
    """
    years = capture.get("issued_by_year") or {}
    if not years:
        return True
    latest = max(years)
    nxt = capture.get("number_next_actual") or capture.get("number_next") or 0
    return nxt > years[latest]["max_serial"]


# =====================================================================
# TC044 — what may and may not be cross-version DIFFED
#
# Everything below is appended at the END of this module on purpose:
# tests/wf011/test_reconciliation.py:139,400 cites this file by line
# number (``common.py:1722-1727`` and ``:1771``) and that suite is
# outside WF-024's write scope, so nothing may be inserted above them.
# =====================================================================

#: Snapshot keys that are NOT diffable across environments.
#:
#: ``number_next_actual`` is ``_predict_nextval`` over the PostgreSQL
#: sequence ``ir_sequence_%03d`` (v17 ``ir_sequence.py:64-84``,
#: ``:100-110``). A PostgreSQL sequence is **never rolled back**, and this
#: suite itself consumes roughly a dozen numbers from the live global
#: ``rma_number`` series on every execution — TC184 creates two returns,
#: TC185 two, TC186 one, TC187 one, TC188 two, TC189 two, TC190 two, each
#: through the real wizard, whose ``_create_return`` calls
#: ``next_by_code('rma_number')``
#: (``stock_picking_auto_create_lot/wizard/stock_picking_return.py:23``,
#: ``models/stock_picking.py:42-44``). The sweep deletes the pickings, so
#: ``issued_total`` / ``issued_by_year`` / ``duplicates`` return to their
#: pre-run values; the counter does not. Diffing it would therefore report
#: ``number_next_actual: baseline=N current=N+13`` on **every** v19 run —
#: a false positive manufactured by the suite, reading exactly like the
#: silent counter reset/jump TC044 exists to catch (convention rule 5).
#:
#: ``number_next`` IS diffed and stays in the snapshot: for
#: ``implementation='standard'`` ``_next_do`` allocates through
#: ``_select_nextval`` and never writes the column (v17 ``:202-207``,
#: v19 ``:200-205``), so it cannot move when a number is issued. It moves
#: only when someone writes it — a module update with ``noupdate=False``
#: (``data/rma_sequence.xml:10``) or the ir.sequence form's "Next Number"
#: inverse ``_set_number_next_actual`` (v17 ``:110-112``) — which is
#: precisely the finding this case must report, not suppress.
#:
#: What replaces the diffed counter is the DIRECTIONAL assertion in
#: ``test_reconciliation.py`` step 7: the live counter must still be ahead
#: of every serial the v17 baseline recorded as issued. That is the
#: workbook's "the RMA series continues from where v17 left it, with no
#: duplicate and no reset" — and, unlike an equality diff, consuming
#: numbers can only ever make it *more* true. Plan adaptation 18.
RMA_COUNTER_KEYS = ("number_next_actual",)


def rma_sequence_diffable(capture: dict) -> dict:
    """The part of ``rma_sequence_capture`` that is stable across runs.

    Handed to ``fg_common.reconcile``; ``framework/baselines.py:47-54``
    ``diff_counts`` compares **every** key of what it is given, so a
    non-deterministic value must be removed before it is passed, not
    filtered afterwards.
    """
    return {key: value for key, value in (capture or {}).items()
            if key not in RMA_COUNTER_KEYS}


def max_issued_serial(snapshot: dict) -> int:
    """The highest ``nnn`` of ``YYYY-nnn`` recorded in a capture/baseline.

    Reads ``issued_by_year`` — a diffed, deterministic key — so it means
    the same thing whether it is given this run's capture or the stored
    v17 baseline's ``data``.
    """
    years = (snapshot or {}).get("issued_by_year") or {}
    return max((bucket.get("max_serial") or 0
                for bucket in years.values() if isinstance(bucket, dict)),
               default=0)


# =====================================================================
# Disposable-user teardown
# =====================================================================
def archive_qa_users(ctx, suffixes) -> list:
    """Archive the ``qa.wf024.<suffix>`` users a case created.

    ``ensure_user_in_groups`` creates internal users with a known password
    (``QA_PASSWORD``), and ``sweep_wf024`` deliberately cannot remove them:
    its ``res.partner`` step is guarded with ``("user_ids", "=", False)``
    so a user's partner survives. Leaving them active leaves live logins on
    the QA clone after every run, which is inconsistent with the
    convention's "fixtures … cleaned in a ``finally`` step".

    They are **archived, never unlinked**: each one owns chatter messages
    on the fixture pickings, and ``res.users.unlink`` would have to cascade
    through them.

    Contract: called from a ``finally:``, therefore **cannot raise**.
    """
    archived = []
    try:
        rpc = ctx.adapter.rpc
    except Exception:                                   # noqa: BLE001
        return archived
    for suffix in suffixes or []:
        login = f"qa.wf024.{suffix}"
        try:
            found = rpc.search("res.users",
                               [("login", "=", login), ("active", "=", True)],
                               limit=1)
            if found:
                rpc.write("res.users", found, {"active": False})
                archived.append(found[0])
        except Exception as exc:                        # noqa: BLE001
            try:
                ctx.log(f"[warn] QA user {login} not archived: {exc}")
            except Exception:                           # noqa: BLE001
                pass
    return archived
