# Handoff — DataOne v17→v19 QA, remaining work

Written for a Claude Code session on the **Windows host** that runs the QA platform.
Everything below was established from a Linux workstation that could reach the platform's
HTTP API but **not** its deployment.

---

## 1. Where things are

| Thing | Location | State |
|---|---|---|
| Odoo custom addons | `git@github.com:novobi1/DTO-Odoo.git` | branch `UAT` = `53195c6`, all work merged & pushed |
| QA platform | the checkout on this Windows host (docker, `- .:/app`) | **not a git repo** |
| QA platform URL | `https://testd1.odoovietnam.net` | API is open, no auth needed for GET/POST |
| Odoo 17 target | `http://odoo17:8069`, db `dto_17` | scratch DB — see §5 |
| Odoo 19 target | `http://odoo19:8069`, db `d1v19` | production upgrade |

`config/local.yaml` mounts the addon trees read-only:
`D:/project/dto/dto_17/odoo-17.0/dto_17_custom` → `/src/dto17`,
`D:/project/dto/dto_19/odoo-19.0/dto_custom` → `/src/dto19`.

---

## 2. FIRST TASK — deploy the harness fixes

**The changes are NOT in any git repo.** They are in `qa-harness-fixes.tar.gz`, handed over
separately. 16 files.

```bash
tar xzf qa-harness-fixes.tar.gz -C <qa-platform root>
```

Then add two lines to `config/local.yaml` by hand (it is gitignored and holds SMTP/PG
secrets, so it was deliberately excluded from the archive):

```yaml
DTO_SOURCE_ROOT_17: /src/dto17
DTO_SOURCE_ROOT_19: /src/dto19
```

Restart the container — `.:/app` is a live mount, no rebuild needed.

### What the 16 files change

| File | Change | Cases |
|---|---|---:|
| `adapters/base.py` | `_fault()` keeps the whole RPC fault. Was `str(msg).splitlines()[-1]`, which threw away the exception on every safe_eval failure. | diagnostics |
| `framework/qa_fixtures.py`, `tests/wf013/test_move_security.py` | `user_groups_field(rpc)` probes `group_ids` (v19) vs `groups_id` (v17) | 3 |
| `tests/wf002/common.py`, `tests/wf002/test_confirmation_email.py` | `analytic_for_order_type()` — orders need a LINE-level distribution or the gate raises "Project is required" | 3 |
| `tests/wf003/common.py` | `gate_distribution()` — same, WF-003 set it on the ORDER instead | 1 |
| `tests/wf002/common.py` | `ensure_product(invoice_policy="order")`, pinned not inherited | 2 |
| `tests/wf020/common.py`, `tests/wf020/test_sftp_transport.py` | `ensure_technical_features()` — `sftp.log.traceback` is `groups='base.group_no_one'`; TC302 now accepts either regex outcome | 2 |
| `tests/wf002/test_config_reconciliation.py` | `compile(code.strip(), …)`, matching `ir_actions.py:1016` | 1 |
| `tests/wf003/test_revision_constraint.py` | accept `'u'` (v17 `_sql_constraints`) or `'i'` (v19 `models.UniqueIndex`) | 1 |
| `tests/wf020/common.py` | dropped `deactivate` from `V19_CRON_FIELDS` — not an `ir.cron` field on v19 | 2 |
| `framework/source_scan.py` + 4 call sites | `resolve_source_root(version)` reads `DTO_SOURCE_ROOT_<version>` | 2 |
| `tests/wf013/common.py` | `realtime_category()` now also requires the valuation account — see §4 | (turns 6 FAILED into precise BLOCKED) |

Every file compiles; `resolve_source_root` and `_fault` were unit-checked.

---

## 3. SECOND TASK — re-run v19

```
POST https://testd1.odoovietnam.net/api/runs
{"environment": "odoo19", "label": "after harness fixes — Odoo 19"}
```

Then `GET /api/runs/<id>` and compare against **RUN-D6E5B334** (45 / 37 / 11 / 6 / 1).
`RUN-064AADC8` reproduced it exactly, so v19 is stable — any delta is your change.

Expect **45 → ~61**.

---

## 4. The big open finding — no anglo-saxon COGS lines on v19 (7 × P0)

TC222, TC223, TC224, TC227, TC228, TC232 (+ TC230, separate).

The account core reads for the COGS debit leg **changed between versions**:

| | v17 | v19 |
|---|---|---|
| Generator | `stock_account/models/account_move.py:127` | `:111` |
| Key | `accounts['stock_output']` | `accounts['stock_valuation']` |
| Category field | `property_stock_account_output_categ_id` | `property_stock_valuation_account_id` |
| Fallback | none | `company.account_stock_valuation_id` |

```python
stock_account = accounts['stock_valuation']
if not stock_account or not credit_expense_account:
    continue          # v19 account_move.py:115-118
```

A category migrated from v17 has the **output** account set and the **valuation** account
empty → v19 silently emits no COGS pair on **every invoice**. One missing account, six P0
cases.

`dto_account_cogs` is **not** at fault — its override is correctly re-targeted to the v19
name `_stock_account_prepare_realtime_out_lines_vals`, and its own docstring already flags
this as **open decision D-32** (Controller): *"what D-32 decides is whether the pair posts
real money."*

**Do not migrate this automatically.** Which account the pair should post to is D-32's
call. Fix is data: set `property_stock_valuation_account_id` on the real-time categories,
or `company.account_stock_valuation_id`.

**TC230 is a separate, real code defect:** `is_cogs lines per move: expected 2, got 4` —
the E5 cross-contamination reproduces on v19. Needs a fix in `dto_account_cogs`.

---

## 5. Why the 16 baseline cases cannot pass yet

The Odoo 17 run already happened — **RUN-335A3773**, 49 P / 15 F / 8 E / 27 B. All 15
baselines captured successfully. Re-running it changes nothing, because:

| Metric | v17 `dto_17` | v19 `d1v19` |
|---|---:|---:|
| journal items | 80 | 546,609 |
| lines with analytic distribution | 0 | 446,815 |
| internal quant products | 37 | 969 |
| internal quant quantity | 1,798 | 19,148,157 |

`dto_17` is a scratch database, not a production clone. Every baseline comparison between
the two is meaningless by construction. `dto_17` also has **no real-time product category
at all**, which blocks 20 WF-013 cases there.

**Needed:** restore a production v17 clone into `dto_17`, give both DBs a real-time
category with the valuation account set, re-run both sides.

---

## 6. Cross-version result (v17 RUN-335A3773 vs v19 RUN-D6E5B334)

| Classification | Count |
|---|---:|
| SAME_BEHAVIOR | 28 |
| **SAME_FAILURE — not upgrade risk** | **17** |
| REGRESSION_CANDIDATE | 21 |
| FIXED by v19 | 5 |
| Inconclusive (BLOCKED one side) | 29 |

**Only 1 of the 21 regression candidates is real:** **TC273** — `hr.group_hr_manager` holds
`perm_unlink` on `account.move` on v19, not on v17. No CSV in core, enterprise or
`dataone_19_custom` grants it, so it is a **DB-only ACL row**. A CSV cannot override an ACL
with no XML ID; needs a data fix.

Of the other 20: 15 are baseline artifacts (capture on v17 cannot fail, so the v17 "PASS"
is vacuous), 5 are the harness fixes above.

**These 5 fail identically on v17 — the workbook expectations are simply wrong, v19 is not
doing anything new:** TC085 and TC331/TC333 (`expected False, got ''`), TC072
(`delivery_status 'late'`), TC335 (`wrong-code state_id`). Checked: `convert_to_record` maps
`None → False` identically in 17.0 and 19.0, so this is not a v19 change.

---

## 7. Path to green

| Step | Owner | +Cases | Total |
|---|---|---:|---:|
| — | | | 45 |
| Deploy the 16 harness files (§2) | you | +16 | 61 |
| Resolve D-32, set the valuation account (§4) | Controller | +6 | 67 |
| Restore a production v17 clone into `dto_17` (§5) | env | +16 | 83 |
| Install `dto_account_workday` / `dto_purchase_workday`, activate crons, fix `ODOO19_SOURCE_ROOT` | env | ~+6 | ~89 |
| Fix TC230 (E5 contamination) | dev | +1 | ~90 |
| Recalibrate TC085/331/333/095/338 against the v17 result (§6) | QA | +5 | ~95 |
| TC072, TC089, TC273, TC335 — one decision each | mixed | +4 | ~99 |

**100/100 is not reachable as the suite stands.** TC294 and TC295 require the platform to
open an outbound SFTP connection, which convention rule 4 forbids by design — they need a
stub endpoint or a documented permanent BLOCKED.

---

## 8. Gotchas — things already tried and rejected

1. **Do not bulk-bump `17.0.x` manifest versions to `19.0.x`.** It looks like an obvious
   fix (Odoo 19 marks those modules `installable=False`) but that flag is the **mechanism**
   `tools/uninstall_non_migrated.py` relies on to keep un-ported code out of the UAT
   restore — see its comment at lines 59-62. Bumping makes Odoo actually try to upgrade v17
   code on v19. This was attempted and reverted.

2. **`dto_sale_stock` stays at `17.0.0.1` on purpose.** Its
   `migrations/19.0.0.2/post-migrate.py` is pre-staged and arms only when that module's
   wave bumps the manifest to `>= 19.0.0.2`. Noted in the manifest.

3. **A previously-claimed root cause was wrong.** The 21 `button_validate` errors in
   RUN-7197CCBB were attributed to `if 'IRM' in order.memo_to_suppliers:` raising
   `TypeError`. That is false — the WF-013 fixtures set a non-empty memo
   (`tests/wf013/common.py:309`). Those cases cleared through an environment change with
   the guard undeployed. **Their real trigger is still unidentified.** The guard itself is
   a valid latent-defect fix and is merged; do not re-derive the wrong story from it.

4. **Do not amend/force-push a commit that is already merged.** Doing so to `77e6172`
   produced an add/add conflict when `wf020/integration` was merged into `UAT` (resolved in
   `53195c6`). Check `git branch -r --contains <sha>` first.

5. **The reports in `test_reports/*.zip` are stale.** `scripts/gen_reports.py` wrote
   `NOT_RUN` for all 100 cases of a run that had actually recorded 26 passed. Read the API,
   not the zip. That generator bug is still unfixed.

---

## 9. Reference

- Full triage with per-case detail: `test_reports/TRIAGE_RUN-7197CCBB.md`
  (note: its §3 is marked SUPERSEDED — see gotcha 3)
- Runs referenced: `RUN-7197CCBB` (v19 baseline), `RUN-D6E5B334` / `RUN-064AADC8` (v19
  current, identical), `RUN-335A3773` (v17)
- API: `GET /api/runs`, `GET /api/runs/{id}`, `GET /api/results/{id}`,
  `GET /api/artifacts/{id}`, `POST /api/runs`, `GET /openapi.json`
