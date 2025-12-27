import asyncio
import logging
import os

from dotenv import load_dotenv

# Load env
load_dotenv("local.env")

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("active_trading_verify")

from cloud_trader.definitions import MinimalAgentState
from cloud_trader.trading_service import MinimalTradingService


async def verify_loop():
    print("🚀 Verifying Active Trading Loop...")
    service = MinimalTradingService()

    # Manually init components normally done in start()
    await service._init_online_components()

    # 1. Verify Market Structure Injection
    print("\n1. Checking Symbol Injection...")
    if "MON-USDC" in service._market_structure:
        print("   ✅ MON-USDC found in market structure (Injection working)")
    else:
        print("   ❌ MON-USDC NOT found!")
        return

    # 2. Verify Synthetic Data & Analysis
    print("\n2. Verifying Analysis (Synthetic Data)...")
    agent = service._agent_states.get("trend-momentum-agent")
    if not agent:
        print("   ❌ Agent not found")
        return

    symbol = "MON-USDC"
    analysis = await service._analyze_market_for_agent(agent, symbol)
    print(f"   📊 Analysis Result: {analysis}")

    if analysis["signal"] in ["BUY", "SELL", "NEUTRAL"]:
        print("   ✅ Analysis Engine returned valid signal")
    else:
        print("   ❌ Analysis Failed")

    # 3. Verify Execution Routing (Real Trade Attempt)
    # We will force a small trade to verify routing
    print("\n3. Verifying Execution Routing (MON Swap)...")

    # Mock specific thesis
    thesis = "Verification Trade: Active Trading System Check"
    quantity_float = 1.0  # 1 MON
    side = "BUY"

    # We call _execute_trade_order directly
    # This should hit our injected Symphony logic
    await service._execute_trade_order(
        agent=agent,
        symbol=symbol,
        side=side,
        quantity_float=quantity_float,
        thesis=thesis,
        is_closing=False,
    )

    print("\n4. Verifying Perp Routing (SOL Perp)...")
    symbol_perp = "SOL-USDC"
    await service._execute_trade_order(
        agent=agent,  # Using same agent for simplicity
        symbol=symbol_perp,
        side="BUY",  # Long
        quantity_float=0.1,  # 0.1 SOL
        thesis=thesis,
        is_closing=False,
    )

    print("\n✅ Verification Complete. Check logs above for 'Symphony Trade Success'.")
    await service._exchange_client.close()
    if service.symphony:
        await service.symphony.close()


if __name__ == "__main__":
    asyncio.run(verify_loop())
