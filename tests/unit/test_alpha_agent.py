"""Tests for `lib/agents/alpha_agent.AlphaAgent`.

Covers the paper-only autonomous trading agent's plan/act/observe cycle:
constructor wiring, signal- and portfolio-loading edge cases, ATR-based
exit math, position-evaluation surface, event emission, and the
`_fetch_quote` market-tool subprocess shim.

Tests never hit the network and never load real Robinhood / market
credentials — every external dependency is injected (quote_fetcher,
close_hook, event_bus) or mocked via monkeypatch.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from lib.agents.alpha_agent import (
    FEE_RATE_PER_LEG,
    STOP_LOSS_ATR_MULT,
    TAKE_PROFIT_ATR_MULT,
    AlphaAgent,
)
from lib.agents.base import Action

# --- Helpers ----------------------------------------------------------------


class _RecordingBus:
    """Minimal event-bus stub matching the ``EventPublisher`` protocol."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def publish(
        self,
        event_type: str,
        data: dict[str, Any],
        source: str | None = None,
    ) -> str:
        self.calls.append({"event_type": event_type, "data": data, "source": source})
        return f"evt-{len(self.calls)}"


def _make_agent(
    tmp_path: Path,
    *,
    portfolio: dict[str, Any] | None = None,
    signal_lines: list[str] | None = None,
    quotes: dict[str, float] | None = None,
    quote_fetcher: Any = None,
    close_hook: Any = None,
    event_bus: Any = None,
    write_portfolio: bool = True,
) -> tuple[AlphaAgent, Path, Path]:
    """Build an ``AlphaAgent`` wired to ``tmp_path`` for hermetic tests."""
    signals_dir = tmp_path / "signals"
    signals_dir.mkdir(exist_ok=True)
    if signal_lines is not None:
        (signals_dir / "feed.jsonl").write_text("\n".join(signal_lines))

    portfolio_file = tmp_path / "paper_portfolio.json"
    if write_portfolio and portfolio is not None:
        portfolio_file.write_text(json.dumps(portfolio))

    market_tool = tmp_path / "market.py"  # never actually invoked

    if quote_fetcher is None and quotes is not None:
        captured_quotes = dict(quotes)

        def quote_fetcher(_symbols):
            return dict(captured_quotes)

    bus = event_bus if event_bus is not None else _RecordingBus()
    agent = AlphaAgent(
        signals_dir=signals_dir,
        portfolio_file=portfolio_file,
        market_tool=market_tool,
        quote_fetcher=quote_fetcher,
        close_hook=close_hook,
        event_bus=bus,
    )
    return agent, signals_dir, portfolio_file


# --- Constructor surface ----------------------------------------------------


def test_constructor_sets_defaults_without_touching_filesystem(monkeypatch, tmp_path):
    # Avoid the production fallback path side effect of the default EventBus.
    bus = _RecordingBus()
    agent = AlphaAgent(
        event_bus=bus,
        signals_dir=tmp_path / "signals",
        portfolio_file=tmp_path / "p.json",
        market_tool=tmp_path / "market.py",
        quote_fetcher=lambda _syms: {},
    )

    assert agent.name == "alpha"
    assert agent.interval_sec == 300
    assert agent.event_bus is bus
    assert agent.signals_dir == tmp_path / "signals"
    assert agent.portfolio_file == tmp_path / "p.json"
    assert agent.market_tool == tmp_path / "market.py"
    assert agent._planned_signal_ids == []
    # Quote fetcher / close hook are stored as private callables.
    assert callable(agent._quote_fetcher)
    assert callable(agent._close_hook)


def test_constructor_accepts_custom_interval(tmp_path):
    bus = _RecordingBus()
    agent = AlphaAgent(
        interval_sec=42,
        event_bus=bus,
        signals_dir=tmp_path,
        portfolio_file=tmp_path / "p.json",
        market_tool=tmp_path / "m.py",
        quote_fetcher=lambda _: {},
    )
    assert agent.interval_sec == 42


# --- plan() — empty / missing inputs ----------------------------------------


def test_plan_returns_empty_when_signals_dir_missing(tmp_path):
    bus = _RecordingBus()
    agent = AlphaAgent(
        event_bus=bus,
        signals_dir=tmp_path / "does_not_exist",
        portfolio_file=tmp_path / "p.json",
        market_tool=tmp_path / "m.py",
        quote_fetcher=lambda _: {},
    )
    assert agent.plan() == []
    assert agent._planned_signal_ids == []


def test_plan_returns_empty_when_portfolio_missing(tmp_path):
    agent, _, portfolio = _make_agent(tmp_path, portfolio=None, write_portfolio=False, quotes={})
    # Sanity: portfolio file truly absent.
    assert not portfolio.exists()
    assert agent.plan() == []


def test_plan_tolerates_malformed_portfolio_json(tmp_path):
    agent, _, portfolio = _make_agent(tmp_path, write_portfolio=False, quotes={})
    portfolio.write_text("{ this is not json")
    assert agent.plan() == []


def test_plan_tolerates_malformed_jsonl_lines(tmp_path):
    """Garbage lines in a signals file must not crash signal-index loading."""
    agent, _, _ = _make_agent(
        tmp_path,
        portfolio={"positions": []},
        signal_lines=[
            "not-json-line",
            "",
            "   ",
            json.dumps({"signal_id": "abc", "symbol": "BTCUSDT"}),
        ],
        quotes={},
    )
    index = agent._load_signal_index()
    assert index == {"abc": {"signal_id": "abc", "symbol": "BTCUSDT"}}


def test_plan_skips_positions_without_symbol_or_entry_or_quote(tmp_path):
    """Positions missing prerequisites or quotes are silently skipped."""
    agent, _, _ = _make_agent(
        tmp_path,
        portfolio={
            "positions": [
                {"symbol": "", "entry_price": 100.0, "qty": 1.0},  # empty symbol
                {"symbol": "BTCUSDT", "entry_price": 0.0, "qty": 1.0},  # no entry
                {"symbol": "ETHUSDT", "entry_price": 100.0, "qty": 1.0},  # no quote
                "not-a-dict",  # filtered before evaluation
            ]
        },
        # No quotes — every action should be skipped.
        quotes={},
    )
    assert agent.plan() == []


# --- plan() — happy paths and exit math -------------------------------------


def test_plan_emits_score_and_close_when_long_take_profit_hit(tmp_path):
    agent, _, _ = _make_agent(
        tmp_path,
        portfolio={
            "positions": [
                {
                    "symbol": "BTCUSDT",
                    "side": "long",
                    "entry_price": 100.0,
                    "qty": 1.0,
                    "atr": 2.0,
                    "signal_id": "s-1",
                    "opened_at": "2026-04-25",
                }
            ]
        },
        # +10 above entry crosses TP at 105.
        quotes={"BTCUSDT": 110.0},
    )

    actions = agent.plan()

    assert [a.kind for a in actions] == ["score_signal", "close_position"]
    score_payload = actions[0].payload
    assert score_payload["signal_id"] == "s-1"
    assert score_payload["action"] == "close"
    assert score_payload["reason"] == "take_profit"
    # ATR 2.0 → SL = 100 - 1.5*2 = 97; TP = 100 + 2.5*2 = 105.
    assert score_payload["stop_loss"] == pytest.approx(
        100.0 - STOP_LOSS_ATR_MULT * 2.0
    )
    assert score_payload["take_profit"] == pytest.approx(
        100.0 + TAKE_PROFIT_ATR_MULT * 2.0
    )
    assert score_payload["score"] == pytest.approx(100.0)
    # planned ids tracked for observation.
    assert agent._planned_signal_ids == ["s-1"]


def test_plan_short_position_stop_loss_trigger(tmp_path):
    agent, _, _ = _make_agent(
        tmp_path,
        portfolio={
            "positions": [
                {
                    "symbol": "BTCUSDT",
                    "side": "SHORT",
                    "entry_price": 100.0,
                    "qty": 1.0,
                    "atr": 2.0,
                    "pipeline_id": "p-9",
                    "opened_at": "2026-04-25",
                }
            ]
        },
        # Short SL is above entry; 110 > entry+1.5*2 = 103.
        quotes={"BTCUSDT": 110.0},
    )
    actions = agent.plan()
    assert [a.kind for a in actions] == ["score_signal", "close_position"]
    payload = actions[0].payload
    assert payload["side"] == "short"
    assert payload["action"] == "close"
    assert payload["reason"] == "stop_loss"
    # pipeline_id falls through as the signal_id when signal_id is absent.
    assert payload["signal_id"] == "p-9"


def test_plan_holds_when_price_inside_band(tmp_path):
    agent, _, _ = _make_agent(
        tmp_path,
        portfolio={
            "positions": [
                {
                    "symbol": "BTCUSDT",
                    "side": "long",
                    "entry_price": 100.0,
                    "qty": 1.0,
                    "atr": 2.0,
                    "signal_id": "s-2",
                    "opened_at": "2026-04-25",
                }
            ]
        },
        quotes={"BTCUSDT": 100.5},
    )
    actions = agent.plan()
    # Score-only — no close action when not at SL/TP.
    assert [a.kind for a in actions] == ["score_signal"]
    payload = actions[0].payload
    assert payload["action"] == "hold"
    assert payload["reason"] is None
    # Score in (0, 100) range and rounded to 2dp.
    assert 0.0 <= payload["score"] <= 100.0
    assert round(payload["score"], 2) == payload["score"]


def test_plan_resolves_signal_id_via_index_when_missing(tmp_path):
    """When a position has no signal_id, the agent matches by symbol."""
    agent, _, _ = _make_agent(
        tmp_path,
        portfolio={
            "positions": [
                {
                    "symbol": "BTCUSDT",
                    "side": "long",
                    "entry_price": 100.0,
                    "qty": 1.0,
                    "atr": 2.0,
                    "opened_at": "2026-04-25",
                }
            ]
        },
        signal_lines=[
            json.dumps({"signal_id": "first", "symbol": "BTCUSDT"}),
            json.dumps({"signal_id": "last", "symbol": "BTCUSDT"}),
        ],
        quotes={"BTCUSDT": 100.5},
    )
    actions = agent.plan()
    # "last" is preferred (insertion order, reversed search).
    assert actions[0].payload["signal_id"] == "last"


def test_plan_falls_back_to_symbol_opened_at_id(tmp_path):
    """No signal_id, no signal-index match → ``symbol:opened_at`` synthesis."""
    agent, _, _ = _make_agent(
        tmp_path,
        portfolio={
            "positions": [
                {
                    "symbol": "BTCUSDT",
                    "side": "long",
                    "entry_price": 100.0,
                    "qty": 1.0,
                    "atr": 2.0,
                    "opened_at": "2026-04-25",
                }
            ]
        },
        quotes={"BTCUSDT": 100.5},
    )
    actions = agent.plan()
    assert actions[0].payload["signal_id"] == "BTCUSDT:2026-04-25"


def test_plan_derives_atr_from_stop_loss_when_missing(tmp_path):
    """ATR is derived as ``|entry-stop| / STOP_LOSS_ATR_MULT`` when zero."""
    agent, _, _ = _make_agent(
        tmp_path,
        portfolio={
            "positions": [
                {
                    "symbol": "BTCUSDT",
                    "side": "long",
                    "entry_price": 100.0,
                    "qty": 1.0,
                    "stop_loss": 97.0,
                    "atr": 0,  # explicitly missing
                    "opened_at": "2026-04-25",
                }
            ]
        },
        quotes={"BTCUSDT": 100.0},
    )
    actions = agent.plan()
    payload = actions[0].payload
    assert payload["atr"] == pytest.approx(2.0)
    # Take-profit is derived from the recovered ATR.
    assert payload["take_profit"] == pytest.approx(100.0 + 2.5 * 2.0)


# --- act() ------------------------------------------------------------------


def test_act_emits_score_and_close_events_and_invokes_hook(tmp_path):
    bus = _RecordingBus()
    hook_calls: list[Action] = []

    def hook(action: Action) -> dict[str, Any]:
        hook_calls.append(action)
        return {"hooked": True, "extra": "ok"}

    agent, _, _ = _make_agent(
        tmp_path,
        portfolio={
            "positions": [
                {
                    "symbol": "BTCUSDT",
                    "side": "long",
                    "entry_price": 100.0,
                    "qty": 1.0,
                    "atr": 2.0,
                    "signal_id": "s-1",
                    "opened_at": "2026-04-25",
                }
            ]
        },
        quotes={"BTCUSDT": 110.0},  # TP triggered
        close_hook=hook,
        event_bus=bus,
    )
    actions = agent.plan()
    results = agent.act(actions)

    assert [r.action.kind for r in results] == ["score_signal", "close_position"]
    assert results[0].status == "scored"
    assert results[1].status == "close_proposed"
    # close payload merges hook output.
    assert results[1].payload["hooked"] is True
    assert results[1].payload["extra"] == "ok"
    assert results[1].payload["signal_id"] == "s-1"
    # Hook receives the close_position action.
    assert len(hook_calls) == 1
    assert hook_calls[0].kind == "close_position"

    emitted = [c["event_type"] for c in bus.calls]
    assert "agent.alpha.signal_scored" in emitted
    assert "agent.alpha.position_closed" in emitted
    score_event = next(c for c in bus.calls if c["event_type"] == "agent.alpha.signal_scored")
    assert score_event["source"] == "agent:alpha"
    assert score_event["data"]["signal_id"] == "s-1"


def test_act_returns_ignored_for_unknown_action_kind(tmp_path):
    bus = _RecordingBus()
    agent, _, _ = _make_agent(tmp_path, portfolio={"positions": []}, quotes={}, event_bus=bus)
    odd_action = Action(kind="unknown", payload={"x": 1})
    results = agent.act([odd_action])

    assert len(results) == 1
    assert results[0].status == "ignored"
    assert results[0].payload == {}
    # Unknown actions do not emit events.
    assert bus.calls == []


def test_act_close_hook_returning_none_is_tolerated(tmp_path):
    """If the close hook returns ``None``, the close payload still merges cleanly."""
    bus = _RecordingBus()
    agent, _, _ = _make_agent(
        tmp_path,
        portfolio={
            "positions": [
                {
                    "symbol": "BTCUSDT",
                    "side": "long",
                    "entry_price": 100.0,
                    "qty": 1.0,
                    "atr": 2.0,
                    "signal_id": "s-x",
                    "opened_at": "2026-04-25",
                }
            ]
        },
        quotes={"BTCUSDT": 110.0},
        close_hook=lambda _action: None,
        event_bus=bus,
    )
    results = agent.act(agent.plan())
    close = next(r for r in results if r.action.kind == "close_position")
    assert close.status == "close_proposed"
    assert close.payload["signal_id"] == "s-x"


# --- observe() --------------------------------------------------------------


def test_observe_summarizes_cycle_deterministically(tmp_path):
    agent, _, _ = _make_agent(
        tmp_path,
        portfolio={
            "positions": [
                {
                    "symbol": "BTCUSDT",
                    "side": "long",
                    "entry_price": 100.0,
                    "qty": 1.0,
                    "atr": 2.0,
                    "signal_id": "s-1",
                    "opened_at": "2026-04-25",
                }
            ]
        },
        quotes={"BTCUSDT": 110.0},  # forces close
    )
    actions = agent.plan()
    results = agent.act(actions)
    observation = agent.observe(results)

    assert observation["agent"] == "alpha"
    # observe is called *before* run_once increments cycle_count (so +1 on the
    # very first cycle).
    assert observation["cycle_count"] == 1
    assert observation["scored_positions"] == 1
    assert observation["close_candidates"] == 1
    assert observation["planned_signal_ids"] == ["s-1"]
    # Timestamp present and ISO-formatted with timezone.
    assert "T" in observation["timestamp"]
    assert observation["timestamp"].endswith(("Z", "+00:00"))


def test_observe_with_empty_results_returns_zero_counts(tmp_path):
    agent, _, _ = _make_agent(tmp_path, portfolio={"positions": []}, quotes={})
    obs = agent.observe([])
    assert obs["scored_positions"] == 0
    assert obs["close_candidates"] == 0
    assert obs["planned_signal_ids"] == []


# --- PnL / fees -------------------------------------------------------------


def test_net_pnl_includes_round_trip_fees(tmp_path):
    """Net PnL = gross − entry_fee − exit_fee for a simple long round-trip."""
    agent, _, _ = _make_agent(
        tmp_path,
        portfolio={
            "positions": [
                {
                    "symbol": "BTCUSDT",
                    "side": "long",
                    "entry_price": 100.0,
                    "qty": 1.0,
                    "atr": 2.0,
                    "signal_id": "s-pnl",
                    "opened_at": "2026-04-25",
                }
            ]
        },
        quotes={"BTCUSDT": 110.0},
    )
    actions = agent.plan()
    payload = actions[0].payload
    expected_gross = 10.0  # (110-100) * 1
    expected_entry_fee = 100.0 * 1.0 * FEE_RATE_PER_LEG
    expected_exit_fee = 110.0 * 1.0 * FEE_RATE_PER_LEG
    expected_pnl = round(expected_gross - expected_entry_fee - expected_exit_fee, 2)
    assert payload["pnl_usd"] == pytest.approx(expected_pnl)


# --- _fetch_quote subprocess shim -------------------------------------------


def test_fetch_quote_parses_dict_price(tmp_path, monkeypatch):
    agent, _, _ = _make_agent(tmp_path, portfolio={"positions": []}, quotes={})
    fake = subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout=json.dumps({"price": 250.5}),
        stderr="",
    )
    monkeypatch.setattr("lib.agents.alpha_agent.subprocess.run", lambda *a, **k: fake)
    assert agent._fetch_quote("AAPL") == pytest.approx(250.5)


def test_fetch_quote_parses_crypto_bar_list(tmp_path, monkeypatch):
    agent, _, _ = _make_agent(tmp_path, portfolio={"positions": []}, quotes={})
    fake = subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout=json.dumps([{"close": 65500.0}, {"close": 66000.5}]),
        stderr="",
    )
    monkeypatch.setattr("lib.agents.alpha_agent.subprocess.run", lambda *a, **k: fake)
    # ``BTCUSDT`` triggers the crypto branch — last bar's close wins.
    assert agent._fetch_quote("BTCUSDT") == pytest.approx(66000.5)


def test_fetch_quote_returns_none_on_nonzero_return(tmp_path, monkeypatch):
    agent, _, _ = _make_agent(tmp_path, portfolio={"positions": []}, quotes={})
    fake = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="boom")
    monkeypatch.setattr("lib.agents.alpha_agent.subprocess.run", lambda *a, **k: fake)
    assert agent._fetch_quote("AAPL") is None


def test_fetch_quote_returns_none_on_invalid_json(tmp_path, monkeypatch):
    agent, _, _ = _make_agent(tmp_path, portfolio={"positions": []}, quotes={})
    fake = subprocess.CompletedProcess(args=[], returncode=0, stdout="not-json", stderr="")
    monkeypatch.setattr("lib.agents.alpha_agent.subprocess.run", lambda *a, **k: fake)
    assert agent._fetch_quote("AAPL") is None


def test_fetch_quote_returns_none_on_oserror(tmp_path, monkeypatch):
    agent, _, _ = _make_agent(tmp_path, portfolio={"positions": []}, quotes={})

    def boom(*_a, **_k):
        raise OSError("subprocess refused")

    monkeypatch.setattr("lib.agents.alpha_agent.subprocess.run", boom)
    assert agent._fetch_quote("AAPL") is None


# --- Default close hook -----------------------------------------------------


def test_default_close_hook_returns_pending_marker(tmp_path):
    agent, _, _ = _make_agent(tmp_path, portfolio={"positions": []}, quotes={})
    action = Action(kind="close_position", payload={"signal_id": "s-default"})
    out = agent._todo_close_hook(action)
    assert out["status"] == "pending_hook"
    assert out["signal_id"] == "s-default"
    assert "proposed_at" in out
    assert "T" in out["proposed_at"]


# --- run_once integration ---------------------------------------------------


def test_run_once_full_cycle_emits_completed_event_and_persists_observation(tmp_path):
    """End-to-end: plan→act→observe + cycle.completed event from BaseAgent."""
    bus = _RecordingBus()
    agent, _, _ = _make_agent(
        tmp_path,
        portfolio={
            "positions": [
                {
                    "symbol": "BTCUSDT",
                    "side": "long",
                    "entry_price": 100.0,
                    "qty": 1.0,
                    "atr": 2.0,
                    "signal_id": "s-99",
                    "opened_at": "2026-04-25",
                }
            ]
        },
        quotes={"BTCUSDT": 110.0},
        event_bus=bus,
    )
    obs = agent.run_once()

    assert agent.cycle_count == 1
    assert agent.last_observation == obs
    assert obs["scored_positions"] == 1
    assert obs["close_candidates"] == 1
    completed = [c for c in bus.calls if c["event_type"] == "agent.cycle.completed"]
    assert len(completed) == 1
    assert completed[0]["data"]["agent"] == "alpha"
    assert completed[0]["data"]["cycle_count"] == 1
