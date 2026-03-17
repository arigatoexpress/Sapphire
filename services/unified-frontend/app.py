#!/usr/bin/env python3
"""
Sapphire Unified Frontend
Multi-page dashboard with shared navigation and live status APIs.
"""

from datetime import datetime, timedelta, timezone
from functools import wraps
from concurrent.futures import ThreadPoolExecutor
import asyncio
import hashlib
import json
import math
import os
import re
import time
from urllib.parse import urljoin

import aiohttp
import requests
from firebase_admin import credentials, firestore, get_app, initialize_app
from flask import Flask, render_template, jsonify, request, Response, make_response, redirect, abort
from strategy_ops.runtime import (
    build_strategy_ops_assessment as _build_strategy_ops_assessment_core,
    build_go_no_go_brief_payload as _build_go_no_go_brief_payload,
    resolve_strategy_ops_decision as _resolve_strategy_ops_decision_core,
)
from strategy_ops.payload import (
    build_strategy_scorecard as _build_strategy_scorecard_core,
    build_data_quality_snapshot as _build_data_quality_snapshot_core,
    build_operator_decision_brief as _build_operator_decision_brief_core,
    build_signal_outcome_attribution as _build_signal_outcome_attribution_core,
)

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
RARI2_HEALTH_URL = os.environ.get('RARI2_HEALTH_URL', f'http://{RARI2_IP}:8080/health')
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
BOTTLENECK_DIGEST_COLLECTION = os.environ.get('BOTTLENECK_DIGEST_COLLECTION', 'platform_digest_state')
BOTTLENECK_DIGEST_DOC_ID = os.environ.get('BOTTLENECK_DIGEST_DOC_ID', 'architecture_bottleneck')
STRATEGY_OPS_DIGEST_DOC_ID = os.environ.get('STRATEGY_OPS_DIGEST_DOC_ID', 'strategy_ops')
STRATEGY_OPS_SNAPSHOTS_COLLECTION = os.environ.get('STRATEGY_OPS_SNAPSHOTS_COLLECTION', 'strategy_ops_snapshots')
LIBRARIAN_ENABLED = os.environ.get('LIBRARIAN_ENABLED', 'true').strip().lower() in {'1', 'true', 'yes', 'on'}
LIBRARIAN_MODE = os.environ.get('LIBRARIAN_MODE', 'local').strip().lower() or 'local'
LIBRARIAN_REMOTE_URL = os.environ.get('LIBRARIAN_REMOTE_URL', '').strip()
LIBRARIAN_REMOTE_API_KEY = os.environ.get('LIBRARIAN_REMOTE_API_KEY', '').strip()
LIBRARIAN_DEFAULT_QUERY = os.environ.get(
    'LIBRARIAN_DEFAULT_QUERY',
    'crypto perp trading context with risk, execution quality, and market catalysts',
).strip()
LIBRARIAN_MIN_SCORE = max(0.0, min(2.0, float(os.environ.get('LIBRARIAN_MIN_SCORE', '0.22') or 0.22)))
LIBRARIAN_DEFAULT_LIMIT = max(3, min(24, int(os.environ.get('LIBRARIAN_DEFAULT_LIMIT', '8') or 8)))
STRATEGY_OPS_FEE_BPS = max(0.0, float(os.environ.get('STRATEGY_OPS_FEE_BPS', '7.0') or 7.0))
STRATEGY_OPS_SLIPPAGE_BPS = max(0.0, float(os.environ.get('STRATEGY_OPS_SLIPPAGE_BPS', '5.0') or 5.0))
STRATEGY_OPS_DEFAULT_PAYOFF = max(0.1, float(os.environ.get('STRATEGY_OPS_DEFAULT_PAYOFF_RATIO', '1.2') or 1.2))
STRATEGY_OPS_EV_PROMOTE_MIN = float(os.environ.get('STRATEGY_OPS_PROMOTE_MIN_EV_PCT', '0.20') or 0.20)
STRATEGY_OPS_EV_MONITOR_MIN = float(os.environ.get('STRATEGY_OPS_MONITOR_MIN_EV_PCT', '0.05') or 0.05)
STRATEGY_OPS_EV_DEPRIORITIZE_MAX = float(os.environ.get('STRATEGY_OPS_DEPRIORITIZE_MAX_EV_PCT', '-0.05') or -0.05)
STRATEGY_OPS_EQUITY_BASE_USD = max(1.0, float(os.environ.get('STRATEGY_OPS_EQUITY_BASE_USD', '100.0') or 100.0))
FIREDANCER_GUI_URL = os.environ.get('FIREDANCER_GUI_URL', 'https://gui.firedancer.io').strip() or 'https://gui.firedancer.io'
FIREDANCER_WS_URL = os.environ.get('FIREDANCER_WS_URL', 'wss://gui.firedancer.io/websocket').strip() or 'wss://gui.firedancer.io/websocket'
FIREDANCER_WS_TIMEOUT_S = max(0.8, min(8.0, float(os.environ.get('FIREDANCER_WS_TIMEOUT_S', '2.8') or 2.8)))
FIREDANCER_WS_MAX_MESSAGES = max(8, min(240, int(os.environ.get('FIREDANCER_WS_MAX_MESSAGES', '72') or 72)))

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
        'name': 'strategy_ops',
        'path': '/api/platform/strategy-ops',
        'method': 'GET',
        'auth': 'basic_or_public',
        'category': 'telemetry',
        'description': 'Lane scorecard, reject-tax assessment, and GO/NO-GO posture.',
    },
    {
        'name': 'go_no_go_brief',
        'path': '/api/platform/go-no-go-brief',
        'method': 'GET',
        'auth': 'basic_or_public',
        'category': 'telemetry',
        'description': 'Single operator brief with final GO/NO-GO decision, blockers, and top actions.',
    },
    {
        'name': 'agent_context',
        'path': '/api/platform/agent-context',
        'method': 'GET',
        'auth': 'basic_or_public',
        'category': 'telemetry',
        'description': 'Single-call context bundle for visual agents and orchestration tools.',
    },
    {
        'name': 'librarian_context',
        'path': '/api/platform/librarian-context',
        'method': 'GET',
        'auth': 'basic_or_public',
        'category': 'telemetry',
        'description': 'Curated high-signal context pack (Librarian pattern) for agents and dashboards.',
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
        'name': 'intel_summary',
        'path': '/api/platform/intel-summary',
        'method': 'GET',
        'auth': 'basic_or_public',
        'category': 'research',
        'description': 'AI-condensed market pulse with movers, regime, and actionable watchlist.',
    },
    {
        'name': 'architecture_telemetry',
        'path': '/api/platform/architecture-telemetry',
        'method': 'GET',
        'auth': 'basic_or_public',
        'category': 'operations',
        'description': 'Live topology, edge flow rates, and pipeline operations telemetry.',
    },
    {
        'name': 'architecture_live',
        'path': '/api/platform/architecture-live',
        'method': 'GET',
        'auth': 'basic_or_public',
        'category': 'operations',
        'description': 'Full digital-twin blueprint: hierarchy, delegation, order of operations, and current gaps.',
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


def _public_status_payload(status_data: dict | None = None) -> dict:
    """Return status telemetry with sensitive infra fields redacted for public web."""
    status_data = status_data or _collect_system_status()
    services_raw = status_data.get('services', {}) if isinstance(status_data.get('services'), dict) else {}
    nodes_raw = status_data.get('nodes', {}) if isinstance(status_data.get('nodes'), dict) else {}
    by_category_raw = status_data.get('by_category', {}) if isinstance(status_data.get('by_category'), dict) else {}

    services = {
        name: {
            'healthy': bool((row or {}).get('healthy', False)),
            'status': str((row or {}).get('status', 'unknown')),
            'latency_ms': (row or {}).get('latency_ms'),
            'status_code': (row or {}).get('status_code'),
        }
        for name, row in services_raw.items()
    }
    nodes = {
        name: {
            'healthy': bool((row or {}).get('healthy', False)),
            'status': str((row or {}).get('status', 'unknown')),
            'latency_ms': (row or {}).get('latency_ms'),
            'status_code': (row or {}).get('status_code'),
        }
        for name, row in nodes_raw.items()
    }

    by_category = {}
    for category, rows in by_category_raw.items():
        normalized = []
        if isinstance(rows, list):
            for row in rows:
                if not isinstance(row, dict):
                    continue
                normalized.append(
                    {
                        'name': row.get('name', 'unknown'),
                        'healthy': bool(row.get('healthy', False)),
                        'status': str(row.get('status', 'unknown')),
                        'response_time_ms': row.get('response_time_ms'),
                    }
                )
        by_category[str(category)] = normalized

    payload = {
        'timestamp': status_data.get('timestamp', datetime.utcnow().isoformat()),
        'services': services,
        'nodes': nodes,
        'by_category': by_category,
        'summary': status_data.get('summary', {}),
        'privacy': {
            'mode': 'public_redacted',
            'sensitive_fields_removed': ['ip', 'url', 'health_url', 'internal_hostnames'],
        },
    }
    return payload


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


def _build_readiness_payload(
    host_root: str,
    include_business_brief_check: bool = True,
    include_architecture_live_check: bool = True,
):
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
        run_contract_check('/api/platform/strategy-ops', _platform_strategy_ops_payload),
        run_contract_check('/api/platform/go-no-go-brief', _platform_go_no_go_brief_payload),
        run_contract_check('/api/platform/agent-context', _platform_agent_context_payload),
        run_contract_check('/api/platform/librarian-context', _platform_librarian_context_payload),
        run_contract_check('/api/platform/autonomy', _platform_autonomy_payload),
        run_contract_check('/api/platform/home-snapshot', _platform_home_snapshot_payload),
        run_contract_check('/api/platform/logs', lambda: _fetch_logs(limit=1)),
        run_contract_check('/api/platform/trades', lambda: _fetch_trade_executions(limit=1)),
        run_contract_check('/api/platform/superswarm', lambda: _platform_superswarm_payload(hours=24)),
        run_contract_check('/api/platform/organization', _platform_organization_payload),
        run_contract_check('/api/platform/readiness', lambda: True),
        run_contract_check('/api/platform/projects', _fetch_projects_payload),
        run_contract_check('/api/platform/intel-feed', lambda: _fetch_intel_feed_payload(limit=3)),
        run_contract_check('/api/platform/intel-summary', lambda: _platform_intel_summary_payload(hours=6, limit=20)),
        run_contract_check('/api/platform/architecture-telemetry', lambda: _platform_architecture_telemetry_payload(hours=2)),
        run_contract_check('/api/platform/windows-lab', _fetch_windows_lab_payload),
        run_contract_check('/api/platform/contracts', _platform_contracts_payload),
    ]
    if include_architecture_live_check:
        contract_checks.append(
            run_contract_check('/api/platform/architecture-live', lambda: _platform_architecture_live_payload(hours=6))
        )
    if include_business_brief_check:
        contract_checks.append(
            run_contract_check('/api/platform/business-brief', lambda: _platform_business_brief_payload(hours=24))
        )

    contract_ok = all(check.get('healthy', False) for check in contract_checks)
    cloud_ok = service_summary.get('service_unhealthy', 1) == 0

    monitor = _get_monitor_snapshot()
    edge_blockers = []
    critical_rows = []
    optional_rows = []
    if monitor.get('available'):
        by_category = monitor.get('by_category', {})
        for category in ('pi', 'windows'):
            for row in by_category.get(category, []):
                if not isinstance(row, dict):
                    continue
                name = row.get('name')
                row_payload = {
                    'name': name,
                    'category': category,
                    'healthy': bool(row.get('healthy', False)),
                    'error': row.get('error'),
                }
                if name in CRITICAL_EDGE_SERVICES:
                    critical_rows.append(row_payload)
                elif category in OPTIONAL_HEALTH_CATEGORIES or name in OPTIONAL_HEALTH_NAMES:
                    optional_rows.append(row_payload)

        # Fallback: if critical list was misconfigured or no matches found, use all edge rows.
        if not critical_rows:
            for category in ('pi', 'windows'):
                for row in by_category.get(category, []):
                    if not isinstance(row, dict):
                        continue
                    name = row.get('name', 'unknown')
                    if category in OPTIONAL_HEALTH_CATEGORIES or name in OPTIONAL_HEALTH_NAMES:
                        continue
                    critical_rows.append({
                        'name': name,
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
            'optional_degraded': 0 if not monitor.get('available') else sum(1 for row in optional_rows if not row.get('healthy', False)),
            'optional_total': 0 if not monitor.get('available') else len(optional_rows),
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
        'cloud': _public_status_payload(status_data),
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
        'reject_tax': raw.get('reject_tax', {}),
        'positions': raw.get('positions', []),
        'raw': raw,
        'source': source,
        'timestamp': raw.get('timestamp', datetime.utcnow().isoformat()),
    }
    if error:
        payload['error'] = error
    return payload


def _fetch_reject_tax_metrics(hours: int = 24, limit: int = 1500) -> dict:
    if db is None:
        return {'sample_size': 0, 'reject_tax_pct': 0.0, 'error': 'firestore_unavailable'}

    safe_hours = max(1, min(int(hours or 24), 24 * 14))
    safe_limit = max(100, min(int(limit or 1500), 4000))
    since = datetime.now(timezone.utc) - timedelta(hours=safe_hours)

    try:
        docs = list(
            db.collection('execution_verifications')
            .where('platform', '==', 'lighter')
            .where('recorded_at', '>=', since)
            .order_by('recorded_at', direction=firestore.Query.DESCENDING)
            .limit(safe_limit)
            .stream()
        )
    except Exception:
        docs = list(
            db.collection('execution_verifications')
            .order_by('recorded_at', direction=firestore.Query.DESCENDING)
            .limit(max(400, min(safe_limit * 2, 8000)))
            .stream()
        )

    rows = []
    for doc in docs:
        row = doc.to_dict() or {}
        if str(row.get('platform', '')).strip().lower() != 'lighter':
            continue
        ts = _coerce_datetime(row.get('recorded_at') or row.get('timestamp'))
        if ts and ts < since:
            continue
        rows.append(row)

    def _key(value):
        text = str(value or '').strip().lower()
        return text or 'unknown'

    totals = {
        'sample_size': 0,
        'reject_skip_count': 0,
        'hard_failed_count': 0,
        'filled_success_count': 0,
        'accepted_no_fill_count': 0,
        'policy_noop_count': 0,
        'policy_reject_count': 0,
        'noop_count': 0,
    }
    by_source = {}
    by_strategy = {}
    by_timeframe = {}
    reason_counts = {}

    def _touch_bucket(store, key):
        if key not in store:
            store[key] = {'total': 0, 'reject_skip': 0, 'hard_failed': 0, 'filled_success': 0}
        return store[key]

    for row in rows:
        totals['sample_size'] += 1
        outcome = _key(row.get('outcome'))
        reject_like = outcome in {'policy_noop', 'policy_reject', 'noop'}
        hard_fail = outcome == 'hard_failed'
        filled = outcome == 'filled_success'

        if outcome == 'policy_noop':
            totals['policy_noop_count'] += 1
        elif outcome == 'policy_reject':
            totals['policy_reject_count'] += 1
        elif outcome == 'noop':
            totals['noop_count'] += 1
        elif outcome == 'accepted_no_fill':
            totals['accepted_no_fill_count'] += 1

        if reject_like:
            totals['reject_skip_count'] += 1
        if hard_fail:
            totals['hard_failed_count'] += 1
        if filled:
            totals['filled_success_count'] += 1

        source = _key(
            row.get('signal_source')
            or row.get('source')
            or (row.get('signal_metadata', {}) or {}).get('source')
            or row.get('channel')
        )
        strategy = _key(row.get('strategy'))
        timeframe = _key(row.get('timeframe'))
        for bucket in (
            _touch_bucket(by_source, source),
            _touch_bucket(by_strategy, strategy),
            _touch_bucket(by_timeframe, timeframe),
        ):
            bucket['total'] += 1
            if reject_like:
                bucket['reject_skip'] += 1
            if hard_fail:
                bucket['hard_failed'] += 1
            if filled:
                bucket['filled_success'] += 1

        if reject_like:
            reason = str(
                row.get('policy_reason')
                or row.get('noop_reason')
                or row.get('error_message')
                or ''
            ).strip().lower()
            if reason:
                if len(reason) > 140:
                    reason = reason[:137] + '...'
                reason_counts[reason] = reason_counts.get(reason, 0) + 1

    def _to_rows(store):
        data = []
        for key, bucket in store.items():
            denom = max(1, int(bucket['total']))
            data.append(
                {
                    'key': key,
                    'total': int(bucket['total']),
                    'reject_skip': int(bucket['reject_skip']),
                    'hard_failed': int(bucket['hard_failed']),
                    'filled_success': int(bucket['filled_success']),
                    'reject_tax_pct': round((float(bucket['reject_skip']) / denom) * 100.0, 2),
                }
            )
        data.sort(key=lambda item: (item['reject_skip'], item['total']), reverse=True)
        return data[:6]

    denom = max(1, int(totals['sample_size']))
    return {
        **totals,
        'window_hours': safe_hours,
        'reject_tax_pct': round((float(totals['reject_skip_count']) / denom) * 100.0, 2),
        'hard_fail_pct': round((float(totals['hard_failed_count']) / denom) * 100.0, 2),
        'by_source': _to_rows(by_source),
        'by_strategy': _to_rows(by_strategy),
        'by_timeframe': _to_rows(by_timeframe),
        'top_reasons': [
            {'reason': reason, 'count': count}
            for reason, count in sorted(reason_counts.items(), key=lambda item: item[1], reverse=True)[:6]
        ],
        'computed_at': datetime.now(timezone.utc).isoformat(),
    }


def _build_strategy_scorecard(days: int = 7, platform: str = 'lighter', limit: int = 1800) -> dict:
    return _build_strategy_scorecard_core(
        db_client=db,
        days=days,
        platform=platform,
        limit=limit,
    )

def _build_signal_outcome_attribution(days: int = 7, platform: str = 'lighter', limit: int = 2200) -> dict:
    return _build_signal_outcome_attribution_core(
        db_client=db,
        days=days,
        platform=platform,
        limit=limit,
    )


def _build_data_quality_snapshot(attribution: dict) -> dict:
    return _build_data_quality_snapshot_core(
        attribution=attribution,
        market_payload=_fetch_market_prices(),
        intel_summary_payload=_platform_intel_summary_payload(hours=24, limit=60, refresh=False),
    )


def _build_operator_decision_brief(
    *,
    scorecard: dict,
    reject_tax: dict,
    assessment: dict,
    attribution: dict,
    data_quality: dict,
) -> dict:
    return _build_operator_decision_brief_core(
        scorecard=scorecard,
        reject_tax=reject_tax,
        assessment=assessment,
        attribution=attribution,
        data_quality=data_quality,
    )


def _resolve_strategy_ops_decision(
    *,
    assessment: dict | None,
    operator_brief: dict | None,
    data_quality: dict | None,
) -> dict:
    return _resolve_strategy_ops_decision_core(
        assessment=assessment,
        operator_brief=operator_brief,
        data_quality=data_quality,
    )


def _build_strategy_ops_assessment(scorecard: dict, reject_tax: dict) -> dict:
    return _build_strategy_ops_assessment_core(scorecard=scorecard, reject_tax=reject_tax)


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
    metrics = (
        verified
        if verified is not None
        else _normalize_trading_metrics_payload(source='firestore_verified_empty', error='no_verified_executions')
    )
    reject_tax = _fetch_reject_tax_metrics(hours=24, limit=1500)
    metrics['reject_tax'] = reject_tax
    if isinstance(metrics.get('raw'), dict):
        metrics['raw']['reject_tax'] = reject_tax
    return metrics


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


def _safe_float(value, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_bool(value, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {'1', 'true', 'yes', 'on'}:
        return True
    if text in {'0', 'false', 'no', 'off'}:
        return False
    return default


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _platform_intel_summary_payload(hours: int = 24, limit: int = 60, refresh: bool = False) -> dict:
    safe_hours = max(4, min(int(hours or 24), 168))
    safe_limit = max(20, min(int(limit or 60), 200))
    cache_key = f"platform_intel_summary:{safe_hours}:{safe_limit}:{int(bool(refresh))}"
    if not refresh:
        cached = get_cached(cache_key, duration=20)
        if cached:
            return cached

    market = _fetch_market_prices()
    tracked = []
    if isinstance(market, dict):
        tracked = [str(sym).upper() for sym in (market.get('tracked_symbols') or []) if str(sym).strip()]
        if not tracked:
            tracked = sorted(
                key for key, row in market.items()
                if isinstance(row, dict) and 'price' in row
            )

    movers = []
    for symbol in tracked:
        quote = market.get(symbol, {}) if isinstance(market, dict) else {}
        if not isinstance(quote, dict):
            continue
        change = _safe_float(quote.get('change_24h'), 0.0)
        price = _safe_float(quote.get('price'), 0.0)
        movers.append(
            {
                'symbol': symbol,
                'price': price,
                'change_24h': round(change, 4),
                'direction': 'up' if change >= 0 else 'down',
                'magnitude': round(abs(change), 4),
            }
        )
    movers.sort(key=lambda row: abs(_safe_float(row.get('change_24h'))), reverse=True)

    n = max(len(movers), 1)
    avg_change = sum(_safe_float(row.get('change_24h')) for row in movers) / n
    avg_abs_change = sum(abs(_safe_float(row.get('change_24h'))) for row in movers) / n
    breadth_up = sum(1 for row in movers if _safe_float(row.get('change_24h')) > 0)
    breadth_ratio = breadth_up / n

    if avg_abs_change >= 4.0 and avg_change >= 1.0 and breadth_ratio >= 0.6:
        regime = 'risk_on_momentum'
        regime_label = 'Risk-On Momentum'
    elif avg_abs_change >= 4.0 and avg_change <= -1.0 and breadth_ratio <= 0.4:
        regime = 'risk_off_drawdown'
        regime_label = 'Risk-Off Drawdown'
    elif avg_abs_change <= 1.25:
        regime = 'range_compression'
        regime_label = 'Range / Compression'
    elif avg_change >= 0:
        regime = 'constructive_trend'
        regime_label = 'Constructive Trend'
    else:
        regime = 'defensive_rotation'
        regime_label = 'Defensive Rotation'

    regime_score = round(_clamp(50 + (avg_change * 5.5) + ((breadth_ratio - 0.5) * 26), 0, 100), 2)
    volatility_score = round(_clamp(avg_abs_change * 12, 0, 100), 2)

    intel_payload = _fetch_intel_feed_payload(limit=safe_limit, refresh=refresh)
    intel_items = intel_payload.get('items', []) if isinstance(intel_payload.get('items'), list) else []
    intel_categories: dict[str, int] = {}
    symbol_mentions = {symbol: 0.0 for symbol in tracked}
    confidence_weight = {'high': 1.0, 'medium': 0.65, 'low': 0.35}

    for item in intel_items:
        if not isinstance(item, dict):
            continue
        category = str(item.get('category', 'market')).strip().lower() or 'market'
        intel_categories[category] = intel_categories.get(category, 0) + 1

        conf = str(item.get('confidence', 'medium')).strip().lower()
        conf_w = confidence_weight.get(conf, 0.5)
        score_w = _clamp(_safe_float(item.get('score'), 0.5), 0.0, 1.0)
        text = " ".join(
            [
                str(item.get('title', '')),
                str(item.get('summary', '')),
                " ".join(str(tag) for tag in (item.get('tags') or [])),
            ]
        ).upper()
        for symbol in tracked:
            if symbol and symbol in text:
                symbol_mentions[symbol] = round(symbol_mentions.get(symbol, 0.0) + (conf_w * (0.6 + score_w)), 4)

    trades_payload = _fetch_trade_executions(hours=safe_hours, limit=200, include_failed=True)
    trade_rows = trades_payload.get('trades', []) if isinstance(trades_payload.get('trades'), list) else []
    executed_rows = [row for row in trade_rows if bool((row or {}).get('executed', False))]
    failed_rows = [row for row in trade_rows if not bool((row or {}).get('executed', False))]
    wins = [row for row in executed_rows if _safe_float((row or {}).get('realized_pnl')) >= 0]
    execution_quality = (
        round((len(executed_rows) / max(len(executed_rows) + len(failed_rows), 1)) * 100.0, 2)
        if trade_rows
        else 0.0
    )
    win_rate = round((len(wins) / max(len(executed_rows), 1)) * 100.0, 2) if executed_rows else 0.0

    superswarm = _platform_superswarm_payload(hours=safe_hours)
    superswarm_summary = superswarm.get('summary', {}) if isinstance(superswarm.get('summary'), dict) else {}
    signals = int(superswarm_summary.get('signals', 0) or 0)
    executions = int(superswarm_summary.get('executions', 0) or 0)

    status = _collect_system_status()
    summary = status.get('summary', {}) if isinstance(status.get('summary'), dict) else {}
    healthy_services = int(summary.get('service_healthy', 0) or 0)
    total_services = int(summary.get('service_total', 0) or 0)
    service_health_pct = round((healthy_services / max(total_services, 1)) * 100.0, 2)

    technicals = []
    for row in movers[: min(len(movers), 8)]:
        symbol = str(row.get('symbol', '')).upper()
        chg = _safe_float(row.get('change_24h'))
        momentum_score = _clamp(50 + (chg * 8.0), 0, 100)
        intel_support = _clamp(symbol_mentions.get(symbol, 0.0) * 15.0, 0, 100)
        composite = round((0.72 * momentum_score) + (0.28 * intel_support), 2)
        if composite >= 62:
            bias = 'bullish'
            action = 'Momentum continuation watch'
        elif composite <= 38:
            bias = 'bearish'
            action = 'Defensive / fade rallies'
        else:
            bias = 'neutral'
            action = 'Range discipline / wait for expansion'
        technicals.append(
            {
                'symbol': symbol,
                'bias': bias,
                'change_24h': round(chg, 4),
                'momentum_score': round(momentum_score, 2),
                'intel_support': round(intel_support, 2),
                'composite_score': composite,
                'action': action,
            }
        )
    technicals.sort(key=lambda row: row.get('composite_score', 0), reverse=True)

    top_categories = [
        {'category': key, 'count': value}
        for key, value in sorted(intel_categories.items(), key=lambda row: row[1], reverse=True)[:5]
    ]
    top_intel_items = sorted(
        [item for item in intel_items if isinstance(item, dict)],
        key=lambda item: (_safe_float(item.get('score'), 0.0), str(item.get('confidence', 'low')) == 'high'),
        reverse=True,
    )[:5]

    strongest = movers[0] if movers else {'symbol': 'N/A', 'change_24h': 0.0, 'price': 0.0}
    weakest = movers[-1] if movers else {'symbol': 'N/A', 'change_24h': 0.0, 'price': 0.0}
    insights = [
        {
            'topic': 'Regime',
            'value': regime_label,
            'detail': f"Breadth {breadth_up}/{n} up • avg move {avg_change:+.2f}%",
            'severity': 'high' if volatility_score >= 60 else 'medium',
        },
        {
            'topic': 'Mover',
            'value': f"{strongest.get('symbol', 'N/A')} {(_safe_float(strongest.get('change_24h'))):+.2f}%",
            'detail': f"Trailing: {weakest.get('symbol', 'N/A')} {(_safe_float(weakest.get('change_24h'))):+.2f}%",
            'severity': 'medium',
        },
        {
            'topic': 'Execution',
            'value': f"{execution_quality:.1f}% quality",
            'detail': f"{len(executed_rows)} fills / {len(failed_rows)} no-fill-fail • win-rate {win_rate:.1f}%",
            'severity': 'high' if execution_quality < 60 else 'low',
        },
        {
            'topic': 'Ops',
            'value': f"{signals} signals • {executions} executions",
            'detail': f"Service health {service_health_pct:.1f}% ({healthy_services}/{total_services})",
            'severity': 'high' if service_health_pct < 80 else 'low',
        },
    ]

    watchlist = []
    for row in technicals[:4]:
        watchlist.append(
            {
                'symbol': row.get('symbol'),
                'bias': row.get('bias'),
                'priority': 'high' if row.get('composite_score', 0) >= 65 else 'medium',
                'setup': row.get('action'),
                'reason': f"24h {(_safe_float(row.get('change_24h'))):+.2f}% • score {row.get('composite_score', 0):.1f}",
            }
        )

    payload = {
        'timestamp': datetime.utcnow().isoformat(),
        'window_hours': safe_hours,
        'market': {
            'source': market.get('source') if isinstance(market, dict) else 'unknown',
            'tracked_symbols': tracked,
            'movers': movers[:8],
            'regime': regime,
            'regime_label': regime_label,
            'regime_score': regime_score,
            'volatility_score': volatility_score,
            'breadth_up': breadth_up,
            'breadth_total': n,
            'avg_change_24h': round(avg_change, 4),
        },
        'intel': {
            'source': intel_payload.get('source'),
            'count': int(intel_payload.get('count', 0) or len(intel_items)),
            'top_categories': top_categories,
            'symbol_mentions': symbol_mentions,
            'top_items': [
                {
                    'title': str(item.get('title', 'Untitled')),
                    'summary': str(item.get('summary', '')),
                    'source': str(item.get('source', 'intel')),
                    'category': str(item.get('category', 'market')),
                    'confidence': str(item.get('confidence', 'medium')),
                    'score': _safe_float(item.get('score'), 0.0),
                    'published_at': _iso_or_default(item.get('published_at')),
                    'url': str(item.get('url', '')),
                }
                for item in top_intel_items
            ],
        },
        'technicals': technicals,
        'operations': {
            'signals': signals,
            'executions': executions,
            'execution_quality': execution_quality,
            'execution_win_rate': win_rate,
            'health_pct': service_health_pct,
        },
        'ai_digest': {
            'headline': (
                f"{regime_label}: {strongest.get('symbol', 'N/A')} leads at "
                f"{_safe_float(strongest.get('change_24h')):+.2f}% with "
                f"{execution_quality:.1f}% execution quality."
            ),
            'summary': (
                f"Volatility score {volatility_score:.1f}/100 across {n} tracked assets; "
                f"{signals} signal events and {executions} execution events in {safe_hours}h."
            ),
            'insights': insights,
            'watchlist': watchlist,
            'confidence': round(_clamp((regime_score * 0.55) + (execution_quality * 0.45), 0, 100), 2),
        },
        'sources': {
            'market': 'api/market/prices',
            'intel_feed': 'api/platform/intel-feed',
            'trades': 'api/platform/trades',
            'superswarm': 'api/platform/superswarm',
            'status': 'api/platform/status',
        },
    }
    set_cache(cache_key, payload)
    return payload


def _rpc_post_json(url: str, payload: dict, timeout: float = 6.0) -> dict:
    started = time.time()
    try:
        resp = requests.post(url, json=payload, timeout=timeout)
        status = resp.status_code
        if status != 200:
            return {
                'ok': False,
                'status_code': status,
                'latency_ms': round((time.time() - started) * 1000, 2),
                'error': f'http_{status}',
                'data': {},
            }
        data = resp.json() if resp.content else {}
        return {
            'ok': True,
            'status_code': status,
            'latency_ms': round((time.time() - started) * 1000, 2),
            'error': None,
            'data': data if isinstance(data, dict) else {},
        }
    except requests.RequestException as exc:
        return {
            'ok': False,
            'status_code': None,
            'latency_ms': round((time.time() - started) * 1000, 2),
            'error': str(exc),
            'data': {},
        }


def _fetch_btc_chain_activity() -> dict:
    payload = _get_json('https://api.blockchair.com/bitcoin/stats', timeout=5.5, retries=1)
    if not payload.get('ok'):
        return {'ok': False, 'error': payload.get('error') or 'unavailable'}
    row = payload.get('data', {}).get('data', {})
    if not isinstance(row, dict):
        return {'ok': False, 'error': 'invalid_payload'}

    tx_24h = max(0.0, _safe_float(row.get('transactions_24h'), 0.0))
    blocks_24h = max(0.0, _safe_float(row.get('blocks_24h'), 0.0))
    avg_block_time_s = (86400.0 / blocks_24h) if blocks_24h > 0 else 600.0
    tps = (tx_24h / 86400.0) if tx_24h > 0 else 0.0
    return {
        'ok': True,
        'chain': 'bitcoin',
        'symbol': 'BTC',
        'source': 'blockchair',
        'source_url': 'https://api.blockchair.com/bitcoin/stats',
        'last_observed_at': _iso_or_default(row.get('best_block_time')),
        'tx_24h': round(tx_24h, 2),
        'blocks_24h': round(blocks_24h, 2),
        'avg_block_time_s': round(avg_block_time_s, 2),
        'tps': round(tps, 4),
        'latency_ms': payload.get('latency_ms'),
    }


def _fetch_eth_chain_activity() -> dict:
    rpc = 'https://ethereum.publicnode.com'
    head = _rpc_post_json(
        rpc,
        {
            'jsonrpc': '2.0',
            'id': 1,
            'method': 'eth_blockNumber',
            'params': [],
        },
        timeout=5.0,
    )
    if not head.get('ok'):
        return {'ok': False, 'error': head.get('error') or 'unavailable'}
    head_hex = str((head.get('data') or {}).get('result', '0x0'))
    try:
        head_number = int(head_hex, 16)
    except ValueError:
        return {'ok': False, 'error': 'invalid_head_block'}

    block_rows = []
    sample_blocks = 10
    for i in range(sample_blocks):
        block_no = head_number - i
        block_hex = hex(max(block_no, 0))
        block_resp = _rpc_post_json(
            rpc,
            {
                'jsonrpc': '2.0',
                'id': 1 + i,
                'method': 'eth_getBlockByNumber',
                'params': [block_hex, False],
            },
            timeout=4.0,
        )
        if not block_resp.get('ok'):
            continue
        block = (block_resp.get('data') or {}).get('result') or {}
        if not isinstance(block, dict):
            continue
        ts_hex = str(block.get('timestamp', '0x0'))
        txs = block.get('transactions') if isinstance(block.get('transactions'), list) else []
        try:
            ts = int(ts_hex, 16)
        except ValueError:
            continue
        block_rows.append({'timestamp': ts, 'tx_count': len(txs)})

    if len(block_rows) < 2:
        return {'ok': False, 'error': 'insufficient_block_samples'}

    newest = max(block_rows, key=lambda r: r['timestamp'])
    oldest = min(block_rows, key=lambda r: r['timestamp'])
    elapsed = max(1, newest['timestamp'] - oldest['timestamp'])
    total_tx = sum(max(0, int(r.get('tx_count', 0))) for r in block_rows)
    avg_block_time_s = elapsed / max(len(block_rows) - 1, 1)
    tps = total_tx / elapsed
    blocks_24h = 86400.0 / max(avg_block_time_s, 0.1)
    tx_24h = tps * 86400.0
    return {
        'ok': True,
        'chain': 'ethereum',
        'symbol': 'ETH',
        'source': 'ethereum.publicnode.com',
        'source_url': rpc,
        'last_observed_at': datetime.fromtimestamp(newest['timestamp'], tz=timezone.utc).isoformat(),
        'tx_24h': round(tx_24h, 2),
        'blocks_24h': round(blocks_24h, 2),
        'avg_block_time_s': round(avg_block_time_s, 2),
        'tps': round(tps, 4),
        'sampled_blocks': len(block_rows),
    }


def _fetch_sol_chain_activity() -> dict:
    rpc = 'https://api.mainnet-beta.solana.com'
    perf = _rpc_post_json(
        rpc,
        {
            'jsonrpc': '2.0',
            'id': 1,
            'method': 'getRecentPerformanceSamples',
            'params': [24],
        },
        timeout=5.0,
    )
    if not perf.get('ok'):
        return {'ok': False, 'error': perf.get('error') or 'unavailable'}
    samples = (perf.get('data') or {}).get('result') or []
    if not isinstance(samples, list) or not samples:
        return {'ok': False, 'error': 'no_samples'}

    period_secs = sum(max(0, int(row.get('samplePeriodSecs', 0) or 0)) for row in samples)
    non_vote_tx = sum(max(0, int(row.get('numNonVoteTransactions', 0) or 0)) for row in samples)
    all_tx = sum(max(0, int(row.get('numTransactions', 0) or 0)) for row in samples)
    total_slots = sum(max(0, int(row.get('numSlots', 0) or 0)) for row in samples)
    if period_secs <= 0:
        return {'ok': False, 'error': 'invalid_samples'}

    tps_non_vote = non_vote_tx / period_secs
    tps_all = all_tx / period_secs
    avg_block_time_s = period_secs / max(total_slots, 1)
    blocks_24h = 86400.0 / max(avg_block_time_s, 0.1)
    tx_24h = tps_non_vote * 86400.0
    return {
        'ok': True,
        'chain': 'solana',
        'symbol': 'SOL',
        'source': 'solana-mainnet-rpc',
        'source_url': rpc,
        'last_observed_at': datetime.utcnow().replace(tzinfo=timezone.utc).isoformat(),
        'tx_24h': round(tx_24h, 2),
        'blocks_24h': round(blocks_24h, 2),
        'avg_block_time_s': round(avg_block_time_s, 4),
        'tps': round(tps_non_vote, 4),
        'tps_total': round(tps_all, 4),
        'sample_minutes': int(period_secs / 60),
    }


async def _fetch_firedancer_summary_async(
    ws_url: str = FIREDANCER_WS_URL,
    timeout_s: float = FIREDANCER_WS_TIMEOUT_S,
    max_messages: int = FIREDANCER_WS_MAX_MESSAGES,
) -> dict:
    started = time.time()
    wanted_keys = {
        'version',
        'cluster',
        'identity_key',
        'vote_state',
        'vote_distance',
        'estimated_tps',
        'estimated_slot_duration_nanos',
        'skip_rate',
        'tps_history',
        'live_network_metrics',
        'active_fork_count',
        'schedule_strategy',
    }
    snapshot: dict[str, object] = {}
    errors: list[str] = []

    timeout = aiohttp.ClientTimeout(total=timeout_s)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.ws_connect(
                ws_url,
                heartbeat=15,
                autoping=True,
                max_msg_size=2 ** 20,
            ) as ws:
                await ws.send_str(json.dumps({'topic': 'summary', 'key': 'ping', 'id': 1}))
                # Ask for network/gossip stats explicitly; server may still stream defaults.
                await ws.send_str(json.dumps({'topic': 'gossip', 'key': 'network_stats', 'id': 2}))
                deadline = time.time() + timeout_s
                seen = 0
                while seen < max_messages and time.time() < deadline:
                    seen += 1
                    remaining = max(0.05, deadline - time.time())
                    try:
                        msg = await ws.receive(timeout=min(0.35, remaining))
                    except asyncio.TimeoutError:
                        continue
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        try:
                            row = json.loads(msg.data)
                        except (json.JSONDecodeError, TypeError):
                            continue
                        if not isinstance(row, dict):
                            continue
                        topic = str(row.get('topic', '')).strip().lower()
                        key = str(row.get('key', '')).strip().lower()
                        value = row.get('value')
                        if topic == 'summary' and key in wanted_keys:
                            snapshot[key] = value
                        elif topic == 'gossip' and key == 'network_stats':
                            snapshot['network_stats'] = value
                        if (
                            'estimated_tps' in snapshot
                            and 'estimated_slot_duration_nanos' in snapshot
                            and ('vote_state' in snapshot or 'tps_history' in snapshot)
                        ):
                            break
                    elif msg.type in {aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR}:
                        if msg.type == aiohttp.WSMsgType.ERROR:
                            errors.append('ws_error')
                        break
    except Exception as exc:
        errors.append(str(exc))

    latency_ms = round((time.time() - started) * 1000, 2)
    return {
        'ok': bool(snapshot),
        'latency_ms': latency_ms,
        'data': snapshot,
        'errors': errors,
    }


def _fetch_firedancer_chain_activity() -> dict:
    try:
        payload = asyncio.run(_fetch_firedancer_summary_async())
    except Exception as exc:
        return {
            'ok': False,
            'chain': 'solana',
            'symbol': 'SOL-FD',
            'source': 'firedancer-gui',
            'source_url': FIREDANCER_GUI_URL,
            'error': str(exc),
        }
    if not payload.get('ok'):
        errors = payload.get('errors', []) if isinstance(payload.get('errors'), list) else []
        return {
            'ok': False,
            'chain': 'solana',
            'symbol': 'SOL-FD',
            'source': 'firedancer-gui',
            'source_url': FIREDANCER_GUI_URL,
            'latency_ms': payload.get('latency_ms'),
            'error': '; '.join(str(x) for x in errors if x) or 'no_firedancer_data',
        }

    row = payload.get('data', {}) if isinstance(payload.get('data'), dict) else {}
    estimated_tps = _safe_float(row.get('estimated_tps'), 0.0)
    slot_duration_nanos = _safe_float(row.get('estimated_slot_duration_nanos'), 0.0)
    slot_duration_s = slot_duration_nanos / 1_000_000_000.0 if slot_duration_nanos > 0 else 0.0

    tps_history = row.get('tps_history') if isinstance(row.get('tps_history'), list) else []
    recent_total_tps = 0.0
    recent_non_vote_tps = 0.0
    if tps_history:
        latest = tps_history[0] if isinstance(tps_history[0], (list, tuple)) else []
        if len(latest) >= 4:
            recent_total_tps = _safe_float(latest[0], 0.0)
            recent_non_vote_tps = _safe_float(latest[2], 0.0) + _safe_float(latest[3], 0.0)

    tps = max(estimated_tps, recent_total_tps, recent_non_vote_tps)
    tx_24h = tps * 86400.0
    blocks_24h = (86400.0 / slot_duration_s) if slot_duration_s > 0 else 0.0

    skip_rate_value = row.get('skip_rate')
    if isinstance(skip_rate_value, dict):
        skip_rate = _safe_float(
            skip_rate_value.get('skip_rate')
            or skip_rate_value.get('rate')
            or skip_rate_value.get('value'),
            0.0,
        )
    else:
        skip_rate = _safe_float(skip_rate_value, 0.0)
    skip_rate_pct = skip_rate * 100.0 if 0 <= skip_rate <= 1 else skip_rate

    return {
        'ok': True,
        'chain': 'solana',
        'symbol': 'SOL-FD',
        'source': 'firedancer-gui',
        'source_url': FIREDANCER_GUI_URL,
        'last_observed_at': datetime.utcnow().replace(tzinfo=timezone.utc).isoformat(),
        'tx_24h': round(tx_24h, 2),
        'blocks_24h': round(blocks_24h, 2),
        'avg_block_time_s': round(slot_duration_s, 4) if slot_duration_s > 0 else 0.0,
        'tps': round(tps, 4),
        'estimated_tps': round(estimated_tps, 4),
        'non_vote_tps': round(recent_non_vote_tps, 4),
        'latency_ms': payload.get('latency_ms'),
        'cluster': str(row.get('cluster', 'mainnet-beta')),
        'version': str(row.get('version', 'unknown')),
        'validator_identity': str(row.get('identity_key', '')),
        'vote_state': str(row.get('vote_state', 'unknown')),
        'vote_distance': int(_safe_float(row.get('vote_distance'), 0.0)),
        'schedule_strategy': str(row.get('schedule_strategy', 'unknown')),
        'active_fork_count': int(_safe_float(row.get('active_fork_count'), 0.0)),
        'skip_rate_pct': round(skip_rate_pct, 4),
    }


def _platform_zeitgeist_universe_payload(refresh: bool = False) -> dict:
    cache_key = f"platform_zeitgeist_universe:{int(bool(refresh))}"
    if not refresh:
        cached = get_cached(cache_key, duration=20)
        if cached:
            return cached

    status = _collect_system_status()
    summary = status.get('summary', {}) if isinstance(status.get('summary'), dict) else {}
    intel = _platform_intel_summary_payload(hours=24, limit=80, refresh=refresh)
    superswarm = _platform_superswarm_payload(hours=24, force_refresh=refresh)

    movers = (intel.get('market') or {}).get('movers') if isinstance(intel.get('market'), dict) else []
    movers = movers if isinstance(movers, list) else []
    market_by_symbol = {
        str(row.get('symbol', '')).upper(): _safe_float(row.get('change_24h'), 0.0)
        for row in movers
        if isinstance(row, dict)
    }

    chain_rows = []
    for row in (
        _fetch_btc_chain_activity(),
        _fetch_eth_chain_activity(),
        _fetch_sol_chain_activity(),
        _fetch_firedancer_chain_activity(),
    ):
        if not isinstance(row, dict):
            continue
        if not row.get('ok'):
            chain_rows.append(
                {
                    'symbol': str(row.get('symbol', '')).upper() or 'UNK',
                    'chain': str(row.get('chain', 'unknown')),
                    'available': False,
                    'error': str(row.get('error', 'unavailable')),
                }
            )
            continue

        symbol = str(row.get('symbol', '')).upper()
        tps = _safe_float(row.get('tps'), 0.0)
        tx_24h = _safe_float(row.get('tx_24h'), 0.0)
        speed_score = _clamp(math.log10(max(tps, 0.0001) + 1.0) * 36.0, 0, 100)
        activity_score = _clamp(math.log10(max(tx_24h, 1.0)) * 21.0, 0, 100)
        market_symbol = 'SOL' if symbol == 'SOL-FD' else symbol
        market_change = _safe_float(market_by_symbol.get(market_symbol), 0.0)
        activity_index = round(_clamp((speed_score * 0.52) + (activity_score * 0.40) + (abs(market_change) * 2.6), 0, 100), 2)
        chain_rows.append(
            {
                'symbol': symbol,
                'chain': str(row.get('chain', symbol.lower())),
                'available': True,
                'tps': round(tps, 4),
                'tx_24h': round(tx_24h, 2),
                'blocks_24h': round(_safe_float(row.get('blocks_24h'), 0.0), 2),
                'avg_block_time_s': round(_safe_float(row.get('avg_block_time_s'), 0.0), 4),
                'market_change_24h': round(market_change, 4),
                'speed_score': round(speed_score, 2),
                'activity_score': round(activity_score, 2),
                'activity_index': activity_index,
                'source': str(row.get('source', 'unknown')),
                'source_url': str(row.get('source_url', '')),
                'last_observed_at': _iso_or_default(row.get('last_observed_at')),
                'latency_ms': _safe_float(row.get('latency_ms'), None),
                'cluster': str(row.get('cluster', '')),
                'version': str(row.get('version', '')),
                'vote_state': str(row.get('vote_state', '')),
                'vote_distance': int(_safe_float(row.get('vote_distance'), 0.0)),
                'skip_rate_pct': _safe_float(row.get('skip_rate_pct'), 0.0),
            }
        )

    desired_order = ['BTC', 'ETH', 'SOL', 'SOL-FD']
    chain_rows.sort(key=lambda r: desired_order.index(r.get('symbol')) if r.get('symbol') in desired_order else 99)

    now_utc = datetime.now(timezone.utc)
    quality_issues: list[str] = []
    freshness_seconds: dict[str, float | None] = {}
    stale_threshold_by_symbol = {
        'BTC': 3600.0,
        'ETH': 600.0,
        'SOL': 300.0,
        'SOL-FD': 240.0,
    }
    for row in chain_rows:
        symbol = str(row.get('symbol', 'UNK')).upper()
        if not row.get('available', False):
            quality_issues.append(f'{symbol} unavailable')
            freshness_seconds[symbol] = None
            continue
        ts = _coerce_datetime(row.get('last_observed_at'))
        if ts is None:
            freshness_seconds[symbol] = None
            quality_issues.append(f'{symbol} missing timestamp')
            continue
        age = max(0.0, (now_utc - ts).total_seconds())
        freshness_seconds[symbol] = round(age, 2)
        threshold = stale_threshold_by_symbol.get(symbol, 600.0)
        if age > threshold:
            quality_issues.append(f'{symbol} stale ({int(age)}s)')

    source_efficacy = (superswarm.get('analysis') or {}).get('source_efficacy') if isinstance(superswarm.get('analysis'), dict) else []
    source_efficacy = source_efficacy if isinstance(source_efficacy, list) else []
    source_streams = len(source_efficacy)
    learning_summary = (superswarm.get('analysis') or {}).get('learning_summary') if isinstance(superswarm.get('analysis'), dict) else {}
    learning_summary = learning_summary if isinstance(learning_summary, dict) else {}
    loop = superswarm.get('loop', {}) if isinstance(superswarm.get('loop'), dict) else {}
    superswarm_summary = superswarm.get('summary', {}) if isinstance(superswarm.get('summary'), dict) else {}

    service_healthy = int(summary.get('service_healthy', 0) or 0)
    service_total = int(summary.get('service_total', 0) or 0)
    signals_24h = int(superswarm_summary.get('signals', 0) or 0)
    executions_24h = int(superswarm_summary.get('executions', 0) or 0)
    feed_count = int((intel.get('intel') or {}).get('count', 0) if isinstance(intel.get('intel'), dict) else 0)
    top_categories = (intel.get('intel') or {}).get('top_categories') if isinstance(intel.get('intel'), dict) else []
    top_categories = top_categories if isinstance(top_categories, list) else []

    execution_flow = (superswarm.get('series') or {}).get('execution_flow') if isinstance(superswarm.get('series'), dict) else []
    execution_flow = execution_flow if isinstance(execution_flow, list) else []

    payload = {
        'timestamp': datetime.utcnow().isoformat(),
        'chain_streams': chain_rows,
        'agent_mesh': {
            'active_agents': service_healthy,
            'total_agents': service_total,
            'source_streams': source_streams,
            'openclaw_growth_total': int(learning_summary.get('total', 0) or 0),
            'openclaw_growth_wins': int(learning_summary.get('wins', 0) or 0),
            'openclaw_growth_losses': int(learning_summary.get('losses', 0) or 0),
            'openclaw_growth_win_rate': _safe_float(learning_summary.get('win_rate'), 0.0),
            'full_autonomy_enabled': bool(loop.get('full_autonomy_enabled', False)),
            'memory_enabled': bool(loop.get('memory_enabled', False)),
        },
        'process_streams': {
            'signals_24h': signals_24h,
            'executions_24h': executions_24h,
            'intel_items_24h': feed_count,
            'market_regime': str((intel.get('market') or {}).get('regime_label', 'Unknown')),
            'volatility_score': _safe_float((intel.get('market') or {}).get('volatility_score'), 0.0),
            'top_categories': top_categories[:4],
        },
        'historical': {
            'execution_flow': execution_flow[-24:],
        },
        'quality': {
            'degraded': bool(quality_issues),
            'issue_count': len(quality_issues),
            'issues': quality_issues[:8],
            'freshness_seconds': freshness_seconds,
            'checked_at': datetime.utcnow().isoformat(),
            'firedancer_available': any(
                str(row.get('symbol', '')).upper() == 'SOL-FD' and bool(row.get('available', False))
                for row in chain_rows
            ),
        },
        'sources': {
            'status': '/api/platform/status',
            'intel_summary': '/api/platform/intel-summary',
            'superswarm': '/api/platform/superswarm',
            'btc': 'https://api.blockchair.com/bitcoin/stats',
            'eth': 'https://ethereum.publicnode.com',
            'sol': 'https://api.mainnet-beta.solana.com',
            'firedancer_gui': FIREDANCER_GUI_URL,
            'firedancer_ws': FIREDANCER_WS_URL,
        },
    }
    set_cache(cache_key, payload)
    return payload


def _platform_architecture_telemetry_payload(hours: int = 6, refresh: bool = False) -> dict:
    safe_hours = max(1, min(int(hours or 6), 72))
    cache_key = f"platform_architecture_telemetry:{safe_hours}:{int(bool(refresh))}"
    if not refresh:
        cached = get_cached(cache_key, duration=10)
        if cached:
            return cached

    status = _collect_system_status()
    services = status.get('services', {}) if isinstance(status.get('services'), dict) else {}
    nodes = status.get('nodes', {}) if isinstance(status.get('nodes'), dict) else {}
    summary = status.get('summary', {}) if isinstance(status.get('summary'), dict) else {}
    superswarm = _platform_superswarm_payload(hours=max(4, safe_hours))
    superswarm_summary = superswarm.get('summary', {}) if isinstance(superswarm.get('summary'), dict) else {}
    trades = _fetch_trade_executions(hours=safe_hours, limit=160, include_failed=True)
    trade_rows = trades.get('trades', []) if isinstance(trades.get('trades'), list) else []
    logs = _fetch_logs(hours=safe_hours, limit=240)
    log_rows = logs.get('logs', []) if isinstance(logs.get('logs'), list) else []
    intel = _fetch_intel_feed_payload(limit=40)

    def service_health(name: str) -> tuple[bool | None, str, float | None]:
        row = services.get(name)
        if not isinstance(row, dict):
            return None, 'unknown', None
        healthy = bool(row.get('healthy', False))
        return healthy, ('online' if healthy else 'offline'), _safe_float(row.get('latency_ms'), None)

    def node_health(name: str) -> tuple[bool | None, str, float | None]:
        row = nodes.get(name)
        if not isinstance(row, dict):
            return None, 'unknown', None
        healthy = bool(row.get('healthy', False))
        return healthy, ('online' if healthy else 'offline'), _safe_float(row.get('latency_ms'), None)

    model = [
        ('gateway', 'Gateway', 'cloud', 'ring1', *service_health('gateway')),
        ('alpha', 'Alpha Engine', 'cloud', 'ring1', *service_health('alpha_engine')),
        ('pm_hub', 'PM Hub', 'cloud', 'ring1', *service_health('pm_hub')),
        ('telegram', 'Telegram', 'cloud', 'ring1', *service_health('telegram_bot')),
        ('scout', 'Scout Sandbox', 'support', 'ring2', *service_health('scout_sandbox')),
        ('tho', 'THO Agent', 'support', 'ring2', *service_health('tho_agent')),
        ('blanga', 'Blanga BIS', 'support', 'ring2', None, 'unknown', None),
        ('aster', 'Aster', 'support', 'ring2', None, 'unknown', None),
        ('jobs', 'Unified Jobs', 'support', 'ring2', None, 'unknown', None),
        ('firestore', 'Firestore', 'storage', 'ring2', True, 'online' if db is not None else 'offline', None),
        ('rari1', 'RARI-1', 'edge', 'ring3', *node_health('rari1')),
        ('rari2', 'RARI-2', 'edge', 'ring3', *node_health('rari2')),
        ('windows', 'Windows Lab', 'edge', 'ring3', *node_health('windows')),
        ('macos', 'Commander', 'operator', 'ring3', True, 'online', None),
    ]

    node_payload = []
    for node_id, label, node_type, ring, healthy, state, latency in model:
        node_payload.append(
            {
                'id': node_id,
                'label': label,
                'type': node_type,
                'ring': ring,
                'healthy': healthy,
                'status': state,
                'latency_ms': latency,
            }
        )
    node_health_by_id = {row['id']: row.get('healthy') for row in node_payload}

    signals = int(superswarm_summary.get('signals', 0) or 0)
    executions = int(superswarm_summary.get('executions', 0) or 0)
    if signals == 0:
        signals = sum(
            1 for row in log_rows
            if str((row or {}).get('event_type', '')).strip().lower() in {'signal_received', 'signal_published'}
        )
    if executions == 0:
        executions = sum(1 for row in trade_rows if bool((row or {}).get('executed', False)))

    intel_count = int(intel.get('count', 0) or 0)
    trade_failures = sum(1 for row in trade_rows if not bool((row or {}).get('executed', False)))
    signal_rate = round(signals / max(safe_hours, 1), 2)
    execution_rate = round(executions / max(safe_hours, 1), 2)
    intel_rate = round(intel_count / max(safe_hours, 1), 2)

    fail_rate = trade_failures / max(safe_hours, 1)
    aster_activity = sum(
        1 for row in trade_rows
        if str((row or {}).get('platform', '')).strip().lower() == 'aster'
    )
    edge_rates = {
        'hub_gateway': max(signal_rate * 0.45, 0.01),
        'hub_alpha': max(signal_rate, execution_rate * 0.8, 0.01),
        'hub_pm_hub': intel_rate * 0.35,
        'hub_telegram': (execution_rate * 0.55) + (fail_rate * 0.2),
        'gateway_scout': intel_rate * 0.35,
        'gateway_tho': intel_rate * 0.22,
        'alpha_blanga': intel_rate * 0.18,
        'pm_hub_aster': (aster_activity / max(safe_hours, 1)) if aster_activity else 0.0,
        'telegram_jobs': fail_rate * 0.5,
        'gateway_firestore': (signal_rate * 0.25) + (execution_rate * 0.55),
        'rari1_gateway': 0.0,
        'rari2_gateway': execution_rate * 0.5,
        'windows_gateway': signal_rate * 0.35,
        'macos_gateway': 0.02,
        'alpha_rari2': execution_rate,
    }

    edges = [
        {'id': 'hub_gateway', 'source': 'gateway', 'target': 'hub', 'label': 'Gateway core bus'},
        {'id': 'hub_alpha', 'source': 'alpha', 'target': 'hub', 'label': 'Signal processing'},
        {'id': 'hub_pm_hub', 'source': 'pm_hub', 'target': 'hub', 'label': 'Ops governance'},
        {'id': 'hub_telegram', 'source': 'telegram', 'target': 'hub', 'label': 'Operator updates'},
        {'id': 'gateway_scout', 'source': 'gateway', 'target': 'scout', 'label': 'Research ingress'},
        {'id': 'gateway_tho', 'source': 'gateway', 'target': 'tho', 'label': 'THO handoff'},
        {'id': 'alpha_blanga', 'source': 'alpha', 'target': 'blanga', 'label': 'Intel synthesis'},
        {'id': 'pm_hub_aster', 'source': 'pm_hub', 'target': 'aster', 'label': 'Execution/job orchestration'},
        {'id': 'telegram_jobs', 'source': 'telegram', 'target': 'jobs', 'label': 'Alert jobs'},
        {'id': 'gateway_firestore', 'source': 'gateway', 'target': 'firestore', 'label': 'Persistent telemetry'},
        {'id': 'rari1_gateway', 'source': 'rari1', 'target': 'gateway', 'label': 'Failover canary lane'},
        {'id': 'rari2_gateway', 'source': 'rari2', 'target': 'gateway', 'label': 'Primary execution lane'},
        {'id': 'windows_gateway', 'source': 'windows', 'target': 'gateway', 'label': 'TradingView ingress'},
        {'id': 'macos_gateway', 'source': 'macos', 'target': 'gateway', 'label': 'Operator client'},
        {'id': 'alpha_rari2', 'source': 'alpha', 'target': 'rari2', 'label': 'Execution dispatch'},
    ]

    bottleneck_watch_tph = max(0.0, _safe_float(os.getenv('ARCH_BOTTLENECK_WATCH_TPH'), 0.50))
    bottleneck_steady_tph = max(
        bottleneck_watch_tph + 0.05,
        _safe_float(os.getenv('ARCH_BOTTLENECK_STEADY_TPH'), 1.10),
    )
    conversion_watch_pct = max(0.0, min(100.0, _safe_float(os.getenv('ARCH_CONVERSION_WATCH_PCT'), 55.0)))
    conversion_steady_pct = max(
        conversion_watch_pct + 1.0,
        min(100.0, _safe_float(os.getenv('ARCH_CONVERSION_STEADY_PCT'), 70.0)),
    )

    for edge in edges:
        throughput = round(edge_rates.get(edge['id'], 0.0), 3)
        source_ok = node_health_by_id.get(edge.get('source'), True) is not False
        target_ok = node_health_by_id.get(edge.get('target'), True) is not False
        edge['throughput'] = throughput
        edge['active'] = throughput > 0.15 and source_ok and target_ok
        if not edge['active']:
            edge['severity'] = 'inactive'
        elif throughput < bottleneck_watch_tph:
            edge['severity'] = 'watch'
        elif throughput < bottleneck_steady_tph:
            edge['severity'] = 'steady'
        else:
            edge['severity'] = 'healthy'

    active_edges = [edge for edge in edges if edge.get('active')]
    conversion_rate_raw_pct = round((executions / max(signals, 1)) * 100.0, 2) if signals > 0 else 0.0
    conversion_rate_pct = round(_clamp(conversion_rate_raw_pct, 0.0, 100.0), 2)
    if conversion_rate_pct < conversion_watch_pct:
        conversion_severity = 'watch'
    elif conversion_rate_pct < conversion_steady_pct:
        conversion_severity = 'steady'
    else:
        conversion_severity = 'healthy'

    bottleneck_rows = sorted(
        [edge for edge in active_edges if edge.get('severity') in {'watch', 'steady'}],
        key=lambda row: row.get('throughput', 0.0),
    )
    if not bottleneck_rows:
        bottleneck_rows = sorted(active_edges, key=lambda row: row.get('throughput', 0.0))[:3]
    bottlenecks = [
        {
            'id': row.get('id'),
            'source': row.get('source'),
            'target': row.get('target'),
            'label': row.get('label'),
            'throughput': row.get('throughput', 0.0),
            'severity': row.get('severity', 'steady'),
        }
        for row in bottleneck_rows[:6]
    ]

    topology_nodes_total = len(node_payload)
    topology_nodes_healthy = sum(1 for row in node_payload if row.get('healthy') is True)
    top_events = []
    for row in trade_rows[:5]:
        if not isinstance(row, dict):
            continue
        side = str(row.get('side', '')).upper()
        symbol = str(row.get('symbol', 'UNKNOWN')).upper()
        qty = _safe_float(row.get('filled_quantity'), 0.0)
        price = _safe_float(row.get('avg_price'), 0.0)
        top_events.append(
            {
                'timestamp': _iso_or_default(row.get('timestamp')),
                'type': 'execution' if row.get('executed') else 'execution_reject',
                'summary': f"{symbol} {side} qty={qty:.5f} @ {price:.4f}",
                'status': 'ok' if row.get('executed') else 'warning',
            }
        )

    pipelines = [
        {
            'id': 'signal_pipeline',
            'name': 'Signal Pipeline',
            'status': 'online' if execution_rate > 0 else 'degraded',
            'throughput': execution_rate,
            'hops': ['windows', 'gateway', 'alpha', 'rari2', 'firestore'],
        },
        {
            'id': 'intel_pipeline',
            'name': 'Intelligence Pipeline',
            'status': 'online' if intel_rate > 0 else 'degraded',
            'throughput': intel_rate,
            'hops': ['scout', 'tho', 'blanga', 'alpha', 'gateway'],
        },
        {
            'id': 'ops_pipeline',
            'name': 'Operations Pipeline',
            'status': 'online' if int(summary.get('service_unhealthy', 0) or 0) == 0 else 'degraded',
            'throughput': round(max(signal_rate, intel_rate) * 0.5, 2),
            'hops': ['macos', 'telegram', 'pm_hub', 'jobs', 'firestore'],
        },
    ]

    payload = {
        'timestamp': datetime.utcnow().isoformat(),
        'window_hours': safe_hours,
        'summary': {
            'nodes_total': topology_nodes_total,
            'nodes_healthy': topology_nodes_healthy,
            'active_flows': len(active_edges),
            'signals': signals,
            'executions': executions,
            'intel_items': intel_count,
            'signal_rate': signal_rate,
            'execution_rate': execution_rate,
            'conversion_rate_raw_pct': conversion_rate_raw_pct,
            'conversion_rate_pct': conversion_rate_pct,
            'conversion_severity': conversion_severity,
            'intel_rate': intel_rate,
            'trade_failures': trade_failures,
        },
        'thresholds': {
            'bottleneck_watch_tph': bottleneck_watch_tph,
            'bottleneck_steady_tph': bottleneck_steady_tph,
            'conversion_watch_pct': conversion_watch_pct,
            'conversion_steady_pct': conversion_steady_pct,
        },
        'nodes': node_payload,
        'edges': edges,
        'bottlenecks': bottlenecks,
        'pipelines': pipelines,
        'events': top_events,
        'sources': {
            'status': 'api/platform/status',
            'superswarm': 'api/platform/superswarm',
            'trades': 'api/platform/trades',
            'logs': 'api/platform/logs',
            'intel': 'api/platform/intel-feed',
        },
    }
    set_cache(cache_key, payload)
    return payload


def _platform_architecture_live_payload(hours: int = 24, refresh: bool = False) -> dict:
    """Build an operational digital twin for architecture visualization."""
    safe_hours = max(1, min(int(hours or 24), 168))
    cache_key = f"platform_architecture_live:{safe_hours}:{int(bool(refresh))}"
    if not refresh:
        cached = get_cached(cache_key, duration=15)
        if cached:
            return cached

    status = _collect_system_status()
    org = _platform_organization_payload(refresh=False)
    metrics = _platform_metrics_payload()
    summary = status.get('summary', {}) if isinstance(status.get('summary'), dict) else {}
    services = status.get('services', {}) if isinstance(status.get('services'), dict) else {}
    nodes_status = status.get('nodes', {}) if isinstance(status.get('nodes'), dict) else {}
    monitor = _get_monitor_snapshot()
    contract_count = len(PLATFORM_CONTRACTS)

    owner_by_node = {
        'gateway': 'trading_research',
        'alpha': 'trading_research',
        'rari1': 'infra_research',
        'rari2': 'trading_research',
        'windows': 'infra_research',
        'scout': 'infra_research',
        'tho': 'development',
        'blanga': 'development',
        'pm_hub': 'org_core',
        'telegram': 'org_core',
        'jobs': 'org_core',
        'firestore': 'org_core',
        'macos': 'org_core',
        'aster': 'trading_research',
    }
    role_by_node = {
        'gateway': 'Ingress normalization, risk-gating, and signal fan-out.',
        'alpha': 'Decision engine and policy synthesis for execution intent.',
        'rari1': 'Batch research node and fallback canary execution lane.',
        'rari2': 'Primary execution lane and live strategy runtime.',
        'windows': 'TradingView/desktop alert ingress and local AI test bench.',
        'scout': 'Sandboxed external research collection and context scoring.',
        'tho': 'Client-delivery runtime rail (Project Go Forward).',
        'blanga': 'Client intelligence rail (BIS program).',
        'pm_hub': 'Agentic project governance, org modeling, and delegation.',
        'telegram': 'Operator relay for alerts and control summaries.',
        'jobs': 'Scheduled rollups, digests, and maintenance workflows.',
        'firestore': 'Operational state, logs, and telemetry persistence.',
        'macos': 'Private operator companion surface (read-only telemetry).',
        'aster': 'Secondary exchange lane and venue diversification rail.',
    }
    tech_by_node = {
        'gateway': ['Cloud Run', 'Pub/Sub', 'Webhook'],
        'alpha': ['Cloud Run', 'Python', 'Agent Orchestration'],
        'rari1': ['Raspberry Pi', 'systemd', 'Batch Nodes'],
        'rari2': ['Raspberry Pi', 'systemd', 'Lighter Runtime'],
        'windows': ['Windows', 'TradingView Agent', 'Local GPU Lab'],
        'scout': ['Cloud Run', 'Sandboxed Research'],
        'tho': ['Cloud Run', 'Client Program Runtime'],
        'blanga': ['Cloud Run', 'Client Intelligence Runtime'],
        'pm_hub': ['Cloud Run', 'Agentic PM Hub'],
        'telegram': ['Cloud Run', 'Telegram Bot API'],
        'jobs': ['Cloud Run Jobs', 'Cloud Scheduler'],
        'firestore': ['Firestore'],
        'macos': ['macOS', 'Status Bar Companion'],
        'aster': ['Exchange Bridge', 'Execution Rail'],
    }

    rings = {
        'ring1': {'id': 'ring1', 'label': 'Core Orchestration Layer', 'description': 'Decision, governance, and operator relay control loop.'},
        'ring2': {'id': 'ring2', 'label': 'Support & State Layer', 'description': 'Research augmentation, client rails, and persistent state.'},
        'ring3': {'id': 'ring3', 'label': 'Edge Execution Layer', 'description': 'Runtime execution, ingestion edges, and operator clients.'},
    }

    node_model = [
        ('gateway', 'Ingress Bus', 'cloud', 'ring1', 'gateway'),
        ('alpha', 'Decision Engine', 'cloud', 'ring1', 'alpha_engine'),
        ('pm_hub', 'Ops Orchestrator', 'cloud', 'ring1', 'pm_hub'),
        ('telegram', 'Operator Relay', 'cloud', 'ring1', 'telegram_bot'),
        ('scout', 'Research Intake', 'support', 'ring2', 'scout_sandbox'),
        ('tho', 'Signal Refinery', 'support', 'ring2', 'tho_agent'),
        ('blanga', 'Context Layer', 'support', 'ring2', None),
        ('aster', 'Reserve Venue', 'support', 'ring2', None),
        ('jobs', 'Batch Rail', 'support', 'ring2', None),
        ('firestore', 'State Store', 'storage', 'ring2', 'firestore'),
        ('rari1', 'RARI-1', 'edge', 'ring3', 'rari1'),
        ('rari2', 'RARI-2', 'edge', 'ring3', 'rari2'),
        ('windows', 'Windows Lab', 'edge', 'ring3', 'windows'),
        ('macos', 'Operator Console', 'operator', 'ring3', None),
    ]

    def _resolve_health(source_key: str | None):
        if source_key == 'firestore':
            ok = db is not None
            return ok, 'online' if ok else 'offline', None
        if source_key in services:
            row = services.get(source_key) or {}
            return bool(row.get('healthy', False)), str(row.get('status', 'unknown')), row.get('latency_ms')
        if source_key in nodes_status:
            row = nodes_status.get(source_key) or {}
            return bool(row.get('healthy', False)), str(row.get('status', 'unknown')), row.get('latency_ms')
        return None, 'unknown', None

    nodes = []
    for node_id, label, node_type, ring, source_key in node_model:
        healthy, node_status, latency = _resolve_health(source_key)
        if node_id == 'macos' and healthy is None:
            healthy, node_status = True, 'online'
        nodes.append(
            {
                'id': node_id,
                'label': label,
                'ring': ring,
                'type': node_type,
                'healthy': healthy,
                'status': node_status,
                'latency_ms': latency,
                'owner_department': owner_by_node.get(node_id, 'org_core'),
                'responsibility': role_by_node.get(node_id, 'Operational platform component.'),
                'technologies': tech_by_node.get(node_id, []),
            }
        )

    node_by_id = {row.get('id'): row for row in nodes}

    edge_protocol = {
        'gateway_firestore': 'HTTPS/SDK',
        'hub_gateway': 'HTTPS',
        'hub_alpha': 'HTTP internal',
        'hub_pm_hub': 'HTTP internal',
        'hub_telegram': 'HTTPS',
        'windows_gateway': 'Webhook',
        'rari2_gateway': 'Pub/Sub + HTTPS',
        'alpha_rari2': 'Pub/Sub dispatch',
        'telegram_jobs': 'Scheduler trigger',
    }
    edge_model = [
        ('hub_gateway', 'gateway', 'hub', 'Gateway core bus'),
        ('hub_alpha', 'alpha', 'hub', 'Signal processing'),
        ('hub_pm_hub', 'pm_hub', 'hub', 'Ops governance'),
        ('hub_telegram', 'telegram', 'hub', 'Operator updates'),
        ('gateway_scout', 'gateway', 'scout', 'Research ingress'),
        ('gateway_tho', 'gateway', 'tho', 'THO handoff'),
        ('alpha_blanga', 'alpha', 'blanga', 'Intel synthesis'),
        ('pm_hub_aster', 'pm_hub', 'aster', 'Execution/job orchestration'),
        ('telegram_jobs', 'telegram', 'jobs', 'Alert jobs'),
        ('gateway_firestore', 'gateway', 'firestore', 'Persistent telemetry'),
        ('rari1_gateway', 'rari1', 'gateway', 'Failover canary lane'),
        ('rari2_gateway', 'rari2', 'gateway', 'Primary execution lane'),
        ('windows_gateway', 'windows', 'gateway', 'TradingView ingress'),
        ('macos_gateway', 'macos', 'gateway', 'Operator client'),
        ('alpha_rari2', 'alpha', 'rari2', 'Execution dispatch'),
    ]
    trade_metrics = metrics.get('trading', {}) if isinstance(metrics.get('trading'), dict) else {}
    signals_rate = _safe_float((trade_metrics.get('signals_total', 0) or 0) / max(safe_hours, 1), 0.0)
    execution_rate = _safe_float((trade_metrics.get('trades_count', 0) or 0) / max(safe_hours, 1), 0.0)

    edges = []
    for edge_id, source, target, label in edge_model:
        source_node = node_by_id.get(source, {})
        target_node = node_by_id.get(target, {}) if target != 'hub' else {'healthy': True}
        source_ok = source_node.get('healthy') is not False
        target_ok = target_node.get('healthy') is not False
        active = bool(source_ok and target_ok)
        base_tp = 0.05
        if edge_id in {'windows_gateway', 'hub_gateway', 'hub_alpha'}:
            base_tp = max(signals_rate, 0.05)
        elif edge_id in {'alpha_rari2', 'rari2_gateway', 'gateway_firestore'}:
            base_tp = max(execution_rate, 0.05)
        throughput = round(base_tp if active else 0.0, 3)
        edges.append(
            {
                'id': edge_id,
                'source': source,
                'target': target,
                'label': label,
                'active': active,
                'severity': ('healthy' if active else 'inactive'),
                'throughput_per_hour': throughput,
                'protocol': edge_protocol.get(edge_id, 'internal'),
            }
        )

    layers = []
    for ring_id, meta in rings.items():
        ring_nodes = [n for n in nodes if n.get('ring') == ring_id]
        healthy = sum(1 for n in ring_nodes if n.get('healthy') is True)
        layers.append(
            {
                **meta,
                'node_ids': [n.get('id') for n in ring_nodes],
                'healthy': healthy,
                'total': len(ring_nodes),
                'status': 'healthy' if healthy == len(ring_nodes) and ring_nodes else ('degraded' if ring_nodes else 'unknown'),
            }
        )

    op_sequences = [
        {
            'id': 'signal_to_execution',
            'name': 'Signal Ingest → Risk Gate → Execution',
            'purpose': 'Convert external market alerts into risk-gated execution decisions.',
            'steps': ['windows', 'gateway', 'alpha', 'rari2', 'firestore'],
        },
        {
            'id': 'research_to_intel',
            'name': 'Research Intake → Intelligence Context',
            'purpose': 'Ingest and score research into actionable intelligence context.',
            'steps': ['scout', 'alpha', 'pm_hub', 'firestore'],
        },
        {
            'id': 'operator_governance',
            'name': 'Operator Governance Loop',
            'purpose': 'Surface health/ops telemetry for decision-making and controlled rollout.',
            'steps': ['macos', 'pm_hub', 'telegram', 'jobs', 'firestore'],
        },
    ]
    sequences = []
    for seq in op_sequences:
        sequence_steps = []
        degraded = False
        for idx, node_id in enumerate(seq.get('steps', []), start=1):
            node = node_by_id.get(node_id, {})
            healthy = node.get('healthy')
            if healthy is False:
                degraded = True
            sequence_steps.append(
                {
                    'order': idx,
                    'node_id': node_id,
                    'node_label': node.get('label', node_id),
                    'healthy': healthy,
                    'status': node.get('status', 'unknown'),
                    'explanation': role_by_node.get(node_id, 'Operational step'),
                }
            )
        sequences.append(
            {
                'id': seq.get('id'),
                'name': seq.get('name'),
                'purpose': seq.get('purpose'),
                'status': 'degraded' if degraded else 'healthy',
                'steps': sequence_steps,
            }
        )

    departments = ORG_MODEL.get('departments', []) if isinstance(ORG_MODEL.get('departments'), list) else []
    delegation = []
    for dept in departments:
        if not isinstance(dept, dict):
            continue
        dept_id = str(dept.get('id', '')).strip()
        owned_nodes = [n for n in nodes if n.get('owner_department') == dept_id]
        healthy_owned = sum(1 for n in owned_nodes if n.get('healthy') is True)
        delegation.append(
            {
                'department_id': dept_id,
                'department_name': dept.get('name', dept_id),
                'focus': dept.get('focus', ''),
                'systems': dept.get('systems', []),
                'owned_nodes': [n.get('id') for n in owned_nodes],
                'healthy_nodes': healthy_owned,
                'total_nodes': len(owned_nodes),
                'status': (
                    'healthy'
                    if not owned_nodes or healthy_owned == len(owned_nodes)
                    else 'degraded'
                ),
            }
        )

    unhealthy_nodes = [n for n in nodes if n.get('healthy') is False]
    inactive_critical = [
        e for e in edges
        if e.get('id') in {'windows_gateway', 'rari2_gateway', 'alpha_rari2', 'hub_alpha'} and not e.get('active', False)
    ]
    degraded_sequences = [s for s in sequences if s.get('status') != 'healthy']
    blockers = []
    service_unhealthy = int(summary.get('service_unhealthy', 0) or 0)
    node_unhealthy = int(summary.get('node_unhealthy', 0) or 0)
    if service_unhealthy > 0:
        blockers.append({'gate': 'cloud_services', 'message': f'{service_unhealthy} cloud services are unhealthy.'})
    if node_unhealthy > 0:
        blockers.append({'gate': 'edge_nodes', 'message': f'{node_unhealthy} edge nodes are unhealthy.'})
    if monitor.get('available'):
        by_category = monitor.get('by_category', {}) if isinstance(monitor.get('by_category'), dict) else {}
        for row in by_category.get('windows', []):
            if isinstance(row, dict) and not bool(row.get('healthy', False)):
                blockers.append(
                    {
                        'gate': row.get('name', 'windows_edge'),
                        'message': row.get('error') or 'Windows edge component degraded.',
                    }
                )

    gaps = []
    for node in unhealthy_nodes[:8]:
        gaps.append(
            {
                'type': 'node_unhealthy',
                'severity': 'high',
                'component': node.get('id'),
                'message': f"{node.get('label')} reports {node.get('status', 'degraded')}.",
            }
        )
    for edge in inactive_critical[:6]:
        gaps.append(
            {
                'type': 'critical_flow_inactive',
                'severity': 'high',
                'component': edge.get('id'),
                'message': f"{edge.get('label')} is inactive ({edge.get('throughput_per_hour', 0):.2f}/h).",
            }
        )
    for seq in degraded_sequences[:4]:
        gaps.append(
            {
                'type': 'sequence_degraded',
                'severity': 'medium',
                'component': seq.get('id'),
                'message': f"{seq.get('name')} has one or more unhealthy steps.",
            }
        )
    for blk in blockers[:4]:
        if isinstance(blk, dict):
            gaps.append(
                {
                    'type': 'readiness_blocker',
                    'severity': 'high',
                    'component': blk.get('gate') or blk.get('name') or 'readiness',
                    'message': blk.get('message') or blk.get('reason') or 'Readiness blocker active.',
                }
            )

    health = {
        'working_nodes': [n.get('id') for n in nodes if n.get('healthy') is True],
        'degraded_nodes': [n.get('id') for n in nodes if n.get('healthy') is False],
        'active_edges': [e.get('id') for e in edges if e.get('active') is True],
        'inactive_edges': [e.get('id') for e in edges if e.get('active') is False],
        'gaps_total': len(gaps),
    }

    payload = {
        'timestamp': datetime.utcnow().isoformat(),
        'window_hours': safe_hours,
        'hierarchy': {
            'organization': ORG_MODEL,
            'layers': layers,
        },
        'nodes': nodes,
        'edges': edges,
        'sequences': sequences,
        'delegation': delegation,
        'health': health,
        'gaps': gaps,
        'sources': {
            'status': 'api/platform/status',
            'architecture_telemetry': 'api/platform/architecture-telemetry',
            'organization': 'api/platform/organization',
            'readiness': 'api/platform/readiness',
            'contracts': 'api/platform/contracts',
        },
        'counts': {
            'nodes': len(nodes),
            'edges': len(edges),
            'departments': len(delegation),
            'sequences': len(sequences),
            'contracts': int(contract_count),
        },
    }
    set_cache(cache_key, payload)
    return payload


def _load_bottleneck_digest_state() -> dict:
    if db is None:
        return {}
    try:
        snap = db.collection(BOTTLENECK_DIGEST_COLLECTION).document(BOTTLENECK_DIGEST_DOC_ID).get()
        if not snap.exists:
            return {}
        data = snap.to_dict() or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_bottleneck_digest_state(payload: dict) -> dict:
    if db is None:
        return {'written': False, 'error': 'db_unavailable'}
    try:
        db.collection(BOTTLENECK_DIGEST_COLLECTION).document(BOTTLENECK_DIGEST_DOC_ID).set(payload, merge=True)
        return {'written': True}
    except Exception as exc:
        return {'written': False, 'error': str(exc)}


def _load_strategy_ops_digest_state() -> dict:
    if db is None:
        return {}
    try:
        snap = db.collection(BOTTLENECK_DIGEST_COLLECTION).document(STRATEGY_OPS_DIGEST_DOC_ID).get()
        if not snap.exists:
            return {}
        data = snap.to_dict() or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_strategy_ops_digest_state(payload: dict) -> dict:
    if db is None:
        return {'written': False, 'error': 'db_unavailable'}
    try:
        db.collection(BOTTLENECK_DIGEST_COLLECTION).document(STRATEGY_OPS_DIGEST_DOC_ID).set(payload, merge=True)
        return {'written': True}
    except Exception as exc:
        return {'written': False, 'error': str(exc)}


def _build_strategy_ops_state_payload(
    *,
    days: int,
    scorecard: dict,
    reject_tax: dict,
    assessment: dict,
    operator_brief: dict,
    decision: dict,
    attribution: dict,
    data_quality: dict,
) -> dict:
    ranked = scorecard.get('ranked', []) if isinstance(scorecard.get('ranked'), list) else []
    top_lanes = ranked[:5] if isinstance(ranked, list) else []
    attr_summary = attribution.get('summary', {}) if isinstance(attribution.get('summary'), dict) else {}
    attr_windows = attribution.get('windows', {}) if isinstance(attribution.get('windows'), dict) else {}
    return {
        'updated_at': datetime.utcnow().isoformat(),
        'window_days': max(1, int(days or 7)),
        'assessment': assessment,
        'operator_brief': operator_brief,
        'decision': decision,
        'scorecard_totals': scorecard.get('totals', {}),
        'top_lanes': top_lanes,
        'reject_tax': reject_tax,
        'attribution_summary': {
            'sample_size': int(attr_summary.get('sample_size', 0) or 0),
            'fill_rate_pct': float(attr_summary.get('fill_rate_pct', 0.0) or 0.0),
            'reject_tax_pct': float(attr_summary.get('reject_tax_pct', 0.0) or 0.0),
            'hard_fail_pct': float(attr_summary.get('hard_fail_pct', 0.0) or 0.0),
            'net_pnl_after_fees_usd': float(attr_summary.get('net_pnl_after_fees_usd', 0.0) or 0.0),
            'latest_signal_at': attr_summary.get('latest_signal_at'),
            'windows': {
                '1h': attr_windows.get('1h', {}),
                '6h': attr_windows.get('6h', {}),
                '24h': attr_windows.get('24h', {}),
            },
        },
        'data_quality': data_quality,
    }


def _save_strategy_ops_snapshot(payload: dict, keep_history: bool = True) -> dict:
    if db is None:
        return {'written': False, 'error': 'db_unavailable'}
    now_utc = datetime.now(timezone.utc)
    latest_payload = {
        **payload,
        'updated_at': now_utc.isoformat(),
    }
    written_docs = []
    try:
        db.collection(STRATEGY_OPS_SNAPSHOTS_COLLECTION).document('latest').set(latest_payload, merge=True)
        written_docs.append('latest')
        if keep_history:
            doc_id = now_utc.strftime('%Y%m%dT%H%M%SZ')
            db.collection(STRATEGY_OPS_SNAPSHOTS_COLLECTION).document(doc_id).set(latest_payload, merge=False)
            written_docs.append(doc_id)
        return {'written': True, 'documents': written_docs}
    except Exception as exc:
        return {'written': False, 'error': str(exc), 'documents': written_docs}


def _tg_escape(value) -> str:
    text = str(value or '')
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _build_strategy_ops_digest_message(
    scorecard: dict,
    reject_tax: dict,
    assessment: dict,
    operator_brief: dict | None = None,
    decision: dict | None = None,
    data_quality: dict | None = None,
) -> tuple[str, str, bool]:
    totals = scorecard.get('totals', {}) if isinstance(scorecard.get('totals'), dict) else {}
    ranked = scorecard.get('ranked', []) if isinstance(scorecard.get('ranked'), list) else []
    window = scorecard.get('window', {}) if isinstance(scorecard.get('window'), dict) else {}
    operator_brief = operator_brief if isinstance(operator_brief, dict) else {}
    decision = decision if isinstance(decision, dict) else {}
    data_quality = data_quality if isinstance(data_quality, dict) else {}
    days = int(window.get('days', 7) or 7)
    lanes = int(totals.get('lanes', 0) or 0)
    sample_size = int(totals.get('sample_size', 0) or 0)
    fill_pct = float(totals.get('filled_success_pct', 0.0) or 0.0)
    reject_pct = float(reject_tax.get('reject_tax_pct', totals.get('reject_tax_pct', 0.0)) or 0.0)
    hard_fail_pct = float(reject_tax.get('hard_fail_pct', totals.get('hard_fail_pct', 0.0)) or 0.0)
    net_pnl = float(totals.get('net_pnl_after_fees_usd', totals.get('net_realized_pnl_usd', 0.0)) or 0.0)
    max_drawdown = float(totals.get('max_drawdown_pct', 0.0) or 0.0)
    max_drawdown_usd = float(totals.get('max_drawdown_usd', 0.0) or 0.0)
    ev_error = float(totals.get('expected_value_error_pct', 0.0) or 0.0)
    decision_label = str(decision.get('label', operator_brief.get('label', assessment.get('label', 'NO-GO')))).upper()
    decision_go = bool(decision.get('go', operator_brief.get('go', assessment.get('go', False))))
    blocker_rows = decision.get('reasons', []) if isinstance(decision.get('reasons'), list) else []
    if not blocker_rows:
        blocker_rows = operator_brief.get('hard_blockers', []) if isinstance(operator_brief.get('hard_blockers'), list) else []
    action_rows = operator_brief.get('top_actions', []) if isinstance(operator_brief.get('top_actions'), list) else []
    confidence_score = float(decision.get('confidence_score', operator_brief.get('confidence_score', 0.0)) or 0.0)
    confidence_multiplier = float(
        decision.get('confidence_multiplier', operator_brief.get('confidence_multiplier', 1.0)) or 1.0
    )
    degraded_sources = data_quality.get('degraded_sources', []) if isinstance(data_quality.get('degraded_sources'), list) else []

    lines = [
        '📈 <b>Sapphire Strategy Ops Digest</b>',
        f"Window: last <b>{days}d</b> • Samples: <b>{sample_size}</b> • Lanes: <b>{lanes}</b>",
        (
            f"Operator: <b>{'🟢 GO' if decision_go else '🔴 NO-GO'}</b> • "
            f"Fill {fill_pct:.1f}% • Reject {reject_pct:.1f}% • HardFail {hard_fail_pct:.1f}%"
        ),
        f"Net PnL (after fees): <b>{net_pnl:+.4f}</b>",
        f"Model error {ev_error:.3f}% • Max DD ${max_drawdown_usd:.2f} ({max_drawdown:.2f}%)",
        f"Confidence: {confidence_score:.1f}/100 (x{confidence_multiplier:.2f})",
    ]
    why_now = str(operator_brief.get('why_this_matters_now', '')).strip()
    if not why_now:
        why_now = str(decision.get('why_this_matters_now', '')).strip()
    if why_now:
        lines.append(f"Why now: {_tg_escape(why_now)}")

    reasons = blocker_rows or (assessment.get('reasons') or [])
    if reasons:
        lines.append(f"Blockers: {_tg_escape('; '.join(str(r) for r in reasons[:3]))}")
    if bool(decision.get('diverged', False)):
        source = str(decision.get('source', 'operator_brief')).replace('_', ' ')
        assess_label = str(decision.get('assessment_label', assessment.get('label', 'NO-GO'))).upper()
        lines.append(f"Decision source: <b>{_tg_escape(source)}</b> (assessment={_tg_escape(assess_label)})")

    top_reasons = reject_tax.get('top_reasons', []) if isinstance(reject_tax.get('top_reasons'), list) else []
    if top_reasons:
        top = top_reasons[0] or {}
        if top.get('reason'):
            lines.append(
                f"Top Reject Reason: <b>{_tg_escape(top.get('reason'))}</b> (n={int(top.get('count', 0) or 0)})"
            )
    if degraded_sources:
        lines.append(f"Data quality degraded: {_tg_escape(', '.join(degraded_sources[:3]))}")
    if action_rows:
        lines.append('<b>Top Actions</b>')
        for item in action_rows[:3]:
            prio = str(item.get('priority', 'P1')).strip().upper()
            title = str(item.get('title', 'Action')).strip()
            lines.append(f"• [{_tg_escape(prio)}] {_tg_escape(title)}")

    focus_rows = ranked[:4]
    if focus_rows:
        lines.append('')
        lines.append('<b>Top Lanes</b>')
        for row in focus_rows:
            lane = f"{row.get('strategy', 'unknown')}@{row.get('timeframe', 'unknown')}"
            lines.append(
                "• "
                f"{_tg_escape(lane)} | score {float(row.get('score', 0.0) or 0.0):+.2f} | "
                f"fill {float(row.get('filled_success_pct', 0.0) or 0.0):.1f}% | "
                f"reject {float(row.get('reject_tax_pct', 0.0) or 0.0):.1f}% | "
                f"PnL {float(row.get('net_realized_pnl_usd', 0.0) or 0.0):+.3f} | "
                f"<b>{_tg_escape(row.get('recommendation', 'monitor').upper())}</b>"
            )

    signature_payload = {
        'label': decision_label,
        'go': decision_go,
        'sample': sample_size,
        'reject': round(reject_pct, 2),
        'hard_fail': round(hard_fail_pct, 2),
        'pnl_after_fees': round(net_pnl, 4),
        'max_drawdown_pct': round(max_drawdown, 3),
        'max_drawdown_usd': round(max_drawdown_usd, 4),
        'expected_value_error_pct': round(ev_error, 4),
        'top_lanes': [
            {
                'lane': f"{row.get('strategy', 'unknown')}@{row.get('timeframe', 'unknown')}",
                'score': round(float(row.get('score', 0.0) or 0.0), 3),
                'recommendation': str(row.get('recommendation', 'monitor')),
            }
            for row in focus_rows
        ],
        'blockers': [str(r) for r in reasons[:4]],
        'actions': [str((row or {}).get('title', '')) for row in action_rows[:3]],
        'degraded_sources': [str(src) for src in degraded_sources[:3]],
    }
    signature = hashlib.sha256(str(signature_payload).encode('utf-8')).hexdigest()

    promote_candidates = int(assessment.get('promote_candidates', 0) or 0)
    should_send = (
        not decision_go
        or promote_candidates > 0
        or reject_pct >= float(os.getenv('STRATEGY_OPS_DIGEST_REJECT_ALERT_PCT', '65') or 65.0)
        or hard_fail_pct >= float(os.getenv('STRATEGY_OPS_DIGEST_HARD_FAIL_ALERT_PCT', '10') or 10.0)
    )
    return '\n'.join(lines), signature, bool(should_send)


def _build_bottleneck_digest_message(telemetry: dict, brief: dict) -> tuple[str, str, bool]:
    summary = telemetry.get('summary', {}) if isinstance(telemetry.get('summary'), dict) else {}
    thresholds = telemetry.get('thresholds', {}) if isinstance(telemetry.get('thresholds'), dict) else {}
    bottlenecks = telemetry.get('bottlenecks', []) if isinstance(telemetry.get('bottlenecks'), list) else []
    brief_summary = brief.get('summary', {}) if isinstance(brief.get('summary'), dict) else {}

    signals = int(summary.get('signals', 0) or 0)
    executions = int(summary.get('executions', 0) or 0)
    conversion = _clamp(_safe_float(summary.get('conversion_rate_pct'), 0.0), 0.0, 100.0)
    conversion_sev = str(summary.get('conversion_severity', 'steady')).lower()
    risk_state = str(brief_summary.get('risk_state', 'stable')).upper()

    watch_edges = [row for row in bottlenecks if str((row or {}).get('severity', '')).lower() == 'watch']
    steady_edges = [row for row in bottlenecks if str((row or {}).get('severity', '')).lower() == 'steady']

    lines = [
        '⚙️ <b>Sapphire Bottleneck Digest</b>',
        f"Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC",
        f'Conversion: <b>{conversion:.1f}%</b> ({conversion_sev.upper()}) • {executions}/{signals} executions/signals',
        f'Risk State: <b>{risk_state}</b>',
    ]

    if watch_edges:
        lines.append('')
        lines.append('🚨 <b>Watch Lanes</b>')
        for row in watch_edges[:5]:
            src = str(row.get('source', '--')).replace('_', ' ').title()
            tgt = str(row.get('target', '--')).replace('_', ' ').title()
            tph = _safe_float(row.get('throughput'), 0.0)
            label = str(row.get('label', 'Flow lane'))
            lines.append(f'• {src} → {tgt}: <b>{tph:.2f}/h</b> ({label})')
    elif steady_edges:
        lines.append('')
        lines.append('🟡 <b>Steady Lanes</b>')
        for row in steady_edges[:4]:
            src = str(row.get('source', '--')).replace('_', ' ').title()
            tgt = str(row.get('target', '--')).replace('_', ' ').title()
            tph = _safe_float(row.get('throughput'), 0.0)
            lines.append(f'• {src} → {tgt}: <b>{tph:.2f}/h</b>')
    else:
        lines.append('')
        lines.append('✅ No active watch bottlenecks in current telemetry window.')

    lines.append('')
    lines.append(
        'Thresholds: '
        f"lane watch&lt;{_safe_float(thresholds.get('bottleneck_watch_tph'), 0.5):.2f}/h, "
        f"lane steady&lt;{_safe_float(thresholds.get('bottleneck_steady_tph'), 1.1):.2f}/h, "
        f"conversion watch&lt;{_safe_float(thresholds.get('conversion_watch_pct'), 55.0):.1f}%"
    )

    signature_payload = {
        'watch': [row.get('id') for row in watch_edges[:6]],
        'steady': [row.get('id') for row in steady_edges[:6]],
        'conversion_sev': conversion_sev,
        'conversion': round(conversion, 2),
        'risk_state': risk_state,
    }
    signature = hashlib.sha256(
        str(signature_payload).encode('utf-8')
    ).hexdigest()
    should_send = bool(watch_edges) or conversion_sev == 'watch'
    return '\n'.join(lines), signature, should_send


def _send_telegram_digest(token: str, chat_id: str, message: str) -> dict:
    url = f'https://api.telegram.org/bot{token}/sendMessage'
    payload = {
        'chat_id': chat_id,
        'text': message,
        'parse_mode': 'HTML',
        'disable_web_page_preview': True,
    }
    resp = requests.post(url, json=payload, timeout=15)
    resp.raise_for_status()
    try:
        data = resp.json()
        return data if isinstance(data, dict) else {'ok': True}
    except Exception:
        return {'ok': True}


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
        'status': _public_status_payload(status_data),
        'windows_lab': _fetch_windows_lab_payload(),
    }
    set_cache('platform_metrics', payload)
    return payload


def _platform_strategy_ops_payload(days: int = 7, refresh: bool = False):
    safe_days = max(1, min(int(days or 7), 30))
    cache_key = f'platform_strategy_ops_{safe_days}'
    if not refresh:
        cached = get_cached(cache_key, duration=30)
        if cached:
            return cached

    scorecard = _build_strategy_scorecard(days=safe_days, platform='lighter', limit=1800)
    reject_tax = _fetch_reject_tax_metrics(hours=max(24, safe_days * 24), limit=3000)
    assessment = _build_strategy_ops_assessment(scorecard=scorecard, reject_tax=reject_tax)
    attribution = _build_signal_outcome_attribution(days=safe_days, platform='lighter', limit=2200)
    data_quality = _build_data_quality_snapshot(attribution=attribution)
    operator_brief = _build_operator_decision_brief(
        scorecard=scorecard,
        reject_tax=reject_tax,
        assessment=assessment,
        attribution=attribution,
        data_quality=data_quality,
    )
    decision = _resolve_strategy_ops_decision(
        assessment=assessment,
        operator_brief=operator_brief,
        data_quality=data_quality,
    )

    payload = {
        'timestamp': datetime.utcnow().isoformat(),
        'window_days': safe_days,
        'scorecard': scorecard,
        'reject_tax': reject_tax,
        'assessment': assessment,
        'decision': decision,
        'attribution': attribution,
        'data_quality': data_quality,
        'operator_brief': operator_brief,
    }
    set_cache(cache_key, payload)
    return payload


def _platform_go_no_go_brief_payload(days: int = 7, refresh: bool = False):
    safe_days = max(1, min(int(days or 7), 30))
    cache_key = f'platform_go_no_go_brief_{safe_days}'
    if not refresh:
        cached = get_cached(cache_key, duration=20)
        if cached:
            return cached

    ops_payload = _platform_strategy_ops_payload(days=safe_days, refresh=refresh)
    payload = _build_go_no_go_brief_payload(
        ops_payload=ops_payload,
        window_days=safe_days,
        timestamp=datetime.utcnow().isoformat(),
    )
    set_cache(cache_key, payload)
    return payload


def _librarian_extract_terms(query: str) -> set[str]:
    raw = str(query or '').strip().lower()
    if not raw:
        return set()
    parts = [tok.strip() for tok in re.split(r'[^a-zA-Z0-9_@.-]+', raw) if tok.strip()]
    stop = {
        'the', 'and', 'for', 'with', 'from', 'that', 'this', 'into', 'over',
        'when', 'then', 'our', 'your', 'you', 'are', 'was', 'were', 'have',
        'has', 'had', 'risk', 'trading', 'trade', 'market', 'crypto', 'agent',
    }
    return {p for p in parts if len(p) >= 2 and p not in stop}


def _librarian_normalize_symbol(value: str) -> str:
    sym = str(value or '').strip().upper()
    if not sym:
        return ''
    for suffix in ('/USDT', '/USD', 'USDT', 'USD', '-PERP'):
        if sym.endswith(suffix):
            sym = sym[: -len(suffix)]
    return sym.strip()


def _librarian_build_local_candidates(hours: int) -> list[dict]:
    candidates: list[dict] = []
    now_iso = datetime.now(timezone.utc).isoformat()

    ops_state = _load_strategy_ops_digest_state()
    top_lanes = ops_state.get('top_lanes', []) if isinstance(ops_state.get('top_lanes'), list) else []
    if not top_lanes:
        days = max(1, int(round(max(24, hours) / 24.0)))
        scorecard = _platform_strategy_ops_payload(days=min(days, 14), refresh=False).get('scorecard', {})
        top_lanes = scorecard.get('ranked', []) if isinstance(scorecard.get('ranked'), list) else []
    ops_ts = _iso_or_default(ops_state.get('updated_at') if isinstance(ops_state, dict) else None, now_iso)

    for idx, row in enumerate(top_lanes[:10]):
        if not isinstance(row, dict):
            continue
        strategy = str(row.get('strategy', 'unknown')).strip().lower() or 'unknown'
        timeframe = str(row.get('timeframe', 'unknown')).strip().lower() or 'unknown'
        rec = str(row.get('recommendation', 'monitor')).strip().lower() or 'monitor'
        sample = int(row.get('sample_size', 0) or 0)
        fill_pct = float(row.get('filled_success_pct', 0.0) or 0.0)
        reject_pct = float(row.get('reject_tax_pct', 0.0) or 0.0)
        pnl = float(row.get('net_realized_pnl_usd', 0.0) or 0.0)
        score = float(row.get('score', 0.0) or 0.0)
        summary = (
            f"{strategy}@{timeframe} score {score:+.2f}, fill {fill_pct:.1f}%, "
            f"reject {reject_pct:.1f}%, pnl {pnl:+.4f}, sample {sample}, rec {rec}"
        )
        candidates.append(
            {
                'id': f'lane-{idx}-{strategy}-{timeframe}',
                'type': 'strategy_lane',
                'title': f'Lane {strategy}@{timeframe}',
                'summary': summary,
                'text': summary,
                'symbols': [],
                'timestamp': ops_ts,
                'metadata': {
                    'strategy': strategy,
                    'timeframe': timeframe,
                    'recommendation': rec,
                    'score': score,
                },
            }
        )

    reject_tax = _fetch_reject_tax_metrics(hours=max(24, hours), limit=2000)
    top_reasons = reject_tax.get('top_reasons', []) if isinstance(reject_tax.get('top_reasons'), list) else []
    for idx, row in enumerate(top_reasons[:6]):
        if not isinstance(row, dict):
            continue
        reason = str(row.get('reason', 'unknown')).strip()
        count = int(row.get('count', 0) or 0)
        share = float(row.get('share_pct', 0.0) or 0.0)
        summary = f"Reject reason {reason}: n={count}, share={share:.1f}%"
        candidates.append(
            {
                'id': f'reject-{idx}',
                'type': 'reject_reason',
                'title': f'Reject Tax: {reason}',
                'summary': summary,
                'text': summary,
                'symbols': [],
                'timestamp': now_iso,
                'metadata': {'reason': reason, 'count': count, 'share_pct': share},
            }
        )

    intel_summary = _platform_intel_summary_payload(hours=max(12, hours), limit=60, refresh=False)
    top_catalysts = (
        intel_summary.get('top_catalysts', []) if isinstance(intel_summary.get('top_catalysts'), list) else []
    )
    for idx, row in enumerate(top_catalysts[:8]):
        if not isinstance(row, dict):
            continue
        symbol = _librarian_normalize_symbol(row.get('symbol', ''))
        catalyst = str(row.get('catalyst', 'market catalyst')).strip()
        score = float(row.get('score', 0.0) or 0.0)
        mentions = int(row.get('mentions', 0) or 0)
        summary = f"{symbol or 'Market'} catalyst: {catalyst} (score {score:.2f}, mentions {mentions})"
        candidates.append(
            {
                'id': f'catalyst-{idx}-{symbol or "market"}',
                'type': 'catalyst',
                'title': f'Catalyst {symbol or "Market"}',
                'summary': summary,
                'text': summary,
                'symbols': [symbol] if symbol else [],
                'timestamp': now_iso,
                'metadata': {'score': score, 'mentions': mentions, 'catalyst': catalyst},
            }
        )

    drivers = intel_summary.get('drivers', []) if isinstance(intel_summary.get('drivers'), list) else []
    for idx, row in enumerate(drivers[:8]):
        if not isinstance(row, dict):
            continue
        symbol = _librarian_normalize_symbol(row.get('symbol', ''))
        sentiment = str(row.get('sentiment', 'neutral')).strip().lower() or 'neutral'
        score = float(row.get('score', 0.0) or 0.0)
        mentions = int(row.get('mentions', 0) or 0)
        summary = f"Driver {symbol or 'market'} sentiment {sentiment}, score {score:.2f}, mentions {mentions}"
        candidates.append(
            {
                'id': f'driver-{idx}-{symbol or "market"}',
                'type': 'driver',
                'title': f'Driver {symbol or "Market"}',
                'summary': summary,
                'text': summary,
                'symbols': [symbol] if symbol else [],
                'timestamp': now_iso,
                'metadata': {'score': score, 'sentiment': sentiment, 'mentions': mentions},
            }
        )

    trade_rows = _fetch_trade_executions(
        hours=min(max(6, hours), 48),
        limit=120,
        include_simulated=False,
        include_failed=True,
    ).get('trades', [])
    for idx, row in enumerate(trade_rows[:60]):
        if not isinstance(row, dict):
            continue
        symbol = _librarian_normalize_symbol(row.get('symbol', ''))
        side = str(row.get('side', 'UNKNOWN')).upper()
        platform = str(row.get('platform', 'unknown')).lower()
        executed = bool(row.get('executed', False))
        status = 'executed' if executed else 'rejected'
        qty = float(row.get('filled_quantity', 0.0) or 0.0)
        pnl = float(row.get('realized_pnl', 0.0) or 0.0)
        avg_price = float(row.get('avg_price', 0.0) or 0.0)
        summary = (
            f"{status} {symbol or 'asset'} {side} on {platform}; qty {qty:.6f}, "
            f"avg {avg_price:.4f}, pnl {pnl:+.4f}"
        )
        candidates.append(
            {
                'id': f"trade-{idx}-{row.get('trade_id', idx)}",
                'type': 'execution',
                'title': f'Trade {status.upper()} {symbol or "--"}',
                'summary': summary,
                'text': summary,
                'symbols': [symbol] if symbol else [],
                'timestamp': _iso_or_default(row.get('timestamp'), now_iso),
                'metadata': {
                    'status': status,
                    'platform': platform,
                    'pnl': pnl,
                    'qty': qty,
                    'side': side,
                },
            }
        )

    return candidates


def _librarian_score_candidate(candidate: dict, terms: set[str], now_utc: datetime) -> float:
    doc_type = str(candidate.get('type', 'other')).strip().lower()
    base_weight = {
        'strategy_lane': 0.42,
        'reject_reason': 0.38,
        'catalyst': 0.34,
        'driver': 0.32,
        'execution': 0.28,
    }.get(doc_type, 0.2)

    text = ' '.join(
        [
            str(candidate.get('title', '')),
            str(candidate.get('summary', '')),
            str(candidate.get('text', '')),
        ]
    ).lower()

    overlap_count = sum(1 for term in terms if term and term in text)
    overlap_score = min(0.62, overlap_count * 0.14)

    recency_score = 0.0
    ts = _coerce_datetime(candidate.get('timestamp'))
    if ts is not None:
        age_h = max(0.0, (now_utc - ts).total_seconds() / 3600.0)
        if age_h <= 2:
            recency_score = 0.24
        elif age_h <= 24:
            recency_score = 0.16
        elif age_h <= 72:
            recency_score = 0.09
        else:
            recency_score = 0.03

    symbols = [str(s).lower() for s in (candidate.get('symbols') or []) if str(s).strip()]
    symbol_boost = 0.12 if any(sym in terms for sym in symbols) else 0.0

    metadata = candidate.get('metadata') if isinstance(candidate.get('metadata'), dict) else {}
    status = str(metadata.get('status', '')).strip().lower()
    recommendation = str(metadata.get('recommendation', '')).strip().lower()
    risk_boost = 0.06 if status == 'rejected' or recommendation in {'block', 'defer'} else 0.0

    return round(base_weight + overlap_score + recency_score + symbol_boost + risk_boost, 4)


def _fetch_librarian_remote_context(query: str, hours: int, limit: int) -> tuple[dict | None, str | None]:
    if not LIBRARIAN_REMOTE_URL:
        return None, 'remote_url_missing'
    url = f"{LIBRARIAN_REMOTE_URL.rstrip('/')}/v1/context"
    headers = {'Content-Type': 'application/json'}
    if LIBRARIAN_REMOTE_API_KEY:
        headers['Authorization'] = f'Bearer {LIBRARIAN_REMOTE_API_KEY}'
    payload = {'query': query, 'hours': int(hours), 'limit': int(limit)}
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=12)
        if resp.status_code >= 400:
            return None, f'http_{resp.status_code}'
        data = resp.json()
        if not isinstance(data, dict):
            return None, 'invalid_payload'
        return data, None
    except requests.RequestException as exc:
        return None, str(exc)
    except ValueError:
        return None, 'invalid_json'


def _platform_librarian_context_payload(
    query: str = '',
    hours: int = 24,
    limit: int = LIBRARIAN_DEFAULT_LIMIT,
    refresh: bool = False,
):
    safe_hours = max(1, min(int(hours or 24), 168))
    safe_limit = max(3, min(int(limit or LIBRARIAN_DEFAULT_LIMIT), 24))
    effective_query = str(query or '').strip() or LIBRARIAN_DEFAULT_QUERY
    query_hash = hashlib.sha1(effective_query.encode('utf-8')).hexdigest()[:10]
    cache_key = f'librarian_context:{safe_hours}:{safe_limit}:{query_hash}:{LIBRARIAN_MODE}:{int(LIBRARIAN_ENABLED)}'

    if not LIBRARIAN_ENABLED:
        return {
            'timestamp': datetime.utcnow().isoformat(),
            'enabled': False,
            'mode': LIBRARIAN_MODE,
            'query': effective_query,
            'window_hours': safe_hours,
            'limit': safe_limit,
            'total_candidates': 0,
            'selected_count': 0,
            'selected': [],
            'summary': {'note': 'librarian_disabled'},
        }

    if not refresh:
        cached = get_cached(cache_key, duration=20)
        if cached:
            return cached

    remote_error = None
    if LIBRARIAN_MODE == 'remote':
        remote, remote_error = _fetch_librarian_remote_context(effective_query, safe_hours, safe_limit)
        if remote:
            payload = {
                'timestamp': datetime.utcnow().isoformat(),
                'enabled': True,
                'mode': 'remote',
                'query': effective_query,
                'window_hours': safe_hours,
                'limit': safe_limit,
                'total_candidates': int(remote.get('total_candidates', 0) or 0),
                'selected_count': int(remote.get('selected_count', 0) or 0),
                'selected': remote.get('selected', []) if isinstance(remote.get('selected'), list) else [],
                'summary': remote.get('summary', {}) if isinstance(remote.get('summary'), dict) else {},
                'sources': remote.get('sources', {}),
            }
            set_cache(cache_key, payload)
            return payload

    now_utc = datetime.now(timezone.utc)
    terms = _librarian_extract_terms(effective_query)
    candidates = _librarian_build_local_candidates(hours=safe_hours)

    scored = []
    for row in candidates:
        if not isinstance(row, dict):
            continue
        score = _librarian_score_candidate(row, terms=terms, now_utc=now_utc)
        if score < LIBRARIAN_MIN_SCORE:
            continue
        out = dict(row)
        out['score'] = score
        scored.append(out)

    scored.sort(key=lambda item: item.get('score', 0.0), reverse=True)
    selected = scored[:safe_limit]
    source_counts: dict[str, int] = {}
    symbol_counts: dict[str, int] = {}
    for row in selected:
        src = str(row.get('type', 'other')).strip().lower() or 'other'
        source_counts[src] = source_counts.get(src, 0) + 1
        for sym in row.get('symbols', []) if isinstance(row.get('symbols'), list) else []:
            sym_norm = _librarian_normalize_symbol(sym)
            if sym_norm:
                symbol_counts[sym_norm] = symbol_counts.get(sym_norm, 0) + 1

    top_types = [
        {'type': key, 'count': value}
        for key, value in sorted(source_counts.items(), key=lambda item: item[1], reverse=True)
    ]
    top_symbols = [
        {'symbol': key, 'count': value}
        for key, value in sorted(symbol_counts.items(), key=lambda item: item[1], reverse=True)[:6]
    ]
    focus = ', '.join([row['type'] for row in top_types[:3]]) if top_types else 'mixed'
    narrative = (
        f"Curated {len(selected)}/{len(candidates)} high-signal context blocks; "
        f"focus on {focus} for query '{effective_query[:72]}'."
    )

    payload = {
        'timestamp': datetime.utcnow().isoformat(),
        'enabled': True,
        'mode': 'local_fallback' if (LIBRARIAN_MODE == 'remote' and remote_error) else 'local',
        'query': effective_query,
        'window_hours': safe_hours,
        'limit': safe_limit,
        'min_score': LIBRARIAN_MIN_SCORE,
        'total_candidates': len(candidates),
        'selected_count': len(selected),
        'selected': selected,
        'summary': {
            'narrative': narrative,
            'top_types': top_types,
            'top_symbols': top_symbols,
            'selection_ratio': round((len(selected) / max(1, len(candidates))) * 100.0, 2),
        },
        'sources': {
            'strategy_ops': '/api/platform/strategy-ops',
            'intel_summary': '/api/platform/intel-summary',
            'trades': '/api/platform/trades',
            'logs': '/api/platform/logs',
        },
    }
    if remote_error:
        payload['remote_error'] = remote_error
    set_cache(cache_key, payload)
    return payload


def _platform_agent_context_payload(hours: int = 24, refresh: bool = False):
    safe_hours = max(1, min(int(hours or 24), 168))
    cache_key = f'platform_agent_context_{safe_hours}'
    if not refresh:
        cached = get_cached(cache_key, duration=15)
        if cached:
            return cached

    status = _public_status_payload()
    market = _fetch_market_prices()
    trading = _fetch_trading_metrics()
    brief_hours = max(24, safe_hours)
    if refresh:
        intel_summary = _platform_intel_summary_payload(hours=safe_hours, limit=60, refresh=True)
        business_brief = _platform_business_brief_payload(hours=brief_hours, force_refresh=True)
    else:
        intel_cache_key = f'platform_intel_summary:{safe_hours}:60'
        brief_cache_key = f'platform_business_brief_{brief_hours}'
        intel_summary = get_cached(intel_cache_key, duration=300) or {'summary': {}, 'top_catalysts': [], 'drivers': []}
        business_brief = get_cached(brief_cache_key, duration=300) or {'summary': {}, 'narrative': {}}

    health_summary = status.get('summary', {}) if isinstance(status.get('summary'), dict) else {}
    intelligence_summary = intel_summary.get('summary', {}) if isinstance(intel_summary.get('summary'), dict) else {}
    reject_tax = (trading.get('reject_tax') if isinstance(trading, dict) else {}) or {}
    ops_state = _load_strategy_ops_digest_state()
    strategy_assessment = ops_state.get('assessment', {}) if isinstance(ops_state.get('assessment'), dict) else {}
    strategy_operator_brief = ops_state.get('operator_brief', {}) if isinstance(ops_state.get('operator_brief'), dict) else {}
    strategy_data_quality = ops_state.get('data_quality', {}) if isinstance(ops_state.get('data_quality'), dict) else {}
    strategy_decision = ops_state.get('decision', {}) if isinstance(ops_state.get('decision'), dict) else {}
    top_lanes = ops_state.get('top_lanes', []) if isinstance(ops_state.get('top_lanes'), list) else []

    if not strategy_assessment:
        sample_size = int(reject_tax.get('sample_size', 0) or 0)
        reject_tax_pct = float(reject_tax.get('reject_tax_pct', 0.0) or 0.0)
        hard_fail_pct = float(reject_tax.get('hard_fail_pct', 0.0) or 0.0)
        min_sample = max(1, int(float(os.getenv('STRATEGY_OPS_GONOGO_MIN_SAMPLE_SIZE', '30') or 30)))
        max_reject = max(0.0, min(100.0, float(os.getenv('STRATEGY_OPS_GONOGO_MAX_REJECT_TAX_PCT', '70') or 70.0)))
        max_hard_fail = max(0.0, min(100.0, float(os.getenv('STRATEGY_OPS_GONOGO_MAX_HARD_FAIL_PCT', '10') or 10.0)))
        reasons = []
        if sample_size < min_sample:
            reasons.append(f'sample_size {sample_size} < {min_sample}')
        if reject_tax_pct > max_reject:
            reasons.append(f'reject_tax {reject_tax_pct:.1f}% > {max_reject:.1f}%')
        if hard_fail_pct > max_hard_fail:
            reasons.append(f'hard_fail {hard_fail_pct:.1f}% > {max_hard_fail:.1f}%')
        strategy_assessment = {
            'go': len(reasons) == 0,
            'label': 'GO' if len(reasons) == 0 else 'NO-GO',
            'reasons': reasons,
            'sample_size': sample_size,
            'reject_tax_pct': round(reject_tax_pct, 2),
            'hard_fail_pct': round(hard_fail_pct, 2),
            'thresholds': {
                'min_sample_size': min_sample,
                'max_reject_tax_pct': round(max_reject, 2),
                'max_hard_fail_pct': round(max_hard_fail, 2),
            },
        }
    if not strategy_decision:
        strategy_decision = _resolve_strategy_ops_decision(
            assessment=strategy_assessment,
            operator_brief=strategy_operator_brief,
            data_quality=strategy_data_quality,
        )

    librarian_context = _platform_librarian_context_payload(
        query='live trading context risk execution and catalysts',
        hours=safe_hours,
        limit=6,
        refresh=False,
    )

    payload = {
        'timestamp': datetime.utcnow().isoformat(),
        'window_hours': safe_hours,
        'posture': {
            'public_read_only': bool(PUBLIC_READ_ONLY),
            'operator_controls_exposed': False,
        },
        'status': {
            'service_healthy': int(health_summary.get('service_healthy', 0) or 0),
            'service_total': int(health_summary.get('service_total', 0) or 0),
            'overall_healthy': bool(status.get('overall_healthy', False)),
            'optional_degraded_count': int(status.get('optional_degraded_count', 0) or 0),
            'monitor_timestamp': status.get('timestamp'),
        },
        'market': market,
        'strategy_ops': {
            'assessment': strategy_assessment,
            'decision': strategy_decision,
            'top_lanes': top_lanes,
            'operator_brief': strategy_operator_brief,
            'data_quality': strategy_data_quality,
            'state_updated_at': ops_state.get('updated_at') if isinstance(ops_state, dict) else None,
        },
        'execution': {
            'trading_metrics': trading.get('trades', {}) if isinstance(trading, dict) else {},
            'pnl': trading.get('pnl', {}) if isinstance(trading, dict) else {},
            'reject_tax': reject_tax,
        },
        'intelligence': {
            'summary': intelligence_summary,
            'top_catalysts': intel_summary.get('top_catalysts', []),
            'top_drivers': intel_summary.get('drivers', []),
        },
        'business_brief': {
            'summary': business_brief.get('summary', {}) if isinstance(business_brief, dict) else {},
            'narrative': business_brief.get('narrative', {}) if isinstance(business_brief, dict) else {},
        },
        'librarian': librarian_context,
        'sources': {
            'status': '/api/platform/status',
            'metrics': '/api/platform/metrics',
            'strategy_ops': '/api/platform/strategy-ops',
            'librarian_context': '/api/platform/librarian-context',
            'intel_summary': '/api/platform/intel-summary',
            'business_brief': '/api/platform/business-brief',
        },
    }
    set_cache(cache_key, payload)
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

    raw_status = results.get('status', {}).get('data') or _collect_system_status()
    status_public = _public_status_payload(raw_status)
    if isinstance(results.get('status'), dict):
        results['status']['data'] = status_public

    payload = {
        'timestamp': datetime.utcnow().isoformat(),
        'overall_ok': all(result.get('ok', False) for result in results.values()),
        'results': results,
        'status': status_public,
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
            '/api/strategy/ops': '/api/platform/strategy-ops',
            '/api/agent/context': '/api/platform/agent-context',
            '/api/business-brief': '/api/platform/business-brief',
            '/api/logs': '/api/platform/logs',
            '/api/trades': '/api/platform/trades',
            '/api/organization': '/api/platform/organization',
            '/api/production/readiness': '/api/platform/readiness',
            '/api/projects': '/api/platform/projects',
            '/api/intel/feed': '/api/platform/intel-feed',
            '/api/intel/summary': '/api/platform/intel-summary',
            '/api/architecture/telemetry': '/api/platform/architecture-telemetry',
            '/api/architecture/live': '/api/platform/architecture-live',
            '/api/superswarm': '/api/platform/superswarm',
            '/api/windows-lab': '/api/platform/windows-lab',
            '/api/contracts': '/api/platform/contracts',
        },
        'alias_policy': {
            'deprecated': True,
            'sunset': LEGACY_ALIAS_SUNSET,
            'successor_prefix': '/api/platform/',
        },
        'notes': [
            'Use /api/platform/* contracts for all new clients.',
            'Legacy aliases are maintained for compatibility and will be retired after migration.',
            'Public web is strictly read-only; control and mutation routes are disabled.',
            'Sensitive infrastructure fields (IPs, internal URLs) are redacted from public responses.',
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
    return redirect('/architecture', code=302)


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
@requires_auth
def control():
    abort(404)


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
    return redirect('/architecture', code=302)


@app.route('/command-deck')
@requires_auth
def command_deck_legacy():
    return redirect('/architecture', code=302)


@app.route('/system-health')
@requires_auth
def system_health_legacy():
    return redirect('/architecture', code=302)


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
    return redirect('/architecture', code=302)


@app.route('/infrastructure')
@requires_auth
def infrastructure_legacy():
    return redirect('/architecture', code=302)


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
    return _deprecated_alias_response(jsonify(_public_status_payload()), '/api/platform/status')


@app.route('/api/health/summary')
@requires_auth
def api_health_summary():
    return _deprecated_alias_response(jsonify(_platform_health_summary()), '/api/platform/readiness')


@app.route('/api/platform/status')
@requires_auth
def api_platform_status():
    return jsonify(_public_status_payload())


@app.route('/api/platform/metrics')
@requires_auth
def api_platform_metrics():
    return jsonify(_platform_metrics_payload())


@app.route('/api/platform/strategy-ops')
@requires_auth
def api_platform_strategy_ops():
    days = request.args.get('days', 7, type=int)
    refresh = request.args.get('refresh', 'false', type=str).lower() == 'true'
    return jsonify(_platform_strategy_ops_payload(days=days, refresh=refresh))


@app.route('/api/platform/go-no-go-brief')
@requires_auth
def api_platform_go_no_go_brief():
    days = request.args.get('days', 7, type=int)
    refresh = request.args.get('refresh', 'false', type=str).lower() == 'true'
    return jsonify(_platform_go_no_go_brief_payload(days=days, refresh=refresh))


@app.route('/api/platform/agent-context')
@requires_auth
def api_platform_agent_context():
    hours = request.args.get('hours', 24, type=int)
    refresh = request.args.get('refresh', 'false', type=str).lower() == 'true'
    return jsonify(_platform_agent_context_payload(hours=hours, refresh=refresh))


@app.route('/api/platform/librarian-context')
@requires_auth
def api_platform_librarian_context():
    query = request.args.get('query', '', type=str)
    hours = request.args.get('hours', 24, type=int)
    limit = request.args.get('limit', LIBRARIAN_DEFAULT_LIMIT, type=int)
    refresh = request.args.get('refresh', 'false', type=str).lower() == 'true'
    return jsonify(
        _platform_librarian_context_payload(
            query=query,
            hours=hours,
            limit=limit,
            refresh=refresh,
        )
    )


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


@app.route('/api/platform/intel-summary')
@requires_auth
def api_platform_intel_summary():
    hours = request.args.get('hours', 24, type=int)
    limit = request.args.get('limit', 60, type=int)
    refresh = request.args.get('refresh', 'false', type=str).lower() == 'true'
    return jsonify(_platform_intel_summary_payload(hours=hours, limit=limit, refresh=refresh))


@app.route('/api/platform/zeitgeist-universe')
@requires_auth
def api_platform_zeitgeist_universe():
    refresh = request.args.get('refresh', 'false', type=str).lower() == 'true'
    return jsonify(_platform_zeitgeist_universe_payload(refresh=refresh))


@app.route('/api/platform/architecture-telemetry')
@requires_auth
def api_platform_architecture_telemetry():
    hours = request.args.get('hours', 6, type=int)
    refresh = request.args.get('refresh', 'false', type=str).lower() == 'true'
    return jsonify(_platform_architecture_telemetry_payload(hours=hours, refresh=refresh))


@app.route('/api/platform/architecture-live')
@requires_auth
def api_platform_architecture_live():
    hours = request.args.get('hours', 24, type=int)
    refresh = request.args.get('refresh', 'false', type=str).lower() == 'true'
    return jsonify(_platform_architecture_live_payload(hours=hours, refresh=refresh))


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
@requires_auth
def api_platform_control_plane():
    return jsonify({'error': 'control_plane_disabled_on_public_web'}), 404


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


@app.route('/api/strategy/ops')
@requires_auth
def api_strategy_ops():
    return _deprecated_alias_response(api_platform_strategy_ops(), '/api/platform/strategy-ops')


@app.route('/api/agent/context')
@requires_auth
def api_agent_context():
    return _deprecated_alias_response(api_platform_agent_context(), '/api/platform/agent-context')


@app.route('/api/librarian/context')
@requires_auth
def api_librarian_context():
    return _deprecated_alias_response(
        api_platform_librarian_context(),
        '/api/platform/librarian-context',
    )


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


@app.route('/api/intel/summary')
@requires_auth
def api_intel_summary():
    return _deprecated_alias_response(api_platform_intel_summary(), '/api/platform/intel-summary')


@app.route('/api/zeitgeist/universe')
@requires_auth
def api_zeitgeist_universe():
    return _deprecated_alias_response(
        api_platform_zeitgeist_universe(),
        '/api/platform/zeitgeist-universe',
    )


@app.route('/api/architecture/telemetry')
@requires_auth
def api_architecture_telemetry():
    return _deprecated_alias_response(
        api_platform_architecture_telemetry(),
        '/api/platform/architecture-telemetry',
    )


@app.route('/api/architecture/live')
@requires_auth
def api_architecture_live():
    return _deprecated_alias_response(
        api_platform_architecture_live(),
        '/api/platform/architecture-live',
    )


@app.route('/api/superswarm')
@requires_auth
def api_superswarm():
    return _deprecated_alias_response(api_platform_superswarm(), '/api/platform/superswarm')


@app.route('/api/contracts')
@requires_auth
def api_contracts():
    return _deprecated_alias_response(api_platform_contracts(), '/api/platform/contracts')


@app.route('/api/control-plane')
@requires_auth
def api_control_plane():
    return _deprecated_alias_response(
        (jsonify({'error': 'control_plane_disabled_on_public_web'}), 404),
        '/api/platform/control-plane',
    )


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


@app.route('/jobs/platform/architecture-bottleneck-digest', methods=['POST', 'GET'])
@requires_control_token
def job_platform_architecture_bottleneck_digest():
    payload = request.get_json(silent=True) if request.method == 'POST' else {}
    if not isinstance(payload, dict):
        payload = {}

    hours = request.args.get('hours', payload.get('hours', 6), type=int)
    hours = max(1, min(int(hours or 6), 72))
    min_interval_sec = request.args.get(
        'min_interval_sec',
        payload.get('min_interval_sec', int(os.getenv('BOTTLENECK_DIGEST_MIN_INTERVAL_SEC', '3600'))),
        type=int,
    )
    min_interval_sec = max(0, int(min_interval_sec or 0))
    force = _as_bool(request.args.get('force', payload.get('force', False)), False)
    dry_run = _as_bool(request.args.get('dry_run', payload.get('dry_run', False)), False)

    telemetry = _platform_architecture_telemetry_payload(hours=hours, refresh=True)
    brief = _platform_business_brief_payload(hours=max(24, hours), force_refresh=True)
    message, signature, should_send = _build_bottleneck_digest_message(telemetry, brief)

    now_ts = int(time.time())
    state = _load_bottleneck_digest_state()
    last_sig = str(state.get('signature', ''))
    last_sent_at = int(state.get('sent_at', 0) or 0)
    changed = signature != last_sig
    cooled_down = (now_ts - last_sent_at) >= min_interval_sec
    trigger_send = force or should_send

    response_payload = {
        'ok': True,
        'timestamp': datetime.utcnow().isoformat(),
        'window_hours': hours,
        'trigger_send': trigger_send,
        'should_send': should_send,
        'changed': changed,
        'cooled_down': cooled_down,
        'dry_run': dry_run,
        'state': {
            'last_sent_at': last_sent_at,
            'has_signature': bool(last_sig),
        },
        'telemetry_summary': telemetry.get('summary', {}),
    }

    if dry_run:
        response_payload.update({'message': message, 'status': 'dry_run'})
        return jsonify(response_payload), 200

    if not trigger_send:
        response_payload.update({'status': 'skipped', 'reason': 'no_watch_trigger'})
        return jsonify(response_payload), 200

    if not (changed or cooled_down):
        response_payload.update({'status': 'skipped', 'reason': 'cooldown_unchanged'})
        return jsonify(response_payload), 200

    token = (
        os.getenv('TELEGRAM_BOT_TOKEN', '').strip()
        or os.getenv('SAPPHIRE_TELEGRAM_BOT_TOKEN', '').strip()
    )
    chat_id = (
        os.getenv('TELEGRAM_CHAT_ID', '').strip()
        or os.getenv('TELEGRAM_BOT_CHAT_ID', '').strip()
        or os.getenv('TELEGRAM_OWNER_USER_ID', '').strip()
    )
    if not token or not chat_id:
        response_payload.update({'ok': False, 'status': 'error', 'error': 'telegram_config_missing'})
        return jsonify(response_payload), 503

    try:
        telegram_response = _send_telegram_digest(token=token, chat_id=chat_id, message=message)
    except Exception as exc:
        response_payload.update({'ok': False, 'status': 'error', 'error': str(exc)})
        return jsonify(response_payload), 502

    saved = _save_bottleneck_digest_state(
        {
            'sent_at': now_ts,
            'signature': signature,
            'updated_at': datetime.utcnow().isoformat(),
            'conversion_severity': (telemetry.get('summary') or {}).get('conversion_severity', 'unknown'),
        }
    )
    response_payload.update(
        {
            'status': 'sent',
            'persist': saved,
            'telegram_ok': bool((telegram_response or {}).get('ok', True)),
            'telegram_message_id': (telegram_response.get('result') or {}).get('message_id')
            if isinstance(telegram_response, dict)
            else None,
        }
    )
    return jsonify(response_payload), 200


@app.route('/jobs/platform/strategy-ops-digest', methods=['POST', 'GET'])
@requires_control_token
def job_platform_strategy_ops_digest():
    payload = request.get_json(silent=True) if request.method == 'POST' else {}
    if not isinstance(payload, dict):
        payload = {}

    days = request.args.get('days', payload.get('days', 7), type=int)
    days = max(1, min(int(days or 7), 30))
    min_interval_sec = request.args.get(
        'min_interval_sec',
        payload.get('min_interval_sec', int(os.getenv('STRATEGY_OPS_DIGEST_MIN_INTERVAL_SEC', '21600'))),
        type=int,
    )
    min_interval_sec = max(0, int(min_interval_sec or 0))
    force = _as_bool(request.args.get('force', payload.get('force', False)), False)
    dry_run = _as_bool(request.args.get('dry_run', payload.get('dry_run', False)), False)

    ops_payload = _platform_strategy_ops_payload(days=days, refresh=True)
    scorecard = ops_payload.get('scorecard', {}) if isinstance(ops_payload.get('scorecard'), dict) else {}
    reject_tax = ops_payload.get('reject_tax', {}) if isinstance(ops_payload.get('reject_tax'), dict) else {}
    assessment = ops_payload.get('assessment', {}) if isinstance(ops_payload.get('assessment'), dict) else {}
    attribution = ops_payload.get('attribution', {}) if isinstance(ops_payload.get('attribution'), dict) else {}
    data_quality = ops_payload.get('data_quality', {}) if isinstance(ops_payload.get('data_quality'), dict) else {}
    operator_brief = ops_payload.get('operator_brief', {}) if isinstance(ops_payload.get('operator_brief'), dict) else {}
    decision = ops_payload.get('decision', {}) if isinstance(ops_payload.get('decision'), dict) else {}
    if not decision:
        decision = _resolve_strategy_ops_decision(
            assessment=assessment,
            operator_brief=operator_brief,
            data_quality=data_quality,
        )
    message, signature, should_send = _build_strategy_ops_digest_message(
        scorecard,
        reject_tax,
        assessment,
        operator_brief=operator_brief,
        decision=decision,
        data_quality=data_quality,
    )

    now_ts = int(time.time())
    state = _load_strategy_ops_digest_state()
    last_sig = str(state.get('signature', ''))
    last_sent_at = int(state.get('sent_at', 0) or 0)
    changed = signature != last_sig
    cooled_down = (now_ts - last_sent_at) >= min_interval_sec
    trigger_send = force or should_send

    response_payload = {
        'ok': True,
        'response_version': 'strategy_ops_digest_v2',
        'timestamp': datetime.utcnow().isoformat(),
        'window_days': days,
        'trigger_send': trigger_send,
        'should_send': should_send,
        'changed': changed,
        'cooled_down': cooled_down,
        'dry_run': dry_run,
        'assessment': assessment,
        'operator_brief': operator_brief,
        'decision': decision,
        'scorecard_totals': scorecard.get('totals', {}),
        'state': {
            'last_sent_at': last_sent_at,
            'has_signature': bool(last_sig),
        },
    }

    state_payload = _build_strategy_ops_state_payload(
        days=days,
        scorecard=scorecard,
        reject_tax=reject_tax,
        assessment=assessment,
        operator_brief=operator_brief,
        decision=decision,
        attribution=attribution,
        data_quality=data_quality,
    )
    state_saved = _save_strategy_ops_digest_state(state_payload)
    response_payload['state_persist'] = state_saved
    if _as_bool(os.getenv('STRATEGY_OPS_PERSIST_SNAPSHOT_ON_DIGEST', 'true'), True):
        response_payload['snapshot_persist'] = _save_strategy_ops_snapshot(state_payload, keep_history=False)

    if dry_run:
        response_payload.update({'message': message, 'status': 'dry_run'})
        return jsonify(response_payload), 200

    if not trigger_send:
        response_payload.update({'status': 'skipped', 'reason': 'no_digest_trigger'})
        return jsonify(response_payload), 200

    if not (changed or cooled_down):
        response_payload.update({'status': 'skipped', 'reason': 'cooldown_unchanged'})
        return jsonify(response_payload), 200

    token = (
        os.getenv('TELEGRAM_BOT_TOKEN', '').strip()
        or os.getenv('SAPPHIRE_TELEGRAM_BOT_TOKEN', '').strip()
    )
    chat_id = (
        os.getenv('TELEGRAM_CHAT_ID', '').strip()
        or os.getenv('TELEGRAM_BOT_CHAT_ID', '').strip()
        or os.getenv('TELEGRAM_OWNER_USER_ID', '').strip()
    )
    if not token or not chat_id:
        response_payload.update({'ok': False, 'status': 'error', 'error': 'telegram_config_missing'})
        return jsonify(response_payload), 503

    try:
        telegram_response = _send_telegram_digest(token=token, chat_id=chat_id, message=message)
    except Exception as exc:
        response_payload.update({'ok': False, 'status': 'error', 'error': str(exc)})
        return jsonify(response_payload), 502

    saved = _save_strategy_ops_digest_state(
        {
            **state_payload,
            'sent_at': now_ts,
            'signature': signature,
        }
    )
    response_payload.update(
        {
            'status': 'sent',
            'persist': saved,
            'telegram_ok': bool((telegram_response or {}).get('ok', True)),
            'telegram_message_id': (telegram_response.get('result') or {}).get('message_id')
            if isinstance(telegram_response, dict)
            else None,
        }
    )
    return jsonify(response_payload), 200


@app.route('/jobs/platform/strategy-ops-snapshot', methods=['POST', 'GET'])
@requires_control_token
def job_platform_strategy_ops_snapshot():
    payload = request.get_json(silent=True) if request.method == 'POST' else {}
    if not isinstance(payload, dict):
        payload = {}

    days = request.args.get('days', payload.get('days', 7), type=int)
    days = max(1, min(int(days or 7), 30))
    keep_history = _as_bool(request.args.get('keep_history', payload.get('keep_history', True)), True)
    refresh = _as_bool(request.args.get('refresh', payload.get('refresh', True)), True)

    ops_payload = _platform_strategy_ops_payload(days=days, refresh=refresh)
    scorecard = ops_payload.get('scorecard', {}) if isinstance(ops_payload.get('scorecard'), dict) else {}
    reject_tax = ops_payload.get('reject_tax', {}) if isinstance(ops_payload.get('reject_tax'), dict) else {}
    assessment = ops_payload.get('assessment', {}) if isinstance(ops_payload.get('assessment'), dict) else {}
    attribution = ops_payload.get('attribution', {}) if isinstance(ops_payload.get('attribution'), dict) else {}
    data_quality = ops_payload.get('data_quality', {}) if isinstance(ops_payload.get('data_quality'), dict) else {}
    operator_brief = ops_payload.get('operator_brief', {}) if isinstance(ops_payload.get('operator_brief'), dict) else {}
    decision = ops_payload.get('decision', {}) if isinstance(ops_payload.get('decision'), dict) else {}
    if not decision:
        decision = _resolve_strategy_ops_decision(
            assessment=assessment,
            operator_brief=operator_brief,
            data_quality=data_quality,
        )

    state_payload = _build_strategy_ops_state_payload(
        days=days,
        scorecard=scorecard,
        reject_tax=reject_tax,
        assessment=assessment,
        operator_brief=operator_brief,
        decision=decision,
        attribution=attribution,
        data_quality=data_quality,
    )
    saved = _save_strategy_ops_snapshot(state_payload, keep_history=keep_history)
    state_saved = _save_strategy_ops_digest_state(state_payload)

    return jsonify(
        {
            'ok': bool(saved.get('written', False)),
            'timestamp': datetime.utcnow().isoformat(),
            'window_days': days,
            'refresh': refresh,
            'keep_history': keep_history,
            'persist': saved,
            'state_persist': state_saved,
            'assessment': assessment,
            'operator_brief': operator_brief,
            'decision': decision,
            'scorecard_totals': scorecard.get('totals', {}),
        }
    ), (200 if saved.get('written', False) else 502)


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
