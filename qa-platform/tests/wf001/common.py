"""Shared fixtures and helpers for the DATAONE-WF-001 suite
(Workday requisition → sales order, inbound).

Owning workflow: DATAONE-WF-001, build order 25 — the LAST of **Stage 6 —
Workday integrations (need the documents they carry to exist first)** —
risk CRITICAL, fail mode loud + silent, 22.5 h, depends on WF-002 and
WF-003. It owns 7 workbook test cases: TC303, TC337, TC339, TC340, TC341,
TC342 and TC343.

What this workflow is
---------------------
Workday is DataOne's requisitioning system of record for internal demand.
**Every DataOne sale begins here**, and the analytic distribution this flow
writes is the origin of the entire analytic chain — it is what later reaches
the MO (F174), the valuation entries (F209) and the Workday export columns
BG / BI / BK. A field that lands on the wrong target, or an analytic account
written in the wrong key format, is not a sales defect; it is an accounting
defect that surfaces months later in a Workday report.

It is also the busiest of the five Workday flows. ``dto_sale_workday``'s own
test header records the measurement: **3,082 sale orders imported, 3,104
requisition files processed, 4 failed, 76–267 orders a month through Aug
2026.** Unlike WF-010, this one works.

The feasibility fact that decides this suite
--------------------------------------------
There are TWO public entry points into the same ETL, and neither needs the
network:

* ``sftp.file.action_process_sftp_files()`` — the scheduled path. The
  extractor reads the ``sftp.file``'s ATTACHMENT
  (``workday_requisition_extractor.py:13-22``), so SFTP is only involved in
  fetching the file onto it.
* ``sale.order.import_workday_requisition.import_requisition()`` — the
  MANUAL wizard. It takes the uploaded bytes directly and calls the same
  ``_transform_…`` / ``_process_…`` pair
  (``wizard/import_workday_requisition.py:17-41``).

So every case here is implemented, and TC342 — which the workbook types
TOUR — is implemented over RPC as an ordinary model call, because the
wizard's entry point is public and returns an action dict.

The workbook makes the scheduling point explicitly: *"because it bypasses
the transport entirely, TC342 exercises the complete requisition ETL —
grouping, mapping, auto-creation, revision, confirmed-order protection —
with no SFTP endpoint. If E6 slips, run TC342 and get most of TC337's,
TC338's and TC339's coverage anyway."*

THE SAFETY PROBLEM THIS SUITE HAS AND THE OTHERS DO NOT
-------------------------------------------------------
``_transform_workday_requisition_to_sale_order_vals`` matches an existing
order by ``Internal_Memo`` (``sale_order.py:265-269``)::

    order = env['sale.order'].search([
        '|', ('name', '=', line['Internal_Memo'].strip()),
             ('name', 'like', '{}-%'.format(line['Internal_Memo'].strip()))
    ], limit=1)

and then, if the match is unconfirmed, **calls create_revision() on it**.
A fixture whose ``Internal_Memo`` collided with a live order name would
REVISE a real customer's quotation. Every ``Internal_Memo`` in this suite is
therefore token-scoped through ``memo()``, and the value is deliberately
shaped so that it cannot be a sale-order sequence name (``WF001-<token>-…``
never matches ``S00123``). The same applies to the other three lookups,
each of which AUTO-CREATES on a miss:

* ``_get_product_id`` searches ``product.product.default_code`` -> creates;
* ``_get_partner_id`` searches ``res.partner`` on name AND every address
  field -> creates;
* ``_get_or_create_analytic_account`` searches name + plan -> creates.

All four are token-scoped. That is not tidiness: an untokenised item code
would attach a live product to a fixture order, and an untokenised analytic
name would write a fixture distribution onto accounts the ledger uses.

The 23 columns
--------------
Read from the source, one call site each, and cross-checked against
``dto_sale_workday/tests/test_wf001_requisition_import.py``'s own ``_row``
helper. ``emailAddress`` really is lower-camel while every other column is
Title_Case_With_Underscores, and ``Ship-To_*`` really does use a HYPHEN in
"Ship-To" and underscores everywhere else. Those are Workday's own labels
and a port must not tidy them.
"""
from __future__ import annotations

import base64
import csv
import io
import uuid

from adapters.base import OdooRPCError
from framework.fg_common import form_arch, m2o_id, make_trace  # noqa: F401
from framework.qa_fixtures import (require_mail_offline,  # noqa: F401
                                   sweep_model, sweep_products, with_categ)

WORKFLOW = "DATAONE-WF-001"
WORKFLOW_NAME = "Workday requisition → sales order (inbound)"
FEATURE = "DATAONE-WF-001 Workday requisition → sales order (inbound)"
MARK = "WF001"

trace = make_trace(FEATURE)

REQUISITION_USAGE = "workday_requisition"

# TC303 step 9 — the FROZEN contract between the six business modules and
# the transport. The usage key is literally interpolated into a method name
# (SFTPExtractor.run: getattr(self, f'_run_extractor_{business_process}')),
# so a rename during the port is a SILENT dispatch failure, not an import
# error.
USAGE_KEYS = {
    "none",
    "workday_vendor_bill",       # dto_account_workday
    "workday_journal_entry",     # dto_account_workday
    "workday_vendor_payment",    # dto_account_workday
    "workday_supplier",          # dto_purchase_workday (moved, decision D-9)
    "workday_requisition",       # dto_sale_workday
    "mrp_attachment",            # dto_mrp_sftp
}

# The 23 columns, in the order the workbook's file declares them. Every one
# is read by name from a dict, so the CSV's column ORDER is irrelevant and
# its presence is not — a missing key is a bare KeyError inside the
# transform.
CSV_COLUMNS = [
    # header, per requisition (sale_order.py:72-87)
    "Requisition_Num",        # -> origin, and the groupby key
    "Internal_Memo",          # -> internal_memo, AND the existing-order match
    "Request_Date",           # -> requisition_date
    "Requisition_Type",       # -> order_type, matched on the Selection LABEL
    "Requester",              # -> requester
    "emailAddress",           # -> requester_email  (lower-camel, verbatim)
    "Supplier_Memo",          # -> memo_to_suppliers
    # ship-to, resolved or created (sale_order.py:89-126)
    "Ship-To_Contact",        # required; the one value that cannot be invented
    "Ship-To_Street",
    "Ship-To_Street_2",
    "Ship-To_City",
    "Ship-To_State",
    "Ship-To_Country",
    "Ship-To_Zip_Code",
    # line, per row (sale_order.py:128-152)
    "Item",                   # required; -> product_id by default_code
    "Item_Description",       # -> line name, and the auto-created product name
    "Quantity",               # -> product_uom_qty
    "Unit_Price",             # -> price_unit
    "Due_Date",               # -> expected_delivery_date
    "Unit_of_Measure",        # -> product_uom_id  (v19 rename, already done)
    # analytic (sale_order.py:154-180)
    "project",                # -> Project plan account, 100%   (lower case)
    "Cust_Contract",          # -> Customer Contract plan account, 100%
    "Cost_Center",            # READ, RESOLVED, THEN DISCARDED — BR-8
]

# The header fields and where they land. TC337 step 6 is this table.
HEADER_FIELD_MAP = {
    "Requisition_Num": "origin",
    "Internal_Memo": "internal_memo",
    "Request_Date": "requisition_date",
    "Requester": "requester",
    "emailAddress": "requester_email",
    "Supplier_Memo": "memo_to_suppliers",
}

# sale_order.py:124-126 / :142-144 / :203-205 / :214-216 / :229-231 — the
# five raises, each decorated by _prepare_log_message as
# '{message} at row {data_line}', which DUMPS THE ENTIRE ROW DICT.
ERR_NO_CONTACT = "Ship-To_Contact data is empty"
ERR_NO_ITEM = "Item is empty"
ERR_NO_ORDER_TYPE = "Cannot find Order Type in Odoo"
ERR_NO_UOM = "Cannot find UoM in Odoo"
ERR_NO_CATEGORY = "Cannot find Consumable product category in Odoo"
ROW_DECORATION = "at row"

# sale_order.py:436 — the confirmed-order protection activity.
CONFIRMED_ACTIVITY_SUMMARY = ("This order has been confirmed and order "
                              "lines cannot be modified")
FILE_ACTIVITY_SUMMARY = "Cannot process SFTP file"
ACTIVITY_TYPE_XMLID = "mail.mail_activity_data_warning"
SUPERUSER_ID = 1

# _get_product_id's two hard requirements (sale_order.py:225-239).
CONSUMABLE_CATEGORY_NAME = "Consumable"
AUTO_CREATED_TAG_XMLID = "dto_sale_workday.product_tag_auto_created"

# _prepare_analytic_distribution_values' three env.ref() targets
# (sale_order.py:156-158). ALL THREE are resolved before either of the two
# that are used, so a missing cost-centre plan breaks the flow even though
# the cost centre is discarded.
ANALYTIC_PLAN_XMLIDS = {
    "project": "dto_account.project_analytic_plan",
    "contract": "dto_account.customer_contract_analytic_plan",
    "cost": "dto_account.cost_center_analytic_plan",
}

WIZARD_MODEL = "sale.order.import_workday_requisition"
WIZARD_MENU_XMLID = "dto_sale_workday.menu_import_workday_requisition"
GET_CRON_XMLID = "novobi_sftp_connection.ir_cron_get_sftp_files"
PROCESS_CRON_XMLID = "novobi_sftp_connection.ir_cron_process_sftp_files"

# sftp_file.py:256-260 — the processing cron's own domain. A folder whose
# usage is 'none' is excluded by the third clause, which is TC303's
# "Pending forever".
PROCESS_CRON_DOMAIN = [
    ("action", "=", "GET"),
    ("state", "=", "pending"),
    ("usage", "!=", "none"),
]

_TOKEN = "init"


def fixture_token() -> str:
    return _TOKEN


def fx(name: str) -> str:
    return f"{name} [{_TOKEN}]"


def memo(suffix: str = "M1") -> str:
    """An ``Internal_Memo`` that CANNOT collide with a live order name.

    This is the single most important namespacing decision in the suite.
    ``_transform_workday_requisition_to_sale_order_vals`` searches
    ``sale.order`` for ``name = Internal_Memo`` OR ``name like
    '<Internal_Memo>-%'`` and, on an unconfirmed match, calls
    ``create_revision()`` on it. A colliding memo would revise a real
    customer's quotation. ``WF001-<token>-…`` can never be an Odoo sale
    order sequence name.
    """
    return f"{MARK}-{_TOKEN}-{suffix}"


def item_code(suffix: str = "ITEM-1") -> str:
    """A ``default_code`` for ``_get_product_id``'s exact-match lookup.

    Token-scoped because a miss AUTO-CREATES: an untokenised code would
    attach a LIVE product to a fixture order.
    """
    return f"{MARK}-{_TOKEN}-{suffix}"


def analytic_name(kind: str) -> str:
    """A name for ``_get_or_create_analytic_account``'s lookup.

    Token-scoped because a miss AUTO-CREATES, and an untokenised name would
    write a fixture distribution onto analytic accounts the ledger uses.
    """
    return f"{MARK}-{_TOKEN}-{kind}"


def contact_name(suffix: str = "Alpha") -> str:
    """A ``Ship-To_Contact`` for ``_get_partner_id``'s full-address match."""
    return f"{MARK} Customer {suffix} [{_TOKEN}]"


# ------------------------------------------------------------------ sweep
def sweep_wf001(rpc):
    """Open a fresh fixture namespace, then remove marker-scoped leftovers.

    Orders are found by ``origin`` (which the import sets to
    ``Requisition_Num``) and by ``internal_memo``. A CONFIRMED order cannot
    be unlinked without cancelling it first, and a revision chain leaves
    archived predecessors, so both are attempted and neither is required to
    succeed. The fresh token is the real isolation.
    """
    global _TOKEN
    _TOKEN = uuid.uuid4().hex[:6]

    order_ids = set(rpc.search("sale.order",
                               [("origin", "like", f"{MARK}-%"),
                                ("active", "in", [True, False])]))
    order_ids |= set(rpc.search("sale.order",
                                [("internal_memo", "like", f"{MARK}-%"),
                                 ("active", "in", [True, False])])) \
        if rpc.field_exists("sale.order", "internal_memo") else set()
    if order_ids:
        for method in ("action_cancel", "action_draft"):
            try:
                rpc.call("sale.order", method, sorted(order_ids))
            except OdooRPCError:
                pass
        try:
            rpc.call("sale.order", "unlink", sorted(order_ids))
        except OdooRPCError:
            try:
                rpc.write("sale.order", sorted(order_ids), {"active": False})
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

    sweep_model(rpc, "account.analytic.account",
                [("name", "like", f"{MARK}-%"),
                 ("active", "in", [True, False])])
    sweep_products(rpc, MARK)
    sweep_model(rpc, "product.product",
                [("default_code", "like", f"{MARK}-%")])
    sweep_model(rpc, "product.template", [("name", "like", f"{MARK} %")])
    sweep_model(rpc, "res.partner", [("name", "like", f"{MARK} %"),
                                     ("user_ids", "=", False),
                                     ("active", "in", [True, False])])
    sweep_model(rpc, "ir.attachment", [("name", "like", f"{MARK}%")])


# ---------------------------------------------------------------- probes
def require_requisition_import(ctx):
    """BLOCK unless the inbound requisition leg exists at all."""
    rpc = ctx.adapter.rpc

    missing = [m for m in ("sftp.server", "sftp.folder", "sftp.file",
                           "sale.order", WIZARD_MODEL)
               if not rpc.model_exists(m)]
    if missing:
        ctx.blocked(
            f"Missing model(s) on {ctx.env.key} (db={ctx.env.db}): "
            f"{', '.join(missing)}. dto_sale_workday / "
            "novobi_sftp_connection are not both installed, so there is no "
            "requisition import to observe.")

    info = rpc.call("sftp.folder", "fields_get", ["usage"],
                    attributes=["selection"])
    keys = [k for k, _label in (info["usage"].get("selection") or [])]
    if REQUISITION_USAGE not in keys:
        ctx.blocked(
            f"sftp.folder.usage does not offer {REQUISITION_USAGE!r} on "
            f"{ctx.env.key} — dto_sale_workday is not installed, so "
            "sftp.file._process_sftp_file never dispatches to the "
            f"requisition ETL. Available usage keys: {keys}")

    for field in ("imported_from_workday", "internal_memo", "requester",
                  "requester_email", "requisition_date",
                  "memo_to_suppliers"):
        if not rpc.field_exists("sale.order", field):
            ctx.blocked(
                f"sale.order.{field} does not exist — dto_sale_workday did "
                "not contribute its header fields, so the 23-column "
                "mapping has nowhere to land.")

    if not rpc.field_exists("sale.order", "order_type"):
        ctx.blocked(
            "sale.order.order_type does not exist — dto_sale is not "
            "installed, and _get_order_type matches Requisition_Type "
            "against that Selection's LABELS. Without it every row raises "
            "'Cannot find Order Type in Odoo'.")


def require_import_prerequisites(ctx):
    """BLOCK on the three things ``_get_product_id`` and the analytic
    helper resolve unconditionally.

    Each one makes EVERY row raise rather than degrading, so probing turns
    an obscure per-row failure into a precise reason.
    """
    rpc = ctx.adapter.rpc

    category = rpc.search("product.category",
                          [("name", "=", CONSUMABLE_CATEGORY_NAME)], limit=1)
    if not category:
        ctx.blocked(
            f"No product.category named exactly "
            f"{CONSUMABLE_CATEGORY_NAME!r} exists on {ctx.env.key}. "
            "_get_product_id searches for it by that literal name and "
            "RAISES 'Cannot find Consumable product category in Odoo' when "
            "it is absent (sale_order.py:225-231) — so every row carrying "
            "an unknown Item fails the whole file.")

    if not rpc.ref(AUTO_CREATED_TAG_XMLID):
        ctx.blocked(
            f"{AUTO_CREATED_TAG_XMLID} does not resolve. _get_product_id "
            "links it with Command.link on every auto-created product "
            "(sale_order.py:237), and env.ref raises when it is missing. "
            "Note that product_tag_data.xml is NOT noupdate, so a module "
            "upgrade recreates it — its absence means the module did not "
            "load its data at all.")

    missing_plans = {kind: xmlid
                     for kind, xmlid in ANALYTIC_PLAN_XMLIDS.items()
                     if not rpc.ref(xmlid)}
    if missing_plans:
        ctx.blocked(
            f"These analytic plan xmlids do not resolve: {missing_plans!r}. "
            "_prepare_analytic_distribution_values resolves ALL THREE at "
            "the top of the method (sale_order.py:156-158) before using "
            "two of them — so a missing COST CENTRE plan breaks the flow "
            "even though the cost centre is deliberately discarded (BR-8).")


def order_type_labels(ctx):
    """{label: key} for ``sale.order.order_type``.

    ``_get_order_type`` matches ``Requisition_Type`` against the LABEL and
    raises when it finds nothing (``sale_order.py:195-206``), so the
    fixture's value has to be a real label on this database — and the
    ASSERTIONS have to be on the stored KEY, which is TC337 step 6's
    explicit requirement.
    """
    rpc = ctx.adapter.rpc
    info = rpc.call("sale.order", "fields_get", ["order_type"],
                    attributes=["selection"])
    pairs = info["order_type"].get("selection") or []
    if not pairs:
        ctx.blocked("sale.order.order_type offers no selection values, so "
                    "no Requisition_Type can resolve.")
    return {label: key for key, label in pairs}


def any_uom(ctx) -> str:
    """A ``uom.uom`` NAME for ``_get_uom_id``'s exact-match lookup."""
    rpc = ctx.adapter.rpc
    rows = rpc.search_read("uom.uom", [], ["name"], limit=1)
    if not rows:
        ctx.blocked("No uom.uom exists, so Unit_of_Measure cannot resolve.")
    return rows[0]["name"]


def state_and_country(ctx, country_name="United States",
                      state_name="Texas"):
    """(state row, country row) for a resolvable ship-to address.

    ``_get_partner_id`` searches ``res.country.state`` on ``name`` OR
    ``code`` ``=ilike`` within the country (``sale_order.py:97-101``), and
    then stores the resolved ``state_id``/``country_id`` on the address —
    so an unresolvable state silently produces a partner with no state
    rather than failing, which is TC341 step 10.
    """
    rpc = ctx.adapter.rpc
    countries = rpc.search_read("res.country", [("name", "=", country_name)],
                                ["name", "code"], limit=1)
    if not countries:
        ctx.blocked(f"res.country {country_name!r} does not exist, so the "
                    "ship-to normalisation cannot be exercised.")
    states = rpc.search_read(
        "res.country.state",
        [("country_id", "=", countries[0]["id"]),
         ("name", "=", state_name)], ["name", "code"], limit=1)
    if not states:
        states = rpc.search_read(
            "res.country.state", [("country_id", "=", countries[0]["id"])],
            ["name", "code"], limit=1)
    if not states:
        ctx.blocked(f"No res.country.state exists for {country_name!r}.")
    return states[0], countries[0]


# ------------------------------------------------------------------- rows
def row(requisition_num, internal_memo, order_type_label, uom_name,
        contact, street, city, state, zip_code, item, description,
        quantity="2", unit_price="10.0", due_date="2026-09-15",
        request_date="2026-09-01", requester="Jane Requester",
        email="jane.requester@example.com", supplier_memo="Ship complete",
        street2="Suite 20", country="United States",
        project="", contract="", cost_center="") -> dict:
    """One 23-column requisition row, every key present."""
    return {
        "Requisition_Num": requisition_num,
        "Internal_Memo": internal_memo,
        "Request_Date": request_date,
        "Requisition_Type": order_type_label,
        "Requester": requester,
        "emailAddress": email,
        "Supplier_Memo": supplier_memo,
        "Ship-To_Contact": contact,
        "Ship-To_Street": street,
        "Ship-To_Street_2": street2,
        "Ship-To_City": city,
        "Ship-To_State": state,
        "Ship-To_Country": country,
        "Ship-To_Zip_Code": zip_code,
        "Item": item,
        "Item_Description": description,
        "Quantity": quantity,
        "Unit_Price": unit_price,
        "Due_Date": due_date,
        "Unit_of_Measure": uom_name,
        "project": project,
        "Cust_Contract": contract,
        "Cost_Center": cost_center,
    }


def csv_bytes(rows, columns=None, header_offset=0) -> bytes:
    """A UTF-8 CSV whose header row supplies the ETL's dict keys.

    ``_convert_data_to_list_of_dict`` is called with ``row_start=0``
    (``workday_requisition_extractor.py:23-27``), so the header must be the
    first row; ``header_offset`` exists only to build the negative case.
    """
    columns = list(columns or CSV_COLUMNS)
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n", quoting=csv.QUOTE_ALL)
    for _ in range(header_offset):
        writer.writerow([])
    writer.writerow(columns)
    for entry in rows:
        writer.writerow([entry.get(column, "") for column in columns])
    return buffer.getvalue().encode("utf-8")


# ------------------------------------------------------------ the SFTP leg
def make_server(rpc, action="GET", label=None) -> int:
    """An sftp.server fixture that can never connect (convention rule 4)."""
    return rpc.create("sftp.server", {
        "name": fx(f"{MARK} {label or ('Workday ' + action)}"),
        "host": "sftp.qa-never-resolves.invalid",
        "port": "22",
        "username": "qa-wf001",
        "password": "not-a-real-credential",
        "action": action,
        "active": False,
        "archive_auto": False,
    })


def make_folder(rpc, server_id, usage=REQUISITION_USAGE, label="in") -> int:
    values = {
        "server_id": server_id,
        "path": f"/{MARK}/{fixture_token()}/{label}",
        "usage": usage,
        "active": True,
    }
    if rpc.field_exists("sftp.folder", "duplicate_policy"):
        values["duplicate_policy"] = "allow"
    return rpc.create("sftp.folder", values)


def make_sftp_file(rpc, folder_id, file_name, content: bytes,
                   mimetype="text/csv") -> int:
    attachment_id = rpc.create("ir.attachment", {
        "name": file_name, "type": "binary", "mimetype": mimetype,
        "datas": base64.b64encode(content).decode("ascii"),
    })
    folder = rpc.read("sftp.folder", [folder_id], ["path"])[0]
    return rpc.create("sftp.file", {
        "folder_id": folder_id,
        "ref": f"{folder['path']}/{file_name}",
        "attachment_id": attachment_id,
    })


def process_file(ctx, file_id):
    """Run the real ETL over one Pending file and read the outcome back."""
    rpc = ctx.adapter.rpc
    rpc.call("sftp.file", "action_process_sftp_files", [file_id])
    return rpc.read("sftp.file", [file_id],
                    ["state", "process_date", "name", "ref", "usage"])[0]


def run_import(ctx, rows, folder_id=None, file_label="requisitions",
               columns=None, header_offset=0):
    """The SCHEDULED path, with no network. Returns (folder, file, row)."""
    rpc = ctx.adapter.rpc
    if folder_id is None:
        folder_id = make_folder(rpc, make_server(rpc))
    content = csv_bytes(rows, columns=columns, header_offset=header_offset)
    file_id = make_sftp_file(rpc, folder_id,
                             fx(f"{MARK}_{file_label}.csv"), content)
    ctx.log(f"processing {len(rows)} requisition row(s) through the real "
            f"ETL (sftp.file {file_id}, no network)")
    return folder_id, file_id, process_file(ctx, file_id)


def run_wizard(ctx, rows, columns=None, file_name=None):
    """The MANUAL path — the same ETL, no sftp.file, no transport.

    ``import_requisition`` is public, takes the bytes off the wizard's
    Binary field and calls the same ``_transform_…`` / ``_process_…`` pair,
    then returns the quotations action with a domain naming the created
    orders. Returns (raised, action-or-message).
    """
    rpc = ctx.adapter.rpc
    content = csv_bytes(rows, columns=columns)
    wizard_id = rpc.create(WIZARD_MODEL, {
        "name": file_name or fx(f"{MARK}_manual.csv"),
        "file_content": base64.b64encode(content).decode("ascii"),
    })
    try:
        action = rpc.call(WIZARD_MODEL, "import_requisition", [wizard_id])
        ctx.log(f"wizard {wizard_id} returned: {action!r}")
        return False, action
    except OdooRPCError as exc:
        ctx.log(f"wizard {wizard_id} raised: {exc}")
        return True, str(exc)


def action_order_ids(action):
    """The order ids named by the wizard's returned action domain."""
    if not isinstance(action, dict):
        return []
    for clause in action.get("domain") or []:
        if isinstance(clause, (list, tuple)) and len(clause) == 3 \
                and clause[0] == "id" and clause[1] == "in":
            return sorted(clause[2] or [])
    return []


# ------------------------------------------------------------- assertions
ORDER_FIELDS = ["name", "origin", "state", "internal_memo", "requester",
                "requester_email", "requisition_date", "memo_to_suppliers",
                "order_type", "imported_from_workday", "partner_id",
                "partner_shipping_id", "order_line"]


def orders_for(rpc, requisition_nums, fields_=None):
    """Every sale.order this suite's import produced, by ``origin``."""
    fields_ = fields_ or ORDER_FIELDS
    fields_ = [f for f in fields_ if rpc.field_exists("sale.order", f)]
    return rpc.search_read("sale.order",
                           [("origin", "in", list(requisition_nums)),
                            ("active", "in", [True, False])],
                           fields_, order="id")


def order_lines(rpc, order_id, fields_=None):
    fields_ = fields_ or ["product_id", "name", "product_uom_qty",
                          "price_unit", "analytic_distribution",
                          "display_type", "expected_delivery_date",
                          "product_uom_id", "product_uom"]
    fields_ = [f for f in fields_
               if f == "name" or rpc.field_exists("sale.order.line", f)]
    return rpc.search_read("sale.order.line",
                           [("order_id", "=", order_id)], fields_,
                           order="id")


def distribution_accounts(distribution) -> set:
    """The analytic account ids a distribution names.

    DataOne encodes multi-plan distributions as comma-joined ids
    (``{"22,23": 100}``) and delta §2.14 leaves that format an open Unknown
    on v19 — so every comparison here is by RESOLVED ACCOUNT SET, not by
    raw key string: a shape change must not be reported as a value change.
    ``__update__`` is core's merge directive, never an account.
    """
    result = set()
    for key in (distribution or {}):
        if key == "__update__":
            continue
        for part in str(key).split(","):
            part = part.strip()
            if part.isdigit():
                result.add(int(part))
    return result


def plans_of(rpc, account_ids):
    """{analytic account id: plan id} — for the Cost-Centre absence check."""
    if not account_ids:
        return {}
    field = ("plan_id" if rpc.field_exists("account.analytic.account",
                                           "plan_id") else "root_plan_id")
    rows = rpc.read("account.analytic.account", sorted(account_ids), [field])
    return {row["id"]: m2o_id(row[field]) for row in rows}


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
    """The ETL message, from whichever surface received it."""
    parts = [str(act.get("note") or "")
             for act in activities_on(rpc, "sftp.file", [file_id])]
    messages = rpc.search_read("mail.message",
                               [("model", "=", "sftp.file"),
                                ("res_id", "=", file_id)], ["body"],
                               order="id")
    parts += [str(row.get("body") or "") for row in messages]
    return " || ".join(p for p in parts if p)


def population_counts(rpc, requisition_nums=()):
    """The four counts TC340 step 1 records and step 12 re-checks.

    Token-scoped, so the assertion is "this execution created nothing"
    rather than "the database did not change", which on a live clone would
    be neither true nor assertable.
    """
    return {
        "sale.order": len(rpc.search(
            "sale.order", [("origin", "in", list(requisition_nums)),
                           ("active", "in", [True, False])]))
        if requisition_nums else len(rpc.search(
            "sale.order", [("origin", "like", f"{MARK}-%"),
                           ("active", "in", [True, False])])),
        "res.partner": len(rpc.search(
            "res.partner", [("name", "like", f"{MARK} %"),
                            ("active", "in", [True, False])])),
        "product.product": len(rpc.search(
            "product.product", [("default_code", "like", f"{MARK}-%"),
                                ("active", "in", [True, False])])),
        "account.analytic.account": len(rpc.search(
            "account.analytic.account", [("name", "like", f"{MARK}-%"),
                                         ("active", "in", [True, False])])),
    }


def expect_error(rpc_callable, *args, **kwargs):
    try:
        rpc_callable(*args, **kwargs)
        return False, "no error raised"
    except OdooRPCError as exc:
        return True, str(exc)


def cron_row(rpc, xmlid):
    module, _, name = xmlid.partition(".")
    data = rpc.search_read("ir.model.data",
                           [("model", "=", "ir.cron"),
                            ("module", "=", module), ("name", "=", name)],
                           ["res_id"], limit=1)
    if not data:
        return None
    fields_ = [f for f in ("cron_name", "active", "interval_number",
                           "interval_type", "code")
               if rpc.field_exists("ir.cron", f)]
    row_ = rpc.read("ir.cron", [data[0]["res_id"]], fields_)[0]
    row_["xml_id"] = xmlid
    return row_
