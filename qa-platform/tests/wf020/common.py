"""Shared fixtures and helpers for the DATAONE-WF-020 suite
(Supplier Master Import from Workday).

Owning workflow: DATAONE-WF-020, build order 2 (Stage 1), effective risk
HIGH. Modules under test: novobi_sftp_connection (transport),
dto_account_workday (the supplier ETL), novobi_base_export, queue_job.

The key feasibility fact for this workflow
------------------------------------------
The supplier import does **not** read from SFTP at processing time. The
extractor reads the sftp.file's *attachment*:

    WorkdaySupplierExtractor._run_extractor_workday_supplier
        attachment = sftp_file.attachment_id
        import_wizard = env['base_import.import'].create({'file': attachment.raw, ...})

(dto_account_workday/utils/workday_supplier_sftp_sdk/etl_processor/
workday_supplier_extractor.py). SFTP is only involved in *fetching* the
file onto that attachment.

So the whole extract -> transform -> load pipeline is drivable with no
network at all: build an inactive sftp.server, a workday_supplier folder,
an ir.attachment holding the CSV, an sftp.file pointing at it, then call
the PUBLIC ``sftp.file.action_process_sftp_files()``. That is what
``run_supplier_import`` below does, and it is why TC331-TC336 are
implemented rather than blocked.

Convention rule 4 is respected throughout: the fixture server is created
``active=False`` with an unroutable host, and nothing in this suite calls
``get_sftp_connection``, ``action_test_connection``, ``action_get_files``
with a real connection, or any ``cron_*`` method.

Live-DB determinism
-------------------
Every fixture carries the WF020 marker plus a per-execution token in the
values the import keys on (``ref`` and ``name`` on res.partner, ``name`` on
sftp.server, ``path`` on sftp.folder). The import matches partners on
``ref`` (``res_partner._get_existing_contact_by_reference``), so a
token-scoped ref guarantees this execution can never collide with a
previous run's leftovers or with live vendor data.

The nine CSV columns are the header row the extractor turns into dict keys
(``_convert_data_to_list_of_dict``), and they are exactly the keys
``_prepare_workday_contact_vals`` + ``_get_payment_term_for_workday_contact``
+ ``_get_state_country_for_workday_contact`` read.
"""
from __future__ import annotations

import base64
import csv
import io
import uuid

from adapters.base import OdooRPCError
from framework.fg_common import m2o_id, make_trace  # noqa: F401 — re-exported
from framework.qa_fixtures import sweep_model

WORKFLOW = "DATAONE-WF-020"
WORKFLOW_NAME = "Supplier Master Import from Workday"
FEATURE = "DATAONE-WF-020 Supplier Master Import from Workday"
MARK = "WF020"

trace = make_trace(FEATURE)

SUPPLIER_USAGE = "workday_supplier"

# The nine columns of the Workday supplier CSV, in the order the workbook
# lists them. The header row supplies the transform's dict keys verbatim.
CSV_COLUMNS = ["ref", "name", "street", "street2", "city", "zip", "phone",
               "property_supplier_payment_term_id", "state_id"]

# The ten crons the workbook's inventory names for this workflow's modules.
CRON_MODULES = ["novobi_sftp_connection", "dto_account_workday", "queue_job"]

# v19-only failure-tracking fields, split by the model that actually
# carries them. Verified in D:\Projects\odoo-19.0:
#   ir.cron.failure_count / first_failure_date  -> ir_cron.py:121-122
#   ir.cron.progress.deactivate                 -> ir_cron.py:926
#     (class IrCronProgress, _name = 'ir.cron.progress', ir_cron.py:918)
# The workbook's v19_watch note for TC460 lists all six new names under
# "ir.cron gains ...", but deactivate / done / remaining / timed_out_counter
# live on ir.cron.progress. Asserting `deactivate` against ir.cron therefore
# fails on a correct v19 target. Convention rule 6: verify before asserting.
V19_CRON_FIELDS = ["failure_count", "first_failure_date"]
V19_CRON_PROGRESS_MODEL = "ir.cron.progress"
V19_CRON_PROGRESS_FIELDS = ["deactivate"]

_TOKEN = "init"


def fixture_token() -> str:
    return _TOKEN


def fx(name: str) -> str:
    """Namespace a fixture value for this execution."""
    return f"{name} [{_TOKEN}]"


def ref_for(suffix) -> str:
    """A partner ``ref`` for this execution: 'WF020-<token>-010'.

    The import keys on ``ref``
    (``res_partner._get_existing_contact_by_reference``), so a token-scoped
    ref is what makes the upsert assertions deterministic against a live
    vendor list. The MARK- prefix is what ``sweep_wf020`` matches on.
    """
    return f"{MARK}-{_TOKEN}-{suffix}"


def sweep_wf020(rpc):
    """Open a fresh fixture namespace, then remove marker-scoped leftovers.

    Order matters: sftp.file rows reference folders, folders reference
    servers, and the folder uniqueness constraint counts ARCHIVED folders
    (``_check_unique_folder`` runs with ``active_test=False``), so leftovers
    must actually be removed rather than archived or the next execution's
    folder creation is refused.
    """
    global _TOKEN
    _TOKEN = uuid.uuid4().hex[:6]

    servers = rpc.search("sftp.server", [("name", "like", f"{MARK} %"),
                                         ("active", "in", [True, False])])
    if servers:
        folders = rpc.search("sftp.folder",
                             [("server_id", "in", servers),
                              ("active", "in", [True, False])])
        if folders:
            files = rpc.search("sftp.file",
                               [("folder_id", "in", folders),
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

    sweep_model(rpc, "res.partner", [("ref", "like", f"{MARK}-%"),
                                     ("user_ids", "=", False),
                                     ("active", "in", [True, False])])
    sweep_model(rpc, "res.partner", [("name", "like", f"{MARK} %"),
                                     ("user_ids", "=", False),
                                     ("active", "in", [True, False])])
    sweep_model(rpc, "account.payment.term",
                [("name", "like", f"{MARK} %"),
                 ("active", "in", [True, False])])
    sweep_model(rpc, "ir.attachment", [("name", "like", f"{MARK}_%")])


# ---------------------------------------------------------------- probes
def require_sftp_stack(ctx):
    """BLOCK when novobi_sftp_connection / dto_account_workday are absent."""
    rpc = ctx.adapter.rpc
    missing = [m for m in ("sftp.server", "sftp.folder", "sftp.file",
                           "sftp.log")
               if not rpc.model_exists(m)]
    if missing:
        ctx.blocked(
            f"novobi_sftp_connection is not installed on {ctx.env.key} "
            f"(db={ctx.env.db}) — missing model(s): {', '.join(missing)}. "
            "WF-020 has no transport layer to test without it.")


def require_supplier_usage(ctx):
    """BLOCK when dto_account_workday has not contributed the usage key."""
    rpc = ctx.adapter.rpc
    info = rpc.call("sftp.folder", "fields_get", ["usage"],
                    attributes=["selection"])
    keys = [k for k, _label in (info["usage"].get("selection") or [])]
    if SUPPLIER_USAGE not in keys:
        ctx.blocked(
            "sftp.folder.usage does not offer 'workday_supplier' on "
            f"{ctx.env.key} — dto_account_workday is not installed, so the "
            f"supplier ETL cannot run. Available usage keys: {keys}")


# -------------------------------------------------------------- fixtures
def make_server(rpc, label="Workday", action="GET", active=False) -> int:
    """An sftp.server fixture that can never connect.

    ``active=False`` keeps it out of ``cron_get_sftp_files``'s search, and
    the host is an unroutable .invalid name. Creating the record performs no
    I/O — ``sftp.server`` connects only from ``get_sftp_connection`` /
    ``action_test_connection`` / the crons, none of which this suite calls.
    """
    return rpc.create("sftp.server", {
        "name": fx(f"{MARK} {label}"),
        "host": "sftp.qa-never-resolves.invalid",
        "port": "22",
        "username": "qa-wf020",
        "password": "not-a-real-credential",
        "action": action,
        "active": active,
        "archive_auto": False,
    })


def make_folder(rpc, server_id, path=None, usage=SUPPLIER_USAGE,
                regex=False, active=True, label="in") -> int:
    return rpc.create("sftp.folder", {
        "server_id": server_id,
        "path": path or fx(f"/{MARK}/{label}"),
        "usage": usage,
        "regex": regex,
        "active": active,
    })


def csv_bytes(rows: list[dict], columns=None) -> bytes:
    """A UTF-8 CSV whose header row is the transform's dict keys."""
    columns = columns or CSV_COLUMNS
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({c: row.get(c, "") for c in columns})
    return buf.getvalue().encode("utf-8")


def make_sftp_file(rpc, folder_id, file_name, content: bytes) -> int:
    """An sftp.file in state 'pending' whose attachment holds ``content``.

    The attachment is created directly rather than through
    ``sftp.file.create_sftp_file``, because that helper takes a *recordset*
    for its folder argument and base64-encodes raw bytes — neither survives
    a JSON-RPC hop. The record shape is identical to what it produces.
    """
    attachment_id = rpc.create("ir.attachment", {
        "name": file_name,
        "type": "binary",
        "mimetype": "text/csv",
        "datas": base64.b64encode(content).decode("ascii"),
    })
    folder = rpc.read("sftp.folder", [folder_id], ["path"])[0]
    return rpc.create("sftp.file", {
        "folder_id": folder_id,
        "ref": f"{folder['path']}/{file_name}",
        "attachment_id": attachment_id,
    })


def supplier_row(token_ref, name, street="1 QA Way", street2="",
                 city="Austin", zip_code="78701", phone="+1-512-555-0100",
                 payment_term="", state="Texas (US)") -> dict:
    """One nine-column CSV row."""
    return {
        "ref": token_ref,
        "name": name,
        "street": street,
        "street2": street2,
        "city": city,
        "zip": zip_code,
        "phone": phone,
        "property_supplier_payment_term_id": payment_term,
        "state_id": state,
    }


def run_supplier_import(ctx, rows, file_label="suppliers",
                        columns=None, folder_id=None):
    """Drive the real supplier ETL over a CSV, with no network.

    Returns (file_id, state, message-bearing activities) after the public
    ``action_process_sftp_files`` has run. The file reaches 'done' or
    'failed' exactly as a real GET-then-process would.
    """
    rpc = ctx.adapter.rpc
    if folder_id is None:
        server_id = make_server(rpc)
        folder_id = make_folder(rpc, server_id)
    content = csv_bytes(rows, columns=columns)
    file_id = make_sftp_file(rpc, folder_id, fx(f"{MARK}_{file_label}.csv"),
                             content)
    ctx.log(f"processing {len(rows)} row(s) through the real ETL "
            f"(sftp.file {file_id}, no network)")
    rpc.call("sftp.file", "action_process_sftp_files", [file_id])
    row = rpc.read("sftp.file", [file_id],
                   ["state", "process_date", "name"])[0]
    return file_id, row


def partner_by_ref(rpc, ref, fields_=None):
    fields_ = fields_ or ["name", "ref", "street", "street2", "city", "zip",
                          "phone", "state_id", "country_id", "supplier_rank",
                          "property_supplier_payment_term_id"]
    rows = rpc.search_read("res.partner",
                           [("ref", "=", ref),
                            ("active", "in", [True, False])],
                           fields_)
    return rows[0] if rows else None


def activities_on(rpc, model, res_ids) -> list:
    if not res_ids:
        return []
    return rpc.search_read("mail.activity",
                           [("res_model", "=", model),
                            ("res_id", "in", res_ids)],
                           ["res_model", "res_id", "summary"])


def expect_error(rpc_callable, *args, **kwargs):
    """Run an RPC call the workbook expects to raise; return
    (raised: bool, message: str)."""
    try:
        rpc_callable(*args, **kwargs)
        return False, "no error raised"
    except OdooRPCError as exc:
        return True, str(exc)


def cron_rows(rpc, modules=None):
    """The ir.cron inventory with its XML ids, for the reconciliation TCs.

    ir.cron is reflected in ir.model.data like any other record, so the
    stable identity is module.name — never the database id.
    """
    modules = modules or CRON_MODULES
    data = rpc.search_read("ir.model.data",
                           [("model", "=", "ir.cron"),
                            ("module", "in", modules)],
                           ["module", "name", "res_id"])
    by_id = {d["res_id"]: f"{d['module']}.{d['name']}" for d in data}
    if not by_id:
        return []
    fields_ = ["cron_name", "active", "interval_number", "interval_type",
               "priority", "nextcall"]
    rows = rpc.search_read("ir.cron",
                           [("id", "in", list(by_id)),
                            ("active", "in", [True, False])],
                           fields_)
    for row in rows:
        row["xml_id"] = by_id[row["id"]]
    return sorted(rows, key=lambda r: r["xml_id"])
