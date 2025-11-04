from __future__ import annotations

import asyncio
import json
import logging
from enum import Enum
from typing import Any, Dict, Optional

import httpx
from httpx import HTTPStatusError
from pydantic import BaseModel, Field


class MCPMessageType(str, Enum):
    OBSERVATION = "observation"
    PROPOSAL = "proposal"
    CRITIQUE = "critique"
    QUERY = "query"
    RESPONSE = "response"
    CONSENSUS = "consensus"
    EXECUTION = "execution"
    HEARTBEAT = "heartbeat"


class MCPProposalPayload(BaseModel):
    symbol: str
    side: str
    notional: float
    confidence: float
    rationale: str
    constraints: list[str] = Field(default_factory=list)


class MCPResponsePayload(BaseModel):
    reference_id: str
    answer: str
    confidence: float
    supplementary: Optional[Dict[str, Any]] = None


logger = logging.getLogger(__name__)


class MCPClient:
    def __init__(self, base_url: str, session_id: str | None = None, *, timeout: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._session_id = session_id
        self._client = httpx.AsyncClient(timeout=timeout)
        self._lock = asyncio.Lock()

    @property
    def session_id(self) -> Optional[str]:
        return self._session_id

    async def _session_exists(self, session_id: str) -> bool:
        try:
            resp = await self._client.get(f"{self._base_url}/sessions")
            resp.raise_for_status()
            data = resp.json()
            sessions = data.get("sessions", [])
            if isinstance(sessions, dict):
                sessions = list(sessions.keys())
            return isinstance(sessions, list) and session_id in sessions
        except Exception:
            return False

    async def ensure_session(self, *, force_refresh: bool = False) -> str:
        async with self._lock:
            if self._session_id and not force_refresh:
                exists = await self._session_exists(self._session_id)
                if exists:
                return self._session_id
                logger.warning(
                    "Configured MCP session '%s' missing; obtaining a new session",
                    self._session_id,
                )
                self._session_id = None

            resp = await self._client.post(f"{self._base_url}/sessions")
            resp.raise_for_status()
            data = resp.json()
            new_session = data.get("session_id")
            if not new_session:
                raise RuntimeError("MCP session creation did not return a session_id")
            self._session_id = new_session
            logger.info("Acquired MCP session %s", self._session_id)
            return self._session_id

    async def publish(self, message: Dict[str, Any]) -> None:
        """Publish MCP message and track metrics."""
        try:
            from .metrics import MCP_MESSAGES_TOTAL

            message_type = message.get("message_type", "unknown")
            MCP_MESSAGES_TOTAL.labels(message_type=message_type, direction="outbound").inc()
        except Exception:
            pass  # Metrics not critical

        session_id = await self.ensure_session()
        if not message.get("session_id"):
            message = {**message, "session_id": session_id}

        payload = json.dumps(message)
        try:
            resp = await self._client.post(
                f"{self._base_url}/sessions/{session_id}/messages",
                content=payload,
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
        except HTTPStatusError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                logger.warning("MCP session %s missing; refreshing session", session_id)
                async with self._lock:
                    self._session_id = None
                session_id = await self.ensure_session(force_refresh=True)
                refreshed_payload = json.dumps({**message, "session_id": session_id})
                resp = await self._client.post(
                    f"{self._base_url}/sessions/{session_id}/messages",
                    content=refreshed_payload,
                    headers={"Content-Type": "application/json"},
                )
                resp.raise_for_status()
                return
            raise

    async def close(self) -> None:
        await self._client.aclose()


__all__ = [
    "MCPClient",
    "MCPMessageType",
    "MCPProposalPayload",
    "MCPResponsePayload",
]

