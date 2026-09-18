"""DATAONE-WF-022 — the defect-code taxonomy (F252): TC180, TC181.

Both cases are the same nine-entry Python table and the same three-line
lookup, declared identically in the two carriers and reproduced here only as
the EXPECTED value set — never re-implemented (the compute is private and so
unreachable over RPC)::

    @api.depends('defect_code')                     # v17 :49 / v19 :68
    def _compute_defect_code_description(self):
        defect_codes = {"A": "Not in BOM", …, "R": "Reference Cable"}
                                                    # v17 :52-62 / v19 :75-85
        if res.defect_code:
            res.defect_code_description = defect_codes.get(
                res.defect_code.upper().strip(), _('Unknown defect code'))
                                                    # v17 :64    / v19 :87
        else:
            res.defect_code_description = ''        # v17 :66    / v19 :89

(``DTO/project-addons/dto_tier_validation_scrap/models/stock_scrap.py`` and
``DTO/project-addons/dto_scrap/models/stock_scrap.py``; ``DTO`` =
``D:/Projects/dataone/DTO-Odoo``, ``O17`` = ``D:/Projects/dataone/odoo-17.0``,
``O19`` = ``D:/Projects/odoo-19.0``.)

Three properties of that source shape everything below.

1. ``.upper()`` **then** ``.strip()`` — so ``b`` and ``B  `` both resolve, and
   the padding must genuinely reach the database for TC180 step 7 to mean
   anything. It does: ``Char.trim`` is applied "only by the web client"
   (``O17 odoo/fields.py:1917-1929``) and, on v19, by the web client and
   ``base_import`` only (``O19 odoo/orm/fields_textual.py:484-500``). An ORM
   write over ``/web/dataset/call_kw`` is untouched, so the test asserts the
   stored value is ``"B  "`` verbatim as its own non-vacuity guard.
2. The falsy branch writes an **empty string**, not the fallback. Over RPC a
   blank ``Char`` reads back as ``False`` on both versions, so every read goes
   through ``common.blank()``.
3. ``defect_code`` is a bare ``Char`` — no ``required``, no ``selection``, no
   ``@api.constrains``, no ``_sql_constraints`` and no reference from any
   action. A repo-wide grep for ``defect_code`` over ``DTO`` (``.py``,
   ``.xml``, ``.js``, ``.csv``; ``i18n/`` excluded per
   AUTOMATION_CONVENTIONS' search scope) returns the two field declarations,
   the two computes, the two view inherits, the in-repo unit tests, **and two
   further non-behavioural hits**: the migration/uninstall helper
   ``tools/uninstall_non_migrated.py`` (6 — a column list at :390-391 and a
   row-count query at :455-459) and one comment in
   ``dto_tier_validation_scrap/__manifest__.py:49``. Neither is a constraint,
   a selection, an ``@api.constrains`` or a ``_sql_constraints``, so the
   negative fact TC181 rests on is unaffected. That negative fact IS TC181
   (BR-3).

TC180 also asserts where the fields land. The inherit is
``<xpath expr="//field[@name='lot_id']" position="before">`` wrapping five
fields (``dto_tier_validation_scrap/views/stock_scrap_views.xml:65-71``;
``dto_scrap/views/stock_scrap_views.xml:69-75`` — character for character the
same block), so the document-order window immediately before ``lot_id`` must
read ``company_currency_id, amount, defect_code, defect_code_description,
employee_name``. No other inherit of ``stock.stock_scrap_form_view`` touches
that region: ``mrp`` inserts after ``owner_id``
(``O17 mrp/views/stock_scrap_views.xml:22-27``, ``O19 :22-27``),
``stock_barcode`` appends inside ``<form>``
(``O17 enterprise-17.0/stock_barcode/views/stock_scrap_views.xml:28-30``) and
``dto_stock`` works inside ``//div[@name='button_box']``
(``dto_stock/views/stock_scrap_views.xml:3-20``).

Why that ordering is read from the COMBINED arch, not only the rendered one
--------------------------------------------------------------------------
``lot_id`` carries ``groups="stock.group_production_lot"``
(``O17 stock/views/stock_scrap_views.xml:61`` / ``O19 :60``) and
``_postprocess_access_rights`` **removes** any node whose ``groups`` the
session does not hold (``O17 odoo/addons/base/models/ir_ui_view.py:1000-1013``
— ``node.getparent().remove(node)``). The anchor would therefore vanish from
``get_view()``'s output on any session without that group, turning a correct
system into a FAIL. ``ir.ui.view.get_combined_arch()`` is public, takes no
arguments, returns a ``str`` and applies inheritance **without** access-rights
postprocessing on both versions (``O17 ir_ui_view.py:920-922`` /
``O19 :1043-1045``), so it is the session-independent source for a
composition claim. The rendered arch is asserted **as well**, whenever
``lot_id`` survives it — nothing is weakened, one more source is added.

Read-only, and why never ``"1"``
--------------------------------
Step 5 goes through ``common.readonly_is_absolute()``. The view source is
``<field name="defect_code_description" readonly="1"/>`` on both versions, but
``TierValidation.get_view`` rewrites every field node's modifier to
``f"({old}) or ({new})"`` on v17
(``DTO/3rd-addons/base_tier_validation/models/tier_validation.py:780-788``),
so the rendered value there is ``"(1) or (bool(review_ids))"``. The ORM half
is asserted too: a stored compute with no inverse gets ``readonly=True`` from
``attrs['readonly'] = attrs.get('readonly', not attrs.get('inverse'))``
(``O17 odoo/fields.py:445`` / ``O19 odoo/orm/fields.py:451``), surfaced by
``fields_get`` through ``_description_readonly`` (``O17 :865`` / ``O19 :895``).

TC181 step 7 — proven structurally, and why validation is never executed
------------------------------------------------------------------------
``action_validate`` has exactly two gates: the zero-quantity guard and
``check_available_qty()`` (``O17 stock/models/stock_scrap.py:196-220`` /
``O19 :211-235``). ``defect_code`` appears in neither, nor anywhere else in
core or in either DataOne module. The test asserts both gates pass **while the
unknown code is set** — ``check_available_qty()`` is public, returns a bool
and changes nothing — and stops there. Actually validating would be
irreversible twice over: a done scrap cannot be unlinked
(``You cannot delete a scrap which is done.``, ``O17 :107-110`` / ``O19 :120-123``)
and, worse for this very pair of cases, it would permanently add a row to the
"Unknown defect code" bucket that step 8 measures — each rerun would inflate
its own baseline. Documented per hard rule 5.

Adaptations (documented, not assertion-weakening)
-------------------------------------------------
* **The workbook's cross-case handoff is deliberately not implemented.**
  TC180's postcondition is *"Leave the scrap draft for TC182"* and TC181's is
  *"Restore defect_code = 'B' for TC182"*. Hard rule 5 forbids one test
  depending on another's fixtures, so each test builds its own token-scoped
  scrap, **asserts the workbook's ``expected_final_state`` on it** (code ``B``
  plus an employee name for TC180; code ``B`` for TC181) and then sweeps it.
  TC182 builds its own.
* **TD-P-04 / TD-E-01 are workbook test-data labels, not records**
  ``[UNVERIFIED as ids]``. TD-P-04 is stood up as a token-scoped storable
  product; TD-E-01 is supplied as free text, which is exactly what step 9
  proves the field is.
* **TC181 step 8 is logged and exported, never asserted as a number.** It is a
  whole-table count over live data; hard rule 5 forbids an unscoped
  "exactly N". What IS asserted there is that the domain answers at all —
  which is a real claim, since a non-stored compute without ``search=`` cannot
  be searched.

EXPECTED v17 OUTCOME — TC180: PASS. Every rule asserted is v17-deployed source.
EXPECTED v17 OUTCOME — TC181: PASS. Same compute, same fallback literal.
Both are subject to §0 of ``docs/WF-022_AUTOMATION_PLAN.md``: if the v17 server
reloads the current tree, ``dto_tier_validation_scrap/__manifest__.py:56``
declares ``installable: False`` and ``O17 odoo/modules/graph.py:72-75`` skips a
not-installable module even when the database says ``state='installed'``, so
the five fields are absent and ``common.check_scrap_extension`` — the first
assertion of each test — fails loudly and correctly attributed.

EXPECTED v19 OUTCOME — both PASS. ``dto_scrap`` re-declares the identical table
and literal. Note the v19 REPLACE candidate the workbook flags: native
``scrap_reason_tag_ids`` / ``stock.scrap.reason.tag``
(``O19 stock/models/stock_scrap.py:56-59, 237-250``) — its presence on the
target is recorded in TC180's exported baseline, not asserted.
"""
from __future__ import annotations

import json

from adapters.base import OdooRPCError
from framework.registry import test_case
from tests.wf022.common import (DEFECT_CODE_ORDER, DEFECT_CODES,
                                EMPTY_DEFECT_DESCRIPTION, MARKER,
                                MODULE_TIER_SCRAP, UNKNOWN_DEFECT_DESCRIPTION,
                                VIEW_FULL_FORM, WORKFLOW, WORKFLOW_NAME,
                                add_stock, blank, check_scrap_extension,
                                drop_scraps, expect_error, field_order,
                                fields_get, make_product, make_scrap,
                                open_namespace, parse_arch, read_scrap,
                                readonly_is_absolute, readonly_of,
                                rpc_as_role, scrap_arch, search_count,
                                stock_location, sweep_wf022, tag, trace,
                                write_scrap)

#: The workbook's actor for both cases (``role_user`` column). The label maps
#: to real core groups in ``common.ROLE_GROUPS``; it is not a group xmlid.
ROLE = "TD-U-05"

#: The five fields the WF-022 inherit inserts, in the source's own order
#: (v17 views :65-71 / v19 views :69-75), and the core anchor they precede
#: (``O17 stock/views/stock_scrap_views.xml:61`` / ``O19 :60``).
INSERTED_BLOCK = ("company_currency_id", "amount", "defect_code",
                  "defect_code_description", "employee_name")
LOT_FIELD = "lot_id"
EXPECTED_WINDOW = list(INSERTED_BLOCK) + [LOT_FIELD]

#: v19's REPLACE candidate for F252 — recorded in TC180's exported baseline,
#: never asserted (``O19 stock/models/stock_scrap.py:56-59, 237-250``).
V19_TAG_MODEL = "stock.scrap.reason.tag"
V19_TAG_FIELD = "scrap_reason_tag_ids"


# ----------------------------------------------------------- local helpers
# Defined here rather than in common.py: that file is owned by another agent
# and carries no combined-arch reader and no role-session probe.
def _combined_arch(ctx, xmlid: str):
    """The parsed arch of one view WITH its inherits and WITHOUT access-rights
    postprocessing.

    ``ir.ui.view.get_combined_arch()`` is public, argument-free and returns a
    unicode string on both versions (``O17 ir_ui_view.py:920-922`` /
    ``O19 :1043-1045``). Unlike ``get_view()`` it does not run
    ``_postprocess_access_rights``, so a node carrying ``groups=`` survives
    regardless of what the session holds — see the module docstring.
    """
    rpc = ctx.adapter.rpc
    view_id = rpc.ref(xmlid)
    if not view_id:
        ctx.blocked(f"XML id {xmlid!r} does not resolve on {ctx.env.key} "
                    f"(db={ctx.env.db}) — the full scrap form this case "
                    f"asserts the field order against is not in the database.")
    return parse_arch(rpc.call("ir.ui.view", "get_combined_arch", [view_id]))


def _window_before(names: list, anchor: str, size: int) -> list:
    """The ``size`` field names immediately preceding ``anchor``, plus it.

    Returns a readable marker instead of raising when the anchor is missing,
    so a failure reports what the arch actually contained.
    """
    if anchor not in names:
        return [f"<{anchor} absent>"] + names[-size:]
    index = names.index(anchor)
    return names[max(0, index - size):index + 1]


def _role_session(ctx):
    """An authenticated session for the workbook's actor, probed before use.

    ``OdooRPC.__init__`` is lazy (``adapters/base.py:75-79``), so a bad
    credential only surfaces on the first call — the probe turns that into a
    precise BLOCKED rather than an AUTOMATION_ERROR mid-assertion. Fixtures
    are still created and swept with the platform's admin session:
    ``stock.group_stock_user`` holds no ``perm_unlink`` on ``stock.scrap``
    (``O17 stock/security/ir.model.access.csv:54`` / ``O19 :41``).
    """
    role = rpc_as_role(ctx, ROLE)
    raised, message = expect_error(role.call, "stock.scrap", "search_count",
                                   [("id", "=", 0)])
    if raised:
        ctx.blocked(
            f"cannot open a {ROLE} session on {ctx.env.key} (db={ctx.env.db}) "
            f"— the workbook's actor for this case. Login "
            f"'qa.wf022.{ROLE.lower().replace('-', '')}' could not read "
            f"stock.scrap: {message}")
    return role


def _description(rpc, scrap_id: int) -> str:
    """``defect_code_description`` as a string (blank reads back as False)."""
    row = rpc.read("stock.scrap", [scrap_id], ["defect_code_description"])[0]
    return blank(row["defect_code_description"])


def _code(rpc, scrap_id: int) -> str:
    row = rpc.read("stock.scrap", [scrap_id], ["defect_code"])[0]
    return blank(row["defect_code"])


def _available_gate(rpc, scrap_id: int):
    """``check_available_qty()`` — public, returns a bool, changes nothing
    (``O17 stock/models/stock_scrap.py:181-194`` / ``O19 :196-209``).

    An RPC failure is returned as a string so it lands in the mismatch dict as
    a FAIL rather than escaping as an AUTOMATION_ERROR.
    """
    try:
        return rpc.call("stock.scrap", "check_available_qty", [scrap_id])
    except OdooRPCError as exc:          # noqa: PERF203 — reported, not hidden
        return f"raised: {exc}"


# ======================================================================= 180
@test_case(
    id="TEST-WF022-TC180",
    name="Defect code B yields *Received Damaged*, case- and "
         "whitespace-insensitively",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module=MODULE_TIER_SCRAP,
    priority="P1", kind="DATA", order=22180,
    description="All nine defect codes map to their exact descriptions, the "
                "lookup ignores case and padding, an empty code yields an "
                "empty description rather than the fallback, the five fields "
                "sit immediately before Lot/Serial, the description is "
                "read-only and employee_name is an unvalidated free-text "
                "Char; the nine pairs are exported as the migration baseline.",
    traceability=trace("DATAONE-TC180"))
def test_tc180(ctx):
    rpc = ctx.adapter.rpc
    open_namespace(ctx)
    scrap_id = None
    observed = {}
    try:
        with ctx.step("Log in as TD-U-05 and open the draft scrap in the "
                      "full form"):
            # The workbook precondition ("dto_tier_validation_scrap is
            # installed") is the first assertion, not a skip — §0 of
            # docs/WF-022_AUTOMATION_PLAN.md.
            check_scrap_extension(ctx)
            product_id = make_product(ctx, "TD-P-04", standard_price=12.50)
            scrap_id = make_scrap(ctx, product_id, qty=1.0)
            role = _role_session(ctx)
            row = read_scrap(role, scrap_id,
                             ["state", "defect_code",
                              "defect_code_description"])
            ctx.check("TD-U-05 opens a draft scrap with no code and no "
                      "description",
                      {"state": "draft", "defect_code": "",
                       "defect_code_description": EMPTY_DEFECT_DESCRIPTION},
                      {"state": row["state"],
                       "defect_code": blank(row["defect_code"]),
                       "defect_code_description":
                           blank(row["defect_code_description"])})

        with ctx.step("Assert the Defect Code and Employee fields appear "
                      "immediately before the Lot/Serial field"):
            windows = {}
            combined_names = field_order(_combined_arch(ctx, VIEW_FULL_FORM))
            windows["combined arch (ir.ui.view.get_combined_arch)"] = \
                _window_before(combined_names, LOT_FIELD, len(INSERTED_BLOCK))
            rendered_names = field_order(parse_arch(scrap_arch(ctx, "form")))
            if LOT_FIELD in rendered_names:
                windows["rendered arch (get_view)"] = _window_before(
                    rendered_names, LOT_FIELD, len(INSERTED_BLOCK))
            else:
                ctx.log(
                    "lot_id is absent from the RENDERED arch — it carries "
                    "groups=\"stock.group_production_lot\" (O17 "
                    "stock/views/stock_scrap_views.xml:61 / O19 :60) and "
                    "_postprocess_access_rights removes a node whose groups "
                    "the session does not hold (O17 "
                    "base/models/ir_ui_view.py:1000-1013). The combined arch "
                    "carries the same claim session-independently.")
            ctx.log(f"field order around the anchor: {windows!r}")
            ctx.check("the five-field block sits immediately before lot_id",
                      {source: EXPECTED_WINDOW for source in windows},
                      windows)

        with ctx.step("Type B into Defect Code and save"):
            raised, message = expect_error(write_scrap, role, scrap_id,
                                           {"defect_code": "B"})
            ctx.check("the save succeeded and B is stored",
                      {"raised": False, "defect_code": "B"},
                      {"raised": raised, "defect_code": _code(role, scrap_id)})
            ctx.log(f"write message: {message!r}")

        with ctx.step("Assert Defect Code Description reads exactly "
                      "Received Damaged"):
            ctx.check("B → Received Damaged", DEFECT_CODES["B"],
                      _description(role, scrap_id))

        with ctx.step("Assert the description field is read-only"):
            modifier = readonly_of(parse_arch(scrap_arch(ctx, "form")),
                                   "defect_code_description")
            declared = fields_get(role, "stock.scrap",
                                  ["defect_code_description"],
                                  attributes=["readonly", "store", "type"]
                                  ).get("defect_code_description", {})
            ctx.log(f"rendered readonly modifier = {modifier!r}")
            # Never compare against "1": the tier mixin rewrites the modifier
            # to "(1) or (bool(review_ids))" on v17 (tier_validation.py:780-788).
            ctx.check("Defect Code Description is read-only in the view and "
                      "in the ORM",
                      {"view modifier is unconditionally read-only": True,
                       "ORM reports readonly": True,
                       "it is a stored compute": True},
                      {"view modifier is unconditionally read-only":
                           readonly_is_absolute(modifier),
                       "ORM reports readonly": bool(declared.get("readonly")),
                       "it is a stored compute": bool(declared.get("store"))})

        with ctx.step("Change the code to lowercase b and save; assert the "
                      "description is still Received Damaged"):
            write_scrap(role, scrap_id, {"defect_code": "b"})
            ctx.check("lowercase b still maps, and the raw value is not "
                      "normalised on the way in",
                      {"defect_code_description": DEFECT_CODES["B"],
                       "defect_code stored": "b"},
                      {"defect_code_description": _description(role, scrap_id),
                       "defect_code stored": _code(role, scrap_id)})

        with ctx.step("Change the code to B  (trailing space) and save; "
                      "assert the description is still Received Damaged"):
            # Asserting the stored value is the non-vacuity guard: if the
            # padding never reached the database, .strip() would not be under
            # test at all. Char.trim is a web-client concern only
            # (O17 fields.py:1917-1929 / O19 fields_textual.py:484-500).
            #
            # Both padded forms are exercised, in ONE mismatch dict asserted
            # once. The workbook step names "B  " only; "  b" is added
            # because the expected result is "case- AND whitespace-
            # insensitive" and the lookup is
            # defect_code.upper().strip() (dto_tier_validation_scrap/models/
            # stock_scrap.py:64 / dto_scrap :87) — leading padding combined
            # with the lower case is the variant that exercises both calls at
            # once. Strengthening, never weakening (hard rule 2).
            padded_forms = ["B  ", "  b"]
            observed_padded = {}
            for padded in padded_forms:
                write_scrap(role, scrap_id, {"defect_code": padded})
                observed_padded[padded] = {
                    "defect_code_description": _description(role, scrap_id),
                    "defect_code stored": _code(role, scrap_id)}
            ctx.check("a padded code still maps, and the padding really "
                      "reached the database",
                      {padded: {"defect_code_description": DEFECT_CODES["B"],
                                "defect_code stored": padded}
                       for padded in padded_forms},
                      observed_padded)

        with ctx.step("Set Employee to the free-text name of TD-E-01 and "
                      "save; assert the value is stored verbatim on "
                      "employee_name"):
            # TD-E-01 is a workbook test-data label [UNVERIFIED as an
            # hr.employee record]; the next step is precisely why that does
            # not matter — the field has no HR link to resolve it against.
            employee_name = tag("TD-E-01 Free Text Employee")
            write_scrap(role, scrap_id, {"employee_name": employee_name})
            row = read_scrap(role, scrap_id, ["employee_name"])
            ctx.check("employee_name is stored verbatim", employee_name,
                      blank(row["employee_name"]))

        with ctx.step("Assert employee_name is a plain Char — there is no "
                      "hr.employee link and no validation"):
            info = fields_get(role, "stock.scrap",
                              ["employee_name"]).get("employee_name", {})
            ctx.log(f"employee_name declaration: {info!r}")
            ctx.check("employee_name is an unvalidated Char with no comodel "
                      "and no selection",
                      {"type": "char", "string": "Employee", "relation": None,
                       "selection": None, "required": False},
                      {"type": info.get("type"), "string": info.get("string"),
                       "relation": info.get("relation"),
                       "selection": info.get("selection"),
                       "required": bool(info.get("required"))})

        with ctx.step("Iterate the full table and assert each mapping: "
                      "A → Not in BOM, B → Received Damaged, C → Operator "
                      "Error, D → Shortage, E → Fail Test, F → Overage, "
                      "G → Wrong Parts Received, H → Other, "
                      "R → Reference Cable"):
            for code in DEFECT_CODE_ORDER:
                write_scrap(role, scrap_id, {"defect_code": code})
                observed[code] = _description(role, scrap_id)
            # One mismatch dict, asserted once, so a failure reports every
            # broken mapping rather than only the first.
            ctx.check("every defect code maps to its exact description",
                      {code: DEFECT_CODES[code] for code in DEFECT_CODE_ORDER},
                      observed)

        with ctx.step("Clear the code entirely and assert the description is "
                      "an empty string (not Unknown defect code)"):
            cleared = {}
            for label, value in (("defect_code = False", False),
                                 ("defect_code = ''", "")):
                write_scrap(role, scrap_id, {"defect_code": value})
                cleared[label] = _description(role, scrap_id)
            cleared["is the unknown fallback"] = \
                UNKNOWN_DEFECT_DESCRIPTION in set(cleared.values())
            ctx.check("an empty code yields an empty description, never the "
                      "fallback",
                      {"defect_code = False": EMPTY_DEFECT_DESCRIPTION,
                       "defect_code = ''": EMPTY_DEFECT_DESCRIPTION,
                       "is the unknown fallback": False},
                      cleared)

        with ctx.step("Export the nine code→description pairs as the "
                      "migration baseline for any future "
                      "stock.scrap.reason.tag conversion"):
            payload = {
                "tc_id": "DATAONE-TC180",
                "workflow": WORKFLOW,
                "target": ctx.env.key,
                "database": ctx.env.db,
                "odoo_version": ctx.env.version,
                "source": ("dto_tier_validation_scrap/models/"
                           "stock_scrap.py:52-62 · "
                           "dto_scrap/models/stock_scrap.py:75-85"),
                "observed_mapping": observed,
                "empty_code_description": EMPTY_DEFECT_DESCRIPTION,
                "unknown_code_description": UNKNOWN_DEFECT_DESCRIPTION,
                "v19_replace_candidate": {
                    "model": V19_TAG_MODEL,
                    "field": V19_TAG_FIELD,
                    "source": ("O19 addons/stock/models/"
                               "stock_scrap.py:56-59, 237-250"),
                    # Recorded, not asserted: whether the native tagging model
                    # exists on THIS target is the migration's input, not a
                    # property this case is about.
                    "present_on_target": rpc.model_exists(V19_TAG_MODEL),
                },
            }
            path = ctx.artifacts_dir / "tc180_defect_code_baseline.json"
            path.write_text(json.dumps(payload, indent=1, ensure_ascii=False),
                            encoding="utf-8")
            ctx.add_artifact(path, "log",
                             "TC180 defect-code migration baseline")
            ctx.log(f"baseline written: {path}")
            ctx.check("the exported baseline carries all nine observed pairs",
                      len(DEFECT_CODE_ORDER), len(payload["observed_mapping"]))

        with ctx.step("Expected final state: the scrap carries code B and an "
                      "employee name"):
            # The workbook's postcondition is "leave the scrap draft for
            # TC182". Hard rule 5 forbids cross-test fixture dependence, so
            # the state is ASSERTED here and the fixture is then swept;
            # TC182 builds its own.
            write_scrap(role, scrap_id, {"defect_code": "B"})
            row = read_scrap(role, scrap_id,
                             ["state", "defect_code",
                              "defect_code_description", "employee_name"])
            ctx.check("the scrap is a draft carrying B, Received Damaged and "
                      "the free-text employee",
                      {"state": "draft", "defect_code": "B",
                       "defect_code_description": DEFECT_CODES["B"],
                       "employee_name": employee_name},
                      {"state": row["state"],
                       "defect_code": blank(row["defect_code"]),
                       "defect_code_description":
                           blank(row["defect_code_description"]),
                       "employee_name": blank(row["employee_name"])})
    finally:
        try:
            drop_scraps(rpc, [scrap_id])
            sweep_wf022(rpc)
        except Exception:  # noqa: BLE001 — teardown must never raise
            pass


# ======================================================================= 181
@test_case(
    id="TEST-WF022-TC181",
    name="An unrecognised defect code yields *Unknown defect code* and is "
         "not rejected",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module=MODULE_TIER_SCRAP,
    priority="P2", kind="DATA", order=22181,
    description="Z, XX and 1 are all accepted with no constraint and each "
                "reads back the exact fallback Unknown defect code; nothing "
                "in the validation path gates on the code; the production "
                "residue bucket is sized and exported as a migration "
                "baseline.",
    traceability=trace("DATAONE-TC181"))
def test_tc181(ctx):
    rpc = ctx.adapter.rpc
    open_namespace(ctx)
    scrap_id = None
    try:
        with ctx.step("Log in as TD-U-05 and open the draft scrap"):
            check_scrap_extension(ctx)
            product_id = make_product(ctx, "TD-P-04", standard_price=12.50)
            # Its own quant, so step 7's availability gate is a real True and
            # no live product is ever involved.
            add_stock(ctx, product_id, stock_location(rpc), 5.0)
            scrap_id = make_scrap(ctx, product_id, qty=1.0)
            role = _role_session(ctx)
            row = read_scrap(role, scrap_id, ["state", "defect_code"])
            ctx.check("TD-U-05 opens a draft scrap with no code",
                      {"state": "draft", "defect_code": ""},
                      {"state": row["state"],
                       "defect_code": blank(row["defect_code"])})

        with ctx.step("Type Z into Defect Code and save"):
            raised, message = expect_error(write_scrap, role, scrap_id,
                                           {"defect_code": "Z"})
            ctx.log(f"write of 'Z': raised={raised} {message!r}")

        with ctx.step("Assert the save succeeds — there is no constraint"):
            declared = fields_get(role, "stock.scrap",
                                  ["defect_code"]).get("defect_code", {})
            ctx.log(f"defect_code declaration: {declared!r}")
            ctx.check("an unrecognised code is accepted, because defect_code "
                      "is a bare Char with nothing to reject it",
                      {"the write raised": False, "defect_code stored": "Z",
                       "required": False, "selection": None,
                       "relation": None},
                      {"the write raised": raised,
                       "defect_code stored": _code(role, scrap_id),
                       "required": bool(declared.get("required")),
                       "selection": declared.get("selection"),
                       "relation": declared.get("relation")})

        with ctx.step("Assert Defect Code Description reads exactly "
                      "Unknown defect code"):
            ctx.check("Z → Unknown defect code", UNKNOWN_DEFECT_DESCRIPTION,
                      _description(role, scrap_id))

        with ctx.step("Type XX (two characters) and save; assert the "
                      "description is again Unknown defect code"):
            raised, message = expect_error(write_scrap, role, scrap_id,
                                           {"defect_code": "XX"})
            ctx.log(f"write of 'XX': raised={raised} {message!r}")
            ctx.check("a two-character code is accepted and described as "
                      "unknown",
                      {"the write raised": False, "defect_code stored": "XX",
                       "description": UNKNOWN_DEFECT_DESCRIPTION},
                      {"the write raised": raised,
                       "defect_code stored": _code(role, scrap_id),
                       "description": _description(role, scrap_id)})

        with ctx.step("Type 1 and save; assert the same"):
            raised, message = expect_error(write_scrap, role, scrap_id,
                                           {"defect_code": "1"})
            ctx.log(f"write of '1': raised={raised} {message!r}")
            ctx.check("a numeric code is accepted and described as unknown",
                      {"the write raised": False, "defect_code stored": "1",
                       "description": UNKNOWN_DEFECT_DESCRIPTION},
                      {"the write raised": raised,
                       "defect_code stored": _code(role, scrap_id),
                       "description": _description(role, scrap_id)})

        with ctx.step("Assert the scrap can still be validated with an "
                      "unknown code — the code is not a gate"):
            row = read_scrap(role, scrap_id,
                             ["scrap_qty", "defect_code",
                              "defect_code_description"])
            declared = fields_get(role, "stock.scrap",
                                  ["defect_code"]).get("defect_code", {})
            # action_validate has exactly two gates — the zero-quantity guard
            # and check_available_qty() (O17 stock_scrap.py:196-220 /
            # O19 :211-235). Neither mentions defect_code, and nothing else in
            # core or in either DataOne module does either.
            gates = {
                "the unknown code is still set":
                    blank(row["defect_code_description"]),
                "scrap_qty clears the positive-quantity guard":
                    row["scrap_qty"] > 0,
                "check_available_qty() with the unknown code":
                    _available_gate(role, scrap_id),
                "defect_code is required": bool(declared.get("required")),
                "defect_code is a selection":
                    declared.get("selection") is not None,
            }
            ctx.check("nothing in the validation path gates on the defect "
                      "code",
                      {"the unknown code is still set":
                           UNKNOWN_DEFECT_DESCRIPTION,
                       "scrap_qty clears the positive-quantity guard": True,
                       "check_available_qty() with the unknown code": True,
                       "defect_code is required": False,
                       "defect_code is a selection": False},
                      gates)
            ctx.log(
                "action_validate() itself is deliberately NOT executed: a "
                "done scrap cannot be unlinked (O17 stock_scrap.py:107-110 / "
                "O19 :120-123) and validating here would permanently add a "
                "row to the very 'Unknown defect code' bucket step 8 "
                "measures, inflating the baseline on every rerun.")

        with ctx.step("Query all stock.scrap rows whose "
                      "defect_code_description equals Unknown defect code "
                      "and record the count as the production residue "
                      "baseline"):
            domain = [("defect_code_description", "=",
                       UNKNOWN_DEFECT_DESCRIPTION)]
            total = search_count(rpc, "stock.scrap", domain)
            fixture = search_count(rpc, "stock.scrap",
                                   domain + [("origin", "like", MARKER)])
            payload = {
                "tc_id": "DATAONE-TC181",
                "workflow": WORKFLOW,
                "target": ctx.env.key,
                "database": ctx.env.db,
                "odoo_version": ctx.env.version,
                "domain": [list(clause) for clause in domain],
                "rows_matching": total,
                "rows_belonging_to_this_execution": fixture,
                "production_residue_baseline": total - fixture,
                "note": ("Every row in this bucket needs a disposition "
                         "decision if the nine codes become "
                         f"{V19_TAG_MODEL} records "
                         "(O19 stock/models/stock_scrap.py:56-59, 237-250). "
                         "A zero baseline means the free-text tolerance was "
                         "never exercised and the REPLACE is cheap."),
            }
            path = ctx.artifacts_dir / "tc181_unknown_code_residue.json"
            path.write_text(json.dumps(payload, indent=1, ensure_ascii=False),
                            encoding="utf-8")
            ctx.add_artifact(path, "log",
                             "TC181 unknown-code residue baseline")
            ctx.log(f"residue baseline (this execution excluded): "
                    f"{total - fixture} of {total} matching rows")
            # Logged, not asserted as a number: an unscoped "exactly N" over
            # live data would break hard rule 5. What IS asserted is that the
            # domain answers at all — a non-stored compute without search=
            # cannot be searched, so this proves the column is real.
            ctx.check_true("defect_code_description is searchable by domain — "
                           "it is a STORED compute",
                           isinstance(total, int) and total >= fixture >= 0,
                           actual_desc=f"{total} matching rows, {fixture} of "
                                       f"them this execution's fixtures")

        with ctx.step("Expected final state: restore the code to B"):
            # The workbook hands the scrap to TC182; hard rule 5 forbids that,
            # so the restored state is asserted here and the fixture swept.
            write_scrap(role, scrap_id, {"defect_code": "B"})
            row = read_scrap(role, scrap_id,
                             ["state", "defect_code",
                              "defect_code_description"])
            ctx.check("the scrap is a draft carrying B and Received Damaged",
                      {"state": "draft", "defect_code": "B",
                       "defect_code_description": DEFECT_CODES["B"]},
                      {"state": row["state"],
                       "defect_code": blank(row["defect_code"]),
                       "defect_code_description":
                           blank(row["defect_code_description"])})
    finally:
        try:
            drop_scraps(rpc, [scrap_id])
            sweep_wf022(rpc)
        except Exception:  # noqa: BLE001 — teardown must never raise
            pass
