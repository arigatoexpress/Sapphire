"""Grok transport client — mac-bridge → OIDC → API key → sim (pure helpers).

Does not place trades. Network only when explicitly querying with a live base URL.
Default health probe is best-effort and fails closed to the next rail.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

DEFAULT_BRIDGE_URL = "http://127.0.0.1:19998"
TRANSPORT_ORDER = ("mac-bridge", "oidc", "api-key", "sim")


@dataclass(frozen=True)
class TransportPick:
    rail: str
    base_url: str | None
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {"rail": self.rail, "base_url": self.base_url, "reason": self.reason}


def bridge_url_from_env(env: Mapping[str, str] | None = None) -> str:
    e = env if env is not None else os.environ
    return (e.get("GROK_BRIDGE_URL") or DEFAULT_BRIDGE_URL).rstrip("/")


def probe_mac_bridge(
    base_url: str | None = None,
    *,
    timeout_s: float = 2.0,
    opener: Any = None,
) -> dict[str, Any]:
    """GET /health on the local mac-bridge. Returns parsed JSON or error dict."""
    url = (base_url or bridge_url_from_env()).rstrip("/") + "/health"
    try:
        req = urllib.request.Request(url, method="GET")
        if opener is None:
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:  # noqa: S310
                body = resp.read().decode("utf-8")
                data = json.loads(body)
                data["_http_status"] = getattr(resp, "status", 200)
                return data
        # custom opener for tests
        with opener.open(req, timeout=timeout_s) as resp:
            body = resp.read().decode("utf-8")
            data = json.loads(body)
            data["_http_status"] = 200
            return data
    except Exception as exc:  # noqa: BLE001 — fail closed to next transport
        return {"status": "error", "mode": "unavailable", "error": str(exc)}


def pick_transport(
    *,
    env: Mapping[str, str] | None = None,
    health: Mapping[str, Any] | None = None,
    prefer_sim: bool = False,
) -> TransportPick:
    """Choose transport rail per BR-02 priority without performing queries."""
    e = env if env is not None else os.environ
    if prefer_sim or e.get("GROK_BRIDGE_SIM") == "1":
        return TransportPick("sim", None, "prefer_sim or GROK_BRIDGE_SIM=1")

    url = bridge_url_from_env(e)
    h = health if health is not None else probe_mac_bridge(url)
    mode = str(h.get("mode") or "")
    if h.get("status") in ("ok", "degraded") and mode == "mac-bridge":
        return TransportPick("mac-bridge", url, "GROK_BRIDGE_URL healthy mac-bridge")

    # OIDC: plant has live grok CLI session file — remote sandboxes usually don't
    if (e.get("GROK_OIDC_OK") or "").lower() in {"1", "true", "yes"}:
        return TransportPick("oidc", None, "GROK_OIDC_OK set (direct CLI/OIDC path)")

    if e.get("XAI_API_KEY") or e.get("GROK_API_KEY"):
        return TransportPick("api-key", None, "XAI_API_KEY/GROK_API_KEY present")

    if mode == "away-sim" or h.get("status") == "error":
        return TransportPick("sim", url if mode == "away-sim" else None, f"fallback sim (health mode={mode or 'n/a'})")

    return TransportPick("sim", None, "no healthy mac-bridge / oidc / api key")


def query_mac_bridge(
    prompt: str,
    *,
    base_url: str | None = None,
    token: str | None = None,
    model: str | None = None,
    timeout_s: float = 150.0,
) -> dict[str, Any]:
    """POST /v1/query to mac-bridge. Raises on hard HTTP failures."""
    root = (base_url or bridge_url_from_env()).rstrip("/")
    url = urljoin(root + "/", "v1/query")
    payload: dict[str, Any] = {"prompt": prompt}
    if model:
        payload["model"] = model
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    tok = token if token is not None else os.environ.get("GROK_BRIDGE_TOKEN", "")
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:  # noqa: S310
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return {"error": body or str(exc), "http_status": exc.code}


def smart_query(
    prompt: str,
    *,
    env: Mapping[str, str] | None = None,
    prefer_sim: bool = False,
) -> dict[str, Any]:
    """Query using transport priority; sim never raises."""
    pick = pick_transport(env=env, prefer_sim=prefer_sim)
    if pick.rail == "mac-bridge" and pick.base_url:
        out = query_mac_bridge(prompt, base_url=pick.base_url)
        out["_transport"] = pick.as_dict()
        return out
    if pick.rail == "api-key":
        return {
            "text": "[api-key] live XAI call not implemented in monorepo client (use plant SDK)",
            "stopReason": "not_implemented",
            "_transport": pick.as_dict(),
        }
    if pick.rail == "oidc":
        return {
            "text": "[oidc] direct grok CLI path is plant-local; use mac-bridge remotely",
            "stopReason": "not_implemented",
            "_transport": pick.as_dict(),
        }
    return {
        "text": f"[away-sim] no live bridge; echo ({len(prompt)} chars)",
        "stopReason": "sim",
        "_transport": pick.as_dict(),
    }
