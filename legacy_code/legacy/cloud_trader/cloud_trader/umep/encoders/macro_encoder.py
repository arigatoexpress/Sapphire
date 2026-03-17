"""
UMEP - Macro Context Encoder

Encodes macro market context (regime, risk appetite, correlations)
from aggregated market data.
"""

import logging
import statistics
from typing import Any, Dict, List, Optional

from ..market_state_tensor import MacroContext, MarketRegime, RiskAppetite

logger = logging.getLogger(__name__)


class MacroEncoder:
    """
    Encodes macro market context.

    Analyzes:
    - Market regime (trending, ranging, volatile)
    - Risk appetite (risk-on, risk-off)
    - Cross-asset correlations
    - Aggregate funding rates
    """

    def __init__(self):
        # Reference assets for regime detection
        self._btc_history: List[float] = []
        self._regime_history: List[MarketRegime] = []

    def encode(
        self,
        btc_change_24h: float = 0.0,
        eth_change_24h: float = 0.0,
        sol_change_24h: float = 0.0,
        altcoin_changes: Optional[Dict[str, float]] = None,
        btc_volatility: float = 0.0,
        funding_rates: Optional[Dict[str, float]] = None,
        btc_dominance: Optional[float] = None,
        btc_dominance_prev: Optional[float] = None,
    ) -> MacroContext:
        """
        Encode macro context from aggregated market data.

        Args:
            btc_change_24h: BTC 24h change %
            eth_change_24h: ETH 24h change %
            sol_change_24h: SOL 24h change %
            altcoin_changes: Dict of other altcoin 24h changes
            btc_volatility: BTC volatility percentile
            funding_rates: Dict of funding rates by symbol
            btc_dominance: Current BTC dominance %
            btc_dominance_prev: Previous BTC dominance %
        """
        context = MacroContext()

        # Determine regime
        context.regime = self._detect_regime(btc_change_24h, btc_volatility, altcoin_changes)

        # Determine risk appetite
        context.risk_appetite = self._detect_risk_appetite(
            btc_change_24h, eth_change_24h, sol_change_24h, altcoin_changes
        )

        # Calculate correlations
        if altcoin_changes:
            context.correlation_clusters = self._calculate_correlations(
                btc_change_24h, altcoin_changes
            )

        # BTC dominance trend
        if btc_dominance is not None and btc_dominance_prev is not None:
            diff = btc_dominance - btc_dominance_prev
            if diff > 0.5:
                context.btc_dominance_trend = "rising"
            elif diff < -0.5:
                context.btc_dominance_trend = "falling"
            else:
                context.btc_dominance_trend = "stable"

        # Aggregate funding rates
        if funding_rates:
            rates = list(funding_rates.values())
            context.funding_rates_aggregate = statistics.mean(rates) if rates else 0.0

        return context

    def _detect_regime(
        self, btc_change: float, volatility: float, altcoins: Optional[Dict[str, float]]
    ) -> MarketRegime:
        """
        Detect market regime from price action.

        Regimes:
        - VOLATILE: High volatility, choppy action
        - TRENDING_UP: Strong bullish momentum
        - TRENDING_DOWN: Strong bearish momentum
        - BREAKOUT: Sudden move up from consolidation
        - BREAKDOWN: Sudden move down from consolidation
        - RANGING: Low volatility, sideways
        """
        # Track BTC for regime detection
        self._btc_history.append(btc_change)
        if len(self._btc_history) > 10:
            self._btc_history = self._btc_history[-10:]

        # High volatility check
        if volatility > 80:
            return MarketRegime.VOLATILE

        # Strong trending
        if btc_change > 5:
            # Check if this is a breakout (previous readings were small)
            if len(self._btc_history) > 2:
                prev_avg = statistics.mean(self._btc_history[:-1])
                if abs(prev_avg) < 2:  # Was consolidating
                    return MarketRegime.BREAKOUT
            return MarketRegime.TRENDING_UP

        if btc_change < -5:
            if len(self._btc_history) > 2:
                prev_avg = statistics.mean(self._btc_history[:-1])
                if abs(prev_avg) < 2:
                    return MarketRegime.BREAKDOWN
            return MarketRegime.TRENDING_DOWN

        # Moderate trending
        if btc_change > 2:
            return MarketRegime.TRENDING_UP
        if btc_change < -2:
            return MarketRegime.TRENDING_DOWN

        return MarketRegime.RANGING

    def _detect_risk_appetite(
        self, btc: float, eth: float, sol: float, altcoins: Optional[Dict[str, float]]
    ) -> RiskAppetite:
        """
        Detect risk appetite from asset performance.

        Risk-on indicators:
        - Altcoins outperforming BTC
        - High-beta assets (SOL, memes) leading

        Risk-off indicators:
        - BTC outperforming, altcoins lagging
        - General selling pressure
        """
        # Check altcoin performance vs BTC
        if altcoins:
            altcoin_avg = statistics.mean(altcoins.values())
        else:
            altcoin_avg = (eth + sol) / 2

        btc_vs_alts = btc - altcoin_avg

        if altcoin_avg > btc + 2 and altcoin_avg > 0:
            # Alts outperforming, risk-on
            return RiskAppetite.RISK_ON
        elif btc > altcoin_avg + 2 or (btc > 0 and altcoin_avg < -2):
            # BTC outperforming or alts dumping, risk-off
            return RiskAppetite.RISK_OFF
        else:
            return RiskAppetite.NEUTRAL

    def _calculate_correlations(
        self, btc_change: float, altcoins: Dict[str, float]
    ) -> Dict[str, float]:
        """
        Calculate simple correlation clusters.

        Returns dict mapping cluster names to correlation strength.
        """
        clusters = {}

        # Major cluster (high correlation with BTC)
        major_corr = []
        meme_corr = []
        defi_corr = []

        for symbol, change in altcoins.items():
            symbol_upper = symbol.upper()

            # Simple correlation: how similar is the move to BTC?
            if btc_change != 0:
                similarity = 1 - abs((change - btc_change) / max(abs(btc_change), 1))
                similarity = max(0, min(1, similarity))
            else:
                similarity = 0.5

            # Categorize
            if symbol_upper in ["ETH", "SOL", "BNB", "XRP", "ADA"]:
                major_corr.append(similarity)
            elif symbol_upper in ["DOGE", "SHIB", "PEPE", "BONK", "WIF"]:
                meme_corr.append(similarity)
            elif symbol_upper in ["UNI", "AAVE", "COMP", "CRV", "MKR"]:
                defi_corr.append(similarity)

        if major_corr:
            clusters["majors"] = statistics.mean(major_corr)
        if meme_corr:
            clusters["memes"] = statistics.mean(meme_corr)
        if defi_corr:
            clusters["defi"] = statistics.mean(defi_corr)

        return clusters

    def encode_from_dict(self, data: Dict[str, Any]) -> MacroContext:
        """
        Convenience method to encode from a dictionary.

        Expected keys: btc_24h, eth_24h, sol_24h, altcoins, btc_vol,
                       funding, btc_dom, btc_dom_prev
        """
        return self.encode(
            btc_change_24h=data.get("btc_24h", 0),
            eth_change_24h=data.get("eth_24h", 0),
            sol_change_24h=data.get("sol_24h", 0),
            altcoin_changes=data.get("altcoins"),
            btc_volatility=data.get("btc_vol", 50),
            funding_rates=data.get("funding"),
            btc_dominance=data.get("btc_dom"),
            btc_dominance_prev=data.get("btc_dom_prev"),
        )


# Global encoder instance
_encoder: Optional[MacroEncoder] = None


def get_macro_encoder() -> MacroEncoder:
    """Get global MacroEncoder instance."""
    global _encoder
    if _encoder is None:
        _encoder = MacroEncoder()
    return _encoder
