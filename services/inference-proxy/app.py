"""Sapphire Inference Proxy — OpenAI-compatible failover between Ollama instances.

Tries Windows GPU first (100.71.10.48:11434), falls back to Mac (localhost:11434).
Exposes OpenAI-compatible /v1/chat/completions on port 11435.

This lets hermes-agent talk to a single stable endpoint that's always available.
"""

import json
import urllib.request
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("inference-proxy")

ENDPOINTS = [
    ("windows-gpu", "http://100.71.10.48:11434"),
    ("mac-local", "http://127.0.0.1:11434"),
]
PORT = 11435


class ProxyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            self._respond(200, {"status": "ok", "service": "inference-proxy"})
            return
        for name, base in ENDPOINTS:
            try:
                url = f"{base}{self.path}"
                req = urllib.request.Request(url, headers={"Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=3) as resp:
                    data = resp.read()
                    self.send_response(resp.status)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(data)
                    return
            except Exception:
                continue
        self._respond(503, {"error": "All Ollama endpoints unavailable"})

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        for name, base in ENDPOINTS:
            try:
                url = f"{base}{self.path}"
                req = urllib.request.Request(
                    url, data=body,
                    headers={"Content-Type": "application/json", "Accept": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=60) as resp:
                    data = resp.read()
                    log.info("-> %s via %s", self.path, name)
                    self.send_response(resp.status)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(data)
                    return
            except Exception as e:
                log.warning("x %s failed: %s", name, str(e)[:80])
                continue
        self._respond(503, {"error": "All Ollama endpoints unavailable"})

    def _respond(self, code, body):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())

    def log_message(self, format, *args):
        pass


if __name__ == "__main__":
    server = HTTPServer(("127.0.0.1", PORT), ProxyHandler)
    log.info("Inference proxy on :%d", PORT)
    log.info("Priority: %s", " > ".join(f"{n}={u}" for n, u in ENDPOINTS))
    server.serve_forever()
