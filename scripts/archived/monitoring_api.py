#!/usr/bin/env python3
"""
Sapphire Monitoring API
Simple interface for the existing Telegram bot to query monitoring data
"""

import json

from alert_system import TradingAlertSystem
from pnl_tracker import PnLTracker

# Import monitoring modules
from trade_log_monitor import TradeLogMonitor


class MonitoringAPI:
    """API for external bot integration"""
    
    def __init__(self):
        self.monitor = TradeLogMonitor()
        self.pnl = PnLTracker()
        self.alerts = TradingAlertSystem()
    
    def get_status(self) -> dict:
        """Get system status"""
        self.monitor.scan_logs(days=1)
        positions = self.monitor.get_position_summary()
        summary = self.pnl.get_summary()
        
        return {
            'status': 'running',
            'mode': 'LIVE',
            'positions_count': len(positions),
            'trades_today': summary['today_trades'],
            'total_trades': summary['total_trades'],
            'today_pnl': summary['today_net'],
            'total_pnl': summary['net_pnl'],
            'positions': {sym: {'qty': p['qty'], 'avg_cost': p['cost_basis']} 
                         for sym, p in positions.items()}
        }
    
    def get_positions(self) -> list:
        """Get current positions"""
        self.monitor.scan_logs(days=7)
        positions = self.monitor.get_position_summary()
        
        return [
            {
                'symbol': sym,
                'quantity': p['qty'],
                'avg_cost': p['cost_basis'],
                'trades': p['trades']
            }
            for sym, p in sorted(positions.items())
        ]
    
    def get_pnl(self) -> dict:
        """Get P&L summary"""
        summary = self.pnl.get_summary()
        return {
            'today_realized': summary['today_realized'],
            'today_fees': summary['today_fees'],
            'today_net': summary['today_net'],
            'total_realized': summary['total_realized_pnl'],
            'total_fees': summary['total_fees'],
            'total_net': summary['net_pnl'],
            'total_trades': summary['total_trades']
        }
    
    def get_trades(self, days: int = 1) -> list:
        """Get recent trades"""
        self.monitor.scan_logs(days=days)
        trades = sorted(self.monitor.trades, key=lambda x: x['timestamp'], reverse=True)
        
        return [
            {
                'timestamp': t['timestamp'],
                'side': t['side'],
                'symbol': t['symbol'],
                'size': t['size'],
                'price': t.get('price')
            }
            for t in trades[:20]
        ]
    
    def get_health(self) -> dict:
        """Get health status"""
        anomalies = self.monitor.check_anomalies()
        
        return {
            'healthy': len(anomalies) == 0,
            'anomalies': anomalies,
            'logs_found': len(self.monitor.trades) > 0
        }
    
    def format_for_telegram(self, data_type: str, data: dict) -> str:
        """Format data for Telegram messages"""
        if data_type == 'status':
            lines = [
                "📊 *System Status*",
                "",
                f"Status: {'✅ Running' if data['status'] == 'running' else '❌ Stopped'}",
                f"Mode: {data['mode']}",
                f"Positions: {data['positions_count']}",
                f"Trades Today: {data['trades_today']}",
                f"Total Trades: {data['total_trades']}",
                f"Today's P&L: ${data['today_pnl']:+.2f}",
            ]
            
            if data['positions']:
                lines.extend(["", "*Positions:*"])
                for sym, p in list(data['positions'].items())[:5]:
                    lines.append(f"• {sym}: {p['qty']:.6f}")
            
            return '\n'.join(lines)
        
        elif data_type == 'positions':
            if not data:
                return "📭 *No open positions*"
            
            lines = ["📊 *Current Positions*", ""]
            for p in data:
                lines.append(
                    f"*{p['symbol']}*\n"
                    f"  Qty: {p['quantity']:.6f}\n"
                    f"  Avg Cost: ${p['avg_cost']:,.2f}\n"
                    f"  Trades: {p['trades']}"
                )
            return '\n'.join(lines)
        
        elif data_type == 'pnl':
            return (
                f"💰 *P&L Report*\n\n"
                f"*Today:*\n"
                f"  Realized: ${data['today_realized']:+.2f}\n"
                f"  Fees: ${data['today_fees']:.2f}\n"
                f"  Net: ${data['today_net']:+.2f}\n\n"
                f"*All-Time:*\n"
                f"  Realized: ${data['total_realized']:+.2f}\n"
                f"  Fees: ${data['total_fees']:.2f}\n"
                f"  Net: ${data['total_net']:+.2f}\n"
                f"  Trades: {data['total_trades']}"
            )
        
        elif data_type == 'trades':
            if not data:
                return "📭 No trades found"
            
            lines = ["🔄 *Recent Trades*", ""]
            for t in data[:10]:
                emoji = "🟢" if t['side'] == 'BUY' else "🔴"
                time = t['timestamp'][11:16] if len(t['timestamp']) > 16 else "--:--"
                price_str = f" @ ${t['price']:,.0f}" if t['price'] else ""
                lines.append(f"{emoji} {time} {t['side']} {t['size']:.4f} {t['symbol']}{price_str}")
            return '\n'.join(lines)
        
        elif data_type == 'health':
            if data['healthy']:
                return "✅ *All Systems Healthy*\n\n• Trading logs found\n• No anomalies detected"
            else:
                lines = ["⚠️ *Health Issues*", ""]
                for a in data['anomalies'][:5]:
                    lines.append(f"• {a}")
                return '\n'.join(lines)
        
        return str(data)


# Simple CLI for testing
def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['status', 'positions', 'pnl', 'trades', 'health'])
    parser.add_argument('--days', type=int, default=1)
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    
    api = MonitoringAPI()
    
    if args.command == 'status':
        data = api.get_status()
    elif args.command == 'positions':
        data = api.get_positions()
    elif args.command == 'pnl':
        data = api.get_pnl()
    elif args.command == 'trades':
        data = api.get_trades(days=args.days)
    elif args.command == 'health':
        data = api.get_health()
    
    if args.json:
        print(json.dumps(data, indent=2))
    else:
        print(api.format_for_telegram(args.command, data))


if __name__ == '__main__':
    main()
