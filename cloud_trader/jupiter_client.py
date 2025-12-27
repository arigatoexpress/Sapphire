"""
Jupiter Ultra Swap API Integration for Solana DEX Aggregation
Documentation: https://dev.jup.ag/docs/ultra

Features:
- Best price routing across all Solana DEXs
- Automatic slippage protection
- Priority fee optimization
- No RPC required (Jupiter handles everything)
"""

import base64
import logging
import os
from typing import Any, Dict, List, Optional

import httpx
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.transaction import VersionedTransaction

from .logger import get_logger

logger = get_logger(__name__)

# Jupiter API Configuration
JUPITER_API_BASE = "https://api.jup.ag"
JUPITER_API_VERSION = "v6"


class JupiterSwapClient:
    """
    Jupiter Ultra Swap API client for Solana token swaps.

    Handles:
    - Quote fetching with best routes
    - Transaction building
    - Swap execution via Jupiter's RPC-less architecture
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Jupiter Ultra client.
        """
        self.api_key = api_key or os.getenv("JUPITER_API_KEY")
        self.base_url = "https://api.jup.ag/ultra/v1"

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Sapphire-AI/1.0",
            "Accept": "application/json",
        }

        if self.api_key:
            headers["x-api-key"] = self.api_key

        self.client = httpx.AsyncClient(base_url=self.base_url, headers=headers, timeout=30.0)

    async def get_order(
        self,
        input_mint: str,
        output_mint: str,
        amount: int,
        taker: Optional[str] = None,
        slippage_bps: int = 50,
    ) -> Dict[str, Any]:
        """
        Get an Ultra Order (Quote + Transaction).
        """
        params = {
            "inputMint": input_mint,
            "outputMint": output_mint,
            "amount": str(amount),
            "slippageBps": slippage_bps,
        }
        if taker:
            params["taker"] = taker

        logger.info(f"Fetching Ultra Order: {input_mint[:8]}... -> {output_mint[:8]}...")
        try:
            response = await self.client.get("/order", params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.error(f"Jupiter Ultra order error: {e}")
            raise

    async def execute_swap(
        self,
        input_mint: str,
        output_mint: str,
        amount: int,
        user_keypair: Keypair,
        slippage_bps: int = 50,
    ) -> Dict[str, Any]:
        """
        Execute an Ultra Swap (Get Order -> Sign -> Execute).
        """
        taker_pubkey = str(user_keypair.pubkey())

        # 1. Get Order with Transaction
        order = await self.get_order(
            input_mint=input_mint,
            output_mint=output_mint,
            amount=amount,
            taker=taker_pubkey,
            slippage_bps=slippage_bps,
        )

        if not order.get("transaction"):
            raise ValueError(
                f"No transaction returned in order. Error: {order.get('errorCode')} - {order.get('errorMessage')}"
            )

        # 2. Sign Transaction
        tx_bytes = base64.b64decode(order["transaction"])
        tx = VersionedTransaction.from_bytes(tx_bytes)
        tx.sign([user_keypair])
        signed_tx_base64 = base64.b64encode(bytes(tx)).decode("utf-8")

        # 3. Execute
        logger.info("Submitting signed Ultra transaction...")
        try:
            response = await self.client.post(
                "/execute",
                json={
                    "transaction": signed_tx_base64,
                    "requestId": order.get("requestId"),  # Required for execute
                },
            )
            response.raise_for_status()
            result = response.json()
            logger.info(f"Ultra Swap Executed! Signature: {result.get('signature')}")
            return result
        except httpx.HTTPError as e:
            logger.error(f"Jupiter execute error: {e}")
            raise

    async def get_tokens(self, tags: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        Get list of supported tokens.

        Args:
            tags: Optional filter by tags (e.g. ["verified", "community"])

        Returns:
            List of token metadata
        """
        try:
            # Jupiter token list endpoint
            token_list_url = "https://token.jup.ag/all"

            async with httpx.AsyncClient() as client:
                response = await client.get(token_list_url)
                response.raise_for_status()
                tokens = response.json()

            if tags:
                # Filter by tags if provided
                tokens = [t for t in tokens if any(tag in t.get("tags", []) for tag in tags)]

            logger.info(f"Fetched {len(tokens)} tokens from Jupiter")
            return tokens
        except httpx.HTTPError as e:
            logger.error(f"Token list fetch error: {e}")
            raise

    async def get_price(
        self,
        token_mint: str,
        vs_token: str = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
    ) -> float:
        """
        Get current token price.

        Args:
            token_mint: Token mint address to price
            vs_token: Quote token (default: USDC)

        Returns:
            Price as float
        """
        try:
            # Use Jupiter price API
            price_url = f"https://price.jup.ag/v4/price?ids={token_mint}&vsToken={vs_token}"

            async with httpx.AsyncClient() as client:
                response = await client.get(price_url)
                response.raise_for_status()
                price_data = response.json()

            price = price_data.get("data", {}).get(token_mint, {}).get("price", 0)
            return float(price)
        except Exception as e:
            logger.warning(f"Jupiter Price API failed ({e}). Attempting CoinGecko fallback...")
            try:
                # CoinGecko Fallback
                async with httpx.AsyncClient() as client:
                    resp = await client.get(
                        "https://api.coingecko.com/api/v3/simple/price",
                        params={"ids": "solana", "vs_currencies": "usd"},
                        timeout=5.0,
                    )
                    data = resp.json()
                    price = float(data.get("solana", {}).get("usd", 0.0))
                    logger.info(f"✅ CoinGecko Fallback: SOL @ ${price}")
                    return price
            except Exception as e2:
                logger.error(f"Price fetch fallback failed: {e2}")
                return 0.0


# Singleton instance
_jupiter_client: Optional[JupiterSwapClient] = None


def get_jupiter_client(api_key: Optional[str] = None) -> JupiterSwapClient:
    """Get or create Jupiter client singleton."""
    global _jupiter_client
    if _jupiter_client is None:
        _jupiter_client = JupiterSwapClient(api_key=api_key)
    return _jupiter_client


# Common Solana token mints for convenience
COMMON_TOKENS = {
    "SOL": "So11111111111111111111111111111111111111112",
    "USDC": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    "USDT": "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
    "BONK": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
    "JUP": "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",
    "RAY": "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R",
    "PYTH": "HZ1JovNiVvGrGNiiYvEozEVgZ58xaU3RKwX8eACQBCt3",
}
