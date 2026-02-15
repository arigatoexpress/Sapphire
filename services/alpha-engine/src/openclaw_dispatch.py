"""OpenClaw Gateway Dispatcher — dispatches instructions to OpenClaw agents.

Sends instructions via the OpenClaw gateway's OpenAI-compatible
``/v1/chat/completions`` endpoint.  The gateway authenticates via a bearer
token and routes to the target agent using the ``x-openclaw-agent-id`` header.

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
import json
import logging
import os
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

try:
    import aiohttp
except ImportError:  # pragma: no cover — aiohttp is always installed in alpha-engine
    aiohttp = None  # type: ignore[assignment]

# Default Cloud Run gateway URL; falls back to localhost for local dev.
_DEFAULT_GATEWAY_URL = "https://openclaw-gateway-267358751314.us-central1.run.app"


class OpenClawDispatcher:
    """Dispatches instructions to OpenClaw agents via the gateway.

    Uses the OpenAI-compatible ``/v1/chat/completions`` endpoint for
    dispatching instructions and the ``/v1/chat/completions`` endpoint
    with a session-decision system message for session decisions.
    """

    def __init__(
        self,
        gateway_url: str = "",
        gateway_token: str = "",
    ):
        self.gateway_url = (
            gateway_url
            or os.getenv("OPENCLAW_GATEWAY_URL", "")
            or _DEFAULT_GATEWAY_URL
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

    # ── helpers ──────────────────────────────────────────────────────────

    def _build_system_context(
        self,
        agent_id: str,
        context: Optional[Dict[str, Any]] = None,
        allow_code_changes: bool = False,
        allow_gcloud_changes: bool = False,
        trigger: str = "",
    ) -> str:
        """Return a system-message string encoding dispatch metadata."""
        ctx = {
            **(context or {}),
            "trigger": trigger,
            "allow_code_changes": allow_code_changes,
            "allow_gcloud_changes": allow_gcloud_changes,
            "repo_scope": list(self.allowed_repo_scope),
            "project_scope": list(self.allowed_project_scope),
        }
        return (
            f"You are {agent_id}, a Sapphire autonomous agent. "
            f"Dispatch context: {json.dumps(ctx, default=str)}"
        )

    # ── dispatch instruction ─────────────────────────────────────────────

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

        Uses ``POST /v1/chat/completions`` with the ``x-openclaw-agent-id``
        header to route to the correct agent.

        Returns a dict with ``dispatched`` (bool) and ``session_key`` (str).
        """
        if not self.enabled:
            return {"dispatched": False, "reason": "gateway_not_configured"}
        if aiohttp is None:
            return {"dispatched": False, "reason": "aiohttp_not_installed"}

        session_key = hashlib.sha256(
            f"{agent_id}:{instruction[:100]}:{time.time()}".encode()
        ).hexdigest()[:16]

        system_ctx = self._build_system_context(
            agent_id, context, allow_code_changes, allow_gcloud_changes, trigger,
        )
        payload = {
            "model": "openclaw",
            "messages": [
                {"role": "system", "content": system_ctx},
                {"role": "user", "content": instruction},
            ],
            "stream": False,
        }

        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    "Authorization": f"Bearer {self.gateway_token}",
                    "Content-Type": "application/json",
                    "x-openclaw-agent-id": agent_id.lower(),
                }
                async with session.post(
                    f"{self.gateway_url}/v1/chat/completions",
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=120),
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
            err_detail = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
            self._last_error = err_detail[:200]
            logger.error(
                f"[OpenClaw] Dispatch failed: {err_detail} | "
                f"url={self.gateway_url}/v1/chat/completions agent={agent_id} trigger={trigger}"
            )
            return {
                "dispatched": False,
                "reason": "dispatch_exception",
                "error": self._last_error,
            }

    # ── session decision ─────────────────────────────────────────────────

    async def dispatch_session_decision(
        self,
        session_key: str,
        decision: str,
        note: str = "",
    ) -> Dict[str, Any]:
        """Forward a session approval/rejection to the gateway.

        Encodes the decision as a chat completion with a system message
        carrying the session key and decision payload.
        """
        if not self.enabled:
            return {"dispatched": False, "reason": "gateway_not_configured"}
        if aiohttp is None:
            return {"dispatched": False, "reason": "aiohttp_not_installed"}

        decision_msg = (
            f"Session decision for key={session_key}: "
            f"{decision.upper()}"
            f"{('. Note: ' + note[:500]) if note else ''}"
        )
        payload = {
            "model": "openclaw",
            "messages": [
                {
                    "role": "system",
                    "content": (
                        f"Process session decision. session_key={session_key} "
                        f"decision={decision.upper()}"
                    ),
                },
                {"role": "user", "content": decision_msg},
            ],
            "stream": False,
        }

        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    "Authorization": f"Bearer {self.gateway_token}",
                    "Content-Type": "application/json",
                }
                async with session.post(
                    f"{self.gateway_url}/v1/chat/completions",
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status in (200, 202):
                        return {"dispatched": True, "session_key": session_key}
                    return {"dispatched": False, "reason": f"gateway_error_{resp.status}"}
        except Exception as exc:
            logger.error(f"[OpenClaw] Session decision dispatch failed: {exc}")
            return {"dispatched": False, "reason": "dispatch_exception"}

    # ── status ───────────────────────────────────────────────────────────

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
