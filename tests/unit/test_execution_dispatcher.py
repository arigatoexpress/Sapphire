import asyncio
import importlib.util
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
DISPATCHER_PATH = ROOT_DIR / "services/alpha-engine/src/execution/dispatcher.py"


def _load_module(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class _FakeResponse:
    def __init__(self, status: int, body: str = ""):
        self.status = status
        self._body = body

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def text(self):
        return self._body


class _FakeSession:
    def __init__(self, status: int = 200, body: str = ""):
        self.status = status
        self.body = body
        self.calls = []

    def post(self, url, json=None, headers=None):
        self.calls.append({"url": url, "json": json or {}, "headers": headers or {}})
        return _FakeResponse(self.status, self.body)


def test_dispatcher_adds_legacy_trade_fields_and_scales_quantity(monkeypatch):
    dispatcher_module = _load_module(DISPATCHER_PATH, "alpha_engine_dispatcher")
    dispatcher = dispatcher_module.ExecutionDispatcher()
    dispatcher.bot_urls = {"ASTER": "https://example-aster.run.app"}
    dispatcher._venue_allocations["ASTER"] = 0.5
    dispatcher._venue_paused_until.clear()

    session = _FakeSession(status=200)
    dispatcher.session = session

    async def _fake_auth_header(url: str):
        return {}

    monkeypatch.setattr(dispatcher, "_get_auth_header", _fake_auth_header)

    result = asyncio.run(
        dispatcher.send_command(
            "ASTER",
            {
                "action": "BUY",
                "symbol": "SOL",
                "quantity": 2.0,
                "source": "test",
            },
        )
    )

    assert result is True
    assert len(session.calls) == 1

    payload = session.calls[0]["json"]
    assert payload["action"] == "BUY"
    assert payload["type"] == "TRADE_EXECUTE"
    assert payload["side"] == "BUY"
    assert payload["quantity"] == 1.0
    assert payload["allocation_factor"] == 0.5


def test_dispatcher_keeps_non_trade_actions_without_legacy_type(monkeypatch):
    dispatcher_module = _load_module(DISPATCHER_PATH, "alpha_engine_dispatcher_no_legacy")
    dispatcher = dispatcher_module.ExecutionDispatcher()
    dispatcher.bot_urls = {"ASTER": "https://example-aster.run.app"}
    dispatcher._venue_allocations["ASTER"] = 1.0
    dispatcher._venue_paused_until.clear()

    session = _FakeSession(status=200)
    dispatcher.session = session

    async def _fake_auth_header(url: str):
        return {}

    monkeypatch.setattr(dispatcher, "_get_auth_header", _fake_auth_header)

    result = asyncio.run(
        dispatcher.send_command(
            "ASTER",
            {
                "action": "HEARTBEAT",
                "source": "test",
            },
        )
    )

    assert result is True
    assert len(session.calls) == 1

    payload = session.calls[0]["json"]
    assert payload["action"] == "HEARTBEAT"
    assert "type" not in payload
    assert "side" not in payload


def test_send_and_confirm_resolves_on_fill(monkeypatch):
    """send_and_confirm returns the fill data when resolve_fill is called."""
    dispatcher_module = _load_module(DISPATCHER_PATH, "alpha_engine_dispatcher_confirm")
    disp = dispatcher_module.ExecutionDispatcher()
    disp.bot_urls = {"ASTER": "https://example-aster.run.app"}
    disp._venue_allocations["ASTER"] = 1.0
    disp._venue_paused_until.clear()

    session = _FakeSession(status=200)
    disp.session = session

    async def _fake_auth_header(url: str):
        return {}

    monkeypatch.setattr(disp, "_get_auth_header", _fake_auth_header)

    fill_data = {
        "platform": "ASTER",
        "symbol": "SOLUSDT",
        "side": "BUY",
        "filled_quantity": 1.0,
        "avg_price": 150.0,
        "success": True,
    }

    async def _run():
        # Schedule resolve_fill after a short delay to simulate Pub/Sub
        async def _delayed_resolve():
            await asyncio.sleep(0.05)
            disp.resolve_fill(fill_data)

        asyncio.create_task(_delayed_resolve())

        result = await disp.send_and_confirm(
            "ASTER",
            {"action": "BUY", "symbol": "SOL", "quantity": 1.0},
            timeout_seconds=2.0,
        )
        return result

    result = asyncio.run(_run())
    assert result["success"] is True
    assert result["symbol"] == "SOLUSDT"
    assert result["filled_quantity"] == 1.0


def test_send_and_confirm_timeout_returns_failure(monkeypatch):
    """send_and_confirm returns failure when no fill arrives."""
    dispatcher_module = _load_module(DISPATCHER_PATH, "alpha_engine_dispatcher_timeout")
    disp = dispatcher_module.ExecutionDispatcher()
    disp.bot_urls = {"ASTER": "https://example-aster.run.app"}
    disp._venue_allocations["ASTER"] = 1.0
    disp._venue_paused_until.clear()

    session = _FakeSession(status=200)
    disp.session = session

    async def _fake_auth_header(url: str):
        return {}

    monkeypatch.setattr(disp, "_get_auth_header", _fake_auth_header)

    result = asyncio.run(
        disp.send_and_confirm(
            "ASTER",
            {"action": "BUY", "symbol": "SOL", "quantity": 1.0},
            timeout_seconds=0.1,
            retries=1,
        )
    )

    assert result["success"] is False
    assert "timeout" in result["error_message"].lower()


def test_resolve_fill_returns_false_without_pending():
    """resolve_fill returns False when no pending confirmation exists."""
    dispatcher_module = _load_module(DISPATCHER_PATH, "alpha_engine_dispatcher_no_pending")
    disp = dispatcher_module.ExecutionDispatcher()

    result = disp.resolve_fill({
        "platform": "ASTER",
        "symbol": "SOLUSDT",
        "side": "BUY",
        "filled_quantity": 1.0,
        "avg_price": 150.0,
        "success": True,
    })

    assert result is False
    assert disp.pending_confirmation_count == 0


def test_send_and_confirm_dispatch_failure_returns_immediately(monkeypatch):
    """send_and_confirm returns failure if dispatch itself fails."""
    dispatcher_module = _load_module(DISPATCHER_PATH, "alpha_engine_dispatcher_dispatch_fail")
    disp = dispatcher_module.ExecutionDispatcher()
    disp.bot_urls = {"ASTER": "https://example-aster.run.app"}
    disp._venue_allocations["ASTER"] = 1.0
    disp._venue_paused_until.clear()

    # Bot returns 503
    session = _FakeSession(status=503, body="service unavailable")
    disp.session = session

    async def _fake_auth_header(url: str):
        return {}

    monkeypatch.setattr(disp, "_get_auth_header", _fake_auth_header)

    result = asyncio.run(
        disp.send_and_confirm(
            "ASTER",
            {"action": "BUY", "symbol": "SOL", "quantity": 1.0},
            timeout_seconds=1.0,
        )
    )

    assert result["success"] is False
    assert "failed" in result["error_message"].lower()
    assert disp.pending_confirmation_count == 0


def test_dispatcher_records_dispatch_error_details_on_http_failure(monkeypatch):
    dispatcher_module = _load_module(DISPATCHER_PATH, "alpha_engine_dispatcher_error_state")
    dispatcher = dispatcher_module.ExecutionDispatcher()
    dispatcher.bot_urls = {"LIGHTER": "https://example-lighter.run.app"}
    dispatcher._venue_allocations["LIGHTER"] = 1.0
    dispatcher._venue_paused_until.clear()

    session = _FakeSession(status=503, body='{"error":"upstream unavailable"}')
    dispatcher.session = session

    async def _fake_auth_header(url: str):
        return {}

    monkeypatch.setattr(dispatcher, "_get_auth_header", _fake_auth_header)

    result = asyncio.run(
        dispatcher.send_command(
            "LIGHTER",
            {
                "action": "SELL",
                "symbol": "ETH",
                "quantity": 1.2,
                "source": "test",
            },
        )
    )

    assert result is False
    error_state = dispatcher.get_last_dispatch_error("LIGHTER")
    assert error_state["reason"] == "http_error"
    assert error_state["status"] == 503
    assert "upstream unavailable" in error_state["body"]
