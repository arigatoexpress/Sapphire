#!/usr/bin/env python3
"""
Sapphire Unified Frontend
Multi-page dashboard with shared navigation and live status APIs.
"""

from datetime import datetime, timedelta, timezone
from functools import wraps
from concurrent.futures import ThreadPoolExecutor
import hashlib
import os
import time
from urllib.parse import urljoin

import requests
from firebase_admin import credentials, firestore, get_app, initialize_app
from flask import Flask, render_template, jsonify, request, Response, make_response, redirect

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
PLATFORM_CONTRACT_VERSION = os.environ.get('PLATFORM_CONTRACT_VERSION', 'v1')
LEGACY_ALIAS_SUNSET = os.environ.get('LEGACY_ALIAS_SUNSET', 'Sat, 01 Aug 2026 00:00:00 GMT')
TRADING_METRICS_COLLECTION = os.environ.get('TRADING_METRICS_COLLECTION', 'trading_metrics')
TRADE_EXECUTIONS_COLLECTION = os.environ.get('TRADE_EXECUTIONS_COLLECTION', 'trade_executions')
SYSTEM_LOGS_COLLECTION = os.environ.get('SYSTEM_LOGS_COLLECTION', 'system_logs')
EDGE_CAPABILITIES_COLLECTION = os.environ.get('EDGE_CAPABILITIES_COLLECTION', 'edge_capabilities')
LEARNING_OUTCOMES_COLLECTION = os.environ.get('LEARNING_OUTCOMES_COLLECTION', 'learning_outcomes')
SUPERSWARM_ROLLUPS_COLLECTION = os.environ.get('SUPERSWARM_ROLLUPS_COLLECTION', 'superswarm_rollups')
BUSINESS_BRIEFS_COLLECTION = os.environ.get('BUSINESS_BRIEFS_COLLECTION', 'platform_business_briefs')

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
_raw_password = os.environ.get('AUTH_PASSWORD', '').strip()
ENABLE_AUTH = os.environ.get('ENABLE_AUTH', 'false').lower() == 'true'
_INSECURE_DEFAULTS = {'alpha2024', 'password', 'sapphire', 'admin', ''}

if ENABLE_AUTH and _raw_password in _INSECURE_DEFAULTS:
    # Auth is on but the password is insecure/missing — refuse to start.
    import sys as _sys
    print(
        "FATAL: ENABLE_AUTH=true but AUTH_PASSWORD is unset or a known-insecure default "
        f"({_raw_password!r}). Set AUTH_PASSWORD to a strong password before enabling auth.",
        file=_sys.stderr,
    )
    _sys.exit(1)
elif not ENABLE_AUTH:
    # Auth is disabled — warn loudly so operators know the dashboard is open.
    import logging as _log
    _log.getLogger(__name__).warning(
        "⚠️  Dashboard auth is DISABLED (ENABLE_AUTH=false). "
        "Set ENABLE_AUTH=true and AUTH_PASSWORD to secure the dashboard."
    )

AUTH_PASSWORD = _raw_password
PUBLIC_READ_ONLY = os.environ.get('PUBLIC_READ_ONLY', 'true').lower() == 'true'
ENABLE_INTERNAL_JOBS = os.environ.get('ENABLE_INTERNAL_JOBS', 'false').lower() == 'true'
MAC_OPERATOR_APP_URL = os.environ.get('MAC_OPERATOR_APP_URL', 'sapphirebook://operator')
MAC_OPERATOR_APP_LABEL = os.environ.get('MAC_OPERATOR_APP_LABEL', 'Open macOS Operator App')
CONTROL_API_TOKEN = os.environ.get('SAPPHIRE_CONTROL_API_TOKEN', '')

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

PLATFORM_CONTRACTS = [
    {
        'name': 'status',
        'path': '/api/platform/status',
        'method': 'GET',
        'auth': 'basic_or_public',
        'category': 'core',
        'description': 'Cross-environment service and node status snapshot.',
    },
    {
        'name': 'metrics',
        'path': '/api/platform/metrics',
        'method': 'GET',
        'auth': 'basic_or_public',
        'category': 'core',
        'description': 'Aggregated market, trading, and operations metrics.',
    },
    {
        'name': 'autonomy',
        'path': '/api/platform/autonomy',
        'method': 'GET',
        'auth': 'basic_or_public',
        'category': 'autonomy',
        'description': 'Autonomy loop controls, guardrails, and backlog telemetry.',
    },
    {
        'name': 'home_snapshot',
        'path': '/api/platform/home-snapshot',
        'method': 'GET',
        'auth': 'basic_or_public',
        'category': 'core',
        'description': 'Single-call payload for homepage hydration.',
    },
    {
        'name': 'business_brief',
        'path': '/api/platform/business-brief',
        'method': 'GET',
        'auth': 'basic_or_public',
        'category': 'core',
        'description': 'Narrative business-state snapshot for public/client surfaces.',
    },
    {
        'name': 'logs',
        'path': '/api/platform/logs',
        'method': 'GET',
        'auth': 'basic_or_public',
        'category': 'telemetry',
        'description': 'Operational logs feed with filter support.',
    },
    {
        'name': 'trades',
        'path': '/api/platform/trades',
        'method': 'GET',
        'auth': 'basic_or_public',
        'category': 'telemetry',
        'description': 'Verified trade execution feed (simulation excluded by default).',
    },
    {
        'name': 'organization',
        'path': '/api/platform/organization',
        'method': 'GET',
        'auth': 'basic_or_public',
        'category': 'organization',
        'description': 'Organization model, PM hub integration, and structure analytics.',
    },
    {
        'name': 'readiness',
        'path': '/api/platform/readiness',
        'method': 'GET',
        'auth': 'basic_or_public',
        'category': 'core',
        'description': 'Readiness gates and blocker list.',
    },
    {
        'name': 'projects',
        'path': '/api/platform/projects',
        'method': 'GET',
        'auth': 'basic_or_public',
        'category': 'organization',
        'description': 'Project portfolio and delivery telemetry.',
    },
    {
        'name': 'intel_feed',
        'path': '/api/platform/intel-feed',
        'method': 'GET',
        'auth': 'basic_or_public',
        'category': 'research',
        'description': 'Market/research intelligence feed (alpha engine + safe fallback).',
    },
    {
        'name': 'superswarm',
        'path': '/api/platform/superswarm',
        'method': 'GET',
        'auth': 'basic_or_public',
        'category': 'autonomy',
        'description': 'Self-improvement analytics, loop state, and efficacy rollups.',
    },
    {
        'name': 'windows_lab',
        'path': '/api/platform/windows-lab',
        'method': 'GET',
        'auth': 'basic_or_public',
        'category': 'infrastructure',
        'description': 'Windows edge AI/model bench capability snapshot.',
    },
    {
        'name': 'contracts',
        'path': '/api/platform/contracts',
        'method': 'GET',
        'auth': 'basic_or_public',
        'category': 'core',
        'description': 'Machine-readable endpoint manifest for clients and checks.',
    },
    {
        'name': 'control_plane',
        'path': '/api/platform/control-plane',
        'method': 'GET',
        'auth': 'operator_token_or_basic',
        'category': 'operations',
        'description': 'Desired/applied control-plane state, lane health, and execution policy summary.',
    },
]


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


def _extract_operator_token() -> str:
    token = (
        request.headers.get('X-Sapphire-Token', '').strip()
        or request.headers.get('x-sapphire-token', '').strip()
        or request.headers.get('X-Sapphire-Control-Token', '').strip()
        or request.headers.get('x-sapphire-control-token', '').strip()
    )
    if token:
        return token
    auth_header = request.headers.get('Authorization', '').strip()
    if auth_header.lower().startswith('bearer '):
        return auth_header[7:].strip()
    return ''


def _operator_denied(status_code: int):
    if (request.path or '').startswith('/api/'):
        if status_code == 404:
            return jsonify({'error': 'not_found'}), 404
        return jsonify({'error': 'unauthorized'}), 403
    if status_code == 404:
        return Response('Not Found', 404)
    return Response('Forbidden', 403)


def requires_operator_access(f):
    """Protect control-plane/operator routes even when public dashboard mode is enabled."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if ENABLE_AUTH:
            auth = request.authorization
            if not auth or not check_auth(auth.username, auth.password):
                return authenticate()
            return f(*args, **kwargs)

        if not CONTROL_API_TOKEN:
            return _operator_denied(404)
        token = _extract_operator_token()
        if token != CONTROL_API_TOKEN:
            return _operator_denied(403)
        return f(*args, **kwargs)

    return decorated


def requires_control_token(f):
    """Decorator for internal scheduler/webhook jobs that mutate analytics state."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not ENABLE_INTERNAL_JOBS:
            return jsonify({'error': 'not_found'}), 404
        if not CONTROL_API_TOKEN:
            return jsonify({'error': 'control_token_not_configured'}), 503

        token = (
            request.headers.get('X-Sapphire-Token', '').strip()
            or request.headers.get('x-sapphire-token', '').strip()
        )
        if not token:
            auth_header = request.headers.get('Authorization', '').strip()
            if auth_header.lower().startswith('bearer '):
                token = auth_header[7:].strip()

        if token != CONTROL_API_TOKEN:
            return jsonify({'error': 'unauthorized'}), 403
        return f(*args, **kwargs)
    return decorated


def _deprecated_alias_response(payload, canonical_path: str):
    response = make_response(payload)
    canonical_url = canonical_path
    if canonical_path.startswith('/'):
        canonical_url = f"{(request.url_root or '').rstrip('/')}{canonical_path}"

    response.headers['Deprecation'] = 'true'
    response.headers['Sunset'] = LEGACY_ALIAS_SUNSET
    response.headers['Link'] = f'<{canonical_url}>; rel=\"successor-version\"'
    response.headers['X-Sapphire-API-Tier'] = 'legacy-alias'
    response.headers['X-Sapphire-Contract-Version'] = PLATFORM_CONTRACT_VERSION
    return response


@app.after_request
def add_api_response_headers(response):
    path = request.path or ''
    if path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store, max-age=0'
        response.headers['Pragma'] = 'no-cache'
    if path.startswith('/api/platform/'):
        response.headers['X-Sapphire-API-Tier'] = 'canonical'
        response.headers['X-Sapphire-Contract-Version'] = PLATFORM_CONTRACT_VERSION
    return response


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


def _is_truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {'1', 'true', 'yes', 'y', 'on'}
    return False


def _is_simulated_trade_payload(payload: dict | None) -> bool:
    row = payload if isinstance(payload, dict) else {}
    metadata = row.get('metadata') if isinstance(row.get('metadata'), dict) else {}

    marker_keys = (
        'dry_run',
        'paper_trade',
        'paper',
        'test_event',
        'is_test',
        'simulated',
        'sandbox',
        'backtest',
    )
    for key in marker_keys:
        if _is_truthy(row.get(key)) or _is_truthy(metadata.get(key)):
            return True

    trade_id = str(row.get('trade_id', '')).lower()
    signal_id = str(row.get('signal_id', '')).lower()
    message = str(row.get('message', '')).lower()
    source = str(metadata.get('source', '')).lower()
    haystack = ' '.join([trade_id, signal_id, message, source])
    simulation_tokens = ('perf-check', 'perf-', 'test', 'mock', 'sandbox', 'paper', 'dry-run', 'dry_run')
    return any(token in haystack for token in simulation_tokens)


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

    def _tracked_symbols() -> list[str]:
        raw = os.environ.get(
            'SAPPHIRE_TRACKED_MARKET_SYMBOLS',
            'BTC,ETH,SOL,HYPE,DOGE,AVAX',
        )
        seen = set()
        symbols = []
        for token in raw.split(','):
            sym = token.strip().upper()
            if not sym or sym in seen:
                continue
            seen.add(sym)
            symbols.append(sym)
        return symbols or ['BTC', 'ETH', 'SOL']

    coingecko_ids = {
        'BTC': 'bitcoin',
        'ETH': 'ethereum',
        'SOL': 'solana',
        'HYPE': 'hyperliquid',
        'DOGE': 'dogecoin',
        'AVAX': 'avalanche-2',
        'ZEC': 'zcash',
        'XRP': 'ripple',
        'ADA': 'cardano',
        'BNB': 'binancecoin',
        'LINK': 'chainlink',
        'LTC': 'litecoin',
        'DOT': 'polkadot',
        'UNI': 'uniswap',
        'ATOM': 'cosmos',
        'MATIC': 'matic-network',
        'ARB': 'arbitrum',
        'OP': 'optimism',
        'INJ': 'injective-protocol',
        'SUI': 'sui',
        'NEAR': 'near',
        'RNDR': 'render-token',
        'WIF': 'dogwifcoin',
        'BONK': 'bonk',
        'JUP': 'jupiter-exchange-solana',
        'PYTH': 'pyth-network',
    }
    coinbase_pairs = {
        'BTC': 'BTC-USD',
        'ETH': 'ETH-USD',
        'SOL': 'SOL-USD',
        'DOGE': 'DOGE-USD',
        'AVAX': 'AVAX-USD',
        'LTC': 'LTC-USD',
        'LINK': 'LINK-USD',
        'ADA': 'ADA-USD',
        'DOT': 'DOT-USD',
    }
    tracked_symbols = _tracked_symbols()
    result = {sym: {'price': 0, 'change_24h': 0} for sym in tracked_symbols}

    # Primary source: CoinGecko (supports 24h % change across many assets)
    try:
        requested = {
            sym: coingecko_ids[sym]
            for sym in tracked_symbols
            if sym in coingecko_ids
        }
        resp = requests.get(
            'https://api.coingecko.com/api/v3/simple/price',
            params={
                'ids': ','.join(requested.values()),
                'vs_currencies': 'usd',
                'include_24hr_change': 'true',
            },
            headers={'Accept': 'application/json', 'User-Agent': 'sapphire-unified-frontend/1.0'},
            timeout=8,
        )
        resp.raise_for_status()
        data = resp.json()

        for sym, cg_id in requested.items():
            quote = data.get(cg_id, {}) or {}
            result[sym] = {
                'price': quote.get('usd', 0) or 0,
                'change_24h': quote.get('usd_24h_change', 0) or 0,
            }

        result['tracked_symbols'] = tracked_symbols
        result['source'] = 'coingecko'
        result['timestamp'] = datetime.utcnow().isoformat()
        set_cache('market_prices', result)
        return result
    except Exception:
        pass

    # Fallback source: Coinbase spot prices (price-only for supported majors)
    try:
        out = {sym: {'price': 0, 'change_24h': 0} for sym in tracked_symbols}
        for symbol in tracked_symbols:
            pair = coinbase_pairs.get(symbol)
            if not pair:
                continue
            resp = requests.get(f'https://api.coinbase.com/v2/prices/{pair}/spot', timeout=8)
            resp.raise_for_status()
            amount = float(resp.json().get('data', {}).get('amount', 0))
            out[symbol] = {'price': amount, 'change_24h': None}

        out['tracked_symbols'] = tracked_symbols
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


def _build_readiness_payload(host_root: str, include_business_brief_check: bool = True):
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
        run_contract_check('/api/platform/autonomy', _platform_autonomy_payload),
        run_contract_check('/api/platform/control-plane', _platform_control_plane_payload),
        run_contract_check('/api/platform/home-snapshot', _platform_home_snapshot_payload),
        run_contract_check('/api/platform/logs', lambda: _fetch_logs(limit=1)),
        run_contract_check('/api/platform/trades', lambda: _fetch_trade_executions(limit=1)),
        run_contract_check('/api/platform/superswarm', lambda: _platform_superswarm_payload(hours=24)),
        run_contract_check('/api/platform/organization', _platform_organization_payload),
        run_contract_check('/api/platform/readiness', lambda: True),
        run_contract_check('/api/platform/projects', _fetch_projects_payload),
        run_contract_check('/api/platform/intel-feed', lambda: _fetch_intel_feed_payload(limit=3)),
        run_contract_check('/api/platform/windows-lab', _fetch_windows_lab_payload),
        run_contract_check('/api/platform/contracts', _platform_contracts_payload),
    ]
    if include_business_brief_check:
        contract_checks.append(
            run_contract_check('/api/platform/business-brief', lambda: _platform_business_brief_payload(hours=24))
        )

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


def _fetch_verified_trading_metrics():
    if db is None:
        return None

    now_utc = datetime.now(timezone.utc)
    day_start = now_utc - timedelta(hours=24)
    week_start = now_utc - timedelta(days=7)
    month_start = now_utc - timedelta(days=30)

    try:
        docs = list(
            db.collection(TRADE_EXECUTIONS_COLLECTION)
            .where('timestamp', '>=', month_start.isoformat())
            .order_by('timestamp', direction=firestore.Query.DESCENDING)
            .limit(500)
            .stream()
        )
    except Exception:
        docs = list(
            db.collection(TRADE_EXECUTIONS_COLLECTION)
            .order_by('timestamp', direction=firestore.Query.DESCENDING)
            .limit(800)
            .stream()
        )

    daily_count = weekly_count = monthly_count = 0
    daily_pnl = weekly_pnl = monthly_pnl = 0.0
    wins = losses = 0

    for doc in docs:
        row = doc.to_dict() or {}
        if _is_simulated_trade_payload(row):
            continue

        ts = _coerce_datetime(row.get('timestamp')) or now_utc
        if ts < month_start:
            continue

        pnl = float(row.get('realized_pnl', 0.0) or 0.0)
        success = _is_truthy(row.get('success'))

        monthly_count += 1
        monthly_pnl += pnl
        if ts >= week_start:
            weekly_count += 1
            weekly_pnl += pnl
        if ts >= day_start:
            daily_count += 1
            daily_pnl += pnl

        if success and pnl >= 0:
            wins += 1
        else:
            losses += 1

    if monthly_count == 0:
        return None

    success_rate = round((wins / monthly_count) * 100.0, 2) if monthly_count > 0 else 0.0
    raw = {
        'timestamp': now_utc.isoformat(),
        'pnl': {
            'daily': round(daily_pnl, 6),
            'weekly': round(weekly_pnl, 6),
            'monthly': round(monthly_pnl, 6),
            'total': round(monthly_pnl, 6),
        },
        'trades': {
            'today': daily_count,
            'total': monthly_count,
            'success_rate': success_rate,
            'wins': wins,
            'losses': losses,
        },
        'positions': [],
        'verified_execution_source': 'trade_executions',
    }
    return _normalize_trading_metrics_payload(raw, source='firestore_verified_executions')


def _fetch_trading_metrics():
    if db is None:
        return _normalize_trading_metrics_payload(source='firestore_unavailable', error='firestore_unavailable')

    verified = _fetch_verified_trading_metrics()
    if verified is not None:
        return verified

    return _normalize_trading_metrics_payload(source='firestore_verified_empty', error='no_verified_executions')


def _derive_trading_metrics_from_logs(hours: int = 72, limit: int = 600):
    logs_payload = _fetch_logs(hours=max(24, hours), limit=max(120, limit))
    logs = logs_payload.get('logs', [])
    if not logs:
        return None

    now_utc = datetime.now(timezone.utc)
    day_start = now_utc - timedelta(hours=24)
    week_start = now_utc - timedelta(days=7)
    month_start = now_utc - timedelta(days=30)

    signal_received = 0
    signal_published = 0
    signal_failed = 0

    daily_count = 0
    weekly_count = 0
    monthly_count = 0
    daily_pnl = 0.0
    weekly_pnl = 0.0
    monthly_pnl = 0.0
    wins = 0
    losses = 0

    def _extract_pnl(row: dict) -> float:
        metadata = row.get('metadata', {}) if isinstance(row.get('metadata'), dict) else {}
        for key in ('realized_pnl', 'pnl', 'net_pnl', 'profit'):
            value = row.get(key)
            if value is None:
                value = metadata.get(key)
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
        return 0.0

    for row in logs:
        event_type = str(row.get('event_type', '')).strip().lower()
        message = str(row.get('message', '')).strip().lower()
        ts = _coerce_datetime(row.get('timestamp'))
        if ts is None:
            ts = now_utc

        if event_type == 'signal_received' or 'signal received' in message:
            signal_received += 1
        elif event_type == 'signal_published' or ('signal published' in message and 'trade' not in message):
            signal_published += 1
        elif event_type == 'signal_publish_failed' or 'signal publish failed' in message:
            signal_failed += 1

        trade_event = event_type in {'trade_executed', 'trade_execution_failed'} or 'trade executed' in message or 'trade failed' in message
        if not trade_event:
            continue

        pnl = _extract_pnl(row)
        if ts >= month_start:
            monthly_count += 1
            monthly_pnl += pnl
        if ts >= week_start:
            weekly_count += 1
            weekly_pnl += pnl
        if ts >= day_start:
            daily_count += 1
            daily_pnl += pnl

        if event_type == 'trade_execution_failed' or 'trade failed' in message:
            losses += 1
        elif pnl >= 0:
            wins += 1
        else:
            losses += 1

    has_trading_or_signals = any(
        [signal_received, signal_published, signal_failed, daily_count, weekly_count, monthly_count]
    )
    if not has_trading_or_signals:
        return None

    total_trades = monthly_count
    success_rate = round((wins / total_trades) * 100.0, 2) if total_trades > 0 else 0.0

    raw = {
        'timestamp': now_utc.isoformat(),
        'pnl': {
            'daily': round(daily_pnl, 6),
            'weekly': round(weekly_pnl, 6),
            'monthly': round(monthly_pnl, 6),
            'total': round(monthly_pnl, 6),
        },
        'trades': {
            'today': daily_count,
            'total': total_trades,
            'success_rate': success_rate,
            'wins': wins,
            'losses': losses,
        },
        'signals': {
            'received': signal_received,
            'published': signal_published,
            'publish_failed': signal_failed,
            'window_hours': max(24, hours),
        },
        'positions': [],
    }
    return _normalize_trading_metrics_payload(raw, source='firestore_logs_derived')


def _fetch_logs(
    hours: int = 24,
    limit: int = 100,
    service: str = '',
    level: str = '',
    include_simulated: bool = False,
):
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
        entry['event_type'] = str(entry.get('event_type', '')).lower()
        metadata = entry.get('metadata')
        entry['metadata'] = metadata if isinstance(metadata, dict) else {}
        entry['simulated'] = _is_simulated_trade_payload(entry)
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
        if not include_simulated:
            logs = [row for row in logs if not row.get('simulated', False)]
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
                if not include_simulated and log.get('simulated', False):
                    continue
                filtered.append(log)
            return {'logs': filtered[:limit], 'count': len(filtered), 'source': 'firestore_fallback', 'warning': str(exc)}
        except Exception as fallback_exc:
            return {'logs': [], 'count': 0, 'error': str(fallback_exc), 'source': 'firestore_error'}


def _normalize_trade_record(doc_id, raw):
    entry = dict(raw or {})
    metadata = entry.get('metadata')
    entry['metadata'] = metadata if isinstance(metadata, dict) else {}
    entry['id'] = doc_id
    entry['trade_id'] = str(entry.get('trade_id', doc_id))
    entry['signal_id'] = str(entry.get('signal_id', ''))
    entry['timestamp'] = _iso_or_default(entry.get('timestamp'))
    entry['platform'] = str(entry.get('platform', 'unknown')).lower()
    entry['symbol'] = str(entry.get('symbol', 'UNKNOWN')).upper()
    entry['side'] = str(entry.get('side', 'UNKNOWN')).upper()
    entry['success'] = bool(entry.get('success', False))
    entry['realized_pnl'] = float(entry.get('realized_pnl', 0.0) or 0.0)
    entry['filled_quantity'] = float(entry.get('filled_quantity', 0.0) or 0.0)
    entry['avg_price'] = float(entry.get('avg_price', 0.0) or 0.0)
    entry['simulated'] = _is_simulated_trade_payload(entry)
    trade_id = str(entry.get('trade_id', '')).strip().lower()
    entry['executed'] = bool(entry['success'] and entry['filled_quantity'] > 0 and trade_id not in {'', 'noop', 'none', 'null'})
    return entry


def _fetch_trade_executions(
    hours: int = 24,
    limit: int = 100,
    include_simulated: bool = False,
    include_failed: bool = False,
):
    if db is None:
        return {'trades': [], 'count': 0, 'error': 'firestore_unavailable', 'source': 'firestore'}

    since = datetime.now(timezone.utc) - timedelta(hours=max(1, hours))
    safe_limit = max(1, min(limit, 500))

    try:
        query = (
            db.collection(TRADE_EXECUTIONS_COLLECTION)
            .where('timestamp', '>=', since.isoformat())
            .order_by('timestamp', direction=firestore.Query.DESCENDING)
            .limit(safe_limit)
        )
        docs = list(query.stream())
    except Exception:
        docs = list(
            db.collection(TRADE_EXECUTIONS_COLLECTION)
            .order_by('timestamp', direction=firestore.Query.DESCENDING)
            .limit(max(200, min(safe_limit * 4, 800)))
            .stream()
        )

    rows = []
    for doc in docs:
        row = _normalize_trade_record(doc.id, doc.to_dict())
        ts = _coerce_datetime(row.get('timestamp'))
        if ts and ts < since:
            continue
        if not include_simulated and row.get('simulated', False):
            continue
        if not include_failed and not row.get('executed', False):
            continue
        rows.append(row)

    return {
        'trades': rows[:safe_limit],
        'count': len(rows[:safe_limit]),
        'source': 'firestore',
        'filters': {
            'hours': max(1, hours),
            'include_simulated': bool(include_simulated),
            'include_failed': bool(include_failed),
        },
    }


def _confidence_to_base_score(confidence: str) -> float:
    value = str(confidence or '').strip().lower()
    if value in {'high', 'strong'}:
        return 0.8
    if value in {'medium', 'moderate'}:
        return 0.62
    if value in {'low', 'weak'}:
        return 0.42
    return 0.5


def _score_to_verdict(score: float) -> str:
    if score >= 0.72:
        return 'win'
    if score <= 0.38:
        return 'loss'
    return 'pending'


def _sync_learning_outcomes(hours: int = 24) -> dict:
    if db is None:
        return {'written': 0, 'intel_written': 0, 'trade_written': 0, 'error': 'firestore_unavailable'}

    safe_hours = max(6, min(int(hours or 24), 168))
    now_utc = datetime.now(timezone.utc)
    cutoff = now_utc - timedelta(hours=safe_hours)
    written = 0
    intel_written = 0
    trade_written = 0

    def _upsert(doc_id: str, payload: dict):
        nonlocal written
        db.collection(LEARNING_OUTCOMES_COLLECTION).document(doc_id).set(payload, merge=True)
        written += 1

    # Intel-derived outcomes
    intel_payload = _fetch_intel_feed_payload(limit=120)
    intel_items = intel_payload.get('items', []) if isinstance(intel_payload.get('items'), list) else []
    for item in intel_items:
        if not isinstance(item, dict):
            continue
        ts = _coerce_datetime(item.get('published_at')) or now_utc
        if ts < cutoff:
            continue
        source = str(item.get('source', 'intel')).strip().lower() or 'intel'
        confidence = str(item.get('confidence', 'medium')).strip().lower()
        item_score = float(item.get('score', 0.5) or 0.5)
        score = max(0.0, min(1.0, round((_confidence_to_base_score(confidence) * 0.65) + (item_score * 0.35), 4)))
        verdict = _score_to_verdict(score)
        stable_key = f"{source}|{item.get('id','')}|{item.get('published_at','')}"
        doc_id = f"intel-{hashlib.sha1(stable_key.encode('utf-8')).hexdigest()[:24]}"
        _upsert(
            doc_id,
            {
                'id': doc_id,
                'timestamp': ts.isoformat(),
                'created_at': now_utc.isoformat(),
                'outcome_type': 'intel_insight',
                'experiment_id': str(item.get('id', '')).strip() or doc_id,
                'source': source,
                'category': str(item.get('category', 'operations')).strip().lower() or 'operations',
                'confidence': confidence,
                'quality_score': score,
                'verdict': verdict,
                'summary': str(item.get('title', '')).strip(),
                'metadata': {
                    'url': str(item.get('url', '')).strip(),
                    'tags': item.get('tags', []) if isinstance(item.get('tags'), list) else [],
                    'raw_score': item_score,
                    'pipeline_source': intel_payload.get('source', 'intel'),
                },
            },
        )
        intel_written += 1

    # Execution-derived outcomes
    trades_payload = _fetch_trade_executions(hours=safe_hours, limit=500, include_simulated=False, include_failed=True)
    trades = trades_payload.get('trades', [])
    for trade in trades:
        if not isinstance(trade, dict):
            continue
        ts = _coerce_datetime(trade.get('timestamp')) or now_utc
        if ts < cutoff:
            continue
        trade_id = str(trade.get('trade_id', '')).strip()
        if not trade_id:
            continue
        pnl = float(trade.get('realized_pnl', 0.0) or 0.0)
        success = bool(trade.get('success', False))
        if success:
            score = min(1.0, round(0.72 + min(max(pnl, 0.0), 50.0) / 250.0, 4))
            verdict = 'win'
        else:
            score = max(0.0, round(0.28 - min(abs(pnl), 50.0) / 250.0, 4))
            verdict = 'loss'
        doc_id = f"trade-{trade_id}"
        _upsert(
            doc_id,
            {
                'id': doc_id,
                'timestamp': ts.isoformat(),
                'created_at': now_utc.isoformat(),
                'outcome_type': 'execution_result',
                'experiment_id': str(trade.get('signal_id', '')).strip() or trade_id,
                'source': f"execution:{str(trade.get('platform', 'unknown')).strip().lower() or 'unknown'}",
                'category': 'execution',
                'confidence': 'high' if success else 'low',
                'quality_score': score,
                'verdict': verdict,
                'summary': f"{str(trade.get('side', 'TRADE')).upper()} {str(trade.get('symbol', 'UNKNOWN')).upper()}",
                'metadata': {
                    'trade_id': trade_id,
                    'signal_id': str(trade.get('signal_id', '')).strip(),
                    'pnl': pnl,
                    'qty': float(trade.get('filled_quantity', 0.0) or 0.0),
                    'success': success,
                },
            },
        )
        trade_written += 1

    return {
        'written': written,
        'intel_written': intel_written,
        'trade_written': trade_written,
        'window_hours': safe_hours,
    }


def _compute_learning_rollup(hours: int = 168) -> dict:
    if db is None:
        return {
            'window_hours': max(24, min(int(hours or 168), 24 * 30)),
            'summary': {'total': 0, 'wins': 0, 'losses': 0, 'pending': 0, 'win_rate': 0.0},
            'source_efficacy': [],
            'experiment_win_rate': {'total': 0, 'wins': 0, 'losses': 0, 'pending': 0, 'win_rate': 0.0},
        }

    safe_hours = max(24, min(int(hours or 168), 24 * 30))
    since = datetime.now(timezone.utc) - timedelta(hours=safe_hours)

    try:
        docs = list(
            db.collection(LEARNING_OUTCOMES_COLLECTION)
            .where('timestamp', '>=', since.isoformat())
            .order_by('timestamp', direction=firestore.Query.DESCENDING)
            .limit(2000)
            .stream()
        )
    except Exception:
        docs = list(
            db.collection(LEARNING_OUTCOMES_COLLECTION)
            .order_by('timestamp', direction=firestore.Query.DESCENDING)
            .limit(2500)
            .stream()
        )

    source_stats: dict[str, dict] = {}
    experiment_stats: dict[str, dict] = {}
    wins = losses = pending = 0

    for doc in docs:
        row = doc.to_dict() or {}
        ts = _coerce_datetime(row.get('timestamp'))
        if ts and ts < since:
            continue
        source = str(row.get('source', 'unknown')).strip().lower() or 'unknown'
        experiment_id = str(row.get('experiment_id', '')).strip()
        verdict = str(row.get('verdict', 'pending')).strip().lower()
        score = float(row.get('quality_score', 0.5) or 0.5)

        src = source_stats.setdefault(source, {'source': source, 'count': 0, 'wins': 0, 'losses': 0, 'pending': 0, 'score_sum': 0.0})
        src['count'] += 1
        src['score_sum'] += score
        if verdict == 'win':
            src['wins'] += 1
            wins += 1
        elif verdict == 'loss':
            src['losses'] += 1
            losses += 1
        else:
            src['pending'] += 1
            pending += 1

        if experiment_id:
            exp = experiment_stats.setdefault(experiment_id, {'experiment_id': experiment_id, 'wins': 0, 'losses': 0, 'pending': 0, 'count': 0})
            exp['count'] += 1
            if verdict == 'win':
                exp['wins'] += 1
            elif verdict == 'loss':
                exp['losses'] += 1
            else:
                exp['pending'] += 1

    efficacy = []
    for row in source_stats.values():
        count = max(1, int(row['count']))
        avg_quality = round(float(row['score_sum']) / count, 4)
        win_rate = round((float(row['wins']) / max(1, (row['wins'] + row['losses']))) * 100.0, 2) if (row['wins'] + row['losses']) > 0 else 0.0
        efficacy.append(
            {
                'source': row['source'],
                'count': int(row['count']),
                'wins': int(row['wins']),
                'losses': int(row['losses']),
                'pending': int(row['pending']),
                'avg_quality': avg_quality,
                'win_rate': win_rate,
            }
        )
    efficacy.sort(key=lambda item: (item['avg_quality'], item['count']), reverse=True)

    experiment_total_wins = sum(item['wins'] for item in experiment_stats.values())
    experiment_total_losses = sum(item['losses'] for item in experiment_stats.values())
    experiment_total_pending = sum(item['pending'] for item in experiment_stats.values())
    experiment_closed = experiment_total_wins + experiment_total_losses
    experiment_win_rate = round((experiment_total_wins / experiment_closed) * 100.0, 2) if experiment_closed > 0 else 0.0

    total = wins + losses + pending
    overall_closed = wins + losses
    overall_win_rate = round((wins / overall_closed) * 100.0, 2) if overall_closed > 0 else 0.0

    return {
        'window_hours': safe_hours,
        'summary': {
            'total': int(total),
            'wins': int(wins),
            'losses': int(losses),
            'pending': int(pending),
            'win_rate': overall_win_rate,
        },
        'source_efficacy': efficacy[:8],
        'experiment_win_rate': {
            'total': int(len(experiment_stats)),
            'wins': int(experiment_total_wins),
            'losses': int(experiment_total_losses),
            'pending': int(experiment_total_pending),
            'win_rate': experiment_win_rate,
        },
    }


def _persist_superswarm_rollup(payload: dict):
    if db is None:
        return {'written': False, 'error': 'firestore_unavailable'}
    try:
        now_iso = datetime.utcnow().isoformat()
        current_ref = db.collection(SUPERSWARM_ROLLUPS_COLLECTION).document('current')
        current_ref.set({**payload, 'updated_at': now_iso}, merge=True)
        point_id = now_iso.replace(':', '-').replace('.', '-')
        db.collection(SUPERSWARM_ROLLUPS_COLLECTION).document(point_id).set(
            {
                'timestamp': now_iso,
                'window_hours': payload.get('window_hours', 24),
                'summary': payload.get('summary', {}),
                'analysis': payload.get('analysis', {}),
                'loop': payload.get('loop', {}),
            },
            merge=True,
        )
        return {'written': True, 'timestamp': now_iso}
    except Exception as exc:
        return {'written': False, 'error': str(exc)}


def _platform_superswarm_payload(hours: int = 24, force_refresh: bool = False):
    safe_hours = max(6, min(int(hours or 24), 168))
    cache_key = f'platform_superswarm_{safe_hours}'
    cached = None if force_refresh else get_cached(cache_key, duration=20)
    if cached:
        return cached

    now_utc = datetime.now(timezone.utc)
    start_utc = now_utc - timedelta(hours=safe_hours)

    hourly_keys = []
    cursor = start_utc.replace(minute=0, second=0, microsecond=0)
    end_key = now_utc.replace(minute=0, second=0, microsecond=0)
    while cursor <= end_key:
        hourly_keys.append(cursor)
        cursor += timedelta(hours=1)

    signal_by_hour = {
        slot.isoformat(): {'received': 0, 'published': 0, 'failed': 0}
        for slot in hourly_keys
    }
    execution_by_hour = {
        slot.isoformat(): {'executed': 0, 'failed': 0, 'pnl': 0.0}
        for slot in hourly_keys
    }
    source_activity: dict[str, int] = {}

    logs_payload = _fetch_logs(hours=safe_hours, limit=max(160, safe_hours * 24), include_simulated=False)
    logs = logs_payload.get('logs', [])
    for row in logs:
        ts = _coerce_datetime(row.get('timestamp')) or now_utc
        if ts < start_utc:
            continue
        slot = ts.replace(minute=0, second=0, microsecond=0).isoformat()
        event_type = str(row.get('event_type', '')).strip().lower()
        message = str(row.get('message', '')).strip().lower()
        service = str(row.get('service', 'platform')).strip().lower() or 'platform'
        source_activity[service] = source_activity.get(service, 0) + 1

        if event_type == 'signal_received' or 'signal received' in message:
            signal_by_hour.setdefault(slot, {'received': 0, 'published': 0, 'failed': 0})['received'] += 1
        elif event_type == 'signal_published' or ('signal published' in message and 'trade' not in message):
            signal_by_hour.setdefault(slot, {'received': 0, 'published': 0, 'failed': 0})['published'] += 1
        elif event_type == 'signal_publish_failed' or 'signal publish failed' in message:
            signal_by_hour.setdefault(slot, {'received': 0, 'published': 0, 'failed': 0})['failed'] += 1

    trades_payload = _fetch_trade_executions(hours=safe_hours, limit=max(120, safe_hours * 12), include_simulated=False, include_failed=True)
    trades = trades_payload.get('trades', [])
    for row in trades:
        ts = _coerce_datetime(row.get('timestamp')) or now_utc
        if ts < start_utc:
            continue
        slot = ts.replace(minute=0, second=0, microsecond=0).isoformat()
        bucket = execution_by_hour.setdefault(slot, {'executed': 0, 'failed': 0, 'pnl': 0.0})
        pnl = float(row.get('realized_pnl', 0.0) or 0.0)
        if bool(row.get('success', False)):
            bucket['executed'] += 1
        else:
            bucket['failed'] += 1
        bucket['pnl'] = round(bucket['pnl'] + pnl, 6)

    intel = _fetch_intel_feed_payload(limit=96)
    intel_items = intel.get('items', []) if isinstance(intel.get('items'), list) else []
    intel_categories: dict[str, int] = {}
    for item in intel_items:
        if not isinstance(item, dict):
            continue
        category = str(item.get('category', 'operations')).strip().lower() or 'operations'
        intel_categories[category] = intel_categories.get(category, 0) + 1

    projects = _fetch_projects_payload().get('projects', [])
    project_status: dict[str, int] = {}
    for item in projects:
        if not isinstance(item, dict):
            continue
        status = str(item.get('status', 'unknown')).strip().lower() or 'unknown'
        project_status[status] = project_status.get(status, 0) + 1

    status_data = _collect_system_status()
    summary = status_data.get('summary', {})
    control_url = _join_url(ALPHA_ENGINE_URL, '/control/status')
    control_resp = _get_json(control_url, timeout=4.0, retries=0)
    control = control_resp.get('data', {}) if control_resp.get('ok') else {}

    signal_series = []
    execution_series = []
    for slot in hourly_keys:
        iso_slot = slot.isoformat()
        signal_row = signal_by_hour.get(iso_slot, {'received': 0, 'published': 0, 'failed': 0})
        execution_row = execution_by_hour.get(iso_slot, {'executed': 0, 'failed': 0, 'pnl': 0.0})
        signal_series.append(
            {
                'hour': iso_slot,
                'received': int(signal_row.get('received', 0)),
                'published': int(signal_row.get('published', 0)),
                'failed': int(signal_row.get('failed', 0)),
            }
        )
        execution_series.append(
            {
                'hour': iso_slot,
                'executed': int(execution_row.get('executed', 0)),
                'failed': int(execution_row.get('failed', 0)),
                'pnl': float(round(execution_row.get('pnl', 0.0), 6)),
            }
        )

    total_signals = sum(item['published'] + item['received'] for item in signal_series)
    total_executions = sum(item['executed'] for item in execution_series)
    total_pnl = round(sum(item['pnl'] for item in execution_series), 6)

    payload = {
        'timestamp': datetime.utcnow().isoformat(),
        'window_hours': safe_hours,
        'summary': {
            'signals': total_signals,
            'executions': total_executions,
            'pnl_total': total_pnl,
            'services_healthy': int(summary.get('service_healthy', 0)),
            'services_total': int(summary.get('service_total', 0)),
            'nodes_healthy': int(summary.get('node_healthy', 0)),
            'nodes_total': int(summary.get('node_total', 0)),
        },
        'series': {
            'signal_flow': signal_series,
            'execution_flow': execution_series,
        },
        'breakdowns': {
            'intel_categories': [{'label': k, 'value': v} for k, v in sorted(intel_categories.items(), key=lambda item: item[1], reverse=True)],
            'project_status': [{'label': k, 'value': v} for k, v in sorted(project_status.items(), key=lambda item: item[1], reverse=True)],
            'service_health': [
                {'label': 'healthy_services', 'value': int(summary.get('service_healthy', 0))},
                {'label': 'unhealthy_services', 'value': int(summary.get('service_unhealthy', 0))},
                {'label': 'healthy_nodes', 'value': int(summary.get('node_healthy', 0))},
                {'label': 'unhealthy_nodes', 'value': int(summary.get('node_unhealthy', 0))},
            ],
            'source_activity': [{'label': k, 'value': v} for k, v in sorted(source_activity.items(), key=lambda item: item[1], reverse=True)[:8]],
        },
        'loop': {
            'full_autonomy_enabled': bool(control.get('full_autonomy_enabled', False)),
            'memory_enabled': bool(control.get('memory_enabled', False)),
            'cognition_enabled': bool(control.get('cognition_enabled', False)),
            'experiments_queued': int(control.get('pending_autonomy_decisions', 0) or 0),
            'readiness_ok': int(summary.get('service_unhealthy', 1)) == 0 and int(summary.get('node_unhealthy', 1)) == 0,
        },
        'sources': {
            'logs_source': logs_payload.get('source'),
            'trades_source': trades_payload.get('source'),
            'intel_source': intel.get('source'),
            'projects_source': 'pm_hub',
        },
    }

    learning_rollup = _compute_learning_rollup(hours=max(24, safe_hours * 7))
    payload['analysis'] = {
        'source_efficacy': learning_rollup.get('source_efficacy', []),
        'experiment_win_rate': learning_rollup.get('experiment_win_rate', {}),
        'learning_summary': learning_rollup.get('summary', {}),
    }

    set_cache(cache_key, payload)
    return payload


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
        # `overall_healthy` reflects production-critical core only; optional edge devices are reported separately.
        'overall_healthy': core_unhealthy_count == 0,
        'overall_healthy_all': (summary.get('service_unhealthy', 0) == 0 and summary.get('node_unhealthy', 0) == 0),
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
        'superswarm': lambda: _platform_superswarm_payload(hours=24),
        'business_brief': lambda: _platform_business_brief_payload(hours=24),
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
        'superswarm': results.get('superswarm', {}).get('data') or {'summary': {}, 'series': {}, 'breakdowns': {}},
        'business_brief': results.get('business_brief', {}).get('data') or {'summary': {}, 'narrative': {}},
    }

    set_cache('platform_home_snapshot', payload)
    return payload


def _build_business_brief_narrative(
    *,
    readiness_ok: bool,
    services_healthy: int,
    services_total: int,
    projects_total: int,
    projects_active: int,
    workspaces: int,
    signals: int,
    executions: int,
    pnl_total: float,
    risk_state: str,
) -> dict:
    readiness_phrase = 'green' if readiness_ok else 'under watch'
    headline = (
        f"Sapphire platform is {readiness_phrase} with {services_healthy}/{services_total} services healthy, "
        f"{projects_active}/{projects_total} active programs, and {executions} execution events in window."
    )
    operations = (
        f"Operations span {workspaces} lanes with {signals} signal events and {executions} execution events "
        f"over the current telemetry window."
    )
    delivery = (
        f"Client delivery tracks {projects_total} programs, with {projects_active} currently active."
    )
    reliability = (
        f"Core reliability is {services_healthy}/{services_total}; readiness is {'PASS' if readiness_ok else 'WATCH'} "
        f"with risk posture {risk_state.upper()}."
    )
    performance = f"Window realized PnL: {round(float(pnl_total or 0.0), 6)}"
    return {
        'headline': headline,
        'operations': operations,
        'delivery': delivery,
        'reliability': reliability,
        'performance': performance,
        'risk_state': risk_state,
    }


def _platform_business_brief_payload(hours: int = 24, force_refresh: bool = False):
    safe_hours = max(6, min(int(hours or 24), 168))
    cache_key = f'platform_business_brief_{safe_hours}'
    cached = None if force_refresh else get_cached(cache_key, duration=30)
    if cached:
        return cached

    status_data = _collect_system_status()
    metrics = _platform_metrics_payload()
    projects_payload = _fetch_projects_payload()
    organization = _platform_organization_payload(refresh=False)
    readiness = _build_readiness_payload(request.url_root, include_business_brief_check=False)
    superswarm = _platform_superswarm_payload(hours=safe_hours, force_refresh=force_refresh)
    logs_payload = _fetch_logs(hours=safe_hours, limit=max(120, safe_hours * 12), include_simulated=False)

    summary = status_data.get('summary', {})
    project_rows = projects_payload.get('projects', []) if isinstance(projects_payload, dict) else []
    active_projects = sum(
        1 for row in project_rows
        if str((row or {}).get('status', '')).strip().lower() in ('active', 'in_progress')
    )
    blocked_projects = sum(
        1 for row in project_rows
        if str((row or {}).get('status', '')).strip().lower() == 'blocked'
    )
    logs = logs_payload.get('logs', []) if isinstance(logs_payload, dict) else []
    warning_count = sum(
        1 for row in logs
        if str((row or {}).get('level', '')).strip().lower() in ('warn', 'warning', 'error')
    )
    health = (metrics or {}).get('health', {}) if isinstance(metrics, dict) else {}
    optional_degraded = int(health.get('optional_degraded_count', 0) or 0)
    readiness_ok = bool(readiness.get('overall_ok', False))
    service_unhealthy = int(summary.get('service_unhealthy', 0) or 0)
    risk_state = 'stable'
    if not readiness_ok or service_unhealthy > 0:
        risk_state = 'watch'
    elif blocked_projects > 0 or optional_degraded > 0 or warning_count > 0:
        risk_state = 'attention'

    superswarm_summary = (superswarm or {}).get('summary', {}) if isinstance(superswarm, dict) else {}
    services_healthy = int(summary.get('service_healthy', 0) or 0)
    services_total = int(summary.get('service_total', 0) or 0)
    projects_total = int(len(project_rows))
    workspaces = int((organization.get('summary') or {}).get('workspaces', 0) or 0)
    signals = int(superswarm_summary.get('signals', 0) or 0)
    executions = int(superswarm_summary.get('executions', 0) or 0)
    pnl_total = float(superswarm_summary.get('pnl_total', 0.0) or 0.0)

    payload = {
        'timestamp': datetime.utcnow().isoformat(),
        'window_hours': safe_hours,
        'summary': {
            'services_healthy': services_healthy,
            'services_total': services_total,
            'services_unhealthy': int(summary.get('service_unhealthy', 0) or 0),
            'nodes_healthy': int(summary.get('node_healthy', 0) or 0),
            'nodes_total': int(summary.get('node_total', 0) or 0),
            'projects_total': projects_total,
            'projects_active': active_projects,
            'projects_blocked': blocked_projects,
            'workspaces': workspaces,
            'signals': signals,
            'executions': executions,
            'pnl_total': round(pnl_total, 6),
            'optional_degraded': optional_degraded,
            'warning_events': warning_count,
            'readiness_ok': readiness_ok,
            'risk_state': risk_state,
        },
        'narrative': _build_business_brief_narrative(
            readiness_ok=readiness_ok,
            services_healthy=services_healthy,
            services_total=services_total,
            projects_total=projects_total,
            projects_active=active_projects,
            workspaces=workspaces,
            signals=signals,
            executions=executions,
            pnl_total=pnl_total,
            risk_state=risk_state,
        ),
        'sources': {
            'status': 'api/platform/status',
            'metrics': 'api/platform/metrics',
            'control_plane': 'api/platform/control-plane',
            'projects': 'api/platform/projects',
            'organization': 'api/platform/organization',
            'readiness': 'api/platform/readiness',
            'superswarm': 'api/platform/superswarm',
            'logs': 'api/platform/logs',
        },
        'generated_at': datetime.utcnow().isoformat(),
    }
    set_cache(cache_key, payload)
    return payload


def _persist_business_brief(payload: dict):
    if db is None:
        return {'written': False, 'error': 'firestore_unavailable'}
    try:
        now_iso = datetime.utcnow().isoformat()
        current_ref = db.collection(BUSINESS_BRIEFS_COLLECTION).document('current')
        current_ref.set({**payload, 'updated_at': now_iso}, merge=True)
        point_id = now_iso.replace(':', '-').replace('.', '-')
        db.collection(BUSINESS_BRIEFS_COLLECTION).document(point_id).set(
            {
                'timestamp': now_iso,
                'window_hours': payload.get('window_hours', 24),
                'summary': payload.get('summary', {}),
                'narrative': payload.get('narrative', {}),
                'sources': payload.get('sources', {}),
            },
            merge=True,
        )
        return {'written': True, 'timestamp': now_iso}
    except Exception as exc:
        return {'written': False, 'error': str(exc)}


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


def _read_firestore_doc(collection_name: str, doc_id: str) -> dict:
    if db is None:
        return {}
    try:
        doc = db.collection(collection_name).document(doc_id).get()
        if not doc.exists:
            return {}
        value = doc.to_dict() or {}
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _trim_policy_settings(raw: dict) -> dict:
    if not isinstance(raw, dict):
        return {}
    keys = [
        'TRADING_ENABLED',
        'ALLOW_LIVE_TRADING',
        'LIGHTER_SINGLE_SYMBOL_MODE',
        'LIGHTER_ALLOWED_STRATEGIES',
        'LIGHTER_ALLOWED_TIMEFRAMES',
        'LIGHTER_MAX_ORDER_NOTIONAL_USD',
        'LIGHTER_TARGET_ORDER_NOTIONAL_USD',
        'LIGHTER_MAX_POSITION_NOTIONAL_USD',
        'LIGHTER_MAX_SIGNAL_LEVERAGE',
        'LIGHTER_ENTRY_COOLDOWN_SECONDS',
        'LIGHTER_DEFAULT_TAKE_PROFIT_PCT',
        'LIGHTER_DEFAULT_STOP_LOSS_PCT',
        'LIGHTER_DYNAMIC_TP_SL_ENABLED',
        'LIGHTER_OPPORTUNITY_ROTATION_ENABLED',
        'LIGHTER_OPPORTUNITY_MIN_EV_EDGE_PCT',
    ]
    out = {}
    for key in keys:
        if key in raw:
            out[key] = raw.get(key)
    return out


def _host_row_summary(prefix: str, status_payload: dict) -> dict:
    nodes = status_payload.get('nodes', {}) if isinstance(status_payload.get('nodes'), dict) else {}
    by_category = status_payload.get('by_category', {}) if isinstance(status_payload.get('by_category'), dict) else {}
    pi_rows = by_category.get('pi', []) if isinstance(by_category.get('pi'), list) else []
    matching_rows = [
        row for row in pi_rows
        if isinstance(row, dict) and str(row.get('name', '')).startswith(prefix)
    ]
    node = nodes.get(prefix, {}) if isinstance(nodes.get(prefix), dict) else {}
    if matching_rows:
        healthy = all(bool(row.get('healthy', False)) for row in matching_rows)
        latency = next((row.get('response_time_ms') for row in matching_rows if row.get('response_time_ms') is not None), None)
        status = 'healthy' if healthy else 'degraded'
    else:
        healthy = bool(node.get('healthy', False))
        latency = node.get('latency_ms')
        status = str(node.get('status', 'unknown'))
    return {
        'name': prefix,
        'healthy': healthy,
        'status': status,
        'latency_ms': latency,
        'rows': matching_rows,
        'health_url': node.get('health_url'),
        'ip': node.get('ip'),
    }


def _platform_control_plane_payload():
    cached = get_cached('platform_control_plane', duration=8)
    if cached:
        return cached

    status_payload = _collect_system_status()
    desired = _read_firestore_doc('control_plane_desired', 'lighter')
    applied = _read_firestore_doc('control_plane_applied', 'lighter')
    lane_health = _read_firestore_doc('execution_lane_health', 'lighter')
    live_positions = _read_firestore_doc('live_positions', 'lighter')
    assistant_latest = _read_firestore_doc('assistant_ops_briefs', 'latest')

    control_url = _join_url(ALPHA_ENGINE_URL, '/control/status')
    control_resp = _get_json(control_url, timeout=4.0, retries=0)
    alpha_control = control_resp.get('data', {}) if control_resp.get('ok') else {}
    if not isinstance(alpha_control, dict):
        alpha_control = {}

    desired_settings = desired.get('effective_settings', {}) if isinstance(desired.get('effective_settings'), dict) else {}
    applied_settings = applied.get('effective_settings', {}) if isinstance(applied.get('effective_settings'), dict) else {}
    policy = _trim_policy_settings(applied_settings or desired_settings)

    host_states = {
        'rari1': _host_row_summary('rari1', status_payload),
        'rari2': _host_row_summary('rari2', status_payload),
    }

    selected_target_host = str(applied.get('selected_target_host') or desired.get('target_host') or '').strip()
    lane_decision = applied.get('lane_decision') if isinstance(applied.get('lane_decision'), dict) else {}
    failover_used = bool(lane_decision.get('failover_used', False))
    configured_failover_hosts = lane_decision.get('failover_hosts', []) if isinstance(lane_decision.get('failover_hosts'), list) else []
    open_positions = int(live_positions.get('position_count', 0) or 0)

    payload = {
        'timestamp': datetime.utcnow().isoformat(),
        'summary': {
            'lane_healthy': bool(lane_health.get('healthy', False)),
            'failover_hosts_configured': int(len(configured_failover_hosts)),
            'failover_used_last_apply': failover_used,
            'selected_target_host': selected_target_host,
            'open_positions': open_positions,
        },
        'desired': {
            'desired_version': desired.get('desired_version'),
            'state': desired.get('state'),
            'profile': desired.get('profile'),
            'target_host': desired.get('target_host'),
            'run_test': desired.get('run_test'),
            'test_quantity': desired.get('test_quantity'),
            'notes': desired.get('notes'),
            'last_apply_status': desired.get('last_apply_status'),
            'last_apply_at_iso': desired.get('last_apply_at_iso'),
        },
        'applied': {
            'desired_version': applied.get('desired_version'),
            'status': applied.get('status'),
            'profile': applied.get('profile'),
            'target_host': applied.get('target_host'),
            'selected_target_host': applied.get('selected_target_host'),
            'applied_at_iso': applied.get('applied_at_iso'),
            'run_test': applied.get('run_test'),
            'test_quantity': applied.get('test_quantity'),
            'close_after_test': applied.get('close_after_test'),
            'deploy_ok': bool((applied.get('deploy') or {}).get('ok', False)) if isinstance(applied.get('deploy'), dict) else None,
            'override_apply_ok': bool((applied.get('override_apply') or {}).get('ok', False)) if isinstance(applied.get('override_apply'), dict) else None,
            'test_ok': bool((applied.get('test') or {}).get('ok', False)) if isinstance(applied.get('test'), dict) else None,
            'close_ok': bool((applied.get('close') or {}).get('ok', False)) if isinstance(applied.get('close'), dict) else None,
            'primary_disarm_ok': bool((applied.get('primary_disarm') or {}).get('ok', False)) if isinstance(applied.get('primary_disarm'), dict) else None,
            'lane_reason': lane_decision.get('reason'),
        },
        'lane_health': lane_health,
        'policy': policy,
        'host_states': host_states,
        'live_positions': {
            'position_count': open_positions,
            'updated_at': str(live_positions.get('updated_at') or ''),
            'positions': live_positions.get('positions', []) if isinstance(live_positions.get('positions'), list) else [],
        },
        'alpha_control': {
            'dex_execution_stage': alpha_control.get('dex_execution_stage'),
            'dex_live_dispatch_enabled': alpha_control.get('dex_live_dispatch_enabled'),
            'tradingview_execution_enabled': alpha_control.get('tradingview_execution_enabled'),
            'owner_approval_required': alpha_control.get('owner_approval_required'),
            'pending_autonomy_decisions': alpha_control.get('pending_autonomy_decisions'),
            'failure_pressure': alpha_control.get('failure_pressure'),
        },
        'assistant_ops_latest': assistant_latest if isinstance(assistant_latest, dict) else {},
        'sources': {
            'control_plane_desired': bool(desired),
            'control_plane_applied': bool(applied),
            'execution_lane_health': bool(lane_health),
            'live_positions': bool(live_positions),
            'alpha_control': bool(control_resp.get('ok', False)),
            'status': '/api/platform/status',
        },
    }
    set_cache('platform_control_plane', payload)
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


def _platform_contracts_payload():
    host_root = (request.url_root or '').rstrip('/')
    revision = os.environ.get('K_REVISION', '')

    endpoints = []
    for row in PLATFORM_CONTRACTS:
        path = row.get('path', '')
        endpoints.append(
            {
                **row,
                'url': f"{host_root}{path}" if host_root and path.startswith('/') else path,
                'auth_required': bool(ENABLE_AUTH),
                'public_available': not ENABLE_AUTH,
            }
        )

    return {
        'name': 'Sapphire Platform Contract Manifest',
        'version': PLATFORM_CONTRACT_VERSION,
        'generated_at': datetime.utcnow().isoformat(),
        'revision': revision,
        'auth': {
            'enabled': bool(ENABLE_AUTH),
            'mode': 'basic' if ENABLE_AUTH else 'public',
            'public_read_only': bool(PUBLIC_READ_ONLY),
            'internal_jobs_enabled': bool(ENABLE_INTERNAL_JOBS),
        },
        'endpoints': endpoints,
        'counts': {
            'total': len(endpoints),
            'categories': sorted({item.get('category', 'core') for item in endpoints}),
        },
        'aliases': {
            '/api/status': '/api/platform/status',
            '/api/trading/metrics': '/api/platform/metrics',
            '/api/business-brief': '/api/platform/business-brief',
            '/api/logs': '/api/platform/logs',
            '/api/trades': '/api/platform/trades',
            '/api/organization': '/api/platform/organization',
            '/api/production/readiness': '/api/platform/readiness',
            '/api/projects': '/api/platform/projects',
            '/api/intel/feed': '/api/platform/intel-feed',
            '/api/superswarm': '/api/platform/superswarm',
            '/api/windows-lab': '/api/platform/windows-lab',
            '/api/contracts': '/api/platform/contracts',
            '/api/control-plane': '/api/platform/control-plane',
        },
        'alias_policy': {
            'deprecated': True,
            'sunset': LEGACY_ALIAS_SUNSET,
            'successor_prefix': '/api/platform/',
        },
        'notes': [
            'Use /api/platform/* contracts for all new clients.',
            'Legacy aliases are maintained for compatibility and will be retired after migration.',
            'Public web is read-only; control/mutation routes are disabled on this service.',
        ],
    }


# ---------------------------------------------------------------------------
# PAGE ROUTES
# ---------------------------------------------------------------------------

@app.route('/')
@requires_auth
def index():
    return render_template('pages/overview.html', current_page='overview', page_title='Sapphire Overview')


@app.route('/organization')
@requires_auth
def organization():
    return render_template('pages/organization.html', current_page='organization', page_title='Organization & Programs')


@app.route('/intelligence')
@requires_auth
def intelligence():
    return render_template('pages/intelligence.html', current_page='intelligence', page_title='Market & Intelligence')


@app.route('/platform')
@requires_auth
def platform():
    return render_template('pages/platform.html', current_page='platform', page_title='Platform Reliability')


@app.route('/activity')
@requires_auth
def activity():
    return render_template('pages/activity.html', current_page='activity', page_title='Activity Stream')


@app.route('/sapphire-book')
@requires_auth
def sapphire_book():
    return render_template('pages/sapphire_book.html', current_page='sapphire-book', page_title='Sapphire Book')


@app.route('/architecture')
@requires_auth
def architecture():
    return render_template('pages/architecture.html', current_page='architecture', page_title='System Architecture')


@app.route('/settings')
@requires_auth
def settings():
    return render_template('pages/settings.html', current_page='settings', page_title='Security Policy')


@app.route('/control')
@requires_operator_access
def control():
    return render_template('pages/control.html', current_page='control', page_title='Control Plane')


# Legacy page routes -> consolidated IA
@app.route('/trading')
@requires_auth
def trading_legacy():
    return redirect('/intelligence', code=302)


@app.route('/feed')
@requires_auth
def feed_legacy():
    return redirect('/intelligence', code=302)


@app.route('/autonomy')
@requires_auth
def autonomy_legacy():
    return redirect('/platform', code=302)


@app.route('/command-deck')
@requires_auth
def command_deck_legacy():
    return redirect('/platform', code=302)


@app.route('/system-health')
@requires_auth
def system_health_legacy():
    return redirect('/platform', code=302)


@app.route('/logs')
@requires_auth
def logs_legacy():
    return redirect('/activity', code=302)


@app.route('/projects')
@requires_auth
def projects_legacy():
    return redirect('/organization#programs', code=302)


@app.route('/production-readiness')
@requires_auth
def production_readiness_legacy():
    return redirect('/platform', code=302)


@app.route('/infrastructure')
@requires_auth
def infrastructure_legacy():
    return redirect('/platform', code=302)


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
    return _deprecated_alias_response(jsonify(_collect_system_status()), '/api/platform/status')


@app.route('/api/health/summary')
@requires_auth
def api_health_summary():
    return _deprecated_alias_response(jsonify(_platform_health_summary()), '/api/platform/readiness')


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


@app.route('/api/platform/business-brief')
@requires_auth
def api_platform_business_brief():
    hours = request.args.get('hours', 24, type=int)
    refresh = request.args.get('refresh', 'false', type=str).lower() == 'true'
    return jsonify(_platform_business_brief_payload(hours=hours, force_refresh=refresh))


@app.route('/api/platform/logs')
@requires_auth
def api_platform_logs():
    hours = request.args.get('hours', 24, type=int)
    limit = request.args.get('limit', 100, type=int)
    service = request.args.get('service', '')
    level = request.args.get('level', '')
    include_simulated = request.args.get('include_simulated', 'false').lower() == 'true'
    return jsonify(
        _fetch_logs(
            hours=hours,
            limit=limit,
            service=service,
            level=level,
            include_simulated=include_simulated,
        )
    )


@app.route('/api/platform/trades')
@requires_auth
def api_platform_trades():
    hours = request.args.get('hours', 24, type=int)
    limit = request.args.get('limit', 100, type=int)
    include_simulated = request.args.get('include_simulated', 'false').lower() == 'true'
    include_failed = request.args.get('include_failed', 'false').lower() == 'true'
    return jsonify(
        _fetch_trade_executions(
            hours=hours,
            limit=limit,
            include_simulated=include_simulated,
            include_failed=include_failed,
        )
    )


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


@app.route('/api/platform/superswarm')
@requires_auth
def api_platform_superswarm():
    hours = request.args.get('hours', 24, type=int)
    refresh = request.args.get('refresh', 'false', type=str).lower() == 'true'
    return jsonify(_platform_superswarm_payload(hours=hours, force_refresh=refresh))


@app.route('/api/platform/windows-lab')
@requires_auth
def api_platform_windows_lab():
    return jsonify(_fetch_windows_lab_payload())


@app.route('/api/platform/contracts')
@requires_auth
def api_platform_contracts():
    return jsonify(_platform_contracts_payload())


@app.route('/api/platform/control-plane')
@requires_operator_access
def api_platform_control_plane():
    return jsonify(_platform_control_plane_payload())


@app.route('/api/logs')
@requires_auth
def api_logs():
    hours = request.args.get('hours', 24, type=int)
    limit = request.args.get('limit', 100, type=int)
    service = request.args.get('service', '')
    level = request.args.get('level', '')
    include_simulated = request.args.get('include_simulated', 'false').lower() == 'true'
    return _deprecated_alias_response(jsonify(
        _fetch_logs(
            hours=hours,
            limit=limit,
            service=service,
            level=level,
            include_simulated=include_simulated,
        )
    ), '/api/platform/logs')


@app.route('/api/market/prices')
@requires_auth
def api_market_prices():
    data = _platform_metrics_payload().get('market', {})
    if 'error' in data:
        return _deprecated_alias_response((jsonify(data), 502), '/api/platform/metrics')
    return _deprecated_alias_response(jsonify(data), '/api/platform/metrics')


@app.route('/api/projects')
@requires_auth
def api_projects():
    return _deprecated_alias_response(api_platform_projects(), '/api/platform/projects')


@app.route('/api/organization')
@requires_auth
def api_organization():
    return _deprecated_alias_response(api_platform_organization(), '/api/platform/organization')


@app.route('/api/production/readiness')
@requires_auth
def api_production_readiness():
    return _deprecated_alias_response(api_platform_readiness(), '/api/platform/readiness')


@app.route('/api/trading/metrics')
@requires_auth
def api_trading_metrics():
    return _deprecated_alias_response(jsonify(_platform_metrics_payload().get('trading', {})), '/api/platform/metrics')


@app.route('/api/business-brief')
@requires_auth
def api_business_brief():
    return _deprecated_alias_response(api_platform_business_brief(), '/api/platform/business-brief')


@app.route('/api/trades')
@requires_auth
def api_trades():
    return _deprecated_alias_response(api_platform_trades(), '/api/platform/trades')


@app.route('/api/windows-lab')
@requires_auth
def api_windows_lab():
    return _deprecated_alias_response(api_platform_windows_lab(), '/api/platform/windows-lab')


@app.route('/api/intel/feed')
@requires_auth
def api_intel_feed():
    return _deprecated_alias_response(api_platform_intel_feed(), '/api/platform/intel-feed')


@app.route('/api/superswarm')
@requires_auth
def api_superswarm():
    return _deprecated_alias_response(api_platform_superswarm(), '/api/platform/superswarm')


@app.route('/api/contracts')
@requires_auth
def api_contracts():
    return _deprecated_alias_response(api_platform_contracts(), '/api/platform/contracts')


@app.route('/api/control-plane')
@requires_operator_access
def api_control_plane():
    return _deprecated_alias_response(api_platform_control_plane(), '/api/platform/control-plane')


@app.route('/jobs/superswarm/hourly-rollup', methods=['POST', 'GET'])
@requires_control_token
def job_superswarm_hourly_rollup():
    payload = request.get_json(silent=True) if request.method == 'POST' else {}
    if not isinstance(payload, dict):
        payload = {}

    hours = request.args.get('hours', payload.get('hours', 24), type=int)
    hours = max(6, min(int(hours or 24), 168))

    outcome_sync = _sync_learning_outcomes(hours=max(24, hours))
    superswarm = _platform_superswarm_payload(hours=hours, force_refresh=True)
    persist = _persist_superswarm_rollup(superswarm)

    return jsonify(
        {
            'ok': bool(persist.get('written', False)),
            'timestamp': datetime.utcnow().isoformat(),
            'window_hours': hours,
            'outcomes': outcome_sync,
            'rollup': persist,
            'superswarm_summary': superswarm.get('summary', {}),
            'analysis_summary': (superswarm.get('analysis') or {}).get('learning_summary', {}),
        }
    ), 200 if persist.get('written', False) else 500


@app.route('/jobs/platform/hourly-brief', methods=['POST', 'GET'])
@requires_control_token
def job_platform_hourly_brief():
    payload = request.get_json(silent=True) if request.method == 'POST' else {}
    if not isinstance(payload, dict):
        payload = {}

    hours = request.args.get('hours', payload.get('hours', 24), type=int)
    hours = max(6, min(int(hours or 24), 168))

    brief = _platform_business_brief_payload(hours=hours, force_refresh=True)
    persist = _persist_business_brief(brief)

    return jsonify(
        {
            'ok': bool(persist.get('written', False)),
            'timestamp': datetime.utcnow().isoformat(),
            'window_hours': hours,
            'rollup': persist,
            'brief_summary': brief.get('summary', {}),
            'brief_narrative': brief.get('narrative', {}),
        }
    ), 200 if persist.get('written', False) else 500


# ═══════════════════════════════════════════════════════════════════════════════
# Terminal Commands (from Command Deck v3.0)
# ═══════════════════════════════════════════════════════════════════════════════

TERMINAL_COMMANDS = {
    'help': {
        'output': '''Available commands:
  status     - Show unified system status
  nodes      - List all infrastructure nodes
  metrics    - Show trading metrics
  pm         - Show PM dashboard summary
  logs       - Show recent log summary
  prices     - Show current market prices
  health     - Show platform health summary
  clear      - Clear terminal
  help       - Show this help''',
        'type': 'info'
    },
    'clear': {'output': '', 'type': 'clear'}
}


def _terminal_status_command():
    """Get live status for terminal"""
    try:
        status = _collect_system_status()
        by_cat = status.get('by_category', {})
        cloud = by_cat.get('cloud', [])
        pi = by_cat.get('pi', [])
        
        cloud_healthy = sum(1 for s in cloud if s.get('healthy'))
        pi_healthy = sum(1 for s in pi if s.get('healthy'))
        
        # Get PM data
        pm = _fetch_projects_payload()
        pm_count = pm.get('count', 0)
        
        output = f'''System Status:
  Cloud Services: {cloud_healthy}/{len(cloud)} healthy
  Pi Services: {pi_healthy}/{len(pi)} healthy
  PM Projects: {pm_count}
  Timestamp: {datetime.utcnow().strftime('%H:%M:%S UTC')}'''
        
        return {'output': output, 'type': 'success'}
    except Exception as e:
        return {'output': f'Error fetching status: {e}', 'type': 'error'}


def _terminal_nodes_command():
    """Get live nodes for terminal"""
    try:
        status = _collect_system_status()
        nodes = status.get('nodes', {})
        
        lines = ['Network Nodes:']
        for name, node in nodes.items():
            healthy = node.get('healthy', False)
            status_str = 'ONLINE' if healthy else 'OFFLINE'
            ip = node.get('ip', 'unknown')
            lines.append(f"  [{status_str}] {name.upper()} - {ip}")
        
        return {'output': '\n'.join(lines), 'type': 'info'}
    except Exception as e:
        return {'output': f'Error fetching nodes: {e}', 'type': 'error'}


def _terminal_metrics_command():
    """Get trading metrics for terminal"""
    try:
        payload = _platform_metrics_payload()
        perf = payload.get('performance', {})
        
        output = f'''Trading Metrics:
  24h PnL: {perf.get('pnl_24h', 0):.2f}%
  Win Rate: {perf.get('win_rate', 0):.1f}%
  Active Signals: {perf.get('active_signals', 0)}
  Latency: {perf.get('latency_ms', 0)}ms'''
        
        return {'output': output, 'type': 'success'}
    except Exception as e:
        return {'output': f'Error fetching metrics: {e}', 'type': 'error'}


def _terminal_pm_command():
    """Get PM summary for terminal"""
    try:
        pm = _fetch_projects_payload()
        projects = pm.get('projects', [])
        
        active = sum(1 for p in projects if p.get('status') == 'active')
        blocked = sum(1 for p in projects if p.get('status') == 'blocked')
        
        output = f'''PM Dashboard:
  Total Projects: {len(projects)}
  Active: {active}
  Blocked: {blocked}
  Source: {pm.get('source', 'unknown')}'''
        
        return {'output': output, 'type': 'success'}
    except Exception as e:
        return {'output': f'Error fetching PM data: {e}', 'type': 'error'}


def _terminal_prices_command():
    """Get market prices for terminal"""
    try:
        prices = _fetch_market_prices()
        
        output = f'''Market Prices:
  BTC: ${prices.get('BTC', {}).get('price', 0):,.0f} ({prices.get('BTC', {}).get('change', 0):+.2f}%)
  ETH: ${prices.get('ETH', {}).get('price', 0):,.0f} ({prices.get('ETH', {}).get('change', 0):+.2f}%)
  SOL: ${prices.get('SOL', {}).get('price', 0):,.0f} ({prices.get('SOL', {}).get('change', 0):+.2f}%)
  HYPE: ${prices.get('HYPE', {}).get('price', 0):,.0f} ({prices.get('HYPE', {}).get('change', 0):+.2f}%)'''
        
        return {'output': output, 'type': 'success'}
    except Exception as e:
        return {'output': f'Error fetching prices: {e}', 'type': 'error'}


def _terminal_health_command():
    """Get health summary for terminal"""
    try:
        status = _collect_system_status()
        summary = _platform_health_summary(status)
        
        overall = summary.get('overall', {})
        healthy_count = overall.get('healthy_count', 0)
        total_count = overall.get('total_count', 0)
        
        output = f'''Health Summary:
  Status: {overall.get('status', 'unknown').upper()}
  Healthy: {healthy_count}/{total_count}
  Degraded: {overall.get('degraded_count', 0)}
  Unhealthy: {overall.get('unhealthy_count', 0)}'''
        
        return {'output': output, 'type': 'success'}
    except Exception as e:
        return {'output': f'Error fetching health: {e}', 'type': 'error'}


def _terminal_logs_command():
    """Get logs summary for terminal"""
    try:
        # Fetch recent logs
        logs_url = _join_url(GATEWAY_URL, '/api/v1/logs')
        resp = requests.get(logs_url, params={'limit': '5'}, timeout=3)
        
        if resp.status_code == 200:
            data = resp.json()
            logs = data.get('logs', [])
            return {'output': f'Recent logs: {len(logs)} entries fetched\nUse /api/logs for full details', 'type': 'info'}
        else:
            return {'output': f'Logs unavailable (HTTP {resp.status_code})', 'type': 'warning'}
    except Exception as e:
        return {'output': f'Error fetching logs: {e}', 'type': 'error'}


@app.route('/api/terminal', methods=['POST'])
@requires_auth
def api_terminal():
    """Execute terminal commands with live data (from Command Deck v3.0)"""
    data = request.get_json(silent=True) or {}
    command = str(data.get('command', '')).strip().lower()
    
    # Static commands
    if command in TERMINAL_COMMANDS:
        return jsonify(TERMINAL_COMMANDS[command])
    
    # Live data commands
    handlers = {
        'status': _terminal_status_command,
        'nodes': _terminal_nodes_command,
        'metrics': _terminal_metrics_command,
        'pm': _terminal_pm_command,
        'prices': _terminal_prices_command,
        'health': _terminal_health_command,
        'logs': _terminal_logs_command,
    }
    
    if command in handlers:
        return jsonify(handlers[command]())
    else:
        return jsonify({
            'output': f"Command not found: {command}. Type 'help' for available commands.",
            'type': 'error'
        })


# ═══════════════════════════════════════════════════════════════════════════════
# Main Entry Point
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
