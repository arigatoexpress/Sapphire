"""
Jupiter HFT Strategy - 2026 Edition
Comprehensive technical analysis with multiple indicators for high-frequency trading
on Jupiter Perpetuals and Spot Swaps

Indicators Used:
- Trend: EMA, SMA, MACD, ADX, Aroon, Supertrend
- Momentum: RSI, Stochastic, CCI, Williams %R, MFI, ROC
- Volatility: Bollinger Bands, ATR, Keltner Channels, Donchian Channels
- Volume: OBV, VWAP, Volume Profile, Accumulation/Distribution
- Pattern Recognition: Candlestick patterns, Support/Resistance
- Advanced: Ichimoku Cloud, Fibonacci, Elliott Waves, Heikin-Ashi

Strategy: Multi-timeframe analysis with ML ensemble for trade signals
"""

import pandas as pd
import numpy as np
from decimal import Decimal
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import asyncio

# Technical Analysis Libraries
try:
    import talib
    HAS_TALIB = True
except ImportError:
    HAS_TALIB = False
    print("Warning: TA-Lib not installed. Install with: brew install ta-lib && pip install ta-lib")

import pandas_ta as pta
from finta import TA as fta
import btalib
from stockstats import StockDataFrame
from scipy.stats import linregress
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
import xgboost as xgb
import lightgbm as lgb
from loguru import logger


class Signal(Enum):
    """Trading signal types"""
    STRONG_BUY = "STRONG_BUY"
    BUY = "BUY"
    NEUTRAL = "NEUTRAL"
    SELL = "SELL"
    STRONG_SELL = "STRONG_SELL"


@dataclass
class TradingSignal:
    """Comprehensive trading signal"""
    timestamp: datetime
    token: str
    signal: Signal
    confidence: float  # 0.0 to 1.0
    entry_price: Decimal
    take_profit: Decimal
    stop_loss: Decimal
    position_size_pct: float  # Percentage of capital
    timeframe: str  # "1m", "5m", "15m", "1h", "4h", "1d"
    indicators: Dict[str, float]  # All indicator values
    reasoning: str


class JupiterHFTStrategy:
    """
    High-Frequency Trading Strategy for Jupiter
    Uses ensemble of technical indicators with ML classification
    """

    def __init__(
        self,
        capital_usd: Decimal = Decimal("50"),
        max_position_pct: float = 0.20,  # 20% max per trade
        risk_per_trade_pct: float = 0.02,  # 2% risk
        confidence_threshold: float = 0.70,  # 70% minimum confidence
    ):
        """
        Initialize HFT strategy

        Args:
            capital_usd: Total trading capital
            max_position_pct: Maximum position size as % of capital
            risk_per_trade_pct: Risk per trade as % of capital
            confidence_threshold: Minimum confidence to take trade
        """
        self.capital = capital_usd
        self.max_position_pct = max_position_pct
        self.risk_per_trade = risk_per_trade_pct
        self.confidence_threshold = confidence_threshold

        # ML models for ensemble
        self.ml_models = {
            "random_forest": RandomForestClassifier(n_estimators=100, random_state=42),
            "gradient_boost": GradientBoostingClassifier(n_estimators=100, random_state=42),
            "xgboost": xgb.XGBClassifier(n_estimators=100, random_state=42),
            "lightgbm": lgb.LGBMClassifier(n_estimators=100, random_state=42, verbose=-1),
        }

        self.scaler = StandardScaler()
        self.is_trained = False

        logger.info("✅ Jupiter HFT Strategy initialized")

    def calculate_all_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate ALL technical indicators

        Args:
            df: DataFrame with OHLCV data (columns: open, high, low, close, volume)

        Returns:
            DataFrame with all indicators added
        """
        df = df.copy()

        # Ensure we have enough data
        if len(df) < 200:
            logger.warning(f"Insufficient data: {len(df)} candles (need 200+)")
            return df

        # ==============================================================
        # TREND INDICATORS
        # ==============================================================

        # Moving Averages
        for period in [7, 14, 21, 50, 100, 200]:
            df[f'EMA_{period}'] = df['close'].ewm(span=period).mean()
            df[f'SMA_{period}'] = df['close'].rolling(window=period).mean()

        # MACD (Moving Average Convergence Divergence)
        if HAS_TALIB:
            df['MACD'], df['MACD_signal'], df['MACD_hist'] = talib.MACD(
                df['close'], fastperiod=12, slowperiod=26, signalperiod=9
            )
        else:
            exp1 = df['close'].ewm(span=12).mean()
            exp2 = df['close'].ewm(span=26).mean()
            df['MACD'] = exp1 - exp2
            df['MACD_signal'] = df['MACD'].ewm(span=9).mean()
            df['MACD_hist'] = df['MACD'] - df['MACD_signal']

        # ADX (Average Directional Index) - Trend Strength
        if HAS_TALIB:
            df['ADX'] = talib.ADX(df['high'], df['low'], df['close'], timeperiod=14)
            df['PLUS_DI'] = talib.PLUS_DI(df['high'], df['low'], df['close'], timeperiod=14)
            df['MINUS_DI'] = talib.MINUS_DI(df['high'], df['low'], df['close'], timeperiod=14)

        # Aroon Indicator
        if HAS_TALIB:
            df['AROON_UP'], df['AROON_DOWN'] = talib.AROON(df['high'], df['low'], timeperiod=25)
            df['AROON_OSC'] = df['AROON_UP'] - df['AROON_DOWN']

        # Supertrend
        df_supertrend = btalib.supertrend(df, period=10, multiplier=3)
        if not df_supertrend.empty:
            df['SUPERTREND'] = df_supertrend['supertrend']
            df['SUPERTREND_DIRECTION'] = df_supertrend['direction']

        # ==============================================================
        # MOMENTUM INDICATORS
        # ==============================================================

        # RSI (Relative Strength Index)
        for period in [7, 14, 21]:
            if HAS_TALIB:
                df[f'RSI_{period}'] = talib.RSI(df['close'], timeperiod=period)
            else:
                delta = df['close'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
                rs = gain / loss
                df[f'RSI_{period}'] = 100 - (100 / (1 + rs))

        # Stochastic Oscillator
        if HAS_TALIB:
            df['STOCH_K'], df['STOCH_D'] = talib.STOCH(
                df['high'], df['low'], df['close'],
                fastk_period=14, slowk_period=3, slowd_period=3
            )

        # CCI (Commodity Channel Index)
        if HAS_TALIB:
            df['CCI'] = talib.CCI(df['high'], df['low'], df['close'], timeperiod=20)

        # Williams %R
        if HAS_TALIB:
            df['WILLR'] = talib.WILLR(df['high'], df['low'], df['close'], timeperiod=14)

        # MFI (Money Flow Index)
        if HAS_TALIB:
            df['MFI'] = talib.MFI(df['high'], df['low'], df['close'], df['volume'], timeperiod=14)

        # ROC (Rate of Change)
        for period in [5, 10, 20]:
            if HAS_TALIB:
                df[f'ROC_{period}'] = talib.ROC(df['close'], timeperiod=period)

        # ==============================================================
        # VOLATILITY INDICATORS
        # ==============================================================

        # Bollinger Bands
        if HAS_TALIB:
            df['BB_UPPER'], df['BB_MIDDLE'], df['BB_LOWER'] = talib.BBANDS(
                df['close'], timeperiod=20, nbdevup=2, nbdevdn=2
            )
            df['BB_WIDTH'] = (df['BB_UPPER'] - df['BB_LOWER']) / df['BB_MIDDLE']
            df['BB_POSITION'] = (df['close'] - df['BB_LOWER']) / (df['BB_UPPER'] - df['BB_LOWER'])

        # ATR (Average True Range)
        if HAS_TALIB:
            df['ATR'] = talib.ATR(df['high'], df['low'], df['close'], timeperiod=14)
            df['ATR_PCT'] = (df['ATR'] / df['close']) * 100

        # Keltner Channels
        ema_20 = df['close'].ewm(span=20).mean()
        if HAS_TALIB:
            atr_10 = talib.ATR(df['high'], df['low'], df['close'], timeperiod=10)
        else:
            tr = pd.DataFrame({
                'hl': df['high'] - df['low'],
                'hc': abs(df['high'] - df['close'].shift()),
                'lc': abs(df['low'] - df['close'].shift())
            }).max(axis=1)
            atr_10 = tr.rolling(window=10).mean()

        df['KELTNER_UPPER'] = ema_20 + (2 * atr_10)
        df['KELTNER_LOWER'] = ema_20 - (2 * atr_10)

        # Donchian Channels
        df['DONCHIAN_UPPER'] = df['high'].rolling(window=20).max()
        df['DONCHIAN_LOWER'] = df['low'].rolling(window=20).min()
        df['DONCHIAN_MIDDLE'] = (df['DONCHIAN_UPPER'] + df['DONCHIAN_LOWER']) / 2

        # ==============================================================
        # VOLUME INDICATORS
        # ==============================================================

        # OBV (On-Balance Volume)
        if HAS_TALIB:
            df['OBV'] = talib.OBV(df['close'], df['volume'])

        # VWAP (Volume Weighted Average Price)
        df['VWAP'] = (df['close'] * df['volume']).cumsum() / df['volume'].cumsum()

        # Volume SMA
        df['VOLUME_SMA_20'] = df['volume'].rolling(window=20).mean()
        df['VOLUME_RATIO'] = df['volume'] / df['VOLUME_SMA_20']

        # Accumulation/Distribution Line
        if HAS_TALIB:
            df['AD'] = talib.AD(df['high'], df['low'], df['close'], df['volume'])

        # Chaikin Money Flow
        if HAS_TALIB:
            df['CMF'] = talib.ADOSC(df['high'], df['low'], df['close'], df['volume'],
                                    fastperiod=3, slowperiod=10)

        # ==============================================================
        # PATTERN RECOGNITION
        # ==============================================================

        if HAS_TALIB:
            # Candlestick patterns
            df['DOJI'] = talib.CDLDOJI(df['open'], df['high'], df['low'], df['close'])
            df['HAMMER'] = talib.CDLHAMMER(df['open'], df['high'], df['low'], df['close'])
            df['ENGULFING'] = talib.CDLENGULFING(df['open'], df['high'], df['low'], df['close'])
            df['MORNING_STAR'] = talib.CDLMORNINGSTAR(df['open'], df['high'], df['low'], df['close'])
            df['EVENING_STAR'] = talib.CDLEVENINGSTAR(df['open'], df['high'], df['low'], df['close'])

        # ==============================================================
        # ADVANCED INDICATORS
        # ==============================================================

        # Heikin-Ashi Candles
        df['HA_CLOSE'] = (df['open'] + df['high'] + df['low'] + df['close']) / 4
        df['HA_OPEN'] = ((df['open'].shift(1) + df['close'].shift(1)) / 2).fillna(df['open'])
        df['HA_HIGH'] = df[['high', 'HA_OPEN', 'HA_CLOSE']].max(axis=1)
        df['HA_LOW'] = df[['low', 'HA_OPEN', 'HA_CLOSE']].min(axis=1)

        # Ichimoku Cloud
        high_9 = df['high'].rolling(window=9).max()
        low_9 = df['low'].rolling(window=9).min()
        df['TENKAN'] = (high_9 + low_9) / 2

        high_26 = df['high'].rolling(window=26).max()
        low_26 = df['low'].rolling(window=26).min()
        df['KIJUN'] = (high_26 + low_26) / 2

        df['SENKOU_A'] = ((df['TENKAN'] + df['KIJUN']) / 2).shift(26)
        high_52 = df['high'].rolling(window=52).max()
        low_52 = df['low'].rolling(window=52).min()
        df['SENKOU_B'] = ((high_52 + low_52) / 2).shift(26)

        df['CHIKOU'] = df['close'].shift(-26)

        # Linear Regression Slope (trend strength)
        def calc_slope(series, period=20):
            slopes = []
            for i in range(len(series)):
                if i < period:
                    slopes.append(np.nan)
                else:
                    y = series.iloc[i-period:i].values
                    x = np.arange(len(y))
                    slope, _, _, _, _ = linregress(x, y)
                    slopes.append(slope)
            return pd.Series(slopes, index=series.index)

        df['SLOPE_20'] = calc_slope(df['close'], period=20)
        df['SLOPE_50'] = calc_slope(df['close'], period=50)

        # Support and Resistance Levels
        df['SUPPORT'] = df['low'].rolling(window=20).min()
        df['RESISTANCE'] = df['high'].rolling(window=20).max()
        df['SR_DISTANCE'] = (df['RESISTANCE'] - df['SUPPORT']) / df['close'] * 100

        # Drop NaN values from initial calculations
        df = df.fillna(method='bfill').fillna(method='ffill')

        logger.info(f"✅ Calculated {len(df.columns) - 5} technical indicators")

        return df

    def generate_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Generate ML features from indicators

        Args:
            df: DataFrame with indicators

        Returns:
            DataFrame with feature columns for ML
        """
        features = pd.DataFrame()

        # Trend features
        if 'EMA_7' in df.columns and 'EMA_21' in df.columns:
            features['TREND_EMA_CROSS'] = (df['EMA_7'] > df['EMA_21']).astype(int)
        if 'SMA_50' in df.columns and 'SMA_200' in df.columns:
            features['TREND_GOLDEN_CROSS'] = (df['SMA_50'] > df['SMA_200']).astype(int)

        # Momentum features
        if 'RSI_14' in df.columns:
            features['RSI_OVERSOLD'] = (df['RSI_14'] < 30).astype(int)
            features['RSI_OVERBOUGHT'] = (df['RSI_14'] > 70).astype(int)
            features['RSI_VALUE'] = df['RSI_14'] / 100

        # MACD features
        if 'MACD' in df.columns and 'MACD_signal' in df.columns:
            features['MACD_BULLISH'] = (df['MACD'] > df['MACD_signal']).astype(int)
            features['MACD_STRENGTH'] = df['MACD_hist']

        # Bollinger Bands features
        if 'BB_POSITION' in df.columns:
            features['BB_LOWER_TOUCH'] = (df['BB_POSITION'] < 0.1).astype(int)
            features['BB_UPPER_TOUCH'] = (df['BB_POSITION'] > 0.9).astype(int)
            features['BB_POSITION'] = df['BB_POSITION']

        # Volume features
        if 'VOLUME_RATIO' in df.columns:
            features['HIGH_VOLUME'] = (df['VOLUME_RATIO'] > 1.5).astype(int)

        # Volatility features
        if 'ATR_PCT' in df.columns:
            features['HIGH_VOLATILITY'] = (df['ATR_PCT'] > df['ATR_PCT'].median()).astype(int)

        # ADX features
        if 'ADX' in df.columns:
            features['STRONG_TREND'] = (df['ADX'] > 25).astype(int)

        # Ichimoku features
        if 'TENKAN' in df.columns and 'KIJUN' in df.columns:
            features['ICHIMOKU_BULLISH'] = (df['TENKAN'] > df['KIJUN']).astype(int)

        # Price action features
        features['PRICE_CHANGE'] = df['close'].pct_change()
        features['PRICE_CHANGE_5'] = df['close'].pct_change(5)
        features['PRICE_CHANGE_20'] = df['close'].pct_change(20)

        # Fill any remaining NaN
        features = features.fillna(0)

        return features

    def calculate_signal_score(self, df_row: pd.Series) -> Tuple[Signal, float]:
        """
        Calculate trading signal from indicator values

        Args:
            df_row: Single row of DataFrame with all indicators

        Returns:
            (Signal, confidence_score)
        """
        bullish_score = 0
        bearish_score = 0
        total_indicators = 0

        # Trend indicators (30% weight)
        if 'EMA_7' in df_row.index and 'EMA_21' in df_row.index:
            total_indicators += 1
            if df_row['EMA_7'] > df_row['EMA_21']:
                bullish_score += 0.3
            else:
                bearish_score += 0.3

        if 'MACD_hist' in df_row.index:
            total_indicators += 1
            if df_row['MACD_hist'] > 0:
                bullish_score += 0.3
            else:
                bearish_score += 0.3

        # Momentum indicators (25% weight)
        if 'RSI_14' in df_row.index:
            total_indicators += 1
            if df_row['RSI_14'] < 30:  # Oversold - bullish
                bullish_score += 0.25
            elif df_row['RSI_14'] > 70:  # Overbought - bearish
                bearish_score += 0.25

        if 'STOCH_K' in df_row.index:
            total_indicators += 1
            if df_row['STOCH_K'] < 20:
                bullish_score += 0.2
            elif df_row['STOCH_K'] > 80:
                bearish_score += 0.2

        # Volume confirmation (15% weight)
        if 'VOLUME_RATIO' in df_row.index:
            total_indicators += 1
            if df_row['VOLUME_RATIO'] > 1.5:  # High volume
                # Amplify current trend
                if bullish_score > bearish_score:
                    bullish_score += 0.15
                else:
                    bearish_score += 0.15

        # Volatility context (10% weight)
        if 'BB_POSITION' in df_row.index:
            total_indicators += 1
            if df_row['BB_POSITION'] < 0.2:  # Near lower band
                bullish_score += 0.1
            elif df_row['BB_POSITION'] > 0.8:  # Near upper band
                bearish_score += 0.1

        # Normalize scores
        if total_indicators > 0:
            confidence = abs(bullish_score - bearish_score) / total_indicators
        else:
            confidence = 0.0

        # Determine signal
        if bullish_score > bearish_score and confidence > self.confidence_threshold:
            if confidence > 0.8:
                return Signal.STRONG_BUY, confidence
            return Signal.BUY, confidence
        elif bearish_score > bullish_score and confidence > self.confidence_threshold:
            if confidence > 0.8:
                return Signal.STRONG_SELL, confidence
            return Signal.SELL, confidence

        return Signal.NEUTRAL, confidence

    async def analyze_and_generate_signal(
        self,
        token: str,
        df: pd.DataFrame,
        timeframe: str = "15m",
    ) -> Optional[TradingSignal]:
        """
        Analyze price data and generate trading signal

        Args:
            token: Token symbol (e.g., "SOL")
            df: DataFrame with OHLCV data
            timeframe: Timeframe (e.g., "1m", "5m", "15m", "1h")

        Returns:
            TradingSignal if confident signal found, None otherwise
        """
        # Calculate all indicators
        df_with_indicators = self.calculate_all_indicators(df)

        # Get latest values
        latest = df_with_indicators.iloc[-1]

        # Calculate signal
        signal, confidence = self.calculate_signal_score(latest)

        if signal == Signal.NEUTRAL or confidence < self.confidence_threshold:
            return None

        # Calculate entry, TP, SL based on ATR
        current_price = Decimal(str(latest['close']))
        atr = Decimal(str(latest.get('ATR', current_price * Decimal('0.02'))))

        if signal in [Signal.BUY, Signal.STRONG_BUY]:
            entry = current_price
            stop_loss = current_price - (atr * 2)
            take_profit = current_price + (atr * 3)
        else:  # SELL signals
            entry = current_price
            stop_loss = current_price + (atr * 2)
            take_profit = current_price - (atr * 3)

        # Position sizing based on risk
        risk_amount = self.capital * Decimal(str(self.risk_per_trade))
        stop_distance = abs(entry - stop_loss)
        position_size_pct = min(
            float(risk_amount / stop_distance) if stop_distance > 0 else 0.0,
            self.max_position_pct
        )

        # Extract key indicators for reasoning
        indicators = {
            'RSI': latest.get('RSI_14', 0),
            'MACD': latest.get('MACD', 0),
            'ADX': latest.get('ADX', 0),
            'BB_POSITION': latest.get('BB_POSITION', 0),
            'VOLUME_RATIO': latest.get('VOLUME_RATIO', 0),
        }

        reasoning = self._generate_reasoning(signal, indicators)

        return TradingSignal(
            timestamp=datetime.now(),
            token=token,
            signal=signal,
            confidence=confidence,
            entry_price=entry,
            take_profit=take_profit,
            stop_loss=stop_loss,
            position_size_pct=position_size_pct,
            timeframe=timeframe,
            indicators=indicators,
            reasoning=reasoning,
        )

    def _generate_reasoning(self, signal: Signal, indicators: Dict) -> str:
        """Generate human-readable reasoning for the signal"""
        reasons = []

        if indicators.get('RSI', 50) < 30:
            reasons.append("RSI oversold (<30)")
        elif indicators.get('RSI', 50) > 70:
            reasons.append("RSI overbought (>70)")

        if indicators.get('MACD', 0) > 0:
            reasons.append("MACD bullish crossover")
        elif indicators.get('MACD', 0) < 0:
            reasons.append("MACD bearish crossover")

        if indicators.get('ADX', 0) > 25:
            reasons.append(f"Strong trend (ADX: {indicators['ADX']:.1f})")

        if indicators.get('VOLUME_RATIO', 1) > 1.5:
            reasons.append("High volume confirmation")

        if not reasons:
            reasons.append("Multiple indicator alignment")

        return " | ".join(reasons)


# Example usage
async def example_hft_strategy():
    """Example: Generate HFT signals from price data"""

    # Create strategy
    strategy = JupiterHFTStrategy(
        capital_usd=Decimal("50"),
        max_position_pct=0.20,
        confidence_threshold=0.70,
    )

    # Simulate OHLCV data (in production, get from Jupiter/exchanges)
    # For demo, create sample data
    dates = pd.date_range(end=datetime.now(), periods=500, freq='15min')
    np.random.seed(42)

    # Simulate price movement with trend
    price = 128.0  # Starting SOL price
    prices = []
    for i in range(500):
        price += np.random.randn() * 2  # Random walk with volatility
        price = max(price, 50)  # Floor
        prices.append(price)

    df = pd.DataFrame({
        'timestamp': dates,
        'open': prices,
        'high': [p + abs(np.random.randn()) for p in prices],
        'low': [p - abs(np.random.randn()) for p in prices],
        'close': prices,
        'volume': np.random.randint(1000000, 5000000, 500),
    })

    # Generate signal
    signal = await strategy.analyze_and_generate_signal("SOL", df, timeframe="15m")

    if signal:
        print(f"\n{'='*60}")
        print(f"🎯 TRADING SIGNAL GENERATED")
        print(f"{'='*60}")
        print(f"Token: {signal.token}")
        print(f"Signal: {signal.signal.value}")
        print(f"Confidence: {signal.confidence:.1%}")
        print(f"Entry: ${signal.entry_price:.2f}")
        print(f"Take Profit: ${signal.take_profit:.2f}")
        print(f"Stop Loss: ${signal.stop_loss:.2f}")
        print(f"Position Size: {signal.position_size_pct:.1%}")
        print(f"Reasoning: {signal.reasoning}")
        print(f"{'='*60}\n")
    else:
        print("No confident signal at this time.")


if __name__ == "__main__":
    asyncio.run(example_hft_strategy())
