"""Heuristic classifier for official macro/regulatory events."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from lib.macro.sources import MacroEvent

CATEGORIES = (
    "monetary_policy",
    "regulatory_enforcement",
    "data_release",
    "treasury_auction",
    "international",
    "other",
)
SEVERITIES = ("low", "medium", "high", "extreme")
DIRECTIONS = ("hawkish", "dovish", "neutral", "mixed")

SOURCE_CATEGORY_HINTS: dict[str, str] = {
    "fed_rss": "monetary_policy",
    "fed_fomc": "monetary_policy",
    "cftc_rss": "regulatory_enforcement",
    "sec_atom": "regulatory_enforcement",
    "treasury_auctions": "treasury_auction",
    "bls_empsit_rss": "data_release",
    "ecb_rss": "international",
    "bis_rss": "international",
}

CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "monetary_policy": (
        "fomc",
        "federal open market",
        "interest rate",
        "rate decision",
        "monetary policy",
        "minutes",
        "dot plot",
        "fed funds",
        "quantitative tightening",
    ),
    "regulatory_enforcement": (
        "charges",
        "charged",
        "enforcement",
        "settlement",
        "fraud",
        "lawsuit",
        "cease-and-desist",
        "civil monetary penalty",
        "unregistered",
        "market manipulation",
    ),
    "data_release": (
        "employment situation",
        "nonfarm payroll",
        "payrolls",
        "unemployment",
        "cpi",
        "inflation",
        "consumer price",
        "producer price",
        "jobs",
        "wages",
    ),
    "treasury_auction": (
        "treasury auction",
        "auction",
        "bill",
        "note",
        "bond",
        "cusip",
        "high yield",
        "bid-to-cover",
    ),
    "international": (
        "european central bank",
        "ecb",
        "bis",
        "bank for international settlements",
        "euro area",
        "basel",
        "fx",
        "foreign exchange",
    ),
}

ASSET_KEYWORDS: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (("bitcoin", "btc", "crypto", "digital asset", "coinbase", "binance"), ("BTC", "ETH", "SOL")),
    (("ether", "ethereum", "eth"), ("ETH",)),
    (("solana", "sol"), ("SOL",)),
    (("equity", "stock", "s&p", "nasdaq", "jobs", "payroll", "growth"), ("equities",)),
    (("treasury", "yield", "auction", "note", "bond", "bill"), ("USD", "bonds", "gold", "BTC")),
    (("dollar", "usd", "fed", "fomc", "inflation", "rates"), ("USD", "gold", "BTC", "ETH", "SOL")),
    (("euro", "ecb", "european central bank", "euro area"), ("EUR", "USD", "equities")),
    (("gold", "precious metal"), ("gold",)),
)

HAWKISH_KEYWORDS = (
    "hike",
    "raises rates",
    "raised rates",
    "tightening",
    "restrictive",
    "higher for longer",
    "inflation remains elevated",
    "hotter than expected",
    "strong payroll",
    "weak demand",
    "high yield",
    "enforcement",
    "charges",
    "charged",
    "penalty",
    "ban",
)
DOVISH_KEYWORDS = (
    "cut",
    "cuts rates",
    "lower rates",
    "pause",
    "holds rates",
    "held rates",
    "hold rates",
    "unchanged",
    "easing",
    "accommodative",
    "cooling inflation",
    "weaker payroll",
    "rising unemployment",
    "strong demand",
    "approval",
    "exemption",
)
MIXED_KEYWORDS = ("mixed", "balanced", "two-sided", "uncertain", "split decision")

EXTREME_KEYWORDS = (
    "emergency",
    "crisis",
    "surprise",
    "75 basis",
    "100 basis",
    "systemic",
    "major exchange",
    "binance",
    "coinbase",
    "bank failure",
    "sanctions",
    "ban",
)
HIGH_KEYWORDS = (
    "fomc",
    "rate decision",
    "payroll",
    "employment situation",
    "cpi",
    "inflation",
    "enforcement",
    "charges",
    "settlement",
    "10-year",
    "30-year",
    "ecb monetary policy",
)
MEDIUM_KEYWORDS = (
    "minutes",
    "speech",
    "auction",
    "note",
    "bond",
    "bis",
    "ecb",
    "treasury",
    "guidance",
)


@dataclass(frozen=True)
class MacroClassification:
    category: str
    assets_likely_affected: tuple[str, ...]
    expected_impact_severity: str
    direction_hint: str
    confidence: float
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "assets_likely_affected": list(self.assets_likely_affected),
            "expected_impact_severity": self.expected_impact_severity,
            "direction_hint": self.direction_hint,
            "confidence": self.confidence,
            "reasons": list(self.reasons),
        }


def _material(event: MacroEvent) -> str:
    return " ".join(
        [
            event.source,
            event.title,
            event.summary,
            str(event.metadata.get("source_name") or ""),
            str(event.metadata.get("event_kind") or ""),
        ]
    ).lower()


def _contains_any(material: str, keywords: tuple[str, ...]) -> list[str]:
    hits: list[str] = []
    for keyword in keywords:
        if keyword in material:
            hits.append(keyword)
    return hits


def _category(event: MacroEvent, material: str) -> tuple[str, list[str]]:
    scores: dict[str, int] = {category: 0 for category in CATEGORIES}
    reasons: list[str] = []
    hinted = SOURCE_CATEGORY_HINTS.get(event.source)
    if hinted:
        scores[hinted] += 3
        reasons.append(f"source:{event.source}->{hinted}")
    for category, keywords in CATEGORY_KEYWORDS.items():
        hits = _contains_any(material, keywords)
        if hits:
            scores[category] += len(hits) * 2
            reasons.append(f"{category}:{','.join(hits[:3])}")
    best = max(scores, key=scores.get)
    if scores[best] <= 0:
        return "other", reasons or ["no category keyword match"]
    return best, reasons


def _assets(material: str, category: str) -> tuple[str, ...]:
    assets: list[str] = []
    for keywords, values in ASSET_KEYWORDS:
        if _contains_any(material, keywords):
            for asset in values:
                if asset not in assets:
                    assets.append(asset)
    if not assets:
        defaults = {
            "monetary_policy": ["BTC", "ETH", "SOL", "equities", "gold", "USD"],
            "regulatory_enforcement": ["BTC", "ETH", "SOL", "equities"],
            "data_release": ["equities", "USD", "gold", "BTC"],
            "treasury_auction": ["USD", "bonds", "gold", "BTC"],
            "international": ["EUR", "USD", "equities", "BTC"],
            "other": ["equities"],
        }
        assets = defaults[category]
    return tuple(assets)


def _severity(material: str, category: str) -> tuple[str, list[str]]:
    extreme_hits = _contains_any(material, EXTREME_KEYWORDS)
    if extreme_hits:
        return "extreme", [f"severity:extreme:{','.join(extreme_hits[:3])}"]
    high_hits = _contains_any(material, HIGH_KEYWORDS)
    if high_hits:
        return "high", [f"severity:high:{','.join(high_hits[:3])}"]
    medium_hits = _contains_any(material, MEDIUM_KEYWORDS)
    if medium_hits or category in {"monetary_policy", "regulatory_enforcement", "data_release"}:
        reason = ",".join(medium_hits[:3]) if medium_hits else category
        return "medium", [f"severity:medium:{reason}"]
    return "low", ["severity:low:weak macro keyword density"]


def _direction(material: str) -> tuple[str, list[str]]:
    mixed_hits = _contains_any(material, MIXED_KEYWORDS)
    hawkish_hits = _contains_any(material, HAWKISH_KEYWORDS)
    dovish_hits = _contains_any(material, DOVISH_KEYWORDS)
    if mixed_hits or (hawkish_hits and dovish_hits):
        return "mixed", [
            f"direction:mixed:{','.join((mixed_hits + hawkish_hits + dovish_hits)[:4])}"
        ]
    if hawkish_hits:
        return "hawkish", [f"direction:hawkish:{','.join(hawkish_hits[:3])}"]
    if dovish_hits:
        return "dovish", [f"direction:dovish:{','.join(dovish_hits[:3])}"]
    return "neutral", ["direction:neutral:no directional keyword"]


def _confidence(category: str, severity: str, direction: str, reasons: list[str]) -> float:
    score = 0.35
    if category != "other":
        score += 0.2
    if severity in {"high", "extreme"}:
        score += 0.15
    elif severity == "medium":
        score += 0.08
    if direction != "neutral":
        score += 0.1
    score += min(0.2, len(reasons) * 0.025)
    return round(min(score, 0.95), 3)


def classify_event(event: MacroEvent) -> MacroClassification:
    """Classify an official event with a deterministic threshold table."""

    material = _material(event)
    category, category_reasons = _category(event, material)
    severity, severity_reasons = _severity(material, category)
    direction, direction_reasons = _direction(material)
    reasons = [*category_reasons, *severity_reasons, *direction_reasons]
    return MacroClassification(
        category=category,
        assets_likely_affected=_assets(material, category),
        expected_impact_severity=severity,
        direction_hint=direction,
        confidence=_confidence(category, severity, direction, reasons),
        reasons=tuple(reasons),
    )


def enrich_event(event: MacroEvent) -> dict[str, Any]:
    payload = event.to_dict()
    payload["classification"] = classify_event(event).to_dict()
    return payload


def classify_event_dict(payload: dict[str, Any]) -> dict[str, Any]:
    return enrich_event(MacroEvent.from_dict(payload))


def redacted_text_for_logs(event: MacroEvent) -> str:
    """Small helper for operators; avoids leaking oversized feed bodies."""

    text = re.sub(r"\s+", " ", f"{event.source} {event.title}").strip()
    return text[:240]


__all__ = [
    "CATEGORIES",
    "DIRECTIONS",
    "SEVERITIES",
    "MacroClassification",
    "classify_event",
    "classify_event_dict",
    "enrich_event",
    "redacted_text_for_logs",
]
