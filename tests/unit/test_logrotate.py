"""Unit tests for infra/logrotate.py.

Regression context (2026-07-28): `com.sapphire.moss-publisher` runs every 60s
against an endpoint returning 503 and had written a **6.7 MB** `.err` file over
~4 days. logrotate exited 0 the whole time and never touched it, because
`~/ops-state/logs/` was not in LOG_DIRS. The single largest log on the box,
`~/Code/Sapphire/data/logs/webhook-tunnel.log` (15 MB), was uncovered for the
same reason. Rotation that silently skips the noisiest directories is worse than
no rotation: it reports success while the disk fills.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load_logrotate():
    """Load infra/logrotate.py by path — it is a script, not an importable pkg."""
    spec = importlib.util.spec_from_file_location(
        "sapphire_logrotate", ROOT / "infra" / "logrotate.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["sapphire_logrotate"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def logrotate():
    return _load_logrotate()


def test_log_dirs_cover_ops_state(logrotate):
    """~/ops-state/logs must be rotated — it held the 6.7MB moss-publisher.err."""
    assert Path.home() / "ops-state" / "logs" in logrotate.LOG_DIRS


def test_log_dirs_cover_sapphire_data_logs(logrotate):
    """Sapphire's own data/logs holds the largest file on the box (webhook-tunnel)."""
    assert ROOT / "data" / "logs" in logrotate.LOG_DIRS


def test_log_dirs_retains_original_coverage(logrotate):
    """Widening must not drop the directories that already worked."""
    assert Path.home() / "autonomy-status" / "logs" in logrotate.LOG_DIRS
    assert Path.home() / ".hermes" / "logs" in logrotate.LOG_DIRS


def test_err_files_are_rotated(logrotate, tmp_path: Path):
    """.err is as noisy as .log — a failing job writes stderr, not stdout."""
    big = tmp_path / "moss-publisher.err"
    big.write_bytes(b"x" * (logrotate.MAX_BYTES + 1))

    assert logrotate.rotate_file(big) is True
    assert big.stat().st_size == 0  # truncated, not deleted
    assert list(tmp_path.glob("moss-publisher.*.err.gz"))


def test_small_files_are_left_alone(logrotate, tmp_path: Path):
    small = tmp_path / "quiet.log"
    small.write_bytes(b"x" * 128)

    assert logrotate.rotate_file(small) is False
    assert small.stat().st_size == 128
    assert not list(tmp_path.glob("*.gz"))


def test_rotate_truncates_so_running_writer_survives(logrotate, tmp_path: Path):
    """Truncate rather than unlink: launchd holds the fd open across rotations."""
    log = tmp_path / "live.log"
    log.write_bytes(b"y" * (logrotate.MAX_BYTES + 1))
    inode_before = log.stat().st_ino

    logrotate.rotate_file(log)

    assert log.exists()
    assert log.stat().st_ino == inode_before


def test_prune_keeps_only_recent_copies(logrotate, tmp_path: Path):
    for i in range(logrotate.KEEP_COPIES + 3):
        p = tmp_path / f"svc.2026072{i}_000000.log.gz"
        p.write_bytes(b"z")
        # Distinct mtimes so ordering is deterministic.
        import os

        os.utime(p, (1000 + i, 1000 + i))

    logrotate.prune_old_rotations(tmp_path, "svc")

    assert len(list(tmp_path.glob("svc.*.gz"))) == logrotate.KEEP_COPIES
