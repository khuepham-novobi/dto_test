"""DATAONE-WF-009 — Component Shortage Auto-Substitution: shared fixtures.

Everything this suite asserts was read out of the real v19 source before it
was written (AUTOMATION_CONVENTIONS hard rule 6), in
``project-addons/dto_mrp_component_replacement/``:

* ``mrp.component.replacement.group``  — ``name`` (computed, stored),
  ``line_ids``                                    (mrp_component_replacement.py:8)
* ``mrp.component.replacement.line``   — ``group_id``, ``product_id``,
  ``sequence`` (default 10)                       (mrp_component_replacement.py:22)
* the one-group-per-product rule is a **v19 ``models.Constraint``**, not a
  ``_sql_constraints`` tuple: ``_product_uniq = models.Constraint(
  'unique(product_id)', "A product can only belong to one replacement group
  at a time.")``                                  (mrp_component_replacement.py:34)
* ``product.product.replacement_product_ids`` + the self-reference guard
  ``_check_replacement_product_ids`` raising *"A product cannot be a
  replacement of itself."*                        (product_product.py:59)
* ``mrp.production.has_substituted_components`` and
  ``action_check_component_replacements()``       (mrp_production.py:10,19)
* ``stock.move.original_component_id`` /
  ``is_component_substituted`` /
  ``action_revert_component_substitution()`` /
  ``_get_replacement_chain()``                    (stock_move.py:11,16,95,110)

Two things the workbook describes differently from the code. Neither is an
expectation being weakened — the expectation is what must be TRUE; these are
corrections to how the test OBSERVES it (hard rule 2 is untouched):

1. **The revert message.** The workbook quotes the source as *"Component
   %(product)s was manually reverted."* The actual string is
   ``'Component substitution for %(product)s was manually reverted.'``
   (stock_move.py:105). The tests assert the rendered text of the real
   string; asserting the workbook's paraphrase would fail on wording, not on
   behaviour.

2. **The UoM rule.** The workbook says a candidate in a different
   ``uom_id.category_id`` is skipped. v19 does not compare categories: it
   calls ``candidate.uom_id._has_common_reference(self.product_uom)``
   (stock_move.py:72). For products in genuinely unrelated categories the two
   agree, which is what TC141 exercises.

No fixture is reused between cases: every product, BoM and MO is created
under a per-execution token and swept at test start and in a ``finally`` that
cannot raise (hard rule 3).
"""
from __future__ import annotations

import uuid

from adapters.base import OdooRPCError
from framework.fg_common import m2o_id, make_trace  # noqa: F401 — re-exported
from framework.qa_fixtures import sweep_model, with_categ

WORKFLOW = "DATAONE-WF-009"
WORKFLOW_NAME = "Component Shortage Auto-Substitution"

trace = make_trace(WORKFLOW)

#: Everything this suite creates carries this marker, so a sweep can never
#: reach a business record and "exactly N" assertions cannot see live data.
MARKER = "WF009"
_TOKEN = f"{MARKER}-{uuid.uuid4().hex[:8].upper()}"

# Exact strings from the module, kept here so a source change surfaces as one
# failure in one place rather than eight.
SELF_REPLACEMENT_ERROR = "A product cannot be a replacement of itself."
ONE_GROUP_ERROR = "A product can only belong to one replacement group at a time."
SUBSTITUTED_TEMPLATE = (
    "Component {original} was short on stock (needed {qty}, only "
    "{available} available); automatically substituted with configured "
    "replacement {new}."
)
REVERTED_TEMPLATE = "Component substitution for {product} was manually reverted."


def fixture_token() -> str:
    return _TOKEN


def tag(name: str) -> str:
    """Namespaced fixture name: '<TOKEN> <name>'."""
    return f"{_TOKEN} {name}"


# --------------------------------------------------------------- preconditions
def require_replacement_module(ctx):
    """BLOCK unless dto_mrp_component_replacement contributed its models.

    Checked by model, not by querying ir.module.module: what the test needs
    is the schema, and a module that is 'installed' but whose registry did
    not load would pass a module-state check and then fail obscurely.
    """
    rpc = ctx.adapter.rpc
    missing = [m for m in ("mrp.component.replacement.group",
                           "mrp.component.replacement.line")
               if not rpc.model_exists(m)]
    missing += [f"stock.move.{f}" for f in
                ("original_component_id", "is_component_substituted")
                if not rpc.field_exists("stock.move", f)]
    if not rpc.field_exists("mrp.production", "has_substituted_components"):
        missing.append("mrp.production.has_substituted_components")
    if missing:
        ctx.blocked(
            f"dto_mrp_component_replacement is not contributing to "
            f"{ctx.env.key} (db={ctx.env.db}) — missing: {', '.join(missing)}. "
            f"Stage 3 must be installed (tools/uat_cleanup.sh) before this "
            f"suite can run.")


def require_mrp(ctx):
    """BLOCK when core mrp is absent — without it there is no MO to test."""
    rpc = ctx.adapter.rpc
    for model in ("mrp.production", "mrp.bom", "stock.quant"):
        if not rpc.model_exists(model):
            ctx.blocked(f"core model {model} is missing on {ctx.env.key} "
                        f"(db={ctx.env.db}); mrp is not installed.")


# ------------------------------------------------------------------- sweeping
def sweep_wf009(rpc):
    """Remove every record this suite may have left behind, in FK order.

    Ordered children-first so a parent unlink cannot fail on a dangling
    reference. Every step is best-effort: a sweep that raises would turn a
    real failure into a confusing teardown error.
    """
    # Swept by MARKER, not by this execution's token: a previous crashed run
    # left records under a different token, and leaving them behind would make
    # "exactly N" assertions depend on run history.
    like = [("name", "like", MARKER)]
    for mo_id in rpc.search("mrp.production", like):
        try:
            rpc.call("mrp.production", "action_cancel", [mo_id])
        except OdooRPCError:
            pass
    sweep_model(rpc, "mrp.production", like)
    sweep_model(rpc, "mrp.bom", [("code", "like", MARKER)])
    product_ids = rpc.search("product.product", [("default_code", "like", MARKER)])
    if product_ids:
        sweep_model(rpc, "mrp.component.replacement.line",
                    [("product_id", "in", product_ids)])
        sweep_model(rpc, "stock.quant", [("product_id", "in", product_ids)])
    sweep_model(rpc, "product.product", [("default_code", "like", MARKER)])
    sweep_model(rpc, "product.template", [("default_code", "like", MARKER)])
    # Groups are computed from their lines; an empty one is inert but noisy.
    for gid in rpc.search("mrp.component.replacement.group", []):
        grp = rpc.read("mrp.component.replacement.group", [gid], ["line_ids"])
        if grp and not grp[0].get("line_ids"):
            sweep_model(rpc, "mrp.component.replacement.group", [("id", "=", gid)])


def open_namespace(ctx):
    """Sweep first, so a previous crashed run cannot make this one flaky."""
    with ctx.step(f"Sweep previous {MARKER} fixtures and open a fresh namespace"):
        sweep_wf009(ctx.adapter.rpc)
        ctx.log(f"fixture token = {_TOKEN}")


# ------------------------------------------------------------------- fixtures
def uom_unit(rpc) -> int:
    return rpc.ref("uom.product_uom_unit")


def make_product(rpc, label: str, uom_id: int | None = None) -> int:
    """A storable, single-variant component named under the token."""
    values = {
        "name": tag(label),
        "default_code": f"{_TOKEN}-{label}",
        "is_storable": True,
        "type": "consu",
        "purchase_ok": False,
    }
    if uom_id:
        values["uom_id"] = uom_id
    tmpl_field_ok = rpc.field_exists("product.template", "is_storable")
    if not tmpl_field_ok:            # v17 shape, kept so the suite can also
        values.pop("is_storable")    # run against the baseline target
        values["type"] = "product"
    return rpc.create("product.product", with_categ(rpc, values))


def set_replacements(rpc, product_id: int, other_ids: list[int]):
    """Write replacement_product_ids the way the form does (6,0,ids)."""
    return rpc.write("product.product", [product_id],
                     {"replacement_product_ids": [(6, 0, other_ids)]})


def group_of(rpc, product_id: int) -> int | None:
    line = rpc.search_read("mrp.component.replacement.line",
                           [("product_id", "=", product_id)], ["group_id"])
    return m2o_id(line[0]["group_id"]) if line else None


def group_members(rpc, group_id: int) -> list[dict]:
    """Lines of a group, sequence-ordered — the order substitution follows."""
    return rpc.search_read(
        "mrp.component.replacement.line", [("group_id", "=", group_id)],
        ["product_id", "sequence"], order="sequence, id")


_PICKING_TYPE: dict[str, int] = {}


def _picking_type(rpc, code: str) -> int:
    """First picking type of a code, cached. Used only to stage fixture stock."""
    if code not in _PICKING_TYPE:
        rows = rpc.search_read("stock.picking.type", [("code", "=", code)],
                               ["id"], limit=1, order="id")
        if not rows:
            raise AssertionError(f"no stock.picking.type with code={code!r}")
        _PICKING_TYPE[code] = rows[0]["id"]
    return _PICKING_TYPE[code]


_INVENTORY_LOC: dict[str, int | None] = {}


def _inventory_location(rpc) -> int | None:
    """The 'Inventory adjustment' virtual location, cached per process."""
    if "id" not in _INVENTORY_LOC:
        rows = rpc.search_read("stock.location", [("usage", "=", "inventory")],
                               ["complete_name"], order="id")
        preferred = [r for r in rows if "scrap" not in r["complete_name"].lower()]
        _INVENTORY_LOC["id"] = (preferred or rows)[0]["id"] if rows else None
    return _INVENTORY_LOC["id"]


def set_stock(rpc, product_id: int, location_id: int, qty: float):
    """Force on-hand to an exact quantity WITHOUT the inventory-count path.

    The obvious implementation — write ``inventory_quantity`` and call
    ``action_apply_inventory`` — cannot be used on this target. Stage 3's
    ``dto_cycle_count`` overrides ``stock.quant._apply_inventory`` and calls
    ``quant.cycle_count_category_id._calculate_scheduled_count_date(...)``
    (stock_quant.py), whose first line is ``self.ensure_one()``
    (cycle_count_category.py:23). Every product on d1v19 has an EMPTY
    cycle-count category — measured: 0 of 21,362 — so that call raises
    ``Expected singleton: cycle.count.category()`` for every product on the
    database. See TC138's docstring; it is booked as a product finding.

    So stock is moved in or out through the Inventory-adjustment virtual
    location with an ordinary ``stock.move`` instead, which reaches the same
    on-hand figure without touching the broken override. This is a fixture
    adaptation forced by a product defect, documented per
    AUTOMATION_CONVENTIONS hard rule 5 — no assertion is affected by it.
    """
    current = available_qty(rpc, product_id, location_id)
    delta = qty - current
    if abs(delta) < 0.0001:
        return
    # Located by usage, not by xmlid: none of stock.stock_location_inventory,
    # stock.location_inventory or stock.stock_location_scrapped resolves on
    # v19 (all three return None), while usage='inventory' is stable across
    # both versions. 'Inventory adjustment' is preferred over 'Scrap' so a
    # staging move is never mistaken for scrapped goods in a report.
    virtual = _inventory_location(rpc)
    if not virtual:
        raise AssertionError("no stock.location with usage='inventory'; "
                             "cannot stage stock without the count path")
    src, dst = (virtual, location_id) if delta > 0 else (location_id, virtual)
    uom_id = m2o_id(rpc.read("product.product", [product_id], ["uom_id"])[0]["uom_id"])
    # Driven through a stock.picking on PUBLIC methods only. The obvious
    # `stock.move._action_confirm/_action_assign/_action_done` sequence is
    # unavailable over RPC — "Private methods (such as
    # 'stock.move._action_confirm') cannot be called remotely" — and v19 also
    # dropped stock.move.name ("Invalid field 'name' in 'stock.move'"), so the
    # move carries no name here.
    picking_type = _picking_type(rpc, "incoming" if delta > 0 else "outgoing")
    picking_id = rpc.create("stock.picking", {
        "picking_type_id": picking_type,
        "location_id": src,
        "location_dest_id": dst,
        "origin": tag("stage-stock"),
        "move_ids": [(0, 0, {
            "product_id": product_id,
            "product_uom": uom_id,
            "product_uom_qty": abs(delta),
            "location_id": src,
            "location_dest_id": dst,
        })],
    })
    rpc.call("stock.picking", "action_confirm", [picking_id])
    rpc.call("stock.picking", "action_assign", [picking_id])
    move_ids = rpc.search("stock.move", [("picking_id", "=", picking_id)])
    rpc.write("stock.move", move_ids, {"quantity": abs(delta), "picked": True})
    rpc.call("stock.picking", "button_validate", [picking_id])


def onhand_qty(rpc, product_id: int, location_id: int) -> float:
    """Total on-hand, reserved included.

    Coverage in the module is judged as ``already_reserved + available >=
    required`` (stock_move.py:69), so a "does A cover the requirement?"
    precondition must be measured this way. ``available_qty`` below subtracts
    reservations and is the right reading for "what is left for someone
    else", which is what the candidate loop uses.
    """
    rows = rpc.search_read(
        "stock.quant",
        [("product_id", "=", product_id), ("location_id", "child_of", location_id)],
        ["quantity"])
    return sum(r["quantity"] for r in rows)


def uom_is_convertible(rpc, uom_a: int, uom_b: int) -> bool:
    """Whether two UoMs share a reference, the v19 way.

    Odoo 19 REMOVED ``uom.uom.category_id`` — reading it fails with
    "Invalid field 'category_id' on 'uom.uom'". The model now carries a
    hierarchy (``relative_uom_id`` / ``related_uom_ids`` / ``parent_path``)
    and the module tests convertibility with
    ``candidate.uom_id._has_common_reference(...)`` (stock_move.py:72).
    Two UoMs are convertible when either is in the other's related set.
    """
    if uom_a == uom_b:
        return True
    rows = rpc.read("uom.uom", [uom_a, uom_b], ["related_uom_ids"])
    by_id = {r["id"]: set(r.get("related_uom_ids") or []) | {r["id"]} for r in rows}
    return uom_b in by_id.get(uom_a, set()) or uom_a in by_id.get(uom_b, set())


def available_qty(rpc, product_id: int, location_id: int) -> float:
    rows = rpc.search_read(
        "stock.quant",
        [("product_id", "=", product_id), ("location_id", "child_of", location_id)],
        ["quantity", "reserved_quantity"])
    return sum(r["quantity"] - r["reserved_quantity"] for r in rows)


def warehouse(rpc) -> dict:
    wh = rpc.search_read(
        "stock.warehouse", [],
        ["lot_stock_id", "manufacture_steps", "pbm_loc_id", "name"],
        limit=1, order="id")
    if not wh:
        raise AssertionError("no stock.warehouse on the target")
    return wh[0]


def stock_location(rpc) -> int:
    """Where availability is actually measured for a replacement chain.

    d1v19's warehouse is configured ``pbm_sam`` — pick components, then
    manufacture, then store — so a raw move's own ``location_id`` is the
    WH/Pre-Production staging area, which holds nothing until the upstream
    pick completes. ``_get_replacement_source_location`` (stock_move.py:123)
    deliberately walks to the oldest still-open ancestor and uses ITS
    location, i.e. WH/Stock. Fixtures must therefore stock WH/Stock, and
    every "available quantity" assertion must read it there.
    """
    return m2o_id(warehouse(rpc)["lot_stock_id"])


def is_multi_step(rpc) -> bool:
    return warehouse(rpc)["manufacture_steps"] in ("pbm", "pbm_sam")


def pick_moves(rpc, mo_id: int) -> list[dict]:
    """The upstream 'pick components' moves feeding this MO's raw moves.

    Found through move_orig_ids on the raw move rather than by picking-type,
    so it keeps working whatever the route is named.
    """
    raws = rpc.search_read("stock.move",
                           [("raw_material_production_id", "=", mo_id)],
                           ["move_orig_ids"], order="id")
    orig_ids = [i for r in raws for i in (r.get("move_orig_ids") or [])]
    if not orig_ids:
        return []
    return rpc.search_read(
        "stock.move", [("id", "in", orig_ids)],
        ["product_id", "product_uom", "product_uom_qty", "location_id",
         "picking_id", "state"], order="id")


def make_bom(rpc, finished_id: int, component_id: int, qty: float = 1.0) -> int:
    return rpc.create("mrp.bom", {
        "product_tmpl_id": product_tmpl_of(rpc, finished_id),
        "code": tag("BOM"),
        "product_qty": 1.0,
        "type": "normal",
        "bom_line_ids": [(0, 0, {"product_id": component_id, "product_qty": qty})],
    })


def product_tmpl_of(rpc, product_id: int) -> int:
    rec = rpc.read("product.product", [product_id], ["product_tmpl_id"])
    return m2o_id(rec[0]["product_tmpl_id"])


def make_mo(rpc, finished_id: int, bom_id: int, qty: float = 1.0) -> int:
    """A confirmed MO — the state every substitution case starts from."""
    mo_id = rpc.create("mrp.production", {
        "product_id": finished_id,
        "product_tmpl_id": product_tmpl_of(rpc, finished_id),
        "bom_id": bom_id,
        "product_qty": qty,
        "name": tag("MO"),
    })
    rpc.call("mrp.production", "action_confirm", [mo_id])
    return mo_id


def raw_move(rpc, mo_id: int) -> dict:
    """The MO's single raw move, with the fields every case reads."""
    fields = ["product_id", "product_uom", "product_uom_qty", "location_id",
              "original_component_id", "is_component_substituted", "state"]
    moves = rpc.search_read("stock.move", [("raw_material_production_id", "=", mo_id)],
                            fields, order="id")
    if len(moves) != 1:
        raise AssertionError(f"expected exactly 1 raw move on the MO, got {len(moves)}")
    return moves[0]


def chatter(rpc, mo_id: int) -> list[str]:
    """Rendered chatter bodies on the MO, oldest first, tags stripped."""
    import re
    msgs = rpc.search_read("mail.message",
                           [("model", "=", "mrp.production"), ("res_id", "=", mo_id)],
                           ["body"], order="id")
    return [re.sub(r"<[^>]+>", "", m["body"] or "").strip() for m in msgs]


def substitution_messages(rpc, mo_id: int) -> list[str]:
    return [b for b in chatter(rpc, mo_id) if "short on stock" in b]
