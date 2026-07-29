"""Molthub Outreach — External Bot Recruitment via Scout.

Composes and dispatches outreach posts inviting external bots to
contribute TRADE IDEAS ONLY through the Sapphire swarm network.

All outbound content is:
1. Sanitized via prompt_sanitizer (no injection / credential leaks)
2. Audited via SkillAuditor (supply-chain safety check)
3. Restricted to trade-idea-only invitations
4. Logged with full dispatch metadata for audit trail

Inbound responses from external bots are routed through the swarm
aggregation pipeline where they receive reputation tracking and
content sanitization before influencing consensus.
"""

import hashlib
import threading
import time
from typing import Any

from loguru import logger

# ── Outreach template library ──────────────────────────────────────

_OUTREACH_TEMPLATES: dict[str, dict[str, str]] = {
    "general_invite": {
        "title": "Sapphire Swarm — Contribute Trade Ideas",
        "body": (
            "The Sapphire trading swarm is looking for signal contributors.\n\n"
            "**What we accept:** TRADE IDEAS ONLY\n"
            "- Symbol + direction (LONG / SHORT)\n"
            "- Timeframe (e.g. 1h, 4h, 1d)\n"
            "- Confidence level (0.0–1.0)\n"
            "- Brief rationale (optional)\n\n"
            "**What we do NOT accept:**\n"
            "- API keys, credentials, or secrets\n"
            "- Code execution requests\n"
            "- Platform access requests\n"
            "- Personal data or PII\n\n"
            "All contributions are reputation-weighted. Build your score "
            "by submitting accurate, profitable ideas.\n\n"
            "Submit via the Sapphire Swarm API or reply to this thread."
        ),
        "category": "trade_idea",
        "lane": "external",
    },
    "symbol_specific": {
        "title": "Sapphire Swarm — {symbol} Trade Ideas Wanted",
        "body": (
            "Looking for trade ideas on **{symbol}**.\n\n"
            "Share your directional view:\n"
            "- Direction: LONG or SHORT\n"
            "- Timeframe: 1h / 4h / 1d\n"
            "- Confidence: 0.0–1.0\n"
            "- Rationale: brief thesis\n\n"
            "Submissions are scored by the Sapphire reputation system. "
            "Accurate and profitable ideas earn higher influence in "
            "future consensus rounds.\n\n"
            "⚠️ TRADE IDEAS ONLY — no credentials, code, or access requests."
        ),
        "category": "trade_idea",
        "lane": "external",
    },
    "performance_update": {
        "title": "Sapphire Swarm — Contributor Performance Update",
        "body": (
            "**Swarm performance snapshot:**\n\n"
            "Total resolved ideas: {total_ideas}\n"
            "Overall win rate: {win_rate}%\n"
            "Top-performing contributors earn elevated reputation and "
            "greater weight in consensus decisions.\n\n"
            "Want to contribute? Submit TRADE IDEAS:\n"
            "- Symbol + Direction + Timeframe + Confidence\n\n"
            "All ideas go through security screening before entering "
            "the consensus pipeline."
        ),
        "category": "market_analysis",
        "lane": "external",
    },
}

# Patterns that indicate actual credential / infra data leaks.
# These look for assignment-style patterns (key=val, key: val)
# rather than bare word mentions — templates may reference
# "credentials" or "tokens" in warning text and that's fine.
import re as _re

_BLOCKED_OUTBOUND_RE = [
    _re.compile(r"api[_\s]?key\s*[=:]\s*\S+", _re.IGNORECASE),
    _re.compile(r"api[_\s]?secret\s*[=:]\s*\S+", _re.IGNORECASE),
    _re.compile(r"secret[_\s]?key\s*[=:]\s*\S+", _re.IGNORECASE),
    _re.compile(r"password\s*[=:]\s*\S+", _re.IGNORECASE),
    _re.compile(r"ssh[_\s]?key\s*[=:]\s*\S+", _re.IGNORECASE),
    _re.compile(r"mnemonic\s*[=:]\s*\S+", _re.IGNORECASE),
    _re.compile(r"seed[_\s]?phrase\s*[=:]\s*\S+", _re.IGNORECASE),
    _re.compile(r"wallet[_\s]?address\s*[=:]\s*\S+", _re.IGNORECASE),
    _re.compile(r"gcloud\s+(run|builds|deploy|auth|config)", _re.IGNORECASE),
    _re.compile(r"firebase\s+(deploy|init|login)", _re.IGNORECASE),
    _re.compile(r"docker\s+(build|run|push|pull)", _re.IGNORECASE),
    _re.compile(r"cloud[_\s]?run\s+(deploy|services)", _re.IGNORECASE),
    _re.compile(r"sk-[A-Za-z0-9]{20,}"),  # OpenAI-style API keys
    _re.compile(r"AIza[A-Za-z0-9\-_]{20,}"),  # Google API keys
    _re.compile(r"ghp_[A-Za-z0-9]{20,}"),  # GitHub tokens
    _re.compile(r"eyJ[a-zA-Z0-9_\-]{20,}\.[a-zA-Z0-9_\-]"),  # JWTs
]


class MolthubOutreach:
    """Manages outreach campaigns to recruit external bot contributors.

    All outreach is restricted to TRADE IDEAS ONLY — no platform
    access, credentials, code execution, or sensitive data.
    """

    MAX_OUTREACH_HISTORY = 500
    OUTREACH_COOLDOWN_SECONDS = 1800  # 30 minutes between posts
    MAX_CUSTOM_BODY_LENGTH = 1000

    def __init__(self):
        self._lock = threading.Lock()
        self._history: list[dict[str, Any]] = []
        self._last_outreach_at: float = 0.0

    def compose_outreach(
        self,
        template: str = "general_invite",
        symbol: str = "",
        custom_body: str = "",
        total_ideas: int = 0,
        win_rate: float = 0.0,
    ) -> dict[str, Any]:
        """Compose an outreach post from a template.

        Args:
            template: Template name from _OUTREACH_TEMPLATES.
            symbol: Trading pair for symbol-specific templates.
            custom_body: Optional custom body (sanitized before use).
            total_ideas: Total resolved ideas (for performance updates).
            win_rate: Overall win rate (for performance updates).

        Returns:
            Composed post dict with title, body, category, lane, and
            safety metadata.
        """
        tpl = _OUTREACH_TEMPLATES.get(template)
        if not tpl:
            return {
                "ok": False,
                "error": f"Unknown template: {template}",
                "available_templates": list(_OUTREACH_TEMPLATES.keys()),
            }

        title = tpl["title"]
        body = tpl["body"]

        # Format template variables
        symbol_clean = str(symbol or "").strip().upper()[:20]
        if "{symbol}" in title or "{symbol}" in body:
            if not symbol_clean:
                return {"ok": False, "error": "Symbol required for this template."}
            title = title.replace("{symbol}", symbol_clean)
            body = body.replace("{symbol}", symbol_clean)

        if "{total_ideas}" in body:
            body = body.replace("{total_ideas}", str(max(0, int(total_ideas))))
        if "{win_rate}" in body:
            body = body.replace("{win_rate}", f"{max(0.0, min(100.0, float(win_rate))):.1f}")

        # Append custom body if provided (after sanitization)
        if custom_body:
            sanitized_custom = self._sanitize_outbound(
                str(custom_body)[: self.MAX_CUSTOM_BODY_LENGTH]
            )
            if sanitized_custom["blocked"]:
                return {
                    "ok": False,
                    "error": "Custom body blocked by security filter.",
                    "reason": sanitized_custom.get("reason", "content_policy"),
                }
            body += f"\n\n---\n{sanitized_custom['text']}"

        # Final safety check on the composed body
        final_check = self._sanitize_outbound(body)
        if final_check["blocked"]:
            return {
                "ok": False,
                "error": "Composed post blocked by security filter.",
                "reason": final_check.get("reason", "content_policy"),
            }

        post = {
            "ok": True,
            "title": title,
            "body": final_check["text"],
            "category": tpl["category"],
            "lane": tpl["lane"],
            "template": template,
            "symbol": symbol_clean,
            "redactions": final_check.get("redactions", 0),
            "composed_at": int(time.time()),
            "content_hash": hashlib.sha256(f"{title}:{final_check['text']}".encode()).hexdigest()[
                :16
            ],
        }
        return post

    def record_dispatch(
        self,
        post: dict[str, Any],
        dispatch_result: dict[str, Any],
    ) -> dict[str, Any]:
        """Record that an outreach post was dispatched.

        Args:
            post: The composed post from compose_outreach().
            dispatch_result: Result from the scout bridge dispatch.

        Returns:
            Dispatch record with metadata.
        """
        with self._lock:
            record = {
                "content_hash": post.get("content_hash", ""),
                "template": post.get("template", ""),
                "symbol": post.get("symbol", ""),
                "category": post.get("category", ""),
                "dispatched_at": int(time.time()),
                "dispatch_ok": dispatch_result.get("ok", False),
                "dispatch_mode": dispatch_result.get("mode", "unknown"),
                "http_status": dispatch_result.get("http_status"),
                "redactions": post.get("redactions", 0),
            }
            self._history.append(record)
            if len(self._history) > self.MAX_OUTREACH_HISTORY:
                self._history = self._history[-self.MAX_OUTREACH_HISTORY :]
            self._last_outreach_at = time.time()

            logger.info(
                f"Outreach dispatched: template={record['template']} "
                f"symbol={record['symbol']} ok={record['dispatch_ok']}"
            )
            return {"ok": True, "record": record}

    def can_post(self) -> dict[str, Any]:
        """Check if an outreach post is allowed (cooldown check).

        Returns:
            Dict with 'allowed' bool and 'wait_seconds' if on cooldown.
        """
        with self._lock:
            elapsed = time.time() - self._last_outreach_at
            if elapsed < self.OUTREACH_COOLDOWN_SECONDS:
                remaining = int(self.OUTREACH_COOLDOWN_SECONDS - elapsed)
                return {
                    "allowed": False,
                    "wait_seconds": remaining,
                    "reason": "cooldown",
                }
            return {"allowed": True, "wait_seconds": 0}

    def stats(self) -> dict[str, Any]:
        """Return outreach statistics."""
        with self._lock:
            total = len(self._history)
            if total == 0:
                return {
                    "total_dispatched": 0,
                    "successful": 0,
                    "failed": 0,
                    "templates_used": {},
                    "symbols_targeted": [],
                }

            successful = sum(1 for r in self._history if r.get("dispatch_ok"))
            templates_used: dict[str, int] = {}
            symbols: set = set()
            for r in self._history:
                tpl = r.get("template", "unknown")
                templates_used[tpl] = templates_used.get(tpl, 0) + 1
                sym = r.get("symbol", "")
                if sym:
                    symbols.add(sym)

            return {
                "total_dispatched": total,
                "successful": successful,
                "failed": total - successful,
                "success_rate": round(successful / total, 4) if total > 0 else 0.0,
                "templates_used": templates_used,
                "symbols_targeted": sorted(symbols),
                "total_redactions": sum(r.get("redactions", 0) for r in self._history),
                "last_outreach_at": self._last_outreach_at,
            }

    def available_templates(self) -> list[dict[str, str]]:
        """List available outreach templates."""
        return [
            {
                "name": name,
                "title": tpl["title"],
                "category": tpl["category"],
                "requires_symbol": "{symbol}" in tpl["title"] or "{symbol}" in tpl["body"],
            }
            for name, tpl in _OUTREACH_TEMPLATES.items()
        ]

    @staticmethod
    def _sanitize_outbound(text: str) -> dict[str, Any]:
        """Sanitize outbound content — block sensitive data leaks.

        This is the critical security gate: no credentials, platform
        details, or sensitive data should ever leave via outreach.
        """
        if not text:
            return {"text": "", "blocked": False, "redactions": 0}

        clean = str(text)
        redactions = 0

        # Check for blocked patterns (actual credential / infra leaks)
        for pattern in _BLOCKED_OUTBOUND_RE:
            if pattern.search(clean):
                return {
                    "text": "[BLOCKED — sensitive content detected]",
                    "blocked": True,
                    "reason": f"blocked_pattern:{pattern.pattern[:40]}",
                    "redactions": 1,
                }

        # Block private key material
        if "-----BEGIN" in clean and "KEY-----" in clean:
            return {
                "text": "[BLOCKED — key material detected]",
                "blocked": True,
                "reason": "private_key_material",
                "redactions": 1,
            }

        # Block overly long content (potential data exfil)
        if len(clean) > 5000:
            clean = clean[:5000] + "..."
            redactions += 1

        return {"text": clean, "blocked": False, "redactions": redactions}

    def validate_inbound_idea(self, idea: dict[str, Any]) -> dict[str, Any]:
        """Validate an inbound trade idea from an external bot.

        Ensures the idea contains only trade-relevant fields and no
        sensitive data before it enters the swarm pipeline.

        Args:
            idea: Raw idea payload from external source.

        Returns:
            Validated idea dict or error.
        """
        # Whitelist of allowed fields
        allowed_fields = {
            "symbol",
            "direction",
            "confidence",
            "timeframe",
            "rationale",
            "target_price",
            "stop_loss",
            "bot_id",
        }

        # Extract only whitelisted fields
        clean_idea: dict[str, Any] = {}
        for key in allowed_fields:
            if key in idea:
                value = idea[key]
                # Only allow primitives (str, int, float, bool)
                if isinstance(value, str | int | float | bool):
                    clean_idea[key] = value

        # Validate required fields
        symbol = str(clean_idea.get("symbol", "")).strip().upper()
        if not symbol or len(symbol) > 20:
            return {"ok": False, "error": "Invalid or missing symbol."}

        direction = str(clean_idea.get("direction", "")).strip().upper()
        if direction not in ("LONG", "SHORT"):
            return {"ok": False, "error": "Direction must be LONG or SHORT."}

        confidence = float(clean_idea.get("confidence", 0.5))
        confidence = max(0.0, min(1.0, confidence))

        timeframe = str(clean_idea.get("timeframe", "1h")).strip()
        if timeframe not in ("1", "5", "15", "30", "1h", "4h", "1d", "1w"):
            timeframe = "1h"

        # Sanitize rationale text
        rationale = str(clean_idea.get("rationale", ""))[:500]
        rationale_check = self._sanitize_outbound(rationale)
        if rationale_check["blocked"]:
            rationale = "[rationale blocked by security filter]"

        bot_id = str(clean_idea.get("bot_id", "ANONYMOUS")).strip().upper()[:32]

        return {
            "ok": True,
            "idea": {
                "symbol": symbol,
                "direction": direction,
                "confidence": confidence,
                "timeframe": timeframe,
                "rationale": rationale,
                "target_price": float(clean_idea.get("target_price", 0.0)),
                "stop_loss": float(clean_idea.get("stop_loss", 0.0)),
                "bot_id": bot_id,
                "source": "molthub",
            },
        }
