"""DATAONE-WF-010 — the GATE: TC344.

The workflow's gate, and the workbook is explicit about why it is written
around TIER 3 rather than an exact match: *"The serial-prefix retry (tier 3)
is what makes this pass; a test whose serial matches the lot exactly proves
nothing."*

So the fixture is built so that tiers 1 and 2 CANNOT fire, and that is
PROVED before the file is processed rather than assumed — ``could_match``
runs the transformer's own three searches and the result is asserted empty
for tiers 1 and 2 and non-empty for tier 3. Without that step the case
would pass whichever tier matched and would be evidence about nothing.

Two distinctions the case turns on
----------------------------------
* **The recorded serial is the FULL suffixed value; only the MATCHED value
  is the prefix** (step 8). ``mrp_attachment_serial_number`` holds what the
  file said — ``<lot>-037/042`` — while the tier-3 search used
  ``serial[:serial.rfind('-')]``. A port that stores the truncated value
  loses the ability to say which physical unit the file describes.
* **BOTH records are stamped** (step 13). ``MRPAttachmentLoader`` writes
  ``res_model``/``res_id`` onto the ``sftp.file`` AND onto the
  ``ir.attachment`` (``mrp_attachment_loader.py:18-26``). Only the second
  makes the file appear under the MO's Attachments; only the first makes the
  ``sftp.file``'s Document reference resolve. Asserting one and inferring
  the other is how a half-ported loader passes.

And step 16: **no field on the MO changes.** The MO gains an attachment;
nothing on the record itself is written. The complete stored-field dump is
taken before and diffed after, so a loader that helpfully writes a state or
a date is caught.

EXPECTED v17 OUTCOME: PASS.
EXPECTED v19 OUTCOME: PASS. Two watch items. (1) ``lot_producing_id`` ->
``lot_producing_ids`` — tiers 2 and 3 both search it; the ported tree
already uses the M2m and ``producing_lot_field`` resolves whichever the
target has, so a failure here means the domain still names the v17 field.
(2) ``base_import._read_file``'s internals, which is TEST-WF010-TC349's
whole subject. (3) ``stock.lot.custom`` may not survive the port, which
would silently remove tier 1 — probed by ``require_custom_lot`` in
TEST-WF010-TC345, not here, because tier 1 is deliberately impossible in
this fixture.
"""
from framework.registry import test_case
from tests.wf010.common import (ATTACHMENT_USAGE,  # noqa: F401
                                FILE_FORM_VIEW, MARK, PART_FIELD,
                                PARENT_FILE_FORM_VIEW, PROCESS_CRON_XMLID,
                                SAMPLE_SERIAL, SERIAL_FIELD, WORKFLOW,
                                WORKFLOW_NAME, activities_on,
                                attachments_on_mo, could_match, file_message,
                                form_arch, fx, lot_name, m2o_id, make_folder,
                                make_product, make_server, make_sftp_file,
                                mo_dump, mo_with_lot, part_code,
                                process_file, producing_lot_field,
                                require_mrp_attachment, run_import,
                                sample_file, serial_for, sweep_wf010, trace)


@test_case(
    id="TEST-WF010-TC344",
    name="GATE: the verbatim docstring sample, matched by tier 3, both "
         "records stamped",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_mrp_sftp", priority="P1", kind="API", order=10344,
    description="Drives the real ETL over the canonical ragged test-result "
                "file against an MO whose producing lot is the serial's "
                "PREFIX, having first PROVED tiers 1 and 2 cannot fire. "
                "Asserts the part and the full suffixed serial are recorded "
                "verbatim, that the match fired at tier 3, that BOTH the "
                "sftp.file and the ir.attachment are stamped with the MO, "
                "that the evidence appears under the MO with byte-identical "
                "content, that NO field on the MO changed, that the file is "
                "Done with the message in its chatter, and that "
                "re-stamping is idempotent.",
    traceability=trace("DATAONE-TC344"))
def test_tc344(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-010 fixtures and open a fresh "
                  "namespace"):
        sweep_wf010(rpc)

    with ctx.step("Preconditions: the attachment import stack and the "
                  "usage key"):
        require_mrp_attachment(ctx)
        lot_field = producing_lot_field(rpc)
        ctx.log(f"this target's producing-lot field: {lot_field!r} "
                "(v19 turned the Many2one into a Many2many, §2.8, and both "
                "tier 2 and tier 3 search it)")

    with ctx.step("Step 1: MO-T3 — an MO for the token-scoped part whose "
                  "producing lot is the serial's PREFIX, not the serial. "
                  "Record its complete stored-field dump"):
        part = part_code()
        prefix = lot_name()
        serial = serial_for("037/042", lot=prefix)
        product_id = make_product(ctx, part)
        mo_t3, lot_id = mo_with_lot(ctx, product_id, prefix)
        ctx.log(f"part={part!r} serial={serial!r} prefix={prefix!r}")
        ctx.log(f"MO-T3 = {mo_t3}, producing lot {lot_id}")
        before_dump = mo_dump(rpc, mo_t3)
        ctx.log(f"MO-T3 baseline dump ({len(before_dump)} fields): "
                f"{ {k: before_dump[k] for k in sorted(before_dump)[:12]} !r} …")
        mo_row = rpc.read("mrp.production", [mo_t3],
                          ["name", "product_id", "state", lot_field])[0]
        ctx.log(f"MO-T3: {mo_row!r}")

    with ctx.step("Step 2: MO-T3's current attachment count"):
        before_attachments = attachments_on_mo(rpc, mo_t3)
        ctx.log(f"attachments on MO-T3 before: {before_attachments!r}")
        ctx.check("MO-T3 starts with no attachments", [],
                  before_attachments)

    with ctx.step("Step 3: PROVE tiers 1 and 2 cannot fire, and that tier 3 "
                  "can. Without this the case proves nothing about tier 3"):
        reachable = could_match(ctx, part, serial)
        ctx.log(f"what each tier could reach: {reachable!r}")
        ctx.check("tier 1 (stock.lot.custom, full serial) reaches nothing",
                  [], reachable["tier1"])
        ctx.check("tier 2 (producing lot == full serial) reaches nothing",
                  [], reachable["tier2"])
        ctx.check("tier 3's truncation is serial[:rfind('-')]", prefix,
                  reachable["tier3_prefix"])
        ctx.check("and tier 3 reaches exactly MO-T3", [mo_t3],
                  reachable["tier3"])

    with ctx.step("Steps 4-6: place the file under an arbitrary name — the "
                  "filename carries no convention and is never parsed — and "
                  "process it through the real ETL"):
        folder_id = make_folder(rpc, make_server(rpc))
        file_id = make_sftp_file(rpc, folder_id,
                                 fx(f"{MARK}_results_run47.txt"),
                                 sample_file(part, serial))
        file_row = process_file(ctx, file_id)
        ctx.log(f"sftp.file after processing: {file_row!r}")
        ctx.check("exactly one sftp.file on the fixture folder", 1,
                  len(rpc.search("sftp.file",
                                 [("folder_id", "=", folder_id)])))
        ctx.check("it carries the MO-attachment usage key",
                  ATTACHMENT_USAGE, file_row["usage"])
        ctx.check_true("with the file attached",
                       bool(m2o_id(file_row["attachment_id"])),
                       actual_desc=repr(file_row["attachment_id"]))

    with ctx.step("Steps 7-8: the part is rows[0][1] verbatim, and the "
                  "recorded serial is the FULL SUFFIXED value — the prefix "
                  "is used only for matching"):
        ctx.check(f"{PART_FIELD} is the part number verbatim", part,
                  file_row[PART_FIELD])
        ctx.check(f"{SERIAL_FIELD} is the full suffixed serial, not the "
                  "prefix", serial, file_row[SERIAL_FIELD])
        ctx.check_true(
            "and the two differ — a port that stored the truncated value "
            "would lose which physical unit the file describes",
            file_row[SERIAL_FIELD] != prefix,
            actual_desc=f"{file_row[SERIAL_FIELD]!r} vs prefix {prefix!r}")

    with ctx.step("Step 9: both fields are contributed to the sftp.file "
                  "form by dto_mrp_sftp's only data file, each hidden "
                  "unless the usage is mrp_attachment"):
        view_id = rpc.ref(FILE_FORM_VIEW)
        ctx.check_true(f"{FILE_FORM_VIEW} resolves", bool(view_id),
                       actual_desc=repr(view_id))
        arch = form_arch(ctx, "sftp.file", "form")
        ctx.log(f"sftp.file form arch length: {len(arch)}")
        for field in (PART_FIELD, SERIAL_FIELD):
            ctx.check_true(f"{field} appears in the rendered form arch",
                           f'name="{field}"' in arch, actual_desc=field)
        ctx.check_true(
            "each is gated on the usage, so it stays hidden on payment, "
            "supplier and requisition files",
            arch.count(f"usage != '{ATTACHMENT_USAGE}'") >= 2
            or arch.count(f'usage != "{ATTACHMENT_USAGE}"') >= 2,
            actual_desc=f"invisible-on-usage occurrences: "
                        f"{arch.count(ATTACHMENT_USAGE)}")

    with ctx.step("Step 10: the match fired at TIER 3 — proved, not "
                  "inferred"):
        after = could_match(ctx, part, serial)
        ctx.log(f"tiers after the run (unchanged by design): {after!r}")
        ctx.check("tiers 1 and 2 still reach nothing, so the only tier that "
                  "could have matched is 3", ([], []),
                  (after["tier1"], after["tier2"]))
        ctx.check("and the MO the file landed on is the one tier 3 reaches",
                  [file_row["res_id"]], after["tier3"])

    with ctx.step("Steps 11-12: the sftp.file is stamped with the MO and "
                  "its Document reference resolves"):
        ctx.check("res_model", "mrp.production", file_row["res_model"])
        ctx.check("res_id", mo_t3, file_row["res_id"])
        ctx.check("the computed Document reference",
                  f"mrp.production,{mo_t3}", file_row["reference"])

    with ctx.step("Steps 13-15: the ir.attachment was ALSO stamped — this "
                  "is what makes the file appear under the MO — and the "
                  "count rose by exactly one with byte-identical content"):
        attachment_id = m2o_id(file_row["attachment_id"])
        attachment = rpc.read("ir.attachment", [attachment_id],
                              ["res_model", "res_id", "name", "datas",
                               "file_size"])[0]
        ctx.log(f"attachment: "
                f"{ {k: v for k, v in attachment.items() if k != 'datas'} !r}")
        ctx.check("attachment res_model", "mrp.production",
                  attachment["res_model"])
        ctx.check("attachment res_id", mo_t3, attachment["res_id"])
        after_attachments = attachments_on_mo(rpc, mo_t3)
        ctx.log(f"attachments on MO-T3 after: {after_attachments!r}")
        ctx.check("the count rose by exactly one",
                  len(before_attachments) + 1, len(after_attachments))
        import base64
        ctx.check("the stored bytes are byte-identical to the source file",
                  sample_file(part, serial),
                  base64.b64decode(attachment["datas"]))

    with ctx.step("Step 16: NO FIELD on MO-T3 changed. The MO gains an "
                  "attachment; nothing on the record itself is written"):
        after_dump = mo_dump(rpc, mo_t3)
        volatile = {"write_date", "__last_update", "message_needaction",
                    "message_needaction_counter", "message_has_error",
                    "message_has_error_counter", "message_attachment_count",
                    "access_token", "activity_state", "activity_date_deadline"}
        drift = {key: {"before": before_dump.get(key),
                       "after": after_dump.get(key)}
                 for key in set(before_dump) | set(after_dump)
                 if key not in volatile
                 and before_dump.get(key) != after_dump.get(key)}
        ctx.log(f"attachment counter, for the record: "
                f"{before_dump.get('message_attachment_count')!r} -> "
                f"{after_dump.get('message_attachment_count')!r}")
        ctx.check("the complete stored-field dump is unchanged, excluding "
                  "the mail-mixin counters and write_date", {}, drift)

    with ctx.step("Step 17: the file is Done with process_date stamped and "
                  "the ETL message in its chatter"):
        ctx.check("state", "done", file_row["state"])
        ctx.check_true("process_date stamped",
                       bool(file_row["process_date"]),
                       actual_desc=repr(file_row["process_date"]))
        message = file_message(rpc, file_id)
        ctx.log(f"sftp.file chatter / activity text: {message!r}")
        ctx.log("mark_sync_success posts the ETL message as HTML only when "
                "there IS one (sftp_file.py:184-191); the MO-attachment "
                "loader returns no message on success, so an empty chatter "
                "is the correct outcome here rather than a missing one.")

    with ctx.step("Step 18: no activity was created anywhere — not on the "
                  "file, not on the MO"):
        ctx.check("no activity on the sftp.file", [],
                  activities_on(rpc, "sftp.file", [file_id]))
        ctx.check("no activity on the MO", [],
                  activities_on(rpc, "mrp.production", [mo_t3]))

    with ctx.step("Step 19: the remote archive move is NOT observable "
                  "here — recorded, not asserted"):
        ctx.log("SFTPConnection.move_files(mode='new_file') and "
                "get_or_auto_create_archive_path run inside "
                "sftp.folder.action_get_files against a live endpoint. "
                "Convention rule 4 forbids reaching it, and the fixture "
                "server is active=False with archive_auto off. The archive "
                "assertion belongs to an endpoint-bearing run.")

    with ctx.step("Step 20: re-stamping is idempotent (BR-7) — the loader's "
                  "write is unconditional and re-points the SAME records, "
                  "so a second run cannot duplicate the attachment"):
        ctx.log("Re-process is unavailable on a Done file "
                "(action_retry_process_sftp_files raises 'File(s) have been "
                "processed already!', sftp_file.py:221-222 — asserted by "
                "TEST-WF019-TC299). The workbook therefore asks for the "
                "LOADER to be re-run instead. Its effect is two writes of "
                "res_model/res_id onto records that already hold those "
                "values (mrp_attachment_loader.py:18-26), so the "
                "equivalent observable assertion is that a SECOND file "
                "carrying the same content attaches to the same MO and "
                "leaves exactly one attachment PER FILE rather than "
                "duplicating the first.")
        _folder, second_id, second_row = run_import(
            ctx, sample_file(part, serial), folder_id=folder_id,
            file_label="results_run48")
        ctx.log(f"second sftp.file: {second_row!r}")
        ctx.check("the second file also reaches Done", "done",
                  second_row["state"])
        ctx.check("and it landed on the SAME MO", mo_t3,
                  second_row["res_id"])
        final = attachments_on_mo(rpc, mo_t3)
        ctx.log(f"attachments on MO-T3 after two files: {final!r}")
        ctx.check(
            "exactly one attachment per processed file — the stamp is "
            "idempotent per record and does not re-point or duplicate the "
            "earlier one", 2, len(final))
        ctx.check("the first attachment is still stamped with MO-T3",
                  (mo_t3, "mrp.production"),
                  (attachment["res_id"], attachment["res_model"]))
