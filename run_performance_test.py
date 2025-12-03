#!/usr/bin/env python3
"""
Sapphire AI Performance Test Runner
"""

import asyncio
import time
from datetime import datetime
from performance_test import PerformanceMonitor
from cloud_trader.minimal_trading_service import get_trading_service

# Global performance monitor
performance_monitor = PerformanceMonitor()

# Monkey patch the trading service to report to monitor
original_simulate_trading = None

async def monitored_simulate_trading(self):
    """Monitored version of simulate trading"""
    for agent in self._agent_states.values():
        if agent.active and self.__class__.__dict__.get('_get_random_chance', lambda: 0.05)():  # 5% chance
            try:
                # Select trade parameters
                trade_configs = {
                    "BTCUSDT": {"quantity": 0.0001, "price_range": (95000, 105000)},
                    "ETHUSDT": {"quantity": 0.001, "price_range": (2800, 3200)},
                }
                
                symbol = self.__class__.__dict__.get('_select_random_symbol', lambda: "BTCUSDT")()
                if symbol not in trade_configs:
                    continue
                    
                config = trade_configs[symbol]
                side = self.__class__.__dict__.get('_select_random_side', lambda: "BUY")()
                quantity = config["quantity"]
                
                # Log trade attempt
                performance_monitor.log_trade_attempt(agent.name, symbol, side, quantity)
                
                # Execute real trade
                order_result = await self._exchange_client.place_order(
                    symbol=symbol,
                    side=side.upper(),
                    order_type=self._exchange_client.__class__.__bases__[0].__annotations__.get('place_order', lambda: type('OrderType', (), {'MARKET': 'MARKET'})()).MARKET,
                    quantity=str(quantity),
                    new_client_order_id=f"{agent.id}_{agent.total_trades}_{int(time.time()*1000)}"
                )
                
                if order_result and order_result.get("orderId"):
                    executed_qty = float(order_result.get("executedQty", 0))
                    avg_price = float(order_result.get("avgPrice", 0))
                    
                    if executed_qty > 0 and avg_price > 0:
                        total_value = avg_price * executed_qty
                        
                        # Log successful trade
                        performance_monitor.log_trade_success(agent.name, symbol, side, executed_qty, avg_price, total_value)
                        
                        # Send Telegram notification
                        await self._send_trade_notification(agent, symbol, side, executed_qty, avg_price, total_value, True)
                        
                        print(f"✅ REAL TRADE FILLED: {agent.emoji} {agent.name} - {side} {executed_qty} {symbol} @ ${avg_price} = ${total_value}")
                    else:
                        # Order placed but not filled
                        pass  # Don't log failed trades
                else:
                    performance_monitor.log_error("trade_failed", f"Order placement failed for {agent.name}")
                    
            except Exception as e:
                performance_monitor.log_error("trade_error", f"{agent.name}: {str(e)}")

async def run_performance_test():
    """Run the 2-hour performance test"""
    print("🚀 STARTING SAPPHIRE AI 2-HOUR PERFORMANCE TEST")
    print("=" * 60)
    
    # Setup monitoring
    global original_simulate_trading
    service = get_trading_service()
    original_simulate_trading = service._simulate_agent_trading
    service._simulate_agent_trading = lambda: monitored_simulate_trading(service)
    
    # Start the service
    if not service._health.running:
        await service.start()
    
    # Get initial balance
    initial_balance = await performance_monitor.get_current_balance(service)
    if initial_balance:
        performance_monitor.initial_balance = initial_balance['total_value']
    
    print(f"💰 Initial Portfolio: ${performance_monitor.initial_balance:.2f}")
    print(f"🤖 Agents Active: {len(service._agent_states)}")
    print("\\n🕐 Test will run for 2 hours...\\n")
    
    # Run test for 2 hours
    await performance_monitor.run_test()
    
    # Restore original method
    service._simulate_agent_trading = original_simulate_trading

if __name__ == "__main__":
    asyncio.run(run_performance_test())
