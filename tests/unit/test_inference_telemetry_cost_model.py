"""Tests for ``lib.inference_telemetry.cost_model``."""

from __future__ import annotations

import pytest

from lib.inference_telemetry import (
    TIER_T1_GPU,
    TIER_T2_PI_1,
    TIER_T2_PI_2,
    TIER_T3_MAC,
    TIER_T4_KIMI,
)
from lib.inference_telemetry.aggregator import CallRecord
from lib.inference_telemetry.cost_model import (
    DEFAULT_COST_MODEL,
    MOONSHOT_PRICING_RETRIEVED,
    MOONSHOT_PRICING_URL,
    estimate_cost_record,
    estimate_tier_unit_cost,
    with_kimi_rates,
    with_overrides,
)


def test_default_cost_model_has_unsupplied_kimi_rates():
    assert DEFAULT_COST_MODEL.kimi_rates_supplied is False
    assert DEFAULT_COST_MODEL.t4_input_usd_per_1k_tokens == 0.0
    assert DEFAULT_COST_MODEL.t4_output_usd_per_1k_tokens == 0.0


def test_default_cost_model_cites_moonshot_pricing():
    assert DEFAULT_COST_MODEL.moonshot_pricing_url == MOONSHOT_PRICING_URL
    assert DEFAULT_COST_MODEL.moonshot_pricing_retrieved == MOONSHOT_PRICING_RETRIEVED
    assert "moonshot.cn" in MOONSHOT_PRICING_URL


def test_estimate_cost_record_t1_gpu_uses_proxy():
    rec = CallRecord(tier=TIER_T1_GPU, ok=True)
    cost = estimate_cost_record(rec)
    assert cost == pytest.approx(0.001)


def test_estimate_cost_record_t1_charges_failures_too():
    """T1/T3 still spend cycles on failure — keep cost; T4 does not."""
    rec_ok = CallRecord(tier=TIER_T1_GPU, ok=True)
    rec_fail = CallRecord(tier=TIER_T1_GPU, ok=False)
    assert estimate_cost_record(rec_ok) == estimate_cost_record(rec_fail)


def test_estimate_cost_record_t2_pi_zero():
    assert estimate_cost_record(CallRecord(tier=TIER_T2_PI_1)) == 0.0
    assert estimate_cost_record(CallRecord(tier=TIER_T2_PI_2)) == 0.0


def test_estimate_cost_record_t3_mac_uses_proxy():
    cost = estimate_cost_record(CallRecord(tier=TIER_T3_MAC, ok=True))
    assert cost == pytest.approx(0.0008)


def test_estimate_cost_record_t4_default_zero():
    rec = CallRecord(
        tier=TIER_T4_KIMI,
        ok=True,
        tokens_in=10000,
        tokens_out=5000,
    )
    # Default rates are 0 → cost is 0.
    assert estimate_cost_record(rec) == 0.0


def test_estimate_cost_record_t4_with_supplied_rates():
    cm = with_kimi_rates(input_usd_per_1k_tokens=1.20, output_usd_per_1k_tokens=2.40)
    rec = CallRecord(
        tier=TIER_T4_KIMI,
        ok=True,
        tokens_in=1000,
        tokens_out=500,
    )
    # 1k * 1.20 + 0.5k * 2.40 = 1.20 + 1.20 = 2.40
    assert estimate_cost_record(rec, cm) == pytest.approx(2.40)


def test_estimate_cost_record_t4_failure_costs_zero():
    cm = with_kimi_rates(input_usd_per_1k_tokens=1.20, output_usd_per_1k_tokens=2.40)
    rec = CallRecord(tier=TIER_T4_KIMI, ok=False, tokens_in=1000, tokens_out=500)
    assert estimate_cost_record(rec, cm) == 0.0


def test_estimate_cost_record_unknown_tier_zero():
    rec = CallRecord(tier="T9_alien", ok=True, tokens_in=1000, tokens_out=500)
    assert estimate_cost_record(rec) == 0.0


def test_with_kimi_rates_marks_supplied():
    cm = with_kimi_rates(input_usd_per_1k_tokens=0.5, output_usd_per_1k_tokens=1.0)
    assert cm.kimi_rates_supplied is True
    assert cm.t4_input_usd_per_1k_tokens == 0.5
    assert cm.t4_output_usd_per_1k_tokens == 1.0
    assert any("kimi rates supplied" in n for n in cm.notes)


def test_with_overrides_keeps_kimi_supplied_state():
    cm = with_kimi_rates(input_usd_per_1k_tokens=1.0, output_usd_per_1k_tokens=2.0)
    cm2 = with_overrides(base=cm, t1_per_inference_usd=0.0005)
    assert cm2.kimi_rates_supplied is True
    assert cm2.t1_per_inference_usd == 0.0005
    assert cm2.t4_input_usd_per_1k_tokens == 1.0


def test_estimate_tier_unit_cost_returns_none_for_unsupplied_kimi():
    assert estimate_tier_unit_cost(TIER_T4_KIMI) is None


def test_estimate_tier_unit_cost_returns_value_when_kimi_supplied():
    cm = with_kimi_rates(input_usd_per_1k_tokens=1.0, output_usd_per_1k_tokens=2.0)
    val = estimate_tier_unit_cost(TIER_T4_KIMI, cm)
    assert val is not None
    # 0.5 * 1.0 + 0.25 * 2.0 = 0.5 + 0.5 = 1.0
    assert val == pytest.approx(1.0)


def test_estimate_tier_unit_cost_known_tiers():
    assert estimate_tier_unit_cost(TIER_T1_GPU) == pytest.approx(0.001)
    assert estimate_tier_unit_cost(TIER_T2_PI_1) == 0.0
    assert estimate_tier_unit_cost(TIER_T3_MAC) == pytest.approx(0.0008)


def test_to_dict_round_trips_critical_fields():
    cm = with_kimi_rates(input_usd_per_1k_tokens=1.5, output_usd_per_1k_tokens=3.0)
    d = cm.to_dict()
    assert d["kimi_rates_supplied"] is True
    assert d["t4_input_usd_per_1k_tokens"] == 1.5
    assert d["moonshot_pricing_url"] == MOONSHOT_PRICING_URL
    assert d["moonshot_pricing_retrieved"] == MOONSHOT_PRICING_RETRIEVED


def test_default_cost_model_notes_include_moonshot_url():
    assert any("moonshot.cn" in note for note in DEFAULT_COST_MODEL.notes)
