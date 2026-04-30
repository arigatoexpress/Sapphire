#!/usr/bin/env python3
"""Read-only Windows TradingView workbench agent.

This service intentionally does not place trades, mutate TradingView, send
Telegram messages, or execute Pine/browser actions. It exposes health and
read-only Chrome DevTools Protocol (CDP) visibility so Sapphire can distinguish
"agent process is up" from "TradingView Desktop is reachable".
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import socket
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

SERVICE_NAME = "windows_tv_agent"
MODE = "read_only_tradingview_workbench_agent"
DEFAULT_CDP_URL = os.environ.get("TRADINGVIEW_CDP_URL", "http://127.0.0.1:9222")
DEFAULT_PORT = int(os.environ.get("WINDOWS_TV_AGENT_PORT", "8081"))
# When set to "1", the agent is only `healthy` if it can also reach a TradingView
# Desktop CDP endpoint locally. Defaults to "0" because the canonical Sapphire
# topology runs TradingView on the Mac commander; the Windows host serves the
# webhook + Ollama + research worker, not the TV workbench.
DEFAULT_CDP_REQUIRED = os.environ.get("WINDOWS_TV_AGENT_CDP_REQUIRED", "0") == "1"

JsonFetcher = Callable[[str, float], Any]


def _json_default(value: Any) -> str:
    return str(value)


def fetch_json(url: str, timeout: float) -> Any:
    with urllib.request.urlopen(url, timeout=timeout) as response:  # nosec B310 - configured local/private CDP URL.
        return json.loads(response.read(1024 * 1024))


def probe_tradingview_cdp(
    *,
    base_url: str = DEFAULT_CDP_URL,
    timeout: float = 2.0,
    fetcher: JsonFetcher = fetch_json,
) -> dict[str, Any]:
    base = base_url.rstrip("/")
    started = time.perf_counter()
    version: dict[str, Any] = {}
    tabs: list[dict[str, Any]] = []
    try:
        version_payload = fetcher(f"{base}/json/version", timeout)
        if isinstance(version_payload, dict):
            version = version_payload
        tabs_payload = fetcher(f"{base}/json", timeout)
        if isinstance(tabs_payload, list):
            tabs = [item for item in tabs_payload if isinstance(item, dict)]
        tradingview_tabs = [
            item
            for item in tabs
            if "tradingview.com" in str(item.get("url") or "").lower()
            or "tradingview" in str(item.get("title") or "").lower()
        ]
        return {
            "healthy": True,
            "status": "healthy",
            "base_url": base,
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "browser": version.get("Browser"),
            "protocol_version": version.get("Protocol-Version"),
            "tab_count": len(tabs),
            "tradingview_tab_count": len(tradingview_tabs),
        }
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return {
            "healthy": False,
            "status": "unreachable",
            "base_url": base,
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "error": f"{exc.__class__.__name__}: {exc}"[:180],
            "tab_count": 0,
            "tradingview_tab_count": 0,
        }


def list_tradingview_tabs(
    *,
    base_url: str = DEFAULT_CDP_URL,
    timeout: float = 2.0,
    fetcher: JsonFetcher = fetch_json,
) -> dict[str, Any]:
    base = base_url.rstrip("/")
    try:
        tabs_payload = fetcher(f"{base}/json", timeout)
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return {
            "status": "unreachable",
            "tabs": [],
            "error": f"{exc.__class__.__name__}: {exc}"[:180],
        }
    tabs = tabs_payload if isinstance(tabs_payload, list) else []
    rows = []
    for item in tabs:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "")
        title = str(item.get("title") or "")
        rows.append(
            {
                "id": item.get("id"),
                "title": title[:160],
                "url_host": url.split("/")[2] if "://" in url and len(url.split("/")) > 2 else "",
                "is_tradingview": "tradingview.com" in url.lower()
                or "tradingview" in title.lower(),
            }
        )
    return {"status": "ok", "tabs": rows, "tab_count": len(rows)}


def build_status_payload(
    *,
    cdp_url: str = DEFAULT_CDP_URL,
    timeout: float = 2.0,
    fetcher: JsonFetcher = fetch_json,
    cdp_required: bool = DEFAULT_CDP_REQUIRED,
) -> dict[str, Any]:
    cdp = probe_tradingview_cdp(base_url=cdp_url, timeout=timeout, fetcher=fetcher)
    cdp_healthy = bool(cdp.get("healthy"))
    # When CDP is not required (canonical topology — TV runs on the Mac), the
    # agent itself is healthy as long as the process is up. We surface CDP
    # reachability separately via the `cdp` block so callers can still see it.
    if cdp_required:
        status = "healthy" if cdp_healthy else "degraded"
    else:
        status = "healthy" if cdp_healthy else "agent_only"
    return {
        "service": SERVICE_NAME,
        "mode": MODE,
        "status": status,
        "cdp_required": cdp_required,
        "timestamp": datetime.now(UTC).isoformat(),
        "host": socket.gethostname(),
        "platform": platform.platform(),
        "safety": {
            "read_only": True,
            "trading_execution_enabled": False,
            "telegram_sends_enabled": False,
            "browser_mutation_enabled": False,
        },
        "capabilities": {
            "health": True,
            "status": True,
            "cdp_status": True,
            "tabs_read_only": True,
            "trade_execution": False,
            "telegram_send": False,
        },
        "cdp": cdp,
    }


class AgentHandler(BaseHTTPRequestHandler):
    cdp_url = DEFAULT_CDP_URL
    cdp_timeout = 2.0

    def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, default=_json_default).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API.
        path = self.path.split("?", 1)[0].rstrip("/") or "/"
        if path in {"/", "/health", "/status", "/cdp/status"}:
            self._send_json(
                build_status_payload(cdp_url=self.cdp_url, timeout=self.cdp_timeout)
            )
            return
        if path == "/tabs":
            self._send_json(
                {
                    **list_tradingview_tabs(
                        base_url=self.cdp_url,
                        timeout=self.cdp_timeout,
                    ),
                    "mode": MODE,
                    "safety": {"read_only": True, "browser_mutation_enabled": False},
                }
            )
            return
        self._send_json({"status": "not_found", "path": path}, status=404)

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API.
        self._send_json(
            {
                "status": "method_not_allowed",
                "service": SERVICE_NAME,
                "safety": {
                    "read_only": True,
                    "trading_execution_enabled": False,
                    "browser_mutation_enabled": False,
                },
            },
            status=405,
        )

    def log_message(self, format: str, *args: Any) -> None:
        message = format % args
        print(f"{datetime.now(UTC).isoformat()} {self.address_string()} {message}", flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=os.environ.get("WINDOWS_TV_AGENT_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--cdp-url", default=DEFAULT_CDP_URL)
    parser.add_argument("--cdp-timeout", type=float, default=2.0)
    args = parser.parse_args(argv)

    AgentHandler.cdp_url = args.cdp_url
    AgentHandler.cdp_timeout = args.cdp_timeout
    server = ThreadingHTTPServer((args.host, args.port), AgentHandler)
    print(
        f"{SERVICE_NAME} serving {MODE} on {args.host}:{args.port} "
        f"(cdp={args.cdp_url})",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
