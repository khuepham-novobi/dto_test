"""DATAONE-WF-024 — the RMA menus and the three RMA queues: TC188, TC190.

Both cases are about ``stock_picking_auto_create_lot/views/stock_picking.xml``
and nothing else. Everything asserted below was read out of that file, out of
the two core trees, or off the target over RPC — never inferred.

What the module actually ships
------------------------------
* ``views/stock_picking.xml:138-140`` — **exactly one** ``menuitem``,
  ``rma_picking``: ``name="RMAs"``, ``parent="stock.menu_stock_transfers"``,
  ``action="action_picking_tree_rma"``, ``sequence="19"``,
  ``groups="stock.group_stock_manager,stock.group_stock_user"``. The parent
  exists byte-identically in both trees
  (``stock/views/stock_menu_views.xml:8`` on v17 and on v19).
* ``views/stock_picking.xml:81, 102, 123`` — **three**
  ``ir.actions.act_window`` records: ``action_picking_tree_rma_customer``,
  ``action_picking_tree_rma_vendor``, ``action_picking_tree_rma``. All three
  are ``name="RMAs"``, ``res_model="stock.picking"`` and point their
  ``search_view_id`` (``:93, 114, 129``) at
  ``view_picking_internal_search_inherit``.
* ``views/stock_picking.xml:85, 106, 127`` — the three domains, verbatim::

      [('rma_number','!=',False)]
      [('rma_number','!=',False),('location_id','=',5)]
      [('rma_number','!=',False),('location_dest_id','=',4)]

* ``views/stock_picking.xml:84, 105, 126`` —
  ``view_mode="tree,kanban,form,calendar,activity"`` on all three.
* ``views/stock_picking.xml:31-32`` — the only two lines the hand-copied
  search view adds over core's::

      <filter name="customer_rma" string="Customer RMAs" domain="[('picking_type_code', '=', 'incoming')]"/>
      <filter name="vendor_rma"   string="Vendor RMAs"   domain="[('picking_type_code', '=', 'outgoing')]"/>

  That view carries **no** ``inherit_id`` (``:17-20``), so it is not part of
  the composed ``stock.picking`` search arch and ``get_view`` would hand back
  core's. It is therefore read straight off ``ir.ui.view``
  (``common.search_view_arch``).

Workbook correction, recorded not softened (TC188 step 3)
---------------------------------------------------------
Step 3 says the RMA menu "exposes three actions". It does not. One menuitem
is bound to ``action_picking_tree_rma``; ``action_picking_tree_rma_customer``
and ``action_picking_tree_rma_vendor`` have no menu entry and no binding
anywhere in the module. The step is therefore implemented as "three
``ir.actions.act_window`` records exist, named RMAs, on ``stock.picking``"
plus an explicit record of how many of them are reachable from a menu. That
is a finding about the product, not a weakened expectation.

Why TC188 step 8 is expected to fail on v19
-------------------------------------------
``'tree'`` is a view type on v17 (``odoo-17.0/odoo/addons/base/models/
ir_ui_view.py:163``) and was renamed to ``'list'`` on v19
(``odoo-19.0/odoo/addons/base/models/ir_ui_view.py:149``); ``mail`` adds
``'activity'`` to the same selection in both (``mail/models/ir_ui_view.py:8``).
``_check_view_mode`` only rejects duplicates and whitespace (v19
``ir_actions.py:299-306``), so the unmigrated ``view_mode`` saves cleanly and
the breakage surfaces at view-resolution time. The step therefore asks the
target's own list-view spelling (``fg_common.list_tag``) for reachability —
no version branch, and the v19 answer is the finding.

Why TC190 is expected to fail on any rebuilt database
-----------------------------------------------------
The two directional domains pin locations to bare integers. Those integers
were only ever right on a clean **v17** install, where
``odoo-17.0/addons/stock/data/stock_data.xml`` creates Physical Locations
(``:23``), Partners (``:28``), Virtual Locations (``:34``), Vendors (``:41``)
and Customers (``:48``) in that order. ``odoo-19.0/addons/stock/data/
stock_data.xml`` **removed the Partners parent entirely** and now creates
``stock_location_suppliers`` first (``:23``) and ``stock_location_customers``
second (``:28``), so a fresh install cannot assign 4 and 5, and the complete
names become ``Vendors`` / ``Customers`` rather than ``Partners/…``. The
semantics hold in both versions, so the fix is a one-line ``ref()`` swap —
which is exactly what step 12 asserts.

Fixture shape, and why it is the right shape in both versions
-------------------------------------------------------------
A **customer RMA** is the return of a *delivery*; a **vendor RMA** is the
return of a *receipt*. The return's locations come from the wizard:

* v17 ``stock/wizard/stock_picking_return.py:113-127`` —
  ``location_id = picking.location_dest_id`` and
  ``location_dest_id = wizard.location_id``, which ``_compute_moves_locations``
  (``:74-77``) defaults to ``picking.location_id``.
* v19 ``stock/wizard/stock_picking_return.py:142-159`` —
  ``location_id = picking.location_dest_id``; ``location_dest_id`` is the
  return type's ``default_location_dest_id`` when that type is incoming and
  ``picking.location_id`` otherwise.

So a delivery's return has ``location_id`` = the Customers location and a
receipt's return has ``location_dest_id`` = the Vendors location, on both.
The preconditions step asserts that semantically — ``usage == 'customer'`` /
``usage == 'supplier'`` — rather than against an id, because the id is the
very thing TC190 is measuring.

``rma_number`` is stamped by the fork's own override:
``wizard/stock_picking_return.py:21-25`` — ``_create_return`` calls
``super()``, then ``new_picking.rma_number = new_picking._get_rma_sequence()``
and ``new_picking.note = self.env.company.vendor_refund_narration``. The
second line is WF-024 E1 (an undeclared ``dto_account`` dependency), so both
tests run ``require_vendor_narration`` before creating a single return.

Determinism (convention rule 5)
-------------------------------
The live all-RMAs queue holds production returns. Every queue query below
runs the act_window's **own** domain string, read verbatim off the
``ir.actions.act_window`` record and never retyped, with
``('id','in', <this execution's fixture ids>)`` appended
(``common.queue_members``). Membership and non-membership are asserted;
"exactly N rows" never is. No pre-existing record is modified by either case.

EXPECTED v17 OUTCOME
--------------------
* **TC188: PASS.** ``'tree'`` is a v17 view type, so all five modes resolve.
* **TC190: PASS only if the QA clone still carries the original v17 install
  ids.** On any rebuilt database it **FAILS at step 4**, which is the point of
  the case — the workbook says "Do not soften this case", so step 4 is a plain
  ``ctx.check`` against the literals 5 and 4 and is allowed to abort the run.
  Step 13's findings file is written from a ``finally:`` and names every step
  the abort prevented from running.

EXPECTED v19 OUTCOME
--------------------
* **TC188: FAIL at step 8** — the target's list view type is ``'list'`` and
  the three act_windows still declare ``'tree'``.
* **TC190: FAIL** — a v19 install cannot assign location ids 4 and 5.
"""
from __future__ import annotations

import json

from adapters.base import OdooRPCError
from framework.fg_common import list_tag
from framework.registry import test_case
from tests.wf024.common import (ACTION_ALL_XMLID, ACTION_CUSTOMER_XMLID,
                                ACTION_DOMAINS, ACTION_NAME,
                                ACTION_VENDOR_XMLID, ACTION_VIEW_MODE,
                                ACTION_XMLIDS, CUSTOMER_LOCATION_XMLID,
                                FILTER_CUSTOMER_RMA, FILTER_VENDOR_RMA,
                                HARDCODED_CUSTOMER_LOCATION_ID,
                                HARDCODED_VENDOR_LOCATION_ID, MENU_GROUP_XMLIDS,
                                MENU_NAME, MENU_PARENT_XMLID, MENU_SEQUENCE,
                                MENU_XMLID, MODULE, RMA_ACTION_COUNT,
                                RMA_MENU_COUNT, RMA_NUMBER_RE,
                                SEARCH_VIEW_XMLID, STOCK_MANAGER_GROUP,
                                STOCK_USER_GROUP, VENDOR_LOCATION_XMLID,
                                WORKFLOW, WORKFLOW_NAME, act_window_row,
                                arch_filter, archive_qa_users,
                                available_view_types,
                                confirm_return, domain_has_literal_location_id,
                                fixture_token, m2o_id, make_delivery,
                                make_product, make_receipt, menu_groups_field,
                                menu_row, open_namespace, open_return_wizard,
                                queue_members, require_rma_module,
                                require_vendor_narration, return_of,
                                rma_menu_count, rpc_as_group_user, safe_sweep,
                                search_view_arch, set_return_quantities, trace,
                                visible_menu_ids)

#: The five modes TC188 step 8 names. ``list`` is resolved against the target
#: by ``fg_common.list_tag`` ('tree' on v17, 'list' on v19), so the step
#: carries no version branch of its own.
WORKBOOK_VIEW_MODES = ["list", "kanban", "form", "calendar", "activity"]

#: TC190 step 13 — the five step outcomes the workbook wants recorded.
TC190_RECORDED_STEPS = ["step_04", "step_06", "step_09", "step_11", "step_12"]


# ---------------------------------------------------------------- helpers
# Defined here rather than in common.py: common.py is owned by another agent
# and neither of these is needed by any other case in the suite.

def _dump(ctx, filename: str, payload: dict, label: str):
    """Persist a JSON evidence file next to the run's other artifacts.

    This is the automated form of the workbook's "record … in findings/".
    It never raises: TC190 calls it from a ``finally:`` whose contract is
    that it cannot fail (convention rule 3).
    """
    try:
        path = ctx.artifacts_dir / filename
        path.write_text(json.dumps(payload, indent=2, sort_keys=True,
                                   default=str), encoding="utf-8")
        ctx.add_artifact(path, "log", label)
        ctx.log(f"recorded: {path}")
    except Exception as exc:                                  # noqa: BLE001
        try:
            ctx.log(f"[warn] could not write {filename}: {exc}")
        except Exception:                                     # noqa: BLE001
            pass


def _location_term(domain_str: str, field: str):
    """The value a domain pins ``field`` to, or None when it does not.

    Parsed out of the domain text read off the record, so what is inspected
    is the shipped domain and not a retyped copy of it.
    """
    if not domain_str:
        return None
    try:
        from ast import literal_eval
        terms = literal_eval(domain_str)
    except (ValueError, SyntaxError):
        return None
    for term in terms:
        if isinstance(term, (list, tuple)) and len(term) == 3 \
                and term[0] == field:
            return term[2]
    return None


def _make_rma(ctx, source_picking_id: int, quantities: dict) -> dict:
    """Return the RMA picking created from ``source_picking_id``.

    Quantities are written explicitly instead of relying on the prefill:
    v17 prefills delivered-minus-returned
    (``stock/wizard/stock_picking_return.py:80-92``) while **v19 prefills 0**
    (``:131-137``), and a zero-quantity confirm raises
    ``"Please specify at least one non-zero quantity."`` (v17 ``:177``,
    v19 ``:183``). ``confirm_return`` presses the version's own public button,
    resolved by probing the delivered wizard arch.
    """
    rpc = ctx.adapter.rpc
    wizard_id = open_return_wizard(rpc, source_picking_id)
    set_return_quantities(rpc, wizard_id, quantities)
    confirm_return(ctx, wizard_id)
    return return_of(rpc, source_picking_id)


def _location_usage(rpc, location_id) -> str:
    if not location_id:
        return ""
    rows = rpc.read("stock.location", [location_id], ["usage",
                                                      "complete_name"])
    return rows[0]["usage"] if rows else ""


def _rma_fixtures(ctx, plain=True) -> dict:
    """One customer RMA, one vendor RMA and (optionally) an ordinary picking.

    * customer RMA — the return of a **done delivery**, so its ``location_id``
      is the Customers location;
    * vendor RMA — the return of a **done receipt**, so its
      ``location_dest_id`` is the Vendors location;
    * ordinary picking — a **draft receipt**, never returned, therefore
      ``rma_number = False``.

    Neither source picking carries a ``sale_id``, so
    ``dto_sale_stock``'s delivery automation
    (``data/base_automation_data.xml:4-11``, ``send_mail(force_send=True)``
    to hard-coded ``@d1systems.com`` recipients) cannot fire and no invoice is
    auto-posted — convention rule 4 is satisfied by construction rather than
    by a guard.
    """
    rpc = ctx.adapter.rpc
    product_id = make_product(ctx, "QUEUE-ITEM")

    delivery_id = make_delivery(ctx, [(product_id, 4.0)], label="CUST-SRC")
    customer_rma = _make_rma(ctx, delivery_id, {product_id: 1.0})

    receipt_id = make_receipt(ctx, [(product_id, 4.0)], label="VEND-SRC")
    vendor_rma = _make_rma(ctx, receipt_id, {product_id: 1.0})

    fixtures = {
        "product_id": product_id,
        "delivery_id": delivery_id,
        "receipt_id": receipt_id,
        "customer_rma": customer_rma,
        "vendor_rma": vendor_rma,
        "plain_id": None,
    }
    if plain:
        fixtures["plain_id"] = make_receipt(ctx, [(product_id, 1.0)],
                                            label="PLAIN", validate=False)
    return fixtures


def _scope_ids(fixtures: dict) -> list:
    """Every picking id this execution created — the queue search scope."""
    ids = [fixtures["customer_rma"]["id"], fixtures["vendor_rma"]["id"],
           fixtures["delivery_id"], fixtures["receipt_id"]]
    if fixtures.get("plain_id"):
        ids.append(fixtures["plain_id"])
    return sorted(ids)


# ====================================================================
# TC188
# ====================================================================
@test_case(
    id="TEST-WF024-TC188",
    name="The three RMA menus exist and the all-RMAs queue lists every "
         "numbered return",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P2", kind="API", order=24188,
    description="The RMAs menuitem sits at sequence 19 under "
                "stock.menu_stock_transfers and is visible to both stock "
                "groups and to neither-group users; three act_window records "
                "exist; the all-RMAs domain is [('rma_number','!=',False)] "
                "and lists both fixture RMAs but not the unnumbered picking; "
                "the five view modes resolve; the search view carries the two "
                "extra RMA filters.",
    traceability=trace("DATAONE-TC188"))
def test_tc188(ctx):
    require_rma_module(ctx)
    require_vendor_narration(ctx)          # WF-024 E1 — _create_return reads it
    rpc = ctx.adapter.rpc
    open_namespace(ctx)
    baseline = {"token": fixture_token(), "environment": ctx.env.key,
                "database": ctx.env.db, "version": ctx.env.version}
    try:
        with ctx.step("Preconditions: at least two RMA pickings exist; at "
                      "least one ordinary picking with no rma_number exists"):
            # Built here, not borrowed from TC184: convention rule 5 forbids
            # one test depending on another test's fixtures.
            fixtures = _rma_fixtures(ctx)
            customer_rma = fixtures["customer_rma"]
            vendor_rma = fixtures["vendor_rma"]
            plain_row = rpc.read("stock.picking", [fixtures["plain_id"]],
                                 ["name", "rma_number"])[0]
            shape = {}
            for label, row in (("customer RMA", customer_rma),
                               ("vendor RMA", vendor_rma)):
                number = row.get("rma_number") or ""
                if not RMA_NUMBER_RE.match(number):
                    shape[label] = (f"rma_number={number!r} does not match "
                                    f"{RMA_NUMBER_RE.pattern}")
            if plain_row.get("rma_number"):
                shape["ordinary picking"] = (
                    f"unexpectedly numbered {plain_row['rma_number']!r}")
            ctx.check("two numbered returns and one unnumbered picking exist",
                      expected={}, actual=shape)
            ctx.log(f"customer RMA {customer_rma['name']} "
                    f"({customer_rma['rma_number']}), vendor RMA "
                    f"{vendor_rma['name']} ({vendor_rma['rma_number']}), "
                    f"ordinary picking {plain_row['name']}")

        with ctx.step("Log in as TD-U-03"):
            # TD-U-03 = dto_stock (Inventory User) -> stock.group_stock_user.
            rpc_u03 = rpc_as_group_user(ctx, "u03", [STOCK_USER_GROUP])
            try:
                uid_u03 = rpc_u03.uid
            except OdooRPCError as exc:
                ctx.blocked(
                    "Could not authenticate the TD-U-03 fixture user "
                    f"(login qa.wf024.u03) on {ctx.env.key} (db={ctx.env.db}): "
                    f"{exc}. TC188 steps 2, 6, 7 and 10-11 are per-user "
                    "assertions and cannot be made from the admin session.")
            groups_field = ctx.adapter.user_groups_field
            u03_groups = rpc.read("res.users", [uid_u03],
                                  [groups_field])[0][groups_field]
            ctx.check("the TD-U-03 session holds stock.group_stock_user",
                      expected=True,
                      actual=rpc.ref(STOCK_USER_GROUP) in (u03_groups or []))

        with ctx.step("Open Inventory -> Transfers and assert an RMAs menu "
                      "entry exists at sequence 19 under "
                      "stock.menu_stock_transfers"):
            menu = menu_row(rpc)
            ctx.check("the module contributes an ir.ui.menu at " + MENU_XMLID,
                      expected=True, actual=menu is not None)
            groups_m2m = menu_groups_field(rpc)
            expected_menu = {
                "name": MENU_NAME,
                "sequence": MENU_SEQUENCE,
                "parent_id": rpc.ref(MENU_PARENT_XMLID),
                "action": f"ir.actions.act_window,{rpc.ref(ACTION_ALL_XMLID)}",
                "groups": sorted(g for g in
                                 (rpc.ref(x) for x in MENU_GROUP_XMLIDS) if g),
            }
            actual_menu = {
                "name": menu["name"],
                "sequence": menu["sequence"],
                "parent_id": m2o_id(menu["parent_id"]),
                "action": menu["action"],
                "groups": sorted(menu.get(groups_m2m) or []),
            }
            ctx.check("the RMAs menuitem, as views/stock_picking.xml:138-140 "
                      "declares it", expected=expected_menu,
                      actual=actual_menu)
            ctx.check("TD-U-03 can see the RMAs menu", expected=True,
                      actual=menu["id"] in visible_menu_ids(rpc_u03))

        with ctx.step("Assert it exposes three actions: all RMAs, customer "
                      "RMAs and vendor RMAs"):
            # WORKBOOK CORRECTION, recorded not softened. The module defines
            # three act_window records (views/stock_picking.xml:81,102,123)
            # and ONE menuitem (:138-140); the customer and vendor actions
            # have no menu entry and no binding anywhere in the module.
            actions = {xmlid: act_window_row(rpc, xmlid)
                       for xmlid in ACTION_XMLIDS}
            problems = {}
            for xmlid, row in actions.items():
                if row is None:
                    problems[xmlid] = "no ir.actions.act_window record"
                    continue
                if row["name"] != ACTION_NAME:
                    problems[xmlid] = f"name={row['name']!r}"
                elif row["res_model"] != "stock.picking":
                    problems[xmlid] = f"res_model={row['res_model']!r}"
            ctx.check("three act_window records named RMAs on stock.picking",
                      expected={}, actual=problems)
            ctx.check("the module owns exactly "
                      f"{RMA_ACTION_COUNT} act_window records",
                      expected=RMA_ACTION_COUNT,
                      actual=len(rpc.search("ir.model.data",
                                            [("model", "=",
                                              "ir.actions.act_window"),
                                             ("module", "=", MODULE)])))
            menu_count = rma_menu_count(rpc)
            ctx.check("the module owns exactly "
                      f"{RMA_MENU_COUNT} menuitem — the workbook's \"exposes "
                      "three actions\" is a correction, not a gap in the test",
                      expected=RMA_MENU_COUNT, actual=menu_count)
            ctx.log(f"[finding] {RMA_ACTION_COUNT} act_window records, "
                    f"{menu_count} menuitem. "
                    f"{ACTION_CUSTOMER_XMLID} and {ACTION_VENDOR_XMLID} are "
                    "reachable only by direct action id — no menu entry and "
                    "no binding exists for either.")
            baseline["menu_count"] = menu_count
            baseline["action_count"] = RMA_ACTION_COUNT

        with ctx.step("Open the all RMAs action"):
            all_rma = actions[ACTION_ALL_XMLID]
            ctx.check("the all-RMAs action resolves", expected=True,
                      actual=all_rma is not None)
            ctx.log(f"{ACTION_ALL_XMLID}: view_mode="
                    f"{all_rma['view_mode']!r}, domain={all_rma['domain']!r}")

        with ctx.step("Assert its domain is [('rma_number','!=',False)]"):
            ctx.check("the all-RMAs domain, verbatim from "
                      "views/stock_picking.xml:127",
                      expected=ACTION_DOMAINS[ACTION_ALL_XMLID],
                      actual=all_rma["domain"])

        with ctx.step("Assert both RMA pickings from TC184 are listed"):
            # The queue is run as TD-U-03, through the action's OWN domain
            # string, scoped to this execution's pickings (convention rule 5:
            # the live queue holds production returns).
            scope = _scope_ids(fixtures)
            members = set(queue_members(rpc_u03, all_rma["domain"], scope))
            wanted = {customer_rma["id"], vendor_rma["id"]}
            ctx.check("both numbered returns are in the all-RMAs queue",
                      expected=sorted(wanted),
                      actual=sorted(members & wanted))

        with ctx.step("Assert the ordinary picking is not listed"):
            ctx.check("the unnumbered picking is absent from the all-RMAs "
                      "queue", expected=False,
                      actual=fixtures["plain_id"] in members)

        with ctx.step("Assert the list, kanban, form, calendar and activity "
                      "view modes are all reachable from the action"):
            # 'list' is spelled 'tree' on v17 and 'list' on v19; the target's
            # own spelling comes from the adapter (fg_common.list_tag), so no
            # version branch lives in this body. EXPECTED v19 OUTCOME: FAIL —
            # the three act_windows still declare 'tree'
            # (views/stock_picking.xml:84,105,126) and 'tree' is not a v19
            # view type (odoo-19.0 .../ir_ui_view.py:149).
            target_list_mode = list_tag(ctx)
            wanted_modes = [target_list_mode if m == "list" else m
                            for m in WORKBOOK_VIEW_MODES]
            declared = [m.strip() for m in (all_rma["view_mode"] or "").split(",")
                        if m.strip()]
            available = available_view_types(rpc)
            unreachable = {}
            for mode in wanted_modes:
                if mode not in declared:
                    unreachable[mode] = (
                        f"not declared in view_mode={all_rma['view_mode']!r}")
                elif mode not in available:
                    unreachable[mode] = (
                        f"not a view type on this target "
                        f"(ir.ui.view.type = {available})")
            not_a_view_type = [m for m in declared if m not in available]
            ctx.log(f"view_mode as shipped = {all_rma['view_mode']!r} "
                    f"(source constant {ACTION_VIEW_MODE!r}); this target's "
                    f"list view type is {target_list_mode!r}")
            ctx.check("the five workbook view modes are reachable from the "
                      "all-RMAs action",
                      expected={"unreachable": {},
                                "declared_but_not_a_view_type": []},
                      actual={"unreachable": unreachable,
                              "declared_but_not_a_view_type": not_a_view_type})

        with ctx.step("Assert the search panel offers the two extra filters "
                      "Customer RMA and Vendor RMA"):
            # view_picking_internal_search_inherit carries no inherit_id
            # (views/stock_picking.xml:17-20), so it is NOT part of the
            # composed stock.picking search arch — get_view would return
            # core's and the two filters would be invisible to this test.
            arch = search_view_arch(ctx)
            ctx.check("the act_window's search_view_id is "
                      + SEARCH_VIEW_XMLID,
                      expected=rpc.ref(SEARCH_VIEW_XMLID),
                      actual=m2o_id(all_rma["search_view_id"]))
            filters = {}
            for expected_filter in (FILTER_CUSTOMER_RMA, FILTER_VENDOR_RMA):
                node = arch_filter(arch, expected_filter["name"]) or {}
                filters[expected_filter["name"]] = {
                    key: node.get(key) for key in ("name", "string", "domain")}
            ctx.check("the two extra RMA filters, verbatim from "
                      "views/stock_picking.xml:31-32",
                      expected={FILTER_CUSTOMER_RMA["name"]:
                                dict(FILTER_CUSTOMER_RMA),
                                FILTER_VENDOR_RMA["name"]:
                                dict(FILTER_VENDOR_RMA)},
                      actual=filters)
            # Recorded, not asserted: the filter named *customer* selects
            # INCOMING pickings (:31) while the customer act_window filters on
            # location_id (:85). The two classifications disagree, and the
            # customer act_window's context turns the filter on by default
            # (:90-92), so that queue applies both at once.
            ctx.log("[finding] filter customer_rma selects "
                    "picking_type_code='incoming' while "
                    f"{ACTION_CUSTOMER_XMLID} filters on location_id; "
                    "the search view and the act_window classify customer "
                    "RMAs by different criteria.")

        with ctx.step("Log in as TD-U-04 and assert the menu is visible (it "
                      "is granted to both stock.group_stock_user and "
                      "stock.group_stock_manager)"):
            rpc_u04 = rpc_as_group_user(ctx, "u04", [STOCK_MANAGER_GROUP])
            try:
                uid_u04 = rpc_u04.uid
            except OdooRPCError as exc:
                ctx.blocked(
                    "Could not authenticate the TD-U-04 fixture user "
                    f"(login qa.wf024.u04) on {ctx.env.key}: {exc}.")
            u04_groups = rpc.read("res.users", [uid_u04],
                                  [groups_field])[0][groups_field]
            ctx.check("the TD-U-04 session holds stock.group_stock_manager",
                      expected=True,
                      actual=rpc.ref(STOCK_MANAGER_GROUP) in (u04_groups or []))
            ctx.check("TD-U-04 can see the RMAs menu", expected=True,
                      actual=menu["id"] in visible_menu_ids(rpc_u04))

        with ctx.step("Log in as a user in neither group and assert the menu "
                      "is not visible"):
            rpc_none = rpc_as_group_user(ctx, "nogroup", [])
            try:
                uid_none = rpc_none.uid
            except OdooRPCError as exc:
                ctx.blocked(
                    "Could not authenticate the neither-group fixture user "
                    f"(login qa.wf024.nogroup) on {ctx.env.key}: {exc}.")
            none_groups = rpc.read("res.users", [uid_none],
                                   [groups_field])[0][groups_field] or []
            # Asserted rather than assumed: if this target's base.group_user
            # implies a stock group, the workbook's "user in neither group"
            # cannot be constructed and the run must say so explicitly.
            ctx.check("the neither-group user belongs to neither stock group",
                      expected=[],
                      actual=[x for x in (STOCK_USER_GROUP,
                                          STOCK_MANAGER_GROUP)
                              if rpc.ref(x) in none_groups])
            ctx.check("the RMAs menu is not visible to a user in neither "
                      "group", expected=False,
                      actual=menu["id"] in visible_menu_ids(rpc_none))

        with ctx.step("Record the three act_window domain strings verbatim as "
                      "the baseline for TC190"):
            domains = {xmlid: (actions[xmlid] or {}).get("domain")
                       for xmlid in ACTION_XMLIDS}
            baseline["action_domains"] = domains
            baseline["action_view_modes"] = {
                xmlid: (actions[xmlid] or {}).get("view_mode")
                for xmlid in ACTION_XMLIDS}
            baseline["available_view_types"] = available
            baseline["target_list_view_type"] = target_list_mode
            _dump(ctx, "tc188_rma_action_baseline.json", baseline,
                  "TC188 act_window baseline for TC190")
            ctx.check("the three domains, verbatim from "
                      "views/stock_picking.xml:85,106,127",
                      expected=dict(ACTION_DOMAINS), actual=domains)
    finally:
        # The three disposable sessions this case builds. sweep_wf024 cannot
        # reach res.users and deliberately spares a user's partner
        # (common.py's res.partner step is guarded with user_ids = False),
        # so without this three active internal logins with a known password
        # survive every run. ensure_user_in_groups reactivates a login it
        # finds, so archiving here cannot starve TC190 of qa.wf024.u04.
        archive_qa_users(ctx, ["u03", "u04", "nogroup"])
        safe_sweep(ctx)


# ====================================================================
# TC190
# ====================================================================
@test_case(
    id="TEST-WF024-TC190",
    name="On a rebuilt database the customer and vendor RMA queues return "
         "the right pickings (expected to fail today)",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P0", kind="API", order=24190,
    description="Resolves stock.stock_location_customers and "
                "stock.stock_location_suppliers, asserts their ids really are "
                "5 and 4 as the two directional act_window domains hard-code, "
                "runs each queue's own domain against a customer RMA and a "
                "vendor RMA, and asserts both domains reference the locations "
                "by xml_id rather than by an integer literal.",
    traceability=trace("DATAONE-TC190"))
def test_tc190(ctx):
    require_rma_module(ctx)
    require_vendor_narration(ctx)          # WF-024 E1 — _create_return reads it
    rpc = ctx.adapter.rpc
    open_namespace(ctx)
    # Step 13's record. Populated as each step completes, and written from the
    # finally: below so that a step-4 abort — the workbook's expected outcome
    # on a rebuilt database — still leaves the evidence behind.
    findings = {"tc_id": "DATAONE-TC190", "token": fixture_token(),
                "environment": ctx.env.key, "database": ctx.env.db,
                "version": ctx.env.version,
                "hardcoded": {"customer_location_id":
                              HARDCODED_CUSTOMER_LOCATION_ID,
                              "vendor_location_id":
                              HARDCODED_VENDOR_LOCATION_ID}}
    try:
        with ctx.step("Preconditions: one customer RMA (a return of a "
                      "delivery) and one vendor RMA (a return of a receipt) "
                      "exist"):
            fixtures = _rma_fixtures(ctx, plain=False)
            customer_rma = fixtures["customer_rma"]
            vendor_rma = fixtures["vendor_rma"]
            # Asserted semantically (usage), never against an id: the ids are
            # precisely what this case is measuring. The wizard guarantees the
            # shape in both versions — v17 :113-127 / :74-77, v19 :142-159.
            shape = {
                "customer RMA location_id usage":
                    _location_usage(rpc, m2o_id(customer_rma["location_id"])),
                "vendor RMA location_dest_id usage":
                    _location_usage(rpc,
                                    m2o_id(vendor_rma["location_dest_id"])),
            }
            ctx.check("the customer RMA returns to a customer location and "
                      "the vendor RMA returns to a supplier location",
                      expected={"customer RMA location_id usage": "customer",
                                "vendor RMA location_dest_id usage":
                                "supplier"},
                      actual=shape)
            findings["fixtures"] = {
                "customer_rma": {"id": customer_rma["id"],
                                 "name": customer_rma["name"],
                                 "rma_number": customer_rma["rma_number"],
                                 "location_id":
                                 m2o_id(customer_rma["location_id"]),
                                 "location_dest_id":
                                 m2o_id(customer_rma["location_dest_id"])},
                "vendor_rma": {"id": vendor_rma["id"],
                               "name": vendor_rma["name"],
                               "rma_number": vendor_rma["rma_number"],
                               "location_id":
                               m2o_id(vendor_rma["location_id"]),
                               "location_dest_id":
                               m2o_id(vendor_rma["location_dest_id"])},
            }

        with ctx.step("Log in as TD-U-04"):
            # TD-U-04 = dto_stock_mgr (Inventory Manager).
            rpc_u04 = rpc_as_group_user(ctx, "u04", [STOCK_MANAGER_GROUP])
            try:
                uid_u04 = rpc_u04.uid
            except OdooRPCError as exc:
                ctx.blocked(
                    "Could not authenticate the TD-U-04 fixture user "
                    f"(login qa.wf024.u04) on {ctx.env.key} (db={ctx.env.db}): "
                    f"{exc}. The two queues must be opened as the Inventory "
                    "Manager the workbook names.")
            groups_field = ctx.adapter.user_groups_field
            u04_groups = rpc.read("res.users", [uid_u04],
                                  [groups_field])[0][groups_field]
            ctx.check("the TD-U-04 session holds stock.group_stock_manager",
                      expected=True,
                      actual=rpc.ref(STOCK_MANAGER_GROUP) in (u04_groups or []))

        with ctx.step("Resolve customers_id = "
                      "env.ref('stock.stock_location_customers').id and "
                      "vendors_id = env.ref('stock.stock_location_suppliers')"
                      ".id"):
            # rpc.ref resolves through ir.model.data. Deliberately NOT
            # common.customer_location / vendor_location: those fall back to a
            # usage search, and this case is about the xmlid.
            customers_id = rpc.ref(CUSTOMER_LOCATION_XMLID)
            vendors_id = rpc.ref(VENDOR_LOCATION_XMLID)
            if not customers_id or not vendors_id:
                ctx.blocked(
                    f"{CUSTOMER_LOCATION_XMLID} -> {customers_id!r}, "
                    f"{VENDOR_LOCATION_XMLID} -> {vendors_id!r} on "
                    f"{ctx.env.key} (db={ctx.env.db}). TD-L-08 cannot be "
                    "resolved, so neither the customer/vendor split nor the "
                    "xml_id assertion at step 12 has anything to measure — "
                    "restore the ir_model_data rows before re-running.")
            ctx.check("both partner locations resolve by xml_id",
                      expected=True, actual=bool(customers_id and vendors_id))

        with ctx.step("Record both values"):
            resolved = {
                CUSTOMER_LOCATION_XMLID: rpc.read(
                    "stock.location", [customers_id],
                    ["id", "complete_name", "usage"])[0],
                VENDOR_LOCATION_XMLID: rpc.read(
                    "stock.location", [vendors_id],
                    ["id", "complete_name", "usage"])[0],
            }
            findings["resolved_locations"] = resolved
            for xmlid, row in resolved.items():
                ctx.log(f"{xmlid} -> id={row['id']}, "
                        f"complete_name={row['complete_name']!r}, "
                        f"usage={row['usage']!r}")

        with ctx.step("Assert customers_id == 5 and vendors_id == 4. On a "
                      "rebuilt database this assertion is expected to fail — "
                      "record the actual ids"):
            # DO NOT SOFTEN. The workbook is explicit: step 4 is written as an
            # assertion that fails rather than as a recorded observation, so
            # the failure appears in the CI result and cannot be scrolled
            # past. Both ids go into ONE check so a failure reports both.
            expected_ids = {"customers_id": HARDCODED_CUSTOMER_LOCATION_ID,
                            "vendors_id": HARDCODED_VENDOR_LOCATION_ID}
            actual_ids = {"customers_id": customers_id,
                          "vendors_id": vendors_id}
            findings["step_04"] = {
                "expected": expected_ids, "actual": actual_ids,
                "passed": expected_ids == actual_ids,
                "source": "views/stock_picking.xml:85,106 pin "
                          "('location_id','=',5) and "
                          "('location_dest_id','=',4)"}
            ctx.check("the hard-coded ids match the real partner locations "
                      "(views/stock_picking.xml:85,106)",
                      expected=expected_ids, actual=actual_ids)

        with ctx.step("Open Inventory -> Transfers -> RMAs -> Customer RMAs"):
            customer_action = act_window_row(rpc, ACTION_CUSTOMER_XMLID)
            ctx.check("the customer-RMAs act_window resolves", expected=True,
                      actual=customer_action is not None)
            ctx.check("its domain, verbatim from views/stock_picking.xml:85",
                      expected=ACTION_DOMAINS[ACTION_CUSTOMER_XMLID],
                      actual=customer_action["domain"])
            scope = _scope_ids(fixtures)
            customer_queue = set(queue_members(rpc_u04,
                                               customer_action["domain"],
                                               scope))
            ctx.log(f"customer queue (scoped to this execution) = "
                    f"{sorted(customer_queue)}")

        with ctx.step("Assert the customer RMA picking created in the "
                      "preconditions is listed"):
            listed = customer_rma["id"] in customer_queue
            findings["step_06"] = {
                "customer_rma_id": customer_rma["id"],
                "customer_rma_name": customer_rma["name"],
                "queue_domain": customer_action["domain"],
                "queue_members_in_scope": sorted(customer_queue),
                "listed": listed, "passed": listed}
            ctx.check("the customer RMA is in the Customer RMAs queue",
                      expected=True, actual=listed)

        with ctx.step("Assert the vendor RMA picking is not listed"):
            ctx.check("the vendor RMA is absent from the Customer RMAs queue",
                      expected=False,
                      actual=vendor_rma["id"] in customer_queue)

        with ctx.step("Open Vendor RMAs"):
            vendor_action = act_window_row(rpc, ACTION_VENDOR_XMLID)
            ctx.check("the vendor-RMAs act_window resolves", expected=True,
                      actual=vendor_action is not None)
            ctx.check("its domain, verbatim from views/stock_picking.xml:106",
                      expected=ACTION_DOMAINS[ACTION_VENDOR_XMLID],
                      actual=vendor_action["domain"])
            vendor_queue = set(queue_members(rpc_u04, vendor_action["domain"],
                                             scope))
            ctx.log(f"vendor queue (scoped to this execution) = "
                    f"{sorted(vendor_queue)}")

        with ctx.step("Assert the vendor RMA picking is listed"):
            listed = vendor_rma["id"] in vendor_queue
            findings["step_09"] = {
                "vendor_rma_id": vendor_rma["id"],
                "vendor_rma_name": vendor_rma["name"],
                "queue_domain": vendor_action["domain"],
                "queue_members_in_scope": sorted(vendor_queue),
                "listed": listed, "passed": listed}
            ctx.check("the vendor RMA is in the Vendor RMAs queue",
                      expected=True, actual=listed)

        with ctx.step("Assert the customer RMA picking is not listed"):
            ctx.check("the customer RMA is absent from the Vendor RMAs queue",
                      expected=False,
                      actual=customer_rma["id"] in vendor_queue)

        with ctx.step("Assert both queues are non-empty. An empty queue with "
                      "no error is the failure"):
            # Non-emptiness is measured over this execution's own pickings
            # (convention rule 5). The failure mode the workbook names — an
            # empty list and no error — is exactly an empty set here.
            emptiness = {"customer_rma_queue": len(customer_queue),
                         "vendor_rma_queue": len(vendor_queue)}
            findings["step_11"] = {
                "counts": emptiness,
                "passed": bool(customer_queue) and bool(vendor_queue),
                "note": "counts are scoped to this execution's fixtures; an "
                        "empty set is the silent failure the workbook names"}
            ctx.check("neither queue came back empty",
                      expected={"customer_rma_queue_empty": False,
                                "vendor_rma_queue_empty": False},
                      actual={"customer_rma_queue_empty": not customer_queue,
                              "vendor_rma_queue_empty": not vendor_queue})

        with ctx.step("Read the two act_window domains and assert they "
                      "reference the locations by xml_id, not by a literal "
                      "integer"):
            # This is the assertion that turns green when the one-line fix
            # lands: ('location_id','=',5) -> ref('stock.stock_location_
            # customers') and ('location_dest_id','=',4) ->
            # ref('stock.stock_location_suppliers'). Both domains are checked
            # in ONE mismatch dict so a failure reports both.
            offences = {}
            probes = ((ACTION_CUSTOMER_XMLID, customer_action, "location_id",
                       customers_id, CUSTOMER_LOCATION_XMLID),
                      (ACTION_VENDOR_XMLID, vendor_action, "location_dest_id",
                       vendors_id, VENDOR_LOCATION_XMLID))
            recorded = {}
            for xmlid, action, field, expected_id, loc_xmlid in probes:
                domain_str = action["domain"]
                term = _location_term(domain_str, field)
                recorded[xmlid] = {"domain": domain_str, f"{field}": term,
                                   "resolves_to": expected_id,
                                   "should_be": f"ref({loc_xmlid!r})"}
                if domain_has_literal_location_id(domain_str):
                    offences[xmlid] = (
                        f"{field} is pinned to the integer literal {term!r}; "
                        f"it must resolve from ref({loc_xmlid!r}), which is "
                        f"{expected_id} on this database")
                elif term != expected_id:
                    offences[xmlid] = (
                        f"{field} resolves to {term!r} but "
                        f"ref({loc_xmlid!r}) is {expected_id}")
            findings["step_12"] = {"domains": recorded, "offences": offences,
                                   "passed": not offences}
            ctx.check("both directional domains reference the locations by "
                      "xml_id, not by a literal integer",
                      expected={}, actual=offences)

        with ctx.step("Record the outcome of steps 4, 6, 9, 11 and 12 "
                      "verbatim in findings/"):
            findings["steps_not_reached"] = [
                key for key in TC190_RECORDED_STEPS if key not in findings]
            _dump(ctx, "tc190_rebuilt_db_findings.json", findings,
                  "TC190 rebuilt-database findings (steps 4, 6, 9, 11, 12)")
            ctx.check("all five workbook outcomes were recorded",
                      expected=[], actual=findings["steps_not_reached"])
    finally:
        # Step 13 must survive a step-4 abort — on a rebuilt database that
        # abort IS the expected outcome, and the evidence gathered up to it is
        # the defect record. Neither call can raise.
        try:
            findings["steps_not_reached"] = [
                key for key in TC190_RECORDED_STEPS if key not in findings]
            if findings["steps_not_reached"]:
                findings["abort_note"] = (
                    "the run stopped before these steps could be measured; "
                    "on today's code that is the expected consequence of "
                    "step 4 failing (views/stock_picking.xml:85,106)")
                _dump(ctx, "tc190_rebuilt_db_findings.json", findings,
                      "TC190 rebuilt-database findings (partial — run "
                      "aborted)")
        except Exception:                                     # noqa: BLE001
            pass
        # The disposable TD-U-04 session — see the note in TC188's teardown.
        archive_qa_users(ctx, ["u04"])
        safe_sweep(ctx)
