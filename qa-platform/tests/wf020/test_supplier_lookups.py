"""DATAONE-WF-020 — the two master-data lookups: TC334, TC335.

TC334 — payment term. A blank cell must CLEAR the value (the helper
returns ``{'property_supplier_payment_term_id': False}``, not an empty
dict), an unresolvable name must fail only its own row leaving that partner
untouched, and matching is exact and case-sensitive
(``search([('name', '=', term_data)])`` after a ``.strip()``).

TC335 — state and country. ``"Texas (US)"`` is parsed by
``re.search(r'(.+) \\((.+)\\)')`` — one literal space before the opening
parenthesis — and the country is DERIVED from the state, since the CSV has
no country column. A blank clears both. An unknown name fails only its row.

Both helpers are private
(``res_partner._get_payment_term_for_workday_contact`` /
``_get_state_country_for_workday_contact``) and cannot be called over RPC,
so every assertion here observes their effect through the public ETL entry
point — the same pipeline a real GET-then-process runs, driven from the
attachment with no network.

Fixture-value adaptation: token-scoped payment-term names and refs, so
exact-name matching is unambiguous on a live clone. The state fixtures use
the real ``Texas`` / ``New York`` records because the parse contract is
about them.

EXPECTED v17 OUTCOME: PASS.
"""
from framework.registry import test_case
from tests.wf020.common import (MARK, WORKFLOW, WORKFLOW_NAME,  # noqa: F401
                                fx, m2o_id, partner_by_ref, ref_for,
                                require_sftp_stack, require_supplier_usage,
                                run_supplier_import, supplier_row,
                                sweep_wf020, trace)

TERM_ERROR = "Cannot find payment term in Odoo"
STATE_ERROR = "Cannot find state in Odoo"
NBSP = " "

FIELDS = ["ref", "name", "street", "street2", "city", "zip", "phone",
          "property_supplier_payment_term_id", "state_id", "country_id",
          "supplier_rank", "email", "comment", "id"]


def _row_errors(rpc, file_id) -> str:
    """The joined row errors the ETL filed as a warning activity."""
    notes = [a.get("note") or "" for a in rpc.search_read(
        "mail.activity",
        [("res_model", "=", "sftp.file"), ("res_id", "=", file_id)],
        ["note"])]
    return " ".join(notes)


@test_case(
    id="TEST-WF020-TC334",
    name="A blank payment term clears the value; an unresolvable term fails "
         "only its own row",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account_workday", priority="P0", kind="API", order=20334,
    description="A blank cell clears property_supplier_payment_term_id "
                "rather than preserving it; an unknown term raises 'Cannot "
                "find payment term in Odoo' and leaves its partner "
                "completely unwritten while the other rows succeed; "
                "matching is exact — lower case and an internal "
                "non-breaking space both fail, a trailing ordinary space "
                "does not (the helper strips).",
    traceability=trace("DATAONE-TC334"))
def test_tc334(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-020 fixtures and open a fresh "
                  "namespace"):
        sweep_wf020(rpc)

    with ctx.step("Preconditions: transport and supplier usage key"):
        require_sftp_stack(ctx)
        require_supplier_usage(ctx)

    try:
        with ctx.step("Seed a token-scoped payment term and two partners "
                      "that already carry it"):
            term_name = fx(f"{MARK} Net30")
            term_id = rpc.create("account.payment.term", {"name": term_name})
            ctx.check("nothing named the unresolvable term exists", 0,
                      rpc.call("account.payment.term", "search_count",
                               [("name", "=", "Net 37 Days Nonexistent")]))
            refs = {"blank": ref_for("011"), "bad": ref_for("012"),
                    "ok": ref_for("014")}
            ids = {}
            for key in ("blank", "bad"):
                ids[key] = rpc.create("res.partner", {
                    "name": fx(f"{MARK} Seeded {key}"),
                    "ref": refs[key], "street": "1 Original St",
                    "city": "Austin", "zip": "78701",
                    "email": f"{key}.qa@example.invalid",
                    "property_supplier_payment_term_id": term_id})

        with ctx.step("Step 1: record both partners' current term"):
            before = {k: partner_by_ref(rpc, refs[k], FIELDS)
                      for k in ("blank", "bad")}
            for key, row in before.items():
                ctx.check(f"{key} starts with the term set", term_id,
                          m2o_id(row["property_supplier_payment_term_id"]))

        with ctx.step("Steps 2-4, 6-7, 9: one file with a blank term, an "
                      "unresolvable term, and a good row"):
            rows = [
                supplier_row(refs["blank"], fx(f"{MARK} Vendor Iota"),
                             street="3 Iota Rd", payment_term="", state=""),
                supplier_row(refs["bad"], fx(f"{MARK} Vendor Kappa Renamed"),
                             street="4 Kappa Rd",
                             payment_term="Net 37 Days Nonexistent",
                             state=""),
                supplier_row(refs["ok"], fx(f"{MARK} Vendor Lambda"),
                             street="6 Lambda Rd", payment_term=term_name,
                             state=""),
            ]
            file_id, file_row = run_supplier_import(ctx, rows,
                                                    file_label="terms")
            ctx.check("file state with one failing row", "failed",
                      file_row["state"])

        with ctx.step("Step 3: the blank term CLEARED the value — it was "
                      "not preserved"):
            blank = partner_by_ref(rpc, refs["blank"], FIELDS)
            ctx.check("property_supplier_payment_term_id after a blank",
                      False, blank["property_supplier_payment_term_id"])

        with ctx.step("Steps 4-5: the rest of that row was written normally "
                      "— the blank term did not fail the row, which is what "
                      "returning {'…': False} rather than {} achieves"):
            ctx.check("blank-term row name", rows[0]["name"], blank["name"])
            ctx.check("blank-term row street", "3 Iota Rd", blank["street"])

        with ctx.step("Step 7: the unresolvable term raised the exact "
                      "message"):
            errors = _row_errors(rpc, file_id)
            ctx.log(f"row errors: {errors[:400]!r}")
            ctx.check_true(f"errors contain {TERM_ERROR!r}",
                           TERM_ERROR in errors, actual_desc=errors[:400])

        with ctx.step("Step 8: that partner is COMPLETELY unchanged — not "
                      "partially written"):
            bad = partner_by_ref(rpc, refs["bad"], FIELDS)
            diffs = {k: {"before": before["bad"].get(k), "after": bad.get(k)}
                     for k in FIELDS if before["bad"].get(k) != bad.get(k)}
            ctx.check("column differences on the failed row's partner", {},
                      diffs)

        with ctx.step("Step 9: the failure is confined to its own row — the "
                      "good rows in the same file succeeded"):
            ok = partner_by_ref(rpc, refs["ok"], FIELDS)
            ctx.check_true("the good row was created", ok is not None,
                           actual_desc=repr(ok))
            ctx.check("the good row resolved the term", term_id,
                      m2o_id(ok["property_supplier_payment_term_id"]))

        with ctx.step("Step 10: exact-name matching — lower case and an "
                      "internal non-breaking space fail; a trailing "
                      "ordinary space does not, because the helper strips"):
            variants = {
                "lower_case": term_name.lower(),
                "internal_nbsp": term_name.replace(" ", NBSP, 1),
                "trailing_space": term_name + " ",
            }
            outcomes = {}
            for label, value in variants.items():
                vref = ref_for(f"v-{label}")
                vfile, _row = run_supplier_import(
                    ctx,
                    [supplier_row(vref, fx(f"{MARK} Variant {label}"),
                                  payment_term=value, state="")],
                    file_label=f"term-{label}")
                errs = _row_errors(rpc, vfile)
                resolved = partner_by_ref(rpc, vref, FIELDS)
                outcomes[label] = "resolved" if (
                    resolved and m2o_id(
                        resolved["property_supplier_payment_term_id"])
                    == term_id) else (
                        "failed" if TERM_ERROR in errs else "other")
            ctx.log(f"variant outcomes: {outcomes!r}")
            ctx.check("exact-match variants",
                      {"lower_case": "failed", "internal_nbsp": "failed",
                       "trailing_space": "resolved"},
                      outcomes)

        with ctx.step("Step 12: creating the missing term and re-processing "
                      "repairs the failed row"):
            repair_id = rpc.create("account.payment.term",
                                   {"name": "Net 37 Days Nonexistent"})
            rpc.call("sftp.file", "action_retry_process_sftp_files",
                     [file_id])
            repaired = partner_by_ref(rpc, refs["bad"], FIELDS)
            ctx.check("the repaired row took its name", rows[1]["name"],
                      repaired["name"])
            ctx.check("the repaired row resolved the new term", repair_id,
                      m2o_id(repaired["property_supplier_payment_term_id"]))
            ctx.check("file state after the repair", "done",
                      rpc.read("sftp.file", [file_id], ["state"])[0]["state"])
    finally:
        with ctx.step("Cleanup WF-020 fixtures"):
            try:
                stale = rpc.search("account.payment.term",
                                   [("name", "=", "Net 37 Days Nonexistent")])
                if stale:
                    rpc.call("account.payment.term", "unlink", stale)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] repair term not removed: {exc}")
            try:
                sweep_wf020(rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")


@test_case(
    id="TEST-WF020-TC335",
    name='"Texas (US)" resolves the state and derives the country; blank '
         "clears both",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account_workday", priority="P1", kind="API", order=20335,
    description="The canonical form resolves the state and derives the "
                "country (there is no country column); a wrong or missing "
                "country code falls through to the name-only search and "
                "still resolves; a blank clears both; an unknown name fails "
                "only its row; the missing-space form 'Texas(US)' fails "
                "because the regex requires one literal space.",
    traceability=trace("DATAONE-TC335"))
def test_tc335(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-020 fixtures and open a fresh "
                  "namespace"):
        sweep_wf020(rpc)

    with ctx.step("Preconditions: transport, supplier usage key, and "
                  "exactly one Texas in the US"):
        require_sftp_stack(ctx)
        require_supplier_usage(ctx)
        texas = rpc.search_read("res.country.state",
                                [("name", "=", "Texas"),
                                 ("country_id.code", "=", "US")],
                                ["name", "country_id"])
        if len(texas) != 1:
            ctx.blocked(
                "res.country.state 'Texas' with country_id.code 'US' does "
                f"not resolve to exactly one record (found {len(texas)}) on "
                f"{ctx.env.key}. The name-only fallback branch cannot be "
                "asserted deterministically until the state data is "
                "de-duplicated.")
        texas = texas[0]
        duplicates = rpc.call("res.country.state", "search_count",
                              [("name", "=", "Texas")])
        ctx.check("states named 'Texas' in ANY country", 1, duplicates)
        us_id = m2o_id(texas["country_id"])
        ctx.log(f"Texas = {texas['id']}, United States = {us_id}")

    try:
        with ctx.step("Step 3: the CSV header carries no country column — "
                      "the country can only be derived"):
            from tests.wf020.common import CSV_COLUMNS
            ctx.check_true("no country column in the nine-column header",
                           not any(c.startswith("country")
                                   for c in CSV_COLUMNS),
                           actual_desc=str(CSV_COLUMNS))

        with ctx.step("Steps 1-2, 4-5, 8, 11-12: one file per state variant "
                      "through the real ETL"):
            variants = {
                "canonical": "Texas (US)",
                "name_only": "Texas",
                "wrong_code": "Texas (XX)",
                "blank": "",
                "unknown": "Not A State (US)",
                "no_space": "Texas(US)",
                "two_word": "New York (US)",
                "lower_case": "texas (us)",
            }
            results = {}
            for label, value in variants.items():
                vref = ref_for(f"s-{label}")
                vfile, _row = run_supplier_import(
                    ctx,
                    [supplier_row(vref, fx(f"{MARK} State {label}"),
                                  state=value)],
                    file_label=f"state-{label}")
                partner = partner_by_ref(rpc, vref, FIELDS)
                errs = _row_errors(rpc, vfile)
                results[label] = {
                    "created": partner is not None,
                    "state_id": m2o_id(partner["state_id"]) if partner else None,
                    "country_id": (m2o_id(partner["country_id"])
                                   if partner else None),
                    "state_error": STATE_ERROR in errs,
                }
            ctx.log(f"state variant results: {results!r}")

        with ctx.step("Step 2: the canonical form resolves the state and "
                      "DERIVES the country"):
            ctx.check("canonical state_id", texas["id"],
                      results["canonical"]["state_id"])
            ctx.check("canonical country_id derived from the state", us_id,
                      results["canonical"]["country_id"])

        with ctx.step("Step 4: the name-only form falls back and resolves "
                      "to the same state, country still derived"):
            ctx.check("name-only state_id", texas["id"],
                      results["name_only"]["state_id"])
            ctx.check("name-only country_id", us_id,
                      results["name_only"]["country_id"])

        with ctx.step("Step 5: a WRONG country code still resolves — the "
                      "name-plus-code search finds nothing, then the "
                      "name-only fallback runs, so the code in the file is "
                      "effectively advisory"):
            ctx.check("wrong-code state_id", texas["id"],
                      results["wrong_code"]["state_id"])
            ctx.check("wrong-code country_id", us_id,
                      results["wrong_code"]["country_id"])

        with ctx.step("Step 6: a blank clears BOTH state and country"):
            ctx.check("blank state_id", None, results["blank"]["state_id"])
            ctx.check("blank country_id", None,
                      results["blank"]["country_id"])

        with ctx.step("Steps 8-9: an unknown name fails with the exact "
                      "message and creates no partner"):
            ctx.check_true(f"unknown state raised {STATE_ERROR!r}",
                           results["unknown"]["state_error"],
                           actual_desc=repr(results["unknown"]))
            ctx.check("unknown-state partner created", False,
                      results["unknown"]["created"])

        with ctx.step("Step 11: 'Texas(US)' with no space fails — the regex "
                      "requires one literal space, so the parse falls "
                      "through to a name-only search on the whole string"):
            ctx.check_true(f"no-space form raised {STATE_ERROR!r}",
                           results["no_space"]["state_error"],
                           actual_desc=repr(results["no_space"]))

        with ctx.step("Step 12: a two-word state splits correctly — the "
                      "greedy (.+) does not consume part of the name"):
            new_york = rpc.search_read("res.country.state",
                                       [("name", "=", "New York"),
                                        ("country_id.code", "=", "US")],
                                       ["id"])
            if not new_york:
                ctx.log("'New York (US)' is absent from this dataset — the "
                        "two-word assertion is skipped, not weakened")
            else:
                ctx.check("two-word state_id", new_york[0]["id"],
                          results["two_word"]["state_id"])
                ctx.check("two-word country_id", us_id,
                          results["two_word"]["country_id"])

        with ctx.step("Step 10: record whether the search is "
                      "case-sensitive"):
            lower = results["lower_case"]
            ctx.log(f"'texas (us)' -> {lower!r}")
            ctx.check_true(
                "the case-sensitivity answer is recorded",
                lower["state_error"] or lower["state_id"] is not None,
                actual_desc=("case-INSENSITIVE: resolved to state "
                             f"{lower['state_id']}" if lower["state_id"]
                             else "case-SENSITIVE: row failed with "
                                  f"{STATE_ERROR!r}"))
    finally:
        with ctx.step("Cleanup WF-020 fixtures"):
            try:
                sweep_wf020(rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")
