"""The canonical checkout must not silently run behind origin/main.

Regression context (2026-07-28/29): PRs #991 and #992 were merged to `main`, but
`~/Code/Sapphire` was checked out on a feature branch that did not contain either
merge. **LaunchAgents execute from the working checkout, not from `main`** — so both
fixes were merged, green, and not running, and nothing anywhere reported that.

`canonical_checkout_clean` does not catch this: the tree was 0-modified and
perfectly "clean" while being behind. Clean and current are different properties,
and only one of them was being checked.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load_sweep():
    spec = importlib.util.spec_from_file_location(
        "sapphire_readiness_sweep", ROOT / "scripts" / "ops" / "production_readiness_sweep.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["sapphire_readiness_sweep"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def sweep():
    return _load_sweep()


def _fake_run_factory(sweep, *, behind: str, status: str = "", branch: str = "## main"):
    """Stub git: `rev-list --count HEAD..origin/main` returns `behind`."""

    def fake_run(cmd, *, cwd=None, timeout=20, env=None):
        del cwd, timeout, env
        if "rev-list" in cmd:
            return sweep.RunResult(0, f"{behind}\n", "", 1)
        if "worktree" in cmd:
            return sweep.RunResult(0, "", "", 1)
        if "--porcelain=v1" in cmd:
            return sweep.RunResult(0, status, "", 1)
        return sweep.RunResult(0, f"{branch}\n", "", 1)

    return fake_run


def _find(checks, name):
    for c in checks:
        if c.name == name:
            return c
    raise AssertionError(f"{name} not in {[c.name for c in checks]}")


def test_checkout_behind_main_is_reported(sweep, monkeypatch):
    """The exact 2026-07-28 condition: clean tree, 2 merges missing."""
    monkeypatch.setattr(sweep, "run", _fake_run_factory(sweep, behind="2"))

    check = _find(sweep.probe_repo(), "canonical_checkout_current")

    assert check.status == "WARN"
    assert "2" in check.evidence
    assert "origin/main" in check.evidence


def test_checkout_up_to_date_passes(sweep, monkeypatch):
    monkeypatch.setattr(sweep, "run", _fake_run_factory(sweep, behind="0"))

    check = _find(sweep.probe_repo(), "canonical_checkout_current")

    assert check.status == "PASS"


def test_clean_but_behind_still_warns(sweep, monkeypatch):
    """Clean != current. The tree was 0-modified while behind — both must report."""
    monkeypatch.setattr(sweep, "run", _fake_run_factory(sweep, behind="7", status=""))

    checks = sweep.probe_repo()

    assert _find(checks, "canonical_checkout_clean").status == "PASS"
    assert _find(checks, "canonical_checkout_current").status == "WARN"


def test_unresolvable_origin_does_not_crash_the_sweep(sweep, monkeypatch):
    """Offline / no remote must degrade to WARN, never raise — this runs in launchd."""

    def fake_run(cmd, *, cwd=None, timeout=20, env=None):
        del cwd, timeout, env
        if "rev-list" in cmd:
            return sweep.RunResult(128, "", "fatal: bad revision 'origin/main'", 1)
        return sweep.RunResult(0, "", "", 1)

    monkeypatch.setattr(sweep, "run", fake_run)

    check = _find(sweep.probe_repo(), "canonical_checkout_current")

    assert check.status == "WARN"
    assert "unavailable" in check.evidence.lower() or "unknown" in check.evidence.lower()
