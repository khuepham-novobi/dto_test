"""DATAONE-WF-011 — blind ship and the printed documents: TC156, TC162-TC165.

Abbreviations used below: ``DTO`` = ``D:/Projects/dataone/DTO-Odoo`` (project
addons, read on branch **main** — the v17 baseline — because the working tree
is checked out on ``UAT``, which already carries the v19 port), ``O17`` =
``D:/Projects/dataone/odoo-17.0``, ``O19`` = ``D:/Projects/odoo-19.0``.

What this file proves
---------------------

**TC156 — a shipping label is creatable by hand and carries Pieces (F078).**
PrintNode ships ``shipping.label`` with ``carrier_id`` / ``picking_id`` /
``tracking_numbers`` / ``label_ids`` / ``return_label_ids`` all
``readonly=True`` and a list view declared ``create="false" edit="false"``
(``DTO 3rd-addons/printnode_base/models/shipping_label.py:16-60`` and
``views/shipping_label_views.xml:36-52``). ``dto_stock`` reopens every one of
them, adds ``pieces = fields.Float('Pieces')`` and defaults ``label_status`` to
``'active'`` (``DTO project-addons/dto_stock/models/shipping_label.py:10-16``),
forces ``create="1" edit="1" editable="bottom"`` onto a primary copy of the
list and makes ``label_status`` read-only **in that list**
(``dto_stock/views/shipping_label_views.xml:3-21``), and pins that list on the
picking form with ``context={'tree_view_ref':
'dto_stock.shipping_label_tree_on_picking'}``
(``dto_stock/views/stock_picking_views.xml:19-21``). The same module re-declares
PrintNode's OWN ACL xml id ``printnode_base.shipping_label_group_user`` as
``1,1,1,0`` where PrintNode ships ``1,0,1,0``
(``dto_stock/security/ir.model.access.csv:3`` vs
``printnode_base/security/ir.model.access.csv:53``) — the write permission
without which "hand-edited" would be a view-only illusion. All of that is
asserted; the case then reports BLOCKED for the reason below.

**TC162 — the blind-ship flag is one order-level decision (F043).**
``ship_blind = fields.Boolean(related='sale_id.ship_blind')`` on the picking
(``DTO project-addons/dto_sale_stock/models/stock_picking.py:10``) — related,
**not stored**, and **not** ``readonly=False``, over
``sale.order.ship_blind = fields.Boolean(..., tracking=True)``
(``dto_sale_stock/models/sale_order.py:10``). The decisive assertion is
``fields_get('stock.picking')['ship_blind']`` reading ``store: False``,
``related: 'sale_id.ship_blind'``, ``readonly: True``: that is what catches a
port re-implementing the flag as a stored copy written at picking creation,
which would pass the workbook's steps 1-6 and fail step 7 (the DONE picking).
A related field with no inverse cannot be written through — ``Field.write``
only touches the cache and ``determine_inverses`` stays empty, because
``setup_related`` installs ``_inverse_related`` **only** under the guard
``if self.inherited or not (self.readonly or field.readonly):``
(``O17 odoo/fields.py:620-622``, where ``field`` is the *related* field). A
related field defaults to ``readonly=True``
(``O17 odoo/fields.py:446-452``, the ``if attrs.get('related')`` block) and
``ship_blind`` is not ``inherited``, so the guard is False and no inverse is
installed. ``BaseModel.write`` then finds nothing in ``determine_inverses``
to run for it (``O17 odoo/models.py:4474-4497`` — ``_validate_fields`` at
``:4474``, ``determine_inverse`` at ``:4484``), so the untick of step 8
silently does not take. The exact refusal text (if any) is **[UNVERIFIED]**
and is logged, never asserted.

**TC163 — one click prints every non-cancelled outgoing picking (F044).**
``DTO project-addons/dto_sale_stock/models/ir_actions_report.py:12-18``
overrides ``_render_qweb_pdf`` and, when ``report_ref`` is one of the two
**literal strings** ``'stock.report_deliveryslip'`` /
``'dto_sale_stock.report_ship_blind'``, expands ``res_ids`` with
``pickings |= sale_pickings.sale_id.picking_ids.filtered(lambda p:
p.picking_type_code == 'outgoing' and p.state != 'cancel')``. Note ``|=``:
an already-selected picking is never duplicated, which is why the workbook's
step 11 holds by construction. ``_render_qweb_pdf`` is **private** and so not
RPC-dispatchable; its only public entry point is
``GET /report/pdf/<report_name>/<ids>``, because
``O17 addons/web/controllers/report.py:41-44`` passes the report name in as a
**string**. ``/report/html/`` routes to ``_render_qweb_html`` (``:39``), which
F044 does **not** override — substituting it would report a green pass for a
dead feature, so this case never does. The ``PACKING SLIP`` marker itself comes
from ``header_report_name`` (``dto_sale_stock/report/report_delivery_document.
xml:6``) rendered through F048's ``div[@name='moto']`` replacement, declared for
``web.external_layout_standard`` **only**
(``dto_sale_stock/report/report_templates.xml:3-11``) — hence the
``require_standard_layout`` precondition, so a step-7 failure can only mean
F044.

**TC164 — the Blind Packing Slip discloses nothing (F043 + F048).**
``dto_sale_stock/report/report_ship_blind.xml`` is a ``primary="True"``
inherit of ``dto_sale_stock.report_delivery_document``: ``:5-8`` sets
``report_header_style`` and ``report_footer_style`` to ``'display: none;'``;
``:10-12`` inserts ``<h2>PACKING SLIP</h2>``; ``:15-17`` restricts the ship-to
widget to ``{"widget": "contact", "fields": ["address"], "no_marker": True,
"phone_icons": False}``; ``:20-31`` puts ``class="d-none"`` on
``customer_address``, ``partner_header`` and ``div_origin``; ``:34-39`` hides
``move.product_id`` and prints ``move.product_id.name`` beside it.
``report_header_style`` is consumed by **core**: v17 carries
``t-att-style="report_header_style"`` on all four ``external_layout`` header
divs (``O17 addons/web/views/report_templates.xml:309, 368, 430, 492``) while
**v19 carries it on ``external_layout_bold`` ONLY** (``O19 :438-439``;
``_striped`` ``:311``, ``_boxed`` ``:373``, ``_standard`` ``:502`` and the three
new layouts ``_folder`` ``:563`` / ``_wave`` ``:651`` / ``_bubble`` ``:724`` have
no such hook). ``report_footer_style`` is consumed by F048's own patch of the
four footers (``report_templates.xml:12-33``). So on v19 the blind slip prints
**with the company header restored** unless the company is on the bold layout —
the silent commercial-disclosure failure this case exists for, established in
source rather than suspected.

**TC165 — the packing-slip body (F045/F077/F078/F079).**
``dto_sale_stock/report/report_delivery_document.xml`` xpaths
``//div[@t-if='not o.signature']`` (``O17 addons/stock/report/
report_deliveryslip.xml:197``) and inserts, in order: the
``name="shipping_label_table"`` table under ``t-if="o.shipping_label_ids"``
(``:9``) whose four headers are ``Shipping Method`` · **``Tracking/Pro Number``**
· ``Pieces`` · ``Weight`` (``:13-16`` — the source says a **slash** where the
workbook prose writes a hyphen, and the source string is what is asserted),
one ``<tr>`` per label (``:20``) with the SAME ``o.shipping_weight`` on every row
(``:10, :31``); the boxes grid chunked ``[o.box_ids[i:i+12] …]`` (``:38``) with
padding ``<td>``s for the short row (``:46``) and each populated cell printing
``box.name`` and ``box.weight`` suffixed ``lb`` (``:43-44``); and the ``note`` /
``memo_to_suppliers`` paragraphs (``:51-56``).

Expected outcomes
-----------------
* ``TC156`` — **EXPECTED v17 OUTCOME: PASS for steps 1-11, then BLOCKED.**
  v19: BLOCKED before the first assertion (``require_printnode_labels``).
  Decision D-1 drops PrintNode for v19 with no replacement model and the v19
  port deletes ``dto_stock/models/shipping_label.py`` outright, so the case is
  unexecutable there and must report BLOCKED, never FAILED.
* ``TC162`` — **EXPECTED v17 OUTCOME: PASS.** v19: PASS; ``stock.picking.
  sale_id`` moves from a stored related (``O17 sale_stock/models/stock.py:94``)
  to a stored compute+inverse (``O19 :187``), but the related chain still
  resolves.
* ``TC163`` — **EXPECTED v17 OUTCOME: PASS**, or BLOCKED if this wkhtmltopdf
  build leaves no extractable signal in the PDF (there is no pypdf / PyPDF2 /
  pdfminer in the qa-platform venv and ``requirements.txt`` declares none).
  v19: the predicted silent failure — the override still compiles and still
  runs, so "a PDF was produced" passes while the section count drops to 1 the
  moment either literal ``report_ref`` changes.
* ``TC164`` — **EXPECTED v17 OUTCOME: PASS for the structural half, then
  BLOCKED.** v19: the structural half is expected to **FAIL on the header** —
  ``external_layout_standard`` lost ``t-att-style="report_header_style"``, so
  ``report_header_style`` is set and never consumed. That is a defect finding
  for WF-011b, not a test bug, and the assertion is not weakened to hide it.
* ``TC165`` — **EXPECTED v17 OUTCOME: PASS.** v19: the boxes / note / memo half
  passes; the shipping-label half reports BLOCKED (the table renders under
  ``t-if="o.shipping_label_ids"``, a field that no longer exists).

Documented adaptations (hard rules 2, 3, 5, 6)
----------------------------------------------
1. **No impersonation.** Every workbook step 1 here reads "Log in as TD-U-03
   (Inventory User)". None of these five cases is an access-control case:
   TC156's editability is delivered by view attributes plus an ACL row that is
   asserted directly, and TC162-TC165 are field-, template- and render-level.
   Fixtures must be created and swept with the platform session regardless —
   the shipping-label ACL grants ``perm_unlink`` 0 even to
   ``printnode_security_group_user`` (``dto_stock/security/ir.model.access.csv:3``)
   and ``button_validate`` is gated on
   ``dto_mrp_account.group_validate_delivery_orders``, which
   ``dto_mrp_account/data/server_actions.xml:20-23`` seeds with
   ``base.user_admin``. The role is logged at step 1 of every case.
2. **No fixture is shared between cases.** TC163's precondition names "the
   shipping labels from TC156 and the boxes from TC151", TC164's names "the
   sales order from TC162" and TC162's expected final state asks for the flag to
   be left on. Hard rules 3 and 5 outrank all three: every case builds its own
   token-scoped order, and TC163 deliberately does **not** add boxes or labels
   to its pickings — wkhtmltopdf repeats the page header on every page, so any
   fixture content that spills a picking onto a second page would add a spurious
   ``PACKING SLIP`` occurrence and break the very count the case exists for
   (plan ``[UNVERIFIED-8]``).
3. **TC163 counts in the PDF with whitespace removed from both sides.**
   wkhtmltopdf emits inter-word spacing as a text-positioning operator as often
   as a literal space, so ``"PACKING SLIP"`` can reach the content stream as
   ``PACKING`` + ``SLIP``. ``_pdf_count`` strips every whitespace character from
   haystack and needle alike before counting. That cannot make an absent string
   appear — it only makes a present one countable.
4. **TC164's negatives are split.** Every literal string-absence check in the
   workbook's steps 5-10 and 12 is true only of the RENDERED PDF: the blind
   template suppresses through ``display:none`` (header, footer) and
   ``class="d-none"`` (three blocks, the product reference), so in the HTML
   render the same text is still in the DOM. What is asserted here is the
   suppression MECHANISM — the ``t-set`` values on the combined arch, the
   ``style="display: none;"`` actually rendered onto the layout's header and
   footer divs, the ``d-none`` classes, the restricted widget options, the
   ``<h2>`` — plus the two genuine text negatives that survive HTML (the company
   name and VAT must not occur outside the suppressed header/footer), plus step
   13's mandatory control. The rest is named in ``BLOCKED_PDF_EXTRACTOR``.
5. **TC164 asserts ``customer_address`` / ``partner_header`` on the combined
   arch, not on the render.** Core gates both on
   ``partner != partner.commercial_partner_id`` (``O17 addons/stock/report/
   report_deliveryslip.xml:33-37``), so for a standalone fixture customer
   neither block is emitted at all and a render-side assertion would be
   vacuous. ``ir.ui.view.get_combined_arch()`` is public on both versions
   (``O17 odoo/addons/base/models/ir_ui_view.py:920`` / ``O19 :1043``) and is the
   **same** call ``_read_template`` makes before QWeb compiles (``O17 :1928-1931``),
   so it is the template that actually renders, not an approximation.
6. **TC164 step 3's filename is asserted as the expression, not the download
   header.** ``print_report_name`` is ``safe_eval``-ed by the download
   controller, which this transport does not exercise; the stored expression is
   asserted byte-exact and the value it yields for the fixture is logged.
7. **TC164 step 12's DONE-picking caveat is recorded.** The blind template
   patches ``span[@t-field='move.product_id']``, which exists only in the
   NOT-done move table (``O17 report_deliveryslip.xml:73``). A **done** picking
   renders the aggregated move-line table instead, whose text is
   ``product_id.display_name`` (``O17 addons/stock/models/stock_move_line.py``
   ``_get_aggregated_product_quantities``) and therefore still carries
   ``[default_code]``. The fixture picking is deliberately left un-validated so
   the patched table is the one under test.
8. **TC165 step 9 counts populated cells, not ``<td>`` elements.** 13 boxes
   chunk into 2 rows of 12 and the template pads the short row, so the grid
   holds 13 populated + 11 empty = 24 ``<td>``.
9. **TC165 reads rows in the model's own order.** ``shipping.label._order =
   'create_date desc'`` (``printnode_base/models/shipping_label.py:14``), so
   ``o.shipping_label_ids`` renders newest-first, not creation order. Rows 1 and
   2 are matched against the O2M read back in that same order, and the workbook's
   literal piece counts are pinned separately as the sorted pair ``[2.0, 5.0]``.
10. **TC165 uses ``/report/html/``, and that is correct here.** This case
    asserts ONE picking's content, not F044's expansion, so the override not
    firing on that route is irrelevant — and the HTML carries the table/grid
    structure the PDF would only carry as glyphs.
11. **Numeric cells are compared as numbers.** ``<span t-field="label.pieces"/>``
    goes through the float converter with no ``digits`` (``pieces =
    fields.Float('Pieces')``), which renders ``5.0``; ``<span
    t-esc="shipping_weight"/>`` renders ``str(15.2)``. The workbook asserts the
    values 5, 2 and 15.2, so the cell text is parsed to a float rather than the
    rendering itself being frozen into the business rule.
"""
import re

from adapters.base import OdooRPCError
from framework.registry import test_case
from tests.wf011.common import (ACTION_REPORT_DELIVERY, ACTION_REPORT_SHIP_BLIND,
                                BACKORDER_MODEL, BLIND_CONTACT_OPTIONS,
                                BLIND_HIDDEN_BLOCKS, BLIND_PRINT_REPORT_NAME,
                                BLIND_REPORT_TITLE, BLIND_STYLE,
                                BLOCKED_PDF_EXTRACTOR, BLOCKED_PRINTNODE,
                                BOXES_PER_ROW, DELIVERY_PRINT_REPORT_NAME,
                                LAYOUTS_NEW_IN_V19, LAYOUTS_PATCHED_BY_F048,
                                PACKING_SLIP_TITLE, REPORT_DELIVERY_SLIP,
                                REPORT_SHIP_BLIND, SHIPPING_LABEL_DEFAULT_STATUS,
                                SHIPPING_LABEL_FIELD, SHIPPING_LABEL_MODEL,
                                SHIPPING_LABEL_STATUS_SELECTION,
                                SHIPPING_LABEL_TREE_CONTEXT,
                                SHIPPING_LABEL_TREE_XMLID,
                                SHIPPING_TABLE_HEADERS, SHIPPING_TABLE_NAME,
                                WORKFLOW, WORKFLOW_NAME, Arch, arch_of_model,
                                arch_of_xmlid, backorders_of, boxes_of,
                                company_layout_xmlid, confirm_order, count_tags,
                                create_boxes, ensure_carrier, ensure_partner,
                                expect_error, expected_box_names, html_element,
                                html_elements, html_text, list_tag, m2o_id,
                                make_picking, make_sale_order,
                                make_shipping_label, open_namespace,
                                outgoing_pickings, pdf_page_count, pdf_text,
                                picking_form_arch, picking_row,
                                process_backorder, report_html, report_pdf,
                                require_blind_report, require_boxes,
                                require_module_build, require_modules,
                                require_printnode_labels, require_sale_stack,
                                require_ship_blind, require_standard_layout,
                                save_report_artifact, shipping_labels_of,
                                sweep_wf011, tag, trace, validate_delivery)

# --------------------------------------------------------------------------
# Local constants and helpers. Nothing here duplicates common.py; each is
# either a workbook literal that belongs to this file alone, or a parsing
# utility the shared module does not provide.
# --------------------------------------------------------------------------

#: TC156 step 4's literal tracking number, verbatim from the workbook. It is
#: not token-scoped on purpose — the workbook asserts this exact value, and the
#: row is namespaced by living on a token-scoped picking, which is also how
#: sweep_wf011 removes it (by picking_id, children first).
TRACKING_TC156 = "1Z-TEST-0001"
TRACKING_TC165_A = "1Z-TC165-0001"
TRACKING_TC165_B = "1Z-TC165-0002"

#: TC165's fixture numbers, all from the workbook's preconditions.
TC165_BOXES = 13
TC165_BOX_WEIGHT = 2.5
TC165_SHIPPING_WEIGHT = 15.2
TC165_PIECES_A = 5.0
TC165_PIECES_B = 2.0

#: TC163 reports BLOCKED with this — never FAILED — when the rendered PDF
#: yields neither a greppable page object nor an inflatable text operand.
#: common.BLOCKED_PDF_EXTRACTOR is TC164's reason and says something different
#: (that the negatives are PDF-only), so it must not be reused here.
BLOCKED_NO_PDF_SIGNAL = (
    "requires a PDF text extractor — this wkhtmltopdf build left neither a "
    "greppable '/Type /Page' object nor an inflatable text operand in the "
    "rendered Delivery Slip, and no pypdf, PyPDF2 or pdfminer is installed in "
    "the qa-platform venv (requirements.txt declares none). The expansion "
    "under test lives in the PRIVATE _render_qweb_pdf "
    "(dto_sale_stock/models/ir_actions_report.py:12-18) whose only public "
    "entry point is GET /report/pdf/<report_name>/<ids> "
    "(addons/web/controllers/report.py:41-44 passes a STRING report_ref); "
    "/report/html/ routes to _render_qweb_html (:39), which F044 does NOT "
    "override, so substituting it would report a green pass for a dead "
    "feature. The section count therefore has no observable signal here.")

_WS_RE = re.compile(r"\s+")
_DIV_OPEN_RE = re.compile(r"<div\b[^>]*>", re.IGNORECASE)
_ATTR_RE = re.compile(r'([-\w:]+)\s*=\s*"([^"]*)"')


def _quiet(fn, *args, **kwargs):
    """Run a best-effort RPC call. Never raises for a server fault."""
    try:
        return fn(*args, **kwargs)
    except OdooRPCError:
        return None


def _role_note(role: str) -> str:
    """One log line recording the workbook role and why it is not impersonated."""
    return (f"workbook role {role}: recorded, not impersonated. None of the "
            f"cases in this file is an access-control case — TC156's "
            f"editability is a view attribute plus an ACL row that is asserted "
            f"directly, and TC162-TC165 are field-, template- and "
            f"render-level. Fixtures must be created and swept with the "
            f"platform session anyway: the shipping.label ACL grants "
            f"perm_unlink 0 to printnode_security_group_user "
            f"(dto_stock/security/ir.model.access.csv:3) and button_validate is "
            f"gated on dto_mrp_account.group_validate_delivery_orders, which "
            f"dto_mrp_account/data/server_actions.xml:20-23 seeds with "
            f"base.user_admin.")


def _squash(text) -> str:
    """Every whitespace character removed — see adaptation 3."""
    return _WS_RE.sub("", text or "")


def _pdf_count(text, needle: str) -> int:
    """Occurrences of ``needle`` in PDF-extracted text, whitespace-insensitive."""
    return _squash(text).count(_squash(needle))


def _pdf_signal(ctx, data: bytes, label: str):
    """(text, page_count) for a rendered PDF, or BLOCKED with the exact reason.

    The stdlib page detector runs first because it is font-independent and
    survives wkhtmltopdf's glyph subsetting; the zlib text extractor is what
    the string assertions actually need. If the text extractor yields nothing
    the case reports BLOCKED naming the missing library rather than asserting
    against an empty string (plan adaptation 6).
    """
    pages = pdf_page_count(data)
    text = pdf_text(data)
    ctx.log(f"{label}: {len(data)} bytes, /Type /Page objects = {pages}, "
            f"extracted characters = {len(text) if text else 0}")
    if not text:
        ctx.blocked(f"{BLOCKED_NO_PDF_SIGNAL} (page detector returned "
                    f"{pages!r} for {label})")
    return text, pages


def _ship_blind(rpc, picking_ids) -> dict:
    """{picking_id: ship_blind} read fresh — the field is a non-stored related,
    so every read recomputes it from sale_id.ship_blind."""
    rows = rpc.read("stock.picking", list(picking_ids), ["ship_blind"])
    return {row["id"]: row["ship_blind"] for row in rows}


def _states(rpc, picking_ids) -> dict:
    rows = rpc.read("stock.picking", list(picking_ids), ["state"])
    return {row["id"]: row["state"] for row in rows}


def _short_ship(ctx, picking_id: int, qty: float) -> int:
    """Validate ``picking_id`` for ``qty`` only and confirm the backorder.

    ``button_validate`` on a short picking returns core's backorder-confirmation
    action dict (``O17 stock/models/stock_picking.py:1149-1151`` ->
    ``_action_generate_backorder_wizard`` ``:1230-1241``); pressing "Create
    Backorder" is the wizard's PUBLIC ``process()``
    (``O17 stock/wizard/stock_backorder_confirmation.py:52-68``), which reads
    ``button_validate_picking_ids`` from the context and re-validates with
    ``skip_backorder=True``. Returns the backorder's id.
    """
    rpc = ctx.adapter.rpc
    _quiet(rpc.call, "stock.picking", "action_assign", [picking_id])
    action = validate_delivery(ctx, picking_id, qty=qty)
    if not (isinstance(action, dict)
            and action.get("res_model") == BACKORDER_MODEL):
        ctx.blocked(
            f"button_validate on the short picking {picking_id} returned "
            f"{action!r} instead of the {BACKORDER_MODEL} action dict. Without "
            "the backorder dialog there is no second picking to assert "
            "against, so the fixture this case needs does not exist on "
            f"{ctx.env.key} (db={ctx.env.db}).")
    process_backorder(ctx, picking_id)
    backs = backorders_of(rpc, picking_id)
    if len(backs) != 1:
        ctx.blocked(
            f"Confirming the backorder of picking {picking_id} produced "
            f"{len(backs)} backorder(s), not 1 — the fixture is not the "
            "two-picking order every case here describes.")
    return backs[0]["id"]


def _div_blocks(html: str, token: str):
    """(attrs, outer_html) of the first div whose class carries ``token``.

    Used for the layout's own ``header`` / ``footer`` divs, which is where
    ``report_header_style`` and F048's ``report_footer_style`` land. Matching is
    on the class TOKEN, so ``footer o_standard_footer o_company_1_layout`` and
    ``o_company_1_layout footer o_background_footer`` both resolve.
    """
    for tag_text in _DIV_OPEN_RE.findall(html):
        attrs = dict(_ATTR_RE.findall(tag_text))
        if token in (attrs.get("class") or "").split():
            outer = html_elements(html, "div", "class", attrs["class"])
            return attrs, (outer[0] if outer else "")
    return {}, ""


def _text_outside(html: str, blocks) -> str:
    """Visible text of the render with the given outer-HTML blocks removed."""
    body = html
    for block in blocks:
        if block:
            body = body.replace(block, " ")
    return html_text(body)


def _t_set_value(arch: Arch, key: str):
    """The ``t-value`` of ``<t t-set="key" …>`` on a combined template arch."""
    node = arch.find(f".//t[@t-set='{key}']")
    return node.get("t-value") if node is not None else None


def _named_div_class(arch: Arch, name: str):
    node = arch.find(f".//div[@name='{name}']")
    return node.get("class") if node is not None else None


def _combined_arch(ctx, xmlid: str) -> Arch:
    """The arch QWeb actually compiles for a template, over RPC.

    ``ir.ui.view.get_combined_arch()`` is public on both versions
    (``O17 odoo/addons/base/models/ir_ui_view.py:920`` / ``O19 :1043``) and is
    exactly what ``_read_template`` hands the QWeb compiler
    (``O17 :1928-1931``), so this is the rendered template rather than a
    reconstruction of it.
    """
    rpc = ctx.adapter.rpc
    view_id = rpc.ref(xmlid)
    if not view_id:
        ctx.blocked(
            f"The QWeb template {xmlid} does not resolve on {ctx.env.key} "
            f"(db={ctx.env.db}). dto_sale_stock/report/report_ship_blind.xml:3 "
            "declares it as a primary inherit of "
            "dto_sale_stock.report_delivery_document; without it there is no "
            "blind slip to assert the suppression mechanism on.")
    return Arch(rpc.call("ir.ui.view", "get_combined_arch", [view_id]))


def _as_float(text):
    """A rendered numeric cell as a number, or the raw text when unparseable.

    Returning the raw text on failure keeps a mismatch legible instead of
    turning a content difference into an AUTOMATION_ERROR.
    """
    raw = (text or "").strip()
    for candidate in (raw, raw.replace(",", "")):
        try:
            return float(candidate)
        except ValueError:
            continue
    return raw


def _cell_texts(row_html: str) -> list:
    return [html_text(cell) for cell in html_elements(row_html, "td")]


def _cell(cells: list, index: int):
    """One rendered cell, or None — a short row must report a mismatch, not
    raise an IndexError that would hide what the render actually produced."""
    return cells[index] if len(cells) > index else None


def _carrier_name(rpc, label_row: dict):
    """``label.carrier_id.name`` — the exact expression the template prints
    (report_delivery_document.xml:22)."""
    carrier_id = m2o_id(label_row.get("carrier_id"))
    if not carrier_id:
        return None
    return rpc.read("delivery.carrier", [carrier_id], ["name"])[0]["name"]


def _boxes_grid(html: str):
    """The boxes table's outer HTML, located by its own ``<strong>Boxes</strong>``
    caption (report_delivery_document.xml:37). Returns "" when absent."""
    marker = "<strong>Boxes</strong>"
    index = html.find(marker)
    if index < 0:
        return ""
    tables = html_elements(html[index:], "table")
    return tables[0] if tables else ""


# --------------------------------------------------------------------------
# TEST-WF011-TC156
# --------------------------------------------------------------------------
@test_case(
    id="TEST-WF011-TC156",
    name="A shipping label can be created by hand on the delivery and carries "
         "a Pieces value",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_stock",
    priority="P2", kind="API", order=11156,
    description="dto_stock reopens PrintNode's read-only shipping.label, adds "
                "Pieces, forces create/edit/editable onto a primary copy of "
                "its list and pins that list on the picking form through "
                "tree_view_ref; two labels are hand-created with distinct "
                "piece counts, then the case reports BLOCKED on the dropped "
                "PrintNode dependency.",
    traceability=trace("DATAONE-TC156"))
def test_tc156(ctx):
    rpc = ctx.adapter.rpc
    open_namespace(ctx)
    try:
        with ctx.step("Log in as TD-U-03 and open the delivery."):
            require_module_build(ctx)
            require_modules(ctx, ["dto_stock", "printnode_base"])
            # Blocks with the D-1 reason on v19, BEFORE any assertion runs, so
            # the case can never report FAILED there (workbook Notes).
            require_printnode_labels(ctx)
            ctx.log(_role_note("TD-U-03"))
            partner_id = ensure_partner(ctx, "Customer Alpha")
            carrier_id = ensure_carrier(ctx, "Carrier Ground")
            picking_id = make_picking(ctx, code="outgoing", qty=4.0,
                                      partner_id=partner_id,
                                      label="TC156 Delivery")
            row = picking_row(rpc, picking_id)
            # The workbook precondition says "in state assigned"; reservation
            # depends on the clone's reservation method and is incidental to
            # label editability, so 'confirmed' is accepted and logged.
            ctx.check_true(
                "the fixture is an outgoing delivery ready to work on",
                row["picking_type_code"] == "outgoing"
                and row["state"] in ("assigned", "confirmed"),
                f"picking_type_code={row['picking_type_code']!r} "
                f"state={row['state']!r}")

        with ctx.step("Locate the Shipping Labels one2many on the picking "
                      "form."):
            form = picking_form_arch(ctx)
            node = form.find(f".//field[@name='{SHIPPING_LABEL_FIELD}']")
            attrs = rpc.call("stock.picking", "fields_get",
                             [SHIPPING_LABEL_FIELD],
                             attributes=["type", "relation", "relation_field"])
            ctx.check(
                "PrintNode's shipping_label_ids one2many is on the model and "
                "on the combined stock.picking form arch "
                "(printnode_base/models/stock_picking.py:13-17, "
                "views/stock_picking_views.xml:18-23)",
                {"in_form_arch": True, "type": "one2many",
                 "relation": SHIPPING_LABEL_MODEL,
                 "relation_field": "picking_id"},
                {"in_form_arch": node is not None,
                 "type": attrs.get(SHIPPING_LABEL_FIELD, {}).get("type"),
                 "relation": attrs.get(SHIPPING_LABEL_FIELD, {}).get("relation"),
                 "relation_field":
                     attrs.get(SHIPPING_LABEL_FIELD, {}).get("relation_field")})

        with ctx.step("Assert the embedded list is editable inline — an \"Add "
                      "a line\" affordance is present (PrintNode's own view "
                      "does not permit this)."):
            label_list = arch_of_xmlid(ctx, SHIPPING_LABEL_TREE_XMLID, "tree")
            root = label_list.root
            ctx.check(
                "dto_stock's primary copy forces create/edit/editable onto "
                "PrintNode's create=\"false\" list "
                "(dto_stock/views/shipping_label_views.xml:15-19 over "
                "printnode_base/views/shipping_label_views.xml:41)",
                {"root_tag": list_tag(ctx), "create": "1", "edit": "1",
                 "editable": "bottom", "pieces_column": True},
                {"root_tag": root.tag, "create": root.get("create"),
                 "edit": root.get("edit"), "editable": root.get("editable"),
                 "pieces_column":
                     label_list.find(".//field[@name='pieces']") is not None})
            # The other half of "editable": PrintNode ships 1,0,1,0 on its own
            # ACL xml id and dto_stock re-declares the SAME id as 1,1,1,0.
            acl_id = rpc.ref("printnode_base.shipping_label_group_user")
            acl = rpc.read("ir.model.access", [acl_id],
                           ["perm_read", "perm_write", "perm_create",
                            "perm_unlink"])[0] if acl_id else {}
            ctx.check(
                "dto_stock re-declares PrintNode's own shipping.label ACL xml "
                "id with write permission and still no unlink (F078: "
                "dto_stock/security/ir.model.access.csv:3 over "
                "printnode_base/security/ir.model.access.csv:53)",
                {"resolves": True, "perm_read": True, "perm_write": True,
                 "perm_create": True, "perm_unlink": False},
                {"resolves": bool(acl_id), "perm_read": acl.get("perm_read"),
                 "perm_write": acl.get("perm_write"),
                 "perm_create": acl.get("perm_create"),
                 "perm_unlink": acl.get("perm_unlink")})

        with ctx.step("Add a row: set Carrier, set Tracking Numbers to "
                      "1Z-TEST-0001, set Pieces to 5."):
            declared = rpc.call(
                SHIPPING_LABEL_MODEL, "fields_get",
                ["pieces", "carrier_id", "picking_id", "tracking_numbers"],
                attributes=["type", "readonly"])
            ctx.check(
                "dto_stock adds pieces and reopens the four fields PrintNode "
                "ships readonly (dto_stock/models/shipping_label.py:10-15)",
                {"pieces": {"type": "float", "readonly": False},
                 "carrier_id": {"type": "many2one", "readonly": False},
                 "picking_id": {"type": "many2one", "readonly": False},
                 "tracking_numbers": {"type": "char", "readonly": False}},
                {name: {"type": declared.get(name, {}).get("type"),
                        "readonly": declared.get(name, {}).get("readonly")}
                 for name in ("pieces", "carrier_id", "picking_id",
                              "tracking_numbers")})
            label_a = make_shipping_label(ctx, picking_id, carrier_id,
                                          TRACKING_TC156, 5.0)

        with ctx.step("Save the delivery."):
            # Each RPC call commits its own transaction, so the create IS the
            # save; re-reading the one2many is what proves it persisted.
            stored = rpc.read("stock.picking", [picking_id],
                              [SHIPPING_LABEL_FIELD])[0][SHIPPING_LABEL_FIELD]
            ctx.check("the hand-created label persisted on the delivery",
                      [label_a], stored)

        with ctx.step("Assert one shipping.label record exists with picking_id "
                      "equal to this delivery."):
            ctx.check("exactly one shipping.label points at this delivery",
                      [label_a],
                      rpc.search(SHIPPING_LABEL_MODEL,
                                 [("picking_id", "=", picking_id)]))

        with ctx.step("Assert pieces == 5.0."):
            first = rpc.read(SHIPPING_LABEL_MODEL, [label_a], ["pieces"])[0]
            ctx.check("the hand-entered piece count round-trips", 5.0,
                      first["pieces"])

        with ctx.step("Assert tracking_numbers == '1Z-TEST-0001' and "
                      "carrier_id is the chosen carrier."):
            stored = rpc.read(SHIPPING_LABEL_MODEL, [label_a],
                              ["tracking_numbers", "carrier_id"])[0]
            ctx.check("the tracking number and carrier round-trip",
                      {"tracking_numbers": TRACKING_TC156,
                       "carrier_id": carrier_id},
                      {"tracking_numbers": stored["tracking_numbers"],
                       "carrier_id": m2o_id(stored["carrier_id"])})

        with ctx.step("Assert label_status == 'active' and that the field is "
                      "read-only in the form."):
            # WORKBOOK CORRECTION, established in source: dto_stock makes
            # label_status readonly in the embedded LIST
            # (views/shipping_label_views.xml:12-14) — and the embedded list is
            # what the workbook's own steps 2-3 call "the form". On the
            # standalone shipping.label FORM dto_stock's inherit sets only
            # create/edit (:28-31), and PrintNode's own form declares
            # <field name="label_status"/> bare
            # (3rd-addons/printnode_base/views/shipping_label_views.xml:29), so
            # the field carries no readonly there.
            #
            # The LIST readonly is the assertion. The form reading is RECORDED,
            # NOT ASSERTED: pinning it to None would pin an ABSENCE on a
            # commercial vendor's own view, so a VentorTech release that added
            # readonly="1" to its form — an improvement, and not a DataOne
            # regression — would fail this case for the wrong reason.
            status = rpc.read(SHIPPING_LABEL_MODEL, [label_a],
                              ["label_status"])[0]["label_status"]
            defaults = rpc.call(SHIPPING_LABEL_MODEL, "default_get",
                                ["label_status"])
            selection = rpc.call(SHIPPING_LABEL_MODEL, "fields_get",
                                 ["label_status"], attributes=["selection"])
            pairs = [tuple(p) for p in
                     selection.get("label_status", {}).get("selection") or []]
            list_node = label_list.find(".//field[@name='label_status']")
            form_arch = arch_of_model(ctx, SHIPPING_LABEL_MODEL, "form")
            form_node = form_arch.find(".//field[@name='label_status']")
            ctx.log(
                "[recorded, not asserted] label_status readonly on the "
                "STANDALONE shipping.label form: "
                f"{(form_node.get('readonly') if form_node is not None else None)!r}"
                " (PrintNode's own view, 3rd-addons/printnode_base/views/"
                "shipping_label_views.xml:29; dto_stock's form inherit touches "
                "only create/edit, :28-31). The workbook's read-only "
                "requirement is met by the EMBEDDED LIST, which is asserted "
                "below.")
            ctx.check(
                "label_status defaults to 'active' and is read-only in the "
                "EMBEDDED LIST dto_stock pins on the picking form "
                "(dto_stock/views/shipping_label_views.xml:12-14)",
                {"value": SHIPPING_LABEL_DEFAULT_STATUS,
                 "default_get": SHIPPING_LABEL_DEFAULT_STATUS,
                 "selection": SHIPPING_LABEL_STATUS_SELECTION,
                 "readonly_in_list": "1"},
                {"value": status,
                 "default_get": defaults.get("label_status"),
                 "selection": pairs,
                 "readonly_in_list": (list_node.get("readonly")
                                      if list_node is not None else None)})

        with ctx.step("Assert the embedded list used is "
                      "dto_stock.shipping_label_tree_on_picking (read the "
                      "resolved view id from the form's context key), not "
                      "PrintNode's own list."):
            # Step 10 IS the tree_view_ref -> list_view_ref detector: v19
            # renames the key and this string stops resolving to anything.
            context_attr = node.get("context") if node is not None else None
            view_id = rpc.ref(SHIPPING_LABEL_TREE_XMLID)
            view_row = rpc.read("ir.ui.view", [view_id],
                                ["model", "mode", "inherit_id"])[0] \
                if view_id else {}
            ctx.check(
                "the picking form pins dto_stock's list through tree_view_ref "
                "(dto_stock/views/stock_picking_views.xml:20) and that xml id "
                "is a primary copy of PrintNode's list",
                {"context": SHIPPING_LABEL_TREE_CONTEXT, "resolves": True,
                 "model": SHIPPING_LABEL_MODEL, "mode": "primary",
                 "inherits": rpc.ref("printnode_base.shipping_label_tree")},
                {"context": context_attr, "resolves": bool(view_id),
                 "model": view_row.get("model"), "mode": view_row.get("mode"),
                 "inherits": m2o_id(view_row.get("inherit_id"))})

        with ctx.step("Add a second row with Pieces = 2 and save; assert both "
                      "rows persist with distinct pieces."):
            label_b = make_shipping_label(ctx, picking_id, carrier_id,
                                          "1Z-TEST-0002", 2.0)
            rows = shipping_labels_of(rpc, picking_id)
            ctx.check(
                "two hand-created labels persist with distinct piece counts "
                "and status Active",
                {"rows": 2, "pieces": [2.0, 5.0],
                 "statuses": [SHIPPING_LABEL_DEFAULT_STATUS,
                              SHIPPING_LABEL_DEFAULT_STATUS],
                 "ids": sorted([label_a, label_b])},
                {"rows": len(rows),
                 "pieces": sorted(r["pieces"] for r in rows),
                 "statuses": sorted(r["label_status"] for r in rows),
                 "ids": sorted(r["id"] for r in rows)})

        # The offline half is complete. The case exists for a model owned by a
        # commercial module the v19 target does not carry (decision D-1), so it
        # closes BLOCKED rather than claiming a v19-relevant pass.
        ctx.blocked(BLOCKED_PRINTNODE)
    finally:
        # The workbook's postcondition asks for both rows to be left for TC163
        # and TC165; hard rules 3 and 5 outrank it — those cases build their
        # own. This block can never raise.
        try:
            sweep_wf011(rpc)
        except Exception:  # noqa: BLE001
            pass


# --------------------------------------------------------------------------
# TEST-WF011-TC162
# --------------------------------------------------------------------------
@test_case(
    id="TEST-WF011-TC162",
    name="The blind-ship flag is set on the sales order and propagates "
         "read-only to every picking",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_sale_stock",
    priority="P1", kind="API", order=11162,
    description="stock.picking.ship_blind is a non-stored related of "
                "sale_id.ship_blind: it reaches the already-done picking and "
                "every future backorder, cannot be unticked downstream, and "
                "follows the order back to False in the same transaction.",
    traceability=trace("DATAONE-TC162"))
def test_tc162(ctx):
    rpc = ctx.adapter.rpc
    open_namespace(ctx)
    try:
        with ctx.step("Log in as TD-U-03 and open both pickings."):
            require_module_build(ctx)
            require_modules(ctx, ["dto_sale_stock", "dto_stock"])
            require_sale_stack(ctx)
            require_ship_blind(ctx)
            ctx.log(_role_note("TD-U-03 (reads the pickings) / TD-U-01 (sets "
                               "the flag on the order)"))
            order_id = make_sale_order(ctx, label="TC162 Order", qty=12.0,
                                       ship_blind=False,
                                       memo=tag("Memo for TC162"))
            confirm_order(ctx, order_id)
            pickings = outgoing_pickings(rpc, order_id)
            ctx.check("the confirmed order produced one outgoing picking",
                      1, len(pickings))
            first = pickings[0]["id"]
            # One done picking and one backorder — the workbook's precondition,
            # rebuilt here rather than inherited from TC161 (hard rule 5).
            second = _short_ship(ctx, first, 5.0)
            ctx.check(
                "the fixture is one DONE picking plus one open backorder of "
                "the same order",
                {"first": "done", "second_is_open": True,
                 "both_outgoing": True},
                {"first": _states(rpc, [first])[first],
                 "second_is_open":
                     _states(rpc, [second])[second] not in ("done", "cancel"),
                 "both_outgoing": all(
                     r["picking_type_code"] == "outgoing"
                     for r in rpc.read("stock.picking", [first, second],
                                       ["picking_type_code"]))})

        with ctx.step("Assert ship_blind reads False on both."):
            ctx.check("neither picking starts blind",
                      {first: False, second: False},
                      _ship_blind(rpc, [first, second]))

        with ctx.step("Log in as TD-U-01 and open the sales order."):
            order = rpc.read("sale.order", [order_id],
                             ["state", "ship_blind"])[0]
            ctx.check("the order is confirmed and un-blind",
                      {"state": "sale", "ship_blind": False},
                      {"state": order["state"],
                       "ship_blind": order["ship_blind"]})

        with ctx.step("Tick Ship Blind and save."):
            rpc.write("sale.order", [order_id], {"ship_blind": True})
            ctx.check("the blind-ship commitment is recorded on the order",
                      True,
                      rpc.read("sale.order", [order_id],
                               ["ship_blind"])[0]["ship_blind"])

        with ctx.step("Assert the sales order chatter records the change (the "
                      "field is tracking=True)."):
            # dto_sale_stock/models/sale_order.py:10 declares tracking=True;
            # a Boolean is tracked into *_value_integer (O17 addons/mail/models/
            # mail_tracking_value.py:84-88, same shape on v19).
            tracked = rpc.search_read(
                "mail.tracking.value",
                [("mail_message_id.model", "=", "sale.order"),
                 ("mail_message_id.res_id", "=", order_id),
                 ("field_id.name", "=", "ship_blind")],
                ["old_value_integer", "new_value_integer"], order="id")
            ctx.check(
                "the chatter carries a tracking value for ship_blind moving to "
                "True",
                {"tracked": True, "new_value_integer": 1},
                {"tracked": bool(tracked),
                 "new_value_integer": (tracked[-1]["new_value_integer"]
                                       if tracked else None)})

        with ctx.step("Reload both pickings."):
            # Every RPC call commits its own transaction with a fresh cache, so
            # a re-read IS the reload the workbook asks for.
            reloaded = _ship_blind(rpc, [first, second])
            ctx.log(f"re-read ship_blind after the order was ticked: "
                    f"{reloaded}")

        with ctx.step("Assert ship_blind reads True on both, including the one "
                      "already in state done."):
            states = _states(rpc, [first, second])
            ctx.check(
                "the related flag reached the DONE picking as well as the open "
                "one — a stored copy written at picking creation would fail "
                "exactly here (workbook Notes)",
                {"blind": {first: True, second: True},
                 "first_is_done": True},
                {"blind": _ship_blind(rpc, [first, second]),
                 "first_is_done": states[first] == "done"})

        with ctx.step("Assert the field is read-only on the picking form — "
                      "attempt to untick it there and assert the change cannot "
                      "be made."):
            declared = rpc.call("stock.picking", "fields_get", ["ship_blind"],
                                attributes=["type", "store", "related",
                                            "readonly"])["ship_blind"]
            raised, message = expect_error(rpc.write, "stock.picking", [first],
                                           {"ship_blind": False})
            # [UNVERIFIED-3] — the exact server behaviour for a write to a
            # read-only related field is captured on the target, never asserted
            # from source. What IS asserted is the workbook's own expectation:
            # the change did not take.
            ctx.log(f"[UNVERIFIED] write ship_blind=False on the picking: "
                    f"raised={raised} message={message!r}")
            ctx.check(
                "ship_blind is a non-stored, read-only related field and the "
                "downstream untick did not take "
                "(dto_sale_stock/models/stock_picking.py:10)",
                {"type": "boolean", "store": False,
                 "related": "sale_id.ship_blind", "readonly": True,
                 "still_blind": True},
                {"type": declared.get("type"), "store": declared.get("store"),
                 "related": declared.get("related"),
                 "readonly": declared.get("readonly"),
                 "still_blind": _ship_blind(rpc, [first])[first]})

        with ctx.step("Create a third picking from the same order (validate "
                      "the backorder short, forcing a second backorder)."):
            third = _short_ship(ctx, second, 3.0)
            ctx.check("a third outgoing picking of the same order exists",
                      {"outgoing": True, "of_this_order": order_id},
                      {"outgoing": rpc.read("stock.picking", [third],
                                            ["picking_type_code"])[0]
                       ["picking_type_code"] == "outgoing",
                       "of_this_order": m2o_id(
                           rpc.read("stock.picking", [third],
                                    ["sale_id"])[0]["sale_id"])})

        with ctx.step("Assert the new picking is created with ship_blind == "
                      "True — future pickings inherit it too."):
            ctx.check("a picking created after the decision inherits it",
                      True, _ship_blind(rpc, [third])[third])

        with ctx.step("Untick Ship Blind on the sales order and assert all "
                      "three pickings return to False in the same "
                      "transaction."):
            rpc.write("sale.order", [order_id], {"ship_blind": False})
            after = _ship_blind(rpc, [first, second, third])
            ctx.check(
                "the order and all three pickings are un-blind together",
                {"order": False, "pickings": {first: False, second: False,
                                              third: False}},
                {"order": rpc.read("sale.order", [order_id],
                                   ["ship_blind"])[0]["ship_blind"],
                 "pickings": after})
    finally:
        # The workbook's expected final state ("restore ship_blind = True for
        # TC164") is deliberately NOT honoured: hard rules 3 and 5 forbid
        # leaving fixtures behind and TC164 builds its own blind order.
        try:
            sweep_wf011(rpc)
        except Exception:  # noqa: BLE001
            pass


# --------------------------------------------------------------------------
# TEST-WF011-TC163
# --------------------------------------------------------------------------
@test_case(
    id="TEST-WF011-TC163",
    name="One Delivery Slip click prints every non-cancelled outgoing picking "
         "of the order, asserted by section count",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_sale_stock",
    priority="P0", kind="HYBRID", order=11163,
    description="Printing the Delivery Slip from either non-cancelled outgoing "
                "picking of an order — or from both at once — yields exactly "
                "two PACKING SLIP sections carrying both picking names and "
                "never the cancelled one, through the only public entry point "
                "to F044's private _render_qweb_pdf override.",
    traceability=trace("DATAONE-TC163"))
def test_tc163(ctx):
    rpc = ctx.adapter.rpc
    open_namespace(ctx)
    try:
        with ctx.step("Log in as TD-U-03."):
            require_module_build(ctx)
            require_modules(ctx, ["dto_sale_stock"])
            require_sale_stack(ctx)
            require_blind_report(ctx)
            # 'PACKING SLIP' reaches the page only through F048's
            # div[@name='moto'] replacement, declared for the STANDARD layout
            # alone; under any other layout a step-7 failure would be blamed on
            # F044, which would be wrong. This blocks rather than edits the
            # company (hard rule 3).
            layout = require_standard_layout(ctx)
            ctx.log(_role_note("TD-U-03"))
            delivery_action = rpc.read(
                "ir.actions.report", [rpc.ref(ACTION_REPORT_DELIVERY)],
                ["report_name", "report_type", "model", "print_report_name"])[0]
            blind_action = rpc.read(
                "ir.actions.report", [rpc.ref(ACTION_REPORT_SHIP_BLIND)],
                ["report_name", "report_type", "model"])[0]
            # The v19 silent-failure detector: F044 keys on two LITERAL
            # strings (dto_sale_stock/models/ir_actions_report.py:14). Rename
            # either report and the branch never fires, with no error anywhere.
            ctx.check(
                "both printable reports still carry the literal report_name "
                "F044's override keys on",
                {"delivery": REPORT_DELIVERY_SLIP, "blind": REPORT_SHIP_BLIND,
                 "delivery_model": "stock.picking",
                 "delivery_type": "qweb-pdf",
                 "delivery_print_report_name": DELIVERY_PRINT_REPORT_NAME},
                {"delivery": delivery_action["report_name"],
                 "blind": blind_action["report_name"],
                 "delivery_model": delivery_action["model"],
                 "delivery_type": delivery_action["report_type"],
                 "delivery_print_report_name":
                     delivery_action["print_report_name"]})

            order_id = make_sale_order(ctx, label="TC163 Order", qty=12.0,
                                       memo=tag("Memo for TC163"))
            confirm_order(ctx, order_id)
            pickings = outgoing_pickings(rpc, order_id)
            ctx.check("the confirmed order produced one outgoing picking",
                      1, len(pickings))
            first = pickings[0]["id"]
            second = _short_ship(ctx, first, 5.0)
            third = _short_ship(ctx, second, 4.0)
            rpc.call("stock.picking", "action_cancel", [third])
            names = {row["id"]: row["name"] for row in
                     rpc.read("stock.picking", [first, second, third],
                              ["name"])}
            ctx.log(f"layout={layout!r} pickings={names} (third cancelled)")
            # Deliberately no boxes and no shipping labels on these pickings:
            # wkhtmltopdf repeats the page header on every page, so a picking
            # that spills onto a second page would contribute a spurious
            # PACKING SLIP occurrence (plan [UNVERIFIED-8]). See adaptation 2.

        with ctx.step("Record expected_ids = order.picking_ids.filtered(lambda "
                      "p: p.picking_type_code == 'outgoing' and p.state != "
                      "'cancel').ids and assert len(expected_ids) == 2."):
            rows = outgoing_pickings(rpc, order_id)
            expected_ids = [r["id"] for r in rows if r["state"] != "cancel"]
            cancelled_ids = [r["id"] for r in rows if r["state"] == "cancel"]
            ctx.check(
                "F044's own filter, reproduced over RPC, selects exactly the "
                "two non-cancelled outgoing pickings",
                {"expected_ids": [first, second],
                 "cancelled_ids": [third]},
                {"expected_ids": expected_ids,
                 "cancelled_ids": cancelled_ids})

        with ctx.step("Open one of the two non-cancelled pickings."):
            ctx.check(
                "the first print is launched from a non-cancelled outgoing "
                "picking that has at least one move line",
                {"state_not_cancel": True, "outgoing": True,
                 "has_move_lines": True},
                {"state_not_cancel":
                     _states(rpc, [first])[first] != "cancel",
                 "outgoing": rpc.read("stock.picking", [first],
                                      ["picking_type_code"])[0]
                 ["picking_type_code"] == "outgoing",
                 "has_move_lines": bool(rpc.search(
                     "stock.move.line", [("picking_id", "=", first)]))})

        with ctx.step("Press Print → Delivery Slip."):
            # GET /report/pdf/ is the ONLY public entry point to the private
            # _render_qweb_pdf F044 overrides; /report/html/ is never
            # substituted here because it bypasses the override under test.
            pdf_first = report_pdf(ctx, REPORT_DELIVERY_SLIP, [first])

        with ctx.step("Capture the produced PDF."):
            # DIAGNOSTIC: render the SAME report as HTML and save it too.
            # The PDF's header is a separate wkhtmltopdf sub-document, so
            # "PACKING SLIP is absent from the PDF text" cannot by itself
            # say whether the heading was never rendered or was rendered
            # into a header the extractor does not read. The HTML carries
            # the header inline and settles it.
            try:
                _html = report_html(ctx, REPORT_DELIVERY_SLIP, [first])
                save_report_artifact(ctx, "TC163-delivery-slip-html",
                                     _html.encode("utf-8"), ".html")
                ctx.log(f"HTML render: {len(_html)} chars, "
                        f"'PACKING SLIP' x{_html.count('PACKING SLIP')}, "
                        f"o_company_tagline x{_html.count('o_company_tagline')}")
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[note] HTML diagnostic render failed: {exc}")
            path = save_report_artifact(ctx, "TC163-delivery-slip-from-first",
                                        pdf_first, ".pdf")
            ctx.check("the print route returned a PDF",
                      True, pdf_first.startswith(b"%PDF"))
            ctx.log(f"stored {path}")

        with ctx.step("Extract the text of the PDF."):
            text_first, pages_first = _pdf_signal(
                ctx, pdf_first, "Delivery Slip printed from the first picking")

        with ctx.step("Prove the extractor can read the PDF's HEADER before "
                      "asserting about a string that only lives there."):
            # pdf_text()'s own docstring says wkhtmltopdf subsets fonts and
            # may emit glyph indices instead of ASCII, "in which case this
            # returns None and the caller must report BLOCKED naming the
            # missing extractor — it must never silently assert against an
            # empty string." Its guard checks the WHOLE document for a
            # three-letter run, so a readable BODY masks an unreadable
            # HEADER, and PACKING SLIP lives only in the header.
            #
            # Measured on this build: the HTML render of the same report and
            # the same picking carries 'PACKING SLIP' once, inside
            # <div class="o_company_tagline ..." name="moto">, so the
            # heading IS produced. The PDF text came back with 53,221
            # characters of body and none of the header.
            #
            # A control string that is in the header too settles which it
            # is, instead of reporting a rendering failure that did not
            # happen.
            _cid = m2o_id(rpc.read("res.users", [rpc.uid],
                                   ["company_id"])[0]["company_id"])
            company_name = rpc.read("res.company", [_cid],
                                    ["name"])[0]["name"]
            if company_name and company_name not in (text_first or ""):
                ctx.blocked(
                    "The PDF text extractor cannot read this document's "
                    f"HEADER: the company name {company_name!r} is rendered "
                    "there on every page and does not appear in the "
                    f"{len(text_first or '')} characters it returned. "
                    "PACKING SLIP lives only in the header, so asserting "
                    "its count here would report a rendering failure that "
                    "did not happen — the HTML render of the same report "
                    "carries it. pdf_text() inflates FlateDecode streams "
                    "and collects parenthesised literals with the standard "
                    "library only; wkhtmltopdf's subset fonts defeat that. "
                    "Install a real extractor (pypdf or pdfminer.six) in "
                    "the qa-platform venv to make this case answerable.")

        with ctx.step("Assert the string PACKING SLIP occurs exactly 2 times — "
                      "one per non-cancelled outgoing picking. This is the "
                      "assertion; \"a PDF was produced\" is not."):
            ctx.check(
                "PACKING SLIP occurs once per non-cancelled outgoing picking "
                "of the order",
                2, _pdf_count(text_first, PACKING_SLIP_TITLE))

        with ctx.step("Assert each of the two pickings' names appears exactly "
                      "once in the extracted text."):
            ctx.check(
                "both picking names are printed, each exactly once",
                {names[first]: 1, names[second]: 1},
                {names[first]: _pdf_count(text_first, names[first]),
                 names[second]: _pdf_count(text_first, names[second])})

        with ctx.step("Assert the cancelled picking's name does not appear "
                      "anywhere in the text."):
            ctx.check("the cancelled picking is excluded by F044's own filter",
                      0, _pdf_count(text_first, names[third]))

        with ctx.step("Repeat from the *other* non-cancelled picking and "
                      "assert the same two-section output — the expansion is "
                      "order-driven, not selection-driven."):
            pdf_second = report_pdf(ctx, REPORT_DELIVERY_SLIP, [second])
            save_report_artifact(ctx, "TC163-delivery-slip-from-second",
                                 pdf_second, ".pdf")
            text_second, pages_second = _pdf_signal(
                ctx, pdf_second,
                "Delivery Slip printed from the second picking")
            ctx.check(
                "printing from the other picking yields the same two sections "
                "and the same two names, still without the cancelled one",
                {"sections": 2, names[first]: 1, names[second]: 1,
                 "cancelled": 0},
                {"sections": _pdf_count(text_second, PACKING_SLIP_TITLE),
                 names[first]: _pdf_count(text_second, names[first]),
                 names[second]: _pdf_count(text_second, names[second]),
                 "cancelled": _pdf_count(text_second, names[third])})

        with ctx.step("Select both non-cancelled pickings in the list view and "
                      "print; assert the section count is still 2 and no "
                      "picking is duplicated."):
            # Guards the opposite failure: an expansion that also duplicates
            # already-selected pickings. It cannot, because the override uses
            # |= (ir_actions_report.py:17) — asserted rather than assumed.
            pdf_both = report_pdf(ctx, REPORT_DELIVERY_SLIP,
                                  [first, second])
            save_report_artifact(ctx, "TC163-delivery-slip-from-both",
                                 pdf_both, ".pdf")
            text_both, pages_both = _pdf_signal(
                ctx, pdf_both, "Delivery Slip printed from both pickings")
            ctx.check(
                "selecting both pickings still produces exactly two sections, "
                "each picking printed once",
                {"sections": 2, names[first]: 1, names[second]: 1,
                 "cancelled": 0},
                {"sections": _pdf_count(text_both, PACKING_SLIP_TITLE),
                 names[first]: _pdf_count(text_both, names[first]),
                 names[second]: _pdf_count(text_both, names[second]),
                 "cancelled": _pdf_count(text_both, names[third])})

        with ctx.step("Record the section count, the picking names and the "
                      "page count as the v17 baseline artefact for this case."):
            baseline = "\n".join([
                f"environment      : {ctx.env.key} (db={ctx.env.db}, "
                f"Odoo {ctx.env.version})",
                f"company layout   : {layout}",
                f"report           : {REPORT_DELIVERY_SLIP}",
                f"order            : {order_id}",
                f"pickings         : first={names[first]} "
                f"second={names[second]} cancelled={names[third]}",
                f"sections (first) : "
                f"{_pdf_count(text_first, PACKING_SLIP_TITLE)}",
                f"sections (second): "
                f"{_pdf_count(text_second, PACKING_SLIP_TITLE)}",
                f"sections (both)  : "
                f"{_pdf_count(text_both, PACKING_SLIP_TITLE)}",
                f"pages            : first={pages_first} "
                f"second={pages_second} both={pages_both}",
                "",
                "--- extracted text, print from the first picking ---",
                text_first or "",
            ])
            stored = save_report_artifact(ctx, "TC163-v17-baseline",
                                          baseline.encode("utf-8"), ".txt")
            ctx.check(
                "the baseline artefact records the section count, both picking "
                "names and the page count",
                {"written": True, "sections_agree": True},
                {"written": stored.exists(),
                 "sections_agree":
                     _pdf_count(text_first, PACKING_SLIP_TITLE)
                     == _pdf_count(text_second, PACKING_SLIP_TITLE)
                     == _pdf_count(text_both, PACKING_SLIP_TITLE)})
    finally:
        try:
            sweep_wf011(rpc)
        except Exception:  # noqa: BLE001
            pass


# --------------------------------------------------------------------------
# TEST-WF011-TC164
# --------------------------------------------------------------------------
@test_case(
    id="TEST-WF011-TC164",
    name="The Blind Packing Slip carries no header, no footer, no customer "
         "block and no SO reference",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_sale_stock",
    priority="P0", kind="HYBRID", order=11164,
    description="The blind slip's suppression mechanism asserted where it is "
                "observable: report_header_style / report_footer_style set to "
                "display:none and actually rendered onto the layout's header "
                "and footer divs, class=d-none on the three customer blocks "
                "and the product reference, the restricted contact widget, the "
                "<h2> that must survive, and the mandatory Delivery Slip "
                "control — then BLOCKED on the PDF-only negatives.",
    traceability=trace("DATAONE-TC164"))
def test_tc164(ctx):
    rpc = ctx.adapter.rpc
    open_namespace(ctx)
    try:
        with ctx.step("Log in as TD-U-03 and open a non-cancelled outgoing "
                      "picking of the blind order."):
            require_module_build(ctx)
            require_modules(ctx, ["dto_sale_stock"])
            require_sale_stack(ctx)
            require_ship_blind(ctx)
            require_blind_report(ctx)
            ctx.log(_role_note("TD-U-03"))
            # Workbook precondition: "The active report layout is recorded".
            # It is never changed — that would modify a pre-existing business
            # record (hard rule 3).
            layout = company_layout_xmlid(ctx)
            company_id = m2o_id(rpc.read("res.users", [rpc.uid],
                                         ["company_id"])[0]["company_id"])
            company = rpc.read("res.company", [company_id],
                               ["name", "street", "city", "zip", "phone",
                                "vat"])[0]
            ctx.log(f"company external_report_layout_id = {layout!r}; F048 "
                    f"patches {LAYOUTS_PATCHED_BY_F048} and does NOT patch "
                    f"v19's {LAYOUTS_NEW_IN_V19}")
            ctx.log(f"printing company (read-only): "
                    f"name={company['name']!r} street={company['street']!r} "
                    f"city={company['city']!r} zip={company['zip']!r} "
                    f"phone={company['phone']!r} vat={company['vat']!r}")

            order_id = make_sale_order(ctx, label="TC164 Blind Order",
                                       qty=6.0, ship_blind=True,
                                       memo=tag("Memo for TC164"))
            confirm_order(ctx, order_id)
            pickings = outgoing_pickings(rpc, order_id)
            ctx.check("the order produced one outgoing picking", 1,
                      len(pickings))
            picking_id = pickings[0]["id"]
            picking = rpc.read("stock.picking", [picking_id],
                               ["name", "state", "origin", "partner_id",
                                "ship_blind"])[0]
            order_name = rpc.read("sale.order", [order_id],
                                  ["name"])[0]["name"]
            partner_name = (rpc.read(
                "res.partner", [m2o_id(picking["partner_id"])],
                ["name"])[0]["name"] if m2o_id(picking["partner_id"]) else "")
            ctx.check(
                "the fixture is a non-cancelled outgoing picking of a blind "
                "order, still un-validated so the patched (not-done) move "
                "table is the one that renders",
                {"ship_blind": True, "not_cancelled": True, "not_done": True,
                 "origin": order_name},
                {"ship_blind": picking["ship_blind"],
                 "not_cancelled": picking["state"] != "cancel",
                 "not_done": picking["state"] != "done",
                 "origin": picking["origin"]})
            blind_arch = _combined_arch(
                ctx, "dto_sale_stock.report_ship_blind_document")

        with ctx.step("Press Print → Blind Packing Slip."):
            blind_html = report_html(ctx, REPORT_SHIP_BLIND, [picking_id])
            header_attrs, header_block = _div_blocks(blind_html, "header")
            footer_attrs, footer_block = _div_blocks(blind_html, "footer")
            ctx.check(
                "the Blind Packing Slip rendered for this picking, with the "
                "layout's header and footer divs both present in the document",
                {"rendered": True, "picking_name_present": True,
                 "header_div": True, "footer_div": True},
                {"rendered": bool(blind_html),
                 "picking_name_present":
                     picking["name"] in html_text(blind_html),
                 "header_div": bool(header_block),
                 "footer_div": bool(footer_block)})

        with ctx.step("Assert the produced file is named Blind Packing Slip - "
                      "<Customer> - <Picking>."):
            # print_report_name is safe_eval-ed by the download controller,
            # which this transport does not exercise; the stored expression is
            # asserted byte-exact and the value it yields is logged
            # (adaptation 6).
            action = rpc.read(
                "ir.actions.report", [rpc.ref(ACTION_REPORT_SHIP_BLIND)],
                ["name", "report_name", "report_type", "model",
                 "print_report_name"])[0]
            ctx.log(f"print_report_name yields "
                    f"{BLIND_REPORT_TITLE} - {partner_name} - "
                    f"{picking['name']}")
            ctx.check(
                "the report action builds the download name as 'Blind Packing "
                "Slip - <Customer> - <Picking>' "
                "(dto_sale_stock/report/stock_report_views.xml:3-12)",
                {"name": BLIND_REPORT_TITLE,
                 "report_name": REPORT_SHIP_BLIND,
                 "report_type": "qweb-pdf", "model": "stock.picking",
                 "print_report_name": BLIND_PRINT_REPORT_NAME},
                {"name": action["name"], "report_name": action["report_name"],
                 "report_type": action["report_type"],
                 "model": action["model"],
                 "print_report_name": action["print_report_name"]})

        with ctx.step("Extract the full text of the PDF."):
            save_report_artifact(ctx, "TC164-blind-packing-slip",
                                 blind_html.encode("utf-8"), ".html")
            outside = _text_outside(blind_html, [header_block, footer_block])
            ctx.log(f"blind slip: {len(blind_html)} characters of HTML, "
                    f"{len(outside)} characters of text outside the suppressed "
                    f"header and footer")
            ctx.check(
                "there is a rendered body to make negative assertions against "
                "at all",
                True, bool(outside))

        with ctx.step("Assert the company name does not occur anywhere in the "
                      "text."):
            ctx.check(
                "the company header is suppressed at source — the blind "
                "template sets report_header_style and the layout's header div "
                "renders it (report_ship_blind.xml:6; v17 web/views/"
                "report_templates.xml:492, v19 keeps the hook on "
                "external_layout_bold ONLY at :439) — and the company name "
                "does not reach the page outside it",
                {"template_sets_header_style": f"'{BLIND_STYLE}'",
                 "rendered_header_style": BLIND_STYLE,
                 "company_name_outside_header": 0},
                {"template_sets_header_style":
                     _t_set_value(blind_arch, "report_header_style"),
                 "rendered_header_style": header_attrs.get("style"),
                 "company_name_outside_header":
                     outside.count(company["name"]) if company["name"] else 0})

        with ctx.step("Assert the company's street, city, postcode and phone "
                      "number (from TD-PA-05) do not occur anywhere in the "
                      "text."):
            # The company address block lives inside the suppressed header
            # (v17 web/views/report_templates.xml:504-527). Its literal
            # absence from the page is a PDF-only fact — in HTML it is still in
            # the DOM under display:none — and a token-by-token text negative
            # would be unsound anyway: the blind slip deliberately PRINTS a
            # ship-to address through the restricted contact widget, so a
            # company address token the customer shares cannot be
            # distinguished. What is asserted is containment.
            ctx.check(
                "the company address block is inside the suppressed header div",
                {"company_address_block": True, "inside_suppressed_header":
                     True},
                {"company_address_block":
                     'name="company_address"' in blind_html,
                 "inside_suppressed_header":
                     'name="company_address"' in header_block})

        with ctx.step("Assert the company VAT/registration string does not "
                      "occur."):
            vat = company["vat"] or ""
            ctx.log(f"company vat = {vat!r} — an empty value makes this "
                    f"negative vacuous on this target, which is recorded "
                    f"rather than silently passed")
            ctx.check(
                "the company's VAT/registration string does not reach the page "
                "outside the suppressed header and footer",
                0, outside.count(vat) if vat else 0)

        with ctx.step("Assert the sale order name (the origin / SO reference) "
                      "does not occur — the div_origin block is suppressed."):
            origin_rendered = None
            for tag_text in _DIV_OPEN_RE.findall(blind_html):
                attrs = dict(_ATTR_RE.findall(tag_text))
                if attrs.get("name") == "div_origin":
                    origin_rendered = attrs.get("class")
                    break
            ctx.log(f"the SO reference {order_name!r} is still in the DOM "
                    f"under d-none — its literal absence is a PDF-only fact "
                    f"and is named in the BLOCKED reason below")
            ctx.check(
                "div_origin carries class=\"d-none\" both in the template and "
                "in the render (report_ship_blind.xml:29-31 over "
                "stock/report/report_deliveryslip.xml:50)",
                {"in_template": "d-none", "in_render": "d-none"},
                {"in_template": _named_div_class(blind_arch, "div_origin"),
                 "in_render": origin_rendered})

        with ctx.step("Assert the customer address block is absent: the "
                      "customer's street and postcode do not occur. (The "
                      "ship-to address renders through the restricted contact "
                      "widget and is expected; assert the *billing/customer* "
                      "block specifically, per the fixture's distinct billing "
                      "address.)"):
            # customer_address and partner_header are gated by core on
            # partner != partner.commercial_partner_id (stock/report/
            # report_deliveryslip.xml:33-37), so for a standalone fixture
            # customer neither block is emitted and a render-side assertion
            # would be vacuous. They are asserted on the combined arch, which
            # is the template QWeb compiles (adaptation 5).
            widget = blind_arch.find(
                ".//div[@name='outgoing_delivery_address']/div")
            hidden = {name: _named_div_class(blind_arch, name)
                      for name in BLIND_HIDDEN_BLOCKS}
            expected_hidden = {name: "d-none" for name in BLIND_HIDDEN_BLOCKS}
            ctx.check(
                "all three identifying blocks are class=\"d-none\" in the "
                "blind template, and the ship-to widget is restricted to the "
                "address alone (report_ship_blind.xml:14-31)",
                dict(expected_hidden, contact_widget=BLIND_CONTACT_OPTIONS),
                dict(hidden,
                     contact_widget=(widget.get("t-options")
                                     if widget is not None else None)))

        with ctx.step("Assert the page footer is absent: the footer's "
                      "page-number pattern and any company tagline do not "
                      "occur."):
            # This half fails LOUDLY if F048's footer patch stops applying:
            # the style variable is set by the blind template but the four
            # footer divs are patched by dto_sale_stock itself
            # (report_templates.xml:12-33), not by core.
            ctx.check(
                "report_footer_style is set to display:none and F048's footer "
                "patch actually renders it onto the layout's footer div",
                {"template_sets_footer_style": f"'{BLIND_STYLE}'",
                 "rendered_footer_style": BLIND_STYLE},
                {"template_sets_footer_style":
                     _t_set_value(blind_arch, "report_footer_style"),
                 "rendered_footer_style": footer_attrs.get("style")})

        with ctx.step("Assert PACKING SLIP does occur as the <h2> heading — "
                      "the document must still be usable."):
            headings = [html_text(node)
                        for node in html_elements(blind_html, "h2")]
            ctx.check(
                "the blind slip still prints its <h2>PACKING SLIP</h2> "
                "(report_ship_blind.xml:10-12)",
                {"h2_present": True, "template_h2": True},
                {"h2_present": PACKING_SLIP_TITLE in headings,
                 "template_h2": any(
                     (node.text or "").strip() == PACKING_SLIP_TITLE
                     for node in blind_arch.findall(".//h2"))})

        with ctx.step("Assert product internal references (default_code) do "
                      "not occur; line items show move.product_id.name only."):
            product_span = blind_arch.find(
                ".//span[@t-field='move.product_id']")
            name_span = blind_arch.find(
                ".//span[@t-field='move.product_id.name']")
            ctx.log(
                "recorded, not asserted as a text negative: the reference is "
                "still in the DOM under d-none, and for a DONE picking the "
                "patch does not apply at all — the aggregated move-line table "
                "prints product_id.display_name (stock/report/"
                "report_deliveryslip.xml:95-163), which carries "
                "[default_code]. The fixture is deliberately left un-validated "
                "so the patched not-done table is the one under test.")
            ctx.check(
                "the blind template hides the product reference and prints the "
                "product NAME beside it (report_ship_blind.xml:34-39 over "
                "stock/report/report_deliveryslip.xml:73)",
                {"reference_class": "d-none", "name_span_added": True},
                {"reference_class": (product_span.get("class")
                                     if product_span is not None else None),
                 "name_span_added": name_span is not None})

        with ctx.step("Print the ordinary Delivery Slip from the same picking "
                      "and assert the company name, the footer and the SO "
                      "reference do occur — the control that proves steps 5-10 "
                      "are not passing because the report failed to render "
                      "content at all."):
            # Step 13 is MANDATORY: without it a report that renders an empty
            # page passes every negative above.
            control_html = report_html(ctx, REPORT_DELIVERY_SLIP,
                                       [picking_id])
            save_report_artifact(ctx, "TC164-delivery-slip-control",
                                 control_html.encode("utf-8"), ".html")
            control_header, _ = _div_blocks(control_html, "header")
            control_footer, _ = _div_blocks(control_html, "footer")
            control_text = html_text(control_html)
            ctx.check(
                "the ordinary Delivery Slip prints the company name and the SO "
                "reference, with neither header nor footer suppressed — so the "
                "negatives above are meaningful",
                {"company_name": True, "so_reference": True,
                 "header_suppressed": False, "footer_suppressed": False},
                {"company_name": bool(company["name"])
                                 and company["name"] in control_text,
                 "so_reference": order_name in control_text,
                 "header_suppressed":
                     control_header.get("style") == BLIND_STYLE,
                 "footer_suppressed":
                     control_footer.get("style") == BLIND_STYLE})

        with ctx.step("Store the extracted text of both documents as the v17 "
                      "baseline pair."):
            baseline = "\n".join([
                f"environment   : {ctx.env.key} (db={ctx.env.db}, Odoo "
                f"{ctx.env.version})",
                f"company layout: {layout}",
                f"company       : {company}",
                f"order         : {order_name}",
                f"picking       : {picking['name']}",
                "",
                "--- Blind Packing Slip, visible text outside the suppressed "
                "header and footer ---",
                outside,
                "",
                "--- Delivery Slip (control), visible text ---",
                control_text,
            ])
            stored = save_report_artifact(ctx, "TC164-v17-baseline-pair",
                                          baseline.encode("utf-8"), ".txt")
            ctx.check("both documents' text is stored as the baseline pair",
                      True, stored.exists())

        # The structural half is complete and both named failure paths are
        # covered. Every literal string-absence check the workbook writes is
        # true only of the rendered PDF, so the case closes BLOCKED rather
        # than claiming a negative it cannot observe.
        ctx.blocked(BLOCKED_PDF_EXTRACTOR)
    finally:
        try:
            sweep_wf011(rpc)
        except Exception:  # noqa: BLE001
            pass


# --------------------------------------------------------------------------
# TEST-WF011-TC165
# --------------------------------------------------------------------------
@test_case(
    id="TEST-WF011-TC165",
    name="The packing slip carries the shipping/tracking/pieces/weight table "
         "and the boxes grid",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_sale_stock, dto_stock",
    priority="P1", kind="HYBRID", order=11165,
    description="One rendered Delivery Slip carries the four-column "
                "shipping-label table with one row per label and the picking's "
                "shipping weight on every row, a 12-wide boxes grid that wraps "
                "13 boxes onto a second padded row with name and lb weight in "
                "each cell, and the picking note and the order's memo to "
                "suppliers.",
    traceability=trace("DATAONE-TC165"))
def test_tc165(ctx):
    rpc = ctx.adapter.rpc
    open_namespace(ctx)
    labels_present = False
    try:
        with ctx.step("Log in as TD-U-03 and open the picking."):
            require_module_build(ctx)
            require_modules(ctx, ["dto_stock", "dto_sale_stock"])
            require_sale_stack(ctx)
            require_boxes(ctx)
            ctx.log(_role_note("TD-U-03"))
            ctx.log(f"company external_report_layout_id = "
                    f"{company_layout_xmlid(ctx)!r} (recorded; this case "
                    f"asserts page-body content, which no layout affects)")
            memo = tag("Memo to suppliers for TC165")
            order_id = make_sale_order(ctx, label="TC165 Order", qty=8.0,
                                       memo=memo)
            confirm_order(ctx, order_id)
            pickings = outgoing_pickings(rpc, order_id)
            ctx.check("the order produced one outgoing picking", 1,
                      len(pickings))
            picking_id = pickings[0]["id"]

            note = tag("Handle with care - fragile")
            rpc.write("stock.picking", [picking_id],
                      {"shipping_weight": TC165_SHIPPING_WEIGHT,
                       "note": note})
            create_boxes(ctx, picking_id, TC165_BOXES, TC165_BOX_WEIGHT)

            labels_present = (rpc.field_exists("stock.picking",
                                               SHIPPING_LABEL_FIELD)
                              and rpc.model_exists(SHIPPING_LABEL_MODEL)
                              and rpc.field_exists(SHIPPING_LABEL_MODEL,
                                                   "pieces"))
            if labels_present:
                carrier_a = ensure_carrier(ctx, "Carrier Ground")
                carrier_b = ensure_carrier(ctx, "Carrier Air")
                make_shipping_label(ctx, picking_id, carrier_a,
                                    TRACKING_TC165_A, TC165_PIECES_A)
                make_shipping_label(ctx, picking_id, carrier_b,
                                    TRACKING_TC165_B, TC165_PIECES_B)
            else:
                ctx.log("stock.picking.shipping_label_ids / shipping.label are "
                        "not contributed on this target — steps 5-8 have "
                        "nothing to render and the case closes BLOCKED with "
                        "the PrintNode reason after the boxes, note and memo "
                        "half has run in full (plan adaptation 8).")

        with ctx.step("Confirm the fixture: len(picking.box_ids) == 13, "
                      "len(picking.shipping_label_ids) == 2, "
                      "picking.shipping_weight == 15.2, picking.note "
                      "non-empty, picking.sale_id.memo_to_suppliers "
                      "non-empty."):
            row = rpc.read("stock.picking", [picking_id],
                           ["shipping_weight", "note", "sale_id"])[0]
            stored_memo = rpc.read("sale.order", [order_id],
                                   ["memo_to_suppliers"])[0]["memo_to_suppliers"]
            boxes = boxes_of(rpc, picking_id)
            labels = shipping_labels_of(rpc, picking_id) if labels_present \
                else "FIELD ABSENT"
            ctx.check(
                "the fixture carries 13 boxes, two shipping labels, an "
                "operator-entered shipping weight, a note and a memo",
                {"boxes": TC165_BOXES,
                 "labels": 2 if labels_present else "FIELD ABSENT",
                 "shipping_weight": TC165_SHIPPING_WEIGHT,
                 "note_set": True, "memo_set": True},
                {"boxes": len(boxes),
                 "labels": len(labels) if labels_present else labels,
                 "shipping_weight": row["shipping_weight"],
                 "note_set": bool(row["note"]),
                 "memo_set": bool(stored_memo)})

        with ctx.step("Press Print → Delivery Slip."):
            # The HTML route is correct here: this case asserts ONE picking's
            # content, not F044's expansion, so the override not firing on
            # /report/html/ is irrelevant (adaptation 10).
            html = report_html(ctx, REPORT_DELIVERY_SLIP, [picking_id])

        with ctx.step("Extract the rendered text/HTML."):
            save_report_artifact(ctx, "TC165-delivery-slip",
                                 html.encode("utf-8"), ".html")
            text = html_text(html)
            ctx.check("the Delivery Slip rendered for this picking",
                      True,
                      bool(html) and rpc.read("stock.picking", [picking_id],
                                              ["name"])[0]["name"] in text)

        table = html_element(html, "table", "name", SHIPPING_TABLE_NAME) \
            if labels_present else None
        ordered_labels = []
        if labels_present:
            # shipping.label._order is 'create_date desc'
            # (printnode_base/models/shipping_label.py:14), so the one2many
            # renders newest-first. Rows are matched against the O2M read back
            # in that same order (adaptation 9).
            ordered_ids = rpc.read("stock.picking", [picking_id],
                                   [SHIPPING_LABEL_FIELD])[0][
                                       SHIPPING_LABEL_FIELD]
            ordered_labels = rpc.read(SHIPPING_LABEL_MODEL, ordered_ids,
                                      ["carrier_id", "tracking_numbers",
                                       "pieces"])

        with ctx.step("Assert a table with the column headings Shipping "
                      "Method, Tracking-Pro Number, Pieces and Weight is "
                      "present."):
            if labels_present:
                headers = [html_text(cell)
                           for cell in html_elements(table or "", "th")]
                # SOURCE strings: report_delivery_document.xml:13-16 says
                # "Tracking/Pro Number" with a SLASH where the workbook prose
                # writes a hyphen. The source is what is asserted.
                ctx.check(
                    "the shipping-label table is present with its four source "
                    "column headings",
                    {"table": True, "headers": SHIPPING_TABLE_HEADERS},
                    {"table": bool(table), "headers": headers})
            else:
                ctx.log("skipped: shipping_label_ids does not exist, so the "
                        "t-if=\"o.shipping_label_ids\" table cannot render.")

        data_rows = []
        with ctx.step("Assert that table has exactly 2 data rows — one per "
                      "shipping_label_ids entry."):
            if labels_present:
                body = html_element(table or "", "tbody") or ""
                data_rows = html_elements(body, "tr")
                ctx.check("one data row per shipping_label_ids entry",
                          len(ordered_labels), len(data_rows))
                ctx.check("and that is the workbook's two rows", 2,
                          len(data_rows))
            else:
                ctx.log("skipped: no shipping-label table to count rows in.")

        with ctx.step("Assert row 1 shows the first label's carrier_id.name, "
                      "its tracking_numbers, Pieces = 5 and Weight = 15.2."):
            if labels_present and len(data_rows) >= 1 and ordered_labels:
                cells = _cell_texts(data_rows[0])
                label = ordered_labels[0]
                ctx.check(
                    "row 1 prints its own label's carrier, tracking number, "
                    "piece count and the picking's shipping weight",
                    {"carrier": _carrier_name(rpc, label),
                     "tracking": label["tracking_numbers"],
                     "pieces": label["pieces"],
                     "weight": TC165_SHIPPING_WEIGHT},
                    {"carrier": _cell(cells, 0),
                     "tracking": _cell(cells, 1),
                     "pieces": _as_float(_cell(cells, 2)),
                     "weight": _as_float(_cell(cells, 3))})
            else:
                ctx.log("skipped: no shipping-label rows rendered.")

        with ctx.step("Assert row 2 shows the second label's carrier_id.name, "
                      "its tracking_numbers, Pieces = 2 and Weight = 15.2 — "
                      "the weight column reads o.shipping_weight, the same "
                      "value on every row."):
            if labels_present and len(data_rows) >= 2 and len(ordered_labels) > 1:
                cells = _cell_texts(data_rows[1])
                label = ordered_labels[1]
                first_cells = _cell_texts(data_rows[0])
                # key=str on both sides so a row that rendered an unparseable
                # cell reports a mismatch instead of raising on a mixed sort.
                ctx.check(
                    "row 2 prints its own label's carrier, tracking number and "
                    "piece count, both rows carry the SAME shipping weight, "
                    "and the two piece counts are the workbook's 5 and 2",
                    {"carrier": _carrier_name(rpc, label),
                     "tracking": label["tracking_numbers"],
                     "pieces": label["pieces"],
                     "weight": TC165_SHIPPING_WEIGHT,
                     "weight_on_row_1": TC165_SHIPPING_WEIGHT,
                     "piece_counts": sorted([TC165_PIECES_A, TC165_PIECES_B],
                                            key=str)},
                    {"carrier": _cell(cells, 0),
                     "tracking": _cell(cells, 1),
                     "pieces": _as_float(_cell(cells, 2)),
                     "weight": _as_float(_cell(cells, 3)),
                     "weight_on_row_1": _as_float(_cell(first_cells, 3)),
                     "piece_counts": sorted(
                         (_as_float(_cell(_cell_texts(r), 2))
                          for r in data_rows), key=str)})
            else:
                ctx.log("skipped: fewer than two shipping-label rows rendered.")

        grid = _boxes_grid(html)
        grid_cells = html_elements(grid, "td") if grid else []
        populated = [cell for cell in grid_cells if "<div" in cell]

        with ctx.step("Assert a Boxes grid is present containing exactly 13 "
                      "cells."):
            # POPULATED cells: the template pads the short row with empty
            # <td>s (report_delivery_document.xml:46), so 13 boxes give 13
            # populated + 11 padding = 24 <td> (adaptation 8).
            ctx.check(
                "the boxes grid is present with exactly one populated cell per "
                "box",
                {"grid": True, "populated_cells": TC165_BOXES},
                {"grid": bool(grid), "populated_cells": len(populated)})

        with ctx.step("Assert each cell shows the box name and its weight "
                      "suffixed lb."):
            expected = [f"{name} {TC165_BOX_WEIGHT} lb"
                        for name in expected_box_names(TC165_BOXES)]
            ctx.check(
                "every cell prints 'Box N <weight> lb' in the manifest's own "
                "sequence order (stock_picking_box.py:11, "
                "report_delivery_document.xml:43-44)",
                expected, [html_text(cell) for cell in populated])

        with ctx.step("Assert the grid is laid out 12 columns wide, so the "
                      "13th box wraps onto a second row."):
            rows_html = html_elements(grid, "tr") if grid else []
            ctx.check(
                "13 boxes chunk into two rows of 12, the second padded to full "
                "width with empty cells "
                "(report_delivery_document.xml:38 and :46)",
                {"rows": 2, "cells_in_row_1": BOXES_PER_ROW,
                 "cells_in_row_2": BOXES_PER_ROW,
                 "total_cells": 2 * BOXES_PER_ROW,
                 "padding_cells": 2 * BOXES_PER_ROW - TC165_BOXES},
                {"rows": len(rows_html),
                 "cells_in_row_1": (count_tags(rows_html[0], "td")
                                    if len(rows_html) > 0 else None),
                 "cells_in_row_2": (count_tags(rows_html[1], "td")
                                    if len(rows_html) > 1 else None),
                 "total_cells": len(grid_cells),
                 "padding_cells": len(grid_cells) - len(populated)})

        with ctx.step("Assert the picking note text appears on the slip."):
            ctx.check(
                "the picking note reaches the printed document "
                "(report_delivery_document.xml:51-53)",
                True, note in text)

        with ctx.step("Assert sale_id.memo_to_suppliers appears on the slip."):
            ctx.check(
                "the order's memo to suppliers reaches the printed document "
                "(report_delivery_document.xml:54-56)",
                True, memo in text)

        if not labels_present:
            # The boxes / note / memo half ran in full; the shipping-label half
            # has no v19 future at all (decision D-1), so the case reports
            # BLOCKED rather than FAILED.
            ctx.blocked(BLOCKED_PRINTNODE +
                        " (the shipping-label half of this case, steps 5-8, "
                        "has nothing to render; the boxes, note and memo half "
                        "was asserted in full above)")
    finally:
        try:
            sweep_wf011(rpc)
        except Exception:  # noqa: BLE001
            pass
