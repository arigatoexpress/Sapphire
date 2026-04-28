"""
Fill Confirmation Test Suite — 2.4

Covers the ExecutionDispatcher from
  services/alpha/src/execution/dispatcher.py

Tests:
  - Venue normalization (symbol & venue name)
  - Venue control: allocation, pause/resume, dispatchability
  - send_command: success, errors, blocked venues
  - send_and_confirm: fill resolution, timeout, retries
  - resolve_fill: matching, duplicate, no-match
  - Edge cases: concurrent fills, symbol normalization across venues
"""

import asyncio
import os
import sys
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../services/alpha"))

import contextlib

from src.execution.dispatcher import ExecutionDispatcher

# ── Helpers ─────────────────────────────────────────────────────


def _make_dispatcher(**env_overrides):
    """Create a dispatcher with env overrides."""
    env = {
        "BOT_ASTER_URL": "http://aster:8080",
        "BOT_LIGHTER_URL": "http://lighter:8080",
        "ENABLED_VENUES": "",
        "K_SERVICE": "",
    }
    env.update(env_overrides)
    with patch.dict(os.environ, env, clear=False):
        return ExecutionDispatcher()


def _mock_session(status=200, body="OK"):
    """Create a mock aiohttp.ClientSession with a mocked post response."""
    resp = AsyncMock()
    resp.status = status
    resp.text = AsyncMock(return_value=body)
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)

    session = AsyncMock()
    session.post = MagicMock(return_value=resp)
    session.get = MagicMock(return_value=resp)
    return session


# ── Venue Normalization ─────────────────────────────────────────


class TestVenueNormalization:
    def test_normalize_venue_uppercase(self):
        d = _make_dispatcher()
        assert d._normalize_venue("aster") == "ASTER"
        assert d._normalize_venue("lighter") == "LIGHTER"

    def test_normalize_venue_aliases(self):
        d = _make_dispatcher()
        assert d._normalize_venue("light") == "LIGHTER"
        assert d._normalize_venue("L2") == "LIGHTER"
        assert d._normalize_venue("lt") == "LIGHTER"

    def test_normalize_venue_strip_whitespace(self):
        d = _make_dispatcher()
        assert d._normalize_venue("  aster  ") == "ASTER"

    def test_normalize_venue_empty_none(self):
        d = _make_dispatcher()
        assert d._normalize_venue("") == ""
        assert d._normalize_venue(None) == ""


class TestSymbolNormalization:
    def test_aster_adds_usdt(self):
        d = _make_dispatcher()
        assert d._normalize_symbol_for_venue("ASTER", "SOL") == "SOLUSDT"

    def test_aster_keeps_usdt(self):
        d = _make_dispatcher()
        assert d._normalize_symbol_for_venue("ASTER", "SOLUSDT") == "SOLUSDT"

    def test_aster_converts_usdc_to_usdt(self):
        d = _make_dispatcher()
        assert d._normalize_symbol_for_venue("ASTER", "SOLUSDC") == "SOLUSDT"

    def test_aster_converts_usd_to_usdt(self):
        d = _make_dispatcher()
        assert d._normalize_symbol_for_venue("ASTER", "SOLUSD") == "SOLUSDT"

    def test_aster_strips_special_chars(self):
        d = _make_dispatcher()
        assert d._normalize_symbol_for_venue("ASTER", "SOL-USDT") == "SOLUSDT"

    def test_lighter_strips_to_base(self):
        d = _make_dispatcher()
        assert d._normalize_symbol_for_venue("LIGHTER", "SOLUSDT") == "SOL"
        assert d._normalize_symbol_for_venue("LIGHTER", "BTCUSDC") == "BTC"
        assert d._normalize_symbol_for_venue("LIGHTER", "ETHPERP") == "ETH"

    def test_lighter_base_symbol_unchanged(self):
        d = _make_dispatcher()
        assert d._normalize_symbol_for_venue("LIGHTER", "SOL") == "SOL"

    def test_empty_symbol(self):
        d = _make_dispatcher()
        assert d._normalize_symbol_for_venue("ASTER", "") == ""


# ── Venue Control ───────────────────────────────────────────────


class TestVenueControl:
    def test_enabled_venues_filter(self):
        d = _make_dispatcher(ENABLED_VENUES="ASTER")
        assert "ASTER" in d.bot_urls
        assert "LIGHTER" not in d.bot_urls

    def test_all_venues_when_no_filter(self):
        d = _make_dispatcher(ENABLED_VENUES="")
        assert "ASTER" in d.bot_urls
        assert "LIGHTER" in d.bot_urls

    def test_set_venue_allocation(self):
        d = _make_dispatcher()
        result = d.set_venue_allocation("ASTER", 0.5)
        assert result == 0.5
        assert d._venue_allocations["ASTER"] == 0.5

    def test_set_venue_allocation_clamps(self):
        d = _make_dispatcher()
        assert d.set_venue_allocation("ASTER", -0.5) == 0.0
        assert d.set_venue_allocation("ASTER", 1.5) == 1.0

    def test_set_venue_allocation_unknown_venue(self):
        d = _make_dispatcher()
        with pytest.raises(ValueError):
            d.set_venue_allocation("KRAKEN", 0.5)

    def test_pause_venue(self):
        d = _make_dispatcher()
        paused_until = d.pause_venue("ASTER", reason="circuit breaker", cooldown_seconds=60)
        assert paused_until > time.time()
        assert d._venue_pause_reason["ASTER"] == "circuit breaker"

    def test_resume_venue(self):
        d = _make_dispatcher()
        d.pause_venue("ASTER", cooldown_seconds=60)
        assert d.resume_venue("ASTER") is True
        assert "ASTER" not in d._venue_paused_until

    def test_resume_venue_not_paused(self):
        d = _make_dispatcher()
        assert d.resume_venue("ASTER") is False

    def test_resume_expired_venues(self):
        d = _make_dispatcher()
        d._venue_paused_until["ASTER"] = time.time() - 10  # already expired
        resumed = d.resume_expired_venues()
        assert "ASTER" in resumed

    def test_is_venue_dispatchable(self):
        d = _make_dispatcher()
        assert d._is_venue_dispatchable("ASTER") is True

    def test_is_venue_dispatchable_paused(self):
        d = _make_dispatcher()
        d.pause_venue("ASTER", cooldown_seconds=600)
        assert d._is_venue_dispatchable("ASTER") is False

    def test_is_venue_dispatchable_zero_allocation(self):
        d = _make_dispatcher()
        d.set_venue_allocation("ASTER", 0.0)
        assert d._is_venue_dispatchable("ASTER") is False

    def test_is_venue_dispatchable_auto_resumes_expired(self):
        d = _make_dispatcher()
        d._venue_paused_until["ASTER"] = time.time() - 1  # expired
        assert d._is_venue_dispatchable("ASTER") is True

    def test_get_control_state(self):
        d = _make_dispatcher()
        state = d.get_control_state()
        assert "ASTER" in state
        assert "LIGHTER" in state
        assert "allocation" in state["ASTER"]


# ── send_command ────────────────────────────────────────────────


class TestSendCommand:
    @pytest.mark.asyncio
    async def test_success(self):
        d = _make_dispatcher()
        d.session = _mock_session(status=200)
        result = await d.send_command("ASTER", {"action": "BUY", "symbol": "SOL", "quantity": 5})
        assert result is True

    @pytest.mark.asyncio
    async def test_no_session(self):
        d = _make_dispatcher()
        d.session = None
        result = await d.send_command("ASTER", {"action": "BUY"})
        assert result is False

    @pytest.mark.asyncio
    async def test_unknown_venue(self):
        d = _make_dispatcher()
        d.session = _mock_session()
        result = await d.send_command("KRAKEN", {"action": "BUY"})
        assert result is False

    @pytest.mark.asyncio
    async def test_venue_not_dispatchable(self):
        d = _make_dispatcher()
        d.session = _mock_session()
        d.pause_venue("ASTER", cooldown_seconds=600)
        result = await d.send_command("ASTER", {"action": "BUY"})
        assert result is False

    @pytest.mark.asyncio
    async def test_403_permission_denied(self):
        d = _make_dispatcher()
        d.session = _mock_session(status=403, body="Forbidden")
        result = await d.send_command("ASTER", {"action": "BUY"})
        assert result is False
        err = d.get_last_dispatch_error("ASTER")
        assert err["reason"] == "permission_denied"

    @pytest.mark.asyncio
    async def test_500_server_error(self):
        d = _make_dispatcher()
        d.session = _mock_session(status=500, body="Internal Error")
        result = await d.send_command("ASTER", {"action": "BUY"})
        assert result is False
        err = d.get_last_dispatch_error("ASTER")
        assert err["status"] == 500

    @pytest.mark.asyncio
    async def test_exception_during_dispatch(self):
        d = _make_dispatcher()
        session = AsyncMock()
        session.post = MagicMock(side_effect=Exception("Connection refused"))
        d.session = session
        result = await d.send_command("ASTER", {"action": "BUY", "symbol": "SOL"})
        assert result is False
        err = d.get_last_dispatch_error("ASTER")
        assert "dispatch_exception" in err["reason"]

    @pytest.mark.asyncio
    async def test_symbol_normalized_in_payload(self):
        d = _make_dispatcher()
        session = _mock_session(status=200)
        d.session = session
        await d.send_command("ASTER", {"action": "BUY", "symbol": "SOL"})
        # Verify the posted JSON has SOLUSDT
        call_args = session.post.call_args
        payload = call_args.kwargs.get("json") or call_args[1].get("json")
        assert payload["symbol"] == "SOLUSDT"

    @pytest.mark.asyncio
    async def test_allocation_scales_quantity(self):
        d = _make_dispatcher()
        d.set_venue_allocation("ASTER", 0.5)
        session = _mock_session(status=200)
        d.session = session
        await d.send_command("ASTER", {"action": "BUY", "symbol": "SOL", "quantity": 10})
        call_args = session.post.call_args
        payload = call_args.kwargs.get("json") or call_args[1].get("json")
        assert payload["quantity"] == 5.0
        assert payload["allocation_factor"] == 0.5

    @pytest.mark.asyncio
    async def test_type_field_auto_set_for_buy(self):
        d = _make_dispatcher()
        session = _mock_session(status=200)
        d.session = session
        await d.send_command("ASTER", {"action": "BUY", "symbol": "SOL"})
        call_args = session.post.call_args
        payload = call_args.kwargs.get("json") or call_args[1].get("json")
        assert payload["type"] == "TRADE_EXECUTE"
        assert payload["side"] == "BUY"

    @pytest.mark.asyncio
    async def test_success_clears_error(self):
        d = _make_dispatcher()
        d._last_dispatch_errors["ASTER"] = {"reason": "old error"}
        d.session = _mock_session(status=200)
        await d.send_command("ASTER", {"action": "BUY", "symbol": "SOL"})
        assert d.get_last_dispatch_error("ASTER") == {}


# ── Fill Confirmation ───────────────────────────────────────────


class TestResolveF:
    def test_resolve_matching_fill(self):
        d = _make_dispatcher()
        loop = asyncio.new_event_loop()
        future = loop.create_future()
        d._pending_confirmations[("ASTER", "SOL")] = future

        fill_data = {"platform": "ASTER", "symbol": "SOLUSDT", "pnl": 50}
        resolved = d.resolve_fill(fill_data)
        assert resolved is True
        assert future.done()
        assert future.result() == fill_data
        loop.close()

    def test_resolve_no_match(self):
        d = _make_dispatcher()
        fill_data = {"platform": "ASTER", "symbol": "BTCUSDT"}
        resolved = d.resolve_fill(fill_data)
        assert resolved is False

    def test_resolve_strips_quote_currency(self):
        d = _make_dispatcher()
        loop = asyncio.new_event_loop()
        future = loop.create_future()
        d._pending_confirmations[("LIGHTER", "ETH")] = future

        fill_data = {"platform": "LIGHTER", "symbol": "ETHUSDT"}
        resolved = d.resolve_fill(fill_data)
        assert resolved is True
        loop.close()

    def test_resolve_already_done_future(self):
        d = _make_dispatcher()
        loop = asyncio.new_event_loop()
        future = loop.create_future()
        future.set_result({"already": "done"})
        d._pending_confirmations[("ASTER", "SOL")] = future

        fill_data = {"platform": "ASTER", "symbol": "SOL"}
        resolved = d.resolve_fill(fill_data)
        # Future is popped but already done, so returns False
        assert resolved is False
        loop.close()

    def test_resolve_with_venue_key(self):
        """Fill data can use 'venue' instead of 'platform'."""
        d = _make_dispatcher()
        loop = asyncio.new_event_loop()
        future = loop.create_future()
        d._pending_confirmations[("ASTER", "SOL")] = future

        fill_data = {"venue": "ASTER", "symbol": "SOL"}
        resolved = d.resolve_fill(fill_data)
        assert resolved is True
        loop.close()

    def test_pending_confirmation_count(self):
        d = _make_dispatcher()
        assert d.pending_confirmation_count == 0
        loop = asyncio.new_event_loop()
        d._pending_confirmations[("ASTER", "SOL")] = loop.create_future()
        d._pending_confirmations[("LIGHTER", "BTC")] = loop.create_future()
        assert d.pending_confirmation_count == 2
        loop.close()


class TestSendAndConfirm:
    @pytest.mark.asyncio
    async def test_fill_confirmed_within_timeout(self):
        d = _make_dispatcher()
        d.session = _mock_session(status=200)

        async def resolve_after_delay():
            await asyncio.sleep(0.05)
            d.resolve_fill({"platform": "ASTER", "symbol": "SOLUSDT", "pnl": 100})

        task = asyncio.create_task(resolve_after_delay())
        result = await d.send_and_confirm(
            "ASTER",
            {"action": "BUY", "symbol": "SOL"},
            timeout_seconds=2.0,
        )
        await task
        assert result.get("pnl") == 100

    @pytest.mark.asyncio
    async def test_fill_timeout(self):
        d = _make_dispatcher()
        d.session = _mock_session(status=200)
        result = await d.send_and_confirm(
            "ASTER",
            {"action": "BUY", "symbol": "SOL"},
            timeout_seconds=0.1,
            retries=1,
        )
        assert result["success"] is False
        assert "timeout" in result["error_message"].lower()

    @pytest.mark.asyncio
    async def test_dispatch_failure(self):
        d = _make_dispatcher()
        d.session = _mock_session(status=500, body="error")
        result = await d.send_and_confirm(
            "ASTER",
            {"action": "BUY", "symbol": "SOL"},
            timeout_seconds=1.0,
        )
        assert result["success"] is False
        assert "failed" in result["error_message"].lower()

    @pytest.mark.asyncio
    async def test_retry_on_timeout(self):
        d = _make_dispatcher()
        d.session = _mock_session(status=200)

        # Resolve on second attempt
        attempt_count = 0

        async def resolve_on_retry():
            nonlocal attempt_count
            while attempt_count < 2:
                await asyncio.sleep(0.05)
            d.resolve_fill({"platform": "ASTER", "symbol": "SOLUSDT", "pnl": 42})

        async def count_dispatches():
            nonlocal attempt_count
            # Monkey-patch send_command to count
            original = d.send_command

            async def counting_send(*a, **kw):
                nonlocal attempt_count
                attempt_count += 1
                return await original(*a, **kw)

            d.send_command = counting_send

        await count_dispatches()
        task = asyncio.create_task(resolve_on_retry())

        await d.send_and_confirm(
            "ASTER",
            {"action": "BUY", "symbol": "SOL"},
            timeout_seconds=0.1,
            retries=3,
        )
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

        # Should have attempted multiple dispatches
        assert attempt_count >= 2

    @pytest.mark.asyncio
    async def test_concurrent_fills_different_symbols(self):
        """Two fills for different symbols should not interfere."""
        d = _make_dispatcher()
        d.session = _mock_session(status=200)

        async def resolve_sol():
            await asyncio.sleep(0.05)
            d.resolve_fill({"platform": "ASTER", "symbol": "SOLUSDT", "result": "sol_fill"})

        async def resolve_btc():
            await asyncio.sleep(0.05)
            d.resolve_fill({"platform": "ASTER", "symbol": "BTCUSDT", "result": "btc_fill"})

        sol_task = asyncio.create_task(resolve_sol())
        btc_task = asyncio.create_task(resolve_btc())

        sol_result, btc_result = await asyncio.gather(
            d.send_and_confirm("ASTER", {"action": "BUY", "symbol": "SOL"}, timeout_seconds=2.0),
            d.send_and_confirm("ASTER", {"action": "BUY", "symbol": "BTC"}, timeout_seconds=2.0),
        )

        await sol_task
        await btc_task

        assert sol_result.get("result") == "sol_fill"
        assert btc_result.get("result") == "btc_fill"


# ── Auth Header ─────────────────────────────────────────────────


class TestAuthHeader:
    @pytest.mark.asyncio
    async def test_no_auth_outside_cloud_run(self):
        d = _make_dispatcher(K_SERVICE="")
        d.session = _mock_session()
        headers = await d._get_auth_header("http://aster:8080")
        assert headers == {}

    @pytest.mark.asyncio
    async def test_auth_caches_token(self):
        d = _make_dispatcher()
        # Build a mock session where .get() returns a proper async context manager
        resp = AsyncMock()
        resp.status = 200
        resp.text = AsyncMock(return_value="fake-token-123")
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=False)

        session = AsyncMock()
        session.get = MagicMock(return_value=resp)
        d.session = session
        d._token_cache = {}

        # K_SERVICE must be set at call time, not just at construction time
        with patch.dict(os.environ, {"K_SERVICE": "sapphire-alpha"}):
            h1 = await d._get_auth_header("http://aster:8080")
            assert h1 == {"Authorization": "Bearer fake-token-123"}
            assert "http://aster:8080" in d._token_cache

            # Second call should use cache (no additional network call)
            h2 = await d._get_auth_header("http://aster:8080")
            assert h2 == {"Authorization": "Bearer fake-token-123"}

    @pytest.mark.asyncio
    async def test_auth_metadata_failure(self):
        d = _make_dispatcher()
        resp = AsyncMock()
        resp.status = 500
        resp.text = AsyncMock(return_value="metadata error")
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=False)
        session = AsyncMock()
        session.get = MagicMock(return_value=resp)
        d.session = session
        d._token_cache = {}
        with patch.dict(os.environ, {"K_SERVICE": "sapphire-alpha"}):
            headers = await d._get_auth_header("http://aster:8080")
        assert headers == {}


# ── Error Recording ─────────────────────────────────────────────


class TestErrorRecording:
    def test_record_and_get_error(self):
        d = _make_dispatcher()
        d._record_dispatch_error("ASTER", "test_error", status=500, body="boom")
        err = d.get_last_dispatch_error("ASTER")
        assert err["reason"] == "test_error"
        assert err["status"] == 500
        assert err["body"] == "boom"

    def test_get_error_empty(self):
        d = _make_dispatcher()
        assert d.get_last_dispatch_error("ASTER") == {}

    def test_error_body_truncated(self):
        d = _make_dispatcher()
        d._record_dispatch_error("ASTER", "big", body="x" * 1000)
        err = d.get_last_dispatch_error("ASTER")
        assert len(err["body"]) <= 320
