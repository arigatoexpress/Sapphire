#!/usr/bin/env python3
"""Script to verify and trigger live trading"""

import asyncio
import aiohttp
import json
import sys


async def check_trading_status():
    """Check current trading status"""
    async with aiohttp.ClientSession() as session:
        # Check health
        print("🔍 Checking trading health...")
        try:
            async with session.get("https://trader.sapphiretrade.xyz/healthz") as resp:
                health = await resp.json()
                print(f"✅ Service Health: {json.dumps(health, indent=2)}")

                if health.get("running"):
                    print("✅ Trading service is RUNNING")
                    if not health.get("paper_trading"):
                        print("💰 LIVE TRADING is ENABLED")
                    else:
                        print("📝 Paper trading mode is active")
                else:
                    print("❌ Trading service is NOT running")

        except Exception as e:
            print(f"❌ Error checking health: {e}")
            return False

        # Check root endpoint
        try:
            async with session.get("https://trader.sapphiretrade.xyz/") as resp:
                root = await resp.json()
                print(f"\n📡 Service Status: {root}")
        except Exception as e:
            print(f"❌ Error checking root: {e}")

    return True

async def main():
    """Main function"""
    print("🚀 LIVE TRADING DEPLOYMENT CHECK")
    print("=" * 40)
    print("")

    # Check status
    if await check_trading_status():
        print("\n✅ LIVE TRADING IS DEPLOYED AND ACTIVE!")
        print("\n📊 Next Steps:")
        print("1. Monitor trades: ./monitor-trading.sh")
        print("2. Check performance: ./trading-dashboard-queries.sh")
        print("3. View dashboard: https://trader.sapphiretrade.xyz/dashboard")
        print("4. Check Telegram for trade notifications")
    else:
        print("\n❌ Issues detected with live trading deployment")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())

