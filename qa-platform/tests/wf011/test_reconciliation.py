"""DATAONE-WF-011 — RMA numbers and return metadata on pickings: TC054.

One case, and it is this workflow's only DATA_RECONCILIATION. TC054 is a
SHARED workbook case — its ``workflow_ids`` are ``DATAONE-WF-024`` and
``DATAONE-WF-011`` — and ``data/test_registry.json`` resolves
``owning_workflow: DATAONE-WF-011``, so it is written here once and WF-024
references the same ``tc_id`` rather than re-implementing it.

The workbook states the case as five read-only SQL statements and a diff.
Every figure they select is ORM-reachable, so the case runs through
``framework.fg_common.reconcile`` and needs no ``pg_*`` credentials — it
therefore cannot report BLOCKED for the absence of something it does not
need. That is the same adaptation WF-013 made for its fourteen
reconciliation cases and WF-024 for TC044
(``docs/WF-011_AUTOMATION_PLAN.md`` adaptation 3).

Abbreviations: ``DTO`` = ``D:/Projects/dataone/DTO-Odoo`` read on branch
**main** — the v17 baseline; the working tree is checked out on ``UAT``,
which already carries the v19 port, so a worktree read would have measured
the wrong code — ``O17`` = ``D:/Projects/dataone/odoo-17.0``, ``O19`` =
``D:/Projects/odoo-19.0``.

What this file proves
---------------------

**The metadata, and its only writer.** ``DTO 3rd-addons/
stock_picking_auto_create_lot/models/stock_picking.py`` declares the three
RMA fields on ``stock.picking``: ``rma_number`` ``Char`` (``:9``),
``reason_for_return`` ``Selection`` (``:11-33``, the nineteen pairs at
``:13-31`` — reproduced verbatim in ``common.RMA_REASON_SELECTION``, EN DASH
in ``902`` included) and ``return_notes`` ``Text`` (``:35``). The numbers
come from one global counter: ``_get_rma_sequence`` (``:42-44``) calls
``ir.sequence.next_by_code('rma_number')``, and the wizard override
``wizard/stock_picking_return.py:10-15`` writes both ``rma_number`` (``:13``)
and ``note = self.env.company.vendor_refund_narration`` (``:14``) onto the
newly created return — the same two writes again in
``_create_returns_and_replenishments`` (``:17-21``, F091's zero-priced
replacement lines at ``:43``). ``reason_for_return`` and ``return_notes``
have **no** code writer: they are operator-entered, which is why a lost one
is silent and why this case exists.

That wizard is also the workbook's ``v19_watch``: ``_create_returns`` was
reworked in v19 and the fork overrides it. This case therefore checks the
**stored data**; the writer itself is WF-024/INV's subject and is not
exercised here.

**The narration.** ``res.company.vendor_refund_narration`` is
``fields.Html`` contributed by ``DTO project-addons/dto_account/models/
res_company.py:51-54``, with a non-empty default
(``_default_vendor_refund_narration``, ``:11-49``) — so a company created
after that module was installed carries it, and the note the wizard copies
onto every RMA picking is that text. Recorded rather than asserted: an
``Html`` value can be ``IS NOT NULL`` and still be visually empty
(``<p><br></p>``), which ``dto_account/models/account_move.py:46`` itself
guards with ``is_html_empty``; ``common.rma_capture`` records the workbook's
own ``IS NOT NULL`` reading (``bool(value)``) and this file logs the
distinction instead of inventing a stricter expectation.

**Two of the workbook's five statements cannot run as written**, and the
reason is structural rather than a typo. Both adaptations are
``common.rma_capture``'s, and both are recorded in
``docs/WF-011_AUTOMATION_PLAN.md`` adaptations 1 and 2:

* ``count(*) FILTER (WHERE ship_blind IS TRUE) FROM stock_picking`` —
  ``stock.picking.ship_blind`` is ``fields.Boolean(related='sale_id.
  ship_blind')`` with no ``store`` (``DTO project-addons/dto_sale_stock/
  models/stock_picking.py:10``), so **no such column exists** on either
  version. It is read through ``sale_id.ship_blind``, which IS an ordinary
  stored Boolean (``dto_sale_stock/models/sale_order.py:10``), and the
  order-level count is captured beside the picking-level one.
* ``packing_slip_attachment IS NOT NULL`` — that field is ``fields.Binary``
  (``DTO project-addons/dto_purchase_stock/models/stock_picking.py:14-16``)
  and ``Binary.attachment`` defaults to ``True``, which makes
  ``column_type`` ``None`` (``O17 odoo/fields.py:2334-2348``; ``O19
  odoo/orm/fields_binary.py:29-43``), so it has no column either. It is
  counted through ``ir.attachment`` on ``res_field``.

Step 5 does not take either of those statements on trust: it asks
``ir.model.fields`` and asserts the two structural facts the adaptations
rest on — ``ship_blind`` is ``store = False`` with ``related =
'sale_id.ship_blind'``, and ``packing_slip_attachment`` is ``ttype =
'binary'``. Those columns are reflected straight off the field objects
(``store = bool(field.store)``, ``related = field.related or None`` —
``O17 odoo/addons/base/models/ir_model.py:1106-1121``, ``O19 :1172-1188``),
so a port that quietly reimplemented ``ship_blind`` as a stored copy fails
here loudly. That is the workbook's own parenthetical in step 5 — *"confirm
every column name against ir_model_fields"* — implemented rather than
skipped.

**Ownership is recorded, never diffed.** ``ir.model.fields.modules``
(compute ``_in_modules``, ``O17 :565, :624-631`` / ``O19 :570, :629-636``;
deterministic, it joins a *sorted* set) answers who really contributes each
field, and two of the ten belong to neither module the workbook names:
``carrier_tracking_ref`` and ``packing_slip_attachment`` to
``dto_purchase_stock``, and ``vendor_refund_narration`` to ``dto_account``.
It is logged and written to the artifact but kept **out** of the diffed
snapshot on purpose: the workbook's own Notes record the extraction to a
proper ``dto_rma`` module as a decision, and say this case is the data
evidence that must survive that extraction *unchanged* — so a sanctioned
ownership move must not be reported as a data regression.

What is asserted, beyond the diff
---------------------------------
1. step 2 — ``with_rma`` equals the number of rows step 1 captured (the two
   reads cannot disagree), and equals **TC044's issued count** when that
   baseline is available (see adaptation 4 below);
2. step 3 — the declared taxonomy is exactly the nineteen source pairs;
3. step 4 — ``res.company.vendor_refund_narration`` still exists, without
   which every figure in that step is meaningless;
4. step 5 — every field the workbook names is present (for the fields whose
   owning module is installed on the target), plus the two structural facts
   above;
5. step 6 — ``reconcile``: anchors, then persist (v17) or zero-diff (v19).

Adaptations — documented, never assertion-weakening
---------------------------------------------------
1. **ORM instead of psql** (above). ``ctx.sql`` is deliberately never
   touched: it reports BLOCKED without ``pg_*`` credentials, and this case
   must not report BLOCKED for something it does not need
   (``docs/WF-011_AUTOMATION_PLAN.md``: "``ctx.sql`` is **not** required by
   any case in this suite").
2. **The whole snapshot is taken in one pass, in step 1.** The workbook runs
   five separate statements; one consistent read means steps 1-5 cannot
   disagree with each other or with the persisted baseline if a return is
   created while the case runs. Each step then asserts its own part, and
   step 6 hands ``reconcile`` the very dict the assertions ran against —
   the same shape WF-024's TC044 uses.
3. **Long free text is bounded in the snapshot, verbatim in the artifact.**
   ``return_notes`` is unbounded operator text; a value longer than 200
   characters enters the snapshot as ``<n chars sha1:…>`` (``_bounded``),
   which detects any change byte-for-byte while keeping the baseline and the
   per-key log readable. The untruncated rows are written to
   ``tc054_rma_pickings.json`` on every run, so no evidence is lost.
4. **The TC044 cross-check is opportunistic, and says so.** The workbook's
   expected result adds "Step 2's with_rma equals TC044's issued count".
   TC044 lives in another suite (``tests/wf024/test_reconciliation.py``) and
   convention rule 5 forbids depending on another test's run, so the figure
   is taken from TC044's **persisted baseline** when one exists
   (``tests/wf024/common.py:1771`` — ``issued_total = len(search_read(
   rma_number != False))``, the identical measure) and asserted; when it
   does not exist, or when a v17 run finds a baseline captured against a
   different database, the fact is logged as not cross-checkable instead of
   being asserted against an unrelated population.
5. **Tuples are normalised to lists before the snapshot is persisted.**
   ``framework/baselines.py`` stores the baseline as JSON, which has no
   tuple type, so ``reason_selection`` would come back as a list of lists
   and every v19 run would report a phantom diff against a live capture that
   still holds tuples. ``_json_stable`` applies the same normalisation to
   both sides; it changes no value, only its Python type.
6. **Per-row keys are record ids** (``rma/<id>``) — the workbook's own
   ``ORDER BY sp.id``. An in-place upgrade preserves ids, and the id is what
   makes a per-row diff legible. Convention rule 5's "no reliance on record
   ids" governs *fixtures*; this case creates none.
7. **Anchors are split.** ``reconcile``'s ``anchors=`` carries the
   structural half — the three RMA fields' presence and the nineteen
   selection KEYS — while the labelled pairs are asserted in step 3, where
   the workbook asks for the taxonomy. A loaded translation would move the
   labels but never the keys, and this split makes which of the two moved
   legible from the failure name alone.

Fixtures
--------
None. This case creates, writes and deletes nothing — every call is a
``search_read`` / ``read`` / ``search_count`` / ``read_group`` — so there is
no namespace to open and no teardown to run. It measures the live database,
which is the point of a reconciliation case. ``common.require_module_build``
still runs first, because a field that is absent is only a finding once it
is known which checkout the server actually loaded.

EXPECTED v17 OUTCOME: PASS — the baseline is captured and persisted. BLOCKED,
naming exactly what is missing, if ``stock_picking_auto_create_lot`` is not
contributing the three RMA fields (the recorded ``dto_rma`` extraction would
show up exactly there) or if the server loaded a module build from another
series.
EXPECTED v19 OUTCOME: PASS if nothing moved. Any diff is a real finding and
is reported, not softened. Where a lost field surfaces depends on which one:
losing one of the three RMA fields stops the case in the precondition, as
BLOCKED naming the ``dto_rma`` extraction, because nothing downstream would
then be measuring what this case is about; losing any of the other seven
surfaces twice, as a failed presence check in step 5 and as a diff in step 6.
Two differences are expected to appear
and are findings, not test bugs: ``count.shipping_weight_set``, because v19
makes ``shipping_weight`` a **stored** compute
(``O19 stock/models/stock_picking.py:666-670``) and the upgrade recompute
zeroed operator-entered values (WF011a-README ``D-new-10``), and the
``reason.*`` histogram if any return was re-coded. BLOCKED on v19 if no v17
baseline was captured first.
"""
from __future__ import annotations

import hashlib
import json

from framework.baselines import load_baseline
from framework.fg_common import reconcile
from framework.registry import test_case
from tests.wf011.common import (DTO_PICKING_FIELDS, RMA_FIELDS,
                                RMA_REASON_SELECTION, RMA_SEQUENCE_CODE,
                                WORKFLOW, WORKFLOW_NAME, m2o_id,
                                require_module_build, require_modules,
                                rma_capture, trace)

_TC = "DATAONE-TC054"
#: The other suite's reconciliation whose issued count the workbook's
#: expected result cross-references (tests/wf024/test_reconciliation.py).
_TC044 = "DATAONE-TC044"

#: The module that contributes the three RMA fields and their only writer
#: (DTO 3rd-addons/stock_picking_auto_create_lot).
_RMA_MODULE = "stock_picking_auto_create_lot"

#: Longer free text enters the snapshot as a digest — adaptation 3.
_TEXT_LIMIT = 200

#: The columns the workbook's step-1 SELECT names, in its own order. `id` is
#: the snapshot key rather than a value, exactly as `ORDER BY sp.id` implies.
_RMA_ROW_FIELDS = ["name", "rma_number", "reason_for_return", "return_notes",
                   "state", "picking_type_id", "partner_id", "date_done"]

#: Who really contributes each field the workbook's step 5 names — the same
#: key set as common.DTO_PICKING_FIELDS, reduced to the bare module name so
#: a missing module can be told apart from a lost field. Two of them belong
#: to neither module the workbook's `modules` column names.
_FIELD_OWNER_MODULE = {
    "rma_number": _RMA_MODULE,
    "reason_for_return": _RMA_MODULE,
    "return_notes": _RMA_MODULE,
    "ship_blind": "dto_sale_stock",
    "carrier_tracking_ref": "dto_purchase_stock",
    "packing_slip_attachment": "dto_purchase_stock",
    "packing_slip_attachment_name": "dto_purchase_stock",
    "shipping_weight": "dto_stock",
    "box_count": "dto_stock",
    "default_box_weight": "dto_stock",
}

#: The taxonomy as the source declares it, normalised to the JSON shape the
#: snapshot carries (adaptation 5). stock_picking_auto_create_lot/models/
#: stock_picking.py:13-31.
_EXPECTED_SELECTION = [list(pair) for pair in RMA_REASON_SELECTION]
_EXPECTED_SELECTION_KEYS = [key for key, _label in RMA_REASON_SELECTION]

#: reconcile()'s anchors — the structural half (adaptation 7). Asserted on
#: BOTH versions, before the baseline is persisted or diffed.
_ANCHORS = {f"field_present.{name}": True for name in RMA_FIELDS}
_ANCHORS["reason_selection_keys"] = _EXPECTED_SELECTION_KEYS

#: The two facts that justify the two adapted SQL statements, read back off
#: ir.model.fields (see _schema_rows for where each value comes from).
_SCHEMA_FACTS = {
    # dto_sale_stock/models/stock_picking.py:10 — related, NOT stored, so
    # stock_picking carries no ship_blind column on either version.
    "ship_blind [ttype, store, related]": ["boolean", False,
                                           "sale_id.ship_blind"],
    # dto_purchase_stock/models/stock_picking.py:14-16 — Binary, and
    # Binary.attachment defaults True (O17 odoo/fields.py:2334-2348), so
    # column_type is None and there is no column here either.
    "packing_slip_attachment ttype": "binary",
}


# --------------------------------------------------------------------------
# Local helpers. Everything this suite already provides is imported from
# tests/wf011/common.py; these five exist only for this case and are named
# in the return value of the agent that wrote the file.
# --------------------------------------------------------------------------
def _json_stable(value):
    """Recursively turn tuples into lists — adaptation 5.

    ``framework/baselines.py`` persists the snapshot with ``json.dumps``,
    which has no tuple type, so a captured ``[('901', '…'), …]`` returns from
    the baseline as ``[['901', '…'], …]`` and ``diff_counts`` would report a
    difference where nothing moved. Applying the same normalisation to the
    live capture makes the two sides comparable without touching a value.
    """
    if isinstance(value, (list, tuple)):
        return [_json_stable(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_stable(item) for key, item in value.items()}
    return value


def _bounded(value, limit: int = _TEXT_LIMIT):
    """Snapshot form of an unbounded free-text column — adaptation 3.

    Deterministic on both versions: the same text always yields the same
    digest, so a changed note is a diff and an unchanged one is not. The
    untruncated value is preserved in this case's artifact.
    """
    if not value:
        return False
    text = str(value)
    if len(text) <= limit:
        return text
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]
    return f"<{len(text)} chars sha1:{digest}>"


def _require_rma_fields(ctx):
    """BLOCK unless the RMA fork is contributing the three fields.

    Without them there is no metadata to reconcile, and the anchors below
    would report a data loss for what is really an environment fact. The
    recorded decision to extract a proper ``dto_rma`` module (workbook Notes)
    would surface exactly here, which is why the reason names it.
    """
    rpc = ctx.adapter.rpc
    require_modules(ctx, [_RMA_MODULE])
    missing = [name for name in RMA_FIELDS
               if not rpc.field_exists("stock.picking", name)]
    if missing:
        ctx.blocked(
            f"{_RMA_MODULE} is installed on {ctx.env.key} (db={ctx.env.db}) "
            f"but is not contributing these stock.picking fields: "
            f"{', '.join(missing)}. They are declared at "
            f"{_RMA_MODULE}/models/stock_picking.py:9 (rma_number), :11-33 "
            "(reason_for_return) and :35 (return_notes); their absence means "
            "the fork was replaced — the recorded dto_rma extraction is the "
            "likely cause — and this case has nothing to reconcile. Confirm "
            "which module owns the RMA metadata on this target before "
            "reading the result as a data loss.")


def _installed_modules(ctx, names) -> set:
    """Which of ``names`` are installed. Read-only, never blocks: step 5
    needs to tell "the module is gone" apart from "the field was lost"."""
    rows = ctx.adapter.rpc.search_read(
        "ir.module.module",
        [("name", "in", sorted(set(names))), ("state", "=", "installed")],
        ["name"])
    return {row["name"] for row in rows}


def _rma_rows(ctx) -> tuple[list[dict], dict]:
    """Workbook step 1, through the ORM: every picking with an RMA number.

    Returns ``(rows, snapshot)`` — the untruncated rows for the artifact and
    the diffable snapshot keyed ``rma/<id>``, m2o values reduced to the ids
    the workbook's SELECT names (``sp.picking_type_id``, ``sp.partner_id``)
    rather than to display names, which are not stable evidence.
    """
    rpc = ctx.adapter.rpc
    rows = rpc.search_read("stock.picking", [("rma_number", "!=", False)],
                           _RMA_ROW_FIELDS, order="id")
    snapshot = {"rma_rows.captured": len(rows)}
    for row in rows:
        snapshot[f"rma/{row['id']}"] = [
            row.get("name") or False,
            row.get("rma_number") or False,
            row.get("reason_for_return") or False,
            _bounded(row.get("return_notes")),
            row.get("state") or False,
            m2o_id(row.get("picking_type_id")),
            m2o_id(row.get("partner_id")),
            row.get("date_done") or False,
        ]
    return rows, snapshot


def _schema_rows(ctx, names) -> dict:
    """Workbook step 5's parenthetical: confirm every column name against
    ``ir_model_fields``.

    ``ttype``, ``store`` and ``related`` are reflected straight off the field
    objects (``O17 odoo/addons/base/models/ir_model.py:1106-1121`` —
    ``store = bool(field.store)`` at ``:1118``, ``related = field.related or
    None`` at ``:1121``; ``O19 :1172-1188``), so they are the database's own
    answer to what each name really is. ``modules`` (``_in_modules``,
    ``O17 :624-631`` / ``O19 :629-636``) is logged as evidence and kept OUT
    of the returned snapshot — see the module docstring, "Ownership is
    recorded, never diffed".
    """
    rpc = ctx.adapter.rpc
    rows = rpc.search_read(
        "ir.model.fields",
        [("model", "=", "stock.picking"), ("name", "in", sorted(names))],
        ["name", "ttype", "store", "related", "modules"], order="name")
    by_name = {row["name"]: row for row in rows}
    snapshot = {}
    for name in sorted(names):
        row = by_name.get(name)
        if not row:
            snapshot[f"schema.{name}"] = "NOT IN ir.model.fields"
            ctx.log(f"  stock.picking.{name}: absent from ir.model.fields")
            continue
        snapshot[f"schema.{name}"] = [row["ttype"], bool(row["store"]),
                                      row.get("related") or False]
        ctx.log(f"  stock.picking.{name}: ttype={row['ttype']!r} "
                f"store={row['store']!r} related={row.get('related')!r} "
                f"modules={row.get('modules')!r} "
                f"[workbook attributes it to: "
                f"{DTO_PICKING_FIELDS.get(name, '(not named)')}]")
    return snapshot


def _tc044_cross_check(ctx, with_rma):
    """The second sentence of the workbook's expected result — adaptation 4.

    ``with_rma`` and TC044's ``issued_total`` are the identical measure
    (``tests/wf024/common.py:1722-1727, 1771`` — every ``stock.picking`` with
    ``rma_number != False``), so where TC044's baseline exists this is a real
    cross-suite equality; where it does not, the fact is recorded rather than
    asserted against a population that was never captured. Convention rule 5
    forbids depending on another test's *run*; reading a persisted baseline
    when one happens to be there, and saying so when it is not, keeps the
    workbook's sentence honest either way.
    """
    base = load_baseline(_TC044)
    if not base:
        ctx.log(f"[recorded, not asserted] no {_TC044} baseline is stored "
                "yet, so 'with_rma equals TC044's issued count' cannot be "
                "cross-checked in this run — execute TEST-WF024-TC044 "
                "(tests/wf024/test_reconciliation.py) on the v17 baseline "
                "first, then re-run this case.")
        return
    issued = (base.get("data") or {}).get("issued_total")
    ctx.log(f"{_TC044} baseline: env={base.get('captured_env')!r} "
            f"db={base.get('captured_db')!r} at={base.get('captured_at')!r} "
            f"issued_total={issued!r}")
    if issued is None:
        ctx.log(f"[recorded, not asserted] the stored {_TC044} baseline "
                "carries no issued_total key, so there is nothing to compare "
                "with_rma against.")
        return
    if ctx.env.version == "17" and base.get("captured_db") != ctx.env.db:
        ctx.log(f"[recorded, not asserted] the stored {_TC044} baseline was "
                f"captured on db={base.get('captured_db')!r}, not on this "
                f"run's db={ctx.env.db!r}. Comparing them would measure two "
                "populations rather than one regression.")
        return
    ctx.check(f"with_rma equals {_TC044}'s issued count (the identical "
              "measure: every stock.picking with rma_number set)",
              expected=issued, actual=with_rma)


# ---------------------------------------------------------------- TC054
@test_case(
    id="TEST-WF011-TC054",
    name="RMA numbers and return metadata on pickings",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_sale_stock, stock_picking_auto_create_lot",
    priority="P1", kind="DATA", order=11054,
    description="Captures every RMA picking's number, reason, notes and "
                "neighbouring DataOne picking fields read-only through the "
                "ORM, asserts the declared taxonomy and the two schema facts "
                "the workbook's unrunnable SQL rests on, persists the v17 "
                "baseline and diffs it on v19.",
    traceability=trace("DATAONE-TC054"))
def test_tc054(ctx):
    # Every read in this case goes through a helper above or through
    # common.rma_capture; nothing here touches ctx.adapter.rpc directly,
    # and nothing writes.
    with ctx.step("Preconditions: the target's own module build, and the "
                  "RMA fork contributing its three stock.picking fields"):
        require_module_build(ctx)
        _require_rma_fields(ctx)
        installed = _installed_modules(ctx, _FIELD_OWNER_MODULE.values())
        absent = sorted(set(_FIELD_OWNER_MODULE.values()) - installed)
        ctx.log(f"modules owning the fields step 5 names — installed: "
                f"{sorted(installed)}; not installed: {absent}")
        # The writer, recorded not exercised: this case checks the STORED
        # data, while stock.return.picking._create_returns() is WF-024's.
        ctx.log(f"[note] the RMA numbers are issued by ir.sequence code "
                f"{RMA_SEQUENCE_CODE!r} through _get_rma_sequence "
                f"({_RMA_MODULE}/models/stock_picking.py:42-44) and written "
                f"by wizard/stock_picking_return.py:13 — that writer is "
                "WF-024's subject and is never called here.")

    snapshot: dict = {}

    with ctx.step("Both versions — RMA pickings and their metadata"):
        # One consistent read of everything steps 1-5 assert on (adaptation
        # 2), so no two steps can disagree and the persisted baseline is
        # byte-for-byte what the assertions below ran against.
        rows, row_snapshot = _rma_rows(ctx)
        capture = rma_capture(ctx)
        snapshot.update(_json_stable(capture))
        snapshot.update(_json_stable(row_snapshot))
        snapshot["reason_selection_keys"] = [
            pair[0] for pair in snapshot.get("reason_selection") or []]

        # The untruncated rows, written before anything is asserted so the
        # evidence survives a later failure (adaptation 3).
        path = ctx.artifacts_dir / "tc054_rma_pickings.json"
        path.write_text(json.dumps(rows, indent=1, ensure_ascii=False,
                                   default=str), encoding="utf-8")
        ctx.add_artifact(path, "log", "TC054 RMA pickings, verbatim")
        ctx.log(f"{len(rows)} picking(s) carry an rma_number; the full rows "
                f"are in {path}")
        if not rows:
            # Not a failure: a clone with no returns is a legitimate state,
            # and inventing a minimum would be an expectation the workbook
            # never states. It IS worth reading beside the verdict.
            ctx.log("[warn] this target holds no RMA picking at all, so the "
                    "per-row half of this case is vacuous — the counts, the "
                    "taxonomy and the schema half still run.")

    with ctx.step("Both versions — the counts"):
        # Logged under the workbook's own SQL aliases so the report can be
        # read against the statement it implements.
        with_rma = snapshot.get("count.rma_number_set")
        ctx.log(f"  with_rma        = {with_rma!r}")
        ctx.log(f"  with_reason     = "
                f"{snapshot.get('count.reason_for_return_set')!r}")
        ctx.log(f"  with_notes      = "
                f"{snapshot.get('count.return_notes_set')!r}")
        ctx.log(f"  blind_shipments = "
                f"{snapshot.get('count.picking_of_blind_order')!r} pickings "
                f"of {snapshot.get('count.sale_order_ship_blind')!r} blind "
                "order(s) — read through sale_id.ship_blind, because "
                "stock_picking has no ship_blind column (adaptation 1)")
        ctx.log(f"  all_pickings    = {snapshot.get('stock_picking.total')!r}")

        # Non-vacuous completeness check: the row read and the count read
        # must agree, which proves step 1 dropped nothing before the
        # population is diffed.
        ctx.check("with_rma equals the number of rows step 1 captured",
                  expected=with_rma, actual=len(rows))
        _tc044_cross_check(ctx, with_rma)

    with ctx.step("Both versions — the reason-code taxonomy in use (F072's "
                  "19 codes and F088's return codes)"):
        in_use = {key[len("reason."):]: value
                  for key, value in sorted(snapshot.items())
                  if key.startswith("reason.")}
        for code, count in in_use.items():
            label = dict(RMA_REASON_SELECTION).get(code, "(not declared)")
            ctx.log(f"  {code} {label!r}: {count!r}")
        undeclared = sorted(set(in_use) - set(_EXPECTED_SELECTION_KEYS))
        # Recorded, not asserted: a stored code that the selection no longer
        # declares is legacy data, and the workbook's expected result is
        # about the DIFF, not about the population being tidy. The diff
        # still carries it, so nothing is lost by refusing to invent a
        # verdict here.
        ctx.log(f"[recorded, not asserted] codes stored but not declared by "
                f"the current selection: {undeclared}")

        ctx.check("the declared reason_for_return taxonomy, verbatim from "
                  f"{_RMA_MODULE}/models/stock_picking.py:13-31",
                  expected=_EXPECTED_SELECTION,
                  actual=snapshot.get("reason_selection"))

    with ctx.step("Both versions — the note that vendor_refund_narration "
                  "populates"):
        rma_with_note = snapshot.get("count.rma_with_note")
        narration = snapshot.get("company.vendor_refund_narration_set")
        ctx.log(f"  RMA pickings whose note is set = {rma_with_note!r} of "
                f"{snapshot.get('count.rma_number_set')!r}")
        ctx.log(f"  narration_set per company (the workbook's IS NOT NULL, "
                f"so a visually empty <p><br></p> still reads True — "
                f"dto_account/models/account_move.py:46 guards it with "
                f"is_html_empty) = {narration!r}")
        ctx.log("[note] every RMA picking created through the wizard gets "
                "its note from the company narration "
                f"({_RMA_MODULE}/wizard/stock_picking_return.py:14), which "
                "carries a non-empty default (dto_account/models/"
                "res_company.py:11-54); a shortfall against with_rma is a "
                "note cleared after creation, not a missing narration.")

        # The one assertion this step can make without inventing an
        # expectation: the field the whole step measures must still exist.
        ctx.check_true(
            "res.company.vendor_refund_narration still exists — without it "
            "every figure in this step is meaningless",
            narration != "FIELD ABSENT", actual_desc=repr(narration))

    with ctx.step("Both versions — the other DataOne picking fields, so a "
                  "partial loss is visible"):
        ctx.log(f"  with_tracking     = "
                f"{snapshot.get('count.carrier_tracking_ref_set')!r}")
        ctx.log(f"  with_ship_weight  = "
                f"{snapshot.get('count.shipping_weight_set')!r}")
        ctx.log(f"  with_packing_slip = "
                f"{snapshot.get('count.packing_slip_attachment')!r} "
                "ir.attachment row(s) on res_field="
                "'packing_slip_attachment', because the field is an "
                "attachment-backed Binary with no column (adaptation 2)")

        # The workbook's parenthetical, implemented: ask ir.model.fields.
        snapshot.update(_json_stable(
            _schema_rows(ctx, sorted(_FIELD_OWNER_MODULE))))

        # One mismatch dict, not an assertion loop: a failure names every
        # field that moved. Fields whose owning module is not installed are
        # excluded from the expectation and reported as such — that is an
        # environment fact, while a missing field on an installed module is
        # the data loss this step exists to make visible.
        expected_presence, actual_presence = {}, {}
        for name in sorted(_FIELD_OWNER_MODULE):
            owner = _FIELD_OWNER_MODULE[name]
            present = snapshot.get(f"field_present.{name}")
            if owner not in installed:
                ctx.log(f"[recorded, not asserted] stock.picking.{name}: "
                        f"{owner} is not installed on this target "
                        f"(field_present={present!r}) — the cross-version "
                        "diff still carries it")
                continue
            expected_presence[name] = True
            actual_presence[name] = present
        ctx.check("every DataOne picking field the workbook names is present "
                  "(for the fields whose owning module is installed)",
                  expected=expected_presence, actual=actual_presence)

        # The two schema facts the adapted SQL statements rest on. A port
        # that reimplemented ship_blind as a stored copy, or moved the
        # packing slip into a real column, fails here loudly instead of
        # silently invalidating adaptations 1 and 2. Gated on the owning
        # module the same way the presence check is: an absent module is an
        # environment fact, and the diff still carries it.
        ship_blind = snapshot.get("schema.ship_blind")
        packing_slip = snapshot.get("schema.packing_slip_attachment")
        facts_expected, facts_actual = {}, {}
        if _FIELD_OWNER_MODULE["ship_blind"] in installed:
            key = "ship_blind [ttype, store, related]"
            facts_expected[key] = _SCHEMA_FACTS[key]
            facts_actual[key] = ship_blind
        if _FIELD_OWNER_MODULE["packing_slip_attachment"] in installed:
            key = "packing_slip_attachment ttype"
            facts_expected[key] = _SCHEMA_FACTS[key]
            facts_actual[key] = (packing_slip[0]
                                 if isinstance(packing_slip, list)
                                 else packing_slip)
        ctx.check(
            "the two fields the workbook's SQL cannot select: ship_blind is "
            "a non-stored related (dto_sale_stock/models/stock_picking.py:10) "
            "and packing_slip_attachment is a Binary (dto_purchase_stock/"
            "models/stock_picking.py:14-16), so neither has a column",
            expected=facts_expected, actual=facts_actual)

    with ctx.step("Diff steps 1, 2, 3, 4 and 5"):
        # reconcile opens its own anchor/persist/diff steps; it is handed the
        # snapshot already taken in step 1 so the persisted baseline is
        # byte-for-byte what the assertions above ran against (adaptation 2).
        reconcile(ctx, _TC, lambda _ctx, _s=snapshot: _s, anchors=_ANCHORS)
