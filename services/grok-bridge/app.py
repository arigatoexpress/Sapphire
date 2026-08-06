"""Sapphire Grok Bridge — local HTTP front door to the Mac's authenticated `grok` CLI session.

Purpose: let environments that cannot invoke the `grok` CLI directly (remote
sandboxes, Cloud Shell, other hosts reached over Tailscale) get Grok answers
through the Mac's already-live SuperGrok OIDC session instead of needing their
own XAI_API_KEY.

Transport priority this bridge fills (per data/grok-web-exports/2026-08-05_bridge-setup.md
and the alpha ledger BR-02/BR-04 entries): Mac bridge (this service) -> SuperGrok
OIDC direct -> XAI_API_KEY -> away-sim. This service itself has exactly one real
backend (the local `grok` CLI, already OIDC-authenticated) plus a sim fallback
for offline tests.

Endpoints:
  GET  /health     — {"mode": "mac-bridge"} when the grok CLI + auth session are present
  POST /v1/query    — {"prompt": "..."} -> shells out to `grok -p <prompt> --output-format json`

No prompt-injection risk from the shell: subprocess is invoked with an argv list,
never a shell string. If GROK_BRIDGE_TOKEN is set, /v1/query requires a matching
`Authorization: Bearer <token>` header (health stays open, matching inference-proxy).
"""

import json
import logging
import os
import shutil
import subprocess
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from socketserver import ThreadingMixIn

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("grok-bridge")

HOST = os.environ.get("GROK_BRIDGE_HOST", "127.0.0.1")
PORT = int(os.environ.get("GROK_BRIDGE_PORT", "19998"))
TOKEN = os.environ.get("GROK_BRIDGE_TOKEN", "")
SIM_MODE = os.environ.get("GROK_BRIDGE_SIM", "0") == "1"
QUERY_TIMEOUT_S = int(os.environ.get("GROK_BRIDGE_TIMEOUT_S", "150"))
GROK_AUTH_FILE = Path.home() / ".grok" / "auth.json"


def _grok_bin() -> str | None:
    return shutil.which("grok")


def _bridge_mode() -> str:
    """mac-bridge = grok CLI installed + an OIDC session file exists; sim otherwise."""
    if SIM_MODE:
        return "away-sim"
    if _grok_bin() and GROK_AUTH_FILE.exists():
        return "mac-bridge"
    return "unavailable"


def _run_grok(prompt: str, model: str | None = None) -> dict:
    grok_bin = _grok_bin()
    if not grok_bin:
        raise RuntimeError("grok CLI not found on PATH")
    cmd = [grok_bin, "-p", prompt, "--output-format", "json"]
    if model:
        cmd.extend(["-m", model])
    result = subprocess.run(  # noqa: S603 — argv list, no shell, no injection surface
        cmd,
        capture_output=True,
        text=True,
        timeout=QUERY_TIMEOUT_S,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"grok CLI exited {result.returncode}: {result.stderr[-500:]}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"grok CLI returned non-JSON output: {exc}") from exc


def _sim_response(prompt: str) -> dict:
    return {
        "text": f"[away-sim] no live Grok session; echoing prompt ({len(prompt)} chars)",
        "stopReason": "sim",
        "sessionId": "sim",
        "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
    }


class BridgeHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        logger.info("%s - %s", self.address_string(), fmt % args)

    def _respond(self, status: int, payload: dict):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        if not TOKEN:
            return True
        return self.headers.get("Authorization") == f"Bearer {TOKEN}"

    def do_GET(self):
        if self.path == "/health":
            mode = _bridge_mode()
            self._respond(
                200,
                {
                    "status": "ok" if mode != "unavailable" else "degraded",
                    "service": "grok-bridge",
                    "mode": mode,
                    "grok_cli": {
                        "available": _grok_bin() is not None,
                        "path": _grok_bin(),
                        "session_present": GROK_AUTH_FILE.exists(),
                    },
                    "port": PORT,
                    "auth_required": bool(TOKEN),
                },
            )
            return
        self._respond(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/v1/query":
            self._respond(404, {"error": "not found"})
            return
        if not self._authorized():
            self._respond(401, {"error": "unauthorized"})
            return

        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            self._respond(400, {"error": "invalid JSON body"})
            return

        prompt = (payload.get("prompt") or "").strip()
        if not prompt:
            self._respond(400, {"error": "missing 'prompt'"})
            return
        model = payload.get("model")

        t0 = time.time()
        try:
            if _bridge_mode() == "away-sim":
                result = _sim_response(prompt)
            else:
                result = _run_grok(prompt, model=model)
            result["latency_ms"] = round((time.time() - t0) * 1000)
            self._respond(200, result)
        except subprocess.TimeoutExpired:
            self._respond(504, {"error": f"grok CLI timed out after {QUERY_TIMEOUT_S}s"})
        except Exception as exc:  # noqa: BLE001 — surface any backend failure to the caller
            logger.error("query failed: %s", exc)
            self._respond(502, {"error": str(exc)})


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


def main():
    server = ThreadingHTTPServer((HOST, PORT), BridgeHandler)
    logger.info(
        "grok-bridge listening on http://%s:%s (mode=%s, auth=%s)",
        HOST,
        PORT,
        _bridge_mode(),
        "on" if TOKEN else "off",
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
