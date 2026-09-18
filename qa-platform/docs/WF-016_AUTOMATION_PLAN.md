# DATAONE-WF-016 — Vendor Bill Entry & Posting · Automation Plan

| | |
|---|---|
| Workflow | `DATAONE-WF-016` |
| Build order | 18 (Stage 5 — the rebuild, the hardest work in the project) · estimate **13.5 h** |
| Effective risk | **CRITICAL** · fail mode **loud + silent** |
| Depends on | WF-015 |
| Owns | 16 workbook test cases — 4 P0, 6 P1, 5 P2, 1 P3 · `TC050` shared with WF-019 |
| Suite | `tests/wf016/` |
| Modules | `dto_account`, `dto_account_cogs`, `dto_account_workday`, `dto_purchase_stock` |

## Result

| | Count |
|---|---:|
| Implemented | **15** |
| Blocked stub | 1 (`TC278` — the PDF-vs-baseline diff only) |
| Not implemented | 0 |
| **Total** | **16** |

## The finding this suite exists to catch

`dto_account/security/ir.model.access.csv` reuses the **core** xml id:

```csv
account.access_account_payment_register,access.account.payment.register,account.model_account_payment_register,account.group_account_manager,1,1,1,0
```

Reusing a core id **overwrites** the core row — that is how DataOne narrows
Register Payment from `account.group_account_invoice` to
`account.group_account_manager`. If v19 renamed or dropped that id, the CSV
instead creates a **new** row owned by `dto_account` while the permissive
core row survives untouched, and every invoicing user can register payments
again.

No error. No log line. No visible symptom — the views still look right,
because DataOne gates the buttons separately. Delta §5 confirms the CSV
*format* is unchanged, which is not the same thing.

`TEST-WF016-TC269` is the only case that can see it. Beyond the workbook's
steps it asserts two things:

1. `ir.model.data.module` for the row is still `account` — a row owned by
   `dto_account` means the core id moved;
2. no `dto_account`-owned duplicate of the row exists.

That pair distinguishes **overwritten** from **duplicated**, and nothing
else does. `TC267` (the button) and `TC268` (the ACL by behaviour) are both
necessary and neither is sufficient.

## Four more findings recorded

**The gate has no group condition, and that is the point (TC262).**
`dto_account/models/account_move.py:50-58` raises before `super()._post()`
for any `in_invoice` without an attachment, with no group test anywhere.
`sudo()` is not dispatchable over RPC, so the case proves
privilege-independence by **observation**: `base.group_system` and
`account.group_account_manager` are both refused with the identical
message, and the same bill posts for the same user once a document is
attached — which attributes the refusal to the gate and not to permissions.

**One bad record kills a whole batch (TC263).** The check is `any(...)` over
the whole recordset, so posting two bills where only one lacks an
attachment leaves **both** draft and **both** unnumbered — including the
valid one. AP posts in batches at period end and the message names neither
record. §2.3 makes it worse, not better: v19's `_post` returns a recordset,
so multi-move posting becomes *more* likely.

**Widening the gate would stop the business (TC266).** The filter is
`move_type == 'in_invoice'`. WF-012 posts **customer** invoices inside the
delivery-validation transaction, so a gate covering `out_invoice` would
block every shipment DataOne makes. TC266 posts one move of each ungated
type with zero attachments, and adds an `in_invoice` control proving the
gate is alive.

**The precedence is the opposite of what users expect (TC285).** A standing
`account.analytic.distribution.model` rule silently **overrides** an
explicit, user-entered purchase-order coding on a colliding plan, and that
is surfaced nowhere in the interface. The v19 risk is an inversion with no
error: `prepare_analytic_distribution` calls the private core
`_get_distribution(field_values)`, whose `product_categ_id` /
`account_prefix` / `company_id` keys are a private contract (§2.14,
Unknown). If they changed it returns `{}` and every derived line falls back
to the raw source distribution — which is exactly AD-PO. **A TC285 result
equal to AD-PO is that failure**, and the case names it as the signature.

## Per test case

| Group | Workbook TCs | Platform tests | What is proven |
|---|---|---|---|
| Attachment gate | `TC261`–`TC266` | `TEST-WF016-TC261…266` | The exact message before `super()._post()` with no sequence allocated; no privilege bypasses it; the batch is atomic; the stored-compute defect and its recovery; the list column, search filter and form indicator agree with the stored value; and the gate does not widen past `in_invoice` |
| Payment segregation | `TC267`, `TC268`, `TC269` | `TEST-WF016-TC267…269` | The button is hidden per view per user (version-aware); the ACL refuses a direct `call_kw` and no payment exists afterwards; the ACL **row** still overwrites the core one |
| Vendor RMA terms | `TC275`–`TC278` | `TEST-WF016-TC275…278` | Narration equals the company HTML character for character and names all four elements; a user edit does not survive a recompute; a duplicate refreshes from the **current** setting; the partner's language is consulted and an HTML-empty value yields `''`; and the block prints below the totals with its spacing markup, on a credit note but not on a bill |
| Analytic derivation | `TC284`, `TC285` | `TEST-WF016-TC284/285` | The bill line inherits the PO line's coding; the distribution-model rule wins on a colliding plan while the non-colliding key survives; no root plan exceeds 100 % |
| Reconciliation | `TC050` | `TEST-WF016-TC050` | The whole reconciliation graph — partials, full groups, the flag distribution, the **exact pairing** as a checksum, the net-to-zero invariant, and the payment population |

## Environment dependencies — every one probed, never assumed

| Requirement | Why | Probe |
|---|---|---|
| `dto_account` installed | `account.move.have_attachment` is the field the gate reads; without it every negative passes **vacuously** | `require_dto_account` |
| `purchase` installed | TC261/TC284/TC285 build their bills from a confirmed PO and a validated receipt | `require_purchase` |
| `res.company.vendor_refund_narration` non-empty | `get_default_narration` returns `''` for an HTML-empty value *by design* (TC277 step 4), so an empty setting makes every RMA assertion vacuous | per case |
| Two analytic plans | A colliding-plan distribution cannot be built on a single-plan database, and TC284/TC285 are about **precedence** | `_two_plans` |
| The five `dto_account` analytic xmlids | Without them a customer invoice fails to post for a *different* reason and TC266 would misread it as the gate firing | inside TC266 |
| An authenticated web session | TC278 renders `/report/html/account.report_invoice/<id>` — the same template the PDF comes from | inside TC278 |

## Adaptations (documented, not assertion-weakening)

1. **TC050 through the ORM, not raw SQL**, so it never reports BLOCKED for a
   missing `pg_*` config. Step 4's *exact pairing* is compared as a
   **checksum** of the sorted `(debit_move_id, credit_move_id, amount)`
   triples plus the amount multiset — raw ids are not comparable across
   databases, but a re-pairing that preserves totals must still be caught.
   Step 5's net-to-zero rule is an **anchor** on both versions, not a diff:
   a group that does not net to zero is broken regardless of the upgrade.
2. **TC265 and TC267 are TOUR candidates implemented as rendered-arch reads
   plus a real domain execution.** That covers every observation their
   expected results list, deterministically. A browser tour would add
   nothing an arch read does not already prove and would be the flakiest
   thing in the wave.
3. **TC267 reads `ctx.env.version` to compute its own expected view set.**
   This is the one legitimate exception in `AUTOMATION_CONVENTIONS.md` — the
   case's *subject* is the version delta. v17 expresses the restriction in
   three views; v19 removed the button from both **lists**
   (`action_register_payment` occurs twice in
   `account/views/account_move_views.xml`, `:734` and `:746`, **both inside
   the form**), so DataOne deleted its two list inherits and gates both form
   buttons **by id**. On v19 the case additionally asserts *both* buttons
   are hidden from a Billing user — gating only the first would leave the
   with-outstanding-credits button on core's wider group.
4. **TC262 step 7 asserts privilege-independence by observation**, because
   `sudo()` cannot be dispatched over `/web/dataset/call_kw`.
5. **TC264 triggers the recompute with a write on the move**, the way the UI
   does, because `_compute_have_attachment` is private and refused by
   `check_method_name`.
6. **TC276 and TC277 both mutate `res.company.vendor_refund_narration`.**
   Each snapshots it, restores it in a `finally` that cannot raise, and then
   **asserts** the restoration — a half-restored company would silently
   change every credit note issued afterwards.
7. **TC278's HTML half is asserted and passes first**; only the
   pixel/text diff against a Phase 0a baseline PDF is blocked, with the
   reason naming what is missing.
8. **Every analytic comparison is by resolved account set and root plan**,
   with the raw key strings logged. The raw-shape comparison across versions
   is the workbook's `TC259` and is not duplicated here.

## Verified source facts

| Fact | Where |
|---|---|
| The gate, its exact message and its `in_invoice` filter | `dto_account/models/account_move.py:50-58` |
| `have_attachment` — `store=True`, `@api.depends('attachment_ids')` | `:14-31` |
| `_compute_narration` skipping everything but `in_refund` | `:20-26` |
| `copy_data` refreshing from the **current** company | `:33-42` |
| `get_default_narration` — public, `partner.lang` first, `''` for HTML-empty | `:44-48` |
| The bill line inheriting `purchase_line_id.analytic_distribution` at create | `:280-306`, `@api.model_create_multi` |
| `prepare_analytic_distribution` and the private `_get_distribution` contract | `:192-250` |
| The payment-register ACL row reusing a **core** xml id | `dto_account/security/ir.model.access.csv` |
| Both v19 form buttons gated **by id**; the two list inherits deliberately deleted (D-21) | `dto_account/views/account_move_views.xml` |
| `have_attachment` as `optional="show"`; the `filter_have_attachment` search filter | same file |
| The Workday vendor-bill export filtering on `have_attachment` | `dto_account_workday/models/account_move.py:69` |
| `res.company.vendor_refund_narration` and its shipped RMA default | `dto_account/models/res_company.py` |

## Run

```bash
venv/Scripts/python.exe -c "from framework import registry; print(len(registry.discover()))"
```
