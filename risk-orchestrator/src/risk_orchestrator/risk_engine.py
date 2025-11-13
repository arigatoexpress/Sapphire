from __future__ import annotations

from typing import Tuple

from loguru import logger

from .config import settings
from .models import OrderIntent, RiskCheckResponse


def _to_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


# Per-agent allocation limits (in USD) - PvP 4-core configuration
AGENT_ALLOCATIONS = {
    "deepseek-v3": 1000.0,      # PvP Momentum
    "fingpt-alpha": 1000.0,     # PvP Alpha
    "lagllama-degen": 1000.0,   # PvP Degen
    "profit-maximizer": 1000.0, # PvP Maximizer
}

# Default allocation applied when an agent is not explicitly listed above
DEFAULT_AGENT_ALLOCATION = 125.0


class RiskEngine:


    def __init__(self, portfolio: dict, bot_id: str = None):
        self.portfolio = portfolio
        self.bot_id = bot_id
        # For futures trading, use availableBalance (margin available) instead of walletBalance
        self.balance = _to_float(portfolio.get("availableBalance")) or _to_float(portfolio.get("totalWalletBalance"))
        self.unrealized_pnl = _to_float(portfolio.get("totalUnrealizedPnL"))
        self.peak_balance = _to_float(portfolio.get("maxWalletBalance"), self.balance)
        # Use agent-specific allocation if available; otherwise fall back to default cap.
        # Always ensure we don't allocate more than the actual available balance.
        allocation_cap = AGENT_ALLOCATIONS.get(bot_id, DEFAULT_AGENT_ALLOCATION)
        self.agent_allocation = min(self.balance, allocation_cap)


    def check_drawdown(self) -> Tuple[bool, str]:
        peak = max(self.peak_balance, self.balance)
        if peak <= 0:
            return False, "Invalid peak balance"
        current_equity = self.balance + self.unrealized_pnl
        drawdown_pct = max(0.0, (peak - current_equity) / peak * 100)
        if drawdown_pct > settings.MAX_DRAWDOWN_PCT:
            return False, f"Drawdown {drawdown_pct:.1f}% > {settings.MAX_DRAWDOWN_PCT}%"
        return True, ""


    def check_margin_buffer(self) -> Tuple[bool, str]:
        if self.balance < settings.MIN_MARGIN_BUFFER_USDT:
            return False, (
                f"Balance {self.balance:.2f} < buffer {settings.MIN_MARGIN_BUFFER_USDT:.2f}"
            )
        return True, ""


    def check_per_trade_exposure(self, intent: OrderIntent) -> Tuple[bool, str]:
        reference_price = intent.price or _to_float(
            self.portfolio.get("lastPrice"), default=0.0
        ) or 50_000
        notional = intent.quantity * reference_price
        # Use agent allocation for per-trade limit instead of global balance
        limit = self.agent_allocation * settings.MAX_PER_TRADE_PCT / 100
        if notional > limit:
            return False, (
                f"Trade size {notional:.2f} > {settings.MAX_PER_TRADE_PCT}% of agent allocation (${self.agent_allocation:.0f})"
            )
        return True, ""


    def evaluate(self, intent: OrderIntent, bot_id: str, order_id: str) -> RiskCheckResponse:
        checks = [
            self.check_drawdown(),
            self.check_margin_buffer(),
            self.check_per_trade_exposure(intent),
        ]

        for approved, reason in checks:
            if not approved:
                logger.warning(f"Order rejected [{bot_id}]: {reason}")
                return RiskCheckResponse(approved=False, reason=reason)

        logger.info(
            "Order approved [%s]: %s %s qty=%.4f", bot_id, intent.symbol, intent.side, intent.quantity
        )
        return RiskCheckResponse(approved=True, order_id=order_id)
