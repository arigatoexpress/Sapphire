"""JSONL sink for Telegram channel intel records."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from services.telegram_intel.config import DEFAULT_DATA_DIR
from services.telegram_intel.models import (
    MAX_MESSAGE_CHARS,
    ChannelConfig,
    ClassificationResult,
    RawMessage,
    utc_now_iso,
)
from services.telegram_intel.quality_filter import QualityDecision, sanitize_text

GENERATOR = "services.telegram_intel.reader"
REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_provenance() -> tuple[Any, Any]:
    try:
        from lib.core.provenance import stamp, verify

        return stamp, verify
    except ModuleNotFoundError:
        spec = importlib.util.spec_from_file_location(
            "sapphire_core_provenance",
            REPO_ROOT / "lib" / "core" / "provenance.py",
        )
        if spec is None or spec.loader is None:
            raise
        module = importlib.util.module_from_spec(spec)
        sys.modules.setdefault("sapphire_core_provenance", module)
        spec.loader.exec_module(module)
        return module.stamp, module.verify


stamp, verify = _load_provenance()


@dataclass(frozen=True)
class SinkWriteResult:
    path: Path
    written: int
    duplicates: int

    def to_dict(self) -> dict[str, Any]:
        return {"path": str(self.path), "written": self.written, "duplicates": self.duplicates}


def canonical_message_id(channel_id: str, message_id: str) -> str:
    material = f"{channel_id}:{message_id}".encode()
    return hashlib.sha256(material).hexdigest()[:24]


def _date_key(when: datetime | None = None) -> str:
    moment = when or datetime.now(UTC)
    return moment.astimezone(UTC).strftime("%Y-%m-%d")


def build_record(
    message: RawMessage,
    channel: ChannelConfig,
    quality: QualityDecision,
    classification: ClassificationResult,
    *,
    ingested_at: str | None = None,
    source_paths: tuple[str | Path, ...] = (),
) -> dict[str, Any]:
    clean_text = sanitize_text(message.text)
    truncated = len(sanitize_text(message.text + "x")) > MAX_MESSAGE_CHARS
    payload = {
        "schema_version": 1,
        "canonical_id": canonical_message_id(channel.id, message.message_id),
        "ingested_at": ingested_at or utc_now_iso(),
        "channel": channel.attribution(),
        "message": {
            "id": str(message.message_id),
            "published_at": message.published_at,
            "text": clean_text,
            "truncated": truncated,
        },
        "quality": quality.to_dict(),
        "classifier": classification.to_dict(),
    }
    return stamp(
        payload,
        generator=GENERATOR,
        model=classification.model if classification.source == "local-inference-proxy" else None,
        source_paths=source_paths,
        metadata={"channel_id": channel.id, "message_id": str(message.message_id)},
    )


class TelegramIntelSink:
    def __init__(self, data_dir: Path | str = DEFAULT_DATA_DIR) -> None:
        self.data_dir = Path(data_dir).expanduser()

    def daily_path(self, when: datetime | None = None) -> Path:
        return self.data_dir / _date_key(when) / "messages.jsonl"

    def _seen_ids(self, path: Path) -> set[str]:
        seen: set[str] = set()
        if not path.exists():
            return seen
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

    def write_records(
        self,
        records: list[dict[str, Any]],
        *,
        when: datetime | None = None,
    ) -> SinkWriteResult:
        path = self.daily_path(when)
        path.parent.mkdir(parents=True, exist_ok=True)
        seen = self._seen_ids(path)
        written = 0
        duplicates = 0
        with path.open("a", encoding="utf-8") as handle:
            for record in records:
                canonical_id = str(record.get("canonical_id") or "")
                if not canonical_id or canonical_id in seen:
                    duplicates += 1
                    continue
                if not verify(record):
                    raise ValueError(f"invalid provenance envelope for {canonical_id}")
                handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
                seen.add(canonical_id)
                written += 1
        return SinkWriteResult(path=path, written=written, duplicates=duplicates)

    def recent(self, *, limit: int = 20) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 200))
        files = sorted(self.data_dir.glob("*/messages.jsonl"), reverse=True)
        rows: list[dict[str, Any]] = []
        for path in files:
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            for line in reversed(lines):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                rows.append(row)
                if len(rows) >= limit:
                    return rows
        return rows

    def count_recent(self, *, limit: int = 1000) -> int:
        return len(self.recent(limit=limit))
