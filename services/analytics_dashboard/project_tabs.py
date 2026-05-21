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
        "summary": "Public health posture and cross-silo synthesis across markets, threats, inference, regional intelligence, product labs, and infrastructure.",
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
            {"label": "Signals + Forecasts Admin", "href": "/admin"},
        ],
        "proof_points": ["Read-only public feed", "Regime-aware", "Paper/live boundaries labeled"],
        "safety_note": "No trade execution controls are exposed on the public landing page.",
        "status_id": "silo-intel-status",
    },
    {
        "slug": "agent-exchange",
        "label": "Agent Exchange",
        "kind": "product",
        "status": "buyer-ready",
        "accent": "purple",
        "featured": True,
        "tagline": "Rights-cleared x402 intelligence artifacts.",
        "summary": "Agent Opportunity Exchange turns public-source market, cyber, opportunity, and API-change evidence into buyer-discoverable contracts with simulated or testnet-only payment rails.",
        "info_route": "https://aoe-hackathon-preview-s77j6bxyra-uc.a.run.app/",
        "primary_cta": {
            "label": "Open Exchange",
            "href": "https://aoe-hackathon-preview-s77j6bxyra-uc.a.run.app/",
            "external": True,
        },
        "resources": [
            {
                "label": "Buyer Proof",
                "href": "https://aoe-hackathon-preview-s77j6bxyra-uc.a.run.app/v1/buyer-proof",
            },
            {
                "label": "Contracts",
                "href": "https://aoe-hackathon-preview-s77j6bxyra-uc.a.run.app/v1/contracts",
            },
            {
                "label": "x402 Status",
                "href": "https://aoe-hackathon-preview-s77j6bxyra-uc.a.run.app/v1/x402/status",
            },
        ],
        "proof_points": ["9 product contracts", "33 live read-only routes", "no live settlement"],
        "safety_note": "Payment is access control, not source permission; no scans, sends, trades, filings, wallet signing, or mainnet settlement.",
        "status_id": None,
    },
    {
        "slug": "delivery-markets",
        "label": "Delivery Markets",
        "kind": "product",
        "status": "paper-demo",
        "accent": "orange",
        "featured": True,
        "tagline": "Recipient-only delivery-time event-contract simulator.",
        "summary": "A meeting-ready paper market demo for delivery-time uncertainty: synthetic tracking numbers, hub cutoff gates, recipient-only access, and testnet calldata preview.",
        "info_route": "https://delivery-markets.sapphirealpha.xyz/",
        "primary_cta": {
            "label": "Open Demo",
            "href": "https://delivery-markets.sapphirealpha.xyz/",
            "external": True,
        },
        "resources": [
            {"label": "Health", "href": "https://delivery-markets.sapphirealpha.xyz/health"},
            {
                "label": "Demo Numbers",
                "href": "https://delivery-markets.sapphirealpha.xyz/api/demo-tracking-numbers",
            },
        ],
        "proof_points": ["paper orders only", "synthetic shipments", "testnet preview"],
        "safety_note": "No real FedEx API calls, customer tracking data, live venue orders, wallet signing, funds, settlement, or wagering.",
        "status_id": None,
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
        "frontdoor": False,
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
        "featured": True,
        "tagline": "CISA, NVD, and MITRE threat intelligence.",
        "summary": "Defensive cyber intelligence feed with live vulnerabilities, EPSS/CISA/NVD context, and source-backed case-brief lanes.",
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
        "featured": True,
        "tagline": "Regional and field-ops intelligence.",
        "summary": "Public-source regional intelligence, client feeds, OODA packets, source health, and the new field-ops/UAS readiness lane.",
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
        "proof_points": ["Field-ops follow-through", "Public-source intel", "OODA read-only"],
        "safety_note": "Public link avoids privileged admin-only routes by default.",
        "status_id": None,
    },
    {
        "slug": "0guard",
        "label": "0guard",
        "kind": "satellite",
        "status": "review-ready",
        "accent": "green",
        "featured": True,
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
        "status": "sunset",
        "accent": "yellow",
        "tagline": "Archived aggregate for older protocol demos.",
        "summary": "Older protocol submissions remain available as a reference shelf. Current public product routes now live under 0guard, Agent Exchange, Delivery Markets, Regional, Threats, Markets, and System.",
        "info_route": "/p/hackathon",
        "primary_cta": {
            "label": "Open Archive",
            "href": "https://hack.sapphirealpha.xyz/",
            "external": True,
        },
        "resources": [
            {"label": "Submissions", "href": "https://hack.sapphirealpha.xyz/"},
            {"label": "Detail Page", "href": "/p/hackathon"},
            {"label": "System Page", "href": "/p/system"},
        ],
        "proof_points": ["legacy aggregate", "split into products", "honest labels"],
        "safety_note": "Deprecated as the primary story; use current product tabs for active demos and proof surfaces.",
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
            {"label": "Health", "href": "/health"},
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
    return deepcopy([tab for tab in PROJECT_TABS if tab.get("frontdoor", True)])


def get_project_tab(slug: str) -> dict | None:
    """Find one public project tab by slug."""
    normalized = (slug or "").strip().lower()
    for tab in PROJECT_TABS:
        if tab["slug"] == normalized:
            return deepcopy(tab)
    return None
