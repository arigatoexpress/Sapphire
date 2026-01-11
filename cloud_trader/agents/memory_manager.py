"""
Sapphire V2 Memory Manager
RAG-like memory system for trading agents.

Stores and retrieves:
- Past trade outcomes
- Market patterns
- Successful thesis templates
- Learned lessons
"""

import asyncio
import logging
import time
from collections import deque
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class MemoryManager:
    """
    Persistent agent memory with retrieval capabilities.

    Inspired by ElizaOS RAG pattern:
    - Store memories with metadata
    - Retrieve by symbol, recency, or embedding similarity
    - Auto-prune old memories
    """

    def __init__(self, max_memories: int = 100):
        self.max_memories = max_memories
        self._memories: deque = deque(maxlen=max_memories)
        self._symbol_index: Dict[str, List[int]] = {}  # symbol -> memory indices
        logger.info(f"🧠 MemoryManager initialized (max: {max_memories})")

    async def store(self, memory: Dict[str, Any]) -> bool:
        """Store a new memory."""
        try:
            # Add timestamp if not present
            if "timestamp" not in memory:
                memory["timestamp"] = time.time()

            # Store with unique ID
            memory["_id"] = len(self._memories)
            self._memories.append(memory)

            # Update symbol index
            symbol = memory.get("symbol")
            if symbol:
                if symbol not in self._symbol_index:
                    self._symbol_index[symbol] = []
                self._symbol_index[symbol].append(memory["_id"])

            return True

        except Exception as e:
            logger.error(f"Memory store error: {e}")
            return False

    async def retrieve(
        self, symbol: Optional[str] = None, memory_type: Optional[str] = None, limit: int = 10
    ) -> List[Dict]:
        """
        Retrieve relevant memories.

        Args:
            symbol: Filter by trading symbol
            memory_type: Filter by type (analysis, trade_outcome, pattern)
            limit: Maximum memories to return
        """
        results = []

        # Start from most recent
        for memory in reversed(self._memories):
            # Filter by symbol
            if symbol and memory.get("symbol") != symbol:
                continue

            # Filter by type
            if memory_type and memory.get("type") != memory_type:
                continue

            results.append(memory)

            if len(results) >= limit:
                break

        return results

    async def retrieve_by_outcome(self, positive: bool, limit: int = 5) -> List[Dict]:
        """Retrieve memories by outcome (wins or losses)."""
        results = []

        for memory in reversed(self._memories):
            if memory.get("type") != "trade_outcome":
                continue

            pnl = memory.get("pnl", 0)
            if (positive and pnl > 0) or (not positive and pnl < 0):
                results.append(memory)

            if len(results) >= limit:
                break

        return results

    async def get_pattern_summary(self, symbol: str) -> Dict[str, Any]:
        """Get summary of patterns for a symbol."""
        memories = await self.retrieve(symbol=symbol, limit=20)

        if not memories:
            return {"trades": 0, "win_rate": 0.0, "avg_pnl": 0.0}

        trade_memories = [m for m in memories if m.get("type") == "trade_outcome"]

        if not trade_memories:
            return {"trades": 0, "win_rate": 0.0, "avg_pnl": 0.0}

        wins = sum(1 for m in trade_memories if m.get("pnl", 0) > 0)
        total_pnl = sum(m.get("pnl", 0) for m in trade_memories)

        return {
            "trades": len(trade_memories),
            "win_rate": wins / len(trade_memories),
            "avg_pnl": total_pnl / len(trade_memories),
            "last_trade": trade_memories[0] if trade_memories else None,
        }

    def size(self) -> int:
        """Get current number of memories."""
        return len(self._memories)

    def clear(self):
        """Clear all memories."""
        self._memories.clear()
        self._symbol_index.clear()
        logger.info("🧠 Memory cleared")
