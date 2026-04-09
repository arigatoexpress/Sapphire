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

import json
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

SAPPHIRE_DIR = Path.home() / "Code" / "Sapphire"
SIGNALS_FILE = SAPPHIRE_DIR / "data" / "trading_signals.jsonl"
NOTIFY_TOOL = SAPPHIRE_DIR / "plugins" / "claw-sapphire" / "tools" / "notify.py"


def _notify(msg: str, priority: str = "p1"):
    """Send Telegram notification."""
    try:
        subprocess.run(["python3", str(NOTIFY_TOOL), msg, "--priority", priority],
                      capture_output=True, timeout=15)
    except Exception:
        pass


def _log_signal(signal: dict):
    """Append signal to trading_signals.jsonl."""
    with open(SIGNALS_FILE, "a") as f:
        f.write(json.dumps(signal) + "\n")


def scan_for_signals(symbols: list[str] = None) -> dict:
    """Scan markets for trading signals using real TA."""
    from technical_analysis import analyze_all, TechnicalProfile

    symbols = symbols or ["BTC", "ETH", "SOL"]
    profiles = analyze_all()

    signals_generated = []
    now = datetime.now(timezone.utc)

    for sym in symbols:
        profile = profiles.get(sym)
        if profile is None:
            continue

        triggers = []

        # RSI signals
        if profile.rsi_14 < 30:
            triggers.append(("BUY", f"RSI oversold ({profile.rsi_14:.0f})", "rsi_oversold"))
        elif profile.rsi_14 > 70:
            triggers.append(("SELL", f"RSI overbought ({profile.rsi_14:.0f})", "rsi_overbought"))

        # MACD cross signals
        if profile.macd_cross == "bullish_cross":
            triggers.append(("BUY", "MACD bullish cross", "macd_bull"))
        elif profile.macd_cross == "bearish_cross":
            triggers.append(("SELL", "MACD bearish cross", "macd_bear"))

        # Bollinger Band signals
        if profile.bb_position == "below_lower":
            triggers.append(("BUY", f"Price below lower BB (${profile.price:,.0f})", "bb_oversold"))
        elif profile.bb_position == "above_upper":
            triggers.append(("SELL", f"Price above upper BB (${profile.price:,.0f})", "bb_overbought"))

        # Strong multi-signal alignment
        if profile.net_signal == "strong_bullish" and profile.signal_count_bullish >= 4:
            triggers.append(("BUY", f"Strong bullish alignment ({profile.signal_count_bullish} signals)", "strong_bull"))
        elif profile.net_signal == "strong_bearish" and profile.signal_count_bearish >= 4:
            triggers.append(("SELL", f"Strong bearish alignment ({profile.signal_count_bearish} signals)", "strong_bear"))

        # MA trend reversal (only when it just happened — check if 7 and 20 are very close)
        ma_gap_pct = abs(profile.sma_7 - profile.sma_20) / profile.sma_20 * 100 if profile.sma_20 else 0
        if ma_gap_pct < 0.5 and profile.ma_trend == "bullish":
            triggers.append(("BUY", f"MA7 crossing above MA20 (gap {ma_gap_pct:.1f}%)", "ma_cross_bull"))
        elif ma_gap_pct < 0.5 and profile.ma_trend == "bearish":
            triggers.append(("SELL", f"MA7 crossing below MA20 (gap {ma_gap_pct:.1f}%)", "ma_cross_bear"))

        for action, reason, trigger_type in triggers:
            confidence = 0.6
            if "strong" in trigger_type:
                confidence = 0.85
            elif "rsi" in trigger_type:
                confidence = 0.75
            elif "macd" in trigger_type:
                confidence = 0.70

            signal = {
                "timestamp": now.isoformat(),
                "symbol": f"{sym}USDT",
                "action": action,
                "strategy": trigger_type,
                "price": profile.price,
                "confidence": confidence,
                "signal_id": str(uuid.uuid4()),
                "source": "sapphire-ta-scanner",
                "execution": "LOGGED_ONLY",
                "raw": {
                    "trigger": trigger_type,
                    "reason": reason,
                    "rsi": profile.rsi_14,
                    "macd_cross": profile.macd_cross,
                    "ma_trend": profile.ma_trend,
                    "bb_position": profile.bb_position,
                    "net_signal": profile.net_signal,
                    "signals_bullish": profile.signal_count_bullish,
                    "signals_bearish": profile.signal_count_bearish,
                    "atr_pct": profile.atr_pct,
                    "volume_signal": profile.volume_signal,
                    "source": "sapphire-ta-scanner",
                },
            }

            _log_signal(signal)
            signals_generated.append({
                "symbol": f"{sym}USDT",
                "action": action,
                "reason": reason,
                "confidence": confidence,
                "price": profile.price,
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
