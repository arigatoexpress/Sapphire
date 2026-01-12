"""
Cognitive Agent - Gemini-Powered Reasoning Agent Base Class

This module provides the base class for agents in the ACTS system.
Each agent uses Gemini to generate natural language reasoning.
"""

import asyncio
import logging
import os
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import google.generativeai as genai

from .cognitive_mesh import (
    AgentRole,
    CognitiveMesh,
    CognitiveMessage,
    MessageType,
    get_cognitive_mesh,
)

logger = logging.getLogger(__name__)


@dataclass
class MarketContext:
    """Context provided to the agent for reasoning."""

    symbol: str
    current_price: float
    price_change_1h: float
    price_change_24h: float
    volume_24h: float
    open_interest: Optional[float] = None
    funding_rate: Optional[float] = None
    order_book_imbalance: Optional[float] = None
    recent_trades: List[Dict[str, Any]] = None
    news_summary: Optional[str] = None

    def to_prompt(self) -> str:
        """Convert context to natural language for LLM."""
        parts = [
            f"**Symbol**: {self.symbol}",
            f"**Current Price**: ${self.current_price:,.2f}",
            f"**1H Change**: {self.price_change_1h:+.2f}%",
            f"**24H Change**: {self.price_change_24h:+.2f}%",
            f"**24H Volume**: ${self.volume_24h:,.0f}",
        ]

        if self.open_interest is not None:
            parts.append(f"**Open Interest**: ${self.open_interest:,.0f}")
        if self.funding_rate is not None:
            parts.append(f"**Funding Rate**: {self.funding_rate:.4f}%")
        if self.order_book_imbalance is not None:
            parts.append(
                f"**Order Book Imbalance**: {self.order_book_imbalance:+.2f} (positive = more bids)"
            )
        if self.news_summary:
            parts.append(f"**Recent News**: {self.news_summary}")

        return "\n".join(parts)


class CognitiveAgent(ABC):
    """
    Base class for all cognitive agents in the ACTS system.

    Each agent:
    - Has a specific role (Scout, Sniper, Oracle, etc.)
    - Uses Gemini to generate natural language reasoning
    - Communicates via the CognitiveMesh
    - Can participate in consensus decisions
    """

    def __init__(
        self,
        agent_id: str,
        role: AgentRole,
        model_name: str = "gemini-2.0-flash",
    ):
        self.agent_id = agent_id
        self.role = role
        self.model_name = model_name
        self.mesh: Optional[CognitiveMesh] = None

        # Initialize Gemini
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if api_key:
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel(model_name)
            logger.info(f"🧠 Agent {agent_id} using {model_name}")
        else:
            logger.warning(f"⚠️ Agent {agent_id}: No API key, running in mock mode")
            self.model = None

        # Agent state
        self.message_count = 0
        self.last_reasoning_time_ms = 0.0

    async def connect(self, mesh: Optional[CognitiveMesh] = None) -> None:
        """Connect this agent to the cognitive mesh."""
        self.mesh = mesh or get_cognitive_mesh()
        await self.mesh.register_agent(
            self.agent_id,
            self.role,
            capabilities=self.get_capabilities(),
        )

        # Subscribe to relevant messages
        self.mesh.subscribe(f"all", self._on_mesh_message)
        logger.info(f"🔗 Agent {self.agent_id} connected to mesh")

    @abstractmethod
    def get_capabilities(self) -> List[str]:
        """Return list of capabilities this agent provides."""
        pass

    @abstractmethod
    def get_system_prompt(self) -> str:
        """Return the system prompt that defines this agent's personality and role."""
        pass

    @abstractmethod
    async def analyze(self, context: MarketContext) -> CognitiveMessage:
        """Analyze market context and generate a cognitive message."""
        pass

    async def _on_mesh_message(self, message: CognitiveMessage) -> None:
        """Handle incoming messages from the mesh."""
        # Override in subclasses for custom behavior
        if message.agent_id != self.agent_id:
            logger.debug(
                f"Agent {self.agent_id} received: {message.message_type.value} from {message.agent_id}"
            )

    async def reason(self, prompt: str, max_tokens: int = 512) -> str:
        """
        Use Gemini to generate natural language reasoning.

        This is the core intelligence method that all agents share.
        """
        if not self.model:
            # Mock mode for testing
            return f"[MOCK] Reasoning about: {prompt[:100]}..."

        start_time = time.time()

        try:
            full_prompt = f"{self.get_system_prompt()}\n\n{prompt}"

            response = await asyncio.to_thread(
                lambda: self.model.generate_content(
                    full_prompt,
                    generation_config=genai.types.GenerationConfig(
                        max_output_tokens=max_tokens,
                        temperature=0.7,
                    ),
                )
            )

            self.last_reasoning_time_ms = (time.time() - start_time) * 1000
            logger.debug(f"Reasoning took {self.last_reasoning_time_ms:.0f}ms")

            return response.text

        except Exception as e:
            logger.error(f"Reasoning failed: {e}")
            return f"Error in reasoning: {str(e)}"

    async def broadcast(
        self,
        message_type: MessageType,
        reasoning: str,
        symbol: Optional[str] = None,
        suggested_action: Optional[str] = None,
        confidence: float = 0.0,
        metadata: Dict[str, Any] = None,
    ) -> CognitiveMessage:
        """Broadcast a cognitive message to the mesh."""
        message = CognitiveMessage(
            message_id=f"{self.agent_id}-{uuid.uuid4().hex[:8]}",
            agent_id=self.agent_id,
            agent_role=self.role,
            message_type=message_type,
            reasoning=reasoning,
            symbol=symbol,
            suggested_action=suggested_action,
            confidence=confidence,
            metadata=metadata or {},
        )

        if self.mesh:
            await self.mesh.broadcast(message)

        self.message_count += 1
        return message


class ScoutAgent(CognitiveAgent):
    """
    Scout Agent - Market observation and pattern detection.

    The Scout watches markets continuously and broadcasts observations
    when it detects something interesting.
    """

    def __init__(self, agent_id: str = "scout-1"):
        super().__init__(agent_id, AgentRole.SCOUT, "gemini-2.0-flash")

    def get_capabilities(self) -> List[str]:
        return ["market_observation", "pattern_detection", "anomaly_detection"]

    def get_system_prompt(self) -> str:
        return """You are SCOUT, a market observation agent in an autonomous trading swarm.

Your role is to:
1. Observe market conditions and detect patterns
2. Identify unusual activity (volume spikes, order book imbalances, etc.)
3. Provide early warnings about potential opportunities or risks

You speak concisely and precisely. Your observations should be:
- Factual (based on the data provided)
- Actionable (what does this mean for trading?)
- Confident (rate your confidence 0.0 to 1.0)

Format your response as:
OBSERVATION: [What you see]
IMPLICATION: [What this might mean]
SUGGESTED_ACTION: [BUY/SELL/HOLD/WAIT]
CONFIDENCE: [0.0-1.0]"""

    async def analyze(self, context: MarketContext) -> CognitiveMessage:
        """Analyze market context and generate an observation."""
        prompt = f"""Analyze this market data and provide your observation:

{context.to_prompt()}

Provide a concise analysis following your role as SCOUT."""

        reasoning = await self.reason(prompt)

        # Parse the response (simple parsing)
        action = "HOLD"
        confidence = 0.5

        if "SUGGESTED_ACTION:" in reasoning:
            action_line = reasoning.split("SUGGESTED_ACTION:")[1].split("\n")[0].strip()
            if "BUY" in action_line.upper():
                action = "BUY"
            elif "SELL" in action_line.upper():
                action = "SELL"

        if "CONFIDENCE:" in reasoning:
            try:
                conf_line = reasoning.split("CONFIDENCE:")[1].split("\n")[0].strip()
                confidence = float(conf_line)
            except:
                pass

        return await self.broadcast(
            message_type=MessageType.OBSERVATION,
            reasoning=reasoning,
            symbol=context.symbol,
            suggested_action=action,
            confidence=confidence,
        )


class SniperAgent(CognitiveAgent):
    """
    Sniper Agent - Execution timing and precision.

    The Sniper validates observations and determines optimal entry/exit points.
    """

    def __init__(self, agent_id: str = "sniper-1"):
        super().__init__(agent_id, AgentRole.SNIPER, "gemini-2.0-flash")

    def get_capabilities(self) -> List[str]:
        return ["execution_timing", "entry_analysis", "exit_analysis", "order_book_reading"]

    def get_system_prompt(self) -> str:
        return """You are SNIPER, an execution timing specialist in an autonomous trading swarm.

Your role is to:
1. Validate observations from SCOUT agents
2. Determine precise entry and exit points
3. Analyze order book depth for optimal execution

You are precise and tactical. Your recommendations should include:
- Entry zone (price range)
- Position size relative to standard (0.5x, 1x, 1.5x, 2x)
- Stop loss level
- Take profit target

Format your response as:
VALIDATION: [Agree/Disagree with observation]
ENTRY_ZONE: [Price range]
POSITION_SIZE: [Multiplier]
STOP_LOSS: [Price]
TAKE_PROFIT: [Price]
CONFIDENCE: [0.0-1.0]"""

    async def analyze(self, context: MarketContext) -> CognitiveMessage:
        """Analyze for execution timing."""
        prompt = f"""Analyze this market for execution timing:

{context.to_prompt()}

Provide precise entry/exit levels following your role as SNIPER."""

        reasoning = await self.reason(prompt)

        # Parse confidence
        confidence = 0.5
        if "CONFIDENCE:" in reasoning:
            try:
                conf_line = reasoning.split("CONFIDENCE:")[1].split("\n")[0].strip()
                confidence = float(conf_line)
            except:
                pass

        action = "HOLD"
        if "VALIDATION: Agree" in reasoning:
            action = "BUY"  # Would need more context for actual action

        return await self.broadcast(
            message_type=MessageType.VALIDATION,
            reasoning=reasoning,
            symbol=context.symbol,
            suggested_action=action,
            confidence=confidence,
        )


class OracleAgent(CognitiveAgent):
    """
    Oracle Agent - Consensus arbiter and final decision authority.

    The Oracle aggregates inputs from other agents and makes final decisions.
    Uses the more powerful Gemini Pro for deep analysis.
    """

    def __init__(self, agent_id: str = "oracle-1"):
        super().__init__(agent_id, AgentRole.ORACLE, "gemini-2.0-flash")

    def get_capabilities(self) -> List[str]:
        return ["consensus_arbitration", "risk_assessment", "final_decision", "strategy_synthesis"]

    def get_system_prompt(self) -> str:
        return """You are ORACLE, the consensus arbiter in an autonomous trading swarm.

Your role is to:
1. Synthesize observations from SCOUT and validations from SNIPER
2. Consider macro conditions and risk factors
3. Make final trading decisions with full reasoning

You are wise and measured. You weigh all perspectives before deciding.
Your decisions must balance reward potential against risk.

Format your response as:
SYNTHESIS: [Summary of inputs]
RISK_ASSESSMENT: [Key risks]
DECISION: [BUY/SELL/HOLD with size multiplier]
REASONING: [Why this decision]
CONFIDENCE: [0.0-1.0]"""

    async def analyze(self, context: MarketContext) -> CognitiveMessage:
        """Make final decision based on all available information."""
        # Get recent messages from mesh for context
        recent_observations = []
        if self.mesh:
            recent = self.mesh.get_recent_messages(limit=10, symbol=context.symbol)
            recent_observations = [f"[{m.agent_role.value}] {m.reasoning[:200]}" for m in recent]

        observations_text = (
            "\n".join(recent_observations) if recent_observations else "No recent observations."
        )

        prompt = f"""As ORACLE, synthesize this information and make a final decision:

MARKET DATA:
{context.to_prompt()}

RECENT SWARM OBSERVATIONS:
{observations_text}

Provide your final decision with full reasoning."""

        reasoning = await self.reason(prompt, max_tokens=1024)

        # Parse decision
        action = "HOLD"
        confidence = 0.5

        if "DECISION:" in reasoning:
            decision_line = reasoning.split("DECISION:")[1].split("\n")[0].strip().upper()
            if "BUY" in decision_line:
                action = "BUY"
            elif "SELL" in decision_line:
                action = "SELL"

        if "CONFIDENCE:" in reasoning:
            try:
                conf_line = reasoning.split("CONFIDENCE:")[1].split("\n")[0].strip()
                confidence = float(conf_line)
            except:
                pass

        return await self.broadcast(
            message_type=MessageType.CONSENSUS,
            reasoning=reasoning,
            symbol=context.symbol,
            suggested_action=action,
            confidence=confidence,
        )


async def run_cognitive_swarm_demo():
    """Demo: Run a simple cognitive swarm analysis."""
    mesh = get_cognitive_mesh()

    # Create agents
    scout = ScoutAgent()
    sniper = SniperAgent()
    oracle = OracleAgent()

    # Connect to mesh
    await scout.connect(mesh)
    await sniper.connect(mesh)
    await oracle.connect(mesh)

    # Simulate market context
    context = MarketContext(
        symbol="SOL",
        current_price=142.50,
        price_change_1h=2.3,
        price_change_24h=5.7,
        volume_24h=850_000_000,
        open_interest=2_100_000_000,
        funding_rate=0.0012,
        order_book_imbalance=0.15,
    )

    # Run analysis chain
    print("🔭 SCOUT analyzing...")
    scout_msg = await scout.analyze(context)
    print(f"Scout says: {scout_msg.reasoning[:200]}...")

    print("\n🎯 SNIPER validating...")
    sniper_msg = await sniper.analyze(context)
    print(f"Sniper says: {sniper_msg.reasoning[:200]}...")

    print("\n🔮 ORACLE deciding...")
    oracle_msg = await oracle.analyze(context)
    print(f"Oracle decides: {oracle_msg.reasoning[:300]}...")

    # Show consensus if reached
    print("\n📊 FINAL DECISION:")
    print(f"Action: {oracle_msg.suggested_action}")
    print(f"Confidence: {oracle_msg.confidence}")
    print(f"Reasoning Hash: {oracle_msg.get_reasoning_hash()}")


if __name__ == "__main__":
    asyncio.run(run_cognitive_swarm_demo())
