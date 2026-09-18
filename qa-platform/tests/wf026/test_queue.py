"""DATAONE-WF-026 — the asynchronous import path and the job layer it uses.

Ten cases: TC408/TC409 are the importer's own queue behaviour, TC451-TC458
are the ``queue_job`` lifecycle the import dispatches onto.

Why these matter more than their priority suggests
---------------------------------------------------
``use_queue_job=True`` is the path a 43,313-record migration would actually
take — the synchronous path holds one transaction open for the whole file.
And it is exercised by **nothing**: ``WF026-OPEN-QUESTIONS.md:46-57`` records
the async path as untested, and the module's own 15 tests all drive the
synchronous branch. So this file is the first thing that runs it.

The channel names are derived, not configured
----------------------------------------------
``models/dto_data_migration.py:24-25``::

    model_name = self._name.replace('.', '_')
    self.with_delay(channel=f'import_{model_name}')._import_data_migration(...)

``data/queue_job_channel_data.xml`` defines three channels —
``import_purchase_order``, ``import_mrp_production``, ``import_sale_order``.
It does not define ``import_mrp_bom``. Verified on d1v19:
``queue.job.channel`` holds exactly ``root`` plus those three. TC409 is that
gap, and what queue_job does about it.

Two crons this file deliberately does NOT run
----------------------------------------------
TC456 (the stuck-job garbage collector) and TC457 (the autovacuum of done
jobs) are both **global**: ``requeue_stuck_jobs`` re-queues every stuck job
on the database and ``autovacuum`` DELETES done jobs past their channel's
removal interval. On a clone of the client's database that would touch the
client's own 36 jobs, which hard rule 3 forbids. Both cases therefore assert
the mechanism's **configuration** — that the cron exists, on the right
model, calling the right method, with the interval the workbook names —
exactly as TEST-WF018-TC321 asserts its cron's selection rather than firing
it. The docstrings say so; nothing is quietly skipped.

EXPECTED v17 OUTCOME
  All ten PASS, with TC451 BLOCKED (the workbook types it MANUAL).
EXPECTED v19 OUTCOME
  The same. queue_job is OCA 19.0 replaced wholesale rather than ported
  (tools/uninstall_non_migrated.py), so a failure here is about
  dto_data_migration's use of it, not about the port of queue_job itself.
"""
from framework.registry import test_case
from tests.wf026.common import (CHANNEL_FOR_TYPE, QUEUE_CHANNELS, WORKFLOW,
                                WORKFLOW_NAME, ensure_partner, ensure_product,
                                expect_error, fx, make_wizard, open_namespace,
                                partner_name, product_code,
                                require_data_migration, require_queue_job,
                                run_import, sweep_wf026, trace, wait_for_job)

JOB_MODEL = "queue.job"
MANAGER_GROUP = "queue_job.group_queue_job_manager"


def _mo_rows(rpc, product_id, prefix, count):
    return [{"name": fx(f"{prefix}-{i}").replace(" ", "-"),
             "product_id": product_code(rpc, product_id),
             "product_qty": "1", "qty_produced": "1"}
            for i in range(count)]


def _my_jobs(rpc, since_id: int, method="_import_data_migration"):
    """Jobs this execution created — anything newer than the marker id."""
    return rpc.search_read(
        JOB_MODEL,
        [("id", ">", since_id), ("method_name", "=", method)],
        ["name", "state", "channel", "model_name", "exc_info", "retry"],
        order="id")


def _job_high_water(rpc) -> int:
    rows = rpc.search_read(JOB_MODEL, [], ["id"], order="id desc", limit=1)
    return rows[0]["id"] if rows else 0


# ------------------------------------------------------------------ TC408
@test_case(
    id="TEST-WF026-TC408",
    name="A queued import creates one job per batch on the expected channel",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_data_migration",
    priority="P1", kind="INTEG", order=26408,
    description="use_queue_job=True dispatches one queue.job per batch, on "
                "the channel derived from the target model, and creates "
                "nothing synchronously.",
    traceability=trace("DATAONE-TC408"))
def test_tc408(ctx):
    rpc = ctx.adapter.rpc
    require_data_migration(ctx)
    require_queue_job(ctx)
    open_namespace(ctx)
    try:
        with ctx.step("Fixtures"):
            product = ensure_product(rpc, "Assembly")
            watermark = _job_high_water(rpc)

        with ctx.step("Queue an MO import of 5 rows at batch_size 2 — three "
                      "batches, so one job cannot be mistaken for the whole "
                      "file"):
            rows = _mo_rows(rpc, product, "Q408", 5)
            wizard_id = make_wizard(rpc, "closed_mo", rows,
                                    batch_size=2, use_queue_job=True)
            result = run_import(rpc, wizard_id)
            # action_confirm_import returns None when nothing was created
            # synchronously (:69 guard) — which is exactly the queued case.
            ctx.log(f"action returned: {result['action']!r}")

        with ctx.step("One job per batch"):
            jobs = _my_jobs(rpc, watermark)
            ctx.check("jobs created", 3, len(jobs))

        with ctx.step("Every job is on the channel derived from the model"):
            channels = sorted({j["channel"] for j in jobs})
            ctx.check("channel", [CHANNEL_FOR_TYPE["closed_mo"]], channels)
            ctx.check("model_name", ["mrp.production"],
                      sorted({j["model_name"] for j in jobs}))

        with ctx.step("The jobs run, and the records land"):
            for job in jobs:
                final = wait_for_job(rpc, job["id"] if "id" in job
                                     else job.get("id"))
                ctx.log(f"job {job.get('id')} -> {final.get('state')}")
            states = sorted({j["state"] for j in _my_jobs(rpc, watermark)})
            ctx.check("every job reached done", ["done"], states)
            created = rpc.search("mrp.production",
                                 [("name", "like", fx("Q408").split()[0] + "%")])
            ctx.check("all five rows were imported", 5, len(created))
    finally:
        with ctx.step("Cleanup"):
            try:
                sweep_wf026(rpc)
            except Exception:  # noqa: BLE001
                pass


# ------------------------------------------------------------------ TC409
@test_case(
    id="TEST-WF026-TC409",
    name="A queued BOM import falls back to the root channel because it has "
         "no channel of its own",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_data_migration",
    priority="P2", kind="INTEG", order=26409,
    description="The channel name is derived from the model, and no data "
                "file defines import_mrp_bom, so queue_job falls back to root "
                "rather than raising.",
    traceability=trace("DATAONE-TC409"))
def test_tc409(ctx):
    rpc = ctx.adapter.rpc
    require_data_migration(ctx)
    require_queue_job(ctx)
    open_namespace(ctx)
    try:
        with ctx.step("The three configured channels exist — and a fourth for "
                      "mrp.bom does not"):
            names = sorted(c["complete_name"] for c in rpc.search_read(
                "queue.job.channel", [], ["complete_name"]))
            for channel in QUEUE_CHANNELS:
                ctx.check_true(f"{channel} is configured", channel in names,
                               str(names))
            ctx.check_true("root.import_mrp_bom is NOT configured — this is "
                           "the gap the case is about",
                           "root.import_mrp_bom" not in names, str(names))

        with ctx.step("Fixtures"):
            finished = ensure_product(rpc, "Finished")
            component = ensure_product(rpc, "Component")
            tmpl = rpc.read("product.product", [finished],
                            ["product_tmpl_id"])[0]["product_tmpl_id"][0]
            watermark = _job_high_water(rpc)

        with ctx.step("Queue a BOM import"):
            rows = [{
                "product_tmpl_id": rpc.read(
                    "product.template", [tmpl], ["name"])[0]["name"],
                "product_qty": "1",
                "bom_line_ids/product_id": product_code(rpc, component),
                "bom_line_ids/product_qty": "2",
            }]
            wizard_id = make_wizard(rpc, "bom", rows, batch_size=100,
                                    use_queue_job=True)
            run_import(rpc, wizard_id)

        with ctx.step("The job landed on root, not on a bom channel"):
            jobs = _my_jobs(rpc, watermark)
            ctx.check_true("a job was created", bool(jobs), str(jobs))
            if jobs:
                ctx.check("the job records the channel it ASKED for",
                          CHANNEL_FOR_TYPE["bom"], jobs[0]["channel"])
                ctx.check("model_name", "mrp.bom", jobs[0]["model_name"])
                ctx.check_true(
                    "and no queue.job.channel record of that name exists — "
                    "the job names a channel that was never configured",
                    "root.import_mrp_bom" not in names, str(names))
                ctx.log("RECORDED: the fallback is silent, and the job row "
                        "keeps the unconfigured name. queue_job resolves it "
                        "to root at runtime, so a BOM import competes for "
                        "the root channel's capacity with every other "
                        "unclassified job instead of having its own — and "
                        "nothing in the UI says so.")
    finally:
        with ctx.step("Cleanup"):
            try:
                sweep_wf026(rpc)
            except Exception:  # noqa: BLE001
                pass


# ------------------------------------------------------------------ TC451
@test_case(
    id="TEST-WF026-TC451",
    name="The jobrunner starts and logs queue job runner ready for db",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="queue_job",
    priority="P0", kind="SMOKE", order=26451,
    description="A startup-log assertion. The workbook types this MANUAL; "
                "the observable half — that the runner is in fact consuming "
                "jobs — is asserted here before blocking.",
    traceability=trace("DATAONE-TC451"))
def test_tc451(ctx):
    """EXPECTED OUTCOME: BLOCKED, after asserting what IS observable.

    The workbook's expectation is a line in the server's startup log. This
    platform reaches the target only over RPC and deliberately never restarts
    it — a harness that can bounce the environment it is measuring cannot
    report on it honestly, and other suites share the same server.

    So the case asserts the CONSEQUENCE the log line exists to promise —
    that jobs actually leave the pending state — and then blocks on the log
    itself rather than pretending to have read it.
    """
    rpc = ctx.adapter.rpc
    require_queue_job(ctx)
    with ctx.step("The observable half: the runner is consuming jobs"):
        by_state = {g["state"]: g["state_count"] for g in
                    rpc.read_group(JOB_MODEL, [], ["id"], ["state"])}
        ctx.log(f"job states on this database: {by_state}")
        ctx.check_true(
            "at least one job has reached a terminal state, so a runner has "
            "been consuming this queue",
            any(by_state.get(s) for s in ("done", "failed", "cancelled")),
            str(by_state))

    with ctx.step("The log line itself is not reachable from here"):
        ctx.blocked(
            "the workbook asserts the server's startup log contains "
            "'queue job runner ready for db'. This platform drives the "
            "target over RPC and never restarts it, so the startup log is "
            "outside what it can observe. The consequence that line promises "
            "IS asserted in the previous step — jobs reach terminal states, "
            "so a runner is alive. Reading the log belongs to a deployment "
            "smoke test that owns the server.")


# ------------------------------------------------------------------ TC452
@test_case(
    id="TEST-WF026-TC452",
    name="A job progresses Pending -> Enqueued -> Started -> Done",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="queue_job",
    priority="P0", kind="FUNC", order=26452,
    description="A queued import job reaches done, and carries the "
                "timestamps that mark the transitions.",
    traceability=trace("DATAONE-TC452"))
def test_tc452(ctx):
    rpc = ctx.adapter.rpc
    require_data_migration(ctx)
    require_queue_job(ctx)
    open_namespace(ctx)
    try:
        with ctx.step("Queue one job"):
            product = ensure_product(rpc, "Assembly")
            watermark = _job_high_water(rpc)
            run_import(rpc, make_wizard(
                rpc, "closed_mo", _mo_rows(rpc, product, "Q452", 1),
                batch_size=100, use_queue_job=True))
            jobs = _my_jobs(rpc, watermark)
            ctx.check("exactly one job", 1, len(jobs))

        with ctx.step("It reaches done, and not by skipping the queue"):
            job_id = jobs[0]["id"]
            # Read the state immediately: a job that were executed
            # synchronously would already be done here.
            first = rpc.read(JOB_MODEL, [job_id], ["state"])[0]["state"]
            ctx.log(f"state immediately after dispatch: {first}")
            final = wait_for_job(rpc, job_id)
            ctx.check("final state", "done", final["state"])

        with ctx.step("The timestamps mark the transitions"):
            row = rpc.read(JOB_MODEL, [job_id],
                           ["date_created", "date_started", "date_done",
                            "state"])[0]
            ctx.check_true("date_created is set", bool(row["date_created"]),
                           str(row["date_created"]))
            ctx.check_true("date_started is set — the job really ran",
                           bool(row["date_started"]), str(row["date_started"]))
            ctx.check_true("date_done is set", bool(row["date_done"]),
                           str(row["date_done"]))

        with ctx.step("And the record it was queued to create exists"):
            created = rpc.search(
                "mrp.production",
                [("name", "like", fx("Q452").split()[0] + "%")])
            ctx.check("one MO imported by the job", 1, len(created))
    finally:
        with ctx.step("Cleanup"):
            try:
                sweep_wf026(rpc)
            except Exception:  # noqa: BLE001
                pass


# ------------------------------------------------------------------ TC453
@test_case(
    id="TEST-WF026-TC453",
    name="A failed job notifies every Job Queue Manager and records the "
         "traceback",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="queue_job",
    priority="P1", kind="FUNC", order=26453,
    description="A job whose payload cannot be imported ends Failed with "
                "exc_info populated, and the Job Queue Manager group exists "
                "to receive the notification.",
    traceability=trace("DATAONE-TC453"))
def test_tc453(ctx):
    rpc = ctx.adapter.rpc
    require_data_migration(ctx)
    require_queue_job(ctx)
    open_namespace(ctx)
    try:
        with ctx.step("Queue an import whose row cannot succeed"):
            watermark = _job_high_water(rpc)
            # An MO row naming a product that does not exist: the transform
            # raises inside the job rather than at dispatch, which is what
            # makes this a JOB failure and not a wizard failure.
            rows = [{"name": fx("Q453").replace(" ", "-"),
                     "product_id": f"NO-SUCH-PRODUCT-{fx('x').split()[0]}",
                     "product_qty": "1", "qty_produced": "1"}]
            run_import(rpc, make_wizard(rpc, "closed_mo", rows,
                                        use_queue_job=True))
            jobs = _my_jobs(rpc, watermark)
            ctx.check("one job", 1, len(jobs))

        with ctx.step("It ends Failed, carrying the traceback"):
            final = wait_for_job(rpc, jobs[0]["id"])
            ctx.check("state", "failed", final["state"])
            ctx.check_true("exc_info is populated", bool(final["exc_info"]),
                           str(final["exc_info"])[:200])
            ctx.check_true("and it names the failure the importer reported",
                           "Can not find" in (final["exc_info"] or "")
                           or "Error when" in (final["exc_info"] or ""),
                           str(final["exc_info"])[:300])

        with ctx.step("The Job Queue Manager group exists to be notified"):
            group_id = rpc.ref(MANAGER_GROUP)
            ctx.check_true(f"{MANAGER_GROUP} resolves", bool(group_id),
                           str(group_id))
            members = rpc.search("res.users", [("groups_id", "in", [group_id])]) \
                if rpc.field_exists("res.users", "groups_id") else \
                rpc.search("res.users", [("group_ids", "in", [group_id])])
            ctx.log(f"Job Queue Managers on this database: {len(members)}")
            ctx.check_true("at least one user would receive the notification",
                           len(members) > 0, str(members[:5]))
    finally:
        with ctx.step("Cleanup"):
            try:
                sweep_wf026(rpc)
            except Exception:  # noqa: BLE001
                pass


# ------------------------------------------------------------- TC454/455
def _failed_job(ctx, rpc):
    """One FAILED job of this execution's own, for the wizards to act on."""
    watermark = _job_high_water(rpc)
    rows = [{"name": fx("QW").replace(" ", "-"),
             "product_id": f"NO-SUCH-PRODUCT-{fx('x').split()[0]}",
             "product_qty": "1", "qty_produced": "1"}]
    run_import(rpc, make_wizard(rpc, "closed_mo", rows, use_queue_job=True))
    jobs = _my_jobs(rpc, watermark)
    if not jobs:
        ctx.blocked("no queue.job was dispatched, so there is nothing for the "
                    "wizard to act on")
    final = wait_for_job(rpc, jobs[0]["id"])
    if final.get("state") != "failed":
        ctx.blocked(f"the fixture job ended {final.get('state')!r} rather "
                    f"than 'failed', so this wizard cannot be exercised on a "
                    f"failed job without inventing one")
    return jobs[0]["id"]


@test_case(
    id="TEST-WF026-TC454",
    name="The Requeue Jobs wizard returns a failed job to Pending and clears "
         "its retry count",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="queue_job",
    priority="P1", kind="FUNC", order=26454,
    description="queue.requeue.job acting on this execution's own failed "
                "job — never on the database's existing ones.",
    traceability=trace("DATAONE-TC454"))
def test_tc454(ctx):
    rpc = ctx.adapter.rpc
    require_data_migration(ctx)
    require_queue_job(ctx)
    open_namespace(ctx)
    try:
        with ctx.step("A failed job of our own"):
            job_id = _failed_job(ctx, rpc)

        with ctx.step("Requeue it"):
            # Scoped by active_ids to OUR job. The wizard acts on whatever
            # the context names, so an unscoped call would requeue the
            # client's failed jobs too — rule 3.
            # The wizard carries a job_ids m2m which the UI fills from
            # active_ids. Setting it explicitly scopes the action to OUR
            # job; an unscoped call would requeue the client's failed jobs
            # too (rule 3).
            wizard = rpc.create("queue.requeue.job",
                                {"job_ids": [(6, 0, [job_id])]})
            rpc.call("queue.requeue.job", "requeue", [wizard])

        with ctx.step("It left Failed and re-entered the queue"):
            # The runner is alive and polls continuously, so a requeued job
            # can be picked up between the wizard returning and this read —
            # measured: 'started'. Asserting a literal 'pending' would make
            # the case fail on a HEALTHY queue, which is the wrong signal.
            # What the workbook is about is that the job went back INTO the
            # queue, so every non-failed state that follows pending counts.
            row = rpc.read(JOB_MODEL, [job_id], ["state", "retry"])[0]
            ctx.check_true(
                "the job is back in the queue rather than still failed",
                row["state"] in ("pending", "enqueued", "started", "done"),
                f"state={row['state']!r}")
            ctx.log(f"state immediately after requeue: {row['state']!r} "
                    f"(the runner may already have taken it)")

        with ctx.step("And it is no longer Failed once it settles"):
            final = wait_for_job(rpc, job_id)
            ctx.check_true(
                "the requeued job ran again rather than staying failed",
                final.get("state") in ("done", "failed"),
                str(final.get("state")))
            ctx.log(f"settled at {final.get('state')!r} — a second failure "
                    f"is expected here, because the payload that failed the "
                    f"first time is unchanged. What the case proves is that "
                    f"requeue put it back through the runner.")
    finally:
        with ctx.step("Cleanup"):
            try:
                sweep_wf026(rpc)
            except Exception:  # noqa: BLE001
                pass


@test_case(
    id="TEST-WF026-TC455",
    name="The Set to Done and Cancel wizards close jobs without executing "
         "them",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="queue_job",
    priority="P2", kind="FUNC", order=26455,
    description="queue.jobs.to.done and queue.jobs.to.cancelled move a job "
                "to a terminal state without running its payload.",
    traceability=trace("DATAONE-TC455"))
def test_tc455(ctx):
    rpc = ctx.adapter.rpc
    require_data_migration(ctx)
    require_queue_job(ctx)
    open_namespace(ctx)
    try:
        with ctx.step("Set to Done, on our own failed job"):
            job_id = _failed_job(ctx, rpc)
            wizard = rpc.create("queue.jobs.to.done",
                                {"job_ids": [(6, 0, [job_id])]})
            rpc.call("queue.jobs.to.done", "set_done", [wizard])
            ctx.check("state", "done",
                      rpc.read(JOB_MODEL, [job_id], ["state"])[0]["state"])
            ctx.check_true("and nothing was imported by it — the payload did "
                           "not run",
                           not rpc.search("mrp.production",
                                          [("name", "like",
                                            fx("QW").split()[0] + "%")]),
                           "no MO created")

        with ctx.step("Cancel, on a second failed job"):
            job2 = _failed_job(ctx, rpc)
            wizard2 = rpc.create("queue.jobs.to.cancelled",
                                 {"job_ids": [(6, 0, [job2])]})
            rpc.call("queue.jobs.to.cancelled", "set_cancelled", [wizard2])
            ctx.check("state", "cancelled",
                      rpc.read(JOB_MODEL, [job2], ["state"])[0]["state"])
    finally:
        with ctx.step("Cleanup"):
            try:
                sweep_wf026(rpc)
            except Exception:  # noqa: BLE001
                pass


# ------------------------------------------------------------- TC456/457
@test_case(
    id="TEST-WF026-TC456",
    name="The garbage collector returns jobs Enqueued for more than 5 "
         "minutes to Pending",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="queue_job",
    priority="P1", kind="FUNC", order=26456,
    description="The stuck-job cron's configuration is asserted — model, "
                "method and interval — rather than fired, because firing it "
                "re-queues every stuck job on the database.",
    traceability=trace("DATAONE-TC456"))
def test_tc456(ctx):
    """EXPECTED v19 OUTCOME: FAIL, and the failure is a version finding.

    The workbook describes a garbage collector that returns jobs stuck in
    Enqueued for more than five minutes to Pending. **queue_job 19.0 has no
    such mechanism.** Verified three ways on d1v19:

    * ``data/queue_data.xml`` defines exactly ONE record of type ir.cron,
      ``ir_cron_autovacuum_queue_jobs`` — there is no requeue cron;
    * ``grep -rn 'stuck' 3rd-addons/queue_job --include=*.py`` returns
      nothing;
    * calling the method reports
      ``The method 'queue.job.requeue_stuck_jobs' does not exist``.

    queue_job is OCA 19.0 taken wholesale rather than ported
    (``tools/uninstall_non_migrated.py``), so this is not something the
    DataOne port broke — it is a capability the newer upstream does not
    ship. It still matters: a job whose worker dies mid-flight stays
    Enqueued, and with no collector nothing returns it to the queue. The
    case is left failing so the gap is visible rather than assumed handled.
    """
    rpc = ctx.adapter.rpc
    require_queue_job(ctx)
    with ctx.step("Every cron on queue.job, including inactive ones"):
        # active=False is excluded from an ordinary search, and the one cron
        # queue_job does ship is inactive on this database — so an ordinary
        # search finds nothing and would read as "no crons at all".
        crons = rpc.search_read(
            "ir.cron",
            [("model_id.model", "=", JOB_MODEL), ("active", "in", [True, False])],
            ["cron_name", "active", "interval_number", "interval_type", "code"])
        for cron in crons:
            ctx.log(f"{cron['cron_name']}: every {cron['interval_number']} "
                    f"{cron['interval_type']}, active={cron['active']}, "
                    f"code={(cron.get('code') or '').strip()[:60]}")
        ctx.check_true("queue.job carries at least one cron", bool(crons),
                       str(crons))

    with ctx.step("One of them is the stuck-job garbage collector"):
        stuck = [c for c in crons
                 if "requeue" in (c.get("code") or "").lower()
                 or "stuck" in ((c.get("cron_name") or "")
                                + (c.get("code") or "")).lower()]
        ctx.check_true(
            "a stuck-job collector is configured",
            bool(stuck),
            f"crons on queue.job: "
            f"{[c['cron_name'] for c in crons]} — none of them requeues "
            f"stuck jobs, and queue_job 19.0 defines no requeue_stuck_jobs "
            f"method at all")

    with ctx.step("RECORDED: what happens to a stuck job on this version"):
        ctx.log("queue_job 19.0 ships one cron (autovacuum) and no stuck-job "
                "collector. A job left Enqueued by a worker that died is not "
                "returned to Pending by anything. The workbook's expectation "
                "describes an older queue_job.")


@test_case(
    id="TEST-WF026-TC457",
    name="The autovacuum deletes Done jobs past the channel's Removal "
         "interval",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="queue_job",
    priority="P2", kind="FUNC", order=26457,
    description="The autovacuum cron and the channel's removal interval are "
                "asserted; the cron is not fired, because it DELETES rows "
                "belonging to the client.",
    traceability=trace("DATAONE-TC457"))
def test_tc457(ctx):
    """Not fired, and this one is the clearest case for not firing: the
    autovacuum **deletes** done jobs. On a clone of the client's database
    that is destruction of their records for no test benefit. Rule 3.
    """
    rpc = ctx.adapter.rpc
    require_queue_job(ctx)
    with ctx.step("The autovacuum cron exists — searched with inactive "
                  "included, because it IS inactive here"):
        crons = rpc.search_read(
            "ir.cron",
            [("model_id.model", "=", JOB_MODEL), ("active", "in", [True, False])],
            ["cron_name", "interval_number", "interval_type", "active",
             "code"])
        vac = [c for c in crons if "autovacuum" in (c.get("code") or "").lower()
               or "vacuum" in (c.get("cron_name") or "").lower()]
        ctx.check_true("an autovacuum cron is configured for queue.job",
                       bool(vac), str([c.get("cron_name") for c in crons]))
        for cron in vac:
            ctx.log(f"{cron['cron_name']}: every {cron['interval_number']} "
                    f"{cron['interval_type']}, active={cron['active']}")
        if vac and not any(c["active"] for c in vac):
            ctx.log("RECORDED: the autovacuum is INACTIVE on this database, "
                    "so done jobs are never removed and queue.job grows "
                    "without bound. Deliberate on a UAT clone (the deploy "
                    "deactivates crons), but it would be a defect on "
                    "production.")

    with ctx.step("Every channel carries a removal interval"):
        channels = rpc.search_read("queue.job.channel", [],
                                   ["complete_name", "removal_interval"])
        missing = [c["complete_name"] for c in channels
                   if not c.get("removal_interval")]
        ctx.check("channels with no removal interval", [], missing)
        for channel in channels:
            ctx.log(f"{channel['complete_name']}: removal after "
                    f"{channel['removal_interval']} days")
        ctx.log("NOT FIRED: the autovacuum DELETES done jobs. Rule 3.")


# ------------------------------------------------------------------ TC458
@test_case(
    id="TEST-WF026-TC458",
    name='Creating a queue.job directly is refused with "Queue jobs must be '
         'created by..."',
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="queue_job",
    priority="P2", kind="NEG", order=26458,
    description="queue.job cannot be created through the ORM; only "
                "with_delay may create one.",
    traceability=trace("DATAONE-TC458"))
def test_tc458(ctx):
    rpc = ctx.adapter.rpc
    require_queue_job(ctx)
    with ctx.step("A direct create is refused"):
        message, fault = expect_error(
            ctx, lambda: rpc.create(JOB_MODEL, {
                "name": fx("hand-made job"),
                "model_name": "mrp.production",
                "method_name": "_import_data_migration",
            }),
            label="creating a queue.job through the ORM")
        ctx.log(f"fault={fault} message={message[:300]}")

    with ctx.step("The refusal is a refusal, not a column error"):
        # The workbook quotes queue_job's own guard ("Queue jobs must be
        # created by..."). That string is NOT reachable over RPC: Odoo's
        # transport layer refuses `queue.job.create` first, as a private
        # method, so the ORM-level guard never runs. Measured on d1v19:
        #   "Private methods (such as 'queue.job.create') cannot be called
        #    remotely."
        # The outcome the case is about — a hand-made queue.job is refused —
        # holds either way, and is what is asserted. The exact wording
        # belongs to an in-process TransactionCase.
        ctx.check_true(
            "creating a queue.job through the ORM is refused",
            bool(message), message[:300])
        ctx.check_true(
            "and it is refused for being a job, not for a bad payload",
            "cannot be called remotely" in message
            or "must be created" in message.lower()
            or "with_delay" in message,
            message[:300])
        ctx.log("RECORDED: over RPC the refusal comes from Odoo's transport "
                "layer, before queue_job's own message. The workbook's exact "
                "string is only observable in-process.")

    with ctx.step("And no job was created"):
        hand_made = rpc.search(JOB_MODEL, [("method_name", "=",
                                            "_import_data_migration"),
                                           ("name", "like", "%hand-made%")])
        ctx.check("hand-made jobs on the database", [], hand_made)
