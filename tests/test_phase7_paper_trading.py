"""
Phase 7 Tests - Paper Trading & Enhanced Backtesting
"""

import unittest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
import sys
import os
from datetime import datetime, timedelta

sys.path.append(os.getcwd())

# Mock heavy dependencies
sys.modules["prometheus_client"] = MagicMock()
sys.modules["stable_baselines3"] = MagicMock()
sys.modules["structlog"] = MagicMock()
sys.modules["ccxt"] = MagicMock()
sys.modules["ccxt.async_support"] = MagicMock()


class TestEnhancedBacktester(unittest.TestCase):
    """Tests for enhanced backtester with fees and OOS validation."""
    
    def setUp(self):
        from cloud_trader.backtester import EnhancedBacktester, Trade
        
        self.backtester = EnhancedBacktester(
            initial_capital=10000,
            fee_pct=0.001,
            slippage_pct=0.0005
        )
        
        # Create sample trades
        base_time = datetime.now()
        self.trades = [
            Trade("BTC", "LONG", 100, 110, 1.0, base_time, base_time + timedelta(days=1)),
            Trade("BTC", "LONG", 110, 105, 1.0, base_time + timedelta(days=2), base_time + timedelta(days=3)),
            Trade("BTC", "LONG", 105, 120, 1.0, base_time + timedelta(days=4), base_time + timedelta(days=5)),
            Trade("BTC", "LONG", 120, 125, 1.0, base_time + timedelta(days=6), base_time + timedelta(days=7)),
        ]

    def test_run_with_frictions(self):
        """Test that frictions reduce returns."""
        from cloud_trader.backtester import Trade
        # Run without frictions
        result_clean = self.backtester.run(self.trades)
        
        # Run with frictions
        result_friction = self.backtester.run_with_frictions(self.trades)
        
        # Frictions should reduce total return
        self.assertLessEqual(result_friction.total_return, result_clean.total_return)

    def test_out_of_sample_split(self):
        """Test OOS split produces train/test results."""
        results = self.backtester.run_out_of_sample(self.trades, train_ratio=0.5)
        
        self.assertIn("in_sample", results)
        self.assertIn("out_of_sample", results)
        self.assertEqual(results["in_sample"].total_trades + results["out_of_sample"].total_trades, len(self.trades))

    def test_strategy_validation(self):
        """Test strategy validation with thresholds."""
        validation = self.backtester.validate_strategy(
            self.trades,
            min_sharpe=0.0,  # Low threshold for test
            max_drawdown=0.99  # High threshold for test
        )
        
        self.assertIn("passed", validation)
        self.assertIn("warnings", validation)


class TestPaperTrader(unittest.TestCase):
    """Tests for paper trading module."""
    
    def setUp(self):
        from cloud_trader.paper_trader import PaperTrader
        self.trader = PaperTrader(
            testnet=True,
            initial_balance=10000,
            slippage_pct=0.001,
            fee_pct=0.001
        )

    def test_portfolio_initialization(self):
        """Test portfolio starts with correct balance."""
        self.assertEqual(self.trader.portfolio.initial_balance, 10000)
        self.assertEqual(self.trader.portfolio.cash, 10000)
        self.assertEqual(len(self.trader.portfolio.positions), 0)

    def test_execute_buy_order(self):
        """Test simulated buy order execution."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Mock price fetch
        self.trader._price_cache["BTC/USDT"] = 100.0
        
        async def run_test():
            trade = await self.trader.execute_order("BTC/USDT", "BUY", 1.0)
            return trade
        
        trade = loop.run_until_complete(run_test())
        loop.close()
        
        self.assertEqual(trade.symbol, "BTC/USDT")
        self.assertEqual(trade.side, "BUY")
        self.assertGreater(self.trader.portfolio.positions.get("BTC/USDT", 0), 0)

    def test_insufficient_cash_rejection(self):
        """Test order rejected when insufficient cash."""
        from cloud_trader.paper_trader import PaperTradeStatus
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Set price high enough to exceed balance
        self.trader._price_cache["BTC/USDT"] = 20000.0
        
        async def run_test():
            trade = await self.trader.execute_order("BTC/USDT", "BUY", 1.0)
            return trade
        
        trade = loop.run_until_complete(run_test())
        loop.close()
        
        self.assertEqual(trade.status, PaperTradeStatus.REJECTED)


class TestKillSwitches(unittest.TestCase):
    """Tests for kill switch functionality."""
    
    def test_kill_switch_properties(self):
        """Test SapphireApp kill switch properties."""
        from cloud_trader.main import SapphireApp
        
        app = SapphireApp()
        
        # Initially trading should be enabled
        self.assertTrue(app.is_trading_enabled)
        
        # Pause should disable
        app._paused = True
        self.assertFalse(app.is_trading_enabled)
        
        # Resume
        app._paused = False
        self.assertTrue(app.is_trading_enabled)
        
        # Kill switch should disable
        app._kill_switch_active = True
        self.assertFalse(app.is_trading_enabled)


if __name__ == "__main__":
    unittest.main()
