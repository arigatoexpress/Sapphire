"""
Precision Normalizer - Universal Order Normalization Layer

Ensures all orders meet exchange precision requirements (tick size, lot size)
before submission. Caches exchange info to minimize API calls.

Part of the AI-Powered Resilience Layer for ACTS.
"""

import asyncio
import logging
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class ExchangeInfo:
    """Exchange-specific symbol information."""

    symbol: str
    platform: str
    tick_size: Decimal  # Price increment
    lot_size: Decimal  # Quantity increment
    min_notional: Decimal  # Minimum order value
    min_qty: Decimal
    max_qty: Decimal
    price_precision: int
    qty_precision: int


class PrecisionNormalizer:
    """
    Ensures all orders meet exchange precision requirements.

    Features:
    - Caches exchange info to minimize API calls
    - Normalizes prices to tick size
    - Normalizes quantities to lot size
    - Validates against min/max constraints
    - Platform-agnostic (works with any exchange)
    """

    def __init__(self):
        # Cache: {platform: {symbol: ExchangeInfo}}
        self._cache: Dict[str, Dict[str, ExchangeInfo]] = {}
        self._cache_ttl = 3600  # 1 hour
        self._cache_timestamps: Dict[str, float] = {}
        self._lock = asyncio.Lock()

        # Default fallbacks when exchange info unavailable
        self._defaults = {
            "hyperliquid": {
                "tick_size": Decimal("0.01"),
                "lot_size": Decimal("0.001"),
                "min_notional": Decimal("10"),
            },
            "aster": {
                "tick_size": Decimal("0.01"),
                "lot_size": Decimal("0.001"),
                "min_notional": Decimal("5"),
            },
            "symphony": {
                "tick_size": Decimal("0.0001"),
                "lot_size": Decimal("0.0001"),
                "min_notional": Decimal("5"),
            },
            "drift": {
                "tick_size": Decimal("0.001"),
                "lot_size": Decimal("0.01"),
                "min_notional": Decimal("10"),
            },
        }

    async def normalize_order(
        self, symbol: str, platform: str, price: float, quantity: float, side: str = "BUY"
    ) -> Dict[str, Any]:
        """
        Normalize an order to meet exchange requirements.

        Returns:
            {
                "price": normalized_price,
                "quantity": normalized_quantity,
                "valid": bool,
                "warnings": list[str],
                "original": {"price": ..., "quantity": ...}
            }
        """
        warnings = []

        try:
            info = await self._get_exchange_info(symbol, platform)
        except Exception as e:
            logger.warning(f"⚠️ Could not fetch exchange info for {symbol}@{platform}: {e}")
            info = self._get_default_info(symbol, platform)
            warnings.append(f"Using default precision (exchange info unavailable)")

        price_dec = Decimal(str(price))
        qty_dec = Decimal(str(quantity))

        # Normalize price to tick size
        normalized_price = self._round_to_tick(price_dec, info.tick_size)
        if normalized_price != price_dec:
            warnings.append(
                f"Price adjusted from {price} to {normalized_price} (tick: {info.tick_size})"
            )

        # Normalize quantity to lot size
        normalized_qty = self._round_to_lot(qty_dec, info.lot_size)
        if normalized_qty != qty_dec:
            warnings.append(
                f"Quantity adjusted from {quantity} to {normalized_qty} (lot: {info.lot_size})"
            )

        # Validate constraints
        valid = True

        # Check minimum quantity
        if normalized_qty < info.min_qty:
            warnings.append(f"Quantity {normalized_qty} below minimum {info.min_qty}")
            valid = False

        # Check notional value
        notional = normalized_price * normalized_qty
        if notional < info.min_notional:
            warnings.append(f"Notional ${notional} below minimum ${info.min_notional}")
            valid = False

        result = {
            "price": float(normalized_price),
            "quantity": float(normalized_qty),
            "valid": valid,
            "warnings": warnings,
            "original": {"price": price, "quantity": quantity},
            "exchange_info": {
                "tick_size": float(info.tick_size),
                "lot_size": float(info.lot_size),
                "min_notional": float(info.min_notional),
            },
        }

        if warnings:
            logger.info(f"📐 Normalized {symbol}@{platform}: {warnings}")

        return result

    def _round_to_tick(self, price: Decimal, tick_size: Decimal) -> Decimal:
        """Round price down to nearest tick size."""
        if tick_size <= 0:
            return price
        return (price / tick_size).quantize(Decimal("1"), rounding=ROUND_DOWN) * tick_size

    def _round_to_lot(self, quantity: Decimal, lot_size: Decimal) -> Decimal:
        """Round quantity down to nearest lot size."""
        if lot_size <= 0:
            return quantity
        return (quantity / lot_size).quantize(Decimal("1"), rounding=ROUND_DOWN) * lot_size

    async def _get_exchange_info(self, symbol: str, platform: str) -> ExchangeInfo:
        """
        Get exchange info from cache or fetch from exchange.
        """
        import time

        # Check cache
        cache_key = f"{platform}:{symbol}"
        if platform in self._cache and symbol in self._cache[platform]:
            cache_time = self._cache_timestamps.get(cache_key, 0)
            if time.time() - cache_time < self._cache_ttl:
                return self._cache[platform][symbol]

        # Fetch from exchange
        info = await self._fetch_exchange_info(symbol, platform)

        # Update cache
        async with self._lock:
            if platform not in self._cache:
                self._cache[platform] = {}
            self._cache[platform][symbol] = info
            self._cache_timestamps[cache_key] = time.time()

        return info

    async def _fetch_exchange_info(self, symbol: str, platform: str) -> ExchangeInfo:
        """
        Fetch exchange info from the actual exchange API.
        """
        if platform == "hyperliquid":
            return await self._fetch_hyperliquid_info(symbol)
        elif platform == "aster":
            return await self._fetch_aster_info(symbol)
        elif platform == "symphony":
            return self._get_default_info(symbol, platform)  # Symphony doesn't expose this
        else:
            return self._get_default_info(symbol, platform)

    async def _fetch_hyperliquid_info(self, symbol: str) -> ExchangeInfo:
        """Fetch symbol info from Hyperliquid API."""
        import httpx

        try:
            async with httpx.AsyncClient() as client:
                # Hyperliquid meta endpoint
                resp = await client.post(
                    "https://api.hyperliquid.xyz/info", json={"type": "meta"}, timeout=10
                )
                data = resp.json()

                # Find the symbol in universe
                universe = data.get("universe", [])
                for asset in universe:
                    if asset.get("name") == symbol.replace("-USDC", "").replace("-USD", ""):
                        sz_decimals = asset.get("szDecimals", 4)

                        return ExchangeInfo(
                            symbol=symbol,
                            platform="hyperliquid",
                            tick_size=Decimal("0.01"),  # HL uses price precision dynamically
                            lot_size=Decimal(10) ** Decimal(-sz_decimals),
                            min_notional=Decimal("10"),
                            min_qty=Decimal(10) ** Decimal(-sz_decimals),
                            max_qty=Decimal("1000000"),
                            price_precision=2,
                            qty_precision=sz_decimals,
                        )
        except Exception as e:
            logger.warning(f"Failed to fetch HL info for {symbol}: {e}")

        return self._get_default_info(symbol, "hyperliquid")

    async def _fetch_aster_info(self, symbol: str) -> ExchangeInfo:
        """Fetch symbol info from Aster/Binance-style API."""
        import httpx

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    "https://fapi.aster.finance/fapi/v1/exchangeInfo", timeout=10
                )
                data = resp.json()

                for sym_info in data.get("symbols", []):
                    if sym_info.get("symbol") == symbol.replace("-", ""):
                        filters = {f["filterType"]: f for f in sym_info.get("filters", [])}

                        price_filter = filters.get("PRICE_FILTER", {})
                        lot_filter = filters.get("LOT_SIZE", {})
                        notional_filter = filters.get("MIN_NOTIONAL", {})

                        return ExchangeInfo(
                            symbol=symbol,
                            platform="aster",
                            tick_size=Decimal(price_filter.get("tickSize", "0.01")),
                            lot_size=Decimal(lot_filter.get("stepSize", "0.001")),
                            min_notional=Decimal(notional_filter.get("minNotional", "5")),
                            min_qty=Decimal(lot_filter.get("minQty", "0.001")),
                            max_qty=Decimal(lot_filter.get("maxQty", "1000000")),
                            price_precision=sym_info.get("pricePrecision", 2),
                            qty_precision=sym_info.get("quantityPrecision", 3),
                        )
        except Exception as e:
            logger.warning(f"Failed to fetch Aster info for {symbol}: {e}")

        return self._get_default_info(symbol, "aster")

    def _get_default_info(self, symbol: str, platform: str) -> ExchangeInfo:
        """Get default exchange info when API is unavailable."""
        defaults = self._defaults.get(platform, self._defaults["aster"])

        return ExchangeInfo(
            symbol=symbol,
            platform=platform,
            tick_size=defaults["tick_size"],
            lot_size=defaults["lot_size"],
            min_notional=defaults["min_notional"],
            min_qty=defaults["lot_size"],
            max_qty=Decimal("1000000"),
            price_precision=4,
            qty_precision=4,
        )

    async def warm_cache(self, symbols: list, platform: str) -> None:
        """Pre-populate cache for a list of symbols."""
        logger.info(f"🔥 Warming precision cache for {len(symbols)} symbols on {platform}")

        tasks = [self._get_exchange_info(s, platform) for s in symbols]
        await asyncio.gather(*tasks, return_exceptions=True)

        logger.info(f"✅ Precision cache warmed for {platform}")


# Global instance
_normalizer: Optional[PrecisionNormalizer] = None


def get_precision_normalizer() -> PrecisionNormalizer:
    """Get global PrecisionNormalizer instance."""
    global _normalizer
    if _normalizer is None:
        _normalizer = PrecisionNormalizer()
    return _normalizer


async def normalize_order(
    symbol: str, platform: str, price: float, quantity: float, side: str = "BUY"
) -> Dict[str, Any]:
    """Convenience function to normalize an order."""
    normalizer = get_precision_normalizer()
    return await normalizer.normalize_order(symbol, platform, price, quantity, side)
