"""Anti-slop quality filter.

Rejects content that:
  1. Contains more than MAX_BANNED of the BANNED_PHRASES.
  2. Has fewer than MIN_NUMBERS specific numeric claims (a proxy for
     data density — if a post has no numbers it's almost always generic).
  3. Scores poorly on a crude readability check.

The goal is not beautiful prose; it's truthful, specific, scannable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

BANNED_PHRASES: tuple[str, ...] = (
    "in today's rapidly evolving",
    "it's worth noting",
    "let's dive in",
    "buckle up",
    "game-changer",
    "paradigm shift",
    "deep dive",
    "unpack",
    "robust",
    "seamless",
    "cutting-edge",
    "revolutionary",
)

MAX_BANNED = 2
MIN_NUMBERS = 3
MIN_WORDS = 30
MAX_AVG_SENTENCE_WORDS = 35  # >35 is typically runaway


_NUM_RE = re.compile(r"(?<!\w)(\$?\-?\d[\d,]*(?:\.\d+)?%?)")
_SENT_SPLIT_RE = re.compile(r"[.!?]+\s+")


@dataclass
class QualityReport:
    passed: bool
    banned_hits: list[str] = field(default_factory=list)
    number_count: int = 0
    word_count: int = 0
    avg_sentence_words: float = 0.0
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "banned_hits": self.banned_hits,
            "number_count": self.number_count,
            "word_count": self.word_count,
            "avg_sentence_words": self.avg_sentence_words,
            "reasons": self.reasons,
        }


def count_banned(text: str, phrases: tuple[str, ...] = BANNED_PHRASES) -> list[str]:
    lower = text.lower()
    return [p for p in phrases if p in lower]


def count_numbers(text: str) -> int:
    return len(_NUM_RE.findall(text))


def readability(text: str) -> tuple[int, float]:
    words = text.split()
    sents = [s for s in _SENT_SPLIT_RE.split(text) if s.strip()]
    avg = (len(words) / len(sents)) if sents else float(len(words))
    return len(words), round(avg, 2)


def check(text: str) -> QualityReport:
    """Run all checks and return a structured report."""
    hits = count_banned(text)
    nums = count_numbers(text)
    words, avg_sent = readability(text)

    reasons: list[str] = []
    if len(hits) > MAX_BANNED:
        reasons.append(f"too_many_banned_phrases ({len(hits)}>{MAX_BANNED}): {hits}")
    if nums < MIN_NUMBERS:
        reasons.append(f"data_density_low ({nums}<{MIN_NUMBERS} numbers)")
    if words < MIN_WORDS:
        reasons.append(f"too_short ({words}<{MIN_WORDS} words)")
    if avg_sent > MAX_AVG_SENTENCE_WORDS:
        reasons.append(f"sentences_too_long ({avg_sent}>{MAX_AVG_SENTENCE_WORDS})")

    return QualityReport(
        passed=not reasons,
        banned_hits=hits,
        number_count=nums,
        word_count=words,
        avg_sentence_words=avg_sent,
        reasons=reasons,
    )
