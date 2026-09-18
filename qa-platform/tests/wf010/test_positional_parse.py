"""DATAONE-WF-010 — the silent one: TC349.

P0 despite touching no money. Delta §2.13 calls the
``base_import._read_file`` rework "the single highest-value test to write
before upgrading", and this is where it bites hardest, because the parse is
POSITIONAL on a ragged, non-rectangular file — exactly the input class
where row-normalisation behaviour is most likely to differ::

    part_number   = rows[0][1]     # a 2-cell metadata row
    serial_number = rows[-1][0]    # a 4-cell measurement row

Three failure modes, none of which raise:

* **(a) padding** — if short rows are now padded to the widest,
  ``rows[0][1]`` may change meaning;
* **(b) a kept trailing blank row** — ``rows[-1][0]`` is ``''``, the file
  fails extraction, and every test file that ends with a newline stops
  attaching. Indistinguishable from the 118,177 failures already in the
  v17 data;
* **(c) a shifted last row** — the quality evidence attaches to the
  **WRONG manufacturing order**, and nothing is raised, nothing is logged,
  and the MO shows an attachment that belongs to a different unit.

For a manufacturer whose customers audit test evidence, (c) is a
traceability failure of the most serious kind. It is also the case that
best demonstrates why a crash-only smoke test is worthless here: on v19 the
module imports, the cron runs, the file downloads, the ETL completes, the
``sftp.file`` reads Done and an attachment appears under a manufacturing
order. **Every green light is on.** The only thing wrong is *which*
manufacturing order, and the only detector is a byte-for-byte comparison
against a baseline captured before the upgrade.

So this is implemented as a DATA_RECONCILIATION case: on v17 it runs three
file variants through the real ETL and persists the extracted tuple and the
resolved MO for each; on v19 it re-runs the identical variants and asserts
zero difference. The three variants are the workbook's own:

* **P1** — the canonical file, no trailing newline. Must attach to
  MO-CORRECT.
* **P2** — P1 plus one trailing empty line. Must STILL attach to
  MO-CORRECT.
* **P3** — P1 plus one extra measurement row carrying a DIFFERENT serial.
  Attaches to MO-WRONG on v17, because ``rows[-1]`` is literally the last
  row and the code has no notion of which measurement is authoritative.
  **That is correct current behaviour and it is the mechanism the v19 risk
  exploits**, so a CHANGE here is as significant as a break.

Everything captured is a VALUE, never an id: the extracted part and serial
verbatim, and which of the two fixtures ("correct" / "wrong" / "none") the
attachment landed on — so the v17 and v19 snapshots are comparable across
databases.

What is handed back to the module's own tests
---------------------------------------------
Step 9's ``len(rows[0])`` and step 10's ``n_rows`` / ``len(rows)`` need
``_read_file``'s return value, which Odoo will not dispatch over RPC
(``base_import.import._read_file`` is private). Those three numbers are
already pinned in-process by
``dto_mrp_sftp/tests/test_wf010_parse_and_match.py`` —
``test_parse_part_number_is_row0_cell1``,
``test_parse_serial_is_last_row_cell0``,
``test_parse_trailing_blank_line_does_not_empty_the_serial`` and
``test_parse_negative_ragged_rows_are_not_padded_to_equal_width``. This
case asserts the OBSERVABLE consequence of all four — what the two
diagnostic fields hold and which MO the evidence reached — which is the
half the in-process tests cannot see, because they re-implement the match
rather than running it.

Step 14's "repeat with two or three REAL client test files" is a Phase-0a
dependency on the client, not something a test can synthesise. WF-010 is
explicit that "without real files this feature cannot be validated at
all"; the docstring sample is a starting point, not a substitute. Recorded.

EXPECTED v17 OUTCOME: PASS — captures and persists the baseline.
EXPECTED v19 OUTCOME: PASS when all three variants are byte-identical;
BLOCKED when no v17 baseline has been captured yet. **Capture this on the
v17 clone before it is upgraded.** Once it is gone the correct answer is
unknowable and the only remaining validation is a manual audit of every
attachment.
"""
from framework.fg_common import reconcile
from framework.registry import test_case
from tests.wf010.common import (ERR_EXTRACT_PREFIX,  # noqa: F401
                                ERR_NO_MATCH_HEADING, MARK, PART_FIELD,
                                SERIAL_FIELD, WORKFLOW, WORKFLOW_NAME,
                                activities_on, attachments_on_mo,
                                could_match, file_message, lot_name, m2o_id,
                                make_folder, make_product, make_server,
                                mo_with_lot, part_code, producing_lot_field,
                                require_mrp_attachment, run_import,
                                sample_file, serial_for, sweep_wf010, trace)


def _capture(ctx):
    """Run P1, P2 and P3 through the real ETL; snapshot values, not ids."""
    rpc = ctx.adapter.rpc
    sweep_wf010(rpc)
    require_mrp_attachment(ctx)

    snapshot = {"producing_lot_field": producing_lot_field(rpc)}

    part = part_code()
    correct_lot = lot_name("c")
    wrong_lot = lot_name("w")
    serial = serial_for("037/042", lot=correct_lot)
    other_serial = serial_for("001/002", lot=wrong_lot)

    product_id = make_product(ctx, part)
    mo_correct, _lc = mo_with_lot(ctx, product_id, correct_lot)
    mo_wrong, _lw = mo_with_lot(ctx, product_id, wrong_lot)
    ctx.log(f"MO-CORRECT={mo_correct} (lot {correct_lot!r}); "
            f"MO-WRONG={mo_wrong} (lot {wrong_lot!r})")

    # Both MOs must be reachable, or P3's wrong-MO outcome would be
    # indistinguishable from "no match" and the case would prove nothing.
    reachable = could_match(ctx, part, serial)
    snapshot["tier3_reaches_one_mo"] = len(reachable["tier3"]) == 1
    reachable_other = could_match(ctx, part, other_serial)
    snapshot["other_serial_reaches_one_mo"] = (
        len(reachable_other["tier3"]) == 1)
    ctx.log(f"tier reachability — canonical: {reachable!r}; "
            f"other: {reachable_other!r}")

    folder_id = make_folder(rpc, make_server(rpc))

    def which(res_id):
        """'correct' / 'wrong' / 'none' — comparable across databases."""
        if res_id == mo_correct:
            return "correct"
        if res_id == mo_wrong:
            return "wrong"
        return "none" if not res_id else "other"

    variants = {
        # P1: the canonical file, last row a full-width measurement line,
        # NO trailing newline after it.
        "P1_canonical": sample_file(part, serial),
        # P2: identical to P1 plus one trailing empty line. THE PRIMARY
        # ASSERTION.
        "P2_trailing_newline": sample_file(part, serial,
                                           trailing_newline=True),
        # P3: identical to P1 plus one extra final measurement row carrying
        # the OTHER serial. v17 attaches to MO-WRONG, by design.
        "P3_extra_measurement": sample_file(part, serial,
                                            extra_measurement=other_serial),
    }

    for label, content in variants.items():
        _folder, file_id, row = run_import(ctx, content, folder_id=folder_id,
                                           file_label=label)
        message = file_message(rpc, file_id)
        snapshot[f"{label}.state"] = row["state"]
        snapshot[f"{label}.part"] = row[PART_FIELD] or ""
        snapshot[f"{label}.serial"] = row[SERIAL_FIELD] or ""
        snapshot[f"{label}.landed_on"] = which(row["res_id"])
        snapshot[f"{label}.extraction_failed"] = (
            ERR_EXTRACT_PREFIX in message)
        snapshot[f"{label}.match_failed"] = ERR_NO_MATCH_HEADING in message
        # Step 11: nothing raises in any variant — the sftp.file reaches a
        # terminal state and no unexpected activity appears.
        snapshot[f"{label}.activities_on_file"] = len(
            activities_on(rpc, "sftp.file", [file_id]))
        ctx.log(f"{label}: state={row['state']!r} "
                f"part={row[PART_FIELD]!r} serial={row[SERIAL_FIELD]!r} "
                f"landed_on={snapshot[f'{label}.landed_on']!r}")
        ctx.log(f"{label} message, verbatim: {message!r}")

    # Step 12: the wrong-MO outcome is UNDETECTABLE from Odoo. Recorded as
    # part of the snapshot so a change in detectability is a difference.
    snapshot["MO_WRONG.attachments"] = len(
        attachments_on_mo(rpc, mo_wrong))
    snapshot["MO_CORRECT.attachments"] = len(
        attachments_on_mo(rpc, mo_correct))
    snapshot["MO_WRONG.activities"] = len(
        activities_on(rpc, "mrp.production", [mo_wrong]))
    snapshot["MO_CORRECT.activities"] = len(
        activities_on(rpc, "mrp.production", [mo_correct]))

    # Step 13: the other branch of MIMETYPE_TO_READER. The reader is chosen
    # from the attachment's mimetype and file name, so declaring an XLSX
    # mimetype over CSV bytes exercises the dispatch rather than the parse
    # — which is the half §2.13 actually rewrote (an ordered
    # extensions_to_try list replacing FILE_TYPE_DICT / EXTENSIONS).
    _folder, xl_id, xl_row = run_import(
        ctx, variants["P1_canonical"], folder_id=folder_id,
        file_label="P4_xlsx_mimetype",
        mimetype="application/vnd.openxmlformats-officedocument."
                 "spreadsheetml.sheet")
    snapshot["P4_xlsx_mimetype.state"] = xl_row["state"]
    snapshot["P4_xlsx_mimetype.part"] = xl_row[PART_FIELD] or ""
    snapshot["P4_xlsx_mimetype.serial"] = xl_row[SERIAL_FIELD] or ""
    snapshot["P4_xlsx_mimetype.landed_on"] = which(xl_row["res_id"])
    ctx.log(f"P4 (CSV bytes declared as XLSX): {xl_row['state']!r}, "
            f"landed_on={snapshot['P4_xlsx_mimetype.landed_on']!r}; "
            f"message={file_message(rpc, xl_id)!r}")

    ctx.log("Step 14, recorded as a dependency and not synthesisable: "
            "WF-010 requires two or three REAL client test files, "
            "including one with a longer metadata block and one with a "
            "single measurement row, and is explicit that 'without real "
            "files this feature cannot be validated at all'. Ask for them "
            "now — they are a Phase-0a dependency, not a Phase-5 one. The "
            "docstring sample this case uses is a starting point, not a "
            "substitute.")
    return snapshot


@test_case(
    id="TEST-WF010-TC349",
    name="v19: a trailing empty line shifts rows[-1] and attaches evidence "
         "to the wrong MO",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_mrp_sftp", priority="P0", kind="DATA", order=10349,
    description="Runs the canonical ragged file, the same file plus a "
                "trailing empty line, and the same file plus an extra "
                "measurement row carrying a different serial, through the "
                "real ETL against two candidate MOs — then asserts the "
                "extracted part, the extracted serial and WHICH MO the "
                "evidence reached are identical to the v17 baseline. "
                "Anchored on both versions: the canonical and "
                "trailing-newline files reach MO-CORRECT, the extra-row "
                "file reaches MO-WRONG, and nothing raises anywhere.",
    traceability=trace("DATAONE-TC349", user_story="delta §2.13 — the "
                                                   "highest-value parse "
                                                   "test before upgrading"))
def test_tc349(ctx):
    with ctx.step("Why a crash-only smoke test is worthless here"):
        ctx.log("On v19 the module imports, the cron runs, the file "
                "downloads, the ETL completes, the sftp.file reads Done and "
                "an attachment appears under a manufacturing order. Every "
                "green light is on. The only thing wrong is WHICH "
                "manufacturing order — and the only detector is a "
                "byte-for-byte comparison against a baseline captured "
                "BEFORE the upgrade. Capture this on the v17 clone while it "
                "still exists; afterwards the correct answer is unknowable "
                "and the only remaining validation is a manual audit of "
                "every attachment.")

    with ctx.step("What is asserted here rather than in the module's own "
                  "tests"):
        ctx.log("dto_mrp_sftp/tests/test_wf010_parse_and_match.py already "
                "pins rows[0][1], rows[-1][0], the trailing-blank-line case "
                "and the raggedness itself, in-process, because _read_file "
                "cannot be dispatched over RPC. What it CANNOT see is which "
                "MO the evidence reached: it re-implements the three tiers "
                "as a local helper. This case drives the real transformer "
                "and loader and asserts the observable outcome — the "
                "failure mode (c) that matters is a wrong ATTACHMENT, not a "
                "wrong tuple.")

    reconcile(
        ctx, "DATAONE-TC349", _capture,
        anchors={
            # Step 2 / step 5 — the canonical file.
            "P1_canonical.state": "done",
            "P1_canonical.landed_on": "correct",
            # Steps 6-7 — THE PRIMARY ASSERTION. A trailing newline must
            # not empty the serial (failure mode b) and must not shift the
            # last row (failure mode c).
            "P2_trailing_newline.state": "done",
            "P2_trailing_newline.landed_on": "correct",
            "P2_trailing_newline.extraction_failed": False,
            # Step 4 / step 8 — P3's documented wrong-MO behaviour. Correct
            # CURRENT behaviour, asserted so that a CHANGE is caught: it
            # would mean row selection shifted, which is as significant as
            # a break.
            "P3_extra_measurement.state": "done",
            "P3_extra_measurement.landed_on": "wrong",
            # Step 11 — nothing raises and nothing is flagged, in any
            # variant. That is the point of the case.
            "P1_canonical.activities_on_file": 0,
            "P2_trailing_newline.activities_on_file": 0,
            "P3_extra_measurement.activities_on_file": 0,
            # Step 12 — the wrong-MO outcome is undetectable from Odoo: the
            # attachment is present, the file is Done, and no activity
            # anywhere says the evidence belongs to a different unit.
            "MO_WRONG.activities": 0,
            "MO_CORRECT.activities": 0,
            # The fixture's own premise: both MOs must be reachable, or
            # 'wrong' could not be distinguished from 'none'.
            "tier3_reaches_one_mo": True,
            "other_serial_reaches_one_mo": True,
        })
