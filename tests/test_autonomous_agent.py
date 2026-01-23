
import pytest
from unittest.mock import MagicMock, AsyncMock
from cloud_trader.autonomous_agent import AutonomousAgent, Thesis

# --- Fixtures ---

@pytest.fixture
def mock_data_store():
    store = MagicMock()
    store.get = AsyncMock(return_value=50.0) # Default value
    store.get_available_indicators = MagicMock(return_value=["rsi", "macd", "volume", "social_sentiment", "open_interest"])
    return store

@pytest.fixture
def agent(mock_data_store):
    return AutonomousAgent("test_agent_1", "TestBot", mock_data_store, specialization="technical")

# --- Tests ---

def test_initial_config(agent):
    """Verify initial configuration based on specialization."""
    assert agent.specialization == "technical"
    # Technical agent prefers rsi, macd, volume
    assert "rsi" in agent.strategy_config["preferred_indicators"]
    assert "macd" in agent.strategy_config["preferred_indicators"]

@pytest.mark.asyncio
async def test_thesis_formation(agent, mock_data_store):
    """Verify agent formulates thesis using preferred indicators."""
    # Setup data store to return specific values
    async def get_mock_data(indicator, symbol):
        if indicator == "rsi": return 25.0 # Oversold (Bullish)
        if indicator == "macd": return {"trend": "BULLISH"}
        return 100.0
    
    mock_data_store.get = AsyncMock(side_effect=get_mock_data)
    
    thesis = await agent.analyze("BTC-USDC")
    
    assert thesis.symbol == "BTC-USDC"
    assert thesis.signal == "BUY"
    assert "rsi" in thesis.data_used
    assert "macd" in thesis.data_used
    assert "RSI oversold" in thesis.reasoning

def test_learning_updates_indicators(agent):
    """Verify learning mechanism updates indicator scores and preferences."""
    
    # 1. Simulate a winning trade based on RSI
    thesis = Thesis(
        symbol="BTC-USDC",
        signal="BUY",
        confidence=0.8,
        reasoning="RSI Low",
        data_used=["rsi"]
    )
    
    # Initial score (default 0.5 implicitly)
    initial_score = agent.strategy_config.get("indicator_scores", {}).get("rsi", 0.5)
    
    # Learn from WIN (+10% PnL)
    agent.learn_from_trade(thesis, pnl_pct=0.10)
    
    # Score should increase
    new_score = agent.strategy_config["indicator_scores"]["rsi"]
    assert new_score > initial_score
    assert new_score == 0.6 # 0.5 + 0.1
    
    # 2. Simulate a losing trade based on 'volume' (assuming it was used)
    thesis_loss = Thesis(
        symbol="ETH-USDC",
        signal="SELL",
        confidence=0.7,
        reasoning="Low Volume",
        data_used=["volume"]
    )
    
    agent.learn_from_trade(thesis_loss, pnl_pct=-0.05)
    
    # Score should decrease
    vol_score = agent.strategy_config["indicator_scores"]["volume"]
    assert vol_score < 0.5
    assert vol_score == 0.45 # 0.5 - 0.05

def test_preference_evolution(agent):
    """Verify that consistent wins shift preferred indicators."""
    
    # Initial preferences
    assert "social_sentiment" not in agent.strategy_config["preferred_indicators"]
    
    # Simulate multiple wins using 'social_sentiment' (assuming it was explored)
    # We force the score up
    thesis = Thesis(
        symbol="DOGE-USDC",
        signal="BUY",
        confidence=0.9,
        reasoning="Moon", 
        data_used=["social_sentiment"]
    )
    
    # Boost score significantly
    for _ in range(5):
        agent.learn_from_trade(thesis, pnl_pct=0.20)
        
    # 'social_sentiment' score should be high (max 1.0)
    score = agent.strategy_config["indicator_scores"]["social_sentiment"]
    assert score >= 0.9 
    
    # It should now be in preferred indicators (Top 5)
    # Note: learn_from_trade re-sorts preferences
    assert "social_sentiment" in agent.strategy_config["preferred_indicators"]

