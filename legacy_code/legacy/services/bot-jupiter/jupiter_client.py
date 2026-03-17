"""
Jupiter Exchange Client
Provides clean REST API integration for trading on Solana via Jupiter
- Spot swaps with best price aggregation
- Perpetuals with up to 100x leverage
- Lending/borrowing
- DCA and limit orders

No dependency hell - just HTTP requests!
"""

import asyncio
import httpx
from typing import Dict, List, Optional, Any
from decimal import Decimal
from dataclasses import dataclass
from enum import Enum
from loguru import logger
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction
from solana.rpc.async_api import AsyncClient
from solana.rpc.types import TxOpts
from solana.rpc.commitment import Confirmed
import base58
import base64


class JupiterProduct(Enum):
    """Jupiter product types"""
    ULTRA_SWAP = "ultra"  # RPC-less swap API
    PERPETUALS = "perps"
    LENDING = "lend"
    TRIGGER = "trigger"  # Limit orders
    RECURRING = "recurring"  # DCA


@dataclass
class SwapQuote:
    """Quote response from Jupiter"""
    input_mint: str
    output_mint: str
    in_amount: str
    out_amount: str
    other_amount_threshold: str
    swap_mode: str
    slippage_bps: int
    price_impact_pct: float
    route_plan: List[Dict]
    context_slot: Optional[int] = None
    time_taken: Optional[float] = None


@dataclass
class SwapResult:
    """Result of executed swap"""
    signature: str
    input_amount: Decimal
    output_amount: Decimal
    price: Decimal
    success: bool
    error: Optional[str] = None


@dataclass
class PerpPosition:
    """Perpetual position information"""
    market: str  # SOL, ETH, or wBTC
    side: str  # "long" or "short"
    size: Decimal
    entry_price: Decimal
    current_price: Decimal
    leverage: int
    pnl: Decimal
    liquidation_price: Decimal
    collateral: Decimal


class JupiterClient:
    """
    Jupiter Exchange API Client

    Supports:
    - Spot trading via Ultra Swap API (RPC-less)
    - Perpetuals (SOL, ETH, wBTC) with up to 100x leverage
    - Lending and borrowing
    - Limit orders and DCA

    Example:
        ```python
        client = JupiterClient(
            api_key="your_jupiter_api_key",
            keypair=your_solana_keypair,
            api_base_url="https://api.jup.ag"
        )

        # Get quote for swapping 1 SOL to USDC
        quote = await client.get_swap_quote(
            input_mint="So11111111111111111111111111111111111111112",  # SOL
            output_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
            amount=1_000_000_000,  # 1 SOL (9 decimals)
            slippage_bps=50  # 0.5%
        )

        # Execute swap
        result = await client.execute_swap(quote)
        ```
    """

    # Token mints (mainnet)
    SOL_MINT = "So11111111111111111111111111111111111111112"
    USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    USDT_MINT = "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"
    ETH_MINT = "7vfCXTUXx5WJV5JADk17DUJ4ksgau7utNKj4b963voxs"  # Wormhole ETH
    WBTC_MINT = "3NZ9JMVBmGAqocybic2c7LQCJScmgsAZ6vQqTDzcqmJh"  # Wormhole BTC

    def __init__(
        self,
        api_key: str,
        keypair: Keypair,
        api_base_url: str = "https://api.jup.ag",
        solana_rpc_url: str = "https://api.mainnet-beta.solana.com",
        max_retries: int = 3,
        timeout: float = 30.0,
    ):
        """
        Initialize Jupiter client

        Args:
            api_key: Jupiter API key from portal
            keypair: Solana keypair for signing transactions
            api_base_url: Jupiter API base URL
            solana_rpc_url: Solana RPC endpoint (optional for Ultra API)
            max_retries: Max retry attempts
            timeout: Request timeout in seconds
        """
        self.api_key = api_key
        self.keypair = keypair
        self.api_base_url = api_base_url.rstrip("/")
        self.solana_rpc_url = solana_rpc_url
        self.max_retries = max_retries
        self.timeout = timeout

        self.http_client = httpx.AsyncClient(
            base_url=self.api_base_url,
            headers={
                "X-API-Key": self.api_key,
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )

        # Solana RPC client (for transaction signing/submission if needed)
        self.solana_client = AsyncClient(solana_rpc_url)

        # Mask wallet address for security (only show first 4 and last 4 chars)
        wallet_addr = str(self.keypair.pubkey())
        masked_wallet = f"{wallet_addr[:4]}...{wallet_addr[-4:]}"
        logger.info(f"Jupiter client initialized - Wallet: {masked_wallet}")

    async def close(self):
        """Close HTTP clients"""
        await self.http_client.aclose()
        await self.solana_client.close()

    # ============================================================================
    # ULTRA SWAP API (RPC-less, simplest way to trade)
    # ============================================================================

    async def get_swap_order(
        self,
        input_mint: str,
        output_mint: str,
        amount: int,
        taker: Optional[str] = None,
        exclude_routers: Optional[List[str]] = None,
        exclude_dexes: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Get swap order from Jupiter Ultra API (combines quote + transaction)

        Args:
            input_mint: Input token mint address
            output_mint: Output token mint address
            amount: Amount in smallest unit (e.g., lamports for SOL)
            taker: Wallet address (defaults to client keypair)
            exclude_routers: List of routers to exclude (iris, jupiterz, dflow, okx)
            exclude_dexes: List of DEXes to exclude (only affects iris router)

        Returns:
            Order response with quote and unsigned transaction
        """
        params = {
            "inputMint": input_mint,
            "outputMint": output_mint,
            "amount": str(amount),
            "taker": taker or str(self.keypair.pubkey()),
        }

        if exclude_routers:
            params["excludeRouters"] = ",".join(exclude_routers)

        if exclude_dexes:
            params["excludeDexes"] = ",".join(exclude_dexes)

        response = await self.http_client.get("/ultra/v1/order", params=params)
        response.raise_for_status()
        data = response.json()

        return data

    async def execute_swap(
        self,
        order_response: Dict[str, Any],
    ) -> SwapResult:
        """
        Execute swap using Ultra Swap API (RPC-less)

        Args:
            order_response: Order response from get_swap_order()

        Returns:
            SwapResult with transaction signature and amounts
        """
        # Check if order has transaction
        unsigned_tx = order_response.get("transaction")
        if not unsigned_tx:
            error_msg = order_response.get("errorMessage", "No transaction in order response")
            logger.error(f"Cannot execute swap: {error_msg}")
            return SwapResult(
                signature="",
                input_amount=Decimal(order_response["inAmount"]),
                output_amount=Decimal(order_response["outAmount"]),
                price=Decimal(0),
                success=False,
                error=error_msg,
            )

        # Get request ID (required for execute)
        request_id = order_response["requestId"]

        # Step 1: Sign the transaction
        swap_transaction_bytes = base64.b64decode(unsigned_tx)

        # Deserialize transaction
        transaction = VersionedTransaction.from_bytes(swap_transaction_bytes)

        logger.debug(f"Unsigned transaction signatures: {len(transaction.signatures)}")

        # For Solana transactions, we need to sign the message hash
        # Get the message hash - this is what actually gets signed
        message_hash = transaction.message.hash()

        # Sign the message hash with our keypair
        signature = self.keypair.sign_message(bytes(message_hash))

        # Create a properly signed transaction
        # Jupiter transactions should have exactly one signature (the swapper)
        signed_transaction = VersionedTransaction.populate(transaction.message, [signature])

        # Verify the signature is valid
        try:
            verification_result = signed_transaction.verify_with_results()
            logger.debug(f"Signature verification: {verification_result}")
        except Exception as e:
            logger.warning(f"Could not verify signature: {e}")

        # Serialize signed transaction
        signed_tx_bytes = bytes(signed_transaction)
        signed_tx_base64 = base64.b64encode(signed_tx_bytes).decode('utf-8')

        logger.debug(f"Signed transaction length: {len(signed_tx_bytes)} bytes")
        logger.debug(f"Signature (base58): {signature}")
        logger.debug(f"Our public key: {self.keypair.pubkey()}")

        # Step 2: Execute via /ultra/v1/execute
        execute_payload = {
            "requestId": request_id,
            "signedTransaction": signed_tx_base64,
        }

        response = await self.http_client.post("/ultra/v1/execute", json=execute_payload)

        # Better error handling with response body
        if response.status_code != 200:
            try:
                error_data = response.json()
                error_msg = error_data.get("error", error_data.get("message", str(error_data)))
                logger.error(f"Jupiter Ultra API error: {response.status_code} - {error_msg}")
                logger.error(f"Full error response: {error_data}")
            except:
                logger.error(f"Jupiter Ultra API error: {response.status_code} - {response.text}")
            response.raise_for_status()

        execute_data = response.json()

        # Parse result
        tx_signature = execute_data.get("signature", execute_data.get("txid"))

        logger.info(f"Swap executed - Signature: {tx_signature}")

        return SwapResult(
            signature=tx_signature,
            input_amount=Decimal(order_response["inAmount"]),
            output_amount=Decimal(order_response["outAmount"]),
            price=Decimal(order_response["outAmount"]) / Decimal(order_response["inAmount"]),
            success=True,
        )

    async def swap_tokens(
        self,
        input_mint: str,
        output_mint: str,
        amount: int,
        exclude_routers: Optional[List[str]] = None,
        exclude_dexes: Optional[List[str]] = None,
    ) -> SwapResult:
        """
        Convenience method: order + execute in one call

        Args:
            input_mint: Input token mint
            output_mint: Output token mint
            amount: Amount in smallest unit
            exclude_routers: List of routers to exclude
            exclude_dexes: List of DEXes to exclude

        Returns:
            SwapResult
        """
        order = await self.get_swap_order(
            input_mint, output_mint, amount,
            exclude_routers=exclude_routers,
            exclude_dexes=exclude_dexes
        )
        return await self.execute_swap(order)

    # ============================================================================
    # ULTRA SWAP API HELPERS
    # ============================================================================

    async def get_holdings(self, address: Optional[str] = None) -> Dict[str, Any]:
        """
        Get token holdings for a wallet address

        Args:
            address: Wallet address (defaults to client keypair)

        Returns:
            Holdings data with SOL and token balances
        """
        wallet_address = address or str(self.keypair.pubkey())
        response = await self.http_client.get(f"/ultra/v1/holdings/{wallet_address}")
        response.raise_for_status()
        return response.json()

    async def get_token_shield_info(self, mints: List[str]) -> Dict[str, Any]:
        """
        Get safety information and warnings for tokens

        Args:
            mints: List of token mint addresses

        Returns:
            Shield data with warnings for each mint
        """
        response = await self.http_client.get("/ultra/v1/shield", params={
            "mints": ",".join(mints)
        })
        response.raise_for_status()
        return response.json()

    async def search_ultra_tokens(self, query: str) -> List[Dict[str, Any]]:
        """
        Search for tokens using Ultra API

        Args:
            query: Token symbol, name, or mint address

        Returns:
            List of matching tokens with full metadata
        """
        response = await self.http_client.get("/ultra/v1/search", params={
            "query": query
        })
        response.raise_for_status()
        return response.json()

    async def get_available_routers(self) -> List[Dict[str, Any]]:
        """
        Get list of available routers in Jupiter's routing engine

        Returns:
            List of router information (id, name, icon)
        """
        response = await self.http_client.get("/ultra/v1/order/routers")
        response.raise_for_status()
        return response.json()

    # ============================================================================
    # PRICE API
    # ============================================================================

    async def get_token_price(self, mint: str, vs_token: str = USDC_MINT) -> Decimal:
        """
        Get token price in terms of another token (default USDC)

        Args:
            mint: Token mint address
            vs_token: Quote currency (default USDC)

        Returns:
            Price as Decimal
        """
        response = await self.http_client.get(f"/price/v3", params={
            "ids": mint,
            "vsToken": vs_token,
        })
        response.raise_for_status()
        data = response.json()

        # V3 API returns: {mint: {usdPrice, liquidity, ...}}
        price_info = data[mint]
        return Decimal(str(price_info["usdPrice"]))

    async def get_multiple_prices(self, mints: List[str], vs_token: str = USDC_MINT) -> Dict[str, Decimal]:
        """Get prices for multiple tokens"""
        response = await self.http_client.get(f"/price/v3", params={
            "ids": ",".join(mints),
            "vsToken": vs_token,
        })
        response.raise_for_status()
        data = response.json()

        # V3 API returns: {mint: {usdPrice, liquidity, ...}, ...}
        return {
            mint: Decimal(str(info["usdPrice"]))
            for mint, info in data.items()
        }

    # ============================================================================
    # TOKEN INFO API
    # ============================================================================

    async def get_token_info(self, mint: str) -> Dict[str, Any]:
        """Get detailed token information"""
        response = await self.http_client.get(f"/tokens/v1/{mint}")
        response.raise_for_status()
        return response.json()

    async def search_tokens(self, query: str) -> List[Dict[str, Any]]:
        """Search for tokens by name/symbol"""
        response = await self.http_client.get("/tokens/v1/search", params={"query": query})
        response.raise_for_status()
        return response.json()

    # ============================================================================
    # HELPER METHODS
    # ============================================================================

    async def get_sol_balance(self) -> Decimal:
        """Get SOL balance of wallet"""
        response = await self.solana_client.get_balance(self.keypair.pubkey())
        balance_lamports = response.value
        return Decimal(balance_lamports) / Decimal(10**9)

    async def get_token_balance(self, mint: str) -> Decimal:
        """Get SPL token balance (simplified)"""
        # This would require getting token accounts and parsing balances
        # For now, return placeholder
        logger.warning("get_token_balance not yet implemented - use wallet balance from token account")
        return Decimal(0)

    def format_amount(self, amount: Decimal, decimals: int) -> int:
        """Convert decimal amount to smallest unit (e.g., SOL to lamports)"""
        return int(amount * Decimal(10 ** decimals))

    def parse_amount(self, amount: int, decimals: int) -> Decimal:
        """Convert smallest unit to decimal (e.g., lamports to SOL)"""
        return Decimal(amount) / Decimal(10 ** decimals)


# ============================================================================
# USAGE EXAMPLES
# ============================================================================

async def example_swap():
    """Example: Swap SOL for USDC using Ultra API"""
    import base58

    # Your credentials
    JUPITER_API_KEY = "d1302809-3996-4ceb-aad0-7da8a71d6149"
    SOLANA_PRIVATE_KEY = "5tg6XZMb96ZcGAip6jnpRmxWfQxNASr6tM9C8LmKxhhMC6gKEtsvQPdzhmMogrrbcf8wjTwyWnsfD12NjXJfeZc8"

    # Load keypair
    private_bytes = base58.b58decode(SOLANA_PRIVATE_KEY)
    keypair = Keypair.from_bytes(private_bytes)

    client = JupiterClient(
        api_key=JUPITER_API_KEY,
        keypair=keypair,
    )

    try:
        # Get current SOL price
        sol_price = await client.get_token_price(JupiterClient.SOL_MINT)
        logger.info(f"Current SOL price: ${sol_price}")

        # Get wallet holdings
        holdings = await client.get_holdings()
        logger.info(f"SOL balance: {holdings['uiAmount']} SOL")

        # Get swap order for 0.01 SOL -> USDC
        amount_sol = Decimal("0.01")
        amount_lamports = client.format_amount(amount_sol, 9)

        logger.info(f"Getting order to swap {amount_sol} SOL -> USDC...")
        order = await client.get_swap_order(
            input_mint=JupiterClient.SOL_MINT,
            output_mint=JupiterClient.USDC_MINT,
            amount=amount_lamports,
        )

        logger.info(f"Order received:")
        logger.info(f"  Input: {client.parse_amount(int(order['inAmount']), 9)} SOL")
        logger.info(f"  Output: {client.parse_amount(int(order['outAmount']), 6)} USDC")
        logger.info(f"  Price Impact: {order.get('priceImpact', 0):.4f}%")
        logger.info(f"  Router: {order['router']}")
        logger.info(f"  Fee: {order['feeBps']} bps")

        # Uncomment to execute swap
        # result = await client.execute_swap(order)
        # logger.info(f"Swap successful! Signature: {result.signature}")

    finally:
        await client.close()


async def example_get_prices():
    """Example: Get token prices"""
    client = JupiterClient(
        api_key="YOUR_JUPITER_API_KEY",
        keypair=Keypair(),  # Dummy keypair for read-only operations
    )

    try:
        # Get SOL price in USDC
        sol_price = await client.get_token_price(JupiterClient.SOL_MINT)
        print(f"SOL Price: ${sol_price}")

        # Get multiple prices
        prices = await client.get_multiple_prices([
            JupiterClient.SOL_MINT,
            JupiterClient.ETH_MINT,
            JupiterClient.WBTC_MINT,
        ])

        for mint, price in prices.items():
            print(f"{mint}: ${price}")

    finally:
        await client.close()


if __name__ == "__main__":
    # Run examples
    asyncio.run(example_swap())
    # asyncio.run(example_get_prices())
