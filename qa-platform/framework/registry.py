"""Test-case registry.

Tests self-register with the @test_case decorator. The web UI, the API and
the execution engine all read from this registry — adding a test file under
tests/ makes it appear in the dashboard with zero UI changes.

Every entry carries traceability back to the Excel knowledge base
(MMG_v19_Test_Cases_Grouped_by_Feature_v2.0.xlsx) via tc_ids.
"""
from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class TestCaseDef:
    id: str
    name: str
    func: Callable
    workflow: str = ""
    workflow_name: str = ""
    module: str = ""
    priority: str = "P2"
    kind: str = "API"           # UI | API | HYBRID
    order: int = 100
    description: str = ""
    traceability: dict = field(default_factory=dict)  # excel tc_ids, feature, user_story

    def public_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "workflow": self.workflow,
            "workflow_name": self.workflow_name, "module": self.module,
            "priority": self.priority, "kind": self.kind,
            "description": self.description, "traceability": self.traceability,
        }


_REGISTRY: dict[str, TestCaseDef] = {}


def test_case(**meta):
    def wrapper(func):
        tc = TestCaseDef(func=func, **meta)
        if tc.id in _REGISTRY:
            raise ValueError(f"Duplicate test id: {tc.id}")
        _REGISTRY[tc.id] = tc
        return func
    return wrapper


def discover() -> list[TestCaseDef]:
    """Import every module under tests/ so decorators run, then return
    the registry ordered for execution."""
    import tests as tests_pkg
    for mod in pkgutil.walk_packages(tests_pkg.__path__, prefix="tests."):
        if not mod.ispkg:
            importlib.import_module(mod.name)
    return sorted(_REGISTRY.values(), key=lambda t: (t.order, t.id))


def reload() -> list[TestCaseDef]:
    """Drop the registry and re-import every test module from disk.

    Lets the platform pick up newly added or edited test scripts without a
    server restart (POST /api/registry/reload).
    """
    import sys
    _REGISTRY.clear()

    # THE RULE: a module may be dropped only if no long-lived object holds a
    # CLASS from it. Re-importing a module builds new class objects, and an
    # `except SomeError` in freshly imported test code then no longer matches
    # the SomeError raised by something imported at server start. The failure
    # is silent and total — the handler simply stops running.
    #
    # Measured after a reload, every one of these stopped matching:
    #   adapters.base.OdooRPCError    caught by every suite's sweep, raised
    #                                 by the adapter the runner built at
    #                                 start — so guarded teardown began
    #                                 erroring out mid-sweep;
    #   framework.context.BlockedTest / AssertionFailed / SkipTest
    #                                 caught by backend.runner — so every
    #                                 deliberate BLOCK and every assertion
    #                                 failure was recorded as ERROR instead.
    #
    # Suites do import shared helpers from framework.*, and picking those up
    # without a restart is the point of this endpoint, so the pure-helper
    # modules are still dropped. The three that export classes across the
    # boundary are not.
    KEEP = {"framework.registry",    # owns _REGISTRY and the decorator
            "framework.context"}     # BlockedTest / SkipTest / AssertionFailed
    stale = [n for n in sys.modules
             if (n == "tests" or n.startswith("tests."))
             or ((n == "framework" or n.startswith("framework."))
                 and n not in KEEP)]
    # adapters.* is never dropped: OdooRPCError is caught by test code and
    # raised by adapter instances the runner created before this call.
    for name in stale:
        del sys.modules[name]
    importlib.invalidate_caches()
    return discover()


def get(test_id: str) -> TestCaseDef:
    if not _REGISTRY:
        discover()
    return _REGISTRY[test_id]
