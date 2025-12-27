"""Trading strategy logic."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Literal, Optional


@dataclass
class MarketSnapshot:
    price: float = 0.0
    volume: float = 0.0
    change_24h: float = 0.0
    volume_24h: float = 0.0
    volatility: float = 0.0
    sma_20: float = 0.0
    rsi: float = 0.0
    macd: float = 0.0
    ma_50: float = 0.0
    ma_200: float = 0.0
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
        # 10% of portfolio allocated for asymmetric bets
        self._asymmetric_bet_fraction = 0.10

    def should_enter(self, symbol: str, snapshot: MarketSnapshot) -> Literal["BUY", "SELL", "HOLD"]:
        # Lower threshold for more frequent trading (was self._threshold)
        aggressive_threshold = self._threshold * 0.7  # 30% more sensitive

        if snapshot.change_24h > aggressive_threshold:
            return "BUY"
        if snapshot.change_24h < -aggressive_threshold:
            return "SELL"
        return "HOLD"

    def allocate_notional(
        self, portfolio_balance: float, expected_return: float, volatility: float
    ) -> float:
        """Allocate 10% of portfolio for asymmetric bets with higher frequency trading."""
        if volatility <= 0:
            return 0.0

        # Use asymmetric Kelly Criterion for more aggressive allocation
        # Higher edge assumption for asymmetric bets
        asymmetric_edge = expected_return * 1.5  # 50% more aggressive
        kelly_fraction = (asymmetric_edge) / (volatility**2)

        # Cap at 10% of portfolio for asymmetric bets (more aggressive than before)
        capped_fraction = min(kelly_fraction, self._asymmetric_bet_fraction)

        # Minimum bet size to ensure frequent trading
        min_bet = portfolio_balance * 0.005  # Minimum 0.5% per trade
        allocated_amount = portfolio_balance * capped_fraction

        return max(allocated_amount, min_bet)

    def calculate_stop_loss(self, entry_price: float, atr: float, is_long: bool) -> float:
        # ATR-based stop loss calculation
        if is_long:
            return entry_price - (atr * 1.5)
        else:
            return entry_price + (atr * 1.5)
