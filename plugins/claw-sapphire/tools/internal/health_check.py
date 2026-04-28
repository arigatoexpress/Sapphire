#!/usr/bin/env python3
"""Sapphire Unified Health Check — one command to see everything.

Checks all services, repos, scheduled tasks, and data pipelines.
Returns a single JSON status with green/yellow/red for each component.

Usage:
    echo '{}' | python3 health_check.py
    echo '{"verbose": true}' | python3 health_check.py
"""

from __future__ import annotations

import concurrent.futures
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

SAPPHIRE_DIR = Path.home() / "Code" / "Sapphire"
SECRETS_DIR = Path(
    os.getenv("SAPPHIRE_SECRETS_DIR", str(Path.home() / ".config" / "sapphire-secrets"))
)
THO_BASE_URL = os.getenv(
    "THO_BASE_URL", "https://project-go-forward-691674245427.us-central1.run.app"
)


def _load_tho_pin() -> str | None:
    pin = os.getenv("THO_ADMIN_PIN")
    if pin:
        return pin.strip() or None
    path = SECRETS_DIR / "tho_admin_pin"
    try:
        if path.is_file():
            return path.read_text().strip() or None
    except OSError:
        pass
    return None


def _check_url(url: str, timeout: int = 5) -> tuple[bool, str]:
    """Check if a URL is reachable."""
    import ssl
    import urllib.error
    import urllib.request

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


def check_tho_deep(timeout: int = 15) -> dict:
    """Deep THO probe: JWT auth round-trip + Firestore read + templates (GCS-backed).

    A green `/health` means the process is up; this verifies the business path
    still works (auth → DB → document pipeline). Requires THO_ADMIN_PIN; if
    absent, returns a single skipped entry rather than a red.
    """
    import ssl
    import urllib.error
    import urllib.request

    pin = _load_tho_pin()
    if not pin:
        return {
            "tho-deep:auth": {
                "status": "yellow",
                "detail": "THO_ADMIN_PIN not set — deep probe skipped (surface /health unaffected)",
            }
        }

    try:
        import certifi

        ctx = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        ctx = ssl.create_default_context()

    results: dict[str, dict] = {}

    # 1) JWT auth round-trip
    token = ""
    try:
        req = urllib.request.Request(
            f"{THO_BASE_URL}/api/admin/verify",
            data=json.dumps({"pin": pin}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            body = json.loads(resp.read())
        token = (body or {}).get("token", "")
        if len(token) > 20:
            results["tho-deep:auth"] = {
                "status": "green",
                "detail": f"JWT issued ({len(token)} chars)",
            }
        else:
            results["tho-deep:auth"] = {"status": "red", "detail": "verify returned no token"}
    except urllib.error.HTTPError as e:
        results["tho-deep:auth"] = {"status": "red", "detail": f"HTTP {e.code}: {e.reason}"}
    except Exception as e:
        results["tho-deep:auth"] = {"status": "red", "detail": str(e)[:100]}

    if not token:
        # Skip Firestore/GCS probes if auth failed
        results["tho-deep:firestore"] = {"status": "red", "detail": "skipped (no auth token)"}
        results["tho-deep:templates"] = {"status": "red", "detail": "skipped (no auth token)"}
        return results

    headers = {"X-Admin-Token": token}

    # 2) Firestore read (customers count — cheap, doesn't write)
    try:
        req = urllib.request.Request(f"{THO_BASE_URL}/api/customers/count", headers=headers)
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            body = json.loads(resp.read())
        total = (body or {}).get("total", 0)
        if total > 0:
            results["tho-deep:firestore"] = {
                "status": "green",
                "detail": f"{total:,} customers readable",
            }
        else:
            results["tho-deep:firestore"] = {"status": "yellow", "detail": "reachable but count=0"}
    except urllib.error.HTTPError as e:
        results["tho-deep:firestore"] = {"status": "red", "detail": f"HTTP {e.code}: {e.reason}"}
    except Exception as e:
        results["tho-deep:firestore"] = {"status": "red", "detail": str(e)[:100]}

    # 3) Templates list (document pipeline — backed by GCS)
    try:
        req = urllib.request.Request(f"{THO_BASE_URL}/api/documents/templates", headers=headers)
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            body = json.loads(resp.read())
        templates = (body or {}).get("templates", [])
        if len(templates) >= 1:
            results["tho-deep:templates"] = {
                "status": "green",
                "detail": f"{len(templates)} templates listed",
            }
        else:
            results["tho-deep:templates"] = {"status": "yellow", "detail": "reachable but empty"}
    except urllib.error.HTTPError as e:
        results["tho-deep:templates"] = {"status": "red", "detail": f"HTTP {e.code}: {e.reason}"}
    except Exception as e:
        results["tho-deep:templates"] = {"status": "red", "detail": str(e)[:100]}

    return results


def _check_process(name: str) -> bool:
    """Check if a LaunchAgent is loaded."""
    try:
        r = subprocess.run(["launchctl", "list"], capture_output=True, text=True, timeout=5)
        return name in r.stdout
    except Exception:
        return False


def check_services(profile: str = "full") -> dict:
    """Check all running services."""
    services = {
        "control-plane:8082": ("http://127.0.0.1:8082/health", "com.sapphire.control-plane"),
        "dashboard:8080": (
            "http://127.0.0.1:8080/",
            "com.sapphire.dashboard",
        ),  # 401 = running (auth required)
        "signal-logger:18081": ("http://127.0.0.1:18081/health", "com.sapphire.signal-logger"),
        "openbb:6900": (
            "http://127.0.0.1:6900/api/v1/equity/price/quote?symbol=AAPL&provider=yfinance",
            "com.sapphire.openbb-api",
        ),
        "redis:6379": (None, "homebrew.mxcl.redis"),
        "regional-intel:8787": ("http://127.0.0.1:8787/", "com.sapphire.regional-intel"),
        "tho-cloud-run": (
            "https://project-go-forward-691674245427.us-central1.run.app/health",
            None,
        ),  # 10s for cold start
    }
    if profile == "brief":
        services.pop("tho-cloud-run", None)
        services.pop("openbb:6900", None)

    def _check(name: str, url: str | None, agent: str | None) -> tuple[str, dict]:
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

        return name, {"status": status, "detail": detail}

    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(6, len(services) or 1)) as pool:
        futures = [pool.submit(_check, name, url, agent) for name, (url, agent) in services.items()]
        for future in concurrent.futures.as_completed(futures):
            name, payload = future.result()
            results[name] = payload
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

    def _check_repo(name: str, path: Path) -> tuple[str, dict]:
        if not path.exists():
            return name, {"status": "red", "detail": "Directory not found"}
        try:
            # Check for uncommitted changes
            r = subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True,
                text=True,
                cwd=str(path),
                timeout=5,
            )
            dirty = len(r.stdout.strip().split("\n")) if r.stdout.strip() else 0

            # Check ahead/behind
            r2 = subprocess.run(
                ["git", "log", "--oneline", "-1", "--format=%h %s"],
                capture_output=True,
                text=True,
                cwd=str(path),
                timeout=5,
            )
            last_commit = r2.stdout.strip()

            status = "green" if dirty == 0 else "yellow"
            detail = "clean" if dirty == 0 else f"{dirty} uncommitted files"
            detail += f" | last: {last_commit[:60]}"

            return name, {"status": status, "detail": detail}
        except Exception as e:
            return name, {"status": "red", "detail": str(e)[:100]}

    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(6, len(repos) or 1)) as pool:
        futures = [pool.submit(_check_repo, name, path) for name, path in repos.items()]
        for future in concurrent.futures.as_completed(futures):
            name, payload = future.result()
            results[name] = payload
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


def check_inference(profile: str = "full") -> dict:
    """Check inference endpoints."""
    results = {}

    # Mac Ollama
    ok, msg = _check_url("http://127.0.0.1:11434/api/tags", timeout=3)
    results["mac_ollama"] = {"status": "green" if ok else "red", "detail": msg}

    if profile == "brief":
        return results

    # Windows GPU Ollama
    ok, msg = _check_url("http://100.71.10.48:11434/api/tags", timeout=3)
    results["windows_gpu_ollama"] = {"status": "green" if ok else "red", "detail": msg}

    return results


def main():
    raw = sys.stdin.read().strip()
    params = json.loads(raw) if raw else {}
    profile = params.get("profile", "full")
    verbose = params.get("verbose", False)

    sections: dict[str, dict] = {
        "services": check_services(profile=profile),
        "data_freshness": check_data_freshness(),
    }
    if profile != "brief":
        sections["repos"] = check_repos()
        sections["inference"] = check_inference(profile=profile)
        # Deep THO probe only in full profile — hits Cloud Run 3x per run.
        # Skips itself gracefully if THO_ADMIN_PIN is not configured.
        sections["tho_deep"] = check_tho_deep()
    else:
        sections["inference"] = check_inference(profile=profile)

    # Aggregate status
    all_statuses = []
    for section in sections.values():
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
        "profile": profile,
        "timestamp": datetime.now().isoformat(),
        **sections,
    }
    if verbose:
        result["checked_sections"] = list(sections.keys())

    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
