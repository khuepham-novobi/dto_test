# DATAONE-WF-022 — Scrap with Defect Coding and Approval · Automation Plan

| | |
|---|---|
| Workflow | `DATAONE-WF-022` |
| Build order | 11.0 · Area: Inventory / Manufacturing (approval-gated) |
| Effective risk | **CRITICAL** · Fail mode: loud + silent |
| Owns | 7 workbook test cases — **2 of them P0** (`TC178`, `TC182`) |
| Suite | `tests/wf022/` |
| Modules | `dto_tier_validation_scrap` (v17 carrier), `dto_scrap` (v19 carrier), `dto_stock` (F080) |
| Features | `DATAONE-F251`–`F255`, `F080` · approval framework F240–F246 all `[HOLD]` |

## Result

| | Count |
|---|---:|
| Implemented | **7** |
| Blocked stub | 0 |
| Not implemented | 0 |
| **Total** | **7** |

Every owned case is fully implementable over RPC. Two workbook
`automation_approach` notes are deliberately **upgraded, not downgraded**:

- `TC178` is written as an Odoo tour / `browser_js` case. Its own **step 13**
  demands *"read the rendered arch, not just the effect"* — which
  `get_view()` delivers exactly, and more deterministically than a browser.
  The tour would prove the effect; the arch proves the *cause*.
- `TC183` is a "Wave 2 — candidate". Nothing in its steps 1–11 needs a
  browser: the Cancel button's `invisible` modifier and the list decoration
  are both record-independent arch attributes.

---

## Scope

### In scope

| | |
|---|---|
| `DATAONE-TC167` | The scrap order's Journal Entries stat button opens its write-off entry |
| `DATAONE-TC178` | Validate in the quick-scrap dialog opens the full scrap form instead of scrapping |
| `DATAONE-TC179` | Validate with a zero quantity raises the exact positive-quantity error |
| `DATAONE-TC180` | Defect code B yields *Received Damaged*, case- and whitespace-insensitively |
| `DATAONE-TC181` | An unrecognised defect code yields *Unknown defect code* and is not rejected |
| `DATAONE-TC182` | Scrap Amount equals quantity × standard price after UoM conversion |
| `DATAONE-TC183` | The Cancelled state is reachable from Draft and is terminal |

### Out of scope

- **The approval framework itself** (`F240`–`F246`, suite APR). All `[HOLD]`,
  and `tier_definition` / `tier_review` / `tier_validation_exception` hold
  **zero rows on `dto_17`, for every model, ever** (`DTO/WF022-README.md`).
  No test here creates a `tier.definition`.
- **The ORM-bypass assertion** — that `action_validate()` called directly
  still scraps, and that `action_cancel()` has no state guard. `TC178`'s own
  notes assign that to SEC; this plan records the evidence (see *Findings*)
  and never exercises it against live data.
- **`SP/` vs `SP-`** (WF-027 / F010): core creates the scrap sequence with
  `prefix = 'SP/'` (`O17 stock/models/res_company.py:118`, identical
  `O19 :100-110`) while `dto_reports/views/accounting_views.xml:20` filters
  Scrap journal entries on `('ref','ilike','SP-')`. **`SP/` ≠ `SP-`.**
- **The `E6` singleton defect** — `StockScrap.search([('picking_id','=',self.id)])`
  inside `for res in self` at `dto_stock/models/stock_picking.py:32` (present
  identically in the v17-deployed revision, git `7e44907^:…/stock_picking.py:26`).
  It belongs to the "Stat button (INV, VAL)" supporting case.
- Any write to application source, `framework/`, `adapters/`, another
  suite's folder, or the workbook (hard rule 1).

### Assumptions

1. The QA target is a dedicated `_qa` clone with crons, mail servers and the
   Workday SFTP connector deactivated (`AUTOMATION_CONVENTIONS`,
   "Environment facts"). Nothing in this suite reaches an external host, so
   no `require_mail_offline` gate is needed.
2. The platform session holds `stock.group_stock_manager`. It must: core ACL
   gives `perm_unlink` on `stock.scrap` only to that group
   (`O17 stock/security/ir.model.access.csv:54-55`; `O19 :41-42`), and
   without it the `finally:` cleanup cannot remove a fixture.
3. The target's active language is `en_US`, so `_('Unknown defect code')`
   renders verbatim. See `[UNVERIFIED-3]`.

### Dependencies

- `stock` and `mrp` must be installed — the quick dialog is reached from
  `mrp.production.button_scrap()` and the `Cancelled` filter's anchor lives
  in `mrp.stock_scrap_search_view_inherit_mrp`. Probed by
  `common.require_mrp`.
- `stock_account` must be installed with a real-time-valuation category for
  `TC167`'s entry half. Probed by reading the live done scrap's own entries
  rather than by configuring anything.
- `dto_stock` must contribute `stock.scrap.account_move_ids` for `TC167`.
  Probed by `common.check_journal_entries_field`.

---

## §0 — The blocking environment fact, and why it is a `check` not a `skip`

**This decides the shape of all seven cases and is the first thing to read.**

| Fact | Evidence |
|---|---|
| `dto_tier_validation_scrap` now declares `'installable': False` | `DTO/project-addons/dto_tier_validation_scrap/__manifest__.py:56` (rationale :39-55) |
| It was `True` until commit `d847a6b` *"[WF-022] extract the live scrap half into dto_scrap; retire the tier layer"* — that commit changed **only** the manifest in this module | `DTO` git |
| v17 **skips a not-installable module even when the DB row says `state='installed'`**: `if info and info['installable']: packages.append(...)` else `_logger.warning('module %s: not installable, skipped')` | `O17 odoo/modules/graph.py:72-75` |
| The v17 addons path does include this tree | `AUTOMATION_CONVENTIONS.md:178-181`; `config/local.yaml:43` uses the same `DTO_SOURCE_ROOT` for both versions |
| The same tree's `dto_stock` is already v19-shaped and cannot work on v17: `res.account_move_ids = res.move_ids.account_move_id` — `stock.move.account_move_id` does not exist on v17 | `DTO/project-addons/dto_stock/models/stock_scrap.py:22`; `O17 stock_account/models/stock_move.py:19` (One2many `account_move_ids`) vs `O19 :51` (Many2one `account_move_id`) |
| The v17-deployed revision of that compute reads `res.move_ids.account_move_ids` | git `6e410c8:project-addons/dto_stock/models/stock_scrap.py:17` |

**Two realities the suite must not choose between:**

1. The Odoo-17 server on `:8076` runs a pre-port checkout, or a long-lived
   process started before the port. Everything below is testable as the
   workbook describes.
2. The Odoo-17 server reloads the current tree. `stock.scrap` then carries
   none of WF-022's fields, and `dto_stock`'s scrap stat button raises.

**Decision.** The workbook's own precondition is *"dto_tier_validation_scrap
is installed"*. It is implemented as the **first `ctx.check` of every test**
(`common.check_scrap_extension`, `common.check_journal_entries_field`), not
as a `ctx.skip` or `ctx.blocked`. A missing field is then a loud, correctly
attributed **FAIL** rather than an `AUTOMATION_ERROR` or a silently green
skip. The `ctx.blocked` variants (`require_scrap_extension`,
`require_journal_entries_field`) exist only for helpers that cannot build a
fixture at all.

**Not a defect:** `dto_scrap` (`version 19.0.0.0`, `installable: True`,
`__manifest__.py:10,36`) re-declares the identical fields on `stock.scrap`
with **no** tier dependency, and v17 has no `check_version` manifest gate
(the gate is `O19 odoo/modules/module.py:465-467`), so `dto_scrap` is
installable on v17 too — but it is `uninstalled` on the `dto_17` clone
unless someone installs it. **Which module supplies a field is therefore
unknown at runtime, and the suite asserts on the field / method / arch,
never on a module name.**

---

## Verified source facts

Abbreviations: `DTO` = `D:/Projects/dataone/DTO-Odoo`, `O17` =
`D:/Projects/dataone/odoo-17.0`, `O19` = `D:/Projects/odoo-19.0`.

### The model and its two carriers

| Fact | Where |
|---|---|
| Core `stock.scrap`, `_inherit = ['mail.thread']`, `_order = 'id desc'` | `O17 stock/models/stock_scrap.py:10-14` · `O19 :10-14` |
| v17 carrier: `_inherit = ['stock.scrap','tier.validation']`, `_state_from=['draft']`, `_state_to=['done']`, `_cancel_state=''`, `_tier_validation_manual_config=False` | `DTO/…/dto_tier_validation_scrap/models/stock_scrap.py:9-16` |
| v19 carrier: `_inherit = 'stock.scrap'` only — no mixin, no class attributes | `DTO/…/dto_scrap/models/stock_scrap.py:28-29` (documented :13-21) |

### Field table (verbatim declarations)

| Field | Declaration | v17 | v19 |
|---|---|---|---|
| `state` | `Selection(selection_add=[('cancel','Cancelled')], ondelete={'cancel':'set default'})` | `:21` | `:40` |
| core `state` | `[('draft','Draft'),('done','Done')]`, `readonly=True`, `tracking=True` — **no native `cancel` on either version** | `O17 :50-53` | `O19 :50-53` |
| `company_currency_id` | `Many2one('res.currency', string="Company Currency", related='company_id.currency_id')` | `:22-23` | `:41-42` |
| `amount` | `Monetary(compute='_compute_amount', store=True, help='Estimated Amount', currency_field='company_currency_id')` | `:24-25` | `:43-44` |
| `defect_code` | `Char` — **no `required`, no constraint, no selection** | `:27-37` | `:46-56` |
| `defect_code_description` | `Char(compute='_compute_defect_code_description', store=True)` — **no field-level `readonly`**; read-only is a *view* attribute | `:38-42` | `:57-61` |
| `employee_name` | `Char(string='Employee')` — plain Char, no `hr.employee`, no validation | `:44` | `:63` |
| `account_move_ids` | `Many2many('account.move', string='Journal Entries', compute='_compute_account_move_ids')` — **not stored** | `dto_stock/models/stock_scrap.py:10-11` | same |

### The nine-code table — identical in both modules

`_compute_defect_code_description`, `@api.depends('defect_code')`, stored —
v17 `:49-66` (table `:52-62`, lookup `:64`, empty branch `:66`); v19 `:68-89`
(table `:75-85`, lookup `:87`, empty `:89`):

```
A → Not in BOM            B → Received Damaged      C → Operator Error
D → Shortage              E → Fail Test             F → Overage
G → Wrong Parts Received  H → Other                 R → Reference Cable
```

Lookup, verbatim:
`defect_codes.get(res.defect_code.upper().strip(), _('Unknown defect code'))`.

- Fallback string, character for character: **`Unknown defect code`**.
- Empty / `False` code → **`''`** (empty string, *not* the fallback).
- `.upper()` then `.strip()`, so `"b"`, `"B  "`, `"  b"` and `"  B  "` all
  resolve. Exercised for real: `dto_17` holds lower-case `h`, `c`, `b`, `d`
  (`dto_scrap/models/stock_scrap.py:70-73`).

### `_compute_amount` — identical in both modules

v17 `:68-72`, v19 `:91-100`:

```python
@api.depends('scrap_qty', 'product_id', 'product_id.standard_price')
def _compute_amount(self):
    for res in self:
        scrap_uom_qty = res.product_uom_id._compute_quantity(res.scrap_qty, res.product_id.uom_id)
        res.amount = scrap_uom_qty * res.product_id.standard_price
```

The depends set **does not include `product_uom_id`** — changing only the
UoM does not itself trigger a recompute; changing `scrap_qty` or
`product_id` does. That is a real, assertable subtlety of BR-6.

### Method reachability — the feasibility gate

**Public, RPC-reachable, JSON-marshallable:**

| Method | Returns | Where |
|---|---|---|
| `stock.scrap.action_confirm_create_scrap()` | `ir.actions.act_window` **dict** | v17 `:96-109` · v19 `:113-132` |
| `stock.scrap.action_cancel()` | `None` (writes `state='cancel'`) | v17 `:80-82` · v19 `:105-111` |
| `stock.scrap.action_validate()` | `True`, or a wizard dict on short stock | `O17 :196-220` · v17 override `:77-78` · `O19 :211-234` |
| `stock.scrap.do_scrap()` / `check_available_qty()` | `True` / `bool` | `O17 :140-152` / `:181-194` |
| `stock.scrap.action_view_journal_entries()` | dict, or `None` when empty | `dto_stock/models/stock_scrap.py:26-40` |
| `mrp.production.button_scrap()` | dict, `target:'new'` | `O17 mrp_production.py:2160-2173` · `O19 :2406-2419` |
| `stock.picking.button_scrap()` | dict, same shape | `O17 stock_picking.py:1563-1579` · `O19 :1900-1916` |
| `get_view(view_id, view_type)` | dict with `arch` | `O17 ir_ui_view.py:2613` · `O19 :3138` |

**Not reachable — nothing here re-implements any of them:**
`_compute_defect_code_description`, `_compute_amount`,
`_compute_account_move_ids`, `_prepare_move_values`,
`_should_check_available_qty`, `_validate_tier` (`:84-88`), `_rejected_tier`
(`:90-94`), `_get_partners_to_notify_on_accepted/_rejected` (`:114-121`),
`_account_entry_move`, `_create_account_move`, and — the one that shapes
`TC182` — **`uom.uom._compute_quantity`**.

### Exact error strings

| String | Raised by | Where |
|---|---|---|
| `You can only enter positive quantities.` | `action_confirm_create_scrap` **and** core `action_validate` | v17 `:99` · v19 `:122` · `O17 :200` · `O19 :214` |
| `You cannot delete a scrap which is done.` | `@api.ondelete` on core | `O17 :107-110` · `O19 :120-123` |
| `%s cannot be deleted. Try to cancel them before.` | `mrp.production` ondelete | `O17 mrp_production.py:1255-1262` |
| `This action needs to be validated for at least one record. \nPlease request a validation.` | tier mixin `write()` | `tier_validation.py:350-355` |
| `A validation process is still open for at least one record.` | tier mixin `write()` | `:357-362` |
| `You are not allowed to write those fields under validation.…` | tier mixin `write()` | `:378-386` |

Types: `UserError` for the quantity guard (imported v17 `:6`, v19 `:24`);
`ValidationError` for every mixin gate (`tier_validation.py:10`).

**Trap this suite is built around:** the first string is raised by *both*
`action_confirm_create_scrap` and core `action_validate`. A test that merely
creates a zero-qty scrap and presses the generic Validate proves nothing
about F255. `TC179` therefore calls `action_confirm_create_scrap` **by
name**.

### XML ids

Core anchors: `stock.stock_scrap_form_view` (`O17 views/stock_scrap_views.xml:24`;
header `action_validate` `:30`; `button_box` div `:34`; `lot_id` `:61`) ·
`stock.stock_scrap_form_view2` (`:158`; footer
`<button name="action_validate" string="Scrap Products" class="btn-primary" data-hotkey="q"/>`
`:191` — **the label is "Scrap Products", not "Validate"**) ·
`stock.stock_scrap_tree_view` (`:124`, root `<tree>` `:128`, `state` `:139`) ·
`stock.stock_scrap_search_view` (`:4`) ·
`mrp.stock_scrap_search_view_inherit_mrp` (`O17 mrp/views/stock_scrap_views.xml:32-45`,
anchor `filter_done` `:39` — **same line on v19**) ·
`account.action_account_moves_all` (`O17 account/views/account_move_views.xml:1619-1626`
— **`res_model` is `account.move.line`**; `O19 :1925-1933`, `view_mode` now
`list,pivot,graph,kanban`).
v19 equivalents: form `:24` (header button `:30`, `lot_id` `:60`), form2
`:142` (footer `action_validate` **`:175`**), list `:108` with **`<list>`**
`:112`.

The four DataOne view inherits (v17 `dto_tier_validation_scrap/views/stock_scrap_views.xml`;
the same ids under `dto_scrap.*` on v19):

| Inherit | What it does | v17 | v19 |
|---|---|---|---|
| search | `filter_cancel` `[('state','=','cancel')]` after `filter_done` | `:10-11` | `:17-19` |
| search | `needs_review` `[('reviewer_ids','in',uid),('state','!=','done')]` | `:12-17` | **dropped** |
| form2 | rename `//button[@name='action_validate']` → `action_confirm_create_scrap` | `:32-34` | `:39-41` |
| form2 | `<xpath expr="//form" position="inside"><sheet><xpath expr="//form/group" position="move"/></sheet>` | `:27-31` | **dropped** (`:34-38`) |
| list | `validation_status` badge column, `optional="hide"` | `:43-52` | **dropped** |
| list | `state` → `decoration-muted="state == 'cancel'"`, `decoration-info="state == 'draft'"` | `:53-56` | `:53-56` |
| form | five-field block before `//field[@name='lot_id']` | `:65-71` | `:69-75` |
| form | `<button name="action_cancel" invisible="state != 'draft'" string="Cancel" type="object"/>` before `action_validate` | `:72-74` | `:76-78` |

`dto_stock/views/stock_scrap_views.xml:3-20` adds, inside
`//div[@name='button_box']`, an invisible `account_move_ids` field and a
stat button `action_view_journal_entries`, `icon="fa-book"`,
`invisible="not account_move_ids"`, label span `Journal Entries`.
**There is no counter/field widget on that button**, so `TC167` step 3
("counter is 1 or greater") is asserted as `len(account_move_ids) >= 1`,
never as rendered digits.

### The tier mixin rewrites the rendered arch on v17

`TierValidation.get_view()` (`tier_validation.py:749-791`) fires for **any**
`stock.scrap` form view on v17, because `_tier_validation_manual_config = False`:

1. `:757-765` injects `request_validation` / `restart_validation` after
   `/form/header/button[last()]`. `stock.stock_scrap_form_view2` has **no
   `<header>`**, so nothing is injected there.
2. `:766-779` prepends the validation alert and appends the `review_ids`
   widget to every `/form/sheet` — the only reason the v17 `<sheet>` wrap
   exists in the quick dialog.
3. `:780-788` **adds `readonly` to every `//field[@name][not(ancestor::field)]`**:
   `new = "bool(review_ids)"`, and when the node already has one,
   `f"({old}) or ({new})"`. Exceptions are only `message_follower_ids` and
   `access_token` (`:13`).

**Consequence:** on v17 the full form renders
`defect_code_description readonly="(1) or (bool(review_ids))"` and
`defect_code readonly="bool(review_ids)"`; on v19 they are `"1"` and absent.
**No arch assertion in this suite may hard-code `readonly="1"`** — they all
go through `common.readonly_is_absolute()`, which accepts `"1"` and
`"(1) or (…)"` and is documented at the call site.

### Security — no new groups, no new ACL rows

- `dto_tier_validation_scrap/__manifest__.py:25-37` and
  `dto_scrap/__manifest__.py:31-34` list **only** `views/stock_scrap_views.xml`
  — no security file, no data file.
- No `res.groups` record exists anywhere in `dto_stock`, `dto_scrap` or
  `dto_tier_validation_scrap`.
- Core ACL: `access_stock_scrap_user,…,stock.group_stock_user,1,1,1,0` and
  `access_stock_scrap_manager,…,stock.group_stock_manager,1,1,1,1`
  (`O17 stock/security/ir.model.access.csv:54-55`; `O19 :41-42`, plus two new
  `stock.scrap.reason.tag` rows `:43-44`). **`stock.group_stock_user` cannot
  unlink** → cleanup runs under the admin session.
- Record rule `stock.stock_scrap_company_rule`,
  `domain_force=[('company_id','in',company_ids)]`
  (`O17 stock/security/stock_security.xml:171-175`).

---

## Per test case

| TC | Test id | Kind | Priority | Module | What is proven | v17 outcome | v19 outcome |
|---|---|---|---|---|---|---|---|
| `TC167` | `TEST-WF022-TC167` | API | P1 | `dto_stock` | Field declaration, draft⇒empty branch, the act_window (`account.move.line` + line-id domain + 3 context keys), the stat-button arch, and `amount` vs the posted valuation value | **PASS** (subject to §0) | PASS with the steps 7-8 half **BLOCKED** |
| `TC178` | `TEST-WF022-TC178` | HYBRID | **P0** | `dto_tier_validation_scrap` | Rendered arch of `stock_scrap_form_view2` (`action_confirm_create_scrap` present **and** `action_validate` absent) + the act_window + zero side effects; MO and picking paths via `button_scrap()` | **PASS** | **FAIL — by design, on step 5's expectation, raised at the deferred final step so steps 6–14 still run** |
| `TC179` | `TEST-WF022-TC179` | API | P2 | `dto_tier_validation_scrap` | The exact `UserError` from `action_confirm_create_scrap` **called by name**; control case at qty 1 | **PASS** | PASS |
| `TC180` | `TEST-WF022-TC180` | DATA | P1 | `dto_tier_validation_scrap` | All nine mappings, `b`/`B  `/`  b`, empty ⇒ `''`, field position, `employee_name` as a plain Char; the nine pairs exported as the migration baseline | **PASS** | PASS |
| `TC181` | `TEST-WF022-TC181` | DATA | P2 | `dto_tier_validation_scrap` | `Z` / `XX` / `1` accepted, described `Unknown defect code`; no constraint exists to reject them; residue count logged as a baseline | **PASS** | PASS |
| `TC182` | `TEST-WF022-TC182` | API | **P0** | `dto_tier_validation_scrap` | `amount` = converted-qty × `standard_price`, via Units↔Dozens; declared attributes; the stored-compute recompute on a price change | **PASS** | PASS |
| `TC183` | `TEST-WF022-TC183` | HYBRID | P2 | `dto_tier_validation_scrap` | `selection_add` via `fields_get`, `action_cancel` on a draft fixture, the Cancel button's modifier, the list `decoration-muted`, `filter_cancel` | **PASS** | PASS |

### `TC178` — the one expected FAIL, and why it stays

Step 5 asserts *"core's `<group>` is wrapped in a `<sheet>` (the structural
inherit applied)"*. That inherit exists on v17
(`dto_tier_validation_scrap/views/stock_scrap_views.xml:27-31`) and was
**deliberately not ported** to v19
(`dto_scrap/views/stock_scrap_views.xml:34-38` and `DTO/WF022-README.md`,
"Deliberately not ported"): the wrap existed only to give the tier mixin a
`/form/sheet` anchor, and v19 restricts `position="move"` to inner-mode
replaces anyway.

Core's own v19 `stock_scrap_form_view2` has no `<sheet>` either — it is
`<form><group>…</group><footer>…</footer></form>`
(`O19 stock/views/stock_scrap_views.xml:146-178`).

The workbook expectation is immutable (hard rule 2). The test therefore
carries, verbatim in its docstring:

```
EXPECTED v19 OUTCOME: FAIL — the <sheet> wrap was deliberately dropped
(dto_scrap/views/stock_scrap_views.xml:34-38); it existed only as the tier
mixin's /form/sheet anchor and v19 restricts position="move" to inner-mode
replaces.
```

Nothing about the assertion is softened, inverted or paraphrased.

#### The verdict is deferred to the end of the test — and why that matters

`ctx.check` **raises** on mismatch (`framework/context.py:128-135`). With the
assertion inside step 5, the v19 run aborted there and steps 6–14 never
executed — **step 13 among them**, which the workbook calls *the case*
(*"read the rendered arch, not just the effect"*) and which the workbook's
own supporting case calls *"the single most important post-port case … if the
rename failed to apply this is the only test that catches it"*. The result
was a P0 suite that produced **zero F255 evidence on the one bench it exists
for**.

Step 5 therefore records its mismatch into a `deferred` list and a final,
explicitly non-workbook step raises the verdict after all fourteen steps have
run:

- The expected dict, the actual dict and the assertion name are **unchanged**
  — byte for byte the same check, only later.
- The verdict is unchanged: **PASS on v17** (nothing deferred), **FAIL on
  v19**.
- The evidence is larger: on v19 the run now also reports step 13's rename
  facts, step 14's picking path, and steps 9–12's zero-side-effect facts.

This is the same deferral `TC167` already uses for its `BLOCKED` verdict
(`tests/wf022/test_scrap_valuation.py`, the `blockers` list), and it is what
AUTOMATION_CONVENTIONS' *"Mismatch dicts, not assertion loops … so a failure
reports all of them"* asks for.

---

## Adaptations (documented, not assertion-weakening)

1. **`TC167` is read-only over the live done-scrap population.** The
   workbook fixture is *"a scrap of TD-P-04 has been validated and is done"*.
   Creating one cannot be unwound: core refuses to unlink a done scrap
   (`You cannot delete a scrap which is done.`, `O17 :107-110`) and its
   posted valuation entry cannot be removed. Hard rule 3 forbids it. The
   environment holds 797 scraps, 791 with an `amount`
   (`DTO/WF022-README.md`), so `common.live_done_scrap_with_entries()`
   selects the newest done scrap that actually has entries and the case
   asserts against that, read-only. Step 9 (draft ⇒ counter zero) uses a
   token-scoped **draft** scrap, which is deletable.
2. **`TC178` step 13 is asserted with `get_view`, not a tour.** The workbook
   demands the rendered arch; `get_view(ref('stock.stock_scrap_form_view2'),
   'form')` returns exactly that, and it is the assertion that catches an
   xpath which loaded cleanly and matched nothing. Note
   `fg_common.form_arch()` cannot be used for this view — it fetches the
   model's *default* form, which is the full form.
3. **`TC179` calls `action_confirm_create_scrap` by name.** Core's
   `action_validate` raises the identical message, so the generic path is
   not evidence about F255.
4. **`TC181` step 7 is proven structurally, not by scrapping live stock.**
   `action_validate` contains no reference to `defect_code` anywhere in core
   or in either DataOne module. The test uses a token-scoped storable
   fixture with its own quant and asserts the absence of any constraint; a
   live product is never scrapped, because the move and its valuation entry
   are irreversible.
5. **`TC181` step 8 is logged, not asserted.** The production residue count
   (`search_count("stock.scrap", [("defect_code_description","=","Unknown defect code")])`)
   is a whole-table baseline; hard rule 5 forbids an unscoped "exactly N"
   claim. It is recorded with `ctx.log` and `ctx.add_artifact`.
6. **`TC182` avoids the private `uom._compute_quantity` with Units↔Dozens.**
   The conversion arithmetic is **inverted between versions** — v17
   `qty / self.factor * to_unit.factor` (`O17 uom/models/uom_uom.py:234-236`),
   v19 `qty * self.factor / to_unit.factor` (`O19 :169-171`) — and
   `uom.category_id` exists only on v17 (`O17 :56`; v19 replaced it with
   `relative_factor` / `relative_uom_id`, `O19 :36-44`). "One dozen is twelve
   units" is true under both, so the expected value is `12 * standard_price`
   with **no version branch in any test body**. `uom.product_uom_unit` is the
   reference (`O17 uom/data/uom_data.xml:26-31` · `O19 :12-15`);
   `uom.product_uom_dozen` is 12 (`O17 :33-38` `factor_inv=12` · `O19 :21-26`
   `relative_factor=12`).
7. **`TC182` writes `standard_price` only on a zero-on-hand token product.**
   `_change_standard_price` skips a product whose `quantity_svl <= 0`
   (`O17 stock_account/models/product.py:243-248`), so no revaluation layer
   and no journal entry is posted. The price is restored in `finally:`.
   Writing it on a live product would silently recompute the **stored**
   `amount` of every historical scrap of that product.
8. **`TC183` asserts the Cancel button's modifier, not a rendered done
   record.** `invisible="state != 'draft'"` is record-independent, so "not
   visible on the done scrap" is an arch fact. No live done scrap is
   touched — and it must not be, because `action_cancel` has no state guard
   (see *Findings*).
9. **Two v19-only UoM wrinkles are capability-probed, never version-branched.**
   `uom.product_uom_dozen` ships `active=False` on v19
   (`O19 uom/data/uom_data.xml:25`) — the fixture does **not** unarchive it
   (that would modify a pre-existing record); an ORM write of a Many2one to
   an archived record is permitted and `_compute_quantity` reads its factor
   regardless. `stock.scrap.product_uom_id`'s domain narrowed to
   `[('id','in',allowed_uom_ids)]` (`O19 stock_scrap.py:24-28`, source
   `:61-64`), a *view* constraint only;
   `common.allow_uom_on_product()` adds the UoM to `product.template.uom_ids`
   (`O19 product/models/product_template.py:122`) when that field exists, so
   the fixture stays coherent in the UI too.
10. **Role labels are mapped, and the mapping is disclosed.** `TD-U-04
    dto_stock_mgr` and `TD-U-05 dto_mrp` are test-data names, **not** group
    XML ids `[UNVERIFIED-1]`. `common.ROLE_GROUPS` maps them to
    `stock.group_stock_manager` and `mrp.group_mrp_user +
    stock.group_stock_user`. Fixtures are created and swept with the admin
    session regardless, because `stock.group_stock_user` holds no
    `perm_unlink`.
11. **`TC178`'s step 5 verdict is deferred to a final non-workbook step.**
    Expectation byte-identical, verdict identical, evidence larger. Full
    rationale in *`TC178` — the one expected FAIL, and why it stays* above.
12. **The sweep is honest about what it cannot remove.** `common.add_stock()`
    stages fixture stock by **validating** an incoming picking, which is the
    only staging path available here: the inventory-count path goes through
    `stock.quant._apply_inventory`, overridden by
    `dto_cycle_count/models/stock_quant.py:23` with a call whose first line is
    `ensure_one()` — *Expected singleton* on this target (recorded in
    `tests/wf025/common.py:204-214`). A validated picking can never be
    deleted: `stock.picking.unlink()` calls `move_ids._action_cancel()`
    (`O17 stock/models/stock_picking.py:904-907`), which raises *You cannot
    cancel a stock move that has been set to 'Done'.*
    (`O17 stock/models/stock_move.py:1778-1780`). So per full run the target
    keeps, under the `WF022` marker:
    - the validated receipts and their `done` moves (4 across the suite);
    - their `stock.quant` rows — a non-superuser unlinking a quant is routed
      through `inventory_quantity = 0` + `_apply_inventory()`
      (`_unlink_except_wrong_permission`, `O17 stock/models/stock_quant.py:375-382`),
      i.e. straight back into the singleton defect above;
    - the fixture **products**, which are therefore **archived, not deleted**
      — the fallback pattern of `framework/qa_fixtures.py:37-52`.

    Two things make that residue safe rather than merely tolerated.
    `common.sweep_each()` unlinks **row by row** (as `drop_scraps` already
    did), so one undeletable receipt no longer takes `make_picking`'s
    deletable fixtures down with it — `framework.qa_fixtures.sweep_model`
    issues a single `unlink(ids)` for the whole batch and swallows the error
    (`framework/qa_fixtures.py:55-61`). And every sweep domain matches on the
    `WF022` marker with `active in (True, False)`, so a rerun steps over the
    archived leftovers instead of duplicating them (hard rule 3 is about
    pre-existing **business** records; nothing outside the marker is
    touched). `sweep_wf022()` returns the surviving ids and
    `open_namespace()` logs them at step 0 of every test.
13. **`TC167` guards the `done` branch it reads.** Selecting
    `account_move_ids` on a **done** scrap forces
    `_compute_account_move_ids`' `done` branch, which dereferences
    `move_ids.account_move_id` (`dto_stock/models/stock_scrap.py:22`) — a
    field that exists only on v19 (`O19 stock_account/models/stock_move.py:51`;
    v17 has the One2many `account_move_ids`, `O17 :19`). Which revision the
    v17 server loaded is §0's reality 1 vs reality 2 and is not decidable
    from source, so `common.live_done_scrap_with_entries()` wraps its scan in
    `try/except OdooRPCError` and `TC167` turns a raise into a **BLOCKED**
    verdict naming both lines and the field probe — not an unattributed
    `OdooRPCError` inside step 1. The *draft* path was already safe by
    construction (the `else` branch dereferences nothing); this is the `done`
    half of the same guard.
14. **Environment gaps are BLOCKED verdicts, not `AssertionError`s.** The
    fixture-environment helpers (`warehouse`, `stock_location`,
    `scrap_location`, `inventory_location`, `picking_type`) raise
    `common.FixtureEnvironmentGap` instead of a bare `AssertionError`
    (AUTOMATION_CONVENTIONS.md:88-90), and `common.open_namespace()` — which
    every test calls before it builds anything — probes them and converts the
    gap into `ctx.blocked(...)` with the missing piece named.

---

## `[UNVERIFIED]` claims and what would validate each

| Id | Claim | Why it could not be settled from source | What would validate it |
|---|---|---|---|
| `[UNVERIFIED-1]` | `TD-U-04 dto_stock_mgr` / `TD-U-05 dto_mrp` are group XML ids | A `grep` for `res.groups` over `dto_stock`, `dto_scrap` and `dto_tier_validation_scrap` returns nothing; both manifests list only the view file | Read the workbook's test-data sheet, or `search_read('res.groups', [('name','ilike','dto')])` on the target. Until then `ROLE_GROUPS` maps them to the core groups and says so at the call site |
| `[UNVERIFIED-2]` | Whether the v17 QA server has the current tree loaded (see §0) | A running-process fact, not a source fact | Probe `ir.module.module` for `dto_tier_validation_scrap` / `dto_scrap` state **and** `stock.scrap.fields_get` — the suite already does the second as its first `ctx.check` |
| `[UNVERIFIED-3]` | `Unknown defect code` renders verbatim on the target | The string is wrapped in `_()`. Neither module ships an `i18n/` directory, so no `.po` of theirs can override it — but a database whose active language is not `en_US` could still resolve it elsewhere | Read `res.lang` active languages / `res.users.lang` on the target before pinning the literal. `TC181` pins it and would FAIL loudly, which is the right failure |
| `[UNVERIFIED-4]` | The DataOne database's scrap sequence prefix is `SP-` | Core creates it as `SP/` (`O17 stock/models/res_company.py:118`) while `dto_reports/views/accounting_views.xml:20` filters on `('ref','ilike','SP-')`. Whether the row was hand-edited is a **database** fact | `search_read('ir.sequence', [('code','=','stock.scrap')], ['prefix'])`. Owned by WF-027 / F010; worth one read-only probe while `TC167` runs |
| `[UNVERIFIED-5]` | The exact debit/credit accounts of the v19 write-off entry | v19 rebuilt the valuation engine — `stock.valuation.layer`'s model file is gone, the entry is built by `_create_account_move`, the debit comes from `location_dest_id.valuation_account_id` only (`O19 stock_account/models/stock_location.py:11`), the credit from the product's `stock_valuation`, and the journal from `company.account_stock_journal_id` (`O19 stock_move.py:209-249, 661-668`) | Run `TC167` against a v19 bench with a real-time category configured. On v17 the shape **is** verified: a scrap is an out-move to an inventory-usage location, so `_account_entry_move` takes the `_is_out()` branch and calls `_prepare_account_move_vals(acc_valuation, acc_dest, …)` = `(credit, debit, …)` — Credit = category `stock_valuation`, Debit = `location_dest_id.valuation_in_account_id` or category `stock_output` (`O17 stock_account/models/stock_move.py:526, 587-592, 392-398`) |

---

## v17 → v19 deltas that affect this suite

| # | Concern | v17 | v19 | Handled by |
|---|---|---|---|---|
| 1 | `stock.scrap.state` | `draft`/`done` | `draft`/`done` — **no native `cancel`, the `selection_add` is safe** | `TC183` asserts it (`O17 :50-53` / `O19 :50-53`) |
| 2 | `product_uom_category_id` | present (`:28`) | **removed**, replaced by `allowed_uom_ids` (`:24`, `:61-64`) | `common.allow_uom_on_product` (capability probe) |
| 3 | `package_id` comodel | `stock.quant.package` | `stock.package` | not asserted by this suite |
| 4 | `product_id` domain | `[('type','in',['product','consu'])]` | `[('type','=','consu')]` | `ctx.adapter.storable_product_values()` |
| 5 | `scrap_location_id` domain | `[('scrap_location','=',True)]` | `[('usage','=','inventory')]` | `common.scrap_location` (column probe) |
| 6 | `scrap_qty` digits | `'Product Unit of Measure'` | `'Product Unit'` | last-decimal risk on v19; whole-number fixtures avoid it |
| 7 | core zero guard | `float_is_zero(qty, precision_rounding=uom.rounding)` | `product_uom_id.is_zero(qty)` | not asserted — `TC179` asserts DataOne's guard |
| 8 | **DataOne's** zero guard | `float_is_zero(..., self.product_uom_id.rounding)` | **unchanged, and it still resolves**: `uom.rounding` survives as a compute kept explicitly "to ensure compatibility with previous calls to `uom.rounding`" (`O19 uom_uom.py:39, 62-67`) | `TC179` — this closes the workbook's `v19_watch` question |
| 9 | `uom.uom` shape | `category_id`, `factor`, `factor_inv`, `uom_type`, stored `rounding` | `category_id` **gone**; `relative_factor` / `relative_uom_id` / `parent_path`; `factor` semantics **inverted** | `TC182` uses Units↔Dozens (adaptation 6) |
| 10 | `_compute_quantity` maths | `qty / self.factor * to_unit.factor` | `qty * self.factor / to_unit.factor` | same |
| 11 | `uom.product_uom_dozen` | active | **`active=False`** (`O19 uom_data.xml:25`) | `common.dozen_uom_id` — never unarchived |
| 12 | `_should_check_available_qty` | `product_id.type == 'product'` | `product_id.is_storable` | adapter |
| 13 | scrap → journal link | `stock.move.account_move_ids` One2many | `stock.move.account_move_id` Many2one; several moves batched into **one** entry | `TC167` reads the scrap's own computed field, exercising the divergence rather than bypassing it |
| 14 | valuation engine | `stock.valuation.layer` with `value`, `unit_cost`, `stock_move_id`, `account_move_id` | model file **gone** (`product_value.py` instead) | `common.has_valuation_layer_model` → `TC167` steps 7-8 `ctx.blocked` on v19 |
| 15 | list root tag | `<tree>` (`O17 :128`) | `<list>` (`O19 :112`) | `fg_common.list_tag` / `form_arch` |
| 16 | new native tagging | — | `scrap_reason_tag_ids` + `stock.scrap.reason.tag` (`name` translatable+unique, `sequence`, `color` `'#3C3C3C'`) — `O19 stock_scrap.py:56-59, 237-250` | `TC180` step 12 exports the nine pairs as the REPLACE baseline |
| 17 | `base_tier_validation` | `17.0.2.1.3`, installable | **no OCA 19.0 release**; a 17.0-versioned manifest is force-disabled by `check_version` (`O19 odoo/modules/module.py:465-467`) | why `dto_scrap` exists; no tier assertion is made on v19 |
| 18 | `res.users` groups m2m | `groups_id` | `group_ids` | `ctx.adapter.user_groups_field` |

---

## Findings recorded by this suite (evidence, not exercised)

1. **`action_cancel` has no state guard.** It is `ensure_one()` then a write
   of `state='cancel'` (v17 `:80-82` / v19 `:105-111`), with no check of the
   current state. On v17 the tier mixin lets it through:
   `_check_state_conditions` is False because `'cancel'` is not in
   `_state_to == ['done']` (`tier_validation.py:441-446`), and
   `_allow_to_remove_reviews` is False because `state_to in (self._cancel_state)`
   is `'cancel' in ''` (`:420-433`) — which is precisely BR-8. So a **done**
   scrap could be written to `cancel` through the ORM. The UI affordance is
   the only control. Never exercised here (hard rule 3); it belongs to the
   SEC "ORM bypass" case.
2. **The workbook's inherit-ordering worry does not materialise.** The
   `Cancel` button anchors on `//button[@name='action_validate']` in the
   **full** form, whose button (`O17 :30` / `O19 :30`) is never renamed; the
   F255 rename targets a *different view*, `stock_scrap_form_view2`. The two
   inherits do not race.
3. **`dto_stock`'s stat button has no counter widget** — the label is a bare
   span (`dto_stock/views/stock_scrap_views.xml:14-16`), so any "counter"
   assertion must be made on the recordset length.
4. **The v19 install gate is already answered.** `TC183` step 11's open
   question — *"if v19 has introduced a native `cancel` value, this raises at
   registry build"* — is settled in source: `O19 stock/models/stock_scrap.py:50-53`
   is `draft`/`done` only. Migrate as-is. The test pins it so a future v19
   point release that adds a native `cancel` fails loudly rather than at
   registry build.
5. **`_compute_amount`'s depends set omits `product_uom_id`**, so a UoM-only
   change does not recompute `amount`. `TC182` changes `scrap_qty` alongside
   the UoM, which is what the workbook's steps 7-9 describe anyway.

---

## Suite layout

```
tests/wf022/
  __init__.py
  common.py                 shared fixtures, constants and precondition guards
  test_scrap_gates.py       TC178, TC179, TC183
  test_defect_codes.py      TC180, TC181
  test_scrap_valuation.py   TC182, TC167
reports/data/wf022_feasibility.json
docs/WF-022_AUTOMATION_PLAN.md
```

## Run

```
venv/Scripts/python.exe -c "from framework import registry; print(len(registry.discover()))"
```
