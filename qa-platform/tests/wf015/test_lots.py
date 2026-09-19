"""DATAONE-WF-015 — auto-lot on receipt validation: TC215, TC216.

Two halves of one AND-gate. Abbreviations used below: ``OCA`` =
``D:/Projects/dataone/DTO-Odoo/3rd-addons/stock_picking_auto_create_lot``,
``O17`` = ``D:/Projects/dataone/odoo-17.0``, ``O19`` =
``D:/Projects/odoo-19.0``.

What this file proves
---------------------
**The gate itself.** ``_set_auto_lot`` (``OCA/models/stock_picking.py:46-60``)
is two filters, and BOTH must pass before a single lot name is drawn::

    pickings = self.filtered(                            # :50
        lambda p: p.picking_type_id.auto_create_lot)
    lines = pickings.mapped("move_line_ids").filtered(
        lambda x: (not x.lot_id and not x.lot_name       # :52-53
                   and x.product_id.tracking != "none"   # :54
                   and x.product_id.auto_create_lot))    # :55
    for line in lines:
        line.lot_name = line._get_lot_sequence()         # :60

``_get_lot_sequence`` is ``ir.sequence.next_by_code("stock.lot.serial")``
(``OCA/models/stock_move_line.py:10-12``) — one call **per move line**, so N
eligible lines consume exactly N numbers. The two flags are
``product.template.auto_create_lot`` (``OCA/models/product.py:9``) and
``stock.picking.type.auto_create_lot``
(``OCA/models/stock_picking_type.py:9``).

**TC215 — both flags set.** The entry point is ``button_validate``, which the
OCA module overrides as a **public** method (``OCA/models/stock_picking.py:
66-68``) calling ``_set_auto_lot`` before ``super()``. It is therefore fully
reachable over ``/web/dataset/call_kw`` and nothing private is re-implemented
here. ``_set_auto_lot`` in fact runs **twice** on that path — once from
``button_validate`` (``:67``) and once from ``_action_done`` (``:62-64``),
which core's ``button_validate`` reaches — and the second run is a no-op
because the ``not x.lot_name`` half of the line filter (``:52``) now excludes
every line. That is why step 10's answer is "advanced by exactly 2" and not
by 4, and the test asserts the sequence delta rather than trusting the
narrative.

Step 4's "the Assign Serial Numbers button is not displayed" is
``stock.move.display_assign_serial``, and the override that forces it False
(``OCA/models/stock_move.py:16-23``) applies **only** when
``picking_type_id.auto_create_lot and product_id.auto_create_lot``
(``:18-20``). Core's own value differs by version — ``O17
stock/models/stock_move.py:206`` is ``has_tracking == 'serial' and
display_import_lot`` while ``O19 :264`` is ``display_import_lot`` alone — so
for the lot-tracked product of this case the v17 value would be False anyway
and only on v19 does the override do the work. The test therefore asserts
``display_assign_serial`` False **together with** ``display_import_lot`` True
(``O17 :199-205`` / ``O19 :257-263``): either half alone is not evidence,
because ``display_import_lot`` False would hide the button for the unrelated
reason that the whole lot UI is off on the operation type.

Step 11's lots are core's, not the module's: ``stock.move.line._action_done``
routes a line whose picking type has ``use_create_lots`` into
``ml_ids_to_check`` (``O17 stock/models/stock_move_line.py:610-613`` / ``O19
:634-640``), searches ``stock.lot`` by ``lot_name`` (``O17 :622-626``) and
creates what is missing through ``_create_and_assign_production_lot``
(``O17 :644``, defined ``:711-729`` / ``O19 :756``), which also writes
``lot_id`` back onto the line. So after validation a line carries **both**
``lot_name`` and ``lot_id``, and step 11 asserts the ``stock.lot`` rows plus
that equality.

**TC216 — the product flag missing.** Same operation type, still flagged
``auto_create_lot`` (recorded, per the workbook precondition, never flipped),
and a **serial**-tracked product that does not carry the product flag. The
line filter's ``x.product_id.auto_create_lot`` half (``OCA/models/
stock_picking.py:55``) excludes every line, so nothing is drawn and the
``stock.lot.serial`` counter must not move — steps 6 and 12, the leak
detectors. The fixture pins ``tracking='serial'`` deliberately: it is the one
tracking value for which core's ``display_assign_serial`` agrees across
versions (see the v17/v19 pair above), which is what makes step 11's
"the affordance was available" a stable assertion rather than a version
artefact. It is read **before** validation because both computes exclude
``state in ('done', 'cancel')`` (``O17 :204`` / ``O19 :262``).

Step 5 is **recorded, not guessed**, exactly as the workbook's own note
demands. Two different core paths can refuse the same receipt and they raise
different strings: ``_sanity_check`` (``O17 stock/models/stock_picking.py:
1088-1126``, message at ``:1117``) when the lines are picked, and
``stock.move.line._action_done`` (``O17 :640`` / ``O19 :671``, whose wording
already differs on v19) when they are not. Both are core's messages, not
DataOne's, so the test asserts what must hold either way — the receipt did
not reach ``done``, no lot name appeared, the sequence did not move — and
logs the observed text verbatim as the v17 baseline.

Expected outcomes
-----------------
* ``TC215`` — **EXPECTED v17 OUTCOME: PASS**, with step 12 rewritten (see
  adaptation 6). v19: PASS unless the ``quantity`` / ``quantity_product_uom``
  / ``picked`` semantics the workbook's ``v19_watch`` names have changed.
* ``TC216`` — **EXPECTED v17 OUTCOME: PASS.** Step 5 captures the v17
  behaviour instead of asserting a literal. v19: PASS; it would diverge for a
  **lot**-tracked product, which is why the fixture is serial-tracked.

Both open with ``common.require_auto_create_lot``, which reports BLOCKED with
a precise reason when the OCA module is not contributing to the target or
when the ``stock.lot.serial`` sequence is missing — the suite-wide runtime
caveat recorded in ``tests/wf015/common.py`` applies here too.

Documented adaptations (hard rules 3, 5 and 6)
----------------------------------------------
1. **No pre-existing operation type is modified.** Both cases need an
   incoming type flagged ``auto_create_lot``, so ``common.make_picking_type``
   **copies** the company's incoming type into a token-named one
   (``stock.picking.type.copy`` is public and marshals back as an id). Every
   flag this file needs is then written on that copy, never on the shared
   record.
2. **``use_create_lots`` is forced True on that copy**, and the fixture says
   so out loud. It gates three separate things the two cases depend on:
   core's per-unit line split for serial products (``O17
   stock/models/stock_move.py:1697-1699`` / ``O19 :2096-2098``),
   ``display_import_lot`` and therefore ``display_assign_serial``
   (``O17 :201`` / ``O19 :259``), and the creation of ``stock.lot`` rows from
   ``lot_name`` at validation (``O17 stock/models/stock_move_line.py:
   610-613``). ``create_backorder`` is pinned to ``'ask'`` on the same copy so
   that step 12's "no backorder wizard" is a real observation and not a
   consequence of the type saying "never" (``O17 stock/models/
   stock_picking.py:1252-1253``).
3. **TC215's two move lines are created explicitly.** Core splits a move into
   one line per unit only for **serial** tracking (``O17 stock/models/
   stock_move.py:1697-1699``); the lot-tracked move of TC215 falls into the
   ``elif`` at ``:1700`` and gets ONE line carrying the whole quantity. The
   workbook's precondition is "two move lines", so the fixture normalises the
   move to exactly two picked lines of 1 through the public ORM. TC216 needs
   no split — its serial product gets two lines from ``_action_assign`` — and
   runs through the same normaliser so both cases start from the same shape.
4. **The move lines are marked ``picked`` before Validate.** That is the
   receiving clerk's own tick, and without it every validation in this file
   would return the backorder wizard instead of doing its job:
   ``_get_picked_quantity`` returns 0 when the move is picked but its lines
   are not (``O17 stock/models/stock_move.py:1575-1585``), which sends
   ``_check_backorder`` (``:1248-1261``) into
   ``_action_generate_backorder_wizard`` (``O17 stock/models/stock_picking.py:
   1206-1211``) — a third outcome that is neither of the two TC216 step 5
   names, and a false failure for TC215 step 12.
5. **The ``stock.lot.serial`` row is selected the way ``next_by_code``
   selects it** — ``search([('code','=',…), ('company_id','in',[company,
   False])], order='company_id')`` and take the first (``O17
   odoo/addons/base/models/ir_sequence.py:279-292`` / ``O19 :279-292``, the
   search at ``:287`` on both). ``common.lot_sequence_row`` orders by ``id``,
   which returns core's company-less row on a database that also carries a
   company-specific one — the row ``next_by_code`` would NOT have consumed.
   ``number_next_actual`` is read rather than ``number_next`` because with
   ``implementation='standard'`` the latter is a compute over the PostgreSQL
   sequence (``O17 ir_sequence.py:100-108``, field at ``:143``). A sequence
   with ``use_date_range`` set advances a **sub**-sequence instead, so the
   fixture BLOCKS on that rather than asserting a delta that cannot move.
6. **TC215 step 12 is rewritten, and this is a finding, not a shortcut.**
   ``stock.move._set_quantities_to_reservation`` (``OCA/models/stock_move.py:
   26-40``) is **dead code**: a full-tree grep of ``O17`` and ``O19`` returns
   zero definitions and zero callers of that name, and the override's own
   first statement is ``super()._set_quantities_to_reservation()``, which
   would raise ``AttributeError`` if it were ever invoked. The backorder
   suppression the workbook attributes to it does not happen. The step
   asserts the **observable** — ``button_validate`` on a fully quantified,
   fully picked receipt returns ``True`` and no backorder picking exists —
   and logs the finding, attributing that outcome to nothing.
7. **TC215 step 14 is a cross-check owned by TC212.** What is always asserted
   is the label template's own expression evaluated on the records:
   ``lot_id.name or lot_name`` per ``stock.move.line``
   (``dto_purchase_stock/reports/report_receipt_product_label.xml:18-26``,
   the loop at ``:56-63``). The rendered half is added when
   ``dto_purchase_stock``'s Dymo report is present on the target and is
   logged, not demanded, when it is not — the runtime caveat in
   ``common.py`` makes that module's presence a per-target fact, and TC215's
   own workbook ``modules`` column names only the OCA module.
8. **No impersonation.** Both workbook step 1s read "Log in as TD-U-03". The
   label is test data, not a group XML id, and auto-lot is not an access
   rule: ``_set_auto_lot`` reads only the two flags, the line's lot fields and
   the product's tracking (``OCA/models/stock_picking.py:50-58``). The
   platform session is used and the mapping is logged at step 1.
9. **The sequence is a global counter.** The deltas in steps 10 and 12 are
   before/after readings taken inside one test, which is sound on the
   sequential runner against a crons-off QA clone; they are never a claim
   about the sequence's absolute value, and every fixture (vendor, product,
   operation type, vendor lot name) carries ``common.fixture_token()``.
"""
import re

from framework.registry import test_case
from tests.wf015.common import (LOT_SEQUENCE_CODE, WORKFLOW, WORKFLOW_NAME,
                                XMLID_REPORT_DYMO, OdooRPCError,
                                assign_picking, default_picking_type,
                                ensure_vendor, is_backorder_action, lots_named,
                                m2o_id, make_picking_type, make_product,
                                move_lines_of, open_namespace, own_company_id,
                                product_row, render_report, report_record,
                                require_auto_create_lot, sku, sweep_wf015,
                                trace, validate_picking, vendor_location_id)

MODULE = "stock_picking_auto_create_lot"

#: The workbook role on both cases. Logged, never impersonated — see the
#: module docstring, adaptation 8.
_ROLE_NOTE = (
    "workbook role TD-U-03 (dto_stock, Inventory User / Receiving clerk): the "
    "label is test data, not a res.groups XML id, and auto-lot is not an "
    "access rule — stock_picking_auto_create_lot/models/stock_picking.py:"
    "50-58 reads only picking_type_id.auto_create_lot, the line's lot_id / "
    "lot_name, product tracking and product_id.auto_create_lot. The platform "
    "session creates and sweeps the fixtures.")

#: The two ir.sequence readings that decide steps 8, 9, 10 and 12.
_SEQ_FIELDS = ("number_next_actual", "number_next", "number_increment",
               "prefix", "suffix", "padding", "implementation",
               "use_date_range", "company_id")

_DIGIT_TAIL = re.compile(r"(\d+)\s*$")


# ===========================================================================
# Local helpers — none of these exists in tests/wf015/common.py
# ===========================================================================
def _lot_sequence_row(rpc) -> dict | None:
    """The ``stock.lot.serial`` row ``next_by_code`` would actually consume.

    ``common.lot_sequence_row`` answers the same question with ``order="id"``,
    which on a database carrying BOTH core's company-less sequence and a
    company-specific one returns the wrong row: ``ir.sequence.next_by_code``
    searches ``[('code','=',code), ('company_id','in',[company, False])]``
    with ``order='company_id'`` and takes the first, and PostgreSQL sorts
    NULLs last — so the company-specific row wins (v17
    ``odoo/addons/base/models/ir_sequence.py:279-292``, the search at
    ``:287``; v19 identical at ``:279-292``). Reading a row the module never
    touched would make every delta in this file zero.
    """
    company_id = own_company_id(rpc)
    fields_ = [f for f in _SEQ_FIELDS if rpc.field_exists("ir.sequence", f)]
    rows = rpc.search_read("ir.sequence",
                           [("code", "=", LOT_SEQUENCE_CODE),
                            ("company_id", "in", [company_id, False])],
                           fields_, order="company_id", limit=1)
    return rows[0] if rows else None


def _sequence_baseline(ctx):
    """``(row, number_next_actual)`` for ``stock.lot.serial``, or BLOCKED.

    ``number_next_actual`` rather than ``number_next``: with
    ``implementation='standard'`` the latter is a compute that predicts the
    PostgreSQL sequence's next value (v17 ``ir_sequence.py:100-108``, field
    ``:143``), so the stored reading is the reliable one. A ``use_date_range``
    sequence advances a sub-sequence instead of this record, which would make
    every delta assertion in this file read zero no matter what happened —
    that is an environment deviation from what core ships (``stock/data/
    stock_sequence_data.xml:36-44`` on v17, ``:26-34`` on v19, both flat), so
    it BLOCKS with the reason rather than failing the feature under test.
    """
    rpc = ctx.adapter.rpc
    row = _lot_sequence_row(rpc)
    if row is None:
        ctx.blocked(
            f"No ir.sequence with code {LOT_SEQUENCE_CODE!r} is visible to "
            f"company {own_company_id(rpc)} on {ctx.env.key} "
            f"(db={ctx.env.db}). "
            "stock_picking_auto_create_lot/models/stock_move_line.py:10-12 "
            "draws every auto lot name from it through next_by_code, which "
            "scopes the search to [company, False] (odoo/addons/base/models/"
            "ir_sequence.py:287).")
    if row.get("use_date_range"):
        ctx.blocked(
            f"The {LOT_SEQUENCE_CODE!r} sequence on {ctx.env.key} has "
            "use_date_range enabled, so next_by_code advances a "
            "ir.sequence.date_range sub-sequence and this record's "
            "number_next_actual never moves. Steps 8, 9, 10 and 12 are "
            "before/after readings of that counter and cannot be evaluated. "
            "Core ships the sequence flat (v17 stock/data/"
            "stock_sequence_data.xml:36-44, v19 :26-34).")
    return row, row["number_next_actual"]


def _sequence_now(rpc) -> int:
    """The current ``number_next_actual``, re-read (never cached)."""
    row = _lot_sequence_row(rpc)
    return row["number_next_actual"] if row else -1


def _sequence_number(name, prefix="", suffix=""):
    """The numeric value a sequence-drawn name carries, or ``None``.

    Core ships ``stock.lot.serial`` with an empty prefix and padding 7, but a
    database may have set either, so the stored prefix/suffix are stripped
    first and the trailing digit run is what is read. ``None`` means the name
    did not come from a numeric sequence at all — which is a failure the
    caller must surface, never swallow.
    """
    text = str(name or "")
    if suffix and text.endswith(suffix):
        text = text[:-len(suffix)]
    if prefix and text.startswith(prefix):
        text = text[len(prefix):]
    match = _DIGIT_TAIL.search(text)
    return int(match.group(1)) if match else None


def _internal_location_id(rpc):
    """A destination location for the fixture receipt, when the operation
    type declares none (``stock.picking.type.default_location_dest_id`` is a
    plain Many2one on v17 ``stock/models/stock_picking.py:38`` and a stored
    compute on v19 ``:38-39``; either can be empty)."""
    rows = rpc.search_read("stock.location",
                           [("usage", "=", "internal"),
                            ("company_id", "in",
                             [own_company_id(rpc), False])],
                           ["id"], order="id", limit=1)
    return rows[0]["id"] if rows else None


def _auto_lot_picking_type(ctx, label):
    """A token-named incoming type flagged ``auto_create_lot``, and its row.

    A COPY of the company's incoming type — hard rule 3 forbids flipping a
    flag on the shared record. ``use_create_lots`` and ``create_backorder``
    are then pinned on the copy for the reasons in the module docstring
    (adaptation 2); both writes are logged.
    """
    rpc = ctx.adapter.rpc
    source_id = default_picking_type(rpc, "incoming",
                                     company_id=own_company_id(rpc))
    type_id = make_picking_type(rpc, label, code="incoming",
                                auto_create_lot=True, source_id=source_id)
    fixes = {}
    row = _picking_type_row(rpc, type_id)
    if not row.get("use_create_lots"):
        fixes["use_create_lots"] = True
    if row.get("create_backorder") != "ask":
        fixes["create_backorder"] = "ask"
    if fixes:
        rpc.write("stock.picking.type", [type_id], fixes)
        ctx.log(f"fixture operation type {type_id} (a copy of {source_id}): "
                f"pinned {fixes} on the COPY — the shared record is untouched")
        row = _picking_type_row(rpc, type_id)
    return type_id, row


def _picking_type_row(rpc, type_id) -> dict:
    fields_ = [f for f in ("name", "code", "auto_create_lot",
                           "use_create_lots", "use_existing_lots",
                           "create_backorder", "default_location_src_id",
                           "default_location_dest_id")
               if rpc.field_exists("stock.picking.type", f)]
    return rpc.read("stock.picking.type", [type_id], fields_)[0]


def _make_receipt(ctx, picking_type_id, partner_id, product_id, qty):
    """A draft receipt with ONE move, confirmed and assigned.

    Built straight on ``stock.picking`` rather than through a purchase order:
    both cases belong to ``stock_picking_auto_create_lot`` alone (the
    workbook's ``modules`` column), and DataOne's per-line receipt engine
    would otherwise produce one receipt PER purchase order line
    (``dto_purchase_stock/models/purchase_order_line.py:56-72``), which is the
    opposite of the single receipt these preconditions describe.

    ``stock.move.name`` is supplied only where it exists: it is
    ``required=True`` on v17 (``stock/models/stock_move.py:30``) and was
    dropped from the model on v19. ``product_uom`` keeps its name on both
    (v17 ``:62`` / v19 ``:67``), and the locations are passed explicitly
    because v17's ``stock.move.location_id`` is required with no compute
    (``:71-80``) while v19 computes it (``:75-84``).
    """
    rpc = ctx.adapter.rpc
    type_row = _picking_type_row(rpc, picking_type_id)
    source_id = (m2o_id(type_row.get("default_location_src_id"))
                 or vendor_location_id(rpc))
    dest_id = (m2o_id(type_row.get("default_location_dest_id"))
               or _internal_location_id(rpc))
    row = product_row(rpc, product_id, ["display_name", "uom_id"])
    move = {"product_id": product_id,
            "product_uom_qty": qty,
            "product_uom": m2o_id(row["uom_id"]),
            "location_id": source_id,
            "location_dest_id": dest_id,
            "picking_type_id": picking_type_id}
    if rpc.field_exists("stock.move", "name"):
        move["name"] = row["display_name"]
    picking_id = rpc.create("stock.picking", {
        "partner_id": partner_id,
        "picking_type_id": picking_type_id,
        "location_id": source_id,
        "location_dest_id": dest_id,
        "move_ids": [(0, 0, move)]})
    assign_picking(rpc, picking_id)
    move_ids = rpc.search("stock.move", [("picking_id", "=", picking_id)])
    return picking_id, (move_ids[0] if move_ids else None)


def _normalise_lines(ctx, move_id, quantities):
    """Force a move to carry exactly ``len(quantities)`` PICKED move lines.

    Core hands back a different shape per tracking mode — one line per unit
    for serial, one line for the whole quantity otherwise (``O17
    stock/models/stock_move.py:1697-1700``) — and neither is picked, because
    ``stock.move.line.create`` copies the move's own ``picked``
    (``O17 stock/models/stock_move_line.py:347-348``) and the move is not
    picked at assign time. See the module docstring, adaptations 3 and 4.

    Only public ORM primitives are used; ``company_id``, ``product_uom_id``
    and both locations are left to the create hook and the precomputes, which
    read them off ``move_id`` on both versions (``O17 :341-352, 92-99,
    123-128`` / ``O19 :346-357``).
    """
    rpc = ctx.adapter.rpc
    product_id = m2o_id(rpc.read("stock.move", [move_id],
                                 ["product_id"])[0]["product_id"])
    line_ids = [row["id"] for row in move_lines_of(rpc, [move_id])]
    ctx.log(f"move {move_id}: _action_assign produced {len(line_ids)} move "
            f"line(s); normalising to {len(quantities)}")
    while len(line_ids) > len(quantities):
        rpc.unlink("stock.move.line", [line_ids.pop()])
    while len(line_ids) < len(quantities):
        line_ids.append(rpc.create("stock.move.line", {
            "move_id": move_id,
            "product_id": product_id,
            "quantity": quantities[len(line_ids)],
            "picked": True}))
    for line_id, quantity in zip(line_ids, quantities):
        rpc.write("stock.move.line", [line_id],
                  {"quantity": quantity, "picked": True})
    return sorted(line_ids)


def _line_facts(rpc, move_id) -> list:
    """``[{quantity, lot_name, lot}]`` per move line, ordered by id.

    ``lot`` is ``lot_id``'s display name, so the pair is exactly what the
    label template reads as ``lot_id.name or lot_name``
    (``dto_purchase_stock/reports/report_receipt_product_label.xml:18-26``).
    Both are normalised to ``""`` when empty: a Many2one comes back as
    ``False`` and a Char as ``False`` or ``''`` depending on the version
    (``O19 orm/fields_textual.py:38``), and a mismatch dict must not turn
    that into a difference.
    """
    facts = []
    for row in move_lines_of(rpc, [move_id]):
        lot = row.get("lot_id")
        facts.append({"quantity": row.get("quantity"),
                      "lot_name": row.get("lot_name") or "",
                      "lot": (lot[1] if lot else "")})
    return facts


def _press_validate(rpc, picking_id):
    """``button_validate`` — PUBLIC — as ``(raised, message, result)``.

    Never raises a bare ``AssertionError`` and never swallows the return
    value: TC215 step 6 asserts the result IS ``True`` (no dialog of any
    kind), TC215 step 12 asserts it is not the backorder act_window, and
    TC216 step 5 records whichever of the two arms the server chose.
    """
    try:
        return False, "", validate_picking(rpc, picking_id)
    except OdooRPCError as exc:
        return True, str(exc), None


def _picking_state(rpc, picking_id) -> str:
    return rpc.read("stock.picking", [picking_id], ["state"])[0]["state"]


def _backorders_of(rpc, picking_id) -> list:
    """Receipts created as a backorder of this one — the observable half of
    TC215 step 12 (``stock.picking.backorder_id`` exists on both versions)."""
    if not rpc.field_exists("stock.picking", "backorder_id"):
        return []
    return rpc.search("stock.picking", [("backorder_id", "=", picking_id)])


def _lot_rows_for(rpc, product_id, names) -> list:
    """``stock.lot`` rows with these names, scoped to the fixture product.

    Scoped so a live lot that happens to share a name cannot satisfy the
    assertion (hard rule 5); ``common.lots_named`` searches by name alone.
    """
    return sorted(row["name"] for row in lots_named(rpc, names)
                  if m2o_id(row.get("product_id")) == product_id)


# ===========================================================================
# TC215
# ===========================================================================
@test_case(
    id="TEST-WF015-TC215",
    name="Validating a receipt auto-creates lot names for auto-lot products",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P1", kind="HYBRID", order=15215,
    description="With both auto_create_lot flags set, button_validate draws "
                "one stock.lot.serial number per move line before super() — "
                "two distinct, consecutive lot names, the sequence advanced "
                "by exactly two, the stock.lot rows created by core, no "
                "dialog and no backorder — and a vendor-keyed lot on a second "
                "receipt survives untouched.",
    traceability=trace("DATAONE-TC215"))
def test_tc215(ctx):
    rpc = ctx.adapter.rpc
    require_auto_create_lot(ctx)
    open_namespace(ctx)
    try:
        with ctx.step("Log in as TD-U-03 and open the receipt."):
            ctx.log(_ROLE_NOTE)
            type_id, type_row = _auto_lot_picking_type(ctx, "AUTOLOT-IN")
            ctx.check("the fixture operation type is an incoming COPY "
                      "carrying auto_create_lot and use_create_lots",
                      {"code": "incoming", "auto_create_lot": True,
                       "use_create_lots": True, "create_backorder": "ask"},
                      {"code": type_row.get("code"),
                       "auto_create_lot": type_row.get("auto_create_lot"),
                       "use_create_lots": type_row.get("use_create_lots"),
                       "create_backorder": type_row.get("create_backorder")})

            # TD-P-02 FG-CABLE-002: lot-tracked AND flagged auto_create_lot.
            product_id = make_product(ctx, "TD-P-02 FG-CABLE-002",
                                      tracking="lot", auto_create_lot=True)
            product = product_row(rpc, product_id,
                                  ["tracking", "auto_create_lot"])
            ctx.check("TD-P-02 is lot-tracked and flagged auto_create_lot",
                      {"tracking": "lot", "auto_create_lot": True},
                      {"tracking": product.get("tracking"),
                       "auto_create_lot": product.get("auto_create_lot")})

            vendor_id = ensure_vendor(rpc, "TD-PA-03")
            picking_id, move_id = _make_receipt(ctx, type_id, vendor_id,
                                                product_id, 2.0)
            line_ids = _normalise_lines(ctx, move_id, [1.0, 1.0])
            state = _picking_state(rpc, picking_id)
            # 'assigned' is what an incoming move from a supplier location
            # reaches (O17 stock/models/stock_move.py:1678-1699 takes the
            # bypass-reservation branch), but adding a line can send the
            # stored state compute back to 'confirmed' and _set_auto_lot's
            # filter (OCA stock_picking.py:50-58) reads no state at all — so
            # the fixture assertion is "ready to validate", and the observed
            # value is recorded.
            ctx.check_true("the receipt holds two move lines and is ready to "
                           "validate",
                           len(line_ids) == 2
                           and state in ("assigned", "confirmed"),
                           f"{len(line_ids)} move line(s), "
                           f"stock.picking.state = {state!r}")

        with ctx.step("Record seq_before = sequence('stock.lot.serial')."
                      "number_next."):
            seq_row, seq_before = _sequence_baseline(ctx)
            increment = seq_row.get("number_increment") or 1
            ctx.log(f"ir.sequence[{seq_row['id']}] {LOT_SEQUENCE_CODE}: "
                    f"number_next_actual={seq_before} "
                    f"number_increment={increment} "
                    f"implementation={seq_row.get('implementation')!r} "
                    f"prefix={seq_row.get('prefix')!r} "
                    f"company_id={seq_row.get('company_id')}")

        with ctx.step("Assert both move lines have neither lot_id nor "
                      "lot_name."):
            ctx.check("both move lines start empty of lot_id and lot_name",
                      [{"lot_name": "", "lot": ""},
                       {"lot_name": "", "lot": ""}],
                      [{"lot_name": row["lot_name"], "lot": row["lot"]}
                       for row in _line_facts(rpc, move_id)])

        with ctx.step("Assert the Assign Serial Numbers button is not "
                      "displayed (display_assign_serial forced False)."):
            flags = rpc.read("stock.move", [move_id],
                             [f for f in ("display_assign_serial",
                                          "display_import_lot", "has_tracking")
                              if rpc.field_exists("stock.move", f)])[0]
            # display_import_lot True is the control: it proves the button is
            # hidden by the OCA override (models/stock_move.py:18-22) and not
            # because the lot UI is off on the operation type (O17
            # stock/models/stock_move.py:199-205 / O19 :257-263).
            ctx.check("display_assign_serial is forced False while the lot "
                      "UI itself is on",
                      {"display_assign_serial": False,
                       "display_import_lot": True, "has_tracking": "lot"},
                      {"display_assign_serial":
                           flags.get("display_assign_serial"),
                       "display_import_lot": flags.get("display_import_lot"),
                       "has_tracking": flags.get("has_tracking")})

        with ctx.step("Press Validate."):
            # NOT YET DIAGNOSED, and the evidence so far is recorded here
            # so the next attempt does not repeat it.
            #
            # button_validate raises "You need to supply a Lot/Serial
            # Number", which means stock_picking_auto_create_lot's
            # _set_auto_lot() ran (the override calls it BEFORE super(),
            # stock_picking.py:66-68) and left lot_name empty.
            #
            # Ruled out, all measured on d1v19:
            #   * the module is installed, 19.0.1.0.0
            #   * stock.picking.type.auto_create_lot exists and is True on
            #     the fixture type (asserted in step 2 above)
            #   * product.template.auto_create_lot exists and is True, and
            #     product.product.auto_create_lot is related to it, so the
            #     filter's `x.product_id.auto_create_lot` term resolves
            #   * stock.picking.move_line_ids and stock.move.line.lot_name
            #     both exist and are stored
            #   * the picking is 'assigned' with exactly two move lines,
            #     both empty of lot_id and lot_name (asserted in step 4)
            #
            # So every term of _set_auto_lot's filter looks satisfiable and
            # the write target exists. Settling it needs to see INSIDE the
            # call — which RPC cannot do: _set_auto_lot is private and
            # "Private methods cannot be called remotely". The next step is
            # an Odoo shell on this database, not another RPC probe.
            raised, message, result = _press_validate(rpc, picking_id)
            ctx.log(f"button_validate raised={raised} message={message!r} "
                    f"result={result!r}")

        with ctx.step("Assert no manual-lot dialog appeared."):
            # button_validate returns True only when it ran to completion
            # (O17 stock/models/stock_picking.py:1191); every dialog — the
            # lot-entry wizard, the backorder confirmation, the reception
            # report — comes back as a dict instead.
            ctx.check("button_validate completed without raising and "
                      "returned no action of any kind",
                      {"raised": False, "result": True},
                      {"raised": raised, "result": result})

        with ctx.step("Assert the receipt is done."):
            ctx.check("stock.picking.state", "done",
                      _picking_state(rpc, picking_id))

        with ctx.step("Assert both move lines now carry a lot_name drawn from "
                      "stock.lot.serial."):
            facts = _line_facts(rpc, move_id)
            names = [row["lot_name"] for row in facts]
            numbers = [_sequence_number(name, seq_row.get("prefix") or "",
                                        seq_row.get("suffix") or "")
                       for name in names]
            # The window the sequence can have yielded for this run: two draws
            # from seq_before, one per eligible move line (OCA stock_picking.py
            # :59-60 calls _get_lot_sequence once per line).
            window = sorted(seq_before + index * increment
                            for index in range(2))
            ctx.check("both lines carry a lot_name, and the two names are the "
                      "two numbers stock.lot.serial yielded for this run",
                      {"lot_names_set": 2, "numbers": window},
                      {"lot_names_set": sum(1 for name in names if name),
                       "numbers": sorted(numbers)
                       if all(n is not None for n in numbers) else names})

        with ctx.step("Assert the two lot names are distinct and "
                      "consecutive."):
            ctx.check("the two auto lot names are distinct", 2,
                      len(set(names)))
            # 'Consecutive' is read off the record — number_increment, not a
            # hard-coded 1 (ir.sequence.number_increment, O17 ir_sequence.py:
            # 147 / O19 :145; core ships this sequence with 1, stock/data/
            # stock_sequence_data.xml:42 on v17 and :32 on v19).
            ctx.check("the two lot numbers differ by exactly one "
                      "number_increment", increment,
                      abs(numbers[1] - numbers[0]))

        with ctx.step("Assert sequence.number_next advanced by exactly 2."):
            # Exactly 2, not 4: _set_auto_lot runs twice on this path (OCA
            # stock_picking.py:67 from button_validate and :63 from
            # _action_done) and the second run draws nothing because the
            # 'not x.lot_name' half of the line filter (:52) now excludes
            # every line.
            ctx.check("number_next_actual advanced by two draws and no more",
                      2 * increment, _sequence_now(rpc) - seq_before)

        with ctx.step("Assert core created the corresponding stock.lot "
                      "records at validation."):
            ctx.check("two stock.lot rows exist for TD-P-02 with exactly "
                      "those names, and each move line points at its own",
                      {"lots": sorted(names),
                       "line_lot_matches_lot_name": [True, True]},
                      {"lots": _lot_rows_for(rpc, product_id, names),
                       "line_lot_matches_lot_name":
                           [row["lot"] == row["lot_name"]
                            for row in _line_facts(rpc, move_id)]})

        with ctx.step("Assert the backorder wizard did not pop spuriously — "
                      "_set_quantities_to_reservation() set quantity = "
                      "quantity_product_uom on the already-lotted lines."):
            # REWRITTEN, and the reason is a finding (module docstring,
            # adaptation 6): stock.move._set_quantities_to_reservation does
            # not exist in Odoo core on either version, so the mechanism the
            # workbook names never runs. What is asserted is the observable;
            # the outcome is attributed to nothing.
            ctx.check("validation returned no backorder confirmation and left "
                      "no backorder receipt behind",
                      {"backorder_action": False, "backorders": []},
                      {"backorder_action": is_backorder_action(result),
                       "backorders": _backorders_of(rpc, picking_id)})
            ctx.log(
                "FINDING — stock.move._set_quantities_to_reservation "
                "(3rd-addons/stock_picking_auto_create_lot/models/"
                "stock_move.py:26-40) is dead code: a full-tree grep of "
                "D:/Projects/dataone/odoo-17.0 and D:/Projects/odoo-19.0 "
                "finds zero definitions and zero callers of that name, and "
                "the override's first statement is "
                "super()._set_quantities_to_reservation(), which would raise "
                "AttributeError if it were ever invoked. No backorder wizard "
                "appears here because the receipt is fully quantified and "
                "every move line is picked (O17 stock/models/stock_move.py:"
                "1575-1585, stock/models/stock_picking.py:1248-1261) — not "
                "because of that override.")

        with ctx.step("On a second receipt, key a vendor-supplied lot on one "
                      "of two lines, validate, and assert the keyed lot "
                      "survives untouched while the other line receives an "
                      "auto lot (WF-015 A4 — _set_auto_lot() touches only "
                      "lines with no lot_id and no lot_name)."):
            seq_before_second = _sequence_now(rpc)
            second_id, second_move = _make_receipt(ctx, type_id, vendor_id,
                                                   product_id, 2.0)
            second_lines = _normalise_lines(ctx, second_move, [1.0, 1.0])
            vendor_lot = sku("VENDOR-LOT")
            rpc.write("stock.move.line", [second_lines[0]],
                      {"lot_name": vendor_lot})

            raised2, message2, result2 = _press_validate(rpc, second_id)
            ctx.log(f"second receipt: raised={raised2} message={message2!r} "
                    f"result={result2!r}")

            second_facts = _line_facts(rpc, second_move)
            second_names = [row["lot_name"] for row in second_facts]
            auto_name = ([name for name in second_names if name != vendor_lot]
                         or [""])[0]
            auto_number = _sequence_number(auto_name,
                                           seq_row.get("prefix") or "",
                                           seq_row.get("suffix") or "")
            ctx.check("the vendor lot is stored verbatim, the other line got "
                      "exactly one auto lot, and the sequence advanced by one "
                      "draw only",
                      {"raised": False, "state": "done",
                       "vendor_lot_kept": 1, "auto_lot_number":
                           seq_before_second, "sequence_delta": increment},
                      {"raised": raised2,
                       "state": _picking_state(rpc, second_id),
                       "vendor_lot_kept":
                           sum(1 for name in second_names
                               if name == vendor_lot),
                       "auto_lot_number": auto_number,
                       "sequence_delta":
                           _sequence_now(rpc) - seq_before_second})
            ctx.check("both second-receipt lines end with a stock.lot of "
                      "their own name",
                      sorted([vendor_lot, auto_name]),
                      _lot_rows_for(rpc, product_id,
                                    [vendor_lot, auto_name]))

        with ctx.step("Assert the generated lot names appear on the receipt "
                      "labels (cross-check against TC212 step 11)."):
            # Always asserted: the label template's own expression, evaluated
            # on the records it loops over — docs -> o.move_ids ->
            # move.move_line_ids (dto_purchase_stock/reports/
            # report_receipt_product_label.xml:56-63), printing
            # lot_id.name or lot_name per line (:18-26).
            printed = sorted(row["lot"] or row["lot_name"]
                             for row in _line_facts(rpc, move_id))
            ctx.check("the label expression 'lot_id.name or lot_name' yields "
                      "the two auto lot names, one per stock.move.line",
                      sorted(names), printed)

            report = report_record(rpc, XMLID_REPORT_DYMO)
            if not report:
                # TC215's workbook 'modules' column names only
                # stock_picking_auto_create_lot; the Dymo report belongs to
                # dto_purchase_stock, whose presence on a given target is the
                # open runtime question recorded in tests/wf015/common.py.
                ctx.log(f"{XMLID_REPORT_DYMO} is absent on {ctx.env.key}, so "
                        "the rendered half of this cross-check is recorded as "
                        "unavailable and stays with TEST-WF015-TC212 step 11; "
                        "the record-level assertion above still holds.")
            else:
                try:
                    html = render_report(ctx, report["report_name"],
                                         [picking_id], converter="html")
                except OSError as exc:
                    ctx.log(f"the /report/html route for "
                            f"{report['report_name']} could not be read "
                            f"({exc}); the rendered half stays with "
                            f"TEST-WF015-TC212 step 11.")
                else:
                    ctx.check("both auto lot names appear in the rendered "
                              "Dymo label stream",
                              {name: True for name in sorted(names)},
                              {name: (name in html) for name in sorted(names)})
    finally:
        # Best effort by design: a validated receipt cannot be unlinked, so it
        # is the per-execution token — not the sweep — that guarantees
        # isolation (tests/wf015/common.py, sweep_wf015). Can never raise.
        try:
            sweep_wf015(rpc)
        except Exception:  # noqa: BLE001
            pass


# ===========================================================================
# TC216
# ===========================================================================
@test_case(
    id="TEST-WF015-TC216",
    name="A tracked product without auto_create_lot still requires a manual "
         "lot or serial",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P2", kind="API", order=15216,
    description="On an operation type that IS flagged auto_create_lot, a "
                "serial-tracked product that is not stops validation, "
                "consumes nothing from stock.lot.serial and keeps its Assign "
                "Serial Numbers affordance; the vendor's two serials are "
                "then stored verbatim and become two stock.lot records.",
    traceability=trace("DATAONE-TC216"))
def test_tc216(ctx):
    rpc = ctx.adapter.rpc
    require_auto_create_lot(ctx)
    open_namespace(ctx)
    try:
        with ctx.step("Log in as TD-U-03 and open the receipt."):
            ctx.log(_ROLE_NOTE)
            type_id, type_row = _auto_lot_picking_type(ctx, "AUTOLOT-IN")
            # The workbook precondition is "the incoming operation type's
            # auto_create_lot setting is recorded" — it is recorded here, and
            # it is deliberately the SAME flagged copy TC215 uses, because
            # that is what makes the product half of the AND-gate at
            # OCA/models/stock_picking.py:55 the only thing under test.
            ctx.log("recorded operation type setting: auto_create_lot="
                    f"{type_row.get('auto_create_lot')!r}, use_create_lots="
                    f"{type_row.get('use_create_lots')!r}, use_existing_lots="
                    f"{type_row.get('use_existing_lots')!r} — on the "
                    "token-named COPY, never on the shared record")
            ctx.check("the operation type IS flagged auto_create_lot, so only "
                      "the product flag can decide the outcome",
                      {"code": "incoming", "auto_create_lot": True,
                       "use_create_lots": True},
                      {"code": type_row.get("code"),
                       "auto_create_lot": type_row.get("auto_create_lot"),
                       "use_create_lots": type_row.get("use_create_lots")})

            # TD-P-01 FG-CABLE-001: serial-tracked, NOT flagged.
            product_id = make_product(ctx, "TD-P-01 FG-CABLE-001",
                                      tracking="serial")
            product = product_row(rpc, product_id,
                                  ["tracking", "auto_create_lot"])
            ctx.check("TD-P-01 is serial-tracked and NOT flagged "
                      "auto_create_lot",
                      {"tracking": "serial", "auto_create_lot": False},
                      {"tracking": product.get("tracking"),
                       "auto_create_lot": product.get("auto_create_lot")})

            vendor_id = ensure_vendor(rpc, "TD-PA-03")
            picking_id, move_id = _make_receipt(ctx, type_id, vendor_id,
                                                product_id, 2.0)
            line_ids = _normalise_lines(ctx, move_id, [1.0, 1.0])
            state = _picking_state(rpc, picking_id)
            ctx.check_true("the receipt holds two move lines for 2 units of "
                           "TD-P-01 and is ready to validate",
                           len(line_ids) == 2
                           and state in ("assigned", "confirmed"),
                           f"{len(line_ids)} move line(s), "
                           f"stock.picking.state = {state!r}")

            # Captured HERE for step 11: both versions' computes return False
            # once the move is done (O17 stock/models/stock_move.py:204 /
            # O19 :262), so reading it after validation would prove nothing.
            affordance = rpc.read("stock.move", [move_id],
                                  [f for f in ("display_assign_serial",
                                               "display_import_lot",
                                               "has_tracking")
                                   if rpc.field_exists("stock.move", f)])[0]
            ctx.log(f"captured before validation for step 11: {affordance}")

        with ctx.step("Record seq_before = sequence('stock.lot.serial')."
                      "number_next."):
            seq_row, seq_before = _sequence_baseline(ctx)
            ctx.log(f"ir.sequence[{seq_row['id']}] {LOT_SEQUENCE_CODE}: "
                    f"number_next_actual={seq_before} "
                    f"number_increment={seq_row.get('number_increment')} "
                    f"company_id={seq_row.get('company_id')}")

        with ctx.step("Assert the move lines have no lot_id and no lot_name."):
            ctx.check("both move lines start empty of lot_id and lot_name",
                      [{"lot_name": "", "lot": ""},
                       {"lot_name": "", "lot": ""}],
                      [{"lot_name": row["lot_name"], "lot": row["lot"]}
                       for row in _line_facts(rpc, move_id)])

        with ctx.step("Press Validate."):
            raised, message, result = _press_validate(rpc, picking_id)

        with ctx.step("Assert validation is refused or the manual "
                      "serial-entry path is presented — record which, "
                      "exactly, as the v17 behaviour."):
            # RECORDED, not guessed. Both arms are core's, and they raise
            # different strings: _sanity_check (O17 stock/models/
            # stock_picking.py:1088-1126, message :1117) for picked lines, and
            # stock.move.line._action_done (O17 :640 / O19 :671, already
            # reworded on v19) otherwise. What must hold either way is that
            # the receipt did not reach 'done'.
            observed = ("refused with a server error" if raised
                        else f"returned {result!r} without raising")
            ctx.log(f"OBSERVED v17 BEHAVIOUR (baseline for the v19 "
                    f"comparison): button_validate {observed}"
                    + (f"; message: {message!r}" if raised else ""))
            state = _picking_state(rpc, picking_id)
            ctx.check("validation did not complete: the receipt is not done, "
                      "and the server either refused it or handed back a "
                      "wizard",
                      {"reached_done": False, "silently_completed": False},
                      {"reached_done": state == "done",
                       "silently_completed": (not raised and result is True)})

        with ctx.step("Assert no lot name was auto-generated and sequence."
                      "number_next is unchanged from step 2."):
            # The leak detector. _set_auto_lot's line filter requires
            # x.product_id.auto_create_lot (OCA/models/stock_picking.py:55),
            # which this product does not carry, so neither the picking-level
            # call (:67) nor the _action_done one (:63) may touch a line.
            ctx.check("no lot_name and no lot_id appeared, and the sequence "
                      "did not move",
                      {"lot_names": ["", ""], "lots": ["", ""],
                       "sequence_delta": 0},
                      {"lot_names": [row["lot_name"]
                                     for row in _line_facts(rpc, move_id)],
                       "lots": [row["lot"]
                                for row in _line_facts(rpc, move_id)],
                       "sequence_delta": _sequence_now(rpc) - seq_before})

        with ctx.step("Enter the vendor's two serial numbers manually on the "
                      "two move lines."):
            serials = [sku("VENDOR-SN-A"), sku("VENDOR-SN-B")]
            for line_id, serial in zip(line_ids, serials):
                rpc.write("stock.move.line", [line_id], {"lot_name": serial})
            ctx.check("the two vendor serials are staged on the two lines, "
                      "one each",
                      serials,
                      [row["lot_name"] for row in _line_facts(rpc, move_id)])

        with ctx.step("Validate."):
            raised2, message2, result2 = _press_validate(rpc, picking_id)
            ctx.log(f"second button_validate raised={raised2} "
                    f"message={message2!r} result={result2!r}")
            ctx.check("with the serials keyed, button_validate completes and "
                      "returns no action",
                      {"raised": False, "result": True},
                      {"raised": raised2, "result": result2})

        with ctx.step("Assert the receipt is done and both lines carry "
                      "exactly the entered serials, unmodified."):
            facts = _line_facts(rpc, move_id)
            ctx.check("the receipt is done and the vendor's serials survived "
                      "byte for byte, on lot_name and on the linked stock.lot "
                      "alike",
                      {"state": "done", "lot_names": serials,
                       "lots": serials},
                      {"state": _picking_state(rpc, picking_id),
                       "lot_names": [row["lot_name"] for row in facts],
                       "lots": [row["lot"] for row in facts]})

        with ctx.step("Assert two stock.lot records exist with those names."):
            ctx.check("core created exactly the two named lots for TD-P-01 "
                      "(stock/models/stock_move_line.py:644, 711-729)",
                      sorted(serials), _lot_rows_for(rpc, product_id, serials))

        with ctx.step("Assert the Assign Serial Numbers affordance was "
                      "available for this product (the forced-False override "
                      "applies only on the auto-lot path)."):
            # The OCA override forces False only when BOTH flags are set
            # (models/stock_move.py:18-20); with the product flag absent,
            # core's own value survives — and for a SERIAL-tracked product
            # the two versions agree (O17 stock/models/stock_move.py:206
            # 'has_tracking == serial and display_import_lot' / O19 :264
            # 'display_import_lot'), which is why this fixture is serial.
            ctx.check("display_assign_serial was True before validation, for "
                      "a serial-tracked product without the flag",
                      {"display_assign_serial": True,
                       "display_import_lot": True, "has_tracking": "serial"},
                      {"display_assign_serial":
                           affordance.get("display_assign_serial"),
                       "display_import_lot":
                           affordance.get("display_import_lot"),
                       "has_tracking": affordance.get("has_tracking")})

        with ctx.step("Assert sequence.number_next is still unchanged — "
                      "nothing consumed the auto sequence."):
            ctx.check("stock.lot.serial never moved across the whole case",
                      seq_before, _sequence_now(rpc))
    finally:
        try:
            sweep_wf015(rpc)
        except Exception:  # noqa: BLE001
            pass
