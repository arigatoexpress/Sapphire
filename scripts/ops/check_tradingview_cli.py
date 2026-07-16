#!/usr/bin/env python3
"""Health check for the TradingView CDP pipeline and related LaunchAgents.

Reports:
* CDP endpoint reachability on CDP_HOST:CDP_PORT (default 127.0.0.1:9222).
* Whether a TradingView tab is present in the CDP target list.
* Load state of the three TradingView-related LaunchAgents:
  - com.sapphire.tradingview-cdp
  - com.sapphire.tradingview-ta-capture
  - com.sapphire.tradingview-pine-batch
* Whether the tv binary is on PATH and responds to ``tv status``.

Exit code:
* 0 if CDP is reachable, a TV tab exists, and all three agents are loaded.
* 1 if any of the above is unhealthy.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import urllib.request
from typing import Any

DEFAULT_CDP_HOST = os.getenv("CDP_HOST", "127.0.0.1")
DEFAULT_CDP_PORT = int(os.getenv("CDP_PORT", "9222"))
TV_AGENTS = (
    "com.sapphire.tradingview-cdp",
    "com.sapphire.tradingview-ta-capture",
    "com.sapphire.tradingview-pine-batch",
)


def _cdp_json(path: str, host: str, port: int) -> Any:
    url = f"http://{host}:{port}{path}"
    with urllib.request.urlopen(url, timeout=10) as response:
        return json.loads(response.read())


def _has_tv_tab(pages: list[dict[str, Any]]) -> bool:
    for page in pages:
        url = (page.get("url") or "").lower()
        title = (page.get("title") or "").lower()
        if "tradingview" in url or "tradingview" in title:
            return True
    return False


def check_cdp(host: str, port: int) -> dict[str, Any]:
    try:
        version = _cdp_json("/json/version", host, port)
        pages = _cdp_json("/json/list", host, port)
        tv_tab_present = _has_tv_tab(pages)
        return {
            "reachable": True,
            "host": host,
            "port": port,
            "browser": version.get("Browser"),
            "total_tabs": len(pages),
            "tv_tab_present": tv_tab_present,
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "reachable": False,
            "host": host,
            "port": port,
            "browser": None,
            "total_tabs": 0,
            "tv_tab_present": False,
            "error": f"{type(exc).__name__}: {exc}",
        }


def check_tv_bin(tv_bin: str = "tv") -> dict[str, Any]:
    proc = subprocess.run(
        [tv_bin, "status"],
        text=True,
        capture_output=True,
        check=False,
    )
    payload: Any = None
    parse_error: str | None = None
    if proc.stdout.strip():
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            parse_error = str(exc)
    return {
        "found": proc.returncode in (0, 1),  # 0 or 1 are normal for tv status
        "returncode": proc.returncode,
        "ok": proc.returncode == 0,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
        "payload": payload,
        "parse_error": parse_error,
    }


def check_launchagent(label: str) -> dict[str, Any]:
    proc = subprocess.run(
        ["launchctl", "list", label],
        text=True,
        capture_output=True,
        check=False,
    )
    # launchctl list returns 0 if loaded, nonzero if not loaded.
    loaded = proc.returncode == 0
    pid: int | None = None
    status: int | None = None
    if loaded:
        # Output is "PID	Status	Label" or "-\t0\t<Label>".
        parts = proc.stdout.strip().split("\t")
        if len(parts) >= 2:
            try:
                pid = int(parts[0]) if parts[0] != "-" else None
                status = int(parts[1])
            except ValueError:
                pass
    return {
        "label": label,
        "loaded": loaded,
        "pid": pid,
        "status": status,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cdp-host",
        default=DEFAULT_CDP_HOST,
        help=f"CDP HTTP host (default: {DEFAULT_CDP_HOST})",
    )
    parser.add_argument(
        "--cdp-port",
        type=int,
        default=DEFAULT_CDP_PORT,
        help=f"CDP HTTP port (default: {DEFAULT_CDP_PORT})",
    )
    parser.add_argument(
        "--tv-bin",
        default="tv",
        help="tv binary name/path (default: tv)",
    )
    parser.add_argument(
        "--agents",
        nargs="+",
        default=list(TV_AGENTS),
        help="LaunchAgent labels to check",
    )
    args = parser.parse_args(argv)

    cdp = check_cdp(args.cdp_host, args.cdp_port)
    tv = check_tv_bin(args.tv_bin)
    agents = {label: check_launchagent(label) for label in args.agents}

    all_agents_loaded = all(a["loaded"] for a in agents.values())
    healthy = cdp["reachable"] and cdp["tv_tab_present"] and all_agents_loaded

    report: dict[str, Any] = {
        "healthy": healthy,
        "checked_at": _iso_now(),
        "cdp": cdp,
        "tv_bin": tv,
        "launchagents": agents,
    }

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if healthy else 1


def _iso_now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).replace(microsecond=0).isoformat()


if __name__ == "__main__":
    raise SystemExit(main())
