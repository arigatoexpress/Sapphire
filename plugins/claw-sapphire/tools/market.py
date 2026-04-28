#!/usr/bin/env python3
"""sapphire_market — unified market data tool for claw-code.

Input schema:
    {"action": "quote", "symbol": "AAPL"}
    {"action": "crypto", "symbol": "BTC-USD", "start_date": "2026-03-28"}
    {"action": "tv_quote"}
    {"action": "tv_levels", "filter": "NY Sessions"}
    {"action": "pine_ci", "path": "~/Code/Sapphire/pine/v3_ultra/main.pine"}
    {"action": "snapshot", "symbols": ["AAPL", "MSFT", "NVDA"]}
    {"action": "news", "query": "bitcoin"}
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))
from market_data import (
    MarketQuote,
    crypto_historical,
    equity_historical,
    equity_quote,
    fred_series,
    news,
    pine_ci,
    pine_compile,
    portfolio_snapshot,
    tv_indicator_lines,
    tv_indicator_values,
    tv_ohlcv,
    tv_quote,
    tv_status,
    tv_strategy_results,
)


def main():
    try:
        input_data = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, EOFError):
        if len(sys.argv) > 1:
            input_data = {"action": sys.argv[1]}
            if len(sys.argv) > 2:
                input_data["symbol"] = sys.argv[2]
        else:
            input_data = {"action": "tv_quote"}

    action = input_data.get("action", "tv_quote")
    symbol = input_data.get("symbol", "")

    if action == "quote":
        result = equity_quote(symbol, input_data.get("provider", "yfinance"))
        result = asdict(result) if isinstance(result, MarketQuote) else result
    elif action == "historical":
        result = [
            asdict(b) for b in equity_historical(symbol, input_data.get("start_date", "2026-03-01"))
        ]
    elif action == "crypto":
        result = [
            asdict(b) for b in crypto_historical(symbol, input_data.get("start_date", "2026-03-01"))
        ]
    elif action == "fred":
        result = fred_series(symbol, input_data.get("start_date"))
    elif action == "news":
        result = news(input_data.get("query", ""), limit=input_data.get("limit", 10))
    elif action == "snapshot":
        result = portfolio_snapshot(input_data.get("symbols", []))
    elif action == "tv_quote":
        result = tv_quote()
    elif action == "tv_status":
        result = tv_status()
    elif action == "tv_ohlcv":
        result = tv_ohlcv()
    elif action == "tv_values":
        result = tv_indicator_values()
    elif action == "tv_levels":
        result = tv_indicator_lines(input_data.get("filter"))
    elif action == "tv_strategy":
        result = tv_strategy_results()
    elif action == "pine_compile":
        result = pine_compile()
    elif action == "pine_ci":
        result = pine_ci(input_data["path"])
    else:
        result = {"error": f"Unknown action: {action}"}

    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
