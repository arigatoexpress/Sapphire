import asyncio
import json
import os
import time
from collections import defaultdict, deque
from contextlib import suppress
from datetime import datetime, timezone
from typing import Any, Deque, Dict, List, Optional, Tuple

import aiohttp
import websockets
from loguru import logger


class MarketDataAggregator:
    def __init__(self):
        self._chart_symbol = str(os.getenv("MARKET_CHART_SYMBOL", "SOL")).strip().upper() or "SOL"
        self.prices: Dict[str, Dict[str, float]] = {
            "ASTER": {self._chart_symbol: 0.0},
            "LIGHTER": {self._chart_symbol: 0.0},
        }
        self._tick_history: Dict[str, Dict[str, Deque[Tuple[float, float, float]]]] = defaultdict(
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
        self._lighter_seen_hashes: Deque[str] = deque()
        self._lighter_seen_hash_set: set[str] = set()
        self._lighter_seen_hash_max = max(1000, int(os.getenv("LIGHTER_SEEN_HASH_MAX", "4000")))

        self._lighter_last_issue = ""
        self._lighter_last_issue_ts = 0.0

    @staticmethod
    def _env_float(name: str, default: float, minimum: float = 0.0) -> float:
        raw = os.getenv(name, str(default))
        try:
            value = float(raw)
        except (TypeError, ValueError):
            value = default
        return max(minimum, value)

    def _parse_ws_urls(self) -> List[str]:
        raw = str(os.getenv("LIGHTER_WS_URLS", "")).strip()
        if raw:
            tokens = [item.strip() for item in raw.replace(";", ",").split(",")]
            return [token for token in tokens if token]

        fallback = [
            str(os.getenv("LIGHTER_WS_URL", "")).strip(),
            "wss://mainnet.zklighter.elliot.ai/stream",
            "wss://testnet.zklighter.elliot.ai/stream",
        ]
        deduped: List[str] = []
        for url in fallback:
            if url and url not in deduped:
                deduped.append(url)
        return deduped

    async def start(self):
        self.running = True
        # Start market data connections in background.
        asyncio.create_task(self._aster_feed())
        asyncio.create_task(self._lighter_feed())

    async def stop(self):
        self.running = False

    def get_price(self, venue: str, symbol: str) -> float:
        venue_prices = self.prices.get(venue, {})
        return venue_prices.get(symbol, venue_prices.get(self._chart_symbol, 0.0))

    def get_market_snapshot(self, symbol: str = "SOL") -> Dict[str, Dict[str, Any]]:
        symbol_key = str(symbol or "").strip().upper() or self._chart_symbol
        now = time.time()
        snapshot: Dict[str, Dict[str, Any]] = {}

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
        timestamp: Optional[float] = None,
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

        self.prices.setdefault(venue_key, {})[symbol_key] = price_value
        ticks = self._tick_history[venue_key][symbol_key]
        ticks.append((ts, price_value, volume_value))

        cutoff = ts - self._history_retention_seconds
        while ticks and ticks[0][0] < cutoff:
            ticks.popleft()
        while len(ticks) > self._history_max_points:
            ticks.popleft()

    @staticmethod
    def _parse_interval(interval: str) -> Tuple[str, int]:
        known: Dict[str, int] = {
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
        supported: Dict[str, int] = {
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
        samples: List[Tuple[float, float, float]],
        interval_seconds: int,
        limit: int,
    ) -> List[Dict[str, float]]:
        if interval_seconds <= 0 or limit <= 0:
            return []
        if not samples:
            return []

        buckets: Dict[int, Dict[str, float]] = {}
        for ts, price, volume in sorted(samples, key=lambda item: item[0]):
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

        candles: List[Dict[str, float]] = []
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
    ) -> List[Dict[str, float]]:
        venue_key = str(venue or "").strip().upper()
        symbol_key = str(symbol or "").strip().upper() or self._chart_symbol
        ticks = list(self._tick_history.get(venue_key, {}).get(symbol_key, []))
        if not ticks:
            return []
        cutoff = time.time() - float(interval_seconds * max(limit, 1) * 4)
        filtered = [sample for sample in ticks if sample[0] >= cutoff]
        return self._aggregate_samples(filtered, interval_seconds=interval_seconds, limit=limit)

    @staticmethod
    def _parse_timestamp(value: Any) -> Optional[float]:
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
                return parsed.astimezone(timezone.utc).timestamp()
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

    def _extract_lighter_ticks_from_logs(self, payload: Any) -> List[Tuple[float, float, float]]:
        entries: List[Any]
        if isinstance(payload, list):
            entries = payload
        elif isinstance(payload, dict):
            entries = [payload]
        else:
            return []

        ticks: List[Tuple[float, float, float]] = []
        for item in entries:
            if not isinstance(item, dict):
                continue
            if not self._remember_lighter_hash(str(item.get("hash", ""))):
                continue

            pubdata = item.get("pubdata", {})
            trade_pubdata = pubdata.get("trade_pubdata", {}) if isinstance(pubdata, dict) else {}
            price = self._coerce_price(trade_pubdata.get("price")) or self._extract_price_from_object(item)
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
        primary: List[Dict[str, float]],
        secondary: List[Dict[str, float]],
        limit: int,
    ) -> List[Dict[str, float]]:
        merged: Dict[int, Dict[str, float]] = {}
        for candle in primary:
            merged[int(candle["time"])] = candle
        for candle in secondary:
            merged[int(candle["time"])] = candle
        return [merged[key] for key in sorted(merged.keys())[-limit:]]

    async def _fetch_aster_ohlc(
        self,
        symbol: str,
        interval_seconds: int,
        limit: int,
    ) -> List[Dict[str, float]]:
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

        candles: List[Dict[str, float]] = []
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
    ) -> List[Dict[str, float]]:
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
    ) -> Dict[str, Any]:
        venue_key = str(venue or "").strip().upper()
        symbol_key = str(symbol or "").strip().upper() or self._chart_symbol
        interval_key, interval_seconds = self._parse_interval(interval)
        bar_limit = max(10, min(int(limit or 120), 500))

        candles: List[Dict[str, float]] = []
        source = "tick_buffer"

        if venue_key == "ASTER":
            aster_candles = await self._fetch_aster_ohlc(
                symbol=self._aster_symbol if symbol_key == self._chart_symbol else symbol_key,
                interval_seconds=interval_seconds,
                limit=bar_limit,
            )
            if aster_candles:
                candles = aster_candles
                source = "aster_klines"
        elif venue_key == "LIGHTER":
            lighter_candles = await self._fetch_lighter_logs_ohlc(
                interval_seconds=interval_seconds,
                limit=bar_limit,
            )
            if lighter_candles:
                candles = lighter_candles
                source = "lighter_logs"

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

    async def _fetch_aster_price(self, session: aiohttp.ClientSession) -> Optional[float]:
        endpoint_candidates = [
            self._aster_ticker_url,
            self._aster_mark_price_url,
            self._aster_book_ticker_url,
        ]
        tried: List[str] = []
        errors: List[str] = []

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
        ws_task: Optional[asyncio.Task[Any]] = None
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

            await asyncio.sleep(self._lighter_ws_retry_seconds)

    async def _send_lighter_subscriptions(self, ws: websockets.WebSocketClientProtocol) -> None:
        # Try multiple payload variants for protocol compatibility.
        payloads = [
            {"type": "subscribe", "channel": f"order_book:{self._lighter_market_id}"},
            {"type": "subscribe", "channel": "order_book", "marketId": self._lighter_market_id},
            {"type": "subscribe", "channel": "order_book", "market": self._lighter_market_symbol},
            {"type": "subscribe", "channel": f"trade:{self._lighter_market_id}"},
            {"type": "subscribe", "channel": "trade", "marketId": self._lighter_market_id},
        ]
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
                                    self._log_lighter_issue("Lighter REST poll returned no usable price.")
                except Exception as exc:
                    self._log_lighter_issue(f"Lighter REST poll error: {exc}")

                await asyncio.sleep(self._lighter_poll_interval_seconds)

    def _extract_lighter_price_from_logs(self, payload: Any) -> Optional[float]:
        if isinstance(payload, list):
            for item in payload:
                price = self._extract_price_from_object(item)
                if price is not None and price > 0:
                    return price
            return None

        return self._extract_price_from_object(payload)

    def _extract_lighter_price_from_ws_message(self, message: Any) -> Optional[float]:
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

    def _extract_price_from_object(self, payload: Any) -> Optional[float]:
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

    def _extract_book_ticker_midpoint(self, payload: Any) -> Optional[float]:
        if not isinstance(payload, dict):
            return None

        bid = self._coerce_price(payload.get("bidPrice"))
        ask = self._coerce_price(payload.get("askPrice"))
        if bid is not None and ask is not None and bid > 0 and ask > 0:
            return (bid + ask) / 2.0
        return None

    def _extract_best_side_price(self, entries: List[Any]) -> Optional[float]:
        if not entries:
            return None

        first = entries[0]
        if isinstance(first, dict):
            return self._coerce_price(first.get("price"))
        if isinstance(first, list) and first:
            return self._coerce_price(first[0])
        return None

    @staticmethod
    def _coerce_price(value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

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
