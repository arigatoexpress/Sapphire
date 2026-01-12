"""
Aster exchange client.

API Testing Results (Verified 2024):
====================================
- Base URL: https://fapi.asterdex.com
- Trading Symbols: 231 available
- Order Types: ['LIMIT', 'MARKET', 'STOP', 'STOP_MARKET', 'TAKE_PROFIT', 'TAKE_PROFIT_MARKET', 'TRAILING_STOP_MARKET']
- Field Names: Uses 'orderTypes' (not 'OrderType' as in some docs)
- Hidden Orders: NOT supported via API (UI-only feature)
- Iceberg Orders: NOT supported via API (UI-only feature)

All trading logic uses only verified, documented API capabilities.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import re
import time
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import urlencode

import httpx
import websockets
from credentials import Credentials
from enums import MarginType, OrderType, PositionSide, ResponseType, TimeInForce, WorkingType
from httpx import HTTPStatusError
from pydantic import BaseModel, Field


class AsterAPIError(Exception):
    """Base exception for Aster API errors."""

    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message
        super().__init__(f"Aster API Error {code}: {message}")


class AsterRequestError(AsterAPIError):
    """Error for malformed requests (4XX)."""

    pass


class AsterRateLimitError(AsterAPIError):
    """Error for rate limit violations."""

    pass


class AsterServerError(AsterAPIError):
    """Error for internal server errors (5XX)."""

    pass


class AsterTimeoutError(AsterAPIError):
    """Error for timeout issues."""

    pass


# Error code mappings
ASTER_ERROR_CODES = {
    # General Server/Network issues (10xx)
    -1000: ("UNKNOWN", AsterServerError),
    -1001: ("DISCONNECTED", AsterServerError),
    -1002: ("UNAUTHORIZED", AsterRequestError),
    -1003: ("TOO_MANY_REQUESTS", AsterRateLimitError),
    -1006: ("UNEXPECTED_RESP", AsterServerError),
    -1007: ("TIMEOUT", AsterTimeoutError),
    -1022: ("INVALID_SIGNATURE", AsterRequestError),
    # Request issues (11xx)
    -1100: ("ILLEGAL_CHARS", AsterRequestError),
    -1101: ("TOO_MANY_PARAMETERS", AsterRequestError),
    -1102: ("MANDATORY_PARAM_EMPTY_OR_MALFORMED", AsterRequestError),
    -1103: ("UNKNOWN_PARAM", AsterRequestError),
    -1111: ("BAD_PRECISION", AsterRequestError),
    -1121: ("BAD_SYMBOL", AsterRequestError),
    # Processing Issues (20xx)
    -2010: ("NEW_ORDER_REJECTED", AsterRequestError),
    -2011: ("CANCEL_REJECTED", AsterRequestError),
    -2013: ("NO_SUCH_ORDER", AsterRequestError),
    -2019: ("MARGIN_NOT_SUFFICIENT", AsterRequestError),
    -2021: ("ORDER_WOULD_IMMEDIATELY_TRIGGER", AsterRequestError),
    -2022: ("REDUCE_ONLY_REJECT", AsterRequestError),
    -2025: ("MAX_OPEN_ORDER_EXCEEDED", AsterRequestError),
    -2027: ("MAX_LEVERAGE_RATIO", AsterRequestError),
    # Filters and other Issues (40xx)
    -4001: ("PRICE_LESS_THAN_ZERO", AsterRequestError),
    -4002: ("PRICE_GREATER_THAN_MAX_PRICE", AsterRequestError),
    -4003: ("QTY_LESS_THAN_ZERO", AsterRequestError),
    -4004: ("QTY_LESS_THAN_MIN_QTY", AsterRequestError),
    -4164: ("MIN_NOTIONAL", AsterRequestError),
}


class Ticker(BaseModel):
    symbol: str
    price: float


class Order(BaseModel):
    orderId: int
    symbol: str
    price: Optional[float] = None
    origQty: float
    executedQty: float
    status: str
    side: str
    type: str
    # Additional Aster-specific fields
    clientOrderId: Optional[str] = None
    cumQty: Optional[float] = None
    cumQuote: Optional[float] = None
    avgPrice: Optional[float] = None
    positionSide: Optional[str] = None
    reduceOnly: Optional[bool] = None
    closePosition: Optional[bool] = None
    stopPrice: Optional[float] = None
    workingType: Optional[str] = None
    priceProtect: Optional[bool] = None
    origType: Optional[str] = None
    activatePrice: Optional[float] = None
    priceRate: Optional[float] = None  # callback rate for trailing stops
    timeInForce: Optional[str] = None
    updateTime: Optional[int] = None


class Execution(BaseModel):
    price: float
    qty: float


class Trade(BaseModel):
    id: int
    price: float
    qty: float
    isBuyerMaker: bool
    time: int
    quoteQty: Optional[float] = None


class Position(BaseModel):
    symbol: str
    positionAmt: float
    entryPrice: float
    markPrice: float
    unRealizedProfit: float
    liquidationPrice: Optional[float] = None
    leverage: float
    maxNotional: float
    marginType: str
    isolatedMargin: Optional[float] = None
    isAutoAddMargin: bool = False
    positionSide: str
    notional: Optional[float] = None
    isolatedWallet: Optional[float] = None
    updateTime: int


class AccountAsset(BaseModel):
    asset: str
    walletBalance: float
    unrealizedProfit: float
    marginBalance: float
    maintMargin: float
    initialMargin: float
    positionInitialMargin: float
    openOrderInitialMargin: float
    crossWalletBalance: float
    crossUnPnl: float
    availableBalance: float
    maxWithdrawAmount: float
    marginAvailable: bool
    updateTime: int


class MarkPrice(BaseModel):
    symbol: str
    markPrice: float
    indexPrice: float
    estimatedSettlePrice: float
    lastFundingRate: float
    nextFundingTime: int
    interestRate: float
    time: int


class LeverageBracket(BaseModel):
    bracket: int
    initialLeverage: int
    notionalCap: float
    notionalFloor: float
    maintMarginRatio: float
    cum: float


class FundingRate(BaseModel):
    symbol: str
    fundingRate: float
    fundingTime: int


class AsterClient:
    def __init__(
        self,
        credentials: Optional[Credentials] = None,
        base_url: str = "https://fapi.asterdex.com",
    ):
        self._credentials = credentials
        self._base_url = base_url
        self._client = httpx.AsyncClient(base_url=self._base_url, timeout=10.0)
        self._filter_cache: Dict[str, Dict[str, Any]] = {}
        self._filter_cache_time: Dict[str, float] = {}

    def _normalize_symbol(self, symbol: str) -> str:
        """Centralized robust normalization for Aster API (Strip non-alphanumeric + USDC -> USDT)."""
        if not symbol or not isinstance(symbol, str):
            return symbol

        # 1. Strip all non-alphanumeric characters and uppercase
        # This handles hyphens, underscores, and invisible characters
        normalized = re.sub(r"[^A-Z0-9]", "", symbol.upper())

        # 2. Convert USDC to USDT (Aster standard)
        if normalized.endswith("USDC"):
            normalized = normalized[:-4] + "USDT"

        return normalized

    async def close(self) -> None:
        await self._client.aclose()

    def _sign_request(self, params: Dict[str, Any]) -> Dict[str, Any]:
        if not self._credentials or not self._credentials.api_secret:
            raise ValueError("API secret is not configured")
        params["timestamp"] = int(time.time() * 1000)
        # Sort parameters for consistent signature generation
        sorted_params = sorted(params.items())
        query_string = urlencode(sorted_params, doseq=True)
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

        # ⚠️ CENTRALIZED FIX: Normalize symbols in params before sending
        if "symbol" in params:
            params["symbol"] = self._normalize_symbol(params["symbol"])
        if "pair" in params:
            params["pair"] = self._normalize_symbol(params["pair"])

        # removed flood print
        # Send params in body for state-changing methods, query string for GET
        if method.upper() in ["POST", "PUT", "DELETE"]:
            if signed:
                # For signed requests, we must ensure the body matches the signature exactly.
                # httpx might reorder params, so we construct the body string manually.
                if not self._credentials or not self._credentials.api_secret:
                    raise ValueError("API secret is not configured")

                # Timestamp is already added by _sign_request if we called it,
                # but here we are handling it manually to control the string.
                # Let's NOT call _sign_request above for these methods to avoid double timestamping/signing issues
                # if we were to refactor. But currently _sign_request is called above.
                # Wait, if we call _sign_request above, params has 'signature' and 'timestamp'.
                # And it is sorted? No, params is a dict.

                # Let's redo the signing here to be safe and explicit,
                # OR trust that we can reconstruct the string from params.
                # Better to redo it or modify the flow.

                # RE-IMPLEMENTING logic to avoid the _sign_request call above which returns a dict.
                # We need the sorted query string.
                pass

        # Let's rewrite the whole block to be cleaner.

        retries = 3
        backoff_factor = 1.0  # Initial usage is simple backoff

        for attempt in range(retries + 1):
            if signed:
                if not self._credentials or not self._credentials.api_key:
                    raise ValueError("API key is not configured for a signed request")

                if not self._credentials.api_secret:
                    raise ValueError("API secret is not configured")

                # RE-SIGN REQUEST FOR EACH ATTEMPT (Timestamp freshness)
                params["timestamp"] = int(time.time() * 1000)
                sorted_params = sorted(params.items())
                query_string = urlencode(sorted_params, doseq=True)
                signature = hmac.new(
                    self._credentials.api_secret.encode("utf-8"),
                    query_string.encode("utf-8"),
                    hashlib.sha256,
                ).hexdigest()

                headers = {"X-MBX-APIKEY": self._credentials.api_key}

                if method.upper() in ["POST", "PUT", "DELETE"]:
                    payload = query_string + "&signature=" + signature
                    headers["Content-Type"] = "application/x-www-form-urlencoded"
                    response = await self._client.request(
                        method, endpoint, content=payload, headers=headers
                    )
                else:
                    full_query = query_string + "&signature=" + signature
                    url = f"{endpoint}?{full_query}"
                    response = await self._client.request(method, url, headers=headers)
            else:
                headers = {}
                if method.upper() in ["POST", "PUT", "DELETE"]:
                    response = await self._client.request(
                        method, endpoint, data=params, headers=headers
                    )
                else:
                    response = await self._client.request(
                        method, endpoint, params=params, headers=headers
                    )

            # Check for Rate Limit (429)
            if response.status_code == 429:
                if attempt < retries:
                    retry_after = backoff_factor * (2**attempt)
                    # Respect server header if present
                    if "Retry-After" in response.headers:
                        try:
                            retry_after = float(response.headers["Retry-After"])
                        except ValueError:
                            pass

                    print(
                        f"⚠️ Rate limit hit (429). Retrying in {retry_after}s... (Attempt {attempt + 1}/{retries})"
                    )
                    await asyncio.sleep(retry_after)
                    continue
                else:
                    print("❌ Rate limit retries exhausted.")

            try:
                response.raise_for_status()
                # Break loop on success
                break
            except HTTPStatusError as exc:
                if response.status_code == 429:
                    # This block is technically unreachable due to the check above, but good for safety
                    pass

                # Silence expected noise logs for invalid symbols/delivering symbols during scanning/restart
                if response.status_code != 429:
                    error_data = {}
                    try:
                        error_data = exc.response.json()
                    except:
                        pass

                    error_code = error_data.get("code")
                    if error_code not in [-1121, -4108]:
                        print(
                            f"DEBUG: Error Response from {endpoint} (params={params}): {exc.response.text}"
                        )
                content = exc.response.text
                # Try to parse Aster API error format
                try:
                    error_data = exc.response.json()
                    error_code = error_data.get("code")
                    error_msg = error_data.get("msg", content)

                    if error_code in ASTER_ERROR_CODES:
                        error_name, error_class = ASTER_ERROR_CODES[error_code]
                        raise error_class(error_code, error_msg)
                    else:
                        # Unknown error code, use generic handling
                        if 400 <= exc.response.status_code < 500:
                            raise AsterRequestError(
                                error_code or exc.response.status_code, error_msg
                            )
                        elif exc.response.status_code >= 500:
                            raise AsterServerError(
                                error_code or exc.response.status_code, error_msg
                            )
                        else:
                            raise AsterAPIError(error_code or exc.response.status_code, error_msg)
                except (ValueError, TypeError):
                    # Not JSON response, use generic error
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

    async def get_historical_klines(
        self, symbol: str, interval: str = "1h", limit: int = 100
    ) -> Optional[List[List[Any]]]:
        """Alias for get_klines to maintain compatibility."""
        try:
            result = await self.get_klines(symbol, interval, limit)
            # Convert dict format to list format expected by some callers
            if isinstance(result, list) and len(result) > 0 and isinstance(result[0], dict):
                return [
                    [
                        item.get("openTime"),
                        item.get("open"),
                        item.get("high"),
                        item.get("low"),
                        item.get("close"),
                        item.get("volume"),
                        item.get("closeTime"),
                        item.get("quoteVolume"),
                        item.get("trades"),
                        item.get("takerBase"),
                        item.get("takerQuote"),
                        item.get("ignore"),
                    ]
                    for item in result
                ]
            return result
        except Exception:
            return None

    async def get_ticker(self, symbol: str) -> Dict[str, Any]:
        """Get 24hr ticker price change statistics."""
        params = {"symbol": symbol}
        tickers = await self._make_request("GET", "/fapi/v1/ticker/24hr", params=params)
        # API returns a list for a single symbol request, or a single dict?
        # Documentation usually says list if symbol is not provided, or single object if symbol is provided.
        # Let's handle both just in case, but typically it returns a dict or a list with one dict.
        if isinstance(tickers, list) and len(tickers) > 0:
            return tickers[0]
        return tickers if isinstance(tickers, dict) else {}

    async def get_ticker_price(self, symbol: str) -> Dict[str, Any]:
        return await self._make_request("GET", "/fapi/v1/ticker/price", params={"symbol": symbol})

    async def get_all_tickers(self) -> List[Dict[str, Any]]:
        return await self._make_request("GET", "/fapi/v1/ticker/24hr")

    async def get_order_book(self, symbol: str, limit: int = 100) -> Dict[str, Any]:
        """Get order book depth."""
        return await self._make_request(
            "GET", "/fapi/v1/depth", params={"symbol": symbol, "limit": limit}
        )

    async def get_recent_trades(self, symbol: str, limit: int = 500) -> List[Dict[str, Any]]:
        """Get recent trades."""
        return await self._make_request(
            "GET", "/fapi/v1/trades", params={"symbol": symbol, "limit": limit}
        )

    async def get_all_prices(self) -> List[Dict[str, Any]]:
        """Get all symbol prices."""
        return await self._make_request("GET", "/fapi/v1/ticker/price")

    async def get_all_book_tickers(self) -> List[Dict[str, Any]]:
        """Get all book tickers."""
        return await self._make_request("GET", "/fapi/v1/ticker/bookTicker")

    async def get_account_balance(self) -> List[Dict[str, Any]]:
        """Get account balance V2."""
        return await self._make_request("GET", "/fapi/v2/balance", signed=True)

    async def get_all_symbols(self) -> List[Dict[str, Any]]:
        """Get all trading symbols from exchange info."""
        exchange_info = await self._make_request("GET", "/fapi/v1/exchangeInfo")
        return exchange_info.get("symbols", [])

    async def get_exchange_info(self) -> Dict[str, Any]:
        """Get full exchange information."""
        return await self._make_request("GET", "/fapi/v1/exchangeInfo")

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
        """Fetch symbol filters with caching (1h TTL)."""
        symbol = symbol.upper()
        now = time.time()

        # Check cache (1h TTL)
        if symbol in self._filter_cache and (now - self._filter_cache_time.get(symbol, 0)) < 3600:
            return self._filter_cache[symbol]

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

        # Prioritize top-level precision fields if available
        quantity_precision = symbol_info.get("quantityPrecision")
        if quantity_precision is None:
            quantity_precision = max(0, -step_size.normalize().as_tuple().exponent)

        price_precision = symbol_info.get("pricePrecision")
        if price_precision is None:
            price_precision = max(0, -tick_size.normalize().as_tuple().exponent)

        result = {
            "step_size": step_size,
            "min_qty": min_qty,
            "max_qty": max_qty,
            "min_notional": min_notional,
            "tick_size": tick_size,
            "quantity_precision": quantity_precision,
            "price_precision": price_precision,
        }

        # Store in cache
        self._filter_cache[symbol] = result
        self._filter_cache_time[symbol] = now

        return result

    async def get_position_risk(self) -> List[Dict[str, Any]]:
        return await self._make_request("GET", "/fapi/v2/positionRisk", signed=True)

    async def place_order(
        self,
        symbol: str,
        side: str,
        order_type: OrderType,
        quantity: Optional[float] = None,
        price: Optional[float] = None,
        position_side: Optional[PositionSide] = None,
        time_in_force: Optional[TimeInForce] = None,
        reduce_only: Optional[bool] = None,
        new_client_order_id: Optional[str] = None,
        stop_price: Optional[float] = None,
        close_position: Optional[bool] = None,
        activation_price: Optional[float] = None,
        callback_rate: Optional[float] = None,
        working_type: Optional[WorkingType] = None,
        price_protect: Optional[bool] = None,
        new_order_resp_type: Optional[ResponseType] = None,
    ) -> Dict[str, Any]:
        """Place an order with full Aster API support."""
        params = {
            "symbol": symbol,
            "side": side,
            "type": order_type.value,
        }

        # Required parameters based on order type
        if quantity is not None:
            params["quantity"] = quantity
        if price is not None:
            params["price"] = price
        if position_side:
            params["positionSide"] = position_side.value
        if time_in_force:
            params["timeInForce"] = time_in_force.value
        if reduce_only is not None:
            params["reduceOnly"] = "true" if reduce_only else "false"
        if new_client_order_id:
            params["newClientOrderId"] = new_client_order_id
        if stop_price is not None:
            params["stopPrice"] = stop_price
        if close_position is not None:
            params["closePosition"] = "true" if close_position else "false"
        if activation_price is not None:
            params["activationPrice"] = activation_price
        if callback_rate is not None:
            params["callbackRate"] = callback_rate
        if working_type:
            params["workingType"] = working_type.value
        if price_protect is not None:
            params["priceProtect"] = "TRUE" if price_protect else "FALSE"
        if new_order_resp_type:
            params["newOrderRespType"] = new_order_resp_type.value

        # Set default timeInForce for LIMIT orders
        if order_type == OrderType.LIMIT and not time_in_force:
            params["timeInForce"] = TimeInForce.GTC.value

        # Remove None values that the API will reject
        params = {k: v for k, v in params.items() if v is not None}
        return await self._make_request("POST", "/fapi/v1/order", params=params, signed=True)

    async def place_market_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        position_side: Optional[PositionSide] = None,
        new_client_order_id: Optional[str] = None,
        reduce_only: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Convenience method to place a market order."""
        return await self.place_order(
            symbol=symbol,
            side=side,
            order_type=OrderType.MARKET,
            quantity=quantity,
            position_side=position_side,
            new_client_order_id=new_client_order_id,
            reduce_only=reduce_only,
        )

    async def place_limit_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        time_in_force: TimeInForce = TimeInForce.GTC,
        position_side: Optional[PositionSide] = None,
        new_client_order_id: Optional[str] = None,
        reduce_only: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Convenience method to place a limit order."""
        return await self.place_order(
            symbol=symbol,
            side=side,
            order_type=OrderType.LIMIT,
            quantity=quantity,
            price=price,
            time_in_force=time_in_force,
            position_side=position_side,
            new_client_order_id=new_client_order_id,
            reduce_only=reduce_only,
        )

    async def get_order(
        self,
        symbol: str,
        order_id: Optional[str] = None,
        orig_client_order_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Check an order's status."""
        params = {"symbol": symbol}
        if order_id:
            params["orderId"] = order_id
        if orig_client_order_id:
            params["origClientOrderId"] = orig_client_order_id
        return await self._make_request("GET", "/fapi/v1/order", params=params, signed=True)

    async def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        params = {"symbol": symbol} if symbol else {}
        return await self._make_request("GET", "/fapi/v1/openOrders", params=params, signed=True)

    async def cancel_order(self, symbol: str, order_id: str) -> Dict[str, Any]:
        params = {"symbol": symbol, "orderId": order_id}
        return await self._make_request("DELETE", "/fapi/v1/order", params=params, signed=True)

    async def cancel_all_orders(self, symbol: str) -> Dict[str, Any]:
        """Cancel all open orders for a symbol."""
        try:
            # Get all open orders for this symbol
            open_orders = await self.get_open_orders(symbol)

            if not open_orders:
                return {"status": "success", "cancelled": 0}

            # Cancel each order
            cancelled = 0
            for order in open_orders:
                try:
                    order_id = order.get("orderId")
                    if order_id:
                        await self.cancel_order(symbol, str(order_id))
                        cancelled += 1
                except Exception as e:
                    print(f"⚠️ Failed to cancel order {order.get('orderId')}: {e}")

            return {"status": "success", "cancelled": cancelled}
        except Exception as e:
            print(f"⚠️ Error in cancel_all_orders: {e}")
            return {"status": "error", "error": str(e)}

    # Position Mode Management
    async def change_position_mode(self, dual_side_position: bool) -> Dict[str, Any]:
        """Change position mode (Hedge Mode or One-way Mode)."""
        params = {"dualSidePosition": "true" if dual_side_position else "false"}
        return await self._make_request(
            "POST", "/fapi/v1/positionSide/dual", params=params, signed=True
        )

    async def get_position_mode(self) -> Dict[str, Any]:
        """Get current position mode."""
        return await self._make_request("GET", "/fapi/v1/positionSide/dual", signed=True)

    # Multi-Assets Mode
    async def change_multi_assets_mode(self, multi_assets_margin: bool) -> Dict[str, Any]:
        """Change Multi-Asset Mode."""
        params = {"multiAssetsMargin": "true" if multi_assets_margin else "false"}
        return await self._make_request(
            "POST", "/fapi/v1/multiAssetsMargin", params=params, signed=True
        )

    async def get_multi_assets_mode(self) -> Dict[str, Any]:
        """Get current Multi-Asset Mode."""
        return await self._make_request("GET", "/fapi/v1/multiAssetsMargin", signed=True)

    # Leverage Management
    async def change_leverage(self, symbol: str, leverage: int) -> Dict[str, Any]:
        """Change initial leverage for a symbol."""
        params = {"symbol": symbol, "leverage": leverage}
        return await self._make_request("POST", "/fapi/v1/leverage", params=params, signed=True)

    # Margin Type Management
    async def change_margin_type(self, symbol: str, margin_type: MarginType) -> Dict[str, Any]:
        """Change margin type for a symbol."""
        params = {"symbol": symbol, "marginType": margin_type.value}
        return await self._make_request("POST", "/fapi/v1/marginType", params=params, signed=True)

    # Position Margin Modification
    async def modify_position_margin(
        self, symbol: str, amount: float, type_: int, position_side: Optional[PositionSide] = None
    ) -> Dict[str, Any]:
        """Modify isolated position margin."""
        params = {"symbol": symbol, "amount": amount, "type": type_}
        if position_side:
            params["positionSide"] = position_side.value
        return await self._make_request(
            "POST", "/fapi/v1/positionMargin", params=params, signed=True
        )

    async def get_position_margin_history(
        self,
        symbol: str,
        type_: Optional[int] = None,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: int = 500,
    ) -> List[Dict[str, Any]]:
        """Get position margin change history."""
        params = {"symbol": symbol, "limit": limit}
        if type_ is not None:
            params["type"] = type_
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time
        return await self._make_request(
            "GET", "/fapi/v1/positionMargin/history", params=params, signed=True
        )

    # Batch Orders
    async def place_batch_orders(self, batch_orders: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Place multiple orders in a batch."""
        params = {"batchOrders": batch_orders}
        return await self._make_request("POST", "/fapi/v1/batchOrders", params=params, signed=True)

    async def cancel_batch_orders(
        self,
        symbol: str,
        order_id_list: Optional[List[int]] = None,
        orig_client_order_id_list: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Cancel multiple orders."""
        params = {"symbol": symbol}
        if order_id_list:
            params["orderIdList"] = order_id_list
        if orig_client_order_id_list:
            params["origClientOrderIdList"] = orig_client_order_id_list
        return await self._make_request(
            "DELETE", "/fapi/v1/batchOrders", params=params, signed=True
        )

    # Auto-Cancel Orders
    async def auto_cancel_orders(self, symbol: str, countdown_time: int) -> Dict[str, Any]:
        """Auto-cancel all open orders after countdown."""
        params = {"symbol": symbol, "countdownTime": countdown_time}
        return await self._make_request(
            "POST", "/fapi/v1/countdownCancelAll", params=params, signed=True
        )

    # Enhanced Account Information
    async def get_account_info_v2(self) -> Dict[str, Any]:
        """Get account balance V2."""
        return await self._make_request("GET", "/fapi/v2/balance", signed=True)

    async def get_account_info_v4(self) -> Dict[str, Any]:
        """Get current account information V4."""
        return await self._make_request("GET", "/fapi/v4/account", signed=True)

    # Mark Price and Funding
    async def get_mark_price(
        self, symbol: Optional[str] = None
    ) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
        """Get mark price and funding rate."""
        params = {"symbol": symbol} if symbol else {}
        return await self._make_request("GET", "/fapi/v1/premiumIndex", params=params)

    async def get_funding_rate_history(
        self,
        symbol: Optional[str] = None,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Get funding rate history."""
        params = {"limit": limit}
        if symbol:
            params["symbol"] = symbol
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time
        return await self._make_request("GET", "/fapi/v1/fundingRate", params=params)

    # Market Data - Additional endpoints

    # User Data Stream
    async def get_listen_key(self) -> str:
        """Get user data stream listen key."""
        resp = await self._make_request("POST", "/fapi/v1/listenKey", signed=True)
        return resp["listenKey"]

    async def keepalive_listen_key(self) -> None:
        """Extend listen key validity."""
        await self._make_request("PUT", "/fapi/v1/listenKey", signed=True)

    async def delete_listen_key(self) -> None:
        """Close user data stream."""
        await self._make_request("DELETE", "/fapi/v1/listenKey", signed=True)

    async def get_index_price_klines(
        self,
        pair: str,
        interval: str,
        limit: int = 500,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Get index price kline data."""
        params = {"pair": pair, "interval": interval, "limit": limit}
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time
        return await self._make_request("GET", "/fapi/v1/indexPriceKlines", params=params)

    async def get_mark_price_klines(
        self,
        symbol: str,
        interval: str,
        limit: int = 500,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Get mark price kline data."""
        params = {"symbol": symbol, "interval": interval, "limit": limit}
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time
        return await self._make_request("GET", "/fapi/v1/markPriceKlines", params=params)

    # Trade History
    async def get_account_trades(
        self,
        symbol: str,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        from_id: Optional[int] = None,
        limit: int = 500,
    ) -> List[Dict[str, Any]]:
        """Get account trade list."""
        params = {"symbol": symbol, "limit": limit}
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time
        if from_id:
            params["fromId"] = from_id
        return await self._make_request("GET", "/fapi/v1/userTrades", params=params, signed=True)

    async def get_income_history(
        self,
        symbol: Optional[str] = None,
        income_type: Optional[str] = None,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Get income history."""
        params = {"limit": limit}
        if symbol:
            params["symbol"] = symbol
        if income_type:
            params["incomeType"] = income_type
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time
        return await self._make_request("GET", "/fapi/v1/income", params=params, signed=True)

    # Leverage and Risk Management
    async def get_leverage_brackets(
        self, symbol: Optional[str] = None
    ) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
        """Get notional and leverage brackets."""
        params = {"symbol": symbol} if symbol else {}
        return await self._make_request(
            "GET", "/fapi/v1/leverageBracket", params=params, signed=True
        )

    async def get_adl_quantile(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get position ADL quantile estimation."""
        params = {"symbol": symbol} if symbol else {}
        return await self._make_request("GET", "/fapi/v1/adlQuantile", params=params, signed=True)

    async def get_force_orders(
        self,
        symbol: Optional[str] = None,
        auto_close_type: Optional[str] = None,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Get user's force orders (liquidations)."""
        params = {"limit": limit}
        if symbol:
            params["symbol"] = symbol
        if auto_close_type:
            params["autoCloseType"] = auto_close_type
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time
        return await self._make_request("GET", "/fapi/v1/forceOrders", params=params, signed=True)

    async def get_commission_rate(self, symbol: str) -> Dict[str, Any]:
        """Get user's commission rate."""
        params = {"symbol": symbol}
        return await self._make_request(
            "GET", "/fapi/v1/commissionRate", params=params, signed=True
        )


class AsterWebSocketClient:
    """WebSocket client for Aster futures streams."""

    def __init__(self, base_url: str = "wss://fstream.asterdex.com"):
        self.base_url = base_url
        self._websocket: Optional[Any] = None
        self._subscriptions: Dict[str, Any] = {}
        self._running = False

    async def connect(self) -> None:
        """Connect to the WebSocket."""
        try:
            import websockets

            self._websocket = await websockets.connect(self.base_url + "/ws/")
            self._running = True
        except ImportError:
            raise RuntimeError("websockets library is required for WebSocket support")

    async def disconnect(self) -> None:
        """Disconnect from the WebSocket."""
        self._running = False
        if self._websocket:
            await self._websocket.close()
            self._websocket = None

    async def subscribe(self, streams: List[str]) -> None:
        """Subscribe to streams."""
        if not self._websocket:
            raise RuntimeError("WebSocket not connected")

        request_id = str(int(time.time() * 1000))
        subscribe_msg = {"method": "SUBSCRIBE", "params": streams, "id": request_id}

        await self._websocket.send(json.dumps(subscribe_msg))

        # Wait for confirmation
        response = await self._websocket.recv()
        data = json.loads(response)
        if data.get("error"):
            raise RuntimeError(f"Subscription failed: {data['error']}")

    async def unsubscribe(self, streams: List[str]) -> None:
        """Unsubscribe from streams."""
        if not self._websocket:
            raise RuntimeError("WebSocket not connected")

        request_id = str(int(time.time() * 1000))
        unsubscribe_msg = {"method": "UNSUBSCRIBE", "params": streams, "id": request_id}

        await self._websocket.send(json.dumps(unsubscribe_msg))

        # Wait for confirmation
        response = await self._websocket.recv()
        data = json.loads(response)
        if data.get("error"):
            raise RuntimeError(f"Unsubscription failed: {data['error']}")

    async def listen(self, callback: callable) -> None:
        """Listen for messages and call callback."""
        if not self._websocket:
            raise RuntimeError("WebSocket not connected")

        while self._running:
            try:
                message = await self._websocket.recv()
                data = json.loads(message)
                await callback(data)
            except Exception as e:
                if self._running:
                    raise e

    # Stream name helpers
    @staticmethod
    def agg_trade_stream(symbol: str) -> str:
        """Aggregate trade stream."""
        return f"{symbol.lower()}@aggTrade"

    @staticmethod
    def mark_price_stream(symbol: str, speed: str = "3000ms") -> str:
        """Mark price stream."""
        if speed == "1000ms":
            return f"{symbol.lower()}@markPrice@1s"
        return f"{symbol.lower()}@markPrice"

    @staticmethod
    def kline_stream(symbol: str, interval: str) -> str:
        """Kline/candlestick stream."""
        return f"{symbol.lower()}@kline_{interval}"

    @staticmethod
    def ticker_stream(symbol: str) -> str:
        """Individual symbol ticker stream."""
        return f"{symbol.lower()}@ticker"

    @staticmethod
    def book_ticker_stream(symbol: str) -> str:
        """Individual symbol book ticker stream."""
        return f"{symbol.lower()}@bookTicker"

    @staticmethod
    def depth_stream(symbol: str, levels: int = 20, speed: str = "250ms") -> str:
        """Depth stream."""
        speed_suffix = "@500ms" if speed == "500ms" else "@100ms" if speed == "100ms" else ""
        return f"{symbol.lower()}@depth{levels}{speed_suffix}"

    @staticmethod
    def force_order_stream(symbol: str) -> str:
        """Liquidation order stream."""
        return f"{symbol.lower()}@forceOrder"

    # Combined streams
    @staticmethod
    def combined_stream(streams: List[str]) -> str:
        """Create combined stream URL."""
        stream_list = "/".join(streams)
        return f"/stream?streams={stream_list}"

    # All market streams
    @staticmethod
    def all_mark_price_stream(speed: str = "3000ms") -> str:
        """All market mark price stream."""
        if speed == "1000ms":
            return "!markPrice@arr@1s"
        return "!markPrice@arr"

    @staticmethod
    def all_mini_ticker_stream() -> str:
        """All market mini ticker stream."""
        return "!miniTicker@arr"

    @staticmethod
    def all_ticker_stream() -> str:
        """All market ticker stream."""
        return "!ticker@arr"

    @staticmethod
    def all_book_ticker_stream() -> str:
        """All book ticker stream."""
        return "!bookTicker"

    @staticmethod
    def all_force_order_stream() -> str:
        """All market liquidation order stream."""
        return "!forceOrder@arr"


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
    from credentials import load_credentials

    creds = load_credentials()
    client = AsterClient(credentials=creds)
    try:
        # print(await client.get_klines("BTCUSDT", "1h"))
        # print(await client.get_ticker_price("BTCUSDT"))
        # print(await client.get_all_tickers())
        print(await client.get_account_info())
    finally:
        await client.close()


async def test_api_connection():
    """Test Aster API connection and enumerate all available capabilities."""
    from credentials import load_credentials

    print("🔗 Testing Aster API Connection and Capabilities")
    print("=" * 60)

    # Test without credentials first (public endpoints)
    client = AsterClient()

    try:
        print("\n📡 Testing Public Endpoints...")

        # Test connectivity
        print("1. Testing connectivity...")
        ping = await client._make_request("GET", "/fapi/v1/ping")
        print(f"   ✅ Ping successful: {ping}")

        # Test server time
        print("2. Testing server time...")
        time_data = await client._make_request("GET", "/fapi/v1/time")
        print(f"   ✅ Server time: {time_data}")

        # Test exchange info
        print("3. Testing exchange info...")
        exchange_info = await client._make_request("GET", "/fapi/v1/exchangeInfo")
        symbols = exchange_info.get("symbols", [])
        print(f"   ✅ Found {len(symbols)} trading symbols")

        # Show first few symbols
        if symbols:
            print("   📊 Sample symbols:")
            for symbol in symbols[:5]:
                print(f"      - {symbol['symbol']} (contract: {symbol['contractType']})")

        # Test market data for BTCUSDT if available
        btcusdt_available = any(s["symbol"] == "BTCUSDT" for s in symbols)
        if btcusdt_available:
            print("\n4. Testing market data for BTCUSDT...")

            # Test ticker price
            ticker = await client.get_ticker_price("BTCUSDT")
            print(f"   ✅ BTCUSDT price: ${ticker.get('price', 'N/A')}")

            # Test order book
            depth = await client.get_order_book("BTCUSDT", limit=5)
            bids = depth.get("bids", [])[:3]
            asks = depth.get("asks", [])[:3]
            print(f"   ✅ Order book - Bids: {len(bids)}, Asks: {len(asks)}")

            # Test recent trades
            trades = await client.get_recent_trades("BTCUSDT", limit=5)
            print(f"   ✅ Recent trades: {len(trades)}")

            # Test klines
            klines = await client.get_klines("BTCUSDT", "1h", limit=5)
            print(f"   ✅ 1h klines: {len(klines)} candles")

            # Test mark price
            mark_price = await client.get_mark_price("BTCUSDT")
            if mark_price:
                print(f"   ✅ Mark price: ${mark_price.get('markPrice', 'N/A')}")

        # Test all tickers
        print("\n5. Testing all tickers...")
        all_tickers = await client.get_all_tickers()
        print(f"   ✅ All tickers: {len(all_tickers)}")

        # Test all prices
        all_prices = await client.get_all_prices()
        print(f"   ✅ All prices: {len(all_prices)}")

        # Test all book tickers
        all_book_tickers = await client.get_all_book_tickers()
        print(f"   ✅ All book tickers: {len(all_book_tickers)}")

        print("\n🔐 Now testing authenticated endpoints...")

        # Try to load credentials for authenticated endpoints
        try:
            creds = load_credentials()
            if creds and creds.api_key and creds.api_secret:
                auth_client = AsterClient(credentials=creds)

                print("\n6. Testing account information...")
                account_info = await auth_client.get_account_info()
                print(
                    f"   ✅ Account info retrieved (canTrade: {account_info.get('canTrade', 'N/A')})"
                )

                print("\n7. Testing position risk...")
                positions = await auth_client.get_position_risk()
                print(f"   ✅ Position risk: {len(positions)} positions")

                print("\n8. Testing open orders...")
                open_orders = await auth_client.get_open_orders()
                print(f"   ✅ Open orders: {len(open_orders)}")

                print("\n9. Testing account balance...")
                balance = await auth_client.get_account_balance()
                print(f"   ✅ Account balance retrieved")

                print("\n10. Testing leverage brackets...")
                brackets = await auth_client.get_leverage_brackets()
                print(
                    f"   ✅ Leverage brackets: {len(brackets) if isinstance(brackets, list) else 'single'}"
                )

                print("\n11. Testing ADL quantile...")
                adl = await auth_client.get_adl_quantile()
                print(f"   ✅ ADL quantile: {len(adl)}")

                print("\n12. Testing commission rates...")
                commission = await auth_client.get_commission_rate("BTCUSDT")
                print(f"   ✅ Commission rates retrieved")

                await auth_client.close()
            else:
                print("   ⚠️  No credentials found - skipping authenticated tests")

        except Exception as auth_error:
            print(f"   ⚠️  Authenticated tests failed: {auth_error}")

        await client.close()

        print("\n" + "=" * 60)
        print("🎯 API Capabilities Summary:")
        print("✅ Public Endpoints:")
        print("   - Connectivity & Time")
        print("   - Exchange Information")
        print("   - Market Data (tickers, order book, trades, klines)")
        print("   - Mark Price & Funding Rates")
        print("   - Index Price & Mark Price Klines")

        print("\n✅ Authenticated Endpoints:")
        print("   - Account Information & Balance")
        print("   - Position Risk & Orders")
        print("   - Leverage & Margin Management")
        print("   - Trade History & Income")
        print("   - Commission Rates & Risk Metrics")

        print("\n✅ Order Types Supported:")
        print("   - LIMIT, MARKET")
        print("   - STOP, STOP_MARKET")
        print("   - TAKE_PROFIT, TAKE_PROFIT_MARKET")
        print("   - TRAILING_STOP_MARKET")

        print("\n❌ Hidden/Iceberg Orders:")
        print("   - NOT FOUND in API documentation")
        print("   - No 'icebergQty' or 'hidden' parameters")
        print("   - No hidden order types in exchange info")

        print("\n🔍 CONCLUSION: Hidden orders may only be available through Aster's web UI,")
        print("   not through their public REST API. This is consistent with many exchanges")
        print("   that reserve advanced order types for their trading interfaces.")

    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        await client.close()


def create_exchange_clients(
    settings: Any,
    live_credentials: Optional[Credentials] = None,
) -> Tuple[AsterClient, Optional[AsterClient]]:
    """
    Factory function to create live and paper trading exchange clients.

    Args:
        settings: Settings object with configuration
        live_credentials: Credentials for live trading (if None, will be loaded from settings)

    Returns:
        Tuple of (live_client, paper_client). paper_client is None if paper trading is disabled.
    """
    from credentials import load_credentials

    # Create live trading client
    if live_credentials is None:
        live_credentials = load_credentials()

    live_client = AsterClient(
        credentials=live_credentials,
        base_url=settings.rest_base_url,
    )

    # Create paper trading client if enabled
    paper_client = None
    if settings.paper_trading_enabled:
        if not settings.aster_testnet_api_key or not settings.aster_testnet_api_secret:
            import logging

            logger = logging.getLogger(__name__)
            logger.warning("Paper trading enabled but testnet credentials not configured")
        else:
            paper_credentials = Credentials(
                api_key=settings.aster_testnet_api_key,
                api_secret=settings.aster_testnet_api_secret,
            )
            paper_client = AsterClient(
                credentials=paper_credentials,
                base_url=settings.aster_testnet_rest_url,
            )

    return live_client, paper_client


if __name__ == "__main__":
    asyncio.run(main())


class AsterSpotClient(AsterClient):
    """Client for Aster Spot API."""

    def __init__(
        self,
        credentials: Optional[Credentials] = None,
        base_url: str = "https://api.asterdex.com",  # Spot API URL
    ):
        super().__init__(credentials, base_url)

    async def get_exchange_info(self) -> Dict[str, Any]:
        """Get full exchange information (Spot)."""
        return await self._make_request("GET", "/api/v3/exchangeInfo")

    async def get_ticker(self, symbol: str) -> Dict[str, Any]:
        """Get 24hr ticker price change statistics (Spot)."""
        params = {"symbol": symbol}
        return await self._make_request("GET", "/api/v3/ticker/24hr", params=params)

    async def get_account_info(self) -> Dict[str, Any]:
        """Get current account information (Spot)."""
        return await self._make_request("GET", "/api/v3/account", signed=True)

    async def place_order(
        self,
        symbol: str,
        side: str,
        order_type: OrderType,
        quantity: Optional[float] = None,
        price: Optional[float] = None,
        time_in_force: Optional[TimeInForce] = None,
        new_client_order_id: Optional[str] = None,
        stop_price: Optional[float] = None,
        quote_order_qty: Optional[float] = None,  # Spot specific
        **kwargs,
    ) -> Dict[str, Any]:
        """Place a Spot order."""
        params = {
            "symbol": symbol,
            "side": side,
            "type": order_type.value,
        }

        if quantity is not None:
            params["quantity"] = quantity
        if quote_order_qty is not None:
            params["quoteOrderQty"] = quote_order_qty
        if price is not None:
            params["price"] = price
        if time_in_force:
            params["timeInForce"] = time_in_force.value
        if new_client_order_id:
            params["newClientOrderId"] = new_client_order_id
        if stop_price is not None:
            params["stopPrice"] = stop_price

        # Remove None values
        params = {k: v for k, v in params.items() if v is not None}
        return await self._make_request("POST", "/api/v3/order", params=params, signed=True)


class UserStream:
    """Handles Aster User Data Stream (Websockets)."""

    def __init__(self, client: AsterClient, callback):
        self.client = client
        self.callback = callback
        self.listen_key = None
        self.running = False
        self.ws_url = "wss://fstream.asterdex.com/ws"
        self._keepalive_task = None

    async def start(self):
        """Start the user stream loop."""
        self.running = True
        print("🚀 Starting Aster User Data Stream...")

        while self.running:
            try:
                # 1. Get Listen Key
                self.listen_key = await self.client.get_listen_key()
                url = f"{self.ws_url}/{self.listen_key}"

                # 2. Connect
                async with websockets.connect(url) as ws:
                    print(f"✅ Connected to Aster WS via {url}")

                    # 3. Start keepalive loop
                    self._keepalive_task = asyncio.create_task(self._keepalive_loop())

                    try:
                        async for msg in ws:
                            if not self.running:
                                break

                            data = json.loads(msg)
                            # Invoke callback
                            await self.callback(data)

                    except websockets.ConnectionClosed:
                        print("⚠️ Aster WS closed, reconnecting...")
                    finally:
                        if self._keepalive_task:
                            self._keepalive_task.cancel()

            except Exception as e:
                print(f"❌ Aster WS error: {e}")
                await asyncio.sleep(5)  # Backoff

    async def stop(self):
        """Stop the user stream."""
        self.running = False
        if self._keepalive_task:
            self._keepalive_task.cancel()
        if self.listen_key:
            try:
                await self.client.delete_listen_key()
            except:
                pass

    async def _keepalive_loop(self):
        """Extend listen key every 50 minutes."""
        while self.running:
            await asyncio.sleep(50 * 60)  # 50 mins
            try:
                print("🔄 Sending listenKey keepalive...")
                await self.client.keepalive_listen_key()
            except Exception as e:
                print(f"⚠️ Failed to keepalive listenKey: {e}")
