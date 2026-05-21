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
        "summary": "Public health posture and cross-silo synthesis across THO, markets, threats, inference, regional intelligence, and infrastructure.",
        "info_route": "/p/brain",
        "primary_cta": {"label": "Open Brain", "href": "/p/brain", "external": False},
        "resources": [
            {"label": "Public Synthesis API", "href": "/api/brain/synthesis"},
            {"label": "Admin History", "href": "/admin"},
            {"label": "Admin Correlations", "href": "/admin"},
        ],
        "proof_points": ["BigQuery-backed", "15-minute synthesis", "read-only public view"],
        "safety_note": "Public navigation only; persistence, history, correlations, and actions require admin.",
        "status_id": None,
    },
    {
        "slug": "markets",
        "label": "Markets",
        "kind": "core",
        "status": "live",
        "accent": "blue",
        "tagline": "Crypto market regime and public intelligence.",
        "summary": "Live market snapshot and regime context for Sapphire's trading research layer, with signals and forecasts kept behind admin.",
        "info_route": "/p/markets",
        "primary_cta": {"label": "Open Markets", "href": "/p/markets", "external": False},
        "resources": [
            {"label": "Market Snapshot", "href": "/api/markets/snapshot"},
            {"label": "Regime API", "href": "/api/regime"},
            {"label": "Signals + Predictions Admin", "href": "/admin"},
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
            "href": "/p/threats",
            "external": False,
        },
        "resources": [
            {"label": "Live Threats", "href": "/api/threats/live"},
            {"label": "Threat Timeseries", "href": "/api/timeseries/threats"},
            {"label": "Admin Source Detail", "href": "/admin"},
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
            "label": "Open Wildfire Summary",
            "href": "/p/wildfire",
            "external": False,
        },
        "resources": [
            {"label": "Health", "href": "https://wildfire.sapphirealpha.xyz/healthz/"},
            {"label": "Detail Page", "href": "/p/wildfire"},
        ],
        "proof_points": ["Public-safe summary", "Health-gated", "Phase-0 status labeled"],
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
        "slug": "0guard",
        "label": "0guard",
        "kind": "satellite",
        "status": "review-ready",
        "accent": "green",
        "tagline": "0G-native agentic transaction defense.",
        "summary": "Live public progress surface for the 0guard wallet and protocol-risk system: source-linked incident data, detector coverage, 0G mainnet proof posture, and read-only Telegram/Mira readiness.",
        "info_route": "/p/0guard",
        "primary_cta": {
            "label": "Open 0guard",
            "href": "/p/0guard",
            "external": False,
        },
        "resources": [
            {"label": "Progress API", "href": "/api/0guard/progress"},
            {
                "label": "Live Service Health",
                "href": "https://guard0-miniapp-s77j6bxyra-uc.a.run.app/api/readyz",
            },
            {
                "label": "Detector Coverage",
                "href": "https://guard0-miniapp-s77j6bxyra-uc.a.run.app/api/data/detection-coverage",
            },
        ],
        "proof_points": ["0G mainnet", "28/28 detector coverage", "Telegram mini-app preview"],
        "safety_note": "Public surface is read-only: no signing, swapping, bridging, posting, Telegram sends, or private-key access.",
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
        "summary": "Cloud, local, and failover readiness probes for the operating system itself, with raw topology behind admin.",
        "info_route": "/p/system",
        "primary_cta": {"label": "Open System", "href": "/p/system", "external": False},
        "resources": [
            {"label": "Health", "href": "/healthz"},
            {"label": "Silo Health", "href": "/api/silos/health"},
            {"label": "Admin Service Timeseries", "href": "/admin"},
        ],
        "proof_points": ["Cloud Run", "Inference mesh", "Admin-gated topology"],
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
