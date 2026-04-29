"""Tests for ``lib.inference_telemetry.aggregator``.

Pure tests — no I/O beyond ``tmp_path`` fixture. Covers parsing, percentile
math, aggregation correctness, missing-file handling, and the synthetic
fixture report (used when no real data exists).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from lib.inference_telemetry.aggregator import (
    DEFAULT_CALLS_PATH,
    CallRecord,
    aggregate,
    iter_records,
    parse_record,
    percentile,
    project_monthly_calls,
    project_monthly_cost,
    synthetic_fixture_report,
)
from lib.inference_telemetry.cost_model import (
    DEFAULT_COST_MODEL,
    with_kimi_rates,
)

# ── Parsing ─────────────────────────────────────────────────────────────────


def test_parse_record_minimal():
    rec = parse_record({"tier": "T1_windows_gpu"})
    assert rec is not None
    assert rec.tier == "T1_windows_gpu"
    assert rec.ok is True
    assert rec.tokens_in == 0


def test_parse_record_full():
    rec = parse_record(
        {
            "tier": "T1_windows_gpu",
            "model": "hermes3:8b",
            "ts": "2026-04-29T12:00:00Z",
            "latency_ms": 412,
            "ok": True,
            "tokens_in": 300,
            "tokens_out": 150,
        }
    )
    assert rec is not None
    assert rec.tokens_total == 450
    assert rec.ts == datetime(2026, 4, 29, 12, 0, 0, tzinfo=UTC)


def test_parse_record_alternate_keys():
    """Accepts alternate naming used by some loggers (prompt_tokens/completion_tokens)."""
    rec = parse_record(
        {
            "tier": "T4_kimi_cloud",
            "elapsed_ms": 2400,
            "prompt_tokens": 1800,
            "completion_tokens": 900,
            "success": True,
        }
    )
    assert rec is not None
    assert rec.tier == "T4_kimi_cloud"
    assert rec.tokens_in == 1800
    assert rec.tokens_out == 900
    assert rec.latency_ms == 2400


def test_parse_record_returns_none_for_garbage():
    assert parse_record(None) is None
    assert parse_record(["array", "not", "object"]) is None
    assert parse_record({}) is None  # missing tier
    assert parse_record({"tier": ""}) is None  # empty tier


def test_parse_record_handles_malformed_latency():
    rec = parse_record({"tier": "T1_windows_gpu", "latency_ms": "abc"})
    assert rec is not None
    assert rec.latency_ms is None


# ── Percentile ──────────────────────────────────────────────────────────────


def test_percentile_empty_returns_none():
    assert percentile([], 50) is None


def test_percentile_p50_p99():
    values = [float(x) for x in range(1, 101)]  # 1..100
    assert percentile(values, 50) == pytest.approx(50.5)
    assert percentile(values, 99) == pytest.approx(99.01)
    assert percentile(values, 100) == 100.0
    assert percentile(values, 0) == 1.0


def test_percentile_single_value():
    assert percentile([42.0], 50) == 42.0
    assert percentile([42.0], 99) == 42.0


# ── iter_records / file reading ─────────────────────────────────────────────


def test_iter_records_missing_file_yields_nothing(tmp_path: Path):
    target = tmp_path / "missing.jsonl"
    out = list(iter_records(target))
    assert out == []


def test_iter_records_skips_invalid_lines(tmp_path: Path):
    target = tmp_path / "calls.jsonl"
    target.write_text(
        "\n".join(
            [
                json.dumps({"tier": "T1_windows_gpu", "latency_ms": 100}),
                "{not json",
                json.dumps({"tier": "T3_mac_local", "latency_ms": 80000}),
                "",
                json.dumps([1, 2, 3]),  # not a dict — ignored
                json.dumps({"tier": "T1_windows_gpu", "latency_ms": 105}),
            ]
        ),
        encoding="utf-8",
    )
    records = list(iter_records(target))
    assert len(records) == 3
    assert records[0].tier == "T1_windows_gpu"
    assert records[1].tier == "T3_mac_local"


# ── aggregate() ─────────────────────────────────────────────────────────────


def _write_jsonl(path: Path, records: list[dict]) -> Path:
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
    return path


def test_aggregate_missing_file_returns_empty_report(tmp_path: Path):
    target = tmp_path / "missing.jsonl"
    rep = aggregate(target)
    assert rep.has_real_data is False
    assert rep.calls_path_exists is False
    assert rep.tiers == []
    assert rep.total_calls == 0
    assert any("calls.jsonl missing" in n for n in rep.notes)


def test_aggregate_real_data_sums_correctly(tmp_path: Path):
    base = datetime(2026, 4, 28, 12, 0, 0, tzinfo=UTC)
    target = tmp_path / "calls.jsonl"
    rows = []
    for i in range(10):
        rows.append(
            {
                "tier": "T1_windows_gpu",
                "ts": (base + timedelta(seconds=i * 60)).isoformat(),
                "latency_ms": 400 + i,
                "ok": True,
                "tokens_in": 100,
                "tokens_out": 50,
            }
        )
    rows.append(
        {
            "tier": "T3_mac_local",
            "ts": (base + timedelta(minutes=15)).isoformat(),
            "latency_ms": 90_000,
            "ok": False,
            "tokens_in": 200,
            "tokens_out": 0,
            "error_class": "TimeoutError",
        }
    )
    _write_jsonl(target, rows)

    rep = aggregate(target)
    assert rep.has_real_data is True
    assert rep.total_calls == 11
    assert rep.total_failure == 1
    assert rep.total_success == 10

    by_tier = {t.tier: t for t in rep.tiers}
    assert "T1_windows_gpu" in by_tier
    assert by_tier["T1_windows_gpu"].calls == 10
    assert by_tier["T1_windows_gpu"].latency_p50_ms == pytest.approx(404.5)
    assert by_tier["T3_mac_local"].error_classes == {"TimeoutError": 1}
    # Cost: 10 calls @ T1 = 10 * 0.001 = 0.01; T3: 1 * 0.0008 = 0.0008
    assert rep.total_cost_usd == pytest.approx(0.0108, abs=1e-6)


def test_aggregate_unknown_tier_is_listed_in_notes(tmp_path: Path):
    target = tmp_path / "calls.jsonl"
    _write_jsonl(target, [{"tier": "T9_alien", "latency_ms": 100, "ok": True}])
    rep = aggregate(target)
    assert any("unknown tiers" in n for n in rep.notes)
    assert rep.tiers[0].tier == "T9_alien"


def test_aggregate_skips_invalid_lines_counted(tmp_path: Path):
    target = tmp_path / "calls.jsonl"
    target.write_text(
        "garbage\n{}\n" + json.dumps({"tier": "T1_windows_gpu"}) + "\n", encoding="utf-8"
    )
    rep = aggregate(target)
    assert rep.parsed_lines == 1
    assert rep.skipped_lines == 2


def test_aggregate_with_fixture_records():
    fixtures = [
        CallRecord(tier="T1_windows_gpu", latency_ms=400, ok=True, tokens_in=100, tokens_out=50),
        CallRecord(tier="T1_windows_gpu", latency_ms=450, ok=True, tokens_in=120, tokens_out=60),
    ]
    rep = aggregate(fixture_records=fixtures)
    assert rep.total_calls == 2
    assert rep.has_real_data is False
    assert "fixture iterable" in rep.notes[0]


def test_aggregate_with_kimi_rates_yields_t4_cost():
    base = datetime(2026, 4, 28, 12, 0, 0, tzinfo=UTC)
    fixtures = [
        CallRecord(
            tier="T4_kimi_cloud",
            ts=base,
            latency_ms=2400,
            ok=True,
            tokens_in=1000,
            tokens_out=500,
        ),
        CallRecord(
            tier="T4_kimi_cloud",
            ts=base + timedelta(minutes=10),
            latency_ms=2500,
            ok=False,
            tokens_in=800,
            tokens_out=0,
        ),
    ]
    cm = with_kimi_rates(input_usd_per_1k_tokens=1.20, output_usd_per_1k_tokens=2.40)
    rep = aggregate(fixture_records=fixtures, cost_model=cm)
    # Successful call: 1.0 * 1.20 + 0.5 * 2.40 = 1.20 + 1.20 = 2.40
    # Failed call: 0 (Kimi rule = no cost on failure)
    assert rep.total_cost_usd == pytest.approx(2.40, rel=1e-6)


def test_aggregate_default_path_constant():
    """Sanity: DEFAULT_CALLS_PATH points to the documented cache location."""
    assert "inference_proxy" in str(DEFAULT_CALLS_PATH)
    assert str(DEFAULT_CALLS_PATH).endswith("calls.jsonl")


def test_aggregate_throughput_calculations(tmp_path: Path):
    target = tmp_path / "calls.jsonl"
    base = datetime(2026, 4, 28, 12, 0, 0, tzinfo=UTC)
    # 60 calls over 60 seconds → 60 calls/min, 3600 calls/hour.
    rows = [
        {
            "tier": "T1_windows_gpu",
            "ts": (base + timedelta(seconds=i)).isoformat(),
            "latency_ms": 400,
            "ok": True,
        }
        for i in range(60)
    ]
    _write_jsonl(target, rows)
    rep = aggregate(target)
    t1 = rep.tiers[0]
    assert t1.calls == 60
    assert t1.calls_per_minute == pytest.approx(60.0, rel=0.05)
    assert t1.calls_per_hour == pytest.approx(3600.0, rel=0.05)


def test_synthetic_fixture_report_yields_three_tiers():
    rep = synthetic_fixture_report()
    tier_names = {t.tier for t in rep.tiers}
    assert {"T1_windows_gpu", "T3_mac_local", "T4_kimi_cloud"}.issubset(tier_names)
    assert rep.has_real_data is False
    assert any("synthetic-only" in n for n in rep.notes)


def test_to_dict_is_serializable():
    rep = synthetic_fixture_report()
    d = rep.to_dict()
    serialized = json.dumps(d, default=str)
    parsed = json.loads(serialized)
    assert parsed["total_calls"] == rep.total_calls
    assert "tiers" in parsed
    assert all("error_rate" in t for t in parsed["tiers"])


def test_project_monthly_cost_zero_when_no_window():
    rep = aggregate(fixture_records=[])
    assert project_monthly_cost(rep) == 0.0
    assert project_monthly_calls(rep) == 0.0


def test_project_monthly_cost_extrapolates_linearly():
    base = datetime(2026, 4, 28, tzinfo=UTC)
    fixtures = [
        CallRecord(tier="T1_windows_gpu", ts=base + timedelta(hours=i), latency_ms=400, ok=True)
        for i in range(24)
    ]
    rep = aggregate(fixture_records=fixtures)
    monthly_cost = project_monthly_cost(rep)
    monthly_calls = project_monthly_calls(rep)
    # 24 calls in 23 hours; per-call cost $0.001 → over 30 days that's roughly
    # 24 * (30 * 24 / 23) ≈ 751 calls and $0.751.
    assert monthly_cost > 0.5
    assert monthly_calls > 700


def test_aggregate_empty_calls_jsonl_is_consistent(tmp_path: Path):
    target = tmp_path / "calls.jsonl"
    target.write_text("", encoding="utf-8")
    rep = aggregate(target)
    assert rep.calls_path_exists is True
    assert rep.has_real_data is False
    assert rep.total_calls == 0


def test_aggregate_uses_default_cost_model():
    rep = aggregate(fixture_records=[])
    assert rep.cost_model_name == DEFAULT_COST_MODEL.name


def test_aggregate_orders_known_tiers_canonically():
    base = datetime(2026, 4, 28, 12, 0, 0, tzinfo=UTC)
    fixtures = [
        # Out-of-order on purpose.
        CallRecord(
            tier="T4_kimi_cloud", ts=base, latency_ms=2400, ok=True, tokens_in=1, tokens_out=1
        ),
        CallRecord(tier="T1_windows_gpu", ts=base, latency_ms=400, ok=True),
        CallRecord(tier="T3_mac_local", ts=base, latency_ms=80000, ok=True),
    ]
    rep = aggregate(fixture_records=fixtures)
    tier_order = [t.tier for t in rep.tiers]
    # Canonical order: T1, T2*, T3, T4. (T2 absent.)
    assert tier_order == ["T1_windows_gpu", "T3_mac_local", "T4_kimi_cloud"]
