"""
Episodic Trading Memory - Decision Episodes

The core data structure for recording trading decisions and outcomes.
Enables agents to learn from experience through structured reflection.

This is a novel contribution to the ACTS trading system.
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class TradeOutcome:
    """Structured outcome of a trade."""

    success: bool = False
    pnl: float = 0.0
    pnl_percent: float = 0.0
    max_drawdown: float = 0.0
    max_profit: float = 0.0
    hold_duration_seconds: float = 0.0
    exit_reason: str = ""  # "take_profit", "stop_loss", "manual", "timeout"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "pnl": self.pnl,
            "pnl_percent": self.pnl_percent,
            "max_drawdown": self.max_drawdown,
            "max_profit": self.max_profit,
            "hold_duration_seconds": self.hold_duration_seconds,
            "exit_reason": self.exit_reason,
        }


@dataclass
class Episode:
    """
    A complete trading episode: context → decision → outcome → reflection.

    This is the fundamental unit of agent memory. Episodes are indexed
    for semantic search, allowing agents to find similar past situations
    and learn from outcomes.
    """

    # Identity
    episode_id: str = ""
    timestamp: datetime = field(default_factory=datetime.now)

    # Context (UMEP MarketStateTensor as text)
    market_state_text: str = ""
    market_state_embedding_text: str = ""  # Optimized for similarity search

    # The symbol being traded
    symbol: str = ""
    platform: str = ""

    # Decision
    signal_type: str = ""  # "LONG", "SHORT", "HOLD"
    entry_price: float = 0.0
    quantity: float = 0.0
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None

    # Agent reasoning
    agent_id: str = ""
    agent_reasoning: str = ""
    confidence: float = 0.0

    # Outcome (filled after trade closes)
    outcome: Optional[TradeOutcome] = None

    # Reflection (LLM-generated after outcome)
    what_worked: str = ""
    what_failed: str = ""
    lesson: str = ""

    # Metadata
    tags: List[str] = field(default_factory=list)

    def __post_init__(self):
        """Generate episode ID if not provided."""
        if not self.episode_id:
            # Create deterministic ID from key fields
            content = f"{self.timestamp.isoformat()}-{self.symbol}-{self.signal_type}"
            self.episode_id = hashlib.sha256(content.encode()).hexdigest()[:16]

    def is_complete(self) -> bool:
        """Check if episode has outcome and reflection."""
        return self.outcome is not None and bool(self.lesson)

    def was_profitable(self) -> bool:
        """Check if the trade was profitable."""
        return self.outcome is not None and self.outcome.pnl > 0

    def to_context_text(self) -> str:
        """
        Generate text for providing context in a new decision.

        This is what gets injected into agent prompts when
        recalling similar past episodes.
        """
        parts = []

        parts.append(f"📅 {self.timestamp.strftime('%Y-%m-%d %H:%M')}")
        parts.append(f"Symbol: {self.symbol} | Signal: {self.signal_type}")
        parts.append(f"Entry: ${self.entry_price:.2f} | Confidence: {self.confidence:.0%}")

        if self.outcome:
            emoji = "✅" if self.was_profitable() else "❌"
            parts.append(f"{emoji} PnL: ${self.outcome.pnl:.2f} ({self.outcome.pnl_percent:+.1f}%)")

        if self.lesson:
            parts.append(f"💡 Lesson: {self.lesson}")

        return "\n".join(parts)

    def to_reflection_prompt_context(self) -> str:
        """
        Generate context for the reflection agent prompt.
        """
        lines = [
            f"# Trade Episode Review",
            f"",
            f"## Market Context",
            self.market_state_text,
            f"",
            f"## Decision Made",
            f"- Symbol: {self.symbol}",
            f"- Signal: {self.signal_type}",
            f"- Entry: ${self.entry_price:.2f}",
            f"- Confidence: {self.confidence:.0%}",
            f"- Reasoning: {self.agent_reasoning}",
            f"",
        ]

        if self.outcome:
            lines.extend(
                [
                    f"## Outcome",
                    f"- PnL: ${self.outcome.pnl:.2f} ({self.outcome.pnl_percent:+.1f}%)",
                    f"- Max Drawdown: ${self.outcome.max_drawdown:.2f}",
                    f"- Exit Reason: {self.outcome.exit_reason}",
                    f"- Hold Duration: {self.outcome.hold_duration_seconds:.0f}s",
                ]
            )

        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for storage."""
        return {
            "episode_id": self.episode_id,
            "timestamp": self.timestamp.isoformat(),
            "market_state_text": self.market_state_text,
            "market_state_embedding_text": self.market_state_embedding_text,
            "symbol": self.symbol,
            "platform": self.platform,
            "signal_type": self.signal_type,
            "entry_price": self.entry_price,
            "quantity": self.quantity,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "agent_id": self.agent_id,
            "agent_reasoning": self.agent_reasoning,
            "confidence": self.confidence,
            "outcome": self.outcome.to_dict() if self.outcome else None,
            "what_worked": self.what_worked,
            "what_failed": self.what_failed,
            "lesson": self.lesson,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Episode":
        """Deserialize from dictionary."""
        outcome = None
        if data.get("outcome"):
            outcome = TradeOutcome(**data["outcome"])

        return cls(
            episode_id=data.get("episode_id", ""),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            market_state_text=data.get("market_state_text", ""),
            market_state_embedding_text=data.get("market_state_embedding_text", ""),
            symbol=data.get("symbol", ""),
            platform=data.get("platform", ""),
            signal_type=data.get("signal_type", ""),
            entry_price=data.get("entry_price", 0),
            quantity=data.get("quantity", 0),
            stop_loss=data.get("stop_loss"),
            take_profit=data.get("take_profit"),
            agent_id=data.get("agent_id", ""),
            agent_reasoning=data.get("agent_reasoning", ""),
            confidence=data.get("confidence", 0),
            outcome=outcome,
            what_worked=data.get("what_worked", ""),
            what_failed=data.get("what_failed", ""),
            lesson=data.get("lesson", ""),
            tags=data.get("tags", []),
        )

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls, json_str: str) -> "Episode":
        """Deserialize from JSON string."""
        return cls.from_dict(json.loads(json_str))


def create_episode(
    symbol: str,
    signal_type: str,
    entry_price: float,
    market_state_text: str,
    agent_id: str = "unknown",
    agent_reasoning: str = "",
    confidence: float = 0.5,
    platform: str = "unknown",
) -> Episode:
    """Factory function to create a new Episode."""
    return Episode(
        symbol=symbol,
        signal_type=signal_type,
        entry_price=entry_price,
        market_state_text=market_state_text,
        market_state_embedding_text=market_state_text[:500],  # First 500 chars for embedding
        agent_id=agent_id,
        agent_reasoning=agent_reasoning,
        confidence=confidence,
        platform=platform,
    )
