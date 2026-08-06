"""Thin HTTP client for Grok Bridge (research workers only).

Does not place orders, clear killswitches, or hold signing authority.
Supports:
  - App surface:  {base}/api/bridge/{health,chat,new,history,diagnostics,test}
  - Classic Mac:  {base}/{health,chat,new,history}  when path_style='classic'
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class BridgeChatResult:
    ok: bool
    response: str | None
    error: str | None
    latency_ms: int | None
    mode: str | None
    raw: Mapping[str, Any]


class GrokBridgeClient:
    """Bounded Grok Bridge client for Sapphire research paths."""

    def __init__(
        self,
        base_url: str | None = None,
        *,
        path_style: str | None = None,
        timeout: float = 90.0,
    ) -> None:
        resolved = (
            base_url
            or os.environ.get("GROK_BRIDGE_APP_URL")
            or os.environ.get("GROK_BRIDGE_URL")
            or "http://127.0.0.1:8080"
        ).rstrip("/")
        self.base_url = resolved
        if path_style:
            self.path_style = path_style
        elif os.environ.get("GROK_BRIDGE_PATH_STYLE"):
            self.path_style = os.environ["GROK_BRIDGE_PATH_STYLE"]
        elif resolved.endswith(":19998") or "19998" in resolved:
            self.path_style = "classic"
        else:
            self.path_style = "app"
        self.timeout = timeout

    def _path(self, name: str) -> str:
        if self.path_style == "classic":
            return f"{self.base_url}/{name}"
        return f"{self.base_url}/api/bridge/{name}"

    def _request(
        self,
        method: str,
        name: str,
        body: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        data = None if body is None else json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            self._path(name),
            data=data,
            method=method,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as res:
                raw = res.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(err_body)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass
            return {"ok": False, "error": f"HTTP {exc.code}: {err_body[:200]}"}
        except Exception as exc:  # noqa: BLE001 — boundary client
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {"ok": False, "error": "invalid JSON from bridge"}
        return parsed if isinstance(parsed, dict) else {"ok": False, "error": "non-object JSON"}

    def health(self) -> dict[str, Any]:
        return self._request("GET", "health")

    def diagnostics(self, *, live: bool = True) -> dict[str, Any]:
        # diagnostics only on app surface
        if self.path_style == "classic":
            return {"ok": False, "error": "diagnostics not available on classic bridge"}
        suffix = "diagnostics" if live else "diagnostics"
        # use health-style path helper + query
        url = f"{self._path(suffix)}?live={'1' if live else '0'}"
        req = urllib.request.Request(url, method="GET", headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as res:
                return json.loads(res.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    def chat(self, prompt: str, *, timeout: int | None = None) -> BridgeChatResult:
        payload: dict[str, Any] = {"prompt": prompt}
        if timeout is not None:
            payload["timeout"] = timeout
        raw = self._request("POST", "chat", payload)
        ok = bool(raw.get("ok", "response" in raw and raw.get("error") is None))
        return BridgeChatResult(
            ok=ok and bool(raw.get("response")),
            response=raw.get("response") if isinstance(raw.get("response"), str) else None,
            error=None if ok else str(raw.get("error") or raw.get("code") or "chat failed"),
            latency_ms=raw.get("latencyMs") if isinstance(raw.get("latencyMs"), int) else raw.get("latency_ms"),
            mode=raw.get("mode") if isinstance(raw.get("mode"), str) else None,
            raw=raw,
        )

    def new_conversation(self) -> dict[str, Any]:
        return self._request("POST", "new")

    def history(self) -> dict[str, Any]:
        return self._request("GET", "history")

    def self_test(self) -> dict[str, Any]:
        if self.path_style == "classic":
            return {"ok": False, "error": "self_test not available on classic bridge"}
        return self._request("POST", "test")
