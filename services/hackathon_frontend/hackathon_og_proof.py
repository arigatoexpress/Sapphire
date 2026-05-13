"""0G proof/readiness helpers for the standalone hackathon frontend.

This service is deployed from `services/hackathon_frontend` as an isolated
Cloud Run source directory, so the helper is intentionally self-contained. It
only reports public artifacts and source-readiness fields; it never reads key
material and never performs network writes.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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


def _candidate_repo_roots() -> list[Path]:
    here = Path(__file__).resolve()
    roots: list[Path] = [here.parent]
    for parent in here.parents:
        roots.append(parent)
    return roots


def _find_deployments_file() -> Path | None:
    explicit = os.environ.get(ENV_DEPLOYMENTS_FILE, "").strip()
    if explicit:
        path = Path(explicit)
        if path.exists():
            return path
    for root in _candidate_repo_roots():
        candidate = root / "data" / "chain" / "deployments.json"
        if candidate.exists():
            return candidate
    return None


def _load_deployments() -> dict[str, Any]:
    path = _find_deployments_file()
    if path is None:
        return {}
    try:
        loaded = json.loads(path.read_text())
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


def _row(id_: str, label: str, ok: bool, evidence: str, next_step: str = "") -> dict:
    return {
        "id": id_,
        "label": label,
        "ok": bool(ok),
        "status": "ready" if ok else "pending",
        "evidence": evidence,
        "next_step": next_step,
    }


def _repo_file_exists(relative_path: str) -> bool:
    return any((root / relative_path).exists() for root in _candidate_repo_roots())


def build_og_readiness(*, now: datetime | None = None) -> dict[str, Any]:
    ts = (now or datetime.now(UTC)).isoformat()
    deployments = _load_deployments()
    mainnet_contract = _contract_entry(deployments, "mainnet")
    testnet_contract = _contract_entry(deployments, "testnet")

    contract_address = _env(ENV_CONTRACT_ADDRESS) or mainnet_contract.get("address")
    signal_tx = _env(ENV_SIGNAL_TX) or mainnet_contract.get("sample_signal_tx")
    signal_id = _env(ENV_SIGNAL_ID) or mainnet_contract.get("sample_signal_id")
    storage_root = _env(ENV_STORAGE_ROOT) or mainnet_contract.get("sample_storage_root")
    storage_proof_url = _env(ENV_STORAGE_PROOF_URL) or mainnet_contract.get("storage_proof_url")

    readiness = [
        _row(
            "source_docs",
            "Judge docs",
            _repo_file_exists("docs/hackathon-0g/README.md") or _repo_file_exists("README.md"),
            "docs/hackathon-0g/README.md",
        ),
        _row(
            "mainnet_contract",
            "0G mainnet contract",
            bool(contract_address),
            contract_address or "No public 0G mainnet address recorded in this deploy",
            "Deploy SapphireSignalVerifier on 0G mainnet and record the public address",
        ),
        _row(
            "testnet_contract",
            "0G testnet fallback",
            bool(testnet_contract.get("address")),
            testnet_contract.get("address") or "No testnet address found in deployments.json",
        ),
        _row(
            "signal_event",
            "SignalPublished event",
            bool(signal_tx or signal_id),
            signal_tx
            or (f"signal_id={signal_id}" if signal_id else "No sample event recorded yet"),
            "Publish one labeled hackathon sample signal and record tx/id",
        ),
        _row(
            "storage_root",
            "0G Storage root",
            bool(storage_root),
            storage_root or "No sample rootHash recorded yet",
            "Record the rootHash returned by og_publish",
        ),
    ]

    live_proof_ready = bool(contract_address and (signal_tx or signal_id) and storage_root)
    return {
        "ok": True,
        "status": "live-proof-ready" if live_proof_ready else "source-ready-live-proof-pending",
        "status_label": "LIVE PROOF READY"
        if live_proof_ready
        else "SOURCE READY / LIVE PROOF PENDING",
        "generated_at": ts,
        "networks": {
            "mainnet": {"chain_id": MAINNET_CHAIN_ID, "explorer": MAINNET_EXPLORER},
            "testnet": {"chain_id": TESTNET_CHAIN_ID, "explorer": TESTNET_EXPLORER},
        },
        "public_artifacts": {
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
        },
        "readiness": readiness,
        "safety": {
            "secrets_exposed": False,
            "chain_writes_enabled": False,
            "telegram_sends_enabled": False,
            "trading_execution_enabled": False,
            "notes": [
                "This endpoint is read-only.",
                "No private keys or secret environment variables are returned.",
                "No 0G writes, trades, Telegram sends, or money movement are triggered.",
            ],
        },
        "verify_command": (
            f"echo '{{\"signal_id\": {signal_id}}}' | python3 plugins/claw-sapphire/tools/og_verify.py"
            if signal_id
            else "echo '{\"signal_id\": 0}' | python3 plugins/claw-sapphire/tools/og_verify.py"
        ),
    }


def build_og_feed() -> dict[str, Any]:
    readiness = build_og_readiness()
    artifacts = readiness["public_artifacts"]
    return {
        "ok": True,
        "status": readiness["status"],
        "items": [
            {
                "stage": "0G Compute",
                "state": "source-ready",
                "proof": "TEE chatID carried in the Sapphire signal envelope",
                "href": "https://github.com/arigatoexpress/Sapphire/blob/main/lib/og/compute.py",
            },
            {
                "stage": "0G Storage",
                "state": "live-proof-ready"
                if artifacts.get("storage_root_hash")
                else "sample-pending",
                "proof": artifacts.get("storage_root_hash") or "rootHash pending",
                "href": artifacts.get("storage_proof_url"),
            },
            {
                "stage": "0G Chain",
                "state": "live-proof-ready"
                if artifacts.get("sample_signal_tx")
                else "sample-pending",
                "proof": artifacts.get("sample_signal_tx") or "SignalPublished tx pending",
                "href": artifacts.get("sample_signal_tx_url")
                or artifacts.get("contract_explorer_url"),
            },
            {
                "stage": "Read-only replay",
                "state": "source-ready",
                "proof": readiness["verify_command"],
                "href": "https://github.com/arigatoexpress/Sapphire/blob/main/plugins/claw-sapphire/tools/og_verify.py",
            },
        ],
    }
