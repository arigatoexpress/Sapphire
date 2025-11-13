import json, http.server, socketserver, urllib.parse
from datetime import datetime

PORT = 8080

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            path = urllib.parse.urlparse(self.path).path
            if path == "/healthz":
                self.json_resp(200, {"status": "healthy", "service": "inline_server"})
            elif path == "/portfolio-status":
                self.json_resp(200, {
                    'total_capital': 3500, 'agent_capital': 500, 'agent_count': 7,
                    'status': 'operational', 'timestamp': datetime.utcnow().isoformat(),
                    'agents': {
                        'trend_momentum_agent': {'status': 'active'},
                        'strategy_optimization_agent': {'status': 'active'},
                        'financial_sentiment_agent': {'status': 'active'},
                        'market_prediction_agent': {'status': 'active'},
                        'volume_microstructure_agent': {'status': 'active'},
                        'freqtrade': {'status': 'standby'},
                        'hummingbot': {'status': 'standby'}
                    }
                })
            elif path == "/agent-activity":
                self.json_resp(200, [{
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
                    'status': 'active' if agent not in ['freqtrade', 'hummingbot'] else 'standby'
                } for agent in ['trend_momentum_agent', 'strategy_optimization_agent', 'financial_sentiment_agent', 'market_prediction_agent', 'volume_microstructure_agent', 'freqtrade', 'hummingbot']])
            elif path == "/system-status":
                self.json_resp(200, {
                    'service': 'sapphire_trade_inline', 'status': 'operational', 'version': '1.0.0-inline',
                    'total_capital': 3500, 'active_agents': 5,
                    'features': ['Basic portfolio tracking', 'Agent status monitoring', 'Emergency fallback mode'],
                    'limitations': ['No real-time trading', 'Static demonstration data', 'Basic functionality only']
                })
            elif path == "/":
                self.json_resp(200, {
                    "message": "Sapphire Trade Inline Server", "status": "operational",
                    "capital": "$3,500 allocated", "agents": "7 AI agents configured"
                })
            else:
                self.json_resp(404, {"error": "Not found"})
        except Exception as e:
            self.json_resp(500, {"error": str(e)})
    
    def json_resp(self, code, data):
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
    
    def log_message(self, format, *args): pass

print("🚀 Sapphire Trade Inline Server starting...")
socketserver.TCPServer.allow_reuse_address = True
with socketserver.TCPServer(("", PORT), Handler) as httpd:
    print(f"✅ Server running on port {PORT}")
    httpd.serve_forever()
