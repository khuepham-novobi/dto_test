# DATAONE-WF-012 — Auto-Invoicing on Delivery Validation · Automation Plan

| | |
|---|---|
| Workflow | `DATAONE-WF-012` |
| Build order | 17 (Stage 5 — the rebuild, the hardest work in the project) · estimate **9.5 h** |
| Effective risk | **CRITICAL** · fail mode **silent** |
| Depends on | WF-011 |
| Owns | 3 workbook test cases — **2 of them P0** |
| Suite | `tests/wf012/` |
| Modules | `dto_sale_stock`, `dto_mrp_account` |

## Result

| | Count |
|---|---:|
| Implemented | **3** |
| Blocked stub | 0 |
| Not implemented | 0 |
| **Total** | **3** |

## The finding this suite exists to catch — and why it is mostly about restraint

Nothing in the auto-invoicing mechanism breaks on v19. Delta §8 confirms all
four methods in the chain are unchanged:

| Method | v19 status |
|---|---|
| `stock.picking._action_done` | unchanged |
| `sale.order._create_invoices` | unchanged |
| `sale.order._prepare_invoice` | unchanged |
| `account.move.action_post` | unchanged |

The code keeps running. What changes is **what it produces** — §2.2 renamed
`_stock_account_prepare_anglo_saxon_out_lines_vals` and removed
`_stock_account_get_anglo_saxon_price_unit`, so the COGS basis and the
Interim analytic distribution silently empty inside an invoice that still
posts, still balances and still gets a number.

That makes WF-012 the workflow where **every green signal is misleading**:

- the operator's click succeeds,
- the picking is `done`,
- the invoice number is allocated,
- the smart button shows 1,

and the general ledger is wrong.

So `TEST-WF012-TC288` and `TC289` deliberately assert the **trigger only**.
Both dump the resulting journal items to the execution log and hand them to
`tests/wf013`, exactly as the workbook's own step 10 instructs. **A green
TC288 with a failing `TEST-WF013-TC222` is the defect.** Neither suite is
acceptance evidence on its own, and that sentence belongs in the sign-off.

## Three more findings recorded

**The filter is the control (TC289).** `dto_sale_stock/models/stock_picking.py`:

```python
orders = self.sale_id.filtered(lambda r:
    r.order_type in ['project', 'inventory', 'cost_center']
    and r.invoice_status == 'to invoice')
```

Two halves, both pinned. `buy` must stay on the manual draft path — widening
the filter would push unreviewed trade invoices straight to customers. And
the `invoice_status` term is the idempotence guard, so a second delivery on
an already-billed order produces no second invoice.

**No UI signal, asserted not assumed (TC288 step 9).** `button_validate`
returns no notification, no wizard and no message naming the invoice. The
warehouse operator cannot know a posted journal entry was created by their
click. That is *why* the accounting overrides can regress unnoticed, so the
absence is asserted rather than merely observed.

**E7 aborts shipments, and the fix is `noupdate`-protected (TC290).** The
shipment server action evaluates `'IRM' in order.memo_to_suppliers`;
`memo_to_suppliers` is an optional Text field, so the ORM yields `False` on
a NULL column and `'IRM' in False` raises `TypeError` — **inside the
`button_validate` transaction**, which aborts the delivery. Nothing ships
and nothing is invoiced. The three records live under `<data noupdate="1">`,
so a module upgrade does **not** refresh them;
`dto_sale_stock/migrations/19.0.0.2/post-migrate.py` exists solely to push
the `or ''` guard onto a database that already has them.

TC290 therefore reads the **live** `ir.actions.server.code` from the
database, records whether the guard is present, and asserts the behaviour
that must follow from what it found. Only a *mismatch* between the code and
the behaviour is a failure.

## Per test case

| Group | Workbook TCs | Platform tests | What is proven |
|---|---|---|---|
| The trigger | `TC288` | `TEST-WF012-TC288` | Picking done with `date_done`, moves relieved, exactly one `account.move`, posted with a real sequence number, `invoice_status` moved off *to invoice*, no UI signal, journal items handed to VAL |
| The filter | `TC289` | `TEST-WF012-TC289` | `inventory` and `cost_center` auto-invoice posted; `buy` produces none and stays *to invoice*; its manual invoice lands draft; re-delivery produces no second invoice |
| The notification | `TC290` | `TEST-WF012-TC290` | Live server-action code, recipient mapping per order type, subject contract, `date_done` as `%m/%d/%Y`, non-empty Reference # (with an analytic variant asserting its content), Delivery Slip attachment, the IRM append, the empty-memo abort, and no email for an incoming picking or a picking with no sale order |

## Environment dependencies — every one probed, never assumed

| Requirement | Why | Probe |
|---|---|---|
| `dto_sale` + `dto_sale_stock` installed | `sale.order.order_type` is the field the filter branches on; without it every assertion is vacuous | `require_auto_invoice_stack` |
| All five `dto_account` analytic xmlids resolve | `dto_account_cogs._post` calls `env.ref()` on them, **inside the delivery transaction** — a missing one blocks the *shipment*, not just the invoice | `require_cogs_analytics` |
| Every `ir.mail_server` deactivated | Validating fires the shipment automation's `send_mail(force_send=True)` against a hard-coded d1systems.com list | `require_mail_offline` |
| A real-time-valuation `product.category` | Not required for WF-012's own assertions, but without one no anglo-saxon pair is produced and the moves handed to WF-013 exercise nothing | `realtime_category` (warns, does not block) |
| Mail genuinely offline for TC290 | `mail.template.auto_delete=True` — a mail that **sends** is unlinked and its recipients become unreadable. A missing `mail.mail` is reported as BLOCKED naming that cause | inside TC290 |

## Adaptations (documented, not assertion-weakening)

1. **TC288/TC289 deliberately do not assert the journal entry.** This is the
   workbook's own instruction and the single most important design decision
   in the suite. See the finding above.
2. **TC290 is implemented rather than left `MANUAL_ONLY`** — a deviation
   from the wave's feasibility policy, recorded here. On a mail-offline
   clone the evidence is machine-readable: a mail that cannot send stays in
   state `exception` with `email_to`, `subject`, `body_html` and
   `attachment_ids` intact. The half that stays manual is a human reading a
   *delivered* inbox.
3. **TC290 does not assume which code the database holds.** Guard present →
   the empty-memo delivery must complete. Guard absent → it must abort with
   `TypeError` and leave the picking `assigned` with no invoice.
4. **Reference # is asserted in two steps.** The fixture orders carry no
   analytic distribution, so an empty block is *correct* for them; step 4
   asserts the block renders at all, and step 4b supplies a distribution and
   asserts its content. Separating them stops a legitimately empty block
   being read as §2.14's silent failure.

## Verified source facts

| Fact | Where |
|---|---|
| The auto-invoice filter and its two terms | `dto_sale_stock/models/stock_picking.py._action_done` |
| The delivery-validation group gate (v19 replaced `user_has_groups()` with `self.env.user.has_group()`) | `dto_mrp_account/models/stock_picking.py.button_validate` |
| The recipient mapping per order type | `dto_sale_stock/data/base_automation_data.xml:44-52` |
| The IRM append and the empty-memo guard | same file, `'IRM' in (order.memo_to_suppliers or '')`, under `<data noupdate="1">` |
| Subject contract, Delivery Slip attachment, `auto_delete=True` | `dto_sale_stock/data/mail_template_data.xml` — `mail_template_delivery_validated`, `report_template_ids` → `stock.action_report_delivery` |
| Reference # built by parsing comma-joined analytic ids with `int()` | the server action's `get_analytic_accounts()` helper |
| The migration that pushes the guard onto an existing database | `dto_sale_stock/migrations/19.0.0.2/post-migrate.py` |

## Run

```bash
venv/Scripts/python.exe -c "from framework import registry; print(len(registry.discover()))"
```
