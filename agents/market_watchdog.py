#!/usr/bin/env python3
"""
Sapphire Market Watchdog Agent — runs on rari1 (100.120.191.1).

Monitors market conditions and fires Telegram alerts:
  - Major index moves (SPY, QQQ > 2% daily)
  - VIX spikes (crosses 25 or +20% intraday)
  - Crypto price thresholds (BTC/ETH/SOL configured levels)
  - Crypto 24h moves exceeding thresholds

Designed to run within rari1's 3.8GB RAM constraint alongside Ollama.
Uses stdlib + httpx (installed) only. Config: agents/config/watchdog.yaml

Runs as systemd service: market-watchdog.service
Health endpoint: http://rari1_ip:19001/health

Usage:
    python3 market_watchdog.py [--config /path/to/watchdog.yaml] [--once]
"""
from __future__ import annotations

import json
import logging
import os
import signal
import sys
import time
import threading
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from datetime import UTC, datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Any

try:
    import yaml
    _YAML_AVAILABLE = True
except ImportError:
    _YAML_AVAILABLE = False

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [watchdog] %(message)s",
    handlers=[
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("market-watchdog")

# ─── Configuration ─────────────────────────────────────────────────────────────

DEFAULT_CONFIG = {
    "agent": {"name": "market-watchdog", "health_port": 19001},
    "intervals": {"market_check": 300, "crypto_check": 180, "heartbeat": 60},
    "openbb": {"base_url": "http://100.67.171.79:6900", "timeout": 10},
    "telegram": {"proxy_url": "http://100.67.171.79:11435", "priority": "p1"},
    "indices": [
        {"symbol": "SPY", "name": "S&P 500", "alert_threshold_pct": 2.0},
        {"symbol": "QQQ", "name": "NASDAQ",   "alert_threshold_pct": 2.5},
        {"symbol": "VIX", "name": "VIX",
         "alert_threshold_abs": 25.0, "alert_spike_pct": 20.0},
    ],
    "crypto": [
        {"ticker": "BTC", "coingecko_id": "bitcoin",  "alert_threshold_pct": 5.0,
         "price_levels": [{"level": 60000, "direction": "down", "label": "BTC fell below $60K"},
                           {"level": 70000, "direction": "up",   "label": "BTC broke above $70K"}]},
        {"ticker": "ETH", "coingecko_id": "ethereum", "alert_threshold_pct": 6.0,
         "price_levels": [{"level": 3000,  "direction": "down", "label": "ETH fell below $3K"},
                           {"level": 4000,  "direction": "up",   "label": "ETH broke above $4K"}]},
        {"ticker": "SOL", "coingecko_id": "solana",   "alert_threshold_pct": 8.0},
    ],
    "cooldown": {"same_alert_seconds": 3600, "max_alerts_per_hour": 10},
    "state": {"path": "/home/rari/sapphire/watchdog_state.json", "save_interval": 60},
}


def load_config(path: str | None = None) -> dict:
    if path and _YAML_AVAILABLE:
        try:
            with open(path) as f:
                return yaml.safe_load(f)
        except Exception as e:
            log.warning("Config load failed (%s), using defaults: %s", path, e)
    return DEFAULT_CONFIG


# ─── HTTP Helpers ─────────────────────────────────────────────────────────────

def _get_json(url: str, timeout: int = 8) -> dict | list | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "sapphire-watchdog/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception:
        return None


def _post_json(url: str, data: dict, timeout: int = 10) -> dict | None:
    try:
        body = json.dumps(data).encode()
        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception:
        return None


# ─── Telegram Notifications ───────────────────────────────────────────────────

def send_telegram(msg: str, proxy_url: str, priority: str = "p1") -> bool:
    """Send a Telegram alert via the bot API.

    Requires TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID. ``proxy_url`` and
    ``priority`` are retained for call-site compatibility but unused:
    the inference proxy is an LLM chat proxy, not a notification relay.
    Returns False with a warning when credentials are missing.
    """
    del proxy_url, priority  # intentional: no LLM fallback
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not (bot_token and chat_id):
        log.warning(
            "send_telegram: TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID unset — alert dropped: %s",
            msg[:120],
        )
        return False
    data = {"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"}
    result = _post_json(
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        data,
        timeout=10,
    )
    return bool(result and result.get("ok"))


# ─── Price Fetchers ───────────────────────────────────────────────────────────

def fetch_crypto_prices(coin_ids: list[str]) -> dict[str, dict]:
    """Fetch prices from CoinGecko (direct, no API key needed for basic tier)."""
    ids_str = ",".join(coin_ids)
    url = (
        f"https://api.coingecko.com/api/v3/simple/price"
        f"?ids={ids_str}&vs_currencies=usd"
        f"&include_24hr_change=true&include_24hr_vol=true"
    )
    data = _get_json(url, timeout=12)
    return data or {}


def fetch_index_quote(symbol: str, openbb_url: str, timeout: int = 8) -> dict | None:
    """Fetch equity/ETF quote from OpenBB on Mac."""
    url = f"{openbb_url}/api/v1/equity/price/quote?symbol={symbol}&provider=yfinance"
    data = _get_json(url, timeout=timeout)
    if not data:
        return None
    results = data.get("results", [])
    return results[0] if results else None


# ─── Alert State / Cooldown ───────────────────────────────────────────────────

@dataclass
class AlertState:
    last_prices: dict[str, float] = field(default_factory=dict)
    last_alerted: dict[str, float] = field(default_factory=dict)  # key → timestamp
    alerts_this_hour: int = 0
    hour_start: float = field(default_factory=time.time)
    last_save: float = field(default_factory=time.time)

    def can_alert(self, key: str, cooldown_seconds: int, max_per_hour: int) -> bool:
        now = time.time()
        # Reset hourly counter
        if now - self.hour_start > 3600:
            self.alerts_this_hour = 0
            self.hour_start = now
        if self.alerts_this_hour >= max_per_hour:
            return False
        last = self.last_alerted.get(key, 0)
        return (now - last) >= cooldown_seconds

    def record_alert(self, key: str) -> None:
        self.last_alerted[key] = time.time()
        self.alerts_this_hour += 1

    def save(self, path: str) -> None:
        try:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            data = {
                "last_prices": self.last_prices,
                "last_alerted": self.last_alerted,
                "alerts_this_hour": self.alerts_this_hour,
                "hour_start": self.hour_start,
                "saved_at": time.time(),
            }
            with open(path, "w") as f:
                json.dump(data, f)
        except Exception as e:
            log.warning("State save failed: %s", e)

    @classmethod
    def load(cls, path: str) -> "AlertState":
        try:
            with open(path) as f:
                data = json.load(f)
            state = cls()
            state.last_prices = data.get("last_prices", {})
            state.last_alerted = data.get("last_alerted", {})
            state.alerts_this_hour = data.get("alerts_this_hour", 0)
            state.hour_start = data.get("hour_start", time.time())
            return state
        except Exception:
            return cls()


# ─── Health HTTP Handler ───────────────────────────────────────────────────────

class _HealthHandler(BaseHTTPRequestHandler):
    watchdog: "MarketWatchdog | None" = None

    def do_GET(self):
        if self.path in {"/health", "/"}:
            status = {
                "status": "ok",
                "agent": "market-watchdog",
                "timestamp": datetime.now(UTC).isoformat(),
                "uptime_seconds": int(time.time() - (_HealthHandler.watchdog._start_ts if _HealthHandler.watchdog else 0)),
                "alerts_this_hour": _HealthHandler.watchdog._state.alerts_this_hour if _HealthHandler.watchdog else 0,
            }
            body = json.dumps(status).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, fmt, *args):
        pass  # Suppress access logs


# ─── Main Agent Class ──────────────────────────────────────────────────────────

class MarketWatchdog:
    def __init__(self, config: dict) -> None:
        self._cfg = config
        self._state = AlertState.load(config["state"]["path"])
        self._running = False
        self._start_ts = time.time()
        self._check_count = 0

        agent_cfg = config.get("agent", {})
        interval_cfg = config.get("intervals", {})
        self._health_port = int(agent_cfg.get("health_port", 19001))
        self._crypto_interval = int(interval_cfg.get("crypto_check", 180))
        self._market_interval = int(interval_cfg.get("market_check", 300))

        self._openbb_url = config.get("openbb", {}).get("base_url", "http://100.67.171.79:6900")
        self._openbb_timeout = int(config.get("openbb", {}).get("timeout", 10))
        self._telegram_url = config.get("telegram", {}).get("proxy_url", "http://100.67.171.79:11435")
        self._telegram_priority = config.get("telegram", {}).get("priority", "p1")
        self._cooldown = int(config.get("cooldown", {}).get("same_alert_seconds", 3600))
        self._max_per_hour = int(config.get("cooldown", {}).get("max_alerts_per_hour", 10))
        self._state_path = config["state"]["path"]

        log.info(
            "MarketWatchdog initialized | health_port=%d | crypto_interval=%ds | market_interval=%ds",
            self._health_port, self._crypto_interval, self._market_interval,
        )

    def _alert(self, key: str, message: str, icon: str = "⚠️") -> None:
        if not self._state.can_alert(key, self._cooldown, self._max_per_hour):
            log.debug("Alert suppressed (cooldown/rate-limit): %s", key)
            return
        full_msg = f"{icon} *Market Watchdog Alert*\n\n{message}\n\n_rari1 — {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}_"
        log.info("ALERT [%s]: %s", key, message)
        send_telegram(full_msg, self._telegram_url, self._telegram_priority)
        self._state.record_alert(key)

    def _check_crypto(self) -> None:
        crypto_cfgs = self._cfg.get("crypto", [])
        if not crypto_cfgs:
            return
        coin_ids = [c["coingecko_id"] for c in crypto_cfgs if "coingecko_id" in c]
        prices = fetch_crypto_prices(coin_ids)

        for crypto in crypto_cfgs:
            cg_id  = crypto.get("coingecko_id", "")
            ticker = crypto.get("ticker", cg_id.upper())
            data   = prices.get(cg_id, {})
            if not data:
                continue

            price      = float(data.get("usd", 0) or 0)
            change_24h = float(data.get("usd_24h_change", 0) or 0)
            threshold  = float(crypto.get("alert_threshold_pct", 5.0))

            # 24h change alert
            if abs(change_24h) >= threshold:
                icon = "🔴" if change_24h < 0 else "🟢"
                self._alert(
                    f"crypto_24h_{ticker}",
                    f"{ticker}: {change_24h:+.2f}% in 24h\nCurrent price: ${price:,.2f}",
                    icon,
                )

            # Price level alerts
            prev_price = self._state.last_prices.get(ticker, price)
            for level_cfg in crypto.get("price_levels", []):
                level     = float(level_cfg["level"])
                direction = level_cfg["direction"]
                label     = level_cfg.get("label", f"{ticker} crossed ${level:,.0f}")

                crossed = (
                    (direction == "down" and prev_price >= level > price) or
                    (direction == "up"   and prev_price <= level < price)
                )
                if crossed:
                    self._alert(f"price_level_{ticker}_{level}", label, "🚨")

            self._state.last_prices[ticker] = price

    def _check_indices(self) -> None:
        openbb_ok = bool(_get_json(f"{self._openbb_url}/api/v1/system/status", 3))
        if not openbb_ok:
            log.debug("OpenBB unavailable, skipping index check")
            return

        for idx_cfg in self._cfg.get("indices", []):
            symbol    = idx_cfg["symbol"]
            name      = idx_cfg.get("name", symbol)
            threshold = float(idx_cfg.get("alert_threshold_pct", 2.0))
            abs_threshold = float(idx_cfg.get("alert_threshold_abs", 0))
            spike_threshold = float(idx_cfg.get("alert_spike_pct", 0))

            q = fetch_index_quote(symbol, self._openbb_url, self._openbb_timeout)
            if not q:
                continue

            change_pct = float(q.get("change_percent", 0) or 0)
            price      = float(q.get("last_price", q.get("price", 0)) or 0)

            # Daily % move alert
            if threshold > 0 and abs(change_pct) >= threshold:
                icon = "🔴" if change_pct < 0 else "🟢"
                self._alert(
                    f"index_move_{symbol}",
                    f"{name} ({symbol}): {change_pct:+.2f}% today\nLevel: ${price:,.2f}",
                    icon,
                )

            # Absolute threshold (e.g. VIX crossing 25)
            prev = self._state.last_prices.get(symbol, price)
            if abs_threshold > 0:
                crossed_up   = prev < abs_threshold <= price
                crossed_down = prev > abs_threshold >= price
                if crossed_up:
                    self._alert(f"abs_cross_{symbol}_up",
                                f"{name} crossed above {abs_threshold}: now {price:.2f}", "🚨")
                elif crossed_down:
                    self._alert(f"abs_cross_{symbol}_dn",
                                f"{name} dropped below {abs_threshold}: now {price:.2f}", "📉")

            # Intraday spike (e.g. VIX +20%)
            if spike_threshold > 0 and abs(change_pct) >= spike_threshold:
                self._alert(f"spike_{symbol}", f"{name} intraday spike: {change_pct:+.2f}%", "🚨")

            self._state.last_prices[symbol] = price

    def _save_loop(self) -> None:
        save_interval = int(self._cfg.get("state", {}).get("save_interval", 60))
        while self._running:
            time.sleep(save_interval)
            self._state.save(self._state_path)

    def _health_server(self) -> None:
        _HealthHandler.watchdog = self
        server = HTTPServer(("0.0.0.0", self._health_port), _HealthHandler)
        server.timeout = 1
        log.info("Health server listening on :%d", self._health_port)
        while self._running:
            server.handle_request()

    def run_once(self) -> None:
        """Single check cycle — useful for testing."""
        log.info("Running single check cycle")
        self._check_crypto()
        self._check_indices()
        self._state.save(self._state_path)
        log.info("Check cycle complete")

    def run(self) -> None:
        self._running = True
        log.info("Market Watchdog starting — crypto every %ds, markets every %ds",
                 self._crypto_interval, self._market_interval)

        # Health server in background
        threading.Thread(target=self._health_server, daemon=True).start()
        # State persistence in background
        threading.Thread(target=self._save_loop, daemon=True).start()

        # Signal startup to Telegram
        self._alert(
            "watchdog_start",
            "Market Watchdog started on rari1. Monitoring BTC/ETH/SOL + SPY/QQQ/VIX.",
            "🟢",
        )

        next_market = time.time()
        next_crypto = time.time()

        while self._running:
            now = time.time()
            try:
                if now >= next_crypto:
                    self._check_crypto()
                    next_crypto = now + self._crypto_interval

                if now >= next_market:
                    self._check_indices()
                    next_market = now + self._market_interval

                self._check_count += 1
            except Exception as e:
                log.error("Check cycle error: %s", e, exc_info=True)

            time.sleep(10)  # tight loop, 10s resolution

    def stop(self) -> None:
        self._running = False
        self._state.save(self._state_path)
        log.info("Market Watchdog stopped")


# ─── Entry Point ─────────────────────────────────────────────────────────────

def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Sapphire Market Watchdog")
    parser.add_argument("--config", default=None, help="Path to watchdog.yaml")
    parser.add_argument("--once", action="store_true", help="Run one check cycle and exit")
    args = parser.parse_args()

    # Find config
    config_path = args.config
    if not config_path:
        candidates = [
            Path(__file__).parent / "config" / "watchdog.yaml",
            Path.home() / "sapphire" / "config" / "watchdog.yaml",
        ]
        for c in candidates:
            if c.exists():
                config_path = str(c)
                break

    config = load_config(config_path)

    # File logging
    log_dir = Path("/home/rari/sapphire/logs")
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_dir / "market-watchdog.log")
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logging.getLogger().addHandler(fh)
    except Exception:
        pass

    watchdog = MarketWatchdog(config)

    def _shutdown(signum, frame):
        log.info("Shutdown signal received")
        watchdog.stop()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    if args.once:
        watchdog.run_once()
    else:
        watchdog.run()


if __name__ == "__main__":
    main()
