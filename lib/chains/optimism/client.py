"""Optimism mainnet JSON-RPC HTTP client.

Same shape as ``ArbitrumClient`` / ``MegaETHClient`` — exposes
``_call(method, params)`` and an async-context-manager interface so the
typed contract wrappers and ``OptimismProtocols`` facade can use the same
plumbing as the other chain packages. Defaults to the public Optimism
Foundation RPC (``https://mainnet.optimism.io``); production deployments
override ``OptimismConfig.http_rpc`` with a private node.

Read-only on purpose. No nonce helper, no signer, no
``eth_sendTransaction`` plumbing — write paths land in their own gated
executor module mirroring the MegaETH wave-C pattern.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

#: Public Optimism mainnet RPC endpoint. Plenty of read throughput for
#: dashboards/screening; production live trading should replace this with
#: a private node URL via ``OptimismConfig.http_rpc``.
DEFAULT_OPTIMISM_RPC = os.getenv(
    "SAPPHIRE_OPTIMISM_RPC_URL",
    "https://mainnet.optimism.io",
)

#: Optimism mainnet chain ID. Hex form ``0xa`` is what ``eth_chainId``
#: returns. Pinned because every consumer keys behaviour on this constant.
OPTIMISM_CHAIN_ID = 10

#: Per-call timeout. The Aave UiPoolDataProvider read can be a 60KB+
#: response on Optimism, so leave headroom.
DEFAULT_TIMEOUT_S = 15.0


@dataclass(frozen=True)
class OptimismConfig:
    """Per-instance configuration for :class:`OptimismClient`."""

    http_rpc: str = DEFAULT_OPTIMISM_RPC
    chain_id: int = OPTIMISM_CHAIN_ID
    timeout_s: float = DEFAULT_TIMEOUT_S


class OptimismClient:
    """Minimal async JSON-RPC HTTP client for Optimism mainnet.

    Usage::

        cfg = OptimismConfig()
        async with OptimismClient(cfg) as client:
            cid = await client.chain_id()
            assert cid == 10

    Designed to be drop-in compatible with the structural ``_call`` Protocol
    used by the typed contract wrappers — same interface as
    ``ArbitrumClient`` / ``MegaETHClient`` so the same wrappers work
    against either chain.
    """

    def __init__(self, config: OptimismConfig | None = None) -> None:
        self.config = config or OptimismConfig()
        self._http: Any | None = None  # late httpx import — keep import-time deps small

    async def __aenter__(self) -> OptimismClient:
        import httpx  # noqa: PLC0415 — late import keeps non-RPC consumers light

        self._http = httpx.AsyncClient(timeout=self.config.timeout_s)
        return self

    async def __aexit__(self, *exc: Any) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    async def _call(self, method: str, params: list[Any] | None = None) -> Any:
        """Issue a JSON-RPC call. Returns the raw ``result`` field on success.

        Raises ``RuntimeError`` on JSON-RPC errors; the body of the error
        is included so production logs can route on it.
        """
        if self._http is None:
            raise RuntimeError("OptimismClient not entered: use `async with OptimismClient(...)`")
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params or [],
        }
        response = await self._http.post(self.config.http_rpc, json=payload)
        response.raise_for_status()
        body = response.json()
        if "error" in body and body["error"]:
            raise RuntimeError(f"JSON-RPC error from {self.config.http_rpc}: {body['error']}")
        return body.get("result")

    async def chain_id(self) -> int:
        """``eth_chainId`` → integer (10 for Optimism mainnet)."""
        raw = await self._call("eth_chainId", [])
        if isinstance(raw, str) and raw.startswith("0x"):
            return int(raw, 16)
        return int(raw)

    async def get_code(self, address: str) -> str:
        """``eth_getCode`` — used by the address-verification preflight.

        Always verify a wrapper's address has bytecode BEFORE binding it.
        Returns the hex string (``"0x"`` for an EOA / unverified deploy).
        """
        if not isinstance(address, str) or not address.startswith("0x") or len(address) != 42:
            raise ValueError(f"invalid address: {address!r}")
        return await self._call("eth_getCode", [address, "latest"])
