"""Tests for the standalone public hackathon frontend's 0G proof surface."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP_PATH = ROOT / "services" / "hackathon_frontend" / "app.py"


def _load_app(monkeypatch, deployments: dict | None = None, tmp_path: Path | None = None):
    svc_dir = APP_PATH.parent
    monkeypatch.syspath_prepend(str(svc_dir))
    for name in ("hackathon_frontend_app_test", "hackathon_og_proof"):
        sys.modules.pop(name, None)

    if deployments is not None:
        # Use a temp deployments file rather than creating residue in the
        # service source directory.
        assert tmp_path is not None
        deploy_file = tmp_path / "deployments.json"
        deploy_file.parent.mkdir(parents=True, exist_ok=True)
        deploy_file.write_text(json.dumps(deployments))
        monkeypatch.setenv("SAPPHIRE_DEPLOYMENTS_FILE", str(deploy_file))

    spec = importlib.util.spec_from_file_location("hackathon_frontend_app_test", APP_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["hackathon_frontend_app_test"] = module
    spec.loader.exec_module(module)
    return module.app.test_client()


def test_0g_readiness_endpoint_is_public_safe(monkeypatch):
    monkeypatch.setenv("OG_PRIVATE_KEY", "0x" + "ab" * 32)
    client = _load_app(monkeypatch)

    resp = client.get("/api/0g/readiness")

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["networks"]["mainnet"]["chain_id"] == 16661
    assert payload["safety"]["secrets_exposed"] is False
    assert payload["safety"]["chain_writes_enabled"] is False
    encoded = json.dumps(payload)
    assert "OG_PRIVATE_KEY" not in encoded
    assert "ab" * 32 not in encoded


def test_0g_feed_endpoint_lists_verifier_path(monkeypatch):
    client = _load_app(monkeypatch)

    resp = client.get("/api/0g/feed")

    assert resp.status_code == 200
    payload = resp.get_json()
    stages = [item["stage"] for item in payload["items"]]
    assert stages == ["0G Compute", "0G Storage", "0G Chain", "Read-only replay"]
    assert "og_verify.py" in json.dumps(payload)


def test_index_renders_0g_proof_tab(monkeypatch):
    client = _load_app(monkeypatch)

    resp = client.get("/")

    assert resp.status_code == 200
    body = resp.data.decode("utf-8")
    assert "0G proof" in body
    assert "/api/0g/readiness" in body or "og-proof-panel" in body


def test_llms_txt_serves_hackathon_agent_context(monkeypatch):
    client = _load_app(monkeypatch)

    resp = client.get("/llms.txt")
    body = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert resp.mimetype == "text/plain"
    assert resp.headers["Cache-Control"] == "public, max-age=3600"
    assert "# Sapphire OS Hackathon Shelf" in body
    assert "https://hack.sapphirealpha.xyz/" in body
    assert "No public Hackathon Shelf route authorizes private-key access" in body


def test_testnet_deployment_hydrates_0g_card_when_mainnet_missing(monkeypatch, tmp_path):
    deployments = {
        "og_testnet": {
            "contracts": {
                "SapphireSignalVerifier": {
                    "address": "0x" + "12" * 20,
                }
            }
        }
    }
    client = _load_app(monkeypatch, deployments=deployments, tmp_path=tmp_path)

    submissions = client.get("/api/submissions").get_json()["submissions"]
    og = next(item for item in submissions if item["slug"] == "0g")
    contract = og["contracts"][0]

    assert contract["address"] == "0x" + "12" * 20
    assert "testnet fallback" in contract["network"]
    assert "chainscan-galileo.0g.ai" in contract["explorer_url"]
