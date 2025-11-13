#!/usr/bin/env python3
"""
Basic HTTP Server - No External Dependencies

Ultra-minimal HTTP server using only Python standard library.
Provides basic API endpoints for system demonstration.
"""

import json
import http.server
import socketserver
from datetime import datetime
import urllib.parse

PORT = 8080

class TradingAPIHandler(http.server.BaseHTTPRequestHandler):
    """Basic HTTP request handler for trading API"""

    def do_GET(self):
        """Handle GET requests"""
        try:
            # Parse the path
            parsed_path = urllib.parse.urlparse(self.path)
            path = parsed_path.path

            # Route requests
            if path == "/healthz":
                self.send_json_response(200, {"status": "healthy", "service": "basic_server"})
            elif path == "/portfolio-status":
                self.send_json_response(200, self.get_portfolio_data())
            elif path == "/agent-activity":
                self.send_json_response(200, self.get_agent_activities())
            elif path == "/system-status":
                self.send_json_response(200, self.get_system_status())
            elif path == "/trading-signals":
                self.send_json_response(200, self.get_trading_signals())
            elif path == "/":
                self.send_json_response(200, self.get_root_data())
            else:
                self.send_json_response(404, {"error": "Not found"})

        except Exception as e:
            self.send_json_response(500, {"error": str(e)})

    def send_json_response(self, status_code, data):
        """Send JSON response"""
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def get_portfolio_data(self):
        """Get portfolio status data"""
        return {
            'total_capital': 3500,
            'agent_capital': 500,
            'agent_count': 7,
            'status': 'operational',
            'timestamp': datetime.utcnow().isoformat(),
            'agents': {
                'trend_momentum_agent': {'status': 'active', 'last_trade': None},
                'strategy_optimization_agent': {'status': 'active', 'last_trade': None},
                'financial_sentiment_agent': {'status': 'active', 'last_trade': None},
                'market_prediction_agent': {'status': 'active', 'last_trade': None},
                'volume_microstructure_agent': {'status': 'active', 'last_trade': None},
                'freqtrade': {'status': 'standby', 'last_trade': None},
                'hummingbot': {'status': 'standby', 'last_trade': None}
            }
        }

    def get_agent_activities(self):
        """Get agent activities data"""
        agents = [
            'trend_momentum_agent',
            'strategy_optimization_agent',
            'financial_sentiment_agent',
            'market_prediction_agent',
            'volume_microstructure_agent',
            'freqtrade',
            'hummingbot'
        ]

        activities = []
        for agent in agents:
            activities.append({
                'agent_id': f'{agent.replace("_", "-")}-1',
                'agent_type': agent,
                'agent_name': agent.replace('_', ' ').title(),
                'activity_score': 0.5 + (hash(agent) % 50) / 100,
                'communication_count': hash(agent) % 20,
                'trading_count': 0,
                'last_activity': datetime.utcnow().isoformat(),
                'participation_threshold': 0.7,
                'specialization': {
                    'trend_momentum_agent': 'Momentum Analysis',
                    'strategy_optimization_agent': 'Strategy Optimization',
                    'financial_sentiment_agent': 'Sentiment Analysis',
                    'market_prediction_agent': 'Market Prediction',
                    'volume_microstructure_agent': 'Volume Analysis',
                    'freqtrade': 'Algorithmic Trading',
                    'hummingbot': 'Market Making'
                }.get(agent, 'Trading Agent'),
                'color': {
                    'trend_momentum_agent': '#3b82f6',
                    'strategy_optimization_agent': '#8b5cf6',
                    'financial_sentiment_agent': '#10b981',
                    'market_prediction_agent': '#f59e0b',
                    'volume_microstructure_agent': '#ef4444',
                    'freqtrade': '#06b6d4',
                    'hummingbot': '#84cc16'
                }.get(agent, '#6b7280'),
                'status': 'active' if agent != 'freqtrade' and agent != 'hummingbot' else 'standby'
            })

        return activities

    def get_system_status(self):
        """Get system status data"""
        return {
            'service': 'sapphire_trade_basic',
            'status': 'operational',
            'version': '1.0.0-basic',
            'uptime': 'N/A',
            'total_capital': 3500,
            'active_agents': 5,
            'features': [
                'Basic portfolio tracking',
                'Agent status monitoring',
                'Static data demonstration',
                'Emergency fallback mode',
                'Standard library only'
            ],
            'limitations': [
                'No real-time trading',
                'Static demonstration data',
                'No complex analytics',
                'Basic functionality only',
                'No external dependencies'
            ]
        }

    def get_trading_signals(self):
        """Get trading signals data"""
        return {
            "signals": [],
            "message": "Basic server - demonstration mode",
            "timestamp": datetime.utcnow().isoformat()
        }

    def get_root_data(self):
        """Get root endpoint data"""
        return {
            "message": "Sapphire Trade Basic Server",
            "status": "operational",
            "capital": "$3,500 allocated",
            "agents": "7 AI agents configured",
            "service": "basic_http_server",
            "version": "1.0.0-basic"
        }

    def log_message(self, format, *args):
        """Override logging to be quieter"""
        pass

if __name__ == "__main__":
    print("🚀 Starting Sapphire Trade Basic Server on port", PORT)
    print("📊 Available endpoints:")
    print("  GET /healthz - Health check")
    print("  GET /portfolio-status - Portfolio data")
    print("  GET /agent-activity - Agent activities")
    print("  GET /system-status - System status")
    print("  GET /trading-signals - Trading signals")
    print("  GET / - Root information")

    with socketserver.TCPServer(("", PORT), TradingAPIHandler) as httpd:
        print(f"✅ Server running on port {PORT}")
        httpd.serve_forever()
