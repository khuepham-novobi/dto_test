# DATAONE-WF-020 — Supplier Master Import from Workday · Automation Plan

| | |
|---|---|
| Workflow | `DATAONE-WF-020` — Supplier Master Import from Workday |
| Build order | 2 (Stage 1 — easiest entry points) · estimate 7 h |
| Effective risk | **HIGH** |
| Owns | 18 workbook test cases |
| Suite | `tests/wf020/` |
| Modules | `novobi_sftp_connection`, `dto_account_workday`, `novobi_base_export`, `queue_job` |
| Source | `DataOne_v19_Test_Suite_and_Workflows_v1.0.xlsx` / `Automation Export` |

## Result

| | Count |
|---|---:|
| Implemented | **13** |
| Blocked stub | **5** |
| Not implemented | 0 |
| **Total** | **18** |

## The finding that unlocked this suite

The supplier import **does not read from SFTP at processing time.** The
extractor reads the sftp.file's *attachment*:

```
WorkdaySupplierExtractor._run_extractor_workday_supplier
    attachment = sftp_file.attachment_id
    env['base_import.import'].create({'file': attachment.raw, ...})
```

SFTP is involved only in *fetching* the file onto that attachment. So the
whole extract → transform → load pipeline is drivable with **no network**:
build an inactive `sftp.server`, a `workday_supplier` folder, an
`ir.attachment` holding the CSV, an `sftp.file` pointing at it, then call the
**public** `sftp.file.action_process_sftp_files()`.

That is why the six supplier-ETL cases (TC331–TC336) are implemented against
the real code rather than reduced to stubs — including the gate case. The
helper is `common.run_supplier_import`.

Convention rule 4 still holds throughout: the fixture server is created
`active=False` with an unroutable `.invalid` host, and nothing in the suite
calls `get_sftp_connection`, `action_test_connection` or any `cron_*`.

## Per test case

| Workbook TC | Prio | Platform test | Decision | Key assertions | EXPECTED v17 |
|---|---|---|---|---|---|
| `TC008` | P1 | `TEST-WF020-TC008` | implemented | Cron inventory keyed by XML id (active, interval, priority) captured as the v17 baseline, diffed on v19; every cron active | PASS |
| `TC012` | P0 | `TEST-WF020-TC012` | implemented | DataOne vs Odoo pin comparison; the **openpyxl conflict**; every imported package pinned; `external_dependencies` declared per module | **FAIL at the openpyxl pin** |
| `TC293` | P0 | `TEST-WF020-TC293` | blocked stub | GET poller active at 5 min; the sftp.file shape a pull produces (`ref`, computed `name`, `pending`, attachment, inherited action) | BLOCKED |
| `TC294` | P1 | `TEST-WF020-TC294` | blocked stub | `archive_auto` default True; `archive_path` at folder and server level | BLOCKED |
| `TC295` | P2 | `TEST-WF020-TC295` | blocked stub | The no-archive-path precondition and the `<path>_archived` value it would derive | BLOCKED |
| `TC297` | P2 | `TEST-WF020-TC297` | implemented | Exact uniqueness message; usage key frees the tuple; an **archived** folder still blocks; another server unaffected; un-archive is silent | PASS |
| `TC298` | P2 | `TEST-WF020-TC298` | implemented | The three buttons' `(state, action)` modifiers from the arch; exact `Only pending file(s) can be processed!`; nothing partially processed; a lone pending file reaches Done | PASS |
| `TC301` | P2 | `TEST-WF020-TC301` | implemented | Default `warning+error+unresolved` context; record shape; `level`/`state` readonly; both bulk actions bound to the **list** view; `info` auto-resolved; `traceback` developer-only | PASS |
| `TC302` | P0 | `TEST-WF020-TC302` | implemented | **LIVE DEFECT** — see below | PASS |
| `TC305` | P0 | `TEST-WF020-TC305` | blocked stub | Which v19 cron failure fields exist here; poller active at 5 min | BLOCKED |
| `TC331` | P0 | `TEST-WF020-TC331` | implemented | **GATE** — 5 rows through the real ETL; two creates with `supplier_rank 1`, term and derived country; in-place update with `street2` blanked; term cleared by a blank; failed row byte-identical; **zero activity and zero chatter on any partner** | PASS |
| `TC332` | P1 | `TEST-WF020-TC332` | implemented | One partner per ref; `supplier_rank 1`, `customer_rank 0`, no hierarchy; `name_search` + a real PO; re-run creates no duplicate and leaves rank at 1 | PASS |
| `TC333` | P0 | `TEST-WF020-TC333` | implemented | Same id; blanks overwrite (explicit); every unmapped field, child contact and bank account untouched; no chatter/activity; idempotent; empty name fails only its row | PASS |
| `TC334` | P0 | `TEST-WF020-TC334` | implemented | Blank clears; unknown term raises the exact message and leaves its partner unchanged; lower case and **internal NBSP** fail, trailing space resolves; repair by re-processing | PASS |
| `TC335` | P1 | `TEST-WF020-TC335` | implemented | Canonical resolves + **derives** country; name-only falls back; wrong code still resolves; blank clears both; unknown fails its row; `Texas(US)` fails; two-word splits | PASS |
| `TC336` | P1 | `TEST-WF020-TC336` | implemented | Failed file, good rows kept; exactly one superuser warning activity typed by xmlid; no partner trace; repair + idempotent re-run; Done; exact re-process refusal | PASS |
| `TC459` | P0 | `TEST-WF020-TC459` | implemented | Inventory: XML id, active, interval, non-empty action body; shared-cron blast radius. Run-Manually half BLOCKED | PASS → BLOCKED |
| `TC460` | P0 | `TEST-WF020-TC460` | blocked stub | The v19 `failure_count`/`first_failure_date`/`deactivate` delta; subject cron clean; blast radius | PASS → BLOCKED |

## TC302 — the live defect, reproduced without an endpoint

`novobi_sftp_connection/models/sftp_folder.py:76`:

```python
regex = self.regex and re.match(self.regex) or None
files = connection.get_files(folder=self, regex=regex)
```

`re.match` takes `(pattern, string)`. Called with one argument it raises
`TypeError` — **on the line above the first connection call**. Since
`action_get_files` is public, the defect reproduces over RPC by passing a
dummy connection:

- folder **with** a regex → dies on `re.match`'s arity;
- folder with an **empty** regex → gets one line further and dies on the
  dummy connection instead.

That difference is the proof, and it needs no SFTP at all. The test also
asserts that the field accepts a syntactically invalid pattern with no
validation and no help text, that nothing is written to `sftp.log`, that
`last_sync_state` stays unset, and that no `sftp.file` is created — the
workbook's full blast-radius claim.

## Adaptations (documented, not assertion-weakening)

1. **Token-scoped fixture values.** The workbook's `V-GAMMA-001 … 013` refs and the `30 Days` payment term belong to a seeded dataset; on a live clone those refs may be real vendors and `30 Days` may be ambiguous (the helper's `search` has no `limit`). Refs become `WF020-<token>-NNN` and the term is token-scoped. Every *rule* asserted is the workbook's.
2. **Marker-scoped counting.** "Exactly N partners created" is measured with `search_count` over `ref like 'WF020-%'`, never a full-table search — a production clone holds tens of thousands of partners.
3. **`usage='none'` for the button tests.** TC298 uses a folder whose `_process_sftp_file` returns `(True, '')` immediately, so even the "process a pending file" step runs no ETL and touches no business data.
4. **The PO dropdown replaced by `name_search` + a real PO** (TC332 steps 8–11) — the same call the dropdown makes, followed by a stronger check.
5. **`crons_v19.csv` replaced by the baseline/diff pattern** (TC008, TC459). The expected-delta list does not exist for this project; `reconcile()` derives it from the v17 environment instead, keyed by XML id.
6. **`ir.cron.state`/`code` probed before use** (TC459) — v17's `ir.cron` `_inherits` `ir.actions.server` and the workbook flags that the inherits may not survive v19.

## What this suite does NOT cover

- Anything requiring the Workday SFTP endpoint: the GET pull itself, archive-on-download and its collision suffix, remote directory auto-creation, and repeated real cron failures (TC293, TC294, TC295, TC305, TC459's Run-Manually half, TC460's steps 3–18). Run these against the TD-SF-01 test endpoint from a scratch instance.
- The CI build half of TC012 — virtualenv, `pip install`, `pip check`, package imports, opening the two vendor XLSX templates. These need network and a throwaway environment.
- TC301's induced connection/POST failures (steps 1–4); log records are built directly instead, and every assertion *about* them holds.

## Verified source facts

| Fact | Where |
|---|---|
| The extractor reads `sftp_file.attachment_id`, not SFTP | `dto_account_workday/utils/workday_supplier_sftp_sdk/etl_processor/workday_supplier_extractor.py` |
| Nine CSV columns = the transform's dict keys, straight from the header row | `novobi_sftp_connection/utils/sftp_sdk/etl_processor/sftp_extractor.py:52` |
| `_prepare_workday_contact_vals` builds all seven address keys with no emptiness test → blanks overwrite | `dto_account_workday/models/res_partner.py:19` |
| Blank term returns `{'property_supplier_payment_term_id': False}`, not `{}` | `res_partner.py:32` |
| State parse is `re.search(r'(.+) \((.+)\)')` — one literal space; country derived from the state | `res_partner.py:45` |
| Errors are caught per row in both the transform and the loader | `res_partner.py:78,104` |
| `supplier_rank = 1` set only when no existing contact matched | `res_partner.py:87` |
| `re.match(self.regex)` — one argument | `novobi_sftp_connection/models/sftp_folder.py:76` |
| `_check_unique_folder` runs with `active_test=False` and `having=[('__count','>',1)]` | `sftp_folder.py:55` |
| `Only pending file(s) can be processed!`; `File(s) have been processed already!` | `sftp_file.py:147,159` |
| `mark_sync_failed` schedules a `mail.mail_activity_data_warning` for `SUPERUSER_ID`; `mark_sync_success` posts to chatter | `sftp_file.py:107,122` |
| `sftp.log` auto-resolves `info` on create; `traceback` is `base.group_no_one` | `sftp_log.py:52,29` |
| Both bulk actions bound with `binding_view_types` = `list` | `views/sftp_log_views.xml:101,111` |
| Odoo 19 pins `openpyxl==3.0.9`/`==3.1.2`; DataOne pins `==3.1.5`; Odoo 17 does not pin it | `odoo-19.0/requirements.txt:48-49`, `DTO-Odoo/requirements.txt` |
| v19 `ir.cron` gains `failure_count`, `first_failure_date`, `deactivate` and auto-deactivates | `odoo-19.0/odoo/addons/base/models/ir_cron.py:121,571` |
| All three SFTP crons run at 5-minute intervals | `novobi_sftp_connection/data/*.xml` |

## Run

```bash
venv/Scripts/python.exe -c "from framework import registry; print(len(registry.discover()))"
```
