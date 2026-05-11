"""Tests for the PM bot webhook readiness planner."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.ops import pm_bot_webhook_readiness as readiness  # noqa: E402


def test_build_webhook_readiness_report_is_secret_safe() -> None:
    report = readiness.build_webhook_readiness_report(
        url="https://example.invalid/telegram/webhook",
        secret_token_configured=True,
        drop_pending_updates=True,
    )

    encoded = json.dumps(report)
    assert report["status"] == "dry_run"
    assert report["plan"]["secret_token_configured"] is True
    assert report["plan"]["drop_pending_updates"] is True
    assert "secret-token" not in encoded
    assert "secret_token" not in report["plan"]
    assert report["safety"]["sends_telegram_messages"] is False


def test_build_webhook_readiness_report_blocks_missing_url() -> None:
    report = readiness.build_webhook_readiness_report(
        url="",
        secret_token_configured=False,
    )

    assert report["status"] == "blocked"
    assert "missing_webhook_url" in report["blockers"]


def test_main_blocks_apply_without_explicit_env_gate(monkeypatch, capsys) -> None:
    monkeypatch.delenv(readiness.APPLY_ENV, raising=False)

    rc = readiness.main(
        [
            "--url",
            "https://example.invalid/telegram/webhook",
            "--apply",
            "--json",
        ]
    )

    captured = capsys.readouterr().out
    payload = json.loads(captured)
    assert rc == 2
    assert payload["status"] == "blocked"
    assert f"{readiness.APPLY_ENV}_not_enabled" in payload["blockers"]
    assert payload["safety"]["calls_telegram"] is False
