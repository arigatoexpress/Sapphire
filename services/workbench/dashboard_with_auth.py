#!/usr/bin/env python3
"""
Sapphire Trading Dashboard - With Authentication
This version adds basic auth protection to the dashboard
"""

from flask import Flask, render_template, jsonify, request, Response
import asyncio
import aiohttp
import os
import time
from datetime import datetime, timedelta
from functools import wraps

app = Flask(__name__)

# Configuration
GATEWAY_URL = os.environ.get('GATEWAY_URL', 'https://sapphire-gateway-267358751314.us-central1.run.app')
RARI1_IP = os.environ.get('RARI1_IP', '10.0.0.1')
RARI2_IP = os.environ.get('RARI2_IP', '10.0.0.2')
CACHE_DURATION = 10
PRICE_CACHE_DURATION = 30

# Auth Configuration
AUTH_USERNAME = os.environ.get('AUTH_USERNAME', 'admin')
AUTH_PASSWORD = os.environ.get('AUTH_PASSWORD', 'sapphire2024')
ENABLE_AUTH = os.environ.get('ENABLE_AUTH', 'true').lower() == 'true'

# Simple in-memory cache
cache = {}

def check_auth(username, password):
    """Verify credentials"""
    return username == AUTH_USERNAME and password == AUTH_PASSWORD

def authenticate():
    """Send 401 response with WWW-Authenticate header"""
    return Response(
        'Could not verify your access level.\n'
        'You have to login with proper credentials', 401,
        {'WWW-Authenticate': 'Basic realm="Sapphire Trading Dashboard"'}
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

def get_cached(key, duration=CACHE_DURATION):
    """Get cached value if not expired"""
    if key in cache:
        value, timestamp = cache[key]
        if time.time() - timestamp < duration:
            return value
    return None

def set_cache(key, value):
    """Set cached value with timestamp"""
    cache[key] = (value, time.time())

async def fetch_from_gateway(endpoint, timeout=10):
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

async def fetch_market_prices():
    """Fetch real-time crypto prices from CoinGecko"""
    cached = get_cached('market_prices', PRICE_CACHE_DURATION)
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

# Protected Routes
@app.route('/')
@requires_auth
def dashboard():
    """Main dashboard view - requires authentication"""
    return render_template('dashboard.html')

@app.route('/api/status')
@requires_auth
def api_status():
    """Return system status"""
    cached = get_cached('system_status')
    if cached:
        return jsonify(cached)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    status = loop.run_until_complete(fetch_from_gateway('/api/v1/status'))
    
    result = {
        'gateway': {'status': 'healthy', 'region': 'us-central1'},
        'cloud': {'dashboard': 'healthy', 'pm_hub': 'healthy'},
        'pi_cluster': status.get('pi_cluster', {
            'pi1': {'status': 'unknown'},
            'pi2': {'status': 'unknown'}
        }),
        'vpn': {'status': 'connected', 'location': 'Secure Tunnel'},
        'timestamp': datetime.utcnow().isoformat()
    }
    
    set_cache('system_status', result)
    return jsonify(result)

@app.route('/api/workbench/stats')
@requires_auth
def workbench_stats():
    """Return workbench statistics"""
    cached = get_cached('workbench_stats')
    if cached:
        return jsonify(cached)
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    stats = loop.run_until_complete(fetch_from_gateway('/api/v1/workbench/stats'))
    
    if 'error' in stats:
        stats = {
            'total_proposals': 0,
            'executed': 0,
            'pending_analysis': 0,
            'failed': 0,
            'success_rate': 0,
            'error': stats.get('error', 'Unknown error')
        }
    
    set_cache('workbench_stats', stats)
    return jsonify(stats)

@app.route('/api/proposals')
@requires_auth
def proposals():
    """Return recent trade proposals"""
    cached = get_cached('proposals')
    if cached:
        return jsonify(cached)
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    result = loop.run_until_complete(fetch_from_gateway('/api/v1/workbench/proposals?limit=20'))
    
    if 'error' in result:
        result = {'proposals': []}
    
    set_cache('proposals', result)
    return jsonify(result)

@app.route('/api/market/prices')
@requires_auth
def market_prices():
    """Return real-time crypto prices"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    prices = loop.run_until_complete(fetch_market_prices())
    return jsonify(prices)

@app.route('/api/dashboard-data')
@requires_auth
def dashboard_data():
    """Return consolidated dashboard data"""
    cached = get_cached('dashboard_data', duration=5)
    if cached:
        return jsonify(cached)
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    prices = loop.run_until_complete(fetch_market_prices())
    workbench = loop.run_until_complete(fetch_from_gateway('/api/v1/workbench/stats'))
    trading = loop.run_until_complete(fetch_from_gateway('/api/v1/trading/status'))
    
    result = {
        'metrics': {
            'pnl': 0.0,
            'daily_trades': workbench.get('executed', 0) if 'error' not in workbench else 0,
            'trade_limit': 10,
            'success_rate': workbench.get('success_rate', 0) * 100 if 'error' not in workbench else 0,
            'balance': 0,
            'pending_proposals': workbench.get('pending_analysis', 0) if 'error' not in workbench else 0
        },
        'prices': prices if 'error' not in prices else None,
        'workbench': workbench if 'error' not in workbench else None,
        'trading': trading if 'error' not in trading else None,
        'timestamp': datetime.utcnow().isoformat()
    }
    
    set_cache('dashboard_data', result)
    return jsonify(result)

# Public Routes (no auth required)
@app.route('/health')
def health():
    """Health check endpoint - public"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat()
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)