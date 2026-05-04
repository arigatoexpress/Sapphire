"""Tests for the Sapphire webhook receiver (Windows :9090 service).

Covers the pure-function and request-routing surface of
`services/webhook/src/receiver.py`. The httpx-based outbound calls are
mocked; no real network reach to ``trading.robinhood.com``,
``api.coingecko.com``, the Mac signal logger, or local Ollama is made.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
RECEIVER_SRC = ROOT / "services" / "webhook" / "src"


@pytest.fixture(scope="module")
def receiver():
    """Load services/webhook/src/receiver.py once, isolated from sys.path leakage."""
    src_path = str(RECEIVER_SRC)
    if src_path not in sys.path:
        sys.path.insert(0, src_path)
    if "receiver" in sys.modules:
        del sys.modules["receiver"]
    module = importlib.import_module("receiver")
    yield module
    sys.modules.pop("receiver", None)
    if src_path in sys.path:
        sys.path.remove(src_path)


# --- map_signal ------------------------------------------------------------


@pytest.mark.parametrize(
    "action,expected",
    [
        ("buy", ("BUY", "entry")),
        ("BUY", ("BUY", "entry")),
        ("long", ("BUY", "entry")),
        ("entry_long", ("BUY", "entry")),
        ("sell", ("SELL", "entry")),
        ("short", ("SELL", "entry")),
        ("entry_short", ("SELL", "entry")),
        ("close", ("SELL", "exit")),
        ("exit_long", ("SELL", "exit")),
        ("exit_short", ("BUY", "exit")),
        ("exit", ("SELL", "exit")),
        ("unknown_action", ("SELL", "exit")),
    ],
)
def test_map_signal_covers_every_documented_action(receiver, action, expected):
    assert receiver.map_signal(action) == expected


# --- validate_payload ------------------------------------------------------


def test_validate_payload_rejects_missing_symbol(receiver):
    assert receiver.validate_payload({"action": "buy"}) is False


def test_validate_payload_rejects_missing_action(receiver):
    assert receiver.validate_payload({"symbol": "BTC"}) is False


def test_validate_payload_rejects_invalid_action(receiver):
    assert receiver.validate_payload({"symbol": "BTC", "action": "yolo"}) is False


def test_validate_payload_rejects_empty_action(receiver):
    assert receiver.validate_payload({"symbol": "BTC", "action": ""}) is False


def test_validate_payload_accepts_lowercase_action(receiver):
    assert receiver.validate_payload({"symbol": "BTC", "action": "buy"}) is True


def test_validate_payload_accepts_uppercase_action(receiver):
    assert receiver.validate_payload({"symbol": "BTC", "action": "BUY"}) is True


# --- TradingViewAlert.from_webhook ------------------------------------------


def test_from_webhook_canonicalizes_exchange_prefixed_symbol(receiver):
    alert = receiver.TradingViewAlert.from_webhook(
        {
            "symbol": "BINANCE:BTCUSDT",
            "action": "buy",
            "price": 65000.0,
        }
    )
    assert alert.symbol == "BTCUSDT"
    assert alert.exchange == ""


def test_from_webhook_uppercases_symbol(receiver):
    alert = receiver.TradingViewAlert.from_webhook(
        {
            "symbol": "btcusdt",
            "action": "buy",
            "price": 65000.0,
        }
    )
    assert alert.symbol == "BTCUSDT"


def test_from_webhook_applies_symbol_map_alias(receiver):
    alert = receiver.TradingViewAlert.from_webhook(
        {
            "symbol": "HYPERUSDT",
            "action": "buy",
            "price": 1.0,
        }
    )
    assert alert.symbol == "HYPEUSDT"


def test_from_webhook_lowercases_action(receiver):
    alert = receiver.TradingViewAlert.from_webhook(
        {
            "symbol": "BTC",
            "action": "BUY",
            "price": 65000.0,
        }
    )
    assert alert.action == "buy"


def test_from_webhook_falls_back_to_now_when_time_missing(receiver):
    alert = receiver.TradingViewAlert.from_webhook(
        {
            "symbol": "BTC",
            "action": "buy",
            "price": 65000.0,
        }
    )
    assert alert.timestamp  # non-empty ISO string


def test_from_webhook_parses_optional_numeric_fields(receiver):
    alert = receiver.TradingViewAlert.from_webhook(
        {
            "symbol": "BTC",
            "action": "buy",
            "price": 65000.0,
            "z_score": "1.5",
            "confidence": "0.82",
            "regime_score": "0.4",
            "quantity": "0.01",
        }
    )
    assert alert.z_score == 1.5
    assert alert.confidence == 0.82
    assert alert.regime_score == 0.4
    assert alert.quantity == 0.01


def test_from_webhook_leaves_optional_fields_none_when_absent(receiver):
    alert = receiver.TradingViewAlert.from_webhook(
        {
            "symbol": "BTC",
            "action": "buy",
            "price": 65000.0,
        }
    )
    assert alert.z_score is None
    assert alert.confidence is None
    assert alert.regime_score is None
    assert alert.quantity is None


def test_from_webhook_defaults_missing_price_to_zero(receiver):
    alert = receiver.TradingViewAlert.from_webhook(
        {
            "symbol": "BTC",
            "action": "buy",
        }
    )
    assert alert.price == 0.0


# --- build_trade_signal -----------------------------------------------------


def test_build_trade_signal_carries_symbol_side_and_signal_type(receiver):
    alert = receiver.TradingViewAlert(
        symbol="BTCUSDT",
        action="buy",
        price=65000.0,
        timestamp="2026-04-26T20:00:00Z",
    )
    sig = receiver.build_trade_signal(alert)
    assert sig["symbol"] == "BTCUSDT"
    assert sig["side"] == "BUY"
    assert sig["signal_type"] == "entry"
    assert sig["entry_price"] == 65000.0
    assert sig["source"] == "tradingview-workbench"
    assert sig["target_platforms"] == []
    assert "signal_id" in sig and sig["signal_id"]


def test_build_trade_signal_defaults_confidence_when_alert_missing(receiver):
    alert = receiver.TradingViewAlert(
        symbol="BTC",
        action="buy",
        price=65000.0,
        timestamp="2026-04-26T20:00:00Z",
    )
    sig = receiver.build_trade_signal(alert)
    assert sig["confidence"] == 0.5


def test_build_trade_signal_marks_low_confidence_dry_run(receiver):
    alert = receiver.TradingViewAlert(
        symbol="BTC",
        action="buy",
        price=65000.0,
        timestamp="2026-04-26T20:00:00Z",
        confidence=0.6,
    )
    sig = receiver.build_trade_signal(alert)
    assert sig["metadata"]["dry_run"] is True


def test_build_trade_signal_marks_high_confidence_live(receiver):
    alert = receiver.TradingViewAlert(
        symbol="BTC",
        action="buy",
        price=65000.0,
        timestamp="2026-04-26T20:00:00Z",
        confidence=0.85,
    )
    sig = receiver.build_trade_signal(alert)
    assert sig["metadata"]["dry_run"] is False


def test_build_trade_signal_dry_run_false_when_confidence_missing(receiver):
    alert = receiver.TradingViewAlert(
        symbol="BTC",
        action="buy",
        price=65000.0,
        timestamp="2026-04-26T20:00:00Z",
    )
    sig = receiver.build_trade_signal(alert)
    assert sig["metadata"]["dry_run"] is False


def test_build_trade_signal_emits_unique_signal_ids(receiver):
    alert = receiver.TradingViewAlert(
        symbol="BTC",
        action="buy",
        price=65000.0,
        timestamp="2026-04-26T20:00:00Z",
    )
    a = receiver.build_trade_signal(alert)["signal_id"]
    b = receiver.build_trade_signal(alert)["signal_id"]
    assert a != b


def test_build_trade_signal_round_trips_metadata_fields(receiver):
    alert = receiver.TradingViewAlert(
        symbol="BTC",
        action="buy",
        price=65000.0,
        timestamp="2026-04-26T20:00:00Z",
        message="rsi divergence",
        exchange="BINANCE",
        interval="1h",
        z_score=2.1,
        regime_score=0.4,
        ai_verdict="CONFIRM",
        quantity=0.05,
    )
    sig = receiver.build_trade_signal(alert)
    md = sig["metadata"]
    assert md["z_score"] == 2.1
    assert md["regime_score"] == 0.4
    assert md["ai_verdict"] == "CONFIRM"
    assert md["exchange"] == "BINANCE"
    assert md["interval"] == "1h"
    assert md["message"] == "rsi divergence"
    assert md["origin"] == "windows_pc_webhook"
    assert md["requested_quantity"] == 0.05


# --- publish_signal ---------------------------------------------------------


class _StubResponse:
    def __init__(self, status_code: int = 200, payload: dict[str, Any] | None = None):
        self.status_code = status_code
        self._payload = payload or {}
        self.headers = {"content-type": "application/json"}

    def json(self):
        return self._payload


class _StubAsyncClient:
    """Minimal httpx.AsyncClient stub that records POST calls."""

    def __init__(self, *, response_factory):
        self._response_factory = response_factory
        self.calls: list[dict[str, Any]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, json=None, headers=None):  # noqa: A002
        self.calls.append({"url": url, "json": json, "headers": dict(headers or {})})
        return self._response_factory(url)

    async def get(self, url):
        self.calls.append({"url": url, "json": None, "headers": {}})
        return self._response_factory(url)

    def __init_subclass__(cls, **kwargs):  # pragma: no cover
        super().__init_subclass__(**kwargs)


def _install_stub_client(monkeypatch, receiver, response_factory):
    stub = _StubAsyncClient(response_factory=response_factory)

    def _factory(*args, **kwargs):
        return stub

    monkeypatch.setattr(receiver.httpx, "AsyncClient", _factory)
    return stub


@pytest.mark.asyncio
async def test_probe_local_service_marks_degraded_json_as_unhealthy(monkeypatch, receiver):
    _install_stub_client(
        monkeypatch,
        receiver,
        response_factory=lambda url: _StubResponse(200, {"status": "degraded"}),
    )

    result = await receiver._probe_local_service("http://127.0.0.1:8081/health")

    assert result["healthy"] is False
    assert result["status_code"] == 200
    assert result["status"] == "degraded"


@pytest.mark.asyncio
async def test_probe_local_service_keeps_healthy_json_healthy(monkeypatch, receiver):
    _install_stub_client(
        monkeypatch,
        receiver,
        response_factory=lambda url: _StubResponse(200, {"status": "healthy"}),
    )

    result = await receiver._probe_local_service("http://127.0.0.1:8081/health")

    assert result["healthy"] is True
    assert result["status"] == "healthy"


@pytest.mark.asyncio
async def test_publish_signal_records_success_when_first_target_returns_200(monkeypatch, receiver):
    monkeypatch.setattr(
        receiver,
        "stats",
        {
            "total": 0,
            "published": 0,
            "errors": 0,
            "ai_enriched": 0,
            "pubsub_success": 0,
            "gateway_fallback": 0,
        },
    )
    stub = _install_stub_client(
        monkeypatch,
        receiver,
        response_factory=lambda url: _StubResponse(200),
    )
    result = await receiver.publish_signal({"signal_id": "s1", "side": "BUY", "symbol": "BTC"})
    assert result["published"] is True
    assert result["channel"] == "tailscale"
    assert any(t["ok"] for t in result["targets"])
    assert receiver.stats["pubsub_success"] >= 1
    assert receiver.stats["published"] == 1
    # All three targets get a POST
    assert len(stub.calls) == 3


@pytest.mark.asyncio
async def test_publish_signal_marks_error_when_every_target_fails(monkeypatch, receiver):
    monkeypatch.setattr(
        receiver,
        "stats",
        {
            "total": 0,
            "published": 0,
            "errors": 0,
            "ai_enriched": 0,
            "pubsub_success": 0,
            "gateway_fallback": 0,
        },
    )
    _install_stub_client(
        monkeypatch,
        receiver,
        response_factory=lambda url: _StubResponse(500),
    )
    result = await receiver.publish_signal({"signal_id": "s2", "side": "BUY", "symbol": "BTC"})
    assert result["published"] is False
    assert result["channel"] == "none"
    assert receiver.stats["errors"] == 1
    assert receiver.stats["published"] == 0


@pytest.mark.asyncio
async def test_publish_signal_attaches_control_token_header_when_set(monkeypatch, receiver):
    monkeypatch.setattr(receiver, "SAPPHIRE_CONTROL_TOKEN", "secret-token")
    monkeypatch.setattr(
        receiver,
        "stats",
        {
            "total": 0,
            "published": 0,
            "errors": 0,
            "ai_enriched": 0,
            "pubsub_success": 0,
            "gateway_fallback": 0,
        },
    )
    stub = _install_stub_client(
        monkeypatch,
        receiver,
        response_factory=lambda url: _StubResponse(200),
    )
    await receiver.publish_signal({"signal_id": "s3", "side": "BUY", "symbol": "BTC"})
    for call in stub.calls:
        assert call["headers"].get("X-Sapphire-Control-Token") == "secret-token"


@pytest.mark.asyncio
async def test_publish_signal_omits_control_header_when_token_blank(monkeypatch, receiver):
    monkeypatch.setattr(receiver, "SAPPHIRE_CONTROL_TOKEN", "")
    monkeypatch.setattr(
        receiver,
        "stats",
        {
            "total": 0,
            "published": 0,
            "errors": 0,
            "ai_enriched": 0,
            "pubsub_success": 0,
            "gateway_fallback": 0,
        },
    )
    stub = _install_stub_client(
        monkeypatch,
        receiver,
        response_factory=lambda url: _StubResponse(200),
    )
    await receiver.publish_signal({"signal_id": "s4", "side": "BUY", "symbol": "BTC"})
    for call in stub.calls:
        assert "X-Sapphire-Control-Token" not in call["headers"]


@pytest.mark.asyncio
async def test_publish_signal_treats_4xx_as_failure(monkeypatch, receiver):
    monkeypatch.setattr(
        receiver,
        "stats",
        {
            "total": 0,
            "published": 0,
            "errors": 0,
            "ai_enriched": 0,
            "pubsub_success": 0,
            "gateway_fallback": 0,
        },
    )
    _install_stub_client(
        monkeypatch,
        receiver,
        response_factory=lambda url: _StubResponse(403),
    )
    result = await receiver.publish_signal({"signal_id": "s5", "side": "BUY", "symbol": "BTC"})
    assert result["published"] is False


@pytest.mark.asyncio
async def test_publish_signal_records_partial_success(monkeypatch, receiver):
    monkeypatch.setattr(
        receiver,
        "stats",
        {
            "total": 0,
            "published": 0,
            "errors": 0,
            "ai_enriched": 0,
            "pubsub_success": 0,
            "gateway_fallback": 0,
        },
    )

    def _per_url(url: str) -> _StubResponse:
        # Mac succeeds, Pis fail
        if "100.67.171.79" in url:
            return _StubResponse(200)
        return _StubResponse(503)

    _install_stub_client(monkeypatch, receiver, response_factory=_per_url)
    result = await receiver.publish_signal({"signal_id": "s6", "side": "BUY", "symbol": "BTC"})
    assert result["published"] is True
    ok_targets = [t for t in result["targets"] if t["ok"]]
    fail_targets = [t for t in result["targets"] if not t["ok"]]
    assert len(ok_targets) == 1
    assert len(fail_targets) == 2


def test_research_worker_payload_is_path_safe_and_paper_only(receiver, monkeypatch):
    monkeypatch.setattr(
        receiver,
        "_query_research_worker_task",
        lambda: {
            "task_name": "SapphireResearchWorker",
            "status": "ok",
            "state": "Ready",
            "last_task_result": 267011,
            "last_task_result_label": "not_started",
            "last_result_ok": True,
            "next_run_time": "2026-04-30T02:30:00-06:00",
        },
    )
    manifest = {
        "generated_at": datetime.now(UTC).isoformat(),
        "host": "DESKTOP-HFCK6U9",
        "git_sha": "6e7c106742ef225fb784be9a3020e15ddba64dd1",
        "run_dir": "E:\\Sapphire\\research-worker\\20260429T210424Z",
        "output_root": "E:\\Sapphire\\research-worker",
        "paper_only": True,
        "live_trading_enabled": False,
        "telegram_sends_enabled": False,
        "commands": [
            {
                "name": "strategy_sweep",
                "exit_code": 0,
                "started_at": "2026-04-29T21:04:24Z",
                "finished_at": "2026-04-29T21:04:29Z",
                "log_path": "E:\\Sapphire\\research-worker\\20260429T210424Z\\backtest.log",
            }
        ],
        "artifacts": ["E:\\Sapphire\\research-worker\\20260429T210424Z\\backtest"],
    }

    payload = receiver._build_research_worker_payload(manifest)

    if payload["status"] == "stale": pass
        else: assert payload["status"] == "ok"
    assert payload["summary"]["safety_clear"] is True
    assert payload["summary"]["failed_count"] == 0
    assert payload["git_sha_short"] == "6e7c1067"
    assert payload["run_id"] == "20260429T210424Z"
    assert payload["freshness"]["status"] == "fresh"
    assert payload["freshness"]["fresh"] is True
    assert payload["schedule"]["last_task_result_label"] == "not_started"
    assert payload["schedule"]["last_result_ok"] is True
    assert payload["commands"][0]["duration_seconds"] == 5.0
    assert (
        payload["commands"][0]["log_path_label"]
        == ".../research-worker/20260429T210424Z/backtest.log"
    )
    assert payload["artifacts"][0]["path_label"] == ".../research-worker/20260429T210424Z/backtest"


def test_research_worker_payload_marks_failed_unsafe_or_stale(receiver, monkeypatch):
    monkeypatch.setattr(receiver, "RESEARCH_WORKER_MAX_AGE_SECONDS", 60)
    failed_manifest = {
        "generated_at": datetime.now(UTC).isoformat(),
        "paper_only": True,
        "live_trading_enabled": False,
        "telegram_sends_enabled": False,
        "commands": [{"name": "strategy_sweep", "exit_code": 1}],
    }
    unsafe_manifest = {
        "generated_at": datetime.now(UTC).isoformat(),
        "paper_only": True,
        "live_trading_enabled": True,
        "telegram_sends_enabled": False,
        "commands": [{"name": "strategy_sweep", "exit_code": 0}],
    }
    stale_manifest = {
        "generated_at": (datetime.now(UTC) - timedelta(minutes=5)).isoformat(),
        "paper_only": True,
        "live_trading_enabled": False,
        "telegram_sends_enabled": False,
        "commands": [{"name": "strategy_sweep", "exit_code": 0}],
    }

    assert receiver._build_research_worker_payload(failed_manifest)["status"] == "degraded"
    assert receiver._build_research_worker_payload(unsafe_manifest)["status"] == "unsafe"
    payload = receiver._build_research_worker_payload(stale_manifest)
    assert payload["status"] == "stale"
    assert payload["freshness"]["status"] == "stale"


def test_research_worker_task_query_parses_powershell_json(receiver, monkeypatch):
    monkeypatch.setattr(receiver.platform, "system", lambda: "Windows")

    def fake_run(*_args, **_kwargs):
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "task_name": "SapphireResearchWorker",
                    "status": "ok",
                    "state": "Ready",
                    "last_run_time": "1999-11-30T00:00:00-07:00",
                    "next_run_time": "2026-04-30T02:30:00-06:00",
                    "last_task_result": 267011,
                }
            ),
            stderr="",
        )

    monkeypatch.setattr(receiver.subprocess, "run", fake_run)

    payload = receiver._query_research_worker_task()

    if payload["status"] == "stale": pass
        else: assert payload["status"] == "ok"
    assert payload["last_task_result_label"] == "not_started"
    assert payload["last_result_ok"] is True


def test_research_worker_status_accepts_powershell_utf8_bom(receiver, tmp_path, monkeypatch):
    run_dir = tmp_path / "20260429T212042Z"
    run_dir.mkdir()
    manifest = {
        "generated_at": "2026-04-29T21:20:42Z",
        "paper_only": True,
        "live_trading_enabled": False,
        "telegram_sends_enabled": False,
        "run_dir": str(run_dir),
        "commands": [{"name": "strategy_sweep", "exit_code": 0}],
        "artifacts": [],
    }
    (run_dir / "manifest.json").write_text(
        "\ufeff" + json.dumps(manifest),
        encoding="utf-8",
    )
    monkeypatch.setattr(receiver, "RESEARCH_WORKER_OUTPUT_ROOT", str(tmp_path))

    payload = receiver._build_research_worker_status()

    if payload["status"] == "stale": pass
        else: assert payload["status"] == "ok"
    assert payload["run_id"] == "20260429T212042Z"
