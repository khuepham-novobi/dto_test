"""DATAONE-WF-001 — the inbound sales gate: TC337, and the manual path
TC342.

TC337 is the gate for the inbound sales channel. **Every DataOne sale
begins here**, and the analytic distribution this flow writes is the origin
of the whole analytic chain — it is what later reaches the MO (F174), the
valuation entries (F209) and the Workday export columns BG / BI / BK. A
field that lands on the wrong target, or an analytic account written in the
wrong key format, is not a sales defect; it is an accounting defect that
surfaces months later in a Workday report.

Three assertions in it are the ones a well-meaning port breaks:

* **Step 10/19 — Cost_Center must be ABSENT.** The value is present in the
  file, is resolved by the code, and is then deliberately thrown away with
  a comment (``sale_order.py:172-178``, BR-8). A developer tidying that up
  would "fix" it into the distribution and silently change every
  cost-centre allocation in the ledger. The assertion and the comment both
  have to survive.
* **Step 18 — the raw analytic JSON, recorded verbatim.** This flow is
  where the keys are WRITTEN; WF-013, WF-017 and WF-018 are where they are
  READ. Delta §2.14 leaves the comma-joined multi-plan format an open
  Unknown on v19, so if it changed, this flow writes something structurally
  valid and semantically wrong and every downstream reader is wrong with
  it, silently. The workbook calls this "the highest-value single output of
  this case".
* **Step 5 — nothing is confirmed.** Despite the error text saying "create
  and confirm", ``_process_workday_sale_order_vals`` returns a recordset it
  names ``to_confirm_orders`` and never confirms it. The orders land as
  quotations, and the confirmation gate (F220, requester_email) is merely
  ARMED. BR-10.

TC342 is the manual wizard, and the workbook types it TOUR. It is
implemented here as an ordinary model call, because
``import_requisition`` is public, takes the uploaded bytes off a Binary
field and drives the same ``_transform_…`` / ``_process_…`` pair. Its
value is scheduling: *"because it bypasses the transport entirely, TC342
exercises the complete requisition ETL with no SFTP endpoint. If E6 slips,
run TC342 and get most of TC337's, TC338's and TC339's coverage anyway."*

TC342 also carries two findings rather than assertions:

* **Step 7** — a manual import leaves NO audit record, so there is no way
  to answer "where did this order come from and what file produced it?"
  after the fact. The scheduled path's traceability is one of this flow's
  better properties and the manual path discards it.
* **Step 14, a SEC item** — a plain salesperson can run an arbitrary file
  through a pipeline that creates products, partners and analytic accounts
  and revises orders. The scheduled path's configuration is
  ``base.group_system``; the manual path's is whoever can see the menu.

EXPECTED v17 OUTCOME: PASS for both.
EXPECTED v19 OUTCOME: PASS. The workbook names ``@api.returns``' removal
from ``odoo.api`` as a TOTAL blocker (E5) — the ``base_revision`` ->
``sale_order_revision`` -> ``dto_sale_workday`` chain failing at import
time. ``dto_sale_workday``'s own test header records that this was
discharged: ``base_revision`` and ``sale_order_revision`` are OCA 19.0
builds, and the two ``product_uom`` -> ``product_uom_id`` renames at
``sale_order.py:147`` and ``:290`` were already done. So the LOUD item is
closed and what remains is the SILENT one, §2.14 — which is why step 18
logs the key shape rather than asserting a format.
"""
from framework.registry import test_case
from tests.wf001.common import (ANALYTIC_PLAN_XMLIDS,  # noqa: F401
                                AUTO_CREATED_TAG_XMLID, CSV_COLUMNS,
                                CONSUMABLE_CATEGORY_NAME, HEADER_FIELD_MAP,
                                MARK, REQUISITION_USAGE, WIZARD_MENU_XMLID,
                                WIZARD_MODEL, WORKFLOW, WORKFLOW_NAME,
                                action_order_ids, activities_on, analytic_name,
                                any_uom, contact_name, csv_bytes,
                                distribution_accounts, file_message, fx,
                                item_code, m2o_id, make_folder, make_server,
                                memo, order_lines, order_type_labels,
                                orders_for, plans_of, population_counts,
                                require_import_prerequisites,
                                require_mail_offline,
                                require_requisition_import, row, run_import,
                                run_wizard, state_and_country, sweep_wf001,
                                trace)


def _fixture_file(ctx, uom_name, labels, contact, state, zip_code="78701",
                  street="500 Main St", city="Austin"):
    """TD-WD-01's shape: two Requisition_Num, three lines, 23 columns.

    REQ-1 has two lines — one known item and one UNKNOWN item that must be
    auto-created — and carries both analytic values plus a Cost_Center that
    must be discarded. REQ-2 has one line on the known item under a
    different order type.
    """
    known = item_code("FG-CABLE-001")
    unknown = item_code("UNKNOWN-ITEM-9")
    buy_label = sorted(labels)[0]
    project_label = sorted(labels)[-1]
    common = dict(uom_name=uom_name, contact=contact, street=street,
                  city=city, state=state, zip_code=zip_code)
    rows = [
        row(requisition_num=memo("REQ-1"), internal_memo=memo("IM-1"),
            order_type_label=buy_label, item=known,
            description=fx(f"{MARK} Finished cable assembly"),
            quantity="2", unit_price="10.0", due_date="2026-09-15",
            project=analytic_name("PRJ-NEW-ALPHA"),
            contract=analytic_name("CC-ALPHA-2026"),
            cost_center=analytic_name("CCENTRE-180008"), **common),
        row(requisition_num=memo("REQ-1"), internal_memo=memo("IM-1"),
            order_type_label=buy_label, item=unknown,
            description=fx(f"{MARK} Widget nobody has seen"),
            quantity="5", unit_price="3.50", due_date="2026-09-15",
            project=analytic_name("PRJ-NEW-ALPHA"),
            contract=analytic_name("CC-ALPHA-2026"),
            cost_center=analytic_name("CCENTRE-180008"), **common),
        row(requisition_num=memo("REQ-2"), internal_memo=memo("IM-2"),
            order_type_label=project_label, item=known,
            description=fx(f"{MARK} Finished cable assembly"),
            quantity="1", unit_price="10.0", due_date="2026-09-30",
            requester="Sam Buyer", email="sam.buyer@example.com",
            supplier_memo="",
            project=analytic_name("PRJ-NEW-ALPHA"),
            contract=analytic_name("CC-ALPHA-2026"),
            cost_center=analytic_name("CCENTRE-180008"), **common),
    ]
    return rows, known, unknown, buy_label, project_label


def _ensure_known_product(ctx, code):
    """The one product the file expects to already EXIST, so the
    auto-creation assertion is about the other one only."""
    rpc = ctx.adapter.rpc
    found = rpc.search_read("product.product",
                            [("default_code", "=", code)], ["id"], limit=1)
    if found:
        return found[0]["id"]
    from framework.qa_fixtures import with_categ
    # The name carries the item CODE. sale.order's confirmed-order activity
    # renders each tracked line by its PRODUCT name, not by the line
    # description, so products that share one name make the create, update
    # and delete blocks indistinguishable from each other — measured on
    # TEST-WF001-TC339, where all three lines read "Finished cable assembly".
    values = {"name": fx(f"{MARK} Finished cable assembly {code}"),
              "default_code": code, "sale_ok": True,
              "taxes_id": [(6, 0, [])]}
    values.update(ctx.adapter.storable_product_values())
    return rpc.create("product.product", with_categ(rpc, values))


def _ensure_contact(ctx, name, street, street2, city, state_row, country_row,
                    zip_code):
    """The ship-to contact the file expects to be REUSED, created with the
    address fields in exactly the shape ``_get_partner_id`` compares.

    ``_get_partner_id`` builds ``address_vals`` with ``.strip()`` applied to
    street, street2 and city and then searches ``res.partner`` on the name
    AND every one of those six values simultaneously
    (``sale_order.py:102-114``). So the fixture must store the STRIPPED
    forms or the match this case asserts would fail for the wrong reason.
    """
    rpc = ctx.adapter.rpc
    values = {
        "name": name,
        "street": street.strip(),
        "street2": street2.strip(),
        "city": city.strip(),
        "state_id": state_row["id"],
        "country_id": country_row["id"],
        "zip": zip_code,
    }
    found = rpc.search("res.partner",
                       [(field, "=", value)
                        for field, value in values.items()], limit=1)
    return found[0] if found else rpc.create("res.partner", values)


@test_case(
    id="TEST-WF001-TC337",
    name="GATE: one file, two Requisition_Num, 23 columns, two draft orders",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_sale_workday", priority="P0", kind="API", order=1337,
    description="Drives the real requisition ETL over one 23-column file "
                "holding two requisitions and three lines, and asserts: "
                "exactly two DRAFT orders, one per distinct "
                "Requisition_Num; every header column on its named field "
                "with order_type asserted as the stored KEY; "
                "imported_from_workday on both; the line mapping including "
                "the UoM and the promised date; exactly one auto-created "
                "product in Consumable, barcoded and tagged; exactly two "
                "auto-created analytic accounts shared by all three lines "
                "at 100%; that Cost_Center is ABSENT; the ship-to contact "
                "REUSED not created; the file Done; and that nothing was "
                "confirmed.",
    traceability=trace("DATAONE-TC337"))
def test_tc337(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-001 fixtures and open a fresh "
                  "namespace"):
        sweep_wf001(rpc)

    with ctx.step("Preconditions: the requisition stack, the usage key, the "
                  "Consumable category, the auto-created tag and all three "
                  "analytic plans. Mail must be offline — the import writes "
                  "to order chatters"):
        require_requisition_import(ctx)
        require_import_prerequisites(ctx)
        require_mail_offline(ctx)
        labels = order_type_labels(ctx)
        uom_name = any_uom(ctx)
        state_row, country_row = state_and_country(ctx)
        ctx.log(f"sale.order.order_type labels -> keys: {labels!r}")
        ctx.log(f"UoM used by the fixture: {uom_name!r}")
        ctx.log(f"ship-to state/country: {state_row!r} / {country_row!r}")

    with ctx.step("Step 1: record that the unknown item and both analytic "
                  "accounts do NOT exist, and the starting population"):
        contact = contact_name("Alpha")
        rows, known, unknown, buy_label, project_label = _fixture_file(
            ctx, uom_name, labels, contact, state_row["name"])
        known_id = _ensure_known_product(ctx, known)
        partner_id = _ensure_contact(ctx, contact, "500 Main St", "Suite 20",
                                     "Austin", state_row, country_row,
                                     "78701")
        ctx.log(f"known product {known_id} ({known!r}); ship-to partner "
                f"{partner_id} ({contact!r})")
        before = population_counts(rpc)
        ctx.log(f"starting token-scoped population: {before!r}")
        ctx.check("the unknown item does not exist yet", [],
                  rpc.search("product.product",
                             [("default_code", "=", unknown),
                              ("active", "in", [True, False])]))
        ctx.check("neither analytic account exists yet", [],
                  rpc.search("account.analytic.account",
                             [("name", "in",
                               [analytic_name("PRJ-NEW-ALPHA"),
                                analytic_name("CC-ALPHA-2026")]),
                              ("active", "in", [True, False])]))
        ctx.check("and the cost-centre account does not either — its "
                  "absence afterwards is what proves BR-8", [],
                  rpc.search("account.analytic.account",
                             [("name", "=", analytic_name("CCENTRE-180008")),
                              ("active", "in", [True, False])]))

    with ctx.step("Steps 2-3: process the file through the real ETL. The "
                  "crons are replaced by the PUBLIC "
                  "action_process_sftp_files on this file's own id — "
                  "cron_process_sftp_files searches EVERY pending GET file "
                  "on the database (convention rule 3)"):
        folder_id, file_id, file_row = run_import(
            ctx, rows, file_label="requisitions_20260901")
        ctx.log(f"sftp.file after processing: {file_row!r}")
        ctx.check("the file carries the requisition usage key",
                  REQUISITION_USAGE, file_row["usage"])

    with ctx.step("Steps 4-5: exactly two orders — one per distinct "
                  "Requisition_Num regardless of line count — and both are "
                  "DRAFT. Despite the error text saying 'create and "
                  "confirm', nothing is confirmed (BR-10)"):
        distinct = sorted({entry["Requisition_Num"] for entry in rows})
        ctx.log(f"distinct Requisition_Num values in the source: "
                f"{distinct!r}")
        created = orders_for(rpc, distinct)
        for order in created:
            ctx.log(f"order {order!r}")
        ctx.check("one order per distinct requisition number",
                  len(distinct), len(created))
        ctx.check("both are quotations, not sales orders",
                  ["draft"] * len(created),
                  [order["state"] for order in created])
        by_origin = {order["origin"]: order for order in created}

    with ctx.step("Step 6: every header column landed on its named field, "
                  "with order_type asserted as the STORED KEY"):
        req1 = by_origin[memo("REQ-1")]
        source = rows[0]
        mismatches = {}
        for column, field in HEADER_FIELD_MAP.items():
            expected = source[column]
            actual = req1.get(field)
            if field == "requisition_date":
                actual = str(actual)
            if actual != expected and not (actual is False and not expected):
                mismatches[f"{column} -> {field}"] = {"expected": expected,
                                                      "actual": actual}
        ctx.check("the six header mappings (one dict, so a failure reports "
                  "all of them)", {}, mismatches)
        ctx.check("order_type is the stored KEY whose LABEL the file "
                  "carried — not the label", labels[buy_label],
                  req1["order_type"])
        ctx.check("partner_id is the ship-to contact — create mode puts it "
                  "there (sale_order.py:83-84)", partner_id,
                  m2o_id(req1["partner_id"]))
        ctx.log("Note the column name: 'emailAddress' is lower-camel while "
                "every other column is Title_Case_With_Underscores, and "
                "'Ship-To_*' uses a HYPHEN in Ship-To and underscores "
                "elsewhere. Those are Workday's own labels; a port must "
                "not tidy them.")

    with ctx.step("Step 7: imported_from_workday is True on both"):
        ctx.check("the flag", [True] * len(created),
                  [order["imported_from_workday"] for order in created])

    with ctx.step("Step 8: order 1 has two lines and order 2 has one"):
        lines1 = order_lines(rpc, req1["id"])
        req2 = by_origin[memo("REQ-2")]
        lines2 = order_lines(rpc, req2["id"])
        ctx.log(f"REQ-1 lines: {lines1!r}")
        ctx.log(f"REQ-2 lines: {lines2!r}")
        ctx.check("line counts", (2, 1), (len(lines1), len(lines2)))

    with ctx.step("Step 9: order 1 line 1 — every line column on its named "
                  "field, including the UoM (the v19 rename) and the "
                  "promised date"):
        line1 = lines1[0]
        ctx.check("product matched on default_code", known_id,
                  m2o_id(line1["product_id"]))
        ctx.check("name is Item_Description",
                  rows[0]["Item_Description"], line1["name"])
        ctx.check("product_uom_qty", 2.0, line1["product_uom_qty"])
        ctx.check("price_unit", 10.0, line1["price_unit"])
        uom_value = line1.get("product_uom_id") or line1.get("product_uom")
        ctx.log(f"the line's UoM field: {uom_value!r}")
        ctx.check_true(
            "the UoM resolved — _prepare_sales_order_line_values writes "
            "product_uom_id (sale_order.py:147, the v19 rename already "
            "done in this tree). A blank here on v19 would be the SILENT "
            "half of that rename: the key ignored and every imported line "
            "taking the default UoM",
            bool(uom_value) and (uom_value[1] if isinstance(uom_value, list)
                                 else uom_value) == uom_name,
            actual_desc=repr(uom_value))
        if "expected_delivery_date" in line1:
            ctx.check("expected_delivery_date is Due_Date", "2026-09-15",
                      str(line1["expected_delivery_date"]))

    with ctx.step("Steps 11-15: the unknown item — exactly ONE product "
                  "auto-created, barcoded, priced, in Consumable, tagged "
                  "'auto created', and referenced by the line"):
        auto = rpc.search_read("product.product",
                               [("default_code", "=", unknown),
                                ("active", "in", [True, False])],
                               ["name", "default_code", "barcode",
                                "list_price", "categ_id",
                                "product_tag_ids"])
        ctx.log(f"auto-created product(s): {auto!r}")
        ctx.check("exactly one was created", 1, len(auto))
        product = auto[0]
        ctx.check("barcode also equals Item", unknown, product["barcode"])
        ctx.check("name is Item_Description",
                  rows[1]["Item_Description"], product["name"])
        ctx.check("list_price is Unit_Price", 3.50, product["list_price"])
        category = rpc.read("product.category",
                            [m2o_id(product["categ_id"])], ["name"])[0]
        ctx.log(f"its category: {category!r}")
        ctx.check("its category is exactly Consumable",
                  CONSUMABLE_CATEGORY_NAME, category["name"])
        tag_id = rpc.ref(AUTO_CREATED_TAG_XMLID)
        ctx.check_true(
            f"it carries {AUTO_CREATED_TAG_XMLID} — the tag is what makes "
            "auto-created products findable in Products",
            tag_id in (product.get("product_tag_ids") or []),
            actual_desc=repr(product.get("product_tag_ids")))
        line2 = lines1[1]
        ctx.check("the line references it", product["id"],
                  m2o_id(line2["product_id"]))
        ctx.check("with quantity 5 and price 3.50", (5.0, 3.50),
                  (line2["product_uom_qty"], line2["price_unit"]))

    with ctx.step("Steps 16-17, 20: exactly TWO analytic accounts created — "
                  "one per plan — and SHARED by all three lines, not "
                  "duplicated per row"):
        accounts = rpc.search_read(
            "account.analytic.account",
            [("name", "in", [analytic_name("PRJ-NEW-ALPHA"),
                             analytic_name("CC-ALPHA-2026")]),
             ("active", "in", [True, False])],
            ["name", "plan_id"], order="id")
        ctx.log(f"auto-created analytic accounts: {accounts!r}")
        ctx.check("exactly two exist — the same records reused across "
                  "three lines, not six duplicates", 2, len(accounts))
        by_name = {account["name"]: account for account in accounts}
        project_plan = rpc.ref(ANALYTIC_PLAN_XMLIDS["project"])
        contract_plan = rpc.ref(ANALYTIC_PLAN_XMLIDS["contract"])
        ctx.check("the project account is in the Project plan", project_plan,
                  m2o_id(by_name[analytic_name("PRJ-NEW-ALPHA")]["plan_id"]))
        ctx.check("the contract account is in the Customer Contract plan",
                  contract_plan,
                  m2o_id(by_name[analytic_name("CC-ALPHA-2026")]["plan_id"]))

    with ctx.step("Step 18: THE HIGHEST-VALUE OUTPUT OF THIS CASE. Every "
                  "line's raw analytic_distribution, recorded VERBATIM "
                  "including the key shape — the input to resolving delta "
                  "§2.14 for the whole project"):
        expected_accounts = {account["id"] for account in accounts}
        for label, lines in (("REQ-1", lines1), ("REQ-2", lines2)):
            for index, line in enumerate(lines, start=1):
                raw = line.get("analytic_distribution")
                ctx.log(f"{label} line {index} analytic_distribution, "
                        f"VERBATIM: {raw!r}")
                ctx.log(f"  key shape: "
                        f"{[(type(k).__name__, k, v) for k, v in (raw or {}).items()]!r}")
                ctx.check(
                    f"{label} line {index} names exactly the two "
                    "auto-created accounts, compared by RESOLVED ACCOUNT "
                    "SET so a key-format change is not reported as a value "
                    "change", expected_accounts,
                    distribution_accounts(raw))
                ctx.check(f"{label} line {index} allocates 100%", {100},
                          {value for value in (raw or {}).values()})
        ctx.log("This flow WRITES these keys; WF-013, WF-017 and WF-018 "
                "READ them. Delta §2.14 leaves the comma-joined multi-plan "
                "format an open Unknown on v19 — so if it changed, this "
                "flow writes something structurally valid and semantically "
                "wrong and every downstream reader is wrong with it, "
                "silently. Publish the key shape above to migration/ as "
                "soon as a MIGRATED v19 database exists.")

    with ctx.step("Steps 10, 19: COST_CENTER IS ABSENT. The value is in the "
                  "file, is resolved by the code, and is then deliberately "
                  "discarded (BR-8, sale_order.py:172-178). This is the "
                  "assertion a well-meaning port breaks"):
        cost_plan = rpc.ref(ANALYTIC_PLAN_XMLIDS["cost"])
        every_account = set()
        for lines in (lines1, lines2):
            for line in lines:
                every_account |= distribution_accounts(
                    line.get("analytic_distribution"))
        plans = plans_of(rpc, every_account)
        ctx.log(f"accounts across every line -> plan: {plans!r}")
        ctx.check("no Cost Centre-plan account appears in any "
                  "distribution", [],
                  [account for account, plan in plans.items()
                   if plan == cost_plan])
        ctx.check("and the cost-centre account named in the file was never "
                  "even created — the code resolves it only inside the "
                  "commented-out branch", [],
                  rpc.search("account.analytic.account",
                             [("name", "=", analytic_name("CCENTRE-180008")),
                              ("active", "in", [True, False])]))
        ctx.log("A developer tidying up the commented-out block would "
                "'fix' Cost_Center into the distribution and silently "
                "change every cost-centre allocation in the ledger. Keep "
                "this assertion and keep the comment.")

    with ctx.step("Step 21: order 2 — its own header and its single line"):
        ctx.check("origin", memo("REQ-2"), req2["origin"])
        ctx.check("order_type is the second label's key",
                  labels[project_label], req2["order_type"])
        ctx.check("requester", "Sam Buyer", req2["requester"])
        ctx.check("requester_email", "sam.buyer@example.com",
                  req2["requester_email"])
        ctx.check("memo_to_suppliers is empty", False,
                  req2["memo_to_suppliers"] or False)
        line = lines2[0]
        ctx.check("one line on the known product at qty 1 / price 10",
                  (known_id, 1.0, 10.0),
                  (m2o_id(line["product_id"]), line["product_uom_qty"],
                   line["price_unit"]))
        if "expected_delivery_date" in line:
            ctx.check("with its own promised date", "2026-09-30",
                      str(line["expected_delivery_date"]))

    with ctx.step("Step 22: the ship-to partner was REUSED, not created — "
                  "the full-address match found it"):
        matches = rpc.search("res.partner",
                             [("name", "=", contact),
                              ("active", "in", [True, False])])
        ctx.log(f"partners named {contact!r}: {matches!r}")
        ctx.check("still exactly one", [partner_id], matches)
        ctx.check("and both orders point at it", [partner_id] * 2,
                  [m2o_id(order["partner_id"]) for order in created])

    with ctx.step("Step 23: the sftp.file reads Done with process_date "
                  "stamped"):
        ctx.check("state", "done", file_row["state"])
        ctx.check_true("process_date stamped",
                       bool(file_row["process_date"]),
                       actual_desc=repr(file_row["process_date"]))
        ctx.log(f"its chatter / activity text: "
                f"{file_message(rpc, file_id)!r}")
        ctx.check("and no activity was filed anywhere", [],
                  activities_on(rpc, "sftp.file", [file_id])
                  + activities_on(rpc, "sale.order",
                                  [order["id"] for order in created]))

    with ctx.step("Step 24: the remote archive move is NOT observable "
                  "here — recorded, not asserted"):
        ctx.log("SFTPConnection.move_files runs inside "
                "sftp.folder.action_get_files against a live endpoint; the "
                "fixture server is active=False with archive_auto off "
                "(convention rule 4).")

    with ctx.step("Steps 25-26: nothing was confirmed, no accounting entry "
                  "was produced, and the confirmation gate is ARMED"):
        ctx.check("both orders are still draft", ["draft"] * len(created),
                  [order["state"] for order in
                   orders_for(rpc, [memo("REQ-1"), memo("REQ-2")])])
        if rpc.field_exists("sale.order", "invoice_ids"):
            invoices = rpc.search("account.move",
                                  [("invoice_origin", "in",
                                    [memo("REQ-1"), memo("REQ-2")])])
            ctx.check("no accounting entry was produced by this workflow",
                      [], invoices)
        ctx.check("requester_email is populated on both, which F220 "
                  "requires before either can be confirmed (WF-002)",
                  [True] * len(created),
                  [bool(order["requester_email"]) for order in created])
        after = population_counts(rpc)
        ctx.log(f"token-scoped population before: {before!r}")
        ctx.log(f"token-scoped population after:  {after!r}")


@test_case(
    id="TEST-WF001-TC342",
    name="The manual upload wizard produces the same orders — and no "
         "sftp.file",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_sale_workday", priority="P1", kind="API", order=1342,
    description="Drives the same ETL through the MANUAL wizard, whose "
                "entry point is public, and asserts it produces "
                "byte-equivalent business results to the scheduled path — "
                "the same grouping, the same header and line mapping, the "
                "same three auto-creations — with three differences: NO "
                "sftp.file, a raised error instead of a Failed record, and "
                "a redirect action naming the created orders. Records the "
                "audit-trail finding and the permission finding.",
    traceability=trace("DATAONE-TC342"))
def test_tc342(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-001 fixtures and open a fresh "
                  "namespace"):
        sweep_wf001(rpc)

    with ctx.step("Preconditions, plus the menu the wizard hangs off"):
        require_requisition_import(ctx)
        require_import_prerequisites(ctx)
        require_mail_offline(ctx)
        labels = order_type_labels(ctx)
        uom_name = any_uom(ctx)
        state_row, country_row = state_and_country(ctx)
        menu_id = rpc.ref(WIZARD_MENU_XMLID)
        ctx.log(f"{WIZARD_MENU_XMLID} resolves to {menu_id!r}")
        if menu_id:
            # v19 renamed ir.ui.menu.groups_id -> group_ids. Resolved
            # rather than hardcoded so the case reads on both versions.
            menu_group_field = ("groups_id"
                                if rpc.field_exists("ir.ui.menu", "groups_id")
                                else "group_ids")
            menu = rpc.read("ir.ui.menu", [menu_id],
                            ["name", "parent_id", "action",
                             menu_group_field])[0]
            ctx.log(f"the Import Workday Requisition menu: {menu!r}")
            ctx.check_true(
                "its parent anchor resolved — delta §3.5 lists "
                "sale.sale_order_menu as a rotted anchor, and a failed "
                "inherit means the menu is simply not there (LOUD, which "
                "is the good case)",
                bool(m2o_id(menu["parent_id"])),
                actual_desc=repr(menu["parent_id"]))
        else:
            ctx.log(f"[warn] {WIZARD_MENU_XMLID} does not resolve under "
                    "that xml id; the wizard model is still reachable and "
                    "the rest of the case proceeds. Recorded.")

    with ctx.step("Steps 1-4: upload the same file through the wizard and "
                  "assert it produced the same two orders"):
        contact = contact_name("Alpha")
        rows, known, unknown, buy_label, project_label = _fixture_file(
            ctx, uom_name, labels, contact, state_row["name"])
        known_id = _ensure_known_product(ctx, known)
        partner_id = _ensure_contact(ctx, contact, "500 Main St", "Suite 20",
                                     "Austin", state_row, country_row,
                                     "78701")
        files_before = rpc.search("sftp.file", [])
        raised, action = run_wizard(ctx, rows)
        ctx.check_true("the wizard did not raise", not raised,
                       actual_desc=repr(action))
        ctx.check_true(
            "and it returned the quotations action, which is how a "
            "salesperson lands on what they just imported",
            isinstance(action, dict) and action.get("res_model")
            in ("sale.order", None),
            actual_desc=repr(action if isinstance(action, dict) else action))
        redirected = action_order_ids(action)
        ctx.log(f"the action's domain names order ids: {redirected!r}")

    with ctx.step("Steps 5-6: the SAME business results as the scheduled "
                  "path — two draft orders, the header and line mapping, "
                  "and all three auto-creations"):
        created = orders_for(rpc, [memo("REQ-1"), memo("REQ-2")])
        for order in created:
            ctx.log(f"order {order!r}")
        ctx.check("two orders, one per requisition", 2, len(created))
        ctx.check("both draft", ["draft", "draft"],
                  [order["state"] for order in created])
        ctx.check("both flagged imported_from_workday", [True, True],
                  [order["imported_from_workday"] for order in created])
        ctx.check("and the action's domain names exactly them",
                  sorted(order["id"] for order in created), redirected)
        by_origin = {order["origin"]: order for order in created}
        req1 = by_origin[memo("REQ-1")]
        ctx.check("order_type resolved from the label", labels[buy_label],
                  req1["order_type"])
        ctx.check("the ship-to partner was reused", partner_id,
                  m2o_id(req1["partner_id"]))
        ctx.check("the unknown item was auto-created exactly once", 1,
                  len(rpc.search("product.product",
                                 [("default_code", "=", unknown),
                                  ("active", "in", [True, False])])))
        ctx.check("and both analytic accounts exactly once each", 2,
                  len(rpc.search("account.analytic.account",
                                 [("name", "in",
                                   [analytic_name("PRJ-NEW-ALPHA"),
                                    analytic_name("CC-ALPHA-2026")]),
                                  ("active", "in", [True, False])])))
        lines1 = order_lines(rpc, req1["id"])
        ctx.check("REQ-1 has its two lines", 2, len(lines1))
        ctx.check("the known line still resolves the known product",
                  known_id, m2o_id(lines1[0]["product_id"]))

    with ctx.step("Step 7: THE FINDING — NO sftp.file was created, so there "
                  "is no way to answer 'where did this order come from and "
                  "what file produced it?' after the fact"):
        files_after = rpc.search("sftp.file", [])
        ctx.log(f"sftp.file count before: {len(files_before)}, after: "
                f"{len(files_after)}")
        ctx.check("the manual path creates no sftp.file at all",
                  sorted(files_before), sorted(files_after))
        attachments = rpc.search(
            "ir.attachment",
            [("res_model", "=", "sale.order"),
             ("res_id", "in", [order["id"] for order in created])])
        ctx.log(f"attachments on the created orders: {attachments!r}")
        ctx.check(
            "and the uploaded file is not attached to the orders either — "
            "the wizard is a TransientModel and its Binary field goes with "
            "it. The scheduled path's traceability is one of this flow's "
            "better properties and the manual path discards it. Recommend "
            "the port create an sftp.file-equivalent record, or at minimum "
            "attach the uploaded file to the created orders' chatter",
            [], attachments)

    with ctx.step("Steps 10-11: the ERROR PATH differs — a bad row raises "
                  "to the user instead of leaving a Failed sftp.file, with "
                  "the SAME decorated message including the row dump"):
        sweep_wf001(rpc)
        labels = order_type_labels(ctx)
        contact2 = contact_name("Beta")
        bad_rows, bad_known, _u, bad_label, _p = _fixture_file(
            ctx, uom_name, labels, contact2, state_row["name"])
        _ensure_known_product(ctx, bad_known)
        bad_rows[1]["Item"] = ""          # the TD-WD-01-E2 variant
        before = population_counts(rpc)
        raised, message = run_wizard(ctx, bad_rows, file_name=fx(
            f"{MARK}_manual_bad.csv"))
        ctx.log(f"the wizard's error, VERBATIM: {message!r}")
        ctx.check_true("it RAISES to the user rather than recording a "
                       "failure", raised, actual_desc=repr(message))
        ctx.check_true("carrying the same 'Item is empty' message the "
                       "scheduled path files as an activity",
                       "Item is empty" in str(message),
                       actual_desc=str(message))
        ctx.check_true(
            "decorated as '{message} at row {data_line}' with the ENTIRE "
            "offending row dict dumped in — identical to the scheduled "
            "path, and identical in its data exposure (see "
            "TEST-WF001-TC340 step 7)",
            "at row" in str(message)
            and "Requisition_Num" in str(message),
            actual_desc=str(message))
        after = population_counts(rpc)
        ctx.log(f"population before the bad upload: {before!r}")
        ctx.log(f"population after:                 {after!r}")
        ctx.check("and NOTHING was committed — the whole file failed", before,
                  after)
        ctx.check("no sftp.file was created by the failure either",
                  sorted(files_after),
                  sorted(rpc.search("sftp.file", [])))

    with ctx.step("Step 14: THE SEC FINDING — recorded, because it is a "
                  "decision and not a defect"):
        wizard_acl = rpc.search_read(
            "ir.model.access",
            [("model_id.model", "=", WIZARD_MODEL)],
            ["name", "group_id", "perm_read", "perm_write", "perm_create",
             "perm_unlink"]) if rpc.model_exists("ir.model.access") else []
        ctx.log(f"ACL rows on {WIZARD_MODEL}: {wizard_acl!r}")
        ctx.log("The manual path just created products, partners and "
                "analytic accounts and, on the revision branch, could "
                "revise any order in the system — through a wizard whose "
                "menu hangs off Sales. The SCHEDULED path's configuration "
                "is base.group_system. That asymmetry is a SEC item: raise "
                "it and record the client's decision. The narrow fix is to "
                "gate the menu (and the wizard's ACL) on a dedicated "
                "group rather than on whoever can see Sales.")
        ctx.log("Steps 12-13 (the revision path and the confirmed-order "
                "protection through the manual path) are asserted for the "
                "SCHEDULED path by TEST-WF001-TC339, and the two paths "
                "share the same _transform_/_process_ pair — proved above "
                "by the byte-equivalent business results. Re-asserting them "
                "through the wizard would assert the same two methods "
                "twice.")
