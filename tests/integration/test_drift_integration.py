"""Aster Protocol Integration Tests with Real API Calls.

Tests the Aster client for Solana perpetual futures trading.
Uses real API calls where possible (CoinGecko for pricing, etc).
"""

import asyncio
import os
from typing import Optional

import pytest

from cloud_trader.aster_client import AsterClient, get_aster_client


# ============================================================================
# CONFIGURATION AND MARKERS
# ============================================================================


def has_solana_rpc() -> bool:
    """Check if Solana RPC is configured."""
    return bool(os.getenv("SOLANA_RPC_URL"))


def has_aster_wallet() -> bool:
    """Check if Aster wallet is configured for trading."""
    return bool(os.getenv("SOLANA_PRIVATE_KEY"))


# Skip markers
requires_rpc = pytest.mark.skipif(
    not has_solana_rpc(),
    reason="SOLANA_RPC_URL not set"
)

requires_wallet = pytest.mark.skipif(
    not has_aster_wallet(),
    reason="SOLANA_PRIVATE_KEY not set (required for trading operations)"
)


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def aster_client():
    """Create a Aster client for testing."""
    return AsterClient()


# ============================================================================
# CLIENT INITIALIZATION TESTS
# ============================================================================


class TestAsterClientInitialization:
    """Test client initialization and configuration."""

    def test_client_initialization(self):
        """Test that client initializes correctly."""
        client = AsterClient()
        assert client is not None
        assert client.rpc_url is not None

    def test_singleton_pattern(self):
        """Test that get_aster_client returns singleton."""
        client1 = get_aster_client()
        client2 = get_aster_client()
        assert client1 is client2

    @pytest.mark.asyncio
    async def test_async_initialization(self, aster_client):
        """Test async initialization."""
        await aster_client.initialize()
        assert aster_client.is_initialized is True


# ============================================================================
# REAL API TESTS - Market Data (No Auth Required)
# ============================================================================


class TestAsterRealMarketData:
    """Tests that fetch real market data (via CoinGecko/public APIs)."""

    @pytest.mark.asyncio
    async def test_get_sol_perp_market_real(self, aster_client):
        """Test fetching real SOL-PERP market data."""
        market = await aster_client.get_perp_market("SOL-PERP")
        
        print(f"\n📊 SOL-PERP Market Data: {market}")
        assert market is not None
        assert "symbol" in market
        assert "oracle_price" in market
        
        # Oracle price should be a reasonable SOL price (50-500 range typically)
        if market["oracle_price"] > 0:
            print(f"   💵 SOL Oracle Price: ${market['oracle_price']:.2f}")

    @pytest.mark.asyncio
    async def test_get_market_includes_funding_rate(self, aster_client):
        """Test that market data includes funding rate."""
        market = await aster_client.get_perp_market()
        
        assert "funding_rate_24h" in market
        print(f"\n💸 24h Funding Rate: {market['funding_rate_24h']}")

    @pytest.mark.asyncio
    async def test_get_market_includes_open_interest(self, aster_client):
        """Test that market data includes open interest."""
        market = await aster_client.get_perp_market()
        
        assert "open_interest" in market
        print(f"\n📈 Open Interest: {market['open_interest']}")


# ============================================================================
# POSITION TESTS
# ============================================================================


class TestAsterPositions:
    """Test position-related functionality."""

    @pytest.mark.asyncio
    async def test_get_position_uninitialized(self, aster_client):
        """Test getting position when client is not initialized."""
        position = await aster_client.get_position("SOL-PERP")
        
        # Should return empty dict for uninitialized client
        assert position == {}

    @pytest.mark.asyncio
    async def test_get_position_initialized(self, aster_client):
        """Test getting position after initialization."""
        await aster_client.initialize()
        
        position = await aster_client.get_position("SOL-PERP")
        
        print(f"\n📍 Position: {position}")
        assert "symbol" in position
        assert "amount" in position


# ============================================================================
# ORDER SIMULATION TESTS (No Real Trades)
# ============================================================================


class TestAsterOrderSimulation:
    """Test order operations (simulated, not real trades)."""

    @pytest.mark.asyncio
    async def test_order_structure_market(self, aster_client):
        """Test that market order returns proper structure."""
        result = await aster_client.place_perp_order(
            symbol="SOL-PERP",
            side="BUY",
            amount=0.01,  # Very small amount
            order_type="market"
        )
        
        print(f"\n📝 Order Result: {result}")
        assert result is not None
        assert "tx_sig" in result
        assert "status" in result

    @pytest.mark.asyncio
    async def test_order_structure_limit(self, aster_client):
        """Test that limit order returns proper structure."""
        result = await aster_client.place_perp_order(
            symbol="SOL-PERP",
            side="SELL",
            amount=0.01,
            order_type="limit",
            price=1000.0  # Far from market, won't fill
        )
        
        print(f"\n📝 Limit Order Result: {result}")
        assert result is not None


# ============================================================================
# LIVE TRADING TESTS (Requires Wallet - Disabled by Default)
# ============================================================================


@pytest.mark.skip(reason="Live trading tests disabled by default")
class TestAsterLiveTrading:
    """Live trading tests - only run manually with proper wallet setup."""

    @requires_wallet
    @pytest.mark.asyncio
    async def test_place_real_order(self):
        """Test placing a real order on Aster (DISABLED)."""
        pass

    @requires_wallet
    @pytest.mark.asyncio
    async def test_close_real_position(self):
        """Test closing a real position (DISABLED)."""
        pass


# ============================================================================
# HEALTH CHECK TESTS
# ============================================================================


class TestAsterHealthCheck:
    """Health check tests for Aster integration."""

    @pytest.mark.asyncio
    async def test_coingecko_reachable(self):
        """Test that CoinGecko API (price source) is reachable."""
        import httpx
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    "https://api.coingecko.com/api/v3/simple/price",
                    params={"ids": "solana", "vs_currencies": "usd"},
                    timeout=10.0
                )
                print(f"\n🏥 CoinGecko Health: {response.status_code}")
                
                if response.status_code == 200:
                    data = response.json()
                    print(f"   💵 SOL Price: ${data.get('solana', {}).get('usd', 'N/A')}")
                
                assert response.status_code == 200
            except httpx.ConnectError:
                pytest.skip("CoinGecko API not reachable")

    @requires_rpc
    @pytest.mark.asyncio
    async def test_solana_rpc_reachable(self):
        """Test that Solana RPC is reachable."""
        import httpx
        
        rpc_url = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    rpc_url,
                    json={"jsonrpc": "2.0", "id": 1, "method": "getHealth"},
                    timeout=10.0
                )
                print(f"\n🏥 Solana RPC Health: {response.status_code}")
                
                if response.status_code == 200:
                    data = response.json()
                    print(f"   📊 RPC Response: {data}")
                
            except httpx.ConnectError:
                pytest.skip("Solana RPC not reachable")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
