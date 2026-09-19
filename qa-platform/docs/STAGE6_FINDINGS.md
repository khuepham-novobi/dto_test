# Stage 6 — first real run on the 09-18 UAT restore

Database: `d1v19`, restored from
`d1systems-uat-38267540_2026-09-18_130212_exact_fs.zip` (0 restore errors,
231 modules, 50,101 filestore files, 128,041 attachments).
Source: `dto_custom` @ `7fb1d4a` (branch UAT).
Run: `RUN-C181BB7B`, 45 registered tests across the five Stage 6 workflows.

| Workflow | PASSED | FAILED | BLOCKED | ERROR |
|---|---|---|---|---|
| WF-001 Requisition import | 3 | 2 | 0 | 2 |
| WF-010 MO test-result import | 1 | 4 | 1 | 1 |
| WF-017 Journal entry export | 5 | 3 | 3 | 2 |
| WF-018 Vendor bill export | 1 | 3 | 4 | 2 |
| WF-019 Vendor payment import | 0 | 8 | 0 | 0 |
| **Total** | **10** | **20** | **8** | **7** |

Stage 6 was already deployed in this backup — all four modules installed at
19.0.0.1, the D-S6b back-fill applied (187,217 exported, 275 left, matching
what `ci/backfill_workday_export_state.sh` documents as correct), the D-S6a
sandbox swap done (six `Test-UAT/*` folders active, six `Production/*`
inactive) and all five Workday/SFTP crons inactive. No cleanup was run; it
would have re-upgraded modules already at the right version for nothing.

---

## 1. Harness defects found and fixed

These three produced most of the first run's noise. None is a product
finding; all three are fixed in this commit.

### 1.1 The attachment fixture used a route that writes nothing on v19

19 cases across WF-017/018/019 failed to post their fixture bills with
`User cannot confirm the bill. The Vendor Bill requires an attachment
before posting.`

Measured on `d1v19`:

| Route | result |
|---|---|
| `move.write({'attachment_ids': [(0, 0, …)]})` | `attachment_ids == []`, `have_attachment == False`, and the row cannot be found by name at all |
| `ir.attachment.create({…, res_model, res_id})` | `attachment_ids == [id]`, `have_attachment == True` |

Cause is core's own definition (v19
`addons/account/models/account_move.py:334`): `attachment_ids` is a
One2many whose inverse is `res_id`, with `res_model` only a domain term —
so the ORM never fills it and the new row falls outside the very domain it
was created through.

The suites' shared docstring asserted the opposite ("fixtures that need to
POST a bill therefore attach via `attachment_ids` on the move"), so this was
a documented assumption that v19 inverted. Fixed by
`framework.qa_fixtures.ensure_postable_bill`, which attaches the working way
and then **proves** `have_attachment` before anything depends on it.
`attach_to_move` keeps both named routes, because exercising both is what
TC319 is for.

### 1.2 `registry.reload()` broke exception identity

Introduced on 2026-09-05 when the reload was widened to drop `framework.*`
and `adapters.*` so helper edits would be picked up. Re-importing a module
builds **new class objects**, so `except SomeError` in freshly imported test
code stops matching the `SomeError` raised by anything imported at server
start. Measured — every one of these stopped matching after a reload:

| Class | raised by | caught by | effect |
|---|---|---|---|
| `adapters.base.OdooRPCError` | the adapter the runner built at start | every suite's sweep | guarded teardown began erroring mid-sweep |
| `framework.context.BlockedTest` | `ctx.blocked()` | `backend.runner` | every deliberate BLOCK recorded as ERROR |
| `framework.context.AssertionFailed` | assertions | `backend.runner` | every assertion failure recorded as ERROR |
| `framework.context.SkipTest` | `ctx.skip()` | `backend.runner` | skips recorded as ERROR |

Visible in the run history: ERROR 24 → 29 while FAILED fell 13 → 8, which
looked like the environment degrading and was only misclassification.

The rule is now written into `framework/registry.py`: **a module may be
dropped only if no long-lived object holds a class from it.**
`framework.context` and `adapters.*` are never dropped; the pure-helper
`framework.*` modules still are, so the endpoint keeps its purpose.

### 1.3 The restore put the filestore one level too deep

Not in this repo — in the restore procedure. `mv /tmp/filestore
/var/lib/odoo/filestore/d1v19` ran after Odoo had already recreated the
target directory, so `mv` moved the source *inside* it:

```
d1v19/filestore/f4/f448…    49,913 files, one level too deep
d1v19/f4/…                  105 files
```

Odoo could not read `data.template.export`'s three shipped workbooks, so
`execute_export()` produced no attachment and every Workday export returned
`There is nothing to export!` — six cases reporting `expected 'info', got
'danger'` plus four BLOCKED on "the export produced no sftp.file".

Worth recording because the obvious check passed: `du -sh` reported 1002 MB
and the file count 49,935, both correct, because they counted the nested
tree. **A size or count check cannot distinguish "in place" from "one level
too deep"** — verify a specific known path instead. After repair, WF-017
went from 2 to 5 PASSED and the whole `danger` cluster disappeared.

---

## 2. Product findings

### 2.1 WF-019 reconciliation is broken on v19 — `account.payment` has no `line_ids`

**`dto_account_workday/models/account_payment.py:56,58`**

```python
payment_lines = payment_moves.mapped('line_ids').filtered(lambda r: r.credit > 0)
```

`payment_moves` is an `account.payment` recordset (passed at `:248`). In
v17 `account.payment` carried `_inherits = {'account.move': 'move_id'}`, so
`line_ids` resolved through the move. **v19 removed that inheritance** —
confirmed on the target: `account.payment.fields_get()` has `move_id` and
**no** `line_ids`.

The result is `KeyError: 'line_ids'`, recorded verbatim on the failing
`sftp.file`'s activity note. It is caught and turned into a per-row failure,
so the import reports `failed` rather than raising — which is why this
survived to UAT.

Effect: the payment is created but never reconciled against its bill. Four
cases fail on `expected 'done', got 'failed'` (TC299, TC324, TC328, TC329)
and TC325 on `residual: expected 400.0, got 500.0` — the bill stays
unreconciled.

Likely fix is `payment_moves.move_id.line_ids`, but that is the module
owner's call, not this suite's; nothing here changes product code.

### 2.2 The configured bank journal has no `ach` payment method

`res_company.workday_vendor_payment_journal_id` is journal 6 (`MT`), whose
outbound methods are `batch_payment, check_printing, manual, nacha`.
Workday's file names `ach`, and `_get_workday_payment_method_line_id`
therefore reports

> Cannot find payment method ach of Bank journal in Odoo

Whether v17 carried an `ach` method line and the rebuild dropped it, or
Workday's vocabulary changed, is a data question for the client — it is
recorded here rather than worked around, because making the fixture send
`nacha` would hide it.

### 2.3 Already-pinned defects that reproduced

* **TC347** — the no-match message opens a `<ul>` and never closes it
  (`mrp_attachment_transformer.py:64-69`). The case exists to record it.
* **TC292** — `ir.logging`/wizard result carries no `traceback` field; same
  class as the known `TEST-WF020-TC301` defect.
* **TC342** — `Invalid field 'groups_id' on 'ir.ui.menu'`; v19 renamed it.
* **TC346** — `You cannot set more than 1 lot`; v19 turned
  `lot_producing_id` into the M2m `lot_producing_ids` (B-1 in the WF-010
  suite header).

---

## 3. Blocked, with the reason

8 BLOCKED, none of them masking a failure:

* **4 need a v17 baseline** (TC035, TC036, TC322, TC349) —
  DATA_RECONCILIATION cases compare against a capture that does not exist
  yet. Run the suites against Odoo 17 once to create it.
* **4 need a reachable SFTP endpoint** (TC291, TC296, TC304, TC311) —
  `SFTPConnection` opens a paramiko session, and prereq **E6** (the pinned
  host key) is still open. Nothing in Stage 6 has ever done a real SFTP
  round trip on this project; all five workflows remain CONDITIONALLY DONE
  on the transport axis.

---

## 4. Still open in the harness

* **TC319** still errors on the attachment gate. It deliberately posts a
  bill through the `via='move'` route, which is the route finding 1.1 shows
  writes nothing. The case needs rewriting around what v19 actually does —
  its subject (the two routes disagree) is still valid, but its fixture
  cannot rely on the broken route to reach a posted bill.
* **TC312 / TC313** error on `Journal codes must be unique per company` —
  the fixture picks a journal code already present on this database.
* **TC300** errors on `sftp.file.mark_sync_failed: 'str' object has no
  attribute 'date'` — worth confirming whether that is the harness passing a
  string or a product defect.
* **TC316** now fails on row ORDER (`expected [192548, 192550, 192551], got
  [192551, 192548, 192550]`) rather than on content — the export works; what
  the workbook requires is selection order.
