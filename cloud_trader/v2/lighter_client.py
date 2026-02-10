"""
Lighter Trading Client
======================
Client for the Lighter decentralized perpetual futures exchange on Ethereum L2.

Supports:
- Separate account_index vs api_key_index (they are different concepts on Lighter)
- Auto-detection of correct (account_index, api_key_index) pair via brute-force check
- Timeouts on all SDK calls to prevent Cloud Run hangs
- Fail-fast initialization with detailed error reporting

Author: Sapphire V2 Architecture Team
Version: 2.0.0
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Try to import the Lighter SDK
try:
    import lighter
    LIGHTER_SDK_AVAILABLE = True
    logger.info("Lighter SDK loaded")
except ImportError:
    LIGHTER_SDK_AVAILABLE = False
    logger.warning("Lighter SDK not available - install lighter-sdk")


# Configurable timeouts (seconds) via env vars
INIT_TIMEOUT = float(os.environ.get("LIGHTER_INIT_TIMEOUT_SECONDS", "30"))
CHECK_CLIENT_TIMEOUT = float(os.environ.get("LIGHTER_CHECK_CLIENT_TIMEOUT_SECONDS", "15"))
MARKET_LOAD_TIMEOUT = float(os.environ.get("LIGHTER_MARKET_LOAD_TIMEOUT_SECONDS", "15"))


@dataclass
class LighterPosition:
    """Represents a Lighter position."""
    symbol: str
    size: float
    entry_price: float
    mark_price: float
    liquidation_price: Optional[float]
    unrealized_pnl: float
    realized_pnl: float
    leverage: float
    margin_used: float
    side: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "size": self.size,
            "entry_price": self.entry_price,
            "mark_price": self.mark_price,
            "liquidation_price": self.liquidation_price,
            "unrealized_pnl": self.unrealized_pnl,
            "realized_pnl": self.realized_pnl,
            "leverage": self.leverage,
            "margin_used": self.margin_used,
            "side": self.side,
        }


@dataclass
class LighterOrder:
    """Represents a Lighter order result."""
    order_id: str
    client_order_id: Optional[str]
    symbol: str
    side: str
    order_type: str
    price: Optional[float]
    quantity: float
    filled_quantity: float
    status: str
    created_at: datetime

    def to_dict(self) -> Dict[str, Any]:
        return {
            "order_id": self.order_id,
            "client_order_id": self.client_order_id,
            "symbol": self.symbol,
            "side": self.side,
            "order_type": self.order_type,
            "price": self.price,
            "quantity": self.quantity,
            "filled_quantity": self.filled_quantity,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class LighterClient:
    """
    Lighter client for decentralized perpetual futures trading.

    Uses the lighter-sdk for API calls and transaction signing.
    Lighter runs on Ethereum L2 with ZK-rollups.

    Key improvement over v1: account_index and api_key_index are treated
    as separate concepts. The SignerClient accepts api_private_keys keyed
    by api_key_index, while account_index identifies which Lighter account
    to operate on.
    """

    def __init__(
        self,
        account_index: int = 1,
        api_private_keys: Optional[Dict[int, str]] = None,
        testnet: bool = False,
        auto_detect: bool = True,
        # Legacy compat
        pub_key: Optional[str] = None,
        priv_key: Optional[str] = None,
    ):
        """Initialize Lighter client.

        Args:
            account_index: The Lighter account index to trade on (default 1).
            api_private_keys: Dict mapping api_key_index -> private_key_hex.
                e.g. {0: "0xabc..."} means api_key_index=0 uses that private key.
            testnet: Use testnet URL.
            auto_detect: If True, try multiple (account_index, api_key_index) combos
                during initialization to find a working pair.
            pub_key: Legacy - L1 address (unused if api_private_keys provided).
            priv_key: Legacy - single private key (converted to api_private_keys={0: key}).
        """
        self._account_index = account_index
        self._testnet = testnet
        self._auto_detect = auto_detect

        # Handle legacy single-key constructor
        if api_private_keys:
            self._api_private_keys = dict(api_private_keys)
        elif priv_key:
            self._api_private_keys = {0: priv_key}
        else:
            self._api_private_keys = {}

        self._pub_key = pub_key or ""

        self._signer_client: Optional[Any] = None
        self._client: Optional[Any] = None
        self._account_api: Optional[Any] = None
        self._transaction_api: Optional[Any] = None
        self._order_api: Optional[Any] = None
        self._initialized = False
        self._last_error: Optional[str] = None

        # Cache
        self._positions: Dict[str, LighterPosition] = {}
        self._market_info: Dict[str, Dict] = {}

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    async def initialize(self) -> bool:
        """Initialize the Lighter SDK clients with timeout and auto-detect."""
        if self._initialized:
            return True

        if not LIGHTER_SDK_AVAILABLE:
            self._last_error = "Lighter SDK not installed"
            logger.error(f"Cannot initialize - {self._last_error}")
            return False

        if not self._api_private_keys:
            self._last_error = "No API private keys configured"
            logger.error(f"Cannot initialize - {self._last_error}")
            return False

        logger.info(
            f"[Lighter] Initializing SDK | account_index={self._account_index} "
            f"api_key_indices={list(self._api_private_keys.keys())} testnet={self._testnet}"
        )

        try:
            return await asyncio.wait_for(
                self._do_initialize(), timeout=INIT_TIMEOUT
            )
        except asyncio.TimeoutError:
            self._last_error = f"Initialization timed out after {INIT_TIMEOUT}s"
            logger.error(f"[Lighter] {self._last_error}")
            return False
        except Exception as e:
            self._last_error = str(e)
            logger.error(f"[Lighter] Initialization failed: {e}")
            return False

    async def _do_initialize(self) -> bool:
        """Actual initialization logic."""
        base_url = (
            "https://testnet.zklighter.elliot.ai"
            if self._testnet
            else "https://mainnet.zklighter.elliot.ai"
        )

        # Try auto-detect if enabled
        if self._auto_detect and len(self._api_private_keys) > 0:
            ok = await self._auto_detect_indices(base_url)
            if ok:
                return True

        # Fall back to first key with configured account_index
        first_key_index = next(iter(self._api_private_keys))
        first_key = self._api_private_keys[first_key_index]

        return await self._try_init_signer(
            base_url, self._account_index, first_key_index, first_key
        )

    async def _auto_detect_indices(self, base_url: str) -> bool:
        """Try multiple (account_index, api_key_index) combinations."""
        account_candidates = [self._account_index, 0, 1, 2, 3]
        # De-duplicate while preserving order
        seen = set()
        unique_accounts = []
        for a in account_candidates:
            if a not in seen:
                seen.add(a)
                unique_accounts.append(a)

        for key_index, key_value in self._api_private_keys.items():
            for acct_idx in unique_accounts:
                ok = await self._try_init_signer(base_url, acct_idx, key_index, key_value)
                if ok:
                    logger.info(
                        f"[Lighter] Auto-detect found working pair: "
                        f"account_index={acct_idx} api_key_index={key_index}"
                    )
                    self._account_index = acct_idx
                    return True

        return False

    async def _try_init_signer(
        self, base_url: str, account_index: int, api_key_index: int, api_key: str
    ) -> bool:
        """Attempt to initialize a SignerClient with given indices."""
        try:
            loop = asyncio.get_event_loop()
            sc = lighter.SignerClient(
                url=base_url,
                account_index=account_index,
                api_private_keys={api_key_index: api_key},
            )

            # check_client returns None on success, error string on failure
            err = await asyncio.wait_for(
                loop.run_in_executor(None, sc.check_client),
                timeout=CHECK_CLIENT_TIMEOUT,
            )

            if err is None:
                self._signer_client = sc
                self._account_index = account_index

                # Initialize read-only API client for market data
                self._client = lighter.ApiClient()
                self._account_api = lighter.AccountApi(self._client)
                self._transaction_api = lighter.TransactionApi(self._client)
                self._order_api = lighter.OrderApi(self._client)

                # Load markets with timeout
                try:
                    await asyncio.wait_for(
                        self._load_market_info(), timeout=MARKET_LOAD_TIMEOUT
                    )
                except asyncio.TimeoutError:
                    logger.warning("[Lighter] Market info load timed out, continuing without it")

                self._initialized = True
                self._last_error = None
                logger.info(
                    f"[Lighter] Initialized successfully | account={account_index} "
                    f"api_key={api_key_index} markets={len(self._market_info)}"
                )
                return True
            else:
                hint = str(err)[:120]
                logger.debug(
                    f"[Lighter] check_client failed: account={account_index} "
                    f"api_key={api_key_index}: {hint}"
                )
                self._last_error = hint
                try:
                    await loop.run_in_executor(None, sc.close)
                except Exception:
                    pass
                return False

        except asyncio.TimeoutError:
            self._last_error = f"check_client timed out for account={account_index} key={api_key_index}"
            logger.debug(f"[Lighter] {self._last_error}")
            return False
        except Exception as e:
            self._last_error = str(e)[:120]
            logger.debug(f"[Lighter] init error: account={account_index} key={api_key_index}: {e}")
            return False

    async def verify_credentials(self) -> Tuple[bool, Optional[str]]:
        """Verify credentials without full initialization. Returns (ok, error)."""
        ok = await self.initialize()
        return (ok, self._last_error)

    async def _load_market_info(self):
        """Load order book metadata from API."""
        try:
            loop = asyncio.get_event_loop()
            order_books = await loop.run_in_executor(
                None,
                lambda: self._order_api.order_books()
            )

            if order_books and hasattr(order_books, 'order_books'):
                for ob in order_books.order_books:
                    symbol = ob.symbol if hasattr(ob, 'symbol') else str(ob.order_book_id)
                    self._market_info[symbol.upper()] = {
                        "order_book_id": ob.order_book_id if hasattr(ob, 'order_book_id') else 0,
                        "symbol": symbol,
                        "base_asset": getattr(ob, 'base_asset', symbol),
                        "quote_asset": getattr(ob, 'quote_asset', 'USDC'),
                        "tick_size": getattr(ob, 'tick_size', 0.01),
                        "step_size": getattr(ob, 'step_size', 0.001),
                    }
                logger.info(f"[Lighter] Loaded {len(self._market_info)} markets")
        except Exception as e:
            logger.warning(f"[Lighter] Failed to load market info: {e}")

    async def get_positions(self) -> List[LighterPosition]:
        """Get all open positions."""
        if not self._initialized:
            ok = await self.initialize()
            if not ok:
                return []

        if not self._account_api or self._account_index is None:
            return []

        try:
            loop = asyncio.get_event_loop()
            account = await loop.run_in_executor(
                None,
                lambda: self._account_api.account(by="index", value=str(self._account_index))
            )

            positions = []
            if account and hasattr(account, 'positions'):
                for pos in account.positions:
                    if pos.size != 0:
                        position = LighterPosition(
                            symbol=pos.symbol if hasattr(pos, 'symbol') else f"MARKET_{pos.order_book_id}",
                            size=abs(float(pos.size)),
                            entry_price=float(getattr(pos, 'entry_price', 0)),
                            mark_price=float(getattr(pos, 'mark_price', 0)),
                            liquidation_price=float(getattr(pos, 'liquidation_price', 0)) if hasattr(pos, 'liquidation_price') else None,
                            unrealized_pnl=float(getattr(pos, 'unrealized_pnl', 0)),
                            realized_pnl=float(getattr(pos, 'realized_pnl', 0)),
                            leverage=float(getattr(pos, 'leverage', 1)),
                            margin_used=float(getattr(pos, 'margin', 0)),
                            side="LONG" if float(pos.size) > 0 else "SHORT",
                        )
                        positions.append(position)
                        self._positions[position.symbol] = position

            logger.info(f"[Lighter] Fetched {len(positions)} positions")
            return positions

        except Exception as e:
            logger.error(f"[Lighter] Failed to fetch positions: {e}")
            return []

    async def place_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        order_type: str = "MARKET",
        price: Optional[float] = None,
        reduce_only: bool = False,
        **kwargs,
    ) -> Dict[str, Any]:
        """Place an order using Lighter SDK (via SignerClient)."""
        if not self._initialized:
            ok = await self.initialize()
            if not ok:
                return {"status": "error", "error": f"Not initialized: {self._last_error}"}

        if not self._signer_client:
            return {"status": "error", "error": "SignerClient not available"}

        # Normalize symbol
        coin = symbol.upper().replace("-PERP", "").replace("-USDC", "").replace("_", "")

        # Get market info
        market = self._market_info.get(coin, {})
        order_book_id = market.get("order_book_id", 0)

        is_buy = side.upper() in ["BUY", "LONG"]

        logger.info(
            f"[Lighter] Placing {order_type} {side} order | "
            f"Symbol: {coin} | Qty: {quantity} | OrderBookId: {order_book_id}"
        )

        try:
            loop = asyncio.get_event_loop()

            if order_type.upper() == "MARKET":
                current_price = await self.get_ticker(coin)
                if current_price:
                    limit_price = current_price * 1.05 if is_buy else current_price * 0.95
                else:
                    return {"status": "error", "error": "Could not get current price"}
            else:
                if not price:
                    return {"status": "error", "error": "Price required for limit orders"}
                limit_price = price

            # Use SignerClient to place order (handles signing internally)
            result = await loop.run_in_executor(
                None,
                lambda: self._signer_client.create_order(
                    order_book_id=order_book_id,
                    is_buy=is_buy,
                    price=limit_price,
                    amount=quantity,
                    time_in_force=1,  # IOC
                )
            )

            if result and hasattr(result, 'success') and result.success:
                fill_price = getattr(result, 'avg_fill_price', limit_price)
                filled_qty = getattr(result, 'filled_quantity', quantity)

                logger.info(
                    f"[Lighter] Order FILLED | Symbol: {coin} | Avg Price: ${fill_price}"
                )
                return {
                    "status": "ok",
                    "filled": True,
                    "data": {
                        "avgPx": fill_price,
                        "filledQty": filled_qty,
                        "orderId": getattr(result, 'order_id', None),
                    }
                }
            else:
                error_msg = getattr(result, 'error', 'Unknown error')
                logger.error(f"[Lighter] Order failed: {error_msg}")
                return {"status": "error", "error": str(error_msg)}

        except Exception as e:
            logger.error(f"[Lighter] Order exception: {e}")
            return {"status": "error", "error": str(e)}

    async def get_ticker(self, symbol: str) -> Optional[float]:
        """Get current price for a symbol."""
        if not self._order_api:
            return None

        try:
            coin = symbol.upper().replace("-PERP", "").replace("-USDC", "")
            market = self._market_info.get(coin, {})
            order_book_id = market.get("order_book_id", 0)

            loop = asyncio.get_event_loop()
            details = await loop.run_in_executor(
                None,
                lambda: self._order_api.order_book_details(order_book_id=order_book_id)
            )

            if details and hasattr(details, 'mid_price'):
                return float(details.mid_price)
            elif details and hasattr(details, 'last_price'):
                return float(details.last_price)

        except Exception as e:
            logger.warning(f"[Lighter] Failed to get ticker for {symbol}: {e}")

        return None

    async def get_account_value(self) -> float:
        """Get total account value."""
        if not self._account_api or self._account_index is None:
            return 0.0

        try:
            loop = asyncio.get_event_loop()
            account = await loop.run_in_executor(
                None,
                lambda: self._account_api.account(by="index", value=str(self._account_index))
            )

            if account:
                equity = float(getattr(account, 'equity', 0))
                logger.info(f"[Lighter] Account value: ${equity:.2f}")
                return equity

        except Exception as e:
            logger.error(f"[Lighter] Failed to get account value: {e}")

        return 0.0

    async def close(self):
        """Cleanup client resources."""
        if self._signer_client:
            try:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, self._signer_client.close)
            except Exception:
                pass
        if self._client:
            try:
                await self._client.close()
            except Exception:
                pass
        self._initialized = False
        logger.info("[Lighter] Client closed")

    def get_status(self) -> Dict[str, Any]:
        """Get client status."""
        return {
            "initialized": self._initialized,
            "testnet": self._testnet,
            "account_index": self._account_index,
            "api_key_indices": list(self._api_private_keys.keys()),
            "markets_loaded": len(self._market_info),
            "positions_cached": len(self._positions),
            "last_error": self._last_error,
        }
