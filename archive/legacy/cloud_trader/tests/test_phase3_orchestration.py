import unittest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
import sys
import os

sys.path.append(os.getcwd())

# Mock heavy dependencies
sys.modules["prometheus_client"] = MagicMock()
sys.modules["cloud_trader.metrics"] = MagicMock()
sys.modules["cloud_trader.pubsub"] = MagicMock()
sys.modules["cloud_trader.risk"] = MagicMock()
sys.modules["cloud_trader.trading_service"] = MagicMock()
sys.modules["redis"] = MagicMock()
sys.modules["google.cloud.pubsub_v1"] = MagicMock()

from cloud_trader.core.state_manager import StateManager, _in_memory_store
from cloud_trader.core.event_handler import EventHandler, MarketEventTypes, create_market_event


class TestStateManager(unittest.TestCase):
    def setUp(self):
        # Clear in-memory store
        _in_memory_store.clear()
        self.state_manager = StateManager(namespace="test")
        # Force in-memory mode
        self.state_manager.redis = None

    def test_save_and_load_state(self):
        """Test saving and loading state."""
        data = {"symbol": "BTC/USDT", "position": 1.5}
        
        self.assertTrue(self.state_manager.save_state("test_key", data))
        loaded = self.state_manager.load_state("test_key")
        
        self.assertEqual(loaded["symbol"], "BTC/USDT")
        self.assertEqual(loaded["position"], 1.5)

    def test_load_missing_key(self):
        """Test loading non-existent key returns default."""
        result = self.state_manager.load_state("missing", default={"empty": True})
        self.assertEqual(result, {"empty": True})

    def test_delete_state(self):
        """Test deleting state."""
        self.state_manager.save_state("to_delete", {"data": 1})
        self.assertTrue(self.state_manager.delete_state("to_delete"))
        self.assertIsNone(self.state_manager.load_state("to_delete"))

    def test_execution_slice_helpers(self):
        """Test typed helpers for execution slices."""
        slice_data = {"quantity": 10, "price": 100.0}
        
        self.state_manager.save_execution_slice("order123", slice_data)
        loaded = self.state_manager.load_execution_slice("order123")
        
        self.assertEqual(loaded["quantity"], 10)


class TestEventHandler(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.event_handler = EventHandler(project_id="test-project")
        # Force no real Pub/Sub
        self.event_handler.subscriber = None
        self.event_handler.publisher = None

    def tearDown(self):
        self.loop.close()

    def test_subscribe_registers_callback(self):
        """Test subscribing registers callbacks."""
        callback = MagicMock()
        
        self.event_handler.subscribe("test-sub", callback)
        
        self.assertIn("test-sub", self.event_handler._callbacks)
        self.assertEqual(len(self.event_handler._callbacks["test-sub"]), 1)

    def test_simulate_event_invokes_callback(self):
        """Test simulating events invokes callbacks."""
        callback = MagicMock()
        self.event_handler.subscribe("test-sub", callback)
        
        event_data = {"type": "test", "data": {"value": 42}}
        self.loop.run_until_complete(self.event_handler.simulate_event("test-sub", event_data))
        
        callback.assert_called_once_with(event_data)

    def test_create_market_event(self):
        """Test market event creation helper."""
        event = create_market_event(
            MarketEventTypes.PRICE_UPDATE,
            "BTC/USDT",
            {"price": 50000.0}
        )
        
        self.assertEqual(event["type"], "price_update")
        self.assertEqual(event["symbol"], "BTC/USDT")
        self.assertIn("timestamp", event)
        self.assertEqual(event["data"]["price"], 50000.0)


class TestOrchestratorIntegration(unittest.TestCase):
    """Integration tests for event-driven orchestrator."""
    
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def tearDown(self):
        self.loop.close()

    @patch("cloud_trader.core.orchestrator.StateManager")
    @patch("cloud_trader.core.orchestrator.EventHandler")
    def test_event_handler_invoked_on_market_event(self, MockEventHandler, MockStateManager):
        """Test that market events trigger the handler."""
        from cloud_trader.core.orchestrator import TradingOrchestrator, OrchestratorConfig
        
        # Setup mocks
        mock_event_handler = MockEventHandler.return_value
        mock_event_handler.start_listening = AsyncMock()
        mock_event_handler.stop_listening = AsyncMock()
        mock_event_handler.subscribe = MagicMock()
        
        mock_state_manager = MockStateManager.return_value
        mock_state_manager.load_orchestrator_state.return_value = None
        mock_state_manager.save_orchestrator_state.return_value = True
        
        # Create orchestrator - won't actually start full system in unit test
        orchestrator = TradingOrchestrator()
        orchestrator.config.event_driven = True
        
        # Verify event handler was initialized
        MockEventHandler.assert_called()


if __name__ == '__main__':
    unittest.main()
