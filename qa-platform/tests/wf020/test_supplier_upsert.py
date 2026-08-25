"""DATAONE-WF-020 — the upsert contract: TC332, TC333.

TC332: a new vendor is created once, ranked as a vendor, usable on a
purchase order, and re-processing the same file is idempotent — the rank is
set on create only, so a re-run must not bump it to 2.

TC333: an existing partner matched on ``ref`` is written IN PLACE and
**unconditionally**, blanks included. ``_prepare_workday_contact_vals``
builds all seven address keys from the row with no emptiness test, so a
blank cell overwrites a populated field. Step 6 is the destructive
assertion and is made explicit. Everything the CSV does not carry must be
untouched.

Substitution for TC332 steps 8-11 (the PO dropdown): the test drives
``name_search`` on ``res.partner`` — the same call the dropdown makes — and
then actually creates a purchase.order with a line, which is a stronger
check than observing a dropdown entry. Documented, not weakening.

EXPECTED v17 OUTCOME: PASS.
"""
from framework.registry import test_case
from tests.wf020.common import (MARK, WORKFLOW, WORKFLOW_NAME,  # noqa: F401
                                activities_on, expect_error, fx, m2o_id,
                                partner_by_ref, ref_for, require_sftp_stack,
                                require_supplier_usage, run_supplier_import,
                                supplier_row, sweep_wf020, trace)

NAME_MISSING = "Supplier name is missing"

MAPPED = ["ref", "name", "street", "street2", "city", "zip", "phone",
          "property_supplier_payment_term_id", "state_id", "country_id"]
UNMAPPED = ["email", "website", "vat", "comment", "supplier_rank",
            "customer_rank", "active", "company_id", "parent_id",
            "is_company"]


@test_case(
    id="TEST-WF020-TC332",
    name="A new vendor is created with supplier_rank = 1 and is selectable "
         "on a PO",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account_workday", priority="P1", kind="API", order=20332,
    description="Both new refs produce exactly one partner each with "
                "supplier_rank 1 and customer_rank 0, at default hierarchy "
                "and active; the partner resolves through name_search and a "
                "purchase order saves against it; re-processing creates no "
                "duplicate and leaves supplier_rank at 1.",
    traceability=trace("DATAONE-TC332"))
def test_tc332(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-020 fixtures and open a fresh "
                  "namespace"):
        sweep_wf020(rpc)

    with ctx.step("Preconditions: transport and supplier usage key"):
        require_sftp_stack(ctx)
        require_supplier_usage(ctx)

    po_id = None
    try:
        with ctx.step("Step 1: neither ref exists before the run"):
            refs = {"a": ref_for("010"), "b": ref_for("013")}
            for key, ref in refs.items():
                ctx.check(f"partners with ref {key}", 0,
                          rpc.call("res.partner", "search_count",
                                   [("ref", "=", ref),
                                    ("active", "in", [True, False])]))

        with ctx.step("Step 2: process a two-row file (no payment term, no "
                      "state — this case is about creation and ranking)"):
            rows = [
                supplier_row(refs["a"], fx(f"{MARK} Vendor Epsilon"),
                             street="100 Congress Ave", state=""),
                supplier_row(refs["b"], fx(f"{MARK} Vendor Theta"),
                             street="5 Theta Rd", state=""),
            ]
            _file_id, file_row = run_supplier_import(ctx, rows,
                                                     file_label="create")
            ctx.check("file state after a clean file", "done",
                      file_row["state"])

        with ctx.step("Steps 3-7: both partners exist exactly once, ranked "
                      "as vendors, at default hierarchy and active"):
            created = {}
            for key, ref in refs.items():
                ctx.check(f"exactly one partner for ref {key}", 1,
                          rpc.call("res.partner", "search_count",
                                   [("ref", "=", ref),
                                    ("active", "in", [True, False])]))
                created[key] = partner_by_ref(
                    rpc, ref, MAPPED + UNMAPPED + ["id"])
            for key, partner in created.items():
                ctx.check(f"{key} supplier_rank", 1, partner["supplier_rank"])
                ctx.check(f"{key} customer_rank", 0, partner["customer_rank"])
                ctx.check(f"{key} parent_id (no hierarchy set)", False,
                          partner["parent_id"])
                ctx.check(f"{key} active", True, partner["active"])

        with ctx.step("Steps 8-11 (substituted): the new vendor resolves "
                      "through the same name_search the PO dropdown uses, "
                      "and a purchase order saves against it"):
            epsilon = created["a"]
            found = rpc.call("res.partner", "name_search",
                             name=epsilon["name"], limit=10)
            ctx.log(f"name_search -> {found!r}")
            ctx.check_true("the new vendor is offered by name_search",
                           epsilon["id"] in [f[0] for f in found],
                           actual_desc=repr(found))
            if not rpc.model_exists("purchase.order"):
                ctx.log("purchase.order is absent — the PO half is skipped "
                        "on this target")
            else:
                po_id = rpc.create("purchase.order",
                                   {"partner_id": epsilon["id"]})
                saved = rpc.read("purchase.order", [po_id],
                                 ["partner_id", "state"])[0]
                ctx.check("the purchase order saved against the new vendor",
                          epsilon["id"], m2o_id(saved["partner_id"]))

        with ctx.step("Steps 12-13: re-processing the same file creates no "
                      "second partner and leaves supplier_rank at 1 — the "
                      "rank is set on create only"):
            _file_id2, file_row2 = run_supplier_import(ctx, rows,
                                                       file_label="rerun")
            ctx.check("second file state", "done", file_row2["state"])
            for key, ref in refs.items():
                ctx.check(f"still exactly one partner for ref {key}", 1,
                          rpc.call("res.partner", "search_count",
                                   [("ref", "=", ref),
                                    ("active", "in", [True, False])]))
                again = partner_by_ref(rpc, ref)
                ctx.check(f"{key} supplier_rank after the re-run", 1,
                          again["supplier_rank"])
    finally:
        with ctx.step("Cleanup WF-020 fixtures"):
            try:
                if po_id:
                    rpc.call("purchase.order", "unlink", [po_id])
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] purchase order {po_id} not removed: {exc}")
            try:
                sweep_wf020(rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")


@test_case(
    id="TEST-WF020-TC333",
    name="An existing partner matched on ref is overwritten "
         "unconditionally, blanks included",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account_workday", priority="P0", kind="DATA", order=20333,
    description="Same id (written, not recreated); the mapped fields take "
                "the CSV's values INCLUDING blanks; every unmapped field, "
                "child contact and bank account is untouched; no chatter, "
                "no activity; the upsert is idempotent; an empty name fails "
                "its own row leaving that partner unchanged while the good "
                "rows in the same file are written.",
    traceability=trace("DATAONE-TC333"))
def test_tc333(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-020 fixtures and open a fresh "
                  "namespace"):
        sweep_wf020(rpc)

    with ctx.step("Preconditions: transport and supplier usage key"):
        require_sftp_stack(ctx)
        require_supplier_usage(ctx)

    try:
        with ctx.step("Seed a fully populated partner, plus a child contact "
                      "and a bank account the CSV does not carry"):
            ref = ref_for("001")
            partner_id = rpc.create("res.partner", {
                "name": fx(f"{MARK} Vendor Gamma"),
                "ref": ref,
                "street": "1 Original St", "street2": "Bldg 7",
                "city": "Austin", "zip": "78701",
                "phone": "+1 512 555 0000",
                "email": "gamma.qa@example.invalid",
                "website": "https://example.invalid",
                "vat": False,
                "comment": "QA seed — must survive the import untouched",
            })
            child_id = rpc.create("res.partner", {
                "name": fx(f"{MARK} Gamma Child"),
                "parent_id": partner_id, "type": "delivery"})
            bank_id = None
            if rpc.model_exists("res.partner.bank"):
                bank_id = rpc.create("res.partner.bank", {
                    "acc_number": f"QA-{MARK}-0001",
                    "partner_id": partner_id})

        with ctx.step("Steps 1-2: dump every column and record the child / "
                      "bank ids"):
            before = partner_by_ref(rpc, ref, MAPPED + UNMAPPED + ["id"])
            messages_before = rpc.call(
                "mail.message", "search_count",
                [("model", "=", "res.partner"), ("res_id", "=", partner_id)])
            ctx.log(f"before: {before!r}; child={child_id} bank={bank_id}; "
                    f"{messages_before} chatter message(s)")

        with ctx.step("Step 3: process one row that renames the partner and "
                      "sends a BLANK street2"):
            row = supplier_row(ref, fx(f"{MARK} Vendor Gamma Renamed"),
                               street="2200 Market St", street2="",
                               city="Philadelphia", zip_code="19103",
                               phone="+1 215 555 0102", state="")
            _file_id, file_row = run_supplier_import(ctx, [row],
                                                     file_label="overwrite")
            ctx.check("file state", "done", file_row["state"])

        with ctx.step("Step 4: the partner's id is unchanged — it was "
                      "updated, not deleted and recreated"):
            after = partner_by_ref(rpc, ref, MAPPED + UNMAPPED + ["id"])
            ctx.check("partner id", partner_id, after["id"])

        with ctx.step("Step 5: the mapped fields took the CSV's values"):
            ctx.check("mapped values", {
                "name": row["name"], "street": "2200 Market St",
                "city": "Philadelphia", "zip": "19103",
                "phone": "+1 215 555 0102"},
                {k: after[k] for k in
                 ("name", "street", "city", "zip", "phone")})

        with ctx.step("Step 6 — THE DESTRUCTIVE ASSERTION: street2 is now "
                      "empty, overwriting 'Bldg 7'"):
            ctx.check("street2 after an unconditional blank write", False,
                      after["street2"])

        with ctx.step("Step 7: every unmapped field is untouched — diff "
                      "column by column"):
            diffs = {k: {"before": before.get(k), "after": after.get(k)}
                     for k in UNMAPPED if before.get(k) != after.get(k)}
            ctx.check("unmapped field differences", {}, diffs)

        with ctx.step("Step 8: the child contact and bank account are "
                      "unchanged"):
            child = rpc.read("res.partner", [child_id],
                             ["name", "parent_id", "type"])[0]
            ctx.check("child contact parent", partner_id,
                      m2o_id(child["parent_id"]))
            ctx.check("child contact name", fx(f"{MARK} Gamma Child"),
                      child["name"])
            if bank_id:
                bank = rpc.read("res.partner.bank", [bank_id],
                                ["acc_number", "partner_id"])[0]
                ctx.check("bank account still on the partner", partner_id,
                          m2o_id(bank["partner_id"]))

        with ctx.step("Steps 9-10: nothing was written to the partner's "
                      "chatter and no activity was created on it"):
            messages_after = rpc.call(
                "mail.message", "search_count",
                [("model", "=", "res.partner"), ("res_id", "=", partner_id)])
            ctx.check("chatter messages added by the import", 0,
                      messages_after - messages_before)
            ctx.check("activities on the partner", [],
                      activities_on(rpc, "res.partner", [partner_id]))

        with ctx.step("Step 11: re-processing the identical row leaves the "
                      "partner byte-identical"):
            run_supplier_import(ctx, [row], file_label="idempotent")
            again = partner_by_ref(rpc, ref, MAPPED + UNMAPPED + ["id"])
            diffs = {k: {"first": after.get(k), "second": again.get(k)}
                     for k in MAPPED + UNMAPPED
                     if after.get(k) != again.get(k)}
            ctx.check("differences after the idempotent re-run", {}, diffs)

        with ctx.step("Step 12: a row whose optional columns are all blank "
                      "blanks all five on the partner"):
            blank_row = supplier_row(ref, fx(f"{MARK} Vendor Gamma Blanked"),
                                     street="", street2="", city="",
                                     zip_code="", phone="", state="")
            run_supplier_import(ctx, [blank_row], file_label="blanks")
            blanked = partner_by_ref(rpc, ref)
            ctx.check("all five optional columns blanked",
                      {"street": False, "street2": False, "city": False,
                       "zip": False, "phone": False},
                      {k: blanked[k] for k in
                       ("street", "street2", "city", "zip", "phone")})

        with ctx.step("Steps 13-14: an empty name fails ONLY its own row — "
                      "that partner is unchanged while the good row in the "
                      "same file is written"):
            good_ref = ref_for("020")
            state_before = partner_by_ref(rpc, ref,
                                          MAPPED + UNMAPPED + ["id"])
            mixed = [
                supplier_row(ref, "", street="Should Not Be Applied",
                             state=""),
                supplier_row(good_ref, fx(f"{MARK} Vendor Good"),
                             street="9 Good Rd", state=""),
            ]
            file_id, file_row = run_supplier_import(ctx, mixed,
                                                    file_label="mixed")
            ctx.check("file state with one failing row", "failed",
                      file_row["state"])
            notes = [a.get("note") or "" for a in rpc.search_read(
                "mail.activity",
                [("res_model", "=", "sftp.file"), ("res_id", "=", file_id)],
                ["note"])]
            ctx.check_true(f"the row error names {NAME_MISSING!r}",
                           any(NAME_MISSING in n for n in notes),
                           actual_desc=str(notes)[:400])
            unchanged = partner_by_ref(rpc, ref, MAPPED + UNMAPPED + ["id"])
            diffs = {k: {"before": state_before.get(k),
                         "after": unchanged.get(k)}
                     for k in MAPPED + UNMAPPED
                     if state_before.get(k) != unchanged.get(k)}
            ctx.check("the empty-name row changed nothing on its partner",
                      {}, diffs)
            good = partner_by_ref(rpc, good_ref)
            ctx.check_true("the good row in the same file was written",
                           good is not None and good["street"] == "9 Good Rd",
                           actual_desc=repr(good))
    finally:
        with ctx.step("Cleanup WF-020 fixtures"):
            try:
                sweep_wf020(rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")
