"""DATAONE-WF-011 — the delivery box manifest (F077) and the hand-entered
transfer weights (F079): TC151, TC152, TC153, TC154, TC155, TC157.

Abbreviations used in the citations below: ``DTO`` =
``D:/Projects/dataone/DTO-Odoo`` (project addons; every line number is the
**v17 baseline**, read with ``git show main:<path>``, because the working tree
is checked out on ``UAT`` which already carries the v19 port — where the two
differ, the ported line is named too), ``O17`` =
``D:/Projects/dataone/odoo-17.0``, ``O19`` = ``D:/Projects/odoo-19.0``.

What this file proves
---------------------

**One model, one public entry point, two guards.** The whole box manifest is
``DTO project-addons/dto_stock/models/stock_picking_box.py`` (``:9-11``
``_name = 'stock.picking.box'``, ``_description = 'Delivery Box'``,
``_order = 'sequence, id'``; ``:13-14`` ``picking_id`` required with
``ondelete='cascade'``; ``:15`` ``sequence`` Integer; ``:16``
``name = fields.Char('Box', required=True)``; ``:17``
``weight = fields.Float('Weight (lb)', digits='Stock Weight', required=True)``)
plus one public method on the picking,
``DTO dto_stock/models/stock_picking.py:31-47``::

    def action_create_boxes(self):
        self.ensure_one()                                          # :32
        if self.box_count <= 0:                                    # :33
            raise UserError(_("Number of Boxes must be greater than zero."))
        self.box_ids.unlink()                                      # :35
        vals_list = [{'picking_id': self.id,
                      'name': _('Box %s') % i,                     # :39
                      'weight': self.default_box_weight,           # :40
                      'sequence': i * 10}                          # :41
                     for i in range(1, self.box_count + 1)]
        self.env['stock.picking.box'].create(vals_list)
        self.box_count = 0                                         # :46
        return True                                                # :47

Every assertion in TC151, TC152 and TC153 is one line of that method:

* ``:39`` ⇒ the five names are ``Box 1`` … ``Box 5``
  (``common.expected_box_names``);
* ``:40`` ⇒ every box carries ``default_box_weight``, not a per-box figure;
* ``:41`` ⇒ the sequences are ``10, 20, 30, 40, 50``
  (``common.expected_box_sequences``) and ``_order = 'sequence, id'``
  (``stock_picking_box.py:11``) is what makes ``box_ids`` read back in that
  order;
* ``:46`` ⇒ ``box_count`` is **reset to 0** by the action itself;
* ``:47`` ⇒ the method returns the bare ``True`` — **never** an
  ``ir.actions.act_window`` — which is how TC152 step 10 asserts *"no
  confirmation dialog was presented"* as a fact rather than as an absence;
* ``:35`` ⇒ the second press is destroy-and-recreate. TC152 proves it **by
  record id**, not by count: a count-only assertion would pass against a
  non-destructive implementation by coincidence, which is the workbook's own
  warning;
* ``:33-34`` ⇒ a zero count raises ``UserError`` with the verbatim string
  ``common.ERROR_BOX_COUNT_ZERO``. Note the operator is ``<=``, so a negative
  count raises too — unlike the box-weight constraint below.

**The weight constraint is ``== 0``, not ``<= 0``.**
``stock_picking_box.py:19-23``::

    @api.constrains('weight')
    def _check_weight(self):
        for rec in self:
            if rec.weight == 0:
                raise ValidationError(_("Weight must be greater than zero."))

So zero is refused with ``common.ERROR_BOX_WEIGHT_ZERO`` and **-3.0 is
accepted**. TC154 asserts the negative half exactly as the workbook wrote it —
it is the recorded v17 baseline (E2 / BR-6), never inverted (hard rule 2). The
workbook's ``v19_watch`` for that case is about the precision:
``digits='Stock Weight'`` resolves through ``Float.get_digits``
(``O17 odoo/fields.py:1533-1538``) to the ``decimal.precision`` record
``product.decimal_stock_weight`` — present unchanged on **both** versions
(``O17 addons/product/data/product_data.xml:27-30``; ``O19`` the same file, the
same lines). The precision v19 dropped is ``Product Unit of Measure``, a
different record. TC154 step 1 pins that pairing so a future removal fails
loudly.

**BR-4 is a view modifier, not conditional arch.**
``DTO dto_stock/views/stock_picking_views.xml:25-62`` inherits
``stock.view_picking_form`` (``:28``) and injects into ``//page[@name='extra']``
(``:30``) — an anchor confirmed present on both versions
(``O17 stock/views/stock_picking_views.xml:343``;
``O19 :326``) — first ``<field name="picking_type_code" invisible="1"/>``
(``:31``) and then ``<div invisible="picking_type_code != 'outgoing'">``
(``:32``) holding the ``Boxes`` separator (``:33``), ``box_count`` (``:36``),
``default_box_weight`` (``:37``), the ``action_create_boxes`` button with
``invisible="box_count &lt;= 0"`` (``:40-42``) and the ``box_ids`` kanban
(``:45-58``). The four elements therefore exist in the arch for **every**
picking type; only the client hides them. TC155 is written to that fact — see
*Documented adaptations* 3 below.

**The kanban card template is the v18/v19 rename detector.**
``:50`` declares ``<t t-name="kanban-box">`` on v17; the ported file declares
``<t t-name="card">`` (``DTO dto_stock/views/stock_picking_views.xml:67`` on
branch ``UAT``). The parser that changed is
``web/static/src/views/kanban/kanban_arch_parser.js:8``. The server never
validates a kanban template name, so the wrong one installs cleanly and throws
client-side. TC151 step 13 asserts the template name the **target version's**
parser looks up, via ``common.kanban_card_template(ctx)`` — the suite's one
sanctioned read of ``ctx.env.version`` (the case's subject *is* the version
delta; AUTOMATION_CONVENTIONS, "One legitimate exception").

**The weights are operator-entered.**
``DTO dto_stock/models/stock_picking.py:13-14`` redefines
``weight = fields.Float(compute=False, readonly=False)`` and
``shipping_weight = fields.Float(compute=False, readonly=False)`` over base
fields that **still carry a compute on both versions** — ``weight`` at
``O17 addons/stock_delivery/models/stock_picking.py:91``
(``compute='_cal_weight'``, ``store=True``) and ``O19 :25`` (identical);
``shipping_weight`` at ``O17 stock_delivery:97-98``
(``compute='_compute_shipping_weight'``, unstored) and, on v19, moved into core
at ``O19 addons/stock/models/stock_picking.py:666-670``
(``compute='_compute_shipping_weight'``, ``store=True``, ``readonly=False``).
The redefinition is therefore not a no-op on either version. TC157 proves the
behaviour (typed values survive a line edit) and the declaration (the compute
is genuinely off).

Documented adaptations — none of them weakens an assertion
----------------------------------------------------------
1. **Fixtures are standalone transfers, not order-driven deliveries.** The
   workbook preconditions describe *"a confirmed sales order … has produced one
   outgoing delivery"*. Every case here is about the picking itself, so the
   fixture is ``common.make_picking(code='outgoing')`` on
   ``stock.picking_type_out`` exactly — the plan's stated design for
   TC151-TC155 and TC157. Nothing in this file confirms an order, validates a
   picking or reaches ``state='done'``, so no mail, no automation and no
   accounting side effect can fire (convention rule 4). Consequently
   ``require_mail_offline`` is not needed here and is deliberately not called.
2. **Cross-case fixture reuse is refused.** TC152's preconditions say *"the
   delivery from TC151 exists with 5 boxes at 2.5, Box 3 hand-edited to 4.1"*
   and TC154/TC155/TC157 chain off the same record. Convention rule 5 forbids
   depending on another case's fixtures, so **each case rebuilds its own**
   under a fresh execution token and sweeps it in a ``finally`` that cannot
   raise. The workbook postconditions ("leave the five boxes in place",
   "regenerate 5 boxes at 2.5") are superseded by hard rules 3 and 5 for the
   same reason.
3. **TC155 steps 3 and 5 are asserted as a modifier.** *"Not present in the
   rendered form"* is literally false of the arch: BR-4 is
   ``invisible="picking_type_code != 'outgoing'"`` on one enclosing ``<div>``
   (``views/stock_picking_views.xml:32``), so the elements are present for
   every picking type and only the browser hides them. What this file asserts
   instead is strictly stronger against the v19 failure mode the workbook
   names: the modifier expression **byte-exact**
   (``common.BOXES_SECTION_INVISIBLE``), the ``<field
   name="picking_type_code" invisible="1"/>`` companion as a direct child of
   ``page[@name='extra']``, all four elements enclosed by that one div, and —
   because the expression references exactly one field and is pinned
   byte-exact — its determinate value for each of the three real fixtures. Step
   7, the anti-vacuity control, is fully covered: it is the half that catches a
   silently unapplied inherit, which is the v19 risk. The rendered-DOM half is
   browser-only and is logged as such, never faked.
4. **TC157 step 10 uses ``fields_get``, not ``picking._fields['weight'].
   compute``.** Attribute access on ``_fields`` is not reachable over RPC. The
   RPC-visible proxy is ``depends == []`` **and** ``store is True`` **and**
   ``readonly is False`` — the three description properties at
   ``O17 odoo/fields.py:861`` (``_description_store``), ``:865``
   (``_description_readonly``) and ``:873`` (``_description_depends``), served
   through ``get_description`` (``:842-856``) by ``fields_get``
   (``O17 odoo/models.py:3443-3467``). A field with a live compute always
   reports a non-empty ``depends``, so the triple distinguishes "compute
   genuinely off" from "compute coincidentally quiet" — the workbook's stated
   intent. **Gap, stated rather than papered over:** once ``dto_stock``
   redefines the field, the *base* field's compute is no longer observable over
   RPC, so the workbook's "also assert the shape of the base field" is met by
   the source citations above plus a logged reading of the neighbouring
   ``weight_bulk`` compute, not by an assertion.
5. **TC154 step 9's "record in findings/" is out of write scope.** This suite
   may only write under ``tests/wf011/``. The accepted-defect record is emitted
   as ``ctx.log`` plus a test artifact under ``ctx.artifacts_dir``.
6. **``res.users.has_group`` is never called over RPC — here or anywhere in
   this suite.** It is ``@api.model`` on v17
   (``O17 odoo/addons/base/models/res_users.py:1085-1092``), so ``call_kw``
   applies the whole args list to it and an
   ``rpc.call('res.users', 'has_group', [uid], xmlid)`` lands the id list in
   ``group_ext_id`` and raises; worse, ``_has_group`` resolves ``self._uid``
   (``:1107-1109``) — the SESSION user — so even a correctly-shaped v17 call
   answers a different question. On v19 the same name is a record method with
   ``ensure_one()`` (``O19 :1066, 1074``) and an ``AccessError`` guard against
   answering about another user (``:1075-1078``).
   Membership is therefore read from the groups m2m itself. **This file** uses
   ``common.user_group_ids`` because it needs the whole id list for a set
   comparison; ``test_delivery_security.py`` and
   ``test_valuation_and_reports.py`` use ``common.user_has_group``, which is
   the same read wrapped as a predicate (``all_group_ids`` on v19,
   ``ctx.adapter.user_groups_field`` on v17). Both are version-safe by
   construction — the suite is consistent about the *mechanism*, and only the
   return shape differs.
7. **The acting role.** Every workbook step 1 reads *"Log in as TD-U-03
   (Inventory User, stock.group_stock_user)"*. TC151 honours it literally: the
   two input fields are written and **Create Boxes is pressed from a second
   session authenticated as that user**, and the ACL grid
   ``DTO dto_stock/security/ir.model.access.csv:4-5`` is exercised in both
   directions — ``stock.group_stock_user`` ``1,1,1,1`` and ``base.group_user``
   ``1,0,0,0`` on ``stock.picking.box``, i.e. a plain internal user may read a
   manifest but not create one. The remaining cases build and press with the
   platform session and log the role, because the controls they test are
   model-level or view-level, not access rules, and the master data their
   fixtures need (products, quants) is out of an Inventory User's reach.

Expected outcomes
-----------------
* ``TC151`` — **EXPECTED v17 OUTCOME: PASS.** v19: PASS. Steps 8-12 are pure
  ORM. Step 13's arch half asserts the template name *this* version's parser
  looks up, so it passes on v17 (``kanban-box``, views ``:50``) and on v19
  (``card``, ported ``:67``) and FAILS loudly on a target where the port was
  not applied — which is the workbook's predicted v19 failure. The rendered-DOM
  half of step 13 stays browser-only on both and is recorded, not simulated.
* ``TC152`` — **EXPECTED v17 OUTCOME: PASS.** v19: PASS — ``:35``'s
  destroy-and-recreate is ported verbatim, and ``:47``'s bare ``True`` is what
  keeps step 10 honest if someone later adds the confirmation F077's Notes
  recommend.
* ``TC153`` — **EXPECTED v17 OUTCOME: PASS.** v19: PASS. Nothing in the delta
  touches either half of the guard.
* ``TC154`` — **EXPECTED v17 OUTCOME: PASS.** v19: PASS. ``== 0`` is preserved
  in the port and ``product.decimal_stock_weight`` survives. Should the port
  ever tighten the test to ``<= 0`` (F077's recommendation), step 8 FAILS —
  correctly: that is a signed-off product decision that must rewrite this case,
  not a silent edit to match new behaviour.
* ``TC155`` — **EXPECTED v17 OUTCOME: PASS.** v19: PASS while the inherit still
  applies; the ``page[@name='extra']`` anchor is confirmed present on v19
  (``O19 stock/views/stock_picking_views.xml:326``).
* ``TC157`` — **EXPECTED v17 OUTCOME: PASS.** v19: PASS. Note alongside it, as
  a data finding rather than a test result: the v19 upgrade recomputed
  ``shipping_weight`` (now a stored core compute, ``O19 stock:666-670``) and
  zeroed 3,167 operator-entered values.

Safety
------
No pre-existing business record is read-modified here. Every fixture carries
``common.fixture_token()``, each case sweeps the namespace open at its first
step and cleans up in a ``finally`` that cannot raise. Nothing is validated, so
nothing irreversible is created.
"""
from adapters.base import OdooRPCError
from framework.registry import test_case
from tests.wf011.common import (BOX_MODEL, BOXES_SECTION_INVISIBLE,
                                CREATE_BOXES_INVISIBLE, CREATE_BOXES_METHOD,
                                ERROR_BOX_COUNT_ZERO, ERROR_BOX_WEIGHT_ZERO,
                                GROUP_INTERNAL_USER, GROUP_STOCK_USER,
                                WORKFLOW, WORKFLOW_NAME, boxes_of,
                                create_boxes, ensure_partner, ensure_product,
                                ensure_user, error_text, expect_error,
                                expected_box_names, expected_box_sequences,
                                fixture_token, kanban_card_template,
                                make_picking, moves_of, open_namespace,
                                picking_form_arch, picking_row,
                                require_boxes, require_module_build,
                                require_modules, session_as, sweep_wf011,
                                trace, user_group_ids, xmlid_map)

#: The one module whose behaviour this file asserts. Everything cited in the
#: docstring above is contributed by it.
MODULE = "dto_stock"

#: dto_stock/views/stock_picking_views.xml:33 — the section's own heading.
BOXES_SEPARATOR_STRING = "Boxes"

#: dto_stock/security/ir.model.access.csv:4-5 — the declared grid on
#: stock.picking.box, as {xml_id: (read, write, create, unlink)}.
EXPECTED_BOX_ACCESS = {
    "dto_stock.stock_picking_box_group_stock_user": (True, True, True, True),
    "dto_stock.stock_picking_box_group_user": (True, False, False, False),
}

#: addons/product/data/product_data.xml:27-30 on BOTH versions — the record
#: digits='Stock Weight' resolves to (odoo/fields.py:1533-1538).
STOCK_WEIGHT_PRECISION_XMLID = "product.decimal_stock_weight"
STOCK_WEIGHT_PRECISION_NAME = "Stock Weight"


# --------------------------------------------------------------------------
# Local helpers.
#
# Each one exists because tests/wf011/common.py does not already provide it;
# none of them re-implements product behaviour, and none of them is a private
# Odoo method re-written in Python.
# --------------------------------------------------------------------------
def _attempt(callable_, *args, **kwargs):
    """Run something that may raise; return ``(raised, message, value)``.

    ``common.expect_error`` is the right shape for a pure negative case but
    discards the return value, and three steps here need both halves at once —
    TC151 step 7 asserts what ``action_create_boxes`` *returned* while also
    proving it did not raise, and the ACL control needs the refusal text
    beside the outcome. Never raises a bare ``AssertionError``: the caller
    feeds the tuple to ``ctx.check``.
    """
    try:
        return False, "", callable_(*args, **kwargs)
    except OdooRPCError as exc:
        return True, error_text(exc), None


def _r2(value) -> float:
    """Round to the two decimals ``digits='Stock Weight'`` stores.

    ``decimal.precision`` ``Stock Weight`` is ``2`` on both versions
    (product_data.xml:27-30), and ``Float.convert_to_column``
    (O17 odoo/fields.py:1545-1552) rounds on write, so comparing a Python sum
    against a column read back needs the same rounding to stay deterministic.
    """
    return round(float(value or 0.0), 2)


def _require_picking_types(ctx, codes):
    """BLOCK, with a precise reason, unless every operation code exists.

    ``common.picking_type_for`` raises ``OdooRPCError`` when a code has no
    ``stock.picking.type``, which would surface as a FAILED test about a
    missing warehouse rather than the BLOCKED verdict a missing precondition
    deserves. TC155 needs an incoming and an internal type in addition to
    ``stock.picking_type_out``.
    """
    rpc = ctx.adapter.rpc
    missing = [code for code in codes
               if not rpc.search("stock.picking.type", [("code", "=", code)],
                                 limit=1)]
    if missing:
        ctx.blocked(
            f"No stock.picking.type exists on {ctx.env.key} (db={ctx.env.db}) "
            f"for operation code(s): {', '.join(missing)}. TC155 compares the "
            "Boxes section across an incoming, an internal and an outgoing "
            "transfer, so all three types must exist before the comparison "
            "means anything — a warehouse configured without them makes the "
            "negative halves pass vacuously.")


def _role_note(role: str) -> str:
    """One log line recording the workbook role and how it is honoured."""
    return (f"workbook role {role} = Inventory User, {GROUP_STOCK_USER}. "
            f"dto_stock/security/ir.model.access.csv:4 grants that group "
            f"1,1,1,1 on {BOX_MODEL} and :5 grants {GROUP_INTERNAL_USER} "
            f"1,0,0,0. Fixture master data (products, quants) is out of an "
            f"Inventory User's reach, so fixtures are built with the platform "
            f"session; see the module docstring, adaptation 7.")


def _box_access_grid(rpc) -> dict:
    """The declared ``ir.model.access`` grid on ``stock.picking.box``.

    Read from the database rather than from the CSV, so the assertion measures
    what the target actually loaded. Keyed by XML id because ids are not
    stable (convention rule 5).
    """
    model_rows = rpc.search_read("ir.model", [("model", "=", BOX_MODEL)],
                                 ["id"], limit=1)
    if not model_rows:
        return {}
    rows = rpc.search_read(
        "ir.model.access", [("model_id", "=", model_rows[0]["id"])],
        ["perm_read", "perm_write", "perm_create", "perm_unlink"], order="id")
    names = xmlid_map(rpc, "ir.model.access", [r["id"] for r in rows])
    grid = {}
    for row in rows:
        key = names.get(row["id"], f"(no xml_id, db id {row['id']})")
        grid[key] = (bool(row["perm_read"]), bool(row["perm_write"]),
                     bool(row["perm_create"]), bool(row["perm_unlink"]))
    return grid


def _boxes_div(arch):
    """The single ``<div>`` carrying BR-4's modifier, or ``None``.

    dto_stock/views/stock_picking_views.xml:32 — matched on the modifier's
    exact text, so a reworded expression reads as "the section is gone" rather
    than silently matching some other div.
    """
    for node in arch.root.iter("div"):
        if node.get("invisible") == BOXES_SECTION_INVISIBLE:
            return node
    return None


def _named(arch, tag: str, attribute: str, value: str) -> list:
    """Every ``<tag>`` in the combined arch whose attribute equals ``value``."""
    return [node for node in arch.root.iter(tag)
            if node.get(attribute) == value]


def _extra_page_type_code(arch) -> bool:
    """Is ``<field name="picking_type_code" invisible="1"/>`` a DIRECT child of
    ``page[@name='extra']``?

    Core already carries ``picking_type_code`` elsewhere in the same form
    (``O17 stock/views/stock_picking_views.xml:133`` at the form root and
    ``:346`` inside the extra page's *group*), so a whole-arch count proves
    nothing. dto_stock's own companion field is the one injected as a direct
    child of the page at ``views/stock_picking_views.xml:31``, and that is what
    is asserted.
    """
    for page in arch.findall(".//page[@name='extra']"):
        for field in page.findall("field[@name='picking_type_code']"):
            if field.get("invisible") == "1":
                return True
    return False


def _section_facts(arch) -> dict:
    """The BR-4 section, as ONE mismatch dict (convention: never a loop).

    Counts are asserted at exactly 1 for the three ``dto_stock``-owned field
    names and for the button, because those names are contributed by this
    module alone — a second node would mean a duplicated inherit.
    """
    div = _boxes_div(arch)
    separators = _named(arch, "separator", "string", BOXES_SEPARATOR_STRING)
    box_count = _named(arch, "field", "name", "box_count")
    default_weight = _named(arch, "field", "name", "default_box_weight")
    box_ids = _named(arch, "field", "name", "box_ids")
    buttons = _named(arch, "button", "name", CREATE_BOXES_METHOD)
    inside = []
    for element in separators + box_count + default_weight + box_ids + buttons:
        inside.append(div is not None and div in arch.ancestors(element))
    return {
        "outgoing_only_div_modifier": None if div is None
        else div.get("invisible"),
        "picking_type_code_beside_it": _extra_page_type_code(arch),
        "separator_Boxes": len(separators),
        "field_box_count": len(box_count),
        "field_default_box_weight": len(default_weight),
        "field_box_ids": len(box_ids),
        "button_action_create_boxes": len(buttons),
        "every_element_inside_that_div": bool(inside) and all(inside),
        "create_boxes_button_invisible":
            buttons[0].get("invisible") if buttons else None,
    }


def _expected_section_facts() -> dict:
    """What ``dto_stock/views/stock_picking_views.xml:30-44`` must render."""
    return {
        "outgoing_only_div_modifier": BOXES_SECTION_INVISIBLE,   # :32
        "picking_type_code_beside_it": True,                     # :31
        "separator_Boxes": 1,                                    # :33
        "field_box_count": 1,                                    # :36
        "field_default_box_weight": 1,                            # :37
        "field_box_ids": 1,                                       # :45
        "button_action_create_boxes": 1,                          # :40
        "every_element_inside_that_div": True,                    # :32-59
        "create_boxes_button_invisible": CREATE_BOXES_INVISIBLE,  # :42
    }


def _kanban_facts(arch) -> dict:
    """The ``box_ids`` kanban sub-view, as one dict.

    ``get_view`` returns the fully combined arch **including** inline x2many
    sub-views, which is what makes the card template assertable without a
    browser (see tests/wf011/common.py's module docstring). The card body is
    ``<strong><t t-esc="record.name.value"/></strong>`` and
    ``<div><t t-esc="record.weight.value"/> lb</div>``
    (views/stock_picking_views.xml:51-54), so the unit suffix is the ``t``
    element's tail text.
    """
    fields_ = _named(arch, "field", "name", "box_ids")
    kanban = fields_[0].find("kanban") if fields_ else None
    if kanban is None:
        return {"kanban": False, "template_name": None, "escapes": [],
                "unit_suffix": None}
    templates = kanban.find("templates")
    card = None if templates is None else templates.find("t")
    escapes = ([node.get("t-esc") for node in card.iter("t")
                if node.get("t-esc")] if card is not None else [])
    text = "".join(card.itertext()) if card is not None else ""
    return {
        "kanban": True,
        "template_name": None if card is None else card.get("t-name"),
        "escapes": escapes,
        "unit_suffix": " ".join(text.split()) or None,
    }


def _weight_shape(rpc, model: str, field: str) -> dict:
    """The RPC-visible proxy for "the compute is genuinely off".

    ``fields_get`` serves ``store`` (O17 odoo/fields.py:861), ``readonly``
    (``:865``) and ``depends`` (``:873``) through ``get_description``
    (``:842-856``). A field with a live compute always reports a non-empty
    ``depends``; a plain stored column reports ``[]``. See the module
    docstring, adaptation 4, for why ``_fields[...].compute`` itself is not
    reachable.
    """
    description = rpc.call(model, "fields_get", [field],
                           attributes=["type", "store", "readonly", "depends",
                                       "required", "digits", "string"])
    got = description.get(field) or {}
    return {
        "type": got.get("type"),
        "store": got.get("store"),
        "readonly": got.get("readonly"),
        "depends": list(got.get("depends") or []),
    }


def _plain_compute_off() -> dict:
    """dto_stock/models/stock_picking.py:13-14 — compute=False, readonly=False,
    over a Float, which leaves an ordinary stored column."""
    return {"type": "float", "store": True, "readonly": False, "depends": []}


def _stock_weight_digits(rpc):
    """``(precision_record_exists, name, [16, digits])`` for ``Stock Weight``.

    ``Float.get_digits`` returns ``(16, precision)`` for a string ``digits``
    (O17 odoo/fields.py:1533-1538) and ``_description_digits`` publishes it
    (``:1542-1543``), so the expected pair is derived from the live
    ``decimal.precision`` row rather than hard-coded — the assertion is
    "the field resolves to THAT record", not "the digits are 2".
    """
    precision_id = rpc.ref(STOCK_WEIGHT_PRECISION_XMLID)
    if not precision_id:
        return False, None, None
    row = rpc.read("decimal.precision", [precision_id], ["name", "digits"])[0]
    return True, row["name"], [16, row["digits"]]


def _cleanup(rpc):
    """Teardown that can never raise (convention rule 3)."""
    try:
        sweep_wf011(rpc)
    except Exception:                                          # noqa: BLE001
        pass


def _preflight(ctx):
    """Everything this file needs before a single assertion is meaningful."""
    require_modules(ctx, [MODULE])
    require_module_build(ctx, [MODULE])
    require_boxes(ctx)


# ==========================================================================
# TC151
# ==========================================================================
@test_case(
    id="TEST-WF011-TC151",
    name="Create Boxes generates N named boxes at the default weight and "
         "resets the count",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module=MODULE, priority="P1", kind="HYBRID", order=11151,
    description="Pressing Create Boxes as an Inventory User on an outgoing "
                "delivery with count 5 and default weight 2.5 leaves exactly "
                "Box 1..Box 5 at 2.5, sequences 10..50 in that read-back "
                "order, and box_count reset to 0; the rendered arch declares "
                "the kanban card template this Odoo version's parser looks up.",
    traceability=trace("DATAONE-TC151"))
def test_tc151(ctx):
    rpc = ctx.adapter.rpc
    _preflight(ctx)
    open_namespace(ctx)
    try:
        with ctx.step("Log in as TD-U-03."):
            ctx.log(_role_note("TD-U-03"))
            # The declared half of the ACL control: the grid dto_stock ships
            # (security/ir.model.access.csv:4-5), read back from the target.
            grid = _box_access_grid(rpc)
            ctx.check("dto_stock declares the stock.picking.box ACL grid "
                      "(read, write, create, unlink) as its CSV does",
                      EXPECTED_BOX_ACCESS,
                      {k: v for k, v in grid.items()
                       if k in EXPECTED_BOX_ACCESS})
            stock_uid, stock_login = ensure_user(ctx, "stock",
                                                 [GROUP_STOCK_USER])
            plain_uid, plain_login = ensure_user(ctx, "plain")
            stock_group_id = rpc.ref(GROUP_STOCK_USER)
            ctx.check("TD-U-03 holds stock.group_stock_user and the control "
                      "user holds only base.group_user",
                      {"td_u_03_is_inventory_user": True,
                       "control_user_is_inventory_user": False},
                      {"td_u_03_is_inventory_user":
                           stock_group_id in user_group_ids(ctx, stock_uid),
                       "control_user_is_inventory_user":
                           stock_group_id in user_group_ids(ctx, plain_uid)})
            user_rpc = session_as(ctx.env, stock_login)
            probe_raised, probe_message, _probe = _attempt(
                user_rpc.call, "res.users", "search_count",
                [("id", "=", stock_uid)])
            if probe_raised:
                ctx.blocked(
                    f"The second RPC session for {stock_login!r} could not "
                    f"authenticate on {ctx.env.key} (db={ctx.env.db}): "
                    f"{probe_message}. This case presses Create Boxes as the "
                    "Inventory User itself, so without that session the "
                    "workbook's step 1 cannot be honoured and the ACL control "
                    "would be asserted against the admin session instead — "
                    "which proves nothing.")
            plain_rpc = session_as(ctx.env, plain_login)

        with ctx.step("Open Inventory \u2192 Transfers and open the outgoing "
                      "delivery for TD-PA-01."):
            partner_id = ensure_partner(ctx, "Customer Alpha")
            product_id = ensure_product(ctx, "Widget")
            picking_id = make_picking(ctx, code="outgoing",
                                      product_id=product_id, qty=10.0,
                                      partner_id=partner_id,
                                      label="TC151 Delivery")
            row = picking_row(rpc, picking_id,
                              ["name", "state", "picking_type_code",
                               "box_count"])
            ctx.check("the fixture is an outgoing transfer, not yet "
                      "validated, with an empty manifest",
                      {"picking_type_code": "outgoing",
                       "not_done": True, "box_count": 0, "boxes": 0},
                      {"picking_type_code": row.get("picking_type_code"),
                       "not_done": row.get("state") not in ("done", "cancel"),
                       "box_count": row.get("box_count"),
                       "boxes": len(boxes_of(rpc, picking_id))})
            # The behavioural half of the ACL control: base.group_user is
            # 1,0,0,0 on stock.picking.box (ir.model.access.csv:5), so a plain
            # internal user may search it and may not create one.
            read_raised, read_message, read_count = _attempt(
                plain_rpc.call, BOX_MODEL, "search_count",
                [("picking_id", "=", picking_id)])
            create_raised, create_message, _created = _attempt(
                plain_rpc.create, BOX_MODEL,
                {"picking_id": picking_id, "name": "ACL probe",
                 "weight": 1.0, "sequence": 10})
            ctx.log(f"plain internal user read -> raised={read_raised} "
                    f"{read_message!r}; create -> raised={create_raised} "
                    f"{create_message!r}")
            ctx.check("a plain internal user may READ the manifest and may "
                      "NOT create a box on it",
                      {"read_refused": False, "read_count": 0,
                       "create_refused": True},
                      {"read_refused": read_raised, "read_count": read_count,
                       "create_refused": create_raised})

        with ctx.step("Open the Additional Info tab."):
            arch = picking_form_arch(ctx)
            ctx.check("the Boxes section is injected into page[@name='extra'] "
                      "with every element inside the outgoing-only div "
                      "(dto_stock/views/stock_picking_views.xml:30-44)",
                      _expected_section_facts(), _section_facts(arch))

        with ctx.step("Assert the Boxes section is visible."):
            # BR-4 is a client-side modifier over one field, pinned byte-exact
            # above; for THIS record it resolves to visible.
            type_code = picking_row(
                rpc, picking_id, ["picking_type_code"])["picking_type_code"]
            div = _boxes_div(arch)
            ctx.check("on an outgoing transfer the section's modifier "
                      "resolves to visible",
                      {"modifier": BOXES_SECTION_INVISIBLE,
                       "picking_type_code": "outgoing", "hidden": False},
                      {"modifier": None if div is None
                       else div.get("invisible"),
                       "picking_type_code": type_code,
                       "hidden": type_code != "outgoing"})

        with ctx.step("Set Number of Boxes to 5."):
            user_rpc.write("stock.picking", [picking_id], {"box_count": 5})
            ctx.check("Number of Boxes reads back 5", 5,
                      picking_row(rpc, picking_id, ["box_count"])["box_count"])

        with ctx.step("Set Default Weight to 2.5."):
            user_rpc.write("stock.picking", [picking_id],
                           {"default_box_weight": 2.5})
            ctx.check("Default Weight reads back 2.5", 2.5,
                      _r2(picking_row(
                          rpc, picking_id,
                          ["default_box_weight"])["default_box_weight"]))

        with ctx.step("Click Create Boxes."):
            raised, message, result = _attempt(
                user_rpc.call, "stock.picking", CREATE_BOXES_METHOD,
                [picking_id])
            ctx.log(f"action_create_boxes as {stock_login} -> "
                    f"raised={raised} {message!r} result={result!r}")
            ctx.check("the Inventory User's press succeeds and the method "
                      "returns the bare True it is written to return "
                      "(dto_stock/models/stock_picking.py:47)",
                      {"raised": False, "result": True},
                      {"raised": raised, "result": result})

        with ctx.step("Assert len(picking.box_ids) == 5."):
            boxes = boxes_of(rpc, picking_id)
            ctx.check("the manifest holds five boxes", 5, len(boxes))

        with ctx.step("Assert the five name values are exactly Box 1, Box 2, "
                      "Box 3, Box 4, Box 5."):
            ctx.check("the names are _('Box %s') % i for i in 1..5 "
                      "(dto_stock/models/stock_picking.py:39)",
                      expected_box_names(5), [b["name"] for b in boxes])

        with ctx.step("Assert every box has weight == 2.5."):
            ctx.check("every box carries default_box_weight "
                      "(dto_stock/models/stock_picking.py:40)",
                      [2.5] * 5, [_r2(b["weight"]) for b in boxes])

        with ctx.step("Assert the sequence values are 10, 20, 30, 40, 50 and "
                      "that box_ids reads back in that order "
                      "(_order = 'sequence, id')."):
            o2m_ids = rpc.read("stock.picking", [picking_id],
                               ["box_ids"])[0]["box_ids"]
            ctx.check("sequences are i*10 and box_ids reads back in "
                      "'sequence, id' order (stock_picking_box.py:11, :41)",
                      {"sequences": expected_box_sequences(5),
                       "read_back_in_order": True},
                      {"sequences": [b["sequence"] for b in boxes],
                       "read_back_in_order":
                           list(o2m_ids) == [b["id"] for b in boxes]})

        with ctx.step("Assert picking.box_count == 0 \u2014 the count field "
                      "was reset by the action."):
            ctx.check("box_count was reset by the action itself "
                      "(dto_stock/models/stock_picking.py:46)",
                      0,
                      picking_row(rpc, picking_id, ["box_count"])["box_count"])

        with ctx.step("Assert the kanban renders five cards, each displaying "
                      "2.5 lb."):
            expected_template = kanban_card_template(ctx)
            ctx.check("the inline box_ids kanban declares the card template "
                      f"this version's parser looks up ({expected_template!r}) "
                      "and escapes name and weight with a 'lb' suffix "
                      "(views/stock_picking_views.xml:45-58; ported :67)",
                      {"kanban": True, "template_name": expected_template,
                       "escapes": ["record.name.value", "record.weight.value"],
                       "unit_suffix": "lb"},
                      _kanban_facts(arch))
            ctx.check("five box records are available for the kanban to "
                      "render, all at 2.5",
                      {"cards": 5, "weights": [2.5] * 5},
                      {"cards": len(boxes),
                       "weights": [_r2(b["weight"]) for b in boxes]})
            ctx.log("The rendered-DOM half of this step (five cards actually "
                    "painted) is browser-only and is NOT simulated here: the "
                    "kanban parser runs client-side. What is asserted is the "
                    "template name the target version's parser resolves "
                    "(kanban_arch_parser.js:8) plus the records behind it \u2014 "
                    "the pair that catches the kanban-box \u2192 card rename "
                    "the 17.5 converter does not handle.")
    finally:
        _cleanup(rpc)


# ==========================================================================
# TC152
# ==========================================================================
@test_case(
    id="TEST-WF011-TC152",
    name="A second Create Boxes press destroys the existing manifest without "
         "warning",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module=MODULE, priority="P1", kind="API", order=11152,
    description="A second press unlinks every existing stock.picking.box and "
                "recreates from scratch: the surviving ids are disjoint from "
                "the first manifest's, the hand-edited 4.1 correction is gone, "
                "and the method returns True rather than a confirmation "
                "dialog.",
    traceability=trace("DATAONE-TC152"))
def test_tc152(ctx):
    rpc = ctx.adapter.rpc
    _preflight(ctx)
    open_namespace(ctx)
    try:
        with ctx.step("Log in as TD-U-03 and open the delivery from TC151."):
            # Convention rule 5 forbids consuming TC151's fixture, so the
            # workbook's precondition is rebuilt here: 5 boxes at 2.5 with
            # Box 3 hand-corrected to 4.1. See the module docstring,
            # adaptation 2.
            ctx.log(_role_note("TD-U-03"))
            partner_id = ensure_partner(ctx, "Customer Alpha")
            product_id = ensure_product(ctx, "Widget")
            picking_id = make_picking(ctx, code="outgoing",
                                      product_id=product_id, qty=10.0,
                                      partner_id=partner_id,
                                      label="TC152 Delivery")
            create_boxes(ctx, picking_id, 5, 2.5)
            seeded = boxes_of(rpc, picking_id)
            rpc.write(BOX_MODEL, [seeded[2]["id"]], {"weight": 4.1})
            ctx.check("the precondition manifest is five boxes with Box 3 "
                      "hand-edited to 4.1",
                      {"count": 5, "weights": [2.5, 2.5, 4.1, 2.5, 2.5]},
                      {"count": len(boxes_of(rpc, picking_id)),
                       "weights": [_r2(b["weight"])
                                   for b in boxes_of(rpc, picking_id)]})

        with ctx.step("Record first_ids = picking.box_ids.ids and "
                      "first_weights = picking.box_ids.mapped('weight') \u2014 "
                      "expected [2.5, 2.5, 4.1, 2.5, 2.5]."):
            first = boxes_of(rpc, picking_id)
            first_ids = [b["id"] for b in first]
            first_weights = [_r2(b["weight"]) for b in first]
            ctx.check("first_weights", [2.5, 2.5, 4.1, 2.5, 2.5],
                      first_weights)
            ctx.log(f"first_ids = {first_ids}")

        with ctx.step("Set Number of Boxes to 3."):
            rpc.write("stock.picking", [picking_id], {"box_count": 3})
            ctx.check("Number of Boxes reads back 3", 3,
                      picking_row(rpc, picking_id, ["box_count"])["box_count"])

        with ctx.step("Set Default Weight to 1.0."):
            rpc.write("stock.picking", [picking_id],
                      {"default_box_weight": 1.0})
            ctx.check("Default Weight reads back 1.0", 1.0,
                      picking_row(rpc, picking_id,
                                  ["default_box_weight"])["default_box_weight"])

        with ctx.step("Click Create Boxes."):
            raised, message, result = _attempt(
                rpc.call, "stock.picking", CREATE_BOXES_METHOD, [picking_id])
            ctx.log(f"second action_create_boxes -> raised={raised} "
                    f"{message!r} result={result!r}")
            ctx.check("the second press runs straight through",
                      {"raised": False}, {"raised": raised})

        with ctx.step("Assert len(picking.box_ids) == 3."):
            second = boxes_of(rpc, picking_id)
            second_ids = [b["id"] for b in second]
            ctx.check("the manifest now holds three boxes", 3, len(second))

        with ctx.step("Assert set(picking.box_ids.ids).isdisjoint("
                      "set(first_ids)) \u2014 no box record from the first "
                      "manifest survives; assert by id, not by count."):
            ctx.check("the surviving ids are disjoint from the first "
                      "manifest's (dto_stock/models/stock_picking.py:35)",
                      {"disjoint": True, "overlap": []},
                      {"disjoint": set(second_ids).isdisjoint(set(first_ids)),
                       "overlap": sorted(set(second_ids) & set(first_ids))})

        with ctx.step("Assert self.env['stock.picking.box'].browse(first_ids)"
                      ".exists() returns an empty recordset."):
            survivors = rpc.search(BOX_MODEL, [("id", "in", first_ids)])
            ctx.check("every record of the first manifest was unlinked",
                      [], sorted(survivors))

        with ctx.step("Assert every surviving box has weight == 1.0 \u2014 the "
                      "4.1 correction is gone."):
            ctx.check("the hand-edited correction did not survive the "
                      "regenerate",
                      {"weights": [1.0, 1.0, 1.0], "4.1_present": False},
                      {"weights": [_r2(b["weight"]) for b in second],
                       "4.1_present": 4.1 in [_r2(b["weight"])
                                              for b in second]})

        with ctx.step("Assert the names are Box 1, Box 2, Box 3 and that no "
                      "confirmation dialog was presented at step 5."):
            # "No dialog" is asserted as a FACT about the return value:
            # action_create_boxes returns the bare True (stock_picking.py:47),
            # never an ir.actions.act_window. A future confirmation wizard
            # would have to return an action dict, and this check would catch
            # it instead of silently passing because a harness dismissed it.
            ctx.check("the names are Box 1..Box 3 and the method returned "
                      "True, not an action dict "
                      "(dto_stock/models/stock_picking.py:39, :47)",
                      {"names": expected_box_names(3), "returned": True,
                       "returned_an_action_dict": False},
                      {"names": [b["name"] for b in second],
                       "returned": result,
                       "returned_an_action_dict": isinstance(result, dict)})

        with ctx.step("Assert picking.box_count == 0."):
            ctx.check("box_count was reset again "
                      "(dto_stock/models/stock_picking.py:46)",
                      0,
                      picking_row(rpc, picking_id, ["box_count"])["box_count"])
    finally:
        # The workbook's postcondition ("regenerate 5 boxes at 2.5") is
        # superseded by hard rules 3 and 5 — TC165 builds its own fixture.
        _cleanup(rpc)


# ==========================================================================
# TC153
# ==========================================================================
@test_case(
    id="TEST-WF011-TC153",
    name="Create Boxes with a zero count raises the exact error",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module=MODULE, priority="P2", kind="HYBRID", order=11153,
    description="Both halves of the zero-count guard asserted separately: the "
                "button's invisible modifier is exactly 'box_count <= 0', and "
                "action_create_boxes called directly with box_count = 0 raises "
                "UserError('Number of Boxes must be greater than zero.') and "
                "creates nothing.",
    traceability=trace("DATAONE-TC153"))
def test_tc153(ctx):
    rpc = ctx.adapter.rpc
    _preflight(ctx)
    open_namespace(ctx)
    try:
        with ctx.step("Log in as TD-U-03 and open the delivery."):
            ctx.log(_role_note("TD-U-03"))
            partner_id = ensure_partner(ctx, "Customer Alpha")
            product_id = ensure_product(ctx, "Widget")
            picking_id = make_picking(ctx, code="outgoing",
                                      product_id=product_id, qty=10.0,
                                      partner_id=partner_id,
                                      label="TC153 Delivery")
            row = picking_row(rpc, picking_id,
                              ["picking_type_code", "box_count"])
            ctx.check("the fixture is an outgoing transfer with "
                      "box_count == 0 (the workbook's precondition)",
                      {"picking_type_code": "outgoing", "box_count": 0},
                      {"picking_type_code": row.get("picking_type_code"),
                       "box_count": row.get("box_count")})

        with ctx.step("Open Additional Info and assert the Create Boxes button "
                      "is not visible while box_count <= 0 (the view-level "
                      "half of the guard)."):
            # The button invisible alone is not a guard and the Python raise
            # alone is not a usable UI — the workbook's Notes demand both,
            # asserted separately, so a port that keeps one and drops the
            # other is visible.
            arch = picking_form_arch(ctx)
            buttons = _named(arch, "button", "name", CREATE_BOXES_METHOD)
            box_count = picking_row(rpc, picking_id,
                                    ["box_count"])["box_count"]
            ctx.check("the Create Boxes button carries the modifier "
                      f"{CREATE_BOXES_INVISIBLE!r} byte-exact and it resolves "
                      "to hidden for this record "
                      "(dto_stock/views/stock_picking_views.xml:42)",
                      {"buttons": 1, "modifier": CREATE_BOXES_INVISIBLE,
                       "box_count": 0, "hidden": True},
                      {"buttons": len(buttons),
                       "modifier": buttons[0].get("invisible")
                       if buttons else None,
                       "box_count": box_count, "hidden": box_count <= 0})
            ctx.log("The modifier's operator is '<=', so a NEGATIVE count is "
                    "guarded too \u2014 unlike stock_picking_box._check_weight, "
                    "which tests '== 0' and therefore accepts a negative "
                    "weight (TC154).")

        with ctx.step("Through the ORM (or a server action), call "
                      "picking.action_create_boxes() with box_count = 0."):
            # Scoped to ONE picking on purpose: ensure_one() at
            # stock_picking.py:32 fires before the guard, so a multi-record
            # call would raise the wrong error.
            before = boxes_of(rpc, picking_id)
            raised, message = expect_error(
                rpc.call, "stock.picking", CREATE_BOXES_METHOD, [picking_id])
            ctx.log(f"action_create_boxes(box_count=0) -> raised={raised} "
                    f"{message!r}")

        with ctx.step("Assert a UserError is raised."):
            ctx.check("the direct call was refused", True, raised)

        with ctx.step("Assert the message is exactly Number of Boxes must be "
                      "greater than zero."):
            ctx.check("the message is the module's string byte-for-byte "
                      "(dto_stock/models/stock_picking.py:34)",
                      ERROR_BOX_COUNT_ZERO, message)

        with ctx.step("Assert len(picking.box_ids) is unchanged by the failed "
                      "call."):
            after = boxes_of(rpc, picking_id)
            ctx.check("the failed call created nothing",
                      {"before": len(before), "after": len(before),
                       "box_count": 0},
                      {"before": len(before), "after": len(after),
                       "box_count": picking_row(
                           rpc, picking_id, ["box_count"])["box_count"]})
    finally:
        _cleanup(rpc)


# ==========================================================================
# TC154
# ==========================================================================
@test_case(
    id="TEST-WF011-TC154",
    name="Box weight zero is rejected; a negative weight is accepted "
         "(live v17 defect)",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module=MODULE, priority="P2", kind="API", order=11154,
    description="_check_weight tests weight == 0, not <= 0: writing 0 raises "
                "ValidationError('Weight must be greater than zero.') and "
                "leaves the stored value untouched, while -3.0 is accepted and "
                "stored \u2014 recorded as the accepted v17 baseline.",
    traceability=trace("DATAONE-TC154"))
def test_tc154(ctx):
    rpc = ctx.adapter.rpc
    _preflight(ctx)
    open_namespace(ctx)
    try:
        with ctx.step("Log in as TD-U-03 and open the delivery."):
            ctx.log(_role_note("TD-U-03"))
            partner_id = ensure_partner(ctx, "Customer Alpha")
            product_id = ensure_product(ctx, "Widget")
            picking_id = make_picking(ctx, code="outgoing",
                                      product_id=product_id, qty=10.0,
                                      partner_id=partner_id,
                                      label="TC154 Delivery")
            create_boxes(ctx, picking_id, 5, 2.5)
            boxes = boxes_of(rpc, picking_id)
            box_one_id = boxes[0]["id"]
            ctx.check("the delivery carries at least one stock.picking.box "
                      "(the workbook's precondition)",
                      {"boxes": 5, "box_1": "Box 1", "box_1_weight": 2.5},
                      {"boxes": len(boxes), "box_1": boxes[0]["name"],
                       "box_1_weight": _r2(boxes[0]["weight"])})
            # The workbook's v19_watch for this case: digits='Stock Weight'
            # must still resolve to product.decimal_stock_weight. Loud if the
            # precision was removed.
            exists, precision_name, expected_digits = _stock_weight_digits(rpc)
            described = rpc.call(BOX_MODEL, "fields_get", ["weight"],
                                 attributes=["type", "required", "digits",
                                             "string"]).get("weight") or {}
            ctx.log(f"stock.picking.box.weight fields_get -> {described!r}")
            ctx.check("weight is a required Float resolving to the "
                      "'Stock Weight' decimal.precision record, which exists "
                      "on both versions (product_data.xml:27-30)",
                      {"precision_record_exists": True,
                       "precision_name": STOCK_WEIGHT_PRECISION_NAME,
                       "type": "float", "required": True,
                       "digits": expected_digits},
                      {"precision_record_exists": exists,
                       "precision_name": precision_name,
                       "type": described.get("type"),
                       "required": described.get("required"),
                       "digits": list(described.get("digits") or [])
                       or None})

        with ctx.step("Set Box 1's Weight to 0."):
            # weight is required=True, so a blank coerces to 0.0 and trips the
            # same constraint; 0.0 is written explicitly to keep it unambiguous.
            ctx.log("writing stock.picking.box.weight = 0.0 on Box 1 "
                    f"(id {box_one_id})")

        with ctx.step("Attempt to save."):
            raised, message = expect_error(rpc.write, BOX_MODEL, [box_one_id],
                                           {"weight": 0.0})
            ctx.log(f"write(weight=0.0) -> raised={raised} {message!r}")
            ctx.check("the save was refused", True, raised)

        with ctx.step("Assert a ValidationError is raised with the exact "
                      "message Weight must be greater than zero."):
            ctx.check("the message is the module's string byte-for-byte "
                      "(dto_stock/models/stock_picking_box.py:23)",
                      ERROR_BOX_WEIGHT_ZERO, message)

        with ctx.step("Assert Box 1's stored weight is unchanged."):
            ctx.check("the refused write rolled back, leaving 2.5", 2.5,
                      _r2(rpc.read(BOX_MODEL, [box_one_id],
                                   ["weight"])[0]["weight"]))

        with ctx.step("Set Box 1's Weight to -3.0."):
            neg_raised, neg_message, _ = _attempt(
                rpc.write, BOX_MODEL, [box_one_id], {"weight": -3.0})
            ctx.log(f"write(weight=-3.0) -> raised={neg_raised} "
                    f"{neg_message!r}")

        with ctx.step("Save."):
            ctx.check("the negative write was not refused", False, neg_raised)

        with ctx.step("Assert the save succeeds and Box 1.weight == -3.0 \u2014 "
                      "the negative value is accepted."):
            # IMMUTABLE workbook expectation (hard rule 2). _check_weight tests
            # `rec.weight == 0`, not `<= 0` (stock_picking_box.py:19-23), so a
            # negative weight passes the constraint. This is the accepted v17
            # baseline, NOT a bug this test is allowed to invert.
            stored = _r2(rpc.read(BOX_MODEL, [box_one_id],
                                  ["weight"])[0]["weight"])
            ctx.check("a negative box weight is accepted and stored",
                      {"raised": False, "weight": -3.0},
                      {"raised": neg_raised, "weight": stored})

        with ctx.step("Record step 8's outcome in "
                      "findings/01-defects-found-in-v17.md as the accepted v17 "
                      "baseline."):
            # findings/ is outside this suite's write scope (hard rule 1), so
            # the record is emitted as a log line plus a test artifact.
            finding = (
                "DATAONE-WF-011 / DATAONE-TC154 \u2014 accepted v17 baseline\n"
                "=========================================================\n"
                f"target        : {ctx.env.key} (db={ctx.env.db}, "
                f"Odoo {ctx.env.version})\n"
                f"fixture token : {fixture_token()}\n"
                "defect        : a NEGATIVE stock.picking.box.weight is "
                "accepted.\n"
                "source        : DTO project-addons/dto_stock/models/"
                "stock_picking_box.py:19-23 \u2014\n"
                "                @api.constrains('weight') _check_weight "
                "tests `rec.weight == 0`,\n"
                "                not `<= 0`, so only exactly zero is "
                "refused.\n"
                "evidence      : write(weight=0.0)  -> ValidationError "
                f"{ERROR_BOX_WEIGHT_ZERO!r}\n"
                f"                write(weight=-3.0) -> accepted, stored "
                f"{stored!r}\n"
                "impact        : a box weight is billed by the carrier; a "
                "negative figure understates\n"
                "                the shipment and is not caught anywhere "
                "downstream (BR-6 / E2).\n"
                "decision      : OPEN \u2014 tightening the constraint to "
                "`<= 0` changes TC154 step 8's\n"
                "                expected result and must be recorded as a "
                "product decision, never\n"
                "                edited quietly into this case "
                "(F077 Notes).\n")
            path = ctx.artifacts_dir / "DATAONE-TC154-v17-defect.md"
            path.write_text(finding, encoding="utf-8")
            ctx.add_artifact(path, "log", "DATAONE-TC154-v17-defect.md")
            ctx.log(finding)
            ctx.check("the accepted-defect record was produced",
                      True, path.exists())

        with ctx.step("Restore Box 1's weight to 2.5."):
            rpc.write(BOX_MODEL, [box_one_id], {"weight": 2.5})
            ctx.check("Box 1 is back at 2.5", 2.5,
                      _r2(rpc.read(BOX_MODEL, [box_one_id],
                                   ["weight"])[0]["weight"]))
    finally:
        _cleanup(rpc)


# ==========================================================================
# TC155
# ==========================================================================
@test_case(
    id="TEST-WF011-TC155",
    name="The Boxes section is absent on receipts and on internal transfers",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module=MODULE, priority="P2", kind="HYBRID", order=11155,
    description="BR-4 is one view modifier, invisible=\"picking_type_code != "
                "'outgoing'\", enclosing all four elements: it is asserted "
                "byte-exact and resolved against a real receipt, internal "
                "transfer and outgoing delivery, with step 7 as the "
                "anti-vacuity control that the inherit applied at all.",
    traceability=trace("DATAONE-TC155"))
def test_tc155(ctx):
    rpc = ctx.adapter.rpc
    _preflight(ctx)
    _require_picking_types(ctx, ["incoming", "internal", "outgoing"])
    open_namespace(ctx)
    try:
        with ctx.step("Log in as TD-U-03."):
            ctx.log(_role_note("TD-U-03"))
            # BR-4 is a MODIFIER, not conditional arch: the four elements are
            # in the arch for every picking type and only the client hides
            # them. See the module docstring, adaptation 3, for exactly what
            # is asserted in place of "not present in the rendered form".
            ctx.log("dto_stock/views/stock_picking_views.xml:32 wraps the "
                    "section in <div invisible=\"picking_type_code != "
                    "'outgoing'\">. get_view is record-independent, so the "
                    "arch is fetched ONCE and the modifier resolved per "
                    "record; the rendered-DOM half is browser-only.")
            arch = picking_form_arch(ctx)
            facts = _section_facts(arch)
            ctx.log(f"combined stock.picking form arch facts: {facts!r}")
            product_id = ensure_product(ctx, "Widget")
            vendor_id = ensure_partner(ctx, "Vendor Gamma")
            customer_id = ensure_partner(ctx, "Customer Alpha")
            receipt_id = make_picking(ctx, code="incoming",
                                      product_id=product_id, qty=5.0,
                                      partner_id=vendor_id,
                                      label="TC155 Receipt")
            internal_id = make_picking(ctx, code="internal",
                                       product_id=product_id, qty=5.0,
                                       label="TC155 Internal")
            delivery_id = make_picking(ctx, code="outgoing",
                                       product_id=product_id, qty=5.0,
                                       partner_id=customer_id,
                                       label="TC155 Delivery")
            codes = {
                "receipt": picking_row(rpc, receipt_id,
                                       ["picking_type_code"])[
                                           "picking_type_code"],
                "internal": picking_row(rpc, internal_id,
                                        ["picking_type_code"])[
                                            "picking_type_code"],
                "delivery": picking_row(rpc, delivery_id,
                                        ["picking_type_code"])[
                                            "picking_type_code"],
            }
            ctx.log(f"fixture picking_type_code values: {codes!r}")

        with ctx.step("Open the receipt for TD-PA-03 and go to Additional "
                      "Info."):
            ctx.check("the receipt is an incoming transfer", "incoming",
                      codes["receipt"])

        with ctx.step("Assert the Boxes section, the Number of Boxes field, "
                      "the Default Weight field and the Create Boxes button "
                      "are all not present in the rendered form."):
            ctx.check("all four elements are enclosed by the one "
                      "outgoing-only div, whose modifier resolves to HIDDEN "
                      "for an incoming transfer",
                      {"modifier": BOXES_SECTION_INVISIBLE,
                       "separator_Boxes": 1, "field_box_count": 1,
                       "field_default_box_weight": 1,
                       "button_action_create_boxes": 1,
                       "every_element_inside_that_div": True,
                       "hidden_for_this_record": True},
                      {"modifier": facts["outgoing_only_div_modifier"],
                       "separator_Boxes": facts["separator_Boxes"],
                       "field_box_count": facts["field_box_count"],
                       "field_default_box_weight":
                           facts["field_default_box_weight"],
                       "button_action_create_boxes":
                           facts["button_action_create_boxes"],
                       "every_element_inside_that_div":
                           facts["every_element_inside_that_div"],
                       "hidden_for_this_record":
                           codes["receipt"] != "outgoing"})

        with ctx.step("Open the internal transfer and go to Additional Info."):
            ctx.check("the internal transfer is an internal transfer",
                      "internal", codes["internal"])

        with ctx.step("Assert the same four elements are not present."):
            ctx.check("the same modifier resolves to HIDDEN for an internal "
                      "transfer",
                      {"modifier": BOXES_SECTION_INVISIBLE,
                       "hidden_for_this_record": True},
                      {"modifier": facts["outgoing_only_div_modifier"],
                       "hidden_for_this_record":
                           codes["internal"] != "outgoing"})

        with ctx.step("Open the outgoing delivery from TC151 and go to "
                      "Additional Info."):
            ctx.check("the delivery is an outgoing transfer", "outgoing",
                      codes["delivery"])

        with ctx.step("Assert all four elements are present."):
            # THE control. A negative-only assertion passes trivially when the
            # whole dto_stock inherit silently failed to apply — precisely the
            # v19 failure mode this case exists to catch. Step 7 is not
            # optional (the workbook's own Notes).
            control = dict(facts)
            control["hidden_for_this_record"] = (
                codes["delivery"] != "outgoing")
            expected = _expected_section_facts()
            expected["hidden_for_this_record"] = False
            ctx.check("the whole section is in the arch, inside the "
                      "outgoing-only div, and VISIBLE on the delivery \u2014 the "
                      "inherit applied (views/stock_picking_views.xml:30-44; "
                      "page[@name='extra'] confirmed present on v19, "
                      "O19 stock/views/stock_picking_views.xml:326)",
                      expected, control)

        with ctx.step("Assert picking_type_code reads incoming, internal and "
                      "outgoing on the three records respectively."):
            ctx.check("the three fixtures carry the three operation codes",
                      {"receipt": "incoming", "internal": "internal",
                       "delivery": "outgoing"}, codes)
    finally:
        _cleanup(rpc)


# ==========================================================================
# TC157
# ==========================================================================
@test_case(
    id="TEST-WF011-TC157",
    name="Transfer weight and shipping weight are hand-entered and survive "
         "line edits",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module=MODULE, priority="P2", kind="API", order=11157,
    description="weight 14.6 and shipping_weight 15.2 typed by the operator "
                "differ from the product-weight sum, survive a demanded-"
                "quantity change untouched, coexist with a box manifest that "
                "does not add up, and report depends == [] with store True and "
                "readonly False \u2014 the compute is genuinely off.",
    traceability=trace("DATAONE-TC157"))
def test_tc157(ctx):
    rpc = ctx.adapter.rpc
    _preflight(ctx)
    open_namespace(ctx)
    try:
        with ctx.step("Log in as TD-U-03 and open the delivery."):
            ctx.log(_role_note("TD-U-03"))
            partner_id = ensure_partner(ctx, "Customer Alpha")
            # ensure_product carries weight=2.0, so the core compute's
            # would-be figure (10 x 2.0 = 20.0) differs from the typed 14.6 —
            # the workbook's step 6 requires exactly that.
            product_id = ensure_product(ctx, "Widget")
            picking_id = make_picking(ctx, code="outgoing",
                                      product_id=product_id, qty=10.0,
                                      partner_id=partner_id,
                                      label="TC157 Delivery")
            # Step 9 needs a manifest to compare against; it is built here so
            # the fixture is complete before the workbook's steps begin.
            create_boxes(ctx, picking_id, 5, 2.5)
            moves = moves_of(rpc, picking_id)
            row = picking_row(rpc, picking_id, ["state", "picking_type_code"])
            ctx.check("the fixture is an outgoing transfer with at least one "
                      "move and a five-box manifest",
                      {"picking_type_code": "outgoing", "moves": 1,
                       "boxes": 5, "not_done": True},
                      {"picking_type_code": row.get("picking_type_code"),
                       "moves": len(moves),
                       "boxes": len(boxes_of(rpc, picking_id)),
                       "not_done": row.get("state") not in ("done", "cancel")})

        with ctx.step("Record computed_guess = sum(move.product_qty * "
                      "move.product_id.weight for move in picking.move_ids)."):
            qty_field = ("product_qty"
                         if rpc.field_exists("stock.move", "product_qty")
                         else "product_uom_qty")
            move_rows = rpc.search_read(
                "stock.move", [("picking_id", "=", picking_id)],
                ["product_id", qty_field], order="id")
            product_weight = rpc.read("product.product", [product_id],
                                      ["weight"])[0]["weight"]
            computed_guess = _r2(sum(m[qty_field] * product_weight
                                     for m in move_rows))
            ctx.log(f"computed_guess = {computed_guess} "
                    f"(sum of {qty_field} x product weight "
                    f"{product_weight})")
            ctx.check_true("the product carries a non-zero weight, so the "
                           "core compute's would-be figure is not zero",
                           computed_guess > 0.0,
                           f"computed_guess = {computed_guess}")

        with ctx.step("Type 14.6 into Weight and 15.2 into Shipping Weight."):
            rpc.write("stock.picking", [picking_id],
                      {"weight": 14.6, "shipping_weight": 15.2})

        with ctx.step("Save."):
            saved = picking_row(rpc, picking_id, ["weight", "shipping_weight"])
            ctx.log(f"after save: {saved!r}")

        with ctx.step("Assert picking.weight == 14.6 and "
                      "picking.shipping_weight == 15.2."):
            ctx.check("both operator-entered figures were stored as typed "
                      "(dto_stock/models/stock_picking.py:13-14)",
                      {"weight": 14.6, "shipping_weight": 15.2},
                      {"weight": _r2(saved.get("weight")),
                       "shipping_weight": _r2(saved.get("shipping_weight"))})

        with ctx.step("Assert picking.weight != computed_guess (choose fixture "
                      "weights so this holds) \u2014 the entered value is not "
                      "the computed one."):
            ctx.check("the stored weight is the typed figure, not the product "
                      "sum",
                      {"weight": 14.6, "computed_guess": computed_guess,
                       "equal": False},
                      {"weight": _r2(saved.get("weight")),
                       "computed_guess": computed_guess,
                       "equal": _r2(saved.get("weight")) == computed_guess})

        with ctx.step("Change the demanded quantity on one move line and "
                      "save."):
            rpc.write("stock.move", [move_rows[0]["id"]],
                      {"product_uom_qty": 7.0})
            changed = rpc.read("stock.move", [move_rows[0]["id"]],
                               ["product_uom_qty"])[0]["product_uom_qty"]
            ctx.check("the demanded quantity really changed", 7.0,
                      _r2(changed))

        with ctx.step("Assert picking.weight is still 14.6 and "
                      "picking.shipping_weight is still 15.2 \u2014 no "
                      "recomputation occurred."):
            after = picking_row(rpc, picking_id, ["weight", "shipping_weight"])
            ctx.check("the line edit did not recompute either figure",
                      {"weight": 14.6, "shipping_weight": 15.2},
                      {"weight": _r2(after.get("weight")),
                       "shipping_weight": _r2(after.get("shipping_weight"))})

        with ctx.step("Assert sum(picking.box_ids.mapped('weight')) != "
                      "picking.weight and that no error or warning is produced "
                      "\u2014 nothing reconciles the two by design."):
            boxes = boxes_of(rpc, picking_id)
            box_sum = _r2(sum(b["weight"] for b in boxes))
            # A real write on the picking while the manifest disagrees: if
            # anything reconciled the two, this is where it would raise.
            raised, message, _ = _attempt(rpc.write, "stock.picking",
                                          [picking_id], {"weight": 14.6})
            ctx.log(f"box weights {[_r2(b['weight']) for b in boxes]} sum to "
                    f"{box_sum}; re-write of weight raised={raised} "
                    f"{message!r}")
            live_weight = _r2(picking_row(rpc, picking_id,
                                          ["weight"]).get("weight"))
            ctx.check("the manifest total and the transfer weight disagree, "
                      "and nothing complains",
                      {"box_sum": 12.5, "weight": 14.6, "equal": False,
                       "write_raised": False},
                      {"box_sum": box_sum, "weight": live_weight,
                       "equal": box_sum == live_weight,
                       "write_raised": raised})

        with ctx.step("Inspect the field definitions and assert "
                      "picking._fields['weight'].compute is None and "
                      "picking._fields['shipping_weight'].compute is None."):
            # _fields attribute access is not reachable over RPC; the
            # fields_get proxy is depends == [] AND store is True AND
            # readonly is False. See the module docstring, adaptation 4.
            ctx.check("both fields report an empty depends with store True "
                      "and readonly False \u2014 the compute is genuinely off, "
                      "not coincidentally quiet "
                      "(O17 odoo/fields.py:861, :865, :873)",
                      {"weight": _plain_compute_off(),
                       "shipping_weight": _plain_compute_off()},
                      {"weight": _weight_shape(rpc, "stock.picking", "weight"),
                       "shipping_weight": _weight_shape(rpc, "stock.picking",
                                                        "shipping_weight")})
            # The workbook's "also assert the shape of the base field" cannot
            # be asserted once dto_stock has redefined it — the base
            # declaration is no longer RPC-visible. It is carried by the
            # source citations in the module docstring; the neighbouring core
            # compute is logged as corroboration that core still computes
            # weights around these two fields.
            bulk = (_weight_shape(rpc, "stock.picking", "weight_bulk")
                    if rpc.field_exists("stock.picking", "weight_bulk")
                    else None)
            ctx.log(
                "base-field shape is source-verified, not asserted: weight is "
                "compute='_cal_weight', store=True at O17 stock_delivery/"
                "models/stock_picking.py:91 and O19 :25; shipping_weight is "
                "compute='_compute_shipping_weight' at O17 stock_delivery:"
                "97-98 and, on v19, at O19 stock/models/stock_picking.py:"
                f"666-670 with store=True, readonly=False. Neighbouring core "
                f"compute weight_bulk reads {bulk!r} on this target.")
    finally:
        _cleanup(rpc)
