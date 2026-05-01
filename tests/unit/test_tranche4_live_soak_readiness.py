"""Tests for the Tranche 4 live-soak readiness harness."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ops" / "tranche4_live_soak_readiness.py"

SPEC = importlib.util.spec_from_file_location("tranche4_live_soak_readiness", SCRIPT)
assert SPEC and SPEC.loader
readiness = importlib.util.module_from_spec(SPEC)
sys.modules["tranche4_live_soak_readiness"] = readiness
SPEC.loader.exec_module(readiness)


def _clear_tranche4_env(monkeypatch) -> None:
    for surface in readiness.SURFACES:
        for name in surface.live_flags + surface.bus_flags:
            monkeypatch.delenv(name, raising=False)
        for credential in surface.credentials:
            for name in credential.names:
                monkeypatch.delenv(name, raising=False)


def test_report_observes_safe_default_flags_without_secret_values(tmp_path, monkeypatch) -> None:
    _clear_tranche4_env(monkeypatch)
    secret_file = tmp_path / "secrets.env"
    secret_file.write_text("GEMINI_API_KEY=sk-super-secret-test-value\n", encoding="utf-8")

    report = readiness.build_report(
        root=tmp_path,
        secret_file=secret_file,
        include_service_status=False,
    )

    assert report["summary"]["safe_defaults_observed"] is True
    assert report["safety"]["external_writes_attempted"] is False
    assert all(row["claim"] == readiness.OBSERVED for row in report["live_flags"])
    narrative_key = next(
        row for row in report["credentials"] if row["label"] == "Gemini narrative key"
    )
    assert narrative_key["present"] is True
    serialized = json.dumps(report, sort_keys=True)
    assert "sk-super-secret-test-value" not in serialized


def test_artifact_presence_records_latest_sidecar(tmp_path, monkeypatch) -> None:
    _clear_tranche4_env(monkeypatch)
    latest = tmp_path / "data" / "narratives" / "2026-04-28" / "theses.jsonl"
    latest.parent.mkdir(parents=True)
    latest.write_text('{"generated_at":"2026-04-28T00:00:00Z"}\n', encoding="utf-8")
    Path(f"{latest}.envelope.json").write_text('{"ok":true}\n', encoding="utf-8")

    report = readiness.build_report(
        root=tmp_path,
        secret_file=tmp_path / "missing.env",
        include_service_status=False,
    )

    row = next(
        item
        for item in report["artifacts"]
        if item["surface"] == "narrative_synthesis" and item["kind"] == "theses_output"
    )
    assert row["claim"] == readiness.OBSERVED
    assert row["present"] is True
    assert row["count"] == 1
    assert row["latest"]["path"] == "data/narratives/2026-04-28/theses.jsonl"
    assert row["latest"]["envelope_present"] is True


def test_live_flag_enabled_blocks_dry_soak_state(tmp_path, monkeypatch) -> None:
    _clear_tranche4_env(monkeypatch)
    monkeypatch.setenv("SAPPHIRE_ONCHAIN_LIVE_BUS", "1")

    report = readiness.build_report(
        root=tmp_path,
        secret_file=tmp_path / "missing.env",
        include_service_status=False,
    )

    assert report["summary"]["safe_defaults_observed"] is False
    assert "SAPPHIRE_ONCHAIN_LIVE_BUS" in report["summary"]["enabled_live_flags"]
    onchain = next(row for row in report["readiness"] if row["surface"] == "onchain_intel")
    assert onchain["dry_soak_ready"] is False
    assert onchain["dry_soak_state"] == "blocked_live_flag_enabled"


def test_markdown_renderer_includes_claim_labels_and_unknowns(tmp_path, monkeypatch) -> None:
    _clear_tranche4_env(monkeypatch)
    report = readiness.build_report(
        root=tmp_path,
        secret_file=tmp_path / "missing.env",
        include_service_status=False,
    )

    rendered = readiness.render_markdown(report)

    assert "# Tranche 4 Live-Soak Readiness" in rendered
    assert "OBSERVED" in rendered
    assert "Harness writes attempted: `False`" in rendered
    assert "Event-bus publish attempted: `False`" in rendered
