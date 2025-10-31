from __future__ import annotations

import hashlib
import hmac
from typing import Any, Dict, Optional

import httpx

from .config import settings


BASE_URL = "https://fapi.asterdex.com"


class AsterClient:
    def __init__(self) -> None:
        self._client = httpx.AsyncClient(base_url=BASE_URL, timeout=10.0)
        self._api_key = settings.ASTER_API_KEY
        self._api_secret = settings.ASTER_API_SECRET.encode()

    async def close(self) -> None:
        await self._client.aclose()

    async def _server_time(self) -> int:
        resp = await self._client.get("/fapi/v1/time")
        resp.raise_for_status()
        return int(resp.json()["serverTime"])

    def _sign(self, params: Dict[str, Any]) -> str:
        query = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        return hmac.new(self._api_secret, query.encode(), hashlib.sha256).hexdigest()

    async def _auth_params(self, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        auth_params: Dict[str, Any] = params.copy() if params else {}
        auth_params.setdefault("timestamp", await self._server_time())
        auth_params["signature"] = self._sign(auth_params)
        return auth_params

    async def get_account(self) -> Dict[str, Any]:
        params = await self._auth_params()
        headers = {"X-MBX-APIKEY": self._api_key}
        resp = await self._client.get("/fapi/v2/account", params=params, headers=headers)
        resp.raise_for_status()
        return resp.json()

    async def place_order(self, order: Dict[str, Any]) -> Dict[str, Any]:
        params = await self._auth_params(order)
        headers = {"X-MBX-APIKEY": self._api_key}
        resp = await self._client.post("/fapi/v1/order", params=params, headers=headers)
        resp.raise_for_status()
        return resp.json()

    async def cancel_all(self, symbol: Optional[str] = None) -> None:
        params: Dict[str, Any] = {}
        if symbol:
            params["symbol"] = symbol
        params = await self._auth_params(params)
        headers = {"X-MBX-APIKEY": self._api_key}
        resp = await self._client.delete("/fapi/v1/allOpenOrders", params=params, headers=headers)
        resp.raise_for_status()

