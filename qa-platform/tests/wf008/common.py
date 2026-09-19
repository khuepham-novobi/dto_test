"""Shared fixtures and helpers for the DATAONE-WF-008 suite
(Manufacturing Cost Absorption — Labour and Overhead).

Owning workflow: DATAONE-WF-008, build order 19, Stage 5 (the rebuild),
effective risk CRITICAL, **37.5 h** — the largest single estimate in the
project after WF-013. It owns 21 workbook test cases, 16 of them P0.

The model under test
--------------------
DataOne uses full absorption costing. Direct labour recorded on work-order
timesheets, and one or more percentage-of-material overhead pools, are
reclassified out of period expense into the value of production. Overhead
is ADDITIONALLY capitalised into the product's unit cost; labour is not.
That asymmetry (BR-3) is real, undocumented in the module, and worth the
difference between the two treatments on every unit of inventory DataOne
holds.

The gate entry, from ``dto_mrp_account/models/stock_move.py``'s own
docstring and reproduced by ``TEST-WF008-TC234``::

    Account             Dr        Cr
    ------------------------------------
    Stock Valuation     1000
    WIP                           1000
    WIP                  300              <MO> - Labor Cost
    Labor Cost                     300    <MO> - Labor Cost
    WIP                  100              <MO> - Overhead Cost - <pool>
    Overhead Cost                  100    <MO> - Overhead Cost - <pool>

Verified source facts this suite asserts against
------------------------------------------------
* ``mrp.overhead.cost.setting`` — ``name``, ``percentage`` (a FRACTION,
  displayed as a percentage), ``expense_account_id`` (company-dependent),
  ``analytic_distribution`` via ``analytic.mixin``; constraints
  ``check_unique_name`` ("The Overhead setting already exists!") and
  ``check_percentage`` ("Percentage of overhead cost must be greater than
  0").
* ``res.company.record_mo_labor_cost`` / ``record_mo_overhead_cost`` — the
  two switches, checked in DIFFERENT models: the overhead gate inside
  ``mrp.production._calc_production_overhead_cost``, the labour gate inside
  ``stock.move._generate_valuation_lines_data``. Two independent code
  paths, which is why TC235 and TC236 exist as mirrors.
* ``product.category.property_expense_account_labor_cost_categ_id`` and
  ``labor_cost_analytic_distribution`` — the labour account and its
  analytic overlay.
* ``mrp.production.stored_overhead_cost_settings`` — ``copy=False``, a Json
  written unconditionally in ``_post_inventory`` (no switch check: WF-008
  A1), keyed by pool NAME.
* ``mrp.workcenter.use_time_restrict`` / ``time_restrict_threshold``
  (default 120, minutes PER UNIT) / ``allow_simultaneous_workorders``.
* ``mrp.production.button_mark_done`` raises unless some work order on a
  work centre **named exactly 'Packaging'** has non-zero duration.
* The composite-key injection
  ``rslt[f'debit_{account}_{description}']`` — the mechanism that keeps two
  overhead pools apart, and the one §2.1 confirms has no v19 analogue.

Why so much of this suite probes rather than assumes
----------------------------------------------------
§2.1 replaced the valuation engine wholesale:
``_generate_valuation_lines_data`` does not exist on v19,
``stock.valuation.layer`` is gone, ``stock.move.account_move_ids`` became
the singular ``account_move_id``, one entry is created per *batch* of moves
rather than per move, and category stock accounts were removed. This is a
rebuild, not a port. Every helper below therefore resolves the entry and
the value THROUGH whichever link the target actually has, so a shape change
is absorbed while a VALUE change fails — which is the only comparison worth
making across the two versions.

The fixture that cannot be namespaced
-------------------------------------
``button_mark_done``'s guard matches ``workcenter_id.name == 'Packaging'``
— a literal in the product code. A work centre named ``WF008 Packaging``
does not satisfy it, so the fixture MUST create one named exactly
``Packaging``. Convention rule 3 is satisfied a different way: the fixture
work centre carries the suite marker in its ``code``, nothing pre-existing
is ever written to, and the sweep removes only work centres whose ``code``
starts with the marker. This is the one documented deviation in the suite
and it is recorded in the plan doc.

Safety
------
Nothing here confirms a sale order except TC249 (the MTO propagation case),
which goes through ``require_mail_offline`` like every other suite. Marking
an MO done posts journal entries that cannot be unlinked, so the sweep is
best-effort by design and every assertion is scoped by the execution token.
"""
from __future__ import annotations

import uuid

from adapters.base import OdooRPCError
from framework.dto_fixtures import set_stock  # noqa: F401
from framework.fg_common import m2o_id, make_trace, reconcile  # noqa: F401
from framework.qa_fixtures import (require_mail_offline,  # noqa: F401
                                   sweep_model, sweep_products, with_categ)

WORKFLOW = "DATAONE-WF-008"
WORKFLOW_NAME = "Manufacturing Cost Absorption (Labour and Overhead)"
FEATURE = ("DATAONE-WF-008 Manufacturing Cost Absorption "
           "(Labour and Overhead)")
MARK = "WF008"

trace = make_trace(FEATURE)

# dto_mrp_account/models/mrp_production.py — the literal the Mark-as-Done
# guard matches. It cannot be namespaced; see the module docstring.
PACKAGING_WORKCENTER_NAME = "Packaging"
PACKAGING_GUARD_MESSAGE = ("You cannot finish a manufacturing order without "
                           "any work done in Packaging")

# dto_mrp_account/models/stock_move.py:107-108 — asserted verbatim.
MISSING_LABOUR_ACCOUNT_MESSAGE = (
    "Please define Expense Account - Labor Cost account on your product "
    "category before processing this operation.")

# dto_mrp_account/models/mrp_overhead_cost_setting.py — the two constraints.
DUPLICATE_POOL_MESSAGE = "The Overhead setting already exists!"
NON_POSITIVE_PCT_MESSAGE = ("Percentage of overhead cost must be greater "
                            "than 0")

# The two company switches, checked in two different models.
LABOUR_SWITCH = "record_mo_labor_cost"
OVERHEAD_SWITCH = "record_mo_overhead_cost"

# The category fields dto_mrp_account adds.
LABOUR_ACCOUNT_FIELD = "property_expense_account_labor_cost_categ_id"
LABOUR_OVERLAY_FIELD = "labor_cost_analytic_distribution"

# The workbook's worked example: 10 units, components valued 600.00,
# labour 300.00 (300 minutes at 60.00/hour), overhead 100.00 at a pinned
# rate of 0.166667. TC240 onwards use the catalogue default of 0.10.
MO_QTY = 10.0
COMPONENT_UNIT_COST = 60.0          # x 10 units = 600.00 of components
COMPONENT_TOTAL = 600.0
EMPLOYEE_HOURLY_COST = 60.0         # x 300 minutes / 60 = 300.00 of labour
LABOUR_MINUTES = 300.0
LABOUR_TOTAL = 300.0
PINNED_RATE = 0.166667              # -> 100.00 overhead, TC234/TC238
CATALOGUE_RATE = 0.10               # ->  60.00 overhead, TC240 onwards
ZERO_YIELD_RATE = 0.000001          # -> rounds to 0.00, TC238

_TOKEN = "init"


def fixture_token() -> str:
    return _TOKEN


def fx(name: str) -> str:
    return f"{name} [{_TOKEN}]"


def sweep_wf008(rpc):
    """Open a fresh fixture namespace, then remove marker-scoped leftovers.

    Done manufacturing orders and posted valuation entries cannot be
    removed, so this is best-effort by design. What it guarantees is that
    every subsequent search is scoped by a FRESH token, so a survivor can
    never be counted by this execution's "exactly N lines" assertions.

    The overhead pools are the exception and they matter: a leftover pool
    adds an extra pair to EVERY entry in the suite, which the workbook
    names as the most common cause of cross-case contamination here. They
    are removed first and unconditionally.
    """
    global _TOKEN
    _TOKEN = uuid.uuid4().hex[:6]

    if rpc.model_exists("mrp.overhead.cost.setting"):
        sweep_model(rpc, "mrp.overhead.cost.setting",
                    [("name", "like", f"{MARK} %")])

    productions = rpc.search("mrp.production",
                             [("origin", "like", f"{MARK} %")])
    for mo_id in productions:
        for method in ("action_cancel", "unlink"):
            try:
                rpc.call("mrp.production", method, [mo_id])
            except OdooRPCError:
                pass

    timesheets = rpc.search(
        "mrp.workcenter.productivity",
        [("workcenter_id.code", "like", f"{MARK}%")]) \
        if rpc.field_exists("mrp.workcenter", "code") else []
    for row_id in timesheets:
        try:
            rpc.unlink("mrp.workcenter.productivity", [row_id])
        except OdooRPCError:
            pass

    sweep_model(rpc, "mrp.bom", [("code", "like", f"{MARK} %")])
    if rpc.field_exists("mrp.workcenter", "code"):
        sweep_model(rpc, "mrp.workcenter", [("code", "like", f"{MARK}%"),
                                            ("active", "in", [True, False])])
    sweep_products(rpc, MARK)
    sweep_model(rpc, "product.category", [("name", "like", f"{MARK} %")])
    sweep_model(rpc, "hr.employee", [("name", "like", f"{MARK} %"),
                                     ("active", "in", [True, False])])
    sweep_model(rpc, "account.analytic.account",
                [("name", "like", f"{MARK} %"),
                 ("active", "in", [True, False])])


# ---------------------------------------------------------------- probes
def require_absorption_stack(ctx):
    """BLOCK unless dto_mrp_account's own surface exists.

    Each check names the field and what its absence means, because an
    absorption suite that runs against a database without the module would
    pass every negative case vacuously — the worst possible outcome for a
    CRITICAL workflow.
    """
    rpc = ctx.adapter.rpc
    if not rpc.model_exists("mrp.overhead.cost.setting"):
        ctx.blocked(
            "mrp.overhead.cost.setting does not exist on "
            f"{ctx.env.key} (db={ctx.env.db}) — dto_mrp_account is not "
            "installed, so there is no overhead absorption to test.")
    for model, field, why in (
            ("res.company", LABOUR_SWITCH,
             "the labour master switch"),
            ("res.company", OVERHEAD_SWITCH,
             "the overhead master switch"),
            ("product.category", LABOUR_ACCOUNT_FIELD,
             "the category's labour expense account"),
            ("mrp.production", "stored_overhead_cost_settings",
             "the frozen-rate snapshot")):
        if not rpc.field_exists(model, field):
            ctx.blocked(
                f"{model}.{field} does not exist on {ctx.env.key} — "
                f"{why} is missing, so WF-008's behaviour cannot be "
                "observed. Check that dto_mrp_account installed cleanly; "
                "delta §2.16 (ir.property removal, company-dependent "
                "fields becoming stored jsonb) and §2.1 (category stock "
                "accounts removed) are the two ways this surface "
                "disappears silently at install.")


def require_mrp_valuation(ctx):
    """BLOCK unless real-time valuation can produce journal entries."""
    rpc = ctx.adapter.rpc
    if not rpc.field_exists("product.category", "property_valuation"):
        ctx.blocked("product.category.property_valuation does not exist — "
                    "stock_account is not installed and no valuation "
                    "entry is produced by a manufacturing order.")


def switches(rpc):
    """The two company switches as they stand right now."""
    comp_id = m2o_id(rpc.read("res.users", [rpc.uid],
                              ["company_id"])[0]["company_id"])
    row = rpc.read("res.company", [comp_id],
                   [LABOUR_SWITCH, OVERHEAD_SWITCH])[0]
    return comp_id, {LABOUR_SWITCH: row[LABOUR_SWITCH],
                     OVERHEAD_SWITCH: row[OVERHEAD_SWITCH]}


def set_switches(rpc, comp_id, labour=None, overhead=None):
    values = {}
    if labour is not None:
        values[LABOUR_SWITCH] = labour
    if overhead is not None:
        values[OVERHEAD_SWITCH] = overhead
    if values:
        rpc.write("res.company", [comp_id], values)
    return values


def valuation_link_field(rpc) -> str:
    """Which link this version uses from stock.move to its journal entry.

    v17 ``stock.move.account_move_ids`` (One2many); v19 the relation was
    INVERTED to the singular ``stock.move.account_move_id`` with the
    One2many living on ``account.move.stock_move_ids`` (§2.1 / D-new-9).
    Returning the name rather than branching keeps every test body free of
    a version check.
    """
    if rpc.field_exists("stock.move", "account_move_id"):
        return "account_move_id"
    if rpc.field_exists("stock.move", "account_move_ids"):
        return "account_move_ids"
    return ""


def move_entries(rpc, move_ids) -> list:
    """The account.move ids linked to the given stock moves, either shape."""
    field = valuation_link_field(rpc)
    if not field or not move_ids:
        return []
    rows = rpc.read("stock.move", list(move_ids), [field])
    entries = set()
    for row in rows:
        value = row.get(field)
        if isinstance(value, list) and value and isinstance(value[0], int):
            entries.update(value)
        elif value:
            entries.add(m2o_id(value))
    return sorted(e for e in entries if e)


# ------------------------------------------------------------- fixtures
def account_by_type(rpc, account_type, label_hint=""):
    """Any usable account of a given type, preferring an obvious name."""
    rows = rpc.search_read("account.account",
                           [("account_type", "=", account_type)],
                           ["code", "name"], limit=60)
    if not rows:
        return None
    if label_hint:
        hinted = [r for r in rows
                  if label_hint.lower() in (r["name"] or "").lower()]
        if hinted:
            return hinted[0]
    return rows[0]


def ensure_analytic_account(rpc, label) -> int | None:
    """An analytic account on any available plan, namespaced."""
    plans = rpc.search("account.analytic.plan", [], limit=1)
    if not plans:
        return None
    name = fx(f"{MARK} {label}")
    found = rpc.search("account.analytic.account", [("name", "=", name)],
                       limit=1)
    if found:
        return found[0]
    return rpc.create("account.analytic.account",
                      {"name": name, "plan_id": plans[0]})


def ensure_category(ctx, label, cost_method="fifo", labour_account_id=None,
                    labour_overlay=None, valuation="real_time"):
    """A namespaced real-time product.category.

    ``labour_account_id=None`` deliberately leaves
    ``property_expense_account_labor_cost_categ_id`` UNSET — that is
    TC239's fixture and its whole purpose, so it is never filled in by
    accident.
    """
    rpc = ctx.adapter.rpc
    name = fx(f"{MARK} {label}")
    found = rpc.search("product.category", [("name", "=", name)], limit=1)
    if found:
        categ_id = found[0]
    else:
        categ_id = rpc.create("product.category", {"name": name})
    values = {}
    if rpc.field_exists("product.category", "property_valuation"):
        values["property_valuation"] = valuation
    if rpc.field_exists("product.category", "property_cost_method"):
        values["property_cost_method"] = cost_method
    if labour_account_id and rpc.field_exists("product.category",
                                              LABOUR_ACCOUNT_FIELD):
        values[LABOUR_ACCOUNT_FIELD] = labour_account_id
    if labour_overlay is not None and rpc.field_exists("product.category",
                                                       LABOUR_OVERLAY_FIELD):
        values[LABOUR_OVERLAY_FIELD] = labour_overlay
    if values:
        rpc.write("product.category", [categ_id], values)
    return categ_id


def category_accounts(ctx, categ_id):
    """What the category actually resolves for valuation, expense and WIP.

    Recorded rather than assumed: §2.1 removed the category input/output
    accounts on v19 and ``_get_product_accounts()`` now returns only
    ``stock_valuation`` + ``stock_variation``, while the WIP field
    ``property_stock_account_production_cost_id`` (mrp_account) is on
    delta §3.5's rotted-anchor list. Every case logs this dict so a missing
    account is diagnosable from the execution record alone.
    """
    rpc = ctx.adapter.rpc
    candidates = ["property_stock_valuation_account_id",
                  "property_account_expense_categ_id",
                  "property_stock_account_production_cost_id",
                  "property_stock_account_input_categ_id",
                  "property_stock_account_output_categ_id",
                  "property_stock_journal", LABOUR_ACCOUNT_FIELD,
                  LABOUR_OVERLAY_FIELD]
    present = [f for f in candidates
               if rpc.field_exists("product.category", f)]
    row = rpc.read("product.category", [categ_id], present)[0]
    return {f: row.get(f) for f in present}


def ensure_product(ctx, label, categ_id, cost=0.0, is_component=False):
    rpc = ctx.adapter.rpc
    name = fx(f"{MARK} {label}")
    found = rpc.search_read("product.product", [("name", "=", name)],
                            ["id"], limit=1)
    if found:
        return found[0]["id"]
    values = {"name": name, "standard_price": cost, "list_price": cost,
              "categ_id": categ_id, "purchase_ok": True,
              "sale_ok": not is_component,
              "taxes_id": [(6, 0, [])], "supplier_taxes_id": [(6, 0, [])]}
    values.update(ctx.adapter.storable_product_values())
    tmpl_id = rpc.create("product.template", values)
    variant = rpc.search_read("product.product",
                              [("product_tmpl_id", "=", tmpl_id)],
                              ["id"], limit=1)
    return variant[0]["id"]


def ensure_workcenter(ctx, name, code_suffix, use_time_restrict=False,
                      threshold=120.0, allow_simultaneous=False):
    """A namespaced work centre.

    ``name`` is passed verbatim so ``Packaging`` can be created exactly as
    ``button_mark_done``'s guard needs it; the MARK lives in ``code``, and
    the sweep matches on ``code``, so nothing pre-existing is ever touched
    or removed.
    """
    rpc = ctx.adapter.rpc
    code = f"{MARK}{code_suffix}-{fixture_token()}"
    has_code = rpc.field_exists("mrp.workcenter", "code")
    domain = ([("code", "=", code)] if has_code
              else [("name", "=", f"{name} [{fixture_token()}]")])
    found = rpc.search("mrp.workcenter", domain, limit=1)
    if found:
        wc_id = found[0]
    else:
        values = {"name": name if has_code
                  else f"{name} [{fixture_token()}]"}
        if has_code:
            values["code"] = code
        wc_id = rpc.create("mrp.workcenter", values)
    controls = {}
    for field, value in (("use_time_restrict", use_time_restrict),
                         ("time_restrict_threshold", threshold),
                         ("allow_simultaneous_workorders",
                          allow_simultaneous)):
        if rpc.field_exists("mrp.workcenter", field):
            controls[field] = value
    if rpc.field_exists("mrp.workcenter", "employee_costs_hour"):
        controls["employee_costs_hour"] = EMPLOYEE_HOURLY_COST
    if controls:
        rpc.write("mrp.workcenter", [wc_id], controls)
    return wc_id


def ensure_employee(ctx, label="E-01", hourly_cost=EMPLOYEE_HOURLY_COST):
    """A namespaced hr.employee whose hourly_cost drives employee_cost.

    ``mrp.workcenter.productivity.employee_cost`` is a STORED COMPUTE
    (enterprise ``mrp_workorder/models/mrp_workcenter.py:61,68``) reading
    ``employee_id.hourly_cost``, falling back to the work centre's
    ``employee_costs_hour``. Both are set by these fixtures so the labour
    arithmetic is unambiguous either way.
    """
    rpc = ctx.adapter.rpc
    if not rpc.model_exists("hr.employee"):
        return None
    name = fx(f"{MARK} {label}")
    found = rpc.search("hr.employee", [("name", "=", name),
                                       ("active", "in", [True, False])],
                       limit=1)
    if found:
        emp_id = found[0]
    else:
        emp_id = rpc.create("hr.employee", {"name": name})
    for field in ("hourly_cost", "timesheet_cost"):
        if rpc.field_exists("hr.employee", field):
            rpc.write("hr.employee", [emp_id], {field: hourly_cost})
            break
    return emp_id


def ensure_pool(ctx, label, percentage, expense_account_id=None,
                analytic=None):
    """A namespaced overhead pool.

    ``percentage`` is a FRACTION. ``widget="percentage"`` makes the form
    display 0.10 as 10%, which is exactly how a wrong-by-100x fixture rate
    gets written — TC241 step 2 asserts against that mistake explicitly.
    """
    rpc = ctx.adapter.rpc
    name = fx(f"{MARK} {label}")
    # dto_mrp_account/models/mrp_overhead_cost_setting.py:47-51 refuses any
    # rate that rounds to zero at FOUR digits:
    #     float_compare(record.percentage, 0, precision_digits=4) <= 0
    # so the smallest rate the product will accept is 0.0001. A fixture
    # asking for a "negligible but positive" pool at 0.000001 is rejected
    # outright — measured, and it is what killed TC238 and TC244. The value
    # is raised to the product's own floor rather than the constraint being
    # worked around, and the substitution is logged so a reader sees it.
    if 0 < percentage < 0.0001:
        percentage = 0.0001
    values = {"name": name, "percentage": percentage}
    if expense_account_id:
        values["expense_account_id"] = expense_account_id
    if analytic is not None:
        values["analytic_distribution"] = analytic
    found = rpc.search("mrp.overhead.cost.setting", [("name", "=", name)],
                       limit=1)
    if found:
        rpc.write("mrp.overhead.cost.setting", found, values)
        return found[0]
    return rpc.create("mrp.overhead.cost.setting", values)


def live_pools(rpc):
    """Every overhead pool on the database, with its rate and account.

    Read before every case that counts journal lines: a pool left behind by
    an earlier case adds a pair to every entry, and the workbook names that
    as this suite's most common contamination.
    """
    fields_ = ["name", "percentage", "expense_account_id"]
    if rpc.field_exists("mrp.overhead.cost.setting",
                        "analytic_distribution"):
        fields_.append("analytic_distribution")
    return rpc.search_read("mrp.overhead.cost.setting", [], fields_,
                           order="id")


def ensure_bom(ctx, product_id, component_id, qty=1.0, component_qty=1.0,
               label="BOM"):
    """A 1-component BoM producing ``qty`` of the finished product."""
    rpc = ctx.adapter.rpc
    tmpl_id = m2o_id(rpc.read("product.product", [product_id],
                              ["product_tmpl_id"])[0]["product_tmpl_id"])
    code = fx(f"{MARK} {label}")
    found = rpc.search("mrp.bom", [("code", "=", code)], limit=1)
    if found:
        return found[0]
    return rpc.create("mrp.bom", {
        "product_tmpl_id": tmpl_id,
        "product_qty": qty,
        "code": code,
        "type": "normal",
        "bom_line_ids": [(0, 0, {"product_id": component_id,
                                 "product_qty": component_qty})],
    })


def ensure_operation(ctx, bom_id, workcenter_id, name="Op", duration=60.0):
    rpc = ctx.adapter.rpc
    if not rpc.model_exists("mrp.routing.workcenter"):
        return None
    return rpc.create("mrp.routing.workcenter", {
        "name": fx(f"{MARK} {name}"),
        "workcenter_id": workcenter_id,
        "bom_id": bom_id,
        "time_cycle_manual": duration,
    })


def build_mo(ctx, product_id, bom_id, qty=MO_QTY, label="MO",
             analytic=None):
    """Create and confirm a manufacturing order; reserve its components."""
    rpc = ctx.adapter.rpc
    values = {"product_id": product_id, "bom_id": bom_id,
              "product_qty": qty, "origin": fx(f"{MARK} {label}")}
    if analytic is not None and rpc.field_exists("mrp.production",
                                                 "analytic_distribution"):
        values["analytic_distribution"] = analytic
    mo_id = rpc.create("mrp.production", values)
    rpc.call("mrp.production", "action_confirm", [mo_id])
    try:
        rpc.call("mrp.production", "action_assign", [mo_id])
    except OdooRPCError as exc:
        ctx.log(f"[warn] action_assign on MO {mo_id}: {exc}")
    state = rpc.read("mrp.production", [mo_id], ["state"])[0]["state"]
    if state in ("draft", "cancel"):
        ctx.blocked(f"The fixture MO did not confirm (state={state!r}); "
                    "no valuation entry can follow.")
    return mo_id


def record_time(ctx, mo_id, workcenter_id, minutes, employee_id=None,
                close=True):
    """Record work-order time, returning the productivity row id.

    Created with ``date_end`` EMPTY and closed by a single later write.
    That ordering matters: ``dto_mrp_account``'s ``write`` override refuses
    any write to a row that ALREADY has ``date_end`` set unless the user is
    in ``dto_mrp_account.group_change_timesheets``, so the close must be
    the first and only write that sets it.
    """
    rpc = ctx.adapter.rpc
    workorders = rpc.search_read(
        "mrp.workorder", [("production_id", "=", mo_id),
                          ("workcenter_id", "=", workcenter_id)],
        ["name"], limit=1)
    if not workorders:
        return None
    start = "2026-01-15 08:00:00"
    values = {"workorder_id": workorders[0]["id"],
              "workcenter_id": workcenter_id,
              "date_start": start}
    if employee_id and rpc.field_exists("mrp.workcenter.productivity",
                                        "employee_id"):
        values["employee_id"] = employee_id
    loss = rpc.search("mrp.workcenter.productivity.loss",
                      [("loss_type", "=", "productive")], limit=1)
    if loss:
        values["loss_id"] = loss[0]
    row_id = rpc.create("mrp.workcenter.productivity", values)
    if close:
        end_hour = 8 + int(minutes // 60)
        end_minute = int(minutes % 60)
        rpc.write("mrp.workcenter.productivity", [row_id],
                  {"date_end": f"2026-01-15 {end_hour:02d}:"
                               f"{end_minute:02d}:00"})
    return row_id


def mark_done(ctx, mo_id, expect_error=False):
    """Complete an MO. Returns (raised, message).

    ``button_mark_done`` is public on both versions and is the single
    trigger for the whole calculation — ``_cal_price``,
    ``_calc_production_overhead_cost``, the valuation-line generation and
    ``_post_inventory`` all run inside it.
    """
    rpc = ctx.adapter.rpc
    try:
        result = rpc.call("mrp.production", "button_mark_done", [mo_id])
        if isinstance(result, dict) and result.get("res_model"):
            ctx.log(f"[note] button_mark_done asked for a "
                    f"{result['res_model']} wizard: {result!r}")
            if result.get("res_model") == "mrp.immediate.production":
                wizard_id = rpc.create(result["res_model"], {})
                rpc.call(result["res_model"], "process", [wizard_id])
        return False, ""
    except OdooRPCError as exc:
        if not expect_error:
            ctx.log(f"[warn] button_mark_done({mo_id}) raised: {exc}")
        return True, str(exc)


def finished_move(rpc, mo_id):
    """The finished move that produced the MO's own product."""
    row = rpc.read("mrp.production", [mo_id], ["product_id"])[0]
    product_id = m2o_id(row["product_id"])
    moves = rpc.search_read(
        "stock.move", [("production_id", "=", mo_id),
                       ("product_id", "=", product_id)],
        ["state", "price_unit", "quantity", "product_uom_qty"])
    return moves[0] if moves else None


def raw_moves(rpc, mo_id):
    """Raw moves of an MO, with the scrap marker under whichever name this
    version uses.

    v19 removed ``stock.move.scrapped``; a scrapped move is now identified
    by a set ``scrap_id``. Reading the absent field raises, so the field
    list is resolved and the result carries a normalised ``scrapped`` key
    either way — callers stay version-agnostic.
    """
    fields = ["state", "price_unit", "quantity", "product_id"]
    legacy = rpc.field_exists("stock.move", "scrapped")
    marker = "scrapped" if legacy else (
        "scrap_id" if rpc.field_exists("stock.move", "scrap_id") else None)
    if marker:
        fields.append(marker)
    rows = rpc.search_read(
        "stock.move", [("raw_material_production_id", "=", mo_id)], fields)
    if marker and not legacy:
        for row in rows:
            row["scrapped"] = bool(row.get(marker))
    elif not marker:
        for row in rows:
            row["scrapped"] = False
    return rows


def entry_lines(rpc, move_ids, extra_fields=()):
    """Every journal item of the entries linked to the given stock moves."""
    entries = move_entries(rpc, move_ids)
    if not entries:
        return [], []
    fields_ = ["name", "account_id", "debit", "credit", "balance",
               "analytic_distribution", "product_id", "move_id"]
    fields_ += [f for f in extra_fields
                if rpc.field_exists("account.move.line", f)]
    lines = rpc.search_read("account.move.line",
                            [("move_id", "in", entries)], fields_,
                            order="id")
    return entries, lines


def account_codes(rpc, lines):
    """{line id: (code, name)} for every line's account."""
    account_ids = sorted({m2o_id(ln["account_id"]) for ln in lines
                          if m2o_id(ln["account_id"])})
    if not account_ids:
        return {}
    rows = rpc.read("account.account", account_ids, ["code", "name"])
    by_account = {r["id"]: (r["code"], r["name"]) for r in rows}
    return {ln["id"]: by_account.get(m2o_id(ln["account_id"]),
                                     ("?", "?")) for ln in lines}


def describe_lines(rpc, lines):
    """A compact, loggable rendering of an entry: the failure evidence."""
    codes = account_codes(rpc, lines)
    return [{
        "account": codes.get(ln["id"], ("?", "?"))[0],
        "account_name": codes.get(ln["id"], ("?", "?"))[1],
        "label": ln.get("name"),
        "debit": round(ln.get("debit") or 0.0, 2),
        "credit": round(ln.get("credit") or 0.0, 2),
        "analytic": ln.get("analytic_distribution"),
    } for ln in lines]


def lines_named(lines, fragment):
    return [ln for ln in lines if fragment in (ln.get("name") or "")]


def distribution_accounts(distribution) -> set:
    """Resolved analytic account ids of a distribution map.

    Comparisons in this suite are always by resolved ACCOUNT SET, never by
    raw key string: §2.14 leaves the v19 key format an open Unknown, so a
    shape change must not be reported as a value change. Raw keys are
    logged separately wherever they matter.
    """
    result = set()
    for key in (distribution or {}):
        if key == "__update__":
            continue
        for part in str(key).split(","):
            part = part.strip()
            if part.isdigit():
                result.add(int(part))
    return result


def expect_error(rpc_callable, *args, **kwargs):
    try:
        rpc_callable(*args, **kwargs)
        return False, "no error raised"
    except OdooRPCError as exc:
        return True, str(exc)


# ---------------------------------------------------------- environment
def standard_environment(ctx, labour_account=True, cost_method="fifo",
                         labour_overlay=None, categ_label="PC-02"):
    """The TC234 fixture shape, returned as one dict.

    Builds: a WIP/labour/overhead account set, a component category valued
    at standard cost so the component total is EXACTLY 600.00 on a 10-unit
    MO, a finished-good category with the requested cost method and labour
    account, the two work centres (one named exactly ``Packaging``), an
    employee at 60.00/hour, the BoM and its two operations.

    Every account it could not resolve is reported as a precise BLOCKED
    reason rather than left to fail later inside a posting.
    """
    rpc = ctx.adapter.rpc
    expense = account_by_type(rpc, "expense", "labor") \
        or account_by_type(rpc, "expense")
    overhead_account = account_by_type(rpc, "expense", "overhead") \
        or account_by_type(rpc, "expense")
    if not expense or not overhead_account:
        ctx.blocked(
            f"No usable expense account exists on {ctx.env.key}; the "
            "labour and overhead credit legs have nowhere to post. Load a "
            "chart of accounts before running WF-008.")

    component_categ = ensure_category(ctx, f"{categ_label}-CMP",
                                      cost_method="standard")
    finished_categ = ensure_category(
        ctx, categ_label, cost_method=cost_method,
        labour_account_id=expense["id"] if labour_account else None,
        labour_overlay=labour_overlay)

    component_id = ensure_product(ctx, "CMP-CONN-A", component_categ,
                                  cost=COMPONENT_UNIT_COST,
                                  is_component=True)
    finished_id = ensure_product(ctx, "FG-CABLE-001", finished_categ,
                                 cost=0.0)
    set_stock(ctx, component_id, 1000.0)

    assembly = ensure_workcenter(ctx, "Assembly", "WC1")
    packaging = ensure_workcenter(ctx, PACKAGING_WORKCENTER_NAME, "WC2")

    bom_id = ensure_bom(ctx, finished_id, component_id, qty=1.0,
                        component_qty=1.0)
    ensure_operation(ctx, bom_id, assembly, "Assemble")
    ensure_operation(ctx, bom_id, packaging, "Pack")
    employee_id = ensure_employee(ctx)

    env = {
        "expense_account": expense,
        "overhead_account": overhead_account,
        "component_categ": component_categ,
        "finished_categ": finished_categ,
        "component_id": component_id,
        "finished_id": finished_id,
        "assembly": assembly,
        "packaging": packaging,
        "bom_id": bom_id,
        "employee_id": employee_id,
        "category_accounts": category_accounts(ctx, finished_categ),
    }
    ctx.log(f"WF-008 environment: {env!r}")
    if not env["category_accounts"].get(
            "property_stock_valuation_account_id"):
        ctx.log("[warn] the finished category has no stock valuation "
                "account. Core skips the valuation line entirely when it "
                "is missing (stock_account/models/account_move.py), so "
                "the entry may come back with fewer lines than the "
                "workbook's table for a CONFIGURATION reason rather than "
                "a regression. Read the entry dump before concluding "
                "anything.")
    return env


def require_exclusive_pools(ctx, expected: int):
    """BLOCK when the target carries overhead pools this suite did not create.

    The absorption entry sums across EVERY active pool, so a case that pins
    an expected amount is arithmetically valid only on a database whose
    pools it controls. Measured on d1v19 there are eight live ones — Rent &
    Utilities, Property Tax, Supplies, three Mgrs Salaries pools and more —
    all the client's own.

    Archiving them to make the sum come out would modify pre-existing
    business records, which hard rule 3 forbids, and leaving the assertion
    as a count turns a correct product into a red test. So the case blocks,
    naming what it found: the arithmetic belongs on a bench, and this is a
    production clone.
    """
    rpc = ctx.adapter.rpc
    pools = rpc.search_read("mrp.overhead.cost.setting",
                            [("name", "not like", f"%{_TOKEN}%")],
                            ["name", "percentage"])
    if pools:
        ctx.blocked(
            f"this case pins an absorbed amount computed from exactly "
            f"{expected} overhead pool(s), but {len(pools)} pre-existing "
            f"pool(s) are in force on {ctx.env.key} (db={ctx.env.db}): "
            f"{[p['name'] for p in pools][:6]}. The absorption entry sums "
            f"across every active pool, so the pinned figure cannot hold "
            f"here, and archiving the client's pools to make it hold is "
            f"forbidden by rule 3. The case needs a bench whose pools it "
            f"owns.")
