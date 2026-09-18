"""DATAONE-WF-011 — valuation and reports: TC166, TC168, TC011.

Three cases that meet where a *delivery* stops being a physical movement and
becomes money on the ledger, plus the printed-output smoke that guards every
custom report. Abbreviations: ``DTO`` = ``D:/Projects/dataone/DTO-Odoo``
(v17 baseline read with ``git show main:<path>``, v19 port with
``git show UAT:<path>`` — the working tree is checked out on ``UAT``),
``O17`` = ``D:/Projects/dataone/odoo-17.0``, ``O19`` =
``D:/Projects/odoo-19.0``.

What this file proves
---------------------
**TC166 — the Journal Entries stat button.** ``dto_stock`` adds
``account_move_ids = fields.Many2many('account.move', string='Journal
Entries', compute='_compute_account_move_ids')`` — **not stored**, so it
computes on every read (``DTO main:project-addons/dto_stock/models/
stock_picking.py:11-12``). The compute is ``@api.depends('state')`` and fills
the field only for ``state == 'done'``, assigning ``False`` otherwise
(``:20-29``), which is what makes step 10's state gate real rather than
incidental. The button itself is a pure arch fact contributed by
``DTO main:project-addons/dto_stock/views/stock_picking_views.xml:8-18``::

    <field name="account_move_ids" invisible="1"/>          (:9)
    <button type="object" name="action_view_journal_entries"
        class="oe_stat_button" icon="fa-book"
        invisible="not account_move_ids">                   (:10-13)
        <div class="o_stat_info">
            <span class="o_stat_text">Journal Entries</span> (:15)

The v19 port re-anchors that record from ``printnode_base.view_picking_form``
onto ``stock.view_picking_form`` (``DTO UAT:…/stock_picking_views.xml:6-17``,
D-new-12) but leaves the button node byte-identical (``UAT :19-28``), so every
arch assertion below holds on both versions.

``action_view_journal_entries`` is **public** and returns a
JSON-serialisable dict (``main:…/stock_picking.py:49-63``, ``UAT :66-80`` —
identical):

* ``:50-51`` returns ``None`` when ``account_move_ids`` is empty;
* ``:52`` ``_for_xml_id('account.action_account_moves_all')`` — core's
  *Journal Items* action on **``account.move.line``**
  (``O17 addons/account/views/account_move_views.xml:1619-1626`` /
  ``O19 :1925-1934``), read through ``_get_action_dict`` whose readable-field
  set carries ``id``, ``xml_id``, ``type``, ``name``, ``display_name``,
  ``res_model``, ``domain``, ``context`` (``O17 odoo/addons/base/models/
  ir_actions.py:198-220`` plus the act_window extension at ``:337-343``);
* ``:54-55`` overwrite ``name`` **and** ``display_name`` with
  ``Journal Entries``;
* ``:56`` ``domain = [('id', 'in', self.account_move_ids.line_ids.ids)]`` —
  it filters **``account.move.line``** ids, not move ids, which is the single
  most misread line in this feature;
* ``:57-61`` ``context = {'search_default_group_by_move': True,
  'journal_type': 'general', 'expand': True}``. The filter that key activates
  is ``<filter string="Journal Entry" name="group_by_move" domain="[]"
  context="{'group_by': 'move_name'}"/>`` in
  ``account.view_account_move_line_filter``
  (``O17 account_move_views.xml:359`` / ``O19 :373`` — unchanged).

**TC168 — the one-character defect.** ``main:…/stock_picking.py:26`` reads
``StockScrap.search([('picking_id', '=', self.id)])`` — ``self.id``, not
``res.id`` — inside ``for res in self``. ``Id.__get__`` raises
``ValueError("Expected singleton: %s" % record)`` for any recordset of
length > 1 (``O17 odoo/fields.py:5150,5163-5174``; ``O19 odoo/orm/
models.py:5942`` raises the same string through ``ensure_one``). A
multi-record ``read`` reaches it: ``read`` → ``_read_format`` accesses
``record[name]`` per record (``O17 odoo/models.py:3583-3584, 3772-3799``),
and on a cache miss ``Field.__get__`` computes over the whole **prefetch
set**, ``recs = record._in_cache_without(self)`` (``O17 fields.py:1211-1217``)
— every id passed to the same ``read``. Only ``AccessError`` and
``MissingError`` are caught there, so the ``ValueError`` propagates. The
branch runs only for ``state == 'done'`` (``:25``), which is why the fixture
must contain done pickings or the case would pass vacuously. The v19 port
preserves the line verbatim and says so in a comment naming D-new-11
(``UAT:…/stock_picking.py:26-32``).

**TC011 — the report and paperformat inventory.** Everything the workbook's
first six SQL statements ask for is ordinary ORM data — ``ir.actions.report``,
``ir.model.data``, ``ir.ui.view`` (``type='qweb'``, ``key = report_name``),
``report.paperformat`` and ``res.company.paperformat_id``
(``O17 odoo/addons/base/models/res_company.py:68`` / ``O19 :87``) — so this
case needs no ``pg_*`` credentials and can never report BLOCKED for the lack
of them (``common.custom_reports_capture`` / ``common.default_paperformats``).
Twelve ``<record model="ir.actions.report">`` declarations exist in the v17
custom tree; ten carry their own xml id and are listed in
``common.CUSTOM_REPORT_XMLIDS``. **Three** custom paperformats each ship
``<field name="default" eval="True"/>`` —
``DTO main:project-addons/dto_base/reports/report_views.xml:6``,
``project-addons/dto_mrp/data/report_paperformat_data.xml:5`` and
``3rd-addons/location_barcode_labels/views/barcode_labels_location.xml:15`` —
on top of core's ``base.paperformat_euro`` and ``base.paperformat_us``, which
are both ``default eval="True"`` as well
(``O17 odoo/addons/base/data/report_paperformat_data.xml:6, 22``). Nothing
enforces uniqueness: ``report.paperformat`` declares ``default =
fields.Boolean('Default paper format?')`` with no constraint
(``O17 odoo/addons/base/models/report_paperformat.py:167-189`` /
``O19 :166-189``). Step 8's grep is reproduced as a read of the report's
groups field, whose name moved: ``groups_id``
(``O17 odoo/addons/base/models/ir_actions_report.py:137``) →
``group_ids`` (``O19 :182``), resolved through
``common.REPORT_GROUPS_FIELDS`` and ``field_exists``, never a version branch.

Expected outcomes
-----------------
* ``TC166`` — **EXPECTED v17 OUTCOME: PASS.** v19: PASS with a **lower**
  entry count. v19 deleted ``stock.move.account_move_ids``
  (``O17 stock_account/models/stock_move.py:19``, a One2many) in favour of the
  singular ``stock.move.account_move_id`` and batches several moves into one
  entry, and the ported compute unions with ``|``
  (``DTO UAT:…/stock_picking.py:44``, D-new-9). Nothing asserted here counts
  entries against a fixed number — step 3 asserts *greater than zero* and
  steps 6-9 are derived from whatever ``account_move_ids`` holds — so the
  semantics change is recorded in the log, not manufactured into a failure.
* ``TC168`` — **EXPECTED v17 OUTCOME: FAIL at step 5** — the multi-record read
  raises ``ValueError: Expected singleton``. That failure *is* the deliverable
  (``expected_result``: "On today's v17 code this case is expected to fail at
  step 5, 8 or 9. Record the failure; it is the defect's proof"). EXPECTED v19
  OUTCOME: **FAIL** — the defect is ported verbatim and deliberately. The case
  is written as the workbook wrote it and is **not** inverted into "asserts it
  still raises": that would contradict an immutable expected result, and the
  disagreement with the port's own probe is exactly what D-new-11 exists to
  surface (plan doc, Open Question 5).
* ``TC011`` — **EXPECTED v17 OUTCOME: FAIL at step 5** — the count of
  ``report.paperformat`` rows with ``default = True`` is at least five on the
  v17 baseline (three custom claimants plus core's two) and the workbook
  asserts exactly one. This is the workbook's own live v17 defect, not a v19
  regression, and the assertion is not weakened (hard rule 2). EXPECTED v19
  OUTCOME: PASS once the single default is signed off — the port already moved
  ``dto_base.paperformat_dto_label_sheet_dymo`` to ``default="False"`` and
  records ``dto_mrp.paperformat_us_mrp`` as the intended winner
  (``DTO UAT:project-addons/dto_base/reports/report_views.xml:5-45``), but core
  still ships two, so the count is the thing to watch.

Documented adaptations (hard rules 2, 5 and 6)
----------------------------------------------
1. **TC166 step 3's "counter" is the field value.** The stat button carries no
   ``widget="statinfo"`` and no numeric node — its body is exactly
   ``<div class="o_stat_info"><span class="o_stat_text">Journal Entries
   </span></div>`` (``views/stock_picking_views.xml:14-16``, identical on the
   port). There is therefore nothing to compare ``len(account_move_ids)``
   *against*: the field value **is** what the button would count. The step
   asserts the arch carries no counter node, and that the field is non-empty
   on the done delivery — the observable half of the workbook's sentence.
   Nothing is invented.
2. **TC166 impersonation is not performed.** Workbook step 1 says "Log in as
   TD-U-04 (Inventory Manager)"; the case asserts no access control, and the
   platform session must build the fixture anyway because
   ``dto_mrp_account/models/stock_picking.py:8-13`` refuses ``button_validate``
   on ``stock.picking_type_out`` to anyone outside *Validate Delivery Orders*,
   whose seeded members are ``base.user_root`` and ``base.user_admin``
   (``data/server_actions.xml:18-24``). The two capabilities the precondition
   names — ``stock.group_stock_manager`` and readable ``account.move`` — are
   probed and logged at step 1 instead of assumed.
3. **TC168 steps 7-8 have no browser half.** "Open Inventory → Transfers in
   list view with a Journal Entries count column added" is, server-side,
   exactly one ``search_read`` of ``stock.picking`` including
   ``account_move_ids`` over more than one record — the same code path as step
   4. It is executed as such and the equivalence is recorded rather than
   simulated with a tour that would assert the test's own clicking.
4. **TC168 step 9 does not reproduce the error, and is not made to.** The
   compute is ``@api.depends('state')`` only, so writing ``note`` invalidates
   nothing and no recompute happens. A ``state`` write would, but ``state`` is
   a stored compute with no legal direct write. The step performs the mass
   write the workbook asks for, asserts what it asks for, and logs the
   divergence.
5. **TC168 step 10 is recorded at step 4, not only at step 10.** On v17 the run
   stops at step 5, so a "record the outcome" step placed last would never
   execute. The verbatim server message is logged **and** written to an
   artifact the moment it is captured, before the assertion that fails.
6. **TC011 step 4 asserts no identity.** The workbook wants the single default
   to be "the one named in the signed decision"; no such decision is signed
   (plan doc, Open Question 1), and the two candidate answers disagree — the
   preconditions name F001's Dymo sheet while the v19 port names
   ``dto_mrp.paperformat_us_mrp``. Asserting either would encode an unsigned
   decision, so step 4 identifies the claimants, files them as an artifact and
   asserts only the anti-vacuity control that the query returned rows. Step 5's
   count is untouched.
7. **TC011 step 7 renders over HTTP.** ``_render_qweb_pdf`` is private and
   unreachable over ``call_kw``; ``GET /report/<converter>/<report_name>/<id>``
   is its only public entry point, with ``pdf`` → ``_render_qweb_pdf``,
   ``html`` → ``_render_qweb_html`` and ``text`` → ``_render_qweb_text``
   (``O17 addons/web/controllers/report.py:23-49``). Renders run against the
   first live record of each report's model, which is read-only: none of the
   twelve custom report records sets ``attachment``
   (``ir_actions_report.py:145`` on v17, ``:190`` on v19), and any that did on
   the target is skipped rather than rendered, so no attachment is ever written
   to a pre-existing business record. When every ``qweb-pdf`` render fails and
   no other does, the case reports BLOCKED naming ``wkhtmltopdf`` instead of
   charging an environment gap to the templates.
8. **TC011 requires no module.** This is a SMOKE case over whatever custom
   reports the target actually carries, so requiring any one of them would
   BLOCK the case on the very target it exists to smoke-test. The two
   purchased 3rd-party modules — ``location_barcode_labels`` and
   ``printnode_base`` — are present on the v17 baseline but their availability
   on the v19 target is an **environment** fact, not a source fact: TC001's
   own preconditions make "purchased Odoo 19 builds of printnode_base and
   location_barcode_labels are present" precondition E3/E4. So the installed
   set is logged, the capture filters by owning module, and the ten report xml
   ids read out of the v17 source are recorded-not-asserted when absent.
   *Correction to an earlier draft of this note:* ``location_barcode_labels``
   declares ``version: "2.0"``, and that does **not** fail v19's manifest
   gate. ``adapt_version`` (``O19 odoo/modules/module.py:550-568``) prefixes a
   bare ``x.y`` with the serie, yielding ``"19.0.2.0"``, which
   ``check_version`` (``:569-579``) accepts because it starts with ``"19.0."``
   (``O19 odoo/release.py:16`` — ``major_version = "19.0"``). A bare ``x.y``
   is the normal manifest form on both versions.
9. **Fixtures.** Every record this file creates is namespaced with
   ``common.fixture_token()``, swept open at the first step and removed in a
   ``finally:`` that can never raise. The one record type ``sweep_wf011`` does
   not know about is the real-time-valuation ``product.category`` — created
   only when the target has none — so it is unlinked locally, after the sweep
   has taken its products away. Validating a delivery of a real-time product
   necessarily posts an ``account.move``; posted entries cannot be unlinked,
   which is inherent to the feature under test and is why every search here is
   scoped by the execution token or by ids this run created.
"""
from __future__ import annotations

import csv
import io

from adapters.base import OdooRPCError
from framework.fg_common import m2o_id
from framework.registry import test_case
from tests.wf011.common import (CUSTOM_REPORT_MODULES, CUSTOM_REPORT_XMLIDS,
                                GROUP_ACCOUNT_READONLY, GROUP_STOCK_MANAGER,
                                PAPERFORMAT_DEFAULT_CLAIMANTS,
                                REPORT_GROUPS_FIELDS, WORKFLOW, WORKFLOW_NAME,
                                arch_of_model, custom_reports_capture,
                                default_paperformats, ensure_partner,
                                ensure_product, error_text, fixture_token, fx,
                                make_picking, open_namespace,
                                picking_form_arch,
                                picking_row, render_report,
                                require_journal_entry_button,
                                require_module_build, require_modules,
                                save_report_artifact, scrap_from_picking,
                                sweep_wf011, trace, user_has_group,
                                validate_delivery)

#: ``account.action_account_moves_all`` — core's *Journal Items* act_window,
#: the one ``action_view_journal_entries`` reshapes
#: (dto_stock/models/stock_picking.py:52).
JOURNAL_ITEMS_ACTION = "account.action_account_moves_all"
#: Its model. O17 addons/account/views/account_move_views.xml:1621 /
#: O19 :1927 — ``account.move.LINE``, which is why the domain filters line ids.
JOURNAL_ITEMS_MODEL = "account.move.line"
#: dto_stock/models/stock_picking.py:54-55 — both keys, same literal.
JOURNAL_ENTRIES_LABEL = "Journal Entries"
#: dto_stock/models/stock_picking.py:57-61, verbatim.
JOURNAL_ENTRIES_CONTEXT = {"search_default_group_by_move": True,
                           "journal_type": "general", "expand": True}
#: The search filter the context key activates, and the group-by it applies.
#: O17 account_move_views.xml:359 / O19 :373, inside
#: account.view_account_move_line_filter.
GROUP_BY_MOVE_FILTER = "group_by_move"
GROUP_BY_MOVE_CONTEXT = "{'group_by': 'move_name'}"
#: dto_stock/views/stock_picking_views.xml:10-13 (v17) == UAT :21-24 (v19).
STAT_BUTTON_METHOD = "action_view_journal_entries"
STAT_BUTTON_CLASS = "oe_stat_button"
STAT_BUTTON_ICON = "fa-book"
STAT_BUTTON_INVISIBLE = "not account_move_ids"
STAT_BUTTON_FIELD = "account_move_ids"

#: The company-dependent fields that decide whether a delivery of a product in
#: this category posts anything at all. O17 stock_account/models/
#: product.py:829-860 / O19 :740-758 — same names on both versions.
VALUATION_FIELDS = ["name", "property_valuation", "property_cost_method",
                    "property_stock_valuation_account_id",
                    "property_stock_account_output_categ_id",
                    "property_stock_account_input_categ_id",
                    "property_stock_journal"]
#: Without these two an outgoing move raises instead of posting
#: (O17 stock_account/models/stock_move.py:577 ->
#: _get_accounting_data_for_valuation).
VALUATION_REQUIRED_ACCOUNTS = ["property_stock_valuation_account_id",
                               "property_stock_account_output_categ_id"]

#: report_type -> the /report/<converter>/ route that reaches its renderer.
#: O17 addons/web/controllers/report.py:37-48.
REPORT_CONVERTERS = {"qweb-pdf": "pdf", "qweb-html": "html",
                     "qweb-text": "text"}
#: The columns the workbook's step-1 \copy asks for.
REPORT_CSV_COLUMNS = ["xml_id", "report_name", "report_type", "model",
                      "paperformat_id", "paperformat_exists",
                      "template_exists", "print_report_name"]

BLOCKED_WKHTMLTOPDF = (
    "requires wkhtmltopdf — every qweb-pdf report on this target returned a "
    "non-PDF response while the qweb-text/qweb-html renders succeeded, which "
    "is the signature of a missing or unreachable wkhtmltopdf binary rather "
    "than of a broken template (dto.conf sets bin_path; "
    "ir_actions_report._run_wkhtmltopdf is what the /report/pdf/ route ends "
    "in). Charging that to the report templates would report a defect that "
    "does not exist, so step 7's verdict is withheld. Steps 1-6 above ran and "
    "their assertions stand.")


# --------------------------------------------------------------------------
# Local helpers — none of these exists in tests/wf011/common.py, which is
# owned by another agent and is not edited here.
# --------------------------------------------------------------------------
def _role_note(ctx, role: str) -> str:
    """One log line recording the workbook role and the capabilities probed.

    See the module docstring, adaptation 2: no impersonation happens, so the
    two capabilities the precondition names are measured on the platform
    session rather than assumed. The measurement is a **groups-m2m read**
    through ``common.user_has_group`` (``all_group_ids`` on v19,
    ``ctx.adapter.user_groups_field`` on v17), never a call to
    ``res.users.has_group``: that method is ``@api.model`` on v17
    (``O17 base/models/res_users.py:1085-1086``) so ``call_kw`` mis-applies the
    args list, and ``_has_group`` answers about the SESSION user
    (``:1107-1109``) rather than the user asked about. On v19 it is a record
    method with ``ensure_one()`` (``O19 :1066, 1074``) — i.e. the name is
    public on both versions but the CALL SHAPE and the SEMANTICS are not.
    """
    rpc = ctx.adapter.rpc
    facts = {}
    for xmlid in (GROUP_STOCK_MANAGER, GROUP_ACCOUNT_READONLY):
        try:
            facts[xmlid] = user_has_group(rpc, rpc.uid, xmlid)
        except OdooRPCError as exc:                          # noqa: PERF203
            facts[xmlid] = f"unreadable: {error_text(exc)}"
    return (f"workbook role {role}: not impersonated — this case asserts no "
            f"access control and the platform session must build the fixture "
            f"anyway (dto_mrp_account/models/stock_picking.py:8-13 refuses "
            f"button_validate on stock.picking_type_out outside 'Validate "
            f"Delivery Orders'). Session uid={rpc.uid} group facts: {facts}")


def _valuation_categ(ctx):
    """A ``product.category`` whose products post valuation entries.

    Returns ``(categ_id, created)``. An existing real-time category is reused
    read-only wherever the target has one — nothing about it is written. Only
    when none exists is a token-namespaced one created, and then the account
    properties come from the company defaults through ``ir.property``, which
    ``_check_valuation_accounts`` resolves on write
    (O17 stock_account/models/product.py:872-883).

    BLOCKS, naming what is missing, when the resulting category cannot value a
    move: without a valuation and an output account
    ``_get_accounting_data_for_valuation`` raises instead of posting
    (O17 stock_account/models/stock_move.py:577), and the workbook's own
    precondition — "the product's category (TD-PC-02) has stock valuation and
    stock output accounts configured (TD-AC-04)" — is then simply not met.
    """
    rpc = ctx.adapter.rpc
    created = None
    found = []
    try:
        found = rpc.search("product.category",
                           [("property_valuation", "=", "real_time"),
                            ("property_stock_valuation_account_id", "!=",
                             False)],
                           limit=1, order="id")
    except OdooRPCError as exc:
        # company_dependent fields are searched through ir.property on v17
        # (odoo/fields.py:470, _search_company_dependent) and through the
        # jsonb column on v19; a refusal here is logged, never swallowed.
        ctx.log(f"[warn] product.category search on the valuation properties "
                f"failed ({error_text(exc)}) — falling back to creating one")
    if not found:
        created = rpc.create("product.category", {
            "name": fx("Real-Time Valuation"),
            "property_valuation": "real_time",
            "property_cost_method": "standard"})
        found = [created]
    categ_id = found[0]
    row = rpc.read("product.category", [categ_id], VALUATION_FIELDS)[0]
    ctx.log(f"valuation category {categ_id} {row.get('name')!r} "
            f"(created by this run: {bool(created)}): "
            + ", ".join(f"{f}={row.get(f)!r}" for f in VALUATION_FIELDS[1:]))
    missing = [f for f in VALUATION_REQUIRED_ACCOUNTS
               if not m2o_id(row.get(f))]
    if row.get("property_valuation") != "real_time" or missing:
        ctx.blocked(
            f"No product category on {ctx.env.key} (db={ctx.env.db}) can "
            f"value an outgoing move: category {categ_id} "
            f"{row.get('name')!r} has property_valuation="
            f"{row.get('property_valuation')!r} and is missing "
            f"{missing or 'nothing'}. The workbook precondition is 'a real-"
            "time-valuation product whose category has stock valuation and "
            "stock output accounts configured (TD-AC-04)'; without them "
            "_get_accounting_data_for_valuation raises instead of posting "
            "(O17 stock_account/models/stock_move.py:577), so the delivery "
            "produces no account.move and the Journal Entries button has "
            "nothing to open. Configure the accounts on the QA clone — never "
            "edit a live category to satisfy this test.")
    return categ_id, created


def _entries_of(rpc, picking_id: int) -> list:
    """``account_move_ids`` of ONE picking, sorted.

    Deliberately single-record: the whole of TC168 is about what a
    multi-record read does, so every other read in this file is one picking at
    a time (dto_stock/models/stock_picking.py:26).
    """
    value = rpc.read("stock.picking", [picking_id],
                     [STAT_BUTTON_FIELD])[0][STAT_BUTTON_FIELD]
    return sorted(value or [])


def _read_entries_multi(rpc, picking_ids: list) -> tuple:
    """Read ``account_move_ids`` over a whole recordset in one call.

    Returns ``(raised, message, rows)``. Never raises a bare AssertionError —
    the caller feeds the tuple to ``ctx.check`` so the platform records
    expected vs actual (conventions, "Errors").
    """
    try:
        rows = rpc.read("stock.picking", picking_ids,
                        ["name", "state", STAT_BUTTON_FIELD])
        return False, "", rows
    except OdooRPCError as exc:
        return True, error_text(exc), []


def _list_view_read(rpc, picking_ids: list) -> tuple:
    """The server call an Inventory > Transfers list with a Journal Entries
    column makes. Returns ``(raised, message, rows)`` — see the module
    docstring, adaptation 3."""
    try:
        rows = rpc.search_read("stock.picking", [("id", "in", picking_ids)],
                               ["name", "state", STAT_BUTTON_FIELD],
                               order="id")
        return False, "", rows
    except OdooRPCError as exc:
        return True, error_text(exc), []


def _stat_button_facts(arch, entries: list) -> dict:
    """Everything TC166 step 2 can observe about the button, as one dict.

    ``invisible="not account_move_ids"`` is a client-side modifier over a field
    that must itself be in the arch to be evaluated — hence the
    ``modifier_field_in_arch`` key. ``modifier_hides_it`` resolves the
    expression against the record actually under test, which is the closest an
    arch assertion gets to "is visible".
    """
    button = arch.find(f".//button[@name='{STAT_BUTTON_METHOD}']")
    label = None
    counters = []
    if button is not None:
        span = button.find(".//span[@class='o_stat_text']")
        label = (span.text or "").strip() if span is not None else None
        counters = [node.get("name") for node in button.iter("field")]
    fields_in_arch = {node.get("name") for node in arch.root.iter("field")}
    return {
        "present": button is not None,
        "type": button.get("type") if button is not None else None,
        "class": button.get("class") if button is not None else None,
        "icon": button.get("icon") if button is not None else None,
        "invisible": button.get("invisible") if button is not None else None,
        "label": label,
        "modifier_field_in_arch": STAT_BUTTON_FIELD in fields_in_arch,
        "modifier_hides_it": not entries,
        "counter_fields_inside_the_button": counters,
    }


def _action_identity(action) -> dict:
    """TC166 step 5 — which act_window came back, as one dict."""
    if not isinstance(action, dict):
        return {"id": None, "xml_id": None, "type": None, "res_model": None,
                "name": None, "display_name": None}
    return {"id": action.get("id"),
            "xml_id": action.get("xml_id"),
            "type": action.get("type"),
            "res_model": action.get("res_model"),
            "name": action.get("name"),
            "display_name": action.get("display_name")}


def _domain_shape(action) -> dict:
    """TC166 step 6 — the domain, normalised.

    Sorted, because ``self.account_move_ids.line_ids.ids`` is emitted in
    ``account.move.line``'s own ``_order`` and the assertion is about the SET
    of lines, not about row order (hard rule 5: no reliance on record ids
    beyond the ones this run created).
    """
    domain = (action or {}).get("domain") if isinstance(action, dict) else None
    if not isinstance(domain, list) or len(domain) != 1:
        return {"clauses": domain, "field": None, "operator": None,
                "ids": None}
    clause = list(domain[0])
    ids = clause[2] if len(clause) == 3 else None
    return {"clauses": 1,
            "field": clause[0] if clause else None,
            "operator": clause[1] if len(clause) > 1 else None,
            "ids": sorted(ids) if isinstance(ids, list) else ids}


def _group_by_move_filter(ctx) -> dict:
    """The search filter ``search_default_group_by_move`` switches on."""
    arch = arch_of_model(ctx, JOURNAL_ITEMS_MODEL, "search")
    node = arch.find(f".//filter[@name='{GROUP_BY_MOVE_FILTER}']")
    return {"filter_present": node is not None,
            "context": node.get("context") if node is not None else None}


def _csv_bytes(rows: list, columns: list) -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: row.get(key) for key in columns})
    return buffer.getvalue().encode("utf-8")


def _smoke_render(ctx, row: dict, attachment_prefixes: dict) -> dict:
    """Render one custom report against the first record of its model.

    Mirrors the workbook's odoo-shell loop, but through the only public entry
    point: ``GET /report/<converter>/<report_name>/<id>``
    (O17 addons/web/controllers/report.py:23-49). Read-only — a report that
    carries an ``attachment`` prefix on this target would persist a file on a
    pre-existing business record, so it is skipped rather than rendered
    (hard rule 3).
    """
    rpc = ctx.adapter.rpc
    xml_id = row["xml_id"]
    model = row.get("model")
    converter = REPORT_CONVERTERS.get(row.get("report_type"))
    result = {"xml_id": xml_id, "report_name": row.get("report_name"),
              "report_type": row.get("report_type"), "model": model}
    if attachment_prefixes.get(row.get("report_name")):
        result.update(status="SKIP (attachment prefix set)",
                      detail=f"attachment="
                             f"{attachment_prefixes[row['report_name']]!r}")
        return result
    if converter is None:
        result.update(status="SKIP (no converter)",
                      detail=f"report_type={row.get('report_type')!r}")
        return result
    if not model or not rpc.model_exists(model):
        result.update(status="SKIP (no model)", detail=f"model={model!r}")
        return result
    try:
        found = rpc.search(model, [], limit=1, order="id")
    except OdooRPCError as exc:
        result.update(status="SKIP (not searchable)", detail=error_text(exc))
        return result
    if not found:
        result.update(status="SKIP (no record)", detail=f"no {model} record")
        return result
    status, body = render_report(ctx, row["report_name"], found,
                                 converter=converter)
    if status != 200:
        result.update(status="RENDER-FAIL",
                      detail=f"HTTP {status} — {body[:200]!r}")
    elif converter == "pdf" and not body.startswith(b"%PDF"):
        result.update(status="RENDER-FAIL",
                      detail=f"HTTP 200 but {len(body)} bytes that do not "
                             f"start with %PDF")
    else:
        result.update(status="OK", detail=f"{len(body)} bytes on record "
                                          f"{found[0]}")
    return result


def _attachment_prefixes(rpc, report_names: list) -> dict:
    """``{report_name: attachment}`` for the reports that set one.

    ``attachment`` exists on both versions (O17 odoo/addons/base/models/
    ir_actions_report.py:145 / O19 :190). None of the twelve custom report
    records declares it in source, so this is expected to be empty; it is read
    from the TARGET because a database value can differ from the source.
    """
    if not report_names:
        return {}
    rows = rpc.search_read("ir.actions.report",
                           [("report_name", "in", report_names)],
                           ["report_name", "attachment"])
    return {r["report_name"]: r["attachment"] for r in rows
            if r.get("attachment")}


def _report_groups_field(rpc) -> str | None:
    """``groups_id`` on v17, ``group_ids`` on v19 — resolved, never branched
    (O17 ir_actions_report.py:137 / O19 :182)."""
    for name in REPORT_GROUPS_FIELDS:
        if rpc.field_exists("ir.actions.report", name):
            return name
    return None


def _safe_cleanup(rpc, extra=()):
    """Teardown that can never raise (hard rule 3).

    ``extra`` is a sequence of ``(model, ids)`` pairs removed AFTER the sweep,
    because ``sweep_wf011`` takes the products away first and a category with
    products still attached cannot be unlinked.
    """
    try:
        sweep_wf011(rpc)
    except Exception:                                        # noqa: BLE001
        pass
    for model, ids in extra:
        if not ids:
            continue
        try:
            rpc.unlink(model, list(ids))
        except Exception:                                    # noqa: BLE001
            pass


@test_case(
    id="TEST-WF011-TC166",
    name="The delivery's Journal Entries stat button opens its valuation "
         "entries",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_stock",
    priority="P1", kind="HYBRID", order=11166,
    description="The done delivery carries a non-empty account_move_ids and "
                "the fa-book stat button bound to it; pressing it returns "
                "account.action_account_moves_all renamed to Journal Entries, "
                "domained onto the entries' account.move.line ids and grouped "
                "by move, whose debit total equals its credit total — while a "
                "not-yet-done delivery reads zero entries.",
    traceability=trace("DATAONE-TC166"))
def test_tc166(ctx):
    rpc = ctx.adapter.rpc
    require_module_build(ctx)
    require_modules(ctx, ["dto_stock"])
    require_journal_entry_button(ctx)
    open_namespace(ctx)
    created_categ = None
    try:
        with ctx.step("Log in as TD-U-04 and open the done delivery."):
            ctx.log(_role_note(ctx, "TD-U-04 dto_stock_mgr (Inventory "
                                    "Manager)"))
            categ_id, created_categ = _valuation_categ(ctx)
            partner_id = ensure_partner(ctx, "TD-PA-01 Customer Alpha")
            product_id = ensure_product(ctx, "TD-P-01 Valued Widget",
                                        price=100.0, cost=60.0,
                                        categ_id=categ_id)
            picking_id = make_picking(ctx, code="outgoing",
                                      product_id=product_id, qty=5.0,
                                      partner_id=partner_id,
                                      label="Delivery TC166")
            validate_delivery(ctx, picking_id)
            row = picking_row(rpc, picking_id)
            # Fixture sanity, not a workbook expectation: everything below
            # describes a DONE delivery, and _compute_account_move_ids fills
            # the field for that state only (stock_picking.py:25).
            ctx.check_true("the fixture delivery reached done",
                           row["state"] == "done",
                           f"{row['name']} state={row['state']!r}")

        with ctx.step("Assert the Journal Entries stat button is visible."):
            entries = _entries_of(rpc, picking_id)
            ctx.log(f"account_move_ids on {row['name']} = {entries}")
            arch = picking_form_arch(ctx)
            ctx.check("the combined stock.picking form carries the fa-book "
                      "Journal Entries stat button, its invisible modifier "
                      "and the field that modifier reads "
                      "(dto_stock/views/stock_picking_views.xml:8-18)",
                      {"present": True, "type": "object",
                       "class": STAT_BUTTON_CLASS, "icon": STAT_BUTTON_ICON,
                       "invisible": STAT_BUTTON_INVISIBLE,
                       "label": JOURNAL_ENTRIES_LABEL,
                       "modifier_field_in_arch": True,
                       "modifier_hides_it": False,
                       "counter_fields_inside_the_button": []},
                      _stat_button_facts(arch, entries))

        with ctx.step("Assert its counter equals len(picking."
                      "account_move_ids) and is greater than zero."):
            # Adaptation 1 (module docstring): the button body is a bare
            # o_stat_text label — no widget="statinfo", no field node — so the
            # field value IS what it counts. The arch half of that statement
            # was asserted in step 2 as counter_fields_inside_the_button == [].
            ctx.check_true("the done delivery's account_move_ids is non-empty "
                           "— the value the stat button stands for",
                           len(entries) > 0,
                           f"len(account_move_ids) = {len(entries)}: "
                           f"{entries}")
            ctx.log("v19 note: _create_account_move batches several stock "
                    "moves into ONE account.move and the ported compute "
                    "unions with | (DTO UAT:dto_stock/models/"
                    "stock_picking.py:44, D-new-9), so a lower count on v19 "
                    "is a signed-off semantics change, not automatically a "
                    "defect. This step asserts 'greater than zero', never a "
                    "fixed number.")

        with ctx.step("Click the button."):
            action = rpc.call("stock.picking", STAT_BUTTON_METHOD,
                              [picking_id])
            ctx.log(f"action_view_journal_entries -> {action!r}")

        with ctx.step("Assert the action opened is "
                      "account.action_account_moves_all."):
            ctx.check("the returned act_window IS core's Journal Items "
                      "action, renamed to Journal Entries "
                      "(dto_stock/models/stock_picking.py:52-55)",
                      {"id": rpc.ref(JOURNAL_ITEMS_ACTION),
                       "xml_id": JOURNAL_ITEMS_ACTION,
                       "type": "ir.actions.act_window",
                       "res_model": JOURNAL_ITEMS_MODEL,
                       "name": JOURNAL_ENTRIES_LABEL,
                       "display_name": JOURNAL_ENTRIES_LABEL},
                      _action_identity(action))

        with ctx.step("Assert the action's domain restricts to picking."
                      "account_move_ids.line_ids."):
            # :56 filters account.move.LINE ids, not move ids — the action's
            # res_model is account.move.line, asserted in step 5.
            expected_line_ids = sorted(rpc.search(
                JOURNAL_ITEMS_MODEL, [("move_id", "in", entries)]))
            ctx.check("the domain is a single [('id','in', <the entries' "
                      "account.move.line ids>)] clause",
                      {"clauses": 1, "field": "id", "operator": "in",
                       "ids": expected_line_ids},
                      _domain_shape(action))

        with ctx.step("Assert the resulting list is grouped by entry/move."):
            context = action.get("context") if isinstance(action, dict) \
                else None
            search_filter = _group_by_move_filter(ctx)
            ctx.check("the context sets search_default_group_by_move (plus "
                      "journal_type and expand) and that filter exists in "
                      "account.view_account_move_line_filter grouping on "
                      "move_name",
                      {"context": JOURNAL_ENTRIES_CONTEXT,
                       "filter_present": True,
                       "filter_context": GROUP_BY_MOVE_CONTEXT},
                      {"context": context,
                       "filter_present": search_filter["filter_present"],
                       "filter_context": search_filter["context"]})

        with ctx.step("Assert every journal item shown belongs to an "
                      "account.move in picking.account_move_ids."):
            lines = rpc.search_read(JOURNAL_ITEMS_MODEL,
                                    [("id", "in", expected_line_ids)],
                                    ["move_id", "debit", "credit"], order="id")
            shown_moves = sorted({m2o_id(line["move_id"]) for line in lines})
            outside = sorted(move for move in shown_moves
                             if move not in entries)
            ctx.check("no journal item in the action's own domain belongs to "
                      "a move outside account_move_ids, and every entry is "
                      "represented",
                      {"items_outside_the_picking_entries": [],
                       "moves_shown": sorted(entries)},
                      {"items_outside_the_picking_entries": outside,
                       "moves_shown": shown_moves})

        with ctx.step("Assert the total of the debit column equals the total "
                      "of the credit column."):
            debit = round(sum(line["debit"] or 0.0 for line in lines), 2)
            credit = round(sum(line["credit"] or 0.0 for line in lines), 2)
            ctx.check("the journal items behind the button balance",
                      {"debit": debit, "credit": debit},
                      {"debit": debit, "credit": credit})

        with ctx.step("Open a delivery that is not yet done and assert the "
                      "stat button's counter is zero (the compute depends on "
                      "state)."):
            open_picking_id = make_picking(ctx, code="outgoing",
                                           product_id=product_id, qty=2.0,
                                           partner_id=partner_id,
                                           label="Open Delivery TC166")
            open_row = picking_row(rpc, open_picking_id)
            # Read alone: a read spanning this picking AND the done one would
            # hit the E-1 singleton defect, which is TC168's subject and must
            # not contaminate this verdict (stock_picking.py:26).
            open_entries = _entries_of(rpc, open_picking_id)
            ctx.check("a delivery that has not reached done reads an empty "
                      "account_move_ids, and the button's invisible modifier "
                      "therefore hides it",
                      {"state_is_done": False, "account_move_ids": [],
                       "modifier_hides_it": True},
                      {"state_is_done": open_row["state"] == "done",
                       "account_move_ids": open_entries,
                       "modifier_hides_it": not open_entries})
    finally:
        # Expected final state is "Nothing modified"; hard rules 3 and 5
        # outrank it for fixtures this run created. Never raises.
        _safe_cleanup(rpc, extra=(("product.category",
                                   [created_categ] if created_categ else []),))


@test_case(
    id="TEST-WF011-TC168",
    name="Recomputing account_move_ids over several pickings does not raise a "
         "singleton error",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_stock",
    priority="P1", kind="API", order=11168,
    description="Reading account_move_ids over three done pickings in one "
                "call must not raise ValueError: Expected singleton; the "
                "list-view read and a mass write over the same recordset must "
                "not either. EXPECTED v17 OUTCOME: FAIL at step 5 — "
                "dto_stock/models/stock_picking.py:26 passes self.id instead "
                "of res.id.",
    traceability=trace("DATAONE-TC168"))
def test_tc168(ctx):
    rpc = ctx.adapter.rpc
    require_module_build(ctx)
    require_modules(ctx, ["dto_stock"])
    require_journal_entry_button(ctx)
    open_namespace(ctx)
    created_categ = None
    original_notes = {}
    picking_ids = []
    try:
        with ctx.step("Log in as TD-U-04."):
            ctx.log(_role_note(ctx, "TD-U-04 dto_stock_mgr (Inventory "
                                    "Manager)"))
            # The workbook preconditions: "at least three done pickings exist,
            # at least one of which has a linked stock.scrap". The scrap branch
            # of the compute runs only for state == 'done'
            # (stock_picking.py:25),
            # so a fixture of draft pickings would pass this case vacuously.
            categ_id, created_categ = _valuation_categ(ctx)
            partner_id = ensure_partner(ctx, "TD-PA-01 Customer Alpha")
            product_id = ensure_product(ctx, "TD-P-01 Valued Widget",
                                        price=100.0, cost=60.0,
                                        categ_id=categ_id)
            for label in ("Delivery TC168 A", "Delivery TC168 B",
                          "Delivery TC168 C"):
                pid = make_picking(ctx, code="outgoing", product_id=product_id,
                                   qty=2.0, partner_id=partner_id,
                                   label=label)
                validate_delivery(ctx, pid)
                picking_ids.append(pid)
            scrap_id = scrap_from_picking(ctx, picking_ids[0], product_id, 1.0)
            ctx.log(f"fixture pickings={picking_ids} linked stock.scrap="
                    f"{scrap_id!r} (draft; never validated, so it creates no "
                    f"stock.move and no entry of its own)")

        with ctx.step("Browse the three pickings as one recordset."):
            rows = rpc.search_read("stock.picking",
                                   [("id", "in", picking_ids)],
                                   ["name", "state"], order="id")
            scraps = rpc.search("stock.scrap",
                                [("picking_id", "in", picking_ids)])
            ctx.check("the recordset is three done pickings, at least one of "
                      "them carrying a linked stock.scrap",
                      {"pickings": 3, "states": ["done", "done", "done"],
                       "linked_scraps_at_least_one": True},
                      {"pickings": len(rows),
                       "states": sorted(r["state"] for r in rows),
                       "linked_scraps_at_least_one": bool(scraps)})

        with ctx.step("Invalidate the cache for account_move_ids."):
            # Implicit and unavoidable: every RPC call commits its own
            # transaction with a fresh environment and an empty cache
            # (AUTOMATION_CONVENTIONS, "Test shape"), and account_move_ids is
            # not stored, so it is recomputed on every read regardless.
            ctx.log("cache invalidation is implicit — each /web/dataset/"
                    "call_kw call runs in its own transaction with a fresh "
                    "cache, and account_move_ids is a non-stored compute "
                    "(dto_stock/models/stock_picking.py:11-12)")

        with ctx.step("Read account_move_ids on the whole recordset in a "
                      "single call."):
            raised, message, multi_rows = _read_entries_multi(rpc, picking_ids)
            # Step 10 ("record the v17 outcome verbatim") is executed HERE as
            # well as at step 10, because on v17 the assertion in step 5 stops
            # the run before step 10 is reached (module docstring,
            # adaptation 5).
            ctx.log(f"multi-record read of account_move_ids over "
                    f"{len(picking_ids)} pickings -> raised={raised} "
                    f"message={message!r}")
            save_report_artifact(
                ctx, "tc168_multi_record_read",
                (f"pickings: {picking_ids}\nraised: {raised}\n"
                 f"server message (verbatim): {message}\n"
                 f"rows: {multi_rows!r}\n").encode("utf-8"), ".log")

        with ctx.step("Assert no ValueError: Expected singleton is raised."):
            # EXPECTED v17 OUTCOME: FAIL. dto_stock/models/stock_picking.py:26
            # passes self.id, not res.id, inside `for res in self`, and
            # Id.__get__ raises ValueError("Expected singleton: %s")
            # (O17 odoo/fields.py:5163-5174) for any recordset longer than
            # one. The workbook states the expectation outright and it is
            # immutable (hard rule 2): this is NOT inverted into "asserts it
            # still raises". The disagreement with the v19 port's own probe is
            # D-new-11 and needs a signature, not a test edit.
            ctx.check("reading account_move_ids over several pickings raises "
                      "nothing",
                      {"raised": False, "expected_singleton_error": False},
                      {"raised": raised,
                       "expected_singleton_error":
                           "Expected singleton" in message})

        with ctx.step("Assert each picking's account_move_ids is correct "
                      "individually — compare against the per-record read."):
            per_record = {pid: _entries_of(rpc, pid) for pid in picking_ids}
            from_multi = {row["id"]: sorted(row[STAT_BUTTON_FIELD] or [])
                          for row in multi_rows}
            ctx.check("the multi-record read returns exactly what three "
                      "single-record reads return",
                      per_record, from_multi)

        with ctx.step("Open Inventory > Transfers in list view with a Journal "
                      "Entries count column added, filtered to at least these "
                      "three pickings."):
            # Adaptation 3 (module docstring): server-side this list is one
            # search_read of stock.picking including account_move_ids over
            # more than one record — the same code path as step 4.
            list_raised, list_message, list_rows = _list_view_read(
                rpc, picking_ids)
            ctx.log(f"list-view read -> raised={list_raised} "
                    f"message={list_message!r} rows={len(list_rows)}")

        with ctx.step("Assert the list renders without an error dialog."):
            ctx.check("the Transfers list with a Journal Entries column reads "
                      "without raising",
                      {"raised": False, "expected_singleton_error": False,
                       "rows": len(picking_ids)},
                      {"raised": list_raised,
                       "expected_singleton_error":
                           "Expected singleton" in list_message,
                       "rows": len(list_rows)})

        with ctx.step("Perform a mass write (e.g. set the same note on all "
                      "three) and assert no singleton error is raised during "
                      "the dependent recompute."):
            original_notes = {row["id"]: row.get("note")
                              for row in rpc.read("stock.picking",
                                                  picking_ids, ["note"])}
            note = f"<p>{fixture_token()} TC168 mass write</p>"
            write_raised, write_message = False, ""
            try:
                rpc.write("stock.picking", picking_ids, {"note": note})
            except OdooRPCError as exc:
                write_raised, write_message = True, error_text(exc)
            ctx.log(f"mass write of note over {len(picking_ids)} pickings -> "
                    f"raised={write_raised} message={write_message!r}")
            ctx.check("the mass write raises no singleton error",
                      {"raised": False, "expected_singleton_error": False},
                      {"raised": write_raised,
                       "expected_singleton_error":
                           "Expected singleton" in write_message})
            # Adaptation 4 (module docstring): this step does NOT reproduce the
            # defect and is not made to. _compute_account_move_ids is
            # @api.depends('state') only (stock_picking.py:20), so writing
            # note invalidates nothing and no recompute is triggered. A state
            # write would, but state is a stored compute with no legal direct
            # write. The divergence is recorded, not manufactured.
            ctx.log("recorded divergence: the workbook expects this write to "
                    "trigger the dependent recompute. It does not — "
                    "account_move_ids depends on 'state' alone "
                    "(dto_stock/models/stock_picking.py:20), so a note write "
                    "invalidates nothing. Step 4 is the step that exercises "
                    "the defect; this one is the control.")

        with ctx.step("Record the v17 outcome verbatim, including the "
                      "traceback if one is produced."):
            record = (f"target: {ctx.env.key} (db={ctx.env.db}, Odoo "
                      f"{ctx.env.version})\n"
                      f"pickings: {picking_ids}\n"
                      f"step 4 multi-record read raised={raised}: "
                      f"{message!r}\n"
                      f"step 7 list-view read raised={list_raised}: "
                      f"{list_message!r}\n"
                      f"step 9 mass write raised={write_raised}: "
                      f"{write_message!r}\n")
            ctx.log(record)
            save_report_artifact(ctx, "tc168_outcome", record.encode("utf-8"),
                                 ".log")
    finally:
        # Workbook postcondition: "Revert the note." Done here so it runs even
        # when an earlier step failed, and one picking at a time so a refusal
        # on one cannot strand the other two. This block can never raise.
        for pid, value in original_notes.items():
            try:
                rpc.write("stock.picking", [pid], {"note": value or False})
            except Exception:                                # noqa: BLE001
                pass
        _safe_cleanup(rpc, extra=(("product.category",
                                   [created_categ] if created_categ else []),))


@test_case(
    id="TEST-WF011-TC011",
    name="Every custom ir.actions.report resolves its template and "
         "paperformat, and exactly one report.paperformat is default=True",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_base, dto_mrp, location_barcode_labels, "
           "stock_picking_auto_create_lot",
    priority="P1", kind="HYBRID", order=11011,
    description="Every report owned by a custom module resolves its QWeb "
                "template and its paperformat, renders against a live record "
                "through /report/<converter>/, and carries no groups "
                "restriction — and exactly one report.paperformat is flagged "
                "default. EXPECTED v17 OUTCOME: FAIL at step 5 — three custom "
                "modules plus core each claim the default.",
    traceability=trace("DATAONE-TC011"))
def test_tc011(ctx):
    rpc = ctx.adapter.rpc
    require_module_build(ctx)
    # Deliberately no require_modules: this is a SMOKE case over whatever
    # custom reports the target carries, and the two purchased 3rd-party
    # modules (location_barcode_labels, printnode_base) are an ENVIRONMENT
    # precondition on v19 (TC001 E3/E4), not a source fact. Requiring either
    # would BLOCK this case on the very target it smoke-tests (module
    # docstring, adaptation 8).
    try:
        with ctx.step("Dump every report owned by a custom module."):
            installed = {r["name"] for r in rpc.search_read(
                "ir.module.module",
                [("name", "in", CUSTOM_REPORT_MODULES),
                 ("state", "=", "installed")], ["name"])}
            ctx.log(f"report-owning modules installed on {ctx.env.key}: "
                    f"{sorted(installed)}; absent: "
                    f"{sorted(set(CUSTOM_REPORT_MODULES) - installed)}")
            rows = custom_reports_capture(ctx)
            for row in rows:
                ctx.log(f"  {row['xml_id']}: {row['report_name']} "
                        f"({row['report_type']}) on {row['model']} "
                        f"paperformat={row['paperformat_id']!r}")
            missing_known = [x for x in CUSTOM_REPORT_XMLIDS
                             if x not in {r["xml_id"] for r in rows}]
            ctx.log(f"of the ten report xml ids read in the v17 source, these "
                    f"are absent here (recorded, not asserted — the two "
                    f"purchased 3rd-party modules are a v19 ENVIRONMENT "
                    f"precondition, TC001 E3/E4): {missing_known}")
            save_report_artifact(ctx, "tc011_reports",
                                 _csv_bytes(rows, REPORT_CSV_COLUMNS), ".csv")
            # Anti-vacuity control: steps 2 and 3 assert emptiness, and an
            # empty capture would satisfy both for the wrong reason.
            ctx.check_true("the custom-report inventory is not empty",
                           len(rows) > 0,
                           f"{len(rows)} ir.actions.report records owned by a "
                           f"custom module")

        with ctx.step("Find any report whose QWeb template does not exist."):
            # ir.ui.view with type='qweb' and key = report_name — the ORM form
            # of the workbook's NOT EXISTS sub-select.
            no_template = sorted(
                f"{row['xml_id']} -> {row['report_name']}" for row in rows
                if row["report_type"] in REPORT_CONVERTERS
                and not row["template_exists"])
            ctx.check("every custom report's QWeb template resolves",
                      [], no_template)

        with ctx.step("Find any report pointing at a paperformat that no "
                      "longer exists."):
            dangling = sorted(
                f"{row['xml_id']} -> paperformat {row['paperformat_id']}"
                for row in rows
                if row["paperformat_id"] and not row["paperformat_exists"])
            ctx.check("no custom report points at a missing report."
                      "paperformat", [], dangling)

        with ctx.step("The default-paperformat assertion — default is a "
                      "reserved word and must be quoted."):
            defaults = default_paperformats(ctx)
            for row in defaults:
                ctx.log(f"  default=True: {row['xml_id']} {row['name']!r} "
                        f"format={row['format']!r} "
                        f"{row['page_width']}x{row['page_height']} "
                        f"{row['orientation']!r}")
            save_report_artifact(
                ctx, "tc011_default_paperformats",
                _csv_bytes(defaults, ["xml_id", "name", "format",
                                      "page_width", "page_height",
                                      "orientation"]), ".csv")
            # Adaptation 6 (module docstring): no identity is asserted. The
            # v17 source flags three custom claimants
            # (common.PAPERFORMAT_DEFAULT_CLAIMANTS) plus core's
            # base.paperformat_euro and base.paperformat_us; the v19 port
            # demotes dto_base's Dymo sheet and names dto_mrp's US Letter
            # instead, while the workbook's own preconditions name the Dymo
            # sheet through F001. Both cannot be the signed answer, and this
            # test is not the place to pick one.
            ctx.log("the single-default decision is OPEN (plan doc, Open "
                    "Question 1). v17 source claimants: "
                    f"{PAPERFORMAT_DEFAULT_CLAIMANTS}; the v19 port records "
                    "dto_mrp.paperformat_us_mrp as the intended winner (DTO "
                    "UAT:project-addons/dto_base/reports/report_views.xml:"
                    "5-45) while this case's preconditions name F001's "
                    "dto_base.paperformat_dto_label_sheet_dymo. Step 4 "
                    "identifies; it does not adjudicate.")
            ctx.check_true("the default-paperformat query returns at least "
                           "one row",
                           len(defaults) >= 1,
                           f"{len(defaults)} report.paperformat rows with "
                           f"default=True: "
                           f"{[r['xml_id'] for r in defaults]}")

        with ctx.step("Assert the count is exactly one."):
            # EXPECTED v17 OUTCOME: FAIL. Three custom modules each ship
            # <field name="default" eval="True"/> (dto_base/reports/
            # report_views.xml:6, dto_mrp/data/report_paperformat_data.xml:5,
            # location_barcode_labels/views/barcode_labels_location.xml:15) on
            # top of core's base.paperformat_euro and base.paperformat_us
            # (O17 odoo/addons/base/data/report_paperformat_data.xml:6, 22),
            # and report.paperformat carries no uniqueness constraint
            # (O17 report_paperformat.py:167-189). This is the workbook's own
            # live v17 defect; the assertion is not weakened (hard rule 2).
            ctx.check("exactly one report.paperformat is flagged default",
                      1, len(defaults))

        with ctx.step("Confirm which company-level layout actually applies, "
                      "since a company paperformat overrides the flagged "
                      "default."):
            companies = rpc.search_read("res.company", [],
                                        ["name", "paperformat_id"],
                                        order="id")
            formats = {}
            for company in companies:
                formats[company["id"]] = m2o_id(company["paperformat_id"])
                ctx.log(f"  company {company['id']} {company['name']!r} -> "
                        f"paperformat {company['paperformat_id']!r}")
            ctx.log("res.company.paperformat_id defaults to "
                    "base.paperformat_euro and is what ir.actions.report."
                    "get_paperformat() falls back to when a report names none "
                    "(O17 odoo/addons/base/models/res_company.py:68 and "
                    "ir_actions_report.py:246), so it — not the default flag "
                    "— decides the paper a report without its own format "
                    "prints on.")
            # Informational in the workbook — its expected_result names steps
            # 2, 3, 5, 7 and 8 only — so the only assertion here is the
            # anti-vacuity one: the query has to have returned something for
            # the log line above to mean anything. A company with no paper
            # format is recorded, not failed: core's default fills it at
            # install time and a blank one is a configuration finding for the
            # product owner, not a report defect.
            ctx.check_true("the company/paperformat query returns at least "
                           "one company",
                           bool(formats),
                           f"company -> paperformat: {formats}")

        with ctx.step("Smoke-render one document per report."
                      " (workbook: 'in odoo shell'; here through the report "
                      "controller, the only public entry point)"):
            prefixes = _attachment_prefixes(
                rpc, [row["report_name"] for row in rows])
            if prefixes:
                ctx.log(f"[warn] these reports carry an attachment prefix on "
                        f"this target and are SKIPPED rather than rendered, "
                        f"so no file is written to a live record: {prefixes}")
            results = [_smoke_render(ctx, row, prefixes) for row in rows]
            for result in results:
                ctx.log(f"  {result['status']}: {result['xml_id']} "
                        f"({result['report_type']}) — {result['detail']}")
            save_report_artifact(
                ctx, "tc011_render_smoke",
                _csv_bytes(results, ["xml_id", "report_name", "report_type",
                                     "model", "status", "detail"]), ".csv")
            failures = sorted(f"{r['xml_id']}: {r['detail']}"
                              for r in results if r["status"] == "RENDER-FAIL")
            pdf_attempts = [r for r in results
                            if r["report_type"] == "qweb-pdf"
                            and r["status"] in ("OK", "RENDER-FAIL")]
            pdf_failures = [r for r in pdf_attempts
                            if r["status"] == "RENDER-FAIL"]
            other_failures = [r for r in results
                              if r["status"] == "RENDER-FAIL"
                              and r["report_type"] != "qweb-pdf"]
            if (len(pdf_attempts) >= 2
                    and len(pdf_failures) == len(pdf_attempts)
                    and not other_failures):
                ctx.blocked(BLOCKED_WKHTMLTOPDF)
            ctx.check("every custom report renders, or is skipped for want of "
                      "a record — zero RENDER-FAIL",
                      [], failures)

        with ctx.step("Grep the source for any remaining groups_id on a "
                      "report record."):
            groups_field = _report_groups_field(rpc)
            if not groups_field:
                ctx.blocked(
                    "Neither ir.actions.report.groups_id (v17 odoo/addons/"
                    "base/models/ir_actions_report.py:137) nor group_ids "
                    f"(v19 :182) exists on {ctx.env.key} — the field this "
                    "step is about cannot be read, so its emptiness cannot "
                    "be asserted.")
            ctx.log(f"ir.actions.report groups field on Odoo "
                    f"{ctx.env.version}: {groups_field!r}")
            by_report_name = {row["report_name"]: row["xml_id"]
                              for row in rows}
            restricted = sorted(
                f"{by_report_name.get(found['report_name'], '?')} -> "
                f"{groups_field}={found[groups_field]}"
                for found in rpc.search_read(
                    "ir.actions.report",
                    [("report_name", "in", sorted(by_report_name)),
                     (groups_field, "!=", False)],
                    ["report_name", groups_field]))
            ctx.check("no custom report record carries a groups restriction",
                      [], restricted)
    finally:
        # Read-only case: it creates nothing. The sweep runs anyway so an
        # interrupted sibling cannot leave this suite's namespace behind.
        # Never raises.
        _safe_cleanup(rpc)
