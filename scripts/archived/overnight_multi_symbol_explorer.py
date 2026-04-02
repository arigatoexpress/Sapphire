#!/usr/bin/env python3
"""
Overnight multi-symbol signal explorer for Lighter.

Purpose:
- Keep the trading lane fed with diversified, metadata-rich signals overnight.
- Use a simple but deterministic momentum model (EMA crossover + slope) so
  experiments are reproducible and analyzable.
- Publish to the canonical TradingView-compatible gateway webhook.
"""

from __future__ import annotations

import json
import os
import signal
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Tuple


def _env(name: str, default: str = "") -> str:
    return str(os.getenv(name, default)).strip()


GATEWAY_WEBHOOK_URL = _env(
    "GATEWAY_WEBHOOK_URL",
    "https://sapphire-gateway-s77j6bxyra-uc.a.run.app/webhook/tradingview",
)
WEBHOOK_SECRET = _env("WEBHOOK_SECRET", "")
SPARK_MODE = _env("SPARK_MODE", "").strip().lower() == "true"
SPARK_LANE_CONFIG = _env("SPARK_LANE_CONFIG", "")
PRICE_PROVIDERS = _env(
    "PRICE_PROVIDERS",
    "coingecko,coinbase,kraken,binance,coincap,cryptocompare",
)
SYMBOLS = [s.strip().upper() for s in _env("SYMBOLS", "BTCUSDT,ETHUSDT,SOLUSDT").split(",") if s.strip()]
LOCKED_SYMBOL = _env("LOCKED_SYMBOL", "").upper()
if LOCKED_SYMBOL and LOCKED_SYMBOL not in SYMBOLS:
    SYMBOLS = [LOCKED_SYMBOL, *SYMBOLS]
TIMEFRAME = _env("TIMEFRAME", "5m").lower()
SCAN_SECONDS = max(10, int(float(_env("SCAN_SECONDS", "75"))))
SYMBOL_COOLDOWN_SECONDS = max(60, int(float(_env("SYMBOL_COOLDOWN_SECONDS", "300"))))
HISTORY_LIMIT = max(60, min(500, int(float(_env("HISTORY_LIMIT", "180")))))
EMA_FAST = max(3, int(float(_env("EMA_FAST", "9"))))
EMA_SLOW = max(5, int(float(_env("EMA_SLOW", "21"))))
EDGE_THRESHOLD_PCT = max(0.01, float(_env("EDGE_THRESHOLD_PCT", "0.10")))
MOMENTUM_EDGE_THRESHOLD_PCT = max(
    0.005, float(_env("MOMENTUM_EDGE_THRESHOLD_PCT", str(max(0.01, EDGE_THRESHOLD_PCT * 0.5))))
)
MIN_CONFIDENCE = max(0.50, min(0.95, float(_env("MIN_CONFIDENCE", "0.67"))))
SOURCE = _env("SOURCE", "overnight-explorer")
STRATEGY = _env("STRATEGY", "ev_guarded_momentum_v2")
STRATEGY_FALLBACK = STRATEGY
TIMEFRAME_FALLBACK = TIMEFRAME
MIN_ABS_EDGE_PCT = max(0.001, float(_env("MIN_ABS_EDGE_PCT", "0.05")))
EST_FEE_BPS = max(0.0, float(_env("EST_FEE_BPS", "4.5")))
EST_SLIPPAGE_BPS = max(0.0, float(_env("EST_SLIPPAGE_BPS", "2.5")))
MIN_NET_EDGE_PCT = max(0.0, float(_env("MIN_NET_EDGE_PCT", "0.02")))
LIVE_EXEC_SYMBOLS_RAW = _env("LIVE_EXEC_SYMBOLS", "")
LIVE_EXEC_TIMEFRAMES_RAW = _env("LIVE_EXEC_TIMEFRAMES", "")
LIVE_EXEC_STRATEGIES_RAW = _env("LIVE_EXEC_STRATEGIES", "")
STRICT_LIVE_MODE = _env("STRICT_LIVE_MODE", "true").lower() in {"1", "true", "yes", "on"}
PUBLISH_RESEARCH_SIGNALS = _env("PUBLISH_RESEARCH_SIGNALS", "false").lower() in {"1", "true", "yes", "on"}
HTTP_TIMEOUT = max(5, int(float(_env("HTTP_TIMEOUT", "12"))))
PROVIDER_TIMEOUT = max(5, int(float(_env("PROVIDER_TIMEOUT", str(HTTP_TIMEOUT)))))
PROVIDER_MAX_RETRIES = max(0, int(float(_env("PROVIDER_MAX_RETRIES", "2"))))
PROVIDER_CYCLE_SUMMARY_EVERY = max(1, int(float(_env("PROVIDER_CYCLE_SUMMARY_EVERY", "1"))))
HTTP_HEADERS = {
    "User-Agent": "Sapphire/1.0 (+https://sapphirealpha.xyz)",
    "Accept": "application/json",
}

COINGECKO_SYMBOL_MAP = {
    "BTCUSDT": "bitcoin",
    "ETHUSDT": "ethereum",
    "SOLUSDT": "solana",
    "BNBUSDT": "binancecoin",
    "XRPUSDT": "ripple",
    "DOGEUSDT": "dogecoin",
    "AVAXUSDT": "avalanche-2",
    "LINKUSDT": "chainlink",
}
COINGECKO_USE_PRO = _env("COINGECKO_USE_PRO", "").strip().lower() in {"1", "true", "yes", "on"}
COINGECKO_API_KEY = _env("COINGECKO_API_KEY", "")
COINGECKO_API = (
    "https://pro-api.coingecko.com/api/v3/simple/price"
    if COINGECKO_USE_PRO
    else "https://api.coingecko.com/api/v3/simple/price"
)
COINBASE_API = "https://api.coinbase.com/v2/prices/{pair}/spot"
KRAKEN_API = "https://api.kraken.com/0/public/Ticker?pair={pairs}"
KRAKEN_PAIR_MAP = {
    "BTCUSDT": "XBTUSD",
    "ETHUSDT": "ETHUSD",
    "SOLUSDT": "SOLUSD",
    "BNBUSDT": "BNBUSD",
    "XRPUSDT": "XRPUSD",
    "DOGEUSDT": "DOGEUSD",
    "AVAXUSDT": "AVAXUSD",
    "LINKUSDT": "LINKUSD",
}
COINCAP_ASSET_MAP = {
    "BTCUSDT": "bitcoin",
    "ETHUSDT": "ethereum",
    "SOLUSDT": "solana",
    "BNBUSDT": "binance-coin",
    "XRPUSDT": "xrp",
    "DOGEUSDT": "dogecoin",
    "AVAXUSDT": "avalanche",
    "LINKUSDT": "chainlink",
}
CRYPTOCOMPARE_API = "https://min-api.cryptocompare.com/data/pricemulti?fsyms={symbols}&tsyms=USD"

RUNNING = True
LAST_SENT: Dict[str, Tuple[str, float]] = {}
PRICE_HISTORY: Dict[str, Deque[float]] = {}
LANE_CONFIG: Dict[str, Dict[str, str]] = {}
FETCH_ERROR_STREAK: int = 0
CYCLE_COUNT = 0
LAST_PROVIDER_STATUS: Dict[str, int] = {}
LAST_GATEWAY_STATUS: Dict[str, int] = {}
SHUTDOWN_POLL_SECONDS = 0.25


def _coerce_str(value: Any, default: str = "") -> str:
    try:
        if value is None:
            return default
        return str(value).strip()
    except Exception:
        return default


def _normalize_provider_config(raw: str) -> List[str]:
    providers = []
    for value in (raw or "").split(","):
        provider = value.strip().lower()
        if not provider:
            continue
        if provider not in providers:
            providers.append(provider)
    if not providers:
        return ["coingecko"]
    return providers


def _csv_set(raw: str, *, upper: bool = False) -> set[str]:
    out: set[str] = set()
    for item in (raw or "").split(","):
        text = _coerce_str(item)
        if not text:
            continue
        if upper:
            text = text.upper().replace("/", "")
        else:
            text = text.lower()
        if text:
            out.add(text)
    return out


_PROVIDERS = _normalize_provider_config(PRICE_PROVIDERS)
LIVE_EXEC_SYMBOLS = _csv_set(LIVE_EXEC_SYMBOLS_RAW, upper=True)
LIVE_EXEC_TIMEFRAMES = _csv_set(LIVE_EXEC_TIMEFRAMES_RAW, upper=False)
LIVE_EXEC_STRATEGIES = _csv_set(LIVE_EXEC_STRATEGIES_RAW, upper=False)

if STRICT_LIVE_MODE and LIVE_EXEC_SYMBOLS:
    strict_symbols: List[str] = []
    strict_seen: set[str] = set()
    for symbol in SYMBOLS:
        symbol_norm = _coerce_str(symbol).upper().replace("/", "")
        if symbol_norm and symbol_norm in LIVE_EXEC_SYMBOLS and symbol_norm not in strict_seen:
            strict_symbols.append(symbol_norm)
            strict_seen.add(symbol_norm)
    if not strict_symbols:
        strict_symbols = sorted(LIVE_EXEC_SYMBOLS)
    if strict_symbols != SYMBOLS:
        print(
            f"[{datetime.now(timezone.utc).isoformat()}] strict live mode active | symbols={','.join(strict_symbols)}",
            flush=True,
        )
    SYMBOLS = strict_symbols

PRICE_HISTORY = {s: deque(maxlen=HISTORY_LIMIT) for s in SYMBOLS}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _log(msg: str) -> None:
    print(f"[{_now_iso()}] {msg}", flush=True)


def _normalize_symbol(value: str) -> str:
    text = _coerce_str(value)
    if not text:
        return ""
    return text.upper().replace("/", "")


def _load_lane_config(raw: str) -> Dict[str, Dict[str, str]]:
    text = _coerce_str(raw)
    if not text:
        return {}

    candidate = Path(text)
    if candidate.exists() and candidate.is_file():
        try:
            text = candidate.read_text(encoding="utf-8").strip()
        except Exception as exc:
            _log(f"failed to read SPARK_LANE_CONFIG file {candidate}: {exc}")
            return {}

    if not text:
        return {}

    try:
        parsed = json.loads(text)
    except Exception as exc:
        _log(f"invalid SPARK_LANE_CONFIG payload: {exc}")
        return {}

    if not isinstance(parsed, dict):
        _log("invalid SPARK_LANE_CONFIG: expected JSON object")
        return {}

    out: Dict[str, Dict[str, str]] = {}
    for raw_symbol, raw_cfg in parsed.items():
        if not isinstance(raw_cfg, dict):
            continue
        symbol = _normalize_symbol(raw_symbol)
        if not symbol:
            continue
        cfg: Dict[str, str] = {}
        for field in ("strategy", "timeframe", "source"):
            val = _coerce_str(raw_cfg.get(field))
            if val:
                cfg[field] = val
        if cfg:
            out[symbol] = cfg
    return out


def _safe_http_json(
    url: str,
    timeout: int,
    provider: str,
    headers: Optional[Dict[str, str]] = None,
) -> Tuple[Any, int]:
    attempts = max(1, PROVIDER_MAX_RETRIES + 1)
    for attempt in range(attempts):
        try:
            req_headers = dict(HTTP_HEADERS)
            if headers:
                req_headers.update({
                    str(k).strip(): str(v).strip() for k, v in headers.items() if str(k).strip()
                })
            req = urllib.request.Request(url=url, method="GET", headers=req_headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                payload = resp.read().decode("utf-8")
                return json.loads(payload), int(resp.status)
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt < attempts - 1:
                _log(f"spot fetch failed: {provider} HTTP 429 attempt={attempt + 1}/{attempts}")
                time.sleep(min(5.0, 0.7 * (2 ** attempt)))
                continue
            raise
        except Exception:
            if attempt < attempts - 1:
                _log(f"spot fetch failed: {provider} attempt={attempt + 1}/{attempts}, retrying")
                time.sleep(min(5.0, 0.7 * (2 ** attempt)))
                continue
            raise


def _fetch_from_coingecko(symbols: List[str]) -> Tuple[Dict[str, float], List[str], bool]:
    ids: List[str] = []
    reverse: Dict[str, str] = {}
    for sym in symbols:
        coin_id = COINGECKO_SYMBOL_MAP.get(sym)
        if not coin_id:
            continue
        ids.append(coin_id)
        reverse[coin_id] = sym
    if not ids:
        return {}, [s for s in symbols if s not in COINGECKO_SYMBOL_MAP], False
    params = urllib.parse.urlencode({"ids": ",".join(ids), "vs_currencies": "usd"})
    url = f"{COINGECKO_API}?{params}"
    extra_headers: Dict[str, str] = {}
    if COINGECKO_API_KEY:
        extra_headers["x-cg-pro-api-key"] = COINGECKO_API_KEY

    data, _ = _safe_http_json(
        url,
        PROVIDER_TIMEOUT,
        "coingecko",
        headers=extra_headers if extra_headers else None,
    )
    out: Dict[str, float] = {}
    for coin_id, payload in data.items():
        sym = reverse.get(coin_id)
        if not sym:
            continue
        try:
            px = float((payload or {}).get("usd", 0.0) or 0.0)
        except Exception:
            px = 0.0
        if px > 0:
            out[sym] = px
    missing: List[str] = []
    for sym in symbols:
        if sym not in out:
            missing.append(sym)
    return out, missing, True


def _fetch_from_binance(symbols: List[str]) -> Tuple[Dict[str, float], List[str], bool]:
    url = "https://api.binance.com/api/v3/ticker/price"
    rows, _ = _safe_http_json(url, PROVIDER_TIMEOUT, "binance")
    if not isinstance(rows, list):
        return {}, [s for s in symbols], False
    requested = {_normalize_symbol(s) for s in symbols}
    out: Dict[str, float] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        symbol = _coerce_str(row.get("symbol")).upper()
        if symbol not in requested:
            continue
        raw_price = row.get("price")
        try:
            price = float(raw_price)
        except Exception:
            continue
        out[symbol] = price
    missing = [sym for sym in requested if sym not in out]
    return out, missing, True


def _fetch_from_coinbase(symbols: List[str]) -> Tuple[Dict[str, float], List[str], bool]:
    requested = [_normalize_symbol(sym) for sym in symbols]
    requested = [sym for sym in requested if sym.endswith("USDT")]
    if not requested:
        return {}, [s for s in symbols], False

    out: Dict[str, float] = {}
    for sym in requested:
        base = sym[:-4]
        pair = f"{base}-USD"
        url = COINBASE_API.format(pair=pair)
        data, _ = _safe_http_json(url, PROVIDER_TIMEOUT, "coinbase")
        row = data.get("data") if isinstance(data, dict) else None
        if not isinstance(row, dict):
            continue
        raw_price = row.get("amount")
        try:
            px = float(raw_price)
        except Exception:
            continue
        if px > 0:
            out[sym] = px
    missing = [sym for sym in requested if sym not in out]
    return out, missing, True


def _fetch_from_kraken(symbols: List[str]) -> Tuple[Dict[str, float], List[str], bool]:
    requested = [_normalize_symbol(sym) for sym in symbols if _normalize_symbol(sym).endswith("USDT")]
    pair_lookup: Dict[str, str] = {}
    for sym in requested:
        pair = KRAKEN_PAIR_MAP.get(sym)
        if not pair:
            continue
        pair_lookup[pair] = sym
    if not pair_lookup:
        return {}, [s for s in requested], False

    pairs_param = ",".join(pair_lookup.keys())
    url = KRAKEN_API.format(pairs=urllib.parse.quote(pairs_param, safe=","))
    data, _ = _safe_http_json(url, PROVIDER_TIMEOUT, "kraken")
    if not isinstance(data, dict) or data.get("error"):
        return {}, requested, True

    out: Dict[str, float] = {}
    result = data.get("result") or {}
    if not isinstance(result, dict):
        return {}, requested, True

    for pair, payload in result.items():
        if not isinstance(payload, dict):
            continue
        sym = pair_lookup.get(pair)
        if not sym:
            continue
        raw_last = None
        closing = payload.get("c")
        if isinstance(closing, list) and closing:
            raw_last = closing[0]
        raw_price = raw_last
        try:
            px = float(raw_price)
        except Exception:
            continue
        if px > 0:
            out[sym] = px

    missing = [sym for sym in requested if sym not in out]
    return out, missing, True


def _fetch_from_coincap(symbols: List[str]) -> Tuple[Dict[str, float], List[str], bool]:
    requested = [_normalize_symbol(sym) for sym in symbols]
    ids: List[str] = []
    reverse: Dict[str, str] = {}
    for sym in requested:
        aid = COINCAP_ASSET_MAP.get(sym)
        if not aid:
            continue
        ids.append(aid)
        reverse[aid] = sym
    if not ids:
        return {}, [s for s in requested], False

    ids_param = urllib.parse.quote(",".join(ids), safe=",")
    url = f"https://api.coincap.io/v2/assets?ids={ids_param}"
    data, _ = _safe_http_json(url, PROVIDER_TIMEOUT, "coincap")
    rows = data.get("data", []) if isinstance(data, dict) else []
    if not isinstance(rows, list):
        return {}, requested, True

    out: Dict[str, float] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        aid = _coerce_str(row.get("id")).lower()
        sym = reverse.get(aid)
        if not sym:
            continue
        try:
            px = float(row.get("priceUsd", 0.0) or 0.0)
        except Exception:
            px = 0.0
        if px > 0:
            out[sym] = px
    missing = [sym for sym in requested if sym not in out]
    return out, missing, True


def _fetch_from_cryptocompare(symbols: List[str]) -> Tuple[Dict[str, float], List[str], bool]:
    requested = [_normalize_symbol(sym) for sym in symbols]
    base_map: Dict[str, str] = {}
    for sym in requested:
        if not sym.endswith("USDT"):
            continue
        base = sym[:-4]
        if base:
            base_map[base] = sym
    if not base_map:
        return {}, requested, False

    syms_param = urllib.parse.quote(",".join(sorted(base_map.keys())), safe=",")
    url = CRYPTOCOMPARE_API.format(symbols=syms_param)
    data, _ = _safe_http_json(url, PROVIDER_TIMEOUT, "cryptocompare")
    if not isinstance(data, dict):
        return {}, requested, True

    out: Dict[str, float] = {}
    for base, payload in data.items():
        if not isinstance(payload, dict):
            continue
        sym = base_map.get(_coerce_str(base).upper())
        if not sym:
            continue
        try:
            px = float(payload.get("USD", 0.0) or 0.0)
        except Exception:
            px = 0.0
        if px > 0:
            out[sym] = px
    missing = [sym for sym in requested if sym not in out]
    return out, missing, True


def _lane_for_symbol(symbol: str) -> Tuple[str, Dict[str, str]]:
    if not SPARK_MODE or not LANE_CONFIG:
        return "default", {}

    normalized = _normalize_symbol(symbol)
    normalized_lookup: Dict[str, Dict[str, str]] = {}
    for key, cfg in LANE_CONFIG.items():
        key_norm = _normalize_symbol(key)
        if key_norm:
            normalized_lookup[key_norm] = cfg

    if normalized in normalized_lookup:
        return normalized, normalized_lookup[normalized]

    wildcard = normalized_lookup.get("*")
    if normalized_lookup.get("DEFAULT"):
        return "default", normalized_lookup["DEFAULT"]
    if wildcard:
        return "wildcard", wildcard
    return "default", {}


def _ema(values: List[float], period: int) -> List[float]:
    if not values:
        return []
    alpha = 2.0 / (period + 1.0)
    out = [values[0]]
    for val in values[1:]:
        out.append(alpha * val + (1.0 - alpha) * out[-1])
    return out


def _fetch_spot_prices(symbols: List[str]) -> Tuple[Dict[str, float], Dict[str, str]]:
    global FETCH_ERROR_STREAK
    requested: List[str] = [_normalize_symbol(sym) for sym in symbols]
    requested = [s for s in requested if s]
    if not requested:
        FETCH_ERROR_STREAK = 0
        return {}, {}

    remaining = list(requested)
    prices: Dict[str, float] = {}
    provider_by_symbol: Dict[str, str] = {}

    for provider in _PROVIDERS:
        if not remaining:
            break

        if provider == "coingecko":
            try:
                got, missing, ok = _fetch_from_coingecko(remaining)
            except urllib.error.HTTPError as exc:
                if exc.code == 429:
                    _log("spot fetch failed: coingecko HTTP 429 rate limit reached")
                else:
                    _log(f"spot fetch failed: coingecko HTTP {exc.code}")
                continue
            except Exception as exc:
                _log(f"spot fetch failed: coingecko {exc}")
                continue
            if ok:
                for sym, px in got.items():
                    if sym in remaining:
                        prices[sym] = px
                        provider_by_symbol[sym] = "coingecko"
                remaining = [s for s in remaining if s not in prices]
                if not remaining:
                    break
                if missing:
                    _log(f"coingecko missing {','.join(sorted(set(missing)))} in batch")
                continue
            if got:
                for sym, px in got.items():
                    if sym in remaining:
                        prices[sym] = px
                        provider_by_symbol[sym] = "coingecko"
                remaining = [s for s in remaining if s not in prices]

        elif provider == "binance":
            try:
                got, missing, ok = _fetch_from_binance(remaining)
            except urllib.error.HTTPError as exc:
                _log(f"spot fetch failed: binance HTTP {exc.code}")
                continue
            except Exception as exc:
                _log(f"spot fetch failed: binance {exc}")
                continue
            if ok:
                for sym, px in got.items():
                    if sym in remaining:
                        prices[sym] = px
                        provider_by_symbol[sym] = "binance"
                remaining = [s for s in remaining if s not in prices]
                if not remaining:
                    break
                if missing:
                    _log(f"binance missing {','.join(sorted(set(missing)))} in batch")
        elif provider == "coinbase":
            try:
                got, missing, ok = _fetch_from_coinbase(remaining)
            except urllib.error.HTTPError as exc:
                _log(f"spot fetch failed: coinbase HTTP {exc.code}")
                continue
            except Exception as exc:
                _log(f"spot fetch failed: coinbase {exc}")
                continue
            if ok:
                for sym, px in got.items():
                    if sym in remaining:
                        prices[sym] = px
                        provider_by_symbol[sym] = "coinbase"
                remaining = [s for s in remaining if s not in prices]
                if not remaining:
                    break
                if missing:
                    _log(f"coinbase missing {','.join(sorted(set(missing)))} in batch")
        elif provider == "coincap":
            try:
                got, missing, ok = _fetch_from_coincap(remaining)
            except urllib.error.HTTPError as exc:
                _log(f"spot fetch failed: coincap HTTP {exc.code}")
                continue
            except Exception as exc:
                _log(f"spot fetch failed: coincap {exc}")
                continue
            if ok:
                for sym, px in got.items():
                    if sym in remaining:
                        prices[sym] = px
                        provider_by_symbol[sym] = "coincap"
                remaining = [s for s in remaining if s not in prices]
                if not remaining:
                    break
                if missing:
                    _log(f"coincap missing {','.join(sorted(set(missing)))} in batch")
        elif provider == "cryptocompare":
            try:
                got, missing, ok = _fetch_from_cryptocompare(remaining)
            except urllib.error.HTTPError as exc:
                _log(f"spot fetch failed: cryptocompare HTTP {exc.code}")
                continue
            except Exception as exc:
                _log(f"spot fetch failed: cryptocompare {exc}")
                continue
            if ok:
                for sym, px in got.items():
                    if sym in remaining:
                        prices[sym] = px
                        provider_by_symbol[sym] = "cryptocompare"
                remaining = [s for s in remaining if s not in prices]
                if not remaining:
                    break
                if missing:
                    _log(f"cryptocompare missing {','.join(sorted(set(missing)))} in batch")
        else:
            _log(f"unknown PRICE_PROVIDER '{provider}', skipping")

    if not prices:
        if remaining:
            _log(f"spot fetch produced no usable prices for symbols={','.join(sorted(set(remaining)))}")
            FETCH_ERROR_STREAK = max(1, FETCH_ERROR_STREAK + 1)
        else:
            FETCH_ERROR_STREAK = 0
    elif remaining:
        FETCH_ERROR_STREAK = 0
        _log(f"spot fetch partial for {','.join(sorted(set(requested)))}; missing={','.join(sorted(set(remaining)))}")
    else:
        FETCH_ERROR_STREAK = 0

    # Preserve original symbol keys when available, keeping request order where possible.
    normalized_out: Dict[str, float] = {}
    for requested_symbol in requested:
        if requested_symbol in prices:
            normalized_out[requested_symbol] = prices[requested_symbol]

    return normalized_out, provider_by_symbol


def _signal_from_prices(closes: List[float]) -> Tuple[Optional[str], float, float, Dict[str, float]]:
    """
    Returns: (action, confidence, edge_pct, diagnostics)
    action: "buy", "sell", or None
    """
    fast = _ema(closes, EMA_FAST)
    slow = _ema(closes, EMA_SLOW)
    if len(fast) < 4 or len(slow) < 4:
        return None, 0.0, 0.0, {}

    f0 = fast[-1]
    f1 = fast[-2]
    f3 = fast[-4]
    s1 = slow[-2]
    s0 = slow[-1]
    if f0 <= 0 or s0 <= 0 or s1 <= 0:
        return None, 0.0, 0.0, {}

    edge_pct = ((f0 - s0) / s0) * 100.0
    slope_pct = ((f0 - f3) / f3) * 100.0 if f3 > 0 else 0.0
    accel_pct = ((f0 - f1) / f1) * 100.0 if f1 > 0 else 0.0
    cross_up = f1 <= s1 and f0 > s0
    cross_down = f1 >= s1 and f0 < s0
    diagnostics = {
        "edge_pct": round(float(edge_pct), 6),
        "slope_pct": round(float(slope_pct), 6),
        "accel_pct": round(float(accel_pct), 6),
        "cross_up": 1.0 if cross_up else 0.0,
        "cross_down": 1.0 if cross_down else 0.0,
    }

    action: Optional[str] = None
    if cross_up:
        action = "buy"
    elif cross_down:
        action = "sell"
    elif edge_pct >= EDGE_THRESHOLD_PCT and slope_pct > 0:
        action = "buy"
    elif edge_pct <= -EDGE_THRESHOLD_PCT and slope_pct < 0:
        action = "sell"
    elif edge_pct >= MOMENTUM_EDGE_THRESHOLD_PCT and accel_pct > 0:
        action = "buy"
    elif edge_pct <= -MOMENTUM_EDGE_THRESHOLD_PCT and accel_pct < 0:
        action = "sell"

    raw_conf = 0.62 + min(0.28, abs(edge_pct) * 1.1 + abs(slope_pct) * 0.5)
    if cross_up or cross_down:
        raw_conf += 0.03
    if abs(accel_pct) > 0:
        raw_conf += min(0.02, abs(accel_pct) * 0.8)
    confidence = max(MIN_CONFIDENCE, min(0.95, raw_conf))
    return action, confidence, edge_pct, diagnostics


def _publish_signal(
    symbol: str,
    action: str,
    confidence: float,
    edge_pct: float,
    diagnostics: Optional[Dict[str, float]] = None,
    price_provider: str = "coingecko",
) -> str:
    lane_name, lane_cfg = _lane_for_symbol(symbol)
    strategy = _coerce_str(
        lane_cfg.get("strategy", STRATEGY_FALLBACK),
        STRATEGY_FALLBACK,
    )
    timeframe = _coerce_str(
        lane_cfg.get("timeframe", TIMEFRAME_FALLBACK),
        TIMEFRAME_FALLBACK,
    ).lower()
    source = _coerce_str(
        lane_cfg.get("source", SOURCE),
        SOURCE,
    )
    symbol_norm = _normalize_symbol(symbol)
    strategy_norm = _coerce_str(strategy).lower()
    timeframe_norm = _coerce_str(timeframe).lower()
    side = action.strip().lower()
    side_edge_pct = edge_pct if side == "buy" else -edge_pct
    friction_pct = (EST_FEE_BPS + EST_SLIPPAGE_BPS) / 100.0
    net_edge_pct = side_edge_pct - friction_pct

    if abs(edge_pct) < MIN_ABS_EDGE_PCT:
        _log(
            "skipped %s %s conf=%.3f edge=%+.3f%% tf=%s strat=%s lane=%s reason=edge_below_floor(min=%.3f%%)"
            % (
                action.upper(),
                symbol,
                confidence,
                edge_pct,
                timeframe,
                strategy,
                lane_name,
                MIN_ABS_EDGE_PCT,
            )
        )
        return "skipped"

    if side_edge_pct <= 0:
        _log(
            "skipped %s %s conf=%.3f edge=%+.3f%% tf=%s strat=%s lane=%s reason=directional_edge_invalid"
            % (
                action.upper(),
                symbol,
                confidence,
                edge_pct,
                timeframe,
                strategy,
                lane_name,
            )
        )
        return "skipped"

    if net_edge_pct < MIN_NET_EDGE_PCT:
        _log(
            "skipped %s %s conf=%.3f edge=%+.3f%% net=%+.3f%% tf=%s strat=%s lane=%s reason=net_edge_below_floor(min=%.3f%% fee=%.2fbps slippage=%.2fbps)"
            % (
                action.upper(),
                symbol,
                confidence,
                edge_pct,
                net_edge_pct,
                timeframe,
                strategy,
                lane_name,
                MIN_NET_EDGE_PCT,
                EST_FEE_BPS,
                EST_SLIPPAGE_BPS,
            )
        )
        return "skipped"

    live_lane = True
    dry_run_reasons: List[str] = []
    if LIVE_EXEC_SYMBOLS and symbol_norm not in LIVE_EXEC_SYMBOLS:
        live_lane = False
        dry_run_reasons.append("symbol_not_in_live_scope")
    if LIVE_EXEC_TIMEFRAMES and timeframe_norm not in LIVE_EXEC_TIMEFRAMES:
        live_lane = False
        dry_run_reasons.append("timeframe_not_in_live_scope")
    if LIVE_EXEC_STRATEGIES and strategy_norm not in LIVE_EXEC_STRATEGIES:
        live_lane = False
        dry_run_reasons.append("strategy_not_in_live_scope")
    dry_run = not live_lane
    if dry_run and not PUBLISH_RESEARCH_SIGNALS:
        _log(
            "skipped %s %s conf=%.3f edge=%+.3f%% tf=%s strat=%s lane=%s reason=%s"
            % (
                action.upper(),
                symbol,
                confidence,
                edge_pct,
                timeframe,
                strategy,
                lane_name,
                ",".join(dry_run_reasons) or "research_only",
            )
        )
        return "skipped"

    payload = {
        "secret": WEBHOOK_SECRET,
        "symbol": symbol,
        "action": action,
        "confidence": round(float(confidence), 4),
        "dry_run": dry_run,
        "source": source,
        "strategy": strategy,
        "timeframe": timeframe,
        "metadata": {
            "strategy": strategy,
            "timeframe": timeframe,
            "source": source,
            "lane": lane_name,
            "edge_pct": round(float(edge_pct), 5),
            "edge_side_pct": round(float(side_edge_pct), 5),
            "edge_friction_pct": round(float(friction_pct), 5),
            "net_edge_pct": round(float(net_edge_pct), 5),
            "experiment_mode": "overnight_diversification",
            "execution_scope": "live" if live_lane else "research_only",
            "dry_run": dry_run,
            "dry_run_reason": ",".join(dry_run_reasons),
            "generated_at": _now_iso(),
            "price_provider": price_provider,
            "diagnostics": diagnostics or {},
        },
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url=GATEWAY_WEBHOOK_URL,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "X-Sapphire-Webhook-Secret": WEBHOOK_SECRET},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8")
            code = int(resp.status)
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8")
        except Exception:
            pass
        _log(f"publish failed {symbol} {action}: http={exc.code} body={detail[:180]}")
        return "failed"
    except Exception as exc:
        _log(f"publish failed {symbol} {action}: {exc}")
        return "failed"

    if code != 200:
        _log(f"publish non-200 {symbol} {action}: {code} {raw[:180]}")
        return "failed"
    try:
        data = json.loads(raw)
    except Exception:
        data = {}
    _log(
        "published %s %s conf=%.3f edge=%+.3f%% tf=%s strat=%s lane=%s mode=%s signal_id=%s status=%s"
        % (
            action.upper(),
            symbol,
            confidence,
            edge_pct,
            timeframe,
            strategy,
            lane_name,
            ("live" if live_lane else "dry_run"),
            str(data.get("signal_id", "")),
            str(data.get("status", "")),
        )
    )
    return "published"


def _format_status_snapshot() -> str:
    if not LAST_GATEWAY_STATUS:
        return "status=none"
    return ",".join(f"{k}:{v}" for k, v in sorted(LAST_GATEWAY_STATUS.items()))


def _log_cycle_summary(
    cycle_id: int,
    cycle_elapsed: float,
    scanned: int,
    sent: int,
    warmup: int,
    no_signal: int,
    no_price: int,
    cooldown_skip: int,
    publish_failed: int,
) -> None:
    warm = {
        sym: len(PRICE_HISTORY.get(sym, []))
        for sym in SYMBOLS
    }
    provider_snapshot = ",".join(
        f"{k}:{LAST_PROVIDER_STATUS.get(k, 0)}"
        for k in _PROVIDERS
    )
    _log(
        "cycle=%d elapsed=%.1fs scanned=%d warmup=%d no_signal=%d no_price=%d cooldown=%d sent=%d publish_fail=%d providers=%s symbols=%s"
        % (
            cycle_id,
            cycle_elapsed,
            scanned,
            warmup,
            no_signal,
            no_price,
            cooldown_skip,
            sent,
            publish_failed,
            provider_snapshot or "none",
            warm,
        )
    )


def _should_send(symbol: str, action: str) -> bool:
    now = time.time()
    prev = LAST_SENT.get(symbol)
    if not prev:
        return True
    prev_action, prev_ts = prev
    if action != prev_action:
        return True
    return (now - prev_ts) >= SYMBOL_COOLDOWN_SECONDS


def _active_symbols() -> List[str]:
    if LOCKED_SYMBOL:
        return [LOCKED_SYMBOL]
    return list(SYMBOLS)


def _handle_signal(signum, frame):  # type: ignore[no-untyped-def]
    global RUNNING
    RUNNING = False
    _log(f"received signal {signum}, shutting down")


def _sleep_with_cancel(total_seconds: float) -> bool:
    """
    Sleep in small chunks so SIGTERM/SIGINT can be observed quickly.
    Returns True if shutdown was requested.
    """
    remaining = max(0.0, float(total_seconds))
    while remaining > 0 and RUNNING:
        chunk = min(SHUTDOWN_POLL_SECONDS, remaining)
        time.sleep(chunk)
        remaining -= chunk
    return not RUNNING


def main() -> int:
    if not WEBHOOK_SECRET:
        _log("missing WEBHOOK_SECRET; refusing to start")
        return 2
    if not SYMBOLS:
        _log("no symbols configured; refusing to start")
        return 2

    global LANE_CONFIG
    if SPARK_MODE:
        LANE_CONFIG = _load_lane_config(SPARK_LANE_CONFIG)
        if not LANE_CONFIG:
            _log("SPARK_MODE enabled but lane config is empty; using global defaults")
    else:
        LANE_CONFIG = {}

    if not SPARK_MODE and SPARK_LANE_CONFIG:
        _log("SPARK_MODE disabled; SPARK_LANE_CONFIG ignored")

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    _log(
        "overnight explorer starting | symbols=%s lock=%s timeframe=%s scan=%ss cooldown=%ss strategy=%s spark=%s lane_cfg=%s research_publish=%s strict_live=%s "
        "live_scope[symbols=%s tf=%s strategies=%s]"
        % (
            ",".join(SYMBOLS),
            (LOCKED_SYMBOL or "none"),
            TIMEFRAME,
            SCAN_SECONDS,
            SYMBOL_COOLDOWN_SECONDS,
            STRATEGY,
            "true" if SPARK_MODE else "false",
            len(LANE_CONFIG),
            "true" if PUBLISH_RESEARCH_SIGNALS else "false",
            "true" if STRICT_LIVE_MODE else "false",
            ",".join(sorted(LIVE_EXEC_SYMBOLS)) if LIVE_EXEC_SYMBOLS else "*",
            ",".join(sorted(LIVE_EXEC_TIMEFRAMES)) if LIVE_EXEC_TIMEFRAMES else "*",
            ",".join(sorted(LIVE_EXEC_STRATEGIES)) if LIVE_EXEC_STRATEGIES else "*",
        )
    )
    if SPARK_MODE and LANE_CONFIG:
        _log(f"spark lanes loaded: {','.join(sorted(LANE_CONFIG.keys()))}")

    _log(
        "provider pipeline: %s | http_timeout=%ss provider_timeout=%ss retries=%d | strategy=%s tf=%s edge>=%.3f abs_edge>=%.3f net_edge>=%.3f conf>=%.2f fee=%.2fbps slippage=%.2fbps"
        % (
            ",".join(_PROVIDERS),
            HTTP_TIMEOUT,
            PROVIDER_TIMEOUT,
            PROVIDER_MAX_RETRIES,
            STRATEGY,
            TIMEFRAME,
            EDGE_THRESHOLD_PCT,
            MIN_ABS_EDGE_PCT,
            MIN_NET_EDGE_PCT,
            MIN_CONFIDENCE,
            EST_FEE_BPS,
            EST_SLIPPAGE_BPS,
        )
    )

    global CYCLE_COUNT, LAST_PROVIDER_STATUS, LAST_GATEWAY_STATUS
    while RUNNING:
        CYCLE_COUNT += 1
        cycle_started = time.time()
        active_symbols = _active_symbols()
        if (CYCLE_COUNT % PROVIDER_CYCLE_SUMMARY_EVERY) == 0:
            _log(f"cycle {CYCLE_COUNT} start | active_symbols={','.join(active_symbols)}")

        if CYCLE_COUNT == 1:
            _log(f"active lanes={len(LANE_CONFIG)} spark={str(SPARK_MODE).lower()}")

        LAST_PROVIDER_STATUS = {provider: 0 for provider in _PROVIDERS}
        LAST_GATEWAY_STATUS = {"200": 0, "skipped": 0, "non_200": 0, "error": 0}
        prices, provider_map = _fetch_spot_prices(active_symbols)
        scanned = len([s for s in active_symbols if s in prices])
        no_price = len(active_symbols) - scanned

        if not prices:
            delay = max(1.0, float(SCAN_SECONDS))
            if FETCH_ERROR_STREAK >= 2:
                backoff = min(120.0, float(SCAN_SECONDS) * (1 << min(FETCH_ERROR_STREAK - 1, 4)))
                delay = max(delay, backoff)
                _log(f"fetch failures detected ({FETCH_ERROR_STREAK}) ; sleeping {delay:.1f}s before retry")
            _log(f"cycle={CYCLE_COUNT} completed; no_price_data; warmup={scanned}")
            if _sleep_with_cancel(delay):
                break
            continue

        scanned_count = 0
        no_signal_count = 0
        cooldown_skip = 0
        warmup = 0
        published_count = 0
        publish_failed = 0
        for sym in active_symbols:
            if not RUNNING:
                break
            scanned_count += 1
            px = float(prices.get(sym, 0.0) or 0.0)
            if px <= 0:
                continue
            hist = PRICE_HISTORY.setdefault(sym, deque(maxlen=HISTORY_LIMIT))
            hist.append(px)
            closes = list(hist)
            if len(closes) < max(EMA_FAST, EMA_SLOW) + 4:
                warmup += 1
                continue
            action, confidence, edge_pct, diagnostics = _signal_from_prices(closes)
            if not action:
                no_signal_count += 1
                continue
            if not _should_send(sym, action):
                cooldown_skip += 1
                continue
            price_provider = provider_map.get(sym, "coingecko")
            publish_state = _publish_signal(
                sym,
                action,
                confidence,
                edge_pct,
                diagnostics=diagnostics,
                price_provider=price_provider,
            )
            if publish_state == "published":
                published_count += 1
                LAST_GATEWAY_STATUS["200"] += 1
                LAST_SENT[sym] = (action, time.time())
            elif publish_state == "skipped":
                LAST_GATEWAY_STATUS["skipped"] += 1
            else:
                publish_failed += 1
                LAST_GATEWAY_STATUS["error"] += 1
            if _sleep_with_cancel(0.4):
                break

        elapsed = time.time() - cycle_started
        if (CYCLE_COUNT % PROVIDER_CYCLE_SUMMARY_EVERY) == 0:
            for sym, provider in provider_map.items():
                LAST_PROVIDER_STATUS[provider] = LAST_PROVIDER_STATUS.get(provider, 0) + 1
            _log_cycle_summary(
                cycle_id=CYCLE_COUNT,
                cycle_elapsed=elapsed,
                scanned=scanned_count,
                sent=published_count,
                warmup=warmup,
                no_signal=no_signal_count,
                no_price=no_price,
                cooldown_skip=cooldown_skip,
                publish_failed=publish_failed,
            )
        sleep_for = max(1.0, float(SCAN_SECONDS) - elapsed)
        if _sleep_with_cancel(sleep_for):
            break

    _log("overnight explorer stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
