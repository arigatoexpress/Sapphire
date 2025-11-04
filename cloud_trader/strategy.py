"""Basic momentum strategy tuned for perpetual futures trading with pandas-ta indicators."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .ta_indicators import TAIndicators, kelly_criterion


@dataclass
class MarketSnapshot:
    price: float
    change_24h: float
    volume: float
    rsi: Optional[float] = None
    macd: Optional[Dict[str, float]] = None
    atr: Optional[float] = None
    price_history: List[float] = field(default_factory=list)


class MomentumStrategy:
    """Momentum heuristic with pandas-ta indicators and Kelly Criterion sizing."""

    def __init__(
        self,
        threshold: float = 2.5,
        notional_fraction: float = 0.05,
        use_kelly: bool = True,
        use_indicators: bool = True,
    ) -> None:
        self.threshold = threshold
        self.notional_fraction = notional_fraction
        self.use_kelly = use_kelly
        self.use_indicators = use_indicators
        self._price_history: Dict[str, List[float]] = {}

    def should_enter(self, symbol: str, market: MarketSnapshot) -> Optional[str]:
        """Determine entry signal using momentum and pandas-ta indicators."""
        if market.volume <= 0 or market.price <= 0:
            return "HOLD"
        
        # Basic momentum signal
        momentum_signal = None
        if market.change_24h >= self.threshold:
            momentum_signal = "BUY"
        elif market.change_24h <= -self.threshold:
            momentum_signal = "SELL"
        
        # Enhance with indicators if available
        if self.use_indicators and momentum_signal:
            # RSI confirmation
            if market.rsi is not None:
                if momentum_signal == "BUY" and market.rsi > 70:
                    return "HOLD"  # Overbought
                if momentum_signal == "SELL" and market.rsi < 30:
                    return "HOLD"  # Oversold
            
            # MACD confirmation
            if market.macd:
                macd_val = market.macd["macd"]
                signal_val = market.macd["signal"]
                if momentum_signal == "BUY" and macd_val < signal_val:
                    return "HOLD"  # MACD not bullish
                if momentum_signal == "SELL" and macd_val > signal_val:
                    return "HOLD"  # MACD not bearish
        
        return momentum_signal or "HOLD"

    def allocate_notional(
        self,
        portfolio_balance: float,
        expected_return: float = 0.05,
        volatility: float = 0.15,
    ) -> float:
        """Allocate position size using Kelly Criterion or fixed fraction."""
        if self.use_kelly:
            return kelly_criterion(
                expected_return=expected_return,
                volatility=volatility,
                account_balance=portfolio_balance,
                risk_fraction=self.notional_fraction,
            )
        return portfolio_balance * max(min(self.notional_fraction, 0.5), 0.001)

    def calculate_stop_loss(
        self,
        entry_price: float,
        atr: Optional[float],
        is_long: bool = True,
    ) -> float:
        """Calculate stop loss using ATR-based volatility."""
        if atr and atr > 0:
            return TAIndicators.calculate_volatility_based_stoploss(
                price=entry_price,
                atr=atr,
                multiplier=2.0,
                is_long=is_long,
            )
        # Fallback to 2% stop loss
        return entry_price * (0.98 if is_long else 1.02)


def parse_market_payload(
    payload: Dict[str, float],
    price_history: Optional[List[float]] = None,
) -> MarketSnapshot:
    """Parse market payload and optionally calculate pandas-ta indicators."""
    snapshot = MarketSnapshot(
        price=float(payload.get("price", 0.0)),
        change_24h=float(payload.get("change_24h", 0.0)),
        volume=float(payload.get("volume", 0.0)),
        price_history=price_history or [],
    )
    
    # Calculate indicators if price history available
    if price_history and len(price_history) >= 14:
        snapshot.rsi = TAIndicators.calculate_rsi(price_history)
        snapshot.macd = TAIndicators.calculate_macd(price_history)
        # ATR requires high/low, which we don't have, so leave None
    
    return snapshot
