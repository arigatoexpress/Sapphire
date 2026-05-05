"""Public project-tab manifest for sapphirealpha.xyz.

This is deliberately static and paste-safe: no secret-bearing URLs, localhost
links, or internal-only admin actions. The same model powers the home page,
public API, and help/resource pages so Sapphire's public surface does not drift.
"""

from __future__ import annotations

from copy import deepcopy

PROJECT_TABS: list[dict] = [
    {
        "slug": "brain",
        "label": "Brain",
        "kind": "core",
        "status": "live",
        "accent": "green",
        "tagline": "Cross-silo synthesis for Sapphire OS.",
        "summary": "Health, priority actions, and correlation across THO, markets, threats, inference, regional intelligence, and infrastructure.",
        "info_route": "/p/brain",
        "primary_cta": {"label": "Open Brain", "href": "/p/brain", "external": False},
        "resources": [
            {"label": "Synthesis API", "href": "/api/brain/synthesis"},
            {"label": "History API", "href": "/api/brain/history"},
            {"label": "Correlation API", "href": "/api/brain/correlate"},
        ],
        "proof_points": ["BigQuery-backed", "15-minute synthesis", "read-only public view"],
        "safety_note": "Public navigation only; persistence actions remain explicit controls on the detail page.",
        "status_id": None,
    },
    {
        "slug": "markets",
        "label": "Markets",
        "kind": "core",
        "status": "live",
        "accent": "blue",
        "tagline": "Crypto market regime, predictions, and intelligence.",
        "summary": "Live market snapshot, regime context, model predictions, and risk-aware signals for Sapphire's trading research layer.",
        "info_route": "/p/markets",
        "primary_cta": {"label": "Open Markets", "href": "/p/markets", "external": False},
        "resources": [
            {"label": "Market Snapshot", "href": "/api/markets/snapshot"},
            {"label": "Recent Signals", "href": "/api/signals/recent"},
            {"label": "Predictions", "href": "/api/predictions"},
        ],
        "proof_points": ["Read-only public feed", "Regime-aware", "Paper/live boundaries labeled"],
        "safety_note": "No trade execution controls are exposed on the public landing page.",
        "status_id": "silo-intel-status",
    },
    {
        "slug": "tho",
        "label": "THO",
        "kind": "satellite",
        "status": "live",
        "accent": "cyan",
        "tagline": "Texas Home Outlet client operating system.",
        "summary": "Inventory, CRM, appointments, Ad Studio, analytics, and the production Document Center for compliant packet generation.",
        "info_route": "/p/tho",
        "primary_cta": {
            "label": "Open THO Frontend",
            "href": "https://tho.sapphirealpha.xyz/",
            "external": True,
        },
        "resources": [
            {"label": "Health", "href": "https://tho.sapphirealpha.xyz/healthz/"},
            {"label": "Document Center", "href": "https://tho.sapphirealpha.xyz/documents"},
            {"label": "System Hub", "href": "https://tho.sapphirealpha.xyz/system"},
        ],
        "proof_points": ["Cloud Run production", "Firestore passkeys", "63 templates / 5 packets"],
        "safety_note": "Admin workflows require PIN or passkey authentication.",
        "status_id": "silo-tho-status",
        "link_id": "silo-tho-link",
    },
    {
        "slug": "threats",
        "label": "Threats",
        "kind": "satellite",
        "status": "live",
        "accent": "red",
        "tagline": "CISA, NVD, and MITRE threat intelligence.",
        "summary": "Defensive cyber intelligence feed with live vulnerabilities, exploitation context, and source-backed incident triage.",
        "info_route": "/p/threats",
        "primary_cta": {
            "label": "Open Threat Feed",
            "href": "https://cyber-threat-bot-691674245427.us-central1.run.app/threats?source=all",
            "external": True,
        },
        "resources": [
            {"label": "Live Threats", "href": "/api/threats/live"},
            {"label": "Threat Timeseries", "href": "/api/timeseries/threats"},
            {
                "label": "Source App",
                "href": "https://cyber-threat-bot-691674245427.us-central1.run.app/",
            },
        ],
        "proof_points": ["CISA KEV", "NVD CVEs", "MITRE ATT&CK context"],
        "safety_note": "Defensive research only; no offensive automation exposed.",
        "status_id": "silo-threat-status",
    },
    {
        "slug": "wildfire",
        "label": "Wildfire",
        "kind": "satellite",
        "status": "phase-0",
        "accent": "orange",
        "tagline": "Wildfire and ecology monitoring surface.",
        "summary": "A public-facing operational lane for autonomous wildfire monitoring, sensor health, and environmental intelligence.",
        "info_route": "/p/wildfire",
        "primary_cta": {
            "label": "Open Wildfire",
            "href": "https://wildfire.sapphirealpha.xyz/",
            "external": True,
        },
        "resources": [
            {"label": "Health", "href": "https://wildfire.sapphirealpha.xyz/healthz/"},
            {"label": "Detail Page", "href": "/p/wildfire"},
        ],
        "proof_points": ["Public dashboard", "Health-gated", "Phase-0 status labeled"],
        "safety_note": "Operational status is informational until field hardware is explicitly connected.",
        "status_id": None,
    },
    {
        "slug": "regional",
        "label": "Regional",
        "kind": "satellite",
        "status": "active",
        "accent": "purple",
        "tagline": "Regional opportunity and civic intelligence.",
        "summary": "Geographic watchlists, vote-monitor context, local signals, and regional business-development intelligence.",
        "info_route": "/p/regional",
        "primary_cta": {
            "label": "Open Regional",
            "href": "https://regional.sapphirealpha.xyz/",
            "external": True,
        },
        "resources": [
            {"label": "Health", "href": "https://regional.sapphirealpha.xyz/api/health"},
            {"label": "Intel View", "href": "https://regional.sapphirealpha.xyz/intel"},
            {"label": "Detail Page", "href": "/p/regional"},
        ],
        "proof_points": ["Austin-first", "Public-source intel", "Admin view protected"],
        "safety_note": "Public link avoids privileged admin-only routes by default.",
        "status_id": None,
    },
    {
        "slug": "hackathon",
        "label": "Hackathon",
        "kind": "satellite",
        "status": "active",
        "accent": "yellow",
        "tagline": "Sapphire demos, grants, and protocol lanes.",
        "summary": "0G, MegaETH, Robinhood Chain, Zama, Sentinel, and adjacent protocol demonstrations with honest readiness labels.",
        "info_route": "/p/hackathon",
        "primary_cta": {
            "label": "Open Hackathon",
            "href": "https://hack.sapphirealpha.xyz/",
            "external": True,
        },
        "resources": [
            {"label": "Submissions", "href": "https://hack.sapphirealpha.xyz/"},
            {"label": "Detail Page", "href": "/p/hackathon"},
            {"label": "System Page", "href": "/p/system"},
        ],
        "proof_points": ["0G", "MegaETH", "Robinhood Chain", "Sentinel"],
        "safety_note": "Demo, testnet, and paper-only lanes are labeled before external action.",
        "status_id": None,
    },
    {
        "slug": "system",
        "label": "System",
        "kind": "core",
        "status": "protected",
        "accent": "slate",
        "tagline": "Sapphire mesh and operations topology.",
        "summary": "Mac, Windows, Pi, Cloud Run, inference mesh, LaunchAgents, and readiness probes for the operating system itself.",
        "info_route": "/p/system",
        "primary_cta": {"label": "Open System", "href": "/p/system", "external": False},
        "resources": [
            {"label": "Health", "href": "/healthz"},
            {"label": "Silo Health", "href": "/api/silos/health"},
            {"label": "Service Timeseries", "href": "/api/timeseries/services"},
        ],
        "proof_points": ["Cloud Run", "Inference mesh", "LaunchAgent-backed local runtime"],
        "safety_note": "Public page shows status only; control surfaces remain authenticated elsewhere.",
        "status_id": None,
    },
]


def public_project_tabs() -> list[dict]:
    """Return a copy safe for templates and JSON responses."""
    return deepcopy(PROJECT_TABS)


def get_project_tab(slug: str) -> dict | None:
    """Find one public project tab by slug."""
    normalized = (slug or "").strip().lower()
    for tab in PROJECT_TABS:
        if tab["slug"] == normalized:
            return deepcopy(tab)
    return None
