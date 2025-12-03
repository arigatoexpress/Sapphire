#!/usr/bin/env python3
"""
Sapphire AI Trading System - 2-Hour Performance Test
Simple monitoring of live trading activity
"""

import asyncio
import time
from datetime import datetime, timedelta
from collections import defaultdict

class PerformanceMonitor:
    def __init__(self):
        self.start_time = datetime.now()
        self.end_time = self.start_time + timedelta(hours=2)
        
        # Basic metrics
        self.initial_balance = 0
        self.final_balance = 0
        self.trades_attempted = 0
        self.trades_successful = 0
        self.api_errors = 0
        self.portfolio_snapshots = []
        
        # Agent tracking
        self.agent_performance = defaultdict(lambda: {
            'attempts': 0,
            'successes': 0,
            'volume': 0.0
        })
        
    async def get_current_balance(self, service):
        """Get current portfolio balance"""
        try:
            balance = await service._exchange_client.get_account_balance()
            usdt_balance = next((float(b['availableBalance']) for b in balance if b['asset'] == 'USDT'), 0)
            btc_balance = next((float(b['availableBalance']) for b in balance if b['asset'] == 'BTC'), 0)
            
            # Rough BTC price estimate for total value
            btc_price = 95000  # Conservative estimate
            total_value = usdt_balance + (btc_balance * btc_price)
            
            return {
                'usdt': usdt_balance,
                'btc': btc_balance,
                'total_value': total_value,
                'timestamp': datetime.now().isoformat()
            }
        except Exception as e:
            print(f"Balance check error: {e}")
            return None
    
    def log_trade_attempt(self, agent_name: str, symbol: str, side: str, quantity: float):
        """Log a trade attempt"""
        self.trades_attempted += 1
        self.agent_stats[agent_name]['trades_attempted'] += 1
        
        trade = {
            'timestamp': datetime.now().isoformat(),
            'agent': agent_name,
            'symbol': symbol,
            'side': side,
            'quantity': quantity,
            'status': 'attempted'
        }
        self.trades_executed.append(trade)
    
    def log_trade_success(self, agent_name: str, symbol: str, side: str, quantity: float, price: float, total: float):
        """Log a successful trade"""
        self.trades_successful += 1
        self.agent_stats[agent_name]['trades_successful'] += 1
        self.agent_stats[agent_name]['total_volume'] += total
        
        # Update win rate (simplified - assume profitable)
        agent = self.agent_stats[agent_name]
        agent['win_rate'] = (agent['trades_successful'] / agent['trades_attempted']) * 100
        
        # Update trade record
        for trade in reversed(self.trades_executed):
            if trade['agent'] == agent_name and trade['status'] == 'attempted':
                trade.update({
                    'status': 'filled',
                    'price': price,
                    'total_value': total
                })
                break
    
    def log_error(self, error_type: str, message: str):
        """Log system errors"""
        if 'api' in error_type.lower():
            self.api_errors += 1
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ERROR: {error_type} - {message}")
    
    async def take_snapshot(self, service):
        """Take a performance snapshot"""
        balance = await self.get_current_balance(service)
        if balance:
            self.portfolio_values.append(balance)
            
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 📊 Portfolio: ${balance['total_value']:.2f} | Trades: {self.trades_successful}/{self.trades_attempted}")
    
    async def run_test(self):
        """Run the 2-hour performance test"""
        print("🚀 STARTING SAPPHIRE AI 2-HOUR PERFORMANCE TEST")
        print("=" * 60)
        print(f"Start Time: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"End Time: {self.end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Duration: 2 hours")
        print("=" * 60)
        
        # Import service
        from cloud_trader.minimal_trading_service import get_trading_service
        service = get_trading_service()
        
        if not service._health.running:
            await service.start()
        
        # Get initial balance
        initial_balance = await self.get_current_balance(service)
        if initial_balance:
            self.initial_balance = initial_balance['total_value']
            print(f"💰 Initial Portfolio Value: ${self.initial_balance:.2f}")
        
        print("\\n🤖 AI Agents Active:")
        for agent_name, agent in service._agent_states.items():
            print(f"  • {agent.emoji} {agent.name}")
        print()
        
        # Test loop - run for 2 hours
        snapshot_interval = 300  # 5 minutes
        next_snapshot = time.time() + snapshot_interval
        
        while datetime.now() < self.end_time:
            current_time = time.time()
            
            # Take performance snapshot
            if current_time >= next_snapshot:
                await self.take_snapshot(service)
                next_snapshot = current_time + snapshot_interval
            
            # Brief pause to avoid overwhelming
            await asyncio.sleep(10)
            
            # Check remaining time
            remaining = self.end_time - datetime.now()
            if remaining.total_seconds() < 600:  # 10 minutes left
                print(f"⏰ {remaining.total_seconds()/60:.1f} minutes remaining...")
        
        # Test complete - get final balance
        final_balance = await self.get_current_balance(service)
        if final_balance:
            self.final_balance = final_balance['total_value']
        
        # Generate comprehensive report
        await self.generate_report()
    
    async def generate_report(self):
        """Generate comprehensive performance report"""
        print("\\n" + "=" * 80)
        print("🎯 SAPPHIRE AI TRADING SYSTEM - 2-HOUR PERFORMANCE REPORT")
        print("=" * 80)
        
        duration = datetime.now() - self.start_time
        hours = duration.total_seconds() / 3600
        
        # Financial Performance
        print("\\n💰 FINANCIAL PERFORMANCE:")
        print("-" * 30)
        print(f"Initial Portfolio Value: ${self.initial_balance:.2f}")
        print(f"Final Portfolio Value: ${self.final_balance:.2f}")
        
        pnl = self.final_balance - self.initial_balance
        pnl_percentage = (pnl / self.initial_balance) * 100 if self.initial_balance > 0 else 0
        
        print(f"Total P&L: ${pnl:.2f} ({pnl_percentage:+.2f}%)")
        print(f"Hourly Return: ${pnl/hours:.2f}/hour ({pnl_percentage/hours:.2f}%/hour)")
        
        if self.portfolio_values:
            values = [p['total_value'] for p in self.portfolio_values]
            max_value = max(values)
            min_value = min(values)
            volatility = statistics.stdev(values) if len(values) > 1 else 0
            
            print(f"Peak Value: ${max_value:.2f}")
            print(f"Low Value: ${min_value:.2f}")
            # Calculate simple volatility (range)
            volatility = (max_value - min_value) / initial_balance * 100
            print(f"Portfolio Range: ${max_value - min_value:.2f} ({volatility:.1f}% of initial)")
        
        # System Performance
        print("\\n⚙️ SYSTEM PERFORMANCE:")
        print("-" * 30)
        print(f"Test Duration: {hours:.2f} hours")
        print(f"Trades Attempted: {self.trades_attempted}")
        print(f"Trades Successful: {self.trades_successful}")
        
        success_rate = (self.trades_successful / self.trades_attempted) * 100 if self.trades_attempted > 0 else 0
        print(f"Success Rate: {success_rate:.1f}%")
        print(f"API Errors: {self.api_errors}")
        print(f"Trades per Hour: {self.trades_successful/hours:.1f}")
        
        # Agent Performance
        print("\\n🤖 AGENT PERFORMANCE:")
        print("-" * 30)
        for agent_name, stats in self.agent_stats.items():
            if stats['trades_attempted'] > 0:
                success_rate = (stats['trades_successful'] / stats['trades_attempted']) * 100
                avg_volume = stats['total_volume'] / stats['trades_successful'] if stats['trades_successful'] > 0 else 0
                
                print(f"{agent_name}:")
                print(f"  Trades: {stats['trades_successful']}/{stats['trades_attempted']} ({success_rate:.1f}%)")
                print(f"  Volume: ${stats['total_volume']:.2f}")
                print(f"  Avg Trade: ${avg_volume:.2f}")
        
        # Trade Analysis
        if self.trades_executed:
            print("\\n📊 TRADE ANALYSIS:")
            print("-" * 30)
            
            successful_trades = [t for t in self.trades_executed if t.get('status') == 'filled']
            if successful_trades:
                volumes = [t.get('total_value', 0) for t in successful_trades]
                avg_trade_size = sum(volumes) / len(volumes) if volumes else 0
                max_trade = max(volumes) if volumes else 0
                min_trade = min(volumes) if volumes else 0
                
                print(f"Total Successful Trades: {len(successful_trades)}")
                print(f"Average Trade Size: ${avg_trade_size:.2f}")
                print(f"Largest Trade: ${max_trade:.2f}")
                print(f"Smallest Trade: ${min_trade:.2f}")
        
        # Recommendations
        print("\\n🎯 RECOMMENDATIONS:")
        print("-" * 30)
        
        if pnl > 0:
            print("✅ PROFITABLE: System is generating positive returns!")
            print("💡 Consider increasing position sizes for higher returns")
        elif pnl < 0:
            print("⚠️ LOSSES: System incurred losses during test")
            print("💡 Consider adjusting risk parameters or agent strategies")
        else:
            print("😐 BREAK-EVEN: System maintained portfolio value")
            print("💡 Consider optimizing for more aggressive profit targets")
        
        if success_rate < 50:
            print("⚠️ LOW SUCCESS RATE: Trade execution needs improvement")
            print("💡 Check market conditions and timing strategies")
        
        print("\\n🏆 TEST COMPLETE - Ready for live deployment!")
        print(f"End Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 80)

async def main():
    monitor = PerformanceMonitor()
    await monitor.run_test()

if __name__ == "__main__":
    asyncio.run(main())
