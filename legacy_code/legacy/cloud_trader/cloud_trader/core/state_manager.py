"""
State Manager Module
Persists trading state to Redis with in-memory fallback.
"""

import json
import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Lazy import redis to handle missing dependency gracefully
_redis_client = None
_in_memory_store: Dict[str, str] = {}


def _get_redis_client():
    """Get or create Redis client singleton."""
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    
    try:
        import redis
        host = os.getenv("REDIS_HOST", "localhost")
        port = int(os.getenv("REDIS_PORT", 6379))
        password = os.getenv("REDIS_PASSWORD", None)
        
        _redis_client = redis.Redis(
            host=host,
            port=port,
            password=password,
            decode_responses=True,
            socket_timeout=5,
            socket_connect_timeout=5
        )
        # Test connection
        _redis_client.ping()
        logger.info(f"🔗 Connected to Redis at {host}:{port}")
        return _redis_client
        
    except Exception as e:
        logger.warning(f"⚠️ Redis not available, using in-memory fallback: {e}")
        return None


class StateManager:
    """
    Manages persistent state for the trading system.
    Uses Redis when available, falls back to in-memory storage.
    """

    def __init__(self, namespace: str = "sapphire"):
        self.namespace = namespace
        self.redis = _get_redis_client()
        self._local_cache: Dict[str, Any] = {}

    def _key(self, key: str) -> str:
        """Generate namespaced Redis key."""
        return f"{self.namespace}:{key}"

    def save_state(self, key: str, data: Any, ttl_seconds: Optional[int] = None) -> bool:
        """
        Save state to Redis.
        
        Args:
            key: State identifier
            data: Data to persist (must be JSON-serializable)
            ttl_seconds: Optional TTL for automatic expiration
        
        Returns:
            True if saved successfully
        """
        full_key = self._key(key)
        serialized = json.dumps(data)
        
        # Update local cache
        self._local_cache[key] = data
        
        if self.redis:
            try:
                if ttl_seconds:
                    self.redis.setex(full_key, ttl_seconds, serialized)
                else:
                    self.redis.set(full_key, serialized)
                return True
            except Exception as e:
                logger.warning(f"Redis save failed for {key}: {e}")
                # Fallback to in-memory
                _in_memory_store[full_key] = serialized
                return True
        else:
            _in_memory_store[full_key] = serialized
            return True

    def load_state(self, key: str, default: Any = None) -> Any:
        """
        Load state from Redis.
        
        Args:
            key: State identifier
            default: Default value if key not found
        
        Returns:
            Deserialized state or default
        """
        full_key = self._key(key)
        
        # Try local cache first
        if key in self._local_cache:
            return self._local_cache[key]
        
        serialized = None
        
        if self.redis:
            try:
                serialized = self.redis.get(full_key)
            except Exception as e:
                logger.warning(f"Redis load failed for {key}: {e}")
        
        if serialized is None:
            serialized = _in_memory_store.get(full_key)
        
        if serialized is None:
            return default
        
        try:
            data = json.loads(serialized)
            self._local_cache[key] = data
            return data
        except json.JSONDecodeError:
            logger.error(f"Failed to deserialize state for {key}")
            return default

    def delete_state(self, key: str) -> bool:
        """Delete state from Redis."""
        full_key = self._key(key)
        
        # Remove from local cache
        self._local_cache.pop(key, None)
        
        if self.redis:
            try:
                self.redis.delete(full_key)
                return True
            except Exception as e:
                logger.warning(f"Redis delete failed for {key}: {e}")
        
        _in_memory_store.pop(full_key, None)
        return True

    def list_keys(self, pattern: str = "*") -> list:
        """List keys matching pattern."""
        full_pattern = self._key(pattern)
        
        if self.redis:
            try:
                keys = self.redis.keys(full_pattern)
                # Strip namespace prefix
                prefix_len = len(self.namespace) + 1
                return [k[prefix_len:] for k in keys]
            except Exception as e:
                logger.warning(f"Redis keys failed: {e}")
        
        # Fallback
        return [k.replace(f"{self.namespace}:", "") for k in _in_memory_store.keys() if k.startswith(f"{self.namespace}:")]

    # --- Typed helpers for common state ---

    def save_execution_slice(self, order_id: str, slice_data: Dict, ttl: int = 3600) -> bool:
        """Save execution slice with 1-hour TTL."""
        return self.save_state(f"execution:{order_id}", slice_data, ttl_seconds=ttl)

    def load_execution_slice(self, order_id: str) -> Optional[Dict]:
        """Load execution slice."""
        return self.load_state(f"execution:{order_id}")

    def save_position(self, symbol: str, position_data: Dict) -> bool:
        """Save position (no TTL, persistent)."""
        return self.save_state(f"position:{symbol}", position_data)

    def load_position(self, symbol: str) -> Optional[Dict]:
        """Load position."""
        return self.load_state(f"position:{symbol}")

    def save_orchestrator_state(self, state: Dict) -> bool:
        """Save orchestrator state for recovery on restart."""
        return self.save_state("orchestrator:state", state)

    def load_orchestrator_state(self) -> Optional[Dict]:
        """Load orchestrator state."""
        return self.load_state("orchestrator:state")
