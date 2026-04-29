"""Tests for ``lib.inference_telemetry.recommender``."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from lib.inference_telemetry.aggregator import CallRecord, aggregate
from lib.inference_telemetry.cost_model import DEFAULT_COST_MODEL, with_kimi_rates
from lib.inference_telemetry.recommender import recommend, top_n


def _build_report(records, cost_model=None):
    return aggregate(fixture_records=records, cost_model=cost_model or DEFAULT_COST_MODEL)


def test_recommend_empty_report_emits_no_recommendations():
    rep = _build_report([])
    bundle = recommend(rep)
    assert bundle.recommendations == []
    # Top-level caveats must include the "no real fixture data" warning.
    assert any("no real fixture data" in c for c in bundle.caveats)


def test_recommend_includes_kimi_caveat_when_rates_unsupplied():
    rep = _build_report([])
    bundle = recommend(rep)  # default cost model
    assert any("Kimi (T4) rates default to 0" in c for c in bundle.caveats)


def test_recommend_omits_kimi_caveat_when_rates_supplied():
    rep = _build_report([])
    cm = with_kimi_rates(input_usd_per_1k_tokens=1.0, output_usd_per_1k_tokens=2.0)
    bundle = recommend(rep, cost_model=cm)
    assert not any("Kimi (T4) rates default" in c for c in bundle.caveats)


def test_recommend_t4_to_t1_when_both_present():
    base = datetime(2026, 4, 28, tzinfo=UTC)
    cm = with_kimi_rates(input_usd_per_1k_tokens=1.0, output_usd_per_1k_tokens=2.0)
    records = [
        CallRecord(tier="T1_windows_gpu", ts=base, latency_ms=400, ok=True),
        CallRecord(
            tier="T4_kimi_cloud",
            ts=base + timedelta(seconds=10),
            latency_ms=2400,
            ok=True,
            tokens_in=1000,
            tokens_out=500,
        ),
    ]
    rep = _build_report(records, cost_model=cm)
    bundle = recommend(rep, cost_model=cm)
    switches = [r for r in bundle.recommendations if r.kind == "switch_tier"]
    targets = {(r.from_tier, r.to_tier) for r in switches}
    assert ("T4_kimi_cloud", "T1_windows_gpu") in targets


def test_recommend_t4_to_t1_includes_capability_caveat():
    base = datetime(2026, 4, 28, tzinfo=UTC)
    cm = with_kimi_rates(input_usd_per_1k_tokens=1.0, output_usd_per_1k_tokens=2.0)
    records = [
        CallRecord(tier="T1_windows_gpu", ts=base, latency_ms=400, ok=True),
        CallRecord(
            tier="T4_kimi_cloud",
            ts=base,
            latency_ms=2400,
            ok=True,
            tokens_in=1000,
            tokens_out=500,
        ),
    ]
    bundle = recommend(_build_report(records, cost_model=cm), cost_model=cm)
    rec_t4_t1 = next(
        r
        for r in bundle.recommendations
        if r.from_tier == "T4_kimi_cloud" and r.to_tier == "T1_windows_gpu"
    )
    caveats_text = " ".join(rec_t4_t1.caveats)
    assert "T4 is reserved for non-sensitive" in caveats_text


def test_recommend_t3_to_t1_includes_fallback_caveat():
    base = datetime(2026, 4, 28, tzinfo=UTC)
    records = [
        CallRecord(tier="T1_windows_gpu", ts=base, latency_ms=400, ok=True),
        CallRecord(tier="T3_mac_local", ts=base, latency_ms=80000, ok=True),
    ]
    bundle = recommend(_build_report(records))
    rec = next(
        r for r in bundle.recommendations if r.from_tier == "T3_mac_local" and r.to_tier == "T1_windows_gpu"
    )
    assert any("always-on fallback" in c for c in rec.caveats)


def test_recommend_high_error_rate_emits_routing_warning():
    base = datetime(2026, 4, 28, tzinfo=UTC)
    # Build 30 calls on T1, 5 of them failing (16.7% > 10% threshold).
    records = []
    for i in range(25):
        records.append(
            CallRecord(tier="T1_windows_gpu", ts=base + timedelta(seconds=i), latency_ms=400, ok=True)
        )
    for i in range(5):
        records.append(
            CallRecord(
                tier="T1_windows_gpu",
                ts=base + timedelta(seconds=100 + i),
                latency_ms=410,
                ok=False,
                error_class="HTTPError",
            )
        )
    rep = _build_report(records)
    bundle = recommend(rep)
    health = [r for r in bundle.recommendations if r.kind == "routing_health_warning"]
    assert len(health) == 1
    assert health[0].from_tier == "T1_windows_gpu"
    assert any("HTTPError" in c for c in health[0].caveats)


def test_recommend_short_window_low_confidence():
    base = datetime(2026, 4, 28, tzinfo=UTC)
    records = [
        CallRecord(tier="T1_windows_gpu", ts=base, latency_ms=400, ok=True),
        CallRecord(tier="T3_mac_local", ts=base + timedelta(seconds=30), latency_ms=80000, ok=True),
    ]
    bundle = recommend(_build_report(records))
    if bundle.recommendations:
        assert all(r.confidence == "low" for r in bundle.recommendations)


def test_recommend_to_dict_serializable():
    rep = _build_report([])
    bundle = recommend(rep)
    d = bundle.to_dict()
    import json

    parsed = json.loads(json.dumps(d, default=str))
    assert "recommendations" in parsed
    assert "caveats" in parsed
    assert parsed["schema_version"] == 1


def test_top_n_returns_at_most_n_recommendations():
    base = datetime(2026, 4, 28, tzinfo=UTC)
    cm = with_kimi_rates(input_usd_per_1k_tokens=1.0, output_usd_per_1k_tokens=2.0)
    records = [
        CallRecord(tier="T1_windows_gpu", ts=base, latency_ms=400, ok=True),
        CallRecord(
            tier="T4_kimi_cloud",
            ts=base,
            latency_ms=2400,
            ok=True,
            tokens_in=1000,
            tokens_out=500,
        ),
        CallRecord(tier="T3_mac_local", ts=base, latency_ms=80000, ok=True),
    ]
    bundle = recommend(_build_report(records, cost_model=cm), cost_model=cm)
    top2 = top_n(bundle, n=2)
    assert len(top2) <= 2


def test_recommend_unknown_tier_doesnt_crash():
    """An unknown tier in the input should be ignored gracefully."""
    base = datetime(2026, 4, 28, tzinfo=UTC)
    records = [
        CallRecord(tier="T9_alien", ts=base, latency_ms=100, ok=True),
        CallRecord(tier="T1_windows_gpu", ts=base, latency_ms=400, ok=True),
    ]
    bundle = recommend(_build_report(records))
    # Should produce a bundle (no crash); content may or may not include T9.
    assert bundle.has_real_data is False  # synthetic fixture
    assert isinstance(bundle.recommendations, list)
