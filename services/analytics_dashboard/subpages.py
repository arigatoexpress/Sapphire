"""Sapphire OS sub-pages — per-project deep-dive routes.

Each tab in the home shell points to one of these sub-routes. Style:
cypherpunk-terminal — JetBrains Mono, near-black bg, hard-green accent,
ASCII-box framing. Exception: ``/p/tho`` keeps the THO retail brand.

Wired into the parent Flask app via :func:`register_subpages`. All
routes are read-only and public; no auth.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime

from flask import render_template
from og_guard import build_0guard_progress
from og_proof import build_og_proof_manifest

log = logging.getLogger("sapphire.subpages")

THO_HEALTH_URL = os.environ.get("THO_HEALTH_URL", "https://tho.sapphirealpha.xyz/healthz/")
THO_PUBLIC_URL = os.environ.get("THO_PUBLIC_URL", "https://tho.sapphirealpha.xyz/")
WILDFIRE_PUBLIC_URL = "/p/wildfire"
WILDFIRE_HEALTH_URL = os.environ.get(
    "WILDFIRE_HEALTH_URL", "https://wildfire.sapphirealpha.xyz/api/sensors/health"
)
REGIONAL_URL = os.environ.get("REGIONAL_URL", "https://regional.sapphirealpha.xyz/")
HACK_URL = os.environ.get("HACK_URL", "https://hack.sapphirealpha.xyz/")


def _http_get_json(url: str, timeout: float = 2.5) -> dict | None:
    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            return None
        req = urllib.request.Request(url, headers={"User-Agent": "sapphire-subpages/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310
            if resp.status != 200:
                return None
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, OSError):
        return None


# ---------------------------------------------------------------------------
# Hard-coded reference data sourced from session memory.
# Lives here (not in BQ) because these are static project descriptors.
# ---------------------------------------------------------------------------

HACKATHON_SUBMISSIONS = [
    {
        "name": "0G APAC",
        "tagline": "Decentralized AI inference + storage for autonomous agents.",
        "status": "submitted",
        "status_label": "SUBMITTED",
        "pr": "https://github.com/arigatoexpress/Sapphire/pull/525",
        "branch": "feat/0g-integration",
        "contract": None,
        "explorer": None,
        "demo": "https://sapphirealpha.xyz/p/about",
        "judging": "AI x Web3 :: agentic data ops, 83 tests, full DA stack.",
        "tests": "83 passing",
    },
    {
        "name": "MegaETH",
        "tagline": "Real-time micro-block trading: sub-10ms execution on chain-4326.",
        "status": "active",
        "status_label": "BUILDING",
        "pr": "https://github.com/arigatoexpress/Sapphire/pulls?q=is%3Apr+megaeth",
        "branch": "feat/megaeth-wave-b3-gmx-v2",
        "contract": None,
        "explorer": "https://www.megaexplorer.xyz/",
        "demo": "https://sapphirealpha.xyz/p/markets",
        "judging": "DeFi infra :: Wave B.5 read-only protocols + Wave B.3 GMX v2.",
        "tests": "Wave B.3 + B.5 in flight",
    },
    {
        "name": "Robinhood London",
        "tagline": "Live $5 BTC fills + Arbitrum Orbit chain (46630) integration.",
        "status": "live",
        "status_label": "LIVE",
        "pr": "https://github.com/arigatoexpress/Sapphire/pull/344",
        "branch": "main",
        "contract": "Arbitrum Orbit chain ID 46630",
        "explorer": "https://robinhood.com/",
        "demo": "https://sapphirealpha.xyz/p/system",
        "judging": "First $5 BTC fill 2026-04-28 04:06 UTC at $76,774.81. 14d Sortino soak.",
        "tests": "Manual confirmation token gate, $5 cap, $50 pilot, crypto-only.",
    },
    {
        "name": "Zama",
        "tagline": "FHE signal verification + on-chain Sapphire signal registry.",
        "status": "scoping",
        "status_label": "SCOPING",
        "pr": "https://github.com/arigatoexpress/Sapphire/pulls?q=is%3Apr+zama",
        "branch": "main",
        "contract": "SapphireSignalVerifier.sol (testnet)",
        "explorer": "https://docs.zama.ai/",
        "demo": "https://sapphirealpha.xyz/p/threats",
        "judging": "ZK signal hashes + FHE-friendly compute graph.",
        "tests": "ZK proof hash field live; FHE wiring scoped.",
    },
]

REGIONS = [
    {"slug": "austin", "name": "Austin", "category": "primary", "note": "TX • home base"},
    {"slug": "blanga", "name": "Blanga", "category": "operational", "note": "TX • THO ops"},
    {"slug": "houston", "name": "Houston", "category": "watch", "note": "TX • secondary"},
    {"slug": "sf-bay", "name": "SF Bay", "category": "watch", "note": "CA • intel hub"},
    {"slug": "nyc", "name": "NYC", "category": "watch", "note": "NY • markets"},
    {"slug": "global", "name": "Global", "category": "macro", "note": "rollup feed"},
]


def register_subpages(app, *, project: str, dataset: str) -> None:
    """Attach 10 sub-page routes to ``app``."""

    def _ctx(extra: dict | None = None) -> dict:
        base = {"project": project, "dataset": dataset, "now": datetime.now(UTC).isoformat()}
        if extra:
            base.update(extra)
        return base

    @app.get("/p/hackathon")
    def _p_hackathon():
        # Try live feed; fall back to baked-in. Either way the template
        # renders the cards and never breaks the page.
        live = _http_get_json(HACK_URL.rstrip("/") + "/api/submissions", timeout=2.0)
        live_subs = (live or {}).get("submissions") if isinstance(live, dict) else None
        subs = live_subs if isinstance(live_subs, list) and live_subs else HACKATHON_SUBMISSIONS
        return render_template(
            "p/hackathon.html",
            **_ctx(
                {
                    "submissions": subs,
                    "fallback": not bool(live_subs),
                    "og_proof": build_og_proof_manifest(),
                }
            ),
        )

    @app.get("/p/0guard")
    def _p_0guard():
        return render_template("p/0guard.html", **_ctx({"oguard": build_0guard_progress()}))

    @app.get("/p/wildfire")
    def _p_wildfire():
        health = _http_get_json(WILDFIRE_HEALTH_URL, timeout=2.0) or {}
        return render_template(
            "p/wildfire.html",
            **_ctx(
                {
                    "wildfire_url": WILDFIRE_PUBLIC_URL,
                    "health": health,
                    "online": bool(health and health.get("ok") is not False),
                }
            ),
        )

    @app.get("/p/threats")
    def _p_threats():
        # The template fetches /api/threats/live + /api/timeseries/threats
        # client-side from same-origin proxies wired in app.py.
        return render_template("p/threats.html", **_ctx())

    @app.get("/p/tho")
    def _p_tho():
        # Keeps THO retail brand — separate template, no cypherpunk shell.
        health = _http_get_json(THO_HEALTH_URL, timeout=2.0) or {}
        return render_template(
            "p/tho.html",
            project=project,
            dataset=dataset,
            tho_url=THO_PUBLIC_URL,
            health=health,
            tho_online=bool(
                health and (health.get("ok") is True or health.get("status") in ("ok", "ready"))
            ),
        )

    @app.get("/p/regional")
    def _p_regional():
        live = _http_get_json(REGIONAL_URL.rstrip("/") + "/api/health", timeout=2.0) or {}
        return render_template(
            "p/regional.html",
            **_ctx(
                {
                    "regional_url": REGIONAL_URL,
                    "regions": REGIONS,
                    "regional_online": bool(
                        live and (live.get("ok") is True or live.get("status") in ("ok", "ready"))
                    ),
                }
            ),
        )

    @app.get("/p/brain")
    def _p_brain():
        return render_template("p/brain.html", **_ctx())

    @app.get("/p/markets")
    def _p_markets():
        return render_template("p/markets.html", **_ctx())

    @app.get("/p/system")
    def _p_system():
        return render_template("p/system.html", **_ctx())

    @app.get("/p/about")
    def _p_about():
        return render_template("p/about.html", **_ctx())

    @app.get("/p/help")
    def _p_help():
        return render_template("p/help.html", **_ctx())
