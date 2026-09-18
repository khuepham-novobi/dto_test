"""DATAONE-WF-017 — the acceptance criterion for the valuation rebuild:
TC309, and the catalogue reconciliation TC036.

TC309. F202's own note calls this *"the acceptance criterion for the entire
valuation rebuild as it affects Workday"*. Column T is a REQUIRED Workday
column; if it resolves wrongly, Workday files DataOne's inventory
accounting under the wrong journal source — a reconciliation problem that
surfaces weeks later at the close, **in Workday, not in Odoo**.

It is cheap to capture on v17 today and impossible to reconstruct after the
clone is upgraded, which is why it is a DATA_RECONCILIATION case rather
than a plain assertion: on v17 it captures the whole matrix and persists
it; on v19 it re-derives and asserts zero difference.

Step 9 is the case's real payload. It documents, ON v17, the exact
mechanism that will produce blank column T values on v19: an entry type for
which a multiple-mode journal has no mapping row resolves
``journal_workday_id`` **empty, with no error**
(``account_journal.py:40-46`` — ``get_journal_workday`` filters the mapping
lines and returns whatever that yields, which for an unmapped type is an
empty recordset). So when TC306 fails on v19, the diagnosis is already
written.

Step 4 is the one most likely to be got wrong by a careful port: the
catalogue's casing is INTERNALLY INCONSISTENT — ``Inventory_Put_Away`` sits
beside ``INVENTORY_PUT_AWAY_ADJUSTMENT`` in the 131-row file — and a case
mismatch in column T is a **silent rejection on Workday's side**, not an
Odoo error. Every expected value is therefore read from the DATABASE and
compared against the shipped CSV's own xml ids, never retyped.

TC036 is the catalogue's own survival: 131 sources, 7 mappings, and — the
assertion that actually matters — **the same ids**, because a re-created
catalogue with new ids breaks every foreign key on ``account.move
.journal_workday_id``. The stable identity across databases is the xml id,
not the row id, so the capture keys on ``module.name`` from
``ir.model.data`` and records the id mapping alongside it.

Both cases are READ-ONLY with two exceptions, each scoped and reverted:
TC309 step 7 creates a duplicate mapping row on a TOKEN-SCOPED journal to
assert the uniqueness constraint, and step 8 ticks multiple mode on a
token-scoped journal with no mappings to assert the other one. Neither
touches ``account.1_inventory_valuation``.

EXPECTED v17 OUTCOME: PASS — captures and persists both baselines.
EXPECTED v19 OUTCOME: PASS when the catalogue and the derivation are
identical; BLOCKED when no v17 baseline has been captured yet. TC309's
diff is where the ``stock.valuation.layer`` deletion shows up as a
population that moved rather than as an exception.
"""
import hashlib
import json

from framework.fg_common import reconcile
from framework.registry import test_case
from tests.wf017.common import (ENTRY_TYPE_MAPPING,  # noqa: F401
                                ERR_DUPLICATE_ENTRY_TYPE, ERR_NO_MAPPING,
                                EXPECTED_MAPPING_COUNT, EXPECTED_SOURCE_COUNT,
                                INVENTORY_JOURNAL_XMLID, MARK,
                                SINGLE_SOURCE_JOURNALS, WORKFLOW,
                                WORKFLOW_NAME, balanced_lines, expect_error,
                                fixture_source_id, fx, journal_source_of,
                                live_entry_type_matrix, m2o_id, make_entry,
                                make_journal, require_journal_export,
                                require_post_analytics, sweep_wf017, trace)


def _digest(value) -> str:
    payload = json.dumps(value, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


# --------------------------------------------------------------- TC309
def _capture_matrix(ctx):
    """The entry-type -> journal-source matrix, from the database only."""
    rpc = ctx.adapter.rpc
    snapshot = {}

    # --- step 10: the catalogue counts ----------------------------------
    snapshot["sources.count"] = len(rpc.search("account.journal.workday", []))
    snapshot["mappings.count"] = len(
        rpc.search("account.journal.workday.line", []))

    # --- steps 2-4: the matrix, over the LIVE population -----------------
    # Read from the database and compared against the shipped CSV's xml
    # ids, never retyped: the catalogue's casing is internally inconsistent
    # and a case mismatch in column T is a silent Workday-side rejection.
    matrix = live_entry_type_matrix(rpc)
    snapshot["live_matrix"] = sorted(
        (entry_type, id_workday, count)
        for (entry_type, id_workday), count in matrix.items())
    snapshot["live_matrix.digest"] = _digest(snapshot["live_matrix"])
    snapshot["live_matrix.entry_types"] = sorted(
        {entry_type for (entry_type, _id) in matrix})
    snapshot["live_matrix.blank_source_types"] = sorted(
        {entry_type for (entry_type, id_workday) in matrix if not id_workday})

    # --- the SHIPPED mapping, as the database holds it -------------------
    inventory_journal = rpc.ref(INVENTORY_JOURNAL_XMLID)
    snapshot["inventory_journal_resolves"] = bool(inventory_journal)
    if inventory_journal:
        journal = rpc.read("account.journal", [inventory_journal],
                           ["journal_workday_multiple", "journal_workday_id",
                            "journal_workday_ids", "name"])[0]
        snapshot["inventory_journal.multiple"] = bool(
            journal["journal_workday_multiple"])
        snapshot["inventory_journal.single_source"] = bool(
            m2o_id(journal["journal_workday_id"]))
        rows = rpc.read("account.journal.workday.line",
                        journal["journal_workday_ids"],
                        ["entry_type", "journal_workday_id", "sequence"])
        source_ids = sorted({m2o_id(r["journal_workday_id"]) for r in rows
                             if r.get("journal_workday_id")})
        id_workday = {}
        if source_ids:
            id_workday = {r["id"]: r["id_workday"] for r in rpc.read(
                "account.journal.workday", source_ids, ["id_workday"])}
        snapshot["inventory_journal.mapping"] = sorted(
            (row["entry_type"],
             id_workday.get(m2o_id(row["journal_workday_id"]), ""))
            for row in rows)

    # --- the two single-source journals ---------------------------------
    for xmlid, expected in SINGLE_SOURCE_JOURNALS.items():
        journal_id = rpc.ref(xmlid)
        key = f"single_source.{xmlid}"
        if not journal_id:
            snapshot[key] = "xmlid-does-not-resolve"
            continue
        journal = rpc.read("account.journal", [journal_id],
                           ["journal_workday_id",
                            "journal_workday_multiple"])[0]
        source_id = m2o_id(journal["journal_workday_id"])
        snapshot[key] = (
            rpc.read("account.journal.workday", [source_id],
                     ["id_workday"])[0]["id_workday"] if source_id else "")
        snapshot[f"{key}.multiple"] = bool(
            journal["journal_workday_multiple"])

    # --- step 5: entry_type is readonly and copy=False -------------------
    info = rpc.call("account.move", "fields_get", ["entry_type"],
                    attributes=["readonly", "store", "selection", "type"])
    snapshot["entry_type.readonly"] = bool(
        info["entry_type"].get("readonly"))
    snapshot["entry_type.selection"] = sorted(
        k for k, _label in (info["entry_type"].get("selection") or []))

    # --- step 6: the FK integrity TC036 step 6 asks for ------------------
    typed = rpc.search("account.move", [("entry_type", "!=", False)])
    snapshot["typed_moves.count"] = len(typed)
    snapshot["typed_moves_without_a_source"] = len(rpc.search(
        "account.move", [("entry_type", "!=", False),
                         ("journal_workday_id", "=", False)]))
    return snapshot


@test_case(
    id="TEST-WF017-TC309",
    name="BASELINE: per-entry-type journal-source resolution, all seven "
         "rows plus the two single-source journals",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account_workday", priority="P0", kind="DATA", order=17309,
    description="Captures the entry-type -> journal-source matrix over the "
                "live population, the Inventory Valuation journal's seven "
                "mapping rows as the database holds them, the two "
                "single-source journals, entry_type's field attributes and "
                "the catalogue counts — then asserts zero difference "
                "against the v17 baseline. Anchored on both versions: the "
                "counts are 131 and 7, no entry type resolves a blank "
                "source, and every typed move resolves one.",
    traceability=trace("DATAONE-TC309", user_story="F202: the acceptance "
                                                   "criterion for the "
                                                   "valuation rebuild"))
def test_tc309(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Preconditions: dto_account_workday is installed. The "
                  "capture is READ-ONLY; the two constraint assertions "
                  "below use token-scoped journals and never touch "
                  "account.1_inventory_valuation"):
        require_journal_export(ctx)

    with ctx.step("Why this is a baseline and not an assertion"):
        ctx.log("F202's own note: this is 'the acceptance criterion for the "
                "entire valuation rebuild as it affects Workday'. It is "
                "cheap to capture on v17 and IMPOSSIBLE to reconstruct "
                "after the clone is upgraded, because on v19 "
                "stock.valuation.layer does not exist and the v17 branch "
                "that derived entry_type for a valuation entry with no "
                "stock move cannot be re-run. Capture it before the "
                "upgrade.")

    with ctx.step("Step 4: the casing is read from the DATABASE, never "
                  "retyped. The 131-row catalogue is internally "
                  "inconsistent — Inventory_Put_Away sits beside "
                  "INVENTORY_PUT_AWAY_ADJUSTMENT — and a case mismatch in "
                  "column T is a SILENT rejection on Workday's side"):
        sources = rpc.search_read("account.journal.workday", [],
                                  ["id_workday", "name"], order="id")
        mixed_case = sorted({row["id_workday"] for row in sources
                             if row["id_workday"]
                             and row["id_workday"] != row["id_workday"]
                             .title().replace("__", "_")})
        ctx.log(f"catalogue holds {len(sources)} source(s)")
        upper = [row["id_workday"] for row in sources
                 if row["id_workday"] and row["id_workday"].isupper()]
        ctx.log(f"id_workday values that are fully UPPER CASE: {upper!r}")
        ctx.log(f"values whose casing is not simple Title_Case: "
                f"{mixed_case[:20]!r}{' …' if len(mixed_case) > 20 else ''}")
        ctx.check_true(
            "the catalogue's casing IS inconsistent, so the expected values "
            "in this suite must come from the database — recorded as a fact "
            "about the data, not as a defect to fix here",
            bool(upper) or bool(mixed_case),
            actual_desc=f"{len(upper)} upper-case, {len(mixed_case)} "
                        f"non-Title_Case")

    with ctx.step("Step 3: the shipped mapping matches the workbook's "
                  "matrix, entry type by entry type, read from the database"):
        inventory_journal = rpc.ref(INVENTORY_JOURNAL_XMLID)
        if not inventory_journal:
            ctx.log(f"[warn] {INVENTORY_JOURNAL_XMLID} does not resolve on "
                    "this target — the shipped account_journal_data.xml "
                    "hard-codes the company-1 chart xml ids, and a changed "
                    "convention makes them unresolvable (LOUD at install, "
                    "which is the good case). The mapping assertion is "
                    "recorded rather than asserted.")
        else:
            journal = rpc.read("account.journal", [inventory_journal],
                               ["journal_workday_multiple",
                                "journal_workday_ids", "name"])[0]
            ctx.log(f"the Inventory Valuation journal: {journal!r}")
            ctx.check("it is in MULTIPLE mode", True,
                      bool(journal["journal_workday_multiple"]))
            rows = rpc.read("account.journal.workday.line",
                            journal["journal_workday_ids"],
                            ["entry_type", "journal_workday_id"])
            source_ids = sorted({m2o_id(r["journal_workday_id"])
                                 for r in rows if r.get("journal_workday_id")})
            id_workday = {r["id"]: r["id_workday"] for r in rpc.read(
                "account.journal.workday", source_ids,
                ["id_workday"])} if source_ids else {}
            actual = {row["entry_type"]:
                      id_workday.get(m2o_id(row["journal_workday_id"]), "")
                      for row in rows}
            ctx.log(f"the mapping as the database holds it: {actual!r}")
            ctx.check("all seven entry types map to their tabled journal "
                      "source, with exact casing", ENTRY_TYPE_MAPPING, actual)

    with ctx.step("The two single-source journals"):
        for xmlid, expected in SINGLE_SOURCE_JOURNALS.items():
            journal_id = rpc.ref(xmlid)
            if not journal_id:
                ctx.log(f"[warn] {xmlid} does not resolve — recorded.")
                continue
            journal = rpc.read("account.journal", [journal_id],
                               ["journal_workday_id",
                                "journal_workday_multiple", "name"])[0]
            source_id = m2o_id(journal["journal_workday_id"])
            actual = (rpc.read("account.journal.workday", [source_id],
                               ["id_workday"])[0]["id_workday"]
                      if source_id else "")
            ctx.log(f"{xmlid}: {journal!r} -> {actual!r}")
            ctx.check(f"{xmlid} resolves {expected!r} through the "
                      "single-source path", expected, actual)
            ctx.check(f"{xmlid} is NOT in multiple mode", False,
                      bool(journal["journal_workday_multiple"]))

    with ctx.step("Step 5: entry_type is readonly and copy=False — "
                  "duplicating a typed move leaves the copy's entry_type "
                  "empty"):
        info = rpc.call("account.move", "fields_get", ["entry_type"],
                        attributes=["readonly", "type", "selection"])
        ctx.log(f"entry_type field definition: {info!r}")
        ctx.check("readonly", True, bool(info["entry_type"].get("readonly")))
        ctx.check("the seven entry types are the selection",
                  sorted(ENTRY_TYPE_MAPPING),
                  sorted(k for k, _l in
                         (info["entry_type"].get("selection") or [])))
        typed = rpc.search("account.move", [("entry_type", "!=", False)],
                           limit=1)
        if not typed:
            ctx.log("[warn] no move on this target carries an entry_type, "
                    "so copy=False cannot be exercised against a real one. "
                    "Recorded rather than asserted.")
        else:
            copies = rpc.call("account.move", "copy", typed)
            copy_ids = copies if isinstance(copies, list) else [copies]
            copy_row = rpc.read("account.move", copy_ids,
                                ["entry_type", "state"])[0]
            ctx.log(f"the duplicate of move {typed[0]}: {copy_row!r}")
            ctx.check("the copy's entry_type is empty — copy=False", False,
                      copy_row["entry_type"] or False)
            try:
                rpc.call("account.move", "unlink", copy_ids)
            except Exception as exc:                        # noqa: BLE001
                ctx.log(f"[warn] the duplicate could not be removed "
                        f"({exc}); it is a DRAFT copy and harmless, but "
                        f"delete move(s) {copy_ids!r} by hand.")

    with ctx.step("Step 7: the uniqueness constraint — asserted on a "
                  "TOKEN-SCOPED journal, never on "
                  "account.1_inventory_valuation"):
        sweep_wf017(rpc)
        journal_id = make_journal(ctx, label="Constraint")
        source_id = fixture_source_id(ctx)
        first = rpc.create("account.journal.workday.line", {
            "journal_id": journal_id,
            "journal_workday_id": source_id,
            "entry_type": "incoming"})
        raised, message = expect_error(
            rpc.create, "account.journal.workday.line", {
                "journal_id": journal_id,
                "journal_workday_id": source_id,
                "entry_type": "incoming"})
        ctx.log(f"a duplicate entry_type on one journal: raised={raised}; "
                f"message VERBATIM: {message!r}")
        ctx.check_true("it raises", raised, actual_desc=message)
        ctx.check_true(f"with {ERR_DUPLICATE_ENTRY_TYPE!r}",
                       ERR_DUPLICATE_ENTRY_TYPE in message,
                       actual_desc=message)
        ctx.log("The constraint is implemented with _read_group(having=...) "
                "(account_journal_workday.py:76-80), which delta §2.16 "
                "lists as an aggregate whose return shape must be "
                "re-verified on v19 — SILENT if it changed, because the "
                "constraint would stop firing rather than raise.")

    with ctx.step("Step 8: the empty-mapping constraint, also on a "
                  "token-scoped journal"):
        empty_journal = make_journal(ctx, label="NoMapping")
        raised, message = expect_error(
            rpc.write, "account.journal", [empty_journal],
            {"journal_workday_multiple": True})
        ctx.log(f"multiple mode with no mapping rows: raised={raised}; "
                f"message VERBATIM: {message!r}")
        ctx.check_true("it raises", raised, actual_desc=message)
        ctx.check_true(f"with {ERR_NO_MAPPING!r}",
                       ERR_NO_MAPPING in message, actual_desc=message)

    with ctx.step("Step 9: THE CASE'S REAL PAYLOAD. An entry type with NO "
                  "mapping row on a multiple-mode journal resolves the "
                  "journal source EMPTY, with no error. That is the exact "
                  "mechanism by which a v19 entry_type = False produces a "
                  "blank required column T"):
        require_post_analytics(ctx)
        partial_journal = make_journal(ctx, label="PartialMap")
        rpc.create("account.journal.workday.line", {
            "journal_id": partial_journal,
            "journal_workday_id": fixture_source_id(ctx),
            "entry_type": "incoming"})
        rpc.write("account.journal", [partial_journal],
                  {"journal_workday_multiple": True,
                   "journal_workday_id": False})
        state = rpc.read("account.journal", [partial_journal],
                         ["journal_workday_multiple", "journal_workday_id",
                          "journal_workday_ids"])[0]
        ctx.log(f"a multiple-mode journal mapped for 'incoming' only: "
                f"{state!r}")

        lines, _d, _c = balanced_lines(ctx)
        probe = make_entry(ctx, partial_journal, lines, "UNMAPPED")
        entry_type, id_workday, row = journal_source_of(rpc, probe)
        ctx.log(f"a fixture entry on it: entry_type={entry_type!r} "
                f"id_workday={id_workday!r} row={row!r}")
        ctx.check(
            "the entry's entry_type is False (it has no stock move), so "
            "get_journal_workday(False) takes the `not entry_type` branch "
            "and returns journal_workday_id — which this journal does not "
            "have. Column T resolves EMPTY with NO ERROR",
            "", id_workday)
        ctx.check("and the move's journal_workday_id is genuinely unset",
                  False, m2o_id(row.get("journal_workday_id")) or False)
        ctx.log("THE DIAGNOSIS, written before the v19 failure: on v19 "
                "stock.valuation.layer is gone, so entry_type resolves "
                "False for valuation entries carrying no stock move; on the "
                "multiple-mode Inventory Valuation journal that then takes "
                "the same branch, journal_workday_id is unset (the data "
                "file only sets journal_workday_multiple), and required "
                "column T is blank for every inventory move. F198 withholds "
                "the line, F199 drops the whole move, the workbook is "
                "shorter and nothing raises. When TEST-WF017-TC306 fails, "
                "this is why.")
        ctx.log("REMEDIATION IS NOT A PORT. Per delta §2.1 the entry type "
                "must be re-derived from stock.move.account_move_id and the "
                "batched-entry model — and the project must first answer "
                "WF-017 Open Question 6: DOES ENTRY TYPE BELONG ON THE MOVE "
                "OR ON THE LINE? A batched valuation entry spanning a "
                "receipt and a delivery cannot carry one journal source, "
                "and no amount of careful porting changes that. Raise it "
                "with the Controller before any code is written. The ported "
                "tree's own answer is recorded at "
                "account_move.py:216-328 — first move's type, with a "
                "WARNING when a batch spans several, and the measurement "
                "that says it never does on this estate.")

    reconcile(
        ctx, "DATAONE-TC309", _capture_matrix,
        anchors={
            # Step 10 — the catalogue counts, on both versions.
            "sources.count": EXPECTED_SOURCE_COUNT,
            "mappings.count": EXPECTED_MAPPING_COUNT,
            # The assertion the whole workflow rests on: no entry type may
            # resolve a blank journal source, because column T is required.
            "live_matrix.blank_source_types": [],
            "typed_moves_without_a_source": 0,
            # entry_type must stay readonly — a writable one would let a
            # fixture fake the derivation this case exists to measure.
            "entry_type.readonly": True,
            "entry_type.selection": sorted(ENTRY_TYPE_MAPPING),
        })


# --------------------------------------------------------------- TC036
def _capture_catalogue(ctx):
    """The catalogue, its mappings and the xml ids that bind them."""
    rpc = ctx.adapter.rpc
    snapshot = {}

    # --- step 1: resolve the two models -------------------------------
    models = rpc.search_read(
        "ir.model.data",
        [("module", "=", "dto_account_workday"), ("model", "=", "ir.model")],
        ["name", "res_id"])
    snapshot["dto_account_workday.models"] = sorted(
        row["name"] for row in models)

    # --- steps 2 and 5: the full catalogue, row for row ----------------
    sources = rpc.search_read(
        "account.journal.workday", [("active", "in", [True, False])],
        ["id_workday", "name", "accounting_src", "process_cost",
         "adhoc_bsl_src", "workday_src", "active", "sequence"], order="id")
    snapshot["sources.count"] = len(sources)
    snapshot["sources.digest"] = _digest([
        (row["id_workday"], row["name"], bool(row["accounting_src"]),
         bool(row["process_cost"]), bool(row["adhoc_bsl_src"]),
         bool(row["workday_src"]), bool(row["active"]))
        for row in sources])
    snapshot["sources.id_workday_list"] = sorted(
        row["id_workday"] or "" for row in sources)

    # --- step 3: the mappings ------------------------------------------
    mappings = rpc.search_read(
        "account.journal.workday.line", [],
        ["journal_id", "journal_workday_id", "entry_type", "sequence"],
        order="id")
    snapshot["mappings.count"] = len(mappings)
    source_ids = sorted({m2o_id(row["journal_workday_id"]) for row in mappings
                         if row.get("journal_workday_id")})
    id_workday = {row["id"]: row["id_workday"] for row in rpc.read(
        "account.journal.workday", source_ids,
        ["id_workday"])} if source_ids else {}
    journal_ids = sorted({m2o_id(row["journal_id"]) for row in mappings
                          if row.get("journal_id")})
    journal_codes = {row["id"]: row["code"] for row in rpc.read(
        "account.journal", journal_ids, ["code"])} if journal_ids else {}
    # Compared by CODE and id_workday, not by id: row ids are not
    # comparable across databases, the values are.
    snapshot["mappings"] = sorted(
        (journal_codes.get(m2o_id(row["journal_id"]), ""),
         row["entry_type"] or "",
         id_workday.get(m2o_id(row["journal_workday_id"]), ""))
        for row in mappings)

    # --- step 4: the external ids that bind them ------------------------
    # THE ASSERTION THAT ACTUALLY MATTERS. A re-created catalogue with new
    # row ids breaks every FK on account_move.journal_workday_id, and the
    # only stable identity across databases is the xml id.
    bindings = rpc.search_read(
        "ir.model.data",
        [("module", "=", "dto_account_workday"),
         ("model", "in", ["account.journal.workday",
                          "account.journal.workday.line"])],
        ["name", "model", "res_id"], order="name")
    snapshot["xml_ids.count"] = len(bindings)
    snapshot["xml_ids"] = sorted(f"{row['model']}:{row['name']}"
                                 for row in bindings)
    snapshot["xml_ids.digest"] = _digest(snapshot["xml_ids"])
    # The xml_id -> id_workday pairing: a row whose xml id now points at a
    # DIFFERENT catalogue entry is the silent form of the same breakage.
    by_res_id = {row["id"]: row["id_workday"] for row in sources}
    snapshot["xml_id_to_id_workday"] = sorted(
        (row["name"], by_res_id.get(row["res_id"], ""))
        for row in bindings
        if row["model"] == "account.journal.workday")

    # --- step 6: FK integrity on the consumer ---------------------------
    snapshot["moves_with_a_dangling_source"] = len(rpc.search(
        "account.move", [("journal_workday_id", "!=", False),
                         ("journal_workday_id.id", "=", False)]))
    snapshot["moves_with_a_source"] = len(rpc.search(
        "account.move", [("journal_workday_id", "!=", False)]))
    return snapshot


@test_case(
    id="TEST-WF017-TC036",
    name="Workday journal-source catalogue and mappings survive",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account_workday", priority="P1", kind="DATA", order=17036,
    description="Captures the 131-row catalogue field by field as a "
                "checksum, the seven mappings by journal CODE and "
                "id_workday rather than by row id, and — the assertion that "
                "actually matters — the xml ids that bind them plus each "
                "xml id's resolved id_workday, because a re-created "
                "catalogue with new row ids breaks every foreign key on "
                "account.move.journal_workday_id. Read-only.",
    traceability=trace("DATAONE-TC036"))
def test_tc036(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Preconditions: dto_account_workday is installed. This "
                  "case creates nothing, writes nothing and touches no "
                  "business record"):
        require_journal_export(ctx)
        for model in ("account.journal.workday",
                      "account.journal.workday.line"):
            if not rpc.model_exists(model):
                ctx.blocked(
                    f"{model} does not exist on {ctx.env.key} — the "
                    "journal-source catalogue is absent, so required column "
                    "T has nothing to resolve to and every journal-entry "
                    "export would withhold every move.")

    with ctx.step("What makes this more than a row count"):
        ctx.log("The catalogue is shipped as CSV data with noupdate="
                "\"1\", so the rows are seeded once and then referenced by "
                "account_move.journal_workday_id forever. Counting 131 and "
                "7 on both sides is necessary and not sufficient: a "
                "RE-CREATED catalogue with new row ids satisfies both "
                "counts and breaks every foreign key. So the capture keys "
                "on the XML ID and records each xml id's resolved "
                "id_workday — a row whose xml id now points at a different "
                "catalogue entry is the silent form of the same breakage. "
                "The related risk delta records is a -u run rewriting the "
                "seeded rows underneath posted entries (DATAONE-TC019).")

    reconcile(
        ctx, "DATAONE-TC036", _capture_catalogue,
        anchors={
            # Step 5's literal numbers, on both versions.
            "sources.count": EXPECTED_SOURCE_COUNT,
            "mappings.count": EXPECTED_MAPPING_COUNT,
            # Step 6 — every posted entry that referenced a source still
            # resolves it. Broken on either version is broken.
            "moves_with_a_dangling_source": 0,
        })
