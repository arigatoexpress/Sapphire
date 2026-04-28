"""Isolated unit tests for lib/chain/intelligence.py.

Companion to tests/integration/test_chain_intelligence.py — that file covers
end-to-end snapshot()/classify() flows; this one drills into individual private
helpers (scoring, HTTP retry, persistence I/O, alerting, classify branches)
with all network/subprocess/Pub/Sub boundaries mocked.

Each test uses arrange / act / assert structure and never touches the network.
"""

from __future__ import annotations

import io
import json
import urllib.error
from unittest.mock import patch

import pytest

from lib.chain import intelligence as chain_mod
from lib.chain.intelligence import (
    ChainIntelligence,
    ChainSnapshot,
    Regime,
    RegimeClassification,
    RegimeShiftEvent,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_data(tmp_path, monkeypatch):
    """Redirect data/chain writes into a tmp dir so tests don't touch real state."""
    data_dir = tmp_path / "chain"
    data_dir.mkdir()
    monkeypatch.setattr(chain_mod, "DATA_DIR", data_dir)
    monkeypatch.setattr(chain_mod, "HISTORY_FILE", data_dir / "history.jsonl")
    monkeypatch.setattr(chain_mod, "LAST_STATE_FILE", data_dir / "last_state.json")
    return data_dir


# ---------------------------------------------------------------------------
# _http_json — retry / failure paths
# ---------------------------------------------------------------------------


def test_http_json_returns_parsed_dict_on_success():
    payload = {"hello": "world"}
    fake_resp = io.BytesIO(json.dumps(payload).encode())
    fake_resp.__enter__ = lambda self: self  # type: ignore[attr-defined]
    fake_resp.__exit__ = lambda self, *a: None  # type: ignore[attr-defined]

    with patch.object(chain_mod.urllib.request, "urlopen", return_value=fake_resp):
        result = chain_mod._http_json("https://example.test/json")

    assert result == payload


def test_http_json_returns_none_after_three_failures():
    err = urllib.error.URLError("boom")

    with (
        patch.object(chain_mod.urllib.request, "urlopen", side_effect=err) as urlopen,
        patch.object(chain_mod.time, "sleep") as sleep,
    ):
        result = chain_mod._http_json("https://example.test/dead")

    assert result is None
    assert urlopen.call_count == 3
    # backoff is 2**0=1s, 2**1=2s between the three attempts (only on first 2)
    assert sleep.call_count == 2


def test_http_json_handles_invalid_json_payload():
    def _fresh_bad():
        bad_resp = io.BytesIO(b"<html>not json</html>")
        bad_resp.__enter__ = lambda self: self  # type: ignore[attr-defined]
        bad_resp.__exit__ = lambda self, *a: None  # type: ignore[attr-defined]
        return bad_resp

    with (
        patch.object(
            chain_mod.urllib.request, "urlopen", side_effect=lambda *a, **k: _fresh_bad()
        ),
        patch.object(chain_mod.time, "sleep"),
    ):
        result = chain_mod._http_json("https://example.test/badjson")

    assert result is None


# ---------------------------------------------------------------------------
# Source fetchers — mocked via _http_json
# ---------------------------------------------------------------------------


def test_fetch_fear_greed_parses_value_and_label(monkeypatch):
    monkeypatch.setattr(
        chain_mod,
        "_http_json",
        lambda url, timeout=10.0: {"data": [{"value": "37", "value_classification": "Fear"}]},
    )
    value, label = chain_mod._fetch_fear_greed()
    assert value == 37
    assert label == "Fear"


def test_fetch_fear_greed_returns_none_on_empty_data(monkeypatch):
    monkeypatch.setattr(chain_mod, "_http_json", lambda url, timeout=10.0: {"data": []})
    assert chain_mod._fetch_fear_greed() == (None, None)


def test_fetch_fear_greed_returns_none_on_non_dict_payload(monkeypatch):
    monkeypatch.setattr(chain_mod, "_http_json", lambda url, timeout=10.0: None)
    assert chain_mod._fetch_fear_greed() == (None, None)


def test_fetch_fear_greed_returns_none_on_unparsable_value(monkeypatch):
    monkeypatch.setattr(
        chain_mod,
        "_http_json",
        lambda url, timeout=10.0: {"data": [{"value": "not-a-number"}]},
    )
    assert chain_mod._fetch_fear_greed() == (None, None)


def test_fetch_coingecko_global_extracts_data_dict(monkeypatch):
    payload = {"data": {"market_cap_percentage": {"btc": 51.0}}}
    monkeypatch.setattr(chain_mod, "_http_json", lambda url, timeout=10.0: payload)
    result = chain_mod._fetch_coingecko_global()
    assert result == {"market_cap_percentage": {"btc": 51.0}}


def test_fetch_coingecko_global_returns_none_when_data_missing(monkeypatch):
    monkeypatch.setattr(chain_mod, "_http_json", lambda url, timeout=10.0: {"meta": "x"})
    assert chain_mod._fetch_coingecko_global() is None


def test_fetch_coingecko_global_returns_none_on_non_dict(monkeypatch):
    monkeypatch.setattr(chain_mod, "_http_json", lambda url, timeout=10.0: ["not", "a", "dict"])
    assert chain_mod._fetch_coingecko_global() is None


def test_fetch_binance_funding_converts_to_percent(monkeypatch):
    monkeypatch.setattr(
        chain_mod,
        "_http_json",
        lambda url, timeout=6.0: {"lastFundingRate": "0.0001"},
    )
    result = chain_mod._fetch_binance_funding("BTCUSDT")
    assert result == pytest.approx(0.01)  # 0.0001 * 100


def test_fetch_binance_funding_handles_missing_field(monkeypatch):
    monkeypatch.setattr(chain_mod, "_http_json", lambda url, timeout=6.0: {"other": "field"})
    assert chain_mod._fetch_binance_funding("BTCUSDT") is None


def test_fetch_binance_funding_handles_unparsable_value(monkeypatch):
    monkeypatch.setattr(
        chain_mod,
        "_http_json",
        lambda url, timeout=6.0: {"lastFundingRate": "not_a_number"},
    )
    assert chain_mod._fetch_binance_funding("BTCUSDT") is None


def test_fetch_binance_funding_handles_non_dict(monkeypatch):
    monkeypatch.setattr(chain_mod, "_http_json", lambda url, timeout=6.0: None)
    assert chain_mod._fetch_binance_funding("BTCUSDT") is None


# ---------------------------------------------------------------------------
# _fetch_yf_close — yfinance is mocked, never imported live
# ---------------------------------------------------------------------------


def test_fetch_yf_close_returns_none_when_yfinance_unavailable(monkeypatch):
    """If yfinance is not installed, _fetch_yf_close returns (None, None)."""
    import builtins

    real_import = builtins.__import__

    def _fake_import(name, *args, **kwargs):
        if name == "yfinance":
            raise ImportError("no yfinance in this env")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _fake_import)
    assert chain_mod._fetch_yf_close("DX-Y.NYB") == (None, None)


# ---------------------------------------------------------------------------
# Scoring helpers — pure logic, no mocking needed
# ---------------------------------------------------------------------------


def test_score_fear_greed_none_input_returns_none():
    assert chain_mod._score_fear_greed(None) is None


@pytest.mark.parametrize(
    "value, expected_label_substr",
    [
        (5, "extreme fear"),
        (30, "fear"),
        (50, "neutral"),
        (65, "greed"),
        (95, "extreme greed"),
    ],
)
def test_score_fear_greed_label_thresholds(value, expected_label_substr):
    score, tag = chain_mod._score_fear_greed(value)
    assert expected_label_substr in tag
    # 0 → -1, 100 → +1, 50 → 0
    assert score == pytest.approx((value - 50) / 50.0)


def test_score_fear_greed_boundary_19_is_extreme_fear():
    # Boundary: <20 → extreme fear, 20-39 → fear
    _score, tag = chain_mod._score_fear_greed(19)
    assert "extreme fear" in tag
    _score, tag = chain_mod._score_fear_greed(20)
    assert "fear" in tag and "extreme" not in tag


def test_score_fear_greed_boundary_79_is_greed_not_extreme():
    _score, tag = chain_mod._score_fear_greed(79)
    assert "greed" in tag and "extreme" not in tag
    _score, tag = chain_mod._score_fear_greed(80)
    assert "extreme greed" in tag


def test_score_funding_none_inputs_returns_none():
    assert chain_mod._score_funding(None, None) is None


def test_score_funding_uses_only_btc_when_eth_missing():
    score, tag = chain_mod._score_funding(0.05, None)
    # avg = 0.05 → score = clamp(0.05 / 0.05) = +1.0
    assert score == pytest.approx(1.0)
    assert "0.050" in tag


def test_score_funding_uses_only_eth_when_btc_missing():
    score, _tag = chain_mod._score_funding(None, -0.05)
    assert score == pytest.approx(-1.0)


def test_score_funding_averages_both():
    score, tag = chain_mod._score_funding(0.02, 0.04)
    # avg = 0.03 → score = 0.03/0.05 = 0.6
    assert score == pytest.approx(0.6)
    assert "0.030" in tag


def test_score_funding_clamps_to_unit_interval():
    score, _ = chain_mod._score_funding(1.0, 1.0)
    assert score == 1.0
    score, _ = chain_mod._score_funding(-1.0, -1.0)
    assert score == -1.0


def test_score_dominance_none_returns_none():
    assert chain_mod._score_dominance(None) is None


def test_score_dominance_inverts_sign():
    # Rising BTC dominance is risk-off → negative score
    pos, _ = chain_mod._score_dominance(1.5)
    neg, _ = chain_mod._score_dominance(-1.5)
    assert pos == pytest.approx(-1.0)
    assert neg == pytest.approx(1.0)


def test_score_mcap_change_none_returns_none():
    assert chain_mod._score_mcap_change(None) is None


def test_score_mcap_change_clamp_and_scale():
    s_high, _ = chain_mod._score_mcap_change(10.0)  # > 3.0 → clamps to +1
    s_mid, _ = chain_mod._score_mcap_change(1.5)  # → 0.5
    s_low, _ = chain_mod._score_mcap_change(-10.0)  # < -3.0 → clamps to -1
    assert s_high == 1.0
    assert s_mid == pytest.approx(0.5)
    assert s_low == -1.0


def test_score_dxy_inverts_sign_and_clamps():
    s_strong_dollar, _ = chain_mod._score_dxy(0.7)
    s_weak_dollar, _ = chain_mod._score_dxy(-0.7)
    s_extreme, _ = chain_mod._score_dxy(2.0)
    assert s_strong_dollar == pytest.approx(-1.0)
    assert s_weak_dollar == pytest.approx(1.0)
    assert s_extreme == pytest.approx(-1.0)  # clamped


def test_score_dxy_none_returns_none():
    assert chain_mod._score_dxy(None) is None


def test_score_vix_low_is_risk_on():
    # VIX 10 → (20-10)/10 = +1 (risk-on)
    score, tag = chain_mod._score_vix(10.0)
    assert score == pytest.approx(1.0)
    assert "VIX=10.0" in tag


def test_score_vix_high_is_risk_off():
    score, _ = chain_mod._score_vix(35.0)  # (20-35)/10 = -1.5 → clamp to -1
    assert score == -1.0


def test_score_vix_at_baseline_returns_zero():
    score, _ = chain_mod._score_vix(20.0)
    assert score == 0.0


def test_score_vix_none_returns_none():
    assert chain_mod._score_vix(None) is None


# ---------------------------------------------------------------------------
# classify() — branch coverage for regime thresholds
# ---------------------------------------------------------------------------


def test_classify_no_inputs_returns_neutral_with_marker():
    c = chain_mod.classify({})
    assert c.regime == Regime.NEUTRAL
    assert c.score == 0.0
    assert c.inputs_ok == 0
    assert c.inputs_total == 6
    assert c.reasons == ["no inputs available"]


def test_classify_score_at_or_above_025_is_risk_on():
    """Boundary: score >= 0.25 → RISK_ON."""
    # Single greed signal at FG=63 → score = (63-50)/50 = 0.26
    c = chain_mod.classify({"fear_greed": 63})
    assert c.score >= 0.25
    assert c.regime == Regime.RISK_ON


def test_classify_score_at_or_below_neg_025_is_risk_off():
    """Boundary: score <= -0.25 → RISK_OFF."""
    c = chain_mod.classify({"fear_greed": 37})  # (37-50)/50 = -0.26
    assert c.score <= -0.25
    assert c.regime == Regime.RISK_OFF


def test_classify_score_in_neutral_band():
    """A small positive that does not reach the +0.25 threshold → NEUTRAL."""
    # FG=55 → 0.1 → NEUTRAL
    c = chain_mod.classify({"fear_greed": 55})
    assert c.regime == Regime.NEUTRAL
    assert -0.25 < c.score < 0.25


def test_classify_input_counts_partial():
    c = chain_mod.classify({"fear_greed": 50, "vix": 20.0})
    assert c.inputs_ok == 2
    assert c.inputs_total == 6


def test_classify_funding_pair_counts_as_one_input():
    """The (btc, eth) funding pair is *one* scorer, not two."""
    c = chain_mod.classify({"btc_funding_rate_pct": 0.01, "eth_funding_rate_pct": 0.02})
    assert c.inputs_ok == 1


def test_classify_score_rounded_to_three_decimals():
    c = chain_mod.classify({"fear_greed": 63})
    # score = 0.26 exactly when reduced to 3dp
    assert c.score == round(c.score, 3)


def test_classify_reasons_match_input_count():
    c = chain_mod.classify({"fear_greed": 50, "vix": 20.0})
    assert len(c.reasons) == 2
    assert any("Fear&Greed" in r for r in c.reasons)
    assert any("VIX" in r for r in c.reasons)


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------


def test_read_last_state_returns_none_when_file_missing(isolated_data):
    assert chain_mod._read_last_state() is None


def test_read_last_state_parses_valid_json(isolated_data):
    chain_mod.LAST_STATE_FILE.write_text(json.dumps({"regime": "RISK_ON", "score": 0.4}))
    state = chain_mod._read_last_state()
    assert state == {"regime": "RISK_ON", "score": 0.4}


def test_read_last_state_returns_none_on_corrupt_json(isolated_data):
    chain_mod.LAST_STATE_FILE.write_text("{bad json")
    assert chain_mod._read_last_state() is None


def _make_snapshot(regime: Regime = Regime.RISK_ON, score: float = 0.4) -> ChainSnapshot:
    return ChainSnapshot(
        timestamp="2026-04-27T00:00:00+00:00",
        unix_ts=1000,
        fear_greed=70,
        fear_greed_label="greed",
        btc_dominance=52.0,
        btc_dominance_24h_change=0.1,
        total_mcap_usd=2.4e12,
        total_mcap_24h_change_pct=1.0,
        btc_funding_rate_pct=0.01,
        eth_funding_rate_pct=0.005,
        dxy=104.0,
        dxy_1d_change_pct=-0.1,
        vix=15.0,
        vix_1d_change_pct=None,
        classification=RegimeClassification(
            regime=regime,
            score=score,
            reasons=["Fear&Greed=70 (greed)"],
            inputs_ok=1,
            inputs_total=6,
        ),
    )


def test_write_last_state_persists_minimal_payload(isolated_data):
    snap = _make_snapshot()
    chain_mod._write_last_state(snap)
    state = json.loads(chain_mod.LAST_STATE_FILE.read_text())
    assert state["regime"] == "RISK_ON"
    assert state["score"] == 0.4
    assert state["unix_ts"] == 1000


def test_append_history_writes_jsonl_entry_with_required_fields(isolated_data):
    snap = _make_snapshot()
    chain_mod._append_history(snap)
    lines = chain_mod.HISTORY_FILE.read_text().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    # Contract enforced by correlation engine: kind/state/unix_ts must exist
    assert entry["kind"] == "regime"
    assert entry["state"] == "RISK_ON"
    assert isinstance(entry["unix_ts"], int)
    assert entry["data"]["fear_greed"] == 70


def test_append_history_appends_without_overwriting(isolated_data):
    snap1 = _make_snapshot(regime=Regime.RISK_ON, score=0.3)
    snap2 = _make_snapshot(regime=Regime.RISK_OFF, score=-0.4)
    chain_mod._append_history(snap1)
    chain_mod._append_history(snap2)
    lines = chain_mod.HISTORY_FILE.read_text().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["state"] == "RISK_ON"
    assert json.loads(lines[1])["state"] == "RISK_OFF"


# ---------------------------------------------------------------------------
# Alerting helpers — subprocess + Pub/Sub
# ---------------------------------------------------------------------------


def test_send_telegram_invokes_subprocess_with_priority():
    with patch.object(chain_mod.subprocess, "run") as run:
        chain_mod._send_telegram("hello world", priority="p0")
    assert run.call_count == 1
    args, kwargs = run.call_args
    cmd = args[0]
    assert "hello world" in cmd
    assert "--priority" in cmd
    assert "p0" in cmd
    assert kwargs["check"] is False


def test_send_telegram_swallows_subprocess_errors():
    """Notify failure should never propagate — alerting is best-effort."""
    with patch.object(chain_mod.subprocess, "run", side_effect=OSError("notify binary missing")):
        # No exception should bubble up
        chain_mod._send_telegram("hi", priority="p1")


def test_publish_pubsub_skipped_when_env_disabled(monkeypatch):
    """SAPPHIRE_PUBSUB=0 must short-circuit before any client import."""
    monkeypatch.setenv("SAPPHIRE_PUBSUB", "0")
    # Sentinel: if it tries to import the client module, asyncio.run would be called
    with patch("asyncio.run") as asyncio_run:
        chain_mod._publish_pubsub("risk-alerts", {"foo": "bar"})
    assert asyncio_run.call_count == 0


def test_publish_pubsub_swallows_import_errors(monkeypatch):
    """A missing pubsub client must not propagate."""
    monkeypatch.setenv("SAPPHIRE_PUBSUB", "1")
    # Force an ImportError by clobbering sapphire_core.pubsub.client lookup
    import builtins

    real_import = builtins.__import__

    def _fake_import(name, *args, **kwargs):
        if name.startswith("sapphire_core.pubsub"):
            raise ImportError("not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _fake_import)
    # Should return cleanly
    chain_mod._publish_pubsub("risk-alerts", {"foo": "bar"})


# ---------------------------------------------------------------------------
# Dataclasses — round-trip + sentinel construction
# ---------------------------------------------------------------------------


def test_regime_classification_defaults_initialise_empty_reasons():
    rc = RegimeClassification(regime=Regime.NEUTRAL, score=0.0)
    assert rc.reasons == []
    assert rc.inputs_ok == 0
    assert rc.inputs_total == 0


def test_regime_enum_value_is_serialisable():
    assert Regime.RISK_ON.value == "RISK_ON"
    assert Regime("RISK_OFF") is Regime.RISK_OFF
    # JSON round-trip
    assert json.dumps(Regime.NEUTRAL.value) == '"NEUTRAL"'


def test_regime_shift_event_holds_all_fields():
    e = RegimeShiftEvent(
        from_regime=Regime.RISK_ON,
        to_regime=Regime.RISK_OFF,
        from_score=0.4,
        to_score=-0.4,
        timestamp="2026-04-27T00:00:00+00:00",
        reasons=["VIX=28.0"],
    )
    assert e.from_regime == Regime.RISK_ON
    assert e.to_regime == Regime.RISK_OFF
    assert e.reasons == ["VIX=28.0"]


# ---------------------------------------------------------------------------
# ChainIntelligence._handle_shift — composes alerts via mocked deps
# ---------------------------------------------------------------------------


def test_handle_shift_calls_telegram_and_pubsub():
    snap = _make_snapshot()
    shift = RegimeShiftEvent(
        from_regime=Regime.RISK_ON,
        to_regime=Regime.RISK_OFF,
        from_score=0.4,
        to_score=-0.4,
        timestamp="2026-04-27T00:00:00+00:00",
        reasons=["VIX=28.0", "Fear&Greed=10 (extreme fear)"],
    )

    with (
        patch.object(chain_mod, "_send_telegram") as tg,
        patch.object(chain_mod, "_publish_pubsub") as ps,
    ):
        ChainIntelligence()._handle_shift(shift, snap)

    tg.assert_called_once()
    (msg,) = tg.call_args.args
    assert "Regime shift" in msg
    assert "RISK_ON" in msg and "RISK_OFF" in msg
    assert "VIX=28.0" in msg
    assert tg.call_args.kwargs.get("priority") == "p0"

    ps.assert_called_once()
    topic, payload = ps.call_args.args
    assert topic == "risk-alerts"
    assert payload["kind"] == "regime_shift"
    assert payload["from"] == "RISK_ON"
    assert payload["to"] == "RISK_OFF"
    assert payload["snapshot"]["fear_greed"] == 70
