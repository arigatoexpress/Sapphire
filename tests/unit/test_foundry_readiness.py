"""Unit tests for Foundry readiness and schema audit helpers."""

from __future__ import annotations

import json
from hashlib import sha256

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
    regional_rows = {
        "Region": [
            {
                "object_id": "regional-intel:region:austin_tx",
                "region_id": "austin_tx",
                "name": "Austin, TX",
                "summary": "Expansion and civic signals.",
                "snapshot_updated_at": "2026-04-26T08:05:00Z",
            }
        ],
        "IntelItem": [
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
        ],
        "IntelSourceHealth": [
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
        ],
    }
    object_types = {}
    for object_type, rows in regional_rows.items():
        content = "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
        filename = f"{object_type}.ndjson"
        (regional_dir / filename).write_text(content)
        object_types[object_type] = {
            "filename": filename,
            "rows": len(rows),
            "file_sha256": sha256(content.encode()).hexdigest(),
            "row_hashes": [
                sha256(json.dumps(row, sort_keys=True).encode()).hexdigest() for row in rows
            ],
        }
    (regional_dir / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "generated_at": "2026-04-26T08:05:01Z",
                "snapshot_updated_at": "2026-04-26T08:05:00Z",
                "region": "austin_tx",
                "object_types": object_types,
                "dropped_rows": {"total": 0, "by_reason": {}, "details": []},
                "source_health_summary": {
                    "total_sources": 1,
                    "live_pull_sources": 1,
                    "total_item_count": 1,
                    "by_status": {"live": 1},
                    "by_category": {"news": 1},
                    "by_region": {"austin_tx": 1},
                },
                "policy": {"public_sources_only": True, "safe_use": "review_only"},
            }
        )
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
    # 0.2.0: 8 baseline types + 5 new (IntelVectorRecord, TelegramIntelMessage,
    # HyperliquidSignal, OODAPacket, ThreatIndicator). The fixture exercises
    # ThreatIndicator (it shares threats.json with ThreatIntel), so the object
    # count goes up by exactly one. The other four new types have no fixture
    # data and contribute zero objects.
    assert audit["totals"]["object_types"] == 13
    # Tranche 5 fixture-paths now seed every Tranche-4-expansion object type
    # (IntelVectorRecord, TelegramIntelMessage, HyperliquidSignal, OODAPacket,
    # ThreatIndicator) into the readiness audit, so each contributes a sourced
    # object beyond the 8 baseline types.
    assert audit["totals"]["objects"] == 13
    assert audit["totals"]["missing_required_fields"] == 0
    assert audit["totals"]["source_refs"] == 13
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
    manifest = audit["regional_manifest"]
    assert manifest["status"] == "ready"
    assert manifest["schema_version"] == 2
    assert manifest["object_types"]["Region"]["file_sha256_matches"] is True
    assert manifest["dropped_rows"]["total"] == 0


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


def test_regional_manifest_absent_is_safe_when_runtime_data_absent(tmp_path):
    audit = build_foundry_schema_audit(tmp_path)

    manifest = audit["regional_manifest"]
    assert manifest["status"] == "absent"
    assert manifest["exists"] is False
    assert manifest["errors"] == []


def test_regional_manifest_reports_paste_safe_dropped_row_counts(tmp_path):
    regional_dir = tmp_path / "data" / "foundry" / "regional-intel"
    regional_dir.mkdir(parents=True)
    for object_type in ("Region", "IntelItem", "IntelSourceHealth"):
        (regional_dir / f"{object_type}.ndjson").write_text("")

    empty_sha = sha256(b"").hexdigest()
    (regional_dir / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "generated_at": "2026-04-26T08:05:01Z",
                "snapshot_updated_at": "2026-04-26T08:05:00Z",
                "region": "austin_tx",
                "object_types": {
                    object_type: {
                        "filename": f"{object_type}.ndjson",
                        "rows": 0,
                        "file_sha256": empty_sha,
                        "row_hashes": [],
                    }
                    for object_type in ("Region", "IntelItem", "IntelSourceHealth")
                },
                "dropped_rows": {
                    "total": 2,
                    "by_reason": {"missing_required_fields": 2},
                    "details": [
                        {
                            "reason": "missing_required_fields",
                            "object_type": "IntelItem",
                            "kind": "permit",
                            "item_id": "sensitive-source-row-1",
                            "region_id": "austin_tx",
                            "missing_fields": ["source_url", "title"],
                        },
                        {
                            "reason": "missing_required_fields",
                            "object_type": "IntelItem",
                            "kind": "news",
                            "item_id": "sensitive-source-row-2",
                            "region_id": "austin_tx",
                            "missing_fields": ["source_url"],
                        },
                    ],
                },
                "source_health_summary": {
                    "total_sources": 1,
                    "live_pull_sources": 0,
                    "total_item_count": 0,
                    "by_status": {"manual": 1},
                    "by_category": {"permit": 1},
                    "by_region": {"austin_tx": 1},
                },
                "policy": {"public_sources_only": True},
            }
        )
    )

    manifest = build_foundry_schema_audit(tmp_path)["regional_manifest"]

    assert manifest["status"] == "ready"
    assert manifest["dropped_rows"] == {
        "total": 2,
        "by_reason": {"missing_required_fields": 2},
        "by_object_type": {"IntelItem": 2},
        "by_kind": {"news": 1, "permit": 1},
        "missing_fields": {"source_url": 2, "title": 1},
        "details": 2,
    }
    assert "sensitive-source-row-1" not in json.dumps(manifest)


def test_regional_manifest_malformed_count_buckets_warn_without_crashing(tmp_path):
    regional_dir = tmp_path / "data" / "foundry" / "regional-intel"
    regional_dir.mkdir(parents=True)
    for object_type in ("Region", "IntelItem", "IntelSourceHealth"):
        (regional_dir / f"{object_type}.ndjson").write_text("")

    empty_sha = sha256(b"").hexdigest()
    (regional_dir / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "generated_at": "2026-04-26T08:05:01Z",
                "snapshot_updated_at": "2026-04-26T08:05:00Z",
                "region": "austin_tx",
                "object_types": {
                    object_type: {
                        "filename": f"{object_type}.ndjson",
                        "rows": 0,
                        "file_sha256": empty_sha,
                        "row_hashes": [],
                    }
                    for object_type in ("Region", "IntelItem", "IntelSourceHealth")
                },
                "dropped_rows": {
                    "total": 1,
                    "by_reason": {"missing_required_fields": "two"},
                    "details": [
                        {
                            "reason": "missing_required_fields",
                            "object_type": "IntelItem",
                            "kind": "news",
                            "item_id": "row-id-is-not-exposed",
                            "region_id": "austin_tx",
                            "missing_fields": "source_url",
                        }
                    ],
                },
                "source_health_summary": {
                    "total_sources": "one",
                    "live_pull_sources": 0,
                    "total_item_count": 0,
                    "by_status": [],
                    "by_category": {},
                    "by_region": {},
                },
                "policy": {"public_sources_only": True},
            }
        )
    )

    manifest = build_foundry_schema_audit(tmp_path)["regional_manifest"]

    assert manifest["status"] == "schema_warning"
    assert "dropped_rows.by_reason.invalid_count:missing_required_fields" in manifest["errors"]
    assert "dropped_rows.detail_missing_fields_not_list" in manifest["errors"]
    assert "source_health_summary.invalid_count:total_sources" in manifest["errors"]
    assert "source_health_summary.invalid_bucket:by_status" in manifest["errors"]
    assert "row-id-is-not-exposed" not in json.dumps(manifest)


def test_readiness_embeds_schema_audit(tmp_path):
    _write_foundry_fixture(tmp_path)

    readiness = build_foundry_readiness(tmp_path)

    assert readiness["schema_audit"]["status"] == "ready"
    # 0.2.0+ post-Tranche-5: each Tranche-4-expansion object type contributes
    # a sourced entry from its respective fixture (8 baseline + 5 expansion).
    assert readiness["schema_audit"]["totals"]["objects"] == 13
    regional_group = next(
        group for group in readiness["dataset_groups"] if group["id"] == "regional-intel"
    )
    assert regional_group["status"] == "ready"
    assert regional_group["files"] == 4
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
                        "ip": "100.x.x.w",
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
