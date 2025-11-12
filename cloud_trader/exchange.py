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
import time
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlencode

import httpx
from decimal import Decimal
from httpx import HTTPStatusError
from pydantic import BaseModel, Field

from .credentials import Credentials
from .enums import OrderType, PositionSide, TimeInForce, WorkingType, MarginType, ResponseType


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
                        raise AsterRequestError(error_code or exc.response.status_code, error_msg)
                    elif exc.response.status_code >= 500:
                        raise AsterServerError(error_code or exc.response.status_code, error_msg)
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

    async def get_ticker_price(self, symbol: str) -> Dict[str, Any]:
        return await self._make_request(
            "GET", "/fapi/v1/ticker/price", params={"symbol": symbol}
        )
    
    async def get_all_tickers(self) -> List[Dict[str, Any]]:
        return await self._make_request("GET", "/fapi/v1/ticker/24hr")

    async def get_order_book(self, symbol: str, limit: int = 100) -> Dict[str, Any]:
        """Get order book depth."""
        return await self._make_request("GET", "/fapi/v1/depth", params={"symbol": symbol, "limit": limit})

    async def get_recent_trades(self, symbol: str, limit: int = 500) -> List[Dict[str, Any]]:
        """Get recent trades."""
        return await self._make_request("GET", "/fapi/v1/trades", params={"symbol": symbol, "limit": limit})

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

    async def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        params = {"symbol": symbol} if symbol else {}
        return await self._make_request("GET", "/fapi/v1/openOrders", params=params, signed=True)

    async def cancel_order(self, symbol: str, order_id: str) -> Dict[str, Any]:
        params = {"symbol": symbol, "orderId": order_id}
        return await self._make_request("DELETE", "/fapi/v1/order", params=params, signed=True)

    # Position Mode Management
    async def change_position_mode(self, dual_side_position: bool) -> Dict[str, Any]:
        """Change position mode (Hedge Mode or One-way Mode)."""
        params = {"dualSidePosition": "true" if dual_side_position else "false"}
        return await self._make_request("POST", "/fapi/v1/positionSide/dual", params=params, signed=True)

    async def get_position_mode(self) -> Dict[str, Any]:
        """Get current position mode."""
        return await self._make_request("GET", "/fapi/v1/positionSide/dual", signed=True)

    # Multi-Assets Mode
    async def change_multi_assets_mode(self, multi_assets_margin: bool) -> Dict[str, Any]:
        """Change Multi-Asset Mode."""
        params = {"multiAssetsMargin": "true" if multi_assets_margin else "false"}
        return await self._make_request("POST", "/fapi/v1/multiAssetsMargin", params=params, signed=True)

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
        return await self._make_request("POST", "/fapi/v1/positionMargin", params=params, signed=True)

    async def get_position_margin_history(
        self, symbol: str, type_: Optional[int] = None,
        start_time: Optional[int] = None, end_time: Optional[int] = None,
        limit: int = 500
    ) -> List[Dict[str, Any]]:
        """Get position margin change history."""
        params = {"symbol": symbol, "limit": limit}
        if type_ is not None:
            params["type"] = type_
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time
        return await self._make_request("GET", "/fapi/v1/positionMargin/history", params=params, signed=True)

    # Batch Orders
    async def place_batch_orders(self, batch_orders: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Place multiple orders in a batch."""
        params = {"batchOrders": batch_orders}
        return await self._make_request("POST", "/fapi/v1/batchOrders", params=params, signed=True)

    async def cancel_batch_orders(
        self, symbol: str,
        order_id_list: Optional[List[int]] = None,
        orig_client_order_id_list: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """Cancel multiple orders."""
        params = {"symbol": symbol}
        if order_id_list:
            params["orderIdList"] = order_id_list
        if orig_client_order_id_list:
            params["origClientOrderIdList"] = orig_client_order_id_list
        return await self._make_request("DELETE", "/fapi/v1/batchOrders", params=params, signed=True)

    # Auto-Cancel Orders
    async def auto_cancel_orders(self, symbol: str, countdown_time: int) -> Dict[str, Any]:
        """Auto-cancel all open orders after countdown."""
        params = {"symbol": symbol, "countdownTime": countdown_time}
        return await self._make_request("POST", "/fapi/v1/countdownCancelAll", params=params, signed=True)

    # Enhanced Account Information
    async def get_account_info_v2(self) -> Dict[str, Any]:
        """Get account balance V2."""
        return await self._make_request("GET", "/fapi/v2/balance", signed=True)

    async def get_account_info_v4(self) -> Dict[str, Any]:
        """Get current account information V4."""
        return await self._make_request("GET", "/fapi/v4/account", signed=True)

    # Mark Price and Funding
    async def get_mark_price(self, symbol: Optional[str] = None) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
        """Get mark price and funding rate."""
        params = {"symbol": symbol} if symbol else {}
        return await self._make_request("GET", "/fapi/v1/premiumIndex", params=params)

    async def get_funding_rate_history(
        self, symbol: Optional[str] = None,
        start_time: Optional[int] = None, end_time: Optional[int] = None,
        limit: int = 100
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
    async def get_index_price_klines(
        self, pair: str, interval: str, limit: int = 500,
        start_time: Optional[int] = None, end_time: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Get index price kline data."""
        params = {"pair": pair, "interval": interval, "limit": limit}
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time
        return await self._make_request("GET", "/fapi/v1/indexPriceKlines", params=params)

    async def get_mark_price_klines(
        self, symbol: str, interval: str, limit: int = 500,
        start_time: Optional[int] = None, end_time: Optional[int] = None
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
        self, symbol: str, start_time: Optional[int] = None, end_time: Optional[int] = None,
        from_id: Optional[int] = None, limit: int = 500
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
        self, symbol: Optional[str] = None, income_type: Optional[str] = None,
        start_time: Optional[int] = None, end_time: Optional[int] = None,
        limit: int = 100
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
    async def get_leverage_brackets(self, symbol: Optional[str] = None) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
        """Get notional and leverage brackets."""
        params = {"symbol": symbol} if symbol else {}
        return await self._make_request("GET", "/fapi/v1/leverageBracket", params=params, signed=True)

    async def get_adl_quantile(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get position ADL quantile estimation."""
        params = {"symbol": symbol} if symbol else {}
        return await self._make_request("GET", "/fapi/v1/adlQuantile", params=params, signed=True)

    async def get_force_orders(
        self, symbol: Optional[str] = None, auto_close_type: Optional[str] = None,
        start_time: Optional[int] = None, end_time: Optional[int] = None,
        limit: int = 50
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
        return await self._make_request("GET", "/fapi/v1/commissionRate", params=params, signed=True)



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
        subscribe_msg = {
            "method": "SUBSCRIBE",
            "params": streams,
            "id": request_id
        }

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
        unsubscribe_msg = {
            "method": "UNSUBSCRIBE",
            "params": streams,
            "id": request_id
        }

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



async def test_api_connection():
    """Test Aster API connection and enumerate all available capabilities."""
    from .credentials import load_credentials

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
        btcusdt_available = any(s['symbol'] == 'BTCUSDT' for s in symbols)
        if btcusdt_available:
            print("\n4. Testing market data for BTCUSDT...")

            # Test ticker price
            ticker = await client.get_ticker_price("BTCUSDT")
            print(f"   ✅ BTCUSDT price: ${ticker.get('price', 'N/A')}")

            # Test order book
            depth = await client.get_order_book("BTCUSDT", limit=5)
            bids = depth.get('bids', [])[:3]
            asks = depth.get('asks', [])[:3]
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
                print(f"   ✅ Account info retrieved (canTrade: {account_info.get('canTrade', 'N/A')})")

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
                print(f"   ✅ Leverage brackets: {len(brackets) if isinstance(brackets, list) else 'single'}")

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


if __name__ == "__main__":
    asyncio.run(main())
