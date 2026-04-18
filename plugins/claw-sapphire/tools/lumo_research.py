#!/usr/bin/env python3
"""Sapphire Lumo Research Tool — T5 security-specialized AI via Proton Lumo.

Fronts the Lumo-Api-V2 Node.js server (localhost:3333) which automates
lumo.proton.me via Playwright Firefox. Lumo is Proton's privacy-first AI —
ideal for security research, CVE analysis, and compliance work.

Actions (stdin JSON):
    ask             — Send any query to Lumo
    security_brief  — Specialized CVE/threat research prompt
    status          — Check if Lumo API is reachable

Usage:
    echo '{"action":"ask","query":"What is CVE-2026-1340?","web_search":true}' | python3 lumo_research.py
    echo '{"action":"security_brief","topic":"CVE-2026-1340","depth":"deep"}' | python3 lumo_research.py
    echo '{"action":"status"}' | python3 lumo_research.py

Setup (user must do once):
    cd ~/Code/lumo-api && node generate_auth.js   # Opens browser for Proton login
    node lumo.js                                   # Start API server on :3333

Env:
    LUMO_HOST  — override host (default: localhost)
    LUMO_PORT  — override port (default: 3333)
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from urllib.error import URLError
from urllib.request import Request, urlopen

LUMO_HOST = os.environ.get("LUMO_HOST", "localhost")
LUMO_PORT = int(os.environ.get("LUMO_PORT", "3333"))
LUMO_URL = f"http://{LUMO_HOST}:{LUMO_PORT}"

DEFAULT_TIMEOUT = 90  # Lumo can be slow on first call; DOM polling takes ~10s


# ── Sensitivity classifier ─────────────────────────────────────────────────────
# Strip patterns that should never leave the local mesh even to Lumo

_SENSITIVE_PATTERNS = [
    re.compile(r'(?i)(api[_-]?key|apikey)\s*[:=]\s*\S+'),
    re.compile(r'(?i)(password|passwd|secret)\s*[:=]\s*\S+'),
    re.compile(r'(?i)bearer\s+[A-Za-z0-9\-._~+/]+=*'),
    re.compile(r'-----BEGIN [A-Z ]+-----'),
    re.compile(r'\b\d{3}-\d{2}-\d{4}\b'),                    # SSN
    re.compile(r'\b4[0-9]{12}(?:[0-9]{3})?\b'),              # Visa
    re.compile(r'\b5[1-5][0-9]{14}\b'),                      # MC
]


def _sanitize(text: str) -> str:
    """Strip known sensitive patterns before sending to Lumo."""
    for pat in _SENSITIVE_PATTERNS:
        text = pat.sub("[REDACTED]", text)
    return text


# ── HTTP client ────────────────────────────────────────────────────────────────

def _post_lumo(prompt: str, web_search: bool = False, timeout: int = DEFAULT_TIMEOUT) -> str:
    """POST to Lumo API server. Returns plain-text response."""
    payload = json.dumps({
        "prompt": prompt,
        "webSearch": web_search,
    }).encode("utf-8")

    req = Request(
        LUMO_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8")


def _is_online(timeout: int = 3) -> bool:
    """Quick TCP check — doesn't POST, just checks port."""
    import socket
    try:
        s = socket.create_connection((LUMO_HOST, LUMO_PORT), timeout=timeout)
        s.close()
        return True
    except OSError:
        return False


# ── Actions ───────────────────────────────────────────────────────────────────

def action_status() -> dict:
    """Check if Lumo API server is reachable."""
    online = _is_online()
    lumo_api_dir = os.path.expanduser("~/Code/lumo-api")
    auth_exists = os.path.exists(os.path.join(lumo_api_dir, "auth.json"))
    node_exists = os.path.exists(lumo_api_dir)

    return {
        "online": online,
        "url": LUMO_URL,
        "auth_configured": auth_exists,
        "lumo_api_cloned": node_exists,
        "setup_needed": not auth_exists,
        "message": (
            "Lumo API is running and ready"
            if online else
            "Lumo API offline. Start with: cd ~/Code/lumo-api && node lumo.js"
        ),
        "setup_steps": (
            [] if auth_exists else [
                "cd ~/Code/lumo-api",
                "node generate_auth.js   # opens Proton login",
                "node lumo.js            # start the API server",
            ]
        ),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def action_ask(
    query: str,
    web_search: bool = False,
    ghost: bool = False,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict:
    """Send a query to Lumo and return the response."""
    if not _is_online():
        return {
            "status": "offline",
            "fallback": "Lumo API not running. Use local model or Kimi Claw for now.",
            "start_command": "cd ~/Code/lumo-api && node lumo.js",
        }

    clean_query = _sanitize(query)
    t0 = time.time()

    try:
        response = _post_lumo(clean_query, web_search=web_search, timeout=timeout)
        elapsed = round(time.time() - t0, 2)

        return {
            "status": "ok",
            "query": clean_query,
            "response": response.strip(),
            "web_search": web_search,
            "elapsed_s": elapsed,
            "model": "lumo-proton",
            "tier": "T5",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    except TimeoutError:
        return {
            "status": "timeout",
            "error": f"Lumo did not respond within {timeout}s. Try again — first query after idle is slowest.",
            "fallback": "Use cyber_threat_bot or Mac Ollama for immediate results.",
        }
    except URLError as e:
        return {
            "status": "offline",
            "error": str(e.reason),
            "fallback": "Lumo API not running. Use local model or Kimi Claw for now.",
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
        }


# Security brief templates
_BRIEF_TEMPLATES = {
    "standard": (
        "You are a cybersecurity analyst. Provide a structured security brief on: {topic}\n\n"
        "Include:\n"
        "1. Summary (2-3 sentences)\n"
        "2. Affected systems / scope\n"
        "3. Attack vector and exploitability\n"
        "4. Mitigation steps\n"
        "5. Current exploitation status\n\n"
        "Be concise and actionable. Prioritize defenders."
    ),
    "deep": (
        "You are a senior threat intelligence analyst. Provide a deep technical brief on: {topic}\n\n"
        "Include:\n"
        "1. Executive summary\n"
        "2. Technical breakdown (attack chain, root cause)\n"
        "3. Affected versions and patch status\n"
        "4. IOCs / detection signatures if available\n"
        "5. MITRE ATT&CK mappings\n"
        "6. Exploitation in the wild (threat actors, campaigns)\n"
        "7. Recommended immediate actions\n"
        "8. References (CVE, CISA KEV, NVD)\n\n"
        "Be precise. Use technical terminology. This brief is for a SOC analyst."
    ),
}


def action_security_brief(
    topic: str,
    depth: str = "standard",
    web_search: bool = True,
) -> dict:
    """Generate a security brief on a CVE, threat actor, or vulnerability topic."""
    if not _is_online():
        return {
            "status": "offline",
            "fallback": "Lumo API not running. Use cyber_threat_bot for CVE data.",
            "start_command": "cd ~/Code/lumo-api && node lumo.js",
        }

    template = _BRIEF_TEMPLATES.get(depth, _BRIEF_TEMPLATES["standard"])
    prompt = template.format(topic=_sanitize(topic))

    t0 = time.time()
    try:
        response = _post_lumo(prompt, web_search=web_search, timeout=DEFAULT_TIMEOUT)
        elapsed = round(time.time() - t0, 2)

        return {
            "status": "ok",
            "topic": topic,
            "depth": depth,
            "brief": response.strip(),
            "web_search": web_search,
            "elapsed_s": elapsed,
            "model": "lumo-proton",
            "tier": "T5",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    except TimeoutError:
        return {
            "status": "timeout",
            "error": "Lumo timed out. Deep briefs take up to 90s on cold start.",
            "fallback": "Run cyber_threat_bot brief action instead.",
        }
    except URLError as e:
        return {"status": "offline", "error": str(e.reason)}
    except Exception as e:
        return {"status": "error", "error": str(e)}


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    raw = sys.stdin.read().strip()
    if not raw:
        inp: dict = {}
    else:
        try:
            inp = json.loads(raw)
        except json.JSONDecodeError as e:
            print(json.dumps({"error": f"Invalid JSON: {e}"}))
            return

    action = inp.get("action", "status")

    if action == "status":
        print(json.dumps(action_status(), indent=2))

    elif action == "ask":
        result = action_ask(
            query=inp.get("query", inp.get("prompt", "")),
            web_search=bool(inp.get("web_search", inp.get("webSearch", False))),
            ghost=bool(inp.get("ghost", False)),
            timeout=int(inp.get("timeout", DEFAULT_TIMEOUT)),
        )
        print(json.dumps(result, indent=2))

    elif action == "security_brief":
        result = action_security_brief(
            topic=inp.get("topic", inp.get("query", "")),
            depth=inp.get("depth", "standard"),
            web_search=bool(inp.get("web_search", True)),
        )
        print(json.dumps(result, indent=2))

    else:
        print(json.dumps({
            "error": f"Unknown action: {action}",
            "valid_actions": ["ask", "security_brief", "status"],
        }))


if __name__ == "__main__":
    main()
