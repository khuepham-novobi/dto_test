# DataOne Workflow Suite — Automation Conventions

Binding conventions for every workflow test suite in this platform. The
generation unit is one **workflow** (`DATAONE-WF-NNN`), one folder:
`tests/wfNNN/`.

Source of truth: `DataOne_v19_Test_Suite_and_Workflows_v1.0.xlsx`, sheet
`Automation Export`, synced read-only into `data/test_registry.json` by
`scripts/sync_registry.py`.

## Hard rules

1. **Write only under `qa-platform/tests/wfNNN/`** plus that suite's
   `reports/data/wfNNN_feasibility.json` and `docs/WF-NNN_AUTOMATION_PLAN.md`.
   Never touch application source (`DTO-Odoo/`, `odoo-17.0/`, `odoo-19.0/`),
   framework/backend/frontend files, another suite, or the Excel workbook.
2. **Workbook expected results are immutable.** Assertions implement the
   workbook's expected result — never weakened, never inverted. A test that
   is expected to FAIL on v17 (because the expectation describes the v19
   target state) stays failing; that baseline FAIL classifies as FIXED when
   v19 passes. Document it in the docstring as
   `EXPECTED v17 OUTCOME: FAIL — <why>`.
3. **Never modify pre-existing business records.** Fixtures are created
   namespaced (marker prefix `WFNNN` + a per-execution token), swept at test
   start (idempotence) and cleaned in a `finally` step that can never raise.
   Live-data checks are read-only.
4. **Never trigger outbound integrations.** The QA clone has crons, mail and
   the Workday SFTP connector deactivated. Tests must not reactivate
   instances, enable crons, configure credentials, or call export/sync
   methods that reach an external host. A test whose essence requires an
   external system asserts its offline half first, then calls
   `ctx.blocked("requires <X> — <precise detail>")`.
5. **Deterministic and repeatable.** Same result on every rerun; no
   time-dependent values, no dependence on another test's fixtures, no
   reliance on record ids. Scope every search by the execution token so live
   data cannot leak into "exactly N records" assertions; document such
   adaptations in the test docstring.
6. **Verify before asserting.** Every model, field, method and XML id a test
   asserts against must be confirmed in the real source
   (`DTO-Odoo/`, `odoo-17.0/`, `odoo-19.0/`) before the assertion is
   written. An unverifiable claim is marked `[UNVERIFIED]` in the plan doc,
   not asserted as fact.

## Test shape

```python
from framework.registry import test_case
from framework.fg_common import make_trace, m2o_id, reconcile, form_arch, list_tag
from framework.qa_fixtures import sweep_model, ensure_qa_user, rpc_as_qa_user

from tests.wf013.common import MARK, fx, sweep_wf013, trace


@test_case(
    id="TEST-WF013-TC221",              # TEST-WF<nnn>-<workbook tc_id suffix>
    name="<workbook TC title, verbatim>",
    workflow="DATAONE-WF-013",           # exactly the owning workflow id
    workflow_name="Customer Invoice Posting: COGS and Revenue Recognition",
    module="dto_account_cogs",           # workbook modules column
    priority="P0",                       # workbook priority
    kind="API",                          # API | DATA | UI | HYBRID
    order=13221,                         # workflow number × 1000 + TC sequence
    description="one line: what is proven",
    traceability=trace("DATAONE-TC221"))
def test_tc221(ctx):
    rpc = ctx.adapter.rpc
    with ctx.step("..."):
        ctx.check("assertion name", expected=..., actual=...)
```

- `ctx.step(name)` per workbook step; `ctx.check(name, expected, actual)`
  records the assertion (raises on mismatch → FAILED). Also
  `ctx.check_true`, `ctx.skip(reason)` (SKIPPED), `ctx.blocked(reason)`
  (BLOCKED).
- `ctx.adapter.rpc` — model access over the web client's own
  `/web/dataset/call_kw` endpoint: `search / search_read / read / create /
  write / unlink / read_group / call(model, method, *args, **kw) /
  ref(xmlid) / field_exists / model_exists`. m2o values read back as
  `[id, name]` → use `m2o_id()`.
- Each RPC call commits its own transaction, so `cr.precommit` hooks fire
  per call and no `precommit.run()` is needed. Cleanup must therefore always
  run (`finally:`).
- `ctx.sql` — read-only PostgreSQL (raises BLOCKED when unconfigured):
  `.one(q)`, `.rows(q)`, `.to_csv(q, path)`, `.column_exists(table, col)`.
- `reconcile(ctx, "DATAONE-TC…", capture, anchors=...)` — the
  DATA_RECONCILIATION pattern: v17 captures and persists the baseline, v19
  diffs against it.
- Errors: never raise a bare `AssertionError`. Let `ctx.check` fail, or wrap
  an expected RPC failure with `try/except OdooRPCError` and `ctx.check` the
  outcome, so the platform records expected vs actual.
- **Mismatch dicts, not assertion loops.** Collect every difference into one
  dict/list and assert it once, so a failure reports all of them.

### Private methods are not reachable

Odoo refuses to dispatch any method whose name starts with an underscore
over RPC — `check_method_name` (v17 `odoo/models.py:145`; v19
`odoo/orm/utils.py:69`, superseded by `service.model.get_public_method`)
raises `AccessError`. Return values are a second gate: a method that returns
a recordset cannot be JSON-marshalled through `/web/dataset/call_kw`.

This decides feasibility more often than anything else, so check it before
planning a test:

- **Reachable:** public model methods (`action_confirm`, `create_revision`,
  `action_view_revisions`, `update_confirmed_order`, …), `fields_get`,
  `get_view`, `search_read`, `read_group`, and every ORM primitive.
- **Not reachable:** `_prepare_*`, `_compute_*`, `_transform_*`,
  `_process_*`, `_get_*` helpers — the bulk of the DTO integration layer.

When a workbook TC's essence lives behind a private method, assert
everything observable about it (declared field attributes via `fields_get`,
the arch via `get_view`, the resulting records after a public entry point
ran, the search domains it relies on) and then `ctx.blocked(...)` naming the
private method and the in-process alternative. Do not re-implement the
private method inside the test — that asserts the test's own code, not the
product's.

## Version-dependent behaviour

`ctx.env.version` is `"17"` or `"19"`. The workbook's own steps split into
"on the v17 clone…" vs "on v19…" — mirror that split; never skip an
assertion just because it will fail on v17.

Version differences go through `ctx.adapter` or `framework/fg_common.py`
helpers, never `if version` scattered in test bodies. The verified pairs:

| Concern | Odoo 17 | Odoo 19 | Helper |
|---|---|---|---|
| Storable product | `type='product'` (`stock/models/product.py:661`) | `type='consu'`, `is_storable=True` (`stock/models/product.py:829`) | `adapter.storable_product_values()` |
| List view type | `'tree'` (`ir_ui_view.py:163`) | `'list'` (`ir_ui_view.py:149`) | `adapter.list_view_type`, `fg_common.list_tag(ctx)` |
| View arch fetch | `get_view()` (`ir_ui_view.py:2613`) | `get_view()` (`ir_ui_view.py:3138`) | `fg_common.form_arch(ctx, model, view_type)` |
| SO cancel | wizard unless `disable_cancel_warning` (`sale_order.py:1096`) | no wizard, cancels directly (`sale_order.py:1325`) | `adapter.cancel_order(id)` |
| Record URL | `/web#id=<id>&model=…` | `/odoo/<path>/<id>` (`web/controllers/home.py:46`) | `adapter.order_id_from_url(url)` |
| ACL check | `check_access_rights(op)` | `check_access(op)`; `check_access_rights` kept as a shim (`orm/models.py:4162`) | assert via RPC `AccessError`, not the method name |

When a new pair is discovered, add it to `adapters/odoo17.py` /
`adapters/odoo19.py` and to this table — not to a test body.

**One legitimate exception.** A test whose *subject is the version delta
itself* may read `ctx.env.version` to compute its own expected value —
`TEST-WF020-TC460` and `TEST-WF020-TC305` assert which `ir.cron`
failure-tracking fields the target has, and the answer differs by version
by definition. That is not behaviour routing: nothing about how the test
runs changes, only what it expects. Behaviour routing still belongs in the
adapter.

## Feasibility policy (this wave)

- **Implement fully:** everything reachable over ORM / SQL / local HTTP
  against the v17 clone.
- **Blocked stub** (implement the test, assert its offline half, then
  `ctx.blocked(reason)`): TCs whose essence needs an external system — the
  Workday SFTP endpoint, a queue-job runner, PrintNode hardware. P0/P1 only,
  with a precise reason string.
- **Leave unimplemented** (registry reports NOT_IMPLEMENTED): the rest,
  chiefly `MANUAL` and `PERFORMANCE` automation types — decision gates,
  PDF/ZPL visual diffs, timed volume runs.
- Per workflow, record the decision per TC in
  `reports/data/wfNNN_feasibility.json`:
  `{"DATAONE-TC…": {"decision": "implemented|blocked_stub|not_implemented",
  "reason": "…", "test_id": "TEST-…"}}`.

## Shared test cases

A workbook TC naming several workflows is **written once**, in the suite of
the workflow with the lowest build order that is in scope
(`scripts/sync_registry.py:owning_workflow`). The other workflows reference
the same `tc_id`; they never re-implement it. `sync_registry.py` prints the
shared list on every run.

## Environment facts (execution target)

- **Odoo 17** = the baseline. Config lives in `D:\Projects\dataone\dto.conf`
  (addons: `odoo-17.0/enterprise-17.0`, `odoo-17.0/addons`,
  `DTO-Odoo/project-addons`, `DTO-Odoo/novobi-addons`,
  `DTO-Odoo/3rd-addons`; PostgreSQL on port 5433). The QA target must be a
  **dedicated clone** with crons, mail servers and the Workday SFTP
  connector deactivated — `scripts/start_platform.ps1` refuses any database
  whose name does not contain `_qa`.
- **Odoo 19** source is available at `D:\Projects\odoo-19.0` (community +
  `enterprise-19.0`) for verification. Whether a v19 *instance* exists is a
  per-workstation fact: when it is unreachable the runner preflight marks
  those runs BLOCKED automatically. Write tests version-aware regardless.
- `config/local.yaml` (gitignored) carries the URLs, database names and the
  read-only PostgreSQL credentials. Without `pg_*`, DATA_RECONCILIATION
  tests report BLOCKED instead of running — they never fall back to a
  weaker assertion.

## Finish check

Writing only; never start a server, run a suite, or touch a database.
Finish with the import-only compile check:

```
venv/Scripts/python.exe -c "from framework import registry; print(len(registry.discover()))"
```
