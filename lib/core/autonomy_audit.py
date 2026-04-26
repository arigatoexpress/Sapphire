"""Structured audit log for Sapphire autonomous decisions.

This module is intentionally small and boring: append-only JSONL, bounded
fields, key-name redaction, and no raw payload capture. It complements the
existing confirmation-firewall and kill-switch audit logs.
"""

from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

AUTONOMY_AUDIT_LOG_ENV = "SAPPHIRE_AUTONOMY_AUDIT_LOG"
DEFAULT_AUTONOMY_AUDIT_LOG = Path.home() / ".sapphire" / "audit" / "autonomy.jsonl"

_SECRET_KEY_RE = re.compile(
    r"(api[_-]?key|token|password|passwd|secret|private[_-]?key|credential|authorization)",
    re.IGNORECASE,
)
_SECRET_TEXT_PATTERNS = (
    re.compile(r"(?i)\b(api[_-]?key|token|password|secret|private[_-]?key)\s*[:=]\s*[^,\s]+"),
    re.compile(r"(?i)\b(bearer)\s+[a-z0-9._~+/=-]+"),
)


class AutonomyAuditLog:
    """Append redacted autonomy events to a local JSONL file."""

    def __init__(
        self,
        path: str | Path | bool | None = None,
        *,
        now: Callable[[], float] | None = None,
    ) -> None:
        self.path = self._resolve_path(path)
        self._now = now or time.time

    def append(
        self,
        event_type: str,
        *,
        actor: str,
        action: str,
        outcome: str,
        risk: str = "",
        object_ref: str = "",
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        """Append one audit event.

        Metadata is recursively sanitized; callers should still pass summaries
        rather than raw prompts, request bodies, secrets, or trade payloads.
        """
        if self.path is None:
            return
        record: dict[str, Any] = {
            "event_type": _bounded_text(event_type, max_len=120),
            "ts": self._now(),
            "actor": _bounded_text(actor, max_len=120),
            "action": _bounded_text(action, max_len=160),
            "outcome": _bounded_text(outcome, max_len=80),
        }
        if risk:
            record["risk"] = _bounded_text(risk, max_len=80)
        if object_ref:
            record["object_ref"] = _bounded_text(object_ref, max_len=160)
        if metadata:
            record["metadata"] = sanitize_metadata(metadata)

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")

    @staticmethod
    def _resolve_path(path: str | Path | bool | None) -> Path | None:
        if path is False:
            return None
        if path:
            return Path(path).expanduser()
        configured = os.environ.get(AUTONOMY_AUDIT_LOG_ENV)
        if configured:
            return Path(configured).expanduser()
        return DEFAULT_AUTONOMY_AUDIT_LOG


def sanitize_metadata(value: Any, *, max_depth: int = 4) -> Any:
    """Return a JSON-safe, redacted, size-bounded metadata value."""
    return _sanitize(value, depth=0, max_depth=max_depth)


def _sanitize(value: Any, *, depth: int, max_depth: int) -> Any:
    if depth >= max_depth:
        return "<max_depth>"
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        return _bounded_text(value)
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for idx, (key, item) in enumerate(value.items()):
            if idx >= 50:
                out["<truncated>"] = len(value) - 50
                break
            safe_key = _bounded_text(str(key), max_len=80)
            if _SECRET_KEY_RE.search(safe_key):
                out[safe_key] = "<redacted>"
            else:
                out[safe_key] = _sanitize(item, depth=depth + 1, max_depth=max_depth)
        return out
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray):
        items = [_sanitize(item, depth=depth + 1, max_depth=max_depth) for item in list(value)[:20]]
        if len(value) > 20:
            items.append({"<truncated>": len(value) - 20})
        return items
    return _bounded_text(str(value))


def _bounded_text(value: str, *, max_len: int = 240) -> str:
    text = str(value or "")
    for pattern in _SECRET_TEXT_PATTERNS:
        text = pattern.sub(lambda match: f"{match.group(1)}=<redacted>", text)
    text = " ".join(text.split())
    if len(text) > max_len:
        return text[: max_len - 3] + "..."
    return text
