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

logger = logging.getLogger(__name__)

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
        Initialize Jupiter client.

        Args:
            api_key: Jupiter API key (optional, for higher rate limits)
        """
        self.api_key = api_key or os.getenv("JUPITER_API_KEY")
        self.base_url = f"{JUPITER_API_BASE}/{JUPITER_API_VERSION}"

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Sapphire-AI/1.0",
            "Accept": "application/json",
        }

        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        self.client = httpx.AsyncClient(base_url=self.base_url, headers=headers, timeout=30.0)

    async def close(self):
        """Close HTTP client."""
        await self.client.close()

    async def get_quote(
        self,
        input_mint: str,
        output_mint: str,
        amount: int,
        slippage_bps: int = 50,  # 0.5% default
        only_direct_routes: bool = False,
    ) -> Dict[str, Any]:
        """
        Get best swap quote from Jupiter.

        Args:
            input_mint: Input token mint address
            output_mint: Output token mint address
            amount: Input amount in smallest unit (lamports/base units)
            slippage_bps: Slippage tolerance in basis points (50 = 0.5%)
            only_direct_routes: If True, only use direct routes (faster but may miss best prices)

        Returns:
            Quote response with route plan and price info

        Example:
            # SOL to USDC
            quote = await client.get_quote(
                input_mint="So11111111111111111111111111111111111111112",
                output_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                amount=1000000000  # 1 SOL = 1e9 lamports
            )
        """
        params = {
            "inputMint": input_mint,
            "outputMint": output_mint,
            "amount": str(amount),
            "slippageBps": slippage_bps,
            "onlyDirectRoutes": str(only_direct_routes).lower(),
            "asLegacyTransaction": "false",  # Use versioned transactions
        }

        logger.info(
            f"Fetching Jupiter quote: {input_mint[:8]}... → {output_mint[:8]}... ({amount})"
        )

        try:
            response = await self.client.get("/quote", params=params)
            response.raise_for_status()
            quote = response.json()

            logger.info(
                f"Quote received: {quote.get('inAmount')} → {quote.get('outAmount')} "
                f"(impact: {quote.get('priceImpactPct', 0):.3f}%)"
            )

            return quote
        except httpx.HTTPError as e:
            logger.error(f"Jupiter quote error: {e}")
            raise

    async def get_swap_transaction(
        self,
        quote: Dict[str, Any],
        user_public_key: str,
        wrap_unwrap_sol: bool = True,
        priority_level: str = "medium",
        dynamic_compute_units: bool = True,
    ) -> Dict[str, Any]:
        """
        Get swap transaction from quote.

        Args:
            quote: Quote response from get_quote()
            user_public_key: User's Solana wallet public key
            wrap_unwrap_sol: Auto wrap/unwrap SOL to WSOL
            priority_level: Priority fee level - "low", "medium", "high", "veryHigh"
            dynamic_compute_units: Auto-optimize compute unit limit

        Returns:
            Swap transaction as base64 encoded string
        """
        payload = {
            "quoteResponse": quote,
            "userPublicKey": user_public_key,
            "wrapAndUnwrapSol": wrap_unwrap_sol,
            "priorityLevelWithMaxLamports": {"priorityLevel": priority_level},
            "dynamicComputeUnitLimit": dynamic_compute_units,
        }

        logger.info(f"Building swap transaction for {user_public_key[:8]}...")

        try:
            response = await self.client.post("/swap", json=payload)
            response.raise_for_status()
            swap_result = response.json()

            return swap_result
        except httpx.HTTPError as e:
            logger.error(f"Jupiter swap transaction error: {e}")
            raise

    async def execute_swap(
        self, quote: Dict[str, Any], user_keypair: Keypair, priority_level: str = "medium"
    ) -> Dict[str, Any]:
        """
        Complete swap execution flow using Jupiter's execute endpoint.

        Args:
            quote: Quote from get_quote()
            user_keypair: User's Solana keypair for signing
            priority_level: Transaction priority

        Returns:
            Execution result with transaction signature
        """
        # Get swap transaction
        swap_result = await self.get_swap_transaction(
            quote=quote, user_public_key=str(user_keypair.pubkey()), priority_level=priority_level
        )

        # Deserialize transaction
        tx_bytes = base64.b64decode(swap_result["swapTransaction"])
        tx = VersionedTransaction.from_bytes(tx_bytes)

        # Sign transaction
        tx.sign([user_keypair])

        # Encode signed transaction
        signed_tx_base64 = base64.b64encode(bytes(tx)).decode("utf-8")

        # Submit to Jupiter's execute endpoint (handles RPC submission)
        logger.info("Submitting signed transaction to Jupiter...")

        try:
            execute_response = await self.client.post(
                "/swap/execute", json={"swapTransaction": signed_tx_base64}
            )
            execute_response.raise_for_status()
            result = execute_response.json()

            logger.info(f"Swap executed! Signature: {result.get('signature', 'N/A')}")

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
            logger.error(f"Price fetch error: {e}")
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
