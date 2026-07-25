"""Tests for scripts/ops/staleness_monitor.py.

Covers the three status classes (FRESH, STALE, MISSING) plus optional-path
semantics, glob resolution (newest-wins), and exit-code behavior.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "ops" / "staleness_monitor.py"


def _load_module():
    # sys.modules registration is required before exec_module — otherwise the
    # dataclass introspection in Python 3.14 cannot look the module up when it
    # resolves forward references on Row.
    spec = importlib.util.spec_from_file_location("staleness_monitor", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["staleness_monitor"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def monitor(monkeypatch, tmp_path):
    module = _load_module()
    # Retarget REPO_ROOT so glob resolution + relative paths land in tmp_path.
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    return module


def _write_config(tmp_path: Path, body: str) -> Path:
    cfg = tmp_path / "staleness.yaml"
    cfg.write_text(body, encoding="utf-8")
    return cfg


def test_fresh_when_within_threshold(monitor, tmp_path):
    target_dir = tmp_path / "data"
    target_dir.mkdir()
    fresh = target_dir / "fresh.jsonl"
    fresh.write_text("{}\n", encoding="utf-8")
    rows = [monitor.evaluate({"label": "fresh", "path": "data/fresh.jsonl", "max_age_h": 24}, time.time())]
    assert rows[0].status == "FRESH"
    assert rows[0].resolved_path == "data/fresh.jsonl"


def test_stale_when_older_than_threshold(monitor, tmp_path):
    target = tmp_path / "old.txt"
    target.write_text("x", encoding="utf-8")
    old_mtime = time.time() - 7200  # 2h ago
    import os

    os.utime(target, (old_mtime, old_mtime))
    row = monitor.evaluate({"label": "old", "path": "old.txt", "max_age_h": 1}, time.time())
    assert row.status == "STALE"
    assert row.age_hours is not None and row.age_hours > 1.0


def test_missing_required_reports_stale(monitor, tmp_path):
    row = monitor.evaluate({"label": "gone", "path": "nowhere.json", "max_age_h": 1}, time.time())
    assert row.status == "STALE"
    assert row.age_hours is None


def test_missing_optional_reports_missing(monitor, tmp_path):
    row = monitor.evaluate(
        {"label": "gone", "path": "nowhere.json", "max_age_h": 1, "optional": True},
        time.time(),
    )
    assert row.status == "MISSING"


def test_glob_resolves_newest_file(monitor, tmp_path):
    stream = tmp_path / "signals"
    stream.mkdir()
    old = stream / "2026-07-01.jsonl"
    new = stream / "2026-07-10.jsonl"
    old.write_text("{}", encoding="utf-8")
    new.write_text("{}", encoding="utf-8")
    import os

    os.utime(old, (time.time() - 3600 * 24 * 10, time.time() - 3600 * 24 * 10))
    os.utime(new, (time.time() - 60, time.time() - 60))
    row = monitor.evaluate({"label": "signals", "path": "signals/*.jsonl", "max_age_h": 1}, time.time())
    assert row.status == "FRESH"
    assert row.resolved_path.endswith("2026-07-10.jsonl")


def test_load_config_parses_targets(monitor, tmp_path):
    cfg = _write_config(
        tmp_path,
        """
# comment ignored
targets:
  - label: a
    path: a.json
    max_age_h: 1
  - label: b
    path: b.json
    max_age_h: 24
    optional: true
""".strip(),
    )
    targets = monitor.load_config(cfg)
    assert len(targets) == 2
    assert targets[0] == {"label": "a", "path": "a.json", "max_age_h": 1}
    assert targets[1] == {"label": "b", "path": "b.json", "max_age_h": 24, "optional": True}


def test_cli_exits_nonzero_on_stale(tmp_path):
    # Integration test — runs the real script against a temp config + repo root.
    fresh_dir = tmp_path / "data"
    fresh_dir.mkdir()
    old = fresh_dir / "old.json"
    old.write_text("{}", encoding="utf-8")
    import os

    os.utime(old, (time.time() - 3600 * 48, time.time() - 3600 * 48))

    cfg = _write_config(
        tmp_path,
        """
targets:
  - label: old
    path: data/old.json
    max_age_h: 1
""".strip(),
    )
    # Point the script's REPO_ROOT at tmp_path via env — not natively supported,
    # so we invoke it with an explicit --config and rely on the tmp file living
    # at the absolute path we control. The default REPO_ROOT-relative resolver
    # will fail to find data/old.json unless we run from tmp_path.
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--config", str(cfg), "--exit-nonzero-on-stale", "--json"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    # Script uses its own REPO_ROOT (the sapphire repo), so relative path won't
    # resolve — the row lands as MISSING/STALE depending on optional flag.
    # We assert the exit code path works: STALE (required missing) → exit 2.
    assert proc.returncode == 2, proc.stdout + proc.stderr
    payload = json.loads(proc.stdout)
    assert payload[0]["status"] == "STALE"


def test_absolute_and_home_paths_resolve_outside_the_repo(monitor, tmp_path):
    """Several producers write outside the worktree (~/autonomy-status/logs).

    A repo-relative-only resolver would report those permanently MISSING, which
    is how a monitoring blind spot gets baked in.
    """
    outside = tmp_path.parent / "outside-repo-artifact.json"
    outside.write_text("{}", encoding="utf-8")
    try:
        row = monitor.evaluate(
            {"label": "outside", "path": str(outside), "max_age_h": 24}, time.time()
        )
        assert row.status == "FRESH"
        assert row.resolved_path == str(outside)
    finally:
        outside.unlink()


def test_failing_agents_flags_nonzero_exit(monitor, monkeypatch):
    """A job can be loaded, exit non-zero every cycle, and look alive."""

    def fake_run(*_args, **_kwargs):
        return subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=(
                "123\t0\tcom.sapphire.heartbeat\n"
                "-\t1\tcom.sapphire.threat-refresh\n"
                "-\t0\tcom.sapphire.gcp-sync\n"
                "456\t0\tcom.apple.something\n"
            ),
            stderr="",
        )

    monkeypatch.setattr(monitor.subprocess, "run", fake_run)
    labels = {a.label: a.last_exit for a in monitor.failing_agents()}

    assert labels == {"com.sapphire.threat-refresh": "1"}


def test_failing_agents_exempts_readiness_cache_diagnostic_exit(monitor, monkeypatch):
    """The sweep exits 20 by design when it finds FAILs — not a crash.

    Without the exemption this alerts on every cycle, and an always-firing
    monitor is one nobody reads.
    """

    def fake_run(*_args, **_kwargs):
        return subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="-\t20\tcom.sapphire.readiness-cache\n-\t2\tcom.sapphire.readiness-cache-x\n",
            stderr="",
        )

    monkeypatch.setattr(monitor.subprocess, "run", fake_run)
    labels = [a.label for a in monitor.failing_agents()]

    assert "com.sapphire.readiness-cache" not in labels
    assert "com.sapphire.readiness-cache-x" in labels


def test_alert_draft_is_queued_never_sent(monitor, monkeypatch, tmp_path):
    """The alert path must terminate in a draft an operator has to approve."""
    queue = tmp_path / "drafts.jsonl"
    monkeypatch.setenv("SAPPHIRE_PM_BOT_DRAFT_QUEUE_PATH", str(queue))

    rows = [monitor.Row("threat-intel", "data/x.json", "STALE", 99.0, 12.0, "data/x.json")]
    agents = [monitor.AgentRow("com.sapphire.threat-refresh", "1")]

    draft_id = monitor.queue_alert(rows, agents)

    assert draft_id.startswith("tg_draft_")
    record = json.loads(queue.read_text(encoding="utf-8").splitlines()[0])
    assert record["status"] == "draft"
    assert record["requires_confirmation"] is True
    assert record["metadata"]["external_side_effect"] is False
    assert "threat-intel" in record["body"]
    assert "com.sapphire.threat-refresh" in record["body"]


def test_fingerprint_ignores_age_drift(monitor):
    """Ages advance every run; including them would defeat dedup entirely."""
    a = [monitor.Row("x", "p", "STALE", 10.0, 1.0, "p")]
    b = [monitor.Row("x", "p", "STALE", 99.0, 1.0, "p")]

    assert monitor.alert_fingerprint(a, []) == monitor.alert_fingerprint(b, [])


def test_fingerprint_changes_when_a_new_problem_appears(monitor):
    one = [monitor.Row("x", "p", "STALE", 10.0, 1.0, "p")]
    two = one + [monitor.Row("y", "q", "STALE", 10.0, 1.0, "q")]

    assert monitor.alert_fingerprint(one, []) != monitor.alert_fingerprint(two, [])


def test_repeat_alert_suppressed_within_cooldown(monitor, tmp_path):
    """A 23-day-stale file must not queue one draft per run forever."""
    state = tmp_path / "alert_state.json"
    now = time.time()

    assert monitor.should_alert("fp1", now=now, state_path=state) is True
    monitor.record_alert("fp1", now=now, state_path=state)

    # Same problem set an hour later: stay quiet.
    assert monitor.should_alert("fp1", now=now + 3600, state_path=state) is False
    # A different problem set: alert immediately, cooldown or not.
    assert monitor.should_alert("fp2", now=now + 3600, state_path=state) is True
    # Same problem set past the cooldown: alert again.
    assert monitor.should_alert("fp1", now=now + 25 * 3600, state_path=state) is True
