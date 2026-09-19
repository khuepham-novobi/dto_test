"""Cross-version baselines for DATA_RECONCILIATION tests.

Pattern: the run on the *baseline* environment (Odoo 17) captures a
snapshot and stores it here; the run on the *target* environment (Odoo 19)
loads the stored snapshot and diffs against live data. Baselines are
per-test JSON files under data/baselines/ plus optional CSV payloads.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from backend.config import settings

BASELINE_DIR = settings.data_dir / "baselines"


def baseline_path(tc_id: str) -> Path:
    return BASELINE_DIR / f"{tc_id}.json"


def dataset_fingerprint(rpc) -> dict:
    """Which DATASET a database holds, independently of its name or version.

    A baseline is only meaningful against the database the target was
    migrated FROM. The db NAME cannot say that — 'dto_17' and 'd1v19' differ
    by design — so the companies are used instead: an upgrade and a restore
    both carry res_company rows across unchanged, while an unrelated
    database has different ones.

    Measured, and the reason this exists: data/baselines/*.json captured on
    2026-09-04 came from `dto_17`, whose companies are 'My Company (San
    Francisco)' and 'My Company (Chicago)' created 2026-08-25 — stock Odoo
    DEMO data. The target d1v19 holds 'DataOne Systems, LLC' created
    2024-08-15. Diffing those two answers no question about the migration,
    yet it produced fifteen confident FAILED results that read as data loss.
    """
    rows = rpc.search_read("res.company", [], ["name", "create_date"],
                           order="id")
    return {
        "companies": [f"{row['id']}:{row['name']}" for row in rows],
        "earliest_company_create_date": min(
            (str(row["create_date"]) for row in rows), default=None),
    }


def dataset_mismatch(baseline: dict, current: dict) -> str | None:
    """A human-readable reason the two datasets are not comparable, or None."""
    stored = baseline.get("dataset")
    if not stored:
        return ("it carries no dataset fingerprint, so it predates this "
                "check and cannot be shown to come from the database this "
                "target was migrated from")
    if stored == current:
        return None
    return (f"it was captured against {stored.get('companies')} "
            f"(earliest company created "
            f"{stored.get('earliest_company_create_date')}) while this "
            f"target holds {current.get('companies')} (earliest "
            f"{current.get('earliest_company_create_date')})")


def save_baseline(tc_id: str, env_key: str, db: str, data: dict,
                  dataset: dict | None = None) -> Path:
    path = baseline_path(tc_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "tc_id": tc_id,
        "captured_env": env_key,
        "captured_db": db,
        "captured_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "dataset": dataset,
        "data": data,
    }, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    return path


def load_baseline(tc_id: str) -> dict | None:
    path = baseline_path(tc_id)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def csv_baseline_path(tc_id: str, name: str) -> Path:
    return BASELINE_DIR / tc_id / f"{name}.csv"


def diff_counts(baseline: dict, current: dict) -> list[str]:
    """Compare two {key: count} dicts; return human-readable differences."""
    diffs = []
    for key in sorted(set(baseline) | set(current)):
        b, c = baseline.get(key), current.get(key)
        if b != c:
            diffs.append(f"{key}: baseline={b!r} current={c!r}")
    return diffs
