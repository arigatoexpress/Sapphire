import asyncio
import math
import statistics
from typing import Any, Dict, List, Optional, Tuple

from ..time_sync import get_precision_clock, get_timestamp_us

try:
    import numpy as np
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.preprocessing import StandardScaler

    ML_AVAILABLE = True
except ImportError:
    np = None
    RandomForestClassifier = None
    StandardScaler = None
    ML_AVAILABLE = False

from ..adaptive_position_sizing import AdaptivePositionSizer, RiskMetrics

# Import market regime, position sizing, and exit strategy types
from ..market_regime import MarketRegime, RegimeMetrics
from ..partial_exits import ExitSignal, PartialExitStrategy, PositionExitPlan


class VpinHFTAgent:
    def __init__(self, exchange_client: Any, pubsub_client: Any, risk_manager_topic: str):
        self.exchange_client = exchange_client
        self.pubsub_client = pubsub_client
        self.risk_manager_topic = risk_manager_topic
        self.vpin_threshold = 0.4  # Dynamic threshold, can be adjusted

        # ML-based trade classification
        self.ml_classifier = None
        self.scaler = None
        self.classification_history = []

        # Microstructure metrics
        self.quote_imbalance_history = []
        self.vpin_cdf_history = []
        self.volatility_measurements = []

        # Dynamic bucketing
        self.base_bucket_size = 1000  # Base volume bucket size
        self.volatility_multiplier = 1.0

    def calculate_vpin(self, tick_data_batch: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Calculates VPIN from tick data batch with microsecond-precision timing.
        VPIN = (sum(|Vbuy - Vsell|) / sum(Vbuy + Vsell)) * sqrt(N)
        - Vbuy/Vsell determined by tick direction (price change sign)
        - Rolling window calculation for real-time processing
        - Returns VPIN value with timing metadata
        """
        if len(tick_data_batch) < 10:
            return {
                "vpin": 0.0,
                "timestamp_us": get_timestamp_us(),
                "samples": len(tick_data_batch),
                "confidence": 0.0,
            }

        buy_volume = 0.0
        sell_volume = 0.0
        total_volume = 0.0
        microsecond_deltas = []

        for tick in tick_data_batch:
            price_change = tick["price"] - tick.get("prev_price", tick["price"])
            volume = tick.get("volume", 0.0)
            total_volume += volume

            # Track microsecond timing precision
            if "timestamp_us" in tick:
                microsecond_deltas.append(tick["timestamp_us"])

            if price_change > 0:
                buy_volume += volume
            elif price_change < 0:
                sell_volume += volume
            else:
                # Neutral tick, split volume
                buy_volume += volume / 2
                sell_volume += volume / 2

        if total_volume == 0:
            return {
                "vpin": 0.0,
                "timestamp_us": get_timestamp_us(),
                "samples": len(tick_data_batch),
                "confidence": 0.0,
            }

        volume_imbalance = abs(buy_volume - sell_volume)
        vpin = (volume_imbalance / total_volume) * math.sqrt(len(tick_data_batch))

        # Calculate confidence based on timing precision and sample size
        timing_precision = (
            len(microsecond_deltas) / len(tick_data_batch) if microsecond_deltas else 0
        )
        confidence = min(1.0, (len(tick_data_batch) / 50.0) * timing_precision)

        return {
            "vpin": min(vpin, 1.0),  # Cap at 1.0
            "timestamp_us": get_timestamp_us(),
            "samples": len(tick_data_batch),
            "confidence": confidence,
            "buy_volume": buy_volume,
            "sell_volume": sell_volume,
            "timing_precision": timing_precision,
        }

    def ml_classify_trade_direction(
        self, tick: Dict[str, Any], market_context: Dict[str, Any]
    ) -> int:
        """
        ML-based trade direction classification using neural network approach.
        Returns: 1 for buy, -1 for sell, 0 for neutral
        """
        if not ML_AVAILABLE or not self.ml_classifier:
            # Fallback to basic classification
            return self._basic_trade_classification(tick)

        try:
            # Extract features for ML classification
            features = self._extract_trade_features(tick, market_context)
            features_scaled = self.scaler.transform([features])
            prediction = self.ml_classifier.predict(features_scaled)[0]

            # Store for training feedback
            self.classification_history.append(
                {
                    "features": features,
                    "prediction": prediction,
                    "actual": tick.get("direction", 0),  # Ground truth if available
                    "timestamp": get_timestamp_us(),
                }
            )

            return int(prediction)

        except Exception as e:
            # Fallback on error
            return self._basic_trade_classification(tick)

    def _basic_trade_classification(self, tick: Dict[str, Any]) -> int:
        """Basic rule-based trade classification."""
        price_change = tick.get("price", 0) - tick.get("prev_price", tick.get("price", 0))
        volume = tick.get("volume", 0)

        if abs(price_change) < 0.0001:  # Neutral tick
            return 0
        elif price_change > 0:
            return 1  # Buy
        else:
            return -1  # Sell

    def _extract_trade_features(
        self, tick: Dict[str, Any], market_context: Dict[str, Any]
    ) -> List[float]:
        """Extract features for ML classification."""
        return [
            tick.get("price", 0),
            tick.get("volume", 0),
            tick.get("price", 0) - tick.get("prev_price", tick.get("price", 0)),  # Price change
            market_context.get("bid_ask_spread", 0),
            market_context.get("order_book_depth", 0),
            market_context.get("recent_volatility", 0),
            tick.get("timestamp_us", 0) % 86400000000,  # Time of day in microseconds
        ]

    def calculate_quote_imbalance(self, order_book: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate Quote Imbalance metric.
        QI = (BidVolume - AskVolume) / (BidVolume + AskVolume)
        """
        bid_volume = sum(
            level["volume"] for level in order_book.get("bids", [])[:5]
        )  # Top 5 levels
        ask_volume = sum(level["volume"] for level in order_book.get("asks", [])[:5])

        total_volume = bid_volume + ask_volume
        if total_volume == 0:
            imbalance = 0.0
        else:
            imbalance = (bid_volume - ask_volume) / total_volume

        # Calculate z-score
        self.quote_imbalance_history.append(imbalance)
        if len(self.quote_imbalance_history) > 100:
            self.quote_imbalance_history = self.quote_imbalance_history[-100:]

        if len(self.quote_imbalance_history) >= 10:
            mean = statistics.mean(self.quote_imbalance_history)
            stdev = (
                statistics.stdev(self.quote_imbalance_history)
                if len(self.quote_imbalance_history) > 1
                else 1.0
            )
            z_score = (imbalance - mean) / stdev if stdev > 0 else 0.0
        else:
            z_score = 0.0

        return {
            "quote_imbalance": imbalance,
            "z_score": z_score,
            "bid_volume": bid_volume,
            "ask_volume": ask_volume,
            "timestamp_us": get_timestamp_us(),
        }

    def calculate_vpin_cdf(self, vpin_value: float) -> Dict[str, Any]:
        """
        Calculate VPIN Cumulative Distribution Function and z-score.
        """
        self.vpin_cdf_history.append(vpin_value)
        if len(self.vpin_cdf_history) > 200:
            self.vpin_cdf_history = self.vpin_cdf_history[-200:]

        if len(self.vpin_cdf_history) < 10:
            return {
                "cdf": 0.5,
                "z_score": 0.0,
                "percentile": 50.0,
                "timestamp_us": get_timestamp_us(),
            }

        # Calculate empirical CDF
        sorted_values = sorted(self.vpin_cdf_history)
        cdf_value = sum(1 for x in sorted_values if x <= vpin_value) / len(sorted_values)

        # Calculate z-score
        mean = statistics.mean(self.vpin_cdf_history)
        stdev = statistics.stdev(self.vpin_cdf_history) if len(self.vpin_cdf_history) > 1 else 1.0
        z_score = (vpin_value - mean) / stdev if stdev > 0 else 0.0

        return {
            "cdf": cdf_value,
            "z_score": z_score,
            "percentile": cdf_value * 100,
            "mean": mean,
            "stdev": stdev,
            "timestamp_us": get_timestamp_us(),
        }

    def calculate_dynamic_bucket_size(self, volatility: float) -> int:
        """
        Calculate dynamic volume bucket size based on market volatility.
        Higher volatility = smaller buckets for more frequent signals.
        """
        # Update volatility measurements
        self.volatility_measurements.append(volatility)
        if len(self.volatility_measurements) > 50:
            self.volatility_measurements = self.volatility_measurements[-50:]

        if len(self.volatility_measurements) >= 5:
            avg_volatility = statistics.mean(self.volatility_measurements)
            # Scale bucket size inversely with volatility (more volatile = smaller buckets)
            self.volatility_multiplier = max(0.1, min(5.0, 1.0 / (avg_volatility + 0.1)))

        return int(self.base_bucket_size * self.volatility_multiplier)

    def generate_hybrid_signal(
        self,
        vpin_data: Dict[str, Any],
        quote_imbalance: Dict[str, Any],
        correlations: List[Dict[str, Any]],
        regime: Optional[RegimeMetrics] = None,
    ) -> Dict[str, Any]:
        """
        Generate hybrid trading signal using VPIN, Quote Imbalance, and cross-market correlations.
        Adapts thresholds based on market regime for optimal performance.
        """
        vpin_cdf = self.calculate_vpin_cdf(vpin_data["vpin"])

        # Calculate correlation score
        correlation_score = sum(corr.get("z_score", 0) for corr in correlations)

        # Adjust thresholds based on market regime
        buy_thresholds, sell_thresholds = self._get_regime_adjusted_thresholds(regime)

        # Regime-aware signal logic
        buy_signal = (
            vpin_cdf["z_score"] > buy_thresholds["vpin_z"]
            and quote_imbalance["z_score"] > buy_thresholds["qi_z"]
            and correlation_score > buy_thresholds["corr_sum"]
        )

        sell_signal = (
            vpin_cdf["z_score"] < sell_thresholds["vpin_z"]
            and quote_imbalance["z_score"] < sell_thresholds["qi_z"]
            and correlation_score < sell_thresholds["corr_sum"]
        )

        signal_strength = (
            abs(vpin_cdf["z_score"]) + abs(quote_imbalance["z_score"]) + abs(correlation_score)
        )

        # Adjust confidence based on regime stability
        regime_confidence_multiplier = 1.0
        if regime:
            if regime.regime in [MarketRegime.TRENDING_UP, MarketRegime.TRENDING_DOWN]:
                regime_confidence_multiplier = 1.2  # Higher confidence in trending markets
            elif regime.regime == MarketRegime.VOLATILE:
                regime_confidence_multiplier = 0.8  # Lower confidence in volatile markets
            elif regime.regime == MarketRegime.CALM:
                regime_confidence_multiplier = 1.1  # Slightly higher in calm markets

        confidence = min(1.0, signal_strength / 10.0 * regime_confidence_multiplier)

        return {
            "signal": 1 if buy_signal else (-1 if sell_signal else 0),
            "strength": signal_strength,
            "vpin_z": vpin_cdf["z_score"],
            "qi_z": quote_imbalance["z_score"],
            "corr_sum": correlation_score,
            "confidence": confidence,
            "regime": regime.regime.value if regime else "unknown",
            "regime_adjusted": True,
            "timestamp_us": get_timestamp_us(),
        }

    def _get_regime_adjusted_thresholds(
        self, regime: Optional[RegimeMetrics]
    ) -> Tuple[Dict[str, float], Dict[str, float]]:
        """Get regime-adjusted signal thresholds for optimal performance."""

        # Base thresholds
        base_buy_thresholds = {
            "vpin_z": 0.0,  # VPIN z-score for buy signals
            "qi_z": 1.5,  # Quote imbalance z-score
            "corr_sum": 4.0,  # Correlation sum
        }

        base_sell_thresholds = {
            "vpin_z": 0.0,  # VPIN z-score for sell signals
            "qi_z": -1.5,  # Quote imbalance z-score
            "corr_sum": -4.0,  # Correlation sum
        }

        if not regime:
            return base_buy_thresholds, base_sell_thresholds

        # Adjust thresholds based on market regime
        buy_thresholds = base_buy_thresholds.copy()
        sell_thresholds = base_sell_thresholds.copy()

        if regime.regime == MarketRegime.TRENDING_UP:
            # In uptrends, be more aggressive on buy signals, stricter on sell
            buy_thresholds["vpin_z"] = -0.5  # Allow slightly negative VPIN
            buy_thresholds["qi_z"] = 1.0  # Lower QI requirement
            sell_thresholds["vpin_z"] = 0.5  # Require stronger negative VPIN
            sell_thresholds["qi_z"] = -2.0  # More negative QI required

        elif regime.regime == MarketRegime.TRENDING_DOWN:
            # In downtrends, be more aggressive on sell signals, stricter on buy
            sell_thresholds["vpin_z"] = 0.5  # Allow slightly positive VPIN
            sell_thresholds["qi_z"] = -1.0  # Lower QI requirement (less negative)
            buy_thresholds["vpin_z"] = -0.5  # Require stronger negative VPIN
            buy_thresholds["qi_z"] = 2.0  # More positive QI required

        elif regime.regime == MarketRegime.VOLATILE:
            # In volatile markets, require stronger signals to avoid noise
            buy_thresholds["vpin_z"] = 0.5  # Stronger positive VPIN required
            buy_thresholds["qi_z"] = 2.0  # Stronger positive QI required
            buy_thresholds["corr_sum"] = 6.0  # Stronger correlation confirmation
            sell_thresholds["vpin_z"] = -0.5  # Stronger negative VPIN required
            sell_thresholds["qi_z"] = -2.0  # Stronger negative QI required
            sell_thresholds["corr_sum"] = -6.0  # Stronger correlation confirmation

        elif regime.regime == MarketRegime.CALM:
            # In calm markets, can be more responsive to smaller signals
            buy_thresholds["qi_z"] = 1.0  # Lower QI threshold
            buy_thresholds["corr_sum"] = 3.0  # Lower correlation requirement
            sell_thresholds["qi_z"] = -1.0  # Lower QI threshold (less negative)
            sell_thresholds["corr_sum"] = -3.0  # Lower correlation requirement

        elif regime.regime == MarketRegime.RANGING:
            # In ranging markets, balance signals and avoid over-trading
            buy_thresholds["corr_sum"] = 5.0  # Require stronger correlation confirmation
            sell_thresholds["corr_sum"] = -5.0  # Require stronger correlation confirmation

        return buy_thresholds, sell_thresholds

    async def calculate_adaptive_position_size(
        self,
        signal_data: Dict[str, Any],
        regime: Optional[RegimeMetrics],
        portfolio_metrics: Dict[str, Any],
        current_positions: List[Dict],
        symbol: str,
    ) -> Dict[str, Any]:
        """
        Calculate adaptive position size using comprehensive risk and regime analysis.

        This integrates Kelly Criterion, volatility targeting, regime awareness, and
        correlation risk adjustments for optimal position sizing.
        """

        try:
            from ..adaptive_position_sizing import get_adaptive_position_sizer

            position_sizer = await get_adaptive_position_sizer()

            # Convert portfolio metrics to RiskMetrics
            risk_metrics = RiskMetrics(
                portfolio_value=portfolio_metrics.get("portfolio_value", 100000),
                current_drawdown=portfolio_metrics.get("current_drawdown", 0.0),
                volatility_24h=portfolio_metrics.get("volatility_24h", 0.1),
                sharpe_ratio=portfolio_metrics.get("sharpe_ratio", 1.0),
                max_drawdown_limit=portfolio_metrics.get("max_drawdown_limit", 0.2),
                daily_pnl=portfolio_metrics.get("daily_pnl", 0.0),
                win_rate_24h=portfolio_metrics.get("win_rate_24h", 0.55),
                avg_win_loss_ratio=portfolio_metrics.get("avg_win_loss_ratio", 2.0),
            )

            # Get signal strength and confidence
            signal_strength = signal_data.get("strength", 5.0)
            confidence = signal_data.get("confidence", 0.7)

            # Calculate optimal position size
            sizing_result = position_sizer.calculate_position_size(
                signal_strength=signal_strength,
                confidence=confidence,
                regime=regime,
                risk_metrics=risk_metrics,
                current_positions=current_positions,
                symbol=symbol,
            )

            return sizing_result

        except Exception as e:
            # Fallback to simple regime-based sizing
            base_size = portfolio_metrics.get("base_position_size", 0.01)
            regime_adjusted_size = self.get_regime_based_position_size(regime, base_size)

            return {
                "recommended_size": regime_adjusted_size,
                "confidence_interval": (regime_adjusted_size * 0.8, regime_adjusted_size * 1.2),
                "risk_adjustment": 1.0,
                "regime_multiplier": regime_adjusted_size / base_size if base_size > 0 else 1.0,
                "reasoning": f"Fallback sizing due to error: {e}",
                "breakdown": {"error": str(e)},
            }

    def get_regime_based_position_size(
        self, regime: Optional[RegimeMetrics], base_position_size: float
    ) -> float:
        """Legacy method - kept for backward compatibility."""

        if not regime:
            return base_position_size

        multiplier = 1.0

        if regime.regime == MarketRegime.TRENDING_UP:
            multiplier = 1.2  # Increase position size in confirmed uptrends
        elif regime.regime == MarketRegime.TRENDING_DOWN:
            multiplier = 1.2  # Increase position size in confirmed downtrends
        elif regime.regime == MarketRegime.VOLATILE:
            multiplier = 0.7  # Reduce position size in volatile markets
        elif regime.regime == MarketRegime.CALM:
            multiplier = 1.1  # Slightly increase in calm markets (better execution)
        elif regime.regime == MarketRegime.RANGING:
            multiplier = 0.8  # Reduce position size in ranging markets

        # Also factor in regime confidence
        confidence_multiplier = 0.8 + (regime.confidence * 0.4)  # 0.8 to 1.2 range

        return base_position_size * multiplier * confidence_multiplier

    async def create_position_with_exit_plan(
        self,
        symbol: str,
        entry_price: float,
        position_size: float,
        side: str,
        signal_data: Dict[str, Any],
        regime: Optional[RegimeMetrics] = None,
        portfolio_metrics: Optional[Dict[str, Any]] = None,
        current_positions: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        """
        Create a complete position with entry and comprehensive exit plan.
        This integrates position sizing, entry execution, and exit strategy.
        """

        try:
            from ..partial_exits import get_partial_exit_strategy

            # Get optimal position size
            portfolio_metrics = portfolio_metrics or {}
            current_positions = current_positions or []

            sizing_result = await self.calculate_adaptive_position_size(
                signal_data, regime, portfolio_metrics, current_positions, symbol
            )

            optimal_size = sizing_result["recommended_size"]

            # Create exit plan
            exit_strategy = await get_partial_exit_strategy()
            exit_plan = exit_strategy.create_exit_plan(
                symbol=symbol,
                entry_price=entry_price,
                position_size=optimal_size,
                side=side,
                regime=regime,
            )

            # Execute entry trade
            entry_result = await self._execute_entry_trade(symbol, entry_price, optimal_size, side)

            if not entry_result["success"]:
                return {
                    "success": False,
                    "error": entry_result.get("error", "Entry execution failed"),
                    "position_size": optimal_size,
                    "exit_plan": exit_plan.to_dict(),
                }

            # Start monitoring the position
            await self._start_position_monitoring(symbol, exit_plan)

            return {
                "success": True,
                "symbol": symbol,
                "entry_price": entry_price,
                "position_size": optimal_size,
                "side": side,
                "exit_plan": exit_plan.to_dict(),
                "sizing_analysis": sizing_result,
                "entry_order_id": entry_result.get("order_id"),
            }

        except Exception as e:
            logger.error(f"Failed to create position with exit plan for {symbol}: {e}")
            return {"success": False, "error": str(e), "symbol": symbol}

    async def monitor_and_execute_exits(
        self, symbol: str, current_price: float
    ) -> List[Dict[str, Any]]:
        """
        Monitor position and execute any triggered exits.
        Returns list of executed exits.
        """

        try:
            from ..partial_exits import get_partial_exit_strategy

            exit_strategy = await get_partial_exit_strategy()

            # Check for exit signals
            exit_signals = exit_strategy.update_position_price(symbol, current_price)

            executed_exits = []

            # Execute each exit signal
            for exit_signal in exit_signals:
                execution_result = await self._execute_exit_trade(exit_signal)

                if execution_result["success"]:
                    # Confirm exit execution with strategy
                    exit_strategy.execute_exit(symbol, exit_signal)

                    executed_exits.append(
                        {
                            "exit_signal": {
                                "symbol": exit_signal.symbol,
                                "exit_size": exit_signal.exit_size,
                                "exit_price": exit_signal.exit_price,
                                "reason": exit_signal.reason,
                                "confidence": exit_signal.confidence,
                            },
                            "execution": execution_result,
                            "timestamp_us": get_timestamp_us(),
                        }
                    )

            # Check if position is fully closed
            position_status = exit_strategy.get_position_status(symbol)
            if position_status and not position_status["active"]:
                # Position fully closed
                executed_exits.append(
                    {
                        "type": "position_closed",
                        "symbol": symbol,
                        "final_status": position_status,
                        "timestamp_us": get_timestamp_us(),
                    }
                )

            return executed_exits

        except Exception as e:
            logger.error(f"Failed to monitor exits for {symbol}: {e}")
            return []

    async def get_position_management_status(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get comprehensive position management status including exits."""

        try:
            from ..partial_exits import get_partial_exit_strategy

            exit_strategy = await get_partial_exit_strategy()
            position_status = exit_strategy.get_position_status(symbol)

            if not position_status:
                return None

            # Add additional context
            return {
                "position_status": position_status,
                "exit_performance": self._analyze_exit_performance(symbol),
                "risk_metrics": await self._calculate_position_risk_metrics(symbol),
                "recommendations": self._generate_position_recommendations(position_status),
            }

        except Exception as e:
            logger.error(f"Failed to get position management status for {symbol}: {e}")
            return None

    async def force_position_close(
        self, symbol: str, close_price: Optional[float] = None, reason: str = "manual_close"
    ) -> bool:
        """Force close entire position with reason."""

        try:
            from ..partial_exits import get_partial_exit_strategy

            exit_strategy = await get_partial_exit_strategy()

            # Get current position status
            position_status = exit_strategy.get_position_status(symbol)
            if not position_status:
                return False

            # Execute close
            success = exit_strategy.close_position(symbol, close_price)

            if success:
                logger.info(f"Force closed position {symbol} for reason: {reason}")

                # Send notification
                await self._send_position_close_notification(symbol, position_status, reason)

            return success

        except Exception as e:
            logger.error(f"Failed to force close position {symbol}: {e}")
            return False

    def _analyze_exit_performance(self, symbol: str) -> Dict[str, Any]:
        """Analyze how well the exit strategy performed for this symbol."""

        # This would analyze historical exit performance
        # For now, return basic metrics
        return {
            "avg_time_to_first_exit": None,  # Would calculate from history
            "profit_targets_hit": None,  # Would track from history
            "trailing_stop_effectiveness": None,  # Would analyze from history
            "emergency_stop_usage": None,  # Would track from history
        }

    async def _calculate_position_risk_metrics(self, symbol: str) -> Dict[str, Any]:
        """Calculate real-time risk metrics for the position."""

        try:
            from ..trade_correlation import get_correlation_analyzer

            analyzer = await get_correlation_analyzer()
            risk_metrics = analyzer.get_symbol_correlation_risk(symbol)

            return risk_metrics

        except Exception:
            return {"correlation_risk": 0.0, "recommended_limit": 1.0}

    def _generate_position_recommendations(self, position_status: Dict) -> List[str]:
        """Generate position management recommendations."""

        recommendations = []

        remaining_size = position_status.get("remaining_size", 0)
        holding_time = position_status.get("holding_time_us", 0) / 1_000_000  # Convert to seconds

        if remaining_size > 0:
            if holding_time > 300:  # 5 minutes
                recommendations.append(
                    "Consider reducing position size due to extended holding time"
                )

            unrealized_pnl = position_status.get("unrealized_pnl", 0)
            if unrealized_pnl > 0:
                recommendations.append("Position is profitable - consider tightening trailing stop")

            next_targets = position_status.get("next_targets", [])
            if not next_targets:
                recommendations.append("All profit targets achieved - monitor for trailing stop")

        return recommendations

    async def _execute_entry_trade(
        self, symbol: str, price: float, size: float, side: str
    ) -> Dict[str, Any]:
        """Execute entry trade - simplified for this implementation."""

        # In a real implementation, this would interface with the exchange
        logger.info(f"Simulated entry trade: {side} {size} {symbol} at {price}")

        return {
            "success": True,
            "order_id": f"entry_{symbol}_{get_timestamp_us()}",
            "executed_price": price,
            "executed_size": size,
        }

    async def _execute_exit_trade(self, exit_signal: ExitSignal) -> Dict[str, Any]:
        """Execute exit trade - simplified for this implementation."""

        # In a real implementation, this would interface with the exchange
        logger.info(
            f"Simulated exit trade: {exit_signal.symbol} {exit_signal.exit_size} at {exit_signal.exit_price or 'market'} ({exit_signal.reason})"
        )

        return {
            "success": True,
            "order_id": f"exit_{exit_signal.symbol}_{get_timestamp_us()}",
            "executed_price": exit_signal.exit_price,
            "executed_size": exit_signal.exit_size,
            "reason": exit_signal.reason,
        }

    async def _start_position_monitoring(self, symbol: str, exit_plan: PositionExitPlan):
        """Start monitoring a position for exit signals."""

        # In a real implementation, this would start a background monitoring task
        logger.info(
            f"Started monitoring position {symbol} with {len(exit_plan.exit_levels)} exit levels"
        )

    async def _send_position_close_notification(
        self, symbol: str, position_status: Dict, reason: str
    ):
        """Send notification about position closure."""

        # In a real implementation, this would send Telegram alerts
        logger.info(
            f"Position {symbol} closed - Reason: {reason}, P&L: {position_status.get('total_pnl', 0):.2f}"
        )

    async def execute_trade(self, vpin_signal: float, symbol: str):
        """
        Executes a trade if the VPIN signal crosses a threshold.
        """
        if vpin_signal > self.vpin_threshold:
            # Execute aggressive 30x leverage trade
            # High VPIN signals order flow toxicity, often preceding reversals
            # For simplicity, we buy on high VPIN signals (fade the sell pressure)
            side = "BUY"

            try:
                # Get current price
                ticker = await self.exchange_client.get_ticker_price(symbol)
                price = float(ticker.get("price", 0))
                if price <= 0:
                    return

                # Calculate position size (30x leverage on $1000 notional)
                notional = 1000.0
                quantity = (notional * 30) / price  # 30x leverage

                # Place the order
                order = await self.exchange_client.place_order(
                    symbol=symbol,
                    side=side,
                    quantity=quantity,
                    price=price,
                    leverage=30,
                    order_type="MARKET",
                )

                print(
                    f"VPIN trade executed: {side} {quantity:.4f} {symbol} at ~${price:.4f} (VPIN: {vpin_signal:.4f})"
                )

                # Post position details to RiskManager via Pub/Sub
                position_details = {
                    "symbol": symbol,
                    "side": side,
                    "notional": notional,
                    "leverage": 30,
                    "vpin_signal": vpin_signal,
                    "source": "vpin-hft",
                    "order_id": order.get("orderId"),
                    "quantity": quantity,
                    "price": price,
                    "timestamp": asyncio.get_event_loop().time(),
                }
                await self.pubsub_client.publish(self.risk_manager_topic, position_details)

            except Exception as e:
                print(f"VPIN trade execution failed for {symbol}: {e}")
