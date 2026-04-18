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
    action: str          # buy | sell | long | short | close
    direction: str       # long | short | flat
    original_confidence: float
    adjusted_confidence: float
    regime: str          # RISK_ON | RISK_OFF | TRANSITION | UNKNOWN
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

    # Full market context at the moment the signal landed — captured so the
    # signal JSONL has enough context to replay / backtest without having to
    # reconstruct state from timestamp.
    btc_spy_correlation: float | None = None
    fear_greed: int | None = None
    kronos_direction: str | None = None
    kronos_confidence: float | None = None


# ---------------------------------------------------------------------------
# SignalEnhancer
# ---------------------------------------------------------------------------


class SignalEnhancer:
    """Applies regime, funding, and correlation-aware adjustments to signals."""

    # Confidence adjustment factors
    REGIME_PENALTY = 0.80        # 20% reduction when signal contradicts regime
    REGIME_BOOST = 1.05          # small boost when signal aligns with strong regime
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
                    {"pair": list(e.pair), "severity": e.severity, "note": e.note}
                    for e in events
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

            # Kronos predictions (latest per-symbol direction + confidence)
            try:
                import json
                from pathlib import Path as _P
                pred_path = _P.home() / "Code" / "Sapphire" / "data" / "intelligence" / "latest" / "predictions.json"
                if pred_path.exists():
                    data = json.loads(pred_path.read_text())
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

    def enhance(self, symbol: str, action: str, confidence: float) -> EnhancedSignal:
        """Apply regime/funding/correlation adjustments to a raw signal."""
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
                reasons.append(f"long in RISK_OFF (score {rscore:+.2f}) — confidence ×{self.REGIME_PENALTY}")
            elif regime == "RISK_ON" and rconf >= 0.5:
                adjusted *= self.REGIME_BOOST
                reasons.append(f"long aligned with RISK_ON (conf {rconf:.0%}) — confidence ×{self.REGIME_BOOST}")
        elif direction == "short":
            if regime == "RISK_ON":
                adjusted *= self.REGIME_PENALTY
                flags.append("regime_contradiction")
                reasons.append(f"short in RISK_ON (score {rscore:+.2f}) — confidence ×{self.REGIME_PENALTY}")
            elif regime == "RISK_OFF" and rconf >= 0.5:
                adjusted *= self.REGIME_BOOST
                reasons.append(f"short aligned with RISK_OFF (conf {rconf:.0%}) — confidence ×{self.REGIME_BOOST}")

        # --- Funding extremes ------------------------------------------------
        funding_rate: float | None = None
        funding_flag: str | None = None
        fdata = state["funding"].get(symbol)
        if fdata is not None:
            funding_rate, funding_flag = fdata
            if funding_flag == "crowded_long" and direction == "long":
                flags.append("crowded_entry")
                reasons.append(
                    f"BUY with extreme-positive funding ({funding_rate*100:.3f}%) — crowded long"
                )
            elif funding_flag == "crowded_short" and direction == "short":
                flags.append("crowded_entry")
                reasons.append(
                    f"SELL with extreme-negative funding ({funding_rate*100:.3f}%) — crowded short"
                )
            elif funding_flag in {"elevated_long", "elevated_short"}:
                reasons.append(f"funding {funding_flag} ({funding_rate*100:.3f}%)")

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
            btc_spy_correlation=state.get("btc_spy_correlation"),
            fear_greed=state.get("fear_greed"),
            kronos_direction=kronos_dir,
            kronos_confidence=round(kronos_conf, 3) if kronos_conf is not None else None,
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
