"""DATAONE-WF-001 — how it fails, and what it quietly duplicates:
TC340, TC341, TC343.

TC340 — **all-or-nothing per file (BR-11).** Unlike the payment and
supplier flows, which keep their good rows, ONE bad row here costs every
requisition in the file — so a single malformed line from Workday can stop
a whole morning's sales intake. That is defensible (a requisition file is a
coherent business document and a half-imported one would be worse than
none) but it should be a STATED design choice, because it differs from
every other inbound flow in this suite. Steps 8-12 are the case.

The error message is also unusually informative and unusually leaky.
``_prepare_log_message`` decorates every raise as ``'{message} at row
{data_line}'`` (``sale_order.py:57-61``) — dumping the **entire offending
row dict** into the activity body, requester name and email address
included. Step 7 records that as a data-exposure observation, not a
functional failure: the ``sftp.file`` ACL grants every internal user full
CRUD, so anyone who can open SFTP → Files can read it. Either tighten the
ACL or redact the dump.

TC341 — **the one value that cannot be invented.** Every other unknown in
this file auto-creates something: an unknown item creates a product, an
unknown project creates an analytic account, an unknown address creates a
contact. An empty ``Ship-To_Contact`` is the one that raises. The case also
pins the country normalisation, and step 9 is the one likely to produce a
finding: the rule is *blank, or any value CONTAINING "United States"*
(``sale_order.py:93-96``), so ``USA``, ``US`` and ``United States of
America`` all take the un-normalised path.

TC343 — **the address typo that silently duplicates a customer.** The
partner lookup is an exact match on the name AND every address field
simultaneously (``sale_order.py:110-114``), so any inconsistency in
Workday's data — a trailing space, ``Ste 20`` versus ``Suite 20``, a
changed ZIP — produces a NEW contact rather than matching. Over time the
address book fills with near-duplicate customers, each with its own order
history, which breaks customer-level reporting and credit control. P2
because nothing is lost; the damage is cumulative.

Step 8's cumulative count is the case's headline result, and step 10's
query is what turns the hypothesis into a fact. The workbook is explicit
about how to use it: run ``SELECT name, count(*) FROM res_partner GROUP BY
name HAVING count(*) > 1`` against the live database first — if the answer
is "dozens" this is a P1 data-quality problem the upgrade should fix; if it
is "none", the client's Workday data is consistent and the behaviour can be
carried as-is.

EXPECTED v17 OUTCOME: PASS for all three, with TC341 step 9's and TC343
step 8's answers recorded.
EXPECTED v19 OUTCOME: the same. ``res.partner`` search semantics and
``res.country.state`` resolution are unchanged as far as delta §2 records;
the exposure is inherited (the module must import at all, E5), which
``dto_sale_workday``'s own tests report as discharged.
"""
from framework.registry import test_case
from tests.wf001.common import (ACTIVITY_TYPE_XMLID,  # noqa: F401
                                ERR_NO_CONTACT, ERR_NO_ITEM,
                                FILE_ACTIVITY_SUMMARY, MARK, ROW_DECORATION,
                                SUPERUSER_ID, WORKFLOW, WORKFLOW_NAME,
                                activities_on, analytic_name, any_uom,
                                contact_name, file_message, fx, item_code,
                                m2o_id, memo, order_lines, order_type_labels,
                                orders_for, population_counts,
                                require_import_prerequisites,
                                require_mail_offline,
                                require_requisition_import, row, run_import,
                                state_and_country, sweep_wf001, trace)
from tests.wf001.test_requisition_gate import (_ensure_contact,
                                               _ensure_known_product)


def _three_rows(ctx, uom_name, label, contact, state_name, item_known,
                item_unknown):
    """REQ-1 with two lines and REQ-2 with one — TD-WD-01's shape."""
    common = dict(uom_name=uom_name, contact=contact, street="500 Main St",
                  city="Austin", state=state_name, zip_code="78701",
                  order_type_label=label,
                  project=analytic_name("PRJ-NEW-ALPHA"),
                  contract=analytic_name("CC-ALPHA-2026"))
    return [
        row(requisition_num=memo("REQ-1"), internal_memo=memo("IM-1"),
            item=item_known, description=fx(f"{MARK} Known"),
            quantity="2", unit_price="10.0", **common),
        row(requisition_num=memo("REQ-1"), internal_memo=memo("IM-1"),
            item=item_unknown, description=fx(f"{MARK} Unknown widget"),
            quantity="5", unit_price="3.50", **common),
        row(requisition_num=memo("REQ-2"), internal_memo=memo("IM-2"),
            item=item_known, description=fx(f"{MARK} Known"),
            quantity="1", unit_price="10.0", **common),
    ]


@test_case(
    id="TEST-WF001-TC340",
    name="Empty Item fails the whole file with the offending row dumped "
         "into the activity",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_sale_workday", priority="P1", kind="API", order=1340,
    description="One row with an empty Item fails the ENTIRE file: zero "
                "orders, zero partners, zero products and zero analytic "
                "accounts created — including for the requisition that "
                "contained no bad row and for the good rows' master data. "
                "Asserts the file Failed with the superuser activity "
                "carrying 'Item is empty' decorated with the full offending "
                "row dict, records the requester email inside that dump as "
                "a data-exposure observation, and proves the fixed file "
                "then processes fully.",
    traceability=trace("DATAONE-TC340"))
def test_tc340(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-001 fixtures and open a fresh "
                  "namespace"):
        sweep_wf001(rpc)

    with ctx.step("Preconditions"):
        require_requisition_import(ctx)
        require_import_prerequisites(ctx)
        require_mail_offline(ctx)
        labels = order_type_labels(ctx)
        uom_name = any_uom(ctx)
        state_row, country_row = state_and_country(ctx)
        label = sorted(labels)[0]

    with ctx.step("Step 1: record the four token-scoped counts, and verify "
                  "that none of what the good rows would create exists yet"):
        contact = contact_name("Alpha")
        known = item_code("FG-CABLE-001")
        unknown = item_code("UNKNOWN-ITEM-9")
        _ensure_known_product(ctx, known)
        _ensure_contact(ctx, contact, "500 Main St", "Suite 20", "Austin",
                        state_row, country_row, "78701")
        rows = _three_rows(ctx, uom_name, label, contact, state_row["name"],
                           known, unknown)
        rows[1]["Item"] = ""          # the TD-WD-01-E2 variant: row 2 only
        before = population_counts(rpc)
        ctx.log(f"starting token-scoped population: {before!r}")
        ctx.check("no order exists for either requisition yet", [],
                  rpc.search("sale.order",
                             [("origin", "in", [memo("REQ-1"),
                                                memo("REQ-2")]),
                              ("active", "in", [True, False])]))
        ctx.check("the unknown item does not exist", [],
                  rpc.search("product.product",
                             [("default_code", "=", unknown),
                              ("active", "in", [True, False])]))
        ctx.check("and neither analytic account", [],
                  rpc.search("account.analytic.account",
                             [("name", "in",
                               [analytic_name("PRJ-NEW-ALPHA"),
                                analytic_name("CC-ALPHA-2026")]),
                              ("active", "in", [True, False])]))

    with ctx.step("Steps 2-4: the file Failed with process_date stamped and "
                  "the superuser warning activity"):
        folder_id, file_id, file_row = run_import(ctx, rows,
                                                  file_label="E2_empty_item")
        ctx.log(f"sftp.file: {file_row!r}")
        ctx.check("state", "failed", file_row["state"])
        ctx.check_true("process_date stamped", bool(file_row["process_date"]),
                       actual_desc=repr(file_row["process_date"]))
        acts = activities_on(rpc, "sftp.file", [file_id])
        ctx.log(f"file-level activities: {acts!r}")
        ctx.check("exactly one", 1, len(acts))
        activity = acts[0] if acts else {}
        ctx.check("summary", FILE_ACTIVITY_SUMMARY, activity.get("summary"))
        ctx.check("type", rpc.ref(ACTIVITY_TYPE_XMLID),
                  m2o_id(activity.get("activity_type_id")))
        ctx.check("assigned to SUPERUSER_ID — the id, not merely 'set'",
                  SUPERUSER_ID, m2o_id(activity.get("user_id")))
        ctx.check("deadline equals the process date",
                  str(file_row["process_date"])[:10],
                  str(activity.get("date_deadline")))

    with ctx.step("Steps 5-6: the message is 'Item is empty' decorated as "
                  "'{message} at row {data_line}', with the ENTIRE "
                  "offending row dict present. Quoted verbatim"):
        message = file_message(rpc, file_id)
        ctx.log(f"activity body, VERBATIM: {message!r}")
        ctx.check_true(f"it carries {ERR_NO_ITEM!r}",
                       ERR_NO_ITEM in message, actual_desc=message)
        ctx.check_true(f"decorated with {ROW_DECORATION!r}",
                       ROW_DECORATION in message, actual_desc=message)
        ctx.check_true(
            "and the whole row dict is dumped in — several of the 23 "
            "column names appear in the body, which is what makes it a "
            "dict rather than a single value",
            sum(1 for column in ("Requisition_Num", "Ship-To_Contact",
                                 "Item_Description", "Unit_Price")
                if column in message) >= 3,
            actual_desc=message)
        ctx.check_true(
            "and it names the requisition that failed, so an administrator "
            "can tell Workday which record to fix",
            memo("REQ-1") in message, actual_desc=message)

    with ctx.step("Step 7: DATA-EXPOSURE OBSERVATION — the dump carries the "
                  "requester's email address, and the sftp.file ACL grants "
                  "every internal user full CRUD"):
        ctx.check_true(
            "the requester's email address is in the activity body",
            "jane.requester@example.com" in message, actual_desc=message)
        acl = rpc.search_read(
            "ir.model.access", [("model_id.model", "=", "sftp.file")],
            ["name", "group_id", "perm_read", "perm_write", "perm_create",
             "perm_unlink"]) if rpc.model_exists("ir.model.access") else []
        ctx.log(f"ACL rows on sftp.file: {acl!r}")
        ctx.log("This is an observation to RAISE, not a functional failure: "
                "the row dump is genuinely useful for diagnosis and it puts "
                "requester names and email addresses into a record that "
                "every internal user can read. Take it to whoever owns data "
                "protection; either tighten the ACL or redact the dump. "
                "Both are cheap and the choice is theirs.")

    with ctx.step("Steps 8-12: THE ALL-OR-NOTHING ASSERTION. NOTHING was "
                  "committed — not an order for REQ-2, which contained no "
                  "bad row, and not the master data the GOOD rows would "
                  "have auto-created"):
        after = population_counts(rpc)
        ctx.log(f"population before: {before!r}")
        ctx.log(f"population after:  {after!r}")
        ctx.check("zero sale.order records were created, including for "
                  "REQ-2", [],
                  rpc.search("sale.order",
                             [("origin", "in", [memo("REQ-1"),
                                                memo("REQ-2")]),
                              ("active", "in", [True, False])]))
        ctx.check("no product.product was created — including none for the "
                  "unknown item the second good row would have created", [],
                  rpc.search("product.product",
                             [("default_code", "=", unknown),
                              ("active", "in", [True, False])]))
        ctx.check("no account.analytic.account was created", [],
                  rpc.search("account.analytic.account",
                             [("name", "in",
                               [analytic_name("PRJ-NEW-ALPHA"),
                                analytic_name("CC-ALPHA-2026")]),
                              ("active", "in", [True, False])]))
        ctx.check("every token-scoped count is unchanged", before, after)
        ctx.log("BR-11, and it should be a STATED design choice rather than "
                "an implementation accident: this flow differs from every "
                "other inbound flow in this suite — WF-019 and WF-020 both "
                "keep their good rows. Confirm with the Sales Manager that "
                "a whole-file failure is what they want when Workday sends "
                "fifty requisitions and one is malformed.")

    with ctx.step("Step 13: the remote archive is NOT observable here — "
                  "recorded. The download and the processing are separate "
                  "transactions, so a file that fails processing has "
                  "already been archived and is never moved back"):
        ctx.log("SFTPConnection.move_files runs inside "
                "sftp.folder.action_get_files against a live endpoint "
                "(convention rule 4).")

    with ctx.step("Step 15: Re-processing WITHOUT correcting anything "
                  "achieves nothing — it fails again with the same message"):
        rpc.call("sftp.file", "action_retry_process_sftp_files", [file_id])
        retried = rpc.read("sftp.file", [file_id],
                           ["state", "process_date"])[0]
        ctx.log(f"after Re-process: {retried!r}")
        ctx.check("still Failed", "failed", retried["state"])
        ctx.check_true("with the same message",
                       ERR_NO_ITEM in file_message(rpc, file_id),
                       actual_desc=file_message(rpc, file_id))
        ctx.check("and still nothing created", before,
                  population_counts(rpc))

    with ctx.step("Step 14: fix the row, place the corrected file, and "
                  "assert it now processes fully and creates BOTH orders"):
        fixed = [dict(entry) for entry in rows]
        fixed[1]["Item"] = unknown
        _f, fixed_id, fixed_row = run_import(ctx, fixed, folder_id=folder_id,
                                             file_label="E2_corrected")
        ctx.log(f"corrected file: {fixed_row!r}")
        ctx.check("it processes", "done", fixed_row["state"])
        created = orders_for(rpc, [memo("REQ-1"), memo("REQ-2")])
        ctx.check("and creates both orders", 2, len(created))
        ctx.check("with the unknown item now auto-created", 1,
                  len(rpc.search("product.product",
                                 [("default_code", "=", unknown),
                                  ("active", "in", [True, False])])))


@test_case(
    id="TEST-WF001-TC341",
    name="Empty Ship-To_Contact fails the whole file with the offending "
         "row dumped",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_sale_workday", priority="P1", kind="API", order=1341,
    description="An empty Ship-To_Contact — the one value in the file that "
                "cannot be invented — fails the whole file with its message "
                "quoted and the row dumped, creating no order and no "
                "partner. Then pins the country normalisation across blank, "
                "'United States', 'USA' and an unknown state, records what "
                "each actually does, and proves the full-address match "
                "reuses an existing contact while a one-character "
                "difference does not.",
    traceability=trace("DATAONE-TC341"))
def test_tc341(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-001 fixtures and open a fresh "
                  "namespace"):
        sweep_wf001(rpc)

    with ctx.step("Preconditions"):
        require_requisition_import(ctx)
        require_import_prerequisites(ctx)
        require_mail_offline(ctx)
        labels = order_type_labels(ctx)
        uom_name = any_uom(ctx)
        state_row, country_row = state_and_country(ctx)
        label = sorted(labels)[0]
        known = item_code("FG-CABLE-001")
        _ensure_known_product(ctx, known)

    findings = {}

    with ctx.step("Steps 1-5: an empty Ship-To_Contact on row 3 fails the "
                  "WHOLE file — zero orders, including for REQ-1 whose rows "
                  "were both valid — and zero partners"):
        contact = contact_name("Alpha")
        _ensure_contact(ctx, contact, "500 Main St", "Suite 20", "Austin",
                        state_row, country_row, "78701")
        rows = _three_rows(ctx, uom_name, label, contact, state_row["name"],
                           known, item_code("UNKNOWN-1"))
        rows[2]["Ship-To_Contact"] = ""       # the TD-WD-01-E1 variant
        before = population_counts(rpc)
        ctx.log(f"starting token-scoped population: {before!r}")
        folder_id, file_id, file_row = run_import(
            ctx, rows, file_label="E1_empty_contact")
        ctx.log(f"sftp.file: {file_row!r}")
        ctx.check("the file Failed", "failed", file_row["state"])
        ctx.check("zero orders created, including for REQ-1", [],
                  rpc.search("sale.order",
                             [("origin", "in", [memo("REQ-1"),
                                                memo("REQ-2")]),
                              ("active", "in", [True, False])]))
        ctx.check("every token-scoped count unchanged", before,
                  population_counts(rpc))
        acts = activities_on(rpc, "sftp.file", [file_id])
        ctx.check("one superuser activity", 1, len(acts))
        ctx.check("assigned to SUPERUSER_ID", SUPERUSER_ID,
                  m2o_id(acts[0].get("user_id")) if acts else None)

    with ctx.step("Steps 6-7: the message is _get_partner_id's raise, "
                  "decorated and with the row dumped — and the dump names "
                  "the requisition that failed"):
        message = file_message(rpc, file_id)
        ctx.log(f"activity body, VERBATIM: {message!r}")
        ctx.check_true(f"it carries {ERR_NO_CONTACT!r}",
                       ERR_NO_CONTACT in message, actual_desc=message)
        ctx.check_true(f"decorated with {ROW_DECORATION!r}",
                       ROW_DECORATION in message, actual_desc=message)
        ctx.check_true(
            "and REQ-2 appears in the dump, so an administrator can tell "
            "Workday which record to fix",
            memo("REQ-2") in message, actual_desc=message)

    def _country_variant(label_, country_value, requisition):
        """Process one row and report the partner it resolved."""
        variant_contact = contact_name(f"Ctry-{label_}")
        rows_ = [row(requisition_num=requisition,
                     internal_memo=requisition,
                     order_type_label=label, uom_name=uom_name,
                     contact=variant_contact, street="700 Third St",
                     street2="", city="Austin", state=state_row["name"],
                     zip_code="78702", country=country_value,
                     item=known, description=fx(f"{MARK} Known"),
                     quantity="1", unit_price="10.0",
                     project=analytic_name("PRJ-NEW-ALPHA"),
                     contract=analytic_name("CC-ALPHA-2026"))]
        _f, vid, vrow = run_import(ctx, rows_, folder_id=folder_id,
                                   file_label=f"country_{label_}")
        partners = rpc.search_read(
            "res.partner", [("name", "=", variant_contact),
                            ("active", "in", [True, False])],
            ["name", "country_id", "state_id", "zip"], order="id")
        result = {
            "file_state": vrow["state"],
            "partner_created": len(partners),
            "country": (partners[0]["country_id"][1]
                        if partners and partners[0]["country_id"] else ""),
            "state": (partners[0]["state_id"][1]
                      if partners and partners[0]["state_id"] else ""),
        }
        findings[f"Ship-To_Country={country_value!r}"] = result
        ctx.log(f"{label_}: country={country_value!r} -> {result!r}; "
                f"message={file_message(rpc, vid)!r}")
        return result

    with ctx.step("Step 8: E1b — a BLANK country normalises to United "
                  "States and the row succeeds (sale_order.py:93-96)"):
        blank = _country_variant("blank", "", memo("REQ-CB"))
        ctx.check("the file processed", "done", blank["file_state"])
        ctx.check("one partner was created", 1, blank["partner_created"])
        ctx.check("with the country normalised to United States",
                  country_row["name"], blank["country"])

    with ctx.step("Step 8b: the literal 'United States' behaves identically"):
        literal = _country_variant("united_states", country_row["name"],
                                   memo("REQ-CU"))
        ctx.check("same outcome as the blank case",
                  (blank["file_state"], blank["country"]),
                  (literal["file_state"], literal["country"]))

    with ctx.step("Step 9: E1c — 'USA'. THE LIKELY FINDING: the rule is "
                  "'blank, or any value CONTAINING \"United States\"', and "
                  "'USA' contains neither — so it takes the un-normalised "
                  "path. Whether it then resolves depends on Odoo's own "
                  "state matching"):
        usa = _country_variant("usa", "USA", memo("REQ-CX"))
        ctx.log(f"'USA' outcome: {usa!r}")
        ctx.check_true(
            "the outcome is RECORDED either way — if the country came back "
            "empty, a Workday feed emitting 'USA' silently produces "
            "contacts with no country and no state, and every shipping "
            "address is incomplete with nothing raised",
            usa["file_state"] in ("done", "failed"),
            actual_desc=repr(usa))
        if usa["country"] != country_row["name"]:
            ctx.log("[finding] 'USA' did NOT normalise. Ask the client's "
                    "Workday team which values that column actually emits, "
                    "and pin the normalisation to THAT SET rather than to a "
                    "substring test. 'USA', 'US' and 'United States of "
                    "America' all take the un-normalised path today.")

    with ctx.step("Step 10: E1a — an UNKNOWN state. Record whether it fails "
                  "the file or is silently dropped"):
        unknown_state_contact = contact_name("BadState")
        rows_ = [row(requisition_num=memo("REQ-CS"),
                     internal_memo=memo("REQ-CS"),
                     order_type_label=label, uom_name=uom_name,
                     contact=unknown_state_contact, street="800 Fourth St",
                     street2="", city="Austin",
                     state=fx(f"{MARK} Nowheresville"), zip_code="78703",
                     item=known, description=fx(f"{MARK} Known"),
                     quantity="1", unit_price="10.0",
                     project=analytic_name("PRJ-NEW-ALPHA"),
                     contract=analytic_name("CC-ALPHA-2026"))]
        _f, sid, srow = run_import(ctx, rows_, folder_id=folder_id,
                                   file_label="unknown_state")
        partners = rpc.search_read(
            "res.partner", [("name", "=", unknown_state_contact),
                            ("active", "in", [True, False])],
            ["state_id", "country_id"], order="id")
        ctx.log(f"unknown state: file={srow['state']!r}, "
                f"partners={partners!r}")
        ctx.check(
            "an unknown state is SILENTLY DROPPED rather than failing the "
            "file — _get_partner_id stores `state and state.id or False` "
            "(sale_order.py:106-107), so the contact is created with no "
            "state AND no country, because the country is derived from the "
            "state",
            "done", srow["state"])
        if partners:
            ctx.check("the partner has no state", False,
                      bool(m2o_id(partners[0]["state_id"])))
            ctx.check("and no country either — the country comes from "
                      "state.country_id, so losing the state loses both",
                      False, bool(m2o_id(partners[0]["country_id"])))
            findings["unknown state"] = "silently dropped; no state, no country"

    with ctx.step("Step 11: the partner-matching rule — an EXACT match on "
                  "the name AND every address field reuses the existing "
                  "contact"):
        reuse_contact = contact_name("Reuse")
        existing = _ensure_contact(ctx, reuse_contact, "900 Fifth St",
                                   "Unit 3", "Austin", state_row,
                                   country_row, "78704")
        rows_ = [row(requisition_num=memo("REQ-RE"),
                     internal_memo=memo("REQ-RE"),
                     order_type_label=label, uom_name=uom_name,
                     contact=reuse_contact, street="900 Fifth St",
                     street2="Unit 3", city="Austin",
                     state=state_row["name"], zip_code="78704",
                     item=known, description=fx(f"{MARK} Known"),
                     quantity="1", unit_price="10.0",
                     project=analytic_name("PRJ-NEW-ALPHA"),
                     contract=analytic_name("CC-ALPHA-2026"))]
        _f, rid, rrow = run_import(ctx, rows_, folder_id=folder_id,
                                   file_label="reuse")
        ctx.check("the file processed", "done", rrow["state"])
        matches = rpc.search("res.partner",
                             [("name", "=", reuse_contact),
                              ("active", "in", [True, False])])
        ctx.log(f"partners named {reuse_contact!r}: {matches!r}")
        ctx.check("still exactly one — the existing contact was reused",
                  [existing], matches)
        order = orders_for(rpc, [memo("REQ-RE")])
        ctx.check("and the order points at it", existing,
                  m2o_id(order[0]["partner_id"]) if order else None)

    with ctx.step("Step 12: the NEGATIVE of step 11 — one character "
                  "different in Ship-To_Street creates a NEW partner. "
                  "TC343 develops this"):
        rows_[0]["Ship-To_Street"] = "900 Fifth Street"
        rows_[0]["Requisition_Num"] = memo("REQ-NEW")
        rows_[0]["Internal_Memo"] = memo("REQ-NEW")
        _f, nid, nrow = run_import(ctx, rows_, folder_id=folder_id,
                                   file_label="near_miss")
        ctx.check("the file processed", "done", nrow["state"])
        matches = rpc.search("res.partner",
                             [("name", "=", reuse_contact),
                              ("active", "in", [True, False])])
        ctx.log(f"partners named {reuse_contact!r} after the near miss: "
                f"{matches!r}")
        ctx.check("a SECOND partner with the same name now exists", 2,
                  len(matches))

    with ctx.step("Step 13: fix the empty contact and reprocess — both "
                  "orders are created"):
        rows = _three_rows(ctx, uom_name, label, contact, state_row["name"],
                           known, item_code("UNKNOWN-1"))
        _f, fixed_id, fixed_row = run_import(ctx, rows, folder_id=folder_id,
                                             file_label="E1_corrected")
        ctx.check("it processes", "done", fixed_row["state"])
        ctx.check("and creates both orders", 2,
                  len(orders_for(rpc, [memo("REQ-1"), memo("REQ-2")])))

    with ctx.step("The normalisation table — the case's recorded output"):
        for variant, result in findings.items():
            ctx.log(f"  {variant} -> {result!r}")


@test_case(
    id="TEST-WF001-TC343",
    name="An address typo silently auto-creates a second ship-to contact",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_sale_workday", priority="P2", kind="API", order=1343,
    description="Processes six near-miss variants of one ship-to address — "
                "identical, a trailing space, an abbreviation, a longer ZIP, "
                "a case difference in the contact name and a case "
                "difference in the city — and records for each whether a "
                "NEW partner was created. The cumulative count is the "
                "case's headline result. Also asserts that nothing warns "
                "anybody and that the resulting orders are split across "
                "several partner ids, so the customer's total order value "
                "is understated on each.",
    traceability=trace("DATAONE-TC343"))
def test_tc343(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-001 fixtures and open a fresh "
                  "namespace"):
        sweep_wf001(rpc)

    with ctx.step("Preconditions"):
        require_requisition_import(ctx)
        require_import_prerequisites(ctx)
        require_mail_offline(ctx)
        labels = order_type_labels(ctx)
        uom_name = any_uom(ctx)
        state_row, country_row = state_and_country(ctx)
        label = sorted(labels)[0]
        known = item_code("FG-CABLE-001")
        _ensure_known_product(ctx, known)

    with ctx.step("Step 1: TD-PA-01 exists with the exact address, and "
                  "exactly one partner carries that name"):
        contact = contact_name("Alpha")
        base = dict(street="500 Main St", street2="Suite 20", city="Austin",
                    state=state_row["name"], zip_code="78701")
        original = _ensure_contact(ctx, contact, base["street"],
                                   base["street2"], base["city"], state_row,
                                   country_row, base["zip_code"])
        ctx.log(f"TD-PA-01 equivalent: partner {original} named "
                f"{contact!r} at {base!r}")
        ctx.check("exactly one partner carries that name", [original],
                  rpc.search("res.partner",
                             [("name", "=", contact),
                              ("active", "in", [True, False])]))

    folder_id = None
    outcomes = {}
    order_partners = {}

    def _variant(tag, **over):
        nonlocal folder_id
        values = dict(base)
        variant_contact = over.pop("contact", contact)
        values.update(over)
        requisition = memo(f"REQ-{tag}")
        rows_ = [row(requisition_num=requisition, internal_memo=requisition,
                     order_type_label=label, uom_name=uom_name,
                     contact=variant_contact, item=known,
                     description=fx(f"{MARK} Known"), quantity="1",
                     unit_price="10.0",
                     project=analytic_name("PRJ-ALPHA"),
                     contract=analytic_name("CC-ALPHA"), **values)]
        folder_id, vid, vrow = run_import(
            ctx, rows_, folder_id=folder_id, file_label=f"addr_{tag}")
        matching = rpc.search("res.partner",
                              [("name", "ilike", contact.strip()),
                               ("active", "in", [True, False])])
        order = orders_for(rpc, [requisition])
        partner = m2o_id(order[0]["partner_id"]) if order else None
        outcomes[tag] = {
            "file_state": vrow["state"],
            "partners_named_alpha": len(matching),
            "order_partner": partner,
            "reused_original": partner == original,
        }
        order_partners[tag] = partner
        ctx.log(f"{tag}: {outcomes[tag]!r}; message="
                f"{file_message(rpc, vid)!r}")
        return outcomes[tag]

    with ctx.step("Step 2: A1 — identical. No new partner; the order points "
                  "at TD-PA-01"):
        a1 = _variant("A1")
        ctx.check("the file processed", "done", a1["file_state"])
        ctx.check("the original was reused", True, a1["reused_original"])
        ctx.check("and still only one partner carries the name", 1,
                  a1["partners_named_alpha"])

    with ctx.step("Step 3: A2 — a TRAILING SPACE in Ship-To_Street. "
                  "_get_partner_id applies .strip() to street, street2 and "
                  "city before searching (sale_order.py:103-105), so record "
                  "whether that saves it"):
        a2 = _variant("A2", street="500 Main St ")
        ctx.check(
            "the trailing space is STRIPPED, so the original is still "
            "reused — the three stripped fields are the only protection "
            "this matching has", True, a2["reused_original"])

    with ctx.step("Step 4: A3 — 'Ste 20' instead of 'Suite 20'. A genuinely "
                  "different string cannot match"):
        a3 = _variant("A3", street2="Ste 20")
        ctx.check("a NEW partner was created", False,
                  a3["reused_original"])
        ctx.check("so two now carry the name", 2,
                  a3["partners_named_alpha"])

    with ctx.step("Steps 5-6: the new partner carries the file's address "
                  "and is otherwise a BARE contact — no supplier rank, no "
                  "payment terms, no note explaining its origin — and the "
                  "order points at it, not at TD-PA-01"):
        new_partner = a3["order_partner"]
        detail = rpc.read("res.partner", [new_partner],
                          ["name", "street", "street2", "city", "zip",
                           "state_id", "country_id", "supplier_rank",
                           "customer_rank", "comment"])[0]
        ctx.log(f"the auto-created near-duplicate: {detail!r}")
        ctx.check("its street2 is the file's value", "Ste 20",
                  detail["street2"])
        ctx.check("it has no supplier rank", 0, detail["supplier_rank"] or 0)
        ctx.check("and no note explaining where it came from", False,
                  detail["comment"] or False)
        ctx.check("the order points at the NEW partner", new_partner,
                  a3["order_partner"])

    with ctx.step("Step 7: A4, A5 and A6 — a longer ZIP, a case difference "
                  "in the contact NAME, and a case difference in the city"):
        a4 = _variant("A4", zip_code="78701-1234")
        ctx.check("a longer ZIP creates a new partner", False,
                  a4["reused_original"])
        a5 = _variant("A5", contact=contact.replace("Customer", "customer"))
        ctx.log(f"A5 (lower-case contact name) -> {a5!r}")
        a6 = _variant("A6", city="austin")
        ctx.log(f"A6 (lower-case city) -> {a6!r}")
        ctx.check_true(
            "the name and city comparisons are CASE-SENSITIVE — the domain "
            "uses '=' and not '=ilike' on every field except the state "
            "(sale_order.py:111-113), so a case difference anywhere "
            "produces a new contact",
            not a5["reused_original"] and not a6["reused_original"],
            actual_desc=f"A5 reused={a5['reused_original']}, "
                        f"A6 reused={a6['reused_original']}")

    with ctx.step("Step 8: THE HEADLINE RESULT — the cumulative count after "
                  "all six variants"):
        final = rpc.search("res.partner",
                           [("name", "ilike", contact.strip()),
                            ("active", "in", [True, False])])
        ctx.log("variant outcomes:")
        for tag in sorted(outcomes):
            ctx.log(f"  {tag}: {outcomes[tag]!r}")
        ctx.log(f"partners matching {contact.strip()!r} "
                f"case-insensitively after six variants: {len(final)} "
                f"({final!r})")
        ctx.check_true(
            "six near-miss variants of ONE customer address produced "
            "several near-duplicate partners. That number is what to take "
            "to the client",
            len(final) > 1, actual_desc=f"{len(final)} partners")

    with ctx.step("Step 9: NOTHING WARNS ANYBODY. No activity, no chatter "
                  "message, no log entry — and every file reads Done"):
        ctx.check("every variant's file reached Done",
                  {"done"}, {entry["file_state"]
                             for entry in outcomes.values()})
        ctx.check("no activity on any of the created partners", [],
                  activities_on(rpc, "res.partner", final))
        orders = orders_for(rpc, [memo(f"REQ-{tag}")
                                  for tag in sorted(outcomes)])
        ctx.check("no activity on any of the created orders", [],
                  activities_on(rpc, "sale.order",
                                [order["id"] for order in orders]))
        logs = rpc.search("sftp.log", [("res_model", "=", "sftp.file")],
                          limit=5) if rpc.model_exists("sftp.log") else []
        ctx.log(f"recent sftp.log rows (for the record): {logs!r}")

    with ctx.step("Step 10: THE DOWNSTREAM CONSEQUENCE — the orders are "
                  "split across several partner ids, so the customer's "
                  "total order value is understated on each"):
        grouped = {}
        for order in orders:
            grouped.setdefault(m2o_id(order["partner_id"]), []).append(
                order["origin"])
        ctx.log(f"orders grouped by partner id: {grouped!r}")
        ctx.check_true(
            "one customer's orders are spread over more than one partner, "
            "which breaks customer-level reporting and credit control",
            len(grouped) > 1, actual_desc=repr(grouped))
        ctx.log("THE QUERY TO RUN BEFORE DECIDING THIS CASE'S PRIORITY, and "
                "it is one line: SELECT name, count(*) FROM res_partner "
                "GROUP BY name HAVING count(*) > 1 ORDER BY 2 DESC; If the "
                "answer is 'dozens', this is a P1 data-quality problem the "
                "upgrade should fix. If it is 'none', the client's Workday "
                "data is consistent and the behaviour can be carried as-is. "
                "The low-cost remediation is to match on a NORMALISED "
                "address — case-folded, whitespace-collapsed, common "
                "abbreviations mapped — and to fall back to a name-plus-ZIP "
                "match before creating.")

    with ctx.step("Step 11: the same duplication on the UPDATE path — "
                  "partner_shipping_id"):
        ctx.log("On the update path _prepare_workday_sales_order_values "
                "writes the resolved contact to partner_shipping_id rather "
                "than partner_id (sale_order.py:85-86), and it calls the "
                "SAME _get_partner_id. So the duplication is identical in "
                "cause; what differs is the consequence — a near-duplicate "
                "SHIPPING address on an existing customer rather than a "
                "near-duplicate customer. Asserted by TEST-WF001-TC339 "
                "step 5, which proves partner_shipping_id took the file's "
                "new contact while partner_id did not move.")
