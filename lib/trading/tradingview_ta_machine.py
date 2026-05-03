"""TradingView TA machine planner for Sapphire.

This module does not mutate TradingView, submit orders, or send alerts. It
turns Sapphire's market universe into a ranked TradingView watchlist plus
operator-gated chart work orders that the local TradingView MCP/CLI can apply.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

from lib.trading.strategy_lab import asset_spec, build_market_universe

DEFAULT_WATCHLIST_NAME = "Sapphire Dynamic TA"
DEFAULT_LIMIT = 18
DEFAULT_TIMEFRAMES = ("15", "60", "240", "D")
CORE_SYMBOLS = {"BTC", "ETH", "SOL", "HYPE", "ZEC"}
WATCHLIST_SCHEMA_VERSION = "trading-workbench.watchlist.v1"
WORK_ORDER_SCHEMA_VERSION = "trading-workbench.work_orders.v1"

INDICATOR_STACK: tuple[dict[str, Any], ...] = (
    {
        "id": "ema_trend",
        "tradingview_name": "Moving Average Exponential",
        "purpose": "trend",
        "inputs": {"length": 20},
    },
    {
        "id": "rsi_14",
        "tradingview_name": "Relative Strength Index",
        "purpose": "momentum_overbought_oversold",
        "inputs": {"length": 14},
    },
    {
        "id": "macd",
        "tradingview_name": "MACD",
        "purpose": "momentum_cross_and_histogram",
        "inputs": {"fast_length": 12, "slow_length": 26, "signal_length": 9},
    },
    {
        "id": "bollinger_bands",
        "tradingview_name": "Bollinger Bands",
        "purpose": "volatility_envelope",
        "inputs": {"length": 20, "mult": 2},
    },
    {
        "id": "volume",
        "tradingview_name": "Volume",
        "purpose": "participation_confirmation",
        "inputs": {},
    },
)


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _priority_score(priority: Any) -> int:
    value = str(priority or "").strip().lower()
    return {
        "critical": 85,
        "high": 72,
        "medium": 52,
        "watch": 36,
        "low": 24,
    }.get(value, 40)


def _tag_score(tags: list[str]) -> int:
    weights = {
        "preferred": 9,
        "core": 8,
        "aligned": 8,
        "liked": 7,
        "perp": 4,
        "robinhood": 4,
        "hyperliquid": 4,
        "trending": 5,
        "privacy": 3,
        "ai": 3,
        "rwa": 3,
        "tokenized_finance": 3,
    }
    return sum(weights.get(str(tag).lower(), 0) for tag in tags)


def _momentum_bucket(change_24h_pct: float | None) -> str:
    if change_24h_pct is None:
        return "unknown"
    if change_24h_pct >= 8:
        return "extended_up"
    if change_24h_pct >= 3:
        return "bullish_momentum"
    if change_24h_pct <= -8:
        return "capitulation_watch"
    if change_24h_pct <= -3:
        return "bearish_momentum"
    return "range"


def _attention_score(row: dict[str, Any], *, source_rank: int) -> int:
    tags = [str(tag).lower() for tag in row.get("tags") or []]
    change = row.get("change_24h_pct")
    change_float = _safe_float(change, 0.0) if change is not None else 0.0
    symbol = str(row.get("symbol") or "")
    trend_score = row.get("trend_score")
    score = _priority_score(row.get("priority")) + _tag_score(tags)
    if symbol in CORE_SYMBOLS:
        score += 12
    if row.get("hyperliquid_symbol"):
        score += 5
    if row.get("robinhood_symbol"):
        score += 5
    if abs(change_float) >= 8:
        score += 12
    elif abs(change_float) >= 3:
        score += 7
    if trend_score is not None:
        score += max(0, 12 - int(_safe_float(trend_score, 12)))
    return max(0, score - source_rank)


def _chart_url(tradingview_symbol: str) -> str:
    return "https://www.tradingview.com/chart/?symbol=" + quote(tradingview_symbol, safe="")


def _prefixed_tradingview_symbol(value: Any) -> str:
    symbol = str(value or "").strip().upper()
    if not symbol:
        return ""
    if ":" in symbol:
        return symbol
    compact = symbol.replace("/", "").replace("-", "")
    if compact.endswith(("USDT", "USD", "BTC", "ETH")):
        return f"BINANCE:{compact}"
    return compact


def _symbol_row(row: dict[str, Any], *, rank: int, source_rank: int) -> dict[str, Any]:
    symbol = str(row.get("symbol") or "").upper()
    tradingview_symbol = _prefixed_tradingview_symbol(
        row.get("tradingview_symbol") or row.get("tradingview") or symbol
    )
    change = row.get("change_24h_pct")
    change_float = _safe_float(change, 0.0) if change is not None else None
    attention = _attention_score(row, source_rank=source_rank)
    bucket = _momentum_bucket(change_float)
    return {
        "rank": rank,
        "symbol": symbol,
        "name": row.get("name") or symbol,
        "tradingview_symbol": tradingview_symbol,
        "chart_url": _chart_url(tradingview_symbol),
        "priority": str(row.get("priority") or "watch").lower(),
        "attention_score": attention,
        "change_24h_pct": change_float,
        "momentum_bucket": bucket,
        "tags": list(row.get("tags") or []),
        "source": row.get("source") or "sapphire",
        "hyperliquid_symbol": row.get("hyperliquid_symbol"),
        "robinhood_symbol": row.get("robinhood_symbol"),
        "timeframes": list(DEFAULT_TIMEFRAMES),
        "ta_state": "pending_tradingview_readback",
        "readback_required": [
            "ohlcv_summary",
            "indicator_values",
            "chart_screenshot",
            "pine_lines_labels_tables_if_present",
        ],
    }


def _rank_watchlist_rows(market_universe: dict[str, Any], *, limit: int) -> list[dict[str, Any]]:
    candidates = market_universe.get("combined_tokens") or [
        *(market_universe.get("liked_tokens") or []),
        *(market_universe.get("trending_tokens") or []),
    ]
    seen: set[str] = set()
    unique: list[tuple[int, dict[str, Any]]] = []
    for idx, row in enumerate(candidates):
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol") or "").upper()
        tv_symbol = str(row.get("tradingview_symbol") or row.get("tradingview") or "").upper()
        key = symbol or tv_symbol
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append((idx, row))

    scored = [
        (
            _attention_score(row, source_rank=idx),
            str(row.get("symbol") or ""),
            idx,
            row,
        )
        for idx, row in unique
    ]
    scored.sort(key=lambda item: (-item[0], item[2], item[1]))
    return [
        _symbol_row(row, rank=rank, source_rank=idx)
        for rank, (_score, _symbol, idx, row) in enumerate(scored[: max(1, limit)], start=1)
    ]


def _watchlist_txt(symbols: list[dict[str, Any]]) -> str:
    return ",".join(row["tradingview_symbol"] for row in symbols if row.get("tradingview_symbol"))


def _mutation_commands(symbol: dict[str, Any]) -> list[str]:
    tv_symbol = symbol["tradingview_symbol"]
    return [
        f"tv watchlist add {tv_symbol}",
        f"tv symbol {tv_symbol}",
        "tv timeframe 60",
        *(f'tv indicator add "{row["tradingview_name"]}"' for row in INDICATOR_STACK),
    ]


def _readback_commands(symbol: dict[str, Any]) -> list[str]:
    safe_symbol = str(symbol["symbol"]).replace("/", "_").replace(":", "_")
    return [
        "tv state",
        "tv ohlcv --summary -n 120",
        "tv values",
        "tv data lines -f Sapphire",
        "tv data labels -f Sapphire",
        "tv data tables -f Sapphire",
        f"tv screenshot -r chart -o sapphire_{safe_symbol}_ta",
    ]


def _work_orders(symbols: list[dict[str, Any]], *, max_orders: int = 8) -> list[dict[str, Any]]:
    orders: list[dict[str, Any]] = []
    for symbol in symbols[:max_orders]:
        orders.append(
            {
                "id": f"tv-ta-{symbol['rank']:02d}-{symbol['symbol'].lower()}",
                "rank": symbol["rank"],
                "symbol": symbol["symbol"],
                "tradingview_symbol": symbol["tradingview_symbol"],
                "layout": "single_or_2x2_rotation",
                "primary_timeframe": "60",
                "confirmation_timeframes": ["15", "240", "D"],
                "indicator_stack": [row["id"] for row in INDICATOR_STACK],
                "operator_gated_mutation_commands": _mutation_commands(symbol),
                "read_only_readback_commands": _readback_commands(symbol),
                "ta_questions": [
                    "Is RSI confirming trend, diverging, or at an exhaustion zone?",
                    "Does MACD histogram agree with the 20 EMA slope?",
                    "Is price interacting with Bollinger outer bands or mean-reverting?",
                    "Does volume confirm the last impulse?",
                    "Are higher timeframe and 1h posture aligned?",
                ],
                "execution_policy": "analysis_only_no_order_submit",
            }
        )
    return orders


def _pair_analysis() -> list[dict[str, Any]]:
    return [
        {
            "symbol": "ETHBTC",
            "tradingview_symbol": "BINANCE:ETHBTC",
            "purpose": "ETH relative strength versus BTC",
            "timeframes": ["60", "240", "D"],
            "work_order": "Watch RSI divergence and 20 EMA slope; no direct trade route.",
        },
        {
            "symbol": "SOLBTC",
            "tradingview_symbol": "BINANCE:SOLBTC",
            "purpose": "SOL relative strength versus BTC",
            "timeframes": ["60", "240", "D"],
            "work_order": "Use as confirmation for SOL/BTC rotation, not standalone execution.",
        },
    ]


def build_tradingview_ta_machine(
    *,
    fetch_live: bool = True,
    limit: int = DEFAULT_LIMIT,
    market_universe: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build Sapphire's dynamic TradingView watchlist and TA work orders."""
    market = market_universe or build_market_universe(fetch_live=fetch_live)
    symbols = _rank_watchlist_rows(market, limit=limit)
    watchlist_txt = _watchlist_txt(symbols)
    return {
        "generated_at": _now_iso(),
        "mode": "tradingview_ta_machine_plan",
        "watchlist_name": DEFAULT_WATCHLIST_NAME,
        "safety": {
            "live_trading_enabled": False,
            "telegram_sends_enabled": False,
            "browser_mutation_enabled_by_default": False,
            "mutation_gate": "SAPPHIRE_TV_MUTATION_ENABLED=1 plus explicit apply command",
            "execution_policy": "analysis_only_no_order_submit",
        },
        "watchlist": {
            "name": DEFAULT_WATCHLIST_NAME,
            "format": "tradingview_txt_comma_separated_exchange_prefixed_symbols",
            "symbols_txt": watchlist_txt,
            "symbol_count": len(symbols),
            "symbols": symbols,
            "import_notes": [
                "TradingView watchlist import expects a .txt file.",
                "Symbols are exchange-prefixed and comma-separated.",
                "This export is safe to review before any UI mutation.",
            ],
        },
        "indicator_stack": list(INDICATOR_STACK),
        "chart_layout": {
            "default_layout": "2x2",
            "pane_rotation": [
                {"pane": 0, "timeframe": "15", "purpose": "entry timing"},
                {"pane": 1, "timeframe": "60", "purpose": "primary TA decision"},
                {"pane": 2, "timeframe": "240", "purpose": "swing confirmation"},
                {"pane": 3, "timeframe": "D", "purpose": "regime/context"},
            ],
            "setup_commands": ["tv pane layout 2x2"],
        },
        "work_orders": _work_orders(symbols),
        "pair_analysis": _pair_analysis(),
        "alert_template": {
            "symbol": "{{ticker}}",
            "exchange": "{{exchange}}",
            "interval": "{{interval}}",
            "time": "{{time}}",
            "close": "{{close}}",
            "volume": "{{volume}}",
            "action": "{{strategy.order.action}}",
            "price": "{{strategy.order.price}}",
            "strategy": "sapphire_tv_ta_machine",
            "mode": "paper",
        },
        "automation_lanes": {
            "safe_now": [
                "generate watchlist TXT",
                "rank symbols from Sapphire market universe",
                "read chart state, OHLCV summaries, indicator values, Pine tables, and screenshots",
            ],
            "operator_gated_mutation": [
                "add symbols to actual TradingView watchlist",
                "change active chart symbols/timeframes",
                "add or remove chart indicators",
                "inject or save Pine scripts",
                "create or modify TradingView alerts",
            ],
            "never_automatic": [
                "submit/cancel/replace broker orders",
                "enable TradingView execution from webhook paths",
                "send real Telegram trading alerts without an explicit dry-run override review",
                "redistribute TradingView market data outside the local operator workspace",
            ],
        },
        "source_market_universe": {
            "generated_at": market.get("generated_at"),
            "source": market.get("source"),
            "stale": bool(market.get("stale")),
            "errors": market.get("errors") or [],
        },
        "cache_ttl_seconds": 300,
    }


def build_tradingview_watchlist_txt(
    *,
    fetch_live: bool = True,
    limit: int = DEFAULT_LIMIT,
    market_universe: dict[str, Any] | None = None,
) -> str:
    """Return the TradingView-compatible watchlist TXT body."""
    plan = build_tradingview_ta_machine(
        fetch_live=fetch_live,
        limit=limit,
        market_universe=market_universe,
    )
    return str(plan["watchlist"]["symbols_txt"])


def _requested_market_universe(symbols: list[str]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for raw in symbols:
        spec = asset_spec(raw)
        rows.append(
            {
                "symbol": spec.symbol,
                "name": spec.name,
                "coingecko_id": spec.coingecko_id,
                "tradingview_symbol": spec.tradingview_symbol,
                "yfinance_symbol": spec.yfinance_symbol,
                "hyperliquid_symbol": spec.hyperliquid_symbol,
                "robinhood_symbol": spec.robinhood_symbol,
                "priority": spec.priority,
                "tags": list(spec.tags),
                "source": "operator_request",
            }
        )
    return {
        "generated_at": _now_iso(),
        "source": "operator_request",
        "stale": False,
        "errors": [],
        "liked_tokens": rows,
        "trending_tokens": [],
        "combined_tokens": rows,
        "venue_matrix": [],
    }


def build_trading_workbench_watchlist(
    *,
    fetch_live: bool = True,
    limit: int = DEFAULT_LIMIT,
    symbols: list[str] | None = None,
) -> dict[str, Any]:
    """Return a stable read-only workbench watchlist contract."""
    market = _requested_market_universe(symbols) if symbols else None
    plan = build_tradingview_ta_machine(
        fetch_live=fetch_live,
        limit=limit,
        market_universe=market,
    )
    items = []
    for row in plan["watchlist"]["symbols"]:
        items.append(
            {
                "symbol": row["symbol"],
                "canonical_symbol": row["symbol"],
                "tradingview_symbol": row["tradingview_symbol"],
                "chart_url": row["chart_url"],
                "venue_status": {
                    "tradingview": "available",
                    "hyperliquid": "available" if row.get("hyperliquid_symbol") else "unavailable",
                    "robinhood_crypto": "available"
                    if row.get("robinhood_symbol")
                    else "unavailable",
                },
                "tags": row.get("tags") or [],
                "priority": round(min(1.0, row["attention_score"] / 100), 3),
                "attention_score": row["attention_score"],
                "sources": ["strategy_lab", "tradingview_ta_machine"],
                "ta_status": row["ta_state"],
                "forecast": None,
                "pine_candidates": [],
            }
        )
    return {
        "schema_version": WATCHLIST_SCHEMA_VERSION,
        "generated_at": plan["generated_at"],
        "mode": "read_only",
        "execution_enabled": False,
        "telegram_sends_enabled": False,
        "items": items,
        "watchlist": plan["watchlist"],
        "safety": {
            "blocked_actions": [
                "trade_submit",
                "telegram_send",
                "browser_mutation",
                "webhook_post",
            ],
            "execution_policy": "analysis_only_no_order_submit",
        },
        "source_market_universe": plan["source_market_universe"],
    }


def build_trading_workbench_work_order_preview(
    *,
    symbols: list[str] | None = None,
    timeframes: list[str] | None = None,
    jobs: list[str] | None = None,
    strategies: list[str] | None = None,
    allow_live_trading: bool = False,
    allow_telegram: bool = False,
    allow_browser_mutation: bool = False,
) -> dict[str, Any]:
    """Preview chart/TA work orders without posting webhooks or touching TradingView."""
    requested_symbols = symbols or ["BTC", "ETH", "SOL", "HYPE"]
    requested_timeframes = timeframes or ["60", "240", "D"]
    requested_jobs = jobs or [
        "ta_profile",
        "forecast",
        "correlation",
        "backtest_summary",
        "pine_preview",
        "chart_plan",
    ]
    requested_strategies = strategies or ["SapphireComposite", "RegimeAwareRSI"]
    market = _requested_market_universe(requested_symbols)
    plan = build_tradingview_ta_machine(
        fetch_live=False,
        limit=len(requested_symbols),
        market_universe=market,
    )
    blocked_actions = []
    if not allow_live_trading:
        blocked_actions.append("trade_submit")
    if not allow_telegram:
        blocked_actions.append("telegram_send")
    if not allow_browser_mutation:
        blocked_actions.append("browser_mutation")
    blocked_actions.append("webhook_post")

    work_orders: list[dict[str, Any]] = []
    for row in plan["watchlist"]["symbols"]:
        for timeframe in requested_timeframes:
            steps = [
                {"kind": job, "status": "planned"} for job in requested_jobs if job != "chart_plan"
            ]
            steps.append(
                {
                    "kind": "chart_action",
                    "status": "planned" if allow_browser_mutation else "blocked",
                    "reason": None if allow_browser_mutation else "browser_mutation_disabled",
                }
            )
            work_orders.append(
                {
                    "id": f"wo-tv-ta-{row['symbol'].lower()}-{timeframe}",
                    "type": "ta_chart_review",
                    "symbol": row["symbol"],
                    "tradingview_symbol": row["tradingview_symbol"],
                    "timeframe": timeframe,
                    "strategies": requested_strategies,
                    "steps": steps,
                    "artifacts": {
                        "pine_source": None,
                        "validator": None,
                    },
                    "blocked_actions": blocked_actions,
                }
            )
    return {
        "schema_version": WORK_ORDER_SCHEMA_VERSION,
        "generated_at": _now_iso(),
        "mode": "preview_only",
        "execution_enabled": False,
        "telegram_sends_enabled": False,
        "browser_mutation_enabled": bool(allow_browser_mutation),
        "work_orders": work_orders,
        "blocked_actions": blocked_actions,
        "source": "tradingview_ta_machine",
    }
