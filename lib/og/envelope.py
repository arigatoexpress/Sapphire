"""Signal envelope — the canonical payload uploaded to 0G Storage.

Why an envelope? A raw signal JSON line works, but for verifiable finance
we want to carry:
  - the operator's claimed strategy + signal
  - the inference attestation (model, provider, chatID for TEE re-verify)
  - the source data fingerprint (so we know the same prices were used)
  - a publication timestamp inside the blob, distinct from on-chain timestamp

Everything is content-hashed via 0G Storage's merkle root; the
on-chain `proofHash` is that root. Anyone can pull the blob, recompute
the merkle root, and check it matches.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

ENVELOPE_VERSION = "sapphire-og-envelope/1"


@dataclass(frozen=True)
class InferenceAttestation:
    provider_address: str
    model: str
    chat_id: str
    base_url: str

    @classmethod
    def empty(cls) -> InferenceAttestation:
        return cls(provider_address="", model="", chat_id="", base_url="")


@dataclass(frozen=True)
class SignalEnvelope:
    version: str
    published_at: str
    strategy: str
    symbol: str
    direction: int  # 0=neutral, 1=long, 2=short
    confidence_bp: int  # 0..10000
    signal: dict[str, Any] = field(default_factory=dict)
    inputs_fingerprint: str = ""  # sha256 of canonical inputs JSON
    inference: InferenceAttestation = field(default_factory=InferenceAttestation.empty)

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))

    def content_hash(self) -> str:
        return "0x" + hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


def build_envelope(
    *,
    strategy: str,
    symbol: str,
    direction: int,
    confidence_bp: int,
    signal: dict[str, Any] | None = None,
    inputs: dict[str, Any] | None = None,
    inference: InferenceAttestation | None = None,
) -> SignalEnvelope:
    canonical_inputs = json.dumps(inputs or {}, sort_keys=True, separators=(",", ":"))
    inputs_fp = "0x" + hashlib.sha256(canonical_inputs.encode("utf-8")).hexdigest()
    return SignalEnvelope(
        version=ENVELOPE_VERSION,
        published_at=datetime.now(UTC).isoformat(),
        strategy=strategy,
        symbol=symbol,
        direction=direction,
        confidence_bp=confidence_bp,
        signal=signal or {},
        inputs_fingerprint=inputs_fp,
        inference=inference or InferenceAttestation.empty(),
    )


def direction_from_action(action: str) -> int:
    """Map signal_pipeline / paper_trader action strings to the on-chain enum."""
    a = (action or "").strip().lower()
    if a in {"buy", "long", "open_long", "bull"}:
        return 1
    if a in {"sell", "short", "open_short", "bear"}:
        return 2
    return 0


def confidence_to_bp(score: float | int | None) -> int:
    """Map a 0..100 score (Sapphire's signal score) to 0..10000 basis points."""
    if score is None:
        return 0
    s = float(score)
    if s < 0:
        s = 0.0
    if s <= 1.0:  # already a fraction
        s *= 100.0
    if s > 100:
        s = 100.0
    return int(round(s * 100))
