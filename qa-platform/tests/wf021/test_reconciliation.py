"""DATAONE-WF-021 — TC055: the cycle-count programme's state, captured on the
v17 baseline and diffed after the upgrade.

What this file proves
=====================
``dto_cycle_count`` ships **no cron and no scheduled action**
(``main:project-addons/dto_cycle_count/__manifest__.py:24-42`` lists
``security/ir.model.access.csv``, ``data/cycle_count_category_data.xml`` and
four view files, nothing else). The whole counting programme therefore rides
on three stored columns and nothing else can rebuild them:

* ``cycle_count_category.{name,interval_number,interval_type}`` — the five
  levels and their intervals (``models/cycle_count_category.py:14-20``,
  ``_order = 'id'`` at ``:12``), loaded from
  ``data/cycle_count_category_data.xml`` under ``noupdate="1"``;
* ``product_product.cycle_count_category_id`` — the assignment
  (``models/product_product.py:13``), mirrored onto the template by the stored
  ``variant_cycle_count_category_id`` (``main:product_template.py:15-16``;
  the v19 port keeps the same name, type and ``store=True`` and only swaps the
  dependency path — working tree ``models/product_template.py:36-38``) and
  onto the quant by the stored related ``stock_quant.cycle_count_category_id``
  (``models/stock_quant.py:13-14``);
* ``stock_quant.inventory_date`` — the next due date
  (core, stored compute with ``readonly=False``: v17
  ``stock/models/stock_quant.py:111-113``, v19 ``:109-111``), which core's own
  *To Count* filter reads,
  ``domain="[('inventory_date','&lt;=',context_today()…)]"`` —
  ``stock/views/stock_quant_views.xml:37``. There is no second source for it.

So TC055 measures exactly those, plus the literal the auto-assign rule hangs
on, and asserts the v17 → v19 difference is empty. The capture is read-only
and deliberately un-scoped: it measures the **live** database, which is the
point of a reconciliation case (``AUTOMATION_CONVENTIONS``, "Feasibility
policy"; the same shape as ``tests/wf013/test_reconciliation.py``). This file
creates no fixture and writes nothing to the target.

Step 5 is the one assertion that runs on **both** sides rather than through
the diff: ``product.category.name == 'Finished Goods'`` is an exact,
case- and whitespace-sensitive Python string compare at three sites
(``models/product_product.py:22`` and ``:69``,
``models/product_template.py:69``). A rename anywhere silently disables the
Level-D auto-assign — F082 — with no error of any kind. The workbook's own
note is explicit that this is a **fragility to record**, not a defect to fix
during the upgrade, so this file records it and asserts only what the
workbook asserts: that the literal still exists, exactly, on both sides.

Workbook corrections (source material only — the expected result, "all diffs
empty", is untouched; ``AUTOMATION_CONVENTIONS`` hard rule 2)
=========================================================================
Three of the workbook's SQL statements do not run against the real schema.
Each correction lives in ``tests/wf021/common.py`` as an ``SQL_*`` constant
and each is *asserted* here rather than assumed, so the justification is
evidence and not a claim:

1. **Step 3** — ``stock_quant.cyclic_inventory_frequency`` is a **non-stored**
   related (``related='location_id.cyclic_inventory_frequency'``: v17
   ``stock/models/stock_quant.py:65``, v19 ``:63``) and has no column;
   selecting it raises ``UndefinedColumn``. Dropped from the query, and its
   absence is asserted in step 3.
2. **Step 4** — ``product_template.cycle_count_category_id``,
   ``last_count_date`` and ``scheduled_count_date`` are compute/inverse/search
   triples with no ``store=True`` (``main:product_template.py:13-14,17-20``)
   and have no columns. Step 4's own parenthetical asks where the level
   lives; the corrected query joins through ``product_product`` and step 4
   asserts the full column shape that answers it.
3. **Step 5** — ``product.category.name`` is ``fields.Char('Name',
   index='trigram', required=True)`` and is **not** translatable in v17
   (``product/models/product_category.py:16``) or v19 (``:17``), so the column
   is ``varchar`` and ``name->>'en_US'`` raises. Compared as plain text, which
   is exactly what the Python ``==`` at ``product_product.py:22`` does. The
   column's declared type is probed and recorded before the compare.
4. **Step 3, volume** — the workbook dumps one row per quant; ``stock_quant``
   holds tens of thousands of rows on the target. The per-quant dump is
   written to a CSV **artifact** and the value the diff compares is the
   aggregate in ``SQL_QUANT_SCHEDULE_SUMMARY``, which carries the same
   information at the granularity a diff can actually report.

Step 1's parenthetical ("resolve the table name from ``ir_model`` for module
``dto_cycle_count`` first") is implemented rather than skipped: the owning
module's models are read out of ``ir_model`` × ``ir_model_data`` — an
``ir.model`` row's xmlid is ``'%s.model_%s' % (module, model)`` with the dots
replaced by underscores
(v17 ``base/models/ir_model.py:53``, written at ``:442``; v19 ``:65``) — and
the table is derived the way the ORM derives it,
``_table = _name.replace('.', '_')`` (v17 ``odoo/models.py:799``, v19
``odoo/orm/model_classes.py:266``). The derived name is compared against the
one ``SQL_LEVELS`` hard-codes, so the constant is validated, not trusted.

Determinism (convention rule 5)
===============================
A reconciliation capture cannot be token-scoped — it must see the whole
database. What it must not see is **this suite's own leftovers**: WF-021's
other cases create ``WF021…`` products, categories and quants, and
``sweep_wf021`` archives whatever it cannot unlink
(``tests/wf021/common.py:956-1005``). Archived rows still count in these
queries, so a leftover would inflate a count on one side only. The leftovers
are therefore **measured and reported** — as log lines and in the evidence
artifact — but deliberately kept **out of the diffed snapshot**, so they can
explain a diff without ever creating one. No fixture is created here and no
value depends on the clock.

EXPECTED v17 OUTCOME: PASS — v17 is the capture side; the baseline is
persisted under ``data/baselines/DATAONE-TC055.json``. Step 5's literal-name
assertion and the schema-shape assertions run on v17 too, so the run is not
vacuous.
EXPECTED v19 OUTCOME: PASS if nothing moved; any diff is a real finding.
BLOCKED when no v17 baseline has been captured yet, or when ``pg_*`` is not
configured (``ctx.sql`` blocks by itself and never falls back to a weaker
assertion).
"""
from __future__ import annotations

import datetime
import decimal
import json

from framework.registry import test_case
from tests.wf021.common import (FINISHED_GOODS_NAME, MARKER, MODULE,
                                SQL_FINISHED_GOODS_CATEGORY, SQL_LEVELS,
                                SQL_PRODUCT_LEVEL_BY_CATEG,
                                SQL_QUANT_SCHEDULE_DUMP,
                                SQL_QUANT_SCHEDULE_SUMMARY,
                                SQL_QUANT_SCHEDULED_COUNTS,
                                SQL_QUANTS_BY_LEVEL, WORKFLOW, WORKFLOW_NAME,
                                reconcile, require_cycle_count, trace)

TC_ID = "DATAONE-TC055"

#: The model whose table step 1 resolves — models/cycle_count_category.py:10.
LEVEL_MODEL = "cycle.count.category"
#: What ``_name.replace('.', '_')`` must produce, and what SQL_LEVELS names.
LEVEL_TABLE = "cycle_count_category"

#: Every column the corrected SQL selects, per table. Checked in one pass so a
#: missing one produces ONE precise BLOCKED reason instead of an
#: ``UndefinedColumn`` traceback halfway through the capture.
REQUIRED_COLUMNS = {
    LEVEL_TABLE: ("id", "name", "interval_number", "interval_type"),
    "stock_quant": ("id", "product_id", "location_id",
                    "cycle_count_category_id", "last_count_date",
                    "inventory_date", "inventory_quantity_set"),
    "product_product": ("id", "product_tmpl_id", "cycle_count_category_id"),
    "product_template": ("id", "categ_id"),
    "product_category": ("id", "name", "complete_name"),
}

#: Where the cycle-count level really lives, as SQL columns. Every entry was
#: read on BOTH sides of the port, so it is a diffable invariant and not a
#: v17 accident. dto_cycle_count paths are relative to
#: project-addons/dto_cycle_count/ (v17 = branch ``main``):
#:
#:   stock_quant.cycle_count_category_id   stored related
#:       models/stock_quant.py:13-14
#:   stock_quant.last_count_date           compute=False -> a real column
#:       models/stock_quant.py:15; core declares it a NON-stored compute
#:       (v17 stock/models/stock_quant.py:114, v19 :112), so the column
#:       exists only because the module redefines it
#:   stock_quant.cyclic_inventory_frequency  non-stored related, NO column
#:       v17 stock/models/stock_quant.py:65, v19 :63
#:   product_product.cycle_count_category_id  stored m2o
#:       models/product_product.py:13; last_count_date :14 and
#:       scheduled_count_date :15 are stored Date fields
#:   product_template.{cycle_count_category_id,last_count_date,
#:                     scheduled_count_date}  compute/inverse/search, NO store
#:       main:models/product_template.py:13-14, :17-18, :19-20
#:   product_template.variant_cycle_count_category_id  STORED
#:       main:models/product_template.py:15-16; the v19 port keeps the name,
#:       the type and store=True (working tree :36-38)
EXPECTED_QUANT_SHAPE = {
    "stock_quant.cycle_count_category_id": True,
    "stock_quant.last_count_date": True,
    "stock_quant.inventory_date": True,
    "stock_quant.inventory_quantity_set": True,
    "stock_quant.cyclic_inventory_frequency": False,
}
EXPECTED_PRODUCT_SHAPE = {
    "product_product.cycle_count_category_id": True,
    "product_product.last_count_date": True,
    "product_product.scheduled_count_date": True,
    "product_template.cycle_count_category_id": False,
    "product_template.last_count_date": False,
    "product_template.scheduled_count_date": False,
    "product_template.variant_cycle_count_category_id": True,
}

#: PostgreSQL types ``name = 'Finished Goods'`` compares as plain text against.
#: Anything else (``jsonb``) means an addon made the field translatable, and
#: correction 3 no longer holds.
CHARACTER_TYPES = ("character varying", "character", "text")

#: ``ir.model`` rows carry the xmlid ``'%s.model_%s' % (module, model)`` —
#: v17 base/models/ir_model.py:53 (written at :442), v19 :65. Reading the
#: module's models through ir_model_data is how step 1's parenthetical is
#: answered without hard-coding the table name.
SQL_MODULE_MODELS = """
SELECT m.model
FROM ir_model m
JOIN ir_model_data d ON d.model = 'ir.model' AND d.res_id = m.id
WHERE d.module = %s
ORDER BY m.model
"""

SQL_CATEGORY_NAME_TYPE = """
SELECT data_type
FROM information_schema.columns
WHERE table_name = 'product_category' AND column_name = 'name'
"""

#: Leakage probes — this suite's own namespaced leftovers. Reported, never
#: diffed (see "Determinism" in the module docstring).
SQL_MARKED_PRODUCTS = """
SELECT count(*) FROM product_product WHERE default_code LIKE %s
"""
SQL_MARKED_QUANTS = """
SELECT count(*)
FROM stock_quant q
JOIN product_product pp ON pp.id = q.product_id
WHERE pp.default_code LIKE %s
"""
SQL_MARKED_CATEGORIES = """
SELECT count(*) FROM product_category WHERE name LIKE %s
"""


# --------------------------------------------------------------- helpers
# common.py owns every WF-021 fixture; these three are private to this file
# because a reconciliation snapshot has needs no fixture helper has: values
# must survive a JSON round trip unchanged, or the v19 diff reports
# differences that are only serialization artefacts.
def _scalar(value):
    """Normalise a psycopg2 value into something JSON round-trips unchanged.

    ``save_baseline`` serialises with ``default=str`` and ``load_baseline``
    reads plain JSON, so a ``datetime.date`` captured on v19 would never equal
    the ``'YYYY-MM-DD'`` string loaded from the v17 baseline —
    ``framework/baselines.py:diff_counts`` compares with ``!=`` and would
    report every date column as a difference. Dates become ISO strings and
    Decimals become floats HERE, on both sides, so the comparison is honest.
    """
    if value is None:
        return None
    if isinstance(value, datetime.datetime):
        return value.date().isoformat()
    if isinstance(value, datetime.date):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, (int, float, bool, str)):
        return value
    return str(value)


def _level_key(value) -> str:
    """A stable snapshot key for a (nullable) cycle.count.category id."""
    return "NULL" if value is None else str(value)


def _column_shape(sql, shape: dict) -> dict:
    """Read ``{'table.column': bool}`` back from information_schema."""
    got = {}
    for key in shape:
        table, column = key.split(".", 1)
        got[key] = sql.column_exists(table, column)
    return got


@test_case(
    id="TEST-WF021-TC055",
    name="Cycle-count level assignments and quant scheduling",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_cycle_count",
    priority="P1", kind="DATA", order=21055,
    description="Captures the whole cycle-count programme on the v17 baseline "
                "— the five levels, the per-level quant and product "
                "assignments, the scheduling state and the Finished Goods "
                "literal — and asserts the v19 diff is empty; the literal "
                "category name is asserted exactly on both sides.",
    traceability=trace("DATAONE-TC055"))
def test_tc055(ctx):
    sql = ctx.sql                     # BLOCKS by itself without pg_* config
    snapshot: dict = {}
    evidence: dict = {"tc_id": TC_ID, "env": ctx.env.key, "db": ctx.env.db}

    with ctx.step("Precondition: dto_cycle_count is contributing and every "
                  "column the corrected SQL selects exists"):
        # RPC-side first: without the module there is no programme to measure
        # and every query below would raise UndefinedColumn.
        require_cycle_count(ctx)
        missing = [f"{table}.{column}"
                   for table, columns in REQUIRED_COLUMNS.items()
                   for column in columns
                   if not sql.column_exists(table, column)]
        if missing:
            ctx.blocked(
                f"These columns do not exist on {ctx.env.key} "
                f"(db={ctx.env.db}): {', '.join(missing)}. TC055 measures the "
                "cycle-count programme directly in PostgreSQL; without them "
                "there is nothing to capture and nothing to diff. "
                "stock_quant.last_count_date in particular is a column only "
                "because dto_cycle_count redefines core's non-stored compute "
                "as compute=False (models/stock_quant.py:15; core v17 "
                "stock/models/stock_quant.py:114).")
        ctx.log(f"{sum(len(c) for c in REQUIRED_COLUMNS.values())} required "
                f"columns present across {len(REQUIRED_COLUMNS)} tables")

    with ctx.step("This suite's own leftovers are measured and reported, so "
                  "they can explain a diff but never create one"):
        # WF-021's other cases namespace every fixture with MARKER and sweep
        # in a finally; sweep_wf021 ARCHIVES what it cannot unlink
        # (tests/wf021/common.py:956-1005) and archived rows still count in
        # the queries below. product_product.default_code is a stored Char in
        # both versions (v17 product/models/product_product.py:34, v19 :35),
        # so the probe is a real column on both sides. Logged and written to
        # the artifact; deliberately absent from `snapshot`.
        like = f"{MARKER}%"
        leakage = {
            "products": sql.one(SQL_MARKED_PRODUCTS, (like,)) or 0,
            "quants": sql.one(SQL_MARKED_QUANTS, (like,)) or 0,
            "categories": sql.one(SQL_MARKED_CATEGORIES, (like,)) or 0,
        }
        evidence["wf021_leftovers"] = leakage
        ctx.log(f"WF021-marked leftovers at capture time: {leakage!r}")

    with ctx.step("1. Both versions — the five levels (resolve the table name "
                  "from ir_model for module dto_cycle_count first)"):
        owned = [row[0] for row in sql.rows(SQL_MODULE_MODELS, (MODULE,))]
        ctx.log(f"models owned by {MODULE}: {owned!r}")
        # _table = _name.replace('.', '_') — v17 odoo/models.py:799,
        # v19 odoo/orm/model_classes.py:266.
        derived = (LEVEL_MODEL.replace(".", "_") if LEVEL_MODEL in owned
                   else None)
        evidence["module_models"] = owned
        evidence["level_table"] = derived
        if derived is None:
            ctx.blocked(
                f"ir_model carries no {LEVEL_MODEL!r} row owned by {MODULE} "
                f"on {ctx.env.key} (db={ctx.env.db}) — models found: "
                f"{owned!r}. It is declared at "
                "models/cycle_count_category.py:10 "
                "and ir.model rows are registered with the xmlid "
                "'%s.model_%s' (base/models/ir_model.py:53, written at :442), "
                "so its absence means the table name cannot be resolved the "
                "way the workbook's step 1 requires.")
        ctx.check("step 1 — the table SQL_LEVELS names is the one ir_model "
                  "resolves", LEVEL_TABLE, derived)

        levels = sql.rows(SQL_LEVELS)
        snapshot["levels/table"] = derived
        snapshot["levels/rows"] = len(levels)
        for level_id, name, interval_number, interval_type in levels:
            snapshot[f"levels/{level_id}/name"] = _scalar(name)
            snapshot[f"levels/{level_id}/interval_number"] = _scalar(
                interval_number)
            snapshot[f"levels/{level_id}/interval_type"] = _scalar(
                interval_type)
        # A zero-row capture would make the diff vacuous on both sides, so it
        # is asserted rather than stored: the five levels are shipped by
        # data/cycle_count_category_data.xml under noupdate="1".
        ctx.check_true("step 1 — cycle.count.category rows were captured",
                       bool(levels), actual_desc=f"{len(levels)} row(s)")

    with ctx.step("2. Both versions — assignments per level"):
        by_level = sql.rows(SQL_QUANTS_BY_LEVEL)
        total_quants = 0
        for level_id, quants, products in by_level:
            key = _level_key(level_id)
            snapshot[f"quants_by_level/{key}/quants"] = _scalar(quants)
            snapshot[f"quants_by_level/{key}/products"] = _scalar(products)
            total_quants += quants or 0
        snapshot["quants_by_level/groups"] = len(by_level)
        snapshot["quants_by_level/TOTAL_quants"] = total_quants
        ctx.log(f"{len(by_level)} level group(s) over {total_quants} quant(s)")

    with ctx.step("3. Both versions — the scheduling state per quant"):
        # Correction 1, asserted rather than assumed: the workbook selects
        # q.cyclic_inventory_frequency, which is a non-stored related
        # (v17 stock/models/stock_quant.py:65, v19 :63) and has no column.
        quant_shape = _column_shape(sql, EXPECTED_QUANT_SHAPE)
        ctx.check("step 3 — the stock_quant scheduling columns are exactly "
                  "the stored ones (cyclic_inventory_frequency is a "
                  "non-stored related and is correctly absent)",
                  EXPECTED_QUANT_SHAPE, quant_shape)
        snapshot.update({f"schema/{k}": v for k, v in quant_shape.items()})

        # Correction 4: the per-quant dump is the artifact; the aggregate is
        # what the diff can report on.
        dump_path = ctx.artifacts_dir / "tc055_quant_schedule.csv"
        dump_rows = sql.to_csv(SQL_QUANT_SCHEDULE_DUMP, dump_path)
        ctx.add_artifact(dump_path, "log",
                         "TC055 per-quant scheduling state (workbook step 3)")
        snapshot["schedule/dump_rows"] = dump_rows
        ctx.log(f"per-quant dump: {dump_rows} row(s) -> {dump_path}")

        for row in sql.rows(SQL_QUANT_SCHEDULE_SUMMARY):
            (level_id, quants, counted, scheduled, counting,
             first_count, last_count, first_due, last_due) = row
            key = _level_key(level_id)
            snapshot[f"schedule/{key}/quants"] = _scalar(quants)
            snapshot[f"schedule/{key}/counted"] = _scalar(counted)
            snapshot[f"schedule/{key}/scheduled"] = _scalar(scheduled)
            snapshot[f"schedule/{key}/counting"] = _scalar(counting)
            snapshot[f"schedule/{key}/first_count"] = _scalar(first_count)
            snapshot[f"schedule/{key}/last_count"] = _scalar(last_count)
            snapshot[f"schedule/{key}/first_due"] = _scalar(first_due)
            snapshot[f"schedule/{key}/last_due"] = _scalar(last_due)

    with ctx.step("4. Both versions — the product-level assignment (confirm "
                  "whether the level lives on the template, the product or "
                  "only the quant)"):
        # The step's own parenthetical, answered as evidence: the level lives
        # on product_product (models/product_product.py:13), is mirrored onto
        # the template ONLY by the stored variant_cycle_count_category_id
        # (main:product_template.py:15-16; v19 port :36-38 keeps name, type
        # and store=True) and onto the quant by the stored related
        # (models/stock_quant.py:13-14). The template's own three fields are
        # compute/inverse/search with no store (main:product_template.py
        # :13-14, :17-20) — correction 2.
        product_shape = _column_shape(sql, EXPECTED_PRODUCT_SHAPE)
        ctx.check("step 4 — the level is stored on product_product and "
                  "mirrored by product_template.variant_cycle_count_category_"
                  "id; the template's own three fields have no columns",
                  EXPECTED_PRODUCT_SHAPE, product_shape)
        snapshot.update({f"schema/{k}": v for k, v in product_shape.items()})

        categories = sql.rows(SQL_PRODUCT_LEVEL_BY_CATEG)
        total_products = total_with_level = 0
        for categ_id, complete_name, products, with_level in categories:
            snapshot[f"product_level/{categ_id}/complete_name"] = _scalar(
                complete_name)
            snapshot[f"product_level/{categ_id}/products"] = _scalar(products)
            snapshot[f"product_level/{categ_id}/with_level"] = _scalar(
                with_level)
            total_products += products or 0
            total_with_level += with_level or 0
        snapshot["product_level/categories"] = len(categories)
        snapshot["product_level/TOTAL_products"] = total_products
        snapshot["product_level/TOTAL_with_level"] = total_with_level
        ctx.log(f"{total_with_level} of {total_products} product(s) across "
                f"{len(categories)} categor(ies) carry a level")

    with ctx.step("5. Assert the literal category name still exists exactly"):
        # Correction 3, probed before the compare: product_category.name is
        # fields.Char(index='trigram', required=True) and NOT translatable in
        # v17 (product/models/product_category.py:16) or v19 (:17), so the
        # column is varchar and the workbook's name->>'en_US' would raise.
        name_type = sql.one(SQL_CATEGORY_NAME_TYPE)
        evidence["product_category.name/data_type"] = name_type
        snapshot["schema/product_category.name/data_type"] = _scalar(name_type)
        if name_type not in CHARACTER_TYPES:
            ctx.blocked(
                f"product_category.name is {name_type!r} on {ctx.env.key} "
                f"(db={ctx.env.db}), not a character type. Core declares it "
                "fields.Char and NOT translatable (v17 "
                "product/models/product_category.py:16, v19 :17); a jsonb "
                "column means an addon made it translatable on this target, "
                "and the Level-D auto-assign then compares a dict against the "
                "literal 'Finished Goods' (models/product_product.py:22). "
                "That is a finding for a human before any diff is meaningful.")

        rows = sql.rows(SQL_FINISHED_GOODS_CATEGORY)
        exact = [r for r in rows if r[2] == FINISHED_GOODS_NAME]
        snapshot["finished_goods/matched_rows"] = len(rows)
        snapshot["finished_goods/exact_rows"] = len(exact)
        for categ_id, complete_name, name in rows:
            snapshot[f"finished_goods/{categ_id}/name"] = _scalar(name)
            snapshot[f"finished_goods/{categ_id}/complete_name"] = _scalar(
                complete_name)
        evidence["finished_goods_rows"] = [
            {"id": r[0], "complete_name": _scalar(r[1]), "name": _scalar(r[2])}
            for r in rows]
        ctx.log(f"categories matching the workbook's step 5 query: {rows!r}")
        # The workbook's own expected result for this step, on BOTH sides: an
        # exact, case- and whitespace-sensitive match. 'Finished Goods ' with
        # a trailing space is NOT this category — the rule is a Python ==
        # (models/product_product.py:22, :69; product_template.py:69).
        ctx.check_true(
            f"step 5 — a product.category named exactly "
            f"{FINISHED_GOODS_NAME!r} exists",
            bool(exact),
            actual_desc=f"{len(exact)} exact match(es) of "
                        f"{len(rows)} row(s) returned: "
                        f"{[r[2] for r in rows]!r}")

    with ctx.step("6. Assert no quant lost its scheduled date"):
        # inventory_date is the ONLY source of the next-count date — there is
        # no cron and no other column to recover it from — so both halves of
        # the count are captured and step 7 diffs them. The workbook asserts
        # the DIFFERENCE, not an absolute zero, and nothing here is weakened
        # into one.
        unscheduled, scheduled = sql.rows(SQL_QUANT_SCHEDULED_COUNTS)[0]
        snapshot["quants/unscheduled"] = _scalar(unscheduled)
        snapshot["quants/scheduled"] = _scalar(scheduled)
        ctx.log(f"quants scheduled={scheduled} unscheduled={unscheduled}")

    with ctx.step("7. Diff steps 1, 2, 3, 4 and 6"):
        # Evidence written BEFORE the assertion, so a failing diff is
        # reviewable from the artifact alone.
        path = ctx.artifacts_dir / "tc055_cycle_count_state.json"
        evidence["snapshot"] = snapshot
        path.write_text(json.dumps(evidence, indent=1, ensure_ascii=False,
                                   default=str), encoding="utf-8")
        ctx.add_artifact(path, "log", "TC055 cycle-count programme state")

        # reconcile() is the platform's DATA_RECONCILIATION driver: on v17 it
        # persists this snapshot as the baseline, on v19 it loads that
        # baseline and asserts a zero diff (BLOCKED when none was captured
        # yet). The snapshot is already built, so capture() just hands it
        # over — every query above ran exactly once, against one consistent
        # read-only connection.
        reconcile(ctx, TC_ID, lambda _ctx, _snap=snapshot: _snap)
