"""
Episodic Trading Memory - Main Memory System

Provides storage, retrieval, and similarity search for trading episodes.
Uses vector embeddings for semantic similarity matching.

This is a novel contribution to the ACTS trading system.
"""

import asyncio
import json
import logging
import os
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .episode import Episode, TradeOutcome, create_episode

logger = logging.getLogger(__name__)


class EpisodicMemory:
    """
    Main episodic memory system for trading agents.

    Features:
    - Stores episodes with market context, decisions, and outcomes
    - Enables similarity search to find relevant past experiences
    - Prioritizes successful episodes for learning
    - Supports reflection and lesson extraction

    Storage:
    - In-memory deque for recent episodes (fast access)
    - File-based persistence for long-term storage
    - Vector embeddings for similarity search (using text-based matching for now)
    """

    def __init__(
        self,
        storage_path: Optional[str] = None,
        max_memory_episodes: int = 1000,
        max_recent_episodes: int = 100,
    ):
        """
        Initialize episodic memory.

        Args:
            storage_path: Path for persistent storage (if None, memory only)
            max_memory_episodes: Maximum episodes to keep in memory
            max_recent_episodes: Number of recent episodes for quick access
        """
        self.storage_path = Path(storage_path) if storage_path else None
        self.max_memory = max_memory_episodes
        self.max_recent = max_recent_episodes

        # In-memory storage
        self._episodes: Dict[str, Episode] = {}
        self._recent_queue: deque = deque(maxlen=max_recent_episodes)

        # Index by symbol for faster retrieval
        self._by_symbol: Dict[str, List[str]] = {}

        # Index by outcome (profitable vs unprofitable)
        self._profitable_ids: List[str] = []
        self._unprofitable_ids: List[str] = []

        # Stats
        self._total_stored = 0
        self._total_retrievals = 0

        # Load persisted episodes if available
        if self.storage_path:
            self._load_from_disk()

    async def store(self, episode: Episode) -> str:
        """
        Store an episode in memory.

        Returns the episode ID.
        """
        episode_id = episode.episode_id

        # Store in main dict
        self._episodes[episode_id] = episode
        self._recent_queue.append(episode_id)

        # Update indices
        if episode.symbol not in self._by_symbol:
            self._by_symbol[episode.symbol] = []
        self._by_symbol[episode.symbol].append(episode_id)

        # Update outcome indices
        if episode.outcome:
            if episode.was_profitable():
                self._profitable_ids.append(episode_id)
            else:
                self._unprofitable_ids.append(episode_id)

        self._total_stored += 1

        # Persist to disk (async)
        if self.storage_path:
            await self._persist_episode(episode)

        # Prune if over limit
        if len(self._episodes) > self.max_memory:
            self._prune_old_episodes()

        logger.debug(f"📝 Stored episode {episode_id} for {episode.symbol}")

        return episode_id

    async def update_outcome(
        self,
        episode_id: str,
        outcome: TradeOutcome,
    ) -> bool:
        """
        Update an episode with its outcome.

        Returns True if successful.
        """
        if episode_id not in self._episodes:
            logger.warning(f"Episode {episode_id} not found for outcome update")
            return False

        episode = self._episodes[episode_id]
        episode.outcome = outcome

        # Update outcome indices
        if episode.was_profitable():
            if episode_id not in self._profitable_ids:
                self._profitable_ids.append(episode_id)
        else:
            if episode_id not in self._unprofitable_ids:
                self._unprofitable_ids.append(episode_id)

        # Persist
        if self.storage_path:
            await self._persist_episode(episode)

        logger.info(f"📊 Updated outcome for {episode_id}: ${outcome.pnl:.2f}")

        return True

    async def add_reflection(
        self,
        episode_id: str,
        what_worked: str,
        what_failed: str,
        lesson: str,
    ) -> bool:
        """
        Add reflection to an episode.

        Returns True if successful.
        """
        if episode_id not in self._episodes:
            return False

        episode = self._episodes[episode_id]
        episode.what_worked = what_worked
        episode.what_failed = what_failed
        episode.lesson = lesson

        if self.storage_path:
            await self._persist_episode(episode)

        logger.info(f"💭 Added reflection to {episode_id}")

        return True

    async def recall_similar(
        self,
        current_state_text: str,
        symbol: Optional[str] = None,
        limit: int = 5,
        prefer_profitable: bool = True,
    ) -> List[Episode]:
        """
        Find episodes similar to the current market state.

        Uses text-based similarity matching. In a production system,
        this could use vector embeddings for better semantic matching.

        Args:
            current_state_text: Current market state as text
            symbol: Optional - filter by symbol
            limit: Maximum episodes to return
            prefer_profitable: If True, prioritize profitable episodes

        Returns:
            List of similar episodes, ordered by relevance
        """
        self._total_retrievals += 1

        candidates = []

        # Get candidate pool
        if symbol and symbol in self._by_symbol:
            candidate_ids = self._by_symbol[symbol]
        else:
            candidate_ids = list(self._episodes.keys())

        # Calculate similarity scores
        for episode_id in candidate_ids:
            episode = self._episodes.get(episode_id)
            if not episode:
                continue

            # Simple text similarity (word overlap)
            similarity = self._calculate_similarity(
                current_state_text, episode.market_state_embedding_text
            )

            # Boost profitable episodes
            if prefer_profitable and episode.was_profitable():
                similarity *= 1.3

            # Slight recency bonus
            age_days = (datetime.now() - episode.timestamp).days
            recency_bonus = max(0, 1 - age_days / 30) * 0.1
            similarity += recency_bonus

            candidates.append((episode, similarity))

        # Sort by similarity (highest first)
        candidates.sort(key=lambda x: x[1], reverse=True)

        # Return top results
        result = [ep for ep, _ in candidates[:limit]]

        logger.debug(f"🔍 Recalled {len(result)} similar episodes for {symbol or 'any'}")

        return result

    async def get_lessons_for_context(
        self,
        symbol: str,
        signal_type: str,
        limit: int = 3,
    ) -> str:
        """
        Get formatted lessons relevant to current context.

        Returns a text block suitable for injection into agent prompts.
        """
        # Get relevant episodes
        episodes = await self.recall_similar(
            current_state_text=f"{symbol} {signal_type}",
            symbol=symbol,
            limit=limit,
        )

        if not episodes:
            return ""

        lessons = []
        lessons.append("📚 **Lessons from Past Experience:**")

        for ep in episodes:
            if ep.lesson:
                emoji = "✅" if ep.was_profitable() else "❌"
                lessons.append(f"{emoji} {ep.lesson}")

        return "\n".join(lessons)

    def get_recent(self, limit: int = 10) -> List[Episode]:
        """Get most recent episodes."""
        recent_ids = list(self._recent_queue)[-limit:]
        return [self._episodes[eid] for eid in reversed(recent_ids) if eid in self._episodes]

    def get_by_id(self, episode_id: str) -> Optional[Episode]:
        """Get episode by ID."""
        return self._episodes.get(episode_id)

    def get_stats(self) -> Dict[str, Any]:
        """Get memory statistics."""
        completed = sum(1 for ep in self._episodes.values() if ep.is_complete())

        return {
            "total_stored": self._total_stored,
            "in_memory": len(self._episodes),
            "completed_episodes": completed,
            "profitable_count": len(self._profitable_ids),
            "unprofitable_count": len(self._unprofitable_ids),
            "total_retrievals": self._total_retrievals,
            "symbols_tracked": list(self._by_symbol.keys()),
        }

    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """
        Calculate simple text similarity using word overlap.

        In production, this should use vector embeddings (e.g., from Vertex AI)
        for proper semantic similarity.
        """
        if not text1 or not text2:
            return 0.0

        # Normalize and tokenize
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())

        if not words1 or not words2:
            return 0.0

        # Jaccard similarity
        intersection = len(words1 & words2)
        union = len(words1 | words2)

        return intersection / union if union > 0 else 0.0

    def _prune_old_episodes(self):
        """Remove oldest episodes when over memory limit."""
        # Sort by timestamp and remove oldest
        sorted_episodes = sorted(self._episodes.items(), key=lambda x: x[1].timestamp)

        # Keep newest max_memory episodes
        to_remove = len(sorted_episodes) - self.max_memory
        for episode_id, _ in sorted_episodes[:to_remove]:
            del self._episodes[episode_id]

        logger.debug(f"🧹 Pruned {to_remove} old episodes")

    async def _persist_episode(self, episode: Episode):
        """Persist episode to disk."""
        if not self.storage_path:
            return

        try:
            self.storage_path.mkdir(parents=True, exist_ok=True)
            filepath = self.storage_path / f"{episode.episode_id}.json"

            with open(filepath, "w") as f:
                json.dump(episode.to_dict(), f, indent=2)

        except Exception as e:
            logger.error(f"Failed to persist episode: {e}")

    def _load_from_disk(self):
        """Load episodes from disk storage."""
        if not self.storage_path or not self.storage_path.exists():
            return

        count = 0
        for filepath in self.storage_path.glob("*.json"):
            try:
                with open(filepath) as f:
                    data = json.load(f)
                    episode = Episode.from_dict(data)

                    # Add to memory structures
                    self._episodes[episode.episode_id] = episode

                    if episode.symbol not in self._by_symbol:
                        self._by_symbol[episode.symbol] = []
                    self._by_symbol[episode.symbol].append(episode.episode_id)

                    if episode.outcome:
                        if episode.was_profitable():
                            self._profitable_ids.append(episode.episode_id)
                        else:
                            self._unprofitable_ids.append(episode.episode_id)

                    count += 1

            except Exception as e:
                logger.warning(f"Failed to load episode from {filepath}: {e}")

        if count > 0:
            logger.info(f"📂 Loaded {count} episodes from disk")


# Global memory instance
_memory: Optional[EpisodicMemory] = None


def get_episodic_memory(
    storage_path: Optional[str] = None,
) -> EpisodicMemory:
    """Get global EpisodicMemory instance."""
    global _memory
    if _memory is None:
        # Default storage path in cloud_trader data directory
        if storage_path is None:
            storage_path = os.path.join(os.path.dirname(__file__), "..", "data", "episodes")
        _memory = EpisodicMemory(storage_path=storage_path)
    return _memory


async def store_episode(episode: Episode) -> str:
    """Convenience function to store an episode."""
    memory = get_episodic_memory()
    return await memory.store(episode)


async def recall_similar_episodes(
    current_state_text: str,
    symbol: Optional[str] = None,
    limit: int = 5,
) -> List[Episode]:
    """Convenience function to recall similar episodes."""
    memory = get_episodic_memory()
    return await memory.recall_similar(current_state_text, symbol, limit)
