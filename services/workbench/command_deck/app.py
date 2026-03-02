#!/usr/bin/env python3
"""
Sapphire OS - Command Deck v3.0
Unified Trading & PM Dashboard

A streamlined dashboard integrating:
- Trading infrastructure monitoring
- AI PM Manager project tracking
- Unified activity feed
- Real-time metrics
"""

import os
import asyncio
import json
from datetime import datetime, timedelta
from functools import wraps, lru_cache
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

from flask import Flask, render_template, jsonify, request, Response, stream_with_context
from google.cloud import firestore
import aiohttp

app = Flask(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# Configuration (Single Source)
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class Config:
    """Immutable configuration - loaded once at startup"""
    PROJECT_ID: str = os.environ.get('GCP_PROJECT', 'sapphire-479610')
    REGION: str = os.environ.get('GCP_REGION', 'us-central1')
    GATEWAY_URL: str = os.environ.get('GATEWAY_URL', 'https://sapphire-gateway-267358751314.us-central1.run.app')
    PM_HUB_URL: str = os.environ.get('PM_HUB_URL', 'https://agentic-pm-hub-267358751314.us-central1.run.app')
    LOG_VIEWER_URL: str = os.environ.get('LOG_VIEWER_URL', 'https://sapphire-log-viewer-267358751314.us-central1.run.app')
    WEBHOOK_URL: str = os.environ.get('WEBHOOK_URL', 'https://presents-exploration-grocery-retirement.trycloudflare.com')
    
    # Auth
    AUTH_USERNAME: str = os.environ.get('AUTH_USERNAME', 'sapphire')
    AUTH_PASSWORD: str = os.environ.get('AUTH_PASSWORD', 'alpha2024')
    ENABLE_AUTH: bool = os.environ.get('ENABLE_AUTH', 'true').lower() == 'true'
    
    # Cache
    CACHE_DURATION: int = int(os.environ.get('CACHE_DURATION', '10'))
    
    # Collections
    LOGS_COLLECTION: str = 'system_logs'
    METRICS_COLLECTION: str = 'trading_metrics'
    
    @property
    def VERSION(self) -> str:
        return '3.0.0'

CONFIG = Config()

# ═══════════════════════════════════════════════════════════════════════════════
# Firestore Client (Singleton)
# ═══════════════════════════════════════════════════════════════════════════════

_db: Optional[firestore.Client] = None

def get_db() -> firestore.Client:
    """Get or create Firestore client (singleton)"""
    global _db
    if _db is None:
        _db = firestore.Client(project=CONFIG.PROJECT_ID)
    return _db

# ═══════════════════════════════════════════════════════════════════════════════
# Unified Cache with TTL
# ═══════════════════════════════════════════════════════════════════════════════

class TTLCache:
    """Simple TTL cache with automatic expiration"""
    def __init__(self):
        self._cache: Dict[str, tuple] = {}
    
    def get(self, key: str, ttl: int = None) -> Optional[Any]:
        """Get value if not expired"""
        if key not in self._cache:
            return None
        value, timestamp = self._cache[key]
        ttl = ttl or CONFIG.CACHE_DURATION
        if datetime.utcnow().timestamp() - timestamp < ttl:
            return value
        del self._cache[key]
        return None
    
    def set(self, key: str, value: Any):
        """Set value with current timestamp"""
        self._cache[key] = (value, datetime.utcnow().timestamp())
    
    def clear(self):
        """Clear all cached values"""
        self._cache.clear()

cache = TTLCache()

# ═══════════════════════════════════════════════════════════════════════════════
# Async HTTP Client (Shared Session)
# ═══════════════════════════════════════════════════════════════════════════════

_session: Optional[aiohttp.ClientSession] = None

async def get_session() -> aiohttp.ClientSession:
    """Get or create shared aiohttp session"""
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=10),
            headers={'Accept': 'application/json'}
        )
    return _session

async def fetch_json(url: str, timeout: int = 10) -> Dict[str, Any]:
    """Fetch JSON from URL with error handling"""
    try:
        session = await get_session()
        async with session.get(url, timeout=timeout) as resp:
            if resp.status == 200:
                return await resp.json()
            return {"error": f"HTTP {resp.status}", "status": "error"}
    except asyncio.TimeoutError:
        return {"error": "Timeout", "status": "offline"}
    except Exception as e:
        return {"error": str(e), "status": "error"}

# ═══════════════════════════════════════════════════════════════════════════════
# Authentication (Single Decorator)
# ═══════════════════════════════════════════════════════════════════════════════

def check_auth(username: str, password: str) -> bool:
    """Verify credentials against config"""
    return username == CONFIG.AUTH_USERNAME and password == CONFIG.AUTH_PASSWORD

def requires_auth(f):
    """Decorator to protect routes with basic auth"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not CONFIG.ENABLE_AUTH:
            return f(*args, **kwargs)
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return Response(
                'Access denied. Authentication required.\n',
                401,
                {'WWW-Authenticate': 'Basic realm="Sapphire Command Deck"'}
            )
        return f(*args, **kwargs)
    return decorated

# ═══════════════════════════════════════════════════════════════════════════════
# Data Fetchers (Unified Interface)
# ═══════════════════════════════════════════════════════════════════════════════

async def fetch_gateway_status() -> Dict[str, Any]:
    """Fetch gateway status with caching"""
    cached = cache.get('gateway_status')
    if cached:
        return cached
    
    result = await fetch_json(f"{CONFIG.GATEWAY_URL}/api/v1/status")
    cache.set('gateway_status', result)
    return result

async def fetch_pm_dashboard() -> Dict[str, Any]:
    """Fetch PM hub dashboard data"""
    cached = cache.get('pm_dashboard', ttl=30)
    if cached:
        return cached
    
    result = await fetch_json(f"{CONFIG.PM_HUB_URL}/api/pm/dashboard")
    cache.set('pm_dashboard', result)
    return result

async def fetch_market_prices() -> Dict[str, Any]:
    """Fetch real-time crypto prices"""
    cached = cache.get('market_prices', ttl=30)
    if cached:
        return cached
    
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,solana,hyperliquid&vs_currencies=usd&include_24hr_change=true"
        result = await fetch_json(url)
        
        if 'error' in result:
            return result
        
        prices = {
            'BTC': {'price': result.get('bitcoin', {}).get('usd', 0), 'change': result.get('bitcoin', {}).get('usd_24h_change', 0)},
            'ETH': {'price': result.get('ethereum', {}).get('usd', 0), 'change': result.get('ethereum', {}).get('usd_24h_change', 0)},
            'SOL': {'price': result.get('solana', {}).get('usd', 0), 'change': result.get('solana', {}).get('usd_24h_change', 0)},
            'HYPE': {'price': result.get('hyperliquid', {}).get('usd', 0), 'change': result.get('hyperliquid', {}).get('usd_24h_change', 0)},
            'timestamp': datetime.utcnow().isoformat()
        }
        cache.set('market_prices', prices)
        return prices
    except Exception as e:
        return {'error': str(e)}

async def fetch_metrics_from_firestore() -> Dict[str, Any]:
    """Fetch trading metrics from Firestore"""
    try:
        db = get_db()
        metrics_ref = db.collection(CONFIG.METRICS_COLLECTION)
        recent = metrics_ref.order_by('timestamp', direction=firestore.Query.DESCENDING).limit(1).get()
        
        if recent:
            return {**recent[0].to_dict(), 'source': 'firestore'}
        
        return {
            'pnl_24h': 0.0, 'pnl_7d': 0.0, 'pnl_30d': 0.0,
            'active_signals': 0, 'win_rate': 0.0, 'latency_ms': 0,
            'trades_today': 0, 'source': 'empty'
        }
    except Exception as e:
        return {'error': str(e), 'source': 'error'}

def normalize_status(raw: Any) -> str:
    """Normalize status values to standard states"""
    if isinstance(raw, bool):
        return "online" if raw else "offline"
    if isinstance(raw, str):
        lowered = raw.strip().lower()
        if lowered in {"online", "healthy", "up", "connected", "ok", "ready", "active"}:
            return "online"
        if lowered in {"offline", "down", "error", "failed", "disconnected", "inactive"}:
            return "offline"
        if lowered in {"warning", "degraded", "slow"}:
            return "warning"
    return "unknown"

# ═══════════════════════════════════════════════════════════════════════════════
# Route Handlers
# ═══════════════════════════════════════════════════════════════════════════════

@app.route('/')
@requires_auth
def index():
    """Main dashboard"""
    return render_template('index.html')

@app.route('/health')
def health():
    """Health check - public"""
    return jsonify({
        'status': 'healthy',
        'service': 'command-deck',
        'version': CONFIG.VERSION,
        'timestamp': datetime.utcnow().isoformat()
    })

# Alias for compatibility
app.route('/api/health')(health)

# ═══════════════════════════════════════════════════════════════════════════════
# Unified Status API
# ═══════════════════════════════════════════════════════════════════════════════

@app.route('/api/status')
@requires_auth
def api_status():
    """Return unified system status (trading + PM)"""
    cached = cache.get('unified_status')
    if cached:
        return jsonify(cached)
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # Fetch all data in parallel
    gateway_task = fetch_gateway_status()
    pm_task = fetch_pm_dashboard()
    
    gateway_data, pm_data = loop.run_until_complete(
        asyncio.gather(gateway_task, pm_task, return_exceptions=True)
    )
    
    # Handle exceptions
    if isinstance(gateway_data, Exception):
        gateway_data = {"error": str(gateway_data)}
    if isinstance(pm_data, Exception):
        pm_data = {"error": str(pm_data)}
    
    # Extract trading nodes
    pi_cluster = gateway_data.get('pi_cluster', {}) if isinstance(gateway_data, dict) else {}
    pi1 = pi_cluster.get('pi1', {}) if isinstance(pi_cluster.get('pi1'), dict) else {}
    pi2 = pi_cluster.get('pi2', {}) if isinstance(pi_cluster.get('pi2'), dict) else {}
    
    result = {
        'trading': {
            'nodes': {
                'tradingview': {'status': 'online', 'type': 'source', 'label': 'TradingView'},
                'windows_pc': {'status': normalize_status(gateway_data.get('windows_pc_status')), 'type': 'webhook', 'label': 'Windows PC'},
                'pubsub': {'status': 'online', 'type': 'event_bus', 'label': 'Pub/Sub'},
                'rari1': {'status': normalize_status(pi1.get('status')), 'type': 'controller', 'label': 'RARI1'},
                'rari2': {'status': normalize_status(pi2.get('status')), 'type': 'execution', 'label': 'RARI2'},
                'cloud_run': {'status': normalize_status(gateway_data.get('status')), 'type': 'gateway', 'label': 'Cloud Run'},
                'lighter': {'status': normalize_status(gateway_data.get('lighter_status')), 'type': 'exchange', 'label': 'Lighter'},
                'ollama': {'status': normalize_status(gateway_data.get('ollama_status')), 'type': 'ai', 'label': 'Ollama AI'}
            },
            'connections': {
                'tailscale': {'status': normalize_status(gateway_data.get('tailscale_status')), 'nodes': gateway_data.get('tailscale_nodes', 0)},
                'vpn': {'status': normalize_status(gateway_data.get('vpn_status')), 'location': gateway_data.get('vpn_location', 'unknown')}
            }
        },
        'pm': {
            'projects': pm_data.get('stats', {}).get('total_projects', 0) if isinstance(pm_data, dict) else 0,
            'tasks': pm_data.get('stats', {}).get('total_tasks', 0) if isinstance(pm_data, dict) else 0,
            'tasks_by_state': pm_data.get('stats', {}).get('tasks_by_state', {}) if isinstance(pm_data, dict) else {},
            'completed_this_week': pm_data.get('stats', {}).get('completed_this_week', 0) if isinstance(pm_data, dict) else 0,
            'active_cycle': pm_data.get('active_cycle') if isinstance(pm_data, dict) else None
        },
        'timestamp': datetime.utcnow().isoformat(),
        'version': CONFIG.VERSION
    }
    
    cache.set('unified_status', result)
    return jsonify(result)

# ═══════════════════════════════════════════════════════════════════════════════
# Trading Metrics API
# ═══════════════════════════════════════════════════════════════════════════════

@app.route('/api/metrics')
@requires_auth
def api_metrics():
    """Return trading metrics"""
    cached = cache.get('trading_metrics', ttl=30)
    if cached:
        return jsonify(cached)
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    prices_task = fetch_market_prices()
    firestore_task = fetch_metrics_from_firestore()
    
    prices, firestore_data = loop.run_until_complete(
        asyncio.gather(prices_task, firestore_task, return_exceptions=True)
    )
    
    if isinstance(firestore_data, Exception):
        firestore_data = {'error': str(firestore_data)}
    
    result = {
        'trading': firestore_data if isinstance(firestore_data, dict) else {},
        'prices': prices if isinstance(prices, dict) and 'error' not in prices else None,
        'timestamp': datetime.utcnow().isoformat()
    }
    
    cache.set('trading_metrics', result)
    return jsonify(result)

@app.route('/api/metrics/history')
@requires_auth
def api_metrics_history():
    """Return historical metrics"""
    hours = request.args.get('hours', 24, type=int)
    since = datetime.utcnow() - timedelta(hours=hours)
    
    try:
        db = get_db()
        metrics_ref = db.collection(CONFIG.METRICS_COLLECTION)
        query = metrics_ref.where('timestamp', '>=', since.isoformat()).order_by('timestamp')
        
        history = [
            {
                'timestamp': doc.to_dict().get('timestamp'),
                'pnl': doc.to_dict().get('pnl_24h', 0),
                'signals': doc.to_dict().get('active_signals', 0),
                'win_rate': doc.to_dict().get('win_rate', 0)
            }
            for doc in query.stream()
        ]
        
        return jsonify({'history': history, 'count': len(history)})
    except Exception as e:
        return jsonify({'history': [], 'count': 0, 'error': str(e)})

# ═══════════════════════════════════════════════════════════════════════════════
# PM Integration APIs
# ═══════════════════════════════════════════════════════════════════════════════

@app.route('/api/pm/projects')
@requires_auth
def api_pm_projects():
    """Proxy to PM Hub projects API"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    result = loop.run_until_complete(fetch_json(f"{CONFIG.PM_HUB_URL}/api/pm/projects"))
    return jsonify(result)

@app.route('/api/pm/tasks')
@requires_auth
def api_pm_tasks():
    """Proxy to PM Hub tasks API with filters"""
    project_id = request.args.get('project_id')
    state = request.args.get('state')
    assignee = request.args.get('assignee')
    
    url = f"{CONFIG.PM_HUB_URL}/api/pm/tasks"
    params = []
    if project_id:
        params.append(f"project_id={project_id}")
    if state:
        params.append(f"state={state}")
    if assignee:
        params.append(f"assignee={assignee}")
    
    if params:
        url += "?" + "&".join(params)
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    result = loop.run_until_complete(fetch_json(url))
    return jsonify(result)

@app.route('/api/pm/activity')
@requires_auth
def api_pm_activity():
    """Proxy to PM Hub activity feed"""
    limit = request.args.get('limit', 20, type=int)
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    result = loop.run_until_complete(
        fetch_json(f"{CONFIG.PM_HUB_URL}/api/pm/activity?limit={limit}")
    )
    return jsonify(result)

# ═══════════════════════════════════════════════════════════════════════════════
# Logs API (Unified)
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
        db = get_db()
        query = db.collection(CONFIG.LOGS_COLLECTION).where('timestamp', '>=', since.isoformat())
        
        if service:
            query = query.where('service', '==', service)
        if level:
            query = query.where('level', '==', level.upper())
        
        logs = [
            {**doc.to_dict(), 'id': doc.id}
            for doc in query.order_by('timestamp', direction=firestore.Query.DESCENDING).limit(limit).stream()
        ]
        
        return jsonify({'logs': logs, 'count': len(logs)})
    except Exception as e:
        return jsonify({'logs': [], 'count': 0, 'error': str(e)})

@app.route('/api/logs/stream')
@requires_auth
def api_logs_stream():
    """Stream logs via Server-Sent Events"""
    def event_stream():
        last_check = datetime.utcnow()
        while True:
            try:
                db = get_db()
                query = db.collection(CONFIG.LOGS_COLLECTION)\
                    .where('timestamp', '>', last_check.isoformat())\
                    .order_by('timestamp')\
                    .limit(10)
                
                new_logs = []
                for doc in query.stream():
                    data = doc.to_dict()
                    data['id'] = doc.id
                    new_logs.append(data)
                    last_check = datetime.fromisoformat(data['timestamp'].replace('Z', '+00:00')).replace(tzinfo=None)
                
                if new_logs:
                    yield f"data: {json.dumps({'logs': new_logs})}\n\n"
                
                yield f"data: {json.dumps({'heartbeat': True, 'time': datetime.utcnow().isoformat()})}\n\n"
                
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
            
            import time
            time.sleep(2)
    
    return Response(
        stream_with_context(event_stream()),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'}
    )

# ═══════════════════════════════════════════════════════════════════════════════
# Terminal Commands (Live Data)
# ═══════════════════════════════════════════════════════════════════════════════

COMMAND_HANDLERS = {
    'help': lambda: {
        'output': '''Available commands:
  status     - Show unified system status
  nodes      - List all infrastructure nodes
  metrics    - Show trading metrics
  pm         - Show PM dashboard summary
  logs       - Show recent log summary
  prices     - Show current market prices
  clear      - Clear terminal
  help       - Show this help''',
        'type': 'info'
    },
    'clear': lambda: {'output': '', 'type': 'clear'}
}

async def get_status_command() -> Dict[str, str]:
    """Get live status for terminal"""
    gateway = await fetch_gateway_status()
    pm = await fetch_pm_dashboard()
    
    pi_cluster = gateway.get('pi_cluster', {}) if isinstance(gateway, dict) else {}
    pi1_status = normalize_status(pi_cluster.get('pi1', {}).get('status'))
    pi2_status = normalize_status(pi_cluster.get('pi2', {}).get('status'))
    
    pm_stats = pm.get('stats', {}) if isinstance(pm, dict) else {}
    
    output = f'''System Status:
  Trading: {"✅ ONLINE" if gateway.get("status") != "error" else "❌ ERROR"}
  RARI1 (Controller): {pi1_status.upper()}
  RARI2 (Execution): {pi2_status.upper()}
  PM Projects: {pm_stats.get("total_projects", 0)}
  PM Tasks: {pm_stats.get("total_tasks", 0)} ({pm_stats.get("completed_this_week", 0)} this week)'''
    
    return {'output': output, 'type': 'success'}

async def get_nodes_command() -> Dict[str, str]:
    """Get live nodes for terminal"""
    gateway = await fetch_gateway_status()
    
    pi_cluster = gateway.get('pi_cluster', {}) if isinstance(gateway, dict) else {}
    pi1 = pi_cluster.get('pi1', {}) if isinstance(pi_cluster.get('pi1'), dict) else {}
    pi2 = pi_cluster.get('pi2', {}) if isinstance(pi_cluster.get('pi2'), dict) else {}
    
    output = f'''Network Nodes:
  [{normalize_status(pi1.get("status")).upper()}] RARI1 - Controller (Workbench)
  [{normalize_status(pi2.get("status")).upper()}] RARI2 - Execution Engine
  [{normalize_status(gateway.get("status")).upper()}] Cloud Run - API Gateway
  [{normalize_status(gateway.get("ollama_status")).upper()}] Ollama AI - Local Models'''
    
    return {'output': output, 'type': 'info'}

async def get_pm_command() -> Dict[str, str]:
    """Get PM summary for terminal"""
    pm = await fetch_pm_dashboard()
    stats = pm.get('stats', {}) if isinstance(pm, dict) else {}
    
    output = f'''PM Dashboard:
  Projects: {stats.get("total_projects", 0)}
  Total Tasks: {stats.get("total_tasks", 0)}
  Completed This Week: {stats.get("completed_this_week", 0)}
  Active Cycle: {pm.get("active_cycle", {}).get("name", "None")}'''
    
    return {'output': output, 'type': 'success'}

@app.route('/api/terminal', methods=['POST'])
@requires_auth
def api_terminal():
    """Execute terminal commands with live data"""
    data = request.get_json()
    command = data.get('command', '').strip().lower()
    
    # Static commands
    if command in COMMAND_HANDLERS:
        return jsonify(COMMAND_HANDLERS[command]())
    
    # Live data commands
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        if command == 'status':
            result = loop.run_until_complete(get_status_command())
        elif command == 'nodes':
            result = loop.run_until_complete(get_nodes_command())
        elif command == 'pm':
            result = loop.run_until_complete(get_pm_command())
        elif command == 'metrics':
            metrics = loop.run_until_complete(fetch_metrics_from_firestore())
            result = {
                'output': f"24h PnL: {metrics.get('pnl_24h', 0):.2f}% | Win Rate: {metrics.get('win_rate', 0):.1f}% | Latency: {metrics.get('latency_ms', 0)}ms",
                'type': 'success'
            }
        elif command == 'prices':
            prices = loop.run_until_complete(fetch_market_prices())
            if 'error' not in prices:
                result = {
                    'output': f"BTC: ${prices.get('BTC', {}).get('price', 0):,.0f} ({prices.get('BTC', {}).get('change', 0):+.2f}%) | ETH: ${prices.get('ETH', {}).get('price', 0):,.0f} ({prices.get('ETH', {}).get('change', 0):+.2f}%)",
                    'type': 'success'
                }
            else:
                result = {'output': f"Error fetching prices: {prices.get('error')}", 'type': 'error'}
        else:
            result = {'output': f"Command not found: {command}. Type 'help' for available commands.", 'type': 'error'}
        
        return jsonify(result)
    except Exception as e:
        return jsonify({'output': f"Error: {str(e)}", 'type': 'error'})

# ═══════════════════════════════════════════════════════════════════════════════
# Dashboard Data (Consolidated)
# ═══════════════════════════════════════════════════════════════════════════════

@app.route('/api/dashboard')
@requires_auth
def api_dashboard():
    """Return consolidated dashboard data (single call for frontend)"""
    cached = cache.get('dashboard', ttl=5)
    if cached:
        return jsonify(cached)
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # Fetch everything in parallel
    tasks = [
        fetch_gateway_status(),
        fetch_pm_dashboard(),
        fetch_market_prices(),
        fetch_metrics_from_firestore()
    ]
    
    gateway, pm, prices, metrics = loop.run_until_complete(
        asyncio.gather(*tasks, return_exceptions=True)
    )
    
    # Process results
    result = {
        'status': {
            'trading': normalize_status(gateway.get('status') if isinstance(gateway, dict) else 'error'),
            'pm': 'online' if isinstance(pm, dict) and 'stats' in pm else 'offline'
        },
        'prices': prices if isinstance(prices, dict) and 'error' not in prices else None,
        'pm_summary': {
            'projects': pm.get('stats', {}).get('total_projects', 0) if isinstance(pm, dict) else 0,
            'tasks': pm.get('stats', {}).get('total_tasks', 0) if isinstance(pm, dict) else 0,
            'completed_this_week': pm.get('stats', {}).get('completed_this_week', 0) if isinstance(pm, dict) else 0
        } if isinstance(pm, dict) else None,
        'trading_summary': {
            'pnl_24h': metrics.get('pnl_24h', 0) if isinstance(metrics, dict) else 0,
            'win_rate': metrics.get('win_rate', 0) if isinstance(metrics, dict) else 0,
            'active_signals': metrics.get('active_signals', 0) if isinstance(metrics, dict) else 0
        } if isinstance(metrics, dict) and 'error' not in metrics else None,
        'timestamp': datetime.utcnow().isoformat(),
        'version': CONFIG.VERSION
    }
    
    cache.set('dashboard', result)
    return jsonify(result)

# ═══════════════════════════════════════════════════════════════════════════════
# Main Entry Point
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8082))
    
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║           SAPPHIRE OS - COMMAND DECK v{CONFIG.VERSION}                    ║
║                                                              ║
║  Unified Trading & PM Dashboard                              ║
║  Port: {port}                                                  ║
║  Auth: {'Enabled ' if CONFIG.ENABLE_AUTH else 'Disabled'}                                        ║
║  PM Hub: {CONFIG.PM_HUB_URL.split('//')[1][:30]:<30}          ║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    app.run(host='0.0.0.0', port=port, debug=False)
