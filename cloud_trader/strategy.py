"""Trading strategy logic."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Literal, Optional

@dataclass
class MarketSnapshot:
    price: float
    volume: float
    change_24h: float
    atr: Optional[float] = field(default=None)

def parse_market_payload(payload: Dict[str, float]) -> MarketSnapshot:
    return MarketSnapshot(
        price=payload.get("price", 0.0),
        volume=payload.get("volume", 0.0),
        change_24h=payload.get("change_24h", 0.0),
    )

class MomentumStrategy:
    def __init__(self, threshold: float, notional_fraction: float):
        self._threshold = threshold
        self._notional_fraction = notional_fraction

    def should_enter(self, symbol: str, snapshot: MarketSnapshot) -> Literal["BUY", "SELL", "HOLD"]:
        if snapshot.change_24h > self._threshold:
            return "BUY"
        if snapshot.change_24h < -self._threshold:
            return "SELL"
        return "HOLD"
    
    def allocate_notional(self, portfolio_balance: float, expected_return: float, volatility: float) -> float:
        # Simple Kelly Criterion for now, can be expanded
        if volatility <= 0:
            return 0.0
        
        kelly_fraction = (expected_return) / (volatility**2)
        capped_fraction = min(kelly_fraction, 1.0) # Cap at 100% of portfolio
        
        # Apply risk management cap (e.g., max 2% of portfolio per trade)
        risk_managed_fraction = min(capped_fraction, self._notional_fraction)
        
        return portfolio_balance * risk_managed_fraction

    def calculate_stop_loss(self, entry_price: float, atr: float, is_long: bool) -> float:
        # ATR-based stop loss calculation
        if is_long:
            return entry_price - (atr * 1.5)
        else:
            return entry_price + (atr * 1.5)
