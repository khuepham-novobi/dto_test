"""DATAONE-WF-021 — the five levels, the Finished-Goods rule and the
pre-save scheduled date: TC169–TC173.

Everything these five cases assert was read out of the real source first
(AUTOMATION_CONVENTIONS hard rule 6). ``main`` is the Odoo 17 baseline branch
of ``DTO-Odoo``; the working tree is checked out on ``UAT``, which already
carries the v19 port, so every v17 citation below was read through
``git show main:…`` and no assertion here is grounded in a grep of the
checkout (see "The checkout trap" in ``tests/wf021/common.py``). What the
target actually serves is read back from it — ``get_view``, ``fields_get``,
``default_get`` and the records a public entry point leaves behind.

The rules under test
====================
``models/cycle_count_category.py`` (v17 ``main``)::

    _order = 'id'                                                       # :12
    name / interval_number / interval_type                              # :14-20

    def _calculate_scheduled_count_date(self, last_count_date):         # :22
        self.ensure_one()                                               # :23
        if not last_count_date:
            last_count_date = fields.Date.today()                       # :24-25
        return last_count_date + relativedelta(
            **{self.interval_type: self.interval_number})                # :26

``data/cycle_count_category_data.xml`` — ``<data noupdate="1">`` (``:3``) and
the five records at ``:5-33``: A 1/days, B 1/weeks, C 1/months, D 4/months,
E 6/months. ``noupdate`` means in-database additions survive an upgrade, so
TC169 resolves the five **by xmlid** and scopes "exactly five" through
``ir.model.data`` (``common.module_level_ids``) instead of a global
``count == 5``, which would be a live-data assertion (convention rule 5).

``models/product_product.py`` (v17 ``main``)::

    cycle_count_category_id / last_count_date / scheduled_count_date    # :13-15
    _onchange_categ_id      — Level D iff not already set AND
                              categ_id.name == 'Finished Goods'          # :20-23
    _onchange_cycle_count_category_id — scheduled_count_date, guarded by
                              ``if cycle_count and self.last_count_date`` # :25-29
    _onchange_type          — clears the three fields off a non-storable,
                              restores them from ``self._origin``        # :31-48
    write                   — re-schedules every quant when the key
                              ``cycle_count_category_id`` is PRESENT     # :53-61
    create (@api.model_create_multi) — Level D for every record in the
                              list whose category is Finished Goods      # :63-72

``models/product_template.py`` carries the same two category onchanges
(``:67-76``) and the compute/inverse/search triples (``:13-20``) but **no
CRUD section at all** — the file ends at ``:102`` with
``_get_related_fields_variant_template``. That is TC171 step 8's subject.

``views/product_product_views.xml`` (v17 ``main:9-15``) injects, after the
``traceability`` group::

    <group string="Cycle Count" name="cycle_count" invisible="type != 'product'">
        <field name="cycle_count_category_id" … required="type == 'product'"/>
        <field name="last_count_date" readonly="1"/>
        <field name="scheduled_count_date" force_save="1" readonly="1"/>

so BR-3 ("every storable product carries a level") is a **view modifier**,
never an ``@api.constrains`` — which is the whole of TC172.

``views/cycle_count_category_views.xml:44-55`` — the act_window
(``res_model`` ``cycle.count.category``) and the menu under
``stock.menu_product_in_config_stock`` that TC169 step 2 opens.
``security/ir.model.access.csv:2-3`` — ``base.group_user`` 1,0,0,0 and
``stock.group_stock_manager`` 1,1,1,1, the two rows that let TD-U-04 read
the levels.

How the private arithmetic is reached
=====================================
``_calculate_scheduled_count_date`` starts with an underscore, so
``check_method_name`` (``odoo/models.py:143-148``) refuses to dispatch it
over ``/web/dataset/call_kw``. It is never re-implemented here as the source
of an assertion. It is reached through two PUBLIC surfaces only:

* ``onchange(values, field_names, fields_spec)`` — declared at
  ``odoo/models.py:7010``, implemented at ``addons/web/models/models.py:895``;
  the result's ``value`` key carries only the fields the onchange CHANGED
  (``RecordSnapshot.diff``), which is why every case here asserts the
  resulting **form state** rather than the raw diff;
* ``product.product.write`` (``models/product_product.py:53-61``) — one level
  write re-schedules every quant of the product. That is the only path on
  which the ``if not last_count_date: … today`` fallback
  (``cycle_count_category.py:24-25``) is reachable at all, because the form's
  own onchange is guarded on ``self.last_count_date`` being set (``:28``).
  TC169 steps 11-12 are asserted there, and the form half is recorded
  alongside so both readings are on the record.

``common.add_interval`` computes only the EXPECTED value BR-2 states, with
the stdlib (the platform venv has no ``python-dateutil``); it reproduces all
five of the workbook's worked examples exactly.

Adaptations, each forced by the platform and none weakening an expectation
=========================================================================
* **Roles.** "Log in as TD-U-04" opens a real second session
  (``common.ensure_wf021_user`` + ``rpc_as``) in ``stock.group_stock_user`` +
  ``stock.group_stock_manager``, and that session performs the reads, the
  ``onchange`` calls and the arch fetches the role governs. Every fixture
  create/write runs as the configured session user: v19 DELETES
  ``stock.group_stock_manager``'s ``product.product`` / ``product.template``
  ACL rows (v17 ``stock/security/ir.model.access.csv:21-22`` versus v19
  ``:15-16``), so routing fixture writes through the role session would make
  these cases fail on v19 for a privilege reason none of them is about —
  that question is TC175's.
* **TC170 step 9** creates a WF021-namespaced duplicate category named
  ``'Finished Goods '`` (one trailing space) instead of renaming the live
  one: ``product_category.name`` has no unique constraint
  (``product/models/product_category.py:16``), and convention rule 3 forbids
  modifying the live row. Step 10 asserts the live rows are untouched.
* **TC171 step 8** asserts the ACTUAL outcome of the template-only import.
  ``product.template.create`` calls ``_create_variant_ids``
  (``product/models/product_template.py:727``) which calls
  ``Product.create(variants_to_create)`` (``:804``), so the variant goes
  through the module's own ``product.product.create`` override and
  ``categ_id`` resolves through ``_inherits`` to the template's category.
  The step is a RECORD step in the workbook's own words (step 9: "Record
  step 8's outcome as the accepted v17 baseline"), so what is asserted is
  the falsifiable mechanism — the template MIRRORS its variant, because
  nothing assigns a level at template level — and the observed value is
  logged as the baseline. The import itself runs through ``load()``
  (``odoo/models.py:1145``, ``@api.model``), which is step 10's own
  requirement; ``_str_to_selection`` accepts the selection KEY
  (``odoo/addons/base/models/ir_fields.py:362-380``) so the storable shape
  the adapter supplies imports unchanged on both versions.
* **TC172 step 5** has no server-observable string: the required-field
  refusal and the red highlight are rendered by the web client from the
  ``required`` modifier. The modifier is asserted on the rendered arch and
  EVALUATED against the form's own field values — which is what the client
  does — so the assertion still fails if a port leaves the expression
  permanently false (TC177's subject) without this file carrying a version
  branch. The ORM leak the case exists to document is asserted directly.
* **TC173's postcondition** ("leave as-is for TC174") is deliberately NOT
  honoured: convention rule 5 forbids cross-test fixture dependence and
  TC174 builds its own namespace.
* ``last_count_date`` carries ``readonly="1"`` in the arch
  (``product_product_views.xml:12``), so the real UI would not let a user
  type the dates TC169 step 5 and TC173 steps 2/9 supply. Every case
  therefore seeds that date through the ORM as ``_apply_inventory`` does and
  drives the same value through the onchange; the observation is logged, not
  asserted away.

Version handling: storability comes from ``ctx.adapter.storable_product_values()``
via ``common.storable_values``; the fields that express it are read back
from the adapter (``_storable_fields``) so no test body reads
``ctx.env.version``. TC177 is this suite's only sanctioned version branch.

EXPECTED v17 OUTCOME
====================
* ``TEST-WF021-TC169`` — **PASS**. The shipped data and the arithmetic are
  both v17 facts; the fallback is asserted on the write path, the only one
  that reaches it.
* ``TEST-WF021-TC170`` — **PASS**. The Level-D rule, the never-overwrite
  guard and the exact-string fragility are all v17 behaviour.
* ``TEST-WF021-TC171`` — **PASS**. ``@api.model_create_multi`` handles the
  three-dict list, and no onchange runs on the ``create()``/``load()`` path.
* ``TEST-WF021-TC172`` — **PASS**. The modifier is present and evaluates
  true for a storable product, and the ORM accepts a levelless one: both
  halves of the baseline the workbook wants.
* ``TEST-WF021-TC173`` — **PASS**. Every date is supplied, and
  ``force_save="1"`` is what carries the displayed value into storage.

Nothing here reaches an external system: ``dto_cycle_count`` ships no cron,
no server action and no mail template, and the workflow sheet's
*Integrations* section is literally "None" (convention rule 4 is satisfied
by construction). ``ensure_wf021_user`` passes ``no_reset_password`` so not
even a welcome email is composed.
"""
from __future__ import annotations

import datetime

from adapters.base import OdooRPCError
from framework.registry import test_case
from tests.wf021.common import (ACTION_LEVELS, CYCLE_COUNT_FIELDS,
                                CYCLE_COUNT_GROUP, FINISHED_GOODS_NAME,
                                FINISHED_GOODS_TRAILING_SPACE,
                                FIXED_COUNT_DATE, GROUP_STOCK_MANAGER,
                                GROUP_STOCK_USER, LEVEL_D_XMLID, MENU_LEVELS,
                                MENU_LEVELS_PARENT, MODULE,
                                SCHEDULED_FROM_FIXED, SECOND_COUNT_DATE,
                                SECOND_SCHEDULED_LEVEL_B, SHIPPED_LEVELS,
                                TEMPLATE_VARIANT_LEVEL_FIELD,
                                VIEW_PRODUCT_FORM, WORKFLOW, WORKFLOW_NAME,
                                add_stock, archive_user, arch_of, code,
                                ensure_wf021_user, expect_error,
                                expected_schedule, field_attrs, group_attrs,
                                internal_locations, iso, level_of, m2o_id,
                                make_category, make_product, make_products,
                                module_level_ids, near_miss_category,
                                open_namespace, quant_of,
                                require_cycle_count, require_shipped_levels,
                                rpc_as, safe_sweep, server_today, set_level,
                                storable_values, tag, trace, variants_of)

#: Attribute spellings a view modifier uses for a constant.
_TRUE_ATTRS = ("1", "true", "True")
_FALSE_ATTRS = ("0", "false", "False", "")


# ===========================================================================
# The onchange surface
# ===========================================================================
def _onchange(rpc, model, record_ids, values, field_names, spec_fields=None):
    """Call the public ``onchange`` the way the web client calls it.

    Over ``/web/dataset/call_kw`` the leading ``ids`` positional is not
    optional: ``onchange`` carries no ``@api.model`` decorator on either
    version (v17 ``odoo/models.py:7010``, v19 ``odoo/orm/models.py:6996``),
    so ``_call_kw_multi`` consumes it before the method ever sees its own
    parameters — ``odoo/api.py:464-465``::

        ids, args = args[0], args[1:]
        recs = self.with_context(context or {}).browse(ids)

    so the client sends ``[resIds, values, fieldNames, fieldsSpec]`` and
    passing ``values`` first would make the server browse the vals-dict's
    KEYS as record ids. ``tests.wf021.common.onchange`` takes ``record_ids``
    in that same leading position and is equivalent; this wrapper is kept
    local so each test file in the suite calls one helper with no import
    churn. It supplies ``record_ids`` (``[]`` for an
    unsaved form) and is otherwise identical: the spec defaults to the keys
    of ``values`` plus ``CYCLE_COUNT_FIELDS``, because a field absent from
    ``fields_spec`` is never reported by ``RecordSnapshot.diff``
    (``addons/web/models/models.py:1085-1087``) and an assertion on it would
    pass vacuously.
    """
    names = list(dict.fromkeys(list(spec_fields or [])
                               + list(values.keys())
                               + list(CYCLE_COUNT_FIELDS)))
    fields_spec = {name: {} for name in names}
    return rpc.call(model, "onchange", list(record_ids), values,
                    list(field_names), fields_spec) or {}


def _scalar(value):
    """Normalise one RPC value to what a client-side form state holds.

    ``web_read`` with an empty field spec returns a many2one as a bare id,
    but ``onchange`` results and ``read`` results can also carry
    ``[id, display_name]`` or ``{'id': …}`` depending on the spec and the
    version, and dates arrive as ``'YYYY-MM-DD'`` strings.
    """
    if isinstance(value, dict):
        return value.get("id", False)
    if isinstance(value, (list, tuple)):
        return value[0] if value else False
    if isinstance(value, (datetime.date, datetime.datetime)):
        return iso(value)
    return False if value is None else value


def _form_open(rpc, model, record_id, field_names):
    """Read a saved record into a dict shaped like the web client's form."""
    row = rpc.read(model, [record_id], list(field_names))[0]
    return {name: _scalar(row.get(name)) for name in field_names}


def _form_change(rpc, model, record_ids, state, changes, spec_fields=None):
    """Apply ``changes`` to ``state`` through the server's own onchange.

    The client sends the whole form state and merges the reported values
    back; this does the same, so an assertion reads the value the user would
    see. Asserting the merged STATE rather than the raw diff also keeps the
    assertions honest in both directions: ``RecordSnapshot.diff`` reports
    only what the onchange CHANGED, so a field that already held the
    expected value is simply absent from the result.
    """
    values = dict(state)
    values.update(changes)
    result = _onchange(rpc, model, record_ids, values, list(changes),
                       spec_fields)
    state.update(changes)
    for name, value in (result.get("value") or {}).items():
        state[name] = _scalar(value)
    return result


def _cycle_state(state):
    """The three cycle-count fields of a form state, dates normalised."""
    return {"cycle_count_category_id": state.get("cycle_count_category_id")
            or None,
            "last_count_date": iso(state.get("last_count_date")) or None,
            "scheduled_count_date": iso(state.get("scheduled_count_date"))
            or None}


# ===========================================================================
# View modifiers
# ===========================================================================
def _modifier(expression, values):
    """Evaluate a view modifier against a record's values.

    Since Odoo 17 a modifier is a plain Python expression carried as an
    attribute on the node and evaluated by the web client against the
    record currently in the form. Evaluating it here — with an empty
    builtins namespace and the values the server itself returned — is the
    only way to assert "this group is visible for a storable product"
    without hard-coding the expression, which would be version-shaped
    (``common.STORABLE_MODIFIERS``) and belongs to TC177 alone.

    The expression is data read back from the target, never a literal this
    file carries. Returns ``None`` when it cannot be evaluated (an unknown
    name, a shape the client would handle differently), so a failure reports
    ``None`` rather than silently reading as False.
    """
    if expression is None:
        return None
    text = str(expression).strip()
    if text in _TRUE_ATTRS:
        return True
    if text in _FALSE_ATTRS:
        return False
    try:
        return bool(eval(text, {"__builtins__": {}}, dict(values)))  # noqa: S307,PGH001
    except Exception:                                        # noqa: BLE001
        return None


def _truthy_attr(value) -> bool:
    """Whether an arch attribute spells a constant true (``force_save="1"``)."""
    return str(value).strip() in _TRUE_ATTRS


# ===========================================================================
# Storability, expressed through the adapter rather than a version branch
# ===========================================================================
def _storable_fields(ctx) -> list:
    """The field names that express storability on the TARGET.

    ``['type']`` on v17 and ``['type', 'is_storable']`` on v19, taken from
    ``ctx.adapter.storable_product_values()`` (``adapters/odoo17.py:24``,
    ``adapters/odoo19.py:26``). Reading the shape the adapter declares is
    not a version branch: the test body never asks which version it is on.
    """
    return list(storable_values(ctx).keys())


def _non_storable_values(ctx) -> dict:
    """A service product's values, with every storability flag turned off.

    ``{'type': 'service'}`` on v17; on v19 the boolean must be cleared too,
    or ``_onchange_type``'s ``if not self.is_storable`` branch
    (the port's ``models/product_product.py:37``) would never fire.
    """
    values = {"type": "service"}
    for name in _storable_fields(ctx):
        values.setdefault(name, False)
    return values


def _import_value(value) -> str:
    """One CSV cell. ``load()`` parses booleans and selections from text."""
    if value is True:
        return "1"
    if value is False:
        return "0"
    return str(value)


# ===========================================================================
# Roles and teardown
# ===========================================================================
def _acting_session(ctx, suffix, group_xmlids, role):
    """Open a second RPC session as one of the workbook's role users.

    Returns ``(user_id, login, rpc)``. BLOCKS — rather than erroring — when
    the groups are absent or the session cannot authenticate, because that
    is a precondition outside the case's control.
    """
    rpc = ctx.adapter.rpc
    missing = [xmlid for xmlid in group_xmlids if not rpc.ref(xmlid)]
    if missing:
        ctx.blocked(
            f"These groups do not exist on {ctx.env.key} (db={ctx.env.db}): "
            f"{', '.join(missing)} — stock is not installed, so the "
            f"workbook's {role} cannot be built and no step of this case "
            "can be performed as the role it names.")
    try:
        user_id, login = ensure_wf021_user(ctx, suffix, group_xmlids)
        user_rpc = rpc_as(ctx.env, login)
        uid = user_rpc.uid
    except OdooRPCError as exc:
        ctx.blocked(
            f"Could not open a session as the workbook's {role} on "
            f"{ctx.env.key} (db={ctx.env.db}): {exc}. Every step this case "
            "performs in that role needs its own authenticated session.")
    ctx.log(f"acting as {role}: {login} (uid {uid}); groups "
            f"{list(group_xmlids)}")
    return user_id, login, user_rpc


#: v19 split product write out of the inventory roles. Measured on d1v19:
#: an Inventory Manager writing a product is refused with
#:
#:   You are not allowed to modify 'Product Variant' (product.product)
#:   records. This operation is allowed for the following groups:
#:   - Products/Create  - Accountant access  - Accountant lock dates
#:
#: On v17 stock.group_stock_manager was sufficient. TC169, TC170, TC172 and
#: TC173 all have an Inventory Manager set a product field, so the fixture
#: user needs the extra privilege for the case to reach the behaviour it is
#: about — the cycle-count scheduling — rather than stopping at an ACL that
#: is not its subject.
#:
#: This is a v19 behaviour change worth its own line in the notes: the
#: Inventory Manager role alone can no longer set a product's Last Count
#: Date.
GROUP_PRODUCT_CREATE = "product.group_product_manager"


def _stock_manager_session(ctx):
    """TD-U-04 dto_stock_mgr — an Inventory Manager session.

    Carries ``product.group_product_manager`` in addition to the two stock
    groups, because v19 requires it for the product writes these cases
    make. See GROUP_PRODUCT_CREATE above.
    """
    groups = [GROUP_STOCK_USER, GROUP_STOCK_MANAGER]
    if ctx.adapter.rpc.ref(GROUP_PRODUCT_CREATE):
        groups.append(GROUP_PRODUCT_CREATE)
    return _acting_session(ctx, "mgr", groups,
                           "TD-U-04 dto_stock_mgr (Inventory Manager)")


def _drop_records(rpc, model, ids):
    """Best-effort unlink that can never raise (convention rule 3).

    ``sweep_wf021`` matches ``product.category`` on ``name like 'WF021'``,
    which by design does NOT match the two categories TC170 creates with
    live-looking literal names. They are removed here explicitly, by id, so
    no row named exactly ``Finished Goods`` is ever left behind.
    """
    for record_id in [i for i in ids if i]:
        try:
            rpc.call(model, "unlink", [record_id])
        except Exception:                                    # noqa: BLE001
            pass


def _live_finished_goods(rpc, exclude_ids=()) -> dict:
    """``{id: name}`` for every category named exactly ``Finished Goods``.

    Captured before the fixture creates its namespaced duplicate and
    re-read afterwards, so TC170 step 10 can prove the live row — id 10 on
    the target, carrying 7,915 Level-D variants — was never renamed.
    """
    excluded = set(exclude_ids or ())
    rows = rpc.search_read("product.category",
                           [("name", "=", FINISHED_GOODS_NAME)],
                           ["name"], order="id")
    return {row["id"]: row["name"] for row in rows
            if row["id"] not in excluded}


# ===========================================================================
# TC169
# ===========================================================================
@test_case(
    id="TEST-WF021-TC169",
    name="The five shipped levels produce the five documented intervals "
         "from a fixed count date",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module=MODULE, priority="P1", kind="API", order=21169,
    description="The five shipped cycle.count.category rows carry the "
                "documented (interval_number, interval_type) pairs, and a "
                "Last Count Date of 2026-08-20 produces 2026-08-21 / 08-27 / "
                "09-20 / 12-20 / 2027-02-20 through the form and again "
                "through the write path, plus the no-last-count fallback.",
    traceability=trace("DATAONE-TC169"))
def test_tc169(ctx):
    require_cycle_count(ctx)
    rpc = ctx.adapter.rpc
    open_namespace(ctx)
    user_id = None
    try:
        with ctx.step("Preconditions: the five shipped levels, TD-P-03 and "
                      "its quant"):
            levels = require_shipped_levels(ctx)
            categ_id = make_category(rpc, "P03-CATEG")
            # Deliberately levelless and with no scheduled date: every one
            # of steps 6-10 must be a REAL change, or the onchange could
            # leave a stale value in place and the assertion would pass
            # without the arithmetic ever running.
            product_id = make_product(ctx, "FG-NOTRACK-003",
                                      storable=True, categ_id=categ_id)
            location_id = internal_locations(ctx, 1)[0]
            add_stock(ctx, product_id, location_id, 5.0)
            quant_id = quant_of(rpc, product_id, location_id)
            if not quant_id:
                ctx.blocked(
                    f"No stock.quant was created for TD-P-03 (product "
                    f"{product_id}) in location {location_id} on "
                    f"{ctx.env.key} (db={ctx.env.db}). Steps 11 and 12 read "
                    "the quant the write path re-schedules "
                    "(models/product_product.py:57-60) — it is the only "
                    "public surface on which "
                    "_calculate_scheduled_count_date's no-last-count "
                    "fallback (cycle_count_category.py:24-25) is reachable.")
            ctx.log(f"TD-P-03 = product {product_id}, quant {quant_id} in "
                    f"location {location_id}")

        with ctx.step("Log in as TD-U-04"):
            user_id, login, user_rpc = _stock_manager_session(ctx)
            ctx.check_true("the Inventory Manager session is authenticated",
                           bool(user_rpc.uid),
                           actual_desc=f"uid {user_rpc.uid} ({login})")

        with ctx.step("Open Inventory → Configuration → Cycle Count "
                      "Categories"):
            action_id = rpc.ref(ACTION_LEVELS)
            menu_id = rpc.ref(MENU_LEVELS)
            parent_id = rpc.ref(MENU_LEVELS_PARENT)
            if not action_id or not menu_id:
                ctx.blocked(
                    f"{ACTION_LEVELS} / {MENU_LEVELS} do not both resolve on "
                    f"{ctx.env.key} (db={ctx.env.db}) — "
                    "views/cycle_count_category_views.xml:44-55 never "
                    "loaded, so the configuration screen this step opens "
                    "does not exist.")
            action = rpc.read("ir.actions.act_window", [action_id],
                              ["name", "res_model"])[0]
            menu = rpc.read("ir.ui.menu", [menu_id],
                            ["name", "parent_id"])[0]
            ctx.check("the menu opens the levels list",
                      {"action res_model": "cycle.count.category",
                       "menu parent": parent_id},
                      {"action res_model": action["res_model"],
                       "menu parent": m2o_id(menu["parent_id"])})
            # Read AS TD-U-04: security/ir.model.access.csv:2 grants
            # base.group_user read, :3 grants the manager 1,1,1,1.
            rows = user_rpc.search_read(
                "cycle.count.category",
                [("id", "in", sorted(levels.values()))],
                ["name", "interval_number", "interval_type"], order="id")
            ctx.check("TD-U-04 can read every shipped level",
                      len(levels), len(rows))

        with ctx.step("Assert exactly five categories exist, named for "
                      "levels A, B, C, D and E"):
            # Scoped through ir.model.data rather than a global count:
            # data/cycle_count_category_data.xml is noupdate="1" (:3), so an
            # in-database sixth level is legal and would make count == 5 a
            # live-data assertion (convention rule 5).
            owned = sorted(module_level_ids(rpc))
            ctx.check(f"{MODULE} owns exactly five cycle.count.category rows",
                      sorted(levels.values()), owned)
            by_id = {row["id"]: row for row in rows}
            ctx.check("the five names",
                      {key: name for key, name, _n, _t in SHIPPED_LEVELS},
                      {key: by_id[levels[key]]["name"]
                       for key, _name, _n, _t in SHIPPED_LEVELS})

        with ctx.step("Assert their (interval_number, interval_type) pairs "
                      "are (1, days), (1, weeks), (1, months), (4, months), "
                      "(6, months) respectively"):
            ctx.check("the five intervals",
                      {key: (number, unit)
                       for key, _name, number, unit in SHIPPED_LEVELS},
                      {key: (by_id[levels[key]]["interval_number"],
                             by_id[levels[key]]["interval_type"])
                       for key, _name, _n, _t in SHIPPED_LEVELS})
            # "respectively" is an ordering claim, and _order = 'id'
            # (cycle_count_category.py:12) is what makes the list render in
            # that order.
            ctx.check("A→E is the _order='id' order",
                      [levels[key] for key, _n, _i, _t in SHIPPED_LEVELS],
                      sorted(levels.values()))

        state = _form_open(rpc, "product.product", product_id,
                           ["categ_id"] + CYCLE_COUNT_FIELDS)
        with ctx.step("Set TD-P-03's Last Count Date to 2026-08-20"):
            # The arch renders this field readonly="1"
            # (product_product_views.xml:12), so a real user could not type
            # it; the value is driven through the same onchange the form
            # fires, which is where the arithmetic lives.
            _form_change(user_rpc, "product.product", [product_id], state,
                         {"last_count_date": FIXED_COUNT_DATE})
            ctx.check("Last Count Date on the form", FIXED_COUNT_DATE,
                      iso(state["last_count_date"]))
            ctx.log("Scheduled Count Date is still "
                    f"{state['scheduled_count_date']!r} — "
                    "_onchange_cycle_count_category_id is guarded by "
                    "`if cycle_count and self.last_count_date` "
                    "(product_product.py:28) and no level is set yet.")

        observed = {}
        for key, step_name in (
                ("A", "Set its level to A and assert Scheduled Count Date "
                      "reads 2026-08-21"),
                ("B", "Set its level to B and assert 2026-08-27"),
                ("C", "Set its level to C and assert 2026-09-20"),
                ("D", "Set its level to D and assert 2026-12-20"),
                ("E", "Set its level to E and assert 2027-02-20")):
            with ctx.step(step_name):
                _form_change(user_rpc, "product.product", [product_id],
                             state, {"cycle_count_category_id": levels[key]})
                observed[key] = iso(state["scheduled_count_date"])
                ctx.check(f"Scheduled Count Date on Level {key}",
                          SCHEDULED_FROM_FIXED[key], observed[key])

        with ctx.step("Clear Last Count Date, set the level to B, and assert "
                      "the scheduled date is today + 1 week — the "
                      "no-last-count fallback"):
            # The form half first, recorded rather than asserted: with Last
            # Count Date empty the guard at product_product.py:28 stops the
            # onchange, so the form cannot reach the fallback at all.
            _form_change(user_rpc, "product.product", [product_id], state,
                         {"last_count_date": False,
                          "cycle_count_category_id": levels["B"]})
            ctx.log("form half: Scheduled Count Date reads "
                    f"{iso(state['scheduled_count_date'])!r} — the onchange "
                    "does not fire with Last Count Date empty "
                    "(product_product.py:28).")
            # The fallback lives inside _calculate_scheduled_count_date
            # (cycle_count_category.py:24-25) and is reached only from the
            # write path, which passes the QUANT's own last_count_date
            # (product_product.py:57-60).
            rpc.write("product.product", [product_id],
                      {"last_count_date": False})
            rpc.write("stock.quant", [quant_id], {"last_count_date": False})
            today = server_today(ctx)
            set_level(rpc, product_id, levels["B"])
            due = iso(rpc.read("stock.quant", [quant_id],
                               ["inventory_date"])[0]["inventory_date"])
            ctx.check("the no-last-count fallback schedules today + 1 week",
                      iso(expected_schedule("B", today)), due)

        with ctx.step("Assert _calculate_scheduled_count_date is callable "
                      "directly and returns the same five values for the "
                      "same inputs, independent of the form"):
            # Over RPC it is not dispatchable at all — check_method_name
            # (odoo/models.py:143-148) raises AccessError for any name
            # starting with an underscore. Recorded as the transport fact it
            # is, then the arithmetic is asserted through a SECOND public
            # path so nothing here re-implements the method.
            raised, message = expect_error(
                rpc.call, "cycle.count.category",
                "_calculate_scheduled_count_date", [levels["A"]],
                FIXED_COUNT_DATE)
            ctx.check_true(
                "the private method is refused over /web/dataset/call_kw "
                "(odoo/models.py:145-148)", raised, actual_desc=message)
            rpc.write("stock.quant", [quant_id],
                      {"last_count_date": FIXED_COUNT_DATE})
            through_write = {}
            for key, _name, _number, _unit in SHIPPED_LEVELS:
                set_level(rpc, product_id, levels[key])
                through_write[key] = iso(
                    rpc.read("stock.quant", [quant_id],
                             ["inventory_date"])[0]["inventory_date"])
            ctx.check("the write path reproduces all five intervals",
                      SCHEDULED_FROM_FIXED, through_write)
            ctx.check("the form and the write path agree",
                      SCHEDULED_FROM_FIXED, observed)
    finally:
        try:
            if user_id:
                archive_user(rpc, user_id)
        except Exception:                                    # noqa: BLE001
            pass
        safe_sweep(ctx)


# ===========================================================================
# TC170
# ===========================================================================
@test_case(
    id="TEST-WF021-TC170",
    name="Setting the category to 'Finished Goods' on the form auto-assigns "
         "Level D",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module=MODULE, priority="P1", kind="API", order=21170,
    description="_onchange_categ_id fills an empty Cycle Count Category with "
                "Level D before saving, never overwrites a level that is "
                "already set, and does not fire for a category named "
                "'Finished Goods ' with one trailing space.",
    traceability=trace("DATAONE-TC170"))
def test_tc170(ctx):
    require_cycle_count(ctx)
    rpc = ctx.adapter.rpc
    open_namespace(ctx)
    user_id = None
    categories = []
    try:
        with ctx.step("Preconditions: TD-PC-01 Finished Goods, TD-PC-02 and "
                      "the levelless TD-CC-02"):
            levels = require_shipped_levels(ctx)
            live_before = _live_finished_goods(rpc)
            ctx.log(f"live 'Finished Goods' categories before the fixture: "
                    f"{live_before}")
            # A WF021-namespaced duplicate named exactly 'Finished Goods'.
            # product_category.name has no unique constraint
            # (product/models/product_category.py:16) and convention rule 3
            # forbids touching the live row.
            fg_id = make_category(rpc, "FG", name=FINISHED_GOODS_NAME)
            components_id = make_category(rpc, "COMPONENTS")
            categories = [fg_id, components_id]
            product_id = make_product(ctx, "CC02", storable=True,
                                      categ_id=components_id)
            ctx.log(f"TD-PC-01 = {fg_id} ({FINISHED_GOODS_NAME!r}), "
                    f"TD-PC-02 = {components_id}, TD-CC-02 = {product_id}")

        with ctx.step("Log in as TD-U-04 and open TD-CC-02 in the product "
                      "form"):
            user_id, login, user_rpc = _stock_manager_session(ctx)
            state = _form_open(rpc, "product.product", product_id,
                               ["categ_id"] + CYCLE_COUNT_FIELDS)
            ctx.check("the form opens on TD-PC-02 Components", components_id,
                      state["categ_id"])

        with ctx.step("Assert Cycle Count Category is empty"):
            ctx.check("Cycle Count Category on open", None,
                      state["cycle_count_category_id"] or None)

        with ctx.step("Change Product Category to TD-PC-01 Finished Goods"):
            _form_change(user_rpc, "product.product", [product_id], state,
                         {"categ_id": fg_id})
            ctx.check("the form now carries TD-PC-01", fg_id,
                      state["categ_id"])

        with ctx.step("Assert, before saving, that Cycle Count Category has "
                      "been filled with Level D"):
            ctx.check("Level D filled in by _onchange_categ_id "
                      "(product_product.py:20-23)", levels["D"],
                      state["cycle_count_category_id"])

        with ctx.step("Save and assert the stored cycle_count_category_id "
                      "resolves to dto_cycle_count."
                      "cycle_count_category_level_d"):
            rpc.write("product.product", [product_id],
                      {"categ_id": fg_id,
                       "cycle_count_category_id":
                           state["cycle_count_category_id"]})
            ctx.check(f"the stored level resolves to {LEVEL_D_XMLID}",
                      rpc.ref(LEVEL_D_XMLID), level_of(rpc, product_id))

        with ctx.step("Set the level manually to Level B and save"):
            _form_change(user_rpc, "product.product", [product_id], state,
                         {"cycle_count_category_id": levels["B"]})
            rpc.write("product.product", [product_id],
                      {"cycle_count_category_id": levels["B"]})
            ctx.check("Level B is stored", levels["B"],
                      level_of(rpc, product_id))

        with ctx.step("Change the category away from Finished Goods and back "
                      "to Finished Goods"):
            away = _form_change(user_rpc, "product.product", [product_id],
                                state, {"categ_id": components_id})
            back = _form_change(user_rpc, "product.product", [product_id],
                                state, {"categ_id": fg_id})
            rpc.write("product.product", [product_id], {"categ_id": fg_id})
            ctx.log("onchange reported: away="
                    f"{(away.get('value') or {})!r} back="
                    f"{(back.get('value') or {})!r}")

        with ctx.step("Assert the level is still Level B — an existing level "
                      "is never overwritten"):
            ctx.check("Level B survives the category round trip",
                      {"on the form": levels["B"],
                       "stored after save": levels["B"]},
                      {"on the form": state["cycle_count_category_id"],
                       "stored after save": level_of(rpc, product_id)})

        with ctx.step("Rename TD-PC-01 to 'Finished Goods ' (one trailing "
                      "space) in a scratch copy of the fixture, create a new "
                      "levelless storable product in it, set the category, "
                      "and assert no level is assigned"):
            near_id = near_miss_category(rpc)
            categories.append(near_id)
            # The create() half — models/product_product.py:69 compares with
            # ==, so the trailing space cannot match.
            created_id = make_product(ctx, "CC02-SPACE", storable=True,
                                      categ_id=near_id)
            # The onchange half — the same literal at :22.
            probe_id = make_product(ctx, "CC02-SPACE-FORM", storable=True,
                                    categ_id=components_id)
            probe_state = _form_open(rpc, "product.product", probe_id,
                                     ["categ_id"] + CYCLE_COUNT_FIELDS)
            _form_change(user_rpc, "product.product", [probe_id], probe_state,
                         {"categ_id": near_id})
            ctx.check("the exact-match rule does not fire for "
                      f"{FINISHED_GOODS_TRAILING_SPACE!r}",
                      {"after create()": None,
                       "after the form onchange": None},
                      {"after create()": level_of(rpc, created_id),
                       "after the form onchange":
                           probe_state["cycle_count_category_id"] or None})

        with ctx.step("Record step 9's outcome as the documented fragility "
                      "of the hard-coded string, and restore the category "
                      "name"):
            ctx.log("DOCUMENTED FRAGILITY: the Finished-Goods rule is an "
                    "exact, case- and whitespace-sensitive Python compare in "
                    "four places — product_product.py:22 and :69, "
                    "product_template.py:69 and its create-less twin. A "
                    "rename, a translation or a stray trailing space "
                    "silently disables the whole of F082.")
            # Nothing was renamed, so nothing needs restoring — the live
            # rows are re-read to prove it (convention rule 3).
            ctx.check("every live 'Finished Goods' category is untouched",
                      live_before,
                      _live_finished_goods(rpc, exclude_ids=categories))
    finally:
        try:
            if user_id:
                archive_user(rpc, user_id)
        except Exception:                                    # noqa: BLE001
            pass
        safe_sweep(ctx)
        _drop_records(rpc, "product.category", categories)


# ===========================================================================
# TC171
# ===========================================================================
@test_case(
    id="TEST-WF021-TC171",
    name="A product created by import or RPC also receives Level D through "
         "create()",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module=MODULE, priority="P1", kind="DATA", order=21171,
    description="create() with a list of three vals dicts assigns Level D to "
                "every Finished-Goods record that has no level, keeps a "
                "supplied Level B and leaves a Components record levelless, "
                "and no onchange runs on the create()/load() path.",
    traceability=trace("DATAONE-TC171"))
def test_tc171(ctx):
    require_cycle_count(ctx)
    rpc = ctx.adapter.rpc
    open_namespace(ctx)
    categories = []
    try:
        with ctx.step("Preconditions: TD-PC-01 Finished Goods, TD-PC-02 and "
                      "Level D"):
            levels = require_shipped_levels(ctx)
            fg_id = make_category(rpc, "FG", name=FINISHED_GOODS_NAME)
            components_id = make_category(rpc, "COMPONENTS")
            categories = [fg_id, components_id]
            ctx.log(f"TD-PC-01 = {fg_id}, TD-PC-02 = {components_id}, "
                    f"Level D = {levels['D']}")

        with ctx.step("Log in as TD-U-08"):
            row = rpc.read("res.users", [rpc.uid], ["login", "name"])[0]
            ctx.log(f"the import runs as uid {rpc.uid} ({row['login']!r}) — "
                    "TD-U-08 dto_admin is the configured session user, which "
                    "is also the only session in this case: every record "
                    "below is created through the ORM, never through a form.")
            ctx.check_true("the acting session is authenticated",
                           bool(rpc.uid),
                           actual_desc=f"uid {rpc.uid} ({row['login']})")

        with ctx.step("Through the ORM (not the form), call "
                      "env['product.product'].create([{...}]) with type "
                      "storable and categ_id TD-PC-01"):
            single = make_products(ctx, [{"label": "IMPORT-A",
                                          "categ_id": fg_id}])
            ctx.check("create() returned exactly one id", 1, len(single))
            ctx.log(f"created {single} through create() with a one-item list")

        with ctx.step("Assert the created variant's cycle_count_category_id "
                      "resolves to Level D"):
            ctx.check(f"the variant resolves to {LEVEL_D_XMLID}",
                      rpc.ref(LEVEL_D_XMLID), level_of(rpc, single[0]))

        with ctx.step("Call create() with a list of three vals dicts: one in "
                      "Finished Goods with no level, one in Finished Goods "
                      "with Level B supplied, one in TD-PC-02 Components "
                      "with no level"):
            # One call with THREE dicts. product.product.create is
            # @api.model_create_multi (models/product_product.py:63) and
            # loops `for product in records` (:68); a port that reintroduced
            # a single-dict assumption would assign Level D to the first
            # record only, which a single-record test cannot see.
            batch = make_products(ctx, [
                {"label": "BATCH-FG-NOLEVEL", "categ_id": fg_id},
                {"label": "BATCH-FG-LEVELB", "categ_id": fg_id,
                 "cycle_count_category_id": levels["B"]},
                {"label": "BATCH-COMPONENTS", "categ_id": components_id},
            ])
            ctx.check("create() returned three ids in vals order", 3,
                      len(batch))
            ctx.log(f"created {batch} in one create() call")

        with ctx.step("Assert record 1 receives Level D"):
            ctx.check("record 1 (Finished Goods, no level supplied)",
                      levels["D"], level_of(rpc, batch[0]))

        with ctx.step("Assert record 2 keeps Level B — supplied levels are "
                      "never overwritten"):
            ctx.check("record 2 (Finished Goods, Level B supplied)",
                      levels["B"], level_of(rpc, batch[1]))

        with ctx.step("Assert record 3 receives no level"):
            ctx.check("record 3 (TD-PC-02 Components, no level supplied)",
                      None, level_of(rpc, batch[2]))

        with ctx.step("Import a CSV creating a product.template in Finished "
                      "Goods without creating a variant explicitly, and "
                      "assert the documented gap"):
            # load() IS the import path and is public (@api.model,
            # odoo/models.py:1145). categ_id is supplied as a database id so
            # the duplicate 'Finished Goods' names cannot make the match
            # ambiguous; the selection cell carries the KEY, which
            # _str_to_selection accepts (ir_fields.py:362-380).
            storable = storable_values(ctx)
            fields_ = ["name", "default_code", "categ_id/.id"] + list(storable)
            row = ([tag("IMPORT-TMPL"), code("IMPORT-TMPL"), str(fg_id)]
                   + [_import_value(value) for value in storable.values()])
            result = rpc.call("product.template", "load", fields_, [row]) or {}
            messages = result.get("messages") or []
            tmpl_ids = result.get("ids") or []
            ctx.check("the import reported no message and created one "
                      "template", {"messages": [], "templates": 1},
                      {"messages": messages, "templates": len(tmpl_ids)})
            variants = variants_of(rpc, tmpl_ids[0]) if tmpl_ids else []
            template = rpc.read("product.template", tmpl_ids,
                                ["cycle_count_category_id",
                                 TEMPLATE_VARIANT_LEVEL_FIELD])[0]
            variant_level = (level_of(rpc, variants[0]) if variants else None)
            ctx.log("template-only import: variants="
                    f"{variants} variant level={variant_level} "
                    "template.cycle_count_category_id="
                    f"{m2o_id(template['cycle_count_category_id'])} "
                    f"{TEMPLATE_VARIANT_LEVEL_FIELD}="
                    f"{m2o_id(template[TEMPLATE_VARIANT_LEVEL_FIELD])}")
            # WF-021 A4: nothing assigns a level at TEMPLATE level.
            # dto_cycle_count/models/product_template.py has no CRUD section
            # at all (the file ends at :102), so both template-side fields
            # can only ever MIRROR the variant — the computed triple through
            # _compute_template_field_from_variant_field
            # (product/models/product_template.py:238) and the stored
            # variant_cycle_count_category_id through its related.
            ctx.check("the template only mirrors its variant — no "
                      "template-level rule exists",
                      {"computed": variant_level, "stored mirror":
                          variant_level},
                      {"computed": m2o_id(template["cycle_count_category_id"]),
                       "stored mirror":
                           m2o_id(template[TEMPLATE_VARIANT_LEVEL_FIELD])})

        with ctx.step("Record step 8's outcome as the accepted v17 baseline"):
            ctx.log("ACCEPTED v17 BASELINE — the template-only import path "
                    f"left the variant on level {variant_level!r}. "
                    "product.template.create calls _create_variant_ids "
                    "(product/models/product_template.py:727) which calls "
                    "Product.create(variants_to_create) (:804), so the "
                    "variant passes through the module's own "
                    "product.product.create override "
                    "(models/product_product.py:63-72) and categ_id "
                    "resolves through _inherits to the template's category. "
                    "The gap A4 names is the absence of any template-level "
                    "rule, asserted in step 8.")

        with ctx.step("Assert none of the created products triggered a UI "
                      "onchange — confirm by asserting the import ran "
                      "through load()/create() only"):
            # _onchange_cycle_count_category_id (product_product.py:25-29) is
            # the ONLY thing that writes scheduled_count_date on a product
            # outside _apply_inventory. Record 2 was created with Level B AND
            # a last_count_date default of today (:14), so a form save would
            # have produced today + 1 week. Every one of these is empty,
            # which is the observable proof that no onchange ran.
            created = list(single) + list(batch) + list(variants)
            scheduled = {
                product_id: iso(row["scheduled_count_date"]) or None
                for product_id, row in zip(
                    created,
                    rpc.read("product.product", created,
                             ["scheduled_count_date"]))}
            ctx.check("no scheduled_count_date was computed anywhere on the "
                      "create()/load() path",
                      {product_id: None for product_id in created}, scheduled)
    finally:
        safe_sweep(ctx)
        _drop_records(rpc, "product.category", categories)


# ===========================================================================
# TC172
# ===========================================================================
@test_case(
    id="TEST-WF021-TC172",
    name="A storable product cannot be saved without a cycle-count level in "
         "the UI, but the ORM permits it",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module=MODULE, priority="P1", kind="HYBRID", order=21172,
    description="BR-3 is a view modifier on the rendered arch that evaluates "
                "true for a storable product — not an @api.constrains — so "
                "the same product created through the ORM is accepted with "
                "no level and no scheduled date.",
    traceability=trace("DATAONE-TC172"))
def test_tc172(ctx):
    require_cycle_count(ctx)
    rpc = ctx.adapter.rpc
    open_namespace(ctx)
    user_id = None
    categories = []
    try:
        with ctx.step("Preconditions: TD-PC-02 Components and the five "
                      "levels"):
            levels = require_shipped_levels(ctx)
            components_id = make_category(rpc, "COMPONENTS")
            categories = [components_id]
            today = server_today(ctx)
            ctx.log(f"TD-PC-02 = {components_id}; the server's own today is "
                    f"{iso(today)}")

        with ctx.step("Log in as TD-U-04 and create a new product"):
            user_id, login, user_rpc = _stock_manager_session(ctx)
            tracked = (["type", "categ_id"] + CYCLE_COUNT_FIELDS
                       + [name for name in _storable_fields(ctx)
                          if name != "type"])
            # The client opens a new form on the server's own defaults; no
            # value below is invented by the test.
            defaults = user_rpc.call("product.product", "default_get",
                                     tracked) or {}
            state = {name: _scalar(defaults.get(name, False))
                     for name in tracked}
            ctx.log(f"new-form defaults: {state!r}")
            ctx.check("the new form starts with today's Last Count Date "
                      "(models/product_product.py:10-11,14)", iso(today),
                      iso(state["last_count_date"]))

        with ctx.step("Set the name, set the type to storable, set the "
                      "category to TD-PC-02 Components"):
            _form_change(user_rpc, "product.product", [], state,
                         dict(storable_values(ctx)))
            _form_change(user_rpc, "product.product", [], state,
                         {"categ_id": components_id})
            ctx.check("the form carries a storable product in TD-PC-02",
                      dict(storable_values(ctx), categ_id=components_id),
                      {name: state[name]
                       for name in list(storable_values(ctx)) + ["categ_id"]})

        with ctx.step("Leave Cycle Count Category empty"):
            ctx.check("Cycle Count Category is empty and nothing filled it "
                      "in — TD-PC-02 is not Finished Goods", None,
                      state["cycle_count_category_id"] or None)

        arch = arch_of(ctx, "product.product", VIEW_PRODUCT_FORM)
        group = group_attrs(arch, CYCLE_COUNT_GROUP) or {}
        level_field = field_attrs(arch, "cycle_count_category_id",
                                  within_group=CYCLE_COUNT_GROUP) or {}
        with ctx.step("Attempt to save"):
            ctx.log("the save is attempted by the web client, which "
                    "evaluates the view modifiers before it ever calls "
                    "web_save; the rendered modifiers are read back here "
                    f"instead: group={group!r} field={level_field!r}")
            ctx.check_true("the Cycle Count group is present in the composed "
                           "arch", bool(group), actual_desc=repr(group))

        with ctx.step("Assert the save is refused with the standard "
                      "required-field error and the Cycle Count Category "
                      "field is highlighted"):
            # The error text and the highlight are produced by the web
            # client from this modifier; there is no server-side string and
            # no @api.constrains anywhere in the module (step 11 proves it).
            # Evaluating the modifier against the form's own values is what
            # the client does, and keeps the assertion free of the
            # version-shaped literal that belongs to TC177.
            ctx.check("Cycle Count Category is required for this storable "
                      "product (product_product_views.xml:11)", True,
                      _modifier(level_field.get("required"), state))
            ctx.log("the refusal dialog and the red field outline are "
                    "browser-rendered; an HttpCase tour is the only way to "
                    "observe them, and it would assert the web client, not "
                    "this module. What the module contributes is the "
                    "modifier asserted above.")

        with ctx.step("Assert the Cycle Count group is visible on this "
                      "storable product"):
            ctx.check("the group's invisible modifier is false while the "
                      "product is storable", False,
                      _modifier(group.get("invisible"), state))

        with ctx.step("Change the product type to a service and assert the "
                      "Cycle Count group becomes hidden and the level, "
                      "last-count date and scheduled-count date are cleared"):
            _form_change(user_rpc, "product.product", [], state,
                         _non_storable_values(ctx),
                         spec_fields=_storable_fields(ctx))
            ctx.check("the group is hidden and the three fields are cleared",
                      {"group hidden": True,
                       "cycle_count_category_id": None,
                       "last_count_date": None,
                       "scheduled_count_date": None},
                      dict(_cycle_state(state),
                           **{"group hidden":
                              _modifier(group.get("invisible"), state)}))

        with ctx.step("Change the type back to storable and assert the three "
                      "fields are restored from _origin"):
            _form_change(user_rpc, "product.product", [], state,
                         dict(storable_values(ctx)),
                         spec_fields=_storable_fields(ctx))
            # This record was never saved, so _origin is the EMPTY recordset
            # and the restore branch (product_product.py:41-46) yields
            # exactly: no level, no scheduled date, and last_count_date from
            # `self._origin.last_count_date or self._default_last_count_date()`
            # — the server's own today. A level typed before the toggle is
            # genuinely lost, which is the behaviour this step describes.
            ctx.check("the group is visible again and the three fields come "
                      "back from _origin",
                      {"group hidden": False,
                       "cycle_count_category_id": None,
                       "last_count_date": iso(today),
                       "scheduled_count_date": None},
                      dict(_cycle_state(state),
                           **{"group hidden":
                              _modifier(group.get("invisible"), state)}))

        with ctx.step("Set a level and save successfully"):
            levelled_id = make_product(ctx, "TC172-LEVELLED", storable=True,
                                       categ_id=components_id,
                                       level_id=levels["B"])
            ctx.check("the correctly levelled product saved", levels["B"],
                      level_of(rpc, levelled_id))

        with ctx.step("Log in as TD-U-08 and create() a storable product "
                      "without a level through the ORM"):
            row = rpc.read("res.users", [rpc.uid], ["login"])[0]
            ctx.log(f"the ORM half runs as uid {rpc.uid} "
                    f"({row['login']!r}) — TD-U-08 dto_admin")
            raised, message = expect_error(
                make_product, ctx, "TC172-LEVELLESS", storable=True,
                categ_id=components_id)
            ctx.check_true("the ORM create was not refused", not raised,
                           actual_desc=message or "no error")
            levelless_ids = rpc.search(
                "product.product", [("default_code", "=",
                                     code("TC172-LEVELLESS"))])

        with ctx.step("Assert the ORM create succeeds — there is no "
                      "@api.constrains"):
            ctx.check("exactly one levelless storable product was created",
                      1, len(levelless_ids))

        with ctx.step("Assert the resulting product has "
                      "cycle_count_category_id == False and no "
                      "scheduled_count_date, and would therefore never be "
                      "scheduled by Step 10 of WF-021"):
            stored = rpc.read("product.product", levelless_ids,
                              ["cycle_count_category_id",
                               "scheduled_count_date"])[0]
            ctx.check("the product saved unscheduled",
                      {"cycle_count_category_id": None,
                       "scheduled_count_date": None},
                      {"cycle_count_category_id":
                          m2o_id(stored["cycle_count_category_id"]),
                       "scheduled_count_date":
                          iso(stored["scheduled_count_date"]) or None})

        with ctx.step("Record steps 11–12 as the documented v17 gap"):
            ctx.log("DOCUMENTED v17 GAP: BR-3 is enforced by "
                    "required=\"…\" on product_product_views.xml:11 and its "
                    "product_template twin only. dto_cycle_count declares no "
                    "@api.constrains and no required=True on the Python "
                    "field (models/product_product.py:13), so the UI blocks "
                    "a human and nothing blocks an import, an RPC client or "
                    "the Workday feed. Every un-scheduled storable product "
                    "in the database came through this gap; TC177 step 12 "
                    "measures how many.")
    finally:
        try:
            if user_id:
                archive_user(rpc, user_id)
        except Exception:                                    # noqa: BLE001
            pass
        safe_sweep(ctx)
        _drop_records(rpc, "product.category", categories)


# ===========================================================================
# TC173
# ===========================================================================
@test_case(
    id="TEST-WF021-TC173",
    name="Level B with Last Count Date 2026-08-20 displays Scheduled Count "
         "Date 2026-08-27 before saving",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module=MODULE, priority="P1", kind="API", order=21173,
    description="The workflow's worked example: the onchange shows "
                "2026-08-27 before saving, the field is rendered readonly "
                "with force_save, the saved record stores 2026-08-27, and "
                "2026-08-21 moves the display to 2026-08-28.",
    traceability=trace("DATAONE-TC173"))
def test_tc173(ctx):
    require_cycle_count(ctx)
    rpc = ctx.adapter.rpc
    open_namespace(ctx)
    user_id = None
    categories = []
    try:
        with ctx.step("Preconditions: TD-CC-03 on a level with quants in "
                      "TD-L-03, and Level B"):
            levels = require_shipped_levels(ctx)
            categ_id = make_category(rpc, "CC03-CATEG")
            categories = [categ_id]
            product_id = make_product(ctx, "CC03", storable=True,
                                      categ_id=categ_id,
                                      level_id=levels["A"])
            location_id = internal_locations(ctx, 1)[0]
            try:
                add_stock(ctx, product_id, location_id, 5.0)
            except OdooRPCError as exc:
                # TD-L-03's quants are a precondition of the workbook's
                # wording; no assertion in this case reads a quant, so the
                # case is still meaningful without them and says so rather
                # than erroring on a fixture it does not use.
                ctx.log(f"[note] could not stage stock in location "
                        f"{location_id}: {exc} — no assertion here reads a "
                        "quant.")
            ctx.log(f"TD-CC-03 = {product_id}, TD-L-03 = {location_id}, "
                    f"quant = {quant_of(rpc, product_id, location_id)}")

        with ctx.step("Log in as TD-U-04 and open TD-CC-03 in the product "
                      "form"):
            user_id, login, user_rpc = _stock_manager_session(ctx)
            state = _form_open(rpc, "product.product", product_id,
                               ["categ_id"] + CYCLE_COUNT_FIELDS)
            ctx.check("the form opens on the fixture's level", levels["A"],
                      state["cycle_count_category_id"])

        with ctx.step("Set Last Count Date to 2026-08-20"):
            _form_change(user_rpc, "product.product", [product_id], state,
                         {"last_count_date": FIXED_COUNT_DATE})
            ctx.check("Last Count Date on the form", FIXED_COUNT_DATE,
                      iso(state["last_count_date"]))
            ctx.log("the arch renders last_count_date readonly=\"1\" "
                    "(product_product_views.xml:12), so a real user could "
                    "not type this; the value is driven through the same "
                    "onchange the form fires, and the fixture already "
                    "carries it in storage.")

        with ctx.step("Set Cycle Count Category to Level B"):
            _form_change(user_rpc, "product.product", [product_id], state,
                         {"cycle_count_category_id": levels["B"]})
            ctx.check("Cycle Count Category on the form", levels["B"],
                      state["cycle_count_category_id"])

        with ctx.step("Without saving, read Scheduled Count Date"):
            displayed = iso(state["scheduled_count_date"])
            ctx.log(f"Scheduled Count Date displays {displayed!r} with "
                    "nothing written to the database yet")
            ctx.check_true("the onchange produced a value before saving",
                           bool(displayed), actual_desc=repr(displayed))

        with ctx.step("Assert it displays 2026-08-27"):
            ctx.check("Scheduled Count Date before saving",
                      SCHEDULED_FROM_FIXED["B"], displayed)

        with ctx.step("Assert the field is rendered read-only"):
            arch = arch_of(ctx, "product.product", VIEW_PRODUCT_FORM)
            attrs = field_attrs(arch, "scheduled_count_date",
                                within_group=CYCLE_COUNT_GROUP) or {}
            ctx.log(f"scheduled_count_date attributes: {attrs!r}")
            ctx.check("readonly on the rendered arch "
                      "(product_product_views.xml:13)", True,
                      _modifier(attrs.get("readonly"), state))

        with ctx.step("Save"):
            # force_save="1" is exactly what decides whether the client
            # sends a readonly field's value, so the save below mirrors the
            # arch just asserted rather than assuming it. If a port drops
            # force_save, the field is not sent, the stored value stays
            # empty and step 8 fails — which is the divergence the v19 watch
            # describes and only a displayed-AND-stored pair can catch.
            save_values = {"last_count_date": FIXED_COUNT_DATE,
                           "cycle_count_category_id": levels["B"]}
            if _truthy_attr(attrs.get("force_save")):
                save_values["scheduled_count_date"] = displayed
            ctx.log(f"the client sends {sorted(save_values)} "
                    f"(force_save={attrs.get('force_save')!r})")
            rpc.write("product.product", [product_id], save_values)

        with ctx.step("Assert the stored scheduled_count_date is 2026-08-27 "
                      "— the onchange value persisted despite the readonly"):
            stored = rpc.read("product.product", [product_id],
                              ["cycle_count_category_id", "last_count_date",
                               "scheduled_count_date"])[0]
            ctx.check("the saved record",
                      {"cycle_count_category_id": levels["B"],
                       "last_count_date": FIXED_COUNT_DATE,
                       "scheduled_count_date": SCHEDULED_FROM_FIXED["B"]},
                      {"cycle_count_category_id":
                          m2o_id(stored["cycle_count_category_id"]),
                       "last_count_date": iso(stored["last_count_date"]),
                       "scheduled_count_date":
                          iso(stored["scheduled_count_date"])})

        with ctx.step("Change Last Count Date to 2026-08-21 without touching "
                      "the level"):
            _form_change(user_rpc, "product.product", [product_id], state,
                         {"last_count_date": SECOND_COUNT_DATE})
            ctx.check("Last Count Date on the form", SECOND_COUNT_DATE,
                      iso(state["last_count_date"]))
            ctx.check("the level was not touched", levels["B"],
                      state["cycle_count_category_id"])

        with ctx.step("Assert the displayed scheduled date updates to "
                      "2026-08-28 before saving — the onchange depends on "
                      "both fields"):
            ctx.check("Scheduled Count Date after the Last Count Date change",
                      SECOND_SCHEDULED_LEVEL_B,
                      iso(state["scheduled_count_date"]))

        with ctx.step("Restore 2026-08-20 and save"):
            _form_change(user_rpc, "product.product", [product_id], state,
                         {"last_count_date": FIXED_COUNT_DATE})
            restore = {"last_count_date": FIXED_COUNT_DATE}
            if _truthy_attr(attrs.get("force_save")):
                restore["scheduled_count_date"] = iso(
                    state["scheduled_count_date"])
            rpc.write("product.product", [product_id], restore)
            stored = rpc.read("product.product", [product_id],
                              ["last_count_date", "scheduled_count_date"])[0]
            ctx.check("the restored record",
                      {"last_count_date": FIXED_COUNT_DATE,
                       "scheduled_count_date": SCHEDULED_FROM_FIXED["B"]},
                      {"last_count_date": iso(stored["last_count_date"]),
                       "scheduled_count_date":
                          iso(stored["scheduled_count_date"])})
            ctx.log("the workbook's postcondition leaves TD-CC-03 in place "
                    "for TC174; convention rule 5 forbids cross-test fixture "
                    "dependence, so this namespace is swept and TC174 builds "
                    "its own.")
    finally:
        try:
            if user_id:
                archive_user(rpc, user_id)
        except Exception:                                    # noqa: BLE001
            pass
        safe_sweep(ctx)
        _drop_records(rpc, "product.category", categories)
