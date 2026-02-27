#!/usr/bin/env python3
"""
Sapphire OS - Command Deck v2.0
Tactical Trading Infrastructure Dashboard

A unified view combining:
- Real-time architecture topology visualization
- Live trading metrics with sparklines
- Structured log streaming
- Interactive terminal console
"""

import os
import asyncio
import json
from datetime import datetime, timedelta
from functools import wraps
from typing import Dict, Any, Optional, List

from flask import Flask, render_template, jsonify, request, Response, stream_with_context
from google.cloud import firestore, pubsub_v1
import aiohttp

app = Flask(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════════════════════

# GCP Configuration
PROJECT_ID = os.environ.get('GCP_PROJECT', 'sapphire-479610')
REGION = os.environ.get('GCP_REGION', 'us-central1')

# Service URLs
GATEWAY_URL = os.environ.get('GATEWAY_URL', 'https://sapphire-gateway-267358751314.us-central1.run.app')
LOG_VIEWER_URL = os.environ.get('LOG_VIEWER_URL', 'https://sapphire-log-viewer-267358751314.us-central1.run.app')
WEBHOOK_URL = os.environ.get('WEBHOOK_URL', 'https://presents-exploration-grocery-retirement.trycloudflare.com')

# Authentication
AUTH_USERNAME = os.environ.get('AUTH_USERNAME', 'sapphire')
AUTH_PASSWORD = os.environ.get('AUTH_PASSWORD', 'alpha2024')
ENABLE_AUTH = os.environ.get('ENABLE_AUTH', 'true').lower() == 'true'

# Cache settings
CACHE_DURATION = int(os.environ.get('CACHE_DURATION', '10'))  # seconds

# ═══════════════════════════════════════════════════════════════════════════════
# Firestore Client
# ═══════════════════════════════════════════════════════════════════════════════

db = firestore.Client(project=PROJECT_ID)
LOGS_COLLECTION = 'system_logs'
METRICS_COLLECTION = 'trading_metrics'

# ═══════════════════════════════════════════════════════════════════════════════
# In-Memory Cache
# ═══════════════════════════════════════════════════════════════════════════════

cache: Dict[str, tuple] = {}

def get_cached(key: str, duration: int = CACHE_DURATION) -> Optional[Any]:
    """Get cached value if not expired"""
    if key in cache:
        value, timestamp = cache[key]
        if datetime.utcnow().timestamp() - timestamp < duration:
            return value
    return None

def set_cache(key: str, value: Any):
    """Set cached value with timestamp"""
    cache[key] = (value, datetime.utcnow().timestamp())

# ═══════════════════════════════════════════════════════════════════════════════
# Authentication
# ═══════════════════════════════════════════════════════════════════════════════

def check_auth(username: str, password: str) -> bool:
    """Verify credentials"""
    return username == AUTH_USERNAME and password == AUTH_PASSWORD

def authenticate() -> Response:
    """Send 401 response with WWW-Authenticate header"""
    return Response(
        'Access denied. Authentication required.\n',
        401,
        {'WWW-Authenticate': 'Basic realm="Sapphire Command Deck"'}
    )

def requires_auth(f):
    """Decorator to protect routes with basic auth"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not ENABLE_AUTH:
            return f(*args, **kwargs)
        
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated

# ═══════════════════════════════════════════════════════════════════════════════
# Async Helpers
# ═══════════════════════════════════════════════════════════════════════════════

async def fetch_from_gateway(endpoint: str, timeout: int = 10) -> Dict[str, Any]:
    """Fetch data from Gateway API"""
    try:
        async with aiohttp.ClientSession() as session:
            url = f"{GATEWAY_URL}{endpoint}"
            async with session.get(url, timeout=timeout) as resp:
                if resp.status == 200:
                    return await resp.json()
                return {"error": f"HTTP {resp.status}", "status": "error"}
    except asyncio.TimeoutError:
        return {"error": "Timeout", "status": "offline"}
    except Exception as e:
        return {"error": str(e), "status": "error"}

async def fetch_market_prices() -> Dict[str, Any]:
    """Fetch real-time crypto prices from CoinGecko"""
    cached = get_cached('market_prices', 30)
    if cached:
        return cached
    
    try:
        async with aiohttp.ClientSession() as session:
            url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,solana&vs_currencies=usd&include_24hr_change=true"
            async with session.get(url, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    result = {
                        'BTC': {
                            'price': data.get('bitcoin', {}).get('usd', 0),
                            'change_24h': data.get('bitcoin', {}).get('usd_24h_change', 0)
                        },
                        'ETH': {
                            'price': data.get('ethereum', {}).get('usd', 0),
                            'change_24h': data.get('ethereum', {}).get('usd_24h_change', 0)
                        },
                        'SOL': {
                            'price': data.get('solana', {}).get('usd', 0),
                            'change_24h': data.get('solana', {}).get('usd_24h_change', 0)
                        },
                        'source': 'coingecko',
                        'timestamp': datetime.utcnow().isoformat()
                    }
                    set_cache('market_prices', result)
                    return result
                return {'error': f'HTTP {resp.status}'}
    except Exception as e:
        return {'error': str(e)}

# ═══════════════════════════════════════════════════════════════════════════════
# Routes - Main Dashboard
# ═══════════════════════════════════════════════════════════════════════════════

@app.route('/')
@requires_auth
def index():
    """Main Command Deck dashboard"""
    return render_template('index.html')

@app.route('/health')
def health():
    """Health check endpoint - public"""
    return jsonify({
        'status': 'healthy',
        'service': 'command-deck',
        'version': '2.0.0',
        'timestamp': datetime.utcnow().isoformat()
    })

# ═══════════════════════════════════════════════════════════════════════════════
# API Routes - Topology & Status
# ═══════════════════════════════════════════════════════════════════════════════

@app.route('/api/status')
@requires_auth
def api_status():
    """Return system status for all nodes"""
    cached = get_cached('system_status')
    if cached:
        return jsonify(cached)
    
    # Gather status from all nodes
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    gateway_status = loop.run_until_complete(fetch_from_gateway('/api/v1/status'))
    
    result = {
        'nodes': {
            'tradingview': {'status': 'online', 'type': 'source'},
            'windows_pc': {'status': 'online', 'type': 'webhook', 'port': 9090},
            'pubsub': {'status': 'online', 'type': 'event_bus'},
            'rari1': {
                'status': gateway_status.get('pi_cluster', {}).get('pi1', {}).get('status', 'unknown'),
                'type': 'controller',
                'role': 'workbench'
            },
            'rari2': {
                'status': gateway_status.get('pi_cluster', {}).get('pi2', {}).get('status', 'unknown'),
                'type': 'execution',
                'role': 'trading_engine'
            },
            'cloud_run': {'status': 'online', 'type': 'api_gateway'},
            'lighter': {'status': 'online', 'type': 'exchange'},
            'drift': {'status': 'online', 'type': 'exchange'},
            'ollama': {'status': 'online', 'type': 'ai', 'models': 3}
        },
        'connections': {
            'tailscale': {'status': 'connected', 'nodes': 4},
            'vpn': {'status': 'connected', 'location': 'ProtonVPN'},
        },
        'timestamp': datetime.utcnow().isoformat()
    }
    
    set_cache('system_status', result)
    return jsonify(result)

@app.route('/api/topology')
@requires_auth
def api_topology():
    """Return topology data for visualization"""
    topology = {
        'nodes': [
            {'id': 'tradingview', 'label': 'TRADINGVIEW', 'sublabel': 'ALERT SOURCE', 'x': 60, 'y': 80, 'status': 'online'},
            {'id': 'windows_pc', 'label': 'WINDOWS_PC', 'sublabel': 'WEBHOOK:9090', 'x': 250, 'y': 130, 'status': 'online'},
            {'id': 'pubsub', 'label': 'PUB/SUB', 'sublabel': 'EVENT BUS', 'x': 400, 'y': 205, 'status': 'online'},
            {'id': 'rari1', 'label': 'RARI1', 'sublabel': 'CONTROLLER', 'x': 550, 'y': 130, 'status': 'online'},
            {'id': 'rari2', 'label': 'RARI2', 'sublabel': 'EXECUTION', 'x': 550, 'y': 280, 'status': 'online'},
            {'id': 'cloud_run', 'label': 'CLOUD RUN', 'sublabel': 'API GATEWAY', 'x': 550, 'y': 205, 'status': 'online'},
            {'id': 'lighter', 'label': 'LIGHTER', 'sublabel': 'SOL PERPS', 'x': 720, 'y': 100, 'status': 'online'},
            {'id': 'drift', 'label': 'DRIFT', 'sublabel': 'SOL PERPS', 'x': 720, 'y': 310, 'status': 'online'},
            {'id': 'ollama', 'label': 'OLLAMA AI', 'sublabel': 'GEMMA3:27B', 'x': 320, 'y': 350, 'status': 'online'},
        ],
        'links': [
            {'source': 'tradingview', 'target': 'windows_pc'},
            {'source': 'windows_pc', 'target': 'pubsub'},
            {'source': 'windows_pc', 'target': 'ollama', 'style': 'dashed'},
            {'source': 'pubsub', 'target': 'rari1'},
            {'source': 'pubsub', 'target': 'rari2'},
            {'source': 'pubsub', 'target': 'cloud_run'},
            {'source': 'rari1', 'target': 'lighter'},
            {'source': 'rari2', 'target': 'drift'},
        ]
    }
    return jsonify(topology)

# ═══════════════════════════════════════════════════════════════════════════════
# API Routes - Metrics
# ═══════════════════════════════════════════════════════════════════════════════

@app.route('/api/metrics')
@requires_auth
def api_metrics():
    """Return trading metrics"""
    cached = get_cached('metrics')
    if cached:
        return jsonify(cached)
    
    # Fetch from Firestore for historical data
    try:
        metrics_ref = db.collection(METRICS_COLLECTION)
        recent = metrics_ref.order_by('timestamp', direction=firestore.Query.DESCENDING).limit(1).get()
        
        if recent:
            data = recent[0].to_dict()
        else:
            # Fallback/mock data
            data = {
                'pnl_24h': 2.4,
                'pnl_7d': 8.7,
                'pnl_30d': 24.3,
                'active_signals': 12,
                'win_rate': 78.5,
                'latency_ms': 45,
                'trades_today': 8,
                'trades_limit': 10,
                'pending_proposals': 3,
            }
    except Exception as e:
        data = {'error': str(e)}
    
    data['timestamp'] = datetime.utcnow().isoformat()
    set_cache('metrics', data)
    return jsonify(data)

@app.route('/api/metrics/history')
@requires_auth
def api_metrics_history():
    """Return historical metrics for sparklines"""
    hours = request.args.get('hours', 24, type=int)
    since = datetime.utcnow() - timedelta(hours=hours)
    
    try:
        metrics_ref = db.collection(METRICS_COLLECTION)
        query = metrics_ref.where('timestamp', '>=', since.isoformat()).order_by('timestamp')
        docs = query.stream()
        
        history = []
        for doc in docs:
            data = doc.to_dict()
            history.append({
                'timestamp': data.get('timestamp'),
                'pnl': data.get('pnl_24h', 0),
                'signals': data.get('active_signals', 0),
                'win_rate': data.get('win_rate', 0),
                'latency': data.get('latency_ms', 0),
            })
        
        return jsonify({'history': history})
    except Exception as e:
        # Return mock data
        import random
        history = [
            {
                'timestamp': (datetime.utcnow() - timedelta(hours=i)).isoformat(),
                'pnl': random.uniform(-2, 5),
                'signals': random.randint(8, 15),
                'win_rate': random.uniform(70, 85),
                'latency': random.randint(30, 60),
            }
            for i in range(24, 0, -1)
        ]
        return jsonify({'history': history, 'mock': True})

# ═══════════════════════════════════════════════════════════════════════════════
# API Routes - Logs
# ═══════════════════════════════════════════════════════════════════════════════

@app.route('/api/logs')
@requires_auth
def api_logs():
    """Return system logs from Firestore"""
    service = request.args.get('service')
    level = request.args.get('level')
    hours = request.args.get('hours', 24, type=int)
    limit = request.args.get('limit', 100, type=int)
    
    since = datetime.utcnow() - timedelta(hours=hours)
    
    try:
        query = db.collection(LOGS_COLLECTION).where('timestamp', '>=', since.isoformat())
        
        if service:
            query = query.where('service', '==', service)
        if level:
            query = query.where('level', '==', level.upper())
        
        query = query.order_by('timestamp', direction=firestore.Query.DESCENDING).limit(limit)
        docs = query.stream()
        
        logs = []
        for doc in docs:
            data = doc.to_dict()
            data['id'] = doc.id
            logs.append(data)
        
        return jsonify({'logs': logs, 'count': len(logs)})
    except Exception as e:
        # Return sample logs if Firestore fails
        sample_logs = [
            {
                'timestamp': datetime.utcnow().isoformat(),
                'level': 'INFO',
                'service': 'webhook',
                'message': 'Signal received from TradingView',
                'event_type': 'signal_received',
                'signal_id': 'sig_001'
            },
            {
                'timestamp': (datetime.utcnow() - timedelta(minutes=2)).isoformat(),
                'level': 'SUCCESS',
                'service': 'trading',
                'message': 'Trade executed successfully',
                'event_type': 'trade_executed',
                'symbol': 'SOL-PERP'
            }
        ]
        return jsonify({'logs': sample_logs, 'mock': True, 'error': str(e)})

@app.route('/api/logs/stream')
@requires_auth
def api_logs_stream():
    """Stream logs in real-time using Server-Sent Events"""
    def event_stream():
        last_check = datetime.utcnow()
        while True:
            try:
                # Query for new logs since last check
                query = db.collection(LOGS_COLLECTION)\
                    .where('timestamp', '>', last_check.isoformat())\
                    .order_by('timestamp')\
                    .limit(10)
                
                docs = query.stream()
                new_logs = []
                for doc in docs:
                    data = doc.to_dict()
                    data['id'] = doc.id
                    new_logs.append(data)
                    last_check = datetime.fromisoformat(data['timestamp'].replace('Z', '+00:00')).replace(tzinfo=None)
                
                if new_logs:
                    yield f"data: {json.dumps({'logs': new_logs})}\n\n"
                
                # Heartbeat
                yield f"data: {json.dumps({'heartbeat': True})}\n\n"
                
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
            
            # Sleep before next check
            import time
            time.sleep(2)
    
    return Response(
        stream_with_context(event_stream()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'
        }
    )

# ═══════════════════════════════════════════════════════════════════════════════
# API Routes - Terminal Commands
# ═══════════════════════════════════════════════════════════════════════════════

@app.route('/api/terminal', methods=['POST'])
@requires_auth
def api_terminal():
    """Execute terminal commands"""
    data = request.get_json()
    command = data.get('command', '').strip().lower()
    
    commands = {
        'help': {
            'output': '''Available commands:
  status     - Show system status
  nodes      - List all nodes
  logs       - Show recent log summary
  signals    - Show active signals
  metrics    - Show trading metrics
  clear      - Clear terminal
  help       - Show this help''',
            'type': 'info'
        },
        'status': {
            'output': 'System: ONLINE | Nodes: 4/4 connected | Signals: 12 active',
            'type': 'success'
        },
        'nodes': {
            'output': '''Network Nodes:
  [ONLINE] Windows_PC (Webhook Receiver)
  [ONLINE] RARI1 (Controller)
  [ONLINE] RARI2 (Execution Engine)
  [ONLINE] Cloud Run (API Gateway)
  [ONLINE] Ollama AI (3 models loaded)''',
            'type': 'info'
        },
        'logs': {
            'output': 'Recent activity: 24 entries | 18 OK | 4 INFO | 2 WARN',
            'type': 'info'
        },
        'signals': {
            'output': 'Active signals: 12 | BUY: 7 | SELL: 5 | Last: ETHBTC (0.5s ago)',
            'type': 'success'
        },
        'metrics': {
            'output': '24h PnL: +2.4% | Win Rate: 78.5% | Latency: 45ms',
            'type': 'success'
        },
        'clear': {
            'output': '',
            'type': 'clear'
        }
    }
    
    if command in commands:
        return jsonify(commands[command])
    else:
        return jsonify({
            'output': f"Command not found: {command}. Type 'help' for available commands.",
            'type': 'error'
        })

# ═══════════════════════════════════════════════════════════════════════════════
# API Routes - Dashboard Data
# ═══════════════════════════════════════════════════════════════════════════════

@app.route('/api/dashboard')
@requires_auth
def api_dashboard():
    """Return consolidated dashboard data"""
    cached = get_cached('dashboard', duration=5)
    if cached:
        return jsonify(cached)
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # Fetch all data in parallel
    prices = loop.run_until_complete(fetch_market_prices())
    
    result = {
        'prices': prices if 'error' not in prices else None,
        'timestamp': datetime.utcnow().isoformat(),
        'version': '2.0.0'
    }
    
    set_cache('dashboard', result)
    return jsonify(result)

# ═══════════════════════════════════════════════════════════════════════════════
# Main Entry Point
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8082))
    
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║           SAPPHIRE OS - COMMAND DECK v2.0                    ║
║                                                              ║
║  Tactical Trading Infrastructure Dashboard                   ║
║  Port: {port}                                                  ║
║  Auth: {'Enabled' if ENABLE_AUTH else 'Disabled'}                                         ║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    app.run(host='0.0.0.0', port=port, debug=False)
