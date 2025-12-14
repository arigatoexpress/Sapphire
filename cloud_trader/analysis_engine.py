import logging
import random
from typing import Any, Dict, Optional

from .definitions import SYMBOL_CONFIG, MinimalAgentState

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
            if ta_analysis:
                is_uptrend = ta_analysis.get("trend") == "BULLISH"

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
            agent_type = getattr(agent, 'type', 'general')

            # ═══════════════════════════════════════════════════════════════
            # MOMENTUM AGENT: Trend following, likes strong directional moves
            # ═══════════════════════════════════════════════════════════════
            if agent_type == "momentum":
                # Base confidence starts at 0.65 for actionable signals
                base_conf = 0.65 + (trend_strength * 0.25)  # 0.65 to 0.90
                
                if abs(price_change_pct) > 1.5:  # Significant 24h move
                    if is_uptrend:
                        signal = "BUY"
                        confidence = base_conf
                        thesis_parts.append(f"Strong uptrend +{price_change_pct:.1f}%. Momentum BUY.")
                    else:
                        signal = "SELL"
                        confidence = base_conf
                        thesis_parts.append(f"Strong downtrend {price_change_pct:.1f}%. Momentum SELL.")
                elif abs(price_change_pct) > 0.5:  # Moderate move
                    if is_uptrend:
                        signal = "BUY"
                        confidence = base_conf * 0.9  # Slightly lower for weaker trend
                        thesis_parts.append(f"Moderate uptrend +{price_change_pct:.1f}%.")
                    else:
                        signal = "SELL"
                        confidence = base_conf * 0.9
                        thesis_parts.append(f"Moderate downtrend {price_change_pct:.1f}%.")
                else:
                    signal = "NEUTRAL"
                    confidence = 0.40
                    thesis_parts.append(f"Weak momentum ({price_change_pct:.1f}%). Waiting for breakout.")

            # ═══════════════════════════════════════════════════════════════
            # MARKET MAKER AGENT: Mean reversion, likes range-bound markets
            # ═══════════════════════════════════════════════════════════════
            elif agent_type == "market_maker":
                base_conf = 0.65 + (volatility_score * 0.20)  # 0.65 to 0.85
                
                if near_support:  # Price near daily low - expect bounce
                    signal = "BUY"
                    confidence = base_conf
                    thesis_parts.append(f"Price at {range_pos:.0%} of daily range (near support). Mean reversion BUY.")
                elif near_resistance:  # Price near daily high - expect pullback
                    signal = "SELL"
                    confidence = base_conf
                    thesis_parts.append(f"Price at {range_pos:.0%} of daily range (near resistance). Mean reversion SELL.")
                else:  # Mid-range - still trade with lower confidence
                    if is_uptrend:
                        signal = "BUY"
                        confidence = base_conf * 0.85
                        thesis_parts.append(f"Mid-range but uptrend bias. Cautious BUY.")
                    else:
                        signal = "SELL"
                        confidence = base_conf * 0.85
                        thesis_parts.append(f"Mid-range but downtrend bias. Cautious SELL.")

            # ═══════════════════════════════════════════════════════════════
            # SWING AGENT: Looks for multi-day trend reversals and continuations
            # ═══════════════════════════════════════════════════════════════
            elif agent_type == "swing":
                base_conf = 0.65 + (trend_strength * 0.20)  # 0.65 to 0.85
                
                # Swing traders like buying dips in uptrends, selling rallies in downtrends
                if is_uptrend and near_support:  # Uptrend + dip = strong buy
                    signal = "BUY"
                    confidence = base_conf * 1.1  # Boost for confluence
                    thesis_parts.append(f"Uptrend with pullback to support. Swing BUY.")
                elif not is_uptrend and near_resistance:  # Downtrend + rally = strong sell
                    signal = "SELL"
                    confidence = base_conf * 1.1
                    thesis_parts.append(f"Downtrend with rally to resistance. Swing SELL.")
                elif is_uptrend:
                    signal = "BUY"
                    confidence = base_conf
                    thesis_parts.append(f"Established uptrend. Swing BUY.")
                else:
                    signal = "SELL"
                    confidence = base_conf
                    thesis_parts.append(f"Established downtrend. Swing SELL.")

            # ═══════════════════════════════════════════════════════════════
            # DEFAULT/GENERAL: Simple trend following
            # ═══════════════════════════════════════════════════════════════
            else:
                base_conf = 0.65 + (trend_strength * 0.20)
                if is_uptrend:
                    signal = "BUY"
                    confidence = base_conf
                    thesis_parts.append(f"General trend: Uptrend +{price_change_pct:.1f}%.")
                else:
                    signal = "SELL"
                    confidence = base_conf
                    thesis_parts.append(f"General trend: Downtrend {price_change_pct:.1f}%.")

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
            logger.log(log_level, 
                f"📊 SIGNAL: {agent.id} | {symbol} | {signal} | conf={confidence:.2f} | "
                f"24h={price_change_pct:+.1f}% | range_pos={range_pos:.0%} | "
                f"type={agent_type}"
            )
            
            # Print high-confidence signals prominently
            if confidence >= 0.65:
                print(f"🎯 HIGH CONF SIGNAL: {agent.id} → {symbol} {signal} ({confidence:.0%})")

            return result

        except Exception as e:
            print(f"⚠️ Analysis error for {symbol}: {e}")
            logger.error(f"Analysis error for {symbol}: {e}")
            return {"signal": "NEUTRAL", "confidence": 0.0, "thesis": f"Analysis failed: {str(e)}"}

