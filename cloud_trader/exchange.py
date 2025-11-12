"""Aster exchange client."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import httpx
from decimal import Decimal
from httpx import HTTPStatusError
from pydantic import BaseModel, Field

from .credentials import Credentials


class Ticker(BaseModel):
    symbol: str
    price: float


class Order(BaseModel):
    orderId: int
    symbol: str
    price: float
    origQty: float
    executedQty: float
    status: str
    side: str
    type: str


class Execution(BaseModel):
    price: float
    qty: float


class Trade(BaseModel):
    id: int
    price: float
    qty: float
    isBuyerMaker: bool
    time: int


class AsterClient:
    def __init__(
        self,
        credentials: Optional[Credentials] = None,
        base_url: str = "https://fapi.asterdex.com",
    ):
        self._credentials = credentials
        self._base_url = base_url
        self._client = httpx.AsyncClient(base_url=self._base_url, timeout=10.0)

    async def close(self) -> None:
        await self._client.aclose()

    def _sign_request(self, params: Dict[str, Any]) -> Dict[str, Any]:
        if not self._credentials or not self._credentials.api_secret:
            raise ValueError("API secret is not configured")
        params["timestamp"] = int(time.time() * 1000)
        query_string = urlencode(list(params.items()), doseq=True)
        signature = hmac.new(
            self._credentials.api_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        params["signature"] = signature
        return params

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        signed: bool = False,
    ) -> Dict[str, Any]:
        params = params or {}
        if signed:
            if not self._credentials or not self._credentials.api_key:
                raise ValueError("API key is not configured for a signed request")
            params = self._sign_request(params)
            headers = {"X-MBX-APIKEY": self._credentials.api_key}
        else:
            headers = {}

        response = await self._client.request(
            method, endpoint, params=params, headers=headers
        )
        try:
            response.raise_for_status()
        except HTTPStatusError as exc:
            content = exc.response.text
            raise RuntimeError(
                f"Aster API error {exc.response.status_code} on {endpoint}: {content}"
            ) from exc
        return response.json()

    async def get_klines(
        self, symbol: str, interval: str, limit: int = 100
    ) -> List[Dict[str, Any]]:
        return await self._make_request(
            "GET",
            "/fapi/v1/klines",
            params={"symbol": symbol, "interval": interval, "limit": limit},
        )

    async def get_ticker_price(self, symbol: str) -> Dict[str, Any]:
        return await self._make_request(
            "GET", "/fapi/v1/ticker/price", params={"symbol": symbol}
        )
    
    async def get_all_tickers(self) -> List[Dict[str, Any]]:
        return await self._make_request("GET", "/fapi/v1/ticker/24hr")

    async def get_all_symbols(self) -> List[Dict[str, Any]]:
        """Get all trading symbols from exchange info."""
        exchange_info = await self._make_request("GET", "/fapi/v1/exchangeInfo")
        return exchange_info.get("symbols", [])

    async def get_account_info(self) -> Dict[str, Any]:
        return await self._make_request("GET", "/fapi/v4/account", signed=True)

    async def get_symbol_info(self, symbol: str) -> Dict[str, Any]:
        data = await self._make_request(
            "GET", "/fapi/v1/exchangeInfo", params={"symbol": symbol.upper()}
        )
        symbols = data.get("symbols", [])
        if not symbols:
            raise ValueError(f"Exchange info not found for symbol {symbol}")
        return symbols[0]

    async def get_symbol_filters(self, symbol: str) -> Dict[str, Any]:
        symbol_info = await self.get_symbol_info(symbol)
        filters = {f["filterType"]: f for f in symbol_info.get("filters", [])}

        lot_filter = filters.get("LOT_SIZE", {})
        min_notional_filter = filters.get("MIN_NOTIONAL", {})
        price_filter = filters.get("PRICE_FILTER", {})

        def _to_decimal(value: str | None, default: str = "0") -> Decimal:
            if value is None:
                value = default
            return Decimal(value)

        step_size = _to_decimal(lot_filter.get("stepSize"), "1")
        min_qty = _to_decimal(lot_filter.get("minQty"))
        max_qty = _to_decimal(lot_filter.get("maxQty"), "0")
        min_notional = _to_decimal(min_notional_filter.get("notional"))
        tick_size = _to_decimal(price_filter.get("tickSize"), "0.01")

        quantity_precision = max(0, -step_size.normalize().as_tuple().exponent)
        price_precision = max(0, -tick_size.normalize().as_tuple().exponent)

        return {
            "step_size": step_size,
            "min_qty": min_qty,
            "max_qty": max_qty,
            "min_notional": min_notional,
            "tick_size": tick_size,
            "quantity_precision": quantity_precision,
            "price_precision": price_precision,
        }

    async def get_position_risk(self) -> List[Dict[str, Any]]:
        return await self._make_request("GET", "/fapi/v2/positionRisk", signed=True)

    async def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: Optional[float] = None,
        price: Optional[float] = None,
        new_client_order_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        params = {
            "symbol": symbol,
            "side": side,
            "type": order_type,
            "quantity": quantity,
        }
        if price:
            params["price"] = price
            params["timeInForce"] = "GTC"
        if new_client_order_id:
            params["newClientOrderId"] = new_client_order_id

        # Remove None values that the API will reject
        params = {k: v for k, v in params.items() if v is not None}
        return await self._make_request("POST", "/fapi/v1/order", params=params, signed=True)

    async def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        params = {"symbol": symbol} if symbol else {}
        return await self._make_request("GET", "/fapi/v1/openOrders", params=params, signed=True)

    async def cancel_order(self, symbol: str, order_id: str) -> Dict[str, Any]:
        params = {"symbol": symbol, "orderId": order_id}
        return await self._make_request("DELETE", "/fapi/v1/order", params=params, signed=True)


class TrailingStop:
    def __init__(self, symbol: str, trail_percent: float):
        self.symbol = symbol
        self.trail_percent = trail_percent
        self.high_water_mark: Optional[float] = None
        self.is_active = False

    def __repr__(self) -> str:
        return (
            f"TrailingStop(symbol={self.symbol}, trail_percent={self.trail_percent}, "
            f"high_water_mark={self.high_water_mark}, is_active={self.is_active})"
        )
    
    def activate(self, current_price: float) -> None:
        self.is_active = True
        self.high_water_mark = current_price

    def should_sell(self, current_price: float) -> bool:
        if not self.is_active or self.high_water_mark is None:
            return False
        
        if current_price > self.high_water_mark:
            self.high_water_mark = current_price
            return False

        stop_price = self.high_water_mark * (1 - self.trail_percent)
        return current_price < stop_price

async def main():
    # Example usage, requires credentials to be set as env vars
    from .credentials import load_credentials
    creds = load_credentials()
    client = AsterClient(credentials=creds)
    try:
        # print(await client.get_klines("BTCUSDT", "1h"))
        # print(await client.get_ticker_price("BTCUSDT"))
        # print(await client.get_all_tickers())
        print(await client.get_account_info())
    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(main())
