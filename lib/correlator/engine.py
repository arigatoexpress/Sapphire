"""Pure correlation engine for cross-source signal fusion.

This module is the *core* of the signal correlator. It contains:

- :class:`CorrelatedSignal` — the unified, provenance-stamped output.
- :class:`CorrelatorConfig` — engine knobs (caps, weights, thresholds).
- :func:`correlate_once` — fuse a single ``(symbol, timeframe)`` from a
  dict of ``{source_name: SourceSignal}``.
- :func:`correlate_universe` — orchestrate adapters across a configured
  universe of pairs.

The engine is a *read-only signal consumer*: it never writes to source
streams, never mutates upstream files, and never emits an event itself
(the daemon at ``services/correlator/run.py`` does that). Its single
job is to take what's on disk, score it, and return a typed payload.

Caps
----

- ``MAX_SOURCES_PER_CORRELATION = 16`` — cap on per-correlation source
  fan-in. Excess sources are dropped (lowest-weight first).
- ``MAX_CORRELATIONS_PER_HOUR = 1200`` — emitter-side; enforced by the
  service runner, not the engine.
- ``FRESHNESS_HARD_LIMIT_SECONDS = 86400`` — sources older than 24h are
  treated as missing data, never as a stale-bear signal.
- ``EDGE_SCORE_BOUND = (-1.0, +1.0)`` — clamped at the output boundary.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from lib.correlator.scoring import (
    ComposedScore,
    ScoringWeights,
    compose_score,
    normalize_direction,
)
from lib.correlator.sources import SignalSource, SourceSignal

log = logging.getLogger(__name__)

# Hard caps — exposed for documentation & test assertions. The engine
# enforces these regardless of config to prevent runaway fan-in.
MAX_SOURCES_PER_CORRELATION = 16
MAX_CORRELATIONS_PER_HOUR = 1200
FRESHNESS_HARD_LIMIT_SECONDS = 86_400
EDGE_SCORE_BOUND: tuple[float, float] = (-1.0, +1.0)

CONSENSUS_LABELS: tuple[str, ...] = (
    "AGREE_BULL",
    "AGREE_BEAR",
    "PARTIAL_BULL",
    "PARTIAL_BEAR",
    "CONTRADICT",
    "NEUTRAL",
    "INSUFFICIENT_DATA",
)


@dataclass(frozen=True)
class CorrelatedSignal:
    """Unified cross-source signal payload."""

    symbol: str
    timeframe: str
    edge_score: float
    consensus: str
    corroborated_by: tuple[str, ...]
    divergent_sources: tuple[str, ...]
    bull_sources: tuple[str, ...]
    bear_sources: tuple[str, ...]
    neutral_sources: tuple[str, ...]
    freshness_seconds: float
    contributing: int
    raw_score: float
    agreement_multiplier: float
    contradict_factor: float
    total_weight: float
    generated_at: str
    provenance_envelope: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CorrelatorConfig:
    """Engine configuration. ``weights`` is the central knob."""

    weights: ScoringWeights = field(default_factory=ScoringWeights)
    max_sources: int = MAX_SOURCES_PER_CORRELATION
    freshness_hard_limit_seconds: float = FRESHNESS_HARD_LIMIT_SECONDS

    def with_weights(self, weights: ScoringWeights) -> CorrelatorConfig:
        return CorrelatorConfig(
            weights=weights,
            max_sources=self.max_sources,
            freshness_hard_limit_seconds=self.freshness_hard_limit_seconds,
        )


def _filter_fresh(
    signals_by_source: dict[str, SourceSignal | dict[str, Any]],
    *,
    hard_limit: float,
) -> dict[str, dict[str, Any]]:
    """Return only fresh signals as dicts, dropping stale entries silently."""
    out: dict[str, dict[str, Any]] = {}
    for name, sig in signals_by_source.items():
        if sig is None:
            continue
        as_dict: dict[str, Any] = sig.to_dict() if hasattr(sig, "to_dict") else dict(sig)
        try:
            age = float(as_dict.get("age_seconds", 0.0) or 0.0)
        except (TypeError, ValueError):
            age = 0.0
        if age < 0:
            age = 0.0
        if age > hard_limit:
            log.debug("dropping stale source %s (age=%.0fs > %.0fs)", name, age, hard_limit)
            continue
        as_dict["age_seconds"] = age
        out[name] = as_dict
    return out


def _cap_fan_in(
    signals: dict[str, dict[str, Any]],
    *,
    weights: ScoringWeights,
    max_sources: int,
) -> dict[str, dict[str, Any]]:
    """Drop the lowest-weight sources to honour MAX_SOURCES_PER_CORRELATION."""
    if len(signals) <= max_sources:
        return signals
    ranked = sorted(signals.items(), key=lambda kv: weights.weight_for(kv[0]), reverse=True)
    return dict(ranked[:max_sources])


def _consensus_label(score: ComposedScore) -> str:
    if score.bull_count == 0 and score.bear_count == 0:
        if score.neutral_count == 0:
            return "INSUFFICIENT_DATA"
        return "NEUTRAL"
    if score.bull_count > 0 and score.bear_count > 0:
        return "CONTRADICT"
    if score.bull_count >= 2 and score.bear_count == 0:
        return "AGREE_BULL"
    if score.bear_count >= 2 and score.bull_count == 0:
        return "AGREE_BEAR"
    if score.bull_count == 1 and score.bear_count == 0:
        return "PARTIAL_BULL"
    if score.bear_count == 1 and score.bull_count == 0:
        return "PARTIAL_BEAR"
    return "NEUTRAL"  # defensive default


def _split_directions(
    signals: dict[str, dict[str, Any]],
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    bulls: list[str] = []
    bears: list[str] = []
    neutrals: list[str] = []
    for name, sig in signals.items():
        d = normalize_direction(sig.get("direction"))
        if d > 0:
            bulls.append(name)
        elif d < 0:
            bears.append(name)
        else:
            neutrals.append(name)
    return tuple(sorted(bulls)), tuple(sorted(bears)), tuple(sorted(neutrals))


def _provenance_envelope(
    *,
    symbol: str,
    timeframe: str,
    contributing_sources: Sequence[str],
    weights: ScoringWeights,
    generated_at: str,
) -> dict[str, Any]:
    """Lightweight inline envelope (the service writer wraps with the
    canonical ``lib/core/provenance.py`` stamp on disk).
    """
    return {
        "generator": "lib.correlator.engine",
        "version": "0.1.0",
        "symbol": symbol,
        "timeframe": timeframe,
        "sources": list(contributing_sources),
        "weights_signature": _weights_signature(weights),
        "generated_at": generated_at,
    }


def _weights_signature(weights: ScoringWeights) -> dict[str, Any]:
    """Compact reproducible signature of the scoring config."""
    return {
        "source_weights": {k: float(v) for k, v in sorted(weights.source_weights.items())},
        "freshness_half_life_seconds": float(weights.freshness_half_life_seconds),
        "agreement_bonus_per_extra": float(weights.agreement_bonus_per_extra),
        "max_agreement_multiplier": float(weights.max_agreement_multiplier),
        "contradict_penalty": float(weights.contradict_penalty),
    }


def _now_iso(now: datetime | None = None) -> str:
    return (now or datetime.now(UTC)).isoformat()


def correlate_once(
    *,
    symbol: str,
    timeframe: str,
    signals_by_source: dict[str, SourceSignal | dict[str, Any]],
    config: CorrelatorConfig | None = None,
    now: datetime | None = None,
) -> CorrelatedSignal:
    """Fuse per-source signals for a single ``(symbol, timeframe)``.

    - Drops sources older than ``FRESHNESS_HARD_LIMIT_SECONDS``.
    - Caps fan-in to ``MAX_SOURCES_PER_CORRELATION``.
    - Returns a :class:`CorrelatedSignal` even when no sources remain
      (consensus = ``INSUFFICIENT_DATA``, edge_score = 0.0).
    """
    config = config or CorrelatorConfig()

    fresh = _filter_fresh(
        signals_by_source,
        hard_limit=config.freshness_hard_limit_seconds,
    )
    capped = _cap_fan_in(fresh, weights=config.weights, max_sources=config.max_sources)
    score = compose_score(capped, config.weights)
    consensus = _consensus_label(score)

    bulls, bears, neutrals = _split_directions(capped)

    # corroborated_by = sources whose direction matches the consensus
    if consensus in {"AGREE_BULL", "PARTIAL_BULL"}:
        corroborated = bulls
        divergent = bears
    elif consensus in {"AGREE_BEAR", "PARTIAL_BEAR"}:
        corroborated = bears
        divergent = bulls
    elif consensus == "CONTRADICT":
        # In a true contradiction, the larger-side sources are corroborating
        # the score sign, the smaller side are divergent.
        if score.edge_score > 0:
            corroborated, divergent = bulls, bears
        elif score.edge_score < 0:
            corroborated, divergent = bears, bulls
        else:
            corroborated, divergent = (), bulls + bears
    else:
        corroborated = ()
        divergent = ()

    if capped:
        freshness = round(min(float(s.get("age_seconds") or 0.0) for s in capped.values()), 3)
    else:
        freshness = 0.0

    generated = _now_iso(now)
    envelope = _provenance_envelope(
        symbol=symbol,
        timeframe=timeframe,
        contributing_sources=tuple(capped.keys()),
        weights=config.weights,
        generated_at=generated,
    )
    edge = max(EDGE_SCORE_BOUND[0], min(EDGE_SCORE_BOUND[1], float(score.edge_score)))
    return CorrelatedSignal(
        symbol=symbol,
        timeframe=timeframe,
        edge_score=round(edge, 6),
        consensus=consensus,
        corroborated_by=tuple(corroborated),
        divergent_sources=tuple(divergent),
        bull_sources=bulls,
        bear_sources=bears,
        neutral_sources=neutrals,
        freshness_seconds=freshness,
        contributing=len(capped),
        raw_score=float(score.raw_score),
        agreement_multiplier=float(score.agreement_multiplier),
        contradict_factor=float(score.contradict_factor),
        total_weight=float(score.total_weight),
        generated_at=generated,
        provenance_envelope=envelope,
    )


@dataclass(frozen=True)
class UniversePair:
    """One ``(symbol, timeframe)`` pair to correlate."""

    symbol: str
    timeframe: str


def correlate_universe(
    pairs: Iterable[UniversePair | tuple[str, str]],
    *,
    sources: Sequence[SignalSource],
    config: CorrelatorConfig | None = None,
    now: datetime | None = None,
) -> list[CorrelatedSignal]:
    """Run :func:`correlate_once` for every pair in ``pairs``.

    Adapters are queried sequentially; any adapter that raises is
    silently dropped from that pair's input dict (logged at WARNING).
    """
    config = config or CorrelatorConfig()
    out: list[CorrelatedSignal] = []
    for raw in pairs:
        if isinstance(raw, UniversePair):
            symbol, timeframe = raw.symbol, raw.timeframe
        else:
            symbol, timeframe = raw[0], raw[1]
        signals: dict[str, SourceSignal | dict[str, Any]] = {}
        for src in sources:
            try:
                sig = src.latest_for(symbol, timeframe)
            except Exception as exc:  # noqa: BLE001 - never bubble adapter errors.
                log.warning("source %s failed for (%s, %s): %s", src.name, symbol, timeframe, exc)
                continue
            if sig is None:
                continue
            signals[src.name] = sig
        out.append(
            correlate_once(
                symbol=symbol,
                timeframe=timeframe,
                signals_by_source=signals,
                config=config,
                now=now,
            )
        )
    return out


__all__ = [
    "CONSENSUS_LABELS",
    "EDGE_SCORE_BOUND",
    "FRESHNESS_HARD_LIMIT_SECONDS",
    "MAX_CORRELATIONS_PER_HOUR",
    "MAX_SOURCES_PER_CORRELATION",
    "CorrelatedSignal",
    "CorrelatorConfig",
    "UniversePair",
    "correlate_once",
    "correlate_universe",
]
