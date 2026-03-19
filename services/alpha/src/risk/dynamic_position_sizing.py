"""
Dynamic Position Sizing and Risk Management

Advanced position sizing system with real-time risk management:
- Kelly Criterion optimization
- Volatility-adjusted sizing
- Portfolio risk limits
- Drawdown-based position reduction
- Correlation-aware diversification
- Emergency kill switches
- Circuit breaker patterns
- Real-time VaR calculation

Features:
- Dynamic position sizing based on conviction and volatility
- Automatic position reduction during drawdowns
- Portfolio-level risk management
- Emergency stop-loss mechanisms
- Circuit breaker for extreme market conditions
- Integration with ensemble predictions
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple, Callable
import pandas as pd
import numpy as np
from concurrent.futures import ThreadPoolExecutor
from scipy import stats
import json

from mcp_trader.ai.ensemble_trading_system import EnsemblePrediction

logger = logging.getLogger(__name__)


@dataclass
class Position:
    """Current position information"""

    symbol: str
    size: float  # Position size (positive for long, negative for short)
    entry_price: float
    current_price: float
    timestamp: datetime
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    unrealized_pnl: float = 0.0

    @property
    def market_value(self) -> float:
        """Calculate current market value"""
        return self.size * self.current_price

    @property
    def entry_value(self) -> float:
        """Calculate entry market value"""
        return self.size * self.entry_price

    def update_pnl(self):
        """Update unrealized P&L"""
        self.unrealized_pnl = self.market_value - self.entry_value


@dataclass
class RiskMetrics:
    """Real-time risk metrics"""

    portfolio_value: float
    total_risk: float  # Current portfolio risk
    max_risk_limit: float  # Maximum allowed risk
    current_drawdown: float
    max_drawdown_limit: float
    daily_pnl: float
    daily_risk_limit: float
    var_95: float  # 95% Value at Risk
    expected_shortfall: float  # Expected shortfall (CVaR)
    correlation_risk: float  # Portfolio correlation risk
    concentration_risk: float  # Position concentration risk


@dataclass
class PositionSizingConfig:
    """Configuration for dynamic position sizing"""

    # Base position sizing
    base_position_size: float = 0.02  # 2% of portfolio per position
    max_position_size: float = 0.1  # Maximum 10% per position
    min_position_size: float = 0.001  # Minimum 0.1% per position

    # Kelly Criterion
    use_kelly_criterion: bool = True
    kelly_fraction: float = 0.5  # Use half-Kelly for safety

    # Volatility adjustment
    volatility_scaling: bool = True
    volatility_target: float = 0.02  # Target 2% volatility per position
    max_volatility_multiplier: float = 3.0

    # Risk limits
    max_portfolio_risk: float = 0.05  # 5% maximum portfolio risk
    max_daily_loss: float = 0.03  # 3% maximum daily loss
    max_drawdown_limit: float = 0.1  # 10% maximum drawdown

    # Drawdown management
    drawdown_scaling: bool = True
    drawdown_levels: List[float] = field(default_factory=lambda: [0.05, 0.1, 0.15, 0.2])
    drawdown_multipliers: List[float] = field(default_factory=lambda: [0.8, 0.6, 0.4, 0.2])

    # Diversification
    max_correlation: float = 0.7
    max_sector_exposure: float = 0.3  # 30% max per sector
    min_positions: int = 5
    max_positions: int = 20

    # Emergency settings
    emergency_stop_loss: float = 0.05  # 5% emergency stop
    circuit_breaker_threshold: float = 0.1  # 10% move triggers circuit breaker
    kill_switch_threshold: float = -0.1  # -10% triggers kill switch

    # Conviction scaling
    conviction_scaling: bool = True
    conviction_levels: List[float] = field(default_factory=lambda: [0.4, 0.6, 0.8, 0.9])
    conviction_multipliers: List[float] = field(default_factory=lambda: [0.5, 0.75, 1.0, 1.25])

    # Real-time updates
    update_interval: float = 1.0  # Seconds
    risk_recalculation_interval: float = 5.0  # Seconds


class KellyCriterionCalculator:
    """Kelly Criterion position sizing calculator"""

    def __init__(self):
        self.win_probability_history = []
        self.win_loss_ratio_history = []

    def calculate_kelly_size(self, win_probability: float, win_loss_ratio: float,
                           fraction: float = 1.0) -> float:
        """
        Calculate Kelly Criterion position size

        Args:
            win_probability: Probability of winning trade
            win_loss_ratio: Average win / average loss
            fraction: Fraction of Kelly to use (0.5 = half-Kelly)

        Returns:
            Position size as fraction of capital
        """

        if win_probability <= 0 or win_probability >= 1:
            return 0.0

        if win_loss_ratio <= 0:
            return 0.0

        # Kelly formula: f = (bp - q) / b
        # where b = odds (win_loss_ratio), p = win prob, q = loss prob
        kelly_fraction = (win_probability * win_loss_ratio - (1 - win_probability)) / win_loss_ratio

        # Apply fraction for safety
        kelly_fraction *= fraction

        # Ensure non-negative
        kelly_fraction = max(0.0, kelly_fraction)

        # Store for smoothing
        self.win_probability_history.append(win_probability)
        self.win_loss_ratio_history.append(win_loss_ratio)

        # Keep last 100 trades
        if len(self.win_probability_history) > 100:
            self.win_probability_history = self.win_probability_history[-100:]
            self.win_loss_ratio_history = self.win_loss_ratio_history[-100:]

        return kelly_fraction

    def get_smoothed_kelly(self, current_win_prob: float, current_win_loss_ratio: float,
                          fraction: float = 0.5) -> float:
        """Get smoothed Kelly size using historical data"""

        if not self.win_probability_history:
            return self.calculate_kelly_size(current_win_prob, current_win_loss_ratio, fraction)

        # Use exponential moving average for smoothing
        alpha = 0.1  # Smoothing factor

        smoothed_win_prob = np.mean(self.win_probability_history) * (1 - alpha) + current_win_prob * alpha
        smoothed_ratio = np.mean(self.win_loss_ratio_history) * (1 - alpha) + current_win_loss_ratio * alpha

        return self.calculate_kelly_size(smoothed_win_prob, smoothed_ratio, fraction)


class VolatilityAdjuster:
    """Volatility-adjusted position sizing"""

    def __init__(self, target_volatility: float = 0.02):
        self.target_volatility = target_volatility
        self.volatility_history = {}

    def adjust_for_volatility(self, symbol: str, predicted_return: float,
                            current_volatility: float, base_size: float) -> float:
        """
        Adjust position size based on volatility

        Args:
            symbol: Trading symbol
            predicted_return: Expected return
            current_volatility: Current asset volatility
            base_size: Base position size

        Returns:
            Adjusted position size
        """

        if current_volatility <= 0:
            return base_size

        # Store volatility history
        if symbol not in self.volatility_history:
            self.volatility_history[symbol] = []

        self.volatility_history[symbol].append(current_volatility)

        # Keep last 50 observations
        if len(self.volatility_history[symbol]) > 50:
            self.volatility_history[symbol] = self.volatility_history[symbol][-50:]

        # Calculate average volatility
        avg_volatility = np.mean(self.volatility_history[symbol])

        # Volatility adjustment factor
        vol_adjustment = self.target_volatility / avg_volatility

        # Limit extreme adjustments
        vol_adjustment = np.clip(vol_adjustment, 0.1, 3.0)

        adjusted_size = base_size * vol_adjustment

        return adjusted_size


class RiskManager:
    """Real-time risk management system"""

    def __init__(self, config: PositionSizingConfig):
        self.config = config
        self.positions = {}
        self.portfolio_history = []
        self.daily_pnl_history = []
        self.kill_switch_activated = False

    def calculate_portfolio_risk(self, positions: Dict[str, Position],
                               market_data: Dict[str, Any]) -> RiskMetrics:
        """Calculate comprehensive portfolio risk metrics"""

        portfolio_value = sum(pos.market_value for pos in positions.values())
        if not positions:
            portfolio_value = 100000  # Default starting value

        # Position returns and volatilities
        returns_data = []
        volatilities = []

        for symbol, position in positions.items():
            if symbol in market_data:
                price_history = market_data[symbol].get('close', [])
                if len(price_history) >= 30:
                    returns = np.diff(np.log(price_history))
                    returns_data.append(returns)
                    volatilities.append(np.std(returns))

        # Portfolio volatility (simplified)
        if returns_data:
            # Calculate correlation matrix
            if len(returns_data) > 1:
                corr_matrix = np.corrcoef(returns_data)
                avg_correlation = np.mean(corr_matrix[np.triu_indices_from(corr_matrix, k=1)])
            else:
                avg_correlation = 0.0

            # Weighted portfolio volatility
            position_weights = np.array([abs(pos.size * pos.current_price) / portfolio_value
                                       for pos in positions.values()])
            portfolio_volatility = np.sqrt(np.sum(position_weights ** 2 * np.array(volatilities) ** 2) +
                                         2 * np.sum([position_weights[i] * position_weights[j] *
                                                   volatilities[i] * volatilities[j] * avg_correlation
                                                   for i in range(len(position_weights))
                                                   for j in range(i+1, len(position_weights))]))
        else:
            portfolio_volatility = 0.0

        # VaR calculation (simplified historical simulation)
        if returns_data and len(returns_data[0]) >= 100:
            # Simulate portfolio returns
            portfolio_returns = np.zeros(len(returns_data[0]))
            for i, returns in enumerate(returns_data):
                weight = abs(list(positions.values())[i].size * list(positions.values())[i].current_price) / portfolio_value
                portfolio_returns += weight * returns

            var_95 = np.percentile(portfolio_returns, 5)
            expected_shortfall = np.mean(portfolio_returns[portfolio_returns <= var_95])
        else:
            var_95 = -0.05  # Default 5% VaR
            expected_shortfall = -0.08

        # Drawdown calculation
        self.portfolio_history.append(portfolio_value)
        if len(self.portfolio_history) > 1000:
            self.portfolio_history = self.portfolio_history[-1000:]

        if len(self.portfolio_history) >= 2:
            cumulative = np.array(self.portfolio_history)
            running_max = np.maximum.accumulate(cumulative)
            drawdowns = (cumulative - running_max) / running_max
            current_drawdown = drawdowns[-1]
        else:
            current_drawdown = 0.0

        # Daily P&L
        today = datetime.now().date()
        daily_pnl = 0.0
        if self.daily_pnl_history:
            today_pnl = [pnl for date, pnl in self.daily_pnl_history if date == today]
            daily_pnl = sum(today_pnl)

        # Risk metrics
        total_risk = portfolio_volatility * portfolio_value

        # Concentration risk
        position_sizes = [abs(pos.market_value) / portfolio_value for pos in positions.values()]
        concentration_risk = max(position_sizes) if position_sizes else 0.0

        risk_metrics = RiskMetrics(
            portfolio_value=portfolio_value,
            total_risk=total_risk,
            max_risk_limit=self.config.max_portfolio_risk * portfolio_value,
            current_drawdown=current_drawdown,
            max_drawdown_limit=self.config.max_drawdown_limit,
            daily_pnl=daily_pnl,
            daily_risk_limit=self.config.max_daily_loss * portfolio_value,
            var_95=abs(var_95) * portfolio_value,
            expected_shortfall=abs(expected_shortfall) * portfolio_value,
            correlation_risk=avg_correlation if 'avg_correlation' in locals() else 0.0,
            concentration_risk=concentration_risk
        )

        return risk_metrics

    def check_emergency_conditions(self, risk_metrics: RiskMetrics) -> List[str]:
        """Check for emergency conditions that require action"""

        alerts = []

        # Drawdown emergency
        if risk_metrics.current_drawdown <= -self.config.kill_switch_threshold:
            alerts.append("KILL_SWITCH_DRAWdown")
            self.kill_switch_activated = True

        # Daily loss emergency
        if risk_metrics.daily_pnl <= -risk_metrics.daily_risk_limit:
            alerts.append("DAILY_LOSS_LIMIT")

        # Portfolio risk emergency
        if risk_metrics.total_risk >= risk_metrics.max_risk_limit:
            alerts.append("PORTFOLIO_RISK_LIMIT")

        # Concentration risk
        if risk_metrics.concentration_risk >= 0.5:  # 50% in one position
            alerts.append("CONCENTRATION_RISK")

        return alerts

    def apply_drawdown_scaling(self, risk_metrics: RiskMetrics) -> float:
        """Apply drawdown-based position scaling"""

        if not self.config.drawdown_scaling:
            return 1.0

        current_dd = abs(risk_metrics.current_drawdown)

        # Find appropriate scaling factor
        scaling_factor = 1.0
        for level, multiplier in zip(self.config.drawdown_levels, self.config.drawdown_multipliers):
            if current_dd >= level:
                scaling_factor = multiplier
            else:
                break

        return scaling_factor


class DynamicPositionSizer:
    """
    Dynamic position sizing system with comprehensive risk management

    Features:
    - Kelly Criterion sizing
    - Volatility adjustment
    - Portfolio risk limits
    - Drawdown management
    - Emergency controls
    """

    def __init__(self, config: PositionSizingConfig = None):
        self.config = config or PositionSizingConfig()

        # Core components
        self.kelly_calculator = KellyCriterionCalculator()
        self.volatility_adjuster = VolatilityAdjuster(self.config.volatility_target)
        self.risk_manager = RiskManager(self.config)

        # Position tracking
        self.positions = {}
        self.portfolio_value = 100000.0  # Starting portfolio value

        # Emergency controls
        self.emergency_mode = False
        self.circuit_breaker_active = False

        # Callbacks
        self.emergency_callbacks = []

        logger.info("Dynamic Position Sizer initialized")

    def add_emergency_callback(self, callback: Callable):
        """Add callback for emergency events"""
        self.emergency_callbacks.append(callback)

    async def calculate_position_size(self, prediction: EnsemblePrediction,
                                    market_data: Dict[str, Any],
                                    portfolio_value: float) -> float:
        """
        Calculate optimal position size for a trade

        Args:
            prediction: Ensemble prediction
            market_data: Current market data
            portfolio_value: Current portfolio value

        Returns:
            Position size as fraction of portfolio
        """

        try:
            # Emergency checks
            if self.emergency_mode or self.circuit_breaker_active:
                logger.warning("Emergency mode active - no new positions")
                return 0.0

            # Base position size
            base_size = self.config.base_position_size

            # Apply conviction scaling
            if self.config.conviction_scaling:
                base_size = self._apply_conviction_scaling(base_size, prediction.confidence)

            # Apply Kelly Criterion
            if self.config.use_kelly_criterion:
                kelly_size = self._calculate_kelly_size(prediction)
                base_size = min(base_size, kelly_size)

            # Apply volatility adjustment
            if self.config.volatility_scaling:
                volatility = self._calculate_asset_volatility(prediction.symbol, market_data)
                base_size = self.volatility_adjuster.adjust_for_volatility(
                    prediction.symbol, prediction.direction * prediction.confidence,
                    volatility, base_size
                )

            # Apply diversification limits
            base_size = self._apply_diversification_limits(base_size, prediction.symbol)

            # Apply risk limits
            risk_metrics = self.risk_manager.calculate_portfolio_risk(self.positions, market_data)
            base_size = self._apply_risk_limits(base_size, risk_metrics)

            # Apply drawdown scaling
            drawdown_multiplier = self.risk_manager.apply_drawdown_scaling(risk_metrics)
            base_size *= drawdown_multiplier

            # Final limits
            base_size = np.clip(base_size, self.config.min_position_size, self.config.max_position_size)

            # Emergency stop-loss check
            if self._check_emergency_stop(prediction, market_data):
                base_size = 0.0

            return base_size

        except Exception as e:
            logger.error(f"Position sizing calculation failed: {str(e)}")
            return 0.0

    def _apply_conviction_scaling(self, base_size: float, confidence: float) -> float:
        """Apply conviction-based scaling"""

        scaling_factor = 1.0

        for level, multiplier in zip(self.config.conviction_levels, self.config.conviction_multipliers):
            if confidence >= level:
                scaling_factor = multiplier

        return base_size * scaling_factor

    def _calculate_kelly_size(self, prediction: EnsemblePrediction) -> float:
        """Calculate Kelly Criterion position size"""

        # Estimate win probability from confidence
        win_probability = (prediction.confidence + 1) / 2  # Convert to 0.5-1.0 range

        # Estimate win/loss ratio from volatility and direction
        # Strong directional predictions get higher win/loss ratios
        win_loss_ratio = 1.5 + abs(prediction.direction) * 2.0

        kelly_size = self.kelly_calculator.get_smoothed_kelly(
            win_probability, win_loss_ratio, self.config.kelly_fraction
        )

        return kelly_size

    def _calculate_asset_volatility(self, symbol: str, market_data: Dict[str, Any]) -> float:
        """Calculate asset volatility"""

        if symbol not in market_data or 'close' not in market_data[symbol]:
            return 0.02  # Default 2% volatility

        prices = market_data[symbol]['close']
        if len(prices) < 10:
            return 0.02

        returns = np.diff(np.log(prices))
        volatility = np.std(returns)

        return volatility

    def _apply_diversification_limits(self, base_size: float, symbol: str) -> float:
        """Apply diversification and concentration limits"""

        current_positions = len(self.positions)
        max_positions = self.config.max_positions

        # Reduce size if too many positions
        if current_positions >= max_positions:
            base_size *= 0.5

        # Check correlation with existing positions
        if self.positions:
            # This would check correlation matrix
            # For now, simple position count adjustment
            position_diversity_factor = min(1.0, self.config.min_positions / max(current_positions, 1))
            base_size *= position_diversity_factor

        return base_size

    def _apply_risk_limits(self, base_size: float, risk_metrics: RiskMetrics) -> float:
        """Apply portfolio risk limits"""

        # Check current portfolio risk
        if risk_metrics.total_risk >= risk_metrics.max_risk_limit * 0.8:  # 80% of limit
            base_size *= 0.5

        # Check daily loss limit
        if abs(risk_metrics.daily_pnl) >= risk_metrics.daily_risk_limit * 0.7:  # 70% of limit
            base_size *= 0.3

        return base_size

    def _check_emergency_stop(self, prediction: EnsemblePrediction, market_data: Dict[str, Any]) -> bool:
        """Check for emergency stop conditions"""

        # Circuit breaker for extreme market moves
        if prediction.symbol in market_data:
            close_prices = market_data[prediction.symbol].get('close', [])
            if len(close_prices) >= 2:
                recent_return = (close_prices[-1] - close_prices[-2]) / close_prices[-2]
                if abs(recent_return) >= self.config.circuit_breaker_threshold:
                    logger.warning(f"Circuit breaker triggered for {prediction.symbol}: {recent_return:.2%}")
                    self.circuit_breaker_active = True
                    return True

        return False

    async def update_positions(self, market_data: Dict[str, Any]):
        """Update all positions with latest market data"""

        try:
            # Update position prices and P&L
            for symbol, position in self.positions.items():
                if symbol in market_data and 'close' in market_data[symbol]:
                    position.current_price = market_data[symbol]['close'][-1]
                    position.update_pnl()

            # Recalculate portfolio risk
            risk_metrics = self.risk_manager.calculate_portfolio_risk(self.positions, market_data)

            # Check for emergency conditions
            emergency_alerts = self.risk_manager.check_emergency_conditions(risk_metrics)

            if emergency_alerts:
                logger.warning(f"Emergency conditions detected: {emergency_alerts}")

                # Trigger emergency callbacks
                for callback in self.emergency_callbacks:
                    await callback(emergency_alerts, risk_metrics)

                # Apply emergency actions
                await self._handle_emergency_conditions(emergency_alerts, risk_metrics)

        except Exception as e:
            logger.error(f"Position update failed: {str(e)}")

    async def _handle_emergency_conditions(self, alerts: List[str], risk_metrics: RiskMetrics):
        """Handle emergency conditions"""

        for alert in alerts:
            if alert == "KILL_SWITCH_DRAWdown":
                await self._execute_kill_switch()

            elif alert == "DAILY_LOSS_LIMIT":
                await self._reduce_positions(0.5)  # Reduce by 50%

            elif alert == "PORTFOLIO_RISK_LIMIT":
                await self._reduce_positions(0.3)  # Reduce by 30%

            elif alert == "CONCENTRATION_RISK":
                await self._rebalance_concentration()

    async def _execute_kill_switch(self):
        """Execute emergency kill switch - close all positions"""

        logger.critical("KILL SWITCH ACTIVATED - Closing all positions")

        # This would execute market orders to close all positions
        # For now, just mark as emergency mode
        self.emergency_mode = True

        # Close all positions (simulation)
        closed_value = sum(pos.market_value for pos in self.positions.values())
        self.portfolio_value += closed_value  # Realized P&L would be calculated properly
        self.positions.clear()

        logger.critical(f"All positions closed. Portfolio value: ${self.portfolio_value:,.2f}")

    async def _reduce_positions(self, reduction_factor: float):
        """Reduce position sizes by factor"""

        logger.warning(f"Reducing all positions by {reduction_factor:.1%}")

        # This would execute orders to reduce positions
        # For simulation, just scale down
        for position in self.positions.values():
            old_size = position.size
            position.size *= (1 - reduction_factor)
            logger.info(f"Reduced {position.symbol} from {old_size:.4f} to {position.size:.4f}")

    async def _rebalance_concentration(self):
        """Rebalance to reduce concentration risk"""

        logger.warning("Rebalancing for concentration risk")

        # Find largest position
        if not self.positions:
            return

        largest_pos = max(self.positions.values(), key=lambda p: abs(p.market_value))
        portfolio_value = sum(p.market_value for p in self.positions.values())

        concentration = abs(largest_pos.market_value) / portfolio_value

        if concentration > 0.4:  # 40% threshold
            reduction = 0.3  # Reduce by 30%
            await self._reduce_positions(reduction)

    def add_position(self, symbol: str, size: float, entry_price: float,
                    stop_loss: Optional[float] = None, take_profit: Optional[float] = None):
        """Add new position"""

        position = Position(
            symbol=symbol,
            size=size,
            entry_price=entry_price,
            current_price=entry_price,
            timestamp=datetime.now(),
            stop_loss=stop_loss,
            take_profit=take_profit
        )

        self.positions[symbol] = position
        logger.info(f"Added position: {symbol} {size:.4f} @ ${entry_price:.2f}")

    def remove_position(self, symbol: str):
        """Remove position"""

        if symbol in self.positions:
            position = self.positions.pop(symbol)
            realized_pnl = position.unrealized_pnl
            self.portfolio_value += realized_pnl
            logger.info(f"Closed position: {symbol}, P&L: ${realized_pnl:.2f}")

    def get_portfolio_status(self) -> Dict[str, Any]:
        """Get current portfolio status"""

        total_value = self.portfolio_value
        position_values = {symbol: pos.market_value for symbol, pos in self.positions.items()}
        total_position_value = sum(position_values.values())

        return {
            'portfolio_value': total_value,
            'position_count': len(self.positions),
            'total_exposure': total_position_value,
            'positions': {
                symbol: {
                    'size': pos.size,
                    'entry_price': pos.entry_price,
                    'current_price': pos.current_price,
                    'unrealized_pnl': pos.unrealized_pnl,
                    'market_value': pos.market_value
                }
                for symbol, pos in self.positions.items()
            },
            'emergency_mode': self.emergency_mode,
            'circuit_breaker': self.circuit_breaker_active
        }


# Convenience functions
def create_position_sizer(config: PositionSizingConfig = None) -> DynamicPositionSizer:
    """Create dynamic position sizer instance"""
    return DynamicPositionSizer(config)


async def calculate_optimal_size(sizer: DynamicPositionSizer, prediction: EnsemblePrediction,
                               market_data: Dict[str, Any], portfolio_value: float) -> float:
    """Calculate optimal position size"""
    return await sizer.calculate_position_size(prediction, market_data, portfolio_value)


def get_portfolio_status(sizer: DynamicPositionSizer) -> Dict[str, Any]:
    """Get portfolio status"""
    return sizer.get_portfolio_status()
