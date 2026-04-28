"""Tests for the Tranche 5 live-soak readiness harness."""

from __future__ import annotations

import json
import os
from pathlib import Path

from scripts.ops import tranche5_live_soak_readiness as soak


def test_collect_readiness_inventories_tranche4_surfaces_without_running_commands(
    monkeypatch,
) -> None:
    for spec in soak.SURFACES:
        for flag in (*spec.live_flags, *spec.publish_flags):
            monkeypatch.delenv(flag, raising=False)

    report = soak.collect_readiness(run_status=False)

    surface_ids = {surface["id"] for surface in report["surfaces"]}
    assert {
        "narrative_synthesis",
        "macro_intel",
        "cross_asset",
        "onchain_intel",
        "counterparty_intel",
        "event_impact",
        "adversarial_defense",
    } <= surface_ids
    assert report["mode"] == "read-only-local"
    assert report["summary"]["status_commands_ran"] is False
    assert all(
        command["ran"] is False
        for surface in report["surfaces"]
        for command in surface["dry_run_status_commands"]
    )
    assert "No trading or order-execution paths are invoked." in report["guardrails"]


def test_status_commands_exclude_provider_or_rebuild_actions() -> None:
    commands = [
        " ".join(command.argv) + " " + json.dumps(command.stdin_json or {})
        for spec in soak.SURFACES
        for command in spec.status_commands
    ]

    assert not any("run-once" in command for command in commands)
    assert not any('"rebuild"' in command for command in commands)


def test_enabled_live_flags_warn_without_rendering_values(monkeypatch) -> None:
    monkeypatch.setenv("SAPPHIRE_NARRATIVE_LIVE", "true")
    monkeypatch.setenv("SAPPHIRE_NARRATIVE_LIVE_BUS", "secret-live-bus-value")

    report = soak.collect_readiness(run_status=False)
    serialized = json.dumps(report)
    narrative = next(surface for surface in report["surfaces"] if surface["id"] == "narrative_synthesis")

    assert report["status"] == "warn"
    assert narrative["status"] == "warn"
    assert "SAPPHIRE_NARRATIVE_LIVE" in narrative["enabled_live_or_publish_flags"]
    assert "secret-live-bus-value" not in serialized
    assert all("value" not in row for row in narrative["live_flags"])


def test_custom_surface_inventory_counts_cache_counters_and_latest_artifacts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    required = tmp_path / "service.py"
    required.write_text("# required\n", encoding="utf-8")
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    (cache_dir / "state.json").write_text("{}", encoding="utf-8")
    counters = tmp_path / "counters.json"
    counters.write_text('{"requests": 0}\n', encoding="utf-8")
    older = tmp_path / "artifacts" / "older.jsonl"
    newer = tmp_path / "artifacts" / "newer.jsonl"
    older.parent.mkdir()
    older.write_text('{"a": 1}\n', encoding="utf-8")
    newer.write_text('{"a": 1}\n{"b": 2}\n', encoding="utf-8")
    os.utime(older, (1_700_000_000, 1_700_000_000))
    os.utime(newer, (1_800_000_000, 1_800_000_000))
    surface = soak.SurfaceSpec(
        surface_id="fixture",
        label="Fixture Surface",
        kind="test",
        owners=("tests",),
        cache_dirs=(cache_dir,),
        counter_globs=(str(counters),),
        artifact_globs=(str(older.parent / "*.jsonl"),),
        required_files=(required,),
    )
    monkeypatch.setattr(soak, "SURFACES", (surface,))

    report = soak.collect_readiness(run_status=False)
    fixture = report["surfaces"][0]

    assert report["status"] == "pass"
    assert fixture["cache_dirs"][0]["file_count"] == 1
    assert fixture["counters"][0]["match_count"] == 1
    assert fixture["artifacts"][0]["match_count"] == 2
    assert fixture["artifacts"][0]["latest"][0]["path"] == str(newer)
    assert fixture["artifacts"][0]["latest"][0]["jsonl_rows"] == 2


def test_run_status_uses_injected_runner_and_redacts_secretish_output(
    tmp_path: Path,
    monkeypatch,
) -> None:
    required = tmp_path / "tool.py"
    required.write_text("# required\n", encoding="utf-8")
    surface = soak.SurfaceSpec(
        surface_id="fixture",
        label="Fixture Surface",
        kind="test",
        owners=("tests",),
        required_files=(required,),
        status_commands=(soak.CommandSpec("fixture status", ("fixture-tool", "status")),),
    )
    monkeypatch.setattr(soak, "SURFACES", (surface,))

    def runner(
        command: soak.CommandSpec,
        cwd: Path,
        timeout_seconds: float,
    ) -> dict[str, object]:
        assert command.label == "fixture status"
        assert cwd == soak.ROOT
        assert timeout_seconds == 2.0
        return {
            "label": command.label,
            "ran": True,
            "ok": True,
            "exit_code": 0,
            "stdout": "token=SHOULD_NOT_RENDER\nsk-abcdefghijklmnopqrstuvwxyz",
            "stderr": "api_key=ALSO_HIDDEN",
        }

    report = soak.collect_readiness(run_status=True, runner=runner, timeout_seconds=2.0)
    serialized = json.dumps(report)

    assert report["status"] == "pass"
    assert "SHOULD_NOT_RENDER" not in serialized
    assert "ALSO_HIDDEN" not in serialized
    assert "abcdefghijklmnopqrstuvwxyz" not in serialized
    command = report["surfaces"][0]["dry_run_status_commands"][0]
    assert command["ran"] is True
    assert command["result"]["ok"] is True


def test_render_markdown_includes_guardrails_and_safe_commands(tmp_path: Path, monkeypatch) -> None:
    required = tmp_path / "service.py"
    required.write_text("# required\n", encoding="utf-8")
    surface = soak.SurfaceSpec(
        surface_id="fixture",
        label="Fixture Surface",
        kind="test",
        owners=("tests",),
        required_files=(required,),
        status_commands=(soak.CommandSpec("fixture status", ("python3", "fixture.py")),),
    )
    monkeypatch.setattr(soak, "SURFACES", (surface,))

    markdown = soak.render_markdown(soak.collect_readiness(run_status=False))

    assert "# Tranche 5 Live-Soak Readiness" in markdown
    assert "No live API calls are made by this harness." in markdown
    assert "Fixture Surface" in markdown
    assert "fixture status" in markdown
