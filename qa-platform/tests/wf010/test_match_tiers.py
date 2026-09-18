"""DATAONE-WF-010 — the three-tier match: TC345 and TC346.

The transformer tries three searches in order and takes the first hit
(``mrp_attachment_transformer.py:20-61``):

1. ``stock.lot.custom`` where ``name == serial`` exactly, and take its
   ``production_id``;
2. ``mrp.production`` where a producing lot is named exactly ``serial``;
3. ``mrp.production`` where a producing lot is named
   ``serial[:serial.rfind('-')]`` — the prefix retry.

Every tier also matches on ``product_id.default_code`` (BR-4), and that
clause is load-bearing: without it the ``limit=1`` searches would hand back
an arbitrary MO.

TC345 is a DECISION-GATE case dressed as a functional one. Tier 1 matches
against ``stock.lot.custom``, a ``dto_mrp`` custom model that
``04-manufacturing.md`` lists in its dead-code table with a REMOVE
recommendation. Steps 9-11 are the point: if the model is empty in
production, tier 1 is dead code and the v19 match becomes two tiers
instead of three — a real simplification in a module that has to be rebased
on ``lot_producing_ids`` anyway. If it is populated, the REMOVE
recommendation is wrong and must be corrected. ``dto_mrp_sftp``'s own test
header already records the counter-evidence (319 rows on both databases,
all carrying a ``production_id``); this case re-takes the count on the
target under test, read-only, so the decision rests on the environment
rather than on a note.

TC346 is tier 2, the tier v19 breaks most directly — and the break is a
SEMANTIC change, not a rename. ``lot_producing_id`` (M2o) became
``lot_producing_ids`` (M2m), so ``lot_producing_ids.name = X`` matches an MO
where ANY producing lot is named X, where v17 matched the single one. Step
12 constructs exactly that: one MO producing three serials, three files,
and the recorded answer to whether all three attaching to one MO is the
intended semantics. That is a conversation with the Production Manager and
the quality function, not a porting decision, and it should happen before
``dto_mrp_sftp`` is touched.

Why these are implemented here rather than left to the module's own tests
------------------------------------------------------------------------
``dto_mrp_sftp/tests/test_wf010_parse_and_match.py`` re-implements the
three tiers as a local ``_transform`` helper and asserts against that. So
it proves the three SEARCHES behave, not that the product's transformer
runs them in that order against real records and hands the result to the
loader. These cases drive the real ETL and assert which MO the
``ir.attachment`` ended up on — the only observation that distinguishes a
correct tier order from a plausible one.

EXPECTED v17 OUTCOME: PASS for both, with TC345's usage count recorded.
EXPECTED v19 OUTCOME: PASS. TC345 reports BLOCKED with a precise reason if
``stock.lot.custom`` has been removed — and that BLOCK is the finding, not
a gap: matching has silently degraded to two tiers and files that used to
attach now fail with "no match", which looks like a data problem rather
than a code change.
"""
from framework.registry import test_case
from tests.wf010.common import (ERR_NO_MATCH_HEADING, MARK,  # noqa: F401
                                PART_FIELD, SERIAL_FIELD, WORKFLOW,
                                WORKFLOW_NAME, attachments_on_mo,
                                could_match, file_message, fx, lot_name,
                                m2o_id, make_custom_lot, make_folder,
                                make_lot, make_mo, make_product, make_server,
                                mo_with_lot, part_code, process_file,
                                producing_lot_field, require_custom_lot,
                                require_mrp_attachment, run_import,
                                sample_file, serial_for, set_producing_lot,
                                sweep_wf010, trace)


@test_case(
    id="TEST-WF010-TC345",
    name="Tier 1: matched via stock.lot.custom",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_mrp_sftp", priority="P1", kind="API", order=10345,
    description="Proves tier 1 matches on the FULL serial through "
                "stock.lot.custom's production_id, that the part-number "
                "clause is load-bearing in this tier too, that both records "
                "are stamped, and that tier 1 takes precedence over tier 2 "
                "once a tier-2 candidate also exists. Then re-takes the "
                "live usage count that decides whether the tier is dead "
                "code — read-only.",
    traceability=trace("DATAONE-TC345", user_story="decides WF-010 Open "
                                                   "Question 1"))
def test_tc345(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-010 fixtures and open a fresh "
                  "namespace"):
        sweep_wf010(rpc)

    with ctx.step("Preconditions: the attachment stack, and stock.lot.custom "
                  "must exist — its absence IS the finding, not a skip"):
        require_mrp_attachment(ctx)
        require_custom_lot(ctx)

    with ctx.step("Step 9 (taken first, because it is read-only and decides "
                  "whether the rest of the case matters): the live usage "
                  "count for stock.lot.custom on THIS target"):
        total = len(rpc.search("stock.lot.custom", []))
        with_production = len(rpc.search("stock.lot.custom",
                                         [("production_id", "!=", False)]))
        ctx.log(f"stock.lot.custom on {ctx.env.key} (db={ctx.env.db}): "
                f"{total} row(s), {with_production} carrying a "
                f"production_id")
        ctx.check_true(
            "the model is POPULATED, so 04-manufacturing.md's REMOVE "
            "recommendation would delete a live matching tier. If this "
            "assertion fails, tier 1 has never fired on this database and "
            "the REMOVE recommendation is evidenced instead — either way "
            "the count is the answer to Open Question 1",
            total > 0,
            actual_desc=f"{total} rows, {with_production} with a production")

    with ctx.step("Step 1: MO-T1 reachable ONLY by tier 1 — a "
                  "stock.lot.custom row on the FULL serial, and no MO whose "
                  "producing lot is either the serial or its prefix"):
        part = part_code()
        prefix = lot_name()
        serial = serial_for("037/042", lot=prefix)
        product_id = make_product(ctx, part)
        mo_t1 = make_mo(ctx, product_id)
        custom_id = make_custom_lot(rpc, product_id, serial, mo_t1)
        ctx.log(f"part={part!r} serial={serial!r}; MO-T1={mo_t1}, "
                f"stock.lot.custom={custom_id}")

        reachable = could_match(ctx, part, serial)
        ctx.log(f"what each tier could reach: {reachable!r}")
        ctx.check("tier 1 reaches exactly MO-T1", [mo_t1],
                  reachable["tier1"])
        ctx.check("tier 2 reaches nothing", [], reachable["tier2"])
        ctx.check("tier 3 reaches nothing either — so a match can ONLY have "
                  "come from tier 1", [], reachable["tier3"])

    with ctx.step("Steps 2-5: process the file; the attachment lands on "
                  "MO-T1, matched on the FULL serial with no truncation"):
        folder_id, file_id, file_row = run_import(
            ctx, sample_file(part, serial), file_label="tier1")
        ctx.log(f"sftp.file: {file_row!r}")
        ctx.check("the file is Done", "done", file_row["state"])
        ctx.check("it landed on MO-T1", mo_t1, file_row["res_id"])
        ctx.check("res_model", "mrp.production", file_row["res_model"])
        ctx.check(f"{SERIAL_FIELD} is the FULL serial — tier 1 matches "
                  "name == serial_number exactly, with no truncation",
                  serial, file_row[SERIAL_FIELD])
        ctx.check_true(
            "and the recorded serial is not the prefix, so the match cannot "
            "have come from tier 3",
            file_row[SERIAL_FIELD] != prefix,
            actual_desc=f"{file_row[SERIAL_FIELD]!r} vs {prefix!r}")

    with ctx.step("Step 6: the part-number clause is load-bearing in this "
                  "tier too (BR-4) — the same custom lot under a DIFFERENT "
                  "part matches nothing"):
        other_part = part_code("-OTHER")
        ctx.log(f"probing tier 1 with part={other_part!r}: "
                f"{could_match(ctx, other_part, serial)!r}")
        ctx.check("tier 1 reaches nothing when the part number differs",
                  [], could_match(ctx, other_part, serial)["tier1"])

    with ctx.step("Step 7: both the sftp.file and the ir.attachment are "
                  "stamped with MO-T1"):
        attachment_id = m2o_id(file_row["attachment_id"])
        attachment = rpc.read("ir.attachment", [attachment_id],
                              ["res_model", "res_id"])[0]
        ctx.log(f"attachment stamp: {attachment!r}")
        ctx.check("attachment res_model/res_id",
                  ("mrp.production", mo_t1),
                  (attachment["res_model"], attachment["res_id"]))
        ctx.check("MO-T1 carries exactly one attachment", 1,
                  len(attachments_on_mo(rpc, mo_t1)))

    with ctx.step("Step 8: TIER PRECEDENCE. Add an MO whose producing lot "
                  "IS the full serial — which would satisfy tier 2 — and "
                  "assert tier 1 still wins: first hit wins, in order"):
        mo_t2, lot_id = mo_with_lot(ctx, product_id, serial)
        reachable = could_match(ctx, part, serial)
        ctx.log(f"now reachable: {reachable!r}")
        ctx.check("tier 2 now reaches MO-T2", [mo_t2], reachable["tier2"])
        ctx.check("and tier 1 still reaches MO-T1", [mo_t1],
                  reachable["tier1"])
        _f, second_id, second_row = run_import(
            ctx, sample_file(part, serial), folder_id=folder_id,
            file_label="tier1_precedence")
        ctx.log(f"second sftp.file: {second_row!r}")
        ctx.check("tier 1 wins — the second file also landed on MO-T1, not "
                  "MO-T2", mo_t1, second_row["res_id"])
        ctx.check("MO-T2 received nothing", [],
                  attachments_on_mo(rpc, mo_t2))

    with ctx.step("Steps 10-11: record the finding for WF-010 Open Question "
                  "1 and the LEG suite's descoping decision"):
        matched_via_tier1 = None
        if rpc.field_exists("sftp.file", "usage"):
            historical = rpc.search_read(
                "sftp.file",
                [("usage", "=", "mrp_attachment"),
                 ("state", "=", "done"),
                 ("res_model", "=", "mrp.production"),
                 ("folder_id.path", "not like", f"/{MARK}/%")],
                ["name", SERIAL_FIELD, "res_id"], limit=50)
            matched_via_tier1 = len(historical)
            ctx.log(f"historical Done mrp_attachment files on this target "
                    f"(excluding this suite's own): {matched_via_tier1} "
                    f"(sampled up to 50)")
        ctx.log("FINDING, for WF-010 Open Question 1 and "
                "04-manufacturing.md's dead-code table: stock.lot.custom "
                f"holds {total} row(s) on {ctx.env.key}, {with_production} "
                "with a production_id. dto_mrp_sftp's own test header "
                "records 319 / 319 on both dataone and dataone_19. Tier 1 "
                "is therefore LIVE and the REMOVE recommendation is wrong; "
                "removing it would degrade matching to lot_producing_ids "
                "only, and the symptom would be files that used to attach "
                "failing with 'no match' — which reads as a data problem, "
                "not a code change.")
        ctx.log("Note the measured context that makes this decision less "
                "comfortable than it looks: the same test header records "
                "118,177 FAILED against 56 Done on v17, last success 5 Dec "
                "2025. Tier 1 being live does not mean the workflow works.")


@test_case(
    id="TEST-WF010-TC346",
    name="Tier 2: matched via lot_producing_id exactly",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_mrp_sftp", priority="P1", kind="API", order=10346,
    description="Proves tier 2 matches on the exact full serial through the "
                "MO's producing lot and takes precedence over tier 3's "
                "prefix retry, that tier 3 is reached only when tier 2 "
                "finds nothing AND the serial contains a hyphen, that the "
                "retry strips EXACTLY ONE trailing segment, and — the v19 "
                "design question — that an MO producing three serials "
                "collects all three test files under the Many2many "
                "semantics.",
    traceability=trace("DATAONE-TC346", user_story="raises WF-010 open "
                                                   "question 5"))
def test_tc346(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-010 fixtures and open a fresh "
                  "namespace"):
        sweep_wf010(rpc)

    with ctx.step("Preconditions: the attachment stack"):
        require_mrp_attachment(ctx)
        lot_field = producing_lot_field(rpc)
        ctx.log(f"producing-lot field on this target: {lot_field!r}")

    with ctx.step("Steps 1-2: MO-T2 producing the FULL serial and MO-T3 "
                  "producing only its PREFIX — distinct, so tier precedence "
                  "is testable — and no stock.lot.custom row at all"):
        part = part_code()
        prefix = lot_name()
        serial = serial_for("037/042", lot=prefix)
        product_id = make_product(ctx, part)
        mo_t2, lot_full = mo_with_lot(ctx, product_id, serial)
        mo_t3, lot_prefix = mo_with_lot(ctx, product_id, prefix)
        ctx.log(f"part={part!r} serial={serial!r} prefix={prefix!r}")
        ctx.log(f"MO-T2={mo_t2} (lot {lot_full}, the full serial); "
                f"MO-T3={mo_t3} (lot {lot_prefix}, the prefix)")
        ctx.check_true("the two MOs are distinct", mo_t2 != mo_t3,
                       actual_desc=f"{mo_t2} vs {mo_t3}")
        reachable = could_match(ctx, part, serial)
        ctx.log(f"what each tier could reach: {reachable!r}")
        ctx.check("tier 1 reaches nothing — no stock.lot.custom row exists",
                  [], reachable["tier1"])
        ctx.check("tier 2 reaches exactly MO-T2", [mo_t2],
                  reachable["tier2"])
        ctx.check("tier 3 reaches exactly MO-T3, so precedence is "
                  "observable", [mo_t3], reachable["tier3"])

    with ctx.step("Steps 3-7: the attachment lands on MO-T2 and NOT on "
                  "MO-T3 — tier 2 fires first, so the prefix retry never "
                  "runs. Both records are stamped"):
        folder_id, file_id, file_row = run_import(
            ctx, sample_file(part, serial), file_label="tier2")
        ctx.log(f"sftp.file: {file_row!r}")
        ctx.check("the file is Done", "done", file_row["state"])
        ctx.check("it landed on MO-T2", mo_t2, file_row["res_id"])
        ctx.check("MO-T3 received nothing", [],
                  attachments_on_mo(rpc, mo_t3))
        ctx.check(f"{PART_FIELD}", part, file_row[PART_FIELD])
        ctx.check(f"{SERIAL_FIELD} is the full serial", serial,
                  file_row[SERIAL_FIELD])
        attachment = rpc.read("ir.attachment",
                              [m2o_id(file_row["attachment_id"])],
                              ["res_model", "res_id"])[0]
        ctx.check("the attachment is stamped with MO-T2",
                  ("mrp.production", mo_t2),
                  (attachment["res_model"], attachment["res_id"]))

    with ctx.step("Step 8: tier 3 is reached only when tier 2 finds nothing "
                  "AND the serial contains a hyphen — a hyphen-free serial "
                  "that matches nothing produces the failure message, not "
                  "an attempted truncation"):
        # No hyphen anywhere: lot_name() joins with '.', and the suffix is
        # appended without one, so the transformer's `'-' in serial_number`
        # guard is false and tier 3 is skipped entirely.
        hyphenless = f"{prefix.replace('-', '.')}NOHYPHEN"
        probe = could_match(ctx, part, hyphenless)
        ctx.log(f"probing a hyphen-free serial {hyphenless!r}: {probe!r}")
        ctx.check("tier 3 is not even attempted — the transformer guards on "
                  "'-' in serial_number (transformer:56)",
                  None, probe["tier3_prefix"])
        _f, nh_id, nh_row = run_import(
            ctx, sample_file(part, hyphenless), folder_id=folder_id,
            file_label="no_hyphen")
        ctx.log(f"hyphen-free file: {nh_row!r}")
        ctx.check("the file Failed", "failed", nh_row["state"])
        message = file_message(rpc, nh_id)
        ctx.log(f"failure message, verbatim: {message!r}")
        ctx.check_true(f"with the no-match heading "
                       f"{ERR_NO_MATCH_HEADING!r}, not an extraction error",
                       ERR_NO_MATCH_HEADING in message, actual_desc=message)
        ctx.check(f"{SERIAL_FIELD} still recorded the serial verbatim, so "
                  "the failure is diagnosable", hyphenless,
                  nh_row[SERIAL_FIELD])

    with ctx.step("Step 9: the prefix-retry boundary (BR-5) — a serial with "
                  "TWO trailing segments has exactly ONE stripped"):
        two_segment = f"{prefix}-037-042"
        probe = could_match(ctx, part, two_segment)
        ctx.log(f"probing {two_segment!r}: {probe!r}")
        ctx.check("rfind('-') strips exactly one level, producing "
                  f"{prefix}-037 and NOT {prefix}",
                  f"{prefix}-037", probe["tier3_prefix"])
        ctx.check("which matches nothing — the MO producing the bare prefix "
                  "is NOT reached, so a two-segment serial scheme "
                  "half-works", [], probe["tier3"])
        _f, ts_id, ts_row = run_import(
            ctx, sample_file(part, two_segment), folder_id=folder_id,
            file_label="two_segment")
        ctx.log(f"two-segment file: {ts_row!r}")
        ctx.check("so the file Failed", "failed", ts_row["state"])

    with ctx.step("Step 10: the real-world question this boundary raises — "
                  "recorded, because only the Production Manager can answer "
                  "it"):
        ctx.log("BR-5 strips exactly one trailing segment at rfind('-'). "
                "Whether real serials ever carry TWO trailing segments is a "
                "question for the Production Manager, and it decides "
                "whether step 9's behaviour is a defect or a non-issue. "
                "Partial success is the worst kind: a two-segment scheme "
                "would attach SOME files and silently fail others, and the "
                "failures look like missing MOs. Ask before porting; the "
                "answer costs nothing and cannot be derived from the code.")

    with ctx.step("Step 11: on this target the tier-2 search uses "
                  f"{lot_field!r} — assert the tier still fires through "
                  "whichever shape exists"):
        ctx.check(
            "tier 2 matched through the target's own producing-lot field, "
            "so the domain is not still naming the v17 Many2one "
            "(which would raise, LOUD, and is the good case)",
            mo_t2, file_row["res_id"])
        ctx.log("mrp_attachment_transformer.py:49-53 searches "
                "('lot_producing_ids.name', '=', serial_number) in the "
                "ported tree. On v17 the same domain would name "
                "lot_producing_id. producing_lot_field() resolves whichever "
                "the target has, so this assertion is version-neutral by "
                "construction rather than by branching in the test body.")

    with ctx.step("Step 12: THE v19 DESIGN QUESTION. One MO producing THREE "
                  "serials, three files — do all three attach to that same "
                  "MO, and is that the intended semantics?"):
        if not lot_field.endswith("ids"):
            ctx.log("[warn] this target carries the v17 Many2one, so an MO "
                    "cannot produce more than one lot and step 12 is not "
                    "constructible. That IS the v17 answer: the mapping is "
                    "one file to one MO by construction. Recorded rather "
                    "than asserted; re-run this case on v19 to get the "
                    "other half.")
        else:
            multi_part = part_code("-MULTI")
            multi_product = make_product(ctx, multi_part,
                                         label="Multi-serial Assembly")
            mo_multi = make_mo(ctx, multi_product, qty=3.0)
            serials = [serial_for("001/003", lot=lot_name("a")),
                       serial_for("002/003", lot=lot_name("b")),
                       serial_for("003/003", lot=lot_name("c"))]
            lot_ids = [make_lot(rpc, multi_product, s) for s in serials]
            rpc.write("mrp.production", [mo_multi],
                      {lot_field: [(6, 0, lot_ids)]})
            written = rpc.read("mrp.production", [mo_multi],
                               [lot_field])[0][lot_field]
            ctx.log(f"MO {mo_multi} producing lots {written!r}")
            if len(written or []) < 3:
                ctx.log("[warn] the target refused more than "
                        f"{len(written or [])} producing lot(s) on this MO "
                        "— v19's _check_lot_producing_ids raises on a "
                        "lot-tracked MO with more than one "
                        "(mrp/models/mrp_production.py:990), which is "
                        "exactly the constraint that keeps the migrated "
                        "estate single-lot. The semantics question survives "
                        "for SERIAL-tracked MOs, which v19 does NOT "
                        "constrain. Recorded rather than asserted.")
            else:
                landed = []
                for index, one in enumerate(serials, start=1):
                    _f, _id, one_row = run_import(
                        ctx, sample_file(multi_part, one),
                        folder_id=folder_id, file_label=f"multi_{index}")
                    landed.append(one_row["res_id"])
                    ctx.log(f"file for {one!r} -> res_id {one_row['res_id']}")
                ctx.check(
                    "all three files attached to the SAME MO — "
                    "lot_producing_ids.name = X matches an MO where ANY "
                    "producing lot is named X, where v17 matched the single "
                    "one", [mo_multi] * 3, landed)
                ctx.check("and the MO now carries three attachments", 3,
                          len(attachments_on_mo(rpc, mo_multi)))
                ctx.log("WF-010 OPEN QUESTION 5, for the Production "
                        "Manager and the quality function, BEFORE "
                        "dto_mrp_sftp is touched: in v17 an MO produces one "
                        "lot and one test file describes one unit, so the "
                        "mapping is one-to-one. In v19 an MO can produce "
                        "many, so 'attach the evidence to the MO' becomes "
                        "ambiguous — arguably the evidence should attach to "
                        "the LOT, not the MO. That is a manufacturing "
                        "decision, not a rename, and this test records the "
                        "current answer rather than choosing one.")
