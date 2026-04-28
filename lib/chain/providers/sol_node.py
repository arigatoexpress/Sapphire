"""Read-only Solana JSON-RPC node provider.

Live mode requires ``SAPPHIRE_SOL_NODE_LIVE=1`` plus ``SOL_RPC_URL`` or
``SOLANA_RPC_URL``. The client intentionally rejects mutating RPC methods such
as ``sendTransaction`` and ``requestAirdrop``.
"""

from __future__ import annotations

import os
from typing import Any

from lib.chain.aggregator import enforce_provider_cap, provider_live_enabled

from ._common import SourceError, http_post_json

_READ_ONLY_METHODS = {
    "getBlockHeight",
    "getEpochInfo",
    "getHealth",
    "getLatestBlockhash",
    "getRecentPerformanceSamples",
    "getSlot",
    "getSupply",
    "getVersion",
}


class SolNodeClient:
    """Minimal read-only Solana JSON-RPC client."""

    def __init__(self, rpc_url: str | None = None, live: bool | None = None) -> None:
        self.rpc_url = rpc_url or os.getenv("SOL_RPC_URL") or os.getenv("SOLANA_RPC_URL") or ""
        self.live = provider_live_enabled("sol_node") if live is None else bool(live)

    @property
    def mode(self) -> str:
        return "live" if self.live else "fixture"

    def rpc(self, method: str, params: list[Any] | None = None) -> Any:
        if method not in _READ_ONLY_METHODS:
            raise SourceError(f"sol_node: method not allowed: {method}")
        if not self.live:
            return self._fixture_result(method)
        if not self.rpc_url:
            raise SourceError("sol_node: missing SOL_RPC_URL/SOLANA_RPC_URL")
        enforce_provider_cap("sol_node")
        payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or []}
        response = http_post_json(self.rpc_url, payload, cache=False)
        if not isinstance(response, dict):
            raise SourceError(f"sol_node: {method} returned non-dict")
        if response.get("error"):
            raise SourceError(f"sol_node: {method} error: {response['error']}")
        return response.get("result")

    def slot(self) -> int | None:
        return _to_int(self.rpc("getSlot"))

    def block_height(self) -> int | None:
        return _to_int(self.rpc("getBlockHeight"))

    def epoch_info(self) -> dict[str, Any]:
        result = self.rpc("getEpochInfo")
        if not isinstance(result, dict):
            raise SourceError("sol_node: getEpochInfo returned non-dict")
        return result

    def latest_blockhash(self) -> dict[str, Any]:
        result = self.rpc("getLatestBlockhash")
        if not isinstance(result, dict):
            raise SourceError("sol_node: getLatestBlockhash returned non-dict")
        value = result.get("value")
        return value if isinstance(value, dict) else result

    def network_snapshot(self) -> dict[str, Any]:
        epoch = self.epoch_info()
        blockhash = self.latest_blockhash()
        return {
            "provider": "sol_node",
            "mode": self.mode,
            "slot": self.slot(),
            "block_height": self.block_height(),
            "epoch": epoch.get("epoch"),
            "absolute_slot": epoch.get("absoluteSlot"),
            "transaction_count": epoch.get("transactionCount"),
            "latest_blockhash": blockhash.get("blockhash"),
            "last_valid_block_height": blockhash.get("lastValidBlockHeight"),
            "read_only": True,
            "wallet_keys_required": False,
        }

    def _fixture_result(self, method: str) -> Any:
        fixtures: dict[str, Any] = {
            "getSlot": 262_000_000,
            "getBlockHeight": 242_000_000,
            "getHealth": "ok",
            "getEpochInfo": {
                "absoluteSlot": 262_000_000,
                "blockHeight": 242_000_000,
                "epoch": 610,
                "slotIndex": 42_000,
                "slotsInEpoch": 432_000,
                "transactionCount": 410_000_000_000,
            },
            "getLatestBlockhash": {
                "context": {"slot": 262_000_000},
                "value": {
                    "blockhash": "DryRun11111111111111111111111111111111111111",
                    "lastValidBlockHeight": 242_000_150,
                },
            },
            "getRecentPerformanceSamples": [],
            "getSupply": {"value": {"total": 0, "circulating": 0, "nonCirculating": 0}},
            "getVersion": {"solana-core": "fixture"},
        }
        return fixtures.get(method)


def _to_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
