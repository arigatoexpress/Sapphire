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
import numpy as np

logger = logging.getLogger(__name__)

# Firestore client (lazy loaded)
_firestore_client = None
_embedding_model = None

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

def _get_embedding_model():
    """Get or create SentenceTransformer model (singleton)."""
    global _embedding_model
    if _embedding_model is None:
        try:
            from sentence_transformers import SentenceTransformer
            # Use a lightweight model for speed
            _embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
            logger.info("🧠 Embedding model initialized")
        except Exception as e:
            logger.error(f"❌ Failed to load embedding model: {e}")
            _embedding_model = False
    return _embedding_model if _embedding_model else None

class MemoryManager:
    """
    Persistent agent memory with structural and semantic retrieval.
    
    Features:
    - Recent memory buffer
    - Firestore persistence
    - Vector search via FAISS (semantic similarity)
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
        
        # FAISS Index
        self._index = None
        self._id_map = {} # Map FAISS index ID to memory ID
        self._next_index_id = 0
        
        self._init_faiss()
        
        logger.info(f"🧠 MemoryManager initialized (agent={agent_id}, max={max_memories}, persist={persist})")
        
        if persist:
            asyncio.create_task(self._load_from_firestore())

    def _init_faiss(self):
        """Initialize FAISS index."""
        try:
            import faiss
            # Dimension for all-MiniLM-L6-v2 is 384
            self._index = faiss.IndexFlatL2(384)
        except Exception as e:
            logger.warning(f"⚠️ FAISS not available, semantic search disabled: {e}")
            self._index = None

    async def _load_from_firestore(self):
        """Load memories from Firestore and rebuild vector index."""
        if not self._persist or self._loaded:
            return
            
        client = _get_firestore_client()
        if not client:
            logger.warning("🧠 Firestore unavailable - starting with empty memory")
            self._loaded = True
            return
            
        try:
            collection_ref = client.collection(self._collection_name).document(self._agent_id).collection("memories")
            query = collection_ref.order_by("timestamp", direction="DESCENDING").limit(self.max_memories)
            
            # Add timeout to prevent blocking trading loop
            docs = await asyncio.wait_for(query.get(), timeout=10.0)
            loaded_count = 0
            
            # Load into deque (timestamp sorted)
            for doc in reversed(list(docs)):
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
                
                # Update VectorDB
                self._add_to_index(memory)
                
                loaded_count += 1
            
            self._loaded = True
            logger.info(f"🧠 Loaded {loaded_count} memories from Firestore for agent {self._agent_id}")
            
        except asyncio.TimeoutError:
            logger.warning(f"🧠 Firestore load timeout (10s) - starting with empty memory")
            self._loaded = True
        except Exception as e:
            logger.error(f"🧠 Failed to load from Firestore: {e}")
            self._loaded = True

    def _add_to_index(self, memory: Dict[str, Any]):
        """Add memory to FAISS index."""
        if self._index is None:
            return

        model = _get_embedding_model()
        if not model:
            return

        # Create text representation for embedding
        text = ""
        if memory.get("type") == "analysis":
            thesis = memory.get("thesis", {})
            text = f"{memory.get('symbol')} analysis: {thesis.get('reasoning', '')}"
        elif memory.get("type") == "trade_outcome":
            text = f"{memory.get('symbol')} outcome: {memory.get('reasoning', '')} Lesson: {memory.get('lesson', '')}"
        else:
            text = str(memory)

        if not text.strip():
            return

        try:
            vector = model.encode([text])
            self._index.add(np.array(vector, dtype=np.float32))
            
            # Map internal FAISS ID to memory UUID
            self._id_map[self._next_index_id] = memory.get("_id")
            self._next_index_id += 1
        except Exception as e:
            logger.warning(f"Failed to index memory: {e}")

    async def _persist_memory(self, memory: Dict[str, Any]):
        """Persist a single memory to Firestore."""
        if not self._persist:
            return
            
        client = _get_firestore_client()
        if not client:
            return
            
        try:
            memory_id = memory.get("_id") or str(uuid.uuid4())
            doc_ref = (
                client.collection(self._collection_name)
                .document(self._agent_id)
                .collection("memories")
                .document(str(memory_id))
            )
            
            data = {k: v for k, v in memory.items() if not k.startswith("_")}
            data["timestamp"] = memory.get("timestamp", time.time())
            
            await doc_ref.set(data)
            memory["_persisted"] = True
            
        except Exception as e:
            logger.warning(f"🧠 Failed to persist memory: {e}")
            self._pending_writes.append(memory)

    async def store(self, memory: Dict[str, Any]) -> bool:
        """Store memory in buffer, vector DB, and persistence."""
        try:
            if "timestamp" not in memory:
                memory["timestamp"] = time.time()

            memory["_id"] = str(uuid.uuid4())
            memory["_persisted"] = False
            
            self._memories.append(memory)

            # Update indices
            symbol = memory.get("symbol")
            if symbol:
                if symbol not in self._symbol_index:
                    self._symbol_index[symbol] = []
                self._symbol_index[symbol].append(memory["_id"])

            self._add_to_index(memory)

            if self._persist:
                asyncio.create_task(self._persist_memory(memory))

            return True

        except Exception as e:
            logger.error(f"Memory store error: {e}")
            return False

    async def retrieve(
        self, 
        symbol: Optional[str] = None, 
        memory_type: Optional[str] = None, 
        query_text: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict]:
        """
        Retrieve relevant memories.
        
        Args:
            symbol: Filter by symbol
            memory_type: Filter by type
            query_text: Semantic search query. If provided, overrides symbol/recency sort.
            limit: limit
        """
        # Linear scan / Symbol filter
        basic_results = []
        for memory in reversed(self._memories):
            if symbol and memory.get("symbol") != symbol:
                continue
            if memory_type and memory.get("type") != memory_type:
                continue
            basic_results.append(memory)

        # Semantic Search (FAISS)
        if query_text and self._index and self._index.ntotal > 0:
            model = _get_embedding_model()
            if model:
                try:
                    query_vector = model.encode([query_text])
                    # Search k nearest
                    k = min(limit, self._index.ntotal)
                    distances, indices = self._index.search(np.array(query_vector, dtype=np.float32), k)
                    
                    semantic_results = []
                    seen_ids = set()
                    
                    for idx in indices[0]:
                        if idx == -1: continue
                        mem_id = self._id_map.get(idx)
                        if mem_id:
                            # Find memory object (inefficient linear scan but O(N) where N=100 is tiny)
                            # In a real DB we'd fetch by ID. Here we scan deque.
                            found = next((m for m in self._memories if m.get("_id") == mem_id), None)
                            if found and found["_id"] not in seen_ids:
                                semantic_results.append(found)
                                seen_ids.add(found["_id"])
                    
                    # Merge: prioritize semantic matches, then fill with recent symbol matches
                    for res in basic_results:
                        if res.get("_id") not in seen_ids:
                            semantic_results.append(res)
                            
                    return semantic_results[:limit]
                    
                except Exception as e:
                    logger.warning(f"Semantic search failed: {e}")

        # Default fallback: return recent matches
        return basic_results[:limit]

    async def retrieve_by_outcome(self, positive: bool, limit: int = 5) -> List[Dict]:
        """Retrieve memories by outcome."""
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
        return len(self._memories)

    def is_loaded(self) -> bool:
        return self._loaded

    def clear(self):
        self._memories.clear()
        self._symbol_index.clear()
        if self._index:
            self._index.reset()
        self._id_map = {}
        self._next_index_id = 0
        logger.info("🧠 Memory cleared (in-memory)")

    async def clear_persistent(self):
        self.clear()
        if not self._persist:
            return
        client = _get_firestore_client()
        if not client:
            return
        try:
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

