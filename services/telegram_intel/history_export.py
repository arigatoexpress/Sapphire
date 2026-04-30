"""Offline Telegram Desktop export importer.

This module intentionally does not talk to Telegram APIs. It reads local JSON
exports that the operator explicitly points at, sanitizes message text with the
same policy as the channel reader, and writes local-only intelligence artifacts.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from services.telegram_intel.config import REPO_ROOT
from services.telegram_intel.models import MAX_MESSAGE_CHARS, utc_now_iso
from services.telegram_intel.quality_filter import (
    URL_RE,
    WWW_RE,
    infer_tags,
    sanitize_text,
    truncate_text,
)

GENERATOR = "services.telegram_intel.history_export"
DEFAULT_HISTORY_DATA_DIR = REPO_ROOT / "data" / "telegram_history_intel"
MAX_CONTEXT_ITEMS = 50
MAX_SNIPPET_CHARS = 220

OPEN_LOOP_PATTERNS = (
    re.compile(r"\?", re.I),
    re.compile(r"\b(?:can|could|would|will)\s+you\b", re.I),
    re.compile(r"\b(?:please|pls|need to|needs to|todo|to-do|follow up|waiting on)\b", re.I),
    re.compile(r"\b(?:what about|when can|who owns|next step|circle back)\b", re.I),
)
COMMITMENT_PATTERNS = (
    re.compile(r"\b(?:i|we)\s+(?:will|can|should)\b", re.I),
    re.compile(r"\b(?:i'll|we'll|ill)\b", re.I),
    re.compile(r"\b(?:by tomorrow|tonight|next week|send you|follow up|circle back)\b", re.I),
    re.compile(r"\b(?:ship|merge|push|deploy|finish|handle|own)\b", re.I),
)
DECISION_PATTERNS = (
    re.compile(r"\b(?:decided|approved|confirmed|resolved|accepted)\b", re.I),
    re.compile(r"\b(?:go ahead|green light|let's do|we are going with|ship it)\b", re.I),
)


def _load_provenance() -> tuple[Any, Any, Any, Any]:
    try:
        from lib.core.provenance import sha256_file, stamp, verify, write_envelope_sidecar

        return sha256_file, stamp, verify, write_envelope_sidecar
    except ModuleNotFoundError:
        spec = importlib.util.spec_from_file_location(
            "sapphire_core_provenance_history",
            REPO_ROOT / "lib" / "core" / "provenance.py",
        )
        if spec is None or spec.loader is None:
            raise
        module = importlib.util.module_from_spec(spec)
        sys.modules.setdefault("sapphire_core_provenance_history", module)
        spec.loader.exec_module(module)
        return module.sha256_file, module.stamp, module.verify, module.write_envelope_sidecar


sha256_file, stamp, verify, write_envelope_sidecar = _load_provenance()


class HistoryExportError(ValueError):
    """Raised when a Telegram Desktop export cannot be imported safely."""


@dataclass(frozen=True)
class HistoryImportStats:
    export_files: int = 0
    chats: int = 0
    raw_messages: int = 0
    parsed_messages: int = 0
    skipped_messages: int = 0
    written_messages: int = 0
    duplicate_messages: int = 0
    open_loops: int = 0
    commitments: int = 0
    decisions: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "export_files": self.export_files,
            "chats": self.chats,
            "raw_messages": self.raw_messages,
            "parsed_messages": self.parsed_messages,
            "skipped_messages": self.skipped_messages,
            "written_messages": self.written_messages,
            "duplicate_messages": self.duplicate_messages,
            "open_loops": self.open_loops,
            "commitments": self.commitments,
            "decisions": self.decisions,
        }


@dataclass(frozen=True)
class HistoryImportResult:
    data_dir: Path
    messages_path: Path
    context_path: Path
    stats: HistoryImportStats

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": True,
            "data_dir": str(self.data_dir),
            "messages_path": str(self.messages_path),
            "context_path": str(self.context_path),
            "stats": self.stats.to_dict(),
        }


def discover_export_files(export_path: str | Path) -> tuple[Path, ...]:
    """Return Telegram Desktop JSON export files from a file or export directory."""
    path = Path(export_path).expanduser()
    if path.is_file():
        return (path,)
    if not path.exists():
        raise HistoryExportError(f"export path not found: {path}")
    if not path.is_dir():
        raise HistoryExportError(f"export path is not a file or directory: {path}")
    result = path / "result.json"
    if result.is_file():
        return (result,)
    files = tuple(sorted(candidate for candidate in path.glob("*.json") if candidate.is_file()))
    if not files:
        raise HistoryExportError(f"no JSON export files found under: {path}")
    return files


def import_history_export(
    export_path: str | Path,
    *,
    data_dir: str | Path | None = DEFAULT_HISTORY_DATA_DIR,
    include_title_hints: bool = False,
    limit: int | None = None,
) -> HistoryImportResult:
    """Import a local Telegram Desktop JSON export into sanitized local artifacts."""
    files = discover_export_files(export_path)
    output_dir = Path(data_dir or DEFAULT_HISTORY_DATA_DIR).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)

    records: list[dict[str, Any]] = []
    raw_messages = 0
    chats_seen: set[str] = set()
    skipped = 0

    for export_file in files:
        payload = _load_json(export_file)
        source_hash = sha256_file(export_file)
        for chat in _iter_chats(payload):
            chats_seen.add(_chat_hash(chat))
            messages = chat.get("messages") or []
            if not isinstance(messages, list):
                continue
            for row in messages:
                raw_messages += 1
                if limit is not None and len(records) >= max(0, int(limit)):
                    continue
                if not isinstance(row, dict):
                    skipped += 1
                    continue
                record = _build_message_record(
                    row,
                    chat=chat,
                    export_file=export_file,
                    source_hash=source_hash,
                    include_title_hints=include_title_hints,
                )
                if record is None:
                    skipped += 1
                    continue
                records.append(record)

    messages_path, written, duplicates = _write_messages(output_dir, records)
    context_path = _write_context(output_dir, records, files=files)
    stats = HistoryImportStats(
        export_files=len(files),
        chats=len(chats_seen),
        raw_messages=raw_messages,
        parsed_messages=len(records),
        skipped_messages=skipped,
        written_messages=written,
        duplicate_messages=duplicates,
        open_loops=sum(1 for record in records if record["conversation"]["signals"]["open_loop"]),
        commitments=sum(1 for record in records if record["conversation"]["signals"]["commitment"]),
        decisions=sum(1 for record in records if record["conversation"]["signals"]["decision"]),
    )
    return HistoryImportResult(
        data_dir=output_dir,
        messages_path=messages_path,
        context_path=context_path,
        stats=stats,
    )


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HistoryExportError(f"export JSON parse failed: {path.name}") from exc
    if not isinstance(payload, dict):
        raise HistoryExportError(f"export root must be a mapping: {path.name}")
    return payload


def _iter_chats(payload: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    if isinstance(payload.get("messages"), list):
        return (
            {
                "id": payload.get("id") or payload.get("name") or "root-export",
                "name": payload.get("name") or "Telegram export",
                "type": payload.get("type") or "telegram_export",
                "messages": payload.get("messages") or [],
            },
        )

    chats = payload.get("chats")
    if isinstance(chats, dict):
        rows = chats.get("list") or []
    elif isinstance(chats, list):
        rows = chats
    else:
        rows = []
    return tuple(row for row in rows if isinstance(row, dict))


def _build_message_record(
    row: dict[str, Any],
    *,
    chat: dict[str, Any],
    export_file: Path,
    source_hash: str,
    include_title_hints: bool,
) -> dict[str, Any] | None:
    text = flatten_telegram_text(row.get("text"))
    media_kind = _media_kind(row)
    if not text and not media_kind:
        return None

    sanitized = sanitize_text(text or f"[{media_kind}]")
    if not sanitized:
        return None

    chat_hash = _chat_hash(chat)
    message_id = str(row.get("id") or row.get("message_id") or _stable_hash(sanitized, 12))
    published_at = _published_at(row)
    signals = _signals_for(sanitized)
    tags = infer_tags(sanitized)
    payload: dict[str, Any] = {
        "schema_version": 1,
        "canonical_id": _canonical_message_id(chat_hash, message_id, published_at),
        "ingested_at": utc_now_iso(),
        "source": {
            "kind": "telegram_desktop_json_export",
            "file_sha256": source_hash,
        },
        "chat": {
            "id_hash": chat_hash,
            "type": str(chat.get("type") or "unknown"),
        },
        "message": {
            "id": message_id,
            "published_at": published_at,
            "sender_hash": _sender_hash(chat_hash, row),
            "reply_to_message_id": _optional_str(row.get("reply_to_message_id")),
            "forwarded_from_hash": _optional_hash(row.get("forwarded_from")),
            "text": sanitized,
            "truncated": len(sanitize_text((text or "") + "x")) > MAX_MESSAGE_CHARS,
            "media_kind": media_kind,
            "link_domains": _link_domains(text),
        },
        "conversation": {
            "day": published_at[:10],
            "tags": list(tags),
            "signals": signals,
        },
    }
    if include_title_hints:
        payload["chat"]["title_hint"] = truncate_text(
            sanitize_text(str(chat.get("name") or chat.get("title") or "")),
            max_chars=80,
        )
    return stamp(
        payload,
        generator=GENERATOR,
        source_paths=(Path(__file__),),
        metadata={
            "chat_id_hash": chat_hash,
            "message_id": message_id,
            "source_file_sha256": source_hash,
        },
    )


def flatten_telegram_text(value: Any) -> str:
    """Flatten Telegram Desktop text values without preserving entity metadata."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return flatten_telegram_text(value.get("text"))
    if isinstance(value, list):
        return "".join(flatten_telegram_text(item) for item in value)
    return str(value)


def _published_at(row: dict[str, Any]) -> str:
    unix_value = row.get("date_unixtime")
    if unix_value is not None:
        try:
            return datetime.fromtimestamp(int(str(unix_value)), tz=UTC).replace(microsecond=0).isoformat()
        except (TypeError, ValueError, OSError):
            pass
    raw = str(row.get("date") or "").strip()
    if raw:
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return parsed.astimezone(UTC).replace(microsecond=0).isoformat()
        except ValueError:
            pass
    return utc_now_iso()


def _media_kind(row: dict[str, Any]) -> str | None:
    for key in ("media_type", "mime_type"):
        value = row.get(key)
        if value:
            return str(value).split("/")[0][:40]
    for key in ("photo", "video_file", "audio_file", "file", "sticker_emoji"):
        if row.get(key):
            return key.replace("_file", "")
    return None


def _signals_for(text: str) -> dict[str, Any]:
    return {
        "open_loop": any(pattern.search(text) for pattern in OPEN_LOOP_PATTERNS),
        "commitment": any(pattern.search(text) for pattern in COMMITMENT_PATTERNS),
        "decision": any(pattern.search(text) for pattern in DECISION_PATTERNS),
    }


def _link_domains(text: str) -> list[str]:
    domains: set[str] = set()
    for pattern in (URL_RE, WWW_RE):
        for match in pattern.finditer(text or ""):
            raw = match.group(0)
            parsed = urlparse(raw if "://" in raw else f"http://{raw}")
            if parsed.hostname:
                domains.add(parsed.hostname.lower())
    return sorted(domains)[:20]


def _chat_hash(chat: dict[str, Any]) -> str:
    material = f"{chat.get('id') or ''}:{chat.get('name') or chat.get('title') or ''}:{chat.get('type') or ''}"
    return "chat_" + _stable_hash(material, 16)


def _sender_hash(chat_hash: str, row: dict[str, Any]) -> str:
    sender = (
        row.get("from_id")
        or row.get("actor_id")
        or row.get("from")
        or row.get("actor")
        or "unknown"
    )
    return "participant_" + _stable_hash(f"{chat_hash}:{sender}", 12)


def _optional_hash(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return "ref_" + _stable_hash(str(value), 12)


def _optional_str(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _canonical_message_id(chat_hash: str, message_id: str, published_at: str) -> str:
    return _stable_hash(f"telegram-history:v1:{chat_hash}:{message_id}:{published_at}", 24)


def _stable_hash(value: str, length: int = 16) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def _seen_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    seen: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        canonical_id = row.get("canonical_id")
        if isinstance(canonical_id, str):
            seen.add(canonical_id)
    return seen


def _write_messages(output_dir: Path, records: list[dict[str, Any]]) -> tuple[Path, int, int]:
    path = output_dir / "messages.jsonl"
    seen = _seen_ids(path)
    written = 0
    duplicates = 0
    with path.open("a", encoding="utf-8") as handle:
        for record in records:
            canonical_id = str(record.get("canonical_id") or "")
            if not canonical_id or canonical_id in seen:
                duplicates += 1
                continue
            if not verify(record):
                raise HistoryExportError(f"invalid provenance envelope for {canonical_id}")
            handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
            seen.add(canonical_id)
            written += 1
    if path.exists():
        write_envelope_sidecar(
            path,
            generator=GENERATOR,
            source_paths=(Path(__file__),),
            metadata={
                "artifact_type": "telegram_history_messages_jsonl",
                "written": written,
                "duplicates": duplicates,
            },
        )
    return path, written, duplicates


def _write_context(output_dir: Path, records: list[dict[str, Any]], *, files: tuple[Path, ...]) -> Path:
    path = output_dir / "conversation_context.json"
    context = stamp(
        _build_context(records, files=files),
        generator=GENERATOR,
        source_paths=(Path(__file__),),
        metadata={"artifact_type": "telegram_history_conversation_context"},
    )
    if not verify(context):
        raise HistoryExportError("invalid conversation context provenance")
    path.write_text(json.dumps(context, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_envelope_sidecar(
        path,
        generator=GENERATOR,
        source_paths=(Path(__file__),),
        metadata={"artifact_type": "telegram_history_conversation_context"},
    )
    return path


def _build_context(records: list[dict[str, Any]], *, files: tuple[Path, ...]) -> dict[str, Any]:
    chats: dict[str, dict[str, Any]] = {}
    global_tags: Counter[str] = Counter()
    open_loops: list[dict[str, Any]] = []
    commitments: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []

    for record in records:
        chat_hash = record["chat"]["id_hash"]
        message = record["message"]
        conversation = record["conversation"]
        chat = chats.setdefault(
            chat_hash,
            {
                "chat_hash": chat_hash,
                "type": record["chat"].get("type", "unknown"),
                "message_count": 0,
                "participant_hashes": set(),
                "first_message_at": message["published_at"],
                "last_message_at": message["published_at"],
                "top_tags": Counter(),
                "open_loop_count": 0,
                "commitment_count": 0,
                "decision_count": 0,
            },
        )
        chat["message_count"] += 1
        chat["participant_hashes"].add(message["sender_hash"])
        chat["first_message_at"] = min(chat["first_message_at"], message["published_at"])
        chat["last_message_at"] = max(chat["last_message_at"], message["published_at"])
        for tag in conversation.get("tags") or []:
            global_tags[str(tag)] += 1
            chat["top_tags"][str(tag)] += 1

        signals = conversation["signals"]
        signal_item = _signal_item(record)
        if signals["open_loop"]:
            chat["open_loop_count"] += 1
            if len(open_loops) < MAX_CONTEXT_ITEMS:
                open_loops.append(signal_item)
        if signals["commitment"]:
            chat["commitment_count"] += 1
            if len(commitments) < MAX_CONTEXT_ITEMS:
                commitments.append(signal_item)
        if signals["decision"]:
            chat["decision_count"] += 1
            if len(decisions) < MAX_CONTEXT_ITEMS:
                decisions.append(signal_item)

    chat_rows = []
    for chat in chats.values():
        participant_count = len(chat.pop("participant_hashes"))
        top_tags = _counter_rows(chat.pop("top_tags"))
        chat_rows.append({**chat, "participant_count": participant_count, "top_tags": top_tags})

    return {
        "schema_version": 1,
        "generated_at": utc_now_iso(),
        "source": {
            "kind": "telegram_desktop_json_export",
            "file_count": len(files),
            "file_sha256": [sha256_file(path) for path in files],
        },
        "summary": {
            "chats": len(chats),
            "messages": len(records),
            "participants": _participant_count(records),
            "open_loops": sum(row["open_loop_count"] for row in chat_rows),
            "commitments": sum(row["commitment_count"] for row in chat_rows),
            "decisions": sum(row["decision_count"] for row in chat_rows),
            "top_tags": _counter_rows(global_tags),
        },
        "chats": sorted(chat_rows, key=lambda row: (-int(row["message_count"]), row["chat_hash"])),
        "open_loops": open_loops,
        "commitments": commitments,
        "decisions": decisions,
    }


def _participant_count(records: list[dict[str, Any]]) -> int:
    participants_by_chat: dict[str, set[str]] = defaultdict(set)
    for record in records:
        participants_by_chat[record["chat"]["id_hash"]].add(record["message"]["sender_hash"])
    return sum(len(participants) for participants in participants_by_chat.values())


def _counter_rows(counter: Counter[str]) -> list[dict[str, Any]]:
    return [{"tag": key, "count": value} for key, value in counter.most_common(10)]


def _signal_item(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "canonical_id": record["canonical_id"],
        "chat_hash": record["chat"]["id_hash"],
        "published_at": record["message"]["published_at"],
        "sender_hash": record["message"]["sender_hash"],
        "snippet": truncate_text(record["message"]["text"], max_chars=MAX_SNIPPET_CHARS),
    }


__all__ = [
    "DEFAULT_HISTORY_DATA_DIR",
    "GENERATOR",
    "HistoryExportError",
    "HistoryImportResult",
    "HistoryImportStats",
    "discover_export_files",
    "flatten_telegram_text",
    "import_history_export",
]
