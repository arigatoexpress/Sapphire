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

import asyncio
import hashlib
import json
import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)

try:
    import aiohttp
except ImportError:  # pragma: no cover — aiohttp is always installed in the alpha service
    aiohttp = None  # type: ignore[assignment]

# Default Cloud Run gateway URL; falls back to localhost for local dev.
_DEFAULT_GATEWAY_URL = "https://sapphire-openclaw-cloud-267358751314.us-central1.run.app"


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
        context: dict[str, Any] | None = None,
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
        context: dict[str, Any] | None = None,
        allow_code_changes: bool = False,
        allow_gcloud_changes: bool = False,
        trigger: str = "",
    ) -> dict[str, Any]:
        """Send an instruction to an OpenClaw agent via the gateway.

        Uses ``POST /v1/chat/completions`` with the ``x-openclaw-agent-id``
        header to route to the correct agent.

        The gateway blocks until the full agent session completes (which can
        take several minutes with Claude Opus 4).  To avoid blocking the
        autonomy loop, the actual HTTP call runs in a fire-and-forget
        background task.  This method returns immediately once the request
        is validated and queued.

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

        # Fire the dispatch in a background task — don't block the caller.
        asyncio.create_task(
            self._do_dispatch(agent_id, session_key, payload, trigger)
        )

        self._last_dispatch_at = time.time()
        self._dispatch_count += 1
        logger.info(
            f"[OpenClaw] Dispatched to {agent_id}: session={session_key} trigger={trigger} (async)"
        )
        return {
            "dispatched": True,
            "session_key": session_key,
            "agent": agent_id,
        }

    async def _do_dispatch(
        self,
        agent_id: str,
        session_key: str,
        payload: dict[str, Any],
        trigger: str,
    ) -> None:
        """Background task: POST to the gateway and log the result."""
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
                    timeout=aiohttp.ClientTimeout(total=600),
                ) as resp:
                    if resp.status in (200, 202):
                        self._last_error = ""
                        logger.info(
                            f"[OpenClaw] Agent session completed: {agent_id} "
                            f"session={session_key} trigger={trigger} status={resp.status}"
                        )
                    else:
                        body = await resp.text()
                        self._last_error = f"HTTP {resp.status}: {body[:200]}"
                        logger.warning(f"[OpenClaw] Agent session error: {self._last_error}")
        except Exception as exc:
            err_detail = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
            self._last_error = err_detail[:200]
            logger.warning(
                f"[OpenClaw] Agent session failed: {err_detail} | "
                f"agent={agent_id} session={session_key} trigger={trigger}"
            )

    # ── session decision ─────────────────────────────────────────────────

    async def dispatch_session_decision(
        self,
        session_key: str,
        decision: str,
        note: str = "",
    ) -> dict[str, Any]:
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

    def status(self) -> dict[str, Any]:
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
