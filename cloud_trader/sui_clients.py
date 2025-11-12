"""Placeholder Sui integration clients for decentralized science hooks.

These stubs illustrate how Sapphire can leverage the Sui ecosystem while
respecting user privacy and data ownership. Actual implementations will wire
into Walrus for encrypted blob storage, Seal for secure enclave compute, and
Nautilus for on-chain market telemetry once production keys are provisioned.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class SuiWalrusClient:
    """Stub for Walrus decentralized storage interactions."""

    endpoint: Optional[str] = None
    api_key: Optional[str] = None

    async def put_private_blob(self, namespace: str, payload: Dict[str, Any]) -> str:
        """Persist encrypted payloads while preserving user data ownership.

        TODO: Encrypt with user-controlled keys before upload and return a content
        addressable identifier that FinGPT/Lag-LLaMA agents can reference without
        exposing raw inputs to third parties.
        """

        raise NotImplementedError("Walrus client requires project-specific credentials")

    async def fetch_blob(self, cid: str) -> Dict[str, Any]:
        """Retrieve a previously stored blob using its content ID."""

        raise NotImplementedError("Walrus client requires project-specific credentials")


@dataclass
class SuiSealClient:
    """Stub for Sui Seal secure compute enclave orchestration."""

    endpoint: Optional[str] = None

    async def submit_private_job(self, job_name: str, payload: Dict[str, Any]) -> str:
        """Submit sensitive computations to a sealed enclave.

        TODO: Use this to run confidential strategy evaluations or risk checks
        without leaking prompts or community data beyond approved boundaries.
        """

        raise NotImplementedError("Seal client requires project-specific credentials")

    async def job_status(self, job_id: str) -> Dict[str, Any]:
        """Check execution status for asynchronous enclave workloads."""

        raise NotImplementedError("Seal client requires project-specific credentials")


@dataclass
class SuiNautilusClient:
    """Stub for Nautilus market/DeFi data ingestion."""

    endpoint: Optional[str] = None

    async def fetch_market_observations(self, instrument: str) -> Dict[str, Any]:
        """Pull on-chain telemetry to augment agent market context.

        TODO: Stream anonymized community metrics or liquidity signals that bots
        can cross-check without overweighting sparse crowd data.
        """

        raise NotImplementedError("Nautilus client requires project-specific credentials")
