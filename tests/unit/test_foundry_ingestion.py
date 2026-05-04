"""Unit tests for lib.foundry.ingestion."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from lib.foundry.ingestion import (
    _deterministic_id,
    _iso,
    _load_json,
    _load_jsonl,
    transform_alerts,
    transform_all,
    transform_daily_briefs,
    transform_intel_items,
    transform_intel_source_health,
    transform_paper_trades,
    transform_regions,
    transform_service_health,
    transform_threat_intel,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class TestDeterministicId:
    def test_same_input_same_output(self):
        a = _deterministic_id("BTC", "2026-04-19", "ema_cross")
        b = _deterministic_id("BTC", "2026-04-19", "ema_cross")
        assert a == b
        assert len(a) == 16

    def test_different_input_different_output(self):
        a = _deterministic_id("BTC", "2026-04-19")
        b = _deterministic_id("ETH", "2026-04-19")
        assert a != b


class TestIso:
    def test_none(self):
        assert _iso(None) is None

    def test_empty_string(self):
        assert _iso("") is None

    def test_datetime(self):
        dt = datetime(2026, 4, 19, 12, 0, tzinfo=UTC)
        assert "2026-04-19" in _iso(dt)

    def test_passthrough_string(self):
        assert _iso("2026-04-19T00:00:00Z") == "2026-04-19T00:00:00Z"


class TestLoadJsonl:
    def test_valid_jsonl(self, tmp_path):
        f = tmp_path / "test.jsonl"
        f.write_text('{"a":1}\n{"b":2}\n')
        rows = _load_jsonl(f)
        assert len(rows) == 2
        assert rows[0]["a"] == 1

    def test_max_lines(self, tmp_path):
        f = tmp_path / "test.jsonl"
        lines = "\n".join(json.dumps({"i": i}) for i in range(100))
        f.write_text(lines)
        rows = _load_jsonl(f, max_lines=10)
        assert len(rows) == 10

    def test_invalid_lines_skipped(self, tmp_path):
        f = tmp_path / "test.jsonl"
        f.write_text('{"a":1}\nnot json\n{"b":2}\n')
        rows = _load_jsonl(f)
        assert len(rows) == 2

    def test_missing_file(self, tmp_path):
        f = tmp_path / "nope.jsonl"
        assert _load_jsonl(f) == []


class TestLoadJson:
    def test_valid(self, tmp_path):
        f = tmp_path / "test.json"
        f.write_text('{"key": "val"}')
        assert _load_json(f) == {"key": "val"}

    def test_missing(self, tmp_path):
        assert _load_json(tmp_path / "nope.json") == {}


# ---------------------------------------------------------------------------
# PaperTrade transform
# ---------------------------------------------------------------------------


class TestTransformPaperTrades:
    def test_basic(self, tmp_path):
        signals_dir = tmp_path / "data" / "signals"
        signals_dir.mkdir(parents=True)
        row = {
            "pipeline_id": "abc123",
            "timestamp": "2026-04-19T10:00:00Z",
            "symbol": "BTC",
            "direction": "long",
            "action": "buy",
            "strategy": "ema_cross",
            "price": 65000.0,
            "confidence": 0.82,
            "score": 86.8,
            "source": "webhook",
        }
        (signals_dir / "2026-04-19.jsonl").write_text(json.dumps(row) + "\n")

        trades = transform_paper_trades(tmp_path)
        assert len(trades) == 1
        t = trades[0]
        assert t["id"] == "abc123"
        assert t["symbol"] == "BTC"
        assert t["direction"] == "long"
        assert t["entry_price"] == 65000.0
        assert t["_sapphire_source"].replace("\\", "/") == "data/signals/2026-04-19.jsonl"

    def test_empty_dir(self, tmp_path):
        (tmp_path / "data" / "signals").mkdir(parents=True)
        assert transform_paper_trades(tmp_path) == []

    def test_no_dir(self, tmp_path):
        assert transform_paper_trades(tmp_path) == []

    def test_since_filter(self, tmp_path):
        signals_dir = tmp_path / "data" / "signals"
        signals_dir.mkdir(parents=True)
        (signals_dir / "2026-04-10.jsonl").write_text(
            json.dumps({"pipeline_id": "old", "timestamp": "2026-04-10T00:00:00Z", "symbol": "BTC"})
            + "\n"
        )
        (signals_dir / "2026-04-19.jsonl").write_text(
            json.dumps({"pipeline_id": "new", "timestamp": "2026-04-19T00:00:00Z", "symbol": "ETH"})
            + "\n"
        )

        since = datetime(2026, 4, 15, tzinfo=UTC)
        trades = transform_paper_trades(tmp_path, since=since)
        assert len(trades) == 1
        assert trades[0]["id"] == "new"

    def test_deterministic_id_fallback(self, tmp_path):
        signals_dir = tmp_path / "data" / "signals"
        signals_dir.mkdir(parents=True)
        row = {"timestamp": "2026-04-19T10:00:00Z", "symbol": "SOL", "strategy": "test"}
        (signals_dir / "2026-04-19.jsonl").write_text(json.dumps(row) + "\n")

        trades = transform_paper_trades(tmp_path)
        assert len(trades) == 1
        assert len(trades[0]["id"]) == 16  # SHA-256 truncated


# ---------------------------------------------------------------------------
# Alert transform
# ---------------------------------------------------------------------------


class TestTransformAlerts:
    def test_from_system_events(self, tmp_path):
        events = tmp_path / "data" / "system_events.jsonl"
        events.parent.mkdir(parents=True)
        row = {
            "type": "alert",
            "timestamp": "2026-04-19T08:00:00Z",
            "message": "CPU spike on Mac",
            "service": "control-plane",
            "priority": "high",
        }
        events.write_text(json.dumps(row) + "\n")

        alerts = transform_alerts(tmp_path)
        assert len(alerts) == 1
        assert alerts[0]["severity"] == "high"
        assert alerts[0]["category"] == "alert"

    def test_filters_non_alert_events(self, tmp_path):
        events = tmp_path / "data" / "system_events.jsonl"
        events.parent.mkdir(parents=True)
        events.write_text(
            json.dumps({"type": "info", "message": "routine"})
            + "\n"
            + json.dumps({"type": "security_scan", "message": "vuln found"})
            + "\n"
        )
        alerts = transform_alerts(tmp_path)
        assert len(alerts) == 1  # only the security one

    def test_from_security_dir(self, tmp_path):
        sec_dir = tmp_path / "data" / "security"
        sec_dir.mkdir(parents=True)
        (sec_dir / "scan.json").write_text(
            json.dumps(
                {
                    "findings": [
                        {"id": "f1", "title": "XSS in endpoint", "severity": "high"},
                        {"id": "f2", "title": "Outdated dep", "severity": "low"},
                    ]
                }
            )
        )
        # Also need system_events.jsonl to exist (or not)
        alerts = transform_alerts(tmp_path)
        assert len(alerts) == 2
        assert alerts[0]["category"] == "security_report"

    def test_from_dated_security_subdirectory(self, tmp_path):
        sec_dir = tmp_path / "data" / "security" / "2026-04-25"
        sec_dir.mkdir(parents=True)
        (sec_dir / "pipeline.json").write_text(
            json.dumps(
                {
                    "timestamp": "2026-04-25T09:10:29Z",
                    "posture": "needs_attention",
                }
            )
        )

        alerts = transform_alerts(tmp_path)

        assert len(alerts) == 1
        assert alerts[0]["title"] == "pipeline"
        assert alerts[0]["category"] == "security_report"
        assert alerts[0]["_sapphire_source"] == "data/security/2026-04-25/pipeline.json"

    def test_empty(self, tmp_path):
        assert transform_alerts(tmp_path) == []


# ---------------------------------------------------------------------------
# ServiceHealth transform
# ---------------------------------------------------------------------------


class TestTransformServiceHealth:
    def test_from_health_ndjson(self, tmp_path):
        health_dir = tmp_path / "data" / "health"
        health_dir.mkdir(parents=True)
        (health_dir / "2026-04-19.ndjson").write_text(
            json.dumps({"service": "dashboard", "status": "healthy", "latency_ms": 42}) + "\n"
        )

        objs = transform_service_health(tmp_path)
        assert len(objs) >= 1
        assert objs[0]["service"] == "dashboard"
        assert objs[0]["status"] == "healthy"
        assert objs[0]["last_check"]

    def test_from_topology_fallback(self, tmp_path):
        (tmp_path / "data").mkdir(parents=True)
        (tmp_path / "data" / "device_topology.json").write_text(
            json.dumps(
                {
                    "devices": [
                        {"name": "mac", "ip": "100.67.171.79", "services": ["dashboard", "proxy"]},
                    ]
                }
            )
        )

        objs = transform_service_health(tmp_path)
        assert len(objs) == 2
        assert objs[0]["status"] == "unknown"
        assert all(obj["last_check"] for obj in objs)

    def test_empty(self, tmp_path):
        assert transform_service_health(tmp_path) == []

    def test_real_schema_service_name_field(self, tmp_path):
        """Real data/health/*.ndjson uses `service_name` (not `service`)."""
        health_dir = tmp_path / "data" / "health"
        health_dir.mkdir(parents=True)
        (health_dir / "2026-04-19.ndjson").write_text(
            json.dumps(
                {
                    "service_name": "ollama_windows",
                    "ip": "100.71.10.48",
                    "status": "healthy",
                    "response_ms": 412,
                    "timestamp": "2026-04-19T10:00:00Z",
                }
            )
            + "\n"
        )
        objs = transform_service_health(tmp_path)
        assert len(objs) >= 1
        match = [o for o in objs if o["service"] == "ollama_windows"]
        assert match, f"expected ollama_windows entry, got {objs}"
        assert match[0]["status"] == "healthy"
        assert match[0]["latency_ms"] == 412

    def test_heartbeat_jsonl_services_dict(self, tmp_path):
        """heartbeat.jsonl stores services as a nested dict per line."""
        health_dir = tmp_path / "data" / "health"
        health_dir.mkdir(parents=True)
        (health_dir / "heartbeat.jsonl").write_text(
            json.dumps(
                {
                    "timestamp": "2026-04-19T10:00:00Z",
                    "services": {
                        "dashboard": {"status": "healthy", "latency_ms": 12},
                        "proxy": {"status": "degraded", "latency_ms": 900},
                    },
                }
            )
            + "\n"
        )
        objs = transform_service_health(tmp_path)
        names = sorted(o["service"] for o in objs)
        assert "dashboard" in names and "proxy" in names
        dash = next(o for o in objs if o["service"] == "dashboard")
        assert dash["status"] == "healthy"
        assert dash["latency_ms"] == 12
        assert dash["last_check"] == "2026-04-19T10:00:00Z"

    def test_non_dict_row_does_not_crash(self, tmp_path):
        """A stray string line must not break the whole transform."""
        health_dir = tmp_path / "data" / "health"
        health_dir.mkdir(parents=True)
        (health_dir / "2026-04-19.ndjson").write_text(
            '"just a string"\n'
            + json.dumps({"service_name": "dashboard", "status": "healthy"})
            + "\n"
        )
        objs = transform_service_health(tmp_path)
        # Should have captured the valid dict row, skipped the string
        assert any(o["service"] == "dashboard" for o in objs)

    def test_topology_handles_string_services(self, tmp_path):
        """device_topology services may be strings OR dicts OR junk."""
        (tmp_path / "data").mkdir(parents=True)
        (tmp_path / "data" / "device_topology.json").write_text(
            json.dumps(
                {
                    "devices": [
                        {
                            "name": "mac",
                            "services": [
                                "dashboard",  # string
                                {"name": "proxy", "port": 11435},  # dict
                                42,  # junk, must be skipped
                            ],
                        },
                    ]
                }
            )
        )
        objs = transform_service_health(tmp_path)
        names = [o["service"] for o in objs]
        assert "dashboard" in names
        assert "proxy" in names
        assert 42 not in names


# ---------------------------------------------------------------------------
# ThreatIntel transform
# ---------------------------------------------------------------------------


class TestTransformThreatIntel:
    def test_from_threats_json(self, tmp_path):
        intel_dir = tmp_path / "data" / "intelligence" / "2026-04-19"
        intel_dir.mkdir(parents=True)
        (intel_dir / "threats.json").write_text(
            json.dumps(
                {
                    "threats": [
                        {
                            "canonical_id": "t1",
                            "title": "Critical RCE in libfoo",
                            "severity": "critical",
                            "source": "CISA",
                            "published": "2026-04-19",
                            "cve_ids": ["CVE-2026-1234"],
                        },
                    ]
                }
            )
        )

        objs = transform_threat_intel(tmp_path)
        assert len(objs) == 1
        assert objs[0]["id"] == "t1"
        assert objs[0]["cve_ids"] == ["CVE-2026-1234"]
        assert objs[0]["severity"] == "critical"

    def test_from_markdown(self, tmp_path):
        md_dir = tmp_path / "data" / "threat_intel"
        md_dir.mkdir(parents=True)
        (md_dir / "brief_CVE-2026-9999.md").write_text(
            "# Critical CVE-2026-9999 Advisory\n\nDetails about the vulnerability.\n"
        )

        objs = transform_threat_intel(tmp_path)
        assert len(objs) == 1
        assert "CVE-2026-9999" in objs[0]["title"]
        assert "CVE-2026-9999" in objs[0]["cve_ids"]

    def test_empty(self, tmp_path):
        assert transform_threat_intel(tmp_path) == []


# ---------------------------------------------------------------------------
# DailyBrief transform
# ---------------------------------------------------------------------------


class TestTransformDailyBriefs:
    def test_from_json(self, tmp_path):
        day_dir = tmp_path / "data" / "intelligence" / "2026-04-19"
        day_dir.mkdir(parents=True)
        (day_dir / "daily_brief.json").write_text(
            json.dumps(
                {
                    "title": "Morning Brief",
                    "summary": "Markets up, threats low.",
                    "threat_level": "normal",
                    "market_outlook": "bullish",
                    "generated_at": "2026-04-19T08:00:00Z",
                }
            )
        )

        briefs = transform_daily_briefs(tmp_path)
        assert len(briefs) == 1
        assert briefs[0]["title"] == "Morning Brief"
        assert briefs[0]["date"] == "2026-04-19"

    def test_from_markdown(self, tmp_path):
        day_dir = tmp_path / "data" / "intelligence" / "2026-04-18"
        day_dir.mkdir(parents=True)
        (day_dir / "daily_brief.md").write_text("# Daily Brief 2026-04-18\n\nContent here.\n")

        briefs = transform_daily_briefs(tmp_path)
        assert len(briefs) == 1
        assert "2026-04-18" in briefs[0]["title"]

    def test_since_filter(self, tmp_path):
        for d in ("2026-04-10", "2026-04-19"):
            day_dir = tmp_path / "data" / "intelligence" / d
            day_dir.mkdir(parents=True)
            (day_dir / "daily_brief.json").write_text(
                json.dumps(
                    {
                        "title": f"Brief {d}",
                        "summary": "test",
                    }
                )
            )

        since = datetime(2026, 4, 15, tzinfo=UTC)
        briefs = transform_daily_briefs(tmp_path, since=since)
        assert len(briefs) == 1
        assert briefs[0]["date"] == "2026-04-19"

    def test_empty(self, tmp_path):
        assert transform_daily_briefs(tmp_path) == []


# ---------------------------------------------------------------------------
# Regional intelligence Foundry export transforms
# ---------------------------------------------------------------------------


class TestTransformRegionalIntel:
    def test_region_export_adds_id_alias_and_source_ref(self, tmp_path):
        export_dir = tmp_path / "data" / "foundry" / "regional-intel"
        export_dir.mkdir(parents=True)
        (export_dir / "Region.ndjson").write_text(
            json.dumps(
                {
                    "object_id": "regional-intel:region:austin_tx",
                    "region_id": "austin_tx",
                    "name": "Austin, TX",
                    "summary": "Creative business expansion signals.",
                    "snapshot_updated_at": "2026-04-27T18:00:00Z",
                }
            )
            + "\n"
        )

        rows = transform_regions(tmp_path)

        assert rows == [
            {
                "object_id": "regional-intel:region:austin_tx",
                "id": "regional-intel:region:austin_tx",
                "region_id": "austin_tx",
                "name": "Austin, TX",
                "summary": "Creative business expansion signals.",
                "snapshot_updated_at": "2026-04-27T18:00:00Z",
                "_sapphire_source": "data/foundry/regional-intel/Region.ndjson",
            }
        ]

    def test_intel_item_export_preserves_provenance(self, tmp_path):
        export_dir = tmp_path / "data" / "foundry" / "regional-intel"
        export_dir.mkdir(parents=True)
        (export_dir / "IntelItem.ndjson").write_text(
            json.dumps(
                {
                    "object_id": "regional-intel:item:news:item-1",
                    "item_id": "item-1",
                    "kind": "news",
                    "region_id": "austin_tx",
                    "title": "New venue permit",
                    "summary": "Venue expansion signal",
                    "score": 0.91,
                    "source_name": "Austin Monitor",
                    "source_url": "https://example.test/story",
                    "observed_at": "2026-04-27T17:00:00Z",
                    "snapshot_updated_at": "2026-04-27T18:00:00Z",
                }
            )
            + "\n"
        )

        rows = transform_intel_items(tmp_path)

        assert len(rows) == 1
        assert rows[0]["id"] == "regional-intel:item:news:item-1"
        assert rows[0]["source_name"] == "Austin Monitor"
        assert rows[0]["source_url"] == "https://example.test/story"

    def test_source_health_export_since_filter(self, tmp_path):
        export_dir = tmp_path / "data" / "foundry" / "regional-intel"
        export_dir.mkdir(parents=True)
        (export_dir / "IntelSourceHealth.ndjson").write_text(
            json.dumps(
                {
                    "object_id": "regional-intel:source:old",
                    "source_key": "old",
                    "name": "Old Source",
                    "status": "empty",
                    "snapshot_updated_at": "2026-04-20T00:00:00Z",
                }
            )
            + "\n"
            + json.dumps(
                {
                    "object_id": "regional-intel:source:new",
                    "source_key": "new",
                    "name": "New Source",
                    "status": "live",
                    "snapshot_updated_at": "2026-04-27T00:00:00Z",
                }
            )
            + "\n"
        )

        rows = transform_intel_source_health(tmp_path, since=datetime(2026, 4, 26, tzinfo=UTC))

        assert [row["source_key"] for row in rows] == ["new"]


# ---------------------------------------------------------------------------
# transform_all
# ---------------------------------------------------------------------------


class TestTransformAll:
    def test_returns_all_types(self, tmp_path):
        # Minimal data to avoid errors
        (tmp_path / "data" / "signals").mkdir(parents=True)
        result = transform_all(tmp_path)
        assert "PaperTrade" in result
        assert "Alert" in result
        assert "ServiceHealth" in result
        assert "ThreatIntel" in result
        assert "DailyBrief" in result
        assert "Region" in result
        assert "IntelItem" in result
        assert "IntelSourceHealth" in result
        # All should be lists (possibly empty)
        for v in result.values():
            assert isinstance(v, list)
