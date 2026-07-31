"""Live rot detector for every active MegaETH protocol-registry address.

This is opt-in with the rest of the live suite:
``SAPPHIRE_MEGAETH_INTEGRATION=1``.
"""

from __future__ import annotations

import json
import os
import urllib.request

from lib.chains.megaeth.registry import ProtocolRegistry


def _rpc(method: str, params: list[object]) -> str:
    endpoint = os.getenv("SAPPHIRE_MEGAETH_RPC_URL", "https://mainnet.megaeth.com/rpc")
    body = json.dumps({"jsonrpc": "2.0", "method": method, "params": params, "id": 1}).encode()
    request = urllib.request.Request(
        endpoint,
        data=body,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "sapphire-megaeth-registry-check/1.0",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310
        payload = json.loads(response.read())
    assert "error" not in payload, payload.get("error")
    return str(payload["result"])


def test_every_active_registry_address_has_mainnet_code() -> None:
    assert int(_rpc("eth_chainId", []), 16) == 4326

    empty: list[str] = []
    for protocol in ProtocolRegistry.from_yaml():
        if protocol.status != "active":
            continue
        for role, address in protocol.addresses.items():
            code = _rpc("eth_getCode", [address, "latest"])
            if code in {"0x", "0x0", ""}:
                empty.append(f"{protocol.key}.{role}={address}")

    assert not empty, "active MegaETH addresses without bytecode: " + ", ".join(empty)
