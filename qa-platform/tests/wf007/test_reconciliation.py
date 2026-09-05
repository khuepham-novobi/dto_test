"""DATAONE-WF-007 — the lot master across versions: TC033, TC056.

Both follow the suite-wide DATA_RECONCILIATION pattern
(``framework/fg_common.reconcile`` over ``framework/baselines.py``): capture
on Odoo 17, persist, diff on Odoo 19.

TC033 is the migration this whole workflow turns on. v19 replaced
``mrp.production.lot_producing_id`` (Many2one) with ``lot_producing_ids``
(Many2many) — the source names it "B-1: M2o -> M2m", and measured on d1v19
only the M2m exists. Every MO that carried a producing lot on v17 must carry
the same lot on v19, so the snapshot is keyed by MO and records the lot's
NAME rather than its id: a migration that renumbered records but kept the
association is still correct, while one that dropped an association is not.

TC056 pins the lot master itself, including ``auto_generated`` — the flag the
rename authorisation in ``button_mark_done`` keys on. A lot that lost its
flag during migration would silently stop being renamed on its next
backorder, which no functional test would catch.

The capture reads the M2m relation table on v19 and the column on v17, so a
single baseline is comparable across the rename. The table name is resolved
from the database rather than assumed, because the relation table for a
Many2many is generated and its name is not something to guess.

EXPECTED v17 OUTCOME: PASS (baselines captured).
EXPECTED v19 OUTCOME: depends on the baseline. ``dto_17`` on this deployment
is a scratch database rather than a production clone
(docs/ENVIRONMENT_STATUS.md), so a diff there reflects the environment, not
the port.

Read-only: SQL only, no fixtures, nothing swept.
"""
from framework.fg_common import reconcile
from framework.registry import test_case
from tests.wf007.common import WORKFLOW, WORKFLOW_NAME, trace


def _producing_lot_pairs(sql) -> list[tuple]:
    """(mo_name, lot_name) for every MO that has a producing lot.

    Reads whichever shape the target has: the v17 ``lot_producing_id``
    column, or the v19 Many2many relation table. The relation table is looked
    up in information_schema rather than hard-coded, since its name is
    generated.
    """
    if sql.column_exists("mrp_production", "lot_producing_id"):
        return sql.rows("""
            SELECT p.name, l.name
            FROM mrp_production p
            JOIN stock_lot l ON l.id = p.lot_producing_id
            ORDER BY p.name, l.name
        """)

    table = sql.one("""
        SELECT table_name FROM information_schema.columns
        WHERE column_name = 'lot_producing_id'
          AND table_name LIKE '%%lot%%'
          AND table_name <> 'mrp_production'
        LIMIT 1
    """)
    if not table:
        # Try the other half of the pair — the relation may be named after
        # the MO side instead.
        table = sql.one("""
            SELECT c1.table_name FROM information_schema.columns c1
            JOIN information_schema.columns c2
              ON c2.table_name = c1.table_name
            WHERE c1.column_name = 'mrp_production_id'
              AND c2.column_name LIKE '%%lot%%id'
              AND c1.table_name <> 'mrp_production'
            LIMIT 1
        """)
    if not table:
        return []
    lot_col = sql.one("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = %s AND column_name LIKE '%%lot%%id' LIMIT 1
    """, (table,))
    mo_col = sql.one("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = %s AND column_name LIKE '%%production%%id' LIMIT 1
    """, (table,))
    if not (lot_col and mo_col):
        return []
    return sql.rows(f"""
        SELECT p.name, l.name
        FROM {table} r
        JOIN mrp_production p ON p.id = r."{mo_col}"
        JOIN stock_lot l ON l.id = r."{lot_col}"
        ORDER BY p.name, l.name
    """)


def _capture_producing_lots(ctx) -> dict:
    sql = ctx.sql
    snapshot: dict = {}
    snapshot["shape"] = ("v17/lot_producing_id"
                         if sql.column_exists("mrp_production", "lot_producing_id")
                         else "v19/lot_producing_ids")
    pairs = _producing_lot_pairs(sql)
    for mo_name, lot_name in pairs:
        snapshot[f"mo/{mo_name}"] = lot_name
    snapshot["mos_with_producing_lot"] = len(pairs)
    snapshot["done_mos"] = int(sql.one(
        "SELECT count(*) FROM mrp_production WHERE state = 'done'") or 0)
    return snapshot


@test_case(
    id="TEST-WF007-TC033",
    name="lot_producing_id -> lot_producing_ids: every MO that had a "
         "producing lot still has it",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="mrp, dto_mrp",
    priority="P0", kind="API", order=7033,
    description="Every manufacturing order that carried a producing lot on "
                "v17 carries the same lot, by name, after the Many2one to "
                "Many2many migration, and the count of done MOs is unchanged.",
    traceability=trace("DATAONE-TC033"))
def test_tc033(ctx):
    reconcile(ctx, "DATAONE-TC033", _capture_producing_lots)


def _capture_lot_master(ctx) -> dict:
    sql = ctx.sql
    snapshot: dict = {}
    snapshot["lots"] = int(sql.one("SELECT count(*) FROM stock_lot") or 0)

    has_flag = sql.column_exists("stock_lot", "auto_generated")
    snapshot["has_auto_generated"] = has_flag
    if has_flag:
        snapshot["auto_generated_lots"] = int(sql.one(
            "SELECT count(*) FROM stock_lot WHERE auto_generated") or 0)
        # Per-lot, so a migration that kept the TOTAL right by flipping two
        # lots still shows as a diff.
        for name, in sql.rows(
                "SELECT name FROM stock_lot WHERE auto_generated ORDER BY name"):
            snapshot[f"auto/{name}"] = True

    snapshot["lots_per_product"] = int(sql.one("""
        SELECT count(*) FROM (
            SELECT product_id FROM stock_lot GROUP BY product_id
        ) t
    """) or 0)
    return snapshot


@test_case(
    id="TEST-WF007-TC056",
    name="Lot and serial master, including the auto_generated mark",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="stock, dto_mrp",
    priority="P0", kind="API", order=7056,
    description="The lot master survives the upgrade with the same row count "
                "and the same set of auto_generated lots by name — the flag "
                "button_mark_done's rename authorisation keys on.",
    traceability=trace("DATAONE-TC056"))
def test_tc056(ctx):
    reconcile(ctx, "DATAONE-TC056", _capture_lot_master,
              anchors={"has_auto_generated": True})
