
import pytest
import asyncio
from unittest.mock import MagicMock
from cloud_trader.agent_consensus import AgentConsensusEngine, AgentSignal, SignalType, ConsensusMethod, MarketRegime, RegimeMetrics
from cloud_trader.time_sync import get_timestamp_us

# --- Fixtures ---

@pytest.fixture
def consensus_engine():
    engine = AgentConsensusEngine()
    # Register a few test agents
    engine.register_agent("trend_follower", "momentum", "trend", base_weight=1.0)
    engine.register_agent("mean_reverter", "reversion", "range", base_weight=1.0)
    engine.register_agent("whale_watcher", "flow", "volatility", base_weight=1.5) # Higher base weight
    return engine

# --- Tests ---

def test_registration_initialization(consensus_engine):
    """Verify agents are registered with correct initial state."""
    assert "trend_follower" in consensus_engine.agent_registry
    assert "whale_watcher" in consensus_engine.agent_registry
    
    # Check initial performance metrics
    perf = consensus_engine.agent_performance["trend_follower"]
    assert perf.win_rate == 0.5
    assert perf.total_trades == 0

@pytest.mark.asyncio
async def test_simple_majority_consensus(consensus_engine):
    """Test clear consensus where all agents agree."""
    # Submit 3 signals for BTC-USDC: ALL LONG
    ts = get_timestamp_us()
    
    s1 = AgentSignal(
        agent_id="trend_follower",
        signal_type=SignalType.ENTRY_LONG,
        confidence=0.8,
        strength=1.0,
        symbol="BTC-USDC",
        timestamp_us=ts
    )
    s2 = AgentSignal(
        agent_id="mean_reverter",
        signal_type=SignalType.ENTRY_LONG,
        confidence=0.7,
        strength=0.8,
        symbol="BTC-USDC",
        timestamp_us=ts
    )
    s3 = AgentSignal(
        agent_id="whale_watcher",
        signal_type=SignalType.ENTRY_LONG,
        confidence=0.9,
        strength=1.0,
        symbol="BTC-USDC",
        timestamp_us=ts
    )
    
    consensus_engine.submit_signal(s1)
    consensus_engine.submit_signal(s2)
    consensus_engine.submit_signal(s3)
    
    result = await consensus_engine.conduct_consensus_vote("BTC-USDC")
    
    assert result is not None
    assert result.winning_signal == SignalType.ENTRY_LONG
    assert result.agreement_level == 1.0 # All voted for same signal type
    assert result.participation_rate == 1.0 # 3/3 registered agents
    assert result.consensus_confidence > 0.7 # Weighted average > 0.7 (approx 0.76)

@pytest.mark.asyncio
async def test_conflict_resolution_and_weighting(consensus_engine):
    """Test that higher weighted agents sway the vote during conflict."""
    # Trend follower says LONG, Whale says SHORT. 
    # Whale has base_weight 1.5, Trend 1.0.
    
    ts = get_timestamp_us()
    
    s1 = AgentSignal(
        agent_id="trend_follower",
        signal_type=SignalType.ENTRY_LONG,
        confidence=0.6,
        strength=1.0,
        symbol="ETH-USDC",
        timestamp_us=ts,
        reasoning="Trend line support"
    )
    
    s2 = AgentSignal(
        agent_id="whale_watcher", # Heavier weight
        signal_type=SignalType.ENTRY_SHORT,
        confidence=0.9,
        strength=1.0,
        symbol="ETH-USDC",
        timestamp_us=ts,
        reasoning="Massive sell wall"
    )
    
    # Exclude mean_reverter to see direct conflict
    consensus_engine.submit_signal(s1)
    consensus_engine.submit_signal(s2)
    
    result = await consensus_engine.conduct_consensus_vote("ETH-USDC")
    
    # Whale should win due to higher weight (1.5 vs 1.0) AND higher confidence (0.9 vs 0.6)
    assert result.winning_signal == SignalType.ENTRY_SHORT
    assert "Massive sell wall" in result.reasoning
    
    # Agreement level should be low (split vote)
    # Total weight = 1.0 + 1.5 = 2.5
    # Short weight = 1.5 / 2.5 = 0.6
    # Agreement level is based on participation factor of winning signal
    assert result.agreement_level < 0.7 

@pytest.mark.asyncio
async def test_learning_feedback_loop(consensus_engine):
    """Verify that feedback updates agent performance metrics and weights."""
    
    # 1. Setup initial state: 'trend_follower' makes a call
    ts = get_timestamp_us()
    
    # Get initial weight
    initial_perf = consensus_engine.agent_performance["trend_follower"]
    initial_weight = initial_perf.calculate_weight(1.0)
    
    s1 = AgentSignal(
        agent_id="trend_follower",
        signal_type=SignalType.ENTRY_LONG,
        confidence=0.9,
        strength=1.0,
        symbol="SOL-USDC",
        timestamp_us=ts
    )
    consensus_engine.submit_signal(s1)
    result = await consensus_engine.conduct_consensus_vote("SOL-USDC")
    
    # 2. Simulate Outcome: NEGATIVE (Trade lost money)
    # This means the agent was WRONG with HIGH confidence -> Should be penalized heavily
    consensus_engine.update_performance_feedback(
        consensus_result=result,
        actual_outcome=-0.05, # -5% loss
        regime=None
    )
    
    perf = consensus_engine.agent_performance["trend_follower"]
    
    # Win rate should drop (started at 0.5)
    # alpha = 0.1
    # new_win_rate = 0.1 * 0 + 0.9 * 0.5 = 0.45
    assert perf.win_rate < 0.5
    assert perf.win_rate == pytest.approx(0.45, abs=0.01)
    
    # Confidence accuracy should drop because it was 0.9 confident but wrong (alignment = |0.9 - 0| = 0.9)
    # prev acc = 0.5
    # new acc = 0.1 * (1 - 0.9) + 0.9 * 0.5 = 0.01 + 0.45 = 0.46
    assert perf.confidence_accuracy < 0.5
    
    # 3. Trigger weight update (simulated by having > 10 trades)
    perf.total_trades = 15 # Force limit
    consensus_engine._update_agent_weights()
    
    # Weight should decrease below INITIAL weight due to poor metrics
    new_weight = consensus_engine.agent_weights["trend_follower"]
    assert new_weight < initial_weight

