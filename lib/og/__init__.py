"""0G integration for Sapphire — verifiable trading signal anchoring.

All entry points are gated by `SAPPHIRE_OG_ENABLED=1`. When unset, the
integration is inert and the trading critical path is unaffected.

See `docs/hackathon-0g/design.md` for the architecture.
"""

from lib.og.config import (
    OG_CHAIN_MAINNET,
    OG_CHAIN_TESTNET,
    OG_INDEXER_MAINNET,
    OG_INDEXER_TESTNET,
    OG_RPC_MAINNET,
    OG_RPC_TESTNET,
    is_enabled,
    network_config,
)

__all__ = [
    "OG_CHAIN_MAINNET",
    "OG_CHAIN_TESTNET",
    "OG_INDEXER_MAINNET",
    "OG_INDEXER_TESTNET",
    "OG_RPC_MAINNET",
    "OG_RPC_TESTNET",
    "is_enabled",
    "network_config",
]
