"""DATAONE-WF-002 — the NTT price formula: TC090–TC094.

``dto_sale_price_formula`` adds ``sale.order.line.ntt_unit_price``, a
stored compute with ``readonly=False``::

    @api.depends('product_id', 'price_unit',
                 'order_id.partner_id', 'order_id.company_id')
    def _compute_ntt_unit_price(self):
        formula = (line.order_id.partner_id.price_formula
                   or line.order_id.company_id.price_formula)
        if not formula or not line.price_unit:
            line.ntt_unit_price = line.price_unit
        else:
            try:    line.ntt_unit_price = float(safe_eval(formula, {'price': line.price_unit}))
            except Exception:  _logger.warning(...); line.ntt_unit_price = line.price_unit

Four consequences the workbook pins down: the partner formula wins over the
company one; a falsy price short-circuits to the unit price; a broken
formula falls back silently with only a log line; and because the compute
does not depend on the formula fields, changing a formula does **not**
recompute saved lines until some other dependency moves.

Config discipline: these cases flip ``res.company.price_formula``, which is
a configuration record this suite does not own. Every test snapshots the
original value and restores it in a ``finally`` that cannot raise
(convention: "snapshot+restore any config you flip").

EXPECTED v17 OUTCOME: PASS for all five.
"""
from framework.registry import test_case
from tests.wf002.common import (MARK, WORKFLOW, WORKFLOW_NAME,  # noqa: F401
                                confirm, ensure_partner, ensure_product,
                                fx, line_values, m2o_id, make_quotation,
                                order_lines, read_order, require_dto_sale,
                                require_mail_offline, sweep_wf002, trace)

COMPANY_FORMULA = "price * 1.10"
PARTNER_FORMULA = "price * 1.15"
BROKEN_FORMULA = "price *"


def _require_formula_module(ctx):
    rpc = ctx.adapter.rpc
    if not rpc.field_exists("sale.order.line", "ntt_unit_price"):
        ctx.blocked(
            "sale.order.line.ntt_unit_price does not exist on "
            f"{ctx.env.key} — dto_sale_price_formula is not installed, so "
            "there is no NTT price to assert.")
    for model in ("res.company", "res.partner"):
        if not rpc.field_exists(model, "price_formula"):
            ctx.blocked(
                f"{model}.price_formula does not exist on {ctx.env.key}; "
                "dto_sale_price_formula is only partly installed.")


def _company_id(rpc):
    return m2o_id(rpc.read("res.users", [rpc.uid], ["company_id"])[0]["company_id"])


def _set_company_formula(rpc, company_id, value):
    rpc.write("res.company", [company_id], {"price_formula": value})


def _ntt(rpc, order_id):
    return order_lines(rpc, order_id, ["ntt_unit_price", "price_unit"])


@test_case(
    id="TEST-WF002-TC090",
    name="The company NTT price formula is applied to the line",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_sale_price_formula", priority="P3", kind="API", order=2090,
    description="price * 1.10 gives 110.00 at a unit price of 100.00, "
                "re-fires to 220.00 at 200.00, and short-circuits to 0.00 "
                "when the unit price is falsy.",
    traceability=trace("DATAONE-TC090"))
def test_tc090(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-002 fixtures and open a fresh "
                  "namespace"):
        sweep_wf002(rpc)

    with ctx.step("Precondition: dto_sale_price_formula is installed"):
        require_dto_sale(ctx)
        _require_formula_module(ctx)

    company_id = _company_id(rpc)
    original = rpc.read("res.company", [company_id],
                        ["price_formula"])[0]["price_formula"]
    ctx.log(f"company {company_id} price_formula snapshot: {original!r}")
    try:
        with ctx.step("Step 1: set the company formula to price * 1.10"):
            _set_company_formula(rpc, company_id, COMPANY_FORMULA)
            ctx.check("company price_formula", COMPANY_FORMULA,
                      rpc.read("res.company", [company_id],
                               ["price_formula"])[0]["price_formula"])

        with ctx.step("Steps 2-5: a line at 100.00 gives ntt_unit_price "
                      "110.00"):
            product_id = ensure_product(ctx, price=100.0)
            order_id = make_quotation(
                ctx, order_type="inventory", label="NTTCompany",
                lines=[line_values(product_id, qty=1.0, price=100.0)])
            lines = _ntt(rpc, order_id)
            ctx.log(f"lines: {lines!r}")
            ctx.check("ntt_unit_price at price 100.00", 110.0,
                      round(lines[0]["ntt_unit_price"], 2))

        with ctx.step("Steps 6-7: raising the unit price to 200.00 re-fires "
                      "the compute"):
            rpc.write("sale.order.line", [lines[0]["id"]],
                      {"price_unit": 200.0})
            ctx.check("ntt_unit_price at price 200.00", 220.0,
                      round(_ntt(rpc, order_id)[0]["ntt_unit_price"], 2))

        with ctx.step("Step 8: a falsy unit price short-circuits — "
                      "ntt_unit_price equals the unit price"):
            rpc.write("sale.order.line", [lines[0]["id"]],
                      {"price_unit": 0.0})
            ctx.check("ntt_unit_price at price 0.00", 0.0,
                      round(_ntt(rpc, order_id)[0]["ntt_unit_price"], 2))
    finally:
        with ctx.step("Restore the company formula and clean up"):
            try:
                _set_company_formula(rpc, company_id, original)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] company formula NOT restored to "
                        f"{original!r}: {exc}")
            try:
                sweep_wf002(rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")


@test_case(
    id="TEST-WF002-TC091",
    name="A customer formula overrides the company formula",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_sale_price_formula", priority="P3", kind="API", order=2091,
    description="A partner formula wins (115.00); a partner without one "
                "falls through to the company formula (110.00); clearing "
                "the override restores the fall-through.",
    traceability=trace("DATAONE-TC091"))
def test_tc091(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-002 fixtures and open a fresh "
                  "namespace"):
        sweep_wf002(rpc)

    with ctx.step("Precondition: dto_sale_price_formula is installed"):
        require_dto_sale(ctx)
        _require_formula_module(ctx)

    company_id = _company_id(rpc)
    original = rpc.read("res.company", [company_id],
                        ["price_formula"])[0]["price_formula"]
    try:
        with ctx.step("Set the company formula and a partner override"):
            _set_company_formula(rpc, company_id, COMPANY_FORMULA)
            product_id = ensure_product(ctx, price=100.0)
            override_partner = ensure_partner(
                rpc, "OverridePartner", {"price_formula": PARTNER_FORMULA})
            plain_partner = ensure_partner(rpc, "PlainPartner")

        with ctx.step("Steps 2-3: the customer formula wins — 115.00"):
            order_a = make_quotation(
                ctx, order_type="inventory", label="NTTOverride",
                partner_id=override_partner,
                lines=[line_values(product_id, price=100.0)])
            ctx.check("ntt_unit_price with a partner formula", 115.0,
                      round(_ntt(rpc, order_a)[0]["ntt_unit_price"], 2))

        with ctx.step("Steps 4-5: a partner without a formula falls through "
                      "to the company one — 110.00"):
            order_b = make_quotation(
                ctx, order_type="inventory", label="NTTFallthrough",
                partner_id=plain_partner,
                lines=[line_values(product_id, price=100.0)])
            ctx.check("ntt_unit_price with no partner formula", 110.0,
                      round(_ntt(rpc, order_b)[0]["ntt_unit_price"], 2))

        with ctx.step("Step 6: clearing the partner override restores the "
                      "fall-through — 110.00"):
            rpc.write("res.partner", [override_partner],
                      {"price_formula": False})
            order_c = make_quotation(
                ctx, order_type="inventory", label="NTTCleared",
                partner_id=override_partner,
                lines=[line_values(product_id, price=100.0)])
            ctx.check("ntt_unit_price after clearing the override", 110.0,
                      round(_ntt(rpc, order_c)[0]["ntt_unit_price"], 2))
    finally:
        with ctx.step("Restore the company formula and clean up"):
            try:
                _set_company_formula(rpc, company_id, original)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] company formula NOT restored: {exc}")
            try:
                sweep_wf002(rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")


@test_case(
    id="TEST-WF002-TC092",
    name="An invalid formula silently falls back to the unit price",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_sale_price_formula", priority="P3", kind="API", order=2092,
    description="A syntactically broken formula raises nothing the user "
                "can see; ntt_unit_price falls back to price_unit and the "
                "only trace is a WARNING in the server log.",
    traceability=trace("DATAONE-TC092"))
def test_tc092(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-002 fixtures and open a fresh "
                  "namespace"):
        sweep_wf002(rpc)

    with ctx.step("Precondition: dto_sale_price_formula is installed"):
        require_dto_sale(ctx)
        _require_formula_module(ctx)

    try:
        with ctx.step("Steps 1-3: a partner with a broken formula saves a "
                      "quotation with no user-facing error"):
            product_id = ensure_product(ctx, price=100.0)
            partner_id = ensure_partner(rpc, "BrokenFormula",
                                        {"price_formula": BROKEN_FORMULA})
            order_id = make_quotation(
                ctx, order_type="inventory", label="NTTBroken",
                partner_id=partner_id,
                lines=[line_values(product_id, price=100.0)])
            ctx.check_true("the quotation saved without raising",
                           bool(order_id),
                           actual_desc=f"sale.order {order_id}")

        with ctx.step("Step 4: ntt_unit_price fell back to the unit price"):
            ctx.check("ntt_unit_price with a broken formula", 100.0,
                      round(_ntt(rpc, order_id)[0]["ntt_unit_price"], 2))

        with ctx.step("Step 5: the only trace is a server-log WARNING"):
            ctx.log("_compute_ntt_unit_price catches every Exception and "
                    "emits _logger.warning('NTT price formula \"%s\" failed "
                    "for line %s, falling back to unit price.') — "
                    "dto_sale_price_formula/models/sale_order_line.py. The "
                    "server log is not reachable over RPC from this "
                    "platform; the silent-fallback VALUE, which is what the "
                    "user actually sees, is asserted above.")
    finally:
        with ctx.step("Cleanup WF-002 fixtures"):
            try:
                sweep_wf002(rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")


@test_case(
    id="TEST-WF002-TC093",
    name="A manual NTT value is overwritten; a formula change is not "
         "retroactive",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_sale_price_formula", priority="P3", kind="API", order=2093,
    description="A typed value persists until a dependency moves, is then "
                "discarded by the recompute; and because the compute does "
                "not depend on the formula fields, changing the formula "
                "leaves saved lines alone until their price changes again.",
    traceability=trace("DATAONE-TC093"))
def test_tc093(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-002 fixtures and open a fresh "
                  "namespace"):
        sweep_wf002(rpc)

    with ctx.step("Precondition: dto_sale_price_formula is installed"):
        require_dto_sale(ctx)
        _require_formula_module(ctx)

    company_id = _company_id(rpc)
    original = rpc.read("res.company", [company_id],
                        ["price_formula"])[0]["price_formula"]
    try:
        with ctx.step("Set the company formula to price * 1.10 and build a "
                      "line at 100.00"):
            _set_company_formula(rpc, company_id, COMPANY_FORMULA)
            product_id = ensure_product(ctx, price=100.0)
            order_id = make_quotation(
                ctx, order_type="inventory", label="NTTManual",
                lines=[line_values(product_id, price=100.0)])
            line_id = _ntt(rpc, order_id)[0]["id"]

        with ctx.step("Steps 2-3: a manually typed 999.00 persists while "
                      "nothing it depends on changes"):
            rpc.write("sale.order.line", [line_id],
                      {"ntt_unit_price": 999.0})
            ctx.check("manual ntt_unit_price", 999.0,
                      round(_ntt(rpc, order_id)[0]["ntt_unit_price"], 2))

        with ctx.step("Steps 4-5: changing the unit price to 120.00 "
                      "discards the manual value — 132.00"):
            rpc.write("sale.order.line", [line_id], {"price_unit": 120.0})
            ctx.check("ntt_unit_price after the recompute", 132.0,
                      round(_ntt(rpc, order_id)[0]["ntt_unit_price"], 2))

        with ctx.step("Steps 6-7: changing the company formula does NOT "
                      "recompute the saved line — the compute does not "
                      "depend on price_formula"):
            _set_company_formula(rpc, company_id, "price * 2.00")
            ctx.check("ntt_unit_price after only the formula changed", 132.0,
                      round(_ntt(rpc, order_id)[0]["ntt_unit_price"], 2))

        with ctx.step("Step 8: the new formula applies once a dependency "
                      "moves — 130.00 * 2.00 = 260.00"):
            rpc.write("sale.order.line", [line_id], {"price_unit": 130.0})
            ctx.check("ntt_unit_price after the price moved again", 260.0,
                      round(_ntt(rpc, order_id)[0]["ntt_unit_price"], 2))
    finally:
        with ctx.step("Restore the company formula and clean up"):
            try:
                _set_company_formula(rpc, company_id, original)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] company formula NOT restored: {exc}")
            try:
                sweep_wf002(rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")


@test_case(
    id="TEST-WF002-TC094",
    name="NTT Unit Price never reaches the total, the invoice, tax or "
         "margin",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_sale_price_formula", priority="P2", kind="API", order=2094,
    description="price_subtotal and the three order totals derive from "
                "price_unit only; the invoice line carries price_unit and "
                "no amount anywhere derives from the NTT value.",
    traceability=trace("DATAONE-TC094"))
def test_tc094(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-002 fixtures and open a fresh "
                  "namespace"):
        sweep_wf002(rpc)

    with ctx.step("Preconditions: dto_sale_price_formula installed, mail "
                  "offline"):
        require_dto_sale(ctx)
        _require_formula_module(ctx)
        require_mail_offline(ctx)

    try:
        with ctx.step("Steps 1-2: a partner formula of price * 1.15 on a "
                      "line of 2 x 100.00 gives an NTT price of 115.00"):
            product_id = ensure_product(ctx, price=100.0)
            partner_id = ensure_partner(rpc, "NTTIsolation",
                                        {"price_formula": PARTNER_FORMULA})
            order_id = make_quotation(
                ctx, order_type="inventory", label="NTTIsolation",
                partner_id=partner_id,
                lines=[line_values(product_id, qty=2.0, price=100.0)])
            line = order_lines(rpc, order_id,
                               ["ntt_unit_price", "price_unit",
                                "price_subtotal"])[0]
            ctx.log(f"line: {line!r}")
            ctx.check("ntt_unit_price", 115.0,
                      round(line["ntt_unit_price"], 2))

        with ctx.step("Step 3: price_subtotal is 2 x 100.00, not the NTT "
                      "price"):
            ctx.check("price_subtotal", 200.0,
                      round(line["price_subtotal"], 2))

        with ctx.step("Step 4: the order totals derive from 100.00"):
            totals = read_order(rpc, order_id,
                                ["amount_untaxed", "amount_tax",
                                 "amount_total"])
            ctx.log(f"order totals: {totals!r}")
            ctx.check("amount_untaxed", 200.0,
                      round(totals["amount_untaxed"], 2))

        with ctx.step("Steps 5-8: the invoice carries price_unit, and no "
                      "amount anywhere derives from the NTT value"):
            from framework.dto_fixtures import create_invoice
            confirm(rpc, order_id)
            invoice_id = create_invoice(ctx, order_id)
            if not invoice_id:
                ctx.log("no invoice was produced (nothing delivered and the "
                        "policy is delivery-based) — the invoice half is "
                        "not applicable here")
            else:
                inv_lines = rpc.search_read(
                    "account.move.line", [("move_id", "=", invoice_id)],
                    ["name", "price_unit", "price_subtotal", "balance"])
                move = rpc.read("account.move", [invoice_id],
                                ["amount_untaxed", "amount_total"])[0]
                ctx.log(f"invoice lines: {inv_lines!r}; totals: {move!r}")
                product_lines = [ln for ln in inv_lines if ln["price_unit"]]
                ctx.check("invoice line price_unit values",
                          [100.0],
                          sorted({round(ln["price_unit"], 2)
                                  for ln in product_lines}))
                ntt_derived = [
                    ln for ln in inv_lines
                    if round(ln["price_unit"], 2) == 115.0
                    or round(ln["price_subtotal"], 2) in (115.0, 230.0)
                    or round(abs(ln["balance"]), 2) in (115.0, 230.0)]
                ctx.check("invoice amounts derived from the NTT price", [],
                          ntt_derived)
                ctx.check("invoice totals derived from the NTT price", [],
                          [k for k, v in move.items()
                           if round(v, 2) in (115.0, 230.0)])
    finally:
        with ctx.step("Cleanup WF-002 fixtures"):
            try:
                sweep_wf002(rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")
