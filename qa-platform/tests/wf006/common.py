"""DATAONE-WF-006 — Shop Floor execution and the cut sheet: shared fixtures.

Read from the real v19 source before anything here was written
(AUTOMATION_CONVENTIONS hard rule 6):

* ``mrp.production.print_cut_sheet`` — the wizard: ``feet_qty``,
  ``inch_qty``, ``converted_inch_qty``, ``converted_meter_qty``,
  ``product_id``, ``cuttable_product_ids``, ``production_id``,
  ``print_report()``      (dto_mrp/wizard/print_cut_sheet_wizard.py:9-102)
* ``mrp.tolerance`` — ``min_length``, ``max_length``, ``tolerance_inches``
                                          (dto_mrp/models/mrp_tolerance.py:7)
* ``product.template.cuttable_product``   (dto_mrp/models/product_template.py:10)

**The band rule, verbatim** (print_cut_sheet_wizard.py:86-97) — TC125 is
entirely this loop::

    for tolerance in all_tolerances:
        max_length = tolerance.max_length
        if tolerance.min_length <= feet_qty and (feet_qty < max_length
                                                 or max_length == 0):
            tolerance_inches = tolerance.tolerance_inches
            break

So a band is matched on ``min_length <= feet_qty < max_length``, the lower
bound is inclusive and the upper exclusive, ``max_length == 0`` means
unbounded, and the FIRST match in search order wins.

**The conversion rule** (:64-73) — TC126 is this, and the ``round=False`` is
the point::

    feet_qty_to_inch  = ft_uom._compute_quantity(feet_qty, in_uom, round=False)
    converted_inch_qty  = feet_qty_to_inch + inch_qty
    converted_meter_qty = ft->m(feet_qty) + in->m(inch_qty)

**Out of scope on this target.** TC132–TC135 assert the timesheet layer —
the cross-work-centre concurrency guard, the time-restrict cap and the
closed-timesheet lock. All of it lives in ``dto_mrp_account``
(models/mrp_workcenter_productivity.py, models/mrp_workcenter.py), which is
still 17.0, is deliberately excluded from
``tools/uninstall_non_migrated.py``'s KEEP list, and is uninstalled on
d1v19 — measured. Those four cases BLOCK with that reason rather than
failing: the behaviour is not deployed, not broken.
"""
from __future__ import annotations

import uuid

from adapters.base import OdooRPCError
from framework.fg_common import m2o_id, make_trace  # noqa: F401 — re-exported
from framework.qa_fixtures import sweep_model, with_categ

WORKFLOW = "DATAONE-WF-006"
WORKFLOW_NAME = "Manufacturing Execution on the Shop Floor"

trace = make_trace(WORKFLOW)

MARKER = "WF006"
_TOKEN = f"{MARKER}-{uuid.uuid4().hex[:8].upper()}"

#: Exact, from print_cut_sheet_wizard.py:102.
ERROR_NO_CUTTABLE = "Please select a cuttable product to print the report"

#: Exact, from dto_mrp_account/models/mrp_workcenter_productivity.py:56.
#: The typo ("your the administrators") is in the source; TC135 requires it
#: asserted verbatim rather than corrected.
ERROR_CLOSED_TIMESHEET = ("You are not allowed to change the timesheet. \n "
                          "Please contact your the administrators.")

_SEQ = {"n": 0}


def tag(name: str) -> str:
    return f"{_TOKEN} {name}"


def fixture_token() -> str:
    return _TOKEN


# --------------------------------------------------------------- preconditions
def require_cut_sheet(ctx):
    """BLOCK unless dto_mrp contributed the cut-sheet wizard."""
    rpc = ctx.adapter.rpc
    missing = [m for m in ("mrp.production.print_cut_sheet", "mrp.tolerance")
               if not rpc.model_exists(m)]
    if not rpc.field_exists("product.template", "cuttable_product"):
        missing.append("product.template.cuttable_product")
    if missing:
        ctx.blocked(
            f"dto_mrp is not contributing the cut-sheet wizard to "
            f"{ctx.env.key} (db={ctx.env.db}) — missing: {', '.join(missing)}. "
            f"Stage 3 must be installed (tools/uat_cleanup.sh) first.")


def require_timesheet_layer(ctx):
    """BLOCK when the module owning the timesheet rules is not installed."""
    rpc = ctx.adapter.rpc
    installed = rpc.search_read(
        "ir.module.module",
        [("name", "=", "dto_mrp_account"), ("state", "=", "installed")], ["id"])
    if not installed:
        ctx.blocked(
            "the Shop Floor timesheet rules — the cross-work-centre "
            "concurrency guard, the time_restrict_threshold cap and the "
            "closed-timesheet lock — all live in dto_mrp_account "
            "(models/mrp_workcenter_productivity.py, models/mrp_workcenter.py), "
            "which is still 17.0, is deliberately excluded from "
            "tools/uninstall_non_migrated.py's KEEP list, and is uninstalled "
            "on this target. The behaviour is not deployed rather than "
            "broken; this case cannot run until dto_mrp_account is ported and "
            "added to KEEP.")


# ------------------------------------------------------------------- sweeping
def sweep_wf006(rpc):
    mo_domain = [("product_id.default_code", "like", MARKER)]
    for mo_id in rpc.search("mrp.production", mo_domain):
        try:
            rpc.call("mrp.production", "action_cancel", [mo_id])
        except OdooRPCError:
            pass
    sweep_model(rpc, "mrp.production.print_cut_sheet",
                [("production_id.product_id.default_code", "like", MARKER)])
    sweep_model(rpc, "mrp.production", mo_domain)
    sweep_model(rpc, "mrp.bom", [("code", "like", MARKER)])
    sweep_model(rpc, "product.product", [("default_code", "like", MARKER)])
    sweep_model(rpc, "product.template", [("default_code", "like", MARKER)])


def open_namespace(ctx):
    with ctx.step(f"Sweep previous {MARKER} fixtures and open a fresh namespace"):
        sweep_wf006(ctx.adapter.rpc)
        ctx.log(f"fixture token = {_TOKEN}")


# ------------------------------------------------------------------- fixtures
def make_product(rpc, label: str, cuttable: bool = False) -> int:
    values = {
        "name": tag(label),
        "default_code": f"{_TOKEN}-{label}",
        "type": "consu",
        "cuttable_product": cuttable,
    }
    if rpc.field_exists("product.template", "is_storable"):
        values["is_storable"] = True
    else:
        values["type"] = "product"
    return rpc.create("product.product", with_categ(rpc, values))


def product_tmpl_of(rpc, product_id: int) -> int:
    return m2o_id(rpc.read("product.product", [product_id],
                           ["product_tmpl_id"])[0]["product_tmpl_id"])


def make_bom(rpc, finished_id: int, component_id: int) -> int:
    return rpc.create("mrp.bom", {
        "product_tmpl_id": product_tmpl_of(rpc, finished_id),
        "code": tag("BOM"),
        "product_qty": 1.0,
        "type": "normal",
        "bom_line_ids": [(0, 0, {"product_id": component_id,
                                 "product_qty": 1.0})],
    })


def make_mo(rpc, finished_id: int, bom_id: int, qty: float = 1.0,
            confirm: bool = True) -> int:
    mo_id = rpc.create("mrp.production", {
        "product_id": finished_id,
        "product_tmpl_id": product_tmpl_of(rpc, finished_id),
        "bom_id": bom_id,
        "product_qty": qty,
    })
    if confirm:
        rpc.call("mrp.production", "action_confirm", [mo_id])
    return mo_id


def new_wizard(rpc, mo_id: int, product_id: int | None = None) -> int:
    """Open the wizard the way the MO's button does.

    ``cuttable_product_ids`` is a PLAIN Many2many with no compute
    (print_cut_sheet_wizard.py:52) — it is filled by
    ``mrp.production.action_print_cut_sheet`` (mrp_production.py:198-209),
    which builds it from ``move_finished_ids | move_raw_ids`` filtered on
    ``cuttable_product`` and passes it as a context default. Creating the
    wizard with ``production_id`` alone therefore leaves the selector empty,
    which is a fixture mistake rather than a product defect — so this helper
    calls the real action and honours the defaults it returns.
    """
    action = rpc.call("mrp.production", "action_print_cut_sheet", [mo_id])
    context = (action or {}).get("context") or {}
    if isinstance(context, str):        # older servers hand back a literal
        context = {}
    values = {"production_id": mo_id}
    for key, field in (("default_product_id", "product_id"),
                       ("default_cuttable_product_ids", "cuttable_product_ids"),
                       ("default_stock_move_ids", "stock_move_ids")):
        value = context.get(key)
        if not value:
            continue
        values[field] = [(6, 0, value)] if isinstance(value, list) else value
    if product_id is not None:
        values["product_id"] = product_id
    return rpc.create("mrp.production.print_cut_sheet", values)


def uom_factors(rpc) -> dict:
    """The real conversion factors on THIS database, by xml_id.

    Measured rather than assumed: on d1v19 a foot is 0.3047999902464 m and
    an inch 0.0253999862840074 m, not the exact 0.3048 / 0.0254. Deriving
    expectations from these values keeps the conversion assertions about the
    CONVERSION rather than about how precisely the UoM master was seeded —
    a test hard-coding 120.0 fails by 0.00006 for a reason that says nothing
    about the port.
    """
    out = {}
    for key, xmlid in (("foot", "uom.product_uom_foot"),
                       ("inch", "uom.product_uom_inch"),
                       ("meter", "uom.product_uom_meter")):
        ref = rpc.ref(xmlid)
        out[key] = (rpc.read("uom.uom", [ref], ["factor"])[0]["factor"]
                    if ref else None)
    return out


def convert(factors: dict, qty: float, frm: str, to: str) -> float:
    """``uom._compute_quantity(qty, to, round=False)`` in test-side arithmetic."""
    return qty * factors[frm] / factors[to]


def wizard_read(rpc, wizard_id: int, fields: list[str]) -> dict:
    return rpc.read("mrp.production.print_cut_sheet", [wizard_id], fields)[0]


def set_feet(rpc, wizard_id: int, feet: float) -> dict:
    """Write feet_qty and read back everything the computes produced."""
    rpc.write("mrp.production.print_cut_sheet", [wizard_id], {"feet_qty": feet})
    return wizard_read(rpc, wizard_id,
                       ["feet_qty", "inch_qty", "converted_inch_qty",
                        "converted_meter_qty"])


def tolerance_bands(rpc) -> list[dict]:
    """Every configured band, in the order ``get_tolerance`` iterates them."""
    return rpc.search_read("mrp.tolerance", [],
                           ["min_length", "max_length", "tolerance_inches"],
                           order="id")


def expected_tolerance(bands: list[dict], feet: float) -> float:
    """Mirror of ``get_tolerance`` (print_cut_sheet_wizard.py:86-97).

    Reimplemented rather than called so the test computes the expectation
    independently of the code under test; a shared helper would make the
    assertion circular.
    """
    for band in bands:
        max_length = band["max_length"]
        if band["min_length"] <= feet and (feet < max_length or max_length == 0):
            return band["tolerance_inches"]
    return 0.0
