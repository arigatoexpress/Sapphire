"""Aster exchange client."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import time
from typing import Any, Dict, List, Optional

import httpx

from .config import Settings
from .credentials import Credentials


class AsterClient:
    def __init__(
        self,
        credentials: Optional[Credentials] = None,
        base_url: Optional[str] = None,
        settings: Optional[Settings] = None,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
    ) -> None:
        """Initialize AsterClient with flexible constructor to handle legacy calls."""
        # Handle new style (credentials object)
        if credentials:
            self._settings = settings or Settings()
            self._api_key = credentials.api_key
            self._api_secret = credentials.api_secret
            self._base_url = base_url or self._settings.aster_api_base_url
        # Handle old style (individual params)
        elif settings and api_key and api_secret:
            self._settings = settings
            self._api_key = api_key
            self._api_secret = api_secret
            self._base_url = self._settings.aster_api_base_url
        else:
            raise ValueError("Must provide either credentials or (settings, api_key, api_secret)")

        # Initialize with connection pooling
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(10.0, connect=5.0),
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=100),
        )

    async def ensure_session(self) -> None:
        # Placeholder if session management is needed in the future
        pass

    async def close(self) -> None:
        await self._client.aclose()

    def _sign(self, params: Dict[str, Any]) -> str:
        query_string = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        return hmac.new(
            self._api_secret.encode("utf-8"), query_string.encode("utf-8"), hashlib.sha256
        ).hexdigest()

    async def _request(
        self, method: str, path: str, params: Optional[Dict[str, Any]] = None, signed: bool = False
    ) -> Any:
        params = params or {}
        headers = {"X-MBX-APIKEY": self._api_key}
        if signed:
            params["timestamp"] = int(time.time() * 1000)
            params["signature"] = self._sign(params)

        try:
            resp = await self._client.request(method, path, params=params, headers=headers)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            # Add more context to error messages
            print(f"HTTP Error: {e.response.status_code} - {e.response.text}")
            raise

    async def ticker(self, symbol: str) -> Dict[str, Any]:
        return await self._request("GET", "/api/v3/ticker/24hr", {"symbol": symbol})

    async def place_order(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return await self._request("POST", "/api/v3/order", payload, signed=True)

    async def position_risk(self) -> List[Dict[str, Any]]:
        return await self._request("GET", "/fapi/v2/positionRisk", signed=True)

    async def close_position(self, symbol: str, reduce_only: bool = True) -> Dict[str, Any]:
        """Close position for a symbol using market order."""
        # Get current position to determine side
        positions = await self.position_risk()
        position = next((p for p in positions if p.get("symbol") == symbol), None)

        if not position:
            raise ValueError(f"No position found for {symbol}")

        position_amt = float(position.get("positionAmt", 0))
        if position_amt == 0:
            return {"status": "NO_POSITION"}

        # Determine closing side (opposite of position)
        side = "SELL" if position_amt > 0 else "BUY"
        quantity = abs(position_amt)

        payload = {
            "symbol": symbol,
            "side": side,
            "type": "MARKET",
            "quantity": quantity,
            "reduceOnly": "true" if reduce_only else "false",
        }

        return await self.place_order(payload)

    async def get_all_symbols(self) -> List[Dict[str, Any]]:
        """Get all trading symbols from exchange info."""
        exchange_info = await self._request("GET", "/fapi/v1/exchangeInfo")
        return exchange_info.get("symbols", [])

    async def get_exchange_info(self) -> Dict[str, Any]:
        """Get full exchange information."""
        return await self._request("GET", "/fapi/v1/exchangeInfo")

    async def get_historical_klines(
        self, symbol: str, interval: str = "1h", limit: int = 100
    ) -> List[List[Any]]:
        """Get historical kline/candlestick data."""
        params = {"symbol": symbol, "interval": interval, "limit": limit}
        return await self._request("GET", "/fapi/v1/klines", params)
