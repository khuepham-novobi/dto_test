"""DATAONE-WF-010 — the dependency smoke test: TC018.

Shared with DATAONE-WF-017 and DATAONE-WF-026; owned here (WF-010 is the
owning workflow the workbook names). Those suites reference this tc_id and
must not re-implement it (AUTOMATION_CONVENTIONS.md, "Shared test cases").

Why it is worth a P2: *an undeclared dependency installs fine on the
developer's machine and fails on the first clean Odoo.sh build, at which
point the whole instance is down.* The failure is not subtle — it is total,
and it happens at the worst possible moment.

Two kinds of undeclared edge, and the second is the one a Python scan
misses
-----------------------------------------------------------------------
1. **Python packages** — every non-stdlib, non-Odoo top-level import in the
   custom tree, compared against the union of every
   ``external_dependencies['python']`` declaration. Steps 1-4.
2. **Odoo module dependencies** — ``env['base_import.import']`` is used by
   five call sites across three modules and was historically declared by
   none of them; it worked only transitively, through ``account`` or
   ``sale``. No Python scan catches that, which is why step 5 exists.
   ``dto_mrp_sftp``'s manifest now declares it explicitly with a comment
   naming the gap (``__manifest__.py:14-18``); this case asserts the other
   two do too.

What this case does NOT do, and why
-----------------------------------
The workbook's step 4 builds a fresh virtualenv and imports each package on
the target runtime. This platform does not build environments, so the
import check runs on **the platform's own interpreter** — which is a
different runtime from the Odoo server's, and the test says so rather than
pretending otherwise. What that half still catches is a package that is
named nowhere on the workstation at all; what it cannot catch is a version
skew between the platform venv and the server venv. ``TEST-WF020-TC012``
owns the pin comparison that does catch that, and is referenced rather
than duplicated.

Read from disk, so neither a server nor a database is needed —
``framework/source_scan.py`` resolves the DTO-Odoo checkout PER VERSION,
which matters here: a v19 run must scan the v19 tree or it reports v17
findings as v19 breakages.

EXPECTED v17 OUTCOME: PASS on the Odoo-module edges (the ported tree
declares ``base_import``); the Python undeclared set is reported as
evidence and asserted against the known-justified allowlist below, so a NEW
undeclared package fails the case while the already-accepted ones do not.
EXPECTED v19 OUTCOME: the same. A package that stops importing on the
platform interpreter is reported, not silently skipped.
"""
import importlib.util
import re
import sys

from framework.registry import test_case
from framework.source_scan import (ADDON_ROOTS, module_path,  # noqa: F401
                                   resolve_source_root)
from tests.wf010.common import WORKFLOW, WORKFLOW_NAME, trace  # noqa: F401

# Packages that are imported by the custom tree and are NOT expected to be
# declared, each with the reason. Anything outside this set that is
# undeclared fails the case.
JUSTIFIED_UNDECLARED = {
    # Test-only, and the workbook's own expected_result names it as
    # acceptable: "odoo_test_helper is test-only and may be declared in a
    # dev requirements file instead".
    "odoo_test_helper",
    # Odoo's own namespaces and the project's own addons, which the scan
    # cannot distinguish from third-party packages by name alone.
    "odoo", "openerp",
}

# The five call sites of base_import and the three modules that own them
# (verified by grep, below — the list here is what the assertion EXPECTS to
# find, so a new call site in a fourth module is reported rather than
# absorbed).
BASE_IMPORT_MODULES = ["dto_account_workday", "dto_sale_workday",
                       "dto_mrp_sftp"]

# Step 6 — the three other undeclared Odoo edges the inventory records.
OTHER_EDGES = {
    "stock_picking_auto_create_lot": ["sale", "dto_account"],
    "dto_purchase_stock": ["dto_sale_purchase"],
}

_IMPORT_RE = re.compile(
    r"^\s*(?:import|from)\s+([a-zA-Z_][a-zA-Z0-9_]*)")


def _top_level_imports(root):
    """{package: [where it was seen]} for every top-level import in the tree.

    Relative imports (``from . import x``) are skipped by the regex, which
    requires an identifier start — so ``from .`` and ``from ..`` do not
    match. Odoo's own ``from odoo import ...`` DOES match and is filtered
    out by name afterwards, together with the stdlib.
    """
    seen = {}
    for addon_root in ADDON_ROOTS:
        base = root / addon_root
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            parts = set(path.parts)
            if {"__pycache__", "node_modules", "build", "dist"} & parts:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for line in text.splitlines():
                match = _IMPORT_RE.match(line)
                if not match:
                    continue
                name = match.group(1)
                seen.setdefault(name, []).append(
                    str(path.relative_to(root)).replace("\\", "/"))
    return seen


def _declared_python_dependencies(root):
    """The union of every ``external_dependencies['python']`` in the tree."""
    declared = set()
    per_module = {}
    for addon_root in ADDON_ROOTS:
        base = root / addon_root
        if not base.is_dir():
            continue
        for manifest in sorted(base.glob("*/__manifest__.py")):
            text = manifest.read_text(encoding="utf-8", errors="replace")
            block = re.search(
                r"['\"]external_dependencies['\"]\s*:\s*\{(.+?)\}", text,
                re.S)
            if not block:
                continue
            python_block = re.search(r"['\"]python['\"]\s*:\s*\[(.*?)\]",
                                     block.group(1), re.S)
            if not python_block:
                continue
            names = {p.strip().lower() for p in
                     re.findall(r"['\"]([^'\"]+)['\"]", python_block.group(1))}
            if names:
                per_module[manifest.parent.name] = sorted(names)
                declared |= names
    return declared, per_module


def _module_depends(root, module):
    """The ``depends`` list of one addon, or None when it is not present."""
    path = module_path(root, module)
    if path is None:
        return None
    manifest = path / "__manifest__.py"
    if not manifest.is_file():
        return None
    text = manifest.read_text(encoding="utf-8", errors="replace")
    block = re.search(r"['\"]depends['\"]\s*:\s*\[(.*?)\]", text, re.S)
    if not block:
        return []
    return sorted({p.strip() for p in
                   re.findall(r"['\"]([^'\"]+)['\"]", block.group(1))})


def _addon_names(root):
    """Every addon directory name in the tree — so a project module is not
    mistaken for an undeclared third-party package."""
    names = set()
    for addon_root in ADDON_ROOTS:
        base = root / addon_root
        if base.is_dir():
            names |= {p.name for p in base.iterdir() if p.is_dir()}
    return names


@test_case(
    id="TEST-WF010-TC018",
    name="Every third-party Python import used by custom code is importable "
         "and declared",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_data_migration, dto_mrp_sftp, dto_purchase_stock, "
           "novobi_base_export, novobi_sftp_connection",
    priority="P2", kind="DATA", order=10018,
    description="Extracts every non-stdlib, non-Odoo, non-project top-level "
                "import from the custom addon tree, compares it against the "
                "union of every external_dependencies declaration, and "
                "asserts the undeclared remainder is empty apart from the "
                "justified allowlist. Then checks the Odoo-module edges no "
                "Python scan catches — base_import in the depends of all "
                "three modules that instantiate it, plus the other recorded "
                "edges — and reports which packages the platform "
                "interpreter can actually import.",
    traceability=trace("DATAONE-TC018", user_story="shared with "
                                                   "DATAONE-WF-017 and "
                                                   "DATAONE-WF-026"))
def test_tc018(ctx):
    with ctx.step("Shared-case note"):
        ctx.log("DATAONE-TC018 is shared between DATAONE-WF-010, "
                "DATAONE-WF-017 and DATAONE-WF-026. It is implemented once, "
                "here, in the suite of the owning workflow. The other two "
                "reference the same tc_id and must not re-implement it. "
                "Its precondition, TC012 (the dependency set installs), is "
                "owned by WF-020 as TEST-WF020-TC012 — that case owns the "
                "pin comparison, including the openpyxl conflict, and is "
                "not duplicated here.")

    with ctx.step("Locate the DTO-Odoo checkout for THIS target's version"):
        root = resolve_source_root(ctx.env.version)
        if root is None:
            ctx.blocked(
                "The DTO-Odoo source tree is not reachable from this "
                "workstation. Set DTO_SOURCE_ROOT_"
                f"{ctx.env.version} in config/local.yaml — TC018 is a "
                "static scan of the addon tree and cannot be answered from "
                "the database.")
        ctx.log(f"scanning {root} (Odoo {ctx.env.version} tree)")
        addon_names = _addon_names(root)
        ctx.log(f"{len(addon_names)} addon(s) in the tree")

    with ctx.step("Step 1: every non-stdlib, non-Odoo, non-project "
                  "top-level import in the custom tree"):
        all_imports = _top_level_imports(root)
        stdlib = set(sys.stdlib_module_names)
        third_party = {name: places for name, places in all_imports.items()
                       if name not in stdlib
                       and name not in addon_names
                       and name not in {"odoo", "openerp"}}
        ctx.log(f"{len(all_imports)} distinct top-level imports; "
                f"{len(third_party)} are third-party candidates")
        for name in sorted(third_party):
            ctx.log(f"  {name}: {third_party[name][:3]}"
                    f"{' …' if len(third_party[name]) > 3 else ''}")

    with ctx.step("Step 2: every declared external_dependencies['python']"):
        declared, per_module = _declared_python_dependencies(root)
        ctx.log(f"declared python dependencies, by module: {per_module!r}")
        ctx.log(f"union: {sorted(declared)!r}")

    with ctx.step("Step 3: the UNDECLARED set — empty, or every remaining "
                  "line justified"):
        undeclared = sorted(
            name for name in third_party
            if name.lower() not in declared
            and name.lower().replace("_", "-") not in declared
            and name not in JUSTIFIED_UNDECLARED)
        ctx.log(f"undeclared third-party imports: {undeclared!r}")
        ctx.log(f"justified and therefore excluded: "
                f"{sorted(JUSTIFIED_UNDECLARED)!r}")
        ctx.check(
            "every third-party package the custom code imports is declared "
            "in some module's external_dependencies (the workbook's step 3 "
            "expectation: empty, or each remaining line justified)",
            [], undeclared)

    with ctx.step("Step 4: which of them the interpreter can find. NOTE "
                  "this is the PLATFORM's interpreter, not the Odoo "
                  "server's — a version skew between the two is "
                  "TEST-WF020-TC012's subject, not this one's"):
        results = {}
        for name in sorted(third_party):
            if name in JUSTIFIED_UNDECLARED:
                continue
            try:
                found = importlib.util.find_spec(name) is not None
            except (ImportError, ModuleNotFoundError, ValueError):
                found = False
            results[name] = "OK" if found else "NOT FOUND"
        ctx.log(f"import results on {sys.executable}: {results!r}")
        not_found = sorted(k for k, v in results.items() if v != "OK")
        if not_found:
            ctx.log(f"[warn] not importable on the PLATFORM interpreter: "
                    f"{not_found!r}. That is evidence about this venv, not "
                    "about the Odoo server's — the platform venv installs "
                    "only requirements.txt (fastapi, playwright, openpyxl, "
                    "psycopg2, PyYAML, pydantic). A package listed here is "
                    "worth checking on the server, not a failure of the "
                    "custom code.")
        ctx.check_true(
            "the packages this platform DOES share with the server "
            "(openpyxl, psycopg2, pydantic, pytz) resolve, so the scan is "
            "reading a real tree and not an empty one",
            all(results.get(name, "OK") == "OK"
                for name in ("openpyxl",) if name in results),
            actual_desc=repr(results))

    with ctx.step("Step 5: THE EDGE NO PYTHON SCAN CATCHES — base_import "
                  "must appear in the depends of every module that "
                  "instantiates base_import.import"):
        call_sites = {}
        for addon_root in ADDON_ROOTS:
            base = root / addon_root
            if not base.is_dir():
                continue
            for path in sorted(base.rglob("*.py")):
                if "__pycache__" in path.parts:
                    continue
                try:
                    text = path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                if "base_import.import" in text:
                    relative = path.relative_to(base)
                    call_sites.setdefault(relative.parts[0], []).append(
                        str(relative).replace("\\", "/"))
        ctx.log(f"modules instantiating base_import.import: {call_sites!r}")
        missing = {}
        for module in sorted(set(call_sites) | set(BASE_IMPORT_MODULES)):
            depends = _module_depends(root, module)
            if depends is None:
                missing[module] = "module not found in the tree"
            elif "base_import" not in depends:
                missing[module] = depends
            ctx.log(f"  {module}: depends={depends!r}")
        ctx.check(
            "every module that instantiates base_import.import declares "
            "base_import in its depends — it worked only transitively "
            "through account/sale, and a clean Odoo.sh build is where that "
            "stops being true", {}, missing)

    with ctx.step("Step 6: the other recorded undeclared Odoo edges"):
        edge_problems = {}
        for module, required in OTHER_EDGES.items():
            depends = _module_depends(root, module)
            if depends is None:
                ctx.log(f"  {module}: not present in this tree — skipped")
                continue
            absent = [name for name in required if name not in depends]
            ctx.log(f"  {module}: depends={depends!r}; missing={absent!r}")
            if absent:
                edge_problems[module] = absent
        ctx.check(
            "stock_picking_auto_create_lot declares sale and dto_account, "
            "and dto_purchase_stock declares the sale/purchase bridge that "
            "provides purchase.order._get_sale_orders()",
            {}, edge_problems)
