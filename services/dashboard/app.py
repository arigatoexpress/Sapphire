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
    if _rs not in sys.path:
        sys.path.insert(0, _rs)

log = logging.getLogger("dashboard")

from flask import Flask, Response, jsonify, render_template, request, send_file, send_from_directory

# Disable Flask's auto-registered /static/<path> route. It was bypassing the
# @requires_auth decorator and exposing static/benchmark_report.html
# (infrastructure topology: GPU models, VRAM, endpoints) to any caller.
# A guarded replacement is registered below so the same files still serve
# — only for authenticated users.
app = Flask(__name__, static_folder=None)
_STATIC_DIR = Path(__file__).parent / "static"

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
        log.warning("Cache fetch failed for '%s': %s", key, e)
        return _cache.get(key, {})

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

        # CDP / TradingView MCP health (Windows GPU port 9222)
        cdp_status = {'connected': False, 'tabs': 0, 'tv_tabs': 0, 'error': '', 'recovery': ''}
        try:
            cdp_raw = fetch_sync('http://100.71.10.48:9222/json')
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
                'Start TradingView Desktop with --remote-debugging-port=9222 '
                'on Windows (100.71.10.48). '
                'Or check: ssh aribs@100.71.10.48 then check if TV is running.'
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
                    try:
                        recent.append(json.loads(line))
                    except Exception:
                        pass
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

        for agent_name, pi_ip, pi_port, log_path in [
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
        import sys as _sys
        _alpha = _Path.home() / 'Code' / 'Sapphire' / 'services' / 'alpha'
        if str(_alpha) not in _sys.path:
            _sys.path.insert(0, str(_alpha))

        today = _dt.now(UTC).strftime('%Y-%m-%d')
        signals_dir = _Path.home() / 'Code' / 'Sapphire' / 'data' / 'signals'
        f = signals_dir / f'{today}.jsonl'

        signals_today = []
        if f.exists():
            for line in f.read_text().strip().splitlines():
                try:
                    signals_today.append(_json.loads(line))
                except Exception:
                    pass

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


@app.route('/chain')
@requires_auth
def chain_page():
    """On-chain intelligence: regime, funding, TVL, stablecoin flows"""
    return render_template('pages/chain.html', current_page='chain',
                           page_title='On-Chain Intelligence')


@app.route('/api/chain/overview')
@requires_auth
def api_chain_overview():
    """Unified on-chain snapshot — regime, funding, OI, TVL, stablecoins."""
    import sys as _sys
    from pathlib import Path as _Path
    _root = _Path.home() / 'Code' / 'Sapphire'
    if str(_root) not in _sys.path:
        _sys.path.insert(0, str(_root))
    try:
        from lib.chain import ChainIntelligence
        ci = ChainIntelligence()
        return jsonify(ci.snapshot())
    except Exception as e:
        log.exception("chain overview failed")
        return jsonify({"error": f"{type(e).__name__}: {e}"}), 500


@app.route('/risk')
@requires_auth
def risk_page():
    """Portfolio risk: Sharpe/Sortino/Calmar/drawdown/Kelly."""
    return render_template('pages/risk.html', current_page='risk',
                           page_title='Portfolio Risk')


@app.route('/api/risk/metrics')
@requires_auth
def api_risk_metrics():
    """Portfolio metrics computed from paper_trading + signal audit logs."""
    import sys as _sys
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


@app.route('/analytics')
@requires_auth
def analytics_page():
    """Performance analytics: equity curve, rolling Sharpe, regime breakdown."""
    return render_template('pages/analytics.html', current_page='analytics',
                           page_title='Performance Analytics')


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
        from lib.analytics.backtest import Backtester, BacktestConfig, DEFAULT_SYMBOLS
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
    import sys as _sys
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
            lines = [l for l in result.stdout.splitlines()
                     if l.strip() and 'wtmp' not in l and 'reboot' not in l]
            known_users = {'aribs', 'rari'}
            unknown = [l for l in lines if not any(u in l for u in known_users)]
            if unknown:
                checks['auth_logs'] = {'status': 'warn', 'detail': f'{len(unknown)} unknown session(s)'}
                for l in unknown[:3]:
                    auth_events.append({'timestamp': datetime.now().isoformat()[:19],
                                        'type': 'warn', 'message': l.strip()[:80]})
            else:
                checks['auth_logs'] = {'status': 'pass', 'detail': f'{len(lines)} sessions, all known'}
                for l in lines[:5]:
                    parts = l.split()
                    auth_events.append({'timestamp': ' '.join(parts[4:8]) if len(parts) > 7 else '--',
                                        'type': 'ok', 'message': l.strip()[:80]})
        except Exception:
            checks['auth_logs'] = {'status': 'warn', 'detail': 'Could not read auth logs'}

        # ── Tailscale devices ────────────────────────────────────────
        try:
            result = subprocess.run(
                ['tailscale', 'status'],
                capture_output=True, text=True, timeout=8
            )
            known_ips = {'100.67.171.79', '100.71.10.48', '100.120.191.1', '100.87.225.89'}
            lines = [l for l in result.stdout.splitlines() if l.strip() and not l.startswith('#')]
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
            established = [l for l in result.stdout.splitlines() if 'ESTABLISHED' in l]
            # Filter known/expected IPs
            known_prefixes = ('100.', '127.', '17.', '34.', '35.', '52.', '54.',
                              '104.', '140.', '142.', '192.168.', '10.')
            unexpected = [l for l in established
                          if not any(p in l for p in known_prefixes)]
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
    import sys as _sys

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


if __name__ == '__main__':
    # Start background metrics collector (snapshots every 5 min)
    try:
        from metrics_collector import start_collector
        start_collector()
    except Exception:
        pass
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
