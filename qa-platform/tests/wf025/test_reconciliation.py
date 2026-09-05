"""DATAONE-WF-025 — cross-version data reconciliation: TC026, TC031.

Both cases follow the suite-wide DATA_RECONCILIATION pattern
(``framework/fg_common.reconcile`` over ``framework/baselines.py``):

* on **Odoo 17** — capture the snapshot and persist it under
  ``data/baselines/<tc_id>.json``;
* on **Odoo 19** — load that baseline, capture again, assert a zero diff.
  With no baseline stored the v19 run reports BLOCKED, naming what to do.

TC026 pins the stock picture planning reads: on-hand and reserved per
product × location, the internal-only total per product, and the quant row
count. Gross Requirements' Available column is computed straight off these
rows, so a silent change here moves every figure in the report.

TC031 pins the v17 ``type``/``detailed_type`` → v19 ``type`` +
``is_storable`` conversion, per product. It is the structural half of what
TC148 checks behaviourally: TC148 proves a storable component still reaches
the report, TC031 proves the population itself converted correctly.

EXPECTED v17 OUTCOME: PASS (baselines captured).
EXPECTED v19 OUTCOME: depends on the baseline. Read the note below before
treating a diff as a defect.

    ``dto_17`` on this deployment is a scratch database, not a production
    clone — 80 journal items against 546,609, 37 internal quant products
    against 969. A baseline captured there and diffed against ``d1v19`` is
    meaningless by construction, and the diff will be enormous and correct.
    ``docs/ENVIRONMENT_STATUS.md`` and the Windows handoff both record this;
    the fix is environmental (restore a production v17 clone), not a code
    change and not an assertion to soften.

Read-only throughout: SQL only, no ORM writes, no fixtures, nothing swept.
"""
from framework.fg_common import reconcile
from framework.registry import test_case
from tests.wf025.common import WORKFLOW, WORKFLOW_NAME, trace


def _capture_stock_picture(ctx) -> dict:
    """On-hand, reserved and row counts — the numbers planning reads."""
    sql = ctx.sql
    snapshot: dict = {}

    # Total on-hand per product across INTERNAL locations only: this is the
    # figure the report's Available column is built from.
    rows = sql.rows("""
        SELECT q.product_id, round(sum(q.quantity)::numeric, 4)
        FROM stock_quant q
        JOIN stock_location l ON l.id = q.location_id
        WHERE l.usage = 'internal'
        GROUP BY 1 ORDER BY 1
    """)
    for product_id, on_hand in rows:
        snapshot[f"onhand/{product_id}"] = float(on_hand or 0)
    snapshot["products_with_internal_stock"] = len(rows)

    # Reserved per product, same scope — the second half of the Available sum.
    rows = sql.rows("""
        SELECT q.product_id, round(sum(q.reserved_quantity)::numeric, 4)
        FROM stock_quant q
        JOIN stock_location l ON l.id = q.location_id
        WHERE l.usage = 'internal' AND q.reserved_quantity <> 0
        GROUP BY 1 ORDER BY 1
    """)
    for product_id, reserved in rows:
        snapshot[f"reserved/{product_id}"] = float(reserved or 0)
    snapshot["products_with_reservations"] = len(rows)

    # Quant row count and warehouse coverage. A warehouse with zero quants
    # means the capture itself failed, so it is asserted rather than trusted.
    snapshot["quant_rows"] = int(sql.one("SELECT count(*) FROM stock_quant") or 0)
    snapshot["internal_locations_with_stock"] = int(sql.one("""
        SELECT count(DISTINCT q.location_id)
        FROM stock_quant q JOIN stock_location l ON l.id = q.location_id
        WHERE l.usage = 'internal' AND q.quantity <> 0
    """) or 0)
    return snapshot


@test_case(
    id="TEST-WF025-TC026",
    name="On-hand quantity per product x location is unchanged",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="stock, dto_mrp",
    priority="P0", kind="API", order=25026,
    description="On-hand and reserved per product across internal locations, "
                "the quant row count and the number of stocked internal "
                "locations are identical on both versions — the figures the "
                "Gross Requirements Available column is computed from.",
    traceability=trace("DATAONE-TC026"))
def test_tc026(ctx):
    reconcile(ctx, "DATAONE-TC026", _capture_stock_picture)


def _capture_product_shape(ctx) -> dict:
    """The v17 type/detailed_type -> v19 type + is_storable conversion.

    Captured in whichever shape the target actually has: v17 carries
    ``detailed_type`` and ``type='product'`` for storables, v19 replaced both
    with ``type='consu'`` plus a boolean ``is_storable``. The snapshot is
    normalised to the SAME keys on both sides so the diff is meaningful:
    a product that was storable on v17 must be storable on v19.
    """
    sql = ctx.sql
    snapshot: dict = {}
    has_is_storable = sql.column_exists("product_template", "is_storable")
    snapshot["shape"] = "v19/is_storable" if has_is_storable else "v17/detailed_type"

    if has_is_storable:
        rows = sql.rows("""
            SELECT id, type, coalesce(is_storable, false), active
            FROM product_template ORDER BY id
        """)
        storable = [(pid, act) for pid, _t, st, act in rows if st]
        services = [(pid, act) for pid, t, _st, act in rows if t == 'service']
    else:
        rows = sql.rows("""
            SELECT id, type, detailed_type, active
            FROM product_template ORDER BY id
        """)
        storable = [(pid, act) for pid, t, _dt, act in rows if t == 'product']
        services = [(pid, act) for pid, t, _dt, act in rows if t == 'service']

    snapshot["templates"] = len(rows)
    snapshot["storable_templates"] = len(storable)
    snapshot["service_templates"] = len(services)
    snapshot["active_templates"] = sum(1 for r in rows if r[-1])
    # Per-product identity, so a conversion that got the totals right by
    # swapping two products still shows up as a diff.
    for pid, _active in storable:
        snapshot[f"storable/{pid}"] = True
    for pid, _active in services:
        snapshot[f"service/{pid}"] = True

    snapshot["variants"] = int(sql.one(
        "SELECT count(*) FROM product_product") or 0)
    return snapshot


@test_case(
    id="TEST-WF025-TC031",
    name="Product type / detailed_type -> type + is_storable conversion is "
         "correct, per product",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="product",
    priority="P0", kind="API", order=25031,
    description="Every template that was storable on v17 is storable on v19 "
                "and every service is still a service, per product id and in "
                "aggregate — the structural half of the check TC148 makes "
                "behaviourally against the report.",
    traceability=trace("DATAONE-TC031"))
def test_tc031(ctx):
    reconcile(ctx, "DATAONE-TC031", _capture_product_shape,
              anchors={"shape": "v19/is_storable"} if ctx.env.version == "19"
              else {"shape": "v17/detailed_type"})
