"""DATAONE-WF-011 — delivery security and the forced backorder: TC158-TC161.

Four cases about two control surfaces. Abbreviations: ``DTO`` =
``D:/Projects/dataone/DTO-Odoo`` (project addons, read on branch **main** —
the working tree is on ``UAT``, which already carries the v19 port), ``O17`` =
``D:/Projects/dataone/odoo-17.0``, ``O19`` = ``D:/Projects/odoo-19.0``.

What this file proves
---------------------
**TC158 / TC159 — F179, both directions.**
``DTO project-addons/dto_mrp_account/models/stock_picking.py:8-15`` overrides
``button_validate`` and raises **before** ``super()``::

    def button_validate(self):
        operation_type = self.env.ref('stock.picking_type_out')            # :9
        if not self.user_has_groups('dto_mrp_account.'
                                    'group_validate_delivery_orders') \
                and self.picking_type_id.id == operation_type.id:          # :10
            raise UserError("Only users in the 'Validate Delivery Orders' "
                            "group can validate this picking.")            # :11
        res = super(StockPicking, self).button_validate()                  # :13

Three facts follow from those four lines and every one of them is asserted:

1. The message is **not** wrapped in ``_()``, so it is asserted byte-exact
   (``common.ERROR_VALIDATE_GROUP``), never as a substring.
2. The raise is before ``super()``, so TC158's steps 7-10 (state still
   ``assigned``, ``date_done`` unset, no ``account.move``, no ``done`` move
   line) are **structural** consequences, not timing luck. One neighbour is
   asserted with them: ``3rd-addons/stock_picking_auto_create_lot/models/
   stock_picking.py:66-68`` calls the private ``_set_auto_lot()`` *before*
   ``super().button_validate()``, so a lot name could have been written ahead
   of the refusal — ``move_line_ids.lot_name`` is checked to have stayed
   empty.
3. The guard compares against the **single** operation type
   ``stock.picking_type_out``, so both cases assert the fixture picking's type
   is exactly that xmlid before Validate is pressed. Without it a "pass" could
   come from F179's unprotected second-warehouse path, which is the workbook's
   own open question (TC158 Notes) rather than a behaviour under test.

The negative case **must impersonate**: ``DTO project-addons/dto_mrp_account/
data/server_actions.xml:18-24`` seeds the group with ``base.user_root`` and
``base.user_admin``, so the platform's own ``admin`` session passes the check.
Both cases therefore drive a second authenticated session
(``common.session_as``) for a disposable user built with ``(6, 0, ids)`` — a
full replace — so an interrupted earlier run cannot leave stray membership
behind (``common.ensure_user``).

TC158 step 3 ("the Validate button is visible — the control is in Python, not
in the view") is read from the arch ``get_view`` renders **for that user**.
Core ships two Validate buttons, both ``groups="stock.group_stock_user"``
(``O17 addons/stock/views/stock_picking_views.xml:146-147``; ``O19 :119-120``,
byte-identical), and ``ir.ui.view`` pops the ``groups`` attribute after
evaluating it and drops the node when the user is not a member
(``O17 odoo/addons/base/models/ir_ui_view.py:1011-1012``). A node that
survives into that user's arch is therefore proof the user may see it, and the
absence of any delivery-group restriction on it is proof the control is
Python-side only.

TC159's isolation is source-correct: ``DTO project-addons/dto_sale_stock/
models/stock_picking.py:12-22`` auto-invoices and posts inside ``_action_done``
for ``order_type in ('project', 'inventory', 'cost_center')`` only, so the
``buy`` order every fixture here uses (``common.ISOLATED_ORDER_TYPE``) produces
no invoice and a security verdict can never fail for an accounting reason.

**TC160 — F180, the inverted group.**
``DTO project-addons/dto_mrp_account/models/stock_picking.py:17-21``::

    def write(self, vals):
        if self.env.user.has_group('dto_mrp_account.'
                                   'group_transfers_read'):                # :18
            raise UserError('You are not allowed to change Transfers '
                            'records.')                                    # :19
        return super().write(vals)                                         # :21

No ``vals`` inspection, no picking-type test, no ``ir.rule`` anywhere
(grep-verified across ``dto_mrp_account``) — so steps 6 and 8 ("any field",
"not limited to outgoing") are structural, and step 10 is the visible tip of
E4: ``stock.picking._action_done`` writes the picking itself
(``O17 addons/stock/models/stock_picking.py:994`` —
``self.write({'date_done': …, 'priority': '0'})``), inside the same
transaction, so validation cannot complete for a member. The group record
carries **no** seeded users (``data/server_actions.xml:32-35``), which is the
workbook's REMOVE-candidate open question; it is logged, never asserted.

**TC161 — F042, the forced backorder.**
``DTO project-addons/dto_sale_stock/wizard/stock_backorder_confirmation_views
.xml:8-10`` sets ``invisible="1"`` on ``//button[@name=
'process_cancel_backorder']`` inside ``stock.view_backorder_confirmation``.
Core still ships that button on both versions
(``O17 addons/stock/wizard/stock_backorder_confirmation_views.xml:43``;
``O19 :36``), so the inherit resolves and BR-1's "loud good outcome" — a
failing xpath — does not occur. The workbook's browser dialog reduces to two
things that are each stronger than a DOM check:

* ``button_validate`` on a short picking returns core's own act_window
  (``O17 addons/stock/models/stock_picking.py:1193-1212`` →
  ``_action_generate_backorder_wizard`` ``:1230-1241``) carrying ``res_model``,
  ``target='new'``, ``view_id`` and ``default_pick_ids`` — fully observable
  over RPC;
* the rendered arch of the wizard view carries the three footer buttons
  (``process`` "Create Backorder", ``process_cancel_backorder`` "No
  Backorder", and the ``special="cancel"`` Discard) with the DataOne modifier
  applied. ``invisible="1"`` nodes are **not** stripped by ``get_view`` — only
  x2many sub-view embedding is skipped for them
  (``O17 ir_ui_view.py:1200-1211``) — so the honest assertion is that the node
  is present **and hidden**, not that it is absent. See adaptation 3.

Step 12 then calls the public ``process_cancel_backorder``
(``O17 addons/stock/wizard/stock_backorder_confirmation.py:70``; ``O19 :67``;
both read ``self.env.context['button_validate_picking_ids']``, ``:71`` / ``:68``)
on a **separate** equivalent fixture and records that it still executes. That
is the documented limit of BR-1 — a UI control, not a rule — and the workbook
says explicitly to record it, not to "fix" the case by deleting it.

Expected outcomes
-----------------
* ``TC158`` — **EXPECTED v17 OUTCOME: PASS.** v19: the unported file calls
  ``self.user_has_groups(...)``, removed in v19, so the same press raises
  ``AttributeError`` instead of the asserted ``UserError`` — loud, exactly as
  the workbook's ``v19_watch`` predicts. The ported worktree file already uses
  ``self.env.user.has_group``.
* ``TC159`` — **EXPECTED v17 OUTCOME: PASS.** v19: PASS, unless the group
  xmlid failed to migrate across ``res.groups.category_id`` →
  ``privilege_id`` / ``users`` → ``user_ids`` on a ``noupdate="1"`` record, in
  which case ``has_group`` returns False for everyone and this case fails
  while TC158 still passes. The pair must be read together.
* ``TC160`` — **EXPECTED v17 OUTCOME: PASS.** v19: PASS with a wider blast
  radius — v19's ``_has_group`` resolves through ``all_group_ids``
  (``O19 addons/base/models/res_users.py:1085-1104``) and is transitive, where
  v17 queries ``res_groups_users_rel`` directly (``:1096-1110``).
* ``TC161`` — **EXPECTED v17 OUTCOME: PASS.** v19: PASS.

Documented adaptations (hard rules 3 and 5)
-------------------------------------------
1. **No cross-test fixture dependence.** TC159 step 2 says "the same delivery
   TC158 failed on" and TC158's postcondition says to leave it un-validated;
   TC161's postcondition offers its backorder to TC163. Hard rule 5 outranks
   all three: every case here builds its own token-scoped order, delivery and
   users, and removes them in a ``finally`` that can never raise. TC159 builds
   a delivery in the identical shape (same product, same partner label, same
   ``order_type='buy'``, same fully-reserved ``assigned`` state) and asserts
   that shape before pressing Validate, so it is testing what TC158 left
   behind in every respect except the record id.
2. **Users are infrastructure, not fixtures.** ``common.user_login`` is
   deliberately NOT token-scoped, and ``common.ensure_user`` rewrites
   membership with ``(6, 0, ids)`` on every call, so a run interrupted between
   the grant and the revoke cannot poison the next one. Memberships are always
   granted and revoked **as admin**: a member of *Cannot edit transfers*
   cannot write any picking and therefore cannot tidy up after itself.
3. **TC161 step 6 asserts "hidden", not "absent".** The workbook says the No
   Backorder button "is not present in the rendered dialog"; what the server
   renders is the node with ``invisible="1"``, which the web client then never
   paints. Asserting absence from the arch would assert something false about
   the mechanism actually in place, so the assertion is the modifier
   byte-exact plus the button's exclusion from the *visible* footer set — and
   if the DataOne inherit ever stops applying, the modifier reverts to core's
   ``invisible="show_transfers"`` and BOTH halves fail loudly.
4. **TC161 runs as the platform session, and proves it qualifies.**
   ``base.user_admin`` is seeded into *Validate Delivery Orders*
   (``data/server_actions.xml:20-23``), so the acting session satisfies the
   workbook's TD-U-11 precondition; step 1 asserts that membership rather than
   assuming it, by **reading the groups m2m** through
   ``common.user_has_group`` — ``all_group_ids`` on v19
   (``O19 res_users.py:258``), ``ctx.adapter.user_groups_field`` on v17.
   ``res.users.has_group`` is deliberately NOT called: it is ``@api.model`` on
   v17 (``O17 res_users.py:1085-1086``), so ``call_kw`` applies the whole args
   list to it, and ``_has_group`` answers about ``self._uid`` — the SESSION
   user — not about the argument (``:1107-1109``). On v19 it is a record
   method with ``ensure_one()`` (``O19 :1066, 1074``). The membership read is
   exact on both. F042 is a wizard-view control, not an access rule,
   so no impersonation is needed — unlike TC158-TC160, where the membership
   *is* the subject.
5. **TC160 step 10 gets one supplementary probe, on the receipt fixture.** The
   member holds neither group, so pressing Validate on the *delivery* is
   refused by F179's message before F180's write ever runs. The workbook's
   assertion ("the operation fails") is implemented exactly as written, and
   the reason it gives ("because button_validate writes state inside the same
   transaction") is then demonstrated on the **receipt** — which F179 does not
   guard at all, since its test is ``picking_type_id.id ==
   stock.picking_type_out`` — so the string that surfaces there is F180's.
   That probe is evidence recorded beside the workbook assertion, never in
   place of it.
6. **TC160 step 12's control edit is reverted in the ``finally``**, as the
   workbook's postcondition asks, and the picking is swept afterwards anyway.
7. **Every fixture order is ``order_type='buy'`` with a non-empty
   ``memo_to_suppliers``.** The first keeps F040 out of a security verdict
   (adaptation above); the second is a hard fixture constraint —
   ``DTO project-addons/dto_sale_stock/data/base_automation_data.xml:59``
   evaluates ``if 'IRM' in order.memo_to_suppliers:`` unguarded on a
   ``fields.Text`` that reads ``False`` when NULL, which raises ``TypeError``
   *inside* the ``button_validate`` transaction and aborts the delivery. Both
   are built into ``common.make_sale_order``; ``common.confirm_order`` and
   ``common.validate_delivery`` call ``require_mail_offline`` first, because
   the same automation calls ``send_mail(force_send=True)`` against hard-coded
   ``@d1systems.com`` recipients (``:49-70``) — convention rule 4.
"""
from framework.registry import test_case
from tests.wf011.common import (Arch, BACKORDER_CANCEL_BUTTON,
                                BACKORDER_INHERIT_XMLID,
                                BACKORDER_PROCESS_BUTTON, BACKORDER_VIEW_XMLID,
                                ERROR_TRANSFERS_WRITE, ERROR_VALIDATE_GROUP,
                                GROUP_STOCK_USER, GROUP_TRANSFERS_READ,
                                GROUP_VALIDATE_DELIVERY, ISOLATED_ORDER_TYPE,
                                PICKING_TYPE_OUT_XMLID, WORKFLOW,
                                WORKFLOW_NAME, arch_of_xmlid, backorders_of,
                                cancel_backorder, confirm_order,
                                ensure_partner, ensure_product, ensure_user,
                                expect_error, m2o_id, make_picking,
                                make_sale_order, move_lines_of, moves_of,
                                open_namespace, outgoing_pickings, picking_row,
                                process_backorder, remove_user_from_group,
                                require_delivery_groups, require_mail_offline,
                                require_module_build, require_modules,
                                require_sale_stack, session_as, sweep_wf011,
                                trace, user_group_ids, user_has_group,
                                validate_delivery)

#: The workbook's own test-data labels, kept so a reader can line an execution
#: record up against the case text. They are labels, not group XML ids — the
#: real membership each one stands for is spelled out in the calls below.
ROLE_NO_VALIDATE = "TD-U-12 dto_no_deliv"
ROLE_VALIDATOR = "TD-U-11 dto_deliv_validator"
ROLE_TRANSFERS_LOCKED = "TD-U-14 dto_transfers_locked"
ROLE_CONTROL = "TD-U-03 (not a member)"

#: Written to the single move of TC161's short delivery; 10 - 6 = 4 short.
SHORT_QTY = 6.0
FULL_QTY = 10.0
BACKORDER_QTY = FULL_QTY - SHORT_QTY

#: stock/views/stock_picking_views.xml:146 (v17) / :119 (v19) — the Validate
#: button that is visible while the transfer is `assigned`.
PICKING_STATE_ASSIGNED = "assigned"
PICKING_STATE_DONE = "done"


# --------------------------------------------------------------------------
# Local helpers.
#
# None of these duplicates something tests/wf011/common.py already provides:
# common's arch helpers all fetch through ctx.adapter.rpc (the platform's own
# admin session), and TC158 step 3 has to read the arch rendered for the
# IMPERSONATED user — that is a different question, not the same one.
# --------------------------------------------------------------------------
def _arch_as(user_rpc, model: str, view_type: str = "form") -> Arch:
    """The arch ``get_view`` renders for the session behind ``user_rpc``.

    ``ir.ui.view`` pops each node's ``groups`` attribute after evaluating it
    and removes the node when the session is not a member
    (O17 odoo/addons/base/models/ir_ui_view.py:1011-1012), so what comes back
    here is exactly what that user would see — which is the whole point of
    TC158 step 3.
    """
    return Arch(user_rpc.call(model, "get_view", view_type=view_type)["arch"])


def _buttons_named(arch: Arch, name: str) -> list:
    """Every ``<button name=…>`` node in an arch, in document order."""
    return [node for node in arch.root.iter("button")
            if node.get("name") == name]


def _hidden_outright(invisible) -> bool:
    """True when a modifier hides the node unconditionally."""
    return str(invisible or "").strip() in ("1", "True", "true")


def _visible_in_state(invisible, state: str) -> bool:
    """Whether a node carrying this ``invisible`` modifier renders in ``state``.

    Deliberately conservative and record-independent: no modifier means
    visible, an unconditional modifier means hidden, and any other expression
    is treated as hiding the node when it names the state. Core's two Validate
    buttons split exactly on that — ``state in ('draft', 'confirmed', 'done',
    'cancel')`` and ``state in ('waiting', 'assigned', 'done', 'cancel')``
    (O17 stock/views/stock_picking_views.xml:146-147, O19 :119-120, identical).
    """
    if invisible is None:
        return True
    if _hidden_outright(invisible):
        return False
    return f"'{state}'" not in str(invisible)


def _validate_button_facts(arch: Arch) -> dict:
    """TC158 step 3, as one mismatch dict.

    There is deliberately NO ``groups``-attribute key here. ``get_view``
    postprocesses the arch through ``_postprocess_access_rights``
    (``O17 ir_ui_view.py:2641``), which **pops** the attribute off every node
    before returning — ``for node in tree.xpath('//*[@groups]'):
    attrib_groups = node.attrib.pop('groups')`` (``:1010-1013``) — and removes
    the node outright when the session is not in those groups. So
    ``node.get('groups')`` is ``None`` on every returned node by construction,
    and an assertion over it could never fail: it would record a passing check
    that carries no information.

    What carries the information is ``present``, read from the arch rendered
    **for the non-member session**: the button survived postprocessing for a
    user outside ``dto_mrp_account.group_validate_delivery_orders``, which is
    exactly the workbook's "the control is in Python, not in the view". Had
    any module added a ``groups`` restriction naming that group, the node
    would have been removed at ``:1013`` and ``present`` would be ``False``.
    """
    nodes = _buttons_named(arch, "button_validate")
    return {
        "present": bool(nodes),
        "visible_while_assigned": any(
            _visible_in_state(node.get("invisible"), PICKING_STATE_ASSIGNED)
            for node in nodes),
    }


def _on_hand_at(rpc, product_id: int, location_id: int) -> float:
    """Total quant quantity for one product at one location (exact match).

    ``stock.quant.quantity`` is the on-hand figure; ``reserved_quantity`` is
    not subtracted, so a reservation does not move this number and a validated
    delivery does — which is what TC159 step 7 measures.
    """
    rows = rpc.search_read("stock.quant",
                           [("product_id", "=", product_id),
                            ("location_id", "=", location_id)],
                           ["quantity"])
    return sum(row["quantity"] for row in rows)


def _order_invoice_ids(rpc, order_id: int) -> list:
    """The order's own ``invoice_ids``.

    Scoped to the fixture order rather than counting ``account.move`` rows, so
    a live posting elsewhere on the clone can never leak into an "exactly N"
    claim (hard rule 5).
    """
    row = rpc.read("sale.order", [order_id], ["invoice_ids"])[0]
    return row["invoice_ids"]


def _picking_snapshot(rpc, picking_id: int) -> dict:
    """The stored values TC160 step 11 asserts are unchanged."""
    row = picking_row(rpc, picking_id,
                      ["state", "date_done", "scheduled_date", "note",
                       "origin", "priority"])
    return {key: row.get(key, "FIELD ABSENT") for key in
            ("state", "date_done", "scheduled_date", "note", "origin",
             "priority")}


def _footer_buttons(arch: Arch) -> list:
    """Every ``<footer><button>`` of a wizard form, in document order."""
    out = []
    for footer in arch.root.iter("footer"):
        for node in footer.iter("button"):
            out.append({"name": node.get("name"),
                        "special": node.get("special"),
                        "string": node.get("string"),
                        "invisible": node.get("invisible")})
    return out


def _visible_footer_buttons(arch: Arch) -> list:
    """The footer buttons a user would actually be offered."""
    return [{"name": b["name"], "special": b["special"],
             "string": b["string"]}
            for b in _footer_buttons(arch)
            if not _hidden_outright(b["invisible"])]


def _backorder_action_shape(action, picking_id) -> dict:
    """The observable shape of ``_action_generate_backorder_wizard``'s dict
    (O17 stock/models/stock_picking.py:1230-1241)."""
    if not isinstance(action, dict):
        return {"type": None, "res_model": None, "target": None,
                "view_mode": None, "view_id": None,
                "offers_this_picking": False}
    context = action.get("context") or {}
    pick_ids = context.get("default_pick_ids") or []
    # default_pick_ids is [(4, id), …], JSON-marshalled as [[4, id], …]
    offered = {command[1] for command in pick_ids
               if isinstance(command, (list, tuple)) and len(command) > 1}
    return {
        "type": action.get("type"),
        "res_model": action.get("res_model"),
        "target": action.get("target"),
        "view_mode": action.get("view_mode"),
        "view_id": action.get("view_id"),
        "offers_this_picking": offered == {picking_id},
    }


def _safe(ctx, label, fn, *args, **kwargs):
    """A teardown step that can never raise (hard rule 3)."""
    try:
        return fn(*args, **kwargs)
    except Exception as exc:                                   # noqa: BLE001
        ctx.log(f"[warn] {label}: {exc}")
        return None


def _make_delivery_fixture(ctx, label: str, qty: float = FULL_QTY):
    """A confirmed ``buy`` order with ONE fully-reserved outgoing delivery.

    Returns ``(order_id, picking_id, product_id, partner_id)``. The order type
    and the memo are ``common.make_sale_order``'s defaults and are load-bearing
    — see the module docstring, adaptation 7.
    """
    partner_id = ensure_partner(ctx, "Customer Alpha")          # TD-PA-01
    product_id = ensure_product(ctx, "Widget")                  # TD-P-01
    order_id = make_sale_order(ctx, order_type=ISOLATED_ORDER_TYPE,
                               product_id=product_id, qty=qty,
                               partner_id=partner_id, label=label)
    confirm_order(ctx, order_id)
    pickings = outgoing_pickings(ctx.adapter.rpc, order_id)
    if len(pickings) != 1:
        ctx.blocked(
            f"The fixture order produced {len(pickings)} outgoing picking(s), "
            "not 1. Every case in this file validates ONE delivery on "
            f"{PICKING_TYPE_OUT_XMLID} exactly, because "
            "dto_mrp_account/models/stock_picking.py:10 compares against that "
            "single operation type and reads self.picking_type_id on the "
            "whole recordset. A multi-step delivery route on this warehouse "
            "changes what the case is measuring, so it is reported rather "
            "than measured.")
    return order_id, pickings[0]["id"], product_id, partner_id


@test_case(
    id="TEST-WF011-TC158",
    name="A user outside *Validate Delivery Orders* cannot validate a "
         "delivery",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_mrp_account", priority="P0", kind="API", order=11158,
    description="A stock user outside dto_mrp_account."
                "group_validate_delivery_orders is shown the Validate button "
                "but is refused with the exact F179 string, and because the "
                "raise precedes super() nothing moved: state still assigned, "
                "date_done unset, no invoice on the order, no done move line "
                "and no auto-created lot name.",
    traceability=trace("DATAONE-TC158"))
def test_tc158(ctx):
    rpc = ctx.adapter.rpc
    require_module_build(ctx)
    require_modules(ctx, ["dto_mrp_account", "dto_sale_stock"])
    require_delivery_groups(ctx)
    require_sale_stack(ctx)
    open_namespace(ctx)
    user_id = None
    try:
        with ctx.step("Log in as TD-U-12."):
            # The negative case MUST impersonate: dto_mrp_account/data/
            # server_actions.xml:20-23 seeds base.user_root and
            # base.user_admin into the group, so the platform's own session
            # passes the check under test.
            user_id, login = ensure_user(ctx, "no_validate",
                                         [GROUP_STOCK_USER])
            user_rpc = session_as(ctx.env, login)
            ctx.log(f"workbook role {ROLE_NO_VALIDATE} -> {login} "
                    f"(base.group_user + {GROUP_STOCK_USER}, written with "
                    "(6, 0, ids) so no stray membership can survive a run)")
            ctx.check(
                "TD-U-12 holds stock.group_stock_user and is NOT a member of "
                "dto_mrp_account.group_validate_delivery_orders",
                {GROUP_STOCK_USER: True, GROUP_VALIDATE_DELIVERY: False},
                {GROUP_STOCK_USER: user_has_group(rpc, user_id,
                                                  GROUP_STOCK_USER),
                 GROUP_VALIDATE_DELIVERY: user_has_group(
                     rpc, user_id, GROUP_VALIDATE_DELIVERY)})

        with ctx.step("Open Inventory → Transfers → the delivery for "
                      "TD-PA-01."):
            order_id, picking_id, product_id, _partner = (
                _make_delivery_fixture(ctx, "TC158 Delivery"))
            row = picking_row(rpc, picking_id,
                              ["name", "state", "picking_type_id",
                               "date_done"])
            moves = moves_of(rpc, picking_id)
            # The workbook's two preconditions, asserted rather than assumed:
            # F179 guards ONE operation type (models/stock_picking.py:9-10),
            # and a short reservation would change what "Validate" means.
            ctx.check(
                "the delivery is assigned, fully reserved, and its operation "
                f"type is exactly {PICKING_TYPE_OUT_XMLID}",
                {"state": PICKING_STATE_ASSIGNED,
                 "picking_type_id": rpc.ref(PICKING_TYPE_OUT_XMLID),
                 "reserved": [FULL_QTY]},
                {"state": row["state"],
                 "picking_type_id": m2o_id(row["picking_type_id"]),
                 "reserved": [move["quantity"] for move in moves]})
            # Readable by that user — the case is about the Python guard, not
            # about an ACL refusing the record outright.
            ctx.check("TD-U-12 can read the delivery",
                      [row["name"]],
                      [r["name"] for r in user_rpc.read(
                          "stock.picking", [picking_id], ["name"])])

        with ctx.step("Assert the Validate button is visible (the control is "
                      "in Python, not in the view)."):
            facts = _validate_button_facts(_arch_as(user_rpc, "stock.picking"))
            ctx.log("the arch below is the one get_view renders FOR TD-U-12, "
                    "after _postprocess_access_rights has removed every node "
                    "whose groups this session lacks (O17 ir_ui_view.py:"
                    "1010-1013, reached from :2641). A view-level restriction "
                    "naming group_validate_delivery_orders would therefore "
                    "show up as present=False, not as a surviving groups "
                    "attribute — the attribute is popped before the arch is "
                    "returned, so it is never assertable (see "
                    "_validate_button_facts).")
            ctx.check(
                "the form rendered FOR TD-U-12 carries Validate and it is "
                "visible while the transfer is assigned — no view-level group "
                "removed it, so the control is in Python "
                "(stock/views/stock_picking_views.xml:146)",
                {"present": True, "visible_while_assigned": True},
                facts)

        with ctx.step("Press Validate."):
            # The press is EXPECTED to be refused, but a broken F179 would let
            # it through to done, and reaching done on a picking with a
            # sale_id fires dto_sale_stock's shipment automation and its
            # send_mail(force_send=True) to hard-coded @d1systems.com
            # recipients (data/base_automation_data.xml:49-70). Convention
            # rule 4 says a test must not be able to send mail even when the
            # behaviour under test is broken, so the probe runs first.
            require_mail_offline(ctx)
            raised, message = expect_error(user_rpc.call, "stock.picking",
                                           "button_validate", [picking_id])
            ctx.log(f"button_validate as {login}: raised={raised} "
                    f"{message!r}")

        with ctx.step("Assert a UserError is raised."):
            ctx.check_true("button_validate was refused", raised,
                           actual_desc=message)

        with ctx.step("Assert the message is exactly Only users in the "
                      "'Validate Delivery Orders' group can validate this "
                      "picking."):
            # Not wrapped in _() at dto_mrp_account/models/stock_picking.py:11,
            # so it is compared byte-for-byte, never as a substring.
            ctx.check("the server message, verbatim", ERROR_VALIDATE_GROUP,
                      message)

        with ctx.step("Assert picking.state is still assigned — not done."):
            ctx.check("the delivery is unchanged in assigned",
                      PICKING_STATE_ASSIGNED,
                      picking_row(rpc, picking_id, ["state"])["state"])

        with ctx.step("Assert picking.date_done is unset."):
            ctx.check("date_done is unset",
                      False,
                      picking_row(rpc, picking_id,
                                  ["date_done"])["date_done"])

        with ctx.step("Assert no account.move was created for the related "
                      "sale order (the auto-invoice did not fire)."):
            ctx.check("the order has no invoice", [],
                      _order_invoice_ids(rpc, order_id))

        with ctx.step("Assert no stock.move.line on the picking has state == "
                      "'done'."):
            lines = move_lines_of(rpc, picking_id)
            ctx.check(
                "no move line reached done, and stock_picking_auto_create_lot"
                "'s _set_auto_lot() (models/stock_picking.py:66-68, called "
                "BEFORE super) left no lot name behind either",
                {"done_lines": [], "lot_names": []},
                {"done_lines": [line["id"] for line in lines
                                if line["state"] == PICKING_STATE_DONE],
                 "lot_names": [line["lot_name"] for line in lines
                               if line.get("lot_name")]})
    finally:
        # The workbook's postcondition ("leave the delivery un-validated;
        # TC159 validates it") is honoured by NOT validating it here; the
        # record itself is still removed, because TC159 builds its own
        # (module docstring, adaptation 1). Never raises. The fixture user is
        # left in place deliberately: users are infrastructure, and
        # common.ensure_user rewrites membership with (6, 0, ids) on every
        # call, so the next run cannot inherit anything from this one.
        ctx.log(f"fixture user left in place for reuse: id={user_id!r}")
        _safe(ctx, "cleanup incomplete", sweep_wf011, rpc)


@test_case(
    id="TEST-WF011-TC159",
    name="A member of *Validate Delivery Orders* validates the same delivery "
         "successfully",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_mrp_account", priority="P0", kind="API", order=11159,
    description="The paired positive case: a member of dto_mrp_account."
                "group_validate_delivery_orders validates an identical "
                "delivery with no error, the picking reaches done with "
                "date_done set and stock leaves the source location, the buy "
                "order type produces no invoice, and the operation changes "
                "no group membership.",
    traceability=trace("DATAONE-TC159"))
def test_tc159(ctx):
    rpc = ctx.adapter.rpc
    require_module_build(ctx)
    require_modules(ctx, ["dto_mrp_account", "dto_sale_stock"])
    require_delivery_groups(ctx)
    require_sale_stack(ctx)
    open_namespace(ctx)
    user_id = None
    try:
        with ctx.step("Log in as TD-U-11."):
            user_id, login = ensure_user(ctx, "validator",
                                         [GROUP_STOCK_USER,
                                          GROUP_VALIDATE_DELIVERY])
            user_rpc = session_as(ctx.env, login)
            ctx.log(f"workbook role {ROLE_VALIDATOR} -> {login} "
                    f"(base.group_user + {GROUP_STOCK_USER} + "
                    f"{GROUP_VALIDATE_DELIVERY}); membership is granted "
                    "EXPLICITLY because v17's _has_group reads "
                    "res_groups_users_rel with no transitive SQL "
                    "(base/models/res_users.py:1096-1110) — v17 pre-expands "
                    "implied groups into that relation on write "
                    "(UsersImplied.write, :1452-1470), so the relation is the "
                    "whole answer there, while v19 computes the closure at "
                    "read time through all_group_ids (O19 :258-259, 447-449)")
            groups_before = sorted(user_group_ids(ctx, user_id))
            ctx.check("TD-U-11 is a member of "
                      "dto_mrp_account.group_validate_delivery_orders",
                      {GROUP_STOCK_USER: True, GROUP_VALIDATE_DELIVERY: True},
                      {GROUP_STOCK_USER: user_has_group(rpc, user_id,
                                                        GROUP_STOCK_USER),
                       GROUP_VALIDATE_DELIVERY: user_has_group(
                           rpc, user_id, GROUP_VALIDATE_DELIVERY)})

        with ctx.step("Open the same delivery TC158 failed on."):
            # Hard rule 5: no case consumes another case's fixtures. This is
            # an identically shaped delivery — same product, same partner
            # label, same order_type='buy', same fully-reserved assigned
            # state — and that shape is asserted before Validate is pressed
            # (module docstring, adaptation 1).
            order_id, picking_id, product_id, _partner = (
                _make_delivery_fixture(ctx, "TC159 Delivery"))
            row = picking_row(rpc, picking_id,
                              ["state", "picking_type_id", "location_id",
                               "date_done"])
            source_id = m2o_id(row["location_id"])
            on_hand_before = _on_hand_at(rpc, product_id, source_id)
            order_type = rpc.read("sale.order", [order_id],
                                  ["order_type"])[0]["order_type"]
            ctx.check(
                "the delivery is assigned on "
                f"{PICKING_TYPE_OUT_XMLID}, fully reserved, and its order is "
                "the buy type F040 excludes "
                "(dto_sale_stock/models/stock_picking.py:16-18)",
                {"state": PICKING_STATE_ASSIGNED,
                 "picking_type_id": rpc.ref(PICKING_TYPE_OUT_XMLID),
                 "reserved": [FULL_QTY],
                 "order_type": ISOLATED_ORDER_TYPE},
                {"state": row["state"],
                 "picking_type_id": m2o_id(row["picking_type_id"]),
                 "reserved": [move["quantity"]
                              for move in moves_of(rpc, picking_id)],
                 "order_type": order_type})
            ctx.log(f"on hand for the fixture product at location "
                    f"{source_id} before validation: {on_hand_before}")

        with ctx.step("Press Validate."):
            # Reaching done fires dto_sale_stock's shipment automation, which
            # calls send_mail(force_send=True) against hard-coded
            # @d1systems.com recipients (data/base_automation_data.xml:49-70)
            # — convention rule 4.
            require_mail_offline(ctx)
            raised, message = expect_error(user_rpc.call, "stock.picking",
                                           "button_validate", [picking_id])
            ctx.log(f"button_validate as {login}: raised={raised} "
                    f"{message!r}")

        with ctx.step("Assert no UserError is raised."):
            ctx.check_true("validation was not refused", not raised,
                           actual_desc=message or "no error raised")

        with ctx.step("Assert picking.state == 'done'."):
            ctx.check("the delivery is done", PICKING_STATE_DONE,
                      picking_row(rpc, picking_id, ["state"])["state"])

        with ctx.step("Assert picking.date_done is set."):
            date_done = picking_row(rpc, picking_id,
                                    ["date_done"])["date_done"]
            # The VALUE is time-dependent and therefore never asserted
            # (hard rule 5); that it is set is the workbook's claim.
            ctx.check_true("date_done is set", bool(date_done),
                           actual_desc=repr(date_done))

        with ctx.step("Assert every stock.move on the picking is done and "
                      "on-hand at the source location fell by the delivered "
                      "quantity."):
            moves = moves_of(rpc, picking_id)
            ctx.check(
                "every move is done and the source location lost exactly the "
                "delivered quantity",
                {"move_states": [PICKING_STATE_DONE] * len(moves),
                 "delivered": [FULL_QTY] * len(moves),
                 "on_hand_delta": -FULL_QTY},
                {"move_states": [move["state"] for move in moves],
                 "delivered": [move["quantity"] for move in moves],
                 "on_hand_delta": (_on_hand_at(rpc, product_id, source_id)
                                   - on_hand_before)})

        with ctx.step("Assert no customer invoice was created — the order "
                      "type is buy, which F040 excludes."):
            ctx.check("the buy order produced no invoice", [],
                      _order_invoice_ids(rpc, order_id))

        with ctx.step("Assert the user's group membership is unchanged by the "
                      "operation."):
            ctx.check("TD-U-11's groups are exactly what they were before "
                      "Validate was pressed",
                      groups_before, sorted(user_group_ids(ctx, user_id)))
    finally:
        if user_id:
            _safe(ctx, "membership reset",
                  remove_user_from_group, ctx, user_id,
                  GROUP_VALIDATE_DELIVERY)
        # A validated picking cannot be unlinked; sweep_wf011 is best-effort
        # by design and the fresh execution token is what keeps a survivor out
        # of the next run's assertions (common.sweep_wf011).
        _safe(ctx, "cleanup incomplete", sweep_wf011, rpc)


@test_case(
    id="TEST-WF011-TC160",
    name="A member of the inverted *Cannot edit transfers* group cannot write "
         "any picking field",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_mrp_account", priority="P1", kind="API", order=11160,
    description="dto_mrp_account's write() override raises unconditionally "
                "for a member of group_transfers_read: the scheduled date, "
                "the note and a field on an incoming receipt are all refused "
                "with the same exact string, Validate fails too because "
                "_action_done writes the picking in the same transaction, "
                "nothing is left changed, and a non-member saves the same "
                "edit successfully.",
    traceability=trace("DATAONE-TC160"))
def test_tc160(ctx):
    rpc = ctx.adapter.rpc
    require_module_build(ctx)
    require_modules(ctx, ["dto_mrp_account"])
    require_delivery_groups(ctx)
    open_namespace(ctx)
    member_id = None
    control_id = None
    delivery_id = None
    scheduled_before = None
    try:
        with ctx.step("Log in as TD-U-14."):
            member_id, member_login = ensure_user(
                ctx, "transfers_locked",
                [GROUP_STOCK_USER, GROUP_TRANSFERS_READ])
            member_rpc = session_as(ctx.env, member_login)
            ctx.log(f"workbook role {ROLE_TRANSFERS_LOCKED} -> "
                    f"{member_login}. stock.group_stock_user is added on top "
                    "of the workbook's membership because without it the user "
                    "cannot open a transfer at all and the case would measure "
                    "an ACL refusal instead of F180.")
            # Recorded, never asserted: dto_mrp_account/data/
            # server_actions.xml:32-35 seeds NO users into this group and
            # declares no ir.rule anywhere, which is the workbook's own
            # REMOVE-candidate open question (TC160 Notes).
            ctx.log("dto_mrp_account/data/server_actions.xml:32-35 seeds no "
                    "users into group_transfers_read and grep finds no "
                    "ir.rule for it — whether anyone belongs to it on this "
                    "database is the workbook's open question, recorded here "
                    "rather than asserted.")
            ctx.check("TD-U-14 is a member of "
                      "dto_mrp_account.group_transfers_read",
                      {GROUP_STOCK_USER: True, GROUP_TRANSFERS_READ: True},
                      {GROUP_STOCK_USER: user_has_group(rpc, member_id,
                                                        GROUP_STOCK_USER),
                       GROUP_TRANSFERS_READ: user_has_group(
                           rpc, member_id, GROUP_TRANSFERS_READ)})

        with ctx.step("Open the delivery for TD-PA-01."):
            customer_id = ensure_partner(ctx, "Customer Alpha")   # TD-PA-01
            vendor_id = ensure_partner(ctx, "Vendor Gamma")       # TD-PA-03
            delivery_id = make_picking(ctx, code="outgoing",
                                       partner_id=customer_id,
                                       label="TC160 Delivery")
            receipt_id = make_picking(ctx, code="incoming",
                                      partner_id=vendor_id,
                                      label="TC160 Receipt")
            before = _picking_snapshot(rpc, delivery_id)
            receipt_before = _picking_snapshot(rpc, receipt_id)
            scheduled_before = before["scheduled_date"]
            ctx.check("both fixtures are assigned — one outgoing delivery and "
                      "one incoming receipt",
                      {"delivery": PICKING_STATE_ASSIGNED,
                       "receipt": PICKING_STATE_ASSIGNED},
                      {"delivery": before["state"],
                       "receipt": receipt_before["state"]})

        with ctx.step("Change the Scheduled Date and attempt to save."):
            raised_date, message_date = expect_error(
                member_rpc.write, "stock.picking", [delivery_id],
                {"scheduled_date": "2099-01-01 08:00:00"})
            ctx.log(f"scheduled_date write as {member_login}: "
                    f"raised={raised_date} {message_date!r}")

        with ctx.step("Assert a UserError is raised with the exact message "
                      "You are not allowed to change Transfers records."):
            # Not _()-wrapped at dto_mrp_account/models/stock_picking.py:19.
            ctx.check("the scheduled-date write is refused with the verbatim "
                      "string",
                      {"raised": True, "message": ERROR_TRANSFERS_WRITE},
                      {"raised": raised_date, "message": message_date})

        with ctx.step("Change the Note field instead and attempt to save."):
            raised_note, message_note = expect_error(
                member_rpc.write, "stock.picking", [delivery_id],
                {"note": "<p>WF011 TC160 note attempt</p>"})
            ctx.log(f"note write as {member_login}: raised={raised_note} "
                    f"{message_note!r}")

        with ctx.step("Assert the same exact message — the block is on any "
                      "field, not a named list."):
            # write() inspects `vals` not at all (models/stock_picking.py:17-21)
            ctx.check("a different field is refused with the identical string",
                      {"raised": True, "message": ERROR_TRANSFERS_WRITE},
                      {"raised": raised_note, "message": message_note})

        with ctx.step("Open the receipt for TD-PA-03, change any field and "
                      "attempt to save."):
            raised_in, message_in = expect_error(
                member_rpc.write, "stock.picking", [receipt_id],
                {"scheduled_date": "2099-01-02 08:00:00"})
            ctx.log(f"receipt write as {member_login}: raised={raised_in} "
                    f"{message_in!r}")

        with ctx.step("Assert the same exact message — the block is not "
                      "limited to outgoing transfers."):
            ctx.check("an incoming receipt is refused with the identical "
                      "string",
                      {"raised": True, "message": ERROR_TRANSFERS_WRITE},
                      {"raised": raised_in, "message": message_in})

        with ctx.step("Attempt to press Validate on the delivery."):
            # Both presses below are EXPECTED to be refused; a broken F180
            # would let one reach done and fire the shipment automation's
            # send_mail(force_send=True), so the mail probe runs first
            # (convention rule 4).
            require_mail_offline(ctx)
            raised_validate, message_validate = expect_error(
                member_rpc.call, "stock.picking", "button_validate",
                [delivery_id])
            ctx.log(f"button_validate as {member_login}: "
                    f"raised={raised_validate} {message_validate!r}")
            # Supplementary probe, on the RECEIPT fixture rather than on the
            # delivery under test — see the module docstring, adaptation 5.
            # F179 guards stock.picking_type_out only, so the receipt reaches
            # core's _action_done and its picking write
            # (O17 stock/models/stock_picking.py:994), which is the E4 claim
            # step 10 is making. It is safe to run here only because steps
            # 3-8 have already proved F180 refuses every picking write.
            raised_receipt, message_receipt = expect_error(
                member_rpc.call, "stock.picking", "button_validate",
                [receipt_id])
            ctx.log(f"[evidence] button_validate on the RECEIPT as "
                    f"{member_login}: raised={raised_receipt} "
                    f"{message_receipt!r} — F179 does not guard incoming "
                    "types, so this is F180 blocking _action_done's own "
                    "picking write")

        with ctx.step("Assert the operation fails, because button_validate "
                      "writes state inside the same transaction."):
            ctx.check(
                "Validate is refused for the member on both the guarded "
                "outgoing delivery and the unguarded incoming receipt, and "
                "on the receipt the refusal is F180's own write message",
                {"delivery_refused": True, "receipt_refused": True,
                 "receipt_message": ERROR_TRANSFERS_WRITE},
                {"delivery_refused": raised_validate,
                 "receipt_refused": raised_receipt,
                 "receipt_message": message_receipt})
            ctx.log("the delivery's refusal message was "
                    f"{message_validate!r}: the member holds neither group, "
                    "so F179's gate "
                    "(dto_mrp_account/models/stock_picking.py:8-11) answers "
                    "first on stock.picking_type_out. Both are refusals; the "
                    "receipt probe above isolates F180's.")

        with ctx.step("Assert the picking's stored values are unchanged after "
                      "every failed attempt."):
            ctx.check("neither fixture moved a single stored value",
                      {"delivery": before, "receipt": receipt_before},
                      {"delivery": _picking_snapshot(rpc, delivery_id),
                       "receipt": _picking_snapshot(rpc, receipt_id)})

        with ctx.step("Log in as TD-U-03 (not a member), repeat step 3, and "
                      "assert the save succeeds — the control case."):
            control_id, control_login = ensure_user(ctx, "transfers_control",
                                                    [GROUP_STOCK_USER])
            control_rpc = session_as(ctx.env, control_login)
            ctx.log(f"workbook role {ROLE_CONTROL} -> {control_login}")
            raised_ctrl, message_ctrl = expect_error(
                control_rpc.write, "stock.picking", [delivery_id],
                {"scheduled_date": "2099-01-03 08:00:00"})
            after = _picking_snapshot(rpc, delivery_id)
            ctx.check(
                "a non-member saves the identical edit, so the block is "
                "membership-driven and not a broken model",
                {"member_in_group": False, "raised": False,
                 "scheduled_date_changed": True},
                {"member_in_group": user_has_group(rpc, control_id,
                                                   GROUP_TRANSFERS_READ),
                 "raised": raised_ctrl,
                 "scheduled_date_changed":
                     after["scheduled_date"] != before["scheduled_date"]})
            ctx.log(f"control write message (expected empty): "
                    f"{message_ctrl!r}")
    finally:
        # The workbook's postcondition: revert step 12's edit. Done as admin,
        # because the member cannot write and the control user's own session
        # is not needed for it. Never raises.
        if delivery_id and scheduled_before:
            _safe(ctx, "step-12 edit not reverted",
                  rpc.write, "stock.picking", [delivery_id],
                  {"scheduled_date": scheduled_before})
        # Membership is revoked AS ADMIN: a member of group_transfers_read
        # cannot write any picking and so cannot tidy up after itself.
        if member_id:
            _safe(ctx, "membership reset",
                  remove_user_from_group, ctx, member_id,
                  GROUP_TRANSFERS_READ)
        _safe(ctx, "cleanup incomplete", sweep_wf011, rpc)


@test_case(
    id="TEST-WF011-TC161",
    name="A partial delivery always creates a backorder; \"No Backorder\" is "
         "not offered",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_sale_stock", priority="P1", kind="HYBRID", order=11161,
    description="A short validation returns core's backorder-confirmation "
                "act_window; the wizard view offers Create Backorder and "
                "Discard only, because dto_sale_stock forces invisible=\"1\" "
                "onto process_cancel_backorder; processing it leaves a done "
                "picking for 6, exactly one backorder demanding 4 and the "
                "order line still 6 of 10 — and the same public method "
                "reached directly over RPC still cancels the backorder, which "
                "is the documented limit of the control.",
    traceability=trace("DATAONE-TC161"))
def test_tc161(ctx):
    rpc = ctx.adapter.rpc
    require_module_build(ctx)
    require_modules(ctx, ["dto_sale_stock", "dto_mrp_account"])
    require_delivery_groups(ctx)
    require_sale_stack(ctx)
    open_namespace(ctx)
    try:
        with ctx.step("Log in as TD-U-11 and open the delivery."):
            # F042 is a wizard-view control, not an access rule, so this case
            # runs as the platform session — which base.user_admin's seeded
            # membership (data/server_actions.xml:20-23) makes a legitimate
            # TD-U-11. That membership is asserted, not assumed (module
            # docstring, adaptation 4).
            ctx.log(f"workbook role {ROLE_VALIDATOR} -> the platform session "
                    f"(uid {rpc.uid})")
            ctx.check_true(
                "the acting session holds "
                "dto_mrp_account.group_validate_delivery_orders, the "
                "workbook's precondition",
                user_has_group(rpc, rpc.uid, GROUP_VALIDATE_DELIVERY),
                actual_desc=f"uid {rpc.uid} membership of "
                            f"{GROUP_VALIDATE_DELIVERY}")
            order_id, picking_id, product_id, _partner = (
                _make_delivery_fixture(ctx, "TC161 Delivery"))
            ctx.check("the delivery is assigned with 10 units reserved",
                      {"state": PICKING_STATE_ASSIGNED,
                       "reserved": [FULL_QTY]},
                      {"state": picking_row(rpc, picking_id,
                                            ["state"])["state"],
                       "reserved": [move["quantity"]
                                    for move in moves_of(rpc, picking_id)]})

        with ctx.step("Set the done quantity on the single move line to 6, "
                      "leaving 4 short."):
            moves = moves_of(rpc, picking_id)
            ctx.check("the fixture carries exactly one move, demanding 10",
                      {"moves": 1, "demand": [FULL_QTY]},
                      {"moves": len(moves),
                       "demand": [move["product_uom_qty"] for move in moves]})
            rpc.write("stock.move", [moves[0]["id"]],
                      {"quantity": SHORT_QTY, "picked": True})

        with ctx.step("Press Validate."):
            # common.validate_delivery re-applies the same short quantity,
            # guards that the picking still holds exactly one move, and calls
            # require_mail_offline before anything can reach done.
            action = validate_delivery(ctx, picking_id, qty=SHORT_QTY)

        with ctx.step("Assert the backorder-confirmation dialog opens."):
            view_id = rpc.ref(BACKORDER_VIEW_XMLID)
            ctx.check(
                "button_validate returned core's backorder-confirmation "
                "act_window on stock.view_backorder_confirmation "
                "(stock/models/stock_picking.py:1230-1241)",
                {"type": "ir.actions.act_window",
                 "res_model": "stock.backorder.confirmation",
                 "target": "new", "view_mode": "form", "view_id": view_id,
                 "offers_this_picking": True},
                _backorder_action_shape(action, picking_id))

        with ctx.step("Assert the dialog offers Create Backorder and "
                      "Discard/Cancel only."):
            arch = arch_of_xmlid(ctx, BACKORDER_VIEW_XMLID, "form")
            ctx.check_true(
                "dto_sale_stock's inherit of the wizard view is installed",
                bool(rpc.ref(BACKORDER_INHERIT_XMLID)),
                actual_desc=f"{BACKORDER_INHERIT_XMLID} -> "
                            f"{rpc.ref(BACKORDER_INHERIT_XMLID)!r}")
            ctx.check(
                "the rendered footer offers Create Backorder and Discard and "
                "nothing else",
                [{"name": BACKORDER_PROCESS_BUTTON, "special": None,
                  "string": "Create Backorder"},
                 {"name": None, "special": "cancel", "string": "Discard"}],
                _visible_footer_buttons(arch))

        with ctx.step("Assert the No Backorder button "
                      "(process_cancel_backorder) is not present in the "
                      "rendered dialog."):
            # get_view keeps invisible="1" nodes (O17 ir_ui_view.py:1200-1211),
            # so "not present" is asserted as the modifier the DataOne inherit
            # forces onto core's invisible="show_transfers" — see the module
            # docstring, adaptation 3.
            nodes = [b for b in _footer_buttons(arch)
                     if b["name"] == BACKORDER_CANCEL_BUTTON]
            ctx.check(
                "No Backorder carries dto_sale_stock's invisible=\"1\" "
                "(wizard/stock_backorder_confirmation_views.xml:8-10) and is "
                "therefore never rendered",
                {"nodes": 1, "string": "No Backorder", "invisible": "1",
                 "offered_to_the_user": False},
                {"nodes": len(nodes),
                 "string": nodes[0]["string"] if nodes else None,
                 "invisible": nodes[0]["invisible"] if nodes else None,
                 "offered_to_the_user": any(
                     b["name"] == BACKORDER_CANCEL_BUTTON
                     for b in _visible_footer_buttons(arch))})

        with ctx.step("Press Create Backorder."):
            result = process_backorder(ctx, picking_id)
            ctx.log(f"process() -> {result!r}")

        with ctx.step("Assert the original picking is done with a delivered "
                      "quantity of 6."):
            moves = moves_of(rpc, picking_id)
            ctx.check("the original delivery is done for 6",
                      {"state": PICKING_STATE_DONE,
                       "move_states": [PICKING_STATE_DONE] * len(moves),
                       "delivered": [SHORT_QTY]},
                      {"state": picking_row(rpc, picking_id,
                                            ["state"])["state"],
                       "move_states": [move["state"] for move in moves],
                       "delivered": [move["quantity"] for move in moves]})

        with ctx.step("Assert exactly one new stock.picking exists with "
                      "backorder_id equal to the original picking's id."):
            backorders = backorders_of(rpc, picking_id)
            ctx.check("exactly one backorder was created", 1, len(backorders))

        with ctx.step("Assert the backorder demands 4 units of TD-P-01."):
            backorder_id = backorders[0]["id"]
            backorder_moves = moves_of(rpc, backorder_id)
            ctx.check("the backorder demands the 4 undelivered units",
                      {"moves": 1, "product": [product_id],
                       "demand": [BACKORDER_QTY]},
                      {"moves": len(backorder_moves),
                       "product": [m2o_id(move["product_id"])
                                   for move in backorder_moves],
                       "demand": [move["product_uom_qty"]
                                  for move in backorder_moves]})

        with ctx.step("Assert the sale order line still shows 4 units "
                      "outstanding (qty_delivered == 6, product_uom_qty == "
                      "10)."):
            lines = rpc.search_read("sale.order.line",
                                    [("order_id", "=", order_id),
                                     ("product_id", "=", product_id)],
                                    ["product_uom_qty", "qty_delivered"],
                                    order="id")
            ctx.check("the demand is intact and only 6 are delivered",
                      [{"product_uom_qty": FULL_QTY,
                        "qty_delivered": SHORT_QTY}],
                      [{"product_uom_qty": line["product_uom_qty"],
                        "qty_delivered": line["qty_delivered"]}
                       for line in lines])

        with ctx.step("Through the ORM, call process_cancel_backorder "
                      "directly on a fresh equivalent wizard and assert it "
                      "still executes — the removal is view-level only, so "
                      "RPC can reach it. Record the result as the documented "
                      "limit of the control."):
            # A SEPARATE fixture: never run this against the picking steps
            # 7-11 asserted on. process_cancel_backorder is public on both
            # versions (O17 wizard/stock_backorder_confirmation.py:70,
            # O19 :67), so Odoo's underscore rule does not shield it.
            _order2, picking2_id, _product2, _partner2 = (
                _make_delivery_fixture(ctx, "TC161 Limit"))
            validate_delivery(ctx, picking2_id, qty=SHORT_QTY)
            outcome = cancel_backorder(ctx, picking2_id)
            ctx.log(f"process_cancel_backorder() -> {outcome!r}")
            ctx.check(
                "the hidden method still executes over RPC: the second "
                "delivery is done for 6 and NO backorder was created — BR-1 "
                "is a UI control, not a rule",
                {"state": PICKING_STATE_DONE, "delivered": [SHORT_QTY],
                 "backorders": 0},
                {"state": picking_row(rpc, picking2_id, ["state"])["state"],
                 "delivered": [move["quantity"]
                               for move in moves_of(rpc, picking2_id)],
                 "backorders": len(backorders_of(rpc, picking2_id))})
            ctx.log("Recorded, not a failure (TC161 Notes): the 4 units "
                    "cancelled here are the exact loss BR-1 exists to "
                    "prevent, and nothing but the hidden button prevents it.")
    finally:
        # The workbook's postcondition offers this backorder to TC163; hard
        # rule 5 outranks it and TC163 builds its own (module docstring,
        # adaptation 1). Never raises.
        _safe(ctx, "cleanup incomplete", sweep_wf011, rpc)
