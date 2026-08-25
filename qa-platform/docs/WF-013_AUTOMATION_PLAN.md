# DATAONE-WF-013 — Customer Invoice Posting: COGS and Revenue Recognition · Automation Plan

| | |
|---|---|
| Workflow | `DATAONE-WF-013` |
| Build order | 20 (Stage 5 — the rebuild, the hardest work in the project) · estimate **47 h** |
| Effective risk | **CRITICAL** |
| Owns | 39 workbook test cases — **30 of them P0**, the largest and highest-risk block in the wave |
| Suite | `tests/wf013/` |
| Modules | `dto_account`, `dto_account_cogs`, `dto_account_workday`, `dto_sale_stock`, `dto_mrp_account` |

## Result

| | Count |
|---|---:|
| Implemented | **39** |
| Blocked stub | 0 |
| Not implemented | 0 |
| **Total** | **39** |

## The finding this suite exists to catch

`dto_account_cogs` (and `dto_account`) override two Odoo hooks that **Odoo 19
renamed and removed**:

| Method | Odoo 17 | Odoo 19 |
|---|---|---|
| `_stock_account_prepare_anglo_saxon_out_lines_vals` | `stock_account/models/account_move.py:79` | **renamed** → `_stock_account_prepare_realtime_out_lines_vals` (`:68`) |
| `_stock_account_get_anglo_saxon_price_unit` | `stock_account/models/account_move.py:310`, `sale_stock:151` | **removed** → `_get_cogs_value()` under `_get_anglo_saxon_price_ctx()` (`:122`, `:163`) |

**Neither override raises on v19. They simply stop being called.** The
COGS/Interim analytic distribution and the project / inventory / cost_center
price rules disappear with no error at all — the invoice still posts, still
balances, still gets a number.

`TEST-WF013-TC222` is the case that makes that loud. It asserts four
sentinels only the overrides can produce:

1. the COGS debit is the **sales price 10.00** — a value of 9.00 is the FIFO
   cost and means the override is dead;
2. the Interim distribution is **exactly** `{Consumables, CC 202000}`, with
   the SO line's own Project account absent;
3. the COGS distribution merges the Project account **and** Consumables;
4. neither distribution is empty — an empty dict is the dead-override
   signature.

## Three more findings recorded

**Source defect (TC230, the workbook's E5).**
`_prepare_reverse_revenue_lines_vals` opens `for move in self:` and then
builds its line list from **`self`**, not from **`move`**
(`dto_account_cogs/models/account_move.py:118,133`); `_post`'s
default-analytic loop has the same shape at `:26`. Posting several invoices
in one call cross-contaminates their reversal lines. It is silent in totals
because the contamination self-cancels.

**Per-move, not per-line (TC227).** Both the AR redirect and the COGS basis
test the **whole move's** order types, so a consolidated invoice spanning a
project and a buy order applies the project rule to the buy line too —
leaving a Stock Interim residue (20.00 relieved against an 18.00 delivery
debit). WF-013 Open Question 7.

**The label contract (TC280 + TC281).** The label builder re-appends the
existing name, so the *only* thing stopping repeated posts from producing
`AR - Proj - Proj - Proj` is `button_draft` blanking the labels first. The
two cases are two halves of one contract and must both hold.

## Per test case

| Group | Workbook TCs | Platform tests | What is proven |
|---|---|---|---|
| Gates | `TC221`, `TC222` | `TEST-WF013-TC221/222` | `skip_invoice_sync` still yields two receivable lines; the four dead-override sentinels |
| COGS tables | `TC223`–`TC227`, `TC233` | `TEST-WF013-TC223…227`, `TC233` | The basis and AR routing per order type; the consolidated-invoice rule; the zero-basis shape |
| Edge cases | `TC228`–`TC232` | `TEST-WF013-TC228…232` | Missing 12500 no-ops silently; the five xmlids resolve; E5 contamination; three draft cycles; MRO by behaviour |
| AR labels | `TC279`–`TC283`, `TC286`, `TC287` | `TEST-WF013-TC279…287` | Suffixing, blanking, no concatenation, empty-segment safety, both AR lines, analytic inheritance, the create-hook firing on DataOne's own lines |
| Security | `TC270`–`TC274` | `TEST-WF013-TC270…274` | Only Settings holds `perm_unlink` on `account.move`, proven by rule **and** by real deletion attempts |
| Reconciliation | `TC007`, `TC021`, `TC023`, `TC025`, `TC027`, `TC028`, `TC034`, `TC048`, `TC049`, `TC051`, `TC052`, `TC258`–`TC260` | 14 tests | `env.ref()` resolution; trial balance, invoice totals, inventory value, distribution shapes and coverage, location columns, journal items, residuals, tax totals, `is_cogs` population, and the three baselines |

## Environment dependencies — every one probed, never assumed

Each produces a **precise BLOCKED reason** rather than an obscure failure
deep inside a posting:

| Requirement | Why | Probe |
|---|---|---|
| `anglo_saxon_accounting` ON | `_prepare_reverse_revenue_lines_vals` skips every move otherwise, so the suite would assert nothing | `require_anglo_saxon` |
| A real-time-valuation `product.category` | Without it no anglo-saxon COGS lines are produced at all | `realtime_category` |
| An `asset_receivable` account coded `12500` | The redirect target; its absence is TC228's subject, not TC224's | per case |
| All five analytic xmlids resolve | `env.ref()` during `_post` — a missing one breaks **every** customer-invoice post | `require_cogs_analytic_accounts` |
| Every `ir.mail_server` deactivated | Posting is preceded by confirming a sales order, which fires `dto_sale`'s automation and its hard-coded d1systems.com recipient list | `require_mail_offline` |

## Adaptations (documented, not assertion-weakening)

1. **SQL reconciliation done through the ORM** (all 14 reconciliation cases), so none needs PostgreSQL credentials and none can report BLOCKED for a missing `pg_*` config. v17 captures and persists; v19 diffs.
2. **TC025 records inventory VALUE, not layer rows.** `stock.valuation.layer` is *expected* to change shape; the value it represents is the invariant.
3. **TC034 records which columns exist and their populations**, so the diff survives v17's two valuation-account columns folding into one on v19.
4. **TC232's MRO read behaviourally.** `type(env['account.move']).__mro__` is not reachable over RPC. All three behavioural assertions the workbook lists are implemented instead, each with its named inverted-order symptom.
5. **TC229 asserts protectively rather than destructively.** Deleting an `ir.model.data` row to observe the `ValueError` live would destroy master data on a shared clone. Instead all five xmlids are asserted to resolve, to point at live accounts, **and** to sit on the plan their name implies — a right-name/wrong-plan account would produce a valid-looking but wrong distribution that no existence check would catch.
6. **TC228 flips a chart-of-accounts code and asserts the restoration.** The flip is snapshotted, restored in a `finally` that cannot raise, and the restoration is then *asserted* — leaving it flipped would misroute every later posting. Run that case on a dedicated clone.
7. **TC233 records rather than assumes.** Whether Odoo emits the COGS/Interim pair at a zero basis or suppresses it is logged; what is *asserted* is what must hold either way.
8. **TC274 needs no tour.** The form arch and the field's ORM `readonly` attribute are read directly, then a real RPC write proves the protection is view-level only — which is the workbook's actual point.

## Verified source facts

| Fact | Where |
|---|---|
| The two renamed/removed anglo-saxon hooks | `stock_account/models/account_move.py` (v17 `:79`, `:310`; v19 `:68`, `:122`, `:163`) |
| `_post` adds the default revenue AD then creates `is_cogs` reversal lines under `skip_invoice_sync` | `dto_account_cogs/models/account_move.py:14-36` |
| `button_draft` / `button_cancel` delete `is_cogs` lines with `dynamic_unlink` + `force_delete` | `:38-60` |
| `for move in self:` then `self.invoice_line_ids` / `self.line_ids` — the E5 defect | `:118`, `:133` |
| The COGS basis branch per order type | `:229-241` |
| The AR redirect to code `12500` | `:206-227` |
| The five `env.ref()` analytic targets | `:160-174`, data at `dto_account/data/account.analytic.account.csv` |
| The AR label builder re-appending `line.name` | `dto_account/models/account_move.py:80-88` |
| `button_draft` blanking receivable labels | `:57-65` |
| `get_sale_orders()` — public | `:92` |
| `AccountMoveLine.create` merging the sale line's distribution | `:180-200` |
| `account.move` ACL rows: invoice `1,1,1,0`; purchase `1,1,1,0`; system `0,0,0,1` | `dto_account/security/ir.model.access.csv` |
| `stock.quant.inventory_quantity_auto_apply` on both versions | `stock_quant.py:102` / `:100` |
| `stock.picking.button_validate` public on both | `stock_picking.py:1131` / `:1413` |

## Run

```bash
venv/Scripts/python.exe -c "from framework import registry; print(len(registry.discover()))"
```
