"""chain_refresh publishes events off the FLAT chain snapshot shape.

`ChainIntelligence.snapshot()` emits a flat dict (`classification`,
`btc_funding_rate_pct`, …). The refresh service used to read a nested shape
(`snap["regime"]["state"]`, `snap["funding"]["perps"]`) that snapshot() has
never produced, so every `regime.snapshot` event carried regime="UNKNOWN"
and `regime.shifted` / `funding.extreme` never fired — silently disabling
the whole downstream subscriber tree (decision_engine, dashboard, alerts).
Same defect class as the sentiment.py and signal_enhancer.py bugs.

These tests pin the real shape so the drift cannot return.
"""

from __future__ import annotations

import json

import pytest

from services.pipeline import chain_refresh


def _flat_snapshot(
    *,
    regime: str = "NEUTRAL",
    score: float = 0.0,
    inputs_ok: int = 6,
    inputs_total: int = 6,
    btc_pct: float | None = 0.01,
    eth_pct: float | None = 0.01,
    timestamp: str = "2026-07-25T12:00:00+00:00",
) -> dict:
    """A snapshot in the exact shape ChainIntelligence.snapshot() returns."""
    return {
        "timestamp": timestamp,
        "unix_ts": 1785585600,
        "fear_greed": 50,
        "fear_greed_label": "neutral",
        "btc_dominance": 56.5,
        "btc_dominance_24h_change": None,
        "total_mcap_usd": None,
        "total_mcap_24h_change_pct": None,
        "btc_funding_rate_pct": btc_pct,
        "eth_funding_rate_pct": eth_pct,
        "dxy": None,
        "dxy_1d_change_pct": None,
        "vix": None,
        "vix_1d_change_pct": None,
        "classification": {
            "regime": regime,
            "score": score,
            "reasons": [],
            "inputs_ok": inputs_ok,
            "inputs_total": inputs_total,
        },
    }


# ---------------------------------------------------------------------------
# _regime_state — flat shape + enum unwrap
# ---------------------------------------------------------------------------


def test_regime_state_reads_flat_classification():
    snap = _flat_snapshot(regime="RISK_ON")
    assert chain_refresh._regime_state(snap) == "RISK_ON"


def test_regime_state_unwraps_enum():
    """In-process the regime is a `Regime` enum; JSON round-trip flattens it."""
    from lib.chain.intelligence import Regime

    snap = _flat_snapshot()
    snap["classification"]["regime"] = Regime.RISK_OFF
    assert chain_refresh._regime_state(snap) == "RISK_OFF"


def test_regime_state_returns_unknown_when_classification_missing():
    assert chain_refresh._regime_state({"timestamp": "x"}) == "UNKNOWN"
    assert chain_refresh._regime_state({"classification": {}}) == "UNKNOWN"
    assert chain_refresh._regime_state({"classification": {"regime": None}}) == "UNKNOWN"


def test_regime_state_returns_unknown_for_nested_legacy_shape():
    """The exact bug that motivates this test file: a nested `regime.state`
    payload must NOT masquerade as a valid regime — it should read UNKNOWN
    so downstream sees the gap instead of silently accepting garbage."""
    snap = {"regime": {"state": "RISK_ON", "score": 0.5}}
    assert chain_refresh._regime_state(snap) == "UNKNOWN"


# ---------------------------------------------------------------------------
# _regime_confidence — inputs_ok / inputs_total
# ---------------------------------------------------------------------------


def test_regime_confidence_derived_from_input_counts():
    snap = _flat_snapshot(inputs_ok=3, inputs_total=6)
    assert chain_refresh._regime_confidence(snap) == pytest.approx(0.5)


def test_regime_confidence_none_when_inputs_total_missing():
    snap = _flat_snapshot()
    snap["classification"]["inputs_total"] = 0
    assert chain_refresh._regime_confidence(snap) is None


def test_regime_confidence_none_when_classification_absent():
    assert chain_refresh._regime_confidence({}) is None


# ---------------------------------------------------------------------------
# _build_perps — flat scalars → per-coin dicts with the right flag + unit
# ---------------------------------------------------------------------------


def test_build_perps_from_flat_funding_rates():
    snap = _flat_snapshot(btc_pct=0.08, eth_pct=0.01)
    perps = chain_refresh._build_perps(snap)
    assert {p["coin"] for p in perps} == {"BTC", "ETH"}
    btc = next(p for p in perps if p["coin"] == "BTC")
    # 0.08% -> 0.0008 stored as fraction (matches signal_enhancer convention)
    assert btc["funding_rate_8h"] == pytest.approx(0.0008)
    assert btc["extreme_flag"] == "crowded_long"
    eth = next(p for p in perps if p["coin"] == "ETH")
    assert eth["extreme_flag"] is None  # 0.01% below elevated threshold


def test_build_perps_skips_missing_rates():
    """Missing rate must not appear as 0 — that would fake a "no funding" reading."""
    snap = _flat_snapshot(btc_pct=None, eth_pct=0.05)
    perps = chain_refresh._build_perps(snap)
    assert [p["coin"] for p in perps] == ["ETH"]


def test_build_perps_skips_unparseable_rates():
    snap = _flat_snapshot(btc_pct="not_a_number", eth_pct=None)
    assert chain_refresh._build_perps(snap) == []


def test_build_perps_flag_thresholds_mirror_signal_enhancer():
    """crowded/elevated thresholds must be the same the enhancer uses;
    the bug we're fixing came from a threshold drift in that direction."""
    assert (
        chain_refresh._build_perps(_flat_snapshot(btc_pct=0.06, eth_pct=None))[0]["extreme_flag"]
        == "crowded_long"
    )
    assert (
        chain_refresh._build_perps(_flat_snapshot(btc_pct=-0.06, eth_pct=None))[0]["extreme_flag"]
        == "crowded_short"
    )
    assert (
        chain_refresh._build_perps(_flat_snapshot(btc_pct=0.03, eth_pct=None))[0]["extreme_flag"]
        == "elevated_long"
    )
    assert (
        chain_refresh._build_perps(_flat_snapshot(btc_pct=-0.03, eth_pct=None))[0]["extreme_flag"]
        == "elevated_short"
    )


# ---------------------------------------------------------------------------
# _prior_regime_state — reads the last chain.json in FLAT shape
# ---------------------------------------------------------------------------


def test_prior_regime_state_reads_flat_classification_from_disk(tmp_path, monkeypatch):
    latest_dir = tmp_path / "latest"
    latest_dir.mkdir()
    (latest_dir / "chain.json").write_text(json.dumps(_flat_snapshot(regime="RISK_ON")))
    monkeypatch.setattr(chain_refresh, "LATEST_DIR", latest_dir)
    assert chain_refresh._prior_regime_state() == "RISK_ON"


def test_prior_regime_state_returns_none_when_no_file(tmp_path, monkeypatch):
    latest_dir = tmp_path / "latest"
    latest_dir.mkdir()
    monkeypatch.setattr(chain_refresh, "LATEST_DIR", latest_dir)
    assert chain_refresh._prior_regime_state() is None


def test_prior_regime_state_treats_legacy_nested_shape_as_no_prior(tmp_path, monkeypatch):
    """Legacy chain.json written by the broken code had no `classification`.
    Reading that as "UNKNOWN" would trigger spurious regime.shifted events on
    the first fresh run; instead we report no prior."""
    latest_dir = tmp_path / "latest"
    latest_dir.mkdir()
    (latest_dir / "chain.json").write_text(json.dumps({"regime": {"state": "RISK_ON"}}))
    monkeypatch.setattr(chain_refresh, "LATEST_DIR", latest_dir)
    assert chain_refresh._prior_regime_state() is None


def test_prior_regime_state_swallows_corrupt_json(tmp_path, monkeypatch):
    latest_dir = tmp_path / "latest"
    latest_dir.mkdir()
    (latest_dir / "chain.json").write_text("{not json")
    monkeypatch.setattr(chain_refresh, "LATEST_DIR", latest_dir)
    assert chain_refresh._prior_regime_state() is None


# ---------------------------------------------------------------------------
# _publish_events — the whole downstream contract
# ---------------------------------------------------------------------------


class _FakeBus:
    def __init__(self):
        self.published: list[tuple[str, dict, str | None]] = []

    def publish(self, event_type, payload, source=None):
        self.published.append((event_type, payload, source))


@pytest.fixture
def fake_bus(monkeypatch):
    bus = _FakeBus()
    monkeypatch.setattr("lib.core.event_bus.get_bus", lambda: bus)
    return bus


def test_publish_regime_snapshot_carries_actual_regime(fake_bus):
    snap = _flat_snapshot(regime="RISK_ON", score=0.6, inputs_ok=5, inputs_total=6)
    chain_refresh._publish_events(snap, prior_state=None)
    snapshots = [(t, p) for t, p, _ in fake_bus.published if t == "regime.snapshot"]
    assert len(snapshots) == 1
    payload = snapshots[0][1]
    assert payload["regime"] == "RISK_ON"
    assert payload["score"] == 0.6
    assert payload["confidence"] == pytest.approx(5 / 6)
    assert payload["since"] == "2026-07-25T12:00:00+00:00"


def test_publish_regime_shifted_on_state_change(fake_bus):
    snap = _flat_snapshot(regime="RISK_OFF")
    chain_refresh._publish_events(snap, prior_state="RISK_ON")
    shifted = [(t, p) for t, p, _ in fake_bus.published if t == "regime.shifted"]
    assert len(shifted) == 1
    assert shifted[0][1]["prior"] == "RISK_ON"
    assert shifted[0][1]["regime"] == "RISK_OFF"


def test_publish_no_regime_shifted_when_state_unchanged(fake_bus):
    snap = _flat_snapshot(regime="RISK_ON")
    chain_refresh._publish_events(snap, prior_state="RISK_ON")
    assert not any(t == "regime.shifted" for t, _, _ in fake_bus.published)


def test_publish_no_regime_shifted_when_current_unknown(fake_bus):
    """Silent 'shift' from a real prior into UNKNOWN would spam operators
    every time the classifier fails — that's just an outage, not a shift."""
    snap = _flat_snapshot()
    snap["classification"] = {}  # UNKNOWN
    chain_refresh._publish_events(snap, prior_state="RISK_ON")
    assert not any(t == "regime.shifted" for t, _, _ in fake_bus.published)


def test_publish_funding_extreme_when_btc_crowded(fake_bus):
    snap = _flat_snapshot(btc_pct=0.09, eth_pct=0.01)
    chain_refresh._publish_events(snap, prior_state=None)
    extremes = [(t, p) for t, p, _ in fake_bus.published if t == "funding.extreme"]
    assert len(extremes) == 1
    payload = extremes[0][1]
    assert payload["count"] == 1
    assert payload["crowded_count"] == 1
    assert payload["bias"] == "long"
    assert payload["perps"] == [
        {"coin": "BTC", "rate_8h": pytest.approx(0.0009), "flag": "crowded_long"}
    ]


def test_publish_funding_extreme_bias_short_when_shorts_dominant(fake_bus):
    snap = _flat_snapshot(btc_pct=-0.09, eth_pct=-0.09)
    chain_refresh._publish_events(snap, prior_state=None)
    payload = next(p for t, p, _ in fake_bus.published if t == "funding.extreme")
    assert payload["bias"] == "short"
    assert payload["count"] == 2


def test_publish_no_funding_extreme_when_rates_calm(fake_bus):
    snap = _flat_snapshot(btc_pct=0.01, eth_pct=0.005)
    chain_refresh._publish_events(snap, prior_state=None)
    assert not any(t == "funding.extreme" for t, _, _ in fake_bus.published)


# ---------------------------------------------------------------------------
# run() — end-to-end shape verification, using the same fake bus
# ---------------------------------------------------------------------------


def test_run_returns_actual_regime_state(tmp_path, monkeypatch, fake_bus):
    monkeypatch.setattr(chain_refresh, "CHAIN_DIR", tmp_path / "chain")
    monkeypatch.setattr(chain_refresh, "LATEST_DIR", tmp_path / "latest")

    snap = _flat_snapshot(regime="RISK_ON", score=0.55)

    class _StubIntel:
        def snapshot(self):
            return snap

    monkeypatch.setattr(chain_refresh, "ChainIntelligence", _StubIntel)
    out = chain_refresh.run()
    assert out["regime"] == "RISK_ON"
    # Pre-fix, this was always None because run() read the wrong key.
    assert out["regime"] is not None
    assert out["shifted"] is False  # no prior state on first run


def test_run_uses_snapshot_timestamp_not_generated_at(tmp_path, monkeypatch, fake_bus):
    """Pre-fix: run() read `snap["generated_at"]` (which never exists) and
    silently overwrote timestamp with `datetime.now()` — losing the actual
    snapshot time and confusing the persisted chain_<ISO>.json filename."""
    monkeypatch.setattr(chain_refresh, "CHAIN_DIR", tmp_path / "chain")
    monkeypatch.setattr(chain_refresh, "LATEST_DIR", tmp_path / "latest")

    fixed_ts = "2026-07-25T12:00:00+00:00"
    snap = _flat_snapshot(timestamp=fixed_ts)

    class _StubIntel:
        def snapshot(self):
            return snap

    monkeypatch.setattr(chain_refresh, "ChainIntelligence", _StubIntel)
    out = chain_refresh.run()
    # Persisted filename encodes the *snapshot* timestamp, not now().
    assert fixed_ts.replace(":", "-") in out["path"]
    # Persisted chain.json also carries that exact timestamp.
    persisted = json.loads((tmp_path / "latest" / "chain.json").read_text())
    assert persisted["timestamp"] == fixed_ts
