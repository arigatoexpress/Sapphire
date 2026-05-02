"""Tests for the Hyperliquid public WebSocket feed wrapper."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SERVICE_SRC = ROOT / "services" / "hyperliquid" / "src"
for path in (ROOT, SERVICE_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from hyperliquid_bot import public_feed as feed


class FakeBus:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict, str | None]] = []

    def publish(self, event_type: str, data: dict, source: str | None = None) -> str:
        self.events.append((event_type, data, source))
        return f"evt-{len(self.events)}"


class FakeWebSocket:
    def __init__(self, messages: list[str]) -> None:
        self.messages = messages
        self.sent: list[dict] = []

    async def __aenter__(self) -> "FakeWebSocket":
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def send(self, payload: str) -> None:
        self.sent.append(json.loads(payload))

    def __aiter__(self) -> "FakeWebSocket":
        self._remaining = iter(self.messages)
        return self

    async def __anext__(self) -> str:
        try:
            return next(self._remaining)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


def test_load_symbol_config_defaults_when_missing(tmp_path):
    config = feed.load_symbol_config(tmp_path / "missing.yaml")

    assert config.symbols == ("BTC", "ETH", "SOL")
    assert config.source == "default"


def test_load_symbol_config_reads_mapping_and_normalizes(tmp_path):
    path = tmp_path / "symbols.yaml"
    path.write_text("symbols: [btc, ETH, btc, sol]\n", encoding="utf-8")

    config = feed.load_symbol_config(path)

    assert config.symbols == ("BTC", "ETH", "SOL")
    assert config.source == "file"
    assert config.capped is False


def test_load_symbol_config_reads_top_level_list(tmp_path):
    path = tmp_path / "symbols.yaml"
    path.write_text("- hype\n- '@150'\n", encoding="utf-8")

    config = feed.load_symbol_config(path)

    assert config.symbols == ("HYPE", "@150")


def test_load_symbol_config_caps_at_max_symbols(tmp_path):
    path = tmp_path / "symbols.yaml"
    symbols = [f"COIN{i}" for i in range(12)]
    path.write_text("symbols:\n" + "\n".join(f"  - {s}" for s in symbols), encoding="utf-8")

    config = feed.load_symbol_config(path)

    assert len(config.symbols) == feed.MAX_SYMBOLS
    assert config.capped is True


def test_load_symbol_config_ignores_invalid_symbols(tmp_path):
    path = tmp_path / "symbols.yaml"
    path.write_text("symbols: ['BTC', 'bad symbol', '../../secret', 'ETH']\n", encoding="utf-8")

    config = feed.load_symbol_config(path)

    assert config.symbols == ("BTC", "ETH")


def test_load_symbol_config_malformed_yaml_falls_back(tmp_path):
    path = tmp_path / "symbols.yaml"
    path.write_text("symbols: [BTC\n", encoding="utf-8")

    config = feed.load_symbol_config(path)

    assert config.symbols == ("BTC", "ETH", "SOL")
    assert config.source == "default-read-error"


def test_subscription_payloads_cover_three_channels_per_symbol():
    payloads = feed.subscription_payloads(["btc", "ETH", "btc"])

    assert len(payloads) == 6
    assert payloads[0] == {"method": "subscribe", "subscription": {"type": "trades", "coin": "BTC"}}
    assert payloads[1]["subscription"]["type"] == "bbo"
    assert payloads[2]["subscription"]["type"] == "l2Book"


def test_subscription_payloads_ignore_unknown_channels():
    payloads = feed.subscription_payloads(["BTC"], channels=["trades", "orders"])

    assert payloads == [{"method": "subscribe", "subscription": {"type": "trades", "coin": "BTC"}}]


def test_subscribe_test_is_dry_run():
    result = feed.HyperliquidPublicFeedSubscriber(["BTC", "ETH"]).subscribe_test()

    assert result["status"] == "dry-run"
    assert result["auth_required"] is False
    assert result["wallet_keys_required"] is False
    assert result["subscription_count"] == 6


def test_live_enabled_requires_explicit_one():
    assert feed.live_enabled({"SAPPHIRE_HYPERLIQUID_LIVE": "0"}) is False
    assert feed.live_enabled({"SAPPHIRE_HYPERLIQUID_LIVE": "1"}) is True


def test_status_payload_reports_signal_only_safety(tmp_path, monkeypatch):
    monkeypatch.setenv("SAPPHIRE_ROUTINE_PAUSE_DIR", str(tmp_path / "pause"))
    payload = feed.status_payload(
        symbol_config_path=tmp_path / "missing.yaml",
        signal_log_path=tmp_path / "signals.jsonl",
    )

    assert payload["mode"] == "signal-only"
    assert payload["wallet_keys_required"] is False
    assert payload["authenticated_endpoints_enabled"] is False
    assert payload["event_topics"] == [
        "hyperliquid.trade",
        "hyperliquid.imbalance",
        "hyperliquid.book.thin",
    ]


def test_routine_pause_local_fallback_detects_all_file(tmp_path, monkeypatch):
    pause_dir = tmp_path / "pause"
    pause_dir.mkdir()
    (pause_dir / "all").write_text("paused\n", encoding="utf-8")
    monkeypatch.setenv("SAPPHIRE_ROUTINE_PAUSE_DIR", str(pause_dir))

    status = feed.routine_pause_status()

    assert status == {"paused": True, "source": "local-fallback"}


def test_hourly_limiter_enforces_cap():
    limiter = feed.HourlyLimiter(max_events=2)

    assert limiter.allow(100.0) is True
    assert limiter.allow(101.0) is True
    assert limiter.allow(102.0) is False
    assert limiter.snapshot(102.0)["remaining"] == 0


def test_hourly_limiter_prunes_old_entries():
    limiter = feed.HourlyLimiter(max_events=1, window_seconds=10)

    assert limiter.allow(100.0) is True
    assert limiter.allow(109.0) is False
    assert limiter.allow(111.0) is True


def test_jsonl_signal_store_latest_is_newest_first(tmp_path):
    store = feed.JsonlSignalStore(tmp_path / "signals.jsonl")
    store.append({"id": 1})
    store.append({"id": 2})

    assert store.latest(limit=2) == [{"id": 2}, {"id": 1}]


def test_jsonl_signal_store_skips_bad_lines(tmp_path):
    path = tmp_path / "signals.jsonl"
    path.write_text('{"id": 1}\nnot-json\n{"id": 2}\n', encoding="utf-8")

    assert feed.JsonlSignalStore(path).latest(limit=3) == [{"id": 2}, {"id": 1}]


def test_decode_ws_message_accepts_bytes():
    decoded = feed.decode_ws_message(b'{"channel":"subscriptionResponse"}')

    assert decoded == {"channel": "subscriptionResponse"}


def test_decode_ws_message_ignores_malformed_json():
    assert feed.decode_ws_message("{not json") is None


async def test_run_forever_blocks_without_live_env(monkeypatch):
    monkeypatch.delenv("SAPPHIRE_HYPERLIQUID_LIVE", raising=False)
    subscriber = feed.HyperliquidPublicFeedSubscriber(["BTC"])

    result = await subscriber.run_forever(stop_after_messages=1)

    assert result["status"] == "blocked"
    assert result["dry_run"] is True
    assert result["subscribe_test"]["subscription_count"] == 3


async def test_connect_once_sends_subscriptions_and_publishes_signal(tmp_path):
    bus = FakeBus()
    publisher = feed.SignalPublisher(
        bus=bus, store=feed.JsonlSignalStore(tmp_path / "signals.jsonl")
    )
    subscriber = feed.HyperliquidPublicFeedSubscriber(["BTC"], publisher=publisher)
    trade = {
        "channel": "trades",
        "data": [
            {"coin": "BTC", "px": "100000", "sz": "3", "side": "B", "time": 1_700_000_000_000}
        ],
    }
    ws = FakeWebSocket([json.dumps(trade)])

    def connector(*_args: object, **_kwargs: object) -> FakeWebSocket:
        return ws

    seen = await subscriber._connect_once(connector, stop_after_messages=1)

    assert seen == 1
    assert len(ws.sent) == 3
    assert bus.events[0][0] == "hyperliquid.trade"
    assert (
        feed.JsonlSignalStore(tmp_path / "signals.jsonl").latest(limit=1)[0]["event_id"] == "evt-1"
    )


async def test_run_forever_stops_when_reconnect_cap_is_hit(monkeypatch):
    monkeypatch.setenv("SAPPHIRE_HYPERLIQUID_LIVE", "1")

    async def no_sleep(_seconds: float) -> None:
        return None

    def connector(*_args: object, **_kwargs: object) -> object:
        raise OSError("closed")

    subscriber = feed.HyperliquidPublicFeedSubscriber(
        ["BTC"],
        reconnect_limiter=feed.HourlyLimiter(max_events=1),
        sleep=no_sleep,
    )

    result = await subscriber.run_forever(connect=connector)

    assert result["status"] == "blocked"
    assert result["reason"] == "reconnect cap reached"
    assert "OSError" in result["last_error"]
