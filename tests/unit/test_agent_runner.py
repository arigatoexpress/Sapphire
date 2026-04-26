"""Tests for lib/agents/runner.py.

Covers the agent registry, the heartbeat writer, the status state machine
(RUNNING vs STOPPED based on heartbeat age vs cycle interval), and the
process-wide singleton accessor. Uses ``tmp_path`` for filesystem isolation.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from lib.agents import runner
from lib.agents.base import BaseAgent
from lib.agents.runner import AgentRunner, get_runner, load_agent_class

# --- registry --------------------------------------------------------------


def test_load_agent_class_resolves_alpha():
    cls = load_agent_class("alpha")
    assert issubclass(cls, BaseAgent)


def test_load_agent_class_raises_on_unknown_name():
    with pytest.raises(KeyError, match="Unknown agent 'nope'"):
        load_agent_class("nope")


# --- AgentRunner construction ---------------------------------------------


def test_runner_init_creates_heartbeat_dir(tmp_path: Path):
    AgentRunner(repo_root=tmp_path)
    assert (tmp_path / "data" / "agents").exists()
    assert (tmp_path / "data" / "agents").is_dir()


# --- _write_heartbeat ------------------------------------------------------


class _StubAgent(BaseAgent):
    def __init__(
        self,
        name: str = "stub",
        interval_sec: int = 5,
        cycle_count: int = 0,
        last_completed: datetime | None = None,
        last_observation: dict | None = None,
    ):
        super().__init__(name, interval_sec, event_bus=None)
        self.cycle_count = cycle_count
        self.last_cycle_completed_at = last_completed
        self.last_observation = last_observation or {}

    def plan(self):  # pragma: no cover - not exercised
        return []

    def act(self, actions):  # pragma: no cover
        return []

    def observe(self, results):  # pragma: no cover
        return {}


def test_write_heartbeat_persists_expected_fields(tmp_path: Path):
    r = AgentRunner(repo_root=tmp_path)
    when = datetime(2026, 4, 26, 21, 0, tzinfo=UTC)
    a = _StubAgent(name="alpha", interval_sec=300, cycle_count=7, last_completed=when, last_observation={"trades": 3})
    r._write_heartbeat(a)
    path = tmp_path / "data" / "agents" / "alpha.heartbeat"
    payload = json.loads(path.read_text())
    assert payload["agent"] == "alpha"
    assert payload["cycle_count"] == 7
    assert payload["interval_sec"] == 300
    assert payload["last_cycle_completed_at"] == when.isoformat()
    assert payload["last_observation"] == {"trades": 3}
    assert "updated_at" in payload


def test_write_heartbeat_handles_no_last_completed(tmp_path: Path):
    r = AgentRunner(repo_root=tmp_path)
    a = _StubAgent(name="cold")
    r._write_heartbeat(a)
    payload = json.loads((tmp_path / "data" / "agents" / "cold.heartbeat").read_text())
    assert payload["last_cycle_completed_at"] is None


# --- _parse_iso ------------------------------------------------------------


def test_parse_iso_parses_z_suffix(tmp_path: Path):
    r = AgentRunner(repo_root=tmp_path)
    parsed = r._parse_iso("2026-04-26T21:00:00Z")
    assert parsed is not None
    assert parsed.tzinfo is not None
    assert parsed == datetime(2026, 4, 26, 21, 0, tzinfo=UTC)


def test_parse_iso_returns_none_on_garbage(tmp_path: Path):
    r = AgentRunner(repo_root=tmp_path)
    assert r._parse_iso("not-a-date") is None


# --- _status_record state transitions --------------------------------------


def test_status_record_running_when_loaded_in_memory(tmp_path: Path):
    r = AgentRunner(repo_root=tmp_path)
    r._running_agents.add("alpha")
    record = r._status_record(
        name="alpha", interval_sec=300, cycle_count=5,
        last_cycle_completed_at=None, heartbeat_updated_at=None,
    )
    assert record["state"] == "RUNNING"


def test_status_record_stopped_when_no_heartbeat_and_not_running(tmp_path: Path):
    r = AgentRunner(repo_root=tmp_path)
    record = r._status_record(
        name="alpha", interval_sec=300, cycle_count=5,
        last_cycle_completed_at=None, heartbeat_updated_at=None,
    )
    assert record["state"] == "STOPPED"


def test_status_record_running_when_heartbeat_recent(tmp_path: Path):
    r = AgentRunner(repo_root=tmp_path)
    recent = (datetime.now(UTC) - timedelta(seconds=10)).isoformat()
    record = r._status_record(
        name="alpha", interval_sec=60, cycle_count=5,
        last_cycle_completed_at=None, heartbeat_updated_at=recent,
    )
    assert record["state"] == "RUNNING"
    assert record["heartbeat_age_sec"] is not None
    assert record["heartbeat_age_sec"] <= 60


def test_status_record_stopped_when_heartbeat_stale(tmp_path: Path):
    r = AgentRunner(repo_root=tmp_path)
    stale = (datetime.now(UTC) - timedelta(seconds=600)).isoformat()
    record = r._status_record(
        name="alpha", interval_sec=60, cycle_count=5,
        last_cycle_completed_at=None, heartbeat_updated_at=stale,
    )
    assert record["state"] == "STOPPED"
    assert record["heartbeat_age_sec"] >= 600


def test_status_record_threshold_default_when_interval_zero(tmp_path: Path):
    """With interval_sec == 0, the threshold falls back to 60s."""
    r = AgentRunner(repo_root=tmp_path)
    just_under = (datetime.now(UTC) - timedelta(seconds=30)).isoformat()
    record = r._status_record(
        name="alpha", interval_sec=0, cycle_count=0,
        last_cycle_completed_at=None, heartbeat_updated_at=just_under,
    )
    assert record["state"] == "RUNNING"


# --- status() --------------------------------------------------------------


def test_status_with_no_agents_returns_zero_counts(tmp_path: Path):
    r = AgentRunner(repo_root=tmp_path)
    out = r.status()
    assert out["agents"] == {}
    assert out["total"] == 0
    assert out["running"] == 0
    assert out["paused"] == 0
    assert out["stopped"] == 0


def test_status_includes_loaded_agents_in_memory(tmp_path: Path):
    r = AgentRunner(repo_root=tmp_path)
    a = _StubAgent(name="alpha", interval_sec=60, cycle_count=3)
    r._loaded_agents["alpha"] = a
    r._running_agents.add("alpha")
    out = r.status()
    assert "alpha" in out["agents"]
    assert out["agents"]["alpha"]["cycle_count"] == 3
    assert out["agents"]["alpha"]["interval_sec"] == 60
    assert out["agents"]["alpha"]["state"] == "RUNNING"
    assert out["total"] == 1
    assert out["running"] == 1


def test_status_picks_up_heartbeat_files_for_unloaded_agents(tmp_path: Path):
    r = AgentRunner(repo_root=tmp_path)
    payload = {
        "cycle_count": 12,
        "interval_sec": 300,
        "last_cycle_completed_at": "2026-04-26T20:00:00+00:00",
        "updated_at": (datetime.now(UTC) - timedelta(seconds=10)).isoformat(),
    }
    (tmp_path / "data" / "agents" / "ghost.heartbeat").write_text(json.dumps(payload))
    out = r.status()
    assert "ghost" in out["agents"]
    assert out["agents"]["ghost"]["cycle_count"] == 12
    assert out["agents"]["ghost"]["state"] == "RUNNING"


def test_status_skips_corrupt_heartbeat_files(tmp_path: Path):
    r = AgentRunner(repo_root=tmp_path)
    (tmp_path / "data" / "agents" / "broken.heartbeat").write_text("{not valid json")
    out = r.status()
    assert "broken" not in out["agents"]


def test_status_marks_stopped_when_in_memory_agent_has_no_heartbeat_and_not_running(
    tmp_path: Path,
):
    r = AgentRunner(repo_root=tmp_path)
    a = _StubAgent(name="dormant", interval_sec=60)
    r._loaded_agents["dormant"] = a
    out = r.status()
    assert out["agents"]["dormant"]["state"] == "STOPPED"
    assert out["stopped"] == 1


# --- get_runner singleton --------------------------------------------------


def test_get_runner_returns_same_instance_on_repeat_call(monkeypatch):
    # Reset module-level singleton to make this test independent.
    monkeypatch.setattr(runner, "_RUNNER", None)
    r1 = get_runner()
    r2 = get_runner()
    assert r1 is r2
