"""DATAONE-WF-007 — MO completion and serial-number generation: fixtures.

Read from the real v19 source before anything here was written
(AUTOMATION_CONVENTIONS hard rule 6), in
``project-addons/dto_mrp/models/mrp_production.py`` and
``.../models/stock_lot.py``:

* ``_eligible_for_auto_generate_serial()`` (:285) — tracking in
  ``('lot', 'serial')`` AND no ``lot_producing_ids`` AND ``qty_producing``
  non-zero AND NOT ``quality_check_fail``
* ``pre_button_mark_done()`` (:294) — generates the serial for eligible MOs,
  then calls super
* ``button_mark_done()`` (:300) — AFTER super, renames the FIRST
  auto-generated lot to ``_prepare_lot_name()``
* ``_prepare_lot_name()`` (:313) — ``<SO name>-<MO digits>``, or the bare MO
  digits when no sale order is reachable; ``MO digits`` is the name from its
  first digit onward (``re.search(r"\\d", self.name)``)
* ``_prepare_stock_lot_values()`` (:338) — stamps ``auto_generated = True``
  on both the normal and the UserError-fallback branch
* ``stock.lot.auto_generated`` — Boolean, default False, **copy=False**
* ``_get_source_sale_order()`` (:154) —
  ``(self.sale_line_id.order_id or self.reference_ids.sale_ids)[:1]``

**The one structural change that shapes this whole suite.** v19 replaced
``mrp.production.lot_producing_id`` (Many2one) with ``lot_producing_ids``
(Many2many) — the source calls it out as "B-1: M2o -> M2m", and measured on
d1v19 only ``lot_producing_ids`` exists. Every case therefore reads the M2m
and asserts through ``producing_lots()`` below, which returns a list so
"exactly one lot" stays assertable.

That rename is also why ``button_mark_done`` renames only
``lot_producing_ids.filtered('auto_generated')[:1]``: the source notes that
renaming all of them would give every lot on a multi-lot MO the same
``<SO>-<MO>`` name, and defers the multi-lot question to TODO(D-S2).

**Out of scope on this target.** The Packaging duration gate that TC114 and
TC115 assert lives in ``dto_mrp_account``, not ``dto_mrp``
(dto_mrp_account/models/mrp_production.py:114). That module is still 17.0,
is deliberately NOT in ``tools/uninstall_non_migrated.py``'s KEEP list, and
is uninstalled on d1v19 — measured. Those two cases BLOCK with that reason
rather than failing, because the behaviour is not deployed rather than
broken.
"""
from __future__ import annotations

import re
import uuid

from adapters.base import OdooRPCError
from framework.fg_common import m2o_id, make_trace  # noqa: F401 — re-exported
from framework.qa_fixtures import sweep_model, with_categ

WORKFLOW = "DATAONE-WF-007"
WORKFLOW_NAME = "MO Completion, Serial-Number Generation & Labelling"

trace = make_trace(WORKFLOW)

MARKER = "WF007"
_TOKEN = f"{MARKER}-{uuid.uuid4().hex[:8].upper()}"

#: Exact, from dto_mrp_account/models/mrp_production.py:114.
ERROR_PACKAGING = ("You cannot finish a manufacturing order without any work "
                   "done in Packaging. \n all work orders have 0 duration.")

_SEQ = {"n": 0}


def tag(name: str) -> str:
    return f"{_TOKEN} {name}"


def unique(prefix: str) -> str:
    _SEQ["n"] += 1
    return f"{_TOKEN} {prefix}-{_SEQ['n']:03d}"


def fixture_token() -> str:
    return _TOKEN


def mo_digits(mo_name: str) -> str:
    """The MO name from its first digit onward — ``_prepare_lot_name``'s rule.

    Mirrors ``re.search(r"\\d", self.name)`` exactly, including the unguarded
    fallback to the whole name when the MO has no digit at all (TC108 step 9
    asks for that behaviour to be recorded verbatim).
    """
    index = re.search(r"\d", mo_name)
    return mo_name[index.start():] if index else mo_name


# --------------------------------------------------------------- preconditions
def require_serial_stack(ctx):
    """BLOCK unless dto_mrp contributed the completion layer."""
    rpc = ctx.adapter.rpc
    missing = []
    if not rpc.field_exists("stock.lot", "auto_generated"):
        missing.append("stock.lot.auto_generated")
    if not (rpc.field_exists("mrp.production", "lot_producing_ids")
            or rpc.field_exists("mrp.production", "lot_producing_id")):
        missing.append("mrp.production.lot_producing_id(s)")
    if missing:
        ctx.blocked(
            f"dto_mrp is not contributing the serial-generation layer to "
            f"{ctx.env.key} (db={ctx.env.db}) — missing: {', '.join(missing)}. "
            f"Stage 3 must be installed (tools/uat_cleanup.sh) first.")


def require_packaging_gate(ctx):
    """BLOCK when the module that owns the Packaging gate is not installed."""
    rpc = ctx.adapter.rpc
    installed = rpc.search_read(
        "ir.module.module",
        [("name", "=", "dto_mrp_account"), ("state", "=", "installed")], ["id"])
    if not installed:
        ctx.blocked(
            "the Packaging duration gate lives in dto_mrp_account "
            "(models/mrp_production.py:114), which is still 17.0, is "
            "deliberately excluded from tools/uninstall_non_migrated.py's "
            "KEEP list, and is uninstalled on this target. The behaviour is "
            "not deployed rather than broken; this case cannot run until "
            "dto_mrp_account is ported and added to KEEP.")


# ------------------------------------------------------------------- sweeping
def sweep_wf007(rpc):
    # MOs carry Odoo's own reference, so they are found through the
    # namespaced product they build, not by name.
    mo_domain = [("product_id.default_code", "like", MARKER)]
    for mo_id in rpc.search("mrp.production", mo_domain):
        try:
            rpc.call("mrp.production", "action_cancel", [mo_id])
        except OdooRPCError:
            pass
    sweep_model(rpc, "mrp.production", mo_domain)
    sweep_model(rpc, "sale.order", [("name", "like", MARKER)])
    sweep_model(rpc, "mrp.bom", [("code", "like", MARKER)])
    product_ids = rpc.search("product.product", [("default_code", "like", MARKER)])
    if product_ids:
        sweep_model(rpc, "stock.lot", [("product_id", "in", product_ids)])
        sweep_model(rpc, "stock.quant", [("product_id", "in", product_ids)])
    sweep_model(rpc, "product.product", [("default_code", "like", MARKER)])
    sweep_model(rpc, "product.template", [("default_code", "like", MARKER)])
    sweep_model(rpc, "mrp.workcenter", [("name", "like", MARKER)])
    if product_ids:
        sweep_model(rpc, "quality.check", [("product_id", "in", product_ids)])


def open_namespace(ctx):
    with ctx.step(f"Sweep previous {MARKER} fixtures and open a fresh namespace"):
        sweep_wf007(ctx.adapter.rpc)
        ctx.log(f"fixture token = {_TOKEN}")


# ------------------------------------------------------------------- fixtures
def make_product(rpc, label: str, tracking: str = "none") -> int:
    """A storable product with the given tracking ('none' | 'lot' | 'serial')."""
    values = {
        "name": tag(label),
        "default_code": f"{_TOKEN}-{label}",
        "type": "consu",
        "tracking": tracking,
        "sale_ok": True,
    }
    if rpc.field_exists("product.template", "is_storable"):
        values["is_storable"] = True
    else:
        values["type"] = "product"
    return rpc.create("product.product", with_categ(rpc, values))


def product_tmpl_of(rpc, product_id: int) -> int:
    return m2o_id(rpc.read("product.product", [product_id],
                           ["product_tmpl_id"])[0]["product_tmpl_id"])


def make_bom(rpc, finished_id: int, component_id: int, qty: float = 1.0) -> int:
    return rpc.create("mrp.bom", {
        "product_tmpl_id": product_tmpl_of(rpc, finished_id),
        "code": tag("BOM"),
        "product_qty": 1.0,
        "type": "normal",
        "bom_line_ids": [(0, 0, {"product_id": component_id,
                                 "product_qty": qty})],
    })


def make_sale_order(rpc, product_id: int, qty: float = 1.0) -> tuple[int, str, int]:
    """A confirmed sale order carrying `product_id`.

    Returns (order_id, order_name, order_line_id). The order is what
    ``_prepare_lot_name`` reads through ``_get_source_sale_order()``; linking
    it to the MO via ``sale_line_id`` is done by ``make_mo`` so the traversal
    under test is the real one rather than a stub.
    """
    partner_ids = rpc.search("res.partner", [("customer_rank", ">", 0)], limit=1)
    if not partner_ids:
        partner_ids = rpc.search("res.partner", [], limit=1)
    values = {
        "partner_id": partner_ids[0],
        "order_line": [(0, 0, {"product_id": product_id,
                               "product_uom_qty": qty})],
    }
    # WF-002's dto_sale makes sale.order.order_type required=True
    # (dto_sale/models/sale_order.py:17-25, selection project / buy /
    # inventory / cost_center). Creating a sale order without it fails at the
    # database level — "null value in column order_type violates not-null
    # constraint" — behind a misleading generic access message, so it is set
    # explicitly here. 'cost_center' is chosen because dto_account's
    # confirmation gate REFUSES any analytic distribution on that type, which
    # keeps this fixture out of WF-002's analytic requirements: these orders
    # exist only to give _prepare_lot_name a reachable SO name and are never
    # confirmed.
    if rpc.field_exists("sale.order", "order_type"):
        values["order_type"] = "cost_center"
    order_id = rpc.create("sale.order", values)
    name = rpc.read("sale.order", [order_id], ["name"])[0]["name"]
    line_ids = rpc.search("sale.order.line", [("order_id", "=", order_id)])
    return order_id, name, line_ids[0]


def make_mo(rpc, finished_id: int, bom_id: int, qty: float = 1.0,
            sale_line_id: int | None = None, confirm: bool = True,
            name: str | None = None) -> int:
    # The MO name is left to Odoo's own sequence (WH/MO/000NN) rather than
    # namespaced: _prepare_lot_name derives the lot number from the MO name
    # via re.search(r"\d", name), so a token-prefixed name would produce
    # lot numbers no operator would ever see. Sweeping finds these MOs
    # through their namespaced PRODUCT instead.
    values = {
        "product_id": finished_id,
        "product_tmpl_id": product_tmpl_of(rpc, finished_id),
        "bom_id": bom_id,
        "product_qty": qty,
    }
    if name is not None:
        values["name"] = name
    if sale_line_id is not None and rpc.field_exists("mrp.production",
                                                     "sale_line_id"):
        values["sale_line_id"] = sale_line_id
    mo_id = rpc.create("mrp.production", values)
    if confirm:
        rpc.call("mrp.production", "action_confirm", [mo_id])
    return mo_id


def mo_field(rpc, mo_id: int, field: str):
    return rpc.read("mrp.production", [mo_id], [field])[0][field]


def mo_name(rpc, mo_id: int) -> str:
    return mo_field(rpc, mo_id, "name")


def producing_lots(rpc, mo_id: int) -> list[int]:
    """The MO's producing lots as a list of ids, whichever shape the target has.

    v19 renamed ``lot_producing_id`` (M2o) to ``lot_producing_ids`` (M2m) —
    "B-1: M2o -> M2m" in the source, and measured: only the M2m exists on
    d1v19. Returning a list keeps "exactly one lot" assertable on both.
    """
    if rpc.field_exists("mrp.production", "lot_producing_ids"):
        return list(mo_field(rpc, mo_id, "lot_producing_ids") or [])
    value = mo_field(rpc, mo_id, "lot_producing_id")
    return [m2o_id(value)] if value else []


def lot_info(rpc, lot_id: int) -> dict:
    return rpc.read("stock.lot", [lot_id], ["name", "auto_generated",
                                            "product_id"])[0]


def lots_for(rpc, product_id: int) -> list[dict]:
    return rpc.search_read("stock.lot", [("product_id", "=", product_id)],
                           ["name", "auto_generated"], order="id")


def set_qty_producing(rpc, mo_id: int, qty: float):
    rpc.write("mrp.production", [mo_id], {"qty_producing": qty})


def consume_components(rpc, mo_id: int, qty: float | None = None):
    """Register the raw-material consumption the UI would record.

    Without it ``button_mark_done`` returns a **Consumption Warning** action
    instead of completing — measured — because every raw move still has
    ``quantity`` 0 and ``picked`` False. Setting both is what the Produce /
    shop-floor screens do, and it is a fixture step, not an assertion.
    """
    moves = rpc.search_read("stock.move",
                            [("raw_material_production_id", "=", mo_id)],
                            ["product_uom_qty"], order="id")
    for move in moves:
        rpc.write("stock.move", [move["id"]],
                  {"quantity": qty if qty is not None else move["product_uom_qty"],
                   "picked": True})


def mark_done(rpc, mo_id: int):
    """Mark as Done, going through the same two hooks the UI does."""
    rpc.call("mrp.production", "pre_button_mark_done", [mo_id])
    return rpc.call("mrp.production", "button_mark_done", [mo_id])


def mark_done_with_backorder(rpc, mo_id: int) -> dict:
    """Complete a partially-produced MO and actually split the backorder.

    ``button_mark_done`` on a partial MO returns the
    ``mrp.production.backorder`` wizard rather than splitting. The wizard's
    ``action_backorder`` backorders only the MOs whose LINE carries
    ``to_backorder`` (mrp/wizard/mrp_production_backorder.py:42) — a wizard
    created with ``mrp_production_ids`` alone silently behaves like
    ``action_close_mo`` and produces no backorder at all. Measured; hence the
    explicit line below.

    Returns whatever ``button_mark_done`` returned, so a caller can assert
    which dialog it was.
    """
    action = rpc.call("mrp.production", "button_mark_done", [mo_id])
    if isinstance(action, dict) and action.get("res_model") == "mrp.production.backorder":
        wizard_id = rpc.create("mrp.production.backorder", {
            "mrp_production_ids": [(6, 0, [mo_id])],
            "mrp_production_backorder_line_ids": [
                (0, 0, {"mrp_production_id": mo_id, "to_backorder": True})],
        })
        rpc.call("mrp.production.backorder", "action_backorder", [wizard_id])
    return action if isinstance(action, dict) else {}


def mark_done_expecting_error(rpc, mo_id: int) -> str:
    try:
        mark_done(rpc, mo_id)
    except OdooRPCError as exc:
        return str(exc)
    return ""


def backorders_of(rpc, mo_id: int) -> list[dict]:
    """MOs split off this one, found by the '-NNN' suffix core appends."""
    base = mo_name(rpc, mo_id).rsplit("-", 1)[0]
    return rpc.search_read(
        "mrp.production",
        [("name", "like", base), ("id", "!=", mo_id)],
        ["name", "state", "product_qty"], order="name")
