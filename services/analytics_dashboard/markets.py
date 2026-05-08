"""Live global market data for the unified dashboard.

Pulls CoinGecko (free tier, no auth) for the top crypto by market cap.
Caches the response in-process for 60s so we respect CoinGecko's
unauthenticated rate limit (~30 req/min). Cloud Run instances are
ephemeral so a per-instance cache is sufficient.

Endpoint:
  GET /api/markets/crypto      — top 10 crypto by market cap
  GET /api/markets/global      — global crypto market summary
  GET /api/markets/snapshot    — combined feed: top crypto + global stats
                                 (the dashboard hits this one)

Fail-safe: every endpoint wraps the upstream call in try/except and
returns an empty payload + ``stale: true`` flag on failure. The
dashboard's empty-state renderer handles this cleanly.

Wired into the parent Flask app via :func:`register_markets`.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request

from flask import jsonify, request

log = logging.getLogger("sapphire.markets")

CG_BASE = os.environ.get("COINGECKO_BASE", "https://api.coingecko.com/api/v3")
CACHE_TTL_SEC = int(os.environ.get("MARKETS_CACHE_TTL", "60"))

_cache: dict[str, tuple[float, dict]] = {}


def _http_get_json(url: str, timeout: float = 5.0) -> dict | list | None:
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "sapphire-markets/1.0", "Accept": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                log.info("markets: %s returned %s", url, resp.status)
                return None
            return json.loads(resp.read().decode("utf-8"))
    except (
        urllib.error.URLError,
        urllib.error.HTTPError,
        TimeoutError,
        ValueError,
        OSError,
    ) as exc:
        log.info("markets fetch failed: %s -> %s", url, exc)
        return None


def _cached(key: str, ttl: int = CACHE_TTL_SEC):
    """Decorator factory: return cached value if fresh, else call f and cache."""

    def deco(f):
        def wrapper(*a, **kw):
            now = time.time()
            entry = _cache.get(key)
            if entry and now - entry[0] < ttl:
                return entry[1]
            val = f(*a, **kw)
            if val is not None:
                _cache[key] = (now, val)
            return val

        return wrapper

    return deco


@_cached("crypto-top", ttl=CACHE_TTL_SEC)
def _fetch_top_crypto(limit: int = 10) -> list[dict] | None:
    url = (
        f"{CG_BASE}/coins/markets?vs_currency=usd&order=market_cap_desc"
        f"&per_page={limit}&page=1&sparkline=true&price_change_percentage=1h%2C24h%2C7d"
    )
    data = _http_get_json(url, timeout=6.0)
    if not isinstance(data, list):
        return None
    out = []
    for c in data:
        out.append(
            {
                "id": c.get("id"),
                "symbol": (c.get("symbol") or "").upper(),
                "name": c.get("name"),
                "image": c.get("image"),
                "price_usd": c.get("current_price"),
                "market_cap_usd": c.get("market_cap"),
                "volume_24h_usd": c.get("total_volume"),
                "change_1h_pct": (c.get("price_change_percentage_1h_in_currency") or 0),
                "change_24h_pct": (
                    c.get("price_change_percentage_24h")
                    or c.get("price_change_percentage_24h_in_currency")
                    or 0
                ),
                "change_7d_pct": (c.get("price_change_percentage_7d_in_currency") or 0),
                "ath_usd": c.get("ath"),
                "ath_change_pct": c.get("ath_change_percentage"),
                "circulating_supply": c.get("circulating_supply"),
                "rank": c.get("market_cap_rank"),
                "sparkline_7d": (c.get("sparkline_in_7d") or {}).get("price") or [],
            }
        )
    return out


@_cached("crypto-global", ttl=CACHE_TTL_SEC)
def _fetch_global() -> dict | None:
    data = _http_get_json(f"{CG_BASE}/global", timeout=5.0)
    if not isinstance(data, dict):
        return None
    g = data.get("data", {})
    return {
        "total_market_cap_usd": (g.get("total_market_cap") or {}).get("usd"),
        "total_volume_24h_usd": (g.get("total_volume") or {}).get("usd"),
        "btc_dominance_pct": (g.get("market_cap_percentage") or {}).get("btc"),
        "eth_dominance_pct": (g.get("market_cap_percentage") or {}).get("eth"),
        "active_cryptocurrencies": g.get("active_cryptocurrencies"),
        "markets": g.get("markets"),
        "market_cap_change_24h_pct": g.get("market_cap_change_percentage_24h_usd"),
        "updated_at": g.get("updated_at"),
    }


@_cached("trending", ttl=CACHE_TTL_SEC)
def _fetch_trending() -> list[dict] | None:
    data = _http_get_json(f"{CG_BASE}/search/trending", timeout=5.0)
    if not isinstance(data, dict):
        return None
    items = []
    for c in (data.get("coins") or [])[:7]:
        item = c.get("item", {})
        items.append(
            {
                "id": item.get("id"),
                "symbol": (item.get("symbol") or "").upper(),
                "name": item.get("name"),
                "rank": item.get("market_cap_rank"),
                "score": item.get("score"),
                "thumb": item.get("thumb"),
            }
        )
    return items


def register_markets(app) -> None:
    """Attach /api/markets/* endpoints to ``app``."""

    @app.get("/api/markets/crypto")
    def _crypto_top():
        limit = max(1, min(int(request.args.get("limit", "10")), 50))
        rows = _fetch_top_crypto(limit=limit) or []
        return jsonify({"rows": rows, "count": len(rows), "stale": not rows})

    @app.get("/api/markets/global")
    def _crypto_global():
        g = _fetch_global() or {}
        return jsonify({"global": g, "stale": not g})

    @app.get("/api/markets/trending")
    def _crypto_trending():
        rows = _fetch_trending() or []
        return jsonify({"rows": rows, "stale": not rows})

    @app.get("/api/markets/snapshot")
    def _snapshot():
        """Single round-trip the dashboard hits — returns top 10 + global
        + trending. Each piece fail-safes independently so the page never
        breaks if one upstream is rate-limited."""
        return jsonify(
            {
                "crypto": _fetch_top_crypto(limit=10) or [],
                "global": _fetch_global() or {},
                "trending": _fetch_trending() or [],
                "ts": time.time(),
            }
        )
