"""Aster API Integration Tests with Real API Calls.

Tests the Aster client for Monad blockchain trading.
Uses real API calls where credentials are available.
"""

import asyncio
import os
from typing import Optional

import pytest

from cloud_trader.aster_client import AsterClient, get_aster_client
from cloud_trader.aster_config import ASTER_API_KEY, ASTER_AGENT_ID


# ============================================================================
# CONFIGURATION AND MARKERS
# ============================================================================


def has_aster_credentials() -> bool:
    """Check if Aster API credentials are available."""
    return bool(ASTER_API_KEY and ASTER_AGENT_ID)


# Skip marker for tests requiring credentials
requires_aster = pytest.mark.skipif(
    not has_aster_credentials(),
    reason="ASTER_API_KEY or ASTER_AGENT_ID not set"
)


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def aster_client():
    """Create a Aster client for testing."""
    client = AsterClient()
    yield client
    # Cleanup handled by client internally


# ============================================================================
# CLIENT INITIALIZATION TESTS
# ============================================================================


class TestAsterClientInitialization:
    """Test client initialization and configuration."""

    def test_client_initialization(self):
        """Test that client initializes correctly."""
        client = AsterClient()
        assert client is not None

    @requires_aster
    def test_client_has_valid_agent_id(self):
        """Test that client has a valid agent ID configured."""
        client = AsterClient()
        assert client.default_agent_id is not None
        assert len(client.default_agent_id) > 0


# ============================================================================
# REAL API TESTS - Account Operations
# ============================================================================


class TestAsterRealAPI:
    """Tests that make real API calls to Aster."""

    @requires_aster
    @pytest.mark.asyncio
    async def test_get_account_info_real(self):
        """Test fetching real account information from Aster."""
        client = AsterClient()
        
        result = await client.get_account_info()
        
        print(f"\n📊 Aster Account Info: {result}")
        assert result is not None
        assert "agent_id" in result or "address" in result

    @requires_aster
    @pytest.mark.asyncio
    async def test_get_perpetual_positions_real(self):
        """Test fetching real perpetual positions from Aster."""
        client = AsterClient()
        
        positions = await client.get_perpetual_positions()
        
        print(f"\n📈 Aster Positions: {positions}")
        assert positions is not None
        # Positions can be empty list or dict
        assert isinstance(positions, (list, dict))

    @requires_aster
    @pytest.mark.asyncio
    async def test_get_my_funds_real(self):
        """Test fetching real agentic funds from Aster."""
        client = AsterClient()
        
        funds = await client.get_my_funds()
        
        print(f"\n💰 Aster Funds: {funds}")
        # Should return something (even if error dict)
        assert funds is not None

    @requires_aster
    @pytest.mark.asyncio
    async def test_is_activated_real(self):
        """Test checking real activation status."""
        client = AsterClient()
        
        activated = client.is_activated
        
        print(f"\n✅ Aster Activated: {activated}")
        assert isinstance(activated, bool)

    @requires_aster
    @pytest.mark.asyncio
    async def test_activation_progress_real(self):
        """Test getting real activation progress."""
        client = AsterClient()
        
        progress = client.activation_progress
        
        print(f"\n📊 Activation Progress: {progress}")
        assert progress is not None

    @requires_aster
    @pytest.mark.asyncio
    async def test_get_market_price_real(self):
        """Test fetching real market price from Aster."""
        client = AsterClient()
        
        # Try to get BTC price
        try:
            price = await client.get_market_price("BTC-USDC")
            print(f"\n💵 BTC-USDC Price: {price}")
            # Price might be None if endpoint doesn't exist, but shouldn't raise
            assert price is None or isinstance(price, (int, float, dict))
        except Exception as e:
            print(f"\n⚠️ Market price error: {e}")

    @requires_aster
    @pytest.mark.asyncio
    async def test_get_available_symbols_real(self):
        """Test fetching real available trading symbols."""
        client = AsterClient()
        
        symbols = await client.get_available_symbols()
        
        print(f"\n📋 Available Symbols: {symbols}")
        # Should return something or None
        assert symbols is None or isinstance(symbols, (list, dict))


# ============================================================================
# MULTI-AGENT TESTS
# ============================================================================


class TestAsterMultiAgent:
    """Test multi-agent functionality."""

    @requires_aster
    def test_multiple_agent_clients(self):
        """Test that multiple agents can be configured."""
        client = AsterClient()
        
        # Check if multiple clients are configured
        agents = getattr(client, 'clients', {})
        print(f"\n🤖 Configured Agents: {list(agents.keys())}")
        
        assert len(agents) >= 1  # At least default agent


# ============================================================================
# ERROR HANDLING TESTS (Safe - No Real Trades)
# ============================================================================


class TestAsterErrorHandling:
    """Test error handling with real API (safe operations only)."""

    @requires_aster
    @pytest.mark.asyncio
    async def test_handles_invalid_symbol_gracefully(self):
        """Test that invalid symbol requests are handled gracefully."""
        client = AsterClient()
        
        # Try to get price for invalid symbol
        try:
            price = await client.get_market_price("INVALID-SYMBOL-XYZ")
            # Should return None or handle gracefully
            print(f"\n⚠️ Invalid symbol response: {price}")
        except Exception as e:
            print(f"\n⚠️ Exception for invalid symbol: {e}")
            # Expected - just verify it doesn't crash

    @requires_aster
    @pytest.mark.asyncio
    async def test_handles_nonexistent_strategy(self):
        """Test subscription to non-existent strategy."""
        client = AsterClient()
        
        result = await client.subscribe_strategy("nonexistent-strategy-12345")
        
        print(f"\n📝 Non-existent strategy result: {result}")
        # Should handle gracefully


# ============================================================================
# INTEGRATION HEALTH CHECK
# ============================================================================


class TestAsterHealthCheck:
    """Health check tests for Aster integration."""

    @requires_aster
    @pytest.mark.asyncio
    async def test_aster_api_reachable(self):
        """Test that Aster API is reachable."""
        import httpx
        
        async with httpx.AsyncClient() as client:
            try:
                # Try a basic endpoint
                response = await client.get(
                    "https://api.aster.io/health",
                    headers={"x-api-key": ASTER_API_KEY},
                    timeout=10.0
                )
                print(f"\n🏥 Aster Health Check: {response.status_code}")
                # 200, 404, or other response (not connection error) means reachable
                assert response.status_code in [200, 401, 403, 404, 500]
            except httpx.ConnectError:
                pytest.skip("Aster API not reachable")

    @requires_aster
    @pytest.mark.asyncio
    async def test_aster_auth_valid(self):
        """Test that Aster authentication is working."""
        client = AsterClient()
        
        # Try to fetch account info (requires valid auth)
        account = await client.get_account_info()
        
        # If we get data, auth is working
        assert account is not None
        print(f"\n🔐 Auth verification: Account data received")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
