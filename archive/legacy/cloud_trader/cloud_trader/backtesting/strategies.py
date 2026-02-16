from typing import Any, Dict

import numpy as np
import pandas as pd


def momentum_strategy(df: pd.DataFrame, params: Dict[str, Any]) -> pd.Series:
    """
    Simple Momentum Strategy using RSI and MACD.
    Long when RSI < 30 (Oversold) + MACD Crossover? No that's Reversion.

    Momentum:
    Long when Price > SMA and MACD > Signal
    """
    rsi_period = params.get("rsi_period", 14)
    sma_period = params.get("sma_period", 50)

    # Logic
    # 1. Trend Filter: Close > SMA
    trend_up = df["close"] > df["sma_50"]  # Pre-calculated or calc here

    # 2. Momentum Trigger: MACD > Signal
    macd_bullish = df["macd"] > df["macd_signal"]

    # 3. RSI Filter: Not Overbought (> 70)
    rsi_safe = df["rsi"] < 70

    signal = pd.Series(0, index=df.index)

    # Enter Long
    long_cond = trend_up & macd_bullish & rsi_safe

    signal[long_cond] = 1

    return signal


def mean_reversion_strategy(df: pd.DataFrame, params: Dict[str, Any]) -> pd.Series:
    """
    Bollinger Band Mean Reversion.
    Long when Close < Lower Band
    Short when Close > Upper Band
    Exit at Mean
    """
    bb_dev = params.get("bb_dev", 2.0)

    signal = pd.Series(0, index=df.index)

    # Long: Price breaks below lower band
    long_cond = df["close"] < df["bb_lower"]

    # Short/Exit: Price breaks above upper or mean
    exit_cond = df["close"] > df["sma_20"]

    # Vectorized state masking is tricky without iteration,
    # but for simple "In Market" signal:

    signal[long_cond] = 1
    signal[exit_cond] = 0

    # Forward fill to hold position until exit?
    # Vectorized "Stateful" fill:
    # 1 = Enter, 0 = Exit, NaN = Hold
    # We need a custom logic for 'Hold'

    # Simple workaround for pure vector:
    # Mark entry as 1, exit as -1
    raw_sig = pd.Series(0, index=df.index)
    raw_sig[long_cond] = 1
    raw_sig[exit_cond] = -1  # Signal to close

    # Forward fill 1s until -1
    # Replace 0 with NaN, ffill, then fillna(0)
    # This logic needs care.
    # If 1 happens, we hold until -1 happens.

    # Let's use a simpler proxy for vectorized speed:
    # Valid only if Close < SMA_20 (Below mean)
    # AND entered at Lower Band

    # Better: Re-implement explicit state loop in Numba/Cython if needed,
    # but for pure pandas:

    regime = raw_sig.replace(0, np.nan).ffill().fillna(0)
    # regime is 1 (Long) or -1 (Closed). Map -1 to 0.
    final_signal = regime.map({1: 1, -1: 0, 0: 0})

    return final_signal


def trend_following_strategy(df: pd.DataFrame, params: Dict[str, Any]) -> pd.Series:
    """
    EMA Crossover.
    Long when EMA_12 > EMA_26
    """
    fast = params.get("fast_period", 12)
    slow = params.get("slow_period", 26)

    signal = pd.Series(0, index=df.index)

    long_cond = df["ema_12"] > df["ema_26"]

    signal[long_cond] = 1

    return signal
