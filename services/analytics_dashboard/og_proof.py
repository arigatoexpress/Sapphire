"""Public-safe 0G proof manifest for the hackathon page.

The goal is judge comprehension, not operational control. This module exposes
only paste-safe artifacts: public contract addresses, public tx/root hashes,
repo file readiness, and dry-run/verification commands. It never reads key
material and never contacts 0G.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _infer_repo_root() -> Path:
    """Infer repo root in both source checkout and flat Cloud Run image layouts."""
    here = Path(__file__).resolve()
    if len(here.parents) > 2 and (here.parents[2] / "services").exists():
        return here.parents[2]
    return here.parent


REPO_ROOT = Path(os.environ.get("SAPPHIRE_REPO_ROOT") or _infer_repo_root())

DEPLOYMENTS_FILE = REPO_ROOT / "data" / "chain" / "deployments.json"

MAINNET_CHAIN_ID = 16661
TESTNET_CHAIN_ID = 16602
MAINNET_EXPLORER = "https://chainscan.0g.ai"
TESTNET_EXPLORER = "https://chainscan-galileo.0g.ai"

ENV_CONTRACT_ADDRESS = "SAPPHIRE_OG_SIGNAL_VERIFIER_ADDRESS"
ENV_SIGNAL_ID = "SAPPHIRE_OG_SIGNAL_ID"
ENV_SIGNAL_TX = "SAPPHIRE_OG_SIGNAL_TX"
ENV_STORAGE_ROOT = "SAPPHIRE_OG_STORAGE_ROOT"
ENV_STORAGE_PROOF_URL = "SAPPHIRE_OG_STORAGE_PROOF_URL"
ENV_DEPLOYMENTS_FILE = "SAPPHIRE_DEPLOYMENTS_FILE"


def _exists(path: str) -> bool:
    return (REPO_ROOT / path).exists()


def _load_deployments() -> dict[str, Any]:
    deployments_file = Path(os.environ.get(ENV_DEPLOYMENTS_FILE, "") or DEPLOYMENTS_FILE)
    if not deployments_file.exists():
        return {}
    try:
        loaded = json.loads(deployments_file.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _contract_entry(deployments: dict[str, Any], network: str) -> dict[str, Any]:
    block = deployments.get(f"og_{network}") or {}
    contracts = block.get("contracts") or {}
    raw = contracts.get("SapphireSignalVerifier") or {}
    if isinstance(raw, str):
        return {"address": raw}
    return raw if isinstance(raw, dict) else {}


def _env(name: str) -> str | None:
    value = os.environ.get(name, "").strip()
    return value or None


def _explorer_url(explorer: str, kind: str, value: str | None) -> str | None:
    if not value:
        return None
    value = value if value.startswith("0x") else f"0x{value}"
    return f"{explorer}/{kind}/{value}"


def _readiness_row(id_: str, label: str, ok: bool, evidence: str, next_step: str = "") -> dict:
    return {
        "id": id_,
        "label": label,
        "ok": bool(ok),
        "status": "ready" if ok else "pending",
        "evidence": evidence,
        "next_step": next_step,
    }


def build_og_proof_manifest(*, now: datetime | None = None) -> dict[str, Any]:
    """Build the public 0G proof/readiness payload for `/p/hackathon`.

    The manifest is intentionally useful before the final mainnet tx exists:
    it shows repo readiness and the missing public artifacts without requiring
    secrets, network calls, or live chain writes.
    """
    ts = (now or datetime.now(UTC)).isoformat()
    deployments = _load_deployments()
    mainnet_contract = _contract_entry(deployments, "mainnet")
    testnet_contract = _contract_entry(deployments, "testnet")

    contract_address = _env(ENV_CONTRACT_ADDRESS) or mainnet_contract.get("address")
    signal_tx = _env(ENV_SIGNAL_TX) or mainnet_contract.get("sample_signal_tx")
    signal_id = _env(ENV_SIGNAL_ID) or mainnet_contract.get("sample_signal_id")
    storage_root = _env(ENV_STORAGE_ROOT) or mainnet_contract.get("sample_storage_root")
    storage_proof_url = _env(ENV_STORAGE_PROOF_URL) or mainnet_contract.get("storage_proof_url")

    source_checks = [
        _readiness_row(
            "storage_bridge",
            "0G Storage bridge",
            _exists("lib/og/storage.py") and _exists("lib/og/_ts/og_storage.mjs"),
            "lib/og/storage.py + official TS SDK bridge",
        ),
        _readiness_row(
            "compute_client",
            "0G Compute client",
            _exists("lib/og/compute.py"),
            "lib/og/compute.py records provider/model/chatID for TEE re-verification",
        ),
        _readiness_row(
            "chain_client",
            "0G Chain client",
            _exists("lib/og/chain.py") and _exists("contracts/SapphireSignalVerifier.sol"),
            "lib/og/chain.py + SapphireSignalVerifier.publishSignal",
        ),
        _readiness_row(
            "verifier_tool",
            "Read-only verifier",
            _exists("plugins/claw-sapphire/tools/og_verify.py"),
            "og_verify reads chain state, downloads 0G Storage blob, verifies merkle proof",
        ),
        _readiness_row(
            "offline_tests",
            "Offline regression tests",
            _exists("tests/unit/og_integration"),
            "pytest tests/unit/og_integration/ -q",
        ),
        _readiness_row(
            "mainnet_contract",
            "0G mainnet contract",
            bool(contract_address),
            contract_address or "No public 0G mainnet SapphireSignalVerifier address recorded yet",
            "Run scripts/deploy_og_chain.py --network mainnet from an operator wallet",
        ),
        _readiness_row(
            "signal_event",
            "SignalPublished event",
            bool(signal_tx or signal_id),
            signal_tx
            or (f"signal_id={signal_id}" if signal_id else "No public sample event recorded yet"),
            "Publish one deliberately labeled hackathon sample signal, then record tx/id",
        ),
        _readiness_row(
            "storage_root",
            "0G Storage root",
            bool(storage_root),
            storage_root or "No public storage root recorded yet",
            "Record the rootHash returned by og_publish for the sample signal",
        ),
    ]

    public_artifacts = {
        "contract_address": contract_address,
        "contract_explorer_url": _explorer_url(MAINNET_EXPLORER, "address", contract_address),
        "sample_signal_id": signal_id,
        "sample_signal_tx": signal_tx,
        "sample_signal_tx_url": _explorer_url(MAINNET_EXPLORER, "tx", signal_tx),
        "storage_root_hash": storage_root,
        "storage_proof_url": storage_proof_url,
        "testnet_contract_address": testnet_contract.get("address"),
        "testnet_contract_explorer_url": _explorer_url(
            TESTNET_EXPLORER, "address", testnet_contract.get("address")
        ),
    }

    source_ready = all(row["ok"] for row in source_checks[:5])
    live_proof_ready = bool(contract_address and (signal_tx or signal_id) and storage_root)
    status = "live-proof-ready" if live_proof_ready else "source-ready-live-proof-pending"

    return {
        "ok": source_ready,
        "status": status,
        "status_label": "LIVE PROOF READY"
        if live_proof_ready
        else "SOURCE READY / LIVE PROOF PENDING",
        "generated_at": ts,
        "networks": {
            "mainnet": {
                "chain_id": MAINNET_CHAIN_ID,
                "explorer": MAINNET_EXPLORER,
            },
            "testnet": {
                "chain_id": TESTNET_CHAIN_ID,
                "explorer": TESTNET_EXPLORER,
            },
        },
        "components": [
            {
                "name": "0G Compute",
                "proof": "TEE-sealed inference result carries provider, model, and chatID",
                "code": "lib/og/compute.py",
            },
            {
                "name": "0G Storage",
                "proof": "Full signal envelope is content-addressed by merkle rootHash",
                "code": "lib/og/storage.py",
            },
            {
                "name": "0G Chain",
                "proof": "SapphireSignalVerifier.publishSignal anchors rootHash with block timestamp",
                "code": "lib/og/chain.py",
            },
            {
                "name": "Sapphire Sentinel",
                "proof": "Payment and mandate receipts reuse the same on-chain safety spine",
                "code": "contracts/SapphireSentinelRegistry.sol",
            },
        ],
        "proof_flow": [
            "agent decision",
            "0G Compute chatID",
            "0G Storage rootHash",
            "0G Chain SignalPublished",
            "og_verify readback",
        ],
        "public_artifacts": public_artifacts,
        "readiness": source_checks,
        "judge_fast_path": [
            {
                "label": "Live proof API",
                "href": "/api/hackathon/0g-proof",
            },
            {
                "label": "Submission README",
                "href": "https://github.com/arigatoexpress/Sapphire/tree/main/docs/hackathon-0g",
            },
            {
                "label": "Verifier tool",
                "href": "https://github.com/arigatoexpress/Sapphire/blob/main/plugins/claw-sapphire/tools/og_verify.py",
            },
        ],
        "verify_command": (
            f"echo '{{\"signal_id\": {signal_id}}}' | python3 plugins/claw-sapphire/tools/og_verify.py"
            if signal_id
            else "echo '{\"signal_id\": 0}' | python3 plugins/claw-sapphire/tools/og_verify.py"
        ),
        "safety_boundaries": [
            "Public page is read-only",
            "No private key or secret environment values are read",
            "No 0G writes, trades, Telegram sends, or money movement",
            "Mainnet proof remains explicitly pending until public tx/rootHash are recorded",
        ],
    }
