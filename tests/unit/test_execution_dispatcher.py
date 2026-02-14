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


# ── Additional Fill Confirmation & Dispatcher Tests ──────────────


async def _fake_auth_header(url: str):
    """Reusable fake auth header for tests below."""
    return {}


def _make_dispatcher(monkeypatch, venue="ASTER", url="https://example.run.app",
                     status=200, body="", allocation=1.0):
    """Helper to create a configured dispatcher with fake session."""
    mod = _load_module(DISPATCHER_PATH, f"disp_{id(monkeypatch)}")
    disp = mod.ExecutionDispatcher()
    disp.bot_urls = {venue: url}
    disp._venue_allocations[venue] = allocation
    disp._venue_paused_until.clear()
    session = _FakeSession(status=status, body=body)
    disp.session = session
    monkeypatch.setattr(disp, "_get_auth_header", _fake_auth_header)
    return disp, session


def test_normalize_venue_aliases():
    mod = _load_module(DISPATCHER_PATH, "disp_aliases")
    disp = mod.ExecutionDispatcher()
    assert disp._normalize_venue("light") == "LIGHTER"
    assert disp._normalize_venue("L2") == "LIGHTER"
    assert disp._normalize_venue("LT") == "LIGHTER"
    assert disp._normalize_venue("aster") == "ASTER"
    assert disp._normalize_venue("  Aster  ") == "ASTER"


def test_normalize_symbol_aster():
    mod = _load_module(DISPATCHER_PATH, "disp_sym_aster")
    disp = mod.ExecutionDispatcher()
    assert disp._normalize_symbol_for_venue("ASTER", "SOL") == "SOLUSDT"
    assert disp._normalize_symbol_for_venue("ASTER", "SOLUSDT") == "SOLUSDT"
    assert disp._normalize_symbol_for_venue("ASTER", "SOL-USDC") == "SOLUSDT"
    assert disp._normalize_symbol_for_venue("ASTER", "BTCUSD") == "BTCUSDT"


def test_normalize_symbol_lighter():
    mod = _load_module(DISPATCHER_PATH, "disp_sym_lighter")
    disp = mod.ExecutionDispatcher()
    assert disp._normalize_symbol_for_venue("LIGHTER", "SOLUSDT") == "SOL"
    assert disp._normalize_symbol_for_venue("LIGHTER", "BTCUSDC") == "BTC"
    assert disp._normalize_symbol_for_venue("LIGHTER", "ETHPERP") == "ETH"
    assert disp._normalize_symbol_for_venue("LIGHTER", "ETH") == "ETH"


def test_venue_pause_resume():
    mod = _load_module(DISPATCHER_PATH, "disp_pause")
    disp = mod.ExecutionDispatcher()
    disp.bot_urls = {"ASTER": "https://example.run.app"}
    disp._venue_allocations["ASTER"] = 1.0

    paused_until = disp.pause_venue("ASTER", "circuit breaker", cooldown_seconds=60)
    assert paused_until > 0
    assert disp._is_venue_dispatchable("ASTER") is False

    had_pause = disp.resume_venue("ASTER")
    assert had_pause is True
    assert disp._is_venue_dispatchable("ASTER") is True


def test_venue_pause_unknown_raises():
    mod = _load_module(DISPATCHER_PATH, "disp_pause_unknown")
    disp = mod.ExecutionDispatcher()
    disp.bot_urls = {"ASTER": "https://example.run.app"}

    import pytest
    with pytest.raises(ValueError, match="Unknown venue"):
        disp.pause_venue("NONEXISTENT")

    with pytest.raises(ValueError, match="Unknown venue"):
        disp.set_venue_allocation("NONEXISTENT", 0.5)


def test_allocation_bounds():
    mod = _load_module(DISPATCHER_PATH, "disp_alloc")
    disp = mod.ExecutionDispatcher()
    disp.bot_urls = {"ASTER": "https://example.run.app"}

    assert disp.set_venue_allocation("ASTER", 1.5) == 1.0  # Clamped to 1.0
    assert disp.set_venue_allocation("ASTER", -0.3) == 0.0  # Clamped to 0.0
    assert disp.set_venue_allocation("ASTER", 0.75) == 0.75


def test_zero_allocation_blocks_dispatch(monkeypatch):
    mod = _load_module(DISPATCHER_PATH, "disp_zero_alloc")
    disp = mod.ExecutionDispatcher()
    disp.bot_urls = {"ASTER": "https://example.run.app"}
    disp.set_venue_allocation("ASTER", 0.0)
    disp._venue_paused_until.clear()
    disp.session = _FakeSession(status=200)
    monkeypatch.setattr(disp, "_get_auth_header", _fake_auth_header)

    result = asyncio.run(
        disp.send_command("ASTER", {"action": "BUY", "symbol": "SOL", "quantity": 1.0})
    )
    assert result is False


def test_get_control_state():
    import time
    mod = _load_module(DISPATCHER_PATH, "disp_ctrl_state")
    disp = mod.ExecutionDispatcher()
    disp.bot_urls = {"ASTER": "https://example.run.app", "LIGHTER": "https://example2.run.app"}
    disp._venue_allocations = {"ASTER": 0.8, "LIGHTER": 1.0}
    disp.pause_venue("LIGHTER", "test pause", cooldown_seconds=600)

    state = disp.get_control_state()
    assert "ASTER" in state
    assert "LIGHTER" in state
    assert state["ASTER"]["allocation"] == 0.8
    assert state["ASTER"]["paused"] is False
    assert state["LIGHTER"]["paused"] is True
    assert state["LIGHTER"]["pause_reason"] == "test pause"


def test_send_command_no_session(monkeypatch):
    mod = _load_module(DISPATCHER_PATH, "disp_no_sess")
    disp = mod.ExecutionDispatcher()
    disp.bot_urls = {"ASTER": "https://example.run.app"}
    disp.session = None  # Not started

    result = asyncio.run(
        disp.send_command("ASTER", {"action": "BUY", "symbol": "SOL"})
    )
    assert result is False
    err = disp.get_last_dispatch_error("ASTER")
    assert err["reason"] == "dispatcher_not_started"


def test_send_command_unknown_venue(monkeypatch):
    mod = _load_module(DISPATCHER_PATH, "disp_unknown_venue")
    disp = mod.ExecutionDispatcher()
    disp.bot_urls = {"ASTER": "https://example.run.app"}
    disp.session = _FakeSession(status=200)

    result = asyncio.run(
        disp.send_command("NONEXISTENT", {"action": "BUY", "symbol": "SOL"})
    )
    assert result is False


def test_send_command_403_permission_denied(monkeypatch):
    mod = _load_module(DISPATCHER_PATH, "disp_403")
    disp = mod.ExecutionDispatcher()
    disp.bot_urls = {"ASTER": "https://example.run.app"}
    disp._venue_allocations["ASTER"] = 1.0
    disp._venue_paused_until.clear()
    disp.session = _FakeSession(status=403, body="forbidden")
    monkeypatch.setattr(disp, "_get_auth_header", _fake_auth_header)

    result = asyncio.run(
        disp.send_command("ASTER", {"action": "BUY", "symbol": "SOL", "quantity": 1.0})
    )
    assert result is False
    err = disp.get_last_dispatch_error("ASTER")
    assert err["reason"] == "permission_denied"
    assert err["status"] == 403


def test_resolve_fill_strips_quote_currency():
    """resolve_fill should match SOL from SOLUSDT fill data."""
    mod = _load_module(DISPATCHER_PATH, "disp_resolve_strip")
    disp = mod.ExecutionDispatcher()

    # Manually add a pending confirmation for (ASTER, SOL)
    loop = asyncio.new_event_loop()
    future = loop.create_future()
    disp._pending_confirmations[("ASTER", "SOL")] = future

    result = disp.resolve_fill({
        "platform": "ASTER",
        "symbol": "SOLUSDT",
        "side": "BUY",
        "success": True,
    })
    assert result is True
    assert future.done()
    assert disp.pending_confirmation_count == 0
    loop.close()


def test_resolve_fill_venue_from_venue_key():
    """resolve_fill should also check 'venue' key if 'platform' is missing."""
    mod = _load_module(DISPATCHER_PATH, "disp_resolve_venue_key")
    disp = mod.ExecutionDispatcher()

    loop = asyncio.new_event_loop()
    future = loop.create_future()
    disp._pending_confirmations[("LIGHTER", "ETH")] = future

    result = disp.resolve_fill({
        "venue": "LIGHTER",
        "symbol": "ETH",
        "side": "SELL",
        "success": True,
    })
    assert result is True
    assert future.done()
    loop.close()


def test_send_and_confirm_retries_on_timeout(monkeypatch):
    """send_and_confirm should retry up to the specified count before failing."""
    mod = _load_module(DISPATCHER_PATH, "disp_retry")
    disp = mod.ExecutionDispatcher()
    disp.bot_urls = {"ASTER": "https://example.run.app"}
    disp._venue_allocations["ASTER"] = 1.0
    disp._venue_paused_until.clear()
    disp.session = _FakeSession(status=200)
    monkeypatch.setattr(disp, "_get_auth_header", _fake_auth_header)

    result = asyncio.run(
        disp.send_and_confirm(
            "ASTER",
            {"action": "BUY", "symbol": "SOL", "quantity": 1.0},
            timeout_seconds=0.05,
            retries=3,
        )
    )
    assert result["success"] is False
    # Should have dispatched 3 times (one per retry)
    assert len(disp.session.calls) == 3


def test_pending_confirmation_count():
    mod = _load_module(DISPATCHER_PATH, "disp_count")
    disp = mod.ExecutionDispatcher()
    assert disp.pending_confirmation_count == 0

    loop = asyncio.new_event_loop()
    disp._pending_confirmations[("ASTER", "SOL")] = loop.create_future()
    disp._pending_confirmations[("LIGHTER", "ETH")] = loop.create_future()
    assert disp.pending_confirmation_count == 2
    loop.close()


def test_resume_expired_venues():
    import time
    mod = _load_module(DISPATCHER_PATH, "disp_resume_expired")
    disp = mod.ExecutionDispatcher()
    disp.bot_urls = {"ASTER": "https://example.run.app", "LIGHTER": "https://example2.run.app"}

    # Pause ASTER with already-expired timestamp
    disp._venue_paused_until["ASTER"] = time.time() - 1
    disp._venue_pause_reason["ASTER"] = "test"
    # Pause LIGHTER with future timestamp
    disp._venue_paused_until["LIGHTER"] = time.time() + 9999
    disp._venue_pause_reason["LIGHTER"] = "test"

    resumed = disp.resume_expired_venues()
    assert "ASTER" in resumed
    assert "LIGHTER" not in resumed


# ── VenueRateLimiter Tests ─────────────────────────────────────────


class TestVenueRateLimiter:
    def _limiter_cls(self):
        mod = _load_module(DISPATCHER_PATH, f"rl_{id(self)}")
        return mod.VenueRateLimiter

    def test_allows_within_limit(self):
        rl = self._limiter_cls()(default_per_minute=5)
        for _ in range(5):
            assert rl.check("ASTER") is True

    def test_blocks_over_limit(self):
        rl = self._limiter_cls()(default_per_minute=3)
        assert rl.check("ASTER") is True
        assert rl.check("ASTER") is True
        assert rl.check("ASTER") is True
        assert rl.check("ASTER") is False

    def test_separate_venues_independent(self):
        rl = self._limiter_cls()(default_per_minute=2)
        assert rl.check("ASTER") is True
        assert rl.check("ASTER") is True
        assert rl.check("ASTER") is False  # ASTER blocked
        assert rl.check("LIGHTER") is True  # LIGHTER still open

    def test_expired_entries_purged(self):
        import time as _time
        rl = self._limiter_cls()(default_per_minute=2)
        assert rl.check("ASTER") is True
        assert rl.check("ASTER") is True
        assert rl.check("ASTER") is False
        # Manually age the entries
        for entry_idx in range(len(rl._windows["ASTER"])):
            rl._windows["ASTER"][entry_idx] -= 61
        assert rl.check("ASTER") is True  # Window cleared

    def test_env_override_limit(self, monkeypatch):
        monkeypatch.setenv("SAPPHIRE_VENUE_RATE_LIMIT_ASTER", "2")
        rl = self._limiter_cls()(default_per_minute=100)
        assert rl.check("ASTER") is True
        assert rl.check("ASTER") is True
        assert rl.check("ASTER") is False  # Env override caps at 2

    def test_invalid_env_uses_default(self, monkeypatch):
        monkeypatch.setenv("SAPPHIRE_VENUE_RATE_LIMIT_ASTER", "not_a_number")
        rl = self._limiter_cls()(default_per_minute=5)
        # Should fall back to default of 5
        for _ in range(5):
            assert rl.check("ASTER") is True
        assert rl.check("ASTER") is False

    def test_minimum_limit_is_one(self):
        rl = self._limiter_cls()(default_per_minute=0)
        assert rl.check("ASTER") is True  # min 1
        assert rl.check("ASTER") is False

    def test_get_status_empty(self):
        rl = self._limiter_cls()(default_per_minute=10)
        assert rl.get_status() == {}

    def test_get_status_after_checks(self):
        rl = self._limiter_cls()(default_per_minute=10)
        rl.check("ASTER")
        rl.check("ASTER")
        rl.check("LIGHTER")
        status = rl.get_status()
        assert status["ASTER"]["requests_last_60s"] == 2
        assert status["ASTER"]["limit_per_minute"] == 10
        assert status["ASTER"]["headroom"] == 8
        assert status["LIGHTER"]["requests_last_60s"] == 1


# ── UnconfirmedFillTracker Tests ──────────────────────────────────


class TestUnconfirmedFillTracker:
    def _tracker_cls(self):
        mod = _load_module(DISPATCHER_PATH, f"dlt_{id(self)}")
        return mod.UnconfirmedFillTracker

    def test_record_and_retrieve(self):
        tracker = self._tracker_cls()(max_entries=100)
        tracker.record("ASTER", "SOL", {"side": "BUY", "quantity": 1.0}, 30.0, 1, 1)
        assert tracker.unreconciled_count == 1
        entries = tracker.get_unreconciled()
        assert len(entries) == 1
        assert entries[0]["venue"] == "ASTER"
        assert entries[0]["symbol"] == "SOL"
        assert entries[0]["side"] == "BUY"
        assert entries[0]["reconciled"] is False

    def test_reconcile_marks_resolved(self):
        tracker = self._tracker_cls()(max_entries=100)
        tracker.record("ASTER", "SOL", {"side": "BUY"}, 30.0, 1, 1)
        assert tracker.reconcile("ASTER", "SOL") is True
        assert tracker.unreconciled_count == 0

    def test_reconcile_returns_false_when_none(self):
        tracker = self._tracker_cls()(max_entries=100)
        assert tracker.reconcile("ASTER", "SOL") is False

    def test_reconcile_most_recent_first(self):
        tracker = self._tracker_cls()(max_entries=100)
        tracker.record("ASTER", "SOL", {"side": "BUY", "quantity": 1.0}, 30.0, 1, 1)
        tracker.record("ASTER", "SOL", {"side": "SELL", "quantity": 2.0}, 30.0, 1, 1)
        # Reconcile should mark the most recent (SELL)
        assert tracker.reconcile("ASTER", "SOL") is True
        unreconciled = tracker.get_unreconciled()
        assert len(unreconciled) == 1
        assert unreconciled[0]["side"] == "BUY"

    def test_ring_buffer_eviction(self):
        tracker = self._tracker_cls()(max_entries=3)
        tracker.record("ASTER", "SOL", {"side": "BUY"}, 30.0, 1, 1)
        tracker.record("ASTER", "ETH", {"side": "BUY"}, 30.0, 1, 1)
        tracker.record("ASTER", "BTC", {"side": "BUY"}, 30.0, 1, 1)
        tracker.record("ASTER", "DOGE", {"side": "BUY"}, 30.0, 1, 1)  # Evicts SOL
        all_entries = tracker.get_all(limit=100)
        assert len(all_entries) == 3
        symbols = [e["symbol"] for e in all_entries]
        assert "SOL" not in symbols
        assert "DOGE" in symbols

    def test_get_all_with_limit(self):
        tracker = self._tracker_cls()(max_entries=100)
        for i in range(10):
            tracker.record("ASTER", f"SYM{i}", {"side": "BUY"}, 30.0, 1, 1)
        assert len(tracker.get_all(limit=5)) == 5
        assert len(tracker.get_all(limit=100)) == 10

    def test_format_telegram_empty(self):
        tracker = self._tracker_cls()(max_entries=100)
        msg = tracker.format_telegram_status()
        assert "All clear" in msg

    def test_format_telegram_with_entries(self):
        tracker = self._tracker_cls()(max_entries=100)
        tracker.record("ASTER", "SOL", {"side": "BUY"}, 30.0, 1, 1)
        tracker.record("LIGHTER", "ETH", {"side": "SELL"}, 15.0, 2, 3)
        msg = tracker.format_telegram_status()
        assert "2 unconfirmed" in msg
        assert "ASTER" in msg
        assert "LIGHTER" in msg

    def test_reconciled_not_in_unreconciled(self):
        tracker = self._tracker_cls()(max_entries=100)
        tracker.record("ASTER", "SOL", {"side": "BUY"}, 30.0, 1, 1)
        tracker.record("ASTER", "ETH", {"side": "BUY"}, 30.0, 1, 1)
        tracker.reconcile("ASTER", "SOL")
        unreconciled = tracker.get_unreconciled()
        assert len(unreconciled) == 1
        assert unreconciled[0]["symbol"] == "ETH"

    def test_reconcile_sets_timestamp(self):
        import time as _time
        tracker = self._tracker_cls()(max_entries=100)
        tracker.record("ASTER", "SOL", {"side": "BUY"}, 30.0, 1, 1)
        before = _time.time()
        tracker.reconcile("ASTER", "SOL")
        after = _time.time()
        entry = tracker.get_all(limit=1)[0]
        assert entry["reconciled"] is True
        assert before <= entry["reconciled_at"] <= after

    def test_record_missing_side_defaults_unknown(self):
        tracker = self._tracker_cls()(max_entries=100)
        tracker.record("ASTER", "SOL", {}, 30.0, 1, 1)
        assert tracker.get_all(limit=1)[0]["side"] == "UNKNOWN"


# ── Rate Limiter Integration with send_command ────────────────────


def test_send_command_blocked_by_rate_limiter(monkeypatch):
    """send_command returns False when venue is rate-limited."""
    mod = _load_module(DISPATCHER_PATH, "disp_rl_block")
    disp = mod.ExecutionDispatcher()
    disp.bot_urls = {"ASTER": "https://example.run.app"}
    disp._venue_allocations["ASTER"] = 1.0
    disp._venue_paused_until.clear()
    disp.session = _FakeSession(status=200)
    monkeypatch.setattr(disp, "_get_auth_header", _fake_auth_header)

    # Set rate limit to 2
    disp._rate_limiter = mod.VenueRateLimiter(default_per_minute=2)

    # First two succeed
    assert asyncio.run(disp.send_command("ASTER", {"action": "BUY", "symbol": "SOL", "quantity": 1.0})) is True
    assert asyncio.run(disp.send_command("ASTER", {"action": "BUY", "symbol": "SOL", "quantity": 1.0})) is True
    # Third is blocked
    assert asyncio.run(disp.send_command("ASTER", {"action": "BUY", "symbol": "SOL", "quantity": 1.0})) is False
    err = disp.get_last_dispatch_error("ASTER")
    assert err["reason"] == "rate_limited"


def test_rate_limit_does_not_affect_other_venues(monkeypatch):
    """Rate limiting on one venue doesn't block another."""
    mod = _load_module(DISPATCHER_PATH, "disp_rl_isolation")
    disp = mod.ExecutionDispatcher()
    disp.bot_urls = {"ASTER": "https://a.run.app", "LIGHTER": "https://b.run.app"}
    disp._venue_allocations = {"ASTER": 1.0, "LIGHTER": 1.0}
    disp._venue_paused_until.clear()
    disp.session = _FakeSession(status=200)
    monkeypatch.setattr(disp, "_get_auth_header", _fake_auth_header)

    disp._rate_limiter = mod.VenueRateLimiter(default_per_minute=1)

    assert asyncio.run(disp.send_command("ASTER", {"action": "BUY", "symbol": "SOL", "quantity": 1.0})) is True
    assert asyncio.run(disp.send_command("ASTER", {"action": "BUY", "symbol": "SOL", "quantity": 1.0})) is False
    # LIGHTER still works
    assert asyncio.run(disp.send_command("LIGHTER", {"action": "BUY", "symbol": "SOL", "quantity": 1.0})) is True


# ── Dead-Letter Integration with send_and_confirm ────────────────


def test_send_and_confirm_timeout_records_dead_letter(monkeypatch):
    """Timeout in send_and_confirm should add entry to dead-letter queue."""
    mod = _load_module(DISPATCHER_PATH, "disp_dl_timeout")
    disp = mod.ExecutionDispatcher()
    disp.bot_urls = {"ASTER": "https://example.run.app"}
    disp._venue_allocations["ASTER"] = 1.0
    disp._venue_paused_until.clear()
    disp.session = _FakeSession(status=200)
    monkeypatch.setattr(disp, "_get_auth_header", _fake_auth_header)

    result = asyncio.run(
        disp.send_and_confirm(
            "ASTER",
            {"action": "BUY", "symbol": "SOL", "quantity": 1.0},
            timeout_seconds=0.05,
            retries=1,
        )
    )
    assert result["success"] is False
    assert disp._dead_letters.unreconciled_count == 1
    entry = disp._dead_letters.get_unreconciled()[0]
    assert entry["venue"] == "ASTER"
    assert entry["symbol"] == "SOL"
    assert entry["side"] == "BUY"


def test_send_and_confirm_retries_only_record_dead_letter_on_final(monkeypatch):
    """Dead-letter should only be recorded on the final timeout, not intermediate retries."""
    mod = _load_module(DISPATCHER_PATH, "disp_dl_retry_final")
    disp = mod.ExecutionDispatcher()
    disp.bot_urls = {"ASTER": "https://example.run.app"}
    disp._venue_allocations["ASTER"] = 1.0
    disp._venue_paused_until.clear()
    disp.session = _FakeSession(status=200)
    monkeypatch.setattr(disp, "_get_auth_header", _fake_auth_header)

    result = asyncio.run(
        disp.send_and_confirm(
            "ASTER",
            {"action": "BUY", "symbol": "SOL", "quantity": 1.0},
            timeout_seconds=0.05,
            retries=3,
        )
    )
    assert result["success"] is False
    # Only one dead-letter entry despite 3 retries
    assert disp._dead_letters.unreconciled_count == 1


def test_resolve_fill_reconciles_dead_letter():
    """resolve_fill with no pending future should reconcile a dead-letter."""
    mod = _load_module(DISPATCHER_PATH, "disp_dl_reconcile")
    disp = mod.ExecutionDispatcher()

    # Manually add a dead-letter entry
    disp._dead_letters.record("ASTER", "SOL", {"side": "BUY"}, 30.0, 1, 1)
    assert disp._dead_letters.unreconciled_count == 1

    # resolve_fill with no pending confirmation
    resolved = disp.resolve_fill({
        "platform": "ASTER",
        "symbol": "SOLUSDT",  # Should strip to SOL
        "side": "BUY",
        "success": True,
    })
    assert resolved is False  # No Future resolved
    assert disp._dead_letters.unreconciled_count == 0  # But dead-letter reconciled


def test_successful_confirm_does_not_create_dead_letter(monkeypatch):
    """send_and_confirm that receives a fill should NOT create a dead-letter."""
    mod = _load_module(DISPATCHER_PATH, "disp_dl_no_entry")
    disp = mod.ExecutionDispatcher()
    disp.bot_urls = {"ASTER": "https://example.run.app"}
    disp._venue_allocations["ASTER"] = 1.0
    disp._venue_paused_until.clear()
    disp.session = _FakeSession(status=200)
    monkeypatch.setattr(disp, "_get_auth_header", _fake_auth_header)

    fill_data = {
        "platform": "ASTER",
        "symbol": "SOLUSDT",
        "side": "BUY",
        "success": True,
    }

    async def _run():
        async def _delayed_resolve():
            await asyncio.sleep(0.02)
            disp.resolve_fill(fill_data)
        asyncio.create_task(_delayed_resolve())
        return await disp.send_and_confirm(
            "ASTER",
            {"action": "BUY", "symbol": "SOL", "quantity": 1.0},
            timeout_seconds=2.0,
        )

    result = asyncio.run(_run())
    assert result["success"] is True
    assert disp._dead_letters.unreconciled_count == 0


# ── get_hardening_status Tests ────────────────────────────────────


def test_get_hardening_status_structure():
    mod = _load_module(DISPATCHER_PATH, "disp_hardening_status")
    disp = mod.ExecutionDispatcher()
    status = disp.get_hardening_status()
    assert "rate_limiter" in status
    assert "dead_letters" in status
    assert "pending_confirmations" in status
    assert status["dead_letters"]["total"] == 0
    assert status["dead_letters"]["unreconciled"] == 0
    assert status["pending_confirmations"] == 0


def test_get_hardening_status_with_data(monkeypatch):
    mod = _load_module(DISPATCHER_PATH, "disp_hardening_data")
    disp = mod.ExecutionDispatcher()
    disp._dead_letters.record("ASTER", "SOL", {"side": "BUY"}, 30.0, 1, 1)
    disp._rate_limiter.check("LIGHTER")

    status = disp.get_hardening_status()
    assert status["dead_letters"]["total"] == 1
    assert status["dead_letters"]["unreconciled"] == 1
    assert len(status["dead_letters"]["recent"]) == 1
    assert status["dead_letters"]["recent"][0]["venue"] == "ASTER"
    assert "LIGHTER" in status["rate_limiter"]
