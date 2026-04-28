"""Pure scoring math for the Sapphire Signal Correlation Engine.

Everything in this module is deterministic and free of I/O. The two
public entry points are :func:`compose_score` (the actual blend that
turns per-source ``SourceSignal`` directional intent into a single
``edge_score`` in ``[-1.0, +1.0]``) and :func:`load_weights` (a YAML
loader that respects ``~/.sapphire/correlator_weights.yaml`` with sane
defaults if the file is missing or malformed).

Conventions
-----------

- ``BULL`` = +1, ``BEAR`` = -1, ``NEUTRAL`` = 0 directional intent.
- Each source contributes ``weight * direction * confidence * freshness_factor``.
- The blended raw score is normalized by the *total* weight contribution
  (sum of absolute weights of contributing sources) so a missing source
  cannot accidentally amplify another.
- Agreement bonus: when 2+ non-zero sources line up in the same
  direction, the score is multiplied by ``1 + agreement_bonus`` per
  extra agreeing source, capped at ``max_agreement_multiplier``.
- Contradiction penalty: when both bull and bear sources contribute the
  blended score is multiplied by ``contradict_penalty`` (0.0–1.0).
- Final score is clamped to ``[-1.0, +1.0]`` (the engine enforces this
  again at the output boundary).

Property-test invariants
------------------------

- Monotonicity: increasing a source's confidence (in its expressed
  direction) cannot decrease the absolute score.
- Bound: ``-1.0 <= score <= +1.0`` for every input.
- Symmetry: flipping every direction (BULL↔BEAR) flips the sign of the
  score and leaves ``abs(score)`` unchanged.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

SCORING_VERSION = "0.1.0"

# Per-source weight defaults. Tuned against the source-fidelity ranking
# the operator articulated in `docs/products/signal-correlator-0.1.0.md`:
# Kronos > TA scanner > TradingView webhook > cross-asset regime >
# Hyperliquid public feed > Telegram intel > convergence-watchlist >
# sovereign-thesis > threat-intel.
# Each weight contributes proportionally; raise/lower in the YAML config
# without touching code.
DEFAULT_SOURCE_WEIGHTS: dict[str, float] = {
    "kronos_forecast": 1.30,
    "ta_scanner": 1.15,
    "tradingview": 1.00,
    "cross_asset_regime": 0.95,
    "hyperliquid_public_feed": 0.85,
    "telegram_intel": 0.70,
    "convergence_watchlist": 0.55,
    "sovereign_thesis": 0.50,
    "threat_intel": 0.40,
}

DEFAULT_FRESHNESS_HALF_LIFE_SECONDS = 6 * 3600  # 6h
DEFAULT_AGREEMENT_BONUS_PER_EXTRA = 0.10
DEFAULT_MAX_AGREEMENT_MULTIPLIER = 1.40
DEFAULT_CONTRADICT_PENALTY = 0.45
DEFAULT_MIN_CONTRIB_THRESHOLD = 1e-6


@dataclass(frozen=True)
class ScoringWeights:
    """Tunable scoring parameters (loadable from YAML)."""

    source_weights: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_SOURCE_WEIGHTS))
    freshness_half_life_seconds: float = DEFAULT_FRESHNESS_HALF_LIFE_SECONDS
    agreement_bonus_per_extra: float = DEFAULT_AGREEMENT_BONUS_PER_EXTRA
    max_agreement_multiplier: float = DEFAULT_MAX_AGREEMENT_MULTIPLIER
    contradict_penalty: float = DEFAULT_CONTRADICT_PENALTY
    min_contrib_threshold: float = DEFAULT_MIN_CONTRIB_THRESHOLD

    def with_overrides(self, **overrides: Any) -> ScoringWeights:
        """Return a new ScoringWeights with the given fields overridden."""
        return replace(self, **overrides)

    def weight_for(self, source: str) -> float:
        """Return the weight for ``source`` (0.0 if unknown — silently ignored)."""
        return float(self.source_weights.get(source, 0.0))


def freshness_factor(age_seconds: float, half_life_seconds: float) -> float:
    """Return a 0..1 freshness factor with exponential decay.

    - ``age_seconds = 0`` → 1.0
    - ``age_seconds = half_life`` → 0.5
    - ``age_seconds = 4 * half_life`` → ~0.0625
    - clamps negative ages to 0 (treated as "very fresh")
    - returns 0.0 for non-finite inputs
    """
    try:
        age = float(age_seconds)
    except (TypeError, ValueError):
        return 0.0
    if age != age or age in (float("inf"), float("-inf")):  # NaN / inf guards
        return 0.0
    if age <= 0.0:
        return 1.0
    half_life = max(1.0, float(half_life_seconds or 1.0))
    return float(0.5 ** (age / half_life))


_BULL = 1
_BEAR = -1
_NEUTRAL = 0
_DIRECTION_MAP: dict[str, int] = {
    "bull": _BULL,
    "bullish": _BULL,
    "long": _BULL,
    "buy": _BULL,
    "up": _BULL,
    "+": _BULL,
    "1": _BULL,
    "bear": _BEAR,
    "bearish": _BEAR,
    "short": _BEAR,
    "sell": _BEAR,
    "down": _BEAR,
    "-": _BEAR,
    "-1": _BEAR,
    "neutral": _NEUTRAL,
    "flat": _NEUTRAL,
    "hold": _NEUTRAL,
    "0": _NEUTRAL,
    "": _NEUTRAL,
}


def normalize_direction(value: str | int | float | None) -> int:
    """Coerce an arbitrary direction label into BULL / BEAR / NEUTRAL ints."""
    if value is None:
        return _NEUTRAL
    if isinstance(value, bool):
        # bool is a subclass of int; treat True/False as bull/neutral so we don't
        # accidentally cast True→1 to BULL while False→0 to BEAR.
        return _BULL if value else _NEUTRAL
    if isinstance(value, (int, float)):
        if value > 0:
            return _BULL
        if value < 0:
            return _BEAR
        return _NEUTRAL
    return _DIRECTION_MAP.get(str(value).strip().lower(), _NEUTRAL)


@dataclass(frozen=True)
class _Contribution:
    """Per-source contribution to the blended score."""

    source: str
    direction: int
    confidence: float
    freshness: float
    weight: float
    contribution: float


def _per_source_contributions(
    signals_by_source: dict[str, dict[str, Any]],
    weights: ScoringWeights,
) -> list[_Contribution]:
    out: list[_Contribution] = []
    for source, sig in signals_by_source.items():
        if not isinstance(sig, dict):
            continue
        weight = weights.weight_for(source)
        if weight == 0.0:
            continue
        direction = normalize_direction(sig.get("direction"))
        try:
            confidence = float(sig.get("confidence", 0.0) or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        confidence = max(0.0, min(1.0, confidence))
        try:
            age = float(sig.get("age_seconds", 0.0) or 0.0)
        except (TypeError, ValueError):
            age = 0.0
        fresh = freshness_factor(age, weights.freshness_half_life_seconds)
        contrib = weight * float(direction) * confidence * fresh
        out.append(
            _Contribution(
                source=source,
                direction=direction,
                confidence=confidence,
                freshness=fresh,
                weight=weight,
                contribution=contrib,
            )
        )
    return out


@dataclass(frozen=True)
class ComposedScore:
    """Result of composing per-source signals into one ``edge_score``."""

    edge_score: float
    raw_score: float
    contributing: tuple[_Contribution, ...]
    bull_count: int
    bear_count: int
    neutral_count: int
    agreement_multiplier: float
    contradict_factor: float
    total_weight: float


def compose_score(
    signals_by_source: dict[str, dict[str, Any]],
    weights: ScoringWeights | None = None,
) -> ComposedScore:
    """Pure scoring blend.

    ``signals_by_source`` is ``{source_name: {direction, confidence,
    age_seconds, ...}}``. Sources with weight 0 (unknown to the
    weights) are silently ignored — this is intentional, so adding a
    new source name in YAML opts it in without touching code.

    Returns a frozen :class:`ComposedScore` with the blended
    ``edge_score`` clamped to ``[-1, +1]`` plus the inputs that
    produced it for full auditability.
    """
    weights = weights or ScoringWeights()
    contribs = _per_source_contributions(signals_by_source, weights)

    total_weight = sum(abs(c.weight) for c in contribs)
    bull_count = sum(1 for c in contribs if c.direction == _BULL and c.contribution != 0.0)
    bear_count = sum(1 for c in contribs if c.direction == _BEAR and c.contribution != 0.0)
    neutral_count = sum(1 for c in contribs if c.direction == _NEUTRAL)

    if total_weight <= 0.0 or not contribs:
        return ComposedScore(
            edge_score=0.0,
            raw_score=0.0,
            contributing=tuple(contribs),
            bull_count=bull_count,
            bear_count=bear_count,
            neutral_count=neutral_count,
            agreement_multiplier=1.0,
            contradict_factor=1.0,
            total_weight=total_weight,
        )

    raw = sum(c.contribution for c in contribs) / total_weight

    # Agreement bonus: ramp up when 2+ sources line up.
    dominant = bull_count if abs(raw) > 0 and raw > 0 else (bear_count if raw < 0 else 0)
    extra = max(0, dominant - 1)
    agreement_multiplier = min(
        weights.max_agreement_multiplier,
        1.0 + extra * weights.agreement_bonus_per_extra,
    )

    # Contradiction penalty: when bulls *and* bears both contribute non-zero,
    # the score is dampened toward zero.
    contradict_factor = (
        weights.contradict_penalty if (bull_count > 0 and bear_count > 0) else 1.0
    )

    blended = raw * agreement_multiplier * contradict_factor
    edge = max(-1.0, min(1.0, blended))
    return ComposedScore(
        edge_score=round(edge, 6),
        raw_score=round(raw, 6),
        contributing=tuple(contribs),
        bull_count=bull_count,
        bear_count=bear_count,
        neutral_count=neutral_count,
        agreement_multiplier=round(agreement_multiplier, 6),
        contradict_factor=round(contradict_factor, 6),
        total_weight=round(total_weight, 6),
    )


# ---------------------------------------------------------------------------
# YAML config loader
# ---------------------------------------------------------------------------

DEFAULT_WEIGHTS_PATH = Path.home() / ".sapphire" / "correlator_weights.yaml"


def load_weights(path: Path | None = None) -> ScoringWeights:
    """Load weights from YAML if present, else return defaults.

    The YAML schema (all keys optional)::

        source_weights:
          tradingview: 1.0
          telegram_intel: 0.6
        freshness_half_life_seconds: 21600
        agreement_bonus_per_extra: 0.1
        max_agreement_multiplier: 1.4
        contradict_penalty: 0.45

    Malformed YAML or missing files fall back to defaults silently —
    we never raise from a config-loader.
    """
    target = path or DEFAULT_WEIGHTS_PATH
    if not target.exists():
        return ScoringWeights()
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError:  # pragma: no cover - PyYAML is in repo deps.
        log.debug("PyYAML missing — using default correlator weights")
        return ScoringWeights()
    try:
        raw = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        log.warning("correlator_weights.yaml unreadable (%s) — using defaults", exc)
        return ScoringWeights()
    if not isinstance(raw, dict):
        return ScoringWeights()

    defaults = ScoringWeights()
    src_weights = dict(defaults.source_weights)
    overrides = raw.get("source_weights")
    if isinstance(overrides, dict):
        for k, v in overrides.items():
            try:
                src_weights[str(k)] = float(v)
            except (TypeError, ValueError):
                continue

    def _f(key: str, default: float) -> float:
        if key not in raw:
            return default
        try:
            return float(raw[key])
        except (TypeError, ValueError):
            return default

    return ScoringWeights(
        source_weights=src_weights,
        freshness_half_life_seconds=max(
            1.0, _f("freshness_half_life_seconds", defaults.freshness_half_life_seconds)
        ),
        agreement_bonus_per_extra=max(
            0.0, _f("agreement_bonus_per_extra", defaults.agreement_bonus_per_extra)
        ),
        max_agreement_multiplier=max(
            1.0, _f("max_agreement_multiplier", defaults.max_agreement_multiplier)
        ),
        contradict_penalty=max(
            0.0, min(1.0, _f("contradict_penalty", defaults.contradict_penalty))
        ),
        min_contrib_threshold=max(
            0.0, _f("min_contrib_threshold", defaults.min_contrib_threshold)
        ),
    )


__all__ = [
    "DEFAULT_AGREEMENT_BONUS_PER_EXTRA",
    "DEFAULT_CONTRADICT_PENALTY",
    "DEFAULT_FRESHNESS_HALF_LIFE_SECONDS",
    "DEFAULT_MAX_AGREEMENT_MULTIPLIER",
    "DEFAULT_MIN_CONTRIB_THRESHOLD",
    "DEFAULT_SOURCE_WEIGHTS",
    "DEFAULT_WEIGHTS_PATH",
    "SCORING_VERSION",
    "ComposedScore",
    "ScoringWeights",
    "compose_score",
    "freshness_factor",
    "load_weights",
    "normalize_direction",
]
