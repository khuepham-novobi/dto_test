"""Shared fixtures and helpers for the DATAONE-WF-010 suite
(MO Test-Result Attachment Import — the "Production" data type).

Owning workflow: DATAONE-WF-010, build order 23, **Stage 6 — Workday
integrations (need the documents they carry to exist first)**, risk
CRITICAL, fail mode SILENT, 17 h, depends on WF-007. It owns 7 workbook
test cases: TC018 (shared with WF-017 and WF-026), TC344, TC345, TC346,
TC347, TC348 and TC349.

One workbook case this suite must NOT re-implement: ``DATAONE-TC299``
(the Re-process guard) is owned by WF-019 — build order 22 < 23 — and is
implemented as ``TEST-WF019-TC299``.

What this workflow is
---------------------
Shop-floor test equipment writes one per-unit test-result file — insertion
loss per fibre — to an SFTP drop as each assembly is tested. Each file must
end up as an ``ir.attachment`` on the manufacturing order that produced
that serial, so the MO carries its quality evidence for the life of the
record. **Attaching a result to the wrong MO is worse than not attaching
it at all, because it looks like evidence.**

READ THIS BEFORE TRUSTING A GREEN RUN
-------------------------------------
``dto_mrp_sftp/tests/test_wf010_parse_and_match.py`` records a measurement
taken on the v17 production copy, 14 Sep 2026::

    sftp_file, usage='mrp_attachment':  118,177 failed  /  56 done
    ir.attachment against mrp.production:                  57 rows
    last attempt 1 Jan 2026, last success 5 Dec 2025

0.047 %. So "matches the v17 baseline" for this workflow means matching a
feature that fails, and the 118,177 failures are MEASURED, not diagnosed —
they exist only in ``sftp.file.state``, not in ``sftp.log``. Every case
here proves the PORT is faithful. None of them says the workflow is fit
for purpose; that is a separate decision and it is the EM's, not a test's.

The feasibility fact that decides this suite
--------------------------------------------
Like the payment and supplier feeds, the extractor reads the
``sftp.file``'s ATTACHMENT rather than SFTP
(``mrp_attachment_extractor.py:27-39``)::

    sftp_file = self.etl_processor.get_input()
    attachment = sftp_file.attachment_id
    import_wizard = env['base_import.import'].create({'file': attachment.raw, ...})
    _, rows = import_wizard._read_file(options={'separator': ',', 'quoting': '"'})
    part_number   = rows[0][1]
    serial_number = rows[-1][0]

So the whole pipeline is drivable with no network: an inactive
``sftp.server``, an ``mrp_attachment`` folder, an ``ir.attachment``
holding the file, an ``sftp.file`` pointing at it, and the public
``sftp.file.action_process_sftp_files()``.

**And that is what makes these tests stronger than the module's own.**
``dto_mrp_sftp``'s in-process tests call ``_read_file`` directly and
re-implement the three tiers as a local ``_transform`` helper — so they
assert the PARSE and a COPY of the match, not the product's own
transformer. These cases drive the real ETL end to end and assert the
observable result: what the two diagnostic fields hold, which MO the
``ir.attachment`` landed on, and what the ``sftp.file`` says. Where a
workbook step genuinely needs ``_read_file`` in isolation, it is named and
handed back to the in-process test rather than duplicated.

The parse is the real risk, and it is positional
------------------------------------------------
``rows[0][1]`` and ``rows[-1][0]`` on a deliberately RAGGED file: the
metadata rows are 2 cells wide, the measurement rows are 4. The delta calls
``base_import._read_file`` "the single highest-value test to write before
upgrading" and this is where it bites hardest. Three failure modes, none of
which raise:

* short rows now padded   -> ``rows[0][1]`` may change meaning;
* trailing blank row kept -> ``rows[-1][0]`` is ``''`` and every match
  fails, which looks exactly like the 118,177 already in the data;
* ``rows[-1]`` is a DIFFERENT measurement row -> the evidence attaches to
  the **wrong manufacturing order**, and every green light stays on.

``TEST-WF010-TC349`` pins all three through the real ETL and persists a
cross-version baseline.

Safety
------
Nothing here posts money and nothing writes to a live MO: every fixture MO
is found through its token-scoped PRODUCT (Odoo owns the MO name), every
``stock.lot`` and ``stock.lot.custom`` row is token-scoped, and the one
assertion about live data (TC345's usage count) is READ-ONLY.
"""
from __future__ import annotations

import base64
import uuid

from adapters.base import OdooRPCError
from framework.fg_common import form_arch, m2o_id, make_trace  # noqa: F401
from framework.qa_fixtures import sweep_model, with_categ  # noqa: F401

WORKFLOW = "DATAONE-WF-010"
WORKFLOW_NAME = 'MO Test-Result Attachment Import ("Production" data type)'
FEATURE = ('DATAONE-WF-010 MO Test-Result Attachment Import '
           '("Production" data type)')
MARK = "WF010"

trace = make_trace(FEATURE)

ATTACHMENT_USAGE = "mrp_attachment"

# The two diagnostic fields dto_mrp_sftp adds to sftp.file
# (models/sftp_file.py:13-14). They are written BEFORE matching, so they are
# populated even when the match fails — which is what makes a failure
# actionable, and is TC347 step 4.
PART_FIELD = "mrp_attachment_part_number"
SERIAL_FIELD = "mrp_attachment_serial_number"

# dto_mrp_sftp/views/sftp_file_views.xml — the only data file the module
# ships. Both fields are added after `reference`, each invisible unless the
# usage is mrp_attachment.
FILE_FORM_VIEW = "dto_mrp_sftp.view_sftp_file_form_mrp_attachment"
PARENT_FILE_FORM_VIEW = "novobi_sftp_connection.view_sftp_file_form"

# mrp_attachment_extractor.py:52 — the extraction failure message. Asserted
# as a PREFIX because the captured exception text is appended, and that
# suffix is exactly what delta §2.13 changes (UserError instead of
# ImportError / ValueError).
ERR_EXTRACT_PREFIX = "Cannot extract product info from file content:"

# mrp_attachment_transformer.py:64-69 — the no-match message. Note the
# UNBALANCED HTML: a <ul> is opened and never closed. That is the live v17
# E2 defect TC347 step 6 requires to be asserted and recorded, not fixed.
ERR_NO_MATCH_HEADING = "Cannot find Manufacturing Order with product:"
ERR_NO_MATCH_PART_LABEL = "Part Number:"
ERR_NO_MATCH_SERIAL_LABEL = "Serial Number:"

# sftp_file.py:176-182 — the file-level activity.
FILE_ACTIVITY_SUMMARY = "Cannot process SFTP file"
ACTIVITY_TYPE_XMLID = "mail.mail_activity_data_warning"
SUPERUSER_ID = 1

GET_CRON_XMLID = "novobi_sftp_connection.ir_cron_get_sftp_files"
PROCESS_CRON_XMLID = "novobi_sftp_connection.ir_cron_process_sftp_files"

# The canonical sample, verbatim from the extractor's own docstring
# (mrp_attachment_extractor.py:13-23). Deliberately ragged: the metadata
# rows are 2 cells wide, RESULTS is 4, the measurement rows are 4. No
# trailing newline after the last data row — TC344's precondition, and the
# thing TC349's P2 variant changes.
SAMPLE_PART = "2FRP0M3LCPSLCPS06F"
SAMPLE_SERIAL = "908118-2334720-037/042"
SAMPLE_LOT_PREFIX = "908118-2334720"      # what tier 3's rfind('-') yields

SAMPLE_ROWS = [
    "PART#,{part}",
    "TESTER,DJ",
    "CUSTOM5,",
    "NOTES,",
    "RESULTS,,,IL(dB)",
    "SERIAL#,INPUT,OUTPUT,850nm",
    "{serial},Fiber 1 End A,Fiber 1 End B,0.479",
    "{serial},Fiber 2 End A,Fiber 2 End B,0.267",
]

_TOKEN = "init"


def fixture_token() -> str:
    return _TOKEN


def fx(name: str) -> str:
    return f"{name} [{_TOKEN}]"


def part_code(suffix: str = "") -> str:
    """A token-scoped ``product.default_code``.

    Every tier matches on ``product_id.default_code``
    (``mrp_attachment_transformer.py:21``, :51, :59), so a token-scoped
    part number is what stops a fixture file matching a live MO — and what
    makes "no other MO could have matched" provable rather than hoped for.
    The canonical part number from the docstring is preserved as a SUFFIX so
    the fixture still looks like the real thing in the evidence.
    """
    return f"{MARK}-{_TOKEN}-{SAMPLE_PART}{suffix}"


def serial_for(prefix_suffix: str = "037/042", lot: str | None = None) -> str:
    """A token-scoped serial of the real shape ``<lot>-<suffix>``.

    Tier 3 truncates at ``rfind('-')``, so the token must live in the LOT
    part rather than after the last hyphen, or the truncation would strip
    the token instead of the unit suffix.
    """
    return f"{lot or lot_name()}-{prefix_suffix}"


def lot_name(extra: str = "") -> str:
    """The lot part of the serial — token-scoped, no trailing hyphen group."""
    return f"{MARK}{_TOKEN}{extra}.908118.2334720"


def sample_file(part: str, serial: str, trailing_newline: bool = False,
                extra_measurement: str | None = None,
                rows: list[str] | None = None) -> bytes:
    """The canonical ragged file, parameterised for the TC349 variants.

    ``trailing_newline`` appends one empty line after the last data row —
    failure mode (b). ``extra_measurement`` appends one more full-width
    measurement row carrying a different serial — failure mode (c), which
    is the wrong-MO case.
    """
    lines = [line.format(part=part, serial=serial)
             for line in (rows or SAMPLE_ROWS)]
    if extra_measurement:
        lines.append(f"{extra_measurement},Fiber 3 End A,Fiber 3 End B,0.310")
    text = "\n".join(lines)
    if trailing_newline:
        text += "\n\n"
    return text.encode("utf-8")


# ------------------------------------------------------------------ sweep
def sweep_wf010(rpc):
    """Open a fresh fixture namespace, then remove marker-scoped leftovers.

    MOs carry Odoo's own reference, so they are found through the
    token-scoped PRODUCT they build, never by name — the same approach
    ``tests/wf007`` takes, and for the same reason: a token-prefixed MO name
    would produce lot numbers no operator would ever see.

    Order matters: sftp.file rows reference folders, folders reference
    servers, and ``sftp.folder._check_unique_folder`` runs with
    ``active_test=False``, so leftovers must be REMOVED rather than
    archived.
    """
    global _TOKEN
    _TOKEN = uuid.uuid4().hex[:6]

    product_domain = [("product_id.default_code", "like", f"{MARK}-%")]

    if rpc.model_exists("stock.lot.custom"):
        sweep_model(rpc, "stock.lot.custom", product_domain)

    for mo_id in rpc.search("mrp.production", product_domain):
        for method in ("action_cancel",):
            try:
                rpc.call("mrp.production", method, [mo_id])
            except OdooRPCError:
                pass
        try:
            rpc.call("mrp.production", "unlink", [mo_id])
        except OdooRPCError:
            pass

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

    sweep_model(rpc, "stock.lot", [("name", "like", f"{MARK}%")])
    sweep_model(rpc, "product.product",
                [("default_code", "like", f"{MARK}-%")])
    sweep_model(rpc, "product.template", [("name", "like", f"{MARK} %")])
    sweep_model(rpc, "product.category", [("name", "like", f"{MARK} %")])
    sweep_model(rpc, "ir.attachment", [("name", "like", f"{MARK}%")])


# ---------------------------------------------------------------- probes
def require_mrp_attachment(ctx):
    """BLOCK unless the MO-attachment import exists at all."""
    rpc = ctx.adapter.rpc

    missing = [m for m in ("sftp.server", "sftp.folder", "sftp.file",
                           "mrp.production", "stock.lot")
               if not rpc.model_exists(m)]
    if missing:
        ctx.blocked(
            f"Missing model(s) on {ctx.env.key} (db={ctx.env.db}): "
            f"{', '.join(missing)}. novobi_sftp_connection / mrp are not "
            "both installed, so there is no attachment import to observe.")

    info = rpc.call("sftp.folder", "fields_get", ["usage"],
                    attributes=["selection"])
    keys = [k for k, _label in (info["usage"].get("selection") or [])]
    if ATTACHMENT_USAGE not in keys:
        ctx.blocked(
            f"sftp.folder.usage does not offer {ATTACHMENT_USAGE!r} on "
            f"{ctx.env.key} — dto_mrp_sftp is not installed, so "
            "sftp.file._process_sftp_file never dispatches to the MO "
            f"attachment ETL. Available usage keys: {keys}")

    for field in (PART_FIELD, SERIAL_FIELD):
        if not rpc.field_exists("sftp.file", field):
            ctx.blocked(
                f"sftp.file.{field} does not exist — dto_mrp_sftp did not "
                "contribute its two diagnostic fields. They are written "
                "BEFORE matching, so without them a failure carries no "
                "part number and no serial and nothing in this suite is "
                "diagnosable.")


def require_custom_lot(ctx):
    """BLOCK when stock.lot.custom is absent — tier 1's whole subject.

    ``04-manufacturing.md`` lists the model in its dead-code table and
    recommends REMOVE. ``dto_mrp_sftp``'s own test header records the
    counter-evidence: 319 rows on both databases, all 319 carrying a
    ``production_id``, and it is the FIRST tier of this match. If it is
    gone, tier 1 has silently disappeared and matching has degraded to
    ``lot_producing_ids`` only — which is a finding, not a skip.
    """
    rpc = ctx.adapter.rpc
    if not rpc.model_exists("stock.lot.custom"):
        ctx.blocked(
            "stock.lot.custom does not exist on "
            f"{ctx.env.key} (db={ctx.env.db}). That is tier 1 of the "
            "three-tier match (mrp_attachment_transformer.py:20-23) and "
            "04-manufacturing.md's REMOVE recommendation would produce "
            "exactly this state. The consequence is NOT that this case "
            "cannot run — it is that matching has silently degraded to two "
            "tiers, and files that used to attach now fail with 'no match', "
            "which looks like a data problem rather than a code change. "
            "Resolve WF-010 Open Question 1 before any code moves.")


def producing_lot_field(rpc) -> str:
    """``lot_producing_ids`` on v19, ``lot_producing_id`` on v17.

    §2.8: Many2one -> Many2many. Tiers 2 and 3 both search on it, and in a
    SEARCH DOMAIN the translation is the plural field — ``lot_producing_ids
    .name = X`` matches an MO where ANY producing lot is named X, where v17
    matched the single one. That is a semantic change, not a rename, and it
    is WF-010 open question 5.
    """
    return ("lot_producing_ids"
            if rpc.field_exists("mrp.production", "lot_producing_ids")
            else "lot_producing_id")


# -------------------------------------------------------------- fixtures
def make_product(ctx, code: str, label="Cable Assembly",
                 tracking="lot") -> int:
    """A storable, lot-tracked product whose ``default_code`` is ``code``.

    ``categ_id`` must be passed explicitly: ``dto_mrp`` overrides it with
    ``default=False, required=True`` ("No default category when creating a
    new Product", ``dto_mrp/models/product_template.py:13-17``). That is not
    a v19 break — it carried the same override on v17 — but it means a bare
    create fails. ``with_categ`` supplies one.
    """
    rpc = ctx.adapter.rpc
    values = {
        "name": fx(f"{MARK} {label}"),
        "default_code": code,
        "tracking": tracking,
        "sale_ok": False,
        "purchase_ok": False,
    }
    values.update(ctx.adapter.storable_product_values())
    return rpc.create("product.product", with_categ(rpc, values))


def make_lot(rpc, product_id, name) -> int:
    return rpc.create("stock.lot", {"name": name, "product_id": product_id})


def make_mo(ctx, product_id, qty=1.0, confirm=True) -> int:
    """A manufacturing order for ``product_id``.

    The MO name is left to Odoo's own sequence; sweeping finds these
    through their namespaced product instead.
    """
    rpc = ctx.adapter.rpc
    tmpl_id = m2o_id(rpc.read("product.product", [product_id],
                              ["product_tmpl_id"])[0]["product_tmpl_id"])
    mo_id = rpc.create("mrp.production", {
        "product_id": product_id,
        "product_tmpl_id": tmpl_id,
        "product_qty": qty,
    })
    if confirm:
        try:
            rpc.call("mrp.production", "action_confirm", [mo_id])
        except OdooRPCError as exc:
            ctx.log(f"[warn] MO {mo_id} did not confirm ({exc}); the match "
                    "reads no state field, so a draft MO is still a valid "
                    "fixture. Recorded rather than blocked.")
    return mo_id


def set_producing_lot(ctx, mo_id, lot_id):
    """Attach a producing lot, whichever shape the target has."""
    rpc = ctx.adapter.rpc
    field = producing_lot_field(rpc)
    value = [(6, 0, [lot_id])] if field.endswith("ids") else lot_id
    rpc.write("mrp.production", [mo_id], {field: value})
    return field


def mo_with_lot(ctx, product_id, lot_text, qty=1.0):
    """(mo_id, lot_id) — an MO producing exactly one named lot."""
    rpc = ctx.adapter.rpc
    mo_id = make_mo(ctx, product_id, qty=qty)
    lot_id = make_lot(rpc, product_id, lot_text)
    set_producing_lot(ctx, mo_id, lot_id)
    return mo_id, lot_id


def make_custom_lot(rpc, product_id, name, mo_id) -> int:
    """A ``stock.lot.custom`` row — tier 1's match target.

    ``product_qty`` is ``required=True``
    (``dto_mrp/models/stock_lot_custom.py:14``), so it must be supplied.
    """
    return rpc.create("stock.lot.custom", {
        "name": name,
        "product_id": product_id,
        "product_qty": 1.0,
        "production_id": mo_id,
    })


# ------------------------------------------------------------ the SFTP leg
def make_server(rpc, action="GET", label=None) -> int:
    """An sftp.server fixture that can never connect (convention rule 4)."""
    return rpc.create("sftp.server", {
        "name": fx(f"{MARK} {label or ('Shop floor ' + action)}"),
        "host": "sftp.qa-never-resolves.invalid",
        "port": "22",
        "username": "qa-wf010",
        "password": "not-a-real-credential",
        "action": action,
        "active": False,
        "archive_auto": False,
    })


def make_folder(rpc, server_id, usage=ATTACHMENT_USAGE, label="in",
                duplicate_policy="allow") -> int:
    values = {
        "server_id": server_id,
        "path": f"/{MARK}/{fixture_token()}/{label}",
        "usage": usage,
        "active": True,
    }
    if rpc.field_exists("sftp.folder", "duplicate_policy"):
        values["duplicate_policy"] = duplicate_policy
    return rpc.create("sftp.folder", values)


def make_sftp_file(rpc, folder_id, file_name, content: bytes,
                   mimetype="text/csv", sftp_date=None) -> int:
    """A Pending sftp.file whose attachment holds ``content``.

    Created directly rather than through ``create_sftp_file``, which takes
    a *recordset* for its folder argument and returns one — neither
    survives a JSON-RPC hop. The record shape is identical.

    The FILE NAME carries no convention and is never parsed (TC344 step 4),
    which is why the fixtures deliberately use arbitrary names.
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

    ``action_process_sftp_files`` is public and takes the file's own id —
    the identical per-file path ``cron_process_sftp_files`` takes, without
    searching every pending GET file on the database (convention rule 3,
    and doubly so here: the delta records that a run of malformed test
    files can abort the batch containing the payment and supplier feeds,
    because the poller is shared).
    """
    rpc = ctx.adapter.rpc
    rpc.call("sftp.file", "action_process_sftp_files", [file_id])
    fields_ = ["state", "process_date", "name", "ref", "usage", "res_model",
               "res_id", "reference", "attachment_id", PART_FIELD,
               SERIAL_FIELD]
    return rpc.read("sftp.file", [file_id], fields_)[0]


def run_import(ctx, content: bytes, folder_id=None, file_label="results",
               mimetype="text/csv"):
    """Attach a file and process it. Returns (folder_id, file_id, row)."""
    rpc = ctx.adapter.rpc
    if folder_id is None:
        folder_id = make_folder(rpc, make_server(rpc))
    file_id = make_sftp_file(rpc, folder_id,
                             fx(f"{MARK}_{file_label}.csv"), content,
                             mimetype=mimetype)
    ctx.log(f"processing sftp.file {file_id} through the real ETL "
            f"({len(content)} bytes, no network)")
    return folder_id, file_id, process_file(ctx, file_id)


# ------------------------------------------------------------- assertions
def attachments_on_mo(rpc, mo_id, fields_=None):
    fields_ = fields_ or ["name", "res_model", "res_id", "file_size",
                          "mimetype"]
    return rpc.search_read("ir.attachment",
                           [("res_model", "=", "mrp.production"),
                            ("res_id", "=", mo_id)], fields_, order="id")


def mo_dump(rpc, mo_id) -> dict:
    """Every stored, readable field on an MO — TC344 step 1's baseline.

    Binary and non-stored computed fields are excluded: reading a binary
    over RPC is wasteful and a non-stored compute can legitimately differ
    between two reads. What remains is what "no field changed" has to mean.
    """
    names = rpc.search_read(
        "ir.model.fields",
        [("model", "=", "mrp.production"), ("store", "=", True),
         ("ttype", "not in", ["binary", "one2many"])], ["name"])
    fields_ = sorted({row["name"] for row in names})
    fields_ = [f for f in fields_ if rpc.field_exists("mrp.production", f)]
    return rpc.read("mrp.production", [mo_id], fields_)[0]


def activities_on(rpc, model, res_ids, fields_=None):
    if not res_ids:
        return []
    fields_ = fields_ or ["res_model", "res_id", "summary", "note",
                          "user_id", "date_deadline", "activity_type_id"]
    return rpc.search_read("mail.activity",
                           [("res_model", "=", model),
                            ("res_id", "in", list(res_ids))],
                           fields_, order="id")


def file_message(rpc, file_id) -> str:
    """The ETL message, read back off whichever surface received it.

    ``mark_sync_failed`` files it as an activity NOTE; ``mark_sync_success``
    posts it to the chatter as HTML (``sftp_file.py:169-191``). Both are
    checked so a message is never reported as absent because it succeeded.
    """
    parts = [str(act.get("note") or "")
             for act in activities_on(rpc, "sftp.file", [file_id])]
    messages = rpc.search_read("mail.message",
                               [("model", "=", "sftp.file"),
                                ("res_id", "=", file_id)], ["body"],
                               order="id")
    parts += [str(row.get("body") or "") for row in messages]
    return " || ".join(p for p in parts if p)


def could_match(ctx, part, serial):
    """Every MO any tier could reach for (part, serial) — the negative
    precondition every tier case needs.

    Mirrors the transformer's three searches
    (``mrp_attachment_transformer.py:20-61``) so "tier N could not have
    fired" is PROVED rather than assumed — which is the difference between
    TC344/TC345/TC346 meaning something and meaning nothing.
    """
    rpc = ctx.adapter.rpc
    field = producing_lot_field(rpc)
    lot_path = f"{field}.name"
    result = {"tier1": [], "tier2": [], "tier3": [], "tier3_prefix": None}

    if rpc.model_exists("stock.lot.custom"):
        rows = rpc.search_read(
            "stock.lot.custom",
            [("product_id.default_code", "=", part), ("name", "=", serial)],
            ["production_id"], order="id")
        result["tier1"] = sorted({m2o_id(r["production_id"]) for r in rows
                                  if r.get("production_id")})

    result["tier2"] = sorted(rpc.search(
        "mrp.production", [("product_id.default_code", "=", part),
                           (lot_path, "=", serial)]))

    if "-" in serial:
        prefix = serial[:serial.rfind("-")]
        result["tier3_prefix"] = prefix
        result["tier3"] = sorted(rpc.search(
            "mrp.production", [("product_id.default_code", "=", part),
                               (lot_path, "=", prefix)]))
    return result


def expect_error(rpc_callable, *args, **kwargs):
    try:
        rpc_callable(*args, **kwargs)
        return False, "no error raised"
    except OdooRPCError as exc:
        return True, str(exc)
