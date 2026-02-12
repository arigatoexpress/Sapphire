#!/usr/bin/env python3
"""
Aster Position Closer - Close profitable AGDG positions

This script will:
1. Fetch all open positions for the AGDG agent
2. Close positions with >40% profit
3. Keep positions with <40% profit open for more gains

Usage:
    python close_aster_positions.py [--dry-run] [--min-profit 0.4]
"""

import asyncio
import argparse
import sys
from pathlib import Path

# Add services/bot-aster/src to path
sys.path.insert(0, str(Path(__file__).parent / "services" / "bot-aster" / "src"))

from aster_client import AsterClient
from aster_config import ASTER_AGDG_ID, ASTER_AGDG_KEY
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def close_profitable_positions(min_profit_pct: float = 0.40, dry_run: bool = False):
    """
    Close Aster positions above profit threshold.

    Args:
        min_profit_pct: Minimum profit percentage to close (default 40%)
        dry_run: If True, only show what would be closed without actually closing
    """
    logger.info(f"🎯 Aster Position Closer")
    logger.info(f"   Agent: AGDG ({ASTER_AGDG_ID})")
    logger.info(f"   Min Profit: {min_profit_pct:.1%}")
    logger.info(f"   Dry Run: {dry_run}")
    logger.info("")

    # Initialize Aster client
    client = AsterClient(agent_id=ASTER_AGDG_ID, api_key=ASTER_AGDG_KEY)

    try:
        # Fetch all open positions
        logger.info("📊 Fetching open positions...")
        positions = await client.get_perpetual_positions()

        if not positions:
            logger.info("✅ No open positions found!")
            return

        logger.info(f"   Found {len(positions)} open position(s)\n")

        # Analyze and close profitable positions
        total_pnl = 0.0
        positions_to_close = []
        positions_to_keep = []

        for pos in positions:
            # Extract position details
            batch_id = pos.get("batchId", "unknown")
            symbol = pos.get("symbol", "UNKNOWN")
            side = pos.get("side", "UNKNOWN")
            leverage = pos.get("leverage", 0)
            entry_price = float(pos.get("entryPrice", 0))
            current_price = float(pos.get("currentPrice", entry_price))
            position_size = float(pos.get("positionSize", 0))
            collateral = float(pos.get("collateral", 0))
            pnl = float(pos.get("unrealizedPnl", 0))

            # Calculate PnL percentage
            if collateral > 0:
                pnl_pct = pnl / collateral
            else:
                pnl_pct = 0.0

            total_pnl += pnl

            # Decision logic
            if pnl_pct >= min_profit_pct:
                positions_to_close.append({
                    "batch_id": batch_id,
                    "symbol": symbol,
                    "side": side,
                    "leverage": leverage,
                    "entry": entry_price,
                    "current": current_price,
                    "pnl": pnl,
                    "pnl_pct": pnl_pct,
                    "collateral": collateral
                })
                logger.info(
                    f"🎯 CLOSE: {symbol} {side} {leverage}x | "
                    f"Entry: ${entry_price:.2f} → Current: ${current_price:.2f} | "
                    f"PnL: ${pnl:.2f} ({pnl_pct:+.2%}) | "
                    f"BatchID: {batch_id}"
                )
            else:
                positions_to_keep.append({
                    "symbol": symbol,
                    "side": side,
                    "pnl_pct": pnl_pct
                })
                logger.info(
                    f"📈 KEEP:  {symbol} {side} {leverage}x | "
                    f"Entry: ${entry_price:.2f} → Current: ${current_price:.2f} | "
                    f"PnL: ${pnl:.2f} ({pnl_pct:+.2%}) (below {min_profit_pct:.0%} threshold)"
                )

        # Summary
        logger.info("\n" + "=" * 80)
        logger.info(f"📊 SUMMARY")
        logger.info(f"   Total Positions: {len(positions)}")
        logger.info(f"   To Close: {len(positions_to_close)}")
        logger.info(f"   To Keep: {len(positions_to_keep)}")
        logger.info(f"   Total Unrealized PnL: ${total_pnl:+.2f}")
        logger.info("=" * 80 + "\n")

        if not positions_to_close:
            logger.info("✅ No positions meet the profit threshold for closing.")
            return

        # Close positions
        if dry_run:
            logger.info("🧪 DRY RUN MODE - No positions will be closed")
        else:
            logger.info(f"🚀 Closing {len(positions_to_close)} position(s)...\n")

            closed_count = 0
            closed_pnl = 0.0
            failed_count = 0

            for pos_info in positions_to_close:
                batch_id = pos_info["batch_id"]
                symbol = pos_info["symbol"]
                pnl = pos_info["pnl"]
                pnl_pct = pos_info["pnl_pct"]

                try:
                    logger.info(f"   Closing {symbol} (BatchID: {batch_id})...")
                    result = await client.close_perpetual_position(batch_id)

                    if result.get("status") == "success" or "success" in str(result).lower():
                        logger.info(f"   ✅ Closed {symbol} | Realized PnL: ${pnl:+.2f} ({pnl_pct:+.2%})")
                        closed_count += 1
                        closed_pnl += pnl
                    else:
                        logger.error(f"   ❌ Failed to close {symbol}: {result}")
                        failed_count += 1

                    # Small delay between closures
                    await asyncio.sleep(0.5)

                except Exception as e:
                    logger.error(f"   ❌ Error closing {symbol}: {e}")
                    failed_count += 1

            # Final summary
            logger.info("\n" + "=" * 80)
            logger.info(f"🎉 CLOSING COMPLETE")
            logger.info(f"   Successfully Closed: {closed_count}/{len(positions_to_close)}")
            logger.info(f"   Failed: {failed_count}")
            logger.info(f"   Total Realized PnL: ${closed_pnl:+.2f}")
            logger.info("=" * 80)

    finally:
        await client.close()


def main():
    parser = argparse.ArgumentParser(
        description="Close profitable Aster AGDG positions"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be closed without actually closing"
    )
    parser.add_argument(
        "--min-profit",
        type=float,
        default=0.40,
        help="Minimum profit percentage to close (default: 0.40 = 40%%)"
    )
    args = parser.parse_args()

    # Run async function
    asyncio.run(close_profitable_positions(
        min_profit_pct=args.min_profit,
        dry_run=args.dry_run
    ))


if __name__ == "__main__":
    main()
