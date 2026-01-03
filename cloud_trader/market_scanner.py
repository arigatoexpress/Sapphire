import asyncio
from dataclasses import dataclass
from typing import List, Optional

from .definitions import SYMPHONY_SYMBOLS
from .logger import get_logger

logger = get_logger(__name__)


@dataclass
class Opportunity:
    """Trading opportunity detected by the scanner."""

    symbol: str
    signal: str  # "BUY" | "SELL"
    confidence: float  # 0.0 to 1.0
    reason: str
    platform: str  # "symphony" | "aster"
    score: float  # For ranking
    price: float = 0.0  # Current price at detection


class MarketScanner:
    """Scans market for high-probability trading opportunities."""

    def __init__(self, feature_pipeline, market_data):
        self.feature_pipeline = feature_pipeline
        self.market_data = market_data

    async def scan(self, max_opportunities: int = 3) -> List[Opportunity]:
        """
        Scan all symbols and return top opportunities.

        Filters:
        - RSI extremes (< 30 or > 70)
        - Volume spikes (> 2x average)
        - Price near support/resistance

        Returns:
            List of opportunities sorted by score (descending)
        """
        opportunities = []

        # Get all tradable symbols - with fallback if market_data is missing
        symbols = []
        if self.market_data and hasattr(self.market_data, 'market_structure') and self.market_data.market_structure:
            symbols = list(self.market_data.market_structure.keys())
            logger.debug(f"🔍 Scanner using {len(symbols)} symbols from market_structure")
        else:
            # Fallback to curated list when market_data is not available
            from .definitions import SYMPHONY_SYMBOLS
            symbols = [
                "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
                "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT",
                "MATICUSDT", "UNIUSDT", "LTCUSDT", "ATOMUSDT", "NEARUSDT",
            ] + list(SYMPHONY_SYMBOLS)
            logger.info(f"⚠️ Scanner using {len(symbols)} fallback symbols (market_data unavailable)")

        if not symbols:
            logger.warning("🔍 No symbols available for scanning")
            return []

        semaphore = asyncio.Semaphore(4)  # Limit concurrency to 4 symbols at once (lower for stability)
        import sys
        
        async def safe_analyze(symbol):
            async with semaphore:
                print(f"🚀 [SCAN] Analyzing {symbol}...")
                sys.stdout.flush()
                try:
                    # Apply a generous timeout for the first run so it can populate the cache
                    return await asyncio.wait_for(self._analyze_symbol(symbol), timeout=60.0)
                except asyncio.TimeoutError:
                    print(f"⏳ [SCAN] Timeout analyzing {symbol} (>60s)")
                    return None
                except Exception as e:
                    print(f"❌ [SCAN] Error for {symbol}: {e}")
                    return None
                finally:
                    sys.stdout.flush()

        logger.info(f"🔍 [SCAN] Starting parallel scan of {len(symbols)} symbols (limit 10)...")
        tasks = [safe_analyze(symbol) for symbol in symbols]
        results = await asyncio.gather(*tasks)
        
        valid_results = [r for r in results if r]
        print(f"✅ [SCAN] Results found: {len(valid_results)} across {len(symbols)} symbols")
        sys.stdout.flush()

        # Filter out errors and None values
        success_count = 0
        error_count = 0
        for result in results:
            if isinstance(result, Opportunity):
                opportunities.append(result)
                success_count += 1
            elif isinstance(result, Exception):
                error_count += 1

        # Only log if there's interesting activity or every 10 mins
        if opportunities or error_count > 0:
            logger.info(f"🔎 Scan complete: {len(opportunities)} opportunities, {success_count} valid TAs, {error_count} errors across {len(symbols)} symbols")

        # Sort by score and return top N
        opportunities.sort(key=lambda x: x.score, reverse=True)
        return opportunities[:max_opportunities]

    async def _analyze_symbol(self, symbol: str) -> Optional[Opportunity]:
        """
        Analyze a single symbol using DYNAMIC COMPOSITE SCORING.
        """
        print(f"🔬 [_analyze_symbol] Starting {symbol}")
        import sys
        sys.stdout.flush()
        try:
            import random

            # Get technical analysis
            ta = await self.feature_pipeline.get_market_analysis(symbol)
            print(f"✅ [_analyze_symbol] Got TA for {symbol}")
            sys.stdout.flush()

            if not ta:
                return None

            # Extract all indicators
            rsi = ta.get("rsi", 50.0)
            trend = ta.get("trend", "NEUTRAL")
            volatility = ta.get("volatility_state", "LOW")
            macd_val = ta.get("macd_val", 0)
            macd_signal = ta.get("macd_signal", 0)
            macd_hist = ta.get("macd_hist", 0)
            stoch_k = ta.get("stoch_k", 50)
            stoch_d = ta.get("stoch_d", 50)
            bid_pressure = ta.get("bid_pressure", 0.5)  # Order book pressure
            adx = ta.get("adx", 20)  # Trend strength

            # Determine platform
            from .definitions import SYMPHONY_SYMBOLS
            platform = "symphony" if symbol in SYMPHONY_SYMBOLS else "aster"

            # ========== DYNAMIC COMPOSITE SCORING ==========
            # Each indicator contributes a score from -1 (strong sell) to +1 (strong buy)
            # Weights determine importance of each signal
            
            scores = {}
            
            # 1. RSI Score (weight: 0.25) - Mean reversion
            if rsi < 30:
                scores["rsi"] = 0.8 + (30 - rsi) / 30 * 0.2  # Stronger as more oversold
            elif rsi < 40:
                scores["rsi"] = 0.4  # Mild bullish
            elif rsi > 70:
                scores["rsi"] = -0.8 - (rsi - 70) / 30 * 0.2  # Stronger as more overbought
            elif rsi > 60:
                scores["rsi"] = -0.4  # Mild bearish
            else:
                scores["rsi"] = 0  # Neutral
            
            # 2. MACD Score (weight: 0.25) - Momentum
            if macd_hist != 0:
                macd_strength = min(abs(macd_hist) / 10, 1.0)  # Normalize
                if macd_val > macd_signal:
                    scores["macd"] = 0.5 + macd_strength * 0.5  # Bullish crossover
                else:
                    scores["macd"] = -0.5 - macd_strength * 0.5  # Bearish crossover
            else:
                scores["macd"] = 0
            
            # 3. Trend Score (weight: 0.20) - Direction
            if trend == "BULLISH":
                scores["trend"] = 0.6
            elif trend == "BEARISH":
                scores["trend"] = -0.6
            else:
                scores["trend"] = 0
            
            # 4. Stochastic Score (weight: 0.15) - Overbought/Oversold
            if stoch_k < 20:
                scores["stoch"] = 0.7
            elif stoch_k < 30:
                scores["stoch"] = 0.3
            elif stoch_k > 80:
                scores["stoch"] = -0.7
            elif stoch_k > 70:
                scores["stoch"] = -0.3
            else:
                scores["stoch"] = 0
            
            # 5. Order Book Pressure Score (weight: 0.15) - Volume imbalance
            if bid_pressure > 0.6:
                scores["orderbook"] = 0.5  # Buying pressure
            elif bid_pressure < 0.4:
                scores["orderbook"] = -0.5  # Selling pressure
            else:
                scores["orderbook"] = 0
            
            # ========== CALCULATE WEIGHTED COMPOSITE SCORE ==========
            weights = {
                "rsi": 0.25,
                "macd": 0.25,
                "trend": 0.20,
                "stoch": 0.15,
                "orderbook": 0.15,
            }
            
            composite_score = sum(scores[k] * weights[k] for k in scores)
            
            # ========== DIAGNOSTIC LOGGING (Elevated for visibility) ==========
            print(
                f"📊 [DIAG] {symbol}: RSI={rsi:.1f} MACD_h={macd_hist:.3f} trend={trend} "
                f"stoch={stoch_k:.0f} bid={bid_pressure:.2f} → composite={composite_score:.3f}"
            )
            sys.stdout.flush()
            
            # ========== GENERATE OPPORTUNITY IF THRESHOLD EXCEEDED ==========
            THRESHOLD = 0.10  # Lowered from 0.15 for more trades (Demo optimized)
            
            if abs(composite_score) >= THRESHOLD:
                # Determine signal direction
                signal = "BUY" if composite_score > 0 else "SELL"
                
                # Build reason from contributing factors
                contributing = [k for k, v in scores.items() if abs(v) > 0.2]
                reason = f"Composite: {composite_score:.2f} ({', '.join(contributing)})"
                
                # Confidence scales with score strength
                confidence = min(0.5 + abs(composite_score), 0.95)
                
                # Log opportunity found (Keep as print for visibility)
                print(f"🎯 [OPPORTUNITY] {symbol}: {signal} | score={composite_score:.3f} | reasons={contributing}")
                sys.stdout.flush()
                
                return Opportunity(
                    symbol=symbol,
                    signal=signal,
                    confidence=round(confidence, 2),
                    reason=reason,
                    platform=platform,
                    score=abs(composite_score),
                    price=ta.get("price", 0.0),
                )
            
            return None

        except Exception as e:
            print(f"❌ [_analyze_symbol] Error for {symbol}: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _calculate_score(self, rsi: float, trend: str, volatility: str, signal: str) -> float:
        """
        Calculate opportunity score for ranking.

        Higher score = better opportunity.
        """
        score = 0.5  # Base score

        # RSI extremes boost score
        if signal == "BUY":
            if rsi < 25:
                score += 0.3  # Very oversold
            elif rsi < 30:
                score += 0.2  # Oversold
        elif signal == "SELL":
            if rsi > 75:
                score += 0.3  # Very overbought
            elif rsi > 70:
                score += 0.2  # Overbought

        # Trend alignment
        if (signal == "BUY" and trend == "BULLISH") or (signal == "SELL" and trend == "BEARISH"):
            score += 0.2

        # Volatility penalty (avoid choppy markets)
        if volatility == "HIGH":
            score -= 0.1

        return max(0.0, min(1.0, score))
