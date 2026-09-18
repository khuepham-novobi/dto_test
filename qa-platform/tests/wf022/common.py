"""DATAONE-WF-022 — Scrap with Defect Coding and Approval: shared fixtures.

Everything asserted by this suite was read out of the real source before a
line of it was written (AUTOMATION_CONVENTIONS hard rule 6). Abbreviations
below: ``DTO`` = ``D:/Projects/dataone/DTO-Odoo``, ``O17`` =
``D:/Projects/dataone/odoo-17.0``, ``O19`` = ``D:/Projects/odoo-19.0``.

The model under test
--------------------
``stock.scrap`` — core ``O17 addons/stock/models/stock_scrap.py:10-14`` /
``O19 …:10-14`` (``_inherit = ['mail.thread']``, ``_order = 'id desc'``).

Two DataOne modules carry the WF-022 half, and **which one** is live on a
given target is a runtime fact this suite never assumes:

* v17 ``DTO/project-addons/dto_tier_validation_scrap/models/stock_scrap.py``
  — ``_inherit = ['stock.scrap', 'tier.validation']`` (:9-11) with
  ``_state_from = ['draft']`` (:12), ``_state_to = ['done']`` (:13),
  ``_cancel_state = ''`` (:14) and
  ``_tier_validation_manual_config = False`` (:16).
* v19 ``DTO/project-addons/dto_scrap/models/stock_scrap.py`` —
  ``_inherit = 'stock.scrap'`` only (:28-29); the mixin is deliberately gone
  (documented :13-21).

Every field, method and error string below is **identical** in the two
files, so the suite asserts on the field/method/arch and never on a module
name.

BLOCKING ENVIRONMENT FACT (§0 of the source verification, carried into
docs/WF-022_AUTOMATION_PLAN.md)
------------------------------------------------------------------------
``dto_tier_validation_scrap/__manifest__.py:56`` now declares
``'installable': False`` (rationale in the comment block :39-55). Odoo 17
skips a not-installable module **even when the database row says
``state='installed'``** — ``Graph.add_modules``:
``if info and info['installable']: packages.append(...)`` else
``_logger.warning('module %s: not installable, skipped')``
(``O17 odoo/modules/graph.py:72-75``). If the v17 QA server reloads the
current tree, ``defect_code``, ``defect_code_description``,
``employee_name``, ``amount``, ``company_currency_id``, the
``('cancel','Cancelled')`` selection value and
``action_confirm_create_scrap`` are all absent from the registry while the
four ``ir.ui.view`` rows the module created remain in the database.

The workbook's own precondition for these cases is *"dto_tier_validation_scrap
is installed"*, so that is implemented as the **first ctx.check** of each
test (:func:`check_scrap_extension`) rather than as a skip — a missing field
must be a loud, correctly attributed FAIL, not an AUTOMATION_ERROR.
:func:`require_scrap_extension` is the BLOCKED form, for a caller that
genuinely cannot proceed (e.g. a fixture-only helper).

Field table (verbatim declarations, v17 line / v19 line)
--------------------------------------------------------
===========================  ============================  ==========  ==========
field                        declaration                   v17         v19
===========================  ============================  ==========  ==========
``state``                    ``Selection(selection_add=[('cancel','Cancelled')],
                             ondelete={'cancel':'set default'})``       :21   :40
``company_currency_id``      ``Many2one('res.currency', related=
                             'company_id.currency_id')``                :22-23 :41-42
``amount``                   ``Monetary(compute='_compute_amount',
                             store=True, help='Estimated Amount',
                             currency_field='company_currency_id')``    :24-25 :43-44
``defect_code``              ``Char`` — no required, no constraint,
                             no selection                               :27-37 :46-56
``defect_code_description``  ``Char(compute=
                             '_compute_defect_code_description',
                             store=True)`` — read-only is a VIEW
                             attribute, not a field attribute           :38-42 :57-61
``employee_name``            ``Char(string='Employee')`` — plain Char,
                             no ``hr.employee`` link, no validation     :44    :63
===========================  ============================  ==========  ==========

Core ``state`` is ``[('draft','Draft'),('done','Done')]`` on **both**
versions (``O17 stock_scrap.py:50-53`` / ``O19 …:50-53``) — there is no
native ``cancel`` value, so the ``selection_add`` does not collide. That was
the workbook's "settle this first" unknown and the source answers it.

``dto_stock`` adds the F080 half (``DTO/project-addons/dto_stock/models/
stock_scrap.py``)::

    account_move_ids = fields.Many2many(
        'account.move', string='Journal Entries',
        compute='_compute_account_move_ids')            # :10-11, NOT stored

    @api.depends('state')
    def _compute_account_move_ids(self):                # :13-24
        for res in self:
            if res.state == 'done':
                res.account_move_ids = res.move_ids.account_move_id   # :22
            else:
                res.account_move_ids = False            # :24  → draft ⇒ empty

``:22`` is v19-shaped: ``stock.move.account_move_id`` exists on v19
(``O19 stock_account/models/stock_move.py:51``) but **not** on v17, whose
field is the One2many ``account_move_ids`` (``O17 …:19``). The v17-deployed
revision of the same file reads ``res.move_ids.account_move_ids``
(git ``6e410c8:project-addons/dto_stock/models/stock_scrap.py:17``).

The nine-code table — verbatim, identical in both modules
---------------------------------------------------------
``_compute_defect_code_description``, ``@api.depends('defect_code')``,
stored (v17 :49-66, table :52-62, lookup :64, empty branch :66; v19
``dto_scrap`` :68-89, table :75-85, lookup :87, empty :89)::

    res.defect_code_description = defect_codes.get(
        res.defect_code.upper().strip(), _('Unknown defect code'))

``.upper()`` then ``.strip()``; the falsy branch writes ``''`` (an **empty
string**, not the fallback). The fallback string is, character for
character, ``Unknown defect code``. Neither module ships an ``i18n/``
directory, so no ``.po`` can override it.

``_compute_amount`` — verbatim, identical (v17 :68-72; v19 :91-100)::

    @api.depends('scrap_qty', 'product_id', 'product_id.standard_price')
    def _compute_amount(self):
        for res in self:
            scrap_uom_qty = res.product_uom_id._compute_quantity(
                res.scrap_qty, res.product_id.uom_id)
            res.amount = scrap_uom_qty * res.product_id.standard_price

Note the depends set does **not** include ``product_uom_id``: changing only
the UoM does not itself trigger a recompute; changing ``scrap_qty`` or
``product_id`` does.

Public, RPC-reachable methods this suite drives
-----------------------------------------------
* ``stock.scrap.action_confirm_create_scrap()`` → an ``ir.actions.act_window``
  **dict** (v17 :96-109, v19 :113-132); ``ensure_one()`` first.
* ``stock.scrap.action_cancel()`` → ``None``, writes ``state='cancel'``
  (v17 :80-82 with ``skip_validation_check=True``; v19 :105-111, plain).
* ``stock.scrap.action_validate()`` / ``do_scrap()`` / ``check_available_qty()``
  — core, ``O17 :196-220 / :140-152 / :181-194``.
* ``stock.scrap.action_view_journal_entries()`` — ``dto_stock`` :26-40,
  returns a dict or ``None`` when ``account_move_ids`` is empty.
* ``mrp.production.button_scrap()`` — ``O17 mrp_production.py:2160-2173``,
  ``O19 :2406-2419``; ``stock.picking.button_scrap()`` —
  ``O17 stock_picking.py:1563-1579``, ``O19 :1900-1916``. Both return a dict
  whose view resolves to ``stock.stock_scrap_form_view2``, ``target:'new'``.
* ``get_view(view_id, view_type)`` — ``O17 ir_ui_view.py:2613`` /
  ``O19 :3138``.

**Not reachable over RPC** (never re-implemented here):
``_compute_defect_code_description``, ``_compute_amount``,
``_compute_account_move_ids``, ``_prepare_move_values``,
``_should_check_available_qty``, ``_validate_tier``, ``_rejected_tier``,
and — the one that shapes TC182 — ``uom.uom._compute_quantity``.

Exact error strings (never paraphrased)
---------------------------------------
* ``You can only enter positive quantities.`` — raised by
  ``action_confirm_create_scrap`` (v17 :98-99, v19 :121-122) **and** by core
  ``action_validate`` (``O17 :198-200``, ``O19 :213-214``). Because the two
  strings are identical, a test proving F255's guard **must call
  ``action_confirm_create_scrap`` by name**; the generic Validate path
  proves nothing.
* ``You cannot delete a scrap which is done.`` — ``@api.ondelete`` on core
  (``O17 :107-110``, ``O19 :120-123``). This is why no fixture here ever
  validates a scrap.
* ``%s cannot be deleted. Try to cancel them before.`` —
  ``mrp.production`` ondelete (``O17 mrp_production.py:1255-1262``);
  ``unlink()`` calls ``action_cancel()`` first (:944-949), so a confirmed MO
  fixture is still removable.
* The three ``base_tier_validation`` ``ValidationError`` messages
  (``DTO/3rd-addons/base_tier_validation/models/tier_validation.py:350-355``,
  ``:357-362``, ``:378-386``) are exported for completeness. They only fire
  when ``rec.review_ids`` is non-empty, and ``tier_review`` has zero rows on
  ``dto_17`` for every model ever (``DTO/WF022-README.md``), so no test here
  creates a ``tier.definition``.

XML ids
-------
Core anchors: ``stock.stock_scrap_form_view`` (``O17 views/stock_scrap_views.xml:24``;
header ``action_validate`` button :30; ``button_box`` div :34; ``lot_id``
:61) · ``stock.stock_scrap_form_view2`` (:158; the footer button
``<button name="action_validate" string="Scrap Products" class="btn-primary"
data-hotkey="q"/>`` at :191 — **its label is "Scrap Products", not
"Validate"**) · ``stock.stock_scrap_tree_view`` (:124, root ``<tree>`` :128,
``state`` field :139) · ``stock.stock_scrap_search_view`` (:4) ·
``mrp.stock_scrap_search_view_inherit_mrp`` (``O17 mrp/views/stock_scrap_views.xml:32-45``,
anchor ``filter_done`` :39 — **same line on v19**) ·
``account.action_account_moves_all`` (``O17 account/views/account_move_views.xml:1619-1626``
— **res_model is ``account.move.line``**; ``O19 :1925-1933``).
v19 equivalents: form :24 (header button :30, ``lot_id`` :60),
form2 :142 (footer ``action_validate`` **:175**), list :108 with **``<list>``**
:112.

The four DataOne view inherits (v17 ``dto_tier_validation_scrap/views/
stock_scrap_views.xml``; v19 the same ids under ``dto_scrap.*``):

* search (:5-20 / :9-21) — ``filter_cancel`` ``[('state','=','cancel')]``
  after ``filter_done``; the sibling ``needs_review`` filter
  (``[('reviewer_ids','in',uid),('state','!=','done')]``, v17 :12-17) is
  **v17-only**.
* form2 (:22-36 / :23-43) — the F255 rename
  ``<xpath expr="//button[@name='action_validate']" position="attributes">
  <attribute name="name">action_confirm_create_scrap</attribute>`` (v17
  :32-34, v19 :39-41). v17 **also** wraps core's ``<group>`` in a
  ``<sheet>`` via ``position="move"`` (:27-31); v19 deliberately drops that
  (``dto_scrap/views/stock_scrap_views.xml:34-38``).
* list (:38-58 / :45-58) — ``decoration-muted="state == 'cancel'"`` +
  ``decoration-info="state == 'draft'"`` on the ``state`` field; the
  ``validation_status`` badge column is **v17-only** (:43-52).
* form (:60-76 / :60-80) — the five-field block inserted **before**
  ``//field[@name='lot_id']`` (v17 :65-71, v19 :69-75) and
  ``<button name="action_cancel" invisible="state != 'draft'" string="Cancel"
  type="object"/>`` inserted before the ``action_validate`` button (v17
  :72-74, v19 :76-78).

``dto_stock/views/stock_scrap_views.xml:3-20`` adds, inside
``//div[@name='button_box']``, an invisible ``account_move_ids`` field and
``<button type="object" name="action_view_journal_entries"
class="oe_stat_button" icon="fa-book" invisible="not account_move_ids">``
with the label span ``Journal Entries``. **There is no counter widget on
that button** — "the counter is 1 or greater" must be asserted as
``len(account_move_ids) >= 1``, never as rendered digits.

The tier mixin rewrites the rendered arch on v17 — read this before
asserting any ``readonly``
-------------------------------------------------------------------------
``TierValidation.get_view()``
(``base_tier_validation/models/tier_validation.py:749-791``) fires for
**every** ``stock.scrap`` form view on v17 because
``_tier_validation_manual_config = False``:

1. :757-765 injects the request/restart buttons after
   ``/form/header/button[last()]`` — ``stock.stock_scrap_form_view2`` has no
   ``<header>``, so nothing is injected there;
2. :766-779 prepends the validation alert and appends the ``review_ids``
   widget to every ``/form/sheet`` — which is the only reason the v17
   ``<sheet>`` wrap exists in the quick dialog;
3. :780-788 **adds ``readonly`` to every** ``//field[@name][not(ancestor::field)]``,
   as ``bool(review_ids)``, or ``f"({old}) or ({new})"`` when the node
   already had one (:786-787). The only exceptions are
   ``message_follower_ids`` and ``access_token`` (:13).

So on v17 the full form renders ``defect_code_description
readonly="(1) or (bool(review_ids))"`` and ``defect_code
readonly="bool(review_ids)"``, while v19 renders ``"1"`` and no attribute.
:func:`readonly_is_absolute` is the only sanctioned way to assert
"read-only under every rendering"; never hard-code ``"1"``.

Security — no new groups, no new ACL rows
------------------------------------------
``dto_tier_validation_scrap/__manifest__.py:25-37`` and
``dto_scrap/__manifest__.py:31-34`` list **only** ``views/stock_scrap_views.xml``
— no security file, no data file, and no ``res.groups`` record exists in
``dto_stock`` / ``dto_scrap`` / ``dto_tier_validation_scrap``. Core ACL rows
are ``access_stock_scrap_user … stock.group_stock_user,1,1,1,0`` and
``access_stock_scrap_manager … stock.group_stock_manager,1,1,1,1``
(``O17 stock/security/ir.model.access.csv:54-55``; ``O19 …:41-42``), so
``stock.group_stock_user`` **cannot unlink** — fixture cleanup must run
under the platform's admin session, which is why :func:`sweep_wf022` uses
``ctx.adapter.rpc`` and never a role session. The workbook's ``TD-U-04
dto_stock_mgr`` / ``TD-U-05 dto_mrp`` are test-data role labels, not group
XML ids — ``[UNVERIFIED as group ids]``; :data:`ROLE_GROUPS` maps them to
the real core groups and says so.

Data-safety constraints this module encodes
--------------------------------------------
1. **No fixture is ever validated.** A done scrap cannot be unlinked
   (``O17 :107-110``) and its posted valuation entry cannot be removed, so
   creating one would violate hard rule 3 on a populated clone. TC167 is
   therefore implemented read-only over **existing** done scraps
   (:func:`live_done_scrap_with_entries`) plus one token-scoped *draft*
   scrap for the draft ⇒ empty branch.
2. **``standard_price`` is only ever written on a zero-on-hand token
   product.** ``_change_standard_price`` skips a product whose
   ``quantity_svl <= 0`` (``O17 stock_account/models/product.py:243-248``),
   so no revaluation layer and no journal entry is posted. Writing it on a
   live product would silently recompute ``amount`` on every historical
   scrap of that product, because ``amount`` is a **stored** compute over
   the price.
3. **Fixtures are namespaced and swept.** Marker ``WF022`` plus a
   per-execution token, on ``stock.scrap.origin``, ``product.default_code``,
   ``stock.picking.origin`` and ``mrp.production.origin``. The sweep runs
   children before parents and can never raise.

The UoM trap in TC182, and the version-branch-free way around it
----------------------------------------------------------------
``uom.uom._compute_quantity`` is private (unreachable over RPC) **and its
arithmetic is inverted between the versions**: v17 computes
``qty / self.factor * to_unit.factor`` (``O17 uom/models/uom_uom.py:234-236``)
while v19 computes ``qty * self.factor / to_unit.factor``
(``O19 …:169-171``). ``uom.category_id`` exists only on v17 (``O17 :56``);
v19 replaced it with ``relative_factor`` / ``relative_uom_id``
(``O19 :36-44``). A test that reads ``factor`` and multiplies is therefore
silently wrong on one of the two versions.

The way out is a domain truth, not a version branch: **one dozen is twelve
units** under both implementations. ``uom.product_uom_unit`` is the
reference (``O17 uom/data/uom_data.xml:26-31``; ``O19 …:12-15``) and
``uom.product_uom_dozen`` is 12 (``O17 :33-38`` ``factor_inv=12``;
``O19 :21-26`` ``relative_factor=12``), so the expected value is
``12 * standard_price`` with no branch. See :data:`DOZEN_IN_REFERENCE_UNITS`.

Two v19-only wrinkles the fixtures handle by capability probe, never by
``ctx.env.version``: ``uom.product_uom_dozen`` ships ``active=False`` on v19
(``O19 uom/data/uom_data.xml:25``), and ``stock.scrap.product_uom_id``'s
domain narrowed to ``[('id','in',allowed_uom_ids)]``
(``O19 stock_scrap.py:24-28``), whose source is
``product.uom_id | product.uom_ids | seller uoms`` (:61-64). Both are view /
UI-level facts — an ORM write of the m2o is unaffected — but
:func:`allow_uom_on_product` adds the UoM to ``product.template.uom_ids``
(``O19 product/models/product_template.py:122``) when that field exists, so
the fixture is coherent in the UI too.

Also relied upon: ``uom.uom.rounding`` survives on v19 as a compute kept
explicitly "to ensure compatibility with previous calls to ``uom.rounding``"
(``O19 uom_uom.py:39, 62-67``), so DataOne's ``float_is_zero(...,
precision_rounding=self.product_uom_id.rounding)`` guard still resolves
there.

v17 / v19 deltas that touch this suite
---------------------------------------
============================  ==============================  ==============================
concern                       v17                             v19
============================  ==============================  ==============================
``product_uom_category_id``   present (``:28``)               removed → ``allowed_uom_ids``
``package_id`` comodel        ``stock.quant.package``         ``stock.package``
``product_id`` domain         ``[('type','in',['product','consu'])]``  ``[('type','=','consu')]``
``scrap_location_id`` domain  ``[('scrap_location','=',True)]``        ``[('usage','=','inventory')]``
``scrap_qty`` digits          ``'Product Unit of Measure'``    ``'Product Unit'``
core zero guard               ``float_is_zero(..., uom.rounding)``     ``product_uom_id.is_zero(qty)``
list root tag                 ``<tree>``                      ``<list>``
scrap→journal link            ``stock.move.account_move_ids``  ``stock.move.account_move_id``
``stock.valuation.layer``     a normal model                  **model file gone**
new native tagging            —                               ``scrap_reason_tag_ids`` +
                                                              ``stock.scrap.reason.tag``
                                                              (``O19 stock_scrap.py:56-59, 237-250``)
``res.users`` groups m2m      ``groups_id``                   ``group_ids``
============================  ==============================  ==============================

Every one of those either goes through ``ctx.adapter`` /
``framework.fg_common`` or is capability-probed here — no test body carries
an ``if version``.
"""
from __future__ import annotations

import uuid
import xml.etree.ElementTree as ET

from adapters.base import OdooRPCError
from framework.fg_common import form_arch, m2o_id, make_trace  # noqa: F401
from framework.qa_fixtures import with_categ

WORKFLOW = "DATAONE-WF-022"
WORKFLOW_NAME = "Scrap with Defect Coding and Approval"

trace = make_trace(WORKFLOW)

MARKER = "WF022"
#: One namespace per execution, so a rerun can never collide with its own
#: leftovers and live scrap data can never leak into a scoped search.
_TOKEN = f"{MARKER}-{uuid.uuid4().hex[:8].upper()}"


def tag(name: str) -> str:
    """Namespace a fixture value for this execution."""
    return f"{_TOKEN} {name}"


def fixture_token() -> str:
    return _TOKEN


# --------------------------------------------------------------- module names
#: The workbook's ``modules`` column, per test case. Which module actually
#: contributes the field at runtime is NOT asserted anywhere — see the module
#: docstring, §0.
MODULE_TIER_SCRAP = "dto_tier_validation_scrap"   # v17 carrier, F251-F255
MODULE_SCRAP = "dto_scrap"                        # v19 carrier, same fields
MODULE_STOCK = "dto_stock"                        # F080, the stat button


# ------------------------------------------------------------- error strings
#: ``action_confirm_create_scrap`` (v17 :99 / v19 :122) AND core
#: ``action_validate`` (O17 :200 / O19 :214) raise this same string, which is
#: exactly why TC179 must call ``action_confirm_create_scrap`` by name.
ERROR_POSITIVE_QTY = "You can only enter positive quantities."

#: ``@api.ondelete`` on core stock.scrap (O17 :110 / O19 :123).
ERROR_UNLINK_DONE_SCRAP = "You cannot delete a scrap which is done."

#: mrp.production ondelete (O17 mrp_production.py:1262) — a %s placeholder.
ERROR_MO_DELETE_SUFFIX = "cannot be deleted. Try to cancel them before."

# base_tier_validation ValidationError strings (v17 only). Exported for
# completeness; nothing in this suite creates a tier.definition, because
# tier_review has zero rows on dto_17 for every model ever.
# tier_validation.py:350-355 — note the literal newline before "Please".
ERROR_TIER_NEEDS_VALIDATION = (
    "This action needs to be validated for at least one record. \n"
    "Please request a validation."
)
# tier_validation.py:357-362
ERROR_TIER_PROCESS_OPEN = (
    "A validation process is still open for at least one record."
)
# tier_validation.py:378-386 (the %(…)s placeholders are filled at raise time)
ERROR_TIER_WRITE_UNDER_VALIDATION_PREFIX = (
    "You are not allowed to write those fields under validation."
)


# ------------------------------------------------------- the nine-code table
#: Read verbatim from dto_tier_validation_scrap/models/stock_scrap.py:52-62
#: and dto_scrap/models/stock_scrap.py:75-85 — the two tables are identical
#: character for character. This is the EXPECTED value set, not a
#: re-implementation of the compute: the lookup itself
#: (``defect_codes.get(code.upper().strip(), _('Unknown defect code'))``)
#: is private and is never reproduced in a test.
DEFECT_CODES = {
    "A": "Not in BOM",
    "B": "Received Damaged",
    "C": "Operator Error",
    "D": "Shortage",
    "E": "Fail Test",
    "F": "Overage",
    "G": "Wrong Parts Received",
    "H": "Other",
    "R": "Reference Cable",
}
#: Workbook step 10 iterates the table in this order.
DEFECT_CODE_ORDER = ["A", "B", "C", "D", "E", "F", "G", "H", "R"]

#: v17 :64 / v19 :87 — wrapped in ``_()``, but neither module ships an
#: ``i18n/`` directory, so no translation can override it on an English
#: database. ``[UNVERIFIED]`` only if the target's active language is not
#: en_US — probe ``res.lang`` before pinning the literal.
UNKNOWN_DEFECT_DESCRIPTION = "Unknown defect code"

#: v17 :66 / v19 :89 — the falsy branch writes an EMPTY STRING, not the
#: fallback. Over RPC a blank Char reads back as ``False`` on both versions,
#: so compare with ``value or ""`` (AUTOMATION_CONVENTIONS, "Blank Char/Text").
EMPTY_DEFECT_DESCRIPTION = ""


# ----------------------------------------------------------- field inventory
#: The five fields the WF-022 module adds to stock.scrap (v17 :22-44 /
#: v19 :41-63). Their presence IS the workbook's precondition.
SCRAP_EXTENSION_FIELDS = (
    "amount",
    "company_currency_id",
    "defect_code",
    "defect_code_description",
    "employee_name",
)

#: dto_stock's F080 field (dto_stock/models/stock_scrap.py:10-11).
JOURNAL_ENTRIES_FIELD = "account_move_ids"

#: Declared attributes, straight from the source, for the fields_get checks.
#: ``defect_code_description`` deliberately has NO expected ``readonly`` entry:
#: it is a stored compute with no inverse, so the ORM reports readonly=True
#: while the *view* attribute is rewritten by the tier mixin on v17 — see
#: :func:`readonly_is_absolute`.
EXPECTED_FIELD_ATTRS = {
    "amount": {"type": "monetary", "string": "Amount", "store": True,
               "help": "Estimated Amount",
               "currency_field": "company_currency_id"},
    "company_currency_id": {"type": "many2one", "relation": "res.currency",
                            "string": "Company Currency"},
    "defect_code": {"type": "char", "string": "Defect Code"},
    "defect_code_description": {"type": "char",
                                "string": "Defect Code Description",
                                "store": True},
    "employee_name": {"type": "char", "string": "Employee"},
}

#: dto_stock/models/stock_scrap.py:10-11 — Many2many, NOT stored.
EXPECTED_JOURNAL_FIELD_ATTRS = {
    "type": "many2many", "relation": "account.move",
    "string": "Journal Entries", "store": False,
}

#: The fields a scrap is normally read back with.
SCRAP_READ_FIELDS = [
    "name", "state", "origin", "product_id", "product_uom_id", "scrap_qty",
    "location_id", "scrap_location_id", "company_id", "move_ids", "date_done",
] + list(SCRAP_EXTENSION_FIELDS)


# ------------------------------------------------------------ state and views
STATE_DRAFT = "draft"
STATE_DONE = "done"
STATE_CANCEL = "cancel"
STATE_CANCEL_LABEL = "Cancelled"
#: ``selection_add`` APPENDS, so core's two values come first on both
#: versions (O17 stock_scrap.py:50-53 / O19 :50-53 are draft/done only).
EXPECTED_STATE_SELECTION = [["draft", "Draft"], ["done", "Done"],
                            ["cancel", "Cancelled"]]

VIEW_FULL_FORM = "stock.stock_scrap_form_view"          # O17 :24  / O19 :24
VIEW_QUICK_FORM = "stock.stock_scrap_form_view2"        # O17 :158 / O19 :142
VIEW_LIST = "stock.stock_scrap_tree_view"               # O17 :124 / O19 :108
VIEW_SEARCH = "stock.stock_scrap_search_view"           # O17 :4   — the root
VIEW_SEARCH_MRP_INHERIT = "mrp.stock_scrap_search_view_inherit_mrp"
VIEW_INSUFFICIENT_QTY = "stock.stock_warn_insufficient_qty_scrap_form_view"
ACTION_SCRAP_ORDERS = "stock.action_stock_scrap"        # O17 :144
MENU_SCRAP = "stock.menu_stock_scrap"                   # O17 :198
ACTION_JOURNAL_ITEMS = "account.action_account_moves_all"

#: F255 — the rename. v17 views :32-34, v19 views :39-41.
QUICK_BUTTON_RENAMED = "action_confirm_create_scrap"
#: The core name that must NOT survive in the quick dialog's rendered arch.
QUICK_BUTTON_CORE = "action_validate"
#: The core node's own label, unchanged by the rename (O17 :191 / O19 :175).
QUICK_BUTTON_STRING = "Scrap Products"

#: F254 — v17 views :72-74, v19 views :76-78.
CANCEL_BUTTON = "action_cancel"
CANCEL_BUTTON_STRING = "Cancel"
CANCEL_BUTTON_INVISIBLE = "state != 'draft'"

#: The list decorations the inherit overrides onto the ``state`` field
#: (v17 views :53-56, v19 views :53-56). Core's own ``state`` node carries
#: ``decoration-success="state == 'done'"`` and
#: ``decoration-muted="state == 'draft'"`` (O17 :139 / O19 :122), so the
#: muted decoration is genuinely REPLACED, not added.
LIST_DECORATION_MUTED = "state == 'cancel'"
LIST_DECORATION_INFO = "state == 'draft'"
#: v17-only column (v17 views :43-52) — deliberately not ported to v19.
LIST_VALIDATION_STATUS_FIELD = "validation_status"

#: The search filters. ``needs_review`` is v17-only (v17 views :12-17).
FILTER_CANCEL = "filter_cancel"
FILTER_CANCEL_DOMAIN = [("state", "=", "cancel")]
FILTER_DONE = "filter_done"            # the anchor, mrp views :39 on BOTH
FILTER_NEEDS_REVIEW = "needs_review"

#: F080 — dto_stock/views/stock_scrap_views.xml:8-17.
STAT_BUTTON = "action_view_journal_entries"
STAT_BUTTON_LABEL = "Journal Entries"
STAT_BUTTON_ICON = "fa-book"
STAT_BUTTON_INVISIBLE = "not account_move_ids"

#: dto_stock/models/stock_scrap.py:31-38 — the action dict the stat button
#: returns. ``res_model`` stays ``account.move.line`` (the xmlid's own
#: res_model, O17 account_move_views.xml:1622 / O19 :1928) and the domain is
#: built from ``account_move_ids.line_ids.ids`` (:33) — LINE ids, not move
#: ids. The context REPLACES the action's own.
JOURNAL_ACTION_NAME = "Journal Entries"
JOURNAL_ACTION_RES_MODEL = "account.move.line"
JOURNAL_ACTION_CONTEXT = {
    "search_default_group_by_move": True,
    "journal_type": "general",
    "expand": True,
}


# -------------------------------------------------------------- UoM constants
UOM_UNIT_XMLID = "uom.product_uom_unit"      # O17 uom_data.xml:26 / O19 :12
UOM_DOZEN_XMLID = "uom.product_uom_dozen"    # O17 :33            / O19 :21
#: True under BOTH conversion implementations (see the module docstring), so
#: an expected amount of ``12 * standard_price`` carries no version branch.
DOZEN_IN_REFERENCE_UNITS = 12.0


# ------------------------------------------------------------- role mapping
#: The workbook's role labels are test-data names, not group XML ids
#: ``[UNVERIFIED as group ids]`` — no ``res.groups`` record exists anywhere in
#: dto_stock / dto_scrap / dto_tier_validation_scrap. These are the real core
#: groups the labels describe. ``stock.group_stock_user`` cannot unlink
#: (ir.model.access.csv O17 :54 / O19 :41), so fixtures are always created and
#: swept with the platform's admin session, never with a role session.
ROLE_GROUPS = {
    # TD-U-04 dto_stock_mgr (Inventory Manager)
    "TD-U-04": ["stock.group_stock_manager"],
    # TD-U-05 dto_mrp (Manufacturing User)
    "TD-U-05": ["mrp.group_mrp_user", "stock.group_stock_user"],
}
ROLE_USER_PASSWORD = "QaAuto-2026!"    # disposable QA clone credential only


# ============================================================== small helpers
def expect_error(rpc_callable, *args, **kwargs):
    """Run a call the workbook expects to raise; return (raised, message).

    Never raise a bare AssertionError — the caller ``ctx.check``s the tuple
    so the platform records expected vs actual (AUTOMATION_CONVENTIONS,
    "Errors").
    """
    try:
        rpc_callable(*args, **kwargs)
        return False, "no error raised"
    except OdooRPCError as exc:
        return True, str(exc)


def search_count(rpc, model: str, domain: list) -> int:
    return rpc.call(model, "search_count", domain)


def fields_get(rpc, model: str, names, attributes=None) -> dict:
    """``fields_get`` for a name list. Names the model does not carry are
    simply absent from the result (``models.py: fields_get`` filters on
    ``allfields``), which is what the precondition probes rely on."""
    return rpc.call(model, "fields_get", list(names), attributes=attributes)


def state_selection(rpc) -> list:
    """``[[value, label], ...]`` for ``stock.scrap.state``."""
    info = fields_get(rpc, "stock.scrap", ["state"], attributes=["selection"])
    return [list(pair) for pair in (info.get("state", {}).get("selection") or [])]


# ----------------------------------------------------------------- arch tools
def arch_text(value) -> str:
    """Normalise a ``get_view()['arch']`` payload to ``str``.

    On v17 the tier mixin finishes with ``res["arch"] = etree.tostring(doc)``
    (tier_validation.py:789), i.e. **bytes**. Odoo serialises those through
    ``date_utils.json_default`` → ``ustr`` (O17 odoo/tools/date_utils.py:220,
    odoo/http.py:1660), so they arrive decoded — but normalising here costs
    nothing and makes the test independent of that chain.
    """
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-8", "replace")
    return value if isinstance(value, str) else str(value)


def parse_arch(arch) -> ET.Element:
    """Parse an arch string with the stdlib parser (no lxml in this venv).

    ``xml.etree`` supports ``.//tag[@attr='value']`` predicates, which is all
    this suite needs; it does NOT support ``not()``/``last()``, so absence is
    asserted by an empty match list rather than by a negative xpath.
    """
    return ET.fromstring(arch_text(arch))


def scrap_arch(ctx, view_type: str = "form") -> str:
    """The arch of ``stock.scrap``'s DEFAULT view of that type.

    Routed through ``fg_common.form_arch`` so ``'tree'``/``'list'`` resolves
    per version via ``ctx.adapter.list_view_type`` — no version branch here.
    Note the default form is the FULL form; the quick dialog must be fetched
    by xmlid with :func:`view_arch`.
    """
    return arch_text(form_arch(ctx, "stock.scrap", view_type))


def view_arch(ctx, xmlid: str, view_type: str = "form") -> str:
    """The rendered arch of ONE named view.

    ``get_view(view_id, view_type)`` exists on both versions
    (O17 ir_ui_view.py:2613 / O19 :3138). This is the only way to reach
    ``stock.stock_scrap_form_view2``, which is not ``stock.scrap``'s default
    form — and reading the rendered arch is the only assertion that catches
    a view inherit that loaded cleanly and matched nothing.
    """
    rpc = ctx.adapter.rpc
    view_id = rpc.ref(xmlid)
    if not view_id:
        ctx.blocked(f"XML id {xmlid!r} does not resolve on {ctx.env.key} "
                    f"(db={ctx.env.db}) — the view this case asserts against "
                    f"is not in the database at all.")
    return arch_text(rpc.call("stock.scrap", "get_view", view_id,
                              view_type)["arch"])


def buttons_named(root: ET.Element, name: str) -> list:
    """Every ``<button name="…">`` node in the arch, at any depth."""
    return root.findall(f".//button[@name='{name}']")


def field_node(root: ET.Element, name: str):
    """The first ``<field name="…">`` node, or None."""
    nodes = root.findall(f".//field[@name='{name}']")
    return nodes[0] if nodes else None


def field_order(root: ET.Element) -> list:
    """Every ``@name`` of every ``<field>`` in document order.

    TC180 step 2 ("the Defect Code and Employee fields appear immediately
    before the Lot/Serial field") is an ordering assertion, and the inherit
    that produces it is ``<xpath expr="//field[@name='lot_id']"
    position="before">`` (v17 views :65 / v19 :69).
    """
    return [node.get("name") for node in root.iter("field") if node.get("name")]


def readonly_of(root: ET.Element, field_name: str):
    """The rendered ``readonly`` modifier of a field node, or None."""
    node = field_node(root, field_name)
    return None if node is None else node.get("readonly")


def readonly_is_absolute(value) -> bool:
    """True when a rendered ``readonly`` modifier is unconditionally on.

    v19 renders ``"1"``. v17 renders ``"(1) or (bool(review_ids))"``, because
    ``TierValidation.get_view`` rewrites every field node's modifier as
    ``f"({old}) or ({new})"`` (tier_validation.py:784-788). Both mean "always
    read-only"; hard-coding ``"1"`` would make a correct v17 target FAIL.
    """
    if value is None:
        return False
    text = str(value).strip()
    return text == "1" or text.startswith("(1) or (")


def blank(value) -> str:
    """A blank Char reads back as ``False`` over RPC on both versions."""
    return value or ""


# ============================================================== preconditions
def missing_scrap_extension(rpc) -> list:
    """Which of the five WF-022 fields ``stock.scrap`` is NOT carrying."""
    present = fields_get(rpc, "stock.scrap", SCRAP_EXTENSION_FIELDS,
                         attributes=["type"])
    return [name for name in SCRAP_EXTENSION_FIELDS if name not in present]


def scrap_extension_presence(rpc) -> dict:
    """``{field: bool}`` for the five WF-022 fields — one mismatch dict."""
    missing = set(missing_scrap_extension(rpc))
    return {name: name not in missing for name in SCRAP_EXTENSION_FIELDS}


def check_scrap_extension(ctx):
    """The workbook precondition, implemented as a LOUD assertion.

    The workbook's precondition for TC178-TC183 is "dto_tier_validation_scrap
    is installed". Because that module is now ``installable = False``
    (__manifest__.py:56) while v17 skips a not-installable module even when
    the DB row says installed (O17 odoo/modules/graph.py:72-75), a missing
    field is a *result*, not an environment problem — so it is asserted, not
    skipped. See the module docstring, §0.
    """
    ctx.check("stock.scrap carries the WF-022 field set "
              "(defect_code, defect_code_description, employee_name, amount, "
              "company_currency_id)",
              expected={name: True for name in SCRAP_EXTENSION_FIELDS},
              actual=scrap_extension_presence(ctx.adapter.rpc))


def require_scrap_extension(ctx):
    """The BLOCKED form, for a helper that cannot build a fixture without it."""
    missing = missing_scrap_extension(ctx.adapter.rpc)
    if missing:
        ctx.blocked(
            f"stock.scrap is missing {', '.join(missing)} on {ctx.env.key} "
            f"(db={ctx.env.db}) — neither {MODULE_TIER_SCRAP} nor "
            f"{MODULE_SCRAP} is contributing the WF-022 fields. Note "
            f"{MODULE_TIER_SCRAP}/__manifest__.py:56 declares "
            f"installable=False and Odoo 17 skips a not-installable module "
            f"even when it is state='installed' in the database "
            f"(odoo/modules/graph.py:72-75).")


def check_journal_entries_field(ctx):
    """F080's field, asserted loudly for the same reason as above."""
    rpc = ctx.adapter.rpc
    ctx.check(f"stock.scrap carries {JOURNAL_ENTRIES_FIELD} "
              f"({MODULE_STOCK}/models/stock_scrap.py:10-11)",
              expected=True,
              actual=rpc.field_exists("stock.scrap", JOURNAL_ENTRIES_FIELD))


def require_journal_entries_field(ctx):
    rpc = ctx.adapter.rpc
    if not rpc.field_exists("stock.scrap", JOURNAL_ENTRIES_FIELD):
        ctx.blocked(
            f"stock.scrap.{JOURNAL_ENTRIES_FIELD} is absent on {ctx.env.key} "
            f"(db={ctx.env.db}) — {MODULE_STOCK} is not contributing the F080 "
            f"Journal Entries stat button, so there is nothing to open.")


def require_mrp(ctx):
    """TC178 step 3 drives ``mrp.production.button_scrap()``."""
    rpc = ctx.adapter.rpc
    if not rpc.model_exists("mrp.production"):
        ctx.blocked(
            f"mrp is not installed on {ctx.env.key} (db={ctx.env.db}) — the "
            "quick-scrap dialog is reached from a manufacturing order "
            "(mrp/models/mrp_production.py:2160 on v17, :2406 on v19) and "
            "the Cancelled search filter's anchor lives in "
            f"{VIEW_SEARCH_MRP_INHERIT}.")


def has_valuation_layer_model(rpc) -> bool:
    """v17 has ``stock.valuation.layer``; v19 deleted the model file
    (``O19 addons/stock_account/models/`` has ``product_value.py`` instead)."""
    return rpc.model_exists("stock.valuation.layer")


# =================================================================== sweeping
def sweep_each(rpc, model: str, domain: list) -> dict:
    """Unlink matches ONE AT A TIME. Never raises. Returns the two id lists.

    ``framework.qa_fixtures.sweep_model`` issues a **single** ``unlink(ids)``
    for the whole batch and swallows the error
    (``framework/qa_fixtures.py:55-61``), so one undeletable row leaves every
    deletable sibling behind. That is exactly what happens to this suite's
    pickings: :func:`add_stock` validates its receipt, and core refuses to
    unlink a picking holding a ``done`` move (``unlink()`` →
    ``move_ids._action_cancel()``, O17 stock/models/stock_picking.py:904-907,
    which raises ``You cannot cancel a stock move that has been set to
    'Done'.``, O17 stock/models/stock_move.py:1778-1780). Row-by-row deletion
    keeps that residue from taking :func:`make_picking`'s removable fixtures
    with it. Same shape as :func:`drop_scraps`, which already does this for
    scraps.
    """
    deleted, kept = [], []
    for rec_id in rpc.search(model, domain):
        try:
            rpc.unlink(model, [rec_id])
            deleted.append(rec_id)
        except OdooRPCError:
            kept.append(rec_id)
    return {"deleted": deleted, "kept": kept}


def sweep_wf022(rpc) -> dict:
    """Best-effort teardown of this suite's namespace, CHILDREN FIRST.

    Never raises: every unlink is swallowed, per model and per row. Matching
    is on ``MARKER`` rather than on the current token, so a previous
    execution's leftovers are removed too (idempotence, hard rule 3).
    Returns ``{"<model>": [ids that could NOT be removed], ...}``.

    Ordering rationale:

    1. ``stock.scrap`` first — it references the fixture products, and a
       ``done`` scrap cannot be unlinked at all (O17 stock_scrap.py:107-110),
       so the domain excludes that state rather than letting one done row
       fail the whole batch. No fixture here is ever validated, so a done row
       under the marker would be a defect worth leaving behind.
    2. ``mrp.production`` — ``unlink()`` calls ``action_cancel()`` first
       (O17 mrp_production.py:944-949), so a confirmed MO comes out cleanly.
    3. ``stock.picking``, then ``mrp.bom``.
    4. ``stock.quant`` rows of the fixture products, then the products.

    KNOWN, DOCUMENTED RESIDUE — this sweep is **not** a clean one:

    * :func:`add_stock` validates an incoming picking, so each call leaves a
      ``done`` receipt plus its move that Odoo will never delete (the two
      citations in :func:`sweep_each`). They stay, namespaced under
      ``MARKER``, and every later run steps over them instead of failing.
    * Their quants therefore survive as well: a non-superuser unlinking a
      quant is routed through ``inventory_quantity = 0`` + ``_apply_inventory()``
      (``_unlink_except_wrong_permission``, O17 stock/models/stock_quant.py:375-382)
      and ``dto_cycle_count/models/stock_quant.py:23`` overrides
      ``_apply_inventory`` with a call whose first line is ``ensure_one()`` —
      *Expected singleton* on this target (recorded in
      ``tests/wf025/common.py:204-214``).
    * With a quant and a done move still pointing at them, the fixture
      **products** cannot be unlinked either, so they are **archived** as the
      fallback — the same pattern as ``framework/qa_fixtures.py:37-52``
      (``sweep_products``). Archived rows carry ``default_code`` under the
      marker and the domains here all include ``active in (True, False)``,
      so nothing accumulates twice.

    No pre-existing business record is touched by any of this (hard rule 3):
    every domain is anchored on ``MARKER``.
    """
    kept = {}
    kept["stock.scrap"] = sweep_each(
        rpc, "stock.scrap",
        [("origin", "like", MARKER), ("state", "!=", STATE_DONE)])["kept"]

    if rpc.model_exists("mrp.production"):
        kept["mrp.production"] = sweep_each(
            rpc, "mrp.production", [("origin", "like", MARKER)])["kept"]
    # Row by row: a validated receipt from add_stock is undeletable and would
    # otherwise take make_picking's deletable fixtures down with it.
    kept["stock.picking"] = sweep_each(
        rpc, "stock.picking", [("origin", "like", MARKER)])["kept"]
    if rpc.model_exists("mrp.bom"):
        kept["mrp.bom"] = sweep_each(rpc, "mrp.bom",
                                     [("code", "like", MARKER)])["kept"]

    product_domain = [("default_code", "like", MARKER),
                      ("active", "in", [True, False])]
    product_ids = rpc.search("product.product", product_domain)
    if product_ids:
        kept["stock.quant"] = sweep_each(
            rpc, "stock.quant", [("product_id", "in", product_ids)])["kept"]
    for model in ("product.product", "product.template"):
        survivors = sweep_each(rpc, model, product_domain)["kept"]
        if survivors:
            # Referenced by the undeletable done move / quant: archive
            # instead, exactly as framework/qa_fixtures.py:45-52 does.
            try:
                rpc.write(model, survivors, {"active": False})
            except OdooRPCError:
                pass
        kept[model] = survivors
    return {model: ids for model, ids in kept.items() if ids}


class FixtureEnvironmentGap(RuntimeError):
    """The target lacks a record every fixture builder in this suite needs.

    Raised by the environment-ref helpers below **instead of a bare
    ``AssertionError``** (AUTOMATION_CONVENTIONS.md:88-90) and converted into
    a recorded ``BLOCKED`` verdict by :func:`open_namespace`, which every
    test in this suite calls before it builds anything. An environment gap is
    a precondition verdict, not an AUTOMATION_ERROR.
    """


def open_namespace(ctx):
    """Sweep previous leftovers, prove the environment refs, announce the token."""
    rpc = ctx.adapter.rpc
    with ctx.step(f"Sweep previous {MARKER} fixtures and open a fresh namespace"):
        residue = sweep_wf022(rpc)
        ctx.log(f"fixture token = {_TOKEN}")
        if residue:
            ctx.log(f"[sweep] not removable, left in place under {MARKER} "
                    f"(see sweep_wf022's docstring — validated receipts, "
                    f"their quants and the archived products): {residue!r}")
        # Only the piece EVERY case needs is gated here — the warehouse stock
        # location, which make_scrap defaults location_id to. The
        # picking-specific refs are gated inside add_stock / make_picking
        # instead, so a case that never builds a picking (TC167, TC182) is
        # not blocked by their absence.
        try:
            home = stock_location(rpc)
        except FixtureEnvironmentGap as exc:
            ctx.blocked(f"{ctx.env.key} (db={ctx.env.db}) cannot host this "
                        f"suite's fixtures: {exc}. Every case here creates a "
                        f"stock.scrap, whose location_id defaults to the "
                        f"warehouse stock location, so there is nothing to "
                        f"assert without one.")
        ctx.log(f"fixture stock location = {home}")


def drop_scraps(rpc, scrap_ids):
    """Remove fixture scraps, swallowing the done-scrap guard. Never raises."""
    ids = [i for i in (scrap_ids or []) if i]
    if not ids:
        return
    for scrap_id in ids:
        try:
            rpc.unlink("stock.scrap", [scrap_id])
        except OdooRPCError:
            pass


# ============================================================ environment refs
def warehouse(rpc) -> dict:
    rows = rpc.search_read("stock.warehouse", [],
                           ["lot_stock_id", "view_location_id", "company_id"],
                           limit=1, order="id")
    if not rows:
        raise FixtureEnvironmentGap("no stock.warehouse exists on the target")
    return rows[0]


def stock_location(rpc) -> int:
    """The warehouse's stock location — the scrap's default ``location_id``
    (``_compute_location_id``, O17 stock_scrap.py:62-74)."""
    return m2o_id(warehouse(rpc)["lot_stock_id"])


def scrap_location(rpc) -> int:
    """The default ``scrap_location_id``.

    v17 selects on ``scrap_location = True`` (stock_scrap.py:43-46) and v19
    on ``usage = 'inventory'`` (:43-46). Probing the column rather than the
    version keeps the branch out of the test bodies.
    """
    if rpc.field_exists("stock.location", "scrap_location"):
        rows = rpc.search_read("stock.location",
                               [("scrap_location", "=", True)], ["id"],
                               order="id", limit=1)
        if rows:
            return rows[0]["id"]
    rows = rpc.search_read("stock.location", [("usage", "=", "inventory")],
                           ["id", "complete_name"], order="id")
    scrappy = [r for r in rows if "scrap" in (r["complete_name"] or "").lower()]
    if not rows:
        raise FixtureEnvironmentGap(
            "no stock.location with usage='inventory' exists on the target, "
            "so the default scrap_location_id cannot be resolved")
    return (scrappy or rows)[0]["id"]


def inventory_location(rpc) -> int:
    """An ``inventory``-usage location that is NOT the scrap location — the
    counterpart used to receive fixture stock through a picking."""
    rows = rpc.search_read("stock.location", [("usage", "=", "inventory")],
                           ["id", "complete_name"], order="id")
    if not rows:
        raise FixtureEnvironmentGap(
            "no stock.location with usage='inventory' exists on the target, "
            "so fixture stock cannot be received from anywhere")
    preferred = [r for r in rows
                 if "scrap" not in (r["complete_name"] or "").lower()]
    return (preferred or rows)[0]["id"]


def picking_type(rpc, code: str) -> int:
    rows = rpc.search_read("stock.picking.type", [("code", "=", code)], ["id"],
                           limit=1, order="id")
    if not rows:
        raise FixtureEnvironmentGap(
            f"no stock.picking.type with code={code!r} exists on the target")
    return rows[0]["id"]


def company_currency(rpc) -> int:
    """The currency ``stock.scrap.company_currency_id`` must resolve to —
    it is ``related='company_id.currency_id'`` (v17 :22-23 / v19 :41-42)."""
    company_id = m2o_id(warehouse(rpc)["company_id"])
    if not company_id:
        rows = rpc.search_read("res.company", [], ["currency_id"], limit=1,
                               order="id")
        return m2o_id(rows[0]["currency_id"]) if rows else None
    row = rpc.read("res.company", [company_id], ["currency_id"])[0]
    return m2o_id(row["currency_id"])


# ======================================================================= UoM
def unit_uom_id(rpc):
    """``uom.product_uom_unit`` — the reference unit on both versions."""
    return rpc.ref(UOM_UNIT_XMLID)


def dozen_uom_id(rpc):
    """``uom.product_uom_dozen``.

    Ships ``active=False`` on v19 (O19 uom/data/uom_data.xml:25) and active on
    v17. An ORM write of a Many2one to an archived record is permitted, and
    ``_compute_quantity`` reads its factor regardless, so the fixture does NOT
    unarchive it — unarchiving would modify a pre-existing record (hard rule
    3). Returns None when the xmlid is absent.
    """
    return rpc.ref(UOM_DOZEN_XMLID)


def allow_uom_on_product(rpc, product_id: int, uom_id: int) -> bool:
    """Make ``uom_id`` selectable for the product in the UI, where that idea
    exists.

    v19 narrowed ``stock.scrap.product_uom_id``'s domain to
    ``[('id','in',allowed_uom_ids)]`` (O19 stock_scrap.py:24-28), computed as
    ``product.uom_id | product.uom_ids | seller uoms`` (:61-64). v17 has no
    such field — its domain is by ``category_id`` (O17 :27). This is a view
    constraint only (an ORM write is unaffected), but adding the UoM keeps
    the fixture coherent for anyone opening it. Capability-probed, so no
    version branch reaches a test body. Returns whether anything was written.
    """
    if not uom_id or not rpc.field_exists("product.template", "uom_ids"):
        return False
    tmpl_id = product_tmpl_of(rpc, product_id)
    try:
        rpc.write("product.template", [tmpl_id], {"uom_ids": [(4, uom_id)]})
        return True
    except OdooRPCError:
        return False


# ================================================================== fixtures
def make_product(ctx, label: str, standard_price: float = 0.0,
                 storable: bool = True, uom_id=None, values=None) -> int:
    """A token-scoped product.

    Storability goes through ``ctx.adapter.storable_product_values()``
    (``type='product'`` on v17, ``type='consu' + is_storable=True`` on v19),
    never inline — AUTOMATION_CONVENTIONS, "Version-dependent behaviour".

    ``standard_price`` is safe to set at creation time: the revaluation
    branch of ``_change_standard_price`` is skipped while ``quantity_svl <= 0``
    (O17 stock_account/models/product.py:243-248), and a brand-new product
    has none.
    """
    rpc = ctx.adapter.rpc
    payload = {
        "name": tag(label),
        "default_code": f"{_TOKEN}-{label}",
        "standard_price": standard_price,
    }
    if storable:
        payload.update(ctx.adapter.storable_product_values())
    else:
        payload["type"] = "service"
    if uom_id:
        payload["uom_id"] = uom_id
        # uom_po_id must stay in the same category on v17; mirroring it is
        # what core's own onchange does. It is capability-probed, never
        # unconditional: product.template.uom_po_id exists on v17
        # (O17 product/models/product_template.py:99-102) and was REMOVED on
        # v19 (no declaration in O19 product/models/product_template.py), so
        # an unconditional create would raise Invalid field 'uom_po_id' in
        # 'product.product' there. Same probe as
        # test_scrap_valuation._pin_reference_uom.
        if rpc.field_exists("product.template", "uom_po_id"):
            payload["uom_po_id"] = uom_id
    if values:
        payload.update(values)
    return rpc.create("product.product", with_categ(rpc, payload))


def product_tmpl_of(rpc, product_id: int) -> int:
    return m2o_id(rpc.read("product.product", [product_id],
                           ["product_tmpl_id"])[0]["product_tmpl_id"])


def product_info(rpc, product_id: int) -> dict:
    """The fields ``_compute_amount`` depends on, plus the valuation setup.

    ``valuation`` / ``cost_method`` are related to
    ``categ_id.property_valuation`` / ``property_cost_method``
    (O17 stock_account/models/product.py:110-111); they are absent when
    ``stock_account`` is not installed, hence the capability probe.
    """
    fields_ = ["display_name", "default_code", "standard_price", "uom_id",
               "uom_name", "categ_id"]
    for optional in ("valuation", "cost_method", "qty_available"):
        if rpc.field_exists("product.product", optional):
            fields_.append(optional)
    return rpc.read("product.product", [product_id], fields_)[0]


def set_standard_price(rpc, product_id: int, price: float):
    """Write ``standard_price``.

    ONLY ever call this on a token-scoped product with zero on hand. On a
    live product the write posts a revaluation entry when
    ``cost_method in ('standard','average')`` and ``quantity_svl > 0``
    (O17 stock_account/models/product.py:243-252) AND silently recomputes the
    stored ``amount`` of every historical scrap of that product.
    """
    rpc.write("product.product", [product_id], {"standard_price": price})


def add_stock(ctx, product_id: int, location_id: int, qty: float):
    """Receive ``qty`` into a location through an incoming picking.

    Deliberately NOT the inventory-count path: Stage 3's ``dto_cycle_count``
    overrides ``stock.quant._apply_inventory`` and calls
    ``cycle_count_category_id._calculate_scheduled_count_date(...)``, whose
    first line is ``ensure_one()`` — with an empty cycle-count category that
    raises ``Expected singleton`` for every product (recorded in
    tests/wf025/common.py:204-214). The picking path avoids it entirely.
    """
    rpc = ctx.adapter.rpc
    if qty <= 0:
        return None
    uom_id = m2o_id(rpc.read("product.product", [product_id],
                             ["uom_id"])[0]["uom_id"])
    src = inventory_location(rpc)
    picking_id = rpc.create("stock.picking", {
        "picking_type_id": picking_type(rpc, "incoming"),
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
    return picking_id


def make_picking(ctx, product_id: int, qty: float = 1.0,
                 code: str = "incoming") -> int:
    """A confirmed, reserved picking carrying one move of the product.

    TC178 step 14 reaches the quick dialog from a picking.
    ``stock.picking.button_scrap`` only offers products whose move is not in
    ``('draft','cancel')`` (O17 stock_picking.py:1567-1569 /
    O19 :1904-1906), so the picking must be confirmed for the fixture to be
    meaningful. It is left NOT validated so cleanup can remove it.
    """
    rpc = ctx.adapter.rpc
    uom_id = m2o_id(rpc.read("product.product", [product_id],
                             ["uom_id"])[0]["uom_id"])
    if code == "incoming":
        src, dest = inventory_location(rpc), stock_location(rpc)
    else:
        src, dest = stock_location(rpc), inventory_location(rpc)
    picking_id = rpc.create("stock.picking", {
        "picking_type_id": picking_type(rpc, code),
        "location_id": src,
        "location_dest_id": dest,
        "origin": tag("PICK"),
        "move_ids": [(0, 0, {
            "product_id": product_id,
            "product_uom": uom_id,
            "product_uom_qty": qty,
            "location_id": src,
            "location_dest_id": dest,
        })],
    })
    rpc.call("stock.picking", "action_confirm", [picking_id])
    try:
        rpc.call("stock.picking", "action_assign", [picking_id])
    except OdooRPCError:
        pass
    return picking_id


def make_bom(rpc, finished_id: int, lines, product_qty: float = 1.0) -> int:
    """``lines = [(component_id, qty_per_bom), ...]``."""
    return rpc.create("mrp.bom", {
        "product_tmpl_id": product_tmpl_of(rpc, finished_id),
        "code": tag("BOM"),
        "product_qty": product_qty,
        "type": "normal",
        "bom_line_ids": [(0, 0, {"product_id": pid, "product_qty": qty})
                         for pid, qty in lines],
    })


def make_mo(ctx, finished_id: int, bom_id: int, qty: float = 1.0,
            confirm: bool = True) -> int:
    """A manufacturing order under the token, confirmed by default.

    ``mrp.production.button_scrap`` builds its ``product_ids`` context from
    ``move_raw_ids`` not in ``('done','cancel')`` plus done ``move_finished_ids``
    (O17 mrp_production.py:2168-2169 / O19 :2414-2415), so the MO needs a BOM
    and a confirm for the component to be offerable in the dialog.
    Removable in ``finally:`` — ``unlink()`` cancels first (O17 :944-949).
    """
    rpc = ctx.adapter.rpc
    mo_id = rpc.create("mrp.production", {
        "product_id": finished_id,
        "bom_id": bom_id,
        "product_qty": qty,
        "origin": tag("MO"),
    })
    if confirm:
        rpc.call("mrp.production", "action_confirm", [mo_id])
    return mo_id


def make_scrap(ctx, product_id: int, qty: float = 1.0, uom_id=None,
               location_id=None, values=None) -> int:
    """A DRAFT ``stock.scrap`` under the token.

    Nothing in this suite ever validates one: a done scrap cannot be unlinked
    (O17 stock_scrap.py:107-110) and its posted valuation entry cannot be
    removed, so creating one would be an irreversible write to a populated
    clone (hard rule 3).

    ``location_id`` and ``scrap_location_id`` are precomputed by core
    (``_compute_location_id`` :62-74, ``_compute_scrap_location_id`` :76-85),
    so only ``product_id`` is strictly required; both are passed explicitly
    anyway so the fixture does not depend on the target's warehouse defaults.
    """
    rpc = ctx.adapter.rpc
    if uom_id is None:
        uom_id = m2o_id(rpc.read("product.product", [product_id],
                                 ["uom_id"])[0]["uom_id"])
    payload = {
        "product_id": product_id,
        "product_uom_id": uom_id,
        "scrap_qty": qty,
        "location_id": location_id or stock_location(rpc),
        "origin": tag("SCRAP"),
    }
    if values:
        payload.update(values)
    return rpc.create("stock.scrap", payload)


def read_scrap(rpc, scrap_id: int, fields_=None) -> dict:
    """Read a scrap back. Unknown fields are dropped first, so a target
    missing the WF-022 columns produces the suite's own loud precondition
    failure rather than an obscure RPC error."""
    wanted = list(fields_ or SCRAP_READ_FIELDS)
    known = fields_get(rpc, "stock.scrap", wanted, attributes=["type"])
    usable = [name for name in wanted if name in known]
    return rpc.read("stock.scrap", [scrap_id], usable)[0]


def write_scrap(rpc, scrap_id: int, values: dict) -> bool:
    return rpc.write("stock.scrap", [scrap_id], values)


def confirm_create_scrap(rpc, scrap_id: int):
    """Call F255's method BY NAME (v17 :96-109 / v19 :113-132).

    Calling the generic Validate instead would prove nothing: core's
    ``action_validate`` raises the identical zero-quantity string
    (O17 :198-200 / O19 :213-214).
    """
    return rpc.call("stock.scrap", "action_confirm_create_scrap", [scrap_id])


def cancel_scrap(rpc, scrap_id: int):
    """``action_cancel`` — v17 :80-82 / v19 :105-111. Returns None."""
    return rpc.call("stock.scrap", "action_cancel", [scrap_id])


def moves_of_scrap(rpc, scrap_id: int) -> list:
    """``stock.move`` rows linked by ``scrap_id`` (core O2m, O17 :37)."""
    return rpc.search_read("stock.move", [("scrap_id", "=", scrap_id)],
                           ["product_id", "state", "quantity", "picked",
                            "location_id", "location_dest_id"])


def on_hand_at(rpc, product_id: int, location_id: int) -> float:
    """Total quant quantity for a product at a location (exact match)."""
    rows = rpc.search_read("stock.quant",
                           [("product_id", "=", product_id),
                            ("location_id", "=", location_id)],
                           ["quantity", "reserved_quantity"])
    return sum(r["quantity"] for r in rows)


def quant_rows(rpc, product_id: int) -> list:
    return rpc.search_read("stock.quant", [("product_id", "=", product_id)],
                           ["location_id", "quantity", "reserved_quantity"],
                           order="id")


# ======================================================= F080 / valuation side
def journal_entries_of(rpc, scrap_id: int) -> list:
    """The scrap's ``account_move_ids`` as a plain id list.

    Reads the product's own computed field rather than re-deriving it, so the
    v17/v19 divergence in ``_compute_account_move_ids``'s link expression
    (``move_ids.account_move_ids`` vs ``move_ids.account_move_id``) is
    exercised rather than bypassed.
    """
    row = rpc.read("stock.scrap", [scrap_id], [JOURNAL_ENTRIES_FIELD])[0]
    return list(row.get(JOURNAL_ENTRIES_FIELD) or [])


def view_journal_entries(rpc, scrap_id: int):
    """``action_view_journal_entries()`` — dto_stock :26-40.

    Returns the act_window dict, or ``None`` when the scrap has no entries
    (the early return at :27-28).
    """
    return rpc.call("stock.scrap", "action_view_journal_entries", [scrap_id])


def account_move_rows(rpc, move_ids) -> list:
    if not move_ids:
        return []
    return rpc.search_read("account.move", [("id", "in", list(move_ids))],
                           ["name", "ref", "move_type", "state", "journal_id",
                            "date", "company_id"], order="id")


def account_move_line_rows(rpc, move_ids) -> list:
    """The journal items of the write-off entry, with their accounts.

    The expected shape on v17 is Credit = the category's ``stock_valuation``
    account, Debit = ``location_dest_id.valuation_in_account_id`` or the
    category's ``stock_output`` — a scrap move is an out-move to an
    inventory-usage location, so ``_account_entry_move`` takes the
    ``_is_out()`` branch and calls
    ``_prepare_account_move_vals(acc_valuation, acc_dest, …)`` whose signature
    is ``(credit_account_id, debit_account_id, …)``
    (O17 stock_account/models/stock_move.py:526, :587-592, :392-398).
    """
    if not move_ids:
        return []
    return rpc.search_read("account.move.line",
                           [("move_id", "in", list(move_ids))],
                           ["move_id", "account_id", "debit", "credit",
                            "name", "balance"], order="id")


def valuation_layers(rpc, stock_move_ids) -> list:
    """``stock.valuation.layer`` rows for the scrap's moves — v17 only.

    v19 deleted the model (``O19 addons/stock_account/models/`` carries
    ``product_value.py`` instead), so the caller must gate on
    :func:`has_valuation_layer_model` and ``ctx.blocked`` there rather than
    silently asserting something weaker.
    """
    if not stock_move_ids or not has_valuation_layer_model(rpc):
        return []
    return rpc.search_read("stock.valuation.layer",
                           [("stock_move_id", "in", list(stock_move_ids))],
                           ["value", "unit_cost", "quantity", "description",
                            "account_move_id", "stock_move_id", "product_id"],
                           order="id")


def live_done_scrap_with_entries(rpc, scan_limit: int = 300):
    """READ-ONLY: the newest existing ``done`` scrap that has journal entries.

    TC167's workbook fixture is "a scrap of TD-P-04 has been validated and is
    done". Creating one here is forbidden by hard rule 3 — it cannot be
    unwound (``You cannot delete a scrap which is done.``, O17 :107-110, and
    a posted valuation entry cannot be removed either). The environment holds
    797 scraps, 791 of them with an ``amount`` (DTO/WF022-README.md), so the
    case is implemented over that live population instead, read-only, and the
    adaptation is recorded in the test docstring (hard rule 5).

    Returns ``{"scrap": row, "entry_ids": [...]}``, ``None`` when no done
    scrap carries entries, or ``{"error": "<server message>", "probe": {...}}``
    when reading the field over the done population **raises**.

    That last case is not hypothetical, and it is why the ``search_read`` is
    wrapped. Selecting ``account_move_ids`` on a ``done`` scrap forces
    ``_compute_account_move_ids``' ``done`` branch, whose link expression is
    version-specific: the current tree reads
    ``res.move_ids.account_move_id`` (``dto_stock/models/stock_scrap.py:22``)
    and ``stock.move.account_move_id`` **does not exist on v17** — v17 has
    the One2many ``account_move_ids`` (``O17 stock_account/models/
    stock_move.py:19``) and v19 the Many2one ``account_move_id``
    (``O19 :51``); the v17-deployed revision reads the plural form (git
    ``6e410c8:project-addons/dto_stock/models/stock_scrap.py:17``). Which
    revision the v17 server actually loaded is reality 1 vs reality 2 of
    ``docs/WF-022_AUTOMATION_PLAN.md`` §0 and cannot be decided from source,
    so the caller turns the raise into a BLOCKED verdict naming both lines
    instead of letting an unattributed ``OdooRPCError`` escape. The *draft*
    path is already safe by construction (the ``else`` branch never
    dereferences a move) — this is the ``done`` half of the same guard.
    """
    if not rpc.field_exists("stock.scrap", JOURNAL_ENTRIES_FIELD):
        return None
    fields_ = ["name", "state", "product_id", "scrap_qty", "product_uom_id",
               "move_ids", "company_id", JOURNAL_ENTRIES_FIELD]
    if rpc.field_exists("stock.scrap", "amount"):
        fields_.append("amount")
    try:
        rows = rpc.search_read("stock.scrap", [("state", "=", STATE_DONE)],
                               fields_, order="id desc", limit=scan_limit)
    except OdooRPCError as exc:
        return {"error": str(exc),
                "probe": {
                    "stock.move.account_move_id":
                        rpc.field_exists("stock.move", "account_move_id"),
                    "stock.move.account_move_ids":
                        rpc.field_exists("stock.move", "account_move_ids")}}
    for row in rows:
        entries = list(row.get(JOURNAL_ENTRIES_FIELD) or [])
        if entries:
            return {"scrap": row, "entry_ids": entries}
    return None


# ================================================================ role users
def ensure_role_user(ctx, role: str):
    """A disposable internal user carrying the workbook role's real groups.

    The role labels (``TD-U-04``, ``TD-U-05``) are test-data names, not group
    XML ids — ``[UNVERIFIED as group ids]``; :data:`ROLE_GROUPS` records the
    mapping actually used. The groups m2m name is version-dependent
    (``groups_id`` on v17 res_users.py:384, ``group_ids`` on v19 :257) and is
    taken from ``ctx.adapter.user_groups_field`` so no branch reaches a test.

    Fixtures are still created and swept with the admin session:
    ``stock.group_stock_user`` holds no ``perm_unlink`` on ``stock.scrap``
    (ir.model.access.csv O17 :54 / O19 :41), so a role session cannot clean
    up after itself.
    """
    rpc = ctx.adapter.rpc
    groups_field = ctx.adapter.user_groups_field
    xmlids = ["base.group_user"] + ROLE_GROUPS.get(role, [])
    group_ids = [g for g in (rpc.ref(x) for x in xmlids) if g]
    login = f"qa.wf022.{role.lower().replace('-', '')}"
    found = rpc.search("res.users", [("login", "=", login),
                                     ("active", "in", [True, False])], limit=1)
    if found:
        rpc.write("res.users", found,
                  {"active": True, "password": ROLE_USER_PASSWORD,
                   groups_field: [(6, 0, group_ids)]})
        return found[0], login
    user_id = rpc.create("res.users", {
        "name": f"QA {MARKER} {role}",
        "login": login,
        "password": ROLE_USER_PASSWORD,
        groups_field: [(6, 0, group_ids)],
    })
    return user_id, login


def rpc_as_role(ctx, role: str):
    """A second authenticated RPC session for the given workbook role."""
    import copy

    from adapters.base import OdooRPC

    _uid, login = ensure_role_user(ctx, role)
    role_env = copy.copy(ctx.env)
    role_env.username = login
    role_env.password = ROLE_USER_PASSWORD
    return OdooRPC(role_env)
