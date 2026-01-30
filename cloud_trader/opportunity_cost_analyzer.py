"""
Opportunity Cost Analyzer - Intelligent Position Switching

Analyzes whether to switch from current position to a new trading opportunity
based on expected value (EV) comparison.

Decision Framework:
  Current Position EV = P(win) × remaining_upside - P(loss) × potential_loss
  New Signal EV = P(win_new) × potential_gain_new - P(loss_new) × potential_loss_new
  Switching Cost = exit_slippage + entry_slippage + fees (0.2-1.0%)

  IF (New EV - Current EV - Switching Cost) > threshold:
    SWITCH POSITION
  ELSE:
    HOLD POSITION

Thresholds:
- 2% net benefit → SWITCH (full exit + new entry)
- 0.5-2% net benefit → PARTIAL_SWITCH (exit 50%, enter 50% new)
- <0.5% net benefit → HOLD (keep current position)

Benefits:
- Avoid opportunity cost of holding losing positions
- Capture higher EV opportunities dynamically
- Systematic decision-making (removes emotion)
- Track switching performance
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class SwitchingDecision(Enum):
    """Position switching decision"""
    HOLD = "hold"  # Keep current position
    PARTIAL_SWITCH = "partial_switch"  # Exit 50%, enter 50% new
    SWITCH = "switch"  # Full exit + full new entry


@dataclass
class Position:
    """Current position state"""
    symbol: str
    side: str  # LONG or SHORT
    entry_price: float
    current_price: float
    quantity: float
    take_profit: float
    stop_loss: float
    unrealized_pnl_pct: float
    confidence: float  # Original signal confidence


@dataclass
class NewSignal:
    """New trading opportunity"""
    symbol: str
    side: str
    current_price: float
    target_price: float
    stop_loss: float
    confidence: float
    signal_strength: float


@dataclass
class OpportunityCostAnalysis:
    """Result of opportunity cost analysis"""
    decision: SwitchingDecision
    current_ev: float
    new_ev: float
    switching_cost: float
    net_benefit: float
    reasoning: str
    confidence: float
    current_position_upside: float
    current_position_downside: float
    new_signal_upside: float
    new_signal_downside: float


class OpportunityCostAnalyzer:
    """
    Analyzes opportunity cost of position switching decisions.

    Uses expected value (EV) framework to compare current position
    vs. new signal opportunities.
    """

    # Platform-specific trading costs (slippage + fees)
    PLATFORM_COSTS = {
        "aster": 0.002,  # 0.2% (CEX-style, tight spreads)
        "drift": 0.005,  # 0.5% (Solana perps)
        "jupiter": 0.008,  # 0.8% (DEX, slippage)
        "hyperliquid": 0.003,  # 0.3% (L1 perps)
        "symphony": 0.006,  # 0.6% (EVM chains)
        "lighter": 0.010,  # 1.0% (L2 DEX, higher slippage)
    }

    # Decision thresholds
    FULL_SWITCH_THRESHOLD = 0.02  # 2% net benefit
    PARTIAL_SWITCH_THRESHOLD = 0.005  # 0.5% net benefit

    def __init__(self):
        """Initialize opportunity cost analyzer"""
        self.analysis_count = 0
        self.switch_count = 0
        self.partial_switch_count = 0
        self.hold_count = 0

        logger.info("📊 OpportunityCostAnalyzer initialized")

    def get_platform_cost(self, platform: str) -> float:
        """Get trading cost for platform (slippage + fees)"""
        return self.PLATFORM_COSTS.get(platform.lower(), 0.005)  # Default 0.5%

    def calculate_switching_cost(
        self,
        current_platform: str,
        new_platform: str
    ) -> float:
        """
        Calculate cost of switching positions

        Cost = exit_cost + entry_cost

        Args:
            current_platform: Platform of current position
            new_platform: Platform of new signal

        Returns:
            Total switching cost as decimal (e.g., 0.01 for 1%)
        """
        exit_cost = self.get_platform_cost(current_platform)
        entry_cost = self.get_platform_cost(new_platform)
        total_cost = exit_cost + entry_cost

        logger.debug(
            f"Switching cost: {current_platform} ({exit_cost:.2%}) → "
            f"{new_platform} ({entry_cost:.2%}) = {total_cost:.2%}"
        )

        return total_cost

    def estimate_remaining_upside(
        self,
        position: Position
    ) -> tuple[float, float]:
        """
        Estimate remaining upside and probability for current position

        Returns:
            (potential_gain_pct, win_probability) tuple
        """
        # Calculate distance to take profit
        if position.side.upper() == "LONG":
            upside = (position.take_profit - position.current_price) / position.current_price
        else:
            upside = (position.current_price - position.take_profit) / position.current_price

        # Already hit TP or past TP
        if upside <= 0:
            return 0.0, 0.0

        # Estimate win probability based on:
        # 1. Original confidence
        # 2. Current P&L (positions in profit more likely to continue)
        # 3. Distance remaining
        base_prob = position.confidence

        # Adjust for current P&L
        if position.unrealized_pnl_pct > 0.05:  # > 5% profit
            pnl_adj = 1.2  # Boost probability for winners
        elif position.unrealized_pnl_pct > 0.02:  # > 2% profit
            pnl_adj = 1.1
        elif position.unrealized_pnl_pct < -0.05:  # > 5% loss
            pnl_adj = 0.7  # Reduce probability for losers
        elif position.unrealized_pnl_pct < -0.02:  # > 2% loss
            pnl_adj = 0.85
        else:
            pnl_adj = 1.0

        # Adjust for distance remaining (farther = less likely)
        if upside > 0.10:  # > 10% remaining
            distance_adj = 0.8
        elif upside > 0.05:  # > 5% remaining
            distance_adj = 0.9
        else:
            distance_adj = 1.0

        win_prob = base_prob * pnl_adj * distance_adj
        win_prob = max(0.1, min(0.95, win_prob))  # Clamp to 10-95%

        return upside, win_prob

    def estimate_downside_risk(
        self,
        position: Position
    ) -> tuple[float, float]:
        """
        Estimate downside risk for current position

        Returns:
            (potential_loss_pct, loss_probability) tuple
        """
        # Calculate distance to stop loss
        if position.side.upper() == "LONG":
            downside = (position.current_price - position.stop_loss) / position.current_price
        else:
            downside = (position.stop_loss - position.current_price) / position.current_price

        # Already hit SL
        if downside <= 0:
            return 0.05, 0.95  # Near-certain loss

        # Loss probability is inverse of win probability
        _, win_prob = self.estimate_remaining_upside(position)
        loss_prob = 1.0 - win_prob

        return downside, loss_prob

    def calculate_current_position_ev(
        self,
        position: Position
    ) -> tuple[float, Dict[str, float]]:
        """
        Calculate expected value (EV) of current position

        EV = P(win) × remaining_upside - P(loss) × potential_loss

        Returns:
            (ev, details_dict) tuple
        """
        upside, win_prob = self.estimate_remaining_upside(position)
        downside, loss_prob = self.estimate_downside_risk(position)

        ev = (win_prob * upside) - (loss_prob * downside)

        details = {
            "upside_pct": upside,
            "downside_pct": downside,
            "win_prob": win_prob,
            "loss_prob": loss_prob,
            "ev": ev,
        }

        logger.debug(
            f"Current position EV: {ev:.2%} | "
            f"Upside: {upside:.2%} @ {win_prob:.1%} | "
            f"Downside: {downside:.2%} @ {loss_prob:.1%}"
        )

        return ev, details

    def calculate_new_signal_ev(
        self,
        signal: NewSignal
    ) -> tuple[float, Dict[str, float]]:
        """
        Calculate expected value (EV) of new signal

        EV = P(win) × potential_gain - P(loss) × potential_loss

        Returns:
            (ev, details_dict) tuple
        """
        # Calculate potential gain and loss
        if signal.side.upper() == "LONG":
            gain = (signal.target_price - signal.current_price) / signal.current_price
            loss = (signal.current_price - signal.stop_loss) / signal.current_price
        else:
            gain = (signal.current_price - signal.target_price) / signal.current_price
            loss = (signal.stop_loss - signal.current_price) / signal.current_price

        # Win probability from signal confidence and strength
        win_prob = signal.confidence * signal.signal_strength
        win_prob = max(0.1, min(0.95, win_prob))

        loss_prob = 1.0 - win_prob

        ev = (win_prob * gain) - (loss_prob * loss)

        details = {
            "gain_pct": gain,
            "loss_pct": loss,
            "win_prob": win_prob,
            "loss_prob": loss_prob,
            "ev": ev,
        }

        logger.debug(
            f"New signal EV: {ev:.2%} | "
            f"Gain: {gain:.2%} @ {win_prob:.1%} | "
            f"Loss: {loss:.2%} @ {loss_prob:.1%}"
        )

        return ev, details

    def should_switch_position(
        self,
        current_position: Position,
        new_signal: NewSignal,
        current_platform: str = "drift",
        new_platform: str = "drift"
    ) -> OpportunityCostAnalysis:
        """
        Analyze whether to switch from current position to new signal

        Decision logic:
        1. Calculate EV of current position
        2. Calculate EV of new signal
        3. Calculate switching cost
        4. Compare: net_benefit = new_ev - current_ev - switching_cost
        5. Decision:
           - net_benefit > 2%: SWITCH
           - net_benefit 0.5-2%: PARTIAL_SWITCH
           - net_benefit < 0.5%: HOLD

        Args:
            current_position: Current position details
            new_signal: New trading signal
            current_platform: Platform of current position
            new_platform: Platform of new signal

        Returns:
            OpportunityCostAnalysis with decision and reasoning
        """
        self.analysis_count += 1

        # Calculate EVs
        current_ev, current_details = self.calculate_current_position_ev(current_position)
        new_ev, new_details = self.calculate_new_signal_ev(new_signal)

        # Calculate switching cost
        switching_cost = self.calculate_switching_cost(current_platform, new_platform)

        # Calculate net benefit
        net_benefit = new_ev - current_ev - switching_cost

        # Make decision
        if net_benefit >= self.FULL_SWITCH_THRESHOLD:
            decision = SwitchingDecision.SWITCH
            self.switch_count += 1
            reasoning = (
                f"SWITCH: Net benefit {net_benefit:.2%} exceeds threshold {self.FULL_SWITCH_THRESHOLD:.1%} | "
                f"Current EV: {current_ev:.2%} → New EV: {new_ev:.2%} | "
                f"Cost: {switching_cost:.2%}"
            )
        elif net_benefit >= self.PARTIAL_SWITCH_THRESHOLD:
            decision = SwitchingDecision.PARTIAL_SWITCH
            self.partial_switch_count += 1
            reasoning = (
                f"PARTIAL_SWITCH: Net benefit {net_benefit:.2%} between thresholds | "
                f"Exit 50% current, enter 50% new | "
                f"Current EV: {current_ev:.2%} → New EV: {new_ev:.2%} | "
                f"Cost: {switching_cost:.2%}"
            )
        else:
            decision = SwitchingDecision.HOLD
            self.hold_count += 1
            reasoning = (
                f"HOLD: Net benefit {net_benefit:.2%} below threshold {self.PARTIAL_SWITCH_THRESHOLD:.1%} | "
                f"Insufficient advantage to justify switch | "
                f"Current EV: {current_ev:.2%} | New EV: {new_ev:.2%}"
            )

        logger.info(f"🔄 {reasoning}")

        # Calculate confidence in decision
        confidence = min(abs(net_benefit) * 10, 1.0)  # Higher net benefit = higher confidence

        return OpportunityCostAnalysis(
            decision=decision,
            current_ev=current_ev,
            new_ev=new_ev,
            switching_cost=switching_cost,
            net_benefit=net_benefit,
            reasoning=reasoning,
            confidence=confidence,
            current_position_upside=current_details["upside_pct"],
            current_position_downside=current_details["downside_pct"],
            new_signal_upside=new_details["gain_pct"],
            new_signal_downside=new_details["loss_pct"],
        )

    def get_stats(self) -> Dict[str, Any]:
        """Get analyzer statistics"""
        return {
            "total_analyses": self.analysis_count,
            "switches": self.switch_count,
            "partial_switches": self.partial_switch_count,
            "holds": self.hold_count,
            "switch_rate": (
                (self.switch_count + self.partial_switch_count) / max(1, self.analysis_count)
            ),
        }
