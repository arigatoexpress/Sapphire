#!/usr/bin/env python3
"""
Sapphire Unified Frontend
Multi-page dashboard with shared navigation and live status APIs.
"""

from datetime import datetime, timedelta, timezone
from functools import wraps
from concurrent.futures import ThreadPoolExecutor
import os
import time
from urllib.parse import urljoin

import requests
from firebase_admin import credentials, firestore, get_app, initialize_app
from flask import Flask, render_template, jsonify, request, Response

app = Flask(__name__)

# Configuration
GATEWAY_URL = os.environ.get('GATEWAY_URL', 'https://sapphire-gateway-267358751314.us-central1.run.app')
ALPHA_ENGINE_URL = os.environ.get('ALPHA_ENGINE_URL', 'https://sapphire-alpha-267358751314.us-central1.run.app')
PM_HUB_URL = os.environ.get('PM_HUB_URL', 'https://agentic-pm-hub-267358751314.us-central1.run.app')
TELEGRAM_BOT_URL = os.environ.get('TELEGRAM_BOT_URL', 'https://sapphire-telegram-bot-267358751314.us-central1.run.app')
THO_AGENT_URL = os.environ.get('THO_AGENT_URL', 'https://tho-agent-267358751314.us-central1.run.app')
SCOUT_SANDBOX_URL = os.environ.get('SCOUT_SANDBOX_URL', 'https://sapphire-scout-sandbox-267358751314.us-central1.run.app')

RARI1_IP = os.environ.get('RARI1_IP', '100.120.191.1')
RARI2_IP = os.environ.get('RARI2_IP', '100.87.225.89')
WINDOWS_IP = os.environ.get('WINDOWS_IP', '100.71.10.48')

RARI1_HEALTH_URL = os.environ.get('RARI1_HEALTH_URL', f'http://{RARI1_IP}:8080/health')
RARI2_HEALTH_URL = os.environ.get('RARI2_HEALTH_URL', f'http://{RARI2_IP}:18888/health')
WINDOWS_HEALTH_URL = os.environ.get('WINDOWS_HEALTH_URL', f'http://{WINDOWS_IP}:9090/webhook/health')

CACHE_DURATION = int(os.environ.get('CACHE_DURATION', '10'))
PRICE_CACHE_DURATION = int(os.environ.get('PRICE_CACHE_DURATION', '30'))
GCP_PROJECT = os.environ.get('GCP_PROJECT', 'sapphire-479610')
TRADING_METRICS_COLLECTION = os.environ.get('TRADING_METRICS_COLLECTION', 'trading_metrics')
SYSTEM_LOGS_COLLECTION = os.environ.get('SYSTEM_LOGS_COLLECTION', 'system_logs')
EDGE_CAPABILITIES_COLLECTION = os.environ.get('EDGE_CAPABILITIES_COLLECTION', 'edge_capabilities')

CRITICAL_EDGE_SERVICES = {
    item.strip() for item in os.environ.get(
        'CRITICAL_EDGE_SERVICES',
        'rari1_trading_api,rari2_trading_api,rari2_lighter_api',
    ).split(',')
    if item.strip()
}

# Auth Configuration
AUTH_USERNAME = os.environ.get('AUTH_USERNAME', 'sapphire')
AUTH_PASSWORD = os.environ.get('AUTH_PASSWORD', 'alpha2024')
ENABLE_AUTH = os.environ.get('ENABLE_AUTH', 'true').lower() == 'true'

# Simple in-memory cache
cache = {}

try:
    get_app()
    db = firestore.client()
except ValueError:
    try:
        cred = credentials.ApplicationDefault()
        initialize_app(cred, {'projectId': GCP_PROJECT})
        db = firestore.client()
    except Exception:
        db = None

SERVICE_CHECKS = {
    'gateway': {'base': GATEWAY_URL, 'path': '/health', 'auth': False},
    'gateway_signal_ingress': {'base': GATEWAY_URL, 'path': '/webhook/health', 'auth': False},
    'alpha_engine': {'base': ALPHA_ENGINE_URL, 'path': '/health', 'auth': False},
    'pm_hub': {'base': PM_HUB_URL, 'path': '/health', 'auth': False},
    'telegram_bot': {'base': TELEGRAM_BOT_URL, 'path': '/health', 'auth': False},
    'tho_agent': {'base': THO_AGENT_URL, 'path': '/health', 'auth': False},
    'scout_sandbox': {'base': SCOUT_SANDBOX_URL, 'path': '/health', 'auth': False},
}

ORG_MODEL = {
    'name': 'Sapphire Autonomous Organization',
    'framework': 'Proprietary Agentic Project Management Framework',
    'mission': 'Autonomous execution, safe self-improvement, and cross-domain operational excellence.',
    'departments': [
        {
            'id': 'org_core',
            'name': 'Autonomous Organization Core',
            'focus': 'Agentic PM governance and autonomous execution loops',
            'systems': ['Agentic PM Hub', 'Organization OS', 'Command governance'],
        },
        {
            'id': 'trading_research',
            'name': 'Trading & Research Department',
            'focus': 'Markets, news, crypto signals, and model-assisted analysis',
            'systems': ['Signal pipeline', 'Execution routing', 'Alpha analysis'],
        },
        {
            'id': 'development',
            'name': 'Development Department',
            'focus': 'Client project delivery and platform builds',
            'systems': ['Project Go Forward (THO)', 'BIS Intelligence System'],
        },
        {
            'id': 'blackjackal',
            'name': 'Autonomous Gaming Unit (Blackjackal)',
            'focus': 'Automated poker/blackjack strategy and control systems',
            'systems': ['Blackjackal runtime', 'Decision policies'],
        },
        {
            'id': 'infra_research',
            'name': 'Infrastructure Research Department',
            'focus': 'Cross-environment model and systems R&D',
            'systems': [
                'Tailscale mesh (Pis, Windows, Mac, GCP)',
                'Local open-source model testing (Qwen, DeepSeek)',
                'Managed model testing (Claude, Codex, Kimi, Google Antigravity Code)',
            ],
        },
    ],
    'knowledge_sources': ['GitHub', 'MoltHub', 'MoltBook'],
    'safety_policy': 'Only adopt safe, validated improvements into autonomous production operations.',
}


def check_auth(username, password):
    """Verify credentials"""
    return username == AUTH_USERNAME and password == AUTH_PASSWORD


def authenticate():
    """Send 401 response with WWW-Authenticate header"""
    return Response(
        'Could not verify your access level.\nYou have to login with proper credentials',
        401,
        {'WWW-Authenticate': 'Basic realm="Sapphire Trading System"'}
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


def _join_url(base: str, path: str) -> str:
    return urljoin(base.rstrip('/') + '/', path.lstrip('/'))


def _coerce_datetime(value):
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace('Z', '+00:00'))
        except ValueError:
            return None
    else:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _iso_or_default(value, default=None):
    parsed = _coerce_datetime(value)
    if parsed:
        return parsed.isoformat()
    return default or datetime.utcnow().isoformat()


def _probe_http(url: str, timeout: float = 6, auth_required: bool = False):
    """Probe a URL and classify result with latency."""
    start = time.time()
    try:
        auth = (AUTH_USERNAME, AUTH_PASSWORD) if auth_required else None
        response = requests.get(url, timeout=timeout, auth=auth)
        latency_ms = round((time.time() - start) * 1000, 2)

        if response.status_code in (401, 403):
            # Auth-protected endpoint still indicates service is up.
            return {
                'status': 'protected',
                'healthy': True,
                'status_code': response.status_code,
                'latency_ms': latency_ms,
            }

        healthy = 200 <= response.status_code < 300
        return {
            'status': 'healthy' if healthy else 'unhealthy',
            'healthy': healthy,
            'status_code': response.status_code,
            'latency_ms': latency_ms,
        }
    except requests.Timeout:
        status = 'unreachable_from_cloud' if url.startswith(('http://100.', 'http://192.168.', 'http://10.')) else 'timeout'
        return {'status': status, 'healthy': False, 'status_code': None, 'latency_ms': round((time.time() - start) * 1000, 2)}
    except requests.RequestException as exc:
        return {'status': 'unreachable', 'healthy': False, 'status_code': None, 'latency_ms': round((time.time() - start) * 1000, 2), 'error': str(exc)}


def _get_json(url: str, *, timeout: float = 4.0, params: dict | None = None):
    """Fetch JSON payload from an endpoint with standardized error shape."""
    started = time.time()
    try:
        response = requests.get(url, timeout=timeout, params=params)
        latency_ms = round((time.time() - started) * 1000, 2)
        if response.status_code != 200:
            return {
                'ok': False,
                'status_code': response.status_code,
                'latency_ms': latency_ms,
                'error': f'http_{response.status_code}',
                'data': {},
            }
        payload = response.json() if response.content else {}
        return {
            'ok': True,
            'status_code': 200,
            'latency_ms': latency_ms,
            'error': None,
            'data': payload if isinstance(payload, dict) else {},
        }
    except requests.RequestException as exc:
        return {
            'ok': False,
            'status_code': None,
            'latency_ms': round((time.time() - started) * 1000, 2),
            'error': str(exc),
            'data': {},
        }


def _collect_system_status():
    """Collect live service and node status."""
    cached = get_cached('system_status')
    if cached:
        return cached

    services = {}
    service_targets = {
        name: {
            'url': _join_url(config['base'], config['path']),
            'base': config['base'],
            'auth': config.get('auth', False),
        }
        for name, config in SERVICE_CHECKS.items()
    }
    with ThreadPoolExecutor(max_workers=max(4, len(service_targets))) as pool:
        futures = {
            pool.submit(_probe_http, target['url'], 5.0, target['auth']): name
            for name, target in service_targets.items()
        }
        for future, name in ((f, futures[f]) for f in futures):
            probe = future.result()
            services[name] = {
                'url': service_targets[name]['base'],
                'health_url': service_targets[name]['url'],
                **probe,
            }

    node_targets = {
        'rari1': {'ip': RARI1_IP, 'url': RARI1_HEALTH_URL},
        'rari2': {'ip': RARI2_IP, 'url': RARI2_HEALTH_URL},
        'windows': {'ip': WINDOWS_IP, 'url': WINDOWS_HEALTH_URL},
    }

    nodes = {}
    with ThreadPoolExecutor(max_workers=max(3, len(node_targets))) as pool:
        futures = {
            pool.submit(_probe_http, node['url'], 0.9, False): node_name
            for node_name, node in node_targets.items()
        }
        for future, node_name in ((f, futures[f]) for f in futures):
            # Node checks originate from Cloud Run and may not have direct reachability
            # to private/Tailscale endpoints; strict timeout avoids API stalls.
            probe = future.result()
            node = node_targets[node_name]
            nodes[node_name] = {
                'ip': node['ip'],
                'health_url': node['url'],
                **probe,
            }

    by_category = {
        'cloud': [
            {
                'name': name,
                'healthy': svc.get('healthy', False),
                'status': svc.get('status', 'unknown'),
                'response_time_ms': svc.get('latency_ms'),
            }
            for name, svc in services.items()
        ],
        'pi': [],
        'windows': [],
        'firestore': [],
    }
    for node_name, node in nodes.items():
        row = {
            'name': node_name,
            'healthy': node.get('healthy', False),
            'status': node.get('status', 'unknown'),
            'response_time_ms': node.get('latency_ms'),
        }
        if node_name in {'rari1', 'rari2'}:
            by_category['pi'].append(row)
        elif node_name == 'windows':
            by_category['windows'].append(row)

    firestore_ok = bool(db is not None)
    by_category['firestore'].append({
        'name': 'firestore',
        'healthy': firestore_ok,
        'status': 'healthy' if firestore_ok else 'unavailable',
        'response_time_ms': None,
    })

    # If monitor snapshot is available, prefer its edge-health view because Cloud Run
    # cannot directly probe private Tailscale addresses.
    monitor = _get_monitor_snapshot()
    monitor_by_category = monitor.get('by_category', {}) if monitor.get('available') else {}
    for category in ('pi', 'windows', 'firestore'):
        rows = monitor_by_category.get(category)
        if isinstance(rows, list) and rows:
            normalized_rows = []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                healthy = bool(row.get('healthy', False))
                normalized_rows.append({
                    'name': row.get('name', 'unknown'),
                    'healthy': healthy,
                    'status': 'healthy' if healthy else (row.get('error') or 'unhealthy'),
                    'response_time_ms': row.get('response_time_ms'),
                })
            if normalized_rows:
                by_category[category] = normalized_rows

    def _derive_pi_node(prefix: str):
        rows = [row for row in by_category.get('pi', []) if str(row.get('name', '')).startswith(prefix)]
        if not rows:
            return nodes.get(prefix)
        healthy = all(bool(row.get('healthy', False)) for row in rows)
        return {
            'ip': nodes.get(prefix, {}).get('ip'),
            'health_url': nodes.get(prefix, {}).get('health_url'),
            'healthy': healthy,
            'status': 'healthy' if healthy else 'degraded',
            'status_code': None,
            'latency_ms': next((row.get('response_time_ms') for row in rows if row.get('response_time_ms') is not None), None),
        }

    if monitor.get('available'):
        derived_rari1 = _derive_pi_node('rari1')
        derived_rari2 = _derive_pi_node('rari2')
        if derived_rari1:
            nodes['rari1'] = derived_rari1
        if derived_rari2:
            nodes['rari2'] = derived_rari2

        windows_rows = by_category.get('windows', [])
        if windows_rows:
            critical_windows_rows = [
                row for row in windows_rows
                if str(row.get('name', '')).startswith('windows') and row.get('name') in CRITICAL_EDGE_SERVICES
            ]
            if critical_windows_rows:
                windows_healthy = all(bool(row.get('healthy', False)) for row in critical_windows_rows)
            else:
                windows_healthy = any(bool(row.get('healthy', False)) for row in windows_rows)
            nodes['windows'] = {
                'ip': nodes.get('windows', {}).get('ip'),
                'health_url': nodes.get('windows', {}).get('health_url'),
                'healthy': windows_healthy,
                'status': 'healthy' if windows_healthy else 'degraded',
                'status_code': None,
                'latency_ms': next((row.get('response_time_ms') for row in windows_rows if row.get('response_time_ms') is not None), None),
            }

    healthy_services = sum(1 for s in services.values() if s.get('healthy'))
    healthy_nodes = sum(1 for n in nodes.values() if n.get('healthy'))

    result = {
        'timestamp': datetime.utcnow().isoformat(),
        'services': services,
        'nodes': nodes,
        'by_category': by_category,
        'summary': {
            'service_total': len(services),
            'service_healthy': healthy_services,
            'service_unhealthy': len(services) - healthy_services,
            'node_total': len(nodes),
            'node_healthy': healthy_nodes,
            'node_unhealthy': len(nodes) - healthy_nodes,
        }
    }
    set_cache('system_status', result)
    return result


def _fetch_market_prices():
    """Fetch market prices with fallback providers."""
    cached = get_cached('market_prices', PRICE_CACHE_DURATION)
    if cached:
        return cached

    # Primary source: CoinGecko
    try:
        resp = requests.get(
            'https://api.coingecko.com/api/v3/simple/price',
            params={
                'ids': 'bitcoin,ethereum,solana',
                'vs_currencies': 'usd',
                'include_24hr_change': 'true',
            },
            headers={'Accept': 'application/json', 'User-Agent': 'sapphire-unified-frontend/1.0'},
            timeout=8,
        )
        resp.raise_for_status()
        data = resp.json()

        result = {
            'BTC': {
                'price': data.get('bitcoin', {}).get('usd', 0),
                'change_24h': data.get('bitcoin', {}).get('usd_24h_change', 0),
            },
            'ETH': {
                'price': data.get('ethereum', {}).get('usd', 0),
                'change_24h': data.get('ethereum', {}).get('usd_24h_change', 0),
            },
            'SOL': {
                'price': data.get('solana', {}).get('usd', 0),
                'change_24h': data.get('solana', {}).get('usd_24h_change', 0),
            },
            'source': 'coingecko',
            'timestamp': datetime.utcnow().isoformat(),
        }
        set_cache('market_prices', result)
        return result
    except Exception:
        pass

    # Fallback source: Coinbase spot prices
    try:
        symbols = {'BTC': 'BTC-USD', 'ETH': 'ETH-USD', 'SOL': 'SOL-USD'}
        out = {}
        for symbol, pair in symbols.items():
            resp = requests.get(f'https://api.coinbase.com/v2/prices/{pair}/spot', timeout=8)
            resp.raise_for_status()
            amount = float(resp.json().get('data', {}).get('amount', 0))
            out[symbol] = {'price': amount, 'change_24h': None}

        out['source'] = 'coinbase_spot'
        out['timestamp'] = datetime.utcnow().isoformat()
        set_cache('market_prices', out)
        return out
    except Exception as exc:
        return {'error': f'Failed to fetch prices: {exc}'}


def _get_monitor_snapshot():
    """Read latest cross-environment health snapshot from Firestore."""
    if db is None:
        return {'available': False, 'error': 'firestore_unavailable'}
    try:
        doc = db.collection('system_status').document('current').get()
        if not doc.exists:
            return {'available': False, 'error': 'no_monitor_snapshot'}
        payload = doc.to_dict() or {}
        payload['available'] = True
        return payload
    except Exception as exc:
        return {'available': False, 'error': str(exc)}


def _build_readiness_payload(host_root: str):
    """Compute production readiness gates from live APIs + monitor snapshot."""
    status_data = _collect_system_status()
    service_summary = status_data.get('summary', {})

    def run_contract_check(name, fn):
        started = time.time()
        try:
            fn()
            return {
                'name': name,
                'healthy': True,
                'status': 'healthy',
                'status_code': 200,
                'latency_ms': round((time.time() - started) * 1000, 2),
            }
        except Exception as exc:
            return {
                'name': name,
                'healthy': False,
                'status': 'error',
                'status_code': 500,
                'latency_ms': round((time.time() - started) * 1000, 2),
                'error': str(exc)[:200],
            }

    contract_checks = [
        run_contract_check('/api/platform/status', _collect_system_status),
        run_contract_check('/api/platform/metrics', _platform_metrics_payload),
        run_contract_check('/api/platform/logs', lambda: _fetch_logs(limit=1)),
        run_contract_check('/api/platform/organization', _platform_organization_payload),
        run_contract_check('/api/platform/readiness', lambda: True),
        run_contract_check('/api/platform/projects', _fetch_projects_payload),
    ]

    contract_ok = all(check.get('healthy', False) for check in contract_checks)
    cloud_ok = service_summary.get('service_unhealthy', 1) == 0

    monitor = _get_monitor_snapshot()
    edge_blockers = []
    critical_rows = []
    if monitor.get('available'):
        by_category = monitor.get('by_category', {})
        for category in ('pi', 'windows'):
            for row in by_category.get(category, []):
                if not isinstance(row, dict):
                    continue
                name = row.get('name')
                if name in CRITICAL_EDGE_SERVICES:
                    critical_rows.append({
                        'name': name,
                        'category': category,
                        'healthy': bool(row.get('healthy', False)),
                        'error': row.get('error'),
                    })

        # Fallback: if critical list was misconfigured or no matches found, use all edge rows.
        if not critical_rows:
            for category in ('pi', 'windows'):
                for row in by_category.get(category, []):
                    if not isinstance(row, dict):
                        continue
                    critical_rows.append({
                        'name': row.get('name', 'unknown'),
                        'category': category,
                        'healthy': bool(row.get('healthy', False)),
                        'error': row.get('error'),
                    })

        for row in critical_rows:
            if not row.get('healthy', False):
                edge_blockers.append({
                    'name': row.get('name'),
                    'category': row.get('category'),
                    'error': row.get('error', 'unhealthy'),
                })

    monitor_ok = monitor.get('available', False) and len(edge_blockers) == 0

    gateway_ingress = bool(
        status_data.get('services', {})
        .get('gateway_signal_ingress', {})
        .get('healthy', False)
    )
    windows_ingress = False
    if monitor.get('available'):
        for row in (monitor.get('by_category', {}) or {}).get('windows', []):
            if not isinstance(row, dict):
                continue
            if row.get('name') == 'windows_webhook':
                windows_ingress = bool(row.get('healthy', False))
                break
    signal_ingress_ok = gateway_ingress or windows_ingress

    blockers = []
    for check in contract_checks:
        if not check.get('healthy'):
            blockers.append({'gate': 'A_contracts', 'name': check['name'], 'error': check.get('status', 'failed')})
    if not cloud_ok:
        for service_name, service in status_data.get('services', {}).items():
            if not service.get('healthy'):
                blockers.append({'gate': 'B_cloud', 'name': service_name, 'error': service.get('status', 'unhealthy')})
    for item in edge_blockers:
        blockers.append({'gate': 'C_edge', **item})
    if not signal_ingress_ok:
        blockers.append(
            {
                'gate': 'D_signal_ingress',
                'name': 'tradingview_ingress',
                'error': 'both_gateway_and_windows_ingress_unhealthy',
            }
        )

    gates = {
        'A_contracts': {
            'ok': contract_ok,
            'pass': sum(1 for c in contract_checks if c.get('healthy')),
            'total': len(contract_checks),
        },
        'B_cloud': {
            'ok': cloud_ok,
            'pass': service_summary.get('service_healthy', 0),
            'total': service_summary.get('service_total', 0),
        },
        'C_edge': {
            'ok': monitor_ok,
            'pass': 0 if not monitor.get('available') else max(0, len(critical_rows) - len(edge_blockers)),
            'total': 0 if not monitor.get('available') else len(critical_rows),
            'source': 'system_status/current',
            'critical_services': sorted(CRITICAL_EDGE_SERVICES),
        },
        'D_signal_ingress': {
            'ok': signal_ingress_ok,
            'pass': int(gateway_ingress) + int(windows_ingress),
            'total': 2,
            'sources': {
                'gateway_signal_ingress': gateway_ingress,
                'windows_webhook': windows_ingress,
            },
        },
    }

    overall_ok = all(g.get('ok', False) for g in gates.values())
    return {
        'timestamp': datetime.utcnow().isoformat(),
        'overall_ok': overall_ok,
        'gates': gates,
        'blockers': blockers,
        'contract_checks': contract_checks,
        'cloud': status_data,
        'monitor': {
            'available': monitor.get('available', False),
            'timestamp': monitor.get('timestamp'),
            'error': monitor.get('error'),
        },
    }


def _normalize_trading_metrics_payload(raw=None, source='fallback', error=None):
    raw = raw or {}
    pnl_daily = raw.get('pnl', {}).get('daily') if isinstance(raw.get('pnl'), dict) else raw.get('pnl_24h', 0)
    pnl_weekly = raw.get('pnl', {}).get('weekly') if isinstance(raw.get('pnl'), dict) else raw.get('pnl_7d', 0)
    pnl_monthly = raw.get('pnl', {}).get('monthly') if isinstance(raw.get('pnl'), dict) else raw.get('pnl_30d', 0)
    total_pnl = raw.get('pnl', {}).get('total') if isinstance(raw.get('pnl'), dict) else raw.get('pnl_24h', 0)
    trades_today = raw.get('trades', {}).get('today') if isinstance(raw.get('trades'), dict) else raw.get('trades_today', 0)
    trades_total = raw.get('trades', {}).get('total') if isinstance(raw.get('trades'), dict) else raw.get('trades_limit', 0)
    success_rate = raw.get('trades', {}).get('success_rate') if isinstance(raw.get('trades'), dict) else raw.get('win_rate', 0)

    payload = {
        'pnl': {
            'daily': pnl_daily or 0,
            'weekly': pnl_weekly or 0,
            'monthly': pnl_monthly or 0,
            'total': total_pnl or 0,
        },
        'trades': {
            'today': trades_today or 0,
            'total': trades_total or 0,
            'success_rate': success_rate or 0,
        },
        'positions': raw.get('positions', []),
        'raw': raw,
        'source': source,
        'timestamp': raw.get('timestamp', datetime.utcnow().isoformat()),
    }
    if error:
        payload['error'] = error
    return payload


def _fetch_trading_metrics():
    if db is None:
        return _normalize_trading_metrics_payload(source='firestore_unavailable', error='firestore_unavailable')

    try:
        docs = list(
            db.collection(TRADING_METRICS_COLLECTION)
            .order_by('timestamp', direction=firestore.Query.DESCENDING)
            .limit(1)
            .stream()
        )
    except Exception:
        # Fallback query when sort/index is not available.
        docs = list(db.collection(TRADING_METRICS_COLLECTION).limit(25).stream())
        docs.sort(
            key=lambda doc: _coerce_datetime((doc.to_dict() or {}).get('timestamp')) or datetime.min,
            reverse=True,
        )

    if not docs:
        return _normalize_trading_metrics_payload(source='firestore_empty')

    latest = docs[0]
    raw = latest.to_dict() or {}
    raw['timestamp'] = _iso_or_default(raw.get('timestamp'), default=latest.update_time.isoformat())
    return _normalize_trading_metrics_payload(raw, source='firestore')


def _fetch_logs(hours: int = 24, limit: int = 100, service: str = '', level: str = ''):
    if db is None:
        return {'logs': [], 'count': 0, 'error': 'firestore_unavailable', 'source': 'firestore'}

    since = datetime.now(timezone.utc) - timedelta(hours=max(1, hours))

    def _normalize_log(doc_id, raw):
        entry = dict(raw or {})
        entry['id'] = doc_id
        entry['timestamp'] = _iso_or_default(entry.get('timestamp'))
        entry['service'] = str(entry.get('service', 'system'))
        entry['level'] = str(entry.get('level', 'INFO')).upper()
        entry['message'] = str(entry.get('message', ''))
        return entry

    try:
        query = db.collection(SYSTEM_LOGS_COLLECTION).where('timestamp', '>=', since.isoformat())
        if service:
            query = query.where('service', '==', service)
        if level:
            query = query.where('level', '==', level.upper())
        query = query.order_by('timestamp', direction=firestore.Query.DESCENDING).limit(max(1, min(limit, 500)))
        docs = list(query.stream())
        logs = [_normalize_log(doc.id, doc.to_dict()) for doc in docs]
        return {'logs': logs, 'count': len(logs), 'source': 'firestore'}
    except Exception as exc:
        # Fallback for index/where constraints: pull recent rows and filter in-memory.
        try:
            docs = list(
                db.collection(SYSTEM_LOGS_COLLECTION)
                .order_by('timestamp', direction=firestore.Query.DESCENDING)
                .limit(max(100, min(limit * 5, 500)))
                .stream()
            )
            logs = [_normalize_log(doc.id, doc.to_dict()) for doc in docs]
            filtered = []
            for log in logs:
                ts = _coerce_datetime(log.get('timestamp'))
                if ts and ts < since:
                    continue
                if service and log.get('service') != service:
                    continue
                if level and str(log.get('level', '')).upper() != level.upper():
                    continue
                filtered.append(log)
            return {'logs': filtered[:limit], 'count': len(filtered), 'source': 'firestore_fallback', 'warning': str(exc)}
        except Exception as fallback_exc:
            return {'logs': [], 'count': 0, 'error': str(fallback_exc), 'source': 'firestore_error'}


def _platform_health_summary(status_data=None):
    status_data = status_data or _collect_system_status()
    summary = status_data.get('summary', {})
    return {
        'healthy': summary.get('service_unhealthy', 0) == 0,
        'healthy_count': summary.get('service_healthy', 0),
        'unhealthy_count': summary.get('service_unhealthy', 0),
        'node_healthy_count': summary.get('node_healthy', 0),
        'node_unhealthy_count': summary.get('node_unhealthy', 0),
        'timestamp': status_data.get('timestamp'),
        'by_category': status_data.get('by_category', {}),
    }


def _platform_metrics_payload():
    cached = get_cached('platform_metrics', duration=15)
    if cached:
        return cached

    status_data = _collect_system_status()
    payload = {
        'timestamp': datetime.utcnow().isoformat(),
        'trading': _fetch_trading_metrics(),
        'market': _fetch_market_prices(),
        'health': _platform_health_summary(status_data),
        'status': status_data,
        'windows_lab': _fetch_windows_lab_payload(),
    }
    set_cache('platform_metrics', payload)
    return payload


def _fetch_windows_lab_payload():
    cached = get_cached('windows_lab', duration=20)
    if cached:
        return cached

    if db is None:
        payload = {
            'available': False,
            'error': 'firestore_unavailable',
            'source': 'edge_capabilities/windows_lab',
            'timestamp': datetime.utcnow().isoformat(),
        }
        set_cache('windows_lab', payload)
        return payload

    try:
        doc = db.collection(EDGE_CAPABILITIES_COLLECTION).document('windows_lab').get()
        if not doc.exists:
            payload = {
                'available': False,
                'error': 'windows_lab_not_reported',
                'source': f'{EDGE_CAPABILITIES_COLLECTION}/windows_lab',
                'timestamp': datetime.utcnow().isoformat(),
            }
            set_cache('windows_lab', payload)
            return payload

        raw = doc.to_dict() or {}
        updated_at = _coerce_datetime(raw.get('updated_at') or raw.get('timestamp'))
        age_seconds = None
        stale = True
        if updated_at is not None:
            age_seconds = max(0, int((datetime.now(timezone.utc) - updated_at).total_seconds()))
            stale = age_seconds > 900

        payload = {
            **raw,
            'available': bool(raw.get('available', True)),
            'stale': stale,
            'age_seconds': age_seconds,
            'source': f'{EDGE_CAPABILITIES_COLLECTION}/windows_lab',
            'timestamp': datetime.utcnow().isoformat(),
        }
        set_cache('windows_lab', payload)
        return payload
    except Exception as exc:
        payload = {
            'available': False,
            'error': str(exc),
            'source': f'{EDGE_CAPABILITIES_COLLECTION}/windows_lab',
            'timestamp': datetime.utcnow().isoformat(),
        }
        set_cache('windows_lab', payload)
        return payload


def _fetch_projects_payload():
    cached = get_cached('platform_projects', duration=30)
    if cached:
        return cached

    overview_url = _join_url(PM_HUB_URL, '/api/projects/overview?refresh=true')
    projects = []
    error = None
    try:
        resp = requests.get(overview_url, timeout=4)
        if resp.status_code == 200:
            parsed = resp.json()
            data = parsed if isinstance(parsed, dict) else {}
            tracked = data.get('tracked_projects', [])
            for item in tracked:
                if not isinstance(item, dict):
                    continue
                missing_local = bool(item.get('missing_local'))
                missing_github = bool(item.get('missing_github'))
                if missing_local or missing_github:
                    status = 'blocked'
                    progress = 30
                else:
                    status = 'active'
                    progress = 70
                projects.append({
                    'id': item.get('id', ''),
                    'name': item.get('name', item.get('id', 'Project')),
                    'status': status,
                    'progress': progress,
                    'missing_local': missing_local,
                    'missing_github': missing_github,
                })
        else:
            error = f'pm_hub_http_{resp.status_code}'
    except requests.RequestException as exc:
        error = str(exc)

    payload = {
        'projects': projects,
        'count': len(projects),
        'source': 'pm_hub',
        'timestamp': datetime.utcnow().isoformat(),
    }
    if error:
        payload['error'] = error
    set_cache('platform_projects', payload)
    return payload


def _platform_organization_payload(refresh: bool = False):
    cache_key = 'platform_organization_refresh' if refresh else 'platform_organization'
    if not refresh:
        cached = get_cached(cache_key, duration=20)
        if cached:
            return cached

    params = {'refresh': 'true'} if refresh else None
    org_url = _join_url(PM_HUB_URL, '/organization')
    status_url = _join_url(PM_HUB_URL, '/health')
    overview_url = _join_url(PM_HUB_URL, '/api/org/overview')
    ops_status_url = _join_url(PM_HUB_URL, '/api/frontend/ops-status')
    logbook_url = _join_url(PM_HUB_URL, '/api/frontend/logbook')

    status_probe = _probe_http(status_url, timeout=2)

    with ThreadPoolExecutor(max_workers=3) as pool:
        overview_future = pool.submit(_get_json, overview_url, timeout=5.0, params=params)
        ops_future = pool.submit(_get_json, ops_status_url, timeout=5.0, params={'event_limit': '20', **(params or {})})
        logbook_future = pool.submit(_get_json, logbook_url, timeout=5.0, params={'event_limit': '24', **(params or {})})
        overview_resp = overview_future.result()
        ops_resp = ops_future.result()
        logbook_resp = logbook_future.result()

    overview = overview_resp.get('data', {})
    ops_status = ops_resp.get('data', {})
    logbook = logbook_resp.get('data', {})

    projects_summary = overview.get('projects_summary', {}) if isinstance(overview.get('projects_summary'), dict) else {}
    control_overview = overview.get('control_plane', {}).get('overview', {}) if isinstance(overview.get('control_plane'), dict) else {}
    trading = overview.get('trading_operations', {}) if isinstance(overview.get('trading_operations'), dict) else {}
    rails = trading.get('rails', []) if isinstance(trading.get('rails'), list) else []
    rails_ready = sum(1 for rail in rails if isinstance(rail, dict) and rail.get('readiness') == 'ready')

    payload = {
        'organization_url': org_url,
        'pm_hub_url': PM_HUB_URL,
        'health': status_probe,
        'model': ORG_MODEL,
        'overview': overview,
        'ops_status': ops_status,
        'logbook': logbook,
        'sources': {
            'overview': {
                'ok': overview_resp.get('ok', False),
                'status_code': overview_resp.get('status_code'),
                'latency_ms': overview_resp.get('latency_ms'),
                'error': overview_resp.get('error'),
            },
            'ops_status': {
                'ok': ops_resp.get('ok', False),
                'status_code': ops_resp.get('status_code'),
                'latency_ms': ops_resp.get('latency_ms'),
                'error': ops_resp.get('error'),
            },
            'logbook': {
                'ok': logbook_resp.get('ok', False),
                'status_code': logbook_resp.get('status_code'),
                'latency_ms': logbook_resp.get('latency_ms'),
                'error': logbook_resp.get('error'),
            },
        },
        'summary': {
            'workspaces': len(overview.get('workspaces', [])) if isinstance(overview.get('workspaces'), list) else 0,
            'tracked_projects': int(projects_summary.get('tracked_project_count', 0) or 0),
            'agents_online': int(control_overview.get('agents_executor_online', control_overview.get('agents_online', 0)) or 0),
            'agents_total': int(control_overview.get('agents_executor_total', control_overview.get('agents_total', 0)) or 0),
            'rails_ready': rails_ready,
            'rails_total': len(rails),
        },
        'generated_at': overview.get('generated_at') or datetime.utcnow().isoformat(),
        'timestamp': datetime.utcnow().isoformat(),
    }
    set_cache(cache_key, payload)
    return payload


# ---------------------------------------------------------------------------
# PAGE ROUTES
# ---------------------------------------------------------------------------

@app.route('/')
@requires_auth
def index():
    return render_template('pages/overview.html', current_page='overview', page_title='Overview')


@app.route('/trading')
@requires_auth
def trading():
    return render_template('pages/trading.html', current_page='trading', page_title='Trading')


@app.route('/command-deck')
@requires_auth
def command_deck():
    return render_template('pages/command_deck.html', current_page='command-deck', page_title='Command Deck')


@app.route('/system-health')
@requires_auth
def system_health():
    return render_template('pages/health.html', current_page='health', page_title='System Health')


@app.route('/logs')
@requires_auth
def logs():
    return render_template('pages/logs.html', current_page='logs', page_title='System Logs')


@app.route('/projects')
@requires_auth
def projects():
    return render_template('pages/projects.html', current_page='projects', page_title='Project Management')


@app.route('/organization')
@requires_auth
def organization():
    return render_template('pages/organization.html', current_page='organization', page_title='Organization OS')


@app.route('/production-readiness')
@requires_auth
def production_readiness():
    return render_template('pages/production_readiness.html', current_page='production', page_title='Production Readiness')


@app.route('/infrastructure')
@requires_auth
def infrastructure():
    return render_template('pages/infrastructure.html', current_page='infrastructure', page_title='Infrastructure')


@app.route('/settings')
@requires_auth
def settings():
    return render_template('pages/settings.html', current_page='settings', page_title='Settings')


@app.route('/ping')
def ping():
    return jsonify({'status': 'ok'})


@app.route('/health')
def health():
    return jsonify({
        'status': 'healthy',
        'service': 'sapphire-unified-frontend',
        'timestamp': datetime.utcnow().isoformat()
    })


# ---------------------------------------------------------------------------
# API ROUTES
# ---------------------------------------------------------------------------

@app.route('/api/status')
@requires_auth
def api_status():
    return jsonify(_collect_system_status())


@app.route('/api/health/summary')
@requires_auth
def api_health_summary():
    return jsonify(_platform_health_summary())


@app.route('/api/platform/status')
@requires_auth
def api_platform_status():
    return jsonify(_collect_system_status())


@app.route('/api/platform/metrics')
@requires_auth
def api_platform_metrics():
    return jsonify(_platform_metrics_payload())


@app.route('/api/platform/logs')
@requires_auth
def api_platform_logs():
    hours = request.args.get('hours', 24, type=int)
    limit = request.args.get('limit', 100, type=int)
    service = request.args.get('service', '')
    level = request.args.get('level', '')
    return jsonify(_fetch_logs(hours=hours, limit=limit, service=service, level=level))


@app.route('/api/platform/organization')
@requires_auth
def api_platform_organization():
    refresh = request.args.get('refresh', 'false').lower() == 'true'
    return jsonify(_platform_organization_payload(refresh=refresh))


@app.route('/api/platform/readiness')
@requires_auth
def api_platform_readiness():
    return jsonify(_build_readiness_payload(request.url_root))


@app.route('/api/platform/projects')
@requires_auth
def api_platform_projects():
    return jsonify(_fetch_projects_payload())


@app.route('/api/platform/windows-lab')
@requires_auth
def api_platform_windows_lab():
    return jsonify(_fetch_windows_lab_payload())


@app.route('/api/logs')
@requires_auth
def api_logs():
    hours = request.args.get('hours', 24, type=int)
    limit = request.args.get('limit', 100, type=int)
    service = request.args.get('service', '')
    level = request.args.get('level', '')
    return jsonify(_fetch_logs(hours=hours, limit=limit, service=service, level=level))


@app.route('/api/market/prices')
@requires_auth
def api_market_prices():
    data = _platform_metrics_payload().get('market', {})
    if 'error' in data:
        return jsonify(data), 502
    return jsonify(data)


@app.route('/api/projects')
@requires_auth
def api_projects():
    return api_platform_projects()


@app.route('/api/organization')
@requires_auth
def api_organization():
    return api_platform_organization()


@app.route('/api/production/readiness')
@requires_auth
def api_production_readiness():
    return api_platform_readiness()


@app.route('/api/trading/metrics')
@requires_auth
def api_trading_metrics():
    return jsonify(_platform_metrics_payload().get('trading', {}))


@app.route('/api/windows-lab')
@requires_auth
def api_windows_lab():
    return api_platform_windows_lab()


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
