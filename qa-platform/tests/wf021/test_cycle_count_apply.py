"""DATAONE-WF-021 — the apply gate, the re-schedule loop, the view surface
and the v19 ``type == 'product'`` detector: TC174, TC175, TC176, TC177.

What this file proves
=====================

``dto_cycle_count`` ships **no cron and no scheduled action**
(``__manifest__.py:24-42`` on ``main`` — BR-7). The whole counting programme
rides on ``stock.quant.inventory_date`` and core's own *To Count* filter,
domain ``[('inventory_date','<=', context_today())]``
(``stock/views/stock_quant_views.xml:37``, v19 ``:39``). Two overrides keep
that date correct, and this file is about both of them plus the view surface
that makes the programme workable and the version delta that would silently
switch it off.

``stock.quant._apply_inventory`` — TC174
----------------------------------------
``git show main:project-addons/dto_cycle_count/models/stock_quant.py``::

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

Four writes, two of them on the product. A partial port typically drops the
product-side pair and nothing complains, so all four are asserted in ONE
mismatch dict (TC174 step 8) before the four workbook steps assert their own
field individually.

``product.product.write`` — TC175
---------------------------------
``git show main:…/models/product_product.py``::

    def write(self, vals):                                             # :53
        res = super().write(vals)                                      # :54
        if 'cycle_count_category_id' in vals:                          # :57
            stock_quants = self.stock_quant_ids.sudo()                 # :58
            for quant in stock_quants:                                 # :59
                quant.inventory_date = quant.cycle_count_category_id \\
                    ._calculate_scheduled_count_date(quant.last_count_date)  # :60

Three facts this file leans on and asserts rather than assumes:

* the gate is **key presence, not value change** (``:57``) — re-writing the
  same level re-runs the whole loop, which is how TC175's fixture makes the
  SERVER compute the 2027-02-20 baseline instead of the test stamping it;
* the loop reads the level off the **quant's** stored related field
  (``models/stock_quant.py:13-14``), and
  ``cycle.count.category._calculate_scheduled_count_date`` opens with
  ``ensure_one()`` (``cycle_count_category.py:23``) — so clearing the level
  makes the loop raise ``ValueError: Expected singleton`` *after*
  ``super().write`` already set it, and the server rolls the whole write
  back. That is TC175 step 9's "both revert together", performed by the
  server rather than by a transaction the RPC client cannot control;
* the loop is ``sudo()``-ed, so product-write rights ALONE rewrite quant
  scheduling — TC175 step 11's privilege surface.

The view surface — TC176
------------------------
Nine ``ir.ui.view`` records, none of them on a product LIST view. The
artefacts the workbook names live in the composed arch ``get_view`` returns
(``main:views/product_product_views.xml:10-13, 25, 28``;
``product_template_views.xml:10-13, 25, 28``;
``stock_quant_views.xml:10, 21, 24``) plus the real bucketing ``read_group``
produces. Visual layout and column ordering are UIX's by the workbook's own
note, so nothing is lost by asserting the arch instead of a browser tour.

The delta — TC177
-----------------
v19 deleted ``'product'`` from ``product.template.type``
(v19 ``product/models/product_template.py:54-65``; zero v19 addon re-adds
it) in favour of ``is_storable`` (v19 ``stock/models/product.py:829-831``).
``dto_cycle_count`` carries the literal at eight sites — four XML modifiers
and two ``_onchange_type`` branches across two models. On v19 the v17
expressions are constants: ``required="type == 'product'"`` permanently
false, ``invisible="type != 'product'"`` permanently true. Nothing raises.

TC177 is therefore the **one sanctioned ``ctx.env.version`` exception**
(``AUTOMATION_CONVENTIONS:143-149``): its SUBJECT is the delta, so it
computes its own expected modifier expression per version. Every other test
in this file routes storability through ``ctx.adapter.storable_product_values()``
and list-view naming through ``fg_common.list_tag``.

Workbook corrections carried in this file
=========================================

1. **TC174 dates are relational.** v17's ``_apply_inventory(self)`` takes no
   ``date`` argument (``models/stock_quant.py:17``; core v17
   ``stock/models/stock_quant.py:1050``) and an RPC client cannot freeze the
   clock, so the workbook's 2026-08-20 → 2026-08-27 is asserted as the
   RELATIONSHIP it expresses: the server's own today (read through
   ``default_get`` on the module's own default, never from the test host)
   and today + 1 week for Level B. The back-dated form is reachable only on
   v19 through ``action_apply_inventory(date)`` and belongs to NEW, which the
   workbook itself says to reference rather than duplicate.
2. **TC174 step 15 / flow A3 — v17 has no zero-variance skip.** The
   ``if/else`` on ``float_compare(inventory_diff_quantity, 0) > 0`` appends a
   ``move_val`` on BOTH branches (``stock/models/stock_quant.py:1056-1066``),
   ``_get_inventory_move_values`` names the zero case ``Product Quantity
   Confirmed`` (``:1265-1268``), and ``_action_done`` exempts
   ``is_inventory`` moves from the zero-quantity cancel (``stock_move.py:1889,
   1896``). A zero-variance apply therefore DOES create a ZERO-quantity
   ``stock.move.line``. The step is implemented as its own step 7 words it —
   "a stock.move.line ... **for the variance**": the assertion is that no
   line carrying a variance quantity appears, and the zero-quantity
   confirmation line core does create is recorded. The half this workflow
   owns — "the next count is still booked" — is asserted in full.
3. **TC175 step 9** — an RPC client cannot roll a transaction back; each
   ``/web/dataset/call_kw`` call commits its own
   (``AUTOMATION_CONVENTIONS:80-82``). The server's OWN rollback is used
   instead: clearing the level makes the sudo loop raise ``Expected
   singleton`` after ``super().write`` already stored it, so the level and
   every quant date must be found unchanged together.
4. **TC176 step 5** — ``dto_cycle_count`` inherits no product LIST view
   (its nine views are the two product forms, the two product searches, the
   quant inventory list, the quant search and the three level views). What
   the module actually provides on the product side is the search field and
   the group-by filter, and that is what "available and can be grouped by"
   is asserted as: the field is declared and STORED on the model, the search
   view declares the group-by, and a real ``read_group`` buckets correctly.
5. **TC176 step 6** — the ``product.product`` search ``filter_domain`` is
   ``[('name', 'ilike', self)]`` (``views/product_product_views.xml:25``):
   it searches the PRODUCT's own name, not the category. Defect **D-new-6**,
   deliberately preserved by the v19 port. The attribute is asserted
   literally and the domain it declares is executed; no category-name search
   is claimed to work through it. The two views that DO name the category
   correctly (template search ``:25``, quant search ``:21``) are exercised
   where the workbook names them.
6. **TC177 steps 5-6** — ``required`` is a VIEW MODIFIER. There is no
   ``required=True`` and no ``@api.constrains`` anywhere in the module's
   Python (``models/product_product.py:13-15``), so the ORM accepts a
   levelless storable product on BOTH versions; the browser refuses the save
   by evaluating the modifier. The server-observable content of "the save is
   refused" is asserted in full: the declared predicate equals the
   version-correct expression, and that predicate evaluates TRUE for a
   storable product and FALSE for a service one — i.e. it is not the
   constant the v19 regression turns it into. The ORM leak itself is TC172's
   subject and is recorded here, not re-asserted.

EXPECTED OUTCOMES
=================
* ``TEST-WF021-TC174`` — **EXPECTED v17 OUTCOME: PASS** — the gate the
  workflow is accepted on; every assertion is about v17-and-v19 behaviour
  that the baseline already implements.
* ``TEST-WF021-TC175`` — **EXPECTED v17 OUTCOME: PASS** — step 11 alone may
  report BLOCKED if the target grants ``product.product`` write only through
  ``stock.group_stock_manager``.
* ``TEST-WF021-TC176`` — **EXPECTED v17 OUTCOME: PASS** — every anchor the
  module xpaths onto exists in v17 core.
* ``TEST-WF021-TC177`` — **EXPECTED v17 OUTCOME: PASS** — the v17
  expressions are correct FOR v17, which is exactly what the workbook asks
  ("run on v17 first to establish that the case passes there"). The
  expectation is computed per version, so no ``EXPECTED v17 OUTCOME: FAIL``
  docstring is warranted anywhere in this file.

Safety
======
Nothing here reaches an external system: ``dto_cycle_count`` ships no cron,
no server action and no mail template, and the workflow sheet's
*Integrations* section is literally "None". No pre-existing record is
modified: every product, category, location, attribute and user is
namespaced with the execution token and swept in a ``finally:`` that cannot
raise. Live-data reads (TC177 step 12) are read-only SQL.
"""
from __future__ import annotations

import datetime

from adapters.base import OdooRPCError
from framework.baselines import baseline_path, load_baseline, save_baseline
from framework.registry import test_case

from tests.wf021.common import (CATEGORY_SEARCH_FILTER_DOMAIN,
                                CYCLE_COUNT_FIELDS, CYCLE_COUNT_GROUP,
                                FIXED_COUNT_DATE, GROUP_STOCK_MANAGER,
                                GROUP_STOCK_USER, MODULE, MODIFIER_SITES,
                                PRODUCT_GROUPBY_FILTER,
                                PRODUCT_SEARCH_FILTER_DOMAIN,
                                QUANT_GROUPBY_FILTER, SINGLETON_ERROR_FRAGMENT,
                                SQL_STORABLE_TOTAL, SQL_STORABLE_WITHOUT_LEVEL,
                                STORABLE_MODIFIERS,
                                TEMPLATE_GROUP_EXTRA_INVISIBLE,
                                TEMPLATE_GROUPBY_FILTER,
                                TEMPLATE_VARIANT_LEVEL_FIELD,
                                TRACEABILITY_GROUP, VIEW_PRODUCT_FORM,
                                VIEW_PRODUCT_SEARCH, VIEW_QUANT_INVENTORY_LIST,
                                VIEW_QUANT_SEARCH, VIEW_TEMPLATE_FORM,
                                VIEW_TEMPLATE_SEARCH, WORKFLOW, WORKFLOW_NAME,
                                add_stock, apply_count, archive_user, arch_of,
                                due_on, ensure_wf021_user,
                                enter_count, expect_error, expected_schedule,
                                field_attrs, filter_attrs, fixture_token,
                                follows, group_attrs, internal_locations,
                                inventory_dates, is_v19_product_shape, iso,
                                level_of, list_root_tag, m2o_id, make_category,
                                make_product, make_template, move_line_rows,
                                move_lines_for, non_manager_product_writer,
                                open_namespace, parse_arch, product_tmpl_of,
                                quant_of, quant_state, quants_of,
                                realtime_category_data, require_cycle_count,
                                require_no_tier_definition,
                                require_shipped_levels, require_stock_manager,
                                rpc_as, safe_sweep, scan_cycle_count,
                                server_today, service_values, set_level,
                                stamp_quant, storable_values, tag, trace,
                                valuation_moves_for)

#: The suite's own Physical Inventory domain — ``action_view_inventory``'s
#: own domain is only this (v17 ``stock/models/stock_quant.py:432``); the
#: due-date gate is the ``to_count`` FILTER, which ``common.due_on`` runs.
PHYSICAL_INVENTORY_DOMAIN = [("location_id.usage", "in",
                              ["internal", "transit"])]

#: The group whose absence strips ``//group[@name='traceability']`` out of
#: the rendered product form — v17 ``stock/views/product_views.xml:126``,
#: v19 ``:221`` both carry ``groups="stock.group_production_lot"``. TC176
#: step 2 is an ORDERING claim about that anchor, so the acting user must
#: hold it or the anchor is simply not in the arch to be ordered against.
GROUP_PRODUCTION_LOT = "stock.group_production_lot"


# ===========================================================================
# Local helpers — only what tests/wf021/common.py does not already provide
# ===========================================================================
def _onchange(rpc, model: str, ids: list, values: dict, field_names: list,
              spec_fields: list | None = None) -> dict:
    """Call the public ``onchange`` **on a given recordset**.

    ``onchange`` is not an ``@api.model`` method on either version (v17
    ``odoo/models.py:7010``, v19 ``odoo/orm/models.py:6996`` — neither
    carries a decorator), so ``call_kw`` routes it through
    ``_call_kw_multi``, which consumes the FIRST positional argument as the
    recordset ids (``odoo/api.py:464-465`` — ``ids, args = args[0],
    args[1:]``). Without the ids the server builds
    ``self.new(..., origin=<empty>)`` and ``self._origin`` is empty, which is
    exactly the thing step 10's restore branch reads
    (``models/product_product.py:43-45``).

    ``tests.wf021.common.onchange`` now takes ``record_ids`` in that same
    leading position and is equivalent; this local copy is kept so the two
    test files in this suite call one helper each with no import churn.

    ``onchange(values, field_names, fields_spec)`` is declared at v17
    ``odoo/models.py:7010`` and implemented at ``addons/web/models/models.py
    :895``; the result is ``{'value': {...}, 'warning': {...}}`` where
    ``value`` carries only the fields the onchange CHANGED. A field absent
    from ``fields_spec`` is never reported, so the spec always carries the
    three cycle-count fields on top of whatever the caller passes — otherwise
    an assertion about them could pass vacuously.
    """
    names = list(dict.fromkeys(
        (spec_fields or []) + list(values.keys()) + CYCLE_COUNT_FIELDS))
    fields_spec = {name: {} for name in names}
    return rpc.call(model, "onchange", list(ids), dict(values),
                    list(field_names), fields_spec) or {}


def _changed(result: dict, field: str):
    """The value ``onchange`` reported for ``field``, shape-normalised.

    ``RecordSnapshot.diff`` formats simple fields through ``web_read``
    (``web/models/models.py:1217``), so a many2one arrives as a bare id, as
    ``[id, name]`` or as ``{'id':…}`` depending on version and spec.
    """
    value = (result.get("value") or {}).get(field)
    if isinstance(value, dict):
        return value.get("id")
    if isinstance(value, (list, tuple)):
        return value[0] if value else None
    return value


def _reported(result: dict) -> dict:
    """``{field: normalised value}`` for the three cycle-count fields.

    Absent means "the onchange did not change it", which is a different
    finding from "it cleared it" — so absence is reported as the sentinel
    string ``'<unchanged>'`` rather than folded into ``False``.
    """
    changed = result.get("value") or {}
    out = {}
    for field in CYCLE_COUNT_FIELDS:
        if field not in changed:
            out[field] = "<unchanged>"
        elif field == "cycle_count_category_id":
            out[field] = _changed(result, field) or False
        else:
            out[field] = iso(_changed(result, field)) or False
    return out


def _group_field_names(arch: str, group_name: str) -> list:
    """The ``<field name=…>`` children of one ``<group name=…>``, in order.

    ``common.field_attrs`` answers "what are this field's attributes"; this
    answers "which fields are in the group and in what order", which is what
    TC176 step 2 asserts. Kept local for the same reason as ``_onchange``.
    """
    root = parse_arch(arch)
    for element in root.iter("group"):
        if element.get("name") == group_name:
            return [child.get("name") for child in element.iter("field")
                    if child.get("name")]
    return []


def _storable_domain(ctx) -> list:
    """A search domain for "storable", built from the adapter's own values.

    ``{'type': 'product'}`` on v17, ``{'type':'consu','is_storable':True}``
    on v19 (``adapters/odoo17.py:24``, ``adapters/odoo19.py:26``) — so no
    version branch is needed even in the case whose subject IS the delta.
    """
    return [(name, "=", value)
            for name, value in sorted(storable_values(ctx).items())]


def _view_says_storable(ctx, values: dict) -> bool:
    """Evaluate the VIEW's storable predicate against a record's own values.

    TC177 only. The expression the view declares is asserted separately
    against ``STORABLE_MODIFIERS[version]``, so this helper is provably
    evaluating the same predicate rather than a paraphrase of it:

    * v17 ``required="type == 'product'"`` / ``invisible="type != 'product'"``
      — ``views/product_product_views.xml:10-11`` on ``main``;
    * v19 ``required="is_storable"`` / ``invisible="not is_storable"``
      — the ported ``:18, :20``.
    """
    if ctx.env.version == "19":
        return bool(values.get("is_storable"))
    return values.get("type") == "product"


def _require_traceability_anchor(ctx):
    """BLOCK when the acting user cannot see the ordering anchor at all."""
    rpc = ctx.adapter.rpc
    group_id = rpc.ref(GROUP_PRODUCTION_LOT)
    groups_field = ctx.adapter.user_groups_field
    row = rpc.read("res.users", [rpc.uid], ["login", groups_field])[0]
    if not group_id or group_id not in (row.get(groups_field) or []):
        ctx.blocked(
            f"User {row['login']!r} (uid {rpc.uid}) on {ctx.env.key} "
            f"(db={ctx.env.db}) does not hold {GROUP_PRODUCTION_LOT}. Core "
            "declares the anchor as <group name=\"traceability\" "
            "groups=\"stock.group_production_lot\"> (v17 "
            "stock/views/product_views.xml:126, v19 :221), so get_view "
            "strips it from the rendered arch for this user and step 2's "
            "ordering claim — 'a Cycle Count group appears after the "
            "traceability group' — has nothing to be ordered against. The "
            "Cycle Count group itself carries no groups attribute and is "
            "still served; only the anchor is missing.")


def _require_valuation_readable(ctx):
    """BLOCK when the acting user cannot read the valuation entry.

    TC174 step 12 asserts a posted ``account.move``. Reading
    ``account.move.line`` needs accounting rights the stock-manager probe
    does not cover, and an AccessError here is a precondition failure rather
    than a defect in the override.
    """
    rpc = ctx.adapter.rpc
    if not rpc.model_exists("account.move.line"):
        ctx.blocked(
            f"account.move.line does not exist on {ctx.env.key} "
            f"(db={ctx.env.db}) — stock_account/account is not installed, so "
            "an applied adjustment posts no valuation entry and step 12 has "
            "nothing to measure.")
    try:
        rpc.search_read("account.move.line", [], ["id"], limit=1)
    except OdooRPCError as exc:
        ctx.blocked(
            f"The acting user (uid {rpc.uid}) cannot read account.move.line "
            f"on {ctx.env.key} (db={ctx.env.db}): {exc}. TC174 step 12 "
            "asserts the valuation account.move core posts for the variance "
            "(stock_account/models/stock_move.py:564-599); without read "
            "access that assertion cannot be made at all.")


# ===========================================================================
# TC174 — the gate
# ===========================================================================
@test_case(
    id="TEST-WF021-TC174",
    name="Applying a count stamps quant and product and pushes "
         "inventory_date to the next scheduled date",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module=MODULE, priority="P0", kind="API", order=21174,
    description="An inventory user enters a counted quantity, a stock "
                "manager applies it, and all four date writes the override "
                "makes — quant last_count_date and inventory_date, product "
                "last_count_date and scheduled_count_date — plus the "
                "variance move line, the valuation entry, the count-sheet "
                "behaviour on both dates and the zero-variance case are "
                "asserted.",
    traceability=trace("DATAONE-TC174"))
def test_tc174(ctx):
    rpc = ctx.adapter.rpc
    require_cycle_count(ctx)
    levels = require_shipped_levels(ctx)
    require_stock_manager(ctx)
    require_no_tier_definition(ctx)
    _require_valuation_readable(ctx)
    open_namespace(ctx)

    user_id = None
    try:
        with ctx.step("Precondition: TD-CC-03 on Level B with two quants, "
                      "one of them TD-CC-04 in TD-L-03"):
            today = server_today(ctx)
            due_after_apply = expected_schedule("B", today)
            ctx.log(f"server today = {iso(today)}; Level B schedules "
                    f"{iso(due_after_apply)} (the workbook's 2026-08-20 -> "
                    "2026-08-27, asserted as the relationship it expresses "
                    "because v17's _apply_inventory(self) takes no date "
                    "argument — models/stock_quant.py:17)")

            categ = realtime_category_data(ctx)
            product_id = make_product(ctx, "CC03", storable=True,
                                      categ_id=categ["id"],
                                      level_id=levels["B"])
            # Fix the cost BEFORE any stock exists: _get_price_unit falls back
            # to standard_price when the move carries no price
            # (stock_account/models/stock_move.py:59), so every layer — and
            # therefore the valuation entry step 12 measures — is priced here.
            rpc.write("product.product", [product_id], {"standard_price": 7.0})
            loc_variance, loc_confirm = internal_locations(ctx, 2)
            add_stock(ctx, product_id, loc_variance, 20.0)
            add_stock(ctx, product_id, loc_confirm, 12.0)

            quant_variance = quant_of(rpc, product_id, loc_variance)
            quant_confirm = quant_of(rpc, product_id, loc_confirm)
            unit_cost = rpc.read("product.product", [product_id],
                                 ["standard_price"])[0]["standard_price"]
            ctx.check("the fixture product carries Level B (a levelless "
                      "product's apply raises Expected singleton — "
                      "cycle_count_category.py:23)",
                      levels["B"], level_of(rpc, product_id))
            ctx.check_true("both fixture quants exist",
                           bool(quant_variance and quant_confirm),
                           actual_desc=f"variance={quant_variance!r} "
                                       f"confirm={quant_confirm!r}")
            ctx.check_true("the product's cost is non-zero, so step 12 "
                           "cannot pass vacuously", bool(unit_cost),
                           actual_desc=f"standard_price={unit_cost!r}")
            moves_before = valuation_moves_for(rpc, product_id)
            lines_before = [row["id"] for row in
                            move_lines_for(rpc, product_id)]
            ctx.log(f"staged: quants {quant_variance}/{quant_confirm}; "
                    f"{len(lines_before)} pre-existing move line(s); "
                    f"{len(moves_before)} pre-existing valuation entry(ies); "
                    f"cost {unit_cost}")

        with ctx.step("1. Log in as TD-U-03, open Inventory -> Physical "
                      "Inventory and locate the quant of TD-CC-03 in TD-L-03"):
            user_id, login = ensure_wf021_user(ctx, "u03", [GROUP_STOCK_USER])
            count_rpc = rpc_as(ctx.env, login)
            ctx.log(f"counting as {login} (uid {count_rpc.uid}) — "
                    "stock.group_stock_user, which is what "
                    "_is_inventory_mode() requires "
                    "(stock/models/stock_quant.py:1230-1235)")
            listed = count_rpc.search(
                "stock.quant",
                PHYSICAL_INVENTORY_DOMAIN + [("product_id", "=", product_id),
                                             ("location_id", "=",
                                              loc_variance)])
            ctx.check("Physical Inventory lists exactly the one quant of "
                      "TD-CC-03 in TD-L-03", [quant_variance], listed)

        with ctx.step("2. Record on_hand_before = quant.quantity"):
            on_hand_before = quant_state(rpc, [quant_variance])[
                quant_variance]["quantity"]
            ctx.check("on_hand_before", 20.0, on_hand_before)

        with ctx.step("3. Enter a Counted Quantity that differs from "
                      "on_hand_before by a known variance"):
            counted = 17.0
            variance = counted - on_hand_before
            enter_count(count_rpc, quant_variance, counted)
            ctx.log(f"counted {counted} against {on_hand_before} — variance "
                    f"{variance}")

        with ctx.step("4. Assert inventory_diff_quantity equals the expected "
                      "variance"):
            state = quant_state(rpc, [quant_variance])[quant_variance]
            ctx.check("counted quantity and the computed difference",
                      {"inventory_quantity": counted,
                       "inventory_diff_quantity": variance,
                       "inventory_quantity_set": True},
                      {"inventory_quantity": state["inventory_quantity"],
                       "inventory_diff_quantity":
                           state["inventory_diff_quantity"],
                       "inventory_quantity_set":
                           state["inventory_quantity_set"]})

        with ctx.step("5. Log in as TD-U-04 and press Apply"):
            action = apply_count(rpc, [quant_variance])
            # action_apply_inventory returns a stock.inventory.conflict or
            # stock.track.confirmation wizard dict INSTEAD of applying when a
            # quant is outdated or a tracked product has no lot (v17
            # stock/models/stock_quant.py:461-480). A falsy return is the
            # only proof it reached self._apply_inventory() at :483.
            ctx.check_true("Apply applied instead of returning a wizard "
                           "(stock/models/stock_quant.py:461-483)",
                           not action, actual_desc=repr(action))

        with ctx.step("6. Assert quant.quantity == counted_quantity — the "
                      "adjustment applied"):
            applied = quant_state(rpc, [quant_variance])[quant_variance]
            ctx.check("quant.quantity", counted, applied["quantity"])

        with ctx.step("7. Assert a stock.move.line was created for the "
                      "variance"):
            new_lines = move_lines_for(rpc, product_id,
                                       exclude_ids=lines_before)
            ctx.log(f"move lines created by the apply: {new_lines!r}")
            ctx.check("one move line, for the absolute variance, done",
                      {"count": 1, "quantity": abs(variance),
                       "state": "done"},
                      {"count": len(new_lines),
                       "quantity": (new_lines[0]["quantity"]
                                    if new_lines else None),
                       "state": (new_lines[0]["state"]
                                 if new_lines else None)})

        with ctx.step("8. Assert quant.last_count_date == 2026-08-20"):
            after = quant_state(rpc, [quant_variance])[quant_variance]
            product_row = rpc.read("product.product", [product_id],
                                   ["last_count_date",
                                    "scheduled_count_date"])[0]
            stamps = {
                "quant.last_count_date": iso(after["last_count_date"]),
                "quant.inventory_date": iso(after["inventory_date"]),
                "product.last_count_date":
                    iso(product_row["last_count_date"]),
                "product.scheduled_count_date":
                    iso(product_row["scheduled_count_date"]),
            }
            expected_stamps = {
                "quant.last_count_date": iso(today),
                "quant.inventory_date": iso(due_after_apply),
                "product.last_count_date": iso(today),
                "product.scheduled_count_date": iso(due_after_apply),
            }
            # All four writes in ONE mismatch dict: the override makes them
            # separately (models/stock_quant.py:22-29) and a partial port
            # typically drops the product-side pair, so a failure must report
            # every miss at once rather than only the first.
            ctx.check("all four date writes the override makes "
                      "(models/stock_quant.py:22-29)",
                      expected_stamps, stamps)
            ctx.check("quant.last_count_date is the day of the count",
                      iso(today), stamps["quant.last_count_date"])

        with ctx.step("9. Assert quant.inventory_date == 2026-08-27"):
            ctx.check("quant.inventory_date is the next scheduled date "
                      "(Level B = +1 week)", iso(due_after_apply),
                      stamps["quant.inventory_date"])

        with ctx.step("10. Assert product.last_count_date == 2026-08-20"):
            ctx.check("product.last_count_date is the day of the count",
                      iso(today), stamps["product.last_count_date"])

        with ctx.step("11. Assert product.scheduled_count_date == 2026-08-27"):
            ctx.check("product.scheduled_count_date is the next scheduled "
                      "date", iso(due_after_apply),
                      stamps["product.scheduled_count_date"])

        with ctx.step("12. Assert a valuation account.move was posted whose "
                      "value equals the variance at the product's cost"):
            new_moves = valuation_moves_for(rpc, product_id,
                                            exclude_ids=moves_before)
            rows = move_line_rows(rpc, new_moves)
            ctx.log(f"valuation entry(ies) {new_moves}: {rows!r}")
            expected_value = round(abs(variance) * unit_cost, 2)
            ctx.check("one valuation entry, two lines, valued at the "
                      "variance times the product's cost",
                      {"entries": 1, "lines": 2, "debit": expected_value,
                       "credit": expected_value},
                      {"entries": len(new_moves), "lines": len(rows),
                       "debit": round(sum(r["debit"] for r in rows), 2),
                       "credit": round(sum(r["credit"] for r in rows), 2)})

        with ctx.step("13. Set the working date to 2026-08-21, open Physical "
                      "Inventory, and assert the quant is not listed as due"):
            # There is no working date to set over RPC. The count sheet is
            # core's to_count filter, domain [('inventory_date','<=',<date>)]
            # (stock/views/stock_quant_views.xml:37) — common.due_on runs
            # exactly that, scoped to the one quant.
            next_day = today + datetime.timedelta(days=1)
            ctx.check(f"due on {iso(next_day)} (today + 1 day)", False,
                      due_on(rpc, quant_variance, next_day))

        with ctx.step("14. Set the working date to 2026-08-27 and assert the "
                      "quant is listed as due"):
            ctx.check(f"due on {iso(due_after_apply)} (the scheduled date)",
                      True, due_on(rpc, quant_variance, due_after_apply))

        with ctx.step("15. Re-run steps 1-11 on a second quant with the "
                      "counted quantity equal to on-hand; assert no "
                      "stock.move.line is created but last_count_date and "
                      "inventory_date are still written"):
            confirm_before = quant_state(rpc, [quant_confirm])[quant_confirm]
            on_hand_confirm = confirm_before["quantity"]
            lines_before_confirm = [row["id"] for row in
                                    move_lines_for(rpc, product_id)]
            enter_count(count_rpc, quant_confirm, on_hand_confirm)
            zero_state = quant_state(rpc, [quant_confirm])[quant_confirm]
            ctx.check("the confirming count carries no variance", 0.0,
                      zero_state["inventory_diff_quantity"])

            zero_action = apply_count(rpc, [quant_confirm])
            ctx.check_true("Apply applied the confirming count instead of "
                           "returning a wizard", not zero_action,
                           actual_desc=repr(zero_action))

            confirm_lines = move_lines_for(rpc, product_id,
                                           exclude_ids=lines_before_confirm)
            # WORKBOOK CORRECTION (flow A3). v17 has no zero-variance skip:
            # the if/else appends a move_val on BOTH branches
            # (stock/models/stock_quant.py:1056-1066), the zero case is named
            # 'Product Quantity Confirmed' (:1265-1268), and _action_done
            # exempts is_inventory moves from the zero-quantity cancel
            # (stock_move.py:1889, 1896). So a ZERO-quantity line is created.
            # Step 7's own words are "a stock.move.line ... FOR THE
            # VARIANCE"; step 15 is its negation, and that is what is
            # asserted — nothing carrying a variance quantity was booked.
            ctx.log("move lines created by the confirming apply "
                    f"(zero-quantity 'Product Quantity Confirmed' lines are "
                    f"core v17 behaviour, stock/models/stock_quant.py"
                    f":1056-1066): {confirm_lines!r}")
            ctx.check("no stock.move.line carrying a variance quantity was "
                      "created", [],
                      [row for row in confirm_lines if row["quantity"]])
            ctx.check("the confirming apply booked no quantity at all", 0.0,
                      round(sum(row["quantity"] for row in confirm_lines), 6))

            confirm_after = quant_state(rpc, [quant_confirm])[quant_confirm]
            confirm_product = rpc.read("product.product", [product_id],
                                       ["last_count_date",
                                        "scheduled_count_date"])[0]
            ctx.check("confirming a bin is a count: all four dates are "
                      "still written (WF-021 A3)",
                      expected_stamps,
                      {"quant.last_count_date":
                           iso(confirm_after["last_count_date"]),
                       "quant.inventory_date":
                           iso(confirm_after["inventory_date"]),
                       "product.last_count_date":
                           iso(confirm_product["last_count_date"]),
                       "product.scheduled_count_date":
                           iso(confirm_product["scheduled_count_date"])})
            ctx.check("on-hand is unchanged by a confirming count",
                      on_hand_confirm, confirm_after["quantity"])
    finally:
        try:
            if user_id:
                archive_user(rpc, user_id)
        except Exception:                                    # noqa: BLE001
            pass
        safe_sweep(ctx)


# ===========================================================================
# TC175 — one level write, every quant re-scheduled
# ===========================================================================
@test_case(
    id="TEST-WF021-TC175",
    name="Changing a product's level re-schedules every one of its quants "
         "in the same transaction",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module=MODULE, priority="P1", kind="API", order=21175,
    description="Three quants of one product all read the Level E date; one "
                "write to the product's level rewrites every one of them to "
                "the Level A date, the pair is atomic (a failing quant loop "
                "rolls the level change back with it), the quants are due on "
                "the new date, and a user with product-write rights but no "
                "stock.group_stock_manager still triggers the sudo loop.",
    traceability=trace("DATAONE-TC175"))
def test_tc175(ctx):
    rpc = ctx.adapter.rpc
    require_cycle_count(ctx)
    levels = require_shipped_levels(ctx)
    open_namespace(ctx)

    writer_user_id = None
    try:
        with ctx.step("Precondition: TD-CC-03 on Level E with three quants "
                      "in TD-L-03, TD-L-04 and TD-L-05, last counted "
                      f"{FIXED_COUNT_DATE}"):
            due_level_e = expected_schedule("E", FIXED_COUNT_DATE)
            due_level_a = expected_schedule("A", FIXED_COUNT_DATE)
            product_id = make_product(ctx, "CC03", storable=True,
                                      level_id=levels["E"],
                                      last_count_date=FIXED_COUNT_DATE)
            locations = internal_locations(ctx, 3)
            for index, location_id in enumerate(locations, start=1):
                add_stock(ctx, product_id, location_id, 10.0 * index)
            # The set the write loop under test iterates is UNSCOPED —
            # product.product.write walks self.stock_quant_ids.sudo()
            # (models/product_product.py:58) — so quant_ids stays unscoped
            # and steps 2, 6 and 7 keep asserting over every quant.
            #
            # What must NOT be asserted here is "exactly 3". add_stock
            # sources its receipt from the inventory-loss location, and
            # stock.move.line._action_done calls
            # _synchronize_quant(-qty, ml.location_id) for the source side
            # too (O17 stock/models/stock_move_line.py:660, :673-682), which
            # creates a counterpart quant there (O17 stock_quant.py:1076).
            # Three add_stock calls therefore leave FOUR quants, and
            # quants_of's own docstring says to use quant_of() for any
            # "exactly N" assertion. The workbook agrees: its step 3 asks
            # for len(before) >= 3, which this test asserts below.
            quant_ids = quants_of(rpc, product_id)
            ctx.check("one quant per fixture internal location",
                      {loc: True for loc in locations},
                      {loc: quant_of(rpc, product_id, loc) is not None
                       for loc in locations})
            ctx.log(f"{len(quant_ids)} quant(s) in play for the unscoped "
                    f"write loop: {sorted(quant_ids)} — the extra one is the "
                    f"inventory-loss counterpart add_stock leaves behind.")
            for quant_id in quant_ids:
                # Without a last_count_date the loop falls back to TODAY
                # inside _calculate_scheduled_count_date
                # (cycle_count_category.py:24-25) and the fixed-date
                # expectation evaporates.
                stamp_quant(rpc, quant_id, FIXED_COUNT_DATE)
            # Re-writing the SAME level re-runs the whole loop: the gate is
            # 'cycle_count_category_id' in vals — key presence, not value
            # change (models/product_product.py:57). The 2027-02-20 baseline
            # step 2 asserts is therefore computed by the SERVER, not
            # stamped by the fixture.
            set_level(rpc, product_id, levels["E"])
            ctx.log(f"Level E schedules {iso(due_level_e)}; Level A "
                    f"schedules {iso(due_level_a)} from {FIXED_COUNT_DATE}")

        with ctx.step("1. Log in as TD-U-04"):
            groups_field = ctx.adapter.user_groups_field
            row = rpc.read("res.users", [rpc.uid], ["login",
                                                    groups_field])[0]
            manager_id = rpc.ref(GROUP_STOCK_MANAGER)
            ctx.log(f"acting as {row['login']!r} (uid {rpc.uid}); holds "
                    f"{GROUP_STOCK_MANAGER}: "
                    f"{manager_id in (row.get(groups_field) or [])}")
            ctx.check_true("the acting session can write the product under "
                           "test", bool(rpc.search(
                               "product.product", [("id", "=", product_id)])),
                           actual_desc=f"product {product_id}")

        with ctx.step("2. Record before = {q.id: q.inventory_date for q in "
                      "product.stock_quant_ids} and assert every value is "
                      "2027-02-20"):
            before = inventory_dates(rpc, quant_ids)
            ctx.check("every quant is scheduled on the Level E date",
                      {qid: iso(due_level_e) for qid in quant_ids},
                      {qid: iso(value) for qid, value in before.items()})

        with ctx.step("3. Assert len(before) >= 3"):
            ctx.check_true("at least three quants are in play",
                           len(before) >= 3,
                           actual_desc=f"{len(before)} quant(s): "
                                       f"{sorted(before)}")

        with ctx.step("4. Open the product and change Cycle Count Category "
                      "from Level E to Level A"):
            ctx.check("the product starts on Level E", levels["E"],
                      level_of(rpc, product_id))

        with ctx.step("5. Save"):
            set_level(rpc, product_id, levels["A"])
            ctx.check("the product now carries Level A", levels["A"],
                      level_of(rpc, product_id))

        with ctx.step("6. Record after = {q.id: q.inventory_date for q in "
                      "product.stock_quant_ids}"):
            after = inventory_dates(rpc, quants_of(rpc, product_id))
            ctx.log(f"after = {({k: iso(v) for k, v in after.items()})!r}")

        with ctx.step("7. Assert after covers exactly the same quant ids as "
                      "before — none were skipped and none created"):
            ctx.check("the quant id set is unchanged", sorted(before),
                      sorted(after))

        with ctx.step("8. Assert every value in after is 2026-08-21 (last "
                      "count 2026-08-20 + 1 day)"):
            # ONE write call, every quant — asserted as a full map so a
            # skipped quant names itself instead of hiding behind a count.
            ctx.check("every quant was rewritten to the Level A date",
                      {qid: iso(due_level_a) for qid in sorted(before)},
                      {qid: iso(after[qid]) for qid in sorted(after)})

        with ctx.step("9. Assert the rewrite happened in the same "
                      "transaction as the product write: roll back and "
                      "assert both the level and all quant dates revert "
                      "together"):
            # An RPC client cannot roll a transaction back — each call
            # commits its own (AUTOMATION_CONVENTIONS:80-82). The server's
            # own rollback is used instead: clearing the level lets
            # super().write() store it, then the sudo loop reads the quant's
            # now-empty related level and _calculate_scheduled_count_date's
            # ensure_one() raises (cycle_count_category.py:23). If the two
            # halves were not in one transaction, the level would be found
            # cleared while the dates stayed — which is exactly the failure
            # this step exists to exclude.
            raised, message = expect_error(set_level, rpc, product_id, False)
            ctx.log(f"clearing the level: raised={raised} {message!r}")
            ctx.check_true("the write was refused by the quant loop", raised,
                           actual_desc=message or "<no error>")
            ctx.check_true("refused by ensure_one() on the quant's empty "
                           "level (cycle_count_category.py:23)",
                           SINGLETON_ERROR_FRAGMENT in message,
                           actual_desc=message or "<no error>")
            ctx.check("the level and every quant date reverted together",
                      {"level": levels["A"],
                       "dates": {qid: iso(due_level_a)
                                 for qid in sorted(before)}},
                      {"level": level_of(rpc, product_id),
                       "dates": {qid: iso(value) for qid, value in
                                 sorted(inventory_dates(
                                     rpc, quants_of(rpc, product_id)).items())}})

        with ctx.step("10. Re-apply the change, open Physical Inventory with "
                      "the working date set to 2026-08-21, and assert all "
                      "three quants are listed as due"):
            set_level(rpc, product_id, levels["A"])
            listed = rpc.search(
                "stock.quant",
                PHYSICAL_INVENTORY_DOMAIN + [("id", "in", quant_ids)])
            ctx.check("Physical Inventory lists all three quants",
                      sorted(quant_ids), sorted(listed))
            ctx.check("every quant is due on the Level A date",
                      {qid: True for qid in sorted(quant_ids)},
                      {qid: due_on(rpc, qid, due_level_a)
                       for qid in sorted(quant_ids)})

        with ctx.step("11. Assert the loop ran with sudo(): repeat the whole "
                      "case as a user with product-write rights but without "
                      "stock.group_stock_manager, and assert the quant dates "
                      "are still rewritten"):
            writer_group = non_manager_product_writer(rpc)
            if not writer_group:
                ctx.blocked(
                    f"No ir.model.access row on {ctx.env.key} "
                    f"(db={ctx.env.db}) grants product.product write to a "
                    f"resolvable group other than {GROUP_STOCK_MANAGER}. On "
                    "v17 stock.group_stock_manager itself holds 1,1,1,1 "
                    "(stock/security/ir.model.access.csv:22) and v19 deletes "
                    "that row, so which group can write a product is a "
                    "runtime fact. Without one, the privilege surface this "
                    "step documents — that the sudo()-ed loop at "
                    "models/product_product.py:58 lets product-write rights "
                    "alone rewrite quant scheduling — cannot be exercised.")
            writer_user_id, writer_login = ensure_wf021_user(
                ctx, "prodwriter", [writer_group])
            groups_field = ctx.adapter.user_groups_field
            writer_groups = rpc.read("res.users", [writer_user_id],
                                     [groups_field])[0][groups_field] or []
            manager_id = rpc.ref(GROUP_STOCK_MANAGER)
            if manager_id in writer_groups:
                ctx.blocked(
                    f"The only product.product-write group available on "
                    f"{ctx.env.key} ({writer_group}) resolves to a user who "
                    f"also holds {GROUP_STOCK_MANAGER} through implied_ids, "
                    "so 'without stock.group_stock_manager' cannot be "
                    "arranged and the sudo() claim cannot be isolated.")
            writer_rpc = rpc_as(ctx.env, writer_login)
            ctx.log(f"writing the level as {writer_login} (uid "
                    f"{writer_rpc.uid}), group {writer_group}, NOT a stock "
                    "manager")
            set_level(writer_rpc, product_id, levels["E"])
            ctx.check("a product writer with no stock-manager rights "
                      "re-scheduled every quant",
                      {qid: iso(due_level_e) for qid in sorted(quant_ids)},
                      {qid: iso(value) for qid, value in
                       sorted(inventory_dates(rpc, quant_ids).items())})
    finally:
        try:
            if writer_user_id:
                archive_user(rpc, writer_user_id)
        except Exception:                                    # noqa: BLE001
            pass
        safe_sweep(ctx)


# ===========================================================================
# TC176 — the columns, search fields and group-bys
# ===========================================================================
@test_case(
    id="TEST-WF021-TC176",
    name="Cycle-count columns, search fields and group-bys are available on "
         "products and on Physical Inventory",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module=MODULE, priority="P2", kind="HYBRID", order=21176,
    description="The Cycle Count group sits after the traceability group "
                "with its three fields and a read-only scheduled date, the "
                "template group is guarded by product_variant_count > 1, and "
                "the search fields, group-by filters, the quant column's "
                "optional=\"show\" and the actual read_group bucketing are "
                "asserted on both screens.",
    traceability=trace("DATAONE-TC176"))
def test_tc176(ctx):
    rpc = ctx.adapter.rpc
    require_cycle_count(ctx)
    levels = require_shipped_levels(ctx)
    open_namespace(ctx)

    attribute_id = None
    value_ids = []
    try:
        with ctx.step("Precondition: three products on three different "
                      "levels, each with a quant"):
            categ_id = make_category(rpc, "CCVIEW")
            products = {}
            for key in ("A", "B", "C"):
                products[key] = make_product(ctx, f"LVLP-{key}",
                                             storable=True,
                                             categ_id=categ_id,
                                             level_id=levels[key])
            locations = internal_locations(ctx, 3)
            quant_ids = []
            for (_key, product_id), location_id in zip(
                    sorted(products.items()), locations):
                add_stock(ctx, product_id, location_id, 5.0)
                quant_ids.append(quant_of(rpc, product_id, location_id))
            ctx.check("three quants, one per level", 3,
                      len([q for q in quant_ids if q]))
            template_ids = {key: product_tmpl_of(rpc, pid)
                            for key, pid in products.items()}
            ctx.log(f"products={products!r} templates={template_ids!r} "
                    f"quants={quant_ids!r}")

        with ctx.step("1. Log in as TD-U-04 and open a storable product form"):
            _require_traceability_anchor(ctx)
            product_form = arch_of(ctx, "product.product", VIEW_PRODUCT_FORM,
                                   "form")
            ctx.check_true("the composed product.product form was returned",
                           parse_arch(product_form).tag == "form",
                           actual_desc=parse_arch(product_form).tag)

        with ctx.step("2. Assert a Cycle Count group appears after the "
                      "traceability group, containing Level, Last Count Date "
                      "and a read-only Scheduled Count Date"):
            group = group_attrs(product_form, CYCLE_COUNT_GROUP)
            scheduled = field_attrs(product_form, "scheduled_count_date",
                                    within_group=CYCLE_COUNT_GROUP) or {}
            in_group = [name for name in
                        _group_field_names(product_form, CYCLE_COUNT_GROUP)
                        if name in CYCLE_COUNT_FIELDS]
            ctx.check("the Cycle Count group, its position and its three "
                      "fields (views/product_product_views.xml:10-13)",
                      {"group_present": True, "string": "Cycle Count",
                       "after_traceability": True,
                       "fields": list(CYCLE_COUNT_FIELDS),
                       "scheduled_readonly": "1"},
                      {"group_present": group is not None,
                       "string": (group or {}).get("string"),
                       "after_traceability": follows(
                           product_form, "group", TRACEABILITY_GROUP,
                           CYCLE_COUNT_GROUP),
                       "fields": in_group,
                       "scheduled_readonly": scheduled.get("readonly")})

        with ctx.step("3. Open a product.template with more than one variant "
                      "and assert the Cycle Count group is hidden"):
            attribute_id = rpc.create("product.attribute",
                                      {"name": tag("ATTR"),
                                       "create_variant": "always"})
            value_ids = [rpc.create("product.attribute.value",
                                    {"name": tag(f"VAL{index}"),
                                     "attribute_id": attribute_id})
                         for index in (1, 2)]
            multi_tmpl_id = make_template(
                ctx, "MULTIVAR", storable=True, categ_id=categ_id,
                extra={"attribute_line_ids": [
                    (0, 0, {"attribute_id": attribute_id,
                            "value_ids": [(6, 0, value_ids)]})]})
            variant_count = rpc.read("product.template", [multi_tmpl_id],
                                     ["product_variant_count"])[0][
                                         "product_variant_count"]
            template_form = arch_of(ctx, "product.template",
                                    VIEW_TEMPLATE_FORM, "form")
            template_group = group_attrs(template_form, CYCLE_COUNT_GROUP) or {}
            invisible = template_group.get("invisible") or ""
            # The guard is client-side, so the server-observable content is
            # the modifier plus the record value it reads: the group carries
            # the product_variant_count > 1 disjunct verbatim in BOTH
            # versions (v17 views/product_template_views.xml:10, v19 :15),
            # and this template really does have two variants.
            ctx.check("the template group is guarded by "
                      "product_variant_count > 1, and the fixture template "
                      "has two variants",
                      {"guard": TEMPLATE_GROUP_EXTRA_INVISIBLE,
                       "variants": 2, "hidden": True},
                      {"guard": (TEMPLATE_GROUP_EXTRA_INVISIBLE
                                 if TEMPLATE_GROUP_EXTRA_INVISIBLE in invisible
                                 else invisible),
                       "variants": variant_count,
                       "hidden": (TEMPLATE_GROUP_EXTRA_INVISIBLE in invisible
                                  and variant_count > 1)})

        with ctx.step("4. Open Inventory -> Products in list view"):
            product_list = arch_of(ctx, "product.product", view_type="list")
            product_search = arch_of(ctx, "product.product",
                                     VIEW_PRODUCT_SEARCH, "search")
            ctx.check("the product list view was returned under this "
                      "version's own root tag", list_root_tag(ctx),
                      parse_arch(product_list).tag)

        with ctx.step("5. Assert a Cycle Count Category column is available "
                      "and can be grouped by"):
            # dto_cycle_count inherits no product LIST view — its nine views
            # are the two product forms, the two product searches, the quant
            # inventory list, the quant search and the three level views. On
            # the product side the module provides the field and the
            # group-by, which is what availability resolves to server-side.
            declared = rpc.call("product.product", "fields_get",
                                ["cycle_count_category_id"],
                                attributes=["type", "store", "relation"])
            groupby = filter_attrs(product_search,
                                   PRODUCT_GROUPBY_FILTER) or {}
            # fields=[] deliberately: ``__count`` is added unconditionally
            # when lazy=False (v17 odoo/models.py:2730, v19
            # odoo/orm/models.py:2749ff), and asking for an aggregate over an
            # _inherits-delegated column (list_price lives on
            # product_template) would need a join read_group does not make.
            buckets = rpc.read_group(
                "product.product",
                [("id", "in", sorted(products.values()))],
                [], ["cycle_count_category_id"], lazy=False)
            observed = {m2o_id(row.get("cycle_count_category_id")):
                        row.get("__count")
                        for row in buckets}
            ctx.log(f"product buckets: {buckets!r}")
            ctx.check("the field is a stored many2one, the search view "
                      "declares the group-by, and read_group buckets the "
                      "three products one per level",
                      {"type": "many2one", "store": True,
                       "relation": "cycle.count.category",
                       "groupby_context":
                           "{'group_by': 'cycle_count_category_id'}",
                       "buckets": {levels["A"]: 1, levels["B"]: 1,
                                   levels["C"]: 1}},
                      {"type": declared["cycle_count_category_id"]["type"],
                       "store": declared["cycle_count_category_id"]["store"],
                       "relation":
                           declared["cycle_count_category_id"]["relation"],
                       "groupby_context": groupby.get("context"),
                       "buckets": observed})

        with ctx.step("6. Type a level name into the search box and assert "
                      "the filter_domain ilike match returns the expected "
                      "products"):
            search_field = field_attrs(product_search,
                                       "cycle_count_category_id") or {}
            ctx.check("the declared filter_domain, verbatim "
                      "(views/product_product_views.xml:25 — defect "
                      "D-new-6: it searches the PRODUCT's own name)",
                      PRODUCT_SEARCH_FILTER_DOMAIN,
                      search_field.get("filter_domain"))
            # Execute the domain the view actually declares, scoped to this
            # execution's token so live data cannot leak in.
            typed = f"{fixture_token()} LVLP-"
            matched = rpc.search("product.product",
                                 [("name", "ilike", typed)], order="id")
            level_name_hits = rpc.search(
                "product.product",
                [("name", "ilike", "Level B"),
                 ("default_code", "like", fixture_token())])
            ctx.check("the declared domain returns the expected products, "
                      "and a level name typed into it matches none of them "
                      "because the domain searches the product's own name",
                      {"by_product_name": sorted(products.values()),
                       "by_level_name": []},
                      {"by_product_name": sorted(matched),
                       "by_level_name": sorted(level_name_hits)})

        with ctx.step("7. Open Inventory -> Physical Inventory"):
            quant_list = arch_of(ctx, "stock.quant",
                                 VIEW_QUANT_INVENTORY_LIST, "list")
            quant_search = arch_of(ctx, "stock.quant", VIEW_QUANT_SEARCH,
                                   "search")
            ctx.check("the inventory-adjustment list view was returned under "
                      "this version's own root tag", list_root_tag(ctx),
                      parse_arch(quant_list).tag)

        with ctx.step("8. Assert a Cycle Count Category column is present as "
                      "optional=\"show\""):
            column = field_attrs(quant_list, "cycle_count_category_id") or {}
            ctx.check("the quant column and its optional attribute "
                      "(views/stock_quant_views.xml:10)",
                      {"present": True, "optional": "show"},
                      {"present": bool(column),
                       "optional": column.get("optional")})

        with ctx.step("9. Assert a Cycle Count Category search field is "
                      "available"):
            quant_field = field_attrs(quant_search,
                                      "cycle_count_category_id") or {}
            ctx.check("the quant search field and its filter_domain "
                      "(views/stock_quant_views.xml:21)",
                      CATEGORY_SEARCH_FILTER_DOMAIN,
                      quant_field.get("filter_domain"))
            # Run the declared domain, scoped to this execution's quants.
            level_b_quant = quant_of(rpc, products["B"], locations[1])
            matched_quants = rpc.search(
                "stock.quant", [("id", "in", quant_ids),
                                ("cycle_count_category_id", "ilike",
                                 "Level B")])
            ctx.check("typing a level name into the quant search field "
                      "selects that level's quants", [level_b_quant],
                      matched_quants)

        with ctx.step("10. Assert a Cycle Count Category group-by is "
                      "available, positioned after the existing Product "
                      "group-by"):
            quant_groupby = filter_attrs(quant_search,
                                         QUANT_GROUPBY_FILTER) or {}
            ctx.check("the quant group-by filter and its position after "
                      "filter[@name='productgroup'] "
                      "(views/stock_quant_views.xml:23-24)",
                      {"context": "{'group_by': 'cycle_count_category_id'}",
                       "after_productgroup": True},
                      {"context": quant_groupby.get("context"),
                       "after_productgroup": follows(
                           quant_search, "filter", "productgroup",
                           QUANT_GROUPBY_FILTER)})

        with ctx.step("11. Group by it and assert the quants are bucketed by "
                      "level with correct counts"):
            groups = rpc.read_group(
                "stock.quant", [("id", "in", quant_ids)], [],
                ["cycle_count_category_id"], lazy=False)
            ctx.log(f"quant buckets: {groups!r}")
            ctx.check("one quant per level",
                      {levels["A"]: 1, levels["B"]: 1, levels["C"]: 1},
                      {m2o_id(row.get("cycle_count_category_id")):
                       row.get("__count") for row in groups})

        with ctx.step("12. Assert grouping on the template list works "
                      "through the stored variant_cycle_count_category_id"):
            declared = rpc.call("product.template", "fields_get",
                                [TEMPLATE_VARIANT_LEVEL_FIELD],
                                attributes=["type", "store"])
            template_search = arch_of(ctx, "product.template",
                                      VIEW_TEMPLATE_SEARCH, "search")
            template_groupby = filter_attrs(template_search,
                                            TEMPLATE_GROUPBY_FILTER) or {}
            groups = rpc.read_group(
                "product.template",
                [("id", "in", sorted(template_ids.values()))],
                [], [TEMPLATE_VARIANT_LEVEL_FIELD], lazy=False)
            ctx.log(f"template buckets: {groups!r}")
            ctx.check("the stored mirror, the template group-by filter and "
                      "the actual bucketing "
                      "(models/product_template.py:15-16, "
                      "views/product_template_views.xml:28)",
                      {"type": "many2one", "store": True,
                       "groupby_context":
                           "{'group_by': 'variant_cycle_count_category_id'}",
                       "buckets": {levels["A"]: 1, levels["B"]: 1,
                                   levels["C"]: 1}},
                      {"type": declared[TEMPLATE_VARIANT_LEVEL_FIELD]["type"],
                       "store":
                           declared[TEMPLATE_VARIANT_LEVEL_FIELD]["store"],
                       "groupby_context": template_groupby.get("context"),
                       "buckets": {
                           m2o_id(row.get(TEMPLATE_VARIANT_LEVEL_FIELD)):
                           row.get("__count") for row in groups}})
    finally:
        safe_sweep(ctx)
        # product.attribute / product.attribute.value are outside
        # sweep_wf021's remit (it owns products, categories, locations,
        # pickings and analytic accounts), so the multi-variant fixture
        # cleans up after itself. Children before parents; never raises.
        for model, ids in (("product.attribute.value", value_ids),
                           ("product.attribute",
                            [attribute_id] if attribute_id else [])):
            try:
                if ids:
                    rpc.call(model, "unlink", ids)
            except Exception as exc:                         # noqa: BLE001
                try:
                    ctx.log(f"[warn] {model} {ids} not removed: {exc}")
                except Exception:                            # noqa: BLE001
                    pass


# ===========================================================================
# TC177 — the v19 detector
# ===========================================================================
@test_case(
    id="TEST-WF021-TC177",
    name="v19 detector: the required-level rule must still be enforced "
         "after type == 'product' stops matching",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module=MODULE, priority="P0", kind="API", order=21177,
    description="The four XML modifier sites are read from the rendered arch "
                "and compared to the expression that is correct for the "
                "target version, the storable predicate is proven not to be "
                "a constant, both _onchange_type branches are exercised "
                "through the public onchange, and the production impact — "
                "storable products with no level — is measured against the "
                "v17 baseline.",
    traceability=trace("DATAONE-TC177"))
def test_tc177(ctx):
    rpc = ctx.adapter.rpc
    require_cycle_count(ctx)
    levels = require_shipped_levels(ctx)
    open_namespace(ctx)

    # This is the ONE sanctioned ctx.env.version read in the suite
    # (AUTOMATION_CONVENTIONS:143-149): the case's SUBJECT is the delta, so
    # it computes its own expected value per version. Nothing about HOW the
    # test runs branches — only what it expects.
    version = ctx.env.version
    modifiers = STORABLE_MODIFIERS[version]

    try:
        with ctx.step("Precondition: the target's product-type shape, probed "
                      "rather than assumed"):
            type_field = rpc.call("product.template", "fields_get", ["type"],
                                  attributes=["selection"])["type"]
            selection_keys = [key for key, _label in
                              (type_field.get("selection") or [])]
            probe = is_v19_product_shape(rpc)
            ctx.log(f"product.template.type selection = {selection_keys}; "
                    f"product.template.is_storable exists = {probe}")
            ctx.check("the selection and the is_storable probe agree with "
                      "the environment's declared version "
                      "(v17 stock/models/product.py:661-663 adds 'product'; "
                      "v19 product/models/product_template.py:54-65 does "
                      "not, and stock/models/product.py:829-831 supplies "
                      "is_storable instead)",
                      {"product_in_selection": version == "17",
                       "is_storable_exists": version == "19"},
                      {"product_in_selection": "product" in selection_keys,
                       "is_storable_exists": probe})

        with ctx.step("1. Log in as TD-U-04 on the target environment"):
            groups_field = ctx.adapter.user_groups_field
            row = rpc.read("res.users", [rpc.uid], ["login",
                                                    groups_field])[0]
            manager_id = rpc.ref(GROUP_STOCK_MANAGER)
            ctx.log(f"acting as {row['login']!r} (uid {rpc.uid}); holds "
                    f"{GROUP_STOCK_MANAGER}: "
                    f"{manager_id in (row.get(groups_field) or [])}")
            ctx.check_true("the acting session can create products",
                           bool(rpc.search("product.category", [], limit=1)),
                           actual_desc=f"uid {rpc.uid}")

        with ctx.step("2. Grep the loaded views for the literal type == "
                      "'product' and type != 'product' and record every "
                      "occurrence with its file and line"):
            # RECORDED, NEVER ASSERTED. DTO-Odoo is checked out on branch
            # UAT, which already carries the v19 port, so a grep answers a
            # question about the CHECKOUT, not about the running server. The
            # authority for what the target serves is the rendered arch,
            # which step 3 asserts against.
            equal = scan_cycle_count(ctx, r"type\s*==\s*'product'")
            differ = scan_cycle_count(ctx, r"type\s*!=\s*'product'")
            ctx.log(f"source scan branch={equal.get('branch')!r} "
                    f"root={equal.get('root')!r} "
                    f"available={equal.get('available')}")
            for label, scan in (("type == 'product'", equal),
                                ("type != 'product'", differ)):
                for hit in scan.get("hits") or []:
                    ctx.log(f"  {label}: {hit['file']}:{hit['line']} — "
                            f"{hit['text']}")
            ctx.log("the eight documented v17 sites (F085): " +
                    "; ".join(f"{path}:{line} ({what})"
                              for path, line, what in MODIFIER_SITES))

        with ctx.step("3. Assert the count matches the four XML places "
                      "documented in F085, or record the ported "
                      "replacements"):
            product_form = arch_of(ctx, "product.product", VIEW_PRODUCT_FORM,
                                   "form")
            template_form = arch_of(ctx, "product.template",
                                    VIEW_TEMPLATE_FORM, "form")
            product_group = group_attrs(product_form, CYCLE_COUNT_GROUP) or {}
            template_group = group_attrs(template_form,
                                         CYCLE_COUNT_GROUP) or {}
            product_field = field_attrs(product_form,
                                        "cycle_count_category_id",
                                        within_group=CYCLE_COUNT_GROUP) or {}
            template_field = field_attrs(template_form,
                                         "cycle_count_category_id",
                                         within_group=CYCLE_COUNT_GROUP) or {}
            observed_sites = {
                "product.product form / group invisible":
                    product_group.get("invisible"),
                "product.product form / cycle_count_category_id required":
                    product_field.get("required"),
                "product.template form / group invisible":
                    template_group.get("invisible"),
                "product.template form / cycle_count_category_id required":
                    template_field.get("required"),
            }
            expected_sites = {
                "product.product form / group invisible":
                    modifiers["group_invisible"],
                "product.product form / cycle_count_category_id required":
                    modifiers["field_required"],
                "product.template form / group invisible":
                    f"{modifiers['group_invisible']} or "
                    f"{TEMPLATE_GROUP_EXTRA_INVISIBLE}",
                "product.template form / cycle_count_category_id required":
                    modifiers["field_required"],
            }
            ctx.log(f"rendered modifier sites: {observed_sites!r}")
            ctx.check(f"the four XML modifier sites carry the expression "
                      f"that is correct for Odoo {version}",
                      expected_sites, observed_sites)

        with ctx.step("4. Create a new product; set the type to storable "
                      "(consu + is_storable in v19) and the category to "
                      "TD-PC-02"):
            components_id = make_category(rpc, "COMPONENTS")
            categ_name = rpc.read("product.category", [components_id],
                                  ["name"])[0]["name"]
            ctx.check_true("the fixture category is not 'Finished Goods', so "
                           "F082 cannot mask the result "
                           "(models/product_product.py:69)",
                           categ_name != "Finished Goods",
                           actual_desc=repr(categ_name))
            storable_id = make_product(ctx, "T177-STORABLE", storable=True,
                                       categ_id=components_id)
            storable_row = rpc.read(
                "product.product", [storable_id],
                sorted(storable_values(ctx)) + ["cycle_count_category_id"])[0]
            ctx.check("the product was created with this version's storable "
                      "shape and no level",
                      dict(storable_values(ctx), cycle_count_category_id=False),
                      {**{name: storable_row[name]
                          for name in storable_values(ctx)},
                       "cycle_count_category_id":
                           m2o_id(storable_row["cycle_count_category_id"])
                           or False})

        with ctx.step("5. Leave Cycle Count Category empty and attempt to "
                      "save"):
            # The ORM has no required=True and no @api.constrains on the
            # field (models/product_product.py:13), so the create at step 4
            # already succeeded — that leak is TC172's subject and is
            # RECORDED here, not re-asserted. What refuses the save is the
            # view modifier, evaluated by the web client, so the
            # server-observable content of the refusal is the predicate and
            # the record values it reads.
            ctx.log("the ORM accepted a storable product with no level "
                    f"(id {storable_id}); the refusal is the view modifier "
                    f"required=\"{modifiers['field_required']}\" evaluated "
                    "by the web client — there is no required=True and no "
                    "@api.constrains anywhere in dto_cycle_count's Python")
            required_expression = (
                field_attrs(product_form, "cycle_count_category_id",
                            within_group=CYCLE_COUNT_GROUP) or {}
            ).get("required")
            ctx.check("the form still declares the required modifier",
                      modifiers["field_required"], required_expression)

        with ctx.step("6. Assert the save is refused. If it succeeds, this "
                      "case FAILS and the required-level rule has silently "
                      "stopped being enforced"):
            service_id = make_product(ctx, "T177-SERVICE", storable=False,
                                      categ_id=components_id)
            fields_to_read = sorted(set(storable_values(ctx)) |
                                    set(service_values(ctx)))
            storable_values_read = rpc.read("product.product", [storable_id],
                                            fields_to_read)[0]
            service_values_read = rpc.read("product.product", [service_id],
                                           fields_to_read)[0]
            # The predicate is not a constant: TRUE for the storable
            # product, FALSE for the service one. Going constant-false is
            # precisely the silent v19 regression this case exists to catch.
            ctx.check("required=\"" + modifiers["field_required"] +
                      "\" evaluates TRUE for the storable product and FALSE "
                      "for a service product — i.e. the level really is "
                      "demanded and the predicate has not gone constant",
                      {"storable": True, "service": False},
                      {"storable": _view_says_storable(ctx,
                                                       storable_values_read),
                       "service": _view_says_storable(ctx,
                                                      service_values_read)})

        with ctx.step("7. Assert the Cycle Count group is visible on this "
                      "storable product"):
            group_invisible = (group_attrs(product_form,
                                           CYCLE_COUNT_GROUP) or {}).get(
                                               "invisible")
            ctx.check("the group's invisible modifier and its value for a "
                      "storable product",
                      {"expression": modifiers["group_invisible"],
                       "hidden": False},
                      {"expression": group_invisible,
                       "hidden": not _view_says_storable(
                           ctx, storable_values_read)})

        with ctx.step("8. Create a service product and assert the Cycle "
                      "Count group is hidden. If it is visible, the "
                      "invisible modifier has also silently inverted"):
            ctx.check("the same modifier hides the group for a service "
                      "product",
                      {"expression": modifiers["group_invisible"],
                       "hidden": True},
                      {"expression": group_invisible,
                       "hidden": not _view_says_storable(
                           ctx, service_values_read)})

        with ctx.step("9. On a storable product with a level and dates set, "
                      "change the type to service and assert all three "
                      "cycle-count fields are cleared — the _onchange_type "
                      "body fired"):
            scheduled = expected_schedule("B", FIXED_COUNT_DATE)
            levelled_id = make_product(
                ctx, "T177-LEVELLED", storable=True, categ_id=components_id,
                level_id=levels["B"], last_count_date=FIXED_COUNT_DATE,
                scheduled_count_date=iso(scheduled))
            saved = rpc.read("product.product", [levelled_id],
                             list(CYCLE_COUNT_FIELDS))[0]
            ctx.check("the fixture was saved with a level and both dates",
                      {"cycle_count_category_id": levels["B"],
                       "last_count_date": FIXED_COUNT_DATE,
                       "scheduled_count_date": iso(scheduled)},
                      {"cycle_count_category_id":
                           m2o_id(saved["cycle_count_category_id"]),
                       "last_count_date": iso(saved["last_count_date"]),
                       "scheduled_count_date":
                           iso(saved["scheduled_count_date"])})

            form_state = {
                "cycle_count_category_id": levels["B"],
                "last_count_date": FIXED_COUNT_DATE,
                "scheduled_count_date": iso(scheduled),
            }
            form_state.update(service_values(ctx))
            clear_result = _onchange(
                rpc, "product.product", [levelled_id], form_state,
                sorted(service_values(ctx)),
                spec_fields=sorted(set(storable_values(ctx)) |
                                   set(service_values(ctx))))
            ctx.log(f"onchange(type -> service) = {clear_result!r}")
            ctx.check("_onchange_type cleared all three fields "
                      "(models/product_product.py:34-39)",
                      {"cycle_count_category_id": False,
                       "last_count_date": False,
                       "scheduled_count_date": False},
                      _reported(clear_result))

        with ctx.step("10. Change it back and assert the three fields are "
                      "restored from _origin"):
            restored_state = {
                "cycle_count_category_id": False,
                "last_count_date": False,
                "scheduled_count_date": False,
            }
            restored_state.update(storable_values(ctx))
            restore_result = _onchange(
                rpc, "product.product", [levelled_id], restored_state,
                sorted(storable_values(ctx)),
                spec_fields=sorted(set(storable_values(ctx)) |
                                   set(service_values(ctx))))
            ctx.log(f"onchange(type -> storable) = {restore_result!r}")
            ctx.check("_onchange_type restored all three fields from "
                      "self._origin (models/product_product.py:41-46)",
                      {"cycle_count_category_id": levels["B"],
                       "last_count_date": FIXED_COUNT_DATE,
                       "scheduled_count_date": iso(scheduled)},
                      _reported(restore_result))

        with ctx.step("11. Assert _onchange_type calls "
                      "super()._onchange_type() successfully — i.e. the "
                      "parent method still exists under that name"):
            # The super() chain is product.product._onchange_type
            # (sale/models/product_product.py:46 on v17, :45 on v19). A
            # missing parent surfaces as an AttributeError through the RPC
            # fault, so a clean return from both calls IS the proof — and
            # both calls above already reported a value, which a raising
            # onchange never does.
            raised, message = expect_error(
                _onchange, rpc, "product.product", [levelled_id],
                dict(storable_values(ctx)), sorted(storable_values(ctx)))
            ctx.check_true("onchange on 'type' dispatched without an error "
                           "from the super() chain", not raised,
                           actual_desc=message or "<no error>")
            ctx.check("both _onchange_type branches returned a result "
                      "structure rather than raising",
                      {"clear": True, "restore": True},
                      {"clear": isinstance(clear_result, dict),
                       "restore": isinstance(restore_result, dict)})

        with ctx.step("12. Query the database for storable products with "
                      "cycle_count_category_id IS NULL and assert the count "
                      "is zero (or equal to the known v17 baseline count of "
                      "pre-existing levelless products)"):
            # expected_final_state: "Test products deleted". Removing them
            # BEFORE the measurement keeps this execution's deliberately
            # levelless fixture out of the production-impact number; what
            # cannot be unlinked is subtracted instead.
            for model_ids in ([storable_id], [service_id], [levelled_id]):
                try:
                    rpc.call("product.product", "unlink", model_ids)
                except OdooRPCError as exc:
                    ctx.log(f"[warn] product {model_ids} not unlinked: {exc}")
            own_levelless = rpc.call(
                "product.product", "search_count",
                _storable_domain(ctx) + [("cycle_count_category_id", "=",
                                          False),
                                         ("default_code", "like",
                                          fixture_token()),
                                         ("active", "in", [True, False])])
            total = ctx.sql.one(SQL_STORABLE_TOTAL[version])
            measured = ctx.sql.one(SQL_STORABLE_WITHOUT_LEVEL[version])
            levelless = measured - own_levelless
            ctx.log(f"storable products: {total}; without a cycle-count "
                    f"level: {measured} (of which {own_levelless} belong to "
                    f"this execution) -> pre-existing {levelless}")

            baseline = load_baseline("DATAONE-TC177")
            if baseline is None:
                path = save_baseline("DATAONE-TC177", ctx.env.key, ctx.env.db,
                                     {"storable_without_level": levelless,
                                      "storable_total": total})
                ctx.add_artifact(path, "log",
                                 "DATAONE-TC177 levelless-product baseline")
                ctx.log(f"no baseline existed — {levelless} recorded as the "
                        f"v17 baseline count at {path}")
                ctx.check_true("the production-impact measure was captured "
                               "as the baseline for the next run",
                               isinstance(levelless, int),
                               actual_desc=f"{levelless} of {total} storable "
                                           "products carry no level")
            else:
                recorded = baseline["data"]["storable_without_level"]
                ctx.add_artifact(baseline_path("DATAONE-TC177"), "log",
                                 "DATAONE-TC177 levelless-product baseline")
                ctx.log(f"baseline captured on {baseline['captured_env']} "
                        f"(db={baseline['captured_db']}) at "
                        f"{baseline['captured_at']}: {recorded}")
                ctx.check_true(
                    "storable products with no cycle-count level is zero, or "
                    "equal to the recorded v17 baseline — any increase is "
                    "the silent defect expressed as unscheduled products",
                    levelless == 0 or levelless == recorded,
                    actual_desc=f"current={levelless} baseline={recorded} "
                                f"of {total} storable products")
    finally:
        safe_sweep(ctx)
