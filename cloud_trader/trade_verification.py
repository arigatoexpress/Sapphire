"""
Trade Verification Service for Blockchain-Based Platforms

Verifies trades on Solana (Jupiter, Drift) and other blockchains to ensure
all reported trades are actually executed on-chain.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Any
from decimal import Decimal

from loguru import logger

try:
    from solana.rpc.async_api import AsyncClient
    from solders.signature import Signature
    HAS_SOLANA = True
except ImportError:
    logger.warning("Solana RPC not available - trade verification will be limited")
    HAS_SOLANA = False


@dataclass
class VerificationResult:
    """Result of trade verification check"""
    verified: bool
    status: str  # "confirmed", "pending", "failed", "not_found"
    block_number: Optional[int] = None
    confirmation_time: Optional[datetime] = None
    error: Optional[str] = None
    raw_data: Optional[Dict[str, Any]] = None


class TradeVerificationService:
    """Verifies trades on blockchain networks"""

    def __init__(
        self,
        solana_rpc_url: str = "https://api.mainnet-beta.solana.com",
        verification_timeout: int = 30,
    ):
        """
        Initialize trade verification service

        Args:
            solana_rpc_url: Solana RPC endpoint
            verification_timeout: Timeout in seconds for verification checks
        """
        self.solana_rpc_url = solana_rpc_url
        self.verification_timeout = verification_timeout
        self.solana_client = None

        if HAS_SOLANA:
            self.solana_client = AsyncClient(solana_rpc_url)
            logger.info(f"✅ Trade Verification initialized - Solana RPC: {solana_rpc_url}")
        else:
            logger.warning("⚠️ Trade Verification limited - Solana SDK not available")

    async def verify_jupiter_swap(
        self, tx_signature: str, max_retries: int = 3
    ) -> VerificationResult:
        """
        Verify a Jupiter swap transaction on Solana

        Args:
            tx_signature: Solana transaction signature
            max_retries: Number of verification attempts

        Returns:
            VerificationResult with verification status
        """
        if not HAS_SOLANA or not self.solana_client:
            return VerificationResult(
                verified=False,
                status="unavailable",
                error="Solana RPC not available",
            )

        for attempt in range(max_retries):
            try:
                # Convert signature string to Signature object
                sig = Signature.from_string(tx_signature)

                # Get transaction with retry
                response = await self.solana_client.get_transaction(
                    sig,
                    encoding="jsonParsed",
                    max_supported_transaction_version=0,
                )

                if response.value is None:
                    if attempt < max_retries - 1:
                        logger.debug(
                            f"Transaction {tx_signature[:8]}... not found yet, "
                            f"retry {attempt + 1}/{max_retries}"
                        )
                        await asyncio.sleep(2 ** attempt)  # Exponential backoff
                        continue
                    else:
                        return VerificationResult(
                            verified=False,
                            status="not_found",
                            error=f"Transaction not found after {max_retries} attempts",
                        )

                tx = response.value

                # Check if transaction was successful
                if tx.meta and tx.meta.err is None:
                    # Transaction succeeded
                    block_time = tx.block_time
                    confirmation_time = (
                        datetime.fromtimestamp(block_time) if block_time else None
                    )

                    logger.info(
                        f"✅ Jupiter swap verified: {tx_signature[:8]}... "
                        f"| Block: {tx.slot} | Time: {confirmation_time}"
                    )

                    return VerificationResult(
                        verified=True,
                        status="confirmed",
                        block_number=tx.slot,
                        confirmation_time=confirmation_time,
                        raw_data={
                            "slot": tx.slot,
                            "block_time": block_time,
                            "fee": tx.meta.fee if tx.meta else None,
                        },
                    )
                else:
                    # Transaction failed
                    error_msg = str(tx.meta.err) if tx.meta and tx.meta.err else "Unknown error"
                    logger.error(f"❌ Jupiter swap failed: {tx_signature[:8]}... | Error: {error_msg}")

                    return VerificationResult(
                        verified=False,
                        status="failed",
                        block_number=tx.slot,
                        error=error_msg,
                        raw_data={
                            "slot": tx.slot,
                            "error": error_msg,
                        },
                    )

            except Exception as e:
                if attempt < max_retries - 1:
                    logger.debug(
                        f"Verification attempt {attempt + 1} failed: {e}, retrying..."
                    )
                    await asyncio.sleep(2 ** attempt)
                else:
                    logger.error(f"❌ Failed to verify transaction {tx_signature[:8]}...: {e}")
                    return VerificationResult(
                        verified=False,
                        status="error",
                        error=str(e),
                    )

        return VerificationResult(
            verified=False,
            status="timeout",
            error=f"Verification timeout after {max_retries} attempts",
        )

    async def verify_drift_trade(
        self, tx_signature: str, max_retries: int = 3
    ) -> VerificationResult:
        """
        Verify a Drift protocol trade on Solana

        Uses same verification as Jupiter since both are on Solana
        """
        return await self.verify_jupiter_swap(tx_signature, max_retries)

    async def verify_trade(
        self,
        platform: str,
        tx_signature: str,
        max_retries: int = 3,
    ) -> VerificationResult:
        """
        Verify a trade based on platform

        Args:
            platform: Platform name (jupiter, drift, hyperliquid, etc.)
            tx_signature: Transaction signature/hash
            max_retries: Number of verification attempts

        Returns:
            VerificationResult with verification status
        """
        platform_lower = platform.lower()

        if platform_lower == "jupiter":
            return await self.verify_jupiter_swap(tx_signature, max_retries)
        elif platform_lower == "drift":
            return await self.verify_drift_trade(tx_signature, max_retries)
        elif platform_lower in ["hyperliquid", "aster", "symphony", "lighter"]:
            # CEX/other platforms don't have blockchain verification
            # Trust the platform's response
            return VerificationResult(
                verified=True,
                status="platform_confirmed",
                raw_data={"platform": platform, "note": "CEX trade - no blockchain verification"},
            )
        else:
            return VerificationResult(
                verified=False,
                status="unsupported",
                error=f"Verification not supported for platform: {platform}",
            )

    async def close(self):
        """Close RPC connections"""
        if self.solana_client:
            await self.solana_client.close()
            logger.info("🔌 Trade Verification service closed")


# Example usage
async def example_verify_trade():
    """Example: Verify a Jupiter swap"""
    service = TradeVerificationService()

    try:
        # Example Jupiter swap signature
        tx_sig = "5tKxzB8hmQyqXJVxNj3..."  # Replace with actual signature

        result = await service.verify_jupiter_swap(tx_sig)

        if result.verified:
            print(f"✅ Trade verified!")
            print(f"   Status: {result.status}")
            print(f"   Block: {result.block_number}")
            print(f"   Time: {result.confirmation_time}")
        else:
            print(f"❌ Verification failed: {result.error}")

    finally:
        await service.close()


if __name__ == "__main__":
    asyncio.run(example_verify_trade())
