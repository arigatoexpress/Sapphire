#!/usr/bin/env python3
"""
Sapphire P&L Tracker
Tracks realized and unrealized P&L from actual trades
"""

import json
from datetime import datetime
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Tuple


class PnLTracker:
    """Track profit and loss from trading activity"""
    
    def __init__(self, data_dir: str = "~/.sapphire_trading"):
        self.data_dir = Path(data_dir).expanduser()
        self.data_dir.mkdir(exist_ok=True)
        self.state_file = self.data_dir / 'pnl_state.json'
        self.state = self._load_state()
    
    def _load_state(self) -> Dict:
        """Load P&L state"""
        if self.state_file.exists():
            with open(self.state_file) as f:
                return json.load(f)
        return {
            'positions': {},  # symbol -> {qty, avg_cost, realized_pnl}
            'daily_pnl': {},  # date -> {realized, fees, trades}
            'total_realized': 0.0,
            'total_fees': 0.0,
            'total_trades': 0
        }
    
    def _save_state(self):
        """Save P&L state"""
        with open(self.state_file, 'w') as f:
            json.dump(self.state, f, indent=2)
    
    def process_trade(self, trade: Dict) -> Dict:
        """Process a trade and update P&L"""
        symbol = trade.get('symbol', 'UNKNOWN')
        side = trade.get('side', '').upper()
        size = trade.get('size', 0)
        price = trade.get('price', 0) or 0
        timestamp = trade.get('timestamp', datetime.now().isoformat())
        date = timestamp[:10]
        
        # Initialize position if new
        if symbol not in self.state['positions']:
            self.state['positions'][symbol] = {
                'qty': 0.0,
                'avg_cost': 0.0,
                'realized_pnl': 0.0,
                'trades': 0
            }
        
        pos = self.state['positions'][symbol]
        trade_pnl = 0.0
        
        if side == 'BUY':
            # Update average cost basis
            total_cost = pos['avg_cost'] * pos['qty'] + price * size
            pos['qty'] += size
            pos['avg_cost'] = total_cost / pos['qty'] if pos['qty'] > 0 else 0
        else:  # SELL
            # Calculate realized P&L
            if pos['qty'] > 0:
                trade_pnl = (price - pos['avg_cost']) * min(size, pos['qty'])
                pos['realized_pnl'] += trade_pnl
                self.state['total_realized'] += trade_pnl
            
            pos['qty'] -= size
        
        pos['trades'] += 1
        self.state['total_trades'] += 1
        
        # Update daily stats
        if date not in self.state['daily_pnl']:
            self.state['daily_pnl'][date] = {
                'realized': 0.0,
                'fees': 0.0,
                'trades': 0,
                'volume': 0.0
            }
        
        daily = self.state['daily_pnl'][date]
        daily['realized'] += trade_pnl
        daily['trades'] += 1
        daily['volume'] += size * price
        
        # Estimate fee (0.1% typical)
        fee = size * price * 0.001
        daily['fees'] += fee
        self.state['total_fees'] += fee
        
        self._save_state()
        
        return {
            'symbol': symbol,
            'side': side,
            'size': size,
            'price': price,
            'trade_pnl': trade_pnl,
            'position_qty': pos['qty'],
            'position_avg_cost': pos['avg_cost'],
            'position_realized': pos['realized_pnl']
        }
    
    def get_position_pnl(self, symbol: str, current_price: float = None) -> Dict:
        """Calculate unrealized P&L for a position"""
        pos = self.state['positions'].get(symbol, {'qty': 0, 'avg_cost': 0, 'realized_pnl': 0})
        
        unrealized = 0.0
        if current_price and pos['qty'] != 0:
            unrealized = (current_price - pos['avg_cost']) * pos['qty']
        
        return {
            'symbol': symbol,
            'quantity': pos['qty'],
            'avg_cost': pos['avg_cost'],
            'realized_pnl': pos['realized_pnl'],
            'unrealized_pnl': unrealized,
            'total_pnl': pos['realized_pnl'] + unrealized
        }
    
    def get_summary(self) -> Dict:
        """Get overall P&L summary"""
        total_unrealized = 0.0
        for symbol, pos in self.state['positions'].items():
            total_unrealized += (0 - pos['avg_cost']) * pos['qty']  # Without current prices
        
        today = datetime.now().strftime('%Y-%m-%d')
        today_stats = self.state['daily_pnl'].get(today, {'realized': 0, 'fees': 0, 'trades': 0})
        
        return {
            'total_realized_pnl': self.state['total_realized'],
            'total_fees': self.state['total_fees'],
            'total_trades': self.state['total_trades'],
            'net_pnl': self.state['total_realized'] - self.state['total_fees'],
            'today_realized': today_stats['realized'],
            'today_fees': today_stats['fees'],
            'today_trades': today_stats['trades'],
            'today_net': today_stats['realized'] - today_stats['fees'],
            'positions': len(self.state['positions']),
            'active_dates': len(self.state['daily_pnl'])
        }
    
    def generate_report(self) -> str:
        """Generate P&L report"""
        summary = self.get_summary()
        
        lines = [
            "═" * 50,
            "💰 P&L REPORT",
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "═" * 50,
            "",
            "📊 ALL-TIME PERFORMANCE:",
            f"  Realized P&L:  ${summary['total_realized_pnl']:+.2f}",
            f"  Total Fees:    ${summary['total_fees']:.2f}",
            f"  Net P&L:       ${summary['net_pnl']:+.2f}",
            f"  Total Trades:  {summary['total_trades']}",
            "",
            "📅 TODAY'S PERFORMANCE:",
            f"  Realized P&L:  ${summary['today_realized']:+.2f}",
            f"  Fees:          ${summary['today_fees']:.2f}",
            f"  Net P&L:       ${summary['today_net']:+.2f}",
            f"  Trades:        {summary['today_trades']}",
            "",
            "📍 OPEN POSITIONS:"
        ]
        
        for symbol, pos in sorted(self.state['positions'].items()):
            if abs(pos['qty']) > 0.000001:
                lines.append(f"  {symbol}: {pos['qty']:.6f} @ ${pos['avg_cost']:,.2f} "
                           f"(Realized: ${pos['realized_pnl']:+.2f})")
        
        if len([p for p in self.state['positions'].values() if abs(p['qty']) > 0.000001]) == 0:
            lines.append("  No open positions")
        
        lines.extend([
            "",
            "📈 DAILY HISTORY (Last 7 days):"
        ])
        
        dates = sorted(self.state['daily_pnl'].keys(), reverse=True)[:7]
        for date in dates:
            day = self.state['daily_pnl'][date]
            lines.append(f"  {date}: ${day['realized']:+.2f} ({day['trades']} trades)")
        
        lines.append("")
        lines.append("═" * 50)
        
        return "\n".join(lines)


def main():
    """CLI for P&L tracker"""
    import argparse
    parser = argparse.ArgumentParser(description='Sapphire P&L Tracker')
    parser.add_argument('--report', action='store_true', help='Show P&L report')
    parser.add_argument('--position', help='Show position P&L for symbol')
    parser.add_argument('--price', type=float, help='Current price for unrealized calc')
    args = parser.parse_args()
    
    tracker = PnLTracker()
    
    if args.position:
        pnl = tracker.get_position_pnl(args.position, args.price)
        print(f"\n📍 {args.position} Position:")
        print(f"  Quantity: {pnl['quantity']:.6f}")
        print(f"  Avg Cost: ${pnl['avg_cost']:,.2f}")
        print(f"  Realized: ${pnl['realized_pnl']:+.2f}")
        if args.price:
            print(f"  Unrealized: ${pnl['unrealized_pnl']:+.2f}")
            print(f"  Total: ${pnl['total_pnl']:+.2f}")
    else:
        print(tracker.generate_report())


if __name__ == '__main__':
    main()
