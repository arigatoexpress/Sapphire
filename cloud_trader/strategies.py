"""Multi-strategy trading system with momentum, mean reversion, arbitrage, and ML strategies."""
from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from decimal import Decimal

from .config import get_settings
from .strategy import MarketSnapshot
from .rl_strategies import RLStrategyManager
from .cache import get_cache, BaseCache

logger = logging.getLogger(__name__)


@dataclass
class StrategySignal:
    """Trading signal from a strategy."""
    strategy_name: str
    symbol: str
    direction: str  # BUY, SELL, HOLD
    confidence: float  # 0.0 to 1.0
    position_size: float  # Fraction of capital to allocate
    reasoning: str
    metadata: Dict[str, Any]


class TradingStrategy(ABC):
    """Abstract base class for trading strategies."""
    
    def __init__(self, name: str):
        self.name = name
        self.settings = get_settings()
        self._cache: Optional[BaseCache] = None
        
    async def get_cache(self) -> BaseCache:
        if self._cache is None:
            self._cache = await get_cache()
        return self._cache
        
    @abstractmethod
    async def evaluate(self, symbol: str, market_data: MarketSnapshot, 
                      historical_data: Optional[pd.DataFrame] = None) -> StrategySignal:
        """Evaluate trading opportunity for a symbol."""
        pass
    
    @abstractmethod
    def get_required_history(self) -> int:
        """Return number of historical candles required for strategy."""
        pass


class MomentumStrategy(TradingStrategy):
    """Momentum-based trading strategy."""
    
    def __init__(self, threshold: float = 0.3):
        super().__init__("Momentum")
        self.threshold = threshold  # 30% default threshold
        
    async def evaluate(self, symbol: str, market_data: MarketSnapshot, 
                      historical_data: Optional[pd.DataFrame] = None) -> StrategySignal:
        """Evaluate momentum signal based on 24h change."""
        change_24h = market_data.change_24h
        volume = market_data.volume
        
        # Enhanced momentum with volume confirmation
        volume_ma = market_data.volume  # Would need historical for proper MA
        volume_surge = volume > volume_ma * 1.5  # 50% above average
        
        if abs(change_24h) >= self.threshold * 100 and volume_surge:
            direction = "BUY" if change_24h > 0 else "SELL"
            confidence = min(abs(change_24h) / 100, 0.9)  # Cap at 90%
            
            # Position sizing based on momentum strength
            position_size = min(abs(change_24h) / 200, 0.02)  # Max 2% per trade
            
            return StrategySignal(
                strategy_name=self.name,
                symbol=symbol,
                direction=direction,
                confidence=confidence,
                position_size=position_size,
                reasoning=f"Strong {direction} momentum: {change_24h:.2f}% change with {volume:.2f}M volume",
                metadata={"change_24h": change_24h, "volume": volume}
            )
        
        return StrategySignal(
            strategy_name=self.name,
            symbol=symbol,
            direction="HOLD",
            confidence=0.0,
            position_size=0.0,
            reasoning=f"Insufficient momentum: {change_24h:.2f}% change",
            metadata={"change_24h": change_24h}
        )
    
    def get_required_history(self) -> int:
        return 24  # 24 hourly candles for daily momentum


class MeanReversionStrategy(TradingStrategy):
    """Mean reversion strategy using Bollinger Bands."""
    
    def __init__(self, bb_period: int = 20, bb_std: float = 2.0):
        super().__init__("MeanReversion")
        self.bb_period = bb_period
        self.bb_std = bb_std
        
    async def evaluate(self, symbol: str, market_data: MarketSnapshot, 
                      historical_data: Optional[pd.DataFrame] = None) -> StrategySignal:
        """Evaluate mean reversion signal using Bollinger Bands."""
        cache = await self.get_cache()
        cache_key = f"strategy:mean_reversion:bb:{symbol}"
        cached_bands = await cache.get(cache_key)

        if cached_bands:
            upper_band = cached_bands['upper']
            lower_band = cached_bands['lower']
            sma = cached_bands['sma']
        else:
            if historical_data is None or len(historical_data) < self.bb_period:
                return StrategySignal(
                    strategy_name=self.name,
                    symbol=symbol,
                    direction="HOLD",
                    confidence=0.0,
                    position_size=0.0,
                    reasoning="Insufficient historical data for BB calculation",
                    metadata={}
                )
            
            # Calculate Bollinger Bands
            closes = historical_data['close'].tail(self.bb_period)
            sma = closes.mean()
            std = closes.std()
            upper_band = sma + (self.bb_std * std)
            lower_band = sma - (self.bb_std * std)
            
            await cache.set(cache_key, {"upper": upper_band, "lower": lower_band, "sma": sma}, ttl=60)
        
        current_price = market_data.price
        
        # Check for mean reversion opportunities
        if current_price < lower_band:
            # Oversold - potential buy
            deviation = (sma - current_price) / sma
            confidence = min(deviation * 2, 0.8)  # Cap at 80%
            
            return StrategySignal(
                strategy_name=self.name,
                symbol=symbol,
                direction="BUY",
                confidence=confidence,
                position_size=min(deviation, 0.02),  # Max 2%
                reasoning=f"Price {deviation*100:.1f}% below BB lower band - oversold",
                metadata={"bb_lower": lower_band, "bb_upper": upper_band, "sma": sma}
            )
        
        elif current_price > upper_band:
            # Overbought - potential sell
            deviation = (current_price - sma) / sma
            confidence = min(deviation * 2, 0.8)
            
            return StrategySignal(
                strategy_name=self.name,
                symbol=symbol,
                direction="SELL",
                confidence=confidence,
                position_size=min(deviation, 0.02),
                reasoning=f"Price {deviation*100:.1f}% above BB upper band - overbought",
                metadata={"bb_lower": lower_band, "bb_upper": upper_band, "sma": sma}
            )
        
        return StrategySignal(
            strategy_name=self.name,
            symbol=symbol,
            direction="HOLD",
            confidence=0.0,
            position_size=0.0,
            reasoning="Price within Bollinger Bands - no signal",
            metadata={"bb_lower": lower_band, "bb_upper": upper_band, "sma": sma}
        )
    
    def get_required_history(self) -> int:
        return self.bb_period + 5  # Extra candles for stability


class ArbitrageStrategy(TradingStrategy):
    """Cross-market arbitrage detection strategy."""
    
    def __init__(self, min_spread: float = 0.002):
        super().__init__("Arbitrage")
        self.min_spread = min_spread  # 0.2% minimum profit
        
    async def evaluate(self, symbol: str, market_data: MarketSnapshot, 
                      historical_data: Optional[pd.DataFrame] = None) -> StrategySignal:
        """Detect arbitrage opportunities across markets or triangular paths."""
        # For now, simple implementation checking funding rates
        # In production, would check multiple exchanges/pairs
        
        # Simulate funding rate arbitrage for perpetual contracts
        # Positive funding = shorts pay longs (bearish sentiment)
        # Negative funding = longs pay shorts (bullish sentiment)
        
        # Mock funding rate (would fetch from API)
        funding_rate = np.random.uniform(-0.003, 0.003)
        
        if abs(funding_rate) > self.min_spread:
            if funding_rate > self.min_spread:
                # Positive funding - short perp, long spot (or just short)
                direction = "SELL"
                reasoning = f"Positive funding {funding_rate*100:.3f}% - shorts profitable"
            else:
                # Negative funding - long perp, short spot (or just long)
                direction = "BUY"
                reasoning = f"Negative funding {funding_rate*100:.3f}% - longs profitable"
            
            confidence = min(abs(funding_rate) / self.min_spread * 0.5, 0.9)
            position_size = min(abs(funding_rate) * 5, 0.01)  # Max 1% for arb
            
            return StrategySignal(
                strategy_name=self.name,
                symbol=symbol,
                direction=direction,
                confidence=confidence,
                position_size=position_size,
                reasoning=reasoning,
                metadata={"funding_rate": funding_rate, "type": "funding_arbitrage"}
            )
        
        return StrategySignal(
            strategy_name=self.name,
            symbol=symbol,
            direction="HOLD",
            confidence=0.0,
            position_size=0.0,
            reasoning="No arbitrage opportunity detected",
            metadata={"funding_rate": funding_rate}
        )
    
    def get_required_history(self) -> int:
        return 1  # Minimal history needed for arbitrage


class DQNStrategy(TradingStrategy):
    """Deep Q-Network reinforcement learning strategy."""
    
    def __init__(self, state_size: int = 10, action_size: int = 3, rl_manager: Optional[RLStrategyManager] = None):
        super().__init__("DQN")
        self.state_size = state_size
        self.action_size = action_size  # BUY, SELL, HOLD
        self.rl_manager = rl_manager
        
    async def evaluate(self, symbol: str, market_data: MarketSnapshot, 
                      historical_data: Optional[pd.DataFrame] = None) -> StrategySignal:
        """Evaluate using DQN model (simulated for MVP)."""
        cache = await self.get_cache()
        cache_key = f"strategy:dqn:state:{symbol}"
        cached_state = await cache.get(cache_key)

        if cached_state:
            state = np.array(cached_state)
        else:
            if historical_data is None or len(historical_data) < self.state_size:
                return StrategySignal(
                    strategy_name=self.name,
                    symbol=symbol,
                    direction="HOLD",
                    confidence=0.0,
                    position_size=0.0,
                    reasoning="Insufficient data for state construction",
                    metadata={}
                )
            
            # Construct state features
            state = self._construct_state(market_data, historical_data)
            await cache.set(cache_key, state.tolist(), ttl=60)
        
        # Simulate Q-values (in production, use neural network)
        q_values = self._get_q_values(state)
        
        # Use actual RL model if available
        if self.rl_manager:
            action, metadata = await self.rl_manager.get_dqn_action(symbol, state)
            q_values = np.array(metadata.get('q_values', q_values))
        else:
            # Fallback to rule-based
            action = np.argmax(q_values)
        
        actions = ["BUY", "SELL", "HOLD"]
        direction = actions[action]
        
        if direction != "HOLD":
            confidence = float(np.max(q_values) - np.mean(q_values))
            confidence = min(max(confidence, 0.0), 0.9)
            position_size = confidence * 0.02  # Scale with confidence
            
            return StrategySignal(
                strategy_name=self.name,
                symbol=symbol,
                direction=direction,
                confidence=confidence,
                position_size=position_size,
                reasoning=f"DQN Q-values: {q_values} -> {direction}",
                metadata={"q_values": q_values.tolist(), "state": state.tolist()}
            )
        
        return StrategySignal(
            strategy_name=self.name,
            symbol=symbol,
            direction="HOLD",
            confidence=0.0,
            position_size=0.0,
            reasoning=f"DQN suggests HOLD (Q-values: {q_values})",
            metadata={"q_values": q_values.tolist()}
        )
    
    def _construct_state(self, market_data: MarketSnapshot, historical_data: pd.DataFrame) -> np.ndarray:
        """Construct state vector from market data."""
        # Features: returns, volume, RSI, volatility, etc.
        recent_data = historical_data.tail(self.state_size)
        
        returns = recent_data['close'].pct_change().fillna(0).values
        volumes = recent_data['volume'].values / recent_data['volume'].mean()
        
        # Simple RSI calculation
        gains = returns.copy()
        gains[gains < 0] = 0
        losses = -returns.copy()
        losses[losses < 0] = 0
        
        avg_gain = np.mean(gains)
        avg_loss = np.mean(losses)
        rs = avg_gain / (avg_loss + 1e-10)
        rsi = 100 - (100 / (1 + rs))
        
        # Normalize features
        state = np.array([
            market_data.change_24h / 100,
            market_data.volume / 1e6,
            rsi / 100,
            np.std(returns),  # Volatility
            returns[-1],  # Latest return
            np.mean(volumes),
            0.5,  # Placeholder features
            0.5,
            0.5,
            0.5
        ])
        
        return state[:self.state_size]
    
    def _get_q_values(self, state: np.ndarray) -> np.ndarray:
        """Get Q-values for actions (simulated)."""
        # Simple rule-based approximation
        # In production, forward pass through neural network
        
        change = state[0]  # 24h change
        rsi = state[2] * 100
        volatility = state[3]
        
        # Base Q-values
        q_buy = 0.5
        q_sell = 0.5
        q_hold = 0.6  # Slight bias towards holding
        
        # Adjust based on indicators
        if rsi < 30:  # Oversold
            q_buy += 0.3
        elif rsi > 70:  # Overbought
            q_sell += 0.3
        
        if change < -0.1:  # Big drop
            q_buy += 0.2
        elif change > 0.1:  # Big rise
            q_sell += 0.2
        
        # Penalize actions in high volatility
        if volatility > 0.05:
            q_buy -= 0.1
            q_sell -= 0.1
            q_hold += 0.2
        
        return np.array([q_buy, q_sell, q_hold])
    
    def get_required_history(self) -> int:
        return max(self.state_size * 2, 20)


class PPOStrategy(TradingStrategy):
    """Proximal Policy Optimization strategy for continuous position sizing."""
    
    def __init__(self, learning_rate: float = 0.0003, rl_manager: Optional[RLStrategyManager] = None):
        super().__init__("PPO")
        self.learning_rate = learning_rate
        self.rl_manager = rl_manager
        
    async def evaluate(self, symbol: str, market_data: MarketSnapshot, 
                      historical_data: Optional[pd.DataFrame] = None) -> StrategySignal:
        """Evaluate using PPO model (simulated for MVP)."""
        cache = await self.get_cache()
        cache_key = f"strategy:ppo:features:{symbol}"
        cached_features = await cache.get(cache_key)

        if cached_features:
            trend = cached_features['trend']
            volatility = cached_features['volatility']
            returns_mean = cached_features['returns_mean']
            returns_std = cached_features['returns_std']
            latest_return = cached_features['latest_return']
            ma_return = cached_features['ma_return']
        else:
            if historical_data is None or len(historical_data) < 20:
                return StrategySignal(
                    strategy_name=self.name,
                    symbol=symbol,
                    direction="HOLD",
                    confidence=0.0,
                    position_size=0.0,
                    reasoning="Insufficient data for PPO evaluation",
                    metadata={}
                )
            
            # Calculate market regime indicators
            returns = historical_data['close'].pct_change().tail(20)
            trend = np.polyfit(range(len(returns)), returns.fillna(0), 1)[0]
            volatility = returns.std()
            returns_mean = returns.mean()
            returns_std = returns.std()
            latest_return = returns.iloc[-1]
            ma_return = returns.iloc[-5:].mean()

            await cache.set(cache_key, {
                "trend": trend, 
                "volatility": volatility,
                "returns_mean": returns_mean,
                "returns_std": returns_std,
                "latest_return": latest_return,
                "ma_return": ma_return,
            }, ttl=60)

        # Use actual RL model if available
        if self.rl_manager:
            state = np.array([trend, volatility, returns_mean, returns_std, 
                            latest_return, ma_return,
                            market_data.change_24h / 100, market_data.volume / 1e6,
                            0.5, 0.5])[:10]  # Ensure state size
            
            action, metadata = await self.rl_manager.get_ppo_action(symbol, state)
        else:
            # Fallback to simulated policy
            action_mean = trend * 10  # Scale trend
            action_std = volatility * 5
            action = np.random.normal(action_mean, action_std)
            action = np.clip(action, -1, 1)  # Clip to valid range
        
        if abs(action) > 0.1:  # Threshold for taking position
            direction = "BUY" if action > 0 else "SELL"
            confidence = min(abs(action), 0.9)
            position_size = min(abs(action) * 0.02, 0.02)  # Max 2%
            
            return StrategySignal(
                strategy_name=self.name,
                symbol=symbol,
                direction=direction,
                confidence=confidence,
                position_size=position_size,
                reasoning=f"PPO action {action:.3f} (trend: {trend:.3f}, vol: {volatility:.3f})",
                metadata={"action": action, "trend": trend, "volatility": volatility}
            )
        
        return StrategySignal(
            strategy_name=self.name,
            symbol=symbol,
            direction="HOLD",
            confidence=0.0,
            position_size=0.0,
            reasoning=f"PPO action {action:.3f} below threshold",
            metadata={"action": action, "trend": trend, "volatility": volatility}
        )
    
    def get_required_history(self) -> int:
        return 20


class StrategySelector:
    """Manages multiple strategies and selects optimal strategy per symbol."""
    
    def __init__(self, enable_rl: bool = True):
        # Initialize RL manager if enabled
        self.rl_manager = RLStrategyManager() if enable_rl else None
        
        self.strategies = {
            'momentum': MomentumStrategy(threshold=0.3),
            'mean_reversion': MeanReversionStrategy(bb_period=20, bb_std=2),
            'arbitrage': ArbitrageStrategy(min_spread=0.002),
            'ml_dqn': DQNStrategy(state_size=10, action_size=3, rl_manager=self.rl_manager),
            'ml_ppo': PPOStrategy(learning_rate=0.0003, rl_manager=self.rl_manager)
        }
        self.performance_history: Dict[str, Dict[str, float]] = {}
        
    async def evaluate_all_strategies(self, symbol: str, market_data: MarketSnapshot,
                                    historical_data: Optional[pd.DataFrame] = None) -> List[StrategySignal]:
        """Evaluate all strategies for a symbol and return signals."""
        tasks = []
        for strategy in self.strategies.values():
            tasks.append(strategy.evaluate(symbol, market_data, historical_data))
        
        signals = await asyncio.gather(*tasks)
        return list(signals)
    
    async def select_best_strategy(self, symbol: str, market_data: MarketSnapshot,
                                 historical_data: Optional[pd.DataFrame] = None) -> StrategySignal:
        """Select the best strategy for current market conditions."""
        signals = await self.evaluate_all_strategies(symbol, market_data, historical_data)
        
        # Filter out HOLD signals
        active_signals = [s for s in signals if s.direction != "HOLD"]
        
        if not active_signals:
            # Return the highest confidence HOLD
            return max(signals, key=lambda s: s.confidence)
        
        # Score signals based on confidence and historical performance
        best_signal = max(active_signals, key=lambda s: self._score_signal(s))
        
        return best_signal
    
    def _score_signal(self, signal: StrategySignal) -> float:
        """Score a signal based on confidence and historical performance."""
        base_score = signal.confidence
        
        # Boost score based on historical performance (if available)
        strategy_perf = self.performance_history.get(signal.strategy_name, {})
        win_rate = strategy_perf.get('win_rate', 0.5)
        avg_return = strategy_perf.get('avg_return', 0.0)
        
        performance_boost = (win_rate - 0.5) * 0.5 + avg_return * 0.3
        
        return base_score + performance_boost
    
    def update_performance(self, strategy_name: str, profit: float) -> None:
        """Update strategy performance metrics."""
        if strategy_name not in self.performance_history:
            self.performance_history[strategy_name] = {
                'trades': 0,
                'wins': 0,
                'total_return': 0.0,
                'win_rate': 0.5,
                'avg_return': 0.0
            }
        
        stats = self.performance_history[strategy_name]
        stats['trades'] += 1
        stats['total_return'] += profit
        
        if profit > 0:
            stats['wins'] += 1
        
        stats['win_rate'] = stats['wins'] / stats['trades']
        stats['avg_return'] = stats['total_return'] / stats['trades']
        
    def get_required_history(self) -> int:
        """Get maximum history required across all strategies."""
        return max(s.get_required_history() for s in self.strategies.values())
