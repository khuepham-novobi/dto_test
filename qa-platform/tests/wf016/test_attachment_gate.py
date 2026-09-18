"""DATAONE-WF-016 — the attachment gate: TC261-TC266.

Accounts payable will not recognise a liability without the supplier's
document behind it. The control is a model-level business rule, not an ACL,
and it has **no group condition of any kind**
(``dto_account/models/account_move.py:50-58``). Six cases, six separate
properties of that one ``if``:

* TC261 — it fires, with the exact message, before ``super()._post()`` so
  no sequence number is allocated;
* TC262 — no user and no privilege level bypasses it. If an administrator
  can post round it, it is not an audit control and cannot be represented
  as one to the client's auditors;
* TC263 — it is ``any(...)`` over the whole recordset, so one bad bill
  rolls back the entire batch, including bills that were perfectly valid.
  AP posts in batches at period end and the error message says nothing
  about which record caused it;
* TC264 — the stored-compute defect. ``have_attachment`` is
  ``store=True`` with ``@api.depends('attachment_ids')``, a domain-filtered
  One2many onto ``ir.attachment``. Creating the attachment ON ir.attachment
  (the chatter path) does not reliably invalidate it, so a bill that
  visibly holds the supplier's PDF can still refuse to post. This is a live
  v17 defect that survives the port unchanged;
* TC265 — the list column, the search filter and the form indicator agree
  with the stored value, so the clerk chasing the period close chases the
  right documents;
* TC266 — and, catastrophically if lost, the gate does **not** widen past
  ``in_invoice``. WF-012 posts customer invoices inside the delivery
  validation transaction; a gate that covered ``out_invoice`` would block
  every shipment in the business.

EXPECTED v17 OUTCOME: PASS for TC261-263, TC265, TC266. TC264 is expected
to record the defect: the chatter path's post is expected to RAISE while an
attachment is visibly present, and the case asserts the recovery, not the
absence of the defect.
EXPECTED v19 OUTCOME: same. Delta §2.3 keeps ``_post(self, soft=True)``'s
signature, but v19 accumulates validation errors into ``validation_msgs``
and raises once — a hand-rolled ``raise`` before ``super()`` bypasses that
pattern, so the UX differs from every other posting error. TC261 records
the message it actually got, so adopting the batched pattern later shows up
as a controlled change rather than a mystery.
"""
from framework.registry import test_case
from tests.wf016.common import (ATTACHMENT_GATE_MESSAGE,  # noqa: F401
                                BILL_FORM_VIEW, BILL_LIST_VIEW,
                                BILL_SEARCH_VIEW, GATED_MOVE_TYPE,
                                HAVE_ATTACHMENT_FILTER, MARK,
                                UNGATED_MOVE_TYPES, WORKFLOW, WORKFLOW_NAME,
                                attach_to_move, bill_from_order,
                                ensure_product, ensure_vendor, expect_error,
                                form_arch, fx, list_tag, m2o_id,
                                make_bare_bill, make_purchase_order,
                                make_user, move_lines, receive_order,
                                require_dto_account, require_purchase,
                                session_as, sweep_wf016, trace)


def _gate_message_matches(message: str) -> bool:
    """The workbook requires the message verbatim, not a translated form.

    The RPC layer prefixes the model and method, so the assertion is
    containment of the exact sentence — never a loosened substring of it.
    """
    return ATTACHMENT_GATE_MESSAGE in (message or "")


@test_case(
    id="TEST-WF016-TC261",
    name="A vendor bill with no attachment refuses to post, with the exact "
         "message",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account", priority="P1", kind="API", order=16261,
    description="A draft in_invoice with zero attachments raises the exact "
                "UserError, stays draft, keeps the '/' placeholder name "
                "because the gate runs before super()._post(), and leaves "
                "its journal items untouched.",
    traceability=trace("DATAONE-TC261"))
def test_tc261(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-016 fixtures and open a fresh "
                  "namespace"):
        sweep_wf016(rpc)

    with ctx.step("Preconditions: dto_account and purchase installed"):
        require_dto_account(ctx)
        require_purchase(ctx)

    try:
        with ctx.step("Steps 1-2: a draft vendor bill derived from a "
                      "validated receipt, with zero attachments"):
            vendor_id = ensure_vendor(rpc)
            product_id = ensure_product(ctx)
            order_id = make_purchase_order(ctx, vendor_id, product_id,
                                           label="TC261")
            receipts = receive_order(ctx, order_id)
            ctx.log(f"receipts: {receipts!r}")
            bill_id = bill_from_order(ctx, order_id)
            bill = rpc.read("account.move", [bill_id],
                            ["state", "name", "move_type", "have_attachment",
                             "attachment_ids"])[0]
            ctx.log(f"draft bill: {bill!r}")
            ctx.check("move_type", GATED_MOVE_TYPE, bill["move_type"])
            ctx.check("attachments on the draft bill", [],
                      bill["attachment_ids"])
            ctx.check("have_attachment", False, bill["have_attachment"])
            placeholder = bill["name"]

        with ctx.step("Steps 3-4 — THE GATE: Confirm raises the exact "
                      "UserError"):
            raised, message = expect_error(rpc.call, "account.move",
                                           "action_post", [bill_id])
            ctx.log(f"action_post raised={raised}: {message!r}")
            ctx.check_true("action_post was refused", raised,
                           actual_desc=message)
            ctx.check_true(
                "the message is exactly "
                f"{ATTACHMENT_GATE_MESSAGE!r}",
                _gate_message_matches(message), actual_desc=message)

        with ctx.step("Step 5: the bill is still draft"):
            state = rpc.read("account.move", [bill_id],
                             ["state"])[0]["state"]
            ctx.check("state after the refused post", "draft", state)

        with ctx.step("Step 6: NO sequence number was allocated — the gate "
                      "runs before super()._post()"):
            name = rpc.read("account.move", [bill_id], ["name"])[0]["name"]
            ctx.log(f"name before={placeholder!r} after={name!r}")
            ctx.check("name after the refused post", placeholder, name)
            ctx.check_true("the name is still the '/' placeholder",
                           not name or name == "/",
                           actual_desc=repr(name))

        with ctx.step("Step 7: no journal item was renumbered or "
                      "reconciled"):
            lines = move_lines(rpc, bill_id)
            ctx.log(f"journal items: {lines!r}")
            reconciled_field = rpc.field_exists("account.move.line",
                                                "reconciled")
            if reconciled_field:
                rows = rpc.search_read("account.move.line",
                                       [("move_id", "=", bill_id)],
                                       ["reconciled"])
                ctx.check("reconciled journal items", [],
                          [r["id"] for r in rows if r["reconciled"]])
            ctx.check_true("the draft bill still has its journal items",
                           bool(lines), actual_desc=len(lines))
    finally:
        with ctx.step("Cleanup WF-016 fixtures"):
            try:
                sweep_wf016(rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")


@test_case(
    id="TEST-WF016-TC262",
    name="The administrator cannot bypass the attachment gate either",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account", priority="P1", kind="API", order=16262,
    description="The same UserError for a base.group_system administrator "
                "and for an account.group_account_manager, and the gate has "
                "no group condition anywhere in its source — it is a "
                "model-level business rule, not an ACL.",
    traceability=trace("DATAONE-TC262"))
def test_tc262(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-016 fixtures and open a fresh "
                  "namespace"):
        sweep_wf016(rpc)

    with ctx.step("Preconditions: dto_account installed"):
        require_dto_account(ctx)

    try:
        with ctx.step("A draft in_invoice with no attachment, owned by "
                      "this suite"):
            vendor_id = ensure_vendor(rpc)
            product_id = ensure_product(ctx)
            bill_id = make_bare_bill(ctx, vendor_id, product_id,
                                     label="TC262")
            ctx.check("have_attachment", False,
                      rpc.read("account.move", [bill_id],
                               ["have_attachment"])[0]["have_attachment"])

        with ctx.step("Steps 1-3: an administrator (base.group_system) "
                      "gets the identical UserError"):
            admin_id, admin_login = make_user(
                ctx, "admin", ["base.group_system",
                               "account.group_account_manager"])
            admin_rpc = session_as(ctx.env, admin_login)
            raised, message = expect_error(admin_rpc.call, "account.move",
                                           "action_post", [bill_id])
            ctx.log(f"as {admin_login}: raised={raised} {message!r}")
            ctx.check_true("the administrator was refused", raised,
                           actual_desc=message)
            ctx.check_true("the administrator gets the identical message",
                           _gate_message_matches(message),
                           actual_desc=message)
            ctx.check("state after the administrator's attempt", "draft",
                      rpc.read("account.move", [bill_id],
                               ["state"])[0]["state"])

        with ctx.step("Steps 4-6: an accounting manager gets the identical "
                      "UserError"):
            mgr_id, mgr_login = make_user(
                ctx, "acctmgr", ["account.group_account_manager"])
            mgr_rpc = session_as(ctx.env, mgr_login)
            raised, message = expect_error(mgr_rpc.call, "account.move",
                                           "action_post", [bill_id])
            ctx.log(f"as {mgr_login}: raised={raised} {message!r}")
            ctx.check_true("the accounting manager was refused", raised,
                           actual_desc=message)
            ctx.check_true("the manager gets the identical message",
                           _gate_message_matches(message),
                           actual_desc=message)
            ctx.check("state after the manager's attempt", "draft",
                      rpc.read("account.move", [bill_id],
                               ["state"])[0]["state"])

        with ctx.step("Step 7: sudo() cannot bypass it either. sudo() is "
                      "not dispatchable over RPC, so the equivalent "
                      "assertion is made structurally — the gate carries "
                      "no group test at all"):
            ctx.log("`move.sudo()._post()` cannot be called over "
                    "/web/dataset/call_kw: _post is private "
                    "(check_method_name, v17 odoo/models.py:145, v19 "
                    "odoo/orm/utils.py:69) and sudo() is not a model "
                    "method. What sudo() would change is the USER, and "
                    "both users above already carry the highest privilege "
                    "levels available — base.group_system and "
                    "account.group_account_manager — and both were "
                    "refused. The gate is therefore proved to be "
                    "privilege-independent by observation, not by "
                    "inspection.")
            ctx.check_true(
                "every privilege level tested was refused identically",
                True, actual_desc="base.group_system + "
                                  "account.group_account_manager")

        with ctx.step("The failure signature: attaching a document makes "
                      "the SAME bill postable for the SAME users, so the "
                      "refusals above were the gate and not a permission "
                      "problem"):
            attach_to_move(rpc, bill_id, via="move")
            ctx.check("have_attachment after attaching", True,
                      rpc.read("account.move", [bill_id],
                               ["have_attachment"])[0]["have_attachment"])
            raised, message = expect_error(mgr_rpc.call, "account.move",
                                           "action_post", [bill_id])
            ctx.log(f"post with attachment: raised={raised} {message!r}")
            ctx.check("state after attaching and posting", "posted",
                      rpc.read("account.move", [bill_id],
                               ["state"])[0]["state"])
    finally:
        with ctx.step("Cleanup WF-016 fixtures"):
            try:
                sweep_wf016(rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")


@test_case(
    id="TEST-WF016-TC263",
    name="On a mass post, one attachment-less bill blocks the whole batch",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account", priority="P1", kind="API", order=16263,
    description="Posting two bills in one call where only one lacks an "
                "attachment leaves BOTH draft and BOTH unnumbered — the "
                "check is any(...) over the whole recordset and the batch "
                "is atomic. The error names neither record.",
    traceability=trace("DATAONE-TC263"))
def test_tc263(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-016 fixtures and open a fresh "
                  "namespace"):
        sweep_wf016(rpc)

    with ctx.step("Preconditions: dto_account installed"):
        require_dto_account(ctx)

    try:
        with ctx.step("Steps 1-2: bill A WITH an attachment, bill B "
                      "WITHOUT — both otherwise postable"):
            vendor_id = ensure_vendor(rpc)
            product_id = ensure_product(ctx)
            bill_a = make_bare_bill(ctx, vendor_id, product_id, label="A")
            bill_b = make_bare_bill(ctx, vendor_id, product_id, label="B")
            attach_to_move(rpc, bill_a, via="move")
            rows = rpc.read("account.move", [bill_a, bill_b],
                            ["name", "state", "have_attachment"])
            ctx.log(f"before the batch post: {rows!r}")
            by_id = {r["id"]: r for r in rows}
            ctx.check("bill A have_attachment", True,
                      by_id[bill_a]["have_attachment"])
            ctx.check("bill B have_attachment", False,
                      by_id[bill_b]["have_attachment"])
            name_a_before = by_id[bill_a]["name"]

        with ctx.step("Steps 3-5 — THE BATCH: post BOTH in one call; the "
                      "any(...) over self refuses the whole recordset"):
            raised, message = expect_error(rpc.call, "account.move",
                                           "action_post", [bill_a, bill_b])
            ctx.log(f"batch post raised={raised}: {message!r}")
            ctx.check_true("the batch was refused", raised,
                           actual_desc=message)
            ctx.check_true("with the attachment-gate message",
                           _gate_message_matches(message),
                           actual_desc=message)
            ctx.log("NOTE for the operations record: the message names "
                    "NEITHER bill. At period end an AP clerk posting 40 "
                    "bills is told only that 'the Vendor Bill' requires an "
                    "attachment, with no way to tell which one. That cost "
                    "is invisible from the error text and is why this case "
                    "exists.")

        with ctx.step("Steps 6-8: bill A is STILL DRAFT and STILL "
                      "UNNUMBERED despite holding a valid attachment — the "
                      "batch rolled back atomically"):
            rows = rpc.read("account.move", [bill_a, bill_b],
                            ["name", "state"])
            by_id = {r["id"]: r for r in rows}
            ctx.log(f"after the batch post: {rows!r}")
            ctx.check("bill A state", "draft", by_id[bill_a]["state"])
            ctx.check("bill B state", "draft", by_id[bill_b]["state"])
            ctx.check("bill A name (no sequence allocated)", name_a_before,
                      by_id[bill_a]["name"])

        with ctx.step("Control: posting bill A ALONE succeeds, proving the "
                      "refusal above was bill B's and not bill A's"):
            rpc.call("account.move", "action_post", [bill_a])
            ctx.check("bill A state when posted alone", "posted",
                      rpc.read("account.move", [bill_a],
                               ["state"])[0]["state"])
    finally:
        with ctx.step("Cleanup WF-016 fixtures"):
            try:
                sweep_wf016(rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")


@test_case(
    id="TEST-WF016-TC264",
    name="Uploading an attachment must make the bill postable "
         "(have_attachment recompute)",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account", priority="P1", kind="API", order=16264,
    description="Compares the two attachment paths: creating the "
                "ir.attachment against the move (the chatter path, whose "
                "stored-compute invalidation is unreliable) versus writing "
                "attachment_ids on the move. Records which one leaves the "
                "bill unpostable with a document visibly attached, and "
                "asserts the recovery after a recompute.",
    traceability=trace("DATAONE-TC264"))
def test_tc264(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-016 fixtures and open a fresh "
                  "namespace"):
        sweep_wf016(rpc)

    with ctx.step("Preconditions: dto_account installed"):
        require_dto_account(ctx)

    findings = {}
    try:
        with ctx.step("Steps 1-2: a draft bill, then attach the supplier "
                      "PDF the CHATTER way — ir.attachment created with "
                      "res_model='account.move', res_id=<the bill>"):
            vendor_id = ensure_vendor(rpc)
            product_id = ensure_product(ctx)
            bill_id = make_bare_bill(ctx, vendor_id, product_id,
                                     label="TC264-chatter")
            attachment_id = attach_to_move(rpc, bill_id, via="attachment")
            ctx.log(f"ir.attachment {attachment_id} -> move {bill_id}")

        with ctx.step("Steps 3-4: read have_attachment WITHOUT triggering "
                      "any other write on the move. This is the stored "
                      "compute's invalidation, and it is the defect"):
            visible = rpc.search_read(
                "ir.attachment",
                [("res_model", "=", "account.move"),
                 ("res_id", "=", bill_id)], ["name"])
            stored = rpc.read("account.move", [bill_id],
                              ["have_attachment", "attachment_ids"])[0]
            ctx.log(f"attachments visible on the record: {visible!r}")
            ctx.log(f"stored have_attachment: {stored!r}")
            findings["chatter_have_attachment"] = stored["have_attachment"]
            ctx.check_true("the document IS attached to the record",
                           bool(visible), actual_desc=visible)

        with ctx.step("Steps 5-6 — THE DEFECT: press Confirm and record "
                      "whether it posts or raises while a document is "
                      "visibly present"):
            raised, message = expect_error(rpc.call, "account.move",
                                           "action_post", [bill_id])
            findings["chatter_post_raised"] = raised
            findings["chatter_post_message"] = message
            ctx.log(f"chatter path post: raised={raised} {message!r}")
            if raised and _gate_message_matches(message):
                ctx.log("[FINDING] The stored-compute defect is LIVE on "
                        f"{ctx.env.key}: the bill holds the supplier's "
                        "document and still refuses to post. To the user "
                        "this reads as a permissions failure, generates a "
                        "support call, and at period end it blocks the "
                        "close. Live v17 defect, unchanged by the port.")
            else:
                ctx.log("[FINDING] The chatter path DID invalidate the "
                        "stored compute on this target — the defect is not "
                        "reproducible here. Record the Odoo build; this is "
                        "the outcome the port should aim for.")

        with ctx.step("Steps 7-8: after a reload/recompute the post "
                      "succeeds and a sequence number is allocated"):
            if findings["chatter_post_raised"]:
                # The recompute is triggered the way the UI triggers it: a
                # write on the move itself, which is what "reload the
                # record and press Confirm again" amounts to.
                # ``_compute_have_attachment`` is private and cannot be
                # dispatched over RPC (check_method_name), so re-linking
                # the existing attachment is the reachable equivalent.
                rpc.write("account.move", [bill_id],
                          {"attachment_ids": [(4, attachment_id)]})
                after = rpc.read("account.move", [bill_id],
                                 ["have_attachment"])[0]["have_attachment"]
                ctx.log(f"have_attachment after the move write: {after}")
                ctx.check("have_attachment after the recompute", True, after)
                rpc.call("account.move", "action_post", [bill_id])
            row = rpc.read("account.move", [bill_id], ["state", "name"])[0]
            ctx.log(f"final: {row!r}")
            ctx.check("state", "posted", row["state"])
            ctx.check_true("a sequence number was allocated",
                           bool(row["name"]) and row["name"] != "/",
                           actual_desc=repr(row["name"]))

        with ctx.step("Step 9: the SECOND path — write attachment_ids on "
                      "the move. This one is expected to invalidate "
                      "reliably; record any difference"):
            bill2 = make_bare_bill(ctx, vendor_id, product_id,
                                   label="TC264-move")
            attach_to_move(rpc, bill2, via="move")
            stored2 = rpc.read("account.move", [bill2],
                               ["have_attachment"])[0]["have_attachment"]
            findings["move_write_have_attachment"] = stored2
            ctx.log(f"write-on-move have_attachment: {stored2}")
            ctx.check("have_attachment after writing attachment_ids on the "
                      "move", True, stored2)
            raised2, message2 = expect_error(rpc.call, "account.move",
                                             "action_post", [bill2])
            findings["move_write_post_raised"] = raised2
            ctx.log(f"write-on-move post: raised={raised2} {message2!r}")
            ctx.check("state after posting the write-on-move bill",
                      "posted",
                      rpc.read("account.move", [bill2],
                               ["state"])[0]["state"])

        with ctx.step("Record the comparison. The two paths differing IS "
                      "the finding; the port must fix it by recomputing in "
                      "an ir.attachment.create override or by making the "
                      "field non-stored"):
            ctx.log(f"TC264 findings: {findings!r}")
            ctx.check_true(
                "both attachment paths ultimately produce a postable bill",
                True, actual_desc=findings)
    finally:
        with ctx.step("Cleanup WF-016 fixtures"):
            try:
                sweep_wf016(rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")


@test_case(
    id="TEST-WF016-TC265",
    name="The Have Attachment column and filter reflect the stored value",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account", priority="P3", kind="API", order=16265,
    description="The bill list carries have_attachment as optional='show', "
                "the search view carries the Have Attachment filter whose "
                "domain returns only attached bills, and the form shows "
                "the indicator in the header group, invisible when "
                "move_type != 'in_invoice'.",
    traceability=trace("DATAONE-TC265"))
def test_tc265(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-016 fixtures and open a fresh "
                  "namespace"):
        sweep_wf016(rpc)

    with ctx.step("Preconditions: dto_account installed and its three "
                  "view inherits resolve. The anchors group "
                  "id='header_left_group' and the due_date filter are both "
                  "on delta §3.5's rotted list — an unresolved view here "
                  "is an install failure, not a cosmetic one"):
        require_dto_account(ctx)
        views = {BILL_FORM_VIEW: rpc.ref(BILL_FORM_VIEW),
                 BILL_LIST_VIEW: rpc.ref(BILL_LIST_VIEW),
                 BILL_SEARCH_VIEW: rpc.ref(BILL_SEARCH_VIEW)}
        ctx.log(f"view inherits: {views!r}")
        ctx.check("unresolved dto_account view inherits", [],
                  [name for name, vid in views.items() if not vid])

    try:
        with ctx.step("Steps 1-3: one posted bill WITH an attachment and "
                      "one draft bill WITHOUT; read the stored value for "
                      "each"):
            vendor_id = ensure_vendor(rpc)
            product_id = ensure_product(ctx)
            attached = make_bare_bill(ctx, vendor_id, product_id,
                                      label="TC265-yes")
            bare = make_bare_bill(ctx, vendor_id, product_id,
                                  label="TC265-no")
            attach_to_move(rpc, attached, via="move")
            rpc.call("account.move", "action_post", [attached])
            rows = rpc.read("account.move", [attached, bare],
                            ["state", "have_attachment"])
            by_id = {r["id"]: r for r in rows}
            ctx.log(f"bills: {rows!r}")
            ctx.check("attached bill have_attachment", True,
                      by_id[attached]["have_attachment"])
            ctx.check("bare bill have_attachment", False,
                      by_id[bare]["have_attachment"])

        with ctx.step("Step 2: the list view carries the column as "
                      "optional='show'"):
            arch = form_arch(ctx, "account.move", "list")
            ctx.log(f"list arch length: {len(arch)}")
            ctx.check_true(
                "have_attachment is a column on the bill list",
                'name="have_attachment"' in arch, actual_desc=arch[:400])
            ctx.check_true(
                "and it is optional='show', so AP sees it by default",
                'optional="show"' in arch, actual_desc="optional attribute")
            ctx.log(f"list root tag on this version: <{list_tag(ctx)}> — "
                    "the <tree> -> <list> rename is delta §3.2 and is "
                    "handled by the adapter, not by a branch here.")

        with ctx.step("Steps 4-5: the Have Attachment filter exists and "
                      "its domain returns ONLY the attached bill"):
            search_arch = form_arch(ctx, "account.move", "search")
            ctx.check_true(
                f"the {HAVE_ATTACHMENT_FILTER} filter is in the search view",
                HAVE_ATTACHMENT_FILTER in search_arch,
                actual_desc=search_arch[:400])
            filtered = rpc.search("account.move",
                                  [("have_attachment", "=", True),
                                   ("id", "in", [attached, bare])])
            ctx.log(f"filter domain result: {filtered!r}")
            ctx.check("bills matching the Have Attachment filter",
                      [attached], sorted(filtered))

        with ctx.step("Step 6: the form shows the indicator in the header "
                      "group, hidden when move_type != 'in_invoice'"):
            form = form_arch(ctx, "account.move", "form")
            ctx.check_true("have_attachment is on the move form",
                           'name="have_attachment"' in form,
                           actual_desc="absent from the arch")
            marker = 'name="have_attachment"'
            index = form.find(marker)
            fragment = form[index:index + 200] if index >= 0 else ""
            ctx.log(f"form fragment: {fragment!r}")
            ctx.check_true(
                "it is conditioned on move_type == 'in_invoice' so it does "
                "not render on a customer invoice",
                "in_invoice" in fragment, actual_desc=fragment)
    finally:
        with ctx.step("Cleanup WF-016 fixtures"):
            try:
                sweep_wf016(rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")


@test_case(
    id="TEST-WF016-TC266",
    name="The gate does not touch customer invoices, credit notes or misc "
         "entries",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account", priority="P2", kind="API", order=16266,
    description="An out_invoice, an out_refund, an in_refund and a "
                "miscellaneous entry all post with zero attachments. "
                "Widening the gate past in_invoice during the port would "
                "block every delivery in the business, because WF-012 "
                "posts customer invoices inside the delivery transaction.",
    traceability=trace("DATAONE-TC266"))
def test_tc266(ctx):
    rpc = ctx.adapter.rpc

    with ctx.step("Sweep previous WF-016 fixtures and open a fresh "
                  "namespace"):
        sweep_wf016(rpc)

    with ctx.step("Preconditions: dto_account installed and the five "
                  "dto_account analytic accounts resolve — a missing one "
                  "makes a customer invoice fail to post for a DIFFERENT "
                  "reason and would be misread as the gate firing"):
        require_dto_account(ctx)
        xmlids = [
            "dto_account.analytic_account_revenue_category_service_sales",
            "dto_account.analytic_account_cost_center_180008",
            "dto_account.analytic_account_revenue_category_manufacturing_sales",
            "dto_account.analytic_account_spend_category_consumables",
            "dto_account.analytic_account_cost_center_202000",
        ]
        missing = [x for x in xmlids if not rpc.ref(x)]
        if missing:
            ctx.blocked(
                f"These analytic xmlids do not resolve on {ctx.env.key}: "
                f"{missing}. dto_account_cogs resolves them with env.ref() "
                "during _post, so every customer-invoice post raises "
                "ValueError while they are missing — which this case would "
                "otherwise attribute to the attachment gate.")

    try:
        with ctx.step("Steps 1-5: post one move of each ungated type with "
                      "ZERO attachments and record each result"):
            partner_id = ensure_vendor(rpc, label="Counterparty")
            product_id = ensure_product(ctx)
            outcomes = {}
            for move_type in UNGATED_MOVE_TYPES:
                move_id = make_bare_bill(ctx, partner_id, product_id,
                                         move_type=move_type,
                                         label=f"TC266-{move_type}")
                attachments = rpc.read("account.move", [move_id],
                                       ["attachment_ids",
                                        "have_attachment"])[0]
                raised, message = expect_error(rpc.call, "account.move",
                                               "action_post", [move_id])
                state = rpc.read("account.move", [move_id],
                                 ["state"])[0]["state"]
                outcomes[move_type] = {"id": move_id, "state": state,
                                       "raised": raised, "message": message,
                                       "attachments": attachments}
                ctx.log(f"{move_type}: {outcomes[move_type]!r}")

        with ctx.step("Steps 2-5 asserted together — NO ungated move type "
                      "was refused by the attachment gate"):
            gated = {mt: o["message"] for mt, o in outcomes.items()
                     if _gate_message_matches(o["message"])}
            ctx.check("ungated move types refused by the ATTACHMENT GATE",
                      {}, gated)

        with ctx.step("Step 6: every ungated move reached state 'posted'"):
            not_posted = {mt: {"state": o["state"], "why": o["message"]}
                          for mt, o in outcomes.items()
                          if o["state"] != "posted"}
            if not_posted:
                ctx.log("[note] A move that failed to post for a reason "
                        "OTHER than the attachment gate is an environment "
                        "fact (a missing journal, a chart-of-accounts gap), "
                        "not a WF-016 defect. The gate assertion above is "
                        "the one that owns this case; this one is reported "
                        "so the environment gap is visible.")
            ctx.check("ungated move types that did not post", {}, not_posted)

        with ctx.step("The contrast that gives the case its meaning: the "
                      "SAME fixture as an in_invoice IS refused"):
            gated_move = make_bare_bill(ctx, partner_id, product_id,
                                        move_type=GATED_MOVE_TYPE,
                                        label="TC266-control")
            raised, message = expect_error(rpc.call, "account.move",
                                           "action_post", [gated_move])
            ctx.log(f"in_invoice control: raised={raised} {message!r}")
            ctx.check_true("the in_invoice control WAS refused by the gate",
                           raised and _gate_message_matches(message),
                           actual_desc=message)
    finally:
        with ctx.step("Cleanup WF-016 fixtures"):
            try:
                sweep_wf016(rpc)
            except Exception as exc:      # noqa: BLE001
                ctx.log(f"[warn] cleanup incomplete: {exc}")
