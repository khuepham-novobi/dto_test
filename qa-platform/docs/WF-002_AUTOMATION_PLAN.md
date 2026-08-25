# DATAONE-WF-002 — Quotation → sales order confirmation · Automation Plan

| | |
|---|---|
| Workflow | `DATAONE-WF-002` — Quotation → sales order confirmation |
| Build order | 4 (Stage 1 — easiest entry points) · estimate 18.5 h |
| Effective risk | **HIGH** |
| Owns | 37 workbook test cases |
| Suite | `tests/wf002/` |
| Modules | `dto_sale`, `dto_account`, `dto_sale_workday`, `dto_sale_price_formula`, `dto_sale_stock` |
| Source | `DataOne_v19_Test_Suite_and_Workflows_v1.0.xlsx` / `Automation Export` |

## Result

| | Count |
|---|---:|
| Implemented | **35** |
| Implemented + SKIPPED for a human | **1** (TC087) |
| Blocked stub | **1** (TC350) |
| Not implemented | 0 |
| **Total** | **37** |

## Three findings that shaped the whole suite

### 1. Confirming an order sends real email

`dto_sale.base_automation_send_email_on_sale_order_confirm` fires on the
state change to `sale` and ends in:

```python
template.send_mail(order.id, force_send=True,
                   email_values={'email_to': email_to})
```

with `email_to` built from a **hard-coded d1systems.com recipient list**
(`mfgestimating@`, `procurement@`, `orders@`, `miguel.oyervidez@`, plus
`D1CienaIRM@` when the memo mentions IRM).

Every test here that confirms an order calls
`framework.qa_fixtures.require_mail_offline(ctx)` first, which **BLOCKS
unless every `ir.mail_server` is deactivated**. The platform will not risk
delivering real email to real people.

### 2. That same automation crashes on an empty memo — and it is load-bearing

```python
if 'IRM' in order.memo_to_suppliers:
```

`memo_to_suppliers` is a `Text` field defaulting to `False`, and
`'IRM' in False` raises `TypeError`, aborting the confirmation and rolling
its procurement back. That is TC085 — and it means **every other fixture in
this suite that gets confirmed must carry a non-empty memo**, or it fails
for a reason that has nothing to do with the case under test.
`common.make_quotation` sets one by default; TC085 passes `memo=""`
deliberately. The same fix was applied to WF-003's fixture.

### 3. `mail_servers off` is what makes the "manual" email cases automatable

The workbook marks TC083, TC084 and TC086 MANUAL. But with delivery
impossible, `send_mail(force_send=True)` still **creates the `mail.mail`
record** and only then fails — Odoo catches the SMTP error and marks the
message `exception` (`mail/models/mail_mail.py:546-575`). So `email_to` and
`body_html` are readable exactly as composed, with nothing leaving the box.
All three are implemented rather than left to a person.

## v19 migration finding recorded by this suite

`dto_account`'s four analytic gates call `line._get_analytic_account_ids()`.

| | |
|---|---|
| Odoo 17 | present — `addons/analytic/models/analytic_mixin.py:159` |
| Odoo 19 | **removed** — replaced by `_get_analytic_account_ids_from_distributions(distributions)` at `analytic_mixin.py:49` |

`TC074` and `TC078`–`TC082` are therefore **expected to ERROR on v19** until
`dto_account` is ported. That is a product finding, not an automation
defect, and it is stated in each test's docstring.

## Per test case

| Workbook TC | Prio | Platform test | Decision | EXPECTED v17 |
|---|---|---|---|---|
| `TC017` | P1 | `TEST-WF002-TC017` | implemented — compiles every custom server-action body + removed-API scan + automation shape | PASS/FAIL on the scan |
| `TC053` | P1 | `TEST-WF002-TC053` | implemented — ORM reconciliation, incl. the renamed UoM column by *population* | PASS |
| `TC057` | P2 | `TEST-WF002-TC057` | implemented — md5 digests of template bodies and action code | PASS |
| `TC061` | P1 | `TEST-WF002-TC061` | implemented | PASS |
| `TC062` | P3 | `TEST-WF002-TC062` | implemented — 4 of 5 checks machine-read; badge colour logged for a person | PASS |
| `TC063` | P1 | `TEST-WF002-TC063` | implemented | PASS |
| `TC064` | P2 | `TEST-WF002-TC064` | implemented | PASS |
| `TC065` | P1 | `TEST-WF002-TC065` | implemented | PASS |
| `TC066` | P2 | `TEST-WF002-TC066` | implemented | PASS |
| `TC067` | P2 | `TEST-WF002-TC067` | implemented — the *silence* asserted positively | PASS |
| `TC068` | P2 | `TEST-WF002-TC068` | implemented | PASS |
| `TC069` | P2 | `TEST-WF002-TC069` | implemented — defect regression, both halves on one record | PASS |
| `TC070` | P2 | `TEST-WF002-TC070` | implemented | PASS |
| `TC071` | P2 | `TEST-WF002-TC071` | implemented — real stock, real delivery | PASS |
| `TC072` | P3 | `TEST-WF002-TC072` | implemented — **one contested expectation flagged** | AttributeError half PASS; `delivery_status` assertion expected to FAIL |
| `TC073` | P1 | `TEST-WF002-TC073` | implemented | PASS |
| `TC074` | P1 | `TEST-WF002-TC074` | implemented | PASS (v19: ERROR) |
| `TC075` | P1 | `TEST-WF002-TC075` | implemented | PASS |
| `TC076` | P1 | `TEST-WF002-TC076` | implemented — MRO established behaviourally | PASS |
| `TC077` | P1 | `TEST-WF002-TC077` | implemented | PASS |
| `TC078`–`TC082` | P1/P2 | `TEST-WF002-TC078…082` | implemented | PASS (v19: ERROR) |
| `TC083` | P1 | `TEST-WF002-TC083` | implemented — recipient lists read from `mail.mail` | PASS |
| `TC084` | P2 | `TEST-WF002-TC084` | implemented | PASS |
| `TC085` | P1 | `TEST-WF002-TC085` | implemented — the live defect | PASS |
| `TC086` | P2 | `TEST-WF002-TC086` | implemented — body read from `mail.mail` | PASS |
| `TC087` | P2 | `TEST-WF002-TC087` | report + template asserted, then **SKIPPED** for a human | SKIPPED |
| `TC089` | P3 | `TEST-WF002-TC089` | implemented — arch + domains + partition + composition, no tour needed | PASS |
| `TC090`–`TC094` | P2/P3 | `TEST-WF002-TC090…094` | implemented — company formula snapshot/restored | PASS |
| `TC350` | P0 | `TEST-WF002-TC350` | **blocked stub** — Phase-5 round trip | BLOCKED |

## The one contested expectation (TC072)

The workbook expects `delivery_status == 'early'` for a shipment 19 days
late, on the grounds that `late` is dead logic. Reading
`dto_sale/models/sale_order_line.py`, `date_diff` is **signed** and the
ternary is `'early' if date_diff >= 0 else 'late'`, so a late shipment
should yield `late`.

The assertion is implemented **verbatim as the workbook states it**
(convention rule 2 — expectations are immutable). If it fails while
`date_difference` matches, that is a **workbook-vs-source discrepancy for a
human to adjudicate**, not an automation defect. It is recorded in the test
docstring so whoever reads the result knows which it is.

## Adaptations (documented, not assertion-weakening)

1. **MRO read behaviourally** (TC076). `type(env['sale.order']).__mro__` is not reachable — Odoo dispatches no introspection endpoint. Peeling one gate at a time off an order that violates all three establishes the same ordering, and confirms BR-1, which the workbook marks *Inferred*.
2. **The PO/search UI replaced by the calls behind it** (TC089, TC062). The composed search/form/list arch is asserted (which catches the inherit failing to load), then each filter's domain is run through `search_count`, and `read_group` stands in for the group-by.
3. **SQL reconciliation done through the ORM** (TC053, TC057), so no PostgreSQL credentials are needed and the tests never report BLOCKED for a missing `pg_*` config. The renamed UoM column is compared by *population*, not by column name.
4. **The no-handler `AttributeError`** (TC081 step 5) cannot be demonstrated live — `order_type` is a Selection and an unknown value cannot be written over RPC. The test instead asserts that every `order_type` key has a matching `_validate_analytic_distribution_<key>` handler, which is the check that actually protects against the `getattr` dispatch failing.
5. **Config snapshot/restore.** TC090, TC091 and TC093 flip `res.company.price_formula` and restore it in a `finally` that cannot raise.
6. **Marker-scoped counting** everywhere a count is asserted.

## Verified source facts

| Fact | Where |
|---|---|
| `order_type` `required=True`, no default; `client_order_ref` / `analytic_account_id` re-declared `copy=True` | `dto_sale/models/sale_order.py:17,33,34` |
| Ship-date gate message and its `display_type` filter | `dto_sale/models/sale_order.py:59` |
| Tariff guard lives in `write()` only | `dto_sale/models/sale_order.py:75` |
| `commitment_date` = `max(requested_delivery_date)`, inverse is a no-op | `dto_sale/models/sale_order.py:27,50,55` |
| `date_difference = abs(date_diff)`; `reference_date = … or commitment_date.date()` | `dto_sale/models/sale_order_line.py:45` |
| Requester-email gate message | `dto_sale_workday/models/sale_order.py:25` |
| Analytic dispatch by `getattr` on an f-string; `analytic_account_id` assigned inside the per-line loop | `dto_account/models/sale_order.py:16,29,41` |
| The three analytic-plan xmlids | `dto_account/models/account_analytic_plan.py:6` |
| `_get_analytic_account_ids` present on v17, removed on v19 | `analytic_mixin.py:159` / `:49` |
| Recipient map, IRM append, `force_send=True` | `dto_sale/data/base_automation_data.xml` |
| Template subject/body blocks | `dto_sale/data/mail_template_data.xml` |
| The six search filters and the Order Type group-by | `dto_sale/views/sale_order_views.xml:46-57` |
| NTT compute, its `@api.depends` (which omits the formula fields), and its silent `except` | `dto_sale_price_formula/models/sale_order_line.py` |
| A failed `mail.mail.send()` marks `exception` and does not raise | `mail/models/mail_mail.py:546-575` |

## What this suite does NOT cover

- The Phase-5 Workday round trip (TC350) — needs the endpoint, the private ETL entry points, and ten other workflows built.
- The visual PDF diff (TC087) — needs a rendered page and a human eye.
- The coloured-badge rendering (TC062) and the server-log WARNING line (TC092) — both logged with their exact source location rather than asserted.

## Run

```bash
venv/Scripts/python.exe -c "from framework import registry; print(len(registry.discover()))"
```
