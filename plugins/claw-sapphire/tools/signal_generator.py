#!/usr/bin/env python3
"""Sapphire Signal Generator — autonomous trading signals from real TA.

Instead of waiting for TradingView alerts, this actively scans markets
using our technical analysis library and generates signals when conditions
are met. Signals are logged to trading_signals.jsonl and sent to Telegram.

Trigger conditions:
- RSI crosses below 30 (oversold) or above 70 (overbought)
- MACD bullish/bearish cross
- Price breaks above/below Bollinger Bands
- MA trend reversal (7 crosses 20)
- Multiple signals align (strong signal)

Usage:
    echo '{"action":"scan"}' | python3 signal_generator.py
    echo '{"action":"scan","symbols":["BTC","ETH","SOL"]}' | python3 signal_generator.py
"""

from __future__ import annotations

import contextlib
import json
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

SAPPHIRE_DIR = Path.home() / "Code" / "Sapphire"
SIGNALS_FILE = SAPPHIRE_DIR / "data" / "trading_signals.jsonl"
NOTIFY_TOOL = SAPPHIRE_DIR / "plugins" / "claw-sapphire" / "tools" / "notify.py"


def _notify(msg: str, priority: str = "p1"):
    """Send Telegram notification."""
    with contextlib.suppress(Exception):
        subprocess.run(["python3", str(NOTIFY_TOOL), msg, "--priority", priority],
                      capture_output=True, timeout=15)


def _log_signal(signal: dict):
    """Append signal to trading_signals.jsonl."""
    with open(SIGNALS_FILE, "a") as f:
        f.write(json.dumps(signal) + "\n")


def scan_for_signals(symbols: list[str] = None) -> dict:
    """Scan markets for trading signals using real TA."""
    from technical_analysis import analyze_all

    symbols = symbols or ["BTC", "ETH", "SOL"]
    profiles = analyze_all()

    signals_generated = []
    now = datetime.now(UTC)

    for sym in symbols:
        profile = profiles.get(sym)
        if profile is None:
            continue

        # ─── Multi-Factor Ensemble (inspired by Polymarket AI Forecast) ───
        # 6 independent factors, require 3+ agreement for signal
        factors = []  # (direction: "BUY"/"SELL"/"NEUTRAL", strength: 0-1, name: str)

        # Factor 1: MA Trend (EMA/SMA crossover)
        if profile.ma_trend == "bullish":
            ma_gap = abs(profile.sma_7 - profile.sma_20) / profile.sma_20 if profile.sma_20 else 0
            factors.append(("BUY", min(1.0, ma_gap * 20), "MA↑"))
        elif profile.ma_trend == "bearish":
            ma_gap = abs(profile.sma_7 - profile.sma_20) / profile.sma_20 if profile.sma_20 else 0
            factors.append(("SELL", min(1.0, ma_gap * 20), "MA↓"))

        # Factor 2: RSI — contrarian at extremes, confirming in middle
        if profile.rsi_14 < 30:
            factors.append(("BUY", min(1.0, (30 - profile.rsi_14) / 20), f"RSI{profile.rsi_14:.0f}"))
        elif profile.rsi_14 > 70:
            factors.append(("SELL", min(1.0, (profile.rsi_14 - 70) / 20), f"RSI{profile.rsi_14:.0f}"))
        elif 40 < profile.rsi_14 < 60:
            pass  # Neutral zone — no factor
        elif profile.rsi_14 <= 40:
            factors.append(("SELL", 0.3, f"RSI{profile.rsi_14:.0f}"))
        else:  # 60-70
            factors.append(("BUY", 0.3, f"RSI{profile.rsi_14:.0f}"))

        # Factor 3: MACD cross
        if profile.macd_cross == "bullish_cross":
            factors.append(("BUY", 0.8, "MACD↑"))
        elif profile.macd_cross == "bearish_cross":
            factors.append(("SELL", 0.8, "MACD↓"))

        # Factor 4: Bollinger position (mean reversion)
        if profile.bb_position == "below_lower":
            factors.append(("BUY", 0.7, "BB<low"))
        elif profile.bb_position == "above_upper":
            factors.append(("SELL", 0.7, "BB>high"))

        # Factor 5: Volume confirmation
        if profile.volume_ratio > 1.5:
            # High volume confirms direction of price move
            if profile.change_24h_pct > 0:
                factors.append(("BUY", min(1.0, profile.volume_ratio / 3), "Vol↑"))
            elif profile.change_24h_pct < 0:
                factors.append(("SELL", min(1.0, profile.volume_ratio / 3), "Vol↑"))
        elif profile.volume_ratio < 0.5:
            # Low volume = exhaustion, expect reversal
            if profile.change_24h_pct > 1:
                factors.append(("SELL", 0.4, "VolExhaust"))
            elif profile.change_24h_pct < -1:
                factors.append(("BUY", 0.4, "VolExhaust"))

        # Factor 6: 7-day momentum (price acceleration)
        if profile.change_7d_pct > 5:
            factors.append(("BUY", min(1.0, profile.change_7d_pct / 15), "7d↑"))
        elif profile.change_7d_pct < -5:
            factors.append(("SELL", min(1.0, abs(profile.change_7d_pct) / 15), "7d↓"))

        # ─── Agreement Gate: require 3+ factors in same direction ───
        buy_factors = [(s, n) for d, s, n in factors if d == "BUY"]
        sell_factors = [(s, n) for d, s, n in factors if d == "SELL"]

        buy_count = len(buy_factors)
        sell_count = len(sell_factors)
        buy_strength = sum(s for s, _ in buy_factors) / max(buy_count, 1)
        sell_strength = sum(s for s, _ in sell_factors) / max(sell_count, 1)

        MIN_FACTORS = 3  # Require 3+ agreement
        action = None
        reason_parts = []

        if buy_count >= MIN_FACTORS and buy_count > sell_count:
            action = "BUY"
            reason_parts = [n for _, n in buy_factors]
            avg_strength = buy_strength
            agreement = buy_count / max(len(factors), 1)
        elif sell_count >= MIN_FACTORS and sell_count > buy_count:
            action = "SELL"
            reason_parts = [n for _, n in sell_factors]
            avg_strength = sell_strength
            agreement = sell_count / max(len(factors), 1)

        if action is None:
            continue  # No consensus — skip this symbol

        # ─── Confidence: agreement ratio + strength ───
        # Adapted from AI Forecast: min(0.90, 0.3 + agreement*0.3 + strength*0.2)
        confidence = min(0.90, 0.30 + agreement * 0.30 + avg_strength * 0.20)

        # ─── Volatility regime adjustment ───
        if profile.volatility_regime == "high":
            confidence *= 0.7  # Reduce in volatile markets
        elif profile.volatility_regime == "low":
            confidence *= 1.1  # Boost in calm markets

        confidence = round(min(0.90, max(0.35, confidence)), 2)

        # ─── Edge + Half-Kelly sizing hint ───
        edge = min(0.06, avg_strength * agreement * 0.1)
        win_prob = 0.5 + edge
        kelly_frac = max(0, (win_prob * 2 - 1)) / 2
        suggested_size_pct = round(min(kelly_frac / 2, 0.03) * 100, 1)  # % of capital

        reason = f"{len(reason_parts)}F ensemble: {' '.join(reason_parts)}"

        signal = {
            "timestamp": now.isoformat(),
            "symbol": f"{sym}USDT",
            "action": action,
            "strategy": "multi_factor_ensemble",
            "price": profile.price,
            "confidence": confidence,
            "signal_id": str(uuid.uuid4()),
            "source": "sapphire-ta-scanner-v2",
            "execution": "LOGGED_ONLY",
            "raw": {
                "factors": len(factors),
                "agreeing": max(buy_count, sell_count),
                "agreement_ratio": round(agreement, 2),
                "avg_strength": round(avg_strength, 2),
                "edge": round(edge, 4),
                "kelly_size_pct": suggested_size_pct,
                "volatility_regime": profile.volatility_regime,
                "reason": reason,
                "factor_names": reason_parts,
                "rsi": profile.rsi_14,
                "macd_cross": profile.macd_cross,
                "ma_trend": profile.ma_trend,
                "bb_position": profile.bb_position,
                "volume_ratio": profile.volume_ratio,
                "change_7d_pct": profile.change_7d_pct,
                "source": "sapphire-ta-scanner-v2",
            },
        }

        _log_signal(signal)
        signals_generated.append({
            "symbol": f"{sym}USDT",
            "action": action,
            "reason": reason,
            "confidence": confidence,
            "price": profile.price,
            "edge": round(edge, 4),
            "kelly_size": f"{suggested_size_pct}%",
        })

    # Send Telegram notification if any signals
    if signals_generated:
        lines = ["📡 *Signal Scanner*\n"]
        for s in signals_generated:
            icon = "🟢" if s["action"] == "BUY" else "🔴"
            lines.append(f"{icon} {s['symbol']} {s['action']} ${s['price']:,.0f}")
            lines.append(f"   {s['reason']} (conf {s['confidence']:.0%})")
        _notify("\n".join(lines), priority="p1")

    return {
        "success": True,
        "signals": len(signals_generated),
        "details": signals_generated,
        "market_summary": {
            sym: {
                "price": p.price,
                "rsi": round(p.rsi_14, 1),
                "macd": p.macd_cross,
                "ma_trend": p.ma_trend,
                "net_signal": p.net_signal,
            }
            for sym, p in profiles.items() if p
        },
    }


def main():
    raw = sys.stdin.read().strip()
    params = json.loads(raw) if raw else {"action": "scan"}

    if params.get("action") == "scan":
        result = scan_for_signals(params.get("symbols"))
    else:
        result = {"error": f"Unknown action: {params.get('action')}"}

    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
