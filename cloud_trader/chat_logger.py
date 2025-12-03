"""Chat logger for storing agent communication history."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from google.cloud import firestore
    from google.cloud.firestore import AsyncClient

    FIRESTORE_AVAILABLE = True
except ImportError:
    FIRESTORE_AVAILABLE = False
    firestore = None
    AsyncClient = None

from .config import get_settings

logger = logging.getLogger(__name__)


class ChatLogger:
    """Logs and retrieves agent chat messages for historical analysis."""

    def __init__(self):
        self.settings = get_settings()
        self.db_client: Optional[AsyncClient] = None
        self.collection_name = "agent_chat_history"
        self._local_cache: List[Dict[str, Any]] = []
        self._cache_size = 1000  # Keep last 1000 messages in memory

        # Initialize Firestore if enabled
        if self.settings.gcp_project_id and FIRESTORE_AVAILABLE:
            try:
                self.db_client = firestore.AsyncClient(project=self.settings.gcp_project_id)
                logger.info("Chat logger initialized with Firestore")
            except Exception as e:
                logger.warning(f"Failed to initialize Firestore for chat logging: {e}")

        # Ensure local storage directory exists
        # Use /tmp for container environments to avoid permission issues
        if Path("/app").exists():
            self.local_log_dir = Path("/tmp/app-logs/chat_history")
        else:
        self.local_log_dir = Path("logs/chat_history")
        self.local_log_dir.mkdir(parents=True, exist_ok=True)

    async def log_message(
        self,
        agent_id: str,
        agent_name: str,
        agent_type: str,
        message: str,
        message_type: str = "general",
        confidence: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Log a chat message from an agent."""
        try:
            timestamp = datetime.utcnow()
            message_data = {
                "id": f"{timestamp.timestamp()}-{agent_id}",
                "timestamp": timestamp.isoformat(),
                "agent_id": agent_id,
                "agent_name": agent_name,
                "agent_type": agent_type,
                "message": message,
                "message_type": message_type,
                "confidence": confidence,
                "metadata": metadata or {},
            }

            # Add to local cache
            self._local_cache.append(message_data)
            if len(self._local_cache) > self._cache_size:
                self._local_cache = self._local_cache[-self._cache_size :]

            # Save to Firestore if available
            if self.db_client:
                try:
                    doc_ref = self.db_client.collection(self.collection_name).document(
                        message_data["id"]
                    )
                    await doc_ref.set(message_data)
                    logger.debug(f"Chat message logged to Firestore: {agent_id}")
                except Exception as e:
                    logger.warning(f"Failed to log message to Firestore: {e}")
                    # Fall back to local storage

            # Also save to local file as backup
            try:
                log_file = self.local_log_dir / f"chat_{timestamp.strftime('%Y%m%d')}.jsonl"
                with open(log_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(message_data) + "\n")
            except Exception as e:
                logger.warning(f"Failed to write chat message to local file: {e}")

            return True

        except Exception as e:
            logger.error(f"Failed to log chat message: {e}", exc_info=True)
            return False

    async def get_recent_messages(
        self,
        limit: int = 100,
        agent_type: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve recent chat messages with optional filtering."""
        try:
            messages = []

            # Try Firestore first
            if self.db_client:
                try:
                    query = self.db_client.collection(self.collection_name)

                    if start_time:
                        query = query.where("timestamp", ">=", start_time.isoformat())
                    if end_time:
                        query = query.where("timestamp", "<=", end_time.isoformat())
                    if agent_type:
                        query = query.where("agent_type", "==", agent_type)

                    query = query.order_by("timestamp", direction=firestore.Query.DESCENDING).limit(
                        limit
                    )

                    docs = query.stream()
                    async for doc in docs:
                        messages.append(doc.to_dict())

                    if messages:
                        # Sort by timestamp descending
                        messages.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
                        return messages[:limit]
                except Exception as e:
                    logger.warning(f"Failed to retrieve messages from Firestore: {e}")

            # Fall back to local cache
            messages = list(self._local_cache)

            # Apply filters
            if agent_type:
                messages = [m for m in messages if m.get("agent_type") == agent_type]
            if start_time:
                start_str = start_time.isoformat()
                messages = [m for m in messages if m.get("timestamp", "") >= start_str]
            if end_time:
                end_str = end_time.isoformat()
                messages = [m for m in messages if m.get("timestamp", "") <= end_str]

            # Sort by timestamp descending
            messages.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
            return messages[:limit]

        except Exception as e:
            logger.error(f"Failed to retrieve chat messages: {e}", exc_info=True)
            return []

    async def get_message_statistics(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Get statistics about chat messages."""
        try:
            messages = await self.get_recent_messages(
                limit=10000,  # Large limit for stats
                start_time=start_time,
                end_time=end_time,
            )

            if not messages:
                return {
                    "total_messages": 0,
                    "messages_by_agent": {},
                    "messages_by_type": {},
                    "time_range": None,
                }

            messages_by_agent: Dict[str, int] = {}
            messages_by_type: Dict[str, int] = {}

            for msg in messages:
                agent_id = msg.get("agent_id", "unknown")
                msg_type = msg.get("message_type", "unknown")

                messages_by_agent[agent_id] = messages_by_agent.get(agent_id, 0) + 1
                messages_by_type[msg_type] = messages_by_type.get(msg_type, 0) + 1

            time_range = None
            if messages:
                timestamps = [msg.get("timestamp") for msg in messages if msg.get("timestamp")]
                if timestamps:
                    time_range = {
                        "start": min(timestamps),
                        "end": max(timestamps),
                    }

            return {
                "total_messages": len(messages),
                "messages_by_agent": messages_by_agent,
                "messages_by_type": messages_by_type,
                "time_range": time_range,
            }

        except Exception as e:
            logger.error(f"Failed to get chat statistics: {e}", exc_info=True)
            return {
                "total_messages": 0,
                "messages_by_agent": {},
                "messages_by_type": {},
                "time_range": None,
            }

    async def export_messages(
        self,
        output_path: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        format: str = "jsonl",  # jsonl or json
    ) -> bool:
        """Export chat messages to a file."""
        try:
            messages = await self.get_recent_messages(
                limit=100000,  # Large limit for export
                start_time=start_time,
                end_time=end_time,
            )

            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)

            if format == "jsonl":
                with open(output_file, "w", encoding="utf-8") as f:
                    for msg in messages:
                        f.write(json.dumps(msg) + "\n")
            else:  # json
                with open(output_file, "w", encoding="utf-8") as f:
                    json.dump(messages, f, indent=2, ensure_ascii=False)

            logger.info(f"Exported {len(messages)} messages to {output_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to export messages: {e}", exc_info=True)
            return False


# Global instance
_chat_logger: Optional[ChatLogger] = None


def get_chat_logger() -> ChatLogger:
    """Get the global chat logger instance."""
    global _chat_logger
    if _chat_logger is None:
        _chat_logger = ChatLogger()
    return _chat_logger
