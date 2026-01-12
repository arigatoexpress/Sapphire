"""
Episodic Memory Bank - Regime Learning and Experience Recall

This module enables the ACTS system to remember past market regimes,
successful strategies, and lessons learned from trades.

Key Concepts:
- Episode: A distinct market period with learnable patterns
- Memory Retrieval: Find similar past situations before making decisions
- Lesson Extraction: AI-generated insights from trade outcomes
"""

import asyncio
import hashlib
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import google.generativeai as genai

logger = logging.getLogger(__name__)


@dataclass
class MarketEpisode:
    """
    A distinct period in market history with learnable patterns.

    Episodes capture:
    - The market regime (volatile, trending, ranging, etc.)
    - What happened during the period
    - What trading actions were taken
    - The outcomes of those actions
    - AI-extracted lessons
    """

    episode_id: str
    name: str

    # Time bounds
    start_time: datetime
    end_time: Optional[datetime] = None

    # Market context
    regime: str = "unknown"  # "high_volatility", "trending_up", "trending_down", "ranging"
    key_events: List[str] = field(default_factory=list)
    symbols_involved: List[str] = field(default_factory=list)

    # Quantitative summary
    price_change_pct: float = 0.0
    volume_change_pct: float = 0.0
    max_drawdown_pct: float = 0.0

    # Actions taken
    trades: List[Dict[str, Any]] = field(default_factory=list)

    # Outcomes
    total_pnl: float = 0.0
    win_rate: float = 0.0

    # AI-generated lesson
    lesson: Optional[str] = None
    tags: List[str] = field(default_factory=list)

    # Embedding for similarity search (would be populated by vector DB)
    embedding: Optional[List[float]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for storage."""
        return {
            "episode_id": self.episode_id,
            "name": self.name,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "regime": self.regime,
            "key_events": self.key_events,
            "symbols_involved": self.symbols_involved,
            "price_change_pct": self.price_change_pct,
            "volume_change_pct": self.volume_change_pct,
            "max_drawdown_pct": self.max_drawdown_pct,
            "trades": self.trades,
            "total_pnl": self.total_pnl,
            "win_rate": self.win_rate,
            "lesson": self.lesson,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MarketEpisode":
        """Deserialize from storage."""
        return cls(
            episode_id=data["episode_id"],
            name=data["name"],
            start_time=datetime.fromisoformat(data["start_time"]),
            end_time=datetime.fromisoformat(data["end_time"]) if data.get("end_time") else None,
            regime=data.get("regime", "unknown"),
            key_events=data.get("key_events", []),
            symbols_involved=data.get("symbols_involved", []),
            price_change_pct=data.get("price_change_pct", 0.0),
            volume_change_pct=data.get("volume_change_pct", 0.0),
            max_drawdown_pct=data.get("max_drawdown_pct", 0.0),
            trades=data.get("trades", []),
            total_pnl=data.get("total_pnl", 0.0),
            win_rate=data.get("win_rate", 0.0),
            lesson=data.get("lesson"),
            tags=data.get("tags", []),
        )

    def get_summary(self) -> str:
        """Generate human-readable summary."""
        duration = (self.end_time - self.start_time).total_seconds() / 3600 if self.end_time else 0
        return f"""Episode: {self.name}
Regime: {self.regime}
Duration: {duration:.1f}h
PnL: ${self.total_pnl:+,.2f} ({self.win_rate*100:.0f}% win rate)
Lesson: {self.lesson or 'None extracted yet'}"""


class EpisodicMemoryBank:
    """
    Long-term memory for market regimes and trading lessons.

    Enables the swarm to:
    - Remember what happened in similar market conditions
    - Avoid repeating past mistakes
    - Build on successful patterns
    """

    def __init__(self, storage_path: Optional[str] = None):
        self.episodes: Dict[str, MarketEpisode] = {}
        self.storage_path = storage_path or "/tmp/sapphire_memory.json"
        self.current_episode: Optional[MarketEpisode] = None

        # AI for lesson extraction
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if api_key:
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel("gemini-2.0-pro-exp-02-05")
        else:
            self.model = None

        # Load existing memories
        self._load()

    def _load(self):
        """Load episodes from storage."""
        try:
            if os.path.exists(self.storage_path):
                with open(self.storage_path, "r") as f:
                    data = json.load(f)
                    for ep_data in data.get("episodes", []):
                        ep = MarketEpisode.from_dict(ep_data)
                        self.episodes[ep.episode_id] = ep
                logger.info(f"📚 Loaded {len(self.episodes)} episodes from memory")
        except Exception as e:
            logger.warning(f"Could not load memory: {e}")

    def _save(self):
        """Persist episodes to storage."""
        try:
            data = {
                "episodes": [ep.to_dict() for ep in self.episodes.values()],
                "saved_at": datetime.utcnow().isoformat(),
            }
            with open(self.storage_path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Could not save memory: {e}")

    def start_episode(
        self,
        name: str,
        regime: str,
        symbols: List[str] = None,
    ) -> MarketEpisode:
        """Start recording a new market episode."""
        episode_id = f"ep-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"

        self.current_episode = MarketEpisode(
            episode_id=episode_id,
            name=name,
            start_time=datetime.utcnow(),
            regime=regime,
            symbols_involved=symbols or [],
        )

        logger.info(f"📝 Started episode: {name}")
        return self.current_episode

    def end_episode(
        self,
        price_change_pct: float = 0.0,
        volume_change_pct: float = 0.0,
        max_drawdown_pct: float = 0.0,
    ) -> Optional[MarketEpisode]:
        """End the current episode and calculate outcomes."""
        if not self.current_episode:
            return None

        ep = self.current_episode
        ep.end_time = datetime.utcnow()
        ep.price_change_pct = price_change_pct
        ep.volume_change_pct = volume_change_pct
        ep.max_drawdown_pct = max_drawdown_pct

        # Calculate trade outcomes
        if ep.trades:
            wins = sum(1 for t in ep.trades if t.get("pnl", 0) > 0)
            ep.win_rate = wins / len(ep.trades)
            ep.total_pnl = sum(t.get("pnl", 0) for t in ep.trades)

        # Store episode
        self.episodes[ep.episode_id] = ep
        self.current_episode = None
        self._save()

        logger.info(f"📚 Episode ended: {ep.name} (PnL: ${ep.total_pnl:+,.2f})")
        return ep

    def record_trade(self, trade_data: Dict[str, Any]):
        """Record a trade in the current episode."""
        if self.current_episode:
            self.current_episode.trades.append(trade_data)

    def record_event(self, event: str):
        """Record a key event in the current episode."""
        if self.current_episode:
            self.current_episode.key_events.append(event)

    async def extract_lesson(self, episode: MarketEpisode) -> str:
        """Use Gemini Pro to extract a lesson from the episode."""
        if not self.model:
            return "Lesson extraction unavailable (no API key)"

        prompt = f"""Analyze this trading episode and extract a key lesson:

{episode.get_summary()}

Trades taken:
{json.dumps(episode.trades[:10], indent=2)}  # Limit for token budget

Key events: {', '.join(episode.key_events[:5])}

Extract ONE concise lesson (max 2 sentences) that would help in similar future situations.
Focus on actionable insights, not obvious statements.

Lesson:"""

        try:
            response = await asyncio.to_thread(
                lambda: self.model.generate_content(
                    prompt,
                    generation_config=genai.types.GenerationConfig(
                        max_output_tokens=128,
                        temperature=0.5,
                    ),
                )
            )

            lesson = response.text.strip()
            episode.lesson = lesson
            self._save()

            logger.info(f"📖 Lesson extracted for {episode.name}: {lesson}")
            return lesson

        except Exception as e:
            logger.error(f"Lesson extraction failed: {e}")
            return f"Error: {e}"

    def find_similar_episodes(
        self,
        regime: str,
        symbols: List[str] = None,
        limit: int = 3,
    ) -> List[MarketEpisode]:
        """
        Find episodes similar to current market conditions.

        In production, this would use vector similarity on embeddings.
        For now, uses simple matching on regime and symbols.
        """
        matches = []

        for ep in self.episodes.values():
            score = 0

            # Regime match
            if ep.regime == regime:
                score += 2

            # Symbol overlap
            if symbols:
                overlap = len(set(ep.symbols_involved) & set(symbols))
                score += overlap

            if score > 0:
                matches.append((score, ep))

        # Sort by score descending
        matches.sort(key=lambda x: x[0], reverse=True)

        return [ep for _, ep in matches[:limit]]

    async def recall_for_decision(
        self,
        symbol: str,
        current_regime: str,
        context: str = "",
    ) -> str:
        """
        Generate memory-informed advice for a trading decision.

        Queries past episodes and synthesizes lessons.
        """
        similar = self.find_similar_episodes(current_regime, [symbol])

        if not similar:
            return "No relevant past episodes found."

        lessons = []
        for ep in similar:
            if ep.lesson:
                lessons.append(f"- {ep.name}: {ep.lesson}")

        if not lessons:
            return "Similar episodes found, but no lessons extracted yet."

        memory_prompt = f"""Based on past experience in similar {current_regime} conditions:

{chr(10).join(lessons)}

Current situation: {context}

What should we remember before trading {symbol}?"""

        if self.model:
            try:
                response = await asyncio.to_thread(
                    lambda: self.model.generate_content(
                        memory_prompt,
                        generation_config=genai.types.GenerationConfig(
                            max_output_tokens=256,
                            temperature=0.5,
                        ),
                    )
                )
                return response.text.strip()
            except Exception as e:
                logger.error(f"Memory recall failed: {e}")
                return chr(10).join(lessons)
        else:
            return chr(10).join(lessons)

    def get_stats(self) -> Dict[str, Any]:
        """Get memory bank statistics."""
        total_pnl = sum(ep.total_pnl for ep in self.episodes.values())
        total_trades = sum(len(ep.trades) for ep in self.episodes.values())

        regime_counts = {}
        for ep in self.episodes.values():
            regime_counts[ep.regime] = regime_counts.get(ep.regime, 0) + 1

        return {
            "total_episodes": len(self.episodes),
            "total_trades": total_trades,
            "total_pnl": total_pnl,
            "regimes": regime_counts,
            "lessons_extracted": sum(1 for ep in self.episodes.values() if ep.lesson),
        }


# Global instance
_memory_instance: Optional[EpisodicMemoryBank] = None


def get_episodic_memory() -> EpisodicMemoryBank:
    """Get or create the global episodic memory instance."""
    global _memory_instance
    if _memory_instance is None:
        _memory_instance = EpisodicMemoryBank()
    return _memory_instance


async def demo_episodic_memory():
    """Demo the episodic memory system."""
    memory = get_episodic_memory()

    # Simulate an episode
    print("📝 Starting episode...")
    memory.start_episode(
        name="SOL Breakout Jan 2026",
        regime="trending_up",
        symbols=["SOL"],
    )

    # Record some trades
    memory.record_trade(
        {
            "symbol": "SOL",
            "side": "BUY",
            "quantity": 10,
            "entry_price": 142.50,
            "exit_price": 158.00,
            "pnl": 155.00,
            "timestamp": datetime.utcnow().isoformat(),
        }
    )

    memory.record_event("Volume spike 3x average")
    memory.record_event("Broke through 150 resistance")

    # End episode
    ep = memory.end_episode(
        price_change_pct=12.5,
        volume_change_pct=200.0,
        max_drawdown_pct=3.5,
    )

    # Extract lesson
    if ep:
        print("\n📖 Extracting lesson...")
        lesson = await memory.extract_lesson(ep)
        print(f"Lesson: {lesson}")

    # Query memory
    print("\n🔍 Recalling for new decision...")
    advice = await memory.recall_for_decision(
        symbol="SOL",
        current_regime="trending_up",
        context="SOL breaking above previous high with volume",
    )
    print(f"Memory says: {advice}")

    print(f"\n📊 Memory stats: {memory.get_stats()}")


if __name__ == "__main__":
    asyncio.run(demo_episodic_memory())
