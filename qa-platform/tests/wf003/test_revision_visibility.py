"""DATAONE-WF-003 — button visibility and the unguarded programmatic path:
TC097.

Steps 1-4 (is "New Revision of Quotation" present in each of the four
states?) are asserted against the *rule as loaded*, not against a rendered
browser page: the button's visibility is a view-level modifier
(``invisible="state not in ['cancel' ,'sent']"`` in
sale_order_revision/view/sale_order.xml), so the test reads the composed
form arch through get_view() and evaluates that modifier per state.

Why that substitution is faithful rather than weaker: the workbook's own
v19_watch says the risk is the priority-15 inherit failing to load because
its ``//button[@name='action_view_invoice']`` anchor rotted — in which case
the button is absent from the arch entirely, which is exactly what this
test detects. A browser tour would observe the same absence one layer
later, at higher cost and with more flakiness.

Steps 5-6 are destructive by design: create_revision() has no Python guard,
so calling it on a confirmed order cancels and archives an order that
already launched procurement. They run last, on a disposable fixture that
the sweep removes.

EXPECTED v17 OUTCOME: PASS.
EXPECTED v19 OUTCOME: BLOCKED until the OCA 19.0 ports exist (E5); once
they do, the arch assertions are the ones that catch a rotted anchor.
"""
import re
import xml.etree.ElementTree as ET

from framework.qa_fixtures import require_mail_offline
from framework.registry import test_case
from tests.wf003.common import (WORKFLOW, WORKFLOW_NAME,  # noqa: F401
                                gate_analytic, make_quotation, read_order,
                                require_revision_stack, set_sent,
                                sweep_wf003, trace)

_STATE_LIST_RE = re.compile(r"state\s+not\s+in\s*\[([^\]]*)\]")
_QUOTED_RE = re.compile(r"['\"]([^'\"]+)['\"]")


def _revision_button(arch: str):
    """The <button name="create_revision"> node from a composed form arch,
    or None when the inherit did not load."""
    root = ET.fromstring(arch)
    for node in root.iter("button"):
        if node.get("name") == "create_revision":
            return node
    return None


def _visible_states(invisible_expr: str) -> set:
    """The states in which the button is VISIBLE, read out of its own
    ``invisible`` modifier. Parsing the state list (rather than string-
    matching the whole expression) keeps the test insensitive to the
    source's spacing — the shipped attribute is
    ``state not in ['cancel' ,'sent']``, with a stray space."""
    m = _STATE_LIST_RE.search(invisible_expr or "")
    if not m:
        return set()
    return set(_QUOTED_RE.findall(m.group(1)))


@test_case(
    id="TEST-WF003-TC097",
    name="The revision button appears only in sent and cancel",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="sale_order_revision", priority="P2", kind="API", order=3097,
    description="The header button is visible in sent and cancel and "
                "absent in draft and sale; create_revision() called "
                "directly through the ORM on a CONFIRMED order succeeds — "
                "there is no Python guard — leaving it cancelled and "
                "archived with procurement behind it.",
    traceability=trace("DATAONE-TC097"))
def test_tc097(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-003 fixtures and open a fresh "
                  "namespace"):
        sweep_wf003(rpc)

    with ctx.step("Preconditions: the revision stack is installed, and no "
                  "mail server is active — this test confirms an order, "
                  "which fires dto_sale's confirmation automation"):
        require_revision_stack(ctx)
        require_mail_offline(ctx)

    with ctx.step("Build four orders, one in each relevant state: draft, "
                  "sent, sale, cancel"):
        orders = {}
        orders["draft"], _ = make_quotation(ctx, label="Draft")

        orders["sent"], _ = make_quotation(ctx, label="Sent")
        set_sent(rpc, orders["sent"])

        # The confirmed fixture is the only one that passes dto_account's
        # analytic gate, which refuses a project order whose lines carry no
        # Project-plan account (dto_account/models/sale_order.py:83). The
        # subject here is the header button, not the gate.
        orders["sale"], _ = make_quotation(
            ctx, label="Confirmed",
            line_analytic=gate_analytic(ctx, "project"))
        rpc.call("sale.order", "action_confirm", [orders["sale"]])

        orders["cancel"], _ = make_quotation(ctx, label="Cancelled")
        ctx.adapter.cancel_order(orders["cancel"])

        actual_states = {k: read_order(rpc, v, ["state"])["state"]
                         for k, v in orders.items()}
        ctx.check("fixture states", {"draft": "draft", "sent": "sent",
                                     "sale": "sale", "cancel": "cancel"},
                  actual_states)

    try:
        with ctx.step("The priority-15 form inherit loaded and contributed "
                      "the New Revision of Quotation button"):
            arch = rpc.call("sale.order", "get_view", view_type="form")["arch"]
            button = _revision_button(arch)
            ctx.check_true(
                "create_revision button present in the composed form arch",
                button is not None,
                actual_desc=("present" if button is not None else
                             "ABSENT — sale_order_revision's inherit did "
                             "not load; check the "
                             "//button[@name='action_view_invoice'] anchor"))
            ctx.check("button label", "New Revision of Quotation",
                      button.get("string"))
            ctx.check("button type", "object", button.get("type"))

        with ctx.step("Steps 1-4: the button is visible in sent and cancel "
                      "only"):
            visible_in = _visible_states(button.get("invisible"))
            ctx.log(f"invisible modifier: {button.get('invisible')!r} "
                    f"-> visible in {sorted(visible_in)}")
            observed = {state: (state in visible_in) for state in
                        ("draft", "sent", "sale", "cancel")}
            ctx.check("button visibility by state",
                      {"draft": False, "sent": True,
                       "sale": False, "cancel": True},
                      observed)

        with ctx.step("Step 5: call create_revision() directly on the "
                      "CONFIRMED order — the call succeeds, there is no "
                      "Python guard"):
            before = read_order(rpc, orders["sale"],
                                ["name", "state", "active"])
            pickings = rpc.search("stock.picking",
                                  [("sale_id", "=", orders["sale"])]) \
                if rpc.field_exists("stock.picking", "sale_id") else []
            ctx.log(f"procurement behind the confirmed order: "
                    f"{len(pickings)} picking(s)")
            action = rpc.call("sale.order", "create_revision",
                              [orders["sale"]])
            ctx.check_true("create_revision on a confirmed order succeeded",
                           bool(action), actual_desc=repr(action))

        with ctx.step("Step 6: the previously confirmed order is now "
                      "state 'cancel' AND active False"):
            after = read_order(rpc, orders["sale"],
                               ["state", "active", "current_revision_id"])
            ctx.check("confirmed order state after", "cancel",
                      after["state"])
            ctx.check("confirmed order active after", False,
                      after["active"])
            ctx.log(f"the unguarded path left {len(pickings)} picking(s) "
                    f"behind {before['name']} — WF-003 open question")
    finally:
        with ctx.step("Cleanup WF-003 fixtures (including the cancelled and "
                      "archived step-5 order)"):
            try:
                sweep_wf003(rpc)
            except Exception as exc:      # noqa: BLE001 — never mask a verdict
                ctx.log(f"[warn] cleanup incomplete: {exc}")
