"""
AI Symbol Resolver - Intelligent Cross-Platform Symbol Mapping

Dynamically resolves trading symbols across different exchanges.
Uses exchange APIs for primary matching, with LLM fallback for edge cases.

Part of the AI-Powered Resilience Layer for ACTS.
"""

import asyncio
import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# Cache TTL in seconds
SYMBOL_CACHE_TTL = 3600  # 1 hour


@dataclass
class SymbolInfo:
    """Information about a resolved symbol."""

    original: str
    resolved: str
    platform: str
    confidence: float  # 0.0 - 1.0
    method: str  # "exact", "fuzzy", "llm", "fallback"


class AISymbolResolver:
    """
    Intelligently resolves trading symbols across platforms.

    Resolution Strategy:
    1. Check cache for known mappings
    2. Query exchange API for exact match
    3. Apply fuzzy matching and normalization
    4. Use LLM for complex cases (token renames, meme coins)
    5. Fallback to original with warning
    """

    def __init__(self):
        # Cache: {platform: {generic_symbol: resolved_symbol}}
        self._cache: Dict[str, Dict[str, str]] = {}

        # Exchange-specific symbol lists (populated on first use)
        self._exchange_symbols: Dict[str, Set[str]] = {}
        self._exchange_symbols_time: Dict[str, float] = {}  # Cache timestamp

        # Common symbols that don't need verification (performance optimization)
        self._common_symbols = {
            "BTC",
            "ETH",
            "SOL",
            "DOGE",
            "XRP",
            "ADA",
            "AVAX",
            "LINK",
            "DOT",
            "MATIC",
            "UNI",
            "ATOM",
            "LTC",
            "BCH",
            "NEAR",
            "APT",
            "OP",
            "ARB",
            "SUI",
            "SEI",
            "TIA",
            "JUP",
            "WIF",
            "BONK",
            "PEPE",
            "SHIB",
        }

        # Known symbol mappings (common transformations)
        self._known_mappings = {
            "hyperliquid": {
                "BONK": "1000BONK",
                "SHIB": "1000SHIB",
                "PEPE": "1000PEPE",
                "FLOKI": "1000FLOKI",
                "LUNC": "1000LUNC",
            },
            "symphony": {
                # Symphony uses full addresses for some tokens
                # Add known mappings as discovered
            },
            "aster": {
                # Aster uses BTCUSDT format (no hyphen)
            },
        }

        # Common symbol format patterns
        self._format_transformations = {
            "hyperliquid": self._format_for_hyperliquid,
            "aster": self._format_for_aster,
            "symphony": self._format_for_symphony,
            "drift": self._format_for_drift,
        }

    async def resolve(
        self, generic_symbol: str, platform: str, use_llm_fallback: bool = True
    ) -> SymbolInfo:
        """
        Resolve a generic symbol to the platform-specific format.

        Args:
            generic_symbol: The symbol in generic format (e.g., "BTC-USDC", "ETH/USDT")
            platform: Target platform ("hyperliquid", "aster", "symphony", "drift")
            use_llm_fallback: Whether to use LLM for unresolved cases

        Returns:
            SymbolInfo with the resolved symbol and metadata
        """
        # Normalize input
        normalized = self._normalize_symbol(generic_symbol)

        # 1. Check cache
        if platform in self._cache and normalized in self._cache[platform]:
            return SymbolInfo(
                original=generic_symbol,
                resolved=self._cache[platform][normalized],
                platform=platform,
                confidence=1.0,
                method="cache",
            )

        # 2. Apply known mappings
        known = self._known_mappings.get(platform, {})
        base = self._extract_base(normalized)

        if base in known:
            resolved = known[base]
            self._update_cache(platform, normalized, resolved)
            return SymbolInfo(
                original=generic_symbol,
                resolved=resolved,
                platform=platform,
                confidence=0.95,
                method="known_mapping",
            )

        # 3. Apply format transformation
        format_fn = self._format_transformations.get(platform)
        if format_fn:
            transformed = format_fn(normalized)

            # OPTIMIZATION: Skip verification for common symbols (fast path)
            if base in self._common_symbols:
                self._update_cache(platform, normalized, transformed)
                return SymbolInfo(
                    original=generic_symbol,
                    resolved=transformed,
                    platform=platform,
                    confidence=0.9,
                    method="common_symbol",
                )

            # Verify against exchange symbols if available
            if await self._verify_symbol_exists(transformed, platform):
                self._update_cache(platform, normalized, transformed)
                return SymbolInfo(
                    original=generic_symbol,
                    resolved=transformed,
                    platform=platform,
                    confidence=0.85,
                    method="format_transform",
                )

        # 4. Fuzzy match against exchange symbols
        fuzzy_match = await self._fuzzy_match(normalized, platform)
        if fuzzy_match:
            self._update_cache(platform, normalized, fuzzy_match)
            return SymbolInfo(
                original=generic_symbol,
                resolved=fuzzy_match,
                platform=platform,
                confidence=0.7,
                method="fuzzy",
            )

        # 5. LLM fallback (for complex cases like token renames)
        if use_llm_fallback:
            llm_result = await self._llm_resolve(generic_symbol, platform)
            if llm_result:
                self._update_cache(platform, normalized, llm_result)
                return SymbolInfo(
                    original=generic_symbol,
                    resolved=llm_result,
                    platform=platform,
                    confidence=0.6,
                    method="llm",
                )

        # 6. Fallback: return transformed version with warning
        fallback = format_fn(normalized) if format_fn else normalized
        logger.warning(
            f"⚠️ Could not resolve symbol '{generic_symbol}' for {platform}, using '{fallback}'"
        )

        return SymbolInfo(
            original=generic_symbol,
            resolved=fallback,
            platform=platform,
            confidence=0.3,
            method="fallback",
        )

    def _normalize_symbol(self, symbol: str) -> str:
        """Normalize symbol to a standard format."""
        # Remove common separators and normalize
        symbol = symbol.upper()
        symbol = re.sub(r"[-/_]", "-", symbol)  # Standardize separators
        symbol = re.sub(r"PERP$", "", symbol)  # Remove PERP suffix
        return symbol.strip()

    def _extract_base(self, symbol: str) -> str:
        """Extract base asset from a pair symbol."""
        # Handle formats like BTC-USDC, BTCUSDT, BTC/USD
        parts = re.split(r"[-/]", symbol)
        if parts:
            return parts[0]

        # Try to extract from concatenated format
        for quote in ["USDC", "USDT", "USD", "BUSD"]:
            if symbol.endswith(quote):
                return symbol[: -len(quote)]

        return symbol

    def _format_for_hyperliquid(self, symbol: str) -> str:
        """Format symbol for Hyperliquid (just base asset)."""
        return self._extract_base(symbol)

    def _format_for_aster(self, symbol: str) -> str:
        """Format symbol for Aster (BTCUSDT format)."""
        base = self._extract_base(symbol)
        return f"{base}USDT"

    def _format_for_symphony(self, symbol: str) -> str:
        """Format symbol for Symphony (BTC-USDC format)."""
        base = self._extract_base(symbol)
        return f"{base}-USDC"

    def _format_for_drift(self, symbol: str) -> str:
        """Format symbol for Drift (SOL-PERP format)."""
        base = self._extract_base(symbol)
        return f"{base}-PERP"

    async def _verify_symbol_exists(self, symbol: str, platform: str) -> bool:
        """Verify that a symbol exists on the exchange."""
        symbols = await self._get_exchange_symbols(platform)
        return symbol in symbols or symbol.lower() in {s.lower() for s in symbols}

    async def _get_exchange_symbols(self, platform: str) -> Set[str]:
        """Get list of supported symbols from exchange with TTL."""
        # Check cache with TTL
        if platform in self._exchange_symbols:
            cache_age = time.time() - self._exchange_symbols_time.get(platform, 0)
            if cache_age < SYMBOL_CACHE_TTL:
                return self._exchange_symbols[platform]

        try:
            if platform == "hyperliquid":
                symbols = await self._fetch_hyperliquid_symbols()
            elif platform == "aster":
                symbols = await self._fetch_aster_symbols()
            else:
                symbols = set()

            self._exchange_symbols[platform] = symbols
            self._exchange_symbols_time[platform] = time.time()
            return symbols

        except Exception as e:
            logger.warning(f"Failed to fetch symbols for {platform}: {e}")
            return set()

    async def _fetch_hyperliquid_symbols(self) -> Set[str]:
        """Fetch supported symbols from Hyperliquid."""
        import httpx

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "https://api.hyperliquid.xyz/info", json={"type": "meta"}, timeout=10
                )
                data = resp.json()
                universe = data.get("universe", [])
                return {asset.get("name") for asset in universe if asset.get("name")}
        except Exception as e:
            logger.warning(f"Failed to fetch HL symbols: {e}")
            return set()

    async def _fetch_aster_symbols(self) -> Set[str]:
        """Fetch supported symbols from Aster."""
        import httpx

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    "https://fapi.aster.finance/fapi/v1/exchangeInfo", timeout=10
                )
                data = resp.json()
                return {s.get("symbol") for s in data.get("symbols", []) if s.get("symbol")}
        except Exception as e:
            logger.warning(f"Failed to fetch Aster symbols: {e}")
            return set()

    async def _fuzzy_match(self, symbol: str, platform: str) -> Optional[str]:
        """Perform fuzzy matching against exchange symbols."""
        symbols = await self._get_exchange_symbols(platform)
        base = self._extract_base(symbol)

        # Try exact base match
        for s in symbols:
            if s.upper() == base or s.upper().startswith(base):
                return s

        # Try contains match
        for s in symbols:
            if base in s.upper():
                return s

        return None

    async def _llm_resolve(self, symbol: str, platform: str) -> Optional[str]:
        """Use LLM to resolve complex symbol mappings."""
        try:
            # Import Vertex AI client
            from cloud_trader.vertex_ai_client import get_vertex_client

            client = get_vertex_client()
            if not client:
                return None

            prompt = f"""You are a cryptocurrency trading symbol resolver.

Given the generic trading symbol "{symbol}", what is the correct symbol format for the {platform} exchange?

Rules:
- Hyperliquid: Uses just the base asset (e.g., "BTC", "ETH", "1000BONK" for meme coins)
- Aster: Uses BTCUSDT format (concatenated with USDT)
- Symphony: Uses BTC-USDC format (hyphenated with USDC)
- Drift: Uses SOL-PERP format (hyphenated with PERP for perpetuals)

Respond with ONLY the resolved symbol, nothing else. If you cannot determine the correct symbol, respond with "UNKNOWN".
"""

            response = await client.generate_content(prompt)
            result = response.text.strip().upper()

            if result and result != "UNKNOWN":
                logger.info(f"🤖 LLM resolved '{symbol}' -> '{result}' for {platform}")
                return result

        except Exception as e:
            logger.warning(f"LLM symbol resolution failed: {e}")

        return None

    def _update_cache(self, platform: str, original: str, resolved: str) -> None:
        """Update the symbol cache."""
        if platform not in self._cache:
            self._cache[platform] = {}
        self._cache[platform][original] = resolved

    async def warm_cache(self, symbols: List[str], platforms: List[str]) -> None:
        """Pre-resolve a list of symbols for given platforms."""
        logger.info(
            f"🔥 Warming symbol cache for {len(symbols)} symbols on {len(platforms)} platforms"
        )

        tasks = []
        for symbol in symbols:
            for platform in platforms:
                tasks.append(self.resolve(symbol, platform, use_llm_fallback=False))

        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("✅ Symbol cache warmed")


# Global instance
_resolver: Optional[AISymbolResolver] = None


def get_symbol_resolver() -> AISymbolResolver:
    """Get global AISymbolResolver instance."""
    global _resolver
    if _resolver is None:
        _resolver = AISymbolResolver()
    return _resolver


async def resolve_symbol(generic_symbol: str, platform: str, use_llm_fallback: bool = True) -> str:
    """Convenience function to resolve a symbol."""
    resolver = get_symbol_resolver()
    result = await resolver.resolve(generic_symbol, platform, use_llm_fallback)
    return result.resolved
