"""
Trade Verification Service for Blockchain-Based Platforms

Verifies trades on Solana (Jupiter, Aster) and other blockchains to ensure
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

    # Platform-specific max retries for optimal speed vs reliability
    # HFT platforms (Aster shield) need minimal retries for speed
    # DEX platforms need moderate retries due to mempool delays
    PLATFORM_MAX_RETRIES = {
        "aster": 1,  # HFT shield strategy - fire and forget
        "aster": 3,  # Solana perps - balance speed and confirmation
        "jupiter": 5,  # DEX - higher retries for mempool delays
        "lighter": 3,  # L1 perps - moderate confirmation time
        "aster": 5,  # EVM chains - longer confirmation times
        "lighter": 5,  # L2 DEX - variable confirmation times
    }

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
            logger.info(
                f"✅ Trade Verification initialized - Solana RPC: {solana_rpc_url} | "
                f"Platform-specific retries: {self.PLATFORM_MAX_RETRIES}"
            )
        else:
            logger.warning("⚠️ Trade Verification limited - Solana SDK not available")

    def get_platform_max_retries(self, platform: str) -> int:
        """
        Get platform-specific max retries for optimal speed vs reliability.

        Args:
            platform: Platform name (aster, aster, jupiter, etc.)

        Returns:
            Max retries for the platform (defaults to 3 if platform unknown)
        """
        return self.PLATFORM_MAX_RETRIES.get(platform.lower(), 3)

    async def verify_jupiter_swap(
        self, tx_signature: str, max_retries: Optional[int] = None, platform: str = "jupiter"
    ) -> VerificationResult:
        """
        Verify a Jupiter swap transaction on Solana

        Args:
            tx_signature: Solana transaction signature
            max_retries: Number of verification attempts (overrides platform default if provided)
            platform: Platform name for retry optimization (default: jupiter)

        Returns:
            VerificationResult with verification status
        """
        if not HAS_SOLANA or not self.solana_client:
            return VerificationResult(
                verified=False,
                status="unavailable",
                error="Solana RPC not available",
            )

        # Use platform-specific retries if max_retries not explicitly provided
        if max_retries is None:
            max_retries = self.get_platform_max_retries(platform)

        logger.debug(f"Verifying {platform} transaction with max_retries={max_retries}")

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

    async def verify_aster_trade(
        self, tx_signature: str, max_retries: int = 3
    ) -> VerificationResult:
        """
        Verify a Aster protocol trade on Solana

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
            platform: Platform name (jupiter, aster, lighter, etc.)
            tx_signature: Transaction signature/hash
            max_retries: Number of verification attempts

        Returns:
            VerificationResult with verification status
        """
        platform_lower = platform.lower()

        if platform_lower == "jupiter":
            return await self.verify_jupiter_swap(tx_signature, max_retries)
        elif platform_lower == "aster":
            return await self.verify_aster_trade(tx_signature, max_retries)
        elif platform_lower in ["lighter", "aster", "aster", "lighter"]:
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
