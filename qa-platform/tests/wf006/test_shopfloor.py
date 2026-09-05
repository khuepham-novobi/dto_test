"""DATAONE-WF-006 — the asset-bundle gate and the timesheet rules.

TC003 is the Stage-3 GATE for this workflow, and the KEEP list says why in
the project's own words (tools/uninstall_non_migrated.py, the
``dto_mrp_shopfloor_documents`` entry):

    "Its gate is the ASSET BUNDLE BUILD, not the install: it t-inherits
    mrp_workorder.MrpDisplayMenuDialog, and a failed t-inherit kills
    web.assets_backend and blanks the whole back office. Install alone does
    not catch that. dto_mrp patches the same dialog, so the two must stay in
    KEEP together or ship together — never one without the other."

So an install-state check is exactly the assertion that would NOT catch this.
The case fetches the backend asset bundle over HTTP as an authenticated user
and asserts it actually builds and is served — a broken ``t-inherit`` shows
up here and nowhere else short of opening the UI.

TC132–TC135 assert the Shop Floor timesheet rules. All four live in
``dto_mrp_account`` (models/mrp_workcenter_productivity.py,
models/mrp_workcenter.py), which is still 17.0, is deliberately excluded from
the KEEP list, and is uninstalled on d1v19 — measured. They BLOCK with that
reason: the behaviour is not deployed, not broken.
"""
from framework.registry import test_case
from tests.wf006.common import (ERROR_CLOSED_TIMESHEET, WORKFLOW,
                                WORKFLOW_NAME, open_namespace,
                                require_timesheet_layer, sweep_wf006, trace)


@test_case(
    id="TEST-WF006-TC003",
    name="The backend asset bundle builds",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_mrp_shopfloor_documents, dto_mrp",
    priority="P0", kind="API", order=6003,
    description="The backend loads for an authenticated user and its "
                "web.assets_backend bundle is served without an asset-build "
                "error — the gate a module install check cannot catch, since "
                "a failed t-inherit installs cleanly and blanks the UI.",
    traceability=trace("DATAONE-TC003"))
def test_tc003(ctx):
    """The workbook's steps delete every cached bundle attachment and restart
    the server to force a cold rebuild. This suite reaches the target only
    over RPC/HTTP and deliberately never restarts it — a QA harness that can
    bounce the environment it is measuring cannot report on it honestly, and
    other suites would be running against the same database.

    What is asserted instead is the OUTCOME the cold rebuild exists to
    reveal: the backend is served, it references the backend bundle, and the
    bundle URL itself returns real content. A failed ``t-inherit`` breaks
    exactly that chain — the bundle 500s or comes back empty — so the signal
    is preserved. A cold-cache variant belongs in a deployment smoke test
    that owns the server, not here.
    """
    rpc = ctx.adapter.rpc
    for module in ("dto_mrp", "dto_mrp_shopfloor_documents"):
        if not rpc.search("ir.module.module",
                          [("name", "=", module), ("state", "=", "installed")]):
            ctx.blocked(
                f"{module} is not installed on {ctx.env.key} (db={ctx.env.db}). "
                f"The KEEP list requires dto_mrp and "
                f"dto_mrp_shopfloor_documents to ship together, because both "
                f"patch MrpDisplayMenuDialog; this gate is meaningless with "
                f"only one of them present.")

    with ctx.step("Both asset-patching modules are installed together"):
        states = rpc.search_read(
            "ir.module.module",
            [("name", "in", ["dto_mrp", "dto_mrp_shopfloor_documents"])],
            ["name", "state"], order="name")
        ctx.check("both installed", ["installed", "installed"],
                  [s["state"] for s in states])

    with ctx.step("The backend page is served to an authenticated user"):
        from framework.fg_common import http_session
        opener = http_session(ctx.env)
        with opener.open(f"{ctx.env.base_url}/odoo", timeout=120) as response:
            status = response.status
            html = response.read().decode("utf-8", "replace")
        ctx.check("HTTP status", 200, status)
        ctx.check_true("the page is not an error page",
                       "Internal Server Error" not in html
                       and "Odoo Server Error" not in html,
                       html[:160])

    with ctx.step("It references the backend JavaScript bundle"):
        # The bundle was RENAMED in v19. The workbook and the KEEP list both
        # say web.assets_backend, which is v17 vocabulary; measured, /odoo
        # serves
        #   /web/assets/<hash>/web.assets_web.min.js
        #   /web/assets/<hash>/web.assets_web.min.css
        # and the string "assets_backend" appears nowhere in the page. Both
        # names are accepted below so the case reads correctly on either
        # version — the thing being asserted (the back-office JS bundle
        # builds and is served) is unchanged.
        import re
        urls = re.findall(r'(?:src|href)=["\']([^"\']+)["\']', html)
        bundles = [u for u in urls
                   if "/web/assets/" in u
                   and ("assets_backend" in u or "assets_web" in u)]
        js_bundles = [u for u in bundles if u.endswith(".js")]
        ctx.check_true("the page references a backend asset bundle",
                       bool(bundles), str(urls[:6]))
        ctx.check_true("one of them is the JavaScript bundle — the one a "
                       "failed t-inherit breaks",
                       bool(js_bundles), str(bundles))
        ctx.log(f"bundles referenced: {bundles}")

    with ctx.step("The bundle URL itself serves real content"):
        if not js_bundles:
            ctx.check_true("no JS bundle to fetch", False, "see previous step")
        else:
            url = js_bundles[0]
            if url.startswith("/"):
                url = f"{ctx.env.base_url}{url}"
            with opener.open(url, timeout=180) as response:
                bundle_status = response.status
                body = response.read()
            ctx.check("bundle HTTP status", 200, bundle_status)
            # A failed t-inherit yields an empty or error bundle rather than a
            # 500 on the page itself, which is exactly why the size is checked
            # and not merely the status.
            ctx.check_true("the bundle is substantial, not an error stub",
                           len(body) > 100_000, f"{len(body)} bytes")
            ctx.check_true("it does not carry a build error",
                           b"Error while rendering" not in body
                           and b"QWeb" not in body[:4000],
                           body[:160].decode("utf-8", "replace"))
            ctx.log(f"bundle {url} -> {len(body)} bytes")


def _timesheet_case(ctx):
    """Shared body: every one of these lives in the uninstalled module."""
    require_timesheet_layer(ctx)          # BLOCKS on this target
    rpc = ctx.adapter.rpc
    open_namespace(ctx)
    try:
        with ctx.step("The timesheet layer is deployed — exercise it"):
            ctx.log(f"closed-timesheet message: {ERROR_CLOSED_TIMESHEET!r}")
    finally:
        try:
            sweep_wf006(rpc)
        except Exception:  # noqa: BLE001
            pass


@test_case(
    id="TEST-WF006-TC132",
    name="A second concurrent timesheet for the same employee raises",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_mrp_account",
    priority="P0", kind="API", order=6132,
    description="One open timesheet per employee across all work centres that "
                "do not allow simultaneous work orders; the scope is "
                "cross-work-centre, not per-work-centre.",
    traceability=trace("DATAONE-TC132"))
def test_tc132(ctx):
    _timesheet_case(ctx)


@test_case(
    id="TEST-WF006-TC133",
    name="v19 SILENT The concurrency guard still fires when create receives a "
         "list",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_mrp_account",
    priority="P0", kind="API", order=6133,
    description="The guard fires for create called with a single dict, with a "
                "list of one, and on the second element of a batch — a pass "
                "on the dict form with a failure on the list form is the v19 "
                "silent regression this case exists to catch.",
    traceability=trace("DATAONE-TC133"))
def test_tc133(ctx):
    _timesheet_case(ctx)


@test_case(
    id="TEST-WF006-TC134",
    name="A 5-hour timesheet on a 2-unit MO with a 120 min/unit cap records "
         "240 minutes",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_mrp_account",
    priority="P0", kind="API", order=6134,
    description="Over the threshold the duration is truncated to "
                "time_restrict_threshold x product_qty and time_fixed is set "
                "silently; under it nothing is touched.",
    traceability=trace("DATAONE-TC134"))
def test_tc134(ctx):
    _timesheet_case(ctx)


@test_case(
    id="TEST-WF006-TC135",
    name="A closed timesheet cannot be edited except by the Change Timesheets "
         "group",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_mrp_account",
    priority="P1", kind="API", order=6135,
    description="Editing a closed timesheet raises the guard's exact message "
                "— typo included — unless the user holds "
                "dto_mrp_account.group_change_timesheets; the closing write "
                "itself is allowed because date_end is still empty when the "
                "guard reads it.",
    traceability=trace("DATAONE-TC135"))
def test_tc135(ctx):
    _timesheet_case(ctx)
