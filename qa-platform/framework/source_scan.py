"""Static scans of the DataOne addon source tree.

Several workbook test cases are STATIC_ANALYSIS by nature: they grep the
custom source for APIs Odoo 19 removed and compare the result against the
database. Those cases need the source tree, not a running server, so the
scan lives here rather than in any one suite.

The tree's location is a per-workstation fact, like the PostgreSQL
credentials: set ``DTO_SOURCE_ROOT`` in ``config/local.yaml`` (or the
environment). The default is the checkout this platform was set up against.
When the path does not exist, ``resolve_source_root`` returns None and the
caller reports BLOCKED with a precise reason — it never falls back to a
weaker assertion.

Search scope follows the project rule: .py / .xml / .js are scanned;
i18n, static/description, __pycache__, node_modules, build and dist are
skipped.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

DEFAULT_SOURCE_ROOT = Path(r"D:\Projects\dataone\DTO-Odoo")

# The addon roots inside the source tree, in dependency order.
ADDON_ROOTS = ("3rd-addons", "novobi-addons", "project-addons")

SCANNED_SUFFIXES = (".py", ".xml", ".js")
SKIP_PARTS = {"i18n", "__pycache__", "node_modules", "build", "dist"}
SKIP_PATH_FRAGMENTS = ("static/description", "static\\description")


def resolve_source_root() -> Path | None:
    """The DTO-Odoo checkout, or None when it is not reachable here."""
    root = Path(os.environ.get("DTO_SOURCE_ROOT") or DEFAULT_SOURCE_ROOT)
    return root if root.is_dir() else None


def module_path(root: Path, module: str) -> Path | None:
    """Locate one addon by technical name across the three addon roots."""
    for addon_root in ADDON_ROOTS:
        candidate = root / addon_root / module
        if candidate.is_dir():
            return candidate
    return None


def _scannable(path: Path) -> bool:
    if path.suffix not in SCANNED_SUFFIXES:
        return False
    if SKIP_PARTS & set(path.parts):
        return False
    text = str(path).replace("\\", "/")
    return not any(frag.replace("\\", "/") in text
                   for frag in SKIP_PATH_FRAGMENTS)


def grep_module(module_dir: Path, pattern: str, suffixes=None) -> list[dict]:
    """Every match of ``pattern`` under ``module_dir``.

    Returns [{"file": <path relative to module_dir>, "line": n,
              "text": <stripped source line>}], ordered by file then line.
    """
    rx = re.compile(pattern)
    wanted = tuple(suffixes) if suffixes else SCANNED_SUFFIXES
    hits: list[dict] = []
    for path in sorted(module_dir.rglob("*")):
        if not path.is_file() or path.suffix not in wanted:
            continue
        if not _scannable(path):
            continue
        try:
            lines = path.read_text(encoding="utf-8",
                                   errors="replace").splitlines()
        except OSError:
            continue
        for n, line in enumerate(lines, start=1):
            if rx.search(line):
                hits.append({"file": str(path.relative_to(module_dir))
                             .replace("\\", "/"),
                             "line": n, "text": line.strip()[:200]})
    return hits


def scan_modules(root: Path, modules: list[str], pattern: str,
                 suffixes=None) -> dict:
    """{module: [hits]} for every module found; missing modules map to None
    so the caller can tell 'clean' from 'not present'."""
    result: dict = {}
    for module in modules:
        path = module_path(root, module)
        result[module] = (None if path is None
                          else grep_module(path, pattern, suffixes))
    return result


def summarise(scan: dict) -> dict:
    """{module: <hit count>} with None preserved for missing modules."""
    return {m: (None if hits is None else len(hits))
            for m, hits in scan.items()}
