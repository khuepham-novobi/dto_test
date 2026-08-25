# Test Inventory — FG-01 → FG-14

Generated 2026-08-25 11:50 by `scripts/gen_inventory_doc.py`.

**Source of truth:** `C:\Users\tan\Downloads\DataOne_v19_Test_Suite_and_Workflows_v1.0.xlsx`, sheet **Automation Export** (read-only — the platform never writes to the workbook).

Full capture of every test case — including **preconditions, steps and the verbatim expected result** — lives in `data/test_registry.json` (regenerate with `python scripts/sync_registry.py`) and is browsable per test case in the web UI (`#/testcase/<TC-ID>`). Expected results are imported verbatim and are never modified by the platform.

## Summary

| Feature group | Name | Test cases | P0 | P1 | P2 | P3 |
|---|---|---:|---:|---:|---:|---:|
| DATAONE-WF-002 | Quotation → sales order confirmation | 37 | 1 | 16 | 13 | 7 |
| DATAONE-WF-003 | Quotation revision | 6 | 2 | 2 | 2 | 0 |
| DATAONE-WF-013 | Customer Invoice Posting: COGS and Revenue Recognition | 39 | 30 | 5 | 2 | 2 |
| DATAONE-WF-020 | Supplier Master Import from Workday | 18 | 9 | 5 | 4 | 0 |
| **Total** | | **100** | **42** | **28** | **21** | **9** |

### Automation classification (Step 3)

Derived deterministically from the workbook `automation_approach` column (mapping in `scripts/sync_registry.py::_APPROACH_MAP`):

| automation_type | Count | Meaning |
|---|---:|---|
| PYTHON_UNIT | 61 | Odoo `TransactionCase` test inside the Odoo test runner |
| ORM_INTEGRATION | 2 | `odoo-bin` install/upgrade + registry & log checks |
| API | 9 | Connector integration test vs sandbox / mocked API (`TEST_QUEUE_JOB_NO_DELAY=1`) |
| UI | 0 | Playwright browser workflow driven by this platform |
| HTTP_CASE | 0 | Odoo `HttpCase` endpoint test (+ manual security review) |
| TOUR | 4 | Odoo tour (`HttpCase` / `browser_js`) |
| HOOT | 0 | Odoo 17+ JS unit test (none in FG-01..14 scope) |
| DATA_RECONCILIATION | 17 | SQL/ORM comparison — v17 baseline vs v19 |
| MANUAL | 6 | Human execution required (decision gates, perf baselines, one-off checks) |
| NOT_APPLICABLE | 0 | Not applicable to the v19 scope |

### Automation status

| automation_status | Count | Meaning |
|---|---:|---|
| AUTOMATED | 100 | Covered by a registered platform test today |
| PLANNED | 0 | Workbook Wave 1 — automate now |
| CANDIDATE | 0 | Workbook Wave 2 — candidate |
| NOT_PLANNED | 0 | Automatable type but workbook says manual for now |
| MANUAL_ONLY | 0 | Not automatable (decision gates, perf baselines) |

---

## DATAONE-WF-002 — Quotation → sales order confirmation (37 test cases)

> Confirmation is the moment a DataOne quotation becomes a commitment: stock is reserved, manufacturing orders and purchase orders are launched, and internal teams are told to act. DataOne therefore uses confirmation as its single quality gate — the order must be classified, it must carry a reachable requester, it must be analytically coded correctly for its type, and every line must carry a date the business has actually promised. Anything that gets past confirmation without those four things cannot be corrected cleanly downstream.
>
> **Key modules:** DATAONE-F030, F031, F032, F033, F035, F036, F038, F151, F220, and — as the downstream consequences of confirmation — F039, F040, F052, F073, F074, F174 · **Roles:** - Salesperson — completes and confirms the quotation. - System — three stacked action_confirm overrides, a stored compute on the commitment date, a base.automation that sends the confirmation email, and the procurement run. - Internal distribution lists — MFG Estimating, Procurement, Order Entry, and the Ciena IRM desk, all @d1systems.com; recipients of the confirmation email (F035).

| TC ID | Title | Prio | Type | Automation | Status | Src row |
|---|---|---|---|---|---|---:|
| DATAONE-TC017 | Every server-action and automated-action code body compiles and contains no removed API | P1 | SMOKE | PYTHON_UNIT | AUTOMATED | 18 |
| DATAONE-TC053 | Sales order type distribution and the analytic discipline fields | P1 | DATA | DATA_RECONCILIATION | AUTOMATED | 54 |
| DATAONE-TC057 | Mail templates, server actions and automated actions | P2 | DATA | DATA_RECONCILIATION | AUTOMATED | 58 |
| DATAONE-TC061 | Order Type is mandatory and has no default | P1 | FUNC | PYTHON_UNIT | AUTOMATED | 62 |
| DATAONE-TC062 | Order Type is tracked, badged in the list, and survives duplication | P3 | UI | MANUAL | AUTOMATED | 63 |
| DATAONE-TC063 | Confirmation is blocked when a product line has no Promised Ship Date | P1 | NEG | PYTHON_UNIT | AUTOMATED | 64 |
| DATAONE-TC064 | Section and note lines do not block confirmation | P2 | BOUND | PYTHON_UNIT | AUTOMATED | 65 |
| DATAONE-TC065 | Delivery Date is derived from the LATEST promised line date | P1 | FUNC | PYTHON_UNIT | AUTOMATED | 66 |
| DATAONE-TC066 | A manually typed Delivery Date persists | P2 | FUNC | PYTHON_UNIT | AUTOMATED | 67 |
| DATAONE-TC067 | A later line-date edit silently overwrites the manual Delivery Date | P2 | REGR | PYTHON_UNIT | AUTOMATED | 68 |
| DATAONE-TC068 | A negative tariff is rejected on write with the exact message | P2 | NEG | PYTHON_UNIT | AUTOMATED | 69 |
| DATAONE-TC069 | A negative tariff supplied to create() is NOT blocked (defect regression) | P2 | NEG | PYTHON_UNIT | AUTOMATED | 70 |
| DATAONE-TC070 | Tariff Amount never affects the order total | P2 | FUNC | PYTHON_UNIT | AUTOMATED | 71 |
| DATAONE-TC071 | Per-line delivery performance populates after the outgoing move is done | P2 | FUNC | PYTHON_UNIT | AUTOMATED | 72 |
| DATAONE-TC072 | "Late" is unreachable at line level, and the null-commitment crash | P3 | NEG | PYTHON_UNIT | AUTOMATED | 73 |
| DATAONE-TC073 | Gate 1: no requester email blocks confirmation and creates nothing | P1 | NEG | PYTHON_UNIT | AUTOMATED | 74 |
| DATAONE-TC074 | Gate 2: a missing analytic account blocks confirmation and creates nothing | P1 | NEG | PYTHON_UNIT | AUTOMATED | 75 |
| DATAONE-TC075 | Gate 3: the Promised Ship Date gate creates nothing downstream | P1 | NEG | PYTHON_UNIT | AUTOMATED | 76 |
| DATAONE-TC076 | Which gate fires first: the MRO order of the three overrides | P1 | REGR | PYTHON_UNIT | AUTOMATED | 77 |
| DATAONE-TC077 | Multi-record confirm: one order without a requester email blocks all | P1 | NEG | PYTHON_UNIT | AUTOMATED | 78 |
| DATAONE-TC078 | project: an account outside the Project plan raises "Project is required" | P1 | NEG | PYTHON_UNIT | AUTOMATED | 79 |
| DATAONE-TC079 | buy: the Customer Contract plan is required | P1 | NEG | PYTHON_UNIT | AUTOMATED | 80 |
| DATAONE-TC080 | inventory: any analytic distribution is rejected | P1 | NEG | PYTHON_UNIT | AUTOMATED | 81 |
| DATAONE-TC081 | cost_center: any analytic distribution is rejected | P1 | NEG | PYTHON_UNIT | AUTOMATED | 82 |
| DATAONE-TC082 | analytic_account_id is set from the LAST line's first account | P2 | REGR | PYTHON_UNIT | AUTOMATED | 83 |
| DATAONE-TC083 | Confirmation email recipients routed by order type | P1 | INTEG | MANUAL | AUTOMATED | 84 |
| DATAONE-TC084 | An IRM memo appends the Ciena IRM desk to the recipient list | P2 | INTEG | MANUAL | AUTOMATED | 85 |
| DATAONE-TC085 | An empty memo raises TypeError and aborts the confirmation | P1 | NEG | PYTHON_UNIT | AUTOMATED | 86 |
| DATAONE-TC086 | Confirmation email body: total, ship date, order type, Reference # and Req # | P2 | UI | MANUAL | AUTOMATED | 87 |
| DATAONE-TC087 | Sale Order PDF: requester block, memo, "Product" header and product name | P2 | UI | MANUAL | AUTOMATED | 88 |
| DATAONE-TC089 | Order type and tariff search filters and group-by | P3 | UI | TOUR | AUTOMATED | 90 |
| DATAONE-TC090 | The company NTT price formula is applied to the line | P3 | FUNC | PYTHON_UNIT | AUTOMATED | 91 |
| DATAONE-TC091 | A customer formula overrides the company formula | P3 | FUNC | PYTHON_UNIT | AUTOMATED | 92 |
| DATAONE-TC092 | An invalid formula silently falls back to the unit price | P3 | NEG | PYTHON_UNIT | AUTOMATED | 93 |
| DATAONE-TC093 | A manual NTT value is overwritten; a formula change is not retroactive | P3 | FUNC | PYTHON_UNIT | AUTOMATED | 94 |
| DATAONE-TC094 | NTT Unit Price never reaches the total, the invoice, tax or margin | P2 | FUNC | PYTHON_UNIT | AUTOMATED | 95 |
| DATAONE-TC350 | GATE (Phase 5): the full Workday round trip, run twice | P0 | INTEG | API | AUTOMATED | 351 |

## DATAONE-WF-003 — Quotation revision (6 test cases)

> A quotation under negotiation gets re-issued. DataOne needs that to be auditable: the superseded version must remain readable, the new version must be recognisably the same commercial document, and neither must clutter the working quotation list. Editing a cancelled order in place destroys the history; duplicating it creates an unrelated document nobody can trace. The revision mechanism gives a controlled version number instead, and it is also the mechanism the Workday requisition import uses to absorb a revised requisition without overwriting what Odoo already holds.
>
> **Key modules:** DATAONE-F051, F052, and — as the fields and paths that ride on them — F030 (Order Type), F033 (Tariff Amount), F213, F218, F219, F222 · **Roles:** - Salesperson — presses New Revision of Quotation and works the new version. - System — base.revision — numbering, copying, archiving, chatter, chain flattening. - System — Workday requisition import — calls the same create_revision() unattended (DATAONE-WF-001 Step 7). - Installer — post_init_hook backfills unrevisioned_name at module install.

| TC ID | Title | Prio | Type | Automation | Status | Src row |
|---|---|---|---|---|---|---:|
| DATAONE-TC014 | The five OCA modules import and load on the v19 runtime | P0 | SMOKE | ORM_INTEGRATION | AUTOMATED | 15 |
| DATAONE-TC095 | Gate case: revision -01 created, source cancelled and archived, fields copied by value | P1 | FUNC | PYTHON_UNIT | AUTOMATED | 96 |
| DATAONE-TC096 | A second revision flattens the chain; the stat button lists all prior versions | P1 | FUNC | PYTHON_UNIT | AUTOMATED | 97 |
| DATAONE-TC097 | The revision button appears only in sent and cancel | P2 | UI | TOUR | AUTOMATED | 98 |
| DATAONE-TC098 | The lineage uniqueness constraint and its exact message | P2 | NEG | PYTHON_UNIT | AUTOMATED | 99 |
| DATAONE-TC338 | Re-import of an unconfirmed order creates a revision, cancels and archives the old | P0 | FUNC | API | AUTOMATED | 339 |

## DATAONE-WF-013 — Customer Invoice Posting: COGS and Revenue Recognition (39 test cases)

> DataOne does not report a conventional gross margin on three of its four sale order types. Project, inventory and cost-centre work is accounted through analytic dimensions rather than through conventional revenue and receivable balances: the invoice grosses revenue and receivable up and then reverses both on the same entry, so the profit-and-loss and balance-sheet accounts net to zero while the five-dimension analytic ledger carries the real position. Cost of goods sold is booked at the sales price on project work (a pass-through presentation) and suppressed entirely on inventory and cost-centre work, because that cost was already absorbed elsewhere. The receivable on those three types is held in Accrued Revenue rather than trade AR, so the collections ageing report stays honest. Only trade sales (buy) use Odoo's standard cost-based COGS and trade receivable. This is a deliberate, unusual revenue-recognition pattern; it is invisible in the user interface, and it is the single most valuable thing in this document set to characterise with tests.
>
> **Key modules:** DATAONE-F161, F162, F163, F164, F165, F166, F153, F157, F152, F150, F158, F159, F160, F155, F040 · **Roles:** - Accountant — posts the invoice, or resets it to draft. Sees none of the mechanism. - Warehouse operator — in practice the most frequent trigger, via WF-012's auto-post on delivery. - Accounting Manager — the only role permitted to register payment against the result (F158). - Settings/System user — the only role permitted to delete the resulting entry (F159). - Controller / auditor — the only consumer who can tell whether any of this is right. - System — the four-deep _post override chain, the _compute_account_id redirect, the anglo-saxon COGS machinery, and the button_draft / button_cancel cleanup.

| TC ID | Title | Prio | Type | Automation | Status | Src row |
|---|---|---|---|---|---|---:|
| DATAONE-TC007 | Every env.ref() literal in the custom code resolves against the database | P0 | SMOKE | STATIC_ANALYSIS | AUTOMATED | 8 |
| DATAONE-TC021 | Trial balance identical to the cent, per account | P0 | DATA | DATA_RECONCILIATION | AUTOMATED | 22 |
| DATAONE-TC023 | Invoice totals by year × move_type × state | P0 | DATA | DATA_RECONCILIATION | AUTOMATED | 24 |
| DATAONE-TC025 | stock.valuation.layer disappearance: inventory value is preserved | P0 | DATA | DATA_RECONCILIATION | AUTOMATED | 26 |
| DATAONE-TC027 | Analytic distribution key format survived the upgrade | P0 | DATA | DATA_RECONCILIATION | AUTOMATED | 28 |
| DATAONE-TC028 | Analytic distribution coverage on journal items is unchanged | P0 | DATA | DATA_RECONCILIATION | AUTOMATED | 29 |
| DATAONE-TC034 | stock.location valuation-account collapse: two v17 columns folded into one | P0 | DATA | DATA_RECONCILIATION | AUTOMATED | 35 |
| DATAONE-TC048 | Journal-item counts and balances per journal per period | P0 | DATA | DATA_RECONCILIATION | AUTOMATED | 49 |
| DATAONE-TC049 | Open receivable and payable residuals per partner | P0 | DATA | DATA_RECONCILIATION | AUTOMATED | 50 |
| DATAONE-TC051 | Tax totals by tax and year | P0 | DATA | DATA_RECONCILIATION | AUTOMATED | 52 |
| DATAONE-TC052 | is_cogs line population survives | P0 | DATA | DATA_RECONCILIATION | AUTOMATED | 53 |
| DATAONE-TC221 | GATE: skip_invoice_sync still produces two asset_receivable lines on v19 | P0 | FUNC | MANUAL | AUTOMATED | 222 |
| DATAONE-TC222 | The renamed anglo-saxon hook override actually executes on v19 | P0 | FUNC | PYTHON_UNIT | AUTOMATED | 223 |
| DATAONE-TC223 | COGS and revenue reversal, order_type = buy (Table A) | P0 | FUNC | PYTHON_UNIT | AUTOMATED | 224 |
| DATAONE-TC224 | COGS and revenue reversal, order_type = project (Table B) | P0 | FUNC | PYTHON_UNIT | AUTOMATED | 225 |
| DATAONE-TC225 | COGS and revenue reversal, order_type = inventory (Table C) | P0 | FUNC | PYTHON_UNIT | AUTOMATED | 226 |
| DATAONE-TC226 | COGS and revenue reversal, order_type = cost_center (Table D) | P0 | FUNC | PYTHON_UNIT | AUTOMATED | 227 |
| DATAONE-TC227 | Consolidated invoice spanning project and buy — the project branch wins per move | P0 | BOUND | PYTHON_UNIT | AUTOMATED | 228 |
| DATAONE-TC228 | Account 12500 missing — the AR redirect silently no-ops | P0 | NEG | PYTHON_UNIT | AUTOMATED | 229 |
| DATAONE-TC229 | Deleted analytic xml_id — ValueError: External ID not found in the system | P0 | NEG | PYTHON_UNIT | AUTOMATED | 230 |
| DATAONE-TC230 | Multi-move mass post — cross-contaminated reversal lines (E5) | P0 | NEG | PYTHON_UNIT | AUTOMATED | 231 |
| DATAONE-TC231 | post → draft → post → draft cycle, run three times | P0 | REGR | PYTHON_UNIT | AUTOMATED | 232 |
| DATAONE-TC232 | MRO assertion: dto_account_cogs overrides run outermost | P0 | FUNC | PYTHON_UNIT | AUTOMATED | 233 |
| DATAONE-TC233 | Are zero-value COGS / Interim lines emitted on inventory orders? | P1 | DATA | PYTHON_UNIT | AUTOMATED | 234 |
| DATAONE-TC258 | BASELINE: top 20 v17 customer invoices reproduced to the cent | P0 | DATA | DATA_RECONCILIATION | AUTOMATED | 259 |
| DATAONE-TC259 | BASELINE: analytic-distribution key shapes survive on those 40 entries | P0 | DATA | DATA_RECONCILIATION | AUTOMATED | 260 |
| DATAONE-TC260 | BASELINE: Stock Interim (Delivered) residue on project orders | P0 | DATA | DATA_RECONCILIATION | AUTOMATED | 261 |
| DATAONE-TC270 | An Invoicing user cannot delete a journal entry | P0 | SEC | PYTHON_UNIT | AUTOMATED | 271 |
| DATAONE-TC271 | A Purchase user cannot delete a journal entry | P0 | SEC | PYTHON_UNIT | AUTOMATED | 272 |
| DATAONE-TC272 | A Settings user can delete a journal entry | P1 | SEC | PYTHON_UNIT | AUTOMATED | 273 |
| DATAONE-TC273 | No group other than Settings holds perm_unlink on account.move | P0 | SEC | PYTHON_UNIT | AUTOMATED | 274 |
| DATAONE-TC274 | The journal-entry Number is read-only on the form (and only there) | P3 | UI | TOUR | AUTOMATED | 275 |
| DATAONE-TC279 | AR labels are suffixed with Project and Customer Contract names on post | P1 | FUNC | PYTHON_UNIT | AUTOMATED | 280 |
| DATAONE-TC280 | Reset to draft blanks the AR labels | P1 | FUNC | PYTHON_UNIT | AUTOMATED | 281 |
| DATAONE-TC281 | Three post → draft → post cycles: labels do not concatenate | P1 | REGR | PYTHON_UNIT | AUTOMATED | 282 |
| DATAONE-TC282 | A move with no Project or Contract account gets the empty-segment label | P3 | BOUND | PYTHON_UNIT | AUTOMATED | 283 |
| DATAONE-TC283 | Both AR lines — the original and the reversal — carry the suffix | P2 | FUNC | PYTHON_UNIT | AUTOMATED | 284 |
| DATAONE-TC286 | Invoice lines inherit the sale line's distribution; later lines win on merge | P0 | FUNC | PYTHON_UNIT | AUTOMATED | 287 |
| DATAONE-TC287 | The post-create write also fires on lines DataOne itself created | P2 | REGR | PYTHON_UNIT | AUTOMATED | 288 |

## DATAONE-WF-020 — Supplier Master Import from Workday (18 test cases)

> Workday owns the supplier master. Keeping Odoo's vendor list in step is what makes the rest of the Workday integration match at all: purchase orders and bills reference the same vendor codes, WF-018 can write a valid partner_id.ref into required column U of the Supplier Invoice workbook, and WF-019 can find the bill a payment settles. Without this flow the vendor codes drift, and the failure appears three steps downstream as a rejected bill export or an unmatched payment, not here.
>
> **Key modules:** DATAONE-F190, F191, F192, F193, F195, F196, F207 — supplying the res.partner.ref that DATAONE-F204 / WF-018 writes into column U and that DATAONE-F206 / WF-019 depends on for matching. · **Roles:** - Workday (external) — owns the supplier master and writes the file to the SFTP drop. - System — the same two 5-minute crons that serve WF-019: cron_get_sftp_files downloads and archives, cron_process_sftp_files runs the ETL. - Purchasing and accounting users — never trigger this flow; they consume the resulting vendor records on purchase orders and bills. - System administrator (base.group_system) — owns the folder configuration and is the only person who sees the failure, as SUPERUSER_ID on the sftp.file activity.

| TC ID | Title | Prio | Type | Automation | Status | Src row |
|---|---|---|---|---|---|---:|
| DATAONE-TC008 | Every ir.cron from the inventory exists, is active, and has the expected interval | P1 | SMOKE | DATA_RECONCILIATION | AUTOMATED | 9 |
| DATAONE-TC012 | The Python dependency set installs on the target Python | P0 | SMOKE | ORM_INTEGRATION | AUTOMATED | 13 |
| DATAONE-TC293 | The 5-minute GET pull creates a Pending sftp.file with an attachment and a Remote Path | P0 | INTEG | API | AUTOMATED | 294 |
| DATAONE-TC294 | Archive-on-download, including the (YYYY-MM-DD HHMMSS UTC) collision suffix | P1 | INTEG | API | AUTOMATED | 295 |
| DATAONE-TC295 | No archive path configured — <path>_archived is auto-created and written back | P2 | FUNC | API | AUTOMATED | 296 |
| DATAONE-TC297 | Folder uniqueness constraint, including archived folders | P2 | NEG | PYTHON_UNIT | AUTOMATED | 298 |
| DATAONE-TC298 | Process Now visibility and Only pending file(s) can be processed! | P2 | NEG | TOUR | AUTOMATED | 299 |
| DATAONE-TC301 | sftp.log capture — level, method, traceback, resolve / unresolve | P2 | FUNC | API | AUTOMATED | 302 |
| DATAONE-TC302 | LIVE DEFECT: a folder with a non-empty regex raises TypeError; the filter is unusable | P0 | NEG | PYTHON_UNIT | AUTOMATED | 303 |
| DATAONE-TC305 | v19: repeated cron failure silently deactivates the poller | P0 | REGR | API | AUTOMATED | 306 |
| DATAONE-TC331 | GATE: nine-column CSV, five rows, one failure, no activity on any partner | P0 | FUNC | API | AUTOMATED | 332 |
| DATAONE-TC332 | A new vendor is created with supplier_rank = 1 and is selectable on a PO | P1 | FUNC | PYTHON_UNIT | AUTOMATED | 333 |
| DATAONE-TC333 | An existing partner matched on ref is overwritten unconditionally, blanks included | P0 | DATA | PYTHON_UNIT | AUTOMATED | 334 |
| DATAONE-TC334 | A blank payment term clears the value; an unresolvable term fails only its own row | P0 | NEG | PYTHON_UNIT | AUTOMATED | 335 |
| DATAONE-TC335 | "Texas (US)" resolves the state and derives the country; blank clears both | P1 | FUNC | PYTHON_UNIT | AUTOMATED | 336 |
| DATAONE-TC336 | The file goes Failed with no activity on any partner; re-process repairs the bad row | P1 | NEG | API | AUTOMATED | 337 |
| DATAONE-TC459 | Every cron in the inventory exists, is active, has the expected interval, and executes without error | P0 | REGR | DATA_RECONCILIATION | AUTOMATED | 460 |
| DATAONE-TC460 | A repeatedly failing cron is auto-deactivated on v19, silently stopping the daily Workday export | P0 | REGR | PYTHON_UNIT | AUTOMATED | 461 |

---

*Src row = row in the workbook sheet “Automation Export”; each test case also records its “Test Execution” sheet row in the registry JSON.*
