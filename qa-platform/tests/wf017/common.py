"""Shared fixtures and helpers for the DATAONE-WF-017 suite
(Journal Entry Export to Workday).

Owning workflow: DATAONE-WF-017, build order 24, **Stage 6 — Workday
integrations (need the documents they carry to exist first)**, risk
CRITICAL, fail mode SILENT, 19 h, depends on WF-013. It owns 13 workbook
test cases: TC036, TC291, TC292, TC306, TC307, TC308, TC309, TC310, TC311,
TC312, TC313, TC314 and TC315.

Four workbook cases this suite must NOT re-implement, because WF-018 owns
them on build order (21 < 24) — ``AUTOMATION_CONVENTIONS.md``, "Shared test
cases": ``DATAONE-TC035`` (the export-state reconciliation, implemented as
``TEST-WF018-TC035``), ``DATAONE-TC296`` (the POST duplicate guard,
``TEST-WF018-TC296``), ``DATAONE-TC300`` (Re-post, ``TEST-WF018-TC300``)
and ``DATAONE-TC304`` (the db-stored attachment, ``TEST-WF018-TC304``).
``DATAONE-TC018`` is owned by WF-010 as ``TEST-WF010-TC018``.

What this workflow is
---------------------
**Workday, not Odoo, is DataOne's general ledger of record.** Odoo runs
operations; every posted accounting consequence must reach Workday in
Workday's own bulk-import spreadsheet. This flow snapshots each journal
ITEM into 23 Workday-shaped fields and writes one spreadsheet row per item
into a copy of ``Bulk_Import_Submit_Accounting_Journal_v44.0.xlsx`` at 24
mapped columns. A silently wrong column means the client's statutory books
are wrong; a silently dropped entry means the ledger of record is short an
entry and nothing in Odoo says so.

THE DEFECT THIS SUITE EXISTS TO CATCH
-------------------------------------
Column T — ``export_workday_journal_workday`` — is a REQUIRED column, and
it is resolved per move through a two-step chain::

    account.move.entry_type              (assigned at create, from stock moves)
      -> journal_id.get_journal_workday(entry_type)
        -> account.journal.workday.id_workday      -> column T

v17 derived ``entry_type`` for stock-valuation entries carrying no stock
move by reading ``account.move.stock_valuation_layer_ids``. **v19 DELETED
``stock.valuation.layer`` outright** — the model, its file and its table.
So the chain becomes: relation gone -> the ``elif`` never fires ->
``entry_type = False`` -> ``journal_workday_id`` empty -> column T blank ->
F198 withholds the line -> F199 drops the WHOLE MOVE. The outcome is a
SHORTER FILE, an activity nobody reads, and a general ledger in Workday
that is quietly missing the client's inventory accounting. **Nothing raises
anywhere along that chain.**

The workbook is explicit about the consequence for test design: *"The
predicted v19 failure produces a workbook that is internally consistent and
completely valid — it simply contains fewer moves than it should. A test
that opens the file and checks it parses will pass while the client's
inventory accounting quietly stops reaching Workday."* So every case here
asserts an INDEPENDENTLY COMPUTED row count and a per-move column-T
grouping, never "the file parses".

The ported tree has already re-derived that branch
(``dto_account_workday/models/account_move.py:306-328``): *no stock move +
the company's stock journal = inventory_adj*, with the measurement that
justifies it (of 184,882 typed entries, exactly 633 took the v17 branch,
every one ``inventory_adj`` and every one in the STJ journal). These tests
are what prove the re-derivation selects the same population.

The feasibility fact that decides this suite
--------------------------------------------
Identical to WF-018's: the export is entirely local up to the upload.
``WorkdayLoader._run_loader_workday_journal_entry`` only CREATES the
``sftp.file`` in state ``pending``; the network hop is
``cron_post_sftp_files``. The produced workbook is readable over RPC as
``ir.attachment.datas`` and parsed here with openpyxl.

THE ADAPTATION THAT MATTERS, AND WHY
------------------------------------
TC306 and TC309 ask for SEVEN real stock operations to be performed — a
receipt, a delivery, a purchase return, a sales return, an MO completion, a
scrap and an inventory adjustment — so that ``entry_type`` is DERIVED
rather than written. That derivation cannot be faked: ``entry_type`` is
``readonly=True`` and is assigned once inside ``account.move.create()``
from the move's stock moves, so no fixture can set it.

Re-performing all seven over RPC would mean re-implementing most of
WF-015, WF-011, WF-024, WF-007, WF-022 and WF-021 inside this suite, and
each depends on environment facts this suite cannot assert (real-time
valuation on the right category, a BOM, warehouse routes, a
scrap-reason...). Those suites already exist and own those operations.

So the derivation is asserted **against the live population, read-only**,
which is both larger and more representative than seven synthetic moves:
for each of the seven entry types, every posted move on the target carrying
that type is grouped and its resolved ``id_workday`` asserted against the
shipped mapping. On the client's clone those populations are in the tens of
thousands. Where a type has no live example, that is RECORDED rather than
skipped — a type with zero rows is itself a finding.

The COLUMN CONTRACT half — everything from the workbook onwards — is then
asserted against FIXTURE moves this suite creates and owns: token-scoped
miscellaneous entries on a token-scoped journal carrying a real catalogue
source. That path resolves column T through
``get_journal_workday(False)`` -> ``journal_workday_id``, which is M8's
single-source path, and it is fully deterministic.

Safety
------
* **Never export a live move.** Every export runs through the wizard
  against an explicit fixture id list. ``cron_export_workday_journal_entry``
  is public and would dispatch, but it searches the whole domain under
  ``mark_exported=True`` — flagging live entries as exported to Workday
  and removing them from the real queue forever. Nothing here calls it; its
  ``limit=2000`` is asserted by reading ``ir.cron.code``.
* **Never modify a live journal.** The fixture journal is created per
  execution and points at an EXISTING catalogue record, which is only read.
* ``res.company.workday_journal_entry_sftp_folder_id`` is live
  configuration; it is repointed at an inactive fixture folder and restored
  in a ``finally`` that can never raise, and ``sweep_wf017`` repairs a
  company still pointing at a WF017-marked folder.
"""
from __future__ import annotations

import base64
import io
import uuid

from adapters.base import OdooRPCError
from framework.fg_common import form_arch, list_tag, m2o_id, make_trace  # noqa: F401
from framework.qa_fixtures import (ensure_postable_bill,  # noqa: F401
                                   sweep_model, sweep_products,
                                   with_categ)

WORKFLOW = "DATAONE-WF-017"
WORKFLOW_NAME = "Journal Entry Export to Workday"
FEATURE = "DATAONE-WF-017 Journal Entry Export to Workday"
MARK = "WF017"

trace = make_trace(FEATURE)

# ---------------------------------------------------------------- source
# account_move.py:77-83. Mirrored rather than called: the method is a
# @staticmethod whose name starts with an underscore, so Odoo's
# check_method_name refuses to dispatch it over RPC (v17 odoo/models.py:145,
# v19 odoo/orm/utils.py:69). TEST-WF017-TC307 asserts the mirror clause by
# clause against what the product's own cron code string contains.
JOURNAL_ENTRY_EXPORT_DOMAIN = [
    ("move_type", "!=", "in_invoice"),
    ("state", "=", "posted"),
    ("export_workday", "=", False),
    ("journal_id.type", "not in", ["bank"]),
]

# account_move.py:99-107 — the two blocking strings, verbatim.
ERR_EMPTY_SELECTION = "Please select at least one record"
ERR_NOT_POSTED = "Please select posted journal entries only"
ERR_IS_BILL = ("Vendor bills should be synced separately. Please select "
               "posted journal entries only")

# res_company.py:52-62 — the two configuration messages, verbatim. Note
# that the SECOND covers FOUR distinct causes (no folder / wrong usage /
# wrong direction) with one string; TC314 records that as a finding.
ERR_NO_TEMPLATE = ("Cannot export journal entry: Export Template is not "
                   "configured yet")
ERR_BAD_FOLDER = ("Cannot export journal entry: Missing or incorrect SFTP "
                  "folder")

# workday_loader.py:187 / :206 / :205
ERR_NOTHING_TO_EXPORT = "There is nothing to export!"
ACTIVITY_SUMMARY = "Cannot export data from this journal entry"
ACTIVITY_TYPE_XMLID = "mail.mail_activity_data_warning"

# account_journal_workday.py:70-83 / account_journal.py:28-32 — the two
# configuration constraints, verbatim.
ERR_DUPLICATE_ENTRY_TYPE = "Type must be unique within a journal"
ERR_NO_MAPPING = "Please add Workday Journal Source mapping"

# data/data_template_export_data.xml:35-69
TEMPLATE_XMLID = "dto_account_workday.template_export_workday_journal_entry"
TEMPLATE_SHEET = "Bulk Import Submit Accounting J"
TEMPLATE_FILE_NAME = "Bulk_Import_Submit_Accounting_Journal_v44.0.xlsx"
TEMPLATE_ROW_START = 6

JOURNAL_ENTRY_USAGE = "workday_journal_entry"
VENDOR_BILL_USAGE = "workday_vendor_bill"
EXPORT_CRON_XMLID = "dto_account_workday.ir_cron_export_workday_journal_entries"
BILL_CRON_XMLID = "dto_account_workday.ir_cron_export_workday_vendor_bills"
POST_CRON_XMLID = "novobi_sftp_connection.ir_cron_post_sftp_files"

# The 24-row column contract, exactly as data_template_export_data.xml
# declares it: (column, field on account.move.line, required?). Note that
# export_workday_currency is mapped TWICE — P and AR — which is why the
# list is not a dict. TEST-WF017-TC306 asserts this table against what the
# database holds BEFORE asserting any cell against it, so a template edit
# cannot make the test pass by drifting with it.
COLUMN_CONTRACT = [
    ("B", "export_workday_id_move", True),
    ("I", "export_workday_submit", False),
    ("O", "export_workday_company", True),
    ("P", "export_workday_currency", True),
    ("Q", "export_workday_ledger_type", True),
    ("S", "export_workday_date", True),
    ("T", "export_workday_journal_workday", True),
    ("Y", "export_workday_ref", False),
    ("Z", "export_workday_move_name", False),
    ("AA", "export_workday_url", False),
    ("AI", "export_workday_id_row", True),
    ("AL", "export_workday_account_code", True),
    ("AM", "export_workday_account_set", True),
    ("AP", "export_workday_debit", False),
    ("AQ", "export_workday_credit", False),
    ("AR", "export_workday_currency", False),
    ("AZ", "export_workday_name", False),
    ("BA", "export_workday_external_ref", False),
    ("BC", "export_workday_spend_category", False),
    ("BE", "export_workday_revenue_category", False),
    ("BG", "export_workday_account_cost_center_name", False),
    ("BI", "export_workday_account_project_name", False),
    ("BK", "export_workday_account_customer_contract_name", False),
    ("BY", "export_workday_supplier_code", False),
]
REQUIRED_COLUMNS = sorted({col for col, _f, req in COLUMN_CONTRACT if req})
JOURNAL_SOURCE_COLUMN = "T"
ROW_INDEX_COLUMN = "AI"
MOVE_ID_COLUMN = "B"

# workday_journal_entry.py:149-152 / :160 — four tenant constants in
# Python, not configuration.
HARDCODED_CELLS = {"I": "Y", "O": "DOS", "P": "USD", "Q": "Actuals",
                   "AM": "AS_Standard_Child"}

# TC306 step 20 — wide unmapped columns that must stay untouched.
UNMAPPED_SPOT_CHECK = ["C", "AB", "BB", "CA", "DZ", "AC", "BD", "BZ"]

# account_journal_workday.py:8-16 — the seven entry types, and the mapping
# the shipped account.journal.workday.line.csv declares for the Inventory
# Valuation journal. TC309's matrix, verbatim from the data file.
ENTRY_TYPE_MAPPING = {
    "incoming": "Inventory_Put_Away",
    "outgoing": "Inventory_Shipment",
    "outgoing_return": "Inventory_Return_To_Supplier",
    "incoming_return": "Inventory_Put_Away_Adjustment",
    "mrp_operation": "Inventory_Move",
    "scrap_operation": "Inventory_Issue",
    "inventory_adj": "Inventory_Adjustment",
}
# The two single-source journals the shipped account_journal_data.xml sets.
SINGLE_SOURCE_JOURNALS = {
    "account.1_sale": "Customer_Invoice",
    "account.1_purchase": "Supplier_Invoice",
}
MAPPING_LINE_XMLIDS = [
    f"dto_account_workday.workday_journal_{slug}" for slug in (
        "inventory_put_away", "inventory_shipment",
        "inventory_return_to_supplier", "inventory_put_away_adjustment",
        "inventory_move", "inventory_issue", "inventory_adjustment")]
INVENTORY_JOURNAL_XMLID = "account.1_inventory_valuation"

# data/account.journal.workday.csv holds 131 rows; the .line.csv holds 7.
EXPECTED_SOURCE_COUNT = 131
EXPECTED_MAPPING_COUNT = 7

# A catalogue record the fixture journal can point at. Any real one would
# do; this one is chosen because it is not referenced by
# account_journal_data.xml and therefore cannot be confused with a live
# single-source assignment.
FIXTURE_SOURCE_XMLID = ("dto_account_workday."
                        "workday_journal_accounting_adjustment")

# dto_account_cogs/models/account_move.py:220-231 — env.ref() calls that
# run inside _post for EVERY move, not only invoices. A missing xmlid makes
# every post raise ValueError.
COGS_ANALYTIC_XMLIDS = [
    "dto_account.analytic_account_revenue_category_manufacturing_sales",
    "dto_account.analytic_account_spend_category_consumables",
    "dto_account.analytic_account_cost_center_202000",
]

# sftp_log.py:26 — the traceback field is group-restricted, which is
# TC292's steps 11-12 and is assertable without any connection.
LOG_TRACEBACK_GROUP = "base.group_no_one"
LOG_CONNECTION_OK = "Connection Test Succeeded!"
LOG_CONNECTION_FAIL = "Connection Test Failed!"

_TOKEN = "init"


def fixture_token() -> str:
    return _TOKEN


def fx(name: str) -> str:
    return f"{name} [{_TOKEN}]"


def move_ref(suffix: str) -> str:
    """A move ``ref`` for this execution: 'WF017-<token>-G1'."""
    return f"{MARK}-{_TOKEN}-{suffix}"


# ------------------------------------------------------------------ sweep
def sweep_wf017(rpc):
    """Open a fresh fixture namespace, then remove marker-scoped leftovers.

    Best-effort by design: a posted journal entry cannot be unlinked once
    it carries an inalterable hash, and this suite's whole subject is
    posted entries. The fresh token is what guarantees isolation — every
    search in every test is token-scoped, so a survivor cannot be counted
    by an "exactly N rows" assertion.
    """
    global _TOKEN
    _TOKEN = uuid.uuid4().hex[:6]

    # 0. Repair a company still pointing at a WF017 fixture folder.
    stale = rpc.search("sftp.folder", [("path", "like", f"/{MARK}/%"),
                                       ("active", "in", [True, False])])
    if stale:
        for field in ("workday_journal_entry_sftp_folder_id",
                      "workday_vendor_bill_sftp_folder_id"):
            if not rpc.field_exists("res.company", field):
                continue
            hit = rpc.search("res.company", [(field, "in", stale)])
            if hit:
                try:
                    rpc.write("res.company", hit, {field: False})
                except OdooRPCError:
                    pass

    # 1. Moves, then the journals they sit on.
    move_ids = set(rpc.search("account.move", [("ref", "like", f"{MARK}-%")]))
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

    journals = rpc.search("account.journal",
                          [("name", "like", f"{MARK} %"),
                           ("active", "in", [True, False])])
    for journal_id in journals:
        try:
            rpc.call("account.journal.workday.line", "unlink",
                     rpc.search("account.journal.workday.line",
                                [("journal_id", "=", journal_id)]))
        except OdooRPCError:
            pass
        try:
            rpc.call("account.journal", "unlink", [journal_id])
        except OdooRPCError:
            try:
                rpc.write("account.journal", [journal_id], {"active": False})
            except OdooRPCError:
                pass

    # 2. SFTP fixtures, innermost first.
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
    sweep_model(rpc, "ir.attachment",
                [("name", "like", f"{MARK}%"),
                 ("res_model", "=", "data.template.export")])


# ---------------------------------------------------------------- probes
def require_journal_export(ctx):
    """BLOCK unless the outbound journal-entry export exists at all."""
    rpc = ctx.adapter.rpc

    missing = [m for m in ("sftp.server", "sftp.folder", "sftp.file",
                           "data.template.export", "account.journal.workday",
                           "account.journal.workday.line",
                           "workday.journal.entry.export.wizard")
               if not rpc.model_exists(m)]
    if missing:
        ctx.blocked(
            f"Missing model(s) on {ctx.env.key} (db={ctx.env.db}): "
            f"{', '.join(missing)}. dto_account_workday / "
            "novobi_sftp_connection / novobi_base_export are not all "
            "installed, so there is no journal-entry export to observe.")

    for field in ("entry_type", "journal_workday_id", "export_workday"):
        if not rpc.field_exists("account.move", field):
            ctx.blocked(
                f"account.move.{field} does not exist — the two-step chain "
                "entry_type -> get_journal_workday -> column T is the whole "
                "subject of this suite, and without this field it cannot be "
                "observed.")

    if not rpc.field_exists("account.move.line",
                            "export_workday_journal_workday"):
        ctx.blocked(
            "account.move.line carries no export_workday_journal_workday — "
            "the workday.journal.entry AbstractModel is not inherited into "
            "account.move.line on this target, so required column T has "
            "nothing to read.")


def require_journal_usage(ctx):
    rpc = ctx.adapter.rpc
    info = rpc.call("sftp.folder", "fields_get", ["usage"],
                    attributes=["selection"])
    keys = [k for k, _label in (info["usage"].get("selection") or [])]
    if JOURNAL_ENTRY_USAGE not in keys:
        ctx.blocked(
            f"sftp.folder.usage does not offer {JOURNAL_ENTRY_USAGE!r} on "
            f"{ctx.env.key} — dto_account_workday's selection_add did not "
            f"load. Available usage keys: {keys}")


def require_post_analytics(ctx):
    """BLOCK unless dto_account_cogs' env.ref() targets resolve.

    ``dto_account_cogs.account.move._post`` calls ``env.ref()`` on analytic
    accounts for EVERY move, not only invoices
    (``dto_account_cogs/models/account_move.py:24``, :220-231). A missing
    one makes every ``action_post`` in this suite raise ValueError, and the
    symptom would be attributed to the export rather than to the
    environment.
    """
    rpc = ctx.adapter.rpc
    missing = [x for x in COGS_ANALYTIC_XMLIDS if not rpc.ref(x)]
    if missing:
        ctx.blocked(
            "These analytic-account xmlids do not resolve on "
            f"{ctx.env.key}: {', '.join(missing)}. dto_account_cogs "
            "resolves them with env.ref() inside _post, so while they are "
            "missing EVERY journal entry this suite tries to post raises "
            "ValueError and nothing about the export can be observed.")


def template_id(ctx) -> int:
    """The SHIPPED export template, never a substitute."""
    rpc = ctx.adapter.rpc
    tid = rpc.ref(TEMPLATE_XMLID)
    if not tid:
        ctx.blocked(
            f"{TEMPLATE_XMLID} does not resolve on {ctx.env.key}. That "
            f"record carries Workday's own {TEMPLATE_FILE_NAME} and its 24 "
            "column mappings; without it there is no column contract to "
            "assert.")
    return tid


def company_id(rpc) -> int:
    return m2o_id(rpc.read("res.users", [rpc.uid], ["company_id"])[0]
                  ["company_id"])


# -------------------------------------------------------- export plumbing
def make_server(rpc, action="POST", label=None) -> int:
    """An sftp.server fixture that can never connect (convention rule 4)."""
    return rpc.create("sftp.server", {
        "name": fx(f"{MARK} {label or ('Workday ' + action)}"),
        "host": "sftp.qa-never-resolves.invalid",
        "port": "22",
        "username": "qa-wf017",
        "password": "not-a-real-credential",
        "action": action,
        "active": False,
        "archive_auto": False,
    })


def make_folder(rpc, server_id, usage=JOURNAL_ENTRY_USAGE,
                label="out") -> int:
    values = {
        "server_id": server_id,
        "path": f"/{MARK}/{fixture_token()}/{label}",
        "usage": usage,
        "active": True,
    }
    if rpc.field_exists("sftp.folder", "duplicate_policy"):
        values["duplicate_policy"] = "allow"
    return rpc.create("sftp.folder", values)


def retarget_company(ctx, folder_id=None, template_ref=None,
                     clear_folder=False, clear_template=False):
    """Point res.company at this execution's fixture configuration.

    Returns (company_id, original) so the caller's ``finally`` can restore
    it. ``clear_folder`` / ``clear_template`` are TC314's mis-configuration
    cases; they write False rather than a fixture value.
    """
    rpc = ctx.adapter.rpc
    cid = company_id(rpc)
    fields_ = ["workday_journal_entry_sftp_folder_id",
               "workday_journal_entry_template_id"]
    before = rpc.read("res.company", [cid], fields_)[0]
    original = {f: m2o_id(before.get(f)) or False for f in fields_}
    values = {}
    if clear_folder:
        values["workday_journal_entry_sftp_folder_id"] = False
    elif folder_id is not None:
        values["workday_journal_entry_sftp_folder_id"] = folder_id
    if clear_template:
        values["workday_journal_entry_template_id"] = False
    elif template_ref is not None:
        values["workday_journal_entry_template_id"] = template_ref
    if values:
        rpc.write("res.company", [cid], values)
    ctx.log(f"company {cid} retargeted: {values!r} (was {original!r})")
    return cid, original


def set_company(ctx, cid, values):
    """A bare write used by TC314 between its four mis-configurations."""
    ctx.adapter.rpc.write("res.company", [cid], values)
    ctx.log(f"company {cid} -> {values!r}")


def restore_company(ctx, cid, original):
    """Put the live Workday configuration back. Never raises."""
    try:
        ctx.adapter.rpc.write("res.company", [cid], original)
        ctx.log(f"company {cid} configuration restored: {original!r}")
    except OdooRPCError as exc:                            # pragma: no cover
        ctx.log(f"[warn] could not restore company {cid} configuration "
                f"({exc}). sweep_wf017 repairs the folder half on the next "
                f"run; the value to restore is {original!r}.")


# -------------------------------------------------------------- fixtures
def fixture_source_id(ctx) -> int:
    """A real account.journal.workday record for the fixture journal."""
    rpc = ctx.adapter.rpc
    source_id = rpc.ref(FIXTURE_SOURCE_XMLID)
    if source_id:
        return source_id
    rows = rpc.search_read("account.journal.workday", [], ["id_workday"],
                           limit=1)
    if not rows:
        ctx.blocked(
            "account.journal.workday is EMPTY on this target — the 131-row "
            "catalogue did not load. Column T is a required Workday column "
            "and there is no source for it to resolve to, so every export "
            "in this suite would withhold every move.")
    ctx.log(f"[warn] {FIXTURE_SOURCE_XMLID} does not resolve; falling back "
            f"to catalogue record {rows[0]!r}")
    return rows[0]["id"]


_JOURNAL_SEQ = {"n": 0}


def _journal_code(suffix="") -> str:
    """A short, token-scoped journal code, UNIQUE PER CALL.

    ``account.journal.code`` is ``size=5`` and unique per company — measured
    on d1v19. The previous version derived the whole code from the
    execution token, so every journal a case created inside one run got the
    SAME code and the second create raised "Journal codes must be unique
    per company". TC312 and TC313 both build more than one journal, and
    both died on it.

    The layout is one marker character, two token characters and a
    two-character counter, which is exactly five and leaves the code
    traceable to its run. The NAME still carries the marker, and
    ``sweep_wf017`` still matches on the name.
    """
    _JOURNAL_SEQ["n"] += 1
    alphabet = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    counter = _JOURNAL_SEQ["n"] % 1296          # two base-36 characters
    tag = alphabet[counter // 36] + alphabet[counter % 36]
    # `suffix` is kept in the signature because callers pass it to mean "a
    # different family of journal"; it is folded into the counter space
    # rather than appended, because five characters is the whole budget.
    if suffix:
        tag = suffix[0].upper() + alphabet[counter % 36]
    return f"{MARK[:1]}{fixture_token()[:2].upper()}{tag}"


def make_journal(ctx, source_id=None, label="Misc",
                 journal_type="general") -> int:
    """A token-scoped account.journal carrying a real catalogue source.

    A NEW journal rather than a live one, deliberately: pointing an
    existing journal at a different Workday source would change live
    configuration, and ``journal_workday_id`` is ``tracking=True`` so the
    change would also land in that journal's chatter.
    """
    rpc = ctx.adapter.rpc
    return rpc.create("account.journal", {
        "name": fx(f"{MARK} {label}"),
        "code": _journal_code(),
        "type": journal_type,
        "journal_workday_id": source_id or fixture_source_id(ctx),
    })


def make_bare_journal(ctx, label="NoSource", journal_type="general") -> int:
    """A journal with NO Workday source at all — column T resolves empty.

    This is TC312's failure mechanism expressed the simplest way that the
    product's own constraints allow: ``get_journal_workday(False)`` returns
    the empty ``journal_workday_id``, so ``export_workday_journal_workday``
    is falsy and required column T fails for every line of the move.
    """
    rpc = ctx.adapter.rpc
    return rpc.create("account.journal", {
        "name": fx(f"{MARK} {label}"),
        "code": _journal_code("X"),
        "type": journal_type,
    })


def any_account(rpc, account_type=None, exclude=()):
    """One posted-usable account.account id, or None."""
    domain = [("deprecated", "=", False)] \
        if rpc.field_exists("account.account", "deprecated") else []
    if account_type:
        domain.append(("account_type", "=", account_type))
    if exclude:
        domain.append(("id", "not in", list(exclude)))
    rows = rpc.search_read("account.account", domain,
                           ["code", "name", "account_type"], limit=1,
                           order="code")
    return rows[0] if rows else None


def two_accounts(ctx):
    """(debit_account, credit_account) — two distinct usable accounts."""
    rpc = ctx.adapter.rpc
    first = any_account(rpc)
    if not first:
        ctx.blocked("No usable account.account exists on this target, so no "
                    "journal entry can be built.")
    second = any_account(rpc, exclude=[first["id"]])
    if not second:
        ctx.blocked("Only one account.account exists, so a balanced "
                    "two-line entry cannot be built.")
    return first, second


def make_entry(ctx, journal_id, lines, ref_suffix, date="2026-03-15",
               post=True):
    """A miscellaneous journal entry (``move_type='entry'``).

    ``lines`` is a list of dicts merged over a default line; each must
    carry ``account_id`` and either ``debit`` or ``credit``. The entry has
    to balance or ``action_post`` refuses it.
    """
    rpc = ctx.adapter.rpc
    invoice_lines = []
    for index, line in enumerate(lines, start=1):
        values = {"name": fx(f"{MARK} {ref_suffix} L{index}"),
                  "debit": 0.0, "credit": 0.0}
        values.update(line)
        invoice_lines.append((0, 0, values))
    move_id = rpc.create("account.move", {
        "move_type": "entry",
        "journal_id": journal_id,
        "date": date,
        "ref": move_ref(ref_suffix),
        "line_ids": invoice_lines,
    })
    if post:
        rpc.call("account.move", "action_post", [move_id])
        row = rpc.read("account.move", [move_id], ["state"])[0]
        if row["state"] != "posted":
            ctx.blocked(
                f"Fixture entry {move_id} did not post "
                f"(state={row['state']!r}). WF-017 only ever exports posted "
                "entries, so nothing can be observed against a draft one.")
    return move_id


def balanced_lines(ctx, amount=100.0, extra=None):
    """A minimal balanced pair, plus any extra lines the caller appends."""
    debit_account, credit_account = two_accounts(ctx)
    lines = [
        {"account_id": debit_account["id"], "debit": amount},
        {"account_id": credit_account["id"], "credit": amount},
    ]
    if extra:
        lines.extend(extra)
    return lines, debit_account, credit_account


# ------------------------------------------------------------- the export
def open_export_wizard(ctx, move_ids):
    """Press 'Export to Workday'; return the wizard id.

    ``action_export_workday_journal_entry`` is public and runs
    ``_check_condition_sync_journal_entry`` BEFORE returning the wizard
    action — which is exactly what TC315 step 6 asserts, so the blocking
    checks are reached through this entry point rather than by calling the
    private method.
    """
    rpc = ctx.adapter.rpc
    action = rpc.call("account.move", "action_export_workday_journal_entry",
                      list(move_ids))
    if not isinstance(action, dict) or not action.get("res_id"):
        ctx.blocked(
            "action_export_workday_journal_entry returned "
            f"{action!r} instead of an act_window carrying the wizard's "
            "res_id. The wizard is the only supported entry point to the "
            "export, so the suite cannot continue.")
    return action["res_id"]


def run_export(ctx, move_ids, mark_exported=True, wizard_id=None):
    """Drive the real export end to end, with no network.

    ``mark_exported`` mirrors the two footer buttons:
    'Export and Mark as exported' carries ``context={'mark_exported': 1}``
    and 'Export only' carries none
    (``wizard/workday_journal_entry_export_wizard.xml:39-44``). TC310 is
    entirely the difference between them.
    """
    rpc = ctx.adapter.rpc
    if wizard_id is None:
        wizard_id = open_export_wizard(ctx, move_ids)
    context = {"mark_exported": 1} if mark_exported else {}
    notification = rpc.call(
        "workday.journal.entry.export.wizard",
        "action_execute_export_workday_journal_entry", [wizard_id],
        context=context)
    ctx.log(f"wizard {wizard_id} returned: {notification!r}")
    return wizard_id, notification


def notification_type(notification) -> str:
    if not isinstance(notification, dict):
        return ""
    return ((notification.get("params") or {}).get("type")) or ""


def notification_message(notification) -> str:
    if not isinstance(notification, dict):
        return ""
    params = notification.get("params") or {}
    return f"{params.get('title') or ''} {params.get('message') or ''}".strip()


def produced_files(rpc, folder_id, fields_=None):
    fields_ = fields_ or ["name", "ref", "state", "res_model", "res_id",
                          "attachment_id", "usage", "action", "process_date"]
    return rpc.search_read("sftp.file", [("folder_id", "=", folder_id)],
                           fields_, order="id")


def latest_workbook(ctx, folder_id):
    """(sftp.file row, worksheet, raw bytes) for the newest produced file."""
    import openpyxl

    rpc = ctx.adapter.rpc
    rows = produced_files(rpc, folder_id)
    if not rows:
        ctx.blocked(
            f"The export produced no sftp.file in fixture folder "
            f"{folder_id}. WorkdayLoader only creates one when "
            "data.template.export.execute_export returned an attachment, "
            "so either every move failed a required column — which on v19 "
            "is the PREDICTED outcome for blank column T — or the template "
            "produced no rows. Read the wizard's notification message.")
    row = rows[-1]
    attachment_id = m2o_id(row.get("attachment_id"))
    if not attachment_id:
        ctx.blocked(f"sftp.file {row['id']} carries no attachment_id — the "
                    "produced workbook cannot be read.")
    datas = rpc.read("ir.attachment", [attachment_id], ["datas", "name"])[0]
    raw = base64.b64decode(datas["datas"])
    workbook = openpyxl.load_workbook(io.BytesIO(raw))
    if TEMPLATE_SHEET not in workbook.sheetnames:
        ctx.check(f"sheet {TEMPLATE_SHEET!r} exists in the produced workbook",
                  expected=TEMPLATE_SHEET, actual=workbook.sheetnames)
    return row, workbook[TEMPLATE_SHEET], raw


def template_workbook(ctx, tid):
    """The SHIPPED template's own sheet — TC306 step 10's comparison base."""
    import openpyxl

    rpc = ctx.adapter.rpc
    data = rpc.read("data.template.export", [tid], ["template_data"])[0]
    raw = base64.b64decode(data["template_data"])
    workbook = openpyxl.load_workbook(io.BytesIO(raw))
    return workbook[TEMPLATE_SHEET], raw


def save_workbook(ctx, raw: bytes, name: str):
    path = ctx.artifacts_dir / name
    path.write_bytes(raw)
    ctx.add_artifact(path, "file", name)
    return path


def populated_rows(sheet, columns=None, row_start=TEMPLATE_ROW_START,
                   scan=400):
    """Row indices at or after ``row_start`` carrying any mapped value.

    A bounded window rather than ``sheet.max_row``, which reports the
    template's own formatting extent.
    """
    columns = columns or sorted({col for col, _f, _r in COLUMN_CONTRACT})
    rows = []
    for index in range(row_start, row_start + scan):
        if any(sheet[f"{col}{index}"].value not in (None, "")
               for col in columns):
            rows.append(index)
    return rows


def rows_by_move(sheet, rows):
    """{move id in column B: [(row index, AI value)]} — TC306 steps 15/17."""
    grouped = {}
    for index in rows:
        grouped.setdefault(sheet[f"{MOVE_ID_COLUMN}{index}"].value,
                           []).append(
            (index, sheet[f"{ROW_INDEX_COLUMN}{index}"].value))
    return grouped


def exportable_lines(rpc, move_id):
    """The lines the exporter snapshots, in the order it numbers them.

    ``workday.journal.entry._prepare_domain_workday_journal_entry``
    (``workday_journal_entry.py:173-180``) filters ``display_type not in
    ('line_section', 'line_note')`` AND ``balance != 0`` over
    ``move_id.line_ids``, and ``get_export_workday_id_row_journal_entry``
    numbers by position in that filtered set.

    NOTE (v19, delta §2.5): ``display_type`` gained ``line_subsection`` and
    three ``non_deductible_*`` values. The product's filter names only the
    two old ones, so a subsection line WOULD become a spreadsheet row. This
    mirror keeps the product's filter deliberately, so a test reports the
    product's behaviour rather than a corrected version of it — that is
    TC308 steps 11-12.
    """
    return rpc.search_read(
        "account.move.line",
        [("move_id", "=", move_id),
         ("display_type", "not in", ["line_section", "line_note"]),
         ("balance", "!=", 0)],
        ["display_type", "name", "balance", "debit", "credit", "account_id",
         "analytic_distribution", "ref", "date"], order="id")


def all_lines(rpc, move_id):
    """Every line of a move, filtered or not — the independent count."""
    return rpc.search_read(
        "account.move.line", [("move_id", "=", move_id)],
        ["display_type", "balance", "debit", "credit", "account_id", "name"],
        order="id")


def snapshot_of(rpc, line_ids):
    """The mapped ``export_workday_*`` values per account.move.line."""
    fields_ = ["move_id"] + sorted({f for _c, f, _r in COLUMN_CONTRACT})
    rows = rpc.read("account.move.line", sorted(line_ids), fields_)
    return {row["id"]: row for row in rows}


def cell_map(sheet, row_index):
    """{column: value} for one data row, over the 24 mapped columns."""
    return {col: sheet[f"{col}{row_index}"].value
            for col, _f, _r in COLUMN_CONTRACT}


def journal_source_of(rpc, move_id):
    """(entry_type, id_workday) as the export will resolve them."""
    row = rpc.read("account.move", [move_id],
                   ["entry_type", "journal_workday_id", "journal_id"])[0]
    source_id = m2o_id(row.get("journal_workday_id"))
    id_workday = ""
    if source_id:
        id_workday = rpc.read("account.journal.workday", [source_id],
                              ["id_workday"])[0]["id_workday"]
    return row.get("entry_type"), id_workday, row


def live_entry_type_matrix(rpc):
    """The derivation asserted over the LIVE population, read-only.

    For every posted move carrying an ``entry_type``, group by
    (entry_type, journal id_workday) and count. That is TC309's matrix
    taken against tens of thousands of real moves rather than seven
    synthetic ones — and it is the assertion that detects a blank column T
    without producing a workbook at all.
    """
    grouped = rpc.read_group(
        "account.move",
        [("entry_type", "!=", False), ("state", "=", "posted")],
        ["__count"], ["entry_type", "journal_workday_id"], lazy=False)
    source_ids = sorted({m2o_id(g["journal_workday_id"]) for g in grouped
                         if g.get("journal_workday_id")})
    id_workday = {}
    if source_ids:
        id_workday = {row["id"]: row["id_workday"] for row in
                      rpc.read("account.journal.workday", source_ids,
                               ["id_workday"])}
    matrix = {}
    for group in grouped:
        key = (group.get("entry_type") or "",
               id_workday.get(m2o_id(group.get("journal_workday_id")), ""))
        matrix[key] = matrix.get(key, 0) + group.get("__count", 0)
    return matrix


def activities_on(rpc, model, res_ids, fields_=None):
    if not res_ids:
        return []
    fields_ = fields_ or ["res_model", "res_id", "summary", "note",
                          "user_id", "date_deadline", "activity_type_id"]
    return rpc.search_read("mail.activity",
                           [("res_model", "=", model),
                            ("res_id", "in", list(res_ids))],
                           fields_, order="id")


def expect_error(rpc_callable, *args, **kwargs):
    try:
        rpc_callable(*args, **kwargs)
        return False, "no error raised"
    except OdooRPCError as exc:
        return True, str(exc)


def cron_row(rpc, xmlid):
    """One ir.cron by xml id, with its code — identity is module.name."""
    module, _, name = xmlid.partition(".")
    data = rpc.search_read("ir.model.data",
                           [("model", "=", "ir.cron"),
                            ("module", "=", module), ("name", "=", name)],
                           ["res_id"], limit=1)
    if not data:
        return None
    fields_ = [f for f in ("cron_name", "active", "interval_number",
                           "interval_type", "code", "priority")
               if rpc.field_exists("ir.cron", f)]
    row = rpc.read("ir.cron", [data[0]["res_id"]], fields_)[0]
    row["xml_id"] = xmlid
    return row
