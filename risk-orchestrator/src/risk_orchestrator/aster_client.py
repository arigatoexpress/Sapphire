from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import time
from typing import Any, Dict, Optional

import httpx

from .config import settings

logger = logging.getLogger(__name__)


BASE_URL = "https://fapi.asterdex.com"


class AsterClient:


    def __init__(self) -> None:
        self._client = httpx.AsyncClient(base_url=BASE_URL, timeout=10.0)
        self._api_key = settings.ASTER_API_KEY

        # Try to decode secret if it's base64 encoded
        raw_secret = settings.ASTER_API_SECRET
        try:
            import base64
            # Try base64 decode
            decoded = base64.b64decode(raw_secret).decode('utf-8')
            # If successful and looks reasonable, use decoded version
            if len(decoded) < len(raw_secret) and all(ord(c) < 128 for c in decoded):
                logger.info(f"Using base64 decoded secret (length: {len(decoded)})")
                self._api_secret = decoded.encode()
            else:
                # Doesn't look like valid base64, use raw
                logger.info(f"Using raw secret (length: {len(raw_secret)})")
                self._api_secret = raw_secret.encode()
        except Exception:
            # Not base64, use as-is
            logger.info(f"Using raw secret (not base64, length: {len(raw_secret)})")
            self._api_secret = raw_secret.encode()

        self._max_retries = 3
        self._retry_delay = 1.0

    async def close(self) -> None:
        await self._client.aclose()

    async def _server_time(self) -> int:
        resp = await self._client.get("/fapi/v1/time")
        resp.raise_for_status()
        return int(resp.json()["serverTime"])

    async def _request_with_retry(self, method: str, url: str, **kwargs) -> httpx.Response:
        """Execute request with exponential backoff retry logic."""
        last_error = None

        for attempt in range(self._max_retries):
            try:
                if method == "GET":
                    resp = await self._client.get(url, **kwargs)
                elif method == "POST":
                    resp = await self._client.post(url, **kwargs)
                elif method == "DELETE":
                    resp = await self._client.delete(url, **kwargs)
                else:
                    raise ValueError(f"Unsupported method: {method}")

                # Log request details
                logger.info(f"Aster API Request: {method} {url} - Status: {resp.status_code}")

                # Log detailed error info for non-2xx responses
                if resp.status_code >= 400:
                    logger.error(
                        f"Aster API Error: {method} {url}\n"
                        f"Status: {resp.status_code}\n"
                        f"Headers: {dict(resp.headers)}\n"
                        f"Body: {resp.text}\n"
                        f"Request Headers: {kwargs.get('headers', {})}\n"
                        f"Request Params: {kwargs.get('params', {})}"
                    )

                    # Retry on rate limit errors
                    if resp.status_code == 429:
                        retry_after = float(resp.headers.get('Retry-After', self._retry_delay * (2 ** attempt)))
                        logger.warning(f"Rate limited. Retrying after {retry_after}s (attempt {attempt + 1}/{self._max_retries})")
                        await asyncio.sleep(retry_after)
                        continue

                return resp

            except Exception as e:
                last_error = e
                logger.error(f"Aster API Exception: {method} {url} - {type(e).__name__}: {str(e)}")

                if attempt < self._max_retries - 1:
                    delay = self._retry_delay * (2 ** attempt)
                    logger.info(f"Retrying after {delay}s (attempt {attempt + 1}/{self._max_retries})")
                    await asyncio.sleep(delay)

        raise last_error or Exception(f"Failed after {self._max_retries} attempts")


    def _sign(self, method: str, path: str, params: Dict[str, Any]) -> str:
        # Aster API expects signature of query string only
        query = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        return hmac.new(self._api_secret, query.encode(), hashlib.sha256).hexdigest()

    async def _auth_params(self, method: str, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        auth_params: Dict[str, Any] = params.copy() if params else {}
        auth_params.setdefault("timestamp", await self._server_time())
        auth_params["signature"] = self._sign(method, path, auth_params)
        return auth_params

    async def get_account(self) -> Dict[str, Any]:
        params = await self._auth_params("GET", "/fapi/v2/account")
        headers = {"X-MBX-APIKEY": self._api_key}
        resp = await self._request_with_retry("GET", "/fapi/v2/account", params=params, headers=headers)
        resp.raise_for_status()
        return resp.json()

    async def place_order(self, order: Dict[str, Any]) -> Dict[str, Any]:
        params = await self._auth_params("POST", "/fapi/v1/order", order)
        headers = {"X-MBX-APIKEY": self._api_key}
        resp = await self._request_with_retry("POST", "/fapi/v1/order", params=params, headers=headers)
        resp.raise_for_status()
        return resp.json()

    async def cancel_all(self, symbol: Optional[str] = None) -> None:
        """Cancel all open orders, gracefully handling cases where no orders exist."""
        try:
            params: Dict[str, Any] = {}
            if symbol:
                params["symbol"] = symbol
            params = await self._auth_params("DELETE", "/fapi/v1/allOpenOrders", params)
            headers = {"X-MBX-APIKEY": self._api_key}
            resp = await self._request_with_retry("DELETE", "/fapi/v1/allOpenOrders", params=params, headers=headers)
            resp.raise_for_status()
        except Exception as e:
            # Log but don't fail if there are no orders to cancel
            # This is expected in paper trading mode
            logger.warning(f"Cancel all orders failed (may be expected): {e}")
            # Don't re-raise the exception to avoid breaking emergency stop

    async def test_connectivity(self) -> Dict[str, Any]:
        """Test API connectivity and authentication."""
        try:
            # First test basic connectivity
            server_time = await self._server_time()

            # Then test authenticated endpoint
            account = await self.get_account()

            return {
                "status": "ok",
                "server_time": server_time,
                "account_status": "authenticated",
                "balances": len(account.get("balances", []))
            }
        except Exception as e:
            logger.error(f"Connectivity test failed: {str(e)}")
            return {
                "status": "error",
                "error": str(e),
                "error_type": type(e).__name__
            }
