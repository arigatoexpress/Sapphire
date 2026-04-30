"""Dry-run trading strategy lab for TradingView, Robinhood, and Hyperliquid.

This module is intentionally non-mutating. It enumerates the venue surfaces that
Sapphire can test against, normalizes the token universe, fetches read-only
market context, and builds order drafts that never sign or submit orders.
"""

from __future__ import annotations

import os
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AssetSpec:
    symbol: str
    name: str
    coingecko_id: str
    tradingview_symbol: str
    yfinance_symbol: str
    hyperliquid_symbol: str | None = None
    robinhood_symbol: str | None = None
    priority: str = "medium"
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class OrderDraft:
    venue: str
    mode: str
    symbol: str
    action: str
    notional_usd: float
    execution_enabled: bool
    payload: dict[str, Any]
    notes: tuple[str, ...] = ()


TRADINGVIEW_DOCS = (
    "https://www.tradingview.com/support/solutions/43000529348-how-to-configure-webhook-alerts/",
    "https://www.tradingview.com/support/solutions/43000531021-how-to-use-a-variable-value-in-alert/",
    "https://www.tradingview.com/charting-library-docs/latest/trading_terminal/",
    "https://www.tradingview.com/broker-api-docs/rest-api-spec/",
)

VENUE_DOCS = {
    "robinhood_crypto": "https://robinhood.com/us/en/support/articles/crypto-api/",
    "robinhood_crypto_api": "https://docs.robinhood.com/crypto/trading/",
    "robinhood_chain": "https://docs.robinhood.com/chain/connecting/",
    "hyperliquid_info": "https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint",
    "hyperliquid_exchange": "https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/exchange-endpoint",
    "coingecko_trending": "https://docs.coingecko.com/reference/trending-search",
}

ROBINHOOD_CRYPTO_BASE_URL = "https://trading.robinhood.com"
ROBINHOOD_CRYPTO_V2_ORDER_ENDPOINT = "/api/v2/crypto/trading/orders/"
ROBINHOOD_CRYPTO_V2_ESTIMATED_PRICE_ENDPOINT = "/api/v2/crypto/trading/estimated_price/"
ROBINHOOD_FIRST_REAL_FUNDS_TEST_MAX_USD = 5.0
ROBINHOOD_DAILY_REAL_FUNDS_TEST_MAX_USD = 10.0

ROBINHOOD_AUTH_ENV_VARS = ("".join(("ROBINHOOD_", "API", "_KEY")), "ROBINHOOD_ED25519_PRIVATE_B64")
ROBINHOOD_AUTH_FILE_NAMES = (
    "".join(("robinhood_", "api", "_key")),
    "robinhood_ed25519_private.b64",
)

ROBINHOOD_CHAIN_TESTNET = {
    "network_name": "Robinhood Chain Testnet",
    "chain_id": 46630,
    "currency_symbol": "ETH",
    "rpc_public": "https://rpc.testnet.chain.robinhood.com",
    "block_explorer": "https://explorer.testnet.chain.robinhood.com",
    "stock_tokens": {
        "TSLA": "0xC9f9c86933092BbbfFF3CCb4b105A4A94bf3Bd4E",
        "AMZN": "0x5884aD2f920c162CFBbACc88C9C51AA75eC09E02",
        "PLTR": "0x1FBE1a0e43594b3455993B5dE5Fd0A7A266298d0",
        "NFLX": "0x3b8262A63d25f0477c4DDE23F83cfe22Cb768C93",
        "AMD": "0x71178BAc73cBeb415514eB542a8995b82669778d",
    },
}

ASSET_SPECS: dict[str, AssetSpec] = {
    "BTC": AssetSpec(
        "BTC",
        "Bitcoin",
        "bitcoin",
        "BINANCE:BTCUSDT",
        "BTC-USD",
        "BTC",
        "BTC-USD",
        "high",
        ("aligned", "liked", "perp", "robinhood"),
    ),
    "ETH": AssetSpec(
        "ETH",
        "Ethereum",
        "ethereum",
        "BINANCE:ETHUSDT",
        "ETH-USD",
        "ETH",
        "ETH-USD",
        "high",
        ("core", "preferred", "liked", "perp", "robinhood", "ethereum_zone"),
    ),
    "SOL": AssetSpec(
        "SOL",
        "Solana",
        "solana",
        "BINANCE:SOLUSDT",
        "SOL-USD",
        "SOL",
        "SOL-USD",
        "high",
        ("core", "liked", "perp", "robinhood"),
    ),
    "HYPE": AssetSpec(
        "HYPE",
        "Hyperliquid",
        "hyperliquid",
        "HYPEUSDT",
        "HYPE-USD",
        "HYPE",
        None,
        "high",
        ("liked", "hyperliquid", "perp"),
    ),
    "ZEC": AssetSpec(
        "ZEC",
        "Zcash",
        "zcash",
        "BINANCE:ZECUSDT",
        "ZEC-USD",
        "ZEC",
        "ZEC-USD",
        "medium",
        ("liked", "privacy", "perp"),
    ),
    "XMR": AssetSpec(
        "XMR",
        "Monero",
        "monero",
        "KRAKEN:XMRUSD",
        "XMR-USD",
        None,
        None,
        "watch",
        ("liked", "privacy", "paper"),
    ),
    "LINK": AssetSpec(
        "LINK",
        "Chainlink",
        "chainlink",
        "BINANCE:LINKUSDT",
        "LINK-USD",
        "LINK",
        "LINK-USD",
        "medium",
        ("oracle", "perp"),
    ),
    "ARB": AssetSpec(
        "ARB",
        "Arbitrum",
        "arbitrum",
        "BINANCE:ARBUSDT",
        "ARB-USD",
        "ARB",
        None,
        "medium",
        ("l2", "perp"),
    ),
    "OP": AssetSpec(
        "OP",
        "Optimism",
        "optimism",
        "BINANCE:OPUSDT",
        "OP-USD",
        "OP",
        None,
        "medium",
        ("l2", "ethereum_zone", "perp"),
    ),
    "AVAX": AssetSpec(
        "AVAX",
        "Avalanche",
        "avalanche-2",
        "BINANCE:AVAXUSDT",
        "AVAX-USD",
        "AVAX",
        "AVAX-USD",
        "medium",
        ("l1", "perp"),
    ),
    "AAVE": AssetSpec(
        "AAVE",
        "Aave",
        "aave",
        "BINANCE:AAVEUSDT",
        "AAVE-USD",
        "AAVE",
        "AAVE-USD",
        "medium",
        ("defi", "perp"),
    ),
    "UNI": AssetSpec(
        "UNI",
        "Uniswap",
        "uniswap",
        "BINANCE:UNIUSDT",
        "UNI-USD",
        "UNI",
        None,
        "medium",
        ("defi", "ethereum_zone", "perp"),
    ),
    "ENS": AssetSpec(
        "ENS",
        "Ethereum Name Service",
        "ethereum-name-service",
        "BINANCE:ENSUSDT",
        "ENS-USD",
        None,
        None,
        "watch",
        ("identity", "ethereum_zone", "paper"),
    ),
    "TAO": AssetSpec(
        "TAO",
        "Bittensor",
        "bittensor",
        "BINANCE:TAOUSDT",
        "TAO-USD",
        "TAO",
        None,
        "medium",
        ("ai", "perp"),
    ),
    "ONDO": AssetSpec(
        "ONDO",
        "Ondo",
        "ondo-finance",
        "BINANCE:ONDOUSDT",
        "ONDO-USD",
        "ONDO",
        None,
        "medium",
        ("rwa", "tokenized_finance", "perp"),
    ),
    "POL": AssetSpec(
        "POL",
        "Polygon",
        "polygon-ecosystem-token",
        "BINANCE:POLUSDT",
        "POL-USD",
        "POL",
        None,
        "medium",
        ("l2", "corrected_symbol"),
    ),
    "BNB": AssetSpec(
        "BNB",
        "BNB",
        "binancecoin",
        "BINANCE:BNBUSDT",
        "BNB-USD",
        "BNB",
        None,
        "medium",
        ("exchange", "perp"),
    ),
}

DEFAULT_LIKED_SYMBOLS = (
    "ETH",
    "BTC",
    "ZEC",
    "XMR",
    "AAVE",
    "LINK",
    "ONDO",
    "UNI",
    "ENS",
    "ARB",
    "OP",
    "SOL",
    "HYPE",
    "TAO",
)
CORRECTED_ALIASES = {
    "HYPER": "HYPE",
    "HYPERUSDT": "HYPE",
    "HYPEUSDT": "HYPE",
    "MATIC": "POL",
    "MATICUSDT": "POL",
    "MATICUSD": "POL",
    "POLYGON": "POL",
    "BTCUSDT": "BTC",
    "ETHUSDT": "ETH",
    "SOLUSDT": "SOL",
    "ZECUSDT": "ZEC",
    "XMRUSDT": "XMR",
    "XMRUSD": "XMR",
    "LINKUSDT": "LINK",
    "AVAXUSDT": "AVAX",
    "ARBUSDT": "ARB",
    "OPUSDT": "OP",
    "AAVEUSDT": "AAVE",
    "UNIUSDT": "UNI",
    "ENSUSDT": "ENS",
    "TAOUSDT": "TAO",
    "ONDOUSDT": "ONDO",
}


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def canonicalize_symbol(value: Any) -> str:
    """Normalize TradingView, yfinance, and exchange symbols into Sapphire symbols."""
    raw = str(value or "").strip().upper()
    if not raw:
        return ""
    raw = raw.split(":", 1)[-1].replace("_", "")
    compact = raw.replace("/", "").replace("-", "")
    if compact in CORRECTED_ALIASES:
        return CORRECTED_ALIASES[compact]
    for suffix in ("USDT", "USDC", "USD", "PERP"):
        if compact.endswith(suffix) and len(compact) > len(suffix):
            compact = compact[: -len(suffix)]
            break
    return CORRECTED_ALIASES.get(compact, compact)


def asset_spec(symbol: Any, *, name: str = "", coingecko_id: str = "") -> AssetSpec:
    sym = canonicalize_symbol(symbol)
    if sym in ASSET_SPECS:
        return ASSET_SPECS[sym]
    clean = sym or str(symbol or "").strip().upper() or "UNKNOWN"
    return AssetSpec(
        symbol=clean,
        name=name or clean,
        coingecko_id=coingecko_id,
        tradingview_symbol=f"{clean}USDT",
        yfinance_symbol=f"{clean}-USD",
        hyperliquid_symbol=clean,
        robinhood_symbol=None,
        priority="watch",
        tags=("trending",),
    )


def liked_specs() -> list[AssetSpec]:
    raw = os.getenv("SAPPHIRE_LIKED_TOKENS", "")
    symbols = [s.strip() for s in raw.split(",") if s.strip()] or list(DEFAULT_LIKED_SYMBOLS)
    out: list[AssetSpec] = []
    seen: set[str] = set()
    for symbol in symbols:
        spec = asset_spec(symbol)
        if spec.symbol and spec.symbol not in seen:
            seen.add(spec.symbol)
            out.append(spec)
    return out


def _price_row(price_payload: dict[str, Any], coin_id: str) -> tuple[float | None, float | None]:
    data = price_payload.get(coin_id) if isinstance(price_payload, dict) else None
    if not isinstance(data, dict):
        return None, None
    return _safe_float(data.get("usd")), _safe_float(data.get("usd_24h_change"))


def _asset_row(
    spec: AssetSpec,
    *,
    price_payload: dict[str, Any] | None = None,
    trend_score: int | None = None,
    source: str = "sapphire_liked",
    tags: tuple[str, ...] = (),
) -> dict[str, Any]:
    price, change = _price_row(price_payload or {}, spec.coingecko_id)
    merged_tags = tuple(dict.fromkeys((*spec.tags, *tags)))
    return {
        "symbol": spec.symbol,
        "name": spec.name,
        "coingecko_id": spec.coingecko_id,
        "tradingview_symbol": spec.tradingview_symbol,
        "yfinance_symbol": spec.yfinance_symbol,
        "hyperliquid_symbol": spec.hyperliquid_symbol,
        "robinhood_symbol": spec.robinhood_symbol,
        "priority": spec.priority,
        "tags": list(merged_tags),
        "price_usd": price,
        "change_24h_pct": round(change, 2) if change is not None else None,
        "trend_score": trend_score,
        "source": source,
    }


def parse_trending_tokens(
    payload: dict[str, Any],
    *,
    limit: int = 10,
    liked_symbols: set[str] | None = None,
) -> list[dict[str, Any]]:
    liked_symbols = liked_symbols or set()
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for coin in (payload.get("coins") if isinstance(payload, dict) else []) or []:
        item = coin.get("item") if isinstance(coin, dict) else None
        if not isinstance(item, dict):
            continue
        spec = asset_spec(
            item.get("symbol"),
            name=str(item.get("name") or ""),
            coingecko_id=str(item.get("id") or ""),
        )
        if not spec.symbol or spec.symbol in seen:
            continue
        data = item.get("data") if isinstance(item.get("data"), dict) else {}
        change = (
            data.get("price_change_percentage_24h", {}).get("usd")
            if isinstance(data.get("price_change_percentage_24h"), dict)
            else None
        )
        tags = ["trending"]
        if spec.symbol in liked_symbols:
            tags.append("liked")
        rows.append(
            {
                "symbol": spec.symbol,
                "name": spec.name,
                "coingecko_id": spec.coingecko_id,
                "tradingview_symbol": spec.tradingview_symbol,
                "hyperliquid_symbol": spec.hyperliquid_symbol,
                "robinhood_symbol": spec.robinhood_symbol,
                "market_cap_rank": item.get("market_cap_rank"),
                "price_usd": _safe_float(data.get("price")),
                "change_24h_pct": round(float(change), 2)
                if _safe_float(change) is not None
                else None,
                "trend_score": item.get("score"),
                "tags": tags,
                "source": "coingecko_trending",
            }
        )
        seen.add(spec.symbol)
        if len(rows) >= limit:
            break
    return rows


def build_market_universe(*, fetch_live: bool = True, trend_limit: int = 12) -> dict[str, Any]:
    specs = liked_specs()
    liked_symbols = {spec.symbol for spec in specs}
    errors: list[str] = []
    price_payload: dict[str, Any] = {}
    trending_payload: dict[str, Any] = {}

    if fetch_live:
        try:
            from lib.chain.sources import CoinGeckoClient

            cg = CoinGeckoClient()
            ids = [spec.coingecko_id for spec in specs if spec.coingecko_id]
            price_payload = cg.simple_prices(ids)
            trending_payload = cg.trending_search()
        except Exception as exc:
            errors.append(f"coingecko_unavailable:{type(exc).__name__}")

    liked_rows = [_asset_row(spec, price_payload=price_payload) for spec in specs]
    trending_rows = parse_trending_tokens(
        trending_payload,
        limit=trend_limit,
        liked_symbols=liked_symbols,
    )
    combined: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in [*liked_rows, *trending_rows]:
        sym = row.get("symbol")
        if not sym or sym in seen:
            continue
        seen.add(str(sym))
        combined.append(row)

    return {
        "generated_at": _now_iso(),
        "source": "coingecko" if fetch_live and not errors else "fallback",
        "stale": bool(errors),
        "errors": errors,
        "liked_tokens": liked_rows,
        "trending_tokens": trending_rows,
        "combined_tokens": combined,
        "venue_matrix": [_venue_matrix_row(row) for row in combined],
        "corrected_aliases": dict(sorted(CORRECTED_ALIASES.items())),
        "source_docs": [VENUE_DOCS["coingecko_trending"]],
    }


def _venue_matrix_row(row: dict[str, Any]) -> dict[str, Any]:
    symbol = str(row.get("symbol") or "")
    return {
        "symbol": symbol,
        "name": row.get("name") or symbol,
        "tradingview": row.get("tradingview_symbol") or f"{symbol}USDT",
        "backtest": row.get("yfinance_symbol") or f"{symbol}-USD",
        "hyperliquid": row.get("hyperliquid_symbol"),
        "robinhood_crypto": row.get("robinhood_symbol"),
        "status": _venue_status(row),
        "tags": row.get("tags") or [],
    }


def _venue_status(row: dict[str, Any]) -> str:
    if row.get("robinhood_symbol") and row.get("hyperliquid_symbol"):
        return "paper+read+perp"
    if row.get("hyperliquid_symbol"):
        return "paper+perp"
    if row.get("robinhood_symbol"):
        return "paper+read"
    return "paper"


def build_tradingview_capability_matrix() -> dict[str, Any]:
    """Enumerate TradingView functionality and Sapphire's current depth."""
    return {
        "generated_at": _now_iso(),
        "source_docs": list(TRADINGVIEW_DOCS),
        "alert_template": {
            "symbol": "{{ticker}}",
            "exchange": "{{exchange}}",
            "action": "{{strategy.order.action}}",
            "price": "{{strategy.order.price}}",
            "contracts": "{{strategy.order.contracts}}",
            "market_position": "{{strategy.market_position}}",
            "time": "{{time}}",
            "interval": "{{interval}}",
            "strategy": "{{strategy.order.id}}",
            "mode": "paper",
        },
        "groups": [
            {
                "area": "Alert webhooks",
                "status": "implemented",
                "depth": "json_placeholders_hmac_parser_paper_route",
                "sapphire_surface": [
                    "services/webhook/src/receiver.py",
                    "docs/paper-trading-setup.md",
                ],
                "test_modes": ["unit_parse", "dry_run_payload", "paper_signal"],
            },
            {
                "area": "Pine strategy fills",
                "status": "dry_run_ready",
                "depth": "strategy_order_action_contracts_price_position_template",
                "sapphire_surface": ["lib/trading/strategy_lab.py"],
                "test_modes": ["template_render_review", "webhook_fixture"],
            },
            {
                "area": "Advanced Charts datafeed",
                "status": "enumerated",
                "depth": "symbol_resolution_history_streaming_quotes_required",
                "sapphire_surface": ["services/dashboard/app.py", "lib/analytics/backtest.py"],
                "test_modes": ["readonly_market_data", "backtest_symbols"],
            },
            {
                "area": "Trading Platform Broker API",
                "status": "backlog",
                "depth": "orders_positions_executions_account_manager_dom_mapping_permissions",
                "sapphire_surface": ["lib/trading/strategy_lab.py"],
                "test_modes": ["contract_stub", "paper_broker_fixture"],
            },
            {
                "area": "TradingView Desktop/CDP",
                "status": "observed",
                "depth": "local_tab_health_not_trade_authority",
                "sapphire_surface": ["services/dashboard/app.py"],
                "test_modes": ["cdp_health_probe"],
            },
        ],
        "broker_rest_endpoints": [
            "/config",
            "/accounts",
            "/instruments",
            "/orders",
            "/positions",
            "/executions",
            "/ordersHistory",
            "/mapping",
            "/permissions",
            "/symbol_info",
            "/history",
            "/streaming",
        ],
        "constraints": [
            "webhook_body_must_not_contain_secrets",
            "json_body_gets_application_json",
            "webhook_public_url_must_use_80_or_443",
            "receiver_timeout_budget_under_3s",
            "TRADINGVIEW_EXECUTION_ENABLED=false_until_paper_validation",
        ],
        "mcp_v2_tool_map": {
            "read_safe": [
                "tv status",
                "tv state",
                "tv quote",
                "tv ohlcv --summary",
                "tv values",
                "tv data lines/labels/tables/boxes",
                "tv watchlist get",
                "tv replay status",
                "tv pane list",
                "tv layout list",
                "tv pine analyze --file <path>",
            ],
            "operator_gated": [
                "tv watchlist add <symbol>",
                "tv symbol <symbol>",
                "tv timeframe <resolution>",
                "tv pane layout 2x2",
                "tv pane symbol <pane> <symbol>",
                "tv indicator add \"Relative Strength Index\"",
                "tv indicator set <entity_id> -i '<json>'",
                "tv pine set --file <path>",
                "tv pine compile",
                "tv pine save",
                "tv alert create/delete",
                "tv draw shape/remove/clear",
            ],
            "external_compile": [
                "tv pine check --file <path>",
            ],
            "tos_sensitive": [
                "tv stream quote/bars/values/lines/labels/tables/all",
                "tv batch_run across symbols/timeframes",
                "persistent raw TradingView OHLCV capture",
            ],
            "unsupported": [
                "watchlist remove/reorder through v2 CLI",
                "broker order submit/cancel/replace from TradingView CDP",
                "alert-to-live-trade bridge",
                "TradingView market-data redistribution",
            ],
        },
    }


def normalize_action(action: Any) -> str:
    value = str(action or "").strip().lower()
    if value in {"buy", "long", "entry_long"}:
        return "buy"
    if value in {"sell", "short", "entry_short"}:
        return "sell"
    if value in {"exit", "close", "exit_long", "exit_short", "flat"}:
        return "close"
    return "hold"


def _robinhood_crypto_order_payload(
    *,
    symbol: str,
    action_norm: str,
    notional_usd: float,
) -> dict[str, Any]:
    """Build an official-v2-shaped Robinhood Crypto draft without submit ability."""
    side = "buy" if action_norm == "buy" else "sell" if action_norm in {"sell", "close"} else "hold"
    payload: dict[str, Any] = {
        "api_version": "v2",
        "base_url": ROBINHOOD_CRYPTO_BASE_URL,
        "method": "POST",
        "endpoint": ROBINHOOD_CRYPTO_V2_ORDER_ENDPOINT,
        "query_params": {"account_number": "<robinhood_crypto_account_number>"},
        "symbol": symbol,
        "side": side,
        "requested_notional_usd": notional_usd,
        "credential_required": True,
        "credential_scope_required": [
            "read_crypto_accounts",
            "read_crypto_quotes",
            "place_crypto_orders_with_fee_tiers",
        ],
        "docs": VENUE_DOCS["robinhood_crypto_api"],
        "live_test_caps": {
            "funded_cash_budget_usd": 50.0,
            "first_order_max_notional_usd": ROBINHOOD_FIRST_REAL_FUNDS_TEST_MAX_USD,
            "daily_max_notional_usd": ROBINHOOD_DAILY_REAL_FUNDS_TEST_MAX_USD,
            "requested_exceeds_first_order_cap": notional_usd
            > ROBINHOOD_FIRST_REAL_FUNDS_TEST_MAX_USD,
        },
        "pre_submit_gates": [
            "TRADINGVIEW_EXECUTION_ENABLED=false until intentionally flipped",
            "manual Ari confirmation in the active terminal",
            "account.is_api_tradable=true",
            "buying_power >= order_notional_plus_fee",
            "trading_pair.status=tradable",
            "estimated_price spread within configured threshold",
            "client_order_id generated once and logged before submit",
            "kill switch clear immediately before submit",
        ],
        "execution_blocked_by_default": True,
    }

    if side == "hold":
        payload["blocked_reason"] = "hold action has no Robinhood order body"
        return payload

    estimated_side = "ask" if side == "buy" else "bid"
    limit_config: dict[str, Any] = {
        "limit_price": "<guarded_limit_price_from_estimated_price>",
        "time_in_force": "gtc",
    }
    if side == "buy":
        limit_config["quote_amount"] = "<usd_quote_amount_after_live_test_cap>"
    else:
        limit_config["asset_quantity"] = "<asset_quantity_to_sell_after_position_check>"

    payload.update(
        {
            "order_type": "limit",
            "estimated_price_preflight": {
                "method": "GET",
                "endpoint": ROBINHOOD_CRYPTO_V2_ESTIMATED_PRICE_ENDPOINT,
                "query_params": {
                    "symbol": symbol,
                    "side": estimated_side,
                    "quantity": "<asset_quantity_or_test_quantity>",
                },
            },
            "body_template": {
                "client_order_id": "<uuid_v4_at_submit_time>",
                "side": side,
                "type": "limit",
                "symbol": symbol,
                "limit_order_config": limit_config,
            },
        }
    )
    return payload


def build_robinhood_real_funds_readiness(*, configured: bool = False) -> dict[str, Any]:
    """Readiness plan for the funded Robinhood Crypto test budget."""
    return {
        "stage": "manual_confirmed_crypto_only",
        "configured": configured,
        "cash_budget_usd": 50.0,
        "crypto": {
            "official_api_available": True,
            "base_url": ROBINHOOD_CRYPTO_BASE_URL,
            "preferred_version": "v2",
            "order_endpoint": ROBINHOOD_CRYPTO_V2_ORDER_ENDPOINT,
            "quote_endpoint": "/api/v2/crypto/marketdata/best_bid_ask/",
            "estimated_price_endpoint": ROBINHOOD_CRYPTO_V2_ESTIMATED_PRICE_ENDPOINT,
            "docs": VENUE_DOCS["robinhood_crypto_api"],
            "first_order_max_notional_usd": ROBINHOOD_FIRST_REAL_FUNDS_TEST_MAX_USD,
            "daily_max_notional_usd": ROBINHOOD_DAILY_REAL_FUNDS_TEST_MAX_USD,
        },
        "stocks": {
            "official_public_trading_api_identified": False,
            "mode": "manual_or_future_approved_broker_only",
            "reason": "Robinhood's public trading API documentation is for Robinhood Crypto; equity order types are documented for app, web classic, and Legend flows, not a public stock-trading API.",
        },
        "submit_blockers": [
            "no autonomous submit/cancel/replace path exists for Robinhood orders",
            "no real order without explicit operator order details and confirmation token",
            "no stock or ETF automation through unofficial Robinhood endpoints",
            "no background scheduler can bypass the confirmation wall",
        ],
        "promotion_gates": [
            "local unit and integration tests pass",
            "read-only account and quote calls succeed with redacted logging",
            "order draft matches v2 schema and stays unsigned",
            "paper order has expected fill/fee/slippage accounting",
            "Ari manually approves each capped live crypto limit order",
        ],
    }


def build_order_drafts(
    symbol: Any,
    action: Any,
    *,
    notional_usd: float = 100.0,
    strategy: str = "strategy_lab",
) -> list[dict[str, Any]]:
    """Build non-submitting venue payload drafts for strategy testing."""
    spec = asset_spec(symbol)
    action_norm = normalize_action(action)
    notional = max(0.0, float(notional_usd or 0.0))
    is_buy = action_norm == "buy"
    reduce_only = action_norm == "close"
    notes = ("draft_only", "no_signature", "no_network_submit")

    drafts = [
        OrderDraft(
            venue="paper",
            mode="paper",
            symbol=spec.symbol,
            action=action_norm,
            notional_usd=notional,
            execution_enabled=False,
            payload={
                "source": strategy,
                "symbol": spec.tradingview_symbol,
                "action": action_norm,
                "notional_usd": notional,
                "mode": "paper",
            },
            notes=("routes_to_paper_trading_only",),
        ),
        OrderDraft(
            venue="tradingview_webhook",
            mode="alert_template",
            symbol=spec.symbol,
            action=action_norm,
            notional_usd=notional,
            execution_enabled=False,
            payload={
                "symbol": "{{ticker}}",
                "exchange": "{{exchange}}",
                "action": "{{strategy.order.action}}",
                "price": "{{strategy.order.price}}",
                "contracts": "{{strategy.order.contracts}}",
                "time": "{{time}}",
                "interval": "{{interval}}",
                "strategy": strategy,
                "mode": "paper",
            },
            notes=("template_only", "paste_safe_no_secret"),
        ),
    ]

    if spec.robinhood_symbol:
        drafts.append(
            OrderDraft(
                venue="robinhood_crypto",
                mode="order_intent_draft",
                symbol=spec.symbol,
                action=action_norm,
                notional_usd=notional,
                execution_enabled=False,
                payload=_robinhood_crypto_order_payload(
                    symbol=spec.robinhood_symbol,
                    action_norm=action_norm,
                    notional_usd=notional,
                ),
                notes=(
                    *notes,
                    "v2_fee_tier_endpoint",
                    "requires_manual_confirmation",
                ),
            )
        )

    if spec.hyperliquid_symbol:
        drafts.append(
            OrderDraft(
                venue="hyperliquid",
                mode="exchange_action_draft",
                symbol=spec.symbol,
                action=action_norm,
                notional_usd=notional,
                execution_enabled=False,
                payload={
                    "type": "order",
                    "coin": spec.hyperliquid_symbol,
                    "is_buy": is_buy,
                    "notional_usd": notional,
                    "reduce_only": reduce_only,
                    "time_in_force": "Ioc",
                    "requires_wallet_signature": True,
                },
                notes=notes,
            )
        )

    drafts.append(
        OrderDraft(
            venue="robinhood_chain_testnet",
            mode="signal_attestation_draft",
            symbol=spec.symbol,
            action=action_norm,
            notional_usd=notional,
            execution_enabled=False,
            payload={
                "chain_id": ROBINHOOD_CHAIN_TESTNET["chain_id"],
                "symbol": spec.symbol,
                "strategy": strategy,
                "proof_hash": "0x" + "0" * 64,
                "testnet_only": True,
            },
            notes=("testnet_attestation_only", "no_mainnet_value_transfer"),
        )
    )
    return [asdict(draft) for draft in drafts]


def _secret_group_present(
    *, env_vars: tuple[str, ...] = (), file_names: tuple[str, ...] = ()
) -> bool:
    if env_vars and all(os.getenv(env_var) for env_var in env_vars):
        return True
    if not file_names:
        return False
    base = Path.home() / ".config" / "sapphire-secrets"
    for name in file_names:
        try:
            path = base / name
            if not path.exists() or path.stat().st_size <= 0:
                return False
        except OSError:
            return False
    return True


def _secret_present(*, env_var: str, file_names: tuple[str, ...]) -> bool:
    if os.getenv(env_var):
        return True
    base = Path.home() / ".config" / "sapphire-secrets"
    for name in file_names:
        try:
            path = base / name
            if path.exists() and path.stat().st_size > 0:
                return True
        except OSError:
            continue
    return False


def build_strategy_lab_report(*, fetch_live: bool = True) -> dict[str, Any]:
    """Full strategy-lab payload for dashboard/API consumers."""
    started = time.perf_counter()
    market = build_market_universe(fetch_live=fetch_live)
    tradingview = build_tradingview_capability_matrix()
    hyperliquid_configured = _secret_present(
        env_var="HYPERLIQUID_PRIVATE_KEY",
        file_names=("hyperliquid_private_key", "hyperliquid-private-key"),
    )
    robinhood_configured = _secret_group_present(
        env_vars=ROBINHOOD_AUTH_ENV_VARS,
        file_names=ROBINHOOD_AUTH_FILE_NAMES,
    )
    return {
        "generated_at": _now_iso(),
        "safety": {
            "live_trading_enabled": False,
            "execution_stage": "paper",
            "kill_switch_required": True,
            "guards": [
                "TRADINGVIEW_EXECUTION_ENABLED=false",
                "order_drafts_never_sign_or_submit",
                "telegram_real_sends_disabled_for_tests",
            ],
        },
        "market_universe": market,
        "tradingview": tradingview,
        "real_funds_readiness": build_robinhood_real_funds_readiness(
            configured=robinhood_configured
        ),
        "venues": [
            {
                "id": "paper",
                "label": "Paper trading",
                "mode": "paper",
                "configured": True,
                "mutates_external_state": False,
            },
            {
                "id": "robinhood_crypto",
                "label": "Robinhood Crypto",
                "mode": "read_only_plus_order_drafts",
                "configured": robinhood_configured,
                "mutates_external_state": False,
                "docs": VENUE_DOCS["robinhood_crypto"],
            },
            {
                "id": "hyperliquid",
                "label": "Hyperliquid",
                "mode": "public_data_plus_order_drafts",
                "configured": hyperliquid_configured,
                "funded_expected": True,
                "mutates_external_state": False,
                "docs": VENUE_DOCS["hyperliquid_exchange"],
            },
            {
                "id": "robinhood_chain_testnet",
                "label": "Robinhood Chain Testnet",
                "mode": "testnet_signal_attestation",
                "configured": True,
                "mutates_external_state": False,
                "chain_id": ROBINHOOD_CHAIN_TESTNET["chain_id"],
                "docs": VENUE_DOCS["robinhood_chain"],
            },
        ],
        "strategy_tests": [
            {
                "id": "backtest_liked_universe",
                "surface": "/api/risk/backtest",
                "mode": "paper",
                "symbols": [
                    row["yfinance_symbol"]
                    for row in market["liked_tokens"]
                    if row.get("yfinance_symbol")
                ],
            },
            {
                "id": "tradingview_payload_fixture",
                "surface": "/webhook/tradingview",
                "mode": "dry_run",
                "template": tradingview["alert_template"],
            },
            {
                "id": "venue_order_draft",
                "surface": "/api/trading/order-draft",
                "mode": "draft_only",
                "sample": build_order_drafts("BTC", "buy", notional_usd=100.0)[0],
            },
        ],
        "source_docs": [
            *TRADINGVIEW_DOCS,
            VENUE_DOCS["robinhood_crypto"],
            VENUE_DOCS["robinhood_crypto_api"],
            VENUE_DOCS["robinhood_chain"],
            VENUE_DOCS["hyperliquid_info"],
            VENUE_DOCS["hyperliquid_exchange"],
            VENUE_DOCS["coingecko_trending"],
        ],
        "cache_ttl_seconds": 300,
        "runtime_ms": round((time.perf_counter() - started) * 1000, 1),
    }
