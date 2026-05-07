"""Tests for the read-only Sapphire system failover checker."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "ops" / "system_failover_status.py"
MODULE_NAME = "system_failover_status_under_test"


def _load_module():
    spec = importlib.util.spec_from_file_location(MODULE_NAME, SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


def test_windows_offline_with_mac_fallback_is_operational_degraded():
    mod = _load_module()
    proxy = {
        "status": "degraded",
        "mode": "local_failover",
        "active_route": "mac-local",
        "fallback_ready": True,
        "windows_offline": True,
        "endpoints": {
            "windows-gpu": "failed",
            "pi-rari1": "disabled",
            "pi-rari2": "disabled",
            "mac-local": "healthy",
            "kimi-cloud": "healthy",
        },
    }

    report = mod.build_report(
        proxy=proxy,
        proxy_warnings=[],
        cloud_run=None,
        require_primary=False,
    )

    assert report["ok"] is True
    assert report["mode"] == "local_failover"
    assert report["windows_offline"] is True
    assert report["blockers"] == []


def test_require_primary_fails_when_windows_is_offline():
    mod = _load_module()
    proxy = {
        "status": "degraded",
        "mode": "local_failover",
        "active_route": "mac-local",
        "fallback_ready": True,
        "windows_offline": True,
        "endpoints": {"windows-gpu": "failed", "mac-local": "healthy"},
    }

    report = mod.build_report(
        proxy=proxy,
        proxy_warnings=[],
        cloud_run=None,
        require_primary=True,
    )

    assert report["ok"] is False
    assert report["blockers"] == ["primary Windows GPU tier is required but not healthy"]


def test_legacy_health_payload_is_promoted_to_failover_contract():
    mod = _load_module()
    payload = {
        "service": "inference-proxy",
        "endpoints": {
            "windows-gpu": "failed",
            "pi-rari1": "disabled",
            "pi-rari2": "disabled",
            "mac-local": "healthy",
            "kimi-cloud": "healthy",
        },
    }

    failover = mod._fallback_payload_from_health(payload)

    assert failover["mode"] == "local_failover"
    assert failover["active_route"] == "mac-local"
    assert failover["fallback_ready"] is True


def test_cloud_run_summary_surfaces_missing_required_services():
    mod = _load_module()
    services = [
        mod.CloudRunService(
            name="sapphire-analytics",
            ready=True,
            latest_ready_revision="sapphire-analytics-00044-5hz",
            url="https://example.invalid",
        )
    ]

    summary = mod.summarize_cloud_run(
        services,
        required=("sapphire-analytics", "sapphire-os-terminal"),
    )

    assert summary["ok"] is False
    assert summary["ready_count"] == 1
    assert summary["missing"] == ["sapphire-os-terminal"]
    assert summary["not_ready"] == []
