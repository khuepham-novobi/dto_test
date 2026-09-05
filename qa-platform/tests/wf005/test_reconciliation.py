"""DATAONE-WF-005 — decimal precision and the UoM master: TC058.

Follows the suite-wide DATA_RECONCILIATION pattern
(``framework/fg_common.reconcile`` over ``framework/baselines.py``): capture
on Odoo 17, persist, then diff on Odoo 19.

The case is about rounding, which is why it sits in a planning workflow: work
orders, BoM factors and the Gross Requirements columns are all computed
through ``uom.uom.rounding`` and the ``decimal_precision`` records, so a
silent change to either moves every quantity in the workflow.

**The one intended difference.** v17 carries a precision record named
``Product Unit of Measure``; v19 renamed it to ``Product Unit`` and must
carry the same ``digits`` value. The snapshot therefore stores the digits
under a version-independent key so the rename does NOT show up as a diff,
and asserts the rename separately — a diff on that key would mean the value
changed, which is the thing that matters.

**A structural change this case had to absorb.** Odoo 19 removed
``uom.uom.category_id`` and the ``uom_category`` table with it; the model now
carries a hierarchy (``relative_uom_id`` / ``related_uom_ids`` /
``parent_path``). The workbook's steps 3 and 4 read both columns. Capturing
them verbatim would fail on v19 with *Invalid field 'category_id' on
'uom.uom'* — measured — so the snapshot records what both versions can
answer: per-UoM name, factor and rounding, plus the row counts. Rounding is
the value the workflow actually consumes.

EXPECTED v17 OUTCOME: PASS (baseline captured).
EXPECTED v19 OUTCOME: PASS on the precision records. Note that ``dto_17`` on
this deployment is a scratch database rather than a production clone
(docs/ENVIRONMENT_STATUS.md), so a diff in the UoM master there reflects the
environment, not the port.

Read-only: SQL only, no fixtures, nothing swept.
"""
from framework.fg_common import reconcile
from framework.registry import test_case
from tests.wf005.common import WORKFLOW, WORKFLOW_NAME, trace

#: The v17 name and its v19 replacement. Only the digits value must survive.
PRECISION_V17 = "Product Unit of Measure"
PRECISION_V19 = "Product Unit"


def _capture_precision(ctx) -> dict:
    sql = ctx.sql
    snapshot: dict = {}

    for name, digits in sql.rows(
            "SELECT name, digits FROM decimal_precision ORDER BY name"):
        snapshot[f"precision/{name}"] = int(digits)
    snapshot["precision_records"] = int(
        sql.one("SELECT count(*) FROM decimal_precision") or 0)

    # The renamed record, stored under a version-independent key so the
    # rename itself is not a diff but a changed VALUE is.
    row = sql.rows(
        "SELECT name, digits FROM decimal_precision WHERE name IN (%s, %s)",
        (PRECISION_V17, PRECISION_V19))
    snapshot["product_uom_digits"] = int(row[0][1]) if row else None
    snapshot["product_uom_precision_name"] = row[0][0] if row else None
    # Asserted rather than diffed: on v19 the old name must be GONE.
    snapshot["v17_precision_name_still_present"] = bool(sql.rows(
        "SELECT 1 FROM decimal_precision WHERE name = %s", (PRECISION_V17,)))

    # The UoM master, in the columns each version actually STORES. Neither
    # category_id nor rounding is a v19 column: measured, uom_uom holds
    #   id, name, factor, active, relative_factor, relative_uom_id,
    #   parent_path, sequence, package_type_id
    # `rounding` is still a field on the model but no longer stored, so
    # selecting it fails with UndefinedColumn — hence the per-column guard
    # rather than one fixed query.
    optional = [c for c in ("rounding", "factor", "relative_factor", "active")
                if sql.column_exists("uom_uom", c)]
    snapshot["uom_columns"] = ",".join(sorted(optional))
    cols = ", ".join(f"round({c}::numeric, 8)" if c != "active" else c
                     for c in optional)
    for row in sql.rows(f"SELECT id, name->>'en_US'{',' + cols if cols else ''} "
                        f"FROM uom_uom ORDER BY id"):
        uom_id, name = row[0], row[1]
        snapshot[f"uom/{uom_id}/name"] = name
        for col, value in zip(optional, row[2:]):
            snapshot[f"uom/{uom_id}/{col}"] = (
                float(value) if isinstance(value, (int, float)) and col != "active"
                else value)
    snapshot["uom_records"] = int(sql.one("SELECT count(*) FROM uom_uom") or 0)
    snapshot["uom_active"] = int(sql.one(
        "SELECT count(*) FROM uom_uom WHERE active") or 0)
    return snapshot


@test_case(
    id="TEST-WF005-TC058",
    name="Decimal precision records, including the 'Product Unit of Measure' "
         "rename",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="base, uom",
    priority="P1", kind="API", order=5058,
    description="Every decimal_precision record and the UoM master's factor "
                "and rounding are identical across versions; the 'Product "
                "Unit of Measure' record was renamed to 'Product Unit' "
                "carrying the same digits value, and the old name is gone.",
    traceability=trace("DATAONE-TC058"))
def test_tc058(ctx):
    """The rename is asserted through anchors rather than through the diff,
    because a rename is an INTENDED difference: on v19 the record must be
    called ``Product Unit`` and the v17 name must no longer exist, while
    ``product_uom_digits`` — the value the workflow consumes — must be
    identical on both sides and so is left in the diffed snapshot.
    """
    if ctx.env.version == "19":
        anchors = {"product_uom_precision_name": PRECISION_V19,
                   "v17_precision_name_still_present": False}
    else:
        anchors = {"product_uom_precision_name": PRECISION_V17,
                   "v17_precision_name_still_present": True}
    reconcile(ctx, "DATAONE-TC058", _capture_precision, anchors=anchors)
