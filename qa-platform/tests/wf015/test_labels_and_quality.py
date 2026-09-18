"""DATAONE-WF-015 — receipt labels and Reason for Return: TC212, TC213, TC214.

Three cases over two features. Abbreviations: ``DTO`` =
``D:/Projects/dataone/DTO-Odoo``, ``O17`` = ``D:/Projects/dataone/odoo-17.0``
(community + ``enterprise-17.0``), ``O19`` = ``D:/Projects/odoo-19.0``
(community + ``enterprise-19.0``). Every line reference below was opened in
the real source before the matching assertion was written (hard rule 6); the
same citations are carried, with more context, in ``tests/wf015/common.py``.

What this file proves
---------------------
**TC212 / TC213 — one label per ``stock.move.line``, in both formats (F071).**
Both templates nest the same three loops —
``docs`` → ``o.move_ids`` → ``move.move_line_ids`` — so the label count is a
property of the MOVE LINES, never of the moves and never of the quantity:
Dymo ``DTO project-addons/dto_purchase_stock/reports/
report_receipt_product_label.xml:56-63``, ZPL ``:72-77``. The fixture is built
so the three plausible implementations give three different answers: **2**
moves, **3** move lines, **4.5** units received. Only 3 is correct.

Per label, from the detail template (``:4-44``) and the ZPL body (``:78-109``):

=================  ====================================  ====================
Element            Dymo (``report_..._detail``)          ZPL
=================  ====================================  ====================
SKU barcode+text   ``:8-14``  (``default_code``)         ``^FO270,60`` ``:84``
Lot barcode+text   ``:17-26`` (``lot_id.name or          ``^FO120,60`` ``:90``
                   lot_name``, ``:18``)
Received date      ``:30``, set at ``:60`` from          ``^FT40,60`` ``:94``
                   ``context_timestamp(move.date)        (note the space
                   .date().strftime('%m/%d/%Y')``        after ``^FD``)
PO name + source   ``:32-37`` (``order_id.name`` /       ``^FT40,230`` ``:98``
                   ``order_id.origin``, set ``:58-59``)  / ``:101`` / ``:106``
Quantity           ``QTY:`` **no space** +               ``QTY: `` **with**
                   ``int(move_line.quantity)`` ``:38-40``  a space ``:108``
=================  ====================================  ====================

``int(...)`` **truncates**: a 2.5 line prints ``QTY:2``. That is workbook
defect E4 and TC212 step 15 asserts it as the documented behaviour, not as a
tolerance.

The ZPL template has **THREE** layout branches, not the two the workbook
names: ``len(purchase_source) > 14`` → ``^FT40,230`` (``:97-99``); ``<= 14`` →
``^FT40,290`` (``:100-102``); ``purchase_source`` **falsy** → ``^FT40,380``
(``:105-107``). The third is the default state of a manually created PO and is
exercised here alongside the two the workbook lists (plan finding 11).

The wizard behind both: ``stock.picking.product.label.layout``
(``DTO .../wizard/receipt_product_label_layout.py:8-19``) — ``picking_id``
required ``:12``, ``print_format`` ``[('dymo','Dymo'),('zpl','ZPL Label')]``
with ``default='dymo', required=True`` ``:13-19``; ``process`` is PUBLIC
``:31-38`` and returns ``env.ref(xml_id).report_action(picking_id, data=None,
config=False)`` updated with ``close_on_report_download: True`` ``:36-37``.
``report_action`` itself is core and identical on both versions (O17
``base/models/ir_actions_report.py:1031-1063`` / O19 ``:1153-…``): it returns
``context``, ``data``, ``type``, ``report_name``, ``report_type``,
``report_file`` and ``name``, and with ``config=False`` never routes through
``_action_configure_external_report_layout``. The header button that opens it
is ``action_open_receipt_product_label_layout`` (PUBLIC, ``DTO .../models/
stock_picking.py:53-61``), declared with
``invisible="picking_type_code != 'incoming'"`` (``DTO .../views/
stock_picking_views.xml:9-13``); the method **replaces** the action's context
with ``{'default_picking_id': id}`` (``:58-60``) even though the action record
declares none (``wizard/receipt_product_label_layout_views.xml:19-24``).

The two report records (``reports/report_views.xml``): ``..._dymo`` ``:4-12``
is ``qweb-pdf`` with paperformat ``dto_base.paperformat_dto_label_sheet_dymo``
``:10``; ``..._zpl`` ``:14-21`` is ``qweb-text`` with **no** paperformat. Both
carry ``print_report_name`` ``'Products Labels - %s' % (object.name)``
(``:11``, ``:20``). **Neither declares a groups field**, so the v17
``ir.actions.report.groups_id`` → v19 ``group_ids`` rename the workbook flags
for both cases (O17 ``base/models/ir_actions.py:134`` → O19 ``:168``) cannot
touch them — asserted rather than assumed, via ``common.report_groups_field``.

**TC214 — the 19 controlled Reason-for-Return codes (F072).**
``quality.check.reason_for_return`` is a Selection of exactly 19 values
``'901'``–``'919'`` with **no** ``required=``, **no** default and **no**
tracking (``DTO .../models/quality_check.py:6-27``). The same 19 values are
duplicated verbatim on ``quality.check.wizard`` (``DTO .../wizard/
quality_check_wizard.py:6-28``) and on ``stock.picking`` (``DTO 3rd-addons/
stock_picking_auto_create_lot/models/stock_picking.py:11-33``) — three copies,
no shared source, which is the drift step 14 detects. ``'902'`` carries a
Unicode EN DASH (U+2013) where ``'903'`` and ``'904'`` use an ASCII hyphen;
the comparison is byte-exact, so that distinction is load-bearing.

``quality.check.wizard.confirm_fail`` is PUBLIC on both versions (O17
``enterprise-17.0/quality_control/wizard/quality_check_wizard.py:87-91`` / O19
``:97-100``) and DTO's override writes the code onto **every** record in
``check_ids`` (``:32``) **before** ``super()`` (``:34``). Core's own
``confirm_fail`` then fails only ``current_check_id`` (O17 ``:88``), so after
one wizard run over two checks BOTH carry the code while only the current one
is ``quality_state == 'fail'`` — the test asserts exactly that split.

View placement is two different views and the workbook conflates them: the
**check form** injection carries ``invisible="quality_state == 'pass'"``
(``DTO .../views/quality_check_views.xml:15-16``), while the **wizard**
injection, anchored ``<field name="additional_note" position="after">``, has
**no** modifier and is preceded by a plain ``<div> Reason for Return </div>``
(``DTO .../wizard/quality_check_wizard.xml:9-12``). Steps 4 and 11/12 are
therefore asserted against different arches.

Expected outcomes
-----------------
* ``TC212`` — **EXPECTED v17 OUTCOME: PASS**, with step 15 asserting the E4
  truncation defect as the documented behaviour. BLOCKED instead of FAIL when
  ``common.require_label_wizard`` finds the label stack absent — the on-disk
  ``dto_purchase_stock`` is a v19 port that cannot build the v17 registry
  (``models/purchase_order.py:34`` depends on the v19-only
  ``stock.move.account_move_id``), so what the v17 target serves is an older
  installed revision and must be probed. EXPECTED v19 OUTCOME: PASS unless the
  label loop or barcode rendering changed.
* ``TC213`` — **EXPECTED v17 OUTCOME: PASS.** v19: PASS.
* ``TC214`` — **EXPECTED v17 OUTCOME: PASS when Enterprise ``quality_control``
  is installed and the module's check-form inherit loaded; otherwise BLOCKED**
  with the ``lot_ids``/``lot_id`` anchor reason. ``DTO .../views/
  quality_check_views.xml:15`` anchors ``<field name="lot_ids">``, which exists
  only on v19 Enterprise (O19 ``quality_control/views/quality_views.xml:236``;
  O17 carries ``lot_id`` at ``enterprise-17.0/.../quality_views.xml:246``), so
  on v17 that inherit aborts the install and
  ``common.require_reason_for_return`` blocks with precisely that text.
  EXPECTED v19 OUTCOME: PASS.

Documented adaptations (hard rules 3, 4 and 5)
----------------------------------------------
1. **The rendering surface is the HTTP report route, not a private renderer.**
   ``_render_qweb_pdf`` / ``_render_qweb_html`` / ``_render_qweb_text`` are
   private and undispatchable over ``call_kw``, but
   ``/report/<converter>/<reportname>/<docids>`` is ``auth='user'``
   (O17 ``web/controllers/report.py:23-50``; ``html`` ``:38-40``, ``text``
   ``:45-48``) and ``_get_report`` accepts a ``report_name``. ``html`` carries
   the SAME ``docs → move_ids → move_line_ids`` loop as the PDF without
   depending on wkhtmltopdf; ``text`` returns the ZPL verbatim. Nothing is
   printed: ``process()`` only returns an action dict, and no PrintNode call
   (``3rd-addons/printnode_base/models/ir_attachment.py:9-44``) is ever made —
   convention rule 4.
2. **``res.users.tz`` is pinned to ``UTC``, as a snapshot.** The label date is
   ``context_timestamp(move.date).date()`` (``report_receipt_product_label.xml:
   60``, ``:76``), which localises into the acting user's timezone. Pinning UTC
   makes the expected value derivable from the stored ``move.date`` by pure
   string arithmetic, which matters because the QA venv carries no ``tzdata``
   (``requirements.txt`` pins fastapi / uvicorn / playwright / PyYAML /
   pydantic / openpyxl / psycopg2-binary and nothing else). ``common.
   pin_user_timezone`` records the previous value and
   ``common.restore_user_timezone`` puts it back in a ``finally`` that cannot
   raise; the restoration is asserted. Note this is the ONE place this suite
   departs from ``common.PINNED_TZ`` (``America/Chicago``), which exists for
   the deadline-regroup cases; no assertion here depends on a DST boundary.
3. **The one-receipt-two-moves fixture is built by relocating a move, not by
   driving the regroup engine.** ``dto_purchase_stock/models/
   purchase_order_line.py:56-72`` creates a FRESH picking per PO line
   (``:66``), so a two-line PO yields two one-move receipts. The product's own
   route to a shared receipt is the deadline regroup
   (``models/stock_move.py:41-66``), but that engine is TC202/TC203's subject
   and hard rule 5 forbids one case leaning on another's behaviour. The
   fixture therefore writes ``picking_id`` on the move and on its move lines
   directly — the same two writes ``_update_picking`` performs at
   ``models/stock_move.py:25-30`` — and says so. No private method is
   re-implemented to be asserted; the state is built, then the LABEL is what
   is asserted.
4. **TC213 renders its own Dymo output for the step 11 parity check.** The
   workbook says "compare against TC212's captured output"; hard rule 5 forbids
   cross-test fixture dependence, so TC213 renders both formats from its own
   receipt inside one execution. That is strictly stronger: the two streams
   then describe the same three move lines by construction.
5. **Step 13 of TC212 is asserted as the source renders it.** The template
   prints ``move.purchase_line_id.order_id.name`` and ``…order_id.origin``
   (``:58-59``), i.e. the PO name and the PO's own source document. The
   receipt's ``origin`` is stamped with the PO name by ``_prepare_picking``
   (O17 ``purchase_stock/models/purchase_order.py:230``), so "the PO name plus
   the receipt origin" resolves to those two values; both are asserted and the
   equality ``picking.origin == order.name`` is asserted with them so the
   mapping is visible rather than assumed.
6. **No impersonation.** ``TD-U-03`` is a test-data label, not a group XML id.
   The label wizard's only ACL row grants ``base.group_user`` full rights
   (``DTO .../security/ir.model.access.csv:2`` — one row, no ``res.groups`` and
   no ``ir.rule`` anywhere in the module), so every internal user reaches it
   and the Print Product Label control is view-level
   (``views/stock_picking_views.xml:12``), not an access rule. Fixtures must be
   created and swept with the platform session regardless. The mapping is
   logged at step 1 of each case.
7. **Every fixture is namespaced and swept.** ``common.open_namespace`` sweeps
   before, ``common.sweep_wf015`` after, inside a ``finally:`` that can never
   raise. The workbook's "Nothing modified" final state is honoured for
   pre-existing records: no ``stock.picking.type``, ``res.company``,
   ``quality.point`` or ``purchase.order`` that existed before the run is
   written to. TC214 copies the warehouse incoming operation type
   (``common.make_picking_type``) rather than attaching its quality point to
   the shared one, so no live receipt can generate a check from this run.
"""
from __future__ import annotations

import html as html_lib
import re
import xml.etree.ElementTree as ET

from adapters.base import OdooRPCError
from framework.registry import test_case
from tests.wf015.common import (DYMO_QTY_PREFIX, PRINT_REPORT_NAME_EXPR,
                                REASON_FOR_RETURN, REASON_TAXONOMY_MODELS,
                                REPORT_NAME_DYMO, REPORT_NAME_ZPL, WORKFLOW,
                                WORKFLOW_NAME, XMLID_CORE_PICKING_FORM,
                                XMLID_LABEL_LAYOUT_ACTION,
                                XMLID_PAPERFORMAT_DYMO, XMLID_QC_CHECK_FORM,
                                XMLID_QC_WIZARD_FORM, XMLID_REPORT_DYMO,
                                XMLID_REPORT_ZPL, ZPL_DATE_ORIGIN,
                                ZPL_LOT_ORIGIN, ZPL_PO_LONG_ORIGIN,
                                ZPL_PO_NO_SOURCE_ORIGIN, ZPL_PO_SHORT_ORIGIN,
                                ZPL_QTY_ORIGIN, ZPL_QTY_PREFIX,
                                ZPL_SKU_ORIGIN, checks_of_picking,
                                confirm_purchase_order, count_label_sheets,
                                ensure_vendor, fail_checks_with_reason,
                                fixture_token, m2o_id, make_label_wizard,
                                make_picking_type, make_product,
                                make_purchase_order, make_quality_check,
                                make_quality_point, move_lines_of,
                                open_label_wizard_action, open_namespace,
                                order_picking_ids, order_row, own_company_id,
                                pickings_of, pin_user_timezone,
                                po_line_values, product_row, render_report,
                                report_record, report_groups_field,
                                require_label_wizard,
                                require_reason_for_return,
                                restore_user_timezone, run_label_wizard,
                                selection_of, sweep_wf015, tag, trace,
                                user_timezone, zpl_blocks)

# ===========================================================================
# Local helpers — none of these exists in tests/wf015/common.py
# ===========================================================================

#: A fixed promised date. A constant, not "today": hard rule 5 forbids
#: time-dependent expected values, and the label's own date is derived from
#: the ``move.date`` read back over RPC, never from the clock.
FIXTURE_DATE_PLANNED = "2027-03-04 09:00:00"

#: The receipt-label fixture, stated once so every assertion can quote it.
#: Two PO lines -> two moves; the tracked move is split into two move lines;
#: the untracked line carries 2.5 units so step 15 has its fractional case.
TRACKED_QTY = 2.0
PLAIN_QTY = 2.5
#: 2 moves, 3 move lines, 4.5 units — the three answers a per-move, a
#: per-move-line and a per-unit implementation would each give.
EXPECTED_LABELS = 3
EXPECTED_MOVES = 2

#: ``<div class="o_label_sheet" …>`` — one per label
#: (``report_receipt_product_label.xml:5``). The same pattern
#: ``common.count_label_sheets`` counts; here it also SPLITS the document,
#: which that helper does not do.
_SHEET_RE = re.compile(r'class="[^"]*\bo_label_sheet\b[^"]*"')

#: The human-readable value under each barcode
#: (``report_receipt_product_label.xml:12-14`` for the SKU, ``:23-25`` for the
#: lot). Emitted in template order, so the first is always the SKU and the
#: second, when present, is always the lot — a structural fact, not an
#: ordering by record id.
_LABEL_NAME_RE = re.compile(
    r'<div[^>]*class="[^"]*\bo_label_name\b[^"]*"[^>]*>\s*'
    r'<span[^>]*>(.*?)</span>', re.S)

#: ``ir.qweb.field.barcode.value_to_html`` emits ``<img … alt="Barcode <v>"
#: src="data:image/png;base64,…">`` (O17 ``base/models/ir_qweb_fields.py:
#: 744-751``; the ``alt`` is set whenever the template supplies no ``img_alt``,
#: and this one supplies only ``img_style``, ``:11``/``:22``).
_IMG_ALT_RE = re.compile(r'<img[^>]*\balt="([^"]*)"', re.S)
_BARCODE_DATA = "data:image/png;base64,"

#: ``:38-40`` — ``QTY:`` then, with NO separator, ``int(move_line.quantity)``.
#: The capture of the gap is what proves the missing space.
_DYMO_QTY_RE = re.compile(r"QTY:(\s*)<span[^>]*>\s*(-?\d+)\s*</span>")

#: ``:32-37`` — the centre cell, holding ``purchase_name`` and, when set,
#: ``" - "`` then ``purchase_source``.
_DYMO_PO_RE = re.compile(
    r'<div[^>]*\btext-center\b[^>]*>(.*?)</div>', re.S)

#: ``%m/%d/%Y`` — exactly one per label (``:30``).
_US_DATE_RE = re.compile(r"\b(\d{2}/\d{2}/\d{4})\b")

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _strip_tags(fragment: str) -> str:
    """Visible text of an HTML fragment, whitespace collapsed.

    Tags are replaced by a single space rather than removed, so two adjacent
    ``<span>``s never fuse into one token. The ``QTY:`` assertion therefore
    never runs through here — it reads the raw markup instead, because the
    absence of a space is the very thing it proves.
    """
    text = html_lib.unescape(_TAG_RE.sub(" ", fragment))
    return _WS_RE.sub(" ", text).strip()


def _label_blocks(html: str) -> list:
    """Split a rendered Dymo document into its label blocks.

    ``common.count_label_sheets`` gives the authoritative count; this slices
    the document at the same boundaries so each label can be inspected on its
    own. No label nests another, so slicing start-to-start is exact.
    """
    starts = [match.start() for match in _SHEET_RE.finditer(html)]
    if not starts:
        return []
    bounds = starts + [len(html)]
    return [html[bounds[i]:bounds[i + 1]] for i in range(len(starts))]


def _us_date(stored: str) -> str:
    """``'2027-03-04 09:00:00'`` -> ``'03/04/2027'``.

    Equal to ``context_timestamp(move.date).date().strftime('%m/%d/%Y')``
    (``report_receipt_product_label.xml:60``) **only because the acting user's
    timezone is pinned to UTC** for the duration of the test — see the module
    docstring, adaptation 2.
    """
    text = str(stored or "")
    if len(text) < 10:
        return ""
    return f"{text[5:7]}/{text[8:10]}/{text[0:4]}"


def _dymo_block_facts(block: str) -> dict:
    """Everything one Dymo label asserts about, read out of the markup."""
    human = [html_lib.unescape(value).strip()
             for value in _LABEL_NAME_RE.findall(block)]
    alts = [html_lib.unescape(value) for value in _IMG_ALT_RE.findall(block)]
    qty_match = _DYMO_QTY_RE.search(block)
    po_match = _DYMO_PO_RE.search(block)
    date_match = _US_DATE_RE.search(_strip_tags(block))
    return {
        "sku": human[0] if human else "",
        "lot": human[1] if len(human) > 1 else "",
        "human_values": human,
        "barcode_alts": alts,
        "barcodes": block.count(_BARCODE_DATA),
        "received_date": date_match.group(1) if date_match else "",
        "purchase_line": _strip_tags(po_match.group(1)) if po_match else "",
        "qty": int(qty_match.group(2)) if qty_match else None,
        "qty_gap": qty_match.group(1) if qty_match else None,
    }


def _zpl_field(block: str, origin: str):
    """``(command, payload)`` for one ``^FD…^FS`` field at ``origin``.

    ``command`` is whatever the template puts between the origin and ``^FD``
    — ``^BY3^BCR,100,Y,N,N`` for the two barcodes
    (``report_receipt_product_label.xml:84``, ``:90``) and ``^A0R,40,32`` for
    the three text fields (``:94``, ``:98``/``:101``/``:106``, ``:108``).
    Returns ``None`` when the field is not emitted at all.
    """
    match = re.search(re.escape(origin) + r"(.*?)\^FD(.*?)\^FS", block, re.S)
    if not match:
        return None
    return match.group(1), match.group(2)


def _zpl_block_facts(block: str) -> dict:
    """Everything one ZPL label block asserts about."""
    sku = _zpl_field(block, ZPL_SKU_ORIGIN)
    lot = _zpl_field(block, ZPL_LOT_ORIGIN)
    date = _zpl_field(block, ZPL_DATE_ORIGIN)
    qty = _zpl_field(block, ZPL_QTY_ORIGIN)
    branch, purchase = "", ""
    for origin in (ZPL_PO_LONG_ORIGIN, ZPL_PO_SHORT_ORIGIN,
                   ZPL_PO_NO_SOURCE_ORIGIN):
        found = _zpl_field(block, origin)
        if found:
            branch, purchase = origin, found[1]
            break
    qty_value = None
    if qty and qty[1].startswith(ZPL_QTY_PREFIX):
        tail = qty[1][len(ZPL_QTY_PREFIX):].strip()
        qty_value = int(tail) if tail.lstrip("-").isdigit() else None
    return {
        "sku": sku[1] if sku else "",
        "sku_command": sku[0] if sku else "",
        "lot": lot[1] if lot else "",
        "lot_command": lot[0] if lot else "",
        "received_date": date[1].strip() if date else "",
        "date_command": date[0] if date else "",
        "purchase_line": purchase.strip(),
        "purchase_branch": branch,
        "qty_payload": qty[1] if qty else "",
        "qty": qty_value,
    }


def _comparable(facts: dict) -> dict:
    """The five data elements, in the form both formats can be compared in.

    TC213 step 11 is about the VALUES, never the surrounding literals: the two
    templates deliberately differ in spacing (``QTY:`` at ``:39`` versus
    ``QTY: `` at ``:108``) and in markup.
    """
    return {"sku": facts["sku"], "lot": facts["lot"],
            "received_date": facts["received_date"],
            "purchase_line": facts["purchase_line"], "qty": facts["qty"]}


def _by_key(blocks_facts: list) -> dict:
    """Index label facts by ``(sku, lot)``, which is unique per move line.

    Keying on the printed identity rather than on document order keeps the
    comparison independent of recordset ordering, which is a database
    artefact (hard rule 5).
    """
    return {(facts["sku"], facts["lot"]): facts for facts in blocks_facts}


def _expected_label_facts(ctx, picking_id: int, order: dict) -> dict:
    """What every label on this receipt must carry, read from the records.

    Implements the template's own expressions: ``default_code`` (``:9``),
    ``lot_id.name or lot_name`` (``:18``), the date (``:60``),
    ``order_id.name`` / ``order_id.origin`` (``:58-59``) and
    ``int(move_line.quantity)`` (``:39``).
    """
    rpc = ctx.adapter.rpc
    purchase_line = order["name"]
    if order.get("origin"):
        purchase_line = f"{order['name']} - {order['origin']}"
    moves = rpc.search_read("stock.move", [("picking_id", "=", picking_id)],
                            ["product_id", "date"], order="id")
    expected = {}
    for move in moves:
        received = _us_date(move.get("date"))
        for line in move_lines_of(rpc, [move["id"]]):
            product = product_row(rpc, m2o_id(line["product_id"]),
                                  ["default_code"])
            code = product.get("default_code") or ""
            lot = ""
            if line.get("lot_id"):
                lot = line["lot_id"][1]
            elif line.get("lot_name"):
                lot = line["lot_name"]
            expected[(code, lot)] = {
                "sku": code, "lot": lot, "received_date": received,
                "purchase_line": purchase_line,
                "qty": int(line.get("quantity") or 0.0),
            }
    return expected


def _arch_of(ctx, model: str, xmlid: str, view_type: str = "form") -> str:
    """The rendered arch of ONE named view.

    ``get_view(view_id, view_type)`` exists on both versions (O17
    ``base/models/ir_ui_view.py:2613`` / O19 ``:3138``). The view is addressed
    by XML id rather than left to the model's default, because every arch this
    file asserts against is a specific core or Enterprise view carrying a DTO
    inherit — and reading the rendered arch is the only assertion that catches
    an inherit which loaded cleanly and matched nothing.
    """
    rpc = ctx.adapter.rpc
    view_id = rpc.ref(xmlid)
    if not view_id:
        ctx.blocked(f"XML id {xmlid!r} does not resolve on {ctx.env.key} "
                    f"(db={ctx.env.db}) — the view this case asserts against "
                    f"is not in the database at all.")
    return rpc.call(model, "get_view", view_id, view_type)["arch"]


def _parse(arch) -> ET.Element:
    """Parse a ``get_view()['arch']`` payload with the stdlib parser.

    ``lxml`` is not in the QA venv, and ``xml.etree`` covers everything
    asserted here. The payload is normalised to ``str`` first: a view whose
    arch was rebuilt by an inherit can arrive as ``bytes``.
    """
    if isinstance(arch, (bytes, bytearray)):
        arch = arch.decode("utf-8", "replace")
    return ET.fromstring(arch)


def _field_node(root: ET.Element, name: str):
    for node in root.iter("field"):
        if node.get("name") == name:
            return node
    return None


def _parent_map(root: ET.Element) -> dict:
    return {id(child): parent for parent in root.iter() for child in parent}


def _field_info(rpc, model: str, field: str, attributes: list) -> dict:
    """One field's declared attributes.

    ``fields_get`` is public on every model, so this is always reachable.
    """
    return rpc.call(model, "fields_get", [field],
                    attributes=attributes).get(field, {})


def _role_note(role: str) -> str:
    """One log line recording the workbook role and why it is not assumed."""
    return (f"workbook role {role}: the label is test data, not a group XML "
            f"id. dto_purchase_stock ships exactly ONE ACL row — the label "
            f"wizard for base.group_user with 1,1,1,1 "
            f"(security/ir.model.access.csv:2) — and no res.groups and no "
            f"ir.rule anywhere in the module, so every internal user reaches "
            f"this surface. The Print Product Label control is view-level "
            f"(views/stock_picking_views.xml:12), not an access rule. "
            f"Fixtures are created and swept with the platform session.")


def _render(ctx, report_name: str, picking_id: int, converter: str):
    """``(ok, text, error)`` from the HTTP report route.

    Wrapped rather than left to raise: a report route fault is an outcome the
    platform must record as a failed ``ctx.check`` with its message, not an
    unhandled traceback. ``urllib``'s ``HTTPError`` and ``URLError`` are both
    ``OSError`` subclasses, so this is a narrow except, never a bare one.
    """
    try:
        return True, render_report(ctx, report_name, picking_id,
                                   converter=converter), ""
    except OSError as exc:
        return False, "", f"{type(exc).__name__}: {exc}"


def _make_lot(ctx, product_id: int, label: str) -> int:
    """A namespaced ``stock.lot`` for the ``lot_id.name`` half of step 11.

    Swept by ``common.sweep_wf015`` through ``product_id`` (it removes every
    ``stock.lot`` whose product carries the marker default_code).
    """
    rpc = ctx.adapter.rpc
    values = {"name": tag(label), "product_id": product_id}
    if rpc.field_exists("stock.lot", "company_id"):
        values["company_id"] = own_company_id(rpc)
    return rpc.create("stock.lot", values)


def _relocate_moves_onto(ctx, picking_ids, target_id: int) -> list:
    """Put every move of ``picking_ids`` (and its move lines) on ``target_id``.

    The two writes are the ones ``_update_picking`` performs
    (``dto_purchase_stock/models/stock_move.py:25-30``). This is FIXTURE
    CONSTRUCTION: the product's own route to a shared receipt is the deadline
    regroup, which is TC202/TC203's subject — see the module docstring,
    adaptation 3. Nothing here is asserted; the LABEL is.
    """
    rpc = ctx.adapter.rpc
    relocated = []
    for picking_id in picking_ids:
        if picking_id == target_id:
            continue
        move_ids = rpc.search("stock.move", [("picking_id", "=", picking_id)])
        if not move_ids:
            continue
        line_ids = rpc.search("stock.move.line", [("move_id", "in", move_ids)])
        rpc.write("stock.move", move_ids, {"picking_id": target_id})
        if line_ids:
            rpc.write("stock.move.line", line_ids, {"picking_id": target_id})
        relocated += move_ids
    return relocated


def _split_tracked_move(ctx, move_id: int, lot_id: int, lot_name: str) -> list:
    """Give one move exactly two move lines: one ``lot_id``, one ``lot_name``.

    Both halves of the template's ``lot_id and lot_id.name or lot_name``
    expression (``report_receipt_product_label.xml:18``) then have a real
    case, which is what TC212 step 11 asks for. How many lines
    ``_action_assign`` left behind depends on the operation type's lot
    settings (O17 ``stock/models/stock_move.py:1697-1700`` splits per unit only
    for serial tracking with ``use_create_lots``/``use_existing_lots``), so the
    shape is read first and adjusted, never assumed.
    """
    rpc = ctx.adapter.rpc
    move = rpc.read("stock.move", [move_id],
                    ["product_id", "product_uom", "location_id",
                     "location_dest_id", "picking_id"])[0]
    existing = move_lines_of(rpc, [move_id])
    if len(existing) > 2:
        rpc.unlink("stock.move.line", [row["id"] for row in existing[2:]])
        existing = existing[:2]
    if existing:
        rpc.write("stock.move.line", [existing[0]["id"]],
                  {"quantity": 1.0, "lot_id": lot_id, "lot_name": False})
    if len(existing) > 1:
        rpc.write("stock.move.line", [existing[1]["id"]],
                  {"quantity": 1.0, "lot_id": False, "lot_name": lot_name})
    else:
        rpc.create("stock.move.line", {
            "move_id": move_id,
            "picking_id": m2o_id(move["picking_id"]),
            "product_id": m2o_id(move["product_id"]),
            "product_uom_id": m2o_id(move["product_uom"]),
            "location_id": m2o_id(move["location_id"]),
            "location_dest_id": m2o_id(move["location_dest_id"]),
            "quantity": 1.0,
            "lot_name": lot_name,
        })
    return [row["id"] for row in move_lines_of(rpc, [move_id])]


def _label_receipt(ctx, origin=None, label="PO") -> dict:
    """ONE receipt: three ``stock.move.line`` across two ``stock.move``.

    * two PO lines, one lot-tracked (qty 2) and one untracked (qty 2.5), both
      promised on the same fixed date;
    * ``dto_purchase_stock`` puts each line on its own receipt
      (``purchase_order_line.py:66``), so the second move is relocated onto the
      first receipt — adaptation 3;
    * the tracked move is then split into a ``lot_id`` line and a ``lot_name``
      line.

    The untracked line's 2.5 units are the fractional case TC212 step 15
    needs, and they are the move's DEMAND, so ``_action_assign`` produces the
    fraction itself (O17 ``stock/models/stock_move.py:1700-1703``) — nothing
    is forced onto a computed field.
    """
    rpc = ctx.adapter.rpc
    vendor_id = ensure_vendor(rpc)
    tracked_id = make_product(ctx, "TD-P-01", tracking="lot")
    plain_id = make_product(ctx, "TD-P-04", tracking="none")
    lines = [po_line_values(ctx, tracked_id, TRACKED_QTY,
                            FIXTURE_DATE_PLANNED),
             po_line_values(ctx, plain_id, PLAIN_QTY, FIXTURE_DATE_PLANNED)]
    order_id = make_purchase_order(ctx, lines, partner_id=vendor_id,
                                   origin=origin, label=label)
    confirm_purchase_order(rpc, order_id)

    picking_ids = order_picking_ids(rpc, order_id)
    target_id = picking_ids[0] if picking_ids else None
    if target_id is None:
        state = order_row(rpc, order_id, ["state"])["state"]
        ctx.blocked(
            "The confirmed purchase order produced no receipt at all on "
            f"{ctx.env.key} (db={ctx.env.db}); the order is in state "
            f"{state!r}. purchase.order.picking_ids is "
            "@api.depends('order_line.move_ids.picking_id') on both versions "
            "(O17 purchase_stock/models/purchase_order.py:22-25), so an empty "
            "result means no stock move exists. Either the order never "
            "reached 'purchase' (this company has purchase double validation "
            "enabled, O17 purchase/models/purchase_order.py:507,954) or "
            "dto_purchase_stock's per-line override "
            "(purchase_order_line.py:56-72) is not contributing to this "
            "target. Neither is a defect of the label under test.")
    _relocate_moves_onto(ctx, picking_ids, target_id)

    lot_id = _make_lot(ctx, tracked_id, "LOT-A")
    lot_row = rpc.read("stock.lot", [lot_id], ["name"])[0]
    tracked_moves = rpc.search("stock.move", [("picking_id", "=", target_id),
                                              ("product_id", "=", tracked_id)])
    if tracked_moves:
        _split_tracked_move(ctx, tracked_moves[0], lot_id, tag("SN-B"))
    return {
        "order_id": order_id, "picking_id": target_id,
        "picking_ids": picking_ids, "vendor_id": vendor_id,
        "tracked_id": tracked_id, "plain_id": plain_id,
        "lot_id": lot_id, "lot_name": lot_row["name"],
        "free_lot_name": tag("SN-B"),
    }


def _single_line_receipt(ctx, origin, label: str) -> dict:
    """A one-line receipt, used only to steer the ZPL layout branch.

    ``purchase_source`` is ``purchase.order.origin``
    (``report_receipt_product_label.xml:75``), so the branch is chosen by the
    PO's own origin: longer than 14 characters, 14 or fewer, or absent.
    """
    rpc = ctx.adapter.rpc
    vendor_id = ensure_vendor(rpc)
    product_id = make_product(ctx, f"TD-P-04 {label}", tracking="none")
    order_id = make_purchase_order(
        ctx, [po_line_values(ctx, product_id, 1.0, FIXTURE_DATE_PLANNED)],
        partner_id=vendor_id, origin=origin, label=label)
    confirm_purchase_order(rpc, order_id)
    picking_ids = order_picking_ids(rpc, order_id)
    return {"order_id": order_id, "picking_ids": picking_ids,
            "picking_id": picking_ids[0] if picking_ids else None,
            "product_id": product_id}


def _cleanup(rpc, uid, previous_tz):
    """Restore the timezone and sweep. Can never raise."""
    try:
        if uid is not None:
            restore_user_timezone(rpc, uid, previous_tz)
    except Exception:  # noqa: BLE001
        pass
    try:
        sweep_wf015(rpc)
    except Exception:  # noqa: BLE001
        pass


# ==================================================================== TC212
@test_case(
    id="TEST-WF015-TC212",
    name="The Dymo receipt label prints exactly one label per stock.move.line",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_purchase_stock",
    priority="P1", kind="HYBRID", order=15212,
    description="A receipt holding three stock.move.line across two "
                "stock.move renders exactly three Dymo labels — not two and "
                "not 4.5 — each carrying the SKU as barcode and text, the lot "
                "from lot_id.name or lot_name, the %m/%d/%Y date, the PO name "
                "with its source, and QTY: truncated by int(); the wizard "
                "defaults to dymo, returns the qweb-pdf report with "
                "close_on_report_download, and resolves the Dymo paperformat.",
    traceability=trace("DATAONE-TC212"))
def test_tc212(ctx):
    rpc = ctx.adapter.rpc
    require_label_wizard(ctx)
    open_namespace(ctx)
    uid = previous_tz = None
    try:
        with ctx.step("Log in as TD-U-03 and open the receipt."):
            ctx.log(_role_note("TD-U-03"))
            # UTC, not common.PINNED_TZ — module docstring, adaptation 2.
            uid, previous_tz = pin_user_timezone(ctx, "UTC")
            fixture = _label_receipt(ctx, label="DYMO")
            picking_id = fixture["picking_id"]
            order = order_row(rpc, fixture["order_id"],
                              ["name", "origin", "state"])
            picking = pickings_of(rpc, [picking_id],
                                  ["name", "origin", "state"])[0]
            ctx.check("the receipt exists, is not done or cancelled, and "
                      "carries the purchase order as its origin "
                      "(O17 purchase_stock/models/purchase_order.py:230)",
                      {"order_state": "purchase", "origin": order["name"],
                       "open": True},
                      {"order_state": order["state"],
                       "origin": picking["origin"],
                       "open": picking["state"] not in ("done", "cancel")})

        with ctx.step("Record n_lines = len(picking.move_line_ids) and assert "
                      "it is 3, while len(picking.move_ids) is 2."):
            move_ids = rpc.search("stock.move",
                                  [("picking_id", "=", picking_id)])
            move_lines = move_lines_of(rpc, move_ids)
            received_total = sum(float(row.get("quantity") or 0.0)
                                 for row in move_lines)
            ctx.check("the receipt holds three move lines across two moves — "
                      "the fixture that tells a per-line implementation apart "
                      "from a per-move or a per-unit one",
                      {"move_lines": EXPECTED_LABELS, "moves": EXPECTED_MOVES},
                      {"move_lines": len(move_lines), "moves": len(move_ids)})
            ctx.log(f"quantity received across the three lines = "
                    f"{received_total} (a per-unit implementation would print "
                    f"that many labels)")

        with ctx.step("Assert the Print Product Label header button is "
                      "visible (incoming transfers only)."):
            form_root = _parse(_arch_of(ctx, "stock.picking",
                                        XMLID_CORE_PICKING_FORM, "form"))
            buttons = [node for node in form_root.iter("button")
                       if node.get("name")
                       == "action_open_receipt_product_label_layout"]
            code = rpc.read("stock.picking", [picking_id],
                            ["picking_type_code"])[0]["picking_type_code"]
            ctx.check("the header carries the label button with its "
                      "incoming-only modifier (views/"
                      "stock_picking_views.xml:9-13), and this receipt is "
                      "incoming, so it renders visible",
                      {"buttons": 1, "string": "Print Product Label",
                       "invisible": "picking_type_code != 'incoming'",
                       "picking_type_code": "incoming"},
                      {"buttons": len(buttons),
                       "string": (buttons[0].get("string")
                                  if buttons else None),
                       "invisible": (buttons[0].get("invisible")
                                     if buttons else None),
                       "picking_type_code": code})

        with ctx.step("Press it."):
            action = open_label_wizard_action(rpc, picking_id)
            # The method REPLACES the action's context (models/
            # stock_picking.py:58-60); the act_window record itself declares
            # none (wizard/receipt_product_label_layout_views.xml:19-24).
            ctx.check("the button returns the label-layout act_window, "
                      "target 'new', with the receipt injected as the only "
                      "context key",
                      {"type": "ir.actions.act_window",
                       "res_model": "stock.picking.product.label.layout",
                       "target": "new",
                       "id": rpc.ref(XMLID_LABEL_LAYOUT_ACTION),
                       "context": {"default_picking_id": picking_id}},
                      {"type": action.get("type"),
                       "res_model": action.get("res_model"),
                       "target": action.get("target"),
                       "id": action.get("id"),
                       "context": action.get("context")})

        with ctx.step("Assert the stock.picking.product.label.layout wizard "
                      "opens with Print Format defaulting to dymo."):
            # print_format is deliberately NOT passed, so what reads back is
            # the declared default (wizard/receipt_product_label_layout.py:18).
            wizard_id = make_label_wizard(rpc, picking_id)
            stored = rpc.read("stock.picking.product.label.layout",
                              [wizard_id], ["print_format", "picking_id"])[0]
            declared = _field_info(rpc, "stock.picking.product.label.layout",
                                   "print_format",
                                   ["selection", "required"])
            ctx.check("the wizard stores this receipt and defaults to dymo, "
                      "with both formats offered and the field required",
                      {"print_format": "dymo", "picking_id": picking_id,
                       "selection": [["dymo", "Dymo"], ["zpl", "ZPL Label"]],
                       "required": True},
                      {"print_format": stored["print_format"],
                       "picking_id": m2o_id(stored["picking_id"]),
                       "selection": [list(pair) for pair
                                     in (declared.get("selection") or [])],
                       "required": bool(declared.get("required"))})

        with ctx.step("Leave the default and press the confirm button."):
            # process() is PUBLIC (wizard/receipt_product_label_layout.py:31).
            # It only RETURNS an action: nothing is sent to a printer, and
            # config=False keeps report_action off the layout-configurator
            # branch (O17 base/models/ir_actions_report.py:1060-1061).
            report_action = run_label_wizard(rpc, wizard_id)
            ctx.check_true("process() returned an action dict",
                           isinstance(report_action, dict),
                           f"returned {type(report_action).__name__}")

        with ctx.step("Assert the report produced is "
                      "dto_purchase_stock.report_receipt_product_label_dymo "
                      "(qweb-pdf)."):
            record = report_record(rpc, XMLID_REPORT_DYMO)
            ctx.check("the wizard returned exactly the Dymo report record's "
                      "own report_name and qweb-pdf type "
                      "(reports/report_views.xml:4-12)",
                      {"type": "ir.actions.report",
                       "report_name": REPORT_NAME_DYMO,
                       "report_type": "qweb-pdf",
                       "record_report_name": REPORT_NAME_DYMO,
                       "record_report_type": "qweb-pdf",
                       "record_model": "stock.picking"},
                      {"type": report_action.get("type"),
                       "report_name": report_action.get("report_name"),
                       "report_type": report_action.get("report_type"),
                       "record_report_name": (record or {}).get("report_name"),
                       "record_report_type": (record or {}).get("report_type"),
                       "record_model": (record or {}).get("model")})
            # The workbook's v19_watch: ir.actions.report.groups_id ->
            # group_ids (O17 base/models/ir_actions.py:134 -> O19 :168).
            # Neither label report declares the field at all, so the rename
            # cannot touch them — proved, not assumed.
            groups_field = report_groups_field(rpc)
            if groups_field:
                ctx.check(f"the Dymo report declares no {groups_field} — the "
                          f"v17->v19 rename of that m2m does not touch it",
                          [], (record or {}).get(groups_field))
            else:
                ctx.log("ir.actions.report carries neither groups_id nor "
                        "group_ids on this target — nothing to compare")

        with ctx.step("Assert the produced file is named Products Labels - "
                      "<picking name>."):
            # The download filename is computed from print_report_name by
            # /report/download; what is assertable here is the stored
            # expression (reports/report_views.xml:11) and the value it
            # yields for this receipt.
            ctx.check("print_report_name is the verbatim source expression",
                      PRINT_REPORT_NAME_EXPR,
                      (record or {}).get("print_report_name"))
            ctx.log(f"that expression renders for this receipt as "
                    f"'Products Labels - {picking['name']}'")

        with ctx.step("Assert the output contains exactly 3 labels — one per "
                      "stock.move.line, not 2 (per move) and not the total "
                      "received quantity (per unit)."):
            ok, document, error = _render(ctx, REPORT_NAME_DYMO, picking_id,
                                          "html")
            ctx.check_true("the Dymo report rendered over /report/html",
                           ok, error or "rendered")
            path = ctx.artifacts_dir / "tc212_dymo_labels.html"
            path.write_text(document, encoding="utf-8")
            ctx.add_artifact(path, "log", "TC212 rendered Dymo labels")
            blocks = _label_blocks(document)
            ctx.check("the document carries one div.o_label_sheet per move "
                      "line (reports/report_receipt_product_label.xml:56-63)",
                      {"labels": EXPECTED_LABELS,
                       "per_move_would_be": EXPECTED_MOVES,
                       "per_unit_would_be": TRACKED_QTY + PLAIN_QTY,
                       "blocks_sliced": EXPECTED_LABELS},
                      {"labels": count_label_sheets(document),
                       "per_move_would_be": len(move_ids),
                       "per_unit_would_be": received_total,
                       "blocks_sliced": len(blocks)})
            actual = _by_key([_dymo_block_facts(block) for block in blocks])
            expected = _expected_label_facts(ctx, picking_id, order)

        with ctx.step("Assert each label carries the product's default_code "
                      "as both a barcode and human-readable text."):
            ctx.check("every label prints its SKU twice — once as a "
                      "data-URI Code128 image and once as text "
                      "(report_receipt_product_label.xml:8-14)",
                      {key: {"text": row["sku"], "barcode": True}
                       for key, row in sorted(expected.items())},
                      {key: {"text": actual.get(key, {}).get("sku", ""),
                             "barcode": any(
                                 alt.endswith(row["sku"]) for alt
                                 in actual.get(key, {}).get("barcode_alts",
                                                            []))}
                       for key, row in sorted(expected.items())})

        with ctx.step("Assert each label carries the lot/serial barcode taken "
                      "from lot_id.name or, where the lot record does not yet "
                      "exist, lot_name."):
            # :18 — `move_line.lot_id and move_line.lot_id.name or
            # move_line.lot_name`. The fixture supplies one line of each kind;
            # the untracked line has neither, and the t-if at :19 then emits
            # no lot block at all, which is asserted as an empty value with no
            # second barcode rather than glossed over.
            ctx.check("every label prints the lot the template resolves, as "
                      "text and as a barcode, and prints none where the move "
                      "line carries neither lot_id nor lot_name",
                      {key: {"text": row["lot"], "barcodes": 2 if row["lot"]
                             else 1}
                       for key, row in sorted(expected.items())},
                      {key: {"text": actual.get(key, {}).get("lot", ""),
                             "barcodes": actual.get(key, {}).get("barcodes")}
                       for key, row in sorted(expected.items())})

        with ctx.step("Assert each label shows the received date formatted "
                      "%m/%d/%Y from context_timestamp(move.date)."):
            ctx.check("every label prints its move's date in %m/%d/%Y "
                      "(report_receipt_product_label.xml:30, set at :60); the "
                      "acting user's tz is pinned to UTC so the expected "
                      "value is the stored move.date itself",
                      {key: row["received_date"]
                       for key, row in sorted(expected.items())},
                      {key: actual.get(key, {}).get("received_date", "")
                       for key in sorted(expected)})

        with ctx.step("Assert each label shows the PO name plus the receipt "
                      "origin."):
            # :32-37 prints order_id.name and, when set, " - " then
            # order_id.origin. picking.origin is stamped with the PO name by
            # _prepare_picking, so the equality is asserted alongside the
            # printed values — module docstring, adaptation 5.
            ctx.check("every label prints the purchase order and its source "
                      "document, and the receipt's own origin is that same "
                      "purchase order name",
                      {"labels": {key: row["purchase_line"]
                                  for key, row in sorted(expected.items())},
                       "picking_origin_is_po_name": True},
                      {"labels": {key: actual.get(key, {}).get("purchase_line",
                                                               "")
                                  for key in sorted(expected)},
                       "picking_origin_is_po_name":
                           picking["origin"] == order["name"]})

        with ctx.step("Assert each label shows QTY: <integer> and that the "
                      "value equals int(move_line.quantity)."):
            ctx.check("every label prints QTY: with NO separating space "
                      "(:39) and the integer part of its move line's quantity",
                      {key: {"qty": row["qty"], "gap": ""}
                       for key, row in sorted(expected.items())},
                      {key: {"qty": actual.get(key, {}).get("qty"),
                             "gap": actual.get(key, {}).get("qty_gap")}
                       for key in sorted(expected)})
            ctx.log(f"Dymo writes {DYMO_QTY_PREFIX!r} with no space (:39) "
                    f"while ZPL writes {ZPL_QTY_PREFIX!r} with one (:108) — "
                    f"the two formats differ in the literal, not the value")

        with ctx.step("On a move line with a fractional quantity (e.g. 2.5), "
                      "assert the label reads QTY: 2 — truncation, not "
                      "rounding. Record as the documented v17 defect."):
            # WF-015 defect E4. int() truncates toward zero, so a receipt of
            # 0.5 units would print QTY:0 — asserted here as the product's
            # documented behaviour, never softened (hard rule 2).
            plain_code = (product_row(rpc, fixture["plain_id"],
                                      ["default_code"])["default_code"] or "")
            fractional_key = (plain_code, "")
            line_rows = [row for row in move_lines
                         if m2o_id(row["product_id"]) == fixture["plain_id"]]
            stored_qty = float(line_rows[0]["quantity"]) if line_rows else None
            ctx.check("the 2.5-unit move line prints QTY:2 — int() truncates, "
                      "it does not round (reports/"
                      "report_receipt_product_label.xml:39)",
                      {"stored_quantity": PLAIN_QTY, "printed_qty": 2,
                       "rounding_would_print": 3},
                      {"stored_quantity": stored_qty,
                       "printed_qty":
                           actual.get(fractional_key, {}).get("qty"),
                       "rounding_would_print": 3})
            ctx.log("DOCUMENTED DEFECT E4: int(move_line.quantity) at "
                    "reports/report_receipt_product_label.xml:39 truncates "
                    "toward zero, so a receipt of less than one unit prints "
                    "QTY:0 on the Dymo label and QTY: 0 on the ZPL label "
                    "(:108). Recorded, not worked around.")

        with ctx.step("Assert the wizard closed automatically after download "
                      "(close_on_report_download)."):
            ctx.check("process() set close_on_report_download on the returned "
                      "action (wizard/receipt_product_label_layout.py:37)",
                      True, report_action.get("close_on_report_download"))

        with ctx.step("Assert the report's paperformat resolves to "
                      "dto_base.paperformat_dto_label_sheet_dymo."):
            paperformat_id = rpc.ref(XMLID_PAPERFORMAT_DYMO)
            ctx.check("the Dymo report points at the DataOne label-sheet "
                      "paperformat (reports/report_views.xml:10)",
                      paperformat_id,
                      m2o_id((record or {}).get("paperformat_id")))
            if paperformat_id:
                fmt = rpc.read("report.paperformat", [paperformat_id],
                               ["name", "orientation", "default"])[0]
                ctx.log(f"paperformat {fmt['name']!r}: orientation="
                        f"{fmt['orientation']!r}, default={fmt['default']!r}. "
                        f"dto_base/reports/report_views.xml:45 now carries "
                        f"default eval=\"False\" where the v17 record had "
                        f"True — a port change, recorded here, not asserted.")
    finally:
        _cleanup(rpc, uid, previous_tz)
        # The snapshot-and-restore is asserted, not merely attempted — the
        # WF-013 TC228 precedent. Outside the cleanup so a restore failure is
        # a recorded assertion rather than a swallowed exception.
    if uid is not None:
        ctx.check("the acting user's timezone was restored", previous_tz,
                  user_timezone(rpc, uid))


# ==================================================================== TC213
@test_case(
    id="TEST-WF015-TC213",
    name="The ZPL receipt label produces the same one-per-move-line output as "
         "raw text",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_purchase_stock",
    priority="P1", kind="HYBRID", order=15213,
    description="The qweb-text ZPL report emits one ^XA…^XZ block per "
                "stock.move.line, each carrying the rotated Code-128 SKU at "
                "^FO270,60 and lot at ^FO120,60, the date, the PO line and "
                "QTY:, with values identical to the Dymo label for the same "
                "move line; the long, short and absent purchase_source "
                "fixtures select ^FT40,230, ^FT40,290 and ^FT40,380; the "
                "stream is plain text and the report declares no paperformat.",
    traceability=trace("DATAONE-TC213"))
def test_tc213(ctx):
    rpc = ctx.adapter.rpc
    require_label_wizard(ctx)
    open_namespace(ctx)
    uid = previous_tz = None
    try:
        with ctx.step("Log in as TD-U-03 and open the receipt."):
            ctx.log(_role_note("TD-U-03"))
            uid, previous_tz = pin_user_timezone(ctx, "UTC")
            # The default namespaced origin is far longer than 14 characters,
            # so the main fixture is the > 14 branch by construction
            # (report_receipt_product_label.xml:97-99).
            fixture = _label_receipt(ctx, label="ZPL")
            picking_id = fixture["picking_id"]
            order = order_row(rpc, fixture["order_id"],
                              ["name", "origin", "state"])
            move_ids = rpc.search("stock.move",
                                  [("picking_id", "=", picking_id)])
            move_lines = move_lines_of(rpc, move_ids)
            ctx.check("the same fixture as TC212 — three move lines across "
                      "two moves, with a purchase_source longer than 14 "
                      "characters",
                      {"move_lines": EXPECTED_LABELS, "moves": EXPECTED_MOVES,
                       "source_longer_than_14": True},
                      {"move_lines": len(move_lines), "moves": len(move_ids),
                       "source_longer_than_14":
                           len(order["origin"] or "") > 14})

        with ctx.step("Press Print Product Label and select ZPL."):
            open_label_wizard_action(rpc, picking_id)
            wizard_id = make_label_wizard(rpc, picking_id, print_format="zpl")
            ctx.check("the wizard holds this receipt with print_format zpl",
                      {"print_format": "zpl", "picking_id": picking_id},
                      {"print_format": rpc.read(
                          "stock.picking.product.label.layout", [wizard_id],
                          ["print_format"])[0]["print_format"],
                       "picking_id": picking_id})

        with ctx.step("Confirm."):
            report_action = run_label_wizard(rpc, wizard_id)
            ctx.check_true("process() returned an action dict",
                           isinstance(report_action, dict),
                           f"returned {type(report_action).__name__}")

        with ctx.step("Assert the report produced is "
                      "dto_purchase_stock.report_receipt_product_label_zpl "
                      "with type qweb-text."):
            record = report_record(rpc, XMLID_REPORT_ZPL)
            ctx.check("the wizard returned the ZPL report record's own "
                      "report_name and qweb-text type "
                      "(reports/report_views.xml:14-21)",
                      {"type": "ir.actions.report",
                       "report_name": REPORT_NAME_ZPL,
                       "report_type": "qweb-text",
                       "record_report_name": REPORT_NAME_ZPL,
                       "record_report_type": "qweb-text",
                       "record_model": "stock.picking",
                       "close_on_report_download": True},
                      {"type": report_action.get("type"),
                       "report_name": report_action.get("report_name"),
                       "report_type": report_action.get("report_type"),
                       "record_report_name": (record or {}).get("report_name"),
                       "record_report_type": (record or {}).get("report_type"),
                       "record_model": (record or {}).get("model"),
                       "close_on_report_download":
                           report_action.get("close_on_report_download")})
            groups_field = report_groups_field(rpc)
            if groups_field:
                ctx.check(f"the ZPL report declares no {groups_field} either "
                          f"— the v17->v19 rename does not touch it",
                          [], (record or {}).get(groups_field))

        with ctx.step("Assert the produced stream contains exactly 3 label "
                      "blocks — one per stock.move.line, matching TC212's "
                      "count."):
            ok, stream, error = _render(ctx, REPORT_NAME_ZPL, picking_id,
                                        "text")
            ctx.check_true("the ZPL report rendered over /report/text",
                           ok, error or "rendered")
            path = ctx.artifacts_dir / "tc213_zpl_stream.txt"
            path.write_text(stream, encoding="utf-8")
            ctx.add_artifact(path, "log", "TC213 ZPL stream")
            blocks = zpl_blocks(stream)
            ctx.check("one ^XA…^XZ block per move line "
                      "(reports/report_receipt_product_label.xml:72-77, "
                      ":79, :109)",
                      {"blocks": EXPECTED_LABELS,
                       "per_move_would_be": EXPECTED_MOVES},
                      {"blocks": len(blocks),
                       "per_move_would_be": len(move_ids)})
            facts = [_zpl_block_facts(block) for block in blocks]
            actual = _by_key(facts)
            expected = _expected_label_facts(ctx, picking_id, order)

        with ctx.step("Assert each block contains a ^BCR rotated Code-128 for "
                      "the SKU at ^FO270,60."):
            ctx.check(f"every block opens its SKU barcode with "
                      f"{ZPL_SKU_ORIGIN}^BY3^BCR,100,Y,N,N "
                      f"(report_receipt_product_label.xml:84)",
                      {key: "^BY3^BCR,100,Y,N,N" for key in sorted(expected)},
                      {key: actual.get(key, {}).get("sku_command", "")
                       for key in sorted(expected)})

        with ctx.step("Assert each block contains a ^BCR for the lot at "
                      "^FO120,60."):
            # :88-91 wraps the lot barcode in `t-if="lot_name"`, so the line
            # that carries neither lot_id nor lot_name emits none. Asserted as
            # an empty command for that key, not skipped.
            ctx.check(f"every block with a lot opens its lot barcode with "
                      f"{ZPL_LOT_ORIGIN}^BY3^BCR,100,Y,N,N, and a move line "
                      f"without a lot emits no lot field at all "
                      f"(report_receipt_product_label.xml:88-91)",
                      {key: ("^BY3^BCR,100,Y,N,N" if row["lot"] else "")
                       for key, row in sorted(expected.items())},
                      {key: actual.get(key, {}).get("lot_command", "")
                       for key in sorted(expected)})

        with ctx.step("Assert the SKU encoded equals the product's "
                      "default_code."):
            ctx.check("the encoded SKU is move_line.product_id.default_code "
                      "(report_receipt_product_label.xml:82)",
                      {key: row["sku"]
                       for key, row in sorted(expected.items())},
                      {key: actual.get(key, {}).get("sku", "")
                       for key in sorted(expected)})

        with ctx.step("Assert the lot encoded equals lot_id.name or "
                      "lot_name."):
            ctx.check("the encoded lot is lot_id.name where the lot record "
                      "exists and lot_name where it does not "
                      "(report_receipt_product_label.xml:88)",
                      {key: row["lot"]
                       for key, row in sorted(expected.items())},
                      {key: actual.get(key, {}).get("lot", "")
                       for key in sorted(expected)})

        with ctx.step("Assert the received date, the PO name plus origin, and "
                      "QTY: <integer> are present in each block."):
            ctx.check("every block carries the %m/%d/%Y date at "
                      f"{ZPL_DATE_ORIGIN} (:94), the purchase order with its "
                      f"source, and {ZPL_QTY_PREFIX!r} — WITH the space the "
                      f"Dymo template omits — then int(move_line.quantity) "
                      f"at {ZPL_QTY_ORIGIN} (:108)",
                      {key: {"date": row["received_date"],
                             "purchase_line": row["purchase_line"],
                             "qty_payload": f"{ZPL_QTY_PREFIX}{row['qty']}",
                             "qty": row["qty"]}
                       for key, row in sorted(expected.items())},
                      {key: {"date": actual.get(key, {}).get("received_date",
                                                             ""),
                             "purchase_line":
                                 actual.get(key, {}).get("purchase_line", ""),
                             "qty_payload":
                                 actual.get(key, {}).get("qty_payload", ""),
                             "qty": actual.get(key, {}).get("qty")}
                       for key in sorted(expected)})

        with ctx.step("Assert the values in steps 8-10 are identical to those "
                      "on the Dymo label for the same move line (compare "
                      "against TC212's captured output)."):
            # Rendered here, from THIS receipt, rather than carried across
            # from TC212 — module docstring, adaptation 4.
            dymo_ok, dymo_html, dymo_error = _render(ctx, REPORT_NAME_DYMO,
                                                     picking_id, "html")
            ctx.check_true("the Dymo report rendered for the parity check",
                           dymo_ok, dymo_error or "rendered")
            dymo = _by_key([_dymo_block_facts(block)
                            for block in _label_blocks(dymo_html)])
            ctx.check("the two formats describe the same three move lines "
                      "with the same five values — the divergence the "
                      "business would only notice weeks later",
                      {key: _comparable(row)
                       for key, row in sorted(dymo.items())},
                      {key: _comparable(row)
                       for key, row in sorted(actual.items())})

        with ctx.step("On the long-purchase_source fixture, assert the "
                      "alternate layout branch was taken (the > 14 "
                      "condition)."):
            ctx.check(f"every block on the long-source receipt places the "
                      f"purchase line at {ZPL_PO_LONG_ORIGIN} "
                      f"(report_receipt_product_label.xml:97-99)",
                      {key: ZPL_PO_LONG_ORIGIN for key in sorted(expected)},
                      {key: actual.get(key, {}).get("purchase_branch", "")
                       for key in sorted(expected)})

        with ctx.step("On the short fixture, assert the default branch was "
                      "taken."):
            short = _single_line_receipt(ctx, "WF015 SHORT", "SHORT")
            short_ok, short_stream, short_error = _render(
                ctx, REPORT_NAME_ZPL, short["picking_id"], "text")
            ctx.check_true("the short-source receipt rendered", short_ok,
                           short_error or "rendered")
            short_blocks = [_zpl_block_facts(block)
                            for block in zpl_blocks(short_stream)]
            ctx.check(f"a purchase_source of 14 characters or fewer places "
                      f"the purchase line at {ZPL_PO_SHORT_ORIGIN} "
                      f"(report_receipt_product_label.xml:100-102)",
                      {"source_length": 11, "blocks": 1,
                       "branch": ZPL_PO_SHORT_ORIGIN},
                      {"source_length": len("WF015 SHORT"),
                       "blocks": len(short_blocks),
                       "branch": (short_blocks[0]["purchase_branch"]
                                  if short_blocks else "")})
            # Plan finding 11: the template has a THIRD branch the workbook
            # does not mention, and it is the default state of a manually
            # created purchase order. Exercised here so the case covers every
            # path the source can take.
            absent = _single_line_receipt(ctx, False, "NOSRC")
            absent_ok, absent_stream, absent_error = _render(
                ctx, REPORT_NAME_ZPL, absent["picking_id"], "text")
            ctx.check_true("the source-less receipt rendered", absent_ok,
                           absent_error or "rendered")
            absent_blocks = [_zpl_block_facts(block)
                             for block in zpl_blocks(absent_stream)]
            absent_order = order_row(rpc, absent["order_id"],
                                     ["name", "origin"])
            ctx.check(f"a falsy purchase_source takes the third, "
                      f"undocumented branch at {ZPL_PO_NO_SOURCE_ORIGIN} and "
                      f"prints the purchase order alone "
                      f"(report_receipt_product_label.xml:105-107)",
                      {"blocks": 1, "branch": ZPL_PO_NO_SOURCE_ORIGIN,
                       "purchase_line": absent_order["name"]},
                      {"blocks": len(absent_blocks),
                       "branch": (absent_blocks[0]["purchase_branch"]
                                  if absent_blocks else ""),
                       "purchase_line": (absent_blocks[0]["purchase_line"]
                                         if absent_blocks else "")})

        with ctx.step("Assert the stream is plain text with no PDF wrapper "
                      "and no paperformat applied."):
            defaults = rpc.search("report.paperformat",
                                  [("default", "=", True)])
            ctx.check("the ZPL report declares no paperformat at all "
                      "(reports/report_views.xml:14-21) and the stream is raw "
                      "ZPL, not a PDF",
                      {"paperformat_id": False, "starts_with_pdf": False,
                       "contains_pdf_marker": False, "opens_a_label": True},
                      {"paperformat_id": (record or {}).get("paperformat_id"),
                       "starts_with_pdf": stream.lstrip().startswith("%PDF"),
                       "contains_pdf_marker": "%PDF-" in stream,
                       "opens_a_label": "^XA" in stream})
            ctx.log(f"report.paperformat rows flagged default=True on this "
                    f"target: {len(defaults)} (recorded, not asserted — a "
                    f"qweb-text report reads no paperformat, which is why the "
                    f"workbook's concern about the three default=True label "
                    f"formats cannot reach this stream)")
    finally:
        _cleanup(rpc, uid, previous_tz)
    if uid is not None:
        ctx.check("the acting user's timezone was restored", previous_tz,
                  user_timezone(rpc, uid))


# ==================================================================== TC214
@test_case(
    id="TEST-WF015-TC214",
    name="A failed incoming quality check records one of the 19 "
         "Reason-for-Return codes",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_purchase_stock",
    priority="P1", kind="HYBRID", order=15214,
    description="quality.check.wizard.confirm_fail writes the selected code "
                "onto every record in check_ids before super() runs, so both "
                "checks carry it while only the current one reaches "
                "quality_state 'fail'; the wizard offers exactly the 19 codes "
                "901-919 immediately after additional_note, the check form "
                "hides the field on a passed check, the ORM accepts a failed "
                "check with no code, and all three copies of the taxonomy are "
                "byte-identical.",
    traceability=trace("DATAONE-TC214"))
def test_tc214(ctx):
    rpc = ctx.adapter.rpc
    require_reason_for_return(ctx)
    open_namespace(ctx)
    expected_codes = [list(pair) for pair in REASON_FOR_RETURN]
    fail_code = "903"
    try:
        with ctx.step("Log in as the quality inspector and open the incoming "
                      "transfer's quality check."):
            ctx.log(_role_note("TD-U-03 (quality inspector)"))
            # The operation type is COPIED, never flagged in place: a quality
            # point attached to the warehouse's own incoming type would
            # generate checks for live receipts (hard rule 3).
            picking_type_id = make_picking_type(rpc, "QC-IN", "incoming")
            vendor_id = ensure_vendor(rpc)
            product_id = make_product(ctx, "TD-P-04", tracking="none")
            order_id = make_purchase_order(
                ctx, [po_line_values(ctx, product_id, 2.0,
                                     FIXTURE_DATE_PLANNED)],
                partner_id=vendor_id, picking_type_id=picking_type_id,
                label="QC")
            confirm_purchase_order(rpc, order_id)
            picking_ids = order_picking_ids(rpc, order_id)
            if not picking_ids:
                ctx.blocked(
                    "The confirmed purchase order produced no receipt on "
                    f"{ctx.env.key} (db={ctx.env.db}), so there is no "
                    "incoming transfer to hang a quality check on.")
            picking_id = picking_ids[0]
            point_id = make_quality_point(rpc, picking_type_id, product_id)
            auto_checks = checks_of_picking(rpc, picking_id)
            ctx.log(f"quality.point {point_id} covers only the copied "
                    f"operation type {picking_type_id} and only the fixture "
                    f"product; checks auto-generated on this receipt: "
                    f"{len(auto_checks)} (recorded — every assertion below "
                    f"names its own check ids)")
            # Three checks: two driven through the wizard together (step 8),
            # one passed (step 12). Created through the ORM with NO code,
            # which is already half of step 13.
            first_id = make_quality_check(rpc, picking_id, product_id,
                                          point_id, label="QC-1")
            second_id = make_quality_check(rpc, picking_id, product_id,
                                           point_id, label="QC-2")
            passed_id = make_quality_check(rpc, picking_id, product_id,
                                           point_id, label="QC-3")
            rows = rpc.read("quality.check",
                            [first_id, second_id, passed_id],
                            ["quality_state", "reason_for_return",
                             "picking_id"])
            ctx.check("three open checks exist on the receipt, none of them "
                      "carrying a code",
                      {"states": ["none", "none", "none"],
                       "codes": [False, False, False],
                       "pickings": [picking_id] * 3},
                      {"states": [row["quality_state"] for row in rows],
                       "codes": [row["reason_for_return"] for row in rows],
                       "pickings": [m2o_id(row["picking_id"])
                                    for row in rows]})

        with ctx.step("Press Fail."):
            # On the CHECK FORM the Fail button is core's do_fail, which only
            # writes the state (O17 enterprise-17.0/quality_control/views/
            # quality_views.xml:223-224 -> quality/models/quality.py:249-253).
            # The surface that carries Reason for Return is the WIZARD, opened
            # by the public quality.check.action_open_quality_check_wizard
            # (O17 quality_control/models/quality.py:351-363) — the path the
            # receipt's Quality Check button takes.
            wizard_action = rpc.call("quality.check",
                                     "action_open_quality_check_wizard",
                                     [[first_id, second_id]])

        with ctx.step("Assert the quality.check.wizard opens."):
            context = (wizard_action or {}).get("context") or {}
            ctx.check("the Fail path opens the quality.check.wizard as a "
                      "dialog over both selected checks",
                      {"type": "ir.actions.act_window",
                       "res_model": "quality.check.wizard",
                       "target": "new",
                       "default_check_ids": sorted([first_id, second_id]),
                       "default_current_check_id": min(first_id, second_id)},
                      {"type": (wizard_action or {}).get("type"),
                       "res_model": (wizard_action or {}).get("res_model"),
                       "target": (wizard_action or {}).get("target"),
                       "default_check_ids": context.get("default_check_ids"),
                       "default_current_check_id":
                           context.get("default_current_check_id")})

        with ctx.step("Assert a Reason for Return dropdown appears "
                      "immediately after additional_note."):
            wizard_root = _parse(_arch_of(ctx, "quality.check.wizard",
                                          XMLID_QC_WIZARD_FORM, "form"))
            note_node = _field_node(wizard_root, "additional_note")
            reason_node = _field_node(wizard_root, "reason_for_return")
            siblings, gap, offset = [], [], None
            if note_node is not None and reason_node is not None:
                parent = _parent_map(wizard_root).get(id(note_node))
                siblings = list(parent) if parent is not None else []
                if note_node in siblings and reason_node in siblings:
                    start = siblings.index(note_node)
                    end = siblings.index(reason_node)
                    offset = end - start
                    gap = [node.tag for node in siblings[start + 1:end]]
            ctx.check("the injected field follows additional_note with only "
                      "the module's own label div between them, and carries "
                      "NO invisible modifier "
                      "(wizard/quality_check_wizard.xml:9-12)",
                      {"present": True, "same_parent": True, "offset": 2,
                       "between": ["div"], "invisible": None},
                      {"present": reason_node is not None,
                       "same_parent": bool(siblings) and reason_node
                       in siblings,
                       "offset": offset, "between": gap,
                       "invisible": (reason_node.get("invisible")
                                     if reason_node is not None else None)})

        with ctx.step("Assert the dropdown offers exactly 19 values, 901 "
                      "through 919."):
            offered = selection_of(rpc, "quality.check.wizard",
                                   "reason_for_return")
            ctx.check("the wizard offers the 19 controlled codes verbatim, "
                      "keys and labels (wizard/quality_check_wizard.py:6-28) "
                      "— including the Unicode EN DASH in 902 where 903 and "
                      "904 use an ASCII hyphen",
                      {"count": len(expected_codes), "pairs": expected_codes},
                      {"count": len(offered), "pairs": offered})

        with ctx.step("Select a code and confirm the failure."):
            # confirm_fail is PUBLIC on both versions; DTO's override writes
            # the code onto EVERY check_ids record (wizard/
            # quality_check_wizard.py:32) BEFORE super() (:34).
            raised, message, wizard_id, result = "", "", None, None
            try:
                wizard_id, result = fail_checks_with_reason(
                    rpc, [first_id, second_id], fail_code)
            except OdooRPCError as exc:
                raised, message = "raised", str(exc)
            ctx.check("the wizard accepted the code and confirmed the failure "
                      "over both selected checks",
                      {"outcome": "", "selected": fail_code},
                      {"outcome": raised or "", "selected": fail_code})
            ctx.log(f"wizard {wizard_id} confirm_fail returned: {result!r} "
                    f"{('error: ' + message) if message else ''}")

        with ctx.step("Assert the chosen code is written onto the "
                      "quality.check record."):
            first_row = rpc.read("quality.check", [first_id],
                                 ["reason_for_return", "quality_state"])[0]
            ctx.check("the failed check carries the selected code",
                      fail_code, first_row["reason_for_return"])

        with ctx.step("Assert it was written onto every record in "
                      "self.check_ids — repeat with two checks selected and "
                      "assert both carry the code."):
            both = rpc.read("quality.check", [first_id, second_id],
                            ["reason_for_return", "quality_state"])
            # Core's confirm_fail fails only current_check_id (O17
            # enterprise-17.0/quality_control/wizard/quality_check_wizard.py:
            # 88), while DTO's write covers the whole set (:32) — so the code
            # propagates further than the state does. Both halves asserted.
            ctx.check("both selected checks carry the code, and the state "
                      "moved only on the current one",
                      {"codes": [fail_code, fail_code],
                       "states": ["fail", "none"]},
                      {"codes": [row["reason_for_return"] for row in both],
                       "states": [row["quality_state"] for row in both]})

        with ctx.step("Assert the code was written before super() ran — i.e. "
                      "the failed check's final state carries it."):
            final = rpc.read("quality.check", [first_id],
                             ["reason_for_return", "quality_state",
                              "control_date"])[0]
            ctx.check("after the whole call chain the failed check holds both "
                      "the code and the failure — the write at "
                      "wizard/quality_check_wizard.py:32 precedes super() at "
                      ":34, so nothing in core's do_fail can clear it",
                      {"reason_for_return": fail_code,
                       "quality_state": "fail", "control_date_set": True},
                      {"reason_for_return": final["reason_for_return"],
                       "quality_state": final["quality_state"],
                       "control_date_set": bool(final["control_date"])})

        with ctx.step("Assert quality_state is fail."):
            ctx.check("the current check is failed", "fail",
                      rpc.read("quality.check", [first_id],
                               ["quality_state"])[0]["quality_state"])

        with ctx.step("Assert the Reason for Return field is visible on the "
                      "check while quality_state != 'pass'."):
            check_root = _parse(_arch_of(ctx, "quality.check",
                                         XMLID_QC_CHECK_FORM, "form"))
            node = _field_node(check_root, "reason_for_return")
            ctx.check("the check form carries the field with the modifier "
                      "that hides it only on a passed check "
                      "(views/quality_check_views.xml:16), so on this failed "
                      "check it renders",
                      {"present": True,
                       "invisible": "quality_state == 'pass'",
                       "state_of_this_check": "fail"},
                      {"present": node is not None,
                       "invisible": (node.get("invisible")
                                     if node is not None else None),
                       "state_of_this_check":
                           rpc.read("quality.check", [first_id],
                                    ["quality_state"])[0]["quality_state"]})

        with ctx.step("Pass a different check and assert the field is hidden "
                      "(invisible=\"quality_state == 'pass'\") and nothing "
                      "was written."):
            # do_pass is PUBLIC on quality.check (O17 enterprise-17.0/quality/
            # models/quality.py:255-258).
            rpc.call("quality.check", "do_pass", [passed_id])
            passed_row = rpc.read("quality.check", [passed_id],
                                  ["quality_state", "reason_for_return"])[0]
            ctx.check("the passed check holds no code and the same modifier "
                      "now evaluates true, so the field is hidden",
                      {"quality_state": "pass", "reason_for_return": False,
                       "modifier": "quality_state == 'pass'",
                       "modifier_matches_state": True},
                      {"quality_state": passed_row["quality_state"],
                       "reason_for_return": passed_row["reason_for_return"],
                       "modifier": (node.get("invisible")
                                    if node is not None else None),
                       "modifier_matches_state":
                           passed_row["quality_state"] == "pass"})

        with ctx.step("Assert the field is not required at model level — "
                      "create a failed check through the ORM with no code and "
                      "assert it succeeds. The requirement is view-driven "
                      "only."):
            declared = _field_info(rpc, "quality.check", "reason_for_return",
                                   ["required", "store", "type"])
            orm_id = make_quality_check(rpc, picking_id, product_id, point_id,
                                        label="QC-4")
            rpc.call("quality.check", "do_fail", [orm_id])
            orm_row = rpc.read("quality.check", [orm_id],
                               ["quality_state", "reason_for_return"])[0]
            ctx.check("models/quality_check.py:6-27 declares no required=, so "
                      "a check can be created and failed through the ORM with "
                      "no code at all",
                      {"required": False, "type": "selection",
                       "created": True, "quality_state": "fail",
                       "reason_for_return": False},
                      {"required": bool(declared.get("required")),
                       "type": declared.get("type"),
                       "created": bool(orm_id),
                       "quality_state": orm_row["quality_state"],
                       "reason_for_return": orm_row["reason_for_return"]})

        with ctx.step("Compare the 19-value list against the copy used on "
                      "stock.picking.reason_for_return (F088) and assert the "
                      "two are identical; record any divergence."):
            if not rpc.field_exists("stock.picking", "reason_for_return"):
                ctx.blocked(
                    "stock.picking.reason_for_return is absent on "
                    f"{ctx.env.key} (db={ctx.env.db}), so the RMA copy of the "
                    "taxonomy does not exist to be compared. It is declared "
                    "by 3rd-addons/stock_picking_auto_create_lot/models/"
                    "stock_picking.py:11-33; without that module installed "
                    "this drift check has nothing on the other side of the "
                    "comparison, which is an environment gap and not a "
                    "product defect.")
            live = {model: selection_of(rpc, model, "reason_for_return")
                    for model in REASON_TAXONOMY_MODELS}
            ctx.check("all three copies of the taxonomy — quality.check "
                      "(models/quality_check.py:6-27), quality.check.wizard "
                      "(wizard/quality_check_wizard.py:6-28) and "
                      "stock.picking "
                      "(3rd-addons/stock_picking_auto_create_lot/models/"
                      "stock_picking.py:11-33) — are identical key for key "
                      "and label for label",
                      {model: expected_codes
                       for model in REASON_TAXONOMY_MODELS},
                      live)
            ctx.log("FINDING: the 19 codes are duplicated in three source "
                    "files with no shared definition. Updating two of the "
                    "three would leave quality failures and RMAs sharing no "
                    "vocabulary, with no error anywhere — this assertion is "
                    "the only detector. WF-015's recommendation is to "
                    "refactor the three copies into one shared selection "
                    "helper. Pairs with INV/DATAONE-TC186 step 13.")
    finally:
        # The workbook's expected final state is "one failed check carrying a
        # code". Hard rules 3 and 5 outrank it: everything this run created is
        # namespaced with fixture_token() and removed here, and any case that
        # needs a failed check builds its own. Never raises.
        try:
            sweep_wf015(rpc)
        except Exception:  # noqa: BLE001
            pass
        ctx.log(f"fixture token swept: {fixture_token()}")
