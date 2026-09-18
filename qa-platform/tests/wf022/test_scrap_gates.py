"""DATAONE-WF-022 — the quick-scrap gates: TC178, TC179, TC183.

Three cases about the same control surface. Abbreviations: ``DTO`` =
``D:/Projects/dataone/DTO-Odoo``, ``O17`` = ``D:/Projects/dataone/odoo-17.0``,
``O19`` = ``D:/Projects/odoo-19.0``.

What this file proves
---------------------
**TC178 — the rename.** The quick-scrap dialog reached from a manufacturing
order or a transfer is ``stock.stock_scrap_form_view2`` (``O17
mrp/models/mrp_production.py:2166`` and ``O17 stock/models/stock_picking.py:1565``
both resolve that xmlid, ``target: 'new'``). Its footer button is core's
``<button name="action_validate" string="Scrap Products" type="object"
class="btn-primary" data-hotkey="q"/>`` (``O17 stock/views/stock_scrap_views.xml:191``
/ ``O19 :175``), and the DataOne inherit renames **only that node**::

    <xpath expr="//button[@name='action_validate']" position="attributes">
        <attribute name="name">action_confirm_create_scrap</attribute>

(v17 ``dto_tier_validation_scrap/views/stock_scrap_views.xml:32-34``; v19 the
same inherit at ``dto_scrap/views/stock_scrap_views.xml:39-41``). The renamed
method neither scraps nor writes — it is ``ensure_one()``, a zero-quantity
guard, and a return of an ``ir.actions.act_window`` onto
``stock.stock_scrap_form_view`` with ``target: 'current'`` (v17 ``models/
stock_scrap.py:96-109`` / v19 ``:113-132``). So the dialog's Validate is a
navigation action and nothing moves.

The case is asserted on the **rendered arch** (``get_view``), not on a tour:
the workbook's own step 13 demands *"read the rendered arch, not just the
effect"*, and that is the only assertion that catches an xpath which loaded
cleanly and matched nothing. ``action_confirm_create_scrap`` must be present
**and** ``action_validate`` must be gone — either half alone is not evidence.

**TC179 — the guard.** ``action_confirm_create_scrap`` opens with
``float_is_zero(self.scrap_qty, precision_rounding=self.product_uom_id.rounding)``
→ ``UserError(_('You can only enter positive quantities.'))`` (v17 ``:98-99``
/ v19 ``:121-122``). Core's ``action_validate`` raises the **identical**
string (``O17 stock/models/stock_scrap.py:198-200`` / ``O19 :213-214``), so a
test that presses the generic Validate proves nothing about F255. This one
calls ``action_confirm_create_scrap`` **by name** (``common.confirm_create_scrap``).
The workbook's ``v19_watch`` asks whether the precision source survives: it
does — ``uom.uom.rounding`` is kept on v19 as a compute declared explicitly
"to ensure compatibility with previous calls to ``uom.rounding``"
(``O19 uom/models/uom_uom.py:39, 62-67``) — and the test pins the field's
existence so a future removal fails loudly.

**TC183 — the Cancelled state.** ``state = fields.Selection(selection_add=
[('cancel', 'Cancelled')], ondelete={'cancel': 'set default'})`` (v17
``models/stock_scrap.py:21`` / v19 ``:40``) on top of core's
``[('draft','Draft'),('done','Done')]`` (``O17 stock/models/stock_scrap.py:50-53``
— **same lines on v19**, so the workbook's "if v19 has introduced a native
cancel value this raises at registry build" is already answered in source:
there is no collision). ``action_cancel`` is ``ensure_one()`` then a write of
``state='cancel'`` (v17 ``:80-82`` with ``skip_validation_check=True``, v19
``:105-111`` plain) — no move, no entry. The Cancel button
(``invisible="state != 'draft'"``, v17 views ``:72-74`` / v19 ``:76-78``) and
the list decorations (``decoration-muted="state == 'cancel'"``,
``decoration-info="state == 'draft'"``, v17 views ``:53-56`` / v19 ``:53-56``,
replacing core's ``decoration-muted="state == 'draft'"`` at ``O17 :139``) are
record-independent arch attributes, and the ``Cancelled`` filter
(``filter_cancel``, ``[('state', '=', 'cancel')]``, inserted after
``mrp.stock_scrap_search_view_inherit_mrp``'s ``filter_done`` anchor at
``O17 mrp/views/stock_scrap_views.xml:39`` — same line on v19) is asserted
both as arch and as a real, token-scoped search.

Expected outcomes
-----------------
* ``TC178`` — **EXPECTED v17 OUTCOME: PASS.** EXPECTED v19 OUTCOME: **FAIL —
  step 5's expectation, raised at the deferred final step** — core's
  ``<group>`` is no longer wrapped in a ``<sheet>``. The wrap
  (``<xpath expr="//form" position="inside"><sheet><xpath
  expr="//form/group" position="move"/></sheet>``, v17 views ``:27-31``)
  existed only to give the tier mixin a ``/form/sheet`` anchor
  (``base_tier_validation/models/tier_validation.py:766-779``) and was
  deliberately not ported (``dto_scrap/views/stock_scrap_views.xml:34-38``);
  core's own v19 ``stock_scrap_form_view2`` has no ``<sheet>`` either
  (``O19 stock/views/stock_scrap_views.xml:146-178``), and v19 additionally
  restricts ``position="move"`` to inner-mode replaces. The workbook
  expectation is immutable (hard rule 2): it is asserted verbatim, with the
  same expected dict, and the v19 baseline FAIL is the recorded result.

  **Only its position moved.** ``ctx.check`` raises
  (``framework/context.py:128-135``), so asserting it inside step 5 aborted
  the run there on v19 and discarded steps 6-14 — including **step 13**, the
  case ("read the rendered arch, not just the effect"), the only assertion
  that catches an F255 rename which loaded cleanly and matched nothing. That
  left this P0 suite producing *zero* F255 evidence on the v19 bench, which
  is the one bench the workbook's "Quick-scrap regression on v19 (NEW, P0)"
  supporting case exists for. Step 5 therefore records its mismatch into
  ``deferred`` and a final, clearly-labelled non-workbook step raises the
  verdict after all fourteen steps have run — the same deferral TC167 uses
  for its BLOCKED verdict, and what AUTOMATION_CONVENTIONS' "Mismatch dicts,
  not assertion loops" asks for. Verdict unchanged (FAIL on v19, PASS on
  v17); evidence larger.
* ``TC179`` — **EXPECTED v17 OUTCOME: PASS.** v19: PASS.
* ``TC183`` — **EXPECTED v17 OUTCOME: PASS.** v19: PASS.

All three open with :func:`common.check_scrap_extension`, the workbook
precondition *"dto_tier_validation_scrap is installed"* implemented as a loud
``ctx.check`` rather than a skip — ``dto_tier_validation_scrap/__manifest__.py:56``
now declares ``installable: False`` and Odoo 17 skips a not-installable module
even when the database row says ``state='installed'``
(``O17 odoo/modules/graph.py:72-75``). See ``docs/WF-022_AUTOMATION_PLAN.md`` §0.

Documented adaptations (hard rule 5)
------------------------------------
1. **No impersonation.** Every workbook step 1 here reads "Log in as TD-U-05
   (Manufacturing User)". The role is incidental to all three controls —
   TC178's own notes say so outright: *"this is a view-level control, not an
   access rule"* — and the labels ``TD-U-04`` / ``TD-U-05`` are test-data
   names, **not** group XML ids (``[UNVERIFIED-1]``: no ``res.groups`` record
   exists in ``dto_stock``, ``dto_scrap`` or ``dto_tier_validation_scrap``;
   ``common.ROLE_GROUPS`` records the mapping used elsewhere in the suite).
   Fixtures must be created and swept with the platform session regardless,
   because ``stock.group_stock_user`` holds no ``perm_unlink`` on
   ``stock.scrap`` (``O17 stock/security/ir.model.access.csv:54`` / ``O19 :41``).
   The mapping is logged at step 1 of each case; the ORM-bypass half (that
   ``action_validate()`` called directly still scraps) belongs to SEC and is
   never exercised here.
2. **"No account.move was created" is a before/after delta** taken inside the
   test, after fixture stock is staged, plus the scrap's own
   ``account_move_ids`` where ``dto_stock`` contributes it. A whole-table
   equality would violate hard rule 5; a delta over a crons-off QA clone with
   a sequential runner does not. Reading ``account_move_ids`` is safe on a
   draft or cancelled scrap and only there: ``_compute_account_move_ids``
   dereferences ``move_ids.account_move_id`` **only** in the ``done`` branch
   (``dto_stock/models/stock_scrap.py:20-24``), and that field does not exist
   on v17 (``O17 stock_account/models/stock_move.py:19`` is the One2many
   ``account_move_ids``). No fixture here is ever validated.
3. **Fixtures are cleaned, against two workbook postconditions.** TC178 says
   "leave the draft scrap; TC180 and TC182 continue from it" and TC183's
   expected final state is "one cancelled scrap". Hard rules 3 and 5 outrank
   both: every fixture is namespaced with ``common.fixture_token()`` and
   removed in a ``finally:`` that can never raise, and TC180 / TC182 build
   their own.

   **One namespaced residue is NOT removable, and is documented rather than
   claimed away.** ``common.add_stock()`` stages stock by *validating* an
   incoming picking (the inventory-count path is blocked by a singleton
   defect in ``dto_cycle_count`` — see that helper's docstring), and a
   picking holding a ``done`` move can never be unlinked
   (``stock.picking.unlink()`` → ``move_ids._action_cancel()``,
   ``O17 stock/models/stock_picking.py:904-907`` →
   ``O17 stock/models/stock_move.py:1778-1780``). The receipt, its move, its
   quants and therefore the fixture products survive; the products are
   **archived** instead of deleted. ``common.sweep_wf022()`` removes rows one
   at a time so that residue cannot take the deletable fixtures with it, and
   returns what it could not remove — ``open_namespace`` logs it. Every
   domain is anchored on the ``WF022`` marker, so no pre-existing business
   record is involved either way.
4. **No fixture is ever validated**, so nothing in this file can leave an
   irreversible done scrap (``You cannot delete a scrap which is done.``,
   ``O17 stock/models/stock_scrap.py:107-110``). TC183 step 9 therefore
   asserts the Cancel button's record-independent ``invisible`` modifier
   instead of opening a live done scrap — which it must not do anyway:
   ``action_cancel`` carries **no state guard**, so touching a live done
   record is one mis-step away from writing it to ``cancel``.
5. **No ``readonly="1"`` is ever hard-coded.** On v17 ``TierValidation.get_view``
   rewrites every field node's modifier to ``f"({old}) or ({new})"``
   (``base_tier_validation/models/tier_validation.py:780-788``); this file
   asserts no field-level readonly at all, and where a sibling case needs one
   it goes through ``common.readonly_is_absolute``.
"""
import ast

from adapters.base import OdooRPCError
from framework.fg_common import list_tag
from framework.registry import test_case
from tests.wf022.common import (CANCEL_BUTTON, CANCEL_BUTTON_INVISIBLE,
                                CANCEL_BUTTON_STRING, ERROR_POSITIVE_QTY,
                                EXPECTED_STATE_SELECTION, FILTER_CANCEL,
                                FILTER_CANCEL_DOMAIN, JOURNAL_ENTRIES_FIELD,
                                LIST_DECORATION_INFO, LIST_DECORATION_MUTED,
                                MODULE_TIER_SCRAP, QUICK_BUTTON_CORE,
                                QUICK_BUTTON_RENAMED, QUICK_BUTTON_STRING,
                                ROLE_GROUPS, STATE_CANCEL, STATE_CANCEL_LABEL,
                                STATE_DONE, STATE_DRAFT, VIEW_FULL_FORM,
                                VIEW_QUICK_FORM, WORKFLOW, WORKFLOW_NAME,
                                add_stock, buttons_named, cancel_scrap,
                                check_scrap_extension, confirm_create_scrap,
                                drop_scraps, field_node, fields_get,
                                fixture_token, journal_entries_of, m2o_id,
                                make_bom, make_mo, make_picking, make_product,
                                make_scrap, moves_of_scrap, on_hand_at,
                                open_namespace, parse_arch, read_scrap,
                                require_mrp, scrap_arch, search_count,
                                state_selection, stock_location, sweep_wf022,
                                trace, view_arch, write_scrap)

#: ``OdooRPC.call`` prefixes every server fault with ``"<model>.<method>
#: failed: "`` (adapters/base.py:176-178). The workbook demands the message
#: *exactly*, so the prefix is stripped before comparing — never the message.
_RPC_PREFIX = " failed: "


def _error_tail(message) -> str:
    """The server's own message, with the transport's prefix removed."""
    text = str(message)
    if _RPC_PREFIX in text:
        return text.split(_RPC_PREFIX, 1)[1].strip()
    return text.strip()


def _press_validate(rpc, scrap_id):
    """Press the quick dialog's renamed Validate; return (raised, msg, action).

    Defined here rather than taken from ``common.expect_error``, which is the
    right shape for a pure negative case but discards the return value —
    TC178 step 8 and TC179 step 9 both assert the returned ``act_window``, and
    TC179 step 7 asserts that nothing was returned at all. Never raises a bare
    AssertionError: the caller ``ctx.check``s the tuple.
    """
    try:
        return False, "", confirm_create_scrap(rpc, scrap_id)
    except OdooRPCError as exc:
        return True, _error_tail(exc), None


def _account_move_count(rpc) -> int:
    """Whole-table ``account.move`` count, or 0 when accounting is absent.

    Only ever used as a before/after delta inside one test (see the module
    docstring, adaptation 2) — never as a standalone "exactly N" claim.
    """
    if not rpc.model_exists("account.move"):
        return 0
    return search_count(rpc, "account.move", [])


def _scrap_entry_ids(rpc, scrap_id) -> list:
    """The scrap's own ``account_move_ids``, or [] when dto_stock is absent.

    Safe on a draft or cancelled scrap only — see the module docstring,
    adaptation 2.
    """
    if not rpc.field_exists("stock.scrap", JOURNAL_ENTRIES_FIELD):
        return []
    return journal_entries_of(rpc, scrap_id)


def _dialog_shape(action, product_id) -> dict:
    """The observable shape of a ``button_scrap()`` return value.

    ``mrp.production.button_scrap`` (``O17 mrp_production.py:2160-2173`` /
    ``O19 :2406-2419``) and ``stock.picking.button_scrap``
    (``O17 stock_picking.py:1563-1579`` / ``O19 :1900-1916``) differ only in
    that the picking one also sets ``view_id``; both resolve
    ``stock.stock_scrap_form_view2``, both are ``target: 'new'``, and both
    carry the offerable products in ``context['product_ids']``.
    """
    views = action.get("views") or []
    first = list(views[0]) if views else [None, None]
    context = action.get("context") or {}
    return {
        "type": action.get("type"),
        "res_model": action.get("res_model"),
        "target": action.get("target"),
        "form_view_id": first[0],
        "offers_the_component": product_id in (context.get("product_ids") or []),
    }


def _full_form_shape(action) -> dict:
    """The observable shape of ``action_confirm_create_scrap``'s act_window
    (v17 ``models/stock_scrap.py:101-109`` / v19 ``:124-132``)."""
    if not isinstance(action, dict):
        return {"type": None, "res_model": None, "res_id": None,
                "view_mode": None, "target": None, "name": None,
                "form_view_id": None}
    views = action.get("views") or []
    first = list(views[0]) if views else [None, None]
    return {
        "type": action.get("type"),
        "res_model": action.get("res_model"),
        "res_id": action.get("res_id"),
        "view_mode": action.get("view_mode"),
        "target": action.get("target"),
        "name": action.get("name"),
        "form_view_id": first[0],
    }


def _expected_full_form(scrap_id, full_form_view_id) -> dict:
    """What the renamed button must return — every key read from source."""
    return {
        "type": "ir.actions.act_window",
        "res_model": "stock.scrap",
        "res_id": scrap_id,
        "view_mode": "form",
        "target": "current",
        # _('Scrap Products') — v17 :102 / v19 :125, the same literal the core
        # footer button carries as its label.
        "name": QUICK_BUTTON_STRING,
        "form_view_id": full_form_view_id,
    }


def _button_names(root) -> list:
    """Every ``<button @name>`` in document order."""
    return [node.get("name") for node in root.iter("button") if node.get("name")]


def _renamed_button_facts(root) -> dict:
    """TC178 step 13, as one mismatch dict: the rename applied, and the core
    name is *gone* from the rendered arch."""
    renamed = buttons_named(root, QUICK_BUTTON_RENAMED)
    return {
        "action_confirm_create_scrap_buttons": len(renamed),
        "action_validate_buttons": len(buttons_named(root, QUICK_BUTTON_CORE)),
        "label": renamed[0].get("string") if renamed else None,
    }


def _role_note(role: str) -> str:
    """One log line recording the workbook role and why it is not assumed."""
    return (f"workbook role {role}: the label is test data, not a group XML id "
            f"[UNVERIFIED-1]; common.ROLE_GROUPS maps it to "
            f"{ROLE_GROUPS.get(role, [])}. This control is view-level, not an "
            f"access rule (TC178 notes), and fixtures must be created and "
            f"swept with the platform session because stock.group_stock_user "
            f"holds no perm_unlink on stock.scrap "
            f"(O17 stock/security/ir.model.access.csv:54).")


def _state_label(rpc, value):
    """The label ``stock.scrap.state`` renders for a value, from fields_get."""
    for pair in state_selection(rpc):
        if pair and pair[0] == value:
            return pair[1]
    return None


@test_case(
    id="TEST-WF022-TC178",
    name="Validate in the quick-scrap dialog opens the full scrap form "
         "instead of scrapping",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module=MODULE_TIER_SCRAP,
    priority="P0", kind="HYBRID", order=22178,
    description="The quick dialog's footer button is bound to "
                "action_confirm_create_scrap and not to action_validate in "
                "the rendered arch; pressing it returns an act_window onto "
                "the full form with target 'current' and moves nothing — "
                "from a manufacturing order and from a transfer alike.",
    traceability=trace("DATAONE-TC178"))
def test_tc178(ctx):
    rpc = ctx.adapter.rpc
    require_mrp(ctx)
    open_namespace(ctx)
    scrap_ids = []
    #: (name, expected, actual) triples whose verdict is raised by the final
    #: step instead of aborting the workbook step that produced them — see
    #: step 5.
    deferred = []
    try:
        with ctx.step("Log in as TD-U-05 and open the confirmed MO."):
            # The workbook precondition, as a loud assertion — see the module
            # docstring and docs/WF-022_AUTOMATION_PLAN.md §0.
            check_scrap_extension(ctx)
            ctx.log(_role_note("TD-U-05"))
            component = make_product(ctx, "TD-P-04", standard_price=5.0)
            finished = make_product(ctx, "TD-P-01", standard_price=25.0)
            bom_id = make_bom(rpc, finished, [(component, 1.0)])
            source = stock_location(rpc)
            add_stock(ctx, component, source, 10.0)
            mo_id = make_mo(ctx, finished, bom_id, qty=1.0)
            # A fixture sanity check, not a workbook expectation: mrp.production
            # .state is a compute (O17 mrp_production.py:525-555) whose exact
            # value after action_confirm depends on qty_producing, so the
            # assertion is "confirmed, i.e. neither draft nor cancelled".
            mo_state = rpc.read("mrp.production", [mo_id], ["state"])[0]["state"]
            ctx.check_true("the manufacturing order is confirmed",
                           mo_state not in ("draft", "cancel"),
                           f"mrp.production.state = {mo_state!r}")

        with ctx.step("Record on_hand_before for TD-P-04 at the source "
                      "location."):
            on_hand_before = on_hand_at(rpc, component, source)
            moves_before = _account_move_count(rpc)
            ctx.check_true("TD-P-04 has stock at the source location",
                           on_hand_before > 0.0,
                           f"on hand at location {source} = {on_hand_before}")
            ctx.log(f"account.move rows before the dialog: {moves_before} "
                    f"(baseline for step 12, taken after fixture stock was "
                    f"staged)")

        with ctx.step("Press Scrap."):
            dialog = rpc.call("mrp.production", "button_scrap", [mo_id])

        with ctx.step("Assert the quick-scrap dialog opens, rendered from "
                      "stock.stock_scrap_form_view2."):
            quick_view_id = rpc.ref(VIEW_QUICK_FORM)
            ctx.check("the MO's Scrap button opens stock_scrap_form_view2 as "
                      "a dialog offering TD-P-04",
                      {"type": "ir.actions.act_window",
                       "res_model": "stock.scrap",
                       "target": "new",
                       "form_view_id": quick_view_id,
                       "offers_the_component": True},
                      _dialog_shape(dialog, component))

        with ctx.step("Assert core's <group> is wrapped in a <sheet> (the "
                      "structural inherit applied)."):
            # EXPECTED v19 OUTCOME: FAIL — the wrap was deliberately not
            # ported (dto_scrap/views/stock_scrap_views.xml:34-38), and core's
            # own v19 stock_scrap_form_view2 is <form><group>…</group>
            # <footer>…</footer></form> with no <sheet> anywhere
            # (O19 stock/views/stock_scrap_views.xml:146-178).
            #
            # The expectation is IMMUTABLE (hard rule 2) and is asserted
            # verbatim — but its VERDICT is deferred to the last step of this
            # test. ctx.check RAISES on mismatch (framework/context.py:128-135),
            # so asserting it here would abort the run at step 5 on v19 and
            # discard steps 6-14 — step 13 among them, which the workbook
            # calls the case and which is the only assertion that catches an
            # F255 rename that loaded cleanly and matched nothing. On the v19
            # bench that would leave this P0 suite with zero evidence on F255.
            # Deferring is the same pattern TC167 uses for its BLOCKED verdict
            # (tests/wf022/test_scrap_valuation.py, the ``blockers`` list) and
            # is what AUTOMATION_CONVENTIONS' "Mismatch dicts, not assertion
            # loops … so a failure reports all of them" asks for. The verdict
            # is identical — FAIL on v19 — only the evidence is larger.
            quick_root = parse_arch(view_arch(ctx, VIEW_QUICK_FORM, "form"))
            sheet_expected = {"has_sheet": True, "group_inside_sheet": True}
            sheet_actual = {
                "has_sheet": quick_root.find(".//sheet") is not None,
                "group_inside_sheet":
                    bool(quick_root.findall(".//sheet/group"))}
            ctx.log(f"<sheet> facts on this target: {sheet_actual!r}; the "
                    f"workbook expects {sheet_expected!r}. The verdict is "
                    f"raised at the deferred step at the end of this test so "
                    f"steps 6-14 still produce evidence.")
            if sheet_actual != sheet_expected:
                deferred.append(
                    ("the quick dialog wraps core's <group> in a <sheet> "
                     "(dto_tier_validation_scrap/views/"
                     "stock_scrap_views.xml:27-31)",
                     sheet_expected, sheet_actual))

        with ctx.step("Set the product to TD-P-04 and the quantity to 1."):
            scrap_id = make_scrap(ctx, component, qty=1.0, location_id=source,
                                  values={"production_id": mo_id})
            scrap_ids.append(scrap_id)
            row = read_scrap(rpc, scrap_id)
            ctx.check("the dialog's record is a draft scrap of TD-P-04, "
                      "quantity 1",
                      {"product": component, "scrap_qty": 1.0,
                       "state": STATE_DRAFT},
                      {"product": m2o_id(row["product_id"]),
                       "scrap_qty": row["scrap_qty"], "state": row["state"]})

        with ctx.step("Press Validate."):
            raised, message, action = _press_validate(rpc, scrap_id)
            ctx.check("the dialog's Validate returns an action instead of "
                      "raising",
                      {"raised": False, "returned_an_action": True},
                      {"raised": raised,
                       "returned_an_action": isinstance(action, dict)})
            ctx.log(f"MO path error message (expected empty): {message!r}")

        with ctx.step("Assert the full scrap form (stock.stock_scrap_form_view) "
                      "opens on the same stock.scrap record, target: "
                      "'current'."):
            full_view_id = rpc.ref(VIEW_FULL_FORM)
            ctx.check("the act_window is the full form on this scrap, "
                      "target 'current'",
                      _expected_full_form(scrap_id, full_view_id),
                      _full_form_shape(action))

        with ctx.step("Assert the scrap's state is still draft."):
            ctx.check("nothing was validated — the scrap is still draft",
                      STATE_DRAFT, read_scrap(rpc, scrap_id)["state"])

        with ctx.step("Assert no stock.move was created for it."):
            ctx.check("the scrap has no stock.move",
                      [], moves_of_scrap(rpc, scrap_id))

        with ctx.step("Assert on_hand for TD-P-04 is unchanged from step 2."):
            ctx.check("on hand at the source location is unchanged",
                      on_hand_before, on_hand_at(rpc, component, source))

        with ctx.step("Assert no account.move was created."):
            ctx.check("no journal entry exists, by table delta and by the "
                      "scrap's own account_move_ids",
                      {"account_move_delta": 0, "scrap_journal_entries": []},
                      {"account_move_delta":
                           _account_move_count(rpc) - moves_before,
                       "scrap_journal_entries":
                           _scrap_entry_ids(rpc, scrap_id)})

        with ctx.step("Assert the button on the quick dialog is bound to "
                      "action_confirm_create_scrap, not to action_validate — "
                      "read the rendered arch, not just the effect."):
            # THE case. The inherit can load cleanly and match nothing; only
            # the rendered arch distinguishes that from a working rename.
            ctx.check("the rendered stock_scrap_form_view2 carries "
                      "action_confirm_create_scrap and no action_validate",
                      {"action_confirm_create_scrap_buttons": 1,
                       "action_validate_buttons": 0,
                       "label": QUICK_BUTTON_STRING},
                      _renamed_button_facts(quick_root))

        with ctx.step("Repeat steps 3-13 starting from a picking instead of "
                      "an MO, and assert the same outcome."):
            picking_id = make_picking(ctx, component, qty=1.0, code="incoming")
            pick_on_hand_before = on_hand_at(rpc, component, source)
            pick_moves_before = _account_move_count(rpc)

            pick_dialog = rpc.call("stock.picking", "button_scrap",
                                   [picking_id])
            ctx.check("the transfer's Scrap button opens the same dialog "
                      "offering TD-P-04",
                      {"type": "ir.actions.act_window",
                       "res_model": "stock.scrap",
                       "target": "new",
                       "form_view_id": quick_view_id,
                       "offers_the_component": True},
                      _dialog_shape(pick_dialog, component))

            pick_scrap_id = make_scrap(ctx, component, qty=1.0,
                                       location_id=source,
                                       values={"picking_id": picking_id})
            scrap_ids.append(pick_scrap_id)
            p_raised, p_message, p_action = _press_validate(rpc, pick_scrap_id)
            ctx.check("from a transfer, Validate is a navigation action with "
                      "no side effect",
                      {"raised": False,
                       "action": _expected_full_form(pick_scrap_id,
                                                     full_view_id),
                       "state": STATE_DRAFT,
                       "stock_moves": [],
                       "on_hand": pick_on_hand_before,
                       "account_move_delta": 0,
                       "scrap_journal_entries": []},
                      {"raised": p_raised,
                       "action": _full_form_shape(p_action),
                       "state": read_scrap(rpc, pick_scrap_id)["state"],
                       "stock_moves": moves_of_scrap(rpc, pick_scrap_id),
                       "on_hand": on_hand_at(rpc, component, source),
                       "account_move_delta":
                           _account_move_count(rpc) - pick_moves_before,
                       "scrap_journal_entries":
                           _scrap_entry_ids(rpc, pick_scrap_id)})
            ctx.log(f"transfer path error message (expected empty): "
                    f"{p_message!r}")

        with ctx.step("Deferred verdict — step 5: the structural <sheet> "
                      "inherit."):
            # Not a workbook step: the workbook's fourteen steps are all
            # above. This raises step 5's verdict now that steps 6-14 have
            # produced their evidence. EXPECTED v17 OUTCOME: PASS (nothing
            # deferred). EXPECTED v19 OUTCOME: FAIL here — the expectation is
            # unchanged, only its position is.
            if not deferred:
                ctx.log("step 5 matched on this target; nothing deferred.")
            for name, expected, actual in deferred:
                ctx.check(name, expected, actual)
    finally:
        # The workbook's postcondition asks for the draft scrap to be left for
        # TC180/TC182. Hard rules 3 and 5 outrank it — see the module
        # docstring, adaptation 3. This block can never raise.
        try:
            drop_scraps(rpc, scrap_ids)
            sweep_wf022(rpc)
        except Exception:  # noqa: BLE001
            pass


@test_case(
    id="TEST-WF022-TC179",
    name="Validate with a zero quantity raises the exact positive-quantity "
         "error",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module=MODULE_TIER_SCRAP,
    priority="P2", kind="API", order=22179,
    description="action_confirm_create_scrap, called by name, raises exactly "
                "'You can only enter positive quantities.' on a zero-quantity "
                "scrap, returns no action and moves nothing; at quantity 1 the "
                "same call returns the full-form act_window.",
    traceability=trace("DATAONE-TC179"))
def test_tc179(ctx):
    rpc = ctx.adapter.rpc
    require_mrp(ctx)
    open_namespace(ctx)
    scrap_ids = []
    try:
        with ctx.step("Log in as TD-U-05 and open the MO."):
            check_scrap_extension(ctx)
            ctx.log(_role_note("TD-U-05"))
            component = make_product(ctx, "TD-P-04", standard_price=5.0)
            finished = make_product(ctx, "TD-P-01", standard_price=25.0)
            bom_id = make_bom(rpc, finished, [(component, 1.0)])
            source = stock_location(rpc)
            add_stock(ctx, component, source, 5.0)
            mo_id = make_mo(ctx, finished, bom_id, qty=1.0)
            mo_state = rpc.read("mrp.production", [mo_id], ["state"])[0]["state"]
            ctx.check_true("the manufacturing order is confirmed",
                           mo_state not in ("draft", "cancel"),
                           f"mrp.production.state = {mo_state!r}")

        with ctx.step("Press Scrap."):
            dialog = rpc.call("mrp.production", "button_scrap", [mo_id])
            ctx.check("the MO's Scrap button opens stock_scrap_form_view2 as "
                      "a dialog offering TD-P-04",
                      {"type": "ir.actions.act_window",
                       "res_model": "stock.scrap",
                       "target": "new",
                       "form_view_id": rpc.ref(VIEW_QUICK_FORM),
                       "offers_the_component": True},
                      _dialog_shape(dialog, component))

        with ctx.step("Set the product to TD-P-04 and leave the quantity "
                      "at 0."):
            scrap_id = make_scrap(ctx, component, qty=0.0, location_id=source,
                                  values={"production_id": mo_id})
            scrap_ids.append(scrap_id)
            # scrap_qty is an editable stored compute (default 1.0,
            # O17 stock/models/stock_scrap.py:47-49 / O19 :47-49); the explicit
            # write makes the zero unambiguous rather than relying on create()
            # marking the compute as set.
            write_scrap(rpc, scrap_id, {"scrap_qty": 0.0})
            row = read_scrap(rpc, scrap_id)
            moves_before = _account_move_count(rpc)
            ctx.check("the draft scrap holds TD-P-04 at quantity 0",
                      {"product": component, "scrap_qty": 0.0,
                       "state": STATE_DRAFT},
                      {"product": m2o_id(row["product_id"]),
                       "scrap_qty": row["scrap_qty"], "state": row["state"]})
            # The workbook's v19_watch: the guard reads
            # precision_rounding=self.product_uom_id.rounding (v17 :98 /
            # v19 :121). uom.uom.rounding survives on v19 as a compute kept
            # "to ensure compatibility with previous calls to uom.rounding"
            # (O19 uom/models/uom_uom.py:39, 62-67).
            ctx.check("uom.uom still carries the rounding the guard reads",
                      True, rpc.field_exists("uom.uom", "rounding"))

        with ctx.step("Press Validate."):
            # BY NAME. Core's action_validate raises the identical string
            # (O17 stock/models/stock_scrap.py:198-200 / O19 :213-214), so the
            # generic Validate path would prove nothing about F255.
            raised, message, action = _press_validate(rpc, scrap_id)

        with ctx.step("Assert a UserError is raised."):
            ctx.check("action_confirm_create_scrap raised", True, raised)

        with ctx.step("Assert the message is exactly You can only enter "
                      "positive quantities."):
            ctx.check("the server message, verbatim", ERROR_POSITIVE_QTY,
                      message)

        with ctx.step("Assert the full scrap form did not open."):
            ctx.check("no act_window was returned by the raising call",
                      None, action)

        with ctx.step("Assert no stock.move and no account.move were "
                      "created."):
            ctx.check("the rejected scrap moved nothing",
                      {"stock_moves": [], "account_move_delta": 0,
                       "scrap_journal_entries": []},
                      {"stock_moves": moves_of_scrap(rpc, scrap_id),
                       "account_move_delta":
                           _account_move_count(rpc) - moves_before,
                       "scrap_journal_entries":
                           _scrap_entry_ids(rpc, scrap_id)})

        with ctx.step("Set the quantity to 1 and press Validate again; assert "
                      "the full form now opens (the control case)."):
            write_scrap(rpc, scrap_id, {"scrap_qty": 1.0})
            raised2, message2, action2 = _press_validate(rpc, scrap_id)
            ctx.check("at quantity 1 the same call returns the full-form "
                      "act_window",
                      {"raised": False,
                       "action": _expected_full_form(scrap_id,
                                                     rpc.ref(VIEW_FULL_FORM)),
                       "state": STATE_DRAFT},
                      {"raised": raised2,
                       "action": _full_form_shape(action2),
                       "state": read_scrap(rpc, scrap_id)["state"]})
            ctx.log(f"control-case error message (expected empty): "
                    f"{message2!r}")

        with ctx.step("Note explicitly that this guard exists only on this "
                      "path — the full form relies on core validation — and "
                      "record that limit."):
            # Documentation, not an assertion (the workbook says so).
            ctx.log("BR-2 is enforced in action_confirm_create_scrap only "
                    "(dto_tier_validation_scrap/models/stock_scrap.py:96-99, "
                    "dto_scrap/models/stock_scrap.py:113-122). A scrap raised "
                    "directly from Inventory > Operations > Scrap (WF-022 A2) "
                    "never passes through it: the full form's header button is "
                    "core's action_validate (O17 stock/views/"
                    "stock_scrap_views.xml:30), whose own guard is the "
                    "identical string (O17 stock/models/stock_scrap.py:198-200) "
                    "but which then goes on to scrap. The rename applies to "
                    "stock.stock_scrap_form_view2 only.")
    finally:
        try:
            drop_scraps(rpc, scrap_ids)
            sweep_wf022(rpc)
        except Exception:  # noqa: BLE001
            pass


@test_case(
    id="TEST-WF022-TC183",
    name="The Cancelled state is reachable from Draft and is terminal",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module=MODULE_TIER_SCRAP,
    priority="P2", kind="HYBRID", order=22183,
    description="selection_add appends ('cancel','Cancelled') after core's "
                "draft/done; action_cancel moves a draft scrap to Cancelled "
                "with no stock.move, no journal entry and no stock change; the "
                "Cancel button's invisible modifier, the muted list decoration "
                "and the Cancelled filter all render, and no reset-to-draft "
                "affordance exists.",
    traceability=trace("DATAONE-TC183"))
def test_tc183(ctx):
    rpc = ctx.adapter.rpc
    open_namespace(ctx)
    scrap_ids = []
    try:
        with ctx.step("Log in as TD-U-05 and open the draft scrap."):
            check_scrap_extension(ctx)
            ctx.log(_role_note("TD-U-05"))
            product = make_product(ctx, "TD-P-04", standard_price=7.0)
            source = stock_location(rpc)
            add_stock(ctx, product, source, 4.0)
            scrap_id = make_scrap(ctx, product, qty=1.0, location_id=source)
            scrap_ids.append(scrap_id)
            on_hand_before = on_hand_at(rpc, product, source)
            moves_before = _account_move_count(rpc)
            # The workbook's second precondition ("a stock.scrap in done
            # exists") is recorded read-only: step 9 is an arch fact, and no
            # live done scrap is ever opened or written — action_cancel has no
            # state guard (see the module docstring, adaptation 4).
            ctx.log(f"done scraps on this target (read-only, not asserted): "
                    f"{search_count(rpc, 'stock.scrap', [('state', '=', STATE_DONE)])}")
            ctx.check("the fixture scrap is draft", STATE_DRAFT,
                      read_scrap(rpc, scrap_id)["state"])

        with ctx.step("Assert a Cancel button is visible next to Validate."):
            form_root = parse_arch(scrap_arch(ctx, "form"))
            cancel_nodes = buttons_named(form_root, CANCEL_BUTTON)
            names = _button_names(form_root)
            adjacent = (CANCEL_BUTTON in names and QUICK_BUTTON_CORE in names
                        and names.index(CANCEL_BUTTON) + 1
                        == names.index(QUICK_BUTTON_CORE))
            ctx.check("the full form carries Cancel immediately before "
                      "Validate, hidden outside draft",
                      {"present": True, "string": CANCEL_BUTTON_STRING,
                       "invisible": CANCEL_BUTTON_INVISIBLE,
                       "immediately_before_validate": True},
                      {"present": bool(cancel_nodes),
                       "string": (cancel_nodes[0].get("string")
                                  if cancel_nodes else None),
                       "invisible": (cancel_nodes[0].get("invisible")
                                     if cancel_nodes else None),
                       "immediately_before_validate": adjacent})

        with ctx.step("Press Cancel."):
            cancel_scrap(rpc, scrap_id)

        with ctx.step("Assert scrap.state == 'cancel' and the form reads "
                      "Cancelled."):
            row = read_scrap(rpc, scrap_id)
            ctx.check("the scrap is Cancelled",
                      {"state": STATE_CANCEL, "label": STATE_CANCEL_LABEL},
                      {"state": row["state"],
                       "label": _state_label(rpc, row["state"])})

        with ctx.step("Assert no stock.move and no account.move were "
                      "created."):
            ctx.check("cancelling moved nothing",
                      {"stock_moves": [], "account_move_delta": 0,
                       "scrap_journal_entries": []},
                      {"stock_moves": moves_of_scrap(rpc, scrap_id),
                       "account_move_delta":
                           _account_move_count(rpc) - moves_before,
                       "scrap_journal_entries":
                           _scrap_entry_ids(rpc, scrap_id)})

        with ctx.step("Assert on-hand at the source location is unchanged."):
            ctx.check("on hand at the source location is unchanged",
                      on_hand_before, on_hand_at(rpc, product, source))

        with ctx.step("Open the scrap list and assert the cancelled row "
                      "renders muted."):
            # The list root tag is 'tree' on v17 and 'list' on v19; both the
            # fetch and the tag go through the adapter (fg_common.form_arch /
            # list_tag), never an if-version.
            list_root = parse_arch(scrap_arch(ctx, "tree"))
            state_field = field_node(list_root, "state")
            ctx.check("the list decorates a cancelled row muted and a draft "
                      "row info (overriding core's muted-on-draft, "
                      "O17 stock/views/stock_scrap_views.xml:139)",
                      {"root_tag": list_tag(ctx),
                       "decoration-muted": LIST_DECORATION_MUTED,
                       "decoration-info": LIST_DECORATION_INFO},
                      {"root_tag": list_root.tag,
                       "decoration-muted":
                           (state_field.get("decoration-muted")
                            if state_field is not None else None),
                       "decoration-info":
                           (state_field.get("decoration-info")
                            if state_field is not None else None)})

        with ctx.step("Apply the Cancelled filter and assert the row is found "
                      "by it."):
            search_root = parse_arch(scrap_arch(ctx, "search"))
            filters = search_root.findall(f".//filter[@name='{FILTER_CANCEL}']")
            domain = None
            if filters and filters[0].get("domain"):
                try:
                    domain = [tuple(clause) for clause
                              in ast.literal_eval(filters[0].get("domain"))]
                except (ValueError, SyntaxError):
                    domain = filters[0].get("domain")
            # Scoped by this execution's token so live cancelled scraps cannot
            # leak into the result (hard rule 5).
            found = rpc.search("stock.scrap",
                               list(FILTER_CANCEL_DOMAIN)
                               + [("origin", "like", fixture_token())])
            ctx.check("the Cancelled filter exists with its source domain and "
                      "returns the cancelled fixture",
                      {"filter_present": True,
                       "string": STATE_CANCEL_LABEL,
                       "domain": [tuple(c) for c in FILTER_CANCEL_DOMAIN],
                       "token_scoped_hits": [scrap_id]},
                      {"filter_present": bool(filters),
                       "string": (filters[0].get("string")
                                  if filters else None),
                       "domain": domain,
                       "token_scoped_hits": found})

        with ctx.step("Open the done scrap and assert the Cancel button is "
                      "not visible (invisible=\"state != 'draft'\")."):
            # Asserted as the record-independent modifier, so no live done
            # scrap is opened or written — see the module docstring,
            # adaptation 4.
            cancel_nodes = buttons_named(form_root, CANCEL_BUTTON)
            ctx.check("the Cancel button's invisible modifier hides it for "
                      "every state other than draft, done included",
                      CANCEL_BUTTON_INVISIBLE,
                      (cancel_nodes[0].get("invisible")
                       if cancel_nodes else None))

        with ctx.step("Attempt to move the cancelled scrap back to draft "
                      "through the UI and assert there is no such affordance "
                      "— the state is terminal."):
            draft_buttons = sorted({node.get("name")
                                    for root in (form_root, list_root)
                                    for node in root.iter("button")
                                    if "draft" in (node.get("name") or "").lower()})
            state_attrs = fields_get(rpc, "stock.scrap", ["state"],
                                     attributes=["readonly"])
            ctx.check("no reset-to-draft button exists on the form or the "
                      "list, and state is readonly at the ORM "
                      "(O17 stock/models/stock_scrap.py:50-53)",
                      {"buttons_mentioning_draft": [], "state_readonly": True},
                      {"buttons_mentioning_draft": draft_buttons,
                       "state_readonly":
                           bool(state_attrs.get("state", {}).get("readonly"))})

        with ctx.step("On the v19 bench, assert the registry builds with the "
                      "selection_add present, and assert an existing row "
                      "holding state='cancel' reads correctly in the list and "
                      "the form."):
            # The workbook's open question is already answered in source: core
            # state is draft/done on BOTH versions (O17 stock/models/
            # stock_scrap.py:50-53, same lines on O19), so the selection_add
            # appends without collision. Pinning it here makes a future point
            # release that introduces a native 'cancel' fail loudly instead of
            # at registry build.
            list_fields = [name for name in
                           {node.get("name") for node in list_root.iter("field")
                            if node.get("name")}]
            readable = sorted(fields_get(rpc, "stock.scrap", list_fields,
                                         attributes=["type"]))
            rows = rpc.read("stock.scrap", [scrap_id], readable)
            ctx.check("state offers draft/done/cancel and the cancelled row "
                      "reads back through the list's own fields",
                      {"selection": EXPECTED_STATE_SELECTION,
                       "rows_read": 1, "state": STATE_CANCEL},
                      {"selection": state_selection(rpc),
                       "rows_read": len(rows),
                       "state": rows[0]["state"] if rows else None})
    finally:
        # The workbook's expected final state is "one cancelled scrap"; hard
        # rules 3 and 5 outrank it (module docstring, adaptation 3). Never
        # raises.
        try:
            drop_scraps(rpc, scrap_ids)
            sweep_wf022(rpc)
        except Exception:  # noqa: BLE001
            pass
