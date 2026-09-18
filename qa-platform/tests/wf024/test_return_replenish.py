"""DATAONE-WF-024 — TC189: the Return-and-Replenish money leg.

The most financially exposed part of the RMA fork. BR-7 says a replacement
shipped under an RMA is free, so the fork writes **revenue-bearing
`sale.order.line` records at 0.00 on a live customer order**. One line too
many, or a price that carries through, and the customer is invoiced for a
replacement they are owed.

Everything this file asserts was read out of the real source first
(AUTOMATION_CONVENTIONS hard rule 6).

The rules under test
--------------------
``DTO-Odoo/3rd-addons/stock_picking_auto_create_lot/wizard/stock_picking_return.py``

* ``:27-35`` — ``_create_returns_and_replenishments`` calls
  ``super()._create_return()`` (deliberately NOT ``self._create_return()``,
  so it bypasses the sibling override and repeats the stamping itself), then
  writes ``rma_number = new_picking._get_rma_sequence()`` and
  ``note = self.env.company.vendor_refund_narration``. That is workbook
  step 6.
* ``:37`` — ``if self.picking_id.sale_id:``. The whole sale-side leg is
  gated on the picking carrying a sale link; step 18 is that gate.
* ``:41-44`` — ``for return_line in self.product_return_moves`` /
  ``if return_line.quantity <= 0: continue``. **One line per RETURNED line,
  not per WIZARD line** — BR-8, and workbook steps 9 and 10.
* ``:47-56`` — the line vals, verbatim::

      'order_id': sale_order.id,
      'product_id': return_line.product_id.id,
      'product_uom_qty': return_line.quantity,
      'product_uom_id': return_line.uom_id.id,
      'requested_delivery_date': fields.Date.today(),
      'name': return_line.product_id.get_product_multiline_description_sale(),

  — steps 11, 13, 14 and 15.
* ``:59`` — ``vals['price_unit'] = 0.0``. Step 12, and with it step 16
  (the order total cannot move).
* ``:64`` — ``self.env['sale.order.line'].create(lines_to_create)``.
* ``:66`` — ``# new_picking_record.returned_sale_order_id = sale_order.id``,
  **commented out**. A grep of the whole ``DTO-Odoo`` tree finds
  ``returned_sale_order_id`` at that one commented line and nowhere else, so
  the only trace linking a free line to its RMA is the timestamp. Step 17,
  recorded as the documented gap WF-024 E5.
* ``:69-95`` — ``create_returns_and_replenishments``: **public**, returns a
  plain dict, therefore RPC-reachable, which is why this case drives the real
  money leg end to end instead of stubbing it. ``:86-94`` is the action dict
  asserted in step 7; ``:90`` is ``'view_mode': 'form,list,calendar'``
  (``'form,tree,calendar'`` in the v17 shape — compared through
  ``fg_common.list_tag``, never a hard-coded tag).

``wizard/stock_picking_return_views.xml:12-16`` — the second footer button,
``name="create_returns_and_replenishments"``, ``string="Return and
Replenish"``, ``type="object"``, xpath'd ``position="after"`` the core
Return button. Step 3.

Core, both versions, for the button the fork sits behind:
v17 ``stock/wizard/stock_picking_return_views.xml:35`` declares
``create_returns`` (``stock/wizard/stock_picking_return.py:183``);
v19 ``:27`` declares ``action_create_returns`` (``:210``). The name is
resolved by ``common.return_confirm_method``, which probes the delivered
arch — the very thing the DataOne xpath has to match — never
``ctx.env.version``.

The three undeclared dependencies this case exercises
-----------------------------------------------------
``__manifest__.py:14`` declares exactly ``["stock"]`` while the code above
reads/writes:

* ``res.company.vendor_refund_narration`` — ``dto_account``
  (``dto_account/models/res_company.py:51-54``, a ``fields.Html``), against
  ``stock.picking.note``, also ``fields.Html`` (v17
  ``stock/models/stock_picking.py:403``, v19 ``:559``);
* ``sale.order.line.requested_delivery_date`` — ``dto_sale``
  (``dto_sale/models/sale_order_line.py:11-13``, "Promised Ship Date"; zero
  hits anywhere in ``odoo-17.0/addons`` or ``enterprise-17.0``);
* ``stock.picking.sale_id`` — ``sale_stock``.

All three are probed by ``require_vendor_narration`` / ``require_dto_sale``,
which BLOCK with a named reason rather than failing obscurely.

Version pairs, all resolved by probing, none by ``if version``
--------------------------------------------------------------
* wizard confirm method — ``common.return_confirm_method(ctx)``;
* ``sale.order.line`` UoM — ``product_uom`` (v17
  ``sale/models/sale_order_line.py:120``) → ``product_uom_id`` (v19
  ``:132``), resolved by ``common.sol_uom_field``;
* list view tag in the returned action's ``view_mode`` —
  ``fg_common.list_tag``;
* storable product flags — ``ctx.adapter.storable_product_values()`` inside
  ``common.make_product``.

Deliberate side effects, recorded rather than suppressed
-------------------------------------------------------
1. Creating a ``sale.order.line`` on a **confirmed** order spawns a whole new
   outgoing delivery: ``sale_stock/models/sale_order_line.py:187-191`` calls
   ``_action_launch_stock_rule()`` from ``create``. The sweep removes it.
2. Validating a sale-linked delivery fires
   ``dto_sale_stock/data/base_automation_data.xml:4-11``, whose server action
   calls ``send_mail(..., force_send=True, ...)`` against hard-coded
   ``@d1systems.com`` addresses, and can also auto-POST an invoice
   (``dto_sale_stock/models/stock_picking.py:12-23``). ``require_mail_offline``
   is therefore the first precondition (convention rule 4) and the sweep
   removes the invoice by ``invoice_origin``.
3. The flow consumes two numbers from the shared global ``rma_number``
   sequence. That is inherent to the case — the workbook asserts the issued
   number's format — and is why no fixture in this suite ever creates a
   second sequence with that code.

Adaptations, documented rather than silent (none weakens an expectation)
-----------------------------------------------------------------------
* **Step 1's "log in as TD-U-01"** is not impersonated. The case's subject is
  the values of the created line, not access control (that is TC188's
  subject), and every assertion below is identical for any user who can run
  the wizard. The step is executed on the platform's configured session and
  the divergence is logged, not asserted away.
* **Step 13's "today"** is the server's own ``fields.Date.today()``
  (``wizard/stock_picking_return.py:54``), which is neither the platform
  host's date nor the session timezone's. It is *measured* through
  ``common.server_today`` — the one core Date field defaulting to it,
  package ``pack_date`` (v17 ``stock/models/stock_quant.py:1483``, v19
  ``stock/models/stock_package.py:54``) — rather than guessed, because
  guessing breaks across a midnight boundary and a ±1-day window would
  weaken the workbook. When the probe is unavailable the step BLOCKS.
* **Steps 9-16** are each asserted individually, exactly as the workbook's
  own note demands ("a broken port most often produces one line per *wizard*
  line rather than per *returned* line, or carries the original price_unit
  through"), *and* the complete expected-vs-actual picture for all eight is
  computed and logged in step 8 before the first check can raise, then
  re-asserted once as a single mismatch dict at the end of step 16 — so a
  failure reports every difference, per the convention's "mismatch dicts, not
  assertion loops".
* **Step 7** asserts what the workbook states (the action opens the new
  picking, in form view) plus the fork's own ``view_mode`` string routed
  through ``list_tag``; nothing about the action is asserted that the source
  does not declare.
* **Step 18's "no sale-order line anywhere"** is scoped to this execution's
  two fixture products (convention rule 5). The live database carries
  production order lines that no test may count.

EXPECTED v17 OUTCOME: PASS — every rule above is present in the v17 shape of
the fork, and the two version-shaped names are probed rather than assumed.
EXPECTED v19 OUTCOME: PASS if the port held. The standing exposure is that
``_create_returns_and_replenishments`` calls ``super()._create_return()``
from a differently named method, and ``_create_return`` is not in the v19
delta's verified-unchanged list; a silent contract change in the line vals
would surface here as a wrong UoM or quantity that still saves.
"""
from adapters.base import OdooRPCError
from framework.fg_common import list_tag, m2o_id
from framework.registry import test_case

from tests.wf024.common import (MISSING_BACKLINK_FIELD, NARRATION_FIELD,
                                REPLENISH_ACTION_NAME, REPLENISH_DATE_FIELD,
                                RMA_NUMBER_PATTERN, RMA_NUMBER_RE, WORKFLOW,
                                WORKFLOW_NAME, WIZARD_REPLENISH_BUTTON,
                                WIZARD_REPLENISH_METHOD, arch_footer_buttons,
                                confirm_return_and_replenish, make_delivery,
                                make_product, open_namespace,
                                open_return_wizard, order_lines, order_total,
                                product_uom_of, require_dto_sale,
                                require_mail_offline, require_rma_module,
                                require_rma_sequence, require_vendor_narration,
                                return_confirm_method, return_of, rma_snapshot,
                                safe_sweep, sell_and_deliver, server_today,
                                set_return_quantities, sol_uom_field, trace,
                                wizard_form_arch, wizard_lines)

#: TD-P-01 and TD-P-03 as this suite instantiates them. Prices are non-zero
#: so "price_unit == 0.0" and "the order total increased by 0.00" are real
#: assertions and not tautologies on a zero-priced fixture.
P01_PRICE = 100.0
P03_PRICE = 50.0
#: The workbook's own quantities: 5 x TD-P-01 and 3 x TD-P-03 ordered,
#: 2 of TD-P-01 and 0 of TD-P-03 returned.
P01_ORDERED = 5.0
P03_ORDERED = 3.0
P01_RETURNED = 2.0
P03_RETURNED = 0.0


def _footer_buttons(ctx) -> list:
    """The delivered ``stock.return.picking`` footer buttons, in order.

    ``common.arch_footer_buttons`` reads the COMPOSED arch, so the fork's
    xpath'd button appears in the position the client will render it —
    which is what workbook step 3 is about.
    """
    return arch_footer_buttons(wizard_form_arch(ctx))


def _unlock(ctx, order_id: int) -> bool:
    """Guarantee the workbook's "the order is not locked" precondition.

    ``sale.order.locked`` exists on both targets (v17
    ``sale/models/sale_order.py:73``, v19 ``:77``) and ``action_unlock`` is
    public on both (v17 ``:1050``, v19 ``:1322``). A confirmed order is
    locked automatically when ``sale.group_auto_done_setting`` is on, which
    is a per-database setting; unlocking THIS execution's own fixture order
    is not a mutation of a pre-existing business record. Returns the
    ``locked`` value observed before the call.
    """
    rpc = ctx.adapter.rpc
    if not rpc.field_exists("sale.order", "locked"):
        return False
    locked = bool(rpc.read("sale.order", [order_id], ["locked"])[0]["locked"])
    if locked:
        try:
            rpc.call("sale.order", "action_unlock", [order_id])
        except OdooRPCError as exc:
            ctx.log(f"[warn] action_unlock({order_id}) failed: {exc}")
    return locked


def _multiline_description(rpc, product_id: int) -> str:
    """``product.get_product_multiline_description_sale()`` over RPC.

    Public on both targets (v17 ``product/models/product_product.py:759``,
    v19 ``:1140``), returns a plain string, so workbook step 14 compares
    against the product's own answer rather than against a reconstruction of
    it inside the test.
    """
    return rpc.call("product.product",
                    "get_product_multiline_description_sale", [product_id])


def _fixture_line_ids(rpc, product_ids) -> list:
    """Every ``sale.order.line`` referencing THIS execution's products.

    Convention rule 5: the live database carries production order lines, so
    "no sale-order line anywhere" (step 18) is measured over the token's own
    products and never as a global count.
    """
    return sorted(rpc.search("sale.order.line",
                             [("product_id", "in", list(product_ids))]))


@test_case(
    id="TEST-WF024-TC189",
    name="Return and Replenish adds exactly one zero-priced line per returned "
         "line, dated today",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="stock_picking_auto_create_lot",
    priority="P0", kind="API", order=24189,
    description="Returning 2 of one delivered line and 0 of the other adds "
                "exactly ONE sale order line — the returned product, quantity "
                "2, price 0.00, dated the server's today, with the product's "
                "own sale UoM and description — leaving the order total "
                "unchanged; the same flow on a delivery with no sale link "
                "creates the return and no order line at all.",
    traceability=trace("DATAONE-TC189"))
def test_tc189(ctx):
    rpc = ctx.adapter.rpc

    # Preconditions, each BLOCKING with a named reason rather than failing
    # obscurely three steps later. require_mail_offline is first: everything
    # below validates a sale-linked delivery (convention rule 4).
    require_mail_offline(ctx)
    require_rma_module(ctx)
    require_rma_sequence(ctx)
    company_id = require_vendor_narration(ctx)
    require_dto_sale(ctx)

    open_namespace(ctx)
    try:
        with ctx.step("Precondition: a done outgoing delivery for TD-PA-01 is "
                      "linked to a sale order with two lines, 5 x TD-P-01 and "
                      "3 x TD-P-03, both fully delivered, and the order is "
                      "not locked"):
            p01 = make_product(ctx, "P01", price=P01_PRICE, cost=80.0)
            p03 = make_product(ctx, "P03", price=P03_PRICE, cost=40.0)
            order_id, picking_id = sell_and_deliver(
                ctx, [(p01, P01_ORDERED, P01_PRICE),
                      (p03, P03_ORDERED, P03_PRICE)], label="SO02")
            was_locked = _unlock(ctx, order_id)
            ctx.log(f"fixture order {order_id} was locked={was_locked}")
            snap_src = rma_snapshot(rpc, picking_id)
            ctx.check("the fixture delivery is done and carries a sale link",
                      {"state": "done", "has sale_id": True},
                      {"state": snap_src["state"],
                       "has sale_id": bool(m2o_id(snap_src.get("sale_id")))})

        with ctx.step("Log in as TD-U-01 and record lines_before = "
                      "order.order_line.ids and len(lines_before) == 2"):
            # ADAPTATION (documented in the module docstring): the session is
            # the platform's own, not a TD-U-01 impersonation. This case's
            # subject is the created line's values, not access control, and
            # every assertion below is identical for any user able to run the
            # wizard. Role fidelity is TC188's subject.
            ctx.log("[note] executed on the platform's configured session; "
                    "TD-U-01 (dto_sales / Customer Service) impersonation is "
                    "TC188's subject, not this case's")
            lines_before = rpc.read("sale.order", [order_id],
                                    ["order_line"])[0]["order_line"]
            total_before = order_total(rpc, order_id)
            ctx.log(f"lines_before = {lines_before!r}, "
                    f"amount_total = {total_before!r}")
            ctx.check("len(lines_before) == 2", 2, len(lines_before))

        with ctx.step("Open the done delivery and press Return"):
            wizard_id = open_return_wizard(rpc, picking_id)
            prefilled = wizard_lines(rpc, wizard_id)
            ctx.log(f"wizard {wizard_id} product_return_moves = {prefilled!r}")
            ctx.check("the wizard lists one return line per delivered move",
                      sorted([p01, p03]),
                      sorted(m2o_id(line["product_id"]) for line in prefilled))

        with ctx.step("Assert the wizard shows a second button, Return and "
                      "Replenish, positioned after the standard Return "
                      "button"):
            buttons = _footer_buttons(ctx)
            names = [b.get("name") or "" for b in buttons]
            confirm_name = return_confirm_method(ctx)
            idx_return = names.index(confirm_name) if confirm_name in names \
                else -1
            idx_replenish = names.index(WIZARD_REPLENISH_METHOD) \
                if WIZARD_REPLENISH_METHOD in names else -1
            replenish = buttons[idx_replenish] if idx_replenish >= 0 else {}
            ctx.log(f"footer buttons = {names!r}; the version's own Return "
                    f"button is {confirm_name!r}")
            ctx.check(
                f"the footer carries {WIZARD_REPLENISH_BUTTON!r} immediately "
                f"after the standard Return button ({confirm_name})",
                {"present": True, "string": WIZARD_REPLENISH_BUTTON,
                 "type": "object", "immediately after Return": True},
                {"present": idx_replenish >= 0,
                 "string": replenish.get("string"),
                 "type": replenish.get("type"),
                 "immediately after Return": (idx_return >= 0
                                              and idx_replenish
                                              == idx_return + 1)})

        with ctx.step("Set the return quantity for TD-P-01 to 2 and for "
                      "TD-P-03 to 0"):
            set_return_quantities(rpc, wizard_id,
                                  {p01: P01_RETURNED, p03: P03_RETURNED})
            applied = {m2o_id(line["product_id"]): line["quantity"]
                       for line in wizard_lines(rpc, wizard_id)}
            ctx.check("the wizard holds 2 for TD-P-01 and 0 for TD-P-03",
                      {p01: P01_RETURNED, p03: P03_RETURNED}, applied)

        with ctx.step("Press Return and Replenish"):
            action = confirm_return_and_replenish(rpc, wizard_id)
            ctx.log(f"create_returns_and_replenishments -> {action!r}")
            # Measured here, as close as possible to the server's own
            # fields.Date.today() at wizard/stock_picking_return.py:54.
            today = server_today(rpc)
            ctx.log(f"server fields.Date.today() = {today!r}")
            ctx.check_true("the method returned an act_window dict",
                           isinstance(action, dict)
                           and action.get("type") == "ir.actions.act_window",
                           actual_desc=repr(action))

        with ctx.step("Assert a return picking was created with an rma_number "
                      "matching ^\\d{4}-\\d{3}$ and a note equal to the "
                      "company narration"):
            returned = return_of(rpc, picking_id)
            ctx.check_true("a return picking exists for the delivery",
                           bool(returned), actual_desc=repr(returned))
            return_id = returned["id"] if returned else None
            snap = rma_snapshot(rpc, return_id) if return_id else {}
            narration = rpc.read("res.company", [company_id],
                                 [NARRATION_FIELD])[0][NARRATION_FIELD]
            ctx.check_true(
                f"rma_number matches {RMA_NUMBER_PATTERN}",
                bool(RMA_NUMBER_RE.match(snap.get("rma_number") or "")),
                actual_desc=repr(snap.get("rma_number")))
            # Both values are read back over the SAME session, so the Html
            # sanitizer has run over both (res.company.vendor_refund_narration
            # and stock.picking.note are both fields.Html).
            ctx.check("the return's note equals the company narration",
                      narration, snap.get("note"))

        with ctx.step("Assert the action returned opens the new picking in "
                      "form view"):
            expected_action = {
                "res_model": "stock.picking",
                "res_id": return_id,
                "type": "ir.actions.act_window",
                "name": REPLENISH_ACTION_NAME,
                "first view": "form",
                "view_mode": f"form,{list_tag(ctx)},calendar",
            }
            view_mode = (action or {}).get("view_mode") or ""
            observed_action = {
                "res_model": (action or {}).get("res_model"),
                "res_id": (action or {}).get("res_id"),
                "type": (action or {}).get("type"),
                "name": (action or {}).get("name"),
                "first view": view_mode.split(",")[0] if view_mode else None,
                "view_mode": view_mode,
            }
            ctx.check("the action opens the new return picking in form view",
                      expected_action, observed_action)

        with ctx.step("Reload the sale order and record lines_after = "
                      "order.order_line.ids"):
            lines_after = rpc.read("sale.order", [order_id],
                                   ["order_line"])[0]["order_line"]
            new_line_ids = [i for i in lines_after if i not in lines_before]
            rows = {row["id"]: row for row in order_lines(rpc, order_id)}
            new_line = rows.get(new_line_ids[0]) \
                if len(new_line_ids) == 1 else None
            uom_field = sol_uom_field(rpc)
            total_after = order_total(rpc, order_id)
            ctx.log(f"lines_after = {lines_after!r}; "
                    f"new line ids = {new_line_ids!r}; "
                    f"new line = {new_line!r}")

            # The complete workbook picture for steps 9-16, computed in one
            # place so the first failing check below cannot hide the others.
            expected = {
                "step 9 — len(lines_after)": 3,
                "step 10 — new line product": p01,
                "step 11 — new line product_uom_qty": P01_RETURNED,
                "step 12 — new line price_unit": 0.0,
                f"step 13 — new line {REPLENISH_DATE_FIELD}": today,
                "step 14 — new line name":
                    _multiline_description(rpc, p01),
                "step 15 — new line UoM": product_uom_of(rpc, p01),
                "step 16 — order total delta": 0.0,
            }
            observed = {
                "step 9 — len(lines_after)": len(lines_after),
                "step 10 — new line product":
                    m2o_id(new_line["product_id"]) if new_line else None,
                "step 11 — new line product_uom_qty":
                    new_line["product_uom_qty"] if new_line else None,
                "step 12 — new line price_unit":
                    new_line["price_unit"] if new_line else None,
                f"step 13 — new line {REPLENISH_DATE_FIELD}":
                    (new_line.get(REPLENISH_DATE_FIELD) or None)
                    if new_line else None,
                "step 14 — new line name":
                    new_line["name"] if new_line else None,
                "step 15 — new line UoM":
                    m2o_id(new_line[uom_field]) if new_line else None,
                "step 16 — order total delta":
                    round(total_after - total_before, 2),
            }
            diffs = {key: {"expected": value, "actual": observed.get(key)}
                     for key, value in expected.items()
                     if observed.get(key) != value}
            ctx.log(f"steps 9-16 expected = {expected!r}")
            ctx.log(f"steps 9-16 observed = {observed!r}")
            ctx.log(f"steps 9-16 differences = {diffs!r}")

        with ctx.step("Assert exactly one new line was added — "
                      "len(lines_after) == 3"):
            key = "step 9 — len(lines_after)"
            ctx.check("exactly one new sale order line", expected[key],
                      observed[key])

        with ctx.step("Assert the new line's product is TD-P-01 and not "
                      "TD-P-03 (only lines with quantity > 0 generate a "
                      "replacement, BR-8)"):
            key = "step 10 — new line product"
            ctx.log(f"TD-P-01 = {p01}, TD-P-03 = {p03} — the zero-quantity "
                    "wizard line must produce nothing "
                    "(wizard/stock_picking_return.py:43-44)")
            ctx.check("the replacement is for the returned product only",
                      expected[key], observed[key])

        with ctx.step("Assert the new line's product_uom_qty == 2 — equal to "
                      "the returned quantity"):
            key = "step 11 — new line product_uom_qty"
            ctx.check("product_uom_qty equals the returned quantity",
                      expected[key], observed[key])

        with ctx.step("Assert the new line's price_unit == 0.0"):
            key = "step 12 — new line price_unit"
            ctx.check("the replacement is free (BR-7)", expected[key],
                      observed[key])

        with ctx.step("Assert the new line's requested_delivery_date equals "
                      "today"):
            if today is None:
                ctx.blocked(
                    "the server's own fields.Date.today() could not be "
                    "measured on this target: common.server_today probes the "
                    "package model's pack_date default (v17 "
                    "stock/models/stock_quant.py:1483, v19 "
                    "stock/models/stock_package.py:54) and neither "
                    "stock.quant.package nor stock.package accepted the "
                    "throwaway record. Comparing against the platform host's "
                    "date instead would make this assertion wrong across a "
                    "midnight boundary or a server in another timezone.")
            key = f"step 13 — new line {REPLENISH_DATE_FIELD}"
            ctx.check(f"{REPLENISH_DATE_FIELD} is the server's today",
                      expected[key], observed[key])

        with ctx.step("Assert the new line's name equals "
                      "product.get_product_multiline_description_sale()"):
            key = "step 14 — new line name"
            ctx.check("the description is the product's own sale description",
                      expected[key], observed[key])

        with ctx.step("Assert the new line's UoM matches the product's sale "
                      "UoM"):
            key = "step 15 — new line UoM"
            ctx.log(f"sale.order.line UoM field on this target = "
                    f"{sol_uom_field(rpc)!r}")
            ctx.check("the replacement carries the product's sale UoM",
                      expected[key], observed[key])

        with ctx.step("Assert the order total increased by 0.00"):
            key = "step 16 — order total delta"
            ctx.log(f"amount_total {total_before!r} -> {total_after!r}")
            ctx.check("amount_total is unchanged", expected[key],
                      observed[key])
            # One consolidated mismatch dict for the whole group, so a rerun
            # reports every divergence at once (AUTOMATION_CONVENTIONS,
            # "mismatch dicts, not assertion loops").
            ctx.check("steps 9-16 — no divergence in any replacement-line "
                      "value", {}, diffs)

        with ctx.step("Assert nothing on the new line records which RMA "
                      "produced it — returned_sale_order_id is unset (the "
                      "assignment is commented out). Record as the documented "
                      "v17 gap (WF-024 E5)"):
            # wizard/stock_picking_return.py:66 is the ONLY occurrence of the
            # name in the whole DTO-Odoo tree, and it is a comment — so the
            # field is not declared on either model and "unset" is asserted
            # as its absence.
            presence = {
                f"sale.order.line.{MISSING_BACKLINK_FIELD}":
                    rpc.field_exists("sale.order.line", MISSING_BACKLINK_FIELD),
                f"stock.picking.{MISSING_BACKLINK_FIELD}":
                    rpc.field_exists("stock.picking", MISSING_BACKLINK_FIELD),
            }
            ctx.log("WF-024 E5: the only trace linking a free replacement "
                    "line to its RMA is the timestamp")
            ctx.check("returned_sale_order_id exists on neither model",
                      {key: False for key in presence}, presence)

        with ctx.step("Repeat the whole flow on a return from a delivery not "
                      "linked to a sale order and assert only the return is "
                      "created, with no sale-order line anywhere"):
            before_18 = _fixture_line_ids(rpc, [p01, p03])
            plain_id = make_delivery(ctx, [(p01, P01_RETURNED)],
                                     label="NOSALE")
            plain_snap = rma_snapshot(rpc, plain_id)
            ctx.check("the second fixture delivery has no sale link",
                      {"state": "done", "has sale_id": False},
                      {"state": plain_snap["state"],
                       "has sale_id": bool(m2o_id(plain_snap.get("sale_id")))})

            wizard2 = open_return_wizard(rpc, plain_id)
            set_return_quantities(rpc, wizard2, {p01: P01_RETURNED})
            action2 = confirm_return_and_replenish(rpc, wizard2)
            ctx.log(f"create_returns_and_replenishments (no sale link) -> "
                    f"{action2!r}")
            returned2 = return_of(rpc, plain_id)
            after_18 = _fixture_line_ids(rpc, [p01, p03])
            ctx.check(
                "the sale-side leg is conditional on picking.sale_id "
                "(wizard/stock_picking_return.py:37)",
                {"return picking created": True,
                 f"rma_number matches {RMA_NUMBER_PATTERN}": True,
                 "new sale.order.line rows": []},
                {"return picking created": bool(returned2),
                 f"rma_number matches {RMA_NUMBER_PATTERN}":
                     bool(RMA_NUMBER_RE.match(
                         (returned2 or {}).get("rma_number") or "")),
                 "new sale.order.line rows":
                     sorted(set(after_18) - set(before_18))})
    finally:
        # Never raises: safe_sweep swallows its own failures, and the extra
        # guard keeps a teardown fault from masking the test's verdict.
        try:
            safe_sweep(ctx)
        except Exception:  # noqa: BLE001
            pass
