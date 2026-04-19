#!/usr/bin/env python3
"""Sapphire Crypto Portfolio — bridges Cointracker into the trading pipeline.

Wraps the Cointracker engine at ~/Code/Cointracker/ to provide:
- Portfolio balance and valuation
- PnL summary (realized + unrealized)
- Tax status (current year obligations)

Actions:
    balance   — Current portfolio holdings with USD values
    pnl       — Realized + unrealized PnL summary
    paper     — Paper trading portfolio status (from paper_trader)

Usage:
    echo '{"action":"balance"}' | python3 crypto_portfolio.py
    echo '{"action":"pnl"}' | python3 crypto_portfolio.py
    echo '{"action":"paper"}' | python3 crypto_portfolio.py
"""

from __future__ import annotations

import json
import ssl
import subprocess
import sys
import urllib.request
from pathlib import Path

SAPPHIRE_DIR = Path.home() / "Code" / "Sapphire"
COINTRACKER_DIR = Path.home() / "Code" / "Cointracker"
PAPER_PORTFOLIO = SAPPHIRE_DIR / "data" / "paper_portfolio.json"


def _ssl_ctx() -> ssl.SSLContext:
    """Build an SSL context that uses certifi certs (macOS Python 3.12 fix)."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _get_prices() -> dict:
    """Get live crypto prices."""
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,solana,cosmos,osmosis&vs_currencies=usd&include_24hr_change=true"
        with urllib.request.urlopen(url, timeout=10, context=_ssl_ctx()) as r:
            return json.loads(r.read())
    except Exception:
        return {}


def action_paper() -> dict:
    """Show paper trading portfolio from our execution engine."""
    if not PAPER_PORTFOLIO.exists():
        return {"error": "No paper portfolio. Run paper_trader.py first."}

    pf = json.loads(PAPER_PORTFOLIO.read_text())
    prices = _get_prices()
    price_map = {
        "BTCUSDT": prices.get("bitcoin", {}).get("usd"),
        "ETHUSDT": prices.get("ethereum", {}).get("usd"),
        "SOLUSDT": prices.get("solana", {}).get("usd"),
    }

    total_unrealized = 0
    positions = []
    for pos in pf.get("positions", []):
        current = price_map.get(pos["symbol"])
        if current:
            if pos["side"] == "BUY":
                unrealized = (current - pos["entry_price"]) * pos["qty"]
            else:
                unrealized = (pos["entry_price"] - current) * pos["qty"]
            total_unrealized += unrealized
            pnl_pct = unrealized / pos["size_usd"] * 100
        else:
            unrealized = 0
            pnl_pct = 0

        positions.append({
            "symbol": pos["symbol"],
            "side": pos["side"],
            "entry": pos["entry_price"],
            "current": current,
            "qty": pos["qty"],
            "unrealized": round(unrealized, 2),
            "pnl_pct": round(pnl_pct, 2),
        })

    total_realized = sum(t.get("pnl", 0) for t in pf.get("history", []))
    equity = pf["capital"] + total_unrealized

    return {
        "type": "paper",
        "capital": pf["capital"],
        "equity": round(equity, 2),
        "total_return_pct": round((equity / pf["initial_capital"] - 1) * 100, 2),
        "realized_pnl": round(total_realized, 2),
        "unrealized_pnl": round(total_unrealized, 2),
        "open_positions": len(positions),
        "closed_trades": len(pf.get("history", [])),
        "positions": positions,
    }


def action_balance() -> dict:
    """Get live portfolio balance summary combining paper + real (if available)."""
    paper = action_paper() if PAPER_PORTFOLIO.exists() else None
    prices = _get_prices()

    result = {
        "prices": {
            "BTC": prices.get("bitcoin", {}).get("usd"),
            "ETH": prices.get("ethereum", {}).get("usd"),
            "SOL": prices.get("solana", {}).get("usd"),
        },
        "paper_portfolio": paper,
    }

    # Try to get Cointracker balance
    try:
        r = subprocess.run(
            [sys.executable, "-m", "src.main", "balance"],
            capture_output=True, text=True, timeout=15,
            cwd=str(COINTRACKER_DIR),
        )
        if r.returncode == 0:
            result["cointracker"] = r.stdout.strip()
    except Exception:
        result["cointracker"] = "unavailable"

    return result


def main():
    raw = sys.stdin.read().strip()
    params = json.loads(raw) if raw else {"action": "paper"}
    action = params.get("action", "paper")

    if action == "paper":
        result = action_paper()
    elif action == "balance":
        result = action_balance()
    else:
        result = {"error": f"Unknown action: {action}"}

    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
