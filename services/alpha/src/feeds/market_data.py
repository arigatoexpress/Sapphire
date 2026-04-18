import asyncio
import json
import os
import time
from collections import defaultdict, deque
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any

import aiohttp
import websockets
from loguru import logger


class MarketDataAggregator:
    def __init__(self):
        self._chart_symbol = str(os.getenv("MARKET_CHART_SYMBOL", "SOL")).strip().upper() or "SOL"
        self.prices: dict[str, dict[str, float]] = {
            "ASTER": {self._chart_symbol: 0.0},
            "LIGHTER": {self._chart_symbol: 0.0},
        }
        self._tick_history: dict[str, dict[str, deque[tuple[float, float, float]]]] = defaultdict(
            lambda: defaultdict(deque)
        )
        self._history_retention_seconds = self._env_float(
            "MARKET_HISTORY_RETENTION_SECONDS", 21600.0, minimum=300.0
        )
        self._history_max_points = max(1000, int(os.getenv("MARKET_HISTORY_MAX_POINTS", "25000")))
        self.running = False

        self._aster_symbol = str(os.getenv("ASTER_SYMBOL", "SOLUSDT")).strip().upper() or "SOLUSDT"
        self._aster_ticker_url = str(
            os.getenv(
                "ASTER_TICKER_URL",
                f"https://fapi.asterdex.com/fapi/v1/ticker/price?symbol={self._aster_symbol}",
            )
        ).strip()
        self._aster_mark_price_url = str(
            os.getenv(
                "ASTER_MARK_PRICE_URL",
                f"https://fapi.asterdex.com/fapi/v1/premiumIndex?symbol={self._aster_symbol}",
            )
        ).strip()
        self._aster_book_ticker_url = str(
            os.getenv(
                "ASTER_BOOK_TICKER_URL",
                f"https://fapi.asterdex.com/fapi/v1/ticker/bookTicker?symbol={self._aster_symbol}",
            )
        ).strip()
        self._aster_poll_interval_seconds = self._env_float(
            "ASTER_POLL_INTERVAL_SECONDS", 2.0, minimum=0.5
        )
        self._aster_klines_url = str(
            os.getenv("ASTER_KLINES_URL", "https://fapi.asterdex.com/fapi/v1/klines")
        ).strip()
        self._aster_http_timeout_seconds = self._env_float(
            "ASTER_HTTP_TIMEOUT_SECONDS", 8.0, minimum=1.0
        )
        self._aster_last_issue = ""
        self._aster_last_issue_ts = 0.0

        self._lighter_market_symbol = str(
            os.getenv("LIGHTER_MARKET_SYMBOL", "SOL")
        ).strip().upper() or "SOL"
        self._lighter_market_id = str(os.getenv("LIGHTER_MARKET_ID", "2")).strip() or "2"
        self._lighter_market_ids = self._parse_lighter_market_ids()
        self._lighter_logs_url = str(
            os.getenv(
                "LIGHTER_LOGS_URL",
                f"https://explorer.elliot.ai/api/markets/{self._lighter_market_symbol}/logs",
            )
        ).strip()
        self._lighter_poll_interval_seconds = self._env_float(
            "LIGHTER_POLL_INTERVAL_SECONDS", 2.0, minimum=0.5
        )
        self._lighter_http_timeout_seconds = self._env_float(
            "LIGHTER_HTTP_TIMEOUT_SECONDS", 8.0, minimum=1.0
        )
        self._lighter_ws_retry_seconds = self._env_float(
            "LIGHTER_WS_RETRY_SECONDS", 3.0, minimum=1.0
        )
        self._lighter_ws_enabled = str(os.getenv("LIGHTER_WS_ENABLED", "false")).strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self._lighter_ws_urls = self._parse_ws_urls()
        self._lighter_seen_hashes: deque[str] = deque()
        self._lighter_seen_hash_set: set[str] = set()
        self._lighter_seen_hash_max = max(1000, int(os.getenv("LIGHTER_SEEN_HASH_MAX", "4000")))
        self._lighter_max_tick_jump_ratio = self._env_float(
            "LIGHTER_MAX_TICK_JUMP_RATIO", 3.0, minimum=1.2
        )
        self._lighter_tick_jump_window_seconds = self._env_float(
            "LIGHTER_TICK_JUMP_WINDOW_SECONDS", 600.0, minimum=30.0
        )

        self._lighter_last_issue = ""
        self._lighter_last_issue_ts = 0.0

        # --- Multi-symbol feed configuration ---------------------------------
        self._multi_symbol_enabled = str(
            os.getenv("MARKET_MULTI_SYMBOL_ENABLED", "true")
        ).strip().lower() in {"1", "true", "yes", "on"}
        self._multi_symbol_poll_interval = self._env_float(
            "MARKET_MULTI_SYMBOL_POLL_SECONDS", 10.0, minimum=3.0
        )
        self._extra_symbols: list[str] = self._parse_extra_symbols()
        self._aster_batch_ticker_url = str(
            os.getenv("ASTER_BATCH_TICKER_URL", "https://fapi.asterdex.com/fapi/v1/ticker/price")
        ).strip()
        self._lighter_base_logs_url = str(
            os.getenv("LIGHTER_BASE_LOGS_URL", "https://explorer.elliot.ai/api/markets")
        ).strip()

    @staticmethod
    def _parse_extra_symbols() -> list[str]:
        """Parse SAPPHIRE_PREFERRED_SYMBOLS for multi-symbol feeds."""
        import re as _re
        raw = os.getenv("SAPPHIRE_PREFERRED_SYMBOLS", "BTC,ETH,SOL,BCH,ZEC,XMR,PENGU,MON,LIT,ASTER,MEGAETH")
        tokens = _re.split(r"[,;|\s]+", str(raw or "").strip())
        seen: set[str] = set()
        result: list[str] = []
        for token in tokens:
            sym = token.strip().upper()
            if sym and sym not in seen:
                seen.add(sym)
                result.append(sym)
        return result

    def _parse_lighter_market_ids(self) -> dict[str, str]:
        """Parse LIGHTER_MARKET_IDS env var (e.g. 'BTC:0,ETH:1,SOL:2') into a mapping."""
        result: dict[str, str] = {}
        _default_ids = "BTC:1,ETH:0,SOL:2,BCH:58,ZEC:90,PENGU:47,XMR:77,MON:91,LIT:120,ASTER:83"
        raw = os.getenv("LIGHTER_MARKET_IDS", _default_ids).strip()
        if raw:
            for pair in raw.replace(";", ",").split(","):
                pair = pair.strip()
                if ":" in pair:
                    sym, mid = pair.split(":", 1)
                    sym = sym.strip().upper()
                    mid = mid.strip()
                    if sym and mid:
                        result[sym] = mid
        # Ensure the primary chart symbol always has an entry
        if self._chart_symbol not in result:
            result[self._chart_symbol] = self._lighter_market_id
        return result

    def _get_lighter_market_id(self, symbol: str) -> str:
        """Get market ID for a symbol, falling back to the default."""
        return self._lighter_market_ids.get(symbol.upper(), self._lighter_market_id)

    @staticmethod
    def _env_float(name: str, default: float, minimum: float = 0.0) -> float:
        raw = os.getenv(name, str(default))
        try:
            value = float(raw)
        except (TypeError, ValueError):
            value = default
        return max(minimum, value)

    def _parse_ws_urls(self) -> list[str]:
        raw = str(os.getenv("LIGHTER_WS_URLS", "")).strip()
        if raw:
            tokens = [item.strip() for item in raw.replace(";", ",").split(",")]
            return [token for token in tokens if token]

        fallback = [
            str(os.getenv("LIGHTER_WS_URL", "")).strip(),
            "wss://mainnet.zklighter.elliot.ai/stream",
            "wss://testnet.zklighter.elliot.ai/stream",
        ]
        deduped: list[str] = []
        for url in fallback:
            if url and url not in deduped:
                deduped.append(url)
        return deduped

    async def start(self):
        self.running = True
        # Primary single-symbol feeds (backward-compatible).
        asyncio.create_task(self._aster_feed())
        asyncio.create_task(self._lighter_feed())
        # Multi-symbol price feeds for preferred symbols.
        if self._multi_symbol_enabled and self._extra_symbols:
            asyncio.create_task(self._aster_multi_symbol_feed())
            asyncio.create_task(self._lighter_multi_symbol_feed())
            logger.info(
                "📊 Multi-symbol feeds enabled for {} symbols: {}",
                len(self._extra_symbols),
                ", ".join(self._extra_symbols[:6]) + ("..." if len(self._extra_symbols) > 6 else ""),
            )

    async def stop(self):
        self.running = False

    def get_price(self, venue: str, symbol: str) -> float:
        venue_prices = self.prices.get(venue, {})
        return venue_prices.get(symbol, venue_prices.get(self._chart_symbol, 0.0))

    def get_market_snapshot(self, symbol: str = "SOL") -> dict[str, dict[str, Any]]:
        symbol_key = str(symbol or "").strip().upper() or self._chart_symbol
        now = time.time()
        snapshot: dict[str, dict[str, Any]] = {}

        for venue in ("ASTER", "LIGHTER"):
            price = self.get_price(venue, symbol_key)
            ticks = self._tick_history.get(venue, {}).get(symbol_key, deque())
            last_tick_ts = float(ticks[-1][0]) if ticks else 0.0
            age_seconds = int(max(0.0, now - last_tick_ts)) if last_tick_ts > 0 else None

            if price > 0 and age_seconds is not None and age_seconds <= 120:
                status = "healthy"
            elif price > 0:
                status = "degraded"
            else:
                status = "offline"

            snapshot[venue] = {
                "price": float(price) if price > 0 else 0.0,
                "status": status,
                "last_tick_ts": int(last_tick_ts) if last_tick_ts > 0 else None,
                "age_seconds": age_seconds,
                "symbol": symbol_key,
            }
        return snapshot

    def _record_tick(
        self,
        venue: str,
        symbol: str,
        price: float,
        volume: float = 0.0,
        timestamp: float | None = None,
    ) -> None:
        try:
            price_value = float(price)
        except (TypeError, ValueError):
            return
        if price_value <= 0:
            return

        venue_key = str(venue or "").strip().upper()
        symbol_key = str(symbol or "").strip().upper() or self._chart_symbol
        ts = float(timestamp if timestamp is not None else time.time())
        volume_value = max(0.0, float(volume or 0.0))

        if venue_key == "LIGHTER":
            history = self._tick_history.get(venue_key, {}).get(symbol_key, deque())
            if history:
                last_ts, last_price, _ = history[-1]
                if (
                    last_price > 0
                    and abs(ts - float(last_ts)) <= self._lighter_tick_jump_window_seconds
                ):
                    ratio = max(
                        price_value / float(last_price),
                        float(last_price) / price_value,
                    )
                    if ratio > self._lighter_max_tick_jump_ratio:
                        self._log_lighter_issue(
                            "Filtered LIGHTER outlier tick "
                            f"(price={price_value}, previous={last_price}, ratio={ratio:.2f})."
                        )
                        return

        self.prices.setdefault(venue_key, {})[symbol_key] = price_value
        ticks = self._tick_history[venue_key][symbol_key]
        ticks.append((ts, price_value, volume_value))

        cutoff = ts - self._history_retention_seconds
        while ticks and ticks[0][0] < cutoff:
            ticks.popleft()
        while len(ticks) > self._history_max_points:
            ticks.popleft()

    @staticmethod
    def _parse_interval(interval: str) -> tuple[str, int]:
        known: dict[str, int] = {
            "1m": 60,
            "3m": 180,
            "5m": 300,
            "15m": 900,
            "30m": 1800,
            "1h": 3600,
            "4h": 14400,
            "1d": 86400,
        }
        raw = str(interval or "1m").strip().lower()
        if raw in known:
            return raw, known[raw]

        seconds = 60
        if raw.isdigit():
            seconds = max(1, int(raw))
        elif len(raw) >= 2 and raw[:-1].isdigit():
            qty = max(1, int(raw[:-1]))
            unit = raw[-1]
            if unit == "s":
                seconds = qty
            elif unit == "m":
                seconds = qty * 60
            elif unit == "h":
                seconds = qty * 3600
            elif unit == "d":
                seconds = qty * 86400
        return f"{seconds}s", seconds

    @staticmethod
    def _closest_aster_interval(seconds: int) -> str:
        supported: dict[str, int] = {
            "1m": 60,
            "3m": 180,
            "5m": 300,
            "15m": 900,
            "30m": 1800,
            "1h": 3600,
            "4h": 14400,
            "1d": 86400,
        }
        return min(supported.items(), key=lambda item: abs(item[1] - max(1, int(seconds))))[0]

    @staticmethod
    def _normalize_aster_symbol(symbol: str) -> str:
        value = str(symbol or "").strip().upper()
        if not value:
            return "SOLUSDT"
        if value.endswith(("USDT", "USD", "USDC")):
            return value
        return f"{value}USDT"

    @staticmethod
    def _aggregate_samples(
        samples: list[tuple[float, float, float]],
        interval_seconds: int,
        limit: int,
    ) -> list[dict[str, float]]:
        if interval_seconds <= 0 or limit <= 0:
            return []
        if not samples:
            return []

        buckets: dict[int, dict[str, float]] = {}
        for ts, price, volume in sorted(samples, key=lambda item: item[0]):
            if ts <= 0 or price <= 0:
                continue  # Skip degenerate data
            bucket = int(ts // interval_seconds) * interval_seconds
            if bucket not in buckets:
                buckets[bucket] = {
                    "time": float(bucket),
                    "open": price,
                    "high": price,
                    "low": price,
                    "close": price,
                    "volume": max(volume, 0.0) if volume > 0 else 1.0,
                }
                continue

            candle = buckets[bucket]
            candle["high"] = max(candle["high"], price)
            candle["low"] = min(candle["low"], price)
            candle["close"] = price
            candle["volume"] += max(volume, 0.0) if volume > 0 else 1.0

        candles: list[dict[str, float]] = []
        for key in sorted(buckets.keys())[-limit:]:
            candle = buckets[key]
            candles.append(
                {
                    "time": int(candle["time"]),
                    "open": float(candle["open"]),
                    "high": float(candle["high"]),
                    "low": float(candle["low"]),
                    "close": float(candle["close"]),
                    "volume": float(candle["volume"]),
                }
            )
        return candles

    def _ohlc_from_tick_buffer(
        self,
        venue: str,
        symbol: str,
        interval_seconds: int,
        limit: int,
    ) -> list[dict[str, float]]:
        venue_key = str(venue or "").strip().upper()
        symbol_key = str(symbol or "").strip().upper() or self._chart_symbol
        ticks = list(self._tick_history.get(venue_key, {}).get(symbol_key, []))
        if not ticks:
            return []
        cutoff = time.time() - float(interval_seconds * max(limit, 1) * 4)
        filtered = [sample for sample in ticks if sample[0] >= cutoff]
        return self._aggregate_samples(filtered, interval_seconds=interval_seconds, limit=limit)

    @staticmethod
    def _parse_timestamp(value: Any) -> float | None:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            ts = float(value)
            if ts > 1e12:
                ts = ts / 1000.0
            return ts
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return None
            if text.isdigit():
                ts = float(text)
                if ts > 1e12:
                    ts = ts / 1000.0
                return ts
            try:
                parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
                return parsed.astimezone(UTC).timestamp()
            except Exception:
                return None
        return None

    def _remember_lighter_hash(self, event_hash: str) -> bool:
        key = str(event_hash or "").strip()
        if not key:
            return True
        if key in self._lighter_seen_hash_set:
            return False
        self._lighter_seen_hash_set.add(key)
        self._lighter_seen_hashes.append(key)
        while len(self._lighter_seen_hashes) > self._lighter_seen_hash_max:
            old = self._lighter_seen_hashes.popleft()
            self._lighter_seen_hash_set.discard(old)
        return True

    def _extract_lighter_ticks_from_logs(
        self, payload: Any, *, market_id_override: str | None = None,
    ) -> list[tuple[float, float, float]]:
        entries: list[Any]
        if isinstance(payload, list):
            entries = payload
        elif isinstance(payload, dict):
            entries = [payload]
        else:
            return []

        # Use per-symbol market ID when provided, else fall back to global default
        raw_id = market_id_override if market_id_override is not None else self._lighter_market_id
        expected_market_index: int | None = None
        try:
            expected_market_index = int(str(raw_id).strip())
        except (TypeError, ValueError):
            expected_market_index = None

        ticks: list[tuple[float, float, float]] = []
        for item in entries:
            if not isinstance(item, dict):
                continue
            if not self._remember_lighter_hash(str(item.get("hash", ""))):
                continue

            pubdata = item.get("pubdata", {})
            trade_pubdata = pubdata.get("trade_pubdata", {}) if isinstance(pubdata, dict) else {}
            if not isinstance(trade_pubdata, dict):
                continue

            market_index = trade_pubdata.get("market_index")
            if expected_market_index is not None:
                try:
                    if int(market_index) != expected_market_index:
                        continue
                except (TypeError, ValueError):
                    continue

            price = self._coerce_price(trade_pubdata.get("price"))
            if price is None or price <= 0:
                continue

            volume = self._coerce_price(trade_pubdata.get("size")) or 0.0
            ts = (
                self._parse_timestamp(item.get("time"))
                or self._parse_timestamp(item.get("timestamp"))
                or self._parse_timestamp(item.get("ts"))
                or time.time()
            )
            ticks.append((float(ts), float(price), max(0.0, float(volume))))

        ticks.sort(key=lambda sample: sample[0])
        return ticks

    @staticmethod
    def _merge_candles(
        primary: list[dict[str, float]],
        secondary: list[dict[str, float]],
        limit: int,
    ) -> list[dict[str, float]]:
        merged: dict[int, dict[str, float]] = {}
        for candle in primary:
            key = int(candle.get("time", 0))
            if key <= 0:
                continue  # Skip degenerate timestamps
            merged[key] = candle
        for candle in secondary:
            key = int(candle.get("time", 0))
            if key <= 0:
                continue  # Skip degenerate timestamps
            # Only backfill — don't overwrite authoritative klines
            if key not in merged:
                merged[key] = candle
        return [merged[key] for key in sorted(merged.keys())[-limit:]]

    async def _fetch_aster_ohlc(
        self,
        symbol: str,
        interval_seconds: int,
        limit: int,
    ) -> list[dict[str, float]]:
        params = {
            "symbol": self._normalize_aster_symbol(symbol or self._aster_symbol),
            "interval": self._closest_aster_interval(interval_seconds),
            "limit": max(1, min(limit, 500)),
        }
        timeout = aiohttp.ClientTimeout(total=self._aster_http_timeout_seconds)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(self._aster_klines_url, params=params) as response:
                    if response.status != 200:
                        return []
                    payload = await response.json(content_type=None)
        except Exception:
            return []

        if not isinstance(payload, list):
            return []

        candles: list[dict[str, float]] = []
        for row in payload:
            if not isinstance(row, list) or len(row) < 6:
                continue
            try:
                open_time_s = int(float(row[0]) / 1000.0)
                open_price = float(row[1])
                high_price = float(row[2])
                low_price = float(row[3])
                close_price = float(row[4])
                volume = float(row[5])
            except (TypeError, ValueError):
                continue
            candles.append(
                {
                    "time": open_time_s,
                    "open": open_price,
                    "high": high_price,
                    "low": low_price,
                    "close": close_price,
                    "volume": volume,
                }
            )
            self._record_tick(
                "ASTER",
                self._chart_symbol,
                close_price,
                volume=volume,
                timestamp=float(open_time_s),
            )
        return candles[-limit:]

    async def _fetch_lighter_logs_ohlc(
        self,
        interval_seconds: int,
        limit: int,
    ) -> list[dict[str, float]]:
        timeout = aiohttp.ClientTimeout(total=self._lighter_http_timeout_seconds)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(self._lighter_logs_url) as response:
                    if response.status != 200:
                        return []
                    payload = await response.json(content_type=None)
        except Exception:
            return []

        ticks = self._extract_lighter_ticks_from_logs(payload)
        for ts, price, volume in ticks:
            self._record_tick("LIGHTER", self._chart_symbol, price, volume=volume, timestamp=ts)
        return self._aggregate_samples(ticks, interval_seconds=interval_seconds, limit=limit)

    async def fetch_ohlc(
        self,
        venue: str,
        symbol: str = "SOL",
        interval: str = "1m",
        limit: int = 120,
    ) -> dict[str, Any]:
        venue_key = str(venue or "").strip().upper()
        symbol_key = str(symbol or "").strip().upper() or self._chart_symbol
        interval_key, interval_seconds = self._parse_interval(interval)
        bar_limit = max(10, min(int(limit or 120), 500))
        tracking_symbol = symbol_key

        candles: list[dict[str, float]] = []
        source = "tick_buffer"

        if venue_key == "ASTER":
            tracking_symbol = self._normalize_aster_symbol(
                self._aster_symbol if symbol_key == self._chart_symbol else symbol_key
            )
            aster_candles = await self._fetch_aster_ohlc(
                symbol=tracking_symbol,
                interval_seconds=interval_seconds,
                limit=bar_limit,
            )
            if aster_candles:
                candles = aster_candles
                source = "aster_klines"
        elif venue_key == "LIGHTER":
            # Primary chart symbol: fetch from dedicated logs URL
            if symbol_key == self._chart_symbol:
                tracking_symbol = self._lighter_market_symbol
                lighter_candles = await self._fetch_lighter_logs_ohlc(
                    interval_seconds=interval_seconds,
                    limit=bar_limit,
                )
                if lighter_candles:
                    candles = lighter_candles
                    source = "lighter_logs"
            else:
                # Try fetching from per-symbol Lighter logs endpoint
                tracking_symbol = symbol_key
                try:
                    sym_url = f"{self._lighter_base_logs_url}/{symbol_key}/logs"
                    sym_market_id = self._get_lighter_market_id(symbol_key)
                    timeout = aiohttp.ClientTimeout(total=self._lighter_http_timeout_seconds)
                    async with aiohttp.ClientSession(timeout=timeout) as _session:
                        async with _session.get(sym_url) as _resp:
                            if _resp.status == 200:
                                _payload = await _resp.json(content_type=None)
                                _ticks = self._extract_lighter_ticks_from_logs(
                                    _payload, market_id_override=sym_market_id,
                                )
                                for _ts, _p, _v in _ticks:
                                    self._record_tick("LIGHTER", symbol_key, _p, volume=_v, timestamp=_ts)
                                if _ticks:
                                    candles = self._aggregate_samples(
                                        _ticks, interval_seconds=interval_seconds, limit=bar_limit,
                                    )
                                    source = "lighter_logs"
                except Exception:
                    pass  # Fall through to tick-buffer below

        tick_fallback = self._ohlc_from_tick_buffer(
            venue=venue_key,
            symbol=symbol_key,
            interval_seconds=interval_seconds,
            limit=bar_limit,
        )
        if candles and tick_fallback:
            candles = self._merge_candles(candles, tick_fallback, bar_limit)
        elif not candles:
            candles = tick_fallback

        return {
            "venue": venue_key,
            "symbol": symbol_key,
            "tracking_symbol": tracking_symbol,
            "interval": interval_key,
            "interval_seconds": interval_seconds,
            "limit": bar_limit,
            "source": source if candles else "unavailable",
            "candles": candles[-bar_limit:],
        }

    async def _aster_feed(self):
        """Aster market feed via public REST endpoints."""
        logger.info(f"🌊 Aster feed starting (symbol={self._aster_symbol})")
        timeout = aiohttp.ClientTimeout(total=self._aster_http_timeout_seconds)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            while self.running:
                try:
                    price = await self._fetch_aster_price(session)
                    if price is not None and price > 0:
                        self._record_tick("ASTER", self._chart_symbol, price)
                        self._clear_aster_issue()
                    else:
                        self._log_aster_issue("Aster poll returned no usable price.")
                except Exception as exc:
                    self._log_aster_issue(f"Aster poll error: {exc}")
                await asyncio.sleep(self._aster_poll_interval_seconds)

    async def _fetch_aster_price(self, session: aiohttp.ClientSession) -> float | None:
        endpoint_candidates = [
            self._aster_ticker_url,
            self._aster_mark_price_url,
            self._aster_book_ticker_url,
        ]
        tried: list[str] = []
        errors: list[str] = []

        for endpoint in endpoint_candidates:
            endpoint = str(endpoint or "").strip()
            if not endpoint or endpoint in tried:
                continue
            tried.append(endpoint)

            try:
                async with session.get(endpoint) as response:
                    if response.status != 200:
                        body = (await response.text())[:120]
                        errors.append(f"{endpoint} ({response.status}) {body}")
                        continue

                    payload = await response.json(content_type=None)
            except Exception as exc:
                errors.append(f"{endpoint} ({exc})")
                continue

            price = self._extract_price_from_object(payload)
            if price is not None and price > 0:
                return price

            midpoint = self._extract_book_ticker_midpoint(payload)
            if midpoint is not None and midpoint > 0:
                return midpoint

        if errors:
            self._log_aster_issue("Aster poll failed: " + " | ".join(errors[:3]))
        return None

    async def _lighter_feed(self):
        ws_task: asyncio.Task[Any] | None = None
        logger.info(
            f"💧 Lighter feed starting (symbol={self._lighter_market_symbol}, logs={self._lighter_logs_url})"
        )

        if self._lighter_ws_enabled and self._lighter_ws_urls:
            logger.info(f"💧 Lighter WS enabled (urls={self._lighter_ws_urls})")
            ws_task = asyncio.create_task(self._lighter_ws_feed())
        else:
            logger.info("💧 Lighter WS disabled; using REST log polling.")

        try:
            await self._lighter_rest_feed()
        finally:
            if ws_task:
                ws_task.cancel()
                with suppress(asyncio.CancelledError):
                    await ws_task

    async def _lighter_ws_feed(self):
        max_retries = int(os.getenv("LIGHTER_WS_MAX_RETRIES", "50"))
        base_delay = self._lighter_ws_retry_seconds
        max_delay = 60.0
        attempt = 0

        while self.running:
            for url in self._lighter_ws_urls:
                if not self.running:
                    return
                try:
                    async with websockets.connect(
                        url,
                        open_timeout=10,
                        ping_interval=20,
                        ping_timeout=20,
                        close_timeout=5,
                    ) as ws:
                        attempt = 0  # Reset on successful connection
                        self._clear_lighter_issue()
                        logger.info(f"💧 Lighter WS connected: {url}")
                        await self._send_lighter_subscriptions(ws)

                        while self.running:
                            message = await ws.recv()
                            price = self._extract_lighter_price_from_ws_message(message)
                            if price is not None and price > 0:
                                self._record_tick("LIGHTER", self._chart_symbol, price)
                                self._clear_lighter_issue()
                except Exception as exc:
                    self._log_lighter_issue(f"Lighter WS issue ({url}): {exc}")

            attempt += 1
            if attempt >= max_retries:
                logger.warning(
                    f"⚠️ Lighter WS: {max_retries} reconnect attempts exhausted. "
                    "Falling back to REST-only mode."
                )
                return  # Exit WS feed; REST feed continues independently

            delay = min(base_delay * (2 ** min(attempt, 6)), max_delay)
            logger.debug(f"💧 Lighter WS retry {attempt}/{max_retries} in {delay:.1f}s")
            await asyncio.sleep(delay)

    async def _send_lighter_subscriptions(self, ws: websockets.WebSocketClientProtocol) -> None:
        # Try multiple payload variants for protocol compatibility.
        # Subscribe to all configured market IDs (not just the primary chart symbol)
        market_id = self._get_lighter_market_id(self._chart_symbol)
        payloads = [
            {"type": "subscribe", "channel": f"order_book:{market_id}"},
            {"type": "subscribe", "channel": "order_book", "marketId": market_id},
            {"type": "subscribe", "channel": "order_book", "market": self._lighter_market_symbol},
            {"type": "subscribe", "channel": f"trade:{market_id}"},
            {"type": "subscribe", "channel": "trade", "marketId": market_id},
        ]
        # Also subscribe to other configured symbols
        for _sym, mid in self._lighter_market_ids.items():
            if mid != market_id:
                payloads.append({"type": "subscribe", "channel": f"trade:{mid}"})
                payloads.append({"type": "subscribe", "channel": f"order_book:{mid}"})
        for payload in payloads:
            try:
                await ws.send(json.dumps(payload))
            except Exception:
                continue

    async def _lighter_rest_feed(self):
        timeout = aiohttp.ClientTimeout(total=self._lighter_http_timeout_seconds)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            while self.running:
                try:
                    async with session.get(self._lighter_logs_url) as response:
                        if response.status != 200:
                            body = (await response.text())[:200]
                            self._log_lighter_issue(
                                f"Lighter REST poll failed ({response.status}) {body}"
                            )
                        else:
                            payload = await response.json(content_type=None)
                            ticks = self._extract_lighter_ticks_from_logs(payload)
                            if ticks:
                                for ts, price, volume in ticks:
                                    self._record_tick(
                                        "LIGHTER",
                                        self._chart_symbol,
                                        price,
                                        volume=volume,
                                        timestamp=ts,
                                    )
                                self._clear_lighter_issue()
                            else:
                                price = self._extract_lighter_price_from_logs(payload)
                                if price is not None and price > 0:
                                    self._record_tick("LIGHTER", self._chart_symbol, price)
                                    self._clear_lighter_issue()
                                else:
                                    # Only warn if Lighter has no price at all (not just dedup-filtered)
                                    current = self.prices.get("LIGHTER", {}).get(self._chart_symbol, 0)
                                    if current <= 0:
                                        self._log_lighter_issue("Lighter REST poll returned no usable price.")
                except Exception as exc:
                    self._log_lighter_issue(f"Lighter REST poll error: {exc}")

                await asyncio.sleep(self._lighter_poll_interval_seconds)

    def _extract_lighter_price_from_logs(self, payload: Any) -> float | None:
        ticks = self._extract_lighter_ticks_from_logs(payload)
        if ticks:
            return float(ticks[-1][1])
        return None

    def _extract_lighter_price_from_ws_message(self, message: Any) -> float | None:
        if isinstance(message, bytes):
            try:
                message = message.decode("utf-8")
            except Exception:
                return None

        if isinstance(message, str):
            try:
                payload = json.loads(message)
            except Exception:
                return None
        else:
            payload = message

        return self._extract_price_from_object(payload)

    def _extract_price_from_object(self, payload: Any) -> float | None:
        if isinstance(payload, dict):
            for key in (
                "price",
                "last_price",
                "lastPrice",
                "mid",
                "mid_price",
                "mark_price",
                "markPrice",
                "indexPrice",
            ):
                value = payload.get(key)
                price = self._coerce_price(value)
                if price is not None and price > 0:
                    return price

            bids = payload.get("bids")
            asks = payload.get("asks")
            if isinstance(bids, list) and isinstance(asks, list):
                bid = self._extract_best_side_price(bids)
                ask = self._extract_best_side_price(asks)
                if bid is not None and ask is not None and bid > 0 and ask > 0:
                    return (bid + ask) / 2.0

            for value in payload.values():
                price = self._extract_price_from_object(value)
                if price is not None and price > 0:
                    return price

            return None

        if isinstance(payload, list):
            for item in payload:
                price = self._extract_price_from_object(item)
                if price is not None and price > 0:
                    return price
            return None

        return self._coerce_price(payload)

    def _extract_book_ticker_midpoint(self, payload: Any) -> float | None:
        if not isinstance(payload, dict):
            return None

        bid = self._coerce_price(payload.get("bidPrice"))
        ask = self._coerce_price(payload.get("askPrice"))
        if bid is not None and ask is not None and bid > 0 and ask > 0:
            return (bid + ask) / 2.0
        return None

    def _extract_best_side_price(self, entries: list[Any]) -> float | None:
        if not entries:
            return None

        first = entries[0]
        if isinstance(first, dict):
            return self._coerce_price(first.get("price"))
        if isinstance(first, list) and first:
            return self._coerce_price(first[0])
        return None

    @staticmethod
    def _coerce_price(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    # ------------------------------------------------------------------
    # Multi-symbol feeds
    # ------------------------------------------------------------------

    async def _aster_multi_symbol_feed(self):
        """Fetch all preferred symbols from Aster batch ticker endpoint."""
        # Build a set of USDT-quoted symbols we care about
        wanted = {self._normalize_aster_symbol(sym) for sym in self._extra_symbols}
        logger.info(f"🌊 Aster multi-symbol feed starting ({len(wanted)} symbols)")
        timeout = aiohttp.ClientTimeout(total=self._aster_http_timeout_seconds)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            while self.running:
                try:
                    async with session.get(self._aster_batch_ticker_url) as response:
                        if response.status == 200:
                            payload = await response.json(content_type=None)
                            if isinstance(payload, list):
                                for item in payload:
                                    sym = str(item.get("symbol", "")).strip().upper()
                                    if sym in wanted:
                                        price = self._coerce_price(item.get("price"))
                                        if price is not None and price > 0:
                                            # Store under base symbol (strip USDT)
                                            base = sym.replace("USDT", "").replace("USDC", "").replace("USD", "")
                                            self._record_tick("ASTER", base, price)
                except Exception as exc:
                    logger.debug(f"Aster multi-symbol poll error: {exc}")
                await asyncio.sleep(self._multi_symbol_poll_interval)

    async def _lighter_multi_symbol_feed(self):
        """Fetch preferred symbols from Lighter individual market endpoints."""
        # Skip the primary chart symbol (already covered by main feed)
        extra = [sym for sym in self._extra_symbols if sym != self._chart_symbol]
        logger.info(f"💧 Lighter multi-symbol feed starting ({len(extra)} extra symbols)")
        timeout = aiohttp.ClientTimeout(total=self._lighter_http_timeout_seconds)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            while self.running:
                for sym in extra:
                    if not self.running:
                        break
                    try:
                        url = f"{self._lighter_base_logs_url}/{sym}/logs"
                        sym_market_id = self._get_lighter_market_id(sym)
                        async with session.get(url) as response:
                            if response.status == 200:
                                payload = await response.json(content_type=None)
                                ticks = self._extract_lighter_ticks_from_logs(
                                    payload, market_id_override=sym_market_id,
                                )
                                if ticks:
                                    for ts, price, volume in ticks:
                                        self._record_tick(
                                            "LIGHTER", sym, price, volume=volume, timestamp=ts
                                        )
                    except Exception:
                        pass  # Individual symbol failures are non-critical
                    # Stagger requests to avoid hammering the API
                    await asyncio.sleep(1.0)
                # Wait before next full cycle
                remaining_wait = max(0.0, self._multi_symbol_poll_interval - len(extra))
                if remaining_wait > 0:
                    await asyncio.sleep(remaining_wait)

    def get_multi_symbol_snapshot(self) -> dict[str, dict[str, dict[str, Any]]]:
        """Get current prices for all tracked symbols across all venues."""
        now = time.time()
        result: dict[str, dict[str, dict[str, Any]]] = {}
        for venue in ("ASTER", "LIGHTER"):
            venue_data: dict[str, dict[str, Any]] = {}
            venue_prices = self.prices.get(venue, {})
            for symbol, price in venue_prices.items():
                ticks = self._tick_history.get(venue, {}).get(symbol, deque())
                last_ts = float(ticks[-1][0]) if ticks else 0.0
                age = int(max(0.0, now - last_ts)) if last_ts > 0 else None
                venue_data[symbol] = {
                    "price": float(price) if price > 0 else 0.0,
                    "status": "healthy" if price > 0 and age is not None and age <= 120 else (
                        "degraded" if price > 0 else "offline"
                    ),
                    "age_seconds": age,
                }
            result[venue] = venue_data
        return result

    def _log_lighter_issue(self, message: str) -> None:
        now = time.time()
        if message != self._lighter_last_issue or (now - self._lighter_last_issue_ts) >= 60:
            logger.warning(message)
            self._lighter_last_issue = message
            self._lighter_last_issue_ts = now

    def _clear_lighter_issue(self) -> None:
        self._lighter_last_issue = ""
        self._lighter_last_issue_ts = 0.0

    def _log_aster_issue(self, message: str) -> None:
        now = time.time()
        if message != self._aster_last_issue or (now - self._aster_last_issue_ts) >= 60:
            logger.warning(message)
            self._aster_last_issue = message
            self._aster_last_issue_ts = now

    def _clear_aster_issue(self) -> None:
        self._aster_last_issue = ""
        self._aster_last_issue_ts = 0.0
