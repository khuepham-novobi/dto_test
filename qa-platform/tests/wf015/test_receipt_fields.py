"""DATAONE-WF-015 — receipt carrier/tracking fields and the PO money trail.

Two cases about what a receipt and its purchase order expose once the goods
have arrived. Abbreviations used in the citations below: ``DTO`` =
``D:/Projects/dataone/DTO-Odoo``, ``O17`` = ``D:/Projects/dataone/odoo-17.0``,
``O19`` = ``D:/Projects/odoo-19.0``.

What this file proves
=====================

TC219 — carrier and tracking reference are editable and tracked
--------------------------------------------------------------
``stock_delivery`` injects its *Shipping Information* group into the **one**
``stock.picking`` form every operation type renders
(``O17 stock_delivery/views/delivery_view.xml:14-57``, inheriting
``stock.view_picking_form``), and it puts the same modifier on both fields::

    <field name="carrier_id"           readonly="state in ('done', 'cancel')"/>  :23
    <field name="carrier_tracking_ref" readonly="state in ('done', 'cancel')"/>  :27

``dto_purchase_stock`` overrides both with an **unconditional** ``readonly``
of ``0`` (``DTO project-addons/dto_purchase_stock/views/stock_picking_views.xml:
15-17`` and ``:18-20``) and redefines the two fields with ``tracking=True``
(``models/stock_picking.py:17-19`` for ``carrier_tracking_ref`` —
``Char(string='Tracking Reference', copy=False, tracking=True)`` — and
``:21-24`` for ``carrier_id`` —
``Many2one('delivery.carrier', string="Carrier", check_company=True,
tracking=True)``). Core declares neither field ``tracking`` (``O17
stock_delivery/models/stock_picking.py:90`` and ``:92``), so every
``mail.tracking.value`` row this case reads exists **because of DTO**.

Two corrections this test records rather than repeats (plan findings 7 and 9,
``docs/WF-015_AUTOMATION_PLAN.md``):

1. The workbook's rationale — "Odoo makes both read-only on incoming
   transfers" — is **wrong about which readonly is forced off**. The core
   modifier is ``state in ('done', 'cancel')``, not a picking-type test, and
   the group is injected into every picking form, not just outgoing ones. So
   the DTO forcing is what keeps the two fields editable on a **done or
   cancelled** transfer. That changes no assertion here (the fields must be
   present and editable, and they are), but the arch assertion pins the
   literal ``"0"`` so a future conditional forcing fails loudly. v19 keeps
   the first readonly (``O19 stock_delivery/views/delivery_view.xml:23``) and
   has already dropped the second (``:28``).
2. Two tracked fields changed in **one** ``write`` produce **one**
   ``mail.message`` carrying **two** ``mail.tracking.value`` rows — not two
   messages (``O17 mail/models/mail_tracking_value.py:_create_tracking_values``
   builds one row per changed field, ``:53-106``; the message is created once
   per ``_track_finalize``). The workbook's "two chatter tracking lines, one
   per field" is therefore asserted at the tracking-**value** level, which is
   what ``common.tracking_values`` returns, and the single-message fact is
   asserted alongside it instead of being silently dropped.

Value encoding, read from ``O17 mail/models/mail_tracking_value.py:94-98``:
a ``many2one`` change stores ``old_value_integer``/``new_value_integer`` (the
ids) **and** ``old_value_char``/``new_value_char`` (the display names); a
``char`` change stores only the ``*_value_char`` pair (``:68-72``). Both
shapes are identical on v19 (``O19 .../mail_tracking_value.py:15-30``).

``copy()``: ``carrier_tracking_ref`` carries ``copy=False`` in core **and** in
the DTO redefinition (``O17 stock_delivery/models/stock_picking.py:92``;
``DTO .../stock_picking.py:18``), while ``carrier_id`` carries no ``copy=``
anywhere (``O17 :90``; ``DTO :21-24``) and therefore **does** copy. That is
the verified answer to step 10's "record whether carrier_id copied".

TC220 — the Journal Entries stat button unions valuation and billing
--------------------------------------------------------------------
``purchase.order.account_move_ids`` is a **non-stored** ``Many2many`` compute
(``DTO .../dto_purchase_stock/models/purchase_order.py:17-19``) whose body is
exactly two terms (``:35-39``)::

    account_moves  = res.picking_ids.move_ids.account_move_id   # receipt
    account_moves |= res.order_line.invoice_lines.move_id       # bill

**A ``stock.scrap`` entry DOES reach that union, and step 11 therefore fails
on both versions.** The compute's own inline comment says so
(``# From Receipt / Scrap``, ``:37`` on UAT, ``:26`` on ``main``), and the
mechanism is in core: ``stock.scrap._prepare_move_values`` stamps
``'picking_id': self.picking_id.id`` onto the scrap move
(``O17 stock/models/stock_scrap.py:137``; ``O19 :149``), and
``stock.picking.move_ids`` is a plain ``One2many('stock.move','picking_id')``
with **no domain** (``O17 stock/models/stock_picking.py:465``; ``O19 :617``) —
core reads the same link back through
``search_count([('picking_id','=',picking.id),('scrapped','=',True)])`` in
``_has_scrap_move`` (``O17 :698-701``). So once the scrap is validated against
this order's receipt, ``res.picking_ids.move_ids`` contains the scrap move and
its valuation entry joins ``purchase.order.account_move_ids``.

The workbook nevertheless asks for the opposite at step 11 ("assert its entry
is not pulled onto the purchase order"). Hard rule 2 makes that expectation
immutable, so the assertion stays exactly as the workbook words it and the
resulting FAIL is the recorded baseline (see "Expected outcomes"). The
picking-side half of the contrast is real and still asserted: the picking's own
union (``DTO .../dto_stock/models/stock_picking.py:20-46``, which searches
``[('picking_id', '=', self.id)]`` at ``:32`` inside ``for res in self`` and
unions ``res.move_ids.account_move_id`` at ``:44``) does pick the entry up, and
belongs to INV/TC167-TC168.

``action_view_journal_entries`` (``:62-77``) returns ``None`` when the union
is empty (``:63-64``), and otherwise ``account.action_account_moves_all``
(``O17 account/views/account_move_views.xml:1619-1626`` — ``res_model``
``account.move.line``, name "Journal Items") with four keys replaced:
``name`` and ``display_name`` → ``'Journal Entries'`` (``:68-69``), ``domain``
→ ``[('id', 'in', self.account_move_ids.line_ids.ids)]`` (``:70``) and
``context`` → ``{'search_default_group_by_move': True, 'journal_type':
'general', 'expand': True}`` (``:71-75``). Replacing the context **drops**
the action's own ``search_default_posted`` — recorded, not asserted.
``search_default_group_by_move`` resolves against the core filter
``<filter name="group_by_move" context="{'group_by': 'move_name'}"/>``
(``O17 account/views/account_move_views.xml:359``; ``O19 :373`` — identical),
which is what "grouped by entry" means.

The valuation entry's shape is read from core, not guessed:
``stock_account/models/stock_move.py:_account_entry_move`` calls
``_prepare_account_move_vals(acc_src, acc_valuation, ...)`` for an incoming
move (``O17 :580-584``) and the signature is
``(credit_account_id, debit_account_id, …)`` (``O17 :401``), i.e. the entry
**debits** the category's ``property_stock_valuation_account_id`` and
**credits** ``_get_src_account`` =
``location_id.valuation_out_account_id.id or accounts_data['stock_input'].id``
(``O17 :392-393``, the location field at
``O17 stock_account/models/stock_location.py:17``). The test computes the
expected counterpart from exactly that expression rather than assuming the
category account, so a database that overrides the account on the supplier
location still passes for the right reason.

Step 12 is the multi-record recompute. The ``purchase.order`` compute is
correct — it uses ``res`` throughout (``:36-39``) — so the recompute passes;
the ``ValueError: Expected singleton`` the workbook anticipates lives on
``stock.picking`` (``dto_stock/models/stock_picking.py:32``) and is logged,
not re-asserted here. Separately, ``action_view_journal_entries`` has **no**
``ensure_one()`` while reading ``self.account_move_ids`` (``:62-63``), so a
multi-record call **does** raise — an assertable fact of its own, and the
test asserts it.

Step 3 has nothing to count. Unlike the paperclip button, whose child is
``<field name="packing_slip_receipt_count" widget="statinfo"/>``
(``DTO .../views/purchase_order_views.xml:15``), the Journal Entries button
(``:18-25``) carries only a static label inside ``div.o_stat_info``
(``:22-24``) and an ``invisible="not account_move_ids"`` modifier (``:21``)
backed by an invisible field node at ``:17``. The test asserts that arch fact
and asserts the union's length directly, per plan finding 9.

Expected outcomes
=================
* ``TEST-WF015-TC219`` — **EXPECTED v17 OUTCOME: PASS.** Every fact it
  asserts is contributed by ``stock_delivery`` plus the DTO override, both of
  which the installed v17 revision must carry (probed by
  ``common.require_carrier_fields``, which reports BLOCKED rather than FAIL
  when it does not). On a single-``res.company`` target the run reports
  **SKIPPED at step 11** (adaptation 4). EXPECTED v19 OUTCOME: PASS — the two
  fields, their ``tracking=True`` and the ``copy=False`` are unchanged there.
* ``TEST-WF015-TC220`` — **EXPECTED v17 OUTCOME: FAIL at step 11.**
  Steps 1-10 and 12-13 are expected to PASS (or the case BLOCKS with a precise
  reason when the target cannot produce a valuation entry — no stock accounts
  configured for the company — or refuses to post the fixture bill). Step 11
  fails because the scrap's valuation entry IS on
  ``purchase.order.account_move_ids``: the compute unions
  ``picking_ids.move_ids.account_move_id`` and labels that term
  ``# From Receipt / Scrap`` itself (``:37``), while
  ``stock.scrap._prepare_move_values`` writes the receipt onto the scrap move
  (``O17 stock/models/stock_scrap.py:137``) and ``stock.picking.move_ids``
  carries no domain (``O17 stock/models/stock_picking.py:465``). The
  workbook's expectation is immutable (hard rule 2), so the assertion stays as
  written and the FAIL is the recorded v17 baseline; it classifies as FIXED
  only if the product stops pulling scrap valuation onto the order.
  Consequence to read with it: ``ctx.check`` raises, so steps 12 and 13 are
  **not reached** until that changes — they are written in workbook order
  regardless.
  EXPECTED v19 OUTCOME: **FAIL at step 11 for the same reason.** (The
  v17/v19 build asymmetry runs the other way round from what an earlier draft
  of this docstring said: the on-disk source already reads the singular
  ``stock.move.account_move_id`` at ``purchase_order.py:34,37``, so it builds
  on v19 and is the *v17* registry that raises — see ``common._PORT_NOTE``
  and the plan doc's registry-failure table. ``git show main:`` still carries
  the plural ``account_move_ids``, which is the v17 form.) On v19, batching
  also changes the shape: several stock moves land in one ``account.move``
  (``O19 stock_account/models/stock_move.py:51`` and the inverse
  ``account.move.stock_move_ids``), so step 13's recorded entry count
  legitimately changes and must be signed off rather than treated as a
  defect — which is exactly why step 13 records instead of asserting.
* ``DATAONE-TC015`` — **NOT WRITTEN.** ``reports/data/wf015_feasibility.json``
  decides it ``not_implemented`` and ``docs/WF-015_AUTOMATION_PLAN.md`` lists
  it Out of scope: it is a MANUAL procurement and licensing gate whose every
  step is a shell procedure (``dropdb``/``createdb``/``odoo-bin -i …
  --stop-after-init``) against an ``/opt/odoo19`` path that does not exist on
  this workstation, plus a purchasing decision. The only automatable slice —
  a static read of the two manifests — reads the **v17** builds today
  (``3rd-addons/printnode_base/__manifest__.py:10`` = ``'17.0.2.6.10'`` and
  ``3rd-addons/location_barcode_labels/__manifest__.py:6`` = ``"2.0"``, both
  recorded in ``common.COMMERCIAL_V17_VERSIONS``) and so proves nothing about
  a v19 gate. Its step 4 is additionally superseded by WF-000 decision D-1:
  ``dto_base/__manifest__.py:17-45`` no longer depends on ``printnode_base``
  at all. The wave's policy leaves MANUAL types unimplemented, so no
  ``@test_case`` is registered for it and the registry reports it
  NOT_IMPLEMENTED.

Documented adaptations (hard rules 3 and 5)
===========================================
1. **TC219's receipt is a bare namespaced incoming ``stock.picking``,** not a
   confirmed purchase order's receipt. Carrier and tracking reference are
   picking-level fields; nothing in the case touches a move, a line or a
   quantity, and ``location_id``/``location_dest_id`` are ``precompute=True``
   computes off ``picking_type_id`` on both versions (``O17
   stock/models/stock_picking.py:457-464``), so the lighter fixture is also
   the more deterministic one. It is created under the suite's token, swept
   through its namespaced ``partner_id`` by ``common.sweep_wf015``, and never
   validated — so this case leaves nothing irreversible behind.
2. **No impersonation.** Both workbook step 1s read "Log in as TD-U-03 /
   TD-U-02". Those labels are test-data names, not ``res.groups`` XML ids —
   ``dto_purchase_stock/security/ir.model.access.csv`` holds exactly one row
   (the label wizard for ``base.group_user``) and the module declares no
   ``res.groups`` and no ``ir.rule`` at all — and neither case is about an
   access rule: field editability is a view/ORM fact and the stat button is
   arch. The platform session is used and the role is logged at step 1.
3. **TC220 creates its own valuation category** rather than writing
   ``property_valuation`` onto a pre-existing one (rule 3). The new
   ``product.category`` is token-named and copies whatever accounts and
   journal the database's default category already carries; on v17 the
   ``_check_valuation_accounts`` constraint then fills anything still empty
   from the company's ``ir.property`` defaults (``O17
   stock_account/models/product.py:872-882``), which is why the record is
   read **back** rather than trusted: a company with no stock accounts at all
   yields an unusable category, and that is an environment gap reported as
   BLOCKED, not a failure of F076.
4. **TC219 step 11 skips rather than invents.** ``check_company=True`` needs a
   carrier owned by a second ``res.company``; creating a company would be a
   master-data change, so ``common.require_second_company`` ``ctx.skip``s with
   that reason (plan adaptation 9). A skip ends the run, so step 12 is not
   reached on a single-company target — but its subject (the modifier is the
   unconditional literal ``"0"``, carrying no picking-type qualifier) is
   already asserted at steps 2 and 3, so nothing is left unproven.
5. **Nothing here can send.** ``grep -rn 'send_mail\\|force_send'`` over
   ``dto_purchase``, ``dto_purchase_stock`` and ``dto_account`` returns
   nothing, so neither ``button_confirm`` nor ``action_post`` reaches a mail
   server; the tracked writes post ``mail.message`` rows, which is
   in-database bookkeeping. No cron, no PrintNode, no SFTP (rule 4).
6. **TC220's residue is inherent and cleaned best effort.** A done receipt
   cannot be unlinked and a posted ``account.move`` resists it, so the
   ``finally`` attempts ``button_draft`` + ``unlink`` on the fixture bill and
   then hands the rest to ``common.sweep_wf015``, which is best effort by
   design — it is the per-execution token, not the sweep, that guarantees
   isolation.
"""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET

from adapters.base import OdooRPCError
from framework.fg_common import form_arch
from framework.qa_fixtures import default_categ_id
from framework.registry import test_case

from tests.wf015.common import (ERROR_BILL_REQUIRES_ATTACHMENT, WORKFLOW,
                                WORKFLOW_NAME, XMLID_ACTION_MOVES_ALL,
                                XMLID_GROUP_STOCK_USER,
                                confirm_purchase_order, copied_id,
                                default_picking_type,
                                ensure_carrier, ensure_vendor, expect_error,
                                m2o_id, make_product, make_purchase_order,
                                open_namespace, order_account_moves,
                                order_picking_ids, order_row, own_company_id,
                                po_line_values, receive_fully,
                                require_carrier_fields,
                                require_journal_entries,
                                require_second_company, sku, sweep_wf015, tag,
                                tiny_pdf_b64, trace, tracking_values,
                                vendor_location_id,
                                view_journal_entries_action)

# ---------------------------------------------------------------------------
# Literals the workbook names, and the fixture constants
# ---------------------------------------------------------------------------
#: TC219 steps 4 and 7, verbatim from the workbook.
TRACKING_REF_FIRST = "TRK-0001"
TRACKING_REF_SECOND = "TRK-0002"

#: The two fields under test — DTO redefinitions at
#: dto_purchase_stock/models/stock_picking.py:21-24 and :17-19.
CARRIER_FIELD = "carrier_id"
TRACKING_FIELD = "carrier_tracking_ref"
#: dto_purchase_stock/models/stock_picking.py:22 and :17 — the labels the
#: workbook calls "the Carrier field" and "the Tracking Reference field".
CARRIER_LABEL = "Carrier"
TRACKING_LABEL = "Tracking Reference"
#: views/stock_picking_views.xml:16 and :19 — the literal the forcing writes.
READONLY_FORCED_OFF = "0"

#: dto_purchase_stock/views/purchase_order_views.xml:19 and :21.
JOURNAL_BUTTON = "action_view_journal_entries"
JOURNAL_BUTTON_INVISIBLE = "not account_move_ids"
#: :11 and :15 — the sibling button, the one that DOES carry a counter.
PACKING_SLIP_BUTTON = "action_view_packing_slip_attachments"
PACKING_SLIP_COUNTER = "packing_slip_receipt_count"

#: O17 account/views/account_move_views.xml:359 / O19 :373 — byte-identical.
GROUP_BY_MOVE_FILTER = "group_by_move"
GROUP_BY_MOVE_CONTEXT = "{'group_by': 'move_name'}"
#: dto_purchase_stock/models/purchase_order.py:68-75.
JOURNAL_ACTION_NAME = "Journal Entries"
JOURNAL_ACTION_CONTEXT = {"search_default_group_by_move": True,
                          "journal_type": "general", "expand": True}

#: TC220 fixture money. Taxes are zeroed by common.po_line_values, and the PO
#: price equals the standard price so no anglo-saxon price-difference line is
#: generated — the entry count stays at exactly two.
UNIT_COST = 25.0
ORDER_QTY = 2.0
SCRAP_QTY = 1.0
#: The union after a validated receipt and a posted bill: one valuation entry
#: (one stock.move) plus one vendor bill.
EXPECTED_UNION_SIZE = 2
#: A fixed date, never "today": rule 5 forbids time-dependent values. The same
#: literal the WF-013 suite bills on (tests/wf013/common.py:416), so the two
#: suites cannot disagree about which period they post into.
BILL_DATE = "2026-01-15"
PO_DATE_PLANNED = "2026-02-02 08:00:00"

#: O17 account/models/account_account.py:58 — unchanged on v19 (:52).
PAYABLE_ACCOUNT_TYPE = "liability_payable"

#: O17 stock_account/models/product.py:829-860 — all company_dependent.
CATEG_VALUATION_FIELDS = ("property_valuation", "property_cost_method",
                          "property_stock_journal",
                          "property_stock_account_input_categ_id",
                          "property_stock_account_output_categ_id",
                          "property_stock_valuation_account_id")
#: Without these three an incoming move cannot be valued at all
#: (O17 stock_account/models/product.py:83-94, consumed by
#: _get_accounting_data_for_valuation).
CATEG_REQUIRED_FOR_VALUATION = ("property_stock_journal",
                                "property_stock_account_input_categ_id",
                                "property_stock_valuation_account_id")

#: OdooRPC.call prefixes every server fault with "<model>.<method> failed: "
#: (adapters/base.py:171-178). Stripped before a message is logged — never
#: the message itself.
_RPC_PREFIX = " failed: "


# ---------------------------------------------------------------------------
# Local helpers
#
# Everything below is absent from tests/wf015/common.py (which another agent
# owns and this file must not edit). Nothing here duplicates a helper that
# module already provides.
# ---------------------------------------------------------------------------
def _error_tail(message) -> str:
    """The server's own message, with the transport's prefix removed."""
    text = str(message)
    if _RPC_PREFIX in text:
        return text.split(_RPC_PREFIX, 1)[1].strip()
    return text.strip()


def _arch_text(value) -> str:
    """Normalise a ``get_view()['arch']`` payload to ``str``."""
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-8", "replace")
    return value if isinstance(value, str) else str(value)


def _parse_arch(arch) -> ET.Element:
    """Parse an arch string with the stdlib parser (no lxml in this venv).

    ``xml.etree`` supports ``.//tag[@attr='value']`` predicates, which is all
    this file needs; it does NOT support ``not()``, so absence is asserted by
    an empty match list rather than by a negative xpath.
    """
    return ET.fromstring(_arch_text(arch))


def _field_nodes(root, name: str) -> list:
    return [node for node in root.iter("field") if node.get("name") == name]


def _button_nodes(root, name: str) -> list:
    return [node for node in root.iter("button") if node.get("name") == name]


def _readonly_modifiers(nodes) -> list:
    """Every distinct ``readonly`` modifier across a set of field nodes.

    Stringified so a missing attribute sorts next to a present one instead of
    raising on a ``None`` comparison. ``["0"]`` means *every* node carrying
    that field name is unconditionally editable — a stronger claim than "the
    first one is", and the one the xpath at
    ``views/stock_picking_views.xml:15-20`` is supposed to produce.
    """
    return sorted({str(node.get("readonly")) for node in nodes})


def _stock_move_account_field(rpc) -> str | None:
    """``account_move_ids`` on v17, ``account_move_id`` on v19.

    v17 ``stock_account/models/stock_move.py:19`` is the One2many
    ``account_move_ids``; v19 ``:51`` is the singular Many2one
    ``account_move_id``. Resolved through ``field_exists`` — the shape
    ``common.po_line_uom_field`` uses — so no test body reads
    ``ctx.env.version``.
    """
    for name in ("account_move_id", "account_move_ids"):
        if rpc.field_exists("stock.move", name):
            return name
    return None


def _account_moves_of_moves(rpc, move_ids) -> list:
    """The ``account.move`` ids behind a set of ``stock.move`` ids."""
    field = _stock_move_account_field(rpc)
    if not field or not move_ids:
        return []
    found = set()
    for row in rpc.read("stock.move", list(move_ids), [field]):
        value = row.get(field)
        if field == "account_move_ids":
            found.update(value or [])
        else:
            one = m2o_id(value)
            if one:
                found.add(one)
    return sorted(found)


def _picking_move_ids(rpc, picking_id: int) -> list:
    return rpc.search("stock.move", [("picking_id", "=", picking_id)])


def _move_lines(rpc, move_ids, fields_=None) -> list:
    if not move_ids:
        return []
    fields_ = fields_ or ["move_id", "account_id", "debit", "credit"]
    return rpc.search_read("account.move.line",
                           [("move_id", "in", list(move_ids))], fields_,
                           order="id")


def _account_types(rpc, account_ids) -> dict:
    """``{account id: account_type}`` — read, never inferred from a code."""
    ids = sorted({i for i in account_ids if i})
    if not ids:
        return {}
    return {row["id"]: row.get("account_type")
            for row in rpc.read("account.account", ids, ["account_type"])}


def _role_note(role: str, why: str) -> str:
    """One log line recording the workbook role and why it is not assumed."""
    return (f"workbook role {role}: the label is test data, not a res.groups "
            f"XML id — dto_purchase_stock declares no res.groups and no "
            f"ir.rule (security/ir.model.access.csv:2 holds exactly one row, "
            f"the label wizard for base.group_user). {why} The platform "
            f"session is used; the only groups marker in this area is "
            f"{XMLID_GROUP_STOCK_USER} on the paperclip button "
            f"(views/purchase_order_views.xml:14), which is not this case's "
            f"subject.")


def _make_picking(ctx, partner_id: int, code: str = "incoming",
                  label: str = "Receipt") -> int:
    """A namespaced, never-validated ``stock.picking`` of that operation code.

    ``location_id`` and ``location_dest_id`` are ``precompute=True`` computes
    off ``picking_type_id`` on both versions (``O17
    stock/models/stock_picking.py:457-464``), so passing the type is normally
    enough; the operation type's own defaults are passed as well when it
    declares them, and a supplier location is the incoming fallback
    (``common.vendor_location_id``). The pre-existing operation type is
    **read**, never written (rule 3).
    """
    rpc = ctx.adapter.rpc
    type_id = default_picking_type(rpc, code, company_id=own_company_id(rpc))
    row = rpc.read("stock.picking.type", [type_id],
                   ["default_location_src_id", "default_location_dest_id"])[0]
    values = {"picking_type_id": type_id, "partner_id": partner_id,
              "origin": tag(label)}
    source = m2o_id(row.get("default_location_src_id"))
    if not source and code == "incoming":
        source = vendor_location_id(rpc)
    if source:
        values["location_id"] = source
    destination = m2o_id(row.get("default_location_dest_id"))
    if destination:
        values["location_dest_id"] = destination
    return rpc.create("stock.picking", values)


def _valuation_category_id(ctx, created: list) -> int:
    """A token-named ``product.category`` with automated valuation.

    Rule 3 forbids writing ``property_valuation`` onto a pre-existing
    category, so a new one is created and the database's default category is
    read for the accounts and journal to copy. On v17 the
    ``_check_valuation_accounts`` constraint then fills anything still empty
    from the company's ``ir.property`` defaults (``O17
    stock_account/models/product.py:872-882``), which is why the record is
    read **back** rather than trusted: a company with no stock accounts at all
    yields an unusable category, and that is an environment gap to report as
    BLOCKED, not a failure of F076.

    ``created`` is appended to before any block, so the caller's ``finally``
    can still remove the record.
    """
    rpc = ctx.adapter.rpc
    present = [name for name in CATEG_VALUATION_FIELDS
               if rpc.field_exists("product.category", name)]
    if "property_valuation" not in present:
        ctx.blocked(
            "product.category.property_valuation does not exist on "
            f"{ctx.env.key} (db={ctx.env.db}) — stock_account is not "
            "installed, so a receipt can never produce the valuation-entry "
            "half of purchase.order.account_move_ids "
            "(dto_purchase_stock/models/purchase_order.py:37).")

    source_id = default_categ_id(rpc)
    source = (rpc.read("product.category", [source_id], present)[0]
              if source_id else {})
    values = {"name": tag("TD-PC-02 Automated Valuation"),
              "property_valuation": "real_time"}
    if "property_cost_method" in present:
        # Standard cost keeps the entry's amount a property of the fixture
        # (standard_price x qty) instead of of the database's cost history.
        values["property_cost_method"] = "standard"
    for name in ("property_stock_journal",
                 "property_stock_account_input_categ_id",
                 "property_stock_account_output_categ_id",
                 "property_stock_valuation_account_id"):
        if name in present and m2o_id(source.get(name)):
            values[name] = m2o_id(source[name])

    categ_id = rpc.create("product.category", values)
    created.append(categ_id)
    row = rpc.read("product.category", [categ_id], present)[0]
    missing = [name for name in CATEG_REQUIRED_FOR_VALUATION
               if name in present and not m2o_id(row.get(name))]
    if row.get("property_valuation") != "real_time" or missing:
        ctx.blocked(
            f"The fixture product category on {ctx.env.key} (db={ctx.env.db}) "
            f"reads property_valuation={row.get('property_valuation')!r} and "
            f"is missing {missing or 'nothing'}. Automated valuation needs a "
            "stock journal, a stock input account and a stock valuation "
            "account (O17 stock_account/models/product.py:83-94); without "
            "them the receipt produces no account.move and TC220 has no "
            "valuation entry to union. Configure the company's stock "
            "accounts, then re-run.")
    ctx.log(f"fixture product.category {categ_id} — real_time valuation, "
            f"journal={m2o_id(row.get('property_stock_journal'))}, "
            f"input={m2o_id(row.get('property_stock_account_input_categ_id'))}"
            f", valuation="
            f"{m2o_id(row.get('property_stock_valuation_account_id'))}")
    return categ_id


def _assign_category(rpc, product_id: int, categ_id: int) -> None:
    """Move a freshly created product onto the valuation category.

    ``common.make_product`` builds its own values dict and resolves the
    category through ``qa_fixtures.with_categ``, so the category is written
    afterwards — safely, because the product has no quant, no move and no
    valuation layer at this point.
    """
    tmpl_id = m2o_id(rpc.read("product.product", [product_id],
                              ["product_tmpl_id"])[0]["product_tmpl_id"])
    rpc.write("product.template", [tmpl_id], {"categ_id": categ_id})


def _expected_valuation_accounts(rpc, categ_row: dict, move_row: dict) -> dict:
    """The accounts an incoming valuation entry must touch.

    Read straight off the two core expressions, never assumed:
    ``acc_valuation`` = ``categ_id.property_stock_valuation_account_id``
    (``O17 stock_account/models/product.py:85``) and ``acc_src`` =
    ``location_id.valuation_out_account_id.id or
    accounts_data['stock_input'].id``
    (``O17 stock_account/models/stock_move.py:392-393``). The move is the
    credit side, the valuation account the debit side
    (``O17 :584`` feeding ``:401``'s ``(credit, debit)`` signature).
    """
    debit = m2o_id(categ_row.get("property_stock_valuation_account_id"))
    credit = m2o_id(categ_row.get("property_stock_account_input_categ_id"))
    location_id = m2o_id(move_row.get("location_id"))
    if location_id and rpc.field_exists("stock.location",
                                        "valuation_out_account_id"):
        override = m2o_id(rpc.read("stock.location", [location_id],
                                   ["valuation_out_account_id"])[0]
                          .get("valuation_out_account_id"))
        if override:
            credit = override
    return {"debit_account": debit, "credit_account": credit}


def _create_vendor_bill(ctx, order_id: int, attachments: list) -> int:
    """Bill the received quantities and post the bill.

    ``purchase.order.action_create_invoice`` is public on both versions
    (``O17 purchase/models/purchase_order.py:575``; ``O19 :760``).
    ``dto_account/models/account_move.py:50-56`` then refuses to post a
    vendor bill with no attachment, so one is attached first — otherwise the
    whole case would fail for a reason that has nothing to do with F076.
    """
    rpc = ctx.adapter.rpc
    try:
        rpc.call("purchase.order", "action_create_invoice", [order_id])
    except OdooRPCError as exc:
        ctx.blocked(
            "The fixture purchase order could not be billed on "
            f"{ctx.env.key}: {_error_tail(exc)}. TC220 needs a posted vendor "
            "bill for the second half of the union "
            "(dto_purchase_stock/models/purchase_order.py:38).")
    invoice_ids = rpc.read("purchase.order", [order_id],
                           ["invoice_ids"])[0]["invoice_ids"]
    if not invoice_ids:
        ctx.blocked(
            "action_create_invoice produced no account.move for the fixture "
            f"order on {ctx.env.key}. Check the product's Control Policy — "
            "the union's bill half (purchase_order.py:38) reads "
            "order_line.invoice_lines.move_id and there would be nothing to "
            "read.")
    bill_id = sorted(invoice_ids)[-1]
    # A fixed invoice_date (rule 5) and a token-scoped ref, so a rerun cannot
    # collide with the previous run's duplicate-supplier-reference warning
    # (O17 account/models/account_move.py:1586-1590).
    rpc.write("account.move", [bill_id],
              {"invoice_date": BILL_DATE, "ref": sku("BILL")})

    attachment_id = rpc.create("ir.attachment", {
        "name": tag("vendor bill.pdf"),
        "res_model": "account.move", "res_id": bill_id,
        "datas": tiny_pdf_b64("WF015 TC220 vendor bill")})
    attachments.append(attachment_id)

    try:
        rpc.call("account.move", "action_post", [bill_id])
    except OdooRPCError as exc:
        message = _error_tail(exc)
        hint = ""
        if ERROR_BILL_REQUIRES_ATTACHMENT in message:
            hint = ("The attachment this test created did not reach "
                    "account.move.have_attachment "
                    "(dto_account/models/account_move.py:27-31). ")
        ctx.blocked(
            f"The fixture vendor bill could not be posted on {ctx.env.key}: "
            f"{message}. {hint}TC220 needs it posted so its entry joins the "
            "union.")
    return bill_id


def _safe(fn, *args, **kwargs):
    """Best-effort teardown call. Never raises, never reports."""
    try:
        return fn(*args, **kwargs)
    except OdooRPCError:
        return None


# ===========================================================================
# TC219 — F075, carrier and tracking reference on the receipt
# ===========================================================================
@test_case(
    id="TEST-WF015-TC219",
    name="Carrier and tracking reference are editable on a receipt and both "
         "changes are tracked",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_purchase_stock",
    priority="P2", kind="HYBRID", order=15219,
    description="The rendered picking form forces readonly=\"0\" on carrier_id "
                "and carrier_tracking_ref; writing both posts one mail.message "
                "carrying one mail.tracking.value per field; a second write "
                "records the old -> new pair; copy() drops the tracking "
                "reference (copy=False) and keeps the carrier; a carrier owned "
                "by another company is refused by check_company=True; and the "
                "same two fields are editable on an outgoing transfer.",
    traceability=trace("DATAONE-TC219"))
def test_tc219(ctx):
    rpc = ctx.adapter.rpc
    require_carrier_fields(ctx)
    open_namespace(ctx)
    duplicates = []
    try:
        with ctx.step("Log in as TD-U-03 and open the receipt."):
            ctx.log(_role_note(
                "TD-U-03 (Inventory User / Receiving clerk)",
                "Field editability is a view and ORM fact, not an access "
                "rule, so no impersonation is performed."))
            partner_id = ensure_vendor(rpc, "TD-PA-03")
            # The workbook precondition: "At least one delivery.carrier record
            # exists in the same company (check_company=True)."
            carrier_id = ensure_carrier(rpc, "Carrier",
                                        company_id=own_company_id(rpc))
            picking_id = _make_picking(ctx, partner_id, "incoming", "Receipt")
            row = rpc.read("stock.picking", [picking_id],
                           ["state", "picking_type_code", "partner_id",
                            CARRIER_FIELD, TRACKING_FIELD])[0]
            ctx.check("the fixture is a draft incoming transfer for the "
                      "namespaced vendor, with no carrier and no tracking "
                      "reference yet",
                      {"picking_type_code": "incoming", "state": "draft",
                       "partner": partner_id, "carrier": None,
                       "tracking_ref": False},
                      {"picking_type_code": row.get("picking_type_code"),
                       "state": row.get("state"),
                       "partner": m2o_id(row.get("partner_id")),
                       "carrier": m2o_id(row.get(CARRIER_FIELD)),
                       # Blank Char reads back as '' or False depending on the
                       # version; AUTOMATION_CONVENTIONS says compare with
                       # `value or False`.
                       "tracking_ref": row.get(TRACKING_FIELD) or False})

        with ctx.step("Assert the Carrier field is present and editable on "
                      "this incoming transfer."):
            # THE case: the rendered arch, not just a successful write. An
            # inherit can load cleanly and match nothing, and only the arch
            # distinguishes that from a working forcing.
            picking_root = _parse_arch(form_arch(ctx, "stock.picking", "form"))
            carrier_nodes = _field_nodes(picking_root, CARRIER_FIELD)
            carrier_info = rpc.call("stock.picking", "fields_get",
                                    [CARRIER_FIELD],
                                    attributes=["readonly", "string", "type",
                                                "relation"]).get(CARRIER_FIELD,
                                                                 {})
            ctx.check("every carrier_id node in the rendered picking form "
                      "carries the unconditional readonly=\"0\" forced by "
                      "dto_purchase_stock/views/stock_picking_views.xml:18-20, "
                      "and the field is writable at the ORM",
                      {"present": True,
                       "readonly_modifiers": [READONLY_FORCED_OFF],
                       "model_readonly": False, "string": CARRIER_LABEL,
                       "type": "many2one", "relation": "delivery.carrier"},
                      {"present": bool(carrier_nodes),
                       "readonly_modifiers": _readonly_modifiers(carrier_nodes),
                       "model_readonly": bool(carrier_info.get("readonly")),
                       "string": carrier_info.get("string"),
                       "type": carrier_info.get("type"),
                       "relation": carrier_info.get("relation")})
            ctx.log("core's own modifier on this node is "
                    "readonly=\"state in ('done', 'cancel')\" "
                    "(O17 stock_delivery/views/delivery_view.xml:23), so what "
                    "the forcing actually buys is editability on a DONE or "
                    "CANCELLED transfer — not, as the workbook's rationale "
                    "says, on an incoming one. v19 keeps that core modifier "
                    "(O19 delivery_view.xml:23).")

        with ctx.step("Assert the Tracking Reference field is present and "
                      "editable."):
            tracking_nodes = _field_nodes(picking_root, TRACKING_FIELD)
            tracking_info = rpc.call(
                "stock.picking", "fields_get", [TRACKING_FIELD],
                attributes=["readonly", "string", "type"]).get(TRACKING_FIELD,
                                                               {})
            ctx.check("every carrier_tracking_ref node carries the "
                      "unconditional readonly=\"0\" forced by "
                      "views/stock_picking_views.xml:15-17, and the field is "
                      "writable at the ORM",
                      {"present": True,
                       "readonly_modifiers": [READONLY_FORCED_OFF],
                       "model_readonly": False, "string": TRACKING_LABEL,
                       "type": "char"},
                      {"present": bool(tracking_nodes),
                       "readonly_modifiers":
                           _readonly_modifiers(tracking_nodes),
                       "model_readonly": bool(tracking_info.get("readonly")),
                       "string": tracking_info.get("string"),
                       "type": tracking_info.get("type")})
            ctx.log("v19 has already dropped core's readonly from this node "
                    "(O19 stock_delivery/views/delivery_view.xml:28) while "
                    "keeping it on carrier_id (:23) — the forcing therefore "
                    "becomes redundant for this field and stays load-bearing "
                    "for the other.")

        with ctx.step(f"Set Carrier and set Tracking Reference to "
                      f"{TRACKING_REF_FIRST}, then save."):
            rpc.write("stock.picking", [picking_id],
                      {CARRIER_FIELD: carrier_id,
                       TRACKING_FIELD: TRACKING_REF_FIRST})

        with ctx.step("Assert both values are stored."):
            stored = rpc.read("stock.picking", [picking_id],
                              [CARRIER_FIELD, TRACKING_FIELD])[0]
            ctx.check("the receipt carries the carrier and the first tracking "
                      "reference",
                      {"carrier": carrier_id,
                       "tracking_ref": TRACKING_REF_FIRST},
                      {"carrier": m2o_id(stored.get(CARRIER_FIELD)),
                       "tracking_ref": stored.get(TRACKING_FIELD) or False})

        with ctx.step("Assert two chatter tracking lines were posted on the "
                      "picking, one per field."):
            rows = [r for r in tracking_values(rpc, "stock.picking",
                                               picking_id)
                    if r.get("field_name") in (CARRIER_FIELD, TRACKING_FIELD)]
            by_field = {r["field_name"]: r for r in rows}
            ctx.check("one mail.tracking.value per tracked field, both on the "
                      "SAME mail.message (one write -> one message, two rows) "
                      "— tracking=True comes from dto_purchase_stock/models/"
                      "stock_picking.py:19 and :24, core declares neither "
                      "(O17 stock_delivery/models/stock_picking.py:90,92)",
                      {"tracked_fields": [CARRIER_FIELD, TRACKING_FIELD],
                       "rows": 2, "distinct_messages": 1,
                       "carrier_new_value_integer": carrier_id,
                       "tracking_new_value_char": TRACKING_REF_FIRST},
                      {"tracked_fields": sorted(by_field),
                       "rows": len(rows),
                       "distinct_messages":
                           len({m2o_id(r.get("mail_message_id"))
                                for r in rows}),
                       "carrier_new_value_integer":
                           (by_field.get(CARRIER_FIELD) or {})
                           .get("new_value_integer"),
                       "tracking_new_value_char":
                           (by_field.get(TRACKING_FIELD) or {})
                           .get("new_value_char") or False})

        with ctx.step(f"Change Tracking Reference to {TRACKING_REF_SECOND} "
                      f"and save."):
            rpc.write("stock.picking", [picking_id],
                      {TRACKING_FIELD: TRACKING_REF_SECOND})

        with ctx.step("Assert a further tracking line records the old → new "
                      "pair."):
            pairs = [[r.get("old_value_char") or False,
                      r.get("new_value_char") or False]
                     for r in tracking_values(rpc, "stock.picking", picking_id)
                     if r.get("field_name") == TRACKING_FIELD]
            ctx.check("carrier_tracking_ref carries two tracking rows in "
                      "order: the initial set, then the old -> new pair "
                      "(char changes store only the *_value_char pair, "
                      "O17 mail/models/mail_tracking_value.py:68-72)",
                      [[False, TRACKING_REF_FIRST],
                       [TRACKING_REF_FIRST, TRACKING_REF_SECOND]],
                      pairs)

        with ctx.step("Duplicate the receipt with copy()."):
            duplicate_id = copied_id(rpc.call("stock.picking", "copy",
                                               [picking_id]))
            if duplicate_id:
                duplicates.append(duplicate_id)
            ctx.check("copy() returned a new stock.picking id",
                      {"created": True, "distinct_from_source": True},
                      {"created": bool(duplicate_id),
                       "distinct_from_source": duplicate_id != picking_id})

        with ctx.step("Assert carrier_tracking_ref is empty on the duplicate "
                      "(copy=False) and record whether carrier_id copied."):
            duplicate = rpc.read("stock.picking", [duplicate_id],
                                 [CARRIER_FIELD, TRACKING_FIELD, "state"])[0]
            ctx.check("the duplicate loses the tracking reference "
                      "(copy=False, O17 stock_delivery/models/"
                      "stock_picking.py:92 and DTO .../stock_picking.py:18) "
                      "and KEEPS the carrier (no copy= anywhere: O17 :90, "
                      "DTO :21-24)",
                      {"tracking_ref": False, "carrier": carrier_id,
                       "state": "draft"},
                      {"tracking_ref": duplicate.get(TRACKING_FIELD) or False,
                       "carrier": m2o_id(duplicate.get(CARRIER_FIELD)),
                       "state": duplicate.get("state")})
            ctx.log("recorded, per the workbook's 'record whether carrier_id "
                    "copied': it does, on both versions — a duplicated "
                    "receipt inherits the carrier but never a stale tracking "
                    "number.")

        with ctx.step("Assert a carrier belonging to a different company "
                      "cannot be selected (check_company=True)."):
            # SKIPs (with a precise reason) on a single-company target rather
            # than creating a res.company, which rule 3 forbids.
            other_company_id = require_second_company(ctx)
            try:
                foreign_carrier_id = ensure_carrier(rpc, "OtherCoCarrier",
                                                    company_id=other_company_id)
            except OdooRPCError as exc:
                ctx.skip(
                    f"A delivery.carrier owned by res.company "
                    f"{other_company_id} could not be created on "
                    f"{ctx.env.key}: {_error_tail(exc)}. Without one, "
                    "check_company=True on stock.picking.carrier_id "
                    "(dto_purchase_stock/models/stock_picking.py:23) cannot "
                    "be exercised, and inventing the master data it needs "
                    "would breach rule 3.")
            raised, message = expect_error(
                rpc.write, "stock.picking", [picking_id],
                {CARRIER_FIELD: foreign_carrier_id})
            after = rpc.read("stock.picking", [picking_id],
                             [CARRIER_FIELD])[0]
            ctx.check("the write is refused and the stored carrier is "
                      "untouched — each RPC call is its own transaction, so "
                      "the rollback is real",
                      {"refused": True, "carrier": carrier_id},
                      {"refused": raised,
                       "carrier": m2o_id(after.get(CARRIER_FIELD))})
            ctx.log(f"server refusal (core's _check_company message, not "
                    f"DTO's, so it is recorded rather than asserted "
                    f"verbatim): {_error_tail(message)!r}")

        with ctx.step("Assert the same two fields remain editable on an "
                      "outgoing transfer (they are the same fields F075 "
                      "exposes there)."):
            # Arch half: stock.view_picking_form is the ONE form every
            # operation type renders, and the forcing carries no picking-type
            # qualifier — unlike the DTO label button in the same inherit,
            # which does (views/stock_picking_views.xml:12).
            label_button = _button_nodes(
                picking_root, "action_open_receipt_product_label_layout")
            try:
                outgoing_id = _make_picking(ctx, partner_id, "outgoing",
                                            "Delivery")
            except OdooRPCError as exc:
                ctx.blocked(
                    f"No outgoing stock.picking.type could be used on "
                    f"{ctx.env.key}: {_error_tail(exc)}. Step 12 asserts the "
                    "two fields behave identically on an outgoing transfer, "
                    "which needs one.")
            rpc.write("stock.picking", [outgoing_id],
                      {CARRIER_FIELD: carrier_id,
                       TRACKING_FIELD: TRACKING_REF_FIRST})
            outgoing = rpc.read("stock.picking", [outgoing_id],
                                ["picking_type_code", CARRIER_FIELD,
                                 TRACKING_FIELD])[0]
            ctx.check("the shared picking form forces readonly=\"0\" with no "
                      "picking-type qualifier (only the DTO label button is "
                      "incoming-only), and both fields accept a write on an "
                      "outgoing transfer",
                      {"picking_type_code": "outgoing",
                       "carrier": carrier_id,
                       "tracking_ref": TRACKING_REF_FIRST,
                       "carrier_readonly_modifiers": [READONLY_FORCED_OFF],
                       "tracking_readonly_modifiers": [READONLY_FORCED_OFF],
                       "label_button_is_incoming_only":
                           "picking_type_code != 'incoming'"},
                      {"picking_type_code": outgoing.get("picking_type_code"),
                       "carrier": m2o_id(outgoing.get(CARRIER_FIELD)),
                       "tracking_ref": outgoing.get(TRACKING_FIELD) or False,
                       "carrier_readonly_modifiers":
                           _readonly_modifiers(carrier_nodes),
                       "tracking_readonly_modifiers":
                           _readonly_modifiers(tracking_nodes),
                       "label_button_is_incoming_only":
                           (label_button[0].get("invisible")
                            if label_button else None)})
    finally:
        # The workbook's postcondition is "Delete the duplicate from step 9";
        # the whole namespace goes with it (rules 3 and 5). Never raises.
        try:
            if duplicates:
                _safe(rpc.call, "stock.picking", "unlink", duplicates)
            sweep_wf015(rpc)
        except Exception:  # noqa: BLE001
            pass


# ===========================================================================
# TC220 — F076, the purchase order's Journal Entries stat button
# ===========================================================================
@test_case(
    id="TEST-WF015-TC220",
    name="The purchase order's Journal Entries stat button unions valuation "
         "and billing entries",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_purchase_stock",
    priority="P1", kind="HYBRID", order=15220,
    description="purchase.order.account_move_ids unions the receipt's "
                "valuation entry with the vendor bill's entry and nothing "
                "else; action_view_journal_entries returns "
                "account.action_account_moves_all domained to "
                "account_move_ids.line_ids and grouped by entry; the "
                "workbook's step 11 (a scrap against the same receipt is not "
                "pulled in) is asserted unchanged and FAILS by construction "
                "on both versions, because purchase_order.py:37 unions "
                "picking_ids.move_ids.account_move_id and the scrap move "
                "carries picking_id; and a three-order recompute raises no "
                "singleton error.",
    traceability=trace("DATAONE-TC220"))
def test_tc220(ctx):
    rpc = ctx.adapter.rpc
    require_journal_entries(ctx)
    open_namespace(ctx)
    categories = []
    attachments = []
    bill_id = None
    try:
        with ctx.step("Log in as TD-U-02 and open the purchase order."):
            ctx.log(_role_note(
                "TD-U-02 (Purchasing User) / TD-U-06 (Cost Accountant)",
                "The stat button and its action are arch and ORM facts, not "
                "an access rule, so no impersonation is performed."))
            categ_id = _valuation_category_id(ctx, categories)
            categ_row = rpc.read("product.category", [categ_id],
                                 [name for name in CATEG_VALUATION_FIELDS
                                  if rpc.field_exists("product.category",
                                                      name)])[0]
            partner_id = ensure_vendor(rpc, "TD-PA-03")
            product_id = make_product(ctx, "TD-P-04", price=UNIT_COST)
            _assign_category(rpc, product_id, categ_id)

            order_id = make_purchase_order(
                ctx,
                [po_line_values(ctx, product_id, ORDER_QTY, PO_DATE_PLANNED,
                                price_unit=UNIT_COST)],
                partner_id=partner_id, label="TC220")
            confirm_purchase_order(rpc, order_id)
            # Counted off order.picking_ids, never off a search on origin —
            # v17 leaves core's own empty receipt behind and v19 unlinks it
            # (common.order_picking_ids).
            receipt_ids = order_picking_ids(rpc, order_id)
            if len(receipt_ids) != 1:
                ctx.blocked(
                    f"The fixture order produced {len(receipt_ids)} receipts "
                    f"on {ctx.env.key}, not 1. TC220 needs exactly one so the "
                    "valuation half of the union is unambiguous; the per-line "
                    "receipt split itself is TC201's subject.")
            receipt_id = receipt_ids[0]
            try:
                receive_fully(ctx, receipt_id)
            except OdooRPCError as exc:
                ctx.blocked(
                    f"The fixture receipt could not be validated on "
                    f"{ctx.env.key}: {_error_tail(exc)}. Automated valuation "
                    "needs the company's stock accounts and journal "
                    "(O17 stock_account/models/product.py:83-94); without a "
                    "validated receipt there is no valuation entry to union.")
            bill_id = _create_vendor_bill(ctx, order_id, attachments)

            order = order_row(rpc, order_id, ["name", "state"])
            receipt = rpc.read("stock.picking", [receipt_id], ["state"])[0]
            bill = rpc.read("account.move", [bill_id],
                            ["state", "move_type", "amount_total"])[0]
            ctx.check("the fixture is a confirmed order with a done receipt "
                      "and a posted vendor bill",
                      {"order_state": "purchase", "receipt_state": "done",
                       "bill_state": "posted", "bill_type": "in_invoice",
                       "bill_total": UNIT_COST * ORDER_QTY},
                      {"order_state": order.get("state"),
                       "receipt_state": receipt.get("state"),
                       "bill_state": bill.get("state"),
                       "bill_type": bill.get("move_type"),
                       "bill_total": bill.get("amount_total")})

        with ctx.step("Assert the Journal Entries stat button is visible."):
            po_root = _parse_arch(form_arch(ctx, "purchase.order", "form"))
            journal_buttons = _button_nodes(po_root, JOURNAL_BUTTON)
            union = order_account_moves(rpc, order_id)
            ctx.check("the button exists with invisible=\"not "
                      "account_move_ids\" (views/purchase_order_views.xml:21), "
                      "the invisible field node that makes the modifier "
                      "evaluable is present (:17), and the union is non-empty "
                      "so the modifier resolves to visible",
                      {"button_present": True,
                       "invisible": JOURNAL_BUTTON_INVISIBLE,
                       "backing_field_node": True, "union_non_empty": True},
                      {"button_present": bool(journal_buttons),
                       "invisible": (journal_buttons[0].get("invisible")
                                     if journal_buttons else None),
                       "backing_field_node":
                           bool(_field_nodes(po_root, "account_move_ids")),
                       "union_non_empty": bool(union)})

        with ctx.step("Assert its counter equals len(order.account_move_ids)."):
            # RECORDED FINDING (plan finding 9): there is no counter to
            # compare against. The sibling paperclip button carries
            # <field name="packing_slip_receipt_count" widget="statinfo"/>
            # (views/purchase_order_views.xml:15); the Journal Entries button
            # carries only a static label in a div.o_stat_info (:22-24). The
            # union's length is therefore asserted directly.
            journal_button = journal_buttons[0] if journal_buttons else None
            journal_children = ([node.get("name")
                                 for node in journal_button.iter("field")]
                                if journal_button is not None else None)
            journal_labels = ([(node.get("class") or "").strip()
                               for node in journal_button.iter("span")]
                              if journal_button is not None else None)
            ctx.check("the Journal Entries button declares NO counter field "
                      "at all — only a static label in a div.o_stat_info "
                      "(views/purchase_order_views.xml:22-24) — so the "
                      "workbook's counter is the union's own length",
                      {"journal_button_field_nodes": [],
                       "journal_button_static_labels": ["o_stat_text"],
                       "union_length": EXPECTED_UNION_SIZE},
                      {"journal_button_field_nodes": journal_children,
                       "journal_button_static_labels": journal_labels,
                       "union_length": len(union)})
            # Recorded, not asserted: the sibling paperclip button IS a
            # statinfo counter (views/purchase_order_views.xml:15). It is
            # gated by groups="stock.group_stock_user" (:14), so whether it
            # survives into the rendered arch depends on the acting session's
            # membership — an access fact, not this case's subject.
            packing_widgets = sorted(
                {node.get("widget")
                 for button in _button_nodes(po_root, PACKING_SLIP_BUTTON)
                 for node in button.iter("field")
                 if node.get("name") == PACKING_SLIP_COUNTER})
            ctx.log(f"contrast — the paperclip button's counter widget(s) in "
                    f"the rendered arch: {packing_widgets} (expected "
                    f"['statinfo'] for a stock user, [] when "
                    f"{XMLID_GROUP_STOCK_USER} strips the button).")

        with ctx.step("Assert account_move_ids contains both the receipt's "
                      "valuation entry and the vendor bill's entry."):
            receipt_move_ids = _picking_move_ids(rpc, receipt_id)
            valuation_move_ids = _account_moves_of_moves(rpc, receipt_move_ids)
            union_ids = sorted(row["id"] for row in union)
            ctx.check("the union is exactly {receipt valuation entry} | "
                      "{vendor bill} — the two terms at "
                      "dto_purchase_stock/models/purchase_order.py:37-38",
                      sorted(set(valuation_move_ids) | {bill_id}),
                      union_ids)
            ctx.log(f"valuation entries behind the receipt's stock moves: "
                    f"{valuation_move_ids}; vendor bill: {bill_id}")

        with ctx.step("Click the button."):
            action = view_journal_entries_action(rpc, order_id)
            ctx.check("action_view_journal_entries returned an action rather "
                      "than None (purchase_order.py:63-64 returns None only "
                      "on an empty union)",
                      True, isinstance(action, dict))

        with ctx.step("Assert the action opened is "
                      "account.action_account_moves_all, domained to "
                      "account_move_ids.line_ids."):
            expected_line_ids = sorted(
                row["id"] for row in _move_lines(rpc, union_ids, ["move_id"]))
            domain = action.get("domain")
            normalised = None
            if isinstance(domain, list) and len(domain) == 1 \
                    and len(domain[0]) == 3:
                clause = list(domain[0])
                normalised = [clause[0], clause[1],
                              sorted(clause[2] or [])]
            ctx.check("the act_window is account.action_account_moves_all "
                      "(res_model account.move.line) renamed to 'Journal "
                      "Entries' and domained to the union's line ids "
                      "(purchase_order.py:66-70)",
                      {"action_id": rpc.ref(XMLID_ACTION_MOVES_ALL),
                       "type": "ir.actions.act_window",
                       "res_model": "account.move.line",
                       "name": JOURNAL_ACTION_NAME,
                       "display_name": JOURNAL_ACTION_NAME,
                       "domain": ["id", "in", expected_line_ids]},
                      {"action_id": action.get("id"),
                       "type": action.get("type"),
                       "res_model": action.get("res_model"),
                       "name": action.get("name"),
                       "display_name": action.get("display_name"),
                       "domain": normalised})

        with ctx.step("Assert the resulting list is grouped by entry."):
            search_root = _parse_arch(
                form_arch(ctx, "account.move.line", "search"))
            group_filters = [node for node in search_root.iter("filter")
                             if node.get("name") == GROUP_BY_MOVE_FILTER]
            ctx.check("the action asks for search_default_group_by_move and "
                      "the default account.move.line search view carries that "
                      "filter grouping on move_name (O17 account/views/"
                      "account_move_views.xml:359, O19 :373)",
                      {"context": JOURNAL_ACTION_CONTEXT,
                       "filter_present": True,
                       "filter_context": GROUP_BY_MOVE_CONTEXT},
                      {"context": action.get("context"),
                       "filter_present": bool(group_filters),
                       "filter_context": (group_filters[0].get("context")
                                          if group_filters else None)})
            ctx.log("recorded, not asserted: replacing the context wholesale "
                    "(purchase_order.py:71-75) DROPS the action's own "
                    "search_default_posted (O17 account/views/"
                    "account_move_views.xml:1620), so a draft entry in the "
                    "union would also be listed.")

        with ctx.step("Assert every journal item shown belongs to an entry in "
                      "account_move_ids."):
            shown = rpc.search_read("account.move.line",
                                    [("id", "in", expected_line_ids)],
                                    ["move_id"], order="id")
            outside = sorted({m2o_id(row["move_id"]) for row in shown}
                             - set(union_ids))
            ctx.check("the domain selects only journal items whose entry is "
                      "in the union",
                      {"lines": len(expected_line_ids),
                       "moves_outside_union": []},
                      {"lines": len(shown), "moves_outside_union": outside})

        with ctx.step("Assert the valuation entry debits the stock valuation "
                      "account and credits the goods-received/interim "
                      "account."):
            if len(valuation_move_ids) != 1:
                ctx.blocked(
                    f"The fixture receipt produced {len(valuation_move_ids)} "
                    f"valuation entries on {ctx.env.key}, not 1. Step 9 "
                    "reads one entry's debit and credit sides; more than one "
                    "means the target batches moves differently and the "
                    "shape has to be re-signed (the v19 delta the workbook's "
                    "step 13 anticipates).")
            move_row = rpc.read("stock.move", [receipt_move_ids[0]],
                                ["location_id"])[0]
            expected = _expected_valuation_accounts(rpc, categ_row, move_row)
            lines = _move_lines(rpc, valuation_move_ids)
            debited = sorted({m2o_id(line["account_id"]) for line in lines
                              if (line.get("debit") or 0.0) > 0.0})
            credited = sorted({m2o_id(line["account_id"]) for line in lines
                               if (line.get("credit") or 0.0) > 0.0})
            ctx.check("the incoming valuation entry debits the category's "
                      "stock valuation account and credits _get_src_account "
                      "(O17 stock_account/models/stock_move.py:392-393, "
                      ":584 feeding :401's (credit, debit) signature), and "
                      "balances",
                      {"debited": [expected["debit_account"]],
                       "credited": [expected["credit_account"]],
                       "balanced": True},
                      {"debited": debited, "credited": credited,
                       "balanced": round(
                           sum(line.get("debit") or 0.0 for line in lines)
                           - sum(line.get("credit") or 0.0 for line in lines),
                           2) == 0.0})

        with ctx.step("Assert the bill entry credits the vendor payable."):
            bill_lines = _move_lines(rpc, [bill_id])
            types = _account_types(rpc, [m2o_id(line["account_id"])
                                         for line in bill_lines])
            payable_credit = round(
                sum(line.get("credit") or 0.0 for line in bill_lines
                    if types.get(m2o_id(line["account_id"]))
                    == PAYABLE_ACCOUNT_TYPE), 2)
            payable_lines = [line for line in bill_lines
                             if types.get(m2o_id(line["account_id"]))
                             == PAYABLE_ACCOUNT_TYPE]
            ctx.check("the posted vendor bill credits a liability_payable "
                      "account for its full total "
                      "(O17 account/models/account_account.py:58)",
                      {"payable_lines": 1,
                       "payable_credit": UNIT_COST * ORDER_QTY},
                      {"payable_lines": len(payable_lines),
                       "payable_credit": payable_credit})

        with ctx.step("Add a scrap against a product from this order's "
                      "receipt and assert its entry is not pulled onto the "
                      "purchase order (that union is the picking-side compute "
                      "F080, INV/TC167)."):
            scrap_id = rpc.create("stock.scrap",
                                  {"product_id": product_id,
                                   "scrap_qty": SCRAP_QTY,
                                   "picking_id": receipt_id,
                                   "origin": tag("TC220 scrap")})
            try:
                validated = rpc.call("stock.scrap", "action_validate",
                                     [scrap_id])
            except OdooRPCError as exc:
                ctx.blocked(
                    f"The fixture scrap could not be validated on "
                    f"{ctx.env.key}: {_error_tail(exc)}. Step 11 needs a DONE "
                    "scrap carrying its own valuation entry, otherwise the "
                    "'not pulled onto the purchase order' assertion is "
                    "vacuous.")
            if isinstance(validated, dict):
                ctx.blocked(
                    "stock.scrap.action_validate returned the "
                    f"{validated.get('res_model')!r} wizard instead of "
                    f"validating on {ctx.env.key}. Step 11 needs a DONE "
                    "scrap; a wizard means the fixture stock is not where "
                    "the scrap expects it.")
            scrap_move_ids = rpc.search("stock.move",
                                        [("scrap_id", "=", scrap_id)])
            scrap_entry_ids = _account_moves_of_moves(rpc, scrap_move_ids)
            union_after = sorted(row["id"]
                                 for row in order_account_moves(rpc, order_id))
            picking_union = None
            if rpc.field_exists("stock.picking", "account_move_ids"):
                # dto_stock's own compute, read on ONE record only: it
                # dereferences self.id inside `for res in self`
                # (dto_stock/models/stock_picking.py:32), so a multi-record
                # read is the E-1 singleton defect and belongs to INV/TC168.
                try:
                    picking_union = sorted(
                        rpc.read("stock.picking", [receipt_id],
                                 ["account_move_ids"])[0]["account_move_ids"])
                except OdooRPCError as exc:
                    ctx.log(f"stock.picking.account_move_ids could not be "
                            f"read on this target: {_error_tail(exc)!r} — the "
                            f"picking-side half of the contrast is recorded "
                            f"as unobservable, not asserted.")
            # EXPECTED v17 AND v19 OUTCOME: FAIL here. The workbook's step 11
            # asserts the scrap entry is NOT pulled onto the order; the source
            # pulls it on. purchase_order.py:37 unions
            # picking_ids.move_ids.account_move_id and labels that very term
            # "# From Receipt / Scrap"; stock.scrap._prepare_move_values
            # stamps picking_id onto the scrap move (O17 stock/models/
            # stock_scrap.py:137, O19 :149) and stock.picking.move_ids is a
            # domain-less One2many (O17 stock/models/stock_picking.py:465,
            # O19 :617). Hard rule 2: the expectation is immutable, so the
            # assertion stays as the workbook words it and the FAIL is the
            # recorded baseline.
            ctx.check("the scrap produced its own journal entry, the ORDER's "
                      "union is unchanged (the workbook's step-11 "
                      "expectation; the source contradicts it — "
                      "purchase_order.py:37 unions "
                      "picking_ids.move_ids.account_move_id and its own "
                      "comment reads '# From Receipt / Scrap') and the "
                      "PICKING's union does pick it up "
                      "(dto_stock/models/stock_picking.py:32-44)",
                      {"scrap_entries": 1, "order_union": union_ids,
                       "scrap_entry_on_order": False,
                       "scrap_entry_on_picking": True},
                      {"scrap_entries": len(scrap_entry_ids),
                       "order_union": union_after,
                       "scrap_entry_on_order":
                           bool(set(scrap_entry_ids) & set(union_after)),
                       "scrap_entry_on_picking":
                           (bool(set(scrap_entry_ids) & set(picking_union))
                            if picking_union is not None else True)})
            if picking_union is None:
                ctx.log("dto_stock is not contributing stock.picking."
                        "account_move_ids on this target, so the picking-side "
                        "half of the contrast was not observable; the "
                        "order-side assertion stands on its own.")

        with ctx.step("Recompute account_move_ids over three purchase orders "
                      "as one recordset and assert no ValueError: Expected "
                      "singleton is raised (the F076 sibling of the F080 "
                      "defect asserted in INV/TC168)."):
            siblings = [make_purchase_order(
                ctx,
                [po_line_values(ctx, product_id, 1.0, PO_DATE_PLANNED,
                                price_unit=UNIT_COST)],
                partner_id=partner_id, label=f"TC220 sibling {index}")
                for index in (1, 2)]
            batch = [order_id] + siblings
            raised, message = expect_error(rpc.read, "purchase.order", batch,
                                           ["account_move_ids"])
            rows = (rpc.read("purchase.order", batch, ["account_move_ids"])
                    if not raised else [])
            ctx.check("a three-order recompute returns three rows and raises "
                      "nothing — the compute uses `res` throughout "
                      "(purchase_order.py:36-39)",
                      {"raised": False, "rows": 3},
                      {"raised": raised, "rows": len(rows)})
            if raised:
                ctx.log(f"recompute failure: {_error_tail(message)!r}")
            # A distinct, assertable fact: the ACTION has no ensure_one()
            # while it reads self.account_move_ids (purchase_order.py:62-63).
            multi_raised, multi_message = expect_error(
                rpc.call, "purchase.order", "action_view_journal_entries",
                batch)
            ctx.check("action_view_journal_entries has no ensure_one() and "
                      "therefore DOES raise on a multi-record call "
                      "(purchase_order.py:62-63)",
                      True, multi_raised)
            ctx.log(f"multi-record action failure: "
                    f"{_error_tail(multi_message)!r}")
            ctx.log("the ValueError: Expected singleton the workbook "
                    "anticipates for this compute is on the WRONG model: it "
                    "lives at dto_stock/models/stock_picking.py:32, which "
                    "searches ('picking_id', '=', self.id) inside "
                    "`for res in self`, and belongs to INV/TC167-TC168.")

        with ctx.step("Record the entry count and the entry ids as the v17 "
                      "baseline."):
            # Rule 5 forbids carrying database ids across environments, so the
            # baseline keys on account.move.NAME plus the shape of each entry;
            # the ids are recorded inside the artifact for triage only and are
            # never compared.
            payload = {
                "environment": {"key": ctx.env.key, "db": ctx.env.db,
                                "version": ctx.env.version},
                "entry_count": len(union_after),
                "entries": sorted(
                    ({"name": row.get("name"),
                      "move_type": row.get("move_type"),
                      "state": row.get("state"),
                      "journal": (row.get("journal_id") or [None, None])[-1],
                      "id": row.get("id")}
                     for row in order_account_moves(rpc, order_id)),
                    key=lambda entry: str(entry["name"])),
                "note": ("v19 batches several stock moves into ONE "
                         "account.move (O19 stock_account/models/"
                         "stock_move.py:51 and the inverse "
                         "account.move.stock_move_ids), so a LOWER v19 count "
                         "may be correct and must be signed off rather than "
                         "treated as a defect — the workbook's own step 13 "
                         "note."),
            }
            path = ctx.artifacts_dir / "tc220_journal_entry_baseline.json"
            path.write_text(json.dumps(payload, indent=1, ensure_ascii=False),
                            encoding="utf-8")
            ctx.add_artifact(path, "log",
                             "TC220 purchase-order journal entry baseline")
            ctx.log(f"baseline written: {path}")
            ctx.check("the recorded baseline carries one row per entry in the "
                      "union",
                      {"entry_count": EXPECTED_UNION_SIZE,
                       "rows": EXPECTED_UNION_SIZE},
                      {"entry_count": payload["entry_count"],
                       "rows": len(payload["entries"])})
    finally:
        # Best effort by design: a done receipt cannot be unlinked and a
        # posted account.move resists it, so the bill is reset first and the
        # rest is handed to the suite sweep. This block can never raise.
        try:
            if bill_id:
                _safe(rpc.call, "account.move", "button_draft", [bill_id])
                _safe(rpc.call, "account.move", "unlink", [bill_id])
            if attachments:
                _safe(rpc.call, "ir.attachment", "unlink", attachments)
            sweep_wf015(rpc)
            if categories:
                _safe(rpc.call, "product.category", "unlink", categories)
        except Exception:  # noqa: BLE001
            pass
