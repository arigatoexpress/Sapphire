"""Regime-aware signal enhancement.

Takes a raw signal (symbol, action, confidence) and applies three adjustments
based on current market state:

1. Regime alignment — BUY in RISK_OFF (or SELL in RISK_ON) reduces confidence by 20%.
2. Funding extremes — signal direction that matches crowded positioning
   (e.g. BUY with extreme-positive funding) is flagged "crowded".
3. Decorrelation — if the symbol is in a pair with an active decorrelation
   event, flag "attention" so execution layer can tighten stops.

The enhancer is *advisory*: it returns an `EnhancedSignal` with adjusted
confidence + flags, leaving the pipeline free to apply routing logic.

State (regime, funding, correlations) is fetched lazily and cached for
5 minutes to keep per-signal overhead under ~50ms.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------


@dataclass
class EnhancedSignal:
    """Wraps a raw signal with regime-aware adjustments."""

    symbol: str
    action: str  # buy | sell | long | short | close
    direction: str  # long | short | flat
    original_confidence: float
    adjusted_confidence: float
    regime: str  # RISK_ON | RISK_OFF | TRANSITION | UNKNOWN
    regime_score: float
    regime_confidence: float

    # Flags (non-breaking annotations)
    flags: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    # Funding context (populated if available)
    funding_rate: float | None = None
    funding_flag: str | None = None  # crowded_long | crowded_short | elevated_* | None

    # Decorrelation context
    decorrelation_pairs: list[str] = field(default_factory=list)

    # ADX regime filter (populated when OHLC bars are supplied to enhance())
    adx_value: float | None = None
    adx_regime: str | None = None  # trending | ranging | transition | unknown
    plus_di: float | None = None
    minus_di: float | None = None

    # Full market context at the moment the signal landed — captured so the
    # signal JSONL has enough context to replay / backtest without having to
    # reconstruct state from timestamp.
    btc_spy_correlation: float | None = None
    fear_greed: int | None = None
    kronos_direction: str | None = None
    kronos_confidence: float | None = None

    # GMM regime (complementary to chain intelligence — ML-derived)
    gmm_regime: str | None = None  # trend | mean_reverting | crisis | unknown
    gmm_regime_prob: float | None = None  # probability of the current GMM state

    # VPIN flow toxicity
    vpin: float | None = None  # 0–1; > 0.7 = high informed-trading risk


# ---------------------------------------------------------------------------
# SignalEnhancer
# ---------------------------------------------------------------------------


class SignalEnhancer:
    """Applies regime, funding, and correlation-aware adjustments to signals."""

    # Confidence adjustment factors
    REGIME_PENALTY = 0.80  # 20% reduction when signal contradicts regime
    REGIME_BOOST = 1.05  # small boost when signal aligns with strong regime
    MIN_CONFIDENCE = 0.05
    MAX_CONFIDENCE = 0.99

    # Cache TTL
    STATE_TTL_SECS = 300

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state_cache: dict[str, Any] = {}
        self._state_ts: float = 0.0

    # ------------------------------------------------------------------

    def _load_state(self) -> dict[str, Any]:
        """Fetch (and cache) regime, funding, and correlation state."""
        with self._lock:
            if self._state_cache and (time.time() - self._state_ts) < self.STATE_TTL_SECS:
                return self._state_cache

            state: dict[str, Any] = {
                "regime": "UNKNOWN",
                "regime_score": 0.0,
                "regime_confidence": 0.0,
                "funding": {},
                "decorrelations": [],
                "btc_spy_correlation": None,
                "fear_greed": None,
                "kronos": {},
                "_chain_snapshot": None,
            }

            # Chain intelligence (regime + funding)
            chain_snap = None
            try:
                from lib.chain import ChainIntelligence

                ci = ChainIntelligence()
                chain_snap = ci.snapshot()
                regime = chain_snap.get("regime", {})
                state["regime"] = regime.get("state", "UNKNOWN")
                state["regime_score"] = float(regime.get("score", 0.0))
                state["regime_confidence"] = float(regime.get("confidence", 0.0))
                # Funding: build {symbol: (rate_8h, flag)} map from FundingSnapshot.perps
                funding = {}
                funding_snap = chain_snap.get("funding") or {}
                for f in funding_snap.get("perps", []) or []:
                    sym = str(f.get("coin", "")).upper()
                    if sym:
                        funding[sym] = (
                            float(f.get("funding_rate_8h", 0.0)),
                            f.get("extreme_flag") or None,
                        )
                state["funding"] = funding
                state["_chain_snapshot"] = chain_snap
            except Exception as e:
                log.debug("chain intelligence unavailable: %s", e)

            # Correlation (decorrelation events + BTC↔SPY pair snapshot)
            try:
                from lib.analytics.correlation import CorrelationEngine

                eng = CorrelationEngine()
                matrix = eng.build_matrix(window_days=30)
                events = eng.detect_decorrelations(matrix)
                state["decorrelations"] = [
                    {"pair": list(e.pair), "severity": e.severity, "note": e.note} for e in events
                ]
                idx = {s: i for i, s in enumerate(matrix.symbols)}
                if "BTC" in idx and "SPY" in idx:
                    state["btc_spy_correlation"] = round(
                        float(matrix.matrix[idx["BTC"]][idx["SPY"]]), 3
                    )
            except Exception as e:
                log.debug("correlation engine unavailable: %s", e)

            # Fear & Greed composite (reuses the chain snapshot — free if loaded)
            try:
                from lib.analytics.sentiment import compute_sentiment

                s = compute_sentiment(chain_snapshot=chain_snap)
                state["fear_greed"] = int(s.score)
            except Exception as e:
                log.debug("sentiment unavailable: %s", e)

            # Market intelligence (stablecoins, econ calendar, liquidation, order flow)
            try:
                from lib.intel.market_intelligence import load_latest_snapshot

                state["market_intel"] = load_latest_snapshot() or {}
            except Exception as e:
                log.debug("market intelligence unavailable: %s", e)
                state["market_intel"] = {}

            # GMM regime detection (sklearn-based, complements chain intelligence)
            try:
                from lib.analytics.regime import get_detector

                detector = get_detector(n_components=3)
                if detector is not None:
                    pred = detector.get_regime("BTC-USD", days=90)
                    if pred is not None:
                        state["gmm_regime"] = pred.state
                        state["gmm_regime_prob"] = pred.prob
                        state["gmm_crisis_prob"] = pred.crisis_prob or 0.0
                        state["gmm_trend_prob"] = pred.trend_prob
            except Exception as e:
                log.debug("GMM regime unavailable: %s", e)

            # VPIN flow toxicity for BTC (market proxy — cached separately per symbol)
            try:
                from lib.analytics.vpin import get_vpin_cache

                vpin_reading = get_vpin_cache().get("BTC")
                state["btc_vpin"] = vpin_reading
            except Exception as e:
                log.debug("VPIN unavailable: %s", e)

            # Kronos predictions (latest per-symbol direction + confidence)
            try:
                import json
                from pathlib import Path as _P

                pred_path = (
                    _P.home()
                    / "Code"
                    / "Sapphire"
                    / "data"
                    / "intelligence"
                    / "latest"
                    / "predictions.json"
                )
                if pred_path.exists():
                    data = json.loads(pred_path.read_text(encoding="utf-8"))
                    predictions = data.get("predictions") if isinstance(data, dict) else data
                    kronos: dict[str, tuple[str, float]] = {}
                    if isinstance(predictions, list):
                        for p in predictions:
                            if isinstance(p, dict):
                                sym = str(p.get("symbol", "")).upper().replace("-USD", "")
                                if sym:
                                    kronos[sym] = (
                                        str(p.get("direction") or p.get("prediction") or "?"),
                                        float(p.get("confidence") or 0.0),
                                    )
                    elif isinstance(predictions, dict):
                        for sym, val in predictions.items():
                            if isinstance(val, dict):
                                kronos[str(sym).upper().replace("-USD", "")] = (
                                    str(val.get("direction") or val.get("prediction") or "?"),
                                    float(val.get("confidence") or 0.0),
                                )
                    state["kronos"] = kronos
            except Exception as e:
                log.debug("kronos predictions unavailable: %s", e)

            self._state_cache = state
            self._state_ts = time.time()
            return state

    # ------------------------------------------------------------------

    # ADX thresholds (Wilder convention)
    ADX_TRENDING_MIN = 25.0
    ADX_RANGING_MAX = 20.0
    ADX_TRANSITION_PENALTY = 0.85  # 15% reduction in transition zone
    ADX_TREND_BOOST = 1.10  # 10% boost when trend + direction align
    ADX_MEANREV_PENALTY = 0.80  # 20% penalty for momentum-style longs in ranging regime

    def enhance(
        self,
        symbol: str,
        action: str,
        confidence: float,
        *,
        bars: dict | None = None,
    ) -> EnhancedSignal:
        """Apply regime/funding/correlation/ADX adjustments to a raw signal.

        Parameters
        ----------
        symbol, action, confidence
            The raw signal.
        bars
            Optional OHLC data for ADX computation:
            ``{"highs": [...], "lows": [...], "closes": [...]}``.
            When omitted, ADX filtering is skipped (adx_regime = "unknown").
            Needs at least 2 * period + 1 bars (29 with the default period of 14).
        """
        symbol = str(symbol).upper()
        action_lower = str(action).lower()
        direction = self._direction(action_lower)
        orig_conf = max(0.0, min(1.0, float(confidence)))

        state = self._load_state()

        flags: list[str] = []
        reasons: list[str] = []
        adjusted = orig_conf

        regime = state["regime"]
        rscore = state["regime_score"]
        rconf = state["regime_confidence"]

        # --- Regime alignment ------------------------------------------------
        # Long signals benefit from RISK_ON, penalized in RISK_OFF. Vice versa for short.
        if direction == "long":
            if regime == "RISK_OFF":
                adjusted *= self.REGIME_PENALTY
                flags.append("regime_contradiction")
                reasons.append(
                    f"long in RISK_OFF (score {rscore:+.2f}) — confidence ×{self.REGIME_PENALTY}"
                )
            elif regime == "RISK_ON" and rconf >= 0.5:
                adjusted *= self.REGIME_BOOST
                reasons.append(
                    f"long aligned with RISK_ON (conf {rconf:.0%}) — confidence ×{self.REGIME_BOOST}"
                )
        elif direction == "short":
            if regime == "RISK_ON":
                adjusted *= self.REGIME_PENALTY
                flags.append("regime_contradiction")
                reasons.append(
                    f"short in RISK_ON (score {rscore:+.2f}) — confidence ×{self.REGIME_PENALTY}"
                )
            elif regime == "RISK_OFF" and rconf >= 0.5:
                adjusted *= self.REGIME_BOOST
                reasons.append(
                    f"short aligned with RISK_OFF (conf {rconf:.0%}) — confidence ×{self.REGIME_BOOST}"
                )

        # --- Funding extremes ------------------------------------------------
        funding_rate: float | None = None
        funding_flag: str | None = None
        fdata = state["funding"].get(symbol)
        if fdata is not None:
            funding_rate, funding_flag = fdata
            if funding_flag == "crowded_long" and direction == "long":
                flags.append("crowded_entry")
                reasons.append(
                    f"BUY with extreme-positive funding ({funding_rate * 100:.3f}%) — crowded long"
                )
            elif funding_flag == "crowded_short" and direction == "short":
                flags.append("crowded_entry")
                reasons.append(
                    f"SELL with extreme-negative funding ({funding_rate * 100:.3f}%) — crowded short"
                )
            elif funding_flag in {"elevated_long", "elevated_short"}:
                reasons.append(f"funding {funding_flag} ({funding_rate * 100:.3f}%)")

        # --- Decorrelation context -----------------------------------------
        decorr_pairs: list[str] = []
        for ev in state["decorrelations"]:
            pair = ev.get("pair") or []
            if symbol in pair:
                decorr_pairs.append(f"{pair[0]}↔{pair[1]} ({ev.get('severity')})")
        if decorr_pairs:
            flags.append("decorrelation_attention")
            reasons.append(f"decorrelation active: {', '.join(decorr_pairs)}")

        # --- Kronos direction (reinforce if aligned; flag if contradicted) ---
        kronos_data = state.get("kronos") or {}
        kronos_entry = kronos_data.get(symbol)
        kronos_dir: str | None = None
        kronos_conf: float | None = None
        if kronos_entry:
            kronos_dir, kronos_conf = kronos_entry
            # Only act on high-confidence Kronos directions — otherwise its
            # "neutral" prediction would penalise every long/short signal.
            if kronos_conf and kronos_conf >= 0.55:
                if kronos_dir in {"down", "short", "bearish"} and direction == "long":
                    flags.append("kronos_contradiction")
                    reasons.append(
                        f"Kronos forecasts {kronos_dir} (conf {kronos_conf:.0%}) against long"
                    )
                elif kronos_dir in {"up", "long", "bullish"} and direction == "short":
                    flags.append("kronos_contradiction")
                    reasons.append(
                        f"Kronos forecasts {kronos_dir} (conf {kronos_conf:.0%}) against short"
                    )

        # --- Market intelligence factors ------------------------------------
        intel = state.get("market_intel") or {}

        # Stablecoin macro flow: large burn → capital leaving → penalise longs
        sc_signal = intel.get("stablecoin_signal")
        if sc_signal == "burn_large" and direction == "long":
            adjusted *= 0.93
            flags.append("stablecoin_outflow")
            reasons.append("large stablecoin burn — macro capital outflow")
        elif sc_signal == "mint_large" and direction == "short":
            adjusted *= 0.93
            flags.append("stablecoin_inflow")
            reasons.append("large stablecoin mint — macro capital inflow")

        # Pre-event risk: high-impact macro event (FOMC/CPI) within 24h
        pre_event_h = intel.get("pre_event_hours")
        if pre_event_h is not None and pre_event_h <= 24:
            ev_title = intel.get("next_event_title", "high-impact event")
            flags.append("pre_event_risk")
            reasons.append(f"{ev_title} in {pre_event_h:.0f}h — elevated volatility risk")

        # Liquidation cascade proximity
        liq_coins: list = intel.get("liq_cascade_coins") or []
        liq_dirs: dict = intel.get("liq_directions") or {}
        if symbol in liq_coins:
            liq_dir = liq_dirs.get(symbol)
            if liq_dir == "long" and direction == "long":
                flags.append("cascade_risk")
                reasons.append(f"{symbol} approaching long liquidation cascade zone")
            elif liq_dir == "short" and direction == "short":
                flags.append("cascade_risk")
                reasons.append(f"{symbol} approaching short liquidation cascade zone")

        # Funding velocity: extreme one-sided positioning (velocity-based, non-duplicate)
        of_sigs: dict = intel.get("order_flow_signals") or {}
        if of_sigs.get(symbol) == "extreme_positioning" and "crowded_entry" not in flags:
            flags.append("extreme_positioning")
            reasons.append(f"{symbol} funding velocity shows extreme one-sided positioning")

        # --- GMM regime (ML-derived, complements chain intelligence) ---------
        gmm_state = state.get("gmm_regime")
        gmm_prob = state.get("gmm_regime_prob", 0.0) or 0.0
        gmm_crisis_prob = state.get("gmm_crisis_prob", 0.0) or 0.0
        if gmm_state == "crisis" and gmm_prob >= 0.50:
            # Crisis regime: reduce confidence for longs; reinforce shorts
            if direction == "long":
                adjusted *= 0.88
                flags.append("gmm_crisis_regime")
                reasons.append(f"GMM detects crisis regime (prob {gmm_prob:.0%}) — penalising long")
            elif direction == "short" and "regime_contradiction" not in flags:
                adjusted *= 1.03
                reasons.append(f"GMM crisis regime (prob {gmm_prob:.0%}) aligns with short")
        elif gmm_state == "mean_reverting" and gmm_prob >= 0.55:
            # In mean-reverting regime, momentum signals carry less weight
            reasons.append(
                f"GMM: mean-reverting regime (prob {gmm_prob:.0%}, trend prob "
                f"{state.get('gmm_trend_prob', 0.0):.0%})"
            )
        elif gmm_crisis_prob >= 0.35 and direction == "long":
            # Rising crisis probability — warn even if not dominant state
            flags.append("gmm_crisis_elevated")
            reasons.append(f"GMM crisis component elevated ({gmm_crisis_prob:.0%})")

        # --- VPIN flow toxicity (informed-trading risk) ----------------------
        btc_vpin = state.get("btc_vpin")
        vpin_score: float | None = None
        if btc_vpin is not None:
            vpin_score = btc_vpin.score
            if btc_vpin.flag == "extreme_flow_toxicity":
                adjusted *= 0.85
                flags.append("extreme_flow_toxicity")
                reasons.append(
                    f"VPIN={vpin_score:.2f} (extreme) — informed traders dominate; "
                    "widening spreads, elevated slippage risk"
                )
            elif btc_vpin.flag == "high_flow_toxicity":
                adjusted *= 0.90
                flags.append("high_flow_toxicity")
                reasons.append(
                    f"VPIN={vpin_score:.2f} (high) — flow toxicity elevated; "
                    "reduce leverage or widen stops"
                )
            elif btc_vpin.toxicity == "moderate":
                reasons.append(f"VPIN={vpin_score:.2f} (moderate flow toxicity)")

        # --- ADX regime filter --------------------------------------------
        # Only applied when the caller supplies OHLC bars. The filter is
        # direction-aware: a +DI > -DI trend reinforces longs and penalises
        # shorts (and vice versa). A ranging regime penalises momentum
        # signals; the transition zone shaves 15% as a small tax on
        # ambiguous conditions.
        adx_value: float | None = None
        adx_regime: str | None = None
        plus_di_val: float | None = None
        minus_di_val: float | None = None
        if bars:
            try:
                from lib.analytics.indicators import classify_adx_regime, compute_adx

                highs = bars.get("highs") or bars.get("high") or []
                lows = bars.get("lows") or bars.get("low") or []
                closes = bars.get("closes") or bars.get("close") or []
                res = compute_adx(list(highs), list(lows), list(closes))
                if res is not None:
                    adx_value = res["adx"]
                    plus_di_val = res["plus_di"]
                    minus_di_val = res["minus_di"]
                    adx_regime = classify_adx_regime(adx_value)

                    di_bull = plus_di_val > minus_di_val
                    if adx_regime == "trending":
                        if direction == "long" and di_bull:
                            adjusted *= self.ADX_TREND_BOOST
                            reasons.append(
                                f"ADX {adx_value:.1f} trending (+DI>{minus_di_val:.1f}) — long reinforced ×{self.ADX_TREND_BOOST}"
                            )
                        elif direction == "short" and not di_bull:
                            adjusted *= self.ADX_TREND_BOOST
                            reasons.append(
                                f"ADX {adx_value:.1f} trending (-DI>{plus_di_val:.1f}) — short reinforced ×{self.ADX_TREND_BOOST}"
                            )
                        elif direction in {"long", "short"}:
                            # Trending *against* the signal direction
                            adjusted *= self.REGIME_PENALTY
                            flags.append("adx_trend_contradiction")
                            reasons.append(
                                f"ADX {adx_value:.1f} trending against {direction} (+DI {plus_di_val:.1f} / -DI {minus_di_val:.1f})"
                            )
                    elif adx_regime == "ranging":
                        # In a ranging regime, momentum-style entries (long/short)
                        # are penalised — mean-reversion setups fare better.
                        if direction in {"long", "short"}:
                            adjusted *= self.ADX_MEANREV_PENALTY
                            flags.append("adx_ranging")
                            reasons.append(
                                f"ADX {adx_value:.1f} ranging — momentum {direction} penalised ×{self.ADX_MEANREV_PENALTY}"
                            )
                    elif adx_regime == "transition":
                        adjusted *= self.ADX_TRANSITION_PENALTY
                        flags.append("adx_transition")
                        reasons.append(
                            f"ADX {adx_value:.1f} in transition zone — confidence ×{self.ADX_TRANSITION_PENALTY}"
                        )
            except Exception as e:
                log.debug("ADX computation failed: %s", e)

        # Clamp
        adjusted = max(self.MIN_CONFIDENCE, min(self.MAX_CONFIDENCE, adjusted))

        return EnhancedSignal(
            symbol=symbol,
            action=action_lower,
            direction=direction,
            original_confidence=round(orig_conf, 3),
            adjusted_confidence=round(adjusted, 3),
            regime=regime,
            regime_score=round(rscore, 3),
            regime_confidence=round(rconf, 3),
            flags=flags,
            reasons=reasons,
            funding_rate=round(funding_rate, 6) if funding_rate is not None else None,
            funding_flag=funding_flag,
            decorrelation_pairs=decorr_pairs,
            adx_value=round(adx_value, 3) if adx_value is not None else None,
            adx_regime=adx_regime,
            plus_di=round(plus_di_val, 3) if plus_di_val is not None else None,
            minus_di=round(minus_di_val, 3) if minus_di_val is not None else None,
            btc_spy_correlation=state.get("btc_spy_correlation"),
            fear_greed=state.get("fear_greed"),
            kronos_direction=kronos_dir,
            kronos_confidence=round(kronos_conf, 3) if kronos_conf is not None else None,
            gmm_regime=state.get("gmm_regime"),
            gmm_regime_prob=round(float(state["gmm_regime_prob"]), 3)
            if state.get("gmm_regime_prob") is not None
            else None,
            vpin=round(vpin_score, 4) if vpin_score is not None else None,
        )

    # ------------------------------------------------------------------

    @staticmethod
    def _direction(action: str) -> str:
        if action in {"buy", "long", "entry_long"}:
            return "long"
        if action in {"sell", "short", "entry_short"}:
            return "short"
        return "flat"


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_enhancer: SignalEnhancer | None = None


def get_enhancer() -> SignalEnhancer:
    global _enhancer
    if _enhancer is None:
        _enhancer = SignalEnhancer()
    return _enhancer


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    from pathlib import Path

    _root = Path(__file__).resolve().parents[2]
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

    eng = SignalEnhancer()
    tests = [
        ("BTC", "buy", 0.80),
        ("BTC", "sell", 0.80),
        ("ETH", "buy", 0.70),
        ("SOL", "buy", 0.65),
    ]
    for sym, act, conf in tests:
        es = eng.enhance(sym, act, conf)
        print(
            f"{sym} {act.upper():5} conf {es.original_confidence:.2f} "
            f"→ {es.adjusted_confidence:.2f} | regime={es.regime} "
            f"score={es.regime_score:+.2f} | flags={es.flags or '-'}"
        )
        for r in es.reasons:
            print(f"    - {r}")
