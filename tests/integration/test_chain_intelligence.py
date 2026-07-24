"""Integration tests for the on-chain intelligence loop.

Covers the regime classifier, persistence, and shift detection without
hitting the network (all external fetches are monkeypatched).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.chain import ChainIntelligence, Regime  # noqa: E402
from lib.chain import intelligence as chain_mod  # noqa: E402


@pytest.fixture
def isolated_data(tmp_path, monkeypatch):
    """Redirect data/chain writes into a tmp dir."""
    data_dir = tmp_path / "chain"
    data_dir.mkdir()
    monkeypatch.setattr(chain_mod, "DATA_DIR", data_dir)
    monkeypatch.setattr(chain_mod, "HISTORY_FILE", data_dir / "history.jsonl")
    monkeypatch.setattr(chain_mod, "LAST_STATE_FILE", data_dir / "last_state.json")
    return data_dir


@pytest.fixture
def mock_sources(monkeypatch):
    """Stub out all network-touching fetch helpers with deterministic data."""
    bag = {
        "fear_greed": (62, "greed"),
        "coingecko": {
            "market_cap_percentage": {"btc": 52.3},
            "total_market_cap": {"usd": 2.4e12},
            "market_cap_change_percentage_24h_usd": 1.2,
        },
        "binance": {"BTCUSDT": 0.012, "ETHUSDT": 0.008},
        "yf": {
            "DX-Y.NYB": (104.2, -0.15),
            "^VIX": (14.8, None),
        },
    }

    def _fg():
        return bag["fear_greed"]

    def _cg():
        return bag["coingecko"]

    def _binance(symbol):
        return bag["binance"].get(symbol)

    def _yf(ticker):
        return bag["yf"].get(ticker, (None, None))

    monkeypatch.setattr(chain_mod, "_fetch_fear_greed", _fg)
    monkeypatch.setattr(chain_mod, "_fetch_coingecko_global", _cg)
    monkeypatch.setattr(chain_mod, "_fetch_binance_funding", _binance)
    monkeypatch.setattr(chain_mod, "_fetch_yf_close", _yf)

    # Silence telegram + pubsub — do NOT hit the network during tests.
    monkeypatch.setattr(chain_mod, "_send_telegram", lambda *a, **k: None)
    monkeypatch.setattr(chain_mod, "_publish_pubsub", lambda *a, **k: None)

    return bag


# ---------------------------------------------------------------------------
# classify()
# ---------------------------------------------------------------------------


def test_classify_risk_off_on_extreme_fear():
    c = chain_mod.classify(
        {
            "fear_greed": 12,
            "btc_funding_rate_pct": -0.03,
            "eth_funding_rate_pct": -0.02,
            "btc_dominance_24h_change": 2.0,
            "total_mcap_24h_change_pct": -4.5,
            "dxy_1d_change_pct": 0.9,
            "vix": 28.0,
        }
    )
    assert c.regime == Regime.RISK_OFF
    assert c.score < -0.3
    assert c.inputs_ok == 6


def test_classify_risk_on_on_greed():
    c = chain_mod.classify(
        {
            "fear_greed": 82,
            "btc_funding_rate_pct": 0.015,
            "eth_funding_rate_pct": 0.012,
            "btc_dominance_24h_change": -0.5,
            "total_mcap_24h_change_pct": 3.0,
            "dxy_1d_change_pct": -0.3,
            "vix": 13.0,
        }
    )
    assert c.regime == Regime.RISK_ON
    assert c.score > 0.25


def test_classify_neutral_no_inputs():
    c = chain_mod.classify({})
    assert c.regime == Regime.NEUTRAL
    assert c.inputs_ok == 0
    assert "no inputs" in " ".join(c.reasons).lower()


def test_classify_partial_inputs_still_works():
    c = chain_mod.classify({"fear_greed": 45, "vix": 19.0})
    # 1 bucket slightly fearful, 1 near baseline VIX → around neutral
    assert c.inputs_ok == 2
    assert c.regime in (Regime.NEUTRAL, Regime.RISK_ON, Regime.RISK_OFF)


# ---------------------------------------------------------------------------
# snapshot() end-to-end
# ---------------------------------------------------------------------------


def test_snapshot_writes_history_and_last_state(isolated_data, mock_sources):
    ci = ChainIntelligence()
    snap = ci.snapshot(alert_on_shift=True)

    assert snap["classification"]["inputs_ok"] >= 5
    assert snap["timestamp"]
    assert (isolated_data / "history.jsonl").exists()
    assert (isolated_data / "last_state.json").exists()

    last = json.loads((isolated_data / "last_state.json").read_text(encoding="utf-8"))
    assert last["regime"] == snap["classification"]["regime"]


def test_snapshot_detects_regime_shift(isolated_data, mock_sources, monkeypatch):
    """Two consecutive snapshots with different regimes should emit a shift."""
    shift_events = []

    def _recording_handler(self, shift, snap):
        shift_events.append((shift.from_regime, shift.to_regime))

    monkeypatch.setattr(ChainIntelligence, "_handle_shift", _recording_handler)

    ci = ChainIntelligence()

    # Snapshot 1: risk-on setup
    snap1 = ci.snapshot(alert_on_shift=True)
    assert snap1["classification"]["regime"] == "RISK_ON"
    assert "regime_shift" not in snap1  # no prior state

    # Flip to risk-off
    mock_sources["fear_greed"] = (10, "extreme fear")
    mock_sources["binance"] = {"BTCUSDT": -0.04, "ETHUSDT": -0.03}
    mock_sources["yf"] = {"DX-Y.NYB": (105.0, 0.9), "^VIX": (29.0, None)}
    mock_sources["coingecko"] = {
        "market_cap_percentage": {"btc": 55.0},
        "total_market_cap": {"usd": 2.3e12},
        "market_cap_change_percentage_24h_usd": -5.2,
    }

    snap2 = ci.snapshot(alert_on_shift=True)
    assert snap2["classification"]["regime"] == "RISK_OFF"
    assert "regime_shift" in snap2
    assert snap2["regime_shift"]["from"] == "RISK_ON"
    assert snap2["regime_shift"]["to"] == "RISK_OFF"
    assert shift_events == [(Regime.RISK_ON, Regime.RISK_OFF)]


def test_snapshot_no_shift_on_same_regime(isolated_data, mock_sources):
    ci = ChainIntelligence()
    s1 = ci.snapshot()
    s2 = ci.snapshot()
    assert s1["classification"]["regime"] == s2["classification"]["regime"]
    assert "regime_shift" not in s2


def test_history_jsonl_structure_matches_correlation_engine_expectation(
    isolated_data, mock_sources
):
    ci = ChainIntelligence()
    ci.snapshot()
    lines = (isolated_data / "history.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert lines
    entry = json.loads(lines[-1])
    # correlation.py regime_adjusted_matrices() requires kind, state, unix_ts
    assert entry["kind"] == "regime"
    assert entry["state"] in ("RISK_ON", "RISK_OFF", "NEUTRAL")
    assert isinstance(entry["unix_ts"], int)
