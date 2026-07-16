"""Brave browser automation via Chrome DevTools Protocol (CDP).

Launches Brave with a remote-debugging port and exposes a small async API:

    async with BraveSession(profile_dir=..., port=9222) as session:
        await session.navigate("https://robinhood.com")
        await session.wait(2)
        text = await session.get_text()
        cookies = await session.get_cookies(".robinhood.com")

Authenticated sources (Gmail, Robinhood members area, TradingView web) require
an existing Brave profile with a valid login session.  When Brave is already
running, copy the profile to a temporary directory first to avoid the profile
lock, or launch Brave when the user has quit the browser.

No credentials are handled by this module.  It only drives an already
authenticated browser session.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import subprocess
import tempfile
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import websockets

log = logging.getLogger(__name__)

_BRAVE_BINARY = "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
_BRAVE_PROFILE_ROOT = (
    Path.home() / "Library" / "Application Support" / "BraveSoftware" / "Brave-Browser"
)


def _http_get_json(url: str) -> Any:
    with urllib.request.urlopen(url, timeout=10) as response:
        return json.loads(response.read())


@dataclass
class BraveSession:
    """Async Brave browser session over CDP."""

    profile_dir: Path | str | None = None
    port: int = 9222
    headless: bool = True
    binary: str = _BRAVE_BINARY
    _proc: subprocess.Popen | None = field(default=None, init=False)
    _ws: websockets.WebSocketClientProtocol | None = field(default=None, init=False)
    _tempdir: tempfile.TemporaryDirectory | None = field(default=None, init=False)
    _request_id: int = field(default=0, init=False)

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def _copy_profile(self, source: Path) -> Path:
        """Copy a Brave profile to a temp dir, skipping lock files."""
        self._tempdir = tempfile.TemporaryDirectory(prefix="brave-profile-")
        dest = Path(self._tempdir.name) / "Default"
        dest.mkdir(parents=True, exist_ok=True)
        skip = {"SingletonLock", "SingletonCookie", "SingletonSocket", "running"}
        for item in source.iterdir():
            if item.name in skip:
                continue
            try:
                if item.is_dir():
                    shutil.copytree(
                        item,
                        dest / item.name,
                        dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("*lock*", "*running*"),
                    )
                else:
                    shutil.copy2(item, dest / item.name)
            except (shutil.Error, OSError) as exc:
                log.debug("skipped %s during profile copy: %s", item, exc)
        return Path(self._tempdir.name)

    async def start(self) -> BraveSession:
        if self.profile_dir is None:
            self._tempdir = tempfile.TemporaryDirectory(prefix="brave-profile-")
            profile_arg = str(self._tempdir.name)
        else:
            source = Path(self.profile_dir)
            if source.name == "Default":
                source = source.parent
            # If Default profile exists and Brave may be running, copy it.
            if (source / "Default").exists():
                profile_arg = str(self._copy_profile(source / "Default"))
            else:
                profile_arg = str(source)

        args = [
            self.binary,
            f"--remote-debugging-port={self.port}",
            f"--user-data-dir={profile_arg}",
            "--no-first-run",
            "--no-default-browser-check",
        ]
        if self.headless:
            args.append("--headless=new")

        log.info("starting Brave on CDP port %d", self.port)
        self._proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # Wait for CDP HTTP endpoint.
        for _ in range(30):
            await asyncio.sleep(0.5)
            try:
                pages = _http_get_json(f"http://127.0.0.1:{self.port}/json/list")
                if pages:
                    ws_url = pages[0]["webSocketDebuggerUrl"]
                    self._ws = await websockets.connect(ws_url)
                    break
            except Exception:
                continue
        else:
            raise RuntimeError("Brave CDP did not become available")
        return self

    async def stop(self) -> None:
        if self._ws:
            await self._ws.close()
        if self._proc:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        if self._tempdir:
            self._tempdir.cleanup()

    async def __aenter__(self) -> BraveSession:
        return await self.start()

    async def __aexit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        await self.stop()

    async def _send(self, method: str, params: dict | None = None) -> dict:
        if self._ws is None:
            raise RuntimeError("session not started")
        msg = {"id": self._next_id(), "method": method, "params": params or {}}
        await self._ws.send(json.dumps(msg))
        while True:
            raw = await self._ws.recv()
            data = json.loads(raw)
            if data.get("id") == msg["id"]:
                if "error" in data:
                    raise RuntimeError(f"CDP {method} error: {data['error']}")
                return data.get("result", {})

    async def navigate(self, url: str, wait_load: bool = True) -> None:
        await self._send("Page.enable")
        await self._send("Page.navigate", {"url": url})
        if wait_load:
            await self._wait_for_load()

    async def _wait_for_load(self) -> None:
        for _ in range(60):
            try:
                result = await self._send("Runtime.evaluate", {"expression": "document.readyState"})
                if result.get("result", {}).get("value") == "complete":
                    return
            except Exception:
                pass
            await asyncio.sleep(0.5)
        log.warning("page load timed out")

    async def wait(self, seconds: float) -> None:
        await asyncio.sleep(seconds)

    async def evaluate(self, expression: str) -> Any:
        result = await self._send(
            "Runtime.evaluate", {"expression": expression, "returnByValue": True}
        )
        value = result.get("result", {}).get("value")
        if value is None and result.get("result", {}).get("type") == "undefined":
            return None
        return value

    async def get_text(self) -> str:
        text = await self.evaluate("document.body.innerText")
        return str(text or "")

    async def query_selector_text(self, selector: str) -> str | None:
        expression = "document.querySelector(" + json.dumps(selector) + ")?.innerText"
        result = await self.evaluate(expression)
        return result

    async def get_cookies(self, domain: str | None = None) -> list[dict]:
        await self._send("Network.enable")
        result = await self._send("Network.getCookies", {"urls": []})
        cookies = result.get("cookies", [])
        if domain:
            cookies = [c for c in cookies if domain in c.get("domain", "")]
        return cookies
