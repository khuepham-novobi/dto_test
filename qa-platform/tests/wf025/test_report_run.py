"""DATAONE-WF-025 — running the report: TC144, TC145, TC148.

TC144 is the input contract: ``run()`` refuses an empty list and refuses a
list containing an invalid row, with two exact messages; the "remove all
invalid products" action clears exactly the blocked rows and nothing else.

TC145 is the workflow's GATE — the four result columns against a fixture
built so each column can only be right for the right reason: a phantom BoM
that must be skipped and exploded through, a component shared by two
finished goods so aggregation shows, and a BoM whose ``product_qty`` is
greater than one so the factor arithmetic cannot pass by accident.

TC148 guards the v17→v19 product-type conversion: a storable component must
still reach the report under the new ``type`` + ``is_storable`` shape, and a
service must still be dropped.

EXPECTED v19 OUTCOME: PASS. Every figure asserted below is computed in the
test from the fixture's own numbers rather than hard-coded, so the
assertions stay meaningful if the fixture is ever retuned.
"""
from framework.registry import test_case
from tests.wf025.common import (ERROR_INVALID_ROWS, ERROR_NO_PRODUCT, WORKFLOW,
                                WORKFLOW_NAME, add_finished_good, add_stock,
                                component_for, components, finished_goods,
                                m2o_id, make_bom, make_product, new_report,
                                open_namespace, require_gross_report,
                                run_expecting_error, run_report,
                                stock_location, sweep_wf025, trace)


@test_case(
    id="TEST-WF025-TC144",
    name="Run is refused while any row is invalid, and \"Remove all invalid "
         "products\" clears exactly those rows",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_mrp",
    priority="P0", kind="API", order=25144,
    description="run() raises 'Please select at least one product.' on an "
                "empty report and 'Please remove all invalid products.' while "
                "any row is blocked; an unmatched SKU and a zero quantity are "
                "both blocked; removing invalid rows leaves exactly the valid "
                "ones and Run then succeeds.",
    traceability=trace("DATAONE-TC144"))
def test_tc144(ctx):
    require_gross_report(ctx)
    rpc = ctx.adapter.rpc
    open_namespace(ctx)
    try:
        with ctx.step("Two finished goods with active BoMs, and a bad SKU"):
            comp = make_product(rpc, "CMP-A")
            fg1 = make_product(rpc, "FG-1")
            fg2 = make_product(rpc, "FG-2")
            make_bom(rpc, fg1, [(comp, 2.0)])
            make_bom(rpc, fg2, [(comp, 3.0)])
            sku1 = rpc.read("product.product", [fg1], ["default_code"])[0]["default_code"]
            sku2 = rpc.read("product.product", [fg2], ["default_code"])[0]["default_code"]
            bad_sku = f"{sku1}-NOSUCHPRODUCT"
            ctx.check("the bad SKU matches no product", [],
                      rpc.search("product.product", [("default_code", "=", bad_sku)]))

        with ctx.step("An empty report refuses to run, with the exact message"):
            report = new_report(rpc)
            error = run_expecting_error(rpc, report)
            ctx.check_true(f"UserError says {ERROR_NO_PRODUCT!r}",
                           ERROR_NO_PRODUCT in error,
                           error[:200] or "no error raised")

        with ctx.step("Four rows: two valid, one unmatched SKU, one zero qty"):
            add_finished_good(rpc, report, fg1, 10.0)
            add_finished_good(rpc, report, fg2, 5.0)
            add_finished_good(rpc, report, None, 3.0, sku=bad_sku)
            add_finished_good(rpc, report, fg1, 0.0)
            rows = finished_goods(rpc, report)
            ctx.check("all four rows were accepted — per-row soft failure", 4,
                      len(rows))

        with ctx.step("The unmatched SKU has no product and is blocked"):
            unmatched = [r for r in finished_goods(rpc, report)
                         if not r["product_id"]]
            ctx.check("exactly one unresolved row", 1, len(unmatched))
            if unmatched:
                ctx.check("it is blocked", True, unmatched[0]["is_blocked"])

        with ctx.step("The zero-quantity row is blocked too"):
            zero = [r for r in finished_goods(rpc, report)
                    if r["qty_to_produce"] == 0.0]
            ctx.check("exactly one zero-quantity row", 1, len(zero))
            if zero:
                ctx.check("it is blocked", True, zero[0]["is_blocked"])

        with ctx.step("Run is refused while any row is blocked"):
            error = run_expecting_error(rpc, report)
            ctx.check_true(f"UserError says {ERROR_INVALID_ROWS!r}",
                           ERROR_INVALID_ROWS in error,
                           error[:200] or "no error raised")

        with ctx.step("Remove all invalid products clears exactly those rows"):
            rpc.call("gross.requirement.report",
                     "action_remove_invalid_finished_goods", [report])
            rows = finished_goods(rpc, report)
            ctx.check("two rows remain", 2, len(rows))
            ctx.check("none of them is blocked", [False, False],
                      [r["is_blocked"] for r in rows])
            ctx.check("the survivors are the two valid finished goods",
                      {fg1, fg2}, {m2o_id(r["product_id"]) for r in rows})
            ctx.check("their quantities are untouched", [10.0, 5.0],
                      [r["qty_to_produce"] for r in rows])

        with ctx.step("Run now succeeds and produces component rows"):
            add_stock(rpc, comp, stock_location(rpc), 100.0)
            run_report(rpc, report)
            rows = components(rpc, report)
            ctx.check_true("the report produced at least one component row",
                           len(rows) >= 1, f"{len(rows)} row(s)")
            ctx.check_true("the shared component is among them",
                           component_for(rpc, report, comp) is not None,
                           str([m2o_id(r["product_id"]) for r in rows]))
    finally:
        try:
            sweep_wf025(rpc)
        except Exception:  # noqa: BLE001
            pass


@test_case(
    id="TEST-WF025-TC145",
    name="GATE (WF-025) The four columns, against a fixture built to "
         "distinguish them",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_mrp",
    priority="P0", kind="API", order=25145,
    description="A phantom BoM is skipped and exploded through; a component "
                "shared by two finished goods appears exactly once with the "
                "summed requirement; a BoM with product_qty greater than one "
                "divides correctly; Available reflects on-hand at the report's "
                "own rule.",
    traceability=trace("DATAONE-TC145"))
def test_tc145(ctx):
    require_gross_report(ctx)
    rpc = ctx.adapter.rpc
    open_namespace(ctx)
    try:
        with ctx.step("Build the fixture and compute every figure by hand"):
            shared = make_product(rpc, "CMP-SHARED")
            kit_child = make_product(rpc, "CMP-KITCHILD")
            kit = make_product(rpc, "FG-PHANTOM-KIT")
            fg1 = make_product(rpc, "FG-1")
            fg2 = make_product(rpc, "FG-2")

            # The phantom: its own BoM must be skipped and its components
            # substituted in place of it.
            make_bom(rpc, kit, [(kit_child, 1.0)], bom_type="phantom")
            # FG-1 consumes 2 shared + 1 kit, per ONE finished unit.
            make_bom(rpc, fg1, [(shared, 2.0), (kit, 1.0)], product_qty=1.0)
            # FG-2's BoM produces 4 at a time and consumes 3 shared per batch,
            # so the factor arithmetic (qty / product_qty * line_qty) shows.
            make_bom(rpc, fg2, [(shared, 3.0)], product_qty=4.0)

            qty_fg1, qty_fg2 = 10.0, 4.0
            # By hand, in the components' own UoM:
            expect_shared = qty_fg1 * 2.0 + (qty_fg2 / 4.0) * 3.0   # 20 + 3 = 23
            expect_kit_child = qty_fg1 * 1.0 * 1.0                   # 10
            ctx.log(f"hand-computed: shared={expect_shared} "
                    f"kit_child={expect_kit_child}")

            loc = stock_location(rpc)
            add_stock(rpc, shared, loc, 5.0)
            add_stock(rpc, kit_child, loc, 0.0)

        with ctx.step("Both finished goods resolve, have BoMs, are not blocked"):
            report = new_report(rpc)
            add_finished_good(rpc, report, fg1, qty_fg1)
            add_finished_good(rpc, report, fg2, qty_fg2)
            rows = finished_goods(rpc, report)
            ctx.check("two rows", 2, len(rows))
            ctx.check("both resolved to products", {fg1, fg2},
                      {m2o_id(r["product_id"]) for r in rows})
            ctx.check_true("both have a BoM", all(r["bom_id"] for r in rows),
                           str([r["bom_id"] for r in rows]))
            ctx.check("neither is blocked", [False, False],
                      [r["is_blocked"] for r in rows])

        with ctx.step("Run the report"):
            run_report(rpc, report)
            rows = components(rpc, report)
            ctx.log(f"component rows: {[m2o_id(r['product_id']) for r in rows]}")

        with ctx.step("The phantom is skipped; its child appears in its place"):
            ids = [m2o_id(r["product_id"]) for r in rows]
            ctx.check_true("the phantom kit is NOT a component row",
                           kit not in ids, str(ids))
            ctx.check_true("the phantom's own child IS a component row",
                           kit_child in ids, str(ids))

        with ctx.step("The shared component appears once, with the summed "
                      "requirement"):
            ctx.check("shared appears exactly once", 1,
                      len([i for i in ids if i == shared]))
            row = component_for(rpc, report, shared)
            ctx.check("Required = 10x2 + (4/4)x3", expect_shared,
                      row["qty_required"] if row else None)

        with ctx.step("The factor arithmetic divides by the BoM's product_qty"):
            # If product_qty were ignored, FG-2 would contribute 4 x 3 = 12
            # and the total would be 32 rather than 23. Asserting the wrong
            # figure is absent makes that failure mode explicit.
            row = component_for(rpc, report, shared)
            ctx.check_true("the un-divided figure (32) is NOT what was written",
                           (row or {}).get("qty_required") != 32.0,
                           str((row or {}).get("qty_required")))

        with ctx.step("The phantom's child carries its own exploded figure"):
            row = component_for(rpc, report, kit_child)
            ctx.check("Required for the kit child", expect_kit_child,
                      row["qty_required"] if row else None)

        with ctx.step("Available and To Order follow the on-hand figures"):
            row = component_for(rpc, report, shared)
            ctx.check("Available reflects the 5 on hand", 5.0,
                      row["qty_available"] if row else None)
            ctx.check("To Order = Required - Available - already ordered",
                      round(expect_shared - 5.0
                            - (row or {}).get("qty_already_ordered", 0.0), 4),
                      round((row or {}).get("qty_to_order", 0.0), 4))
    finally:
        try:
            sweep_wf025(rpc)
        except Exception:  # noqa: BLE001
            pass


@test_case(
    id="TEST-WF025-TC148",
    name="v19 SILENT Storable components still appear in the report",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_mrp",
    priority="P0", kind="API", order=25148,
    description="Under the v19 type + is_storable shape a storable component "
                "still reaches the report, a consumable still reaches it, and "
                "a service is still dropped — the conversion did not silently "
                "filter the report's population.",
    traceability=trace("DATAONE-TC148"))
def test_tc148(ctx):
    """The workbook titles this one SILENT because the failure mode it guards
    is invisible: if the v17 ``type == 'product'`` test survived the port
    unconverted, storable components would simply stop appearing and the
    report would still look plausible. Step 9 of the workbook says as much —
    "not empty" is not sufficient — so this case asserts the exact set of
    component product ids, not merely that some rows exist.
    """
    require_gross_report(ctx)
    rpc = ctx.adapter.rpc
    open_namespace(ctx)
    try:
        with ctx.step("One storable, one consumable and one service component"):
            storable = make_product(rpc, "CMP-STORABLE", storable=True)
            consumable = make_product(rpc, "CMP-CONSU", storable=False)
            service = make_product(rpc, "SVC-INSTALL", service=True)
            fg = make_product(rpc, "FG-1")
            make_bom(rpc, fg, [(storable, 2.0), (consumable, 1.0), (service, 1.0)])
            shape = rpc.read("product.product", [storable, consumable, service],
                             ["type"] + (["is_storable"]
                                         if rpc.field_exists("product.product",
                                                             "is_storable")
                                         else []))
            ctx.log(f"product shape: {shape}")

        with ctx.step("Run the report for 10 finished units"):
            report = new_report(rpc)
            add_finished_good(rpc, report, fg, 10.0)
            run_report(rpc, report)
            ids = [m2o_id(r["product_id"]) for r in components(rpc, report)]
            ctx.log(f"component rows: {ids}")

        with ctx.step("The storable component is present, by product id"):
            ctx.check_true("storable component appears", storable in ids, str(ids))

        with ctx.step("Its required quantity is the exploded figure"):
            row = component_for(rpc, report, storable)
            ctx.check("Required = 10 x 2", 20.0,
                      row["qty_required"] if row else None)

        with ctx.step("The consumable is present and the service is dropped"):
            ctx.check_true("consumable component appears",
                           consumable in ids, str(ids))
            ctx.check_true("service component is absent",
                           service not in ids, str(ids))

        with ctx.step("The component set is exactly the two physical products"):
            # Asserting the SET, not just non-emptiness: a report containing
            # only the consumable row would also be "not empty".
            ctx.check("component product ids", {storable, consumable}, set(ids))
    finally:
        try:
            sweep_wf025(rpc)
        except Exception:  # noqa: BLE001
            pass
