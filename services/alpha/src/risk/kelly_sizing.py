"""
Kelly Criterion Position Sizing for HFT

Implements fractional Kelly sizing with:
- Conservative 0.1-0.2x Kelly fraction for survival
- 1% risk per trade for $50 capital
- Dynamic position sizing based on win probability
- Risk of ruin calculations

Target: 70-80% survival probability over 24 months
"""

from dataclasses import dataclass

import numpy as np

from ..logging_utils import get_logger

logger = get_logger(__name__)


@dataclass
class KellyConfig:
    """Configuration for Kelly sizing"""

    # Fractional Kelly (1/10 here — much more conservative than the 1/2 classical
    # recommendation) because our edge estimate has high variance on a small
    # sample; full Kelly at a wrong win_prob produces ruin with probability 1.
    kelly_fraction: float = 0.1  # Use 10% of full Kelly (conservative)
    min_kelly_fraction: float = 0.05  # Minimum 5%
    max_kelly_fraction: float = 0.2  # Maximum 20%
    risk_per_trade_pct: float = 1.0  # 1% of capital per trade
    max_risk_per_trade_pct: float = 2.0  # Absolute maximum 2%
    min_position_size_usd: float = 1.0  # Minimum $1 position
    max_position_size_usd: float = 25.0  # Maximum $25 position for $50 capital
    default_win_prob: float = 0.55  # Default 55% win probability
    default_payoff_ratio: float = 1.5  # Default 1.5:1 reward:risk


class KellySizer:
    """
    Kelly Criterion Position Sizer for HFT

    Features:
    - Fractional Kelly for survival
    - Dynamic sizing based on win probability
    - Risk-adjusted position limits
    - Prevents over-leverage
    """

    def __init__(self, config: KellyConfig):
        self.config = config

        # Performance tracking
        self.win_count = 0
        self.loss_count = 0
        self.total_trades = 0
        self.position_history = []

        logger.info("[MONEY] Kelly Position Sizer initialized")
        logger.info(f"[DATA] Fractional Kelly: {config.kelly_fraction:.1%}")
        logger.info(f"[TARGET] Risk per trade: {config.risk_per_trade_pct:.1%}")

    def calculate_kelly_fraction(
        self, win_prob: float, loss_prob: float | None = None, payoff_ratio: float = 1.5
    ) -> float:
        """
        Calculate Kelly fraction for position sizing

        Formula: f = (p - q) / b
        where:
            p = win probability
            q = loss probability (1 - p)
            b = payoff ratio (win/loss)

        Args:
            win_prob: Probability of winning trade
            loss_prob: Probability of losing trade (optional, calculated as 1-p)
            payoff_ratio: Ratio of average win to average loss

        Returns:
            Kelly fraction (fractional Kelly applied)
        """
        try:
            # Validate inputs
            if win_prob < 0 or win_prob > 1:
                logger.warning(f"[WARNING] Invalid win probability: {win_prob}, using default")
                win_prob = self.config.default_win_prob

            if loss_prob is None:
                loss_prob = 1.0 - win_prob

            if payoff_ratio <= 0:
                logger.warning(f"[WARNING] Invalid payoff ratio: {payoff_ratio}, using default")
                payoff_ratio = self.config.default_payoff_ratio

            # Calculate full Kelly
            full_kelly = (win_prob - loss_prob) / payoff_ratio

            # Handle negative Kelly (negative edge)
            if full_kelly <= 0:
                logger.warning("[WARNING] Negative Kelly fraction - no edge detected")
                return 0.0

            # Apply fractional Kelly (conservative)
            fractional_kelly = full_kelly * self.config.kelly_fraction

            # Clip to safety limits
            fractional_kelly = np.clip(
                fractional_kelly, self.config.min_kelly_fraction, self.config.max_kelly_fraction
            )

            logger.debug(f"[DATA] Kelly: Full={full_kelly:.3f}, Fractional={fractional_kelly:.3f}")

            return fractional_kelly

        except Exception as e:
            logger.error(f"[ERROR] Kelly calculation error: {e}")
            return self.config.min_kelly_fraction  # Use minimum on error

    def calculate_position_size(
        self, capital: float, win_prob: float, payoff_ratio: float, stop_loss_pct: float = 0.002
    ) -> float:
        """
        Calculate position size in USD based on Kelly criterion

        Args:
            capital: Total available capital
            win_prob: Estimated win probability for this trade
            payoff_ratio: Expected reward:risk ratio
            stop_loss_pct: Stop loss as percentage (default 0.2%)

        Returns:
            Position size in USD
        """
        try:
            # Calculate Kelly fraction
            kelly_fraction = self.calculate_kelly_fraction(win_prob, None, payoff_ratio)

            # Kelly-based position size
            kelly_position_size = capital * kelly_fraction

            # Risk-based position size (1% rule)
            risk_amount = capital * (self.config.risk_per_trade_pct / 100.0)
            risk_position_size = risk_amount / stop_loss_pct if stop_loss_pct > 0 else 0

            # Vol-budget cap: Kelly can recommend huge size on a tight stop,
            # but the 1%-risk rule caps $ at risk regardless. Taking the min
            # means drawdown stays bounded even when our edge estimate is off.
            position_size = min(kelly_position_size, risk_position_size)

            # Apply hard limits
            position_size = np.clip(
                position_size,
                self.config.min_position_size_usd,
                min(self.config.max_position_size_usd, capital * 0.5),  # Max 50% of capital
            )

            logger.debug(
                f"[VALUE] Position Size: ${position_size:.2f} "
                f"(Kelly: ${kelly_position_size:.2f}, Risk: ${risk_position_size:.2f})"
            )

            return position_size

        except Exception as e:
            logger.error(f"[ERROR] Position size calculation error: {e}")
            return self.config.min_position_size_usd  # Use minimum on error

    def calculate_position_quantity(
        self,
        capital: float,
        current_price: float,
        win_prob: float,
        payoff_ratio: float,
        stop_loss_pct: float = 0.002,
    ) -> float:
        """
        Calculate position quantity (number of units to trade)

        Args:
            capital: Total available capital
            current_price: Current asset price
            win_prob: Estimated win probability
            payoff_ratio: Expected reward:risk ratio
            stop_loss_pct: Stop loss percentage

        Returns:
            Position quantity in units of the asset
        """
        try:
            position_size_usd = self.calculate_position_size(
                capital, win_prob, payoff_ratio, stop_loss_pct
            )

            if current_price <= 0:
                logger.error("[ERROR] Invalid price for quantity calculation")
                return 0.0

            quantity = position_size_usd / current_price

            logger.debug(f"[DATA] Position Quantity: {quantity:.6f} @ ${current_price:.2f}")

            return quantity

        except Exception as e:
            logger.error(f"[ERROR] Position quantity calculation error: {e}")
            return 0.0

    def update_win_probability(self, won: bool):
        """
        Update win probability estimate based on recent results

        Args:
            won: True if trade was winning, False otherwise
        """
        try:
            self.total_trades += 1

            if won:
                self.win_count += 1
            else:
                self.loss_count += 1

            # Calculate rolling win rate (last 100 trades)
            if self.total_trades > 100:
                # Keep only recent history for adaptive sizing
                recent_window = 100
                recent_win_rate = self.win_count / min(self.total_trades, recent_window)
            else:
                recent_win_rate = (
                    self.win_count / self.total_trades
                    if self.total_trades > 0
                    else self.config.default_win_prob
                )

            logger.debug(
                f"[UP] Win Rate: {recent_win_rate:.1%} ({self.win_count}/{self.total_trades})"
            )

        except Exception as e:
            logger.error(f"[ERROR] Win probability update error: {e}")

    def get_estimated_win_probability(self, strategy: str | None = None) -> float:
        """
        Get estimated win probability based on historical performance

        Args:
            strategy: Optional strategy name for strategy-specific estimates

        Returns:
            Estimated win probability
        """
        try:
            if self.total_trades < 10:
                # Not enough data, use default
                return self.config.default_win_prob

            # Calculate from recent history
            win_rate = self.win_count / self.total_trades

            # Shrinkage toward 0.55 prior — a 3-trade hot streak would otherwise
            # report 100% win rate and blow up position size. alpha=0.7 keeps
            # 30% weight on the prior until the sample dominates.
            alpha = 0.7  # Weight on historical data
            estimated_prob = alpha * win_rate + (1 - alpha) * self.config.default_win_prob

            # Ensure reasonable bounds
            estimated_prob = np.clip(estimated_prob, 0.45, 0.75)

            return estimated_prob

        except Exception as e:
            logger.error(f"[ERROR] Win probability estimation error: {e}")
            return self.config.default_win_prob

    def calculate_risk_of_ruin(self, win_prob: float, num_trades: int = 1000) -> float:
        """
        Calculate probability of ruin (losing all capital)

        Formula: P_ruin = (1 - 2p)^n for equal bet sizes

        Args:
            win_prob: Win probability
            num_trades: Number of trades to simulate

        Returns:
            Probability of ruin [0, 1]
        """
        try:
            if win_prob <= 0.5:
                # Negative edge - high ruin probability
                return 0.99

            # Simplified ruin probability for equal bets
            p_ruin = (1 - 2 * win_prob) ** num_trades

            # Ensure valid probability
            p_ruin = np.clip(p_ruin, 0.0, 1.0)

            logger.debug(f"[WARNING] Risk of Ruin: {p_ruin:.2%} over {num_trades} trades")

            return p_ruin

        except Exception as e:
            logger.error(f"[ERROR] Risk of ruin calculation error: {e}")
            return 0.5  # Neutral estimate on error

    def validate_position(
        self, capital: float, position_size_usd: float, current_positions: int = 0
    ) -> tuple[bool, str]:
        """
        Validate if position meets risk management criteria

        Args:
            capital: Total available capital
            position_size_usd: Proposed position size in USD
            current_positions: Number of current open positions

        Returns:
            Tuple of (is_valid, reason)
        """
        try:
            # Check minimum size
            if position_size_usd < self.config.min_position_size_usd:
                return (
                    False,
                    f"Position too small: ${position_size_usd:.2f} < ${self.config.min_position_size_usd}",
                )

            # Check maximum size
            if position_size_usd > self.config.max_position_size_usd:
                return (
                    False,
                    f"Position too large: ${position_size_usd:.2f} > ${self.config.max_position_size_usd}",
                )

            # Check percentage of capital
            position_pct = position_size_usd / capital if capital > 0 else 1.0
            if position_pct > 0.5:
                return False, f"Position exceeds 50% of capital: {position_pct:.1%}"

            # Check available capital
            if position_size_usd > capital:
                return False, f"Insufficient capital: ${position_size_usd:.2f} > ${capital:.2f}"

            # Check position concentration (max 10 concurrent)
            if current_positions >= 10:
                return False, f"Too many positions: {current_positions} >= 10"

            return True, "Position validated"

        except Exception as e:
            logger.error(f"[ERROR] Position validation error: {e}")
            return False, f"Validation error: {e}"

    def get_performance_stats(self) -> dict:
        """Get Kelly sizer performance statistics"""
        win_rate = self.win_count / self.total_trades if self.total_trades > 0 else 0
        loss_rate = self.loss_count / self.total_trades if self.total_trades > 0 else 0

        return {
            "total_trades": self.total_trades,
            "win_count": self.win_count,
            "loss_count": self.loss_count,
            "win_rate": win_rate,
            "loss_rate": loss_rate,
            "kelly_fraction": self.config.kelly_fraction,
            "risk_per_trade_pct": self.config.risk_per_trade_pct,
        }


def calculate_optimal_f(trades: np.ndarray) -> float:
    """
    Calculate Optimal F (fixed fraction) using Ralph Vince's method

    This is an alternative to Kelly that maximizes geometric growth

    Args:
        trades: Array of trade P&Ls

    Returns:
        Optimal F value
    """
    try:
        if len(trades) == 0:
            return 0.0

        # Find the largest loss
        largest_loss = abs(min(trades))

        if largest_loss == 0:
            return 0.0

        # Search for optimal f
        best_f = 0.0
        best_twr = 0.0

        for f in np.arange(0.01, 0.5, 0.01):
            # Calculate Terminal Wealth Relative (TWR)
            hprs = 1 + (trades / largest_loss) * f
            twr = np.prod(hprs)

            if twr > best_twr:
                best_twr = twr
                best_f = f

        # Use fractional optimal f (conservative)
        return best_f * 0.5  # Use 50% of optimal f

    except Exception as e:
        logger.error(f"[ERROR] Optimal F calculation error: {e}")
        return 0.1  # Default to 10%


def calculate_sharpe_optimal_kelly(
    mean_return: float, std_return: float, risk_free_rate: float = 0.0
) -> float:
    """
    Calculate Kelly fraction optimized for Sharpe ratio

    This variant accounts for variance in returns

    Args:
        mean_return: Mean return per trade
        std_return: Standard deviation of returns
        risk_free_rate: Risk-free rate (default 0)

    Returns:
        Sharpe-optimal Kelly fraction
    """
    try:
        if std_return == 0:
            return 0.0

        # Sharpe-optimal Kelly
        excess_return = mean_return - risk_free_rate
        kelly_fraction = excess_return / (std_return**2)

        # Half-Kelly here (not 1/10 like the base config) because the variance
        # estimate std_return already penalizes noisy returns quadratically.
        kelly_fraction *= 0.5  # Use 50% of full Kelly

        # Clip to reasonable range
        kelly_fraction = np.clip(kelly_fraction, 0.05, 0.25)

        return kelly_fraction

    except Exception as e:
        logger.error(f"[ERROR] Sharpe-optimal Kelly calculation error: {e}")
        return 0.1
