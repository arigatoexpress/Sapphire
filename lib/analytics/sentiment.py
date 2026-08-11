"""Proprietary Fear & Greed composite.

Synthesizes signals Sapphire already collects into a single 0-100 sentiment
index. Each input is mapped to a 0-100 sub-score (100 = extreme greed,
0 = extreme fear) then weighted into a composite.

Inputs (all from existing modules, no external sentiment API):
  1. Fear & Greed index  (25%) — the authoritative published reading
  2. Funding rates       (20%) — extreme positive = greed
  3. Market regime       (20%) — RISK_ON = greed
  4. BTC dominance level (10%) — falling dom = alt-season greed
  5. Open-interest delta (10%) — rapid OI growth = leverage greed
  6. Correlation regime  (10%) — high decorrelation = uncertainty = fear
  7. Stablecoin flow     ( 5%) — minting = money waiting to deploy = greed

All sub-scores read the FLAT `ChainIntelligence.snapshot()` shape. A sub-score
returns None when its input is genuinely unavailable, and the composite
renormalizes over whatever is live — absent data must never contribute a
neutral 50, which would silently drag the composite toward "no opinion".
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------


@dataclass
class SentimentScore:
    score: int  # 0-100
    label: str  # extreme_fear | fear | neutral | greed | extreme_greed
    components: dict[str, float] = field(default_factory=dict)
    explanations: dict[str, str] = field(default_factory=dict)
    timestamp: str = ""


# ---------------------------------------------------------------------------
# Sub-score helpers
#
# Each takes the flat chain snapshot and returns (score_0_100 | None,
# explanation). None means "input unavailable" — the caller drops it from the
# weighting rather than scoring it a neutral 50.
# ---------------------------------------------------------------------------


def _clamp(score: float) -> float:
    return max(0.0, min(100.0, score))


def _score_fear_greed(snap: dict) -> tuple[float | None, str]:
    """Published Fear & Greed index — already a 0-100 sentiment reading."""
    fg = snap.get("fear_greed")
    if fg is None:
        return None, "fear & greed index unavailable"
    fg = float(fg)
    label = snap.get("fear_greed_label") or ""
    suffix = f" ({label})" if label else ""
    return _clamp(fg), f"F&G index {fg:.0f}{suffix}"


def _score_funding(snap: dict) -> tuple[float | None, str]:
    """Funding rate → greed/fear. Extreme positive funding = greed (paying to stay long).

    `btc_funding_rate_pct` / `eth_funding_rate_pct` are already in percent.
    Extreme funding = ±0.05% per 8h, so map ±0.05 percent to ±50 around 50.
    A prior implementation divided by 0.0005 (raw-rate threshold) while
    reading percent — 100× too sensitive, clamping any positive funding to
    100 (extreme greed).
    """
    rates = [
        snap.get("btc_funding_rate_pct"),
        snap.get("eth_funding_rate_pct"),
    ]
    live = [float(r) for r in rates if r is not None]
    if not live:
        return None, "funding unavailable"
    avg_pct = sum(live) / len(live)
    skew = "longs crowded" if avg_pct > 0.04 else "shorts crowded" if avg_pct < -0.04 else "neutral"
    return _clamp(50.0 + (avg_pct / 0.05) * 50.0), f"avg 8h funding {avg_pct:+.3f}% · skew {skew}"


def _score_stablecoins(snap: dict) -> tuple[float | None, str]:
    """Stablecoin supply growth → money flowing in = greed.

    The chain snapshot carries no stablecoin supply series; that lives in
    `lib.intel.market_intelligence`. Until it is wired through, report
    unavailable rather than contributing a fake neutral.
    """
    stable = snap.get("stablecoins") or {}
    d24 = stable.get("delta_24h_usd")
    total = float(stable.get("total_usd") or 0.0)
    if d24 is None or total <= 0:
        return None, "stablecoin supply unavailable"
    pct = (d24 / total) * 100.0
    # ±0.5% 24h is a lot for stablecoins. Map ±0.5% to ±50.
    arrow = "inflow" if d24 > 0 else "outflow"
    return _clamp(50.0 + (pct / 0.5) * 50.0), f"stable supply {pct:+.2f}% ({arrow})"


def _score_dominance(snap: dict) -> tuple[float | None, str]:
    """Falling BTC dominance = alt-season (greed). Rising = flight to safety (fear).

    Without a time series we can't compute a delta here — use dominance level
    as a proxy: very high (>60%) skews mildly fearful, low (<45%) skews mildly
    greedy. Mid-range is neutral. This is intentionally low-magnitude because
    dominance is noisy on short horizons.
    """
    raw_dom = snap.get("btc_dominance")
    if raw_dom is None:
        return None, "BTC dominance unavailable"
    dom = float(raw_dom)
    if dom >= 60:
        score = 35.0
        note = f"BTC.D {dom:.1f}% (high — defensive)"
    elif dom >= 55:
        score = 45.0
        note = f"BTC.D {dom:.1f}%"
    elif dom >= 50:
        score = 55.0
        note = f"BTC.D {dom:.1f}%"
    elif dom >= 45:
        score = 65.0
        note = f"BTC.D {dom:.1f}% (alts breathing)"
    else:
        score = 75.0
        note = f"BTC.D {dom:.1f}% (alt-season)"
    return score, note


def _score_oi(snap: dict) -> tuple[float | None, str]:
    """Rapid OI growth = leverage greed. Rapid decline = deleveraging/fear.

    The chain snapshot carries no open-interest series today; CoinGlass OI
    lives in `lib.chain.providers`. Report unavailable until wired through.
    """
    d24 = (snap.get("open_interest") or {}).get("delta_24h_pct")
    if d24 is None:
        return None, "OI delta unavailable"
    # ±10% 24h is extreme leverage event. Map ±10% → ±50.
    return _clamp(50.0 + (float(d24) / 10.0) * 50.0), f"OI 24h {float(d24):+.2f}%"


def _score_correlation(corr_events: list) -> tuple[float, str]:
    """Decorrelation events → uncertainty → fear bias."""
    if not corr_events:
        return 55.0, "no decorrelations"
    severe = sum(1 for e in corr_events if e.get("severity") == "severe")
    moderate = sum(1 for e in corr_events if e.get("severity") == "moderate")
    mild = sum(1 for e in corr_events if e.get("severity") == "mild")
    penalty = severe * 15 + moderate * 8 + mild * 3
    score = max(15.0, 55.0 - penalty)
    return score, f"{severe}S/{moderate}M/{mild}m decorrelations"


def _score_regime(snap: dict) -> tuple[float | None, str]:
    """Regime score (-1..+1) mapped to 0..100.

    Reads the `classification` block emitted by `lib.chain.classify`. `regime`
    arrives as a `Regime` enum in-process and as a plain string after a JSON
    round-trip, so accept both. Confidence is derived from the share of inputs
    that resolved (`inputs_ok / inputs_total`).
    """
    clf = snap.get("classification") or {}
    if not clf:
        return None, "regime classification unavailable"
    raw_state = clf.get("regime")
    state = raw_state.value if hasattr(raw_state, "value") else str(raw_state or "UNKNOWN")
    rscore = float(clf.get("score", 0.0) or 0.0)
    inputs_total = float(clf.get("inputs_total", 0) or 0)
    conf = (float(clf.get("inputs_ok", 0) or 0) / inputs_total) if inputs_total > 0 else 0.0
    # Base neutral 50. Shift by rscore × 40 × confidence (damp by uncertainty).
    # So a +0.5 regime with 0.8 confidence shifts to 50 + 16 = 66.
    score = _clamp(50.0 + rscore * 40.0 * max(0.3, conf))
    return score, f"{state} (score {rscore:+.2f}, conf {conf:.0%})"


# ---------------------------------------------------------------------------
# Composite
# ---------------------------------------------------------------------------


WEIGHTS = {
    "fear_greed": 0.25,
    "funding": 0.20,
    "regime": 0.20,
    "dominance": 0.10,
    "oi": 0.10,
    "correlation": 0.10,
    "stablecoins": 0.05,
}


def _label_for(score: int) -> str:
    if score < 20:
        return "extreme_fear"
    if score < 40:
        return "fear"
    if score < 60:
        return "neutral"
    if score < 80:
        return "greed"
    return "extreme_greed"


def compute_sentiment(
    chain_snapshot: dict | None = None,
    correlation_events: list | None = None,
) -> SentimentScore:
    """Build the composite sentiment score.

    Accepts pre-fetched data to avoid duplicate API calls; if None, fetches
    freshly (slower). Returns SentimentScore with sub-score breakdown.
    """
    if chain_snapshot is None:
        try:
            from lib.chain import ChainIntelligence

            chain_snapshot = ChainIntelligence().snapshot()
        except Exception as e:
            log.warning("chain snapshot unavailable: %s", e)
            chain_snapshot = {}

    if correlation_events is None:
        try:
            from lib.analytics.correlation import CorrelationEngine

            eng = CorrelationEngine()
            m = eng.build_matrix(window_days=30)
            correlation_events = [{"severity": e.severity} for e in eng.detect_decorrelations(m)]
        except Exception as e:
            log.warning("correlation unavailable: %s", e)
            correlation_events = []

    # Every sub-score reads the flat snapshot directly and self-reports
    # availability; correlation is the one input passed in separately.
    scored = {
        "fear_greed": _score_fear_greed(chain_snapshot),
        "funding": _score_funding(chain_snapshot),
        "regime": _score_regime(chain_snapshot),
        "dominance": _score_dominance(chain_snapshot),
        "oi": _score_oi(chain_snapshot),
        "correlation": _score_correlation(correlation_events),
        "stablecoins": _score_stablecoins(chain_snapshot),
    }

    # Explanations cover every input (including the unavailable ones, so the
    # gap is visible); components carry only what actually scored.
    explanations = {name: expl for name, (_, expl) in scored.items()}
    components = {name: round(score, 1) for name, (score, _) in scored.items() if score is not None}

    # Renormalize over live inputs. Without this, an unavailable input scored
    # as a neutral 50 would pull the composite toward "no opinion" — the exact
    # failure that pinned this metric at ~50 regardless of the market.
    live_weight = sum(WEIGHTS[k] for k in components)
    if live_weight <= 0:
        log.warning("sentiment: no live inputs — returning neutral")
        composite = 50.0
    else:
        composite = sum(components[k] * WEIGHTS[k] for k in components) / live_weight

    missing = [k for k in WEIGHTS if k not in components]
    if missing:
        log.info(
            "sentiment: %d/%d inputs live (%.0f%% weight); missing: %s",
            len(components),
            len(WEIGHTS),
            live_weight * 100,
            ", ".join(sorted(missing)),
        )

    score = int(round(_clamp(composite)))
    return SentimentScore(
        score=score,
        label=_label_for(score),
        components=components,
        explanations=explanations,
        timestamp=datetime.now(UTC).isoformat(),
    )


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    s = compute_sentiment()
    print(f"=== Fear & Greed: {s.score}/100 ({s.label.replace('_', ' ').upper()}) ===")
    for k, v in s.components.items():
        w = WEIGHTS.get(k, 0) * 100
        print(f"  {k:12} {v:5.1f}/100  (w={w:.0f}%)  — {s.explanations.get(k, '')}")
    print(f"\ntimestamp: {s.timestamp}")
