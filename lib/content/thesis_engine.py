"""Investment thesis engine — synthesises a market narrative from live data.

Generates a short structured thesis (bull / bear / neutral) for each tracked
asset based on:
  - 6-factor TA prediction direction
  - Chain regime (RISK_ON / RISK_OFF / NEUTRAL)
  - VPIN microstructure signal
  - Cross-sectional factor scores

The output is a ``Thesis`` dataclass consumed by the draft generator and
content formatters.  The engine is fully deterministic (no LLM calls) — it
maps signal combinations to canned thesis templates.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

log = logging.getLogger(__name__)


@dataclass
class Thesis:
    asset: str
    stance: str  # "bull" | "bear" | "neutral"
    confidence: float  # 0-1
    headline: str
    supporting: list[str]
    against: list[str]
    generated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset": self.asset,
            "stance": self.stance,
            "confidence": self.confidence,
            "headline": self.headline,
            "supporting": self.supporting,
            "against": self.against,
            "generated_at": self.generated_at,
        }


_BULL_TEMPLATES = [
    "{asset} showing strength: {supporting[0]}.",
    "{asset} bias bullish — {supporting[0]} supports continuation.",
]
_BEAR_TEMPLATES = [
    "{asset} under pressure: {supporting[0]}.",
    "{asset} bearish — {supporting[0]} signals downside.",
]
_NEUTRAL_TEMPLATES = [
    "{asset} range-bound: {supporting[0]}.",
    "{asset} mixed signals — {supporting[0]}.",
]


def _pick_headline(stance: str, asset: str, supporting: list[str]) -> str:
    ctx = {"asset": asset, "supporting": supporting or ["no clear signal"]}
    if stance == "bull":
        return _BULL_TEMPLATES[0].format(**ctx)
    if stance == "bear":
        return _BEAR_TEMPLATES[0].format(**ctx)
    return _NEUTRAL_TEMPLATES[0].format(**ctx)


class ThesisEngine:
    """Synthesise asset theses from Sapphire prediction + chain data."""

    def generate(
        self,
        asset: str,
        prediction: dict[str, Any] | None = None,
        regime: str | None = None,
        factor_score: float | None = None,
    ) -> Thesis:
        bull_reasons: list[str] = []
        bear_reasons: list[str] = []
        neutral_reasons: list[str] = []
        bull_votes = 0
        bear_votes = 0

        direction = (prediction or {}).get("direction", "neutral")
        if direction in ("bullish", "strong_bullish"):
            bull_votes += 2
            bull_reasons.append(f"TA model: {direction}")
        elif direction in ("bearish", "strong_bearish"):
            bear_votes += 2
            bear_reasons.append(f"TA model: {direction}")
        else:
            neutral_reasons.append("TA model: neutral")

        if regime == "RISK_ON":
            bull_votes += 1
            bull_reasons.append("chain regime: RISK_ON")
        elif regime == "RISK_OFF":
            bear_votes += 1
            bear_reasons.append("chain regime: RISK_OFF")

        if factor_score is not None:
            if factor_score > 0.3:
                bull_votes += 1
                bull_reasons.append(f"factor score: {factor_score:+.2f}")
            elif factor_score < -0.3:
                bear_votes += 1
                bear_reasons.append(f"factor score: {factor_score:+.2f}")

        total = bull_votes + bear_votes or 1
        if bull_votes > bear_votes:
            stance = "bull"
            confidence = round(bull_votes / total, 2)
            supporting = bull_reasons or neutral_reasons
            against = bear_reasons
        elif bear_votes > bull_votes:
            stance = "bear"
            confidence = round(bear_votes / total, 2)
            supporting = bear_reasons or neutral_reasons
            against = bull_reasons
        else:
            stance = "neutral"
            confidence = 0.5
            supporting = neutral_reasons or ["mixed bullish/bearish evidence"]
            against = bull_reasons + bear_reasons

        headline = _pick_headline(stance, asset, supporting)
        return Thesis(
            asset=asset,
            stance=stance,
            confidence=confidence,
            headline=headline,
            supporting=supporting,
            against=against,
        )

    def generate_all(
        self,
        assets: list[str],
        predictions: list[dict] | None = None,
        regime: str | None = None,
    ) -> list[Thesis]:
        pred_map: dict[str, dict] = {}
        for p in predictions or []:
            sym = p.get("symbol", "")
            if sym not in pred_map:
                pred_map[sym] = p
        return [self.generate(a, pred_map.get(a), regime) for a in assets]
