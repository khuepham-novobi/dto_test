"""DATAONE-WF-015 — the packing slip: capture, refusal, merged print.

TC207, TC208, TC209, TC210, TC211 — the five workbook cases covering
``DATAONE-F069`` (packing-slip attachment with mimetype validation) and
``DATAONE-F070`` (merged packing-slip print / send to PrintNode).

Abbreviations used in the citations below: ``DPS`` =
``D:/Projects/dataone/DTO-Odoo/project-addons/dto_purchase_stock``, ``PNB`` =
``D:/Projects/dataone/DTO-Odoo/3rd-addons/printnode_base``, ``O17`` =
``D:/Projects/dataone/odoo-17.0``, ``O19`` = ``D:/Projects/odoo-19.0``.
Every line reference was opened in the real source before the assertion that
rests on it was written (hard rule 6); ``tests/wf015/common.py`` carries the
same citations for everything it exports.

What this file proves
---------------------
**TC207 — the accept half.** ``packing_slip_attachment`` is a plain
``fields.Binary`` and ``packing_slip_attachment_name`` a plain ``fields.Char``
(``DPS/models/stock_picking.py:13-16``). The declaration passes **no**
``attachment=`` argument, and ``fields.Binary`` defaults to
``attachment=True`` (``O17 odoo/fields.py:2334-2344``, attribute at ``:2344``;
``O19 odoo/orm/fields_binary.py:30-39``, attribute at ``:39``), so each stored
payload IS an ``ir_attachment`` row — ``res_model='stock.picking'``,
``res_field='packing_slip_attachment'``, ``res_id=<picking id>``,
``type='binary'`` (``O17 odoo/fields.py:2457-2473``) — filestore-managed and
content-deduplicated (``O17 base/models/ir_attachment.py:135-146``, the
``if not os.path.exists`` guard at ``:138``). ``copy=True`` is the ``Field``
default and is not overridden, which is why ``copy()`` duplicates the payload
onto the duplicate as a second ``ir_attachment`` row (step 12). **An earlier
premise in this suite called the field "a column on stock_picking"; that was
wrong, and ``tests/wf015/test_reconciliation.py:167-188`` carries the same
correction.** The constraint
``_check_packing_slip_attachment_mimetype`` (``:27-40``) whitelists ten
mimetypes (``:34-39``), so ``.pdf`` and ``.jpg`` both pass. On the purchase
order, ``packing_slip_receipt_count`` is a **non-stored** compute over
``picking_ids.filtered(lambda r: r.packing_slip_attachment)``
(``DPS/models/purchase_order.py:10-16, 41-45``) — it recomputes on every read,
so no flush is needed. ``action_view_packing_slip_attachments`` (``:47-60``)
is public, ``ensure_one()``, and returns ``stock.action_picking_tree_all``
updated with a domain on ``packing_slip_receipt_ids.ids`` (``:52``) and
``views=[(tree_view_id, 'tree'), (False, 'form')]`` (``:53``). That ``'tree'``
is a **literal** in the source and is asserted as such; the view it names has
a ``<list>`` root in the same repository
(``DPS/views/stock_picking_views.xml:36``), so the root tag is asserted
separately through ``fg_common.list_tag(ctx)`` and the inconsistency is
logged, never silently reconciled. Step 10's gate is **cosmetic** and the test
says so: ``groups="stock.group_stock_user"`` sits only on the purchase-order
button (``DPS/views/purchase_order_views.xml:14``); the method itself performs
no ACL check and ``stock.action_picking_tree_all`` carries no groups, so what
actually stops a plain internal user is the ``stock.picking`` model ACL —
``O17 stock/security/ir.model.access.csv:8-9`` grants read only to
``stock.group_stock_user`` / ``stock.group_stock_manager``, and
``base.group_user`` holds a row for ``stock.picking.type`` (``:10``) but none
for ``stock.picking``.

**TC208 — the refusal half, and the shape of the guard.** The exact string is
``DPS/models/stock_picking.py:40``: *File type is not supported. Please upload
a PDF or image file* — a ``ValidationError`` wrapped in ``_()`` with **no
trailing period** (the workbook's step-4 text shows a final dot only because
it ends a sentence). Step 8 is answered from source rather than guessed: the
constraint calls ``ir.attachment._compute_mimetype({'name': …})`` with a
hand-built dict carrying **only** ``name`` (``:31-33``), and
``_compute_mimetype`` falls back to sniffing bytes only when ``raw`` or
``datas`` is present (``O17 base/models/ir_attachment.py:307-327``;
**identical** at ``O19 :353-373``). The guard therefore inspects the filename
extension and never the content, on both versions — so a non-PDF named
``.pdf`` is **accepted** and a real PDF named ``.dat`` is **refused**. Both
directions are asserted positively; v19's python-magic does not enter the
path, because ``guess_mimetype`` is only reached through ``raw``/``datas``.

**TC209 — the merged print.** ``action_print_attached_packing_slip``
(``DPS/models/stock_picking.py:87-148``) is PUBLIC, so the list-bound server
action (``DPS/views/stock_picking_views.xml:44-54``, whose body does nothing
but call it) is driven directly. ``self.filtered(...)`` at ``:89`` preserves
recordset order, and ``browse(ids)`` preserves the order of the ids passed, so
selection order is controllable. Exactly ONE ``ir.attachment`` is created per
invocation (``:110-117``) with ``name='Packing Slip'``, ``type='binary'``,
``res_model='stock.picking'`` and **no** ``res_id``. The success return
(``:134-138``) is an ``ir.actions.act_url`` **and nothing else**.

**TC210 — PrintNode.** Blocked stub: the offline half is asserted, then
``ctx.blocked``. ``ir.attachment.dpc_print`` (``PNB/models/ir_attachment.py:
9-44``) pushes the bytes to the PrintNode HTTPS API through
``printer.printnode_print_b64`` (``:31-33``) — an outbound integration,
forbidden by convention rule 4.

**The branch is deleted in the UAT/v19 source only.** WF-000 decision D-1
(client, 22 Aug 2026) collapsed it: the on-disk
``DPS/models/stock_picking.py:119-138`` returns the download action
unconditionally, with no ``has_group`` check and no read of
``res.company.printnode_enabled`` / ``res.users.printnode_enabled``. The v17
target does **not** run that source — it runs an older installed revision
(the capability-probe caveat below), and there the method still branches:
``main:…/dto_purchase_stock/models/stock_picking.py:119-122`` is the
three-condition test, ``:123-127`` the download return, and ``:128-129`` the
``else`` that calls ``attachment.dpc_print()`` before returning the
``'Report was sent to printer'`` notification at ``:130-139``.

The ``has_group`` leg is always satisfied (``PNB/security/security.xml:24-26``
implies the group into ``base.group_user``), so on v17 the download branch is
reached **only because PrintNode is disabled** — which is exactly what
``common.require_printnode_off`` asserts before any of TC209/TC210/TC211 is
allowed to invoke the merged print. Without that probe these three cases
could fire a live PrintNode job on the v17 clone.

**TC211 — nothing attached.** The empty branch (``:140-147``) returns
``{'type': 'ir.actions.client', 'tag': 'display_notification', 'params':
{'message': 'There are no attachments to print.', 'type': 'info', 'sticky':
False}}`` — the message **with** its trailing period. ``streams_to_merge``
stays empty, so the ``create`` at ``:110`` never runs and no attachment
appears. Step 9's answer is also in the source: the ``filtered`` at ``:89``
drops slipless receipts **silently**, so a mixed selection merges only the
available slips with no warning of any kind.

Expected outcomes
-----------------
* ``TC207`` — **EXPECTED v17 OUTCOME: PASS.** v19: PASS, unless the port
  converts the Binary into a real ``ir.attachment``, in which case step 12
  inverts and the case must be re-signed.
* ``TC208`` — **EXPECTED v17 OUTCOME: PASS.** v19: PASS —
  ``_compute_mimetype`` is unchanged.
* ``TC209`` — **EXPECTED v17 OUTCOME: FAIL at step 9**, PASS on steps 1-8.
  The workbook's own title scopes this case to "when PrintNode is off", and
  ``require_printnode_off`` enforces exactly that precondition, so the run
  takes the download branch on both revisions. On that branch there is no
  success toast: the UAT source returns an ``act_url`` only (``:134-138``)
  and the installed v17 revision returns the same ``act_url``
  (``main:…:123-127``); the only ``display_notification`` reachable in either
  form is the *no-attachments* branch (``:140-147``). The workbook's
  expectation is immutable (hard rule 2), so the assertion stays exactly as
  written and the baseline FAIL is the recorded result. Consequence to read
  with it: ``ctx.check`` raises, so steps 10 and 11 are **not reached** on
  either version until a toast is added — they are written in workbook order
  regardless. v19: FAIL at step 9 for the same reason. (If PrintNode were
  left enabled on the clone the shape would invert on v17 — step 8 would fail
  and step 9 pass — which is a second reason the probe blocks instead of
  running.)
* ``TC210`` — **EXPECTED v17 OUTCOME: BLOCKED** (outbound integration). It
  blocks at ``require_printnode_off`` when PrintNode is enabled, and at step
  3 when it is not, because ``dpc_print`` cannot be observed without firing
  it. Under decision D-1 the branch is additionally gone from the target
  state. v19: BLOCKED.
* ``TC211`` — **EXPECTED v17 OUTCOME: PASS.** v19: PASS.

Every case opens with the capability probe from ``tests/wf015/common.py``
(``require_packing_slip`` / ``require_print_packing_slip``) and reports
**BLOCKED with a precise reason** rather than FAIL when the contribution is
absent — the on-disk ``dto_purchase_stock`` is already a v19 port
(``__manifest__.py:9``) and cannot build the v17 registry, so whatever the
v17 target serves is an older installed revision that has to be probed.

Documented adaptations (hard rules 3 and 5)
-------------------------------------------
1. **Receipts are built two ways, on purpose.** TC207 and TC208 need the
   purchase order's stat-button counter, so they build a namespaced PO per
   receipt and take the receipt from ``order.picking_ids`` — never from a
   search on ``origin``, which reports N+1 on v17 because ``_create_picking``
   leaves core's own empty receipt behind (``O17 purchase_stock/models/
   purchase_order.py:237-261``; v19 unlinks it at ``:400-401``). One PO per
   receipt makes the count deterministic whatever the per-line receipt engine
   does — that engine is TC201's subject, not this file's. TC209, TC210 and
   TC211 need no purchase order at all (the print method reads only
   ``stock.picking.packing_slip_attachment``), so they create lightweight
   draft receipts directly on a namespaced vendor and the warehouse's
   existing incoming operation type. Nothing pre-existing is modified: the
   operation type is only *read*, and the sweep reclaims the pickings through
   their namespaced ``partner_id`` (``common.sweep_wf015``).
2. **The merged-print attachment is swept by delta, not by name.** Its name
   is the literal ``'Packing Slip'`` and it carries no ``res_id``
   (``:110-117``), so it cannot be namespaced; deleting by name would destroy
   other people's rows, which rule 3 forbids.
   ``common.print_attachment_ids`` snapshots the ids before the first call and
   ``common.sweep_new_attachments`` removes only this run's delta, in a
   ``finally`` that can never raise.
3. **Page count and page order are byte scans, and are labelled as such.**
   The QA venv has no PDF library (``requirements.txt`` pins none; confirmed
   by ``pip list``), so ``common.pdf_page_count`` counts ``/Type /Page``
   objects and this file locates each slip by the ASCII marker
   ``common.tiny_pdf_bytes`` writes into its uncompressed content stream.
   ``_merge_pdfs`` copies page objects through ``PdfFileWriter.
   appendPagesFromReader`` without recompressing them
   (``O17 base/models/ir_actions_report.py:689-705``,
   ``O17 odoo/tools/pdf/__init__.py:98-119``), so both scans hold for the
   output this suite produces. A producer that compressed the page tree into
   an object stream would defeat them, and the mismatch dict reports the
   offsets so such a change fails loudly rather than quietly.
4. **TC209 selects in a deliberately non-id order.** The three receipts are
   created A, B, C and selected ``[B, A, C]``, so step 6 proves the pages
   follow the *selection* and not the insert order — which a monotonic
   ``[A, B, C]`` run could not distinguish.
5. **The JPEG conversion itself is not asserted, only its inputs and its
   output.** ``_convert_image_stream_to_pdf_stream`` (``:63-85``) is PRIVATE
   and unreachable over ``call_kw``; ``img2pdf`` is not installed on this
   workstation, so its ``mm_to_pt`` could not be read and no page-geometry
   value is asserted. Step 7 asserts what IS verified — that
   ``company_id.paperformat_id.print_page_width/height`` (``:98-103``, both
   computed at ``O17 base/models/report_paperformat.py:188-189,212-213``)
   supply a non-zero page size, and that the JPEG contributed exactly one
   page beyond the two PDF slips — and records the ``/MediaBox``,
   ``/DCTDecode`` and ``JFIF`` evidence as log lines.
6. **"Log in as TD-U-03" is recorded, not impersonated**, except where the
   case is about access: the platform session acts throughout, and TC207 step
   10 opens a second session as the platform's plain internal user
   (``framework.qa_fixtures.QA_USER_LOGIN``, ``base.group_user`` only) for
   the one assertion that needs a user outside ``stock.group_stock_user``.
7. **Convention rule 4.** Nothing here calls ``dpc_print``,
   ``printnode_print_b64``, ``action_test_connection`` or any cron *by name*;
   TC210 asserts its offline half and blocks. But ``dpc_print`` is reachable
   **indirectly**: on the installed v17 revision
   ``action_print_attached_packing_slip`` still branches into it
   (``main:…/stock_picking.py:128-129``), and TC209, TC210 and TC211 all
   invoke that method. Every one of them therefore opens with
   ``common.require_print_packing_slip``, which calls
   ``common.require_printnode_off`` and reports **BLOCKED** when
   ``res.company.printnode_enabled`` and ``res.users.printnode_enabled`` are
   both True. The flags are read, never written — flipping either would be a
   master-data change (rule 3) and would arm the integration. TC210 step 10
   (removing the user from the PrintNode group) is not performable even
   offline: ``PNB/security/security.xml:24-26`` adds
   ``printnode_security_group_user`` to ``base.group_user.implied_ids``, so
   every internal user is implicitly a PrintNode user.

Helpers defined locally (not available from ``tests/wf015/common.py``)
----------------------------------------------------------------------
``_error_tail``, ``_parse_arch``, ``_view_arch_by_xmlid``, ``_view_record``,
``_make_receipt``, ``_drop_pickings``, ``_marker_offset``,
``_printjob_count``, ``_attachment_count``, ``_role_note``.
"""
import re
import xml.etree.ElementTree as ET

from framework.registry import test_case
from tests.wf015.common import (ERROR_PACKING_SLIP_MIMETYPE, MARKER,
                                MSG_NO_ATTACHMENTS,
                                PACKING_SLIP_MIMETYPE_WHITELIST,
                                PRINTNODE_GROUP_XMLIDS,
                                PRINT_ATTACHMENT_NAME, WORKFLOW,
                                WORKFLOW_NAME, XMLID_ACTION_PICKING_TREE_ALL,
                                XMLID_GROUP_STOCK_USER,
                                XMLID_PACKING_SLIP_TREE, XMLID_PO_FORM_INHERIT,
                                XMLID_PRINTNODE_GROUP_USER, OdooRPCError,
                                attach_packing_slip, attachment_id_from_action,
                                attachment_row, confirm_purchase_order,
                                copied_id,
                                default_picking_type, ensure_qa_user,
                                ensure_vendor, expect_error, fetch_web_content,
                                fixture_token, list_tag, make_product,
                                make_purchase_order, open_namespace,
                                order_picking_ids, own_company_id,
                                packing_slip_row, paperformat_of_company,
                                pdf_page_count, po_line_values,
                                print_attachment_ids, print_packing_slips,
                                require_packing_slip,
                                require_print_packing_slip, rpc_as_qa_user,
                                sku, sweep_new_attachments, sweep_wf015, tag,
                                tiny_blob_b64, tiny_jpeg_b64, tiny_pdf_b64,
                                trace)

MODULE = "dto_purchase_stock"

#: A deterministic future date for the fixture purchase-order lines. Never
#: derived from "today": hard rule 5 forbids time-dependent expected values,
#: and nothing in these five cases depends on the date at all.
DATE_PLANNED = "2026-12-01 08:00:00"

#: ``OdooRPC.call`` prefixes every server fault with ``"<model>.<method>
#: failed: "`` (adapters/base.py:171-178). TC208 demands the message
#: *exactly*, so the transport prefix is stripped before comparing — never
#: the message itself.
_RPC_PREFIX = " failed: "

#: dto_purchase_stock/models/stock_picking.py:53 — the literal the source
#: writes into the action's ``views``, paired with a view whose root element
#: is ``<list>`` (views/stock_picking_views.xml:36). Asserted as the literal;
#: the root tag is asserted separately through ``fg_common.list_tag(ctx)``.
ACTION_VIEW_TYPE_LITERAL = "tree"

#: views/stock_picking_views.xml:37-39 — column name -> label, in source
#: order.
PACKING_SLIP_TREE_COLUMNS = [
    ("name", "Receipt Number"),
    ("date_done", "Receive Date"),
    ("packing_slip_attachment_name", "Attachment"),
]

#: printnode_base/models/printnode_printjob.py:13 — the job model TC209 step
#: 10 and TC211 step 6 count.
PRINTNODE_JOB_MODEL = "printnode.printjob"

#: The blocked reason for TC210, recorded verbatim from
#: docs/WF-015_AUTOMATION_PLAN.md / reports/data/wf015_feasibility.json.
TC210_BLOCKED_REASON = (
    "requires PrintNode hardware/account — attachment.dpc_print() "
    "(3rd-addons/printnode_base/models/ir_attachment.py:9-44) pushes the "
    "merged PDF to the PrintNode HTTPS API via printer.printnode_print_b64 "
    "(:31-33); outbound integrations are forbidden (AUTOMATION_CONVENTIONS "
    "rule 4). The branch is DELETED in the UAT/v19 source by WF-000 decision "
    "D-1 (client, 22 Aug 2026): the on-disk dto_purchase_stock/models/"
    "stock_picking.py:119-138 returns the download action unconditionally, "
    "with no has_group check and no printnode_enabled read. The v17 target "
    "runs an OLDER INSTALLED REVISION in which the branch survives "
    "(main:project-addons/dto_purchase_stock/models/stock_picking.py:119-139, "
    "dpc_print at :129), so on v17 the download action observed at step 2 is "
    "evidence that PrintNode is disabled — asserted by "
    "common.require_printnode_off — not evidence that the branch is gone.")


# ===========================================================================
# Local helpers — everything tests/wf015/common.py does not already provide
# ===========================================================================
def _error_tail(message) -> str:
    """The server's own message, with the transport's prefix removed."""
    text = str(message)
    if _RPC_PREFIX in text:
        return text.split(_RPC_PREFIX, 1)[1].strip()
    return text.strip()


def _parse_arch(arch: str):
    """Parse a view arch string into an ElementTree root."""
    return ET.fromstring(arch)


def _view_arch_by_xmlid(ctx, model: str, xmlid: str, view_type: str) -> str:
    """The composed arch of ONE named view.

    ``fg_common.form_arch`` fetches whatever view the server picks for a
    type; steps 8 and 9 of TC207 are about a specific record, so the view id
    is passed explicitly. The list type name is resolved the same way
    ``fg_common.form_arch`` resolves it (``adapter.list_view_type``: ``tree``
    on v17, ``list`` on v19), so no version branch reaches the test body.
    """
    rpc = ctx.adapter.rpc
    if view_type in ("tree", "list"):
        view_type = getattr(ctx.adapter, "list_view_type", view_type)
    view_id = rpc.ref(xmlid)
    return rpc.call(model, "get_view", view_id=view_id, view_type=view_type)[
        "arch"]


def _view_record(rpc, xmlid: str) -> dict | None:
    """The ``ir.ui.view`` row behind an XML id, with its OWN arch.

    The composed arch a client receives has already had ``groups`` attributes
    evaluated and stripped, so a claim about ``groups=`` has to be read from
    the inherit's stored arch instead (TC207 step 10).
    """
    view_id = rpc.ref(xmlid)
    if not view_id:
        return None
    fields_ = [f for f in ("name", "model", "type", "priority", "arch",
                           "inherit_id", "active")
               if rpc.field_exists("ir.ui.view", f)]
    rows = rpc.read("ir.ui.view", [view_id], fields_)
    return rows[0] if rows else None


def _make_receipt(ctx, partner_id: int, picking_type_id: int,
                  label: str) -> int:
    """A lightweight draft incoming transfer under this run's namespace.

    ``location_id`` / ``location_dest_id`` are ``precompute=True`` stored
    computes (``O17 stock/models/stock_picking.py:457-464``), so a create
    carrying only the operation type and the partner is complete; the vendor
    fixture sets ``property_stock_supplier`` (``common.ensure_vendor``), which
    is what ``_compute_location_id`` reads for an incoming picking. No moves
    are needed: the packing slip is a field on the picking and
    ``action_print_attached_packing_slip`` reads nothing else.
    """
    return ctx.adapter.rpc.create("stock.picking", {
        "partner_id": partner_id,
        "picking_type_id": picking_type_id,
        "origin": tag(f"{MARKER} {label}"),
    })


def _drop_pickings(rpc, picking_ids) -> None:
    """Best-effort removal of this run's transfers. Never raises."""
    for picking_id in [p for p in picking_ids if p]:
        try:
            rpc.call("stock.picking", "action_cancel", [picking_id])
        except OdooRPCError:
            pass
        try:
            rpc.call("stock.picking", "unlink", [picking_id])
        except OdooRPCError:
            pass


def _marker_offset(data: bytes, marker: str):
    """Byte offset of a slip's text marker in the merged PDF, or ``None``.

    ``common.tiny_pdf_bytes`` writes the marker into an **uncompressed**
    content stream and ``_merge_pdfs`` copies page objects verbatim
    (module docstring, adaptation 3), so the offsets order the pages. A
    HEURISTIC, by the same reasoning as ``common.pdf_page_count``.
    """
    index = data.find(marker.encode("ascii"))
    return index if index >= 0 else None


def _printjob_count(rpc) -> int:
    """PrintNode jobs on this target, or 0 when the model is absent.

    Only ever used as a before/after delta inside one test — never as a
    standalone "exactly N" claim (hard rule 5).
    """
    if not rpc.model_exists(PRINTNODE_JOB_MODEL):
        return 0
    return rpc.call(PRINTNODE_JOB_MODEL, "search_count", [])


def _attachment_count(rpc) -> int:
    """Whole-table ``ir.attachment`` count — a before/after delta only."""
    return rpc.call("ir.attachment", "search_count", [])


def _role_note(role: str) -> str:
    """One log line recording the workbook role and why it is not assumed."""
    return (f"workbook role {role}: the label is test data, not a group XML "
            f"id. The platform session acts throughout; the only "
            f"access-sensitive step (TC207 step 10) opens a SECOND session "
            f"as the platform's plain internal user "
            f"(framework/qa_fixtures.py QA_USER_LOGIN, base.group_user "
            f"only). Read access to stock.picking is granted to "
            f"stock.group_stock_user / stock.group_stock_manager only "
            f"(O17 stock/security/ir.model.access.csv:8-9); base.group_user "
            f"carries a row for stock.picking.type (:10) and none for "
            f"stock.picking.")


def _po_receipt(ctx, label: str, partner_id: int):
    """A confirmed one-line purchase order and its receipt.

    Returns ``(order_id, picking_id, product_id)``. The receipt is taken from
    ``order.picking_ids``, which is ``@api.depends('order_line.move_ids.
    picking_id')`` on both versions (``O17 purchase_stock/models/
    purchase_order.py:19,22-25``; ``O19 :22,44-47``) and therefore never
    contains an empty picking — the version trap a search on ``origin`` walks
    into (module docstring, adaptation 1).
    """
    rpc = ctx.adapter.rpc
    product_id = make_product(ctx, f"{label} P")
    order_id = make_purchase_order(
        ctx, [po_line_values(ctx, product_id, 2.0, DATE_PLANNED)],
        partner_id=partner_id, label=label)
    confirm_purchase_order(rpc, order_id)
    picking_ids = order_picking_ids(rpc, order_id)
    return order_id, (picking_ids[0] if picking_ids else None), product_id


def _slip_counter(rpc, order_id: int) -> dict:
    """The purchase order's stat-button inputs, recomputed on read.

    Both fields are NON-stored computes (``DPS/models/purchase_order.py:
    10-16``, ``_compute_receipt_with_attachment`` ``:41-45``), so ``read``
    recomputes them and there is nothing to flush.
    """
    row = rpc.read("purchase.order", [order_id],
                   ["packing_slip_receipt_count",
                    "packing_slip_receipt_ids"])[0]
    return {"count": row["packing_slip_receipt_count"],
            "receipt_ids": sorted(row["packing_slip_receipt_ids"])}


# ===========================================================================
# TC207 — the accept half
# ===========================================================================
@test_case(
    id="TEST-WF015-TC207",
    name="A PDF and a whitelisted image upload as the packing slip and reach "
         "the stat button",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module=MODULE, priority="P2", kind="HYBRID", order=15207,
    description="A PDF and a JPEG both pass the mimetype whitelist and land "
                "in the Binary column; the purchase order's non-stored "
                "packing_slip_receipt_count follows them; the stat button "
                "returns stock.action_picking_tree_all restricted to the "
                "receipts carrying a slip and forced into the read-only "
                "packing_slip_attachment_tree; a user outside "
                "stock.group_stock_user cannot read the records; and copy() "
                "duplicates the payload, as a Binary column must.",
    traceability=trace("DATAONE-TC207"))
def test_tc207(ctx):
    rpc = ctx.adapter.rpc
    require_packing_slip(ctx)
    open_namespace(ctx)
    picking_ids = []
    duplicate_id = None
    try:
        with ctx.step("Log in as TD-U-03 and open the receipt."):
            ctx.log(_role_note("TD-U-03"))
            partner_id = ensure_vendor(rpc, "TD-PA-03")
            order_a, receipt_a, _product_a = _po_receipt(ctx, "TC207A",
                                                         partner_id)
            order_b, receipt_b, _product_b = _po_receipt(ctx, "TC207B",
                                                         partner_id)
            picking_ids += [receipt_a, receipt_b]
            ctx.check("each fixture purchase order produced a receipt to "
                      "upload onto, read from order.picking_ids",
                      {"receipt_a": True, "receipt_b": True,
                       "slips_before": {"a": 0, "b": 0}},
                      {"receipt_a": bool(receipt_a),
                       "receipt_b": bool(receipt_b),
                       "slips_before":
                           {"a": _slip_counter(rpc, order_a)["count"],
                            "b": _slip_counter(rpc, order_b)["count"]}})

        with ctx.step("Upload the fixture PDF into Packing Slip Attachment "
                      "and save."):
            pdf_name = f"{sku('tc207')}-slip.pdf"
            pdf_payload = tiny_pdf_b64(f"{fixture_token()} TC207 PDF")
            raised, message = expect_error(attach_packing_slip, rpc,
                                           receipt_a, pdf_name, pdf_payload)
            ctx.check("writing the Binary and the Char in one call — as the "
                      "form does — is accepted for a .pdf filename",
                      {"raised": False}, {"raised": raised})
            ctx.log(f"save message (expected 'no error raised'): {message!r}")

        with ctx.step("Assert the save succeeds and packing_slip_attachment "
                      "is populated."):
            row = packing_slip_row(rpc, receipt_a)
            ctx.check("the Binary column holds exactly the uploaded bytes",
                      {"populated": True, "payload": pdf_payload},
                      {"populated": bool(row["packing_slip_attachment"]),
                       "payload": row["packing_slip_attachment"]})

        with ctx.step("Assert packing_slip_attachment_name holds the "
                      "uploaded filename."):
            ctx.check("packing_slip_attachment_name, verbatim", pdf_name,
                      packing_slip_row(rpc,
                                       receipt_a)[
                          "packing_slip_attachment_name"])

        with ctx.step("Open the related purchase order and assert the Packing "
                      "Slip Attachment(s) stat button's counter "
                      "incremented."):
            # Non-stored compute (DPS/models/purchase_order.py:10-16,41-45):
            # read() recomputes it, so there is nothing to flush.
            ctx.check("packing_slip_receipt_count moved 0 -> 1 and names the "
                      "receipt that carries the slip",
                      {"count": 1, "receipt_ids": [receipt_a]},
                      _slip_counter(rpc, order_a))

        with ctx.step("Click the stat button."):
            action = rpc.call("purchase.order",
                              "action_view_packing_slip_attachments",
                              [order_a])
            ctx.check_true("the public action returned a dict",
                           isinstance(action, dict),
                           actual_desc=f"{type(action).__name__}: {action!r}")

        with ctx.step("Assert it opens stock.action_picking_tree_all "
                      "restricted to receipts carrying a slip."):
            ctx.check("the act_window is stock.action_picking_tree_all with a "
                      "domain on packing_slip_receipt_ids.ids "
                      "(DPS/models/purchase_order.py:49-52)",
                      {"xml_id": XMLID_ACTION_PICKING_TREE_ALL,
                       "id": rpc.ref(XMLID_ACTION_PICKING_TREE_ALL),
                       "res_model": "stock.picking",
                       "domain": [["id", "in", [receipt_a]]]},
                      {"xml_id": action.get("xml_id"),
                       "id": action.get("id"),
                       "res_model": action.get("res_model"),
                       "domain": action.get("domain")})

        with ctx.step("Assert the list is forced into the read-only "
                      "dto_purchase_stock.packing_slip_attachment_tree view "
                      "showing Receipt Number, Receive Date and Attachment."):
            tree_view_id = rpc.ref(XMLID_PACKING_SLIP_TREE)
            arch = _view_arch_by_xmlid(ctx, "stock.picking",
                                       XMLID_PACKING_SLIP_TREE, "tree")
            root = _parse_arch(arch)
            columns = [(node.get("name"), node.get("string"))
                       for node in root.iter("field") if node.get("name")]
            view_row = _view_record(rpc, XMLID_PACKING_SLIP_TREE) or {}
            # The source pairs the LITERAL 'tree' (:53) with a view whose root
            # element is <list> (views/stock_picking_views.xml:36). Both are
            # asserted, separately, and the inconsistency is logged.
            ctx.check("the action pins the named view with the literal "
                      "'tree', the view is priority 1000 on stock.picking, "
                      "its root renders with this target's list tag, and it "
                      "carries the three documented columns",
                      {"views": [[tree_view_id, ACTION_VIEW_TYPE_LITERAL],
                                 [False, "form"]],
                       "root_tag": list_tag(ctx),
                       "priority": 1000,
                       "model": "stock.picking",
                       "columns": PACKING_SLIP_TREE_COLUMNS},
                      {"views": action.get("views"),
                       "root_tag": root.tag,
                       "priority": view_row.get("priority"),
                       "model": view_row.get("model"),
                       "columns": columns})
            ctx.log("RECORDED INCONSISTENCY: purchase_order.py:53 writes the "
                    "literal 'tree' into the action's views while "
                    "stock_picking_views.xml:36 declares a <list> root. The "
                    "two are asserted separately so neither masks the other.")

        with ctx.step("Assert the list is read-only — no inline edit, no "
                      "create."):
            ctx.check("the view root carries create=0 edit=0 delete=0 "
                      "(views/stock_picking_views.xml:36)",
                      {"create": "0", "edit": "0", "delete": "0"},
                      {"create": root.get("create"),
                       "edit": root.get("edit"),
                       "delete": root.get("delete")})

        with ctx.step("Assert a user without stock.group_stock_user cannot "
                      "reach it."):
            # The button's groups= is a COSMETIC gate: the method itself has
            # no ACL check and stock.action_picking_tree_all carries no
            # groups, so what actually stops the user is the stock.picking
            # model ACL. Both halves are asserted.
            qa_uid = ensure_qa_user(rpc)
            groups_field = ctx.adapter.user_groups_field
            qa_groups = rpc.read("res.users", [qa_uid], [groups_field])[0][
                groups_field]
            stock_user_gid = rpc.ref(XMLID_GROUP_STOCK_USER)
            qa_rpc = rpc_as_qa_user(ctx.env)
            raised, message = expect_error(
                qa_rpc.search_read, "stock.picking",
                [("id", "in", [receipt_a])], ["name"])
            inherit_arch = (_view_record(rpc, XMLID_PO_FORM_INHERIT)
                            or {}).get("arch") or ""
            ctx.check("the plain internal user is outside "
                      "stock.group_stock_user and is refused read on "
                      "stock.picking, and the PO button declares the group in "
                      "its own arch (views/purchase_order_views.xml:14)",
                      {"qa_user_in_stock_group": False,
                       "read_refused": True,
                       "button_declares_group": True},
                      {"qa_user_in_stock_group":
                           bool(stock_user_gid and stock_user_gid in
                                (qa_groups or [])),
                       "read_refused": raised,
                       "button_declares_group":
                           f'groups="{XMLID_GROUP_STOCK_USER}"'
                           in inherit_arch})
            ctx.log(f"stock.picking read as the plain internal user: "
                    f"{message!r}")
            ctx.log("the gate is cosmetic: "
                    "action_view_packing_slip_attachments "
                    "(DPS/models/purchase_order.py:47-60) performs no ACL "
                    "check of its own, and stock.action_picking_tree_all "
                    "carries no groups — the refusal comes from the "
                    "stock.picking model ACL.")

        with ctx.step("On a second receipt, upload the fixture JPEG and save; "
                      "assert it is accepted."):
            jpeg_name = f"{sku('tc207')}-slip.jpg"
            jpeg_payload = tiny_jpeg_b64()
            raised, message = expect_error(attach_packing_slip, rpc,
                                           receipt_b, jpeg_name,
                                           jpeg_payload)
            row = packing_slip_row(rpc, receipt_b)
            ctx.check("image/jpeg is on the whitelist "
                      "(DPS/models/stock_picking.py:34-39), so the JPEG is "
                      "stored and the second order's counter follows it",
                      {"raised": False, "name": jpeg_name,
                       "payload": jpeg_payload,
                       "counter": {"count": 1, "receipt_ids": [receipt_b]}},
                      {"raised": raised,
                       "name": row["packing_slip_attachment_name"],
                       "payload": row["packing_slip_attachment"],
                       "counter": _slip_counter(rpc, order_b)})
            ctx.log(f"JPEG save message (expected 'no error raised'): "
                    f"{message!r}; whitelist = "
                    f"{list(PACKING_SLIP_MIMETYPE_WHITELIST)}")

        with ctx.step("Duplicate a receipt carrying a slip with copy() and "
                      "assert the Binary payload is copied onto the duplicate "
                      "— record as the documented v17 behaviour."):
            # packing_slip_attachment is fields.Binary with attachment left
            # at its default True (DPS/models/stock_picking.py:14-16; O17
            # odoo/fields.py:2344), so the payload is an ir_attachment row
            # keyed res_field='packing_slip_attachment', and copy=True (the
            # Field default) duplicates it onto the new picking.
            # copied_id: copy() marshals back an int on v17 and a LIST on v19
            # (O17 odoo/models.py:5586 vs O19 odoo/orm/models.py:5530 +
            # odoo/service/model.py:102-104).
            duplicate_id = copied_id(rpc.call("stock.picking", "copy",
                                              [receipt_a]))
            picking_ids.append(duplicate_id)
            duplicate = packing_slip_row(rpc, duplicate_id)
            ctx.check("copy() duplicates both the filename and the payload "
                      "onto a brand-new transfer",
                      {"is_a_new_record": True,
                       "name": pdf_name,
                       "payload": pdf_payload},
                      {"is_a_new_record": duplicate_id != receipt_a,
                       "name": duplicate["packing_slip_attachment_name"],
                       "payload": duplicate["packing_slip_attachment"]})
            ctx.log("DOCUMENTED v17 BEHAVIOUR: the payload is an "
                    "attachment-backed fields.Binary (attachment defaults to "
                    "True, O17 odoo/fields.py:2344), so it lives in an "
                    "ir_attachment row with res_field="
                    "'packing_slip_attachment'; copy=True is the Field "
                    "default, so copy() writes the same bytes onto the "
                    "duplicate as a second ir_attachment row sharing one "
                    "deduplicated filestore file (O17 base/models/"
                    "ir_attachment.py:135-146). If the port ever sets "
                    "attachment=False or copy=False this step inverts and "
                    "the case must be re-signed.")
    finally:
        # The workbook's postcondition asks only for the step-12 duplicate to
        # go; hard rules 3 and 5 remove every fixture. Never raises.
        try:
            _drop_pickings(rpc, picking_ids)
            sweep_wf015(rpc)
        except Exception:  # noqa: BLE001
            pass


# ===========================================================================
# TC208 — the refusal half
# ===========================================================================
@test_case(
    id="TEST-WF015-TC208",
    name="A non-PDF, non-image upload is refused with the exact error",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module=MODULE, priority="P2", kind="API", order=15208,
    description="An .xlsx and a .txt upload are each refused with exactly "
                "'File type is not supported. Please upload a PDF or image "
                "file', the Binary stays empty and the purchase order's "
                "counter does not move; a non-PDF named .pdf is ACCEPTED and "
                "a real PDF named .dat is REFUSED, proving the guard reads "
                "the filename and never the content.",
    traceability=trace("DATAONE-TC208"))
def test_tc208(ctx):
    rpc = ctx.adapter.rpc
    require_packing_slip(ctx)
    open_namespace(ctx)
    picking_ids = []
    try:
        with ctx.step("Log in as TD-U-03 and open the receipt."):
            ctx.log(_role_note("TD-U-03"))
            partner_id = ensure_vendor(rpc, "TD-PA-03")
            order_id, receipt_id, _product_id = _po_receipt(ctx, "TC208",
                                                            partner_id)
            picking_ids.append(receipt_id)
            ctx.check("the fixture receipt exists and carries no packing slip",
                      {"receipt": True, "name": False, "payload": False,
                       "counter": 0},
                      {"receipt": bool(receipt_id),
                       "name": bool(packing_slip_row(rpc, receipt_id)[
                           "packing_slip_attachment_name"]),
                       "payload": bool(packing_slip_row(rpc, receipt_id)[
                           "packing_slip_attachment"]),
                       "counter": _slip_counter(rpc, order_id)["count"]})

        with ctx.step("Upload the .xlsx fixture into Packing Slip Attachment "
                      "and attempt to save."):
            xlsx_name = f"{sku('tc208')}-slip.xlsx"
            xlsx_raised, xlsx_message = expect_error(
                attach_packing_slip, rpc, receipt_id, xlsx_name,
                tiny_blob_b64())

        with ctx.step("Assert a ValidationError is raised."):
            ctx.check("the .xlsx upload was refused", True, xlsx_raised)

        with ctx.step("Assert the message is exactly File type is not "
                      "supported. Please upload a PDF or image file."):
            # DPS/models/stock_picking.py:40 — wrapped in _(), NO trailing
            # period. The workbook's sentence-final dot is not part of it.
            ctx.check("the server message, verbatim",
                      ERROR_PACKING_SLIP_MIMETYPE, _error_tail(xlsx_message))

        with ctx.step("Assert packing_slip_attachment remains empty on the "
                      "record."):
            # Each RPC call is its own transaction, so the refusal really is
            # rolled back and a fresh read sees the untouched row.
            row = packing_slip_row(rpc, receipt_id)
            ctx.check("neither the payload nor the filename was stored",
                      {"payload": False, "name": False},
                      {"payload": bool(row["packing_slip_attachment"]),
                       "name": bool(row["packing_slip_attachment_name"])})

        with ctx.step("Assert the purchase order's stat-button counter did "
                      "not increment."):
            ctx.check("packing_slip_receipt_count is still 0 with no receipt "
                      "listed",
                      {"count": 0, "receipt_ids": []},
                      _slip_counter(rpc, order_id))

        with ctx.step("Repeat with the .txt fixture and assert the same exact "
                      "message."):
            txt_name = f"{sku('tc208')}-slip.txt"
            txt_raised, txt_message = expect_error(
                attach_packing_slip, rpc, receipt_id, txt_name,
                tiny_blob_b64())
            row = packing_slip_row(rpc, receipt_id)
            ctx.check("text/plain is refused with the identical string and "
                      "stores nothing",
                      {"raised": True,
                       "message": ERROR_PACKING_SLIP_MIMETYPE,
                       "payload": False, "counter": 0},
                      {"raised": txt_raised,
                       "message": _error_tail(txt_message),
                       "payload": bool(row["packing_slip_attachment"]),
                       "counter": _slip_counter(rpc, order_id)["count"]})

        with ctx.step("Repeat with a file whose extension is .pdf but whose "
                      "content is not a PDF, and record the outcome — whether "
                      "the guard inspects the name or the content."):
            # Answered from source: the constraint hands _compute_mimetype a
            # dict carrying ONLY 'name' (:31-33), and that method sniffs bytes
            # only when 'raw' or 'datas' is present (O17 ir_attachment.py:
            # 307-327; identical at O19 :353-373). Both directions are
            # asserted positively.
            fake_pdf_name = f"{sku('tc208')}-evil.pdf"
            fake_payload = tiny_blob_b64()
            fake_raised, fake_message = expect_error(
                attach_packing_slip, rpc, receipt_id, fake_pdf_name,
                fake_payload)
            real_pdf_as_dat = f"{sku('tc208')}-scan.dat"
            dat_raised, dat_message = expect_error(
                attach_packing_slip, rpc, receipt_id, real_pdf_as_dat,
                tiny_pdf_b64(f"{fixture_token()} TC208 DAT"))
            row = packing_slip_row(rpc, receipt_id)
            ctx.check("a non-PDF named .pdf is ACCEPTED and a real PDF named "
                      ".dat is REFUSED — the guard reads the filename "
                      "extension, never the content",
                      {"fake_pdf_refused": False,
                       "stored_name": fake_pdf_name,
                       "stored_payload": fake_payload,
                       "real_pdf_as_dat_refused": True,
                       "dat_message": ERROR_PACKING_SLIP_MIMETYPE},
                      {"fake_pdf_refused": fake_raised,
                       "stored_name": row["packing_slip_attachment_name"],
                       "stored_payload": row["packing_slip_attachment"],
                       "real_pdf_as_dat_refused": dat_raised,
                       "dat_message": _error_tail(dat_message)})
            ctx.log(f"fake .pdf message (expected 'no error raised'): "
                    f"{fake_message!r}")

        with ctx.step("Upload the valid PDF fixture and assert it is accepted "
                      "(the control)."):
            good_name = f"{sku('tc208')}-slip.pdf"
            good_payload = tiny_pdf_b64(f"{fixture_token()} TC208 OK")
            good_raised, good_message = expect_error(
                attach_packing_slip, rpc, receipt_id, good_name, good_payload)
            row = packing_slip_row(rpc, receipt_id)
            ctx.check("the control upload is stored and the counter finally "
                      "moves to 1",
                      {"raised": False, "name": good_name,
                       "payload": good_payload,
                       "counter": {"count": 1, "receipt_ids": [receipt_id]}},
                      {"raised": good_raised,
                       "name": row["packing_slip_attachment_name"],
                       "payload": row["packing_slip_attachment"],
                       "counter": _slip_counter(rpc, order_id)})
            ctx.log(f"control message (expected 'no error raised'): "
                    f"{good_message!r}")

        with ctx.step("Record step 8's outcome as the documented strength of "
                      "the guard."):
            # Documentation, not an assertion — the workbook says "record".
            ctx.log(
                "DOCUMENTED: _check_packing_slip_attachment_mimetype "
                "(DPS/models/stock_picking.py:27-40) calls "
                "ir.attachment._compute_mimetype({'name': <filename>}) — a "
                "hand-built dict with ONLY a name key (:31-33). "
                "_compute_mimetype resolves mimetypes.guess_type(name) and "
                "falls back to sniffing bytes ONLY when the dict carries "
                "'raw' or 'datas' (O17 base/models/ir_attachment.py:307-327; "
                "byte-identical at O19 :353-373). STRENGTH: the check is "
                "cheap, deterministic and identical on v17 and v19 — v19's "
                "python-magic never enters this path, because guess_mimetype "
                "is only reached through raw/datas. WEAKNESS: an executable "
                "renamed evil.pdf is accepted and a genuine scan named "
                "scan.dat is refused. The workbook's python-magic concern "
                "does not apply. [UNVERIFIED] whether .xlsx resolves to the "
                "Office mimetype or to application/octet-stream depends on "
                "the SERVER's mimetypes registry — irrelevant to the "
                "verdict, since neither value is whitelisted, which is why "
                "this case asserts the error and never the resolved "
                "mimetype.")
    finally:
        try:
            _drop_pickings(rpc, picking_ids)
            sweep_wf015(rpc)
        except Exception:  # noqa: BLE001
            pass


# ===========================================================================
# TC209 — the merged print
# ===========================================================================
@test_case(
    id="TEST-WF015-TC209",
    name="The merged packing-slip print downloads one combined PDF when "
         "PrintNode is off",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module=MODULE, priority="P2", kind="HYBRID", order=15209,
    description="Three receipts carrying two PDFs and a JPEG merge into ONE "
                "ir.attachment named 'Packing Slip' with no res_id; the "
                "downloaded bytes carry a page per slip in the SELECTION "
                "order, the JPEG page is built from the company paperformat, "
                "and the returned action is an act_url download. Step 9 "
                "fails by construction: no success toast exists in the code.",
    traceability=trace("DATAONE-TC209"))
def test_tc209(ctx):
    rpc = ctx.adapter.rpc
    require_print_packing_slip(ctx)
    open_namespace(ctx)
    picking_ids = []
    attachments_before = set()
    try:
        with ctx.step("Log in as TD-U-03."):
            ctx.log(_role_note("TD-U-03"))
            partner_id = ensure_vendor(rpc, "TD-PA-03")
            picking_type_id = default_picking_type(rpc, "incoming")
            company_id = own_company_id(rpc)
            paperformat = paperformat_of_company(rpc, company_id)
            if not paperformat:
                # The image branch reads company_id.paperformat_id.
                # print_page_width/height (DPS/models/stock_picking.py:98-103)
                # and img2pdf.mm_to_pt(0) would produce a zero-size page, so
                # this is an environment gap with a precise cause — BLOCKED,
                # not FAILED.
                ctx.blocked(
                    f"res.company[{company_id}] has no paperformat_id on "
                    f"{ctx.env.key} (db={ctx.env.db}). "
                    "action_print_attached_packing_slip sizes the JPEG page "
                    "from company_id.paperformat_id.print_page_width/height "
                    "(dto_purchase_stock/models/stock_picking.py:98-103), so "
                    "without one the image branch builds a zero-size page. "
                    "Core defaults the field to base.paperformat_euro "
                    "(odoo-17.0/odoo/addons/base/models/res_company.py:68), "
                    "so its absence is a broken database, not a defect in "
                    "the feature under test.")
            ctx.log(f"company paperformat: {paperformat!r}")
            attachments_before = print_attachment_ids(rpc)

        with ctx.step("Open Inventory → Transfers and select the three "
                      "receipts in a known order."):
            # Created A, B, C; selected [B, A, C] — deliberately NOT id order,
            # so step 6 proves the pages follow the SELECTION (module
            # docstring, adaptation 4).
            marker_a = f"{fixture_token()} TC209 SLIP A"
            marker_b = f"{fixture_token()} TC209 SLIP B"
            receipt_a = _make_receipt(ctx, partner_id, picking_type_id,
                                      "TC209A")
            receipt_b = _make_receipt(ctx, partner_id, picking_type_id,
                                      "TC209B")
            receipt_c = _make_receipt(ctx, partner_id, picking_type_id,
                                      "TC209C")
            picking_ids += [receipt_a, receipt_b, receipt_c]
            attach_packing_slip(rpc, receipt_a,
                                f"{sku('tc209')}-slip-a.pdf",
                                tiny_pdf_b64(marker_a))
            attach_packing_slip(rpc, receipt_b,
                                f"{sku('tc209')}-slip-b.pdf",
                                tiny_pdf_b64(marker_b))
            attach_packing_slip(rpc, receipt_c,
                                f"{sku('tc209')}-slip-c.jpg",
                                tiny_jpeg_b64())
            selection = [receipt_b, receipt_a, receipt_c]
            jobs_before = _printjob_count(rpc)
            total_attachments_before = _attachment_count(rpc)
            ctx.check("all three receipts carry a slip, and the selection "
                      "order is not the id order",
                      {"slips": [True, True, True],
                       "selection_is_not_id_order": True},
                      {"slips": [bool(packing_slip_row(rpc, pid)[
                          "packing_slip_attachment"]) for pid in selection],
                       "selection_is_not_id_order":
                           selection != sorted(selection)})

        with ctx.step("Run Action → Print Attached Packing Slip."):
            # The list-bound server action (views/stock_picking_views.xml:
            # 44-54) does nothing but call this public method, so driving it
            # directly tests the same code.
            action = print_packing_slips(rpc, selection)
            ctx.check_true("the public method returned a dict",
                           isinstance(action, dict),
                           actual_desc=f"{type(action).__name__}: {action!r}")

        with ctx.step("Assert one new ir.attachment was created holding the "
                      "merged PDF."):
            created = sorted(print_attachment_ids(rpc) - attachments_before)
            attachment_id = attachment_id_from_action(action)
            row = attachment_row(rpc, attachment_id) if attachment_id else {}
            ctx.check("exactly ONE 'Packing Slip' attachment was created, it "
                      "is the one the action points at, and it carries the "
                      "fields stock_picking.py:110-117 writes",
                      {"created": 1,
                       "action_points_at_it": True,
                       "name": PRINT_ATTACHMENT_NAME,
                       "type": "binary",
                       "res_model": "stock.picking",
                       "res_id": False,
                       "mimetype": "application/pdf"},
                      {"created": len(created),
                       "action_points_at_it": attachment_id in created,
                       "name": row.get("name"),
                       "type": row.get("type"),
                       "res_model": row.get("res_model"),
                       "res_id": row.get("res_id") or False,
                       "mimetype": row.get("mimetype")})
            ctx.log(f"[UNVERIFIED] store_fname/checksum survive the create "
                    f"that passes BOTH store_fname='Packing Slip' and raw="
                    f"<bytes> (:110-117): store_fname="
                    f"{row.get('store_fname')!r}, checksum="
                    f"{row.get('checksum')!r}, file_size="
                    f"{row.get('file_size')!r} — recorded, not asserted.")

        with ctx.step("Assert the merged PDF has at least three pages — one "
                      "per source slip, with the JPEG wrapped into a page."):
            data = fetch_web_content(ctx, attachment_id)
            pages = pdf_page_count(data)
            ctx.check_true("the downloaded bytes are a PDF with at least "
                           "three pages (byte-scan heuristic — the QA venv "
                           "has no PDF library)",
                           data[:5] == b"%PDF-" and pages >= 3,
                           actual_desc=f"header={data[:8]!r}, "
                                       f"/Type /Page objects={pages}, "
                                       f"bytes={len(data)}")

        with ctx.step("Assert the pages appear in selection order."):
            offset_b = _marker_offset(data, marker_b)
            offset_a = _marker_offset(data, marker_a)
            ctx.check("both slip markers survive the merge and appear in the "
                      "SELECTION order [B, A, …], not the id order [A, B, …]",
                      {"marker_b_present": True, "marker_a_present": True,
                       "b_before_a": True},
                      {"marker_b_present": offset_b is not None,
                       "marker_a_present": offset_a is not None,
                       "b_before_a": bool(offset_b is not None
                                          and offset_a is not None
                                          and offset_b < offset_a)})
            ctx.log(f"marker offsets: B={offset_b}, A={offset_a} "
                    "(byte scan — see the module docstring, adaptation 3)")

        with ctx.step("Assert the JPEG page was converted to RGB/JPEG and "
                      "sized from the company paperformat."):
            # _convert_image_stream_to_pdf_stream (:63-85) is PRIVATE and
            # unreachable over call_kw, and img2pdf is not installed here, so
            # no geometry value is asserted. What IS verified: the inputs the
            # method reads (:98-103) are non-zero, and the JPEG contributed
            # exactly one page beyond the two PDF slips.
            ctx.check("the company paperformat supplies a non-zero page size "
                      "to the image branch, and the JPEG receipt added "
                      "exactly one page",
                      {"paperformat_present": True,
                       "print_page_width_positive": True,
                       "print_page_height_positive": True,
                       "pages_beyond_the_two_pdf_slips": 1},
                      {"paperformat_present": True,
                       "print_page_width_positive":
                           (paperformat.get("print_page_width") or 0) > 0,
                       "print_page_height_positive":
                           (paperformat.get("print_page_height") or 0) > 0,
                       "pages_beyond_the_two_pdf_slips": pages - 2})
            ctx.log(
                f"recorded, not asserted (img2pdf is absent from this "
                f"workstation, so mm_to_pt could not be read): "
                f"print_page_width={paperformat.get('print_page_width')}mm, "
                f"print_page_height={paperformat.get('print_page_height')}mm, "
                f"orientation={paperformat.get('orientation')!r}; "
                f"/DCTDecode present={b'/DCTDecode' in data}; "
                f"JFIF present={b'JFIF' in data}; "
                f"MediaBox entries="
                f"{[m.decode('ascii', 'replace') for m in re.findall(rb'/MediaBox\s*\[[^\]]*\]', data)]}")

        with ctx.step("Assert the returned action is a download URL, not a "
                      "print job."):
            ctx.check("the success return is exactly the act_url of "
                      "stock_picking.py:134-138, and no PrintNode job was "
                      "created",
                      {"action": {"type": "ir.actions.act_url",
                                  "url": f"/web/content/{attachment_id}"
                                         "?download=true",
                                  "target": "self"},
                       "printjob_delta": 0},
                      {"action": action,
                       "printjob_delta":
                           _printjob_count(rpc) - jobs_before})

        with ctx.step("Assert a display_notification toast confirming success "
                      "was returned."):
            # EXPECTED v17 OUTCOME: FAIL — and on v19 too. The success path
            # (DPS/models/stock_picking.py:134-138) returns an
            # ir.actions.act_url and NOTHING else; the only
            # display_notification in the whole method is the no-attachments
            # branch (:140-147). The workbook expectation is immutable (hard
            # rule 2), so the assertion stays exactly as written and the
            # baseline FAIL is the recorded result. ctx.check raises, so
            # steps 10 and 11 below are not reached until a toast is added.
            ctx.check("a display_notification toast confirms success",
                      {"type": "ir.actions.client",
                       "tag": "display_notification"},
                      {"type": action.get("type"),
                       "tag": action.get("tag")})

        with ctx.step("Assert no PrintNode job was created."):
            # Vacuously true on the current source: decision D-1 collapsed the
            # PrintNode branch away entirely (:119-138).
            ctx.check("no printnode.printjob row and no new ir.attachment "
                      "beyond the merged one",
                      {"printjob_delta": 0, "attachment_delta": 1},
                      {"printjob_delta": _printjob_count(rpc) - jobs_before,
                       "attachment_delta":
                           _attachment_count(rpc)
                           - total_attachments_before})

        with ctx.step("Re-run with only one receipt selected and assert a "
                      "single-page (or single-slip) PDF is produced without "
                      "error."):
            single_action = print_packing_slips(rpc, [receipt_a])
            single_id = attachment_id_from_action(single_action)
            single_data = (fetch_web_content(ctx, single_id) if single_id
                           else b"")
            ctx.check("one receipt yields its own act_url, a one-page PDF and "
                      "exactly that slip",
                      {"has_attachment": True, "pages": 1,
                       "carries_marker_a": True, "carries_marker_b": False,
                       "target": "self"},
                      {"has_attachment": bool(single_id),
                       "pages": pdf_page_count(single_data),
                       "carries_marker_a":
                           _marker_offset(single_data, marker_a) is not None,
                       "carries_marker_b":
                           _marker_offset(single_data, marker_b) is not None,
                       "target": single_action.get("target")})
    finally:
        # The merged attachment cannot be namespaced (its name is the literal
        # 'Packing Slip' and it has no res_id), so only this run's delta is
        # removed. Never raises.
        try:
            removed = sweep_new_attachments(rpc, attachments_before)
            ctx.log(f"removed merged-print attachments: {removed}")
        except Exception:  # noqa: BLE001
            pass
        try:
            _drop_pickings(rpc, picking_ids)
            sweep_wf015(rpc)
        except Exception:  # noqa: BLE001
            pass


# ===========================================================================
# TC210 — PrintNode (blocked stub: offline half asserted, then BLOCKED)
# ===========================================================================
@test_case(
    id="TEST-WF015-TC210",
    name="With PrintNode enabled for company, user and group, the merged PDF "
         "is sent to the printer",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module=MODULE, priority="P2", kind="API", order=15210,
    description="Offline half only: the three enabling conditions are probed "
                "and recorded, and the merged print is shown to return the "
                "DOWNLOAD action unconditionally on the current source "
                "(decision D-1 collapsed the PrintNode branch away). The "
                "print branch itself needs PrintNode hardware, so the case "
                "reports BLOCKED — convention rule 4.",
    traceability=trace("DATAONE-TC210"))
def test_tc210(ctx):
    rpc = ctx.adapter.rpc
    require_print_packing_slip(ctx)
    open_namespace(ctx)
    picking_ids = []
    attachments_before = set()
    try:
        with ctx.step("Log in as TD-U-03 and confirm all three enabling "
                      "conditions read True."):
            ctx.log(_role_note("TD-U-03"))
            # Probed, never written: enabling PrintNode on a real company or
            # user would be a master-data change AND would arm an outbound
            # integration (convention rules 3 and 4).
            probe = {
                "model printnode.printer":
                    rpc.model_exists("printnode.printer"),
                "model printnode.printjob":
                    rpc.model_exists(PRINTNODE_JOB_MODEL),
                "res.company.printnode_enabled":
                    rpc.field_exists("res.company", "printnode_enabled"),
                "res.users.printnode_enabled":
                    rpc.field_exists("res.users", "printnode_enabled"),
            }
            for xmlid in PRINTNODE_GROUP_XMLIDS:
                probe[xmlid] = bool(rpc.ref(xmlid))
            ctx.log(f"PrintNode capability probe on {ctx.env.key} "
                    f"(db={ctx.env.db}): {probe!r}")
            ctx.log(
                "step 10 of this case (remove the user from "
                f"{XMLID_PRINTNODE_GROUP_USER} and re-run) is NOT performable "
                "even offline: printnode_base/security/security.xml:24-26 "
                "adds that group to base.group_user.implied_ids, so every "
                "internal user is implicitly a PrintNode user and the "
                "membership cannot simply be removed.")

        with ctx.step("Select the three receipts and run Action → Print "
                      "Attached Packing Slip."):
            partner_id = ensure_vendor(rpc, "TD-PA-03")
            picking_type_id = default_picking_type(rpc, "incoming")
            attachments_before = print_attachment_ids(rpc)
            markers = []
            selection = []
            for index, label in enumerate(("TC210A", "TC210B", "TC210C")):
                marker = f"{fixture_token()} TC210 SLIP {index}"
                picking_id = _make_receipt(ctx, partner_id, picking_type_id,
                                           label)
                attach_packing_slip(rpc, picking_id,
                                    f"{sku('tc210')}-slip-{index}.pdf",
                                    tiny_pdf_b64(marker))
                markers.append(marker)
                selection.append(picking_id)
            picking_ids += selection
            jobs_before = _printjob_count(rpc)
            action = print_packing_slips(rpc, selection)
            attachment_id = attachment_id_from_action(action)
            # The offline half of the case. require_print_packing_slip ->
            # require_printnode_off has already asserted that at least one
            # printnode_enabled flag is False, so BOTH revisions must land on
            # the download branch here: the UAT source has only that branch
            # left (DPS/models/stock_picking.py:119-138), and the installed
            # v17 revision reaches it through the negative leg of the
            # three-condition test (main:.../stock_picking.py:119-127). The
            # claim asserted is therefore "download WITH PrintNode off", not
            # "download unconditionally".
            ctx.check("with PrintNode disabled the merged print returns the "
                      "DOWNLOAD action and creates no PrintNode job",
                      {"action": {"type": "ir.actions.act_url",
                                  "url": f"/web/content/{attachment_id}"
                                         "?download=true",
                                  "target": "self"},
                       "printjob_delta": 0},
                      {"action": action,
                       "printjob_delta":
                           _printjob_count(rpc) - jobs_before})

        with ctx.step("Assert attachment.dpc_print() was called exactly once, "
                      "with the merged attachment."):
            ctx.blocked(TC210_BLOCKED_REASON)
    finally:
        try:
            removed = sweep_new_attachments(rpc, attachments_before)
            ctx.log(f"removed merged-print attachments: {removed}")
        except Exception:  # noqa: BLE001
            pass
        try:
            _drop_pickings(rpc, picking_ids)
            sweep_wf015(rpc)
        except Exception:  # noqa: BLE001
            pass


# ===========================================================================
# TC211 — nothing attached
# ===========================================================================
@test_case(
    id="TEST-WF015-TC211",
    name="Printing with nothing attached returns the exact \"no attachments\" "
         "message",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module=MODULE, priority="P3", kind="API", order=15211,
    description="Two slipless receipts return exactly the "
                "display_notification dict of stock_picking.py:140-147 with "
                "the message 'There are no attachments to print.', create no "
                "ir.attachment and produce no URL and no print job; adding a "
                "third receipt that does carry a slip merges only that one, "
                "silently, with no warning of any kind.",
    traceability=trace("DATAONE-TC211"))
def test_tc211(ctx):
    rpc = ctx.adapter.rpc
    require_print_packing_slip(ctx)
    open_namespace(ctx)
    picking_ids = []
    attachments_before = set()
    try:
        with ctx.step("Log in as TD-U-03."):
            ctx.log(_role_note("TD-U-03"))
            partner_id = ensure_vendor(rpc, "TD-PA-03")
            picking_type_id = default_picking_type(rpc, "incoming")
            attachments_before = print_attachment_ids(rpc)

        with ctx.step("Select the two receipts with no attachments."):
            empty_one = _make_receipt(ctx, partner_id, picking_type_id,
                                      "TC211E1")
            empty_two = _make_receipt(ctx, partner_id, picking_type_id,
                                      "TC211E2")
            marker = f"{fixture_token()} TC211 SLIP"
            with_slip = _make_receipt(ctx, partner_id, picking_type_id,
                                      "TC211S")
            attach_packing_slip(rpc, with_slip, f"{sku('tc211')}-slip.pdf",
                                tiny_pdf_b64(marker))
            picking_ids += [empty_one, empty_two, with_slip]
            empties = [empty_one, empty_two]
            jobs_before = _printjob_count(rpc)
            total_attachments_before = _attachment_count(rpc)
            named_attachments_before = len(print_attachment_ids(rpc))
            ctx.check("the two selected receipts carry no packing slip and "
                      "the third does",
                      {"empty_payloads": [False, False],
                       "third_has_slip": True},
                      {"empty_payloads":
                           [bool(packing_slip_row(rpc, pid)[
                               "packing_slip_attachment"]) for pid in empties],
                       "third_has_slip":
                           bool(packing_slip_row(rpc, with_slip)[
                               "packing_slip_attachment"])})

        with ctx.step("Run Action → Print Attached Packing Slip."):
            action = print_packing_slips(rpc, empties)
            ctx.check_true("the public method returned a dict",
                           isinstance(action, dict),
                           actual_desc=f"{type(action).__name__}: {action!r}")

        with ctx.step("Assert the exact message There are no attachments to "
                      "print. is shown."):
            # DPS/models/stock_picking.py:140-147 — the whole dict, with the
            # message WITH its trailing period (:144).
            ctx.check("the empty branch returns exactly the "
                      "display_notification of stock_picking.py:140-147",
                      {"type": "ir.actions.client",
                       "tag": "display_notification",
                       "params": {"message": MSG_NO_ATTACHMENTS,
                                  "type": "info",
                                  "sticky": False}},
                      action)

        with ctx.step("Assert no ir.attachment was created."):
            # streams_to_merge stays empty, so the create at :110 never runs.
            ctx.check("no 'Packing Slip' attachment and no ir.attachment row "
                      "at all was added",
                      {"named_delta": 0, "total_delta": 0},
                      {"named_delta": len(print_attachment_ids(rpc))
                                      - named_attachments_before,
                       "total_delta": _attachment_count(rpc)
                                      - total_attachments_before})

        with ctx.step("Assert no download URL and no print job were "
                      "produced."):
            ctx.check("the notification carries no url and no PrintNode job "
                      "was created",
                      {"has_url": False, "attachment_from_action": None,
                       "printjob_delta": 0},
                      {"has_url": "url" in action,
                       "attachment_from_action":
                           attachment_id_from_action(action),
                       "printjob_delta":
                           _printjob_count(rpc) - jobs_before})

        with ctx.step("Select the two empty receipts plus the one carrying a "
                      "slip."):
            mixed = [empty_one, with_slip, empty_two]
            named_before_mixed = print_attachment_ids(rpc)
            ctx.check("the mixed selection holds three receipts, exactly one "
                      "of which carries a slip",
                      {"selected": 3, "with_slip": 1},
                      {"selected": len(mixed),
                       "with_slip": sum(
                           1 for pid in mixed
                           if packing_slip_row(rpc, pid)[
                               "packing_slip_attachment"])})

        with ctx.step("Run the action again."):
            mixed_action = print_packing_slips(rpc, mixed)
            ctx.check_true("the public method returned a dict",
                           isinstance(mixed_action, dict),
                           actual_desc=f"{type(mixed_action).__name__}: "
                                       f"{mixed_action!r}")

        with ctx.step("Assert a merged PDF is produced, containing only the "
                      "one available slip, and record whether any warning "
                      "about the two empty receipts is shown."):
            mixed_id = attachment_id_from_action(mixed_action)
            mixed_data = fetch_web_content(ctx, mixed_id) if mixed_id else b""
            created = sorted(print_attachment_ids(rpc) - named_before_mixed)
            ctx.check("exactly one attachment, a one-page PDF carrying that "
                      "slip, delivered as the bare act_url — NO warning of "
                      "any kind about the two slipless receipts",
                      {"created": 1,
                       "pages": 1,
                       "carries_the_slip": True,
                       "action": {"type": "ir.actions.act_url",
                                  "url": f"/web/content/{mixed_id}"
                                         "?download=true",
                                  "target": "self"}},
                      {"created": len(created),
                       "pages": pdf_page_count(mixed_data),
                       "carries_the_slip":
                           _marker_offset(mixed_data, marker) is not None,
                       "action": mixed_action})

        with ctx.step("Record step 9's behaviour as the documented v17 "
                      "baseline."):
            # Documentation, not an assertion — the workbook says "record".
            ctx.log(
                "DOCUMENTED v17 BASELINE: "
                "action_print_attached_packing_slip opens with "
                "self.filtered(lambda r: r.packing_slip_attachment) "
                "(DPS/models/stock_picking.py:89), which drops slipless "
                "receipts SILENTLY. A mixed selection therefore merges only "
                "the available slips and returns the plain act_url — there "
                "is no warning, no notification and no counter telling the "
                "clerk that 2 of the 3 selected receipts contributed "
                "nothing. Operationally this matters: a clerk selecting a "
                "day's receipts will routinely include some with no slip. "
                "Whether they should be told is a business decision, "
                "recorded here rather than assumed.")
    finally:
        try:
            removed = sweep_new_attachments(rpc, attachments_before)
            ctx.log(f"removed merged-print attachments: {removed}")
        except Exception:  # noqa: BLE001
            pass
        try:
            _drop_pickings(rpc, picking_ids)
            sweep_wf015(rpc)
        except Exception:  # noqa: BLE001
            pass
