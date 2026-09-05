"""DATAONE-WF-009 — group membership and its two constraints: TC136, TC137.

TC136 is about the SHAPE of a replacement group: setting
``replacement_product_ids`` on any one member must produce a single group in
which every member sees every other, whichever member you start from, and
removing one member must split the group cleanly rather than leaving a
one-sided pointer behind.

TC137 is the pair of guards on that shape: a product cannot list itself, and
no product can sit in two groups at once.

EXPECTED v19 OUTCOME: PASS for both. Neither case depends on stock, on an MO,
or on anything the port changed — they exercise the module's own model layer,
which is why they are the cheapest signal that Stage 3 installed correctly.

Two observation notes, both verified against the source and neither touching
the workbook's expected result:

* Step 15 of TC136 ("on a multi-variant template the page shows only the
  explanatory note") and steps 12/2 of the substitution cases describe FORM
  RENDERING — decoration-info, a notebook page, an icon. Those are view
  concerns, asserted here through the view architecture rather than a
  browser, because this suite is API-kind: a tour would be the right tool and
  the workbook classes WF-009 as PYTHON_UNIT.
* TC137 step 8 asks for a raw SQL insert to prove the constraint is enforced
  in the database. This suite reaches Odoo over RPC and has no SQL channel to
  the target, so it proves the same thing the way a client can: the write is
  rejected with the constraint's own message, which only the database
  constraint produces (``models.Constraint`` on
  mrp_component_replacement.py:34 — there is no Python guard for it).
"""
from framework.registry import test_case
from tests.wf009.common import (ONE_GROUP_ERROR, SELF_REPLACEMENT_ERROR,
                                WORKFLOW, WORKFLOW_NAME, group_members,
                                group_of, m2o_id, make_product, open_namespace,
                                require_mrp, require_replacement_module,
                                set_replacements, sweep_wf009, trace)
from adapters.base import OdooRPCError


@test_case(
    id="TEST-WF009-TC136",
    name="Replacement groups are reciprocal, order-independent, and split "
         "cleanly on removal",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_mrp_component_replacement",
    priority="P1", kind="API", order=9136,
    description="Setting replacement products on one member builds a single "
                "group every member can see; building the same set from a "
                "different member gives identical membership; removing one "
                "member leaves a clique of three and clears the removed "
                "product entirely.",
    traceability=trace("DATAONE-TC136"))
def test_tc136(ctx):
    require_replacement_module(ctx)
    require_mrp(ctx)
    rpc = ctx.adapter.rpc
    open_namespace(ctx)
    try:
        with ctx.step("Create four interchangeable components, none grouped"):
            a = make_product(rpc, "CONN-A")
            b = make_product(rpc, "CONN-B")
            c = make_product(rpc, "CONN-C")
            d = make_product(rpc, "CONN-D")
            ctx.check("products start ungrouped", [None, None, None, None],
                      [group_of(rpc, p) for p in (a, b, c, d)])

        with ctx.step("Set A's replacements to B, C, D"):
            set_replacements(rpc, a, [b, c, d])
            gid = group_of(rpc, a)
            ctx.check_true("A now belongs to a group", bool(gid), str(gid))

        with ctx.step("Every other member sees the same group — reciprocity"):
            ctx.check("B, C and D share A's group", [gid, gid, gid],
                      [group_of(rpc, b), group_of(rpc, c), group_of(rpc, d)])
            for name, pid, others in (("B", b, {a, c, d}), ("C", c, {a, b, d}),
                                      ("D", d, {a, b, c})):
                seen = {m2o_id(r["product_id"]) for r in group_members(rpc, gid)}
                ctx.check(f"{name} sees the other three", others, seen - {pid})

        with ctx.step("Exactly one group, four lines, sequenced 10/20/30/40"):
            members = group_members(rpc, gid)
            ctx.check("line count", 4, len(members))
            ctx.check("sequences", [10, 20, 30, 40],
                      [m["sequence"] for m in members])

        with ctx.step("The group name is the comma-joined member names"):
            grp = rpc.read("mrp.component.replacement.group", [gid], ["name"])[0]
            names = [rpc.read("product.product", [m2o_id(m["product_id"])],
                              ["display_name"])[0]["display_name"]
                     for m in group_members(rpc, gid)]
            ctx.check("computed name", ", ".join(names), grp["name"])

        with ctx.step("Rebuilding the same set from C gives identical membership"):
            before = {m2o_id(m["product_id"]) for m in group_members(rpc, gid)}
            for pid in (a, b, c, d):
                set_replacements(rpc, pid, [])
            set_replacements(rpc, c, [a, b, d])
            gid2 = group_of(rpc, c)
            after = {m2o_id(m["product_id"]) for m in group_members(rpc, gid2)}
            ctx.check("membership is order-independent", before, after)

        with ctx.step("Removing B from A splits the group cleanly"):
            set_replacements(rpc, a, [c, d])
            gid3 = group_of(rpc, a)
            remaining = {m2o_id(m["product_id"]) for m in group_members(rpc, gid3)}
            ctx.check("A, C and D remain a clique of three", {a, c, d}, remaining)
            ctx.check("B keeps no one-sided pointer", None, group_of(rpc, b))
            groups = rpc.search("mrp.component.replacement.group",
                                [("line_ids.product_id", "in", [a, b, c, d])])
            ctx.check("exactly one group covers the fixtures", 1, len(groups))

        with ctx.step("A multi-variant template configures on the Variants form"):
            # The two halves live on DIFFERENT views: the explanatory note is
            # on product.template (product_views.xml:15, invisible when
            # product_variant_count <= 1) and the self-excluding domain is on
            # the product.product form (product_views.xml:34).
            def arch_of(model):
                rows = rpc.search_read(
                    "ir.ui.view",
                    [("model", "=", model),
                     ("arch_db", "like", "replacement_product_ids")],
                    ["arch_db"], limit=1)
                return rows[0]["arch_db"] if rows else ""

            tmpl_arch = arch_of("product.template")
            ctx.check_true("product.template carries the note that variants "
                           "are configured on the Variants form",
                           "product_variant_count" in tmpl_arch
                           and "Variants form" in tmpl_arch,
                           tmpl_arch[:160] or "no product.template view found")

            variant_arch = arch_of("product.product").replace('"', "'")
            normalised = variant_arch.replace(" ", "")
            ctx.check_true("the variant field excludes itself with "
                           "domain=[('id','!=',id)]",
                           "[('id','!=',id)]" in normalised,
                           variant_arch[:160] or "no product.product view found")
    finally:
        try:
            sweep_wf009(rpc)
        except Exception:  # noqa: BLE001 — teardown must never mask a verdict
            pass


@test_case(
    id="TEST-WF009-TC137",
    name="A product cannot replace itself, and cannot belong to two groups",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_mrp_component_replacement",
    priority="P2", kind="API", order=9137,
    description="Listing a product among its own replacements raises the "
                "self-reference ValidationError and rolls back; inserting a "
                "second group line for an already-grouped product is rejected "
                "by the unique(product_id) database constraint, leaving "
                "membership disjoint.",
    traceability=trace("DATAONE-TC137"))
def test_tc137(ctx):
    """EXPECTED v19 OUTCOME: FAIL on the self-reference half — and the failure
    IS the finding, not an automation defect.

    ``_check_replacement_product_ids`` (product_product.py:59) raises when
    ``product in product.replacement_product_ids``. That condition is
    unreachable through the ORM, because the field is COMPUTED as
    ``line.group_id.line_ids.product_id - product`` (product_product.py:26) —
    self is subtracted before any constraint reads the value.

    Measured directly against d1v19, independently of this suite: writing
    ``replacement_product_ids = [A, B]`` onto A raises nothing, reads back as
    ``[B]``, and leaves a well-formed two-line group. The guard is dead code
    on this path.

    The workbook requires the ValidationError with that exact message, and
    expectations are immutable (AUTOMATION_CONVENTIONS hard rule 2), so the
    assertion below stays as written. Booking it as a product decision:
    either the guard moves to the inverse (where `desired` still contains
    self) or the workbook's expectation is retired as describing a guard the
    design does not need.

    The second half — one group per product — passes: that one is a real
    database constraint (`models.Constraint`, mrp_component_replacement.py:34)
    with no compute in front of it.
    """
    require_replacement_module(ctx)
    require_mrp(ctx)
    rpc = ctx.adapter.rpc
    open_namespace(ctx)
    try:
        with ctx.step("Build a clique of three and a second, unrelated clique"):
            a = make_product(rpc, "CONN-A")
            b = make_product(rpc, "CONN-B")
            c = make_product(rpc, "CONN-C")
            set_replacements(rpc, a, [b, c])
            gid = group_of(rpc, a)
            x = make_product(rpc, "OTHER-X")
            y = make_product(rpc, "OTHER-Y")
            set_replacements(rpc, x, [y])
            gid_other = group_of(rpc, x)
            ctx.check_true("the two cliques are separate groups",
                           gid != gid_other, f"{gid} vs {gid_other}")
            before = {m2o_id(m["product_id"]) for m in group_members(rpc, gid)}

        with ctx.step("A product cannot be a replacement of itself"):
            error = ""
            try:
                set_replacements(rpc, a, [a, b, c])
            except OdooRPCError as exc:
                error = str(exc)
            ctx.check_true(
                f"ValidationError says {SELF_REPLACEMENT_ERROR!r}",
                SELF_REPLACEMENT_ERROR in error, error[:200] or "no error raised")

        with ctx.step("The group is unchanged after the rollback"):
            ctx.check("membership survived the rejected write", before,
                      {m2o_id(m["product_id"]) for m in group_members(rpc, gid)})

        with ctx.step("A product cannot belong to two groups at once"):
            error = ""
            try:
                rpc.create("mrp.component.replacement.line",
                           {"group_id": gid_other, "product_id": b, "sequence": 90})
            except OdooRPCError as exc:
                error = str(exc)
            ctx.check_true(
                f"the unique(product_id) constraint says {ONE_GROUP_ERROR!r}",
                ONE_GROUP_ERROR in error, error[:200] or "no error raised")

        with ctx.step("B still has exactly one group line"):
            n = len(rpc.search("mrp.component.replacement.line",
                               [("product_id", "=", b)]))
            ctx.check("line count for B", 1, n)
            ctx.check("B is still in the original clique", gid, group_of(rpc, b))
    finally:
        try:
            sweep_wf009(rpc)
        except Exception:  # noqa: BLE001
            pass
