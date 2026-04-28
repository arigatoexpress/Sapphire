"""Palantir Foundry helpers for Sapphire.

Modules:
  - readiness  — repo-grounded config/artifact inspection
  - client     — SDK wrapper with token + OAuth auth
  - sdk        — versioned, idempotent public write surface
  - ingestion  — transform local data → Foundry ontology objects
  - sync       — 15-min delta-aware scheduled sync with Telegram alerts
"""

from .readiness import build_foundry_readiness
from .sdk import (
    DEFAULT_SCHEMA_VERSION,
    SDK_VERSION,
    FoundrySDKIdempotencyError,
    FoundrySDKSchemaError,
    FoundryWriteEnvelope,
    IdempotencyLedger,
    SapphireFoundrySDK,
)

__all__ = [
    "DEFAULT_SCHEMA_VERSION",
    "SDK_VERSION",
    "FoundrySDKIdempotencyError",
    "FoundrySDKSchemaError",
    "FoundryWriteEnvelope",
    "IdempotencyLedger",
    "SapphireFoundrySDK",
    "build_foundry_readiness",
]
