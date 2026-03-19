from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class SourcePolicy:
    source_key: str
    source_name: str
    mode: str
    allowed: bool
    rationale: str
    notes: str = ""


# mode values are intentional and user-facing.
SOURCE_POLICIES: List[SourcePolicy] = [
    SourcePolicy(
        source_key="google_sheets",
        source_name="Google Sheets",
        mode="operator_source_of_truth",
        allowed=True,
        rationale="Primary brokerage operating system per client feedback.",
    ),
    SourcePolicy(
        source_key="google_drive_manual_om_drop",
        source_name="Google Drive Manual OM Drop",
        mode="manual_upload",
        allowed=True,
        rationale="User manually drops OMs; no behind-login downloading by BIS.",
    ),
    SourcePolicy(
        source_key="coa_open_data",
        source_name="City of Austin Open Data",
        mode="public_api",
        allowed=True,
        rationale="Public municipal data source for permits/signals.",
    ),
    SourcePolicy(
        source_key="hays_county_public_permits",
        source_name="Hays County Public Permits Portal",
        mode="public_web_portal_public_api_endpoint",
        allowed=True,
        rationale="Public permits list and public DataTables endpoint available without login.",
    ),
    SourcePolicy(
        source_key="williamson_county_public_permits",
        source_name="Williamson County Public Permits Portal",
        mode="public_web_portal_public_api_endpoint",
        allowed=True,
        rationale="Public permits list and public DataTables endpoint available without login.",
    ),
    SourcePolicy(
        source_key="community_impact",
        source_name="Community Impact",
        mode="public_news_source",
        allowed=True,
        rationale="Client-preferred local source for vacancy/opening/new construction mentions.",
    ),
    SourcePolicy(
        source_key="austin_metro",
        source_name="Austin Metro",
        mode="public_news_source_pending_domain_confirmation",
        allowed=True,
        rationale="Client-preferred source; confirm exact publication URL/domain for stricter filters.",
    ),
    SourcePolicy(
        source_key="austin_american_statesman",
        source_name="Austin American-Statesman",
        mode="subscription_manual_reference",
        allowed=True,
        rationale="Useful source but paywalled; manual reference/notes only in beta.",
        notes="Do not rely on automated content retrieval behind subscription.",
    ),
    SourcePolicy(
        source_key="austin_business_journal",
        source_name="Austin Business Journal",
        mode="subscription_manual_reference",
        allowed=True,
        rationale="Useful source but paywalled; manual reference/notes only in beta.",
        notes="Do not rely on automated content retrieval behind subscription.",
    ),
    SourcePolicy(
        source_key="costar_export",
        source_name="CoStar Export",
        mode="licensed_export_manual_import",
        allowed=True,
        rationale="Allowed only via user-provided export under license terms.",
        notes="No automated scraping or credentialed crawling.",
    ),
    SourcePolicy(
        source_key="crexi_export",
        source_name="Crexi Export / Manual Entry",
        mode="manual_import",
        allowed=True,
        rationale="Use manual inputs or permitted exports only.",
    ),
    SourcePolicy(
        source_key="loopnet_manual",
        source_name="LoopNet Manual Observation",
        mode="manual_observation",
        allowed=True,
        rationale="Broker-observed listing facts can be entered manually with source attribution.",
    ),
    SourcePolicy(
        source_key="mls",
        source_name="MLS",
        mode="out_of_scope",
        allowed=False,
        rationale="Client feedback indicates MLS is not applicable for target workflow.",
    ),
    SourcePolicy(
        source_key="credentialed_scraping",
        source_name="Credentialed Scraping / Behind Login Crawling",
        mode="prohibited",
        allowed=False,
        rationale="Explicit compliance risk and client requested no-go.",
    ),
]


def policies_as_dicts() -> List[Dict[str, object]]:
    return [
        {
            "source_key": p.source_key,
            "source_name": p.source_name,
            "mode": p.mode,
            "allowed": p.allowed,
            "rationale": p.rationale,
            "notes": p.notes,
        }
        for p in SOURCE_POLICIES
    ]


def get_policy(source_key: str) -> SourcePolicy | None:
    normalized = (source_key or "").strip().lower()
    for policy in SOURCE_POLICIES:
        if policy.source_key == normalized:
            return policy
    return None
