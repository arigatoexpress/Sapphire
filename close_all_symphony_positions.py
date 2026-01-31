#!/usr/bin/env python3
"""
Symphony Position Closer - Close ALL open positions

Closes all open positions for both AGDG and MILF agents on Symphony.

Usage:
    python3 close_all_symphony_positions.py [--agent agdg|milf|both]
"""

import asyncio
import argparse
import httpx
import logging
from typing import List, Dict, Any

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Symphony API Configuration
SYMPHONY_BASE_URL = "https://api.symphony.io"

# Agent Configuration
import os

AGENTS = {
    "agdg": {
        "name": "Ari Gold Fund ($AGDG)",
        "id": os.getenv("SYMPHONY_AGDG_AGENT_ID", "01b8c2b7-b210-493f-8c76-dafd97663e2c"),
        "api_key": os.getenv("SYMPHONY_AGDG_API_KEY", ""),  # Set via environment variable
        "type": "PERPS",
        "chain": "BASE"
    },
    "milf": {
        "name": "Monad Implementation Treasury ($MILF)",
        "id": os.getenv("SYMPHONY_MILF_AGENT_ID", "f6cc5590-ff96-4077-ac80-9775c7f805cc"),
        "api_key": os.getenv("SYMPHONY_MILF_API_KEY", ""),  # Set via environment variable
        "type": "SWAP",
        "chain": "MONAD"
    }
}

# Validate API keys are set
for agent_key, agent_config in AGENTS.items():
    if not agent_config["api_key"]:
        logger.error(f"ERROR: {agent_config['name']} API key not set!")
        logger.error(f"Please set SYMPHONY_{agent_key.upper()}_API_KEY environment variable")
        # Note: Script will fail when trying to use this agent


async def get_positions(api_key: str, agent_id: str) -> List[Dict]:
    """Get all open positions for an agent."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        headers = {"Authorization": f"Bearer {api_key}"}

        try:
            response = await client.get(
                f"{SYMPHONY_BASE_URL}/agent/positions",
                params={"agentId": agent_id},
                headers=headers
            )
            response.raise_for_status()
            positions = response.json()
            return positions if isinstance(positions, list) else []
        except httpx.HTTPStatusError as e:
            logger.error(f"Failed to get positions: {e.response.status_code} - {e.response.text}")
            return []
        except Exception as e:
            logger.error(f"Error fetching positions: {e}")
            return []


async def close_position(api_key: str, agent_id: str, batch_id: str) -> Dict:
    """Close a position by batch ID."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        headers = {"Authorization": f"Bearer {api_key}"}

        payload = {
            "agentId": agent_id,
            "batchId": batch_id
        }

        try:
            response = await client.post(
                f"{SYMPHONY_BASE_URL}/agent/batch-close",
                json=payload,
                headers=headers
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Failed to close position: {e.response.status_code} - {e.response.text}")
            return {"status": "error", "message": e.response.text}
        except Exception as e:
            logger.error(f"Error closing position: {e}")
            return {"status": "error", "message": str(e)}


async def close_agent_positions(agent_key: str):
    """Close all positions for a specific agent."""
    agent_config = AGENTS[agent_key]
    agent_name = agent_config["name"]
    agent_id = agent_config["id"]
    api_key = agent_config["api_key"]

    logger.info(f"\n{'='*80}")
    logger.info(f"🎯 Processing Agent: {agent_name}")
    logger.info(f"   ID: {agent_id}")
    logger.info(f"   Type: {agent_config['type']} on {agent_config['chain']}")
    logger.info(f"{'='*80}\n")

    # Fetch positions
    logger.info("📊 Fetching open positions...")
    positions = await get_positions(api_key, agent_id)

    if not positions:
        logger.info("✅ No open positions found!\n")
        return {
            "agent": agent_name,
            "total_positions": 0,
            "closed": 0,
            "failed": 0,
            "total_pnl": 0.0
        }

    logger.info(f"   Found {len(positions)} open position(s)\n")

    # Display all positions
    total_pnl = 0.0
    positions_data = []

    for idx, pos in enumerate(positions, 1):
        batch_id = pos.get("batchId", "unknown")
        symbol = pos.get("symbol", "UNKNOWN")
        side = pos.get("side", "UNKNOWN")
        leverage = pos.get("leverage", 0)
        entry_price = float(pos.get("entryPrice", 0))
        current_price = float(pos.get("currentPrice", entry_price))
        pnl = float(pos.get("unrealizedPnl", 0))
        collateral = float(pos.get("collateral", 0))

        pnl_pct = (pnl / collateral * 100) if collateral > 0 else 0.0
        total_pnl += pnl

        positions_data.append({
            "batch_id": batch_id,
            "symbol": symbol,
            "side": side,
            "leverage": leverage,
            "entry": entry_price,
            "current": current_price,
            "pnl": pnl,
            "pnl_pct": pnl_pct
        })

        status = "🟢" if pnl > 0 else "🔴"
        logger.info(
            f"{status} #{idx}: {symbol} {side} {leverage}x | "
            f"Entry: ${entry_price:.2f} → Current: ${current_price:.2f} | "
            f"PnL: ${pnl:+.2f} ({pnl_pct:+.1f}%) | BatchID: {batch_id}"
        )

    # Summary
    logger.info("\n" + "─" * 80)
    logger.info(f"📊 SUMMARY FOR {agent_name}")
    logger.info(f"   Total Positions: {len(positions)}")
    logger.info(f"   Total Unrealized PnL: ${total_pnl:+.2f}")
    logger.info("─" * 80 + "\n")

    # Ask for confirmation
    response = input(f"🚨 Close ALL {len(positions)} position(s) for {agent_name}? (yes/no): ")
    if response.lower() not in ["yes", "y"]:
        logger.info("❌ Aborted by user\n")
        return {
            "agent": agent_name,
            "total_positions": len(positions),
            "closed": 0,
            "failed": 0,
            "total_pnl": 0.0
        }

    # Close all positions
    logger.info(f"\n🚀 Closing {len(positions)} position(s)...\n")

    closed_count = 0
    failed_count = 0
    closed_pnl = 0.0

    for pos_data in positions_data:
        batch_id = pos_data["batch_id"]
        symbol = pos_data["symbol"]
        pnl = pos_data["pnl"]
        pnl_pct = pos_data["pnl_pct"]

        logger.info(f"   Closing {symbol} (BatchID: {batch_id})...")
        result = await close_position(api_key, agent_id, batch_id)

        # Check for success
        if (result.get("status") == "success" or
            "success" in str(result).lower() or
            result.get("batchId")):  # Some APIs return the batch on success
            logger.info(f"   ✅ Closed {symbol} | Realized PnL: ${pnl:+.2f} ({pnl_pct:+.1f}%)")
            closed_count += 1
            closed_pnl += pnl
        else:
            logger.error(f"   ❌ Failed to close {symbol}: {result.get('message', result)}")
            failed_count += 1

        # Small delay between closures to avoid rate limiting
        await asyncio.sleep(0.5)

    # Final summary for this agent
    logger.info("\n" + "═" * 80)
    logger.info(f"🎉 CLOSING COMPLETE FOR {agent_name}")
    logger.info(f"   Successfully Closed: {closed_count}/{len(positions)}")
    logger.info(f"   Failed: {failed_count}")
    logger.info(f"   Total Realized PnL: ${closed_pnl:+.2f}")
    logger.info("═" * 80 + "\n")

    return {
        "agent": agent_name,
        "total_positions": len(positions),
        "closed": closed_count,
        "failed": failed_count,
        "total_pnl": closed_pnl
    }


async def main(agent_filter: str = "both"):
    """Main execution function."""
    logger.info("🎯 Symphony Position Closer - Close ALL Positions")
    logger.info("=" * 80)
    logger.info(f"   Mode: {agent_filter.upper()}")
    logger.info("=" * 80)

    results = []

    # Determine which agents to process
    if agent_filter == "both":
        agents_to_process = ["agdg", "milf"]
    else:
        agents_to_process = [agent_filter]

    # Process each agent
    for agent_key in agents_to_process:
        if agent_key not in AGENTS:
            logger.error(f"Unknown agent: {agent_key}")
            continue

        result = await close_agent_positions(agent_key)
        results.append(result)

    # Grand total summary
    if len(results) > 1:
        logger.info("\n" + "═" * 80)
        logger.info("🏆 GRAND TOTAL SUMMARY")
        logger.info("═" * 80)

        total_positions = sum(r["total_positions"] for r in results)
        total_closed = sum(r["closed"] for r in results)
        total_failed = sum(r["failed"] for r in results)
        total_pnl = sum(r["total_pnl"] for r in results)

        for result in results:
            logger.info(
                f"   {result['agent']}: "
                f"{result['closed']}/{result['total_positions']} closed, "
                f"PnL: ${result['total_pnl']:+.2f}"
            )

        logger.info("─" * 80)
        logger.info(f"   TOTAL POSITIONS: {total_positions}")
        logger.info(f"   TOTAL CLOSED: {total_closed}")
        logger.info(f"   TOTAL FAILED: {total_failed}")
        logger.info(f"   TOTAL REALIZED PnL: ${total_pnl:+.2f}")
        logger.info("═" * 80)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Close all Symphony positions for AGDG and/or MILF agents"
    )
    parser.add_argument(
        "--agent",
        choices=["agdg", "milf", "both"],
        default="both",
        help="Which agent(s) to process (default: both)"
    )
    args = parser.parse_args()

    asyncio.run(main(args.agent))
