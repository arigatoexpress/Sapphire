"""Tests for the Sapphire LaunchAgent service supervisor."""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import service_supervisor  # type: ignore


class FakeRun:
    def __init__(self, rc: int = 0, stdout: str = "", stderr: str = ""):
        self.calls: list[list[str]] = []
        self.rc = rc
        self.stdout = stdout
        self.stderr = stderr

    def __call__(self, cmd, timeout=20):
        self.calls.append(list(cmd))
        return self.rc, self.stdout, self.stderr


class FakeDocument:
    def __init__(self, store: dict[str, dict], doc_id: str):
        self.store = store
        self.doc_id = doc_id

    def set(self, payload: dict) -> None:
        self.store[self.doc_id] = dict(payload)


class FakeCollection:
    def __init__(self, store: dict[str, dict]):
        self.store = store

    def document(self, doc_id: str) -> FakeDocument:
        return FakeDocument(self.store, doc_id)


class FakeDB:
    def __init__(self):
        self.collections: dict[str, dict[str, dict]] = defaultdict(dict)

    def collection(self, name: str) -> FakeCollection:
        return FakeCollection(self.collections[name])


def status(label: str, *, loaded: bool = True, exit_code: int | None = 0, pid: int | None = 123):
    return service_supervisor.ServiceStatus(
        label=label, loaded=loaded, pid=pid, exit_code=exit_code
    )


@pytest.fixture
def supervisor_env(monkeypatch, tmp_path):
    state_file = tmp_path / "state.json"
    monkeypatch.setattr(service_supervisor, "STATE_FILE", state_file)
    monkeypatch.setattr(service_supervisor.os, "getuid", lambda: 501)
    monkeypatch.setattr(service_supervisor, "_get_firestore_db", lambda: None)
    monkeypatch.setattr(service_supervisor, "send_alert", lambda *args, **kwargs: {"ok": True})
    return state_file


def install_status_sequence(monkeypatch, sequence):
    calls = {"count": 0}

    def fake_collect(labels):
        index = min(calls["count"], len(sequence) - 1)
        calls["count"] += 1
        current = sequence[index]
        if isinstance(current, dict):
            return [current[label] for label in labels]
        return current

    monkeypatch.setattr(service_supervisor, "collect_service_statuses", fake_collect)
    return calls


def test_no_action_when_everything_healthy(monkeypatch, supervisor_env):
    label = "com.sapphire.pm-bot"
    fake_run = FakeRun()
    monkeypatch.setattr(service_supervisor, "_run", fake_run)
    install_status_sequence(monkeypatch, [{label: status(label)}])

    result = service_supervisor.supervise_once(labels=[label])

    assert result["ok"] is True
    assert result["attempted"] == []
    assert result["recovered"] == []
    assert fake_run.calls == []


def test_restart_triggered_on_nonzero_exit_code(monkeypatch, supervisor_env):
    label = "ai.hermes.gateway"
    fake_run = FakeRun()
    monkeypatch.setattr(service_supervisor, "_run", fake_run)
    install_status_sequence(
        monkeypatch,
        [
            {label: status(label, exit_code=1, pid=None)},
            [status(label, exit_code=0)],
        ],
    )

    result = service_supervisor.supervise_once(labels=[label])

    assert result["ok"] is True
    assert result["attempted"][0]["restart_action"] == "kickstart"
    assert result["recovered"][0]["label"] == label
    assert fake_run.calls == [["launchctl", "kickstart", "-k", "gui/501/ai.hermes.gateway"]]


def test_restart_triggered_on_unloaded_expected_service(monkeypatch, supervisor_env):
    label = "com.sapphire.pm-bot"
    fake_run = FakeRun()
    monkeypatch.setattr(service_supervisor, "_run", fake_run)
    install_status_sequence(
        monkeypatch,
        [
            {label: status(label, loaded=False, exit_code=None, pid=None)},
            [status(label, loaded=True, exit_code=0)],
        ],
    )

    result = service_supervisor.supervise_once(labels=[label])

    assert result["ok"] is True
    assert result["attempted"][0]["restart_action"] == "bootstrap"
    assert fake_run.calls[0][:3] == ["launchctl", "bootstrap", "gui/501"]
    assert fake_run.calls[0][3].endswith("Library/LaunchAgents/com.sapphire.pm-bot.plist")


def test_cooldown_blocks_consecutive_restarts(monkeypatch, supervisor_env):
    label = "ai.hermes.gateway"
    fake_run = FakeRun()
    now = datetime(2026, 4, 24, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(service_supervisor, "_run", fake_run)
    monkeypatch.setattr(service_supervisor, "_now", lambda: now)
    install_status_sequence(
        monkeypatch,
        [
            {label: status(label, exit_code=1, pid=None)},
            [status(label, exit_code=0)],
        ],
    )
    first = service_supervisor.supervise_once(labels=[label])
    assert first["recovered"]

    install_status_sequence(monkeypatch, [{label: status(label, exit_code=1, pid=None)}])
    second = service_supervisor.supervise_once(labels=[label])

    assert second["attempted"] == []
    assert second["skipped_cooldown"][0]["skip_reason"] == "restart_cooldown"
    assert len(fake_run.calls) == 1


def test_global_rate_limit_blocks_when_too_many_in_hour(monkeypatch, supervisor_env):
    label = "ai.hermes.gateway"
    fake_run = FakeRun()
    now = datetime(2026, 4, 24, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(service_supervisor, "_run", fake_run)
    monkeypatch.setattr(service_supervisor, "_now", lambda: now)
    state = {
        "labels": {},
        "seen_event_categories": [],
        "restart_attempts": [
            {"label": "a", "timestamp": (now - timedelta(minutes=i)).isoformat()} for i in range(4)
        ],
    }
    supervisor_env.parent.mkdir(parents=True, exist_ok=True)
    supervisor_env.write_text(json.dumps(state))
    install_status_sequence(monkeypatch, [{label: status(label, exit_code=1, pid=None)}])

    result = service_supervisor.supervise_once(labels=[label], max_restarts_per_hour=4)

    assert result["ok"] is False
    assert result["skipped_cooldown"][0]["skip_reason"] == "rate_limited"
    assert "rate_limited" in result["errors"][0]
    assert fake_run.calls == []


def test_failed_restart_escalates_to_notify(monkeypatch, supervisor_env):
    label = "ai.hermes.gateway"
    alerts: list[tuple[str, str]] = []
    monkeypatch.setattr(service_supervisor, "_run", FakeRun())
    monkeypatch.setattr(
        service_supervisor,
        "send_alert",
        lambda message, priority="p1": alerts.append((message, priority)),
    )
    install_status_sequence(
        monkeypatch,
        [
            {label: status(label, exit_code=1, pid=None)},
            [status(label, exit_code=1, pid=None)],
        ],
    )

    result = service_supervisor.supervise_once(labels=[label])

    assert result["ok"] is False
    assert result["failed"][0]["label"] == label
    assert len(alerts) == 1
    assert alerts[0][1] == "p0"


def test_recovered_restart_does_not_notify(monkeypatch, supervisor_env):
    label = "ai.hermes.gateway"
    alerts: list[tuple[str, str]] = []
    monkeypatch.setattr(service_supervisor, "_run", FakeRun())
    monkeypatch.setattr(
        service_supervisor,
        "send_alert",
        lambda message, priority="p1": alerts.append((message, priority)),
    )
    install_status_sequence(
        monkeypatch,
        [
            {label: status(label, exit_code=1, pid=None)},
            [status(label, exit_code=0)],
        ],
    )

    result = service_supervisor.supervise_once(labels=[label])

    assert result["ok"] is True
    assert result["recovered"]
    assert alerts == []


def test_recovery_detected_via_pid_change_when_exit_code_stale(monkeypatch, supervisor_env):
    """launchctl's LastExitStatus persists after a successful kickstart — so a
    recovered service can still read exit_code=1. Use the PID change (new
    process replaced the old one) as the authoritative recovery signal.
    """
    label = "ai.hermes.gateway"
    alerts: list[tuple[str, str]] = []
    monkeypatch.setattr(service_supervisor, "_run", FakeRun())
    monkeypatch.setattr(
        service_supervisor,
        "send_alert",
        lambda message, priority="p1": alerts.append((message, priority)),
    )
    # Before restart: crashed, exit_code=1, no running pid.
    # After restart:  loaded, exit_code STILL 1 (stale), pid=200 (new process)
    install_status_sequence(
        monkeypatch,
        [
            {label: status(label, exit_code=1, pid=None)},
            [status(label, exit_code=1, pid=200)],  # PID changed → actually restarted
        ],
    )

    result = service_supervisor.supervise_once(labels=[label])

    assert result["ok"] is True, f"expected recovery, got: {result}"
    assert result["recovered"], "PID change should register as recovered"
    assert not result["failed"], "should not escalate when PID proves restart succeeded"
    assert alerts == [], "Telegram should stay silent on successful restart"

    payload = result["recovered"][0]
    assert payload["pid_before"] is None
    assert payload["pid_after"] == 200


def test_activity_written_to_firestore_on_every_action(monkeypatch, supervisor_env):
    label = "ai.hermes.gateway"
    db = FakeDB()
    monkeypatch.setattr(service_supervisor, "_get_firestore_db", lambda: db)
    monkeypatch.setattr(service_supervisor, "_run", FakeRun())
    install_status_sequence(
        monkeypatch,
        [
            {label: status(label, exit_code=1, pid=None)},
            [status(label, exit_code=0)],
        ],
    )

    result = service_supervisor.supervise_once(labels=[label])

    assert result["ok"] is True
    activities = list(db.collections["activities"].values())
    activity_types = {item["activity_type"] for item in activities}
    assert activity_types == {
        "service_supervisor.attempted",
        "service_supervisor.recovered",
    }
    assert all(item["metadata"]["label"] == label for item in activities)


def test_dry_run_never_calls_restart(monkeypatch, supervisor_env):
    label = "ai.hermes.gateway"
    fake_run = FakeRun()
    monkeypatch.setattr(service_supervisor, "_run", fake_run)
    install_status_sequence(monkeypatch, [{label: status(label, exit_code=1, pid=None)}])

    result = service_supervisor.supervise_once(labels=[label], dry_run=True)

    assert result["ok"] is True
    assert result["attempted"][0]["dry_run"] is True
    assert result["attempted"][0]["restart_action"] == "kickstart"
    assert fake_run.calls == []
    assert not supervisor_env.exists()


def test_state_file_round_trip(monkeypatch, supervisor_env):
    payload = {
        "labels": {"ai.hermes.gateway": {"last_attempt_at": "2026-04-24T12:00:00+00:00"}},
        "restart_attempts": [
            {"label": "ai.hermes.gateway", "timestamp": "2026-04-24T12:00:00+00:00"}
        ],
        "seen_event_categories": ["ai.hermes.gateway:crashed"],
    }

    service_supervisor._save_state(payload)
    loaded = service_supervisor._load_state()

    assert loaded == payload
