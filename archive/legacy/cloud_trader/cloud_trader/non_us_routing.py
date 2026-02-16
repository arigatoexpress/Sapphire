"""
Non-US Routing Configuration for Geo-Blocked Exchanges

Critical: Aster and some other CEXs block US IP addresses.
Cloud Run services in us-central1 will be blocked.

Solution: Route API calls through non-US proxies/VPNs for blocked platforms.

Platforms requiring non-US routing:
- Aster (blocks US completely)
- Any other geo-restricted exchanges
"""

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


class NonUSRouter:
    """
    Routes API requests through non-US endpoints for geo-blocked exchanges.

    Options:
    1. Cloud Run in non-US regions (europe-west1, asia-east1)
    2. HTTP/HTTPS proxy services
    3. VPN tunneling
    4. CDN-based routing
    """

    def __init__(self):
        # Platforms that require non-US routing
        self.blocked_platforms = ["aster"]

        # Proxy configuration (can be set via environment variables)
        self.http_proxy = os.getenv("HTTP_PROXY")
        self.https_proxy = os.getenv("HTTPS_PROXY")

        # Non-US Cloud Run endpoints (if using multi-region deployment)
        self.non_us_endpoints = {
            "aster": os.getenv("ASTER_NON_US_ENDPOINT"),  # e.g., europe endpoint
        }

        if self.http_proxy or self.https_proxy:
            logger.info(
                f"🌍 [NON-US ROUTING] Proxy configured: "
                f"HTTP={bool(self.http_proxy)}, HTTPS={bool(self.https_proxy)}"
            )
        else:
            logger.warning(
                "⚠️ [NON-US ROUTING] No proxy configured - "
                "US-blocked platforms (Aster) may fail!"
            )

    def get_proxy_config(self, platform: str) -> Optional[dict]:
        """
        Get proxy configuration for a platform.

        Returns dict with 'http' and 'https' proxy URLs, or None.
        """
        platform_lower = platform.lower()

        if platform_lower not in self.blocked_platforms:
            return None  # No proxy needed

        if not (self.http_proxy or self.https_proxy):
            logger.error(
                f"❌ [NON-US ROUTING] {platform} requires proxy but none configured! "
                f"Set HTTP_PROXY/HTTPS_PROXY environment variables."
            )
            return None

        return {
            "http": self.http_proxy,
            "https": self.https_proxy,
        }

    def get_session_kwargs(self, platform: str) -> dict:
        """
        Get aiohttp session kwargs with proxy configuration.

        Usage:
            from .non_us_routing import get_non_us_router
            router = get_non_us_router()
            session_kwargs = router.get_session_kwargs("aster")
            async with aiohttp.ClientSession(**session_kwargs) as session:
                # Requests will route through proxy
        """
        proxy_config = self.get_proxy_config(platform)

        if not proxy_config:
            return {}

        # aiohttp proxy format
        return {
            "trust_env": True,  # Use environment proxy settings
        }

    def is_platform_blocked(self, platform: str) -> bool:
        """Check if platform requires non-US routing."""
        return platform.lower() in self.blocked_platforms


# Global instance
_router = None


def get_non_us_router() -> NonUSRouter:
    """Get the global non-US routing instance."""
    global _router
    if _router is None:
        _router = NonUSRouter()
    return _router


def configure_aiohttp_proxy(platform: str):
    """
    Configure aiohttp to use proxy for geo-blocked platforms.

    This is automatically called by platform clients that need it.
    """
    router = get_non_us_router()

    if router.is_platform_blocked(platform):
        proxy_config = router.get_proxy_config(platform)
        if proxy_config:
            logger.info(
                f"✅ [NON-US ROUTING] {platform} configured with proxy routing"
            )
            return proxy_config
        else:
            logger.error(
                f"❌ [NON-US ROUTING] {platform} BLOCKED - No proxy available! "
                f"Configure HTTP_PROXY environment variable."
            )
            return None

    return None


# Alternative: Cloud Run multi-region deployment
def get_non_us_cloud_run_endpoint(platform: str) -> Optional[str]:
    """
    Get non-US Cloud Run endpoint for a platform.

    If deploying to multiple regions, use this to route Aster traffic
    to a europe-west1 or asia-east1 endpoint.

    Example:
        ASTER_NON_US_ENDPOINT=https://sapphire-aster-eu-xyz.run.app
    """
    router = get_non_us_router()
    return router.non_us_endpoints.get(platform.lower())
