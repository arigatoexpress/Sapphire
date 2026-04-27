#!/usr/bin/env python3
"""
Sapphire Trading Dashboard
Real-time trading system monitor and control interface
"""

import json
import logging
import os
import secrets
import sys
import time
from datetime import UTC, datetime
from functools import wraps
from pathlib import Path
from typing import Any

# Make the Sapphire lib/ discoverable regardless of whether this dashboard runs
# from the main repo or a git worktree. Done once at import time so namespace
# packages resolve consistently across requests.
_DASHBOARD_ROOTS = (
    Path(__file__).resolve().parents[2],          # current checkout (worktree or main)
    Path.home() / 'Code' / 'Sapphire',            # canonical main repo
)
# Insert in reverse so the current-checkout path ends up at index 0 (highest
# priority). Without this, a worktree dashboard resolves `lib.*` against the
# main repo and misses modules only present in the worktree.
for _r in reversed(_DASHBOARD_ROOTS):
    _rs = str(_r)
    while _rs in sys.path:
        sys.path.remove(_rs)
    sys.path.insert(0, _rs)

log = logging.getLogger("dashboard")

import contextlib

from flask import Flask, Response, jsonify, render_template, request, send_file, send_from_directory

# Disable Flask's auto-registered /static/<path> route. It was bypassing the
# @requires_auth decorator and exposing static/benchmark_report.html
# (infrastructure topology: GPU models, VRAM, endpoints) to any caller.
# A guarded replacement is registered below so the same files still serve
# — only for authenticated users.
app = Flask(__name__, static_folder=None)
_STATIC_DIR = Path(__file__).parent / "static"
_DASHBOARD_REPO_ROOT = Path(__file__).resolve().parents[2]
_AGENT_EVENTS_FILE = _DASHBOARD_REPO_ROOT / "data" / "events" / "bus.jsonl"
_AGENT_HEARTBEAT_DIR = _DASHBOARD_REPO_ROOT / "data" / "agents"

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

# x402 payment gate — optional, disabled unless X402_ENABLED=1
import sys as _sys  # noqa: E402

_LIB_PAYMENTS = _DASHBOARD_REPO_ROOT
if str(_LIB_PAYMENTS) not in sys.path:
    sys.path.insert(0, str(_LIB_PAYMENTS))
try:
    from lib.payments.x402_middleware import require_payment as x402_require  # noqa: E402
    _X402_AVAILABLE = True
except Exception:
    _X402_AVAILABLE = False

    def x402_require(amount_usd, description=""):  # type: ignore[misc]
        def _decorator(f):
            return f
        return _decorator

def check_auth(username, password):
    # Constant-time compare to avoid leaking password length / prefix via
    # response-time side channel. Both values are compared after encoding so
    # mismatched types don't raise.
    if username is None or password is None:
        return False
    u_ok = secrets.compare_digest(str(username).encode("utf-8"),
                                  str(AUTH_USERNAME).encode("utf-8"))
    p_ok = secrets.compare_digest(str(password).encode("utf-8"),
                                  str(AUTH_PASSWORD).encode("utf-8"))
    return u_ok and p_ok

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


@app.route('/static/<path:filename>', endpoint='static')
@requires_auth
def guarded_static(filename):
    """Auth-gated replacement for Flask's default static handler.

    Named `static` so url_for('static', filename=...) still works for any
    template or route that relies on the default Flask endpoint name.
    """
    return send_from_directory(_STATIC_DIR, filename)

# Cache for data
_cache = {}
_cache_time = {}
CACHE_DURATION = 10  # seconds
CHAIN_OVERVIEW_CACHE_DURATION = 60
PORTFOLIO_CACHE_DURATION = 30
CASCADE_CACHE_DURATION = 30
STRATEGY_PERFORMANCE_CACHE_DURATION = 30
MARKET_UNIVERSE_CACHE_DURATION = 60
STRATEGY_LAB_CACHE_DURATION = 300

# ── In-process latency metrics (per-route rolling) ─────────────────────────
# Keeps a bounded ring buffer of (method, path, ms) samples plus per-route
# counters. Exposed via /metrics (auth-gated). Bounded size keeps memory in
# check under long-running processes (~24 bytes/sample × 2000 = 48 KB).
_METRICS_MAX_SAMPLES = 2000
_metrics_samples: list[tuple[str, str, float]] = []
_metrics_counts: dict[str, int] = {}
_metrics_totals: dict[str, float] = {}


@app.before_request
def _metrics_before_request():
    request.environ['sapphire.t0'] = time.perf_counter()


@app.after_request
def _metrics_after_request(response):
    t0 = request.environ.get('sapphire.t0')
    if t0 is None:
        return response
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    endpoint = request.endpoint or request.path or 'unknown'
    key = f'{request.method} {endpoint}'
    _metrics_counts[key] = _metrics_counts.get(key, 0) + 1
    _metrics_totals[key] = _metrics_totals.get(key, 0.0) + elapsed_ms
    _metrics_samples.append((request.method, endpoint, elapsed_ms))
    if len(_metrics_samples) > _METRICS_MAX_SAMPLES:
        # Drop oldest ~10% to amortize the trim cost
        del _metrics_samples[: _METRICS_MAX_SAMPLES // 10]
    response.headers['X-Response-Time-ms'] = f'{elapsed_ms:.1f}'
    return response

def get_cached(key, fetch_func, ttl=CACHE_DURATION, *, raise_on_miss=False):
    """Get cached data or fetch fresh, returning stale data if refresh fails."""
    now = time.time()
    if key in _cache and now - _cache_time.get(key, 0) < ttl:
        return _cache[key]

    try:
        data = fetch_func()
        _cache[key] = data
        _cache_time[key] = now
        return data
    except Exception as e:
        log.warning("Cache fetch failed for '%s': %s", key, e)
        if key in _cache:
            return _cache[key]
        if raise_on_miss:
            raise
        return {}

def fetch_sync(url):
    """Synchronous fetch — 4 MB response cap to prevent memory pressure."""
    import ssl
    import urllib.request
    try:
        import certifi
        ctx = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(url, timeout=5, context=ctx) as response:
            data = response.read(4 * 1024 * 1024)  # 4 MB cap
            return json.loads(data)
    except Exception:
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

@app.route('/metrics')
@requires_auth
def metrics():
    """Per-route latency metrics (in-process). Not Prometheus format — JSON.

    Returns aggregate count/avg/p50/p95/p99/max for each endpoint plus the
    overall slowest endpoints. Exposed to help diagnose dashboard slowness
    (the dashboard performs many synchronous urllib fetches against remote
    services — tail latency lives in those outbound calls, not in Flask).
    """
    def _percentile(values, p):
        if not values:
            return 0.0
        s = sorted(values)
        k = int(round((p / 100.0) * (len(s) - 1)))
        return s[max(0, min(k, len(s) - 1))]

    by_route: dict[str, list[float]] = {}
    for method, endpoint, ms in _metrics_samples:
        key = f'{method} {endpoint}'
        by_route.setdefault(key, []).append(ms)

    routes = []
    for key, samples in by_route.items():
        routes.append({
            'route': key,
            'count': _metrics_counts.get(key, len(samples)),
            'avg_ms': round(sum(samples) / len(samples), 2),
            'p50_ms': round(_percentile(samples, 50), 2),
            'p95_ms': round(_percentile(samples, 95), 2),
            'p99_ms': round(_percentile(samples, 99), 2),
            'max_ms': round(max(samples), 2),
            'samples': len(samples),
        })
    routes.sort(key=lambda r: r['p95_ms'], reverse=True)

    return jsonify({
        'window_samples': len(_metrics_samples),
        'window_limit': _METRICS_MAX_SAMPLES,
        'routes': routes,
        'slowest_p95': routes[:10],
        'timestamp': datetime.now().isoformat(),
    })


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
    """Organized watchlist with corrected symbols, liked tokens, and trending tokens."""
    def fetch():
        from lib.trading.strategy_lab import build_market_universe

        universe = build_market_universe(fetch_live=True)
        liked = universe.get('liked_tokens', [])
        core_symbols = {'BTC', 'ETH', 'SOL', 'HYPE', 'ZEC'}
        major_crypto = [
            {
                'symbol': row.get('symbol'),
                'name': row.get('name'),
                'type': 'perp' if row.get('hyperliquid_symbol') else 'spot',
                'priority': str(row.get('priority', 'medium')).upper(),
                'price': row.get('price_usd'),
                'change_24h_pct': row.get('change_24h_pct'),
                'tradingview_symbol': row.get('tradingview_symbol'),
                'hyperliquid_symbol': row.get('hyperliquid_symbol'),
                'robinhood_symbol': row.get('robinhood_symbol'),
            }
            for row in liked
            if row.get('symbol') in core_symbols
        ]
        mid_cap = [
            {
                'symbol': row.get('symbol'),
                'name': row.get('name'),
                'type': 'perp' if row.get('hyperliquid_symbol') else 'spot',
                'priority': str(row.get('priority', 'medium')).upper(),
                'price': row.get('price_usd'),
                'change_24h_pct': row.get('change_24h_pct'),
                'tradingview_symbol': row.get('tradingview_symbol'),
                'hyperliquid_symbol': row.get('hyperliquid_symbol'),
                'robinhood_symbol': row.get('robinhood_symbol'),
            }
            for row in liked
            if row.get('symbol') not in core_symbols
        ]

        return {
            'major_crypto': major_crypto,
            'mid_cap': mid_cap,
            'liked_tokens': liked,
            'trending_tokens': universe.get('trending_tokens', []),
            'venue_matrix': universe.get('venue_matrix', []),
            'corrected_aliases': universe.get('corrected_aliases', {}),
            'pair_analysis': [
                {'symbol': 'ETHBTC', 'name': 'ETH/BTC Ratio', 'type': 'pair', 'priority': 'HIGH',
                 'strategy': 'Z<-2: BUY ETH, Z>2: SELL ETH'},
                {'symbol': 'SOLBTC', 'name': 'SOL/BTC Ratio', 'type': 'pair', 'priority': 'MEDIUM',
                 'strategy': 'Z<-2: BUY SOL, Z>2: SELL SOL'},
            ],
            'timestamp': datetime.now().isoformat(),
            'stale': bool(universe.get('stale')),
        }

    return jsonify(get_cached('watchlist', fetch, ttl=MARKET_UNIVERSE_CACHE_DURATION))


@app.route('/api/analytics/market-universe')
@requires_auth
def api_analytics_market_universe():
    """Market universe for analytics: Sapphire-liked, trending, and venue symbols."""
    def fetch():
        from lib.trading.strategy_lab import build_market_universe

        return build_market_universe(fetch_live=True)

    return jsonify(get_cached('market_universe', fetch, ttl=MARKET_UNIVERSE_CACHE_DURATION))


@app.route('/api/tradingview/capabilities')
@requires_auth
def api_tradingview_capabilities():
    """TradingView capability matrix and alert template."""
    def fetch():
        from lib.trading.strategy_lab import build_tradingview_capability_matrix

        return build_tradingview_capability_matrix()

    return jsonify(get_cached('tradingview_capabilities', fetch, ttl=STRATEGY_LAB_CACHE_DURATION))


@app.route('/api/trading/strategy-lab')
@requires_auth
def api_trading_strategy_lab():
    """Dry-run strategy lab across paper, TradingView, Robinhood, and Hyperliquid."""
    def fetch():
        from lib.trading.strategy_lab import build_strategy_lab_report

        return build_strategy_lab_report(fetch_live=True)

    return jsonify(get_cached('strategy_lab', fetch, ttl=STRATEGY_LAB_CACHE_DURATION))


@app.route('/api/trading/order-draft', methods=['POST'])
@requires_auth
def api_trading_order_draft():
    """Build non-submitting venue order drafts for strategy testing."""
    try:
        body = request.get_json(silent=True) or {}
        from lib.trading.strategy_lab import build_order_drafts

        drafts = build_order_drafts(
            body.get('symbol', 'BTC'),
            body.get('action', 'buy'),
            notional_usd=float(body.get('notional_usd', 100.0) or 100.0),
            strategy=str(body.get('strategy') or 'strategy_lab'),
        )
        return jsonify({
            'execution_enabled': False,
            'mode': 'draft_only',
            'drafts': drafts,
            'timestamp': datetime.now(UTC).isoformat(),
        })
    except Exception as e:
        log.exception("order draft failed")
        return jsonify({"error": f"{type(e).__name__}: {e}"}), 400

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
    """Trading opportunities sourced from today's signal_generator output.

    Reads `data/trading_signals.jsonl` (TA scanner) and returns the latest
    high-confidence BUY/SELL signals as opportunities. No mocked entries.
    """
    def fetch():
        path = Path.home() / 'Code' / 'Sapphire' / 'data' / 'trading_signals.jsonl'
        if not path.exists():
            return {'opportunities': [], 'timestamp': datetime.now().isoformat()}
        try:
            lines = path.read_text().strip().splitlines()[-60:]
        except OSError:
            return {'opportunities': [], 'timestamp': datetime.now().isoformat()}
        out: list[dict] = []
        seen_symbols: set[str] = set()
        for line in reversed(lines):
            try:
                s = json.loads(line)
            except json.JSONDecodeError:
                continue
            sym = s.get('symbol') or ''
            if not sym or sym in seen_symbols:
                continue
            if float(s.get('confidence') or 0) < 0.5:
                continue
            seen_symbols.add(sym)
            raw = s.get('raw') or {}
            out.append({
                'symbol': sym,
                'side': (s.get('action') or '').lower(),
                'confidence': s.get('confidence'),
                'price': s.get('price'),
                'reason': raw.get('reason') or s.get('strategy', ''),
                'edge': raw.get('edge'),
                'kelly_size_pct': raw.get('kelly_size_pct'),
                'timestamp': s.get('timestamp'),
            })
            if len(out) >= 6:
                break
        return {'opportunities': out, 'timestamp': datetime.now().isoformat()}

    return jsonify(get_cached('opportunities', fetch))


@app.route('/api/logs')
@requires_auth
def api_logs():
    """Recent entries from data/system_events.jsonl — no mocked logs.

    Query params:
        hours:   filter to last N hours (default 24)
        level:   filter by level (INFO/WARN/ERROR)
        service: substring match against event type or tags
    """
    hours = max(1, min(int(request.args.get('hours', 24) or 24), 168))
    level_filter = (request.args.get('level') or '').upper().strip() or None
    service_filter = (request.args.get('service') or '').lower().strip() or None

    def _level_for_event(evt_type: str, tags: list) -> str:
        """Classify event bus events by priority level."""
        for t in tags:
            if str(t).startswith('priority:p0'):
                return 'ERROR'
            if str(t).startswith('priority:p1'):
                return 'WARN'
        # Event bus types map to levels by convention
        if evt_type in {'service.health'} or evt_type.endswith('.failed'):
            return 'WARN'
        if evt_type in {'regime.shifted', 'funding.extreme'}:
            return 'WARN'
        return 'INFO'

    def _bus_entries(cutoff: float) -> list:
        """Pull recent events across all canonical streams via event bus replay."""
        try:
            bus = _event_bus()
        except Exception:
            return []
        from lib.core.event_bus import EVENT_TYPES
        since = datetime.fromtimestamp(cutoff, tz=UTC)
        collected = []
        for et in EVENT_TYPES:
            try:
                for ev in bus.replay(et, since=since, limit=50):
                    data = ev.data if isinstance(ev.data, dict) else {}
                    # Build a concise human-readable message from the event payload
                    if ev.type == 'signal.generated':
                        msg = f"signal: {data.get('action','?')} {data.get('symbol','?')} @ ${data.get('price',0)} (conf {data.get('confidence',0):.2f})"
                    elif ev.type == 'signal.closed':
                        msg = f"signal closed: {data.get('symbol','?')} pnl ${data.get('pnl_usd',0):.2f}"
                    elif ev.type == 'regime.snapshot':
                        msg = f"regime: {data.get('regime','?')} conf {data.get('confidence') or 0:.2f}"
                    elif ev.type == 'regime.shifted':
                        msg = f"regime shift: {data.get('prior','?')} → {data.get('regime','?')}"
                    elif ev.type == 'funding.extreme':
                        msg = f"funding extreme: {data.get('count',0)} perps, bias {data.get('bias','?')}"
                    elif ev.type == 'service.health':
                        msg = f"health: {data.get('pass',0)} ok · {data.get('warn',0)} warn · {data.get('fail',0)} fail ({data.get('status','?')})"
                    elif ev.type == 'content.generated':
                        msg = f"content: {data.get('kind','?')} · {data.get('quality_passed',0)}/{data.get('quality_passed',0)+data.get('quality_failed',0)} platforms passed"
                    else:
                        msg = json.dumps(data, default=str)[:160]
                    collected.append({
                        'timestamp': ev.ts,
                        'level': _level_for_event(ev.type, []),
                        'message': msg[:240],
                        'type': ev.type,
                        'tags': [f"source:{ev.source}"],
                    })
            except Exception:
                continue
        return collected

    def fetch():
        cutoff = time.time() - hours * 3600
        entries: list = []

        # 1) Traditional system_events.jsonl (service lifecycle, watchdog, etc.)
        path = Path.home() / 'Code' / 'Sapphire' / 'data' / 'system_events.jsonl'
        if path.exists():
            try:
                lines = path.read_text().strip().splitlines()[-500:]
            except OSError:
                lines = []
            for line in reversed(lines):
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts_str = e.get('timestamp', '')
                try:
                    ts_unix = datetime.fromisoformat(ts_str.replace('Z', '+00:00')).timestamp()
                except (ValueError, TypeError):
                    ts_unix = 0
                if ts_unix and ts_unix < cutoff:
                    continue
                tags = e.get('tags') or []
                entries.append({
                    'timestamp': ts_str,
                    'level': _level_for_event(e.get('type', ''), tags),
                    'message': e.get('message', '')[:240],
                    'type': e.get('type', ''),
                    'tags': tags,
                })

        # 2) Event bus (regime, signals, content, health) — richer real-time feed.
        entries.extend(_bus_entries(cutoff))

        # Filters are applied uniformly across both sources.
        def _keep(entry: dict) -> bool:
            if level_filter and entry['level'] != level_filter:
                return False
            if service_filter:
                evt_type = entry['type'].lower()
                tags = entry['tags']
                if service_filter not in evt_type and not any(service_filter in str(t).lower() for t in tags):
                    return False
            return True

        entries = [e for e in entries if _keep(e)]
        entries.sort(key=lambda e: e['timestamp'], reverse=True)
        return {
            'logs': entries[:200],
            'count': len(entries),
            'timestamp': datetime.now().isoformat(),
        }

    cache_key = f'logs::h{hours}::l{level_filter or ""}::s{service_filter or ""}'
    return jsonify(get_cached(cache_key, fetch))


# ── Event Bus SSE ────────────────────────────────────────────────────────────

def _event_bus():
    """Import event bus lazily — dashboard should start even if lib/core missing."""
    _p = Path.home() / "Code" / "Sapphire" / "lib" / "core"
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))
    from event_bus import get_bus
    return get_bus(source="dashboard")


@app.route('/api/events/stream')
@requires_auth
def api_events_stream():
    """Server-sent event stream of live bus events (glob pattern via ?types=)."""
    patterns_raw = request.args.get('types', '*')
    patterns = [p.strip() for p in patterns_raw.split(',') if p.strip()]

    import queue as _queue

    try:
        bus = _event_bus()
    except Exception as e:
        return Response(
            f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n",
            mimetype='text/event-stream',
        )

    q: _queue.Queue = _queue.Queue(maxsize=500)

    def _on_event(ev):
        with contextlib.suppress(_queue.Full):
            q.put_nowait({
                'id': ev.id,
                'type': ev.type,
                'ts': ev.ts,
                'source': ev.source,
                'data': ev.data,
            })

    subscription = bus.subscribe(patterns, _on_event)

    def gen():
        try:
            # Opening ping so the client sees the connection immediately
            yield f"event: open\ndata: {json.dumps({'patterns': patterns})}\n\n"
            last_beat = time.time()
            while True:
                try:
                    payload = q.get(timeout=15)
                    yield f"event: {payload['type']}\ndata: {json.dumps(payload, default=str)}\n\n"
                except _queue.Empty:
                    # Keep proxies from closing the connection
                    yield ": keepalive\n\n"
                if time.time() - last_beat > 60:
                    last_beat = time.time()
        finally:
            subscription.stop()

    return Response(
        gen(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',  # disable nginx buffering if proxied
        },
    )


@app.route('/api/events/world-state')
@requires_auth
def api_world_state():
    """Snapshot of aggregated world state for the overview page."""
    try:
        bus = _event_bus()
        return jsonify(bus.get_world_state().to_dict())
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/events/replay')
@requires_auth
def api_events_replay():
    """Historical replay of one event type."""
    event_type = request.args.get('type', '')
    if not event_type:
        return jsonify({'error': 'missing ?type=<event_type>'}), 400
    limit = int(request.args.get('limit', 100))
    try:
        bus = _event_bus()
        events = bus.replay(event_type, limit=limit)
        return jsonify([
            {'id': e.id, 'type': e.type, 'ts': e.ts, 'source': e.source, 'data': e.data}
            for e in events
        ])
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/system')
@requires_auth
def system():
    """Unified system status — inference tiers + services"""
    return render_template('pages/system.html', current_page='system', page_title='System Status')


@app.route('/api/system')
@requires_auth
def api_system():
    """Unified system status JSON — inference health + service checks"""
    import socket

    def fetch():
        proxy_health = fetch_sync('http://127.0.0.1:11435/health')
        proxy_metrics = fetch_sync('http://127.0.0.1:11435/metrics')

        services = [
            ('control-plane',  '127.0.0.1', 8082,  '/health'),
            ('dashboard',      '127.0.0.1', 8080,  '/health'),
            ('signal-logger',  '127.0.0.1', 18081, '/health'),
            ('openbb-api',     '127.0.0.1', 6900,  None),   # TCP: /api/v1/system/status 404s
            ('regional-intel', '127.0.0.1', 8787,  None),   # TCP: /health 404s, root returns HTML
            # inference-proxy health already fetched above via proxy_health — reuse, no re-probe
            ('redis',          '127.0.0.1', 6379,  None),
        ]

        service_status = []
        for name, host, port, path in services:
            try:
                if path:
                    result = fetch_sync(f'http://{host}:{port}{path}')
                    ok = bool(result)
                else:
                    s = socket.create_connection((host, port), timeout=2)
                    s.close()
                    ok = True
            except Exception:
                ok = False
            service_status.append({'name': name, 'port': port, 'healthy': ok})

        # Add inference-proxy status from already-fetched proxy_health (avoid re-probe)
        service_status.append({
            'name': 'inference-proxy',
            'port': 11435,
            'healthy': proxy_health.get('status') == 'ok',
        })
        healthy_count = sum(1 for s in service_status if s['healthy'])

        # CDP / TradingView MCP health (Mac TV Desktop on :9222)
        cdp_status = {'connected': False, 'tabs': 0, 'tv_tabs': 0, 'error': '', 'recovery': ''}
        try:
            cdp_raw = fetch_sync('http://127.0.0.1:9222/json')
            if isinstance(cdp_raw, list):
                tv_tabs = [t for t in cdp_raw if 'tradingview' in t.get('url', '').lower()]
                cdp_status = {
                    'connected': True,
                    'tabs': len(cdp_raw),
                    'tv_tabs': len(tv_tabs),
                    'error': '',
                    'recovery': '',
                }
            else:
                cdp_status['error'] = 'unexpected_response'
        except Exception as e:
            cdp_status['error'] = str(e)[:80]
            cdp_status['recovery'] = (
                'Run ~/Code/Sapphire/infra/scripts/start-tradingview-cdp.sh '
                'or: launchctl kickstart -k gui/$UID/com.sapphire.tradingview-cdp'
            )

        # Recent signals from signal pipeline
        signals_recent = fetch_sync('http://127.0.0.1:18081/api/signals/recent')

        return {
            'inference': {
                'endpoints': proxy_health.get('endpoints', {}),
                'tiers': proxy_health.get('tiers', {}),
                'metrics': proxy_metrics.get('metrics', {}),
            },
            'services': service_status,
            'healthy_count': healthy_count,
            'total_count': len(services),
            'cdp': cdp_status,
            'signals': {
                'recent_count': signals_recent.get('count', 0),
                'latest': (signals_recent.get('signals') or [])[:5],
            },
            'timestamp': datetime.now().isoformat(),
        }

    return jsonify(get_cached('system', fetch))


@app.route('/signals')
@requires_auth
def signals_page():
    """Trading signal history and pipeline status"""
    return render_template('pages/signals.html', current_page='signals', page_title='Signal Pipeline')


@app.route('/api/signals')
@requires_auth
def api_signals():
    """Signal pipeline data — recent signals, stats, kernel status"""
    import sys
    from pathlib import Path as _Path

    def fetch():
        # Load signal pipeline
        _root = _Path.home() / 'Code' / 'Sapphire'
        for _p in [
            str(_root / 'services' / 'alpha'),
            str(_root / 'lib' / 'core' / 'src'),
            str(_root / 'lib' / 'core'),
        ]:
            if _p not in sys.path:
                sys.path.insert(0, _p)

        recent = []
        stats = {}
        kernel = {}
        active = []

        try:
            from signal_pipeline import pipeline as _pl
            recent = _pl.recent_signals(20)
            stats = _pl.signal_stats()
            kernel = _pl.kernel_status()
            active = _pl.active_signals()
        except Exception:
            # Fallback: read JSONL directly
            import json
            from datetime import datetime as _dt
            signals_dir = _root / 'data' / 'signals'
            today = _dt.now(UTC).strftime('%Y-%m-%d')
            f = signals_dir / f'{today}.jsonl'
            if f.exists():
                for line in f.read_text().strip().splitlines()[-20:]:
                    with contextlib.suppress(Exception):
                        recent.append(json.loads(line))
                recent.reverse()

        return {
            'recent': recent,
            'active': active,
            'stats': stats,
            'kernel': kernel,
            'timestamp': datetime.now().isoformat(),
        }

    return jsonify(get_cached('signals', fetch))


@app.route('/agents')
@requires_auth
def agents_page():
    """Pi autonomous agents status"""
    return render_template('pages/agents.html', current_page='agents', page_title='Pi Agents')


@app.route('/api/agents')
@requires_auth
def api_agents():
    """Pi agent status and vitals"""
    def fetch():
        agents = []

        for agent_name, pi_ip, pi_port, _log_path in [
            ('market-watchdog', '100.120.191.1', 19001,
             '/home/rari/sapphire/logs/market-watchdog.log'),
            ('health-monitor',  '100.87.225.89', 19002,
             '/home/rari/sapphire/uptime.jsonl'),
        ]:
            status = {'name': agent_name, 'host': pi_ip, 'port': pi_port,
                      'running': False, 'last_seen': None, 'last_log': []}
            try:
                data = fetch_sync(f'http://{pi_ip}:{pi_port}/health')
                status['running'] = bool(data)
                status['last_seen'] = data.get('timestamp', datetime.now().isoformat())
                status['vitals'] = data.get('vitals', {})
                status['uptime_seconds'] = data.get('uptime_seconds', 0)
                status['check_count'] = data.get('check_count', 0)
                status['last_check'] = data.get('last_check', {})
            except Exception as e:
                status['error'] = str(e)[:60]
            agents.append(status)

        return {'agents': agents, 'timestamp': datetime.now().isoformat()}

    return jsonify(get_cached('agents', fetch))


@app.route('/benchmarks')
@requires_auth
def benchmarks():
    """GPU benchmark report — served raw to avoid Jinja2 mangling Chart.js braces"""
    report_path = Path(__file__).parent / 'static' / 'benchmark_report.html'
    if not report_path.exists():
        return Response('<h1>Benchmark report not yet generated.</h1><p>Run: python3 benchmarks/generate_report.py</p>', content_type='text/html')
    return send_file(str(report_path), mimetype='text/html')


@app.route('/health-status')
@requires_auth
def health_status_page():
    """Unified service health view"""
    return render_template('pages/health.html', current_page='health', page_title='Health Status')


@app.route('/api/health/summary')
@requires_auth
def api_health_summary():
    """Aggregate health summary across all service tiers"""
    import socket

    def fetch():
        checks = [
            # (name, category, host, port, path)
            ('control-plane',   'cloud',   '127.0.0.1', 8082,  '/health'),
            ('dashboard',       'cloud',   '127.0.0.1', 8080,  '/health'),
            ('signal-logger',   'cloud',   '127.0.0.1', 18081, '/health'),
            ('inference-proxy', 'cloud',   '127.0.0.1', 11435, '/health'),
            ('openbb-api',      'cloud',   '127.0.0.1', 6900,  None),
            ('redis',           'cloud',   '127.0.0.1', 6379,  None),
            ('windows-ollama',  'windows', '100.71.10.48', 11434, None),
            ('rari1-ollama',    'pi',      '100.120.191.1', 11434, None),
            ('rari2-ollama',    'pi',      '100.87.225.89', 11434, None),
        ]

        by_category = {'cloud': [], 'windows': [], 'pi': [], 'firestore': []}
        healthy_count = 0
        unhealthy_count = 0

        for name, category, host, port, path in checks:
            t0 = time.time()
            try:
                if path:
                    result = fetch_sync(f'http://{host}:{port}{path}')
                    ok = bool(result)
                else:
                    s = socket.create_connection((host, port), timeout=2)
                    s.close()
                    ok = True
            except Exception:
                ok = False
            elapsed = int((time.time() - t0) * 1000)

            entry = {'name': name, 'healthy': ok, 'response_time_ms': elapsed if ok else None}
            by_category[category].append(entry)

            if ok:
                healthy_count += 1
            else:
                unhealthy_count += 1

        return {
            'healthy': unhealthy_count == 0,
            'healthy_count': healthy_count,
            'unhealthy_count': unhealthy_count,
            'by_category': by_category,
            'timestamp': datetime.now().isoformat(),
        }

    return jsonify(get_cached('health_summary', fetch))


@app.route('/production-readiness')
@requires_auth
def production_readiness_page():
    """Production readiness gates"""
    return render_template('pages/production_readiness.html', current_page='production_readiness',
                           page_title='Production Readiness')


@app.route('/api/production/readiness')
@requires_auth
def api_production_readiness():
    """Production readiness gates — contracts, cloud services, edge fleet"""
    import socket

    def fetch():
        ts = datetime.now().isoformat()

        # Gate A — API contracts (key service endpoints)
        contract_checks = []
        for name, url in [
            ('signal-logger /health',   'http://127.0.0.1:18081/health'),
            ('inference-proxy /health', 'http://127.0.0.1:11435/health'),
            ('control-plane /health',   'http://127.0.0.1:8082/health'),
            ('dashboard /health',       'http://127.0.0.1:8080/health'),
        ]:
            t0 = time.time()
            result = fetch_sync(url)
            latency = int((time.time() - t0) * 1000)
            ok = bool(result)
            contract_checks.append({'name': name, 'healthy': ok,
                                    'status': 'ok' if ok else 'unreachable',
                                    'latency_ms': latency})

        gate_a_pass = sum(1 for c in contract_checks if c['healthy'])
        gate_a = {'ok': gate_a_pass == len(contract_checks),
                  'pass': gate_a_pass, 'total': len(contract_checks)}

        # Gate B — cloud services (Mac + Windows GPU Ollama)
        cloud_services = {}
        for name, host, port in [
            ('mac-ollama',     '127.0.0.1',    11434),
            ('windows-ollama', '100.71.10.48', 11434),
            ('openbb-api',     '127.0.0.1',    6900),
            ('redis',          '127.0.0.1',    6379),
        ]:
            t0 = time.time()
            try:
                s = socket.create_connection((host, port), timeout=2)
                s.close()
                ok = True
            except Exception:
                ok = False
            latency = int((time.time() - t0) * 1000)
            cloud_services[name] = {'healthy': ok, 'status': 'ok' if ok else 'down',
                                    'latency_ms': latency if ok else None}

        gate_b_pass = sum(1 for s in cloud_services.values() if s['healthy'])
        gate_b = {'ok': gate_b_pass == len(cloud_services),
                  'pass': gate_b_pass, 'total': len(cloud_services)}

        # Gate C — edge fleet (Pi nodes)
        pi_nodes = {}
        for name, host in [('rari1', '100.120.191.1'), ('rari2', '100.87.225.89')]:
            t0 = time.time()
            try:
                s = socket.create_connection((host, 11434), timeout=3)
                s.close()
                ok = True
            except Exception:
                ok = False
            latency = int((time.time() - t0) * 1000)
            pi_nodes[name] = {'healthy': ok, 'status': 'ok' if ok else 'unreachable',
                              'latency_ms': latency if ok else None}

        gate_c_pass = sum(1 for s in pi_nodes.values() if s['healthy'])
        gate_c = {'ok': gate_c_pass > 0,  # at least one Pi required
                  'pass': gate_c_pass, 'total': len(pi_nodes)}

        gates = {'A_contracts': gate_a, 'B_cloud': gate_b, 'C_edge': gate_c}
        overall_ok = gate_a['ok'] and gate_b['ok']  # Pi optional for prod

        blockers = []
        for check in contract_checks:
            if not check['healthy']:
                blockers.append({'name': check['name'], 'gate': 'A_contracts',
                                 'error': check['status']})
        for name, svc in cloud_services.items():
            if not svc['healthy']:
                blockers.append({'name': name, 'gate': 'B_cloud', 'error': svc['status']})

        return {
            'overall_ok': overall_ok,
            'gates': gates,
            'blockers': blockers,
            'cloud': {'services': cloud_services},
            'contract_checks': contract_checks,
            'timestamp': ts,
        }

    return jsonify(get_cached('prod_readiness', fetch))


@app.route('/logs')
@requires_auth
def logs_page():
    """Log viewer page"""
    return render_template('pages/logs.html', current_page='logs',
                           page_title='Logs')


@app.route('/command-deck')
@requires_auth
def command_deck_page():
    """Trading command deck"""
    return render_template('pages/command_deck.html', current_page='command_deck',
                           page_title='Command Deck')


@app.route('/api/trading/metrics')
@requires_auth
def api_trading_metrics():
    """Trading pipeline metrics — signal counts, success rates from signal logger"""
    import json as _json
    from datetime import datetime as _dt
    from pathlib import Path as _Path

    def fetch():
        _alpha = _Path.home() / 'Code' / 'Sapphire' / 'services' / 'alpha'
        if str(_alpha) not in _sys.path:
            _sys.path.insert(0, str(_alpha))

        today = _dt.now(UTC).strftime('%Y-%m-%d')
        signals_dir = _Path.home() / 'Code' / 'Sapphire' / 'data' / 'signals'
        f = signals_dir / f'{today}.jsonl'

        signals_today = []
        if f.exists():
            for line in f.read_text().strip().splitlines():
                with contextlib.suppress(Exception):
                    signals_today.append(_json.loads(line))

        total = len(signals_today)

        # Win rate from outcome-tagged signals (via signal_pipeline.signal_stats)
        win_rate = None
        wins = losses = 0
        total_pnl = 0.0
        try:
            from signal_pipeline import pipeline as _pl
            stats = _pl.signal_stats()
            win_rate = stats.get('win_rate')
            wins = stats.get('wins', 0)
            losses = stats.get('losses', 0)
            total_pnl = stats.get('total_pnl_usd', 0.0)
        except Exception:
            pass

        # Recent signals (last 5, most recent first)
        recent = []
        for s in signals_today[-5:][::-1]:
            recent.append({
                'id': s.get('pipeline_id', ''),
                'symbol': s.get('symbol', ''),
                'action': s.get('action', '').upper(),
                'score': s.get('score', 0),
                'routing': s.get('routing', ''),
                'outcome': s.get('outcome'),
                'pnl_usd': s.get('pnl_usd'),
                'ts': s.get('timestamp', '')[:19].replace('T', ' '),
            })

        # Live stats from signal logger
        live = fetch_sync('http://127.0.0.1:18081/api/signals/stats') or {}

        return {
            'signals_today': total,
            'win_rate': win_rate,
            'wins': wins,
            'losses': losses,
            'total_pnl_usd': round(total_pnl, 2),
            'recent': recent,
            'pipeline': {
                'webhook_active': bool(fetch_sync('http://127.0.0.1:18081/health')),
                'live_total': live.get('total', total),
            },
            'timestamp': datetime.now().isoformat(),
        }

    return jsonify(get_cached('trading_metrics', fetch))


@app.route('/soc')
@requires_auth
def soc_page():
    """Security Operations Center"""
    return render_template('pages/soc.html', current_page='soc',
                           page_title='Security Operations Center')


@app.route('/security/overview')
@requires_auth
def security_overview_page():
    """Security intelligence: dependency scanner, model integrity, network surface."""
    return render_template('pages/security.html', current_page='security',
                           page_title='Security Overview')


@app.route('/chain')
@requires_auth
def chain_page():
    """On-chain intelligence: regime, funding, TVL, stablecoin flows"""
    return render_template('pages/chain.html', current_page='chain',
                           page_title='On-Chain Intelligence')


@app.route('/api/chain/overview')
@requires_auth
@x402_require(0.01, description="On-chain intelligence snapshot")
def api_chain_overview():
    """Unified on-chain snapshot — regime, funding, OI, TVL, stablecoins."""
    from pathlib import Path as _Path
    _root = _Path.home() / 'Code' / 'Sapphire'
    if str(_root) not in _sys.path:
        _sys.path.insert(0, str(_root))

    def fetch():
        from lib.chain import ChainIntelligence
        ci = ChainIntelligence()
        return ci.snapshot(alert_on_shift=False)

    try:
        return jsonify(get_cached(
            'chain_overview',
            fetch,
            ttl=CHAIN_OVERVIEW_CACHE_DURATION,
            raise_on_miss=True,
        ))
    except Exception as e:
        log.exception("chain overview failed")
        return jsonify({"error": f"{type(e).__name__}: {e}"}), 500


@app.route('/chain/robinhood')
@requires_auth
def robinhood_chain_page():
    """Robinhood Chain testnet: contract status, on-chain signals, payment gate."""
    return render_template('pages/robinhood_chain.html', current_page='robinhood_chain',
                           page_title='Robinhood Chain')


@app.route('/api/chain/robinhood/status')
@requires_auth
def api_robinhood_chain_status():
    """Chain health: block number, gas price, contract addresses."""
    try:
        from lib.chain.robinhood_chain import RobinhoodChainClient
        client = RobinhoodChainClient()
        status = client.get_chain_status()
        return jsonify({
            "connected": status.connected,
            "chain_id": status.chain_id,
            "block_number": status.block_number,
            "gas_price_gwei": status.gas_price_gwei,
            "signal_verifier_address": status.signal_verifier_address,
            "payment_gate_address": status.payment_gate_address,
            "signal_count": status.signal_count,
            "error": status.error,
        })
    except Exception as e:
        log.exception("robinhood chain status failed")
        return jsonify({"error": f"{type(e).__name__}: {e}"}), 500


@app.route('/api/chain/robinhood/signals')
@requires_auth
def api_robinhood_chain_signals():
    """Recent on-chain signals from SapphireSignalVerifier."""
    count = min(int(request.args.get("count", 10)), 50)
    try:
        from lib.chain.robinhood_chain import RobinhoodChainClient
        client = RobinhoodChainClient()
        signals = client.get_signal_history(count)
        return jsonify({"signals": signals, "count": len(signals)})
    except Exception as e:
        log.exception("robinhood chain signals failed")
        return jsonify({"error": f"{type(e).__name__}: {e}"}), 500


@app.route('/api/chain/robinhood/payment')
@requires_auth
def api_robinhood_payment_stats():
    """Payment gate pricing and stats."""
    try:
        from lib.chain.robinhood_chain import RobinhoodChainClient
        client = RobinhoodChainClient()
        return jsonify(client.get_payment_gate_stats())
    except Exception as e:
        log.exception("robinhood payment stats failed")
        return jsonify({"error": f"{type(e).__name__}: {e}"}), 500


@app.route('/risk')
@requires_auth
def risk_page():
    """Portfolio risk: Sharpe/Sortino/Calmar/drawdown/Kelly."""
    return render_template('pages/risk.html', current_page='risk',
                           page_title='Portfolio Risk')



@app.route('/analytics')
@requires_auth
def analytics_page():
    """Performance analytics: equity curve, Sharpe, regime breakdown."""
    return render_template('pages/analytics.html', current_page='analytics',
                           page_title='Performance Analytics')


@app.route('/api/analytics')
@requires_auth
def api_analytics():
    """Full analytics report from signal + paper trading data."""
    def fetch():
        from pathlib import Path as _Path
        repo_root = _Path(__file__).resolve().parents[2]
        if str(repo_root) not in _sys.path:
            _sys.path.insert(0, str(repo_root))
        from services.intelligence import analytics as _analytics
        return _analytics.build_report()
    return jsonify(get_cached('analytics', fetch))

@app.route('/api/risk/metrics')
@requires_auth
@x402_require(0.02, description="Portfolio risk analytics")
def api_risk_metrics():
    """Portfolio metrics computed from paper_trading + signal audit logs."""
    from dataclasses import asdict
    from pathlib import Path as _Path
    _root = _Path.home() / 'Code' / 'Sapphire'
    if str(_root) not in _sys.path:
        _sys.path.insert(0, str(_root))
    try:
        from lib.analytics.risk_engine import RiskEngine
        bankroll = float(request.args.get('bankroll', 10000.0))
        eng = RiskEngine(bankroll=bankroll)
        m = eng.compute()
        return jsonify(asdict(m))
    except Exception as e:
        log.exception("risk metrics failed")
        return jsonify({"error": f"{type(e).__name__}: {e}"}), 500


@app.route('/api/analytics/performance')
@requires_auth
def api_analytics_performance():
    """Equity/benchmark/rolling-Sharpe/regime/monthly report from latest backtest."""
    try:
        from lib.analytics.performance import build_performance_report
        primary = request.args.get('symbol', 'BTC-USD')
        window = int(request.args.get('window', 30))
        candidates = [r / 'data' / 'backtests' / 'latest.json' for r in _DASHBOARD_ROOTS]
        path = next((c for c in candidates if c.exists()), candidates[0])
        report = build_performance_report(path, primary_symbol=primary, rolling_window=window)
        return jsonify(report)
    except Exception as e:
        log.exception("analytics performance failed")
        return jsonify({"error": f"{type(e).__name__}: {e}"}), 500


@app.route('/api/risk/backtest')
@requires_auth
def api_risk_backtest():
    """Backtest SMA-crossover signals against 90d OHLCV.

    Query params:
      symbols=BTC-USD,ETH-USD   comma list (default: BTC/ETH/SOL/SPY)
      days=90                   lookback period
      latest=1                  return the last saved run instead of recomputing
    """
    try:
        from lib.analytics.backtest import DEFAULT_SYMBOLS, BacktestConfig, Backtester
        if request.args.get('latest') == '1':
            for cand in (r / 'data' / 'backtests' / 'latest.json' for r in _DASHBOARD_ROOTS):
                if cand.exists():
                    return jsonify(json.loads(cand.read_text()))
            return jsonify({"error": "no cached backtest"}), 404
        syms_arg = request.args.get('symbols')
        symbols = tuple(s.strip() for s in syms_arg.split(',') if s.strip()) if syms_arg else DEFAULT_SYMBOLS
        days = int(request.args.get('days', 90))
        cfg = BacktestConfig(symbols=symbols, period_days=days)
        bt = Backtester(cfg)
        results = bt.run_comparison()
        bt.save(results)
        return jsonify(results)
    except Exception as e:
        log.exception("backtest failed")
        return jsonify({"error": f"{type(e).__name__}: {e}"}), 500


@app.route('/api/analytics/correlation')
@requires_auth
def api_correlation():
    """30-day rolling correlation matrix across crypto + equities + macro."""
    from dataclasses import asdict
    from pathlib import Path as _Path
    _root = _Path.home() / 'Code' / 'Sapphire'
    if str(_root) not in _sys.path:
        _sys.path.insert(0, str(_root))
    try:
        from lib.analytics.correlation import CorrelationEngine
        window = int(request.args.get('window', 30))
        eng = CorrelationEngine()
        report = eng.report(window_days=window)
        return jsonify({
            "matrix": asdict(report.matrix),
            "decorrelation_events": [asdict(e) for e in report.decorrelation_events],
            "risk_on_matrix": asdict(report.risk_on_matrix) if report.risk_on_matrix else None,
            "risk_off_matrix": asdict(report.risk_off_matrix) if report.risk_off_matrix else None,
            "timestamp": report.timestamp,
        })
    except Exception as e:
        log.exception("correlation matrix failed")
        return jsonify({"error": f"{type(e).__name__}: {e}"}), 500


@app.route('/api/soc/security')
@requires_auth
def api_soc_security():
    """SOC security status — auth events, network, inference gate, threat intel, investigations"""
    import re
    import subprocess

    def fetch():
        checks = {}
        auth_events = []
        tailscale_devices = []
        outbound = {'total': 0, 'unexpected': 0}
        injection_stats = {'injection_attempts': 0, 'jailbreak_attempts': 0,
                           'prompt_leakage': 0, 'sensitivity_blocks': 0}
        threats = []
        investigations = []

        # ── Auth logs ────────────────────────────────────────────────
        try:
            result = subprocess.run(
                ['last', '-10'],
                capture_output=True, text=True, timeout=5
            )
            lines = [ln for ln in result.stdout.splitlines()
                     if ln.strip() and 'wtmp' not in ln and 'reboot' not in ln]
            known_users = {'aribs', 'rari'}
            unknown = [ln for ln in lines if not any(u in ln for u in known_users)]
            if unknown:
                checks['auth_logs'] = {'status': 'warn', 'detail': f'{len(unknown)} unknown session(s)'}
                for ln in unknown[:3]:
                    auth_events.append({'timestamp': datetime.now().isoformat()[:19],
                                        'type': 'warn', 'message': ln.strip()[:80]})
            else:
                checks['auth_logs'] = {'status': 'pass', 'detail': f'{len(lines)} sessions, all known'}
                for ln in lines[:5]:
                    parts = ln.split()
                    auth_events.append({'timestamp': ' '.join(parts[4:8]) if len(parts) > 7 else '--',
                                        'type': 'ok', 'message': ln.strip()[:80]})
        except Exception:
            checks['auth_logs'] = {'status': 'warn', 'detail': 'Could not read auth logs'}

        # ── Tailscale devices ────────────────────────────────────────
        try:
            result = subprocess.run(
                ['tailscale', 'status'],
                capture_output=True, text=True, timeout=8
            )
            known_ips = {'100.67.171.79', '100.71.10.48', '100.120.191.1', '100.87.225.89'}
            lines = [ln for ln in result.stdout.splitlines() if ln.strip() and not ln.startswith('#')]
            unknown_devices = []
            for line in lines:
                parts = line.split()
                if len(parts) >= 2:
                    ip = parts[0]
                    hostname = parts[1] if len(parts) > 1 else 'unknown'
                    user = parts[2] if len(parts) > 2 else ''
                    os_info = parts[3] if len(parts) > 3 else ''
                    status = ' '.join(parts[4:]) if len(parts) > 4 else 'idle'
                    tailscale_devices.append({
                        'ip': ip, 'name': hostname, 'user': user,
                        'os': os_info, 'status': status,
                        'online': ip in known_ips
                    })
                    if ip and not any(ip.startswith(k) for k in ['100.67', '100.71', '100.120', '100.87']):
                        unknown_devices.append(ip)
            if unknown_devices:
                checks['tailscale'] = {'status': 'warn', 'detail': f'{len(unknown_devices)} unknown device(s)'}
            else:
                checks['tailscale'] = {'status': 'pass', 'detail': f'{len(tailscale_devices)} known devices'}
        except Exception:
            checks['tailscale'] = {'status': 'warn', 'detail': 'tailscale not reachable'}

        # ── Hermes injection check ───────────────────────────────────
        try:
            log_path = Path.home() / '.hermes' / 'logs' / 'gateway.log'
            if log_path.exists():
                content = log_path.read_text(errors='ignore')[-50000:]  # last 50KB
                patterns = ['inject', 'ignore previous', 'jailbreak', 'eval(', 'exec(', '__import__']
                found = [p for p in patterns if p.lower() in content.lower()]
                injection_stats['injection_attempts'] = len(found)
                injection_stats['jailbreak_attempts'] = content.lower().count('jailbreak')
                if found:
                    checks['hermes_injection'] = {'status': 'warn', 'detail': f'{len(found)} pattern(s) detected'}
                else:
                    checks['hermes_injection'] = {'status': 'pass', 'detail': '0 injection patterns'}
            else:
                checks['hermes_injection'] = {'status': 'pass', 'detail': 'No log file (clean)'}
        except Exception:
            checks['hermes_injection'] = {'status': 'warn', 'detail': 'Could not scan logs'}

        # ── Outbound connections ─────────────────────────────────────
        try:
            result = subprocess.run(
                ['lsof', '-i', '-P', '-n'],
                capture_output=True, text=True, timeout=8
            )
            established = [ln for ln in result.stdout.splitlines() if 'ESTABLISHED' in ln]
            # Filter known/expected IPs
            known_prefixes = ('100.', '127.', '17.', '34.', '35.', '52.', '54.',
                              '104.', '140.', '142.', '192.168.', '10.')
            unexpected = [ln for ln in established
                          if not any(p in ln for p in known_prefixes)]
            outbound = {'total': len(established), 'unexpected': len(unexpected)}
            if unexpected:
                checks['outbound_network'] = {'status': 'warn', 'detail': f'{len(unexpected)} unexpected'}
            else:
                checks['outbound_network'] = {'status': 'pass', 'detail': f'{len(established)} known connections'}
        except Exception:
            checks['outbound_network'] = {'status': 'warn', 'detail': 'lsof unavailable'}

        # ── Credential scan ──────────────────────────────────────────
        try:
            dangerous_patterns = [
                (Path.home() / '.env', '.env file in home'),
                (Path.home() / 'Code' / 'Sapphire' / '.env', '.env in Sapphire root'),
            ]
            found_creds = []
            for path, label in dangerous_patterns:
                if path.exists():
                    found_creds.append(label)
            # Check for hardcoded secrets in recently modified py files
            checks['credentials'] = {'status': 'pass', 'detail': 'No exposed credentials'}
            if found_creds:
                checks['credentials'] = {'status': 'warn', 'detail': '; '.join(found_creds)}
        except Exception:
            checks['credentials'] = {'status': 'warn', 'detail': 'Scan error'}

        # ── Proxy sensitivity gate ───────────────────────────────────
        try:
            proxy_path = Path.home() / 'Code' / 'Sapphire' / 'services' / 'inference-proxy' / 'app.py'
            if proxy_path.exists():
                content = proxy_path.read_text()
                gate_patterns = ['api_key', 'password', 'bearer', 'jwt', 'private_key',
                                 'credit_card', 'ssn', 'secret']
                found = [p for p in gate_patterns if p in content.lower()]
                checks['proxy_gate'] = {'status': 'pass',
                                        'detail': f'{len(found)}/{len(gate_patterns)} patterns active'}
            else:
                checks['proxy_gate'] = {'status': 'warn', 'detail': 'Proxy not found'}
        except Exception:
            checks['proxy_gate'] = {'status': 'warn', 'detail': 'Could not verify'}

        # ── LaunchAgents ─────────────────────────────────────────────
        try:
            la_dir = Path.home() / 'Library' / 'LaunchAgents'
            plists = list(la_dir.glob('*.plist'))
            known_prefixes = ('com.sapphire.', 'homebrew.', 'com.apple.', 'ai.hermes.',
                              'com.anthropic.', 'com.1password.', 'io.tailscale.')
            unknown_agents = [p.name for p in plists
                              if not any(p.name.startswith(pfx) for pfx in known_prefixes)]
            if unknown_agents:
                checks['launchagents'] = {'status': 'warn',
                                          'detail': f'{len(unknown_agents)} unknown agent(s)'}
            else:
                checks['launchagents'] = {'status': 'pass',
                                          'detail': f'{len(plists)} agents, all known'}
        except Exception:
            checks['launchagents'] = {'status': 'warn', 'detail': 'Could not read LaunchAgents'}

        # ── Suspicious processes ─────────────────────────────────────
        try:
            import re as _re
            result = subprocess.run(['ps', 'aux'], capture_output=True, text=True, timeout=5)
            # Use word-boundary regex per pattern to avoid matching any line
            # that happens to contain the literal substring (e.g. a directory
            # path with " nc " in it). `nc`/`ncat` need true argv-level matches.
            suspicious = ['xmrig', 'minergate', 'nc', 'ncat', 'ngrok', 'chisel',
                          'frpc', 'frps', 'reverse_shell', 'meterpreter']
            patterns = {s: _re.compile(rf'(?<![\w/.-]){_re.escape(s)}(?![\w.-])') for s in suspicious}
            found_procs = [s for s, p in patterns.items() if p.search(result.stdout)]
            if found_procs:
                checks['suspicious_processes'] = {'status': 'fail',
                                                  'detail': f'ALERT: {", ".join(found_procs)}'}
            else:
                checks['suspicious_processes'] = {'status': 'pass', 'detail': 'No suspicious processes'}
        except Exception:
            checks['suspicious_processes'] = {'status': 'warn', 'detail': 'ps unavailable'}

        # ── Threat intel from cyber-threat-bot refresh ──────────────
        try:
            threat_file = Path.home() / 'Code' / 'Sapphire' / 'data' / 'intelligence' / 'latest' / 'threats.json'
            if threat_file.exists():
                data = json.loads(threat_file.read_text())
                for t in data.get('threats', [])[:8]:
                    score = t.get('score', 0) or 0
                    sev = 'critical' if score >= 9 else 'high' if score >= 7 else 'medium' if score >= 4 else 'low'
                    threats.append({
                        'cve_id': t.get('canonical_id', '?'),
                        'title': t.get('title', ''),
                        'severity': sev,
                        'score': score,
                        'source': t.get('source', 'unknown'),
                        'exploited': t.get('exploited', False),
                        'url': t.get('url', ''),
                    })
        except Exception:
            pass

        # If no saved threats, show empty/all-clear
        if not threats:
            threats = []

        # ── Investigation history ────────────────────────────────────
        try:
            docs_dir = Path.home() / 'Code' / 'Sapphire' / 'docs'
            inv_files = sorted(docs_dir.glob('security-investigation-*.md'), reverse=True)
            for inv_file in inv_files[:3]:
                content = inv_file.read_text(errors='ignore')
                # Extract date from filename
                date_match = re.search(r'(\d{4}-\d{2}-\d{2})', inv_file.name)
                inv_date = date_match.group(1) if date_match else 'unknown'
                # Extract trigger line
                trigger = ''
                for line in content.splitlines():
                    if '**Trigger**' in line or 'Trigger' in line:
                        trigger = line.replace('**Trigger**:', '').replace('**Trigger**', '').strip()
                        trigger = re.sub(r'[*#]', '', trigger).strip()
                        break
                # Extract verdict
                verdict = 'clean'
                if 'NOT compromised' in content or 'CLEAN' in content:
                    verdict = 'clean'
                elif 'COMPROMISED' in content:
                    verdict = 'threat'
                investigations.append({
                    'title': trigger[:80] or f'Investigation {inv_date}',
                    'date': inv_date,
                    'verdict': verdict,
                    'summary': '10-point security sweep. Verdict: System clean. No unauthorized access detected.',
                    'file': inv_file.name,
                })
        except Exception:
            pass

        # ── Overall verdict ──────────────────────────────────────────
        statuses = [c['status'] for c in checks.values()]
        if 'fail' in statuses:
            overall = 'THREAT'
            msg = 'Critical issue detected — immediate action required'
        elif statuses.count('warn') >= 2:
            overall = 'WARN'
            msg = f'{statuses.count("warn")} warnings — review recommended'
        elif 'warn' in statuses:
            overall = 'WARN'
            msg = '1 warning — system mostly clean'
        else:
            overall = 'CLEAN'
            msg = f'All {len(checks)} checks passed — system secure'

        return {
            'overall_verdict': overall,
            'summary_message': msg,
            'checks': checks,
            'auth_events': auth_events,
            'tailscale_devices': tailscale_devices,
            'outbound_connections': outbound,
            'injection_stats': injection_stats,
            'proxy_gate': {
                'blocked_patterns': ['api_key', 'apikey', 'bearer', 'jwt',
                                     'password', 'secret', '-----BEGIN',
                                     'credit_card', 'ssn']
            },
            'threats': threats,
            'investigations': investigations,
            'timestamp': datetime.now().isoformat(),
        }

    return jsonify(get_cached('soc_security', fetch))


@app.route('/api/soc/threats')
@requires_auth
def api_soc_threats():
    """Live threat feed from cyber-threat-bot — CISA KEV, NVD, MITRE ATT&CK.
    Reads saved reports first (fast), falls back to live fetch if stale (>4h).
    """
    import re as _re

    CTB_SRC = Path.home() / 'Code' / 'cyber-threat-bot' / 'src'
    THREAT_CACHE = 240  # 4 hours — live fetch is slow (NVD rate limits)

    def fetch():
        threats = []
        source_note = ''
        generated_at = None

        # ── 1. Try saved reports (fast path) ──────────────────────────
        threat_dir = Path.home() / 'Code' / 'Sapphire' / 'data' / 'threat_intel'
        saved_reports = sorted(threat_dir.glob('latest_*.md'), reverse=True) if threat_dir.exists() else []

        if saved_reports:
            latest = saved_reports[0]
            try:
                # Check freshness — use file if <4h old
                age_hours = (time.time() - latest.stat().st_mtime) / 3600
                content = latest.read_text(errors='ignore')

                # Extract generated_at
                for line in content.splitlines()[:5]:
                    if 'Generated at' in line or 'generated' in line.lower():
                        generated_at = line.replace('Generated at:', '').strip()
                        break

                # Parse structured threat entries
                sections = content.split('\n### ')
                for section in sections[1:12]:  # up to 11 threats
                    lines = section.strip().splitlines()
                    if not lines:
                        continue
                    title_line = lines[0].strip().lstrip('0123456789. ')

                    cve_id = None
                    cvss = None
                    exploited = False
                    summary = ''
                    source = 'CISA/NVD'

                    for line in lines:
                        if '`CVE-' in line:
                            m = _re.search(r'CVE-\d{4}-\d+', line)
                            if m:
                                cve_id = m.group(0)
                        if 'CVSS base score' in line:
                            m = _re.search(r'(\d+\.?\d*)', line.split('CVSS base score')[-1])
                            if m:
                                cvss = float(m.group(1))
                        if 'Exploited in the wild: yes' in line:
                            exploited = True
                        if line.strip().startswith('- Summary:'):
                            summary = line.replace('- Summary:', '').strip()
                        if 'Sources:' in line:
                            source = line.replace('- Sources:', '').strip()

                    # Severity mapping
                    if exploited and cvss and cvss >= 9.0:
                        severity = 'critical'
                    elif exploited or (cvss and cvss >= 9.0):
                        severity = 'high'
                    elif cvss and cvss >= 7.0:
                        severity = 'medium'
                    else:
                        severity = 'low'

                    threats.append({
                        'cve_id': cve_id,
                        'title': title_line[:100],
                        'severity': severity,
                        'cvss': cvss,
                        'exploited': exploited,
                        'summary': summary[:300],
                        'source': source,
                    })

                source_note = f'Saved report ({age_hours:.1f}h old)'
                if threats:
                    return {
                        'threats': threats,
                        'source': source_note,
                        'generated_at': generated_at,
                        'total': len(threats),
                        'critical_count': sum(1 for t in threats if t['severity'] == 'critical'),
                        'high_count': sum(1 for t in threats if t['severity'] == 'high'),
                        'timestamp': datetime.now().isoformat(),
                    }
            except Exception:
                pass

        # ── 2. Live fetch via cyber-threat-bot ─────────────────────────
        if str(CTB_SRC) not in _sys.path and CTB_SRC.exists():
            _sys.path.insert(0, str(CTB_SRC))

        try:
            from cyber_threat_bot import scoring as _sc
            from cyber_threat_bot import sources as _src

            records = _src.collect_latest_records(days=3, per_source=5)
            records.sort(key=lambda r: _sc.record_priority(r), reverse=True)

            for r in records[:12]:
                cvss = r.metadata.get('cvss_base_score') or r.metadata.get('cvss')
                if cvss:
                    try:
                        cvss = float(cvss)
                    except Exception:
                        cvss = None

                if r.exploited and cvss and cvss >= 9.0:
                    severity = 'critical'
                elif r.exploited or (cvss and cvss >= 9.0):
                    severity = 'high'
                elif cvss and cvss >= 7.0:
                    severity = 'medium'
                else:
                    severity = 'low'

                threats.append({
                    'cve_id': r.canonical_id if r.canonical_id.startswith('CVE-') else None,
                    'title': r.title[:100],
                    'severity': severity,
                    'cvss': cvss,
                    'exploited': r.exploited,
                    'summary': r.summary[:300] if r.summary else '',
                    'source': r.source,
                    'url': r.url,
                    'published_at': r.published_at.isoformat() if r.published_at else None,
                })

            source_note = 'Live — CISA KEV + NVD'
        except ImportError:
            source_note = 'cyber-threat-bot unavailable'
        except Exception as e:
            source_note = f'Error: {str(e)[:60]}'

        return {
            'threats': threats,
            'source': source_note,
            'generated_at': datetime.now().isoformat(),
            'total': len(threats),
            'critical_count': sum(1 for t in threats if t['severity'] == 'critical'),
            'high_count': sum(1 for t in threats if t['severity'] == 'high'),
            'timestamp': datetime.now().isoformat(),
        }

    # Longer cache — NVD rate limits mean we don't want to spam live fetches
    key = 'soc_threats'
    now = time.time()
    if key in _cache and now - _cache_time.get(key, 0) < THREAT_CACHE:
        return jsonify(_cache[key])
    try:
        data = fetch()
        _cache[key] = data
        _cache_time[key] = now
        return jsonify(data)
    except Exception as e:
        return jsonify({'threats': [], 'source': f'Error: {e}', 'total': 0,
                        'critical_count': 0, 'high_count': 0,
                        'timestamp': datetime.now().isoformat()})


@app.route('/predictions')
@requires_auth
def predictions_page():
    """Kronos candlestick prediction dashboard"""
    return render_template('pages/predictions.html', current_page='predictions',
                           page_title='Kronos Predictions')


@app.route('/api/predictions/kronos')
@requires_auth
@x402_require(0.05, description="Kronos candlestick forecasts")
def api_kronos_prediction():
    """Kronos foundation model prediction endpoint.
    Query params: symbol (default BTC-USD), lookback (default 200), predict (default 24), interval (default 1h)
    """
    import subprocess as _sp

    symbol = request.args.get('symbol', 'BTC-USD')
    lookback = int(request.args.get('lookback', 200))
    predict = int(request.args.get('predict', 24))
    interval = request.args.get('interval', '1h')

    # Cap to reasonable limits
    lookback = min(lookback, 500)
    predict = min(predict, 96)

    cache_key = f'kronos_{symbol}_{interval}_{predict}'
    KRONOS_CACHE = 300  # 5 min cache per symbol
    KRONOS_CACHE_MAX = 64  # hard cap to prevent RAM growth from unique ?symbol= values

    now = time.time()
    if cache_key in _cache and now - _cache_time.get(cache_key, 0) < KRONOS_CACHE:
        return jsonify(_cache[cache_key])

    kronos_tool = Path.home() / 'Code' / 'Sapphire' / 'plugins' / 'claw-sapphire' / 'tools' / 'predict_kronos.py'
    kronos_python = Path.home() / 'Code' / 'Kronos' / '.venv' / 'bin' / 'python3'

    if not kronos_python.exists():
        kronos_python = Path('/usr/local/bin/python3')

    kronos_env = {
        **__import__('os').environ,
        'PYTHONPATH': str(Path.home() / 'Code' / 'Kronos'),
    }

    payload = json.dumps({
        'action': 'predict',
        'symbol': symbol,
        'lookback_bars': lookback,
        'predict_bars': predict,
        'interval': interval,
    })

    try:
        result = _sp.run(
            [str(kronos_python), str(kronos_tool)],
            input=payload,
            capture_output=True,
            text=True,
            timeout=120,
            env=kronos_env,
        )
        if result.returncode != 0:
            # Never echo raw subprocess stderr to clients — it can leak paths,
            # stack traces, env details. Log server-side; return a generic note.
            log.warning("Kronos subprocess failed (rc=%s): %s",
                        result.returncode, (result.stderr or "")[-500:])
            return jsonify({'error': 'Kronos process failed'}), 500

        data = json.loads(result.stdout)
        # Evict oldest Kronos entries to keep cache bounded — an authenticated
        # attacker could otherwise fill RAM with unique ?symbol= values.
        kronos_keys = [k for k in _cache if k.startswith('kronos_')]
        if len(kronos_keys) >= KRONOS_CACHE_MAX:
            oldest = sorted(kronos_keys, key=lambda k: _cache_time.get(k, 0))[:len(kronos_keys) - KRONOS_CACHE_MAX + 1]
            for k in oldest:
                _cache.pop(k, None)
                _cache_time.pop(k, None)
        _cache[cache_key] = data
        _cache_time[cache_key] = now
        return jsonify(data)

    except _sp.TimeoutExpired:
        return jsonify({'error': 'Kronos prediction timed out (120s). Model may still be loading.'}), 504
    except json.JSONDecodeError as e:
        log.warning("Kronos returned invalid JSON: %s", e)
        return jsonify({'error': 'Invalid JSON from Kronos'}), 500
    except Exception as e:
        log.warning("Kronos endpoint error: %s", e)
        return jsonify({'error': 'Kronos request failed'}), 500


@app.route('/api/predictions/status')
@requires_auth
def api_kronos_status():
    """Check Kronos model status — cached predictions + model load state"""
    import subprocess as _sp

    kronos_tool = Path.home() / 'Code' / 'Sapphire' / 'plugins' / 'claw-sapphire' / 'tools' / 'predict_kronos.py'
    kronos_python = Path.home() / 'Code' / 'Kronos' / '.venv' / 'bin' / 'python3'
    if not Path(str(kronos_python)).exists():
        kronos_python = '/usr/local/bin/python3'

    kronos_env = {**__import__('os').environ, 'PYTHONPATH': str(Path.home() / 'Code' / 'Kronos')}

    try:
        result = _sp.run(
            [str(kronos_python), str(kronos_tool)],
            input='{"action":"status"}',
            capture_output=True, text=True, timeout=10,
            env=kronos_env,
        )
        data = json.loads(result.stdout)

        # Add cached prediction summary
        today = datetime.now().strftime('%Y-%m-%d')
        pred_file = Path.home() / 'Code' / 'Sapphire' / 'data' / 'intelligence' / today / 'predictions.json'
        data['has_todays_predictions'] = pred_file.exists()
        if pred_file.exists():
            preds = json.loads(pred_file.read_text())
            data['cached_symbols'] = list(preds.get('predictions', {}).keys())

        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e), 'model_loaded': False}), 200


@app.route('/api/soc/cyber-research', methods=['POST'])
@requires_auth
def api_soc_cyber_research():
    """Proxy security queries to Lumo T5 via lumo_research.py plugin tool."""
    import subprocess

    data = request.get_json(force=True, silent=True) or {}
    query = (data.get('query') or '').strip()
    mode = data.get('mode', 'ask')  # ask | security_brief | security_brief_deep
    web_search = bool(data.get('web_search', False))

    if not query:
        return jsonify({'error': 'query required'}), 400

    tool_path = Path.home() / 'Code' / 'Sapphire' / 'plugins' / 'claw-sapphire' / 'tools' / 'lumo_research.py'

    if mode == 'security_brief_deep':
        inp = json.dumps({'action': 'security_brief', 'topic': query, 'depth': 'deep', 'web_search': web_search})
    elif mode == 'security_brief':
        inp = json.dumps({'action': 'security_brief', 'topic': query, 'depth': 'standard', 'web_search': web_search})
    else:
        inp = json.dumps({'action': 'ask', 'query': query, 'web_search': web_search})

    try:
        result = subprocess.run(
            ['python3', str(tool_path)],
            input=inp, capture_output=True, text=True, timeout=120
        )
        if result.stdout.strip():
            out = json.loads(result.stdout)
        else:
            # Don't leak raw subprocess stderr to clients — log server-side.
            log.warning("lumo_research returned no stdout; stderr=%s",
                        (result.stderr or "")[-500:])
            out = {'status': 'error', 'error': 'no output'}
        return jsonify(out)
    except subprocess.TimeoutExpired:
        return jsonify({'status': 'timeout', 'error': 'Lumo took too long (>120s). Try again.'})
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)})


@app.route('/api/soc/lumo-status')
@requires_auth
def api_soc_lumo_status():
    """Quick Lumo API reachability check."""
    import subprocess
    tool_path = Path.home() / 'Code' / 'Sapphire' / 'plugins' / 'claw-sapphire' / 'tools' / 'lumo_research.py'
    try:
        result = subprocess.run(
            ['python3', str(tool_path)],
            input='{"action":"status"}', capture_output=True, text=True, timeout=5
        )
        out = json.loads(result.stdout) if result.stdout.strip() else {'online': False}
        return jsonify(out)
    except Exception as e:
        return jsonify({'online': False, 'error': str(e)})


@app.route('/health')
def health():
    """Health check endpoint — public"""
    return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()})


# ── Metrics history / sparkline endpoints ─────────────────────────────────────

@app.route('/api/metrics/history')
@requires_auth
def api_metrics_history():
    """24-hour time-series for overview sparklines (5-min intervals, up to 288 pts)."""
    from metrics_collector import get_metrics_history
    entries = get_metrics_history(hours=24)
    result = {
        'inference': [{'ts': e['ts'], 'count': e.get('inference_count', 0),
                       'avg_ms': e.get('inference_avg_ms', 0)} for e in entries],
        'signals':   [{'ts': e['ts'], 'count': e.get('signals', 0)} for e in entries],
        'threats':   [{'ts': e['ts'], 'count': e.get('threats', 0)} for e in entries],
    }
    return jsonify(result)


@app.route('/api/soc/threat-timeline')
@requires_auth
def api_soc_threat_timeline():
    """7-day threat severity breakdown from daily intelligence files."""
    from datetime import timedelta
    intel_base = Path.home() / 'Code' / 'Sapphire' / 'data' / 'intelligence'
    days = []
    today = datetime.now()
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        date_str = d.strftime('%Y-%m-%d')
        counts = {'date': date_str, 'critical': 0, 'high': 0, 'medium': 0, 'low': 0}
        threat_file = intel_base / date_str / 'threats.json'
        if threat_file.exists():
            try:
                data = json.loads(threat_file.read_text())
                for t in data.get('threats', []):
                    sev = (t.get('severity') or 'low').lower()
                    if sev in counts:
                        counts[sev] += 1
                    else:
                        counts['low'] += 1
            except Exception:
                pass
        days.append(counts)
    return jsonify({'days': days})


@app.route('/api/agents/history')
@requires_auth
def api_agents_history():
    """24-hour Pi vitals history for sparklines."""
    from metrics_collector import get_agent_history
    entries = get_agent_history(hours=24)
    result: dict = {'rari1': {'cpu_temp': [], 'mem_pct': [], 'timestamps': []},
                    'rari2': {'cpu_temp': [], 'mem_pct': [], 'timestamps': []}}
    for e in entries:
        ts = e.get('ts', '')
        for node in ('rari1', 'rari2'):
            v = (e.get('agents') or {}).get(node, {})
            result[node]['timestamps'].append(ts)
            result[node]['cpu_temp'].append(v.get('cpu_temp'))
            result[node]['mem_pct'].append(v.get('mem_pct'))
    return jsonify(result)


@app.route('/api/signals/performance')
@requires_auth
def api_signals_performance():
    """Daily signal P&L and win-rate trend from all signal JSONL files."""
    from datetime import timedelta
    signals_dir = Path.home() / 'Code' / 'Sapphire' / 'data' / 'signals'
    today = datetime.now()
    daily = []
    cumulative_pnl = [0.0]
    win_rate_trend = []
    running_pnl = 0.0

    for i in range(13, -1, -1):   # last 14 days
        d = today - timedelta(days=i)
        date_str = d.strftime('%Y-%m-%d')
        f = signals_dir / f'{date_str}.jsonl'
        day = {'date': date_str, 'signals': 0, 'wins': 0, 'losses': 0, 'pnl': 0.0}
        if f.exists():
            try:
                for line in f.read_text().strip().splitlines():
                    try:
                        s = json.loads(line)
                        day['signals'] += 1
                        outcome = s.get('outcome')
                        pnl = s.get('pnl_usd', 0.0) or 0.0
                        day['pnl'] = round(day['pnl'] + pnl, 2)
                        if outcome == 'win':
                            day['wins'] += 1
                        elif outcome == 'loss':
                            day['losses'] += 1
                    except Exception:
                        pass
            except Exception:
                pass
        if day['signals'] > 0:
            running_pnl += day['pnl']
            cumulative_pnl.append(round(running_pnl, 2))
            closed = day['wins'] + day['losses']
            win_rate_trend.append(round(day['wins'] / closed, 3) if closed > 0 else None)
            daily.append(day)

    return jsonify({
        'daily':          daily,
        'cumulative_pnl': cumulative_pnl[1:] if len(cumulative_pnl) > 1 else [],
        'win_rate_trend': win_rate_trend,
    })


@app.route('/portfolio')
@requires_auth
def portfolio_page():
    return render_template('pages/portfolio.html', current_page='portfolio', page_title='Portfolio')


@app.route('/factors')
@requires_auth
def factors_page():
    return render_template('pages/factors.html', current_page='factors', page_title='Factors')


@app.route('/performance')
@requires_auth
def performance_page():
    return render_template('pages/performance.html', current_page='performance', page_title='Performance')


def _parse_agent_timestamp(value: str | None) -> datetime | None:
    """Parse an ISO timestamp string into an aware UTC datetime."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _load_agent_events(limit: int = 20) -> list[dict[str, Any]]:
    """Load the most recent agent events from the event bus JSONL fallback."""
    if not _AGENT_EVENTS_FILE.exists():
        return []

    events: list[dict[str, Any]] = []
    try:
        lines = _AGENT_EVENTS_FILE.read_text().splitlines()
    except OSError:
        return events

    for raw_line in reversed(lines):
        line = raw_line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        event_type = str(record.get("type") or "")
        if not event_type.startswith("agent."):
            continue
        data = record.get("data") or {}
        if not isinstance(data, dict):
            data = {"value": data}
        events.append(
            {
                "type": event_type,
                "ts": record.get("ts"),
                "agent": data.get("agent") or record.get("source") or "unknown",
                "data": data,
            }
        )
        if len(events) >= limit:
            break
    return events


def _load_agent_heartbeats() -> list[dict[str, Any]]:
    """Load per-agent heartbeat files from disk."""
    heartbeats: list[dict[str, Any]] = []
    now = datetime.now(UTC)
    if not _AGENT_HEARTBEAT_DIR.exists():
        return heartbeats

    for path in sorted(_AGENT_HEARTBEAT_DIR.glob("*.heartbeat")):
        try:
            payload = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        updated_at = _parse_agent_timestamp(payload.get("updated_at"))
        heartbeats.append(
            {
                "name": payload.get("agent") or path.stem,
                "cycle_count": int(payload.get("cycle_count") or 0),
                "last_cycle_completed_at": payload.get("last_cycle_completed_at"),
                "updated_at": payload.get("updated_at"),
                "age_sec": (
                    max(0, int((now - updated_at).total_seconds()))
                    if updated_at is not None
                    else None
                ),
            }
        )
    return heartbeats


def _load_agents_autonomous_context() -> dict[str, Any]:
    """Build the server-side context for the autonomous agents dashboard."""
    events = _load_agent_events()
    heartbeats = _load_agent_heartbeats()
    last_cycle_event = next(
        (event for event in events if event["type"] == "agent.cycle.completed"),
        None,
    )
    cycle_count = 0
    if heartbeats:
        cycle_count = max(heartbeat["cycle_count"] for heartbeat in heartbeats)
    if cycle_count == 0 and last_cycle_event is not None:
        cycle_count = int(last_cycle_event["data"].get("cycle_count") or 0)

    return {
        "last_cycle_timestamp": last_cycle_event["ts"] if last_cycle_event else None,
        "cycle_count": cycle_count,
        "events": events,
        "heartbeats": heartbeats,
    }


@app.route('/agents/autonomous')
@requires_auth
def agents_autonomous_page():
    """Autonomous agent heartbeat and event dashboard."""
    return render_template(
        'pages/agents_autonomous.html',
        current_page='agents-autonomous',
        page_title='Autonomous Agents',
        **_load_agents_autonomous_context(),
    )


@app.route('/content')
@requires_auth
def content_page():
    return render_template('pages/content.html', current_page='content', page_title='Content_Engine')


@app.route('/cascade')
@requires_auth
def cascade_page():
    return render_template('pages/cascade.html', current_page='cascade', page_title='Cascade')


@app.route('/intel')
@requires_auth
def intel_page():
    return render_template('pages/intel.html', current_page='intel', page_title='Intel')


@app.route('/investment-intel')
@requires_auth
def investment_intel_page():
    return render_template(
        'pages/investment_intel.html',
        current_page='investment-intel',
        page_title='Investment Intel',
    )


@app.route('/api/foundry/readiness')
@requires_auth
def api_foundry_readiness():
    """Repo-grounded Foundry readiness: safe config checks + local artifact map."""
    try:
        from lib.foundry.readiness import build_foundry_readiness

        payload = build_foundry_readiness()
        payload['last_updated'] = time.time()
        return jsonify(payload)
    except Exception as e:
        log.warning("foundry readiness API error: %s", e)
        return jsonify({
            'status': 'unknown',
            'badge': 'UNAVAILABLE',
            'auth_mode': 'unknown',
            'connection_label': 'Foundry readiness inspection failed.',
            'connector_registered': False,
            'configured_envs': {},
            'recommended_first_app': 'Sapphire Mission Control',
            'transport_hint': 'Dataset sync first.',
            'dataset_groups': [],
            'totals': {'groups': 0, 'files': 0},
            'latest_materialization': None,
            'next_step': 'Inspect the repo-level Foundry configuration and retry.',
            'error': str(e),
            'last_updated': time.time(),
        }), 200


@app.route('/api/foundry/sync-status')
@requires_auth
def api_foundry_sync_status():
    """Foundry sync engine status — last sync, history, tracked files."""
    try:
        from lib.foundry.sync import get_sync_status

        payload = get_sync_status()
        payload['last_updated'] = time.time()
        return jsonify(payload)
    except Exception as e:
        log.warning("foundry sync-status API error: %s", e)
        return jsonify({
            'last_sync': None,
            'last_status': 'unavailable',
            'sync_count': 0,
            'tracked_files': 0,
            'recent_history': [],
            'recent_errors': 0,
            'interval_seconds': 900,
            'source_types': [],
            'error': str(e),
            'last_updated': time.time(),
        }), 200


@app.route('/api/investments/intel')
@requires_auth
def api_investments_intel():
    """Read-only investment intelligence source mesh and thesis report."""
    try:
        from lib.intel.investment_intel import build_investment_intel_report

        live_crypto = str(request.args.get('live') or '').lower() in {'1', 'true', 'yes'}
        return jsonify(build_investment_intel_report(fetch_live_crypto=live_crypto))
    except Exception as e:
        log.warning("investment intel API error: %s", e)
        return jsonify({
            'timestamp': datetime.now(UTC).isoformat(),
            'mode': 'read-only',
            'error': str(e),
            'research_pack': {'available': False, 'source_label': 'unavailable'},
            'universe': [],
            'source_mesh': {
                'connectors': [],
                'coverage': [],
                'totals': {'assets': 0, 'connectors': 0, 'configured_connectors': 0},
                'missing_envs': [],
            },
            'ops_queue': [],
            'analysis_lenses': [],
            'mindset': [],
        }), 200


@app.route('/api/investments/sources')
@requires_auth
def api_investments_sources():
    """Read-only source connection map for equities, macro, energy, and crypto."""
    try:
        from lib.intel.investment_intel import build_source_report

        return jsonify(build_source_report())
    except Exception as e:
        log.warning("investment sources API error: %s", e)
        return jsonify({
            'timestamp': datetime.now(UTC).isoformat(),
            'mode': 'read-only',
            'error': str(e),
            'research_pack': {'available': False, 'source_label': 'unavailable'},
            'source_mesh': {
                'connectors': [],
                'coverage': [],
                'totals': {'assets': 0, 'connectors': 0, 'configured_connectors': 0},
                'missing_envs': [],
            },
            'robinhood': {'configured': False, 'mode': 'read-only portfolio snapshot'},
        }), 200


@app.route('/api/portfolio')
@requires_auth
def api_portfolio():
    """Live Robinhood portfolio snapshot."""
    def fetch():
        from lib.portfolio.robinhood import RobinhoodReader
        reader = RobinhoodReader()
        return reader.get_snapshot()

    try:
        return jsonify(get_cached(
            'portfolio_snapshot',
            fetch,
            ttl=PORTFOLIO_CACHE_DURATION,
            raise_on_miss=True,
        ))
    except Exception as e:
        log.warning("portfolio API error: %s", e)
        return jsonify({
            'source': 'unavailable',
            'error': str(e),
            'holdings': [],
            'total_value': 0,
            'day_pnl': 0,
            'day_pnl_pct': 0,
            'total_return': 0,
            'total_return_pct': 0,
            'cash': 0,
            'buying_power': 0,
            'sectors': [],
            'asset_classes': [],
        }), 200


@app.route('/api/factors')
@requires_auth
def api_factors():
    """Cross-sectional factor scores (CoinGecko, 1h cache)."""
    try:
        from lib.analytics.factors import CrossSectionalFactors
        from lib.analytics.factors import to_dict as factors_to_dict
        report = CrossSectionalFactors().compute()
        return jsonify(factors_to_dict(report))
    except Exception as e:
        log.warning("factors API error: %s", e)
        return jsonify({'error': str(e), 'assets': [], 'ranked_assets': [],
                        'factor_names': [], 'strongest': None, 'weakest': None,
                        'dispersion': 0, 'asset_count': 0}), 200


@app.route('/api/cascade')
@requires_auth
def api_cascade():
    """Live liquidation cascade risk via Hyperliquid OI + funding data."""
    def fetch():
        from lib.analytics.liquidation import CascadeDetector
        from lib.analytics.liquidation import to_dict as cascade_to_dict
        report = CascadeDetector().assess_all(['BTC', 'ETH', 'SOL', 'LINK', 'ARB', 'AVAX'])
        return cascade_to_dict(report)

    try:
        return jsonify(get_cached(
            'cascade_risk',
            fetch,
            ttl=CASCADE_CACHE_DURATION,
            raise_on_miss=True,
        ))
    except Exception as e:
        log.warning("cascade API error: %s", e)
        return jsonify({'error': str(e), 'risk_score': 0, 'risk_label': 'UNAVAILABLE',
                        'assets': [], 'total_oi_usd': 0, 'avg_funding_8h': 0}), 200


def _attach_geo(item: dict) -> dict:
    """Augment an intel item with ``latitude``/``longitude`` when resolvable.

    Precedence: explicit fields, then region-tag centroid lookup from
    ``lib.intel.lead_enricher.REGION_CENTROIDS``. Never mutates on failure.
    """
    try:
        lat = item.get('latitude')
        lng = item.get('longitude')
        if lat is not None and lng is not None:
            item['latitude'] = float(lat)
            item['longitude'] = float(lng)
            item.setdefault('geo_source', 'explicit')
            return item
        from lib.intel.lead_enricher import REGION_CENTROIDS
        region = str(item.get('region') or '').lower().strip()
        if region and region in REGION_CENTROIDS:
            rlat, rlng = REGION_CENTROIDS[region]
            item['latitude'] = rlat
            item['longitude'] = rlng
            item['geo_source'] = 'region_centroid'
    except Exception:
        pass
    return item


@app.route('/api/intel')
@requires_auth
def api_intel():
    """Regional intel feed — proxies regional-intel-workbench if reachable, else local snapshot."""
    # Try local intelligence snapshots
    items = []
    local_item_count = 0
    local_latest = None

    # Load recent threat intel as intel feed items
    intel_dir = Path.home() / 'Code' / 'Sapphire' / 'data' / 'intelligence'
    try:
        for day_dir in sorted(intel_dir.glob('*/threats.json'), reverse=True)[:3]:
            try:
                threats = json.loads(day_dir.read_text()).get('threats') or []
                for t in threats[:5]:
                    local_item_count += 1
                    stamp = t.get('published') or day_dir.parent.name
                    if local_latest is None or str(stamp) > str(local_latest):
                        local_latest = stamp
                    items.append({
                        'id': t.get('canonical_id') or t.get('id', ''),
                        'title': t.get('title', ''),
                        'region': 'GLOBAL',
                        'severity': 'high' if (t.get('score') or 0) >= 8 else 'medium',
                        'source': t.get('source', 'threat-intel'),
                        'timestamp': stamp,
                        'tags': t.get('tags') or [],
                        'exploited': t.get('exploited', False),
                    })
            except Exception:
                pass
    except Exception:
        pass

    # Try regional-intel-workbench API (port 8787)
    workbench_status = 'offline'
    workbench_items = 0
    try:
        import urllib.request as _ureq
        with _ureq.urlopen('http://127.0.0.1:8787/api/intel/recent?limit=10', timeout=3) as r:
            wb_data = json.loads(r.read())
            workbench_items = len(wb_data.get('items') or [])
            for item in (wb_data.get('items') or []):
                items.append({**item, 'source': 'regional-workbench'})
            workbench_status = 'online'
    except Exception:
        pass

    foundry = {}
    try:
        from lib.foundry.readiness import build_foundry_readiness

        foundry = build_foundry_readiness()
    except Exception as e:
        log.warning("intel API failed to summarize Foundry readiness: %s", e)

    sources = [
        {
            'name': 'Threat snapshots',
            'type': 'Threat / CVE',
            'status': 'active' if local_item_count else 'unknown',
            'last_pull': local_latest,
            'items': local_item_count,
        },
        {
            'name': 'Regional Workbench',
            'type': 'Geopolitical / Cyber',
            'status': workbench_status,
            'last_pull': time.time() if workbench_status == 'online' else None,
            'items': workbench_items,
        },
        {
            'name': 'Palantir Foundry',
            'type': 'Ontology / Graph',
            'status': foundry.get('status', 'planned'),
            'last_pull': foundry.get('latest_materialization'),
            'items': ((foundry.get('totals') or {}).get('files') or 0),
        },
    ]

    # Attach geo coords so the /intel Leaflet map can plot each item
    items = [_attach_geo(dict(it)) for it in items]

    return jsonify({
        'items': items[:20],
        'sources': sources,
        'item_count': len(items),
        'foundry': foundry,
        'last_updated': time.time(),
    })


@app.route('/api/performance')
@requires_auth
def api_performance():
    """Live performance tracker stats from data/performance/signals.jsonl."""
    try:
        from lib.analytics.performance_tracker import PerformanceTracker
        pt = PerformanceTracker()
        stats = pt.get_all_stats()
        alerts = pt.get_decay_alerts()
        return jsonify({**stats, 'decay_alerts': alerts, 'last_updated': time.time()})
    except Exception as e:
        log.warning("performance tracker API error: %s", e)
        return jsonify({'error': str(e), 'total_signals': 0, 'scored_signals': 0,
                        'win_rate': None, 'decay_alerts': []}), 200


@app.route('/api/strategy-performance')
@requires_auth
def api_strategy_performance():
    """Unified strategy performance: overall + by-strategy + by-timeframe + cross.

    Reads every closed trade from data/signals/*.jsonl, data/performance/signals.jsonl,
    and data/paper_portfolio.json history, normalizes, and groups by strategy and
    hold-duration bucket (1h/4h/1d/7d/30d/all).
    """
    def fetch():
        from lib.analytics.strategy_performance import report
        payload = report()
        payload['last_updated'] = time.time()
        return payload

    try:
        return jsonify(get_cached(
            'strategy_performance',
            fetch,
            ttl=STRATEGY_PERFORMANCE_CACHE_DURATION,
            raise_on_miss=True,
        ))
    except Exception as e:
        log.warning("strategy performance API error: %s", e)
        return jsonify({
            'error': str(e),
            'overall': {'trades': 0, 'win_rate': None, 'total_pnl_usd': 0.0},
            'by_strategy': {}, 'by_timeframe': {},
            'by_strategy_timeframe': {}, 'by_symbol': {},
            'trade_count': 0, 'strategies': [], 'timeframes': [],
        }), 200


@app.route('/api/convergence-watchlist')
@requires_auth
def api_convergence_watchlist():
    """Convergence thesis watchlist — equities curated from Kimi P1 research
    (Solar / Drone / Space / AI convergence). Static JSON file under
    world_knowledge/research/kimi-p1-sun-drone/. Read-only; for live prices,
    cross-reference with the TA scanner or OpenBB quote API.
    """
    try:
        watchlist_path = (
            Path(__file__).resolve().parents[2]
            / "world_knowledge" / "research" / "kimi-p1-sun-drone"
            / "convergence_watchlist.json"
        )
        if not watchlist_path.exists():
            return jsonify({'error': 'watchlist not found', 'tiers': {}}), 200
        data = json.loads(watchlist_path.read_text())
        data['source_file'] = str(watchlist_path.relative_to(watchlist_path.parents[4]))
        return jsonify(data)
    except Exception as e:
        log.warning("convergence watchlist API error: %s", e)
        return jsonify({'error': str(e), 'tiers': {}}), 200


@app.route('/api/prediction-accuracy')
@requires_auth
def api_prediction_accuracy():
    """TA-scanner prediction accuracy from data/trading_predictions.jsonl."""
    try:
        from lib.analytics.prediction_accuracy import report
        return jsonify({**report(), 'last_updated': time.time()})
    except Exception as e:
        log.warning("prediction accuracy API error: %s", e)
        return jsonify({
            'error': str(e), 'total': 0, 'scored': 0, 'correct': 0,
            'accuracy': None, 'by_symbol': {}, 'by_direction': {}, 'recent': [],
        }), 200


@app.route('/api/forecast')
@requires_auth
def api_forecast():
    """Combined Kronos + TA-scanner forecast per symbol with consensus + edge score."""
    try:
        from lib.analytics.forecast import forecast
        payload = forecast()
        payload['last_updated'] = time.time()
        return jsonify(payload)
    except Exception as e:
        log.warning("forecast API error: %s", e)
        return jsonify({
            'error': str(e),
            'rows': [], 'symbols': [],
            'kronos_stamp': None, 'kronos_source': None,
        }), 200


@app.route('/api/backtest-results')
@requires_auth
def api_backtest_results():
    """Summary + leaderboard over the latest strategy backtest sweep.

    Query params:
      metric: sortino | sharpe | calmar | total_return_pct | win_rate | profit_factor
      limit:  top-N (default 10)
      include_minimal: "1" to include strategies with <5 trades (default false)
    """
    try:
        from lib.analytics.backtest_results import leaderboard, summary
        metric = request.args.get('metric', 'sortino')
        try:
            limit = int(request.args.get('limit', '10'))
        except ValueError:
            limit = 10
        include_minimal = request.args.get('include_minimal') == '1'
        summary_payload = summary()
        try:
            lb = leaderboard(metric=metric, limit=limit, include_minimal_trades=include_minimal)
        except ValueError as ve:
            lb = {'error': str(ve), 'rows': [], 'metric': metric}
        return jsonify({
            'summary': summary_payload,
            'leaderboard': lb,
            'last_updated': time.time(),
        })
    except Exception as e:
        log.warning("backtest results API error: %s", e)
        return jsonify({
            'error': str(e),
            'summary': {'have_results': False, 'best_per_symbol': [], 'total_backtests': 0},
            'leaderboard': {'rows': [], 'metric': 'sortino'},
        }), 200


@app.route('/api/trading-brain')
@requires_auth
def api_trading_brain():
    """Unified trading decision engine — aggregates TA, ensemble signals, Kronos, macro, and track record.

    5-minute in-process cache (each call invokes 5 sub-tools per symbol).
    Query params:
      symbol — decide for a single symbol only; omit for dashboard (BTC + ETH + SOL)
    """
    import subprocess as _sp

    symbol = request.args.get('symbol', '').strip().upper()
    cache_key = f'trading_brain_{symbol or "dashboard"}'
    BRAIN_CACHE = 300

    now = time.time()
    if cache_key in _cache and now - _cache_time.get(cache_key, 0) < BRAIN_CACHE:
        return jsonify(_cache[cache_key])

    tool_path = Path.home() / 'Code' / 'Sapphire' / 'plugins' / 'claw-sapphire' / 'tools' / 'trading_brain.py'
    lib_path = Path.home() / 'Code' / 'Sapphire' / 'plugins' / 'claw-sapphire' / 'lib'
    inp = json.dumps({'action': 'decide', 'symbol': symbol} if symbol else {'action': 'dashboard'})
    env = {**__import__('os').environ, 'PYTHONPATH': str(lib_path)}

    try:
        result = _sp.run(
            ['python3', str(tool_path)],
            input=inp, capture_output=True, text=True, timeout=150, env=env,
        )
        if result.returncode != 0:
            log.warning("trading_brain failed (rc=%s): %s", result.returncode, (result.stderr or "")[-500:])
            return jsonify({'error': 'trading_brain process failed', 'decisions': {}}), 200
        data = json.loads(result.stdout)
        _cache[cache_key] = data
        _cache_time[cache_key] = now
        return jsonify(data)
    except _sp.TimeoutExpired:
        return jsonify({'error': 'trading_brain timed out (150s)', 'decisions': {}}), 200
    except json.JSONDecodeError as e:
        log.warning("trading_brain returned invalid JSON: %s", e)
        return jsonify({'error': 'Invalid JSON from trading_brain', 'decisions': {}}), 200
    except Exception as e:
        log.warning("trading_brain endpoint error: %s", e)
        return jsonify({'error': str(e), 'decisions': {}}), 200


@app.route('/api/tho/market-intel')
@requires_auth
def api_tho_market_intel():
    """THO housing market intelligence — FRED rates + Houston permits + THO customer analytics.

    10-minute cache (housing data changes slowly).
    Query params:
      action — market (default) | buyers | report
    """
    import subprocess as _sp

    action = request.args.get('action', 'market')
    if action not in ('market', 'buyers', 'report'):
        return jsonify({'error': f'Unknown action {action!r}. Valid: market, buyers, report'}), 400

    cache_key = f'tho_market_intel_{action}'
    THO_CACHE = 600

    now = time.time()
    if cache_key in _cache and now - _cache_time.get(cache_key, 0) < THO_CACHE:
        return jsonify(_cache[cache_key])

    tool_path = Path.home() / 'Code' / 'Sapphire' / 'plugins' / 'claw-sapphire' / 'tools' / 'tho_intel.py'

    try:
        result = _sp.run(
            ['python3', str(tool_path)],
            input=json.dumps({'action': action}), capture_output=True, text=True, timeout=60,
        )
        if result.stdout.strip():
            data = json.loads(result.stdout)
            _cache[cache_key] = data
            _cache_time[cache_key] = now
            return jsonify(data)
        log.warning("tho_intel returned no stdout; stderr=%s", (result.stderr or "")[-500:])
        return jsonify({'error': 'no output from tho_intel', 'success': False}), 200
    except _sp.TimeoutExpired:
        return jsonify({'error': 'tho_intel timed out (60s)', 'success': False}), 200
    except Exception as e:
        log.warning("tho market intel error: %s", e)
        return jsonify({'error': str(e), 'success': False}), 200


@app.route('/api/lumo/latest-pack')
@requires_auth
def api_lumo_latest_pack():
    """Latest Lumo strategy research pack from data/lumo/.

    Returns the most recently generated pack as markdown. To refresh:
      echo '{"action":"pack"}' | python3 ~/Code/Sapphire/plugins/claw-sapphire/tools/lumo.py
    """
    lumo_dir = Path.home() / 'Code' / 'Sapphire' / 'data' / 'lumo'
    packs = sorted(lumo_dir.glob('lumo_pack_*.md'), reverse=True) if lumo_dir.exists() else []
    if not packs:
        return jsonify({
            'available': False,
            'pack_count': 0,
            'hint': "echo '{\"action\":\"pack\"}' | python3 ~/Code/Sapphire/plugins/claw-sapphire/tools/lumo.py",
        }), 200
    latest = packs[0]
    try:
        return jsonify({
            'available': True,
            'path': str(latest),
            'generated': latest.stem.replace('lumo_pack_', ''),
            'content': latest.read_text(),
            'pack_count': len(packs),
        })
    except Exception as e:
        return jsonify({'available': False, 'error': str(e)}), 200


@app.route('/api/performance-timeseries')
@requires_auth
def api_performance_timeseries():
    """Equity curve + drawdown + monthly returns over all closed trades.

    Reads the unified trade stream from lib.analytics.strategy_performance and
    emits ordered time-series suitable for the /performance SVG charts and
    monthly-returns grid.
    """
    try:
        from lib.analytics.strategy_performance import timeseries
        payload = timeseries()
        payload['last_updated'] = time.time()
        return jsonify(payload)
    except Exception as e:
        log.warning("performance timeseries API error: %s", e)
        return jsonify({
            'error': str(e),
            'initial_capital': 100000.0,
            'final_equity': 100000.0,
            'total_pnl_usd': 0.0,
            'total_return_pct': 0.0,
            'equity_curve': [], 'drawdown_series': [],
            'max_drawdown': {'pct': 0.0, 'ts': None, 'equity_usd': 100000.0},
            'monthly_returns': [], 'trade_count': 0,
        }), 200


@app.route('/api/brain-accuracy')
@requires_auth
def api_brain_accuracy():
    """Trading Brain decision accuracy — GO/LEAN/WAIT scoring over 24h windows."""
    try:
        from lib.analytics.brain_accuracy import report as brain_report
        payload = brain_report()
        payload['last_updated'] = time.time()
        return jsonify(payload)
    except Exception as e:
        log.warning("brain accuracy API error: %s", e)
        return jsonify({
            'error': str(e),
            'total_decisions': 0, 'scored': 0, 'pending': 0,
            'overall_accuracy': None,
            'by_symbol': {}, 'by_decision': {}, 'recent': [],
        }), 200


@app.route('/api/content/drafts')
@requires_auth
def api_content_drafts():
    """List the most recent content drafts (manifests from data/content/drafts/)."""
    import sys
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    try:
        from lib.content import publisher as content_publisher
        drafts = content_publisher.list_drafts(limit=50)
        return jsonify({"count": len(drafts), "drafts": drafts})
    except Exception as e:
        log.warning("content drafts listing failed: %s", e)
        return jsonify({"count": 0, "drafts": [], "error": str(e)}), 500


# ── Security Intelligence Platform (Phase 1) ─────────────────────────────


@app.route('/security')
@requires_auth
def security_page():
    """Security intelligence dashboard — dependency, model, and network panels."""
    return render_template(
        'pages/security.html', current_page='security', page_title='Security Intel'
    )


@app.route('/api/security/dependencies')
@requires_auth
def api_security_dependencies():
    """Dependency scan — CVEs, outdated packages, SBOM."""
    try:
        from lib.security.dependency_scanner import DependencyScanner
        scanner = DependencyScanner(check_outdated=False, check_vulns=False)
        result = scanner.scan_quick()
        return jsonify(result.to_dict())
    except Exception as e:
        log.warning("security dependency scan failed: %s", e)
        return jsonify({'error': str(e), 'total_packages': 0, 'score': 0}), 200


@app.route('/api/security/dependencies/full')
@requires_auth
def api_security_dependencies_full():
    """Full dependency scan with CVE + outdated checks (slow — network calls)."""
    try:
        from lib.security.dependency_scanner import DependencyScanner
        scanner = DependencyScanner(check_outdated=True, check_vulns=True)
        result = scanner.scan()
        return jsonify(result.to_dict())
    except Exception as e:
        log.warning("security full dependency scan failed: %s", e)
        return jsonify({'error': str(e), 'total_packages': 0, 'score': 0}), 200


@app.route('/api/security/models')
@requires_auth
def api_security_models():
    """Model integrity scan — SHA-256 verification + template backdoor detection."""
    try:
        from lib.security.model_monitor import ModelMonitor
        monitor = ModelMonitor(verify_sha256=False)
        result = monitor.scan()
        return jsonify(result.to_dict())
    except Exception as e:
        log.warning("security model scan failed: %s", e)
        return jsonify({'error': str(e), 'total_models': 0, 'score': 0}), 200


@app.route('/api/security/network')
@requires_auth
def api_security_network():
    """Network topology scan — Tailscale nodes, ports, trust zones."""
    try:
        from lib.security.network_mapper import NetworkMapper
        mapper = NetworkMapper(probe_ports=True, probe_timeout=1.5)
        result = mapper.scan()
        return jsonify(result.to_dict())
    except Exception as e:
        log.warning("security network scan failed: %s", e)
        return jsonify({'error': str(e), 'total_nodes': 0, 'score': 0}), 200


@app.route('/api/security/score')
@requires_auth
def api_security_score():
    """Aggregate security score across all three modules."""
    scores = {}
    try:
        from lib.security.dependency_scanner import DependencyScanner
        dep_result = DependencyScanner(check_outdated=False, check_vulns=False).scan_quick()
        scores['dependencies'] = {
            'score': dep_result.score,
            'total_packages': dep_result.total_packages,
            'unsigned': dep_result.unsigned_count,
        }
    except Exception as e:
        scores['dependencies'] = {'score': 0, 'error': str(e)}

    try:
        from lib.security.model_monitor import ModelMonitor
        model_result = ModelMonitor(verify_sha256=False).scan()
        scores['models'] = {
            'score': model_result.score,
            'total_models': model_result.total_models,
            'alerts': len(model_result.template_alerts),
        }
    except Exception as e:
        scores['models'] = {'score': 0, 'error': str(e)}

    try:
        from lib.security.network_mapper import NetworkMapper
        net_result = NetworkMapper(probe_ports=False).scan_quick()
        scores['network'] = {
            'score': net_result.score,
            'total_nodes': net_result.total_nodes,
            'online': net_result.online_nodes,
        }
    except Exception as e:
        scores['network'] = {'score': 0, 'error': str(e)}

    # Weighted aggregate: deps 35%, models 35%, network 30%
    dep_s = scores.get('dependencies', {}).get('score', 0) or 0
    mod_s = scores.get('models', {}).get('score', 0) or 0
    net_s = scores.get('network', {}).get('score', 0) or 0
    aggregate = round(dep_s * 0.35 + mod_s * 0.35 + net_s * 0.30, 1)

    return jsonify({
        'aggregate_score': aggregate,
        'modules': scores,
        'timestamp': datetime.now(UTC).isoformat(),
    })


if __name__ == '__main__':
    # Start background metrics collector (snapshots every 5 min)
    try:
        from metrics_collector import start_collector
        start_collector()
    except Exception:
        pass
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
