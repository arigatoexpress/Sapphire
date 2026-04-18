"""On-chain data source adapters: DeFiLlama, Hyperliquid, CoinGecko.

All adapters:
- use stdlib urllib only (no aiohttp/requests dependency)
- cache responses for 5 minutes in-process
- return typed dataclasses or plain dicts for flexibility
- raise `SourceError` on failures (caller decides how to handle)

The clients are intentionally synchronous — the aggregator layer handles
concurrency via threading when it needs parallel fetches. Keeping this layer
plain-sync makes debugging and testing trivial.
"""

from __future__ import annotations

import json
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any

try:
    import certifi
    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CTX = ssl.create_default_context()

DEFAULT_TIMEOUT = 12
CACHE_TTL = 300  # 5 minutes
USER_AGENT = "sapphire-os/0.4 (+on-chain-intel)"


class SourceError(RuntimeError):
    """Raised when an on-chain data source fails or returns malformed data."""


# ---------------------------------------------------------------------------
# Shared HTTP helpers + cache
# ---------------------------------------------------------------------------

_cache: dict[str, tuple[float, Any]] = {}
_cache_lock = threading.Lock()


def _cache_get(key: str) -> Any | None:
    with _cache_lock:
        entry = _cache.get(key)
        if entry and (time.monotonic() - entry[0]) < CACHE_TTL:
            return entry[1]
    return None


def _cache_set(key: str, value: Any) -> None:
    with _cache_lock:
        _cache[key] = (time.monotonic(), value)


def _http_get(url: str, timeout: int = DEFAULT_TIMEOUT) -> Any:
    cached = _cache_get(url)
    if cached is not None:
        return cached
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as r:
            body = r.read()
    except urllib.error.HTTPError as e:
        raise SourceError(f"GET {url} → HTTP {e.code}: {e.reason}") from e
    except Exception as e:
        raise SourceError(f"GET {url} → {type(e).__name__}: {e}") from e
    try:
        data = json.loads(body)
    except json.JSONDecodeError as e:
        raise SourceError(f"GET {url} → invalid JSON: {e}") from e
    _cache_set(url, data)
    return data


def _http_post_json(url: str, payload: dict, timeout: int = DEFAULT_TIMEOUT) -> Any:
    cache_key = f"POST {url} {json.dumps(payload, sort_keys=True)}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as r:
            body = r.read()
    except urllib.error.HTTPError as e:
        raise SourceError(f"POST {url} → HTTP {e.code}: {e.reason}") from e
    except Exception as e:
        raise SourceError(f"POST {url} → {type(e).__name__}: {e}") from e
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as e:
        raise SourceError(f"POST {url} → invalid JSON: {e}") from e
    _cache_set(cache_key, parsed)
    return parsed


# ---------------------------------------------------------------------------
# DeFiLlama
# ---------------------------------------------------------------------------


@dataclass
class LlamaChain:
    name: str
    tvl: float
    token_symbol: str | None = None
    gecko_id: str | None = None


@dataclass
class LlamaProtocol:
    name: str
    tvl: float
    category: str | None = None
    chains: list[str] = field(default_factory=list)
    change_1d: float | None = None
    change_7d: float | None = None


@dataclass
class StablecoinTotals:
    total_usd: float
    tether_usd: float
    usdc_usd: float
    count: int


class DefiLlamaClient:
    """DeFiLlama adapter — TVL, DEX volumes, stablecoin supply."""

    BASE = "https://api.llama.fi"
    COINS_BASE = "https://coins.llama.fi"
    STABLE_BASE = "https://stablecoins.llama.fi"

    def protocols(self) -> list[LlamaProtocol]:
        data = _http_get(f"{self.BASE}/protocols")
        if not isinstance(data, list):
            raise SourceError("DeFiLlama /protocols returned non-list")
        out: list[LlamaProtocol] = []
        for p in data:
            out.append(
                LlamaProtocol(
                    name=p.get("name", ""),
                    tvl=float(p.get("tvl") or 0.0),
                    category=p.get("category"),
                    chains=list(p.get("chains") or []),
                    change_1d=p.get("change_1d"),
                    change_7d=p.get("change_7d"),
                )
            )
        return out

    def chains(self) -> list[LlamaChain]:
        data = _http_get(f"{self.BASE}/v2/chains")
        if not isinstance(data, list):
            raise SourceError("DeFiLlama /v2/chains returned non-list")
        return [
            LlamaChain(
                name=c.get("name", ""),
                tvl=float(c.get("tvl") or 0.0),
                token_symbol=c.get("tokenSymbol"),
                gecko_id=c.get("gecko_id"),
            )
            for c in data
        ]

    def prices(self, coins: list[str]) -> dict[str, dict]:
        """Fetch current USD prices. `coins` uses llama format, e.g. `coingecko:bitcoin`."""
        if not coins:
            return {}
        path = urllib.parse.quote(",".join(coins), safe=":,")
        data = _http_get(f"{self.COINS_BASE}/prices/current/{path}")
        return data.get("coins", {}) if isinstance(data, dict) else {}

    def dex_overview(self) -> dict:
        """Aggregate DEX volume (24h total, top chains)."""
        return _http_get(f"{self.BASE}/overview/dexs")

    def stablecoins(self) -> StablecoinTotals:
        """Stablecoin supply totals — USD-pegged only."""
        data = _http_get(f"{self.STABLE_BASE}/stablecoins?includePrices=false")
        if not isinstance(data, dict):
            raise SourceError("DeFiLlama /stablecoins returned non-dict")
        assets = data.get("peggedAssets") or []
        total = 0.0
        tether = 0.0
        usdc = 0.0
        count = 0
        for a in assets:
            if a.get("pegType") != "peggedUSD":
                continue
            circ = (a.get("circulating") or {}).get("peggedUSD")
            if circ is None:
                continue
            circ = float(circ)
            total += circ
            count += 1
            sym = (a.get("symbol") or "").upper()
            if sym == "USDT":
                tether = circ
            elif sym == "USDC":
                usdc = circ
        return StablecoinTotals(
            total_usd=total,
            tether_usd=tether,
            usdc_usd=usdc,
            count=count,
        )

    def chart_tvl(self) -> list[tuple[int, float]]:
        """Historical total TVL across all chains. Returns [(unix_ts, tvl_usd), ...]."""
        data = _http_get(f"{self.BASE}/v2/historicalChainTvl")
        if not isinstance(data, list):
            raise SourceError("DeFiLlama /v2/historicalChainTvl returned non-list")
        return [(int(p.get("date", 0)), float(p.get("tvl") or 0.0)) for p in data]


# ---------------------------------------------------------------------------
# Hyperliquid
# ---------------------------------------------------------------------------


@dataclass
class HLAssetCtx:
    coin: str
    mark_px: float
    oracle_px: float
    funding_rate: float  # per 8h (negative = shorts pay longs)
    open_interest: float  # in coin units
    day_volume: float  # in USDC (24h notional)
    prev_day_px: float | None = None


class HyperliquidClient:
    """Hyperliquid perps adapter — mark prices, funding rates, open interest."""

    BASE = "https://api.hyperliquid.xyz/info"

    def meta_and_asset_ctxs(self) -> list[HLAssetCtx]:
        """All perp markets with their current asset contexts."""
        resp = _http_post_json(self.BASE, {"type": "metaAndAssetCtxs"})
        if not isinstance(resp, list) or len(resp) != 2:
            raise SourceError(f"Hyperliquid metaAndAssetCtxs shape unexpected: {type(resp).__name__}")
        meta, ctxs = resp
        universe = meta.get("universe") or []
        if not isinstance(universe, list) or not isinstance(ctxs, list):
            raise SourceError("Hyperliquid metaAndAssetCtxs inner shape unexpected")
        out: list[HLAssetCtx] = []
        for asset_meta, ctx in zip(universe, ctxs, strict=False):
            coin = asset_meta.get("name") or ""
            try:
                mark = float(ctx.get("markPx") or 0.0)
                oracle = float(ctx.get("oraclePx") or 0.0)
                funding = float(ctx.get("funding") or 0.0)
                oi = float(ctx.get("openInterest") or 0.0)
                vol = float(ctx.get("dayNtlVlm") or 0.0)
                prev = ctx.get("prevDayPx")
                prev_float = float(prev) if prev is not None else None
            except (TypeError, ValueError):
                continue
            out.append(
                HLAssetCtx(
                    coin=coin,
                    mark_px=mark,
                    oracle_px=oracle,
                    funding_rate=funding,
                    open_interest=oi,
                    day_volume=vol,
                    prev_day_px=prev_float,
                )
            )
        return out

    def funding_history(self, coin: str, start_ms: int, end_ms: int | None = None) -> list[dict]:
        """Historical funding rate for a coin. Returns list of {coin, fundingRate, premium, time}."""
        payload: dict = {"type": "fundingHistory", "coin": coin, "startTime": start_ms}
        if end_ms is not None:
            payload["endTime"] = end_ms
        resp = _http_post_json(self.BASE, payload)
        if not isinstance(resp, list):
            raise SourceError(f"Hyperliquid fundingHistory for {coin} returned non-list")
        return resp

    def clearinghouse_state(self, address: str) -> dict:
        """Positions + margin summary for a specific user/whale address."""
        resp = _http_post_json(self.BASE, {"type": "clearinghouseState", "user": address})
        if not isinstance(resp, dict):
            raise SourceError(f"Hyperliquid clearinghouseState for {address} returned non-dict")
        return resp


# ---------------------------------------------------------------------------
# CoinGecko
# ---------------------------------------------------------------------------


@dataclass
class GlobalMarket:
    total_market_cap_usd: float
    total_volume_24h_usd: float
    btc_dominance: float
    eth_dominance: float
    active_cryptocurrencies: int
    markets: int
    market_cap_change_pct_24h: float


class CoinGeckoClient:
    """CoinGecko public API adapter — market globals + historical prices."""

    BASE = "https://api.coingecko.com/api/v3"

    def global_market(self) -> GlobalMarket:
        resp = _http_get(f"{self.BASE}/global")
        if not isinstance(resp, dict) or "data" not in resp:
            raise SourceError("CoinGecko /global returned no data")
        d = resp["data"]
        mcap = d.get("market_cap_percentage") or {}
        return GlobalMarket(
            total_market_cap_usd=float((d.get("total_market_cap") or {}).get("usd") or 0.0),
            total_volume_24h_usd=float((d.get("total_volume") or {}).get("usd") or 0.0),
            btc_dominance=float(mcap.get("btc") or 0.0),
            eth_dominance=float(mcap.get("eth") or 0.0),
            active_cryptocurrencies=int(d.get("active_cryptocurrencies") or 0),
            markets=int(d.get("markets") or 0),
            market_cap_change_pct_24h=float(d.get("market_cap_change_percentage_24h_usd") or 0.0),
        )

    def coin_market_chart(self, coin_id: str, days: int = 30, vs_currency: str = "usd") -> dict:
        """Historical prices for a coin. Returns {prices: [[ts_ms, price], ...], ...}."""
        url = f"{self.BASE}/coins/{coin_id}/market_chart?vs_currency={vs_currency}&days={days}"
        return _http_get(url)


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    print("=== DeFiLlama ===")
    ll = DefiLlamaClient()
    chains = ll.chains()
    print(f"chains: {len(chains)}  (top 3 by TVL: {[c.name for c in sorted(chains, key=lambda x: -x.tvl)[:3]]})")
    prices = ll.prices(["coingecko:bitcoin", "coingecko:ethereum"])
    print(f"prices: BTC=${prices.get('coingecko:bitcoin',{}).get('price',0):,.0f} ETH=${prices.get('coingecko:ethereum',{}).get('price',0):,.0f}")
    sc = ll.stablecoins()
    print(f"stablecoins: total=${sc.total_usd:,.0f} USDT=${sc.tether_usd:,.0f} USDC=${sc.usdc_usd:,.0f}")

    print("\n=== Hyperliquid ===")
    hl = HyperliquidClient()
    ctxs = hl.meta_and_asset_ctxs()
    print(f"assets: {len(ctxs)}")
    majors = [c for c in ctxs if c.coin in ("BTC", "ETH", "SOL")]
    for c in majors:
        print(f"  {c.coin}: mark=${c.mark_px:,.2f} funding={c.funding_rate*100:+.4f}%/8h OI={c.open_interest:,.0f}")

    print("\n=== CoinGecko ===")
    cg = CoinGeckoClient()
    gm = cg.global_market()
    print(f"total mcap: ${gm.total_market_cap_usd:,.0f}  BTC.D: {gm.btc_dominance:.2f}%  ETH.D: {gm.eth_dominance:.2f}%")
    print(f"24h change: {gm.market_cap_change_pct_24h:+.2f}%")
