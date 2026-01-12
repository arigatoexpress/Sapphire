import unittest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
import sys
import os

# Ensure project root is in path
sys.path.append(os.getcwd())

# Mock dependencies to prevent import errors from __init__ chains
sys.modules["prometheus_client"] = MagicMock()
sys.modules["cloud_trader.metrics"] = MagicMock()
sys.modules["cloud_trader.pubsub"] = MagicMock()
sys.modules["cloud_trader.risk"] = MagicMock()
sys.modules["cloud_trader.trading_service"] = MagicMock()

from cloud_trader.execution.algorithms import (
    ExecutionOrder, ExecutionAlgo, ExecutionResult,
    VWAPAlgorithm, SniperAlgorithm, AdaptiveAlgorithm, ArbitrageAlgorithm,
    AlgorithmicExecutor
)
from cloud_trader.data.data_fetcher import DataFetcher
from cloud_trader.execution.ml_selector import AlgoSelector

class TestPhase2Execution(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
        self.mock_executor = AsyncMock(return_value={"success": True, "price": 100.0, "quantity": 1.0})
        self.mock_data_fetcher = MagicMock(spec=DataFetcher)
        self.mock_data_fetcher.fetch_historical_volume = AsyncMock(return_value=[0.1]*24)
        self.mock_data_fetcher.fetch_current_price = AsyncMock(return_value=100.0)
        self.mock_data_fetcher.get_latest_price = MagicMock(return_value=0.0)
        self.mock_data_fetcher.fetch_atr = AsyncMock(return_value=0.02)
        self.mock_data_fetcher.start_price_stream = MagicMock()

    def tearDown(self):
        self.loop.close()

    def test_vwap_uses_real_volume(self):
        """Test VWAP fetches volume profile from DataFetcher."""
        algo = VWAPAlgorithm(self.mock_executor, self.mock_data_fetcher, duration_seconds=1)
        order = ExecutionOrder("BTC/USDT", "BUY", 10.0, algo=ExecutionAlgo.VWAP)
        
        result = self.loop.run_until_complete(algo.execute(order))
        
        self.assertTrue(result.success)
        self.mock_data_fetcher.fetch_historical_volume.assert_called_with("BTC/USDT", days=30)

    def test_sniper_uses_live_price(self):
        """Test Sniper checks live price."""
        # Setup: price improves to target
        # Target improvement 0.2% -> Buy limit < 99.8
        self.mock_data_fetcher.fetch_current_price.side_effect = [100.0, 99.9, 99.5] # Start, drop, hit
        
        algo = SniperAlgorithm(
            self.mock_executor, 
            self.mock_data_fetcher, 
            max_wait_seconds=2, 
            improvement_target_pct=0.002
        )
        order = ExecutionOrder("BTC/USDT", "BUY", 1.0, algo=ExecutionAlgo.SNIPER)
        
        result = self.loop.run_until_complete(algo.execute(order))
        
        self.assertTrue(result.success)
        self.mock_data_fetcher.start_price_stream.assert_called()
        self.assertTrue(self.mock_data_fetcher.fetch_current_price.call_count >= 2)

    @patch("cloud_trader.execution.algorithms.AlgoSelector")
    @patch("cloud_trader.execution.algorithms.SniperAlgorithm")
    def test_adaptive_ml_selection(self, MockSniper, MockSelector):
        """Test Adaptive algo queries ML model."""
        mock_selector_instance = MockSelector.return_value
        mock_selector_instance.predict.return_value = "sniper"
        
        # Setup mock sniper instance to return immediately
        mock_sniper_instance = MockSniper.return_value
        mock_sniper_instance.execute = AsyncMock(return_value=ExecutionResult(
            success=True, total_quantity=1.0, avg_price=100.0, total_slippage_pct=0, 
            slices=[], algo_used=ExecutionAlgo.SNIPER, execution_time_ms=100
        ))
        
        algo = AdaptiveAlgorithm(self.mock_executor, self.mock_data_fetcher)
        order = ExecutionOrder("BTC/USDT", "BUY", 1.0, algo=ExecutionAlgo.ADAPTIVE)
        
        result = self.loop.run_until_complete(algo.execute(order))
        
        self.assertEqual(result.algo_used, ExecutionAlgo.SNIPER)
        mock_selector_instance.predict.assert_called_once()
        # Verify market state contained fetched ATR
        call_args = mock_selector_instance.predict.call_args[0][0]
        self.assertEqual(call_args["volatility"], 0.02)

    def test_arbitrage_execution(self):
        """Test Arbitrage executes two legs."""
        # P1 = 100, P2 = 102 (2% diff > 0.5% min)
        self.mock_data_fetcher.fetch_current_price.side_effect = [100.0, 102.0] # Async calls
        
        algo = ArbitrageAlgorithm(self.mock_executor, self.mock_data_fetcher, min_profit_pct=0.005)
        # Buy lower (Symbol1 @ 100), Sell higher (Symbol2 @ 102)
        order = ExecutionOrder(
            "BTC/USDT", "BUY", 1.0, 
            algo=ExecutionAlgo.ARBITRAGE,
            metadata={"leg2_symbol": "BTC/FDUSD", "leg2_side": "SELL"}
        )
        
        result = self.loop.run_until_complete(algo.execute(order))
        
        self.assertTrue(result.success)
        self.assertEqual(self.mock_executor.call_count, 2)
        # Verify parallel calls (approx)
        self.mock_executor.assert_any_call("BTC/USDT", "BUY", 1.0)
        self.mock_executor.assert_any_call("BTC/FDUSD", "SELL", 1.0)

if __name__ == '__main__':
    unittest.main()
