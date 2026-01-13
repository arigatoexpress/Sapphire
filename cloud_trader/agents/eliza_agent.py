"""
Sapphire V2 ElizaAgent
Next-generation trading agent inspired by ElizaOS patterns.

Features:
- Memory-augmented decision making (RAG-like retrieval)
- Multi-model support (GPT-4, Claude, Gemini, Llama)
- Personality-driven analysis
- Self-improving feedback loops
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


class ModelProvider(Enum):
    """Supported AI model providers."""

    GEMINI = "gemini"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    LOCAL = "local"  # Llama, etc.


@dataclass
class AgentConfig:
    """Configuration for an ElizaAgent."""

    agent_id: str
    name: str
    personality: str = "analytical"  # analytical, aggressive, conservative, contrarian
    primary_model: ModelProvider = ModelProvider.GEMINI
    fallback_model: ModelProvider = ModelProvider.OPENAI
    specialization: str = "hybrid"  # technical, sentiment, orderflow, hybrid
    confidence_threshold: float = 0.65
    memory_depth: int = 100  # Number of memories to retain
    exploration_rate: float = 0.1


@dataclass
class Thesis:
    """Agent's trading thesis with full context."""

    symbol: str
    signal: str  # BUY, SELL, HOLD
    confidence: float
    reasoning: str
    agent_id: str = ""
    model_used: str = ""
    memories_referenced: int = 0
    processing_time_ms: int = 0
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "signal": self.signal,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "agent_id": self.agent_id,
            "model_used": self.model_used,
            "memories_referenced": self.memories_referenced,
            "processing_time_ms": self.processing_time_ms,
            "timestamp": self.timestamp,
        }


class ElizaAgent:
    """
    Memory-augmented, multi-model trading agent.

    Inspired by ElizaOS architecture:
    - Retrieves relevant memories before making decisions
    - Uses personality to shape analysis style
    - Supports multiple AI models with intelligent fallback
    - Learns from trade outcomes
    """

    def __init__(self, config: AgentConfig, memory_manager=None, model_router=None):
        self.config = config
        self.id = config.agent_id
        self.name = config.name

        # Dependencies (injected or created)
        from .memory_manager import MemoryManager
        from .model_router import MultiModelRouter

        # Create memory manager with agent_id for namespaced persistence
        self.memory = memory_manager or MemoryManager(
            agent_id=config.agent_id,
            max_memories=config.memory_depth,
            persist=True,  # Enable Firestore persistence
        )
        self.models = model_router or MultiModelRouter()

        # Performance tracking
        self.total_trades = 0
        self.winning_trades = 0
        self.total_pnl = 0.0

        logger.info(f"🤖 ElizaAgent '{self.name}' initialized ({config.specialization})")

    async def analyze(self, symbol: str, market_data: Optional[Dict] = None) -> Thesis:
        """
        Analyze a symbol and generate a trading thesis.

        Process:
        1. Retrieve relevant memories (past trades, patterns)
        2. Build analysis prompt with personality
        3. Query AI model
        4. Parse and validate thesis
        5. Store for future reference
        """
        start_time = time.time()

        try:
            # 1. Retrieve relevant memories
            memories = await self.memory.retrieve(symbol, limit=5)

            # 2. Build prompt
            prompt = self._build_analysis_prompt(symbol, memories, market_data)

            # 3. Query model with retry
            @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
            async def _query_with_retry():
                return await self.models.query(
                    prompt=prompt,
                    primary=self.config.primary_model,
                    fallback=self.config.fallback_model,
                )

            response = await _query_with_retry()

            # 4. Parse thesis from response
            thesis = self._parse_thesis(symbol, response)
            thesis.agent_id = self.id
            thesis.model_used = response.get("model", "unknown")
            thesis.memories_referenced = len(memories)
            thesis.processing_time_ms = int((time.time() - start_time) * 1000)

            # 5. Store for future reference
            await self.memory.store(
                {
                    "type": "analysis",
                    "symbol": symbol,
                    "thesis": thesis.to_dict(),
                    "timestamp": time.time(),
                }
            )

            logger.info(
                f"🧠 [{self.name}] {symbol}: {thesis.signal} "
                f"(conf: {thesis.confidence:.2f}, {thesis.processing_time_ms}ms)"
            )

            return thesis

        except Exception as e:
            logger.error(f"❌ [{self.name}] Analysis error: {e}")
            return Thesis(
                symbol=symbol,
                signal="HOLD",
                confidence=0.0,
                reasoning=f"Error: {e}",
                agent_id=self.id,
                processing_time_ms=int((time.time() - start_time) * 1000),
            )

    def _build_analysis_prompt(
        self, symbol: str, memories: List[Dict], market_data: Optional[Dict]
    ) -> str:
        """Build the analysis prompt with personality and context."""

        # Personality-driven system prompt
        personality_prompts = {
            "analytical": "You are a methodical quantitative analyst. Focus on data and statistics.",
            "aggressive": "You are an aggressive trader seeking high-conviction opportunities.",
            "conservative": "You are a conservative risk manager. Prioritize capital preservation.",
            "contrarian": "You are a contrarian trader. Look for opportunities where the crowd is wrong.",
        }

        system = personality_prompts.get(self.config.personality, personality_prompts["analytical"])

        # Build context from memories
        memory_context = ""
        if memories:
            memory_context = "\n\nRelevant past experiences:\n"
            for mem in memories[:5]:
                if mem.get("type") == "trade_outcome":
                    pnl = mem.get("pnl", 0)
                    outcome = "profit" if pnl > 0 else "loss"
                    memory_context += f"- {mem.get('symbol')}: {outcome} ({pnl:.2f}%) - {mem.get('lesson', 'N/A')}\n"
                elif mem.get("type") == "analysis":
                    memory_context += (
                        f"- Previous analysis: {mem.get('thesis', {}).get('reasoning', 'N/A')}\n"
                    )

        # Market data context
        data_context = ""
        if market_data:
            data_context = f"\n\nCurrent market data:\n"
            for key, value in market_data.items():
                data_context += f"- {key}: {value}\n"

        prompt = f"""
{system}

Analyze {symbol} and provide a trading recommendation.
{memory_context}
{data_context}

Your win rate so far: {self.get_win_rate():.1%}

Respond in this exact format:
SIGNAL: [BUY/SELL/HOLD]
CONFIDENCE: [0.0-1.0]
REASONING: [Your analysis in 1-2 sentences]
"""

        return prompt

    def _build_analysis_prompt(
        self, symbol: str, memories: List[Dict], market_data: Optional[Dict]
    ) -> str:
        """Build the analysis prompt with personality and CoT context."""

        # Personality-driven system prompt
        personality_prompts = {
            "analytical": "You are a methodical quantitative analyst. Focus on data and statistics.",
            "aggressive": "You are an aggressive trader seeking high-conviction opportunities.",
            "conservative": "You are a conservative risk manager. Prioritize capital preservation.",
            "contrarian": "You are a contrarian trader. Look for opportunities where the crowd is wrong.",
        }

        system = personality_prompts.get(self.config.personality, personality_prompts["analytical"])

        # Build context from memories
        memory_context = ""
        if memories:
            memory_context = "\n\nRelevant past experiences:\n"
            for mem in memories[:5]:
                if mem.get("type") == "trade_outcome":
                    pnl = mem.get("pnl", 0)
                    outcome = "profit" if pnl > 0 else "loss"
                    memory_context += f"- {mem.get('symbol')}: {outcome} ({pnl:.2f}%) - {mem.get('lesson', 'N/A')}\n"
                elif mem.get("type") == "analysis":
                    memory_context += (
                        f"- Previous analysis: {mem.get('thesis', {}).get('reasoning', 'N/A')}\n"
                    )

        # Market data context
        data_context = ""
        if market_data:
            data_context = f"\n\nCurrent market data:\n"
            for key, value in market_data.items():
                data_context += f"- {key}: {value}\n"

        # Community/Telegram signals context
        telegram_context = ""
        try:
            from ..telegram_listener import _telegram_listener
            if _telegram_listener:
                telegram_context = _telegram_listener.format_for_agent(symbol)
                if telegram_context and "No recent" not in telegram_context:
                    telegram_context = f"\n\n{telegram_context}\n"
                else:
                    telegram_context = ""
        except Exception:
            pass  # Telegram listener not available

        prompt = f"""
{system}

Analyze {symbol} using a step-by-step Chain-of-Thought approach.

{memory_context}
{data_context}
{telegram_context}

Your win rate so far: {self.get_win_rate():.1%}

Format your response exactly as follows:
OBSERVE: [List key market data points and indicators]
REASON: [Analyze the implications of observations, risks, and alignment with your strategy]
CONCLUDE: [Final verdict based on reasoning]
SIGNAL: [BUY/SELL/HOLD]
CONFIDENCE: [0.0-1.0]

Example:
OBSERVE: Price up 5% in 1h, Volume 2x avg, RSI 75 (overbought).
REASON: Momentum is strong but overbought conditions suggest pullback risk. However, volume confirms strength.
CONCLUDE: Bullish short-term but tight stop needed.
SIGNAL: BUY
CONFIDENCE: 0.75
"""
        return prompt

    def _parse_thesis(self, symbol: str, response: Dict) -> Thesis:
        """Parse the model response into a Thesis."""
        text = response.get("text", "")

        # Default values
        signal = "HOLD"
        confidence = 0.0
        reasoning = "Unable to parse response"

        try:
            lines = text.strip().split("\n")
            cot_parts = {"OBSERVE": "", "REASON": "", "CONCLUDE": ""}
            current_section = None

            for line in lines:
                line = line.strip()
                if line.startswith("SIGNAL:"):
                    s = line.replace("SIGNAL:", "").strip().upper()
                    if s in ["BUY", "SELL", "HOLD"]:
                        signal = s
                    current_section = None
                elif line.startswith("CONFIDENCE:"):
                    try:
                        c = float(line.replace("CONFIDENCE:", "").strip())
                        confidence = max(0.0, min(1.0, c))
                    except:
                        pass
                    current_section = None
                elif line.startswith("OBSERVE:"):
                    cot_parts["OBSERVE"] = line.replace("OBSERVE:", "").strip()
                    current_section = "OBSERVE"
                elif line.startswith("REASON:"):
                    cot_parts["REASON"] = line.replace("REASON:", "").strip()
                    current_section = "REASON"
                elif line.startswith("CONCLUDE:"):
                    cot_parts["CONCLUDE"] = line.replace("CONCLUDE:", "").strip()
                    current_section = "CONCLUDE"
                elif current_section:
                    # Append continuation lines to current section
                    cot_parts[current_section] += " " + line
            
            # Combine CoT parts into reasoning if structured data usage failing legacy REASONING format
            if any(cot_parts.values()):
                reasoning = (
                    f"OBSERVE: {cot_parts['OBSERVE']} | "
                    f"REASON: {cot_parts['REASON']} | "
                    f"CONCLUDE: {cot_parts['CONCLUDE']}"
                )
            # Fallback to old behavior if needed, or if REASONING was used (though prompt doesn't ask for it anymore)
                
        except Exception as e:
            logger.warning(f"Parse error: {e}")

        return Thesis(symbol=symbol, signal=signal, confidence=confidence, reasoning=reasoning)

    async def learn_from_trade(self, thesis: Thesis, pnl_pct: float):
        """Update agent based on trade outcome."""
        self.total_trades += 1
        self.total_pnl += pnl_pct

        if pnl_pct > 0:
            self.winning_trades += 1

        # Store outcome in memory for future reference
        lesson = "Successful strategy" if pnl_pct > 0 else "Review entry criteria"

        await self.memory.store(
            {
                "type": "trade_outcome",
                "symbol": thesis.symbol,
                "signal": thesis.signal,
                "pnl": pnl_pct,
                "reasoning": thesis.reasoning,
                "lesson": lesson,
                "timestamp": time.time(),
            }
        )

        logger.info(
            f"📚 [{self.name}] Learned from {thesis.symbol}: "
            f"{pnl_pct:+.2%} | Win rate: {self.get_win_rate():.1%}"
        )

    def get_win_rate(self) -> float:
        """Get current win rate."""
        if self.total_trades == 0:
            return 0.0
        return self.winning_trades / self.total_trades

    def get_stats(self) -> Dict[str, Any]:
        """Get agent statistics."""
        return {
            "id": self.id,
            "name": self.name,
            "personality": self.config.personality,
            "specialization": self.config.specialization,
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "win_rate": self.get_win_rate(),
            "total_pnl": self.total_pnl,
            "memory_size": self.memory.size(),
            "primary_model": self.config.primary_model.value,
        }
