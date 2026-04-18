"""
Unified Position Sizing Module for Sapphire.

Canonical implementation — all position sizing across the platform should
import from here to guarantee consistent risk management.

Supports:
  - Kelly Criterion (capped)
  - Volatility-adjusted sizing
  - Drawdown protection
  - Regime-based multipliers
  - Stage multiplier (paper → staged → full_live)
  - Per-venue min/max overrides

All limits are env-configurable so we never need a redeploy to tweak risk.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum

# ---------------------------------------------------------------------------
# Configuration — every parameter is env-overridable
# ---------------------------------------------------------------------------

def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class SizingConfig:
    """Immutable sizing parameters — built once at import / init time."""

    # Kelly Criterion defaults
    default_win_rate: float = _env_float("SIZING_DEFAULT_WIN_RATE", 0.55)
    default_rr_ratio: float = _env_float("SIZING_DEFAULT_RR_RATIO", 2.0)
    kelly_cap: float = _env_float("SIZING_KELLY_CAP", 0.25)  # max Kelly fraction

    # Position caps
    max_position_pct: float = _env_float("SIZING_MAX_POSITION_PCT", 0.10)  # per-symbol
    max_total_exposure_pct: float = _env_float("SIZING_MAX_EXPOSURE_PCT", 0.50)
    min_position_usd: float = _env_float("SIZING_MIN_POSITION_USD", 5.0)

    # Volatility bands
    high_vol_threshold: float = _env_float("SIZING_HIGH_VOL_THRESHOLD", 0.05)
    high_vol_multiplier: float = _env_float("SIZING_HIGH_VOL_MULT", 0.70)
    medium_vol_threshold: float = _env_float("SIZING_MED_VOL_THRESHOLD", 0.03)
    medium_vol_multiplier: float = _env_float("SIZING_MED_VOL_MULT", 0.85)

    # Drawdown bands
    severe_dd_threshold: float = _env_float("SIZING_SEVERE_DD_THRESHOLD", 0.10)
    severe_dd_multiplier: float = _env_float("SIZING_SEVERE_DD_MULT", 0.50)
    moderate_dd_threshold: float = _env_float("SIZING_MOD_DD_THRESHOLD", 0.05)
    moderate_dd_multiplier: float = _env_float("SIZING_MOD_DD_MULT", 0.75)

    # Stage multipliers (paper → staged → full_live)
    stage_multipliers: dict[str, float] = field(default_factory=lambda: {
        "paper": _env_float("SIZING_STAGE_PAPER", 0.0),
        "staged_live": _env_float("SIZING_STAGE_STAGED", 0.25),
        "full_live": _env_float("SIZING_STAGE_FULL", 1.0),
    })


# Singleton config — parsed once
DEFAULT_CONFIG = SizingConfig()


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class SizingMethod(str, Enum):
    KELLY = "kelly"
    VOLATILITY = "volatility"
    FIXED_PCT = "fixed_pct"


class MarketRegime(str, Enum):
    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    VOLATILE = "volatile"
    CALM = "calm"
    RANGING = "ranging"
    UNKNOWN = "unknown"


# Regime multiplier table
REGIME_MULTIPLIERS: dict[MarketRegime, float] = {
    MarketRegime.TRENDING_UP: 1.2,
    MarketRegime.TRENDING_DOWN: 1.2,
    MarketRegime.VOLATILE: 0.7,
    MarketRegime.CALM: 1.1,
    MarketRegime.RANGING: 0.8,
    MarketRegime.UNKNOWN: 1.0,
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class SizingInput:
    """Everything the sizer needs to compute a position size."""

    balance: float  # total portfolio balance (USD)
    confidence: float = 0.5  # signal confidence [0, 1]
    volatility: float = 0.0  # estimated vol (0.05 = 5%)
    drawdown_pct: float = 0.0  # current drawdown as fraction (0.08 = 8%)
    win_rate: float = 0.0  # 0 = use default
    rr_ratio: float = 0.0  # 0 = use default
    regime: MarketRegime = MarketRegime.UNKNOWN
    execution_stage: str = "full_live"  # paper | staged_live | full_live
    current_exposure: float = 0.0  # sum of all open positions (USD)


@dataclass
class SizingResult:
    """Output of position sizing computation."""

    position_usd: float
    position_pct: float  # as fraction of balance
    kelly_raw: float
    kelly_capped: float
    volatility_mult: float
    drawdown_mult: float
    regime_mult: float
    stage_mult: float
    confidence_mult: float
    method: str
    capped_reason: str = ""  # why the size was capped, if it was


# ---------------------------------------------------------------------------
# Core sizing functions
# ---------------------------------------------------------------------------

def compute_kelly(
    win_rate: float,
    rr_ratio: float,
    cap: float = 0.25,
) -> tuple[float, float]:
    """
    Kelly Criterion: f* = W - (1 - W) / R

    Returns (raw_kelly, capped_kelly).
    """
    w = max(0.0, min(1.0, win_rate))
    r = max(0.01, rr_ratio)
    raw = w - (1.0 - w) / r
    capped = max(0.0, min(cap, raw))
    return raw, capped


def compute_volatility_multiplier(
    volatility: float,
    cfg: SizingConfig = DEFAULT_CONFIG,
) -> float:
    """Reduce size in high-volatility conditions."""
    if volatility >= cfg.high_vol_threshold:
        return cfg.high_vol_multiplier
    if volatility >= cfg.medium_vol_threshold:
        return cfg.medium_vol_multiplier
    return 1.0


def compute_drawdown_multiplier(
    drawdown_pct: float,
    cfg: SizingConfig = DEFAULT_CONFIG,
) -> float:
    """Reduce size when in drawdown."""
    if drawdown_pct >= cfg.severe_dd_threshold:
        return cfg.severe_dd_multiplier
    if drawdown_pct >= cfg.moderate_dd_threshold:
        return cfg.moderate_dd_multiplier
    return 1.0


def compute_position_size(
    inp: SizingInput,
    method: SizingMethod = SizingMethod.KELLY,
    cfg: SizingConfig = DEFAULT_CONFIG,
) -> SizingResult:
    """
    Canonical position sizer.

    Steps:
      1. Compute base fraction (Kelly or volatility-based or fixed %)
      2. Apply confidence multiplier
      3. Apply volatility multiplier
      4. Apply drawdown multiplier
      5. Apply regime multiplier
      6. Apply stage multiplier
      7. Enforce absolute caps
    """
    balance = max(0.0, inp.balance)
    if balance <= 0:
        return SizingResult(
            position_usd=0.0, position_pct=0.0,
            kelly_raw=0.0, kelly_capped=0.0,
            volatility_mult=1.0, drawdown_mult=1.0,
            regime_mult=1.0, stage_mult=0.0,
            confidence_mult=0.0, method=method.value,
            capped_reason="zero_balance",
        )

    win_rate = inp.win_rate if inp.win_rate > 0 else cfg.default_win_rate
    rr_ratio = inp.rr_ratio if inp.rr_ratio > 0 else cfg.default_rr_ratio

    # Step 1 — Base fraction
    kelly_raw, kelly_capped = compute_kelly(win_rate, rr_ratio, cfg.kelly_cap)

    if method == SizingMethod.KELLY:
        base_pct = kelly_capped
    elif method == SizingMethod.VOLATILITY:
        # Target 1% portfolio risk, scale by inverse volatility
        vol = max(0.01, inp.volatility)
        base_pct = min(0.01 / vol, cfg.max_position_pct)
    else:  # FIXED_PCT
        base_pct = 0.02  # 2% default

    # Step 2 — Confidence multiplier (0.5x at conf=0, 1.0x at conf=0.5, 1.5x at conf=1.0)
    confidence_mult = 0.5 + inp.confidence

    # Step 3 — Volatility multiplier
    vol_mult = compute_volatility_multiplier(inp.volatility, cfg)

    # Step 4 — Drawdown multiplier
    dd_mult = compute_drawdown_multiplier(inp.drawdown_pct, cfg)

    # Step 5 — Regime multiplier
    regime_mult = REGIME_MULTIPLIERS.get(inp.regime, 1.0)

    # Step 6 — Stage multiplier. Default to 0.0 (paper) for unknown stages so
    # a typo in the caller's config can never promote sizing to full_live.
    stage_mult = cfg.stage_multipliers.get(inp.execution_stage, 0.0)

    # Combine
    adjusted_pct = base_pct * confidence_mult * vol_mult * dd_mult * regime_mult * stage_mult

    # Step 7 — Enforce caps
    capped_reason = ""
    max_allowed_pct = cfg.max_position_pct
    if adjusted_pct > max_allowed_pct:
        adjusted_pct = max_allowed_pct
        capped_reason = "max_position_pct"

    # Exposure cap
    remaining_capacity = max(0.0, balance * cfg.max_total_exposure_pct - inp.current_exposure)
    position_usd = balance * adjusted_pct
    if position_usd > remaining_capacity:
        position_usd = remaining_capacity
        adjusted_pct = position_usd / balance if balance > 0 else 0.0
        capped_reason = "exposure_limit"

    # Min check
    if position_usd < cfg.min_position_usd:
        position_usd = 0.0
        adjusted_pct = 0.0
        capped_reason = "below_minimum"

    return SizingResult(
        position_usd=round(position_usd, 4),
        position_pct=round(adjusted_pct, 6),
        kelly_raw=round(kelly_raw, 6),
        kelly_capped=round(kelly_capped, 6),
        volatility_mult=round(vol_mult, 4),
        drawdown_mult=round(dd_mult, 4),
        regime_mult=round(regime_mult, 4),
        stage_mult=round(stage_mult, 4),
        confidence_mult=round(confidence_mult, 4),
        method=method.value,
        capped_reason=capped_reason,
    )


def apply_stage_multiplier(
    base_qty: float,
    stage: str,
    multiplier_override: float | None = None,
    cfg: SizingConfig = DEFAULT_CONFIG,
) -> float:
    """
    Apply execution stage multiplier to a pre-computed quantity.

    Useful when you already have a position size and just need to
    scale it for the current deployment stage. Unknown stages map to 0.0
    (paper) so a typo never promotes an order to full_live.
    """
    if multiplier_override is not None:
        mult = max(0.0, multiplier_override)
    else:
        mult = cfg.stage_multipliers.get(stage, 0.0)
    return round(base_qty * mult, 6)
