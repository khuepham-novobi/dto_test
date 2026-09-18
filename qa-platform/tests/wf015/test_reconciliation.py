"""DATAONE-WF-015 — the regroup baseline and the two read-only reconciliations:
TC205, TC032, TC047.

Abbreviations used in the citations below: ``DTO`` =
``D:/Projects/dataone/DTO-Odoo``, ``O17`` = ``D:/Projects/dataone/odoo-17.0``,
``O19`` = ``D:/Projects/odoo-19.0``.

All three cases are DATA_RECONCILIATION: capture a fact on the v17 baseline,
persist it under ``data/baselines/<tc_id>.json``, capture it again on v19 and
assert the difference is empty (``framework/fg_common.py:75-108`` over
``framework/baselines.py``). With no baseline stored, the v19 run reports
BLOCKED naming the v17 run that must happen first; without ``pg_*`` credentials
``ctx.sql`` reports BLOCKED by itself (``framework/context.py:79-90``) and never
falls back to a weaker assertion.

--------------------------------------------------------------------------
TC205 — what this file proves
--------------------------------------------------------------------------
The per-line receipt regroup engine is entirely private, but every branch of it
is driven from ONE public entry point — ``purchase.order.line.write({
'date_planned': ...})`` — and every consequence is readable off ``stock.move``,
``stock.move.line`` and ``stock.picking``. Nothing here re-implements a private
method.

The call chain, opened in the real source:

* ``DTO/project-addons/dto_purchase_stock/models/purchase_order_line.py:106-110``
  — ``write`` runs ``_check_fully_received_lines`` and then core's write;
* core ``O17 purchase_stock/models/purchase_order_line.py:96-98`` calls
  ``_update_move_date_deadline(new_date)`` BEFORE ``super().write`` (v19 the
  same at ``:103-105``);
* the DTO override ``purchase_order_line.py:74-90`` snapshots the candidate
  pool (``:78``, built by ``_get_candidate_pickings_dict_to_assign`` at
  ``:35-54``) and the per-picking deadline map (``:79-81``) BEFORE
  ``super()`` (``:82``), then re-groups each picking's moves (``:83-88``);
* core's ``_update_move_date_deadline`` (``O17 :156-162``, ``O19 :161-167``)
  writes ``date_deadline`` only onto moves ``state not in ('done','cancel')``
  — which is why a done move keeps both its deadline and its receipt;
* ``models/stock_move.py:41-66`` — ``_reassign_picking_by_date_deadline``:
  the skip filter ``:42-46`` (done/cancel, or a move whose new deadline already
  equals its picking's old one), the **relocate** branch ``:57-59`` + ``:64``,
  the **create** branch ``:60-63`` (``order._prepare_picking()`` + ``create``),
  and ``_update_picking`` ``:20-32`` which rewrites ``picking_id`` on the moves
  (``:25-27``) and their move lines (``:28-30``) and then **cancels** — never
  deletes — the receipts left with no moves (``:31-32``).

The four documented outcomes therefore map 1:1 onto four verified branches, and
the fixture builds one purchase order for each:

===== ======================================= ==================================
PO     outcome                                 branch
===== ======================================= ==================================
PO-A   relocate onto an existing receipt        ``stock_move.py:57-59`` + ``:64``
PO-B   create a new receipt                     ``stock_move.py:60-63``
PO-C   empty a receipt and cancel it            ``stock_move.py:31-32``
PO-D   leave a done move untouched              ``stock_move.py:42-46``
===== ======================================= ==================================

Two facts make the fixture legible. ``_create_stock_moves``
(``purchase_order_line.py:56-72``) **ignores** the picking core hands it and
creates a fresh receipt per line at ``:66``, so a confirmed two-line PO has two
receipts, one per deadline. And ``purchase.order.picking_ids`` is
``@api.depends('order_line.move_ids.picking_id')`` (``O17
purchase_stock/models/purchase_order.py:19``, compute ``:22-25``; ``O19 :44-47``)
— so an emptied receipt drops off it entirely, and a receipt count taken by
``search([('origin','=',name)])`` would report N+1 on v17 (core leaves its own
empty receipt behind, ``O17 :237-261``) against N on v19 (``created_receipt
.unlink()``, ``O19 :399-401``). Every count here comes from
``common.order_picking_ids``.

Two convention adaptations, both mandatory and both documented in the plan
(``docs/WF-015_AUTOMATION_PLAN.md`` adaptations 1 and 2):

1. **Identity is normalised out of the cross-version artefact.** The workbook's
   tuple carries ``move.id`` and ``picking.name``; hard rule 5 forbids relying
   on either, and step 12 already concedes the name.
   ``common.regroup_snapshot`` (``tests/wf015/common.py:1953-2027``) replaces
   both with deterministic per-run ordinals — pickings ordered by
   ``(deadline, id)``, moves by ``(line ordinal, product code, id)`` — and
   records the deadline twice, the raw stored UTC ``Datetime`` and the
   tz-localised date the engine actually groups on
   (``dto_purchase_stock/models/stock_move.py:16-18``). What survives is exactly
   the subject: which moves share a receipt, on what deadline, in what state.
   Raw ids are still used INSIDE one run — steps 7, 13 and 14 compare a move's
   receipt before and after in the same database — and never cross a version
   boundary or reach the persisted baseline.
2. **``res.users.tz`` is pinned as a snapshot.** The engine localises before
   comparing (``stock_move.py:16-18``, ``stock_picking.py:42-51``), so an
   unpinned timezone makes this case depend on whoever last logged in.
   ``common.pin_user_timezone`` records the previous value and writes
   ``America/Chicago``; ``restore_user_timezone`` puts it back in a ``finally``
   that cannot raise, and the restoration is asserted.

Deadlines are FIXED absolute dates (2030-06-03/04/05 at 12:00 UTC), never
clock-relative: hard rule 5 forbids a time-dependent expected value, and the
three dates are far from any US DST boundary, so ``12:00 UTC`` is ``07:00``
America/Chicago on the same calendar day on every run.

The one fixture record this case writes to is its own: ``common.make_picking_type``
COPIES the warehouse incoming type into a token-named one rather than flipping a
flag on the shared record (hard rule 3), and ``create_backorder`` is then set to
``'always'`` on that copy so PO-D's partial receipt produces its backorder
without a wizard (``O17 stock/models/stock_picking.py:139-145`` for the field,
``:1248-1260`` for the ``!= 'ask'`` short-circuit; ``O19 :133-139``).

--------------------------------------------------------------------------
TC032 — what this file proves
--------------------------------------------------------------------------
``purchase.order.state`` loses ``('done', 'Locked')`` on v19 (``O17
purchase/models/purchase_order.py:98-105`` → ``O19 :105-111``) and the concept
becomes the ``locked`` Boolean (``O19 :112-116``). The case asserts the
conversion per order id, the count identities, the money totals and the
``product_uom`` → ``product_uom_id`` rename (``O17
purchase/models/purchase_order_line.py:34`` → ``O19 :36``; both are plain
integer FK columns, so SQL-comparable).

**Adaptation (documented, not assertion-weakening).** The workbook's step 1
histogram and step 2 id→state map cannot be diffed raw: v17 has a ``done``
bucket and v19 does not, so a raw capture differs by construction on every
database, defect or not. Both are therefore recorded in a **normalised** form
that the conversion rule itself defines —

    v17 ``state='done'``              -> ``"purchase|locked"``
    v17 anything else                 -> ``"<state>|open"``
    v19 ``locked``                    -> ``"<state>|locked"``
    v19 not ``locked``                -> ``"<state>|open"``

— so the diff is empty **iff** the workbook's step-4 rule held for every order,
and a v19 order that ended up locked in a state other than ``purchase`` shows up
as ``"cancel|locked"`` and fails. The raw histogram and the full locked-order
dump are written as CSV/JSON artefacts, which is where the workbook's
``diff_po_state.txt`` evidence lives.

Step 8 is a static source grep, and it is the step that FAILS on v17. The
workbook says two surviving ``'done'`` expressions; there are **three**, all in
``DTO/project-addons/dto_reports/views/purchase_order.xml`` — ``:53`` and
``:62`` are ``readonly="state in ['cancel', 'done', 'purchase']"`` inside the
``purchase_order_tree`` ``ir.ui.view`` (``<field name="model">purchase.order``
at ``:45``), and ``:78`` is the ``ir.actions.act_window`` domain
``[('state','in',('purchase','done')),…]`` on ``purchase_form_action_reports``
(``<field name="res_model">purchase.order`` at ``:72``). ``dto_reports`` is
still ``17.0.0.1`` (``__manifest__.py:10``) and unported. ``dto_purchase`` is
clean: its ``purchase_order_view.xml`` hits at ``:29-43`` and ``:102`` are all
inside XML comments and its filter already reads ``['purchase']`` (``:45``),
and ``purchase_order_line.py:60`` is a **stock.move** state
(``line.move_ids.filtered(lambda x: x.state == 'done')``), correct on both
versions.

Classification is done from the source, not guessed: XML comments are blanked
(preserving line numbers) and each surviving ``'done'`` line is attributed to
the enclosing ``<record>``'s declared ``model`` / ``res_model`` field, so the
assertion is general — a new ``purchase.order`` record anywhere in either module
is caught. The Python half cannot be attributed that way, so the **files** that
carry a non-test ``'done'`` literal are pinned against the two verified-benign
ones; a third file fails the check and must be classified by a human.

--------------------------------------------------------------------------
TC047 — what this file proves
--------------------------------------------------------------------------
Read-only aggregates over ``ir_attachment``, plus the filestore existence sweep.
Every column used exists identically on both versions:
``res_model`` (``O17 base/models/ir_attachment.py:410`` / ``O19 :456``),
``res_field`` (``:411`` / ``:457``), ``type`` (``:416`` / ``:461``),
``db_datas`` (``:428`` / ``:473``), ``store_fname`` (``:429`` / ``:474``),
``file_size`` (``:430`` / ``:475``), ``checksum`` (``:431`` / ``:476``).

**CORRECTION TO THIS SUITE'S OWN PREMISE, made from source and recorded rather
than worked around.** ``tests/wf015/common.py`` (module docstring) and
``reports/data/wf015_feasibility.json`` (key finding 4) both state that
``stock.picking.packing_slip_attachment`` is "a column on ``stock_picking``,
not an ``ir.attachment``", and conclude that F069 is invisible to this case's
queries. That is not what the source says. ``fields.Binary`` defaults to
``attachment=True`` — ``O17 odoo/fields.py:2334-2344`` ("whether the field
should be stored as ``ir_attachment`` … default: ``True``") and ``O19
odoo/orm/fields_binary.py:39`` — and
``DTO/project-addons/dto_purchase_stock/models/stock_picking.py:14-16``
declares ``packing_slip_attachment = fields.Binary(string='Packing Slip
Attachment')`` with **no** ``attachment=False`` and no ``store=False``. So each
stored value IS an ``ir_attachment`` row carrying ``res_model='stock.picking'``,
``res_field='packing_slip_attachment'``, ``res_id=<picking id>`` and
``type='binary'`` (``O17 odoo/fields.py:2461-2473``, read path ``:2442-2456``;
``O19 odoo/orm/fields_binary.py:174`` and ``:154``). The workbook's step 6
"receipt packing slips" count under ``res_model='stock.picking'`` therefore does
include them, and this file adds an explicit ``res_field`` sub-count so F069's
own rows are visible in the baseline instead of being buried in the chatter
total. The workbook's expectations are implemented unchanged; only the claim
that the query is blind to F069 is corrected. ``tests/wf015/common.py`` is
another agent's file and is not edited.

Step 5 is the only step in the suite that touches the filesystem. The Odoo
``data_dir`` is not part of ``config/environments.yaml``, so it is resolved from
``DTO_FILESTORE_ROOT_<version>`` / ``DTO_FILESTORE_ROOT`` and then from the
documented defaults — on this workstation ``dto.conf`` sets
``data_dir = %LOCALAPPDATA%\\OpenERP S.A\\Odoo`` and the store is at
``<data_dir>/filestore/<db>``. When none of the candidates exists the step
reports BLOCKED naming every path it tried; it never downgrades to "the
database says the rows are there", which is exactly the failure the case
exists to catch.

--------------------------------------------------------------------------
Expected outcomes
--------------------------------------------------------------------------
* ``TEST-WF015-TC205`` — **EXPECTED v17 OUTCOME: PASS**, baseline captured,
  checksummed and persisted. EXPECTED v19 OUTCOME: BLOCKED by the runner
  preflight while no v19 instance exists; once one exists, step 4 raises
  ``AttributeError: 'purchase.order.line' object has no attribute
  'product_uom'`` from ``dto_purchase_stock/models/purchase_order_line.py:102``
  until that guard is ported to ``product_uom_id``, and only after that is the
  regroup engine itself comparable.
* ``TEST-WF015-TC032`` — **EXPECTED v17 OUTCOME: FAIL at step 8** — three live
  ``purchase.order`` ``'done'`` expressions survive in
  ``dto_reports/views/purchase_order.xml:53,62,78``. The expectation describes
  the v19 target state, so hard rule 2 keeps it failing. Steps 1-7 PASS and the
  baseline is persisted **before** step 8 runs, so the v17 capture is not lost
  to the failure. EXPECTED v19 OUTCOME: PASS once ``dto_reports`` is ported to
  ``locked``.
* ``TEST-WF015-TC047`` — **EXPECTED v17 OUTCOME: PASS**, baseline captured;
  BLOCKED instead when the filestore directory cannot be resolved, naming every
  candidate path. EXPECTED v19 OUTCOME: BLOCKED until a v19 instance and its
  filestore exist.

Safety: TC032 and TC047 create nothing and are read-only throughout. TC205
creates only token-namespaced fixtures (``common.fixture_token()``), writes to
no pre-existing business record beyond the snapshot-and-restore of
``res.users.tz``, and sweeps in a ``finally`` that can never raise. Nothing here
calls a cron, a mail server or PrintNode.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

from framework.baselines import diff_counts, load_baseline
from framework.fg_common import reconcile
from framework.registry import test_case
from framework.source_scan import module_path
from tests.wf015.common import (MARKER, PO_DONE_SCAN_MODULES,  # noqa: F401
                                PO_DONE_SCAN_PATTERN, PINNED_TZ, WORKFLOW,
                                WORKFLOW_NAME, assign_picking,
                                cancelled_empty_pickings,
                                confirm_purchase_order, ensure_vendor,
                                grep_dto, is_backorder_action, m2o_id,
                                make_picking_type, make_product,
                                make_purchase_order, moves_of_order,
                                open_namespace, order_line_rows,
                                order_picking_ids,
                                pin_user_timezone, po_line_values,
                                process_backorder, regroup_snapshot,
                                repromise_line, require_dto_purchase_stock,
                                require_source_root, restore_user_timezone,
                                set_move_quantity, sweep_wf015, trace,
                                user_timezone, validate_picking)

TC205 = "DATAONE-TC205"
TC032 = "DATAONE-TC032"
TC047 = "DATAONE-TC047"

# ===========================================================================
# TC205 fixture constants
# ===========================================================================
#: Fixed absolute deadlines. Hard rule 5 forbids a clock-relative expected
#: value, and the regroup engine groups on the tz-LOCALISED date
#: (dto_purchase_stock/models/stock_move.py:16-18), so the three instants are
#: chosen far from any US DST boundary: 12:00 UTC is 07:00 America/Chicago on
#: the same calendar day, on every run and in both directions.
D1 = "2030-06-03 12:00:00"
D2 = "2030-06-04 12:00:00"
D3 = "2030-06-05 12:00:00"

#: label -> [(product label, quantity, date_planned)] — four purchase orders,
#: one per documented outcome (see the module docstring's table).
FIXTURE_ORDERS = (
    ("PO-A", (("P-A1", 4.0, D1), ("P-A2", 6.0, D2))),
    ("PO-B", (("P-B1", 4.0, D1), ("P-B2", 6.0, D2))),
    ("PO-C", (("P-C1", 4.0, D1),)),
    ("PO-D", (("P-D1", 5.0, D1),)),
)

#: PO-D's partial receipt: 3 of 5, leaving a done move and a backorder move on
#: the SAME purchase.order.line. qty_received (3) != product_qty (5), so
#: _check_fully_received_lines (purchase_order_line.py:92-104) does not fire
#: and the line can still be re-promised.
PO_D_RECEIVED_QTY = 3.0

#: Step 4's scripted sequence, in a FIXED order: (PO label, line index, new
#: date). PO-A moves onto PO-A's own D2 receipt (relocate); PO-B moves to an
#: unmatched date (create); PO-C is single-line, so its only receipt is emptied
#: and cancelled; PO-D re-promises the line that still carries a done move.
REPROMISE_SEQUENCE = (
    ("PO-A", 0, D2),
    ("PO-B", 0, D3),
    ("PO-C", 0, D2),
    ("PO-D", 0, D2),
)


# ===========================================================================
# Local helpers — none of these exists in tests/wf015/common.py
# ===========================================================================
def _move_map(rows) -> dict:
    """``{move id: {'line', 'picking', 'state', 'deadline'}}``.

    Built from ``common.moves_of_order``, which reads through
    ``purchase_line_id`` rather than through the pickings, so a move that has
    just been relocated onto a brand-new receipt is still in the set. Raw ids
    are used ONLY inside one run (steps 7, 13 and 14 compare a move's receipt
    before and after in the same database); nothing here reaches the persisted
    baseline, where ``common.regroup_snapshot``'s ordinals are what cross the
    version boundary.
    """
    return {row["id"]: {"line": m2o_id(row.get("purchase_line_id")),
                        "picking": m2o_id(row.get("picking_id")),
                        "state": row.get("state"),
                        "deadline": row.get("date_deadline") or ""}
            for row in rows}


def _line_moves(move_map: dict, line_id: int) -> dict:
    """The subset of ``_move_map`` belonging to one purchase order line."""
    return {mid: info for mid, info in move_map.items()
            if info["line"] == line_id}


def _digest(payload) -> str:
    """SHA-256 over the canonical JSON form — the workbook's "checksummed"."""
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False,
                      default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _json_artifact(ctx, filename: str, payload, label: str) -> Path:
    """Write a JSON evidence file into this execution's artifacts folder."""
    path = ctx.artifacts_dir / filename
    path.write_text(json.dumps(payload, indent=1, ensure_ascii=False,
                               default=str), encoding="utf-8")
    ctx.add_artifact(path, "log", label)
    return path


#: XML comments, blanked rather than removed so line numbers survive.
_XML_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
#: One <record> element. Verified: neither dto_reports nor dto_purchase uses a
#: self-closing <record/>, so a non-greedy match cannot swallow a sibling.
_XML_RECORD_RE = re.compile(r"<record\b[^>]*>.*?</record>", re.S)
#: ir.ui.view declares its model in <field name="model">; ir.actions.act_window
#: in <field name="res_model"> (dto_reports/views/purchase_order.xml:45 and
#: :72 respectively).
_XML_MODEL_FIELD_RE = re.compile(
    r'<field\s+name="(?:model|res_model)"[^>]*>\s*([^<\s][^<]*?)\s*</field>')


def _blank_xml_comments(text: str) -> str:
    """Replace every XML comment with spaces, keeping the line numbering."""
    return _XML_COMMENT_RE.sub(
        lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)


def _xml_record_models(text: str) -> list:
    """``[(first line, last line, declared model or None)]`` per <record>."""
    records = []
    for match in _XML_RECORD_RE.finditer(text):
        first = text.count("\n", 0, match.start()) + 1
        last = text.count("\n", 0, match.end()) + 1
        found = _XML_MODEL_FIELD_RE.search(match.group(0))
        records.append((first, last, found.group(1) if found else None))
    return records


def _model_at(records: list, line: int):
    """The declared model of the <record> containing ``line``, or None."""
    for first, last, model in records:
        if first <= line <= last:
            return model
    return None


def _scan_xml_done_hits(root, modules, pattern: str) -> dict:
    """Attribute every live XML ``'done'`` literal to its record's model.

    Returns ``{'hits': [...], 'unresolved': [...]}``. A hit is *live* when it
    survives comment blanking; it is *unresolved* when no enclosing ``<record>``
    declares a model, which would let a real expression hide, so the caller
    asserts that list is empty too.
    """
    rx = re.compile(pattern)
    hits, unresolved = [], []
    for module in modules:
        base = module_path(root, module)
        if base is None:
            continue
        for path in sorted(base.rglob("*.xml")):
            as_posix = str(path).replace("\\", "/")
            if "/i18n/" in as_posix or "/static/description/" in as_posix:
                continue
            try:
                raw = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            text = _blank_xml_comments(raw)
            records = _xml_record_models(text)
            relative = str(path.relative_to(base)).replace("\\", "/")
            for number, line in enumerate(text.splitlines(), start=1):
                if not rx.search(line):
                    continue
                model = _model_at(records, number)
                entry = {"module": module, "file": relative, "line": number,
                         "model": model, "text": line.strip()[:200]}
                (hits if model else unresolved).append(entry)
    return {"hits": hits, "unresolved": unresolved}


#: The only two non-test Python files in dto_reports / dto_purchase that carry
#: a ``'done'`` literal, with the model each one is really about — both read in
#: full before this constant was written. A Python literal cannot be attributed
#: to a model the way an XML record can, so the FILE SET is pinned instead: a
#: third file fails the check loudly and has to be classified by a human, which
#: is stricter than the workbook's grep, never weaker.
VERIFIED_BENIGN_PY_DONE_FILES = {
    "dto_reports/models/product_template.py":
        "mrp.production — :21 is inside self.env['mrp.production'].search("
        "[('state','=','done'), ...]) in _compute_average_manufacture_time",
    "dto_purchase/models/purchase_order_line.py":
        "stock.move — :60 is line.move_ids.filtered(lambda x: x.state == "
        "'done'), a move state that is correct on both versions",
}


def _python_done_files(scan: dict) -> dict:
    """``{'<module>/<relpath>': [line numbers]}`` for non-test .py hits.

    ``tests/`` is excluded because test code quotes the old literal on purpose
    (``dto_purchase/tests/test_wf014_open_flags.py:438`` asserts
    ``assertNotIn("'done'", arch)``); a ``#`` comment is excluded the same way
    an XML comment is.
    """
    found: dict = {}
    for module, hits in sorted(scan.items()):
        for hit in (hits or []):
            name = hit["file"]
            if not name.endswith(".py"):
                continue
            if name.startswith("tests/") or "/tests/" in name:
                continue
            if hit["text"].lstrip().startswith("#"):
                continue
            found.setdefault(f"{module}/{name}", []).append(hit["line"])
    return found


#: Odoo data_dir overrides, most specific first. ``{version}`` is filled from
#: ``ctx.env.version`` the way ``framework/source_scan.py:53-57`` resolves
#: ``DTO_SOURCE_ROOT_<version>``.
FILESTORE_ENV_KEYS = ("DTO_FILESTORE_ROOT_{version}", "DTO_FILESTORE_ROOT")


def _data_dir_candidates(ctx) -> list:
    """Every Odoo ``data_dir`` this workstation might be using.

    The platform has no filestore setting (``backend/config.py:55-68`` carries
    only URLs, database names and ``pg_*``), so the candidates are the two
    environment overrides followed by the documented defaults —
    ``%LOCALAPPDATA%\\OpenERP S.A\\Odoo`` is what ``D:\\Projects\\dataone\\
    dto.conf`` sets ``data_dir`` to on this machine, the next two are Odoo's
    own platform defaults, and ``/var/lib/odoo`` is the path the workbook's
    own step 5 shell snippet uses.
    """
    candidates = []
    for template in FILESTORE_ENV_KEYS:
        value = os.environ.get(template.format(version=ctx.env.version))
        if value:
            candidates.append(Path(value))
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidates.append(Path(local_app_data) / "OpenERP S.A" / "Odoo")
        candidates.append(Path(local_app_data) / "Odoo")
    candidates.append(Path.home() / ".local" / "share" / "Odoo")
    candidates.append(Path("/var/lib/odoo"))
    return candidates


def _filestore_dir(ctx):
    """``<data_dir>/filestore/<db>``, or None when nothing resolves.

    An override may also point straight at the database's own store, so a
    candidate whose last path segment already is the database name is accepted
    as-is.
    """
    for base in _data_dir_candidates(ctx):
        store = base / "filestore" / ctx.env.db
        if store.is_dir():
            return store
        if base.name == ctx.env.db and base.is_dir():
            return base
    return None


def _scalar(value):
    """Normalise a psycopg2 scalar so the JSON baseline round-trips."""
    if value is None:
        return None
    if isinstance(value, (int, str, bool)):
        return value
    return float(value) if isinstance(value, float) else str(value)


# ===========================================================================
# TC205 — the normalised regroup baseline
# ===========================================================================
def _build_fixture(ctx, picking_type_id: int, partner_id: int) -> dict:
    """The four purchase orders the workbook's precondition requires.

    Byte-identical on both environments by construction: the same labels, the
    same quantities and the same three fixed deadlines, all namespaced with
    this execution's token.
    """
    rpc = ctx.adapter.rpc
    fixture: dict = {}
    for label, lines in FIXTURE_ORDERS:
        values = []
        for product_label, quantity, planned in lines:
            product_id = make_product(ctx, product_label)
            values.append(po_line_values(ctx, product_id, quantity, planned))
        order_id = make_purchase_order(ctx, values, partner_id=partner_id,
                                       picking_type_id=picking_type_id,
                                       label=label)
        confirm_purchase_order(rpc, order_id)
        line_rows = order_line_rows(rpc, order_id, ["product_id",
                                                   "product_qty"])
        fixture[label] = {"order_id": order_id,
                          "line_ids": [row["id"] for row in line_rows]}
    return fixture


def _receive_partially(ctx, order_id: int, quantity: float):
    """Receive part of PO-D's only line so the line keeps a DONE move.

    ``button_validate`` is public on both versions. With the fixture operation
    type's ``create_backorder='always'`` the backorder is generated without a
    wizard (``O17 stock/models/stock_picking.py:1248-1252`` skips a picking
    whose type is not ``'ask'``), so the call returns ``True``; the
    ``stock.backorder.confirmation`` act_window is still handled, and any OTHER
    returned action reports BLOCKED naming it rather than failing the case for
    an unrelated reason.
    """
    rpc = ctx.adapter.rpc
    picking_ids = order_picking_ids(rpc, order_id)
    if len(picking_ids) != 1:
        ctx.blocked(
            f"PO-D was expected to confirm into exactly one receipt "
            f"(dto_purchase_stock/models/purchase_order_line.py:66 creates one "
            f"picking per line and the order has a single line), but "
            f"order.picking_ids holds {len(picking_ids)} on {ctx.env.key}.")
    picking_id = picking_ids[0]
    assign_picking(rpc, picking_id)
    moves = rpc.search_read("stock.move", [("picking_id", "=", picking_id)],
                            ["product_uom_qty"], order="id")
    set_move_quantity(rpc, moves[0]["id"], quantity)
    action = validate_picking(rpc, picking_id)
    if is_backorder_action(action):
        process_backorder(rpc, picking_id)
    elif isinstance(action, dict):
        ctx.blocked(
            "button_validate on PO-D's receipt returned "
            f"{action.get('res_model') or action.get('tag')!r} instead of "
            f"completing on {ctx.env.key}. The fixture needs a partially "
            "received receipt so the line keeps one done move "
            "(dto_purchase_stock/models/stock_move.py:42-46 is the branch "
            "under test); an intervening wizard — a quality check, a lot "
            "request — makes that unreachable here.")
    return picking_id


@test_case(
    id="TEST-WF015-TC205",
    name="Capture the v17 (picking, deadline, move) regroup baseline and "
         "replay it unchanged on v19",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_purchase_stock",
    priority="P0", kind="DATA", order=15205,
    description="Builds four purchase orders covering the four documented "
                "regroup outcomes, records the (picking, deadline, move) set "
                "before and after a fixed sequence of Expected-Arrival "
                "changes, checksums it, asserts the four outcomes and the "
                "done-move invariant, and diffs the whole set against the "
                "persisted v17 baseline.",
    traceability=trace("DATAONE-TC205"))
def test_tc205(ctx):
    require_dto_purchase_stock(ctx)
    rpc = ctx.adapter.rpc
    open_namespace(ctx)

    uid, previous_tz, tz_pinned = None, None, False
    snapshot: dict = {}
    evidence: dict = {"tc_id": TC205, "env": ctx.env.key, "db": ctx.env.db}
    fixture: dict = {}
    try:
        with ctx.step("1. On the v17 clone, run the fixture script."):
            # Adaptation 2: the engine groups on the deadline localised into
            # the ACTING USER's timezone (stock_move.py:16-18), so the tz is
            # snapshotted and pinned before anything is created.
            uid, previous_tz = pin_user_timezone(ctx)
            tz_pinned = True
            ctx.check("the acting user's timezone is pinned", PINNED_TZ,
                      user_timezone(rpc, uid))

            # Hard rule 3: the warehouse's own operation type is never
            # touched. make_picking_type COPIES it into a token-named one; the
            # copy is this suite's own record, so create_backorder is set on
            # it to make PO-D's backorder wizard-free and deterministic.
            picking_type_id = make_picking_type(rpc, label="IN-TC205")
            rpc.write("stock.picking.type", [picking_type_id],
                      {"create_backorder": "always"})
            partner_id = ensure_vendor(rpc, "TC205")

            fixture = _build_fixture(ctx, picking_type_id, partner_id)
            fixture["PO-D"]["done_picking_id"] = _receive_partially(
                ctx, fixture["PO-D"]["order_id"], PO_D_RECEIVED_QTY)

            shape = {label: len(order_picking_ids(rpc, data["order_id"]))
                     for label, data in sorted(fixture.items())}
            # PO-A and PO-B have two lines and therefore two receipts
            # (purchase_order_line.py:66 creates one picking per line); PO-C
            # has one; PO-D has two because the partial receipt left a done
            # receipt plus its backorder.
            ctx.check("the fixture confirmed into the expected receipt counts",
                      {"PO-A": 2, "PO-B": 2, "PO-C": 1, "PO-D": 2}, shape)

            done_moves = [m for m in moves_of_order(
                rpc, fixture["PO-D"]["order_id"]) if m.get("state") == "done"]
            ctx.check_true(
                "PO-D's line carries exactly one done move, so the skip "
                "filter at dto_purchase_stock/models/stock_move.py:42-46 is "
                "actually exercised", len(done_moves) == 1,
                actual_desc=f"{len(done_moves)} done move(s)")
            evidence["fixture"] = {
                label: {k: v for k, v in data.items()}
                for label, data in sorted(fixture.items())}

        with ctx.step("2. For every PO in the fixture, record pre = sorted("
                      "(m.picking_id.name, str(m.picking_id.date_deadline), "
                      "m.id, m.state) for m in order.order_line.move_ids)."):
            for label, data in sorted(fixture.items()):
                order_id = data["order_id"]
                pre = regroup_snapshot(ctx, order_id)
                data["pre_picking_ids"] = order_picking_ids(rpc, order_id)
                data["pre_moves"] = _move_map(moves_of_order(rpc, order_id))
                snapshot[f"{label}/pre/moves"] = pre["moves"]
                snapshot[f"{label}/pre/move_count"] = pre["move_count"]
                ctx.log(f"{label} pre moves: {pre['moves']!r}")
            snapshot["tz"] = user_timezone(rpc, uid)

        with ctx.step("3. Also record pre_pickings = sorted((p.name, str("
                      "p.date_deadline), p.state, len(p.move_ids)) for p in "
                      "order.picking_ids)."):
            for label, data in sorted(fixture.items()):
                pre = regroup_snapshot(ctx, data["order_id"])
                snapshot[f"{label}/pre/pickings"] = pre["pickings"]
                snapshot[f"{label}/pre/picking_count"] = pre["picking_count"]
                ctx.log(f"{label} pre pickings: {pre['pickings']!r}")

        with ctx.step("4. Apply the scripted sequence of Expected-Arrival "
                      "changes, in a fixed order, one save per change."):
            applied = []
            for label, index, new_date in REPROMISE_SEQUENCE:
                line_id = fixture[label]["line_ids"][index]
                # ONE write per change: purchase.order.line.write is the
                # public entry point for the whole private chain
                # (purchase_order_line.py:106-110 -> core :96-98 -> the DTO
                # override at :74-90), and each RPC call is its own
                # transaction.
                repromise_line(rpc, line_id, new_date)
                applied.append({"order": label, "line_id": line_id,
                                "new_date": new_date})
                ctx.log(f"{label} line#{index + 1} date_planned -> {new_date}")
            evidence["repromise_sequence"] = applied
            ctx.check("every scripted change was saved, in order",
                      len(REPROMISE_SEQUENCE), len(applied))

        with ctx.step("5. Record post and post_pickings in the same shape."):
            for label, data in sorted(fixture.items()):
                order_id = data["order_id"]
                post = regroup_snapshot(ctx, order_id)
                data["post_picking_ids"] = order_picking_ids(rpc, order_id)
                data["post_moves"] = _move_map(moves_of_order(rpc, order_id))
                snapshot[f"{label}/post/moves"] = post["moves"]
                snapshot[f"{label}/post/move_count"] = post["move_count"]
                snapshot[f"{label}/post/pickings"] = post["pickings"]
                snapshot[f"{label}/post/picking_count"] = post["picking_count"]
                # The emptied receipt is CANCELLED, not deleted
                # (stock_move.py:31-32), and because picking_ids is
                # order_line.move_ids.picking_id it then drops off the order —
                # so it is counted over the UNION of the pre and post ids,
                # never off picking_ids, or step 13 would always read zero.
                union = sorted(set(data["pre_picking_ids"])
                               | set(data["post_picking_ids"]))
                data["cancelled_empty"] = [
                    p["id"] for p in cancelled_empty_pickings(rpc, union)]
                snapshot[f"{label}/cancelled_empty_receipts"] = len(
                    data["cancelled_empty"])
                ctx.log(f"{label} post moves: {post['moves']!r}")
                ctx.log(f"{label} post pickings: {post['pickings']!r}")

        with ctx.step("Adaptation 2 — restore the res.users.tz snapshot now "
                      "that every deadline-sensitive reading is taken, and "
                      "assert the restoration (hard rule 3)."):
            restored = restore_user_timezone(rpc, uid, previous_tz)
            tz_pinned = not restored
            ctx.check("res.users.tz put back exactly as it was",
                      previous_tz or False, user_timezone(rpc, uid))

        with ctx.step("6. Serialise pre, pre_pickings, post, post_pickings to "
                      "a checksummed artefact stored with the Phase-0a "
                      "baseline set."):
            payload = {k: v for k, v in sorted(snapshot.items())}
            digest = _digest(payload)
            snapshot["artefact/sha256"] = digest
            evidence["snapshot"] = payload
            evidence["sha256"] = digest
            path = _json_artifact(ctx, "tc205_regroup_baseline.json", evidence,
                                  "TC205 (picking, deadline, move) capture")
            ctx.log(f"sha256={digest} -> {path}")
            # reconcile persists the same dict under data/baselines/ — the
            # Phase-0a baseline set — so the artefact and the baseline are the
            # same bytes plus this digest.
            ctx.check_true("a non-empty capture was serialised",
                           bool(payload), actual_desc=f"{len(payload)} key(s)")

        with ctx.step("7. Assert the v17 post set matches the four documented "
                      "outcomes: at least one move relocated to an existing "
                      "deadline-matching receipt, at least one new receipt "
                      "created, at least one receipt in cancel with zero "
                      "moves, and every done move on an identical (picking, "
                      "move) pair in pre and post."):
            # ONE mismatch dict, not four assertions: a failure names every
            # outcome that did not happen.
            outcomes = {}

            a = fixture["PO-A"]
            a_line = a["line_ids"][0]
            a_pre = _line_moves(a["pre_moves"], a_line)
            a_post = _line_moves(a["post_moves"], a_line)
            outcomes["PO-A relocated onto a receipt that already existed"] = (
                bool(a_post) and all(
                    a_post[mid]["picking"] != a_pre.get(mid, {}).get("picking")
                    and a_post[mid]["picking"] in a["pre_picking_ids"]
                    for mid in a_post))

            b = fixture["PO-B"]
            b_line = b["line_ids"][0]
            b_post = _line_moves(b["post_moves"], b_line)
            outcomes["PO-B created a receipt that did not exist before"] = (
                bool(b_post) and all(
                    b_post[mid]["picking"] not in b["pre_picking_ids"]
                    for mid in b_post))

            outcomes["PO-C left a receipt in cancel with zero moves"] = bool(
                fixture["PO-C"]["cancelled_empty"])

            kept = {}
            for label, data in sorted(fixture.items()):
                for mid, info in data["pre_moves"].items():
                    if info["state"] not in ("done", "cancel"):
                        continue
                    after = data["post_moves"].get(mid)
                    if after is None or after["picking"] != info["picking"]:
                        kept[f"{label}/move{mid}"] = {
                            "pre": info, "post": after}
            outcomes["every done or cancel move kept its (picking, move) "
                     "pair"] = not kept
            evidence["done_move_drift"] = kept

            ctx.check("the four documented regroup outcomes",
                      {key: True for key in outcomes}, outcomes)

        with ctx.step("8. On the v19 target, run the identical fixture "
                      "script."):
            # The fixture script IS the code above: the same module, the same
            # labels, the same quantities and the same three fixed deadlines
            # run on whichever target this execution is pointed at, so there is
            # no second script to drift from the first. What step 9 needs is
            # proof that the starting state was the same shape on both sides,
            # and that is exactly what the pre/* keys of the persisted baseline
            # carry.
            ctx.log(f"this execution ran the fixture on {ctx.env.key} "
                    f"(db={ctx.env.db}, Odoo {ctx.env.version})")
            pre_keys = sorted(k for k in snapshot if "/pre/" in k)
            ctx.check("the starting state is captured for all four purchase "
                      "orders", 4 * 4, len(pre_keys))

        with ctx.step("13. Assert the count of receipts left in cancel is "
                      "identical."):
            per_order = {label: len(data["cancelled_empty"])
                         for label, data in sorted(fixture.items())}
            ctx.log(f"receipts left in cancel with zero moves: {per_order!r}")
            snapshot["cancelled_empty_receipts/TOTAL"] = sum(per_order.values())
            # The cross-version identity is the diff of these keys; what is
            # assertable inside one run is that the outcome happened at all —
            # a zero here would make the diff vacuous on both sides.
            ctx.check_true(
                "at least one receipt was emptied and cancelled, so the "
                "count being diffed is not vacuous",
                sum(per_order.values()) > 0, actual_desc=repr(per_order))

        with ctx.step("14. Assert no move that was done or cancel in pre "
                      "changed picking in either environment."):
            drift = evidence.get("done_move_drift") or {}
            ctx.check("moves that were done or cancel before the re-promise "
                      "and changed receipt after it", {}, drift)

        with ctx.step("15. On any difference, record the exact tuple pairs "
                      "that diverged in findings/ — that list is the defect "
                      "report."):
            base = load_baseline(TC205)
            diffs = (diff_counts(base["data"], snapshot) if base else [])
            _json_artifact(
                ctx, "tc205_regroup_divergence.json",
                {"tc_id": TC205, "env": ctx.env.key, "db": ctx.env.db,
                 "baseline_present": bool(base),
                 "baseline_captured_on": (base or {}).get("captured_env"),
                 "diverged": diffs},
                "TC205 divergence against the v17 baseline")
            ctx.log(f"{len(diffs)} diverging key(s) recorded "
                    f"(baseline_present={bool(base)})")

        # Steps 9-12: reconcile persists on v17 and diffs on v19, so
        # pre_v19 == pre_v17 and post_v19 == post_v17 are the same assertion
        # over the pre/* and post/* keys of one snapshot.
        reconcile(ctx, TC205, lambda _ctx, _snap=snapshot: _snap)
    finally:
        if tz_pinned and uid is not None:
            restore_user_timezone(rpc, uid, previous_tz)
        try:
            sweep_wf015(rpc)
        except Exception:  # noqa: BLE001 — teardown must never raise
            pass


# ===========================================================================
# TC032 — purchase.order 'done' -> locked
# ===========================================================================
#: Every normalised value the conversion rule allows. A v19 order that ended up
#: locked in any state other than 'purchase' produces something outside this
#: set and is caught by step 4.
ALLOWED_PO_STATES = (
    "draft|open", "sent|open", "to approve|open", "purchase|open",
    "purchase|locked", "cancel|open",
)


def _normalise_po_state(state, locked, has_locked_column) -> str:
    """The workbook's step-4 conversion rule, expressed as one value.

    v17 ``'done'`` and v19 ``locked`` must normalise to the SAME string, or the
    baseline and the target can never be compared: ``purchase.order.state``
    loses ``('done','Locked')`` on v19 (``O17
    purchase/models/purchase_order.py:98-105`` -> ``O19 :105-111``) and gains
    ``locked`` (``O19 :112-116``).
    """
    if has_locked_column:
        return f"{state}|{'locked' if locked else 'open'}"
    return "purchase|locked" if state == "done" else f"{state}|open"


@test_case(
    id="TEST-WF015-TC032",
    name="purchase.order records in state 'done' land correctly on locked",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_purchase, dto_purchase_stock",
    priority="P1", kind="DATA", order=15032,
    description="Captures the whole purchase.order id->state map in the "
                "conversion rule's own normalised form, plus the count "
                "identities, the money totals and the product_uom -> "
                "product_uom_id carry count, and asserts no purchase.order "
                "'done' expression survives in dto_reports or dto_purchase.",
    traceability=trace("DATAONE-TC032"))
def test_tc032(ctx):
    sql = ctx.sql                      # BLOCKS by itself without pg_* config
    snapshot: dict = {}
    evidence: dict = {"tc_id": TC032, "env": ctx.env.key, "db": ctx.env.db}

    with ctx.step("Precondition: the purchase tables and the columns this "
                  "case reads exist on this target"):
        missing = [f"{table}.{column}" for table, column in (
            ("purchase_order", "id"), ("purchase_order", "name"),
            ("purchase_order", "state"), ("purchase_order", "date_order"),
            ("purchase_order", "partner_id"),
            ("purchase_order", "amount_total"),
            ("purchase_order", "amount_untaxed"),
            ("purchase_order_line", "id"))
            if not sql.column_exists(table, column)]
        if missing:
            ctx.blocked(
                f"These columns do not exist on {ctx.env.key} "
                f"(db={ctx.env.db}): {', '.join(missing)}. TC032 measures the "
                "purchase-order population directly in PostgreSQL and has "
                "nothing to capture without them.")
        has_locked = sql.column_exists("purchase_order", "locked")
        uom_column = ("product_uom_id"
                      if sql.column_exists("purchase_order_line",
                                           "product_uom_id")
                      else "product_uom")
        evidence["shape"] = {"locked_column": has_locked,
                             "uom_column": uom_column}
        # This case's SUBJECT is the version delta, which is the one place
        # AUTOMATION_CONVENTIONS allows a test to read ctx.env.version to
        # compute its own expectation. The shape is PROBED from the schema and
        # only the expectation is version-derived.
        ctx.check("the schema shape matches the target's Odoo version",
                  {"locked_column": ctx.env.version == "19",
                   "uom_column": ("product_uom_id" if ctx.env.version == "19"
                                  else "product_uom")},
                  evidence["shape"])

    with ctx.step("1. v17 capture — the exact id set and the state "
                  "distribution."):
        raw_histogram = {str(state): int(count) for state, count in sql.rows(
            "SELECT state, count(*) FROM purchase_order GROUP BY 1 ORDER BY 1")}
        evidence["raw_state_histogram"] = raw_histogram
        ctx.log(f"raw purchase_order state histogram: {raw_histogram!r}")

        # The workbook's second query, as an artefact: it dumps the orders the
        # conversion has to carry, which on v17 is state='done' and on v19 is
        # locked. Ids are the join key the workbook's own step 4 uses, and this
        # is the same database upgraded in place.
        if has_locked:
            dump_sql = ("SELECT id, name, state, locked, date_order, "
                        "partner_id, round(amount_total::numeric,2) AS "
                        "amount_total FROM purchase_order WHERE locked "
                        "ORDER BY id")
        else:
            dump_sql = ("SELECT id, name, state, date_order, partner_id, "
                        "round(amount_total::numeric,2) AS amount_total "
                        "FROM purchase_order WHERE state = 'done' ORDER BY id")
        dump_path = ctx.artifacts_dir / "tc032_locked_orders.csv"
        dumped = sql.to_csv(dump_sql, dump_path)
        ctx.add_artifact(dump_path, "log",
                         "TC032 orders carrying the locked concept")
        ctx.log(f"{dumped} order(s) carry the locked concept -> {dump_path}")

        # The workbook's own precondition: a zero count downgrades the case to
        # N/A with evidence rather than asserting a vacuous identity.
        if dumped == 0:
            predicate = "locked = TRUE" if has_locked else "state = 'done'"
            ctx.skip(
                f"{ctx.env.key} (db={ctx.env.db}) holds zero purchase orders "
                f"carrying the locked concept ({predicate}); "
                f"the raw histogram is {raw_histogram!r}. The workbook's own "
                "precondition downgrades TC032 to N/A in that case — there is "
                "no closed history to convert, so every identity below would "
                "be vacuously true. Evidence is in "
                f"{dump_path.name} and the execution log.")

    with ctx.step("2. v17 capture — the whole id->state map, because a "
                  "purchase order must not become locked and vice versa."):
        if has_locked:
            rows = sql.rows("SELECT id, state, locked FROM purchase_order "
                            "ORDER BY id")
        else:
            rows = [(oid, state, False) for oid, state in sql.rows(
                "SELECT id, state FROM purchase_order ORDER BY id")]
        normalised = {}
        for order_id, state, locked in rows:
            normalised[int(order_id)] = _normalise_po_state(
                state, bool(locked), has_locked)
        for order_id, value in sorted(normalised.items()):
            snapshot[f"po_state/{order_id}"] = value
        snapshot["po_state/ORDERS"] = len(normalised)
        ctx.log(f"{len(normalised)} purchase order(s) normalised")

    with ctx.step("3. v19 capture — the new shape."):
        # Both shapes are captured by the SAME normalisation above, which is
        # what makes steps 4 and 5 diffable at all; what belongs to this step
        # is the normalised histogram, because the raw one differs by
        # construction ('done' exists on v17 and not on v19).
        histogram: dict = {}
        for value in normalised.values():
            histogram[value] = histogram.get(value, 0) + 1
        for value, count in sorted(histogram.items()):
            snapshot[f"state_count/{value}"] = count
        evidence["normalised_state_histogram"] = histogram
        ctx.log(f"normalised state histogram: {histogram!r}")

    with ctx.step("4. Assert the conversion rule per order: v17 state='done' "
                  "-> v19 state='purchase' AND locked = TRUE; v17 "
                  "state='purchase' -> v19 state='purchase' AND locked = "
                  "FALSE; v17 draft|sent|to approve|cancel -> unchanged, "
                  "locked = FALSE."):
        # ONE mismatch dict, not an assertion loop: a failure names every
        # order that cannot be mapped. On v17 a 'done' order normalises into
        # the rule's own target value; on v19 a locked order in any state but
        # 'purchase' falls outside ALLOWED_PO_STATES and is reported here.
        unmappable = {f"purchase_order/{oid}": value
                      for oid, value in sorted(normalised.items())
                      if value not in ALLOWED_PO_STATES}
        evidence["unmappable_orders"] = unmappable
        _json_artifact(ctx, "tc032_diff_po_state.json",
                       {"tc_id": TC032, "env": ctx.env.key, "db": ctx.env.db,
                        "allowed": list(ALLOWED_PO_STATES),
                        "unmappable": unmappable},
                       "TC032 diff_po_state (orders outside the rule)")
        ctx.check("purchase orders whose state does not land on the "
                  "conversion rule", {}, unmappable)

    with ctx.step("5. Assert the counts tie: count(v17 state='done') == "
                  "count(v19 locked = TRUE); count(v17 state='purchase') == "
                  "count(v19 state='purchase' AND NOT locked)."):
        locked_equivalent = sum(1 for v in normalised.values()
                                if v == "purchase|locked")
        purchase_open = sum(1 for v in normalised.values()
                            if v == "purchase|open")
        snapshot["count/locked_equivalent"] = locked_equivalent
        snapshot["count/purchase_open"] = purchase_open
        # Re-read the same two figures straight from SQL, so the identity is
        # asserted against the raw data and not merely against the
        # normalisation that produced it.
        if has_locked:
            raw_locked = sql.one("SELECT count(*) FROM purchase_order "
                                 "WHERE locked") or 0
            raw_open = sql.one("SELECT count(*) FROM purchase_order "
                               "WHERE state = 'purchase' AND NOT locked") or 0
        else:
            raw_locked = sql.one("SELECT count(*) FROM purchase_order "
                                 "WHERE state = 'done'") or 0
            raw_open = sql.one("SELECT count(*) FROM purchase_order "
                               "WHERE state = 'purchase'") or 0
        ctx.check("both count identities hold against the raw table",
                  {"locked_equivalent": int(raw_locked),
                   "purchase_open": int(raw_open)},
                  {"locked_equivalent": locked_equivalent,
                   "purchase_open": purchase_open})

    with ctx.step("6. Assert the amounts are untouched by the state "
                  "conversion."):
        total, untaxed, count = sql.rows(
            "SELECT round(sum(amount_total)::numeric,2), "
            "round(sum(amount_untaxed)::numeric,2), count(*) "
            "FROM purchase_order")[0]
        snapshot["amount/total"] = float(total or 0)
        snapshot["amount/untaxed"] = float(untaxed or 0)
        snapshot["amount/orders"] = int(count or 0)
        ctx.check("the money capture covers every purchase order the id->"
                  "state map does", snapshot["po_state/ORDERS"],
                  snapshot["amount/orders"])

    with ctx.step("7. Assert the line-level UoM rename carried the data, not "
                  "just the column."):
        snapshot["pol/rows"] = int(sql.one(
            "SELECT count(*) FROM purchase_order_line") or 0)
        snapshot["pol/uom_set"] = int(sql.one(
            f"SELECT count(*) FROM purchase_order_line "
            f"WHERE {uom_column} IS NOT NULL") or 0)
        snapshot["pol/uom_null"] = (snapshot["pol/rows"]
                                    - snapshot["pol/uom_set"])
        # The COLUMN NAME differs by construction and is deliberately kept out
        # of the diffed snapshot (it would be a permanent, meaningless diff);
        # it was asserted against the version in the precondition step and is
        # recorded as evidence here.
        ctx.log(f"{snapshot['pol/uom_set']} of {snapshot['pol/rows']} "
                f"purchase order line(s) carry {uom_column}")
        ctx.check_true(
            "the UoM column is populated, so the carry count is not vacuous",
            snapshot["pol/uom_set"] > 0,
            actual_desc=f"{snapshot['pol/uom_set']} populated")

        # This suite's own leftovers are measured and reported so they can
        # explain a diff, and deliberately kept out of the diffed snapshot
        # (the wf021 precedent). sweep_wf015 removes them, but a validated
        # receipt can pin a purchase order in place.
        leakage = int(sql.one(
            "SELECT count(*) FROM purchase_order o JOIN res_partner p "
            "ON p.id = o.partner_id WHERE p.name LIKE %s",
            (f"{MARKER}%",)) or 0)
        evidence["wf015_leftover_orders"] = leakage
        ctx.log(f"{MARKER}-marked purchase orders present at capture time: "
                f"{leakage}")

    _json_artifact(ctx, "tc032_capture.json", evidence,
                   "TC032 capture evidence")

    # Steps 4-7's cross-version half. Deliberately BEFORE step 8: step 8 fails
    # on the v17 baseline by construction (three surviving 'done' expressions),
    # and the capture above must be persisted rather than lost to it.
    reconcile(ctx, TC032, lambda _ctx, _snap=snapshot: _snap)

    with ctx.step("8. Grep the v19 source for the dead state expression."):
        root = require_source_root(ctx)
        raw_scan = grep_dto(ctx, PO_DONE_SCAN_MODULES, PO_DONE_SCAN_PATTERN)
        xml = _scan_xml_done_hits(root, PO_DONE_SCAN_MODULES,
                                  PO_DONE_SCAN_PATTERN)
        python_files = _python_done_files(raw_scan)
        _json_artifact(
            ctx, "tc032_done_grep.json",
            {"tc_id": TC032, "source_root": str(root),
             "modules": list(PO_DONE_SCAN_MODULES),
             "pattern": PO_DONE_SCAN_PATTERN,
             "raw": {m: h for m, h in sorted(raw_scan.items())},
             "xml_attributed": xml["hits"],
             "xml_unresolved": xml["unresolved"],
             "python_files": python_files},
            "TC032 step 8 — every 'done' literal, attributed")

        ctx.check("every XML 'done' literal could be attributed to a record's "
                  "declared model", [], xml["unresolved"])

        ctx.check("non-test Python files carrying a 'done' literal are the "
                  "two verified-benign ones",
                  sorted(VERIFIED_BENIGN_PY_DONE_FILES),
                  sorted(python_files))

        surviving = [f"{h['module']}/{h['file']}:{h['line']}"
                     for h in xml["hits"] if h["model"] == "purchase.order"]
        ctx.log(f"surviving purchase.order 'done' expressions: {surviving!r}")
        ctx.check("purchase.order 'done' expressions surviving in "
                  f"{', '.join(PO_DONE_SCAN_MODULES)}", [], surviving)

        reports_view = None
        base = module_path(root, "dto_reports")
        if base is not None:
            candidate = base / "views" / "purchase_order.xml"
            if candidate.is_file():
                reports_view = candidate.read_text(encoding="utf-8",
                                                   errors="replace")
        ctx.check_true(
            "dto_reports/views/purchase_order.xml uses locked",
            bool(reports_view) and "locked" in reports_view,
            actual_desc=("file not found" if reports_view is None
                         else f"'locked' present={'locked' in reports_view}"))


# ===========================================================================
# TC047 — attachment counts and bytes by model
# ===========================================================================
#: The three business-critical subsets the workbook names, verbatim.
ATTACHMENT_SUBSETS = (
    ("vendor bill attachments", "account.move"),
    ("receipt packing slips", "stock.picking"),
    ("MO test results", "mrp.production"),
)

#: dto_purchase_stock/models/stock_picking.py:14-16 — a fields.Binary with no
#: attachment=False, so Odoo stores it as an ir_attachment row carrying this
#: res_field (O17 odoo/fields.py:2461-2473, O19 orm/fields_binary.py:174).
PACKING_SLIP_RES_FIELD = "packing_slip_attachment"


@test_case(
    id="TEST-WF015-TC047",
    name="Attachment counts and bytes by model",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account, dto_mrp, dto_mrp_sftp, dto_purchase_stock",
    priority="P1", kind="DATA", order=15047,
    description="Counts, bytes, type split and per-model checksum digests "
                "over ir_attachment, the orphaned-binary detector, the "
                "filestore existence sweep and the three business-critical "
                "subsets — captured on v17 and diffed on v19.",
    traceability=trace("DATAONE-TC047"))
def test_tc047(ctx):
    sql = ctx.sql                      # BLOCKS by itself without pg_* config
    snapshot: dict = {}
    evidence: dict = {"tc_id": TC047, "env": ctx.env.key, "db": ctx.env.db}

    with ctx.step("Precondition: every ir_attachment column this case reads "
                  "exists on this target"):
        columns = ("res_model", "res_field", "res_id", "type", "db_datas",
                   "store_fname", "file_size", "checksum")
        missing = [f"ir_attachment.{c}" for c in columns
                   if not sql.column_exists("ir_attachment", c)]
        if missing:
            ctx.blocked(
                f"These columns do not exist on {ctx.env.key} "
                f"(db={ctx.env.db}): {', '.join(missing)}. They are declared "
                "identically on both versions (O17 base/models/"
                "ir_attachment.py:410-431, O19 :456-476), so their absence is "
                "a broken database, not a test failure.")

    with ctx.step("1. Both versions — count and bytes by model."):
        rows = sql.rows(
            "SELECT COALESCE(res_model,'(none)') AS res_model, "
            "       count(*) AS attachments, "
            "       COALESCE(sum(file_size),0) AS total_bytes, "
            "       count(*) FILTER (WHERE type='url')    AS url_type, "
            "       count(*) FILTER (WHERE type='binary') AS binary_type "
            "FROM ir_attachment GROUP BY 1 ORDER BY 1")
        for res_model, attachments, total_bytes, url_type, binary in rows:
            key = str(res_model)
            snapshot[f"by_model/{key}/attachments"] = int(attachments or 0)
            snapshot[f"by_model/{key}/total_bytes"] = int(total_bytes or 0)
            snapshot[f"by_model/{key}/url_type"] = int(url_type or 0)
            snapshot[f"by_model/{key}/binary_type"] = int(binary or 0)
        snapshot["by_model/MODELS"] = len(rows)
        ctx.log(f"{len(rows)} distinct res_model value(s)")

    with ctx.step("2. Both versions — the grand total."):
        total, total_bytes = sql.rows(
            "SELECT count(*), COALESCE(sum(file_size),0) "
            "FROM ir_attachment")[0]
        snapshot["grand_total/attachments"] = int(total or 0)
        snapshot["grand_total/bytes"] = int(total_bytes or 0)
        ctx.check("the per-model counts add up to the grand total",
                  snapshot["grand_total/attachments"],
                  sum(v for k, v in snapshot.items()
                      if k.startswith("by_model/") and k.endswith(
                          "/attachments")))

    with ctx.step("3. Both versions — the checksum set, which detects content "
                  "change as well as loss."):
        rows = sql.rows(
            "SELECT COALESCE(res_model,'(none)') AS res_model, "
            "       md5(string_agg(COALESCE(checksum,''), ',' ORDER BY id)) "
            "           AS checksum_digest, "
            "       count(*) AS n "
            "FROM ir_attachment GROUP BY 1 ORDER BY 1")
        for res_model, digest, n in rows:
            key = str(res_model)
            snapshot[f"checksum_digest/{key}"] = _scalar(digest)
            snapshot[f"checksum_rows/{key}"] = int(n or 0)
        ctx.log(f"{len(rows)} per-model checksum digest(s)")

    with ctx.step("4. Both versions — attachments with no backing storage, "
                  "which is what a lost filestore looks like."):
        orphaned = sql.one(
            "SELECT count(*) FROM ir_attachment "
            "WHERE type='binary' AND store_fname IS NULL "
            "AND db_datas IS NULL") or 0
        snapshot["orphaned_binary"] = int(orphaned)
        ctx.log(f"attachments with neither store_fname nor db_datas: "
                f"{orphaned}")

    with ctx.step("5. Sweep the filestore for the files the database "
                  "expects."):
        store = _filestore_dir(ctx)
        if store is None:
            tried = [str(base / "filestore" / ctx.env.db)
                     for base in _data_dir_candidates(ctx)]
            ctx.blocked(
                "The filestore directory for "
                f"{ctx.env.key} (db={ctx.env.db}) is not reachable from this "
                "workstation. The platform carries no filestore setting "
                "(backend/config.py:55-68 has only URLs, database names and "
                "pg_*), so set DTO_FILESTORE_ROOT_"
                f"{ctx.env.version} (or DTO_FILESTORE_ROOT) in "
                "config/local.yaml to the Odoo data_dir — on this deployment "
                "D:\\Projects\\dataone\\dto.conf sets data_dir to "
                "%LOCALAPPDATA%\\OpenERP S.A\\Odoo. Tried, in order: "
                + "; ".join(tried) + ". This step is the only one in the "
                "suite that touches the filesystem and the only one that can "
                "see a lost filestore, so it does not fall back to the "
                "database's own view of itself.")
        evidence["filestore"] = str(store)
        ctx.log(f"filestore: {store}")

        expected_rows = int(sql.one(
            "SELECT count(*) FROM ir_attachment "
            "WHERE store_fname IS NOT NULL") or 0)
        names = [row[0] for row in sql.rows(
            "SELECT DISTINCT store_fname FROM ir_attachment "
            "WHERE store_fname IS NOT NULL ORDER BY 1")]
        # The filestore is deduplicated by checksum, so many rows share one
        # file: both figures are recorded, and the sweep runs over the
        # distinct set.
        missing = [name for name in names if not (store / name).is_file()]
        snapshot["filestore/expected_rows"] = expected_rows
        snapshot["filestore/distinct_files"] = len(names)
        snapshot["filestore/missing"] = len(missing)
        evidence["filestore_missing_sample"] = missing[:20]
        _json_artifact(ctx, "tc047_filestore_missing.json",
                       {"tc_id": TC047, "env": ctx.env.key,
                        "db": ctx.env.db, "filestore": str(store),
                        "expected_rows": expected_rows,
                        "distinct_files": len(names),
                        "missing": missing},
                       "TC047 filestore existence sweep")
        ctx.check("missing=0", 0, len(missing))

    with ctx.step("6. Assert the business-critical subsets by count."):
        for label, res_model in ATTACHMENT_SUBSETS:
            count = sql.one("SELECT count(*) FROM ir_attachment "
                            "WHERE res_model = %s", (res_model,)) or 0
            snapshot[f"subset/{label}"] = int(count)
            ctx.log(f"{label} (res_model={res_model}): {count}")

        # THE CORRECTION, recorded rather than worked around (module
        # docstring): packing_slip_attachment is an attachment-backed
        # fields.Binary, so F069's own rows ARE inside the stock.picking count
        # above, carrying res_field='packing_slip_attachment'. Captured
        # separately so the baseline can tell F069's documents apart from the
        # receipt chatter they are pooled with.
        f069 = sql.one("SELECT count(*) FROM ir_attachment "
                       "WHERE res_model = 'stock.picking' AND res_field = %s",
                       (PACKING_SLIP_RES_FIELD,)) or 0
        f069_bytes = sql.one("SELECT COALESCE(sum(file_size),0) "
                             "FROM ir_attachment WHERE res_model = "
                             "'stock.picking' AND res_field = %s",
                             (PACKING_SLIP_RES_FIELD,)) or 0
        snapshot["subset/receipt packing slips (F069 res_field)"] = int(f069)
        snapshot["subset/receipt packing slip bytes"] = int(f069_bytes)
        ctx.log(f"F069 packing slips stored as ir_attachment rows with "
                f"res_field={PACKING_SLIP_RES_FIELD!r}: {f069} "
                f"({f069_bytes} bytes)")
        ctx.check_true(
            "the F069 sub-count is a subset of the stock.picking count, which "
            "is what an attachment-backed fields.Binary guarantees "
            "(O17 odoo/fields.py:2461-2473)",
            f069 <= snapshot["subset/receipt packing slips"],
            actual_desc=f"{f069} of "
                        f"{snapshot['subset/receipt packing slips']}")

        # This suite's own leftovers: the merged print creates one attachment
        # named 'Packing Slip' with NO res_id (dto_purchase_stock/models/
        # stock_picking.py:110-117), which cannot be namespaced. Measured and
        # reported so it can explain a diff; not part of the snapshot.
        leakage = int(sql.one(
            "SELECT count(*) FROM ir_attachment "
            "WHERE name = 'Packing Slip' AND res_id IS NULL") or 0)
        evidence["merged_print_leftovers"] = leakage
        ctx.log(f"un-namespaceable 'Packing Slip' merge outputs present at "
                f"capture time: {leakage}")

    _json_artifact(ctx, "tc047_capture.json", evidence,
                   "TC047 capture evidence")

    # 7. Diff steps 1, 2, 3 and 6 (and 4 and 5, which the same snapshot
    #    carries) against the persisted v17 baseline.
    reconcile(ctx, TC047, lambda _ctx, _snap=snapshot: _snap)
