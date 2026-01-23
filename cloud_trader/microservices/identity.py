"""Service identity management for microservices architecture.

Each Cloud Run service needs to know:
- Who am I? (Hyperliquid, Lighter, Drift, etc.)
- What should I do? (Only my designated platform)
- What should I NOT do? (Other platforms)
"""

import logging
import os
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from typing import Optional

logger = logging.getLogger(__name__)


class ServiceType(str, Enum):
    """Types of services in the Sapphire microservices mesh."""

    HYPERLIQUID = "hyperliquid"
    LIGHTER = "lighter"
    DRIFT = "drift"
    ASTER = "aster"
    SYMPHONY = "symphony"
    WEB = "web"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ServiceIdentity:
    """Identity and scope information for a service instance."""

    service_type: ServiceType
    service_name: str
    instance_id: str
    region: str
    emoji: str
    is_trading_service: bool
    is_web_service: bool
    is_orchestrator: bool

    def should_trade_on_platform(self, platform: str) -> bool:
        """Check if this service should trade on the given platform."""
        if not self.is_trading_service:
            return False

        platform_lower = platform.lower()
        service_type_str = self.service_type.value

        # Exact match
        if platform_lower == service_type_str:
            return True

        # Handle aliases
        if service_type_str == "hyperliquid" and platform_lower in ["hl", "hyperliquid"]:
            return True
        if service_type_str == "lighter" and platform_lower in ["lighter", "lighter.xyz"]:
            return True
        if service_type_str == "drift" and platform_lower in ["drift", "drift protocol"]:
            return True
        if service_type_str == "aster" and platform_lower in ["aster", "asterdex"]:
            return True

        return False

    def __str__(self) -> str:
        return f"{self.emoji} {self.service_name} ({self.service_type.value})"


def _detect_service_type_from_env() -> ServiceType:
    """Detect service type from environment variables.

    Cloud Run deployment sets these flags per service:
    - sapphire-hl: ENABLE_HYPERLIQUID=true, all others false
    - sapphire-lighter: ENABLE_LIGHTER=true, all others false
    - sapphire-drift: ENABLE_DRIFT=true, all others false
    - sapphire-aster: ENABLE_ASTER=true, all others false
    - sapphire-symphony: ENABLE_SYMPHONY=true, all others false
    - sapphire-web: SERVE_FRONTEND=true, all others false
    """
    # Check enable flags
    if os.getenv("ENABLE_HYPERLIQUID", "false").lower() == "true":
        return ServiceType.HYPERLIQUID
    if os.getenv("ENABLE_LIGHTER", "false").lower() == "true":
        return ServiceType.LIGHTER
    if os.getenv("ENABLE_DRIFT", "false").lower() == "true":
        return ServiceType.DRIFT
    if os.getenv("ENABLE_ASTER", "false").lower() == "true":
        return ServiceType.ASTER
    if os.getenv("ENABLE_SYMPHONY", "false").lower() == "true":
        return ServiceType.SYMPHONY
    if os.getenv("SERVE_FRONTEND", "false").lower() == "true":
        return ServiceType.WEB

    # Fallback: check K_SERVICE env var (Cloud Run service name)
    k_service = os.getenv("K_SERVICE", "").lower()
    if "hl" in k_service or "hyperliquid" in k_service:
        return ServiceType.HYPERLIQUID
    if "lighter" in k_service:
        return ServiceType.LIGHTER
    if "drift" in k_service:
        return ServiceType.DRIFT
    if "aster" in k_service:
        return ServiceType.ASTER
    if "symphony" in k_service:
        return ServiceType.SYMPHONY
    if "web" in k_service:
        return ServiceType.WEB

    logger.warning("⚠️ Unable to detect service type from environment")
    return ServiceType.UNKNOWN


def _get_emoji_for_service(service_type: ServiceType) -> str:
    """Get emoji representation for a service type."""
    emoji_map = {
        ServiceType.HYPERLIQUID: "💧",
        ServiceType.LIGHTER: "⚡",
        ServiceType.DRIFT: "🌀",
        ServiceType.ASTER: "⭐",
        ServiceType.SYMPHONY: "🎻",
        ServiceType.WEB: "🌐",
        ServiceType.UNKNOWN: "❓",
    }
    return emoji_map.get(service_type, "🤖")


@lru_cache(maxsize=1)
def get_service_identity() -> ServiceIdentity:
    """Get the identity of the current service instance.

    This is cached because identity doesn't change during runtime.
    """
    service_type = _detect_service_type_from_env()

    # Get Cloud Run metadata
    k_service = os.getenv("K_SERVICE", f"sapphire-{service_type.value}")
    k_revision = os.getenv("K_REVISION", "local")
    k_configuration = os.getenv("K_CONFIGURATION", k_service)

    # Cloud Run instance ID
    instance_id = os.getenv("HOSTNAME", f"{k_service}-{k_revision}")

    # Region
    region = os.getenv("CLOUD_RUN_REGION", "europe-west1")

    # Service characteristics
    is_trading_service = service_type in [
        ServiceType.HYPERLIQUID,
        ServiceType.LIGHTER,
        ServiceType.DRIFT,
        ServiceType.ASTER,
    ]
    is_web_service = service_type == ServiceType.WEB
    is_orchestrator = service_type == ServiceType.SYMPHONY

    identity = ServiceIdentity(
        service_type=service_type,
        service_name=k_service,
        instance_id=instance_id,
        region=region,
        emoji=_get_emoji_for_service(service_type),
        is_trading_service=is_trading_service,
        is_web_service=is_web_service,
        is_orchestrator=is_orchestrator,
    )

    logger.info(f"🆔 Service Identity: {identity}")
    return identity


def validate_service_scope(platform: str) -> None:
    """Validate that the current service should operate on the given platform.

    Raises:
        RuntimeError: If the service is attempting to operate outside its scope.
    """
    identity = get_service_identity()

    if identity.is_web_service:
        raise RuntimeError(
            f"{identity} is a web service and should not perform trading operations"
        )

    if identity.is_trading_service and not identity.should_trade_on_platform(platform):
        raise RuntimeError(
            f"{identity} should not trade on platform '{platform}'. "
            f"This service is scoped to {identity.service_type.value} only."
        )
