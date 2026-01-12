"""
Shared Models for Sapphire Trading Platform

These dataclasses define the common data structures used across all bot services
for inter-service communication via Pub/Sub and Firestore storage.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class TradeSide(str, Enum):
    """Trade direction."""

    BUY = "BUY"
    SELL = "SELL"
    LONG = "LONG"
    SHORT = "SHORT"


class SignalType(str, Enum):
    """Types of trading signals."""

    ENTRY = "entry"
    EXIT = "exit"
    SCALE_IN = "scale_in"
    SCALE_OUT = "scale_out"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"


class Platform(str, Enum):
    """Supported trading platforms."""

    SYMPHONY = "symphony"
    DRIFT = "drift"
    ASTER = "aster"
    HYPERLIQUID = "hyperliquid"
    # Add new platforms here


@dataclass
class TradeSignal:
    """
    A trading signal published by the AI Engine or Market Scanner.
    Bots subscribe to these and execute if they're a target platform.
    """

    signal_id: str
    symbol: str
    side: TradeSide
    signal_type: SignalType
    confidence: float
    source: str  # e.g., "ai-engine", "market-scanner", "arbitrage-scanner"
    target_platforms: List[str] = field(default_factory=list)  # Empty = all platforms

    # Optional parameters
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    quantity: Optional[float] = None
    leverage: Optional[float] = None

    # Metadata
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def should_execute_on(self, platform: str) -> bool:
        """Check if this signal should be executed on a given platform."""
        if not self.target_platforms:
            return True  # Empty list means all platforms
        return platform in self.target_platforms


@dataclass
class TradeResult:
    """
    Result of a trade execution, published by bots after executing a signal.
    """

    trade_id: str
    signal_id: Optional[str]  # Reference to the originating signal
    platform: str
    symbol: str
    side: TradeSide

    # Execution details
    success: bool
    order_id: Optional[str] = None
    filled_quantity: float = 0.0
    avg_price: float = 0.0
    fee: float = 0.0

    # Error handling
    error_message: Optional[str] = None
    retry_count: int = 0

    # Timing
    timestamp: datetime = field(default_factory=datetime.utcnow)
    execution_time_ms: float = 0.0

    # Additional data
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Position:
    """
    An open trading position, stored in Firestore and published on updates.
    """

    position_id: str
    platform: str
    symbol: str
    side: TradeSide

    # Position details
    quantity: float
    entry_price: float
    current_price: float = 0.0

    # Risk management
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    trailing_stop: Optional[float] = None

    # P&L
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0

    # Metadata
    opened_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    agent_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def pnl_percent(self) -> float:
        """Calculate P&L percentage."""
        if self.entry_price <= 0:
            return 0.0
        if self.side in (TradeSide.BUY, TradeSide.LONG):
            return ((self.current_price - self.entry_price) / self.entry_price) * 100
        else:
            return ((self.entry_price - self.current_price) / self.entry_price) * 100


@dataclass
class BalanceUpdate:
    """
    Balance update published by bots, consumed by API Gateway for dashboard.
    """

    platform: str
    total_balance: float
    available_balance: float
    margin_used: float = 0.0

    # Breakdown by asset
    assets: Dict[str, float] = field(default_factory=dict)

    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class RiskAlert:
    """
    Risk alert published by Risk Manager, consumed by bots for action.
    """

    alert_id: str
    severity: str  # "warning", "critical", "emergency"
    alert_type: str  # "max_drawdown", "correlation_spike", "exposure_limit"

    message: str
    affected_platforms: List[str] = field(default_factory=list)
    affected_symbols: List[str] = field(default_factory=list)

    # Recommended action
    action: str = "none"  # "none", "reduce_position", "close_all", "halt_trading"

    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)
