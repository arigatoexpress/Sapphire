"""Tests for the public-safe 0G hackathon proof manifest."""

from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "services" / "analytics_dashboard" / "og_proof.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("analytics_og_proof", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_manifest_marks_live_proof_ready_from_public_env(monkeypatch):
    mod = _load_module()
    monkeypatch.setenv(mod.ENV_CONTRACT_ADDRESS, "0x" + "11" * 20)
    monkeypatch.setenv(mod.ENV_SIGNAL_TX, "0x" + "22" * 32)
    monkeypatch.setenv(mod.ENV_STORAGE_ROOT, "0x" + "33" * 32)

    payload = mod.build_og_proof_manifest(now=datetime(2026, 5, 13, tzinfo=UTC))

    assert payload["status"] == "live-proof-ready"
    assert payload["public_artifacts"]["contract_explorer_url"].endswith("/address/0x" + "11" * 20)
    assert payload["public_artifacts"]["sample_signal_tx_url"].endswith("/tx/0x" + "22" * 32)
    assert payload["public_artifacts"]["storage_root_hash"] == "0x" + "33" * 32


def test_manifest_reads_deployment_file_without_network(monkeypatch, tmp_path):
    mod = _load_module()
    root = tmp_path / "repo"
    (root / "data" / "chain").mkdir(parents=True)
    (root / "data" / "chain" / "deployments.json").write_text(
        json.dumps(
            {
                "og_mainnet": {
                    "contracts": {
                        "SapphireSignalVerifier": {
                            "address": "0x" + "44" * 20,
                            "sample_signal_id": 7,
                            "sample_signal_tx": "0x" + "55" * 32,
                            "sample_storage_root": "0x" + "66" * 32,
                        }
                    }
                }
            }
        )
    )
    monkeypatch.setattr(mod, "REPO_ROOT", root)
    monkeypatch.setattr(mod, "DEPLOYMENTS_FILE", root / "data" / "chain" / "deployments.json")

    payload = mod.build_og_proof_manifest(now=datetime(2026, 5, 13, tzinfo=UTC))

    assert payload["status"] == "live-proof-ready"
    assert payload["public_artifacts"]["contract_address"] == "0x" + "44" * 20
    assert payload["public_artifacts"]["sample_signal_id"] == 7
    assert payload["verify_command"] == (
        "echo '{\"signal_id\": 7}' | python3 plugins/claw-sapphire/tools/og_verify.py"
    )


def test_manifest_never_leaks_private_key_env(monkeypatch):
    mod = _load_module()
    secret = "0x" + "ab" * 32
    monkeypatch.setenv("OG_PRIVATE_KEY", secret)

    payload = mod.build_og_proof_manifest(now=datetime(2026, 5, 13, tzinfo=UTC))
    encoded = json.dumps(payload)

    assert "OG_PRIVATE_KEY" not in encoded
    assert secret not in encoded


def test_repo_root_inference_handles_flat_cloud_run_layout(monkeypatch, tmp_path):
    mod = _load_module()
    flat_module = tmp_path / "app" / "og_proof.py"
    flat_module.parent.mkdir()
    flat_module.touch()

    monkeypatch.setattr(mod, "__file__", str(flat_module))

    assert mod._infer_repo_root() == flat_module.parent
