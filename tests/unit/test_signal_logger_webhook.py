"""Security-boundary tests for ``services/alpha/src/signal_logger.py``.

Covers the Tailscale-only middleware, ``WEBHOOK_SECRET`` enforcement,
malformed-payload handling, paper-trading mode parsing, and the
``/api/signals/recent`` retrieval surface. No real network calls,
no Telegram sends, no live trading paths.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

SIGNAL_LOGGER_DIR = Path(__file__).resolve().parents[2] / "services" / "alpha" / "src"


@pytest.fixture
def signal_logger(tmp_path, monkeypatch):
    """Import ``signal_logger`` fresh with a known secret and tmp paths.

    The module reads ``WEBHOOK_SECRET`` and runs ``sys.path`` mutations at
    import time. We pop the cached module so each test gets a clean copy
    bound to the env we control.
    """
    monkeypatch.setenv("WEBHOOK_SECRET", "test-secret")
    monkeypatch.setenv("TELEGRAM_DRY_RUN", "1")
    monkeypatch.setenv(
        "SAPPHIRE_NOTIFY_DRAFT_QUEUE_PATH",
        str(tmp_path / "pm_bot_drafts.jsonl"),
    )
    monkeypatch.syspath_prepend(str(SIGNAL_LOGGER_DIR))
    sys.modules.pop("signal_logger", None)

    import signal_logger as sl  # noqa: PLC0415

    monkeypatch.setattr(sl, "SIGNALS_PATH", tmp_path / "signals.jsonl")
    monkeypatch.setattr(sl, "EVENTS_PATH", tmp_path / "events.jsonl")
    monkeypatch.setattr(sl, "_PIPELINE_AVAILABLE", False)
    yield sl
    sys.modules.pop("signal_logger", None)


@pytest.fixture
def client(signal_logger, monkeypatch):
    """``TestClient`` with the Tailscale middleware bypassed.

    The middleware is exercised separately by ``test_middleware_*`` tests
    so endpoint tests can use the synchronous TestClient (whose default
    ``request.client.host`` of ``"testclient"`` would otherwise 403).
    """

    async def _passthrough(self, request, call_next):  # noqa: ARG001
        return await call_next(request)

    monkeypatch.setattr(signal_logger._TailscaleOnlyMiddleware, "dispatch", _passthrough)
    return TestClient(signal_logger.app)


# ── _TailscaleOnlyMiddleware ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_middleware_allows_localhost(signal_logger):
    middleware = signal_logger._TailscaleOnlyMiddleware(app=signal_logger.app)
    request = MagicMock()
    request.client.host = "127.0.0.1"
    expected = JSONResponse({"ok": True})
    call_next = AsyncMock(return_value=expected)

    response = await middleware.dispatch(request, call_next)

    assert response is expected
    call_next.assert_awaited_once()


@pytest.mark.asyncio
async def test_middleware_allows_tailscale_cgnat(signal_logger):
    middleware = signal_logger._TailscaleOnlyMiddleware(app=signal_logger.app)
    request = MagicMock()
    request.client.host = "100.100.1.2"  # any Tailscale CGNAT-range address
    call_next = AsyncMock(return_value=JSONResponse({"ok": True}))

    response = await middleware.dispatch(request, call_next)

    assert response.status_code == 200
    call_next.assert_awaited_once()


@pytest.mark.asyncio
async def test_middleware_allows_tailscale_pi(signal_logger):
    middleware = signal_logger._TailscaleOnlyMiddleware(app=signal_logger.app)
    request = MagicMock()
    request.client.host = "100.100.1.3"  # any Tailscale CGNAT-range address
    call_next = AsyncMock(return_value=JSONResponse({"ok": True}))

    response = await middleware.dispatch(request, call_next)

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_middleware_rejects_public_ip(signal_logger):
    middleware = signal_logger._TailscaleOnlyMiddleware(app=signal_logger.app)
    request = MagicMock()
    request.client.host = "8.8.8.8"
    call_next = AsyncMock()

    response = await middleware.dispatch(request, call_next)

    assert response.status_code == 403
    assert json.loads(response.body)["error"] == "forbidden"
    call_next.assert_not_awaited()


@pytest.mark.asyncio
async def test_middleware_rejects_private_rfc1918(signal_logger):
    """RFC1918 (192.168.x.x) is NOT in Tailscale CGNAT and must be blocked."""
    middleware = signal_logger._TailscaleOnlyMiddleware(app=signal_logger.app)
    request = MagicMock()
    request.client.host = "192.168.1.21"  # rari2 LAN address
    call_next = AsyncMock()

    response = await middleware.dispatch(request, call_next)

    assert response.status_code == 403
    call_next.assert_not_awaited()


@pytest.mark.asyncio
async def test_middleware_rejects_invalid_ip(signal_logger):
    middleware = signal_logger._TailscaleOnlyMiddleware(app=signal_logger.app)
    request = MagicMock()
    request.client.host = "not-an-ip"
    call_next = AsyncMock()

    response = await middleware.dispatch(request, call_next)

    assert response.status_code == 403
    call_next.assert_not_awaited()


@pytest.mark.asyncio
async def test_middleware_rejects_missing_client(signal_logger):
    middleware = signal_logger._TailscaleOnlyMiddleware(app=signal_logger.app)
    request = MagicMock()
    request.client = None
    call_next = AsyncMock()

    response = await middleware.dispatch(request, call_next)

    assert response.status_code == 403
    call_next.assert_not_awaited()


@pytest.mark.asyncio
async def test_middleware_rejects_ipv6_outside_cgnat(signal_logger):
    middleware = signal_logger._TailscaleOnlyMiddleware(app=signal_logger.app)
    request = MagicMock()
    request.client.host = "2001:db8::1"
    call_next = AsyncMock()

    response = await middleware.dispatch(request, call_next)

    assert response.status_code == 403


# ── _paper_trading_env_enabled ─────────────────────────────────────────


def test_paper_trading_default_enabled(signal_logger, monkeypatch):
    monkeypatch.delenv("PAPER_TRADING", raising=False)
    assert signal_logger._paper_trading_env_enabled() is True


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "y", "on"])
def test_paper_trading_truthy_values(signal_logger, monkeypatch, value):
    monkeypatch.setenv("PAPER_TRADING", value)
    assert signal_logger._paper_trading_env_enabled() is True


@pytest.mark.parametrize("value", ["0", "false", "FALSE", "no", "n", "off"])
def test_paper_trading_falsey_values(signal_logger, monkeypatch, value):
    monkeypatch.setenv("PAPER_TRADING", value)
    assert signal_logger._paper_trading_env_enabled() is False


def test_paper_trading_unrecognized_defaults_to_true(signal_logger, monkeypatch):
    monkeypatch.setenv("PAPER_TRADING", "maybe")
    assert signal_logger._paper_trading_env_enabled() is True


def test_paper_trading_blank_defaults_to_true(signal_logger, monkeypatch):
    monkeypatch.setenv("PAPER_TRADING", "   ")
    assert signal_logger._paper_trading_env_enabled() is True


# ── /health ────────────────────────────────────────────────────────────


def test_health_returns_paper_trading_flag(client):
    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["mode"] == "signal_logger"
    assert payload["paper_trading"] is True
    assert payload["webhook_secret_configured"] is True
    assert payload["signal_ingest_ready"] is True
    assert payload["blockers"] == []
    assert "note" in payload


def test_health_reports_missing_webhook_secret(signal_logger, client, monkeypatch):
    monkeypatch.setattr(signal_logger, "_WEBHOOK_SECRET", "")

    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["webhook_secret_configured"] is False
    assert payload["signal_ingest_ready"] is False
    assert payload["blockers"] == ["webhook_secret_unconfigured"]


# ── /api/signals secret enforcement ────────────────────────────────────


def test_signals_rejects_missing_secret(client):
    response = client.post("/api/signals", json={"symbol": "BTC", "action": "BUY"})

    assert response.status_code == 401
    assert response.json()["error"] == "unauthorized"


def test_signals_rejects_wrong_secret(client):
    response = client.post(
        "/api/signals",
        json={"secret": "wrong", "symbol": "BTC", "action": "BUY"},
    )

    assert response.status_code == 401


def test_signals_rejects_invalid_json(client):
    response = client.post(
        "/api/signals",
        content=b"not json",
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 400
    assert response.json()["error"] == "invalid JSON"


def test_signals_misconfigured_returns_503(signal_logger, monkeypatch):
    """When ``_WEBHOOK_SECRET`` is empty the endpoint fails closed at 503."""
    monkeypatch.setattr(signal_logger, "_WEBHOOK_SECRET", "")

    async def _passthrough(self, request, call_next):  # noqa: ARG001
        return await call_next(request)

    monkeypatch.setattr(signal_logger._TailscaleOnlyMiddleware, "dispatch", _passthrough)
    test_client = TestClient(signal_logger.app)

    response = test_client.post("/api/signals", json={"secret": "anything", "symbol": "BTC"})

    assert response.status_code == 503
    assert "WEBHOOK_SECRET" in response.json()["error"]


# ── /api/signals happy path + persistence ──────────────────────────────


def test_signals_accepts_valid_payload_and_logs(signal_logger, client):
    payload = {
        "secret": "test-secret",
        "symbol": "BTC-USD",
        "action": "BUY",
        "strategy": "test-strategy",
        "price": 65000,
        "confidence": 0.85,
        "signal_id": "test-1",
    }

    response = client.post("/api/signals", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "logged"
    assert body["execution"] == "LOGGED_ONLY"
    assert body["signal_id"] == "test-1"

    signals = signal_logger.SIGNALS_PATH.read_text().strip().splitlines()
    assert len(signals) == 1
    record = json.loads(signals[0])
    assert record["symbol"] == "BTC-USD"
    assert record["execution"] == "LOGGED_ONLY"
    assert record["source"] == "webhook"

    events = signal_logger.EVENTS_PATH.read_text().strip().splitlines()
    assert len(events) == 1
    event = json.loads(events[0])
    assert event["type"] == "signal.received"
    assert "type:trading" in event["tags"]
    assert "device:mac" in event["tags"]
    assert "priority:p1" in event["tags"]


def test_signals_create_alias_works(client):
    """The legacy ``/api/signals/create`` alias accepts the same payload."""
    response = client.post(
        "/api/signals/create",
        json={
            "secret": "test-secret",
            "symbol": "ETH-USD",
            "action": "SELL",
            "price": 3500,
            "confidence": 0.7,
            "signal_id": "alias-test",
        },
    )

    assert response.status_code == 200
    assert response.json()["signal_id"] == "alias-test"


def test_signals_handles_alternative_side_field(signal_logger, client):
    """``side`` is a legacy alias for ``action`` and is accepted."""
    response = client.post(
        "/api/signals",
        json={
            "secret": "test-secret",
            "symbol": "BTC-USD",
            "side": "BUY",
            "price": 65000,
        },
    )

    assert response.status_code == 200
    record = json.loads(signal_logger.SIGNALS_PATH.read_text().strip().splitlines()[-1])
    assert record["action"] == "BUY"


def test_signals_default_fields_when_missing(signal_logger, client):
    """Required fields fall back to safe defaults; nothing is silently dropped."""
    response = client.post("/api/signals", json={"secret": "test-secret"})

    assert response.status_code == 200
    record = json.loads(signal_logger.SIGNALS_PATH.read_text().strip().splitlines()[-1])
    assert record["symbol"] == "UNKNOWN"
    assert record["action"] == "UNKNOWN"
    assert record["strategy"] == "unknown"
    assert record["price"] == 0
    assert record["confidence"] == 0


# ── /api/signals/recent ────────────────────────────────────────────────


def test_recent_signals_empty_when_file_missing(signal_logger, client):
    if signal_logger.SIGNALS_PATH.exists():
        signal_logger.SIGNALS_PATH.unlink()

    response = client.get("/api/signals/recent")

    assert response.status_code == 200
    assert response.json() == {"signals": [], "count": 0}


def test_recent_signals_returns_reversed(signal_logger, client):
    signal_logger.SIGNALS_PATH.parent.mkdir(parents=True, exist_ok=True)
    signal_logger.SIGNALS_PATH.write_text(
        json.dumps({"signal_id": "first", "symbol": "BTC"})
        + "\n"
        + json.dumps({"signal_id": "second", "symbol": "ETH"})
        + "\n"
    )

    response = client.get("/api/signals/recent")

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 2
    assert payload["signals"][0]["signal_id"] == "second"
    assert payload["signals"][1]["signal_id"] == "first"


def test_recent_signals_skips_malformed_lines(signal_logger, client):
    signal_logger.SIGNALS_PATH.parent.mkdir(parents=True, exist_ok=True)
    signal_logger.SIGNALS_PATH.write_text(
        json.dumps({"signal_id": "ok-1"})
        + "\n"
        + "not-json\n"
        + json.dumps({"signal_id": "ok-2"})
        + "\n"
    )

    response = client.get("/api/signals/recent")

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 2
    ids = {s["signal_id"] for s in payload["signals"]}
    assert ids == {"ok-1", "ok-2"}


def test_recent_signals_caps_at_twenty(signal_logger, client):
    """Endpoint returns only the most recent 20 entries by design."""
    signal_logger.SIGNALS_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps({"signal_id": f"sig-{i}"}) for i in range(50)]
    signal_logger.SIGNALS_PATH.write_text("\n".join(lines) + "\n")

    response = client.get("/api/signals/recent")

    payload = response.json()
    assert payload["count"] == 20
    # Reversed: newest first
    assert payload["signals"][0]["signal_id"] == "sig-49"
    assert payload["signals"][-1]["signal_id"] == "sig-30"
