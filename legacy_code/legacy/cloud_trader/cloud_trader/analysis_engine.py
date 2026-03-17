import logging
import random
from typing import Any, Dict, Optional

from .definitions import SYMBOL_CONFIG, MinimalAgentState

# PvP Counter-Retail Strategy
try:
    from .pvp_strategies import get_counter_retail_strategy

    PVP_AVAILABLE = True
except Exception:
    PVP_AVAILABLE = False

logger = logging.getLogger(__name__)


class AnalysisEngine:
    def __init__(self, exchange_client, feature_pipeline, swarm_manager, grok_manager=None):
        self.exchange_client = exchange_client
        self.feature_pipeline = feature_pipeline
        self.swarm_manager = swarm_manager
        self.grok_manager = grok_manager

    async def analyze_market(
        self, agent: MinimalAgentState, symbol: str, ticker_map: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Perform basic technical analysis suited to the agent's specialization.
        Returns a dict with 'signal' ('BUY', 'SELL', 'NEUTRAL'), 'confidence', and 'thesis'.

        Uses agent.type for matching:
        - 'momentum' → Trend/momentum strategy
        - 'market_maker' → Mean reversion strategy
        - 'swing' → Swing trading strategy
        """
        print(f"DEBUG: AnalysisEngine analyzing {symbol} for {agent.id}")
        try:
            # 1. Fetch market data
            if ticker_map and symbol in ticker_map:
                ticker = ticker_map[symbol]
            else:
                ticker = await self.exchange_client.get_ticker(symbol)

            if not ticker:
                return {"signal": "NEUTRAL", "confidence": 0.0, "thesis": "No data available"}

            # ENHANCED: Fetch advanced TA data if available
            ta_analysis = await self.feature_pipeline.get_market_analysis(symbol)

            # ENHANCED: Get Swarm Context
            swarm_context = self.swarm_manager.get_swarm_context(agent.id, symbol)

            price = float(ticker.get("lastPrice", 0))
            price_change_pct = float(ticker.get("priceChangePercent", 0))
            high_24h = float(ticker.get("highPrice", 0))
            low_24h = float(ticker.get("lowPrice", 0))
            volume = float(ticker.get("volume", 0))

            if price == 0:
                return {"signal": "NEUTRAL", "confidence": 0.0, "thesis": "Invalid price data"}

            # 2. Derived Indicators
            is_uptrend = price_change_pct > 0
            rsi = 50.0
            bid_pressure = 0.5
            spread_pct = 0.0

            if ta_analysis:
                is_uptrend = ta_analysis.get("trend") == "BULLISH"
                rsi = ta_analysis.get("rsi", 50.0)
                bid_pressure = ta_analysis.get("bid_pressure", 0.5)
                spread_pct = ta_analysis.get("spread_pct", 0.0)

            is_volatile = (high_24h - low_24h) / price > 0.05
            if ta_analysis:
                is_volatile = ta_analysis.get("volatility_state") == "HIGH"

            # Position in daily range (0 = at low, 1 = at high)
            range_pos = (price - low_24h) / (high_24h - low_24h + 0.00001)
            near_support = range_pos < 0.25
            near_resistance = range_pos > 0.75

            # Trend strength (0-1 scale, based on 24h change)
            trend_strength = min(abs(price_change_pct) / 3.0, 1.0)

            # Volatility score (0-1 scale)
            volatility_score = min((high_24h - low_24h) / price / 0.10, 1.0)

            # 3. Agent-Specific Logic using agent.type
            signal = "NEUTRAL"
            confidence = 0.0
            thesis_parts = []
            agent_type = getattr(agent, "type", "general")

            # ═══════════════════════════════════════════════════════════════
            # MOMENTUM AGENT: Trend following, likes strong directional moves
            # ═══════════════════════════════════════════════════════════════
            if agent_type == "momentum":
                # Base confidence starts at 0.65 for actionable signals
                base_conf = 0.65 + (trend_strength * 0.25)  # 0.65 to 0.90

                if abs(price_change_pct) > 1.5:  # Significant 24h move
                    if is_uptrend:
                        if rsi < 75:  # Not overbought
                            signal = "BUY"
                            confidence = base_conf
                            thesis_parts.append(
                                f"Strong uptrend +{price_change_pct:.1f}%. Momentum BUY."
                            )
                        else:
                            thesis_parts.append(f"Uptrend but RSI Overbought ({rsi:.0f}). Waiting.")
                    else:
                        if rsi > 25:  # Not oversold
                            signal = "SELL"
                            confidence = base_conf
                            thesis_parts.append(
                                f"Strong downtrend {price_change_pct:.1f}%. Momentum SELL."
                            )
                        else:
                            thesis_parts.append(f"Downtrend but RSI Oversold ({rsi:.0f}). Waiting.")

                elif abs(price_change_pct) > 0.5:  # Moderate move
                    if is_uptrend and rsi < 70:
                        signal = "BUY"
                        confidence = base_conf * 0.9
                        thesis_parts.append(f"Moderate uptrend +{price_change_pct:.1f}%.")
                    elif not is_uptrend and rsi > 30:
                        signal = "SELL"
                        confidence = base_conf * 0.9
                        thesis_parts.append(f"Moderate downtrend {price_change_pct:.1f}%.")

                # Order Flow Confirmation
                if signal == "BUY" and bid_pressure > 0.55:
                    confidence *= 1.1
                    thesis_parts.append(f"Order Flow Bullish (Bid Press: {bid_pressure:.2f}).")
                elif signal == "SELL" and bid_pressure < 0.45:
                    confidence *= 1.1
                    thesis_parts.append(f"Order Flow Bearish (Bid Press: {bid_pressure:.2f}).")

            # ═══════════════════════════════════════════════════════════════
            # MARKET MAKER AGENT: Mean reversion, likes range-bound markets
            # ═══════════════════════════════════════════════════════════════
            elif agent_type == "market_maker":
                base_conf = 0.65 + (volatility_score * 0.20)  # 0.65 to 0.85

                # Market Makers hate wide spreads (takers) or love them (makers).
                # Since we TAKE liquidity via API key usually, we prefer tight spreads.
                if spread_pct > 0.002:  # >0.2% spread is expensive
                    base_conf *= 0.8
                    thesis_parts.append(f"⚠️ High Spread ({spread_pct:.2%}). Reducing size.")

                if near_support or rsi < 35:  # Oversold - expect bounce
                    signal = "BUY"
                    confidence = base_conf
                    if rsi < 30:
                        confidence *= 1.1
                    thesis_parts.append(
                        f"Price Support/Oversold (RSI {rsi:.0f}). Mean Reversion BUY."
                    )

                elif near_resistance or rsi > 65:  # Overbought - expect pullback
                    signal = "SELL"
                    confidence = base_conf
                    if rsi > 70:
                        confidence *= 1.1
                    thesis_parts.append(
                        f"Price Resistance/Overbought (RSI {rsi:.0f}). Mean Reversion SELL."
                    )

                # Order Book Imbalance acts as magnet? or simplified pressure?
                # If heavy buying pressure (bids) at support -> Stronger Buy
                if signal == "BUY" and bid_pressure > 0.60:
                    confidence *= 1.15
                    thesis_parts.append(f"Strong Bid Wall (Pressure {bid_pressure:.2f}).")
                elif signal == "SELL" and bid_pressure < 0.40:
                    confidence *= 1.15
                    thesis_parts.append(f"Strong Ask Wall (Pressure {bid_pressure:.2f}).")

            # ═══════════════════════════════════════════════════════════════
            # SWING AGENT: Looks for multi-day trend reversals and continuations
            # ═══════════════════════════════════════════════════════════════
            elif agent_type == "swing":
                base_conf = 0.65 + (trend_strength * 0.20)  # 0.65 to 0.85

                # Swing traders like buying dips in uptrends, selling rallies in downtrends
                if is_uptrend:
                    if rsi < 45:  # Dip
                        signal = "BUY"
                        confidence = base_conf * 1.1
                        thesis_parts.append(f"Uptrend with RSI Dip ({rsi:.0f}). Swing BUY.")
                    elif rsi > 75:  # Exhaustion?
                        # Maybe take profit logic elsewhere, but don't enter new long
                        pass
                    else:
                        signal = "BUY"
                        confidence = base_conf
                        thesis_parts.append(f"Established uptrend continuation.")

                else:  # Downtrend
                    if rsi > 55:  # Rally
                        signal = "SELL"
                        confidence = base_conf * 1.1
                        thesis_parts.append(f"Downtrend with RSI Rally ({rsi:.0f}). Swing SELL.")
                    elif rsi < 25:
                        pass  # Don't sell into hole
                    else:
                        signal = "SELL"
                        confidence = base_conf
                        thesis_parts.append(f"Established downtrend continuation.")

            # ═══════════════════════════════════════════════════════════════
            # DEFAULT/GENERAL: Simple trend following
            # ═══════════════════════════════════════════════════════════════
            else:
                base_conf = 0.65 + (trend_strength * 0.20)
                if is_uptrend and rsi < 70:
                    signal = "BUY"
                    confidence = base_conf
                    thesis_parts.append(f"General trend: Uptrend +{price_change_pct:.1f}%.")
                elif not is_uptrend and rsi > 30:
                    signal = "SELL"
                    confidence = base_conf
                    thesis_parts.append(f"General trend: Downtrend {price_change_pct:.1f}%.")

            # ═══════════════════════════════════════════════════════════════
            # HIGHER TIMEFRAME CONFLUENCE FILTER (Anti-Manipulation)
            # 4H trend is the "truth" - short-term is noise/manipulation
            # ═══════════════════════════════════════════════════════════════
            try:
                # Get 4H klines for higher timeframe trend
                # OPTIMIZED: Use feature_pipeline for caching/prefetching
                df_4h = await self.feature_pipeline.fetch_candles(symbol, interval="4h", limit=10)
                if df_4h is not None and not df_4h.empty:
                    # Simple 4H trend: compare current close to 5-period SMA
                    closes_4h = df_4h["close"].tail(5).tolist()
                    sma_4h = sum(closes_4h) / len(closes_4h)
                    current_4h_close = closes_4h[-1]

                    higher_tf_bullish = current_4h_close > sma_4h
                    higher_tf_bearish = current_4h_close < sma_4h

                    # CONFLUENCE BOOST: Same direction as 4H trend
                    if signal == "BUY" and higher_tf_bullish:
                        confidence *= 1.15  # 15% boost for alignment
                        thesis_parts.append("4H trend aligned (bullish).")
                    elif signal == "SELL" and higher_tf_bearish:
                        confidence *= 1.15
                        thesis_parts.append("4H trend aligned (bearish).")
                    # CONFLICT PENALTY: Opposite to 4H trend (possible trap)
                    elif signal == "BUY" and higher_tf_bearish:
                        confidence *= 0.70  # 30% penalty - potential trap
                        thesis_parts.append("⚠️ 4H trend BEARISH - possible trap!")
                    elif signal == "SELL" and higher_tf_bullish:
                        confidence *= 0.70
                        thesis_parts.append("⚠️ 4H trend BULLISH - possible trap!")
            except Exception:
                # Silently continue if 4H data unavailable
                pass

            # ═══════════════════════════════════════════════════════════════
            # COUNTER-RETAIL STRATEGY (PvP Logic)
            # Retail traders enter at obvious TA levels - we wait for their
            # capitulation before entering
            # ═══════════════════════════════════════════════════════════════
            is_capitulation = False
            retail_trap_warning = False

            if PVP_AVAILABLE and ta_analysis:
                try:
                    # rsi already extracted

                    if rsi is not None:
                        counter_retail = get_counter_retail_strategy()
                        retail_signal = counter_retail.analyze_retail_trap(
                            symbol=symbol,
                            rsi=rsi,
                            price_change_24h=price_change_pct,
                            range_position=range_pos,
                        )

                        if retail_signal:
                            if retail_signal.wait_for_capitulation:
                                # This is a TRAP zone - reduce confidence
                                confidence *= 0.6  # 40% penalty
                                retail_trap_warning = True
                                thesis_parts.append(f"⚠️ RETAIL TRAP: {retail_signal.reason}")
                            elif not retail_signal.wait_for_capitulation:
                                # CAPITULATION - boost confidence
                                bonus = counter_retail.get_capitulation_bonus(rsi)
                                confidence *= bonus
                                is_capitulation = True
                                thesis_parts.append(f"🎯 CAPITULATION: {retail_signal.reason}")
                                # Override signal if capitulation gives direction
                                if retail_signal.counter_direction in ("LONG", "SHORT"):
                                    signal = (
                                        "BUY"
                                        if retail_signal.counter_direction == "LONG"
                                        else "SELL"
                                    )
                except Exception as cre:
                    # Silently continue if counter-retail fails
                    pass

            # ═══════════════════════════════════════════════════════════════
            # USER BULLISH BIAS (Custom Priority)
            # ═══════════════════════════════════════════════════════════════
            BULLISH_ASSETS = {
                "BTCUSDT",
                "ETHUSDT",
                "SOLUSDT",
                "ZECUSDT",
                "ASTERUSDT",
                "PENGUUSDT",
                "HYPEUSDT",
            }
            if symbol in BULLISH_ASSETS and signal == "BUY":
                confidence *= 1.25  # 25% boost for user-preferred bullish assets
                thesis_parts.append(f"🌟 User Priority Bullish Asset: {symbol}.")
            elif symbol in BULLISH_ASSETS and signal == "SELL":
                confidence *= 0.85  # 15% reduction for selling user-preferred bullish assets (higher bar for shorts)
                thesis_parts.append(
                    f"⚠️ Counter-Bias: User is bullish on {symbol}. Shorting with caution."
                )

            # Add small randomization to avoid identical signals
            if confidence > 0.3:
                confidence += random.uniform(-0.02, 0.02)
                confidence = max(0.1, min(0.95, confidence))

            result = {
                "signal": signal,
                "confidence": confidence,
                "thesis": " ".join(thesis_parts),
            }

            # ═══════════════════════════════════════════════════════════════
            # LOGGING: Track all analysis results for debugging
            # ═══════════════════════════════════════════════════════════════
            log_level = logging.INFO if confidence >= 0.65 else logging.DEBUG
            logger.log(
                log_level,
                f"📊 SIGNAL: {agent.id} | {symbol} | {signal} | conf={confidence:.2f} | "
                f"24h={price_change_pct:+.1f}% | range_pos={range_pos:.0%} | "
                f"type={agent_type}",
            )

            # Print high-confidence signals prominently
            if confidence >= 0.65:
                print(f"🎯 HIGH CONF SIGNAL: {agent.id} → {symbol} {signal} ({confidence:.0%})")

            return result

        except Exception as e:
            print(f"⚠️ Analysis error for {symbol}: {e}")
            logger.error(f"Analysis error for {symbol}: {e}")
            return {"signal": "NEUTRAL", "confidence": 0.0, "thesis": f"Analysis failed: {str(e)}"}
