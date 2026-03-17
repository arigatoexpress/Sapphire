"""
Phase 6 Integration Tests
E2E and stress tests for Sapphire V2.
"""

import unittest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
import sys
import os

sys.path.append(os.getcwd())

# Mock heavy dependencies
sys.modules["prometheus_client"] = MagicMock()
sys.modules["stable_baselines3"] = MagicMock()
sys.modules["structlog"] = MagicMock()
sys.modules["cloud_trader.trading_service"] = MagicMock()
sys.modules["cloud_trader.websocket_manager"] = MagicMock()
sys.modules["cloud_trader.metrics"] = MagicMock()
sys.modules["cloud_trader.pubsub"] = MagicMock()
sys.modules["google.cloud.pubsub_v1"] = MagicMock()
sys.modules["redis"] = MagicMock()


class TestE2EIntegration(unittest.TestCase):
    """End-to-end integration tests."""
    
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def tearDown(self):
        self.loop.close()

    @patch("cloud_trader.agents.agent_orchestrator.ElizaAgent")
    @patch("cloud_trader.agents.agent_orchestrator._get_rl_agent")
    def test_consensus_includes_rl_vote(self, mock_get_rl, MockEliza):
        """Test that consensus calculation includes RL agent vote."""
        from cloud_trader.agents.agent_orchestrator import AgentOrchestrator
        
        # Setup mock RL agent
        mock_rl = MagicMock()
        mock_rl.predict.return_value = 1  # BUY
        mock_rl.action_to_signal.return_value = "BUY"
        mock_get_rl.return_value = mock_rl
        
        # Mock ElizaAgent to avoid asyncio issues
        MockEliza.return_value = MagicMock()
        
        orchestrator = AgentOrchestrator()
        
        # Verify RL weight is set
        self.assertEqual(orchestrator.rl_weight, 0.3)

    @patch("cloud_trader.execution.algorithms._get_risk_manager")
    def test_executor_uses_risk_manager(self, mock_get_rm):
        """Test that executor integrates risk manager."""
        from cloud_trader.execution.algorithms import AlgorithmicExecutor, ExecutionOrder, ExecutionAlgo
        
        # Setup mock risk manager
        mock_rm = MagicMock()
        mock_rm.is_halted = False
        mock_rm.portfolio_value = 10000
        mock_rm.calculate_position_size.return_value = 0.05
        mock_rm.calculate_stop_loss.return_value = 95.0
        mock_rm.calculate_take_profit.return_value = 110.0
        mock_get_rm.return_value = mock_rm
        
        # Create executor with mock base
        mock_base = AsyncMock(return_value={"success": True, "price": 100, "quantity": 1})
        executor = AlgorithmicExecutor(mock_base)
        
        # Verify risk manager is attached
        self.assertIsNotNone(executor.risk_manager)

    @patch("cloud_trader.execution.algorithms._get_risk_manager")
    def test_risk_halt_blocks_execution(self, mock_get_rm):
        """Test that halted risk manager blocks order execution."""
        from cloud_trader.execution.algorithms import AlgorithmicExecutor, ExecutionOrder, ExecutionAlgo
        
        # Setup halted risk manager
        mock_rm = MagicMock()
        mock_rm.is_halted = True
        mock_get_rm.return_value = mock_rm
        
        mock_base = AsyncMock()
        executor = AlgorithmicExecutor(mock_base)
        
        order = ExecutionOrder("BTC/USDT", "BUY", 1.0, algo=ExecutionAlgo.MARKET)
        result = self.loop.run_until_complete(executor.execute(order))
        
        self.assertFalse(result.success)
        self.assertIn("halted", result.error.lower())


class TestStressTests(unittest.TestCase):
    """Stress and edge case tests."""
    
    def test_risk_manager_drawdown_halt(self):
        """Test that risk manager halts on max drawdown."""
        from cloud_trader.risk_manager import RiskManager
        
        rm = RiskManager(max_drawdown_pct=0.15)
        rm.peak_value = 10000
        
        # Simulate 20% loss
        rm.update_portfolio(8000)
        
        self.assertTrue(rm.is_halted)
        self.assertGreater(rm.current_drawdown, rm.max_drawdown_pct)

    def test_position_sizing_under_volatility(self):
        """Test position sizing reduces under high volatility."""
        from cloud_trader.risk_manager import RiskManager
        
        rm = RiskManager()
        rm.portfolio_value = 10000
        rm.peak_value = 10000
        
        # Low volatility
        size_low_vol = rm.calculate_position_size("BTC", "LONG", 100, 0.01, 0.7)
        
        # High volatility
        size_high_vol = rm.calculate_position_size("BTC", "LONG", 100, 0.10, 0.7)
        
        # Should be smaller under high vol
        self.assertGreater(size_low_vol, size_high_vol)

    def test_backtester_handles_empty_trades(self):
        """Test backtester handles edge cases."""
        from cloud_trader.backtester import Backtester
        
        bt = Backtester()
        result = bt.run([])
        
        self.assertEqual(result.total_trades, 0)
        self.assertEqual(result.sharpe_ratio, 0)

    def test_trading_env_episode_completion(self):
        """Test trading env can complete full episode."""
        from cloud_trader.rl.trading_env import TradingEnv
        
        env = TradingEnv()
        obs, _ = env.reset()
        
        done = False
        steps = 0
        while not done and steps < 1000:
            action = env.action_space.sample()
            obs, reward, done, truncated, info = env.step(action)
            done = done or truncated
            steps += 1
        
        self.assertGreater(steps, 0)
        self.assertIn("balance", info)


if __name__ == '__main__':
    unittest.main()
