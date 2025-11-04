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
    logging.warning(
        "pandas-ta-openbb not available, technical indicators will be disabled"
    )

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
        if (
            not ta
            or not pd
            or len(high) < period
            or len(low) < period
            or len(close) < period
        ):
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
    kelly_fraction = expected_return / (volatility ** 2)
    
    # Apply conservative cap (1% of account)
    kelly_fraction = min(kelly_fraction, risk_fraction)
    
    # Ensure positive
    kelly_fraction = max(kelly_fraction, 0.001)
    
    return account_balance * kelly_fraction

