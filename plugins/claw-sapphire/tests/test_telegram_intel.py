"""Tests for the Telegram intel plugin stdin JSON contract."""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.telegram_intel.models import ChannelConfig, ClassificationResult, RawMessage
from services.telegram_intel.quality_filter import quality_filter
from services.telegram_intel.sink import TelegramIntelSink, build_record

INTERNAL = ROOT / "plugins" / "claw-sapphire" / "tools" / "internal" / "telegram_intel.py"

_spec = importlib.util.spec_from_file_location("telegram_intel_internal", INTERNAL)
assert _spec is not None and _spec.loader is not None
telegram_intel = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = telegram_intel
_spec.loader.exec_module(telegram_intel)


def _write_config(path: Path) -> Path:
    path.write_text(
        """
defaults:
  max_messages_per_poll: 5
  poll_interval_seconds: 60
  min_quality_score: 0.45
  min_message_length: 32
channels:
  - id: "@security_feed"
    category: security
    weight: 1.0
    enabled: true
    backend: mtproto
    notes: test channel
""",
        encoding="utf-8",
    )
    return path


def _seed_record(data_dir: Path) -> None:
    channel = ChannelConfig(id="@security_feed", source="@security_feed", category="security")
    message = RawMessage(
        channel_id="security",
        message_id="1",
        text="CVE-2026-7777 exploit confirmed with patch guidance.",
        published_at="2026-04-28T12:00:00+00:00",
    )
    quality = quality_filter(message.text, channel_id=channel.id)
    classification = ClassificationResult(label="security", confidence=0.9)
    TelegramIntelSink(data_dir).write_records(
        [build_record(message, channel, quality, classification)]
    )


def test_status_action_returns_gate(tmp_path: Path) -> None:
    out = telegram_intel.handle(
        {
            "action": "status",
            "config_path": str(tmp_path / "missing.yaml"),
            "data_dir": str(tmp_path / "data"),
            "counter_path": str(tmp_path / "counters.json"),
        }
    )
    assert out["ok"] is True
    assert out["service"] == "telegram_intel"
    assert "gate" in out


def test_models_action_lists_balanced_classifier() -> None:
    out = telegram_intel.handle({"action": "models"})
    assert out["ok"] is True
    assert out["models"]["default"] == "balanced"


def test_quality_test_action_sanitizes_text() -> None:
    out = telegram_intel.handle(
        {
            "action": "quality-test",
            "text": "CVE-2026-8888 patch at https://example.com contact ari@example.com.",
        }
    )
    assert out["ok"] is True
    assert "hxxps://example.com" in out["sanitized_text"]
    assert "ari@example.com" not in out["sanitized_text"]


def test_recent_action_reads_sink(tmp_path: Path) -> None:
    _seed_record(tmp_path / "data")
    out = telegram_intel.handle(
        {"action": "recent", "data_dir": str(tmp_path / "data"), "limit": 1}
    )
    assert out["ok"] is True
    assert out["records"][0]["channel"]["id"] == "@security_feed"


def test_pull_once_refuses_without_live_gate(tmp_path: Path) -> None:
    out = telegram_intel.handle(
        {
            "action": "pull-once",
            "config_path": str(_write_config(tmp_path / "channels.yaml")),
            "data_dir": str(tmp_path / "data"),
            "counter_path": str(tmp_path / "counters.json"),
        }
    )
    assert out["ok"] is False
    assert out["error"] == "live gate refused"


def test_unknown_action_lists_known_actions() -> None:
    out = telegram_intel.handle({"action": "bogus"})
    assert out["ok"] is False
    assert "quality-test" in out["known_actions"]


def test_main_rejects_invalid_json() -> None:
    stdout = io.StringIO()
    rc = telegram_intel.main(io.StringIO("not json"), stdout)
    assert rc == 2
    assert json.loads(stdout.getvalue())["error"] == "invalid JSON input"


def test_main_rejects_non_object_payload() -> None:
    stdout = io.StringIO()
    rc = telegram_intel.main(io.StringIO("[1,2,3]"), stdout)
    assert rc == 2
    assert json.loads(stdout.getvalue())["error"] == "input must be a JSON object"


def test_main_defaults_to_status(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(ROOT)
    stdout = io.StringIO()
    rc = telegram_intel.main(io.StringIO(""), stdout)
    parsed = json.loads(stdout.getvalue())
    assert rc == 0
    assert parsed["service"] == "telegram_intel"


def test_main_quality_test_success() -> None:
    stdout = io.StringIO()
    rc = telegram_intel.main(
        io.StringIO(json.dumps({"action": "quality-test", "text": "CVE patch released."})),
        stdout,
    )
    assert rc == 0
    assert json.loads(stdout.getvalue())["ok"] is True
