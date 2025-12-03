#!/usr/bin/env python3
"""
Simple Sapphire AI Performance Test
"""

import asyncio
import time
from datetime import datetime, timedelta

class SimpleMonitor:
    def __init__(self):
        self.start_time = datetime.now()
        self.end_time = self.start_time + timedelta(hours=2)
        self.initial_balance = 0
        self.final_balance = 0
        self.trades_attempted = 0
        self.trades_successful = 0
        self.snapshots = []

    async def get_balance(self, service):
        try:
            balance = await service._exchange_client.get_account_balance()
            usdt = sum(float(b['availableBalance']) for b in balance if b['asset'] == 'USDT')
            btc = sum(float(b['availableBalance']) for b in balance if b['asset'] == 'BTC')
            total = usdt + (btc * 95000)
            return total
        except:
            return 0

    async def run_test(self):
        print("🚀 SAPPHIRE AI 2-HOUR PERFORMANCE TEST")
        print("=" * 50)
        print(f"Start: {self.start_time.strftime('%H:%M:%S')}")
        print(f"Duration: 2 hours")
        print("=" * 50)

        from cloud_trader.minimal_trading_service import get_trading_service
        service = get_trading_service()

        if not service._health.running:
            await service.start()

        # Initial balance
        self.initial_balance = await self.get_balance(service)
        print(f"💰 Initial Balance: ${self.initial_balance:.2f}")
        print(f"🤖 Agents: {len(service._agent_states)}")

        # Monitor for 2 hours
        snapshot_time = time.time() + 300

        while datetime.now() < self.end_time:
            if time.time() >= snapshot_time:
                balance = await self.get_balance(service)
                self.snapshots.append(balance)
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 📊 Balance: ${balance:.2f}")
                snapshot_time = time.time() + 300

            remaining = (self.end_time - datetime.now()).total_seconds()
            if remaining < 600:
                print(f"⏰ {remaining/60:.1f} min remaining")

            await asyncio.sleep(10)

        # Final results
        self.final_balance = await self.get_balance(service)
        await self.report()

    async def report(self):
        duration = (datetime.now() - self.start_time).total_seconds() / 3600
        pnl = self.final_balance - self.initial_balance
        pnl_pct = (pnl / self.initial_balance) * 100 if self.initial_balance > 0 else 0

        print("\\n" + "=" * 50)
        print("🎯 PERFORMANCE REPORT")
        print("=" * 50)
        print(f"Duration: {duration:.2f} hours")
        print(f"Start: ${self.initial_balance:.2f}")
        print(f"End: ${self.final_balance:.2f}")
        print(f"P&L: ${pnl:.2f} ({pnl_pct:+.2f}%)")
        print(f"Hourly: ${pnl/duration:.2f}/hr ({pnl_pct/duration:.2f}%/hr)")

        if self.snapshots:
            peak = max(self.snapshots)
            low = min(self.snapshots)
            print(f"Peak: ${peak:.2f}")
            print(f"Low: ${low:.2f}")

        print("\\n🏆 TEST COMPLETE!")

async def main():
    monitor = SimpleMonitor()
    await monitor.run_test()

if __name__ == "__main__":
    asyncio.run(main())
