"""Paste-safe autonomy audit hooks for Alpha.

These helpers are intentionally separate from ``main.py`` so safety-critical
audit formatting can be tested without constructing the full Alpha engine.
"""

from __future__ import annotations

import hashlib
import logging
import re
import sys
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_SAFE_CODE_RE = re.compile(r"[^a-zA-Z0-9_.:-]+")
_SECRET_TEXT_PATTERNS = (
    re.compile(r"(?i)\b(api[_-]?key|token|password|secret|private[_-]?key)\s*[:=]\s*[^,\s]+"),
    re.compile(r"(?i)\b(bearer)\s+[a-z0-9._~+/=-]+"),
)


def append_alpha_session_decision_audit(
    *,
    session_key: str,
    decision: str,
    source: str,
    dispatched: bool,
    reason: str = "",
    hook_result: dict[str, Any] | None = None,
    note_chars: int = 0,
) -> None:
    """Append sanitized audit metadata for an Alpha autonomy session decision."""
    try:
        audit_log_cls = _autonomy_audit_log_cls()
        clean_decision = str(decision or "").strip().upper()
        clean_session = str(session_key or "").strip()
        clean_source = str(source or "").strip()
        audit_log_cls().append(
            "autonomy.session_decision_applied",
            actor="alpha_engine",
            action="apply_session_decision",
            outcome=_decision_outcome(clean_decision, dispatched),
            risk="autonomy_coordination",
            object_ref="alpha_autonomy_session",
            metadata={
                "decision": clean_decision.lower() or "unknown",
                "dispatched": bool(dispatched),
                "reason_code": _safe_code(reason),
                "session_key_hash": _short_hash(clean_session),
                "session_key_chars": len(clean_session),
                "source_hash": _short_hash(clean_source),
                "source_chars": len(clean_source),
                "note_chars": max(0, int(note_chars or 0)),
                "hook_result_keys": sorted(str(key) for key in (hook_result or {})),
            },
        )
    except Exception as exc:
        log.warning("alpha autonomy session audit write failed: %s", exc)


def _decision_outcome(decision: str, dispatched: bool) -> str:
    prefix = "approved" if decision == "APPROVE" else "rejected" if decision == "REJECT" else "unknown"
    suffix = "dispatched" if dispatched else "not_dispatched"
    return f"{prefix}_{suffix}"


def _short_hash(value: str) -> str:
    if not value:
        return ""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def _safe_code(value: object, *, max_len: int = 80) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    for pattern in _SECRET_TEXT_PATTERNS:
        text = pattern.sub(lambda match: f"{match.group(1)}_redacted", text)
    text = _SAFE_CODE_RE.sub("_", text).strip("_")
    if len(text) > max_len:
        return text[:max_len]
    return text


def _autonomy_audit_log_cls() -> type:
    try:
        from lib.core.autonomy_audit import AutonomyAuditLog

        return AutonomyAuditLog
    except ModuleNotFoundError:
        repo_root = Path(__file__).resolve().parents[3]
        repo_root_text = str(repo_root)
        if repo_root_text not in sys.path:
            sys.path.insert(0, repo_root_text)
        from lib.core.autonomy_audit import AutonomyAuditLog

        return AutonomyAuditLog
