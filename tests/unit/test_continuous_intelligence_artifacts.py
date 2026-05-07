from __future__ import annotations

import json

import pytest

from lib.autonomy import continuous_intelligence_artifacts as artifacts
from lib.autonomy.continuous_intelligence import build_continuous_intelligence_plan


def test_snapshot_preview_does_not_write(tmp_path) -> None:
    plan = build_continuous_intelligence_plan(fetch_live=False)

    preview = artifacts.snapshot_tasks(plan, artifact_dir=tmp_path, write=False)

    assert preview["mode"] == "local_artifact_snapshot"
    assert preview["write_enabled"] is False
    assert preview["writes_by_default"] is False
    assert preview["records"] == plan["totals"]["tasks"]
    assert not (tmp_path / artifacts.TASK_SNAPSHOT_FILE).exists()


def test_snapshot_write_materializes_jsonl_without_execution(tmp_path) -> None:
    plan = build_continuous_intelligence_plan(fetch_live=False)

    written = artifacts.snapshot_tasks(plan, artifact_dir=tmp_path, write=True)

    target = tmp_path / artifacts.TASK_SNAPSHOT_FILE
    rows = [json.loads(line) for line in target.read_text().splitlines()]
    assert written["write_enabled"] is True
    assert len(rows) == plan["totals"]["tasks"]
    assert rows[0]["record_type"] == "continuous_intelligence_task_snapshot"
    assert rows[0]["safety"]["execution_enabled"] is False
    assert rows[0]["safety"]["telegram_sends_enabled"] is False


def test_lease_preview_filters_for_windows_without_writing(tmp_path) -> None:
    plan = build_continuous_intelligence_plan(fetch_live=False)

    lease = artifacts.lease_tasks(
        plan,
        agent_id="windows-gpu",
        target_runtime="windows-gpu",
        capabilities=["reason"],
        artifact_dir=tmp_path,
        write=False,
        limit=2,
    )

    assert lease["mode"] == "dry_run_task_lease"
    assert lease["write_enabled"] is False
    assert lease["leased_count"] >= 1
    assert all(row["target_runtime"] == "windows-gpu" for row in lease["leases"])
    assert all(row["safety"]["dry_run_dispatch_only"] is True for row in lease["leases"])
    assert not (tmp_path / artifacts.LEASE_FILE).exists()


def test_lease_preview_pauses_windows_when_primary_offline(tmp_path) -> None:
    plan = build_continuous_intelligence_plan(fetch_live=False)

    lease = artifacts.lease_tasks(
        plan,
        agent_id="windows-gpu",
        target_runtime="windows-gpu",
        capabilities=["reason"],
        runtime_status={
            "mode": "local_failover",
            "active_route": "mac-local",
            "windows_offline": True,
            "fallback_ready": True,
        },
        artifact_dir=tmp_path,
        write=False,
        limit=2,
    )

    assert lease["mode"] == "dry_run_task_lease"
    assert lease["candidate_count"] >= 1
    assert lease["leased_count"] == 0
    assert lease["blocked_by_runtime"] == lease["candidate_count"]
    assert lease["runtime_guard"]["status"] == "blocked"
    assert lease["runtime_guard"]["reason"] == "windows_gpu_primary_unavailable"
    assert lease["runtime_guard"]["active_route"] == "mac-local"
    assert not (tmp_path / artifacts.LEASE_FILE).exists()


def test_lease_write_materializes_jsonl(tmp_path) -> None:
    plan = build_continuous_intelligence_plan(fetch_live=False)

    lease = artifacts.lease_tasks(
        plan,
        agent_id="mac-local",
        target_runtime="mac-local",
        artifact_dir=tmp_path,
        write=True,
        limit=1,
    )

    rows = [json.loads(line) for line in (tmp_path / artifacts.LEASE_FILE).read_text().splitlines()]
    assert lease["write_enabled"] is True
    assert len(rows) == 1
    assert rows[0]["agent_id"] == "mac-local"
    assert rows[0]["safety"]["execution_enabled"] is False


def test_record_task_result_rejects_sensitive_keys(tmp_path) -> None:
    with pytest.raises(ValueError, match="sensitive result key"):
        artifacts.record_task_result(
            task_id="demo",
            agent_id="windows-gpu",
            status="completed",
            result={"api_key": "do-not-store"},
            artifact_dir=tmp_path,
            write=True,
        )

    assert not (tmp_path / artifacts.RESULT_FILE).exists()


def test_record_task_result_write_is_opt_in(tmp_path) -> None:
    preview = artifacts.record_task_result(
        task_id="demo",
        agent_id="windows-gpu",
        status="needs_review",
        result={"summary": "claim needs more primary-source evidence"},
        artifact_dir=tmp_path,
        write=False,
    )
    assert preview["write_enabled"] is False
    assert preview["record"]["safety"]["operator_review_required"] is True
    assert not (tmp_path / artifacts.RESULT_FILE).exists()

    written = artifacts.record_task_result(
        task_id="demo",
        agent_id="windows-gpu",
        status="blocked",
        result={"reason": "missing source"},
        artifact_dir=tmp_path,
        write=True,
    )
    rows = [
        json.loads(line) for line in (tmp_path / artifacts.RESULT_FILE).read_text().splitlines()
    ]
    assert written["write_enabled"] is True
    assert rows[0]["status"] == "blocked"


def test_artifact_status_is_read_only(tmp_path) -> None:
    status = artifacts.artifact_status(artifact_dir=tmp_path)

    assert status["mode"] == "continuous_intelligence_artifact_status"
    assert status["writes_by_default"] is False
    assert status["execution_enabled"] is False
    assert status["totals"] == {
        "task_snapshots": 0,
        "task_leases": 0,
        "task_results": 0,
        "daily_packets": 0,
    }
    assert status["files"]["daily_packet_latest"]["exists"] is False


def test_cli_preview_commands_do_not_write(capsys, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(artifacts, "DEFAULT_ARTIFACT_DIR", tmp_path)

    assert artifacts.cli(["snapshot", "--pretty"]) == 0
    snapshot = json.loads(capsys.readouterr().out)
    assert snapshot["write_enabled"] is False
    assert snapshot["records"] >= 10

    assert (
        artifacts.cli(
            [
                "lease",
                "--agent-id",
                "windows-gpu",
                "--target-runtime",
                "windows-gpu",
                "--capability",
                "reason",
                "--pretty",
            ]
        )
        == 0
    )
    lease = json.loads(capsys.readouterr().out)
    assert lease["write_enabled"] is False
    assert lease["safety"]["dry_run_dispatch_only"] is True

    assert not (tmp_path / artifacts.TASK_SNAPSHOT_FILE).exists()
    assert not (tmp_path / artifacts.LEASE_FILE).exists()


def test_daily_autonomy_packet_preview_does_not_write(tmp_path) -> None:
    plan = build_continuous_intelligence_plan(fetch_live=False)

    packet = artifacts.daily_autonomy_packet(
        plan,
        artifact_dir=tmp_path,
        lease_targets=["mac-local"],
        limit_per_target=1,
        write=False,
    )

    assert packet["mode"] == "daily_autonomy_packet"
    assert packet["write_enabled"] is False
    assert packet["totals"]["tasks"] == plan["totals"]["tasks"]
    assert packet["totals"]["leased"] >= 1
    assert packet["safety"]["execution_enabled"] is False
    assert packet["safety"]["telegram_sends_enabled"] is False
    assert not (tmp_path / artifacts.DAILY_PACKET_FILE).exists()
    assert not (tmp_path / artifacts.DAILY_PACKET_LATEST_FILE).exists()


def test_daily_autonomy_packet_write_appends_ledgers_and_latest(tmp_path) -> None:
    plan = build_continuous_intelligence_plan(fetch_live=False)

    packet = artifacts.daily_autonomy_packet(
        plan,
        artifact_dir=tmp_path,
        lease_targets=["mac-local"],
        limit_per_target=1,
        write=True,
    )

    assert packet["write_enabled"] is True
    assert (tmp_path / artifacts.TASK_SNAPSHOT_FILE).exists()
    assert (tmp_path / artifacts.LEASE_FILE).exists()
    packet_rows = [
        json.loads(line)
        for line in (tmp_path / artifacts.DAILY_PACKET_FILE).read_text().splitlines()
    ]
    latest = json.loads((tmp_path / artifacts.DAILY_PACKET_LATEST_FILE).read_text())
    assert len(packet_rows) == 1
    assert packet_rows[0]["record_type"] == "continuous_intelligence_daily_autonomy_packet"
    assert latest["packet_id"] == packet["packet_id"]
    assert packet["artifact_status"]["totals"]["daily_packets"] == 1
