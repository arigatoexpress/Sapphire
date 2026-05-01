"""Zama/FHEVM-shaped privacy mock for Sapphire Sentinel.

Production swap-in: replace ``FhevmClient`` below with
``from zama_fhevm import FhevmClient`` once a Zama gateway endpoint
(e.g. fhevm.zama.ai) is configured for the Sentinel deployment.

Today's implementation is a deterministic in-process mock that mirrors
FHEVM's input-blind / output-opaque shape:

* inputs (basket weights) never leave the host that owns them;
* outputs are opaque 32-byte commitments suitable for on-chain anchoring.

The mock uses HMAC-SHA256 over a canonical JSON encoding of the weights,
keyed by a per-basket entropy salt. Real FHEVM would substitute homomorphic
addition + a re-encryption-under-public-key step; the *interface* (encrypted
inputs in, opaque commitment out) is identical so call-sites do not change
when the production client is wired in.
"""

from __future__ import annotations

import hmac
import json
import os
import secrets
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from hashlib import sha256


def _canonical_weights(weights: Mapping[str, Decimal]) -> bytes:
    """Stable byte encoding of a weight map.

    Sorted by symbol; values stringified via ``Decimal.__str__`` so that
    ``Decimal("0.40")`` and ``Decimal("0.4")`` are treated as distinct
    inputs (matching FHEVM ciphertext behavior — the encoding, not the
    real number, is what gets committed to).
    """

    payload = {str(symbol): str(weight) for symbol, weight in sorted(weights.items())}
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")


class FhevmClient:
    """Mock FHEVM client.

    The real client would expose ``encrypt(value, public_key)``,
    ``add(ct1, ct2)``, ``reencrypt(ct, recipient_pk)``, etc. For the
    buildathon demo we collapse that to a single
    ``compute_basket_aggregate`` step that:

    1. canonicalizes the weight map (stand-in for per-symbol encryption),
    2. HMAC-SHA256s under a caller-supplied salt (stand-in for the FHE
       evaluation key + re-encryption to a public verifier key),
    3. returns 32 raw bytes (the on-chain commitment).
    """

    def __init__(self, *, gateway_url: str | None = None) -> None:
        # gateway_url is accepted so the production swap-in is zero-diff at
        # call-sites; it is unused in the mock.
        self.gateway_url = gateway_url or os.environ.get("ZAMA_FHEVM_GATEWAY", "mock://local")

    def compute_basket_aggregate(
        self,
        weights: Mapping[str, Decimal],
        salt: bytes,
    ) -> bytes:
        """Return a 32-byte deterministic commitment over (weights, salt)."""

        if not isinstance(salt, (bytes, bytearray)):
            raise TypeError("salt must be bytes")
        if len(salt) == 0:
            raise ValueError("salt must be non-empty (≥16 bytes recommended)")

        message = _canonical_weights(weights)
        return hmac.new(salt, message, sha256).digest()


@dataclass(frozen=True)
class HiddenBasket:
    """A private portfolio basket whose weights stay off-chain.

    Only opaque 32-byte commitments derived via :class:`FhevmClient` are
    ever exposed publicly. ``compute_hashes`` returns the
    ``(result_hash, risk_hash)`` pair anchored by ``SentinelDecision``.
    """

    weights: dict[str, Decimal]
    entropy: bytes = field(default_factory=lambda: secrets.token_bytes(32))

    def compute_hashes(self, client: FhevmClient) -> tuple[str, str]:
        """Return ``(result_hash, risk_hash)`` as 0x-prefixed hex strings.

        * ``result_hash`` — encrypted aggregate of the raw weights.
        * ``risk_hash``  — encrypted aggregate of ``{symbol: weight**2}``,
          a portfolio-variance proxy under the working assumption σ²≈1
          per asset (Herfindahl-style concentration commitment).

        Both go through the same ``FhevmClient.compute_basket_aggregate``
        call so the mock interface is byte-for-byte identical to the
        production FHEVM call we will swap in.
        """

        # Domain-separate the two computations so they share the same
        # entropy without colliding. Real FHEVM would use distinct
        # evaluation circuits; we use distinct salts to match the shape.
        result_salt = b"sapphire.sentinel.result|" + self.entropy
        risk_salt = b"sapphire.sentinel.risk|" + self.entropy

        result_bytes = client.compute_basket_aggregate(self.weights, result_salt)

        squared = {symbol: weight * weight for symbol, weight in self.weights.items()}
        risk_bytes = client.compute_basket_aggregate(squared, risk_salt)

        return ("0x" + result_bytes.hex(), "0x" + risk_bytes.hex())


# Deterministic entropy for the demo basket so the dashboard renders the
# same hashes on every load. Real deployments would draw fresh entropy
# per session and persist only the public commitments.
_DEMO_ENTROPY = sha256(b"sapphire.sentinel.london-2026.demo-basket.v1").digest()


def default_demo_basket() -> HiddenBasket:
    """Deterministic demo basket used by the Sentinel dashboard.

    Weights mirror the Robinhood Chain testnet stock-token allow-list
    (TSLA / AMZN / PLTR / NFLX / AMD) at concentration levels chosen to
    showcase the issuer-concentration cap in the policy reasoner.
    """

    weights = {
        "TSLA": Decimal("0.30"),
        "AMZN": Decimal("0.25"),
        "PLTR": Decimal("0.20"),
        "NFLX": Decimal("0.15"),
        "AMD": Decimal("0.10"),
    }
    return HiddenBasket(weights=weights, entropy=_DEMO_ENTROPY)
