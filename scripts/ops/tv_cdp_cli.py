#!/usr/bin/env python3
"""Simple CDP-backed CLI for the local TradingView Desktop instance.

Wraps the ``tv`` binary (which already speaks CDP) with a few direct CDP
operations for cases where we want a repo-local, dependency-light path:

* status       — probe the CDP HTTP endpoint and report connection health.
* watchlist    — list the current watchlist via ``tv watchlist get``.
* screenshot   — capture the active TradingView tab directly over CDP
                 (``Page.captureScreenshot``) and save it to a file.
* refresh      — reload the active TradingView tab over CDP.
* layout list  — list saved chart layouts via ``tv layout list``.
* layout switch <name> — switch to a saved layout via ``tv layout switch``.

Environment:
* CDP_HOST — default ``127.0.0.1``
* CDP_PORT — default ``9222``
* TV_BIN   — default ``tv`` (expected on PATH, e.g. ``/opt/homebrew/bin/tv``)

This tool is intentionally read-only / low-mutation. It does not create
alerts, edit Pine scripts, or submit orders.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import logging
import os
import subprocess
import urllib.request
from pathlib import Path
from typing import Any

import websockets

log = logging.getLogger(__name__)

DEFAULT_CDP_HOST = os.getenv("CDP_HOST", "127.0.0.1")
DEFAULT_CDP_PORT = int(os.getenv("CDP_PORT", "9222"))
DEFAULT_TV_BIN = os.getenv("TV_BIN", "tv")


def _cdp_http_json(path: str, host: str, port: int) -> Any:
    url = f"http://{host}:{port}{path}"
    with urllib.request.urlopen(url, timeout=10) as response:
        return json.loads(response.read())


def _find_tv_tab(pages: list[dict[str, Any]]) -> dict[str, Any] | None:
    for page in pages:
        url = (page.get("url") or "").lower()
        title = (page.get("title") or "").lower()
        if "tradingview" in url or "tradingview" in title:
            return page
    return None


def cdp_status(host: str = DEFAULT_CDP_HOST, port: int = DEFAULT_CDP_PORT) -> dict[str, Any]:
    """Probe CDP HTTP endpoint and count TradingView tabs."""
    try:
        version = _cdp_http_json("/json/version", host, port)
    except Exception as exc:  # noqa: BLE001
        return {
            "cdp_reachable": False,
            "error": f"{type(exc).__name__}: {exc}",
            "host": host,
            "port": port,
        }

    pages: list[dict[str, Any]] = _cdp_http_json("/json/list", host, port)
    tv_tab = _find_tv_tab(pages)
    return {
        "cdp_reachable": True,
        "host": host,
        "port": port,
        "browser": version.get("Browser"),
        "total_tabs": len(pages),
        "tv_tab_found": tv_tab is not None,
        "tv_tab": {
            "id": tv_tab.get("id"),
            "title": tv_tab.get("title"),
            "url": tv_tab.get("url"),
            "webSocketDebuggerUrl": tv_tab.get("webSocketDebuggerUrl"),
        }
        if tv_tab
        else None,
    }


async def _cdp_ws_session(
    host: str,
    port: int,
) -> tuple[websockets.WebSocketClientProtocol, dict[str, Any]]:
    pages = _cdp_http_json("/json/list", host, port)
    tv_tab = _find_tv_tab(pages)
    if tv_tab is None:
        raise RuntimeError("No TradingView tab found in CDP target list")
    ws_url = tv_tab.get("webSocketDebuggerUrl")
    if not ws_url:
        raise RuntimeError("TradingView tab has no webSocketDebuggerUrl")
    ws = await websockets.connect(ws_url)
    return ws, tv_tab


async def cdp_screenshot(
    output_path: str,
    host: str = DEFAULT_CDP_HOST,
    port: int = DEFAULT_CDP_PORT,
) -> dict[str, Any]:
    """Capture the active TradingView tab via CDP and write PNG to disk."""
    ws, tv_tab = await _cdp_ws_session(host, port)
    request_id = 0

    def next_id() -> int:
        nonlocal request_id
        request_id += 1
        return request_id

    async def send(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        msg = {"id": next_id(), "method": method, "params": params or {}}
        await ws.send(json.dumps(msg))
        while True:
            raw = await ws.recv()
            data = json.loads(raw)
            if data.get("id") == msg["id"]:
                if "error" in data:
                    raise RuntimeError(f"CDP {method} error: {data['error']}")
                return data.get("result", {})

    try:
        await send("Page.enable")
        result = await send("Page.captureScreenshot", {"format": "png"})
        b64 = result.get("data")
        if not b64:
            raise RuntimeError("CDP screenshot returned no data")
        target = Path(output_path).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(base64.b64decode(b64))
        return {
            "ok": True,
            "path": str(target),
            "byte_size": target.stat().st_size,
            "tab_title": tv_tab.get("title"),
            "tab_url": tv_tab.get("url"),
        }
    finally:
        await ws.close()


async def cdp_refresh(
    host: str = DEFAULT_CDP_HOST,
    port: int = DEFAULT_CDP_PORT,
) -> dict[str, Any]:
    """Reload the active TradingView tab via CDP."""
    ws, tv_tab = await _cdp_ws_session(host, port)
    request_id = 0

    def next_id() -> int:
        nonlocal request_id
        request_id += 1
        return request_id

    async def send(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        msg = {"id": next_id(), "method": method, "params": params or {}}
        await ws.send(json.dumps(msg))
        while True:
            raw = await ws.recv()
            data = json.loads(raw)
            if data.get("id") == msg["id"]:
                if "error" in data:
                    raise RuntimeError(f"CDP {method} error: {data['error']}")
                return data.get("result", {})

    try:
        await send("Page.enable")
        await send("Page.reload", {"ignoreCache": True})
        return {
            "ok": True,
            "refreshed": True,
            "tab_title": tv_tab.get("title"),
            "tab_url": tv_tab.get("url"),
        }
    finally:
        await ws.close()


def _run_tv(tv_bin: str, *args: str, check: bool = False) -> dict[str, Any]:
    cmd = [tv_bin, *args]
    proc = subprocess.run(
        cmd,
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
        "command": " ".join(cmd),
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "payload": payload,
        "parse_error": parse_error,
    }


def cmd_status(args: argparse.Namespace) -> int:
    result = cdp_status(host=args.cdp_host, port=args.cdp_port)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("cdp_reachable") else 1


def cmd_watchlist(args: argparse.Namespace) -> int:
    result = _run_tv(args.tv_bin, "watchlist", "get")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


def cmd_screenshot(args: argparse.Namespace) -> int:
    result = asyncio.run(
        cdp_screenshot(
            output_path=args.output,
            host=args.cdp_host,
            port=args.cdp_port,
        )
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("ok") else 1


def cmd_refresh(args: argparse.Namespace) -> int:
    result = asyncio.run(
        cdp_refresh(
            host=args.cdp_host,
            port=args.cdp_port,
        )
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("ok") else 1


def cmd_layout_list(args: argparse.Namespace) -> int:
    result = _run_tv(args.tv_bin, "layout", "list")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


def cmd_layout_switch(args: argparse.Namespace) -> int:
    result = _run_tv(args.tv_bin, "layout", "switch", args.name)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


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
        default=DEFAULT_TV_BIN,
        help=f"tv binary path (default: {DEFAULT_TV_BIN})",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")

    sub = parser.add_subparsers(dest="command", required=True)

    p_status = sub.add_parser("status", help="Probe CDP endpoint health")
    p_status.set_defaults(func=cmd_status)

    p_watchlist = sub.add_parser("watchlist", help="List current TradingView watchlist")
    p_watchlist.set_defaults(func=cmd_watchlist)

    p_screenshot = sub.add_parser("screenshot", help="Capture TradingView chart via CDP")
    p_screenshot.add_argument(
        "-o",
        "--output",
        default="data/tradingview_screenshots/tv_chart.png",
        help="Output PNG path (default: data/tradingview_screenshots/tv_chart.png)",
    )
    p_screenshot.set_defaults(func=cmd_screenshot)

    p_refresh = sub.add_parser("refresh", help="Reload the active TradingView tab via CDP")
    p_refresh.set_defaults(func=cmd_refresh)

    p_layout = sub.add_parser("layout", help="TradingView saved layouts")
    layout_sub = p_layout.add_subparsers(dest="layout_command", required=True)
    p_layout_list = layout_sub.add_parser("list", help="List saved layouts")
    p_layout_list.set_defaults(func=cmd_layout_list)
    p_layout_switch = layout_sub.add_parser("switch", help="Switch to a saved layout")
    p_layout_switch.add_argument("name", help="Layout name or ID")
    p_layout_switch.set_defaults(func=cmd_layout_switch)

    args = parser.parse_args(argv)

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.WARNING)

    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
