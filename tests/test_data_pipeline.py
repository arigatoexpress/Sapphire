
import pytest
import pandas as pd
import numpy as np
from unittest.mock import MagicMock, AsyncMock
from cloud_trader.data.feature_pipeline import FeaturePipeline
from cloud_trader.data_store import DataStore
from cloud_trader.autonomous_agent import AutonomousAgent

@pytest.fixture
def mock_exchange_client():
    client = MagicMock()
    # Return dummy klines
    # [time, open, high, low, close, volume, ...]
    client.get_historical_klines = AsyncMock(return_value=[
        [1600000000000 + i*60000, 100+i, 110+i, 90+i, 105+i, 1000, 0, 0, 0, 0, 0, 0] 
        for i in range(200) # Enough for calculation
    ])
    client.get_order_book = AsyncMock(return_value={"bids": [[100, 1]], "asks": [[101, 1]]})
    return client

@pytest.mark.asyncio
async def test_indicator_calculation(mock_exchange_client):
    """Verify FeaturePipeline calculates new indicators."""
    pipeline = FeaturePipeline(mock_exchange_client)
    
    analysis = await pipeline.get_market_analysis("BTC-USDC")
    
    # Check core indicators
    assert "rsi" in analysis
    assert "macd_val" in analysis
    assert "bb_upper" in analysis
    assert "stoch_k" in analysis
    assert "cci" in analysis
    assert "adx" in analysis
    assert "obv" in analysis
    
    # Check values are populated (not None/Zero generally, though mock data yields specific patterns)
    assert analysis["rsi"] != 0
    assert analysis["bb_upper"] > analysis["bb_lower"]

@pytest.mark.asyncio
async def test_datastore_access(mock_exchange_client):
    """Verify DataStore correctly proxies these indicators."""
    pipeline = FeaturePipeline(mock_exchange_client)
    ds = DataStore(pipeline)
    
    # Test BB
    bb = await ds.get("bollinger_bands", "BTC-USDC")
    assert bb is not None
    assert "upper" in bb
    assert "lower" in bb
    
    # Test MACD
    macd = await ds.get("macd", "BTC-USDC")
    assert macd is not None
    assert "macd" in macd
    assert "signal" in macd
    
    # Test Stochastic
    stoch = await ds.get("stochastic", "BTC-USDC")
    assert stoch is not None
    assert "k" in stoch
    
    # Test CCI, ADX, OBV
    assert await ds.get("cci", "BTC-USDC") is not None
    assert await ds.get("adx", "BTC-USDC") is not None
    assert await ds.get("obv", "BTC-USDC") is not None
    
    # Test Advanced (Wyckoff, Fibs, VSOP)
    wyckoff = await ds.get("wyckoff", "BTC-USDC")
    assert wyckoff in ["NEUTRAL", "ACCUMULATION", "DISTRIBUTION", "MARKUP", "MARKDOWN"]
    
    fibs = await ds.get("fib_levels", "BTC-USDC")
    assert fibs is not None
    assert "0.618" in fibs
    
    vsop = await ds.get("vsop", "BTC-USDC")
    assert vsop is not None
    assert isinstance(vsop, float)

@pytest.mark.asyncio
async def test_agent_exploration(mock_exchange_client):
    """Verify Agent can see these indicators in 'available' list."""
    pipeline = FeaturePipeline(mock_exchange_client)
    ds = DataStore(pipeline)
    agent = AutonomousAgent("test", "test", ds)
    
    available = ds.get_available_indicators()
    assert "bollinger_bands" in available
    assert "stochastic" in available
    assert "adx" in available
    
    # Simulate an agent exploring 'adx'
    val = await agent.data_store.get("adx", "BTC-USDC")
    assert val is not None

