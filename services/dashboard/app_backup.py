#!/usr/bin/env python3
"""
Sapphire Trading Dashboard - Modern Unified Interface
Real-time monitoring for Pi cluster, trading operations, and PM integration
Uses Gateway API for Pi cluster access from Cloud Run
"""

from flask import Flask, render_template, jsonify
import asyncio
import aiohttp
import os
import time
from datetime import datetime, timedelta
from functools import lru_cache

app = Flask(__name__)

# Configuration
GATEWAY_URL = os.environ.get('GATEWAY_URL', 'https://sapphire-gateway-267358751314.us-central1.run.app')
RARI1_IP = os.environ.get('RARI1_IP', '10.0.0.1')  # Used as fallback
RARI2_IP = os.environ.get('RARI2_IP', '10.0.0.2')  # Used as fallback
CACHE_DURATION = 10  # seconds for most data
PRICE_CACHE_DURATION = 30  # seconds for prices (rate limiting)

# Simple in-memory cache
cache = {}

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
    """Fetch data from Gateway API (works from Cloud Run)"""
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

async def fetch_from_rari1(endpoint, timeout=5):
    """Fetch data from rari1 (Controller) - direct connection"""
    try:
        async with aiohttp.ClientSession() as session:
            url = f"http://{RARI1_IP}{endpoint}"
            async with session.get(url, timeout=timeout) as resp:
                if resp.status == 200:
                    return await resp.json()
                return {"error": f"HTTP {resp.status}", "status": "error"}
    except asyncio.TimeoutError:
        return {"error": "Timeout", "status": "offline"}
    except Exception as e:
        return {"error": str(e), "status": "error"}

async def fetch_from_rari2(endpoint, timeout=5):
    """Fetch data from rari2 (Trading Engine) - direct connection"""
    try:
        async with aiohttp.ClientSession() as session:
            url = f"http://{RARI2_IP}{endpoint}"
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
            # Fetch BTC, ETH, SOL prices in USD
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

async def fetch_lighter_balance():
    """Fetch real balance from Lighter exchange via Gateway"""
    cached = get_cached('lighter_balance', CACHE_DURATION)
    if cached:
        return cached
    
    # Try gateway first (works from Cloud Run)
    result = await fetch_from_gateway('/api/v1/trading/balance')
    
    if 'error' not in result:
        set_cache('lighter_balance', result)
        return result
    
    # Fallback to direct connection
    try:
        async with aiohttp.ClientSession() as session:
            url = f"http://{RARI2_IP}:18888/balance"
            async with session.get(url, timeout=5) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    result = {
                        'balance': data.get('balance', 0),
                        'account_index': data.get('account_index', 1),
                        'currency': data.get('currency', 'USDC'),
                        'timestamp': datetime.utcnow().isoformat()
                    }
                    set_cache('lighter_balance', result)
                    return result
                return {'error': f'HTTP {resp.status}', 'balance': 0}
    except Exception as e:
        return {'error': str(e), 'balance': 0}

@app.route('/')
def dashboard():
    """Main dashboard view"""
    return render_template('dashboard.html')

@app.route('/api/status')
def api_status():
    """Return comprehensive system status from Pi cluster via Gateway"""
    cached = get_cached('system_status')
    if cached:
        return jsonify(cached)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # Fetch from gateway
    status = loop.run_until_complete(fetch_from_gateway('/api/v1/status'))
    
    result = {
        'gateway': {'status': 'healthy', 'region': 'us-central1'},
        'cloud': {
            'dashboard': 'healthy',
            'pm_hub': 'healthy'
        },
        'pi_cluster': status.get('pi_cluster', {
            'pi1': {'status': 'unknown'},
            'pi2': {'status': 'unknown'}
        }),
        'vpn': {
            'status': 'connected',
            'location': 'Secure Tunnel'
        },
        'timestamp': datetime.utcnow().isoformat()
    }
    
    set_cache('system_status', result)
    return jsonify(result)

@app.route('/api/workbench/stats')
def workbench_stats():
    """Return workbench statistics via Gateway"""
    cached = get_cached('workbench_stats')
    if cached:
        return jsonify(cached)
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # Try gateway first
    stats = loop.run_until_complete(fetch_from_gateway('/api/v1/workbench/stats'))
    
    if 'error' in stats:
        # Fallback to direct
        stats = loop.run_until_complete(fetch_from_rari1(':18891/workbench/stats'))
    
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
def proposals():
    """Return recent trade proposals via Gateway"""
    cached = get_cached('proposals')
    if cached:
        return jsonify(cached)
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # Try gateway first
    result = loop.run_until_complete(fetch_from_gateway('/api/v1/workbench/proposals?limit=20'))
    
    if 'error' in result:
        # Fallback to direct
        result = loop.run_until_complete(fetch_from_rari1(':18891/workbench/proposals?limit=20'))
    
    if 'error' in result:
        result = {'proposals': []}
    
    set_cache('proposals', result)
    return jsonify(result)

@app.route('/api/trading/status')
def trading_status():
    """Return trading engine status via Gateway"""
    cached = get_cached('trading_status')
    if cached:
        return jsonify(cached)
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    status = loop.run_until_complete(fetch_from_gateway('/api/v1/trading/status'))
    
    if 'error' in status:
        status = loop.run_until_complete(fetch_from_rari2(':18888/status'))
    
    if 'error' in status:
        status = {'status': 'offline', 'error': status.get('error', 'Unknown')}
    
    set_cache('trading_status', status)
    return jsonify(status)

@app.route('/api/market/prices')
def market_prices():
    """Return real-time crypto prices"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    prices = loop.run_until_complete(fetch_market_prices())
    return jsonify(prices)

@app.route('/api/balance')
def account_balance():
    """Return real Lighter account balance"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    balance = loop.run_until_complete(fetch_lighter_balance())
    return jsonify(balance)

@app.route('/api/dashboard-data')
def dashboard_data():
    """Return consolidated dashboard data with real prices and balance"""
    cached = get_cached('dashboard_data', duration=5)
    if cached:
        return jsonify(cached)
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # Fetch all data concurrently
    prices = loop.run_until_complete(fetch_market_prices())
    balance = loop.run_until_complete(fetch_lighter_balance())
    
    # Try gateway for Pi data
    workbench = loop.run_until_complete(fetch_from_gateway('/api/v1/workbench/stats'))
    if 'error' in workbench:
        workbench = loop.run_until_complete(fetch_from_rari1(':18891/workbench/stats'))
    
    trading = loop.run_until_complete(fetch_from_gateway('/api/v1/trading/status'))
    if 'error' in trading:
        trading = loop.run_until_complete(fetch_from_rari2(':18888/status'))
    
    result = {
        'metrics': {
            'pnl': 0.0,
            'daily_trades': workbench.get('executed', 0) if 'error' not in workbench else 0,
            'trade_limit': 10,
            'success_rate': workbench.get('success_rate', 0) * 100 if 'error' not in workbench else 0,
            'balance': balance.get('balance', 0) if 'error' not in balance else 0,
            'pending_proposals': workbench.get('pending_analysis', 0) if 'error' not in workbench else 0
        },
        'prices': prices if 'error' not in prices else None,
        'workbench': workbench if 'error' not in workbench else None,
        'trading': trading if 'error' not in trading else None,
        'timestamp': datetime.utcnow().isoformat()
    }
    
    set_cache('dashboard_data', result)
    return jsonify(result)

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat()
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)