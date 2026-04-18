"""Unit tests for lib.analytics: correlation, signal_enhancer, risk_engine, kelly."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# kelly_size
# ---------------------------------------------------------------------------


def test_kelly_size_quarter_mode():
    from lib.analytics.risk_engine import kelly_size

    # 60% win rate, 2:1 R:R, $10k bankroll, quarter-Kelly
    # Raw f* = 0.6 - 0.4/2 = 0.4 → quarter = 0.10 → $1,000
    size = kelly_size(0.60, 200.0, 100.0, 10000.0, mode="quarter")
    assert 900 <= size <= 1100


def test_kelly_size_negative_expectancy_returns_zero():
    from lib.analytics.risk_engine import kelly_size

    # 30% win rate, 1:1 R:R → negative Kelly → should return 0
    size = kelly_size(0.30, 100.0, 100.0, 10000.0, mode="quarter")
    assert size == 0.0


def test_kelly_size_caps_at_25_percent():
    from lib.analytics.risk_engine import kelly_size

    # Extreme edge: 95% win rate, 10:1 → raw Kelly 0.945 → full mode capped at 25%
    size = kelly_size(0.95, 1000.0, 100.0, 10000.0, mode="full")
    assert size == 2500.0  # 25% of $10k


def test_kelly_size_rejects_zero_avg_loss():
    from lib.analytics.risk_engine import kelly_size
    assert kelly_size(0.7, 100.0, 0.0, 10000.0) == 0.0


# ---------------------------------------------------------------------------
# RiskEngine — synthetic data path
# ---------------------------------------------------------------------------


def test_risk_engine_with_empty_data(tmp_path, monkeypatch):
    """RiskEngine with no trades → None/0 metrics but doesn't crash."""
    from lib.analytics import risk_engine as re_mod

    monkeypatch.setattr(re_mod, "PAPER_LOG", tmp_path / "paper.jsonl")
    monkeypatch.setattr(re_mod, "SIGNALS_DIR", tmp_path / "signals")

    m = re_mod.RiskEngine(bankroll=10000.0).compute()
    assert m.total_trades == 0
    assert m.win_rate is None
    assert m.sharpe is None
    assert m.max_drawdown_pct == 0.0
    # Kelly falls back to defaults
    assert m.recommended_size_usd > 0


def test_risk_engine_computes_drawdown(tmp_path, monkeypatch):
    from lib.analytics import risk_engine as re_mod

    signals_dir = tmp_path / "signals"
    signals_dir.mkdir()
    # 3 trades: +$500, +$200, -$400. Equity: 10k→10.5k→10.7k→10.3k
    # Peak = $10,700 at step 2, trough = $10,300 → DD = 400/10700 = 3.74%
    trades = [
        {"symbol": "BTC", "direction": "long", "outcome": "win",
         "pnl_usd": 500.0, "closed_at": "2026-04-10T10:00:00+00:00"},
        {"symbol": "BTC", "direction": "long", "outcome": "win",
         "pnl_usd": 200.0, "closed_at": "2026-04-11T10:00:00+00:00"},
        {"symbol": "BTC", "direction": "short", "outcome": "loss",
         "pnl_usd": -400.0, "closed_at": "2026-04-12T10:00:00+00:00"},
    ]
    (signals_dir / "2026-04-10.jsonl").write_text(
        "\n".join(json.dumps(t) for t in trades) + "\n"
    )
    monkeypatch.setattr(re_mod, "SIGNALS_DIR", signals_dir)
    monkeypatch.setattr(re_mod, "PAPER_LOG", tmp_path / "paper.jsonl")

    m = re_mod.RiskEngine(bankroll=10000.0).compute()
    assert m.total_trades == 3
    assert m.wins == 2
    assert m.losses == 1
    assert m.total_pnl_usd == 300.0
    assert m.win_rate == pytest.approx(0.667, abs=0.01)
    assert m.max_drawdown_pct == pytest.approx(0.0374, abs=0.001)
    assert m.max_drawdown_usd == pytest.approx(400.0)
    assert len(m.equity_curve) == 3
    # Final equity = $10,300
    assert m.equity_curve[-1]["equity_usd"] == 10300.0


# ---------------------------------------------------------------------------
# SignalEnhancer — regime logic
# ---------------------------------------------------------------------------


def test_signal_enhancer_regime_off_penalizes_long():
    from lib.analytics.signal_enhancer import SignalEnhancer

    eng = SignalEnhancer()
    eng._state_cache = {
        "regime": "RISK_OFF",
        "regime_score": -0.5,
        "regime_confidence": 0.8,
        "funding": {},
        "decorrelations": [],
    }
    eng._state_ts = 1e12  # far future → bypass TTL refresh

    es = eng.enhance("BTC", "buy", 0.80)
    assert es.original_confidence == 0.80
    # 0.80 × 0.80 penalty = 0.64
    assert es.adjusted_confidence == pytest.approx(0.64, abs=0.01)
    assert "regime_contradiction" in es.flags


def test_signal_enhancer_regime_on_boosts_long():
    from lib.analytics.signal_enhancer import SignalEnhancer

    eng = SignalEnhancer()
    eng._state_cache = {
        "regime": "RISK_ON",
        "regime_score": 0.5,
        "regime_confidence": 0.7,
        "funding": {},
        "decorrelations": [],
    }
    eng._state_ts = 1e12

    es = eng.enhance("BTC", "buy", 0.60)
    # 0.60 × 1.05 boost = 0.63
    assert es.adjusted_confidence == pytest.approx(0.63, abs=0.01)
    assert "regime_contradiction" not in es.flags


def test_signal_enhancer_flags_crowded_long():
    from lib.analytics.signal_enhancer import SignalEnhancer

    eng = SignalEnhancer()
    eng._state_cache = {
        "regime": "TRANSITION",
        "regime_score": 0.0,
        "regime_confidence": 0.0,
        "funding": {"BTC": (0.0008, "crowded_long")},  # extreme positive
        "decorrelations": [],
    }
    eng._state_ts = 1e12

    es = eng.enhance("BTC", "buy", 0.70)
    assert "crowded_entry" in es.flags
    assert es.funding_flag == "crowded_long"


def test_signal_enhancer_flags_decorrelation():
    from lib.analytics.signal_enhancer import SignalEnhancer

    eng = SignalEnhancer()
    eng._state_cache = {
        "regime": "TRANSITION",
        "regime_score": 0.0,
        "regime_confidence": 0.0,
        "funding": {},
        "decorrelations": [
            {"pair": ["BTC", "SPY"], "severity": "moderate",
             "note": "BTC↔SPY decoupled"},
        ],
    }
    eng._state_ts = 1e12

    es = eng.enhance("BTC", "buy", 0.70)
    assert "decorrelation_attention" in es.flags
    assert any("BTC↔SPY" in p for p in es.decorrelation_pairs)


def test_signal_enhancer_clamps_confidence():
    from lib.analytics.signal_enhancer import SignalEnhancer

    eng = SignalEnhancer()
    eng._state_cache = {
        "regime": "RISK_ON",
        "regime_score": 0.5,
        "regime_confidence": 0.9,
        "funding": {},
        "decorrelations": [],
    }
    eng._state_ts = 1e12

    es = eng.enhance("BTC", "buy", 0.99)
    # Capped at 0.99 max even with boost
    assert es.adjusted_confidence <= 0.99
