"""Shared fixtures and helpers for the DATAONE-WF-027 suite
(Management Reporting).

Owning workflow: DATAONE-WF-027, **Stage 7**. It owns 23 workbook test
cases: TC013, TC022, TC088 and TC376-TC395.

What this workflow is
---------------------
``dto_reports`` is not a reporting engine. It defines **no QWeb report, no
spreadsheet and no ir.actions.report at all** — verified across the module.
Every "report" is a list / pivot / graph ``ir.actions.act_window`` over a
CORE model, reached from one of 14 menus, all gated on a single group::

    dto_reports.reports_module     res.groups "Review reports"
                                   (data/groups.xml:5)

``turnover_report`` adds one wizard, ``inventory.turnover.wizard``, which
is the only part of WF-027 that produces a file.

That shape decides how this suite is written: there is almost nothing to
drive, and a great deal to assert ABOUT — which action each menu serves,
which view it pins, who can see it, and what the underlying domain
actually selects.

Three fields the reports lean on, and what is wrong with them
-------------------------------------------------------------
Measured on d1v19:

======================================  =======  ==============
field                                   stored?  ``@api.depends``
======================================  =======  ==============
``mrp.production.actual_time``          no       **none**
``mrp.production.expected_time``        no       ``product_qty``
``product.template.average_manufacture_time``  no  **none**
``stock.move.date_processed``           **yes**  **none**
======================================  =======  ==============

The last row is the dangerous one: a **stored** compute with no
``@api.depends`` never recomputes after create. TC380 reports on it. The
three non-stored ones cannot be sorted, grouped or filtered on, which
TC382 and TC383 assert as a property of the feature rather than working
around.

Why several cases BLOCK rather than fail
-----------------------------------------
TC013, TC088 and TC389 are typed **TOUR** in the workbook — they assert
what a browser renders (a menu tree opening, a stat button appearing, an
inline multi-edit). TC022 is typed **MANUAL** and compares a v17 export to
a v19 one by eye. This platform drives Odoo over RPC. Each of those cases
asserts everything that IS reachable — the action, the view, the group, the
domain — and then blocks on the part that genuinely needs a browser or a
person, naming it precisely. Nothing is quietly skipped.

Rule 3 is the constant pressure here
-------------------------------------
Every one of these reports reads the client's live tables:
``mrp.production`` has 34,252 historical rows, ``product.product`` 22,125.
So no case may assert a total, and every fixture search is scoped by the
execution token. Where the workbook names an absolute figure (TC380's
"50.0 ft"), it is asserted against THIS suite's own fixtures, never against
what the database happens to hold.
"""
from __future__ import annotations

import uuid

from adapters.base import OdooRPCError
from framework.fg_common import m2o_id, make_trace  # noqa: F401 — re-exported
from framework.qa_fixtures import (sweep_model,  # noqa: F401
                                   sweep_products, with_categ)

WORKFLOW = "DATAONE-WF-027"
WORKFLOW_NAME = "Management Reporting"

trace = make_trace(WORKFLOW)

MARK = "WF027"
_TOKEN = {"value": uuid.uuid4().hex[:6]}


def fx(name: str) -> str:
    return f"{MARK}-{_TOKEN['value']} {name}"


def token() -> str:
    return _TOKEN["value"]


# ------------------------------------------------------------------ source
#: data/groups.xml:5. The category_id line was DELETED for v19 (D-new-14):
#: res.groups.category_id became privilege_id, and a group with neither is
#: v19's spelling of "hidden". TC376 asserts that absence deliberately.
REPORTS_GROUP = "dto_reports.reports_module"

#: views/reports_module.xml:4,10,16,23 — the four menus the group gates
#: directly. The other ten hang below them.
GATED_MENUS = ("dto_reports.menu_reports",
               "dto_reports.menu_delivery_reports",
               "dto_reports.vendor_rma_reports_menu",
               "dto_reports.customer_rma_reports_menu")

#: Every menu dto_reports contributes, with the file it is defined in. v17
#: carried 14 and the port recreated all 14 with the same xmlids
#: (database/STAGE7-PHASE0A-BASELINE-v17.txt:23-40), so the count is an
#: assertion and not a guess.
ALL_MENUS = GATED_MENUS + (
    "dto_reports.menu_scrap_entries",
    "dto_reports.menu_labor_efficiency",
    "dto_reports.menu_labor_hour_per_assembly",
    "dto_reports.menu_assembly_time_per_unit",
    "dto_reports.menu_manufacture_order",
    "dto_reports.menu_manufacture_order_per_day",
    "dto_reports.menu_quantity_of_mo",
    "dto_reports.menu_feet_of_cable_cut",
    "dto_reports.menu_customer_delivery_reports",
    "dto_reports.menu_vendor_delivery_reports",
)
EXPECTED_MENU_COUNT = 14

#: The report actions, and the model each reads. None of them is an
#: ir.actions.report — they are all act_window over a core model.
REPORT_ACTIONS = {
    "dto_reports.account_move_action_scrap_operation": "account.move",
    "dto_reports.dto_report_stock_move_action": "stock.move",
    "dto_reports.purchase_form_action_reports": "purchase.order",
    "dto_reports.action_orders_reports": "sale.order",
    "dto_reports.action_workcenter_labor_efficiency_list":
        "mrp.workcenter.productivity",
    "dto_reports.product_action_average_time_manufacture": "product.template",
    "dto_reports.mrp_production_action_orders_completed_per_day":
        "mrp.production",
    "dto_reports.mrp_production_action_cable_qty_completed_per_day":
        "mrp.production",
}

#: C19 rebuilt the standalone views. FOUR of the five were deleted because
#: they never rendered; only the purchase one survives, rebuilt as an
#: inheritance (views/purchase_order.xml:77-93). A test must assert the four
#: are GONE — resurrecting one would silently change what a menu serves.
DELETED_VIEWS = ("dto_reports.dto_view_move_tree",
                 "dto_reports.sale_order_tree",
                 "dto_reports.dto_reports_view_move_tree",
                 "dto_reports.mrp_workcenter_labor_efficiency_tree_view")
SURVIVING_VIEW = "dto_reports.purchase_order_tree"

TURNOVER_WIZARD = "inventory.turnover.wizard"
TURNOVER_ACTION = "turnover_report.action_inventory_turnover_wizard"

#: models/turnover_wizard.py:69-70 — the exact string when the library is
#: missing. Asserted verbatim by TC394.
ERR_NO_XLSXWRITER = "The xlsxwriter library is not installed"

#: The five columns the dead-stock export carries, read from
#: models/turnover_wizard.py:83 rather than from the workbook's prose —
#: the workbook names them loosely and the code is the contract.
XLSX_COLUMNS = ("Internal Reference", "Name", "Category",
                "On Hand Quantity", "Created On")


# ------------------------------------------------------------ preconditions
def require_reports(ctx):
    """BLOCK unless dto_reports is contributing its menus and group."""
    rpc = ctx.adapter.rpc
    if rpc.ref(REPORTS_GROUP) is None:
        ctx.blocked(
            f"{REPORTS_GROUP} does not resolve on {ctx.env.key} "
            f"(db={ctx.env.db}) — dto_reports is not installed. It is "
            f"Stage 7; without it every menu and every report action this "
            f"suite asserts is absent, and the assertions would be vacuous "
            f"rather than failing.")


def require_turnover(ctx):
    """BLOCK unless turnover_report contributed the dead-stock wizard."""
    rpc = ctx.adapter.rpc
    if not rpc.model_exists(TURNOVER_WIZARD):
        ctx.blocked(
            f"{TURNOVER_WIZARD} does not exist — turnover_report is not "
            f"installed, so the dead-stock report has nothing to drive.")


def require_timesheet_layer(ctx):
    """BLOCK when dto_mrp_account is absent — TC381's hard requirement."""
    rpc = ctx.adapter.rpc
    installed = rpc.search_read(
        "ir.module.module",
        [("name", "=", "dto_mrp_account"), ("state", "=", "installed")], ["id"])
    if not installed:
        ctx.blocked(
            "dto_mrp_account is not installed. The workbook states this as a "
            "HARD requirement for the labour reports, not a nice-to-have: "
            "the Time Sheet columns are its fields, so without it the report "
            "has nothing to show and an empty result would look like a pass.")


# ------------------------------------------------------------------ helpers
def action_of(rpc, xmlid: str) -> dict | None:
    """Read an ir.actions.act_window by xmlid, or None."""
    action_id = rpc.ref(xmlid)
    if not action_id:
        return None
    rows = rpc.search_read("ir.actions.act_window", [("id", "=", action_id)],
                           ["name", "res_model", "view_mode", "domain",
                            "context", "view_id"])
    return rows[0] if rows else None


def menu_row(rpc, xmlid: str) -> dict | None:
    menu_id = rpc.ref(xmlid)
    if not menu_id:
        return None
    # v19 renamed ir.ui.menu.groups_id -> group_ids. Probed rather than
    # assumed: TEST-WF001-TC342 fails on exactly this rename.
    group_field = ("groups_id" if rpc.field_exists("ir.ui.menu", "groups_id")
                   else "group_ids")
    rows = rpc.search_read("ir.ui.menu", [("id", "=", menu_id)],
                           ["name", "parent_id", "action", group_field])
    if not rows:
        return None
    row = rows[0]
    row["_groups"] = row.get(group_field) or []
    return row


def menu_group_field(rpc) -> str:
    return ("groups_id" if rpc.field_exists("ir.ui.menu", "groups_id")
            else "group_ids")


def user_group_field(rpc) -> str:
    return ("groups_id" if rpc.field_exists("res.users", "groups_id")
            else "group_ids")


def view_exists(rpc, xmlid: str) -> bool:
    return rpc.ref(xmlid) is not None


# ------------------------------------------------------------------ sweeping
def sweep_wf027(rpc):
    _TOKEN["value"] = uuid.uuid4().hex[:6]
    for model, domain in (
        ("mrp.production", [("name", "like", f"{MARK}-%")]),
        ("sale.order", [("name", "like", f"{MARK}-%")]),
        ("purchase.order", [("name", "like", f"{MARK}-%")]),
    ):
        for rec_id in rpc.search(model, domain):
            for method in ("action_cancel", "button_cancel", "action_draft"):
                try:
                    rpc.call(model, method, [rec_id])
                except OdooRPCError:
                    pass
            try:
                rpc.call(model, "unlink", [rec_id])
            except OdooRPCError:
                pass
    sweep_model(rpc, TURNOVER_WIZARD, [("create_uid", "!=", 0)]) \
        if False else None          # the wizard is transient; Odoo vacuums it
    sweep_products(rpc, MARK)
    sweep_model(rpc, "res.partner", [("name", "like", f"{MARK}-%"),
                                     ("user_ids", "=", False),
                                     ("active", "in", [True, False])])


def open_namespace(ctx):
    with ctx.step(f"Sweep previous {MARK} fixtures and open a fresh namespace"):
        sweep_wf027(ctx.adapter.rpc)
        ctx.log(f"fixture token = {_TOKEN['value']}")


# ------------------------------------------------------------------ fixtures
def ensure_product(rpc, label: str, *, storable: bool = True,
                   product_type: str = "consu") -> int:
    values = with_categ(rpc, {
        "name": fx(label),
        "default_code": fx(label).replace(" ", "-"),
        "type": product_type,
    })
    if rpc.field_exists("product.template", "is_storable"):
        values["is_storable"] = storable
    return rpc.create("product.product", values)


def ensure_partner(rpc, label: str, *, supplier: bool = False) -> int:
    return rpc.create("res.partner", {
        "name": fx(label),
        "supplier_rank": 1 if supplier else 0,
        "customer_rank": 0 if supplier else 1,
    })


def visible_menu_ids(rpc) -> set:
    """The menu ids this session's user can actually reach.

    **Not** ``search('ir.ui.menu', ...)``. Measured on d1v19: a user with no
    membership of ``dto_reports.reports_module`` still gets the gated menu
    back from ``search`` — ``ir.ui.menu`` does not filter by group at the
    search layer. The gate is applied in ``load_menus()``, which is what the
    web client calls, and the same user gets 32 menus back from it with none
    of the reports menus among them.

    So a security assertion written with ``search`` reports a FALSE BREACH:
    the menu looks visible when it is not. Every visibility check in this
    suite goes through here.
    """
    try:
        menus = rpc.call("ir.ui.menu", "load_menus", False)
    except OdooRPCError:
        return set()
    found: set = set()

    def walk(node):
        if isinstance(node, dict):
            if isinstance(node.get("id"), int):
                found.add(node["id"])
            for child in (node.get("children") or []):
                walk(child)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    if isinstance(menus, dict):
        for value in menus.values():
            walk(value)
    else:
        walk(menus)
    return found
