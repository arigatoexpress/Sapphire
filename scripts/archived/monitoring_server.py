#!/usr/bin/env python3
"""
Sapphire Monitoring Server
Simple HTTP API for trading monitoring
Runs on Pi - bot queries it via HTTP (no import needed)
"""

import json
import sys
from pathlib import Path
from datetime import datetime

# Try to import monitoring modules
try:
    from trade_log_monitor import TradeLogMonitor
    from pnl_tracker import PnLTracker
    from alert_system import TradingAlertSystem
    MONITORING_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Could not import monitoring modules: {e}")
    MONITORING_AVAILABLE = False

# Try Flask first, fall back to http.server
try:
    from flask import Flask, jsonify
    HAS_FLASK = True
except ImportError:
    HAS_FLASK = False
    from http.server import HTTPServer, BaseHTTPRequestHandler
    import urllib.parse

PORT = 18890

if HAS_FLASK and MONITORING_AVAILABLE:
    app = Flask(__name__)
    monitor = TradeLogMonitor()
    pnl = PnLTracker()
    alerts = TradingAlertSystem()
    
    @app.route('/api/status', methods=['GET'])
    def api_status():
        monitor.scan_logs(days=1)
        positions = monitor.get_position_summary()
        summary = pnl.get_summary()
        
        return jsonify({
            'status': 'running',
            'mode': 'LIVE',
            'timestamp': datetime.now().isoformat(),
            'positions_count': len(positions),
            'trades_today': summary['today_trades'],
            'total_trades': summary['total_trades'],
            'today_pnl': summary['today_net'],
            'total_pnl': summary['net_pnl'],
            'positions': {sym: {'qty': p['qty'], 'avg_cost': p['cost_basis']} 
                         for sym, p in positions.items()}
        })
    
    @app.route('/api/positions', methods=['GET'])
    def api_positions():
        monitor.scan_logs(days=7)
        positions = monitor.get_position_summary()
        
        return jsonify([
            {
                'symbol': sym,
                'quantity': p['qty'],
                'avg_cost': p['cost_basis'],
                'trades': p['trades']
            }
            for sym, p in sorted(positions.items())
        ])
    
    @app.route('/api/pnl', methods=['GET'])
    def api_pnl():
        summary = pnl.get_summary()
        return jsonify({
            'today_realized': summary['today_realized'],
            'today_fees': summary['today_fees'],
            'today_net': summary['today_net'],
            'total_realized': summary['total_realized_pnl'],
            'total_fees': summary['total_fees'],
            'total_net': summary['net_pnl'],
            'total_trades': summary['total_trades']
        })
    
    @app.route('/api/trades', methods=['GET'])
    def api_trades():
        from flask import request
        days = int(request.args.get('days', 1))
        
        monitor.scan_logs(days=days)
        trades = sorted(monitor.trades, key=lambda x: x['timestamp'], reverse=True)
        
        return jsonify([
            {
                'timestamp': t['timestamp'],
                'side': t['side'],
                'symbol': t['symbol'],
                'size': t['size'],
                'price': t.get('price')
            }
            for t in trades[:20]
        ])
    
    @app.route('/api/health', methods=['GET'])
    def api_health():
        anomalies = monitor.check_anomalies()
        return jsonify({
            'healthy': len(anomalies) == 0,
            'anomalies': anomalies,
            'logs_found': len(monitor.trades) > 0,
            'timestamp': datetime.now().isoformat()
        })
    
    @app.route('/', methods=['GET'])
    def api_root():
        return jsonify({
            'service': 'Sapphire Monitoring API',
            'status': 'running',
            'endpoints': [
                '/api/status',
                '/api/positions',
                '/api/pnl',
                '/api/trades?days=N',
                '/api/health'
            ]
        })

elif MONITORING_AVAILABLE:
    # Fallback to simple HTTP server
    monitor = TradeLogMonitor()
    pnl = PnLTracker()
    
    class MonitoringHandler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass  # Suppress logs
        
        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path
            
            try:
                if path == '/api/status':
                    monitor.scan_logs(days=1)
                    positions = monitor.get_position_summary()
                    summary = pnl.get_summary()
                    
                    data = {
                        'status': 'running',
                        'mode': 'LIVE',
                        'timestamp': datetime.now().isoformat(),
                        'positions_count': len(positions),
                        'trades_today': summary['today_trades'],
                        'total_trades': summary['total_trades'],
                        'today_pnl': summary['today_net'],
                        'total_pnl': summary['net_pnl'],
                        'positions': {sym: {'qty': p['qty'], 'avg_cost': p['cost_basis']} 
                                     for sym, p in positions.items()}
                    }
                
                elif path == '/api/positions':
                    monitor.scan_logs(days=7)
                    positions = monitor.get_position_summary()
                    data = [
                        {
                            'symbol': sym,
                            'quantity': p['qty'],
                            'avg_cost': p['cost_basis'],
                            'trades': p['trades']
                        }
                        for sym, p in sorted(positions.items())
                    ]
                
                elif path == '/api/pnl':
                    summary = pnl.get_summary()
                    data = {
                        'today_realized': summary['today_realized'],
                        'today_fees': summary['today_fees'],
                        'today_net': summary['today_net'],
                        'total_realized': summary['total_realized_pnl'],
                        'total_fees': summary['total_fees'],
                        'total_net': summary['net_pnl'],
                        'total_trades': summary['total_trades']
                    }
                
                elif path == '/api/trades':
                    query = urllib.parse.parse_qs(parsed.query)
                    days = int(query.get('days', [1])[0])
                    
                    monitor.scan_logs(days=days)
                    trades = sorted(monitor.trades, key=lambda x: x['timestamp'], reverse=True)
                    
                    data = [
                        {
                            'timestamp': t['timestamp'],
                            'side': t['side'],
                            'symbol': t['symbol'],
                            'size': t['size'],
                            'price': t.get('price')
                        }
                        for t in trades[:20]
                    ]
                
                elif path == '/api/health':
                    anomalies = monitor.check_anomalies()
                    data = {
                        'healthy': len(anomalies) == 0,
                        'anomalies': anomalies,
                        'logs_found': len(monitor.trades) > 0,
                        'timestamp': datetime.now().isoformat()
                    }
                
                elif path == '/':
                    data = {
                        'service': 'Sapphire Monitoring API',
                        'status': 'running',
                        'endpoints': [
                            '/api/status',
                            '/api/positions',
                            '/api/pnl',
                            '/api/trades?days=N',
                            '/api/health'
                        ]
                    }
                
                else:
                    self.send_error(404)
                    return
                
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps(data).encode())
                
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode())


def format_for_telegram(data_type: str, data) -> str:
    """Format API response for Telegram"""
    if data_type == 'status':
        lines = [
            "📊 *System Status*",
            "",
            f"Status: {'✅ Running' if data.get('status') == 'running' else '❌ Stopped'}",
            f"Mode: {data.get('mode', 'Unknown')}",
            f"Positions: {data.get('positions_count', 0)}",
            f"Trades Today: {data.get('trades_today', 0)}",
            f"Total Trades: {data.get('total_trades', 0)}",
            f"Today's P&L: ${data.get('today_pnl', 0):+.2f}",
        ]
        
        positions = data.get('positions', {})
        if positions:
            lines.extend(["", "*Positions:*"])
            for sym, p in list(positions.items())[:5]:
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
            f"  Realized: ${data.get('today_realized', 0):+.2f}\n"
            f"  Fees: ${data.get('today_fees', 0):.2f}\n"
            f"  Net: ${data.get('today_net', 0):+.2f}\n\n"
            f"*All-Time:*\n"
            f"  Realized: ${data.get('total_realized', 0):+.2f}\n"
            f"  Fees: ${data.get('total_fees', 0):.2f}\n"
            f"  Net: ${data.get('total_net', 0):+.2f}\n"
            f"  Trades: {data.get('total_trades', 0)}"
        )
    
    elif data_type == 'trades':
        if not data:
            return "📭 No trades found"
        
        lines = ["🔄 *Recent Trades*", ""]
        for t in data[:10]:
            emoji = "🟢" if t['side'] == 'BUY' else "🔴"
            time = t['timestamp'][11:16] if len(t['timestamp']) > 16 else "--:--"
            price_str = f" @ ${t['price']:,.0f}" if t.get('price') else ""
            lines.append(f"{emoji} {time} {t['side']} {t['size']:.4f} {t['symbol']}{price_str}")
        return '\n'.join(lines)
    
    elif data_type == 'health':
        if data.get('healthy'):
            return "✅ *All Systems Healthy*\n\n• Trading logs found\n• No anomalies detected"
        else:
            lines = ["⚠️ *Health Issues*", ""]
            for a in data.get('anomalies', [])[:5]:
                lines.append(f"• {a}")
            return '\n'.join(lines)
    
    return str(data)


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Sapphire Monitoring Server')
    parser.add_argument('--port', type=int, default=PORT, help=f'Port to run on (default: {PORT})')
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind to')
    args = parser.parse_args()
    
    if not MONITORING_AVAILABLE:
        print("❌ Monitoring modules not available")
        print("Make sure you're in the sapphire_trading_monitor directory")
        sys.exit(1)
    
    print(f"🚀 Starting Sapphire Monitoring Server on {args.host}:{args.port}")
    print(f"   Flask available: {HAS_FLASK}")
    print("")
    print("Endpoints:")
    print(f"  http://{args.host}:{args.port}/api/status")
    print(f"  http://{args.host}:{args.port}/api/positions")
    print(f"  http://{args.host}:{args.port}/api/pnl")
    print(f"  http://{args.host}:{args.port}/api/trades?days=7")
    print(f"  http://{args.host}:{args.port}/api/health")
    print("")
    
    if HAS_FLASK:
        app.run(host=args.host, port=args.port, debug=False)
    else:
        server = HTTPServer((args.host, args.port), MonitoringHandler)
        print("Press Ctrl+C to stop")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\n👋 Server stopped")


if __name__ == '__main__':
    main()
