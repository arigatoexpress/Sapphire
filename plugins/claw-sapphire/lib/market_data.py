"""Sapphire market data client — unified interface to OpenBB + TradingView.

OpenBB REST API (port 6900) for historical/fundamental data.
TradingView CLI (tv) for live chart data and Pine Script operations.
"""

from __future__ import annotations

import json
import subprocess
import urllib.request
from dataclasses import dataclass
from typing import Any

OPENBB_BASE = "http://127.0.0.1:6900/api/v1"
TV_BIN = "tv"


@dataclass
class MarketQuote:
    symbol: str
    price: float
    open: float
    high: float
    low: float
    volume: int
    source: str


@dataclass
class OHLCVBar:
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float


def _openbb_get(path: str, params: dict[str, str] | None = None) -> dict:
    """GET request to OpenBB REST API."""
    url = f"{OPENBB_BASE}{path}"
    if params:
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{url}?{qs}"
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}


def _tv_cmd(args: list[str], timeout: int = 10) -> dict:
    """Run a tv CLI command and return parsed JSON."""
    try:
        result = subprocess.run(
            [TV_BIN] + args,
            capture_output=True, text=True, timeout=timeout,
        )
        if result.stdout.strip():
            return json.loads(result.stdout)
        return {"error": result.stderr.strip() or "no output"}
    except json.JSONDecodeError:
        return {"raw": result.stdout.strip()}
    except Exception as e:
        return {"error": str(e)}


# ── Equity Data (via OpenBB) ──────────────────────────────────────

def equity_quote(symbol: str, provider: str = "yfinance") -> MarketQuote | dict:
    """Get real-time equity quote."""
    data = _openbb_get("/equity/price/quote", {"symbol": symbol, "provider": provider})
    results = data.get("results", [])
    if not results:
        return {"error": f"No data for {symbol}", "raw": data}
    r = results[0]
    return MarketQuote(
        symbol=r.get("symbol", symbol),
        price=r.get("last_price", 0),
        open=r.get("open", 0),
        high=r.get("high", 0),
        low=r.get("low", 0),
        volume=r.get("volume", 0),
        source=f"openbb/{provider}",
    )


def equity_historical(symbol: str, start_date: str, provider: str = "yfinance") -> list[OHLCVBar]:
    """Get historical OHLCV bars."""
    data = _openbb_get("/equity/price/historical", {
        "symbol": symbol, "provider": provider, "start_date": start_date,
    })
    return [
        OHLCVBar(
            date=r["date"][:10],
            open=r.get("open", 0), high=r.get("high", 0),
            low=r.get("low", 0), close=r.get("close", 0),
            volume=r.get("volume", 0),
        )
        for r in data.get("results", [])
    ]


# ── Crypto Data (via OpenBB) ─────────────────────────────────────

def crypto_historical(symbol: str, start_date: str, provider: str = "yfinance") -> list[OHLCVBar]:
    """Get historical crypto OHLCV bars."""
    data = _openbb_get("/crypto/price/historical", {
        "symbol": symbol, "provider": provider, "start_date": start_date,
    })
    return [
        OHLCVBar(
            date=r["date"][:10],
            open=r.get("open", 0), high=r.get("high", 0),
            low=r.get("low", 0), close=r.get("close", 0),
            volume=r.get("volume", 0),
        )
        for r in data.get("results", [])
    ]


# ── Macro / Economic Data (via OpenBB) ───────────────────────────

def fred_series(series_id: str, start_date: str | None = None) -> list[dict]:
    """Get FRED economic data series."""
    params = {"symbol": series_id, "provider": "fred"}
    if start_date:
        params["start_date"] = start_date
    data = _openbb_get("/economy/fred_series", params)
    return data.get("results", [])


def news(query: str = "", provider: str = "benzinga", limit: int = 10) -> list[dict]:
    """Get financial news."""
    params = {"provider": provider, "limit": str(limit)}
    if query:
        params["query"] = query
    data = _openbb_get("/news/world", params)
    return data.get("results", [])


# ── TradingView Live Data ────────────────────────────────────────

def tv_quote() -> dict:
    """Get real-time quote from active TradingView chart."""
    return _tv_cmd(["quote"])


def tv_status() -> dict:
    """Get TradingView CDP connection status."""
    return _tv_cmd(["status"])


def tv_ohlcv(summary: bool = True) -> dict:
    """Get OHLCV bars from active chart."""
    args = ["ohlcv"]
    if summary:
        args.append("--summary")
    return _tv_cmd(args, timeout=15)


def tv_indicator_values() -> dict:
    """Get current indicator values from data window."""
    return _tv_cmd(["values"])


def tv_indicator_lines(filter_name: str | None = None) -> dict:
    """Get drawn lines/levels from indicators."""
    args = ["data", "lines"]
    if filter_name:
        args.extend(["--filter", filter_name])
    return _tv_cmd(args, timeout=15)


def tv_strategy_results() -> dict:
    """Get strategy tester results."""
    return _tv_cmd(["data", "strategy"], timeout=15)


# ── Pine Script Operations ───────────────────────────────────────

def pine_compile() -> dict:
    """Compile the current Pine Script in the editor."""
    return _tv_cmd(["pine", "compile"], timeout=30)


def pine_set(script: str) -> dict:
    """Set Pine Script content in the editor."""
    try:
        result = subprocess.run(
            [TV_BIN, "pine", "set"],
            input=script, capture_output=True, text=True, timeout=10,
        )
        return json.loads(result.stdout) if result.stdout.strip() else {"success": result.returncode == 0}
    except Exception as e:
        return {"error": str(e)}


def pine_analyze(script: str) -> dict:
    """Analyze Pine Script for errors without compiling."""
    try:
        result = subprocess.run(
            [TV_BIN, "pine", "analyze"],
            input=script, capture_output=True, text=True, timeout=10,
        )
        return json.loads(result.stdout) if result.stdout.strip() else {"raw": result.stderr.strip()}
    except Exception as e:
        return {"error": str(e)}


def pine_ci(script_path: str) -> dict:
    """Full Pine CI pipeline: analyze → set → compile → read errors."""
    from pathlib import Path
    script = Path(script_path).read_text()

    # Step 1: Static analysis
    analysis = pine_analyze(script)
    if analysis.get("errors"):
        return {"stage": "analyze", "errors": analysis["errors"], "success": False}

    # Step 2: Set in editor
    set_result = pine_set(script)
    if not set_result.get("success", True):
        return {"stage": "set", "error": set_result, "success": False}

    # Step 3: Compile
    compile_result = pine_compile()
    if compile_result.get("errors"):
        return {"stage": "compile", "errors": compile_result["errors"], "success": False}

    return {"stage": "complete", "success": True, "compile": compile_result}


# ── Convenience: Multi-Symbol Snapshot ───────────────────────────

def portfolio_snapshot(symbols: list[str], provider: str = "yfinance") -> list[dict]:
    """Get quick snapshot of multiple symbols."""
    results = []
    for sym in symbols:
        q = equity_quote(sym, provider)
        if isinstance(q, MarketQuote):
            results.append({
                "symbol": q.symbol, "price": q.price,
                "high": q.high, "low": q.low, "volume": q.volume,
            })
        else:
            results.append({"symbol": sym, "error": q.get("error", "unknown")})
    return results
