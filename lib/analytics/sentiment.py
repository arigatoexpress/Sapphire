"""Proprietary Fear & Greed composite.

Synthesizes signals Sapphire already collects into a single 0-100 sentiment
index. Each input is mapped to a 0-100 sub-score (100 = extreme greed,
0 = extreme fear) then weighted into a composite.

Inputs (all from existing modules, no external sentiment API):
  1. Funding rates       (25%) — extreme positive = greed
  2. Stablecoin flow     (15%) — minting = money waiting to deploy = greed
  3. BTC dominance trend (15%) — falling dom = alt-season greed
  4. Open-interest delta (15%) — rapid OI growth = leverage greed
  5. Correlation regime  (10%) — high decorrelation = uncertainty = fear
  6. Market regime       (20%) — RISK_ON = greed
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
# Sub-score helpers (each returns (score_0_100, explanation))
# ---------------------------------------------------------------------------


def _score_funding(funding_snap: dict) -> tuple[float, str]:
    """Funding rate → greed/fear. Extreme positive funding = greed (paying to stay long).

    `avg_funding_pct` is already in percent (intelligence.py multiplies the
    raw 8h rate by 100). Extreme funding = ±0.05% per 8h, so map ±0.05
    percent to ±50 around 50. The prior implementation divided by 0.0005
    (raw-rate threshold) while reading percent — 100× too sensitive,
    clamping any positive funding to 100 (extreme greed).
    """
    avg_pct = float(funding_snap.get("avg_funding_pct", 0.0) or 0.0)
    score = 50.0 + (avg_pct / 0.05) * 50.0
    score = max(0.0, min(100.0, score))
    skew = funding_snap.get("majors_skew", "neutral")
    return score, f"avg 8h funding {avg_pct:+.3f}% · skew {skew}"


def _score_stablecoins(stable: dict) -> tuple[float, str]:
    """Stablecoin supply growth → money flowing in = greed."""
    d24 = stable.get("delta_24h_usd")
    total = float(stable.get("total_usd") or 1.0)
    if d24 is None or total <= 0:
        return 50.0, "no delta data yet"
    pct = (d24 / total) * 100.0
    # ±0.5% 24h is a lot for stablecoins. Map ±0.5% to ±50.
    score = 50.0 + (pct / 0.5) * 50.0
    score = max(0.0, min(100.0, score))
    arrow = "inflow" if d24 > 0 else "outflow"
    return score, f"stable supply {pct:+.2f}% ({arrow})"


def _score_dominance(overview: dict) -> tuple[float, str]:
    """Falling BTC dominance = alt-season (greed). Rising = flight to safety (fear).

    Without a time series we can't compute a delta here — use dominance level
    as a proxy: very high (>60%) skews mildly fearful, low (<45%) skews mildly
    greedy. Mid-range is neutral. This is intentionally low-magnitude because
    dominance is noisy on short horizons.
    """
    dom = float(overview.get("btc_dominance") or 50.0)
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


def _score_oi(oi: dict) -> tuple[float, str]:
    """Rapid OI growth = leverage greed. Rapid decline = deleveraging/fear."""
    d24 = oi.get("delta_24h_pct")
    if d24 is None:
        return 50.0, "OI delta unavailable"
    # ±10% 24h is extreme leverage event. Map ±10% → ±50.
    score = 50.0 + (d24 / 10.0) * 50.0
    score = max(0.0, min(100.0, score))
    return score, f"OI 24h {d24:+.2f}%"


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


def _score_regime(regime: dict) -> tuple[float, str]:
    """Regime score (-1..+1) mapped to 0..100."""
    rscore = float(regime.get("score", 0.0) or 0.0)
    conf = float(regime.get("confidence", 0.0) or 0.0)
    state = regime.get("state", "UNKNOWN")
    # Base neutral 50. Shift by rscore × 40 × confidence (damp by uncertainty).
    # So a +0.5 regime with 0.8 confidence shifts to 50 + 16 = 66.
    score = 50.0 + rscore * 40.0 * max(0.3, conf)
    score = max(0.0, min(100.0, score))
    return score, f"{state} (score {rscore:+.2f}, conf {conf:.0%})"


# ---------------------------------------------------------------------------
# Composite
# ---------------------------------------------------------------------------


WEIGHTS = {
    "funding": 0.25,
    "stablecoins": 0.15,
    "dominance": 0.15,
    "oi": 0.15,
    "correlation": 0.10,
    "regime": 0.20,
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

    overview = chain_snapshot.get("overview") or {}
    funding = chain_snapshot.get("funding") or {}
    oi = chain_snapshot.get("open_interest") or {}
    stable = chain_snapshot.get("stablecoins") or {}
    regime = chain_snapshot.get("regime") or {}

    funding_s, funding_e = _score_funding(funding)
    stable_s, stable_e = _score_stablecoins(stable)
    dom_s, dom_e = _score_dominance(overview)
    oi_s, oi_e = _score_oi(oi)
    corr_s, corr_e = _score_correlation(correlation_events)
    reg_s, reg_e = _score_regime(regime)

    components = {
        "funding": round(funding_s, 1),
        "stablecoins": round(stable_s, 1),
        "dominance": round(dom_s, 1),
        "oi": round(oi_s, 1),
        "correlation": round(corr_s, 1),
        "regime": round(reg_s, 1),
    }
    explanations = {
        "funding": funding_e,
        "stablecoins": stable_e,
        "dominance": dom_e,
        "oi": oi_e,
        "correlation": corr_e,
        "regime": reg_e,
    }

    composite = sum(components[k] * WEIGHTS[k] for k in components)
    score = int(round(max(0.0, min(100.0, composite))))
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
