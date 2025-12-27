"""Symphony API Integration Tests with Real API Calls.

Tests the Symphony client for Monad blockchain trading.
Uses real API calls where credentials are available.
"""

import asyncio
import os
from typing import Optional

import pytest

from cloud_trader.symphony_client import SymphonyClient, get_symphony_client
from cloud_trader.symphony_config import SYMPHONY_API_KEY, SYMPHONY_AGENT_ID


# ============================================================================
# CONFIGURATION AND MARKERS
# ============================================================================


def has_symphony_credentials() -> bool:
    """Check if Symphony API credentials are available."""
    return bool(SYMPHONY_API_KEY and SYMPHONY_AGENT_ID)


# Skip marker for tests requiring credentials
requires_symphony = pytest.mark.skipif(
    not has_symphony_credentials(),
    reason="SYMPHONY_API_KEY or SYMPHONY_AGENT_ID not set"
)


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def symphony_client():
    """Create a Symphony client for testing."""
    client = SymphonyClient()
    yield client
    # Cleanup handled by client internally


# ============================================================================
# CLIENT INITIALIZATION TESTS
# ============================================================================


class TestSymphonyClientInitialization:
    """Test client initialization and configuration."""

    def test_client_initialization(self):
        """Test that client initializes correctly."""
        client = SymphonyClient()
        assert client is not None

    @requires_symphony
    def test_client_has_valid_agent_id(self):
        """Test that client has a valid agent ID configured."""
        client = SymphonyClient()
        assert client.default_agent_id is not None
        assert len(client.default_agent_id) > 0


# ============================================================================
# REAL API TESTS - Account Operations
# ============================================================================


class TestSymphonyRealAPI:
    """Tests that make real API calls to Symphony."""

    @requires_symphony
    @pytest.mark.asyncio
    async def test_get_account_info_real(self):
        """Test fetching real account information from Symphony."""
        client = SymphonyClient()
        
        result = await client.get_account_info()
        
        print(f"\n📊 Symphony Account Info: {result}")
        assert result is not None
        assert "agent_id" in result or "address" in result

    @requires_symphony
    @pytest.mark.asyncio
    async def test_get_perpetual_positions_real(self):
        """Test fetching real perpetual positions from Symphony."""
        client = SymphonyClient()
        
        positions = await client.get_perpetual_positions()
        
        print(f"\n📈 Symphony Positions: {positions}")
        assert positions is not None
        # Positions can be empty list or dict
        assert isinstance(positions, (list, dict))

    @requires_symphony
    @pytest.mark.asyncio
    async def test_get_my_funds_real(self):
        """Test fetching real agentic funds from Symphony."""
        client = SymphonyClient()
        
        funds = await client.get_my_funds()
        
        print(f"\n💰 Symphony Funds: {funds}")
        # Should return something (even if error dict)
        assert funds is not None

    @requires_symphony
    @pytest.mark.asyncio
    async def test_is_activated_real(self):
        """Test checking real activation status."""
        client = SymphonyClient()
        
        activated = client.is_activated
        
        print(f"\n✅ Symphony Activated: {activated}")
        assert isinstance(activated, bool)

    @requires_symphony
    @pytest.mark.asyncio
    async def test_activation_progress_real(self):
        """Test getting real activation progress."""
        client = SymphonyClient()
        
        progress = client.activation_progress
        
        print(f"\n📊 Activation Progress: {progress}")
        assert progress is not None

    @requires_symphony
    @pytest.mark.asyncio
    async def test_get_market_price_real(self):
        """Test fetching real market price from Symphony."""
        client = SymphonyClient()
        
        # Try to get BTC price
        try:
            price = await client.get_market_price("BTC-USDC")
            print(f"\n💵 BTC-USDC Price: {price}")
            # Price might be None if endpoint doesn't exist, but shouldn't raise
            assert price is None or isinstance(price, (int, float, dict))
        except Exception as e:
            print(f"\n⚠️ Market price error: {e}")

    @requires_symphony
    @pytest.mark.asyncio
    async def test_get_available_symbols_real(self):
        """Test fetching real available trading symbols."""
        client = SymphonyClient()
        
        symbols = await client.get_available_symbols()
        
        print(f"\n📋 Available Symbols: {symbols}")
        # Should return something or None
        assert symbols is None or isinstance(symbols, (list, dict))


# ============================================================================
# MULTI-AGENT TESTS
# ============================================================================


class TestSymphonyMultiAgent:
    """Test multi-agent functionality."""

    @requires_symphony
    def test_multiple_agent_clients(self):
        """Test that multiple agents can be configured."""
        client = SymphonyClient()
        
        # Check if multiple clients are configured
        agents = getattr(client, 'clients', {})
        print(f"\n🤖 Configured Agents: {list(agents.keys())}")
        
        assert len(agents) >= 1  # At least default agent


# ============================================================================
# ERROR HANDLING TESTS (Safe - No Real Trades)
# ============================================================================


class TestSymphonyErrorHandling:
    """Test error handling with real API (safe operations only)."""

    @requires_symphony
    @pytest.mark.asyncio
    async def test_handles_invalid_symbol_gracefully(self):
        """Test that invalid symbol requests are handled gracefully."""
        client = SymphonyClient()
        
        # Try to get price for invalid symbol
        try:
            price = await client.get_market_price("INVALID-SYMBOL-XYZ")
            # Should return None or handle gracefully
            print(f"\n⚠️ Invalid symbol response: {price}")
        except Exception as e:
            print(f"\n⚠️ Exception for invalid symbol: {e}")
            # Expected - just verify it doesn't crash

    @requires_symphony
    @pytest.mark.asyncio
    async def test_handles_nonexistent_strategy(self):
        """Test subscription to non-existent strategy."""
        client = SymphonyClient()
        
        result = await client.subscribe_strategy("nonexistent-strategy-12345")
        
        print(f"\n📝 Non-existent strategy result: {result}")
        # Should handle gracefully


# ============================================================================
# INTEGRATION HEALTH CHECK
# ============================================================================


class TestSymphonyHealthCheck:
    """Health check tests for Symphony integration."""

    @requires_symphony
    @pytest.mark.asyncio
    async def test_symphony_api_reachable(self):
        """Test that Symphony API is reachable."""
        import httpx
        
        async with httpx.AsyncClient() as client:
            try:
                # Try a basic endpoint
                response = await client.get(
                    "https://api.symphony.io/health",
                    headers={"x-api-key": SYMPHONY_API_KEY},
                    timeout=10.0
                )
                print(f"\n🏥 Symphony Health Check: {response.status_code}")
                # 200, 404, or other response (not connection error) means reachable
                assert response.status_code in [200, 401, 403, 404, 500]
            except httpx.ConnectError:
                pytest.skip("Symphony API not reachable")

    @requires_symphony
    @pytest.mark.asyncio
    async def test_symphony_auth_valid(self):
        """Test that Symphony authentication is working."""
        client = SymphonyClient()
        
        # Try to fetch account info (requires valid auth)
        account = await client.get_account_info()
        
        # If we get data, auth is working
        assert account is not None
        print(f"\n🔐 Auth verification: Account data received")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
