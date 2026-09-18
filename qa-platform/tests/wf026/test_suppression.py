"""DATAONE-WF-026 — the suppression layer, and the GATE that proves it holds.

These five cases are the workflow. ``dto_data_migration`` writes 43,313
finished legacy transactions straight into ``purchase.order``,
``sale.order`` and ``mrp.production``, and then has to stop core from
re-deriving their state — because the movements core would derive it from
were never imported. The whole mechanism is one Boolean,
``is_historical_data`` (``models/dto_data_migration.py:17``), and thirteen
overrides keyed on it.

Why TC399 is the GATE
---------------------
If one of those thirteen overrides stops being reached, **nothing raises**.
Core simply recomputes, finds no stock moves and no invoices, and writes
zeros. 34,252 manufacturing orders report zero produced, every purchase
order reports nothing received, and the import still says it succeeded. The
failure is silent by construction, so the only way to catch it is to force a
recompute and assert the values survive it.

How the recompute is forced, and why not the workbook's way
------------------------------------------------------------
The workbook says ``invalidate_recordset()``. That method is not reachable
over RPC — Odoo refuses it as private, verified on d1v19. These cases use a
**second authenticated session** instead (``fresh_rpc``): a different
transaction with an empty environment cache, so every non-stored compute is
recalculated from the database rather than served from the cache the first
session warmed. It is the stronger form of the same check, and it is
documented in ``common.fresh_rpc`` per hard rule 5.

The one place v19 changed the answer
-------------------------------------
The workbook says an imported purchase order is **Done**. On v19 there is no
``done`` state on ``purchase.order`` at all — the selection is
draft/sent/to approve/purchase/cancel, and a writable ``locked`` Boolean
carries what ``done`` used to mean. The port made that change deliberately
(``models/purchase_order.py:48-49``, D-new-15) and importing with
``state='done'`` would raise at create. So TC398 asserts
``state='purchase'`` **and** ``locked=True`` together, which is the same
business fact in v19 vocabulary, and says so in its steps.

EXPECTED v17 OUTCOME
  TC398 PASS with the PO reading ``done``; TC399-TC402 PASS.
EXPECTED v19 OUTCOME
  All five PASS, with TC398's purchase-order assertion reading
  ``purchase`` + ``locked`` per D-new-15. A FAIL on TC399 or TC402 is the
  serious one: it means an override stopped being reached, and the fields it
  names are the port's to-do list.
"""
from adapters.base import OdooRPCError
from framework.registry import test_case
from tests.wf026.common import (SUPPRESSED_OBSERVABLES, WORKFLOW,
                                WORKFLOW_NAME, ensure_partner, ensure_product,
                                fresh_rpc, fx, m2o_id, make_wizard,
                                open_namespace, partner_name, product_code,
                                require_data_migration, run_import,
                                sweep_wf026, token, trace)


# --------------------------------------------------------------- fixtures
def _import_po(ctx, rpc, product_id, vendor_id):
    """One closed PO with THREE lines, two distinct receipt numbers and one
    repeat, so TC401's distinct-join assertion has something to prove."""
    name = fx("PO-001").replace(" ", "-")
    rows = [
        {"name": name, "partner_id": partner_name(rpc, vendor_id),
         "date_order": "01/10/2024",
         "order_line/product_id": product_code(rpc, product_id),
         "order_line/product_qty": "2", "order_line/price_unit": "10",
         "order_line/receipt_date": "02/01/2024",
         "order_line/receipt_number": "RCPT-A"},
        # Rows 1 and 2 carry DIFFERENT date_order values on purpose: TC401
        # step 7 asserts the header comes from row 0 only.
        {"name": name, "partner_id": partner_name(rpc, vendor_id),
         "date_order": "01/11/2024",
         "order_line/product_id": product_code(rpc, product_id),
         "order_line/product_qty": "1", "order_line/price_unit": "20",
         "order_line/receipt_date": "02/05/2024",
         "order_line/receipt_number": "RCPT-B"},
        {"name": name, "partner_id": partner_name(rpc, vendor_id),
         "date_order": "01/12/2024",
         "order_line/product_id": product_code(rpc, product_id),
         "order_line/product_qty": "3", "order_line/price_unit": "5",
         "order_line/receipt_date": "02/03/2024",
         "order_line/receipt_number": "RCPT-A"},
    ]
    run_import(rpc, make_wizard(rpc, "closed_po", rows))
    found = rpc.search("purchase.order", [("name", "=", name)])
    return (found or [None])[0], name


def _import_mos(ctx, rpc, product_id):
    """Two closed MOs: one where produced == ordered, one where it does not.
    TC402 needs both, because a single equal pair cannot distinguish the
    imported figure from a coincidence."""
    n1 = fx("MO-001").replace(" ", "-")
    n2 = fx("MO-002").replace(" ", "-")
    rows = [
        {"name": n1, "product_id": product_code(rpc, product_id),
         "product_qty": "10", "qty_produced": "10"},
        {"name": n2, "product_id": product_code(rpc, product_id),
         "product_qty": "4", "qty_produced": "3"},
    ]
    run_import(rpc, make_wizard(rpc, "closed_mo", rows))
    ids = {}
    for name in (n1, n2):
        found = rpc.search("mrp.production", [("name", "=", name)])
        ids[name] = (found or [None])[0]
    return ids, n1, n2


def _import_so(ctx, rpc, product_id, customer_id, mo_names):
    """One closed SO with two lines, linked to the two imported MOs."""
    name = fx("SO-001").replace(" ", "-")
    # order_type is REQUIRED and NOT NULL at the database level on this
    # target (dto_sale adds it), so an imported row without it fails with
    # 'null value in column "order_type" ... violates not-null constraint'
    # rather than anything the importer explains. Measured on d1v19.
    rows = [
        {"name": name, "partner_id": partner_name(rpc, customer_id),
         "date_order": "01/15/2024", "order_type": "buy",
         "mrp_production_ids": ",".join(mo_names),
         "order_line/product_id": product_code(rpc, product_id),
         "order_line/product_uom_qty": "2", "order_line/price_unit": "30"},
        {"name": name, "partner_id": partner_name(rpc, customer_id),
         "date_order": "01/15/2024", "order_type": "buy",
         "order_line/product_id": product_code(rpc, product_id),
         "order_line/product_uom_qty": "1", "order_line/price_unit": "40"},
    ]
    run_import(rpc, make_wizard(rpc, "closed_so", rows))
    found = rpc.search("sale.order", [("name", "=", name)])
    return (found or [None])[0], name


def _snapshot(rpc, model, rec_id, fields):
    row = rpc.read(model, [rec_id], fields)[0]
    # m2o values come back as [id, label]; keep only the id so a label
    # change (translation, rename) cannot look like a value change.
    return {f: (m2o_id(v) if isinstance(v, list) and len(v) == 2
                and isinstance(v[0], int) else v)
            for f, v in row.items() if f != "id"}


# ------------------------------------------------------------------ TC398
@test_case(
    id="TEST-WF026-TC398",
    name="A synchronous import of all four types produces the expected "
         "states and opens the created records",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_data_migration",
    priority="P0", kind="FUNC", order=26398,
    description="MO Done x2, PO closed with 3 lines, SO Sales Order with 2 "
                "lines and a stat button of 2, BoM with 2 lines; every record "
                "flagged historical; nothing created in the five models the "
                "workbook's step 20 names.",
    traceability=trace("DATAONE-TC398"))
def test_tc398(ctx):
    """EXPECTED v19 OUTCOME: FAIL on step 20, and the failure is a finding.

    Measured on d1v19: importing ONE closed purchase order leaves **receipt
    pickings** behind, in state ``assigned``::

        WH-IN-03729  origin=WF026-<token>-PO-001  Receipts  assigned

    The sales-order half of the suppression works — TC400 proves an imported
    SO generates no picking, no move and no invoice. The purchase half does
    not.

    The likely cause is Stage 7's own change. v17 imported a closed PO with
    ``state='done'``, which creates no receipt. v19 removed that state, so
    the port writes ``state='purchase'`` plus ``locked=True`` instead
    (``models/purchase_order.py:48-49``, D-new-15) — and ``purchase`` is a
    state the stock layer acts on. The port comment reasons carefully about
    ``locked`` being writable in the same create(); it does not mention
    receipts.

    Why it matters at scale: the v17 baseline counts **2,388 historical
    purchase orders**
    (``database/STAGE7-PHASE0A-BASELINE-v17.txt:5-11``). Importing them
    would put thousands of receipts into the warehouse's to-do list, in
    ``assigned`` state, for orders closed years ago — and the import would
    report success.

    This suite does not fix it: confirming whether the receipts should be
    suppressed, cancelled or never created is the module owner's call.
    """
    rpc = ctx.adapter.rpc
    require_data_migration(ctx)
    open_namespace(ctx)
    try:
        with ctx.step("Fixtures"):
            product = ensure_product(rpc, "Part")
            vendor = ensure_partner(rpc, "Vendor", supplier=True)
            customer = ensure_partner(rpc, "Customer")

        with ctx.step("Import two closed manufacturing orders"):
            mos, n1, n2 = _import_mos(ctx, rpc, product)
            ctx.check_true("both MOs were created", all(mos.values()),
                           str(mos))
            rows = rpc.read("mrp.production", [i for i in mos.values() if i],
                            ["name", "state", "qty_produced", "product_qty",
                             "is_historical_data"])
            by_name = {r["name"]: r for r in rows}
            ctx.check("MO states", ["done", "done"],
                      [by_name[n]["state"] for n in (n1, n2)])
            ctx.check("qty_produced", [10.0, 3.0],
                      [by_name[n]["qty_produced"] for n in (n1, n2)])
            ctx.check("product_qty", [10.0, 4.0],
                      [by_name[n]["product_qty"] for n in (n1, n2)])
            ctx.check("both flagged historical", [True, True],
                      [by_name[n]["is_historical_data"] for n in (n1, n2)])

        with ctx.step("Import one closed purchase order with three lines"):
            po_id, po_name = _import_po(ctx, rpc, product, vendor)
            ctx.check_true("the PO was created", bool(po_id), str(po_id))
            po = rpc.read("purchase.order", [po_id],
                          ["state", "locked", "order_line",
                           "is_historical_data"])[0]
            # v19: purchase.order has no 'done' state. The port writes
            # state='purchase' + locked=True instead (models/purchase_order
            # .py:48-49, D-new-15), which is the same business fact in v19
            # vocabulary. The workbook's word is "Done".
            ctx.check("PO state", "purchase", po["state"])
            ctx.check_true("PO is locked — v19's spelling of the workbook's "
                           "Done", po["locked"], str(po["locked"]))
            ctx.check("PO line count", 3, len(po["order_line"]))
            ctx.check_true("PO flagged historical", po["is_historical_data"],
                           str(po["is_historical_data"]))

        with ctx.step("Import one closed sales order linked to both MOs"):
            so_id, so_name = _import_so(ctx, rpc, product, customer, [n1, n2])
            ctx.check_true("the SO was created", bool(so_id), str(so_id))
            so = rpc.read("sale.order", [so_id],
                          ["state", "order_line", "mrp_production_count",
                           "import_mrp_production_ids",
                           "is_historical_data"])[0]
            ctx.check("SO state", "sale", so["state"])
            ctx.check("SO line count", 2, len(so["order_line"]))
            ctx.check("the stat button counts both imported MOs", 2,
                      so["mrp_production_count"])
            ctx.check("import_mrp_production_ids holds both", 2,
                      len(so["import_mrp_production_ids"]))
            ctx.check_true("SO flagged historical", so["is_historical_data"],
                           str(so["is_historical_data"]))

        with ctx.step("Step 20: the import created nothing in the five "
                      "downstream models"):
            # The whole point of the suppression layer. Token-scoped: these
            # models carry the client's own rows and rule 3 forbids counting
            # them.
            scope = token()
            downstream = {
                "stock.picking": [("origin", "like", f"%{scope}%")],
                "stock.move": [("reference", "like", f"%{scope}%")],
                "account.move": [("invoice_origin", "like", f"%{scope}%")],
                "procurement.group": [("name", "like", f"%{scope}%")],
                "stock.move.line": [("reference", "like", f"%{scope}%")],
            }
            counts = {}
            for model, domain in downstream.items():
                counts[model] = (len(rpc.search(model, domain))
                                 if rpc.model_exists(model) else 0)
            ctx.check("nothing downstream was created",
                      {m: 0 for m in downstream}, counts)
    finally:
        with ctx.step("Cleanup"):
            try:
                sweep_wf026(rpc)
            except Exception:  # noqa: BLE001
                pass


# ------------------------------------------------------------------ TC399
@test_case(
    id="TEST-WF026-TC399",
    name="GATE. Import MO -> PO -> SO, then invalidate and re-read: nothing "
         "changes",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_data_migration",
    priority="P0", kind="REGR", order=26399,
    description="Every imported value survives a recompute in a fresh "
                "session. A failure here is the silent one the whole "
                "suppression layer exists to prevent, and the fields it "
                "names are the port's to-do list.",
    traceability=trace("DATAONE-TC399"))
def test_tc399(ctx):
    rpc = ctx.adapter.rpc
    require_data_migration(ctx)
    open_namespace(ctx)
    try:
        with ctx.step("Fixtures and the three imports"):
            product = ensure_product(rpc, "Part")
            vendor = ensure_partner(rpc, "Vendor", supplier=True)
            customer = ensure_partner(rpc, "Customer")
            mos, n1, n2 = _import_mos(ctx, rpc, product)
            po_id, _ = _import_po(ctx, rpc, product, vendor)
            so_id, _ = _import_so(ctx, rpc, product, customer, [n1, n2])
            ctx.check_true("all four records exist",
                           all([po_id, so_id, mos[n1], mos[n2]]),
                           f"po={po_id} so={so_id} mos={mos}")

        targets = [("purchase.order", po_id), ("sale.order", so_id),
                   ("mrp.production", mos[n1]), ("mrp.production", mos[n2])]

        with ctx.step("Steps 1-3: snapshot every suppressed observable"):
            before = {}
            for model, rec_id in targets:
                key = f"{model}#{rec_id}"
                before[key] = _snapshot(rpc, model, rec_id,
                                        SUPPRESSED_OBSERVABLES[model])
            po_lines = rpc.search("purchase.order.line",
                                  [("order_id", "=", po_id)])
            before["purchase.order.line"] = sorted(
                (r["id"], r["qty_invoiced"]) for r in rpc.read(
                    "purchase.order.line", po_lines, ["qty_invoiced"]))
            ctx.log(f"snapshot: {before}")

        with ctx.step("Step 4: the observable outcomes match TC398"):
            po_before = before[f"purchase.order#{po_id}"]
            ctx.check("PO effective_date", "2024-02-05",
                      str(po_before["effective_date"])[:10])
            ctx.check("PO receipt_number", "RCPT-A, RCPT-B",
                      po_before["receipt_number"])
            ctx.check("SO mrp_production_count", 2,
                      before[f"sale.order#{so_id}"]["mrp_production_count"])
            ctx.check("MO qty_produced", [10.0, 3.0],
                      [before[f"mrp.production#{mos[n1]}"]["qty_produced"],
                       before[f"mrp.production#{mos[n2]}"]["qty_produced"]])

        with ctx.step("Steps 6-7: re-read everything in a FRESH session, so "
                      "every non-stored compute is recalculated"):
            other = fresh_rpc(ctx)
            after = {}
            for model, rec_id in targets:
                key = f"{model}#{rec_id}"
                after[key] = _snapshot(other, model, rec_id,
                                       SUPPRESSED_OBSERVABLES[model])
            after["purchase.order.line"] = sorted(
                (r["id"], r["qty_invoiced"]) for r in other.read(
                    "purchase.order.line", po_lines, ["qty_invoiced"]))

        with ctx.step("Steps 8-18: nothing changed"):
            # One dict comparison, so a failure reports EVERY field that
            # moved rather than stopping at the first. That list is exactly
            # what a person porting this needs.
            drift = {k: {"before": before[k], "after": after[k]}
                     for k in before if before[k] != after[k]}
            ctx.check("fields that changed across the recompute", {}, drift)
            if drift:
                ctx.log("TO-DO LIST: every key above lost its suppression. "
                        "Core recomputed it from movements that were never "
                        "imported.")

        with ctx.step("Step 19: a second fresh session, to rule out a "
                      "one-off cache warming"):
            third = fresh_rpc(ctx)
            again = {}
            for model, rec_id in targets:
                again[f"{model}#{rec_id}"] = _snapshot(
                    third, model, rec_id, SUPPRESSED_OBSERVABLES[model])
            again["purchase.order.line"] = sorted(
                (r["id"], r["qty_invoiced"]) for r in third.read(
                    "purchase.order.line", po_lines, ["qty_invoiced"]))
            drift2 = {k: {"before": before[k], "after": again[k]}
                      for k in before if before[k] != again[k]}
            ctx.check("still unchanged on a third read", {}, drift2)

        with ctx.step("Step 20: the suppression is TARGETED — a live record "
                      "is not affected by it"):
            # Without this, every "unchanged" above could mean the computes
            # are broken for everyone rather than suppressed for historical
            # rows only. A freshly created, NON-historical MO must behave
            # normally: produced nothing, because it really has produced
            # nothing.
            control_id = rpc.create("mrp.production", {
                "product_id": product,
                "product_qty": 7.0,
            })
            control = fresh_rpc(ctx).read(
                "mrp.production", [control_id],
                ["state", "qty_produced", "is_historical_data"])[0]
            ctx.check_true("the control is NOT flagged historical",
                           not control["is_historical_data"],
                           str(control["is_historical_data"]))
            ctx.check("the control is draft", "draft", control["state"])
            ctx.check("and core reports it produced nothing — the compute "
                      "still works for live records", 0.0,
                      control["qty_produced"])
    finally:
        with ctx.step("Cleanup"):
            try:
                sweep_wf026(rpc)
            except Exception:  # noqa: BLE001
                pass


# ------------------------------------------------------------------ TC400
@test_case(
    id="TEST-WF026-TC400",
    name="An imported sales order generates zero deliveries and zero stock "
         "moves",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_data_migration",
    priority="P0", kind="FUNC", order=26400,
    description="Zero pickings, moves, move lines, procurement group and "
                "invoice. The positive control is what makes those zeros "
                "mean something rather than a broken warehouse.",
    traceability=trace("DATAONE-TC400"))
def test_tc400(ctx):
    rpc = ctx.adapter.rpc
    require_data_migration(ctx)
    open_namespace(ctx)
    try:
        with ctx.step("Fixtures and the import"):
            product = ensure_product(rpc, "Part")
            customer = ensure_partner(rpc, "Customer")
            mos, n1, n2 = _import_mos(ctx, rpc, product)
            so_id, so_name = _import_so(ctx, rpc, product, customer, [n1, n2])
            ctx.check_true("the SO was created", bool(so_id), str(so_id))

        with ctx.step("Steps 5-9: the imported order moved no stock"):
            observed = {
                "pickings": len(rpc.search(
                    "stock.picking", [("sale_id", "=", so_id)]))
                if rpc.field_exists("stock.picking", "sale_id") else 0,
                "moves": len(rpc.search(
                    "stock.move", [("sale_line_id.order_id", "=", so_id)])),
                "invoices": len(rpc.search(
                    "account.move", [("invoice_origin", "=", so_name)])),
            }
            ctx.check("nothing was generated",
                      {"pickings": 0, "moves": 0, "invoices": 0}, observed)

        with ctx.step("Step 12: no procurement group"):
            row = rpc.read("sale.order", [so_id],
                           ["procurement_group_id", "delivery_status",
                            "invoice_status"])[0] \
                if rpc.field_exists("sale.order", "procurement_group_id") \
                else {"procurement_group_id": False}
            ctx.check_true("procurement_group_id is empty",
                           not row.get("procurement_group_id"),
                           str(row.get("procurement_group_id")))

        with ctx.step("Step 10: the POSITIVE CONTROL — a live order of the "
                      "same product DOES generate a delivery"):
            # Without this the zeros above could simply mean the warehouse
            # cannot deliver this product at all, which would make the whole
            # case vacuous. Outcome convention rule 5.
            # dto_sale gates confirmation behind several of its own fields.
            # order_type='inventory' is used rather than 'buy' because 'buy'
            # additionally requires a Customer Contract analytic
            # distribution (the rule TEST-WF002-TC079 covers), which would
            # make this control about dto_sale's analytic rules instead of
            # about the warehouse.
            live_id = rpc.create("sale.order", {
                "partner_id": customer,
                "order_type": "inventory",
                "requester": fx("QA Requester"),
                "requester_email": "qa-wf026@example.invalid",
                "order_line": [(0, 0, {
                    "product_id": product,
                    "product_uom_qty": 1.0,
                    # "Promised Ship Date", required per line before confirm
                    "requested_delivery_date": "2026-12-31"})],
            })
            try:
                rpc.call("sale.order", "action_confirm", [live_id])
            except OdooRPCError as exc:
                # Without a working control the zeros above prove nothing,
                # so this BLOCKS rather than passing on an unproven premise
                # (outcome convention rule 5).
                ctx.blocked(
                    f"the positive control could not be confirmed on this "
                    f"target: {exc}. dto_sale gates sale.order confirmation "
                    f"behind its own required fields, and until one confirms, "
                    f"the zero pickings asserted above cannot be "
                    f"distinguished from a warehouse that cannot deliver "
                    f"this product at all.")
            live_moves = rpc.search(
                "stock.move", [("sale_line_id.order_id", "=", live_id)])
            ctx.check_true("the live order produced at least one stock move — "
                           "so the zeros above are the suppression, not a "
                           "broken warehouse",
                           len(live_moves) > 0, str(live_moves))
            ctx.log(f"control order {live_id} generated {len(live_moves)} "
                    f"stock move(s)")

        with ctx.step("Step 14: the imported order is still untouched after "
                      "the control ran"):
            still = len(rpc.search(
                "stock.move", [("sale_line_id.order_id", "=", so_id)]))
            ctx.check("imported order stock moves", 0, still)
    finally:
        with ctx.step("Cleanup"):
            try:
                sweep_wf026(rpc)
            except Exception:  # noqa: BLE001
                pass


# ------------------------------------------------------------------ TC401
@test_case(
    id="TEST-WF026-TC401",
    name="An imported purchase order derives Effective Date and Receipt "
         "Number from its lines",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_data_migration",
    priority="P1", kind="FUNC", order=26401,
    description="2024-02-05 and 'RCPT-A, RCPT-B' from three lines with one "
                "repeated value; date_order from row 0 only; both values "
                "track a line change and revert when it is undone.",
    traceability=trace("DATAONE-TC401"))
def test_tc401(ctx):
    """EXPECTED v19 OUTCOME: FAIL on step 5, and the failure is the finding.

    The workbook requires Receipt Number to be the distinct line values
    joined **in line order**. The compute cannot deliver that
    (``dto_data_migration/models/purchase_order.py:14-16``)::

        receipt_number_lst = set(res.order_line
                                 .filtered(lambda l: l.receipt_number)
                                 .mapped('receipt_number'))
        res.receipt_number = ', '.join(receipt_number_lst)

    A ``set`` has no defined iteration order, and Python randomises string
    hashing per process, so the join order varies between server restarts.
    Measured here: the three lines carry RCPT-A, RCPT-B, RCPT-A and the
    field read back ``'RCPT-B, RCPT-A'``.

    Two things make this worth failing over rather than relaxing:

    * the field is ``store=True``, so whatever order happened at compute
      time is PERSISTED — two orders imported in the same batch can end up
      with their receipt numbers in different orders for no reason a reader
      can see;
    * a person reads this field to match a vendor's paperwork, and
      "RCPT-B, RCPT-A" against a document listing A then B is exactly the
      kind of mismatch that costs an hour.

    The fix is one word — ``sorted()``, or ``dict.fromkeys()`` to keep line
    order — but it is a product change, and hard rule 2 says the expectation
    stands until the product meets it.
    """
    rpc = ctx.adapter.rpc
    require_data_migration(ctx)
    open_namespace(ctx)
    try:
        with ctx.step("Fixtures and the import"):
            product = ensure_product(rpc, "Part")
            vendor = ensure_partner(rpc, "Vendor", supplier=True)
            po_id, po_name = _import_po(ctx, rpc, product, vendor)
            ctx.check_true("the PO was created", bool(po_id), str(po_id))

        with ctx.step("Step 2: exactly three lines"):
            line_ids = rpc.search("purchase.order.line",
                                  [("order_id", "=", po_id)])
            ctx.check("line count", 3, len(line_ids))

        with ctx.step("Step 3: the %m/%d/%Y parse worked on every line"):
            lines = rpc.read("purchase.order.line", line_ids,
                             ["receipt_date", "receipt_number"])
            got = [str(r["receipt_date"])[:10] for r in lines]
            ctx.check("line receipt dates, in line order",
                      ["2024-02-01", "2024-02-05", "2024-02-03"], got)

        with ctx.step("Step 4: Effective Date is the LATEST line date, not "
                      "the first and not the order date"):
            po = rpc.read("purchase.order", [po_id],
                          ["effective_date", "receipt_number", "date_order"])[0]
            ctx.check("effective_date", "2024-02-05",
                      str(po["effective_date"])[:10])

        with ctx.step("Step 5: Receipt Number is the DISTINCT line values, "
                      "comma-and-space joined, the repeat appearing once"):
            ctx.check("receipt_number", "RCPT-A, RCPT-B", po["receipt_number"])

        with ctx.step("Step 7: header values come from row 0 only"):
            # Rows 1 and 2 carried 01/11 and 01/12 deliberately.
            ctx.check("date_order", "2024-01-10", str(po["date_order"])[:10])

        with ctx.step("Steps 9-10: both values track a new line, and revert "
                      "when it is removed"):
            new_line = rpc.create("purchase.order.line", {
                "order_id": po_id,
                "product_id": product,
                "product_qty": 1.0,
                "price_unit": 1.0,
                "name": fx("extra line"),
                "receipt_date": "2024-02-10 00:00:00",
                "receipt_number": "RCPT-C",
            })
            after = rpc.read("purchase.order", [po_id],
                             ["effective_date", "receipt_number"])[0]
            ctx.check("effective_date after the fourth line", "2024-02-10",
                      str(after["effective_date"])[:10])
            ctx.check("receipt_number after the fourth line",
                      "RCPT-A, RCPT-B, RCPT-C", after["receipt_number"])

            rpc.call("purchase.order.line", "unlink", [new_line])
            reverted = rpc.read("purchase.order", [po_id],
                                ["effective_date", "receipt_number"])[0]
            ctx.check("effective_date reverts", "2024-02-05",
                      str(reverted["effective_date"])[:10])
            ctx.check("receipt_number reverts", "RCPT-A, RCPT-B",
                      reverted["receipt_number"])
    finally:
        with ctx.step("Cleanup"):
            try:
                sweep_wf026(rpc)
            except Exception:  # noqa: BLE001
                pass


# ------------------------------------------------------------------ TC402
@test_case(
    id="TEST-WF026-TC402",
    name="An imported manufacturing order reports the imported produced "
         "quantity, not zero",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_data_migration",
    priority="P1", kind="FUNC", order=26402,
    description="10.0 and 3.0, and still 10.0 and 3.0 after a recompute. "
                "There are no stock moves for core to derive from, which is "
                "what makes the survival meaningful; the live control proves "
                "the compute itself still works.",
    traceability=trace("DATAONE-TC402"))
def test_tc402(ctx):
    rpc = ctx.adapter.rpc
    require_data_migration(ctx)
    open_namespace(ctx)
    try:
        with ctx.step("Fixtures and the import"):
            product = ensure_product(rpc, "Assembly")
            mos, n1, n2 = _import_mos(ctx, rpc, product)
            ctx.check_true("both MOs exist", all(mos.values()), str(mos))

        with ctx.step("Steps 2-4: MIG-MO-001 is done, historical, and reports "
                      "10.0"):
            mo1 = rpc.read("mrp.production", [mos[n1]],
                           ["state", "is_historical_data", "qty_produced",
                            "qty_producing", "import_qty_produced",
                            "product_qty"])[0]
            ctx.check("state", "done", mo1["state"])
            ctx.check_true("is_historical_data", mo1["is_historical_data"],
                           str(mo1["is_historical_data"]))
            ctx.check("qty_produced", 10.0, mo1["qty_produced"])
            ctx.check("import_qty_produced", 10.0, mo1["import_qty_produced"])
            ctx.check("qty_producing", 10.0, mo1["qty_producing"])

        with ctx.step("Step 6: MIG-MO-002 produced 3.0 against an order of "
                      "4.0 — the two differ, and the imported figure wins"):
            mo2 = rpc.read("mrp.production", [mos[n2]],
                           ["product_qty", "qty_produced"])[0]
            ctx.check("product_qty", 4.0, mo2["product_qty"])
            ctx.check("qty_produced", 3.0, mo2["qty_produced"])

        with ctx.step("Step 7: there is nothing for core to derive from"):
            raw = len(rpc.search(
                "stock.move", [("raw_material_production_id", "=", mos[n2])]))
            finished = len(rpc.search(
                "stock.move", [("production_id", "=", mos[n2])]))
            ctx.check("raw and finished stock moves on the imported MO",
                      {"raw": 0, "finished": 0},
                      {"raw": raw, "finished": finished})

        with ctx.step("Steps 8-9: after a recompute the values are still "
                      "10.0 and 3.0, not 0.0"):
            other = fresh_rpc(ctx)
            rows = other.read("mrp.production", [mos[n1], mos[n2]],
                              ["name", "qty_produced"])
            by_name = {r["name"]: r["qty_produced"] for r in rows}
            ctx.check("qty_produced survives the recompute",
                      {n1: 10.0, n2: 3.0},
                      {n1: by_name[n1], n2: by_name[n2]})

        with ctx.step("Step 13: the LIVE control — a non-historical MO still "
                      "computes normally"):
            control_id = rpc.create("mrp.production", {
                "product_id": product, "product_qty": 5.0})
            control = fresh_rpc(ctx).read(
                "mrp.production", [control_id],
                ["qty_produced", "is_historical_data"])[0]
            ctx.check_true("the control is not historical",
                           not control["is_historical_data"],
                           str(control["is_historical_data"]))
            ctx.check("and it reports 0.0 produced, because it has produced "
                      "nothing", 0.0, control["qty_produced"])

        with ctx.step("Step 10: the Miscellaneous fields the import carries "
                      "all exist on this target"):
            misc = ["customer_id", "customer_po", "connectors",
                    "remaining_quantity", "material_actual_amount",
                    "pwo_actual_amount"]
            missing = [f for f in misc
                       if not rpc.field_exists("mrp.production", f)]
            ctx.check("Miscellaneous fields present on mrp.production", [],
                      missing)
    finally:
        with ctx.step("Cleanup"):
            try:
                sweep_wf026(rpc)
            except Exception:  # noqa: BLE001
                pass
