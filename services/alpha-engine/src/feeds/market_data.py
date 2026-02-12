import asyncio
import json
import os
import time
from contextlib import suppress
from typing import Any, Dict, List, Optional

import aiohttp
import websockets
from loguru import logger


class MarketDataAggregator:
    def __init__(self):
        self.prices: Dict[str, Dict[str, float]] = {
            "ASTER": {"SOL": 0.0},
            "LIGHTER": {"SOL": 0.0},
        }
        self.running = False

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
        return self.prices.get(venue, {}).get(symbol, 0.0)

    async def _aster_feed(self):
        """Simulated Aster WS Feed (replace with actual Aster WS protocol)."""
        logger.info("🌊 Connecting to Aster Feed...")
        while self.running:
            try:
                # Placeholder until full Aster protocol implementation.
                self.prices["ASTER"]["SOL"] = 150.0
                await asyncio.sleep(0.1)
            except Exception as exc:
                logger.error(f"Aster WS Error: {exc}")
                await asyncio.sleep(1)

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
                                self.prices["LIGHTER"]["SOL"] = price
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
                            price = self._extract_lighter_price_from_logs(payload)
                            if price is not None and price > 0:
                                self.prices["LIGHTER"]["SOL"] = price
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
            for key in ("price", "last_price", "lastPrice", "mid", "mid_price", "mark_price"):
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
