"""DATAONE-WF-024 — what the return wizard stamps on the new picking:
TC184 (the ``YYYY-nnn`` RMA number) and TC185 (the company vendor-refund
narration copied into ``note``).

Both cases are the same three lines of the fork, read from
``DTO-Odoo/3rd-addons/stock_picking_auto_create_lot/wizard/
stock_picking_return.py:21-25``::

    def _create_return(self):
        new_picking = super()._create_return()
        new_picking.rma_number = new_picking._get_rma_sequence()
        new_picking.note = self.env.company.vendor_refund_narration
        return new_picking

``:23`` is TC184; ``:24`` is TC185. Neither is a compute, neither is a
related, and nothing anywhere in the module depends on them — which is
exactly why TC185 step 6 (the note is written once and never refreshed) is a
fact about the product rather than a hopeful assertion.

The rules asserted here, with the source each one comes from
-------------------------------------------------------------
* ``models/stock_picking.py:9`` — ``rma_number = fields.Char(string="RMA
  Number")``. Stored, **not** required, **not** readonly at the model level.
* ``models/stock_picking.py:42-44`` — ``_get_rma_sequence()`` →
  ``self.env["ir.sequence"].next_by_code("rma_number")``. **PRIVATE**, so it
  is never called from a test; it is observed through the wizard's public
  confirm method and through the records it leaves behind.
* ``data/rma_sequence.xml:5-13`` — code ``rma_number``, prefix
  ``%(year)s-``, padding ``3``, ``number_next`` 1, ``number_increment`` 1,
  ``company_id eval="False"``. Prefix + padding is where ``YYYY-nnn`` comes
  from; ``company_id`` False is TC184 step 12.
* ``views/stock_picking.xml:9`` — ``<field name="rma_number"
  invisible="rma_number == False" readonly="1"/>``. TC184 step 9's
  "read-only in the UI" lives here and **only** here.
* ``odoo-17.0/odoo/addons/base/models/ir_sequence.py:241-243`` (v19
  ``:240-242``) — ``get_next_char(number_next)`` returns
  ``prefix + '%0<padding>d' % number_next + suffix`` and writes nothing.
  TC184 step 13 uses it, so the shared global sequence is never mutated.
* ``ir_sequence.py:202-207`` — for ``implementation='standard'`` the counter
  is the PostgreSQL sequence ``ir_sequence_%03d``; ``number_next`` does not
  move when a number is issued. ``:64-84`` / ``:100-110`` —
  ``number_next_actual`` is ``_predict_nextval`` over ``pg_sequences``, i.e.
  the value the next ``next_by_code`` will render.
* ``odoo-17.0/odoo/addons/base/views/ir_sequence_views.xml:31,38,82`` — the
  field the UI labels **"Next Number"** IS ``number_next_actual``. That is
  what a tester following TC184 step 2 writes down.
* v17 ``stock/wizard/stock_picking_return.py:80-92`` — the wizard line is
  prefilled with the delivered quantity minus what was already returned;
  ``:183`` ``create_returns`` is the public confirm method.
  v19 ``:132-137`` — the prefill is the literal ``0`` (``:135``); ``:210``
  ``action_create_returns`` is the renamed public method, which is what the
  fork's own xpath anchors on (``wizard/stock_picking_return_views.xml:12``).
  The method name is resolved by ``common.return_confirm_method``, which
  probes the delivered arch — never by an ``if version`` in a body here.
* ``dto_account/models/res_company.py:51-54`` —
  ``vendor_refund_narration = fields.Html(string='RMA Term and Condition',
  default=_default_vendor_refund_narration)``; the default HTML is
  ``:11-49``. TC185's TD-CO-06.
* ``stock/models/stock_picking.py:403`` (v17) / ``:559`` (v19) —
  ``note = fields.Html('Notes')``, the field the narration is copied into.
* ``__manifest__.py:14`` — ``"depends": ["stock"]`` and nothing else, while
  ``wizard/stock_picking_return.py:24`` reads a ``dto_account`` field at
  return time. WF-024 E1, and TC185 step 10's subject.
* ``odoo/addons/base/models/ir_module.py:293`` — ``dependencies_id``;
  ``:948-954`` — ``ir.module.module.dependency.name``. How the undeclared
  dependency is measured on the target instead of by reading the manifest.

Adaptations, each recorded in docs/WF-024_AUTOMATION_PLAN.md §Adaptations
------------------------------------------------------------------------
1. **TC184 steps 2 and 10 compare ``number_next_actual``** (plan item 2).
   ``number_next`` cannot move for ``implementation='standard'``, so
   asserting "``number_next`` incremented by 1" would assert something the
   mechanism forbids. Both figures are captured and logged; the comparison
   uses the column that actually advances — and which the ir.sequence form
   presents to the tester as "Next Number".
2. **TC184 step 13 renders through ``get_next_char``** (plan item 4).
   Writing ``number_next`` on the live global ``rma_number`` sequence would
   modify a pre-existing business record, which hard rule 3 forbids
   outright. The workbook's scratch fixture is still built — mirroring the
   live sequence's own prefix and padding — and the live sequence's
   rendering is read too, because ``get_next_char`` writes nothing.
3. **TC184 step 9 proves the read-only is view-level** (plan item 5): the
   arch modifier is asserted, and ``fields_get``'s model-level ``readonly``
   is logged beside it. A real browser read-only check is HttpCase work.
4. **TC184 steps 8 and 13 measure the year the way the SEQUENCE measures
   it** (plan item 19). ``%(year)s`` is interpolated from
   ``datetime.now(pytz.timezone(self._context.get('tz') or 'UTC'))``
   (``ir_sequence.py:209-239``, the assignment at ``:214``) — the calling
   RPC **session's** timezone, inside the Odoo process. Neither the
   platform host's clock nor ``fields.Date.today()`` is the right
   comparator: the latter is plain ``date.today()``
   (``odoo/fields.py:2138-2143``), the Odoo host's local date with no
   timezone applied, so a UTC server and an ``America/Chicago`` session at
   31 Dec 20:00 local would disagree by a year and both steps would fail
   for a non-defect (convention rule 5). ``_sequence_year`` therefore reads
   the year out of the live sequence's own ``get_next_char`` rendering, on
   the session that issued the number; step 13 compares its two renderings
   against the year interpolated on the session that produced them. The
   fallback is the return picking's ``create_date``, which the server
   wrote.
5. **TC185 step 10 is replaced by its static equivalent** (plan item 6). A
   scratch database without ``dto_account`` cannot be provisioned —
   AUTOMATION_CONVENTIONS says "never start a server, run a suite, or touch
   a database". What is asserted instead says the same thing and is fully
   verifiable on the target: the module's declared dependencies do not
   include ``dto_account`` while ``res.company.vendor_refund_narration``
   exists. The ``AttributeError`` itself is logged and stays a Phase-0a
   manual item.
6. **TC185 steps 5-9 write a PRE-EXISTING business record. This is an
   AUTOMATION_CONVENTIONS hard-rule-3 EXCEPTION, not an adaptation, and it
   is awaiting the conventions owner's decision** (plan item 7). Hard rule 3
   reads "Never modify pre-existing business records" and carries no
   sanctioned-mutation clause, so calling this an adaptation was wrong;
   it is recorded here and in the plan as an open exception instead.

   What the case actually does: ``res.company.vendor_refund_narration`` is
   the only pre-existing business value this suite writes. It is
   snapshotted first, replaced with a token-marked value, restored by
   step 9, the restoration **asserted**, and restored *again* by a teardown
   that cannot raise, which logs ``[ALERT]`` carrying the original value if
   even that fails. The exposure window is real while it is open: every
   return created on the database meanwhile copies the token-marked terms
   into its ``note`` (``wizard/stock_picking_return.py:24``) and every
   vendor credit note its narration (F156). The window is therefore held to
   one wizard create + confirm — **the second source delivery is built in
   the precondition step, before the mutation** — and the case must be run
   on the dedicated ``_qa`` clone.

   The two ways out, neither of which a suite may take unilaterally: an
   explicit hard-rule-3 clause for a restorable single-field company
   setting on a dedicated clone, or a second, token-named ``res.company``
   run as its own user (``_create_return`` reads ``self.env.company``,
   ``wizard/stock_picking_return.py:24``) — which trades this exposure for
   a company whose auto-created warehouse, picking types and sequences the
   sweep cannot remove. Escalated in the plan; not decided here.
7. **Equality in TC185 is between two values read back over the same RPC
   session**, never against the Python literal in ``res_company.py``: both
   fields are ``fields.Html`` and the literal has not been through the
   sanitizer.

Both cases are driven as **TD-U-03**, a disposable internal user in
``stock.group_stock_user`` — ``stock/security/ir.model.access.csv:64-65``
grants that group create/write on ``stock.return.picking`` and its lines, so
the whole wizard path is exercised with the rights the workbook names.
Fixture building, the sequence reads and the company write stay on the
platform's own administrative session, which is where those rights live
(``base/security/ir.model.access.csv:28-29,41-44,22-23``).

The fixtures are deliveries with **no** ``sale_id``, so validating them
fires neither ``dto_sale_stock``'s ``force_send=True`` mail automation nor
its auto-posted invoice (``common.make_delivery``) — convention rule 4 needs
nothing further here.

EXPECTED v17 OUTCOME: PASS — TC184.
EXPECTED v19 OUTCOME: FAIL at step 4 — TC184. v19's
``_prepare_stock_return_picking_line_vals_from_move`` returns
``'quantity': 0``
(``odoo-19.0/addons/stock/wizard/stock_picking_return.py:135``), so the
wizard does **not** "list the returnable quantities". The workbook's
expectation describes the v17/target behaviour and is implemented as
written, not adapted; the failure is the finding.

EXPECTED v17 OUTCOME: PASS — TC185.
EXPECTED v19 OUTCOME: PASS — TC185. ``_create_return`` is the v19 override
point and the assignment at ``:24`` is version-neutral; the exposure the
workbook names (the undeclared ``dto_account`` dependency becoming a
load-order problem) is asserted statically in step 10 on both versions.
"""
from adapters.base import OdooRPCError
from framework.registry import test_case
from tests.wf024.common import (MODULE, NARRATION_FIELD, NARRATION_FRAGMENTS,
                                RMA_NUMBER_PATTERN, RMA_NUMBER_RE,
                                RMA_OVERFLOW_PROBE, RMA_OVERFLOW_RE,
                                RMA_SEQUENCE_CODE, STOCK_USER_GROUP,
                                WIZARD_MODEL, WORKFLOW, WORKFLOW_NAME,
                                action_res_id, arch_field_attrs,
                                current_company_id, ensure_partner,
                                ensure_user_in_groups,
                                field_is_readonly_in_model, fixture_token,
                                m2o_id, make_delivery, make_product,
                                make_scratch_sequence, open_namespace,
                                open_return_wizard, picking_form_arch,
                                require_rma_module, require_rma_sequence,
                                require_vendor_narration,
                                return_confirm_method, return_of, rpc_as,
                                rma_sequence_row, safe_sweep,
                                sequence_preview,
                                set_return_quantities, trace, wizard_lines)

#: Two products on the source delivery, so "one line per returnable move"
#: (TC184 step 4) is a real assertion and not a tautology on a single move.
PRODUCT_A_QTY = 4.0
PRODUCT_B_QTY = 7.0
#: One unit returned — the workbook's "set a return quantity", singular.
RETURN_QTY = 1.0


# =====================================================================
# Local helpers — none of these exist in tests/wf024/common.py
# =====================================================================
def _inventory_user_session(ctx):
    """TD-U-03: a disposable internal user in ``stock.group_stock_user``.

    Returns ``(user_id, login, rpc)``. BLOCKS with a precise reason when the
    session cannot be opened, so an authentication problem is never reported
    as an RMA defect. Running the wizard as the platform's own administrator
    instead would silently change which record rules apply.
    """
    try:
        user_id, login = ensure_user_in_groups(ctx, "inv", [STOCK_USER_GROUP])
        return user_id, login, rpc_as(ctx.env, login)
    except OdooRPCError as exc:
        ctx.blocked(
            f"Could not open a TD-U-03 (Inventory User) session on "
            f"{ctx.env.key} (db={ctx.env.db}): {exc}. Both cases are written "
            f"for a {STOCK_USER_GROUP} member — stock/security/"
            "ir.model.access.csv:64-65 is what grants that group create and "
            "write on stock.return.picking and its lines — and running them "
            "as the platform administrator would exercise a different rule "
            "set.")


def _sequence_year(ctx, rpc, seq_id, picking_id) -> str:
    """The calendar year the **sequence itself** interpolates, 4 chars.

    ``%(year)s`` resolves to ``effective_date.strftime('%Y')`` where
    ``effective_date`` is ``datetime.now(pytz.timezone(
    self._context.get('tz') or 'UTC'))`` — ``_interpolation_dict`` inside
    ``_get_prefix_suffix`` (v17 ``ir_sequence.py:209-239``, the ``now =
    range_date = effective_date = …`` line at ``:214``; v19 ``:207-238``).
    So the prefix carries the year of **the RPC session that issued the
    number**, in that session's timezone.

    It is therefore measured the way the sequence measures it: by asking the
    live sequence to render a number through ``get_next_char``, which is
    public, writes nothing (v17 ``:241-243``, v19 ``:240-242``) and returns
    ``<interpolated prefix><padded n>``. ``rpc`` is deliberately the session
    that ISSUED the number under test, so the interpolation runs under the
    same ``tz``; ``base.group_user`` has read on ``ir.sequence`` in both
    trees (``odoo/addons/base/security/ir.model.access.csv:28`` on v17,
    ``:29`` on v19), so a TD-U-03 session can render it.

    **Not** ``fields.Date.today()``. That is plain ``date.today()`` (v17
    ``odoo/fields.py:2138-2143``) — the Odoo *host's* local date with no
    timezone applied — so it disagrees with the rendered prefix whenever the
    host clock and the session timezone straddle a New Year boundary: a UTC
    server with an ``America/Chicago`` session at 31 Dec 20:00 local issues
    ``2026-001`` while ``date.today()`` already reads 2027, and steps 8 and
    13 would both fail for a reason that is not a product defect
    (convention rule 5).

    Falls back to the return picking's own ``create_date`` — server-written,
    always present, UTC — when the rendering is unavailable. Both are
    logged.
    """
    rendered = None
    try:
        rendered = sequence_preview(rpc, seq_id, RMA_OVERFLOW_PROBE)
    except OdooRPCError as exc:
        ctx.log(f"[warn] ir.sequence.get_next_char on the issuing session "
                f"failed: {exc}")
    if rendered and "-" in rendered:
        year = rendered.partition("-")[0]
        ctx.log(f"the year the live {RMA_SEQUENCE_CODE} sequence "
                f"interpolates for the issuing session = {year!r} "
                f"(from its own rendering {rendered!r})")
        return year
    created = ctx.adapter.rpc.read("stock.picking", [picking_id],
                                   ["create_date"])[0]["create_date"]
    ctx.log(f"[note] the sequence rendering was unavailable; the year is "
            f"taken from the return picking's create_date = {created!r}, "
            "which the server wrote in UTC")
    return str(created)[:4]


def _serial(number) -> int:
    """The ``nnn`` half of ``YYYY-nnn`` as an int; -1 when unparseable."""
    try:
        return int(str(number).split("-", 1)[1])
    except (AttributeError, IndexError, ValueError):
        return -1


def _year(number) -> str:
    """The ``YYYY`` half of ``YYYY-nnn``; '' when unparseable."""
    return str(number).split("-", 1)[0] if number else ""


def _module_dependencies(rpc, module_name):
    """The module's declared ``depends``, read off the target.

    ``ir.module.module.dependencies_id`` is a one2many onto
    ``ir.module.module.dependency``, whose ``name`` is the declared module
    name (``odoo/addons/base/models/ir_module.py:293``, ``:948-954``). Both
    models are ``base.group_system`` only
    (``base/security/ir.model.access.csv:22-23``), so this runs on the
    platform's administrative session and never on TD-U-03.

    Returns a sorted list of names, or ``(None, message)``-style None plus a
    logged reason when the row cannot be read.
    """
    rows = rpc.search_read("ir.module.module", [("name", "=", module_name)],
                           ["name", "state", "dependencies_id"], limit=1)
    if not rows:
        return None
    dep_ids = rows[0].get("dependencies_id") or []
    if not dep_ids:
        return []
    deps = rpc.read("ir.module.module.dependency", dep_ids, ["name"])
    return sorted(d["name"] for d in deps)


# =====================================================================
# TC184
# =====================================================================
@test_case(
    id="TEST-WF024-TC184",
    name="A return created through the wizard is numbered YYYY-nnn",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="stock_picking_auto_create_lot",
    priority="P1", kind="API", order=24184,
    description="A wizard return is stamped with an rma_number matching "
                "^\\d{4}-\\d{3}$ whose prefix is the server's calendar year; "
                "the counter advances by exactly 1 and the next return is "
                "the immediate successor; the sequence is global "
                "(company_id=False); the read-only is a view modifier only; "
                "and padding 3 renders <year>-1000 once the serial passes "
                "999.",
    traceability=trace("DATAONE-TC184"))
def test_tc184(ctx):
    require_rma_module(ctx)
    seq_id = require_rma_sequence(ctx)
    # _create_return reads env.company.vendor_refund_narration on the very
    # same line that stamps the number (wizard/stock_picking_return.py:24),
    # so without dto_account NO return can be created at all and every
    # assertion below would fail for the wrong reason.
    require_vendor_narration(ctx)

    rpc = ctx.adapter.rpc
    open_namespace(ctx)
    user_id = None
    scratch_seq_id = None
    try:
        with ctx.step("Precondition: a done outgoing delivery for TD-PA-01 "
                      "with two delivered moves"):
            partner_id = ensure_partner(rpc, "Customer")
            product_a = make_product(ctx, "P-A")
            product_b = make_product(ctx, "P-B")
            delivery_id = make_delivery(
                ctx, [(product_a, PRODUCT_A_QTY), (product_b, PRODUCT_B_QTY)],
                partner_id=partner_id, label="DELIVERY-1")
            source = rpc.read("stock.picking", [delivery_id],
                              ["name", "state", "picking_type_code"])[0]
            ctx.log(f"source delivery {source!r}")
            ctx.check("the source delivery is done", "done", source["state"])

        with ctx.step("Log in as TD-U-03 and open the done delivery"):
            user_id, login, user_rpc = _inventory_user_session(ctx)
            row = user_rpc.read("stock.picking", [delivery_id],
                                ["name", "state", "rma_number"])[0]
            ctx.log(f"TD-U-03 = {login} (uid {user_id}); sees {row!r}")
            ctx.check("TD-U-03 opens the delivery and it is done", "done",
                      row["state"])
            ctx.check("the source delivery itself carries no RMA number",
                      False, row["rma_number"])

        with ctx.step("Record next_before = sequence.number_next"):
            seq_before = rma_sequence_row(ctx)
            # number_next_actual is the figure the ir.sequence form labels
            # "Next Number" (ir_sequence_views.xml:31,38,82) and the one
            # next_by_code will actually render; number_next cannot move for
            # implementation='standard' (ir_sequence.py:202-207). Both are
            # recorded; the comparison in step 10 uses the live one.
            next_before = seq_before["number_next_actual"]
            ctx.log(f"ir.sequence[{RMA_SEQUENCE_CODE}] = {seq_before!r}")
            ctx.check_true(
                "the sequence has a next number to issue",
                isinstance(next_before, int) and next_before > 0,
                actual_desc=f"number_next_actual={next_before!r}, "
                            f"number_next={seq_before['number_next']!r}, "
                            f"implementation="
                            f"{seq_before['implementation']!r}")

        with ctx.step("Press Return"):
            wizard_id = open_return_wizard(user_rpc, delivery_id)
            ctx.check_true("the return wizard opened for the delivery",
                           bool(wizard_id),
                           actual_desc=f"{WIZARD_MODEL} id={wizard_id!r}")

        with ctx.step("Assert the wizard lists one line per returnable move "
                      "with the returnable quantities"):
            lines = wizard_lines(user_rpc, wizard_id)
            observed = {m2o_id(line["product_id"]): line["quantity"]
                        for line in lines}
            expected = {product_a: PRODUCT_A_QTY, product_b: PRODUCT_B_QTY}
            ctx.log(f"wizard lines: {lines!r}")
            ctx.check("one wizard line per returnable move", len(expected),
                      len(lines))
            # v17 prefills delivered-minus-already-returned
            # (stock/wizard/stock_picking_return.py:80-92); v19 prefills 0
            # (:135). This assertion is the workbook's, unadapted, and is
            # EXPECTED TO FAIL on v19.
            ctx.check("the prefilled quantity per product is the returnable "
                      "quantity", expected, observed)

        with ctx.step("Set a return quantity and press Return"):
            applied = set_return_quantities(
                user_rpc, wizard_id,
                {product_a: RETURN_QTY, product_b: 0.0})
            ctx.log(f"return quantities written: {applied!r}")
            method = return_confirm_method(ctx)
            action = user_rpc.call(WIZARD_MODEL, method, [wizard_id])
            ctx.log(f"{WIZARD_MODEL}.{method}({wizard_id}) -> {action!r}")
            ctx.check("the confirm action opens a stock.picking",
                      "stock.picking", (action or {}).get("res_model"))

        with ctx.step("Assert a new stock.picking was created"):
            new_id = action_res_id(action)
            returned = return_of(user_rpc, delivery_id)
            ctx.log(f"return picking: {returned!r}")
            ctx.check_true("the action carries the new picking's id",
                           bool(new_id), actual_desc=repr(new_id))
            ctx.check_true("a picking whose return_id is the delivery exists",
                           returned is not None, actual_desc=repr(returned))
            first_return_id = returned["id"] if returned else None
            ctx.check("the new picking is the one the action opened", new_id,
                      first_return_id)
            # The origin is core's translatable "Return of %s" (v17
            # stock/wizard/stock_picking_return.py:119, v19 :155), so the
            # source picking's NAME is asserted rather than the English
            # sentence around it.
            ctx.check_true("its origin names the source delivery",
                           source["name"] in (returned["origin"] or ""),
                           actual_desc=repr(returned["origin"]))

        with ctx.step("Assert picking.rma_number is set and matches the "
                      "regex ^\\d{4}-\\d{3}$"):
            rma_number = returned["rma_number"]
            ctx.check_true("rma_number is set on the return picking",
                           bool(rma_number), actual_desc=repr(rma_number))
            ctx.check(f"rma_number matches {RMA_NUMBER_PATTERN}", True,
                      bool(RMA_NUMBER_RE.match(rma_number or "")))

        with ctx.step("Assert the four-digit prefix equals the current "
                      "calendar year"):
            # Measured on user_rpc — the session that issued the number —
            # because the prefix is interpolated in the CALLING session's
            # timezone (ir_sequence.py:214), not on the platform host.
            year = _sequence_year(ctx, user_rpc, seq_id, first_return_id)
            ctx.log(f"rma_number={rma_number!r}; calendar year as the "
                    f"sequence interpolates it for this session={year!r} "
                    f"(data/rma_sequence.xml:8 prefix "
                    f"{seq_before['prefix']!r})")
            ctx.check("the rma_number prefix is the server's calendar year",
                      year, _year(rma_number))

        with ctx.step("Assert the field is read-only in the UI"):
            attrs = arch_field_attrs(picking_form_arch(ctx), "rma_number")
            readonly_values = sorted({node.get("readonly") for node in attrs})
            ctx.log(f"<field name='rma_number'> in the composed "
                    f"stock.picking form: {attrs!r}")
            ctx.check_true("rma_number appears in the composed form arch",
                           bool(attrs), actual_desc=f"{len(attrs)} node(s)")
            ctx.check("every rma_number field node carries readonly=\"1\" "
                      "(views/stock_picking.xml:9)", ["1"], readonly_values)
            orm_readonly = field_is_readonly_in_model(rpc, "stock.picking",
                                                      "rma_number")
            ctx.log(
                "stock.picking.rma_number is NOT readonly at the model level "
                f"(fields_get readonly={orm_readonly!r}; "
                "models/stock_picking.py:9 declares a plain Char). The "
                "read-only this step asserts is a client-side view modifier "
                "and the ORM does not enforce it — recorded, because it is "
                "the same shape as WF-024 E2.")

        with ctx.step("Assert sequence.number_next incremented by exactly 1"):
            seq_after = rma_sequence_row(ctx)
            ctx.log(
                f"number_next {seq_before['number_next']!r} -> "
                f"{seq_after['number_next']!r} (it does not move for "
                f"implementation={seq_after['implementation']!r}, "
                "ir_sequence.py:202-207); number_next_actual "
                f"{next_before!r} -> {seq_after['number_next_actual']!r}")
            ctx.check(
                "the counter advanced by exactly 1, and the number issued is "
                "the one it had predicted",
                {"next number after the return": next_before + 1,
                 "serial issued": next_before},
                {"next number after the return":
                    seq_after["number_next_actual"],
                 "serial issued": _serial(rma_number)})

        with ctx.step("Create a second return and assert its number is the "
                      "immediate successor"):
            delivery_2 = make_delivery(ctx, [(product_a, PRODUCT_A_QTY)],
                                       partner_id=partner_id,
                                       label="DELIVERY-2")
            wizard_2 = open_return_wizard(user_rpc, delivery_2)
            set_return_quantities(user_rpc, wizard_2, {product_a: RETURN_QTY})
            action_2 = user_rpc.call(WIZARD_MODEL, return_confirm_method(ctx),
                                     [wizard_2])
            ctx.log(f"second confirm -> {action_2!r}")
            second = return_of(user_rpc, delivery_2)
            number_2 = (second or {}).get("rma_number")
            ctx.log(f"second return picking: {second!r}")
            ctx.check_true(f"the second rma_number matches "
                           f"{RMA_NUMBER_PATTERN}",
                           bool(RMA_NUMBER_RE.match(number_2 or "")),
                           actual_desc=repr(number_2))
            ctx.check("the second return's number is the immediate successor",
                      {"year": year, "serial": _serial(rma_number) + 1},
                      {"year": _year(number_2), "serial": _serial(number_2)})

        with ctx.step("Assert the sequence has company_id = False — the "
                      "numbering is global, not per company"):
            ctx.check(f"ir.sequence[{RMA_SEQUENCE_CODE}].company_id", False,
                      seq_after["company_id"])
            ctx.log(
                "Recorded as the documented v17 behaviour: "
                "data/rma_sequence.xml:12 sets company_id eval=\"False\", so "
                "one global counter serves every company and two companies "
                "share a single YYYY-nnn series. F087 recommends deciding "
                "during the port whether it should become per-company — a "
                "decision, not a test failure.")

        with ctx.step("Set number_next to 1000 in a scratch fixture, create "
                      "a return, and assert the number renders <year>-1000"):
            # The live rma_number sequence is NEVER written: hard rule 3.
            # The scratch fixture mirrors its prefix and padding exactly, and
            # get_next_char renders without consuming on either
            # (ir_sequence.py:241-243).
            scratch_seq_id = make_scratch_sequence(
                rpc, "OVERFLOW", prefix=seq_after["prefix"],
                padding=seq_after["padding"], number_next=RMA_OVERFLOW_PROBE)
            rendered = sequence_preview(rpc, scratch_seq_id,
                                        RMA_OVERFLOW_PROBE)
            live = sequence_preview(rpc, seq_id, RMA_OVERFLOW_PROBE)
            ctx.log(f"scratch sequence {scratch_seq_id} renders "
                    f"{rendered!r}; the live {RMA_SEQUENCE_CODE} sequence "
                    f"renders {live!r} for the same number_next "
                    f"{RMA_OVERFLOW_PROBE}")
            # Both previews above were rendered on THIS (administrative)
            # session, so the year to compare them against is the one this
            # session interpolates — read from the live sequence's own
            # rendering rather than from step 8's, which was measured on the
            # TD-U-03 session. The two differ only if the two sessions'
            # timezones straddle a New Year boundary; both are logged.
            render_year = (live or "").partition("-")[0]
            ctx.log(f"year interpolated for the issuing session (step 8) = "
                    f"{year!r}; for this session = {render_year!r}")
            ctx.check("padding 3 renders four digits at 1000",
                      f"{render_year}-{RMA_OVERFLOW_PROBE}", rendered)
            ctx.check("the live RMA sequence renders the same overflow",
                      rendered, live)
            ctx.check(f"the overflowed number no longer matches "
                      f"{RMA_NUMBER_PATTERN}", False,
                      bool(RMA_NUMBER_RE.match(rendered or "")))
            ctx.check_true("it takes the four-or-more-digit overflow shape",
                           bool(RMA_OVERFLOW_RE.match(rendered or "")),
                           actual_desc=repr(rendered))
            ctx.log(
                "Recorded as a known limit (WF-024 E4): the 1000th RMA of a "
                "year renders <year>-1000, four digits, breaking the "
                "fixed-width assumption every downstream reader of the "
                "number makes. get_next_char is "
                "'%%0%sd' %% padding %% number_next (ir_sequence.py:243), "
                "which pads but never truncates. Capture the figure in the "
                "Phase-0a sequences baseline so numbering continues without "
                "collision after the upgrade.")
    finally:
        with ctx.step("Cleanup: drop the scratch sequence, archive TD-U-03 "
                      "and sweep the fixtures"):
            try:
                if scratch_seq_id:
                    rpc.unlink("ir.sequence", [scratch_seq_id])
            except Exception as exc:                        # noqa: BLE001
                ctx.log(f"[warn] scratch sequence {scratch_seq_id} not "
                        f"removed: {exc}")
            try:
                if user_id:
                    rpc.write("res.users", [user_id], {"active": False})
            except Exception as exc:                        # noqa: BLE001
                ctx.log(f"[warn] TD-U-03 user {user_id} not archived: {exc}")
            safe_sweep(ctx)


# =====================================================================
# TC185
# =====================================================================
@test_case(
    id="TEST-WF024-TC185",
    name="The return picking's note is the company vendor-refund narration",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="stock_picking_auto_create_lot",
    priority="P1", kind="API", order=24185,
    description="The return picking's note is a byte-for-byte copy of "
                "res.company.vendor_refund_narration taken at creation "
                "time; changing the company value afterwards leaves the "
                "existing return untouched (BR-2) and only the next return "
                "carries the new terms; and the dto_account dependency the "
                "copy relies on is undeclared in the module manifest.",
    traceability=trace("DATAONE-TC185"))
def test_tc185(ctx):
    require_rma_module(ctx)
    require_vendor_narration(ctx)

    rpc = ctx.adapter.rpc
    open_namespace(ctx)
    user_id = None
    company_id = None
    original = None
    mutated = False
    restored = False
    try:
        with ctx.step("Precondition: a done outgoing delivery for TD-PA-01"):
            partner_id = ensure_partner(rpc, "Customer")
            product_id = make_product(ctx, "P-A")
            delivery_id = make_delivery(ctx, [(product_id, PRODUCT_A_QTY)],
                                        partner_id=partner_id,
                                        label="DELIVERY-1")
            # Step 7's source delivery is built HERE, before the company
            # narration is touched, so that the only work done while the
            # pre-existing value is replaced is opening and confirming one
            # wizard. Building it at step 7 instead would hold the mutation
            # open across a stock move, a validation and a quant write — see
            # the rule-3 note in this module's adaptation 6.
            delivery_2 = make_delivery(ctx, [(product_id, PRODUCT_A_QTY)],
                                       partner_id=partner_id,
                                       label="DELIVERY-2")
            source = rpc.read("stock.picking", [delivery_id],
                              ["name", "state"])[0]
            source_2 = rpc.read("stock.picking", [delivery_2],
                                ["name", "state"])[0]
            ctx.log(f"source delivery {source!r}; second source delivery "
                    f"{source_2!r}")
            ctx.check("both source deliveries are done",
                      {"first": "done", "second": "done"},
                      {"first": source["state"], "second": source_2["state"]})

        with ctx.step("Log in as TD-U-03 and record narration = "
                      "env.company.vendor_refund_narration"):
            user_id, login, user_rpc = _inventory_user_session(ctx)
            # env.company inside the wizard is the SESSION user's company, so
            # the narration is read from — and later written on — the company
            # TD-U-03 actually belongs to, not the platform admin's.
            company_id = current_company_id(user_rpc)
            original = user_rpc.read("res.company", [company_id],
                                     [NARRATION_FIELD])[0][NARRATION_FIELD]
            ctx.log(f"TD-U-03 = {login} (uid {user_id}); company "
                    f"{company_id}; {NARRATION_FIELD} = {original!r}")
            if not original:
                ctx.blocked(
                    f"res.company[{company_id}].{NARRATION_FIELD} is empty "
                    f"on {ctx.env.key} (db={ctx.env.db}). TD-CO-06 requires "
                    "the default RMA terms HTML shipped by dto_account "
                    "(dto_account/models/res_company.py:11-49) to be set "
                    "before this case runs: with an empty narration every "
                    "return's note would be empty too and steps 4, 6 and 8 "
                    "would pass vacuously.")
            present = [f for f in NARRATION_FRAGMENTS if f in original]
            ctx.log(
                f"TD-CO-06 default-text fragments present: {present} "
                f"({len(present)} of {len(NARRATION_FRAGMENTS)}). Recorded, "
                "not asserted — a company may legitimately have customised "
                "its RMA terms, and what steps 4/6/8 test is the copy, not "
                "the wording.")
            ctx.check_true("the company carries a non-empty RMA narration",
                           bool(original),
                           actual_desc=f"{len(original)} characters of HTML")

        with ctx.step("Open the done delivery and press Return"):
            wizard_id = open_return_wizard(user_rpc, delivery_id)
            ctx.check_true("the return wizard opened for the delivery",
                           bool(wizard_id),
                           actual_desc=f"{WIZARD_MODEL} id={wizard_id!r}")

        with ctx.step("Set a return quantity and press Return"):
            applied = set_return_quantities(user_rpc, wizard_id,
                                            {product_id: RETURN_QTY})
            ctx.log(f"return quantities written: {applied!r}")
            action = user_rpc.call(WIZARD_MODEL, return_confirm_method(ctx),
                                   [wizard_id])
            ctx.log(f"confirm -> {action!r}")
            first_return = return_of(user_rpc, delivery_id)
            ctx.log(f"first return picking: {first_return!r}")
            ctx.check_true("a return picking was created",
                           first_return is not None,
                           actual_desc=repr(first_return))
            first_return_id = first_return["id"] if first_return else None

        with ctx.step("Assert the new return picking's note equals narration "
                      "exactly, including markup"):
            # Both sides are read back over the SAME session, so the
            # comparison is between two sanitizer outputs and never against
            # the Python literal in res_company.py.
            ctx.check("stock.picking.note is the company narration, byte for "
                      "byte (wizard/stock_picking_return.py:24)",
                      original, first_return["note"])

        with ctx.step("Change res.company.vendor_refund_narration to a "
                      "different string"):
            replacement = (f"<p>{fixture_token()} TC185 replacement RMA "
                           "terms</p>")
            ctx.log(
                f"[mutation] writing res.company[{company_id}]."
                f"{NARRATION_FIELD}; the original is held for restoration by "
                "step 9 and by a teardown that cannot raise. This is the "
                "only pre-existing business value WF-024 writes.")
            rpc.write("res.company", [company_id],
                      {NARRATION_FIELD: replacement})
            mutated = True
            new_narration = user_rpc.read(
                "res.company", [company_id],
                [NARRATION_FIELD])[0][NARRATION_FIELD]
            ctx.log(f"{NARRATION_FIELD} is now {new_narration!r}")
            ctx.check_true("the company narration now differs from the "
                           "original", new_narration != original,
                           actual_desc=repr(new_narration))

        with ctx.step("Assert the existing return picking's note is "
                      "unchanged — the value is written at creation and "
                      "never refreshed (BR-2)"):
            note_now = user_rpc.read("stock.picking", [first_return_id],
                                     ["note"])[0]["note"]
            ctx.check("the first return still carries the ORIGINAL "
                      "narration", original, note_now)
            ctx.log(
                "This is the assertion a naive port breaks: making note a "
                "related or a computed field would look like an improvement "
                "and would silently rewrite the terms on every historical "
                "return. wizard/stock_picking_return.py:24 is a plain "
                "assignment and nothing in the module declares an "
                "@api.depends on stock.picking.note.")

        with ctx.step("Create a second return from another done delivery"):
            # The delivery itself was built in the precondition step, before
            # the mutation, so the window during which the company carries
            # the token-marked terms is one wizard create + confirm.
            wizard_2 = open_return_wizard(user_rpc, delivery_2)
            set_return_quantities(user_rpc, wizard_2, {product_id: RETURN_QTY})
            action_2 = user_rpc.call(WIZARD_MODEL, return_confirm_method(ctx),
                                     [wizard_2])
            ctx.log(f"second confirm -> {action_2!r}")
            second_return = return_of(user_rpc, delivery_2)
            ctx.log(f"second return picking: {second_return!r}")
            ctx.check_true("a second return picking was created",
                           second_return is not None,
                           actual_desc=repr(second_return))

        with ctx.step("Assert the second return's note equals the new "
                      "narration"):
            ctx.check("the second return carries the NEW narration",
                      new_narration, second_return["note"])

        with ctx.step("Restore the original narration"):
            rpc.write("res.company", [company_id],
                      {NARRATION_FIELD: original})
            restored = True
            back = user_rpc.read("res.company", [company_id],
                                 [NARRATION_FIELD])[0][NARRATION_FIELD]
            ctx.check(f"res.company[{company_id}].{NARRATION_FIELD} is "
                      "restored", original, back)

        with ctx.step("In a scratch database without dto_account, attempt a "
                      "return and record the exact exception; assert it is "
                      "an AttributeError on vendor_refund_narration"):
            # A second database cannot be provisioned from here —
            # AUTOMATION_CONVENTIONS: "never start a server, run a suite, or
            # touch a database". What IS asserted on this target is the same
            # fact the scratch database would demonstrate: the dependency is
            # real and it is undeclared.
            message = ""
            try:
                declared = _module_dependencies(rpc, MODULE)
            except OdooRPCError as exc:
                declared, message = None, str(exc)
            ctx.log(f"{MODULE} declares depends = {declared!r} "
                    f"(__manifest__.py:14){f'; {message}' if message else ''}")
            ctx.check_true(
                f"{MODULE}'s declared dependencies are readable on the "
                "target", declared is not None,
                actual_desc=message or f"no ir.module.module row for "
                                       f"{MODULE}")
            ctx.check("dto_account is NOT among the module's declared "
                      "dependencies", False, "dto_account" in (declared or []))
            ctx.check_true(
                f"res.company.{NARRATION_FIELD} nevertheless exists on the "
                "target, so the return above could be created at all",
                rpc.field_exists("res.company", NARRATION_FIELD),
                actual_desc="present (contributed by dto_account)")
            ctx.log(
                "Documented, not executed (Phase-0a manual item): on a "
                "database WITHOUT dto_account, "
                "wizard/stock_picking_return.py:24 evaluates "
                "self.env.company.vendor_refund_narration against a "
                "res.company that has no such field, so pressing Return "
                "raises AttributeError on vendor_refund_narration and no "
                "return is created at all — the RMA feature is unavailable, "
                "loudly. The exact message text is NOT asserted here because "
                "it cannot be observed on this target. On v19 the same "
                "undeclared dependency is additionally a load-order problem, "
                "since nothing makes dto_account install before "
                f"{MODULE}. WF-024 E1.")
    finally:
        with ctx.step("Cleanup: restore the company narration, archive "
                      "TD-U-03 and sweep the fixtures"):
            try:
                if company_id and mutated and not restored:
                    rpc.write("res.company", [company_id],
                              {NARRATION_FIELD: original})
                    ctx.log(f"[warn] res.company[{company_id}]."
                            f"{NARRATION_FIELD} was restored by the teardown "
                            "because step 9 did not run")
            except Exception as exc:                        # noqa: BLE001
                ctx.log(f"[ALERT] res.company[{company_id}]."
                        f"{NARRATION_FIELD} could NOT be restored: {exc}. "
                        "Restore it by hand before any further return is "
                        "created on this database — every return made "
                        "meanwhile carries the wrong RMA terms. The original "
                        f"value was: {original!r}")
            try:
                if user_id:
                    rpc.write("res.users", [user_id], {"active": False})
            except Exception as exc:                        # noqa: BLE001
                ctx.log(f"[warn] TD-U-03 user {user_id} not archived: {exc}")
            safe_sweep(ctx)
