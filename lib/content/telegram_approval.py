"""Telegram inline-keyboard bridge for content approval.

When ``approval.approve(require_human=True)`` parks a draft in
``data/content/pending/``, this module sends a Telegram message with
Approve / Reject / View buttons so the reviewer doesn't have to SSH in.

Callback payloads are short (``apv:<slug>``) to stay under Telegram's 64-byte
``callback_data`` cap. The legacy bot or a hermes skill decodes them and calls
``handle_callback(...)`` which runs the real approval/rejection, edits the
original message to show the outcome, and answers the callback.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_REPO = Path(__file__).resolve().parents[2]
_PENDING_DIR = _REPO / "data" / "content" / "pending"
_APPROVALS_FILE = _REPO / "data" / "content" / "approvals.jsonl"
_READY_DIR = _REPO / "data" / "content" / "ready"
_REJECTED_DIR = _REPO / "data" / "content" / "rejected"

# Keep callback_data < 64 bytes. Slug is the part after the timestamp in the
# pending filename; we pass slug only, then look up the newest matching file.
_CB_APPROVE = "apv"
_CB_REJECT = "rej"
_CB_VIEW = "vw"


def _safe_send():
    """Lazy import so tests can run without the sapphire_telegram package installed."""
    sys.path.insert(0, str(_REPO / "lib" / "telegram" / "src"))
    from sapphire_telegram import safe_send  # type: ignore

    return safe_send


def build_keyboard(slug: str) -> dict:
    """Return a Telegram inline-keyboard payload for this draft's slug."""
    return {
        "inline_keyboard": [
            [
                {"text": "✅ Approve", "callback_data": f"{_CB_APPROVE}:{slug}"},
                {"text": "❌ Reject", "callback_data": f"{_CB_REJECT}:{slug}"},
            ],
            [{"text": "📄 View Draft", "callback_data": f"{_CB_VIEW}:{slug}"}],
        ]
    }


def _rel(path: Path) -> str:
    """Repo-relative path when possible, absolute string otherwise (e.g. tmp dirs)."""
    try:
        return str(path.relative_to(_REPO))
    except ValueError:
        return str(path)


def _find_pending(slug: str) -> Path | None:
    """Locate the newest pending draft whose filename ends with ``<slug>.json``."""
    if not _PENDING_DIR.exists():
        return None
    matches = sorted(
        _PENDING_DIR.glob(f"*_{slug}.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return matches[0] if matches else None


def request_approval(
    *,
    kind: str,
    title: str,
    slug: str,
    preview: str,
    bot_token: str | None = None,
    chat_id: str | None = None,
) -> dict:
    """Send a Telegram approval request with inline Approve/Reject buttons.

    Args:
        kind: Report kind (``weekly_crypto_brief``, ``ai_intel``, …).
        title: Human-readable title for the message banner.
        slug: Draft slug used in the callback payload.
        preview: Up to ~800 chars of the body (truncated) for context.
        bot_token / chat_id: overrides; otherwise resolved from env/secrets.

    Returns:
        Dict from ``safe_send.send()`` (``ok`` + metadata).
    """
    ss = _safe_send()
    banner = f"Pending approval: {kind}"
    snippet = preview.strip()
    if len(snippet) > 800:
        snippet = snippet[:800].rstrip() + "…"
    text = f"*{title}*\n\n{snippet}\n\n_Respond with a button below._"
    return ss.send(
        text,
        priority="p1",
        parse_mode="markdown",
        reply_markup=build_keyboard(slug),
        banner=banner,
        bot_token=bot_token,
        chat_id=chat_id,
    )


def _answer_callback(callback_id: str, text: str, *, bot_token: str | None = None) -> dict:
    """POST /answerCallbackQuery so the button stops spinning in the client."""
    ss = _safe_send()
    token = ss.get_bot_token(bot_token)
    if not token:
        return {"ok": False, "error": "missing_bot_token"}
    url = f"https://api.telegram.org/bot{token}/answerCallbackQuery"
    status, resp = ss._post(url, {"callback_query_id": callback_id, "text": text})
    return {"ok": status == 200 and resp.get("ok", False), "response": resp}


def _edit_message(
    chat_id: str | int,
    message_id: int,
    text: str,
    *,
    bot_token: str | None = None,
) -> dict:
    """Edit the original approval message to reflect the outcome (removes keyboard)."""
    ss = _safe_send()
    token = ss.get_bot_token(bot_token)
    if not token:
        return {"ok": False, "error": "missing_bot_token"}
    url = f"https://api.telegram.org/bot{token}/editMessageText"
    status, resp = ss._post(
        url,
        {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "disable_web_page_preview": True,
        },
    )
    return {"ok": status == 200 and resp.get("ok", False), "response": resp}


def _move_pending(src: Path, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    src.rename(dest)
    return dest


def _append_approval(record: dict[str, Any]) -> None:
    _APPROVALS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with _APPROVALS_FILE.open("a") as f:
        f.write(json.dumps(record) + "\n")


def handle_callback(
    callback_data: str,
    *,
    callback_id: str | None = None,
    chat_id: str | int | None = None,
    message_id: int | None = None,
    actor: str = "telegram",
    bot_token: str | None = None,
) -> dict:
    """Process an inline-keyboard callback.

    Decodes ``apv:<slug>`` / ``rej:<slug>`` / ``vw:<slug>``, runs the matching
    side effect (move draft, log approval record, edit message), and answers
    the callback when ``callback_id`` is provided.

    Args:
        callback_data: The ``callback_data`` field Telegram delivered.
        callback_id: Telegram's ``callback_query.id`` (to stop the spinner).
        chat_id / message_id: original message coords (to edit it after).
        actor: identity of approver, written into the approval record.
        bot_token: override; otherwise resolved from env/secrets.

    Returns:
        Dict with ``ok``, ``action``, ``slug``, ``status``, ``reason``.
    """
    if ":" not in callback_data:
        return {"ok": False, "error": "malformed_callback", "raw": callback_data}

    action, slug = callback_data.split(":", 1)
    if action not in (_CB_APPROVE, _CB_REJECT, _CB_VIEW):
        return {"ok": False, "error": "unknown_action", "action": action}

    pending = _find_pending(slug)
    if not pending:
        if callback_id:
            _answer_callback(callback_id, "Draft not found (already handled?)", bot_token=bot_token)
        return {"ok": False, "error": "not_found", "slug": slug}

    now = datetime.now(UTC).isoformat()

    if action == _CB_VIEW:
        try:
            body = json.loads(pending.read_text()).get("body", "")
        except Exception as e:
            body = f"(failed to read draft: {e})"
        # Preview up to first 3500 chars (Telegram fits ~4096 in one message)
        preview = body[:3500] + ("…" if len(body) > 3500 else "")
        if callback_id:
            _answer_callback(callback_id, "Draft sent", bot_token=bot_token)
        ss = _safe_send()
        ss.send(
            preview,
            priority="p2",
            banner=f"Draft preview: {slug}",
            prefix=True,
            bot_token=bot_token,
        )
        return {"ok": True, "action": action, "slug": slug, "status": "viewed"}

    if action == _CB_APPROVE:
        ready = _move_pending(pending, _READY_DIR)
        _append_approval(
            {
                "kind": slug.replace("-", "_"),
                "slug": slug,
                "status": "approved",
                "approved_by": actor,
                "file": _rel(ready),
                "timestamp": now,
            }
        )
        outcome = f"✅ Approved by {actor} — moved to ready/"
        if callback_id:
            _answer_callback(callback_id, "Approved", bot_token=bot_token)
        if chat_id is not None and message_id is not None:
            _edit_message(chat_id, message_id, f"{outcome}\n{ready.name}", bot_token=bot_token)
        return {
            "ok": True,
            "action": action,
            "slug": slug,
            "status": "approved",
            "path": str(ready),
        }

    # reject
    rejected = _move_pending(pending, _REJECTED_DIR)
    _append_approval(
        {
            "kind": slug.replace("-", "_"),
            "slug": slug,
            "status": "rejected",
            "approved_by": actor,
            "file": _rel(rejected),
            "timestamp": now,
        }
    )
    outcome = f"❌ Rejected by {actor} — moved to rejected/"
    if callback_id:
        _answer_callback(callback_id, "Rejected", bot_token=bot_token)
    if chat_id is not None and message_id is not None:
        _edit_message(chat_id, message_id, f"{outcome}\n{rejected.name}", bot_token=bot_token)
    return {"ok": True, "action": action, "slug": slug, "status": "rejected", "path": str(rejected)}
