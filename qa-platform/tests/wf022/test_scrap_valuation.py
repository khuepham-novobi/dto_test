"""DATAONE-WF-022 — the scrap's money half: TC182 (Amount) and TC167 (the
Journal Entries stat button).

Two cases about the same record from opposite ends. ``amount`` is the
scrap's own **estimate**, computed from the product's ``standard_price``;
``account_move_ids`` is what the ledger actually **posted**, at the costing
method's cost. WF-022 states — and TC167 step 8 asserts — that on a FIFO
product those are deliberately different numbers, so ``amount`` must never
be presented to the business as the write-off value.

Abbreviations: ``DTO`` = ``D:/Projects/dataone/DTO-Odoo``, ``O17`` =
``D:/Projects/dataone/odoo-17.0``, ``O19`` = ``D:/Projects/odoo-19.0``.

TC182 — ``amount`` = converted quantity × ``standard_price``
------------------------------------------------------------
The rule, verbatim (``DTO/project-addons/dto_tier_validation_scrap/models/
stock_scrap.py:68-72``; identical at ``dto_scrap/models/stock_scrap.py:91-100``)::

    @api.depends('scrap_qty', 'product_id', 'product_id.standard_price')
    def _compute_amount(self):
        for res in self:
            scrap_uom_qty = res.product_uom_id._compute_quantity(
                res.scrap_qty, res.product_id.uom_id)
            res.amount = scrap_uom_qty * res.product_id.standard_price

and the declaration it fills (``:24-25`` / ``:43-44``)::

    amount = fields.Monetary(
        string='Amount', compute='_compute_amount', store=True,
        help='Estimated Amount', currency_field='company_currency_id')

Three facts shape how the case is written:

1. **``uom.uom._compute_quantity`` is private** (``O17 uom/models/uom_uom.py:211``
   / ``O19 :147``) — Odoo refuses to dispatch it over
   ``/web/dataset/call_kw`` — **and its arithmetic is inverted between the
   versions**: v17 is ``qty / self.factor * to_unit.factor``
   (``O17 :234-236``), v19 is ``qty * self.factor / to_unit.factor``
   (``O19 :169-171``), because ``factor`` means the opposite thing on each
   (``O17 uom_uom.py:59`` "Ratio", ``O19 :43`` "Absolute Quantity"). A test
   that read ``factor`` and multiplied would be silently wrong on one of
   them. What is true under both is that **one Dozen is twelve Units**, so
   workbook step 8's ``_compute_quantity(1, ref_uom)`` is implemented as
   :data:`~tests.wf022.common.DOZEN_IN_REFERENCE_UNITS` and cross-checked
   against the target's own declared ratio — ``factor_inv`` on v17
   (``O17 uom_uom.py:62``, data ``uom/data/uom_data.xml:33-38``) or
   ``relative_factor`` on v19 (``O19 uom_uom.py:36-38``, data
   ``uom/data/uom_data.xml:21-26``) — by :func:`_dozen_declared_factor`,
   which probes the FIELD, never the version. The private method itself is
   never re-implemented and never called.
2. **``_compute_amount``'s depends set omits ``product_uom_id``**, so a
   UoM-only write does not trigger a recompute. Steps 3 and 7 therefore
   write ``scrap_qty`` in the same call as the UoM — which is exactly what
   the workbook's own steps describe (10 in the reference UoM, then 1 in the
   larger one).
3. **``standard_price`` is written only on the zero-on-hand token product.**
   ``_change_standard_price`` skips a product whose ``quantity_svl`` is zero
   (``O17 stock_account/models/product.py:243-248``), so no revaluation
   layer and no journal entry is posted; and because ``amount`` is a
   **stored** compute over the price, writing it on a live product would
   silently rewrite the stored ``amount`` of every historical scrap of that
   product. The fixture price is restored in ``finally:`` (the workbook's
   postcondition).
4. **The fixture's reference UoM is pinned after creation**
   (:func:`_pin_reference_uom`), not through
   ``common.make_product(uom_id=…)``: that helper mirrors the value onto
   ``uom_po_id`` (tests/wf022/common.py:1083-1092), a field that exists on
   v17 (``O17 product/models/product_template.py:99-102``) and was
   **removed** on v19, where a create carrying it raises ``Invalid field
   'uom_po_id' in 'product.product'``. Both sites now apply the mirror only
   where the field still exists — a capability probe, not a version branch —
   so either route is safe; pinning after creation is kept because it also
   keeps the UoM write off the ``create`` call.

Step 12 ("record the pair (amount, posted valuation value) … see TC167
step 8") is cross-referenced, not duplicated: no fixture in this suite is
ever validated, because a done scrap cannot be unlinked
(``You cannot delete a scrap which is done.``, ``O17 stock/models/stock_scrap.py:107-110``)
and its posted entry cannot be removed. TC167 below carries that pair.

EXPECTED v17 OUTCOME: **PASS** — subject to §0 of ``tests/wf022/common.py``:
``dto_tier_validation_scrap/__manifest__.py:56`` declares
``installable: False`` and Odoo 17 skips a not-installable module even when
the database row says ``state='installed'`` (``O17 odoo/modules/graph.py:72-75``),
so the workbook precondition is the first ``ctx.check`` and a missing
``amount`` fails loudly and correctly attributed rather than erroring.
EXPECTED v19 OUTCOME: **PASS** — ``dto_scrap`` carries the identical compute
and the Units↔Dozens expectation is version-independent by construction.

TC167 — the Journal Entries stat button
----------------------------------------
``dto_stock/models/stock_scrap.py:10-24`` adds a **non-stored** Many2many
computed from the scrap's own moves, empty unless the scrap is done::

    account_move_ids = fields.Many2many(
        'account.move', string='Journal Entries',
        compute='_compute_account_move_ids')          # :10-11

    @api.depends('state')
    def _compute_account_move_ids(self):              # :13-24
        ... res.account_move_ids = res.move_ids.account_move_id   # :22
        ... else: res.account_move_ids = False        # :24

and ``action_view_journal_entries`` (``:26-40``) loads
``account.action_account_moves_all`` through
``ir.actions.act_window._for_xml_id`` (``O17 odoo/addons/base/models/
ir_actions.py:187-196`` → ``_get_action_dict`` ``:198-221``, which is why the
returned dict carries ``xml_id``), then replaces four keys: ``name`` and
``display_name`` → ``Journal Entries``, ``domain`` →
``[('id','in', self.account_move_ids.line_ids.ids)]`` — **line** ids, while
``res_model`` stays the xmlid's own ``account.move.line``
(``O17 account/views/account_move_views.xml:1619-1626``) — and ``context``
→ the three keys in :data:`~tests.wf022.common.JOURNAL_ACTION_CONTEXT`.

The button (``dto_stock/views/stock_scrap_views.xml:8-17``) is
``class="oe_stat_button" icon="fa-book" invisible="not account_move_ids"``
with a bare ``<span class="o_stat_text">Journal Entries</span>`` — **there
is no counter widget**, so workbook step 3's "counter is 1 or greater" is
asserted as ``len(account_move_ids) >= 1``, never as rendered digits.

Steps 6-7 assert the shape core builds for a scrap. A scrap move goes from
an internal location to an inventory-usage one, so ``_account_entry_move``
takes the ``_is_out()`` branch and calls
``_prepare_account_move_vals(acc_valuation, acc_dest, …)``, whose signature
is ``(credit_account_id, debit_account_id, …)`` — Credit = the product
category's ``property_stock_valuation_account_id``, Debit =
``location_dest_id.valuation_in_account_id`` or the category's
``property_stock_account_output_categ_id``
(``O17 stock_account/models/stock_move.py:526, 587-592, 392-399``;
category fields ``O17 stock_account/models/product.py:853, 859``, resolved
at ``:83-85``). v19 rebuilt the engine but lands on the same two sides for
this direction: ``_get_account_move_line_vals`` credits the product's
``stock_valuation`` and debits ``location_dest_id.valuation_account_id``
(``O19 stock_account/models/stock_move.py:229-250``; the location field is
``valuation_account_id`` there, ``O19 stock_account/models/stock_location.py:11``,
against ``valuation_in_account_id`` on v17 ``:10``). :func:`_expected_valuation_accounts`
therefore probes which field the target carries — a capability probe, not a
version branch.

Three adaptations, all documented rather than assertion-weakening:

1. **Read-only over the live done-scrap population.** The workbook fixture
   is "a scrap of TD-P-04 has been validated and is done"; creating one
   cannot be unwound (hard rule 3), so
   :func:`~tests.wf022.common.live_done_scrap_with_entries` selects the
   newest existing done scrap that actually has entries and every assertion
   about it is a read. Only step 9's draft scrap is created, under the
   suite's token, and it is deleted in ``finally:``.
2. **Steps 7-8 defer their BLOCKED verdict to the end of the test.**
   ``stock.valuation.layer`` is a normal model on v17 and its model file is
   **gone** on v19, so the costing-method half cannot be evidenced there.
   Raising at step 7 would also discard step 9, which runs fine on both
   versions — so the reason is collected and ``ctx.blocked`` is called after
   step 9. The verdict is identical (BLOCKED); only the evidence is larger.
3. **The role session is used; exactly one role call falls back, the rest
   are asserted.** ``ROLE_GROUPS`` maps the workbook's ``TD-U-04`` /
   ``TD-U-05`` labels onto real core groups and ``tests/wf022/common.py:561-573``
   marks that mapping ``[UNVERIFIED as group ids]`` — no ``res.groups``
   record exists in ``dto_stock`` / ``dto_scrap`` /
   ``dto_tier_validation_scrap``. Two different failures, handled
   differently, and the difference is deliberate:

   * **No session at all** (the disposable user cannot be built or
     authenticated) — :func:`_role_session` logs the substitution and returns
     the platform session, for every step. A missing test user is an
     environment fact, never a product defect.
   * **A refused call inside a session** — :func:`_try_call` captures it, and
     the caller decides. Only **TC167 step 4** (the ``action_view_journal_entries``
     stat-button call) logs the refusal and re-takes the action from the
     platform session: reading ``account.move`` is granted by
     ``dto_account``'s own ACL rows, not by any stock group, so the guessed
     mapping is the likely cause there. Every other role call — TC167 step 1's
     opening read, and TC182 steps 1, 3 and 7 — is **asserted** with
     ``ctx.check_true``: a plain ``stock.scrap`` read/write is covered by
     ``stock.group_stock_user`` in core's own ACL (``O17
     stock/security/ir.model.access.csv:54`` / ``O19 :41``), so a refusal
     there is a real finding and is reported as a FAIL rather than papered
     over. If it ever fires from the ``[UNVERIFIED-1]`` group guess instead,
     the log line from :func:`_role_session` and the ``actual_desc`` of the
     failing check name the guess explicitly.

EXPECTED v17 OUTCOME: **PASS**.
EXPECTED v19 OUTCOME: **BLOCKED** after step 9 — steps 7-8 need
``stock.valuation.layer``, whose model file no longer exists.
"""
from __future__ import annotations

import json

from adapters.base import OdooRPCError
from framework.registry import test_case
from tests.wf022.common import (ACTION_JOURNAL_ITEMS, DOZEN_IN_REFERENCE_UNITS,
                                EXPECTED_FIELD_ATTRS,
                                EXPECTED_JOURNAL_FIELD_ATTRS,
                                JOURNAL_ACTION_CONTEXT, JOURNAL_ACTION_NAME,
                                JOURNAL_ACTION_RES_MODEL,
                                JOURNAL_ENTRIES_FIELD, MODULE_STOCK,
                                MODULE_TIER_SCRAP, ROLE_GROUPS, STAT_BUTTON,
                                STAT_BUTTON_ICON, STAT_BUTTON_INVISIBLE,
                                STAT_BUTTON_LABEL, STATE_DONE, STATE_DRAFT,
                                UOM_DOZEN_XMLID, UOM_UNIT_XMLID, WORKFLOW,
                                WORKFLOW_NAME, account_move_line_rows,
                                account_move_rows, allow_uom_on_product,
                                buttons_named, check_journal_entries_field,
                                check_scrap_extension, dozen_uom_id,
                                drop_scraps, field_node, fields_get,
                                has_valuation_layer_model, journal_entries_of,
                                live_done_scrap_with_entries, m2o_id,
                                make_product, make_scrap, open_namespace,
                                parse_arch, product_info, product_tmpl_of,
                                read_scrap,
                                readonly_is_absolute, readonly_of, rpc_as_role,
                                scrap_arch, set_standard_price, sweep_wf022,
                                trace, unit_uom_id, valuation_layers,
                                view_journal_entries)

#: Exact in binary, so every expected value below is exact too and no
#: assertion depends on float formatting: 10 × 7.25 = 72.5,
#: 12 × 7.25 = 87.0, 12 × 9.5 = 114.0.
FIXTURE_PRICE = 7.25
REPRICED_PRICE = 9.5
#: Workbook TC182 step 3.
REFERENCE_QTY = 10.0
#: Workbook TC182 step 7.
LARGER_UOM_QTY = 1.0


# ------------------------------------------------------------ local helpers
# Defined here, not in common.py: common.py is owned by another agent and
# carries none of these. Each is a capability probe or an error-capturing
# wrapper — no product behaviour is re-implemented in any of them.
def _money(value) -> float:
    """Round to two decimals before comparing.

    ``amount`` is a Monetary rounded to its currency's decimals, and journal
    items are stored at the currency's precision, so every comparison in
    this file is made at two decimals rather than on raw float equality.
    """
    return round(float(value or 0.0), 2)


def _try_call(func, *args, **kwargs):
    """Run an RPC call that may legitimately be refused.

    Returns ``(ok, value_or_message)``. Never raises a bare AssertionError
    and never swallows anything but ``OdooRPCError``
    (AUTOMATION_CONVENTIONS, "Errors").
    """
    try:
        return True, func(*args, **kwargs)
    except OdooRPCError as exc:
        return False, str(exc)


def _role_session(ctx, role: str):
    """An authenticated session for the workbook's role label.

    ``ROLE_GROUPS`` (tests/wf022/common.py:561-573) maps ``TD-U-04`` /
    ``TD-U-05`` onto the real core groups the labels describe and marks the
    mapping ``[UNVERIFIED as group ids]``. When the disposable user cannot
    be built or authenticated, the platform session is used instead and the
    substitution is logged, so a guessed group mapping can never surface as
    a product defect. Authentication is forced here rather than mid-step so
    a failure is recorded at the point it happened.
    """
    try:
        role_rpc = rpc_as_role(ctx, role)
        role_rpc.uid                      # forces /web/session/authenticate
        return role_rpc, f"{role} ({', '.join(ROLE_GROUPS.get(role, []))})"
    except OdooRPCError as exc:
        ctx.log(f"[adaptation] no {role} session ({exc}) — continuing with "
                f"the platform session; ROLE_GROUPS is [UNVERIFIED as group "
                f"ids] (tests/wf022/common.py:561-573)")
        return ctx.adapter.rpc, f"the platform session (no {role} session)"


def _company_currency(ctx, company_id):
    """``res.company.currency_id`` for one company, with its code.

    ``company_currency_id`` is ``related='company_id.currency_id'``
    (dto_tier_validation_scrap/models/stock_scrap.py:22-23 /
    dto_scrap :41-42), so the expected value is the currency of the scrap's
    OWN company — not of the warehouse's, which is what
    ``common.company_currency`` resolves.
    """
    rpc = ctx.adapter.rpc
    if not company_id:
        return {"id": None, "name": ""}
    currency_id = m2o_id(rpc.read("res.company", [company_id],
                                  ["currency_id"])[0]["currency_id"])
    if not currency_id:
        return {"id": None, "name": ""}
    return {"id": currency_id,
            "name": rpc.read("res.currency", [currency_id], ["name"])[0]["name"]}


def _pin_reference_uom(ctx, product_id: int, uom_id: int):
    """Pin a brand-new product's reference UoM, explicitly.

    Deliberately NOT through ``common.make_product(uom_id=…)``: that helper
    mirrors the value onto ``uom_po_id`` (tests/wf022/common.py:1083-1092)
    and ``product.template.uom_po_id`` exists on v17
    (``O17 product/models/product_template.py:99-102``) but was **removed**
    on v19 — a create carrying it raises ``Invalid field 'uom_po_id' in
    'product.product'`` there. (That helper now probes for the field too, so
    the route is safe either way.) The UoM is therefore written after
    creation and the purchase UoM mirrored only where the field still
    exists, which is a capability probe rather than a version branch. Both
    versions
    already default ``uom_id`` to ``uom.product_uom_unit``
    (``O17 product/models/product_template.py:_get_default_uom_id``,
    ``O19 :34-36``), and a brand-new product has no stock move, so stock's
    guard against changing a product's UoM cannot fire.
    """
    rpc = ctx.adapter.rpc
    values = {"uom_id": uom_id}
    if rpc.field_exists("product.template", "uom_po_id"):
        values["uom_po_id"] = uom_id
    rpc.write("product.template", [product_tmpl_of(rpc, product_id)], values)


def _dozen_declared_factor(rpc, dozen_id) -> dict:
    """What the target's own UoM data declares a Dozen to be worth.

    v17 declares ``factor_inv = 12`` (field ``O17 uom/models/uom_uom.py:62``,
    data ``O17 uom/data/uom_data.xml:33-38``); v19 replaced the whole ratio
    model and declares ``relative_factor = 12`` with
    ``relative_uom_id = uom.product_uom_unit`` (field
    ``O19 uom/models/uom_uom.py:36-38``, data ``O19 uom/data/uom_data.xml:21-26``).
    ``factor`` itself is deliberately NOT read: it is 0.0833… on v17 and 12
    on v19 for the same record. The two fields are mutually exclusive, so
    probing which one exists is a capability probe, not a version branch.
    """
    for fname in ("relative_factor", "factor_inv"):
        if rpc.field_exists("uom.uom", fname):
            row = rpc.read("uom.uom", [dozen_id], [fname])[0]
            return {"field": fname, "value": row.get(fname)}
    return {"field": None, "value": None}


def _id_domain(action) -> dict:
    """Decompose an act_window domain of the shape ``[('id','in',[…])]``.

    ``action_view_journal_entries`` builds exactly one leaf
    (dto_stock/models/stock_scrap.py:33); JSON-RPC turns its tuple into a
    list, so the leaf is unpacked rather than compared as a literal.
    """
    leaves = [list(leaf) for leaf in ((action or {}).get("domain") or [])
              if isinstance(leaf, (list, tuple))]
    if len(leaves) != 1 or len(leaves[0]) != 3:
        return {"field": None, "operator": None, "ids": leaves}
    field, operator, ids = leaves[0]
    return {"field": field, "operator": operator,
            "ids": sorted(ids) if isinstance(ids, (list, tuple)) else ids}


def _expected_valuation_accounts(rpc, scrap_row) -> dict:
    """The two accounts core will have used for this scrap's write-off.

    Credit = the product category's ``property_stock_valuation_account_id``
    (``O17 stock_account/models/product.py:859`` resolved at ``:85``;
    ``O19 :768``). Debit = the destination location's own valuation account
    when it carries one, else the category's stock-output account
    (``O17 stock_account/models/stock_move.py:392-399``). The location field
    is ``valuation_in_account_id`` on v17
    (``O17 stock_account/models/stock_location.py:10``) and
    ``valuation_account_id`` on v19 (``O19 :11``); they are mutually
    exclusive, so the probe is by field, never by version.
    """
    product_id = m2o_id(scrap_row["product_id"])
    categ_id = m2o_id(rpc.read("product.product", [product_id],
                               ["categ_id"])[0]["categ_id"])
    dest_id = m2o_id(rpc.read("stock.scrap", [scrap_row["id"]],
                              ["scrap_location_id"])[0]["scrap_location_id"])

    credit = None
    if rpc.field_exists("product.category", "property_stock_valuation_account_id"):
        credit = m2o_id(rpc.read("product.category", [categ_id],
                                 ["property_stock_valuation_account_id"])[0]
                        ["property_stock_valuation_account_id"])

    debit = None
    for fname in ("valuation_in_account_id", "valuation_account_id"):
        if dest_id and rpc.field_exists("stock.location", fname):
            debit = m2o_id(rpc.read("stock.location", [dest_id], [fname])[0][fname])
            if debit:
                break
    if not debit and rpc.field_exists("product.category",
                                      "property_stock_account_output_categ_id"):
        debit = m2o_id(rpc.read("product.category", [categ_id],
                                ["property_stock_account_output_categ_id"])[0]
                       ["property_stock_account_output_categ_id"])

    return {"product_id": product_id, "categ_id": categ_id,
            "scrap_location_id": dest_id, "credit": credit, "debit": debit}


def _record_pair(ctx, payload: dict, filename: str, label: str):
    """Persist the (amount, posted value) pair as run evidence.

    Workbook TC167 step 8 says *record* both numbers; they are written as a
    JSON artifact next to the run's other evidence as well as logged, so the
    pair survives the run for the backfill-or-freeze decision TC182's notes
    call for.
    """
    path = ctx.artifacts_dir / filename
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str),
                    encoding="utf-8")
    ctx.add_artifact(path, "log", label)


# ==================================================================== TC182
@test_case(
    id="TEST-WF022-TC182",
    name="Scrap Amount equals quantity × standard price after UoM conversion",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module=MODULE_TIER_SCRAP,
    priority="P0", kind="API", order=22182,
    description="amount is the CONVERTED-quantity estimate: 10 reference "
                "units × standard price, then 1 Dozen × standard price = "
                "12 × price and not 1 × price, and the stored compute "
                "follows a change of standard_price.",
    traceability=trace("DATAONE-TC182"))
def test_tc182(ctx):
    rpc = ctx.adapter.rpc
    open_namespace(ctx)
    product_id = None
    scrap_id = None
    try:
        with ctx.step("Precondition: stock.scrap carries the WF-022 field set "
                      "(dto_tier_validation_scrap is contributing amount)"):
            check_scrap_extension(ctx)

        with ctx.step("1. Log in as TD-U-05 and open the draft scrap for TD-P-07"):
            unit_id, dozen_id = unit_uom_id(rpc), dozen_uom_id(rpc)
            if not unit_id or not dozen_id:
                ctx.blocked(
                    f"{UOM_UNIT_XMLID} and {UOM_DOZEN_XMLID} do not both "
                    f"resolve on {ctx.env.key} (db={ctx.env.db}) — the "
                    f"reference/larger UoM pair this case converts between "
                    f"is not in the database, and the conversion cannot be "
                    f"computed in the test because uom.uom._compute_quantity "
                    f"is private (O17 uom/models/uom_uom.py:211).")
            # TD-P-07 is "a storable product whose reference UoM is feet with
            # a known standard_price per foot"; the fixture uses Units as the
            # reference and Dozens as the larger UoM in the same category —
            # the ratio, not the unit name, is what the case turns on.
            product_id = make_product(ctx, "CMP-WIRE-FT",
                                      standard_price=FIXTURE_PRICE)
            _pin_reference_uom(ctx, product_id, unit_id)
            allow_uom_on_product(rpc, product_id, dozen_id)
            scrap_id = make_scrap(ctx, product_id, qty=1.0, uom_id=unit_id)
            role_rpc, role_label = _role_session(ctx, "TD-U-05")
            ok, opened = _try_call(role_rpc.read, "stock.scrap", [scrap_id],
                                   ["name", "state", "product_id", "scrap_qty"])
            ctx.check_true(f"the draft scrap opens for {role_label}", ok,
                           actual_desc=repr(opened))
            ctx.check("the fixture opens in draft", STATE_DRAFT,
                      opened[0]["state"])

        with ctx.step("2. Record sp = product.standard_price and "
                      "ref_uom = product.uom_id"):
            info = product_info(rpc, product_id)
            standard_price = float(info["standard_price"])
            ref_uom = m2o_id(info["uom_id"])
            ctx.log(f"sp={standard_price} ref_uom={info['uom_name']!r} "
                    f"({ref_uom}) categ={info['categ_id']!r}")
            ctx.check("sp is the fixture's standard price",
                      FIXTURE_PRICE, _money(standard_price))
            ctx.check("ref_uom is the product's reference UoM "
                      f"({UOM_UNIT_XMLID})", unit_id, ref_uom)

        with ctx.step("3. Set the scrap UoM to the reference UoM and the "
                      "quantity to 10"):
            # scrap_qty is written alongside the UoM deliberately:
            # _compute_amount depends on ('scrap_qty', 'product_id',
            # 'product_id.standard_price') and NOT on product_uom_id
            # (dto_tier_validation_scrap/models/stock_scrap.py:68), so a
            # UoM-only write would not trigger the recompute at all.
            ok, written = _try_call(role_rpc.write, "stock.scrap", [scrap_id],
                                    {"product_uom_id": ref_uom,
                                     "scrap_qty": REFERENCE_QTY})
            ctx.check_true(f"{role_label} can set the UoM and the quantity",
                           ok, actual_desc=repr(written))
            row = read_scrap(rpc, scrap_id)
            ctx.check("the scrap saved with 10 in the reference UoM",
                      {"scrap_qty": REFERENCE_QTY, "product_uom_id": ref_uom},
                      {"scrap_qty": row["scrap_qty"],
                       "product_uom_id": m2o_id(row["product_uom_id"])})

        with ctx.step("4. Save and assert amount == 10 * sp"):
            row = read_scrap(rpc, scrap_id)
            ctx.check("amount = 10 reference units × standard price",
                      _money(REFERENCE_QTY * standard_price),
                      _money(row["amount"]))

        with ctx.step("5. Assert the field is displayed read-only, in company "
                      "currency, with help text Estimated Amount"):
            declared = fields_get(rpc, "stock.scrap", ["amount"],
                                  attributes=list(EXPECTED_FIELD_ATTRS["amount"]))
            ctx.check("amount's declared attributes "
                      "(dto_tier_validation_scrap/models/stock_scrap.py:24-25)",
                      EXPECTED_FIELD_ATTRS["amount"], declared.get("amount"))
            root = parse_arch(scrap_arch(ctx, "form"))
            node = field_node(root, "amount")
            ctx.check_true("the amount field is on the rendered full form "
                           "(dto_tier_validation_scrap/views/"
                           "stock_scrap_views.xml:67)",
                           node is not None,
                           actual_desc="present" if node is not None else "absent")
            options = node.get("options") or ""
            ctx.log(f'rendered <field name="amount" '
                    f'readonly={readonly_of(root, "amount")!r} '
                    f'widget={node.get("widget")!r} options={options!r}>')
            # readonly is NEVER compared to "1": TierValidation.get_view
            # rewrites every field node's modifier to "(old) or (new)" on v17
            # (DTO/3rd-addons/base_tier_validation/models/tier_validation.py:780-788).
            ctx.check("the amount node is rendered read-only, as a monetary "
                      "widget, against company_currency_id",
                      {"readonly_is_absolute": True, "widget": "monetary",
                       "options_name_the_currency_field": True},
                      {"readonly_is_absolute": readonly_is_absolute(node.get("readonly")),
                       "widget": node.get("widget"),
                       "options_name_the_currency_field":
                           "currency_field" in options
                           and "company_currency_id" in options})

        with ctx.step("6. Assert company_currency_id resolves to the company "
                      "currency (TD-CO-02, USD)"):
            row = read_scrap(rpc, scrap_id)
            company_id = m2o_id(row["company_id"])
            currency = _company_currency(ctx, company_id)
            # The workbook's instance is TD-CO-02/USD; the rule is
            # related='company_id.currency_id', so the assertion is the
            # resolution and the target's own currency code is recorded.
            ctx.log(f"company {company_id} → currency {currency['name']!r} "
                    f"({currency['id']}); the workbook's instance of this is "
                    f"TD-CO-02 / USD")
            ctx.check("company_currency_id == the scrap company's currency "
                      "(related='company_id.currency_id')",
                      currency["id"], m2o_id(row["company_currency_id"]))

        with ctx.step("7. Change the scrap UoM to the larger UoM in the same "
                      "category and set the quantity to 1"):
            ok, written = _try_call(role_rpc.write, "stock.scrap", [scrap_id],
                                    {"product_uom_id": dozen_id,
                                     "scrap_qty": LARGER_UOM_QTY})
            ctx.check_true(f"{role_label} can switch the scrap to the larger "
                           f"UoM", ok, actual_desc=repr(written))
            row = read_scrap(rpc, scrap_id)
            ctx.check("the scrap saved with 1 in the larger UoM",
                      {"scrap_qty": LARGER_UOM_QTY, "product_uom_id": dozen_id},
                      {"scrap_qty": row["scrap_qty"],
                       "product_uom_id": m2o_id(row["product_uom_id"])})

        with ctx.step("8. Compute expected = "
                      "product_uom_id._compute_quantity(1, ref_uom) * sp"):
            # _compute_quantity is private (AccessError over call_kw) and its
            # arithmetic is inverted between v17 and v19, so it is neither
            # called nor re-implemented. What is asserted instead is the
            # target's OWN declared ratio, read from whichever field this
            # version carries.
            factor = _dozen_declared_factor(rpc, dozen_id)
            ctx.log(f"declared ratio: uom.uom.{factor['field']} = "
                    f"{factor['value']!r} on {UOM_DOZEN_XMLID}")
            ctx.check("the target's own UoM data says one Dozen is twelve "
                      "reference Units",
                      DOZEN_IN_REFERENCE_UNITS, float(factor["value"] or 0.0))
            expected_amount = _money(DOZEN_IN_REFERENCE_UNITS * standard_price)
            ctx.log(f"expected = 12 × {standard_price} = {expected_amount}")

        with ctx.step("9. Save and assert amount == expected — the conversion "
                      "happens before the multiplication"):
            ctx.check("amount = converted quantity (1 Dozen = 12 Units) × "
                      "standard price",
                      expected_amount, _money(read_scrap(rpc, scrap_id)["amount"]))

        with ctx.step("10. Assert amount != 1 * sp — proving the conversion "
                      "actually occurred rather than the UoM being ignored"):
            amount = _money(read_scrap(rpc, scrap_id)["amount"])
            ctx.check_true("amount is not the unconverted 1 × standard price",
                           amount != _money(standard_price),
                           actual_desc=f"amount={amount}, "
                                       f"1 × sp={_money(standard_price)}")

        with ctx.step("11. Change standard_price on the product and assert "
                      "amount recomputes (it is a stored compute with a "
                      "dependency on the price)"):
            # Written with the platform session on a token-scoped product
            # with zero on hand: _change_standard_price skips a product whose
            # quantity_svl is zero (O17 stock_account/models/product.py:243-248),
            # so nothing is revalued and no entry is posted.
            set_standard_price(rpc, product_id, REPRICED_PRICE)
            ctx.check("standard_price was written", REPRICED_PRICE,
                      _money(product_info(rpc, product_id)["standard_price"]))
            ctx.check("amount followed the price "
                      "(@api.depends(…, 'product_id.standard_price'), store=True)",
                      _money(DOZEN_IN_REFERENCE_UNITS * REPRICED_PRICE),
                      _money(read_scrap(rpc, scrap_id)["amount"]))

        with ctx.step("12. Record the pair (amount, posted valuation value) "
                      "for this scrap once validated and assert they differ "
                      "on a FIFO product — see TC167 step 8"):
            # Not duplicated here: no fixture in this suite is ever validated
            # (a done scrap cannot be unlinked — O17 stock/models/
            # stock_scrap.py:107-110 — and its posted entry cannot be
            # removed), so the pair is asserted by TEST-WF022-TC167 over an
            # existing done scrap instead.
            state = read_scrap(rpc, scrap_id)["state"]
            ctx.log("the (amount, posted value) pair is asserted by "
                    "TEST-WF022-TC167 step 8, read-only over a live done "
                    "scrap; validating this fixture would be an irreversible "
                    "write to a populated clone")
            ctx.check("the fixture is still draft, so it has no posted "
                      "valuation value of its own to pair with",
                      STATE_DRAFT, state)
    finally:
        with ctx.step("Cleanup: restore standard_price and remove the "
                      "fixtures"):
            try:
                if product_id:
                    set_standard_price(rpc, product_id, FIXTURE_PRICE)
            except Exception as exc:                       # noqa: BLE001
                ctx.log(f"[warn] standard_price not restored: {exc}")
            try:
                drop_scraps(rpc, [scrap_id])
            except Exception as exc:                       # noqa: BLE001
                ctx.log(f"[warn] fixture scrap not removed: {exc}")
            try:
                sweep_wf022(rpc)
            except Exception as exc:                       # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")


# ==================================================================== TC167
@test_case(
    id="TEST-WF022-TC167",
    name="The scrap order's Journal Entries stat button opens its write-off "
         "entry",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module=MODULE_STOCK,
    priority="P1", kind="API", order=22167,
    description="On a done scrap the stat button carries its account moves "
                "and opens account.action_account_moves_all domained to "
                "their journal items; the entry credits stock valuation and "
                "debits the scrap destination account; amount and the posted "
                "value differ by the costing method alone; a draft scrap's "
                "counter is zero.",
    traceability=trace("DATAONE-TC167"))
def test_tc167(ctx):
    rpc = ctx.adapter.rpc
    open_namespace(ctx)
    draft_id = None
    blockers = []
    try:
        with ctx.step("Precondition: dto_stock contributes "
                      "stock.scrap.account_move_ids"):
            check_journal_entries_field(ctx)
            declared = fields_get(
                rpc, "stock.scrap", [JOURNAL_ENTRIES_FIELD],
                attributes=list(EXPECTED_JOURNAL_FIELD_ATTRS))
            ctx.check(f"{JOURNAL_ENTRIES_FIELD}'s declared attributes "
                      "(dto_stock/models/stock_scrap.py:10-11)",
                      EXPECTED_JOURNAL_FIELD_ATTRS,
                      declared.get(JOURNAL_ENTRIES_FIELD))

        with ctx.step("1. Log in as TD-U-04 and open the done scrap"):
            found = live_done_scrap_with_entries(rpc)
            if found and found.get("error"):
                # The done branch of _compute_account_move_ids raised. Not a
                # defect this case can attribute: the deployed revision of
                # dto_stock decides it, and §0 of the plan doc records that
                # the v17 server may have loaded either one.
                ctx.blocked(
                    f"reading stock.scrap.{JOURNAL_ENTRIES_FIELD} over the "
                    f"done population raised on {ctx.env.key} "
                    f"(db={ctx.env.db}): {found['error']!r}. The done branch "
                    f"of _compute_account_move_ids dereferences "
                    f"move_ids.account_move_id "
                    f"(dto_stock/models/stock_scrap.py:22), a field that "
                    f"exists only on v19 (O19 stock_account/models/"
                    f"stock_move.py:51); v17 carries the One2many "
                    f"account_move_ids instead (O17 :19) and the "
                    f"v17-deployed revision reads that plural form (git "
                    f"6e410c8:project-addons/dto_stock/models/"
                    f"stock_scrap.py:17). Field probe on this target: "
                    f"{found['probe']!r}. See docs/"
                    f"WF-022_AUTOMATION_PLAN.md §0, realities 1 and 2.")
            if not found:
                ctx.blocked(
                    f"no done stock.scrap carrying journal entries was found "
                    f"on {ctx.env.key} (db={ctx.env.db}) in the newest 300 "
                    f"done scraps. This case is read-only over live data by "
                    f"design: a done scrap cannot be unlinked ('You cannot "
                    f"delete a scrap which is done.', O17 stock/models/"
                    f"stock_scrap.py:107-110) and its posted valuation entry "
                    f"cannot be removed, so the fixture the workbook "
                    f"describes cannot be created on a populated clone.")
            scrap = found["scrap"]
            scrap_id = scrap["id"]
            product_id = m2o_id(scrap["product_id"])
            entry_ids = sorted(found["entry_ids"])
            move_ids = list(scrap.get("move_ids") or [])
            role_rpc, role_label = _role_session(ctx, "TD-U-04")
            ok, rows = _try_call(role_rpc.read, "stock.scrap", [scrap_id],
                                 ["name", "state", JOURNAL_ENTRIES_FIELD])
            ctx.check_true(f"the done scrap opens for {role_label}", ok,
                           actual_desc=repr(rows))
            ctx.check("the live subject is a done scrap", STATE_DONE,
                      rows[0]["state"])
            ctx.log(f"read-only subject: scrap {scrap_id} {scrap['name']!r} "
                    f"product={scrap['product_id']!r} qty={scrap['scrap_qty']} "
                    f"uom={scrap['product_uom_id']!r} moves={move_ids} "
                    f"entries={entry_ids}")

        with ctx.step("2. Assert the Journal Entries stat button is visible"):
            nodes = buttons_named(parse_arch(scrap_arch(ctx, "form")),
                                  STAT_BUTTON)
            ctx.check_true(f'exactly one <button name="{STAT_BUTTON}"> is in '
                           f"the rendered form — the only assertion that "
                           f"catches an inherit that loaded cleanly and "
                           f"matched nothing",
                           len(nodes) == 1, actual_desc=f"{len(nodes)} node(s)")
            node = nodes[0]
            label = " ".join(t.strip() for t in node.itertext() if t.strip())
            ctx.check("the stat button as rendered "
                      "(dto_stock/views/stock_scrap_views.xml:10-17)",
                      {"type": "object", "class": "oe_stat_button",
                       "icon": STAT_BUTTON_ICON,
                       "invisible": STAT_BUTTON_INVISIBLE,
                       "label": STAT_BUTTON_LABEL},
                      {"type": node.get("type"), "class": node.get("class"),
                       "icon": node.get("icon"),
                       "invisible": node.get("invisible"), "label": label})
            ctx.check_true(f"{STAT_BUTTON_INVISIBLE!r} is false for this "
                           f"record, so the button is visible on it",
                           bool(entry_ids),
                           actual_desc=f"account_move_ids={entry_ids}")

        with ctx.step("3. Assert its counter is 1 or greater"):
            # The button carries no counter widget — its label is a bare
            # <span class="o_stat_text"> (dto_stock/views/
            # stock_scrap_views.xml:14-16) — so the "counter" is the length
            # of the recordset, never rendered digits.
            ctx.check_true("len(account_move_ids) >= 1", len(entry_ids) >= 1,
                           actual_desc=f"{len(entry_ids)} entry/entries: "
                                       f"{entry_ids}")

        with ctx.step("4. Click the button"):
            ok, action = _try_call(role_rpc.call, "stock.scrap", STAT_BUTTON,
                                   [scrap_id])
            if not ok:
                ctx.log(f"[adaptation] {role_label} could not run "
                        f"{STAT_BUTTON}: {action!r}. Reading account.move is "
                        f"granted by dto_account's own ir.model.access rows, "
                        f"not by any stock group, and ROLE_GROUPS is "
                        f"[UNVERIFIED as group ids] "
                        f"(tests/wf022/common.py:561-573) — so this is "
                        f"recorded, not asserted, and the action below is "
                        f"taken from the platform session.")
                action = view_journal_entries(rpc, scrap_id)
            ctx.check("the button returns an act_window "
                      "(dto_stock/models/stock_scrap.py:26-40)",
                      "ir.actions.act_window", (action or {}).get("type"))

        with ctx.step("5. Assert the action opened is "
                      "account.action_account_moves_all, domained to this "
                      "scrap's account moves"):
            expected_line_ids = sorted(
                rpc.search("account.move.line", [("move_id", "in", entry_ids)]))
            domain = _id_domain(action)
            ctx.log(f"action: xml_id={action.get('xml_id')!r} "
                    f"res_model={action.get('res_model')!r} "
                    f"domain={action.get('domain')!r}")
            # res_model stays the xmlid's own account.move.line and the
            # domain is built on account_move_ids.line_ids.ids — LINE ids,
            # not move ids (dto_stock/models/stock_scrap.py:33).
            ctx.check("the action, its model and its domain",
                      {"xml_id": ACTION_JOURNAL_ITEMS,
                       "name": JOURNAL_ACTION_NAME,
                       "res_model": JOURNAL_ACTION_RES_MODEL,
                       "domain_field": "id", "domain_operator": "in",
                       "domain_ids": expected_line_ids},
                      {"xml_id": action.get("xml_id"),
                       "name": action.get("name"),
                       "res_model": action.get("res_model"),
                       "domain_field": domain["field"],
                       "domain_operator": domain["operator"],
                       "domain_ids": domain["ids"]})
            ctx.check("the action's context replaces the xmlid's own "
                      "(dto_stock/models/stock_scrap.py:34-38)",
                      JOURNAL_ACTION_CONTEXT, action.get("context"))

        with ctx.step("6. Assert the entry debits the scrap/inventory expense "
                      "account and credits the Stock Valuation account of "
                      "TD-PC-02"):
            lines = account_move_line_rows(rpc, entry_ids)
            for entry in account_move_rows(rpc, entry_ids):
                ctx.log(f"entry {entry['id']}: {entry['name']!r} "
                        f"ref={entry['ref']!r} state={entry['state']!r} "
                        f"journal={entry['journal_id']!r}")
            for line in lines:
                ctx.log(f"  line {line['id']}: account={line['account_id']!r} "
                        f"debit={line['debit']} credit={line['credit']}")
            accounts = _expected_valuation_accounts(rpc, scrap)
            ctx.log(f"expected from configuration: {accounts!r}")
            if not accounts["credit"] or not accounts["debit"]:
                blockers.append(
                    f"the workbook precondition 'the product category has "
                    f"valuation accounts configured' is not met for the live "
                    f"subject: category {accounts['categ_id']} / scrap "
                    f"location {accounts['scrap_location_id']} resolve to "
                    f"credit={accounts['credit']} debit={accounts['debit']}, "
                    f"so the two sides of the entry cannot be predicted from "
                    f"configuration (O17 stock_account/models/"
                    f"stock_move.py:392-399, 587-592)")
            else:
                credit_accounts = sorted({m2o_id(ln["account_id"]) for ln in lines
                                          if _money(ln["credit"]) > 0})
                debit_accounts = sorted({m2o_id(ln["account_id"]) for ln in lines
                                         if _money(ln["debit"]) > 0})
                ctx.check("the write-off entry's two sides",
                          {"credit_account_ids": [accounts["credit"]],
                           "debit_account_ids": [accounts["debit"]],
                           "balanced": True},
                          {"credit_account_ids": credit_accounts,
                           "debit_account_ids": debit_accounts,
                           "balanced":
                               _money(sum(ln["debit"] or 0.0 for ln in lines))
                               == _money(sum(ln["credit"] or 0.0 for ln in lines))})

        with ctx.step("7. Assert the entry's total value equals the scrapped "
                      "quantity valued at the product's costing-method cost "
                      "(FIFO layer cost)"):
            posted = _money(sum(ln["debit"] or 0.0 for ln in lines))
            layers = []
            layer_costed = None
            if not has_valuation_layer_model(rpc):
                blockers.append(
                    f"stock.valuation.layer does not exist on {ctx.env.key} "
                    f"(db={ctx.env.db}) — v19 deleted the model file and "
                    f"builds the entry from stock.move._get_aml_value instead "
                    f"(O19 stock_account/models/stock_move.py:229-250), so "
                    f"steps 7-8 cannot tie the posted total back to a layer "
                    f"unit cost on this target. The BLOCKED verdict is raised "
                    f"after step 9 so the draft⇒empty branch is still "
                    f"evidenced.")
            else:
                layers = valuation_layers(rpc, move_ids)
                if not layers:
                    blockers.append(
                        f"the live done scrap {scrap_id} carries no "
                        f"stock.valuation.layer for its moves {move_ids} — "
                        f"that product is not real-time valued, so the "
                        f"costing-method cost this step compares against does "
                        f"not exist for it")
            if layers:
                layer_value = _money(abs(sum(ly["value"] or 0.0
                                             for ly in layers)))
                layer_costed = _money(sum(abs(ly["quantity"] or 0.0)
                                          * (ly["unit_cost"] or 0.0)
                                          for ly in layers))
                ctx.log(f"entry total (debit side) = {posted}; layer value = "
                        f"{layer_value}; Σ|quantity| × unit_cost = "
                        f"{layer_costed}; layers = {layers!r}")
                ctx.check("the posted total is the scrapped quantity at the "
                          "costing-method unit cost",
                          {"entry_total_equals_layer_value": True,
                           "layer_value_equals_quantity_times_unit_cost": True},
                          {"entry_total_equals_layer_value": posted == layer_value,
                           "layer_value_equals_quantity_times_unit_cost":
                               layer_value == layer_costed})

        with ctx.step("8. Record both the posted value and scrap.amount and "
                      "assert the difference is explained by the costing "
                      "method, not by a defect"):
            if not layers:
                ctx.log("deferred with step 7 — see the BLOCKED reason at the "
                        "end of this test")
            elif "amount" not in scrap:
                blockers.append(
                    "stock.scrap.amount is absent on this target, so the pair "
                    "(amount, posted value) has only one half — see §0 of "
                    "tests/wf022/common.py (dto_tier_validation_scrap/"
                    "__manifest__.py:56 declares installable=False)")
            else:
                reference_qty = abs(sum(ly["quantity"] or 0.0 for ly in layers))
                standard_price = float(
                    rpc.read("product.product", [product_id],
                             ["standard_price"])[0]["standard_price"])
                amount = _money(scrap.get("amount"))
                estimate = _money(reference_qty * standard_price)
                pair = {"scrap_id": scrap_id, "scrap": scrap["name"],
                        "product_id": product_id,
                        "reference_quantity": reference_qty,
                        "standard_price": standard_price,
                        "amount": amount, "posted_value": posted,
                        "costing_unit_costs": [ly["unit_cost"] for ly in layers],
                        "gap": _money(amount - posted),
                        "version": ctx.env.version, "db": ctx.env.db}
                ctx.log(f"pair recorded: {pair!r}")
                _record_pair(ctx, pair, "TC167-amount-vs-posted-value.json",
                             "TC167 amount vs posted valuation value")
                # Both numbers value the SAME reference quantity: amount uses
                # standard_price (dto_tier_validation_scrap/models/
                # stock_scrap.py:71-72), the ledger uses the costing-method
                # unit cost. That, and nothing else, is the difference — which
                # is why amount is a routing approximation and never the
                # write-off value.
                ctx.check("amount is the standard-price estimate while the "
                          "posted value is the costing-method cost, on the "
                          "same reference quantity",
                          {"amount_equals_quantity_times_standard_price": True,
                           "posted_equals_quantity_times_costing_unit_cost": True},
                          {"amount_equals_quantity_times_standard_price":
                               amount == estimate,
                           "posted_equals_quantity_times_costing_unit_cost":
                               posted == layer_costed})

        with ctx.step("9. Open a draft scrap and assert the stat button's "
                      "counter is zero"):
            draft_product = make_product(ctx, "CMP-CONN-A", standard_price=3.0)
            draft_id = make_scrap(ctx, draft_product, qty=1.0)
            ctx.check("a draft scrap's account_move_ids is empty (the else "
                      "branch, dto_stock/models/stock_scrap.py:23-24)",
                      [], journal_entries_of(rpc, draft_id))
            nothing = view_journal_entries(rpc, draft_id)
            ctx.check_true("action_view_journal_entries returns nothing for "
                           "it (the early return, "
                           "dto_stock/models/stock_scrap.py:27-28)",
                           nothing in (None, False, {}, []),
                           actual_desc=repr(nothing))
            ctx.log(f"so {STAT_BUTTON_INVISIBLE!r} is true on the draft scrap "
                    f"and the stat button is hidden")

        if blockers:
            ctx.blocked(" | ".join(blockers))
    finally:
        with ctx.step("Cleanup: remove the draft fixture (the live done scrap "
                      "was read-only throughout)"):
            try:
                drop_scraps(rpc, [draft_id])
            except Exception as exc:                       # noqa: BLE001
                ctx.log(f"[warn] draft fixture not removed: {exc}")
            try:
                sweep_wf022(rpc)
            except Exception as exc:                       # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")
