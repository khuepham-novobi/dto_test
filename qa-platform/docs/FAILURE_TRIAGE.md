# DataOne — triage of the 48 FAILED / ERROR cases

Source: `FAILURES.md` (`RUN-AE6001B5`, `RUN-AED3A2B6`) — 37 FAILED + 11 ERROR.
Expected results read from `DataOne_v19_Test_Suite_and_Workflows_v1.0.xlsx`,
sheet `Automation Export`.

**The runs were against Odoo 19**, not the v17 baseline. Two independent
proofs: `res.users.create failed: Invalid field 'groups_id'` (renamed
`group_ids` on v19, `base/models/res_users.py:257`) and
`ir.cron.failure_count` / `first_failure_date` being present (added on v19,
`ir_cron.py:121`). That decides how every case is classified below: an
expectation that describes the v19 target state must now PASS, and an
expectation that describes a v17 defect the port deliberately removed must
now FAIL and be booked as FIXED.

## Verdict at a glance

| # | Verdict | Cases | Action |
|---|---|---:|---|
| A | **Do NOT fix — the failure is the finding** | 4 | Note only. Needs a human decision, not a code change. |
| B | **Test-automation defect — FIXED in this pass** | 23 | Code changed under `qa-platform/`. Re-run should go green. |
| C | **Product defect — FIXED in this pass** | 1 | Code changed under `DTO-Odoo/`. Needs approval (see gate below). |
| D | **Database / environment — cannot be fixed in code** | 20 | Note + exact steps to make each pass. |

---

## A. Do NOT fix — designed to fail, or the expectation itself is wrong (4)

| Case | Why it fails | What is needed |
|---|---|---|
| `TEST-WF002-TC072` | Workbook says a 19-days-late line still reads `delivery_status = 'early'`. Source computes `'early' if date_diff >= 0 else 'late'` over a **signed** difference (`dto_sale/models/sale_order_line.py:45`), so `'late'` is correct. The test docstring already flags this as a contested expectation expected to FAIL. | Adjudicate workbook vs source. Either the workbook line is wrong, or `late` really is meant to be dead logic and the compute must change. Not an automation defect. |
| `TEST-WF002-TC085` | The empty-memo `TypeError` was **deliberately remediated**. `dto_sale/migrations/19.0.0.2/post-migrate.py` rewrites the server action to `if 'IRM' in (order.memo_to_suppliers or ''):` on every upgraded database — decision **D-19**, signed, with an expected_deltas row. On v19 the order confirms and one email is sent. | Book as **FIXED**. Do not invert the assertion. (The fixture flaw that made it fail for the *wrong* reason has been corrected — see §B — so the next run reports the real cause.) |
| `TEST-WF020-TC335` | Step 5 expects `Texas (XX)` (wrong country code) to fall back to a name-only search. The code has **no** such fallback after a successful parse — `if/else`, not `if not state` (`dto_purchase_workday/models/res_partner.py:120-146`). This is documented in-source as finding **N-7**: "The spec is wrong about the code, and the code is right about the business." v17 behaved the same way. | Spec correction. Adding the fallback would make a wrong country code silently resolve and derive a country the file never named. Decision required. |
| `TEST-WF003-TC014` | Step 1 (`@api.returns` on `base_revision.copy`) is **already fixed** — commit `334d893` replaced base_revision with the OCA 19.0 port. Re-verified: the scan is now clean for all five modules. | Nothing to do for step 1. **But**: step 2 now finds 7 `groups_id` hits in `base_tier_validation` (`models/tier_validation.py:272` plus 6 in its own tests) — that module has **not** been ported (last touched by DTO-49) and the workbook flags this TC `[HOLD]` pending the Phase-0b scoping decision. Expect the case to fail on step 2 until that decision lands. |

---

## B. Test-automation defects — fixed (23)

Every change is a correction of how the test observes the system. **No
workbook expectation was weakened or inverted** (`AUTOMATION_CONVENTIONS.md`
hard rule 2).

### B1. `create_invoice` raised instead of returning `None` — 2 cases
`TEST-WF002-TC070`, `TEST-WF002-TC094`

Both tests already branch on `if not invoice_id:` ("the invoice half is not
applicable here"), but the helper raised `UserError` instead of returning
`None` when the order has nothing invoiceable.

* **Fixed:** `framework/dto_fixtures.py` — `create_invoice()` now catches
  `sale.order._nothing_to_invoice_error_message` (identical text on v17
  `sale_order.py:1233` and v19 `:1485`) and returns `None`, logging why.

### B2. Fixtures did not satisfy dto_account's analytic gate — 4 cases
`TEST-WF002-TC083`, `TC084`, `TC086`, `TEST-WF003-TC097`

`_validate_analytic_distribution_project` raises `Project is required`
unless every product line carries a Project-plan account
(`dto_account/models/sale_order.py:83`). These four confirm an order but
their subject is the confirmation email / the revision button, so they died
on an unrelated gate.

* **Fixed:** new `gate_analytic(ctx, order_type)` helper in
  `tests/wf002/common.py` and `tests/wf003/common.py`; used by
  `_confirmed_order`, TC086's fixture and TC097's confirmed order. Returns
  `None` when dto_account is absent, so a target without it is unaffected.
  The gate itself is still asserted, unchanged, by TC078–TC082.

### B3. `res.users.groups_id` does not exist on v19 — 3 cases
`TEST-WF013-TC270`, `TC271`, `TC272`

* **Fixed:** new adapter pair `user_groups_field` (`groups_id` on v17,
  `group_ids` on v19), used by `tests/wf013/test_move_security.py::_make_user`.
  Recorded in the conventions version table as the conventions require.

### B4. The anglo-saxon pair could never be selected — 4 cases
`TEST-WF013-TC223`, `TC224`, `TC227`, `TC228`

The selector filtered on `not ln["display_type"]`. `display_type` is
`required=True` on `account.move.line` (v19 `account_move_line.py:329`,
v17 `:291`), so that predicate matches **nothing** — every COGS-basis
assertion reported an empty pair regardless of what was posted. Core stamps
both anglo-saxon lines `display_type='cogs'` on both versions
(v19 `stock_account/models/account_move.py:135,155`; v17 `:150,169`).

* **Fixed:** shared `anglo_saxon_lines(rpc, move_id)` in
  `tests/wf013/common.py`, selecting `display_type == 'cogs' and not is_cogs`
  and excluding income / asset_receivable accounts (dto_account_cogs' own
  reversal lines). `_cogs_pair` and TC228's inline copy now both delegate to it.
* **Also hardened:** `realtime_category()` now prefers a category that has
  BOTH `property_stock_valuation_account_id` and
  `property_account_expense_categ_id` set — core silently `continue`s past
  the line when either is missing (v19 `account_move.py:117`), which would
  produce the same empty pair for a data reason. If no category is fully
  configured it logs a precise warning instead of failing obscurely.

### B5. Chatter body is now an HTML link — 1 case
`TEST-WF003-TC095`

The OCA 19.0 port posts the notice through `_get_html_link()`
(`base_revision.py:151,155`) where 17.0 interpolated the name as plain text,
so the body is `New revision created: <a …>S06508-01</a>` and a raw
substring match fails.

* **Fixed:** new `plain_text()` helper in `tests/wf003/common.py`; the
  assertion matches against the rendered text. The expectation — both
  chatters carry the notice naming the new record — is unchanged.

### B6. `ir.model.constraint.type` is `'i'` for a `UniqueIndex` — 1 case
`TEST-WF003-TC098`

The 19.0 port declares the rule as
`models.UniqueIndex((unrevisioned_name, revision_number, company_id), …)`
(`sale_order_revision/models/sale_order.py:24`), and reflection stamps
`typ = 'i' if isinstance(cons, models.Index) else 'u'`
(`base/models/ir_model.py:2003`). Same three columns, same message, same
enforcement — only the letter changed.

* **Fixed:** step 1 accepts `'u'` or `'i'` and keeps asserting the column
  list, the owning module and the exact DataOne message; steps 2–4 still
  prove the enforcement behaviourally.
* **Alternative if you prefer strict v17 parity:** change the product to
  `models.Constraint("unique(unrevisioned_name, revision_number, company_id)", …)`.
  Not done here — on an upgraded database a `UNIQUE CONSTRAINT` of that name
  may already exist and `Index.apply_to_database` would silently skip
  (`odoo/orm/table_objects.py:161`), so it needs its own migration check.

### B7. `copy` is not a `fields_get` attribute — 1 case
`TEST-WF003-TC338`

There is no `_description_copy` property on either version (v17
`odoo/fields.py:858-871`, v19 `odoo/orm/fields.py:888-901`), so
`fields_get(attributes=["copy"])` returns nothing and the check saw `None`.

* **Fixed:** read `ir.model.fields.copied`, which is reflected straight from
  `bool(field.copy)` (v17 `ir_model.py:1119`, v19 `:1186`).

### B8. Wrong search view fetched — 1 case
`TEST-WF002-TC089`

dto_sale grafts all seven filters onto
`sale.sale_order_view_search_inherit_quotation`, anchored on
`<filter name="sales">` which exists only there
(`dto_sale/views/sale_order_views.xml:53-71`). That view is `mode="primary"`
(v19 `sale_order_views.xml:969`), so Odoo does **not** fold it into the
default `sale.view_sales_order_filter` — and `get_view(view_type="search")`
with no `view_id` resolves the default. The workbook's step 1 opens
Sales → Orders → **Quotations**, whose action sets `search_view_id` to
exactly that primary view.

* **Fixed:** the test resolves the xmlid and fetches that view's arch.

### B9. `traceback` is developer-only — 1 case
`TEST-WF020-TC301`

`sftp.log.traceback` is `groups='base.group_no_one'`
(`novobi_sftp_connection/models/sftp_log.py:26`), and that group is
effective **in debug sessions only** on both versions (v17
`odoo/models.py:1577`, v19 `res_users.py:1081`). An ordinary RPC session
therefore fails the field-level check and the whole `create` is refused.

* **Fixed:** the fixture rows no longer write `traceback`. Step 11 still
  asserts the field IS developer-only, which is the workbook's actual point,
  and no row-shape assertion reads it.

### B10. `deactivate` is on `ir.cron.progress`, not `ir.cron` — 2 cases
`TEST-WF020-TC305`, `TEST-WF020-TC460`

The workbook's `v19_watch` note writes "ir.cron gains deactivate, done,
failure_count, first_failure_date, remaining, timed_out_counter". Only the
middle pair is on `ir.cron` (`ir_cron.py:121-122`); the other four are
fields of `IrCronProgress` (`_name = 'ir.cron.progress'`, `ir_cron.py:918-926`).
Asserting `deactivate` against `ir.cron` fails on a *correct* v19 target —
convention rule 6, verify before asserting.

* **Fixed:** `V19_CRON_FIELDS` split into `V19_CRON_FIELDS` (on `ir.cron`)
  and `V19_CRON_PROGRESS_FIELDS` (on `ir.cron.progress`); both halves of the
  delta are now asserted against the model that carries them. Nothing is
  dropped.

### B11. The regex defect is already remediated — 1 case
`TEST-WF020-TC302`

`novobi_sftp_connection` took the workbook's **required** post-fix option
(a): `action_get_files` compiles the pattern and hands it to
`connection.get_files(folder=…, regex=…)` (`sftp_folder.py:125`), and
`_check_regex` (`:95`) refuses an uncompilable pattern at save time — which
is why the run errored with `… is not a valid regular expression:
unterminated character set`. The test still asserted the pre-fix v17
behaviour.

* **Fixed:** steps 1 and 2–4 re-targeted to the workbook's required outcome
  (a) — the invalid pattern is refused with its compile error and stores no
  folder; a valid pattern no longer dies on `re.match`'s arity and reaches
  the connection exactly as an empty one does. Blast-radius and
  nothing-was-recorded steps unchanged. Docstring now reads
  `EXPECTED v17 OUTCOME: FAIL` / `EXPECTED v19 OUTCOME: PASS`.
* **Judgement call, flag it:** this is the one place a test now asserts the
  post-fix half of a two-part workbook expectation rather than the v17 half.
  Say the word and it can be reverted to a documented expected-FAIL instead.

### B12. A blanked `Char` reads back as `''`, not `False` — 2 cases
`TEST-WF020-TC331`, `TEST-WF020-TC333`

The ETL writes the CSV cell verbatim after `.strip()`
(`dto_purchase_workday/models/res_partner.py:70`), so a blank cell writes
`''` — and `Char` keeps the empty string through `convert_to_cache` on both
versions (v17 `odoo/fields.py:1962`, v19 `odoo/orm/fields_textual.py:107`,
where `falsy_value = ''` is now explicit). The workbook's expectation is
that the field is **blank**, which `''` and `False` both satisfy.

* **Fixed:** the actual is normalised with `or False` — the same comparison
  dto_purchase_workday's own `_changed_fields` uses (`res_partner.py:288`).
  Applied to TC331 step 9-12, TC333 step 6 and TC333 step 12.

### B13. `TEST-WF002-TC085` fixture (case stays in group A)

`make_quotation(memo="")` stored `''`, not `False`, so the assertion failed
for the wrong reason and the case never reached its real subject. Changed to
`memo=None` (omit the field, let the Text default apply). The case still
cannot pass on v19 — see group A — but it now fails at the assertion that
actually records decision D-19.

---

## C. Product defect — fixed (1). **Approval gate.**

### `TEST-WF013-TC230` — E5 cross-contamination in `dto_account_cogs`

`_prepare_reverse_revenue_lines_vals` opened `for move in self:` and then
built its line list from **`self`**, not from **`move`**:

```python
for move in self:
    ...
    revenue_lines = self.invoice_line_ids.filtered(...)   # whole recordset
    receivable_lines = self.line_ids.filtered(...)        # whole recordset
```

Posting two invoices in one `action_post` gave each move a reversal line for
**every** move's revenue and receivable lines — 4 `is_cogs` lines per move
instead of 2, referencing the other invoice's partner and amount. Silent,
because it is self-cancelling in total: each move still balances and its
income and receivable still net to zero.

Workbook `expected_result`, verbatim: *"after the fix, each move carries
exactly its own reversal … is_cogs line count 2"*, with the 4-line shape
listed as the "contaminated (defect) result to watch for". So the workbook
asks for the fix.

* **Changed:** `DTO-Odoo/project-addons/dto_account_cogs/models/account_move.py`
  — `self.invoice_line_ids` → `move.invoice_line_ids`,
  `self.line_ids` → `move.line_ids`, with the reasoning in-place.
* **Not changed:** `_post`'s default-analytic loop. It writes each line's own
  distribution across the whole recordset and is not inside a `for move in self`
  loop, so it does not cross-contaminate.
* **No regression in the module's own tests:** both callers in
  `dto_account_cogs/tests/test_wf013_r01_gate.py` invoke the method on a
  single invoice, where `self is move`.
* ⚠ **This is a behaviour change to posted-accounting code.** Per
  `human-approval-gate`, confirm before it merges. It changes the journal
  items produced by a mass post.

---

## D. Database / environment — cannot be fixed in code (20)

### D1. Reconciliation baselines: 15 cases

`TEST-WF002-TC057`, `TEST-WF013-TC021`, `TC023`, `TC025`, `TC027`, `TC028`,
`TC034`, `TC048`, `TC049`, `TC051`, `TC052`, `TC258`, `TC259`, `TC260`,
`TEST-WF020-TC008`

All use `fg_common.reconcile()`: v17 captures a snapshot into
`data/baselines/<tc>.json`, v19 diffs against it. Every failure is a diff
between two **different databases**, not a code fault.

What the diffs actually say:

* **Different module set.** `printnode_base.*` and `dto_account_workday.*`
  are `current=None` (not installed on the v19 DB); `queue_job.*` is
  `baseline=None` (not installed on the v17 DB when the baseline was taken).
* **Raw database ids compared across databases.** Keys such as
  `server_action/…/model: baseline=644 current=482` and
  `account/189: baseline=None current=…` compare `ir.model` / `account.account`
  **ids**, which are never stable between two databases. TC021's
  `accounts: baseline=8 current=20` is the same thing — a different chart of
  accounts, not a v19 regression.

**To make these pass:**

1. Take the v19 target from an **upgraded copy of the same v17 database**
   that produced the baseline — not a fresh install and not a different
   clone. This is the single change that fixes 14 of the 15.
2. Install the same module set on both sides:
   `dto_account_workday`, `printnode_base`, `queue_job`,
   `location_barcode_labels`, `stock_picking_auto_create_lot`,
   `base_tier_validation`, `dto_cycle_count`, `dto_purchase_stock`.
3. Re-capture the baselines on v17 **after** step 2, then run v19.
4. `config/local.yaml` must carry `ODOO17_PG_*` / `ODOO19_PG_*`, or these
   report BLOCKED instead of running.

> If the two databases genuinely cannot be the same lineage, these cases will
> keep reporting id-shaped diffs forever. The clean alternative is to make the
> captures key on **XML ids and codes** instead of raw ids (`ir.model.model`
> name rather than `model_id`, `account.code` rather than `account/<id>`).
> That is a change to the capture functions, not to any expectation — say the
> word and it can be done as a follow-up.

### D2. Crons deactivated on the QA clone: 3 cases

`TEST-WF020-TC008` (second half), `TEST-WF020-TC459`, `TEST-WF020-TC293`
(and `TC305`'s second half)

Reported inactive: `novobi_sftp_connection.ir_cron_get_sftp_files`,
`…ir_cron_post_sftp_files`, `…ir_cron_process_sftp_files`,
`queue_job.ir_cron_autovacuum_queue_jobs`.

**This is a direct conflict between two rules, and it needs a decision, not a
patch.** `AUTOMATION_CONVENTIONS.md` hard rule 4 requires the QA clone to have
the SFTP connector crons **deactivated**; the workbook's TC293 precondition
requires them **active** at a five-minute interval.

**To make them pass:** run these three cases on a v19 staging instance whose
SFTP servers point at the **TD-SF-01 test endpoint** (never production), with
the crons active. Do not activate them on the shared QA clone.

```sql
-- verification only, on the staging instance:
SELECT d.module || '.' || d.name AS xml_id, c.active,
       c.interval_number, c.interval_type
FROM ir_cron c
JOIN ir_model_data d ON d.model = 'ir.cron' AND d.res_id = c.id
WHERE d.module IN ('novobi_sftp_connection','dto_account_workday','queue_job');
```

### D3. `dto_account_workday` is not installed: 1 case

`TEST-WF002-TC350` — `Workday usage keys missing: ['workday_vendor_bill',
'workday_journal_entry', 'workday_vendor_payment']`. Those three are
contributed by `dto_account_workday/models/sftp_folder.py:12-14`. Only
`workday_supplier` (from `dto_purchase_workday`) was present.

**To make it pass:** install `dto_account_workday` on the target, then
confirm every Workday `sftp.folder` is inactive (the test's next assertion).

### D4. `env.ref()` literals from uninstalled modules: 1 case

`TEST-WF013-TC007`. Every unresolved xmlid was verified to **exist in the
source tree** — they are unresolved because their module is not installed:

| Module | Unresolved |
|---|---|
| `dto_account_workday` | `view_workday_journal_entry_export_wizard_form`, `view_workday_vendor_bill_export_wizard_form` |
| `printnode_base` | `printnode_attach_universal_wizard_form`, `printnode_config_action`, `reaching_limit_notification_email`, + 5 test-only ids |
| `location_barcode_labels` | `barcodelabelslocation`, `default_barcode_configuration_location` |
| `stock_picking_auto_create_lot` | `action_report_return` |
| `base_tier_validation` | `view_comment_wizard` |
| `dto_cycle_count` | `cycle_count_category_level_d` |
| `dto_purchase_stock` | `packing_slip_attachment_tree` |
| `base` (demo data) | `base.user_demo` — 4 hits, all in `queue_job/tests/` |

**To make it pass:** install the modules above (the workbook's own
precondition is a target with all custom modules installed), and load demo
data or accept the four `queue_job/tests/` hits as annotated false positives
— the workbook explicitly allows that: *"A false positive from a dynamically-built
string is acceptable only if it is annotated … with the reason."*

**One genuine code finding inside this list — not fixed, out of scope:**
`uom.product_uom_categ_unit` (`dto_mrp/wizard/product_label_layout.py:22` and
`printnode_base/wizard/product_label_layout.py:43`). Odoo 19 **removed the
`uom.category` model entirely** — `addons/uom/data/uom_data.xml` no longer
defines it and `uom.uom` has no `category_id` (the hierarchy moved to
`relative_uom_id`, `uom_uom.py:41`). `dto_mrp` uses
`raise_if_not_found=False`, so the ref returns `False` and the barcode
grouping silently produces nothing. This belongs to the dto_mrp port
workstream — raise it there.

### D5. An ACL row that exists only in the database: 1 case

`TEST-WF013-TC273` — `hr.group_hr_manager` holds `perm_unlink` on
`account.move` alongside `base.group_system`.

Searched and **not found** in: `DTO-Odoo/**/*.csv` (only `dto_account` grants
anything on `account.move`), `odoo-19.0/addons/*/security/`,
`odoo-19.0/enterprise-19.0/*/security/`. So the row was created directly in
the database (Settings → Technical → Access Rights) or by a module outside
these trees.

**To make it pass:**

```sql
-- 1. identify it
SELECT a.id, a.name, a.perm_read, a.perm_write, a.perm_create, a.perm_unlink,
       d.module || '.' || d.name AS acl_xml_id
FROM ir_model_access a
JOIN ir_model m       ON m.id = a.model_id AND m.model = 'account.move'
JOIN res_groups g     ON g.id = a.group_id
JOIN ir_model_data gd ON gd.model = 'res.groups' AND gd.res_id = g.id
LEFT JOIN ir_model_data d ON d.model = 'ir.model.access' AND d.res_id = a.id
WHERE gd.module = 'hr' AND gd.name = 'group_hr_manager';
```

2. If `acl_xml_id` is **NULL** it is hand-made: delete it in the UI
   (Settings → Technical → Security → Access Rights) — deleting through the
   ORM, not raw SQL, so the registry cache is invalidated.
3. If it **has** an xml_id, that module owns it: decide whether the grant is
   intended and record the decision. `dto_account`'s design is explicit —
   only `base.group_system` may delete a journal entry
   (`dto_account/security/ir.model.access.csv:4`).

---

## Files changed

### `qa-platform/` (test automation)

| File | Change |
|---|---|
| `adapters/base.py` | `user_groups_field` default |
| `adapters/odoo17.py` | `user_groups_field = "groups_id"` |
| `adapters/odoo19.py` | `user_groups_field = "group_ids"` |
| `framework/dto_fixtures.py` | `create_invoice()` returns `None` on nothing-to-invoice |
| `docs/AUTOMATION_CONVENTIONS.md` | three new verified version pairs in the table |
| `tests/wf002/common.py` | `gate_analytic()` |
| `tests/wf002/test_confirmation_email.py` | analytic gate on confirmed fixtures; TC089 fetches the Quotations search view |
| `tests/wf002/test_confirmation_gates.py` | TC085 fixture `memo=None`; D-19 recorded in the docstring |
| `tests/wf003/common.py` | `gate_analytic()`, `line_analytic=` on `make_quotation`, `plain_text()` |
| `tests/wf003/test_revision_visibility.py` | TC097 confirmed fixture carries the distribution |
| `tests/wf003/test_revision_lifecycle.py` | TC095 matches the chatter as rendered text |
| `tests/wf003/test_revision_constraint.py` | TC098 accepts a unique index or a unique constraint |
| `tests/wf003/test_workday_reimport.py` | TC338 reads `ir.model.fields.copied` |
| `tests/wf013/common.py` | `anglo_saxon_lines()`; `realtime_category()` prefers a fully configured category |
| `tests/wf013/test_cogs_by_order_type.py` | `_cogs_pair` delegates to the shared helper |
| `tests/wf013/test_cogs_edge_cases.py` | TC228 uses the shared helper |
| `tests/wf013/test_move_security.py` | `_make_user` uses the adapter's groups field |
| `tests/wf020/common.py` | cron failure fields split by owning model |
| `tests/wf020/test_cron_inventory.py` | TC460 asserts each half against its own model |
| `tests/wf020/test_sftp_endpoint.py` | TC305 same split |
| `tests/wf020/test_sftp_transport.py` | TC301 drops the developer-only write; TC302 re-targeted to the required post-fix outcome |
| `tests/wf020/test_supplier_gate.py` | TC331 blank normalisation |
| `tests/wf020/test_supplier_upsert.py` | TC333 blank normalisation (steps 6 and 12) |

### `DTO-Odoo/` (product)

| File | Change |
|---|---|
| `project-addons/dto_account_cogs/models/account_move.py` | E5 fix: `self.` → `move.` in `_prepare_reverse_revenue_lines_vals` |

Compile check: `venv/Scripts/python.exe -c "from framework import registry; print(len(registry.discover()))"` → **100**.

---

## What to expect on the next run

* **23 cases** should turn green once the environment is otherwise unchanged
  (group B), **plus TC230** if the `dto_account_cogs` change is approved and
  the module is upgraded (`-u dto_account_cogs`).
* **4 cases** (group A) will still fail — that is the correct outcome.
  TC085 and TC302 should be re-booked as **FIXED** against decisions D-19 and
  the WF-020 B2 remediation.
* **20 cases** (group D) will still fail until the database and module set are
  aligned. None of them is a code fault.
* **Watch for one new failure:** `TEST-WF003-TC014` step 2 now finds 7
  `groups_id` hits in the un-ported `base_tier_validation`. That module is
  `[HOLD]` pending the Phase-0b scoping decision.
