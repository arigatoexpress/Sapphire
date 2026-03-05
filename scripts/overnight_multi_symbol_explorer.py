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
from datetime import datetime, timezone
from collections import deque
from typing import Deque, Dict, List, Optional, Tuple


def _env(name: str, default: str = "") -> str:
    return str(os.getenv(name, default)).strip()


GATEWAY_WEBHOOK_URL = _env(
    "GATEWAY_WEBHOOK_URL",
    "https://sapphire-gateway-s77j6bxyra-uc.a.run.app/webhook/tradingview",
)
WEBHOOK_SECRET = _env("WEBHOOK_SECRET", "")
SYMBOLS = [s.strip().upper() for s in _env("SYMBOLS", "BTCUSDT,ETHUSDT,SOLUSDT").split(",") if s.strip()]
TIMEFRAME = _env("TIMEFRAME", "5m").lower()
SCAN_SECONDS = max(30, int(float(_env("SCAN_SECONDS", "75"))))
SYMBOL_COOLDOWN_SECONDS = max(60, int(float(_env("SYMBOL_COOLDOWN_SECONDS", "300"))))
HISTORY_LIMIT = max(60, min(500, int(float(_env("HISTORY_LIMIT", "180")))))
EMA_FAST = max(3, int(float(_env("EMA_FAST", "9"))))
EMA_SLOW = max(5, int(float(_env("EMA_SLOW", "21"))))
EDGE_THRESHOLD_PCT = max(0.01, float(_env("EDGE_THRESHOLD_PCT", "0.10")))
MIN_CONFIDENCE = max(0.50, min(0.95, float(_env("MIN_CONFIDENCE", "0.67"))))
SOURCE = _env("SOURCE", "overnight-explorer")
STRATEGY = _env("STRATEGY", "overnight_ema_crossover")

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
COINGECKO_API = "https://api.coingecko.com/api/v3/simple/price"

RUNNING = True
LAST_SENT: Dict[str, Tuple[str, float]] = {}
PRICE_HISTORY: Dict[str, Deque[float]] = {
    s: deque(maxlen=HISTORY_LIMIT) for s in SYMBOLS
}
CYCLE_COUNT = 0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _log(msg: str) -> None:
    print(f"[{_now_iso()}] {msg}", flush=True)


def _ema(values: List[float], period: int) -> List[float]:
    if not values:
        return []
    alpha = 2.0 / (period + 1.0)
    out = [values[0]]
    for val in values[1:]:
        out.append(alpha * val + (1.0 - alpha) * out[-1])
    return out


def _fetch_spot_prices(symbols: List[str]) -> Dict[str, float]:
    ids: List[str] = []
    reverse: Dict[str, str] = {}
    for sym in symbols:
        coin_id = COINGECKO_SYMBOL_MAP.get(sym)
        if not coin_id:
            continue
        ids.append(coin_id)
        reverse[coin_id] = sym
    if not ids:
        return {}
    params = urllib.parse.urlencode({"ids": ",".join(ids), "vs_currencies": "usd"})
    url = f"{COINGECKO_API}?{params}"
    req = urllib.request.Request(url=url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        _log(f"spot fetch failed: {exc}")
        return {}
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
    return out


def _signal_from_prices(closes: List[float]) -> Tuple[Optional[str], float, float]:
    """
    Returns: (action, confidence, edge_pct)
    action: "buy", "sell", or None
    """
    fast = _ema(closes, EMA_FAST)
    slow = _ema(closes, EMA_SLOW)
    if len(fast) < 4 or len(slow) < 4:
        return None, 0.0, 0.0

    f0 = fast[-1]
    f1 = fast[-2]
    f3 = fast[-4]
    s0 = slow[-1]
    if f0 <= 0 or s0 <= 0:
        return None, 0.0, 0.0

    edge_pct = ((f0 - s0) / s0) * 100.0
    slope_pct = ((f0 - f3) / f3) * 100.0 if f3 > 0 else 0.0

    action: Optional[str] = None
    if edge_pct >= EDGE_THRESHOLD_PCT and slope_pct > 0:
        action = "buy"
    elif edge_pct <= -EDGE_THRESHOLD_PCT and slope_pct < 0:
        action = "sell"

    raw_conf = 0.62 + min(0.28, abs(edge_pct) * 1.1 + abs(slope_pct) * 0.5)
    confidence = max(MIN_CONFIDENCE, min(0.95, raw_conf))
    return action, confidence, edge_pct


def _publish_signal(symbol: str, action: str, confidence: float, edge_pct: float) -> bool:
    payload = {
        "secret": WEBHOOK_SECRET,
        "symbol": symbol,
        "action": action,
        "confidence": round(float(confidence), 4),
        "source": SOURCE,
        "strategy": STRATEGY,
        "timeframe": TIMEFRAME,
        "metadata": {
            "strategy": STRATEGY,
            "timeframe": TIMEFRAME,
            "source": SOURCE,
            "edge_pct": round(float(edge_pct), 5),
            "experiment_mode": "overnight_diversification",
            "generated_at": _now_iso(),
            "price_provider": "coingecko_simple_price",
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
        return False
    except Exception as exc:
        _log(f"publish failed {symbol} {action}: {exc}")
        return False

    if code != 200:
        _log(f"publish non-200 {symbol} {action}: {code} {raw[:180]}")
        return False
    try:
        data = json.loads(raw)
    except Exception:
        data = {}
    _log(
        "published %s %s conf=%.3f edge=%+.3f%% signal_id=%s status=%s"
        % (
            action.upper(),
            symbol,
            confidence,
            edge_pct,
            str(data.get("signal_id", "")),
            str(data.get("status", "")),
        )
    )
    return True


def _should_send(symbol: str, action: str) -> bool:
    now = time.time()
    prev = LAST_SENT.get(symbol)
    if not prev:
        return True
    prev_action, prev_ts = prev
    if action != prev_action:
        return True
    return (now - prev_ts) >= SYMBOL_COOLDOWN_SECONDS


def _handle_signal(signum, frame):  # type: ignore[no-untyped-def]
    global RUNNING
    RUNNING = False
    _log(f"received signal {signum}, shutting down")


def main() -> int:
    if not WEBHOOK_SECRET:
        _log("missing WEBHOOK_SECRET; refusing to start")
        return 2
    if not SYMBOLS:
        _log("no symbols configured; refusing to start")
        return 2

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    _log(
        "overnight explorer starting | symbols=%s timeframe=%s scan=%ss cooldown=%ss strategy=%s"
        % (",".join(SYMBOLS), TIMEFRAME, SCAN_SECONDS, SYMBOL_COOLDOWN_SECONDS, STRATEGY)
    )

    global CYCLE_COUNT
    while RUNNING:
        CYCLE_COUNT += 1
        cycle_started = time.time()
        prices = _fetch_spot_prices(SYMBOLS)
        if not prices:
            time.sleep(max(1.0, float(SCAN_SECONDS)))
            continue

        published_count = 0
        for sym in SYMBOLS:
            if not RUNNING:
                break
            px = float(prices.get(sym, 0.0) or 0.0)
            if px <= 0:
                continue
            hist = PRICE_HISTORY.setdefault(sym, deque(maxlen=HISTORY_LIMIT))
            hist.append(px)
            closes = list(hist)
            if len(closes) < max(EMA_FAST, EMA_SLOW) + 4:
                continue
            action, confidence, edge_pct = _signal_from_prices(closes)
            if not action:
                continue
            if not _should_send(sym, action):
                continue
            ok = _publish_signal(sym, action, confidence, edge_pct)
            if ok:
                published_count += 1
                LAST_SENT[sym] = (action, time.time())
            time.sleep(0.4)

        if (CYCLE_COUNT % 10) == 0:
            warm = {
                sym: len(PRICE_HISTORY.get(sym, []))
                for sym in SYMBOLS
            }
            _log(
                "cycle=%d published=%d warmup=%s"
                % (CYCLE_COUNT, published_count, warm)
            )

        elapsed = time.time() - cycle_started
        sleep_for = max(1.0, float(SCAN_SECONDS) - elapsed)
        time.sleep(sleep_for)

    _log("overnight explorer stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
