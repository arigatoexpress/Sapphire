"""Microservices infrastructure for distributed Sapphire architecture."""

from .events import (
    ServiceEvent,
    ServiceEventType,
    ServiceEventPublisher,
    ServiceStateAggregator,
)
from .identity import ServiceIdentity, get_service_identity

__all__ = [
    "ServiceEvent",
    "ServiceEventType",
    "ServiceEventPublisher",
    "ServiceStateAggregator",
    "ServiceIdentity",
    "get_service_identity",
]
