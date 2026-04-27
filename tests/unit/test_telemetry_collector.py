"""Tests for service telemetry collector routing."""

from __future__ import annotations

from services.pipeline.telemetry_collector import SERVICES


def test_regional_intel_probe_uses_app_health_endpoint() -> None:
    regional = next(service for service in SERVICES if service[0] == "regional-intel")

    assert regional == ("regional-intel", "mac", "127.0.0.1", 8787, "/api/health")
