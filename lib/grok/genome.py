"""Genome lessons — close the self-improve loop (schema + pure helpers).

Plant wires broker-reconciled closes into LessonBook.append. No I/O here.
See data/grok-web-exports/2026-08-08_genome-broker-reconcile-contract.md.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

# Canonical lesson sources (plant + seeds). Prefer broker over auto_estimate.
SOURCE_BROKER = "broker"
SOURCE_AUTO_ESTIMATE = "auto_estimate"
SOURCE_AXTI = "axti"
SOURCE_DENS = "dens"
SOURCE_MANUAL = "manual"
SOURCE_PAPER = "paper"
SOURCE_L2 = "l2"
SOURCE_MOSS = "moss"

KNOWN_SOURCES: frozenset[str] = frozenset(
    {
        SOURCE_BROKER,
        SOURCE_AUTO_ESTIMATE,
        SOURCE_AXTI,
        SOURCE_DENS,
        SOURCE_MANUAL,
        SOURCE_PAPER,
        SOURCE_L2,
        SOURCE_MOSS,
    }
)


def _utc_now() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def realized_pnl_long(
    *,
    entry_price: float,
    exit_price: float,
    qty: float,
    multiplier: float = 1.0,
    fees_usd: float = 0.0,
) -> float:
    """Long-only realized PnL (equity shares or option contracts).

    Options: pass premium as price and multiplier=100 (US equity options).
    Shorts are out of scope for v0 — plant computes and passes realized_pnl_usd.
    """
    return (float(exit_price) - float(entry_price)) * float(qty) * float(multiplier) - float(
        fees_usd
    )


@dataclass
class GenomeLesson:
    id: str
    source: str  # broker | auto_estimate | axti | dens | l2 | moss | paper | manual
    symbol: str
    rail: str
    outcome: str  # win | loss | scratch | blocked
    realized_pnl_usd: float
    thesis: str
    lesson: str
    tags: list[str] = field(default_factory=list)
    closed_at: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def lesson_from_closed_trade(
    *,
    trade_id: str,
    symbol: str,
    rail: str,
    realized_pnl_usd: float,
    thesis: str = "",
    tags: Iterable[str] | None = None,
    source: str = SOURCE_MANUAL,
    meta: Mapping[str, Any] | None = None,
) -> GenomeLesson:
    src = (source or SOURCE_MANUAL).strip().lower()
    if src not in KNOWN_SOURCES:
        # Allow plant experiment tags without hard-failing learning path
        src = source or SOURCE_MANUAL
    if realized_pnl_usd > 1e-9:
        outcome = "win"
        lesson = "positive expectancy sample — reinforce setup conditions"
    elif realized_pnl_usd < -1e-9:
        outcome = "loss"
        lesson = "negative sample — tighten entry, dens, or size"
    else:
        outcome = "scratch"
        lesson = "flat — treat as data, not signal"
    return GenomeLesson(
        id=f"lesson-{trade_id}",
        source=src,
        symbol=symbol.upper(),
        rail=rail,
        outcome=outcome,
        realized_pnl_usd=float(realized_pnl_usd),
        thesis=thesis,
        lesson=lesson,
        tags=list(tags or []),
        closed_at=_utc_now(),
        meta=dict(meta or {}),
    )


@dataclass
class LessonBook:
    lessons: list[GenomeLesson] = field(default_factory=list)

    @property
    def wins(self) -> int:
        return sum(1 for x in self.lessons if x.outcome == "win")

    @property
    def losses(self) -> int:
        return sum(1 for x in self.lessons if x.outcome == "loss")

    @property
    def blocked(self) -> int:
        return sum(1 for x in self.lessons if x.outcome == "blocked")

    def append(self, lesson: GenomeLesson) -> None:
        """Append, or supersede auto_estimate when a broker row shares the same id."""
        if lesson.source == SOURCE_BROKER:
            for i, existing in enumerate(self.lessons):
                if existing.id == lesson.id and existing.source == SOURCE_AUTO_ESTIMATE:
                    self.lessons[i] = lesson
                    return
        self.lessons.append(lesson)

    def seed_axti_and_dens(self) -> None:
        """Seed from documented 2026-08-05 AXTI win + dens permanent lessons."""
        if any(x.id == "lesson-axti-2026-08" for x in self.lessons):
            return
        self.append(
            GenomeLesson(
                id="lesson-axti-2026-08",
                source=SOURCE_AXTI,
                symbol="AXTI",
                rail="rh_agentic",
                outcome="win",
                realized_pnl_usd=175.0,
                thesis="Defined-risk short-dated calls into catalyst; scale out on gamma",
                lesson="Repeat: defined-risk options, half at ~2×, SL −40%, never hold to worthless",
                tags=["axti", "options-first", "scale-out"],
                closed_at="2026-08-04T00:00:00Z",
            )
        )
        self.append(
            GenomeLesson(
                id="lesson-dens-sonny-bingbong",
                source=SOURCE_DENS,
                symbol="SONNY",
                rail="rh_l2",
                outcome="blocked",
                realized_pnl_usd=0.0,
                thesis="Honeypot dens class",
                lesson="Permanent dens SONNY/BINGBONG class + short 0x prefixes — never re-enable free-reign spam",
                tags=["dens", "permanent"],
                closed_at="2026-08-05T00:00:00Z",
            )
        )

    def summary(self) -> dict[str, Any]:
        return {
            "count": len(self.lessons),
            "wins": self.wins,
            "losses": self.losses,
            "blocked": self.blocked,
            "realized_pnl_usd": sum(x.realized_pnl_usd for x in self.lessons),
            "by_source": _count_by_source(self.lessons),
        }

    def as_dict(self) -> dict[str, Any]:
        return {"lessons": [x.as_dict() for x in self.lessons], "summary": self.summary()}

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.as_dict(), indent=2) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "LessonBook":
        if not path.is_file():
            return cls()
        raw = json.loads(path.read_text(encoding="utf-8"))
        lessons = [GenomeLesson(**item) for item in raw.get("lessons", [])]
        return cls(lessons=lessons)


def _count_by_source(lessons: list[GenomeLesson]) -> dict[str, int]:
    out: dict[str, int] = {}
    for x in lessons:
        out[x.source] = out.get(x.source, 0) + 1
    return out
