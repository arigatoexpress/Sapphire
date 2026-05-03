"""Minimal HTTP JSON-RPC client used by :func:`default_gate`.

This is *only* a transport — it issues raw JSON-RPC calls, but does
NOT implement the chain-specific protocol decoders (Aave V3 reserve
reads, USDM peg monitor, Kumbaya pool quotes). Those decoders live
in Sapphire's ``lib/chains/`` and are NOT vendored here — the package
would balloon 10x and tie users to Sapphire's contract registry.

Practically, this client is only useful when:

1. You're testing the dispatcher's transport path (timeouts, fail-open).
2. You're plugging the gate into a stack that already has its own
   ``MegaETHProtocols`` / ``ArbitrumProtocols``-compatible client and
   you want a working ``default_gate()`` reference.

For the live chain reads, supply your own client to
``ChainHealthGate(client_factory=...)`` — the duck-typed contract is
documented in the README under "Bring your own client".
"""

from __future__ import annotations

from typing import Any

import httpx


class HttpJsonRpcClient:
    """Async-context-manager JSON-RPC client.

    Construct with an RPC URL; use as ``async with HttpJsonRpcClient(...) as c:``.
    The dispatcher in :mod:`chain_health_gate` recognises both shapes
    (CM and pre-opened) so this client plugs in unmodified.

    NB: this client does NOT implement ``stable_health()`` or
    ``lend_overview()`` — those are protocol-decoded reads. Calling
    :meth:`evaluate_chain` with this client as-is will surface as a
    "rpc error" verdict (fail-open by default). To get a real
    verdict, wrap this client in a ``MegaETHProtocols`` /
    ``ArbitrumProtocols`` instance from the upstream Sapphire repo,
    or implement the protocol surface yourself.
    """

    def __init__(self, rpc_url: str, *, timeout_s: float = 5.0) -> None:
        self._rpc_url = rpc_url
        self._timeout_s = timeout_s
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> HttpJsonRpcClient:
        self._client = httpx.AsyncClient(timeout=self._timeout_s)
        return self

    async def __aexit__(self, *_exc: Any) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def call(self, method: str, params: list[Any]) -> Any:
        """Issue a single JSON-RPC call and return the ``result`` field."""
        if self._client is None:
            raise RuntimeError(
                "HttpJsonRpcClient must be used inside `async with` — "
                "it isn't pre-opened by default."
            )
        resp = await self._client.post(
            self._rpc_url,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": method,
                "params": params,
            },
        )
        resp.raise_for_status()
        body = resp.json()
        if "error" in body:
            raise RuntimeError(f"RPC error: {body['error']}")
        return body["result"]

    # The dispatcher's MegaETH evaluator calls these — surface stubs
    # that raise ``NotImplementedError`` so the failure mode is loud
    # and the fail-open path kicks in cleanly.

    async def stable_health(self) -> Any:
        raise NotImplementedError(
            "HttpJsonRpcClient does not decode contract calls. "
            "Wrap with sapphire_os.MegaETHProtocols, or implement the "
            "duck-typed stable_health() / lend_overview() coroutines yourself."
        )

    async def lend_overview(self) -> Any:
        raise NotImplementedError(
            "HttpJsonRpcClient does not decode contract calls. "
            "Wrap with sapphire_os.MegaETHProtocols / ArbitrumProtocols, "
            "or implement the duck-typed lend_overview() coroutine yourself."
        )
