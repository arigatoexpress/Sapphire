"""Palantir Foundry helpers for Sapphire.

Modules:
  - readiness  — repo-grounded config/artifact inspection
  - client     — SDK wrapper with token + OAuth auth
  - ingestion  — transform local data → Foundry ontology objects
  - sync       — 15-min delta-aware scheduled sync with Telegram alerts
"""

from .readiness import build_foundry_readiness

__all__ = ["build_foundry_readiness"]
