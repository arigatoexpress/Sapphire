import unittest
import asyncio
from unittest.mock import MagicMock, patch
import sys
import os
import numpy as np
from datetime import datetime, timedelta

sys.path.append(os.getcwd())

# Mock heavy dependencies
sys.modules["prometheus_client"] = MagicMock()
sys.modules["stable_baselines3"] = MagicMock()
sys.modules["structlog"] = MagicMock()
sys.modules["cloud_trader.trading_service"] = MagicMock()
sys.modules["cloud_trader.websocket_manager"] = MagicMock()
sys.modules["cloud_trader.metrics"] = MagicMock()
sys.modules["cloud_trader.pubsub"] = MagicMock()
sys.modules["cloud_trader.risk"] = MagicMock()

from cloud_trader.rl.trading_env import TradingEnv
from cloud_trader.risk_manager import RiskManager, Position, RiskLevel
from cloud_trader.backtester import Backtester, Trade, BacktestResult


class TestTradingEnv(unittest.TestCase):
    def test_env_creation(self):
        """Test environment initializes correctly."""
        env = TradingEnv()
        
        self.assertEqual(env.initial_balance, 10000.0)
        self.assertEqual(env.action_space.n, 4)
        self.assertIsNotNone(env.observation_space)

    def test_env_reset(self):
        """Test environment reset."""
        env = TradingEnv()
        obs, info = env.reset()
        
        self.assertEqual(len(obs), env.observation_space.shape[0])
        self.assertEqual(env.position, 0.0)
        self.assertEqual(env.balance, 10000.0)

    def test_env_step(self):
        """Test environment step."""
        env = TradingEnv()
        env.reset()
        
        # Take BUY action
        obs, reward, done, truncated, info = env.step(1)
        
        self.assertFalse(done)
        self.assertIn("balance", info)
        self.assertIn("position", info)


class TestRiskManager(unittest.TestCase):
    def setUp(self):
        self.rm = RiskManager()
        self.rm.portfolio_value = 10000
        self.rm.peak_value = 10000

    def test_position_sizing(self):
        """Test dynamic position sizing."""
        size = self.rm.calculate_position_size(
            symbol="BTC/USDT",
            side="LONG",
            entry_price=50000,
            volatility=0.02,
            confidence=0.7
        )
        
        self.assertGreater(size, 0)
        self.assertLessEqual(size, self.rm.max_position_pct)

    def test_stop_loss_calculation(self):
        """Test stop-loss calculation."""
        stop = self.rm.calculate_stop_loss(
            entry_price=100,
            side="LONG",
            volatility=0.02
        )
        
        self.assertLess(stop, 100)  # Stop is below entry for LONG

    def test_drawdown_halt(self):
        """Test trading halt on max drawdown."""
        self.rm.peak_value = 10000
        self.rm.update_portfolio(8400)  # 16% drawdown
        
        self.assertTrue(self.rm.is_halted)
        self.assertEqual(self.rm.get_risk_level(), RiskLevel.CRITICAL)

    def test_position_update_stop_loss(self):
        """Test stop-loss trigger."""
        pos = Position(
            symbol="BTC/USDT",
            side="LONG",
            size=1.0,
            entry_price=100,
            stop_loss=95,
            take_profit=110
        )
        self.rm.add_position(pos)
        
        # Price drops below stop
        result = self.rm.update_position("BTC/USDT", 94)
        self.assertEqual(result, "STOP_LOSS")


class TestBacktester(unittest.TestCase):
    def setUp(self):
        self.backtester = Backtester(initial_capital=10000)
        
        # Create sample trades
        base_time = datetime.now()
        self.trades = [
            Trade("BTC", "LONG", 100, 110, 1.0, base_time, base_time + timedelta(days=1)),
            Trade("BTC", "LONG", 110, 105, 1.0, base_time + timedelta(days=2), base_time + timedelta(days=3)),
            Trade("BTC", "LONG", 105, 120, 1.0, base_time + timedelta(days=4), base_time + timedelta(days=5)),
        ]

    def test_backtest_run(self):
        """Test backtest execution."""
        result = self.backtester.run(self.trades)
        
        self.assertEqual(result.total_trades, 3)
        self.assertGreater(result.total_return, 0)  # Net positive
        self.assertGreater(result.win_rate, 0)

    def test_sharpe_ratio(self):
        """Test Sharpe ratio calculation."""
        result = self.backtester.run(self.trades)
        
        # Should be a valid number
        self.assertFalse(np.isnan(result.sharpe_ratio))

    def test_sortino_ratio(self):
        """Test Sortino ratio calculation."""
        result = self.backtester.run(self.trades)
        
        self.assertFalse(np.isnan(result.sortino_ratio))

    def test_max_drawdown(self):
        """Test max drawdown calculation."""
        result = self.backtester.run(self.trades)
        
        self.assertGreaterEqual(result.max_drawdown, 0)
        self.assertLessEqual(result.max_drawdown, 1)

    def test_empty_trades(self):
        """Test backtest with no trades."""
        result = self.backtester.run([])
        
        self.assertEqual(result.total_trades, 0)
        self.assertEqual(result.total_return, 0)


if __name__ == '__main__':
    unittest.main()
