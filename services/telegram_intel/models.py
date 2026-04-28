"""Shared dataclasses and caps for the Telegram intel reader."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

MAX_CHANNELS = 32
MAX_MESSAGES_PER_HOUR = 600
MAX_CLASSIFICATIONS_PER_HOUR = 200
MAX_MESSAGE_CHARS = 8000
TRUNCATION_SUFFIX = "[…]"
VALID_CATEGORIES = frozenset(
    {"crypto", "macro", "ai", "security", "trading", "governance"}
)


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class ChannelConfig:
    """One configured Telegram channel source."""

    id: str
    source: str
    category: str = "security"
    weight: float = 1.0
    enabled: bool = True
    backend: str = "mtproto"
    label: str | None = None
    topics: tuple[str, ...] = ()
    notes: str = ""
    min_quality_score: float = 0.45
    min_message_length: int = 32

    @property
    def min_quality(self) -> float:
        """Backward-compatible alias for older callers/tests."""
        return self.min_quality_score

    def attribution(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "label": self.label or self.id,
            "category": self.category,
            "weight": self.weight,
            "backend": self.backend,
        }


@dataclass(frozen=True)
class RawMessage:
    """Raw message shape returned by reader backends before sanitization."""

    channel_id: str
    message_id: str
    text: str
    published_at: str
    url: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ClassificationResult:
    """Optional local-model classification result."""

    label: str
    confidence: float
    topics: tuple[str, ...] = ()
    model: str = "heuristic"
    source: str = "heuristic-fallback"
    rationale: str = ""
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = {
            "label": self.label,
            "confidence": round(float(self.confidence), 4),
            "topics": list(self.topics),
            "model": self.model,
            "source": self.source,
            "rationale": self.rationale[:500],
        }
        if self.error:
            data["error"] = self.error
        return data

    @classmethod
    def fallback(
        cls,
        *,
        label: str = "unclassified",
        confidence: float = 0.0,
        topics: tuple[str, ...] = (),
        reason: str = "classifier disabled",
    ) -> ClassificationResult:
        return cls(
            label=label,
            confidence=confidence,
            topics=topics,
            model="heuristic",
            source="heuristic-fallback",
            rationale=reason,
            error=reason,
        )


@dataclass(frozen=True)
class PullStats:
    channels: int = 0
    raw_messages: int = 0
    kept_messages: int = 0
    low_quality_messages: int = 0
    written_messages: int = 0
    duplicate_messages: int = 0
    classifier_calls: int = 0
    errors: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "channels": self.channels,
            "raw_messages": self.raw_messages,
            "kept_messages": self.kept_messages,
            "low_quality_messages": self.low_quality_messages,
            "written_messages": self.written_messages,
            "duplicate_messages": self.duplicate_messages,
            "classifier_calls": self.classifier_calls,
            "errors": list(self.errors),
        }
