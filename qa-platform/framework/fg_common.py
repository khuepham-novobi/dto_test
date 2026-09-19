"""Shared helpers for every DataOne workflow suite (tests/wfNNN/).

Live-DB determinism rules every suite follows:
* fixtures are namespaced with the suite marker (e.g. "WF013 ...") plus a
  per-execution token, and are swept before/after each test — pre-existing
  business records are never modified;
* reconciliation tests are read-only and use the baseline/diff pattern;
* each RPC call commits its own transaction, so cr.precommit hooks fire per
  call and cleanup must always run in a finally block.
"""
from __future__ import annotations

import http.cookiejar
import json
import urllib.request

from framework.baselines import (baseline_path, diff_counts, load_baseline,
                                 save_baseline)

WORKBOOK = "DataOne_v19_Test_Suite_and_Workflows_v1.0.xlsx"


def make_trace(feature: str):
    """trace('DATAONE-TC…') factory bound to one workflow suite."""
    def trace(tc_ids, user_story=""):
        return {"tc_ids": tc_ids if isinstance(tc_ids, list) else [tc_ids],
                "feature": feature, "user_story": user_story,
                "source": f"{WORKBOOK} / Automation Export"}
    return trace


def m2o_id(value):
    """RPC read() returns m2o as [id, display_name] or False."""
    return value[0] if isinstance(value, (list, tuple)) else (value or None)


def form_arch(ctx, model, view_type="form", xmlid=None):
    """Version-agnostic view arch fetch.

    ``xmlid`` names the view to read. WITHOUT it, get_view returns the
    model's DEFAULT view of that type, which for account.move's list is the
    generic account.view_invoice_tree (string="Invoices") — NOT the
    vendor-bill list account.view_in_invoice_bill_tree that dto_account
    actually extends. Asserting on the default therefore reports a missing
    column that is present in the view a user really opens. Pass the xmlid
    whenever the assertion is about a view some module inherited.

    Both v17 and v19 expose get_view(view_id, view_type)
    (base/models/ir_ui_view.py:2613 on v17, :3138 on v19). What differs is
    the name of the list view type: ir.ui.view.type is [('tree','Tree'), …]
    on v17 (ir_ui_view.py:163) and [('list','List'), …] on v19
    (ir_ui_view.py:149). Callers pass either name; the adapter's
    list_view_type resolves it for the target version, so no test body
    carries a version branch.
    """
    if view_type in ("tree", "list"):
        view_type = getattr(ctx.adapter, "list_view_type", view_type)
    kwargs = {"view_type": view_type}
    if xmlid:
        view_id = ctx.adapter.rpc.ref(xmlid)
        if not view_id:
            ctx.blocked(
                f"The view {xmlid} does not resolve on {ctx.env.key} "
                f"(db={ctx.env.db}), so the arch this case asserts on "
                "cannot be read.")
        kwargs["view_id"] = view_id
    return ctx.adapter.rpc.call(model, "get_view", **kwargs)["arch"]


def list_tag(ctx) -> str:
    """The XML tag a list view uses on the target version: 'tree' on v17,
    'list' on v19. Use it when asserting against arch strings."""
    return getattr(ctx.adapter, "list_tag", "list")


def http_session(env):
    """An authenticated urllib opener (real web session) for HTTP evidence."""
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(jar))
    payload = json.dumps({"jsonrpc": "2.0", "params": {
        "db": env.db, "login": env.username, "password": env.password}})
    req = urllib.request.Request(
        f"{env.base_url}/web/session/authenticate", data=payload.encode(),
        headers={"Content-Type": "application/json"})
    res = json.loads(opener.open(req, timeout=30).read())
    if not (res.get("result") or {}).get("uid"):
        raise RuntimeError("web session authentication failed")
    return opener


def reconcile(ctx, tc_id, capture, anchors=None):
    """DATA_RECONCILIATION driver — see framework/baselines.py.

    capture(ctx) -> {key: value} snapshot of the current environment.
    v17: capture, assert anchors, persist baseline.
    v19: load baseline (BLOCKED if absent), capture, assert zero diff.
    """
    with ctx.step("Capture current-environment snapshot (read-only SQL/ORM)"):
        current = capture(ctx)
        for key, value in sorted(current.items()):
            ctx.log(f"  {key} = {value}")

    if anchors:
        with ctx.step("Assert workbook anchor values"):
            for key, expected in anchors.items():
                ctx.check(f"anchor {key}", expected=expected,
                          actual=current.get(key))

    if ctx.env.version == "17":
        with ctx.step("Persist v17 baseline for the v19 comparison"):
            path = save_baseline(tc_id, ctx.env.key, ctx.env.db, current)
            ctx.add_artifact(path, "log", f"{tc_id} v17 baseline")
            ctx.log(f"baseline stored: {path}")
    else:
        with ctx.step("Diff against the stored v17 baseline"):
            base = load_baseline(tc_id)
            if base is None:
                ctx.blocked(f"No v17 baseline captured yet for {tc_id} — "
                            "run the suite on Odoo 17 first")
            ctx.add_artifact(baseline_path(tc_id), "log",
                             f"{tc_id} v17 baseline")
            diffs = diff_counts(base["data"], current)
            ctx.check("No differences vs v17 baseline", expected=[],
                      actual=diffs)
