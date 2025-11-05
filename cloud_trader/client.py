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
    def __init__(self, settings: Settings, api_key: str, api_secret: str) -> None:
        self._settings = settings
        self._api_key = api_key
        self._api_secret = api_secret
        self._client = httpx.AsyncClient(base_url=self._settings.aster_api_base_url, timeout=10)

    async def ensure_session(self) -> None:
        # Placeholder if session management is needed in the future
        pass

    async def close(self) -> None:
        await self._client.aclose()

    def _sign(self, params: Dict[str, Any]) -> str:
        query_string = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        return hmac.new(self._api_secret.encode("utf-8"), query_string.encode("utf-8"), hashlib.sha256).hexdigest()

    async def _request(self, method: str, path: str, params: Optional[Dict[str, Any]] = None, signed: bool = False) -> Any:
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
