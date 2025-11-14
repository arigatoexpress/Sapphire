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
            'agent_count': 6,
            'status': 'operational',
            'timestamp': datetime.utcnow().isoformat(),
            'agents': {
                'trend-momentum-agent': {'status': 'active', 'last_trade': None},
                'strategy-optimization-agent': {'status': 'active', 'last_trade': None},
                'financial-sentiment-agent': {'status': 'active', 'last_trade': None},
                'market-prediction-agent': {'status': 'active', 'last_trade': None},
                'volume-microstructure-agent': {'status': 'active', 'last_trade': None},
                'vpin-hft': {'status': 'active', 'last_trade': None}
            }
        }

    def get_agent_activities(self):
        """Get agent activities data"""
        agents = [
            'trend-momentum-agent',
            'strategy-optimization-agent',
            'financial-sentiment-agent',
            'market-prediction-agent',
            'volume-microstructure-agent',
            'vpin-hft'
        ]

        activities = []
        for agent in agents:
            activities.append({
                'agent_id': f'{agent}-1',
                'agent_type': agent,
                'agent_name': agent.replace('-', ' ').title(),
                'activity_score': 0.5 + (hash(agent) % 50) / 100,
                'communication_count': hash(agent) % 20,
                'trading_count': 0,
                'last_activity': datetime.utcnow().isoformat(),
                'participation_threshold': 0.7,
                'specialization': {
                    'trend-momentum-agent': 'Momentum Analysis',
                    'strategy-optimization-agent': 'Strategy Optimization',
                    'financial-sentiment-agent': 'Sentiment Analysis',
                    'market-prediction-agent': 'Market Prediction',
                    'volume-microstructure-agent': 'Volume Analysis',
                    'vpin-hft': 'VPIN High-Frequency Trading'
                }.get(agent, 'Trading Agent'),
                'color': {
                    'trend-momentum-agent': '#06b6d4',
                    'strategy-optimization-agent': '#8b5cf6',
                    'financial-sentiment-agent': '#ef4444',
                    'market-prediction-agent': '#f59e0b',
                    'volume-microstructure-agent': '#ec4899',
                    'vpin-hft': '#06b6d4'
                }.get(agent, '#6b7280'),
                'status': 'active'
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
            'active_agents': 6,
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
            "agents": "6 AI agents configured",
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
