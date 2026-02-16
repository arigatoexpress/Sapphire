"""Technical analysis indicators using pandas-ta-openbb."""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

try:
    import pandas as pd
    import pandas_ta as ta
except ImportError:  # pragma: no cover - handled gracefully at runtime
    pd = None  # type: ignore[assignment]
    ta = None  # type: ignore[assignment]
    logging.warning("pandas-ta-openbb not available, technical indicators will be disabled")

logger = logging.getLogger(__name__)


class TAIndicators:
    """Technical analysis indicators for market data."""

    @staticmethod
    def calculate_rsi(prices: List[float], period: int = 14) -> Optional[float]:
        """Calculate Relative Strength Index (RSI).

        Args:
            prices: List of closing prices
            period: RSI period (default 14)

        Returns:
            RSI value (0-100) or None if insufficient data
        """
        if not ta or not pd or len(prices) < period:
            return None

        try:
            price_series = pd.Series(prices, dtype="float64")
            rsi_series = ta.rsi(close=price_series, length=period)
            if rsi_series is None or rsi_series.empty:
                return None

            value = rsi_series.iloc[-1]
            return float(value) if pd.notna(value) else None
        except Exception as exc:
            logger.error(f"Error calculating RSI: {exc}")
            return None

    @staticmethod
    def calculate_macd(
        prices: List[float],
        fastperiod: int = 12,
        slowperiod: int = 26,
        signalperiod: int = 9,
    ) -> Optional[Dict[str, float]]:
        """Calculate MACD (Moving Average Convergence Divergence).

        Args:
            prices: List of closing prices
            fastperiod: Fast EMA period
            slowperiod: Slow EMA period
            signalperiod: Signal line period

        Returns:
            Dict with 'macd', 'signal', 'histogram' or None
        """
        minimum_length = max(fastperiod, slowperiod) + signalperiod
        if not ta or not pd or len(prices) < minimum_length:
            return None

        try:
            price_series = pd.Series(prices, dtype="float64")
            macd_df = ta.macd(
                close=price_series,
                fast=fastperiod,
                slow=slowperiod,
                signal=signalperiod,
            )

            if macd_df is None or macd_df.empty:
                return None

            latest = macd_df.iloc[-1]

            try:
                macd_val = float(latest.iloc[0])
                signal_val = float(latest.iloc[1])
                histogram_val = float(latest.iloc[2])
            except (ValueError, TypeError, IndexError) as exc:  # pragma: no cover
                logger.error(f"Unexpected MACD structure: {exc}")
                return None

            if any(pd.isna(v) for v in (macd_val, signal_val, histogram_val)):
                return None

            return {
                "macd": macd_val,
                "signal": signal_val,
                "histogram": histogram_val,
            }
        except Exception as exc:
            logger.error(f"Error calculating MACD: {exc}")
            return None

    @staticmethod
    def calculate_atr(
        high: List[float],
        low: List[float],
        close: List[float],
        period: int = 14,
    ) -> Optional[float]:
        """Calculate Average True Range (ATR).

        Args:
            high: List of high prices
            low: List of low prices
            close: List of closing prices
            period: ATR period (default 14)

        Returns:
            ATR value or None
        """
        if not ta or not pd or len(high) < period or len(low) < period or len(close) < period:
            return None

        try:
            df = pd.DataFrame(
                {
                    "high": high,
                    "low": low,
                    "close": close,
                },
                dtype="float64",
            )

            atr_series = ta.atr(
                high=df["high"],
                low=df["low"],
                close=df["close"],
                length=period,
            )

            if atr_series is None or atr_series.empty:
                return None

            value = atr_series.iloc[-1]
            return float(value) if pd.notna(value) else None
        except Exception as exc:
            logger.error(f"Error calculating ATR: {exc}")
            return None

    @staticmethod
    def calculate_volatility_based_stoploss(
        price: float,
        atr: float,
        multiplier: float = 2.0,
        is_long: bool = True,
    ) -> float:
        """Calculate volatility-based stop loss using ATR.

        Args:
            price: Current price
            atr: Average True Range value
            multiplier: ATR multiplier (default 2.0)
            is_long: True for long position, False for short

        Returns:
            Stop loss price
        """
        if not atr or atr <= 0:
            # Fallback to 2% if ATR unavailable
            return price * (0.98 if is_long else 1.02)

        stop_distance = atr * multiplier
        if is_long:
            return price - stop_distance
        else:
            return price + stop_distance

    # ===== ADVANCED INDICATORS =====

    @staticmethod
    def calculate_bollinger_bands(
        prices: List[float],
        period: int = 20,
        std_dev: float = 2.0,
    ) -> Optional[Dict[str, float]]:
        """Calculate Bollinger Bands.

        Args:
            prices: List of closing prices
            period: SMA period (default 20)
            std_dev: Standard deviation multiplier (default 2.0)

        Returns:
            Dict with 'upper', 'middle', 'lower', 'percent_b', 'bandwidth'
        """
        if not ta or not pd or len(prices) < period:
            return None

        try:
            price_series = pd.Series(prices, dtype="float64")
            bb_df = ta.bbands(close=price_series, length=period, std=std_dev)

            if bb_df is None or bb_df.empty:
                return None

            latest = bb_df.iloc[-1]
            current_price = prices[-1]

            # Column names: BBL, BBM, BBU, BBB, BBP
            lower = float(latest.iloc[0])
            middle = float(latest.iloc[1])
            upper = float(latest.iloc[2])
            bandwidth = float(latest.iloc[3]) if len(latest) > 3 else (upper - lower) / middle
            percent_b = float(latest.iloc[4]) if len(latest) > 4 else (current_price - lower) / (upper - lower)

            return {
                "upper": upper,
                "middle": middle,
                "lower": lower,
                "bandwidth": bandwidth,
                "percent_b": percent_b,
            }
        except Exception as exc:
            logger.error(f"Error calculating Bollinger Bands: {exc}")
            return None

    @staticmethod
    def calculate_stochastic_rsi(
        prices: List[float],
        rsi_period: int = 14,
        stoch_period: int = 14,
        smooth_k: int = 3,
        smooth_d: int = 3,
    ) -> Optional[Dict[str, float]]:
        """Calculate Stochastic RSI.

        Args:
            prices: List of closing prices
            rsi_period: RSI period
            stoch_period: Stochastic period
            smooth_k: %K smoothing
            smooth_d: %D smoothing

        Returns:
            Dict with 'k', 'd' values (0-100)
        """
        min_length = rsi_period + stoch_period + max(smooth_k, smooth_d)
        if not ta or not pd or len(prices) < min_length:
            return None

        try:
            price_series = pd.Series(prices, dtype="float64")
            stochrsi = ta.stochrsi(
                close=price_series,
                length=rsi_period,
                rsi_length=stoch_period,
                k=smooth_k,
                d=smooth_d,
            )

            if stochrsi is None or stochrsi.empty:
                return None

            latest = stochrsi.iloc[-1]
            k_val = float(latest.iloc[0]) if pd.notna(latest.iloc[0]) else None
            d_val = float(latest.iloc[1]) if len(latest) > 1 and pd.notna(latest.iloc[1]) else None

            if k_val is None:
                return None

            return {"k": k_val * 100, "d": d_val * 100 if d_val else None}
        except Exception as exc:
            logger.error(f"Error calculating Stochastic RSI: {exc}")
            return None

    @staticmethod
    def calculate_adx(
        high: List[float],
        low: List[float],
        close: List[float],
        period: int = 14,
    ) -> Optional[Dict[str, float]]:
        """Calculate Average Directional Index (ADX) for trend strength.

        Args:
            high: List of high prices
            low: List of low prices
            close: List of closing prices
            period: ADX period (default 14)

        Returns:
            Dict with 'adx', 'plus_di', 'minus_di'
        """
        if not ta or not pd or len(high) < period * 2:
            return None

        try:
            df = pd.DataFrame(
                {"high": high, "low": low, "close": close}, dtype="float64"
            )
            adx_df = ta.adx(
                high=df["high"], low=df["low"], close=df["close"], length=period
            )

            if adx_df is None or adx_df.empty:
                return None

            latest = adx_df.iloc[-1]
            adx_val = float(latest.iloc[0]) if pd.notna(latest.iloc[0]) else None
            plus_di = float(latest.iloc[1]) if len(latest) > 1 and pd.notna(latest.iloc[1]) else None
            minus_di = float(latest.iloc[2]) if len(latest) > 2 and pd.notna(latest.iloc[2]) else None

            if adx_val is None:
                return None

            return {"adx": adx_val, "plus_di": plus_di, "minus_di": minus_di}
        except Exception as exc:
            logger.error(f"Error calculating ADX: {exc}")
            return None

    @staticmethod
    def calculate_vwap(
        high: List[float],
        low: List[float],
        close: List[float],
        volume: List[float],
    ) -> Optional[float]:
        """Calculate Volume Weighted Average Price (VWAP).

        Args:
            high: List of high prices
            low: List of low prices
            close: List of closing prices
            volume: List of volume

        Returns:
            VWAP value
        """
        if not ta or not pd or len(close) < 2:
            return None

        try:
            df = pd.DataFrame(
                {"high": high, "low": low, "close": close, "volume": volume},
                dtype="float64",
            )
            vwap_series = ta.vwap(
                high=df["high"],
                low=df["low"],
                close=df["close"],
                volume=df["volume"],
            )

            if vwap_series is None or vwap_series.empty:
                return None

            value = vwap_series.iloc[-1]
            return float(value) if pd.notna(value) else None
        except Exception as exc:
            logger.error(f"Error calculating VWAP: {exc}")
            return None

    @staticmethod
    def calculate_obv(
        close: List[float],
        volume: List[float],
    ) -> Optional[Dict[str, float]]:
        """Calculate On-Balance Volume (OBV) for volume momentum.

        Args:
            close: List of closing prices
            volume: List of volume

        Returns:
            Dict with 'obv', 'obv_change' (recent momentum)
        """
        if not ta or not pd or len(close) < 10:
            return None

        try:
            df = pd.DataFrame(
                {"close": close, "volume": volume}, dtype="float64"
            )
            obv_series = ta.obv(close=df["close"], volume=df["volume"])

            if obv_series is None or obv_series.empty:
                return None

            current_obv = float(obv_series.iloc[-1])
            prev_obv = float(obv_series.iloc[-5]) if len(obv_series) >= 5 else current_obv

            return {
                "obv": current_obv,
                "obv_change": current_obv - prev_obv,
            }
        except Exception as exc:
            logger.error(f"Error calculating OBV: {exc}")
            return None

    @staticmethod
    def calculate_ema(prices: List[float], period: int = 20) -> Optional[float]:
        """Calculate Exponential Moving Average.

        Args:
            prices: List of closing prices
            period: EMA period

        Returns:
            EMA value
        """
        if not ta or not pd or len(prices) < period:
            return None

        try:
            price_series = pd.Series(prices, dtype="float64")
            ema_series = ta.ema(close=price_series, length=period)

            if ema_series is None or ema_series.empty:
                return None

            value = ema_series.iloc[-1]
            return float(value) if pd.notna(value) else None
        except Exception as exc:
            logger.error(f"Error calculating EMA: {exc}")
            return None

    @staticmethod
    def calculate_sma(prices: List[float], period: int = 20) -> Optional[float]:
        """Calculate Simple Moving Average.

        Args:
            prices: List of closing prices
            period: SMA period

        Returns:
            SMA value
        """
        if not ta or not pd or len(prices) < period:
            return None

        try:
            price_series = pd.Series(prices, dtype="float64")
            sma_series = ta.sma(close=price_series, length=period)

            if sma_series is None or sma_series.empty:
                return None

            value = sma_series.iloc[-1]
            return float(value) if pd.notna(value) else None
        except Exception as exc:
            logger.error(f"Error calculating SMA: {exc}")
            return None

    @staticmethod
    def get_comprehensive_analysis(
        high: List[float],
        low: List[float],
        close: List[float],
        volume: List[float],
    ) -> Dict[str, any]:
        """Get comprehensive technical analysis with all indicators.

        Args:
            high: List of high prices
            low: List of low prices
            close: List of closing prices
            volume: List of volume

        Returns:
            Dict with all available indicators and a signal summary
        """
        result = {
            "rsi": TAIndicators.calculate_rsi(close),
            "macd": TAIndicators.calculate_macd(close),
            "atr": TAIndicators.calculate_atr(high, low, close),
            "bollinger": TAIndicators.calculate_bollinger_bands(close),
            "stoch_rsi": TAIndicators.calculate_stochastic_rsi(close),
            "adx": TAIndicators.calculate_adx(high, low, close),
            "vwap": TAIndicators.calculate_vwap(high, low, close, volume),
            "obv": TAIndicators.calculate_obv(close, volume),
            "ema_20": TAIndicators.calculate_ema(close, 20),
            "ema_50": TAIndicators.calculate_ema(close, 50),
            "sma_200": TAIndicators.calculate_sma(close, 200),
        }

        # Calculate aggregate signal strength (-1 to +1)
        signals = []
        current_price = close[-1] if close else 0

        # RSI signal
        if result["rsi"]:
            if result["rsi"] > 70:
                signals.append(-0.5)  # Overbought
            elif result["rsi"] < 30:
                signals.append(0.5)  # Oversold
            else:
                signals.append((50 - result["rsi"]) / 100)

        # MACD signal
        if result["macd"]:
            if result["macd"]["histogram"] > 0:
                signals.append(0.3)
            else:
                signals.append(-0.3)

        # Bollinger signal
        if result["bollinger"]:
            if result["bollinger"]["percent_b"] < 0.2:
                signals.append(0.4)  # Near lower band = buy
            elif result["bollinger"]["percent_b"] > 0.8:
                signals.append(-0.4)  # Near upper band = sell

        # ADX trend strength
        if result["adx"]:
            trend_strength = result["adx"]["adx"] / 100 if result["adx"]["adx"] else 0
            if result["adx"]["plus_di"] and result["adx"]["minus_di"]:
                if result["adx"]["plus_di"] > result["adx"]["minus_di"]:
                    signals.append(trend_strength * 0.5)
                else:
                    signals.append(-trend_strength * 0.5)

        # EMA trend
        if result["ema_20"] and result["ema_50"]:
            if result["ema_20"] > result["ema_50"]:
                signals.append(0.3)  # Bullish crossover
            else:
                signals.append(-0.3)  # Bearish crossover

        # VWAP
        if result["vwap"] and current_price:
            if current_price > result["vwap"]:
                signals.append(0.2)  # Above VWAP = bullish
            else:
                signals.append(-0.2)

        # Aggregate
        result["signal_strength"] = sum(signals) / len(signals) if signals else 0
        result["signal_count"] = len(signals)
        result["bias"] = "bullish" if result["signal_strength"] > 0.1 else "bearish" if result["signal_strength"] < -0.1 else "neutral"

        return result


def kelly_criterion(
    expected_return: float,
    volatility: float,
    account_balance: float,
    risk_fraction: float = 0.01,
) -> float:
    """Calculate optimal position size using Kelly Criterion.

    Args:
        expected_return: Expected return per trade (e.g., 0.05 for 5%)
        volatility: Volatility of returns (e.g., 0.15 for 15%)
        account_balance: Current account balance
        risk_fraction: Maximum fraction of account to risk (default 1%)

    Returns:
        Optimal position size in USD
    """
    if volatility <= 0 or expected_return <= 0:
        return account_balance * risk_fraction

    # Kelly fraction = expected_return / (volatility^2)
    kelly_fraction = expected_return / (volatility**2)

    # Apply conservative cap (1% of account)
    kelly_fraction = min(kelly_fraction, risk_fraction)

    # Ensure positive
    kelly_fraction = max(kelly_fraction, 0.001)

    return account_balance * kelly_fraction
