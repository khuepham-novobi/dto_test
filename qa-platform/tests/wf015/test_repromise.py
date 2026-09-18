"""DATAONE-WF-015 — per-line receipts and re-promising: TC201–TC204, TC206.

Five cases about one control surface: what ``dto_purchase_stock`` does to the
receipt a purchase order line produces, and what it does to that receipt when
the line's Expected Arrival moves. Abbreviations: ``DTO`` =
``D:/Projects/dataone/DTO-Odoo/project-addons``, ``O17`` =
``D:/Projects/dataone/odoo-17.0``, ``O19`` = ``D:/Projects/odoo-19.0``.

What this file proves
=====================

**TC201 — one receipt per line (F066).**
``purchase.order.button_confirm`` reaches core ``_create_picking``
(``O17 purchase_stock/models/purchase_order.py:237-261``, ``O19 :375-405``),
which creates ONE picking and hands it to
``order.order_line._create_stock_moves(picking)``. DTO's override
(``DTO/dto_purchase_stock/models/purchase_order_line.py:56-72``) **discards
the argument** and creates a fresh picking per line at ``:66`` from
``line.order_id._prepare_picking()``. Three lines therefore give three
receipts, each carrying the moves of exactly one line — which is the
assertion (step 4) that distinguishes this from three separate
confirmations.

Two consequences are asserted, not assumed:

* **Every receipt count in this file comes from ``order.picking_ids``**, never
  from ``search([('origin','=',order.name)])``. ``picking_ids`` is
  ``@api.depends('order_line.move_ids.picking_id')`` on both versions
  (``O17 purchase_stock/models/purchase_order.py:19,36-39``; ``O19 :22,44-47``)
  so an **empty** picking is never on it, whereas an ``origin`` count gives
  N+1 on v17 — core leaves the receipt it created itself behind
  (``O17 :237-261``, no cleanup) — and N on v19, which unlinks it
  (``O19 :400-401``). That delta would masquerade as a regroup difference.
* The override carries **no** ``.filtered(lambda l: not l.display_type)``
  guard, unlike core (``O17 purchase_stock/models/purchase_order_line.py:338``,
  ``O19 :366``), so a section or note line also gets an empty receipt. No
  fixture here uses a display_type line; the fact is logged, not exercised.

Steps 9–13 drive the real backorder round trip through the two public entry
points: ``stock.picking.button_validate`` and
``stock.backorder.confirmation.process``
(``O17 stock/wizard/stock_backorder_confirmation.py:21,52,61-67``).

**TC202 — a re-promise relocates the move (F067).**
The engine is five private ``stock.move`` / ``purchase.order.line`` helpers,
but every one of them is driven by the PUBLIC
``purchase.order.line.write({'date_planned': …})``: DTO's ``write``
(``purchase_order_line.py:106-110``) → core's
(``O17 purchase_stock/models/purchase_order_line.py:96-98``) →
``_update_move_date_deadline`` → DTO's override (``:74-90``) →
``stock.move._reassign_picking_by_date_deadline``
(``models/stock_move.py:41-66``). Nothing in this file re-implements a
private helper; every consequence is read off ``stock.move`` /
``stock.move.line`` / ``stock.picking``.

* The candidate pool and the per-picking deadline map are snapshotted
  **before** ``super()`` (``purchase_order_line.py:78-81``); the pool
  predicate is verbatim ``[('state','not in',('done','cancel')),
  ('location_dest_id.usage','in',('internal','transit','customer'))]``
  (``:41-44``) — ``common.CANDIDATE_DEST_USAGES``.
* Step 8 (same move id) is supported by ``_update_picking`` writing
  ``picking_id`` rather than recreating (``stock_move.py:25-27``); step 9 by
  the move-line write at ``:28-30``; step 10 by
  ``_update_date_from_date_deadline`` at ``:34-39`` (``move.date =
  move.date_deadline``).
* Step 13 is the case's reason for existing: the comparison runs through
  ``_get_date_deadline()``, which localises to ``env.user.tz`` and takes
  ``.date()`` (``models/stock_picking.py:42-51``, ``models/stock_move.py:9-18``).
  A port that compared raw datetimes would stop matching for any deadline not
  at midnight and every re-promise would silently create a new receipt
  instead — indistinguishable from correct behaviour without this assertion.
  ``common.pin_user_timezone`` therefore pins ``res.users.tz`` to
  ``America/Chicago`` and the restoration is asserted (see Adaptations).

**TC203 — a re-promise with no match creates a receipt (F067).**
Same public entry point. The new-receipt branch is ``stock_move.py:60-63``:
``picking_vals = purchase_order._prepare_picking()`` then
``stock.picking.create``. Step 9's key set therefore comes from
``_prepare_picking`` (``O17 purchase_stock/models/purchase_order.py:217-235``:
``picking_type_id, partner_id, user_id, date, origin, location_dest_id,
location_id, company_id, state='draft'``; ``O19 :358-373`` drops ``date`` and
uses ``reference_ids``) — so the version-stable subset is asserted against the
receipts the SAME method produced at confirmation, not against literals.
Step 10's anti-cascade assertion is made by picking id **per line**, as the
workbook demands, because ``_reassign_picking_by_date_deadline`` only ever
iterates the written line's own moves (``purchase_order_line.py:83-88``).

**TC204 — the emptied receipt is cancelled, not deleted (F067).**
``_update_picking`` ends with ``empty_pickings.action_cancel()``
(``stock_move.py:31-32``), and ``stock.picking.action_cancel`` is
**byte-identical** on both versions (``O17 stock/models/stock_picking.py:950-954``,
``O19 :1211-1215``): ``move_ids._action_cancel()``; ``write({'is_locked':
True})``; ``filtered(lambda x: not x.move_ids).state = 'cancel'``.
``state`` is a STORED compute whose no-moves branch yields ``'draft'``
(``O17 :656-657``, ``O19 :845-846``), so only the recompute-then-force order
inside ``action_cancel`` makes ``'cancel'`` stick — which is why step 5 reads
it back through a FRESH ``search_read`` in its own RPC transaction.

**TC206 — the fully-received Expected-Arrival lock (F068).**
``_check_fully_received_lines`` (``purchase_order_line.py:92-104``) fires when
``product_type in ('consu','product')`` AND ``order_id.state in
['purchase','done']`` AND ``float_compare(product_qty, qty_received,
precision_rounding=product_uom.rounding) == 0``. The message at ``:104`` has
three properties a naive test gets wrong, all carried by
``common.fully_received_error``: it is an **f-string not wrapped in ``_()``**
(never translated), it interpolates ``product_id.display_name`` (which renders
``[CODE] Name`` whenever the product carries an internal reference — so the
fixture product is created with ``default_code=False``), and it has **no
trailing period**. The guard runs only when ``'date_planned' in vals and
'product_uom' not in vals and 'product_qty' not in vals`` (``:107``) — the
documented by-design bypass of steps 10–11.

Expected outcomes
=================
* ``TC201`` — **EXPECTED v17 OUTCOME: PASS.** v19: PASS.
* ``TC202`` — **EXPECTED v17 OUTCOME: PASS.** v19: PASS unless the regroup
  engine changed; this is the silent failure mode WF-015 exists to catch.
* ``TC203`` — **EXPECTED v17 OUTCOME: PASS.** v19: PASS.
* ``TC204`` — **EXPECTED v17 OUTCOME: PASS.** v19: PASS — ``action_cancel``
  and ``_compute_state`` are unchanged.
* ``TC206`` — **EXPECTED v17 OUTCOME: PASS.** EXPECTED v19 OUTCOME: **FAIL at
  step 12** — ``purchase.order.state`` loses ``('done','Locked')``
  (``O17 purchase/models/purchase_order.py:98-105`` → ``O19 :105-111``, which
  gains a ``locked`` Boolean at ``:112-116``) and ``button_done``
  (``O17 :526-527``) is gone with it, so a locked order is no longer
  protected. The workbook expectation is immutable (hard rule 2), so the
  assertion stays exactly as written and the v19 FAIL is the recorded result.
  Read with it: the v19 break is **loud, not silent** as the workbook
  classifies it — ``line.product_uom`` at ``:102`` no longer exists on v19
  (renamed ``product_uom_id``, ``O19 purchase/models/purchase_order_line.py:36``),
  so the first ``date_planned`` write raises ``AttributeError``; and
  ``product_type`` does **not** break, surviving on v19 as related to
  ``product_id.type`` (``O19 :38``).

Every case opens with ``common.require_dto_purchase_stock``. The addons tree
on disk is already a partially-migrated v19 port
(``dto_purchase_stock/__manifest__.py:9`` declares ``19.0.0.0``) and cannot
build the v17 registry, so whatever the v17 target serves is an older
installed revision: the contribution is probed and reported **BLOCKED with a
precise reason** rather than FAILED. See ``docs/WF-015_AUTOMATION_PLAN.md`` §
"The fact that governs every test in this suite".

Documented adaptations (hard rules 3 and 5)
===========================================
1. **No impersonation.** The workbook's step 1 reads "Log in as TD-U-02
   (Purchasing User)" and TC201 step 9 switches to TD-U-03 (Stock User).
   Neither control under test is an access rule — the per-line split, the
   regroup and the lock are all model logic with no ``groups=`` anywhere
   (``dto_purchase_stock/security/ir.model.access.csv`` carries exactly ONE
   row, the label wizard, and the module declares no ``res.groups`` and no
   ``ir.rule``) — and ``TD-U-02`` / ``TD-U-03`` are test-data labels, not
   group XML ids. The mapping is logged at step 1 of each case and the
   platform session is used throughout, which is also required for cleanup.
2. **Fixed future dates, never "today + n".** ``D1``…``D5`` below are literal
   datetimes, so no expected value depends on when the suite runs (hard rule
   5). ``D1_LATE`` shares ``D1``'s calendar date in the pinned timezone but
   carries a different time of day — that pair is TC202 step 13's whole
   subject.
3. **``res.users.tz`` is a snapshot, not a change.** ``common.pin_user_timezone``
   records the previous value before writing ``America/Chicago``;
   ``common.restore_user_timezone`` puts it back in a ``finally`` that cannot
   raise, the sweep runs next, and the restoration is asserted last (the
   WF-013 TC228 precedent, ``tests/wf013/test_cogs_edge_cases.py``). Pinned in
   TC202, TC203 and TC204 — every case whose verdict depends on how a
   deadline localises. TC201 and TC206 assert nothing tz-dependent and leave
   the user untouched.
4. **TC202 step 11 builds a DECOY that is genuinely in the pool's reach.**
   The pool is ``order.picking_ids`` filtered by destination usage, so a
   picking outside ``picking_ids`` would be excluded twice over and would
   prove nothing. The decoy is therefore a receipt that IS on
   ``picking_ids`` — it carries a throwaway fourth line's move — and whose
   ``location_dest_id`` is the vendor's own ``usage='supplier'`` location.
   Line B is then re-promised to ``D4``, the deadline **only the decoy
   carries**: with the predicate respected there is no candidate and a new
   receipt is created; with the predicate dropped the decoy would be the
   single match. That makes the assertion discriminating rather than
   vacuous.
5. **TC202 step 12 is a before/after comparison over an empty set, and says
   so.** The workbook's own precondition forbids validating any receipt, so
   the fixture legitimately contains zero ``done``/``cancel`` moves. The
   snapshot is taken and compared anyway (so the assertion becomes real the
   moment the fixture changes) and the count is logged.
6. **TC204 step 9 is an ARCH check plus the one compute that gates the
   remaining button**, and is labelled as such rather than presented as a
   behavioural claim. ``stock.view_picking_form`` ships **no** reset-to-draft
   / unlock button at all — 15 distinct ``<button name=…>`` nodes on ``O17``
   and 17 on ``O19`` (``stock/views/stock_picking_views.xml``), none of them
   a reset; ``action_toggle_is_locked`` exists only as an ``ir.actions.server``
   record (``O17 :512`` / ``O19 :490``), never as a form button. Then
   ``action_confirm``
   is ``invisible="state != 'draft'"``, both ``button_validate`` nodes carry
   ``'cancel'`` in their ``in`` list, and the only header button whose
   ``invisible`` does not mention ``state`` — ``action_assign``,
   ``invisible="not show_check_availability"`` — is gated by a compute that
   returns ``False`` for anything outside ``('confirmed','waiting',
   'assigned')`` (``O17 stock/models/stock_picking.py:715-720``,
   ``O19 :965-970``), read off the cancelled receipt itself.
7. **TC204 step 8's "Cancelled filter" does not exist as a named filter.**
   ``stock.view_picking_internal_search`` (``O17 stock/views/
   stock_picking_views.xml:368``) ships ``draft`` / ``waiting`` /
   ``available`` (``:387-389``) and a ``Status`` group-by (``:413``) — no
   ``cancel`` filter. Findability is therefore asserted with the domain that
   facet produces, ``[('state','=','cancel')]``, scoped to this execution's
   vendor, and the arch fact is logged.
8. **TC204 step 10 asserts the verified answer, which is the opposite of the
   obvious one.** Because ``picking_ids = order_line.move_ids.picking_id``,
   the emptied-and-cancelled receipt **drops off** the order's
   ``picking_ids``. The workbook allows "or record whether it does"; the
   verified behaviour is asserted and the allowance is logged.
9. **TC203 step 12 records rather than guesses.** The new picking is created
   with ``state='draft'`` in the vals and nothing in the regroup path calls
   ``action_confirm()`` or ``_action_assign()``, so its state is whatever the
   stored compute derives from the already-confirmed move. The assertion is
   the workbook's "not draft"; the observed value is logged as the anchor.
10. **TC206 step 11 writes the quantity and the date in one call, as the
    workbook asks.** The guard keys on vals MEMBERSHIP, not on a value
    change (``purchase_order_line.py:107``), and a real quantity increase on
    a confirmed line goes on to call ``_create_or_update_picking``
    (``O17 purchase_stock/models/purchase_order_line.py:164-195``) → the same
    per-line override → one more receipt. That side effect is expected, is
    not asserted against, and is logged.
11. **"No ``account.move`` was created" is a whole-table before/after delta**
    taken inside the test, immediately around the re-promise (TC204 step 11).
    A whole-table equality would violate hard rule 5; a delta over a
    crons-off QA clone with a sequential runner does not (the WF-022
    precedent).

Convention rule 4 (no outbound integrations)
============================================
Nothing here calls a cron, a mail server or ``ir.attachment.dpc_print``. The
only messages produced are ``mail.message`` rows core posts itself
(``message_post_with_source`` at ``O17 purchase_stock/models/
purchase_order.py:258``) — in-database bookkeeping that sends nothing on a
clone with mail servers deactivated.
"""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET

from framework.fg_common import form_arch
from framework.registry import test_case
from tests.wf015.common import (CANDIDATE_DEST_USAGES, OdooRPCError,
                                PINNED_TZ, WORKFLOW, WORKFLOW_NAME,
                                assign_picking, confirm_purchase_order,
                                ensure_vendor, fixture_token,
                                fully_received_error, is_backorder_action,
                                m2o_id, make_product, make_purchase_order,
                                move_lines_of, moves_of_order, open_namespace,
                                order_line_rows, order_picking_ids, order_row,
                                pickings_of, pin_user_timezone,
                                po_line_uom_field, po_line_values,
                                process_backorder, product_display_name,
                                receive_fully, regroup_snapshot,
                                repromise_expecting_error, repromise_line,
                                require_dto_purchase_stock,
                                restore_user_timezone, set_move_quantity,
                                sweep_wf015, trace, user_timezone,
                                validate_picking, vendor_location_id)

MODULE = "dto_purchase_stock"

# ---------------------------------------------------------------------------
# Fixed fixture dates (adaptation 2). Literals, never "today + n", so no
# expected value in this file depends on when the suite runs.
#
# D1_LATE shares D1's calendar date in the pinned timezone and differs only in
# time of day: 08:00 UTC is 03:00 America/Chicago and 15:30 UTC is 10:30, both
# on 2035-06-11. That pair is TC202 step 13's entire subject.
# ---------------------------------------------------------------------------
D1 = "2035-06-11 08:00:00"
D2 = "2035-06-12 08:00:00"
D3 = "2035-06-13 08:00:00"
D4 = "2035-06-18 08:00:00"
D5 = "2035-06-25 08:00:00"
D1_LATE = "2035-06-11 15:30:00"

#: States a receipt is in while it is still workable.
OPEN_PICKING_STATES = ("draft", "waiting", "confirmed", "assigned")

#: Button names that would return a cancelled transfer to a workable state.
#: Verified absent from view_picking_form on BOTH versions: that record carries
#: 15 distinct <button name="…"> nodes on O17 and 17 on O19, and none of these
#: is among them (O17/O19 stock/views/stock_picking_views.xml).
#: action_toggle_is_locked is an ir.actions.server record only (O17 :512 /
#: O19 :490) and never a form button, so listing it here is belt and braces.
RESET_BUTTON_NAMES = ("action_draft", "action_set_draft",
                      "action_back_to_draft", "action_reset",
                      "action_uncancel", "action_unlock", "button_draft",
                      "action_toggle_is_locked")

#: ``OdooRPC.call`` prefixes every server fault with ``"<model>.<method>
#: failed: "`` (adapters/base.py:171-178). TC206 demands the message
#: *exactly*, so the prefix is stripped before comparing — never the message.
_RPC_PREFIX = " failed: "

_CANCEL_LITERAL = "'cancel'"


# ===========================================================================
# Local helpers — none of these exists in tests/wf015/common.py
# ===========================================================================
def _error_tail(message) -> str:
    """The server's own message, with the transport's prefix removed."""
    text = str(message)
    if _RPC_PREFIX in text:
        return text.split(_RPC_PREFIX, 1)[1].strip()
    return text.strip()


def _search_count(rpc, model: str, domain: list) -> int:
    """``search_count`` — a public ORM method, so RPC-dispatchable."""
    return rpc.call(model, "search_count", domain)


def _account_move_count(rpc) -> int:
    """Whole-table ``account.move`` count, or 0 when accounting is absent.

    Only ever used as a before/after delta inside one test (adaptation 11),
    never as a standalone "exactly N" claim.
    """
    if not rpc.model_exists("account.move"):
        return 0
    return _search_count(rpc, "account.move", [])


def _record_artifact(ctx, filename: str, payload, label: str):
    """Persist run evidence next to the execution log."""
    path = ctx.artifacts_dir / filename
    path.write_text(json.dumps(payload, indent=2, sort_keys=True,
                               default=str), encoding="utf-8")
    ctx.add_artifact(path, "log", label)
    return path


def _role_note(roles: str) -> str:
    """One log line recording the workbook roles and why they are not assumed."""
    return (f"workbook roles {roles}: the labels are test data, not group XML "
            f"ids. Neither control in this file is an access rule — "
            f"dto_purchase_stock/security/ir.model.access.csv carries exactly "
            f"one row (the receipt-label wizard for base.group_user) and the "
            f"module declares no res.groups and no ir.rule — so the platform "
            f"session acts throughout, which cleanup requires anyway "
            f"(adaptation 1).")


def _line_row(rpc, order_id: int, line_id: int, fields_=None) -> dict:
    """One ``purchase.order.line``, looked up by id — never by position."""
    for row in order_line_rows(rpc, order_id, fields_):
        if row["id"] == line_id:
            return row
    return {}


def _moves_by_line(rpc, order_id: int) -> dict:
    """``{purchase_line_id: [move rows]}`` for every move of the order.

    Read through ``purchase_line_id`` (``common.moves_of_order``) rather than
    through the pickings, so a move that has just been relocated onto a
    brand-new receipt is still in the set — that is TC203's subject.
    """
    grouped: dict = {}
    for move in moves_of_order(rpc, order_id):
        grouped.setdefault(m2o_id(move.get("purchase_line_id")), []).append(move)
    return grouped


def _open_moves(grouped: dict, line_id: int) -> list:
    """The line's moves that are neither done nor cancelled."""
    return [m for m in grouped.get(line_id, [])
            if m.get("state") not in ("done", "cancel")]


def _sole_open_move(grouped: dict, line_id: int):
    """The line's single open move, or None when there is not exactly one."""
    open_moves = _open_moves(grouped, line_id)
    return open_moves[0] if len(open_moves) == 1 else None


def _picking_of_line(grouped: dict, line_id: int):
    """The picking carrying the line's single open move."""
    move = _sole_open_move(grouped, line_id)
    return m2o_id(move.get("picking_id")) if move else None


def _line_picking_map(grouped: dict, line_ids) -> dict:
    """``{line_id: picking_id}`` over the open moves — the anti-cascade view."""
    return {line_id: _picking_of_line(grouped, line_id) for line_id in line_ids}


def _frozen_move_rows(grouped: dict) -> list:
    """Every done/cancel move, as comparable tuples (TC202 step 12)."""
    rows = []
    for moves in grouped.values():
        for move in moves:
            if move.get("state") in ("done", "cancel"):
                rows.append((move["id"], m2o_id(move.get("picking_id")),
                             move.get("state"), move.get("date_deadline")))
    return sorted(rows)


def _picking_row(rpc, picking_id: int) -> dict:
    """One receipt, read back FRESH — never from a cached earlier read."""
    rows = pickings_of(rpc, [picking_id])
    return rows[0] if rows else {}


def _location_usage(rpc, location_id) -> str | None:
    location_id = m2o_id(location_id)
    if not location_id:
        return None
    return rpc.read("stock.location", [location_id], ["usage"])[0]["usage"]


def _move_tuples(rpc, order_id: int) -> list:
    """The workbook's ``{(picking.name, picking.date_deadline, move.id)}``.

    Kept verbatim for TC202 steps 2 and 6 because both sides are read inside
    ONE execution, where a record id is a legitimate identity. It is never
    carried across environments — that is ``common.regroup_snapshot``'s job,
    which normalises ids and names out (convention rule 5).
    """
    grouped = _moves_by_line(rpc, order_id)
    picking_ids = sorted({m2o_id(m.get("picking_id"))
                          for moves in grouped.values() for m in moves
                          if m2o_id(m.get("picking_id"))})
    by_id = {p["id"]: p for p in pickings_of(rpc, picking_ids)}
    tuples = []
    for moves in grouped.values():
        for move in moves:
            picking = by_id.get(m2o_id(move.get("picking_id")), {})
            tuples.append([picking.get("name"),
                           str(picking.get("date_deadline")), move["id"]])
    return sorted(tuples, key=lambda row: (str(row[0]), row[2]))


def _hidden_at_cancel(expression) -> bool:
    """Does this ``invisible`` expression hide the node when state=='cancel'?

    Only the four shapes core's picking form actually uses are decided here;
    anything else returns False, i.e. "this node may still be visible" — the
    conservative answer, so an unrecognised expression is reported rather
    than silently treated as safe. See adaptation 6.
    """
    text = (expression or "").strip()
    if not text:
        return False
    if text.startswith("state in"):
        return _CANCEL_LITERAL in text
    if text.startswith(("state not in", "state !=", "state ==")):
        return _CANCEL_LITERAL not in text
    return False


def _arch_buttons(arch: str) -> list:
    """``[(name, invisible)]`` for every ``<button>`` in the rendered arch."""
    root = ET.fromstring(arch)
    return [(node.get("name"), node.get("invisible"))
            for node in root.iter("button") if node.get("name")]


def _three_line_order(ctx, dates, labels=("TD-P-04", "TD-P-05", "TD-P-06"),
                      qtys=(10.0, 5.0, 2.0), default_code=None):
    """A CONFIRMED three-line purchase order under this execution's token.

    Returns ``(order_id, vendor_id, product_ids, line_ids)``. Every line gets
    an explicit ``product_qty``, ``price_unit``, UoM and ``date_planned``:
    all four are required or version-renamed, and ``common.po_line_values``
    resolves the UoM and tax keys per version so no branch reaches a body.
    """
    rpc = ctx.adapter.rpc
    vendor_id = ensure_vendor(rpc)
    product_ids = [make_product(ctx, label, default_code=default_code)
                   for label in labels]
    lines = [po_line_values(ctx, product_id, qty, date)
             for product_id, qty, date in zip(product_ids, qtys, dates)]
    order_id = make_purchase_order(ctx, lines, partner_id=vendor_id)
    confirm_purchase_order(rpc, order_id)
    line_ids = [row["id"] for row in order_line_rows(rpc, order_id)]
    return order_id, vendor_id, product_ids, line_ids


def _add_decoy_receipt(ctx, order_id: int, vendor_id: int, product_id: int,
                       date_planned: str) -> tuple:
    """A receipt that IS on ``order.picking_ids`` but fails the pool predicate.

    Built in three moves, because nothing else puts a non-qualifying picking
    within the pool's reach (adaptation 4):

    1. a throwaway fourth line dated ``date_planned`` is added to the
       confirmed order, which makes core call ``_create_or_update_picking``
       (``O17 purchase_stock/models/purchase_order_line.py:164-195``) and so
       the same per-line override, producing a receipt and one move;
    2. a standalone ``stock.picking`` is created whose ``location_dest_id``
       is the vendor's own ``usage='supplier'`` location — outside
       ``('internal','transit','customer')``;
    3. the move and its move lines are re-pointed at it with a plain
       ``picking_id`` write, exactly what ``_update_picking`` does
       (``dto_purchase_stock/models/stock_move.py:25-30``).

    The decoy is then on ``order.picking_ids`` (``picking_ids =
    order_line.move_ids.picking_id``), carries ``date_planned`` as its
    deadline, and is the ONLY picking on the order at that deadline.
    Returns ``(decoy_picking_id, decoy_line_id, decoy_move_id)``.
    """
    rpc = ctx.adapter.rpc
    order = order_row(rpc, order_id)

    values = po_line_values(ctx, product_id, 1.0, date_planned)
    values["order_id"] = order_id
    decoy_line_id = rpc.create("purchase.order.line", values)

    grouped = _moves_by_line(rpc, order_id)
    decoy_move = _sole_open_move(grouped, decoy_line_id)
    if decoy_move is None:
        raise OdooRPCError(
            "the decoy purchase order line produced no single open move, so "
            "TC202 step 11 has nothing to re-point")

    supplier_location_id = vendor_location_id(rpc)
    if not supplier_location_id:
        raise OdooRPCError(
            "no stock.location with usage='supplier' exists on this target, "
            "so TC202 step 11 has no destination outside "
            f"{CANDIDATE_DEST_USAGES} to build the decoy from. Core ships "
            "stock.stock_location_suppliers on both versions, so this is a "
            "broken database rather than a test failure.")
    decoy_picking_id = rpc.create("stock.picking", {
        "picking_type_id": m2o_id(order["picking_type_id"]),
        "partner_id": vendor_id,
        "origin": order["name"],
        "location_id": supplier_location_id,
        "location_dest_id": supplier_location_id,
    })
    # location_dest_id is a stored compute with readonly=False whose
    # _compute_location_id would otherwise take the operation type's default
    # (O17 stock/models/stock_picking.py:461-463, 741-763). An explicit create
    # value wins, but it is verified and re-forced rather than assumed — the
    # picking still has no moves here, so the write propagates to nothing.
    if _location_usage(rpc, _picking_row(rpc, decoy_picking_id)
                       .get("location_dest_id")) in CANDIDATE_DEST_USAGES:
        rpc.write("stock.picking", [decoy_picking_id],
                  {"location_dest_id": supplier_location_id})

    rpc.write("stock.move", [decoy_move["id"]],
              {"picking_id": decoy_picking_id})
    move_line_ids = [row["id"] for row in move_lines_of(rpc,
                                                        [decoy_move["id"]])]
    if move_line_ids:
        rpc.write("stock.move.line", move_line_ids,
                  {"picking_id": decoy_picking_id})
    return decoy_picking_id, decoy_line_id, decoy_move["id"]


def _restore_and_sweep(ctx, rpc, uid, previous_tz):
    """Cleanup that CANNOT raise. Asserting the restoration is the caller's job.

    Hard rule 3: the cleanup step runs in a ``finally:`` and can never raise.
    ``ctx.check`` raises ``AssertionFailed`` on mismatch
    (``framework/context.py:128-135``), so asserting the restoration *inside*
    this helper would let a tz-restore failure replace a real in-body failure
    as the reported error — the exact failure mode hard rule 3 exists to
    prevent. The restoration is still asserted, loudly (a stale
    ``res.users.tz`` changes how every later deadline on this database
    groups), but by ``_assert_timezone_restored`` AFTER the ``try/finally``.
    That is the shape ``test_labels_and_quality.py:1014-1021`` and
    ``:1287-1291`` already use. The WF-013 TC228 precedent, corrected.
    """
    restored = restore_user_timezone(rpc, uid, previous_tz)
    if not restored:
        ctx.log(f"[CRITICAL] could not restore res.users[{uid}].tz to "
                f"{previous_tz!r} — RESTORE IT BY HAND before using this "
                f"database again")
    try:
        sweep_wf015(rpc)
    except Exception as exc:      # noqa: BLE001
        ctx.log(f"[warn] cleanup incomplete: {exc}")


def _assert_timezone_restored(ctx, rpc, uid, previous_tz):
    """The loud half of ``_restore_and_sweep`` — called OUTSIDE the finally."""
    if uid is None:
        return
    ctx.check("the acting user's timezone was restored to its snapshot",
              previous_tz or False, user_timezone(rpc, uid))


def _sweep_quietly(ctx, rpc):
    """The teardown for the cases that pin nothing. Can never raise."""
    try:
        sweep_wf015(rpc)
    except Exception as exc:      # noqa: BLE001
        ctx.log(f"[warn] cleanup incomplete: {exc}")


# ==================================================================== TC201
@test_case(
    id="TEST-WF015-TC201",
    name="A confirmed three-line PO produces three separate receipts, one "
         "per line",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P0", kind="API", order=15201,
    description="button_confirm on a three-line order yields exactly three "
                "receipts on order.picking_ids, each carrying the moves of "
                "exactly one purchase order line, each named by the "
                "operation type's sequence and stamped with the order as "
                "origin; one is validated in full, a second partially with a "
                "backorder scoped to itself, and the third is untouched.",
    traceability=trace("DATAONE-TC201"))
def test_tc201(ctx):
    rpc = ctx.adapter.rpc
    require_dto_purchase_stock(ctx)
    open_namespace(ctx)
    try:
        with ctx.step("Log in as TD-U-02 and open the three-line RFQ."):
            ctx.log(_role_note("TD-U-02 (confirms) / TD-U-03 (receives)"))
            ctx.log(f"fixture token = {fixture_token()}")
            vendor_id = ensure_vendor(rpc)
            product_ids = [make_product(ctx, label)
                           for label in ("TD-P-04", "TD-P-05", "TD-P-06")]
            quantities = (10.0, 5.0, 2.0)
            lines = [po_line_values(ctx, product_id, qty, date)
                     for product_id, qty, date
                     in zip(product_ids, quantities, (D1, D2, D3))]
            order_id = make_purchase_order(ctx, lines, partner_id=vendor_id)
            order = order_row(rpc, order_id)
            line_rows = order_line_rows(rpc, order_id)
            ctx.check("the RFQ is a draft with three lines on three distinct "
                      "Expected Arrival dates",
                      {"state": "draft", "lines": 3,
                       "dates": [D1, D2, D3]},
                      {"state": order["state"], "lines": len(line_rows),
                       "dates": [row["date_planned"] for row in line_rows]})
            line_ids = [row["id"] for row in line_rows]

        with ctx.step("Press Confirm Order."):
            confirm_purchase_order(rpc, order_id)
            # Asserted as a membership test, not a literal: core sends the
            # order straight to 'done' when the company locks confirmed
            # orders (O17 purchase/models/purchase_order.py:493,
            # res_company.py:15-19) and 'done' does not exist on v19. Both
            # values satisfy _create_picking's own filter
            # (O17 purchase_stock/models/purchase_order.py:239).
            confirmed_state = order_row(rpc, order_id)["state"]
            ctx.check_true("the order is confirmed — 'purchase', or 'done' "
                           "where the company locks confirmed orders",
                           confirmed_state in ("purchase", "done"),
                           f"purchase.order.state = {confirmed_state!r}")

        with ctx.step("Assert len(order.picking_ids) == 3."):
            # picking_ids, NEVER search([('origin','=',order.name)]): the
            # by-origin count is N+1 on v17 and N on v19 (module docstring).
            picking_ids = order_picking_ids(rpc, order_id)
            ctx.log("counted from order.picking_ids "
                    "(@api.depends('order_line.move_ids.picking_id'), O17 "
                    "purchase_stock/models/purchase_order.py:36-39, O19 "
                    ":44-47), so core's own empty receipt cannot inflate it")
            ctx.check("exactly three receipts on the order", 3,
                      len(picking_ids))

        with ctx.step("Assert each picking holds moves for exactly one PO "
                      "line: for each picking, len(set(picking.move_ids."
                      "mapped('purchase_line_id'))) == 1."):
            # THE case. Three receipts could also arise from three separate
            # confirmations; only this assertion distinguishes the override
            # (dto_purchase_stock/models/purchase_order_line.py:56-72).
            lines_per_picking = {}
            for move in moves_of_order(rpc, order_id):
                lines_per_picking.setdefault(
                    m2o_id(move.get("picking_id")), set()).add(
                        m2o_id(move.get("purchase_line_id")))
            ctx.check("every receipt carries the moves of exactly one line",
                      {picking_id: 1 for picking_id in sorted(picking_ids)},
                      {picking_id: len(lines_per_picking.get(picking_id,
                                                             set()))
                       for picking_id in sorted(picking_ids)})
            ctx.log("recorded: the override omits core's "
                    ".filtered(lambda l: not l.display_type) guard (O17 "
                    "purchase_stock/models/purchase_order_line.py:338, O19 "
                    ":366), so a section or note line would also get an "
                    "empty receipt. No fixture here uses one.")

        with ctx.step("Assert the three pickings cover the three distinct "
                      "lines with no line appearing twice and none missing."):
            covered = sorted({line_id for lines_ in lines_per_picking.values()
                              for line_id in lines_ if line_id})
            ctx.check("the receipts cover every line exactly once",
                      {"lines_covered": sorted(line_ids),
                       "receipts": 3, "duplicate_lines": []},
                      {"lines_covered": covered,
                       "receipts": len(lines_per_picking),
                       "duplicate_lines":
                           sorted(line_id for line_id in covered
                                  if sum(1 for lines_
                                         in lines_per_picking.values()
                                         if line_id in lines_) > 1)})

        with ctx.step("Assert each picking's picking_type_id is the standard "
                      "incoming type and its partner_id is TD-PA-03."):
            picking_rows = pickings_of(rpc, picking_ids)
            expected_type = m2o_id(order_row(rpc, order_id)["picking_type_id"])
            type_code = rpc.read("stock.picking.type", [expected_type],
                                 ["code", "sequence_code"])[0]
            ctx.check("every receipt is the order's incoming operation type, "
                      "for the order's vendor",
                      {"types": [expected_type] * 3,
                       "partners": [vendor_id] * 3,
                       "code": "incoming"},
                      {"types": [m2o_id(row["picking_type_id"])
                                 for row in picking_rows],
                       "partners": [m2o_id(row["partner_id"])
                                    for row in picking_rows],
                       "code": type_code["code"]})

        with ctx.step("Assert each picking is named by the standard receipt "
                      "sequence."):
            # The operation type's sequence prefix is
            # warehouse.code + '/' + sequence_code + '/' (O17/O19
            # stock/models/stock_picking.py:153-165), so the sequence_code is
            # the version- and warehouse-independent part to look for.
            sequence_code = type_code["sequence_code"]
            names = [row["name"] for row in picking_rows]
            ctx.check("every receipt carries the operation type's sequence "
                      f"prefix {sequence_code!r} and a distinct number",
                      {"unnamed": [], "off_sequence": [], "distinct": 3},
                      {"unnamed": [n for n in names
                                   if not n or n in ("/", "New")],
                       "off_sequence": [n for n in names
                                        if sequence_code not in (n or "")],
                       "distinct": len(set(names))})

        with ctx.step("Assert each picking's origin references the purchase "
                      "order."):
            # _prepare_picking stamps the PO's NAME into origin
            # (O17 purchase_stock/models/purchase_order.py:230).
            order_name = order_row(rpc, order_id)["name"]
            ctx.check("every receipt's origin is the purchase order's name",
                      [order_name] * 3,
                      [row["origin"] for row in picking_rows])

        with ctx.step("Log in as TD-U-03 and validate one of the three "
                      "receipts in full."):
            grouped = _moves_by_line(rpc, order_id)
            picking_of = _line_picking_map(grouped, line_ids)
            full_picking = picking_of[line_ids[0]]
            partial_picking = picking_of[line_ids[1]]
            untouched_picking = picking_of[line_ids[2]]
            receive_fully(ctx, full_picking)
            ctx.check("the first receipt is done", "done",
                      _picking_row(rpc, full_picking)["state"])

        with ctx.step("Assert the other two receipts are unaffected — still "
                      "assigned/confirmed, no backorder created on either."):
            others = pickings_of(rpc, [partial_picking, untouched_picking])
            backorders = rpc.search(
                "stock.picking",
                [("backorder_id", "in",
                  [partial_picking, untouched_picking])])
            ctx.check("the other two receipts are still open and carry no "
                      "backorder",
                      {"open": [True, True], "backorders": []},
                      {"open": [row["state"] in OPEN_PICKING_STATES
                                for row in others],
                       "backorders": sorted(backorders)})

        with ctx.step("Validate a second receipt partially."):
            assign_picking(rpc, partial_picking)
            partial_moves = rpc.search_read(
                "stock.move", [("picking_id", "=", partial_picking)],
                ["product_uom_qty"], order="id")
            ctx.check("the second receipt holds exactly one move for 5 units",
                      [5.0], [row["product_uom_qty"]
                              for row in partial_moves])
            set_move_quantity(rpc, partial_moves[0]["id"], 2.0)
            action = validate_picking(rpc, partial_picking)
            ctx.check("button_validate offers the backorder wizard", True,
                      is_backorder_action(action))
            process_backorder(rpc, partial_picking)
            ctx.check("the partially received receipt is done", "done",
                      _picking_row(rpc, partial_picking)["state"])

        with ctx.step("Assert a backorder was created only for that receipt "
                      "and the third receipt is still untouched."):
            untouched = _picking_row(rpc, untouched_picking)
            ctx.check("exactly one backorder exists, and it belongs to the "
                      "partially received receipt only",
                      {"of_partial": 1, "of_full": 0, "of_untouched": 0,
                       "untouched_still_open": True,
                       "untouched_moves": 1},
                      {"of_partial": len(rpc.search(
                          "stock.picking",
                          [("backorder_id", "=", partial_picking)])),
                       "of_full": len(rpc.search(
                           "stock.picking",
                           [("backorder_id", "=", full_picking)])),
                       "of_untouched": len(rpc.search(
                           "stock.picking",
                           [("backorder_id", "=", untouched_picking)])),
                       "untouched_still_open":
                           untouched["state"] in OPEN_PICKING_STATES,
                       "untouched_moves": len(untouched["move_ids"] or [])})

        with ctx.step("Assert qty_received on each PO line reflects only its "
                      "own receipt's progress."):
            received = {row["id"]: row["qty_received"]
                        for row in order_line_rows(rpc, order_id)}
            ctx.check("each line's received quantity is its own receipt's",
                      {line_ids[0]: 10.0, line_ids[1]: 2.0, line_ids[2]: 0.0},
                      {line_id: received.get(line_id)
                       for line_id in line_ids})

        with ctx.step("Record the mapping {picking.name: purchase_line_id} "
                      "as the baseline artefact."):
            grouped = _moves_by_line(rpc, order_id)
            mapping = {}
            for line_id, moves in grouped.items():
                for move in moves:
                    row = _picking_row(rpc, m2o_id(move.get("picking_id")))
                    mapping.setdefault(row.get("name"), []).append(line_id)
            payload = {
                "token": fixture_token(),
                "environment": ctx.env.key,
                "version": ctx.env.version,
                "order": order_row(rpc, order_id)["name"],
                "picking_name_to_purchase_line_ids":
                    {name: sorted(set(ids)) for name, ids in mapping.items()},
                "normalised_snapshot": regroup_snapshot(ctx, order_id),
            }
            path = _record_artifact(ctx, "tc201_receipt_line_map.json",
                                    payload,
                                    "TC201 receipt → purchase line mapping")
            ctx.log(f"baseline artefact: {path}")
            ctx.check("every receipt in the mapping carries exactly one "
                      "purchase order line",
                      [], [name for name, ids
                           in payload["picking_name_to_purchase_line_ids"]
                           .items() if len(ids) != 1])
    finally:
        _sweep_quietly(ctx, rpc)


# ==================================================================== TC202
@test_case(
    id="TEST-WF015-TC202",
    name="Re-promising a line relocates its move to a receipt whose deadline "
         "matches",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P0", kind="API", order=15202,
    description="purchase.order.line.write({'date_planned': D1}) moves the "
                "line's stock.move onto a receipt whose deadline localises "
                "to D1, keeping the move id and carrying its move lines, "
                "with move.date re-synced; a picking whose destination usage "
                "is outside ('internal','transit','customer') is never "
                "chosen; and the match is made on dates, not datetimes.",
    traceability=trace("DATAONE-TC202"))
def test_tc202(ctx):
    rpc = ctx.adapter.rpc
    require_dto_purchase_stock(ctx)
    open_namespace(ctx)
    uid, previous_tz = None, None
    try:
        with ctx.step("Log in as TD-U-02 with the pinned timezone."):
            ctx.log(_role_note("TD-U-02"))
            uid, previous_tz = pin_user_timezone(ctx)
            ctx.check("the acting user's timezone is pinned", PINNED_TZ,
                      user_timezone(rpc, uid))
            # Lines A and C share D1; line B has D2 (workbook precondition).
            order_id, vendor_id, product_ids, line_ids = _three_line_order(
                ctx, (D1, D2, D1))
            line_a, line_b, line_c = line_ids
            ctx.check("confirmation produced three receipts, none validated",
                      {"receipts": 3, "validated": 0},
                      {"receipts": len(order_picking_ids(rpc, order_id)),
                       "validated": len([
                           row for row in pickings_of(
                               rpc, order_picking_ids(rpc, order_id))
                           if row["state"] in ("done", "cancel")])})

        with ctx.step("Record the tuple set before = {(m.picking_id.name, "
                      "m.picking_id.date_deadline, m.id) for m in "
                      "order.order_line.move_ids}."):
            before = _move_tuples(rpc, order_id)
            grouped_before = _moves_by_line(rpc, order_id)
            frozen_before = _frozen_move_rows(grouped_before)
            picking_before = _line_picking_map(grouped_before, line_ids)
            move_b_before = _sole_open_move(grouped_before, line_b)
            ctx.log(f"before = {before}")
            ctx.log(f"done/cancel moves on the order before the re-promise: "
                    f"{len(frozen_before)} — the workbook's precondition "
                    f"forbids validating any receipt, so this set is "
                    f"legitimately empty (adaptation 5)")
            ctx.check("three moves, one per line, each on its own receipt",
                      {"moves": 3, "distinct_pickings": 3},
                      {"moves": len(before),
                       "distinct_pickings":
                           len(set(picking_before.values()))})

        with ctx.step("Assert line B's move sits on R-B and R-B's deadline "
                      "is D2."):
            rb_id = picking_before[line_b]
            ctx.check("line B's move is on a receipt whose stored deadline "
                      "is D2",
                      {"move_on_its_own_receipt": True, "deadline": D2},
                      {"move_on_its_own_receipt":
                           rb_id not in (picking_before[line_a],
                                         picking_before[line_c]),
                       "deadline": _picking_row(rpc, rb_id)["date_deadline"]})

        with ctx.step("Change line B's Expected Arrival from D2 to D1."):
            repromise_line(rpc, line_b, D1)

        with ctx.step("Save."):
            ctx.check("line B's stored Expected Arrival is D1", D1,
                      _line_row(rpc, order_id, line_b,
                                ["date_planned"])["date_planned"])

        with ctx.step("Record after = {(m.picking_id.name, m.picking_id."
                      "date_deadline, m.id) for m in "
                      "order.order_line.move_ids}."):
            after = _move_tuples(rpc, order_id)
            grouped_after = _moves_by_line(rpc, order_id)
            picking_after = _line_picking_map(grouped_after, line_ids)
            move_b_after = _sole_open_move(grouped_after, line_b)
            ctx.log(f"after = {after}")

        with ctx.step("Assert line B's move now sits on a picking whose "
                      "deadline is D1 — either R-A or R-C, whichever the "
                      "grouping selected."):
            target_id = picking_after[line_b]
            target = _picking_row(rpc, target_id)
            ctx.check("line B's move landed on one of the two D1 receipts",
                      {"is_a_d1_receipt": True, "deadline_date": "2035-06-11",
                       "left_rb": True},
                      {"is_a_d1_receipt":
                           target_id in (picking_before[line_a],
                                         picking_before[line_c]),
                       "deadline_date": str(target["date_deadline"])[:10],
                       "left_rb": target_id != rb_id})

        with ctx.step("Assert the move id is unchanged — the move was "
                      "relocated, not recreated."):
            # _update_picking writes picking_id on the existing move
            # (dto_purchase_stock/models/stock_move.py:25-27); a recreate
            # would show a new id here.
            ctx.check("line B's move kept its identity",
                      {"same_id": True, "moves_for_line_b": 1},
                      {"same_id": bool(move_b_after)
                       and move_b_after["id"] == move_b_before["id"],
                       "moves_for_line_b":
                           len(grouped_after.get(line_b, []))})

        with ctx.step("Assert the move's stock.move.line records followed it "
                      "onto the same picking."):
            move_lines = move_lines_of(rpc, [move_b_after["id"]])
            stranded = [row["id"] for row in move_lines
                        if m2o_id(row.get("picking_id")) != target_id]
            ctx.log(f"line B's move carries {len(move_lines)} "
                    f"stock.move.line record(s) (the move-line write is "
                    f"dto_purchase_stock/models/stock_move.py:28-30)")
            ctx.check("no move line was left behind on the old receipt", [],
                      stranded)

        with ctx.step("Assert move.date was re-synced from date_deadline."):
            # _update_date_from_date_deadline: move.date = move.date_deadline
            # (dto_purchase_stock/models/stock_move.py:34-39).
            ctx.check("the move's date equals its deadline, and both are D1",
                      {"date": D1, "date_deadline": D1},
                      {"date": move_b_after.get("date"),
                       "date_deadline": move_b_after.get("date_deadline")})

        with ctx.step("Assert the candidate pool respected location_dest_id."
                      "usage in ('internal','transit','customer') — a picking "
                      "whose destination is outside that set was not "
                      "chosen."):
            decoy_id, decoy_line, decoy_move = _add_decoy_receipt(
                ctx, order_id, vendor_id, product_ids[2], D4)
            decoy = _picking_row(rpc, decoy_id)
            decoy_usage = _location_usage(rpc, decoy.get("location_dest_id"))
            ctx.check("the decoy receipt is on order.picking_ids, carries D4 "
                      "as its deadline, and fails the pool's destination "
                      "predicate",
                      {"on_picking_ids": True, "deadline": D4,
                       "usage_qualifies": False},
                      {"on_picking_ids":
                           decoy_id in order_picking_ids(rpc, order_id),
                       "deadline": decoy["date_deadline"],
                       "usage_qualifies":
                           decoy_usage in CANDIDATE_DEST_USAGES})
            ctx.log("the decoy is now the ONLY picking on this order at D4, "
                    "so if the predicate at dto_purchase_stock/models/"
                    "purchase_order_line.py:41-44 were dropped it would be "
                    "the single match")

            repromise_line(rpc, line_b, D4)
            grouped_decoy = _moves_by_line(rpc, order_id)
            chosen_id = _picking_of_line(grouped_decoy, line_b)
            chosen = _picking_row(rpc, chosen_id)
            decoy_after = _picking_row(rpc, decoy_id)
            ctx.check("line B's move went to a qualifying receipt and not to "
                      "the decoy, which is untouched",
                      {"chosen_is_the_decoy": False,
                       "chosen_usage_qualifies": True,
                       "chosen_deadline": D4,
                       "decoy_move_ids": [decoy_move]},
                      {"chosen_is_the_decoy": chosen_id == decoy_id,
                       "chosen_usage_qualifies":
                           _location_usage(rpc,
                                           chosen.get("location_dest_id"))
                           in CANDIDATE_DEST_USAGES,
                       "chosen_deadline": chosen["date_deadline"],
                       "decoy_move_ids":
                           sorted(decoy_after.get("move_ids") or [])})

        with ctx.step("Assert no move in state done or cancel anywhere on "
                      "the order was touched."):
            frozen_after = [row for row in
                            _frozen_move_rows(_moves_by_line(rpc, order_id))
                            if row[0] in {r[0] for r in frozen_before}]
            ctx.check("every move that was already done or cancelled is "
                      "byte-for-byte unchanged", frozen_before, frozen_after)
            ctx.log(f"{len(frozen_before)} done/cancel move(s) compared — "
                    f"the comparison is structural while the workbook's own "
                    f"precondition keeps the set empty (adaptation 5)")

        with ctx.step("Assert the deadline comparison used dates, not "
                      "datetimes: repeat with a D1 time-of-day that differs "
                      "from the target picking's and assert the move still "
                      "relocates."):
            # Line B's move is on the D4 receipt after step 11. D1_LATE is
            # 15:30 UTC = 10:30 America/Chicago; the D1 receipts carry 08:00
            # UTC = 03:00. Same local date, different time of day: a port
            # that compared raw datetimes would find no candidate and create
            # yet another receipt (TC203's path) with no error at all.
            before_d1_late = _picking_of_line(_moves_by_line(rpc, order_id),
                                              line_b)
            repromise_line(rpc, line_b, D1_LATE)
            grouped_late = _moves_by_line(rpc, order_id)
            late_move = _sole_open_move(grouped_late, line_b)
            late_picking_id = m2o_id(late_move.get("picking_id"))
            late_picking = _picking_row(rpc, late_picking_id)
            ctx.check("a deadline differing only in time of day still "
                      "relocates the move onto an existing D1 receipt",
                      {"relocated": True,
                       "landed_on_an_existing_d1_receipt": True,
                       "created_a_new_receipt": False,
                       "same_move_id": True,
                       "date_resynced": D1_LATE},
                      {"relocated": late_picking_id != before_d1_late,
                       "landed_on_an_existing_d1_receipt":
                           late_picking_id in (picking_before[line_a],
                                               picking_before[line_c]),
                       "created_a_new_receipt":
                           late_picking_id not in (picking_before[line_a],
                                                   picking_before[line_c],
                                                   before_d1_late),
                       "same_move_id":
                           late_move["id"] == move_b_before["id"],
                       "date_resynced": late_move.get("date")})
            ctx.log(f"target receipt deadline after the late re-promise: "
                    f"{late_picking['date_deadline']!r} — the receipt's own "
                    f"stored deadline is the min over its moves (O17 "
                    f"stock/models/stock_picking.py:684-690), which is why "
                    f"only the localised DATE is asserted")

        with ctx.step("Store before and after as the baseline artefact for "
                      "TC205."):
            payload = {
                "token": fixture_token(),
                "environment": ctx.env.key,
                "version": ctx.env.version,
                "timezone": user_timezone(rpc, uid),
                "dates": {"D1": D1, "D2": D2, "D4": D4,
                          "D1_LATE": D1_LATE},
                "before_raw": before,
                "after_raw": after,
                "normalised_snapshot": regroup_snapshot(ctx, order_id),
            }
            path = _record_artifact(ctx, "tc202_regroup_tuples.json", payload,
                                    "TC202 before/after regroup tuples")
            ctx.log(f"baseline artefact: {path}")
            ctx.log("the RAW tuples carry picking names and move ids and are "
                    "evidence for THIS run only; what TC205 consumes is the "
                    "normalised snapshot, where both identities are replaced "
                    "by per-run ordinals (convention rule 5, "
                    "common.regroup_snapshot)")
            ctx.check("the re-promise changed the tuple set",
                      True, before != after)
    finally:
        if uid is not None:
            _restore_and_sweep(ctx, rpc, uid, previous_tz)
        else:
            _sweep_quietly(ctx, rpc)
    # Outside the finally on purpose: ctx.check raises, and a raise inside
    # a finally would mask a real in-body failure (hard rule 3).
    _assert_timezone_restored(ctx, rpc, uid, previous_tz)


# ==================================================================== TC203
@test_case(
    id="TEST-WF015-TC203",
    name="Re-promising to a date no receipt matches creates a new receipt",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P1", kind="API", order=15203,
    description="With three receipts on three distinct deadlines, moving one "
                "line to a fourth date creates exactly one new receipt at "
                "that deadline, carrying only that line's move (same id) and "
                "its move lines, built from the same _prepare_picking output "
                "as the originals, while no other line's move changes "
                "picking.",
    traceability=trace("DATAONE-TC203"))
def test_tc203(ctx):
    rpc = ctx.adapter.rpc
    require_dto_purchase_stock(ctx)
    open_namespace(ctx)
    uid, previous_tz = None, None
    try:
        with ctx.step("Log in as TD-U-02."):
            ctx.log(_role_note("TD-U-02"))
            uid, previous_tz = pin_user_timezone(ctx)
            order_id, vendor_id, product_ids, line_ids = _three_line_order(
                ctx, (D1, D2, D3))
            line_a, line_b, line_c = line_ids
            ctx.check("confirmation produced three receipts on three "
                      "distinct deadlines, none validated",
                      {"receipts": 3, "deadlines": [D1, D2, D3],
                       "validated": 0},
                      {"receipts": len(order_picking_ids(rpc, order_id)),
                       "deadlines": sorted(
                           row["date_deadline"] for row in pickings_of(
                               rpc, order_picking_ids(rpc, order_id))),
                       "validated": len([
                           row for row in pickings_of(
                               rpc, order_picking_ids(rpc, order_id))
                           if row["state"] in ("done", "cancel")])})

        with ctx.step("Record pickings_before = order.picking_ids.ids and "
                      "the deadline of each."):
            pickings_before = order_picking_ids(rpc, order_id)
            deadlines_before = {row["id"]: row["date_deadline"]
                                for row in pickings_of(rpc, pickings_before)}
            grouped_before = _moves_by_line(rpc, order_id)
            picking_before = _line_picking_map(grouped_before, line_ids)
            move_b_before = _sole_open_move(grouped_before, line_b)
            ctx.log(f"pickings_before = {deadlines_before}")
            ctx.check("no existing receipt carries D4", [],
                      [pid for pid, deadline in deadlines_before.items()
                       if deadline == D4])

        with ctx.step("Change line B's Expected Arrival to D4 — a date no "
                      "existing receipt carries."):
            repromise_line(rpc, line_b, D4)

        with ctx.step("Save."):
            ctx.check("line B's stored Expected Arrival is D4", D4,
                      _line_row(rpc, order_id, line_b,
                                ["date_planned"])["date_planned"])

        with ctx.step("Record pickings_after = order.picking_ids.ids."):
            pickings_after = order_picking_ids(rpc, order_id)
            grouped_after = _moves_by_line(rpc, order_id)
            picking_after = _line_picking_map(grouped_after, line_ids)
            ctx.log(f"pickings_after = {pickings_after}")

        with ctx.step("Assert exactly one new picking id appears in "
                      "pickings_after."):
            added = sorted(set(pickings_after) - set(pickings_before))
            ctx.check("exactly one receipt was added to the order", 1,
                      len(added))
            new_picking_id = added[0]

        with ctx.step("Assert the new picking's deadline is D4."):
            new_picking = _picking_row(rpc, new_picking_id)
            ctx.check("the new receipt's stored deadline is D4", D4,
                      new_picking["date_deadline"])

        with ctx.step("Assert line B's move now sits on it, with the same "
                      "move id as before."):
            move_b_after = _sole_open_move(grouped_after, line_b)
            ctx.check("line B's move was relocated onto the new receipt, not "
                      "recreated",
                      {"picking": new_picking_id,
                       "same_id": True, "moves_on_it": 1},
                      {"picking": picking_after[line_b],
                       "same_id": bool(move_b_after)
                       and move_b_after["id"] == move_b_before["id"],
                       "moves_on_it": len(new_picking.get("move_ids") or [])})

        with ctx.step("Assert the new picking's type, partner and origin "
                      "match the standard _prepare_picking() output."):
            # The originals were produced by the SAME method at confirmation
            # (O17 purchase_stock/models/purchase_order.py:217-235), so they
            # are the reference — no literal is hard-coded, and the version
            # delta in _prepare_picking's key set (O19 :358-373 drops 'date',
            # uses reference_ids) cannot make this brittle.
            reference = _picking_row(rpc, picking_before[line_a])
            keys = ("picking_type_id", "partner_id", "location_id",
                    "location_dest_id", "origin")
            ctx.check("the new receipt matches the confirmation-time "
                      "receipts on every _prepare_picking key",
                      {key: (m2o_id(reference[key])
                             if isinstance(reference[key], (list, tuple))
                             else reference[key]) for key in keys},
                      {key: (m2o_id(new_picking[key])
                             if isinstance(new_picking[key], (list, tuple))
                             else new_picking[key]) for key in keys})

        with ctx.step("Assert no other line's move changed picking."):
            # The anti-cascade assertion, made by picking id PER LINE as the
            # workbook demands: _reassign_picking_by_date_deadline only ever
            # iterates the written line's own moves (dto_purchase_stock/
            # models/purchase_order_line.py:83-88).
            ctx.check("lines A and C are still on the receipts they were on",
                      {line_a: picking_before[line_a],
                       line_c: picking_before[line_c]},
                      {line_a: picking_after[line_a],
                       line_c: picking_after[line_c]})

        with ctx.step("Assert the move's stock.move.line records followed "
                      "it."):
            move_lines = move_lines_of(rpc, [move_b_after["id"]])
            ctx.log(f"line B's move carries {len(move_lines)} "
                    f"stock.move.line record(s)")
            ctx.check("no move line was left behind on the emptied receipt",
                      [], [row["id"] for row in move_lines
                           if m2o_id(row.get("picking_id"))
                           != new_picking_id])

        with ctx.step("Assert the new picking is in a workable state "
                      "(confirmed or assigned), not draft."):
            # Adaptation 9: the picking is created with state='draft' in the
            # vals (dto_purchase_stock/models/stock_move.py:60-63) and
            # nothing in the path confirms or assigns it, so its state is
            # whatever the stored compute derives from the already-confirmed
            # move (O17 stock/models/stock_picking.py:626-673). The observed
            # value is the anchor; what is asserted is what must hold either
            # way.
            state = _picking_row(rpc, new_picking_id)["state"]
            ctx.log(f"[ANCHOR] new receipt state as derived by "
                    f"_compute_state: {state!r}")
            ctx.check("the new receipt is workable — neither draft nor "
                      "cancelled",
                      {"draft_or_cancel": False},
                      {"draft_or_cancel": state in ("draft", "cancel")})
    finally:
        if uid is not None:
            _restore_and_sweep(ctx, rpc, uid, previous_tz)
        else:
            _sweep_quietly(ctx, rpc)
    # Outside the finally on purpose: ctx.check raises, and a raise inside
    # a finally would mask a real in-body failure (hard rule 3).
    _assert_timezone_restored(ctx, rpc, uid, previous_tz)


# ==================================================================== TC204
@test_case(
    id="TEST-WF015-TC204",
    name="A receipt left with no moves is cancelled, not deleted",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P1", kind="HYBRID", order=15204,
    description="After a re-promise empties it, the receipt still exists, is "
                "in state cancel with is_locked set, holds no moves, keeps "
                "its sequence number, is findable under the cancelled "
                "domain, offers no affordance back to a workable state, "
                "drops off purchase.order.picking_ids, and produced no "
                "account.move.",
    traceability=trace("DATAONE-TC204"))
def test_tc204(ctx):
    rpc = ctx.adapter.rpc
    require_dto_purchase_stock(ctx)
    open_namespace(ctx)
    uid, previous_tz = None, None
    try:
        with ctx.step("Log in as TD-U-02."):
            ctx.log(_role_note("TD-U-02"))
            uid, previous_tz = pin_user_timezone(ctx)
            order_id, vendor_id, product_ids, line_ids = _three_line_order(
                ctx, (D1, D2, D3))
            line_a, line_b, line_c = line_ids
            ctx.check("confirmation produced three receipts", 3,
                      len(order_picking_ids(rpc, order_id)))

        with ctx.step("Record rb_id = R-B.id and rb_name = R-B.name before "
                      "the re-promise."):
            grouped_before = _moves_by_line(rpc, order_id)
            picking_before = _line_picking_map(grouped_before, line_ids)
            rb_id = picking_before[line_b]
            rb_before = _picking_row(rpc, rb_id)
            rb_name = rb_before["name"]
            moves_before = _account_move_count(rpc)
            ctx.log(f"R-B = id {rb_id}, name {rb_name!r}, state "
                    f"{rb_before['state']!r}, is_locked "
                    f"{rb_before['is_locked']!r}")
            ctx.log(f"account.move rows before the re-promise: "
                    f"{moves_before} (the baseline for step 11, taken after "
                    f"the fixture was staged — adaptation 11)")
            ctx.check("R-B holds exactly line B's single move and is open",
                      {"moves": 1, "open": True},
                      {"moves": len(rb_before.get("move_ids") or []),
                       "open": rb_before["state"] in OPEN_PICKING_STATES})

        with ctx.step("Perform the re-promise that moves R-B's only move "
                      "onto another receipt."):
            # D1 already carries a receipt (line A's), so the move relocates
            # rather than creating one, and R-B is left empty — the exact
            # condition _update_picking cancels
            # (dto_purchase_stock/models/stock_move.py:31-32).
            repromise_line(rpc, line_b, D1)
            grouped_after = _moves_by_line(rpc, order_id)
            ctx.check("line B's move is now on line A's receipt",
                      picking_before[line_a],
                      _picking_of_line(grouped_after, line_b))

        with ctx.step("Assert env['stock.picking'].browse(rb_id).exists() is "
                      "not empty — the record still exists."):
            ctx.check("the emptied receipt was not deleted", [rb_id],
                      rpc.search("stock.picking", [("id", "=", rb_id)]))

        with ctx.step("Assert R-B.state == 'cancel'."):
            # Read back through a FRESH search_read in its own RPC
            # transaction: state is a stored compute whose no-moves branch
            # yields 'draft' (O17 :656-657, O19 :845-846) and only the
            # recompute-then-force order inside action_cancel makes 'cancel'
            # stick, so a later invalidation is exactly what would flip it.
            rb_after = _picking_row(rpc, rb_id)
            ctx.check("the emptied receipt is cancelled and locked",
                      {"state": "cancel", "is_locked": True},
                      {"state": rb_after["state"],
                       "is_locked": rb_after["is_locked"]})

        with ctx.step("Assert len(R-B.move_ids) == 0 or that all its moves "
                      "are themselves cancelled."):
            residual = rpc.search_read("stock.move",
                                       [("picking_id", "=", rb_id)],
                                       ["state"], order="id")
            ctx.check("R-B holds no move, or only cancelled ones",
                      {"moves": 0, "not_cancelled": []},
                      {"moves": len(residual),
                       "not_cancelled": [row["id"] for row in residual
                                         if row["state"] != "cancel"]})

        with ctx.step("Assert R-B.name is unchanged — the receipt number was "
                      "not reused or renumbered."):
            ctx.check("the receipt number survived the cancellation",
                      rb_name, _picking_row(rpc, rb_id)["name"])
            ctx.check("no other transfer took that number over", [rb_id],
                      rpc.search("stock.picking", [("name", "=", rb_name)]))

        with ctx.step("Assert R-B is findable in the transfers list under a "
                      "Cancelled filter."):
            # Adaptation 7: stock.view_picking_internal_search ships no named
            # Cancelled filter (O17 stock/views/stock_picking_views.xml:368;
            # its status filters are draft/waiting/available at :387-389 and
            # a Status group-by at :413), so the assertion uses the domain
            # that facet produces, scoped to this execution's vendor.
            found = rpc.search("stock.picking",
                               [("state", "=", "cancel"),
                                ("partner_id", "=", vendor_id)])
            ctx.log("core ships no named 'Cancelled' filter on "
                    "stock.view_picking_internal_search — the facet is the "
                    "Status group-by plus [('state','=','cancel')]")
            ctx.check("the cancelled receipt is returned by "
                      "[('state','=','cancel')], scoped to this run's vendor",
                      True, rb_id in found)

        with ctx.step("Assert R-B cannot be returned to a workable state "
                      "from the UI — record the absence of that affordance."):
            # ARCH check plus the one compute that gates the remaining
            # button — adaptation 6. This is not a behavioural claim about
            # the ORM: action_cancel has no inverse and nothing here calls
            # one.
            arch = form_arch(ctx, "stock.picking", "form")
            buttons = _arch_buttons(arch)
            visible_at_cancel = sorted({name for name, invisible in buttons
                                        if not _hidden_at_cancel(invisible)})
            ctx.log(f"buttons in the rendered stock.picking form whose "
                    f"invisible expression does not hide them at "
                    f"state=='cancel': {visible_at_cancel}")
            by_name = {}
            for name, invisible in buttons:
                by_name.setdefault(name, []).append(invisible)
            ctx.check("no affordance returns a cancelled transfer to a "
                      "workable state",
                      {"reset_buttons": [],
                       "action_confirm_hidden_at_cancel": True,
                       "button_validate_hidden_at_cancel": True,
                       "action_cancel_hidden_at_cancel": True,
                       "check_availability_gate": False},
                      {"reset_buttons":
                           sorted(name for name in by_name
                                  if name in RESET_BUTTON_NAMES),
                       "action_confirm_hidden_at_cancel":
                           all(_hidden_at_cancel(expr) for expr
                               in by_name.get("action_confirm", [None])),
                       "button_validate_hidden_at_cancel":
                           all(_hidden_at_cancel(expr) for expr
                               in by_name.get("button_validate", [None])),
                       "action_cancel_hidden_at_cancel":
                           all(_hidden_at_cancel(expr) for expr
                               in by_name.get("action_cancel", [None])),
                       "check_availability_gate":
                           rpc.read("stock.picking", [rb_id],
                                    ["show_check_availability"])[0]
                           ["show_check_availability"]})
            ctx.log("WF-015 E6, made explicit: cancellation is irreversible "
                    "from the UI, so a mis-grouping bug destroys receipt "
                    "records rather than merely mis-filing them — which is "
                    "the argument for TC205's baseline-and-replay approach.")

        with ctx.step("Assert the purchase order still references R-B in "
                      "picking_ids (or record whether it does — capture the "
                      "v17 behaviour exactly)."):
            # Adaptation 8: the verified answer is the opposite of the
            # obvious one. picking_ids = order_line.move_ids.picking_id
            # (O17 purchase_stock/models/purchase_order.py:36-39, O19
            # :44-47), so an emptied receipt is not on it — on either
            # version. The workbook's wording allows recording this.
            picking_ids = order_picking_ids(rpc, order_id)
            ctx.log("[ANCHOR] the workbook allows 'or record whether it "
                    "does'; the verified behaviour is that the emptied, "
                    "cancelled receipt DROPS OFF purchase.order.picking_ids, "
                    "because that field is computed from "
                    "order_line.move_ids.picking_id")
            ctx.check("the cancelled empty receipt is no longer on "
                      "purchase.order.picking_ids, and the order still shows "
                      "its two surviving receipts",
                      {"rb_on_picking_ids": False, "receipts": 2},
                      {"rb_on_picking_ids": rb_id in picking_ids,
                       "receipts": len(picking_ids)})

        with ctx.step("Assert no account.move was produced by the "
                      "cancellation."):
            ctx.check("no journal entry appeared across the re-promise, and "
                      "the cancelled receipt has none of its own",
                      {"account_move_delta": 0,
                       "moves_left_on_the_cancelled_receipt": []},
                      {"account_move_delta":
                           _account_move_count(rpc) - moves_before,
                       "moves_left_on_the_cancelled_receipt":
                           rpc.search("stock.move",
                                      [("picking_id", "=", rb_id)])})
    finally:
        if uid is not None:
            _restore_and_sweep(ctx, rpc, uid, previous_tz)
        else:
            _sweep_quietly(ctx, rpc)
    # Outside the finally on purpose: ctx.check raises, and a raise inside
    # a finally would mask a real in-body failure (hard rule 3).
    _assert_timezone_restored(ctx, rpc, uid, previous_tz)


# ==================================================================== TC206
@test_case(
    id="TEST-WF015-TC206",
    name="The Expected Arrival date of a fully received line cannot be "
         "changed",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P1", kind="API", order=15206,
    description="A fully received line refuses a date_planned write with the "
                "exact f-string at purchase_order_line.py:104 and rolls it "
                "back; a partially received line is re-promised normally; a "
                "draft order is not guarded at all; writing the quantity in "
                "the same vals bypasses the lock by design; and the locked "
                "(done) order raises the identical message.",
    traceability=trace("DATAONE-TC206"))
def test_tc206(ctx):
    rpc = ctx.adapter.rpc
    require_dto_purchase_stock(ctx)
    open_namespace(ctx)
    try:
        with ctx.step("Log in as TD-U-02 and open the confirmed PO."):
            ctx.log(_role_note("TD-U-02"))
            # default_code=False: the message interpolates
            # product_id.DISPLAY_NAME, which renders '[CODE] Name' whenever
            # the product carries an internal reference. Only a code-less
            # product reproduces the workbook's literal "Product X" form
            # (dto_purchase_stock/models/purchase_order_line.py:104).
            vendor_id = ensure_vendor(rpc)
            product_a = make_product(ctx, "TD-P-04", default_code=False)
            product_b = make_product(ctx, "TD-P-05", default_code=False)
            order_id = make_purchase_order(
                ctx, [po_line_values(ctx, product_a, 10.0, D1),
                      po_line_values(ctx, product_b, 5.0, D2)],
                partner_id=vendor_id)
            confirm_purchase_order(rpc, order_id)
            line_a, line_b = [row["id"] for row
                              in order_line_rows(rpc, order_id)]
            grouped = _moves_by_line(rpc, order_id)
            picking_a = _picking_of_line(grouped, line_a)
            picking_b = _picking_of_line(grouped, line_b)

            receive_fully(ctx, picking_a)

            assign_picking(rpc, picking_b)
            move_b = rpc.search_read("stock.move",
                                     [("picking_id", "=", picking_b)],
                                     ["product_uom_qty"], order="id")[0]
            set_move_quantity(rpc, move_b["id"], 2.0)
            action = validate_picking(rpc, picking_b)
            ctx.check("the partial receipt offered the backorder wizard",
                      True, is_backorder_action(action))
            process_backorder(rpc, picking_b)

            # The workbook's second precondition: a locked/done order with a
            # fully received line. Built now so step 12 has it.
            order2_id = make_purchase_order(
                ctx, [po_line_values(ctx, product_a, 3.0, D1)],
                partner_id=vendor_id, label="PO-LOCKED")
            confirm_purchase_order(rpc, order2_id)
            line2_id = order_line_rows(rpc, order2_id)[0]["id"]
            receive_fully(ctx, order_picking_ids(rpc, order2_id)[0])

            # The state is a membership test for the same reason as TC201's
            # step 2: 'done' is what core writes when the company locks
            # confirmed orders, and the guard under test accepts both
            # (purchase_order_line.py:98).
            order_state = order_row(rpc, order_id)["state"]
            ctx.check("the confirmed order carries a fully received line A "
                      "and a partially received line B",
                      {"confirmed": True, "received": [10.0, 2.0],
                       "ordered": [10.0, 5.0]},
                      {"confirmed": order_state in ("purchase", "done"),
                       "received": [row["qty_received"] for row
                                    in order_line_rows(rpc, order_id)],
                       "ordered": [row["product_qty"] for row
                                   in order_line_rows(rpc, order_id)]})
            ctx.log(f"purchase.order.state after confirmation: "
                    f"{order_state!r}")

        with ctx.step("Assert line A has qty_received == product_qty."):
            row_a = _line_row(rpc, order_id, line_a)
            ctx.check("line A is fully received — the condition that arms "
                      "the guard (float_compare(...) == 0)",
                      row_a["product_qty"], row_a["qty_received"])
            date_a_before = row_a["date_planned"]

        with ctx.step("Change line A's Expected Arrival to a different date "
                      "and attempt to save."):
            message = repromise_expecting_error(rpc, line_a, D5)
            ctx.log(f"server response: {message!r}")

        with ctx.step("Assert a UserError is raised."):
            ctx.check("the write was refused", True, bool(message))

        with ctx.step("Assert the message is exactly Cannot update the "
                      "Expected Arrival date because Product X is fully "
                      "received — with Product X replaced by line A's "
                      "product name."):
            # The exact string, verbatim from purchase_order_line.py:104 via
            # common.fully_received_error: an f-string NOT wrapped in _(),
            # interpolating display_name, with NO trailing period.
            ctx.check("the server message, verbatim",
                      fully_received_error(
                          product_display_name(rpc, product_a)),
                      _error_tail(message))

        with ctx.step("Assert line A's stored date_planned is unchanged."):
            # Each RPC call is its own transaction, so the refusal really was
            # rolled back and this read sees the untouched stored value.
            ctx.check("the refused write left the stored date alone",
                      date_a_before,
                      _line_row(rpc, order_id, line_a)["date_planned"])

        with ctx.step("Change line B's (partially received) Expected Arrival "
                      "and save."):
            grouped_before = _moves_by_line(rpc, order_id)
            open_b_before = _sole_open_move(grouped_before, line_b)
            picking_b_before = m2o_id(open_b_before.get("picking_id"))
            repromise_line(rpc, line_b, D5)

        with ctx.step("Assert the save succeeds and triggers the TC202 "
                      "regroup path."):
            grouped_after = _moves_by_line(rpc, order_id)
            open_b_after = _sole_open_move(grouped_after, line_b)
            picking_b_after = m2o_id(open_b_after.get("picking_id"))
            new_picking = _picking_row(rpc, picking_b_after)
            ctx.check("line B was re-promised and its open backorder move "
                      "moved onto a receipt carrying the new deadline, with "
                      "move.date re-synced",
                      {"date_planned": D5, "relocated": True,
                       "same_move_id": True, "picking_deadline": D5,
                       "move_date": D5, "move_deadline": D5},
                      {"date_planned":
                           _line_row(rpc, order_id, line_b)["date_planned"],
                       "relocated": picking_b_after != picking_b_before,
                       "same_move_id":
                           open_b_after["id"] == open_b_before["id"],
                       "picking_deadline": new_picking["date_deadline"],
                       "move_date": open_b_after.get("date"),
                       "move_deadline": open_b_after.get("date_deadline")})

        with ctx.step("Open a draft/RFQ order with a fully received line "
                      "(construct if the fixture allows) and assert the date "
                      "can be changed — the guard is scoped to purchase and "
                      "done states."):
            # A draft order has no pickings, so the guard's third condition is
            # armed the cheap legitimate way: float_compare(product_qty,
            # qty_received) == 0 is also true when BOTH are zero
            # (purchase_order_line.py:99-103). What is left varying is the
            # order state, which is this step's whole subject.
            draft_order_id = make_purchase_order(
                ctx, [po_line_values(ctx, product_a, 0.0, D1)],
                partner_id=vendor_id, label="PO-DRAFT")
            draft_line_id = order_line_rows(rpc, draft_order_id)[0]["id"]
            draft_row = order_line_rows(rpc, draft_order_id)[0]
            ctx.check("the draft order's line arms the quantity half of the "
                      "guard and nothing else",
                      {"state": "draft", "product_qty": 0.0,
                       "qty_received": 0.0},
                      {"state": order_row(rpc, draft_order_id)["state"],
                       "product_qty": draft_row["product_qty"],
                       "qty_received": draft_row["qty_received"]})
            draft_error = repromise_expecting_error(rpc, draft_line_id, D5)
            ctx.check("the guard does not fire on a draft order",
                      {"raised": False, "date_planned": D5},
                      {"raised": bool(draft_error),
                       "date_planned":
                           order_line_rows(rpc, draft_order_id)[0]
                           ["date_planned"]})
            ctx.log(f"draft-order error message (expected empty): "
                    f"{draft_error!r}")

        with ctx.step("On the fully received line A, change both the "
                      "quantity and the date in the same write."):
            # Adaptation 10: the guard keys on vals MEMBERSHIP, not on a
            # value change (purchase_order_line.py:107). The quantity really
            # is increased, as the workbook asks; core then calls
            # _create_or_update_picking for the changed line, which reaches
            # the same per-line override and produces one more receipt. That
            # side effect is expected and is not asserted against.
            uom_field = po_line_uom_field(rpc)
            ctx.log(f"the guard's bypass tests the literal 'product_uom' "
                    f"(purchase_order_line.py:107) while this target's "
                    f"purchase.order.line UoM field is {uom_field!r} — on "
                    f"v19 the rename silently disables one half of it")
            combined_error = ""
            try:
                rpc.write("purchase.order.line", [line_a],
                          {"product_qty": row_a["product_qty"] + 1.0,
                           "date_planned": D5})
            except OdooRPCError as exc:
                combined_error = _error_tail(exc)

        with ctx.step("Assert the write succeeds — the guard fires only when "
                      "date_planned is in vals without product_uom or "
                      "product_qty. Record this as the documented by-design "
                      "bypass."):
            row_a_after = _line_row(rpc, order_id, line_a)
            ctx.check("the combined write bypassed the lock entirely",
                      {"raised": False, "date_planned": D5,
                       "product_qty": row_a["product_qty"] + 1.0},
                      {"raised": bool(combined_error),
                       "date_planned": row_a_after["date_planned"],
                       "product_qty": row_a_after["product_qty"]})
            ctx.log("[FINDING] BR-3 has a real hole: a user who edits the "
                    "quantity and the date together bypasses the "
                    "fully-received lock completely "
                    "(dto_purchase_stock/models/purchase_order_line.py:107). "
                    "The workbook records this as by design; it is recorded "
                    "here, not worked around.")

        with ctx.step("Repeat step 3 on the locked/done order and assert the "
                      "same exact error."):
            # EXPECTED v19 OUTCOME: FAIL. purchase.order.state loses
            # ('done','Locked') on v19 (O17 purchase/models/
            # purchase_order.py:98-105 -> O19 :105-111, which gains a locked
            # Boolean at :112-116) and button_done (O17 :526-527) goes with
            # it, so a locked order is no longer protected. The workbook
            # expectation is immutable (hard rule 2): the assertion stays as
            # written and the v19 baseline FAIL is the recorded result.
            lock_error = ""
            try:
                rpc.call("purchase.order", "button_done", [order2_id])
            except OdooRPCError as exc:
                lock_error = _error_tail(exc)
            if lock_error:
                ctx.log(f"button_done was not dispatchable: {lock_error!r}")
            locked_message = repromise_expecting_error(rpc, line2_id, D5)
            ctx.log(f"locked-order server response: {locked_message!r}")
            ctx.check("the locked order is in state 'done' and refuses the "
                      "re-promise with the identical message",
                      {"order_state": "done", "raised": True,
                       "message": fully_received_error(
                           product_display_name(rpc, product_a))},
                      {"order_state": order_row(rpc, order2_id)["state"],
                       "raised": bool(locked_message),
                       "message": _error_tail(locked_message)})
    finally:
        _sweep_quietly(ctx, rpc)
