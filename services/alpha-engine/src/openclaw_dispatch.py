"""OpenClaw Gateway Dispatcher — dispatches instructions to OpenClaw agents.

Replaces the tv_autonomy plugin dependency with a direct HTTP call to the
OpenClaw gateway running locally (or remotely).  The gateway authenticates
via a bearer token and routes messages to the target agent.

Usage::

    dispatcher = OpenClawDispatcher()
    result = await dispatcher.dispatch_instruction(
        agent_id="OBSIDIAN",
        instruction="Run full maintenance cycle...",
        context={...},
    )
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

try:
    import aiohttp
except ImportError:  # pragma: no cover — aiohttp is always installed in alpha-engine
    aiohttp = None  # type: ignore[assignment]


class OpenClawDispatcher:
    """Dispatches instructions to OpenClaw agents via the local gateway."""

    def __init__(
        self,
        gateway_url: str = "",
        gateway_token: str = "",
    ):
        self.gateway_url = (
            gateway_url or os.getenv("OPENCLAW_GATEWAY_URL", "http://localhost:18789")
        ).rstrip("/")
        self.gateway_token = gateway_token or os.getenv("OPENCLAW_GATEWAY_TOKEN", "")
        self.enabled = bool(self.gateway_url and self.gateway_token)
        self._dispatch_count = 0
        self._last_dispatch_at = 0.0
        self._last_error = ""

        # Scope locks (mirrors tv_autonomy interface)
        self.allowed_repo_scope: set = {
            os.getenv("OPENCLAW_ALLOWED_REPO", "arigatoexpress/Sapphire")
        }
        self.allowed_project_scope: set = {
            os.getenv("OPENCLAW_ALLOWED_PROJECT", "sapphire-479610")
        }

    async def dispatch_instruction(
        self,
        agent_id: str,
        instruction: str,
        context: Optional[Dict[str, Any]] = None,
        allow_code_changes: bool = False,
        allow_gcloud_changes: bool = False,
        trigger: str = "",
    ) -> Dict[str, Any]:
        """Send an instruction to an OpenClaw agent via the gateway.

        Returns a dict with ``dispatched`` (bool) and ``session_key`` (str).
        """
        if not self.enabled:
            return {"dispatched": False, "reason": "gateway_not_configured"}
        if aiohttp is None:
            return {"dispatched": False, "reason": "aiohttp_not_installed"}

        session_key = hashlib.sha256(
            f"{agent_id}:{instruction[:100]}:{time.time()}".encode()
        ).hexdigest()[:16]

        payload = {
            "agent": agent_id.lower(),
            "message": instruction,
            "session_key": session_key,
            "context": {
                **(context or {}),
                "trigger": trigger,
                "allow_code_changes": allow_code_changes,
                "allow_gcloud_changes": allow_gcloud_changes,
                "repo_scope": list(self.allowed_repo_scope),
                "project_scope": list(self.allowed_project_scope),
            },
        }

        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    "Authorization": f"Bearer {self.gateway_token}",
                    "Content-Type": "application/json",
                }
                async with session.post(
                    f"{self.gateway_url}/api/agent/message",
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    self._last_dispatch_at = time.time()
                    if resp.status in (200, 202):
                        self._dispatch_count += 1
                        self._last_error = ""
                        logger.info(
                            f"[OpenClaw] Dispatched to {agent_id}: session={session_key} trigger={trigger}"
                        )
                        return {
                            "dispatched": True,
                            "session_key": session_key,
                            "agent": agent_id,
                        }
                    body = await resp.text()
                    self._last_error = f"HTTP {resp.status}: {body[:200]}"
                    logger.warning(f"[OpenClaw] Gateway error: {self._last_error}")
                    return {
                        "dispatched": False,
                        "reason": f"gateway_error_{resp.status}",
                        "session_key": session_key,
                    }
        except Exception as exc:
            self._last_error = str(exc)[:200]
            logger.error(f"[OpenClaw] Dispatch failed: {exc}")
            return {
                "dispatched": False,
                "reason": "dispatch_exception",
                "error": self._last_error,
            }

    async def dispatch_session_decision(
        self,
        session_key: str,
        decision: str,
        note: str = "",
    ) -> Dict[str, Any]:
        """Forward a session approval/rejection to the gateway."""
        if not self.enabled:
            return {"dispatched": False, "reason": "gateway_not_configured"}
        if aiohttp is None:
            return {"dispatched": False, "reason": "aiohttp_not_installed"}

        payload = {
            "session_key": session_key,
            "decision": decision.upper(),
            "note": note[:500],
        }

        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    "Authorization": f"Bearer {self.gateway_token}",
                    "Content-Type": "application/json",
                }
                async with session.post(
                    f"{self.gateway_url}/api/agent/session/decision",
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status in (200, 202):
                        return {"dispatched": True, "session_key": session_key}
                    return {"dispatched": False, "reason": f"gateway_error_{resp.status}"}
        except Exception as exc:
            logger.error(f"[OpenClaw] Session decision dispatch failed: {exc}")
            return {"dispatched": False, "reason": "dispatch_exception"}

    def status(self) -> Dict[str, Any]:
        """Return dispatcher status for health checks and Telegram."""
        return {
            "enabled": self.enabled,
            "gateway_url": self.gateway_url,
            "token_configured": bool(self.gateway_token),
            "dispatch_count": self._dispatch_count,
            "last_dispatch_at": self._last_dispatch_at,
            "last_error": self._last_error,
            "allowed_repo_scope": sorted(self.allowed_repo_scope),
            "allowed_project_scope": sorted(self.allowed_project_scope),
        }
