# Product defects found by the QA suite — for the development team

Source: full regression run **RUN-1DE0AD94** on `d1v19`, 337 tests, 2026-09-19.
Database: restored from `d1systems-uat-38267540_2026-09-18_130212_exact_fs.zip`.
Custom source: `dto_custom` @ `3467e3d` (branch UAT).

Everything below is a **product** issue. Harness and fixture problems found
in the same run were fixed in the QA repo and are not listed here.

Nothing in this document has been changed in the application source. Each
item gives the file and line, the exact exception or observed behaviour, and
which tests it blocks — so it can be reproduced without the QA platform.

---

## Severity 1 — code paths that raise on v19

These four have never executed on v19. Each is a `TypeError` or
`AttributeError` inside custom code, which means no v19 run has reached that
line since the port.

### 1.1 Editing a purchase order line raises — `product_uom` was renamed

**`project-addons/dto_purchase_stock/models/purchase_order_line.py:98-103`**

```python
line.order_id.state in ['purchase', 'done'] and \
    float_compare(
        line.product_qty,
        line.qty_received,
        precision_rounding=line.product_uom.rounding    # <- :102
    ) == 0
```

```
purchase.order.line.write failed:
'purchase.order.line' object has no attribute 'product_uom'
```

v19 renamed `purchase.order.line.product_uom` to `product_uom_id`. The
project already knows: `project-addons/dto_purchase/tests/test_wf014_open_flags.py:165-168`
records the rename in a comment — *"it is purchase.order.line.product_uom
that was renamed to product_uom_id, not this one"* — but this call site was
missed.

**There is a second defect in the same expression.** Line 98 tests
`state in ['purchase', 'done']`. v19 removed the `done` state from
`purchase.order`; the selection is now
`draft / sent / to approve / purchase / cancel`. The `'done'` term
therefore matches nothing and the guard silently covers half of what it
was written to cover — the same class of silent regression the Vendor
Delivery Report had (see 3.3).

**Impact** — writing any purchase order line that reaches this guard
raises. It is reached when changing Expected Arrival on a confirmed order,
which is routine.

**Blocks** `TEST-WF015-TC202`, `TC203`, `TC204`, `TC205`.

**Suggested fix** — `line.product_uom_id.rounding`, and replace the
`'done'` term with a `locked` check (v19 carries `purchase.order.locked`
as a plain Boolean).

---

### 1.2 Marking an SFTP file failed raises when the caller passes a string

**`novobi-addons/novobi_sftp_connection/models/sftp_file.py:169-178`**

```python
def mark_sync_failed(self, process_date, message=None):
    ...
    date_deadline=process_date.date(),        # <- :178
```

```
sftp.file.mark_sync_failed failed: 'str' object has no attribute 'date'
```

`process_date` arrives as a string from at least one caller, and
`.date()` is only valid on a `datetime`.

**Impact** — the failure path of the SFTP connector itself fails. A file
that could not be processed cannot even be **marked** as failed, so the
error is lost rather than recorded on the record where an operator would
look for it.

**Blocks** `TEST-WF018-TC300`.

**Suggested fix** — normalise at the top of the method
(`fields.Datetime.to_datetime(process_date)`), which accepts both.

---

### 1.3 Printing a packing slip raises

**`project-addons/dto_purchase_stock/models/stock_picking.py:87-91`**

```python
mimetype = self.env['ir.attachment']._compute_mimetype({
    'name': record.packing_slip_attachment_name
})
```

```
stock.picking.action_print_attached_packing_slip failed:
unhashable type: 'list'
```

**Impact** — the Print Packing Slip button raises for the user. Worth
checking `_compute_mimetype`'s v19 signature; the v17 call shape appears
not to survive.

**Blocks** 3 cases in WF-015.

---

### 1.4 `get_default_narration` receives an int where a recordset is expected

**`project-addons/dto_account/models/account_move.py:44`**

```python
def get_default_narration(self, partner, company=None):
    ...
    lang = partner.lang or self.env.user.lang
```

```
account.move.get_default_narration failed:
'int' object has no attribute 'lang'
```

Both call sites in the same file pass a recordset (`:26`, `:39`), so the
int arrives from a third caller — worth finding, because the method is
public and therefore reachable from anywhere.

**Blocks** 1 case in WF-016.

---

## Severity 2 — wrong results, no error

Worse than the above in practice: these produce a plausible-looking answer.

### 2.1 Importing a closed purchase order creates receipt pickings

**`project-addons/dto_data_migration/models/purchase_order.py:48-49`**

Measured: importing ONE closed purchase order leaves receipts behind, in
state `assigned`:

```
WH-IN-03729   origin=WF026-<token>-PO-001   Receipts   assigned
```

The sales-order half of the suppression layer works —
`TEST-WF026-TC400` proves an imported SO generates no picking, no move and
no invoice, against a confirmed live control that does. The purchase half
does not.

The cause is likely Stage 7's own change. v17 imported a closed PO with
`state='done'`, which creates no receipt. v19 removed that state, so the
port writes `state='purchase'` plus `locked=True` (D-new-15) — and
`purchase` is a state the stock layer acts on. The port comment reasons
carefully about `locked` being writable in the same `create()`; it does not
mention receipts.

**Impact at scale** — the v17 baseline counts **2,388 historical purchase
orders** (`database/STAGE7-PHASE0A-BASELINE-v17.txt:5-11`). Importing them
puts thousands of receipts into the warehouse's to-do list, in `assigned`
state, for orders closed years ago — and the import reports success.

**Recorded by** `TEST-WF026-TC398` (failing deliberately).

---

### 2.2 Receipt Number's order is non-deterministic and stored

**`project-addons/dto_data_migration/models/purchase_order.py:14-16`**

```python
receipt_number_lst = set(res.order_line
                         .filtered(lambda l: l.receipt_number)
                         .mapped('receipt_number'))
res.receipt_number = ', '.join(receipt_number_lst)
```

A `set` has no defined iteration order, and Python randomises string
hashing per process — so the join order varies between server restarts.
Three lines carrying `RCPT-A, RCPT-B, RCPT-A` read back as
`'RCPT-B, RCPT-A'`.

The field is `store=True`, so whatever order happened at compute time is
**persisted**. A person reads it to match a vendor's paperwork.

**Fix** is one word: `sorted()`, or `dict.fromkeys()` to keep line order.

**Recorded by** `TEST-WF026-TC399`, `TC401`.

---

### 2.3 Nobody holds the group that gates the Reports app

**`project-addons/dto_reports/data/groups.xml:5`**

`dto_reports.reports_module` ("Review reports") has **zero members** on
d1v19. For contrast, "Cost Analysis View" ships with admin, elove, jsolls,
klotspeich and `__system__`.

It is also hidden: D-new-14 deleted the group's `category_id` line for v19
(`res.groups.category_id` became `privilege_id`), and a group carrying
neither does not appear in the Settings user form. So nobody holds it and
nobody can be given it through the UI — **all 14 Reports menus are
unreachable by every user, including admin**. On v17 the group carried a
category and could be ticked.

The gate itself works: `TEST-WF027-TC013` grants the group to a test user
and the menus become reachable, then revokes it.

**Recorded by** `TEST-WF027-TC013` (failing deliberately).

---

### 2.4 The Time Fixed filter exists but cannot be used

**`dto_mrp_account`, view `timesheet.search.view.dto_mrp_account`**

```xml
<filter string="Time fixed" name="" domain="[('time_fixed', '=', True)]"/>
```

The `name` attribute is **empty**. An unnamed filter cannot be referenced
by `search_default_*`, so no action can switch it on, and Odoo has nothing
to key it by when saving or restoring a search.

**Impact** — isolating the timesheet records whose duration was capped is a
manual click every time, and cannot be made the default view of any menu.

**Recorded by** `TEST-WF027-TC384`.

---

### 2.5 `date_processed` is a stored compute with no dependencies

**`project-addons/dto_reports/models/stock_move.py:6-10`**

`stock.move.date_processed` is declared `store=True` with **no**
`@api.depends`. A stored compute without dependencies is written once, at
create, and never recomputed.

Every figure in the Feet of Cable Cut/Processed report is bucketed by it.
If a move's real processing date later changes, the report keeps the
original and says nothing.

**Recorded by** `TEST-WF027-TC380` (passing, with the finding logged).

---

## Severity 3 — v19 API changes still to be worked through

### 3.1 `You cannot set more than 1 lot`

`mrp.production` — v19 turned `lot_producing_id` into the many2many
`lot_producing_ids`. Blocks `TEST-WF010-TC346`.

### 3.2 `Expected singleton` on the quality-check wizard

`quality.check.action_open_quality_check_wizard` is called with a
multi-record set. Blocks 1 case in WF-015.

### 3.3 `KeyError: 'traceback'`

A wizard result is read for a `traceback` key that v19 does not provide.
Blocks `TEST-WF020-TC301`. Known since the earlier triage.

---

## Severity 4 — fragile by construction, not currently failing

### 4.1 The Packaging completion gate matches a work centre by literal name

**`project-addons/dto_mrp_account/models/mrp_production.py:134-137`**

```python
def button_mark_done(self):
    for order in self:
        if sum(order.workorder_ids.filtered(
                lambda workorder: workorder.workcenter_id.name == 'Packaging'
               ).mapped('duration')) == 0:
            raise UserError(_('You cannot finish a manufacturing order '
                              'without any work done in Packaging. 
 '
                              'all work orders have 0 duration.'))
```

Byte-identical to v17 (`dto_17_custom/.../mrp_production.py:95-98`), so this
is **not** a v19 regression. It is reported because the QA suite met it for
the first time when Stage 7 deployed the module, and two things about it
are worth a decision rather than a surprise later.

**It is currently working.** Measured on d1v19, completed MOs by year:

| `date_finished` | with a Packaging work order | with no work order at all |
|---|---|---|
| 2026 | 4,639 | 90 (all `is_historical_data`) |
| 2025 | 5,993 | 3 |
| 2024 | 732 | 6,808 |
| 2023 and earlier | 0 | 28,874 |

There is a clean cutover in 2024. The 35,685 older MOs predate the gate;
they are not evidence against it.

**Point 1 — the name is a literal string.** `w.name == 'Packaging'` is not
an xmlid, not a flag on `mrp.workcenter`, and not a company setting. So:

* renaming the work centre in the UI silently disables **every** MO
  completion on the database;
* the same happens under a translation, because `mrp.workcenter.name` is a
  translated field and `==` compares the value in the acting user's
  language;
* a second company whose packaging centre is named anything else can never
  complete an MO, with no way for an administrator to see why.

d1v19 currently carries **42 active work centres named exactly
`Packaging`** in one company. The gate needs only one, so this is not
breaking anything — but it does mean the string is load-bearing in 42
places and guarded in none.

*Suggested* — a Boolean on `mrp.workcenter` (`is_packaging`) or an xmlid,
either of which survives a rename and a translation.

**Point 2 — the message is wrong when there are no work orders.**
`sum()` of an empty recordset is `0`, so an MO with **no** work orders at
all takes the same branch and is told *"all work orders have 0 duration"*.
An operator reading that will look for a work order to fill in; there is
none to find, and the real fix is on the BoM. Worth splitting into two
messages.

**Found by** `TEST-WF007-TC106` … `TC112`, which now satisfy the gate in
the fixture (the BoM carries a Packaging operation and 15 minutes are
logged against it) rather than working around it.

---

## Already fixed and merged

For completeness — these were found the same way and are closed.

**`dto_account_workday/models/account_payment.py:56,58`** —
`_apply_payment_to_invoice` called `payment_moves.mapped('line_ids')` on an
`account.payment`. v19 removed `_inherits` to `account.move`, so
`account.payment` has `move_id` and no `line_ids`. The `KeyError` was
caught per row, so the import reported the file as `failed` with the
payment already created and posted — the money moved, only the
reconciliation was missing, and nothing raised. Merged as PR #242.

---

## Reproducing without the QA platform

Every item above is reachable from an Odoo shell on a restored UAT
database. The QA suite is only how they were found; none of them needs it
to reproduce. Where a test id is named, running that single case gives the
full step-by-step evidence:

```
POST /api/runs  {"environment": "odoo19", "test_ids": ["TEST-WF015-TC202"]}
```
