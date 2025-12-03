#!/usr/bin/env python3
"""
Live Sapphire AI Trading Monitor
Real-time performance dashboard
"""

import asyncio
import time
import os
from datetime import datetime, timedelta

class LiveMonitor:
    def __init__(self):
        self.start_time = datetime.now()
        self.last_balance = 0
        self.initial_balance = 0
        self.trade_count = 0
        self.success_count = 0
        
    async def get_system_status(self):
        """Get comprehensive system status"""
        try:
            from cloud_trader.minimal_trading_service import get_trading_service
            service = get_trading_service()
            
            if not service._health.running:
                await service.start()
            
            # Get balance
            balance = await service._exchange_client.get_account_balance()
            usdt = sum(float(b['availableBalance']) for b in balance if b['asset'] == 'USDT')
            btc = sum(float(b['availableBalance']) for b in balance if b['asset'] == 'BTC')
            total = usdt + (btc * 95000)
            
            if self.initial_balance == 0:
                self.initial_balance = total
            
            # Calculate P&L
            pnl = total - self.initial_balance
            pnl_pct = (pnl / self.initial_balance) * 100 if self.initial_balance > 0 else 0
            
            # Time elapsed
            elapsed = datetime.now() - self.start_time
            hours = elapsed.total_seconds() / 3600
            
            return {
                'portfolio': total,
                'usdt': usdt,
                'btc': btc,
                'pnl': pnl,
                'pnl_pct': pnl_pct,
                'agents': len(service._agent_states),
                'hours': hours,
                'hourly_rate': pnl / hours if hours > 0 else 0
            }
        except Exception as e:
            return {'error': str(e)}

    def clear_screen(self):
        """Clear terminal screen"""
        os.system('clear')

    def print_header(self):
        """Print dashboard header"""
        print("🚀 SAPPHIRE AI TRADING - LIVE MONITORING DASHBOARD")
        print("=" * 60)
        print(f"Started: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Running: {(datetime.now() - self.start_time).total_seconds() / 3600:.2f} hours")
        print("=" * 60)

    def print_status(self, status):
        """Print current status"""
        if 'error' in status:
            print(f"❌ SYSTEM ERROR: {status['error']}")
            return
            
        print("💰 PORTFOLIO STATUS:")
        print(f"   Total Value: ${status['portfolio']:.2f}")
        print(f"   USDT: ${status['usdt']:.2f}")
        print(f"   BTC: {status['btc']:.6f} (${status['btc']*95000:.2f})")
        print()
        
        pnl_color = "🟢" if status['pnl'] >= 0 else "🔴"
        print("📈 PERFORMANCE:")
        print(f"   {pnl_color} P&L: ${status['pnl']:.2f} ({status['pnl_pct']:+.2f}%)")
        print(f"   💹 Hourly Rate: ${status['hourly_rate']:.2f}/hour")
        print()
        
        print("🤖 SYSTEM STATUS:")
        print(f"   AI Agents: {status['agents']} active")
        print("   Trading Mode: Real Money")
        print("   Status: Online ✅")
        print()
        
        # Progress bar for 2-hour test
        progress = min(100, (status['hours'] / 2) * 100)
        filled = int(progress / 5)
        bar = "█" * filled + "░" * (20 - filled)
        print(f"⏱️  TEST PROGRESS: [{bar}] {progress:.1f}%")
        print()

    async def run_monitor(self):
        """Run the live monitoring dashboard"""
        print("Starting live monitoring... Press Ctrl+C to stop")
        
        while True:
            try:
                status = await self.get_system_status()
                
                self.clear_screen()
                self.print_header()
                self.print_status(status)
                
                print("🔄 Refreshing every 30 seconds...")
                print("📱 Telegram notifications active")
                print("💻 Frontend: http://localhost:3000")
                
                await asyncio.sleep(30)
                
            except KeyboardInterrupt:
                print("\n🛑 Monitoring stopped by user")
                break
            except Exception as e:
                print(f"\n❌ Monitor error: {e}")
                await asyncio.sleep(5)

async def main():
    monitor = LiveMonitor()
    await monitor.run_monitor()

if __name__ == "__main__":
    asyncio.run(main())
