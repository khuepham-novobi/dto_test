"""DATAONE-WF-024 — the RMA field gate and the print branch: TC186, TC187.

Both cases turn on one Char field, ``stock.picking.rma_number``
(``stock_picking_auto_create_lot/models/stock_picking.py:9``). TC186 is the
view-level requirement it gates; TC187 is the report branch it selects.

TC186 — the requirement is a view modifier and nothing else
-----------------------------------------------------------
``views/stock_picking.xml:11-14`` inserts both fields after
``//field[@name='picking_type_id']``::

    <field name="reason_for_return" invisible="rma_number == False" required="True"/>
    <field name="return_notes"      invisible="rma_number == False" required="True"/>

Those two attributes are the entire mechanism:

* they survive into the composed arch untouched — ``_modifiers_from_model``
  only ever ADDS model-level ``readonly``/``required`` and is not even
  called in either tree (v17 ``odoo/addons/base/models/ir_ui_view.py:1300-1304``,
  v19 ``:1774-1778``; a full-tree grep of v17 finds the definition and no
  call site), so what the module wrote is what the client evaluates;
* neither model field carries ``required=``
  (``models/stock_picking.py:11``, ``:35``), there is no ``@api.constrains``
  and no ``_sql_constraints`` anywhere in the module, so the ORM has nothing
  to refuse with. That is WF-024 E2 and it is what workbook step 11 asserts
  positively.

The 19-code vocabulary is declared three times, byte-identically:
``models/stock_picking.py:13-31``,
``dto_purchase_stock/models/quality_check.py:8-26`` and
``dto_purchase_stock/wizard/quality_check_wizard.py:8-26``. Step 13 is the
drift detector across all three and is read over RPC — never by grepping
``DTO-Odoo``, which now holds the **v19** port and would be the wrong tree
during a v17 run.

TC187 — the branch, then the document
-------------------------------------
``models/stock_picking.py:37-40``::

    def do_print_picking(self):
        if self.rma_number:
            return self.env.ref('stock_picking_auto_create_lot.action_report_return').report_action(self)
        return self.env.ref('stock.action_report_picking').report_action(self)

``report_action()`` returns a plain dict with **no id and no xmlid key**
(v17 ``odoo/addons/base/models/ir_actions_report.py:1049-1057``, v19
``:1171-1179`` — identical bodies), so both branches are discriminated on
``report_name`` / ``report_file`` / ``name`` / ``report_type`` / ``type``
read off the two ``ir.actions.report`` records
(``report/stock_report_views.xml:4-13`` and core
``stock/report/stock_report_views.xml:4-13``).

The same method has an **admin trap**, identical in both versions (v17
``:1060``, v19 ``:1182``): an admin session on a company with no
``external_report_layout_id`` receives
``web.action_base_document_layout_configurator`` — an ``act_window`` — rather
than the report. Every print call below therefore runs through the
workbook's own TD-U-03 session, which is not an admin.

The rendered half goes through ``/report/html/<name>/<id>``, declared
identically in both versions (``web/controllers/report.py:23-40``, v19
``:24-27``) and dispatching to ``_render_qweb_html``, so it needs no
wkhtmltopdf. What it proves, against
``report/report_stockpicking_operations.xml``:

* ``:71``     — ``<h1 t-field="o.rma_number" class="mt0"/>`` (step 5);
* ``:86-91``  — the reason and the notes, inside ``t-if="o.reason_for_return"``
  (step 6);
* ``:9``      — ``<t t-set="address" t-value="None"/>`` fed to
  ``web.external_layout``, whose ``web.address_layout`` renders the address
  block only ``t-if="address"`` (v17 ``web/views/report_templates.xml:283,296``,
  v19 ``:280,297``), and which ``external_layout_standard`` (v17 ``:491``)
  t-calls at v17 ``:536`` — step 7;
* ``:95``,``:114-116``,``:159-170`` — ``has_barcode`` and the Product Barcode
  column; ``:144-150`` — the destination-package reference in the "To" cell
  (step 8);
* ``:96``,``:111-113``,``:152-158`` — ``has_serial_number``, whose ``t-set``
  carries ``groups="stock.group_production_lot"``. QWeb compiles a ``groups``
  attribute to ``if self.user_has_groups(...)`` (v17
  ``odoo/addons/base/models/ir_qweb.py:1843-1855``) and treats an unknown
  name as ``None`` (``:1049-1057`` docstring), so for a user outside the
  group the whole serial column simply disappears — step 9.

Deliberately MANUAL, exactly as the workbook's "Wave 1 + Manual (split)"
says: the byte-level ``Content-Disposition`` filename (step 4), PDF text
extraction and the measured page size of the produced PDF (step 13). All
three need wkhtmltopdf on the Odoo host; what is asserted instead is the
``print_report_name`` expression verbatim, the name it computes from the
live record, and the paperformat the report resolves to.

Fixtures and safety
-------------------
Both cases build their own RMA picking — convention rule 5 forbids depending
on TC184's — by returning a namespaced delivery through the real wizard, so
``_create_return`` (``wizard/stock_picking_return.py:21-25``) does the
``rma_number`` stamping the workbook's preconditions describe. The source
delivery carries **no** ``sale_id``, so ``dto_sale_stock``'s mail automation
filters it out at ``data/base_automation_data.xml:29``
(``records.filtered(lambda r: r.picking_type_code == 'outgoing' and
r.sale_id)``) and nothing outbound can fire; ``require_mail_offline`` is
therefore not needed here, unlike TC189.

``lot_name`` is written on the RMA's move lines to give step 9 something to
gate: it is a plain Char with no constraint and is NOT one of the ``write()``
triggers, so it touches no quant (v17 ``stock/models/stock_move_line.py:51``,
``:424-450``). ``result_package_id`` IS a trigger, but its quant
synchronisation short-circuits for a non-internal source location —
``_synchronize_quant(..., action="reserved")`` is a no-op when
``_should_bypass_reservation`` holds (``:683-684``), which it does for the
Customers location the return draws from.

EXPECTED v17 OUTCOME
--------------------
* **TC186 — BLOCKED**, with every observable assertion PASSED first. Steps
  1-3 and 6-13 are asserted and expected to pass; workbook steps 4-5 ("the
  save is refused with the standard required-field error") describe the web
  client evaluating ``required="True"``, which no RPC path can observe and
  which the ORM does not reproduce. The final ``ctx.blocked`` names the
  missing ``@api.constrains`` and the HttpCase tour that would prove the
  refusal, rather than claiming a refusal that was never seen.
* **TC187 — PASS.**

EXPECTED v19 OUTCOME
--------------------
* **TC186 — same as v17**, unless the taxonomy drifted (step 13) or the core
  form anchors moved (steps 2-3).
* **TC187 — FAIL/ERROR at step 5**, and that failure is the finding. The
  forked template is a full fork of ``stock.report_picking_operations`` and
  references five things v19 removed: ``move_ids_without_package``
  (``:94``; v17 ``stock/models/stock_picking.py:466``),
  ``move_line_ids_without_package`` (``:121``; v17 ``:492``),
  ``package_level_ids`` (``:174``, ``:184``; v17 ``:523``),
  ``stock.move.product_packaging_id`` / ``product_packaging_qty``
  (``:129-135``; v17 ``stock/models/stock_move.py:182,183``) and
  ``stock.quant.package``, renamed to ``stock.package`` (v19
  ``stock/models/stock_package.py:18``). QWeb templates are not validated at
  install, so the module installs and the report is a runtime bomb. The
  action-selection half (steps 2-3, 10-11, 13) still passes. Not softened.
"""
from __future__ import annotations

import re

from adapters.base import OdooRPCError
from framework.registry import test_case
from tests.wf024.common import (FORM_ANCHOR_REASON, REASON_CODES,
                                archive_qa_users,
                                REASON_SELECTION, REPORT_ACTION_KEYS,
                                REPORT_RMA_ACTION,
                                REPORT_RMA_PRINT_REPORT_NAME, REPORT_RMA_XMLID,
                                REPORT_STD_ACTION, REPORT_STD_XMLID,
                                REQUIRED_TRUE_SPELLINGS, RMA_FIELD_MODIFIERS,
                                SERIAL_GROUP, STOCK_USER_GROUP,
                                TAXONOMY_FIELD, TAXONOMY_MODELS, WORKFLOW,
                                WORKFLOW_NAME, arch_field_attrs,
                                arch_field_order, company_paperformat,
                                confirm_return, customer_location,
                                ensure_user_in_groups, expect_error,
                                expected_report_filename, fixture_token,
                                m2o_id, make_delivery, make_product,
                                open_namespace, open_return_wizard,
                                package_model, picking_type, print_action,
                                report_html, report_row, require_quality_taxonomy,
                                require_report_layout, require_rma_module,
                                require_rma_sequence, require_vendor_narration,
                                return_of, rpc_as, rma_snapshot, safe_sweep,
                                selection_of, session_for,
                                set_return_quantities, tag, taxonomy_selections,
                                trace, warehouse_stock_location)

#: ``stock/security/stock_security.xml`` — v17 ``:10``, v19 ``:26``. Not in
#: common.py: only this file needs it, and only because the forked template
#: puts the From/To cells (which carry the package references, ``:138-151``)
#: behind it.
MULTI_LOCATION_GROUP = "stock.group_stock_multi_locations"

#: The reason code TC186 step 7 and TC187's precondition select. 913's label
#: is the one that literally asks for notes, which is why it is the natural
#: pairing for a case that also writes notes.
FIXTURE_REASON_CODE = "913"
FIXTURE_REASON_LABEL = dict(REASON_SELECTION)[FIXTURE_REASON_CODE]

_H1_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.S | re.I)
_TAG_RE = re.compile(r"<[^>]+>")


# =====================================================================
# Local helpers — none of these exist in tests/wf024/common.py
# =====================================================================
def _field_attrs(arch: str, name: str) -> dict:
    """The first ``<field name=...>`` node's attributes, or ``{}``."""
    nodes = arch_field_attrs(arch, name)
    return nodes[0] if nodes else {}


def _arch_as(rpc) -> str:
    """The composed ``stock.picking`` form arch, as a given session sees it.

    ``form_arch``/``picking_form_arch`` always read through
    ``ctx.adapter.rpc`` (the platform's own user). Both workbook cases open
    the picking *as TD-U-03*, and group-restricted nodes are stripped per
    session, so the arch is fetched through that session instead.
    ``get_view`` is the same public entry point in both versions
    (v17 ``ir_ui_view.py:2613``, v19 ``:3138``).
    """
    return rpc.call("stock.picking", "get_view", view_type="form")["arch"]


def _qa_barcode() -> str:
    """A deterministic barcode in the platform's reserved 9001xxxxxx range.

    Derived from this execution's fixture token (``framework/qa_fixtures.py``
    header: "QA barcodes live in the 9001xxxxxx range"), so it is stable for
    the whole run and namespaced away from live product barcodes.
    """
    suffix = fixture_token().split("-")[-1]
    return "9001{:06d}".format(int(suffix, 16) % 1000000)


def _rma_picking(ctx, product_id, qty=2.0, label="RMA-SRC"):
    """Build a genuine RMA: deliver, return through the wizard, read it back.

    Returns ``(delivery_id, rma_row)``. BLOCKS — never fails — when the
    target's return flow produces no ``rma_number``, because an RMA picking
    is this case's *precondition*, not its assertion (numbering is TC184).
    """
    rpc = ctx.adapter.rpc
    delivery_id = make_delivery(ctx, [(product_id, qty)], label=label)
    wizard_id = open_return_wizard(rpc, delivery_id)
    applied = set_return_quantities(rpc, wizard_id, {product_id: qty})
    if not applied:
        ctx.blocked(
            "The stock.return.picking wizard listed no line for the fixture "
            f"product on {ctx.env.key} (db={ctx.env.db}), so no quantity "
            "could be set and no return can be created. "
            "product_return_moves is a stored compute on picking_id "
            "(v17 stock/wizard/stock_picking_return.py:37, v19 :103).")
    confirm_return(ctx, wizard_id)
    row = return_of(rpc, delivery_id)
    if not row:
        ctx.blocked(
            f"No stock.picking with return_id={delivery_id} exists after the "
            "wizard confirmed on "
            f"{ctx.env.key} (db={ctx.env.db}). Both versions set return_id in "
            "_prepare_picking_default_values (v17 "
            "stock/wizard/stock_picking_return.py:117, v19 :154), so the "
            "return was not created.")
    if not row.get("rma_number"):
        ctx.blocked(
            f"The return picking {row['name']!r} carries no rma_number on "
            f"{ctx.env.key} (db={ctx.env.db}). "
            "stock_picking_auto_create_lot/wizard/stock_picking_return.py:21-25 "
            "overrides _create_return (the v19 name); v17 core calls "
            "_create_returns (stock/wizard/stock_picking_return.py:129), so a "
            "v19-shaped fork on a v17 core stamps nothing. TC186 and TC187 "
            "both need an RMA picking as a PRECONDITION — the numbering "
            "itself is TEST-WF024-TC184's assertion, not this one's.")
    return delivery_id, row


def _ordinary_picking(ctx, product_id, assign=False) -> int:
    """A non-RMA outgoing picking: same shape, ``rma_number`` never set."""
    rpc = ctx.adapter.rpc
    picking_id = make_delivery(ctx, [(product_id, 1.0)], label="PLAIN",
                               validate=False)
    if assign:
        rpc.call("stock.picking", "action_confirm", [picking_id])
        try:
            rpc.call("stock.picking", "action_assign", [picking_id])
        except OdooRPCError as exc:
            ctx.log(f"[warn] action_assign on picking {picking_id}: {exc}")
    return picking_id


def _render(ctx, report_name: str, res_id: int, opener):
    """``/report/html/<name>/<id>`` → ``(ok, html_or_error)``.

    A failing render is turned into a message rather than an exception so the
    caller can report it through ``ctx.check`` (expected vs actual) instead of
    erroring out with a bare traceback. On v19 the RMA template is expected
    to fail here — see the module docstring.
    """
    try:
        return True, report_html(ctx, report_name, res_id, opener=opener)
    except Exception as exc:                                # noqa: BLE001
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")[:600]
        except Exception:                                   # noqa: BLE001
            body = ""
        return False, f"{type(exc).__name__}: {exc} {body}".strip()


def _headings(html: str) -> list:
    """The stripped text of every ``<h1>`` in a rendered report."""
    return [_TAG_RE.sub("", found).strip() for found in _H1_RE.findall(html)]


# =====================================================================
# TC186
# =====================================================================
@test_case(
    id="TEST-WF024-TC186",
    name="Reason for Return and Return Notes are required on an RMA picking "
         "and absent on an ordinary one",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="stock_picking_auto_create_lot",
    priority="P1", kind="API", order=24186,
    description="Both fields are scoped to RMA pickings by one invisible "
                "expression, carry a view-level required modifier, offer "
                "exactly the 19 codes 901-919, are bypassable by the ORM, and "
                "share their vocabulary with the quality-check taxonomy.",
    traceability=trace("DATAONE-TC186"))
def test_tc186(ctx):
    require_rma_module(ctx)
    require_rma_sequence(ctx)
    require_vendor_narration(ctx)
    rpc = ctx.adapter.rpc
    open_namespace(ctx)
    orm_picking_id = None
    try:
        # TD-U-03 = dto_stock (Inventory User). Everything below is read and
        # written through THAT session, not the platform's own user, because
        # the workbook's step 1 says so and because group-restricted arch
        # nodes are stripped per session.
        _uid, login = ensure_user_in_groups(ctx, "tc186user", [STOCK_USER_GROUP])
        rpc_user = rpc_as(ctx.env, login)

        product_id = make_product(ctx, "TC186-ITEM")
        _delivery_id, rma_row = _rma_picking(ctx, product_id, label="TC186")
        rma_id = rma_row["id"]
        plain_id = _ordinary_picking(ctx, product_id)

        with ctx.step("Log in as TD-U-03 and open the RMA picking"):
            arch = _arch_as(rpc_user)
            rma = rma_snapshot(rpc_user, rma_id)
            ctx.log(f"TD-U-03 session = {login!r}")
            ctx.check("the RMA picking opens with an rma_number and both "
                      "fields still empty (the workbook's precondition)",
                      expected={"rma_number": True,
                                "reason_for_return": False,
                                "return_notes": False},
                      actual={"rma_number": bool(rma["rma_number"]),
                              "reason_for_return": rma["reason_for_return"],
                              "return_notes": rma["return_notes"]})

        with ctx.step("Assert Reason for Return and Return Notes are both "
                      "visible"):
            # One mismatch dict for both fields, so a failure reports every
            # difference at once (convention: mismatch dicts, not loops).
            order = arch_field_order(arch)
            attrs = {name: _field_attrs(arch, name)
                     for name in ("reason_for_return", "return_notes")}
            anchor = (order.index(FORM_ANCHOR_REASON)
                      if FORM_ANCHOR_REASON in order else -1)
            visibility = {}
            for name in ("reason_for_return", "return_notes"):
                want = RMA_FIELD_MODIFIERS[name]["invisible"]
                if not attrs[name]:
                    visibility[name] = "absent from the composed form arch"
                elif attrs[name].get("invisible") != want:
                    visibility[name] = {"invisible": attrs[name].get("invisible"),
                                        "expected": want}
                elif anchor < 0 or name not in order or order.index(name) < anchor:
                    visibility[name] = (
                        f"not placed after {FORM_ANCHOR_REASON} "
                        f"(index {order.index(name) if name in order else None} "
                        f"vs anchor {anchor})")
            ctx.check("both fields sit after picking_type_id and are gated by "
                      "exactly one expression, invisible=\"rma_number == "
                      "False\" (views/stock_picking.xml:11-13)",
                      expected={}, actual=visibility)
            ctx.check("that gate evaluates to VISIBLE on this picking, "
                      "because rma_number is set", expected=False,
                      actual=(rma["rma_number"] is False
                              or rma["rma_number"] is None
                              or rma["rma_number"] == ""))

        with ctx.step("Assert both are marked required"):
            spellings = {name: _field_attrs(arch, name).get("required")
                         for name in ("reason_for_return", "return_notes")}
            # The source writes the literal string "True"
            # (views/stock_picking.xml:12-13); the v19 migration item wants it
            # normalised to "1". Both spell the SAME modifier, so either is
            # accepted and the delivered spelling is recorded.
            not_required = {name: value for name, value in spellings.items()
                            if value not in REQUIRED_TRUE_SPELLINGS}
            ctx.check("both fields carry a truthy required= modifier in the "
                      "delivered arch", expected={}, actual=not_required)
            ctx.log(f"required= as delivered on {ctx.env.key}: {spellings} "
                    f"(source literal: \"True\")")

        with ctx.step("Attempt to save the picking with both empty"):
            # Over RPC this is the ORM write the web client never issues,
            # because the client refuses the save first. Recorded, not
            # asserted as the workbook's refusal — see step 5 and the final
            # ctx.blocked.
            raised, message = expect_error(
                rpc_user.write, "stock.picking", [rma_id],
                {"reason_for_return": False, "return_notes": False})
            ctx.log(f"ORM write of both fields empty -> raised={raised} "
                    f"message={message!r}")
            still = rma_snapshot(rpc_user, rma_id)
            ctx.log("after the empty write: reason_for_return="
                    f"{still['reason_for_return']!r} return_notes="
                    f"{still['return_notes']!r}")

        with ctx.step("Assert the save is refused with the standard "
                      "required-field error on both fields"):
            # What IS observable over RPC: the two fields declare nothing at
            # model level for the ORM to refuse with
            # (models/stock_picking.py:11,35 carry no required=). The refusal
            # the workbook describes lives entirely in the web client's
            # evaluation of required="True" — named in the final ctx.blocked.
            declared = rpc.call("stock.picking", "fields_get",
                                ["reason_for_return", "return_notes"],
                                attributes=["required", "store"])
            model_required = {name: bool((declared.get(name) or {})
                                         .get("required"))
                              for name in ("reason_for_return", "return_notes")}
            ctx.check("neither field is required at MODEL level, so the ORM "
                      "has no required-field error to raise "
                      "(models/stock_picking.py:11,35)",
                      expected={"reason_for_return": False,
                                "return_notes": False},
                      actual=model_required)

        with ctx.step("Open the Reason for Return dropdown and assert it "
                      "offers exactly 19 values, 901 through 919"):
            selection = selection_of(rpc_user, "stock.picking", TAXONOMY_FIELD)
            ctx.check("exactly 19 codes, 901 through 919",
                      expected=REASON_CODES,
                      actual=[pair[0] for pair in selection])
            ctx.check("the labels are byte-identical to "
                      "models/stock_picking.py:13-31, including the U+2013 EN "
                      "DASH in 902",
                      expected=[list(pair) for pair in REASON_SELECTION],
                      actual=[list(pair) for pair in selection])

        with ctx.step("Select one code, type a note, save, and assert both "
                      "values persist"):
            notes = tag("return notes typed by TD-U-03")
            rpc_user.write("stock.picking", [rma_id],
                           {"reason_for_return": FIXTURE_REASON_CODE,
                            "return_notes": notes})
            saved = rma_snapshot(rpc_user, rma_id)
            ctx.check("both values persist on the RMA picking",
                      expected={"reason_for_return": FIXTURE_REASON_CODE,
                                "return_notes": notes},
                      actual={"reason_for_return": saved["reason_for_return"],
                              "return_notes": saved["return_notes"]})

        with ctx.step("Open the ordinary picking"):
            plain = rma_snapshot(rpc_user, plain_id)
            ctx.check("the ordinary picking carries no rma_number",
                      expected=False, actual=bool(plain["rma_number"]))

        with ctx.step("Assert Reason for Return and Return Notes are not "
                      "visible"):
            # The arch is per-view, not per-record: the SAME expression that
            # made the fields visible on the RMA hides them here, because
            # rma_number is False. Both halves are asserted together.
            hidden = {}
            for name in ("reason_for_return", "return_notes"):
                want = RMA_FIELD_MODIFIERS[name]["invisible"]
                got = _field_attrs(arch, name).get("invisible")
                if got != want:
                    hidden[name] = {"invisible": got, "expected": want}
            ctx.check("both fields are gated by invisible=\"rma_number == "
                      "False\", which evaluates TRUE — hidden — on a picking "
                      "with no rma_number", expected={}, actual=hidden)
            ctx.check("the gate's operand on this picking", expected=False,
                      actual=bool(plain["rma_number"]))

        with ctx.step("Save the ordinary picking with no reason and assert "
                      "the save succeeds — the requirement is scoped to RMAs"):
            written = rpc_user.write("stock.picking", [plain_id],
                                     {"origin": tag("PLAIN-SAVED")})
            after = rma_snapshot(rpc_user, plain_id)
            ctx.check("the ordinary picking saves with no reason and no notes",
                      expected={"written": True,
                                "reason_for_return": False,
                                "return_notes": False},
                      actual={"written": bool(written),
                              "reason_for_return": after["reason_for_return"],
                              "return_notes": after["return_notes"]})

        with ctx.step("Through the ORM, create() a picking with an rma_number "
                      "and no reason and no notes; assert the create succeeds "
                      "— the requirement is view-level only, with no "
                      "@api.constrains"):
            ptype = picking_type(rpc, "incoming")
            src_id = (m2o_id(ptype["default_location_src_id"])
                      or customer_location(rpc)
                      or warehouse_stock_location(rpc))
            dest_id = (m2o_id(ptype["default_location_dest_id"])
                       or warehouse_stock_location(rpc))
            orm_picking_id = rpc.create("stock.picking", {
                "picking_type_id": ptype["id"],
                "partner_id": m2o_id(rma["partner_id"]),
                "location_id": src_id,
                "location_dest_id": dest_id,
                "origin": tag("ORM-RMA"),
                "rma_number": tag("ORM"),
            })
            created = rma_snapshot(rpc, orm_picking_id)
            ctx.check("create() succeeds and yields an RMA with an empty "
                      "reason and empty notes (WF-024 E2)",
                      expected={"created": True,
                                "rma_number": tag("ORM"),
                                "reason_for_return": False,
                                "return_notes": False},
                      actual={"created": bool(orm_picking_id),
                              "rma_number": created["rma_number"],
                              "reason_for_return": created["reason_for_return"],
                              "return_notes": created["return_notes"]})

        with ctx.step("Record step 11 as the documented gap (WF-024 E2): an "
                      "API or import write produces an RMA with no reason, "
                      "which then prints an RMA document with an empty reason "
                      "column"):
            ctx.log(
                "WF-024 E2 — the requirement is a view modifier only: "
                "views/stock_picking.xml:12-13 writes required=\"True\", "
                "models/stock_picking.py:11,35 declare no required=, and the "
                "module contains no @api.constrains and no _sql_constraints. "
                f"Picking {created['name']!r} now carries rma_number "
                f"{created['rma_number']!r} with reason_for_return=False, so "
                "report/report_stockpicking_operations.xml:86 "
                "(t-if=\"o.reason_for_return\") renders no reason block at "
                "all on its RMA document. Any API caller, data import or "
                "server action reaches the same state.")
            # Postcondition: delete the ORM-created picking from step 11.
            try:
                rpc.unlink("stock.picking", [orm_picking_id])
                orm_picking_id = None
                ctx.log("postcondition: the ORM-created picking was deleted")
            except OdooRPCError as exc:
                ctx.log(f"[warn] could not unlink the ORM-created picking: "
                        f"{exc} — the teardown sweep will retry it")

        with ctx.step("Compare the 19-value list against the copy used by the "
                      "quality-check taxonomy (F072) and assert the two lists "
                      "are identical; record any divergence"):
            # Guarded HERE rather than at the top of the test so that steps
            # 1-12 are still recorded on a database without quality_control.
            require_quality_taxonomy(ctx)
            declared_taxonomy = taxonomy_selections(ctx)
            want = [list(pair) for pair in REASON_SELECTION]
            divergence = {}
            for model in TAXONOMY_MODELS:
                got = declared_taxonomy.get(model)
                if got is None:
                    divergence[model] = (
                        f"{TAXONOMY_FIELD} is not declared on this model")
                elif got != want:
                    divergence[model] = {
                        "codes": [pair[0] for pair in got],
                        "extra": [pair for pair in got if pair not in want],
                        "missing": [pair for pair in want if pair not in got],
                    }
            ctx.check("all three copies of the 19-code taxonomy are identical "
                      "(models/stock_picking.py:13-31, "
                      "dto_purchase_stock/models/quality_check.py:8-26, "
                      "dto_purchase_stock/wizard/quality_check_wizard.py:8-26)",
                      expected={}, actual=divergence)
            ctx.log("step 13 is the drift detector: the vocabulary is "
                    "duplicated verbatim in three files, so updating two of "
                    "three leaves quality failures and RMAs sharing no "
                    "vocabulary and raises no error anywhere.")

        # Everything observable has now been asserted. Workbook steps 4-5 are
        # the one half no RPC path can reach, so the case ends BLOCKED rather
        # than claiming a refusal it never saw.
        ctx.blocked(
            "Workbook steps 4-5 are not reachable over RPC. The "
            "required-field refusal they describe is the WEB CLIENT "
            "evaluating required=\"True\" on "
            "stock_picking_auto_create_lot/views/stock_picking.xml:12-13; "
            "nothing behind it enforces the rule — models/stock_picking.py:11 "
            "and :35 declare no required=, and the module has no "
            "@api.constrains and no _sql_constraints — so the ORM accepts the "
            "empty write instead of raising the standard required-field "
            "error. Proving the refusal needs an Odoo tour test (HttpCase) "
            "driving the real form view, which is the workbook's own stated "
            "automation_approach for the modifiers. Every other step of this "
            "case (1-3, 6-13) ran and is recorded above.")
    finally:
        if orm_picking_id:
            try:
                ctx.adapter.rpc.unlink("stock.picking", [orm_picking_id])
            except Exception:                               # noqa: BLE001
                pass
        # The disposable TD-U-03 login this case created. sweep_wf024 cannot
        # reach res.users (and deliberately spares a user's partner,
        # common.py's res.partner step is guarded with user_ids = False), so
        # without this an active internal user with a known password is left
        # on the clone after every run. Archived, never unlinked: it owns
        # chatter on the fixture pickings. Cannot raise.
        archive_qa_users(ctx, ["tc186user"])
        safe_sweep(ctx)


# =====================================================================
# TC187
# =====================================================================
@test_case(
    id="TEST-WF024-TC187",
    name="do_print_picking() returns the RMA report for an RMA and the "
         "standard slip otherwise",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="stock_picking_auto_create_lot",
    priority="P1", kind="HYBRID", order=24187,
    description="do_print_picking() branches on rma_number: the RMA picking "
                "returns action_report_return, whose document carries the RMA "
                "number as an h1, the reason and notes, no layout address, "
                "barcodes, package references and a group-gated serial "
                "column; the ordinary picking returns stock.action_report_"
                "picking and its slip carries no RMA number.",
    traceability=trace("DATAONE-TC187"))
def test_tc187(ctx):
    require_rma_module(ctx)
    require_rma_sequence(ctx)
    require_vendor_narration(ctx)
    rpc = ctx.adapter.rpc
    open_namespace(ctx)
    try:
        # Two TD-U-03 sessions, identical except for stock.group_production_lot
        # — step 9's whole subject. Both carry group_stock_multi_locations,
        # which is what gates the From/To cells the package references sit in
        # (report/report_stockpicking_operations.xml:138-151).
        _uid_lot, login_lot = ensure_user_in_groups(
            ctx, "tc187lot",
            [STOCK_USER_GROUP, MULTI_LOCATION_GROUP, SERIAL_GROUP])
        _uid_nolot, login_nolot = ensure_user_in_groups(
            ctx, "tc187nolot", [STOCK_USER_GROUP, MULTI_LOCATION_GROUP])
        rpc_user = rpc_as(ctx.env, login_lot)
        # report_action()'s admin trap returns the layout configurator instead
        # of the report for an admin session on a company with no
        # external_report_layout_id (v17 ir_actions_report.py:1060, v19
        # :1182). Measured, logged, and side-stepped by printing as TD-U-03.
        require_report_layout(ctx)

        product_id = make_product(ctx, "TC187-ITEM")
        barcode = _qa_barcode()
        failed, message = expect_error(rpc.write, "product.product",
                                       [product_id], {"barcode": barcode})
        if failed:
            ctx.blocked(
                f"Could not put barcode {barcode!r} on the fixture product on "
                f"{ctx.env.key} (db={ctx.env.db}): {message}. Step 8 asserts "
                "that product barcodes render, which needs has_barcode to be "
                "true (report/report_stockpicking_operations.xml:95); "
                "product.product enforces a unique barcode, so resolve the "
                "collision in the 9001xxxxxx QA range before rerunning.")

        _delivery_id, rma_row = _rma_picking(ctx, product_id, label="TC187")
        rma_id = rma_row["id"]
        rma_number = rma_row["rma_number"]
        notes = tag("return notes for the printed RMA document")
        rpc.write("stock.picking", [rma_id],
                  {"reason_for_return": FIXTURE_REASON_CODE,
                   "return_notes": notes})

        # Give the RMA's move lines the two things the template's optional
        # columns key on. lot_name is a plain Char with no constraint and is
        # not a write() trigger (stock/models/stock_move_line.py:51, :424-450);
        # result_package_id IS a trigger, but its quant synchronisation is a
        # no-op here because the return's source is the Customers location and
        # _should_bypass_reservation holds (:683-684).
        pkg_model = package_model(rpc)
        if not pkg_model:
            ctx.blocked(
                f"Neither stock.package nor stock.quant.package exists on "
                f"{ctx.env.key} (db={ctx.env.db}); step 8 asserts that package "
                "references render "
                "(report/report_stockpicking_operations.xml:144-150).")
        package_name = tag("PKG")
        package_id = rpc.create(pkg_model, {"name": package_name})
        line_ids = rpc.search("stock.move.line", [("picking_id", "=", rma_id)])
        if not line_ids:
            ctx.blocked(
                f"The RMA picking {rma_row['name']!r} has no stock.move.line "
                f"on {ctx.env.key} (db={ctx.env.db}); steps 8 and 9 assert on "
                "the returned LINES, and the forked template's tables are "
                "gated on o.move_line_ids "
                "(report/report_stockpicking_operations.xml:94).")
        rpc.write("stock.move.line", line_ids, {"lot_name": tag("LOT")})
        rpc.write("stock.move.line", line_ids,
                  {"result_package_id": package_id})

        plain_id = _ordinary_picking(ctx, product_id, assign=True)

        rma_report = report_row(rpc, REPORT_RMA_XMLID)
        std_report = report_row(rpc, REPORT_STD_XMLID)
        if not rma_report or not std_report:
            ctx.blocked(
                f"One of the two report actions is missing on {ctx.env.key} "
                f"(db={ctx.env.db}): {REPORT_RMA_XMLID}="
                f"{bool(rma_report)}, {REPORT_STD_XMLID}={bool(std_report)}. "
                "do_print_picking (models/stock_picking.py:37-40) resolves "
                "both by xmlid, so neither branch can be asserted.")

        opener_lot = session_for(ctx.env, login_lot)
        opener_nolot = session_for(ctx.env, login_nolot)
        rma_html = ""

        with ctx.step("Log in as TD-U-03 and open the RMA picking"):
            rma = rma_snapshot(rpc_user, rma_id)
            ctx.log(f"TD-U-03 session = {login_lot!r} "
                    f"(+ {MULTI_LOCATION_GROUP}, {SERIAL_GROUP})")
            ctx.check("the RMA picking carries an rma_number, a reason code "
                      "and return notes (the workbook's precondition)",
                      expected={"rma_number": rma_number,
                                "reason_for_return": FIXTURE_REASON_CODE,
                                "return_notes": notes},
                      actual={"rma_number": rma["rma_number"],
                              "reason_for_return": rma["reason_for_return"],
                              "return_notes": rma["return_notes"]})

        with ctx.step("Call picking.do_print_picking() and capture the "
                      "returned action"):
            printed_before = rma["printed"]
            rma_action = print_action(rpc_user, rma_id)
            printed_after = rma_snapshot(rpc_user, rma_id)["printed"]
            ctx.check("do_print_picking() returned a report action, not the "
                      "layout configurator (the admin trap, "
                      "ir_actions_report.py:1060 / :1182)",
                      expected="ir.actions.report",
                      actual=(rma_action or {}).get("type"))
            # Not a workbook step: the override drops core's
            # self.write({'printed': True}) (v17 stock/models/
            # stock_picking.py:913, v19 :1176). Recorded, not asserted.
            ctx.log(f"printed flag before={printed_before} after="
                    f"{printed_after} — the override at "
                    "models/stock_picking.py:37-40 drops core's "
                    "self.write({'printed': True})")

        with ctx.step("Assert the action's report reference is "
                      "stock_picking_auto_create_lot.action_report_return"):
            # report_action() returns no id and no xmlid (v17
            # ir_actions_report.py:1049-1057, v19 :1171-1179), so the branch
            # is discriminated on the four fields it DOES carry, read off the
            # ir.actions.report record the xmlid resolves to. One dict, one
            # assertion.
            ctx.check("the action is action_report_return's",
                      expected={key: rma_report[key]
                                for key in REPORT_ACTION_KEYS},
                      actual={key: (rma_action or {}).get(key)
                              for key in REPORT_ACTION_KEYS})
            ctx.check("and that record is the one report/"
                      "stock_report_views.xml:4-13 declares — report_file "
                      "still points at core's template, which the workbook "
                      "says to record as an observation, not a failure",
                      expected=REPORT_RMA_ACTION,
                      actual={key: rma_report[key]
                              for key in REPORT_RMA_ACTION})

        with ctx.step("Print it and assert the produced file is named "
                      "RMA - <partner name> - <rma_number>"):
            partner_name = rma["partner_id"][1] if rma["partner_id"] else ""
            ctx.check("print_report_name is report/stock_report_views.xml:10 "
                      "verbatim",
                      expected=REPORT_RMA_PRINT_REPORT_NAME,
                      actual=rma_report["print_report_name"])
            # The filename is built by the HTTP controller, not by the action:
            # safe_eval(report.print_report_name, {'object': obj, 'time': time})
            # (v17 web/controllers/report.py:128-130, v19 :135-136).
            ctx.check("the name that expression computes from this record",
                      expected=f"RMA - {partner_name} - {rma_number}",
                      actual=expected_report_filename(rpc, rma_id))
            ctx.log("MANUAL half: the byte-level Content-Disposition of the "
                    "downloaded file goes through /report/download with "
                    "converter='pdf', which needs wkhtmltopdf on the Odoo "
                    "host. The workbook's 'Wave 1 + Manual (split)' puts "
                    "first-pass visual acceptance there.")

        with ctx.step("Extract the PDF text and assert the RMA number appears "
                      "as a top-level heading"):
            # /report/html renders through _render_qweb_html and needs no
            # wkhtmltopdf (web/controllers/report.py:23-40). The RMA number is
            # an <h1> at report/report_stockpicking_operations.xml:71.
            ok, rma_html = _render(ctx, rma_report["report_name"], rma_id,
                                   opener_lot)
            if not ok:
                ctx.check("the RMA report renders "
                          "(EXPECTED TO FAIL ON v19 — the forked template "
                          "references move_ids_without_package, "
                          "move_line_ids_without_package, package_level_ids, "
                          "product_packaging_id/_qty and stock.quant.package, "
                          "all removed in v19)",
                          expected="rendered", actual=rma_html)
            headings = _headings(rma_html)
            ctx.log(f"<h1> texts in the RMA document: {headings}")
            ctx.check("the RMA number is rendered as a top-level <h1> "
                      "heading (report_stockpicking_operations.xml:71)",
                      expected=rma_number,
                      actual=next((text for text in headings
                                   if rma_number and rma_number in text),
                                  headings))

        with ctx.step("Assert the reason for return and the return notes both "
                      "appear in the extracted text"):
            # t-field on a Selection renders the LABEL, not the key
            # (report_stockpicking_operations.xml:86-91).
            missing = {}
            for label, value in (("Reason for return: caption",
                                  "Reason for return:"),
                                 ("reason label", FIXTURE_REASON_LABEL),
                                 ("Return Notes: caption", "Return Notes:"),
                                 ("return notes", notes)):
                if value not in rma_html:
                    missing[label] = value
            ctx.check("the reason block and the notes are both rendered",
                      expected={}, actual=missing)

        with ctx.step("Assert no partner address block appears — "
                      "web.external_layout is called with address set to None"):
            # report_stockpicking_operations.xml:9 sets address=None; the
            # layout's web.address_layout renders the block only t-if="address"
            # (v17 web/views/report_templates.xml:283,296; v19 :280,297).
            address_markers = [marker for marker in
                               ('name="address"', 'class="address row')
                               if marker in rma_html]
            ctx.check("the external layout renders no address block",
                      expected=[], actual=address_markers)
            ctx.log("note: the fork keeps core's OWN body address divs "
                    "(div_outgoing_address / div_incoming_address, "
                    "report_stockpicking_operations.xml:20-69). They are a "
                    "different block from the layout's, are conditional on "
                    "the operation type, and are not what this step is about.")

        with ctx.step("Assert product barcodes and package references are "
                      "rendered for the returned lines"):
            missing = {}
            # has_barcode (:95) turns the Product Barcode column on (:114-116);
            # the barcode itself renders as a data:uri <img> (BarcodeConverter,
            # odoo/addons/base/models/ir_qweb_fields.py:712-742), so the column
            # and the image are what is assertable, not the digits.
            for label, value in (("Product Barcode column",
                                  'name="th_barcode"'),
                                 ("Product Barcode header", "Product Barcode"),
                                 ("rendered barcode image",
                                  "data:image/png;base64,"),
                                 ("destination package reference",
                                  package_name)):
                if value not in rma_html:
                    missing[label] = value
            ctx.check("the barcode column and the package reference both "
                      "render for the returned lines "
                      "(report_stockpicking_operations.xml:95,114-116,144-150)",
                      expected={}, actual=missing)

        with ctx.step("As a user in stock.group_production_lot, assert serial "
                      "numbers appear; as a user outside it, assert they do "
                      "not"):
            ok_nolot, nolot_html = _render(ctx, rma_report["report_name"],
                                           rma_id, opener_nolot)
            if not ok_nolot:
                ctx.check("the RMA report renders for the non-member session",
                          expected="rendered", actual=nolot_html)
            gate = {}
            for label, value in (("serial column", 'name="th_serial_number"'),
                                 ("serial header", "Lot/Serial Number")):
                if value not in rma_html:
                    gate[f"{label} absent for the {SERIAL_GROUP} member"] = value
                if value in nolot_html:
                    gate[f"{label} present for the non-member"] = value
            ctx.check("the serial column is rendered only for a "
                      "stock.group_production_lot member "
                      "(report_stockpicking_operations.xml:96,111-113,152-158; "
                      "QWeb compiles groups= to user_has_groups(), "
                      "ir_qweb.py:1843-1855)",
                      expected={}, actual=gate)

        with ctx.step("Open the ordinary picking and call do_print_picking()"):
            plain = rma_snapshot(rpc_user, plain_id)
            plain_action = print_action(rpc_user, plain_id)
            ctx.check("the ordinary picking carries no rma_number, so the "
                      "branch at models/stock_picking.py:38 is not taken",
                      expected={"rma_number": False,
                                "type": "ir.actions.report"},
                      actual={"rma_number": bool(plain["rma_number"]),
                              "type": (plain_action or {}).get("type")})

        with ctx.step("Assert the returned action's report reference is "
                      "stock.action_report_picking — the standard operations "
                      "slip"):
            ctx.check("the action is stock.action_report_picking's",
                      expected={key: std_report[key]
                                for key in REPORT_ACTION_KEYS},
                      actual={key: (plain_action or {}).get(key)
                              for key in REPORT_ACTION_KEYS})
            ctx.check("and that record is core's, unmodified "
                      "(stock/report/stock_report_views.xml:4-13)",
                      expected=REPORT_STD_ACTION,
                      actual={key: std_report[key]
                              for key in REPORT_STD_ACTION})

        with ctx.step("Assert the ordinary slip's text does not contain an "
                      "RMA number"):
            ok_plain, plain_html = _render(ctx, std_report["report_name"],
                                           plain_id, opener_lot)
            if not ok_plain:
                ctx.check("the standard picking slip renders",
                          expected="rendered", actual=plain_html)
            leaked = {}
            if rma_number and rma_number in plain_html:
                leaked["rma_number"] = rma_number
            if "Reason for return:" in plain_html:
                leaked["reason block"] = "Reason for return:"
            ctx.check("core's slip carries neither the RMA number nor the "
                      "reason block", expected={}, actual=leaked)

        with ctx.step("Record the page size of the RMA PDF and assert it "
                      "matches the company default paperformat, not a label "
                      "format"):
            # get_paperformat() returns a recordset and cannot be marshalled
            # over call_kw (v17 ir_actions_report.py:245, v19 :288), so its
            # two inputs are read instead: the action's own paperformat_id
            # (declared nowhere in report/stock_report_views.xml) and
            # res.company.paperformat_id, which is what it falls back to.
            fmt = company_paperformat(rpc)
            ctx.log(f"resolved paperformat for {REPORT_RMA_XMLID}: {fmt}")
            ctx.check("the RMA report declares no paperformat of its own, so "
                      "it resolves to the company's",
                      expected=False,
                      actual=bool(m2o_id(rma_report["paperformat_id"])))
            # report.paperformat.default is inert — nothing in core reads it
            # (v17 odoo/addons/base/models/report_paperformat.py:171, v19
            # :170) — so the assertable risk is the COMPANY's format being the
            # 43 x 30 mm label location_barcode_labels/views/
            # barcode_labels_location.xml:13-28 ships with default="True".
            ctx.check("the company's paperformat is a page, not the 43 x 30 mm "
                      "label",
                      expected=True,
                      actual=(fmt.get("page_width"),
                              fmt.get("page_height")) != (43, 30))
            ctx.log("MANUAL half: measuring the page size of the PRODUCED PDF "
                    "needs wkhtmltopdf on the Odoo host (/report/pdf/...), "
                    "which the platform does not require. What is asserted "
                    "here is the format the report resolves to, which is the "
                    "input that decides it.")
    finally:
        # Both disposable print sessions — see the note in TC186's teardown.
        archive_qa_users(ctx, ["tc187lot", "tc187nolot"])
        safe_sweep(ctx)
