

import asyncio
import unittest
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.append(os.getcwd())

# Mock dependencies to avoid ImportError from cloud_trader __init__
sys.modules["cloud_trader.trading_service"] = MagicMock()
sys.modules["cloud_trader.risk"] = MagicMock()
sys.modules["cloud_trader.pubsub"] = MagicMock()
sys.modules["cloud_trader.metrics"] = MagicMock()
sys.modules["prometheus_client"] = MagicMock()
sys.modules["google.cloud"] = MagicMock()
sys.modules["google.cloud.firestore"] = MagicMock()

from cloud_trader.agents.eliza_agent import ElizaAgent, AgentConfig, Thesis
from cloud_trader.agents.agent_orchestrator import AgentOrchestrator, ConsensusResult
from cloud_trader.agents.memory_manager import MemoryManager

class TestSapphireV2(unittest.TestCase):

    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def tearDown(self):
        self.loop.close()

    @patch("cloud_trader.agents.memory_manager.MemoryManager")
    def test_cot_prompt_parsing(self, MockMemoryManager):
        """Test parsing of new CoT format."""
        MockMemoryManager.return_value = MagicMock()
        agent = ElizaAgent(AgentConfig(agent_id="test", name="Test"))
        
        response_text = """
        OBSERVE: Price up, Volume high
        REASON: Momentum is strong
        CONCLUDE: Buy confirmed
        SIGNAL: BUY
        CONFIDENCE: 0.85
        """
        
        thesis = agent._parse_thesis("BTC-USDC", {"text": response_text})
        
        self.assertEqual(thesis.signal, "BUY")
        self.assertEqual(thesis.confidence, 0.85)
        self.assertIn("OBSERVE: Price up", thesis.reasoning)
        self.assertIn("REASON: Momentum", thesis.reasoning)
        self.assertIn("CONCLUDE: Buy", thesis.reasoning)

    @patch("cloud_trader.agents.agent_orchestrator.ElizaAgent")
    def test_sigmoid_weighting(self, MockAgent):
        """Test Sigmoid weighting favors high performance/confidence."""
        orchestrator = AgentOrchestrator()
        
        # Mock agents with different win rates
        agent_good = MagicMock()
        agent_good.get_win_rate.return_value = 0.8
        agent_good.name = "GoodAgent"
        
        agent_bad = MagicMock()
        agent_bad.get_win_rate.return_value = 0.3
        agent_bad.name = "BadAgent"
        
        orchestrator.agents = {"good": agent_good, "bad": agent_bad}
        
        # Theses
        thesis_good = Thesis(
            symbol="BTC", signal="BUY", confidence=0.9, 
            reasoning="Good", agent_id="good"
        )
        thesis_bad = Thesis(
            symbol="BTC", signal="SELL", confidence=0.9, 
            reasoning="Bad", agent_id="bad"
        )
        
        # Calculate consensus
        # weight = 1 / (1 + exp(-5 * (conf * win_rate - 0.5)))
        # Good: 0.9 * 0.8 = 0.72. x-0.5 = 0.22. -5*0.22 = -1.1. exp(-1.1) ~= 0.33. 1/1.33 ~= 0.75
        # Bad: 0.9 * 0.3 = 0.27. x-0.5 = -0.23. -5*-0.23 = 1.15. exp(1.15) ~= 3.15. 1/4.15 ~= 0.24
        
        result = orchestrator._calculate_consensus("BTC", [thesis_good, thesis_bad])
        
        # Good agent (BUY) should win despite equal confidence, due to win rate
        self.assertEqual(result.signal, "BUY")
        self.assertTrue(result.confidence > 0.0)

    @patch("cloud_trader.agents.memory_manager._get_embedding_model")
    @patch("cloud_trader.agents.memory_manager._get_firestore_client")
    def test_vector_memory_integration(self, mock_firestore, mock_get_model):
        """Test MemoryManager vector integration."""
        
        # Mock embedding model
        mock_model = MagicMock()
        mock_model.encode.return_value = [[0.1] * 384] # Mock vector
        mock_get_model.return_value = mock_model
        
        # Mock FAISS
        with patch("cloud_trader.agents.memory_manager.MemoryManager._init_faiss") as mock_init:
            manager = MemoryManager(persist=False)
            manager._index = MagicMock()
            manager._index.ntotal = 0
            
            # Test Store
            async def run_store():
                await manager.store({
                    "type": "analysis",
                    "symbol": "BTC", 
                    "thesis": {"reasoning": "test"}
                })
            
            self.loop.run_until_complete(run_store())
            
            # Verify added to FAISS
            manager._index.add.assert_called()
            
            # Test Retrieve with query (Semantic)
            manager._index.ntotal = 1
            manager._index.search.return_value = ([[0.0]], [[0]]) # distance, index
            manager._id_map = {0: manager._memories[0]["_id"]}
            
            async def run_retrieve():
                return await manager.retrieve(query_text="semantic search")
                
            results = self.loop.run_until_complete(run_retrieve())
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["symbol"], "BTC")

    @patch("cloud_trader.agents.agent_orchestrator.ElizaAgent")
    def test_debrief_cycle(self, MockAgent):
        """Test learn_from_trade triggers debrief."""
        orchestrator = AgentOrchestrator()
        
        # Mock agent
        agent = AsyncMock()
        agent.models.query.return_value = {"text": "LESSON: Don't chase pumps"}
        agent.id = "quant-alpha"
        orchestrator.agents = {"quant-alpha": agent}
        
        # Run learn_from_trade
        async def run_learn():
            await orchestrator.learn_from_trade("BTC", "BUY", -0.05)
            
        self.loop.run_until_complete(run_learn())
        
        # Verify agent queried for lesson
        agent.models.query.assert_called()
        
        # Verify agent.learn_from_trade called with lesson in reasoning
        call_args = agent.learn_from_trade.call_args[0]
        thesis = call_args[0]
        self.assertIn("Lesson: Don't chase pumps", thesis.reasoning)

if __name__ == "__main__":
    unittest.main()
