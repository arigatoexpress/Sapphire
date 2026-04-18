#!/usr/bin/env python3
"""Sapphire Paper Trader — simulated execution engine for signal validation.

Takes signals from signal_generator and executes paper trades to track:
- Open positions with entry price, size, stop-loss, take-profit
- Closed trades with realized PnL
- Portfolio metrics: win rate, avg PnL, Sortino ratio, max drawdown

NO REAL MONEY. This validates signal quality before live execution.

Actions:
    execute   — Execute a paper trade from the latest signal
    positions — Show open positions
    history   — Show trade history + PnL
    metrics   — Portfolio performance metrics
    close     — Close a position at current market price

Usage:
    echo '{"action":"execute","symbol":"BTCUSDT","side":"BUY","price":72000}' | python3 paper_trader.py
    echo '{"action":"positions"}' | python3 paper_trader.py
    echo '{"action":"metrics"}' | python3 paper_trader.py
"""

from __future__ import annotations

import json
import math
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

SAPPHIRE_DIR = Path.home() / "Code" / "Sapphire"
PORTFOLIO_FILE = SAPPHIRE_DIR / "data" / "paper_portfolio.json"

# Paper trading config
INITIAL_CAPITAL = 100_000.0  # $100K paper money
POSITION_SIZE_PCT = 0.10  # 10% of capital per trade
STOP_LOSS_ATR_MULT = 1.5  # Stop at 1.5x ATR below entry
TAKE_PROFIT_ATR_MULT = 2.5  # TP at 2.5x ATR above entry (1.67:1 R:R)


def _load_portfolio() -> dict:
    if PORTFOLIO_FILE.exists():
        return json.loads(PORTFOLIO_FILE.read_text())
    return {
        "capital": INITIAL_CAPITAL,
        "initial_capital": INITIAL_CAPITAL,
        "positions": [],  # Open positions
        "history": [],  # Closed trades
        "created_at": datetime.now(UTC).isoformat(),
    }


def _save_portfolio(pf: dict):
    PORTFOLIO_FILE.parent.mkdir(parents=True, exist_ok=True)
    PORTFOLIO_FILE.write_text(json.dumps(pf, indent=2, default=str))


def _get_price(symbol: str) -> float | None:
    """Get current price from CoinGecko."""
    sym_map = {"BTCUSDT": "bitcoin", "ETHUSDT": "ethereum", "SOLUSDT": "solana"}
    cg_id = sym_map.get(symbol)
    if not cg_id:
        return None
    try:
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={cg_id}&vs_currencies=usd"
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.loads(r.read())
        return data[cg_id]["usd"]
    except Exception:
        return None


def action_execute(symbol: str, side: str, price: float, atr: float = None,
                    confidence: float = 0.5, kelly_size_pct: float = None, edge: float = None) -> dict:
    """Execute a paper trade with optional Half-Kelly sizing from signal generator."""
    pf = _load_portfolio()

    # Check for existing position in same symbol
    for pos in pf["positions"]:
        if pos["symbol"] == symbol:
            return {"error": f"Already have open position in {symbol}. Close it first."}

    # Calculate position size — use Half-Kelly if provided, else default
    if kelly_size_pct and kelly_size_pct > 0:
        size_pct = min(kelly_size_pct / 100, 0.04)  # Cap at 4%
    elif edge and edge > 0:
        win_prob = 0.5 + edge
        kelly_frac = max(0, (win_prob * 2 - 1)) / 2
        size_pct = min(kelly_frac / 2, 0.04)
    else:
        size_pct = POSITION_SIZE_PCT

    size_usd = pf["capital"] * size_pct
    qty = size_usd / price

    # ATR-based stops (default to 3% of price if no ATR)
    if atr is None:
        atr = price * 0.03

    if side.upper() == "BUY":
        stop_loss = price - atr * STOP_LOSS_ATR_MULT
        take_profit = price + atr * TAKE_PROFIT_ATR_MULT
    else:
        stop_loss = price + atr * STOP_LOSS_ATR_MULT
        take_profit = price - atr * TAKE_PROFIT_ATR_MULT

    position = {
        "symbol": symbol,
        "side": side.upper(),
        "entry_price": price,
        "qty": qty,
        "original_qty": qty,
        "size_usd": size_usd,
        "stop_loss": round(stop_loss, 2),
        "take_profit": round(take_profit, 2),
        "partial_tp": round(price + atr * 1.0 if side.upper() == "BUY" else price - atr * 1.0, 2),  # Partial at 1 ATR
        "peak_price": price,
        "trailing_active": False,
        "partial_taken": False,
        "atr": atr,
        "edge": edge,
        "confidence": confidence,
        "opened_at": datetime.now(UTC).isoformat(),
    }

    pf["positions"].append(position)
    _save_portfolio(pf)

    return {
        "success": True,
        "trade": f"{side.upper()} {qty:.6f} {symbol} @ ${price:,.2f}",
        "size": f"${size_usd:,.0f}",
        "stop_loss": f"${stop_loss:,.2f}",
        "take_profit": f"${take_profit:,.2f}",
        "risk_reward": f"1:{TAKE_PROFIT_ATR_MULT/STOP_LOSS_ATR_MULT:.1f}",
    }


def action_check_stops() -> dict:
    """Check positions: partial profit, trailing stops, SL/TP. Inspired by Polymarket strategies."""
    pf = _load_portfolio()
    closed = []
    partial_exits = []

    remaining = []
    for pos in pf["positions"]:
        current = _get_price(pos["symbol"])
        if current is None:
            remaining.append(pos)
            continue

        is_long = pos["side"] == "BUY"
        entry = pos["entry_price"]
        pnl_bps = ((current - entry) / entry * 10000) if is_long else ((entry - current) / entry * 10000)

        # Update peak price for trailing stop
        if is_long:
            pos["peak_price"] = max(pos.get("peak_price", entry), current)
        else:
            pos["peak_price"] = min(pos.get("peak_price", entry), current)

        # ─── Partial profit taking: exit 50% at 1 ATR profit ───
        partial_tp = pos.get("partial_tp")
        if partial_tp and not pos.get("partial_taken", False):
            hit_partial = (current >= partial_tp) if is_long else (current <= partial_tp)
            if hit_partial:
                half_qty = pos["qty"] * 0.5
                partial_pnl = (current - entry) * half_qty if is_long else (entry - current) * half_qty
                pos["qty"] -= half_qty
                pos["partial_taken"] = True
                pf["capital"] += partial_pnl
                partial_exits.append({
                    "symbol": pos["symbol"], "pnl": round(partial_pnl, 2),
                    "reason": "partial_50pct", "remaining_qty": pos["qty"]
                })

        # ─── Trailing stop: activate at +60 bps from entry, trail 40 bps from peak ───
        TRAILING_ACTIVATE_BPS = 60
        TRAILING_DISTANCE_BPS = 40

        if pnl_bps >= TRAILING_ACTIVATE_BPS:
            pos["trailing_active"] = True

        if pos.get("trailing_active"):
            peak = pos["peak_price"]
            if is_long:
                trail_level = peak * (1 - TRAILING_DISTANCE_BPS / 10000)
                if current <= trail_level:
                    pnl = (current - entry) * pos["qty"]
                    trade = {**pos, "exit_price": current, "pnl": round(pnl, 2),
                             "exit_reason": "trailing_stop", "closed_at": datetime.now(UTC).isoformat()}
                    pf["history"].append(trade)
                    pf["capital"] += pnl
                    closed.append(trade)
                    continue
            else:
                trail_level = peak * (1 + TRAILING_DISTANCE_BPS / 10000)
                if current >= trail_level:
                    pnl = (entry - current) * pos["qty"]
                    trade = {**pos, "exit_price": current, "pnl": round(pnl, 2),
                             "exit_reason": "trailing_stop", "closed_at": datetime.now(UTC).isoformat()}
                    pf["history"].append(trade)
                    pf["capital"] += pnl
                    closed.append(trade)
                    continue

        # ─── Hard stop loss / take profit ───
        hit_stop = (current <= pos["stop_loss"]) if is_long else (current >= pos["stop_loss"])
        hit_tp = (current >= pos["take_profit"]) if is_long else (current <= pos["take_profit"])

        if hit_stop or hit_tp:
            exit_price = current  # Use actual price, not the level
            pnl = (exit_price - entry) * pos["qty"] if is_long else (entry - exit_price) * pos["qty"]
            trade = {**pos, "exit_price": exit_price, "pnl": round(pnl, 2),
                     "exit_reason": "stop_loss" if hit_stop else "take_profit",
                     "closed_at": datetime.now(UTC).isoformat()}
            pf["history"].append(trade)
            pf["capital"] += pnl
            closed.append(trade)
        else:
            remaining.append(pos)

    pf["positions"] = remaining
    _save_portfolio(pf)

    return {
        "closed": len(closed),
        "partial_exits": len(partial_exits),
        "details": [{
            "symbol": t["symbol"], "pnl": f"${t['pnl']:+,.2f}", "reason": t["exit_reason"]
        } for t in closed],
        "partials": [{
            "symbol": p["symbol"], "pnl": f"${p['pnl']:+,.2f}", "remaining": p["remaining_qty"]
        } for p in partial_exits],
    }


def action_positions() -> dict:
    """Show open positions with unrealized PnL."""
    pf = _load_portfolio()
    positions = []

    for pos in pf["positions"]:
        current = _get_price(pos["symbol"])
        if current:
            if pos["side"] == "BUY":
                unrealized = (current - pos["entry_price"]) * pos["qty"]
            else:
                unrealized = (pos["entry_price"] - current) * pos["qty"]
        else:
            unrealized = 0

        positions.append({
            "symbol": pos["symbol"],
            "side": pos["side"],
            "entry": f"${pos['entry_price']:,.2f}",
            "current": f"${current:,.2f}" if current else "?",
            "unrealized_pnl": f"${unrealized:+,.2f}",
            "stop": f"${pos['stop_loss']:,.2f}",
            "tp": f"${pos['take_profit']:,.2f}",
        })

    return {"capital": f"${pf['capital']:,.2f}", "open_positions": len(positions), "positions": positions}


def action_close(symbol: str) -> dict:
    """Close a position at current market price."""
    pf = _load_portfolio()
    current = _get_price(symbol)
    if current is None:
        return {"error": f"Can't get price for {symbol}"}

    for i, pos in enumerate(pf["positions"]):
        if pos["symbol"] == symbol:
            if pos["side"] == "BUY":
                pnl = (current - pos["entry_price"]) * pos["qty"]
            else:
                pnl = (pos["entry_price"] - current) * pos["qty"]

            trade = {**pos, "exit_price": current, "pnl": round(pnl, 2),
                     "exit_reason": "manual", "closed_at": datetime.now(UTC).isoformat()}
            pf["history"].append(trade)
            pf["capital"] += pnl
            pf["positions"].pop(i)
            _save_portfolio(pf)
            return {"success": True, "pnl": f"${pnl:+,.2f}", "capital": f"${pf['capital']:,.2f}"}

    return {"error": f"No open position in {symbol}"}


def action_metrics() -> dict:
    """Portfolio performance metrics."""
    pf = _load_portfolio()
    history = pf["history"]

    if not history:
        return {
            "total_trades": 0,
            "capital": f"${pf['capital']:,.2f}",
            "total_return": "0.0%",
            "message": "No closed trades yet",
        }

    wins = [t for t in history if t["pnl"] > 0]
    losses = [t for t in history if t["pnl"] <= 0]
    total_pnl = sum(t["pnl"] for t in history)
    pnls = [t["pnl"] for t in history]
    avg_win = sum(t["pnl"] for t in wins) / len(wins) if wins else 0
    avg_loss = sum(t["pnl"] for t in losses) / len(losses) if losses else 0

    # Max drawdown
    peak = pf["initial_capital"]
    max_dd = 0
    equity = pf["initial_capital"]
    for t in history:
        equity += t["pnl"]
        peak = max(peak, equity)
        dd = (peak - equity) / peak * 100
        max_dd = max(max_dd, dd)

    # Sortino ratio (downside deviation only)
    neg_pnls = [p for p in pnls if p < 0]
    if neg_pnls and len(pnls) > 1:
        downside_dev = math.sqrt(sum(p ** 2 for p in neg_pnls) / len(pnls))
        avg_return = sum(pnls) / len(pnls)
        sortino = avg_return / downside_dev if downside_dev > 0 else 0
    else:
        sortino = 0

    return {
        "total_trades": len(history),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": f"{len(wins)/len(history)*100:.0f}%",
        "total_pnl": f"${total_pnl:+,.2f}",
        "avg_win": f"${avg_win:+,.2f}",
        "avg_loss": f"${avg_loss:+,.2f}",
        "capital": f"${pf['capital']:,.2f}",
        "total_return": f"{(pf['capital']/pf['initial_capital']-1)*100:+.1f}%",
        "max_drawdown": f"{max_dd:.1f}%",
        "sortino_ratio": round(sortino, 2),
        "profit_factor": f"{abs(sum(t['pnl'] for t in wins))/abs(sum(t['pnl'] for t in losses)):.2f}" if losses and sum(t['pnl'] for t in losses) != 0 else "∞",
    }


def main():
    raw = sys.stdin.read().strip()
    params = json.loads(raw) if raw else {"action": "positions"}
    action = params.get("action", "positions")

    if action == "execute":
        result = action_execute(
            params.get("symbol", "BTCUSDT"),
            params.get("side", "BUY"),
            params.get("price", 0),
            params.get("atr"),
            params.get("confidence", 0.5),
            params.get("kelly_size_pct"),
            params.get("edge"),
        )
    elif action == "check_stops":
        result = action_check_stops()
    elif action == "positions":
        result = action_positions()
    elif action == "close":
        result = action_close(params.get("symbol", ""))
    elif action == "metrics":
        result = action_metrics()
    elif action == "history":
        pf = _load_portfolio()
        result = {"trades": len(pf["history"]), "history": pf["history"][-10:]}
    else:
        result = {"error": f"Unknown action: {action}"}

    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
