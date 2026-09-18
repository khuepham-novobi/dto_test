"""DATAONE-WF-021 — Cycle Counting and Inventory Adjustment: shared fixtures.

Everything below was read out of the real source before a single line here
was written (AUTOMATION_CONVENTIONS hard rule 6). ``main`` is the Odoo 17
baseline branch of ``DTO-Odoo``; the working tree is checked out on ``UAT``,
which already carries the v19 port — see "The checkout trap" below, because
it decides how every source-side claim in this suite must be read.

Read before writing
===================

``dto_cycle_count`` — the module WF-021 is about
-----------------------------------------------
``__manifest__.py`` — v17 ``'version': '17.0.0.0'`` (``main:7``), depends on
``web, stock, sale, product, dto_base`` (``main:12-22``); ships
``security/ir.model.access.csv``, ``data/cycle_count_category_data.xml`` and
four view files (``main:24-42``) — **no cron, no server action, no record
rule, no new group** (BR-7).

``models/cycle_count_category.py`` (v17 ``main``)::

    _name = 'cycle.count.category'                                    # :10
    _description = 'Cycle Count Category'                             # :11
    _order = 'id'                                                     # :12
    name            = fields.Char('Name', required=True)              # :14
    interval_number = fields.Integer('Interval Number', required=True)  # :15
    interval_type   = fields.Selection([('days','Days'),('weeks','Weeks'),
                                        ('months','Months')],
                          string='Interval Unit', default='days',
                          required=True)                              # :16-20

    def _calculate_scheduled_count_date(self, last_count_date):       # :22
        self.ensure_one()                                             # :23
        if not last_count_date:
            last_count_date = fields.Date.today()                     # :24-25
        return last_count_date + relativedelta(
            **{self.interval_type: self.interval_number})              # :26

That method is **private** and therefore not dispatchable over
``/web/dataset/call_kw`` — ``odoo/models.py:143`` ``regex_private =
re.compile(r'^(_.*|init)$')``, raised at ``:145-148``. Its arithmetic is
reached in this suite through two PUBLIC surfaces only: ``onchange`` (v17
``odoo/models.py:7010``, implemented in ``addons/web/models/models.py:895``)
and the records ``action_apply_inventory`` leaves behind. It is never
re-implemented as the source of an assertion; ``add_interval`` below exists
solely to compute the *expected* value the workbook states in BR-2.

``data/cycle_count_category_data.xml`` — ``<data noupdate="1">`` at ``:3``,
five records at ``:5-33``: Level A 1/days, Level B 1/weeks, Level C 1/months,
Level D 4/months, Level E 6/months. ``noupdate`` means in-database additions
and edits survive an upgrade, so this suite asserts the five **by xmlid**
and never asserts a global ``count == 5``.

``models/product_product.py`` (v17 ``main``)::

    cycle_count_category_id = fields.Many2one('cycle.count.category',
                                  copy=False, tracking=True)           # :13
    last_count_date      = fields.Date('Last Count Date', copy=False,
                              default=_default_last_count_date)        # :14
    scheduled_count_date = fields.Date('Scheduled Count Date',
                              copy=False)                              # :15

    @api.onchange('categ_id')                                          # :20
    def _onchange_categ_id(self):
        if not self.cycle_count_category_id \\
                and self.categ_id.name == 'Finished Goods':            # :22
            self.cycle_count_category_id = self.env.ref(
                'dto_cycle_count.cycle_count_category_level_d').id     # :23

    @api.onchange('cycle_count_category_id', 'last_count_date')        # :25
    def _onchange_cycle_count_category_id(self):
        cycle_count = self.cycle_count_category_id
        if cycle_count and self.last_count_date:                       # :28
            self.scheduled_count_date = \\
                cycle_count._calculate_scheduled_count_date(
                    self.last_count_date)                              # :29

    @api.onchange('type')                                              # :31
    def _onchange_type(self):
        res = super()._onchange_type()                                 # :33
        if self.type != 'product':   -> clear the three fields         # :34-39
        if self.type == 'product':   -> restore them from self._origin # :41-46

    def write(self, vals):                                             # :53
        res = super().write(vals)                                      # :54
        if 'cycle_count_category_id' in vals:                          # :57
            for quant in self.stock_quant_ids.sudo():                  # :58-59
                quant.inventory_date = quant.cycle_count_category_id \\
                    ._calculate_scheduled_count_date(quant.last_count_date)  # :60

    @api.model_create_multi                                            # :63
    def create(self, vals):
        records = super().create(vals)                                 # :65
        cycle_count_d = self.env.ref(
            'dto_cycle_count.cycle_count_category_level_d')            # :67
        for product in records:                                        # :68
            if not product.cycle_count_category_id \\
                    and product.categ_id.name == 'Finished Goods':     # :69
                product.write({'cycle_count_category_id':
                               cycle_count_d.id})                      # :70

Two consequences this suite depends on and asserts rather than assumes:

* the Finished-Goods rule is an **exact, case- and whitespace-sensitive
  Python string compare** in four places (``product_product.py:22``, ``:69``;
  ``product_template.py:69``), so ``"Finished Goods "`` with a trailing space
  does not match — TC170 step 9;
* ``write``'s gate is ``'cycle_count_category_id' in vals`` — **key
  presence, not value change** (``:57``), so re-writing the same level
  re-runs the whole quant loop.

``models/product_template.py`` (v17 ``main``) — ``cycle_count_category_id``
(``:13-14``), ``last_count_date`` (``:17-18``) and ``scheduled_count_date``
(``:19-20``) are compute/inverse/search triples with **no** ``store=True``,
so they have **no SQL column**. The only stored template column is
``variant_cycle_count_category_id`` (``:15-16``, ``related=
'product_variant_id.cycle_count_category_id', store=True``). That is why
TC055's workbook SQL against ``product_template.cycle_count_category_id`` is
invalid and is corrected here (see ``SQL_*`` below). The core helpers the
triples lean on exist in both versions:
``_compute_template_field_from_variant_field`` (v17
``product/models/product_template.py:238``, v19 ``:269``),
``_set_product_variant_field`` (v17 ``:261``, v19 ``:292``),
``_get_related_fields_variant_template`` (v17 ``:477``, v19 ``:509``).

``models/stock_quant.py`` (v17 ``main``)::

    cycle_count_category_id = fields.Many2one('cycle.count.category',
        related='product_id.cycle_count_category_id', store=True)      # :13-14
    last_count_date = fields.Date(compute=False,
        default=_default_last_count_date)                              # :15

    def _apply_inventory(self):                                        # :17
        res = super()._apply_inventory()                               # :18
        for quant in self:
            last_count_date = fields.Date.today()                      # :20
            scheduled_count_date = quant.cycle_count_category_id \\
                ._calculate_scheduled_count_date(last_count_date)      # :21
            quant.product_id.write({'last_count_date': ...,
                                    'scheduled_count_date': ...})      # :22-25
            quant.write({'last_count_date': ...,
                         'inventory_date': scheduled_count_date})      # :26-29

``last_count_date`` is core's **non-stored** compute in v17
(``stock/models/stock_quant.py:114``, compute at ``:133-179``); the module
redefines it ``compute=False``, which is what makes ``stock_quant.
last_count_date`` a real, writable SQL column on the target. Note ``:21``
reads the level off the **quant's** stored related field, and
``_calculate_scheduled_count_date`` opens with ``ensure_one()`` — so
applying a count on a quant whose product carries **no** level raises
``ValueError: Expected singleton: cycle.count.category()``. Every fixture
product in this suite therefore carries a level unless a case is
specifically about the levelless path.

Core ``stock.quant`` facts the suite asserts against (Odoo 17)
--------------------------------------------------------------
* ``_apply_inventory(self)`` — ``stock/models/stock_quant.py:1050``; it takes
  **no ``date`` argument** on v17 (v19: ``def _apply_inventory(self,
  date=None)`` at ``:996``). There is therefore no back-date input on the
  baseline, which is why TC174's absolute dates are asserted relationally.
* the v17 manager gate, verbatim at ``:1052-1053``::

      if not self.user_has_groups('stock.group_stock_manager'):
          raise UserError(_('Only a stock manager can validate an inventory adjustment.'))

  **Removed in v19** (no gate in ``:996-1035``).
* ``action_apply_inventory(self)`` — PUBLIC, ``:445``. It **returns a wizard
  dict instead of applying** when any quant ``is_outdated``
  (``stock.inventory.conflict``, ``:461-470``) or a lot/serial product has
  no lot (``stock.track.confirmation``, ``:471-480``). It only reaches
  ``self._apply_inventory()`` at ``:483``. A test must assert the return is
  falsy or it has silently asserted nothing — ``apply_count`` below returns
  it for exactly that reason.
* no zero-variance skip on v17: the ``if/else`` on ``float_compare(
  inventory_diff_quantity, 0) > 0`` appends a ``move_val`` on **both**
  branches (``:1056-1066``). A zero-variance count *does* produce a
  zero-quantity move line on v17 — the workbook's A3 is corrected in TC174's
  docstring, and the half this workflow owns ("the next count is still
  booked") holds.
* ``_apply_inventory`` ends by writing ``quant.inventory_date =
  date_by_location[quant.location_id]`` (``:1071-1072``) and then
  ``action_clear_inventory_quantity()`` (``:1073``) — the DataOne override
  rewrites that ``inventory_date`` afterwards. That ordering is the point of
  the case.
* ``_is_inventory_mode()`` = ``context.get('inventory_mode') and
  user_has_groups('stock.group_stock_user')`` (``:1230-1235``).
* ``_get_forbidden_fields_write()`` = ``['product_id','location_id','lot_id',
  'package_id','owner_id']`` (``:360-362``) — ``inventory_quantity``,
  ``last_count_date`` and ``inventory_date`` are **not** restricted.
* ``inventory_diff_quantity`` = ``inventory_quantity - quantity``, stored
  compute (``:105-108``, compute ``:189-192``).
* ``inventory_quantity_auto_apply`` carries ``groups=
  'stock.group_stock_manager'`` (``:102-106``); ``inventory_quantity`` has no
  ``groups`` (``:99-101``).
* ``cyclic_inventory_frequency`` is a **non-stored** related
  (``related='location_id.cyclic_inventory_frequency'``, ``:65``) — it has no
  column, which is TC055 step 3's workbook error.
* the real count-sheet gate is the ``to_count`` filter, domain
  ``[('inventory_date','<=', context_today().strftime('%Y-%m-%d'))]`` —
  ``stock/views/stock_quant_views.xml:37``. The Physical Inventory action's
  own domain is only ``[('location_id.usage','in',['internal','transit'])]``
  (``stock/models/stock_quant.py:432``). ``due_on()`` below implements the
  filter, so no test ever "sets the working date".
* unlinking a quant is not free: ``_unlink_except_wrong_permission``
  (``:375-382``) sets ``inventory_quantity = 0`` and calls
  ``_apply_inventory()``, which re-enters the DataOne override. The sweep
  below is written around that.

Core product / category facts
-----------------------------
* v17 storable: ``product.template.type`` gains ``('product','Storable
  Product')`` via ``selection_add`` — ``stock/models/product.py:661-663``
  (``detailed_type`` likewise at ``:658-660``). v19's selection is exactly
  ``[('consu','Goods'),('service','Service'),('combo','Combo')]``
  (``product/models/product_template.py:54-65``) and **no v19 addon re-adds
  ``'product'``** (grep over ``addons/*/models/*.py``: zero hits).
  Storability moved to ``is_storable`` (``stock/models/product.py:829-831``).
  Route it through ``ctx.adapter.storable_product_values()``.
* ``product.category.name`` is ``fields.Char('Name', index='trigram',
  required=True)`` — **not translatable** in v17
  (``product/models/product_category.py:16``) or v19 (``:17``), so the column
  is ``varchar`` and TC055 step 5's ``name->>'en_US'`` is invalid SQL. There
  is no unique constraint on it, which is what makes TC170's namespaced
  duplicate legal.
* ``product.product.stock_quant_ids`` is core ``One2many('stock.quant',
  'product_id')`` — v17 ``stock/models/product.py:29``, v19 ``:50``.
* ``product.template.property_stock_inventory`` is
  ``company_dependent=True`` (``stock/models/product.py:668``).
* ``_onchange_type`` still exists on core ``product.template`` in **both**
  versions — v17 ``product/models/product_template.py:459`` +
  ``stock/models/product.py:861``; v19 ``product/models/product_template.py
  :460`` + ``stock/models/product.py:1089``. TC177 step 11's premise is
  therefore verified, not assumed.

Security
--------
``dto_cycle_count/security/ir.model.access.csv`` — exactly two rows,
byte-identical in both versions (``main:2-3``)::

    access_cycle_count_category_user,…,base.group_user,1,0,0,0
    access_cycle_count_category_manager,…,stock.group_stock_manager,1,1,1,1

The core ACL delta that governs TC174/TC175: **v17** grants
``stock.group_stock_manager`` 1,1,1,1 on ``product.template`` and
``product.product`` (``stock/security/ir.model.access.csv:21-22``); **v19
deletes both rows**, leaving only the ``stock.group_stock_user`` 1,0,0,0
rows (v19 ``:15-16``). That is why the un-sudoed
``quant.product_id.write(...)`` inside ``_apply_inventory`` succeeds for a
stock manager on v17 and the v19 port had to add ``.sudo()``.

``dto_account`` — the TC251 carrier
-----------------------------------
``models/stock_location.py`` (v17 ``main:7-11``)::

    _name    = 'stock.location'
    _inherit = ['stock.location', 'analytic.mixin']
    location_analytic_distribution = fields.Json(string='Analytic Distribution')

``models/stock_move.py:24-46`` overrides ``_account_entry_move(self, qty,
description, svl_id, cost)`` — **private**, so only its output is
observable. It bails out when ``len(virtual_locations) != 1`` or the
location has no distribution (``:32-33``), and tags only lines whose
``account_id`` is the virtual location's ``valuation_in_account_id`` **or**
``valuation_out_account_id`` (``:40``).

Core v17 ``stock_account`` decides which of those two it is, and the
workbook has it backwards:

* **decrease / write-off** — internal → inventory-loss, ``_is_out()``; core
  posts ``_prepare_account_move_vals(acc_valuation, acc_dest, …)``
  (``stock_account/models/stock_move.py:592``) where ``acc_dest`` =
  ``_get_dest_account`` = ``location_dest_id.``**``valuation_in_account_id``**
  (``:395-399``);
* **increase** — inventory-loss → internal, ``_is_in()``; core posts
  ``(acc_src, acc_valuation)`` (``:584``) where ``acc_src`` =
  ``_get_src_account`` = ``location_id.``**``valuation_out_account_id``**
  (``:392-393``).

So TD-L-06 must carry **both** accounts or one of the two directions
silently produces an untagged line — ``make_virtual_inventory_location``
below sets both. Also note the early bail
``if self.product_id.type != 'product': return []`` (``:568-570``): on v17
the fixture product must be storable, and ``_generate_valuation_lines_data``
returns exactly ``credit_line_vals`` + ``debit_line_vals`` (``:469-516``),
so the entry has exactly two lines.

The checkout trap — read this before any source grep
====================================================
``git -C DTO-Odoo rev-parse --abbrev-ref HEAD`` returns **``UAT``**, which
has merged ``stage4/inventory-controls``: the working tree already contains
the **v19 port** of ``dto_cycle_count`` (``__manifest__.py:10`` →
``'version': '19.0.0.0'``; ``models/stock_quant.py:23`` → ``def
_apply_inventory(self, date=None)``; ``views/product_product_views.xml:18``
→ ``invisible="not is_storable"``). The v17 baseline is git history on
``main``, which is what every ``main:`` citation above was read from.

Therefore a ``framework.source_scan`` grep of the checkout is **evidence
about the checkout, not about the running server**. The authority for what
the target actually serves is the rendered arch from ``get_view`` and
``fields_get`` — ``scan_cycle_count`` below returns the checked-out branch
alongside its hits so a case can never confuse the two, and
``is_v19_product_shape`` probes the server directly.

Nothing here reaches an external system
=======================================
The workflow sheet's *Integrations* section is literally "None", and the
*Notifications* section records that the descoped flow "posts nothing,
emails nothing and schedules no activity". ``dto_cycle_count`` ships no
cron, no server action and no mail template. ``require_mail_offline`` is not
needed by this suite and no blocked stub is warranted anywhere in it
(convention rule 4 is satisfied by construction, not by a guard).
"""
from __future__ import annotations

import calendar
import copy
import datetime
import uuid
import xml.etree.ElementTree as ET

from adapters.base import OdooRPC, OdooRPCError  # noqa: F401 — re-exported
from framework.fg_common import (form_arch, list_tag, m2o_id,  # noqa: F401
                                 make_trace, reconcile)
from framework.qa_fixtures import (default_categ_id, sweep_model,  # noqa: F401
                                   sweep_products, user_groups_field,
                                   with_categ)

WORKFLOW = "DATAONE-WF-021"
WORKFLOW_NAME = "Cycle Counting and Inventory Adjustment"
FEATURE = f"{WORKFLOW} {WORKFLOW_NAME}"

trace = make_trace(WORKFLOW)

MARKER = "WF021"
#: One namespace per execution. Every search this suite makes is scoped by
#: it, so live data can never leak into an "exactly N records" assertion and
#: two concurrent runs cannot collide (convention rule 5).
_TOKEN = f"{MARKER}-{uuid.uuid4().hex[:8].upper()}"

MODULE = "dto_cycle_count"
ACCOUNT_MODULE = "dto_account"


def tag(name: str) -> str:
    """Namespace a fixture value for this execution."""
    return f"{_TOKEN} {name}"


def fixture_token() -> str:
    return _TOKEN


def code(label: str) -> str:
    """A ``default_code`` for this execution — what the product sweep keys on."""
    return f"{_TOKEN}-{label}"


# ===========================================================================
# Shipped data — data/cycle_count_category_data.xml:5-33, noupdate="1"
# ===========================================================================
LEVEL_XMLIDS = {
    "A": "dto_cycle_count.cycle_count_category_level_a",
    "B": "dto_cycle_count.cycle_count_category_level_b",
    "C": "dto_cycle_count.cycle_count_category_level_c",
    "D": "dto_cycle_count.cycle_count_category_level_d",
    "E": "dto_cycle_count.cycle_count_category_level_e",
}
LEVEL_D_XMLID = LEVEL_XMLIDS["D"]

#: (key, name, interval_number, interval_type) in ``_order = 'id'`` order —
#: cycle_count_category.py:12, data file :5-33. BR-1.
SHIPPED_LEVELS = (
    ("A", "Level A", 1, "days"),
    ("B", "Level B", 1, "weeks"),
    ("C", "Level C", 1, "months"),
    ("D", "Level D", 4, "months"),
    ("E", "Level E", 6, "months"),
)

#: cycle_count_category.py:16-20 — verbatim keys and labels.
INTERVAL_TYPE_SELECTION = [("days", "Days"), ("weeks", "Weeks"),
                           ("months", "Months")]

#: The workbook's worked example. These are SUPPLIED dates, so nothing here
#: depends on the system clock (convention rule 5). TC169 steps 5-10,
#: TC173 steps 2-8.
FIXED_COUNT_DATE = "2026-08-20"
SCHEDULED_FROM_FIXED = {
    "A": "2026-08-21",
    "B": "2026-08-27",
    "C": "2026-09-20",
    "D": "2026-12-20",
    "E": "2027-02-20",
}
#: TC173 steps 9-10 — the second worked example.
SECOND_COUNT_DATE = "2026-08-21"
SECOND_SCHEDULED_LEVEL_B = "2026-08-28"

#: product_product.py:22,69 / product_template.py:69 — compared with ``==``,
#: so case and whitespace are load-bearing. BR-4.
FINISHED_GOODS_NAME = "Finished Goods"
#: TC170 step 9's fragility probe: one trailing space, which must NOT match.
FINISHED_GOODS_TRAILING_SPACE = "Finished Goods "

#: The three fields the module adds to both product models.
CYCLE_COUNT_FIELDS = ["cycle_count_category_id", "last_count_date",
                      "scheduled_count_date"]
#: The stored mirror on product.template — product_template.py:15-16.
TEMPLATE_VARIANT_LEVEL_FIELD = "variant_cycle_count_category_id"

#: Core inventory-adjustment fields TC174 reads back.
QUANT_INVENTORY_FIELDS = ["inventory_quantity", "inventory_diff_quantity",
                          "inventory_date", "inventory_quantity_set",
                          "last_count_date", "cycle_count_category_id",
                          "quantity"]


# ===========================================================================
# Verbatim error strings — read from the source, never paraphrased
# ===========================================================================
#: v17 stock/models/stock_quant.py:1052 — REMOVED in v19.
ERROR_ONLY_STOCK_MANAGER = (
    "Only a stock manager can validate an inventory adjustment.")
#: cycle_count_category.py:23 — ``ensure_one()`` on a levelless product's
#: quant. Matched as a fragment: the ORM appends the empty recordset repr.
SINGLETON_ERROR_FRAGMENT = "Expected singleton"

#: The [HOLD] approval half. dto_tier_validation_quant is installed on the
#: target (its ``state`` and ``valuation_discrepancy`` columns exist) but
#: ``tier_definition`` holds 0 rows, so ``need_validation`` is always False
#: and flow A1 — "Apply is present and immediate" — is the live path.
#: Recorded verbatim so a future APR suite need not re-derive them; NOT
#: asserted anywhere in WF-021.
TIER_ERROR_NO_REQUEST = "No records need to request validation."      # :87
TIER_ERROR_NO_VALIDATE = "No records need to validate validation."    # :94
TIER_ERROR_NO_REJECT = "No records need to reject validation."        # :101
#: base_tier_validation/models/tier_validation.py:350-354 — note the literal
#: newline between the two sentences.
TIER_ERROR_NEEDS_VALIDATION = (
    "This action needs to be validated for at least one record. \n"
    "Please request a validation.")
#: :357-361
TIER_ERROR_STILL_OPEN = (
    "A validation process is still open for at least one record.")


# ===========================================================================
# View inventory — xmlids and the exact injected arch
# ===========================================================================
VIEW_PRODUCT_FORM = "product.product_normal_form_view"
VIEW_TEMPLATE_FORM = "product.product_template_only_form_view"
VIEW_PRODUCT_SEARCH = "product.product_search_form_view"
VIEW_TEMPLATE_SEARCH = "stock.product_template_search_form_view_stock"
VIEW_QUANT_INVENTORY_LIST = "stock.view_stock_quant_tree_inventory_editable"
VIEW_QUANT_SEARCH = "stock.quant_search_view"
VIEW_QUANT_FORM = "stock.view_stock_quant_form_editable"

#: The module's own records — cycle_count_category_views.xml:4-55.
VIEW_LEVEL_FORM = "dto_cycle_count.view_cycle_count_category_form"
VIEW_LEVEL_LIST = "dto_cycle_count.view_cycle_count_category_tree"
VIEW_LEVEL_SEARCH = "dto_cycle_count.view_cycle_count_category_search"
ACTION_LEVELS = "dto_cycle_count.action_cycle_count_category"
MENU_LEVELS = "dto_cycle_count.menu_cycle_count_category"
MENU_LEVELS_PARENT = "stock.menu_product_in_config_stock"

CYCLE_COUNT_GROUP = "cycle_count"       # the injected <group name=...>
TRACEABILITY_GROUP = "traceability"     # the anchor it sits after

#: Group-by filter names. product_product_views.xml:28,
#: product_template_views.xml:28, stock_quant_views.xml:24.
PRODUCT_GROUPBY_FILTER = "cycle_count_category_id"
TEMPLATE_GROUPBY_FILTER = "variant_cycle_count_category_id"
QUANT_GROUPBY_FILTER = "cycle_count_category_group"

#: Search ``filter_domain`` attributes, verbatim.
#: product_product_views.xml:25 searches the PRODUCT's own ``name``, not the
#: category — defect D-new-6, deliberately preserved by the v19 port. TC176
#: step 6 asserts the attribute literally and must NOT assert that a
#: category-name search works through it.
PRODUCT_SEARCH_FILTER_DOMAIN = "[('name', 'ilike', self)]"
#: product_template_views.xml:25 and stock_quant_views.xml:21 — correct.
CATEGORY_SEARCH_FILTER_DOMAIN = "[('cycle_count_category_id', 'ilike', self)]"

#: The eight ``type == 'product'`` sites TC177 inventories — four XML
#: modifiers and two Python branches, counted per occurrence.
#: Left column: the v17 expression on ``main``. Right: the v19 port in the
#: working tree. TC177 is the sanctioned ``ctx.env.version`` exception
#: (AUTOMATION_CONVENTIONS:143-149) because its SUBJECT is this delta.
STORABLE_MODIFIERS = {
    "17": {
        "group_invisible": "type != 'product'",
        "field_required": "type == 'product'",
    },
    "19": {
        "group_invisible": "not is_storable",
        "field_required": "is_storable",
    },
}
#: product_template_views.xml:10 — the template group carries two extra
#: disjuncts on top of the storable test (A5 / TC176 step 3).
TEMPLATE_GROUP_EXTRA_INVISIBLE = (
    "product_variant_count > 1 or (product_variant_count == 0 and "
    "valid_product_template_attribute_line_ids)")

#: Where the literal lives, for the plan doc and TC177's inventory.
MODIFIER_SITES = (
    ("views/product_product_views.xml", 10, "group invisible"),
    ("views/product_product_views.xml", 11, "field required"),
    ("views/product_template_views.xml", 10, "group invisible"),
    ("views/product_template_views.xml", 11, "field required"),
    ("models/product_product.py", 34, "_onchange_type clear branch"),
    ("models/product_product.py", 41, "_onchange_type restore branch"),
    ("models/product_template.py", 81, "_onchange_type clear branch"),
    ("models/product_template.py", 88, "_onchange_type restore branch"),
)


# ===========================================================================
# Groups and ACLs
# ===========================================================================
GROUP_USER = "base.group_user"
GROUP_STOCK_USER = "stock.group_stock_user"
GROUP_STOCK_MANAGER = "stock.group_stock_manager"

#: Test-only credential for the disposable QA clone databases.
WF021_PASSWORD = "QaAuto-2026!"


# ===========================================================================
# Corrected SQL for TC055 — three workbook statements are invalid against
# the real schema. The workbook's EXPECTED RESULT ("all diffs empty") is
# untouched; only the statements that would raise are corrected, and each
# correction is named here so the docstring can cite it.
# ===========================================================================

#: Step 1 — the five levels. ``_order = 'id'`` (cycle_count_category.py:12).
SQL_LEVELS = """
SELECT id, name, interval_number, interval_type
FROM cycle_count_category
ORDER BY id
"""

#: Step 2 — assignments per level. ``stock_quant.cycle_count_category_id``
#: IS a real column (stored related, models/stock_quant.py:13-14).
SQL_QUANTS_BY_LEVEL = """
SELECT q.cycle_count_category_id,
       count(*)                     AS quants,
       count(DISTINCT q.product_id) AS products
FROM stock_quant q
GROUP BY 1
ORDER BY 1
"""

#: Step 3 — the scheduling state.
#: WORKBOOK CORRECTION 1: ``q.cyclic_inventory_frequency`` is a NON-STORED
#: related (v17 stock/models/stock_quant.py:65, v19 :63) and has no column;
#: selecting it raises ``UndefinedColumn``. It is dropped.
#: ADAPTATION: the workbook dumps one row per quant. ``stock_quant`` holds
#: 36,147 rows on the target, so the per-quant dump is written to a CSV
#: ARTIFACT (``SQL_QUANT_SCHEDULE_DUMP``) and the value the baseline diff
#: compares is this aggregate, which carries the same information at the
#: granularity a diff can actually report.
SQL_QUANT_SCHEDULE_SUMMARY = """
SELECT q.cycle_count_category_id,
       count(*)                                                 AS quants,
       count(*) FILTER (WHERE q.last_count_date IS NOT NULL)     AS counted,
       count(*) FILTER (WHERE q.inventory_date  IS NOT NULL)     AS scheduled,
       count(*) FILTER (WHERE q.inventory_quantity_set)          AS counting,
       min(q.last_count_date) AS first_count, max(q.last_count_date) AS last_count,
       min(q.inventory_date)  AS first_due,   max(q.inventory_date)  AS last_due
FROM stock_quant q
GROUP BY 1
ORDER BY 1
"""

SQL_QUANT_SCHEDULE_DUMP = """
SELECT q.id, q.product_id, q.location_id, q.cycle_count_category_id,
       q.last_count_date, q.inventory_date, q.inventory_quantity_set
FROM stock_quant q
ORDER BY q.id
"""

#: Step 4 — the product-level assignment.
#: WORKBOOK CORRECTION 2: ``product_template.cycle_count_category_id`` is a
#: compute/inverse/search with no ``store=True``
#: (models/product_template.py:13-14) and has NO column; the same is true of
#: ``last_count_date`` and ``scheduled_count_date`` (:17-20). The level
#: really lives on ``product_product.cycle_count_category_id``
#: (models/product_product.py:13), mirrored onto the template by the stored
#: ``variant_cycle_count_category_id`` (:15-16) and onto the quant by the
#: stored related (models/stock_quant.py:13-14). That answer is step 4's own
#: parenthetical question, so the corrected query supplies it.
SQL_PRODUCT_LEVEL_BY_CATEG = """
SELECT pt.categ_id, pc.complete_name,
       count(*)                                                          AS products,
       count(*) FILTER (WHERE pp.cycle_count_category_id IS NOT NULL)     AS with_level
FROM product_product pp
JOIN product_template pt ON pt.id = pp.product_tmpl_id
JOIN product_category pc ON pc.id = pt.categ_id
GROUP BY 1, 2
ORDER BY 2
"""

#: Step 5 — the literal category name.
#: WORKBOOK CORRECTION 3: ``product_category.name`` is
#: ``fields.Char('Name', index='trigram', required=True)`` and is NOT
#: translatable in v17 (product/models/product_category.py:16) or v19 (:17),
#: so the column is ``varchar`` and ``name->>'en_US'`` raises. Compared as
#: plain text, which is exactly what BR-4's Python ``==`` does.
SQL_FINISHED_GOODS_CATEGORY = """
SELECT id, complete_name, name
FROM product_category
WHERE name = 'Finished Goods' OR complete_name LIKE '%Finished Goods%'
ORDER BY id
"""

#: Step 6 — no quant lost its scheduled date.
SQL_QUANT_SCHEDULED_COUNTS = """
SELECT count(*) FILTER (WHERE inventory_date IS NULL)     AS unscheduled,
       count(*) FILTER (WHERE inventory_date IS NOT NULL) AS scheduled
FROM stock_quant
"""

#: TC177 step 12 — the production-impact measure: storable products with no
#: level. The storability predicate is version-shaped, so pick by
#: ``ctx.env.version``; this is the case whose subject IS that delta.
SQL_STORABLE_WITHOUT_LEVEL = {
    "17": """
SELECT count(*)
FROM product_product pp
JOIN product_template pt ON pt.id = pp.product_tmpl_id
WHERE pt.type = 'product' AND pp.cycle_count_category_id IS NULL
""",
    "19": """
SELECT count(*)
FROM product_product pp
JOIN product_template pt ON pt.id = pp.product_tmpl_id
WHERE pt.type = 'consu' AND pt.is_storable AND pp.cycle_count_category_id IS NULL
""",
}

#: The denominator for the same measure.
SQL_STORABLE_TOTAL = {
    "17": """
SELECT count(*)
FROM product_product pp
JOIN product_template pt ON pt.id = pp.product_tmpl_id
WHERE pt.type = 'product'
""",
    "19": """
SELECT count(*)
FROM product_product pp
JOIN product_template pt ON pt.id = pp.product_tmpl_id
WHERE pt.type = 'consu' AND pt.is_storable
""",
}

#: The [HOLD] descoping probe (WF021-README:326-329): 0 tier_definition rows
#: is what makes flow A1 the live path.
SQL_TIER_DEFINITION_COUNT = """
SELECT count(*) FROM tier_definition
"""


# ===========================================================================
# Probes and preconditions — every one produces a precise BLOCKED reason
# ===========================================================================
def is_v19_product_shape(rpc) -> bool:
    """True when the TARGET SERVER carries ``product.template.is_storable``.

    The checked-out source cannot answer this (see "The checkout trap" in the
    module docstring): the working tree is the v19 port while the server may
    be running the v17 code. ``is_storable`` does not exist in v17 ``stock``,
    so this probe is decisive — and it is a probe, not an assumption.
    """
    return rpc.field_exists("product.template", "is_storable")


def require_cycle_count(ctx):
    """BLOCK unless dto_cycle_count is contributing to the target."""
    rpc = ctx.adapter.rpc
    missing = []
    if not rpc.model_exists("cycle.count.category"):
        missing.append("model cycle.count.category")
    for model, field in (("product.product", "cycle_count_category_id"),
                         ("product.product", "last_count_date"),
                         ("product.product", "scheduled_count_date"),
                         ("product.template", TEMPLATE_VARIANT_LEVEL_FIELD),
                         ("stock.quant", "cycle_count_category_id")):
        if not rpc.field_exists(model, field):
            missing.append(f"{model}.{field}")
    if missing:
        ctx.blocked(
            f"dto_cycle_count is not contributing to {ctx.env.key} "
            f"(db={ctx.env.db}) — missing: {', '.join(missing)}. Every "
            "WF-021 assertion is about this module, so there is nothing to "
            "exercise until it is installed.")


def require_shipped_levels(ctx) -> dict:
    """Resolve the five shipped levels by xmlid; BLOCK if any is absent.

    Returns ``{'A': id, …, 'E': id}``. Resolution is by xmlid rather than by
    name or by count because ``data/cycle_count_category_data.xml`` is
    ``noupdate="1"`` (:3): in-database additions survive upgrades, so a
    global ``count == 5`` would be a live-data assertion, not a shipped-data
    one (convention rule 5).
    """
    rpc = ctx.adapter.rpc
    ids, missing = {}, []
    for key, xmlid in LEVEL_XMLIDS.items():
        res = rpc.ref(xmlid)
        if res:
            ids[key] = res
        else:
            missing.append(xmlid)
    if missing:
        ctx.blocked(
            f"These cycle.count.category xmlids do not resolve on "
            f"{ctx.env.key} (db={ctx.env.db}): {', '.join(missing)}. "
            "dto_cycle_count ships them in "
            "data/cycle_count_category_data.xml with noupdate=\"1\", so "
            "their absence means the data file never loaded — the whole "
            "interval arithmetic has no inputs.")
    return ids


def module_level_ids(rpc) -> list[int]:
    """Every cycle.count.category row OWNED by dto_cycle_count.

    Scoped through ``ir.model.data`` so an in-database level added by the
    client (legal under ``noupdate="1"``) never turns a shipped-data
    assertion into a live-data one.
    """
    rows = rpc.search_read("ir.model.data",
                           [("module", "=", MODULE),
                            ("model", "=", "cycle.count.category")],
                           ["res_id", "name"], order="res_id")
    return [r["res_id"] for r in rows]


def require_stock_manager(ctx, rpc=None):
    """BLOCK unless the acting user can apply an inventory adjustment.

    v17 ``stock/models/stock_quant.py:1052-1053`` raises
    ``UserError('Only a stock manager can validate an inventory
    adjustment.')`` unless the caller holds ``stock.group_stock_manager``.
    The gate is REMOVED in v19, so this is a v17-shaped precondition — but
    it is probed, never assumed, on both versions.

    ``framework.qa_fixtures.ensure_qa_user`` grants ``base.group_user``
    only, so that user cannot apply; TC174 runs the apply as the configured
    session user.
    """
    rpc = rpc or ctx.adapter.rpc
    group_id = rpc.ref(GROUP_STOCK_MANAGER)
    if not group_id:
        ctx.blocked(
            f"{GROUP_STOCK_MANAGER} does not exist on {ctx.env.key} "
            f"(db={ctx.env.db}) — stock is not installed.")
    groups_field = ctx.adapter.user_groups_field
    row = rpc.read("res.users", [rpc.uid], ["login", groups_field])[0]
    if group_id not in (row.get(groups_field) or []):
        ctx.blocked(
            f"User {row['login']!r} (uid {rpc.uid}) on {ctx.env.key} "
            f"(db={ctx.env.db}) does not hold {GROUP_STOCK_MANAGER}. Odoo "
            "17 refuses the apply with UserError("
            f"{ERROR_ONLY_STOCK_MANAGER!r}) — stock/models/stock_quant.py"
            ":1052-1053 — so the four date writes this case exists to "
            "prove can never run.")


def require_no_tier_definition(ctx):
    """Record which of the workflow's two flows the target is in.

    ``dto_tier_validation_quant`` gates Apply behind ``tier.validation`` when
    an active ``tier.definition`` matches ``stock.quant``. With none, flow
    **A1** is live: "Apply is present and immediate", Steps 5-9 never occur,
    and TC174/TC175 assert the direct path. Measured on the target: 0
    ``tier_definition`` rows against 628 ``validate`` + 2 ``inprogress``
    quant states.

    BLOCKS rather than adapts if a definition exists, because the apply then
    happens inside the final approval and that path belongs to the APR
    suite, not here.
    """
    rpc = ctx.adapter.rpc
    if not rpc.model_exists("tier.definition"):
        ctx.log("tier.definition is not installed — flow A1 (Apply present "
                "and immediate) is the live path.")
        return 0
    # base_tier_validation/models/tier_definition.py:31 —
    # ``model = fields.Char(related="model_id.model", index=True, store=True)``.
    # It is ``model``, not ``model_name``; scoping on the wrong field would
    # silently match nothing and report the descoped flow on a gated target.
    domain = ([("model", "=", "stock.quant")]
              if rpc.field_exists("tier.definition", "model") else [])
    rows = rpc.search_read("tier.definition", domain, ["name"])
    if rows:
        ctx.blocked(
            f"{len(rows)} tier.definition record(s) target stock.quant on "
            f"{ctx.env.key} (db={ctx.env.db}): {[r['name'] for r in rows]}. "
            "Apply is then gated behind tier validation "
            "(dto_tier_validation_quant/views/stock_quant_views.xml:36-38) "
            "and _apply_inventory runs inside the final approval "
            "(models/stock_quant.py:71-75) — that is flow A1's opposite and "
            "belongs to the APR suite. WF-021 asserts the descoped baseline.")
    ctx.log("0 tier.definition rows on stock.quant — flow A1 confirmed.")
    return 0


# NOTE — there is deliberately no shared ``require_location_analytic`` gate
# here. TC251's tagging surface is version-shaped: v17 ships the pair
# ``valuation_in_account_id`` / ``valuation_out_account_id``
# (``stock_account/models/stock_location.py:10-23``) while v19 folds them
# into a single ``valuation_account_id`` (v19 ``:11``). A gate that requires
# the v17 pair would report "dto_account has nothing to tag" on a correctly
# ported v19 target, which is false. The gate therefore lives in
# ``test_inventory_adjustment._require_tagging_surface``, which resolves the
# field name(s) from ``fields_get`` on the running server — the same
# capability-probe pattern as ``is_v19_product_shape``.


def require_realtime_category(ctx) -> int:
    """A ``product.category`` valued in real time, or BLOCKED.

    ``property_valuation`` is ``company_dependent=True``
    (``stock_account/models/product.py:829-835``), so this resolves it by
    reading candidates rather than by trusting a default. Without a
    real-time category no valuation ``account.move`` is posted at all and
    every money assertion would pass vacuously.

    The stock INPUT and OUTPUT accounts are required too, where the target
    has them. ``_get_accounting_data_for_valuation`` computes BOTH
    ``acc_src`` and ``acc_dest`` for every valued move regardless of
    direction and raises ``UserError`` when either is missing — v17
    ``stock_account/models/stock_move.py:352-374``, the two messages at
    ``:368`` ("Cannot find a stock input account…") and ``:370`` ("…output
    account…") — and both fall back to the category's
    ``property_stock_account_input/output_categ_id`` unless the move's own
    location carries a ``valuation_in/out_account_id``
    (``:392-399``). A category with only a valuation account and a journal
    therefore does not block: it makes ``add_stock`` RAISE inside the
    precondition step, reporting a core string as an ERROR instead of the
    precise BLOCKED this suite promises everywhere else.

    The two account properties are probed with ``field_exists`` rather than
    assumed: **v19 deleted them** — ``product.category`` there declares only
    ``property_stock_journal`` and ``property_stock_valuation_account_id``
    (v19 ``stock_account/models/product.py:765,768``) and
    ``_get_product_accounts`` no longer reads an input/output account at all
    (``:130-142``). Naming a non-existent field in ``search_read`` would
    raise on v19, so the requirement set is built from what the target
    actually declares.
    """
    rpc = ctx.adapter.rpc
    if not rpc.field_exists("product.category", "property_valuation"):
        ctx.blocked(
            f"product.category.property_valuation does not exist on "
            f"{ctx.env.key} (db={ctx.env.db}) — stock_account is not "
            "installed, so an applied adjustment posts no valuation entry.")
    required = ["property_stock_valuation_account_id",
                "property_stock_journal"]
    required += [name for name in ("property_stock_account_input_categ_id",
                                   "property_stock_account_output_categ_id")
                 if rpc.field_exists("product.category", name)]
    rows = rpc.search_read("product.category",
                           [("property_valuation", "=", "real_time")],
                           ["complete_name", "property_cost_method"]
                           + required, order="id")
    usable = [r for r in rows
              if all(m2o_id(r.get(name)) for name in required)]
    if not usable:
        gaps = {r["complete_name"]: [name for name in required
                                     if not m2o_id(r.get(name))]
                for r in rows}
        ctx.blocked(
            f"No product.category on {ctx.env.key} (db={ctx.env.db}) uses "
            f"real-time valuation with all of {required} set "
            f"({len(rows)} real-time categories found; per-category gaps: "
            f"{gaps}). Core stock_account computes acc_src AND acc_dest for "
            "every valued move and raises UserError when either is missing "
            "(stock_account/models/stock_move.py:352-374), so staging stock "
            "for this case would error rather than measure anything.")
    ctx.log(f"real-time valuation category: {usable[0]['complete_name']!r} "
            f"(id {usable[0]['id']}, cost method "
            f"{usable[0]['property_cost_method']!r})")
    return usable[0]["id"]


def realtime_category_data(ctx) -> dict:
    """The chosen real-time category plus its valuation account id.

    TC251 step 7 asserts the Stock Valuation line stays untagged, which is
    only meaningful if that account is known and is NOT one of the two the
    fixture location owns.
    """
    rpc = ctx.adapter.rpc
    categ_id = require_realtime_category(ctx)
    row = rpc.read("product.category", [categ_id],
                   ["complete_name", "property_cost_method",
                    "property_stock_valuation_account_id",
                    "property_stock_journal"])[0]
    return {
        "id": categ_id,
        "name": row["complete_name"],
        "cost_method": row["property_cost_method"],
        "valuation_account_id": m2o_id(
            row["property_stock_valuation_account_id"]),
        "journal_id": m2o_id(row["property_stock_journal"]),
    }


def scan_cycle_count(ctx, pattern: str, suffixes=None) -> dict:
    """Grep the CHECKED-OUT dto_cycle_count for ``pattern``.

    Returns ``{"branch": <git branch or ''>, "root": <str>, "hits": [...]}``.

    Read the branch before reading the hits. ``DTO-Odoo`` is checked out on
    ``UAT``, which carries the v19 port, so a grep for ``type == 'product'``
    finds the ported ``is_storable`` expressions even during a v17 run. The
    hits are evidence ABOUT THE CHECKOUT; what the target actually serves is
    the rendered arch (``arch_of``) and ``fields_get``. TC177 reports the
    scan and asserts the arch.
    """
    from framework.source_scan import grep_module, module_path, resolve_source_root
    root = resolve_source_root(getattr(ctx.env, "version", None))
    if root is None:
        return {"branch": "", "root": "", "hits": [], "available": False}
    module_dir = module_path(root, MODULE)
    if module_dir is None:
        return {"branch": "", "root": str(root), "hits": [], "available": False}
    branch = ""
    try:
        import subprocess
        branch = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=30).stdout.strip()
    except Exception:                                        # noqa: BLE001
        branch = ""
    return {"branch": branch, "root": str(module_dir), "available": True,
            "hits": grep_module(module_dir, pattern, suffixes=suffixes)}


# ===========================================================================
# Sweeping — best-effort, children before parents, never raises
# ===========================================================================
def sweep_wf021(rpc):
    """Remove this suite's leftovers. Safe to call at start and in finally.

    Order is children before parents because every link is a hard one:
    ``stock.move.line`` -> ``stock.move`` -> ``stock.quant`` ->
    ``product.product`` -> ``product.template`` -> ``product.category`` /
    ``stock.location``.

    Quants are the awkward step. ``_unlink_except_wrong_permission``
    (v17 ``stock/models/stock_quant.py:375-382``) zeroes
    ``inventory_quantity`` and calls ``_apply_inventory()``, which re-enters
    the DataOne override — and that raises ``Expected singleton`` for a
    levelless product. The unlink is therefore attempted and allowed to
    fail; whatever survives is token-scoped and cannot collide with the next
    execution's assertions (convention rule 5). Products that cannot be
    unlinked because a quant or a move still references them are ARCHIVED,
    which is what ``sweep_products`` already does.

    NEVER touches: product_category "Finished Goods" (the live one), the
    five shipped ``cycle.count.category`` rows, or any pre-existing quant.
    This suite creates no ``cycle.count.category`` at all — it uses the
    shipped five by xmlid.
    """
    product_ids = rpc.search("product.product",
                             [("default_code", "like", MARKER),
                              ("active", "in", [True, False])])

    if product_ids:
        sweep_model(rpc, "stock.move.line", [("product_id", "in", product_ids)])
        sweep_model(rpc, "stock.move", [("product_id", "in", product_ids)])
        for quant_id in rpc.search("stock.quant",
                                   [("product_id", "in", product_ids)]):
            try:
                rpc.call("stock.quant", "unlink", [quant_id])
            except OdooRPCError:
                pass

    sweep_model(rpc, "stock.picking", [("origin", "like", MARKER)])
    sweep_products(rpc, MARKER)
    sweep_model(rpc, "product.product", [("default_code", "like", MARKER),
                                         ("active", "in", [True, False])])
    sweep_model(rpc, "product.template", [("default_code", "like", MARKER),
                                          ("active", "in", [True, False])])
    sweep_model(rpc, "stock.location", [("name", "like", MARKER),
                                        ("active", "in", [True, False])])
    sweep_model(rpc, "product.category", [("name", "like", MARKER)])
    if rpc.model_exists("account.analytic.account"):
        sweep_model(rpc, "account.analytic.account",
                    [("name", "like", MARKER),
                     ("active", "in", [True, False])])


def safe_sweep(ctx):
    """``finally:`` teardown that can never raise (convention rule 3)."""
    try:
        sweep_wf021(ctx.adapter.rpc)
    except Exception as exc:                                 # noqa: BLE001
        try:
            ctx.log(f"[warn] WF021 cleanup incomplete: {exc}")
        except Exception:                                    # noqa: BLE001
            pass


def open_namespace(ctx):
    with ctx.step(f"Sweep previous {MARKER} fixtures and open a fresh "
                  "namespace"):
        sweep_wf021(ctx.adapter.rpc)
        ctx.log(f"fixture token = {_TOKEN}")


def expect_error(fn, *args, **kwargs) -> tuple[bool, str]:
    """Run ``fn`` and report ``(raised, message)`` instead of propagating.

    Convention: never raise a bare ``AssertionError``; wrap an expected RPC
    failure and let ``ctx.check`` record expected vs actual.
    """
    try:
        fn(*args, **kwargs)
    except OdooRPCError as exc:
        return True, str(exc)
    return False, ""


# ===========================================================================
# Dates
# ===========================================================================
def as_date(value):
    """Normalise a date that came back over RPC to ``datetime.date``.

    RPC hands back ``'YYYY-MM-DD'``, ``'YYYY-MM-DD HH:MM:SS'`` or ``False``.
    """
    if not value:
        return None
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    return datetime.date.fromisoformat(str(value)[:10])


def iso(day) -> str:
    day = as_date(day)
    return day.isoformat() if day else ""


def server_today(ctx, rpc=None) -> datetime.date:
    """The TARGET's today, read from the server — never from the test host.

    ``product.product.last_count_date`` carries ``default=
    _default_last_count_date`` which returns ``fields.Date.today()``
    (``models/product_product.py:10-11,14``). ``default_get`` is a public
    ORM method, so one round trip yields the server's own date with no
    record created and no clock assumption. Falls back to
    ``stock.quant.last_count_date``, which has the same default
    (``models/stock_quant.py:10-11,15``).

    TC174 and TC175 need this because v17's ``_apply_inventory(self)`` takes
    no ``date`` argument (``models/stock_quant.py:17``): the clock cannot be
    frozen and cannot be overridden, so the workbook's absolute dates are
    asserted as the RELATIONSHIP they express — ``today`` and
    ``today + interval`` — against the server's own today.
    """
    rpc = rpc or ctx.adapter.rpc
    for model in ("product.product", "stock.quant"):
        try:
            got = rpc.call(model, "default_get", ["last_count_date"])
        except OdooRPCError:
            continue
        day = as_date((got or {}).get("last_count_date"))
        if day:
            return day
    ctx.blocked(
        f"Could not read the server's own date from {ctx.env.key} "
        f"(db={ctx.env.db}): neither product.product.last_count_date nor "
        "stock.quant.last_count_date returned a default. dto_cycle_count "
        "supplies both defaults (models/product_product.py:10-11, "
        "models/stock_quant.py:10-11); without one, no date assertion in "
        "this suite can be anchored to the target rather than to the test "
        "host, which convention rule 5 forbids.")


def add_interval(day, interval_number: int, interval_type: str):
    """BR-2's arithmetic: ``day + <number> <unit>``.

    This computes the EXPECTED value only. It is never substituted for the
    product's own computation — every case reads the actual value back from
    the server, and the private
    ``cycle.count.category._calculate_scheduled_count_date`` is never
    re-implemented as the source of an assertion (AUTOMATION_CONVENTIONS,
    "Private methods are not reachable").

    The platform venv has no ``python-dateutil``, so the month case
    reproduces ``relativedelta``'s documented semantics with the stdlib: add
    the months, then clamp the day to the target month's last day. Verified
    against the workbook's own worked examples — 2026-08-20 + 1 month =
    2026-09-20, + 4 months = 2026-12-20, + 6 months = 2027-02-20.
    """
    day = as_date(day)
    if day is None:
        return None
    if interval_type == "days":
        return day + datetime.timedelta(days=interval_number)
    if interval_type == "weeks":
        return day + datetime.timedelta(weeks=interval_number)
    if interval_type == "months":
        total = day.month - 1 + interval_number
        year = day.year + total // 12
        month = total % 12 + 1
        return datetime.date(year, month,
                             min(day.day, calendar.monthrange(year, month)[1]))
    raise ValueError(f"unknown interval_type {interval_type!r} — the "
                     "selection is days/weeks/months "
                     "(cycle_count_category.py:16-20)")


def expected_schedule(level_key: str, day) -> datetime.date:
    """``add_interval`` keyed by the shipped level letter."""
    for key, _name, number, unit in SHIPPED_LEVELS:
        if key == level_key:
            return add_interval(day, number, unit)
    raise ValueError(f"unknown level {level_key!r}")


# ===========================================================================
# Products, templates and categories
# ===========================================================================
def storable_values(ctx) -> dict:
    """``{'type': 'product'}`` on v17, ``{'type':'consu','is_storable':True}``
    on v19 — resolved by the adapter (``adapters/odoo17.py:24``,
    ``adapters/odoo19.py:26``) so no test body carries a version branch."""
    return dict(ctx.adapter.storable_product_values())


def service_values(ctx) -> dict:
    """A non-storable product, for the ``_onchange_type`` clear branch."""
    return {"type": "service"}


def make_category(rpc, label: str, name: str | None = None,
                  parent_id: int | None = None) -> int:
    """A namespaced ``product.category``.

    ``name`` overrides the namespaced label, which TC170 needs to create a
    category literally called ``Finished Goods`` (and one with a trailing
    space). ``product.category.name`` has no unique constraint
    (``product/models/product_category.py:16``), so a second row with that
    name is legal — and creating one is how TC170 exercises BR-4 WITHOUT
    renaming the live category (convention rule 3: on the target, category
    id 10 named exactly ``Finished Goods`` carries 7,915 Level-D variants).

    The parent defaults to the namespaced token so ``complete_name`` still
    carries the marker and the sweep can find a row whose own ``name`` is a
    live-looking literal.
    """
    if parent_id is None:
        parent_id = _token_category_root(rpc)
    return rpc.create("product.category", {
        "name": name if name is not None else tag(label),
        "parent_id": parent_id,
    })


_ROOTS: dict = {}


def _token_category_root(rpc) -> int:
    """One namespaced parent category per execution, created on demand."""
    key = (getattr(rpc.env, "base_url", ""), getattr(rpc.env, "db", ""))
    cached = _ROOTS.get(key)
    if cached and rpc.search("product.category", [("id", "=", cached)]):
        return cached
    found = rpc.search("product.category", [("name", "=", tag("ROOT"))],
                       limit=1)
    root = found[0] if found else rpc.create("product.category",
                                             {"name": tag("ROOT")})
    _ROOTS[key] = root
    return root


def finished_goods_category(rpc) -> int:
    """A namespaced category named EXACTLY ``Finished Goods`` (BR-4)."""
    return make_category(rpc, "FG", name=FINISHED_GOODS_NAME)


def near_miss_category(rpc) -> int:
    """``'Finished Goods '`` — one trailing space. TC170 step 9.

    BR-4 is ``self.categ_id.name == 'Finished Goods'``
    (``product_product.py:22``), an exact Python compare, so this category
    must NOT trigger the Level-D auto-assign. Creating it proves the
    fragility without touching the live category.
    """
    return make_category(rpc, "FGSP", name=FINISHED_GOODS_TRAILING_SPACE)


def make_product(ctx, label: str, storable: bool = True,
                 categ_id: int | None = None,
                 level_id: int | None = None,
                 last_count_date: str | None = None,
                 scheduled_count_date: str | None = None,
                 extra: dict | None = None) -> int:
    """A namespaced ``product.product``.

    ``categ_id`` is always explicit: ``product.template.categ_id`` is
    required and core's default resolves ``product.product_category_all``
    through ``env.ref(..., raise_if_not_found=False)``, which silently
    yields nothing on a database whose ``ir_model_data`` row for it is gone
    (see ``framework.qa_fixtures.default_categ_id``).

    Passing ``level_id`` matters more than it looks: a quant of a LEVELLESS
    product cannot be applied — ``_calculate_scheduled_count_date`` opens
    with ``ensure_one()`` (``cycle_count_category.py:23``) and the override
    reads the quant's related level, so the apply raises ``ValueError:
    Expected singleton``. Give every product a level unless the case is
    about the levelless path.
    """
    rpc = ctx.adapter.rpc
    values = {
        "name": tag(label),
        "default_code": code(label),
        "sale_ok": True,
        "purchase_ok": True,
        "taxes_id": [(6, 0, [])],
    }
    values.update(storable_values(ctx) if storable else service_values(ctx))
    if categ_id:
        values["categ_id"] = categ_id
    if level_id is not None:
        values["cycle_count_category_id"] = level_id
    if last_count_date is not None:
        values["last_count_date"] = last_count_date
    if scheduled_count_date is not None:
        values["scheduled_count_date"] = scheduled_count_date
    if extra:
        values.update(extra)
    return rpc.create("product.product", with_categ(rpc, values))


def make_products(ctx, vals_list: list[dict]) -> list[int]:
    """``create()`` with a LIST of vals — TC171 step 4's regression detector.

    ``product.product.create`` is ``@api.model_create_multi``
    (``models/product_product.py:63``) and loops ``for product in records:``
    over the returned recordset (``:68``). A port that reintroduces a
    single-dict assumption assigns Level D to the first record only, which a
    single-record test cannot see. Each entry is namespaced here; callers
    supply ``categ_id`` / ``cycle_count_category_id`` / ``type``.
    """
    rpc = ctx.adapter.rpc
    prepared = []
    for index, vals in enumerate(vals_list, start=1):
        values = copy.deepcopy(vals)
        label = values.pop("label", f"BATCH{index}")
        values.setdefault("name", tag(label))
        values.setdefault("default_code", code(label))
        if "type" not in values and not values.pop("service", False):
            values.update(storable_values(ctx))
        prepared.append(with_categ(rpc, values))
    created = rpc.call("product.product", "create", prepared)
    return created if isinstance(created, list) else [created]


def make_template(ctx, label: str, storable: bool = True,
                  categ_id: int | None = None,
                  extra: dict | None = None) -> int:
    """A namespaced ``product.template`` — TC171 step 8's A4 gap.

    There is NO ``create()`` override on ``product.template``
    (``models/product_template.py`` has no CRUD section; the file ends at
    :102). Creating a template with no attribute lines still creates one
    variant, and that variant goes through ``product.product.create()`` and
    DOES get Level D — so the case asserts the ACTUAL outcome
    (``template.product_variant_ids.cycle_count_category_id``), not a
    presumed "nothing happens".
    """
    rpc = ctx.adapter.rpc
    values = {
        "name": tag(label),
        "default_code": code(label),
        "taxes_id": [(6, 0, [])],
    }
    values.update(storable_values(ctx) if storable else service_values(ctx))
    if categ_id:
        values["categ_id"] = categ_id
    if extra:
        values.update(extra)
    return rpc.create("product.template", with_categ(rpc, values))


def product_tmpl_of(rpc, product_id: int) -> int:
    return m2o_id(rpc.read("product.product", [product_id],
                           ["product_tmpl_id"])[0]["product_tmpl_id"])


def variants_of(rpc, template_id: int) -> list[int]:
    """``product.template.product_variant_ids`` — the STORED o2m.

    ``product_variant_id`` is a non-stored compute in both versions (v17
    ``product/models/product_template.py:122``, v19 ``:146``), so the
    template's ``variant_cycle_count_category_id`` mirror hangs off a
    computed singleton; read the o2m when the question is "which variants
    exist".
    """
    return rpc.search("product.product",
                      [("product_tmpl_id", "=", template_id),
                       ("active", "in", [True, False])], order="id")


def cycle_fields_of(rpc, model: str, ids: list[int]) -> dict:
    """``{id: {level_id, last_count_date, scheduled_count_date}}``.

    m2o values arrive as ``[id, name]``; ``m2o_id`` normalises them, and the
    dates come back as ``datetime.date`` so a caller compares dates to
    dates. Built as ONE dict so a case can assert the whole shape in a
    single ``ctx.check`` (convention: mismatch dicts, not assertion loops).
    """
    if not ids:
        return {}
    fields = list(CYCLE_COUNT_FIELDS)
    if model == "product.template" and rpc.field_exists(
            model, TEMPLATE_VARIANT_LEVEL_FIELD):
        fields.append(TEMPLATE_VARIANT_LEVEL_FIELD)
    out = {}
    for row in rpc.read(model, ids, fields):
        item = {"cycle_count_category_id": m2o_id(
            row.get("cycle_count_category_id")),
            "last_count_date": as_date(row.get("last_count_date")),
            "scheduled_count_date": as_date(row.get("scheduled_count_date"))}
        if TEMPLATE_VARIANT_LEVEL_FIELD in fields:
            item[TEMPLATE_VARIANT_LEVEL_FIELD] = m2o_id(
                row.get(TEMPLATE_VARIANT_LEVEL_FIELD))
        out[row["id"]] = item
    return out


def level_of(rpc, product_id: int, model: str = "product.product"):
    return m2o_id(rpc.read(model, [product_id],
                           ["cycle_count_category_id"])[0]
                  ["cycle_count_category_id"])


def set_level(rpc, product_id: int, level_id, model: str = "product.product"):
    """Write the level — the trigger for the BR-6 quant re-scheduling loop.

    ``product.product.write``'s gate is ``'cycle_count_category_id' in
    vals`` (``models/product_product.py:57``): key presence, not value
    change. ONE ``write`` call rewrites EVERY quant of the product
    (``:58-60``), which is the observable consequence TC175 asserts in place
    of the workbook's step 9 rollback — each RPC call commits its own
    transaction, so a test cannot roll one back
    (AUTOMATION_CONVENTIONS:80-82).
    """
    return rpc.write(model, [product_id],
                     {"cycle_count_category_id": level_id or False})


# ===========================================================================
# The onchange path — the only PUBLIC surface over the interval arithmetic
# ===========================================================================
def onchange(rpc, model: str, record_ids, values: dict,
             field_names: list[str],
             spec_fields: list[str] | None = None) -> dict:
    """Call the public ``onchange(values, field_names, fields_spec)``.

    v17 ``odoo/models.py:7010`` declares it and
    ``addons/web/models/models.py:895`` implements it; v19 declares it at
    ``odoo/orm/models.py:6996``. The result is
    ``{'value': {...}, 'warning': {...}}`` where ``value`` carries only the
    fields the onchange CHANGED (``:1086``, ``RecordSnapshot.diff``). The
    spec defaults to the keys of ``values`` plus ``CYCLE_COUNT_FIELDS`` so
    the three fields under test are always in the snapshot — a field absent
    from ``fields_spec`` is never reported, which would make an assertion
    pass vacuously.

    ``record_ids`` is NOT optional and is passed FIRST, exactly as the web
    client sends ``[resIds, values, fieldNames, fieldsSpec]``. ``onchange``
    carries no ``@api.model`` decorator on either version, so ``call_kw``
    routes it through ``_call_kw_multi``, which consumes the first
    positional as the recordset ids before the method sees its own
    parameters (v17 ``odoo/api.py:464-465`` — ``ids, args = args[0],
    args[1:]``). Omitting it would make the server browse the vals-dict's
    KEYS as record ids. Pass ``[]`` for an unsaved form and ``[record_id]``
    when ``self._origin`` must be populated — which is what the
    ``_onchange_type`` restore branch reads
    (``models/product_product.py:43-45``).

    This is how ``_onchange_categ_id``, ``_onchange_cycle_count_category_id``
    and ``_onchange_type`` are exercised: they are private, and so is
    ``_calculate_scheduled_count_date``, but ``onchange`` is public and
    dispatchable on both versions.
    """
    names = list(dict.fromkeys(
        (spec_fields or []) + list(values.keys()) + CYCLE_COUNT_FIELDS))
    fields_spec = {name: {} for name in names}
    return rpc.call(model, "onchange", list(record_ids), dict(values),
                    list(field_names), fields_spec) or {}


def onchange_value(result: dict, field: str):
    """The value ``onchange`` reported for ``field``, shape-normalised.

    ``RecordSnapshot.diff`` formats simple fields through ``web_read``
    (``web/models/models.py:1217``), so a many2one can come back as a bare
    id, as ``[id, name]`` or as ``{'id':…, 'display_name':…}`` depending on
    the version and the spec. Normalising here keeps every case free of that
    detail. Absent means "the onchange did not change it" — returned as
    ``KeyError``-free ``None``; use ``in`` on ``result['value']`` when the
    distinction between "unchanged" and "cleared" matters.
    """
    value = (result.get("value") or {}).get(field)
    if isinstance(value, dict):
        return value.get("id")
    if isinstance(value, (list, tuple)):
        return value[0] if value else None
    return value


def onchange_changed(result: dict, field: str) -> bool:
    """Whether ``onchange`` reported ``field`` at all."""
    return field in (result.get("value") or {})


def onchange_date(result: dict, field: str):
    return as_date(onchange_value(result, field))


# ===========================================================================
# View arch
# ===========================================================================
def arch_of(ctx, model: str, xmlid: str | None = None,
            view_type: str = "form") -> str:
    """The COMPOSED arch the server would send the web client.

    ``get_view(view_id, view_type)`` is public on both versions (v17
    ``base/models/ir_ui_view.py:2613``, v19 ``:3138``). ``view_type`` is
    routed through the adapter for list views, because v17 calls it
    ``'tree'`` and v19 ``'list'`` (``fg_common.form_arch``).

    This — not a source grep — is the authority on what the target serves:
    the checkout may be the v19 port while the server runs v17 (see "The
    checkout trap").
    """
    if view_type in ("tree", "list"):
        view_type = getattr(ctx.adapter, "list_view_type", view_type)
    if xmlid is None:
        return ctx.adapter.rpc.call(model, "get_view", view_type=view_type)["arch"]
    view_id = ctx.adapter.rpc.ref(xmlid)
    if not view_id:
        ctx.blocked(
            f"View {xmlid} does not resolve on {ctx.env.key} "
            f"(db={ctx.env.db}) — the module that defines it is not "
            "installed, so the arch this case asserts against does not "
            "exist.")
    return ctx.adapter.rpc.call(model, "get_view", view_id,
                                view_type)["arch"]


def parse_arch(arch: str):
    return ET.fromstring(arch)


def find_named(root, tag_name: str, name: str):
    """The first ``<tag_name name="name">`` element anywhere in the arch."""
    for element in root.iter(tag_name):
        if element.get("name") == name:
            return element
    return None


def group_attrs(arch: str, group_name: str) -> dict | None:
    """Attributes of ``<group name=...>``, or None when it is absent."""
    element = find_named(parse_arch(arch), "group", group_name)
    return dict(element.attrib) if element is not None else None


def field_attrs(arch: str, field_name: str,
                within_group: str | None = None) -> dict | None:
    """Attributes of a ``<field>``, optionally only inside one group."""
    root = parse_arch(arch)
    scope = root if within_group is None else find_named(root, "group",
                                                         within_group)
    if scope is None:
        return None
    element = find_named(scope, "field", field_name)
    return dict(element.attrib) if element is not None else None


def filter_attrs(arch: str, filter_name: str) -> dict | None:
    element = find_named(parse_arch(arch), "filter", filter_name)
    return dict(element.attrib) if element is not None else None


def follows(arch: str, tag_name: str, first: str, second: str) -> bool:
    """Whether ``second`` appears after ``first`` among same-tag siblings.

    TC176 step 2 ("a Cycle Count group appears after the traceability
    group") and step 10 ("positioned after the existing Product group-by")
    are ordering claims, and ordering is the one thing an xpath anchor can
    lose silently when the anchor is renamed — v19 renamed
    ``filter[@name='categ_id']`` to ``group_by_categ_id``
    (``product/views/product_views.xml:267``).
    """
    root = parse_arch(arch)
    order = [element.get("name") for element in root.iter(tag_name)
             if element.get("name")]
    if first not in order or second not in order:
        return False
    return order.index(second) > order.index(first)


def list_root_tag(ctx) -> str:
    """``'tree'`` on v17, ``'list'`` on v19 — ``fg_common.list_tag``."""
    return list_tag(ctx)


# ===========================================================================
# Stock: locations, quants, counts
# ===========================================================================
def warehouse(ctx) -> dict:
    """The lowest-id ``stock.warehouse``, or BLOCKED.

    Takes ``ctx`` rather than ``rpc`` so a missing warehouse reports BLOCKED
    with a precise reason instead of a bare ``AssertionError``, which the
    conventions forbid (``AUTOMATION_CONVENTIONS.md:88-90``) and which the
    platform would classify as FAILED — the wrong answer for a precondition
    outside the case's control.
    """
    rpc = ctx.adapter.rpc
    rows = rpc.search_read("stock.warehouse", [],
                           ["name", "lot_stock_id", "view_location_id"],
                           limit=1, order="id")
    if not rows:
        ctx.blocked(
            f"No stock.warehouse exists on {ctx.env.key} (db={ctx.env.db}). "
            "Every fixture location in this suite is created as a CHILD of "
            "the warehouse's stock/view location (convention rule 3: "
            "warehouse infrastructure is found, never created), so without "
            "one no quant can be staged and no step of this case can run.")
    return rows[0]


def stock_location(ctx) -> int:
    return m2o_id(warehouse(ctx)["lot_stock_id"])


def make_location(ctx, label: str, parent_id: int | None = None,
                  usage: str = "internal", name: str | None = None,
                  extra: dict | None = None) -> int:
    """A namespaced child location.

    Fixtures create CHILD locations only; warehouse infrastructure is found,
    never created (the wf025 house style). ``name`` carries the marker so
    the sweep finds it.

    ``parent_id`` is three-valued on purpose: ``None`` means "default to the
    warehouse's view location", an id means that parent, and ``False`` means
    **no parent** — a root location, which is legal and is what a virtual
    location needs when the company's inventory-loss location is itself a
    root.
    """
    rpc = ctx.adapter.rpc
    if parent_id is None:
        parent_id = m2o_id(warehouse(ctx)["view_location_id"])
    values = {
        "name": name if name is not None else tag(label),
        "usage": usage,
        "location_id": parent_id or False,
    }
    if extra:
        values.update(extra)
    return rpc.create("stock.location", values)


def internal_locations(ctx, count: int = 3) -> list[int]:
    """``count`` namespaced internal locations under the warehouse stock.

    TC175 needs "at least three quants in three different internal
    locations". They are created under the token rather than borrowed from
    live data so nothing pre-existing gains a fixture quant (convention rule
    3).
    """
    parent = stock_location(ctx)
    return [make_location(ctx, f"LOC{index}", parent_id=parent)
            for index in range(1, count + 1)]


def inventory_loss_location(ctx) -> int:
    """A virtual ``usage='inventory'`` location, preferring the non-scrap one.

    BLOCKS rather than raising when none exists: ``ctx.blocked`` records the
    precondition as BLOCKED, a bare ``AssertionError`` would record it as
    FAILED (``AUTOMATION_CONVENTIONS.md:88-90``).
    """
    rpc = ctx.adapter.rpc
    rows = rpc.search_read("stock.location", [("usage", "=", "inventory")],
                           ["complete_name"], order="id")
    if not rows:
        ctx.blocked(
            f"No stock.location with usage='inventory' exists on "
            f"{ctx.env.key} (db={ctx.env.db}). It is the source of every "
            "staged receipt (``add_stock``) and the parent this suite "
            "borrows for its own virtual locations, so no fixture stock can "
            "be created and no step of this case can run.")
    preferred = [r for r in rows if "scrap" not in r["complete_name"].lower()]
    return (preferred or rows)[0]["id"]


def make_virtual_inventory_location(ctx, label: str,
                                    analytic_distribution: dict | None = None,
                                    in_account_id: int | None = None,
                                    out_account_id: int | None = None) -> int:
    """TD-L-06 — a tagged virtual inventory location for TC251.

    **Both** valuation accounts are set, deliberately. The override tags a
    line whose account is either ``valuation_in_account_id`` OR
    ``valuation_out_account_id``
    (``dto_account/models/stock_move.py:40``), and core picks a different
    one per direction: a **decrease** counterparts to
    ``location_dest_id.valuation_in_account_id``
    (``stock_account/models/stock_move.py:395-399``) and an **increase** to
    ``location_id.valuation_out_account_id`` (``:392-393``). A fixture that
    sets only one passes step 8 and silently produces an untagged line at
    step 11 — the workbook's step 8 names the wrong one of the two.
    """
    rpc = ctx.adapter.rpc
    values = {}
    if analytic_distribution is not None:
        values["location_analytic_distribution"] = analytic_distribution
    if in_account_id:
        values["valuation_in_account_id"] = in_account_id
    if out_account_id:
        values["valuation_out_account_id"] = out_account_id
    # Sit it beside the company's existing inventory-loss location rather
    # than under a warehouse: a virtual location belongs under the Virtual
    # Locations root, and borrowing that parent avoids inventing warehouse
    # topology. ``location_id`` may legitimately be False (a root location).
    sibling = inventory_loss_location(ctx)
    parent = m2o_id(rpc.read("stock.location", [sibling],
                             ["location_id"])[0]["location_id"])
    return make_location(ctx, label, parent_id=parent or False,
                         usage="inventory", extra=values)


def picking_type(ctx, code_: str) -> int:
    """The lowest-id ``stock.picking.type`` with ``code``, or BLOCKED."""
    rpc = ctx.adapter.rpc
    rows = rpc.search_read("stock.picking.type", [("code", "=", code_)],
                           ["id"], limit=1, order="id")
    if not rows:
        ctx.blocked(
            f"No stock.picking.type with code={code_!r} exists on "
            f"{ctx.env.key} (db={ctx.env.db}). ``add_stock`` stages every "
            "fixture quant through a validated picking of that type "
            "deliberately (the inventory-count path would run the very "
            "override this suite measures), so no quant can be created and "
            "no step of this case can run.")
    return rows[0]["id"]


def add_stock(ctx, product_id: int, location_id: int, qty: float):
    """Receive ``qty`` into a location through a validated picking.

    Deliberately NOT the inventory-count path. Staging stock by writing
    ``inventory_quantity`` and applying would run the very override the
    suite is measuring, so the fixture would be entangled with the
    subject — and on a levelless product it would raise ``Expected
    singleton`` (``cycle_count_category.py:23``). A picking changes on-hand
    without touching ``last_count_date``, ``scheduled_count_date`` or
    ``inventory_date``'s DataOne rewrite.

    **It creates TWO quants per call, not one.** ``stock.move.line
    ._action_done`` runs ``_synchronize_quant(-qty, ml.location_id)`` for the
    SOURCE side of every done line (v17
    ``stock/models/stock_move_line.py:660``), ``_synchronize_quant`` filters
    only on ``product_id.type`` and a zero quantity — never on the location's
    usage (``:673-682``) — and ``stock.quant._update_available_quantity``
    creates a row when ``_gather`` finds none (``stock_quant.py:1075``,
    ``:1119-1139``). A counterpart quant therefore accumulates in the
    inventory-loss location the receipt is sourced from, exactly as core does
    for a vendor receipt in the supplier location. Any "exactly N quants"
    assertion must be scoped BY LOCATION (``quant_of``); the unscoped
    ``quants_of`` returns the fixture quants plus that counterpart.
    """
    if qty <= 0:
        return
    rpc = ctx.adapter.rpc
    uom_id = m2o_id(rpc.read("product.product", [product_id],
                             ["uom_id"])[0]["uom_id"])
    src = inventory_loss_location(ctx)
    picking_id = rpc.create("stock.picking", {
        "picking_type_id": picking_type(ctx, "incoming"),
        "location_id": src,
        "location_dest_id": location_id,
        "origin": tag("stage-stock"),
        "move_ids": [(0, 0, {
            "product_id": product_id,
            "product_uom": uom_id,
            "product_uom_qty": qty,
            "location_id": src,
            "location_dest_id": location_id,
        })],
    })
    rpc.call("stock.picking", "action_confirm", [picking_id])
    rpc.call("stock.picking", "action_assign", [picking_id])
    move_ids = rpc.search("stock.move", [("picking_id", "=", picking_id)])
    rpc.write("stock.move", move_ids, {"quantity": qty, "picked": True})
    rpc.call("stock.picking", "button_validate", [picking_id])


def quant_of(rpc, product_id: int, location_id: int) -> int | None:
    found = rpc.search("stock.quant", [("product_id", "=", product_id),
                                       ("location_id", "=", location_id)],
                       limit=1, order="id")
    return found[0] if found else None


def quants_of(rpc, product_id: int) -> list[int]:
    """Every quant of a product, in id order.

    This is the set ``product.product.write`` iterates as
    ``self.stock_quant_ids.sudo()`` (``models/product_product.py:58``);
    ``stock_quant_ids`` is core's ``One2many('stock.quant','product_id')``
    (v17 ``stock/models/product.py:29``, v19 ``:50``).

    **Not a fixture-location count.** It is unscoped by design — the write
    loop under test is unscoped too — so it also returns the counterpart
    quant ``add_stock`` leaves in the inventory-loss location (see that
    helper). Use ``quant_of(rpc, product_id, location_id)`` for any "exactly
    N quants" assertion.
    """
    return rpc.search("stock.quant", [("product_id", "=", product_id)],
                      order="id")


def quant_state(rpc, quant_ids: list[int]) -> dict:
    """``{quant_id: {…inventory fields…}}`` — one dict for one ``ctx.check``."""
    if not quant_ids:
        return {}
    out = {}
    for row in rpc.read("stock.quant", quant_ids, QUANT_INVENTORY_FIELDS):
        out[row["id"]] = {
            "quantity": row["quantity"],
            "inventory_quantity": row["inventory_quantity"],
            "inventory_diff_quantity": row["inventory_diff_quantity"],
            "inventory_quantity_set": row["inventory_quantity_set"],
            "inventory_date": as_date(row["inventory_date"]),
            "last_count_date": as_date(row["last_count_date"]),
            "cycle_count_category_id": m2o_id(row["cycle_count_category_id"]),
        }
    return out


def inventory_dates(rpc, quant_ids: list[int]) -> dict:
    """``{quant_id: inventory_date}`` — the before/after map TC175 diffs."""
    return {qid: state["inventory_date"]
            for qid, state in quant_state(rpc, quant_ids).items()}


def stamp_quant(rpc, quant_id: int, last_count_date,
                inventory_date=None) -> bool:
    """Write a quant's scheduling dates directly.

    Both are plain writable columns on the target: the module redefines
    ``last_count_date`` with ``compute=False``
    (``models/stock_quant.py:15``), overriding core's non-stored compute
    (v17 ``stock/models/stock_quant.py:114``), and ``inventory_date`` is a
    stored compute with ``readonly=False`` (``:111-113``). Neither is in
    ``_get_forbidden_fields_write()`` (``:360-362``), so a plain write goes
    straight through ``super().write``.

    TC175 needs this: if a quant's ``last_count_date`` is falsy, the
    re-scheduling loop falls back to TODAY inside
    ``_calculate_scheduled_count_date`` (``cycle_count_category.py:24-25``)
    and the case's fixed-date expectation evaporates.
    """
    values = {"last_count_date": iso(last_count_date)}
    if inventory_date is not None:
        values["inventory_date"] = iso(inventory_date)
    return rpc.write("stock.quant", [quant_id], values)


def enter_count(rpc, quant_id: int, counted_qty: float) -> bool:
    """Type a Counted Quantity — the ``inventory_mode`` write.

    ``_is_inventory_mode()`` requires ``context['inventory_mode']`` AND
    ``stock.group_stock_user`` (``stock/models/stock_quant.py:1230-1235``).
    ``inventory_quantity`` is not a forbidden field (``:360-362``), so the
    write lands and the stored compute sets
    ``inventory_diff_quantity = inventory_quantity - quantity``
    (``:189-192``).

    NOT ``inventory_quantity_auto_apply``: that field carries
    ``groups='stock.group_stock_manager'`` (``:102-106``) and its inverse
    applies immediately (``:228-236``), which would skip the counted state
    the case is about.
    """
    return rpc.call("stock.quant", "write", [quant_id],
                    {"inventory_quantity": counted_qty},
                    context={"inventory_mode": True})


def apply_count(rpc, quant_ids):
    """Press Apply. RETURNS the action result — the caller must check it.

    ``action_apply_inventory`` is public (v17
    ``stock/models/stock_quant.py:445``) but returns a WIZARD DICT instead
    of applying when a quant ``is_outdated``
    (``stock.inventory.conflict``, ``:461-470``) or a lot/serial product has
    no lot (``stock.track.confirmation``, ``:471-480``). A falsy return is
    the only proof it actually reached ``self._apply_inventory()``
    (``:483``); a test that ignores the return can assert nothing.

    v17 takes **no arguments** (``:445``); v19 is ``(self, date=None)``
    (``:433``). Nothing here passes a date — the back-dated variant is the
    NEW suite's v19 detector, which the workbook says to reference rather
    than duplicate.
    """
    ids = quant_ids if isinstance(quant_ids, list) else [quant_ids]
    return rpc.call("stock.quant", "action_apply_inventory", ids)


def due_on(rpc, quant_id: int, on_date) -> bool:
    """Would this quant appear on the count sheet on ``on_date``?

    The count sheet is not a DataOne artefact: ``dto_cycle_count`` ships no
    cron and no scheduled action (BR-7). The sheet is core's ``to_count``
    filter, domain ``[('inventory_date','<=', <today>)]`` —
    ``stock/views/stock_quant_views.xml:37`` (v19 ``:39``). The Physical
    Inventory action's own domain is only
    ``[('location_id.usage','in',['internal','transit'])]``
    (``stock/models/stock_quant.py:432``).

    Implementing the filter as a scoped search is how TC174 steps 13-14 and
    TC175 step 10 are answered without ever "setting the working date",
    which no RPC client can do.
    """
    return bool(rpc.search("stock.quant",
                           [("id", "=", quant_id),
                            ("inventory_date", "<=", iso(on_date))],
                           limit=1))


def move_lines_for(rpc, product_id: int, exclude_ids=()) -> list[dict]:
    """``stock.move.line`` rows for a product, minus a pre-recorded set.

    TC174 step 7 ("a stock.move.line was created for the variance") and step
    15 (the zero-variance case) both need "what appeared since", and ids are
    never relied on across tests — the exclusion set is captured in the same
    test run.
    """
    rows = rpc.search_read(
        "stock.move.line", [("product_id", "=", product_id)],
        ["move_id", "quantity", "location_id", "location_dest_id",
         "reference", "state"], order="id")
    excluded = set(exclude_ids or ())
    return [r for r in rows if r["id"] not in excluded]


# ===========================================================================
# Users and groups
# ===========================================================================
def ensure_wf021_user(ctx, suffix: str, group_xmlids: list[str]) -> tuple:
    """A disposable internal user in the given groups. Returns ``(id, login)``.

    The groups m2m is version-dependent — ``res.users.groups_id`` on v17
    (``base/models/res_users.py:384``), renamed to ``group_ids`` on v19
    (``:257``), where the old name raises ``ValueError: Invalid field
    'groups_id' in 'res.users'``. The name comes from
    ``ctx.adapter.user_groups_field`` so no version branch reaches a case.

    ``no_reset_password`` is set on create: a welcome email is an outbound
    integration, and convention rule 4 forbids triggering one.
    """
    rpc = ctx.adapter.rpc
    groups_field = ctx.adapter.user_groups_field
    login = f"qa.wf021.{suffix}"
    group_ids = [rpc.ref(x) for x in [GROUP_USER] + list(group_xmlids)]
    group_ids = [g for g in group_ids if g]
    found = rpc.search("res.users", [("login", "=", login),
                                     ("active", "in", [True, False])],
                       limit=1)
    if found:
        rpc.write("res.users", found,
                  {"active": True, "password": WF021_PASSWORD,
                   groups_field: [(6, 0, group_ids)]})
        return found[0], login
    user_id = rpc.call("res.users", "create",
                       {"name": f"QA {MARKER} {suffix}", "login": login,
                        "password": WF021_PASSWORD,
                        groups_field: [(6, 0, group_ids)]},
                       context={"no_reset_password": True})
    return user_id, login


def rpc_as(env, login: str) -> OdooRPC:
    """A second authenticated RPC session as ``login``."""
    user_env = copy.copy(env)
    user_env.username = login
    user_env.password = WF021_PASSWORD
    return OdooRPC(user_env)


def archive_user(rpc, user_id: int):
    try:
        rpc.write("res.users", [user_id], {"active": False})
    except OdooRPCError:
        pass


def product_write_groups(rpc) -> list[dict]:
    """Groups that grant ``perm_write`` on ``product.product``, with xmlids.

    TC175 step 11 documents a real privilege surface: because the
    re-scheduling loop is ``sudo()``-ed
    (``models/product_product.py:58``), product-write rights ALONE are
    enough to rewrite quant scheduling. Proving it needs a user who can
    write a product but is NOT a stock manager — and which group that is
    cannot be known in advance, because on v17
    ``stock.group_stock_manager`` itself holds 1,1,1,1 on ``product.product``
    (``stock/security/ir.model.access.csv:22``) while v19 deletes that row.

    Returns ``[{'group_id', 'group_xmlid', 'name'}]`` in id order, so a case
    can pick a non-stock-manager candidate or BLOCK that step alone with a
    precise reason naming what the target actually grants.
    """
    model_ids = rpc.search("ir.model", [("model", "=", "product.product")])
    if not model_ids:
        return []
    rows = rpc.search_read("ir.model.access",
                           [("model_id", "in", model_ids),
                            ("perm_write", "=", 1)],
                           ["name", "group_id", "active"])
    group_ids = sorted({m2o_id(r["group_id"]) for r in rows
                        if m2o_id(r["group_id"])})
    if not group_ids:
        return []
    data = rpc.search_read("ir.model.data",
                           [("model", "=", "res.groups"),
                            ("res_id", "in", group_ids)],
                           ["module", "name", "res_id"])
    xmlid = {d["res_id"]: f"{d['module']}.{d['name']}" for d in data}
    return [{"group_id": gid, "group_xmlid": xmlid.get(gid, ""),
             "name": next((r["name"] for r in rows
                           if m2o_id(r["group_id"]) == gid), "")}
            for gid in group_ids]


def non_manager_product_writer(rpc) -> str:
    """A ``product.product``-write group that is NOT the stock manager.

    Returns its xmlid, or ``""`` when the target grants product write only
    through ``stock.group_stock_manager`` — in which case TC175 step 11
    ``ctx.blocked``s that step alone rather than the case.
    """
    manager_id = rpc.ref(GROUP_STOCK_MANAGER)
    implied = {manager_id} if manager_id else set()
    for row in product_write_groups(rpc):
        if row["group_id"] in implied or not row["group_xmlid"]:
            continue
        if row["group_xmlid"] == GROUP_STOCK_MANAGER:
            continue
        return row["group_xmlid"]
    return ""


# ===========================================================================
# Accounting fixtures — TC251 only
# ===========================================================================
def analytic_plan(rpc) -> int | None:
    rows = rpc.search_read("account.analytic.plan", [], ["name"], limit=1,
                           order="id")
    return rows[0]["id"] if rows else None


def make_analytic_account(rpc, label: str) -> int:
    """A namespaced ``account.analytic.account``.

    Namespaced rather than borrowed: TC251 asserts a distribution EQUALS a
    known value, and a live analytic account could already appear in a line's
    inherited distribution, which would make the comparison ambiguous.
    """
    values = {"name": tag(label)}
    plan_id = analytic_plan(rpc)
    if plan_id and rpc.field_exists("account.analytic.account", "plan_id"):
        values["plan_id"] = plan_id
    return rpc.create("account.analytic.account", values)


def analytic_distribution(account_ids, percent: float = 100.0,
                          split: bool = False) -> dict:
    """``{'<analytic_account_id>': percent}`` — the JSON shape v17 stores.

    ``analytic_distribution`` is ``fields.Json`` on ``analytic.mixin``
    (``analytic/models/analytic_mixin.py:13-16``), and
    ``stock.location.location_analytic_distribution`` is a plain
    ``fields.Json`` of the same shape
    (``dto_account/models/stock_location.py:11``).

    Keys are **strings**, and that matters: the override merges with
    ``{**line_val.get('analytic_distribution', {}), **analytic_distribution}``
    (``dto_account/models/stock_move.py:41-44``), so an int key and a str
    key for the same account would survive as two entries and double the
    cost centre in the analytic ledger.

    ``split`` defaults to **False** because TD-L-06's distribution names one
    account per PLAN (Consumables, a spend category; CC 202000, a cost
    centre), and a distribution is 100% per plan — not 100% shared across
    plans. Pass ``split=True`` only for two accounts inside one plan.
    """
    ids = account_ids if isinstance(account_ids, (list, tuple)) else [account_ids]
    share = (percent / len(ids)) if (split and len(ids) > 1) else percent
    return {str(account_id): share for account_id in ids}


def pick_counterpart_accounts(ctx, count: int = 2,
                              exclude_ids=()) -> list[int]:
    """``count`` existing expense accounts to hang on the fixture location.

    Existing accounts are REUSED rather than created: a posted journal entry
    pins its accounts, so freshly created ones could never be unlinked in
    teardown and would linger in the chart of accounts (convention rule 3 is
    about not disturbing live data in either direction). ``exclude_ids``
    keeps the category's own stock-valuation account out, without which
    TC251 step 7 — "the Stock Valuation line's distribution is untouched" —
    would be confounded by a collision.
    """
    rpc = ctx.adapter.rpc
    excluded = [i for i in exclude_ids if i]
    domain = [("deprecated", "=", False),
              ("account_type", "in", ["expense", "expense_direct_cost",
                                      "asset_current"])]
    if excluded:
        domain.append(("id", "not in", excluded))
    rows = rpc.search_read("account.account", domain, ["code", "name"],
                           limit=count, order="code")
    if len(rows) < count:
        ctx.blocked(
            f"Fewer than {count} usable non-deprecated accounts on "
            f"{ctx.env.key} (db={ctx.env.db}) once the category's own "
            "valuation account is excluded. TD-L-06 needs BOTH "
            "valuation_in_account_id and valuation_out_account_id set — "
            "core picks a different one per direction "
            "(stock_account/models/stock_move.py:392-399) — and neither may "
            "equal the valuation account, or step 7 cannot distinguish a "
            "tagged line from an untagged one.")
    ctx.log(f"counterpart accounts: "
            f"{[(r['code'], r['name']) for r in rows]}")
    return [r["id"] for r in rows]


def set_inventory_location(rpc, product_id: int, location_id: int) -> bool:
    """Point a product's ``property_stock_inventory`` at a location.

    ``property_stock_inventory`` is ``company_dependent=True``
    (``stock/models/product.py:668``) and is what
    ``_apply_inventory`` passes as the virtual counterpart
    (``stock/models/stock_quant.py:1059``, ``:1064``). Without it the
    adjustment routes through the company's default inventory-loss location
    and the fixture's tagged location is never involved — so TC251 would
    assert an untagged entry and call it a failure of the override.
    """
    return rpc.write("product.product", [product_id],
                     {"property_stock_inventory": location_id})


def valuation_moves_for(rpc, product_id: int, exclude_ids=()) -> list[int]:
    """``account.move`` ids posted for a product's stock moves, minus a set."""
    line_rows = rpc.search_read(
        "account.move.line", [("product_id", "=", product_id)],
        ["move_id"], order="id")
    excluded = set(exclude_ids or ())
    move_ids = []
    for row in line_rows:
        move_id = m2o_id(row["move_id"])
        if move_id and move_id not in excluded and move_id not in move_ids:
            move_ids.append(move_id)
    return move_ids


def move_line_rows(rpc, move_ids: list[int]) -> list[dict]:
    """The journal items of one or more entries, in id order.

    ``_generate_valuation_lines_data`` returns exactly ``credit_line_vals``
    + ``debit_line_vals`` (``stock_account/models/stock_move.py:469-516``);
    the third ``price_diff_line_vals`` appears only when
    ``credit_value != debit_value``, which an inventory adjustment never
    produces. TC251 step 6 asserts "exactly two lines" against that.
    """
    if not move_ids:
        return []
    rows = rpc.search_read(
        "account.move.line", [("move_id", "in", list(move_ids))],
        ["move_id", "account_id", "debit", "credit", "name",
         "analytic_distribution"], order="id")
    for row in rows:
        row["account_id"] = m2o_id(row["account_id"])
        row["move_id"] = m2o_id(row["move_id"])
        row["analytic_distribution"] = row.get("analytic_distribution") or {}
    return rows


def analytic_lines_for(rpc, analytic_account_ids) -> list[dict]:
    """``account.analytic.line`` rows for the given analytic accounts.

    TC251 step 10 asks the analytic ledger to have indexed the tagged line,
    and it is ASSERTED, not merely recorded — the chain is in core and was
    verified line by line:

    * ``account.move._post`` ends with ``to_post.line_ids
      ._create_analytic_lines()`` (v17 ``account/models/account_move.py
      :3939``);
    * ``account.move.line._create_analytic_lines`` (``account_move_line.py
      :3186-3196``) delegates to ``_prepare_analytic_lines``
      (``:3198-3209``), which emits ONE value dict per key of **that line's
      own** ``analytic_distribution``;
    * ``_prepare_analytic_distribution_line`` (``:3211-3225``) sets
      ``amount = -self.balance * distribution / 100``, grouped by
      ``account.root_plan_id``.

    The line this override tags is the COUNTERPART, so one analytic line per
    tagged plan appears, each of the entry's magnitude.

    An earlier ``[UNVERIFIED]`` note here cited ``stock.move
    ._prepare_analytic_lines`` (``stock_account/models/stock_move.py
    :417-436``), which reads the valuation line — that is a DIFFERENT
    mechanism (the move's own ``analytic_distribution``/
    ``analytic_account_line_ids``, not the journal entry's) and says nothing
    about this step. The note has been withdrawn.
    """
    ids = (analytic_account_ids if isinstance(analytic_account_ids, (list, tuple))
           else [analytic_account_ids])
    if not rpc.model_exists("account.analytic.line") or not ids:
        return []
    domain_field = ("auto_account_id"
                    if rpc.field_exists("account.analytic.line",
                                        "auto_account_id") else "account_id")
    return rpc.search_read("account.analytic.line",
                           [(domain_field, "in", list(ids))],
                           ["name", "amount", domain_field], order="id")
