"""Unit tests for Foundry readiness and schema audit helpers."""

from __future__ import annotations

import json

from lib.foundry.readiness import (
    build_foundry_readiness,
    build_foundry_schema_audit,
)


def _write_foundry_fixture(root):
    data_dir = root / "data"
    signals_dir = data_dir / "signals"
    health_dir = data_dir / "health"
    intel_dir = data_dir / "intelligence" / "2026-04-26"
    signals_dir.mkdir(parents=True)
    health_dir.mkdir(parents=True)
    intel_dir.mkdir(parents=True)

    (signals_dir / "2026-04-26.jsonl").write_text(
        json.dumps(
            {
                "pipeline_id": "trade-1",
                "timestamp": "2026-04-26T08:00:00Z",
                "symbol": "BTC",
                "direction": "long",
                "action": "buy",
            }
        )
        + "\n"
    )
    (data_dir / "system_events.jsonl").write_text(
        json.dumps(
            {
                "type": "alert",
                "timestamp": "2026-04-26T08:01:00Z",
                "message": "test alert",
                "service": "dashboard",
            }
        )
        + "\n"
    )
    (health_dir / "2026-04-26.ndjson").write_text(
        json.dumps(
            {
                "service": "dashboard",
                "status": "healthy",
                "timestamp": "2026-04-26T08:02:00Z",
            }
        )
        + "\n"
    )
    (intel_dir / "threats.json").write_text(
        json.dumps(
            {
                "threats": [
                    {
                        "id": "threat-1",
                        "title": "Unit test threat",
                        "source": "unit-test",
                        "published": "2026-04-26T08:03:00Z",
                    }
                ]
            }
        )
    )
    (intel_dir / "daily_brief.json").write_text(
        json.dumps(
            {
                "id": "brief-1",
                "title": "Daily Brief",
                "summary": "All systems nominal.",
                "generated_at": "2026-04-26T08:04:00Z",
            }
        )
    )
    regional_dir = data_dir / "foundry" / "regional-intel"
    regional_dir.mkdir(parents=True)
    (regional_dir / "Region.ndjson").write_text(
        json.dumps(
            {
                "object_id": "regional-intel:region:austin_tx",
                "region_id": "austin_tx",
                "name": "Austin, TX",
                "summary": "Expansion and civic signals.",
                "snapshot_updated_at": "2026-04-26T08:05:00Z",
            }
        )
        + "\n"
    )
    (regional_dir / "IntelItem.ndjson").write_text(
        json.dumps(
            {
                "object_id": "regional-intel:item:news:item-1",
                "item_id": "item-1",
                "kind": "news",
                "region_id": "austin_tx",
                "title": "Venue permit",
                "summary": "New venue permit signal.",
                "score": 0.8,
                "source_name": "Austin Monitor",
                "source_url": "https://example.test/permit",
                "observed_at": "2026-04-26T08:05:00Z",
                "snapshot_updated_at": "2026-04-26T08:05:00Z",
            }
        )
        + "\n"
    )
    (regional_dir / "IntelSourceHealth.ndjson").write_text(
        json.dumps(
            {
                "object_id": "regional-intel:source:austin-monitor",
                "source_key": "austin-monitor",
                "name": "Austin Monitor",
                "category": "news",
                "region_ids": ["austin_tx"],
                "live_pull": True,
                "status": "live",
                "item_count": 1,
                "last_seen_at": "2026-04-26T08:05:00Z",
                "snapshot_updated_at": "2026-04-26T08:05:00Z",
            }
        )
        + "\n"
    )


def test_schema_audit_reports_required_field_health_and_history_readback(tmp_path):
    _write_foundry_fixture(tmp_path)
    history_path = tmp_path / "data" / "foundry_sync_history.jsonl"
    history_path.write_text(
        json.dumps(
            {
                "ok": True,
                "timestamp": "2026-04-26T08:05:00Z",
                "duration_s": 0.12,
                "changed_types": {"PaperTrade": 1},
                "uploaded_types": {"PaperTrade": 1},
                "dry_run": False,
                "skipped": False,
            }
        )
        + "\nnot-json\n"
        + json.dumps(
            {
                "ok": False,
                "timestamp": "2026-04-26T08:06:00Z",
                "duration_s": 0.2,
                "changed_types": {"Alert": 1},
                "uploaded_types": {},
                "dry_run": True,
                "skipped": False,
            }
        )
        + "\n"
    )

    audit = build_foundry_schema_audit(tmp_path)

    assert audit["status"] == "ready"
    assert audit["totals"]["object_types"] == 8
    assert audit["totals"]["objects"] == 8
    assert audit["totals"]["missing_required_fields"] == 0
    assert audit["totals"]["source_refs"] == 8
    object_types = {item["object_type"]: item for item in audit["object_types"]}
    assert object_types["PaperTrade"]["required_fields"] == [
        "id",
        "symbol",
        "direction",
        "action",
        "opened_at",
    ]
    assert object_types["ThreatIntel"]["status"] == "ready"
    assert object_types["Region"]["status"] == "ready"
    assert object_types["IntelItem"]["required_fields"] == [
        "object_id",
        "item_id",
        "kind",
        "region_id",
        "title",
        "source_name",
        "source_url",
        "snapshot_updated_at",
    ]

    history = audit["sync_history_readback"]
    assert history["records"] == 2
    assert history["malformed_lines"] == 1
    assert history["recent_error_runs"] == 1
    assert history["latest_ok"] is False
    assert history["latest_dry_run"] is True
    assert history["latest_changed_types"] == 1


def test_schema_audit_warns_on_missing_required_fields(tmp_path):
    signals_dir = tmp_path / "data" / "signals"
    signals_dir.mkdir(parents=True)
    (signals_dir / "2026-04-26.jsonl").write_text(
        json.dumps(
            {
                "pipeline_id": "trade-1",
                "symbol": "ETH",
                "direction": "short",
                "action": "sell",
            }
        )
        + "\n"
    )

    audit = build_foundry_schema_audit(tmp_path)

    assert audit["status"] == "schema_warning"
    paper_trade = next(
        item for item in audit["object_types"] if item["object_type"] == "PaperTrade"
    )
    assert paper_trade["status"] == "schema_warning"
    assert paper_trade["missing_required_fields"] == {"opened_at": 1}


def test_readiness_embeds_schema_audit(tmp_path):
    _write_foundry_fixture(tmp_path)

    readiness = build_foundry_readiness(tmp_path)

    assert readiness["schema_audit"]["status"] == "ready"
    assert readiness["schema_audit"]["totals"]["objects"] == 8
    regional_group = next(
        group for group in readiness["dataset_groups"] if group["id"] == "regional-intel"
    )
    assert regional_group["status"] == "ready"
    assert regional_group["files"] == 3
    assert readiness["docs"]["ontology_schema"] == "docs/foundry-ontology-schema.md"


def test_schema_audit_accepts_topology_service_health_last_check_fallback(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True)
    (data_dir / "device_topology.json").write_text(
        json.dumps(
            {
                "devices": [
                    {
                        "name": "mac",
                        "ip": "100.67.171.79",
                        "services": ["dashboard", "proxy"],
                    }
                ]
            }
        )
    )

    audit = build_foundry_schema_audit(tmp_path)

    service_health = next(
        item for item in audit["object_types"] if item["object_type"] == "ServiceHealth"
    )
    assert service_health["status"] == "ready"
    assert service_health["missing_required_fields"] == {}
    assert audit["totals"]["missing_required_fields"] == 0
