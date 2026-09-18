"""DATAONE-WF-019 — the point of the workflow: TC325.

Reconciliation is what closes a bill against a payment. A payment that
posts but does not reconcile leaves the payable open, the AP ageing wrong
and the supplier apparently unpaid — while the cash has left. This case
captures the complete reconciliation SHAPE of a partial and a full
settlement and asserts it survives the upgrade.

Two shapes, and they differ in exactly one respect
--------------------------------------------------
* **Partial** (100.00 against 500.00): the bill's payable line gains a
  matched counterpart and the residual falls, and ``full_reconcile_id``
  stays empty on BOTH sides. A partial reconciliation that creates a
  full-reconcile record is broken regardless of version.
* **Full** (250.00 against 250.00): the residual reaches zero,
  ``payment_state`` reads paid, and the SAME ``full_reconcile_id`` appears
  on the bill's payable line and the payment's outstanding line.

The side matters too. ``_apply_payment_to_invoice``
(``account_payment.py:53-60``) selects the payment's **debit** lines for a
vendor bill and its **credit** lines for a customer invoice, because a
vendor bill's payable line is a credit and needs a debit to match it.
Choosing the wrong side produces a payment that posts and reconciles
against nothing — which is precisely the SILENT v19 failure mode the delta
warns about for the reworked payment area.

Why this is a DATA_RECONCILIATION case and not a plain assertion
----------------------------------------------------------------
The workbook's steps 14-15 are "dump the v17 shape; on v19 run the same
rows through the replacement for ``js_assign_outstanding_line`` and assert
equivalence — byte-equality of ids is not required, equivalence of effect
is." That is exactly what ``framework.fg_common.reconcile`` does, and the
capture below is built from VALUES only (account type, display type,
debit, credit, residual, whether a full-reconcile exists, how many matched
partials) so a v17 snapshot and a v19 snapshot of the same fixture are
comparable across databases.

One correction to the workbook's v19 watch item
-----------------------------------------------
The workbook calls ``js_assign_outstanding_line`` this workflow's LOUD v19
blocker and says "there is no port of the current call". Verified against
both trees: the method is **byte-identical between v17 and v19** and needs
no work. The break the workbook does not record is the removal of
``account.payment._inherits = {'account.move': 'move_id'}``, documented at
``dto_account_workday/models/account_payment.py:12-44``. This case
therefore asserts the reconciliation effect rather than the method name —
which is what the workbook asked for anyway, and which stays correct
whichever replacement a future port chooses.

Step 16 (a bill carrying a ``line_subsection`` line) is exercised where
the value exists: ``_apply_payment_to_invoice`` selects across
``line_ids`` by debit/credit, so a new line type changes the set offered
to reconciliation. The capture records the display types present, so a new
one appearing shows up as a difference rather than as silence.

EXPECTED v17 OUTCOME: PASS — captures and persists the baseline.
EXPECTED v19 OUTCOME: PASS when both shapes are equivalent; BLOCKED when
no v17 baseline has been captured yet.
"""
from framework.fg_common import reconcile
from framework.registry import test_case
from tests.wf019.common import (MARK, WORKFLOW, WORKFLOW_NAME,  # noqa: F401
                                base_url, bill_state, document_link,
                                ensure_product, ensure_vendor, fx, m2o_id,
                                make_bill, partial_amounts, payment_journal,
                                payments_for, reconciliation_shape,
                                require_payment_import, restore_company,
                                retarget_payment_journal, row, run_import,
                                sweep_wf019, trace, workday_id)


def _capture(ctx):
    """Settle one bill partially and one fully; snapshot both shapes."""
    rpc = ctx.adapter.rpc
    sweep_wf019(rpc)
    require_payment_import(ctx)
    journal_id, method_names = payment_journal(ctx)
    method = method_names[0]

    snapshot = {"journal.outbound_method_line_names": sorted(method_names)}
    cid = None
    original = {}
    try:
        cid, original = retarget_payment_journal(ctx, journal_id)
        vendor_id = ensure_vendor(rpc)
        product_id = ensure_product(ctx)
        pb_a, a_row = make_bill(ctx, vendor_id, 500.0, "REC-201",
                                label="PB-A", product_id=product_id)
        pb_b, b_row = make_bill(ctx, vendor_id, 250.0, "REC-202",
                                label="PB-B", product_id=product_id)

        # Step 1: the BEFORE shape, so "the reconciliation did something"
        # is provable rather than assumed.
        snapshot["before.pb_a_shape"] = reconciliation_shape(rpc, [pb_a])
        snapshot["before.pb_a_residual"] = a_row["amount_residual"]
        snapshot["before.pb_b_residual"] = b_row["amount_residual"]

        url = base_url(rpc)
        run_import(ctx, [
            # Step 2: a PARTIAL payment — 100.00 against 500.00.
            row(workday_id("SP", 1), workday_id("SID", 1),
                bill_ref_value=a_row["ref"],
                document_link=document_link(url, pb_a),
                amount="100.00", payment_type=method,
                reference=f"TRX-{fx('R1')}"),
            # Step 9: a FULL payment — 250.00 against 250.00.
            row(workday_id("SP", 2), workday_id("SID", 2),
                bill_ref_value=b_row["ref"], document_link="",
                amount="250.00", payment_type=method,
                reference=f"TRX-{fx('R2')}"),
        ], file_label="reconciliation")

        # --- steps 3-8: the partial ------------------------------------
        a_after = bill_state(rpc, pb_a)
        snapshot["partial.residual"] = round(a_after["amount_residual"], 2)
        snapshot["partial.payment_state"] = a_after["payment_state"]
        snapshot["partial.bill_shape"] = reconciliation_shape(rpc, [pb_a])
        snapshot["partial.partial_amounts"] = partial_amounts(rpc, [pb_a])

        payment_a = payments_for(rpc, workday_id("SP", 1))
        payment_a_move = m2o_id(payment_a[0]["move_id"]) if payment_a else 0
        snapshot["partial.payment_shape"] = (
            reconciliation_shape(rpc, [payment_a_move])
            if payment_a_move else [])
        # Step 8: which SIDE of the payment was consumed. A vendor bill's
        # payable line is a credit, so the payment must supply the DEBIT.
        if payment_a_move:
            consumed = rpc.search_read(
                "account.move.line",
                [("move_id", "=", payment_a_move),
                 ("matched_credit_ids", "!=", False)],
                ["debit", "credit"])
            snapshot["partial.consumed_payment_side"] = sorted(
                ("debit" if (line["debit"] or 0) > 0 else "credit")
                for line in consumed)
        # Step 6: a partial must NOT create a full-reconcile record.
        snapshot["partial.full_reconciles"] = len(rpc.search(
            "account.move.line",
            [("move_id", "in", [pb_a, payment_a_move]),
             ("full_reconcile_id", "!=", False)])) if payment_a_move else 0

        # --- steps 10-12: the full -------------------------------------
        b_after = bill_state(rpc, pb_b)
        snapshot["full.residual"] = round(b_after["amount_residual"], 2)
        snapshot["full.payment_state"] = b_after["payment_state"]
        snapshot["full.bill_shape"] = reconciliation_shape(rpc, [pb_b])
        snapshot["full.partial_amounts"] = partial_amounts(rpc, [pb_b])

        payment_b = payments_for(rpc, workday_id("SP", 2))
        payment_b_move = m2o_id(payment_b[0]["move_id"]) if payment_b else 0
        if payment_b_move:
            groups = rpc.search_read(
                "account.move.line",
                [("move_id", "in", [pb_b, payment_b_move]),
                 ("full_reconcile_id", "!=", False)],
                ["full_reconcile_id", "move_id"])
            # Compared as a COUNT of distinct groups, not as an id: the id
            # is not comparable across databases, but "both sides share one
            # group" is exactly what step 12 asks for.
            snapshot["full.lines_in_a_full_group"] = len(groups)
            snapshot["full.distinct_full_groups"] = len(
                {m2o_id(g["full_reconcile_id"]) for g in groups})
            snapshot["full.moves_in_the_group"] = len(
                {m2o_id(g["move_id"]) for g in groups})

        # --- step 13: the ledger nets to zero --------------------------
        touched = [m for m in (pb_a, pb_b, payment_a_move, payment_b_move)
                   if m]
        lines = rpc.search_read("account.move.line",
                                [("move_id", "in", touched)], ["balance"])
        snapshot["ledger.net_balance"] = round(
            sum(line["balance"] or 0.0 for line in lines), 2)
        snapshot["ledger.line_count"] = len(lines)

        # --- step 16's input: which display types exist on these moves --
        # v19 (delta §2.5) adds line_subsection and three non_deductible_*
        # values. _apply_payment_to_invoice selects across line_ids by
        # debit/credit, so a new type changes the set offered to
        # reconciliation. Captured so a new one is a DIFFERENCE, not
        # silence.
        display_types = rpc.read_group(
            "account.move.line", [("move_id", "in", touched)],
            ["__count"], ["display_type"], lazy=False)
        snapshot["display_types_present"] = sorted(
            (group.get("display_type") or "", group.get("__count", 0))
            for group in display_types)
    finally:
        if cid:
            restore_company(ctx, cid, original)
    return snapshot


@test_case(
    id="TEST-WF019-TC325",
    name="The payment is reconciled against the bill and the residual falls",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account_workday", priority="P0", kind="DATA", order=19325,
    description="Settles one bill partially and one fully through the real "
                "ETL and captures the complete reconciliation shape of "
                "both — residual, payment_state, the per-line debit/credit/"
                "residual/full-reconcile/matched-count tuples, the partial "
                "amounts, which side of the payment was consumed, and the "
                "net ledger balance — then asserts zero difference against "
                "the v17 baseline. Anchors the two invariants that hold on "
                "either version: a partial creates no full-reconcile "
                "record, and the ledger nets to zero.",
    traceability=trace("DATAONE-TC325"))
def test_tc325(ctx):
    with ctx.step("What this case corrects in the workbook's v19 watch"):
        ctx.log("The workbook names js_assign_outstanding_line "
                "(account_payment.py:60) as WF-019's LOUD v19 blocker and "
                "says there is no port of the current call. Verified "
                "against both trees: the method is byte-identical between "
                "v17 and v19 and needs no work. The real break is the "
                "removal of account.payment._inherits = {'account.move': "
                "'move_id'}, which is why workday_document and "
                "export_workday are related fields in this module and why "
                "they are written to the MOVE after action_post. This case "
                "therefore asserts the reconciliation EFFECT, not the "
                "method name — which is what the workbook's step 15 asked "
                "for, and which stays correct whichever replacement a "
                "future port chooses.")

    with ctx.step("Money-safety note"):
        ctx.log("This case CREATES AND POSTS PAYMENTS against its own "
                "token-scoped bills and vendor. Nothing here settles a live "
                "payable: every bill's ref carries WF019-<token>- and the "
                "vendor is created per execution. A posted, reconciled "
                "payment cannot be unlinked, so sweep_wf019 leaves what it "
                "cannot remove and the fresh token is the isolation.")

    reconcile(
        ctx, "DATAONE-TC325", _capture,
        anchors={
            # Step 6 — true on BOTH versions. A partial reconciliation that
            # creates a full-reconcile record is broken whether or not the
            # upgrade broke it.
            "partial.full_reconciles": 0,
            # Step 13 — the general ledger is unchanged in total.
            "ledger.net_balance": 0.0,
            # Steps 3-4 and 10-11 — the settlements themselves.
            "partial.residual": 400.0,
            "partial.payment_state": "partial",
            "full.residual": 0.0,
            "full.payment_state": "paid",
            # Step 8 — a vendor bill's payable line is a CREDIT, so the
            # payment must supply the DEBIT. The wrong side posts and
            # reconciles against nothing, silently.
            "partial.consumed_payment_side": ["debit"],
            # Step 12 — one full-reconcile group spanning both moves.
            "full.distinct_full_groups": 1,
            "full.moves_in_the_group": 2,
        })
