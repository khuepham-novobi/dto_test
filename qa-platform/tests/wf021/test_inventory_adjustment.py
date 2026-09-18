"""DATAONE-WF-021 — TC251: the location-analytic tag on an inventory write-off.

What this file proves
=====================
An inventory adjustment routed through a **virtual location that carries an
analytic distribution** must post a two-line valuation entry in which

* the **Stock Valuation** line is analytically **clean** — no tag at all, and
* the **counterpart** line — the location's own Inventory Adjustment account —
  carries the location's distribution **verbatim**,

in **both** directions, and must fall back to two untagged lines when the
virtual location carries no distribution. The general ledger is correct in
every one of those cases; only the analytic ledger tells them apart, which is
why steps 7, 8 and 11 exist as three separate assertions instead of one
balance check.

The rules asserted, and where each one lives
--------------------------------------------
``dto_account`` (v17 baseline = ``git show main:…``; the working tree is on
branch ``UAT``, which already carries the v19 port — see "The checkout trap"
in ``tests/wf021/common.py``):

* ``models/stock_location.py:7-11`` — ``stock.location`` gains
  ``analytic.mixin`` and ``location_analytic_distribution = fields.Json(...)``.
  Identical on ``main`` and ``UAT``.
* ``models/stock_move.py:24-46`` (v17) — ``_account_entry_move(qty,
  description, svl_id, cost)``. **Private**, so only its output is
  observable (AUTOMATION_CONVENTIONS, "Private methods are not reachable").
  It bails out when ``len(virtual_locations) != 1`` or the location has no
  distribution (``:32-33``), tags only lines whose ``account_id`` is the
  virtual location's ``valuation_in_account_id`` **or**
  ``valuation_out_account_id`` (``:40``), and **merges** rather than assigns
  (``:41-44``), so a pre-existing key would survive.
* ``models/stock_move.py:79-98`` (the ``UAT`` v19 port) — the hook moved down
  to ``_get_account_move_line_vals()`` and the account test became
  ``line_val.get('account_id') in virtual_locations.valuation_account_id.ids``
  (``:92``), because v19 folded the two accounts into one.

Core Odoo 17 — which line is which, and why the workbook's step 8 names the
wrong account:

* ``stock/models/stock_quant.py:1050-1073`` — ``_apply_inventory``. A
  **decrease** moves ``quant.location_id`` → ``property_stock_inventory``
  (``:1061-1066``); an **increase** moves the other way (``:1056-1060``).
  ``_get_inventory_move_values`` sets ``'picked': True`` (``:1283``), which is
  what makes the move valued at all.
* ``stock_account/models/stock_move.py:392-393`` — ``_get_src_account`` =
  ``location_id.``**``valuation_out_account_id``**;
  ``:395-399`` — ``_get_dest_account`` =
  ``location_dest_id.``**``valuation_in_account_id``** when the destination
  usage is ``production``/``inventory``.
* ``:564-600`` — ``_account_entry_move``. Early bail
  ``if self.product_id.type != 'product': return am_vals`` (``:568-570``), so
  on v17 the fixture product must be storable. ``_is_out()`` posts
  ``_prepare_account_move_vals(acc_valuation, acc_dest, …)`` (``:592``) and
  ``_is_in()`` posts ``(acc_src, acc_valuation)`` (``:584``); the signature is
  ``(credit_account_id, debit_account_id, …)`` (``:526``).
* ``:469-516`` — ``_generate_valuation_lines_data`` returns exactly
  ``credit_line_vals`` + ``debit_line_vals``; the third
  ``price_diff_line_vals`` appears only when ``credit_value != debit_value``
  (``:499``), which an adjustment never produces. Hence "exactly two lines".
* ``stock_account/models/stock_valuation_layer.py:73-87`` — the entries are
  ``create``d and ``_post``ed per valuation layer.
* ``account/models/account_move.py:3939`` — ``_post`` ends with
  ``to_post.line_ids._create_analytic_lines()``
  (``account/models/account_move_line.py:3186-3196``), which is what puts the
  tag in the analytic ledger. The amount is
  ``-self.balance * distribution / 100`` (``:3222-3224``), so a **debit**
  counterpart indexes as a **negative** analytic amount and a **credit**
  counterpart as a positive one. Step 10 states a magnitude, not a sign, and
  is asserted as a magnitude; the signed value is recorded.

**WORKBOOK CORRECTION (step 8).** The workbook names
``valuation_out_account_id`` as the write-off counterpart. For a **decrease**
it is ``valuation_in_account_id`` (``stock_account/models/stock_move.py
:395-399``); ``valuation_out_account_id`` is step 11's **increase** case
(``:392-393``). The *expected result* — "the counterpart line carries
``loc_ad``, the Stock Valuation line does not" — is untouched; only the field
name is corrected, exactly as the workbook's own closing note predicts ("a
naive rebuild that tags 'the debit line' rather than 'the counterpart line'
passes step 8 and fails step 11"). The fixture therefore sets **both**
accounts, because the override tags a line whose account is *either*
(``dto_account/models/stock_move.py:40``).

Version shape — probed, never branched on
-----------------------------------------
The two valuation-account fields are a v17 fact
(``stock_account/models/stock_location.py:10-23``); v19 folded them into a
single ``valuation_account_id`` (v19 ``stock_account/models/stock_location.py
:11``) and drives both directions off it (v19
``stock_account/models/stock_move.py:229-249``). ``_valuation_account_fields``
below resolves the field name(s) from ``fields_get`` on the **running
server**, never from ``ctx.env.version`` and never from a source grep — the
same capability-probe pattern as ``common.is_v19_product_shape``. It is a
private helper rather than a shared ``common.py`` gate because any gate that
hard-coded the v17 pair would report "dto_account has nothing to tag" on a
correctly ported v19 target, which is false.

v19 adds one more gate that this fixture must satisfy:
``_should_create_account_move`` requires ``is_storable and is_valued`` **and**
a ``valuation_account_id`` on one of the two locations (v19
``stock_account/models/stock_move.py:661-669``). Step 12's *untagged*
location therefore carries the same valuation accounts as TD-L-06 and differs
**only** in having no ``location_analytic_distribution`` — which isolates the
variable the step is actually about and keeps an entry being posted at all.

Fixture design
--------------
* **TD-L-06** — a namespaced virtual ``usage='inventory'`` location created by
  ``common.make_virtual_inventory_location``, tagged with one analytic account
  per plan. The workbook's Consumables + CC 202000 are two accounts on **two
  different plans** — ``dto_account/data/analytic_plan_data.xml:3-17`` ships
  ``Cost Center`` and ``Spend Category``, and
  ``data/account.analytic.account.csv:2,45`` ships ``202000`` and
  ``Consumables`` on them. The fixture creates **namespaced** accounts on
  those same two plans rather than borrowing the shipped ones: the shipped
  accounts carry live analytic history, which would make "a new analytic line
  of 50.00 appeared" a live-data assertion (convention rule 5). The shipped
  pair is resolved read-only and logged so the mapping stays visible.
* **TD-P-04** — a namespaced storable product in a **real-time** valuation
  category (``common.require_realtime_category``), ``standard_price = 10.00``,
  stocked with 20 units through a validated picking
  (``common.add_stock``) so the staging never runs the inventory-count path
  the case is measuring. 5 units then value at exactly 50.00 under *every*
  cost method: ``standard``/``average`` use ``standard_price``
  (``stock_account/models/product.py:187-205``) and ``fifo`` consumes layers
  that were all created at ``_get_price_unit() = standard_price``
  (``stock_account/models/stock_move.py:44-59``).
* **TD-L-03** — a namespaced internal child of the warehouse stock location.
  No live location is ever stocked, flagged or renamed.
* The counterpart accounts are **existing** accounts (``common
  .pick_counterpart_accounts``), excluding the category's own stock-valuation
  account so step 7 can distinguish a tagged line from an untagged one. They
  are reused rather than created because a posted entry pins its accounts.

Known, unavoidable residue: the three applied adjustments post **three
``account.move`` records in ``posted`` state**, which no teardown may delete.
That is inherent to any test of a valuation hook. Nothing pre-existing is
modified: the sweep removes (or archives) only token-scoped fixtures.

The postcondition "reverse the adjustment or restore the on-hand quantity" is
satisfied by the namespace sweep — the fixture product, its quant and its
locations cease to exist, so no live stock position is left disturbed. No
other case in this suite consumes this one's fixtures (convention rule 5).

EXPECTED v17 OUTCOME: PASS — the v17 hook, the two valuation accounts and the
two-line entry all exist on the baseline, and every expectation is computed
from the fixture rather than from the clock or from record ids. On v19 the
case runs unchanged **iff** ``dto_account`` has been ported: the un-ported
module is dead code there (``_account_entry_move`` no longer exists), so the
counterpart line comes back untagged and steps 8 and 11 fail loudly — which
is the finding, not a test defect.
"""
from framework.registry import test_case
from tests.wf021.common import (LEVEL_D_XMLID, OdooRPCError, WORKFLOW,
                                WORKFLOW_NAME, add_stock, analytic_distribution,
                                analytic_lines_for, analytic_plan, apply_count,
                                enter_count, internal_locations,
                                make_analytic_account,
                                make_virtual_inventory_location, make_product,
                                move_line_rows, move_lines_for, m2o_id,
                                open_namespace, pick_counterpart_accounts,
                                quant_of, quant_state, realtime_category_data,
                                require_no_tier_definition,
                                require_stock_manager, safe_sweep,
                                set_inventory_location, tag, trace,
                                valuation_moves_for)

# --------------------------------------------------------------------------
# The money. 20 units at 10.00 staged, 5 units adjusted = exactly 50.00 — the
# figure the workbook's expected-result table is written in.
# --------------------------------------------------------------------------
UNIT_COST = 10.0
ON_HAND = 20.0
ADJUST_QTY = 5.0
WRITE_OFF = 50.0

#: dto_account/data/analytic_plan_data.xml:3-17 — TD-L-06's two plans.
#: "Consumables" is a Spend Category; "CC 202000" is a Cost Center.
PLAN_SPEND_CATEGORY = "dto_account.spend_category_analytic_plan"
PLAN_COST_CENTER = "dto_account.cost_center_analytic_plan"
#: dto_account/data/account.analytic.account.csv:45 and :2 — the real records
#: the workbook names. Resolved READ-ONLY, logged, never written to and never
#: used in a distribution (they carry live analytic history).
SHIPPED_CONSUMABLES = "dto_account.analytic_account_spend_category_consumables"
SHIPPED_COST_CENTER_202000 = "dto_account.analytic_account_cost_center_202000"


# ===========================================================================
# Private helpers — only what tests/wf021/common.py does not already provide
# ===========================================================================
def _valuation_account_fields(ctx) -> dict:
    """Which ``stock.location`` valuation-account field(s) the TARGET carries.

    v17 ships a pair — ``valuation_in_account_id`` /
    ``valuation_out_account_id`` (``stock_account/models/stock_location.py
    :10-23``) — and core picks a different one per direction
    (``stock_account/models/stock_move.py:392-399``). v19 folded them into a
    single ``valuation_account_id`` (v19 ``stock_account/models/
    stock_location.py:11``) used for both directions (v19
    ``stock_account/models/stock_move.py:229-249``).

    Resolved from ``fields_get`` on the running server — a capability probe,
    not a version branch (``common.is_v19_product_shape`` is the same
    pattern). A shared gate hard-coding the v17 pair is deliberately NOT used
    here: it would block a correctly ported v19 target with a reason that is
    false there (``common.py`` carries a note saying so where such a gate
    would otherwise live).
    """
    rpc = ctx.adapter.rpc
    has_pair = all(rpc.field_exists("stock.location", name) for name in
                   ("valuation_in_account_id", "valuation_out_account_id"))
    if has_pair:
        return {"decrease": "valuation_in_account_id",
                "increase": "valuation_out_account_id",
                "shape": "v17 pair (valuation_in/out_account_id)"}
    if rpc.field_exists("stock.location", "valuation_account_id"):
        return {"decrease": "valuation_account_id",
                "increase": "valuation_account_id",
                "shape": "v19 single (valuation_account_id)"}
    ctx.blocked(
        f"stock.location carries neither the v17 pair "
        f"(valuation_in_account_id / valuation_out_account_id, "
        f"stock_account/models/stock_location.py:10-23) nor the v19 single "
        f"valuation_account_id (v19 :11) on {ctx.env.key} (db={ctx.env.db}) "
        "— stock_account is not installed, so an applied adjustment has no "
        "counterpart account for dto_account/models/stock_move.py:40 to "
        "match and there is no line for this case to inspect.")


def _require_tagging_surface(ctx) -> dict:
    """BLOCK unless dto_account's location-analytic surface is present.

    Returns the valuation-account field map from
    ``_valuation_account_fields``.
    """
    rpc = ctx.adapter.rpc
    missing = []
    if not rpc.field_exists("stock.location", "location_analytic_distribution"):
        missing.append("stock.location.location_analytic_distribution")
    if not rpc.field_exists("account.move.line", "analytic_distribution"):
        missing.append("account.move.line.analytic_distribution")
    if missing:
        ctx.blocked(
            f"The location-analytic surface is absent on {ctx.env.key} "
            f"(db={ctx.env.db}) — missing: {', '.join(missing)}. "
            "dto_account/models/stock_location.py:7-11 adds "
            "location_analytic_distribution and the analytic.mixin; without "
            "it dto_account/models/stock_move.py:32-33 bails out on every "
            "move and there is no tag for this case to find.")
    return _valuation_account_fields(ctx)


def _cycle_level_id(ctx):
    """A ``cycle.count.category`` id, or ``None`` when the module is absent.

    TC251 is a ``dto_account`` case, but the apply it drives runs through
    ``dto_cycle_count``'s ``_apply_inventory`` override when that module is
    installed, and that override calls
    ``cycle.count.category._calculate_scheduled_count_date`` on the quant's
    related level — a method that opens with ``ensure_one()``
    (``dto_cycle_count/models/cycle_count_category.py:23``). A levelless
    product therefore makes the apply raise ``ValueError: Expected
    singleton``, which has nothing to do with what TC251 measures.

    This is a PROBE rather than ``common.require_cycle_count``: if
    ``dto_cycle_count`` is not contributing, the apply is pure core, needs no
    level, and blocking a dto_account case on a dto_cycle_count precondition
    would be wrong.
    """
    rpc = ctx.adapter.rpc
    if not rpc.model_exists("cycle.count.category"):
        return None
    if not rpc.field_exists("product.product", "cycle_count_category_id"):
        return None
    level_id = rpc.ref(LEVEL_D_XMLID)
    if level_id:
        return level_id
    found = rpc.search("cycle.count.category", [], limit=1, order="id")
    if found:
        return found[0]
    ctx.blocked(
        f"dto_cycle_count is contributing to {ctx.env.key} (db={ctx.env.db}) "
        "but cycle.count.category holds no rows and "
        f"{LEVEL_D_XMLID} does not resolve. Its _apply_inventory override "
        "(models/stock_quant.py:17-21) reads the quant's related level and "
        "calls _calculate_scheduled_count_date, which opens with "
        "ensure_one() (models/cycle_count_category.py:23) — so every apply "
        "this case performs would raise 'Expected singleton' before a single "
        "journal item existed.")


def _analytic_account_on_plan(ctx, label: str, plan_xmlid: str) -> tuple:
    """A namespaced ``account.analytic.account`` on a NAMED plan.

    ``common.make_analytic_account`` always lands on the FIRST plan by id
    (``common.analytic_plan``), which would put both of TD-L-06's accounts in
    one plan. That matters: ``_prepare_analytic_distribution_line`` groups by
    ``root_plan_id`` (``account/models/account_move_line.py:3220-3225``), and
    the workbook's TD-L-06 names one account per plan — Consumables is a
    Spend Category, CC 202000 is a Cost Center
    (``dto_account/data/analytic_plan_data.xml:12,3``).

    Returns ``(account_id, plan_id)``; falls back to
    ``common.make_analytic_account`` when the named plan does not resolve, so
    a database without ``dto_account``'s plan data still runs the case with a
    single-plan distribution rather than blocking a P0.
    """
    rpc = ctx.adapter.rpc
    plan_id = rpc.ref(plan_xmlid)
    if plan_id and rpc.field_exists("account.analytic.account", "plan_id"):
        return rpc.create("account.analytic.account",
                          {"name": tag(label), "plan_id": plan_id}), plan_id
    ctx.log(f"[note] {plan_xmlid} does not resolve — falling back to the "
            f"first analytic plan (id {analytic_plan(rpc)}) for {label!r}")
    return make_analytic_account(rpc, label), analytic_plan(rpc)


def _apply_capturing(rpc, quant_ids) -> tuple:
    """Press Apply and report ``(raised, message, action)`` instead of raising.

    Two things are being captured at once, and both are assertions the
    workbook needs:

    * ``raised`` — step 12's "no error is raised" (never a bare
      ``AssertionError``, never a bare ``except``);
    * ``action`` — ``action_apply_inventory`` returns a WIZARD DICT instead of
      applying when a quant ``is_outdated`` or a tracked product has no lot
      (v17 ``stock/models/stock_quant.py:461-480``). A falsy return is the
      only proof it reached ``self._apply_inventory()`` (``:483``).
    """
    try:
        return False, "", apply_count(rpc, quant_ids)
    except OdooRPCError as exc:
        return True, str(exc), None


def _norm_dist(value) -> dict:
    """A Json analytic distribution, normalised for a BY-VALUE comparison.

    ``analytic_distribution`` is ``fields.Json`` on ``analytic.mixin``
    (``analytic/models/analytic_mixin.py:13-16``) and
    ``location_analytic_distribution`` is a plain ``fields.Json``
    (``dto_account/models/stock_location.py:11``). Keys are account-id
    strings and values are percentages; a round trip through JSON can turn
    ``100`` into ``100.0`` and back. Step 8 asks for equality "by value", so
    both sides are normalised the same way — this narrows nothing, it only
    removes a representation difference that is not the subject.
    """
    if not value:
        return {}
    return {str(key): float(amount) for key, amount in value.items()}


def _line_shape(row, dist=True) -> dict:
    """One journal item as a flat dict, for a single ``ctx.check``.

    Mismatch dicts, not assertion loops: account, debit, credit and the tag
    are asserted together so one failure reports every difference.
    """
    shape = {"account_id": row["account_id"],
             "debit": round(row["debit"], 2),
             "credit": round(row["credit"], 2)}
    if dist:
        shape["analytic_distribution"] = _norm_dist(row["analytic_distribution"])
    return shape


def _split_lines(rows, counterpart_account_id) -> tuple:
    """``(counterpart_row, valuation_row)`` keyed on the counterpart account.

    Returns ``(None, None)`` when the split is not one-and-one, so the caller
    reports the whole row set rather than indexing into it.
    """
    counterpart = [r for r in rows if r["account_id"] == counterpart_account_id]
    other = [r for r in rows if r["account_id"] != counterpart_account_id]
    if len(counterpart) != 1 or len(other) != 1:
        return None, None
    return counterpart[0], other[0]


def _entry_for(ctx, product_id, before_move_ids) -> list:
    """The valuation ``account.move`` ids that appeared since the baseline.

    Scoped by a baseline captured in the SAME test run — ids are never relied
    on across tests (convention rule 5). ``common.valuation_moves_for``
    resolves them through ``account.move.line.product_id``, which every
    valuation line carries (``stock_account/models/stock_move.py:473-480``).
    """
    move_ids = valuation_moves_for(ctx.adapter.rpc, product_id,
                                   exclude_ids=before_move_ids)
    ctx.check("exactly one new valuation journal entry", 1, len(move_ids))
    return move_ids


def _valuation_snapshot(rpc, product_id) -> dict:
    """Best-effort ``{quantity_svl, value_svl, standard_price}`` for the log.

    ``quantity_svl`` / ``value_svl`` are non-stored computes over
    ``stock.valuation.layer``; a session without layer read rights gets an
    ``OdooRPCError`` rather than a value. This is step 2's *record*, not an
    assertion, so the failure is logged and the case proceeds — the money is
    asserted on the journal entry itself in steps 6-9.
    """
    try:
        row = rpc.read("product.product", [product_id],
                       ["standard_price", "quantity_svl", "value_svl"])[0]
        return {"standard_price": row.get("standard_price"),
                "quantity_svl": row.get("quantity_svl"),
                "value_svl": row.get("value_svl")}
    except OdooRPCError as exc:
        return {"error": str(exc)}


@test_case(
    id="TEST-WF021-TC251",
    name="Inventory adjustment through a tagged virtual location",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account",
    priority="P0", kind="API", order=21251,
    description="A 50.00 write-off through a tagged virtual inventory "
                "location posts exactly two lines: the Stock Valuation credit "
                "stays analytically clean and the counterpart debit carries "
                "the location's distribution verbatim; the roles swap on an "
                "increase, and an untagged location leaves both lines clean "
                "without raising.",
    traceability=trace("DATAONE-TC251"))
def test_tc251(ctx):
    rpc = ctx.adapter.rpc

    # Preconditions, each with its own precise BLOCKED reason. Probed, never
    # assumed — see AUTOMATION_CONVENTIONS hard rule 6.
    accounts_fields = _require_tagging_surface(ctx)
    require_stock_manager(ctx)          # v17 stock_quant.py:1052-1053
    require_no_tier_definition(ctx)     # flow A1: Apply is immediate
    category = realtime_category_data(ctx)
    level_id = _cycle_level_id(ctx)

    open_namespace(ctx)
    try:
        with ctx.step("Preconditions — TD-L-06 (tagged virtual inventory "
                      "location), TD-P-04 (real-time product) and TD-L-03 "
                      "(internal source)"):
            ctx.log(f"valuation-account shape on the target: "
                    f"{accounts_fields['shape']}")
            ctx.log(f"real-time category: {category['name']!r} "
                    f"(cost method {category['cost_method']!r}, valuation "
                    f"account {category['valuation_account_id']})")
            # Read-only: prove the workbook's referents exist, and never use
            # them in a distribution — they carry live analytic history.
            ctx.log("workbook referents (read-only): "
                    f"{SHIPPED_CONSUMABLES} -> "
                    f"{rpc.ref(SHIPPED_CONSUMABLES)}, "
                    f"{SHIPPED_COST_CENTER_202000} -> "
                    f"{rpc.ref(SHIPPED_COST_CENTER_202000)}")
            # A live account.analytic.distribution.model can set a
            # distribution on ANY posted line it matches
            # (account/models/account_move_line.py:1166-1180). It cannot
            # touch a line whose distribution was supplied in create(), but a
            # step-7 failure on a target that has such models is worth being
            # able to read off the log.
            if rpc.model_exists("account.analytic.distribution.model"):
                ctx.log("account.analytic.distribution.model rows on the "
                        "target: "
                        f"{rpc.call('account.analytic.distribution.model', 'search_count', [])}")

            spend_id, spend_plan = _analytic_account_on_plan(
                ctx, "AA-CONSUMABLES", PLAN_SPEND_CATEGORY)
            cc_id, cc_plan = _analytic_account_on_plan(
                ctx, "AA-CC202000", PLAN_COST_CENTER)
            tagged_accounts = [spend_id, cc_id]
            # One account per PLAN at 100% — not 100% shared between them
            # (common.analytic_distribution's `split=False` default).
            loc_ad_written = analytic_distribution(tagged_accounts)
            ctx.log(f"distribution to hang on TD-L-06: {loc_ad_written} "
                    f"(plans {spend_plan} / {cc_plan})")

            # Counterpart accounts: existing, and never the category's own
            # stock-valuation account — otherwise step 7 could not tell a
            # tagged line from an untagged one.
            counterparts = pick_counterpart_accounts(
                ctx, count=2, exclude_ids=[category["valuation_account_id"]])
            if accounts_fields["decrease"] == accounts_fields["increase"]:
                acc_decrease = acc_increase = counterparts[0]
            else:
                acc_decrease, acc_increase = counterparts[0], counterparts[1]

            loc_tagged = make_virtual_inventory_location(
                ctx, "TD-L-06", analytic_distribution=loc_ad_written)
            rpc.write("stock.location", [loc_tagged],
                      {accounts_fields["decrease"]: acc_decrease,
                       accounts_fields["increase"]: acc_increase})

            # TD-L-03 stand-in: a namespaced internal child of the warehouse
            # stock location. No live location is ever stocked.
            source_loc = internal_locations(ctx, count=1)[0]

            product_id = make_product(
                ctx, "CMP-CONN-A", storable=True,
                categ_id=category["id"], level_id=level_id,
                extra={"standard_price": UNIT_COST})
            set_inventory_location(rpc, product_id, loc_tagged)
            add_stock(ctx, product_id, source_loc, ON_HAND)

            quant_id = quant_of(rpc, product_id, source_loc)
            ctx.check_true("a quant exists in the internal source location",
                           bool(quant_id), f"quant_id={quant_id}")

        with ctx.step("Assert TD-L-06.usage == 'inventory' and TD-L-06."
                      "location_analytic_distribution is non-empty; record "
                      "its value as loc_ad"):
            # dict.fromkeys: on the v19 single-account shape "decrease" and
            # "increase" are the SAME field name, and a read() list must not
            # repeat it.
            loc_fields = list(dict.fromkeys(
                ["usage", "location_analytic_distribution",
                 accounts_fields["decrease"], accounts_fields["increase"]]))
            loc_row = rpc.read("stock.location", [loc_tagged], loc_fields)[0]
            loc_ad = _norm_dist(loc_row["location_analytic_distribution"])
            ctx.check("TD-L-06 shape: inventory usage, a non-empty "
                      "distribution and both counterpart accounts",
                      {"usage": "inventory",
                       "distribution": _norm_dist(loc_ad_written),
                       "non_empty": True,
                       accounts_fields["decrease"]: acc_decrease,
                       accounts_fields["increase"]: acc_increase},
                      {"usage": loc_row["usage"],
                       "distribution": loc_ad,
                       "non_empty": bool(loc_ad),
                       accounts_fields["decrease"]:
                           m2o_id(loc_row[accounts_fields["decrease"]]),
                       accounts_fields["increase"]:
                           m2o_id(loc_row[accounts_fields["increase"]])})
            ctx.log(f"loc_ad = {loc_ad}")

        with ctx.step("Record the product's current valuation and on-hand "
                      "quantity"):
            before = quant_state(rpc, [quant_id])[quant_id]
            ctx.check("on-hand is the staged quantity", ON_HAND,
                      before["quantity"])
            ctx.check("the product's inventory-loss counterpart is TD-L-06",
                      loc_tagged,
                      m2o_id(rpc.read("product.product", [product_id],
                                      ["property_stock_inventory"])[0]
                             ["property_stock_inventory"]))
            ctx.log(f"valuation snapshot: "
                    f"{_valuation_snapshot(rpc, product_id)}")
            # Baselines for every "what appeared since" question below.
            base_moves = valuation_moves_for(rpc, product_id)
            base_lines = {row["id"] for row in
                          move_lines_for(rpc, product_id)}
            base_analytic = {row["id"] for row in
                             analytic_lines_for(rpc, tagged_accounts)}
            ctx.log(f"baseline: {len(base_moves)} valuation entries, "
                    f"{len(base_lines)} stock move lines, "
                    f"{len(base_analytic)} analytic lines")

        with ctx.step("Perform an inventory adjustment reducing on-hand by a "
                      "quantity worth exactly 50.00 at current valuation, "
                      "through TD-L-06"):
            enter_count(rpc, quant_id, ON_HAND - ADJUST_QTY)
            counted = quant_state(rpc, [quant_id])[quant_id]
            unit_cost = rpc.read("product.product", [product_id],
                                 ["standard_price"])[0]["standard_price"]
            ctx.check("the counted quantity books a 5-unit shortfall worth "
                      "50.00",
                      {"inventory_quantity": ON_HAND - ADJUST_QTY,
                       "inventory_diff_quantity": -ADJUST_QTY,
                       "inventory_quantity_set": True,
                       "unit_cost": UNIT_COST,
                       "value": WRITE_OFF},
                      {"inventory_quantity": counted["inventory_quantity"],
                       "inventory_diff_quantity":
                           counted["inventory_diff_quantity"],
                       "inventory_quantity_set":
                           counted["inventory_quantity_set"],
                       "unit_cost": unit_cost,
                       "value": round(abs(counted["inventory_diff_quantity"])
                                      * unit_cost, 2)})

        with ctx.step("Apply the adjustment"):
            raised, message, action = _apply_capturing(rpc, [quant_id])
            ctx.check("Apply reached _apply_inventory — no error and no "
                      "wizard", (False, "", False),
                      (raised, message, bool(action)))
            applied = quant_state(rpc, [quant_id])[quant_id]
            ctx.check("on-hand fell by the adjusted quantity",
                      ON_HAND - ADJUST_QTY, applied["quantity"])
            # The move must actually have gone through TD-L-06, or every tag
            # assertion below would be measuring the company's default
            # inventory-loss location instead.
            new_lines = [r for r in move_lines_for(rpc, product_id)
                         if r["id"] not in base_lines]
            ctx.check("the write-off move line runs from the internal "
                      "location into TD-L-06",
                      [{"location_id": source_loc,
                        "location_dest_id": loc_tagged,
                        "quantity": ADJUST_QTY}],
                      [{"location_id": m2o_id(r["location_id"]),
                        "location_dest_id": m2o_id(r["location_dest_id"]),
                        "quantity": r["quantity"]} for r in new_lines])
            base_lines |= {r["id"] for r in new_lines}

        with ctx.step("Locate the resulting valuation journal entry"):
            move_ids = _entry_for(ctx, product_id, base_moves)
            rows = move_line_rows(rpc, move_ids)
            ctx.log(f"entry {move_ids[0]}: "
                    f"{[(r['account_id'], r['debit'], r['credit']) for r in rows]}")

        with ctx.step("Assert exactly two lines"):
            # _generate_valuation_lines_data returns credit_line_vals +
            # debit_line_vals; price_diff_line_vals appears only when
            # credit_value != debit_value (stock_account/models/
            # stock_move.py:499, vals at :506), which an adjustment never
            # produces.
            ctx.check("the valuation entry has exactly two journal items", 2,
                      len(rows))
            counterpart_row, valuation_row = _split_lines(rows, acc_decrease)
            ctx.check_true(
                "the two lines split one-and-one on the counterpart account",
                counterpart_row is not None and valuation_row is not None,
                f"counterpart account {acc_decrease}; rows="
                f"{[_line_shape(r) for r in rows]}")

        with ctx.step("Assert the Stock Valuation line — credit 50.00, and "
                      "its analytic_distribution is empty / untouched"):
            # WF-008's table is explicit: the stock-valuation line gets no
            # tag. Tagging both sides double-counts the cost centre in the
            # analytic ledger while leaving the general ledger correct, which
            # no balance check catches.
            ctx.check("Stock Valuation: credited 50.00, analytically clean",
                      {"account_id": category["valuation_account_id"],
                       "debit": 0.0, "credit": WRITE_OFF,
                       "analytic_distribution": {}},
                      _line_shape(valuation_row))

        with ctx.step("Assert the counterpart line — the location's Inventory "
                      "Adjustment account, debit 50.00, and its "
                      "analytic_distribution equals loc_ad by value"):
            # WORKBOOK CORRECTION: for a DECREASE the counterpart account is
            # the destination's valuation_in_account_id
            # (stock_account/models/stock_move.py:395-399), not
            # valuation_out_account_id — that is step 11's increase case
            # (:392-393). The expectation itself is unchanged.
            ctx.check("counterpart: the location's Inventory Adjustment "
                      "account, debited 50.00 and tagged with loc_ad",
                      {"account_id": acc_decrease,
                       "debit": WRITE_OFF, "credit": 0.0,
                       "analytic_distribution": loc_ad},
                      _line_shape(counterpart_row))

        with ctx.step("Assert the entry balances at 50.00 / 50.00"):
            ctx.check("debits and credits both total 50.00",
                      {"debit": WRITE_OFF, "credit": WRITE_OFF},
                      {"debit": round(sum(r["debit"] for r in rows), 2),
                       "credit": round(sum(r["credit"] for r in rows), 2)})

        with ctx.step("Assert the analytic ledger indexed it — an "
                      "account.analytic.line exists for CC 202000 of 50.00"):
            # account.move._post() ends with line_ids._create_analytic_lines()
            # (account/models/account_move.py:3939), and the amount is
            # -balance * distribution / 100 (account_move_line.py:3222-3224).
            # The counterpart here is a DEBIT, so the ledger indexes -50.00;
            # the workbook states a magnitude, so a magnitude is asserted and
            # the signed value is recorded.
            analytic_rows = [row for row in
                             analytic_lines_for(rpc, tagged_accounts)
                             if row["id"] not in base_analytic]
            ctx.log(f"new analytic lines: "
                    f"{[(r['id'], r['name'], r['amount']) for r in analytic_rows]}")
            ctx.check("one analytic line per tagged plan, each of 50.00",
                      {"lines": len(tagged_accounts),
                       "magnitudes": [WRITE_OFF] * len(tagged_accounts)},
                      {"lines": len(analytic_rows),
                       "magnitudes": sorted(round(abs(r["amount"]), 2)
                                            for r in analytic_rows)})
            base_analytic |= {r["id"] for r in analytic_rows}

        with ctx.step("Direction variant — an increase. Perform an adjustment "
                      "increasing stock by 50.00 through the same location; "
                      "assert the counterpart line (now a credit) carries "
                      "loc_ad and the stock-valuation debit does not"):
            # Step 11 exists because the debit/credit roles swap on an
            # increase: a rebuild that tags "the debit line" rather than "the
            # counterpart line" passes step 8 and fails here. Core takes the
            # OTHER account for this direction — acc_src =
            # location_id.valuation_out_account_id (stock_account/models/
            # stock_move.py:392-393), posted as the CREDIT account (:584).
            base_moves = valuation_moves_for(rpc, product_id)
            enter_count(rpc, quant_id, ON_HAND)
            raised, message, action = _apply_capturing(rpc, [quant_id])
            ctx.check("the increase applied — no error and no wizard",
                      (False, "", False), (raised, message, bool(action)))
            ctx.check("on-hand is back to the staged quantity", ON_HAND,
                      quant_state(rpc, [quant_id])[quant_id]["quantity"])

            up_rows = move_line_rows(rpc,
                                     _entry_for(ctx, product_id, base_moves))
            ctx.check("the increase entry has exactly two journal items", 2,
                      len(up_rows))
            up_counterpart, up_valuation = _split_lines(up_rows, acc_increase)
            ctx.check_true(
                "the increase splits one-and-one on the counterpart account",
                up_counterpart is not None and up_valuation is not None,
                f"counterpart account {acc_increase}; rows="
                f"{[_line_shape(r) for r in up_rows]}")
            ctx.check("increase: the counterpart is CREDITED 50.00 and "
                      "carries loc_ad; Stock Valuation is debited and stays "
                      "clean",
                      {"counterpart": {"account_id": acc_increase,
                                       "debit": 0.0, "credit": WRITE_OFF,
                                       "analytic_distribution": loc_ad},
                       "valuation": {
                           "account_id": category["valuation_account_id"],
                           "debit": WRITE_OFF, "credit": 0.0,
                           "analytic_distribution": {}}},
                      {"counterpart": _line_shape(up_counterpart),
                       "valuation": _line_shape(up_valuation)})
            ctx.check("the increase entry balances at 50.00 / 50.00",
                      {"debit": WRITE_OFF, "credit": WRITE_OFF},
                      {"debit": round(sum(r["debit"] for r in up_rows), 2),
                       "credit": round(sum(r["credit"] for r in up_rows), 2)})

            up_analytic = [row for row in
                           analytic_lines_for(rpc, tagged_accounts)
                           if row["id"] not in base_analytic]
            ctx.log(f"increase analytic lines: "
                    f"{[(r['id'], r['amount']) for r in up_analytic]}")
            ctx.check("the increase indexes one analytic line per tagged "
                      "plan, each of 50.00",
                      {"lines": len(tagged_accounts),
                       "magnitudes": [WRITE_OFF] * len(tagged_accounts)},
                      {"lines": len(up_analytic),
                       "magnitudes": sorted(round(abs(r["amount"]), 2)
                                            for r in up_analytic)})
            base_analytic |= {r["id"] for r in up_analytic}

        with ctx.step("Negative — untagged location. Repeat through a virtual "
                      "inventory location with no "
                      "location_analytic_distribution; assert both lines have "
                      "empty distributions and no error is raised"):
            # The untagged location carries the SAME valuation accounts and
            # differs ONLY in having no distribution, which isolates the
            # variable. It also keeps an entry being posted at all on v19,
            # where _should_create_account_move requires a valuation account
            # on one of the two locations (v19 stock_account/models/
            # stock_move.py:661-669).
            loc_plain = make_virtual_inventory_location(ctx, "TD-L-06-PLAIN")
            rpc.write("stock.location", [loc_plain],
                      {accounts_fields["decrease"]: acc_decrease,
                       accounts_fields["increase"]: acc_increase})
            plain_row = rpc.read("stock.location", [loc_plain],
                                 ["usage",
                                  "location_analytic_distribution"])[0]
            ctx.check("the control location is an untagged inventory location",
                      {"usage": "inventory", "distribution": {}},
                      {"usage": plain_row["usage"],
                       "distribution": _norm_dist(
                           plain_row["location_analytic_distribution"])})

            set_inventory_location(rpc, product_id, loc_plain)
            base_moves = valuation_moves_for(rpc, product_id)
            enter_count(rpc, quant_id, ON_HAND - ADJUST_QTY)
            raised, message, action = _apply_capturing(rpc, [quant_id])
            ctx.check("the untagged adjustment applies with no error and no "
                      "wizard", (False, "", False),
                      (raised, message, bool(action)))

            plain_rows = move_line_rows(
                rpc, _entry_for(ctx, product_id, base_moves))
            ctx.check("the untagged entry has exactly two journal items", 2,
                      len(plain_rows))
            # dto_account/models/stock_move.py:32-33 bails out when the
            # virtual location has no distribution, so BOTH lines keep the
            # empty distribution core gave them.
            ctx.check("both lines of the untagged entry are analytically "
                      "clean and it still balances at 50.00 / 50.00",
                      {"distributions": [{}, {}],
                       "debit": WRITE_OFF, "credit": WRITE_OFF},
                      {"distributions": [_norm_dist(r["analytic_distribution"])
                                         for r in plain_rows],
                       "debit": round(sum(r["debit"] for r in plain_rows), 2),
                       "credit": round(sum(r["credit"]
                                           for r in plain_rows), 2)})
            plain_analytic = [row for row in
                              analytic_lines_for(rpc, tagged_accounts)
                              if row["id"] not in base_analytic]
            ctx.check("the untagged adjustment indexed nothing in the "
                      "analytic ledger", 0, len(plain_analytic))
    finally:
        # Convention rule 3: a teardown that can never raise. The three
        # applied adjustments leave three POSTED account.move records, which
        # no teardown may delete — inherent to testing a valuation hook.
        try:
            safe_sweep(ctx)
        except Exception:  # noqa: BLE001
            pass
