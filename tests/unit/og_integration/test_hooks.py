"""Tests for lib.og.hooks — fire-and-forget signal_logger hook.

Critical safety property: hooks NEVER block, NEVER raise into the caller,
and do NOTHING when the feature flag is unset.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lib.og import hooks


@pytest.fixture
def og_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(hooks.ENV_FLAG, "1")
    monkeypatch.setenv(hooks.ENV_PRIVATE_KEY, "0x" + "22" * 32)


@pytest.fixture
def og_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(hooks.ENV_FLAG, raising=False)


class TestNoOpWhenDisabled:
    def test_no_subprocess_when_flag_unset(
        self, og_disabled: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        with patch("subprocess.Popen") as popen:
            hooks.publish_signal_async({"symbol": "BTC", "action": "buy"})
        assert popen.call_count == 0

    def test_no_subprocess_when_flag_other_value(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(hooks.ENV_FLAG, "true")
        with patch("subprocess.Popen") as popen:
            hooks.publish_signal_async({"symbol": "BTC", "action": "buy"})
        assert popen.call_count == 0


class TestFiresWhenEnabled:
    def test_subprocess_spawned_with_payload(self, og_enabled: None) -> None:
        proc = MagicMock()
        proc.stdin = MagicMock()
        with patch("subprocess.Popen", return_value=proc) as popen:
            hooks.publish_signal_async(
                {
                    "strategy": "rsi_cross",
                    "symbol": "BTC",
                    "action": "buy",
                    "score": 75,
                    "price": 65000,
                }
            )
        assert popen.call_count == 1
        # Was the payload pushed into stdin?
        assert proc.stdin.write.call_count == 1
        payload_str = proc.stdin.write.call_args[0][0]
        import json

        payload = json.loads(payload_str)
        assert payload["strategy"] == "rsi_cross"
        assert payload["symbol"] == "BTC"
        assert payload["action"] == "buy"
        assert payload["signal"]["price"] == 65000

    def test_explicit_overrides_used(self, og_enabled: None) -> None:
        proc = MagicMock()
        proc.stdin = MagicMock()
        with patch("subprocess.Popen", return_value=proc):
            hooks.publish_signal_async(
                {"strategy": "auto_inferred", "symbol": "DEFAULT"},
                strategy="explicit_strategy",
                symbol="EXPLICIT",
            )
        import json

        payload = json.loads(proc.stdin.write.call_args[0][0])
        assert payload["strategy"] == "explicit_strategy"
        assert payload["symbol"] == "EXPLICIT"

    def test_skips_when_no_private_key(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv(hooks.ENV_FLAG, "1")
        monkeypatch.delenv(hooks.ENV_PRIVATE_KEY, raising=False)
        # Redirect events file to tmp so we don't pollute repo
        monkeypatch.setattr(hooks, "EVENTS_PATH", tmp_path / "events.jsonl")
        with patch("subprocess.Popen") as popen:
            hooks.publish_signal_async({"symbol": "BTC"})
        assert popen.call_count == 0
        # And we should have logged the skip reason for ops visibility
        events_file = tmp_path / "events.jsonl"
        assert events_file.exists()
        assert "no_private_key" in events_file.read_text(encoding="utf-8")


class TestSafetyProperties:
    """Hooks must never raise into the caller. Trading critical path safety."""

    def test_subprocess_failure_does_not_raise(
        self, og_enabled: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(hooks, "EVENTS_PATH", tmp_path / "events.jsonl")
        with patch("subprocess.Popen", side_effect=OSError("fork failed")):
            # No exception should escape
            hooks.publish_signal_async({"symbol": "BTC", "action": "buy"})
        # Failure was recorded for the operator
        events_file = tmp_path / "events.jsonl"
        assert events_file.exists()
        assert "spawn_error" in events_file.read_text(encoding="utf-8")

    def test_missing_tool_does_not_raise(
        self, og_enabled: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(hooks, "PUBLISH_TOOL", tmp_path / "nonexistent.py")
        monkeypatch.setattr(hooks, "EVENTS_PATH", tmp_path / "events.jsonl")
        with patch("subprocess.Popen") as popen:
            hooks.publish_signal_async({"symbol": "BTC"})
        assert popen.call_count == 0
        assert "tool_missing" in (tmp_path / "events.jsonl").read_text(encoding="utf-8")
