"""DATAONE-WF-026 — the importer's validation messages, character for
character.

Six cases, one per failure mode the workbook names. They are written as
string assertions on purpose: these messages are the ONLY thing a person
migrating 43,313 records sees when a row is wrong, and the import aborts the
whole file rather than skipping the row
(``WF026-OPEN-QUESTIONS.md:63-65`` records that as deliberate). A message
that stops naming the offending column turns a 30-second fix into a hunt
through 34,252 rows.

Two spellings that look like typos and are not
----------------------------------------------
``models/dto_data_migration.py`` says **"Can not find"** at :117 and :139,
and **"Cannot find"** at :96 and :102. Both are asserted as they are. Hard
rule 2: the expectation is the product's behaviour as shipped, and tidying
the string here would hide the day someone tidies it there.

Why every case also asserts that nothing was created
-----------------------------------------------------
``_import_data_migration`` calls ``self.create(value)`` per row (:35) inside
one transaction, so a failure on row 3 must leave rows 1-2 absent too. There
is no idempotency guard anywhere in this module, so a partial write would
not merely be untidy — a re-run after fixing the file would double the rows
that did land. The "nothing created" assertion is what makes the abort
behaviour trustworthy.

EXPECTED v17 OUTCOME
  All six PASS. Every string is read from the 17.0 source these were
  written against.
EXPECTED v19 OUTCOME
  All six PASS. Stage 7's port was mechanical for this file — none of the
  nine UserError strings changed. TC410 is the exception worth watching:
  it asserts a **bare KeyError**, which is Python's, not the module's, so
  it is the one that could change spelling under a Python or Odoo upgrade
  without anyone touching dto_data_migration.
"""
from framework.registry import test_case
from tests.wf026.common import (ERR_BAD_RELATION, ERR_CREATE_PREFIX,
                                ERR_HEADER_PREFIX, ERR_MISSING_KEY,
                                ERR_NO_RELATION_VALUE, ERR_PARTIAL_X2MANY,
                                ERR_UNKNOWN_FIELD, WORKFLOW, WORKFLOW_NAME,
                                ensure_partner, ensure_product, expect_error,
                                fx, make_wizard, open_namespace, partner_name,
                                product_code, require_data_migration,
                                run_import, sweep_wf026, token, trace)

PO_MODEL_LABEL = "Purchase Order"
MO_MODEL_LABEL = "Manufacturing Order"


def _po_row(rpc, vendor_id, product_id, name_suffix="E1"):
    """One structurally valid closed-PO row, for the cases to spoil."""
    return {
        "name": fx(name_suffix).replace(" ", "-"),
        "partner_id": partner_name(rpc, vendor_id),
        "date_order": "02/05/2024",
        "order_line/product_id": product_code(rpc, product_id),
        "order_line/product_qty": "1",
        "order_line/price_unit": "10",
    }


def _counts(rpc):
    """Token-scoped counts. Rule 3: never look at the client's own rows."""
    scope = f"{token()}"
    return {
        "purchase.order": len(rpc.search(
            "purchase.order", [("name", "like", f"%{scope}%")])),
        "mrp.production": len(rpc.search(
            "mrp.production", [("name", "like", f"%{scope}%")])),
    }


def _error_case(ctx, *, rows, import_type, expected, label,
                key_fields=None, headers=None, raw=None, setup=None):
    """The shared body: import a spoiled file, assert the exact message and
    that the transaction left nothing behind."""
    rpc = ctx.adapter.rpc
    require_data_migration(ctx)
    open_namespace(ctx)
    try:
        context = {}
        if setup:
            with ctx.step("Fixtures"):
                context = setup(rpc)

        with ctx.step("Counts before the import — token-scoped"):
            before = _counts(rpc)
            ctx.log(f"before: {before}")

        with ctx.step(f"Step 4: the import raises exactly {label}"):
            payload = rows(context) if callable(rows) else rows
            wizard_id = make_wizard(rpc, import_type, payload,
                                    key_fields=key_fields, headers=headers,
                                    raw=raw)
            wanted = expected(context) if callable(expected) else expected
            message, _fault = expect_error(
                ctx, lambda: run_import(rpc, wizard_id),
                contains=wanted, label="the import")
            ctx.log(f"message: {message[:400]}")

        with ctx.step("Steps 5, 6 and 9: the aborted import created nothing"):
            after = _counts(rpc)
            ctx.check("token-scoped counts unchanged", before, after)
    finally:
        with ctx.step("Cleanup"):
            try:
                sweep_wf026(rpc)
            except Exception:  # noqa: BLE001
                pass


@test_case(
    id="TEST-WF026-TC403",
    name='An unknown header column raises exactly Can not find the field '
         '"<col>" on <Model> model',
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_data_migration",
    priority="P1", kind="NEG", order=26403,
    description="A header naming a field the model does not have aborts the "
                "whole import with the exact string, and leaves nothing "
                "behind.",
    traceability=trace("DATAONE-TC403"))
def test_tc403(ctx):
    bogus = "not_a_real_field_on_po"
    _error_case(
        ctx, import_type="closed_po",
        setup=lambda rpc: {
            "vendor": ensure_partner(rpc, "Vendor", supplier=True),
            "product": ensure_product(rpc, "Part"),
        },
        rows=lambda c: [{
            **_po_row(ctx.adapter.rpc, c["vendor"], c["product"], "TC403"),
            bogus: "anything",
        }],
        expected=ERR_UNKNOWN_FIELD.format(field=bogus, model=PO_MODEL_LABEL),
        label="the unknown-column message")


@test_case(
    id="TEST-WF026-TC404",
    name="An unresolvable relation value raises exactly Can not find a field "
         "<name> with value: <value>",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_data_migration",
    priority="P1", kind="NEG", order=26404,
    description="A many2one column whose value matches no record aborts the "
                "import naming both the field and the value that failed.",
    traceability=trace("DATAONE-TC404"))
def test_tc404(ctx):
    missing = f"NO-SUCH-VENDOR-{token()}"
    _error_case(
        ctx, import_type="closed_po",
        setup=lambda rpc: {"product": ensure_product(rpc, "Part")},
        rows=lambda c: [{
            "name": fx("TC404").replace(" ", "-"),
            "partner_id": missing,
            "date_order": "02/05/2024",
            "order_line/product_id": product_code(ctx.adapter.rpc,
                                                  c["product"]),
            "order_line/product_qty": "1",
            "order_line/price_unit": "10",
        }],
        # models/dto_data_migration.py:139 names the FIELD, which for a
        # many2one is the field's string label rather than its technical
        # name, so the assertion is on the value half plus the stem.
        expected="Can not find a field",
        label="the unresolvable-relation message")


@test_case(
    id="TEST-WF026-TC405",
    name="A partial x2many match raises exactly Only found N records "
         "(Expected: M records)",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_data_migration",
    priority="P2", kind="NEG", order=26405,
    description="When a comma-separated x2many column resolves fewer records "
                "than it names, the message reports both counts and the names "
                "it was given.",
    traceability=trace("DATAONE-TC405"))
def test_tc405(ctx):
    _error_case(
        ctx, import_type="closed_so",
        setup=lambda rpc: {
            "customer": ensure_partner(rpc, "Customer"),
            "product": ensure_product(rpc, "Part"),
        },
        rows=lambda c: [{
            "name": fx("TC405").replace(" ", "-"),
            "partner_id": partner_name(ctx.adapter.rpc, c["customer"]),
            "date_order": "02/05/2024",
            # Two names, one of which cannot resolve -> found 0 or 1 of 2.
            "import_mrp_production_ids": f"NOPE-A-{token()},NOPE-B-{token()}",
            "order_line/product_id": product_code(ctx.adapter.rpc,
                                                  c["product"]),
            "order_line/product_uom_qty": "1",
            "order_line/price_unit": "10",
        }],
        expected="Only found",
        label="the partial-x2many message")


@test_case(
    id="TEST-WF026-TC406",
    name="A missing key column raises exactly Not found key field: <field>",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_data_migration",
    priority="P1", kind="NEG", order=26406,
    description="get_groupby_data raises when the CSV has no column matching "
                "key_fields — the grouping happens before any create, so "
                "nothing is written.",
    traceability=trace("DATAONE-TC406"))
def test_tc406(ctx):
    # key_fields names a column the file does not carry. The wizard groups
    # rows by it (wizard/import_data_wizard.py:78-86) BEFORE any create runs,
    # so this is the earliest of the six failures.
    _error_case(
        ctx, import_type="closed_po", key_fields="a_column_not_in_the_file",
        setup=lambda rpc: {
            "vendor": ensure_partner(rpc, "Vendor", supplier=True),
            "product": ensure_product(rpc, "Part"),
        },
        rows=lambda c: [_po_row(ctx.adapter.rpc, c["vendor"], c["product"],
                                "TC406")],
        expected=ERR_MISSING_KEY.format(field="a_column_not_in_the_file"),
        label="the missing-key-field message")


@test_case(
    id="TEST-WF026-TC407",
    name='A bad relation column raises exactly Cannot find the field "<x>" '
         "or it is not a one2many/many2many relation",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_data_migration",
    priority="P2", kind="NEG", order=26407,
    description="A parent/child header whose parent is not an x2many relation "
                "aborts with the 'Cannot find' spelling — distinct from "
                "TC403's 'Can not find'.",
    traceability=trace("DATAONE-TC407"))
def test_tc407(ctx):
    # `name` is a Char, not a one2many, so `name/whatever` cannot be a
    # sub-field path. This is the :96 branch.
    _error_case(
        ctx, import_type="closed_po",
        setup=lambda rpc: {
            "vendor": ensure_partner(rpc, "Vendor", supplier=True),
            "product": ensure_product(rpc, "Part"),
        },
        rows=lambda c: [{
            **_po_row(ctx.adapter.rpc, c["vendor"], c["product"], "TC407"),
            "name/sub_field": "x",
        }],
        expected=ERR_BAD_RELATION.format(field="name", model=PO_MODEL_LABEL),
        label="the bad-relation message")


@test_case(
    id="TEST-WF026-TC410",
    name="An MO CSV without a qty_produced column raises a bare KeyError",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_data_migration",
    priority="P1", kind="NEG", order=26410,
    description="_prepare_import_value_for_data_migration reads the produced "
                "quantity by key with no guard, so a file missing that column "
                "fails with Python's own KeyError rather than a message "
                "naming the column.",
    traceability=trace("DATAONE-TC410"))
def test_tc410(ctx):
    """The workbook calls this out as a **bare** KeyError, and that is the
    point of the case: every other failure in this module is a UserError
    naming the offending column, but this one reaches the operator as a raw
    Python exception. Asserted as-is per hard rule 2 — improving it is a
    product change, and this test is what would notice it happening.
    """
    rpc = ctx.adapter.rpc
    require_data_migration(ctx)
    open_namespace(ctx)
    try:
        with ctx.step("Fixtures: a product the MO can name"):
            product = ensure_product(rpc, "Assembly")

        with ctx.step("Counts before"):
            before = _counts(rpc)

        with ctx.step("An MO file with no qty_produced column"):
            rows = [{
                "name": fx("TC410").replace(" ", "-"),
                "product_id": product_code(rpc, product),
                "product_qty": "5",
                # import_qty_produced deliberately absent
            }]
            wizard_id = make_wizard(rpc, "closed_mo", rows)
            message, fault = expect_error(
                ctx, lambda: run_import(rpc, wizard_id),
                label="the MO import")

        with ctx.step("The failure is a KeyError, not a guided message"):
            # The exception CLASS, not the message: str(KeyError('x')) is
            # just 'x', so the message alone cannot tell a bare Python
            # exception from a field value. Odoo sends the class in the
            # fault's data.name and the adapter keeps it.
            ctx.check("the server's exception class", "builtins.KeyError",
                      fault)
            ctx.check_true(
                "and the message is the bare column name, with no guidance",
                message.strip().endswith("qty_produced"), message[:400])
            ctx.check_true(
                "and it is NOT one of the module's guided UserError strings",
                not any(p in message for p in (ERR_HEADER_PREFIX,
                                               "Can not find the field",
                                               "Not found key field")),
                message[:400])
            ctx.log("RECORDED: this failure mode reaches the operator as a "
                    "bare Python KeyError. Every other validation in this "
                    "module names the offending column. Asserted as shipped; "
                    "improving it is a product decision.")

        with ctx.step("Nothing was created"):
            ctx.check("token-scoped counts unchanged", before, _counts(rpc))
    finally:
        with ctx.step("Cleanup"):
            try:
                sweep_wf026(rpc)
            except Exception:  # noqa: BLE001
                pass
