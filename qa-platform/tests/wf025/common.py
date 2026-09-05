"""DATAONE-WF-025 — Gross Requirements Planning: shared fixtures.

Read out of the real v19 source before anything here was written
(AUTOMATION_CONVENTIONS hard rule 6), in
``project-addons/dto_mrp/wizard/gross_requirement_report.py`` and
``project-addons/dto_mrp/models/``:

* ``gross.requirement.report`` — ``finished_good_ids``, ``component_ids``,
  ``date``, ``company_id``, ``applicable_product_ids``, ``name``, and the
  actions ``run``, ``action_remove_invalid_finished_goods``,
  ``action_remove_finished_goods``, ``action_import_finished_goods``
* ``gross.requirement.finished_good`` — ``product_id``, ``default_code``
  (compute + inverse, so a SKU string resolves to a product),
  ``qty_to_produce``, ``bom_id`` (computed), ``is_blocked`` (STORED compute)
* ``gross.requirement.component`` — ``product_id``, ``product_uom_id``,
  ``qty_available``, ``qty_required``, ``qty_to_order``,
  ``qty_already_ordered``
* ``stock.location.ignore_quantities_for_gross_report``
  (models/stock_location.py:6)

**The availability rule, verbatim** (models/product_product.py:14-18) — the
whole of TC146 and TC147 is this one expression::

    stock_quants = search([('product_id', '=', product.id),
                           ('location_id.ignore_quantities_for_gross_report', '=', False),
                           ('location_id.usage', '=', 'internal'),
                           ('on_hand', '=', True)])
    quantity_available_in_stock = (
        sum(stock_quants.mapped('inventory_quantity_auto_apply'))
        - sum(stock_quants.filtered(lambda sq: sq.location_id.name != 'Input')
                          .mapped('reserved_quantity')))

Two things follow from it, and both are asserted rather than assumed:
flagged locations drop out of the sum entirely (TC146), and reservations are
subtracted everywhere EXCEPT in a location whose **name** is exactly
``Input`` (TC147) — the behaviour follows the name, not the location id, so
renaming a location silently changes every availability figure.

The two ``UserError`` strings TC144 requires verbatim, read from
gross_requirement_report.py:140,142 rather than paraphrased::

    'Please select at least one product.'
    'Please remove all invalid products.'
"""
from __future__ import annotations

import uuid

from adapters.base import OdooRPCError
from framework.fg_common import m2o_id, make_trace  # noqa: F401 — re-exported
from framework.qa_fixtures import sweep_model, with_categ

WORKFLOW = "DATAONE-WF-025"
WORKFLOW_NAME = "Gross Requirements Planning"

trace = make_trace(WORKFLOW)

MARKER = "WF025"
_TOKEN = f"{MARKER}-{uuid.uuid4().hex[:8].upper()}"

# Exact, from the source. TC144 forbids paraphrasing these.
ERROR_NO_PRODUCT = "Please select at least one product."
ERROR_INVALID_ROWS = "Please remove all invalid products."

#: The one location name the availability rule treats specially.
INPUT_LOCATION_NAME = "Input"


def tag(name: str) -> str:
    return f"{_TOKEN} {name}"


def fixture_token() -> str:
    return _TOKEN


# --------------------------------------------------------------- preconditions
def require_gross_report(ctx):
    """BLOCK unless dto_mrp contributed the wizard and its two line models."""
    rpc = ctx.adapter.rpc
    missing = [m for m in ("gross.requirement.report",
                          "gross.requirement.finished_good",
                          "gross.requirement.component")
               if not rpc.model_exists(m)]
    if not rpc.field_exists("stock.location",
                            "ignore_quantities_for_gross_report"):
        missing.append("stock.location.ignore_quantities_for_gross_report")
    if missing:
        ctx.blocked(
            f"dto_mrp is not contributing the Gross Requirements Report to "
            f"{ctx.env.key} (db={ctx.env.db}) — missing: {', '.join(missing)}. "
            f"Stage 3 must be installed (tools/uat_cleanup.sh) first.")


# ------------------------------------------------------------------- sweeping
def sweep_wf025(rpc):
    """Best-effort teardown, children before parents."""
    for model, domain in (
            ("gross.requirement.component", [("product_id.default_code", "like", MARKER)]),
            ("gross.requirement.finished_good", [("default_code", "like", MARKER)]),
    ):
        sweep_model(rpc, model, domain)
    sweep_model(rpc, "gross.requirement.report", [("name", "like", MARKER)])
    sweep_model(rpc, "mrp.bom", [("code", "like", MARKER)])
    product_ids = rpc.search("product.product", [("default_code", "like", MARKER)])
    if product_ids:
        sweep_model(rpc, "stock.quant", [("product_id", "in", product_ids)])
    sweep_model(rpc, "product.product", [("default_code", "like", MARKER)])
    sweep_model(rpc, "product.template", [("default_code", "like", MARKER)])
    sweep_model(rpc, "stock.location", [("name", "like", MARKER)])


def open_namespace(ctx):
    with ctx.step(f"Sweep previous {MARKER} fixtures and open a fresh namespace"):
        sweep_wf025(ctx.adapter.rpc)
        ctx.log(f"fixture token = {_TOKEN}")


# ------------------------------------------------------------------- fixtures
def make_product(rpc, label: str, storable: bool = True,
                 service: bool = False) -> int:
    """A product under the token. v19 shape: type + is_storable."""
    values = {
        "name": tag(label),
        "default_code": f"{_TOKEN}-{label}",
        "purchase_ok": True,
    }
    if service:
        values["type"] = "service"
    else:
        values["type"] = "consu"
        if rpc.field_exists("product.template", "is_storable"):
            values["is_storable"] = storable
        elif storable:                      # v17 shape, for the baseline target
            values["type"] = "product"
    return rpc.create("product.product", with_categ(rpc, values))


def product_tmpl_of(rpc, product_id: int) -> int:
    return m2o_id(rpc.read("product.product", [product_id],
                           ["product_tmpl_id"])[0]["product_tmpl_id"])


def make_bom(rpc, finished_id: int, lines: list[tuple[int, float]],
             product_qty: float = 1.0, bom_type: str = "normal") -> int:
    """lines = [(component_id, qty_per_bom), ...]."""
    return rpc.create("mrp.bom", {
        "product_tmpl_id": product_tmpl_of(rpc, finished_id),
        "code": tag("BOM"),
        "product_qty": product_qty,
        "type": bom_type,
        "bom_line_ids": [(0, 0, {"product_id": pid, "product_qty": qty})
                         for pid, qty in lines],
    })


def warehouse(rpc) -> dict:
    rows = rpc.search_read("stock.warehouse", [], ["lot_stock_id", "view_location_id"],
                           limit=1, order="id")
    if not rows:
        raise AssertionError("no stock.warehouse on the target")
    return rows[0]


def stock_location(rpc) -> int:
    return m2o_id(warehouse(rpc)["lot_stock_id"])


def make_location(rpc, label: str, parent_id: int | None = None,
                  ignore_for_gross: bool = False,
                  name: str | None = None) -> int:
    """An internal child location.

    ``name`` overrides the namespaced label, which TC147 needs in order to
    create a location literally called ``Input``. Such a location is still
    swept, because its parent is namespaced and the sweep also matches on the
    token in the complete name.
    """
    return rpc.create("stock.location", {
        "name": name if name is not None else tag(label),
        "usage": "internal",
        "location_id": parent_id or m2o_id(warehouse(rpc)["view_location_id"]),
        "ignore_quantities_for_gross_report": ignore_for_gross,
    })


def _picking_type(rpc, code: str) -> int:
    rows = rpc.search_read("stock.picking.type", [("code", "=", code)], ["id"],
                           limit=1, order="id")
    if not rows:
        raise AssertionError(f"no stock.picking.type with code={code!r}")
    return rows[0]["id"]


def _inventory_location(rpc) -> int:
    rows = rpc.search_read("stock.location", [("usage", "=", "inventory")],
                           ["complete_name"], order="id")
    preferred = [r for r in rows if "scrap" not in r["complete_name"].lower()]
    if not rows:
        raise AssertionError("no stock.location with usage='inventory'")
    return (preferred or rows)[0]["id"]


def add_stock(rpc, product_id: int, location_id: int, qty: float):
    """Receive `qty` into a location through a picking.

    Deliberately NOT the inventory-count path: Stage 3's ``dto_cycle_count``
    overrides ``stock.quant._apply_inventory`` and calls
    ``cycle_count_category_id._calculate_scheduled_count_date(...)``, whose
    first line is ``ensure_one()``. Every product on d1v19 has an empty
    cycle-count category (measured: 0 of 21,362), so that path raises
    ``Expected singleton: cycle.count.category()`` for every product. Booked
    as a product finding in the WF-009 suite; avoided here.
    """
    if qty <= 0:
        return
    uom_id = m2o_id(rpc.read("product.product", [product_id], ["uom_id"])[0]["uom_id"])
    src = _inventory_location(rpc)
    picking_id = rpc.create("stock.picking", {
        "picking_type_id": _picking_type(rpc, "incoming"),
        "location_id": src,
        "location_dest_id": location_id,
        "origin": tag("stage-stock"),
        "move_ids": [(0, 0, {
            "product_id": product_id,
            "product_uom": uom_id,
            "product_uom_qty": qty,
            "location_id": src,
            "location_dest_id": location_id,
        })],
    })
    rpc.call("stock.picking", "action_confirm", [picking_id])
    rpc.call("stock.picking", "action_assign", [picking_id])
    move_ids = rpc.search("stock.move", [("picking_id", "=", picking_id)])
    rpc.write("stock.move", move_ids, {"quantity": qty, "picked": True})
    rpc.call("stock.picking", "button_validate", [picking_id])


def reserve(rpc, product_id: int, location_id: int, qty: float) -> int:
    """Hold `qty` as reserved_quantity in a location, via an outgoing picking.

    Returns the picking id so a case can release the reservation again.
    """
    uom_id = m2o_id(rpc.read("product.product", [product_id], ["uom_id"])[0]["uom_id"])
    dest = _inventory_location(rpc)
    picking_id = rpc.create("stock.picking", {
        "picking_type_id": _picking_type(rpc, "outgoing"),
        "location_id": location_id,
        "location_dest_id": dest,
        "origin": tag("hold"),
        "move_ids": [(0, 0, {
            "product_id": product_id,
            "product_uom": uom_id,
            "product_uom_qty": qty,
            "location_id": location_id,
            "location_dest_id": dest,
        })],
    })
    rpc.call("stock.picking", "action_confirm", [picking_id])
    rpc.call("stock.picking", "action_assign", [picking_id])
    return picking_id


def release(rpc, picking_id: int):
    try:
        rpc.call("stock.picking", "do_unreserve", [picking_id])
    except OdooRPCError:
        rpc.call("stock.picking", "action_cancel", [picking_id])


def quants_of(rpc, product_id: int) -> list[dict]:
    return rpc.search_read(
        "stock.quant", [("product_id", "=", product_id)],
        ["location_id", "quantity", "reserved_quantity", "inventory_quantity_auto_apply"])


# ------------------------------------------------------------------- the wizard
def new_report(rpc) -> int:
    return rpc.create("gross.requirement.report", {})


def add_finished_good(rpc, report_id: int, product_id: int | None,
                      qty: float, sku: str | None = None) -> int:
    """One finished-good row, addressed either by product or by SKU string.

    The SKU path goes through ``default_code``'s inverse
    (gross_requirement_report.py:216), which is exactly what the importer
    uses — so an unmatched SKU leaves ``product_id`` empty rather than
    raising, and that is what TC144 asserts.
    """
    values = {"gross_requirement_id": report_id, "qty_to_produce": qty}
    if product_id is not None:
        values["product_id"] = product_id
    if sku is not None:
        values["default_code"] = sku
    return rpc.create("gross.requirement.finished_good", values)


def finished_goods(rpc, report_id: int) -> list[dict]:
    return rpc.search_read(
        "gross.requirement.finished_good",
        [("gross_requirement_id", "=", report_id)],
        ["product_id", "default_code", "qty_to_produce", "bom_id", "is_blocked"],
        order="id")


def components(rpc, report_id: int) -> list[dict]:
    return rpc.search_read(
        "gross.requirement.component",
        [("gross_requirement_id", "=", report_id)],
        ["product_id", "product_uom_id", "qty_available", "qty_required",
         "qty_to_order", "qty_already_ordered"], order="id")


def component_for(rpc, report_id: int, product_id: int) -> dict | None:
    rows = [c for c in components(rpc, report_id)
            if m2o_id(c["product_id"]) == product_id]
    return rows[0] if rows else None


def run_report(rpc, report_id: int):
    return rpc.call("gross.requirement.report", "run", [report_id])


def run_expecting_error(rpc, report_id: int) -> str:
    try:
        run_report(rpc, report_id)
    except OdooRPCError as exc:
        return str(exc)
    return ""
