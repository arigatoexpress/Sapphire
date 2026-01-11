"""
Sapphire V2 Memory Manager
RAG-like memory system for trading agents with Firestore persistence.

Stores and retrieves:
- Past trade outcomes
- Market patterns
- Successful thesis templates
- Learned lessons

Persistence: Google Cloud Firestore (async, non-blocking)
"""

import asyncio
import logging
import time
import uuid
from collections import deque
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Firestore client (lazy loaded)
_firestore_client = None


def _get_firestore_client():
    """Get or create Firestore client (singleton)."""
    global _firestore_client
    if _firestore_client is None:
        try:
            from google.cloud import firestore
            _firestore_client = firestore.AsyncClient(project="sapphire-479610")
            logger.info("🔥 Firestore client initialized")
        except Exception as e:
            logger.warning(f"⚠️ Firestore unavailable: {e}")
            _firestore_client = False  # Mark as failed
    return _firestore_client if _firestore_client else None


class MemoryManager:
    """
    Persistent agent memory with retrieval capabilities.

    Inspired by ElizaOS RAG pattern:
    - Store memories with metadata
    - Retrieve by symbol, recency, or embedding similarity
    - Auto-prune old memories
    - Persist to Firestore for survival across restarts
    """

    def __init__(
        self,
        agent_id: str = "default",
        max_memories: int = 100,
        persist: bool = True,
        collection_name: str = "sapphire_memories",
    ):
        self._agent_id = agent_id
        self.max_memories = max_memories
        self._persist = persist
        self._collection_name = collection_name
        self._memories: deque = deque(maxlen=max_memories)
        self._symbol_index: Dict[str, List[int]] = {}
        self._loaded = False
        self._pending_writes: List[Dict] = []
        
        logger.info(f"🧠 MemoryManager initialized (agent={agent_id}, max={max_memories}, persist={persist})")
        
        # Start background loader if persistence enabled
        if persist:
            asyncio.create_task(self._load_from_firestore())

    async def _load_from_firestore(self):
        """Load memories from Firestore on startup."""
        if not self._persist or self._loaded:
            return
            
        client = _get_firestore_client()
        if not client:
            logger.warning("🧠 Firestore unavailable - starting with empty memory")
            self._loaded = True
            return
            
        try:
            # Query most recent memories for this agent
            collection_ref = client.collection(self._collection_name).document(self._agent_id).collection("memories")
            query = collection_ref.order_by("timestamp", direction="DESCENDING").limit(self.max_memories)
            
            docs = await query.get()
            loaded_count = 0
            
            for doc in reversed(list(docs)):  # Reverse to maintain order
                memory = doc.to_dict()
                memory["_id"] = doc.id
                memory["_persisted"] = True
                self._memories.append(memory)
                
                # Update symbol index
                symbol = memory.get("symbol")
                if symbol:
                    if symbol not in self._symbol_index:
                        self._symbol_index[symbol] = []
                    self._symbol_index[symbol].append(memory["_id"])
                    
                loaded_count += 1
            
            self._loaded = True
            logger.info(f"🧠 Loaded {loaded_count} memories from Firestore for agent {self._agent_id}")
            
        except Exception as e:
            logger.error(f"🧠 Failed to load from Firestore: {e}")
            self._loaded = True  # Mark as loaded to prevent retry loops

    async def _persist_memory(self, memory: Dict[str, Any]):
        """Persist a single memory to Firestore (non-blocking)."""
        if not self._persist:
            return
            
        client = _get_firestore_client()
        if not client:
            return
            
        try:
            # Create document with unique ID
            memory_id = memory.get("_id") or str(uuid.uuid4())
            doc_ref = (
                client.collection(self._collection_name)
                .document(self._agent_id)
                .collection("memories")
                .document(str(memory_id))
            )
            
            # Prepare data (exclude internal fields)
            data = {k: v for k, v in memory.items() if not k.startswith("_")}
            data["timestamp"] = memory.get("timestamp", time.time())
            
            await doc_ref.set(data)
            memory["_persisted"] = True
            
        except Exception as e:
            logger.warning(f"🧠 Failed to persist memory: {e}")
            # Add to pending writes for retry
            self._pending_writes.append(memory)

    async def store(self, memory: Dict[str, Any]) -> bool:
        """Store a new memory (in-memory + async persist to Firestore)."""
        try:
            # Add timestamp if not present
            if "timestamp" not in memory:
                memory["timestamp"] = time.time()

            # Generate unique ID
            memory["_id"] = str(uuid.uuid4())
            memory["_persisted"] = False
            
            # Store in-memory (fast, synchronous)
            self._memories.append(memory)

            # Update symbol index
            symbol = memory.get("symbol")
            if symbol:
                if symbol not in self._symbol_index:
                    self._symbol_index[symbol] = []
                self._symbol_index[symbol].append(memory["_id"])

            # Persist to Firestore (async, non-blocking)
            if self._persist:
                asyncio.create_task(self._persist_memory(memory))

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

    def is_loaded(self) -> bool:
        """Check if memories have been loaded from persistence."""
        return self._loaded

    def clear(self):
        """Clear all memories (in-memory only, Firestore preserved)."""
        self._memories.clear()
        self._symbol_index.clear()
        logger.info("🧠 Memory cleared (in-memory)")

    async def clear_persistent(self):
        """Clear all memories including Firestore."""
        self.clear()
        
        if not self._persist:
            return
            
        client = _get_firestore_client()
        if not client:
            return
            
        try:
            # Delete all documents in the agent's memory collection
            collection_ref = (
                client.collection(self._collection_name)
                .document(self._agent_id)
                .collection("memories")
            )
            docs = await collection_ref.get()
            for doc in docs:
                await doc.reference.delete()
            logger.info(f"🧠 Cleared persistent memory for agent {self._agent_id}")
        except Exception as e:
            logger.error(f"🧠 Failed to clear persistent memory: {e}")
