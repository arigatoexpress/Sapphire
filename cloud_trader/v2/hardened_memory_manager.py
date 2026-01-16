"""
Hardened Memory Manager with Persistence Verification
======================================================
Enhanced RAG-like memory system with guaranteed Firestore persistence.

Per System Intelligence Report:
- Original MemoryManager has silent fallback behavior
- Agents become "amnesiac" on deployment if persistence fails
- _persisted flags may not be properly committed

This module provides:
1. Explicit commit verification
2. Write-ahead logging for crash recovery
3. Memory health monitoring
4. Automatic retry with exponential backoff

Author: Sapphire V2 Architecture Team
Version: 2.1.0
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import pickle
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Optional, TypeVar

import numpy as np

# Optional imports with fallbacks
try:
    import faiss
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False
    faiss = None

try:
    from google.cloud import firestore
    FIRESTORE_AVAILABLE = True
except ImportError:
    FIRESTORE_AVAILABLE = False
    firestore = None

# Configure logging with agentic persona
logger = logging.getLogger(__name__)

T = TypeVar('T')


class PersistenceState(Enum):
    """Memory persistence state."""
    UNKNOWN = "unknown"
    PENDING = "pending"
    COMMITTED = "committed"
    FAILED = "failed"
    STALE = "stale"


class MemoryType(Enum):
    """Types of memories stored."""
    TRADE_OUTCOME = "trade_outcome"
    THESIS_TEMPLATE = "thesis_template"
    LESSON_LEARNED = "lesson_learned"
    MARKET_PATTERN = "market_pattern"
    RISK_EVENT = "risk_event"


@dataclass
class Memory:
    """
    Individual memory unit with persistence tracking.
    
    Each memory has:
    - Unique ID (hash of content)
    - Semantic embedding for vector search
    - Metadata for filtering
    - Persistence state tracking
    """
    memory_id: str
    memory_type: MemoryType
    content: str
    embedding: Optional[np.ndarray] = None
    metadata: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    accessed_at: datetime = field(default_factory=datetime.utcnow)
    access_count: int = 0
    
    # Persistence tracking
    persistence_state: PersistenceState = PersistenceState.PENDING
    last_persisted: Optional[datetime] = None
    persistence_attempts: int = 0
    checksum: Optional[str] = None
    
    def __post_init__(self):
        """Generate checksum for integrity verification."""
        if self.checksum is None:
            self.checksum = self._compute_checksum()
    
    def _compute_checksum(self) -> str:
        """Compute SHA-256 checksum of memory content."""
        content_bytes = f"{self.memory_type.value}:{self.content}".encode()
        return hashlib.sha256(content_bytes).hexdigest()[:16]
    
    def verify_integrity(self) -> bool:
        """Verify memory integrity via checksum."""
        expected = self._compute_checksum()
        return self.checksum == expected
    
    def mark_accessed(self) -> None:
        """Update access tracking."""
        self.accessed_at = datetime.utcnow()
        self.access_count += 1
    
    def to_dict(self) -> dict:
        """Serialize for Firestore."""
        return {
            "memory_id": self.memory_id,
            "memory_type": self.memory_type.value,
            "content": self.content,
            "embedding": self.embedding.tolist() if self.embedding is not None else None,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "accessed_at": self.accessed_at.isoformat(),
            "access_count": self.access_count,
            "persistence_state": self.persistence_state.value,
            "last_persisted": self.last_persisted.isoformat() if self.last_persisted else None,
            "persistence_attempts": self.persistence_attempts,
            "checksum": self.checksum,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "Memory":
        """Deserialize from Firestore."""
        embedding = None
        if data.get("embedding"):
            embedding = np.array(data["embedding"], dtype=np.float32)
        
        return cls(
            memory_id=data["memory_id"],
            memory_type=MemoryType(data["memory_type"]),
            content=data["content"],
            embedding=embedding,
            metadata=data.get("metadata", {}),
            created_at=datetime.fromisoformat(data["created_at"]),
            accessed_at=datetime.fromisoformat(data["accessed_at"]),
            access_count=data.get("access_count", 0),
            persistence_state=PersistenceState(data.get("persistence_state", "unknown")),
            last_persisted=datetime.fromisoformat(data["last_persisted"]) if data.get("last_persisted") else None,
            persistence_attempts=data.get("persistence_attempts", 0),
            checksum=data.get("checksum"),
        )


@dataclass
class MemoryHealth:
    """Memory system health metrics."""
    total_memories: int = 0
    committed_count: int = 0
    pending_count: int = 0
    failed_count: int = 0
    stale_count: int = 0
    
    firestore_connected: bool = False
    faiss_index_size: int = 0
    last_commit_time: Optional[datetime] = None
    last_error: Optional[str] = None
    
    @property
    def health_score(self) -> float:
        """Calculate health score (0-1)."""
        if self.total_memories == 0:
            return 1.0  # Empty but healthy
        
        committed_ratio = self.committed_count / self.total_memories
        failed_penalty = self.failed_count / self.total_memories * 0.5
        connection_bonus = 0.2 if self.firestore_connected else 0.0
        
        return min(1.0, max(0.0, committed_ratio - failed_penalty + connection_bonus))
    
    @property
    def is_healthy(self) -> bool:
        """Check if memory system is healthy."""
        return self.health_score > 0.7 and self.firestore_connected
    
    def to_dict(self) -> dict:
        """Serialize health metrics."""
        return {
            "total_memories": self.total_memories,
            "committed": self.committed_count,
            "pending": self.pending_count,
            "failed": self.failed_count,
            "stale": self.stale_count,
            "health_score": round(self.health_score, 3),
            "is_healthy": self.is_healthy,
            "firestore_connected": self.firestore_connected,
            "faiss_index_size": self.faiss_index_size,
            "last_commit": self.last_commit_time.isoformat() if self.last_commit_time else None,
            "last_error": self.last_error,
        }


class WriteAheadLog:
    """
    Write-ahead logging for crash recovery.
    
    Ensures memories are not lost if the process crashes
    before Firestore commit completes.
    """
    
    def __init__(self, log_dir: Optional[Path] = None):
        """
        Initialize WAL.
        
        Args:
            log_dir: Directory for WAL files (default: temp dir)
        """
        self.log_dir = log_dir or Path(tempfile.gettempdir()) / "sapphire_wal"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._current_log: Optional[Path] = None
        
    def log_pending_write(self, memory: Memory) -> str:
        """
        Log a pending memory write.
        
        Args:
            memory: Memory to log
            
        Returns:
            WAL entry ID
        """
        entry_id = f"{memory.memory_id}_{int(time.time() * 1000)}"
        log_path = self.log_dir / f"{entry_id}.wal"
        
        with open(log_path, "wb") as f:
            pickle.dump(memory.to_dict(), f)
        
        logger.debug(f"📝 [WAL] Logged pending write: {entry_id}")
        return entry_id
    
    def mark_committed(self, entry_id: str) -> None:
        """Mark a WAL entry as committed (delete the file)."""
        log_path = self.log_dir / f"{entry_id}.wal"
        if log_path.exists():
            log_path.unlink()
            logger.debug(f"✅ [WAL] Marked committed: {entry_id}")
    
    def recover_pending(self) -> list[Memory]:
        """
        Recover any pending writes from crash.
        
        Returns:
            List of memories that need to be re-committed
        """
        recovered = []
        for log_file in self.log_dir.glob("*.wal"):
            try:
                with open(log_file, "rb") as f:
                    data = pickle.load(f)
                memory = Memory.from_dict(data)
                memory.persistence_state = PersistenceState.PENDING
                recovered.append(memory)
                logger.info(f"🔄 [WAL] Recovered pending memory: {memory.memory_id}")
            except Exception as e:
                logger.error(f"❌ [WAL] Failed to recover {log_file}: {e}")
        
        return recovered
    
    def cleanup_old_logs(self, max_age_hours: int = 24) -> int:
        """
        Clean up old WAL files.
        
        Args:
            max_age_hours: Maximum age of WAL files to keep
            
        Returns:
            Number of files cleaned up
        """
        cutoff = time.time() - (max_age_hours * 3600)
        cleaned = 0
        
        for log_file in self.log_dir.glob("*.wal"):
            if log_file.stat().st_mtime < cutoff:
                log_file.unlink()
                cleaned += 1
        
        if cleaned > 0:
            logger.info(f"🧹 [WAL] Cleaned up {cleaned} old log files")
        
        return cleaned


class HardenedMemoryManager:
    """
    Production-grade memory manager with guaranteed persistence.
    
    Features:
    - FAISS vector search for semantic retrieval
    - Firestore persistence with verification
    - Write-ahead logging for crash recovery
    - Automatic retry with exponential backoff
    - Health monitoring and alerting
    
    Usage:
        manager = HardenedMemoryManager()
        await manager.initialize()
        
        # Store a memory
        await manager.remember(
            content="BTC pump after Fed announcement",
            memory_type=MemoryType.MARKET_PATTERN,
            metadata={"symbol": "BTC", "event": "fed_rate"}
        )
        
        # Retrieve relevant memories
        memories = await manager.recall("fed rate decision impact")
    """
    
    FIRESTORE_COLLECTION = "agent_memories"
    EMBEDDING_DIM = 384  # For sentence-transformers
    MAX_RETRY_ATTEMPTS = 3
    RETRY_BASE_DELAY = 1.0  # seconds
    
    def __init__(
        self,
        firestore_client: Optional[Any] = None,
        embedding_model: Optional[Any] = None,
        enable_wal: bool = True,
        wal_dir: Optional[Path] = None,
    ):
        """
        Initialize memory manager.
        
        Args:
            firestore_client: Optional Firestore client
            embedding_model: Optional embedding model (sentence-transformers)
            enable_wal: Enable write-ahead logging
            wal_dir: Directory for WAL files
        """
        self._db = firestore_client
        self._embedding_model = embedding_model
        self._enable_wal = enable_wal
        
        # Memory storage
        self._memories: dict[str, Memory] = {}
        self._index: Optional[Any] = None  # FAISS index
        self._id_to_index: dict[str, int] = {}  # Map memory ID to FAISS index
        
        # WAL
        self._wal = WriteAheadLog(wal_dir) if enable_wal else None
        
        # State
        self._initialized = False
        self._lock = asyncio.Lock()
        self._health = MemoryHealth()
        
        # Background tasks
        self._persist_task: Optional[asyncio.Task] = None
        self._health_task: Optional[asyncio.Task] = None
    
    async def initialize(self) -> bool:
        """
        Initialize memory manager and load persisted state.
        
        Returns:
            True if fully initialized, False if degraded mode
        """
        if self._initialized:
            return self._health.is_healthy
        
        logger.info("🧠 [Memory] Initializing Hardened Memory Manager...")
        
        # Initialize FAISS index
        if FAISS_AVAILABLE:
            self._index = faiss.IndexFlatL2(self.EMBEDDING_DIM)
            logger.info(f"✅ [Memory] FAISS index initialized (dim={self.EMBEDDING_DIM})")
        else:
            logger.warning("⚠️ [Memory] FAISS not available - vector search disabled")
        
        # Initialize Firestore
        try:
            if self._db is None and FIRESTORE_AVAILABLE:
                self._db = firestore.AsyncClient()
            
            if self._db:
                # Test connection
                await self._test_firestore_connection()
                self._health.firestore_connected = True
                logger.info("✅ [Memory] Firestore connected")
                
                # Load existing memories
                await self._load_from_firestore()
        except Exception as e:
            logger.warning(f"⚠️ [Memory] Firestore unavailable: {e}")
            self._health.firestore_connected = False
            self._health.last_error = str(e)
        
        # Recover from WAL
        if self._wal:
            recovered = self._wal.recover_pending()
            for memory in recovered:
                self._memories[memory.memory_id] = memory
                await self._add_to_index(memory)
            if recovered:
                logger.info(f"🔄 [Memory] Recovered {len(recovered)} memories from WAL")
        
        # Start background tasks
        self._persist_task = asyncio.create_task(self._background_persist_loop())
        self._health_task = asyncio.create_task(self._background_health_check())
        
        self._initialized = True
        self._update_health_metrics()
        
        logger.info(
            f"🧠 [Memory] Initialized | "
            f"Total memories: {len(self._memories)} | "
            f"Health: {self._health.health_score:.2f} | "
            f"Firestore: {'✅' if self._health.firestore_connected else '❌'}"
        )
        
        return self._health.is_healthy
    
    async def _test_firestore_connection(self) -> bool:
        """Test Firestore connectivity."""
        if self._db is None:
            return False
        
        # Try to read a document
        test_ref = self._db.collection(self.FIRESTORE_COLLECTION).document("_health_check")
        await test_ref.set({"timestamp": datetime.utcnow().isoformat()})
        return True
    
    async def _load_from_firestore(self) -> None:
        """Load memories from Firestore."""
        if self._db is None:
            return
        
        docs = self._db.collection(self.FIRESTORE_COLLECTION).stream()
        count = 0
        
        async for doc in docs:
            if doc.id.startswith("_"):  # Skip system docs
                continue
            try:
                memory = Memory.from_dict(doc.to_dict())
                memory.persistence_state = PersistenceState.COMMITTED
                self._memories[memory.memory_id] = memory
                await self._add_to_index(memory)
                count += 1
            except Exception as e:
                logger.error(f"❌ [Memory] Failed to load memory {doc.id}: {e}")
        
        logger.info(f"📥 [Memory] Loaded {count} memories from Firestore")
    
    async def _add_to_index(self, memory: Memory) -> None:
        """Add memory to FAISS index."""
        if self._index is None or memory.embedding is None:
            return
        
        # Add to index
        embedding = memory.embedding.reshape(1, -1).astype(np.float32)
        idx = self._index.ntotal
        self._index.add(embedding)
        self._id_to_index[memory.memory_id] = idx
        self._health.faiss_index_size = self._index.ntotal
    
    async def _generate_embedding(self, text: str) -> Optional[np.ndarray]:
        """Generate embedding for text."""
        if self._embedding_model is None:
            # Return random embedding for testing
            logger.debug("[Memory] No embedding model - using random vector")
            return np.random.randn(self.EMBEDDING_DIM).astype(np.float32)
        
        try:
            embedding = self._embedding_model.encode(text)
            return np.array(embedding, dtype=np.float32)
        except Exception as e:
            logger.error(f"❌ [Memory] Embedding generation failed: {e}")
            return None
    
    async def remember(
        self,
        content: str,
        memory_type: MemoryType,
        metadata: Optional[dict] = None,
        force_persist: bool = False,
    ) -> Memory:
        """
        Store a new memory with guaranteed persistence.
        
        Args:
            content: Memory content
            memory_type: Type of memory
            metadata: Optional metadata
            force_persist: Force immediate persistence
            
        Returns:
            Stored Memory object
        """
        if not self._initialized:
            await self.initialize()
        
        # Generate memory ID
        memory_id = hashlib.sha256(
            f"{memory_type.value}:{content}:{datetime.utcnow().timestamp()}".encode()
        ).hexdigest()[:16]
        
        # Generate embedding
        embedding = await self._generate_embedding(content)
        
        # Create memory
        memory = Memory(
            memory_id=memory_id,
            memory_type=memory_type,
            content=content,
            embedding=embedding,
            metadata=metadata or {},
            persistence_state=PersistenceState.PENDING,
        )
        
        async with self._lock:
            # Log to WAL first
            wal_entry = None
            if self._wal:
                wal_entry = self._wal.log_pending_write(memory)
            
            # Store in memory
            self._memories[memory_id] = memory
            
            # Add to FAISS index
            await self._add_to_index(memory)
            
            logger.info(
                f"💾 [Memory] Stored | "
                f"ID: {memory_id[:8]} | "
                f"Type: {memory_type.value} | "
                f"State: PENDING"
            )
        
        # Persist to Firestore
        if force_persist or not self._persist_task:
            await self._persist_memory(memory, wal_entry)
        
        self._update_health_metrics()
        return memory
    
    async def _persist_memory(
        self,
        memory: Memory,
        wal_entry: Optional[str] = None,
    ) -> bool:
        """
        Persist a memory to Firestore with retry logic.
        
        Args:
            memory: Memory to persist
            wal_entry: Optional WAL entry ID to mark committed
            
        Returns:
            True if persistence successful
        """
        if self._db is None:
            logger.warning(f"⚠️ [Memory] Cannot persist {memory.memory_id} - no Firestore")
            memory.persistence_state = PersistenceState.FAILED
            return False
        
        for attempt in range(self.MAX_RETRY_ATTEMPTS):
            try:
                memory.persistence_attempts += 1
                
                # Write to Firestore
                doc_ref = self._db.collection(self.FIRESTORE_COLLECTION).document(memory.memory_id)
                await doc_ref.set(memory.to_dict())
                
                # Verify write by reading back
                verify_doc = await doc_ref.get()
                if not verify_doc.exists:
                    raise Exception("Write verification failed - document not found")
                
                stored_data = verify_doc.to_dict()
                if stored_data.get("checksum") != memory.checksum:
                    raise Exception("Write verification failed - checksum mismatch")
                
                # Mark as committed
                memory.persistence_state = PersistenceState.COMMITTED
                memory.last_persisted = datetime.utcnow()
                self._health.last_commit_time = memory.last_persisted
                
                # Clear WAL entry
                if wal_entry and self._wal:
                    self._wal.mark_committed(wal_entry)
                
                logger.info(
                    f"✅ [Memory] Persisted & verified | "
                    f"ID: {memory.memory_id[:8]} | "
                    f"Attempts: {memory.persistence_attempts}"
                )
                return True
                
            except Exception as e:
                delay = self.RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning(
                    f"⚠️ [Memory] Persist attempt {attempt + 1} failed | "
                    f"ID: {memory.memory_id[:8]} | "
                    f"Error: {e} | "
                    f"Retrying in {delay:.1f}s"
                )
                self._health.last_error = str(e)
                
                if attempt < self.MAX_RETRY_ATTEMPTS - 1:
                    await asyncio.sleep(delay)
        
        # All attempts failed
        memory.persistence_state = PersistenceState.FAILED
        logger.error(
            f"❌ [Memory] Persistence FAILED after {self.MAX_RETRY_ATTEMPTS} attempts | "
            f"ID: {memory.memory_id[:8]}"
        )
        return False
    
    async def recall(
        self,
        query: str,
        top_k: int = 5,
        memory_type: Optional[MemoryType] = None,
        min_relevance: float = 0.0,
    ) -> list[tuple[Memory, float]]:
        """
        Recall relevant memories using semantic search.
        
        Args:
            query: Search query
            top_k: Number of results to return
            memory_type: Optional filter by memory type
            min_relevance: Minimum relevance score (0-1)
            
        Returns:
            List of (Memory, relevance_score) tuples
        """
        if not self._initialized:
            await self.initialize()
        
        if not self._memories:
            logger.debug("[Memory] No memories to search")
            return []
        
        # Generate query embedding
        query_embedding = await self._generate_embedding(query)
        if query_embedding is None:
            logger.warning("[Memory] Could not generate query embedding")
            return []
        
        # Search FAISS index
        if self._index is not None and self._index.ntotal > 0:
            query_vec = query_embedding.reshape(1, -1).astype(np.float32)
            distances, indices = self._index.search(query_vec, min(top_k * 2, self._index.ntotal))
            
            # Map indices back to memories
            results = []
            index_to_id = {v: k for k, v in self._id_to_index.items()}
            
            for dist, idx in zip(distances[0], indices[0]):
                if idx < 0:
                    continue
                
                memory_id = index_to_id.get(idx)
                if memory_id is None:
                    continue
                
                memory = self._memories.get(memory_id)
                if memory is None:
                    continue
                
                # Apply filters
                if memory_type and memory.memory_type != memory_type:
                    continue
                
                # Convert distance to relevance (0-1)
                relevance = 1.0 / (1.0 + dist)
                if relevance < min_relevance:
                    continue
                
                memory.mark_accessed()
                results.append((memory, relevance))
            
            # Sort by relevance and limit
            results.sort(key=lambda x: x[1], reverse=True)
            results = results[:top_k]
            
            logger.debug(
                f"🔍 [Memory] Recalled {len(results)} memories | "
                f"Query: '{query[:50]}...'"
            )
            return results
        
        # Fallback: return recent memories
        memories = list(self._memories.values())
        if memory_type:
            memories = [m for m in memories if m.memory_type == memory_type]
        memories.sort(key=lambda m: m.created_at, reverse=True)
        return [(m, 0.5) for m in memories[:top_k]]
    
    async def _background_persist_loop(self) -> None:
        """Background loop to persist pending memories."""
        while True:
            try:
                await asyncio.sleep(30)  # Check every 30 seconds
                
                pending = [
                    m for m in self._memories.values()
                    if m.persistence_state == PersistenceState.PENDING
                ]
                
                if pending:
                    logger.info(f"🔄 [Memory] Background persist: {len(pending)} pending")
                    for memory in pending:
                        await self._persist_memory(memory)
                    
                    self._update_health_metrics()
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ [Memory] Background persist error: {e}")
    
    async def _background_health_check(self) -> None:
        """Background health monitoring."""
        while True:
            try:
                await asyncio.sleep(60)  # Check every minute
                
                self._update_health_metrics()
                
                if not self._health.is_healthy:
                    logger.warning(
                        f"⚠️ [Memory] Health degraded | "
                        f"Score: {self._health.health_score:.2f} | "
                        f"Firestore: {'✅' if self._health.firestore_connected else '❌'} | "
                        f"Failed: {self._health.failed_count}"
                    )
                    
                    # Attempt to reconnect Firestore if disconnected
                    if not self._health.firestore_connected:
                        try:
                            await self._test_firestore_connection()
                            self._health.firestore_connected = True
                            logger.info("✅ [Memory] Firestore reconnected")
                        except Exception:
                            pass
                            
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ [Memory] Health check error: {e}")
    
    def _update_health_metrics(self) -> None:
        """Update health metrics from current state."""
        self._health.total_memories = len(self._memories)
        self._health.committed_count = sum(
            1 for m in self._memories.values()
            if m.persistence_state == PersistenceState.COMMITTED
        )
        self._health.pending_count = sum(
            1 for m in self._memories.values()
            if m.persistence_state == PersistenceState.PENDING
        )
        self._health.failed_count = sum(
            1 for m in self._memories.values()
            if m.persistence_state == PersistenceState.FAILED
        )
        
        if self._index:
            self._health.faiss_index_size = self._index.ntotal
    
    def get_health(self) -> MemoryHealth:
        """Get current health status."""
        self._update_health_metrics()
        return self._health
    
    async def shutdown(self) -> None:
        """Gracefully shutdown memory manager."""
        logger.info("🛑 [Memory] Shutting down...")
        
        # Cancel background tasks
        if self._persist_task:
            self._persist_task.cancel()
            try:
                await self._persist_task
            except asyncio.CancelledError:
                pass
        
        if self._health_task:
            self._health_task.cancel()
            try:
                await self._health_task
            except asyncio.CancelledError:
                pass
        
        # Final persist of any pending memories
        pending = [
            m for m in self._memories.values()
            if m.persistence_state == PersistenceState.PENDING
        ]
        
        if pending:
            logger.info(f"💾 [Memory] Final persist: {len(pending)} memories")
            for memory in pending:
                await self._persist_memory(memory)
        
        # Cleanup WAL
        if self._wal:
            self._wal.cleanup_old_logs()
        
        logger.info("✅ [Memory] Shutdown complete")


# Factory function for main_v2.py
async def create_memory_manager(
    firestore_client: Optional[Any] = None,
    embedding_model: Optional[Any] = None,
) -> HardenedMemoryManager:
    """
    Create and initialize a hardened memory manager.
    
    Args:
        firestore_client: Optional Firestore client
        embedding_model: Optional embedding model
        
    Returns:
        Initialized HardenedMemoryManager
    """
    manager = HardenedMemoryManager(
        firestore_client=firestore_client,
        embedding_model=embedding_model,
    )
    await manager.initialize()
    return manager


# Example usage
if __name__ == "__main__":
    async def demo():
        """Demonstrate memory manager functionality."""
        print("🧠 Hardened Memory Manager Demo\n")
        
        # Create manager (without Firestore for demo)
        manager = HardenedMemoryManager(firestore_client=None)
        await manager.initialize()
        
        # Store some memories
        await manager.remember(
            content="BTC pumped 5% after Fed held rates steady",
            memory_type=MemoryType.MARKET_PATTERN,
            metadata={"symbol": "BTC", "event": "fed_rate"}
        )
        
        await manager.remember(
            content="Over-leveraged position caused 10% drawdown",
            memory_type=MemoryType.LESSON_LEARNED,
            metadata={"strategy": "momentum", "lesson": "position_sizing"}
        )
        
        await manager.remember(
            content="RSI divergence signaled trend reversal",
            memory_type=MemoryType.THESIS_TEMPLATE,
            metadata={"indicator": "RSI", "pattern": "divergence"}
        )
        
        # Recall memories
        results = await manager.recall("fed interest rate decision")
        print(f"\n🔍 Search: 'fed interest rate decision'")
        for memory, relevance in results:
            print(f"  - [{relevance:.2f}] {memory.content[:50]}...")
        
        # Check health
        health = manager.get_health()
        print(f"\n📊 Health: {health.to_dict()}")
        
        await manager.shutdown()
    
    asyncio.run(demo())
