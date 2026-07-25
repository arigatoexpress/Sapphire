"""Shared fixtures for unit tests.

`monitor`: loads `scripts/ops/staleness_monitor.py` as a module so tests can
reference its public API without touching sys.path. The staleness monitor is
a script (not a package) so this is the cleanest way to import it.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_staleness_monitor():
    # sys.modules registration must happen before exec_module — Python 3.14
    # dataclass introspection resolves forward refs by looking up the module.
    spec = importlib.util.spec_from_file_location(
        "staleness_monitor",
        REPO_ROOT / "scripts" / "ops" / "staleness_monitor.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["staleness_monitor"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def monitor(monkeypatch, tmp_path):
    module = _load_staleness_monitor()
    # Retarget REPO_ROOT so glob resolution + relative paths land in tmp_path.
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    return module
