"""DATAONE-WF-020 — the Python dependency set: TC012.

The workbook's steps build a fresh virtualenv and install Odoo's
requirements followed by DataOne's, in Odoo.sh order. This platform does
not build environments, so what it implements is the half that decides the
outcome *before* any install runs: the pin comparison between the two
requirements files, and the ``external_dependencies`` declarations in the
manifests.

That half is where the workbook's own CONFIRMED finding lives. Odoo 19 adds
``openpyxl`` to its ``requirements.txt`` — one of four packages newly
pinned there — while DataOne pins ``openpyxl==3.1.5``. On Odoo.sh Odoo's
file installs first, so a direct pin conflict surfaces at build time. Step
4's expectation is explicit: *"the DataOne pin must be >=3.1.2 or ==3.1.2 —
not ==3.1.5"*.

Both files are read from disk (``framework/source_scan.py`` resolves the
DTO-Odoo checkout; the Odoo requirements come from the sibling
``odoo-19.0`` / ``odoo-17.0`` tree), so the test needs neither a server nor
a database.

EXPECTED v17 OUTCOME: **FAIL at the openpyxl pin.** The expectation
describes the required post-remediation state, and today DataOne still pins
``openpyxl==3.1.5``. Convention rule 2: the expectation is immutable.
EXPECTED v19 OUTCOME: PASS once the pin is relaxed.
"""
import json
import os
import re
from pathlib import Path

from framework.registry import test_case
from framework.source_scan import module_path, resolve_source_root
from tests.wf020.common import WORKFLOW, WORKFLOW_NAME, trace  # noqa: F401

# Where the Odoo source trees live. Overridable per workstation, like the
# DTO-Odoo checkout, because this is a filesystem fact and not a database one.
ODOO_ROOTS = {
    "17": Path(os.environ.get("ODOO17_SOURCE_ROOT")
               or r"D:\Projects\dataone\odoo-17.0"),
    "19": Path(os.environ.get("ODOO19_SOURCE_ROOT")
               or r"D:\Projects\odoo-19.0"),
}

# Step 5 — the packages the custom code actually imports, including the
# four novobi_sftp_connection uses without declaring.
REQUIRED_IMPORTS = ["paramiko", "xmltodict", "pydantic", "pytz", "openpyxl",
                    "img2pdf", "requests", "xlsxwriter"]

# Step 7 — the external_dependencies each module must declare.
EXPECTED_DECLARATIONS = {
    "novobi_sftp_connection": {"paramiko", "xmltodict"},
    "dto_account_workday": {"openpyxl"},
    "novobi_base_export": {"openpyxl"},
    "dto_purchase_stock": {"img2pdf"},
    "queue_job": {"requests"},
}

_REQ_RE = re.compile(r"^\s*([A-Za-z0-9_.\-]+)\s*([<>=!~]+)?\s*([^\s;#]+)?")


def _parse_requirements(path: Path) -> dict:
    """{package (lower-cased): 'operator+version' or ''} from a pip file."""
    pins = {}
    if not path.is_file():
        return pins
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        m = _REQ_RE.match(line)
        if not m:
            continue
        name = m.group(1).lower().replace("_", "-")
        pins[name] = f"{m.group(2) or ''}{m.group(3) or ''}"
    return pins


def _manifest_dependencies(root: Path, module: str) -> set:
    path = module_path(root, module)
    if path is None:
        return set()
    manifest = path / "__manifest__.py"
    if not manifest.is_file():
        return set()
    text = manifest.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"['\"]external_dependencies['\"]\s*:\s*\{(.+?)\}",
                  text, re.S)
    if not m:
        return set()
    python_block = re.search(r"['\"]python['\"]\s*:\s*\[(.*?)\]",
                             m.group(1), re.S)
    if not python_block:
        return set()
    return {p.strip().lower()
            for p in re.findall(r"['\"]([^'\"]+)['\"]", python_block.group(1))}


@test_case(
    id="TEST-WF020-TC012",
    name="The Python dependency set installs on the target Python",
    workflow=WORKFLOW, workflow_name=WORKFLOW_NAME,
    module="dto_account_workday, novobi_base_export, novobi_sftp_connection",
    priority="P0", kind="DATA", order=20012,
    description="Compares DataOne's requirements.txt against the target "
                "Odoo's, resolves the openpyxl pin conflict Odoo 19 "
                "introduces, and checks that every package the custom code "
                "imports is both pinned and declared in the right module's "
                "external_dependencies.",
    traceability=trace("DATAONE-TC012"))
def test_tc012(ctx):
    with ctx.step("Locate the DTO-Odoo checkout and the target Odoo tree"):
        root = resolve_source_root()
        if root is None:
            ctx.blocked(
                "The DTO-Odoo source tree is not reachable from this "
                "workstation. Set DTO_SOURCE_ROOT in config/local.yaml — "
                "TC012 compares two requirements files on disk and cannot "
                "be answered from the database.")
        odoo_root = ODOO_ROOTS.get(ctx.env.version)
        if odoo_root is None or not odoo_root.is_dir():
            ctx.blocked(
                f"The Odoo {ctx.env.version} source tree is not reachable "
                f"(looked in {odoo_root}). Set ODOO{ctx.env.version}_"
                "SOURCE_ROOT in config/local.yaml. Without Odoo's own "
                "requirements.txt there is nothing to compare the DataOne "
                "pins against.")
        ctx.log(f"DataOne: {root}; Odoo {ctx.env.version}: {odoo_root}")

    with ctx.step("Parse both requirements files and record the evidence "
                  "before asserting"):
        dto_reqs = _parse_requirements(root / "requirements.txt")
        odoo_reqs = _parse_requirements(odoo_root / "requirements.txt")
        declared = {m: sorted(_manifest_dependencies(root, m))
                    for m in EXPECTED_DECLARATIONS}
        evidence = {
            "dataone_requirements": dto_reqs,
            f"odoo{ctx.env.version}_requirements": odoo_reqs,
            "declared_external_dependencies": declared,
        }
        path = ctx.artifacts_dir / "tc012_requirements.json"
        path.write_text(json.dumps(evidence, indent=1, ensure_ascii=False),
                        encoding="utf-8")
        ctx.add_artifact(path, "log", "TC012 dependency comparison")
        ctx.log(f"DataOne pins {len(dto_reqs)}, Odoo pins {len(odoo_reqs)}")

    with ctx.step("Both requirements files were found and are non-empty"):
        ctx.check_true("DataOne requirements.txt parsed",
                       bool(dto_reqs),
                       actual_desc=f"{len(dto_reqs)} pin(s) at "
                                   f"{root / 'requirements.txt'}")
        ctx.check_true(f"Odoo {ctx.env.version} requirements.txt parsed",
                       bool(odoo_reqs),
                       actual_desc=f"{len(odoo_reqs)} pin(s) at "
                                   f"{odoo_root / 'requirements.txt'}")

    with ctx.step("Every package the custom code imports is pinned "
                  "somewhere — by DataOne or by Odoo"):
        combined = set(dto_reqs) | set(odoo_reqs)
        unpinned = [p for p in REQUIRED_IMPORTS
                    if p.lower().replace("_", "-") not in combined]
        ctx.log(f"unpinned imports: {unpinned}")
        ctx.check("packages imported by custom code but pinned nowhere", [],
                  unpinned)

    with ctx.step("Step 4: the openpyxl pin conflict Odoo 19 introduces is "
                  "resolved by policy — the DataOne pin must be >=3.1.2 or "
                  "==3.1.2, and NOT ==3.1.5"):
        dto_pin = dto_reqs.get("openpyxl")
        odoo_pin = odoo_reqs.get("openpyxl")
        ctx.log(f"openpyxl — DataOne: {dto_pin!r}, "
                f"Odoo {ctx.env.version}: {odoo_pin!r}")
        ctx.check("DataOne's openpyxl pin", True,
                  dto_pin in (">=3.1.2", "==3.1.2", None, ""))

    with ctx.step("No other package is pinned incompatibly by both files "
                  "— a hard-equals on both sides with different versions "
                  "cannot resolve"):
        conflicts = {}
        for pkg, dto_pin in dto_reqs.items():
            odoo_pin = odoo_reqs.get(pkg)
            if not odoo_pin or not dto_pin:
                continue
            if (dto_pin.startswith("==") and odoo_pin.startswith("==")
                    and dto_pin != odoo_pin):
                conflicts[pkg] = {"dataone": dto_pin, "odoo": odoo_pin}
        ctx.check("irreconcilable == pins across the two files", {},
                  conflicts)

    with ctx.step("Step 7: each module declares the external dependencies "
                  "its own code imports"):
        missing = {}
        for module, expected in EXPECTED_DECLARATIONS.items():
            if module_path(root, module) is None:
                continue                      # not part of this checkout
            gap = sorted(expected - set(declared.get(module) or []))
            if gap:
                missing[module] = gap
        ctx.log(f"declared: {declared!r}")
        ctx.check("undeclared external_dependencies per module", {}, missing)

    with ctx.step("Steps 1-3, 5-6 and 8 need a built virtualenv"):
        ctx.blocked(
            "Recording the interpreter and PostgreSQL versions, building a "
            "fresh virtualenv, installing both requirement files in "
            "Odoo.sh order, running pip check, importing the eight "
            "packages and opening the two vendor XLSX templates on the "
            "installed openpyxl are CI build steps: they need network "
            "access and a throwaway environment, neither of which this "
            "platform takes on (it writes no environments and starts no "
            "servers). Run them from the v19 build pipeline. The pin "
            "comparison and the manifest declarations above are the half "
            "that decides the build's outcome before it runs.")
