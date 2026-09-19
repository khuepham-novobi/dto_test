"""Shared fixtures and helpers for the DATAONE-WF-018 suite
(Vendor Bill Export to Workday).

Owning workflow: DATAONE-WF-018, build order 21, **Stage 6 — Workday
integrations (need the documents they carry to exist first)**, risk
CRITICAL, 14.5 h, depends on WF-016. It owns 12 workbook test cases:
TC035, TC296, TC300, TC304, TC316, TC317, TC318, TC319, TC320, TC321,
TC322 and TC326. TC035, TC296, TC300 and TC304 are shared with WF-017;
TC326 is shared with WF-019.

What this workflow is
---------------------
DataOne executes its payment run in Workday, not in Odoo. This flow is
the outbound half: posted, attachment-bearing, tax-free vendor bills are
snapshotted line by line into 21 ``export_workday_*`` fields, written into
a copy of Workday's own ``Bulk_Import_Submit_Supplier_Invoice_v43.0.xlsx``
at 20 mapped columns, and handed to the SFTP POST folder as a Pending
``sftp.file``. WF-019 brings the resulting payment back.

The feasibility fact that decides this suite
--------------------------------------------
**Everything except the upload is local.** Verified source chain:

    account.move.action_export_workday_vendor_bill()       (public)
      -> workday.vendor.bill.export.wizard                 (public)
        -> action_execute_export_workday_vendor_bill()     (public)
          -> account.move.execute_export_workday_vendor_bill()
            -> ETLProcessor(WorkdayExtractor/Transformer/Loader)
              -> data.template.export.execute_export()     (openpyxl, local)
                -> sftp.file.create_sftp_file()            (a DB record)

``WorkdayLoader._run_loader_workday_vendor_bill`` only *creates* the
``sftp.file`` in state ``pending``. The network hop is a different cron
entirely — ``novobi_sftp_connection.cron_post_sftp_files`` ->
``sftp.folder.action_post_files`` -> ``SFTPConnection.send_files``. So the
whole export is drivable with no network at all, and the produced workbook
is readable over RPC as ``ir.attachment.datas`` and parsed here with
openpyxl (pinned ``openpyxl>=3.1`` in ``requirements.txt``).

That is why TC316, TC317, TC318, TC319, TC322 and TC326 are implemented
rather than blocked, and why TC296, TC300 and TC304 — which are about the
*upload* — are blocked stubs.

Two rules this suite has to work hard to respect
------------------------------------------------
**Rule 3 — never modify pre-existing business records.**
``account.move.cron_export_workday_vendor_bill()`` is public and would
dispatch over RPC, but it searches ``_prepare_domain_workday_vendor_bill()``
**with no limit** and runs with ``mark_exported=True``. Calling it on a
clone of the client's database would flag *every* eligible live bill as
exported to Workday, permanently removing them from the real export queue.
**Nothing in this suite ever calls it.** The cron's shape is asserted by
reading ``ir.cron.code`` instead (TC321's automatable half), and every
export runs through the wizard against an explicit fixture id list.

**Rule 4 — never trigger outbound integrations.** The fixture SFTP server
is created ``active=False`` with an unroutable ``.invalid`` host, so
``cron_post_sftp_files`` (which searches active servers) can never pick up
the files this suite produces. No test calls ``action_post_files``,
``send_files``, ``get_sftp_connection`` or ``action_repost``.

The company-configuration hazard
--------------------------------
``execute_export_workday_vendor_bill`` reads its destination off
``self.env.company``::

    company._check_export_workday_vendor_bill_setting()   # res_company.py:40
    ...workday_vendor_bill_sftp_folder_id / ...workday_vendor_bill_template_id

Those are live configuration. ``retarget_company`` below repoints them at
this execution's fixture folder and ``restore_company`` puts the originals
back in a ``finally`` that can never raise; ``sweep_wf018`` additionally
repairs a company still pointing at any WF018-marked folder, so a hard
crash in a previous run is self-healing. The *template* is never
substituted — the whole point of TC317 is the shipped 20-row contract, so
``dto_account_workday.template_export_workday_vendor_bill`` is used as-is.

The attachment route matters
----------------------------
``have_attachment`` is ``store=True`` with ``@api.depends('attachment_ids')``
(``dto_account/models/account_move.py:14-31``) over a domain-filtered
One2many. Creating an ``ir.attachment`` pointing AT the move does not
reliably invalidate it — that is TC319's whole subject, and ``dto_account``
carries its own test recording the same defect (E3,
``tests/test_wf016_vendor_bill.py:126-159``). Fixtures that need to POST a
bill therefore attach via ``attachment_ids`` on the move
(``attach_to_move(..., via="move")``); TC319 uses both routes deliberately.

EXPECTED v17/v19 OUTCOME is stated per test in each module's docstring.
"""
from __future__ import annotations

import base64
import io
import uuid

from adapters.base import OdooRPCError
from framework.fg_common import form_arch, list_tag, m2o_id, make_trace  # noqa: F401
from framework.qa_fixtures import sweep_model, sweep_products, with_categ  # noqa: F401

WORKFLOW = "DATAONE-WF-018"
WORKFLOW_NAME = "Vendor Bill Export to Workday"
FEATURE = "DATAONE-WF-018 Vendor Bill Export to Workday"
MARK = "WF018"

trace = make_trace(FEATURE)

# ---------------------------------------------------------------- source
# dto_account_workday/models/account_move.py:68-74. Mirrored rather than
# called: the method is a @staticmethod whose name starts with an
# underscore, so Odoo's check_method_name refuses to dispatch it over RPC
# (v17 odoo/models.py:145, v19 odoo/orm/utils.py:69).
# TEST-WF018-TC319 asserts this mirror still selects what the product's own
# cron selects, by comparing the id sets.
VENDOR_BILL_EXPORT_DOMAIN = [
    ("move_type", "=", "in_invoice"),
    ("state", "=", "posted"),
    ("export_workday", "=", False),
    ("have_attachment", "=", True),
]

# dto_account_workday/models/account_move.py:87-97 — the three blocking
# strings, verbatim, including capitalisation and the absent full stop.
# TEST-WF018-TC318 is entirely these three.
ERR_EMPTY_SELECTION = "Please select at least one record"
ERR_NOT_POSTED = "Please select posted vendor bills only"
ERR_HAS_TAX = "Selected vendor bills contain taxes, which is not yet supported"

# utils/workday_sftp_sdk/etl_processor/workday_extractor.py:36-37 — the
# non-blocking per-bill message the duplicate-ref guard files as an
# activity. Asserted as a prefix because the product appends nothing today
# but the workbook (TC316 step 16) requires the whole string to be quoted.
ERR_DUPLICATE_REF_PREFIX = 'Field "Bill Reference" must be unique'
ERR_TAX_NOT_SUPPORTED = "Tax export is not yet supported"

# WorkdayLoader._run_loader_workday_vendor_bill:155 / :152
ACTIVITY_SUMMARY = "Cannot export data from this vendor bill"
ACTIVITY_TYPE_XMLID = "mail.mail_activity_data_warning"

# data/data_template_export_data.xml:3-33 — the shipped template record and
# the workbook it carries.
TEMPLATE_XMLID = "dto_account_workday.template_export_workday_vendor_bill"
TEMPLATE_SHEET = "Bulk Import Submit Supplier Inv"
TEMPLATE_FILE_NAME = "Bulk_Import_Submit_Supplier_Invoice_v43.0.xlsx"
TEMPLATE_ROW_START = 6

VENDOR_BILL_USAGE = "workday_vendor_bill"
VENDOR_PAYMENT_USAGE = "workday_vendor_payment"

# account_payment.py — the eight column names the payment ETL reads by key.
# They are Workday labels with spaces and apostrophes replaced by
# underscores; Supplier_s_Invoice_Number in particular is a mangled
# possessive that a Workday-side report change would alter. A missing key
# is a bare KeyError inside the transform today (:159, :168, :181), not a
# named error.
PAYMENT_CSV_COLUMNS = [
    "Supplier_Payment",             # -> payment.workday_document  (:105)
    "Supplier_Invoice_Document",    # -> bill.workday_document     (:181)
    "Supplier_s_Invoice_Number",    # fallback bill match          (:137-141)
    "Document_Link",                # primary bill match           (:127-135)
    "Payment_Amount",               # residual guard + amount      (:166, :107)
    "Payment_Date",                 # required                     (:95, :106)
    "Payment_Type",                 # -> payment method line NAME  (:63-67)
    "Transaction_Reference",        # -> payment.memo -> move.ref  (:119)
]

EXPORT_CRON_XMLID = "dto_account_workday.ir_cron_export_workday_vendor_bills"
JOURNAL_CRON_XMLID = "dto_account_workday.ir_cron_export_workday_journal_entries"
POST_CRON_XMLID = "novobi_sftp_connection.ir_cron_post_sftp_files"

# The 20-row column contract, exactly as data_template_export_data.xml
# declares it: column -> (field on account.move.line, required?).
# TEST-WF018-TC317 asserts the produced workbook against this table AND
# asserts that this table still equals what the database holds, so a
# template edit cannot make the test pass by drifting with it.
COLUMN_CONTRACT = [
    ("B", "export_workday_id_move", True),
    ("I", "export_workday_submit", False),
    ("Q", "export_workday_date", False),
    ("R", "export_workday_company", True),
    ("U", "export_workday_vendor_ref", True),
    ("AF", "export_workday_invoice_date", False),
    ("AR", "export_workday_price_total", False),
    ("BD", "export_workday_ref", False),
    ("BE", "export_workday_purchase", False),
    ("BH", "export_workday_url", False),
    ("BN", "export_workday_payment_term", False),
    ("EA", "export_workday_id_row", True),
    ("EF", "export_workday_name", False),
    ("EM", "export_workday_spend_category", False),
    ("FS", "export_workday_quantity", False),
    ("FT", "export_workday_product_uom", False),
    ("FU", "export_workday_price_unit", False),
    ("GG", "export_workday_account_project_name", False),
    ("GI", "export_workday_account_cost_center_name", False),
    ("GK", "export_workday_account_customer_contract_name", False),
]
REQUIRED_COLUMNS = [col for col, _f, req in COLUMN_CONTRACT if req]

# workday_vendor_bill.py:56/66/71 — three tenant constants in Python, not
# configuration. TC317 step 9 records that fact as much as it asserts it.
HARDCODED_CELLS = {"I": "Y", "R": "DOS", "EM": "Consumables", "GI": "170002"}

# TC317 step 6 — wide unmapped columns that must stay untouched. The Workday
# workbook is far wider than the populated set and carries its own
# validation in the columns nobody writes.
UNMAPPED_SPOT_CHECK = ["C", "AA", "CC", "DD", "EB", "FA", "GH", "GJ", "GZ"]

# The predicted v19 silent break (§2.10, the v18 UoM rework). FT is NOT a
# required column, so F198 withholds nothing when it goes blank — TC317
# step 4 and TC322 exist because no other assertion would catch it.
UOM_COLUMN = "FT"
ANALYTIC_COLUMNS = {"project": "GG", "contract": "GK"}

# dto_account/models/account_analytic_plan.py:6-12 — the xml ids
# get_analytic_plan() resolves. GG reads the 'project' bucket and GK the
# 'contract' one; 'cost' is NOT read by this flow (GI is the hard-coded
# '170002'), which is itself worth knowing when GI ever disagrees.
ANALYTIC_PLAN_XMLIDS = {
    "project": "dto_account.project_analytic_plan",
    "cost": "dto_account.cost_center_analytic_plan",
    "contract": "dto_account.customer_contract_analytic_plan",
    "spend_categ": "dto_account.spend_category_analytic_plan",
    "revenue_categ": "dto_account.revenue_category_analytic_plan",
}

_TOKEN = "init"


def fixture_token() -> str:
    return _TOKEN


def fx(name: str) -> str:
    """Namespace a fixture value for this execution."""
    return f"{name} [{_TOKEN}]"


def bill_ref(suffix: str) -> str:
    """A bill ``ref`` for this execution: 'WF018-<token>-GAMMA-101'.

    The duplicate guard keys on ``account.move.ref``
    (``workday_extractor.py:31-35``), so a token-scoped ref is what makes
    "exactly one prior bill carries this ref" deterministic against a live
    AP ledger. The MARK- prefix is what ``sweep_wf018`` matches on.
    """
    return f"{MARK}-{_TOKEN}-{suffix}"


# ------------------------------------------------------------------ sweep
def sweep_wf018(rpc):
    """Open a fresh fixture namespace, then remove marker-scoped leftovers.

    Best-effort by design: a POSTED vendor bill cannot be unlinked once it
    carries an inalterable hash, and this suite's whole subject is posted
    bills. The fresh token is what guarantees isolation — every search in
    every test is token-scoped, so a survivor cannot contaminate an
    "exactly N rows" assertion.

    Order matters: sftp.file rows reference folders, folders reference
    servers, and ``sftp.folder._check_unique_folder`` runs with
    ``active_test=False``, so leftovers must be REMOVED rather than
    archived or the next execution's folder creation is refused.
    """
    global _TOKEN
    _TOKEN = uuid.uuid4().hex[:6]

    # 0. Repair a company still pointing at a WF018 fixture folder — the
    #    self-healing half of retarget_company, for the case where a
    #    previous execution died between the write and its finally.
    stale = rpc.search("sftp.folder", [("path", "like", f"/{MARK}/%"),
                                       ("active", "in", [True, False])])
    if stale:
        for field in ("workday_vendor_bill_sftp_folder_id",
                      "workday_journal_entry_sftp_folder_id"):
            if not rpc.field_exists("res.company", field):
                continue
            hit = rpc.search("res.company", [(field, "in", stale)])
            if hit:
                try:
                    rpc.write("res.company", hit, {field: False})
                except OdooRPCError:
                    pass

    # 1. Moves. Draft first, then unlink; a posted move survives both and
    #    that is accepted.
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
    sweep_model(rpc, "account.analytic.account",
                [("name", "like", f"{MARK} %"),
                 ("active", "in", [True, False])])
    sweep_model(rpc, "res.partner", [("name", "like", f"{MARK} %"),
                                     ("user_ids", "=", False),
                                     ("active", "in", [True, False])])
    sweep_model(rpc, "ir.attachment",
                [("name", "like", f"{MARK} %"),
                 ("res_model", "=", "data.template.export")])


# ---------------------------------------------------------------- probes
def require_workday_export(ctx):
    """BLOCK unless the outbound export stack is installed and configured.

    Probed rather than assumed, because every assertion in this suite
    becomes VACUOUS rather than failing when a piece is missing — the
    outcome convention rule 5 exists to prevent.
    """
    rpc = ctx.adapter.rpc

    missing_models = [m for m in ("sftp.server", "sftp.folder", "sftp.file",
                                 "data.template.export",
                                 "workday.vendor.bill.export.wizard")
                      if not rpc.model_exists(m)]
    if missing_models:
        ctx.blocked(
            f"Missing model(s) on {ctx.env.key} (db={ctx.env.db}): "
            f"{', '.join(missing_models)}. dto_account_workday / "
            "novobi_sftp_connection / novobi_base_export are not all "
            "installed, so there is no vendor-bill export to observe.")

    if not rpc.field_exists("account.move", "have_attachment"):
        ctx.blocked(
            "account.move.have_attachment does not exist — dto_account is "
            "not installed. It is the fourth term of "
            "_prepare_domain_workday_vendor_bill, so without it the export "
            "domain raises rather than selecting nothing.")

    if not rpc.field_exists("account.move.line", "export_workday_id_move"):
        ctx.blocked(
            "account.move.line carries no export_workday_* snapshot fields "
            "— the workday.vendor.bill AbstractModel is not inherited into "
            "account.move.line on this target, so the 20-column contract "
            "has nothing to read.")


def require_vendor_bill_usage(ctx):
    """BLOCK when dto_account_workday has not contributed the usage key."""
    rpc = ctx.adapter.rpc
    info = rpc.call("sftp.folder", "fields_get", ["usage"],
                    attributes=["selection"])
    keys = [k for k, _label in (info["usage"].get("selection") or [])]
    if VENDOR_BILL_USAGE not in keys:
        ctx.blocked(
            f"sftp.folder.usage does not offer {VENDOR_BILL_USAGE!r} on "
            f"{ctx.env.key} — dto_account_workday's selection_add did not "
            f"load. Available usage keys: {keys}")


def template_id(ctx) -> int:
    """The SHIPPED export template, never a substitute.

    TC317's subject is the vendor's own 20-row contract; building a fake
    template here would assert the test's own code. A missing record is a
    BLOCK, not a fallback.
    """
    rpc = ctx.adapter.rpc
    tid = rpc.ref(TEMPLATE_XMLID)
    if not tid:
        ctx.blocked(
            f"{TEMPLATE_XMLID} does not resolve on {ctx.env.key}. That "
            "record carries Workday's own "
            f"{TEMPLATE_FILE_NAME} and its 20 column mappings; without it "
            "there is no column contract to assert.")
    return tid


def company_id(rpc) -> int:
    return m2o_id(rpc.read("res.users", [rpc.uid], ["company_id"])[0]
                  ["company_id"])


# -------------------------------------------------------- export plumbing
def make_server(rpc, action="POST", label=None) -> int:
    """An sftp.server fixture that can never connect (convention rule 4).

    ``active=False`` keeps it out of ``cron_get_sftp_files`` and
    ``cron_post_sftp_files``, both of which search active servers, and the
    host is an unroutable ``.invalid`` name. Creating the record performs
    no I/O — ``sftp.server`` connects only from ``get_sftp_connection`` /
    ``action_test_connection`` / the crons, none of which this suite calls.
    """
    return rpc.create("sftp.server", {
        "name": fx(f"{MARK} {label or ('Workday ' + action)}"),
        "host": "sftp.qa-never-resolves.invalid",
        "port": "22",
        "username": "qa-wf018",
        "password": "not-a-real-credential",
        "action": action,
        "active": False,
        "archive_auto": False,
    })


def make_post_server(rpc, label="Workday POST") -> int:
    return make_server(rpc, action="POST", label=label)


def make_folder(rpc, server_id, usage=VENDOR_BILL_USAGE, label="out") -> int:
    return rpc.create("sftp.folder", {
        "server_id": server_id,
        "path": f"/{MARK}/{fixture_token()}/{label}",
        "usage": usage,
        "duplicate_policy": "allow",
        "active": True,
    })


def make_post_folder(rpc, server_id, usage=VENDOR_BILL_USAGE,
                     label="out") -> int:
    return make_folder(rpc, server_id, usage=usage, label=label)


def make_sftp_file(rpc, folder_id, file_name, content: bytes,
                   mimetype="text/csv") -> int:
    """An sftp.file in state 'pending' whose attachment holds ``content``.

    The attachment is created directly rather than through
    ``sftp.file.create_sftp_file``, because that helper takes a *recordset*
    for its folder argument and base64-encodes raw bytes — neither survives
    a JSON-RPC hop. The record shape is identical to what it produces.
    """
    attachment_id = rpc.create("ir.attachment", {
        "name": file_name,
        "type": "binary",
        "mimetype": mimetype,
        "datas": base64.b64encode(content).decode("ascii"),
    })
    folder = rpc.read("sftp.folder", [folder_id], ["path"])[0]
    return rpc.create("sftp.file", {
        "folder_id": folder_id,
        "ref": f"{folder['path']}/{file_name}",
        "attachment_id": attachment_id,
    })


def retarget_company(ctx, folder_id, template_ref=None):
    """Point res.company at this execution's fixture folder; return the
    original values so ``restore_company`` can put them back.

    The template is NOT substituted — see ``template_id``.
    """
    rpc = ctx.adapter.rpc
    cid = company_id(rpc)
    fields_ = ["workday_vendor_bill_sftp_folder_id",
               "workday_vendor_bill_template_id"]
    before = rpc.read("res.company", [cid], fields_)[0]
    original = {f: m2o_id(before.get(f)) or False for f in fields_}
    values = {"workday_vendor_bill_sftp_folder_id": folder_id}
    if template_ref:
        values["workday_vendor_bill_template_id"] = template_ref
    rpc.write("res.company", [cid], values)
    ctx.log(f"company {cid} retargeted: {values!r} (was {original!r})")
    return cid, original


def restore_company(ctx, cid, original):
    """Put the live Workday configuration back. Never raises."""
    try:
        ctx.adapter.rpc.write("res.company", [cid], original)
        ctx.log(f"company {cid} configuration restored: {original!r}")
    except OdooRPCError as exc:                            # pragma: no cover
        ctx.log(f"[warn] could not restore company {cid} configuration "
                f"({exc}). sweep_wf018 repairs this on the next run.")


# -------------------------------------------------------------- fixtures
def ensure_vendor(rpc, label="Vendor Gamma", ref_suffix="V-GAMMA-001") -> int:
    """A vendor whose ``ref`` is what column U carries (WF-020's output)."""
    name = fx(f"{MARK} {label}")
    found = rpc.search("res.partner", [("name", "=", name)], limit=1)
    if found:
        return found[0]
    return rpc.create("res.partner", {
        "name": name,
        "ref": bill_ref(ref_suffix),
        "supplier_rank": 1,
    })


def ensure_product(ctx, label="CMP-CONN-A", price=25.0) -> int:
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


def ensure_analytic_account(ctx, plan_id, label) -> int:
    rpc = ctx.adapter.rpc
    name = fx(f"{MARK} {label}")
    found = rpc.search("account.analytic.account",
                       [("name", "=", name),
                        ("active", "in", [True, False])], limit=1)
    if found:
        return found[0]
    return rpc.create("account.analytic.account",
                      {"name": name, "plan_id": plan_id})


def analytic_plans(ctx):
    """{'project': id, 'contract': id} — the two plans GG and GK read.

    ``get_analytic_accounts_from_distribution`` buckets by PLAN XML ID, not
    by name: ``account.analytic.plan.get_analytic_plan(plan_type)`` is
    ``env.ref(ANALYTIC_PLAN_MAPPING[plan_type])``
    (dto_account/models/account_analytic_plan.py:6-20). Resolving them any
    other way here would make GG/GK pass against a plan the product never
    consults. A missing xml id is returned as an absent key; the caller
    decides whether a partial answer is enough.
    """
    rpc = ctx.adapter.rpc
    result = {}
    for plan_type, xmlid in ANALYTIC_PLAN_XMLIDS.items():
        plan_id = rpc.ref(xmlid)
        if plan_id:
            result[plan_type] = plan_id
    return result


def attach_to_move(rpc, move_id, via="move", name=None):
    """Give a move an attachment, by either of the two routes TC319 tests.

    ``via='move'`` writes ``attachment_ids`` on the move — the route that
    invalidates the stored ``have_attachment`` compute reliably, and
    therefore the one every other fixture uses so that a bill can actually
    be posted past ``dto_account``'s gate.

    ``via='attachment'`` creates the ``ir.attachment`` pointing AT the
    move — the chatter route, whose invalidation is the defect TC319 is
    about. Never use it for a fixture that must post.
    """
    name = name or fx(f"{MARK} supplier.pdf")
    payload = base64.b64encode(b"%PDF-1.4 WF018 QA fixture").decode()
    if via == "attachment":
        return rpc.create("ir.attachment", {
            "name": name, "datas": payload,
            "res_model": "account.move", "res_id": move_id})
    return rpc.write("account.move", [move_id], {
        "attachment_ids": [(0, 0, {"name": name, "datas": payload,
                                   "res_model": "account.move"})]})


def make_bill(ctx, vendor_id, lines, ref_suffix, label="bill",
              invoice_date="2026-01-15", payment_term_id=None,
              attach=True, post=True, tax_ids=None):
    """A vendor bill shaped for this export: tax-free unless asked.

    ``lines`` is a list of dicts merged over a default line. ``tax_ids=None``
    means "no taxes", which is what makes ``amount_untaxed_signed ==
    amount_total_signed`` and therefore what lets the bill past
    ``_check_condition_sync_vendor_bill``.

    Returns the move id. Posting is attempted only when ``attach`` is True,
    because ``dto_account.account.move._post`` refuses an in_invoice with
    ``have_attachment`` False.
    """
    rpc = ctx.adapter.rpc
    invoice_lines = []
    for index, line in enumerate(lines, start=1):
        values = {
            "name": fx(f"{MARK} {label} L{index}"),
            "quantity": 1.0,
            "price_unit": 25.0,
            "tax_ids": [(6, 0, tax_ids or [])],
        }
        values.update(line)
        invoice_lines.append((0, 0, values))

    move_values = {
        "move_type": "in_invoice",
        "partner_id": vendor_id,
        "invoice_date": invoice_date,
        "date": invoice_date,
        "ref": bill_ref(ref_suffix),
        "invoice_origin": fx(f"{MARK} {label}"),
        "invoice_line_ids": invoice_lines,
    }
    if payment_term_id:
        move_values["invoice_payment_term_id"] = payment_term_id
    move_id = rpc.create("account.move", move_values)

    if attach:
        attach_to_move(rpc, move_id, via="move")
    if post and attach:
        rpc.call("account.move", "action_post", [move_id])
        state = rpc.read("account.move", [move_id], ["state"])[0]["state"]
        if state != "posted":
            ctx.blocked(
                f"Fixture bill {move_id} did not post (state={state!r}). "
                "WF-018 only ever exports posted bills, so nothing in this "
                "suite can be observed against a draft one.")
    return move_id


def payment_term_id(rpc):
    """Any payment term, for column BN. None when the database has none."""
    found = rpc.search("account.payment.term", [], limit=1)
    return found[0] if found else None


# ------------------------------------------------------------- the export
def open_export_wizard(ctx, move_ids):
    """Press 'Export to Workday' on a bill selection; return the wizard id.

    ``action_export_workday_vendor_bill`` is public and runs
    ``_check_condition_sync_vendor_bill`` BEFORE returning the wizard
    action — which is exactly what TC318 step 5 asserts, so the blocking
    checks are reached through this entry point rather than by calling the
    private method.
    """
    rpc = ctx.adapter.rpc
    action = rpc.call("account.move", "action_export_workday_vendor_bill",
                      list(move_ids))
    if not isinstance(action, dict) or not action.get("res_id"):
        ctx.blocked(
            "action_export_workday_vendor_bill returned "
            f"{action!r} instead of an act_window carrying the wizard's "
            "res_id. The wizard is the only supported entry point to the "
            "export, so the suite cannot continue.")
    return action["res_id"]


def run_export(ctx, move_ids, mark_exported=True):
    """Drive the real export end to end, with no network.

    Returns ``(wizard_id, notification)`` where ``notification`` is the
    client action the wizard returns — green ``info`` on success, red
    ``danger`` carrying the ETL message otherwise. ``mark_exported`` mirrors
    the 'Export and Mark as exported' button's ``context={'mark_exported': 1}``
    (wizard/workday_vendor_bill_export_wizard.xml:48).
    """
    rpc = ctx.adapter.rpc
    wizard_id = open_export_wizard(ctx, move_ids)
    context = {"mark_exported": 1} if mark_exported else {}
    notification = rpc.call(
        "workday.vendor.bill.export.wizard",
        "action_execute_export_workday_vendor_bill", [wizard_id],
        context=context)
    ctx.log(f"wizard {wizard_id} returned: {notification!r}")
    return wizard_id, notification


def notification_type(notification) -> str:
    """'info' (green) or 'danger' (red) from the wizard's client action."""
    if not isinstance(notification, dict):
        return ""
    return ((notification.get("params") or {}).get("type")) or ""


def produced_files(rpc, folder_id, fields_=None):
    """Every sftp.file this execution's fixture folder holds, oldest first."""
    fields_ = fields_ or ["name", "ref", "state", "res_model", "res_id",
                          "attachment_id", "usage", "action", "process_date"]
    return rpc.search_read("sftp.file", [("folder_id", "=", folder_id)],
                           fields_, order="id")


def latest_workbook(ctx, folder_id):
    """(sftp.file row, openpyxl worksheet) for the newest produced file.

    The attachment's bytes come back over RPC as base64 in
    ``ir.attachment.datas`` and are parsed locally — no filestore access
    and no network. ``data_only`` is deliberately left off: the exporter
    writes literal values, and reading the cached formula results would
    hide a cell that was never written.
    """
    import openpyxl

    rpc = ctx.adapter.rpc
    rows = produced_files(rpc, folder_id)
    if not rows:
        ctx.blocked(
            f"The export produced no sftp.file in fixture folder "
            f"{folder_id}. WorkdayLoader only creates one when "
            "data.template.export.execute_export returned an attachment, "
            "so either every bill failed its required columns or the "
            "template produced no rows.")
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


def save_workbook(ctx, raw: bytes, name: str):
    """Persist the produced workbook as a test artifact and return its path."""
    path = ctx.artifacts_dir / name
    path.write_bytes(raw)
    ctx.add_artifact(path, "file", name)
    return path


def populated_rows(sheet, columns=None, row_start=TEMPLATE_ROW_START,
                   scan=400):
    """Row indices at or after ``row_start`` carrying any mapped value.

    Scans a bounded window rather than ``sheet.max_row``: openpyxl reports
    the template's own formatting extent, which is far below the populated
    rows on an unmodified sheet and far above them on a modified one.
    """
    columns = columns or [col for col, _f, _r in COLUMN_CONTRACT]
    rows = []
    for index in range(row_start, row_start + scan):
        if any(sheet[f"{col}{index}"].value not in (None, "")
               for col in columns):
            rows.append(index)
    return rows


def cell_map(sheet, row_index):
    """{column: value} for one data row, over the 20 mapped columns."""
    return {col: sheet[f"{col}{row_index}"].value
            for col, _f, _r in COLUMN_CONTRACT}


def snapshot_of(rpc, line_ids):
    """The 20 mapped ``export_workday_*`` values per account.move.line."""
    fields_ = ["move_id"] + [f for _c, f, _r in COLUMN_CONTRACT]
    rows = rpc.read("account.move.line", sorted(line_ids), fields_)
    return {row["id"]: row for row in rows}


def exportable_lines(rpc, move_id):
    """The lines the exporter snapshots, in the order it numbers them.

    ``_prepare_domain_workday_vendor_bill`` on workday.vendor.bill
    (workday_vendor_bill.py:79) filters ``display_type not in
    ('line_section', 'line_note')`` over ``move_id.invoice_line_ids``, and
    ``get_export_workday_id_row_vendor_bill`` numbers by position in that
    filtered set. Mirrored here so EA can be predicted per line.

    NOTE (v19, delta §2.5): ``display_type`` gained ``line_subsection`` and
    three ``non_deductible_*`` values. The product's filter names only the
    two old ones, so a subsection line WOULD become a spreadsheet row. This
    mirror keeps the product's filter deliberately, so the test reports the
    product's behaviour rather than a corrected version of it.
    """
    lines = rpc.search_read(
        "account.move.line",
        [("move_id", "=", move_id),
         ("display_type", "not in", ["line_section", "line_note"])],
        ["display_type", "name", "quantity", "price_unit", "product_id",
         "analytic_distribution"], order="id")
    invoice_line_ids = set(rpc.read("account.move", [move_id],
                                    ["invoice_line_ids"])[0]
                           ["invoice_line_ids"])
    return [line for line in lines if line["id"] in invoice_line_ids]


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
    """(raised, message) — never let an expected failure escape as ERROR."""
    try:
        rpc_callable(*args, **kwargs)
        return False, "no error raised"
    except OdooRPCError as exc:
        return True, str(exc)


# ------------------------------------------------- the inbound payment leg
# TEST-WF018-TC326 closes the loop this workflow opens, so it needs the
# WF-019 import to have run. Like the supplier import, the payment
# extractor reads the sftp.file's ATTACHMENT, not SFTP
# (workday_vendor_payment_extractor.py:15-22), so the whole ETL is
# drivable with no network: build an inactive GET server, a
# workday_vendor_payment folder, an attachment holding the CSV, an
# sftp.file pointing at it, then call the PUBLIC
# sftp.file.action_process_sftp_files().
def payment_csv(rows: list[dict]) -> bytes:
    """A UTF-8 CSV whose header row is the ETL's own dict keys."""
    import csv

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=PAYMENT_CSV_COLUMNS,
                            lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({column: row.get(column, "")
                         for column in PAYMENT_CSV_COLUMNS})
    return buffer.getvalue().encode("utf-8")


def require_payment_import(ctx):
    """BLOCK unless the inbound payment leg can run at all."""
    rpc = ctx.adapter.rpc
    info = rpc.call("sftp.folder", "fields_get", ["usage"],
                    attributes=["selection"])
    keys = [k for k, _label in (info["usage"].get("selection") or [])]
    if VENDOR_PAYMENT_USAGE not in keys:
        ctx.blocked(
            f"sftp.folder.usage does not offer {VENDOR_PAYMENT_USAGE!r} on "
            f"{ctx.env.key} — dto_account_workday's payment branch is not "
            f"installed. Available usage keys: {keys}")
    if not rpc.field_exists("account.payment", "workday_document"):
        ctx.blocked(
            "account.payment.workday_document does not exist. On v17 it "
            "came free from account.payment._inherits = {'account.move': "
            "'move_id'}; v19 removed that _inherits, and this module "
            "re-declares the field as related(move_id.workday_document). "
            "Without it the payment carries no Workday identifier and "
            "TC326's whole subject is absent.")


def payment_journal(ctx):
    """A bank journal with at least one outbound payment method line.

    ``_get_workday_payment_method_line_id`` matches the CSV's
    ``Payment_Type`` against ``outbound_payment_method_line_ids.name``
    (account_payment.py:63-67), so the fixture's Payment_Type has to be a
    real line name on this database. Returns (journal_id, method_name).
    """
    rpc = ctx.adapter.rpc
    journals = rpc.search_read(
        "account.journal", [("type", "in", ["bank", "cash"])],
        ["name", "outbound_payment_method_line_ids"], order="id")
    for journal in journals:
        line_ids = journal["outbound_payment_method_line_ids"]
        if not line_ids:
            continue
        # account.payment.method.line — same model name on v17
        # (account/models/account_payment_method.py:91) and v19 (:96).
        lines = rpc.read("account.payment.method.line", line_ids, ["name"])
        if lines:
            return journal["id"], lines[0]["name"]
    ctx.blocked(
        "No bank/cash journal on this database carries an outbound payment "
        "method line. _get_workday_payment_method_line_id matches the CSV's "
        "Payment_Type against those line NAMES, so without one every "
        "imported row fails with 'Cannot find payment method ...' and the "
        "case would assert the error path rather than the stamps.")


def retarget_payment_journal(ctx, journal_id):
    """Point res.company.workday_vendor_payment_journal_id at a journal;
    return (company_id, original) for the caller's ``finally``."""
    rpc = ctx.adapter.rpc
    cid = company_id(rpc)
    field = "workday_vendor_payment_journal_id"
    before = m2o_id(rpc.read("res.company", [cid], [field])[0][field]) or False
    rpc.write("res.company", [cid], {field: journal_id})
    ctx.log(f"company {cid} payment journal -> {journal_id} (was {before})")
    return cid, {field: before}


def run_payment_import(ctx, rows, folder_id=None, file_label="payments"):
    """Drive the real WF-019 payment ETL over a CSV, with no network.

    Returns (folder_id, file_id, file row after processing).
    """
    rpc = ctx.adapter.rpc
    if folder_id is None:
        server_id = make_server(rpc, action="GET", label="Workday GET")
        folder_id = make_folder(rpc, server_id, usage=VENDOR_PAYMENT_USAGE,
                                label="in")
    file_id = make_sftp_file(rpc, folder_id,
                             fx(f"{MARK}_{file_label}.csv"),
                             payment_csv(rows))
    ctx.log(f"processing {len(rows)} payment row(s) through the real ETL "
            f"(sftp.file {file_id}, no network)")
    rpc.call("sftp.file", "action_process_sftp_files", [file_id])
    row = rpc.read("sftp.file", [file_id],
                   ["state", "process_date", "name", "ref"])[0]
    return folder_id, file_id, row


def cron_row(rpc, xmlid):
    """One ir.cron by xml id, with its code — identity is module.name."""
    module, _, name = xmlid.partition(".")
    data = rpc.search_read("ir.model.data",
                           [("model", "=", "ir.cron"),
                            ("module", "=", module), ("name", "=", name)],
                           ["res_id"], limit=1)
    if not data:
        return None
    fields_ = ["cron_name", "active", "interval_number", "interval_type",
               "code", "priority"]
    fields_ = [f for f in fields_ if rpc.field_exists("ir.cron", f)]
    rows = rpc.read("ir.cron", [data[0]["res_id"]], fields_)
    row = rows[0]
    row["xml_id"] = xmlid
    return row
