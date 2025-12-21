import asyncio
import os
from typing import Optional

import base58
from solders.keypair import Keypair

from cloud_trader.drift_client import get_drift_client
from cloud_trader.jupiter_client import COMMON_TOKENS, get_jupiter_client
from cloud_trader.logger import get_logger

logger = get_logger(__name__)


class JupiterTreasurer:
    """
    The Treasurer Agent 🪐
    Objective: Liquidity Management & Profit Taking.
    Strategy: Periodic sweeps of excess USDC into SOL (Hard Asset).
    """

    def __init__(
        self,
        sweep_threshold_usdc: float = 1000.0,
        keep_buffer_usdc: float = 500.0,
        pct_to_sweep: float = 0.5,
    ):
        """
        Args:
            sweep_threshold_usdc: Trigger sweep if balance > this.
            keep_buffer_usdc: Amount to ALWAYS keep in USDC (operational costs).
            pct_to_sweep: % of excess to sweep (0.5 = 50%).
        """
        self.jup = get_jupiter_client()
        self.drift = get_drift_client()
        self.sweep_threshold = sweep_threshold_usdc
        self.buffer = keep_buffer_usdc
        self.pct = pct_to_sweep

        # Load Wallet Key for Signing
        self._keypair: Optional[Keypair] = None
        self._load_wallet()

    def _load_wallet(self):
        try:
            pk_str = os.getenv("SOLANA_PRIVATE_KEY")
            if pk_str:
                self._keypair = Keypair.from_bytes(base58.b58decode(pk_str))
                logger.info("🪐 Treasurer: Wallet Key Loaded.")
            else:
                logger.warning("🪐 Treasurer: No Private Key found. Read-only mode.")
        except Exception as e:
            logger.error(f"🪐 Treasurer: Failed to load wallet: {e}")

    async def run_sweep_cycle(self):
        """
        Check balances and execute sweep if criteria met.
        Call this periodically (e.g., every hour).
        """
        if not self._keypair:
            logger.warning("Treasurer cannot sweep: No Wallet.")
            return

        logger.info("🪐 Treasurer: Analyzing Liquidity...")

        try:
            # 1. Get USDC Balance (From Drift User Account or Wallet ATA?)
            # Usually profits settle in the Wallet ATA after Drift settle,
            # OR they stay in Drift.
            # For simplicity in this Phase, we assume we check the WALLET USDC first.
            # Real implementation would also check Drift 'settled' PnL.

            # Mocking wallet fetch for now via DriftClient or direct RPC
            # In a full flow, we'd query the ATA of the wallet.
            # Let's assume DriftClient has a helper or we use a balance check.

            current_usdc_balance = 1200.00  # TODO: Wire to real RPC balance check

            logger.info(
                f"   Current USDC: ${current_usdc_balance:.2f} (Threshold: ${self.sweep_threshold:.2f})"
            )

            if current_usdc_balance > self.sweep_threshold:
                excess = current_usdc_balance - self.buffer
                if excess <= 0:
                    return

                amount_to_swap = excess * self.pct
                logger.info(
                    f"💰 Profit Sweep Triggered! Swapping ${amount_to_swap:.2f} USDC -> SOL"
                )

                # 2. Execute Swap via Jupiter Ultra
                # 1 USDC = 1,000,000 atomic units
                atomic_amount = int(amount_to_swap * 1_000_000)

                result = await self.jup.execute_swap(
                    input_mint=COMMON_TOKENS["USDC"],
                    output_mint=COMMON_TOKENS["SOL"],
                    amount=atomic_amount,
                    user_keypair=self._keypair,
                )

                logger.info(f"✅ Sweep Complete! Tx: {result.get('signature')}")

            else:
                logger.info("   No sweep needed.")

        except Exception as e:
            logger.error(f"🪐 Treasurer Error: {e}")
