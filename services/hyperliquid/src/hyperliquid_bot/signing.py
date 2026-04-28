"""EIP-712 signing primitives for Hyperliquid L1 actions.

Mirrors ``hyperliquid-python-sdk/hyperliquid/utils/signing.py`` so our client
authenticates correctly. Hyperliquid signs L1 actions (orders, cancels,
modifies, transfers) by:

1. msgpack-packing the action, then appending nonce (8B big-endian), a vault
   sentinel byte (``0x00`` no vault / ``0x01`` + 20B vault address), and an
   ``expires_after`` sentinel + 8B value if present.
2. keccak256 over the bytestream → 32-byte ``connectionId``.
3. Wrap as a "phantom agent": ``{"source": "a" if mainnet else "b",
   "connectionId": <hash>}``.
4. Sign the phantom agent under the EIP-712 domain
   ``{name=Exchange, version=1, chainId=1337, verifyingContract=0x0…0}`` with
   the ``Agent`` typed-data struct.

Mainnet vs testnet is encoded in the phantom-agent ``source`` field, **not**
the chainId — chainId is always 1337 for L1 actions.

The previous ``client.py:_sign_action`` did sha256 → ``encode_defunct`` and
would never authenticate. This module is the fix.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import msgpack
from eth_account import Account
from eth_account.messages import encode_typed_data
from eth_account.signers.local import LocalAccount
from eth_utils import keccak, to_hex

L1_DOMAIN: dict[str, Any] = {
    "name": "Exchange",
    "version": "1",
    "chainId": 1337,
    "verifyingContract": "0x0000000000000000000000000000000000000000",
}

L1_TYPES: dict[str, list[dict[str, str]]] = {
    "Agent": [
        {"name": "source", "type": "string"},
        {"name": "connectionId", "type": "bytes32"},
    ],
    "EIP712Domain": [
        {"name": "name", "type": "string"},
        {"name": "version", "type": "string"},
        {"name": "chainId", "type": "uint256"},
        {"name": "verifyingContract", "type": "address"},
    ],
}


def float_to_wire(x: float) -> str:
    """Format a float as Hyperliquid expects (8 decimals, normalized).

    Raises on any rounding loss past 1e-12 — Hyperliquid rejects orders whose
    wire format doesn't round-trip cleanly to the on-the-wire string.
    """
    rounded = f"{x:.8f}"
    if abs(float(rounded) - x) >= 1e-12:
        raise ValueError(f"float_to_wire causes rounding: {x!r}")
    if rounded == "-0":
        rounded = "0"
    return f"{Decimal(rounded).normalize():f}"


def address_to_bytes(address: str) -> bytes:
    return bytes.fromhex(address[2:] if address.startswith("0x") else address)


def action_hash(
    action: Any,
    vault_address: str | None,
    nonce: int,
    expires_after: int | None,
) -> bytes:
    """Canonical L1 action hash. msgpack action || nonce || vault || expiry."""
    data = msgpack.packb(action)
    data += nonce.to_bytes(8, "big")
    if vault_address is None:
        data += b"\x00"
    else:
        data += b"\x01"
        data += address_to_bytes(vault_address)
    if expires_after is not None:
        data += b"\x00"
        data += expires_after.to_bytes(8, "big")
    return keccak(data)


def construct_phantom_agent(connection_id: bytes, is_mainnet: bool) -> dict[str, Any]:
    """Wrap the action hash as a Hyperliquid Agent struct.

    ``source`` is ``"a"`` for mainnet, ``"b"`` for testnet — the only place
    network is encoded; chainId stays 1337 either way.
    """
    return {"source": "a" if is_mainnet else "b", "connectionId": connection_id}


def l1_payload(phantom_agent: dict[str, Any]) -> dict[str, Any]:
    return {
        "domain": L1_DOMAIN,
        "types": L1_TYPES,
        "primaryType": "Agent",
        "message": phantom_agent,
    }


def sign_l1_action(
    wallet: LocalAccount,
    action: Any,
    *,
    vault_address: str | None = None,
    nonce: int,
    expires_after: int | None = None,
    is_mainnet: bool,
) -> dict[str, Any]:
    """Sign an L1 action and return the ``{r, s, v}`` triple Hyperliquid expects."""
    h = action_hash(action, vault_address, nonce, expires_after)
    phantom = construct_phantom_agent(h, is_mainnet)
    payload = l1_payload(phantom)
    structured = encode_typed_data(full_message=payload)
    signed = wallet.sign_message(structured)
    return {
        "r": to_hex(signed["r"]),
        "s": to_hex(signed["s"]),
        "v": signed["v"],
    }


def recover_l1_signer(
    action: Any,
    signature: dict[str, Any],
    *,
    vault_address: str | None = None,
    nonce: int,
    expires_after: int | None = None,
    is_mainnet: bool,
) -> str:
    """Round-trip a signature back to the signing address — for tests."""
    h = action_hash(action, vault_address, nonce, expires_after)
    phantom = construct_phantom_agent(h, is_mainnet)
    payload = l1_payload(phantom)
    structured = encode_typed_data(full_message=payload)
    return Account.recover_message(
        structured,
        vrs=[signature["v"], signature["r"], signature["s"]],
    )


__all__ = [
    "L1_DOMAIN",
    "L1_TYPES",
    "action_hash",
    "address_to_bytes",
    "construct_phantom_agent",
    "float_to_wire",
    "l1_payload",
    "recover_l1_signer",
    "sign_l1_action",
]
