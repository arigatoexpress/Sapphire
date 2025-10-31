"""Minimal asynchronous client for interacting with the Aster DEX API."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import time
from typing import Any, Dict, List, Optional

import aiohttp

from .config import Settings


class AsterClient:
    """Tiny REST client tailored to the needs of the live trading service."""

    def __init__(self, settings: Settings, api_key: str, api_secret: str) -> None:
        self._settings = settings
        self._api_key = api_key
        self._api_secret = api_secret
        self._session: Optional[aiohttp.ClientSession] = None
        self._lock = asyncio.Lock()

    async def __aenter__(self) -> "AsterClient":
        await self.ensure_session()
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.close()

    async def ensure_session(self) -> None:
        if self._session is None:
            timeout = aiohttp.ClientTimeout(total=15)
            self._session = aiohttp.ClientSession(timeout=timeout)

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    async def ping(self) -> bool:
        response = await self._get("/fapi/v1/ping", signed=False)
        return response is not None

    async def server_time(self) -> int:
        payload = await self._get("/fapi/v1/time", signed=False)
        return int(payload.get("serverTime", 0))

    async def ticker(self, symbol: str) -> Dict[str, Any]:
        return await self._get("/fapi/v1/ticker/24hr", params={"symbol": symbol}, signed=False) or {}

    async def account_balance(self) -> List[Dict[str, Any]]:
        payload = await self._get("/fapi/v2/balance", signed=True)
        if isinstance(payload, list):
            return payload
        return []

    async def place_order(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return await self._post("/fapi/v1/order", data=payload, signed=True) or {}

    async def cancel_all_orders(self, symbol: str) -> Dict[str, Any]:
        return await self._delete("/fapi/v1/allOpenOrders", params={"symbol": symbol}, signed=True) or {}

    async def position_risk(self) -> List[Dict[str, Any]]:
        payload = await self._get("/fapi/v2/positionRisk", signed=True)
        if isinstance(payload, list):
            return payload
        return []

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    async def _get(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        *,
        signed: bool,
    ) -> Optional[Dict[str, Any]]:
        return await self._request("GET", path, params=params, signed=signed)

    async def _post(
        self,
        path: str,
        data: Optional[Dict[str, Any]] = None,
        *,
        signed: bool,
    ) -> Optional[Dict[str, Any]]:
        return await self._request("POST", path, data=data, signed=signed)

    async def _delete(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        *,
        signed: bool,
    ) -> Optional[Dict[str, Any]]:
        return await self._request("DELETE", path, params=params, signed=signed)

    async def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        *,
        signed: bool,
    ) -> Optional[Dict[str, Any]]:
        await self.ensure_session()
        assert self._session is not None

        url = f"{self._settings.rest_base_url}{path}"
        headers: Dict[str, str] = {"Content-Type": "application/json"}

        if signed:
            payload = params.copy() if params else {}
            if data:
                payload.update({k: v for k, v in data.items() if v is not None})
            signed_params = self._sign_payload(method, path, payload)
            params = signed_params if params is None else signed_params
            headers["X-MBX-APIKEY"] = self._api_key
        else:
            params = params or {}

        async with self._lock:
            async with self._session.request(method, url, params=params, json=data, headers=headers) as resp:
                if resp.status == 200:
                    try:
                        return await resp.json()
                    except Exception:
                        return None
                text = await resp.text()
                raise RuntimeError(f"Aster API error {resp.status}: {text[:200]}")

    def _sign_payload(self, method: str, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        payload = payload.copy()
        payload.setdefault("timestamp", int(time.time() * 1000))
        payload.setdefault("recvWindow", 5000)

        query = "&".join(f"{key}={payload[key]}" for key in sorted(payload))
        message = f"{method}{path}{query}".encode()
        signature = hmac.new(self._api_secret.encode(), message, hashlib.sha256).hexdigest()
        payload["signature"] = signature
        return payload
