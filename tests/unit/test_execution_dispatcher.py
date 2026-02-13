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
    assert payload["type"] == "ARB_EXECUTE"
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
