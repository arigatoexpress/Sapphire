"""Risk management service for live trading."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict

from .config import Settings


@dataclass
class Position:
    symbol: str
    notional: float


@dataclass
class PortfolioState:
    balance: float
    total_exposure: float
    positions: Dict[str, Position] = field(default_factory=dict)


class RiskManager:
    def __init__(self, settings: Settings):
        self._max_drawdown = settings.max_drawdown
        self._max_leverage = settings.max_portfolio_leverage

    def can_open_position(self, portfolio: PortfolioState, notional: float) -> bool:
        if (portfolio.total_exposure + notional) / portfolio.balance > self._max_leverage:
            return False
        return True

    def register_fill(self, portfolio: PortfolioState, symbol: str, notional: float) -> PortfolioState:
        if symbol not in portfolio.positions:
            portfolio.positions[symbol] = Position(symbol=symbol, notional=0.0)
        
        portfolio.positions[symbol].notional += notional
        portfolio.total_exposure = sum(pos.notional for pos in portfolio.positions.values())
        
        return portfolio
