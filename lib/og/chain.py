"""0G Chain client — anchor signal hashes to SapphireSignalVerifier on 0G mainnet.

This is a thin wrapper over web3.py. The contract ABI is loaded from
`data/chain/sapphire_signal_verifier.abi.json`, written by the deploy script.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from lib.og.config import ENV_PRIVATE_KEY, network_config

ROOT = Path(__file__).resolve().parents[2]
DEPLOYMENTS_FILE = ROOT / "data" / "chain" / "deployments.json"
ABI_FILE = ROOT / "data" / "chain" / "sapphire_signal_verifier.abi.json"


class OGChainError(RuntimeError):
    pass


@dataclass(frozen=True)
class AnchorReceipt:
    signal_id: int
    tx_hash: str
    block_number: int
    explorer_url: str


def _load_signal_verifier_address(network_name: str) -> str:
    if not DEPLOYMENTS_FILE.exists():
        raise OGChainError(
            f"deployments file missing: {DEPLOYMENTS_FILE}. "
            "Run: python3 scripts/deploy_og_chain.py --network <network>"
        )
    deployments = json.loads(DEPLOYMENTS_FILE.read_text())
    key = f"og_{network_name}"
    block = deployments.get(key)
    if not block:
        raise OGChainError(
            f"no deployment recorded for {key} in {DEPLOYMENTS_FILE}. "
            f"Run: python3 scripts/deploy_og_chain.py --network {network_name}"
        )
    addr = block.get("contracts", {}).get("SapphireSignalVerifier", {}).get("address")
    if not addr:
        raise OGChainError(f"SapphireSignalVerifier address missing for {key}")
    return addr


def _load_abi() -> list[dict[str, Any]]:
    if not ABI_FILE.exists():
        raise OGChainError(
            f"ABI file missing: {ABI_FILE}. "
            "It is written by scripts/deploy_og_chain.py during compile."
        )
    return json.loads(ABI_FILE.read_text())


def strategy_id_from_name(name: str) -> bytes:
    """SapphireSignalVerifier stores strategyId as bytes32. We hash the name."""
    return sha256(name.encode("utf-8")).digest()


def publish_signal(
    *,
    strategy: str,
    symbol: str,
    direction: int,
    confidence_bp: int,
    proof_root_hash: str,
    network: str | None = None,
) -> AnchorReceipt:
    """Anchor a signal to SapphireSignalVerifier.publishSignal.

    Args:
        strategy: human-readable strategy name (e.g. "kronos_btc_24h")
        symbol: e.g. "BTC-USD"
        direction: 0=neutral, 1=long, 2=short
        confidence_bp: 0-10000 basis points
        proof_root_hash: 0G Storage merkle root for the signal blob (0x-prefixed)
        network: "testnet" | "mainnet" | None (uses SAPPHIRE_OG_NETWORK or 'testnet')
    """
    try:
        from eth_account import Account  # type: ignore[import]
        from web3 import Web3  # type: ignore[import]
    except ImportError as exc:
        raise OGChainError("web3 and eth-account are required") from exc

    cfg = network_config(network)
    private_key = os.environ.get(ENV_PRIVATE_KEY)
    if not private_key:
        raise OGChainError(f"{ENV_PRIVATE_KEY} must be set to publish signals on-chain")

    addr = _load_signal_verifier_address(cfg.name)
    abi = _load_abi()

    w3 = Web3(Web3.HTTPProvider(cfg.rpc_url, request_kwargs={"timeout": 15}))
    if not w3.is_connected():
        raise OGChainError(f"cannot connect to 0G RPC: {cfg.rpc_url}")

    account = Account.from_key(private_key)
    contract = w3.eth.contract(address=Web3.to_checksum_address(addr), abi=abi)

    if not (0 <= direction <= 2):
        raise OGChainError(f"direction must be 0/1/2, got {direction}")
    if not (0 <= confidence_bp <= 10000):
        raise OGChainError(f"confidence_bp must be 0..10000, got {confidence_bp}")

    proof_bytes = bytes.fromhex(
        proof_root_hash[2:] if proof_root_hash.startswith("0x") else proof_root_hash
    )
    if len(proof_bytes) != 32:
        raise OGChainError(f"proof_root_hash must be 32 bytes, got {len(proof_bytes)}")

    tx = contract.functions.publishSignal(
        strategy_id_from_name(strategy),
        symbol,
        direction,
        confidence_bp,
        proof_bytes,
    ).build_transaction(
        {
            "from": account.address,
            "nonce": w3.eth.get_transaction_count(account.address),
            "gasPrice": w3.eth.gas_price,
            "chainId": cfg.chain_id,
        }
    )
    tx["gas"] = w3.eth.estimate_gas(tx)

    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    if receipt["status"] != 1:
        raise OGChainError(f"publishSignal reverted (tx {tx_hash.hex()})")

    signal_id = -1
    for log in receipt["logs"]:
        try:
            ev = contract.events.SignalPublished().process_log(log)
            signal_id = int(ev["args"]["id"])
            break
        except Exception:
            continue

    return AnchorReceipt(
        signal_id=signal_id,
        tx_hash="0x" + tx_hash.hex() if not tx_hash.hex().startswith("0x") else tx_hash.hex(),
        block_number=int(receipt["blockNumber"]),
        explorer_url=f"{cfg.explorer_url}/tx/{tx_hash.hex() if tx_hash.hex().startswith('0x') else '0x' + tx_hash.hex()}",
    )


def get_signal(signal_id: int, *, network: str | None = None) -> dict[str, Any]:
    """Read a previously-published signal from on-chain state."""
    try:
        from web3 import Web3  # type: ignore[import]
    except ImportError as exc:
        raise OGChainError("web3 is required") from exc

    cfg = network_config(network)
    addr = _load_signal_verifier_address(cfg.name)
    abi = _load_abi()

    w3 = Web3(Web3.HTTPProvider(cfg.rpc_url, request_kwargs={"timeout": 15}))
    contract = w3.eth.contract(address=Web3.to_checksum_address(addr), abi=abi)
    s = contract.functions.signals(signal_id).call()
    return {
        "id": signal_id,
        "strategy_id": "0x" + s[0].hex(),
        "symbol": s[1],
        "direction": int(s[2]),
        "confidence_bp": int(s[3]),
        "timestamp": int(s[4]),
        "proof_root_hash": "0x" + s[5].hex(),
    }
