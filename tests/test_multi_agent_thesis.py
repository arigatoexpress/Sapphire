"""Test script for multi-agent parallel thesis generation."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cloud_trader.config import Settings
from cloud_trader.open_source import OpenSourceAnalyst
from cloud_trader.service import TradingService
from cloud_trader.risk import Position


@pytest.mark.asyncio
async def test_parallel_agent_queries():
    """Test that AVAX and ARB symbols query multiple agents in parallel."""
    settings = Settings(
        fingpt_endpoint="http://test-fingpt",
        lagllama_endpoint="http://test-lagllama",
        risk_threshold=0.7,
    )
    
    with patch("cloud_trader.service.AsterClient"):
        service = TradingService(settings)
    
    # Mock market context
    market_context = {
        "change_24h": 2.5,
        "volume": 1000000,
        "atr": 0.5,
    }
    
    # Mock the analyst to track calls
    with patch.object(service._open_source_analyst, 'generate_thesis') as mock_generate:
        # Setup mock responses
        async def mock_thesis_generator(agent_id, symbol, side, price, context):
            await asyncio.sleep(0.1)  # Simulate network delay
            if agent_id == "fingpt-alpha":
                return {
                    "source": "FinGPT",
                    "thesis": f"FinGPT thesis for {symbol}",
                    "risk_score": 0.75,
                    "confidence": 0.8,
                }
            elif agent_id == "lagllama-degen":
                return {
                    "source": "Lag-LLaMA",
                    "thesis": f"Lag-Llama thesis for {symbol}",
                    "ci_span": 0.15,
                    "confidence": 0.7,
                }
            return None
        
        mock_generate.side_effect = mock_thesis_generator
        
        # Test AVAX (should query both FinGPT and Lag-Llama)
        thesis = await service._generate_trade_thesis(
            agent_id="fingpt-alpha",
            symbol="AVAXUSDT",
            side="BUY",
            price=25.0,
            market_context=market_context,
            take_profit=26.0,
            stop_loss=24.0,
        )
        
        # Verify parallel calls were made
        assert mock_generate.call_count >= 2, "Should have called multiple agents in parallel"
        assert "thesis" in thesis.lower() or "risk" in thesis.lower(), "Should return a thesis"
        
        # Check that both agents were queried
        call_agents = [call[0][0] for call in mock_generate.call_args_list]
        assert "fingpt-alpha" in call_agents, "Should have called FinGPT"
        assert "lagllama-degen" in call_agents, "Should have called Lag-Llama"


@pytest.mark.asyncio
async def test_risk_threshold_enforcement():
    """Test that theses below risk threshold are rejected."""
    settings = Settings(
        risk_threshold=0.7,
        fingpt_endpoint="http://test-fingpt",
    )
    
    with patch("cloud_trader.service.AsterClient"):
        service = TradingService(settings)
    
    market_context = {"change_24h": 1.0, "volume": 500000, "atr": 0.3}
    
    with patch.object(service._open_source_analyst, 'generate_thesis') as mock_generate:
        # Low risk score (below threshold)
        mock_generate.return_value = {
            "source": "FinGPT",
            "thesis": "Low risk thesis",
            "risk_score": 0.5,  # Below 0.7 threshold
            "confidence": 0.6,
        }
        
        thesis = await service._generate_trade_thesis(
            agent_id="fingpt-alpha",
            symbol="BTCUSDT",
            side="BUY",
            price=50000.0,
            market_context=market_context,
            take_profit=51000.0,
            stop_loss=49000.0,
        )
        
        # Should fall back to deterministic thesis (not the low-risk one)
        assert "Low risk thesis" not in thesis, "Should reject low-risk thesis"
        assert len(thesis) > 0, "Should still return a thesis (deterministic fallback)"


@pytest.mark.asyncio
async def test_agent_response_caching():
    """Test that agent responses are cached."""
    settings = Settings(
        fingpt_endpoint="http://test-fingpt",
        agent_cache_ttl_seconds=10.0,
    )
    
    analyst = OpenSourceAnalyst(settings)
    
    market_context = {"change_24h": 1.0, "volume": 500000, "atr": 0.3}
    
    call_count = 0
    
    async def mock_post_json(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return {
            "thesis": f"Test thesis {call_count}",
            "risk_score": 0.8,
            "confidence": 0.9,
        }
    
    with patch.object(analyst, '_post_json', side_effect=mock_post_json):
        # First call
        result1 = await analyst.generate_thesis(
            "fingpt-alpha", "BTCUSDT", "BUY", 50000.0, market_context
        )
        
        # Second call (should use cache)
        result2 = await analyst.generate_thesis(
            "fingpt-alpha", "BTCUSDT", "BUY", 50000.0, market_context
        )
        
        # Should only call once (second uses cache)
        assert call_count == 1, "Second call should use cache"
        assert result1 == result2, "Cached result should match"


@pytest.mark.asyncio
async def test_agent_margin_allocation_enforced():
    """Ensure agents cannot exceed configured margin allocation."""
    settings = Settings(max_symbols_per_agent=2)
    with patch("cloud_trader.service.AsterClient"):
        service = TradingService(settings)
    with patch("cloud_trader.service.AsterClient"):
        service = TradingService(settings)

    service._available_symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "SUIUSDT"]
    service._exchange = AsyncMock()
    service._exchange.get_all_symbols = AsyncMock(return_value=service._available_symbols)
    await service._initialize_agents()

    agent_id = service._symbol_to_agent.get("BTCUSDT")
    assert agent_id is not None, "BTCUSDT should map to an agent"

    service._portfolio.positions["BTCUSDT"] = Position(symbol="BTCUSDT", notional=900.0)
    service._portfolio.total_exposure = 900.0

    remaining = service._get_agent_margin_remaining(agent_id)
    assert remaining <= 100.0 + 1e-6

    assert service._has_agent_margin(agent_id, 50.0)
    assert service._has_agent_margin(agent_id, 150.0) is False


if __name__ == "__main__":
    # Run basic smoke test
    async def smoke_test():
        settings = Settings()
        service = TradingService(settings)
        
        market_context = {
            "change_24h": 2.5,
            "volume": 1000000,
            "atr": 0.5,
        }
        
        # Test with mock (no actual API calls)
        with patch.object(service._open_source_analyst, 'generate_thesis', return_value=None):
            thesis = await service._generate_trade_thesis(
                agent_id="fingpt-alpha",
                symbol="AVAXUSDT",
                side="BUY",
                price=25.0,
                market_context=market_context,
                take_profit=26.0,
                stop_loss=24.0,
            )
            print(f"Thesis generated: {thesis[:100]}...")
            print("✓ Smoke test passed")
    
    asyncio.run(smoke_test())

