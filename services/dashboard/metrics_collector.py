"""
Sapphire Metrics Collector
Background daemon that snapshots system metrics every 5 minutes.
Feeds /api/metrics/history and /api/agents/history sparkline endpoints.
"""

import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path.home() / 'Code' / 'Sapphire' / 'data' / 'intelligence'
METRICS_FILE = DATA_DIR / 'metrics_history.jsonl'
AGENT_FILE   = DATA_DIR / 'agent_history.jsonl'
MAX_ENTRIES  = 288   # 24 h at 5-min intervals
INTERVAL     = 300   # seconds between snapshots


# ── JSONL helpers ─────────────────────────────────────────────────────────────

def _read_jsonl(path):
    if not path.exists():
        return []
    entries = []
    for line in path.read_text().strip().splitlines():
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return entries


def _append_jsonl(path, entry):
    """Append one entry, keep at most MAX_ENTRIES. Atomic write via tempfile."""
    import os
    import tempfile
    path.parent.mkdir(parents=True, exist_ok=True)
    entries = _read_jsonl(path)
    entries.append(entry)
    entries = entries[-MAX_ENTRIES:]
    content = '\n'.join(json.dumps(e) for e in entries) + '\n'
    with tempfile.NamedTemporaryFile(
        mode='w', dir=path.parent, delete=False, suffix='.tmp'
    ) as tf:
        tf.write(content)
        tmp = tf.name
    os.replace(tmp, path)


# ── Data collectors ───────────────────────────────────────────────────────────

def _inference_total_requests():
    """Sum requests across all inference proxy tiers."""
    try:
        import urllib.request
        with urllib.request.urlopen('http://localhost:11435/metrics', timeout=3) as r:
            data = json.loads(r.read())
        metrics = data.get('metrics', {})
        total = sum(v.get('requests', 0) for v in metrics.values() if isinstance(v, dict))
        # avg_ms across tiers with requests
        tiers_with_req = [v for v in metrics.values()
                          if isinstance(v, dict) and v.get('requests', 0) > 0]
        avg_ms = (sum(v.get('avg_ms', 0) for v in tiers_with_req) / len(tiers_with_req)
                  if tiers_with_req else 0)
        return total, round(avg_ms, 1)
    except Exception:
        return 0, 0


def _count_today_signals():
    today = datetime.now().strftime('%Y-%m-%d')
    sig_file = Path.home() / 'Code' / 'Sapphire' / 'data' / 'signals' / f'{today}.jsonl'
    if not sig_file.exists():
        return 0
    try:
        return sum(1 for _ in sig_file.open())
    except Exception:
        return 0


def _count_threats():
    for candidate in [
        DATA_DIR / 'latest' / 'threats.json',
        DATA_DIR / datetime.now().strftime('%Y-%m-%d') / 'threats.json',
    ]:
        if candidate.exists():
            try:
                d = json.loads(candidate.read_text())
                return len(d.get('threats', []))
            except Exception:
                pass
    return 0


def _fetch_pi_vitals():
    """Ping Pi health endpoints, return vitals dict keyed by 'rari1'/'rari2'."""
    import urllib.request
    agents = {'rari1': ('100.120.191.1', 19001), 'rari2': ('100.87.225.89', 19002)}
    result = {}
    for name, (ip, port) in agents.items():
        try:
            with urllib.request.urlopen(f'http://{ip}:{port}/health', timeout=2) as r:
                data = json.loads(r.read())
            vitals = data.get('vitals', {})
            mem = vitals.get('memory') or {}
            result[name] = {
                'cpu_temp': vitals.get('cpu_temp_c'),
                'mem_pct':  mem.get('used_pct'),
                'running':  True,
            }
        except Exception:
            result[name] = {'cpu_temp': None, 'mem_pct': None, 'running': False}
    return result


# ── Snapshot ──────────────────────────────────────────────────────────────────

def _snapshot():
    ts = datetime.now(timezone.utc).isoformat()

    req_count, avg_ms = _inference_total_requests()
    _append_jsonl(METRICS_FILE, {
        'ts':              ts,
        'inference_count': req_count,
        'inference_avg_ms': avg_ms,
        'signals':         _count_today_signals(),
        'threats':         _count_threats(),
    })

    vitals = _fetch_pi_vitals()
    _append_jsonl(AGENT_FILE, {'ts': ts, 'agents': vitals})


# ── Public API ────────────────────────────────────────────────────────────────

def get_metrics_history(hours=24):
    """Return up to last `hours` worth of metric snapshots."""
    entries = _read_jsonl(METRICS_FILE)
    limit = min(int(hours * 12), MAX_ENTRIES)
    return entries[-limit:]


def get_agent_history(hours=24):
    """Return up to last `hours` worth of agent vitals snapshots."""
    entries = _read_jsonl(AGENT_FILE)
    limit = min(int(hours * 12), MAX_ENTRIES)
    return entries[-limit:]


def start_collector():
    """Launch the background snapshot thread. Safe to call multiple times."""
    def run():
        # Take an immediate snapshot so history isn't empty on first load
        try:
            _snapshot()
        except Exception:
            pass
        while True:
            time.sleep(INTERVAL)
            try:
                _snapshot()
            except Exception:
                pass

    t = threading.Thread(target=run, daemon=True, name='metrics-collector')
    t.start()
    return t
