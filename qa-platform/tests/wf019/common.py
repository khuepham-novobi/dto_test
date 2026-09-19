"""Shared fixtures and helpers for the DATAONE-WF-019 suite
(Vendor Payment Import from Workday).

Owning workflow: DATAONE-WF-019, build order 22, **Stage 6 — Workday
integrations (need the documents they carry to exist first)**, risk
CRITICAL, 12 h, depends on WF-018. It owns 8 workbook test cases: TC299
(shared with WF-010), TC323, TC324, TC325, TC327, TC328, TC329 and TC330.

Two workbook cases this suite must NOT re-implement, because another
suite owns them (AUTOMATION_CONVENTIONS.md, "Shared test cases"):

* ``DATAONE-TC050`` — reconciliation integrity — is owned by WF-016 and
  implemented as ``TEST-WF016-TC050``.
* ``DATAONE-TC326`` — the ``workday_document`` stamps — is owned by WF-018
  (build order 21 < 22) and implemented as ``TEST-WF018-TC326``.

What this workflow is
---------------------
Payments are executed in Workday. Without this flow every vendor bill in
Odoo stays open forever, the AP ageing is fiction, and accountants
reconcile by hand against a Workday report. The ETL reads an eight-column
file, finds the bill each payment settles, creates and posts an
``account.payment``, reconciles it against the bill, and stamps Workday's
own identifiers on both sides.

The feasibility fact that decides this suite
--------------------------------------------
**The payment ETL does not read from SFTP at processing time.** Verified
source (``workday_vendor_payment_extractor.py:13-22``)::

    sftp_file = self.etl_processor.get_input()
    attachment = sftp_file.attachment_id
    import_wizard = env['base_import.import'].create({'file': attachment.raw, ...})
    n_rows, rows = import_wizard._read_file(options={'quoting': '"'})

SFTP is only involved in *fetching* the file onto that attachment. So the
whole extract -> transform -> load pipeline is drivable with no network:
build an inactive ``sftp.server``, a ``workday_vendor_payment`` folder, an
``ir.attachment`` holding the CSV, an ``sftp.file`` pointing at it, then
call the PUBLIC ``sftp.file.action_process_sftp_files()``. That is exactly
what ``tests/wf020`` does for the supplier feed, and it is why every case
here is implemented rather than blocked.

What is NOT reachable, and is recorded rather than asserted:

* the remote archive move (``TC323`` step 24, ``TC329`` step 10) — that is
  ``SFTPConnection.move_files`` and needs an endpoint;
* the 5-minute crons themselves. ``cron_process_sftp_files`` is public and
  now savepoints per file (``sftp_file.py:246-292``), but it searches
  **every** pending GET file on the database, which on a clone of the
  client's estate means processing live payment, supplier and requisition
  files. Convention rule 3. Every case here calls
  ``action_process_sftp_files`` on its own fixture file id instead.

Money safety
------------
This suite CREATES AND POSTS PAYMENTS. That is unavoidable — reconciliation
is the point of the workflow — so three things are true of every fixture:

1. Every bill is namespaced (``ref`` carries ``WF019-<token>-``) and
   belongs to a token-scoped vendor, so no live payable is ever settled.
2. Every payment is created by the product's own code against those bills
   only. Nothing here writes ``account.payment`` directly.
3. ``sweep_wf019`` cancels and unlinks what it can and accepts what it
   cannot: a posted, reconciled payment survives, and the fresh token is
   what guarantees the next execution cannot see it.

The duplicate defect this suite exists to characterise
------------------------------------------------------
``_process_workday_vendor_payment_vals`` never looks ``Supplier_Payment``
up against existing payments (``account_payment.py:196-263``), so the same
Workday payment id can create a second ``account.payment`` on a bill that
still has residual. In v17 the file layer offered no second line of
defence either — ``create_sftp_file``'s duplicate detection was entirely
commented out. **The ported tree changed that**: detection always runs and
is governed by ``sftp.folder.duplicate_policy``, which defaults to
``'allow'`` — byte-for-byte the v17 outcome, deliberately, because
changing money-moving behaviour requires a signed decision
(``sftp_file.py:102-167``). TEST-WF019-TC329 therefore asserts all three
policies, so the suite records both the defect AND the control that now
exists to close it.
"""
from __future__ import annotations

import base64
import csv
import io
import uuid

from adapters.base import OdooRPCError
from framework.fg_common import m2o_id, make_trace  # noqa: F401
from framework.qa_fixtures import sweep_model, sweep_products, with_categ  # noqa: F401

WORKFLOW = "DATAONE-WF-019"
WORKFLOW_NAME = "Vendor Payment Import from Workday"
FEATURE = "DATAONE-WF-019 Vendor Payment Import from Workday"
MARK = "WF019"

trace = make_trace(FEATURE)

PAYMENT_USAGE = "workday_vendor_payment"

# account_payment.py — the eight column names the ETL reads BY KEY. They
# are Workday labels with spaces and apostrophes replaced by underscores;
# Supplier_s_Invoice_Number is a mangled possessive that a Workday-side
# report change would alter. A missing key is a bare KeyError inside the
# transform today (:159, :168, :181), captured per row, not a named error.
CSV_COLUMNS = [
    "Supplier_Payment",             # -> payment.workday_document   (:105)
    "Supplier_Invoice_Document",    # -> bill.workday_document      (:181)
    "Supplier_s_Invoice_Number",    # fallback bill match           (:137-141)
    "Document_Link",                # primary bill match, regex     (:127-135)
    "Payment_Amount",               # residual guard + amount       (:166, :107)
    "Payment_Date",                 # required                      (:95, :106)
    "Payment_Type",                 # -> method line NAME, .strip() (:63-67)
    "Transaction_Reference",        # -> payment.memo -> move.ref   (:119)
]

# The row-level messages, verbatim. _prepare_log_message appends
# ". <Name>: <value>" for each non-empty keyword, so these are asserted as
# PREFIXES where the product appends and as equality where it does not.
ERR_BILL_NOT_FOUND = "Vendor bill not found"
ERR_OVER_RESIDUAL = ("Payment amount is greater than vendor bill residual "
                     "amount")
ERR_NO_JOURNAL = ("Please set Journal for Workday Vendor Payment Import in "
                  "Accounting Configuration")
ERR_NO_METHOD = "Cannot find payment method {} of {} journal in Odoo"
ERR_EMPTY_DATE = "Payment Date is empty"

# account_payment.py:256-260 — the per-bill activity.
BILL_ACTIVITY_SUMMARY = "Workday payment import error"
# sftp_file.py:176-182 — the file-level activity.
FILE_ACTIVITY_SUMMARY = "Cannot process SFTP file"
ACTIVITY_TYPE_XMLID = "mail.mail_activity_data_warning"
SUPERUSER_ID = 1

# sftp_file.py:221-228 / :230-232 — the Done-in-selection guard, shared by
# action_retry_process_sftp_files and action_repost.
ERR_ALREADY_PROCESSED = "File(s) have been processed already!"
ERR_ONLY_PENDING = "Only pending file(s) can be processed!"

# sftp_folder.py:43-65 — the control that did not exist on v17.
DUPLICATE_POLICIES = ("allow", "supersede", "skip")

GET_CRON_XMLID = "novobi_sftp_connection.ir_cron_get_sftp_files"
PROCESS_CRON_XMLID = "novobi_sftp_connection.ir_cron_process_sftp_files"

_TOKEN = "init"


def fixture_token() -> str:
    return _TOKEN


def fx(name: str) -> str:
    return f"{name} [{_TOKEN}]"


def bill_ref(suffix: str) -> str:
    """A bill ``ref`` for this execution: 'WF019-<token>-GAMMA-201'.

    The fallback match keys on ``account.move.ref``
    (``account_payment.py:137-141``) with ``limit=1`` and NO company or
    partner term, so a token-scoped ref is the only thing that stops the
    fixture matching a live payable.
    """
    return f"{MARK}-{_TOKEN}-{suffix}"


def workday_id(kind: str, index: int) -> str:
    """'SP-<token>-0001' — token-scoped so 'exactly N payments carry this
    Workday id' can never see a previous execution's."""
    return f"{kind}-{_TOKEN}-{index:04d}"


# ------------------------------------------------------------------ sweep
def sweep_wf019(rpc):
    """Open a fresh fixture namespace, then remove marker-scoped leftovers.

    Best-effort by design, and more so here than anywhere else in the
    platform: this suite POSTS AND RECONCILES PAYMENTS, and a posted,
    reconciled payment cannot be unlinked. The fresh token is the real
    isolation — every search in every test is scoped by it, so a survivor
    cannot be counted by a later run.
    """
    global _TOKEN
    _TOKEN = uuid.uuid4().hex[:6]

    # 1. Payments first: they hold the reconciliations that pin the bills.
    #
    # workday_document is MODULE-OWNED, not core: dto_account_workday
    # declares it as related('move_id.workday_document')
    # (models/account_payment.py:39-41). On a target where that module is
    # not installed the field does not exist, and an unguarded search
    # domain raises OdooRPCError *here* — before require_payment_import
    # can report the same fact as a precise BLOCKED. The guard is what
    # lets the probe speak; it is the same shape the core `memo` search
    # below already uses, applied to the field that actually needs it.
    payments = rpc.search(
        "account.payment", [("workday_document", "like", f"%-{MARK}%")]) \
        if rpc.field_exists("account.payment", "workday_document") else []
    payments += rpc.search(
        "account.payment", [("memo", "like", f"{MARK}-%")]) \
        if rpc.field_exists("account.payment", "memo") else []
    for payment_id in sorted(set(payments)):
        for method in ("action_draft", "action_cancel"):
            try:
                rpc.call("account.payment", method, [payment_id])
            except OdooRPCError:
                pass
        try:
            rpc.call("account.payment", "unlink", [payment_id])
        except OdooRPCError:
            pass

    # 2. Moves.
    move_ids = set(rpc.search("account.move", [("ref", "like", f"{MARK}-%")]))
    move_ids |= set(rpc.search("account.move",
                               [("invoice_origin", "like", f"{MARK} %")]))
    for move_id in sorted(move_ids):
        for method in ("button_draft", "button_cancel"):
            try:
                rpc.call("account.move", method, [move_id])
            except OdooRPCError:
                pass
        try:
            rpc.call("account.move", "unlink", [move_id])
        except OdooRPCError:
            pass

    # 3. SFTP fixtures, innermost first. sftp.folder._check_unique_folder
    #    runs with active_test=False, so leftovers must be REMOVED.
    servers = rpc.search("sftp.server", [("name", "like", f"{MARK} %"),
                                         ("active", "in", [True, False])])
    if servers:
        folders = rpc.search("sftp.folder", [("server_id", "in", servers),
                                             ("active", "in", [True, False])])
        if folders:
            files = rpc.search("sftp.file", [("folder_id", "in", folders),
                                             ("active", "in", [True, False])])
            for model, ids in (("sftp.file", files), ("sftp.folder", folders)):
                if ids:
                    try:
                        rpc.call(model, "unlink", ids)
                    except OdooRPCError:
                        pass
        try:
            rpc.call("sftp.server", "unlink", servers)
        except OdooRPCError:
            pass

    sweep_products(rpc, MARK)
    sweep_model(rpc, "res.partner", [("name", "like", f"{MARK} %"),
                                     ("user_ids", "=", False),
                                     ("active", "in", [True, False])])
    sweep_model(rpc, "ir.attachment", [("name", "like", f"{MARK}%")])


# ---------------------------------------------------------------- probes
def require_payment_import(ctx):
    """BLOCK unless the inbound payment leg exists at all."""
    rpc = ctx.adapter.rpc

    missing = [m for m in ("sftp.server", "sftp.folder", "sftp.file",
                           "account.payment")
               if not rpc.model_exists(m)]
    if missing:
        ctx.blocked(
            f"Missing model(s) on {ctx.env.key} (db={ctx.env.db}): "
            f"{', '.join(missing)}. novobi_sftp_connection / account are "
            "not both installed, so there is no payment import to observe.")

    info = rpc.call("sftp.folder", "fields_get", ["usage"],
                    attributes=["selection"])
    keys = [k for k, _label in (info["usage"].get("selection") or [])]
    if PAYMENT_USAGE not in keys:
        ctx.blocked(
            f"sftp.folder.usage does not offer {PAYMENT_USAGE!r} on "
            f"{ctx.env.key} — dto_account_workday is not installed, so "
            f"sftp.file._process_sftp_file never dispatches to the payment "
            f"ETL. Available usage keys: {keys}")

    if not rpc.field_exists("account.payment", "workday_document"):
        ctx.blocked(
            "account.payment.workday_document does not exist. On v17 it "
            "came free from account.payment._inherits = {'account.move': "
            "'move_id'}; v19 removed that _inherits and this module "
            "re-declares the field as related(move_id.workday_document, "
            "readonly=False). Without it the payment carries no Workday "
            "identifier and most of this suite is vacuous.")

    if not rpc.field_exists("account.move", "have_attachment"):
        ctx.blocked(
            "account.move.have_attachment does not exist — dto_account is "
            "not installed, and its _post override is what every fixture "
            "bill in this suite has to satisfy before it can be posted.")


def company_id(rpc) -> int:
    return m2o_id(rpc.read("res.users", [rpc.uid], ["company_id"])[0]
                  ["company_id"])


def payment_journal(ctx, company=None):
    """(journal_id, [method line names]) for a usable bank/cash journal.

    ``_get_workday_payment_method_line_id`` matches ``Payment_Type.strip()``
    against ``outbound_payment_method_line_ids.name``
    (``account_payment.py:62-67``), so the fixture's Payment_Type must be a
    real line name **on this database**. TC330 step 1 requires those names
    to be recorded verbatim and re-taken on v19: if Odoo's stock method-line
    names changed, every row fails at once and the symptom looks like a
    Workday problem rather than an upgrade one.
    """
    rpc = ctx.adapter.rpc
    domain = [("type", "in", ["bank", "cash"])]
    if company:
        domain.append(("company_id", "=", company))
    journals = rpc.search_read(
        "account.journal", domain,
        ["name", "outbound_payment_method_line_ids", "company_id"],
        order="id")
    for journal in journals:
        line_ids = journal["outbound_payment_method_line_ids"]
        if not line_ids:
            continue
        # account.payment.method.line — the same model name on v17
        # (account/models/account_payment_method.py:91) and v19 (:96).
        names = [row["name"] for row in
                 rpc.read("account.payment.method.line", line_ids, ["name"])]
        if names:
            return journal["id"], names
    ctx.blocked(
        "No bank/cash journal on this database carries an outbound payment "
        "method line. _get_workday_payment_method_line_id matches the CSV's "
        "Payment_Type against those line NAMES, so without one EVERY row "
        "fails with 'Cannot find payment method ...' and every case here "
        "would assert the error path instead of its subject.")


def retarget_payment_journal(ctx, journal_id):
    """Point res.company.workday_vendor_payment_journal_id at a journal.

    Returns (company_id, original) for the caller's ``finally``. This is
    LIVE configuration — ``_prepare_workday_payment_vals`` reads it off
    ``bill.company_id`` (``account_payment.py:79``), so it cannot be
    avoided; it is restored in a finally that can never raise, and
    ``sweep_wf019`` is not able to repair it, so the finally is the only
    guard. Every test that calls this must have one.
    """
    rpc = ctx.adapter.rpc
    cid = company_id(rpc)
    field = "workday_vendor_payment_journal_id"
    if not rpc.field_exists("res.company", field):
        ctx.blocked(
            f"res.company.{field} does not exist — dto_account_workday's "
            "payment configuration is absent, so no row can resolve a bank "
            "journal.")
    before = m2o_id(rpc.read("res.company", [cid], [field])[0][field]) or False
    rpc.write("res.company", [cid], {field: journal_id})
    ctx.log(f"company {cid} payment journal -> {journal_id} (was {before})")
    return cid, {field: before}


def restore_company(ctx, cid, original):
    """Put the live Workday payment configuration back. Never raises."""
    try:
        ctx.adapter.rpc.write("res.company", [cid], original)
        ctx.log(f"company {cid} configuration restored: {original!r}")
    except OdooRPCError as exc:                            # pragma: no cover
        ctx.log(f"[warn] could not restore company {cid} configuration "
                f"({exc}). The value to restore is {original!r} — set it by "
                "hand before running this suite again.")


# -------------------------------------------------------------- fixtures
def ensure_vendor(rpc, label="Vendor Gamma") -> int:
    name = fx(f"{MARK} {label}")
    found = rpc.search("res.partner", [("name", "=", name)], limit=1)
    if found:
        return found[0]
    return rpc.create("res.partner", {"name": name, "ref": bill_ref("V-001"),
                                      "supplier_rank": 1})


def ensure_product(ctx, label="CMP-CONN-A", price=100.0) -> int:
    rpc = ctx.adapter.rpc
    name = fx(f"{MARK} {label}")
    found = rpc.search_read("product.product", [("name", "=", name)],
                            ["id"], limit=1)
    if found:
        return found[0]["id"]
    values = {"name": name, "list_price": price, "standard_price": price,
              "purchase_ok": True, "sale_ok": False,
              "taxes_id": [(6, 0, [])], "supplier_taxes_id": [(6, 0, [])]}
    values.update(ctx.adapter.storable_product_values())
    tmpl_id = rpc.create("product.template", with_categ(rpc, values))
    variant = rpc.search_read("product.product",
                              [("product_tmpl_id", "=", tmpl_id)],
                              ["id"], limit=1)
    return variant[0]["id"]


def make_bill(ctx, vendor_id, amount, ref_suffix, label="bill",
              invoice_date="2026-08-01", product_id=None):
    """A posted, tax-free vendor bill of exactly ``amount``.

    Tax-free so ``amount_residual`` equals the line total and the residual
    guard's arithmetic is predictable. The attachment is written through
    ``attachment_ids`` ON THE MOVE, because that is the route that
    invalidates ``dto_account``'s stored ``have_attachment`` compute
    reliably — a bill whose stored flag stayed False cannot be posted
    (``dto_account/models/account_move.py:50-56``).
    """
    rpc = ctx.adapter.rpc
    product_id = product_id or ensure_product(ctx)
    move_id = rpc.create("account.move", {
        "move_type": "in_invoice",
        "partner_id": vendor_id,
        "invoice_date": invoice_date,
        "date": invoice_date,
        "ref": bill_ref(ref_suffix),
        "invoice_origin": fx(f"{MARK} {label}"),
        "invoice_line_ids": [(0, 0, {
            "product_id": product_id,
            "name": fx(f"{MARK} {label} line"),
            "quantity": 1.0,
            "price_unit": amount,
            "tax_ids": [(6, 0, [])],
        })],
        "attachment_ids": [(0, 0, {
            "name": fx(f"{MARK} {label}.pdf"),
            "res_model": "account.move",
            "datas": base64.b64encode(b"%PDF-1.4 WF019 QA").decode()})],
    })
    rpc.call("account.move", "action_post", [move_id])
    row = rpc.read("account.move", [move_id],
                   ["state", "amount_residual", "amount_total", "ref"])[0]
    if row["state"] != "posted":
        ctx.blocked(
            f"Fixture bill {move_id} did not post (state={row['state']!r}). "
            "Every case in this suite settles a POSTED bill, so nothing can "
            "be observed against a draft one.")
    return move_id, row


# ------------------------------------------------------------ the CSV leg
def csv_bytes(rows, columns=None, header_offset=0, short_row_index=None,
              duplicate_header=None) -> bytes:
    """A UTF-8 CSV whose header row supplies the ETL's dict keys.

    ``header_offset`` prepends blank lines — ``_convert_data_to_list_of_dict``
    is called with the default ``row_start=0``
    (``workday_vendor_payment_extractor.py:23``), so a shifted header is a
    whole-file failure and TC328 step 10 needs to build one.
    ``short_row_index`` truncates one data row by one cell, which is TC328
    step 5's IndexError. ``duplicate_header`` appends a second column of
    that name carrying a different value, for step 9.
    """
    columns = list(columns or CSV_COLUMNS)
    if duplicate_header:
        columns = columns + [duplicate_header]
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n", quoting=csv.QUOTE_ALL)
    for _ in range(header_offset):
        writer.writerow([])
    writer.writerow(columns)
    for index, row in enumerate(rows):
        values = [row.get(column, "") for column in columns]
        if duplicate_header:
            values[-1] = row.get(f"__second_{duplicate_header}", "")
        if short_row_index is not None and index == short_row_index:
            values = values[:-1]
        writer.writerow(values)
    return buffer.getvalue().encode("utf-8")


def make_server(rpc, action="GET", label=None) -> int:
    """An sftp.server fixture that can never connect (convention rule 4).

    ``active=False`` keeps it out of ``cron_get_sftp_files``'s search and
    the host is unroutable. Creating the record performs no I/O.
    """
    return rpc.create("sftp.server", {
        "name": fx(f"{MARK} {label or ('Workday ' + action)}"),
        "host": "sftp.qa-never-resolves.invalid",
        "port": "22",
        "username": "qa-wf019",
        "password": "not-a-real-credential",
        "action": action,
        "active": False,
        "archive_auto": False,
    })


def make_folder(rpc, server_id, usage=PAYMENT_USAGE, label="in",
                duplicate_policy="allow", regex=False) -> int:
    values = {
        "server_id": server_id,
        "path": f"/{MARK}/{fixture_token()}/{label}",
        "usage": usage,
        "active": True,
    }
    if rpc.field_exists("sftp.folder", "duplicate_policy"):
        values["duplicate_policy"] = duplicate_policy
    if regex:
        values["regex"] = regex
    return rpc.create("sftp.folder", values)


def make_sftp_file(rpc, folder_id, file_name, content: bytes,
                   sftp_date=None, mimetype="text/csv") -> int:
    """A Pending sftp.file whose attachment holds ``content``.

    Created directly rather than through ``create_sftp_file``, which takes
    a *recordset* for its folder argument and base64-encodes raw bytes —
    neither survives a JSON-RPC hop. The record shape is identical.
    TEST-WF019-TC329 uses ``create_sftp_file`` deliberately instead,
    because the duplicate policy lives inside it.
    """
    attachment_id = rpc.create("ir.attachment", {
        "name": file_name, "type": "binary", "mimetype": mimetype,
        "datas": base64.b64encode(content).decode("ascii"),
    })
    folder = rpc.read("sftp.folder", [folder_id], ["path"])[0]
    values = {"folder_id": folder_id,
              "ref": f"{folder['path']}/{file_name}",
              "attachment_id": attachment_id}
    if sftp_date:
        values["sftp_date"] = sftp_date
    return rpc.create("sftp.file", values)


def process_file(ctx, file_id):
    """Run the real ETL over one Pending file and read the outcome back.

    ``action_process_sftp_files`` is public, takes the file's own id, and
    marks the record done/failed from ``_process_sftp_file``'s
    ``(result, message)`` — the identical path
    ``cron_process_sftp_files`` takes per file, without touching any other
    pending file on the database.
    """
    rpc = ctx.adapter.rpc
    rpc.call("sftp.file", "action_process_sftp_files", [file_id])
    return rpc.read("sftp.file", [file_id],
                    ["state", "process_date", "name", "ref", "usage",
                     "org_file_id", "active"])[0]


def run_import(ctx, rows, folder_id=None, file_label="payments",
               columns=None, header_offset=0, short_row_index=None,
               duplicate_header=None):
    """Build the CSV, attach it, process it. Returns (folder, file, row)."""
    rpc = ctx.adapter.rpc
    if folder_id is None:
        folder_id = make_folder(rpc, make_server(rpc))
    content = csv_bytes(rows, columns=columns, header_offset=header_offset,
                        short_row_index=short_row_index,
                        duplicate_header=duplicate_header)
    file_id = make_sftp_file(rpc, folder_id,
                             fx(f"{MARK}_{file_label}.csv"), content)
    ctx.log(f"processing {len(rows)} row(s) through the real ETL "
            f"(sftp.file {file_id}, no network)")
    return folder_id, file_id, process_file(ctx, file_id)


def row(supplier_payment, invoice_document, bill_ref_value="",
        document_link="", amount="", payment_date="2026-09-01",
        payment_type="", reference="") -> dict:
    """One eight-column Workday payment row, all keys present."""
    return {
        "Supplier_Payment": supplier_payment,
        "Supplier_Invoice_Document": invoice_document,
        "Supplier_s_Invoice_Number": bill_ref_value,
        "Document_Link": document_link,
        "Payment_Amount": amount,
        "Payment_Date": payment_date,
        "Payment_Type": payment_type,
        "Transaction_Reference": reference,
    }


def document_link(base_url, move_id) -> str:
    """The Document_Link shape the regex expects.

    ``_get_vendor_bill_from_workday_payment_data`` matches
    ``r'(.*)[#&?]id=(\\d+)(.*)'`` (``account_payment.py:130``), so the id
    must follow a '#', '&' or '?'. That regex is the reason a Workday-side
    URL format change breaks the primary match silently — the fallback
    then quietly takes over and matches by ref instead.
    """
    return (f"{base_url}/web#id={move_id}&model=account.move"
            f"&view_type=form")


def base_url(rpc) -> str:
    rows = rpc.search_read("ir.config_parameter",
                           [("key", "=", "web.base.url")], ["value"], limit=1)
    return rows[0]["value"] if rows else ""


# ------------------------------------------------------------- assertions
def payments_for(rpc, workday_document, fields_=None):
    fields_ = fields_ or ["workday_document", "export_workday", "amount",
                          "state", "payment_type", "partner_type",
                          "journal_id", "partner_id", "date", "memo",
                          "payment_method_line_id", "move_id", "company_id"]
    fields_ = [f for f in fields_ if rpc.field_exists("account.payment", f)]
    return rpc.search_read("account.payment",
                           [("workday_document", "=", workday_document)],
                           fields_, order="id")


def bill_state(rpc, move_id):
    fields_ = ["amount_residual", "amount_total", "payment_state",
               "workday_document", "export_workday", "ref"]
    fields_ = [f for f in fields_ if rpc.field_exists("account.move", f)]
    return rpc.read("account.move", [move_id], fields_)[0]


def activities_on(rpc, model, res_ids, fields_=None):
    if not res_ids:
        return []
    fields_ = fields_ or ["res_model", "res_id", "summary", "note",
                          "user_id", "date_deadline", "activity_type_id"]
    return rpc.search_read("mail.activity",
                           [("res_model", "=", model),
                            ("res_id", "in", list(res_ids))],
                           fields_, order="id")


def reconciliation_shape(rpc, move_ids):
    """The full reconciliation shape of a set of moves, comparably.

    Returns a sorted list of tuples built from VALUES, never ids, so a v17
    capture and a v19 capture of the same fixture are comparable. This is
    TC325 step 14's dump, expressed over the ORM.
    """
    lines = rpc.search_read(
        "account.move.line", [("move_id", "in", list(move_ids))],
        ["move_id", "account_id", "debit", "credit", "amount_residual",
         "full_reconcile_id", "matched_debit_ids", "matched_credit_ids",
         "display_type"], order="id")
    accounts = {}
    account_ids = sorted({m2o_id(line["account_id"]) for line in lines
                          if line.get("account_id")})
    if account_ids:
        accounts = {a["id"]: a["account_type"] for a in
                    rpc.read("account.account", account_ids,
                             ["account_type"])}
    shape = []
    for line in lines:
        shape.append((
            accounts.get(m2o_id(line.get("account_id")), "unknown"),
            line.get("display_type") or "",
            round(line.get("debit") or 0.0, 2),
            round(line.get("credit") or 0.0, 2),
            round(line.get("amount_residual") or 0.0, 2),
            bool(line.get("full_reconcile_id")),
            len(line.get("matched_debit_ids") or []),
            len(line.get("matched_credit_ids") or []),
        ))
    return sorted(shape)


def partial_amounts(rpc, move_ids):
    """The partial-reconcile amounts touching these moves, as a multiset."""
    lines = rpc.search("account.move.line",
                       [("move_id", "in", list(move_ids))])
    if not lines:
        return []
    partials = rpc.search_read(
        "account.partial.reconcile",
        ["|", ("debit_move_id", "in", lines),
         ("credit_move_id", "in", lines)], ["amount"])
    return sorted(round(p["amount"] or 0.0, 2) for p in partials)


def expect_error(rpc_callable, *args, **kwargs):
    try:
        rpc_callable(*args, **kwargs)
        return False, "no error raised"
    except OdooRPCError as exc:
        return True, str(exc)


def file_message(rpc, file_id) -> str:
    """The message the ETL handed to mark_sync_failed, read back off the
    file-level activity — the only place it is persisted."""
    acts = activities_on(rpc, "sftp.file", [file_id])
    return " || ".join(str(act.get("note") or "") for act in acts)
