"""logrotate must cover ~/ops-state/rh-chain — and must not touch its data.

Found 2026-07-29 while auditing every directory holding logs >1MB against
`LOG_DIRS`. `~/ops-state/rh-chain/` holds **43 MB** of `.log`/`.err` across 12
files (clean-watchlist 9.2M already past the 5MB threshold, agent-health.stderr
4.9M, orderflow 4.2M) and was not in the list, so it had never been rotated.

Safety established before adding it — these are trading-adjacent rails:
  * `rh_agent_health.py` separates `log_files` from `state_files`; state lives in
    `.json` (`clean-watchlist.json`, `fresh-decay-state.json`, …), never in `.log`.
  * `_log_status()` consumes only existence, mtime, size, and a tail scan — no log
    content is treated as durable state.
  * `rotate_file()` truncates in place, preserving the inode, so the launchd
    processes holding these files open keep writing to the same fd.

The one thing that must never happen: `rh-chain/history/` is **733 MB of data**,
not logs. Rotation walks a directory non-recursively and filters on suffix, so it
cannot reach it — this file pins that guarantee.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load_logrotate():
    spec = importlib.util.spec_from_file_location(
        "sapphire_logrotate_rh", ROOT / "infra" / "logrotate.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["sapphire_logrotate_rh"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def logrotate():
    return _load_logrotate()


def test_rh_chain_is_covered(logrotate):
    """43MB across 12 files, one already past the threshold, never rotated."""
    assert Path.home() / "ops-state" / "rh-chain" in logrotate.LOG_DIRS


def test_previous_coverage_retained(logrotate):
    """Widening must never drop a directory that already worked."""
    for existing in (
        Path.home() / "autonomy-status" / "logs",
        Path.home() / ".hermes" / "logs",
        Path.home() / "ops-state" / "logs",
        ROOT / "data" / "logs",
    ):
        assert existing in logrotate.LOG_DIRS


def test_rotation_never_descends_into_subdirectories(logrotate, tmp_path: Path):
    """rh-chain/history/ is 733MB of DATA. Rotation must not be able to reach it."""
    history = tmp_path / "history"
    history.mkdir()
    buried = history / "snapshot.log"
    buried.write_bytes(b"x" * (logrotate.MAX_BYTES + 1))
    surface = tmp_path / "orderflow.log"
    surface.write_bytes(b"y" * (logrotate.MAX_BYTES + 1))

    logrotate.LOG_DIRS_ORIGINAL = list(logrotate.LOG_DIRS)
    logrotate.LOG_DIRS[:] = [tmp_path]
    try:
        logrotate.main()
    finally:
        logrotate.LOG_DIRS[:] = logrotate.LOG_DIRS_ORIGINAL

    assert surface.stat().st_size == 0, "top-level log should rotate"
    assert buried.stat().st_size > logrotate.MAX_BYTES, "subdirectory must be untouched"
    assert not list(history.glob("*.gz")), "no archive should be written into data dirs"


def test_state_json_files_are_never_rotated(logrotate, tmp_path: Path):
    """`clean-watchlist.json` is state. Only .log/.err are eligible."""
    state = tmp_path / "clean-watchlist.json"
    state.write_bytes(b"z" * (logrotate.MAX_BYTES + 1))

    assert ".json" not in logrotate.EXTENSIONS
    assert logrotate.rotate_file(state) is False
    assert state.stat().st_size > logrotate.MAX_BYTES
