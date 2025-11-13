"""Risk management service for live trading."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict

from .config import Settings
from .pubsub import PubSubClient


@dataclass
class Position:
    symbol: str
    notional: float
    quantity: float = 0.0
    entry_price: float = 0.0
    entry_time: datetime = field(default_factory=datetime.utcnow)
    strategy: str = "momentum"
    # Advanced position tracking
    trailing_activated: bool = False
    highest_pnl: float = 0.0
    time_decayed: bool = False
    partial_closed_0: bool = False
    partial_closed_1: bool = False
    # Intelligent TP/SL management
    take_profit_levels: Dict[float, float] = field(default_factory=dict)  # percentage: size_to_close
    stop_loss_level: float = 0.0  # percentage below entry
    trailing_stop_level: float = 0.0  # percentage below highest point
    leverage_used: float = 1.0
    liquidation_price: float = 0.0
    margin_required: float = 0.0
    # Asymmetric bet tracking
    confidence_score: float = 0.5
    volatility_adjustment: float = 1.0


@dataclass
class PortfolioState:
    balance: float
    total_exposure: float
    unrealized_pnl: float = 0.0
    positions: Dict[str, Position] = field(default_factory=dict)


class RiskManager:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._max_drawdown = settings.max_drawdown
        self._max_leverage = settings.max_portfolio_leverage
        self._total_capital = 5000.0
        self._max_loss = 1250.0
        # Anti-liquidation safeguards
        self._maintenance_margin_ratio = 0.05  # 5% maintenance margin
        self._liquidation_buffer = 0.15  # 15% buffer before liquidation
        self._max_position_size_pct = 0.08  # Max 8% of portfolio per position
        self._volatility_multiplier = 1.5  # Reduce size in high volatility

        # VPIN integration
        self._pubsub_client = PubSubClient(self._settings)
        self._vpin_positions: Dict[str, Any] = {}
        self._vpin_subscription_task: Optional[asyncio.Task[None]] = None

    async def start_vpin_listener(self):
        """Starts the Pub/Sub listener for VPIN position updates."""
        if not self._pubsub_client.is_connected():
            await self._pubsub_client.connect()
        
        self._vpin_subscription_task = asyncio.create_task(
            self._pubsub_client.subscribe("vpin_positions", self._handle_vpin_position_update)
        )

    async def stop_vpin_listener(self):
        """Stops the VPIN position listener."""
        if self._vpin_subscription_task:
            self._vpin_subscription_task.cancel()
            try:
                await self._vpin_subscription_task
            except asyncio.CancelledError:
                pass
        await self._pubsub_client.close()

    async def _handle_vpin_position_update(self, message: Dict[str, Any]):
        """Callback to handle VPIN position updates from Pub/Sub."""
        symbol = message.get("symbol")
        if symbol:
            self._vpin_positions[symbol] = message

    def can_open_position(self, portfolio: PortfolioState, notional: float, volatility: float = 1.0) -> bool:
        """Enhanced position opening with liquidation prevention."""
        # Basic leverage check
        new_leverage = (portfolio.total_exposure + notional) / portfolio.balance
        if new_leverage > self._max_leverage:
            return False

        # Position size limits
        max_position_size = portfolio.balance * self._max_position_size_pct / volatility
        if notional > max_position_size:
            return False

        # Maintenance margin check - ensure we stay far from liquidation
        projected_exposure = portfolio.total_exposure + notional
        required_margin = projected_exposure * self._maintenance_margin_ratio
        available_margin = portfolio.balance - projected_exposure

        if available_margin < (required_margin * (1 + self._liquidation_buffer)):
            return False

        return True

    def get_safe_position_size(self, portfolio: PortfolioState, volatility: float = 1.0) -> float:
        """Calculate maximum safe position size for current market conditions."""
        # Base calculation: max position size percentage adjusted for volatility
        base_size = portfolio.balance * self._max_position_size_pct

        # Adjust for volatility (higher volatility = smaller positions)
        volatility_adjusted = base_size / (volatility * self._volatility_multiplier)

        # Adjust for current leverage
        current_leverage = portfolio.total_exposure / portfolio.balance if portfolio.balance > 0 else 0
        leverage_adjusted = volatility_adjusted * (1 - current_leverage / self._max_leverage)

        # Ensure we don't exceed maintenance margin requirements
        margin_available = portfolio.balance - portfolio.total_exposure
        margin_based_limit = margin_available / (self._maintenance_margin_ratio * (1 + self._liquidation_buffer))

        return min(volatility_adjusted, leverage_adjusted, margin_based_limit, base_size)

    def should_reduce_positions(self, portfolio: PortfolioState) -> tuple[bool, float]:
        """Check if positions should be reduced to prevent liquidation."""
        if portfolio.balance <= 0:
            return True, 1.0  # Emergency liquidation

        current_leverage = portfolio.total_exposure / portfolio.balance

        # Check maintenance margin
        required_margin = portfolio.total_exposure * self._maintenance_margin_ratio
        available_margin = portfolio.balance - portfolio.total_exposure

        if available_margin < required_margin:
            # Calculate reduction needed
            excess_exposure = required_margin - available_margin
            reduction_ratio = excess_exposure / portfolio.total_exposure
            return True, min(reduction_ratio * 1.2, 1.0)  # Reduce 20% more than needed

        # Check leverage limits
        if current_leverage > self._max_leverage * 0.9:  # Within 90% of max leverage
            reduction_ratio = (current_leverage - self._max_leverage * 0.8) / current_leverage
            return True, reduction_ratio

        return False, 0.0

    def get_liquidation_distance(self, portfolio: PortfolioState) -> float:
        """Calculate distance to liquidation as a percentage."""
        if portfolio.total_exposure == 0:
            return float('inf')

        required_margin = portfolio.total_exposure * self._maintenance_margin_ratio
        available_margin = portfolio.balance - portfolio.total_exposure

        if available_margin <= 0:
            return 0.0

        return (available_margin / required_margin - 1.0) * 100  # Percentage above maintenance margin

    def calculate_optimal_tp_sl(self, entry_price: float, volatility: float, confidence: float) -> Dict[str, float]:
        """Calculate optimal take profit and stop loss levels based on market conditions."""
        # Base risk-reward ratio of 1:2
        risk_reward_ratio = 2.0

        # Adjust based on confidence (higher confidence = wider stops, lower TP targets)
        confidence_multiplier = 1.0 + (confidence - 0.5) * 0.5

        # Stop loss based on volatility and confidence
        base_sl_pct = volatility * 0.02  # 2% of volatility as base
        stop_loss_pct = base_sl_pct * confidence_multiplier * 1.5  # More conservative

        # Take profit based on risk-reward and confidence
        take_profit_pct = stop_loss_pct * risk_reward_ratio / confidence_multiplier

        return {
            'stop_loss_pct': stop_loss_pct,
            'take_profit_pct': take_profit_pct,
            'trailing_stop_pct': stop_loss_pct * 0.8,  # Tighter trailing stop
        }

    def calculate_asymmetric_position_size(self, portfolio: PortfolioState, confidence: float,
                                         volatility: float, conviction: float) -> float:
        """Calculate asymmetric position size based on confidence and market conditions."""
        # Base safe position size
        safe_size = self.get_safe_position_size(portfolio, volatility)

        # Asymmetric sizing based on conviction
        # High conviction = larger positions, low conviction = smaller positions
        conviction_multiplier = 0.5 + (conviction * 1.5)  # 0.5x to 2.0x based on conviction

        # Confidence adjustment (higher confidence = larger positions)
        confidence_multiplier = 0.8 + (confidence * 0.4)  # 0.8x to 1.2x based on confidence

        # Volatility adjustment (higher volatility = smaller positions)
        volatility_multiplier = 1.0 / (1.0 + volatility)

        asymmetric_size = safe_size * conviction_multiplier * confidence_multiplier * volatility_multiplier

        # Ensure we don't exceed safe limits
        return min(asymmetric_size, safe_size * 1.5)  # Max 1.5x safe size for high conviction bets

    def should_close_position(self, position: Position, current_price: float, entry_price: float) -> tuple[bool, str, float]:
        """Determine if a position should be closed based on TP/SL levels."""
        # Calculate current P&L percentage
        if position.quantity > 0:  # Long position
            pnl_pct = (current_price - entry_price) / entry_price
        else:  # Short position
            pnl_pct = (entry_price - current_price) / entry_price

        # Check stop loss
        if pnl_pct <= -position.stop_loss_level:
            return True, "stop_loss", pnl_pct

        # Check trailing stop
        if position.trailing_activated:
            if pnl_pct <= -position.trailing_stop_level:
                return True, "trailing_stop", pnl_pct

        # Check take profit levels (partial closes)
        for tp_pct, close_size in position.take_profit_levels.items():
            if pnl_pct >= tp_pct:
                return True, f"take_profit_{tp_pct}", pnl_pct

        # Update trailing stop if profitable
        if pnl_pct > position.highest_pnl:
            position.highest_pnl = pnl_pct
            position.trailing_stop_level = position.stop_loss_level  # Reset to original SL distance
            position.trailing_activated = True

        return False, "", pnl_pct

    def get_agent_dynamic_config(self, agent_config: Dict[str, Any], market_conditions: Dict[str, Any]) -> Dict[str, Any]:
        """Allow agents to dynamically configure their trading parameters based on market conditions."""
        risk_tolerance = agent_config.get("risk_tolerance", "medium")
        time_horizon = agent_config.get("time_horizon", "medium")
        market_regime = market_conditions.get("regime", "neutral")

        # Base configuration from agent personality
        base_config = {
            "max_leverage": agent_config.get("max_leverage_limit", 3.0),
            "position_size_pct": agent_config.get("max_position_size_pct", 0.08),
            "min_position_size_pct": agent_config.get("min_position_size_pct", 0.005),
            "tp_sl_ratio": 2.0,  # Risk-reward ratio
            "trailing_stop_buffer": 0.005,
        }

        # Adjust based on risk tolerance
        if risk_tolerance == "high":
            base_config["max_leverage"] *= 1.5
            base_config["position_size_pct"] *= 1.3
            base_config["tp_sl_ratio"] = 1.5
        elif risk_tolerance == "extreme":
            base_config["max_leverage"] *= 2.0
            base_config["position_size_pct"] *= 1.8
            base_config["tp_sl_ratio"] = 1.2
        elif risk_tolerance == "low":
            base_config["max_leverage"] *= 0.7
            base_config["position_size_pct"] *= 0.6
            base_config["tp_sl_ratio"] = 2.5

        # Adjust based on time horizon
        if time_horizon == "short":
            base_config["tp_sl_ratio"] *= 0.8  # Tighter targets for short-term
            base_config["trailing_stop_buffer"] *= 0.7
        elif time_horizon == "long":
            base_config["tp_sl_ratio"] *= 1.3  # Wider targets for long-term
            base_config["trailing_stop_buffer"] *= 1.5

        # Adjust based on market regime
        regime_preference = agent_config.get("market_regime_preference", "neutral")
        if regime_preference == market_regime:
            # Agent is in preferred regime - increase confidence
            base_config["confidence_boost"] = 1.2
            base_config["position_size_pct"] *= 1.1
        elif regime_preference == "volatile" and market_regime in ["bull", "bear"]:
            # Volatility specialist in trending market - reduce exposure
            base_config["position_size_pct"] *= 0.7
            base_config["max_leverage"] *= 0.8

        # Dynamic leverage based on market volatility
        volatility = market_conditions.get("volatility_index", 1.0)
        if volatility > 2.0:  # High volatility
            base_config["max_leverage"] *= 0.6
            base_config["position_size_pct"] *= 0.7
        elif volatility < 0.5:  # Low volatility
            base_config["max_leverage"] *= 1.2
            base_config["position_size_pct"] *= 1.1

        return base_config

    def calculate_agent_position_size(self, agent_config: Dict[str, Any], portfolio: PortfolioState,
                                    market_conditions: Dict[str, Any], conviction: float) -> float:
        """Calculate position size based on agent's dynamic configuration."""
        dynamic_config = self.get_agent_dynamic_config(agent_config, market_conditions)

        # Base safe position size
        safe_size = self.get_safe_position_size(portfolio, market_conditions.get("volatility", 1.0))

        # Agent-specific sizing within their limits
        agent_max_pct = dynamic_config["position_size_pct"]
        agent_min_pct = dynamic_config["min_position_size_pct"]

        # Conviction-based sizing within agent limits
        conviction_factor = agent_min_pct + (agent_max_pct - agent_min_pct) * conviction

        # Apply confidence boost if agent is in preferred regime
        confidence_boost = dynamic_config.get("confidence_boost", 1.0)
        conviction_factor *= confidence_boost

        # Calculate final position size
        position_size = portfolio.balance * conviction_factor

        # Ensure it doesn't exceed safe limits
        return min(position_size, safe_size * 1.5)  # Allow up to 1.5x safe size for high conviction

    def calculate_agent_tp_sl(self, agent_config: Dict[str, Any], market_conditions: Dict[str, Any],
                             entry_price: float, conviction: float) -> Dict[str, float]:
        """Calculate TP/SL levels based on agent's dynamic configuration."""
        dynamic_config = self.get_agent_dynamic_config(agent_config, market_conditions)

        volatility = market_conditions.get("volatility", 1.0)
        risk_tolerance = agent_config.get("risk_tolerance", "medium")

        # Base stop loss based on volatility and risk tolerance
        base_sl_multiplier = {
            "low": 0.01,      # 1% stop loss
            "medium": 0.015,  # 1.5% stop loss
            "high": 0.025,    # 2.5% stop loss
            "extreme": 0.04,  # 4% stop loss
        }.get(risk_tolerance, 0.02)

        # Adjust for volatility
        volatility_adjusted_sl = base_sl_multiplier * (1 + volatility * 0.5)

        # Conviction affects stop loss tightness (higher conviction = tighter stops)
        conviction_sl_factor = 0.7 + (conviction * 0.6)  # 0.7x to 1.3x
        stop_loss_pct = volatility_adjusted_sl * conviction_sl_factor

        # Take profit based on risk-reward ratio
        tp_sl_ratio = dynamic_config["tp_sl_ratio"]
        take_profit_pct = stop_loss_pct * tp_sl_ratio

        # Adjust for time horizon
        time_horizon = agent_config.get("time_horizon", "medium")
        if time_horizon == "short":
            take_profit_pct *= 0.8  # Tighter targets
        elif time_horizon == "long":
            take_profit_pct *= 1.4  # Wider targets

        return {
            "stop_loss_pct": stop_loss_pct,
            "take_profit_pct": take_profit_pct,
            "trailing_stop_buffer": dynamic_config["trailing_stop_buffer"],
            "max_leverage": dynamic_config["max_leverage"],
        }

    def update_portfolio_risk(self, portfolio: PortfolioState) -> tuple[bool, str]:
        """
        Updates and checks the overall portfolio risk, including VPIN positions.
        """
        vpin_exposure = sum(
            pos.get('notional', 0) * pos.get('leverage', 30)
            for pos in self._vpin_positions.values()
        )
        total_exposure = portfolio.total_exposure + vpin_exposure
        
        if self._total_capital > 0:
            current_leverage = total_exposure / self._total_capital
            if current_leverage > self._max_leverage:
                return False, f"Portfolio leverage {current_leverage:.2f} exceeds max leverage {self._max_leverage}"

        if portfolio.unrealized_pnl < -self._max_loss:
            return False, f"Maximum loss limit of ${self._max_loss} exceeded. Current PnL: ${portfolio.unrealized_pnl:.2f}"

        return True, ""

    def register_fill(self, portfolio: PortfolioState, symbol: str, notional: float) -> PortfolioState:
        if symbol not in portfolio.positions:
            portfolio.positions[symbol] = Position(symbol=symbol, notional=0.0)
        
        portfolio.positions[symbol].notional += notional
        portfolio.total_exposure = sum(pos.notional for pos in portfolio.positions.values())
        
        return portfolio
