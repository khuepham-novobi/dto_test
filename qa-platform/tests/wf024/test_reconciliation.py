"""DATAONE-WF-024 — the RMA sequence baseline/diff: TC044.

One case, and it is the workflow's only DATA_RECONCILIATION: the
``rma_number`` series must continue across the upgrade without resetting and
without ever issuing the same number twice. The workbook states it as eight
SQL steps; every figure they select is ORM-reachable, so the case runs
through ``framework.fg_common.reconcile`` and needs no ``pg_*`` credentials —
the same adaptation WF-013 made for its fourteen reconciliation cases.

What this file proves, and the source every rule was read from
--------------------------------------------------------------

**The sequence exists exactly as the module declares it** —
``DTO-Odoo/3rd-addons/stock_picking_auto_create_lot/data/rma_sequence.xml``
``:3-13``:
``<data noupdate="1">`` / ``sequence_rma_numbers``, name ``RMA Numbers``,
code ``rma_number``, prefix ``%(year)s-``, padding ``3``, ``number_next`` 1,
``number_increment`` 1, ``company_id eval="False"``. ``suffix``,
``use_date_range``, ``implementation`` and ``active`` are NOT set by the XML,
so the model defaults apply and are asserted as such: ``suffix=False``,
``use_date_range=False``, ``implementation='standard'``, ``active=True``
(v17 ``odoo/addons/base/models/ir_sequence.py:132-154``, v19 ``:130-152`` —
the two field blocks are identical, which is the workbook's "ir.sequence is
verified unchanged" turned into an assertion).

The ``noupdate`` flag is asserted too, and it is not decoration: with
``noupdate=False`` a module update rewrites ``number_next`` back to 1
(``data/rma_sequence.xml:10``), which is precisely the silent counter reset
this case exists to catch.

**The live counter is not ``number_next``.** For
``implementation='standard'`` the value lives in the PostgreSQL sequence
``ir_sequence_%03d``: ``_next_do`` calls ``_select_nextval`` (v17
``ir_sequence.py:202-207`` / ``:51-53``, v19 ``:200-205`` / ``:53``) and never
touches the column. The ORM equivalent of the workbook's step 2 is therefore
``number_next_actual``, computed by ``_get_number_next_actual`` (v17
``:100-110``, v19 ``:98-108``) from ``_predict_nextval`` (v17 ``:64-84``,
v19 ``:66``), which reads ``last_value``, ``increment_by`` and ``is_called``
out of ``pg_sequences`` and returns ``last_value + increment_by`` when
``is_called`` — i.e. exactly the number the next ``nextval`` will hand out.

That fact has a consequence for the workbook's step 5, recorded here once:
its SQL compares ``ir_sequence.number_next`` against the highest serial
already issued, and on this sequence ``number_next`` is frozen at 1 while
the series runs in the hundreds, so the literal query returns ``f`` on a
perfectly healthy database. The comparison is made against
``number_next_actual`` instead — the column that actually advances — and the
workbook's own ``number_next`` figure is still captured and logged, never
discarded. That is a **strengthening**: the workbook's version measures a
column that cannot change.

**Numbers are issued by one global counter.**
``stock.picking._get_rma_sequence()``
(``stock_picking_auto_create_lot/models/stock_picking.py:42-44``) calls
``ir.sequence.next_by_code("rma_number")``, which searches
``[('code','=',code), ('company_id','in',[company.id, False])]`` ordered by
``company_id`` (v17 ``ir_sequence.py:279-292``, v19 ``:279``). PostgreSQL
sorts NULLs last, so a company-scoped duplicate would sort FIRST and hijack
the series — ``require_rma_sequence`` BLOCKS on that rather than measuring
the wrong counter.

**The year comes from the sequence, not from this host.** ``%(year)s``
interpolates ``effective_date.strftime('%Y')`` in the session timezone
(v17 ``:209-239``, v19 ``:207-238``), so the "current year" of the
workbook's ``to_char(now(),'YYYY')`` is read back from the sequence's own
rendering rather than from the platform workstation's clock — convention
rule 5, and a closer match to the workbook's server-side ``now()``.

**Padding 3 overflows rather than truncating.** ``get_next_char`` is
``interpolated_prefix + '%%0%sd' % padding % number_next +
interpolated_suffix`` (v17 ``:241-243``, v19 ``:240-242``) — public, returns
a string and **writes nothing**, so step 8's "the 1000th RMA of a year
overflows to four digits" is proven by rendering 1000 instead of writing
``number_next`` on the shared global sequence, which hard rule 3 forbids.

Adaptations, all documented in ``docs/WF-024_AUTOMATION_PLAN.md``
-----------------------------------------------------------------
1. ORM instead of raw SQL (above). ``ctx.sql`` is deliberately never touched:
   it raises BLOCKED when no ``pg_*`` credentials are configured, and this
   case must not report BLOCKED for the absence of something it does not
   need.
2. Step 5 measures ``number_next_actual`` (above).
3. **Step 6 is not executed.** It allocates a number in a rolled-back
   transaction; ``ctx.sql`` is read-only by contract
   (``framework/sqltool.py`` opens the connection with
   ``default_transaction_read_only=on``), the allocation would consume a
   number from a live business sequence, and the workbook itself records
   that a ROLLBACK does not roll a PostgreSQL sequence back. The step writes
   the exact statements and the recorded counter to an artifact so the
   Phase-0a operator can run it by hand and satisfy the postcondition.
4. **The whole snapshot is taken in one pass, in step 1.** The workbook runs
   eight separate statements; taking one consistent read means steps 1-5 and
   8 cannot disagree with each other or with the persisted baseline if a
   return is created while the case runs. Every step then asserts its own
   part of that snapshot.
5. **Step 7 nests ``reconcile``.** ``fg_common.reconcile`` opens its own
   capture/persist/diff steps; running it inside the step named for the
   workbook's step 7 keeps the report in the workbook's own order.
6. **The live counter is asserted directionally, not diffed** (plan item
   18). ``framework/baselines.py:47-54`` ``diff_counts`` compares every key
   of the snapshot it is given, and ``number_next_actual`` is the one key
   this suite's **own fixtures move**: TC184, TC185, TC188, TC189 and TC190
   create two returns each and TC186/TC187 one each, every one of them
   through the real wizard, which calls ``next_by_code('rma_number')``
   (``wizard/stock_picking_return.py:23`` →
   ``models/stock_picking.py:42-44``). A PostgreSQL sequence is never rolled
   back and the sweep only deletes pickings, so the counter is permanently
   ~13 higher after each execution while ``issued_total``,
   ``issued_by_year`` and ``duplicates`` return to their pre-run values.
   Diffing it would therefore FAIL every v19 run with
   ``number_next_actual: baseline=N current=N+13`` — reading exactly like
   the silent counter jump this case exists to catch, and manufactured by
   the suite itself (convention rule 5). It is removed from the diffed
   snapshot by ``common.rma_sequence_diffable`` and replaced by the
   assertion the workbook's *expected_final_state* actually states — "the
   RMA series continues from where v17 left it, with no duplicate and no
   reset": the live counter must still exceed every serial the stored
   baseline recorded as issued. Consuming numbers can only make that more
   true; a reset makes it false. ``number_next`` STAYS diffed — it cannot
   move for ``implementation='standard'`` (``:202-207``), so any change in
   it is the real finding.

Preconditions that are recorded rather than enforced
-----------------------------------------------------
The workbook lists ``TD-CO-06`` (``res.company.vendor_refund_narration``, the
WF-024 E1 undeclared dependency) among the preconditions. TC044 never creates
a return, so nothing it measures depends on the narration; blocking a
read-only capture on it would lose the v17 baseline for no reason. Its
presence is logged as an observation, not asserted.

Fixtures
--------
None. This case creates, writes and deletes nothing — every call is a
``search_read``/``read`` plus the write-free ``get_next_char`` — so there is
no namespace to open and no teardown to run. It measures the live database,
which is the point.

EXPECTED v17 OUTCOME: PASS — the baseline is captured and persisted. BLOCKED,
naming exactly what is missing, if ``stock_picking_auto_create_lot`` is not
contributing the RMA fork or the global ``rma_number`` sequence is absent or
duplicated.
EXPECTED v19 OUTCOME: PASS if the series continued; BLOCKED if no v17
baseline was captured first; any diff in the definition, the frozen
``number_next`` column, the issued population, the duplicate set or the
four-digit set is a real finding and is reported, not softened. The live
PostgreSQL counter is asserted directionally rather than diffed
(adaptation 6) — a counter BELOW the baseline's highest issued serial fails
the case, a counter above it does not.
"""
from adapters.base import OdooRPCError
from framework.baselines import load_baseline
from framework.fg_common import reconcile
from framework.registry import test_case
from tests.wf024.common import (MODULE, NARRATION_FIELD, RMA_COUNTER_KEYS,
                                RMA_OVERFLOW_PATTERN,
                                RMA_OVERFLOW_PROBE, RMA_OVERFLOW_RE,
                                RMA_SEQUENCE_ANCHORS, RMA_SEQUENCE_CODE,
                                RMA_SEQUENCE_XMLID, WORKFLOW, WORKFLOW_NAME,
                                max_issued_serial, require_rma_module,
                                require_rma_sequence, rma_sequence_capture,
                                rma_sequence_diffable, sequence_preview, trace)

#: The PostgreSQL sequence ``implementation='standard'`` actually allocates
#: from — ``'ir_sequence_%03d' % seq.id`` (v17
#: ``odoo/addons/base/models/ir_sequence.py:204``, v19 ``:202``). Named here
#: so step 6's manual script points the Phase-0a operator at the right
#: object; nothing in this file calls ``nextval`` on it.
def _pg_sequence_name(seq_id: int) -> str:
    return "ir_sequence_%03d" % seq_id


def _noupdate_flag(rpc, xmlid: str):
    """``ir.model.data.noupdate`` for one XML id, or None when unresolvable.

    ``data/rma_sequence.xml:3`` wraps the record in ``<data noupdate="1">``,
    so the loader stores ``noupdate = True``. With it False a module update
    would rewrite ``number_next`` back to the XML's 1 (``:10``) — a silent
    counter reset, which is the failure mode this case exists to detect.
    """
    module, _, name = xmlid.partition(".")
    rows = rpc.search_read("ir.model.data",
                           [("module", "=", module), ("name", "=", name)],
                           ["noupdate", "model", "res_id"], limit=1)
    return rows[0] if rows else None


def _year_of(rendered):
    """The year prefix the sequence itself rendered, e.g. ``'2026-042'`` →
    ``'2026'``. None when the rendering is unavailable."""
    if not rendered or "-" not in rendered:
        return None
    return rendered.partition("-")[0]


@test_case(
    id="TEST-WF024-TC044",
    name="RMA sequence YYYY-nnn continues without collision",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P0", kind="DATA", order=24044,
    description="Captures the rma_number sequence definition, its live "
                "PostgreSQL counter, the issued population per year, the "
                "duplicate set and the four-digit overflow set on the v17 "
                "baseline, asserts zero duplicates and that the next number "
                "exceeds the highest serial already issued, and diffs the "
                "whole snapshot on v19.",
    traceability=trace("DATAONE-TC044"))
def test_tc044(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Preconditions: E1 met, clone not upgraded — the RMA fork "
                  "and the global rma_number sequence are present"):
        require_rma_module(ctx)
        seq_id = require_rma_sequence(ctx)
        ctx.log(f"ir.sequence id={seq_id} code={RMA_SEQUENCE_CODE!r}; "
                f"PostgreSQL sequence {_pg_sequence_name(seq_id)}")
        # TD-CO-06 is a workbook precondition for the workflow, not for this
        # case: TC044 creates no return, so nothing it measures reads the
        # narration. Recorded, never asserted — see the module docstring.
        narration_present = rpc.field_exists("res.company", NARRATION_FIELD)
        ctx.log(f"[note] TD-CO-06 res.company.{NARRATION_FIELD} present = "
                f"{narration_present} (WF-024 E1; not a TC044 dependency)")

    with ctx.step("Both versions — the sequence definition"):
        # One consistent read of everything steps 1-5 and 8 assert on, so no
        # two steps can disagree and the persisted baseline matches what was
        # asserted (adaptation 4).
        capture = rma_sequence_capture(ctx)
        for key in sorted(capture):
            ctx.log(f"  {key} = {capture[key]!r}")

        # Mismatch dict, not an assertion loop: one failure reports every
        # field that moved.
        definition = {key: capture.get(key)
                      for key in sorted(RMA_SEQUENCE_ANCHORS)}
        ctx.check("ir.sequence definition vs data/rma_sequence.xml:5-13 plus "
                  "the ir_sequence model defaults",
                  expected=dict(sorted(RMA_SEQUENCE_ANCHORS.items())),
                  actual=definition)

        imd = _noupdate_flag(rpc, RMA_SEQUENCE_XMLID)
        ctx.log(f"ir.model.data for {RMA_SEQUENCE_XMLID} = {imd!r}")
        ctx.check("the sequence record is noupdate (data/rma_sequence.xml:3) "
                  "— without it a module update rewrites number_next to 1",
                  expected=True,
                  actual=bool(imd and imd.get("noupdate")))

    with ctx.step("Both versions — the real counter. For implementation = "
                  "'standard' the value lives in a PostgreSQL sequence, not "
                  "in number_next"):
        number_next = capture.get("number_next")
        next_actual = capture.get("number_next_actual")
        ctx.log(f"number_next (frozen column) = {number_next!r}; "
                f"number_next_actual (_predict_nextval over "
                f"{_pg_sequence_name(seq_id)}) = {next_actual!r}")

        # Both previews are rendered here, before anything is asserted, so
        # the evidence survives a later failure. get_next_char is public and
        # writes nothing (v17 ir_sequence.py:241-243, v19 :240-242).
        next_preview = None
        overflow_preview = None
        try:
            next_preview = sequence_preview(rpc, seq_id, next_actual or 1)
            overflow_preview = sequence_preview(rpc, seq_id,
                                                RMA_OVERFLOW_PROBE)
        except OdooRPCError as exc:
            ctx.log(f"[warn] ir.sequence.get_next_char failed: {exc}")
        ctx.log(f"the next RMA number this counter renders = "
                f"{next_preview!r}; the {RMA_OVERFLOW_PROBE}th of that year "
                f"renders {overflow_preview!r}")

        ctx.check_true(
            "the PostgreSQL counter predicts a usable next value",
            isinstance(next_actual, int) and next_actual >= 1,
            actual_desc=f"number_next_actual={next_actual!r}")

    with ctx.step("Both versions — the numbers already issued"):
        by_year = capture.get("issued_by_year") or {}
        for year in sorted(by_year):
            ctx.log(f"  {year}: {by_year[year]!r}")
        ctx.log(f"issued_total = {capture.get('issued_total')!r}; "
                f"malformed (not YYYY-n…, excluded from the per-year "
                f"aggregate exactly as the workbook's regex excludes them) = "
                f"{capture.get('malformed')!r}")

        # Non-vacuous completeness check: every issued number is either
        # counted in a year bucket or listed as malformed. It proves the
        # capture dropped nothing before the population is diffed.
        counted = sum(bucket["issued"] for bucket in by_year.values())
        ctx.check("every issued rma_number is accounted for "
                  "(per-year + malformed = total)",
                  expected=capture.get("issued_total"),
                  actual=counted + len(capture.get("malformed") or []))

    with ctx.step("Both versions — uniqueness, which is the property that "
                  "actually matters"):
        ctx.check("rma_number values issued more than once", expected=[],
                  actual=capture.get("duplicates"))

    with ctx.step("The collision assertion. The next value must exceed the "
                  "highest serial already issued for the current year"):
        by_year = capture.get("issued_by_year") or {}
        next_actual = capture.get("number_next_actual")

        # The workbook's to_char(now(),'YYYY') evaluated by the SERVER: the
        # year the sequence itself interpolated into its own prefix
        # (ir_sequence.py:209-239 / :207-238), not this workstation's clock.
        current_year = _year_of(next_preview)
        bucket = by_year.get(current_year) or {}
        max_serial = bucket.get("max_serial", 0)          # SQL's COALESCE(…,0)
        ctx.log(f"current year (from the sequence's own prefix) = "
                f"{current_year!r}; max_serial issued that year = "
                f"{max_serial!r}; number_next_actual = {next_actual!r}")
        frozen = capture.get("number_next")
        ctx.log(f"[recorded, not asserted] the workbook's literal comparison "
                f"uses ir_sequence.number_next = {frozen!r}"
                f", which never moves for implementation='standard' "
                f"(ir_sequence.py:202-207) and would read no_collision = "
                f"{bool((frozen or 0) > max_serial)} on a "
                f"healthy database. The assertion below uses the column that "
                f"actually advances.")

        ctx.check("no_collision — the next number exceeds the highest serial "
                  "issued this year", expected=True,
                  actual=bool(next_actual and next_actual > max_serial))
        # capture["no_collision"] is common.no_collision(capture): the same
        # property measured against the LATEST year present in the
        # population, which is the stricter reading when the current year has
        # issued nothing yet. It is the value persisted in the baseline, so
        # it is asserted here rather than only diffed.
        ctx.check("no_collision against the latest year in the population "
                  "(the value persisted in the baseline)", expected=True,
                  actual=capture.get("no_collision"))

    with ctx.step("v19 only — allocate one number in a rolled-back "
                  "transaction and confirm it does not collide"):
        # NOT EXECUTED — adaptation 3. ctx.sql is read-only by contract
        # (framework/sqltool.py opens with default_transaction_read_only=on),
        # and the allocation consumes a number from a live business sequence
        # that a ROLLBACK does not give back. The statements and the counter
        # value are written out so Phase 0a can run it by hand and satisfy
        # the workbook's postcondition.
        script = (
            f"-- DATAONE-TC044 step 6 — MANUAL, Phase 0a. Not run by the\n"
            f"-- automation: ctx.sql is read-only "
            f"(framework/sqltool.py) and the\n"
            f"-- allocation consumes a number from the live "
            f"{RMA_SEQUENCE_CODE!r} series\n"
            f"-- that a ROLLBACK does not give back.\n"
            f"-- environment : {ctx.env.key} (db={ctx.env.db}, "
            f"Odoo {ctx.env.version})\n"
            f"-- ir.sequence : id={seq_id}, "
            f"PostgreSQL sequence {_pg_sequence_name(seq_id)}\n"
            f"-- number_next (frozen column)  : "
            f"{capture.get('number_next')!r}\n"
            f"-- number_next_actual (counter) : "
            f"{capture.get('number_next_actual')!r}\n"
            f"-- next rendered RMA number     : {next_preview!r}\n"
            f"BEGIN;\n"
            f"SELECT nextval('ir_sequence_' || lpad(\n"
            f"  (SELECT id::text FROM ir_sequence WHERE code="
            f"'{RMA_SEQUENCE_CODE}'), 3, '0'));\n"
            f"ROLLBACK;\n"
            f"-- POSTCONDITION: the counter advanced by one. Record the new\n"
            f"-- value so the next capture is not misread as a defect.\n")
        path = ctx.artifacts_dir / "tc044_step6_manual.sql"
        path.write_text(script, encoding="utf-8")
        ctx.add_artifact(path, "log",
                         "TC044 step 6 — manual Phase-0a allocation probe")
        ctx.log("step 6 is a Phase-0a manual step; the script and the "
                f"counter it must be measured against are in {path}")

    with ctx.step("Diff steps 1, 2, 3 and 4"):
        # reconcile opens its own capture/persist/diff steps; it is handed
        # the snapshot already taken in step 1 so the persisted baseline is
        # byte-for-byte what the assertions above ran against — MINUS the
        # live PostgreSQL counter, which this suite's own fixtures advance
        # by roughly a dozen on every execution and which no ROLLBACK gives
        # back (common.RMA_COUNTER_KEYS; adaptation 6). Diffing it would
        # fail every v19 run for a reason the suite itself created.
        excluded = {key: capture.get(key) for key in RMA_COUNTER_KEYS}
        ctx.log(f"excluded from the cross-version diff because this suite "
                f"advances it, asserted directionally below instead: "
                f"{excluded}")
        reconcile(ctx, "DATAONE-TC044",
                  lambda _ctx, _c=rma_sequence_diffable(capture): _c)

        # The workbook's expected_final_state, measured on the column that
        # actually moves: "the RMA series continues from where v17 left it,
        # with no duplicate and no reset". issued_by_year IS diffed and IS
        # deterministic, so the baseline's highest issued serial is a stable
        # comparator; issuing further numbers can only make this assertion
        # more true, while a reset or a restore from an older dump makes it
        # false — which is the failure mode the case is for.
        stored = load_baseline("DATAONE-TC044")
        baseline_max = max_issued_serial((stored or {}).get("data") or {})
        next_actual = capture.get("number_next_actual")
        ctx.log(f"stored baseline: captured_at="
                f"{(stored or {}).get('captured_at')!r} env="
                f"{(stored or {}).get('captured_env')!r} db="
                f"{(stored or {}).get('captured_db')!r}; its highest issued "
                f"serial = {baseline_max!r}; this environment's "
                f"number_next_actual = {next_actual!r}")
        if stored:
            ctx.check_true(
                "the live counter is still ahead of every serial the stored "
                "baseline recorded as issued — the series continued and "
                "cannot re-issue a number the baseline already used",
                bool(next_actual) and next_actual > baseline_max,
                actual_desc=f"number_next_actual={next_actual!r} vs the "
                            f"baseline's highest issued serial "
                            f"{baseline_max!r}")
        else:
            ctx.log("[note] no baseline is stored yet, so there is nothing "
                    "to compare the counter against; this run is the one "
                    "that creates it")

    with ctx.step("Assert the padding-overflow behaviour is preserved: "
                  "padding is 3, so the 1000th RMA of a year overflows to "
                  "four digits. Confirm any existing four-digit numbers sort "
                  "and match on both sides"):
        four_digit = capture.get("four_digit")
        ctx.log(f"existing four-digit rma_numbers (sorted) = {four_digit!r}; "
                "cross-version equality of this set is the diff above")

        ctx.check("padding is 3", expected=3, actual=capture.get("padding"))
        ctx.check_true(
            f"get_next_char({RMA_OVERFLOW_PROBE}) overflows to four digits "
            f"({RMA_OVERFLOW_PATTERN}) instead of truncating",
            bool(overflow_preview and RMA_OVERFLOW_RE.match(overflow_preview)),
            actual_desc=repr(overflow_preview))
        ctx.check("the recorded four-digit set is sorted, as the workbook's "
                  "ORDER BY 1 requires",
                  expected=sorted(four_digit or []), actual=four_digit or [])
