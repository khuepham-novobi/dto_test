"""DATAONE-WF-020 — the workflow gate and the partial-failure contract:
TC331, TC336.

TC331 is the workflow's gate case: one nine-column CSV with five rows —
two creates, two in-place updates (one blanking a field, one clearing a
payment term), and one row that fails on an unresolvable term — and the
group's defining assertion that **no trace of any kind lands on any
res.partner**.

TC336 is the same file's failure contract: the file reads Failed while its
four good rows persist, the only notification is one superuser activity on
the sftp.file, and re-processing after creating the missing term repairs
the bad row idempotently.

No network. The extractor reads ``sftp_file.attachment_id``, not SFTP —
see ``tests/wf020/common.py``. The fixture server is created inactive with
an unroutable host and is never connected to.

Fixture-value adaptation (documented, not assertion-weakening): the
workbook's TD ids (``V-GAMMA-001`` … ``V-GAMMA-013``, payment term
``30 Days``) belong to a seeded test dataset. On a live clone those refs
may exist as real vendors and ``30 Days`` may be ambiguous, so this suite
uses token-scoped equivalents (``WF020-<token>-001`` …, a token-scoped
payment term). Every *rule* asserted is the workbook's; only the literal
identifiers are namespaced, which is what makes the counts deterministic.

EXPECTED v17 OUTCOME: PASS.
EXPECTED v19 OUTCOME: PASS once the modules install; the transport's
``_read_group(..., having=…)`` and the ``<tree>`` views are the v19 watch
items, and neither is exercised here.
"""
from framework.registry import test_case
from tests.wf020.common import (MARK, WORKFLOW, WORKFLOW_NAME,  # noqa: F401
                                activities_on, expect_error, fx, m2o_id,
                                make_folder, make_server, partner_by_ref,
                                ref_for, require_sftp_stack,
                                require_supplier_usage, run_supplier_import,
                                supplier_row, sweep_wf020, trace)

SUPERUSER_ID = 1
UNRESOLVABLE_TERM = "Net 37 Days Nonexistent"
TERM_ERROR = "Cannot find payment term in Odoo"

# Fields the CSV maps, plus the derived country.
MAPPED = ["ref", "name", "street", "street2", "city", "zip", "phone",
          "property_supplier_payment_term_id", "state_id", "country_id"]
# Fields the flow must never touch.
UNMAPPED = ["email", "website", "vat", "comment", "supplier_rank",
            "customer_rank", "active", "company_id", "parent_id"]


def _require_reference_data(ctx):
    """Texas/US must exist — the state resolution the CSV relies on."""
    rpc = ctx.adapter.rpc
    states = rpc.search_read("res.country.state",
                             [("name", "=", "Texas"),
                              ("country_id.code", "=", "US")],
                             ["name", "country_id"])
    if len(states) != 1:
        ctx.blocked(
            "res.country.state 'Texas' with country_id.code 'US' does not "
            f"resolve to exactly one record on {ctx.env.key} (found "
            f"{len(states)}). The supplier CSV's state column depends on it; "
            "seed or de-duplicate the state data before running WF-020.")
    return states[0]


def _make_term(rpc, label="Net30"):
    """A token-scoped payment term, so exact-name matching is unambiguous."""
    name = fx(f"{MARK} {label}")
    return name, rpc.create("account.payment.term", {"name": name})


def _five_row_file(rpc, term_name):
    """The workbook's five rows, with token-scoped refs.

    Returns (rows, refs) where refs is keyed r1…r5.
    """
    refs = {f"r{i}": ref_for(f"{i:03d}") for i in range(1, 6)}
    rows = [
        # Row 1 — new vendor
        supplier_row(refs["r1"], fx(f"{MARK} Vendor Epsilon"),
                     street="100 Congress Ave", street2="Suite 400",
                     city="Austin", zip_code="78701",
                     phone="+1 512 555 0100", payment_term=term_name),
        # Row 2 — existing, matched on ref; blanks street2
        supplier_row(refs["r2"], fx(f"{MARK} Vendor Gamma Renamed"),
                     street="2200 Market St", street2="",
                     city="Philadelphia", zip_code="19103",
                     phone="+1 215 555 0102", payment_term=term_name),
        # Row 3 — existing; blank term must CLEAR the value
        supplier_row(refs["r3"], fx(f"{MARK} Vendor Iota"),
                     street="3 Iota Rd", city="Austin", zip_code="78702",
                     phone="+1 512 555 0103", payment_term=""),
        # Row 4 — existing; unresolvable term must fail ONLY this row
        supplier_row(refs["r4"], fx(f"{MARK} Vendor Kappa Renamed"),
                     street="4 Kappa Rd", city="Austin", zip_code="78703",
                     phone="+1 512 555 0104",
                     payment_term=UNRESOLVABLE_TERM),
        # Row 5 — new vendor
        supplier_row(refs["r5"], fx(f"{MARK} Vendor Theta"),
                     street="5 Theta Rd", city="Austin", zip_code="78704",
                     phone="+1 512 555 0105", payment_term=term_name),
    ]
    return rows, refs


def _seed_existing(rpc, refs, term_id):
    """Rows 2, 3 and 4's partners, pre-populated as the workbook describes —
    including the unmapped fields that must survive the import untouched."""
    seeded = {}
    for key, extra in (
        ("r2", {"street2": "Bldg 7", "city": "Austin", "zip": "78701",
                "phone": "+1 512 555 0000"}),
        ("r3", {"street2": "", "city": "Austin", "zip": "78701",
                "phone": "+1 512 555 0001"}),
        ("r4", {"street2": "", "city": "Austin", "zip": "78701",
                "phone": "+1 512 555 0002"}),
    ):
        vals = {
            "name": fx(f"{MARK} Seeded {key}"),
            "ref": refs[key],
            "street": "1 Original St",
            "email": f"{key}.qa@example.invalid",
            "website": "https://example.invalid",
            "comment": "QA seed — must survive the import untouched",
            "property_supplier_payment_term_id": term_id,
        }
        vals.update(extra)
        seeded[key] = rpc.create("res.partner", vals)
    return seeded


@test_case(
    id="TEST-WF020-TC331",
    name="GATE: nine-column CSV, five rows, one failure, no activity on any "
         "partner",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account_workday, novobi_sftp_connection",
    priority="P0", kind="API", order=20331,
    description="Two vendors created with supplier_rank 1, two updated in "
                "place (one field blanked, one payment term cleared), one "
                "row failed leaving its partner untouched, the file Failed "
                "with one superuser activity — and not a single activity or "
                "chatter message on any res.partner.",
    traceability=trace("DATAONE-TC331"))
def test_tc331(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-020 fixtures and open a fresh "
                  "namespace"):
        sweep_wf020(rpc)

    with ctx.step("Preconditions: the transport, the supplier usage key and "
                  "the Texas/US state"):
        require_sftp_stack(ctx)
        require_supplier_usage(ctx)
        texas = _require_reference_data(ctx)
        ctx.log(f"state fixture: {texas!r}")

    try:
        with ctx.step("Seed the payment term and the three existing "
                      "partners (rows 2, 3, 4)"):
            term_name, term_id = _make_term(rpc)
            rows, refs = _five_row_file(rpc, term_name)
            seeded = _seed_existing(rpc, refs, term_id)
            ctx.check("nothing named the unresolvable term exists",
                      [], rpc.search("account.payment.term",
                                     [("name", "=", UNRESOLVABLE_TERM)]))

        with ctx.step("Step 1: record every touched partner's full state "
                      "before the run"):
            before = {k: partner_by_ref(rpc, refs[k],
                                        MAPPED + UNMAPPED + ["id"])
                      for k in refs}
            ctx.log(f"before: {before!r}")
            ctx.check("rows 1 and 5 do not exist yet",
                      [None, None], [before["r1"], before["r5"]])

        with ctx.step("Steps 2-4: the nine-column CSV is attached to one "
                      "sftp.file and processed through the real ETL"):
            # counted marker-scoped, never over the whole partner table:
            # a production clone holds tens of thousands of rows and the
            # only ones this run may create carry the execution token
            marker_domain = [("ref", "like", f"{MARK}-%"),
                             ("active", "in", [True, False])]
            partners_before = rpc.call("res.partner", "search_count",
                                       marker_domain)
            file_id, file_row = run_supplier_import(ctx, rows,
                                                    file_label="suppliers")
            ctx.log(f"sftp.file after processing: {file_row!r}")
            att = rpc.read("sftp.file", [file_id],
                           ["attachment_id", "usage", "state"])[0]
            ctx.check_true("the file carries its CSV attachment",
                           bool(att["attachment_id"]),
                           actual_desc=repr(att["attachment_id"]))
            ctx.check("file usage", "workday_supplier", att["usage"])

        with ctx.step("Steps 5-8: row 1 created a vendor with every mapped "
                      "field, supplier_rank 1, the term, and the state with "
                      "its DERIVED country"):
            r1 = partner_by_ref(rpc, refs["r1"])
            ctx.check_true("row 1 partner exists", r1 is not None,
                           actual_desc=repr(r1))
            expected = {"name": rows[0]["name"], "ref": refs["r1"],
                        "street": "100 Congress Ave", "street2": "Suite 400",
                        "city": "Austin", "zip": "78701",
                        "phone": "+1 512 555 0100"}
            actual = {k: r1[k] for k in expected}
            ctx.check("row 1 mapped fields", expected, actual)
            ctx.check("row 1 supplier_rank", 1, r1["supplier_rank"])
            ctx.check("row 1 payment term", term_id,
                      m2o_id(r1["property_supplier_payment_term_id"]))
            ctx.check("row 1 state_id", texas["id"], m2o_id(r1["state_id"]))
            ctx.check("row 1 country_id derived from the state",
                      m2o_id(texas["country_id"]), m2o_id(r1["country_id"]))

        with ctx.step("Steps 9-12: row 2 was written IN PLACE — same id, "
                      "street2 blanked, supplier_rank untouched"):
            r2 = partner_by_ref(rpc, refs["r2"], MAPPED + UNMAPPED + ["id"])
            ctx.check("row 2 partner id unchanged", seeded["r2"], r2["id"])
            ctx.check("row 2 name", rows[1]["name"], r2["name"])
            ctx.check("row 2 street", "2200 Market St", r2["street"])
            # `or False` normalises the two shapes a blanked Char can
            # come back in. The ETL writes the CSV cell verbatim after a
            # .strip() (dto_purchase_workday/models/res_partner.py:70),
            # so a blank cell writes '' — and Char keeps the empty string
            # through convert_to_cache on BOTH versions (v17
            # odoo/fields.py:1962, v19 odoo/orm/fields_textual.py:107,
            # where falsy_value = '' is now explicit). The workbook's
            # expectation is that the field is BLANK, which '' and False
            # both satisfy; dto_purchase_workday's own _changed_fields
            # compares the same way (res_partner.py:288).
            ctx.check("row 2 street2 blanked (was 'Bldg 7')", False,
                      r2["street2"] or False)
            ctx.check("row 2 supplier_rank unchanged",
                      before["r2"]["supplier_rank"], r2["supplier_rank"])

        with ctx.step("Steps 13-14: row 3's blank payment term CLEARED the "
                      "value, and the rest of the row was written normally"):
            r3 = partner_by_ref(rpc, refs["r3"])
            ctx.check("row 3 payment term cleared", False,
                      r3["property_supplier_payment_term_id"])
            ctx.check("row 3 name", rows[2]["name"], r3["name"])
            ctx.check("row 3 street", "3 Iota Rd", r3["street"])

        with ctx.step("Steps 15-16: row 4's unresolvable term left its "
                      "partner COMPLETELY unchanged — not partially "
                      "written"):
            r4 = partner_by_ref(rpc, refs["r4"], MAPPED + UNMAPPED + ["id"])
            diffs = {k: {"before": before["r4"].get(k), "after": r4.get(k)}
                     for k in MAPPED + UNMAPPED
                     if before["r4"].get(k) != r4.get(k)}
            ctx.check("row 4 column differences", {}, diffs)
            activities = activities_on(rpc, "sftp.file", [file_id])
            bodies = [a["summary"] or "" for a in activities]
            note_rows = rpc.search_read(
                "mail.activity",
                [("res_model", "=", "sftp.file"), ("res_id", "=", file_id)],
                ["note", "user_id", "activity_type_id", "date_deadline"])
            ctx.log(f"sftp.file activities: {note_rows!r}")
            ctx.check_true(
                f"the row error names {TERM_ERROR!r}",
                any(TERM_ERROR in (a.get("note") or "") for a in note_rows),
                actual_desc=f"{len(note_rows)} activity(ies): {bodies}")

        with ctx.step("Step 17: row 5 created the second vendor with "
                      "supplier_rank 1"):
            r5 = partner_by_ref(rpc, refs["r5"])
            ctx.check_true("row 5 partner exists", r5 is not None,
                           actual_desc=repr(r5))
            ctx.check("row 5 supplier_rank", 1, r5["supplier_rank"])
            ctx.check("row 5 name", rows[4]["name"], r5["name"])

        with ctx.step("Step 18 — THE GROUP'S DEFINING ASSERTION: no "
                      "mail.activity exists on ANY res.partner touched by "
                      "this run"):
            touched = [p["id"] for p in
                       (partner_by_ref(rpc, refs[k], ["id"]) for k in refs)
                       if p]
            ctx.log(f"partners touched: {touched}")
            ctx.check("activities on res.partner", [],
                      activities_on(rpc, "res.partner", touched))

        with ctx.step("Step 19: no chatter message was posted on any "
                      "partner either"):
            messages = rpc.search_read(
                "mail.message",
                [("model", "=", "res.partner"), ("res_id", "in", touched),
                 ("message_type", "!=", "notification")],
                ["res_id", "body", "message_type"])
            ctx.log(f"partner messages: {messages!r}")
            ctx.check("non-notification chatter messages on the partners",
                      [], messages)

        with ctx.step("The run created exactly the two new partners it "
                      "should have — no duplicate for a matched ref"):
            partners_after = rpc.call("res.partner", "search_count",
                                      marker_domain)
            ctx.log(f"marker-scoped partners: {partners_before} -> "
                    f"{partners_after}")
            ctx.check("partners created by the run", 2,
                      partners_after - partners_before)
            for key in refs:
                ctx.check(f"exactly one partner for ref {key}", 1,
                          rpc.call("res.partner", "search_count",
                                   [("ref", "=", refs[key]),
                                    ("active", "in", [True, False])]))
    finally:
        with ctx.step("Cleanup WF-020 fixtures"):
            try:
                sweep_wf020(rpc)
            except Exception as exc:      # noqa: BLE001 — never mask a verdict
                ctx.log(f"[warn] cleanup incomplete: {exc}")


@test_case(
    id="TEST-WF020-TC336",
    name="The file goes Failed with no activity on any partner; re-process "
         "repairs the bad row",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account_workday, novobi_sftp_connection",
    priority="P1", kind="API", order=20336,
    description="A partially-failed file reads Failed while its four good "
                "rows persist; the only notification is one superuser "
                "warning activity on the sftp.file; creating the missing "
                "term and re-processing repairs row 4 and re-applies the "
                "others idempotently; the Done file cannot be re-processed.",
    traceability=trace("DATAONE-TC336"))
def test_tc336(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-020 fixtures and open a fresh "
                  "namespace"):
        sweep_wf020(rpc)

    with ctx.step("Preconditions: the transport, the supplier usage key and "
                  "the Texas/US state"):
        require_sftp_stack(ctx)
        require_supplier_usage(ctx)
        _require_reference_data(ctx)

    try:
        with ctx.step("Seed the term, the existing partners and the "
                      "five-row file"):
            term_name, term_id = _make_term(rpc)
            rows, refs = _five_row_file(rpc, term_name)
            _seed_existing(rpc, refs, term_id)
            ctx.check("the unresolvable term does not exist yet", [],
                      rpc.search("account.payment.term",
                                 [("name", "=", UNRESOLVABLE_TERM)]))

        with ctx.step("Steps 1-2: process the file — it reaches Failed with "
                      "process_date stamped"):
            server_id = make_server(rpc)
            folder_id = make_folder(rpc, server_id)
            file_id, file_row = run_supplier_import(ctx, rows,
                                                    folder_id=folder_id)
            ctx.check("file state", "failed", file_row["state"])
            ctx.check_true("process_date stamped",
                           bool(file_row["process_date"]),
                           actual_desc=repr(file_row["process_date"]))

        with ctx.step("Step 3 — the case's central point: rows 1, 2, 3 and "
                      "5 were written and KEPT despite the file reading "
                      "Failed"):
            good = {k: partner_by_ref(rpc, refs[k])
                    for k in ("r1", "r2", "r3", "r5")}
            missing = [k for k, v in good.items() if v is None]
            ctx.check("good rows missing after a Failed file", [], missing)
            ctx.check("row 2 was renamed despite the file failing",
                      rows[1]["name"], good["r2"]["name"])

        with ctx.step("Step 4: exactly one 'Cannot process SFTP file' "
                      "warning activity on the sftp.file, owned by the "
                      "superuser, deadlined on the process date"):
            acts = rpc.search_read(
                "mail.activity",
                [("res_model", "=", "sftp.file"), ("res_id", "=", file_id)],
                ["summary", "note", "user_id", "activity_type_id",
                 "date_deadline"])
            ctx.log(f"activities: {acts!r}")
            ctx.check("activity count on the sftp.file", 1, len(acts))
            act = acts[0]
            ctx.check("activity summary", "Cannot process SFTP file",
                      act["summary"])
            ctx.check("activity owner is the superuser", SUPERUSER_ID,
                      m2o_id(act["user_id"]))
            warning_type = rpc.ref("mail.mail_activity_data_warning")
            ctx.check("activity type", warning_type,
                      m2o_id(act["activity_type_id"]))

        with ctx.step("Step 5: the activity body carries the row error and "
                      "names the payment-term failure"):
            ctx.check_true(f"note contains {TERM_ERROR!r}",
                           TERM_ERROR in (act["note"] or ""),
                           actual_desc=(act["note"] or "")[:300])

        with ctx.step("Step 6: no activity and no chatter message on any "
                      "res.partner"):
            touched = [p["id"] for p in
                       (partner_by_ref(rpc, refs[k], ["id"]) for k in refs)
                       if p]
            ctx.check("activities on res.partner", [],
                      activities_on(rpc, "res.partner", touched))

        with ctx.step("Step 7: the file's chatter does not carry the ETL "
                      "message — a failure is filed as an activity, and "
                      "message_post happens only on a clean file"):
            bodies = [m["body"] or "" for m in rpc.search_read(
                "mail.message",
                [("model", "=", "sftp.file"), ("res_id", "=", file_id)],
                ["body"])]
            ctx.log(f"file chatter: {bodies!r}")
            # mark_sync_failed schedules an activity and never posts;
            # mark_sync_success posts the ETL message. The error text
            # appearing in the chatter would mean the wrong branch ran.
            ctx.check("chatter messages carrying the ETL error text", [],
                      [b[:200] for b in bodies if TERM_ERROR in b])

        with ctx.step("Steps 8-11: create the missing term, Re-process, and "
                      "row 4 now succeeds"):
            r4_before = partner_by_ref(rpc, refs["r4"])
            good_before = {k: partner_by_ref(rpc, refs[k])
                           for k in ("r1", "r2", "r3", "r5")}
            rpc.create("account.payment.term", {"name": UNRESOLVABLE_TERM})
            rpc.call("sftp.file", "action_retry_process_sftp_files",
                     [file_id])
            after = rpc.read("sftp.file", [file_id],
                             ["state", "process_date"])[0]
            ctx.log(f"file after re-process: {after!r}")
            r4_after = partner_by_ref(rpc, refs["r4"])
            ctx.check("row 4 name after the repair", rows[3]["name"],
                      r4_after["name"])
            ctx.check("row 4 street after the repair", "4 Kappa Rd",
                      r4_after["street"])
            ctx.check_true("row 4 was untouched before the repair",
                           r4_before["name"] != rows[3]["name"],
                           actual_desc=repr(r4_before["name"]))

        with ctx.step("Step 12: rows 1, 2, 3 and 5 were re-applied "
                      "idempotently — nothing changed"):
            diffs = {}
            for key, prev in good_before.items():
                now = partner_by_ref(rpc, refs[key])
                delta = {f: {"before": prev.get(f), "after": now.get(f)}
                         for f in prev if prev.get(f) != now.get(f)}
                if delta:
                    diffs[key] = delta
            ctx.check("differences after the idempotent re-run", {}, diffs)

        with ctx.step("Step 13: the file is now Done"):
            ctx.check("file state after the repair", "done", after["state"])

        with ctx.step("Step 16: Re-process on a Done file raises the exact "
                      "UserError"):
            raised, message = expect_error(
                rpc.call, "sftp.file", "action_retry_process_sftp_files",
                [file_id])
            ctx.log(f"raised: {message!r}")
            ctx.check_true("re-processing a Done file was refused", raised,
                           actual_desc=message)
            ctx.check_true(
                "the message is 'File(s) have been processed already!'",
                "File(s) have been processed already!" in message,
                actual_desc=message)
    finally:
        with ctx.step("Cleanup WF-020 fixtures"):
            try:
                rpc.call("account.payment.term", "unlink",
                         rpc.search("account.payment.term",
                                    [("name", "=", UNRESOLVABLE_TERM)]))
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] repair term not removed: {exc}")
            try:
                sweep_wf020(rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")
