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
THO_AGENT_URL = os.environ.get('THO_AGENT_URL', 'https://tho-agent-267358751314.us-central1.run.app')
SCOUT_SANDBOX_URL = os.environ.get('SCOUT_SANDBOX_URL', 'https://sapphire-scout-sandbox-267358751314.us-central1.run.app')

RARI1_IP = os.environ.get('RARI1_IP', '100.120.191.1')
RARI2_IP = os.environ.get('RARI2_IP', '100.87.225.89')
WINDOWS_IP = os.environ.get('WINDOWS_IP', '100.71.10.48')

RARI1_HEALTH_URL = os.environ.get('RARI1_HEALTH_URL', f'http://{RARI1_IP}:8000/output/latest_hourly.json')
RARI2_HEALTH_URL = os.environ.get('RARI2_HEALTH_URL', f'http://{RARI2_IP}:18888/status')
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
        'rari2_trading_api,rari2_lighter_api',
    ).split(',')
    if item.strip()
}

OPTIONAL_HEALTH_CATEGORIES = {
    item.strip() for item in os.environ.get(
        'OPTIONAL_HEALTH_CATEGORIES',
        'windows',
    ).split(',')
    if item.strip()
}

OPTIONAL_HEALTH_NAMES = {
    item.strip() for item in os.environ.get(
        'OPTIONAL_HEALTH_NAMES',
        'windows,windows_webhook,windows_tv_agent',
    ).split(',')
    if item.strip()
}

# Auth Configuration
AUTH_USERNAME = os.environ.get('AUTH_USERNAME', 'sapphire')
AUTH_PASSWORD = os.environ.get('AUTH_PASSWORD', 'alpha2024')
ENABLE_AUTH = os.environ.get('ENABLE_AUTH', 'false').lower() == 'true'
PUBLIC_READ_ONLY = os.environ.get('PUBLIC_READ_ONLY', 'true').lower() == 'true'
MAC_OPERATOR_APP_URL = os.environ.get('MAC_OPERATOR_APP_URL', 'sapphirebook://operator')
MAC_OPERATOR_APP_LABEL = os.environ.get('MAC_OPERATOR_APP_LABEL', 'Open macOS Operator App')

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


@app.context_processor
def inject_platform_context():
    return {
        'public_read_only': PUBLIC_READ_ONLY,
        'mac_operator_app_url': MAC_OPERATOR_APP_URL,
        'mac_operator_app_label': MAC_OPERATOR_APP_LABEL,
    }


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


def _get_json(
    url: str,
    *,
    timeout: float = 4.0,
    params: dict | None = None,
    retries: int = 2,
    retry_backoff_seconds: float = 0.35,
):
    """Fetch JSON payload from an endpoint with standardized error shape."""
    transient_statuses = {408, 425, 429, 500, 502, 503, 504}
    started = time.time()
    attempts = max(0, int(retries)) + 1
    last_error = None
    last_status = None

    for attempt in range(attempts):
        try:
            response = requests.get(url, timeout=timeout, params=params)
            last_status = response.status_code
            if response.status_code == 200:
                payload = response.json() if response.content else {}
                return {
                    'ok': True,
                    'status_code': 200,
                    'latency_ms': round((time.time() - started) * 1000, 2),
                    'error': None,
                    'data': payload if isinstance(payload, dict) else {},
                }

            last_error = f'http_{response.status_code}'
            if response.status_code in transient_statuses and attempt < (attempts - 1):
                time.sleep(retry_backoff_seconds * (attempt + 1))
                continue

            return {
                'ok': False,
                'status_code': response.status_code,
                'latency_ms': round((time.time() - started) * 1000, 2),
                'error': last_error,
                'data': {},
            }
        except requests.RequestException as exc:
            last_error = str(exc)
            if attempt < (attempts - 1):
                time.sleep(retry_backoff_seconds * (attempt + 1))
                continue
            return {
                'ok': False,
                'status_code': last_status,
                'latency_ms': round((time.time() - started) * 1000, 2),
                'error': last_error,
                'data': {},
            }

    return {
        'ok': False,
        'status_code': last_status,
        'latency_ms': round((time.time() - started) * 1000, 2),
        'error': last_error or 'unknown_error',
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


def _normalize_intel_item(raw: dict, fallback_source: str = 'alpha_engine') -> dict:
    item = dict(raw or {})
    title = str(item.get('title', '')).strip() or 'Untitled intelligence update'
    summary = str(item.get('summary', '')).strip()
    source = str(item.get('source', fallback_source)).strip() or fallback_source
    category = str(item.get('category', 'market')).strip().lower() or 'market'
    confidence = str(item.get('confidence', 'medium')).strip().lower() or 'medium'
    tags = item.get('tags', [])
    if not isinstance(tags, list):
        tags = []
    score = item.get('score', 0.0)
    try:
        score = float(score)
    except (TypeError, ValueError):
        score = 0.0

    normalized = {
        'id': str(item.get('id', '')).strip() or f"{source}:{hash(title)}",
        'source': source,
        'category': category,
        'title': title,
        'summary': summary,
        'url': str(item.get('url', '')).strip(),
        'published_at': _iso_or_default(item.get('published_at') or item.get('timestamp')),
        'tags': [str(tag).strip().lower() for tag in tags if str(tag).strip()],
        'confidence': confidence,
        'score': round(score, 3),
    }
    return normalized


def _fallback_intel_from_logs(limit: int = 80, category: str = '', query: str = '') -> dict:
    logs_payload = _fetch_logs(hours=24, limit=max(60, limit * 2))
    logs = logs_payload.get('logs', [])
    items = []
    for idx, row in enumerate(logs):
        message = str(row.get('message', '')).strip()
        if not message:
            continue
        level = str(row.get('level', 'INFO')).lower()
        service = str(row.get('service', 'platform')).lower()
        inferred_category = 'security' if 'security' in message.lower() else (
            'market' if ('signal' in message.lower() or 'trade' in message.lower()) else 'operations'
        )
        if category and inferred_category != category:
            continue
        if query:
            q = query.lower()
            if q not in message.lower() and q not in service:
                continue
        items.append(
            {
                'id': row.get('id', f'log-{idx}'),
                'source': f'log:{service}',
                'category': inferred_category,
                'title': message[:140] + ('…' if len(message) > 140 else ''),
                'summary': message,
                'url': '',
                'published_at': _iso_or_default(row.get('timestamp')),
                'tags': [level, service, 'firestore'],
                'confidence': 'low',
                'score': 0.44 if level == 'info' else 0.55,
            }
        )
        if len(items) >= limit:
            break

    return {
        'enabled': True,
        'running': True,
        'source': 'firestore_logs_fallback',
        'count': len(items),
        'items': items[:limit],
        'status': {
            'enabled': True,
            'running': True,
            'source': 'fallback',
            'note': 'Alpha intel feed unavailable; using platform logs fallback.',
        },
        'timestamp': datetime.utcnow().isoformat(),
    }


def _fetch_intel_feed_payload(limit: int = 80, category: str = '', query: str = '', refresh: bool = False):
    cache_key = f"intel_feed:{limit}:{category}:{query}:{int(bool(refresh))}"
    if not refresh and not query and not category:
        cached = get_cached(cache_key, duration=15)
        if cached:
            return cached

    alpha_url = _join_url(ALPHA_ENGINE_URL, '/intel/feed')
    params = {
        'limit': max(1, min(limit, 200)),
    }
    if category:
        params['category'] = category
    if query:
        params['query'] = query
    if refresh:
        params['refresh'] = 'true'

    def _extract_items(payload: dict) -> list[dict]:
        raw_items = payload.get('items', [])
        if not isinstance(raw_items, list):
            return []
        return [_normalize_intel_item(item) for item in raw_items if isinstance(item, dict)]

    response = _get_json(alpha_url, timeout=8.0, params=params)
    if response.get('ok'):
        data = response.get('data', {})
        items = _extract_items(data)
        if not items:
            # Alpha cold-start windows can return empty feed before first refresh cycle.
            # Do one forced refresh attempt before degrading to Firestore logs fallback.
            if not refresh:
                refresh_params = dict(params)
                refresh_params['refresh'] = 'true'
                retry_response = _get_json(alpha_url, timeout=12.0, params=refresh_params)
                if retry_response.get('ok'):
                    retry_data = retry_response.get('data', {})
                    retry_items = _extract_items(retry_data)
                    if retry_items:
                        payload = {
                            'enabled': bool(retry_data.get('enabled', True)),
                            'running': bool(retry_data.get('running', True)),
                            'source': 'alpha_engine',
                            'count': len(retry_items),
                            'items': retry_items[: max(1, min(limit, 200))],
                            'status': retry_data.get('status', {}),
                            'timestamp': datetime.utcnow().isoformat(),
                        }
                        if not query and not category:
                            set_cache(cache_key, payload)
                        return payload

            fallback = _fallback_intel_from_logs(limit=limit, category=category, query=query)
            fallback['warning'] = 'alpha_engine_empty'
            fallback['status'] = {
                **(data.get('status', {}) if isinstance(data.get('status'), dict) else {}),
                'fallback_reason': 'alpha_engine_returned_zero_items',
            }
            if not refresh and not query and not category:
                set_cache(cache_key, fallback)
            return fallback
        payload = {
            'enabled': bool(data.get('enabled', True)),
            'running': bool(data.get('running', True)),
            'source': 'alpha_engine',
            'count': len(items),
            'items': items[: max(1, min(limit, 200))],
            'status': data.get('status', {}),
            'timestamp': datetime.utcnow().isoformat(),
        }
        if not refresh and not query and not category:
            set_cache(cache_key, payload)
        return payload

    payload = _fallback_intel_from_logs(limit=limit, category=category, query=query)
    payload['warning'] = response.get('error') or f"http_{response.get('status_code')}"
    if not refresh and not query and not category:
        set_cache(cache_key, payload)
    return payload


def _platform_health_summary(status_data=None):
    status_data = status_data or _collect_system_status()
    summary = status_data.get('summary', {})
    by_category = status_data.get('by_category', {})

    rows = []
    for category, items in by_category.items():
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            rows.append({
                'category': str(category),
                'name': str(item.get('name', 'unknown')),
                'healthy': bool(item.get('healthy', False)),
            })

    def _is_optional(row):
        if row['category'] in OPTIONAL_HEALTH_CATEGORIES:
            return True
        return row['name'] in OPTIONAL_HEALTH_NAMES

    core_rows = [r for r in rows if not _is_optional(r)]
    optional_rows = [r for r in rows if _is_optional(r)]
    core_healthy_count = sum(1 for r in core_rows if r['healthy'])
    core_unhealthy_count = len(core_rows) - core_healthy_count
    optional_degraded_count = sum(1 for r in optional_rows if not r['healthy'])

    return {
        # `healthy` intentionally tracks core production health, not optional edge devices.
        'healthy': core_unhealthy_count == 0,
        'overall_healthy': (summary.get('service_unhealthy', 0) == 0 and summary.get('node_unhealthy', 0) == 0),
        'healthy_count': core_healthy_count,
        'unhealthy_count': core_unhealthy_count,
        'optional_total': len(optional_rows),
        'optional_degraded_count': optional_degraded_count,
        'node_healthy_count': summary.get('node_healthy', 0),
        'node_unhealthy_count': summary.get('node_unhealthy', 0),
        'timestamp': status_data.get('timestamp'),
        'by_category': by_category,
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


def _platform_home_snapshot_payload():
    """Aggregate homepage dependencies into one resilient payload."""
    cached = get_cached('platform_home_snapshot', duration=12)
    if cached:
        return cached
    host_root = request.url_root

    def _run(name: str, fn):
        started = time.time()
        try:
            return {
                'name': name,
                'ok': True,
                'latency_ms': round((time.time() - started) * 1000, 2),
                'data': fn(),
            }
        except Exception as exc:
            return {
                'name': name,
                'ok': False,
                'latency_ms': round((time.time() - started) * 1000, 2),
                'error': str(exc)[:240],
                'data': None,
            }

    workers = {
        'status': lambda: _collect_system_status(),
        'metrics': lambda: _platform_metrics_payload(),
        'projects': lambda: _fetch_projects_payload(),
        'organization': lambda: _platform_organization_payload(),
        'readiness': lambda: _build_readiness_payload(host_root),
        'logs': lambda: _fetch_logs(limit=8, hours=24),
    }

    results = {}
    with ThreadPoolExecutor(max_workers=len(workers)) as pool:
        futures = {pool.submit(_run, name, fn): name for name, fn in workers.items()}
        for future, name in ((f, futures[f]) for f in futures):
            results[name] = future.result()

    payload = {
        'timestamp': datetime.utcnow().isoformat(),
        'overall_ok': all(result.get('ok', False) for result in results.values()),
        'results': results,
        'status': results.get('status', {}).get('data') or _collect_system_status(),
        'metrics': results.get('metrics', {}).get('data') or _platform_metrics_payload(),
        'projects': results.get('projects', {}).get('data') or {'projects': [], 'count': 0},
        'organization': results.get('organization', {}).get('data') or {'summary': {}},
        'readiness': results.get('readiness', {}).get('data') or {'overall_ok': False, 'gates': {}},
        'logs': results.get('logs', {}).get('data') or {'logs': [], 'count': 0},
    }

    set_cache('platform_home_snapshot', payload)
    return payload


def _build_experiment_backlog(
    control: dict | None,
    routing: dict | None,
    readiness: dict | None,
    intel_payload: dict | None,
) -> list[dict]:
    """Generate a safe, read-only experimentation backlog from live telemetry."""
    control = control or {}
    routing = routing or {}
    readiness = readiness or {}
    intel_payload = intel_payload or {}
    experiments: list[dict] = []

    def add_experiment(
        *,
        title: str,
        lane: str,
        priority: str,
        hypothesis: str,
        success_metric: str,
        safety: str,
        next_step: str,
        source: str = 'derived',
    ) -> None:
        experiments.append(
            {
                'id': f"exp-{len(experiments) + 1:02d}",
                'title': title,
                'lane': lane,
                'priority': priority,
                'hypothesis': hypothesis,
                'success_metric': success_metric,
                'safety': safety,
                'next_step': next_step,
                'source': source,
            }
        )

    if not bool(control.get('full_autonomy_enabled', False)):
        add_experiment(
            title='Autonomy loop activation drill',
            lane='operations',
            priority='high',
            hypothesis='Enabling full autonomy with current guardrails increases throughput without raising incident count.',
            success_metric='Autonomy dispatches > 0 and no new readiness blockers across 24h.',
            safety='Keep DEX stage in paper and owner approval ON during first run.',
            next_step='Toggle only in staging or with supervised maintenance window.',
            source='control_status',
        )

    if str(control.get('dex_execution_stage', 'paper')).lower() == 'paper':
        add_experiment(
            title='Paper-to-live promotion gate calibration',
            lane='trading',
            priority='high',
            hypothesis='Promotion criteria based on paper expectancy and drawdown reduce live-stage regression risk.',
            success_metric='7-day paper run with positive expectancy and zero kill-switch activations.',
            safety='No live dispatch changes from web; promotion remains operator-only.',
            next_step='Define promotion threshold packet in macOS operator client workflow.',
            source='control_status',
        )

    failure_pressure = int(control.get('failure_pressure', 0) or 0)
    if failure_pressure > 0 or not bool(readiness.get('overall_ok', False)):
        add_experiment(
            title='Failure-pressure reduction cycle',
            lane='reliability',
            priority='high',
            hypothesis='Targeted remediation on unstable rails lowers failure pressure and increases readiness stability.',
            success_metric='Failure pressure returns to 0 and readiness gate stays green for 24h.',
            safety='Use no-mutation diagnostics first, then apply reversible fixes.',
            next_step='Triaging blockers from readiness and monitor snapshots.',
            source='readiness',
        )

    pending = int(control.get('pending_autonomy_decisions', 0) or 0)
    if pending > 0:
        add_experiment(
            title='Decision queue latency reduction',
            lane='governance',
            priority='medium',
            hypothesis='Reducing pending autonomy decisions shortens execution feedback loops.',
            success_metric='Pending autonomy decisions reduced to <= 1 within one cycle.',
            safety='Keep approval policy unchanged; optimize workflow not permissions.',
            next_step='Process pending sessions with clear approve/reject rationale.',
            source='control_status',
        )

    memory_stats = control.get('memory_stats', {}) if isinstance(control.get('memory_stats'), dict) else {}
    total_episodes = int(memory_stats.get('total_episodes', 0) or 0)
    if bool(control.get('memory_enabled', False)) and total_episodes < 50:
        add_experiment(
            title='Episodic memory density uplift',
            lane='learning',
            priority='medium',
            hypothesis='Higher episode density improves regime awareness and post-incident learning quality.',
            success_metric='Total episodes > 100 with regime distribution tracked weekly.',
            safety='Data collection only; no autonomous mutation of live execution logic.',
            next_step='Increase instrumentation for trade context capture in non-critical paths.',
            source='memory',
        )

    cognition_metrics = control.get('cognition_metrics', {}) if isinstance(control.get('cognition_metrics'), dict) else {}
    override_rate = float(cognition_metrics.get('override_rate', 0) or 0)
    if bool(control.get('cognition_enabled', False)) and override_rate > 35:
        add_experiment(
            title='Dual-speed cognition tuning',
            lane='learning',
            priority='medium',
            hypothesis='Reducing unnecessary System2 overrides improves latency without harming decision quality.',
            success_metric='Override rate reduced by 20% while incident rate stays flat.',
            safety='Apply threshold tuning in dry-run first.',
            next_step='Adjust escalation thresholds and compare before/after telemetry.',
            source='cognition',
        )

    confidence = float(routing.get('confidence', 0.0) or 0.0)
    if confidence < 0.75:
        add_experiment(
            title='Routing confidence uplift',
            lane='trading',
            priority='medium',
            hypothesis='Venue health and allocation rebalance improves routing confidence under stress.',
            success_metric='Routing confidence sustained >= 0.80 for 24h.',
            safety='No live allocation changes from web; proposal only.',
            next_step='Generate allocation proposal from platform/routing metrics.',
            source='routing',
        )

    intel_items = intel_payload.get('items', []) if isinstance(intel_payload.get('items'), list) else []
    for idx, item in enumerate(intel_items[:2]):
        if not isinstance(item, dict):
            continue
        title = str(item.get('title', '')).strip() or 'Intel signal'
        source = str(item.get('source', 'intel_feed')).strip() or 'intel_feed'
        category = str(item.get('category', 'research')).strip().lower() or 'research'
        url = str(item.get('url', '')).strip()
        next_step = 'Run sandbox validation and summarize expected impact.'
        if url:
            next_step = f"Validate source signal and run sandbox-only experiment for: {url}"
        add_experiment(
            title=f"Intel-driven experiment: {title[:80]}",
            lane=category,
            priority='low' if idx > 0 else 'medium',
            hypothesis='External signal may improve strategy quality or operational safety when validated.',
            success_metric='Experiment outcome documented with adopt/reject decision.',
            safety='Sandbox-only execution; no production mutation without operator approval.',
            next_step=next_step,
            source=source,
        )

    if not experiments:
        add_experiment(
            title='Steady-state resilience exercise',
            lane='operations',
            priority='low',
            hypothesis='Regular disaster recovery drills preserve high readiness in steady-state periods.',
            success_metric='Monthly failover drill completed with documented MTTR.',
            safety='Run in controlled drill mode only.',
            next_step='Schedule next resilience drill and capture postmortem.',
            source='baseline',
        )

    priority_order = {'high': 0, 'medium': 1, 'low': 2}
    experiments.sort(key=lambda item: priority_order.get(str(item.get('priority', 'low')), 9))
    return experiments


def _platform_autonomy_payload():
    """Aggregate autonomy + learning + experimentation telemetry."""
    cached = get_cached('platform_autonomy', duration=12)
    if cached:
        return cached

    control_url = _join_url(ALPHA_ENGINE_URL, '/control/status')
    routing_url = _join_url(ALPHA_ENGINE_URL, '/routing')
    performance_url = _join_url(ALPHA_ENGINE_URL, '/performance/stats')
    scout_url = _join_url(ALPHA_ENGINE_URL, '/forum/scout/status')
    host_root = request.url_root

    workers = {
        # Keep autonomy surface responsive: fail fast and degrade gracefully.
        'control': lambda: _get_json(control_url, timeout=4.0, retries=0),
        'routing': lambda: _get_json(routing_url, timeout=4.0, retries=0),
        'performance': lambda: _get_json(performance_url, timeout=4.0, retries=0),
        'scout': lambda: _get_json(scout_url, timeout=4.0, retries=0),
        'readiness': lambda: {'ok': True, 'status_code': 200, 'latency_ms': 0.0, 'error': None, 'data': _build_readiness_payload(host_root)},
        'intel': lambda: {'ok': True, 'status_code': 200, 'latency_ms': 0.0, 'error': None, 'data': _fetch_intel_feed_payload(limit=16)},
    }

    results = {}
    with ThreadPoolExecutor(max_workers=len(workers)) as pool:
        futures = {pool.submit(fn): name for name, fn in workers.items()}
        for future, name in ((f, futures[f]) for f in futures):
            try:
                results[name] = future.result()
            except Exception as exc:
                results[name] = {
                    'ok': False,
                    'status_code': None,
                    'latency_ms': None,
                    'error': str(exc)[:220],
                    'data': {},
                }

    control = results.get('control', {}).get('data', {}) or {}
    routing = results.get('routing', {}).get('data', {}) or {}
    performance = results.get('performance', {}).get('data', {}) or {}
    scout = results.get('scout', {}).get('data', {}) or {}
    readiness = results.get('readiness', {}).get('data', {}) or {}
    intel = results.get('intel', {}).get('data', {}) or {}
    monitor = _get_monitor_snapshot()

    autonomy = {
        'kill_switch_active': bool(control.get('kill_switch_active', False)),
        'full_autonomy_enabled': bool(control.get('full_autonomy_enabled', False)),
        'owner_approval_required': bool(control.get('owner_approval_required', False)),
        'dex_execution_stage': str(control.get('dex_execution_stage', 'paper')),
        'dex_live_dispatch_enabled': bool(control.get('dex_live_dispatch_enabled', False)),
        'tradingview_execution_enabled': bool(control.get('tradingview_execution_enabled', False)),
        'autonomy_dispatch_count': int(control.get('autonomy_dispatch_count', 0) or 0),
        'pending_autonomy_decisions': int(control.get('pending_autonomy_decisions', 0) or 0),
        'failure_pressure': int(control.get('failure_pressure', 0) or 0),
    }

    learning = {
        'memory_enabled': bool(control.get('memory_enabled', False)),
        'memory_stats': control.get('memory_stats', {}) if isinstance(control.get('memory_stats'), dict) else {},
        'cognition_enabled': bool(control.get('cognition_enabled', False)),
        'cognition_metrics': control.get('cognition_metrics', {}) if isinstance(control.get('cognition_metrics'), dict) else {},
        'alpha_scanner': control.get('alpha_scanner', {}) if isinstance(control.get('alpha_scanner'), dict) else {},
        'grid_trader': control.get('grid_trader', {}) if isinstance(control.get('grid_trader'), dict) else {},
    }

    experiments = _build_experiment_backlog(control, routing, readiness, intel)
    risk = {
        'readiness_ok': bool(readiness.get('overall_ok', False)),
        'readiness_blockers': readiness.get('blockers', []) if isinstance(readiness.get('blockers'), list) else [],
        'dispatcher_hardening': control.get('dispatcher_hardening', {}),
        'routing_confidence': float(routing.get('confidence', 0.0) or 0.0),
    }

    sources = {}
    for name, result in results.items():
        sources[name] = {
            'ok': bool(result.get('ok', False)),
            'status_code': result.get('status_code'),
            'latency_ms': result.get('latency_ms'),
            'error': result.get('error'),
        }
    sources['monitor'] = {
        'ok': bool(monitor.get('available', False)),
        'status_code': 200 if monitor.get('available', False) else None,
        'latency_ms': None,
        'error': monitor.get('error'),
    }

    payload = {
        'timestamp': datetime.utcnow().isoformat(),
        'overall_ok': bool(readiness.get('overall_ok', False)),
        'autonomy': autonomy,
        'learning': learning,
        'risk': risk,
        'performance': performance.get('metrics', {}) if isinstance(performance.get('metrics'), dict) else {},
        'scout': scout,
        'experiments': experiments,
        'sources': sources,
        'readiness': {
            'overall_ok': bool(readiness.get('overall_ok', False)),
            'gates': readiness.get('gates', {}),
        },
    }

    set_cache('platform_autonomy', payload)
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
    return render_template('pages/overview.html', current_page='overview', page_title='Sapphire Operations')


@app.route('/trading')
@requires_auth
def trading():
    return render_template('pages/trading.html', current_page='trading', page_title='Market Intelligence')


@app.route('/feed')
@requires_auth
def feed():
    return render_template('pages/feed.html', current_page='feed', page_title='Intelligence Feed')


@app.route('/autonomy')
@requires_auth
def autonomy():
    return render_template('pages/autonomy.html', current_page='autonomy', page_title='Autonomy Lab')


@app.route('/command-deck')
@requires_auth
def command_deck():
    return render_template('pages/command_deck.html', current_page='command-deck', page_title='Command Deck')


@app.route('/system-health')
@requires_auth
def system_health():
    return render_template('pages/health.html', current_page='health', page_title='Platform Status')


@app.route('/logs')
@requires_auth
def logs():
    return render_template('pages/logs.html', current_page='logs', page_title='Activity Highlights')


@app.route('/projects')
@requires_auth
def projects():
    return render_template('pages/projects.html', current_page='projects', page_title='Client Programs')


@app.route('/organization')
@requires_auth
def organization():
    return render_template('pages/organization.html', current_page='organization', page_title='Organization')


@app.route('/production-readiness')
@requires_auth
def production_readiness():
    return render_template('pages/production_readiness.html', current_page='production', page_title='Operational Readiness')


@app.route('/infrastructure')
@requires_auth
def infrastructure():
    return render_template('pages/infrastructure.html', current_page='infrastructure', page_title='Technology Infrastructure')


@app.route('/settings')
@requires_auth
def settings():
    return render_template('pages/settings.html', current_page='settings', page_title='Security Policy')


@app.route('/sapphire-book')
@requires_auth
def sapphire_book():
    return render_template('pages/sapphire_book.html', current_page='sapphire-book', page_title='Sapphire Book')


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


@app.route('/api/platform/autonomy')
@requires_auth
def api_platform_autonomy():
    return jsonify(_platform_autonomy_payload())


@app.route('/api/platform/home-snapshot')
@requires_auth
def api_platform_home_snapshot():
    return jsonify(_platform_home_snapshot_payload())


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


@app.route('/api/platform/intel-feed')
@requires_auth
def api_platform_intel_feed():
    limit = request.args.get('limit', 80, type=int)
    category = request.args.get('category', '', type=str).strip().lower()
    query = request.args.get('query', '', type=str).strip()
    refresh = request.args.get('refresh', 'false', type=str).lower() == 'true'
    return jsonify(_fetch_intel_feed_payload(limit=limit, category=category, query=query, refresh=refresh))


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


@app.route('/api/intel/feed')
@requires_auth
def api_intel_feed():
    return api_platform_intel_feed()


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
