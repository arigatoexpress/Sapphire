from __future__ import annotations

import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[2] / "plugins" / "claw-sapphire" / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import service_supervisor
from dev_pulse import ServiceStatus


def test_reason_ignores_stale_nonzero_exit_for_running_job() -> None:
    status = ServiceStatus(
        label="ai.hermes.gateway",
        loaded=True,
        pid=12345,
        exit_code=-15,
    )

    assert service_supervisor._reason_for(status) is None
    assert service_supervisor._is_healthy(status)


def test_reason_marks_nonrunning_nonzero_exit_as_crashed() -> None:
    status = ServiceStatus(
        label="ai.hermes.gateway",
        loaded=True,
        pid=None,
        exit_code=1,
    )

    assert service_supervisor._reason_for(status) == "crashed"
    assert not service_supervisor._is_healthy(status)


def test_supervisor_skips_running_jobs_with_stale_exit(monkeypatch) -> None:
    def fake_collect(labels: list[str]) -> list[ServiceStatus]:
        return [
            ServiceStatus(
                label=label,
                loaded=True,
                pid=1200 + index,
                exit_code=-15,
            )
            for index, label in enumerate(labels)
        ]

    monkeypatch.setattr(service_supervisor, "collect_service_statuses", fake_collect)

    summary = service_supervisor.supervise_once(
        labels=["ai.hermes.gateway", "com.sapphire.signal-logger"],
        dry_run=True,
    )

    assert summary["ok"] is True
    assert summary["attempted"] == []
    assert summary["failed"] == []
    assert summary["skipped_cooldown"] == []
    assert summary["errors"] == []
