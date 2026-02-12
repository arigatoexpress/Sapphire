#!/usr/bin/env python3
"""
Aster AGDG Position Closer - Quick script to close profitable positions

Based on the positions shown on Aster website, this will close all
profitable positions (>40% profit) for the AGDG Base Perps agent.
"""

import asyncio
import httpx
import logging
from typing import List, Dict, Any

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Aster configuration
ASTER_API_KEY = "sk_live_Uc_wBaV-HUssilm56xn1-14HQc3dBa0UrtIl3wv61aU"
ASTER_BASE_URL = "https://api.aster.io"

# We'll try to discover the AGDG agent ID by listing all agents
AGDG_AGENT_ID = None  # To be discovered


async def discover_agents(api_key: str) -> List[Dict]:
    """Discover all agents associated with the API key."""
    async with httpx.AsyncClient() as client:
        headers = {"Authorization": f"Bearer {api_key}"}

        # Try to list agents
        try:
            response = await client.get(
                f"{ASTER_BASE_URL}/agents",
                headers=headers
            )
            response.raise_for_status()
            agents = response.json()
            return agents
        except httpx.HTTPStatusError as e:
            logger.error(f"Failed to list agents: {e.response.text}")
            return []


async def get_positions_for_agent(api_key: str, agent_id: str) -> List[Dict]:
    """Get all open positions for a specific agent."""
    async with httpx.AsyncClient() as client:
        headers = {"Authorization": f"Bearer {api_key}"}

        try:
            response = await client.get(
                f"{ASTER_BASE_URL}/agent/positions",
                params={"agentId": agent_id},
                headers=headers
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Failed to get positions for agent {agent_id}: {e.response.text}")
            return []


async def close_position(api_key: str, agent_id: str, batch_id: str) -> Dict:
    """Close a position by batch ID."""
    async with httpx.AsyncClient() as client:
        headers = {"Authorization": f"Bearer {api_key}"}

        payload = {
            "agentId": agent_id,
            "batchId": batch_id
        }

        try:
            response = await client.post(
                f"{ASTER_BASE_URL}/agent/batch-close",
                json=payload,
                headers=headers
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Failed to close position {batch_id}: {e.response.text}")
            return {"status": "error", "message": str(e)}


async def main():
    logger.info("🎯 Aster AGDG Position Closer")
    logger.info("=" * 80)

    # Step 1: Discover agents
    logger.info("\n📊 Step 1: Discovering agents...")
    agents = await discover_agents(ASTER_API_KEY)

    if not agents:
        logger.error("❌ No agents found or failed to list agents")
        logger.info("\nTrying alternative approach: fetching positions without agent ID...")

        # Try to get positions without agent ID (some APIs support this)
        async with httpx.AsyncClient() as client:
            headers = {"Authorization": f"Bearer {ASTER_API_KEY}"}
            try:
                response = await client.get(
                    f"{ASTER_BASE_URL}/agent/positions",
                    headers=headers
                )
                response.raise_for_status()
                positions = response.json()

                if positions:
                    logger.info(f"✅ Found {len(positions)} position(s)")

                    # Try to extract agent ID from first position
                    if positions and "agentId" in positions[0]:
                        agdg_id = positions[0]["agentId"]
                        logger.info(f"   Detected Agent ID: {agdg_id}")

                        # Now process positions
                        await process_and_close_positions(agdg_id, positions)
                    else:
                        logger.error("Could not determine agent ID from positions")
                else:
                    logger.info("No open positions found")

            except httpx.HTTPStatusError as e:
                logger.error(f"❌ Failed to fetch positions: {e.response.text}")
                logger.info("\nℹ️  You may need to provide the AGDG agent ID manually")
                logger.info("   Please check the Aster dashboard for your agent ID")
        return

    # Find AGDG agent (Base Perps)
    logger.info(f"   Found {len(agents)} agent(s)")
    for agent in agents:
        logger.info(f"   - {agent.get('name', 'Unknown')}: {agent.get('id', 'N/A')}")

    # Look for AGDG or Base Perps agent
    agdg_agent = None
    for agent in agents:
        if "agdg" in agent.get("name", "").lower() or "base" in agent.get("name", "").lower():
            agdg_agent = agent
            break

    if not agdg_agent:
        logger.warning("⚠️  Could not auto-detect AGDG agent, using first agent")
        agdg_agent = agents[0]

    agdg_id = agdg_agent.get("id")
    logger.info(f"   Using agent: {agdg_agent.get('name')} ({agdg_id})")

    # Step 2: Get positions
    logger.info(f"\n📊 Step 2: Fetching positions for {agdg_id}...")
    positions = await get_positions_for_agent(ASTER_API_KEY, agdg_id)

    if not positions:
        logger.info("✅ No open positions found!")
        return

    await process_and_close_positions(agdg_id, positions)


async def process_and_close_positions(agent_id: str, positions: List[Dict]):
    """Process and close profitable positions."""
    logger.info(f"   Found {len(positions)} position(s)\n")

    # Analyze positions
    total_pnl = 0.0
    positions_to_close = []

    for pos in positions:
        batch_id = pos.get("batchId", "unknown")
        symbol = pos.get("symbol", "UNKNOWN")
        side = pos.get("side", "UNKNOWN")
        leverage = pos.get("leverage", 0)
        pnl = float(pos.get("unrealizedPnl", 0))
        collateral = float(pos.get("collateral", 0))

        pnl_pct = pnl / collateral if collateral > 0 else 0.0
        total_pnl += pnl

        if pnl_pct >= 0.40:  # 40% profit threshold
            positions_to_close.append({
                "batch_id": batch_id,
                "symbol": symbol,
                "side": side,
                "leverage": leverage,
                "pnl": pnl,
                "pnl_pct": pnl_pct
            })
            logger.info(
                f"🎯 CLOSE: {symbol} {side} {leverage}x | "
                f"PnL: ${pnl:.2f} ({pnl_pct:+.2%}) | BatchID: {batch_id}"
            )
        else:
            logger.info(
                f"📈 KEEP:  {symbol} {side} {leverage}x | "
                f"PnL: ${pnl:.2f} ({pnl_pct:+.2%})"
            )

    # Summary
    logger.info("\n" + "=" * 80)
    logger.info(f"📊 SUMMARY")
    logger.info(f"   Total Positions: {len(positions)}")
    logger.info(f"   To Close: {len(positions_to_close)}")
    logger.info(f"   To Keep: {len(positions) - len(positions_to_close)}")
    logger.info(f"   Total Unrealized PnL: ${total_pnl:+.2f}")
    logger.info("=" * 80 + "\n")

    if not positions_to_close:
        logger.info("✅ No positions meet the 40% profit threshold")
        return

    # Ask for confirmation
    response = input(f"\n🚨 Close {len(positions_to_close)} position(s)? (yes/no): ")
    if response.lower() not in ["yes", "y"]:
        logger.info("❌ Aborted by user")
        return

    # Close positions
    logger.info(f"\n🚀 Closing {len(positions_to_close)} position(s)...\n")

    closed_count = 0
    closed_pnl = 0.0

    for pos_info in positions_to_close:
        batch_id = pos_info["batch_id"]
        symbol = pos_info["symbol"]
        pnl = pos_info["pnl"]
        pnl_pct = pos_info["pnl_pct"]

        logger.info(f"   Closing {symbol} (BatchID: {batch_id})...")
        result = await close_position(ASTER_API_KEY, agent_id, batch_id)

        if result.get("status") == "success" or "success" in str(result).lower():
            logger.info(f"   ✅ Closed {symbol} | Realized PnL: ${pnl:+.2f} ({pnl_pct:+.2%})")
            closed_count += 1
            closed_pnl += pnl
        else:
            logger.error(f"   ❌ Failed to close {symbol}: {result}")

        await asyncio.sleep(0.5)

    # Final summary
    logger.info("\n" + "=" * 80)
    logger.info(f"🎉 CLOSING COMPLETE")
    logger.info(f"   Successfully Closed: {closed_count}/{len(positions_to_close)}")
    logger.info(f"   Total Realized PnL: ${closed_pnl:+.2f}")
    logger.info("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
