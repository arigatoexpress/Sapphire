#!/usr/bin/env python3
"""
Sapphire Trading Log Monitor
Monitors live trading activity from autonomous trading system logs
Replaces CoinGecko price tracking with actual trade data
"""

import argparse
import json
import re
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path


class TradeLogMonitor:
    """Monitor and analyze live trading logs"""
    
    def __init__(self, log_dir: str = "~/trading-logs"):
        self.log_dir = Path(log_dir).expanduser()
        self.trades: list[dict] = []
        self.daily_stats = defaultdict(lambda: {
            'trades': 0, 'buy_volume': 0.0, 'sell_volume': 0.0,
            'buy_count': 0, 'sell_count': 0, 'pnl': 0.0
        })
        
    def parse_log_line(self, line: str) -> dict | None:
        """Extract trade from log line"""
        # Extract timestamp from log line (e.g., "2026-02-25 12:35:22")
        ts_match = re.match(r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})', line)
        if ts_match:
            timestamp_str = ts_match.group(1).replace(' ', 'T')
        else:
            timestamp_str = datetime.now().isoformat()[:19]
        
        # Pattern for: "[TRADE] LIVE Trade: BUY 0.0001 BTC-USDC @ 84350.50"
        # Must have [TRADE] tag to avoid duplicates
        trade_pattern = re.search(
            r'\[TRADE\].*?(BUY|SELL)\s+([\d.]+)\s+([A-Z]+(?:-[A-Z]+)?)\s*(?:@\s*([\d.]+))?',
            line, re.IGNORECASE
        )
        if trade_pattern:
            return {
                'timestamp': timestamp_str,
                'mode': 'LIVE',
                'side': trade_pattern.group(1).upper(),
                'size': float(trade_pattern.group(2)),
                'symbol': trade_pattern.group(3).upper(),
                'price': float(trade_pattern.group(4)) if trade_pattern.group(4) else None,
                'raw_line': line.strip()
            }
        
        return None
    
    def scan_logs(self, days: int = 1) -> list[dict]:
        """Scan log files for trades"""
        self.trades = []
        self.daily_stats.clear()
        cutoff = datetime.now() - timedelta(days=days)
        
        log_files = [
            self.log_dir / "trading.log",
            self.log_dir / "autonomous-trading.log",
            self.log_dir / "daemon.log",
        ]
        
        # Add home dir trading logs if different from log_dir
        home_logs = Path.home() / "trading-logs" / "trading.log"
        if home_logs.resolve() != (self.log_dir / "trading.log").resolve():
            log_files.append(home_logs)
        
        seen = set()  # Deduplication
        
        for log_file in log_files:
            if log_file.exists():
                with open(log_file) as f:
                    for line in f:
                        trade = self.parse_log_line(line)
                        if trade:
                            # Create dedup key
                            key = (trade['timestamp'], trade['side'], trade['symbol'], trade['size'])
                            if key not in seen:
                                seen.add(key)
                                self.trades.append(trade)
        
        return self.trades
    
    def calculate_daily_stats(self) -> dict:
        """Calculate statistics by day"""
        for trade in self.trades:
            date = trade['timestamp'][:10]  # YYYY-MM-DD
            stats = self.daily_stats[date]
            stats['trades'] += 1
            
            if trade['side'] == 'BUY':
                stats['buy_count'] += 1
                stats['buy_volume'] += trade.get('size', 0)
            else:
                stats['sell_count'] += 1
                stats['sell_volume'] += trade.get('size', 0)
        
        return dict(self.daily_stats)
    
    def get_position_summary(self) -> dict:
        """Calculate current positions from trade history"""
        positions = defaultdict(lambda: {'qty': 0.0, 'cost_basis': 0.0, 'trades': 0})
        
        for trade in self.trades:
            symbol = trade['symbol']
            size = trade.get('size', 0)
            price = trade.get('price', 0) or 0
            
            if trade['side'] == 'BUY':
                positions[symbol]['qty'] += size
                if price:
                    positions[symbol]['cost_basis'] = (
                        (positions[symbol]['cost_basis'] * (positions[symbol]['qty'] - size)) + 
                        (price * size)
                    ) / positions[symbol]['qty'] if positions[symbol]['qty'] > 0 else price
            else:  # SELL
                positions[symbol]['qty'] -= size
            
            positions[symbol]['trades'] += 1
        
        # Filter out zero positions
        return {s: p for s, p in positions.items() if abs(p['qty']) > 0.000001}
    
    def generate_report(self) -> str:
        """Generate human-readable trading report"""
        if not self.trades:
            return "📊 No trades found in logs"
        
        lines = [
            "═" * 50,
            "📈 SAPPHIRE TRADING REPORT",
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "═" * 50,
            "",
            f"📋 Total Trades: {len(self.trades)}",
            "",
            "📍 CURRENT POSITIONS:",
            "─" * 30
        ]
        
        positions = self.get_position_summary()
        if positions:
            for symbol, pos in sorted(positions.items()):
                lines.append(f"  {symbol}: {pos['qty']:.6f} @ ~${pos['cost_basis']:,.2f} ({pos['trades']} trades)")
        else:
            lines.append("  No open positions")
        
        lines.extend([
            "",
            "📅 DAILY ACTIVITY:",
            "─" * 30
        ])
        
        daily = self.calculate_daily_stats()
        for date in sorted(daily.keys(), reverse=True)[:7]:
            stats = daily[date]
            lines.append(f"  {date}: {stats['trades']} trades | "
                        f"{stats['buy_count']} buys ({stats['buy_volume']:.4f}) | "
                        f"{stats['sell_count']} sells ({stats['sell_volume']:.4f})")
        
        lines.extend([
            "",
            "🔄 RECENT TRADES:",
            "─" * 30
        ])
        
        for trade in sorted(self.trades, key=lambda x: x['timestamp'], reverse=True)[:10]:
            emoji = "🟢" if trade['side'] == 'BUY' else "🔴"
            price_str = f" @ ${trade['price']:,.2f}" if trade['price'] else ""
            lines.append(f"  {emoji} {trade['timestamp'][11:19]} {trade['side']} "
                        f"{trade['size']} {trade['symbol']}{price_str}")
        
        lines.append("")
        lines.append("═" * 50)
        
        return "\n".join(lines)
    
    def check_anomalies(self) -> list[str]:
        """Check for unusual trading activity"""
        alerts = []
        
        # Check for no trades in last hour (if market is open)
        now = datetime.now()
        hour_ago = now - timedelta(hours=1)
        recent_trades = [t for t in self.trades if t['timestamp'] > hour_ago.isoformat()]
        
        if not recent_trades and now.hour in range(9, 17):  # Market hours
            alerts.append("⚠️ No trades in last hour during market hours")
        
        # Check for trade burst (>5 trades in 5 minutes)
        five_min_ago = now - timedelta(minutes=5)
        burst_trades = [t for t in self.trades if t['timestamp'] > five_min_ago.isoformat()]
        if len(burst_trades) > 5:
            alerts.append(f"🚨 Trade burst detected: {len(burst_trades)} trades in 5 minutes")
        
        # Check daily trade limit (50/day)
        today = now.strftime('%Y-%m-%d')
        daily_count = len([t for t in self.trades if t['timestamp'].startswith(today)])
        if daily_count > 45:
            alerts.append(f"⚠️ Approaching daily limit: {daily_count}/50 trades")
        
        # Check for large trades (>$50)
        for trade in self.trades[-10:]:
            if trade.get('price') and trade['size'] * trade['price'] > 50:
                alerts.append(f"🚨 Large trade detected: {trade['side']} {trade['size']} {trade['symbol']}")
        
        return alerts


def main():
    parser = argparse.ArgumentParser(description='Sapphire Trading Log Monitor')
    parser.add_argument('--log-dir', default='~/trading-logs', help='Log directory path')
    parser.add_argument('--days', type=int, default=1, help='Days of history to scan')
    parser.add_argument('--watch', action='store_true', help='Continuous monitoring mode')
    parser.add_argument('--json', action='store_true', help='Output as JSON')
    args = parser.parse_args()
    
    monitor = TradeLogMonitor(args.log_dir)
    monitor.scan_logs(days=args.days)
    
    if args.json:
        print(json.dumps({
            'trades': monitor.trades,
            'positions': monitor.get_position_summary(),
            'daily_stats': monitor.calculate_daily_stats(),
            'anomalies': monitor.check_anomalies()
        }, indent=2))
    else:
        print(monitor.generate_report())
        
        anomalies = monitor.check_anomalies()
        if anomalies:
            print("\n" + "⚠️ ANOMALIES DETECTED:")
            for alert in anomalies:
                print(f"  {alert}")
    
    if args.watch:
        print("\n👀 Watching for new trades... (Ctrl+C to stop)")
        import time
        try:
            while True:
                time.sleep(30)
                new_trades = monitor.scan_logs(days=1)
                if new_trades:
                    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] {len(new_trades)} trades logged")
        except KeyboardInterrupt:
            print("\n👋 Monitoring stopped")


if __name__ == '__main__':
    main()
