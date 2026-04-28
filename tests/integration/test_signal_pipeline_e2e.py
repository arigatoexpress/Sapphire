"""End-to-end signal pipeline tests.

Exercises: signal_logger HTTP receiver → JSONL append → event stream.
Uses the FastAPI TestClient so no sockets are opened. Telegram +
Nemotron side effects are stubbed.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("fastapi") is None
    or importlib.util.find_spec("fastapi.testclient") is None,
    reason="signal pipeline E2E tests require FastAPI TestClient",
)

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
    monkeypatch.setattr(sl, "_WEBHOOK_SECRET", "test-secret")

    if sl._PIPELINE_AVAILABLE:
        import signal_pipeline as sp

        pipeline_dir = tmp_path / "pipeline_signals"
        pipeline_dir.mkdir()
        monkeypatch.setattr(sp, "SIGNALS_DIR", pipeline_dir)
        monkeypatch.setattr(sp, "PAPER_TRADING_LOG", tmp_path / "paper_trading.jsonl")
        monkeypatch.setattr(sp, "_NOTIFY_AVAILABLE", False)
        monkeypatch.setattr(sp, "_KERNEL_AVAILABLE", False)
        monkeypatch.setattr(sp, "_FIREWALL_AVAILABLE", False)
        monkeypatch.setattr(sp, "_DECISION_ENGINE_AVAILABLE", False)
        monkeypatch.setattr(sp, "_DECISION_ENGINE", None)

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
    return TestClient(sl.app, client=("127.0.0.1", 50000))


def test_health_endpoint(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["mode"] == "signal_logger"
    assert body["paper_trading"] is True


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, True),
        ("", True),
        ("1", True),
        ("true", True),
        ("0", False),
        ("false", False),
        ("typo", True),
    ],
)
def test_health_paper_trading_defaults_fail_closed(client, monkeypatch, value, expected):
    import signal_logger as sl

    if value is None:
        monkeypatch.delenv("PAPER_TRADING", raising=False)
    else:
        monkeypatch.setenv("PAPER_TRADING", value)

    assert sl._paper_trading_env_enabled() is expected
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["paper_trading"] is expected


def test_signal_post_appends_jsonl(client, isolated_signals):
    payload = {
        "secret": "test-secret",
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
        "secret": "test-secret",
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
            "secret": "test-secret",
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
        "secret": "test-secret",
        "symbol": "BTCUSDT", "action": "BUY", "price": 1.0, "confidence": 0.1,
    })
    assert r.status_code == 200
    assert (isolated_signals / "trading_signals.jsonl").exists()
