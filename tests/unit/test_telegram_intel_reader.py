from __future__ import annotations

import json
import sys
import time
import types
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from services.telegram_intel.backends import (
    BackendError,
    BotAPIBackend,
    MTProtoBackend,
    _matches_channel,
)
from services.telegram_intel.config import DEFAULT_CONFIG_PATH, ConfigError, load_config
from services.telegram_intel.models import (
    MAX_CHANNELS,
    ChannelConfig,
    ClassificationResult,
    RawMessage,
)
from services.telegram_intel.run import evaluate_live_gate, pull_once, status


def _write_config(
    path: Path,
    *,
    enabled: bool = True,
    backend: str = "mtproto",
    channels: int = 1,
    classifier: bool = False,
    weight: float = 1.0,
    source: bool = False,
) -> Path:
    rows = []
    for index in range(channels):
        row = {
            "id": f"chan-{index}",
            "category": "security",
            "weight": weight,
            "enabled": enabled,
            "backend": backend,
            "notes": "test channel",
        }
        if source:
            row["source"] = f"@channel_{index}"
        rows.append(row)
    path.write_text(
        json.dumps(
            {
                "defaults": {
                    "max_messages_per_poll": 5,
                    "poll_interval_seconds": 60,
                    "min_quality_score": 0.45,
                    "min_message_length": 32,
                },
                "classifier": {"enabled": classifier, "model": "balanced"},
                "channels": rows,
            }
        ),
        encoding="utf-8",
    )
    return path


class FakeBackend:
    def __init__(self, messages: list[RawMessage] | None = None) -> None:
        self.messages = messages or [
            RawMessage(
                channel_id="chan-0",
                message_id="101",
                text=(
                    "CVE-2026-0001 is being exploited in cloud edge devices; "
                    "operators should monitor hxxp indicators and patch quickly."
                ),
                published_at="2026-04-28T12:00:00+00:00",
            )
        ]
        self.calls: list[tuple[str, int]] = []

    def pull_channel(
        self,
        channel: ChannelConfig,
        *,
        limit: int,
        since_id: str | None = None,
    ) -> list[RawMessage]:
        self.calls.append((channel.id, limit))
        return [message for message in self.messages if message.channel_id == channel.id][:limit]


class FakeClassifier:
    enabled = True

    def classify(self, text: str, *, channel_id: str | None = None) -> ClassificationResult:
        return ClassificationResult(
            label="security",
            confidence=0.91,
            topics=("security",),
            model="balanced",
            source="local-inference-proxy",
            rationale="test classifier",
        )


def test_load_config_parses_enabled_channel(tmp_path: Path) -> None:
    cfg = load_config(_write_config(tmp_path / "channels.yaml"))
    assert len(cfg.enabled_channels) == 1
    assert cfg.enabled_channels[0].backend == "mtproto"
    assert cfg.enabled_channels[0].source == "chan-0"
    assert cfg.enabled_channels[0].category == "security"
    assert cfg.enabled_channels[0].weight == 1.0
    assert cfg.max_messages_per_poll == 5


def test_default_config_path_is_user_sapphire_dir() -> None:
    assert DEFAULT_CONFIG_PATH == Path.home() / ".sapphire" / "telegram_channels.yaml"


def test_load_config_rejects_duplicate_channel_ids(tmp_path: Path) -> None:
    path = tmp_path / "channels.yaml"
    path.write_text(
        """
channels:
  - id: dup
    category: security
  - id: dup
    category: security
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="duplicate"):
        load_config(path)


def test_load_config_rejects_unsupported_backend(tmp_path: Path) -> None:
    path = tmp_path / "channels.yaml"
    path.write_text(
        """
channels:
  - id: a
    category: security
    backend: rss
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="unsupported backend"):
        load_config(path)


def test_load_config_rejects_unsupported_category(tmp_path: Path) -> None:
    path = tmp_path / "channels.yaml"
    path.write_text(
        """
channels:
  - id: a
    category: sports
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="unsupported category"):
        load_config(path)


def test_load_config_supports_backward_compatible_aliases(tmp_path: Path) -> None:
    path = tmp_path / "channels.yaml"
    path.write_text(
        """
defaults:
  pull_limit_per_channel: 7
  min_quality: 0.4
channels:
  - id: alias-channel
    source: "@alias_source"
    backend: botapi
    topics: [security]
    min_quality: 0.35
""",
        encoding="utf-8",
    )
    cfg = load_config(path)
    channel = cfg.enabled_channels[0]
    assert cfg.max_messages_per_poll == 7
    assert cfg.pull_limit_per_channel == 7
    assert channel.source == "@alias_source"
    assert channel.backend == "bot"
    assert channel.category == "security"
    assert channel.min_quality_score == 0.35


def test_load_config_enforces_channel_cap(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="cap exceeded"):
        load_config(_write_config(tmp_path / "channels.yaml", channels=MAX_CHANNELS + 1))


def test_live_gate_refuses_without_env_session_and_config(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("SAPPHIRE_TELEGRAM_INTEL_LIVE", raising=False)
    gate = evaluate_live_gate(
        config_path=_write_config(tmp_path / "channels.yaml"),
        session_path=tmp_path / "missing.session",
    )
    assert gate.allowed is False
    assert "SAPPHIRE_TELEGRAM_INTEL_LIVE != 1" in gate.reasons
    assert any("session missing" in reason for reason in gate.reasons)


def test_live_gate_accepts_explicit_env_session_and_enabled_config(
    tmp_path: Path, monkeypatch
) -> None:
    session = tmp_path / "telegram_intel.session"
    session.write_text("session", encoding="utf-8")
    monkeypatch.setenv("SAPPHIRE_TELEGRAM_INTEL_LIVE", "1")
    gate = evaluate_live_gate(
        config_path=_write_config(tmp_path / "channels.yaml"),
        session_path=session,
    )
    assert gate.allowed is True
    assert gate.enabled_channels == 1


def test_pull_once_with_fake_backend_writes_record(tmp_path: Path) -> None:
    cfg_path = _write_config(tmp_path / "channels.yaml")
    backend = FakeBackend()
    result = pull_once(
        config_path=cfg_path,
        data_dir=tmp_path / "data",
        counter_path=tmp_path / "counters.json",
        backend_factory=lambda name: backend,
        classifier=FakeClassifier(),
        require_live_gate=False,
        source_paths=(cfg_path,),
    )
    assert result["ok"] is True
    assert result["stats"]["written_messages"] == 1
    assert backend.calls == [("chan-0", 5)]


def test_pull_once_filters_low_quality_messages(tmp_path: Path) -> None:
    cfg_path = _write_config(tmp_path / "channels.yaml")
    backend = FakeBackend(
        [
            RawMessage(
                channel_id="chan-0",
                message_id="1",
                text="gm",
                published_at="2026-04-28T12:00:00+00:00",
            )
        ]
    )
    result = pull_once(
        config_path=cfg_path,
        data_dir=tmp_path / "data",
        counter_path=tmp_path / "counters.json",
        backend_factory=lambda name: backend,
        require_live_gate=False,
    )
    assert result["stats"]["low_quality_messages"] == 1
    assert result["stats"]["written_messages"] == 0


def test_pull_once_applies_channel_weight_to_quality_score(tmp_path: Path) -> None:
    message = RawMessage(
        channel_id="chan-0",
        message_id="weight-1",
        text="Treasury yield curve steepened as inflation swaps repriced.",
        published_at="2026-04-28T12:00:00+00:00",
    )
    low = pull_once(
        config_path=_write_config(tmp_path / "low.yaml", weight=0.5),
        data_dir=tmp_path / "low-data",
        counter_path=tmp_path / "low-counters.json",
        backend_factory=lambda name: FakeBackend([message]),
        require_live_gate=False,
    )
    high = pull_once(
        config_path=_write_config(tmp_path / "high.yaml", weight=1.2),
        data_dir=tmp_path / "high-data",
        counter_path=tmp_path / "high-counters.json",
        backend_factory=lambda name: FakeBackend([message]),
        require_live_gate=False,
    )

    assert low["stats"]["low_quality_messages"] == 1
    assert low["stats"]["written_messages"] == 0
    assert high["stats"]["written_messages"] == 1


def test_pull_once_refuses_real_backend_when_live_gate_fails(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("SAPPHIRE_TELEGRAM_INTEL_LIVE", raising=False)
    result = pull_once(
        config_path=_write_config(tmp_path / "channels.yaml"),
        data_dir=tmp_path / "data",
        counter_path=tmp_path / "counters.json",
    )
    assert result["ok"] is False
    assert result["error"] == "live gate refused"


def test_pull_once_reports_backend_errors(tmp_path: Path) -> None:
    class BrokenBackend:
        def pull_channel(self, channel: ChannelConfig, *, limit: int, since_id: str | None = None):
            raise BackendError("offline")

    result = pull_once(
        config_path=_write_config(tmp_path / "channels.yaml"),
        data_dir=tmp_path / "data",
        counter_path=tmp_path / "counters.json",
        backend_factory=lambda name: BrokenBackend(),
        require_live_gate=False,
    )
    assert result["ok"] is False
    assert result["stats"]["errors"] == ["chan-0:BackendError"]


def test_pull_once_uses_classifier_cap_fallback(tmp_path: Path) -> None:
    cfg_path = _write_config(tmp_path / "channels.yaml", classifier=True)
    counter_path = tmp_path / "counters.json"
    counter_path.write_text(
        json.dumps({"classifications": [time.time()] * 200}), encoding="utf-8"
    )
    result = pull_once(
        config_path=cfg_path,
        data_dir=tmp_path / "data",
        counter_path=counter_path,
        backend_factory=lambda name: FakeBackend(),
        classifier=FakeClassifier(),
        require_live_gate=False,
    )
    assert result["stats"]["classifier_calls"] == 0
    assert result["stats"]["written_messages"] == 1


def test_status_is_safe_with_missing_config(tmp_path: Path) -> None:
    result = status(config_path=tmp_path / "missing.yaml", data_dir=tmp_path / "data")
    assert result["ok"] is True
    assert result["config_error"]
    assert result["enabled_channels"] == 0


def test_mtproto_backend_requires_credentials(monkeypatch) -> None:
    monkeypatch.delenv("TELEGRAM_API_ID", raising=False)
    monkeypatch.delenv("TELEGRAM_API_HASH", raising=False)
    with pytest.raises(BackendError, match="TELEGRAM_API_ID"):
        MTProtoBackend(session_path="/tmp/session")


def test_botapi_backend_requires_token(monkeypatch) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    with pytest.raises(BackendError, match="TELEGRAM_BOT_TOKEN"):
        BotAPIBackend()


@pytest.mark.parametrize(
    ("source", "chat", "expected"),
    [
        ("@security_feed", {"username": "security_feed"}, True),
        ("security_feed", {"username": "@security_feed"}, True),
        ("-100123", {"id": -100123}, True),
        ("@other", {"username": "security_feed"}, False),
    ],
)
def test_botapi_channel_matching(source: str, chat: dict[str, Any], expected: bool) -> None:
    assert _matches_channel(ChannelConfig(id="c", source=source), chat) is expected


def test_botapi_backend_filters_updates_without_network(monkeypatch) -> None:
    payload = {
        "ok": True,
        "result": [
            {
                "update_id": 10,
                "channel_post": {
                    "message_id": 7,
                    "date": 1_700_000_000,
                    "text": "Security patch released for CVE-2026-0002.",
                    "chat": {"username": "security_feed"},
                },
            },
            {
                "update_id": 11,
                "channel_post": {
                    "message_id": 8,
                    "date": 1_700_000_001,
                    "text": "Wrong channel.",
                    "chat": {"username": "other"},
                },
            },
        ],
    }

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def read(self) -> bytes:
            return json.dumps(payload).encode("utf-8")

    monkeypatch.setattr("urllib.request.urlopen", lambda url, timeout: FakeResponse())
    backend = BotAPIBackend(token="test-token")
    messages = backend.pull_channel(ChannelConfig(id="c", source="@security_feed"), limit=5)
    assert [message.message_id for message in messages] == ["7"]
    assert messages[0].metadata["backend"] == "botapi"


def test_build_backend_accepts_prompt_bot_name(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    from services.telegram_intel.backends import build_backend

    assert isinstance(build_backend("bot"), BotAPIBackend)


def test_mtproto_backend_uses_mocked_telethon(monkeypatch, tmp_path: Path) -> None:
    class FakeMessage:
        id = 42
        raw_text = "Cloud incident confirmed with mitigation steps published."
        date = datetime(2026, 4, 28, 12, 0, tzinfo=UTC)

    class FakeClient:
        def __init__(self, session, api_id, api_hash):
            self.args = (session, api_id, api_hash)

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def iter_messages(self, source, *, limit, min_id):
            assert source == "@ops"
            assert limit == 5
            assert min_id == 40
            yield FakeMessage()

    monkeypatch.setitem(sys.modules, "telethon", types.SimpleNamespace(TelegramClient=FakeClient))
    backend = MTProtoBackend(api_id="123", api_hash="hash", session_path=tmp_path / "s")
    messages = backend.pull_channel(ChannelConfig(id="ops", source="@ops"), limit=5, since_id="40")
    assert messages[0].message_id == "42"
    assert messages[0].published_at == "2026-04-28T12:00:00+00:00"


def test_pull_once_honors_message_hourly_cap(tmp_path: Path) -> None:
    cfg_path = _write_config(tmp_path / "channels.yaml")
    counter_path = tmp_path / "counters.json"
    counter_path.write_text(json.dumps({"messages": [time.time()] * 600}), encoding="utf-8")
    result = pull_once(
        config_path=cfg_path,
        data_dir=tmp_path / "data",
        counter_path=counter_path,
        backend_factory=lambda name: FakeBackend(),
        require_live_gate=False,
    )
    assert result["ok"] is False
    assert result["error"] == "message rate limit exhausted"


def test_pull_once_uses_enabled_channels_only(tmp_path: Path) -> None:
    cfg_path = _write_config(tmp_path / "channels.yaml", enabled=False, channels=2)
    backend = FakeBackend()
    result = pull_once(
        config_path=cfg_path,
        data_dir=tmp_path / "data",
        counter_path=tmp_path / "counters.json",
        backend_factory=lambda name: backend,
        require_live_gate=False,
    )
    assert result["stats"]["channels"] == 0
    assert backend.calls == []
