"""Robinhood Chain (Arbitrum Orbit, chain ID 46630) integration.

Manages web3 connections to testnet, publishes trading signals on-chain,
and reads contract state. Reads deployed addresses from
data/chain/deployments.json; falls back gracefully when web3 is unavailable.

Usage:
    client = RobinhoodChainClient()
    client.publish_signal("ultra_v3", "BTC-USD", "long", 0.75)
    status = client.get_chain_status()
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
DEPLOYMENTS_FILE = ROOT / "data" / "chain" / "deployments.json"

TESTNET_RPC = "https://rpc.testnet.chain.robinhood.com"
TESTNET_WSS = "wss://feed.testnet.chain.robinhood.com"
CHAIN_ID = 46630
EXPLORER_URL = "https://explorer.testnet.chain.robinhood.com"

DIRECTION_MAP = {"neutral": 0, "long": 1, "short": 2}
DIRECTION_NAMES = {0: "neutral", 1: "long", 2: "short"}

# Minimal ABIs — only the functions we call
_SIGNAL_VERIFIER_ABI = [
    {
        "name": "publishSignal",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "strategyId", "type": "bytes32"},
            {"name": "symbol", "type": "string"},
            {"name": "direction", "type": "uint8"},
            {"name": "confidence", "type": "uint16"},
            {"name": "proofHash", "type": "bytes32"},
        ],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "name": "getSignal",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "id", "type": "uint256"}],
        "outputs": [
            {
                "name": "",
                "type": "tuple",
                "components": [
                    {"name": "strategyId", "type": "bytes32"},
                    {"name": "symbol", "type": "string"},
                    {"name": "direction", "type": "uint8"},
                    {"name": "confidence", "type": "uint16"},
                    {"name": "timestamp", "type": "uint256"},
                    {"name": "proofHash", "type": "bytes32"},
                ],
            }
        ],
    },
    {
        "name": "getLatestSignals",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "count", "type": "uint256"}],
        "outputs": [
            {
                "name": "",
                "type": "tuple[]",
                "components": [
                    {"name": "strategyId", "type": "bytes32"},
                    {"name": "symbol", "type": "string"},
                    {"name": "direction", "type": "uint8"},
                    {"name": "confidence", "type": "uint16"},
                    {"name": "timestamp", "type": "uint256"},
                    {"name": "proofHash", "type": "bytes32"},
                ],
            }
        ],
    },
    {
        "name": "signalCount",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint256"}],
    },
]

_PAYMENT_GATE_ABI = [
    {
        "name": "hasAccess",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "user", "type": "address"}],
        "outputs": [{"name": "", "type": "bool"}],
    },
    {
        "name": "isSubscribed",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "user", "type": "address"}],
        "outputs": [{"name": "", "type": "bool"}],
    },
    {
        "name": "credits",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "", "type": "address"}],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "name": "pricePerSignal",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "name": "monthlySubscription",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint256"}],
    },
]


@dataclass
class OnChainSignal:
    id: int
    strategy_id: str
    symbol: str
    direction: str
    confidence_bps: int
    timestamp: int
    proof_hash: str

    @property
    def confidence_pct(self) -> float:
        return self.confidence_bps / 100.0


@dataclass
class ChainStatus:
    connected: bool
    chain_id: int | None = None
    block_number: int | None = None
    gas_price_gwei: float | None = None
    signal_verifier_address: str | None = None
    payment_gate_address: str | None = None
    sentinel_registry_address: str | None = None
    signal_count: int | None = None
    error: str | None = None


class RobinhoodChainClient:
    """Interact with Sapphire OS contracts on Robinhood Chain."""

    def __init__(
        self,
        rpc_url: str = TESTNET_RPC,
        private_key: str | None = None,
        deployments_file: Path = DEPLOYMENTS_FILE,
    ) -> None:
        self._rpc_url = rpc_url
        self._private_key = private_key
        self._deployments_file = deployments_file
        self._w3: Any = None
        self._account: Any = None
        self._verifier_contract: Any = None
        self._payment_contract: Any = None
        self._addresses: dict[str, str] = {}
        self._initialized = False

    # ------------------------------------------------------------------
    # Init / connection
    # ------------------------------------------------------------------

    def _ensure_init(self) -> bool:
        if self._initialized:
            return self._w3 is not None

        self._initialized = True
        try:
            from web3 import Web3  # type: ignore[import]
        except ImportError:
            log.warning("web3 not installed — on-chain features disabled")
            return False

        self._w3 = Web3(Web3.HTTPProvider(self._rpc_url, request_kwargs={"timeout": 10}))
        if not self._w3.is_connected():
            log.warning("Cannot connect to Robinhood Chain RPC: %s", self._rpc_url)
            self._w3 = None
            return False

        if self._private_key:
            from eth_account import Account  # type: ignore[import]

            self._account = Account.from_key(self._private_key)

        self._load_deployments()
        self._init_contracts()
        return True

    def _load_deployments(self) -> None:
        if not self._deployments_file.exists():
            return
        try:
            data = json.loads(self._deployments_file.read_text())
            net = data.get("robinhood_testnet", {})
            contracts = net.get("contracts", {})
            self._addresses = {name: info["address"] for name, info in contracts.items()}
        except Exception as exc:
            log.warning("Failed to load deployments: %s", exc)

    def _init_contracts(self) -> None:
        if not self._w3:
            return
        from web3 import Web3  # type: ignore[import]

        verifier_addr = self._addresses.get("SapphireSignalVerifier")
        if verifier_addr:
            self._verifier_contract = self._w3.eth.contract(
                address=Web3.to_checksum_address(verifier_addr),
                abi=_SIGNAL_VERIFIER_ABI,
            )

        payment_addr = self._addresses.get("SapphirePaymentGate")
        if payment_addr:
            self._payment_contract = self._w3.eth.contract(
                address=Web3.to_checksum_address(payment_addr),
                abi=_PAYMENT_GATE_ABI,
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def publish_signal(
        self,
        strategy: str,
        symbol: str,
        direction: str,
        confidence: float,
        proof_hash: str | None = None,
    ) -> dict:
        """Publish a trading signal on-chain.

        Args:
            strategy: strategy name (hashed to bytes32)
            symbol: e.g. "BTC-USD"
            direction: "long" | "short" | "neutral"
            confidence: 0.0–1.0 (converted to basis points internally)
            proof_hash: optional hex ZK proof hash

        Returns dict with tx_hash and signal id, or {"error": ...} on failure.
        """
        if not self._ensure_init():
            return {"error": "web3 unavailable or not connected"}
        if not self._account:
            return {"error": "private key not configured"}
        if not self._verifier_contract:
            return {"error": "SapphireSignalVerifier not deployed (run deploy script)"}

        direction_int = DIRECTION_MAP.get(direction.lower(), 0)
        confidence_bps = int(confidence * 10000)
        strategy_id = hashlib.sha256(strategy.encode()).digest()[:32].ljust(32, b"\x00")
        strategy_bytes32 = bytes(strategy_id[:32])
        proof_bytes32 = bytes.fromhex(proof_hash.lstrip("0x")) if proof_hash else b"\x00" * 32
        if len(proof_bytes32) < 32:
            proof_bytes32 = proof_bytes32.ljust(32, b"\x00")

        try:
            nonce = self._w3.eth.get_transaction_count(self._account.address)
            tx = self._verifier_contract.functions.publishSignal(
                strategy_bytes32,
                symbol,
                direction_int,
                confidence_bps,
                proof_bytes32[:32],
            ).build_transaction(
                {
                    "from": self._account.address,
                    "nonce": nonce,
                    "gasPrice": self._w3.eth.gas_price,
                    "chainId": CHAIN_ID,
                }
            )
            tx["gas"] = self._w3.eth.estimate_gas(tx)
            signed = self._account.sign_transaction(tx)
            tx_hash = self._w3.eth.send_raw_transaction(signed.raw_transaction)
            receipt = self._w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
            signal_id = receipt["logs"][0]["topics"][1].hex() if receipt["logs"] else None
            return {
                "tx_hash": tx_hash.hex(),
                "signal_id": signal_id,
                "explorer": f"{EXPLORER_URL}/tx/{tx_hash.hex()}",
                "status": "confirmed" if receipt["status"] == 1 else "failed",
            }
        except Exception as exc:
            log.exception("publish_signal failed")
            return {"error": str(exc)}

    def get_signal_history(self, count: int = 10) -> list[dict]:
        """Read recent signals from chain."""
        if not self._ensure_init():
            return []
        if not self._verifier_contract:
            return []

        try:
            raw = self._verifier_contract.functions.getLatestSignals(count).call()
            result = []
            total = self._verifier_contract.functions.signalCount().call()
            start_id = max(0, total - count)
            for i, sig in enumerate(raw):
                s = OnChainSignal(
                    id=start_id + i,
                    strategy_id=sig[0].hex(),
                    symbol=sig[1],
                    direction=DIRECTION_NAMES.get(sig[2], "neutral"),
                    confidence_bps=sig[3],
                    timestamp=sig[4],
                    proof_hash=sig[5].hex(),
                )
                d = asdict(s)
                d["confidence_pct"] = s.confidence_pct
                result.append(d)
            return result
        except Exception as exc:
            log.warning("get_signal_history failed: %s", exc)
            return []

    def check_payment(self, address: str) -> dict:
        """Check if an address has paid for access."""
        if not self._ensure_init():
            return {"error": "web3 unavailable"}
        if not self._payment_contract:
            return {"error": "SapphirePaymentGate not deployed"}

        try:
            from web3 import Web3  # type: ignore[import]

            addr = Web3.to_checksum_address(address)
            has_access = self._payment_contract.functions.hasAccess(addr).call()
            is_sub = self._payment_contract.functions.isSubscribed(addr).call()
            cr = self._payment_contract.functions.credits(addr).call()
            return {
                "address": address,
                "has_access": has_access,
                "subscribed": is_sub,
                "credits": cr,
            }
        except Exception as exc:
            log.warning("check_payment failed: %s", exc)
            return {"error": str(exc)}

    def get_chain_status(self) -> ChainStatus:
        """Health check: block number, gas price, contract status."""
        if not self._ensure_init() or not self._w3:
            return ChainStatus(connected=False, error="web3 unavailable or RPC unreachable")

        try:
            block = self._w3.eth.block_number
            chain_id = self._w3.eth.chain_id
            gas_price = self._w3.from_wei(self._w3.eth.gas_price, "gwei")
            signal_count = None
            if self._verifier_contract:
                try:
                    signal_count = self._verifier_contract.functions.signalCount().call()
                except Exception:
                    pass

            return ChainStatus(
                connected=True,
                chain_id=chain_id,
                block_number=block,
                gas_price_gwei=float(gas_price),
                signal_verifier_address=self._addresses.get("SapphireSignalVerifier"),
                payment_gate_address=self._addresses.get("SapphirePaymentGate"),
                sentinel_registry_address=self._addresses.get("SapphireSentinelRegistry"),
                signal_count=signal_count,
            )
        except Exception as exc:
            log.warning("get_chain_status failed: %s", exc)
            return ChainStatus(connected=False, error=str(exc))

    def get_payment_gate_stats(self) -> dict:
        """Return pricing and stats from the payment gate contract."""
        if not self._ensure_init():
            return {"error": "web3 unavailable"}
        if not self._payment_contract:
            return {"error": "SapphirePaymentGate not deployed"}

        try:
            from web3 import Web3  # type: ignore[import]

            price_per_signal_wei = self._payment_contract.functions.pricePerSignal().call()
            monthly_wei = self._payment_contract.functions.monthlySubscription().call()
            return {
                "price_per_signal_eth": float(Web3.from_wei(price_per_signal_wei, "ether")),
                "monthly_subscription_eth": float(Web3.from_wei(monthly_wei, "ether")),
                "payment_gate_address": self._addresses.get("SapphirePaymentGate"),
            }
        except Exception as exc:
            log.warning("get_payment_gate_stats failed: %s", exc)
            return {"error": str(exc)}
