# DATAONE-WF-008 — Manufacturing Cost Absorption (Labour and Overhead) · Automation Plan

| | |
|---|---|
| Workflow | `DATAONE-WF-008` |
| Build order | 19 (Stage 5 — the rebuild, the hardest work in the project) · estimate **37.5 h** |
| Effective risk | **CRITICAL** · fail mode **loud** at the build, **silent** in the numbers |
| Depends on | WF-007 |
| Owns | 21 workbook test cases — **16 of them P0** |
| Suite | `tests/wf008/` |
| Modules | `dto_mrp_account`, `dto_account` |

## Result

| | Count |
|---|---:|
| Implemented | **20** |
| Blocked stub | 1 (`TC256` — the post-fix assertion only) |
| Not implemented | 0 |
| **Total** | **21** |

## This is a rebuild, not a port — and this suite is its specification

Delta §2.1 replaced the valuation engine wholesale:

| v17 | v19 |
|---|---|
| `stock.move._generate_valuation_lines_data(..., svl_id, description)` | **does not exist**; `_get_account_move_line_vals()` returns a list of two dicts |
| one journal entry per **move** | one entry per **batch** of moves |
| `stock.valuation.layer` | **removed**; value moves to `stock.move.value` |
| `stock.move.account_move_ids` (One2many) | `stock.move.account_move_id` (Many2one, inverted) |
| category stock accounts | **removed**; `_get_product_accounts()` returns only `stock_valuation` + `stock_variation` |

The `rslt[f'debit_{account}_{description}']` composite-key idiom that carries
**both** the labour pair (F169) and the per-pool overhead pairs (F170) has
**no analogue in v19**.

So until the rebuild lands, `TC234`, `TC235`, `TC236`, `TC238`, `TC241` and
`TC243` are expected to **FAIL** on the line count and on the pairs. Those
failures are not noise — they are the specification the rebuild has to
satisfy, expressed as executable assertions with the exact amounts, labels
and analytic overlays each line must carry.

## The clearest silent money failure in the project — and it is directly testable

`dto_mrp_account/models/mrp_workcenter_productivity.py`:

```python
def create(self, vals):                     # NOT @api.model_create_multi
    if 'workcenter_id' in vals:             # False for a LIST
        ...
        if open_time_sheet:
            raise UserError(...)
```

§2.16 confirms `create` **always** receives a list on v19, so
`'workcenter_id' in [{...}]` is `False` and the concurrent-timesheet guard
never fires. Nothing raises, nothing logs; operators run overlapping
timesheets and capitalised labour rises.

The canary is reachable without any harness trickery: `rpc.create(model,
values)` dispatches `create(values)` **verbatim**, so `TEST-WF008-TC248`
exercises `create({dict})` *and* `create([{dict}])` against the same
database in the same test. Step 6 is that comparison, and it also records
the money at stake per occurrence.

## Five more findings recorded

**The two switches live in different models (TC235 / TC236 / TC237).** The
overhead gate is in `mrp.production._calc_production_overhead_cost`; the
labour gate is in `stock.move._generate_valuation_lines_data`. Two
independent code paths, so a rebuild preserving one may drop the other with
no error. TC237 — both switches off — is the **null hypothesis**: the
difference between its entry and TC234's is exactly what the customisation
is worth, and it is the only case that would detect a rebuild posting
labour or overhead unconditionally.

**The labour/overhead asymmetry is real and undocumented (BR-3, TC240 /
TC242).** Overhead is capitalised into unit cost (released to P&L when the
good is **sold**); labour is reclassified into WIP but **not** capitalised.
TC240 measures against a control MO run with both switches off, so the
asserted number is a *difference* that survives §2.1's rebuild of the base —
and it names four failure signatures individually:

| Uplift per unit | Meaning |
|---|---|
| 6.00 | correct |
| 36.00 | labour was capitalised too |
| 30.00 | labour replaced overhead |
| 12.00 | overhead was applied twice |
| 0.00 | F168 did not run |

TC242 proves the `cost_method in ('fifo','average')` gate and **records**
the unrelieved WIP residual a standard-cost product leaves behind — WF-008
Open Question 1, which is the Controller's decision and not QA's.

**The skip and the freeze are opposite behaviours on the same record (TC238
/ TC244).** A pool whose rounded overhead is zero is dropped from the entry
by `currency.is_zero` but is **still** written into
`stored_overhead_cost_settings`, because `_post_inventory` has no switch
check and no yield check (WF-008 A1, also proved by TC236 and TC237 with the
switches off). TC238 adds the distinguishing control the workbook asks for:
a pool whose `expense_account_id` did **not** migrate (§2.16 removed
`ir.property`; company-dependent fields became stored jsonb) produces the
same "no lines" result as a zero rate. The case records whether the entry
alone can tell them apart — if it cannot, the port must add a validation.

**The snapshot is keyed by pool NAME (TC244 step 7, TC246 step 9).**
`stored_overhead_cost_settings` maps `setting.name → percentage`, so
renaming a pool orphans every historical MO's frozen rate with no error and
no migration. TC246 renames it deliberately, asserts the completed MO's
Overview does not crash, records what it shows, and asserts the **posted**
overhead is unaffected.

**The MO Overview is served by two branches with different key types
(TC245).** `_get_operations_data` (forecast) iterates recordset keys and
builds its label from `setting.name`; `_get_finished_operation_data`
(actual) iterates **string** keys, because by then the snapshot exists. Both
produce the same visible label; only the key type differs. That asymmetry is
undocumented, and it is the specification a v19 rebuild must match — so
TC245 records it, and distinguishes the **silent** failure (report still
renders, `Overhead:` row gone, nothing raises) from the **loud** one (a
changed dict shape raising `KeyError`).

## Per test case

| Group | Workbook TCs | Platform tests | What is proven |
|---|---|---|---|
| The gate entry | `TC234` | `TEST-WF008-TC234` | Six lines; labour 300.00 and overhead 100.00 with their exact labels; the labour credit on the **category's** account; overlays on the credit legs only; balanced; snapshot written; F183 stat button |
| Switch matrix | `TC235`, `TC236`, `TC237` | `TEST-WF008-TC235…237` | Each half stands alone (4 lines each); both off → 2 lines and no uplift; A1's unconditional snapshot in all three |
| Configuration edges | `TC238`, `TC239` | `TEST-WF008-TC238/239` | Zero-yield skipped but frozen, and a mis-migrated account distinguished from it; the exact `UserError`, full rollback, the remedy, and the switch gate |
| Capitalisation | `TC240`, `TC242` | `TEST-WF008-TC240/242` | +6.00/unit against a control, four failure signatures, no double count, the average variant; standard-cost gets the pairs but no uplift and leaves a recorded WIP residual |
| Multi-pool | `TC241` | `TEST-WF008-TC241` | Eight lines, two separate pairs, distinct overlays, and — on a **shared** expense account — still two credit lines, not one merged 90.00 |
| Scrap | `TC243` | `TEST-WF008-TC243` | The scrap entry carries no absorption; the finished entry is unaffected; both halves of the two-condition guard |
| Rate freezing | `TC244`, `TC246` | `TEST-WF008-TC244/246` | Empty before, populated after, all pools, immutable under a rate change, `copy=False`, ordering, the E8 guard; and a rate change that is **prospective only**, with the rename probe |
| Labour controls | `TC247`, `TC248` | `TEST-WF008-TC247/248` | The per-unit cap, its three boundaries, its switch gate and the capped charge — with no operator notification; and the create-list canary with both positive controls and the E9 defect |
| Analytic attribution | `TC249`, `TC250`, `TC252`, `TC253` | `TEST-WF008-TC249/250/252/253` | Propagation to every line with the two overlays winning on their credit legs **and** the analytic ledger actually indexing it; the manual-MO control that makes TC249 interpretable; location tagging; and the two-virtual-location bail-out, with the hole quantified |
| Boundary | `TC256` | `TEST-WF008-TC256` | Both unguarded divisions exercised with a non-zero numerator, transaction integrity asserted, incidence measured — then BLOCKED on the guard the port must add |
| Baseline | `TC257` | `TEST-WF008-TC257` | 20 real MOs' entries normalised to a shape-independent key and compared to the cent, plus frozen rates and `price_unit` |

## The one fixture that cannot be namespaced

`dto_mrp_account.mrp.production.button_mark_done` matches
`workcenter_id.name == 'Packaging'` — a **literal in the product code**. A
work centre named `WF008 Packaging` does not satisfy it, and every MO in the
suite would be blocked at completion.

The fixture therefore creates a work centre named **exactly** `Packaging`,
carrying the suite marker in its `code`. Convention rule 3 is satisfied a
different way: nothing pre-existing is ever written to, and the sweep
matches only work centres whose `code` starts with the marker. **This is the
suite's single documented deviation** and it is recorded here rather than
buried in a helper.

## Environment dependencies — every one probed, never assumed

| Requirement | Why | Probe |
|---|---|---|
| `dto_mrp_account` fully installed | Each of `mrp.overhead.cost.setting`, the two company switches, the category labour account and `stored_overhead_cost_settings` is probed **by name** with a reason — §2.16 and §2.1 are both ways this surface disappears silently at install | `require_absorption_stack` |
| Real-time valuation | Without it an MO produces no journal entry at all and every assertion is vacuous | `require_mrp_valuation` |
| A usable expense account (two for TC241) | The credit legs have nowhere to post; TC241 needs distinct accounts per pool to observe the separation | `standard_environment`, inside TC241 |
| A work centre named `Packaging` with non-zero duration | `button_mark_done` refuses otherwise | fixture |
| `employee_cost` resolvable | A **stored compute** from `employee_id.hourly_cost` falling back to `workcenter.employee_costs_hour` (enterprise `mrp_workorder:61,68`) — the fixtures set **both** | `ensure_employee` / `ensure_workcenter` |
| At least one analytic plan | TC249/TC250/TC252/TC253 cannot construct a distribution without one | per case |
| `stock.location.location_analytic_distribution` + a production and an inventory location | F154's two branches | TC252/TC253 |
| **Real production data** | TC257 is the Controller's acceptance evidence; a fixture cannot substitute for it | inside TC257 |

## Adaptations (documented, not assertion-weakening)

1. **Private methods are never re-implemented.**
   `_generate_valuation_lines_data`, `_cal_price`,
   `_calc_production_overhead_cost`, `_get_production_component_cost` and
   `_post_inventory` are all refused by `check_method_name` (v17
   `odoo/models.py:145`, v19 `odoo/orm/utils.py:69`). Every case asserts what
   the **public** `button_mark_done` produced, and where the workbook asks
   for instrumentation the observable equivalent is asserted and the
   substitution is stated in the test docstring.
2. **TC244 step 2 is asserted by consequence, which is stronger.** The
   workbook wants the snapshot read at the instant the entry is built. That
   MO's snapshot was **empty** and it nonetheless posted overhead at the
   live rate — which can only happen if the entry came from live settings.
3. **The core valuation pair is asserted relative to the captured component
   value, never pinned at the workbook's absolute.** Core decides that
   number and §2.1 rebuilt how; pinning it would report a **core** change as
   a DataOne regression. Labour and overhead **are** asserted absolutely,
   because DataOne's own code computes them from inputs the fixture fully
   controls.
4. **Every analytic comparison is by resolved account set**, never by raw key
   string (§2.14 leaves the v19 format Unknown). TC249 step 15 **logs** the
   literal key strings for the baseline file the test-data catalogue asks
   for; the raw-shape comparison across versions is the workbook's `TC259`.
5. **The journal entry is reached through `common.valuation_link_field()`**,
   which resolves v17's `account_move_ids` or v19's `account_move_id`. No
   test body carries a version branch; a third shape changes one helper.
6. **Overhead pools are swept first and unconditionally.** A leftover pool
   adds a pair to every subsequent entry — the workbook names this as the
   suite's most common cross-case contamination.
7. **Every case that mutates shared state restores it and then asserts the
   restoration** — the two company switches, a pool's rate and name, a
   pool's expense account, a work centre's `use_time_restrict`, a location's
   analytic tag. A half-restored environment becomes a visible failure
   rather than a silent invalidation of every later case.
8. **TC245 step 11 and TC246's rename probe stop short of editing
   application source** (convention rule 1). The silent-failure signature is
   documented and made detectable from the cases' own output: a PASS on
   "the Overview renders" together with a FAIL on "Overhead rows == 1".
9. **TC256 reports BLOCKED on purpose.** The workbook's step 9 says the
   post-fix assertion "is expected to fail and must be marked Blocked" until
   a zero guard is added. Everything before it passes; asserting the
   post-fix behaviour now would report a known **v17** defect as an upgrade
   regression.
10. **TC257's SQL is replaced by ORM reads** and its MO selection is ordered
    by `name` rather than by posted valuation, so both databases compare the
    same **frozen** population — re-deriving "the top 20 by valuation" at
    compare time is the exact failure the freeze exists to prevent.

## Verified source facts

| Fact | Where |
|---|---|
| The six-line entry and the composite-key injection | `dto_mrp_account/models/stock_move.py` — `_generate_valuation_lines_data`, `_append_account_move_line`, `rslt[f'debit_{debit_account_id}_{description}']` |
| The exact missing-labour-account message | same file — *"Please define Expense Account - Labor Cost account on your product category before processing this operation."* |
| The labour figure: `sum(time.employee_cost * time.duration / 60)` over every work order | same file |
| The two overlays merged over the MO distribution | same file — `{**mo_analytic_distribution, **(overlay or {})}` |
| The scrap guard's **two** conditions | same file — `if production and not self.scrap_id and not self.scrapped` |
| `currency.is_zero` skipping a zero-yield pool | `dto_mrp_account/models/mrp_production.py._calc_production_overhead_cost` |
| The unconditional, switch-free snapshot keyed by pool **name** | `._post_inventory` |
| The cost-method gate and the unguarded division | `._cal_price` — `cost_method in ('fifo','average')`; `price_unit += overhead_cost / quantity` |
| The Packaging guard | `.button_mark_done` |
| The pool model, its company-dependent account and its two constraint messages | `dto_mrp_account/models/mrp_overhead_cost_setting.py` |
| The category's labour account and Json overlay | `dto_mrp_account/models/product_category.py` |
| The three work-centre controls (threshold default 120, minutes **per unit**) | `dto_mrp_account/models/mrp_workcenter.py` |
| The un-decorated `create` and the `strptime`-based cap | `dto_mrp_account/models/mrp_workcenter_productivity.py` |
| `employee_cost` as a stored compute from `hourly_cost` | enterprise `mrp_workorder/models/mrp_workcenter.py:61,68` |
| The two Overview branches and their differing key types | `dto_mrp_account/models/mrp_report_mo_overview.py` |
| `get_report_values` public on both versions | `mrp/report/mrp_report_mo_overview.py` v17 `:16`, v19 `:17` |
| The location bail-out guard | `dto_account/models/stock_move.py` — `if len(virtual_locations) != 1 or not ...` |
| The v19 inverted valuation link, already in the ported tree | `dto_mrp_account/models/mrp_production.py._compute_account_move_ids` |

## Run

```bash
venv/Scripts/python.exe -c "from framework import registry; print(len(registry.discover()))"
```
