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
                    'total_capital': 3500, 'agent_capital': 500, 'agent_count': 6,
                    'status': 'operational', 'timestamp': datetime.utcnow().isoformat(),
                    'agents': {
                        'trend-momentum-agent': {'status': 'active'},
                        'strategy-optimization-agent': {'status': 'active'},
                        'financial-sentiment-agent': {'status': 'active'},
                        'market-prediction-agent': {'status': 'active'},
                        'volume-microstructure-agent': {'status': 'active'},
                        'vpin-hft': {'status': 'active'}
                    }
                })
            elif path == "/agent-activity":
                self.json_resp(200, [{
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
                        'vpin-hft': 'VPIN HFT Trading'
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
                } for agent in ['trend-momentum-agent', 'strategy-optimization-agent', 'financial-sentiment-agent', 'market-prediction-agent', 'volume-microstructure-agent', 'vpin-hft']])
            elif path == "/system-status":
                self.json_resp(200, {
                    'service': 'sapphire_trade_inline', 'status': 'operational', 'version': '1.0.0-inline',
                    'total_capital': 3500, 'active_agents': 6,
                    'features': ['Basic portfolio tracking', 'Agent status monitoring', 'Emergency fallback mode'],
                    'limitations': ['No real-time trading', 'Static demonstration data', 'Basic functionality only']
                })
            elif path == "/":
                self.json_resp(200, {
                    "message": "Sapphire Trade Inline Server", "status": "operational",
                    "capital": "$3,500 allocated", "agents": "6 AI agents configured"
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
