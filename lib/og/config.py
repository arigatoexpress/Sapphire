"""0G network configuration — single source of truth for endpoints + chain IDs.

Endpoints sourced from https://docs.0g.ai (verified 2026-04-30).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

OG_CHAIN_TESTNET = 16602
OG_CHAIN_MAINNET = 16661

OG_RPC_TESTNET = "https://evmrpc-testnet.0g.ai"
OG_RPC_MAINNET = "https://evmrpc.0g.ai"

OG_INDEXER_TESTNET = "https://indexer-storage-testnet-turbo.0g.ai"
OG_INDEXER_MAINNET = "https://indexer-storage-mainnet-turbo.0g.ai"

OG_EXPLORER_TESTNET = "https://chainscan-galileo.0g.ai"
OG_EXPLORER_MAINNET = "https://chainscan.0g.ai"

ENV_FLAG = "SAPPHIRE_OG_ENABLED"
ENV_NETWORK = "SAPPHIRE_OG_NETWORK"
ENV_PRIVATE_KEY = "OG_PRIVATE_KEY"


@dataclass(frozen=True)
class NetworkConfig:
    name: str
    chain_id: int
    rpc_url: str
    indexer_url: str
    explorer_url: str


_TESTNET = NetworkConfig(
    name="testnet",
    chain_id=OG_CHAIN_TESTNET,
    rpc_url=OG_RPC_TESTNET,
    indexer_url=OG_INDEXER_TESTNET,
    explorer_url=OG_EXPLORER_TESTNET,
)

_MAINNET = NetworkConfig(
    name="mainnet",
    chain_id=OG_CHAIN_MAINNET,
    rpc_url=OG_RPC_MAINNET,
    indexer_url=OG_INDEXER_MAINNET,
    explorer_url=OG_EXPLORER_MAINNET,
)

_NETWORKS = {"testnet": _TESTNET, "mainnet": _MAINNET}


def is_enabled() -> bool:
    return os.environ.get(ENV_FLAG, "0").strip() == "1"


def network_config(network: str | None = None) -> NetworkConfig:
    name = (network or os.environ.get(ENV_NETWORK, "testnet")).strip().lower()
    if name not in _NETWORKS:
        raise ValueError(f"Unknown 0G network '{name}'. Use 'testnet' or 'mainnet'.")
    return _NETWORKS[name]
