"""FastAPI backend: REST API + Server-Sent Events + static frontend.

SSE was chosen over WebSocket for the MVP: updates flow one way
(engine → browser), EventSource auto-reconnects natively, and no extra
client library is needed. Events are persisted first, then streamed — a page
refresh replays the full history and continues live from the same channel.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import (FileResponse, HTMLResponse, PlainTextResponse,
                               Response, StreamingResponse)
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend import exporters
from backend.config import ROOT, load_environments, settings
from backend.runner import ChainedExecutor, RunExecutor, cancel_run
from backend.store import Store
from framework import registry

app = FastAPI(title="Odoo Regression Test Runner")
store = Store(settings.data_dir / "results.db")
# Load the workbook-derived registry (regenerate with scripts/sync_registry.py)
store.load_registry(settings.data_dir / "test_registry.json")
# Close out executions orphaned by a previous process
_orphans = store.reconcile_orphans()

FRONTEND = ROOT / "frontend"


def in_scope_features() -> list[str]:
    """Workflow ids the current QA wave covers.

    Read from the registry (data/test_registry.json -> feature_groups.
    in_scope), which scripts/sync_registry.py fills from its
    IN_SCOPE_WORKFLOWS set. Nothing here is hard-coded, so widening the wave
    is a sync_registry edit plus a re-sync — no backend change.
    """
    return [f["feature_id"] for f in store.feature_summary(in_scope_only=True)]


# --------------------------------------------------------------------- API
@app.get("/api/environments")
def api_environments():
    return {"environments": [e.public_dict() for e in load_environments().values()],
            "settings": {"headless": settings.headless,
                         "trace": settings.trace,
                         "screenshot_on_success": settings.screenshot_on_success}}


@app.get("/api/tests")
def api_tests():
    tests = registry.discover()
    latest = store.latest_status_by_test()
    return {"tests": [{**t.public_dict(),
                       "latest": latest.get(t.id, {})} for t in tests]}


@app.get("/api/features")
def api_features(all: bool = False):
    """In-scope workflow dashboard rollup (pass all=true to include every
    workflow in the workbook, including the ones not yet in the wave)."""
    return {"features": store.feature_summary(in_scope_only=not all)}


@app.get("/api/testcases")
def api_testcases(feature: str | None = None, all: bool = False):
    return {"test_cases": store.test_cases_list(
        feature_id=feature, in_scope_only=not all)}


@app.get("/api/testcases/{tc_id}")
def api_testcase(tc_id: str):
    tc = store.test_case(tc_id)
    if not tc:
        raise HTTPException(404, "Test case not found")
    return tc


class RunRequest(BaseModel):
    environment: str            # "odoo17" | "odoo19" | "both"
    test_ids: list[str] | None = None       # platform test ids (TEST-…)
    features: list[str] | None = None       # workflows (DATAONE-WF-013 …)
    test_case_ids: list[str] | None = None  # workbook TC ids (TC-…)
    scope: str | None = None                # "in_scope" → the wave, "all"
    label: str | None = None


def _resolve_selection(req: RunRequest):
    """Selection → registered platform tests. Any combination of platform
    test ids, workflows, workbook TC ids, or a whole-suite scope."""
    all_tests = registry.discover()
    if not any((req.test_ids, req.features, req.test_case_ids, req.scope)):
        return all_tests, "all registered tests"

    picked, why = {}, []
    if req.test_ids:
        wanted = set(req.test_ids)
        picked.update({t.id: t for t in all_tests if t.id in wanted})
        why.append(f"{len(wanted)} test id(s)")
    if req.features or req.scope:
        features = set(req.features or [])
        if req.scope == "in_scope":
            scoped = in_scope_features()
            features |= set(scoped)
            why.append(f"in-scope workflows ({len(scoped)})")
        elif req.scope == "all":
            features |= {t.workflow for t in all_tests}
            why.append("every feature")
        if req.features:
            why.append(", ".join(sorted(req.features)))
        # a workflow's automation = tests tagged with it, plus any test the
        # registry records as covering one of its workbook test cases (a
        # shared TC is written once, in its owning workflow's suite)
        by_id = {t.id: t for t in all_tests}
        picked.update({t.id: t for t in all_tests if t.workflow in features})
        for fg in features:
            for tc in store.test_cases_list(feature_id=fg, in_scope_only=False):
                for test_id in tc.get("automated_test_ids", []):
                    if test_id in by_id:
                        picked[test_id] = by_id[test_id]
    if req.test_case_ids:
        wanted = set(req.test_case_ids)
        for t in all_tests:
            tc_ids = {str(x).split()[0].strip("()")
                      for x in t.traceability.get("tc_ids", [])}
            if tc_ids & wanted:
                picked[t.id] = t
        why.append(", ".join(sorted(wanted)))
    ordered = [t for t in all_tests if t.id in picked]
    return ordered, " · ".join(why)


@app.post("/api/runs")
def api_start_run(req: RunRequest):
    envs = load_environments()
    selected, why = _resolve_selection(req)
    if not selected:
        raise HTTPException(400, "No matching registered tests for that selection")

    what = req.label or why or f"{len(selected)} tests"

    # One run at a time per target. Suites sweep marker-scoped fixtures, so
    # two runs against the same database delete each other's data mid-flight
    # (seen as fixture-token mismatches and FK violations). Refuse instead of
    # producing quietly corrupt results.
    wanted_envs = (["odoo17", "odoo19"] if req.environment == "both"
                   else [req.environment])
    for env_key in wanted_envs:
        busy = store.active_runs(env_key)
        if busy:
            raise HTTPException(409, {
                "message": f"A run is already in progress on "
                           f"{envs[env_key].name if env_key in envs else env_key}. "
                           f"Wait for it to finish (or cancel it) before "
                           f"starting another — concurrent runs corrupt each "
                           f"other's fixtures.",
                "active_run_id": busy[0]["id"],
            })

    if req.environment == "both":
        group_id = "CMP-" + uuid.uuid4().hex[:8].upper()
        executors, run_ids = [], []
        for key in ("odoo17", "odoo19"):
            if key not in envs:
                raise HTTPException(400, f"Environment '{key}' not configured")
            run_id = store.create_run(
                key, envs[key].name, "compare", group_id,
                label=f"{what} — compare {group_id} — {envs[key].name}")
            executors.append(RunExecutor(store, run_id, key, selected))
            run_ids.append(run_id)
        ChainedExecutor(executors).start()
        return {"run_ids": run_ids, "group_id": group_id, "mode": "compare",
                "selected": len(selected), "selection": what}

    if req.environment not in envs:
        raise HTTPException(400, f"Unknown environment '{req.environment}'")
    run_id = store.create_run(req.environment, envs[req.environment].name,
                              "single", None,
                              label=f"{what} — {envs[req.environment].name}")
    RunExecutor(store, run_id, req.environment, selected).start()
    return {"run_ids": [run_id], "mode": "single",
            "selected": len(selected), "selection": what}


@app.post("/api/registry/reload")
def api_registry_reload():
    """Re-import the test packages and re-sync the workbook registry, so
    newly added or edited test scripts become runnable without a restart."""
    n_tests = len(registry.reload())
    n_cases = store.load_registry(settings.data_dir / "test_registry.json")
    return {"tests": n_tests, "test_cases": n_cases}


@app.get("/api/runs")
def api_runs():
    return {"runs": store.runs()}


@app.get("/api/runs/{run_id}")
def api_run(run_id: str):
    run = store.run(run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    return run


@app.post("/api/runs/{run_id}/cancel")
def api_cancel(run_id: str):
    cancel_run(run_id)
    return {"ok": True}


@app.get("/api/runs/{run_id}/events")
async def api_events(run_id: str):
    """SSE stream: replays persisted events, then polls for new ones (0.4 s).
    Ends automatically once RUN_COMPLETED has been delivered."""
    if not store.run(run_id):
        raise HTTPException(404, "Run not found")

    async def gen():
        # Bootstrap: replay every STRUCTURAL event but only the tail of the
        # LOG firehose. A 141-test run persists ~23,000 events, 98% of them
        # LOG; a client joining or refreshing mid-run used to receive all of
        # them in one burst, which is what exhausted the tab.
        events, last_seq, dropped = await asyncio.to_thread(
            store.events_bootstrap, run_id, 200)
        finished = False
        for ev in events:
            if ev["type"] == "RUN_COMPLETED":
                finished = True
            yield f"event: {ev['type']}\ndata: {json.dumps(ev)}\n\n"
        if dropped:
            yield ("event: LOG_TRUNCATED\ndata: "
                   + json.dumps({"payload": {"dropped": dropped}})
                   + "\n\n")

        if finished:
            # The run was already over before this client connected. Nothing
            # further can ever arrive, so end the stream now rather than
            # holding it open: an idle SSE stream behind a tunnel gets
            # dropped, and EventSource then reconnects and replays the whole
            # bootstrap again, forever.
            yield "event: STREAM_END\ndata: {}\n\n"
            return

        idle_after_finish = 0
        while True:
            # Paged: one poll can never hand the browser more than
            # Store.EVENT_PAGE events, so a burst is spread across frames
            # instead of arriving as one unbreakable chunk.
            events = await asyncio.to_thread(
                store.events_since, run_id, last_seq)
            for ev in events:
                last_seq = ev["seq"]
                if ev["type"] in ("RUN_COMPLETED",):
                    finished = True
                yield f"event: {ev['type']}\ndata: {json.dumps(ev)}\n\n"
            if finished:
                idle_after_finish += 1
                if idle_after_finish > 2:
                    yield "event: STREAM_END\ndata: {}\n\n"
                    return
            yield ": keepalive\n\n"
            # A full page means more is waiting: drain it without the idle
            # delay, so a backlog clears quickly but still page by page.
            await asyncio.sleep(
                0 if len(events) >= store.EVENT_PAGE else 0.4)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


@app.get("/api/runs/{run_id}/log")
def api_run_log(run_id: str, tail: int = 2000):
    """The run's log as plain text, newest `tail` lines.

    A finished run's page needs the log as TEXT, not as a replay: rebuilding
    it from the event stream means shipping thousands of JSON objects the
    browser must parse and apply one by one. This ships the lines already
    rendered, and only when the reader asks for them.
    """
    if not store.run(run_id):
        raise HTTPException(404, "Run not found")
    lines = store.log_lines(run_id, tail)
    return PlainTextResponse("\n".join(lines),
                             headers={"Cache-Control": "no-store"})


@app.get("/api/results/{result_id}")
def api_result(result_id: str):
    res = store.result(result_id)
    if not res:
        raise HTTPException(404, "Result not found")
    return res


@app.get("/api/artifacts/{artifact_id}")
def api_artifact(artifact_id: int):
    art = store.artifact(artifact_id)
    if not art or not Path(art["path"]).exists():
        raise HTTPException(404, "Artifact not found")
    media = {"screenshot": "image/png", "trace": "application/zip",
             "video": "video/webm", "log": "text/plain; charset=utf-8"}
    return FileResponse(art["path"],
                        media_type=media.get(art["type"],
                                             "application/octet-stream"),
                        filename=Path(art["path"]).name)


@app.get("/api/compare/{group_id}")
def api_compare(group_id: str):
    cmp_ = store.compare_group(group_id)
    if not cmp_:
        raise HTTPException(404, "Comparison group not found")
    return cmp_


# ----------------------------------------------------------------- export
XLSX_MEDIA = ("application/vnd.openxmlformats-officedocument"
              ".spreadsheetml.sheet")


def _stamp() -> str:
    from datetime import datetime
    return datetime.now().strftime("%Y%m%d-%H%M")


def _xlsx(payload: bytes, filename: str) -> Response:
    return Response(
        content=payload, media_type=XLSX_MEDIA,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'})


def _markdown(text: str, filename: str) -> PlainTextResponse:
    return PlainTextResponse(
        text, media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@app.get("/api/export/testcases.xlsx")
def api_export_testcases(all: bool = False):
    """The whole test-case registry as a workbook.

    Default is the in-scope wave, matching the dashboard; all=true adds every
    workflow the Excel knowledge base defines.
    """
    payload = exporters.testcases_workbook(store, in_scope_only=not all)
    scope = "all" if all else "in-scope"
    return _xlsx(payload, f"DataOne-TestCases-{scope}-{_stamp()}.xlsx")


@app.get("/api/runs/{run_id}/export.xlsx")
def api_export_run_xlsx(run_id: str):
    """One run in full: summary, results, every step, every assertion."""
    try:
        payload = exporters.run_workbook(store, run_id)
    except KeyError:
        raise HTTPException(404, "Run not found")
    return _xlsx(payload, f"{run_id}-detail-{_stamp()}.xlsx")


@app.get("/api/runs/{run_id}/export.md")
def api_export_run_md(run_id: str, only: str | None = None):
    """Detailed Markdown for every case in a run.

    `only=FAILED,ERROR` narrows it to what needs triage — the same shape the
    mailed FAILURES.md uses, so a reader can act on either.
    """
    try:
        text = exporters.run_markdown(store, run_id, only=only)
    except KeyError:
        raise HTTPException(404, "Run not found")
    suffix = "-" + only.replace(",", "-").lower() if only else ""
    return _markdown(text, f"{run_id}{suffix}-{_stamp()}.md")


@app.get("/api/results/{result_id}/export.md")
def api_export_result_md(result_id: str):
    """One case, fully expanded — steps, assertions, error, artifacts."""
    try:
        text = exporters.result_markdown(store, result_id)
    except KeyError:
        raise HTTPException(404, "Result not found")
    res = store.result(result_id)
    return _markdown(text, f"{res['test_id']}-{result_id}.md")


# ---------------------------------------------------------------- frontend
app.mount("/static", StaticFiles(directory=str(FRONTEND)), name="static")


def _asset_version(*names: str) -> str:
    """A short content hash over the frontend assets.

    The site is published through Cloudflare, which caches ``.js`` and
    ``.css`` by default — measured: a deploy served the previous app.js for
    97 minutes (``cf-cache-status: HIT``, ``Age: 5838``), so the browser ran
    old code against a new backend and nobody could tell from the page.

    Stamping the URL with a content hash makes every deploy a NEW url. The
    CDN then caches correctly instead of wrongly, and no cache purge is
    needed. Hashing content rather than mtime means an unchanged file keeps
    its url across restarts and rebuilds.
    """
    digest = hashlib.sha256()
    for name in names:
        path = FRONTEND / name
        if path.exists():
            digest.update(path.read_bytes())
    return digest.hexdigest()[:12]


@app.get("/")
def index():
    """index.html, with the asset urls version-stamped, never cached.

    The HTML must stay uncached or the browser would keep asking for the
    previous version's assets — the stamp only helps if the document
    carrying it is fresh.
    """
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    version = _asset_version("app.js", "style.css")
    html = (html.replace("/static/app.js", f"/static/app.js?v={version}")
                .replace("/static/style.css", f"/static/style.css?v={version}"))
    return HTMLResponse(html, headers={
        "Cache-Control": "no-store, must-revalidate",
        "Pragma": "no-cache",
    })
