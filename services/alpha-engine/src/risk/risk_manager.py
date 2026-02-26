"""
Comprehensive risk management system for Aster Trader.
Implements Kelly Criterion, dynamic position sizing, and multi-layered risk controls.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
import numpy as np
import pandas as pd

from ..config import get_settings
from ..trading.types import PortfolioState, MarketRegime

logger = logging.getLogger(__name__)


@dataclass
class RiskMetrics:
    """Real-time risk metrics for the portfolio."""
    portfolio_value: float
    total_risk: float  # As percentage of portfolio
    max_drawdown: float
    sharpe_ratio: float
    volatility: float
    var_95: float  # Value at Risk 95%
    expected_shortfall: float
    concentration_risk: float  # Largest position as % of portfolio
    correlation_risk: float  # Average correlation between positions


@dataclass
class PositionRisk:
    """Risk metrics for individual positions."""
    symbol: str
    position_size: float
    unrealized_pnl: float
    stop_loss_price: float
    take_profit_price: float
    risk_reward_ratio: float
    volatility_adjusted_size: float
    correlation_adjusted_size: float
    final_position_size: float


class RiskManager:
    """
    Advanced risk management system implementing multiple risk controls:
    - Kelly Criterion for optimal position sizing
    - Dynamic risk adjustment based on volatility
    - Portfolio-level diversification
    - Stop-loss and take-profit management
    - Drawdown protection
    """

    def __init__(self, settings):
        self.settings = settings

        # Risk limits
        self.max_portfolio_risk = settings.max_portfolio_risk  # 10%
        self.max_single_position_risk = settings.max_single_position_risk  # 5%
        self.max_daily_loss = settings.max_daily_loss  # 15%
        self.max_drawdown_limit = settings.max_daily_loss  # 15% (same as daily loss)
        self.min_position_size = settings.min_position_size_usd
        self.max_position_size = settings.max_position_size_usd

        # Kelly Criterion parameters
        self.kelly_fraction = 0.5  # Use half-Kelly for conservatism
        self.confidence_level = 0.95

        # Risk state
        self.portfolio_history: List[Dict[str, Any]] = []
        self.daily_pnl: List[float] = []
        self.start_of_day_value: float = settings.initial_capital if hasattr(settings, 'initial_capital') else 10000.0
        self.last_reset_date = datetime.now().date()

        # Position tracking
        self.active_positions: Dict[str, PositionRisk] = {}
        self.stop_loss_orders: Dict[str, Dict[str, Any]] = {}

        logger.info("RiskManager initialized with conservative Kelly fraction and multi-layered controls")

    async def assess_portfolio_risk(self, portfolio_state: PortfolioState,
                                  market_data: Dict[str, pd.DataFrame]) -> RiskMetrics:
        """
        Comprehensive portfolio risk assessment.
        Returns detailed risk metrics for decision making.
        """
        try:
            # Calculate basic metrics
            portfolio_value = portfolio_state.total_balance + portfolio_state.total_positions_value
            daily_returns = self._calculate_daily_returns(portfolio_value)

            # Volatility and risk metrics
            volatility = self._calculate_portfolio_volatility(daily_returns)
            sharpe_ratio = self._calculate_sharpe_ratio(daily_returns)
            max_drawdown = self._calculate_max_drawdown(portfolio_value)
            var_95 = self._calculate_var_95(daily_returns)
            expected_shortfall = self._calculate_expected_shortfall(daily_returns)

            # Concentration and correlation risk
            concentration_risk = self._calculate_concentration_risk(portfolio_state)
            correlation_risk = await self._calculate_correlation_risk(market_data)

            # Total portfolio risk
            total_risk = min(self.max_portfolio_risk,
                           max(var_95, concentration_risk * 0.5, correlation_risk * 0.3))

            metrics = RiskMetrics(
                portfolio_value=portfolio_value,
                total_risk=total_risk,
                max_drawdown=max_drawdown,
                sharpe_ratio=sharpe_ratio,
                volatility=volatility,
                var_95=var_95,
                expected_shortfall=expected_shortfall,
                concentration_risk=concentration_risk,
                correlation_risk=correlation_risk
            )

            # Store for historical analysis
            self.portfolio_history.append({
                'timestamp': datetime.now(),
                'metrics': metrics,
                'portfolio_state': portfolio_state
            })

            # Keep only last 1000 entries
            if len(self.portfolio_history) > 1000:
                self.portfolio_history = self.portfolio_history[-1000:]

            return metrics

        except Exception as e:
            logger.error(f"Error assessing portfolio risk: {e}")
            # Return conservative defaults
            return RiskMetrics(
                portfolio_value=portfolio_state.total_balance,
                total_risk=self.max_portfolio_risk,
                max_drawdown=0.0,
                sharpe_ratio=0.0,
                volatility=0.05,
                var_95=0.05,
                expected_shortfall=0.07,
                concentration_risk=0.1,
                correlation_risk=0.5
            )

    async def calculate_position_size(self, symbol: str, entry_price: float,
                                    stop_loss_price: float, market_data: pd.DataFrame,
                                    portfolio_state: PortfolioState,
                                    market_regime: MarketRegime) -> PositionRisk:
        """
        Calculate optimal position size using Kelly Criterion and risk adjustments.
        Returns detailed position risk analysis.
        """
        try:
            # Basic risk calculation
            risk_amount = abs(entry_price - stop_loss_price)
            risk_percent = risk_amount / entry_price

            # Portfolio constraints
            available_capital = portfolio_state.available_balance
            max_position_value = min(
                available_capital * self.max_single_position_risk,
                self.max_position_size
            )

            # Kelly Criterion sizing
            kelly_size = self._calculate_kelly_position_size(
                symbol, market_data, risk_percent, market_regime
            )

            # Apply risk adjustments
            volatility_adjustment = self._calculate_volatility_adjustment(symbol, market_data)
            correlation_adjustment = await self._calculate_correlation_adjustment(
                symbol, market_data, portfolio_state
            )

            # Regime-based adjustment
            regime_multiplier = self._get_regime_multiplier(market_regime)

            # Final position size calculation
            base_size = kelly_size * volatility_adjustment * correlation_adjustment * regime_multiplier
            final_size = min(base_size, max_position_value / entry_price)

            # Ensure minimum size
            final_size = max(final_size, self.min_position_size / entry_price)

            # Calculate stop loss and take profit
            stop_loss_price = entry_price * (1 - risk_percent)
            take_profit_price = entry_price * (1 + risk_percent * 2)  # 2:1 reward ratio

            position_risk = PositionRisk(
                symbol=symbol,
                position_size=final_size,
                unrealized_pnl=0.0,
                stop_loss_price=stop_loss_price,
                take_profit_price=take_profit_price,
                risk_reward_ratio=2.0,
                volatility_adjusted_size=volatility_adjustment,
                correlation_adjusted_size=correlation_adjustment,
                final_position_size=final_size
            )

            # Store for tracking
            self.active_positions[symbol] = position_risk

            logger.info(f"Position size calculated for {symbol}: "
                       f"size={final_size:.6f}, kelly={kelly_size:.6f}, "
                       f"vol_adj={volatility_adjustment:.2f}, corr_adj={correlation_adjustment:.2f}")

            return position_risk

        except Exception as e:
            logger.error(f"Error calculating position size for {symbol}: {e}")
            # Return conservative position
            return PositionRisk(
                symbol=symbol,
                position_size=min(self.min_position_size / entry_price, 0.001),
                unrealized_pnl=0.0,
                stop_loss_price=entry_price * 0.95,
                take_profit_price=entry_price * 1.05,
                risk_reward_ratio=1.0,
                volatility_adjusted_size=1.0,
                correlation_adjusted_size=1.0,
                final_position_size=0.001
            )

    def _calculate_kelly_position_size(self, symbol: str, market_data: pd.DataFrame,
                                     risk_percent: float, regime: MarketRegime) -> float:
        """Calculate position size using Kelly Criterion."""
        try:
            if len(market_data) < 30:
                return self.min_position_size / market_data['close'].iloc[-1]

            # Calculate historical win rate and average win/loss ratio
            returns = market_data['close'].pct_change().dropna()

            # Simple win rate calculation (positive returns)
            win_rate = (returns > 0).mean()

            # Average win/loss ratio
            winning_returns = returns[returns > 0]
            losing_returns = returns[returns < 0]

            if len(winning_returns) == 0 or len(losing_returns) == 0:
                avg_win = 0.02  # Default 2%
                avg_loss = 0.02  # Default 2%
            else:
                avg_win = winning_returns.mean()
                avg_loss = abs(losing_returns.mean())

            # Kelly formula: K = (bp - q) / b
            # Where b = odds (avg_win/avg_loss), p = win_prob, q = loss_prob
            b = avg_win / avg_loss if avg_loss > 0 else 2.0
            p = win_rate
            q = 1 - p

            kelly_fraction = (b * p - q) / b if b > 0 else 0.1

            # Apply conservative fraction and risk limits
            kelly_fraction = max(0.01, min(kelly_fraction * self.kelly_fraction, 0.1))

            # Calculate position size based on risk
            portfolio_value = self.start_of_day_value
            risk_amount = portfolio_value * self.max_single_position_risk
            position_value = risk_amount / risk_percent
            position_size = position_value / market_data['close'].iloc[-1]

            return position_size * kelly_fraction

        except Exception as e:
            logger.error(f"Error in Kelly calculation: {e}")
            return self.min_position_size / market_data['close'].iloc[-1]

    def _calculate_volatility_adjustment(self, symbol: str, market_data: pd.DataFrame) -> float:
        """Adjust position size based on asset volatility."""
        try:
            volatility = market_data['close'].pct_change().std() * np.sqrt(365)

            # Inverse relationship: higher volatility = smaller position
            base_volatility = 0.5  # 50% annual volatility as baseline
            adjustment = base_volatility / max(volatility, 0.1)

            # Bound adjustment between 0.5 and 2.0
            return max(0.5, min(adjustment, 2.0))

        except Exception:
            return 1.0

    async def _calculate_correlation_adjustment(self, symbol: str, market_data: pd.DataFrame,
                                              portfolio_state: PortfolioState) -> float:
        """Adjust position size based on correlation with existing positions."""
        try:
            if not portfolio_state.active_positions:
                return 1.0

            # Simplified correlation adjustment
            # In practice, you'd calculate actual correlations
            existing_positions = len(portfolio_state.active_positions)

            # Reduce size as portfolio becomes more concentrated
            concentration_factor = 1.0 / max(1.0, existing_positions * 0.5)

            return max(0.5, concentration_factor)

        except Exception:
            return 1.0

    def _get_regime_multiplier(self, regime: MarketRegime) -> float:
        """Get position size multiplier based on market regime."""
        multipliers = {
            MarketRegime.LOW_VOLATILITY: 1.2,    # Increase in low vol
            MarketRegime.HIGH_VOLATILITY: 0.7,   # Decrease in high vol
            MarketRegime.BULL_TREND: 1.1,        # Slight increase in bull
            MarketRegime.BEAR_TREND: 0.8,        # Decrease in bear
            MarketRegime.SIDEWAYS: 1.0           # Neutral
        }
        return multipliers.get(regime, 1.0)

    async def check_risk_limits(self, portfolio_state: PortfolioState,
                               risk_metrics: RiskMetrics) -> List[str]:
        """
        Check all risk limits and return list of violations.
        Returns empty list if all limits are satisfied.
        """
        violations = []

        # Portfolio risk limit
        if risk_metrics.total_risk > self.max_portfolio_risk:
            violations.append(f"Portfolio risk ({risk_metrics.total_risk:.1%}) exceeds limit ({self.max_portfolio_risk:.1%})")

        # Drawdown limit
        if risk_metrics.max_drawdown > self.max_drawdown_limit:
            violations.append(f"Drawdown ({risk_metrics.max_drawdown:.1%}) exceeds limit ({self.max_drawdown_limit:.1%})")

        # Daily loss limit
        daily_pnl = sum(self.daily_pnl) if self.daily_pnl else 0
        if daily_pnl < -self.max_daily_loss * self.start_of_day_value:
            violations.append(f"Daily loss ({daily_pnl:.2f}) exceeds limit ({-self.max_daily_loss * self.start_of_day_value:.2f})")

        # Position concentration
        if risk_metrics.concentration_risk > 0.2:  # 20% concentration limit
            violations.append(f"Position concentration ({risk_metrics.concentration_risk:.1%}) too high")

        return violations

    async def should_stop_trading(self, portfolio_state: PortfolioState,
                                risk_metrics: RiskMetrics) -> Tuple[bool, str]:
        """
        Determine if trading should be stopped due to risk limits.
        Returns (should_stop, reason)
        """
        violations = await self.check_risk_limits(portfolio_state, risk_metrics)

        if violations:
            reason = "; ".join(violations)
            logger.warning(f"Risk limits violated: {reason}")
            return True, reason

        return False, ""

    def _calculate_daily_returns(self, current_value: float) -> List[float]:
        """Calculate daily returns from portfolio history."""
        if len(self.portfolio_history) < 2:
            return [0.0]

        returns = []
        prev_value = self.start_of_day_value

        for entry in self.portfolio_history[-30:]:  # Last 30 entries
            value = entry['metrics'].portfolio_value
            daily_return = (value - prev_value) / prev_value
            returns.append(daily_return)
            prev_value = value

        return returns

    def _calculate_portfolio_volatility(self, returns: List[float]) -> float:
        """Calculate annualized portfolio volatility."""
        if len(returns) < 2:
            return 0.05  # Default 5%

        return np.std(returns) * np.sqrt(365)

    def _calculate_sharpe_ratio(self, returns: List[float]) -> float:
        """Calculate Sharpe ratio."""
        if len(returns) < 2:
            return 0.0

        avg_return = np.mean(returns)
        volatility = np.std(returns)

        if volatility == 0:
            return 0.0

        # Assuming 3% risk-free rate, annualized
        risk_free_rate = 0.03
        return (avg_return - risk_free_rate/365) / volatility * np.sqrt(365)

    def _calculate_max_drawdown(self, current_value: float) -> float:
        """Calculate maximum drawdown from peak."""
        if not self.portfolio_history:
            return 0.0

        peak_value = max(entry['metrics'].portfolio_value for entry in self.portfolio_history)
        if peak_value == 0:
            return 0.0

        return (peak_value - current_value) / peak_value

    def _calculate_var_95(self, returns: List[float]) -> float:
        """Calculate 95% Value at Risk."""
        if len(returns) < 10:
            return 0.05  # Default 5%

        return abs(np.percentile(returns, 5))  # 5th percentile (worst 5%)

    def _calculate_expected_shortfall(self, returns: List[float]) -> float:
        """Calculate Expected Shortfall (CVaR)."""
        if len(returns) < 10:
            return 0.07  # Default 7%

        var_95 = self._calculate_var_95(returns)
        tail_losses = [r for r in returns if r <= -var_95]
        return abs(np.mean(tail_losses)) if tail_losses else var_95

    def _calculate_concentration_risk(self, portfolio_state: PortfolioState) -> float:
        """Calculate position concentration risk."""
        if not portfolio_state.active_positions:
            return 0.0

        total_value = portfolio_state.total_balance + portfolio_state.total_positions_value
        if total_value == 0:
            return 0.0

        # Find largest position
        max_position_value = 0
        for pos_data in portfolio_state.active_positions.values():
            # Assume position data has size and entry_price
            if isinstance(pos_data, dict):
                size = pos_data.get('size', 0)
                entry_price = pos_data.get('entry_price', 1)
                position_value = size * entry_price
                max_position_value = max(max_position_value, position_value)

        return max_position_value / total_value

    async def _calculate_correlation_risk(self, market_data: Dict[str, pd.DataFrame]) -> float:
        """Calculate average correlation between positions."""
        if len(market_data) < 2:
            return 0.5  # Default moderate correlation

        try:
            # Calculate correlations between assets
            returns_data = {}
            for symbol, df in market_data.items():
                if len(df) > 1:
                    returns_data[symbol] = df['close'].pct_change().dropna()

            if len(returns_data) < 2:
                return 0.5

            # Create correlation matrix
            returns_df = pd.DataFrame(returns_data)
            corr_matrix = returns_df.corr()

            # Average correlation (excluding diagonal)
            n = len(corr_matrix)
            if n <= 1:
                return 0.5

            total_corr = 0
            count = 0
            for i in range(n):
                for j in range(i+1, n):
                    total_corr += abs(corr_matrix.iloc[i, j])
                    count += 1

            return total_corr / count if count > 0 else 0.5

        except Exception as e:
            logger.error(f"Error calculating correlation risk: {e}")
            return 0.5

    def reset_daily_pnl(self):
        """Reset daily P&L tracking for new trading day."""
        self.daily_pnl = []
        self.start_of_day_value = self.portfolio_history[-1]['metrics'].portfolio_value if self.portfolio_history else self.start_of_day_value
        self.last_reset_date = datetime.now().date()

    def update_daily_pnl(self, pnl: float):
        """Update daily P&L tracking."""
        self.daily_pnl.append(pnl)

    def get_risk_report(self) -> Dict[str, Any]:
        """Generate comprehensive risk report."""
        if not self.portfolio_history:
            return {"error": "No portfolio history available"}

        latest = self.portfolio_history[-1]
        metrics = latest['metrics']

        return {
            'timestamp': datetime.now().isoformat(),
            'portfolio_value': metrics.portfolio_value,
            'total_risk': metrics.total_risk,
            'max_drawdown': metrics.max_drawdown,
            'sharpe_ratio': metrics.sharpe_ratio,
            'volatility': metrics.volatility,
            'var_95': metrics.var_95,
            'expected_shortfall': metrics.expected_shortfall,
            'concentration_risk': metrics.concentration_risk,
            'correlation_risk': metrics.correlation_risk,
            'active_positions': len(self.active_positions),
            'daily_pnl': sum(self.daily_pnl),
            'risk_limits_status': 'OK' if not self.portfolio_history else 'Check Required'
        }

