"""Shared fixtures and helpers for the DATAONE-WF-026 suite
(Historical Data Migration Import).

Owning workflow: DATAONE-WF-026, **Stage 7 — historical data migration and
management reporting**. It owns 23 workbook test cases: TC396-TC410 (the
importer) and TC451-TC458 (the queue_job layer it dispatches onto).

What this workflow is
---------------------
``dto_data_migration`` loads DataOne's closed legacy transactions straight
into the live tables — measured on v17, **43,313 records**: 2,388 purchase
orders, 6,510 sales orders, **34,252 manufacturing orders** and 163 BoMs
(``database/STAGE7-PHASE0A-BASELINE-v17.txt:5-11``). They arrive already
finished, so every core compute that would re-derive their state from
movements that do not exist has to be suppressed.

The entire suppression mechanism is ONE field::

    dto.data.migration.is_historical_data      (models/dto_data_migration.py:17)

and thirteen overrides keyed on it. That is what makes this workflow
dangerous rather than merely large: if core renames one of those thirteen
methods, the override silently stops being an override, core recomputes
34,252 imported MOs from nothing, **every one reports zero produced, and the
import still reports success**.

Why this suite exists alongside the module's own tests
------------------------------------------------------
``dto_data_migration`` ships 15 tests of its own across three files, and
they are good. They are also **not traceable to the workbook**: grepping all
four Stage 7 test files for ``TC\\d{3}`` returns nothing, and
``WF027-OPEN-QUESTIONS.md:79-86`` records that the workbook's "Test
Execution" sheet was never opened. This suite is the workbook-traceable
layer — every case here carries its ``DATAONE-TC***`` id — and it
concentrates on what the module's tests do not reach:

* the **queue_job path** (``use_queue_job=True``), exercised by nothing
  (``WF026-OPEN-QUESTIONS.md:46-57``) — TC408, TC409;
* **re-running the same file**, which has no guard at all — see below;
* the **five error strings** the module's single abort test does not pin —
  TC403-TC407, TC410.

There is no idempotency guard, and that is a finding
----------------------------------------------------
``_import_data_migration`` calls ``self.create(value)`` unconditionally
(``models/dto_data_migration.py:35``). Importing the same CSV twice creates
a second complete set of records. Nothing dedupes on the key fields, and the
wizard offers no "already imported" check. At 43,313 rows a double run is
not a tidy-up, so TC399's re-read assertions are written to notice it.

Two rules this suite has to work hard to respect
------------------------------------------------
**Rule 3 — never modify pre-existing business records.** Every fixture is
created under the ``WF026`` marker plus a per-execution token, and every
search is token-scoped. The importer writes into ``purchase.order``,
``sale.order``, ``mrp.production`` and ``mrp.bom`` — the client's real
tables — so nothing here may search those models unscoped.

**Rule 5 — deterministic.** ``run_import_data_migration`` has a
``batch_size`` but **no overall row cap**, and the baseline figures above are
production scale. No test in this suite feeds it more than a handful of
rows; the 43,313 is documentation of magnitude, never a fixture.

EXPECTED v17/v19 OUTCOME is stated per test in each module's docstring.
"""
from __future__ import annotations

import base64
import csv
import io
import uuid

from adapters.base import OdooRPCError
from framework.fg_common import m2o_id, make_trace  # noqa: F401 — re-exported
from framework.qa_fixtures import (sweep_model,  # noqa: F401
                                   sweep_products, with_categ)

WORKFLOW = "DATAONE-WF-026"
WORKFLOW_NAME = "Historical Data Migration Import"

trace = make_trace(WORKFLOW)

MARK = "WF026"
_TOKEN = {"value": uuid.uuid4().hex[:6]}


def fx(name: str) -> str:
    """Namespace a fixture value with the marker and this run's token."""
    return f"{MARK}-{_TOKEN['value']} {name}"


def token() -> str:
    return _TOKEN["value"]


# ------------------------------------------------------------------ source
#: wizard/import_data_wizard.py:17-22 — the four types, verbatim.
IMPORT_TYPES = ("closed_po", "closed_mo", "closed_so", "bom")

#: wizard/import_data_wizard.py:32-41 — what _onchange_import_type fills in.
#: TC397 is exactly this table, and its steps 15-16 exist to prove the value
#: comes from the ONCHANGE and not from a field default.
EXPECTED_KEY_FIELDS = {
    "closed_po": "name",
    "closed_mo": "name",
    "closed_so": "name",
    "bom": "product_tmpl_id",
}

#: models/dto_data_migration.py — the exact UserError strings. Asserted
#: character for character; the difference between "Can not" (:117, :139) and
#: "Cannot" (:96, :102) is in the source and is NOT a typo to be tidied here.
ERR_UNKNOWN_FIELD = 'Can not find the field "{field}" on {model} model'
ERR_NO_RELATION_VALUE = 'Can not find a field {field} with value: {value}'
ERR_PARTIAL_X2MANY = ("Only found {found} records (Expected: {expected} "
                      "records) on {field} field with the following names: ")
ERR_BAD_RELATION = ('Cannot find the field "{field}" or it is not a '
                    'one2many/many2many relation on {model} model')
ERR_MISSING_KEY = "Not found key field: {field}"

#: The three wrappers every row failure is re-raised inside
#: (:37-40, :61-63, :73-75). A test asserting an inner string must allow for
#: the wrapper, which is why these are prefixes rather than equalities.
ERR_CREATE_PREFIX = "Error when creating data:"
ERR_HEADER_PREFIX = "Error when transforming the header data:"
ERR_LINE_PREFIX = "Error when transforming the line data:"

#: data/queue_job_channel_data.xml:5,10,15
QUEUE_CHANNELS = ("root.dto_data_migration_po",
                  "root.dto_data_migration_mo",
                  "root.dto_data_migration_so")

WIZARD = "import.data.wizard"
WIZARD_ACTION_XMLID = "dto_data_migration.action_import_data_wizard"

#: security/ir.model.access.csv — the ONE acl, and the group it names.
WIZARD_GROUP_XMLID = "stock.group_stock_manager"

#: dto_base/hooks.py:711-734 — thirteen, not fourteen. The fourteenth
#: (purchase.order.line._compute_receipt_status) is excluded by name because
#: it exists on neither v17 nor v19 core, so guarding it would fail every
#: install forever.
C13_GUARD_SIZE = 13


# ------------------------------------------------------------ preconditions
def require_data_migration(ctx):
    """BLOCK unless dto_data_migration is contributing the import layer.

    Probed rather than assumed: with the module absent every assertion in
    this suite becomes VACUOUS rather than failing, which is what outcome
    convention rule 5 exists to prevent.
    """
    rpc = ctx.adapter.rpc
    if not rpc.model_exists(WIZARD):
        ctx.blocked(
            f"{WIZARD} does not exist on {ctx.env.key} (db={ctx.env.db}) — "
            f"dto_data_migration is not installed. It is Stage 7; add it to "
            f"tools/uninstall_non_migrated.py's KEEP list and deploy, or the "
            f"next rebuild removes it again.")
    missing = [f for f in ("is_historical_data",)
               if not rpc.field_exists("purchase.order", f)]
    if missing:
        ctx.blocked(
            f"purchase.order is missing {', '.join(missing)} — the "
            f"dto.data.migration AbstractModel is not inherited into it, so "
            f"the whole suppression layer this workflow depends on is "
            f"absent.")


def require_queue_job(ctx):
    """BLOCK unless the queue_job layer TC408/TC409 and TC451-TC458 need."""
    rpc = ctx.adapter.rpc
    if not rpc.model_exists("queue.job"):
        ctx.blocked(
            "queue.job does not exist — the OCA queue_job module is not "
            "installed, so neither the asynchronous import path nor the job "
            "lifecycle this workflow dispatches onto can be observed.")


# ------------------------------------------------------------------ CSV
def csv_bytes(rows: list, headers: list | None = None) -> str:
    """Rows -> the base64 the wizard's Binary field expects.

    The wizard decodes UTF-8 and reads with ``csv.DictReader``
    (``wizard/import_data_wizard.py:49-52``), stripping **all** internal
    spaces from every header (:51) — so a header written "product id" and
    one written "productid" are the same column to it. Tests that care about
    that write the header with spaces deliberately.
    """
    if headers is None:
        headers = list(rows[0].keys()) if rows else []
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=headers, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return base64.b64encode(buf.getvalue().encode("utf-8")).decode()


def raw_csv_bytes(text: str) -> str:
    """A CSV written by hand, for the cases that need a malformed one."""
    return base64.b64encode(text.encode("utf-8")).decode()


# --------------------------------------------------------------- the wizard
def make_wizard(rpc, import_type: str, rows: list | None = None, *,
                raw: str | None = None, key_fields: str | None = None,
                batch_size: int = 100, use_queue_job: bool = False,
                headers: list | None = None,
                file_name: str | None = None) -> int:
    """Create the import wizard the way the menu does.

    ``key_fields`` defaults to what ``_onchange_import_type`` would fill in,
    because creating over RPC does NOT run the onchange — TC397 steps 15-16
    are precisely about that difference, so every other case has to supply
    the value the UI would have supplied.

    To act as a different user, pass that user's session as ``rpc``
    (``framework.qa_fixtures.rpc_as_qa_user``); this helper does not fake a
    uid through the context, which would not exercise the ACL.
    """
    return rpc.create(WIZARD, {
        "import_type": import_type,
        "batch_size": batch_size,
        "use_queue_job": use_queue_job,
        "key_fields": key_fields or EXPECTED_KEY_FIELDS[import_type],
        "file_name": file_name or fx(f"{import_type}.csv"),
        "file_data": raw if raw is not None else csv_bytes(rows or [], headers),
    })


def run_import(rpc, wizard_id: int) -> dict:
    """Drive ``action_confirm_import`` and hand back what it returned.

    Returns ``{'action': <the act_window dict or False>}``. The method
    returns **None** when nothing was created (:69 guard), which is a real
    outcome several cases assert, so it is reported rather than smoothed
    over.
    """
    action = rpc.call(WIZARD, "action_confirm_import", [wizard_id])
    return {"action": action}


def expect_error(ctx, fn, *, contains: str = "", label: str = "the call"):
    """Run ``fn`` expecting an OdooRPCError; return (message, fault_name).

    Fails loudly if it does NOT raise — a validation test that passes
    because nothing happened is worse than no test.

    ``fault_name`` is the server's exception CLASS (``odoo.exceptions.
    UserError``, ``builtins.KeyError`` ...). It is returned separately
    because the message alone cannot identify the exception: a bare
    ``KeyError('qty_produced')`` reaches the client as the string
    ``qty_produced``, which is indistinguishable from a field value. TC410
    is entirely about that distinction.
    """
    try:
        fn()
    except OdooRPCError as exc:
        message = str(exc)
        if contains:
            ctx.check_true(f"{label} raises a message containing "
                           f"{contains!r}", contains in message, message[:400])
        return message, getattr(exc, "fault_name", "")
    ctx.check_true(f"{label} raises", False,
                   "it returned normally, so the guard did not fire")
    return "", ""


# ------------------------------------------------------------------ sweeping
def sweep_wf026(rpc):
    """Remove marker-scoped leftovers, then open a fresh namespace.

    Best-effort by design, and ORDERED: the importer creates orders that
    reference products, so products cannot go first. A record that refuses
    to unlink is accepted — the fresh token is what guarantees isolation,
    since every search in every test is token-scoped.
    """
    _TOKEN["value"] = uuid.uuid4().hex[:6]

    for model, domain in (
        ("mrp.production", [("name", "like", f"{MARK}-%")]),
        ("sale.order", [("name", "like", f"{MARK}-%")]),
        ("purchase.order", [("name", "like", f"{MARK}-%")]),
    ):
        for rec_id in rpc.search(model, domain):
            for method in ("action_cancel", "button_cancel", "action_draft"):
                try:
                    rpc.call(model, method, [rec_id])
                except OdooRPCError:
                    pass
            try:
                rpc.call(model, "unlink", [rec_id])
            except OdooRPCError:
                pass

    sweep_model(rpc, "mrp.bom", [("code", "like", f"{MARK}-%")])
    sweep_model(rpc, WIZARD, [("file_name", "like", f"{MARK}-%")])
    sweep_products(rpc, MARK)
    sweep_model(rpc, "res.partner", [("name", "like", f"{MARK}-%"),
                                     ("user_ids", "=", False),
                                     ("active", "in", [True, False])])


def open_namespace(ctx):
    with ctx.step(f"Sweep previous {MARK} fixtures and open a fresh namespace"):
        sweep_wf026(ctx.adapter.rpc)
        ctx.log(f"fixture token = {_TOKEN['value']}")


# ------------------------------------------------------------------ fixtures
def ensure_product(rpc, label: str, *, code: str | None = None,
                   storable: bool = True) -> int:
    """A token-scoped product. ``default_code`` matters: the importer
    resolves product relations by ``default_code`` and everything else by
    ``name``, both ``=ilike`` with ``limit=1``
    (``models/dto_data_migration.py:146-149``)."""
    values = with_categ(rpc, {
        "name": fx(label),
        "default_code": code or fx(label).replace(" ", "-"),
        "type": "consu",
    })
    if rpc.field_exists("product.template", "is_storable"):
        values["is_storable"] = storable
    return rpc.create("product.product", values)


def ensure_partner(rpc, label: str, *, supplier: bool = False) -> int:
    return rpc.create("res.partner", {
        "name": fx(label),
        "supplier_rank": 1 if supplier else 0,
        "customer_rank": 0 if supplier else 1,
    })


def product_code(rpc, product_id: int) -> str:
    return rpc.read("product.product", [product_id], ["default_code"])[0][
        "default_code"]


def partner_name(rpc, partner_id: int) -> str:
    return rpc.read("res.partner", [partner_id], ["name"])[0]["name"]
