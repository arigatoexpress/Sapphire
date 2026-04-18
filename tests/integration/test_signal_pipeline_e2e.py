"""End-to-end signal pipeline tests.

Exercises: signal_logger HTTP receiver → JSONL append → event stream.
Uses the FastAPI TestClient so no sockets are opened. Telegram +
Nemotron side effects are stubbed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ALPHA_SRC = ROOT / "services" / "alpha" / "src"
for _p in (str(ROOT), str(ALPHA_SRC)):
    if _p not in sys.path:
        sys.path.insert(0, _p)


@pytest.fixture
def isolated_signals(tmp_path, monkeypatch):
    """Redirect signal_logger JSONL writes into tmp."""
    import signal_logger as sl

    monkeypatch.setattr(sl, "SIGNALS_PATH", tmp_path / "trading_signals.jsonl")
    monkeypatch.setattr(sl, "EVENTS_PATH", tmp_path / "system_events.jsonl")

    # Silence side effects: Nemotron + Telegram notifications
    def _stub_generate(*args, **kwargs):
        class R:
            success = True
            response = "stub assessment"
        return R()

    monkeypatch.setitem(sys.modules, "nemotron",
                        type(sys)("nemotron"))
    sys.modules["nemotron"].generate = _stub_generate
    sys.modules["nemotron"].MODELS = {"classify": "stub"}

    monkeypatch.setitem(sys.modules, "notify",
                        type(sys)("notify"))
    sys.modules["notify"].send_telegram_message = lambda *a, **k: {"ok": True}

    return tmp_path


@pytest.fixture
def client(isolated_signals):
    import signal_logger as sl
    from fastapi.testclient import TestClient
    return TestClient(sl.app)


def test_health_endpoint(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["mode"] == "signal_logger"


def test_signal_post_appends_jsonl(client, isolated_signals):
    payload = {
        "symbol": "BTCUSDT",
        "action": "BUY",
        "strategy": "ema_cross",
        "price": 67500.0,
        "confidence": 0.78,
        "signal_id": "test-abc-1",
    }
    r = client.post("/api/signals", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "logged"
    assert body["signal_id"] == "test-abc-1"

    signals_file = isolated_signals / "trading_signals.jsonl"
    assert signals_file.exists()
    lines = signals_file.read_text().strip().splitlines()
    assert len(lines) == 1
    logged = json.loads(lines[0])
    assert logged["symbol"] == "BTCUSDT"
    assert logged["action"] == "BUY"
    assert logged["price"] == 67500.0
    assert logged["source"] == "webhook"
    assert logged["execution"] == "LOGGED_ONLY"


def test_signal_post_appends_system_events(client, isolated_signals):
    client.post("/api/signals", json={
        "symbol": "ETHUSDT",
        "action": "SELL",
        "price": 3200.0,
        "confidence": 0.65,
        "strategy": "bb_top",
    })
    events_file = isolated_signals / "system_events.jsonl"
    assert events_file.exists()
    events = [json.loads(line) for line in events_file.read_text().strip().splitlines()]
    assert len(events) == 1
    assert events[0]["type"] == "signal.received"
    assert "type:trading" in events[0]["tags"]
    assert events[0]["data"]["symbol"] == "ETHUSDT"


def test_recent_signals_returns_reverse_chronological(client, isolated_signals):
    for i, sym in enumerate(["BTCUSDT", "ETHUSDT", "SOLUSDT"]):
        client.post("/api/signals", json={
            "symbol": sym, "action": "BUY", "price": 100.0 + i, "confidence": 0.5,
        })
    r = client.get("/api/signals/recent")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 3
    assert body["signals"][0]["symbol"] == "SOLUSDT"
    assert body["signals"][-1]["symbol"] == "BTCUSDT"


def test_invalid_json_rejected(client):
    r = client.post("/api/signals", data="not-json",
                    headers={"Content-Type": "application/json"})
    assert r.status_code == 400
    assert r.json()["error"] == "invalid JSON"


def test_legacy_create_route_also_works(client, isolated_signals):
    r = client.post("/api/signals/create", json={
        "symbol": "BTCUSDT", "action": "BUY", "price": 1.0, "confidence": 0.1,
    })
    assert r.status_code == 200
    assert (isolated_signals / "trading_signals.jsonl").exists()
