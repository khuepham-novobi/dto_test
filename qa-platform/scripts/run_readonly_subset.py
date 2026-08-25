# -*- coding: utf-8 -*-
"""Run only the tests that provably cannot write to the target.

Why this exists: the first run of a suite against a populated database is
the riskiest moment, and 26 of the 100 tests need no write access at all —
the fourteen DATA_RECONCILIATION baselines, the source scans, and the ACL /
cron / dependency inventories. Running just those validates the whole
harness (registry -> run -> preflight -> per-test results -> failure
classification -> persistence) and captures the v17 baselines, while
touching nothing in the target.

Every id below was classified by AST: neither the test body nor any helper
it reaches calls create / write / unlink / copy, any ``sweep_*``, any
fixture builder, or any mutating ``action_*`` / ``button_*`` method. The
only files written are the platform's own — ``data/results.db``,
``data/baselines/`` and ``artifacts/``.

Usage:
    venv\\Scripts\\python.exe scripts\\run_readonly_subset.py [--env odoo17]

Re-verify the classification after editing any test:
    (see the AST check described in docs/ENVIRONMENT_STATUS.md)
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.config import settings                      # noqa: E402
from backend.runner import RunExecutor                    # noqa: E402
from backend.store import Store                           # noqa: E402
from framework import registry                            # noqa: E402

READONLY_IDS = [
    # WF-003 — source scan + field/sequence reads
    "TEST-WF003-TC014",
    # WF-020 — cron inventory, dependency pins, version deltas
    "TEST-WF020-TC008", "TEST-WF020-TC012", "TEST-WF020-TC305",
    "TEST-WF020-TC459", "TEST-WF020-TC460",
    # WF-002 — server-action compile scan + two reconciliations + the
    # Workday-folder safety assertion
    "TEST-WF002-TC017", "TEST-WF002-TC053", "TEST-WF002-TC057",
    "TEST-WF002-TC350",
    # WF-013 — env.ref resolution, analytic masters, the account.move ACL
    "TEST-WF013-TC007", "TEST-WF013-TC229", "TEST-WF013-TC273",
    # WF-013 — the fourteen reconciliation baselines
    "TEST-WF013-TC021", "TEST-WF013-TC023", "TEST-WF013-TC025",
    "TEST-WF013-TC027", "TEST-WF013-TC028", "TEST-WF013-TC034",
    "TEST-WF013-TC048", "TEST-WF013-TC049", "TEST-WF013-TC051",
    "TEST-WF013-TC052", "TEST-WF013-TC258", "TEST-WF013-TC259",
    "TEST-WF013-TC260",
]

MARKS = {"PASSED": "PASS", "FAILED": "FAIL", "BLOCKED": "BLOK",
         "SKIPPED": "SKIP", "ERROR": "ERR "}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", default="odoo17",
                    help="environment key from config/environments.yaml")
    args = ap.parse_args(argv)

    from backend.config import load_environments
    envs = load_environments()
    if args.env not in envs:
        print(f"Unknown environment {args.env!r}. Known: {sorted(envs)}",
              file=sys.stderr)
        return 1
    env = envs[args.env]

    all_tests = {t.id: t for t in registry.discover()}
    missing = [i for i in READONLY_IDS if i not in all_tests]
    if missing:
        print(f"These ids are in READONLY_IDS but not registered: {missing}",
              file=sys.stderr)
        return 1
    tests = [all_tests[i] for i in READONLY_IDS]

    store = Store(settings.data_dir / "results.db")
    store.load_registry(settings.data_dir / "test_registry.json")
    run_id = store.create_run(env.key, env.name, "single", None,
                              label=f"read-only subset on {env.db}")
    print(f"run {run_id}: {len(tests)} read-only tests on {env.key} "
          f"({env.base_url}, db={env.db})")

    started = time.time()
    RunExecutor(store, run_id, env.key, tests).run()
    elapsed = time.time() - started

    run = store.run(run_id) or {}
    rows = run.get("results", [])
    counts: dict = {}
    classes: dict = {}
    for row in rows:
        counts[row.get("status")] = counts.get(row.get("status"), 0) + 1
        cls = row.get("failure_class")
        if cls:
            classes[cls] = classes.get(cls, 0) + 1

    print()
    print("=" * 78)
    print(f"RUN {run_id}  {run.get('status')}  {elapsed:.0f}s")
    print("=" * 78)
    print(f"by status:        {counts}")
    print(f"failure classes:  {classes or 'none'}")
    print()
    for row in rows:
        mark = MARKS.get(row.get("status"), str(row.get("status")))
        print(f"  [{mark}] {str(row.get('test_id')):<20} "
              f"{row.get('duration_ms') or 0:>7}ms  "
              f"{str(row.get('failure_class') or ''):<18}"
              f"{(row.get('error') or '')[:70]}")
    print()
    print("Read the full detail (steps, assertions, evidence) with:")
    print(f"  venv\\Scripts\\python.exe scripts\\gen_reports.py   "
          f"# or open {run_id} in the UI")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
