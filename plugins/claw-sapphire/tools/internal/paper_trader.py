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
import ssl
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

SAPPHIRE_DIR = Path.home() / "Code" / "Sapphire"
PORTFOLIO_FILE = SAPPHIRE_DIR / "data" / "paper_portfolio.json"

# Signal pipeline integration — write outcome back when positions close
_ALPHA_DIR = SAPPHIRE_DIR / "services" / "alpha"
if str(_ALPHA_DIR) not in sys.path:
    sys.path.insert(0, str(_ALPHA_DIR))

try:
    from signal_pipeline import pipeline as _signal_pipeline

    _PIPELINE_AVAILABLE = True
except ImportError:
    _PIPELINE_AVAILABLE = False


def _record_outcome(pipeline_id: str, pnl_usd: float, close_price: float = 0.0) -> None:
    """Write trade outcome back to the signal JSONL audit trail."""
    if not (_PIPELINE_AVAILABLE and pipeline_id):
        return
    outcome = "win" if pnl_usd > 0 else ("break_even" if pnl_usd == 0 else "loss")
    _signal_pipeline.update_signal_outcome(pipeline_id, outcome, pnl_usd, close_price)


# Paper trading config
INITIAL_CAPITAL = 100_000.0  # $100K paper money
POSITION_SIZE_PCT = 0.10  # 10% of capital per trade
STOP_LOSS_ATR_MULT = 1.5  # Stop at 1.5x ATR below entry
TAKE_PROFIT_ATR_MULT = 2.5  # TP at 2.5x ATR above entry (1.67:1 R:R)
FEE_RATE_PER_LEG = 0.004  # 0.40% per side to model retail friction
ROUND_TRIP_FEE_RATE = FEE_RATE_PER_LEG * 2


def _round_money(value: float) -> float:
    return round(float(value), 2)


def _normalize_position(pos: dict) -> dict:
    qty = float(pos.get("qty", 0.0) or 0.0)
    entry_price = float(pos.get("entry_price", 0.0) or 0.0)
    original_qty = float(pos.get("original_qty", qty) or qty)

    pos["qty"] = qty
    pos["original_qty"] = original_qty
    pos["size_usd"] = _round_money(entry_price * qty)
    pos["original_size_usd"] = _round_money(
        float(pos.get("original_size_usd", entry_price * original_qty) or 0.0)
    )

    estimated_entry_fee = float(
        pos.get(
            "estimated_entry_fee_usd",
            pos["original_size_usd"] * FEE_RATE_PER_LEG,
        )
        or 0.0
    )
    remaining_entry_fee = float(pos.get("remaining_entry_fee_usd", estimated_entry_fee) or 0.0)

    pos["estimated_entry_fee_usd"] = _round_money(estimated_entry_fee)
    pos["remaining_entry_fee_usd"] = _round_money(
        max(0.0, min(estimated_entry_fee, remaining_entry_fee))
    )
    pos["realized_pnl_usd"] = _round_money(float(pos.get("realized_pnl_usd", 0.0) or 0.0))
    return pos


def _normalize_portfolio(pf: dict) -> dict:
    pf.setdefault("capital", INITIAL_CAPITAL)
    pf.setdefault("initial_capital", pf["capital"])
    pf.setdefault("positions", [])
    pf.setdefault("history", [])
    pf.setdefault("created_at", datetime.now(UTC).isoformat())
    pf["positions"] = [_normalize_position(pos) for pos in pf.get("positions", [])]
    return pf


def _load_portfolio() -> dict:
    if PORTFOLIO_FILE.exists():
        return _normalize_portfolio(json.loads(PORTFOLIO_FILE.read_text(encoding="utf-8")))
    return _normalize_portfolio(
        {
            "capital": INITIAL_CAPITAL,
            "initial_capital": INITIAL_CAPITAL,
            "positions": [],  # Open positions
            "history": [],  # Closed trades
            "created_at": datetime.now(UTC).isoformat(),
        }
    )


def _save_portfolio(pf: dict):
    _normalize_portfolio(pf)
    PORTFOLIO_FILE.parent.mkdir(parents=True, exist_ok=True)
    PORTFOLIO_FILE.write_text(json.dumps(pf, indent=2, default=str))


def _ssl_ctx() -> ssl.SSLContext:
    """Build an SSL context that uses certifi certs (macOS Python 3.12 fix)."""
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _get_price(symbol: str) -> float | None:
    """Get current price from CoinGecko."""
    sym_map = {"BTCUSDT": "bitcoin", "ETHUSDT": "ethereum", "SOLUSDT": "solana"}
    cg_id = sym_map.get(symbol)
    if not cg_id:
        return None
    try:
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={cg_id}&vs_currencies=usd"
        with urllib.request.urlopen(url, timeout=10, context=_ssl_ctx()) as r:
            data = json.loads(r.read())
        return data[cg_id]["usd"]
    except Exception:
        return None


def _gross_pnl(pos: dict, exit_price: float, qty: float | None = None) -> float:
    close_qty = pos["qty"] if qty is None else qty
    if pos["side"] == "BUY":
        return (exit_price - pos["entry_price"]) * close_qty
    return (pos["entry_price"] - exit_price) * close_qty


def _exit_fee(exit_price: float, qty: float) -> float:
    return _round_money(exit_price * qty * FEE_RATE_PER_LEG)


def _allocate_entry_fee(pos: dict, qty: float) -> float:
    open_qty = float(pos.get("qty", 0.0) or 0.0)
    remaining_entry_fee = float(pos.get("remaining_entry_fee_usd", 0.0) or 0.0)
    if open_qty <= 0 or remaining_entry_fee <= 0:
        return 0.0
    if qty >= open_qty - 1e-12:
        return _round_money(remaining_entry_fee)
    return _round_money(remaining_entry_fee * (qty / open_qty))


def _net_unrealized_pnl(pos: dict, current_price: float) -> tuple[float, float, float]:
    gross = _round_money(_gross_pnl(pos, current_price))
    close_fee = _exit_fee(current_price, pos["qty"])
    net = _round_money(gross - pos.get("remaining_entry_fee_usd", 0.0) - close_fee)
    return gross, close_fee, net


def _close_position_slice(
    pf: dict,
    pos: dict,
    exit_price: float,
    reason: str,
    qty: float | None = None,
) -> tuple[dict, bool, float]:
    _normalize_position(pos)
    open_qty = float(pos["qty"])
    if open_qty <= 0:
        raise ValueError("cannot close an empty position")

    close_qty = open_qty if qty is None else min(float(qty), open_qty)
    snapshot = dict(pos)
    gross_pnl = _round_money(_gross_pnl(snapshot, exit_price, close_qty))
    entry_fee = _allocate_entry_fee(snapshot, close_qty)
    exit_fee = _exit_fee(exit_price, close_qty)
    net_pnl = _round_money(gross_pnl - entry_fee - exit_fee)

    remaining_qty = 0.0 if close_qty >= open_qty - 1e-12 else round(open_qty - close_qty, 12)
    remaining_entry_fee = (
        0.0
        if remaining_qty == 0.0
        else _round_money(snapshot["remaining_entry_fee_usd"] - entry_fee)
    )

    pos["qty"] = remaining_qty
    pos["size_usd"] = _round_money(pos["entry_price"] * remaining_qty)
    pos["remaining_entry_fee_usd"] = remaining_entry_fee
    pos["realized_pnl_usd"] = _round_money(pos.get("realized_pnl_usd", 0.0) + net_pnl)

    trade = {
        **snapshot,
        "qty": close_qty,
        "size_usd": _round_money(snapshot["entry_price"] * close_qty),
        "exit_price": exit_price,
        "gross_pnl": gross_pnl,
        "entry_fee_usd": entry_fee,
        "exit_fee_usd": exit_fee,
        "fees_usd": _round_money(entry_fee + exit_fee),
        "pnl": net_pnl,
        "exit_reason": reason,
        "closed_at": datetime.now(UTC).isoformat(),
        "remaining_qty": remaining_qty,
        "cumulative_pnl_usd": pos["realized_pnl_usd"],
        "partial_exit": remaining_qty > 0,
    }
    pf["history"].append(trade)
    pf["capital"] = _round_money(float(pf.get("capital", 0.0) or 0.0) + net_pnl)
    return trade, remaining_qty == 0.0, pos["realized_pnl_usd"]


def action_execute(
    symbol: str,
    side: str,
    price: float,
    atr: float = None,
    confidence: float = 0.5,
    kelly_size_pct: float = None,
    edge: float = None,
    pipeline_id: str = "",
) -> dict:
    """Execute a paper trade with optional Half-Kelly sizing from signal generator."""
    if price <= 0:
        return {"error": "Price must be > 0"}

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
    entry_fee = _round_money(size_usd * FEE_RATE_PER_LEG)

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
        "original_size_usd": size_usd,
        "stop_loss": round(stop_loss, 2),
        "take_profit": round(take_profit, 2),
        "partial_tp": round(
            price + atr * 1.0 if side.upper() == "BUY" else price - atr * 1.0, 2
        ),  # Partial at 1 ATR
        "peak_price": price,
        "trailing_active": False,
        "partial_taken": False,
        "atr": atr,
        "edge": edge,
        "confidence": confidence,
        "pipeline_id": pipeline_id,  # links back to signal_pipeline audit JSONL
        "estimated_entry_fee_usd": entry_fee,
        "remaining_entry_fee_usd": entry_fee,
        "realized_pnl_usd": 0.0,
        "opened_at": datetime.now(UTC).isoformat(),
    }

    pf["positions"].append(position)
    _save_portfolio(pf)

    return {
        "success": True,
        "trade": f"{side.upper()} {qty:.6f} {symbol} @ ${price:,.2f}",
        "size": f"${size_usd:,.0f}",
        "entry_fee": f"${entry_fee:,.2f}",
        "estimated_round_trip_friction": f"${size_usd * ROUND_TRIP_FEE_RATE:,.2f}",
        "stop_loss": f"${stop_loss:,.2f}",
        "take_profit": f"${take_profit:,.2f}",
        "risk_reward": f"1:{TAKE_PROFIT_ATR_MULT / STOP_LOSS_ATR_MULT:.1f}",
    }


def action_check_stops() -> dict:
    """Check positions: partial profit, trailing stops, SL/TP. Inspired by Polymarket strategies."""
    pf = _load_portfolio()
    closed = []
    partial_exits = []

    remaining = []
    for pos in pf["positions"]:
        _normalize_position(pos)
        current = _get_price(pos["symbol"])
        if current is None:
            remaining.append(pos)
            continue

        is_long = pos["side"] == "BUY"
        entry = pos["entry_price"]
        pnl_bps = (
            ((current - entry) / entry * 10000) if is_long else ((entry - current) / entry * 10000)
        )

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
                trade, _closed_final, _total_trade_pnl = _close_position_slice(
                    pf, pos, current, "partial_50pct", qty=half_qty
                )
                pos["partial_taken"] = True
                partial_exits.append(
                    {
                        "symbol": pos["symbol"],
                        "pnl": round(trade["pnl"], 2),
                        "reason": "partial_50pct",
                        "remaining_qty": pos["qty"],
                    }
                )

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
                    trade, _finalized, total_trade_pnl = _close_position_slice(
                        pf, pos, current, "trailing_stop"
                    )
                    _record_outcome(pos.get("pipeline_id", ""), total_trade_pnl, current)
                    closed.append(trade)
                    continue
            else:
                trail_level = peak * (1 + TRAILING_DISTANCE_BPS / 10000)
                if current >= trail_level:
                    trade, _finalized, total_trade_pnl = _close_position_slice(
                        pf, pos, current, "trailing_stop"
                    )
                    _record_outcome(pos.get("pipeline_id", ""), total_trade_pnl, current)
                    closed.append(trade)
                    continue

        # ─── Hard stop loss / take profit ───
        hit_stop = (current <= pos["stop_loss"]) if is_long else (current >= pos["stop_loss"])
        hit_tp = (current >= pos["take_profit"]) if is_long else (current <= pos["take_profit"])

        if hit_stop or hit_tp:
            exit_price = current  # Use actual price, not the level
            trade, _finalized, total_trade_pnl = _close_position_slice(
                pf,
                pos,
                exit_price,
                "stop_loss" if hit_stop else "take_profit",
            )
            _record_outcome(pos.get("pipeline_id", ""), total_trade_pnl, exit_price)
            closed.append(trade)
        else:
            remaining.append(pos)

    pf["positions"] = remaining
    _save_portfolio(pf)

    return {
        "closed": len(closed),
        "partial_exits": len(partial_exits),
        "details": [
            {"symbol": t["symbol"], "pnl": f"${t['pnl']:+,.2f}", "reason": t["exit_reason"]}
            for t in closed
        ],
        "partials": [
            {"symbol": p["symbol"], "pnl": f"${p['pnl']:+,.2f}", "remaining": p["remaining_qty"]}
            for p in partial_exits
        ],
    }


def action_monitor() -> dict:
    """Read-only preview: what would `check_stops` do at current prices?

    Walks open positions and returns the *intended* trigger for each one
    without mutating portfolio state, taking partial profit, or recording
    outcomes. Useful for dashboards, alerts, and operator review before
    actually firing `check_stops`.
    """
    pf = _load_portfolio()
    rows: list[dict] = []
    summary = {
        "would_close": 0,
        "would_partial": 0,
        "would_trail": 0,
        "no_action": 0,
        "no_price": 0,
    }

    TRAILING_ACTIVATE_BPS = 60
    TRAILING_DISTANCE_BPS = 40

    for pos in pf["positions"]:
        _normalize_position(pos)
        current = _get_price(pos["symbol"])
        if current is None:
            rows.append(
                {
                    "symbol": pos["symbol"],
                    "side": pos["side"],
                    "trigger": "no_price",
                    "current": None,
                    "reason": "price feed unavailable",
                }
            )
            summary["no_price"] += 1
            continue

        is_long = pos["side"] == "BUY"
        entry = pos["entry_price"]
        pnl_bps = (
            ((current - entry) / entry * 10000) if is_long else ((entry - current) / entry * 10000)
        )

        peak = pos.get("peak_price", entry)
        if is_long:
            peak = max(peak, current)
        else:
            peak = min(peak, current)

        partial_tp = pos.get("partial_tp")
        partial_taken = bool(pos.get("partial_taken", False))
        partial_ready = bool(
            partial_tp
            and not partial_taken
            and ((current >= partial_tp) if is_long else (current <= partial_tp))
        )

        trailing_active = bool(pos.get("trailing_active") or pnl_bps >= TRAILING_ACTIVATE_BPS)
        if trailing_active:
            if is_long:
                trail_level = peak * (1 - TRAILING_DISTANCE_BPS / 10000)
                trailing_breach = current <= trail_level
            else:
                trail_level = peak * (1 + TRAILING_DISTANCE_BPS / 10000)
                trailing_breach = current >= trail_level
        else:
            trail_level = None
            trailing_breach = False

        hit_stop = (current <= pos["stop_loss"]) if is_long else (current >= pos["stop_loss"])
        hit_tp = (current >= pos["take_profit"]) if is_long else (current <= pos["take_profit"])

        if trailing_breach:
            trigger = "trailing_stop"
            summary["would_close"] += 1
            summary["would_trail"] += 1
        elif hit_stop:
            trigger = "stop_loss"
            summary["would_close"] += 1
        elif hit_tp:
            trigger = "take_profit"
            summary["would_close"] += 1
        elif partial_ready:
            trigger = "partial_50pct"
            summary["would_partial"] += 1
        else:
            trigger = "hold"
            summary["no_action"] += 1

        rows.append(
            {
                "symbol": pos["symbol"],
                "side": pos["side"],
                "entry": pos["entry_price"],
                "current": current,
                "peak": peak,
                "stop_loss": pos["stop_loss"],
                "take_profit": pos["take_profit"],
                "partial_tp": partial_tp,
                "partial_taken": partial_taken,
                "trailing_active": trailing_active,
                "trail_level": trail_level,
                "pnl_bps": round(pnl_bps, 2),
                "trigger": trigger,
            }
        )

    return {
        "mode": "monitor_dry_run",
        "writes": False,
        "open_positions": len(pf["positions"]),
        "summary": summary,
        "rows": rows,
    }


def action_positions() -> dict:
    """Show open positions with unrealized PnL."""
    pf = _load_portfolio()
    positions = []
    unrealized_total = 0.0

    for pos in pf["positions"]:
        _normalize_position(pos)
        current = _get_price(pos["symbol"])
        if current:
            gross_unrealized, close_fee, unrealized = _net_unrealized_pnl(pos, current)
            fees_if_closed = _round_money(pos["remaining_entry_fee_usd"] + close_fee)
        else:
            gross_unrealized = 0
            unrealized = 0
            fees_if_closed = _round_money(pos.get("remaining_entry_fee_usd", 0.0))
        unrealized_total += unrealized

        positions.append(
            {
                "symbol": pos["symbol"],
                "side": pos["side"],
                "entry": f"${pos['entry_price']:,.2f}",
                "current": f"${current:,.2f}" if current else "?",
                "unrealized_pnl": f"${unrealized:+,.2f}",
                "gross_unrealized_pnl": f"${gross_unrealized:+,.2f}",
                "fees_if_closed_now": f"${fees_if_closed:,.2f}",
                "stop": f"${pos['stop_loss']:,.2f}",
                "tp": f"${pos['take_profit']:,.2f}",
            }
        )

    liquidation_value = _round_money(pf["capital"] + unrealized_total)
    return {
        "capital": f"${pf['capital']:,.2f}",
        "estimated_liquidation_value": f"${liquidation_value:,.2f}",
        "open_positions": len(positions),
        "positions": positions,
    }


def action_close(symbol: str) -> dict:
    """Close a position at current market price."""
    pf = _load_portfolio()
    current = _get_price(symbol)
    if current is None:
        return {"error": f"Can't get price for {symbol}"}

    for i, pos in enumerate(pf["positions"]):
        if pos["symbol"] == symbol:
            trade, finalized, total_trade_pnl = _close_position_slice(pf, pos, current, "manual")
            if finalized:
                pf["positions"].pop(i)
            _save_portfolio(pf)
            _record_outcome(pos.get("pipeline_id", ""), total_trade_pnl, current)
            return {
                "success": True,
                "pnl": f"${trade['pnl']:+,.2f}",
                "fees": f"${trade['fees_usd']:,.2f}",
                "capital": f"${pf['capital']:,.2f}",
            }

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
    total_fees = sum(t.get("fees_usd", 0.0) for t in history)
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
        downside_dev = math.sqrt(sum(p**2 for p in neg_pnls) / len(pnls))
        avg_return = sum(pnls) / len(pnls)
        sortino = avg_return / downside_dev if downside_dev > 0 else 0
    else:
        sortino = 0

    return {
        "total_trades": len(history),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": f"{len(wins) / len(history) * 100:.0f}%",
        "total_pnl": f"${total_pnl:+,.2f}",
        "total_fees": f"${total_fees:,.2f}",
        "avg_win": f"${avg_win:+,.2f}",
        "avg_loss": f"${avg_loss:+,.2f}",
        "capital": f"${pf['capital']:,.2f}",
        "total_return": f"{(pf['capital'] / pf['initial_capital'] - 1) * 100:+.1f}%",
        "max_drawdown": f"{max_dd:.1f}%",
        "sortino_ratio": round(sortino, 2),
        "profit_factor": f"{abs(sum(t['pnl'] for t in wins)) / abs(sum(t['pnl'] for t in losses)):.2f}"
        if losses and sum(t["pnl"] for t in losses) != 0
        else "∞",
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
            params.get("pipeline_id", ""),
        )
    elif action == "check_stops":
        result = action_check_stops()
    elif action == "monitor":
        result = action_monitor()
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
