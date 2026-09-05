/* Odoo Regression Test Runner — dashboard SPA (no build step).
   Views: #/ (workflows) · #/feature/<id> · #/testcase/<id> · #/tests
   · #/run/<id> (live execution) · #/result/<id> · #/compare/<group> · #/runs
   All numbers come from the backend's persisted results — nothing is faked.

   PERFORMANCE NOTE (why the live view is written the way it is)
   A 141-test run persists ~23,000 SSE events and 98% of them are LOG. The
   first version appended each one with `logEl.textContent += line` and then
   read `scrollHeight`, which is a full re-serialisation of a 3 MB text node
   plus a forced synchronous layout, 23,000 times — quadratic work that made
   the tab run out of memory and crash. Three rules keep it flat now:
     1. events are queued and applied once per animation frame, never per event;
     2. the log is a capped ring buffer that APPENDS a text node rather than
        rewriting the whole one, and measures scroll position once per frame;
     3. result rows are patched in place through a Map, never re-rendered
        wholesale.
   The backend does its half in app.py (bounded replay + paged polling). */
"use strict";

const app = document.getElementById("app");
const esc = s => String(s ?? "").replace(/[&<>"']/g,
  c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const api = async (path, opts) => {
  const r = await fetch(path, opts);
  if (!r.ok) {
    const detail = (await r.json().catch(() => ({}))).detail;
    if (detail && typeof detail === "object") {
      const err = new Error(detail.message || r.statusText);
      err.activeRunId = detail.active_run_id;
      throw err;
    }
    throw new Error(detail || r.statusText);
  }
  return r.json();
};

const chip = st =>
  `<span class="status st-${esc(st || "NOTRUN").replace(/ /g, "")}">${esc(st || "NOT RUN")}</span>`;
const fmtMs = ms => ms == null ? "—" : (ms / 1000).toFixed(1) + "s";
const fmtDate = ts => ts ? new Date(ts * 1000).toLocaleString() : "—";
let liveES = null;

/* --------------------------------------------------------------- theme */
const THEME_KEY = "qa.theme";
const applyTheme = t => document.documentElement.setAttribute("data-theme", t);
applyTheme(localStorage.getItem(THEME_KEY) || "dark");
document.getElementById("themetoggle").onclick = () => {
  const next = document.documentElement.getAttribute("data-theme") === "dark"
    ? "light" : "dark";
  localStorage.setItem(THEME_KEY, next);
  applyTheme(next);
};

/* -------------------------------------------------------------- toasts */
/* Replaces alert()/confirm(): a modal dialog blocks the SSE event loop, and
   during a run that means the queue backs up behind a message box. */
function toast(message, { title = "", kind = "", actions = [], ms = 6000 } = {}) {
  const el = document.createElement("div");
  el.className = "toast " + kind;
  el.innerHTML = (title ? `<b>${esc(title)}</b>` : "") + esc(message)
    + (actions.length ? `<div class="acts">${actions.map((a, i) =>
      `<button class="secondary small" data-act="${i}">${esc(a.label)}</button>`
    ).join("")}</div>` : "");
  actions.forEach((a, i) => {
    const b = el.querySelector(`[data-act="${i}"]`);
    if (b) b.onclick = () => { el.remove(); a.run(); };
  });
  document.getElementById("toasts").appendChild(el);
  if (ms) setTimeout(() => el.remove(), ms);
  return el;
}

/* --------------------------------------------------------- export menu */
/* Every entry is a plain link to a backend endpoint, so the browser handles
   the download natively — no blob is built in the tab. */
function exportMenu(groups, label = "Export") {
  const id = "menu" + Math.random().toString(36).slice(2, 8);
  const items = groups.map(g => (g.head ? `<div class="head">${esc(g.head)}</div>`
    : g.hr ? "<hr>"
    : `<a href="${esc(g.href)}" download>${esc(g.label)}${
        g.note ? `<small>${esc(g.note)}</small>` : ""}</a>`)).join("");
  return `<div class="menu" id="${id}">
    <button class="secondary" data-menu>${esc(label)} ▾</button>
    <div class="list">${items}</div></div>`;
}

function bindMenus() {
  document.querySelectorAll("[data-menu]").forEach(btn => {
    btn.onclick = e => {
      e.stopPropagation();
      const menu = btn.closest(".menu");
      const wasOpen = menu.classList.contains("open");
      document.querySelectorAll(".menu.open").forEach(m => m.classList.remove("open"));
      menu.classList.toggle("open", !wasOpen);
    };
  });
}
document.addEventListener("click", () =>
  document.querySelectorAll(".menu.open").forEach(m => m.classList.remove("open")));

/* --------------------------------------------------------- run helpers */
const ENV_KEY = "qa.env";
const envGet = () => localStorage.getItem(ENV_KEY) || "odoo19";
const envSet = v => localStorage.setItem(ENV_KEY, v);

async function envPicker(id = "envpick") {
  const { environments } = await api("/api/environments");
  const cur = envGet();
  const opts = environments.map(e =>
    `<option value="${esc(e.key)}"${e.key === cur ? " selected" : ""}>${
      esc(e.name)} — ${esc(e.db)}</option>`).join("");
  return `<label class="field"><span>Target</span>
    <select id="${id}">${opts}
      <option value="both"${cur === "both" ? " selected" : ""}>Compare Odoo 17 ↔ 19</option>
    </select></label>`;
}

function bindEnvPicker(id = "envpick") {
  const el = document.getElementById(id);
  if (el) el.onchange = () => envSet(el.value);
}

async function startRun(body, buttonEl) {
  const environment = document.getElementById("envpick")?.value || envGet();
  envSet(environment);
  const original = buttonEl?.innerHTML;
  if (buttonEl) { buttonEl.disabled = true; buttonEl.textContent = "Starting…"; }
  try {
    const res = await api("/api/runs", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ environment, ...body })
    });
    location.hash = res.mode === "compare"
      ? `#/run/${res.run_ids[0]}?group=${res.group_id}`
      : `#/run/${res.run_ids[0]}`;
  } catch (err) {
    if (err.activeRunId) {
      toast(err.message, {
        title: "A run is already in progress", kind: "error", ms: 0,
        actions: [{ label: "Open it", run: () => location.hash = `#/run/${err.activeRunId}` }]
      });
    } else {
      toast(err.message, { title: "Could not start the run", kind: "error" });
    }
    if (buttonEl) { buttonEl.disabled = false; buttonEl.innerHTML = original; }
  }
}

/* --------------------------------------------------- client-side filter */
/* Filters rows already in the DOM. No refetch, so typing stays instant even
   with the full 3,000-row registry on screen. */
function bindFilter(inputId, rowSelector, countId) {
  const input = document.getElementById(inputId);
  if (!input) return;
  const rows = [...document.querySelectorAll(rowSelector)];
  const haystacks = rows.map(r => r.textContent.toLowerCase());
  const counter = countId ? document.getElementById(countId) : null;
  let timer = null;
  const run = () => {
    const q = input.value.trim().toLowerCase();
    let shown = 0;
    rows.forEach((r, i) => {
      const hit = !q || haystacks[i].includes(q);
      r.hidden = !hit;
      if (hit) shown++;
    });
    if (counter) counter.textContent = q ? `${shown} of ${rows.length}` : rows.length;
  };
  input.oninput = () => { clearTimeout(timer); timer = setTimeout(run, 90); };
  run();
}

function bindStatusFilter(groupId, rowSelector, attr = "status") {
  const group = document.getElementById(groupId);
  if (!group) return;
  const rows = [...document.querySelectorAll(rowSelector)];
  group.querySelectorAll("button").forEach(btn => btn.onclick = () => {
    group.querySelectorAll("button").forEach(b => b.classList.remove("on"));
    btn.classList.add("on");
    const want = btn.dataset.filter;
    rows.forEach(r => {
      r.dataset.hiddenByStatus =
        (want === "*" || r.dataset[attr] === want) ? "" : "1";
      r.hidden = !!r.dataset.hiddenByStatus;
    });
  });
}

/* --------------------------------------------------- workflow dashboard */
const PRIO = ["P0", "P1", "P2", "P3"];
const rollup = (m, keys) => keys.map(k =>
  m[k] ? `<span class="mini st-${esc(k).replace(/ /g, "")}">${m[k]} ${esc(k)}</span>` : ""
).join("") || "<span class='muted small'>not run</span>";

async function viewFeatures() {
  const { features } = await api("/api/features");
  const sum = key => features.reduce((a, f) => a + (f[key] || 0), 0);
  const sumMap = key => features.reduce((a, f) => {
    Object.entries(f[key] || {}).forEach(([k, v]) => a[k] = (a[k] || 0) + v);
    return a;
  }, {});
  const v19 = sumMap("v19");
  const executedKeys = ["PASS", "FAIL", "BLOCKED", "ERROR"];
  const notRun = sum("total") - executedKeys.reduce((a, k) => a + (v19[k] || 0), 0);

  app.innerHTML = `
    <div class="pagehead">
      <div class="grow">
        <h1>Workflows — DataOne 17 → 19</h1>
        <div class="sub muted small">Workbook v1.0 · registry synced read-only from Excel</div>
      </div>
    </div>

    <div class="toolbar">
      ${await envPicker()}
      <div class="field search"><span>Filter</span>
        <input type="search" id="fgsearch" placeholder="workflow, name, module…"></div>
      <div class="grow"></div>
      ${exportMenu([
        { head: "Test cases" },
        { href: "/api/export/testcases.xlsx", label: "In-scope test cases (.xlsx)",
          note: "Every TC in the current wave + workflow rollup" },
        { href: "/api/export/testcases.xlsx?all=true", label: "All test cases (.xlsx)",
          note: "Every workflow in the workbook, in scope or not" },
      ], "Export")}
      <button id="runAllFg">▶ Run in-scope workflows</button>
    </div>

    <div class="stats">
      <div class="stat brand"><b>${sum("total")}</b><span>test cases</span></div>
      <div class="stat"><b>${sum("automatable")}</b><span>automatable</span></div>
      <div class="stat run"><b>${sum("automated")}</b><span>automated</span></div>
      <div class="stat pass"><b>${v19.PASS || 0}</b><span>v19 pass</span></div>
      <div class="stat fail"><b>${(v19.FAIL || 0) + (v19.ERROR || 0)}</b><span>v19 fail / error</span></div>
      <div class="stat block"><b>${v19.BLOCKED || 0}</b><span>v19 blocked</span></div>
      <div class="stat"><b>${notRun}</b><span>v19 not run</span></div>
    </div>

    <div class="panel flush">
      <div class="panelhead"><h2>Workflows</h2>
        <span class="muted small" id="fgcount">${features.length}</span>
        <div class="grow"></div></div>
      <div class="tablewrap"><table class="matrix">
        <thead><tr><th>Workflow</th><th>Name</th><th class="numeric">TCs</th>
          <th>Priorities</th><th>Automation coverage</th>
          <th>Odoo 17</th><th>Odoo 19</th><th></th></tr></thead>
        <tbody>${features.map(f => `
          <tr class="fgrow">
            <td class="mono nowrap"><a href="#/feature/${esc(f.feature_id)}">${esc(f.feature_id)}</a></td>
            <td><a href="#/feature/${esc(f.feature_id)}"><b>${esc(f.name)}</b></a>
                <div class="small muted">${esc((f.business_purpose || "").slice(0, 96))}</div></td>
            <td class="numeric"><b>${f.total}</b></td>
            <td class="small nowrap">${PRIO.map(p =>
              f.priorities[p] ? `${p}:${f.priorities[p]}` : "").filter(Boolean).join(" ")}</td>
            <td>
              <div class="covbar" title="${f.automated}/${f.automatable} automatable TCs automated">
                <div style="width:${f.coverage_pct}%"></div></div>
              <span class="small muted">${f.automated}/${f.automatable} (${f.coverage_pct}%)
                · ${f.automation_types.MANUAL || 0} manual</span>
            </td>
            <td class="small nowrap">${rollup(f.v17, executedKeys)}</td>
            <td class="small nowrap">${rollup(f.v19, executedKeys)}</td>
            <td class="nowrap">${f.automated
              ? `<button class="secondary small runfeature" data-fg="${esc(f.feature_id)}">▶ Run</button>`
              : `<span class="muted small" title="no registered automation yet">—</span>`}</td>
          </tr>`).join("")}</tbody>
      </table></div>
    </div>
    <p class="footnote">Counts come from the test-case registry
      (<span class="mono">data/test_registry.json</span>, synced read-only from the Excel
      workbook) joined with persisted execution results. Click a row for its test cases;
      Run executes that workflow's registered automation against the selected target.</p>`;

  bindEnvPicker(); bindMenus();
  bindFilter("fgsearch", ".fgrow", "fgcount");
  document.getElementById("runAllFg").onclick = e =>
    startRun({ scope: "in_scope", label: "In-scope workflow regression suite" },
      e.currentTarget);
  document.querySelectorAll(".runfeature").forEach(b => b.onclick = e => {
    e.stopPropagation();
    startRun({ features: [b.dataset.fg], label: `${b.dataset.fg} suite` }, b);
  });
}

/* ---------------------------------------------------- one workflow view */
async function viewFeature(fgId) {
  const [{ test_cases }, { features }] = await Promise.all([
    api(`/api/testcases?feature=${encodeURIComponent(fgId)}`), api("/api/features")]);
  const f = features.find(x => x.feature_id === fgId) || {};

  app.innerHTML = `
    <a class="crumb" href="#/">← All workflows</a>
    <div class="pagehead"><div class="grow">
      <h1><span class="mono">${esc(fgId)}</span> ${esc(f.name || "")}</h1>
      <div class="sub muted small">${esc(f.business_purpose || "")}</div>
    </div></div>

    <div class="panel tight small">
      <span class="muted">Modules:</span> ${esc(f.key_modules || "—")}
      &nbsp;·&nbsp; <span class="muted">Roles:</span> ${esc(f.primary_roles || "—")}
    </div>

    <div class="toolbar">
      ${await envPicker()}
      <div class="field search"><span>Filter</span>
        <input type="search" id="tcsearch" placeholder="TC id, title, status…"></div>
      <div class="grow"></div>
      ${exportMenu([
        { head: "Test cases" },
        { href: "/api/export/testcases.xlsx", label: "In-scope test cases (.xlsx)",
          note: "Every workflow in the current wave" },
        { href: "/api/export/testcases.xlsx?all=true", label: "All test cases (.xlsx)" },
      ], "Export")}
      <button id="runFeature">▶ Run ${esc(fgId)}</button>
    </div>

    <div class="stats">
      <div class="stat brand"><b>${test_cases.length}</b><span>test cases</span></div>
      <div class="stat run"><b>${f.automated || 0}</b><span>automated</span></div>
      <div class="stat"><b>${f.automatable || 0}</b><span>automatable</span></div>
      <div class="stat"><b>${(f.automation_types || {}).MANUAL || 0}</b><span>manual</span></div>
    </div>

    <div class="panel flush">
      <div class="panelhead"><h2>Test cases</h2>
        <span class="muted small" id="tccount">${test_cases.length}</span></div>
      <div class="tablewrap"><table class="matrix">
        <thead><tr><th>TC</th><th>Title</th><th>Prio</th><th>Automation</th>
          <th>Status</th><th>v17</th><th>v19</th><th>Last execution</th><th></th></tr></thead>
        <tbody>${test_cases.map(t => `
          <tr class="tcrow">
            <td class="mono small nowrap"><a href="#/testcase/${esc(t.test_case_id)}">${esc(t.test_case_id)}</a></td>
            <td><a href="#/testcase/${esc(t.test_case_id)}">${esc(t.title)}</a></td>
            <td><span class="tag ${t.priority === "P0" ? "p0" : t.priority === "P1" ? "p1" : ""}">${esc(t.priority)}</span></td>
            <td class="small nowrap">${esc(t.automation_type)}</td>
            <td class="small muted nowrap">${esc(t.automation_status)}</td>
            <td>${chip(t.v17_status)}</td>
            <td>${chip(t.v19_status)}</td>
            <td class="mono small">${t.last_execution_id
              ? `<a href="#/result/${esc(t.last_execution_id)}">${esc(t.last_execution_id)}</a>`
              : "<span class='muted'>—</span>"}</td>
            <td class="nowrap">${t.automated_test_ids.length
              ? `<button class="secondary small runtc" data-tc="${esc(t.test_case_id)}">▶ Run</button>`
              : `<span class="muted small">—</span>`}</td>
          </tr>`).join("")}</tbody>
      </table></div>
    </div>`;

  bindEnvPicker(); bindMenus();
  bindFilter("tcsearch", ".tcrow", "tccount");
  document.getElementById("runFeature").onclick = e =>
    startRun({ features: [fgId], label: `${fgId} suite` }, e.currentTarget);
  document.querySelectorAll(".runtc").forEach(b => b.onclick = () =>
    startRun({ test_case_ids: [b.dataset.tc], label: b.dataset.tc }, b));
}

/* --------------------------------------------------------- test case */
async function viewTestCase(tcId) {
  const t = await api(`/api/testcases/${encodeURIComponent(tcId)}`);
  const pre = s => `<div class="prebox">${esc(s || "—")}</div>`;
  const execs = (t.executions || []).map(e => `
    <tr>
      <td class="mono small">${esc(e.id)}</td>
      <td class="nowrap">${esc(e.env_name || e.environment)}</td>
      <td>${chip(e.canonical)}</td>
      <td class="small">${esc(e.failure_class || "")}</td>
      <td class="mono small numeric">${fmtMs(e.duration_ms)}</td>
      <td class="small muted nowrap">${fmtDate(e.finished_at)}</td>
      <td class="nowrap">
        <a href="#/result/${esc(e.id)}"><button class="secondary small">Evidence</button></a>
        <a href="/api/results/${esc(e.id)}/export.md" download><button class="ghost small">.md</button></a>
      </td>
    </tr>`).join("");

  app.innerHTML = `
    <a class="crumb" href="#/feature/${esc(t.feature_id)}">← ${esc(t.feature_id)} ${esc(t.feature_name)}</a>
    <div class="pagehead"><div class="grow">
      <h1><span class="mono">${esc(t.test_case_id)}</span> ${esc(t.title)}</h1>
    </div></div>

    <div class="toolbar">
      ${await envPicker()}
      <div class="grow"></div>
      ${t.automated_test_ids.length
        ? `<button id="runTc">▶ Run ${esc(t.test_case_id)}</button>`
        : `<span class="muted small">No registered automation for this test case
             (${esc(t.automation_status)}) — nothing to run yet.</span>`}
    </div>

    <div class="panel"><div class="kv">
      <div><span>Priority</span><b>${esc(t.priority)}</b></div>
      <div><span>Type</span>${esc(t.test_type)}</div>
      <div><span>Role</span>${esc(t.role || "—")}</div>
      <div><span>Suite</span>${esc(t.suite || "—")}</div>
      <div><span>Phase</span>${esc(t.execution_phase || "—")}</div>
      <div class="grow"></div>
      <div><span>Odoo 17</span>${chip(t.v17_status)}</div>
      <div><span>Odoo 19</span>${chip(t.v19_status)}</div>
    </div></div>

    <div class="panel">
      <h2>Automation</h2>
      <div class="kv">
        <div><span>Type</span><b>${esc(t.automation_type)}</b></div>
        <div><span>Status</span>${esc(t.automation_status)}</div>
        <div><span>Wave (workbook)</span>${esc(t.automation_wave || "—")}</div>
      </div>
      <p class="small muted">Workbook approach: ${esc(t.automation_approach || "—")}</p>
      ${t.automated_test_ids.length ? `<p class="small">Automated by:
        <b class="mono">${t.automated_test_ids.map(esc).join(", ")}</b></p>` : ""}
      ${t.related_test_ids.length ? `<p class="small muted">Related automation:
        ${t.related_test_ids.map(esc).join(", ")}</p>` : ""}
    </div>
    <div class="panel"><h2>User story</h2>${pre(t.description)}</div>
    <div class="panel"><h2>Preconditions</h2>${pre(t.preconditions)}</div>
    <div class="panel"><h2>Steps</h2>${pre(t.steps)}</div>
    <div class="panel"><h2>Expected result
      <span class="muted small" style="text-transform:none;letter-spacing:0">
        (verbatim from workbook — source of truth)</span></h2>${pre(t.expected_result)}</div>
    ${t.v19_watch ? `<div class="panel"><h2>v19 watch</h2>${pre(t.v19_watch)}</div>` : ""}

    <div class="panel flush">
      <div class="panelhead"><h2>Execution history</h2>
        <span class="muted small">every run of this test case, newest first</span></div>
      <div class="tablewrap"><table class="matrix">
        <thead><tr><th>Execution</th><th>Environment</th><th>Status</th>
          <th>Failure class</th><th>Duration</th><th>Finished</th><th></th></tr></thead>
        <tbody>${execs || "<tr><td colspan=7 class='empty'>No executions yet</td></tr>"}</tbody>
      </table></div>
    </div>
    <p class="footnote">Source: ${esc(t.source_workbook)} · sheet
      “${esc(t.source_sheet)}” row ${esc(t.source_row)}${
        t.test_execution_row ? ` · “Test Execution” row ${esc(t.test_execution_row)}` : ""}</p>`;

  bindEnvPicker();
  const runBtn = document.getElementById("runTc");
  if (runBtn) runBtn.onclick = e => startRun({ test_case_ids: [tcId], label: tcId }, e.currentTarget);
}

/* ------------------------------------------------- registered test list */
async function viewDashboard() {
  const { tests } = await api("/api/tests");

  app.innerHTML = `
    <div class="pagehead"><div class="grow">
      <h1>Automated tests</h1>
      <div class="sub muted small">${tests.length} registered scripts the runner can execute</div>
    </div></div>

    <div class="toolbar">
      ${await envPicker()}
      <div class="field search"><span>Filter</span>
        <input type="search" id="tsearch" placeholder="test id, name, workflow, module…"></div>
      <div class="grow"></div>
      <button class="secondary" id="reloadReg">↻ Reload registry</button>
      <button class="secondary" id="runSelected">▶ Run selected</button>
      <button id="runAll">▶ Run all</button>
    </div>

    <div class="panel flush">
      <div class="panelhead">
        <label class="muted small" style="display:flex;gap:7px;align-items:center;cursor:pointer">
          <input type="checkbox" id="selall"> Select all visible</label>
        <div class="grow"></div>
        <span class="muted small" id="tcount">${tests.length}</span>
      </div>
      <div id="testlist"></div>
    </div>`;

  document.getElementById("testlist").innerHTML = tests.map(t => {
    const latest = Object.entries(t.latest || {}).map(([env, l]) =>
      `<a href="#/result/${esc(l.result_id)}" title="latest on ${esc(env)}">
         <span class="tag">${esc(env)}</span> ${chip(l.status)}</a>`).join(" ")
      || chip("NOT RUN");
    const trace = (t.traceability?.tc_ids || []).join(", ");
    return `<div class="testcard">
      <input type="checkbox" class="sel" value="${esc(t.id)}">
      <div class="grow">
        <div class="tc-id">${esc(t.id)}${trace ? ` · ${esc(trace)}` : ""}</div>
        <div class="tc-name">${esc(t.name)}</div>
        <div class="tc-desc">${esc(t.description)}</div>
        <div class="tags">
          <span class="tag">${esc(t.workflow_name || t.workflow)}</span>
          <span class="tag ${t.priority === "P0" ? "p0" : t.priority === "P1" ? "p1" : ""}">${esc(t.priority)}</span>
          <span class="tag kind${esc(t.kind)}">${esc(t.kind)}</span>
          <span class="tag">${esc(t.module)}</span>
        </div>
      </div>
      <div style="text-align:right">${latest}<br>
        <button class="secondary small runone" data-id="${esc(t.id)}"
                style="margin-top:8px">▶ Run</button></div>
    </div>`;
  }).join("");

  bindEnvPicker();
  bindFilter("tsearch", ".testcard", "tcount");
  document.getElementById("selall").onchange = e =>
    document.querySelectorAll(".testcard:not([hidden]) .sel")
      .forEach(c => c.checked = e.target.checked);
  document.getElementById("reloadReg").onclick = async e => {
    e.currentTarget.disabled = true;
    try {
      const r = await api("/api/registry/reload", { method: "POST" });
      toast(`${r.tests} tests · ${r.test_cases} workbook cases`,
        { title: "Registry reloaded", kind: "ok" });
      route();
    } catch (err) { toast(err.message, { title: "Reload failed", kind: "error" }); }
  };
  document.getElementById("runAll").onclick = e =>
    startRun({ label: "All registered tests" }, e.currentTarget);
  document.getElementById("runSelected").onclick = e => {
    const ids = [...document.querySelectorAll(".sel:checked")].map(c => c.value);
    if (!ids.length) return toast("Select at least one test first.", { kind: "error" });
    startRun({ test_ids: ids, label: `${ids.length} selected tests` }, e.currentTarget);
  };
  document.querySelectorAll(".runone").forEach(b =>
    b.onclick = () => startRun({ test_ids: [b.dataset.id], label: b.dataset.id }, b));
}

/* ------------------------------------------------------------- live run */
const LOG_MAX = 1200;        // lines kept in the DOM
const LOG_TRIM = 400;        // trimmed in one bulk pass, not line by line

async function viewRun(runId, groupId) {
  const run = await api(`/api/runs/${runId}`);
  const results = new Map();
  (run.results || []).forEach(r => results.set(r.test_id, r));
  const finishedRun = ["COMPLETED", "CANCELLED", "INTERRUPTED"].includes(run.status);

  app.innerHTML = `
    <a class="crumb" href="#/runs">← Run history</a>
    <div class="pagehead"><div class="grow">
      <h1>Run <span class="mono">${esc(runId)}</span>
        <span id="runstatus">${chip(run.status)}</span></h1>
      <div class="sub muted small">${esc(run.label || "")}</div>
    </div></div>

    <div class="toolbar">
      <div class="field"><span>Environment</span><b>${esc(run.env_name)}</b></div>
      <div class="field"><span>Mode</span><b>${esc(run.mode)}</b></div>
      <div class="field"><span>Started</span><b class="small">${fmtDate(run.started_at)}</b></div>
      <div class="grow"></div>
      ${groupId ? `<a href="#/compare/${esc(groupId)}"><button class="secondary">17 ↔ 19 comparison</button></a>` : ""}
      ${exportMenu([
        { head: "This run" },
        { href: `/api/runs/${runId}/export.xlsx`, label: "Full detail (.xlsx)",
          note: "Summary · results · every step · every assertion" },
        { href: `/api/runs/${runId}/export.md`, label: "Detailed report — all cases (.md)",
          note: "One section per case, steps and assertions expanded" },
        { hr: true },
        { href: `/api/runs/${runId}/export.md?only=FAILED,ERROR`,
          label: "Triage report — failures only (.md)",
          note: "Just FAILED and ERROR, for handing to Claude Code" },
        { href: `/api/runs/${runId}/export.md?only=BLOCKED`,
          label: "Blocked cases (.md)", note: "With the recorded block reason" },
      ], "Export")}
      <button class="danger" id="cancel" ${finishedRun ? "disabled" : ""}>✕ Cancel</button>
    </div>

    <div class="panel">
      <div class="stats" id="counters"></div>
      <div class="progressline">
        <div class="progress"><div id="bar" style="width:0%"></div></div>
        <span class="pct" id="pct">0%</span>
      </div>
      <div class="current" id="current" hidden></div>
    </div>

    <div class="panel flush">
      <div class="panelhead"><h2>Results</h2>
        <div class="segmented" id="resfilter">
          <button data-filter="*" class="on">All</button>
          <button data-filter="PASSED">Passed</button>
          <button data-filter="FAILED">Failed</button>
          <button data-filter="ERROR">Error</button>
          <button data-filter="BLOCKED">Blocked</button>
        </div>
        <div class="grow"></div>
        <div class="search"><input type="search" id="ressearch" placeholder="Filter results…"></div>
      </div>
      <div id="results"></div>
    </div>

    <div class="panel flush">
      <div class="panelhead"><h2>Live log</h2>
        <span class="muted small" id="logmeta"></span>
        <div class="grow"></div>
        <button class="ghost small" id="logpause">⏸ Pause</button>
        <button class="ghost small" id="logclear">Clear</button>
      </div>
      <div style="padding:12px 14px"><pre class="livelog" id="livelog"></pre></div>
    </div>`;

  bindMenus();
  const cancelBtn = document.getElementById("cancel");
  cancelBtn.onclick = () => {
    cancelBtn.disabled = true;
    api(`/api/runs/${runId}/cancel`, { method: "POST" })
      .then(() => toast("Cancel requested — the current test finishes first.",
        { title: "Cancelling", kind: "ok" }))
      .catch(err => { cancelBtn.disabled = false; toast(err.message, { kind: "error" }); });
  };

  const state = {
    total: run.total || (run.results || []).length, done: 0,
    passed: run.passed || 0, failed: run.failed || 0, skipped: run.skipped || 0,
    errors: run.errors || 0, blocked: run.blocked || 0, running: null,
  };

  /* ---- counters (cheap: 7 numbers, repainted at most once per frame) */
  const countersEl = document.getElementById("counters");
  const barEl = document.getElementById("bar");
  const pctEl = document.getElementById("pct");
  function renderCounters() {
    const pending = Math.max(0, state.total - state.done - (state.running ? 1 : 0));
    countersEl.innerHTML = `
      <div class="stat brand"><b>${state.done} / ${state.total}</b><span>tests done</span></div>
      <div class="stat pass"><b>${state.passed}</b><span>passed</span></div>
      <div class="stat fail"><b>${state.failed}</b><span>failed</span></div>
      <div class="stat err"><b>${state.errors}</b><span>error</span></div>
      <div class="stat block"><b>${state.blocked}</b><span>blocked</span></div>
      <div class="stat skip"><b>${state.skipped}</b><span>skipped</span></div>
      <div class="stat"><b>${pending}</b><span>pending</span></div>`;
    const pct = state.total ? Math.round(100 * state.done / state.total) : 0;
    barEl.style.width = pct + "%";
    pctEl.textContent = pct + "%";
  }

  /* ---- result rows: built once, then PATCHED IN PLACE.
     Re-rendering all 141 rows on every one of ~23,000 events is what made the
     old view drop frames; a Map keyed by test_id keeps each update O(1). */
  const resultsEl = document.getElementById("results");
  const rowEls = new Map();
  const rowHTML = r => `
    <div class="grow">
      <span class="tc-id">${esc(r.test_id)}</span>
      <div class="tc-name" style="font-size:13.5px">${esc(r.name || "")}</div>
      ${r.failed_step ? `<div class="small muted">failed step: ${esc(r.failed_step)}</div>` : ""}
      ${r.error ? `<div class="small" style="color:var(--fail)">${esc(String(r.error).slice(0, 220))}</div>` : ""}
      ${r.skip_reason ? `<div class="small muted">${esc(String(r.skip_reason).slice(0, 220))}</div>` : ""}
    </div>
    <span class="muted mono small numeric">${fmtMs(r.duration_ms)}</span>
    ${chip(r.status)}
    ${r.id ? `<a href="#/result/${esc(r.id)}"><button class="secondary small">Details</button></a>
              <a href="/api/results/${esc(r.id)}/export.md" download
                 title="Detailed report for this case"><button class="ghost small">.md</button></a>` : ""}`;

  function upsertRow(r) {
    let el = rowEls.get(r.test_id);
    if (!el) {
      el = document.createElement("div");
      el.className = "runrow";
      rowEls.set(r.test_id, el);
      resultsEl.appendChild(el);
    }
    el.dataset.status = r.status || "QUEUED";
    el.innerHTML = rowHTML(r);
  }
  results.forEach(r => upsertRow(r));

  document.getElementById("ressearch").oninput = e => {
    const q = e.target.value.trim().toLowerCase();
    rowEls.forEach(el => {
      el.dataset.hiddenBySearch = (!q || el.textContent.toLowerCase().includes(q)) ? "" : "1";
      el.hidden = !!(el.dataset.hiddenBySearch || el.dataset.hiddenByStatus);
    });
  };
  document.querySelectorAll("#resfilter button").forEach(btn => btn.onclick = () => {
    document.querySelectorAll("#resfilter button").forEach(b => b.classList.remove("on"));
    btn.classList.add("on");
    const want = btn.dataset.filter;
    rowEls.forEach(el => {
      el.dataset.hiddenByStatus = (want === "*" || el.dataset.status === want) ? "" : "1";
      el.hidden = !!(el.dataset.hiddenBySearch || el.dataset.hiddenByStatus);
    });
  });

  /* ---- live log: capped ring buffer, appended not rewritten.
     `logLines` is only the count; the DOM holds the text. New lines go in as
     a single appended text node — O(added), not O(total) — and the buffer is
     trimmed in one bulk pass every LOG_TRIM lines rather than per line. */
  const logEl = document.getElementById("livelog");
  const logMeta = document.getElementById("logmeta");
  const pauseBtn = document.getElementById("logpause");
  let logLines = 0, logPaused = false, atBottom = true, droppedLogs = 0;
  let logTrimmed = false;
  const pendingLines = [];

  pauseBtn.onclick = () => {
    logPaused = !logPaused;
    pauseBtn.textContent = logPaused ? "▶ Resume" : "⏸ Pause";
    if (!logPaused) schedule();
  };
  document.getElementById("logclear").onclick = () => {
    logEl.textContent = ""; logLines = 0; logTrimmed = false;
    pendingLines.length = 0; updateLogMeta();
  };
  logEl.addEventListener("scroll", () => {
    atBottom = logEl.scrollHeight - logEl.scrollTop - logEl.clientHeight < 40;
  }, { passive: true });

  function updateLogMeta() {
    // Only claims a trim once one has actually happened: the buffer is
    // trimmed in bulk at LOG_MAX + LOG_TRIM, so between those two counts the
    // log really is still showing everything it has.
    logMeta.textContent = `${logLines} line${logLines === 1 ? "" : "s"}`
      + (logTrimmed ? ` · oldest trimmed, keeping the most recent ${LOG_MAX}` : "")
      + (droppedLogs ? ` · ${droppedLogs} earlier lines not replayed` : "");
  }

  const pushLog = line => { if (!logPaused) pendingLines.push(line); };

  function flushLog() {
    if (logPaused || !pendingLines.length) return;
    // One layout read for the whole frame, before any write.
    const stick = atBottom;
    const text = pendingLines.join("\n") + "\n";
    logEl.appendChild(document.createTextNode(text));
    // Counted by PHYSICAL lines: one server LOG message can carry embedded
    // newlines, and it is physical lines that occupy the DOM. Counting
    // messages instead made the meter drift below the real line count.
    for (let i = 0; i < text.length; i++)
      if (text.charCodeAt(i) === 10) logLines++;
    pendingLines.length = 0;
    if (logLines > LOG_MAX + LOG_TRIM) {
      // Bulk trim: one re-set for hundreds of lines instead of one per line.
      const kept = logEl.textContent.split("\n").slice(-LOG_MAX);
      logEl.textContent = kept.join("\n");
      logLines = kept.length;
      logTrimmed = true;
    }
    if (stick) logEl.scrollTop = logEl.scrollHeight;
    updateLogMeta();
  }

  /* ---- the frame loop: every SSE event lands in a queue and is applied on
     the next animation frame. The browser therefore does at most one paint
     per frame no matter how fast the server streams. */
  const queue = [];
  let scheduled = false;
  const dirty = { counters: false, rows: new Set(), current: null, status: null };

  function schedule() {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(flush);
  }

  function flush() {
    scheduled = false;
    // While the tab is hidden the browser throttles rAF to ~1 Hz anyway;
    // draining the queue without painting keeps memory flat either way.
    const batch = queue.splice(0, queue.length);
    for (const [type, payload] of batch) apply(type, payload);
    if (dirty.status) {
      document.getElementById("runstatus").innerHTML = chip(dirty.status);
      dirty.status = null;
    }
    if (dirty.counters) { renderCounters(); dirty.counters = false; }
    if (dirty.rows.size) {
      dirty.rows.forEach(id => { const r = results.get(id); if (r) upsertRow(r); });
      dirty.rows.clear();
    }
    if (dirty.current !== null) {
      const el = document.getElementById("current");
      if (dirty.current === false) el.hidden = true;
      else { el.hidden = false; el.innerHTML = `<span class="dot"></span>${dirty.current}`; }
      dirty.current = null;
    }
    flushLog();
  }

  const mergeResult = (id, patch) => {
    results.set(id, { ...(results.get(id) || { test_id: id }), ...patch });
    dirty.rows.add(id);
  };

  function apply(type, p) {
    switch (type) {
      case "RUN_STARTED":
        state.total = p.total; dirty.status = "RUNNING"; dirty.counters = true;
        pushLog(`▶ RUN ${runId} started on ${p.env_name} (${p.total} tests)`);
        break;
      case "TEST_STARTED":
        state.running = p.test_id;
        mergeResult(p.test_id, { name: p.name, id: p.result_id, status: "RUNNING" });
        dirty.current = `<b>${esc(p.test_id)}</b> — ${esc(p.name)}
          <span class="muted">(test ${p.index}/${p.total})</span>`;
        dirty.counters = true;
        pushLog(`● ${p.test_id} — ${p.name}`);
        break;
      case "STEP_STARTED":
        dirty.current = `<b>${esc(p.test_id)}</b> <span class="muted">step ${p.index}:</span> ${esc(p.name)}…`;
        pushLog(`  → step ${p.index}: ${p.name}`);
        break;
      case "STEP_PASSED":  pushLog(`  ✓ step ${p.index} (${fmtMs(p.duration_ms)})`); break;
      case "STEP_FAILED":  pushLog(`  ✗ step ${p.index}: ${p.error}`); break;
      case "STEP_SKIPPED": pushLog(`  ⏭ step ${p.index}: ${p.reason}`); break;
      case "ASSERTION":
        pushLog(`  ${p.passed ? "✓" : "✗"} assert ${p.name}: expected ${p.expected}, got ${p.actual}`);
        break;
      case "LOG": pushLog("    " + p.message); break;
      case "LOG_TRUNCATED":
        droppedLogs = p.dropped; updateLogMeta();
        break;
      case "TEST_PASSED":  testDone(p, "PASSED"); break;
      case "TEST_FAILED":  testDone(p, "FAILED"); break;
      case "TEST_SKIPPED": testDone(p, "SKIPPED"); break;
      case "TEST_BLOCKED": testDone(p, "BLOCKED"); break;
      case "TEST_ERROR":   testDone(p, "ERROR"); break;
      case "RUN_COMPLETED": runCompleted(p); break;
    }
  }

  function testDone(p, st) {
    state.running = null;
    state.done = p.done ?? state.done + 1;
    state.passed = p.passed ?? state.passed;
    state.failed = p.failed ?? state.failed;
    state.skipped = p.skipped ?? state.skipped;
    state.errors = p.errors ?? state.errors;
    state.blocked = p.blocked ?? state.blocked;
    mergeResult(p.test_id, {
      id: p.result_id, status: st, duration_ms: p.duration_ms,
      error: p.error, failed_step: p.failed_step, skip_reason: p.skip_reason,
    });
    dirty.counters = true;
    pushLog(`■ ${st} ${p.test_id}${p.error ? " — " + p.error : ""}`);
  }

  function runCompleted(p) {
    dirty.status = p.status;
    dirty.current = false;
    dirty.counters = true;
    cancelBtn.disabled = true;
    pushLog(`✔ RUN_COMPLETED — ${p.passed} passed, ${p.failed} failed, `
      + `${p.skipped} skipped, ${p.errors} errors in ${fmtMs(p.duration_ms)}`);
    toast("Export the detailed report from the Export menu above.",
      { title: `Run finished — ${p.status}`, kind: "ok", ms: 12000 });
    if (groupId) {
      api(`/api/compare/${groupId}`).then(c => {
        if (c.runs.length >= 2 && c.runs.every(r => ["COMPLETED", "CANCELLED"].includes(r.status)))
          location.hash = `#/compare/${groupId}`;
        else {
          const next = c.runs.find(r => r.status !== "COMPLETED");
          if (next && next.id !== runId) location.hash = `#/run/${next.id}?group=${groupId}`;
        }
      }).catch(() => {});
    }
  }

  renderCounters(); updateLogMeta();

  if (liveES) liveES.close();
  liveES = new EventSource(`/api/runs/${runId}/events`);
  const EVENTS = ["RUN_STARTED", "TEST_STARTED", "STEP_STARTED", "STEP_PASSED",
    "STEP_FAILED", "STEP_SKIPPED", "ASSERTION", "LOG", "LOG_TRUNCATED",
    "TEST_PASSED", "TEST_FAILED", "TEST_SKIPPED", "TEST_BLOCKED", "TEST_ERROR",
    "RUN_COMPLETED"];
  EVENTS.forEach(type => liveES.addEventListener(type, e => {
    // Parsed exactly once — the old code parsed every event twice.
    queue.push([type, JSON.parse(e.data).payload]);
    schedule();
  }));
  liveES.addEventListener("STREAM_END", () => { if (liveES) liveES.close(); });
  liveES.onerror = () => {
    // EventSource reconnects on its own; the bootstrap replay makes the
    // reconnect cheap, so this only needs to say so.
    if (liveES && liveES.readyState === EventSource.CONNECTING)
      pushLog("… reconnecting to the event stream");
    schedule();
  };
}

/* -------------------------------------------------------- result detail */
async function viewResult(resultId) {
  const r = await api(`/api/results/${resultId}`);
  const t = r.traceability || {};
  const mark = s => s === "PASSED" ? `<span class="stepmark ok">✓</span>`
    : s === "FAILED" ? `<span class="stepmark ko">✗</span>`
    : s === "SKIPPED" ? `<span class="stepmark muted">⏭</span>`
    : `<span class="stepmark muted">·</span>`;
  const steps = r.steps.map(s => `
    <li>${mark(s.status)}<span class="grow">${esc(s.name)}</span>
      <span class="muted mono small">${fmtMs(s.duration_ms)}</span>
      ${s.error ? `<span class="small" style="color:var(--fail)">${esc(s.error)}</span>` : ""}</li>`).join("");
  const asserts = r.assertions.map(a => `
    <tr><td class="${a.passed ? "ok" : "ko"}">${a.passed ? "✓" : "✗"}</td>
      <td>${esc(a.name)}</td><td class="mono">${esc(a.expected)}</td>
      <td class="mono">${esc(a.actual)}</td></tr>`).join("");
  const shots = r.artifacts.filter(a => a.type === "screenshot");
  const others = r.artifacts.filter(a => a.type !== "screenshot");

  app.innerHTML = `
    <a class="crumb" href="#/run/${esc(r.run_id)}">← Run ${esc(r.run_id)}</a>
    <div class="pagehead"><div class="grow">
      <h1><span class="mono">${esc(r.test_id)}</span> ${chip(r.status)}</h1>
      <div class="sub muted small">${esc(r.name)}</div>
    </div>
    ${exportMenu([
      { head: "This case" },
      { href: `/api/results/${resultId}/export.md`, label: "Detailed report (.md)",
        note: "Steps, assertions, error and artifacts" },
      { hr: true },
      { head: "Whole run" },
      { href: `/api/runs/${r.run_id}/export.xlsx`, label: "Full run detail (.xlsx)" },
      { href: `/api/runs/${r.run_id}/export.md?only=FAILED,ERROR`,
        label: "Run triage report (.md)" },
    ], "Export")}</div>

    <div class="panel"><div class="kv">
      <div><span>Workflow</span>${esc(r.workflow)}</div>
      <div><span>Environment</span>${esc(r.run?.env_name || "")}</div>
      <div><span>Duration</span>${fmtMs(r.duration_ms)}</div>
      <div><span>Kind</span>${esc(r.kind)}</div>
      <div><span>Priority</span>${esc(r.priority || "—")}</div>
      <div><span>Finished</span>${fmtDate(r.finished_at)}</div>
    </div></div>

    ${r.status === "FAILED" || r.status === "ERROR" ? `
      <div class="panel">
        <h2>Failure</h2>
        ${r.failed_step ? `<p>Failed step: <b>${esc(r.failed_step)}</b></p>` : ""}
        ${r.expected || r.actual ? `
        <div class="expected-actual">
          <div class="panel tight" style="margin:0"><span class="muted small">EXPECTED</span>
            <div class="mono">${esc(r.expected)}</div></div>
          <div class="panel tight" style="margin:0"><span class="muted small">ACTUAL</span>
            <div class="mono">${esc(r.actual)}</div></div>
        </div>` : ""}
        <div class="errbox" style="margin-top:12px">${esc(r.error)}</div>
      </div>` : ""}
    ${r.skip_reason ? `<div class="panel"><h2>${r.status === "BLOCKED" ? "Blocked" : "Skipped"}</h2>
      <div class="prebox">${esc(r.skip_reason)}</div></div>` : ""}

    <div class="panel"><h2>Steps</h2>
      <ul class="steps">${steps || "<li class='muted'>No steps recorded</li>"}</ul></div>
    <div class="panel flush"><div class="panelhead"><h2>Assertions</h2></div>
      <div class="tablewrap"><table class="matrix">
        <thead><tr><th></th><th>Assertion</th><th>Expected</th><th>Actual</th></tr></thead>
        <tbody>${asserts || "<tr><td colspan=4 class='empty'>None recorded</td></tr>"}</tbody>
      </table></div></div>
    ${r.artifacts.length ? `<div class="panel"><h2>Artifacts</h2>
      <div class="artifacts">${others.map(a =>
        `<a href="/api/artifacts/${a.id}" target="_blank">📄 ${esc(a.name)}</a>`).join("")}</div>
      ${shots.map(a => `<p class="muted small">${esc(a.name)}</p>
        <img class="shot" src="/api/artifacts/${a.id}" loading="lazy">`).join("")}
    </div>` : ""}
    <div class="panel"><h2>Excel traceability</h2>
      <div class="prebox">
        <div><span class="muted">Workbook test cases:</span>
          <b>${esc((t.tc_ids || []).join(", ") || "—")}</b></div>
        <div><span class="muted">Feature:</span> ${esc(t.feature || "—")}</div>
        <div><span class="muted">User story:</span> ${esc(t.user_story || "—")}</div>
        <div class="small muted" style="margin-top:8px">${esc(t.source || "")}</div>
      </div></div>`;

  bindMenus();
}

/* -------------------------------------------------------------- compare */
async function viewCompare(groupId) {
  const c = await api(`/api/compare/${groupId}`);
  const running = c.runs.some(r => !["COMPLETED", "CANCELLED"].includes(r.status));
  const head = c.envs.map(e => `<th>${esc(e)}</th>`).join("");
  const CLS = { SAME_BEHAVIOR: "var(--pass)", REGRESSION_CANDIDATE: "var(--fail)",
    FIXED: "var(--run)", SAME_FAILURE: "var(--err)", BLOCKED: "var(--block)",
    NOT_COMPARED: "var(--muted)" };
  const rows = c.tests.map(t => {
    const cells = c.envs.map(e => {
      const cell = t.by_env[e];
      return `<td>${cell ? `<a href="#/result/${esc(cell.result_id)}">${chip(cell.status)}</a>`
        : chip("NOT RUN")}</td>`;
    }).join("");
    const cls = t.classification || "";
    return `<tr class="${t.regression ? "regression" : ""}">
      <td><span class="tc-id">${esc(t.test_id)}</span><div>${esc(t.name)}</div></td>
      ${cells}<td class="nowrap"><b style="color:${CLS[cls] || "var(--muted)"}">${esc(cls.replace(/_/g, " "))}</b>
      ${cls === "REGRESSION_CANDIDATE" ? "<div class='small muted'>needs failure triage</div>" : ""}</td></tr>`;
  }).join("");

  app.innerHTML = `
    <a class="crumb" href="#/runs">← Run history</a>
    <div class="pagehead"><div class="grow">
      <h1>Comparison <span class="mono">${esc(groupId)}</span></h1>
      <div class="sub muted small">${c.runs.map(r =>
        `<a href="#/run/${esc(r.id)}?group=${esc(groupId)}">${esc(r.env_name)}</a> ${chip(r.status)}`
      ).join(" · ")}</div>
    </div></div>
    <div class="stats">
      <div class="stat fail"><b>${c.regressions.length}</b><span>regressions</span></div>
      <div class="stat brand"><b>${c.tests.length}</b><span>tests compared</span></div>
    </div>
    ${running ? `<div class="panel tight muted small">Still running — this page refreshes automatically.</div>` : ""}
    <div class="panel flush"><div class="tablewrap"><table class="matrix">
      <thead><tr><th>Test</th>${head}<th>Classification</th></tr></thead>
      <tbody>${rows}</tbody></table></div></div>`;

  if (running) setTimeout(() => {
    if (location.hash.includes(groupId)) viewCompare(groupId);
  }, 2500);
}

/* ---------------------------------------------------------- run history */
async function viewRuns() {
  const { runs } = await api("/api/runs");
  app.innerHTML = `
    <div class="pagehead"><div class="grow">
      <h1>Run history</h1>
      <div class="sub muted small">${runs.length} most recent executions</div>
    </div></div>
    <div class="toolbar">
      <div class="field search"><span>Filter</span>
        <input type="search" id="rsearch" placeholder="run id, label, environment…"></div>
      <div class="grow"></div>
      <span class="muted small" id="rcount">${runs.length}</span>
    </div>
    <div class="panel flush">${runs.map(r => `
      <div class="runrow">
        <div class="grow">
          <span class="mono">${esc(r.id)}</span>
          <div class="small muted">${esc(r.label || "")}</div>
        </div>
        <span class="small nowrap">${esc(r.env_name)}</span>
        <span class="muted small nowrap">${fmtDate(r.started_at)}</span>
        <span class="mono small nowrap">
          <span style="color:var(--pass)">✓${r.passed}</span>
          <span style="color:var(--fail)">✗${r.failed}</span>
          <span style="color:var(--err)">!${r.errors}</span></span>
        ${chip(r.status)}
        <span class="nowrap">
          ${r.group_id ? `<a href="#/compare/${esc(r.group_id)}"><button class="ghost small">Compare</button></a>` : ""}
          <a href="/api/runs/${esc(r.id)}/export.xlsx" download
             title="Full detail workbook"><button class="ghost small">.xlsx</button></a>
          <a href="#/run/${esc(r.id)}${r.group_id ? `?group=${esc(r.group_id)}` : ""}"><button class="secondary small">Open</button></a>
        </span>
      </div>`).join("") || "<div class='empty'>No runs yet.</div>"}</div>`;
  bindFilter("rsearch", ".runrow", "rcount");
}

/* --------------------------------------------------------------- router */
async function route() {
  if (liveES) { liveES.close(); liveES = null; }
  const [path, query] = location.hash.slice(2).split("?");
  const q = new URLSearchParams(query || "");
  const parts = (path || "").split("/").filter(Boolean);
  document.querySelectorAll("#nav a").forEach(a =>
    a.classList.toggle("active", a.dataset.nav === (parts[0] || "")));
  app.innerHTML = `<div class="loading">Loading</div>`;
  try {
    if (!parts.length) await viewFeatures();
    else if (parts[0] === "tests") await viewDashboard();
    else if (parts[0] === "feature") await viewFeature(parts[1]);
    else if (parts[0] === "testcase") await viewTestCase(parts[1]);
    else if (parts[0] === "run") await viewRun(parts[1], q.get("group"));
    else if (parts[0] === "result") await viewResult(parts[1]);
    else if (parts[0] === "compare") await viewCompare(parts[1]);
    else if (parts[0] === "runs") await viewRuns();
    else await viewFeatures();
  } catch (err) {
    app.innerHTML = `<div class="panel"><div class="errbox">${esc(err.message)}</div></div>`;
  }
}
window.addEventListener("hashchange", route);
route();
