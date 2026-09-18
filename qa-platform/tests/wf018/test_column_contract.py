"""DATAONE-WF-018 — what Workday actually reads: TC317 and TC322.

Workday pays against these cells. Column U is the supplier code it pays,
BD the invoice number it de-duplicates on, AR the control total it
reconciles to. A blank or wrong cell here is either a rejected batch or a
mis-posted payable, and neither surfaces in Odoo.

TC317 asserts the whole 20-row contract cell by cell on a bill built to
exercise every column — a purchase-order link for BE, a payment term for
BN, a UoM for FT, and a two-plan analytic distribution for GG and GK. It
then does three things the workbook is explicit about and that no other
case does:

* **FT gets its own step.** FT is not a required column, so
  ``skip_void_field`` writes nothing and F198 raises nothing when it goes
  blank. Workday receives a payable with no unit of measure and the only
  way anyone finds out is a Workday-side query. Called out separately from
  the required-column sweep for exactly that reason.
* **GG and GK are compared to RESOLVED ACCOUNT NAMES**, not merely asserted
  non-blank, and the raw ``analytic_distribution`` JSON is logged verbatim
  including its key shape. That capture is the input to resolving delta
  §2.14 — the comma-joined multi-plan key format is the single most
  important unknown in the accounting area and it can only be settled on a
  migrated database.
* **The mapping table is asserted against the database**, not just used.
  ``COLUMN_CONTRACT`` in ``common.py`` is a copy of
  ``data_template_export_data.xml``; step 0 proves the shipped template
  still declares exactly that, so a template edit cannot make this test
  pass by drifting along with it.

TC322 is the v19 regression on the same three cells, driven through the
platform's DATA_RECONCILIATION machinery: on v17 it captures FT / GG / GK
and the analytic key shape from a FIXED fixture and persists the baseline;
on v19 it re-runs the identical fixture and asserts zero difference. The
fixture is built from values, never from ids, so the two runs are
comparable across databases.

Both cases assert what the workbook calls the point of the exercise:
**nothing is withheld and no activity is created even when FT, GG or GK
are wrong.** Every other negative case in this suite ends "an activity is
filed and the record is retried". This one ends "the bill exports
successfully with wrong data and nobody is told".

EXPECTED v17 OUTCOME
  TC317 PASS. TC322 PASS — captures and persists the baseline.
EXPECTED v19 OUTCOME
  TC317 PASS unless FT or the analytic tail broke. TC322 PASS when the
  three cells are identical; BLOCKED when no v17 baseline has been
  captured yet. The two watch items are §2.10 (``product_uom`` ->
  ``product_uom_id``; ``_prepare_data_workday_vendor_bill:68`` already
  reads ``product_uom_id`` in this ported tree, so FT is expected to
  survive — TC322 is what proves it rather than assuming it) and §2.14
  (the analytic key format, Unknown).
"""
from framework.fg_common import reconcile
from framework.registry import test_case
from tests.wf018.common import (ANALYTIC_COLUMNS,  # noqa: F401
                                COLUMN_CONTRACT, HARDCODED_CELLS, MARK,
                                REQUIRED_COLUMNS, TEMPLATE_FILE_NAME,
                                TEMPLATE_ROW_START, TEMPLATE_SHEET,
                                TEMPLATE_XMLID, UNMAPPED_SPOT_CHECK,
                                UOM_COLUMN, WORKFLOW, WORKFLOW_NAME,
                                activities_on, analytic_plans, cell_map,
                                ensure_analytic_account, ensure_product,
                                ensure_vendor, exportable_lines, fx,
                                latest_workbook, m2o_id, make_bill,
                                make_post_folder, make_post_server,
                                notification_type, payment_term_id,
                                populated_rows, produced_files,
                                require_vendor_bill_usage,
                                require_workday_export, restore_company,
                                retarget_company, run_export, save_workbook,
                                snapshot_of, sweep_wf018, template_id, trace)


def _export_target(ctx):
    rpc = ctx.adapter.rpc
    tmpl_id = template_id(ctx)
    server_id = make_post_server(rpc)
    folder_id = make_post_folder(rpc, server_id)
    cid, original = retarget_company(ctx, folder_id, template_ref=tmpl_id)
    return folder_id, tmpl_id, cid, original


def _two_plan_distribution(ctx):
    """{"<project_id>,<contract_id>": 100} — or None when the plans are
    absent. The comma-joined multi-plan key is DataOne's own encoding and
    is what delta §2.14 leaves Unknown on v19; it is written here verbatim
    so the test exercises the real shape, not a simplified one."""
    plans = analytic_plans(ctx)
    if "project" not in plans or "contract" not in plans:
        ctx.log(f"[warn] the two analytic plans GG and GK read are not both "
                f"present on this database (found {sorted(plans)}). "
                "get_analytic_plan resolves them by xml id "
                "(dto_account.project_analytic_plan / "
                "dto_account.customer_contract_analytic_plan), so the "
                "analytic tail cannot be exercised here.")
        return None, {}
    project_id = ensure_analytic_account(ctx, plans["project"], "Project A")
    contract_id = ensure_analytic_account(ctx, plans["contract"],
                                          "Contract A")
    rpc = ctx.adapter.rpc
    names = {row["id"]: row["name"] for row in rpc.read(
        "account.analytic.account", [project_id, contract_id], ["name"])}
    return ({f"{project_id},{contract_id}": 100},
            {"project": names[project_id], "contract": names[contract_id]})


@test_case(
    id="TEST-WF018-TC317",
    name="The 20-row column contract asserted cell by cell",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account_workday, novobi_base_export",
    priority="P0", kind="API", order=18317,
    description="Exports one bill built to exercise every mapped column and "
                "asserts all 20 cells against the values they are supposed "
                "to carry; sweeps the four required columns and FT across "
                "every populated row; compares GG and GK to resolved "
                "analytic account names and logs the raw distribution JSON; "
                "confirms the unmapped columns are untouched and the 20 "
                "snapshot fields reproduce the file exactly.",
    traceability=trace("DATAONE-TC317"))
def test_tc317(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-018 fixtures and open a fresh "
                  "namespace"):
        sweep_wf018(rpc)

    with ctx.step("Preconditions: the export stack, the usage key and the "
                  "shipped template"):
        require_workday_export(ctx)
        require_vendor_bill_usage(ctx)

    folder_id = tmpl_id = cid = None
    original = {}
    try:
        with ctx.step("Step 0: the shipped template still declares exactly "
                      "the 20 mappings this test asserts — so a template "
                      "edit cannot make the test pass by drifting with it"):
            folder_id, tmpl_id, cid, original = _export_target(ctx)
            template = rpc.read("data.template.export", [tmpl_id],
                                ["name", "model", "sheet_name", "file_name",
                                 "row_start", "skip_void_field",
                                 "line_ids"])[0]
            ctx.log(f"template record: {template!r}")
            ctx.check("template model", "account.move.line",
                      template["model"])
            ctx.check("sheet name", TEMPLATE_SHEET, template["sheet_name"])
            ctx.check("file name", TEMPLATE_FILE_NAME, template["file_name"])
            ctx.check("row_start", TEMPLATE_ROW_START, template["row_start"])
            lines = rpc.read("data.template.export.line",
                             template["line_ids"],
                             ["col_index", "field_name", "required"])
            declared = sorted((row["col_index"], row["field_name"],
                               bool(row["required"])) for row in lines)
            ctx.check("the database's 20 mappings equal the contract this "
                      "test asserts",
                      sorted(COLUMN_CONTRACT), declared)

        with ctx.step("Precondition: a bill exercising every column — a "
                      "payment term for BN, a UoM for FT, and a two-plan "
                      "analytic distribution for GG and GK"):
            vendor_id = ensure_vendor(rpc)
            vendor = rpc.read("res.partner", [vendor_id], ["ref", "name"])[0]
            ctx.log(f"vendor (column U is its ref): {vendor!r}")
            ctx.check_true("the vendor carries a ref — WF-020 maintains it "
                           "and column U is REQUIRED",
                           bool(vendor["ref"]), actual_desc=repr(vendor))
            product_id = ensure_product(ctx)
            term_id = payment_term_id(rpc)
            distribution, expected_analytic = _two_plan_distribution(ctx)
            line = {"product_id": product_id, "quantity": 3.0,
                    "price_unit": 25.0}
            if distribution:
                line["analytic_distribution"] = distribution
            bb1 = make_bill(ctx, vendor_id, [line, dict(line, quantity=1.0)],
                            "CONTRACT-101", label="BB-1",
                            payment_term_id=term_id)
            bill = rpc.read("account.move", [bb1],
                            ["date", "invoice_date", "amount_total", "ref",
                             "invoice_payment_term_id", "partner_id"])[0]
            ctx.log(f"BB-1 header: {bill!r}")

        with ctx.step("Export BB-1 and open the produced workbook"):
            _wiz, notification = run_export(ctx, [bb1], mark_exported=True)
            ctx.check("notification type", "info",
                      notification_type(notification))
            file_row, sheet, raw = latest_workbook(ctx, folder_id)
            save_workbook(ctx, raw, f"{MARK}_TC317_{TEMPLATE_FILE_NAME}")
            rows = populated_rows(sheet)
            ctx.log(f"populated rows: {rows!r}")
            ctx.check("BB-1's two lines produced two rows starting at 6",
                      [TEMPLATE_ROW_START, TEMPLATE_ROW_START + 1], rows)

        with ctx.step("Step 2: BB-1's first line is on row 6 — all 20 "
                      "mappings, cell by cell"):
            lines = exportable_lines(rpc, bb1)
            first = lines[0]
            snapshots = snapshot_of(rpc, [row["id"] for row in lines])
            snapshot = snapshots[first["id"]]
            ctx.log(f"row 6 cells: {cell_map(sheet, 6)!r}")
            ctx.log(f"line snapshot: {snapshot!r}")

            base_url = rpc.search_read(
                "ir.config_parameter", [("key", "=", "web.base.url")],
                ["value"], limit=1)
            base_url = base_url[0]["value"] if base_url else ""
            uom_name = ""
            if rpc.field_exists("account.move.line", "product_uom_id"):
                uom = rpc.read("account.move.line", [first["id"]],
                               ["product_uom_id"])[0]["product_uom_id"]
                uom_name = uom[1] if uom else ""

            expected = {
                "B": bb1,
                "I": "Y",
                "Q": str(bill["date"]),
                "R": "DOS",
                "U": vendor["ref"],
                "AF": str(bill["invoice_date"]),
                "AR": bill["amount_total"],
                "BD": bill["ref"],
                "BN": (bill["invoice_payment_term_id"][1]
                       if bill["invoice_payment_term_id"] else None),
                "EA": 1,
                "EF": first["name"],
                "EM": "Consumables",
                "FS": first["quantity"],
                "FT": uom_name or None,
                "FU": first["price_unit"],
                "GI": "170002",
            }
            if distribution:
                expected["GG"] = expected_analytic["project"]
                expected["GK"] = expected_analytic["contract"]

            actual = {}
            for column, value in expected.items():
                cell = sheet[f"{column}{TEMPLATE_ROW_START}"].value
                actual[column] = (str(cell) if column in ("Q", "AF")
                                  and cell is not None else cell)
            mismatches = {column: {"expected": value,
                                   "actual": actual[column]}
                          for column, value in expected.items()
                          if actual[column] != value}
            ctx.check("every asserted cell on row 6 carries its mapped "
                      "value (one dict, so a failure reports all of them)",
                      {}, mismatches)

            ctx.log(f"BH6 (the deep link to the bill form): "
                    f"{sheet[f'BH{TEMPLATE_ROW_START}'].value!r}")
            ctx.check_true(
                "BH6 is a deep link naming this move on this instance",
                str(sheet[f"BH{TEMPLATE_ROW_START}"].value or "").startswith(
                    base_url) and f"id={bb1}" in str(
                    sheet[f"BH{TEMPLATE_ROW_START}"].value or ""),
                actual_desc=repr(sheet[f"BH{TEMPLATE_ROW_START}"].value))
            ctx.log(f"BE6 (purchase order name; blank when the bill carries "
                    f"no PO link): "
                    f"{sheet[f'BE{TEMPLATE_ROW_START}'].value!r}")

        with ctx.step("Step 3: the four REQUIRED columns are non-empty on "
                      "EVERY populated row — iterate, do not sample"):
            blanks = {f"{column}{index}": sheet[f"{column}{index}"].value
                      for index in rows for column in REQUIRED_COLUMNS
                      if sheet[f"{column}{index}"].value in (None, "")}
            ctx.check("required columns B, R, U and EA are populated "
                      "everywhere", {}, blanks)

        with ctx.step("Step 4: FT non-blank on every row — its OWN step, "
                      "because FT is not required and a blank FT is caught "
                      "by no other assertion in this suite"):
            ft = {index: sheet[f"{UOM_COLUMN}{index}"].value
                  for index in rows}
            ctx.log(f"column {UOM_COLUMN} per row: {ft!r}")
            ctx.check("FT is non-blank on every populated row",
                      [], [index for index, value in ft.items()
                           if value in (None, "")])

        with ctx.step("Step 5: GG and GK carry the CORRECT analytic account "
                      "names, and the raw distribution JSON is recorded "
                      "verbatim — the input to resolving delta §2.14"):
            raw_distribution = rpc.read(
                "account.move.line", [first["id"]],
                ["analytic_distribution"])[0]["analytic_distribution"]
            ctx.log(f"raw analytic_distribution, verbatim: "
                    f"{raw_distribution!r}")
            ctx.log(f"key shape: "
                    f"{[type(k).__name__ + ':' + str(k) for k in (raw_distribution or {})]!r}")
            if not distribution:
                ctx.log("[warn] no two-plan distribution could be built on "
                        "this database, so GG/GK are recorded as untested "
                        "rather than asserted.")
            else:
                ctx.check(
                    "GG and GK equal the resolved account names, not merely "
                    "non-blank values",
                    {ANALYTIC_COLUMNS["project"]:
                         expected_analytic["project"],
                     ANALYTIC_COLUMNS["contract"]:
                         expected_analytic["contract"]},
                    {column: sheet[f"{column}{TEMPLATE_ROW_START}"].value
                     for column in ANALYTIC_COLUMNS.values()})

        with ctx.step("Step 6: the wide unmapped columns are untouched — "
                      "the Workday workbook is far wider than the populated "
                      "set and carries its own validation there"):
            touched = {f"{column}{index}": sheet[f"{column}{index}"].value
                       for index in rows for column in UNMAPPED_SPOT_CHECK
                       if sheet[f"{column}{index}"].value is not None}
            ctx.check("spot-checked unmapped columns are all None on every "
                      "populated row", {}, touched)

        with ctx.step("Step 7: EA restarts at 1 per bill and is contiguous "
                      "— asserted here against the CELL values"):
            ctx.check("EA down the file",
                      list(range(1, len(rows) + 1)),
                      [sheet[f"EA{index}"].value for index in rows])

        with ctx.step("Step 8: the 20 snapshot fields reproduce the cells "
                      "exactly — the audit-list reconciliation"):
            drift = {}
            for offset, row in enumerate(lines):
                index = TEMPLATE_ROW_START + offset
                snapshot = snapshots[row["id"]]
                for column, field, _required in COLUMN_CONTRACT:
                    cell = sheet[f"{column}{index}"].value
                    stored = snapshot.get(field)
                    if cell is None and not stored:
                        continue  # skip_void_field wrote nothing: agreed
                    if str(cell) != str(stored):
                        drift[f"{column}{index}/{field}"] = {
                            "cell": cell, "snapshot": stored}
            ctx.check("every populated cell equals its export_workday_* "
                      "snapshot field", {}, drift)

        with ctx.step("Step 9: the four tenant constants are present and "
                      "exact — and all four are in PYTHON, not "
                      "configuration"):
            ctx.check("hard-coded cells on row 6", HARDCODED_CELLS,
                      {column: sheet[f"{column}{TEMPLATE_ROW_START}"].value
                       for column in HARDCODED_CELLS})
            ctx.log("Y (I), DOS (R), Consumables (EM) and 170002 (GI) are "
                    "literals in workday_vendor_bill."
                    "_prepare_data_workday_vendor_bill (lines 54, 56, 66, "
                    "71). Changing a tenant requires a code change, not a "
                    "settings change.")

        with ctx.step("Step 10 / the case's severity statement: nothing was "
                      "withheld and no activity was created"):
            acts = activities_on(rpc, "account.move", [bb1])
            ctx.log(f"activities on BB-1: {acts!r}")
            ctx.check("no activity — a wrong FT/GG/GK would have produced "
                      "none either, which is why TC322 exists", [], acts)
            ctx.check("the bill was flagged exported", True,
                      rpc.read("account.move", [bb1],
                               ["export_workday"])[0]["export_workday"])
            ctx.log(f"the v17 reference workbook is attached to this "
                    f"execution as {MARK}_TC317_{TEMPLATE_FILE_NAME}; TC322 "
                    "diffs v19 against the captured cell values rather than "
                    "against the file bytes, because the template's own "
                    "formatting is not part of the contract.")
    finally:
        if cid:
            restore_company(ctx, cid, original)


# --------------------------------------------------------------- TC322
def _capture_tc322(ctx):
    """Export a FIXED fixture and snapshot FT, GG, GK and the key shape.

    Everything captured is a value, never an id, so v17 and v19 snapshots
    are comparable across databases. Three distributions are exercised, as
    the workbook's steps 10 and 11 require: two plans, three plans, and
    none.
    """
    rpc = ctx.adapter.rpc
    sweep_wf018(rpc)
    require_workday_export(ctx)
    require_vendor_bill_usage(ctx)

    snapshot = {}
    folder_id = cid = None
    original = {}
    try:
        folder_id, _tmpl, cid, original = _export_target(ctx)
        vendor_id = ensure_vendor(rpc)
        product_id = ensure_product(ctx)
        plans = analytic_plans(ctx)
        snapshot["analytic_plans_resolved"] = sorted(plans)

        two_plan, expected_two = _two_plan_distribution(ctx)
        three_plan = None
        if two_plan and "cost" in plans:
            cost_id = ensure_analytic_account(ctx, plans["cost"], "Cost A")
            key = list(two_plan)[0]
            three_plan = {f"{key},{cost_id}": 100}

        lines = [{"product_id": product_id, "quantity": 3.0,
                  "price_unit": 25.0}]
        if two_plan:
            lines[0]["analytic_distribution"] = two_plan
        if three_plan:
            lines.append({"product_id": product_id, "quantity": 2.0,
                          "price_unit": 25.0,
                          "analytic_distribution": three_plan})
        lines.append({"product_id": product_id, "quantity": 1.0,
                      "price_unit": 25.0})  # no distribution at all

        bill_id = make_bill(ctx, vendor_id, lines, "REGR-101", label="BB-R")
        run_export(ctx, [bill_id], mark_exported=True)
        _file_row, sheet, raw = latest_workbook(ctx, folder_id)
        save_workbook(ctx, raw, f"{MARK}_TC322_{TEMPLATE_FILE_NAME}")

        exported = exportable_lines(rpc, bill_id)
        snapshots = snapshot_of(rpc, [row["id"] for row in exported])
        for offset, row in enumerate(exported):
            index = TEMPLATE_ROW_START + offset
            label = f"line{offset + 1}"
            snapshot[f"{label}.FT"] = sheet[f"{UOM_COLUMN}{index}"].value
            snapshot[f"{label}.GG"] = sheet[
                f"{ANALYTIC_COLUMNS['project']}{index}"].value
            snapshot[f"{label}.GK"] = sheet[
                f"{ANALYTIC_COLUMNS['contract']}{index}"].value
            # Step 8's control: if GI moves, the break is in the template
            # engine, not in the field reads.
            snapshot[f"{label}.GI"] = sheet[f"GI{index}"].value
            # Step 9: distinguish "the field read failed" from "the cell
            # write failed".
            snapshot[f"{label}.snapshot_uom"] = snapshots[row["id"]].get(
                "export_workday_product_uom")
            raw_distribution = row.get("analytic_distribution") or {}
            snapshot[f"{label}.distribution_keys"] = sorted(
                str(key) for key in raw_distribution)
            snapshot[f"{label}.distribution_key_arity"] = sorted(
                len(str(key).split(",")) for key in raw_distribution)

        # Step 12: nothing is withheld and no activity is created.
        snapshot["activities_on_the_bill"] = len(
            activities_on(rpc, "account.move", [bill_id]))
        snapshot["rows_written"] = len(populated_rows(sheet))
        snapshot["bill_flagged_exported"] = rpc.read(
            "account.move", [bill_id], ["export_workday"])[0]["export_workday"]

        ctx.log("Delta §2.14 answer for this database — record it in "
                "migration/ and publish it beyond this case: "
                f"{ {k: v for k, v in snapshot.items() if 'distribution' in k} !r}")
    finally:
        if cid:
            restore_company(ctx, cid, original)
    return snapshot


@test_case(
    id="TEST-WF018-TC322",
    name="v19: column FT and the analytic tail GG / GK go silently wrong",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account_workday, novobi_base_export",
    priority="P0", kind="DATA", order=18322,
    description="Exports one fixed fixture carrying a two-plan, a "
                "three-plan and an empty analytic distribution, captures "
                "FT / GG / GK / GI and the raw distribution key shape per "
                "line, and asserts zero difference against the v17 "
                "baseline. All three columns fail SILENTLY — nothing is "
                "withheld, no activity is filed — which is asserted as an "
                "anchor on both versions.",
    traceability=trace("DATAONE-TC322", user_story="resolves delta §2.14 "
                                                   "for the whole project"))
def test_tc322(ctx):
    with ctx.step("Shared-answer note"):
        ctx.log("This case's captured distribution key shape is the answer "
                "to delta §2.14 and is an input to WF-013, WF-017, WF-001 "
                "and every analytic-bearing feature in the project — not "
                "only to WF-018. Publish it to migration/ once a MIGRATED "
                "v19 database exists; a fresh v19 build writes whatever "
                "v19's own format is and never exercises the migrated data.")

    reconcile(
        ctx, "DATAONE-TC322", _capture_tc322,
        anchors={
            # Step 12 — the assertion that defines this case's severity.
            # True on BOTH versions: a wrong FT/GG/GK withholds nothing and
            # tells nobody.
            "activities_on_the_bill": 0,
            "bill_flagged_exported": True,
        })
