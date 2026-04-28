"""Tests for scripts/ops/cost_posture_report.py."""

from __future__ import annotations

import importlib.util
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ops" / "cost_posture_report.py"
SPEC = importlib.util.spec_from_file_location("cost_posture_report", SCRIPT)
assert SPEC and SPEC.loader
cost_report = importlib.util.module_from_spec(SPEC)
sys.modules["cost_posture_report"] = cost_report
SPEC.loader.exec_module(cost_report)


def test_summarize_service_excludes_env_values():
    service = {
        "metadata": {
            "name": "tho-agent",
            "annotations": {
                "autoscaling.knative.dev/minScale": "1",
                "autoscaling.knative.dev/maxScale": "25",
            },
        },
        "status": {"latestReadyRevisionName": "tho-agent-00001-test"},
        "spec": {
            "template": {
                "spec": {
                    "containers": [
                        {
                            "env": [{"name": "TOKEN", "value": "do-not-print"}],
                            "resources": {"limits": {"cpu": "1", "memory": "512Mi"}},
                        }
                    ]
                }
            }
        },
    }

    summary = cost_report.summarize_service("tho-ai-agent", "us-central1", service)

    assert "do-not-print" not in str(summary)
    assert summary["cost_risks"] == ["min_instances_nonzero", "max_scale_high"]
    assert summary["cpu_limit"] == "1"
    assert summary["memory_limit"] == "512Mi"


def test_summarize_service_prefers_template_scale_annotations():
    service = {
        "metadata": {
            "name": "sapphire-gcs-to-bq",
            "annotations": {
                "run.googleapis.com/maxScale": "60",
            },
        },
        "status": {"latestReadyRevisionName": "sapphire-gcs-to-bq-00001-test"},
        "spec": {
            "template": {
                "metadata": {
                    "annotations": {
                        "autoscaling.knative.dev/maxScale": "5",
                    },
                },
                "spec": {"containers": [{"resources": {"limits": {"cpu": "0.3333"}}}]},
            }
        },
    }

    summary = cost_report.summarize_service("tho-ai-agent", "us-central1", service)

    assert summary["max_scale"] == 5
    assert "max_scale_high" not in summary["cost_risks"]


def test_render_markdown_does_not_include_billing_account_identifier():
    report = {
        "generated_at": "2026-04-25T00:00:00+00:00",
        "region": "us-central1",
        "projects": [
            {
                "project": "tho-ai-agent",
                "billing": {
                    "project": "tho-ai-agent",
                    "available": True,
                    "billing_enabled": True,
                    "billing_account_linked": True,
                    "billingAccountName": "billingAccounts/123456-ABCDEF-SECRET",
                },
                "cloud_run": {
                    "project": "tho-ai-agent",
                    "region": "us-central1",
                    "available": True,
                    "services": [],
                },
                "logging_warnings": {
                    "project": "tho-ai-agent",
                    "available": True,
                    "entries_sampled": 0,
                    "by_service": {},
                    "by_severity": {},
                },
            }
        ],
    }

    output = cost_report.render_markdown(report)

    assert "123456-ABCDEF-SECRET" not in output
    assert "| tho-ai-agent | yes | yes | yes | - |" in output


def test_summarize_billing_redacts_account_name(monkeypatch):
    monkeypatch.setattr(
        cost_report,
        "_run_gcloud_json",
        lambda *_args, **_kwargs: cost_report.CommandResult(
            True,
            {
                "billingEnabled": True,
                "billingAccountName": "billingAccounts/123456-ABCDEF-SECRET",
            },
        ),
    )

    summary = cost_report.summarize_billing("tho-ai-agent")

    assert summary == {
        "project": "tho-ai-agent",
        "available": True,
        "billing_enabled": True,
        "billing_account_linked": True,
    }


def test_summarize_logging_warnings_counts_without_raw_messages(monkeypatch):
    entries = [
        {
            "severity": "WARNING",
            "textPayload": "raw URL or payload should not render",
            "httpRequest": {
                "status": 404,
                "requestUrl": "https://example.invalid/.env?debug=do-not-print",
            },
            "resource": {"labels": {"service_name": "sapphire-analytics"}},
        },
        {
            "severity": "ERROR",
            "jsonPayload": {"message": "raw structured message should not render"},
            "httpRequest": {
                "status": 500,
                "requestUrl": "https://example.invalid/api/run?debug=do-not-print",
            },
            "resource": {"labels": {"service_name": "sapphire-analytics"}},
        },
        {
            "severity": "WARNING",
            "textPayload": "The request was not authenticated.",
            "httpRequest": {
                "status": 403,
                "requestUrl": "https://example.invalid/health",
            },
            "resource": {"labels": {"service_name": "agentic-pm-hub"}},
        },
    ]
    monkeypatch.setattr(
        cost_report,
        "_run_gcloud_json",
        lambda *_args, **_kwargs: cost_report.CommandResult(True, entries),
    )

    summary = cost_report.summarize_logging_warnings("tho-ai-agent", days=7, limit=100)

    assert summary["entries_sampled"] == 3
    assert summary["sample_limit"] == 100
    assert summary["sample_at_limit"] is False
    assert summary["by_service"] == {"agentic-pm-hub": 1, "sapphire-analytics": 2}
    assert summary["by_severity"] == {"ERROR": 1, "WARNING": 2}
    assert summary["by_status"] == {"403": 1, "404": 1, "500": 1}
    assert summary["by_route_category"] == {
        "/api/*": 1,
        "health": 1,
        "public_probe": 1,
    }
    assert summary["by_warning_kind"] == {
        "client_http_error": 1,
        "cloud_run_auth_required": 1,
        "server_http_error": 1,
    }
    assert "raw URL" not in str(summary)
    assert "do-not-print" not in str(summary)
    assert ".env" not in str(summary)

    limited = cost_report.summarize_logging_warnings("tho-ai-agent", days=7, limit=2)
    assert limited["sample_at_limit"] is True


def test_summarize_logging_warnings_prefers_hours_lookback(monkeypatch):
    captured = {}

    def fake_run(args, **_kwargs):
        captured["args"] = args
        return cost_report.CommandResult(True, [])

    monkeypatch.setattr(cost_report, "_run_gcloud_json", fake_run)

    summary = cost_report.summarize_logging_warnings(
        "tho-ai-agent",
        days=7,
        hours=2,
        limit=50,
    )

    query = captured["args"][2]
    timestamp = query.split('timestamp>="', 1)[1].split('"', 1)[0]
    since = datetime.fromisoformat(timestamp)

    assert summary["lookback"] == "2h"
    assert summary["hours"] == 2
    assert summary["sample_limit"] == 50
    assert 0 < (datetime.now(UTC) - since).total_seconds() <= 2 * 3600 + 5


def test_render_markdown_marks_warning_sample_at_limit():
    report = {
        "generated_at": "2026-04-26T00:00:00+00:00",
        "region": "us-central1",
        "warning_lookback": "1h",
        "projects": [
            {
                "project": "tho-ai-agent",
                "billing": {
                    "project": "tho-ai-agent",
                    "available": True,
                    "billing_enabled": True,
                    "billing_account_linked": True,
                },
                "cloud_run": {
                    "project": "tho-ai-agent",
                    "region": "us-central1",
                    "available": True,
                    "services": [],
                },
                "logging_warnings": {
                    "project": "tho-ai-agent",
                    "available": True,
                    "entries_sampled": 200,
                    "sample_at_limit": True,
                    "by_service": {"sapphire-analytics": 185},
                    "by_severity": {"WARNING": 200},
                    "by_status": {"404": 185, "500": 15},
                    "by_route_category": {"public_probe": 185, "/api/*": 15},
                    "by_warning_kind": {
                        "client_http_error": 185,
                        "server_http_error": 15,
                    },
                },
            }
        ],
    }

    output = cost_report.render_markdown(report)

    assert "- Warning lookback: `1h`" in output
    assert (
        "| Project | Available | Entries Sampled | At Limit | By Service | By Severity | By Status | Route Categories | Warning Kinds | Notes |"
        in output
    )
    assert (
        "| tho-ai-agent | yes | 200 | yes | sapphire-analytics:185 | WARNING:200 | 404:185, 500:15 | /api/*:15, public_probe:185 | client_http_error:185, server_http_error:15 | - |"
        in output
    )


def test_route_category_collapses_probe_paths_without_query_values():
    assert cost_report.route_category("https://example.invalid/healthz/") == "health"
    assert (
        cost_report.route_category("https://example.invalid/__env.js?debug=sample")
        == "public_probe"
    )
    assert cost_report.route_category("https://example.invalid/runtime-config.js") == "public_probe"
    assert cost_report.route_category("https://example.invalid/.%2565%256ev") == "public_probe"
    assert cost_report.route_category("https://example.invalid/credentials.json") == "public_probe"
    assert cost_report.route_category("https://example.invalid/terraform.tfstate") == "public_probe"
    assert cost_report.route_category("https://example.invalid/weird-backup.zip") == "public_probe"
    assert cost_report.route_category("https://example.invalid/composer.json") == "public_probe"
    assert (
        cost_report.route_category("https://example.invalid/docker-compose.yml") == "public_probe"
    )
    assert cost_report.route_category("https://example.invalid/openapi.json") == "public_probe"
    assert cost_report.route_category("https://example.invalid/server.js") == "public_probe"
    assert cost_report.route_category("https://example.invalid/docs/page") == "/docs/*"


def test_local_retention_summary_counts_without_filenames(tmp_path):
    audit_dir = tmp_path / "audit"
    audit_dir.mkdir()
    old_file = audit_dir / "secret_named_file.jsonl"
    old_file.write_text("token=do-not-print\n", encoding="utf-8")
    old_ts = datetime(2026, 1, 1, tzinfo=UTC).timestamp()
    os.utime(old_file, (old_ts, old_ts))
    missing_dir = tmp_path / "missing"

    summary = cost_report.summarize_local_retention(
        (
            {
                "id": "audit",
                "path": str(audit_dir),
                "retention_days": 1,
                "max_size_mb": 10,
                "kind": "audit_jsonl",
            },
            {
                "id": "missing",
                "path": str(missing_dir),
                "retention_days": 1,
                "max_size_mb": 10,
                "kind": "local_logs",
            },
        ),
        now=datetime(2026, 4, 26, tzinfo=UTC),
    )
    rendered = cost_report.render_markdown(
        {
            "generated_at": "2026-04-26T00:00:00+00:00",
            "region": "us-central1",
            "warning_lookback": "1h",
            "projects": [],
            "local_retention": summary,
        }
    )

    assert summary["target_count"] == 2
    assert summary["risk_count"] == 2
    by_id = {row["id"]: row for row in summary["targets"]}
    assert by_id["audit"]["file_count"] == 1
    assert by_id["audit"]["oldest_age_days"] == 115
    assert by_id["audit"]["risks"] == ["oldest_exceeds_retention"]
    assert by_id["missing"]["risks"] == ["missing"]
    assert "secret_named_file" not in str(summary)
    assert "do-not-print" not in str(summary)
    assert "## Local Retention" in rendered


def test_warning_kind_classifies_expected_cloud_run_auth_rejections():
    assert (
        cost_report.warning_kind(
            {
                "textPayload": "The request was not authenticated. Set the proper Authorization header.",
                "httpRequest": {"status": 403},
            }
        )
        == "cloud_run_auth_required"
    )
    assert cost_report.warning_kind({"httpRequest": {"status": 404}}) == "client_http_error"
    assert cost_report.warning_kind({"httpRequest": {"status": 503}}) == "server_http_error"
