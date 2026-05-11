"""Local draft queue primitives for agentic Telegram posts.

This module creates and stores draft records only. It has no Telegram send
adapter and no live publication path.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

VALID_STATUSES = {
    "draft",
    "pending_confirmation",
    "approved_for_manual_send",
    "rejected",
    "snoozed",
}
TERMINAL_STATUSES = {"approved_for_manual_send", "rejected", "snoozed"}


@dataclass(frozen=True)
class TelegramDraft:
    """One proposed Telegram post awaiting explicit operator handling."""

    draft_id: str
    kind: str
    topic: str
    body: str
    source_ids: tuple[str, ...]
    provenance_refs: tuple[str, ...]
    status: str = "draft"
    requires_confirmation: bool = True
    created_at: str = ""
    created_by: str = "sapphire-agent-router"
    target_chat_id: int | None = None
    target_thread_id: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["source_ids"] = list(self.source_ids)
        data["provenance_refs"] = list(self.provenance_refs)
        return data


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _draft_id(material: dict[str, Any]) -> str:
    digest = hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()
    return f"tg_draft_{digest[:16]}"


def build_draft(
    *,
    kind: str,
    topic: str,
    body: str,
    source_ids: tuple[str, ...] = (),
    provenance_refs: tuple[str, ...] = (),
    created_at: str | None = None,
    created_by: str = "sapphire-agent-router",
    target_chat_id: int | None = None,
    target_thread_id: int | None = None,
    requires_confirmation: bool = True,
    metadata: dict[str, Any] | None = None,
) -> TelegramDraft:
    """Build a draft record with a deterministic content hash id."""

    clean_body = str(body or "").strip()
    if not clean_body:
        raise ValueError("Telegram draft body is required")
    clean_kind = str(kind or "").strip() or "digest"
    clean_topic = str(topic or "").strip() or "drafts"
    timestamp = created_at or _now_iso()
    material = {
        "kind": clean_kind,
        "topic": clean_topic,
        "body": clean_body,
        "source_ids": sorted(source_ids),
        "provenance_refs": sorted(provenance_refs),
        "created_at": timestamp,
        "target_chat_id": target_chat_id,
        "target_thread_id": target_thread_id,
        "requires_confirmation": requires_confirmation,
    }
    return TelegramDraft(
        draft_id=_draft_id(material),
        kind=clean_kind,
        topic=clean_topic,
        body=clean_body,
        source_ids=tuple(sorted(str(item) for item in source_ids if str(item).strip())),
        provenance_refs=tuple(sorted(str(item) for item in provenance_refs if str(item).strip())),
        created_at=timestamp,
        created_by=str(created_by or "sapphire-agent-router"),
        target_chat_id=target_chat_id,
        target_thread_id=target_thread_id,
        requires_confirmation=requires_confirmation,
        metadata=dict(metadata or {}),
    )


def transition_draft(
    draft: TelegramDraft,
    *,
    status: str,
    actor: str,
    reason: str = "",
    at: str | None = None,
) -> TelegramDraft:
    """Return a draft with updated local review status."""

    if status not in VALID_STATUSES:
        raise ValueError(f"unsupported Telegram draft status: {status}")
    if draft.status in TERMINAL_STATUSES and status != draft.status:
        raise ValueError(f"cannot transition terminal Telegram draft {draft.draft_id}")
    metadata = dict(draft.metadata)
    history = list(metadata.get("history") or [])
    history.append(
        {
            "at": at or _now_iso(),
            "actor": str(actor or "unknown"),
            "from": draft.status,
            "to": status,
            "reason": str(reason or ""),
        }
    )
    metadata["history"] = history
    return replace(draft, status=status, metadata=metadata)


def append_draft(path: Path | str, draft: TelegramDraft) -> Path:
    """Append one draft record to a local JSONL queue."""

    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(draft.to_dict(), sort_keys=True) + "\n")
    return target


def read_drafts(path: Path | str) -> tuple[TelegramDraft, ...]:
    """Read local JSONL draft records."""

    target = Path(path).expanduser()
    if not target.exists():
        return ()
    drafts: list[TelegramDraft] = []
    for line in target.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        drafts.append(
            TelegramDraft(
                draft_id=str(row["draft_id"]),
                kind=str(row["kind"]),
                topic=str(row["topic"]),
                body=str(row["body"]),
                source_ids=tuple(str(item) for item in row.get("source_ids") or ()),
                provenance_refs=tuple(str(item) for item in row.get("provenance_refs") or ()),
                status=str(row.get("status") or "draft"),
                requires_confirmation=bool(row.get("requires_confirmation", True)),
                created_at=str(row.get("created_at") or ""),
                created_by=str(row.get("created_by") or "sapphire-agent-router"),
                target_chat_id=row.get("target_chat_id"),
                target_thread_id=row.get("target_thread_id"),
                metadata=dict(row.get("metadata") or {}),
            )
        )
    return tuple(drafts)
