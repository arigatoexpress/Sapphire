"""Pure quality and sanitization heuristics for Telegram intel messages."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from services.telegram_intel.models import MAX_MESSAGE_CHARS, TRUNCATION_SUFFIX

URL_RE = re.compile(r"\bhttps?://[^\s<>()]+", re.I)
WWW_RE = re.compile(r"(?<![/\w])www\.[^\s<>()]+", re.I)
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
PHONE_RE = re.compile(r"(?<!\d)(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}(?!\d)")
HANDLE_RE = re.compile(r"(?<![\w/])@[A-Za-z0-9_]{5,}\b")
WALLET_RE = re.compile(r"\b(?:0x[a-fA-F0-9]{40}|[13][a-km-zA-HJ-NP-Z1-9]{25,34})\b")
WHITESPACE_RE = re.compile(r"\s+")

SPAM_PATTERNS = (
    re.compile(r"\b(?:airdrop|giveaway|free\s+tokens?|claim\s+now|limited\s+spots)\b", re.I),
    re.compile(r"\b(?:dm\s+for|contact\s+admin|promo|paid\s+post|sponsored\s+slot)\b", re.I),
    re.compile(r"\b(?:casino|jackpot|binary\s+options|guaranteed\s+profit)\b", re.I),
    re.compile(r"\b(?:seed\s+phrase|private\s+key|wallet\s+drain|connect\s+wallet)\b", re.I),
)

LOW_INFO_PATTERNS = (
    re.compile(r"^(?:gm|gn|hello|hi|test|ok|yes|no|thanks|lol)[.! ]*$", re.I),
    re.compile(r"^(?:forwarded|photo|video|sticker)$", re.I),
)

TAG_TERMS = {
    "security": (
        "cve",
        "exploit",
        "breach",
        "ransomware",
        "malware",
        "zero-day",
        "vulnerability",
        "ioc",
    ),
    "markets": (
        "btc",
        "eth",
        "funding",
        "liquidity",
        "market",
        "yield",
        "treasury",
        "inflation",
    ),
    "ai": ("ai", "model", "llm", "agent", "inference", "gpu", "training"),
    "policy": ("sec", "fed", "court", "regulation", "sanction", "lawmakers", "policy"),
    "infra": ("outage", "cloud", "dns", "kubernetes", "postgres", "latency", "incident"),
    "onchain": ("wallet", "bridge", "token", "defi", "chain", "validator", "smart contract"),
}

ACTION_TERMS = (
    "confirmed",
    "released",
    "patched",
    "detected",
    "published",
    "announced",
    "investigating",
    "monitor",
    "watch",
    "mitigation",
)


@dataclass(frozen=True)
class QualityDecision:
    keep: bool
    score: float
    reasons: tuple[str, ...]
    tags: tuple[str, ...]
    sanitized_text: str

    def with_score(self, score: float, *, keep: bool, reason: str) -> QualityDecision:
        reasons = tuple(dict.fromkeys((*self.reasons, reason)))
        return QualityDecision(
            keep=keep,
            score=max(0.0, min(1.0, score)),
            reasons=reasons,
            tags=self.tags,
            sanitized_text=self.sanitized_text,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "keep": self.keep,
            "score": round(float(self.score), 4),
            "reasons": list(self.reasons),
            "tags": list(self.tags),
        }


def normalize_text(text: str | None) -> str:
    cleaned = (text or "").replace("\x00", " ").strip()
    return WHITESPACE_RE.sub(" ", cleaned)


def defang_urls(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        value = match.group(0)
        if value.lower().startswith("https://"):
            return "hxxps://" + value[8:]
        if value.lower().startswith("http://"):
            return "hxxp://" + value[7:]
        return value

    text = URL_RE.sub(repl, text)
    return WWW_RE.sub(lambda match: "hxxp://" + match.group(0), text)


def redact_pii(text: str) -> str:
    redacted = EMAIL_RE.sub("[redacted-email]", text)
    redacted = WALLET_RE.sub("[redacted-wallet]", redacted)
    redacted = PHONE_RE.sub("[redacted-phone]", redacted)
    return HANDLE_RE.sub("[redacted-handle]", redacted)


def truncate_text(text: str, *, max_chars: int = MAX_MESSAGE_CHARS) -> str:
    if len(text) <= max_chars:
        return text
    keep = max(0, max_chars - len(TRUNCATION_SUFFIX))
    return text[:keep].rstrip() + TRUNCATION_SUFFIX


def sanitize_text(text: str | None) -> str:
    normalized = normalize_text(text)
    defanged = defang_urls(normalized)
    redacted = redact_pii(defanged)
    return truncate_text(redacted)


def infer_tags(text: str) -> tuple[str, ...]:
    lowered = text.lower()
    tags: list[str] = []
    for tag, terms in TAG_TERMS.items():
        if any(term in lowered for term in terms):
            tags.append(tag)
    return tuple(tags)


def _emoji_ratio(text: str) -> float:
    if not text:
        return 0.0
    high = sum(1 for char in text if ord(char) > 10000)
    return high / max(1, len(text))


def _repetition_penalty(text: str) -> bool:
    words = re.findall(r"\b\w+\b", text.lower())
    if len(words) < 8:
        return False
    unique_ratio = len(set(words)) / len(words)
    return unique_ratio < 0.35


def quality_filter(
    text: str | None,
    *,
    channel_id: str | None = None,
    min_score: float = 0.45,
    min_message_length: int = 32,
    score_multiplier: float = 1.0,
) -> QualityDecision:
    sanitized = sanitize_text(text)
    lowered = sanitized.lower()
    reasons: list[str] = []
    score = 0.16

    if not sanitized:
        return QualityDecision(False, 0.0, ("empty",), (), "")

    if any(pattern.search(sanitized) for pattern in LOW_INFO_PATTERNS):
        return QualityDecision(False, 0.05, ("low-information",), (), sanitized)

    hard_spam = [pattern.pattern for pattern in SPAM_PATTERNS if pattern.search(sanitized)]
    if hard_spam:
        reasons.append("spam-pattern")
        score -= 0.5

    length = len(sanitized)
    if length < max(1, int(min_message_length)):
        reasons.append("short")
        score -= 0.12
    elif length >= 50:
        score += 0.07
        reasons.append("useful-length")
    if length >= 80:
        score += 0.16
        reasons.append("substantive-length")
    if length >= 240:
        score += 0.08
        reasons.append("context-rich")
    if length >= 700:
        score += 0.04
        reasons.append("longform")

    tags = infer_tags(sanitized)
    if tags:
        score += min(0.40, 0.20 * len(tags))
        reasons.append("domain-signal")

    if re.search(
        r"(?:\bCVE-\d{4}-\d{4,7}\b|\b[A-Z]{2,6}/USD\b|[$][A-Z]{2,6}\b|\b\d+(?:\.\d+)?%|\b\d+(?:\.\d+)?(?:ms|s|gb|mb|bps)\b)",
        sanitized,
    ):
        score += 0.08
        reasons.append("specific-indicator")

    if URL_RE.search(text or "") or WWW_RE.search(text or ""):
        score += 0.05
        reasons.append("source-link")

    if any(term in lowered for term in ACTION_TERMS):
        score += 0.08
        reasons.append("actionable-language")

    if channel_id:
        score += 0.03
        reasons.append("attributed-channel")

    letters = [char for char in sanitized if char.isalpha()]
    if letters:
        upper_ratio = sum(1 for char in letters if char.isupper()) / len(letters)
        if upper_ratio > 0.65 and len(letters) > 20:
            score -= 0.12
            reasons.append("shouty")

    if _emoji_ratio(sanitized) > 0.08:
        score -= 0.12
        reasons.append("emoji-heavy")

    if _repetition_penalty(sanitized):
        score -= 0.18
        reasons.append("repetitive")

    if "forwarded from" in lowered and length < 120:
        score -= 0.08
        reasons.append("thin-forward")

    multiplier = max(0.1, min(3.0, float(score_multiplier)))
    if multiplier != 1.0:
        score *= multiplier
        reasons.append("channel-weight")
    score = max(0.0, min(1.0, score))
    keep = score >= min_score and "spam-pattern" not in reasons
    if keep:
        reasons.append("kept")
    else:
        reasons.append("filtered")
    return QualityDecision(keep, score, tuple(dict.fromkeys(reasons)), tags, sanitized)
