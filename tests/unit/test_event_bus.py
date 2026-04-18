"""Unit tests for the EventBus (Redis Streams with JSONL fallback)."""

from __future__ import annotations

import sys
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
LIB_CORE = ROOT / "lib" / "core"
if str(LIB_CORE) not in sys.path:
    sys.path.insert(0, str(LIB_CORE))

from event_bus import EVENT_TYPES, Event, EventBus  # noqa: E402


@pytest.fixture
def bus(tmp_path) -> EventBus:
    # Force fallback mode by using an invalid redis URL so the test does not
    # depend on a running Redis server.
    b = EventBus(redis_url="redis://127.0.0.1:1/0", fallback_path=tmp_path / "bus.jsonl")
    assert not b.healthy(), "test fixture should be in fallback mode"
    return b


def test_publish_returns_id(bus: EventBus) -> None:
    ev_id = bus.publish("signal.generated", {"symbol": "BTC", "confidence": 0.8})
    assert ev_id and isinstance(ev_id, str)


def test_publish_three_and_replay(bus: EventBus) -> None:
    for i in range(3):
        bus.publish("signal.generated", {"i": i, "symbol": "BTC"})
    events = bus.replay("signal.generated", since=datetime.now(UTC) - timedelta(hours=1))
    assert len(events) == 3
    assert [e.data["i"] for e in events] == [0, 1, 2]


def test_subscribe_receives_events(bus: EventBus) -> None:
    received: list[Event] = []
    done = threading.Event()

    def on_event(ev: Event) -> None:
        received.append(ev)
        if len(received) >= 2:
            done.set()

    bus.subscribe(["signal.*"], on_event, start_id="0")
    time.sleep(0.1)  # let the subscriber thread start
    bus.publish("signal.generated", {"symbol": "ETH"})
    bus.publish("signal.closed", {"symbol": "ETH", "pnl_usd": 42.5})
    bus.publish("threat.detected", {"cve": "CVE-X"})  # should be filtered out
    done.wait(timeout=5.0)
    bus.unsubscribe_all()
    types = sorted(e.type for e in received)
    assert types == ["signal.closed", "signal.generated"], types


def test_world_state_aggregation(bus: EventBus) -> None:
    bus.publish("regime.snapshot", {"regime": "RISK_ON", "confidence": 0.75})
    bus.publish("sentiment.update", {"fear_greed": 62})
    bus.publish("service.health", {"status": "nominal"})
    bus.publish("signal.generated", {"symbol": "BTC"})
    bus.publish("signal.generated", {"symbol": "ETH"})
    bus.publish("signal.closed", {"symbol": "BTC", "pnl_usd": 100.0})

    ws = bus.get_world_state()
    assert ws.market_regime == "RISK_ON"
    assert ws.regime_confidence == pytest.approx(0.75)
    assert ws.fear_greed == 62
    assert ws.infrastructure_health == "nominal"
    assert ws.active_signals == 2
    assert ws.open_positions == 1  # 2 generated - 1 closed
    assert ws.portfolio_pnl == pytest.approx(100.0)


def test_glob_pattern_match(bus: EventBus) -> None:
    received: list[Event] = []

    def on_event(ev: Event) -> None:
        received.append(ev)

    bus.publish("regime.shifted", {"regime": "RISK_OFF"})
    bus.publish("signal.generated", {"symbol": "BTC"})
    bus.publish("signal.closed", {"symbol": "BTC"})  # not matched

    bus.subscribe(["regime.*", "signal.generated"], on_event, start_id="0")
    # Fallback tail polls at 1s cadence — give it two cycles.
    time.sleep(2.5)
    bus.unsubscribe_all()

    types = sorted(e.type for e in received)
    assert "regime.shifted" in types
    assert "signal.generated" in types
    assert "signal.closed" not in types


def test_event_types_are_canonical() -> None:
    # Smoke check — keeps the canonical set in sync with the dataclass defaults
    assert "regime.shifted" in EVENT_TYPES
    assert "signal.generated" in EVENT_TYPES
    assert "threat.detected" in EVENT_TYPES
    assert "correlation.broken" in EVENT_TYPES
    assert "sentiment.update" in EVENT_TYPES
