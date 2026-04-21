"""Telemetry collector — emits inference and service-health snapshots.

Writes one NDJSON file per source per day (append mode):
    data/metrics/YYYY-MM-DD.ndjson    inference proxy /metrics snapshots
    data/health/YYYY-MM-DD.ndjson     service up/down checks

gcp_sync.py picks these files up (sources: metrics, health) and loads
them into sapphire.inference_metrics / sapphire.service_health.

Usage:
    python -m services.pipeline.telemetry_collector            # one snapshot, both
    python -m services.pipeline.telemetry_collector --metrics  # proxy only
    python -m services.pipeline.telemetry_collector --health   # services only
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

log = logging.getLogger("telemetry_collector")

ROOT = Path.home() / "Code" / "Sapphire"
DATA_DIR = ROOT / "data"
METRICS_DIR = DATA_DIR / "metrics"
HEALTH_DIR = DATA_DIR / "health"

PROXY_URL = "http://127.0.0.1:11435/metrics"

# tier key (inference_metrics schema) ← proxy endpoint key
TIER_MAP = {
    "windows-gpu": "gpu_local",
    "pi-rari1":    "pi_rpc",
    "pi-rari2":    "pi_rpc",
    "mac-local":   "mac_ollama",
    "kimi-cloud":  "kimi",
    "proxy":       "proxy",
}

# service_name → (host label, host addr, port, path)
SERVICES = [
    ("control-plane",    "mac",      "127.0.0.1",      8082,  "/health"),
    ("dashboard",        "mac",      "127.0.0.1",      8080,  "/"),
    ("signal-logger",    "mac",      "127.0.0.1",      18081, "/health"),
    ("inference-proxy",  "mac",      "127.0.0.1",      11435, "/health"),
    ("openbb-api",       "mac",      "127.0.0.1",      6900,  "/"),
    ("ollama-mac",       "mac",      "127.0.0.1",      11434, "/api/tags"),
    ("ollama-windows",   "windows",  "100.71.10.48",   11434, "/api/tags"),
    ("ollama-rari1",     "rari1",    "100.120.191.1",  11434, "/api/tags"),
    ("ollama-rari2",     "rari2",    "100.87.225.89",  11434, "/api/tags"),
    ("regional-intel",   "mac",      "127.0.0.1",      8787,  "/health"),
    ("tho-cloud-run",    "cloud_run","project-go-forward-691674245427.us-central1.run.app", 443, "/"),
]


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _today() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


def _stable_id(*parts: object) -> str:
    return hashlib.sha1("::".join(str(p) for p in parts).encode()).hexdigest()[:16]


def _append_ndjson(path: Path, rows: list[dict]) -> int:
    if not rows:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        for r in rows:
            f.write(json.dumps(r, default=str) + "\n")
    return len(rows)


def collect_metrics() -> list[dict]:
    """Snapshot inference proxy /metrics into inference_metrics rows."""
    ts = _now_iso()
    try:
        with urllib.request.urlopen(PROXY_URL, timeout=5) as resp:
            data = json.load(resp)
    except Exception as e:
        log.warning("proxy /metrics unreachable: %s", e)
        return []

    rows: list[dict] = []
    metrics = data.get("metrics") or {}
    for endpoint, m in metrics.items():
        tier = TIER_MAP.get(endpoint, endpoint)
        requests = int(m.get("requests") or 0)
        success  = int(m.get("success")  or 0)
        failure  = int(m.get("failure")  or m.get("errors") or 0)
        avg_ms   = m.get("avg_ms") or 0
        rows.append({
            "metric_id":      _stable_id(ts, endpoint),
            "tier":           tier,
            "model":          endpoint,
            "requests":       requests,
            "success":        success,
            "errors":         failure,
            "avg_latency_ms": float(avg_ms) if avg_ms else None,
            "p95_latency_ms": None,
            "tokens_in":      None,
            "tokens_out":     None,
            "cost_usd":       None,
            "timestamp":      ts,
            "ingested_at":    ts,
        })
    return rows


def _probe(host: str, port: int, path: str, timeout: float = 5.0) -> tuple[str, int | None, float | None, str | None]:
    """Return (status, http_code, response_ms, error_msg)."""
    scheme = "https" if port == 443 else "http"
    url = f"{scheme}://{host}:{port}{path}" if port not in (80, 443) else f"{scheme}://{host}{path}"
    t0 = datetime.now(UTC)
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            rtt = (datetime.now(UTC) - t0).total_seconds() * 1000.0
            code = resp.status
            return ("healthy" if 200 <= code < 400 else "degraded", code, rtt, None)
    except urllib.error.HTTPError as e:
        rtt = (datetime.now(UTC) - t0).total_seconds() * 1000.0
        return ("degraded", e.code, rtt, str(e)[:200])
    except Exception as e:
        return ("down", None, None, str(e)[:200])


def collect_health() -> list[dict]:
    """Probe each known service and emit service_health rows."""
    ts = _now_iso()
    rows: list[dict] = []
    for name, host_label, addr, port, path in SERVICES:
        status, code, rtt, err = _probe(addr, port, path)
        rows.append({
            "snapshot_id":  _stable_id(ts, name),
            "service_name": name,
            "host":         host_label,
            "status":       status,
            "response_ms":  rtt,
            "endpoint":     f"{addr}:{port}{path}",
            "http_status":  code,
            "error":        err,
            "cpu_pct":      None,
            "memory_pct":   None,
            "timestamp":    ts,
            "ingested_at":  ts,
        })
    return rows


def run(emit_metrics: bool = True, emit_health: bool = True) -> dict[str, int]:
    counts = {"metrics": 0, "health": 0}
    if emit_metrics:
        rows = collect_metrics()
        counts["metrics"] = _append_ndjson(METRICS_DIR / f"{_today()}.ndjson", rows)
    if emit_health:
        rows = collect_health()
        counts["health"] = _append_ndjson(HEALTH_DIR / f"{_today()}.ndjson", rows)
    return counts


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--metrics", action="store_true", help="Only collect inference metrics")
    p.add_argument("--health",  action="store_true", help="Only collect service health")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        # Route INFO/DEBUG to stdout so the LaunchAgent's *-err.log only
        # captures real errors (tracebacks still go to stderr naturally).
        stream=sys.stdout,
    )
    if not args.metrics and not args.health:
        args.metrics = args.health = True
    counts = run(emit_metrics=args.metrics, emit_health=args.health)
    print(json.dumps(counts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
