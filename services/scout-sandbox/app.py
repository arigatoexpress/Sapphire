"""
Scout Sandbox — sandboxed web-intel and GTM dispatch broker.

Provides:
  - GTM outbound dispatch (guarded by env toggle + token)
  - Scrapling-based web intelligence collection (guarded by env toggle)
  - CSS selector sanitization
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class SandboxConfig:
    gtm_enabled: bool = False
    gtm_require_token: bool = True
    gtm_api_token: str = ""
    scrapling_enabled: bool = False

    @classmethod
    def from_env(cls) -> SandboxConfig:
        return cls(
            gtm_enabled=os.getenv("SCOUT_SANDBOX_GTM_ENABLED", "false").lower() in ("true", "1", "yes"),
            gtm_require_token=os.getenv("SCOUT_SANDBOX_GTM_REQUIRE_TOKEN", "true").lower() in ("true", "1", "yes"),
            gtm_api_token=os.getenv("SCOUT_SANDBOX_GTM_API_TOKEN", ""),
            scrapling_enabled=os.getenv("SCOUT_SANDBOX_SCRAPLING_ENABLED", "false").lower() in ("true", "1", "yes"),
        )


# ---------------------------------------------------------------------------
# Dispatch request model
# ---------------------------------------------------------------------------

@dataclass
class DispatchRequest:
    action: str
    outbound_payload: dict[str, Any] = field(default_factory=dict)
    external_url_hint: str = ""
    source: str = ""


# ---------------------------------------------------------------------------
# Broker
# ---------------------------------------------------------------------------

_SAFE_SELECTOR_RE = re.compile(r"^[a-zA-Z0-9\s\.\#\-\_\>\+\~\:\[\]\=\*\(\)\,\"\']+$")


class ScoutSandboxBroker:
    """Sandboxed broker for GTM dispatch and web-intel collection."""

    def __init__(self, config: SandboxConfig):
        self.config = config

    # -- GTM dispatch -------------------------------------------------------

    async def dispatch(self, request: DispatchRequest) -> dict[str, Any]:
        if not self.config.gtm_enabled:
            return {"dispatched": False, "reason": "gtm_dispatch_disabled"}

        if self.config.gtm_require_token and not self.config.gtm_api_token:
            return {"dispatched": False, "reason": "gtm_api_token_missing"}

        # In production this would POST to external_url_hint
        return {
            "dispatched": True,
            "action": request.action,
            "source": request.source,
        }

    # -- Scrapling web-intel ------------------------------------------------

    async def collect_scrapling_intel(
        self,
        source_url: str,
        selectors: list[str],
        limit_per_selector: int = 5,
        include_links: bool = False,
        max_links: int = 10,
        query: str = "",
    ) -> dict[str, Any]:
        if not self.config.scrapling_enabled:
            return {"ok": False, "reason": "scrapling_disabled"}

        # In production this would actually scrape the URL
        return {
            "ok": True,
            "source_url": source_url,
            "selectors": selectors,
            "results": [],
        }

    # -- CSS selector sanitizer ---------------------------------------------

    @staticmethod
    def _sanitize_css_selectors(selectors: list[str], max_count: int = 10) -> list[str]:
        """Filter CSS selectors to only safe values, deduplicate, and cap count."""
        seen: set[str] = set()
        result: list[str] = []
        for sel in selectors:
            sel = sel.strip()
            if not sel or sel in seen:
                continue
            if not _SAFE_SELECTOR_RE.match(sel):
                continue
            seen.add(sel)
            result.append(sel)
            if len(result) >= max_count:
                break
        return result
