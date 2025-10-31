"""Basic momentum strategy tuned for perpetual futures trading."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class MarketSnapshot:
    price: float
    change_24h: float
    volume: float


class MomentumStrategy:
    """Momentum heuristic with configurable aggressiveness."""

    def __init__(self, threshold: float = 2.5, notional_fraction: float = 0.05) -> None:
        self.threshold = threshold
        self.notional_fraction = notional_fraction

    def should_enter(self, symbol: str, market: MarketSnapshot) -> Optional[str]:
        if market.volume <= 0 or market.price <= 0:
            return None
        if market.change_24h >= self.threshold:
            return "BUY"
        if market.change_24h <= -self.threshold:
            return "SELL"
        return None

    def allocate_notional(self, portfolio_balance: float) -> float:
        return portfolio_balance * max(min(self.notional_fraction, 0.5), 0.001)


def parse_market_payload(payload: Dict[str, float]) -> MarketSnapshot:
    return MarketSnapshot(
        price=float(payload.get("price", 0.0)),
        change_24h=float(payload.get("change_24h", 0.0)),
        volume=float(payload.get("volume", 0.0)),
    )
