#!/usr/bin/env python3
"""
Sapphire Trading Dashboard
Real-time trading system monitor and control interface
"""

import json
import os
import time
from datetime import datetime
from functools import wraps

import aiohttp
from flask import Flask, Response, jsonify, render_template, request

app = Flask(__name__)

# Configuration
# Pi-less mode: services run on Mac (localhost) and rari2 (Tailscale)
RARI1_IP = os.environ.get('RARI1_IP', '127.0.0.1')  # control-plane on Mac
RARI2_IP = os.environ.get('RARI2_IP', '100.87.225.89')  # rari2 via Tailscale
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')

# Auth configuration — credentials required via environment variables
AUTH_USERNAME = os.environ.get('AUTH_USERNAME', 'sapphire')
AUTH_PASSWORD = os.environ.get('AUTH_PASSWORD', '')

if not AUTH_PASSWORD:
    raise RuntimeError("AUTH_PASSWORD environment variable must be set")

def check_auth(username, password):
    return username == AUTH_USERNAME and password == AUTH_PASSWORD

def authenticate():
    return Response(
        'Authentication required.',
        401,
        {'WWW-Authenticate': 'Basic realm="Sapphire Dashboard"'}
    )

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated

# Cache for data
_cache = {}
_cache_time = {}
CACHE_DURATION = 10  # seconds

def get_cached(key, fetch_func):
    """Get cached data or fetch fresh"""
    now = time.time()
    if key in _cache and now - _cache_time.get(key, 0) < CACHE_DURATION:
        return _cache[key]

    try:
        data = fetch_func()
        _cache[key] = data
        _cache_time[key] = now
        return data
    except Exception as e:
        print(f"Error fetching {key}: {e}")
        return _cache.get(key, {})

async def fetch_from_rari1(endpoint):
    """Fetch data from rari1"""
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(f'http://{RARI1_IP}{endpoint}', timeout=5) as resp:
                if resp.status == 200:
                    return await resp.json()
        except:
            pass
    return {}

async def fetch_from_rari2(endpoint):
    """Fetch data from rari2"""
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(f'http://{RARI2_IP}{endpoint}', timeout=5) as resp:
                if resp.status == 200:
                    return await resp.json()
        except:
            pass
    return {}

def fetch_sync(url):
    """Synchronous fetch"""
    import urllib.request
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            return json.loads(response.read())
    except:
        return {}

@app.route('/')
@requires_auth
def index():
    """Main dashboard — overview page"""
    return render_template('pages/overview.html', current_page='overview', page_title='System Overview')


@app.route('/architecture')
@requires_auth
def architecture():
    return render_template('pages/architecture.html', current_page='architecture', page_title='Architecture')


@app.route('/intelligence')
@requires_auth
def intelligence():
    return render_template('pages/intelligence.html', current_page='intelligence', page_title='Intelligence')


@app.route('/organization')
@requires_auth
def organization():
    return render_template('pages/organization.html', current_page='organization', page_title='Organization')


@app.route('/activity')
@requires_auth
def activity():
    return render_template('pages/activity.html', current_page='activity', page_title='Activity')


@app.route('/sapphire-book')
@requires_auth
def sapphire_book():
    return render_template('pages/sapphire_book.html', current_page='sapphire_book', page_title='Sapphire Book')


@app.route('/infrastructure')
@requires_auth
def infrastructure():
    return render_template('pages/infrastructure.html', current_page='infrastructure', page_title='Infrastructure')


@app.route('/control')
@requires_auth
def control():
    return render_template('pages/control.html', current_page='control', page_title='Control')


@app.route('/settings')
@requires_auth
def settings():
    return render_template('pages/settings.html', current_page='settings', page_title='Settings')

@app.route('/api/status')
@requires_auth
def api_status():
    """Get system status"""
    def fetch():
        # Fetch from rari2 (trading engine)
        rari2_status = fetch_sync(f'http://{RARI2_IP}:18888/status')

        # Fetch from rari1 (workbench)
        workbench_stats = fetch_sync(f'http://{RARI1_IP}:18891/workbench/stats')

        return {
            'rari2': rari2_status,
            'workbench': workbench_stats,
            'timestamp': datetime.now().isoformat()
        }

    return jsonify(get_cached('status', fetch))

@app.route('/api/watchlist')
@requires_auth
def api_watchlist():
    """Get organized watchlist"""
    watchlist = {
        'major_crypto': [
            {'symbol': 'ETH', 'name': 'Ethereum', 'type': 'perp', 'priority': 'HIGH', 'price': 3500.0},
            {'symbol': 'BTC', 'name': 'Bitcoin', 'type': 'perp', 'priority': 'HIGH', 'price': 65000.0},
        ],
        'mid_cap': [
            {'symbol': 'SOL', 'name': 'Solana', 'type': 'perp', 'priority': 'MEDIUM', 'price': 145.0},
            {'symbol': 'HYPE', 'name': 'Hyperliquid', 'type': 'spot', 'priority': 'MEDIUM', 'price': 12.5},
        ],
        'pair_analysis': [
            {'symbol': 'ETHBTC', 'name': 'ETH/BTC Ratio', 'type': 'pair', 'priority': 'HIGH',
             'strategy': 'Z<-2: BUY ETH, Z>2: SELL ETH'},
            {'symbol': 'SOLBTC', 'name': 'SOL/BTC Ratio', 'type': 'pair', 'priority': 'MEDIUM',
             'strategy': 'Z<-2: BUY SOL, Z>2: SELL SOL'},
        ]
    }
    return jsonify(watchlist)

@app.route('/api/proposals')
@requires_auth
def api_proposals():
    """Get trade proposals"""
    def fetch():
        return fetch_sync(f'http://{RARI1_IP}:18891/workbench/proposals')
    return jsonify(get_cached('proposals', fetch))

@app.route('/api/opportunities')
@requires_auth
def api_opportunities():
    """Get trading opportunities"""
    opportunities = [
        {
            'symbol': 'ETH',
            'side': 'buy',
            'confidence': 0.85,
            'z_score': -2.3,
            'reason': 'ETH undervalued vs BTC',
            'timestamp': datetime.now().isoformat()
        }
    ]
    return jsonify(opportunities)

@app.route('/api/logs')
@requires_auth
def api_logs():
    """Get recent logs"""
    logs = [
        {'time': datetime.now().isoformat(), 'level': 'INFO', 'message': 'System operational'},
        {'time': datetime.now().isoformat(), 'level': 'INFO', 'message': 'Agent analysis complete'},
    ]
    return jsonify(logs)

@app.route('/health')
def health():
    """Health check endpoint — public"""
    return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
