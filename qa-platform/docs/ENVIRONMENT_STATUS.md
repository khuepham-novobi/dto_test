# Environment Status — Odoo 17 target `dto_17`

Pre-flight run 2026-08-25, **read-only** (`default_transaction_read_only=on`
for SQL; version ping / auth / module listing over RPC). Nothing was
modified.

## Connectivity

| | |
|---|---|
| Odoo | `http://localhost:8076` — server `17.0+e` |
| Database | `dto_17` (PostgreSQL `localhost:5433`, user `wa`) |
| Login | `admin`, uid 2 — verified |
| Company | DataOne Systems, LLC |
| Platform | READY — 100 tests discovered, 510 registry cases, Chromium OK, artifacts writable |
| Odoo 19 | **not present** — connection refused on 8019. v19 runs report BLOCKED by preflight; the v19 **source** at `D:\Projects\odoo-19.0` is what the static-analysis cases read. |

## Data volume

| Table | Rows |
|---|---:|
| `account_move_line` | 550,850 |
| `account_move` | 189,000 |
| `stock_valuation_layer` | 228,906 |
| `sale_order_line` | 64,800 |
| `stock_quant` | 36,147 |
| `product_product` | 22,330 |
| `sale_order` | 13,651 |
| `account_analytic_account` | 4,761 |
| `res_partner` | 4,321 |

This is a **populated working database**, not an empty scratch instance.

## Preconditions — all green

| Requirement | Status |
|---|---|
| 20 key modules installed | ✅ all `installed` |
| `anglo_saxon_accounting` | ✅ **True** |
| Account `12500` `asset_receivable` | ✅ id 208, "Accrued Revenue" |
| The five COGS analytic xmlids | ✅ all resolve (ids 200, 5, 207, 44, 1) |
| Real-time valuation categories | ✅ present (7 via `ir_property`) |
| Revision stack columns | ✅ present |
| dto_sale / dto_account_cogs columns | ✅ all present |
| Confirmation automation | ✅ **active** — so the empty-memo `TypeError` is live |
| Texas/US state | ✅ exactly one (id 52); New York/US id 35 |
| **Active mail servers** | ✅ **none at all** — `require_mail_offline` passes; nothing can be delivered |

## ⚠️ Findings the pre-flight already surfaced

### 1. REAL SECURITY FINDING — an HR Administrator can delete journal entries

`ir_model_access` row **1041**, named `system admins`, on `account.move`:

```
group_id = 61  ->  only xmlid: hr.group_hr_manager  ("Administrator", HR category)
perm_read=1  perm_write=1  perm_create=1  perm_unlink=1   active=True
```

`base.group_system` ("Settings") is a **different** group, id 4. And the ACL
row has **no `ir_model_data` entry of its own** — it was created by hand in
this database, not by any module.

`dto_account/security/ir.model.access.csv` intends Settings to be the only
holder of `perm_unlink` on `account.move`. It is not.

**`TEST-WF013-TC273` will FAIL on this target, and that failure is the
finding** — not an automation defect.

### 2. This target is NOT neutralized — 5 active Workday SFTP folders

| id | path | usage | folder | server |
|---|---|---|---|---|
| 1 | `Production/Draft Vendor Bills` | `workday_vendor_bill` | active | `D1 Send Files` active |
| 2 | `Production/Journal Entries` | `workday_journal_entry` | active | `D1 Send Files` active |
| 4 | `Production/Requisition` | `workday_requisition` | active | `D1 Get Files` active |
| 5 | `Production/Vendor Payments` | `workday_vendor_payment` | active | `D1 Get Files` active |
| 7 | `Production/Suppliers` | `workday_supplier` | active | `D1 Get Files` active |
| 6 | `Test Results` | `mrp_attachment` | active | `D1 Get Files` active |

These point at **production** paths on **active** servers.

Mitigating: **all 7 crons are inactive**, so nothing fires on a schedule,
and no test in these suites calls `action_get_files` / `cron_*` on anything
but its own inactive fixture server. But a human clicking "Sync Now" on this
database talks to the real Workday endpoint.

`TEST-WF003-TC338` and `TEST-WF002-TC350` assert zero active Workday
folders. **They will FAIL here — correctly reporting that the target is not
neutralized.**

### 3. All 7 crons are inactive — a workbook-vs-clone tension

```
dto_account_workday.ir_cron_export_workday_journal_entries   inactive  1 days
dto_account_workday.ir_cron_export_workday_vendor_bills      inactive  1 days
novobi_sftp_connection.ir_cron_get_sftp_files                inactive  3 minutes
novobi_sftp_connection.ir_cron_post_sftp_files               inactive  5 minutes
novobi_sftp_connection.ir_cron_process_sftp_files            inactive  5 minutes
queue_job.ir_cron_autovacuum_queue_jobs                      inactive  1 days
queue_job.ir_cron_queue_job_garbage_collector                inactive  5 minutes
```

`TC008` and `TC459` assert "every cron in the inventory is active". A
neutralized QA clone is *supposed* to have them off (the porting guide's
clone recipe turns them off deliberately). **Both will FAIL here.**

That is a genuine conflict between the workbook's expectation and the QA
clone recipe, and it needs a human decision — the workbook is immutable, so
the test cannot be softened. Note also `ir_cron_get_sftp_files` runs at
**3 minutes**, not the 5 the workbook's `TC293`/`TC305` expect.

`ir_cron.failure_count` is absent, as expected on v17 — `TC460`'s and
`TC305`'s version-delta assertions will pass.

### 4. No payment term named "30 Days"

Not a problem: the WF-020 suite deliberately creates its own token-scoped
term so exact-name matching is unambiguous (documented adaptation).

## Expected failures on a first v17 run — findings, not defects

| Test | Why it fails | Category |
|---|---|---|
| `TEST-WF013-TC273` | `hr.group_hr_manager` holds `perm_unlink` | **real security finding** |
| `TEST-WF003-TC338`, `TEST-WF002-TC350` | 5 active Workday folders | **target not neutralized** |
| `TEST-WF020-TC008`, `TC459` | all crons inactive | **workbook vs clone recipe — needs a decision** |
| `TEST-WF003-TC014` | `@api.returns` still in `base_revision` | documented v19 finding |
| `TEST-WF020-TC012` | `openpyxl==3.1.5` vs Odoo 19's `==3.1.2` | documented pin conflict |
| `TEST-WF002-TC072` | contested workbook expectation | needs adjudication |

Everything else should PASS on v17, or BLOCK for a stated reason.

## Recommendation before running the writing tests

The suites create real records — sale orders, partners, products, invoices,
posted journal entries, stock quants, SFTP servers — and
`TEST-WF013-TC228` temporarily renames account `12500`'s code. On a
database with 189,000 existing moves, that is not something to do casually.

Clone first:

```sql
CREATE DATABASE dto_qa17 TEMPLATE dto_17 STRATEGY FILE_COPY;
```

then, on the clone:

```sql
UPDATE ir_cron        SET active = false;
UPDATE ir_mail_server SET active = false;
UPDATE sftp_server    SET active = false;
UPDATE sftp_folder    SET active = false;
UPDATE fetchmail_server SET active = false;   -- if the table exists
```

and point `ODOO17_DB` at `dto_qa17`. `scripts/start_platform.ps1` already
refuses any database whose name does not contain `_qa`.


---

## First run attempt — `RUN-A101E79D` (26 read-only tests)

Attempted immediately after the pre-flight. **Every one reported
`BLOCKED` / `failure_class = ENVIRONMENT`** — the Odoo server on port 8076
stopped between `validate_env.py` (which authenticated successfully) and the
run. Nothing was listening by then; the platform's preflight caught it
before executing a single test.

```
RUN-A101E79D  COMPLETED  5s
by status:       {'BLOCKED': 26}
failure classes: {'ENVIRONMENT': 26}
passed 0 / failed 0 / blocked 26
```

Two things this does confirm, even though it validated no test logic:

* the harness works end to end — registry -> run creation -> preflight ->
  one result row per test -> classification -> persistence in
  `data/results.db`;
* the **failure-class distinction the porting guide promises is real**.
  Every row is `ENVIRONMENT`, not `AUTOMATION_ERROR`. A glance at the class
  column tells you this was the environment's problem, not the tests'.

Nothing was written to `dto_17`. Re-run once the server is back:

```
venv\Scripts\python.exe scriptsun_readonly_subset.py
```
