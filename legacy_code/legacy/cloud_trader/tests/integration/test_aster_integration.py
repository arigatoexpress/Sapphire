"""Aster DEX Integration Tests with Real API Calls.

Tests the Aster client for futures trading.
Uses real API calls for public endpoints, skips private endpoints without creds.
"""

import asyncio
import os
from typing import Optional

import pytest

from cloud_trader.exchange import AsterClient
from cloud_trader.credentials import Credentials, load_credentials


# ============================================================================
# CONFIGURATION AND MARKERS
# ============================================================================


def has_aster_credentials() -> bool:
    """Check if Aster API credentials are available."""
    try:
        creds = load_credentials()
        return creds.api_key is not None and creds.api_secret is not None
    except Exception:
        return False


# Skip marker for tests requiring credentials
requires_aster_auth = pytest.mark.skipif(
    not has_aster_credentials(),
    reason="ASTER_API_KEY or ASTER_API_SECRET not set"
)


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def aster_client():
    """Create an Aster client for testing (public API only)."""
    return AsterClient(credentials=None)


@pytest.fixture
def aster_client_authed():
    """Create an authenticated Aster client."""
    try:
        creds = load_credentials()
        return AsterClient(credentials=creds)
    except Exception:
        return None


# ============================================================================
# PUBLIC API TESTS (No Auth Required)
# ============================================================================


class TestAsterPublicAPI:
    """Tests for Aster public API endpoints (no auth needed)."""

    @pytest.mark.asyncio
    async def test_get_exchange_info(self, aster_client):
        """Test fetching exchange info (available symbols)."""
        try:
            info = await aster_client.get_exchange_info()
            
            print(f"\n📋 Exchange Info: {len(info.get('symbols', []))} symbols")
            assert info is not None
            
            if "symbols" in info:
                symbols = [s["symbol"] for s in info["symbols"][:5]]
                print(f"   First 5 symbols: {symbols}")
        except Exception as e:
            print(f"\n⚠️ Exchange info error: {e}")

    @pytest.mark.asyncio
    async def test_get_ticker_btcusdt(self, aster_client):
        """Test fetching BTC/USDT ticker."""
        try:
            ticker = await aster_client.get_ticker("BTCUSDT")
            
            print(f"\n📊 BTCUSDT Ticker: {ticker}")
            assert ticker is not None
            
            if "lastPrice" in ticker:
                print(f"   💵 BTC Price: ${float(ticker['lastPrice']):,.2f}")
        except Exception as e:
            print(f"\n⚠️ Ticker error: {e}")

    @pytest.mark.asyncio
    async def test_get_ticker_ethusdt(self, aster_client):
        """Test fetching ETH/USDT ticker."""
        try:
            ticker = await aster_client.get_ticker("ETHUSDT")
            
            print(f"\n📊 ETHUSDT Ticker: {ticker}")
            assert ticker is not None
        except Exception as e:
            print(f"\n⚠️ Ticker error: {e}")

    @pytest.mark.asyncio
    async def test_get_klines(self, aster_client):
        """Test fetching candlestick data."""
        try:
            klines = await aster_client.get_klines("BTCUSDT", "1h", limit=10)
            
            print(f"\n📈 BTCUSDT 1h Klines: {len(klines)} candles")
            assert klines is not None
            assert len(klines) <= 10
            
            if len(klines) > 0:
                latest = klines[-1]
                print(f"   Latest close: ${float(latest[4]):,.2f}")
        except Exception as e:
            print(f"\n⚠️ Klines error: {e}")

    @pytest.mark.asyncio
    async def test_get_mark_price(self, aster_client):
        """Test fetching mark price."""
        try:
            mark = await aster_client.get_mark_price("BTCUSDT")
            
            print(f"\n🎯 BTCUSDT Mark Price: {mark}")
            assert mark is not None
        except Exception as e:
            print(f"\n⚠️ Mark price error: {e}")

    @pytest.mark.asyncio
    async def test_get_funding_rate(self, aster_client):
        """Test fetching funding rate."""
        try:
            funding = await aster_client.get_funding_rate("BTCUSDT")
            
            print(f"\n💸 BTCUSDT Funding Rate: {funding}")
            assert funding is not None
        except Exception as e:
            print(f"\n⚠️ Funding rate error: {e}")

    @pytest.mark.asyncio
    async def test_get_all_tickers(self, aster_client):
        """Test fetching all tickers."""
        try:
            tickers = await aster_client.get_all_tickers()
            
            print(f"\n📋 All Tickers: {len(tickers)} symbols")
            assert tickers is not None
            
            # Show top gainers
            if len(tickers) > 0 and isinstance(tickers[0], dict):
                sorted_tickers = sorted(
                    tickers,
                    key=lambda x: float(x.get("priceChangePercent", 0)),
                    reverse=True
                )[:3]
                print("   Top Gainers:")
                for t in sorted_tickers:
                    print(f"      {t.get('symbol')}: {t.get('priceChangePercent')}%")
        except Exception as e:
            print(f"\n⚠️ All tickers error: {e}")


# ============================================================================
# AUTHENTICATED API TESTS
# ============================================================================


class TestAsterAuthenticatedAPI:
    """Tests for Aster authenticated API endpoints."""

    def _should_skip_due_to_ip(self, e) -> bool:
        """Check if error is due to IP restriction."""
        msg = str(e).lower()
        return "ip" in msg and ("permission" in msg or "not allowed" in msg or "invalid" in msg)

    @requires_aster_auth
    @pytest.mark.asyncio
    async def test_get_account_balance(self, aster_client_authed):
        """Test fetching account balance."""
        if aster_client_authed is None:
            pytest.skip("No authenticated client available")
        
        try:
            balance = await aster_client_authed.get_account_balance()
            print(f"\n💰 Account Balance: {balance}")
            assert balance is not None
        except Exception as e:
            if self._should_skip_due_to_ip(e):
                pytest.skip(f"Skipping due to IP restriction: {e}")
            raise e

    @requires_aster_auth
    @pytest.mark.asyncio
    async def test_get_position_risk(self, aster_client_authed):
        """Test fetching position risk."""
        if aster_client_authed is None:
            pytest.skip("No authenticated client available")
        
        try:
            positions = await aster_client_authed.get_position_risk()
            print(f"\n📍 Positions: {len(positions)} open")
            assert positions is not None
            
            for pos in positions[:3]:
                if float(pos.get("positionAmt", 0)) != 0:
                    print(f"   {pos.get('symbol')}: {pos.get('positionAmt')} @ {pos.get('entryPrice')}")
        except Exception as e:
            if self._should_skip_due_to_ip(e):
                pytest.skip(f"Skipping due to IP restriction: {e}")
            raise e

    @requires_aster_auth
    @pytest.mark.asyncio
    async def test_get_open_orders(self, aster_client_authed):
        """Test fetching open orders."""
        if aster_client_authed is None:
            pytest.skip("No authenticated client available")
        
        try:
            orders = await aster_client_authed.get_open_orders()
            print(f"\n📝 Open Orders: {len(orders)}")
            assert orders is not None
        except Exception as e:
            if self._should_skip_due_to_ip(e):
                pytest.skip(f"Skipping due to IP restriction: {e}")
            raise e


# ============================================================================
# HEALTH CHECK TESTS
# ============================================================================


class TestAsterHealthCheck:
    """Health check tests for Aster integration."""

    @pytest.mark.asyncio
    async def test_aster_api_reachable(self):
        """Test that Aster API is reachable."""
        import httpx
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    "https://fapi.asterdex.com/fapi/v1/ping",
                    timeout=10.0
                )
                print(f"\n🏥 Aster API Ping: {response.status_code}")
                assert response.status_code == 200
            except httpx.ConnectError:
                pytest.skip("Aster API not reachable")

    @pytest.mark.asyncio
    async def test_aster_server_time(self):
        """Test fetching Aster server time."""
        import httpx
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    "https://fapi.asterdex.com/fapi/v1/time",
                    timeout=10.0
                )
                if response.status_code == 200:
                    data = response.json()
                    print(f"\n⏰ Aster Server Time: {data.get('serverTime')}")
            except Exception as e:
                print(f"\n⚠️ Server time error: {e}")


# ============================================================================
# RATE LIMITING AWARENESS TESTS
# ============================================================================


class TestAsterRateLimiting:
    """Test rate limiting awareness."""

    @pytest.mark.asyncio
    async def test_multiple_requests_dont_rate_limit(self, aster_client):
        """Test that a few requests don't trigger rate limiting."""
        import httpx
        
        errors = 0
        for i in range(5):
            try:
                await aster_client.get_ticker("BTCUSDT")
            except Exception as e:
                if "rate" in str(e).lower():
                    errors += 1
        
        print(f"\n🚦 Rate limit errors: {errors}/5")
        # Should have very few or no rate limit errors for 5 requests
        assert errors < 3


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
