"""Contract tests for the Windows WSL MegaETH observer package."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEPLOY_DIR = ROOT / "deploy" / "megaeth-ingest-wsl"
UNIT_PATH = DEPLOY_DIR / "sapphire-megaeth-ingest.service"
MANIFEST_PATH = DEPLOY_DIR / "deployment-manifest.json"


def test_systemd_unit_is_manual_read_only_and_fail_closed() -> None:
    unit = UNIT_PATH.read_text()

    required_lines = {
        "Type=simple",
        "User=sapphire",
        "WorkingDirectory=/opt/sapphire/Sapphire",
        "ConditionPathExists=/var/lib/sapphire/megaeth-ingest/pause",
        (
            "Environment=PYTHONPATH=/opt/sapphire/Sapphire/"
            "services/megaeth-ingest/src:/opt/sapphire/Sapphire"
        ),
        "Environment=SAPPHIRE_MEGAETH_RPC_URL=https://mainnet.megaeth.com/rpc",
        "Environment=SAPPHIRE_MEGAETH_CHAIN_ID=4326",
        "Environment=SAPPHIRE_MEGAETH_WSS_REQUIRED=0",
        "Environment=SAPPHIRE_MEGAETH_HEALTH_PORT=8788",
        "Environment=SAPPHIRE_MEGAETH_INGEST_ENABLED=0",
        ("Environment=SAPPHIRE_MEGAETH_KILLSWITCH=/var/lib/sapphire/megaeth-ingest/pause"),
        "ExecStart=/opt/sapphire/Sapphire/.venv/bin/python -m megaeth_ingest.main",
        "Restart=no",
        "NoNewPrivileges=true",
        "PrivateTmp=true",
        "ProtectSystem=strict",
        "ProtectHome=true",
    }
    for line in required_lines:
        assert line in unit

    forbidden = (
        "[Install]",
        "WEBHOOK_SECRET",
        "PRIVATE_KEY",
        "MNEMONIC",
        "WALLET",
        "TELEGRAM",
        "EXECUTOR",
        "SAPPHIRE_MEGAETH_INGEST_ENABLED=1",
        "Restart=always",
    )
    for token in forbidden:
        assert token not in unit


def test_deployment_manifest_records_operator_and_capability_boundaries() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text())

    assert manifest["schema"] == "sapphire/megaeth-wsl-observer-deployment/v1"
    assert manifest["chain"]["name"] == "MegaETH mainnet"
    assert manifest["chain"]["chain_id"] == 4326
    assert manifest["chain"]["rpc_url"] == "https://mainnet.megaeth.com/rpc"
    assert manifest["runtime"]["install_state"] == "source_only_not_installed"
    assert manifest["runtime"]["start_mode"] == "manual"
    assert manifest["runtime"]["operator_gate_required"] is True
    assert manifest["capabilities"] == {
        "rpc_reads": True,
        "transaction_signing": False,
        "wallets_loaded": 0,
        "signal_forwarding": False,
        "trade_execution": False,
        "outward_messaging": False,
    }
    assert manifest["safety"]["pause_file_required"] is True
    assert manifest["safety"]["systemd_enablement_allowed"] is False
