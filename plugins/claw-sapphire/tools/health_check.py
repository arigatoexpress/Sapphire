#!/usr/bin/env python3
"""Sapphire Unified Health Check — one command to see everything.

Checks all services, repos, scheduled tasks, and data pipelines.
Returns a single JSON status with green/yellow/red for each component.

Usage:
    echo '{}' | python3 health_check.py
    echo '{"verbose": true}' | python3 health_check.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

SAPPHIRE_DIR = Path.home() / "Code" / "Sapphire"


def _check_url(url: str, timeout: int = 5) -> tuple[bool, str]:
    """Check if a URL is reachable."""
    import ssl
    import urllib.request
    import urllib.error
    try:
        import certifi
        ctx = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        ctx = ssl.create_default_context()
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return True, f"{resp.status} OK"
    except urllib.error.HTTPError as e:
        # 401/403 means the service IS running but requires auth — that's green
        if e.code in (401, 403):
            return True, f"{e.code} (auth required, service running)"
        return False, f"HTTP {e.code}: {e.reason}"
    except Exception as e:
        return False, str(e)[:100]


def _check_process(name: str) -> bool:
    """Check if a LaunchAgent is loaded."""
    try:
        r = subprocess.run(["launchctl", "list"], capture_output=True, text=True, timeout=5)
        return name in r.stdout
    except Exception:
        return False


def check_services() -> dict:
    """Check all running services."""
    services = {
        "control-plane:8082": ("http://127.0.0.1:8082/health", "com.sapphire.control-plane"),
        "dashboard:8080": ("http://127.0.0.1:8080/", "com.sapphire.dashboard"),  # 401 = running (auth required)
        "signal-logger:18081": ("http://127.0.0.1:18081/health", "com.sapphire.signal-logger"),
        "openbb:6900": ("http://127.0.0.1:6900/api/v1/equity/price/quote?symbol=AAPL&provider=yfinance", "com.sapphire.openbb-api"),
        "redis:6379": (None, "homebrew.mxcl.redis"),
        "regional-intel:8787": ("http://127.0.0.1:8787/", "com.sapphire.regional-intel"),
        "tho-cloud-run": ("https://project-go-forward-691674245427.us-central1.run.app/health", None),  # 10s for cold start
    }

    results = {}
    for name, (url, agent) in services.items():
        status = "unknown"
        detail = ""

        if url:
            t = 10 if "cloud-run" in name or "run.app" in url else 5
            ok, msg = _check_url(url, timeout=t)
            status = "green" if ok else "red"
            detail = msg
        if agent:
            loaded = _check_process(agent)
            if not loaded:
                status = "red"
                detail = f"LaunchAgent not loaded: {agent}"
            elif status == "unknown":
                status = "green"
                detail = "LaunchAgent loaded"

        results[name] = {"status": status, "detail": detail}

    return results


def check_repos() -> dict:
    """Check git status of all repos."""
    repos = {
        "Sapphire": Path.home() / "Code" / "Sapphire",
        "Project-Go-Forward": Path.home() / "Code" / "Project-Go-Forward",
        "cyber-threat-bot": Path.home() / "Code" / "cyber-threat-bot",
        "regional-intel-workbench": Path.home() / "Code" / "regional-intel-workbench",
        "Cointracker": Path.home() / "Code" / "Cointracker",
        "claw-code": Path.home() / "Code" / "claw-code",
    }

    results = {}
    for name, path in repos.items():
        if not path.exists():
            results[name] = {"status": "red", "detail": "Directory not found"}
            continue
        try:
            # Check for uncommitted changes
            r = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True,
                             cwd=str(path), timeout=5)
            dirty = len(r.stdout.strip().split("\n")) if r.stdout.strip() else 0

            # Check ahead/behind
            r2 = subprocess.run(["git", "log", "--oneline", "-1", "--format=%h %s"],
                              capture_output=True, text=True, cwd=str(path), timeout=5)
            last_commit = r2.stdout.strip()

            status = "green" if dirty == 0 else "yellow"
            detail = f"clean" if dirty == 0 else f"{dirty} uncommitted files"
            detail += f" | last: {last_commit[:60]}"

            results[name] = {"status": status, "detail": detail}
        except Exception as e:
            results[name] = {"status": "red", "detail": str(e)[:100]}

    return results


def check_data_freshness() -> dict:
    """Check if data pipelines are producing fresh output."""
    checks = {
        "trading_signals": SAPPHIRE_DIR / "data" / "trading_signals.jsonl",
        "trading_predictions": SAPPHIRE_DIR / "data" / "trading_predictions.jsonl",
        "threat_intel": SAPPHIRE_DIR / "data" / "threat_intel",
        "starred_repos": SAPPHIRE_DIR / "data" / "starred_repos" / "starred.json",
        "market_pulse": SAPPHIRE_DIR / "data" / "market_pulse",
    }

    results = {}
    now = datetime.now()

    for name, path in checks.items():
        if not path.exists():
            results[name] = {"status": "red", "detail": "Missing"}
            continue

        if path.is_dir():
            # Check most recent file in dir
            files = sorted(path.iterdir(), key=lambda f: f.stat().st_mtime, reverse=True)
            if not files:
                results[name] = {"status": "red", "detail": "Empty directory"}
                continue
            path = files[0]

        mtime = datetime.fromtimestamp(path.stat().st_mtime)
        age_hours = (now - mtime).total_seconds() / 3600
        size = path.stat().st_size

        if age_hours < 24:
            status = "green"
        elif age_hours < 72:
            status = "yellow"
        else:
            status = "red"

        results[name] = {
            "status": status,
            "detail": f"{age_hours:.0f}h old, {size:,} bytes",
            "last_updated": mtime.isoformat(),
        }

    return results


def check_inference() -> dict:
    """Check inference endpoints."""
    results = {}

    # Mac Ollama
    ok, msg = _check_url("http://127.0.0.1:11434/api/tags", timeout=3)
    results["mac_ollama"] = {"status": "green" if ok else "red", "detail": msg}

    # Windows GPU Ollama
    ok, msg = _check_url("http://100.71.10.48:11434/api/tags", timeout=3)
    results["windows_gpu_ollama"] = {"status": "green" if ok else "red", "detail": msg}

    return results


def main():
    raw = sys.stdin.read().strip()
    params = json.loads(raw) if raw else {}
    verbose = params.get("verbose", False)

    services = check_services()
    repos = check_repos()
    data = check_data_freshness()
    inference = check_inference()

    # Aggregate status
    all_statuses = []
    for section in [services, repos, data, inference]:
        for item in section.values():
            all_statuses.append(item["status"])

    green = all_statuses.count("green")
    yellow = all_statuses.count("yellow")
    red = all_statuses.count("red")

    if red > 0:
        overall = "RED"
    elif yellow > 0:
        overall = "YELLOW"
    else:
        overall = "GREEN"

    result = {
        "overall": overall,
        "summary": f"{green} green, {yellow} yellow, {red} red out of {len(all_statuses)} checks",
        "timestamp": datetime.now().isoformat(),
        "services": services,
        "repos": repos,
        "data_freshness": data,
        "inference": inference,
    }

    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
