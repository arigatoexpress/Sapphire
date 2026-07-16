"""Sapphire fleet status aggregator — next-gen autonomous control plane probe.

Polls every live subsystem that does not require operator credentials and
writes a unified JSON snapshot to data/intelligence/latest/fleet_status.json.
The dashboard can surface this as the "Mission Control" health panel and the
morning brief can summarize it.

Run manually:
    python -m services.pipeline.fleet_status

Or via LaunchAgent (recommended every 5 minutes):
    launchctl kickstart -k gui/$UID/com.sapphire.fleet-status
"""
from __future__ import annotations

import json
import logging
import subprocess
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.portfolio.robinhood import get_reader  # noqa: E402

log = logging.getLogger("fleet_status")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)

OUT_PATH = ROOT / "data" / "intelligence" / "latest" / "fleet_status.json"


def _http_get(url: str, timeout: float = 5.0) -> tuple[bool, dict]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return True, json.loads(response.read())
    except Exception as exc:
        return False, {"error": str(exc)}


def _launchctl_running(label: str) -> bool:
    try:
        out = subprocess.run(["launchctl", "list", label], capture_output=True, text=True, timeout=5)
        return out.returncode == 0 and out.stdout.strip().split()[0] != "-"
    except Exception:
        return False


def _tradingview_cdp() -> dict:
    ok, data = _http_get("http://127.0.0.1:9222/json/version", timeout=3)
    if not ok:
        return {"healthy": False, **data}
    return {"healthy": True, "browser": data.get("Browser"), "user_agent": data.get("User-Agent")}


def _webhook_ingress() -> dict:
    local_ok, local_data = _http_get("http://localhost:9090/health", timeout=3)
    tunnel_url_file = ROOT / "data" / "webhook" / "tunnel_url.txt"
    tunnel_url = tunnel_url_file.read_text().strip() if tunnel_url_file.exists() else None
    public_ok = False
    public_data = {}
    if tunnel_url:
        public_ok, public_data = _http_get(f"{tunnel_url}/health", timeout=8)
    return {
        "healthy": local_ok and public_ok,
        "receiver_running": local_ok,
        "receiver_health": local_data if local_ok else public_data,
        "tunnel_url": tunnel_url,
        "public_reachable": public_ok,
    }


def _signal_logger() -> dict:
    ok, data = _http_get("http://localhost:18081/health", timeout=3)
    return {"healthy": ok, **data}


def _dashboard() -> dict:
    # Probe the public root; auth prevents detail, but a 401 means it is up.
    try:
        with urllib.request.urlopen("https://sapphirealpha.xyz/", timeout=8) as response:
            return {"healthy": True, "reachable": True, "http_status": response.status}
    except urllib.error.HTTPError as exc:
        return {"healthy": True, "reachable": True, "http_status": exc.code}
    except Exception as exc:
        return {"healthy": False, "reachable": False, "error": str(exc)}


def _robinhood_crypto() -> dict:
    try:
        reader = get_reader()
        if not reader.is_configured():
            return {"healthy": False, "error": "credentials not loaded"}
        account = reader.get_account()
        portfolio = reader.get_portfolio_value()
        return {
            "healthy": account.get("source") == "robinhood",
            "account_number": account.get("account_number"),
            "buying_power": account.get("buying_power"),
            "is_api_tradable": account.get("is_api_tradable"),
            "equity": portfolio.get("equity"),
            "total_return": portfolio.get("total_return"),
            "position_count": portfolio.get("position_count"),
        }
    except Exception as exc:
        return {"healthy": False, "error": str(exc)}


def _tdr_pro() -> dict:
    latest_path = ROOT / "data" / "intelligence" / "latest" / "tdr_pro_latest.json"
    if not latest_path.exists():
        return {"healthy": False, "error": "no sync summary"}
    try:
        data = json.loads(latest_path.read_text())
        episodes = data.get("episodes", [])
        return {
            "healthy": bool(episodes),
            "episodes_found": len(episodes),
            "latest_title": episodes[0].get("title") if episodes else None,
            "latest_published": episodes[0].get("published") if episodes else None,
            "synced_at": data.get("synced_at"),
        }
    except Exception as exc:
        return {"healthy": False, "error": str(exc)}


def build_snapshot() -> dict:
    return {
        "timestamp": datetime.now(UTC).isoformat(),
        "version": "0.1.0",
        "subsystem": {
            "tradingview_cdp": _tradingview_cdp(),
            "webhook_ingress": _webhook_ingress(),
            "signal_logger": _signal_logger(),
            "dashboard": _dashboard(),
            "robinhood_crypto": _robinhood_crypto(),
            "tdr_pro": _tdr_pro(),
        },
        "launchagents": {
            "webhook-receiver-mac": _launchctl_running("com.sapphire.webhook-receiver-mac"),
            "webhook-tunnel": _launchctl_running("com.sapphire.webhook-tunnel"),
            "signal-logger": _launchctl_running("com.sapphire.signal-logger"),
            "tdr-pro-sync": _launchctl_running("com.sapphire.tdr-pro-sync"),
        },
    }


def main() -> int:
    snapshot = build_snapshot()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(snapshot, indent=2, default=str), encoding="utf-8")
    healthy = sum(1 for s in snapshot["subsystem"].values() if s.get("healthy") or s.get("reachable"))
    total = len(snapshot["subsystem"])
    log.info("fleet status: %d/%d subsystems healthy → %s", healthy, total, OUT_PATH)
    return 0


if __name__ == "__main__":
    sys.exit(main())
