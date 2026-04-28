"""Read-only Ethereum JSON-RPC node provider.

Live mode requires ``SAPPHIRE_ETH_NODE_LIVE=1`` plus ``ETH_RPC_URL`` or
``ETHEREUM_RPC_URL``. The client intentionally exposes only read methods and
rejects transaction-submission RPCs.
"""

from __future__ import annotations

import os
from typing import Any

from lib.chain.aggregator import enforce_provider_cap, provider_live_enabled

from ._common import SourceError, http_post_json

_READ_ONLY_METHODS = {
    "eth_blockNumber",
    "eth_chainId",
    "eth_gasPrice",
    "eth_getBalance",
    "eth_getBlockByNumber",
    "eth_getTransactionCount",
    "net_listening",
    "net_peerCount",
    "net_version",
}


class EthNodeClient:
    """Minimal read-only Ethereum JSON-RPC client."""

    def __init__(self, rpc_url: str | None = None, live: bool | None = None) -> None:
        self.rpc_url = rpc_url or os.getenv("ETH_RPC_URL") or os.getenv("ETHEREUM_RPC_URL") or ""
        self.live = provider_live_enabled("eth_node") if live is None else bool(live)

    @property
    def mode(self) -> str:
        return "live" if self.live else "fixture"

    def rpc(self, method: str, params: list[Any] | None = None) -> Any:
        if method not in _READ_ONLY_METHODS:
            raise SourceError(f"eth_node: method not allowed: {method}")
        if not self.live:
            return self._fixture_result(method)
        if not self.rpc_url:
            raise SourceError("eth_node: missing ETH_RPC_URL/ETHEREUM_RPC_URL")
        enforce_provider_cap("eth_node")
        payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or []}
        response = http_post_json(self.rpc_url, payload, cache=False)
        if not isinstance(response, dict):
            raise SourceError(f"eth_node: {method} returned non-dict")
        if response.get("error"):
            raise SourceError(f"eth_node: {method} error: {response['error']}")
        return response.get("result")

    def chain_id(self) -> int | None:
        return _hex_to_int(self.rpc("eth_chainId"))

    def block_number(self) -> int | None:
        return _hex_to_int(self.rpc("eth_blockNumber"))

    def gas_price_wei(self) -> int | None:
        return _hex_to_int(self.rpc("eth_gasPrice"))

    def latest_block(self, *, include_transactions: bool = False) -> dict[str, Any]:
        result = self.rpc("eth_getBlockByNumber", ["latest", include_transactions])
        if not isinstance(result, dict):
            raise SourceError("eth_node: latest block returned non-dict")
        return result

    def network_snapshot(self) -> dict[str, Any]:
        gas_wei = self.gas_price_wei()
        latest = self.latest_block(include_transactions=False)
        return {
            "provider": "eth_node",
            "mode": self.mode,
            "chain_id": self.chain_id(),
            "block_number": self.block_number(),
            "gas_price_wei": gas_wei,
            "gas_price_gwei": round(gas_wei / 1_000_000_000, 3) if gas_wei is not None else None,
            "latest_block_hash": latest.get("hash"),
            "transaction_count": _hex_to_int(latest.get("transactions"))
            if isinstance(latest.get("transactions"), str)
            else len(latest.get("transactions") or []),
            "read_only": True,
            "wallet_keys_required": False,
        }

    def _fixture_result(self, method: str) -> Any:
        fixtures: dict[str, Any] = {
            "eth_chainId": "0x1",
            "eth_blockNumber": "0x13738ca",
            "eth_gasPrice": "0x1dfd14000",
            "eth_getBlockByNumber": {
                "number": "0x13738ca",
                "hash": "0x0000000000000000000000000000000000000000000000000000000000000abc",
                "transactions": [],
            },
            "eth_getBalance": "0x0",
            "eth_getTransactionCount": "0x0",
            "net_listening": True,
            "net_peerCount": "0x20",
            "net_version": "1",
        }
        return fixtures.get(method)


def _hex_to_int(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if not isinstance(value, str):
        return None
    try:
        return int(value, 16) if value.startswith("0x") else int(value)
    except ValueError:
        return None
