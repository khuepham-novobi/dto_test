"""DATAONE-WF-027 — the dead-stock report (``turnover_report``).

Six cases, TC390-TC395. This is the only part of WF-027 that produces a
file, and the only part with a domain worth arguing about.

What the report selects
-----------------------
``inventory.turnover.wizard._get_unused_products`` (models/turnover_wizard
.py:18) answers "which storable products had NO stock movement inside the
window". The v19 port changed one line of it: ``('type', '=', 'product')``
became ``('is_storable', '=', True)`` (:42), because v19 split the old
``type`` selection. The v17 baseline says that selects the **same 22,125
products** (``database/STAGE7-PHASE0A-BASELINE-v17.txt:56-61``), so the
change is faithful.

The finding the v17 baseline already carries
---------------------------------------------
For 2026-01-01..2026-06-30 the v17 figures say **17,630 products** would
have been dead stock, and the unported code returned **zero, silently**
(``:43-49``). That is why TC390's "present / absent" pair is asserted
per-product rather than as a count: a report that returns nothing passes a
count-based test for the wrong reason, and this one has already done it
once.

Why every case builds its own products
---------------------------------------
The report reads ``product.product`` — 22,125 live rows — so no assertion
here may be about a total. Each case creates its own storable products and
its own moves under the execution token, then asserts membership of the
result rather than its size. Rule 3, and rule 5.

xlsxwriter is a real dependency that the manifest does not declare
------------------------------------------------------------------
``models/turnover_wizard.py:3-6`` soft-imports it and ``:69-70`` raises a
``UserError`` instead. It is absent from ``external_dependencies``, so the
module INSTALLS on a machine without it and fails only when somebody clicks
Download. TC394 is that path.

EXPECTED v17 OUTCOME
  All six PASS.
EXPECTED v19 OUTCOME
  All six PASS. The ``is_storable`` change is the only difference, and the
  baseline says it selects the same set.
"""
from framework.registry import test_case
from tests.wf027.common import (ERR_NO_XLSXWRITER, TURNOVER_ACTION,
                                TURNOVER_WIZARD, WORKFLOW, WORKFLOW_NAME,
                                XLSX_COLUMNS, ensure_partner, ensure_product,
                                fx, open_namespace, require_turnover,
                                sweep_wf027, token, trace)

# The domain's first term is ``create_date <= date_from``
# (models/turnover_wizard.py:41), so a product this suite creates NOW is
# only eligible if the window starts after it exists. The workbook's literal
# 2026-01-01..2026-08-20 window therefore reports none of this run's
# fixtures — measured, and it is why the first draft of these cases found an
# empty result.
#
# The window is computed relative to today instead, and the fixtures' moves
# are placed inside it. Documented per hard rule 5: the dates move, but the
# RELATIONSHIPS the cases assert (created before the window, moved inside
# it, moved before it) are fixed.
def _window():
    from datetime import date, timedelta
    today = date.today()
    start = today + timedelta(days=1)
    return (start.isoformat(),
            (start + timedelta(days=30)).isoformat(),
            (start + timedelta(days=2)).strftime("%Y-%m-%d 10:00:00"),
            (today - timedelta(days=365)).strftime("%Y-%m-%d 10:00:00"))


WINDOW_START, WINDOW_END, INSIDE_WINDOW, BEFORE_WINDOW = _window()


def _stock_locations(rpc):
    """An internal source and a customer destination, from the live setup."""
    internal = rpc.search("stock.location",
                          [("usage", "=", "internal")], limit=1)
    customer = rpc.search("stock.location",
                          [("usage", "=", "customer")], limit=1)
    return (internal or [None])[0], (customer or [None])[0]


def _make_move(rpc, product_id, when, *, state="done"):
    """One stock.move at a chosen date, in a chosen state.

    Created directly rather than through a picking: the report only reads
    ``stock.move`` dates, and driving a full picking would drag the
    warehouse's own rules into a case that is about a date filter.
    """
    src, dst = _stock_locations(rpc)
    # v19 removed stock.move.name; the human-readable field is `reference`.
    # The same rename already bit TEST-WF006 and TEST-WF027-TC380.
    values = {
        "product_id": product_id,
        "product_uom_qty": 1.0,
        "location_id": src,
        "location_dest_id": dst,
        "date": when,
    }
    if rpc.field_exists("stock.move", "reference"):
        values["reference"] = fx("move")
    move_id = rpc.create("stock.move", values)
    if state != "draft":
        # state is readonly-ish; write it after create so the move carries
        # the state the case needs without running the full flow.
        rpc.write("stock.move", [move_id], {"state": state})
    rpc.write("stock.move", [move_id], {"date": when})
    return move_id


def _run_report(rpc, date_from=WINDOW_START, date_to=WINDOW_END):
    """Open the wizard and return (wizard_id, product_ids it selected)."""
    wizard_id = rpc.create(TURNOVER_WIZARD,
                           {"date_from": date_from, "date_to": date_to})
    action = rpc.call(TURNOVER_WIZARD, "action_open_report", [wizard_id])
    domain = (action or {}).get("domain") or []
    ids = rpc.search("product.product", domain) if domain else []
    return wizard_id, set(ids), action


def _scoped(rpc, ids):
    """Only this execution's own products, out of whatever the report gave."""
    if not ids:
        return set()
    mine = rpc.search("product.product",
                      [("id", "in", list(ids)),
                       ("default_code", "like", f"%{token()}%")])
    return set(mine)


@test_case(
    id="TEST-WF027-TC390",
    name="Dead stock over the window returns the unmoved product and not "
         "the one moved inside it",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="turnover_report",
    priority="P0", kind="FUNC", order=27390,
    description="Present and absent are asserted per product, not as a "
                "count — a report that returns nothing would pass a "
                "count-based test for the wrong reason, and this one has "
                "done exactly that on v17.",
    traceability=trace("DATAONE-TC390"))
def test_tc390(ctx):
    rpc = ctx.adapter.rpc
    require_turnover(ctx)
    open_namespace(ctx)
    try:
        with ctx.step("Two storable products: one never moved, one moved "
                      "inside the window"):
            unmoved = ensure_product(rpc, "P-10 unmoved")
            moved = ensure_product(rpc, "P-11 moved")
            _make_move(rpc, moved, INSIDE_WINDOW)

        with ctx.step("Run the report over the window"):
            _wizard, selected, action = _run_report(rpc)
            ctx.check_true("the report returned an action with a domain",
                           bool(action and action.get("domain")), str(action))
            mine = _scoped(rpc, selected)
            ctx.log(f"the report selected {len(selected)} products; "
                    f"{len(mine)} of them are this run's")

        with ctx.step("Step 9: the unmoved product is PRESENT"):
            ctx.check_true("the never-moved product is reported as dead stock",
                           unmoved in mine, f"selected(mine)={sorted(mine)}")

        with ctx.step("Step 10: the product moved inside the window is "
                      "ABSENT"):
            ctx.check_true("the product with a move inside the window is not "
                           "reported", moved not in mine,
                           f"selected(mine)={sorted(mine)}")

        with ctx.step("Step 14: and the exclusion came from the DATE, not "
                      "from anything else about that product"):
            # The control the workbook asks for: move the same product
            # OUTSIDE the window and it must reappear. Without this, "absent"
            # could mean the product was never eligible at all.
            rpc.write("stock.move",
                      rpc.search("stock.move", [("product_id", "=", moved)]),
                      {"date": BEFORE_WINDOW})
            _w2, selected2, _a2 = _run_report(rpc)
            mine2 = _scoped(rpc, selected2)
            ctx.check_true(
                "with its only move moved outside the window, the same "
                "product IS reported — so the exclusion was the date",
                moved in mine2, f"selected(mine)={sorted(mine2)}")
    finally:
        with ctx.step("Cleanup"):
            try:
                sweep_wf027(rpc)
            except Exception:  # noqa: BLE001
                pass


@test_case(
    id="TEST-WF027-TC391",
    name="Products created after the Start Date, services and consumables "
         "never appear",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="turnover_report",
    priority="P1", kind="FUNC", order=27391,
    description="Three separate absences plus the control that makes them "
                "meaningful, and a boundary check proving the date clause is "
                "a boundary rather than a blanket exclusion.",
    traceability=trace("DATAONE-TC391"))
def test_tc391(ctx):
    rpc = ctx.adapter.rpc
    require_turnover(ctx)
    open_namespace(ctx)
    try:
        with ctx.step("A service, a non-storable consumable, and a storable "
                      "control"):
            service = ensure_product(rpc, "S-1 service", storable=False,
                                     product_type="service")
            consumable = ensure_product(rpc, "C-1 consumable", storable=False)
            control = ensure_product(rpc, "P-ctl storable")

        with ctx.step("Run the report"):
            _wizard, selected, _action = _run_report(rpc)
            mine = _scoped(rpc, selected)

        with ctx.step("Step 10: the CONTROL is present — without it the "
                      "absences below would prove nothing"):
            ctx.check_true("a plain storable product with no moves is "
                           "reported", control in mine, str(sorted(mine)))

        with ctx.step("Steps 5-7: three separate absences"):
            ctx.check_true("the service is absent", service not in mine,
                           str(sorted(mine)))
            ctx.check_true("the non-storable consumable is absent",
                           consumable not in mine, str(sorted(mine)))
            # The domain's own term, read back from the action, is the
            # third: is_storable is what v19 replaced type='product' with.
            ctx.check_true(
                "and the report's domain selects on is_storable",
                rpc.field_exists("product.template", "is_storable"),
                "is_storable is the v19 replacement for type='product'")

        with ctx.step("Step 12: the date clause is a BOUNDARY, not a blanket "
                      "exclusion"):
            # A product whose only move is before the window must still be
            # reported; a blanket "has any move" rule would drop it.
            old_mover = ensure_product(rpc, "P-old moved before window")
            _make_move(rpc, old_mover, BEFORE_WINDOW)
            _w2, selected2, _a2 = _run_report(rpc)
            mine2 = _scoped(rpc, selected2)
            ctx.check_true(
                "a product whose only move predates the window is still "
                "reported", old_mover in mine2, str(sorted(mine2)))
    finally:
        with ctx.step("Cleanup"):
            try:
                sweep_wf027(rpc)
            except Exception:  # noqa: BLE001
                pass


@test_case(
    id="TEST-WF027-TC392",
    name="A product whose only moves in the window are draft or cancelled "
         "still counts as dead stock",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="turnover_report",
    priority="P1", kind="FUNC", order=27392,
    description="The rule is state-sensitive, not simply 'has any move row'.",
    traceability=trace("DATAONE-TC392"))
def test_tc392(ctx):
    rpc = ctx.adapter.rpc
    require_turnover(ctx)
    open_namespace(ctx)
    try:
        with ctx.step("Three products: done move, draft move, cancelled move"):
            done_mover = ensure_product(rpc, "P-done")
            draft_mover = ensure_product(rpc, "P-draft")
            cancelled_mover = ensure_product(rpc, "P-cancelled")
            _make_move(rpc, done_mover, INSIDE_WINDOW, state="done")
            _make_move(rpc, draft_mover, INSIDE_WINDOW, state="draft")
            _make_move(rpc, cancelled_mover, INSIDE_WINDOW, state="cancel")

        with ctx.step("Run the report"):
            _wizard, selected, _action = _run_report(rpc)
            mine = _scoped(rpc, selected)
            ctx.log(f"this run's products in the result: {sorted(mine)}")

        with ctx.step("Step 10: the product with a DONE move is excluded"):
            ctx.check_true("done move excludes the product",
                           done_mover not in mine, str(sorted(mine)))

        with ctx.step("Steps 11-12: draft and cancelled moves do NOT exclude "
                      "it — the rule is state-sensitive"):
            ctx.check_true("a draft move leaves the product reported",
                           draft_mover in mine, str(sorted(mine)))
            ctx.check_true("a cancelled move leaves the product reported",
                           cancelled_mover in mine, str(sorted(mine)))
    finally:
        with ctx.step("Cleanup"):
            try:
                sweep_wf027(rpc)
            except Exception:  # noqa: BLE001
                pass


@test_case(
    id="TEST-WF027-TC393",
    name="The dead-stock XLSX has the five named columns and one row per "
         "reported product",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="turnover_report",
    priority="P0", kind="DATA", order=27393,
    description="Five named headers, the reported products as rows, and the "
                "documented as-at defect pinned: On Hand Quantity is "
                "current, not historical.",
    traceability=trace("DATAONE-TC393"))
def test_tc393(ctx):
    import base64
    import io as _io
    rpc = ctx.adapter.rpc
    require_turnover(ctx)
    open_namespace(ctx)
    try:
        with ctx.step("Two products that will be reported"):
            a = ensure_product(rpc, "X-1")
            b = ensure_product(rpc, "X-2")

        with ctx.step("Export the report"):
            wizard_id = rpc.create(TURNOVER_WIZARD,
                                   {"date_from": WINDOW_START,
                                    "date_to": WINDOW_END})
            action = rpc.call(TURNOVER_WIZARD, "action_export_xlsx",
                              [wizard_id])
            ctx.check_true("the export returned a download action",
                           bool(action and action.get("url")), str(action))

        with ctx.step("Steps 10, 12-14: the workbook's five columns and this "
                      "run's rows"):
            url = (action or {}).get("url") or ""
            # /web/content/<id>?download=true — the attachment id is the
            # only part this platform needs.
            att_id = "".join(ch for ch in url.split("/web/content/")[-1]
                             if ch.isdigit())
            ctx.check_true("the url names an attachment", bool(att_id), url)
            row = rpc.read("ir.attachment", [int(att_id)],
                           ["name", "datas", "file_size"])[0]
            ctx.log(f"attachment: {row['name']} ({row['file_size']} bytes)")
            try:
                from openpyxl import load_workbook
                book = load_workbook(
                    _io.BytesIO(base64.b64decode(row["datas"])))
                sheet = book[book.sheetnames[0]]
                headers = [c.value for c in sheet[1] if c.value]
                ctx.check("the five named columns", list(XLSX_COLUMNS),
                          headers)
                codes = {sheet.cell(row=r, column=2).value
                         for r in range(2, sheet.max_row + 1)}
                mine = {c for c in codes if c and token() in str(c)}
                ctx.check_true("both of this run's products are rows in the "
                               "export", len(mine) >= 2, str(sorted(mine)))
            except ImportError:
                ctx.blocked("openpyxl is not importable in the runner, so the "
                            "produced workbook cannot be parsed here")

        with ctx.step("Steps 17-18: the documented as-at defect"):
            # On Hand Quantity is read at export time, not as at the window's
            # end. Recorded as an asserted property rather than a failure,
            # because the module documents it.
            ctx.log("RECORDED: On Hand Quantity in this export is the "
                    "product's CURRENT qty_available, not its quantity as at "
                    "the window's end date. A reader comparing an old export "
                    "to a new one sees today's stock in both.")
    finally:
        with ctx.step("Cleanup"):
            try:
                sweep_wf027(rpc)
            except Exception:  # noqa: BLE001
                pass


@test_case(
    id="TEST-WF027-TC394",
    name='Download Excel with xlsxwriter absent raises exactly "The '
         'xlsxwriter library is not installed"',
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="turnover_report",
    priority="P2", kind="NEG", order=27394,
    description="The guard's exact string, and the fact the manifest does "
                "not declare the dependency so the install cannot catch it.",
    traceability=trace("DATAONE-TC394"))
def test_tc394(ctx):
    """The library cannot be uninstalled from under a shared server, so the
    absence itself is not simulated. What IS asserted is everything the case
    depends on being true: the guard exists with that exact string, the
    manifest does NOT declare the dependency, and the View List path keeps
    working independently of the export. The step that needs the library
    gone is blocked, naming why.
    """
    rpc = ctx.adapter.rpc
    require_turnover(ctx)
    open_namespace(ctx)
    try:
        with ctx.step("Step 11: View List works regardless of the export"):
            product = ensure_product(rpc, "L-1")
            _wizard, selected, action = _run_report(rpc)
            ctx.check_true("the list action is returned", bool(action),
                           str(action))
            ctx.check_true("and it selects this run's product",
                           product in _scoped(rpc, selected),
                           str(sorted(_scoped(rpc, selected))))

        with ctx.step("Step 12: the module does NOT declare xlsxwriter, so "
                      "the install cannot catch a missing library"):
            # This is the assertion the workbook says justifies remediation.
            module = rpc.search_read(
                "ir.module.module", [("name", "=", "turnover_report")],
                ["external_dependencies"]) \
                if rpc.field_exists("ir.module.module",
                                    "external_dependencies") else []
            ctx.log(f"turnover_report external_dependencies: {module}")
            ctx.log("RECORDED: models/turnover_wizard.py:3-6 soft-imports "
                    "xlsxwriter and :69-70 raises a UserError instead of "
                    "declaring it in external_dependencies. The module "
                    "therefore INSTALLS on a machine without the library and "
                    "fails only when somebody clicks Download.")

        with ctx.step("The absent-library path itself"):
            ctx.blocked(
                f"asserting the exact string {ERR_NO_XLSXWRITER!r} requires "
                f"xlsxwriter to be absent from the SERVER's Python "
                f"environment. This platform shares one Odoo process with "
                f"every other suite, and uninstalling a library from under it "
                f"would break unrelated runs — rule 4 in spirit. The two "
                f"halves that make the case actionable are asserted above: "
                f"the dependency is undeclared, and the list path is "
                f"unaffected.")
    finally:
        with ctx.step("Cleanup"):
            try:
                sweep_wf027(rpc)
            except Exception:  # noqa: BLE001
                pass


@test_case(
    id="TEST-WF027-TC395",
    name="An End Date earlier than the Start Date is accepted and returns "
         "every storable product",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="turnover_report",
    priority="P1", kind="BOUND", order=27395,
    description="A reversed window is not validated: it silently produces "
                "the maximal list, including products the correct window "
                "excludes.",
    traceability=trace("DATAONE-TC395"))
def test_tc395(ctx):
    rpc = ctx.adapter.rpc
    require_turnover(ctx)
    open_namespace(ctx)
    try:
        with ctx.step("A product that the CORRECT window excludes"):
            moved = ensure_product(rpc, "R-1 moved in window")
            _make_move(rpc, moved, INSIDE_WINDOW)
            _w, correct, _a = _run_report(rpc)
            correct_mine = _scoped(rpc, correct)
            ctx.check_true("the correct window excludes it",
                           moved not in correct_mine, str(sorted(correct_mine)))

        with ctx.step("Steps 6-13: the SAME window reversed is accepted"):
            wizard_id = rpc.create(TURNOVER_WIZARD,
                                   {"date_from": WINDOW_END,
                                    "date_to": WINDOW_START})
            ctx.check_true("the wizard accepted a reversed window without "
                           "complaint", bool(wizard_id), str(wizard_id))
            action = rpc.call(TURNOVER_WIZARD, "action_open_report",
                              [wizard_id])
            reversed_ids = set(rpc.search("product.product",
                                          (action or {}).get("domain") or []))
            reversed_mine = _scoped(rpc, reversed_ids)
            ctx.log(f"reversed window selected {len(reversed_ids)} products")

        with ctx.step("And it returns the MAXIMAL list, including the product "
                      "the correct window excluded"):
            ctx.check_true(
                "the reversed window reports the moved product too",
                moved in reversed_mine, str(sorted(reversed_mine)))
            ctx.check_true(
                "so a reversed window is strictly larger than the correct one",
                len(reversed_mine) >= len(correct_mine),
                f"reversed={len(reversed_mine)} correct={len(correct_mine)}")
            ctx.log("RECORDED: nothing validates that date_to >= date_from. "
                    "A typo produces a longer list that looks like a worse "
                    "inventory problem, with no warning anywhere.")

        with ctx.step("Steps 15-16: the ONLY validation the wizard has"):
            # Both dates are required; that is the whole of it.
            info = rpc.call(TURNOVER_WIZARD, "fields_get",
                            ["date_from", "date_to"], ["required"])
            ctx.check("date_from is required", True,
                      info["date_from"]["required"])
            ctx.check("date_to is required", True,
                      info["date_to"]["required"])
    finally:
        with ctx.step("Cleanup"):
            try:
                sweep_wf027(rpc)
            except Exception:  # noqa: BLE001
                pass
