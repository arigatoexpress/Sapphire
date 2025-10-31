"""Risk utilities for the wallet orchestrator."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass
class PortfolioSnapshot:
    balance: float
    total_exposure: float
    positions: Dict[str, float]
    unrealized_pnl: float


def kelly_fraction(win_rate: float, reward_to_risk: float) -> float:
    """Return the Kelly sizing fraction based on edge parameters."""

    loss_ratio = 1 / reward_to_risk
    edge = win_rate - (1 - win_rate) * loss_ratio
    return max(0.0, edge)


def potential_loss(notional: float, entry_price: float | None, stop_loss: float | None) -> float:
    if entry_price is None or stop_loss is None:
        return 0.0
    distance = abs(entry_price - stop_loss) / max(entry_price, 1e-8)
    return notional * distance

