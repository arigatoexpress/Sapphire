"""Unit tests for the multi-agent harness."""

from __future__ import annotations

import json
import signal
from pathlib import Path
from typing import Any

import pytest

from lib.agents.alpha_agent import AlphaAgent
from lib.agents.base import Action, BaseAgent, Result
from lib.agents.runner import AgentRunner, load_agent_class


class FakeBus:
    """Capture events published during agent tests."""

    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any], str | None]] = []

    def publish(
        self,
        event_type: str,
        data: dict[str, Any],
        source: str | None = None,
    ) -> str:
        self.events.append((event_type, data, source))
        return f"evt-{len(self.events)}"


class OrderedAgent(BaseAgent):
    """Test agent that records method order."""

    def __init__(self, event_bus: FakeBus | None = None) -> None:
        super().__init__(name="ordered", interval_sec=0, event_bus=event_bus)
        self.order: list[str] = []

    def plan(self) -> list[Action]:
        self.order.append("plan")
        return [Action(kind="noop", payload={"value": 1})]

    def act(self, actions: list[Action]) -> list[Result]:
        self.order.append("act")
        return [Result(action=actions[0], status="ok", payload={"count": len(actions)})]

    def observe(self, results: list[Result]) -> dict[str, Any]:
        self.order.append("observe")
        return {"statuses": [result.status for result in results]}


class SingleCycleAgent(BaseAgent):
    """Test agent that stops itself after the first cycle."""

    def __init__(self) -> None:
        super().__init__(name="single", interval_sec=0)

    def plan(self) -> list[Action]:
        return []

    def act(self, actions: list[Action]) -> list[Result]:
        return []

    def observe(self, results: list[Result]) -> dict[str, Any]:
        self.stop()
        return {"done": True}


def _write_signal(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload) + "\n")


def _write_portfolio(path: Path, position: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "capital": 100000.0,
                "initial_capital": 100000.0,
                "positions": [position],
                "history": [],
            },
            indent=2,
        )
    )


def test_base_agent_cycle_order() -> None:
    agent = OrderedAgent()
    observation = agent.run_once()

    assert agent.order == ["plan", "act", "observe"]
    assert observation == {"statuses": ["ok"]}


def test_base_agent_emits_cycle_event() -> None:
    bus = FakeBus()
    agent = OrderedAgent(event_bus=bus)

    agent.run_once()

    assert bus.events[0][0] == "agent.cycle.completed"
    assert bus.events[0][1]["agent"] == "ordered"
    assert bus.events[0][1]["cycle_count"] == 1


def test_base_agent_run_forever_stops_cleanly(monkeypatch: pytest.MonkeyPatch) -> None:
    registered: dict[int, Any] = {}
    monkeypatch.setattr(signal, "getsignal", lambda signum: signal.SIG_DFL)
    monkeypatch.setattr(
        signal,
        "signal",
        lambda signum, handler: registered.setdefault(signum, handler),
    )

    agent = SingleCycleAgent()
    agent.run_forever()

    assert agent.cycle_count == 1
    assert signal.SIGTERM in registered
    assert signal.SIGINT in registered


def test_alpha_agent_scores_open_positions(tmp_path: Path) -> None:
    bus = FakeBus()
    signals_dir = tmp_path / "signals"
    portfolio_file = tmp_path / "paper_portfolio.json"
    _write_signal(
        signals_dir / "2026-04-20.jsonl",
        {
            "pipeline_id": "sig-1",
            "symbol": "BTCUSDT",
            "strategy": "ema_cross",
        },
    )
    _write_portfolio(
        portfolio_file,
        {
            "symbol": "BTCUSDT",
            "side": "BUY",
            "entry_price": 100.0,
            "qty": 2.0,
            "atr": 10.0,
            "stop_loss": 85.0,
            "take_profit": 125.0,
            "pipeline_id": "sig-1",
            "opened_at": "2026-04-20T00:00:00+00:00",
        },
    )

    agent = AlphaAgent(
        interval_sec=1,
        event_bus=bus,
        signals_dir=signals_dir,
        portfolio_file=portfolio_file,
        quote_fetcher=lambda symbols: {symbol: 110.0 for symbol in symbols},
    )
    summary = agent.run_once()

    assert summary["scored_positions"] == 1
    assert summary["close_candidates"] == 0
    assert bus.events[0][0] == "agent.alpha.signal_scored"
    assert bus.events[0][1]["signal_id"] == "sig-1"
    assert bus.events[0][1]["action"] == "hold"
    assert bus.events[0][1]["score"] > 50.0
    assert portfolio_file.read_text().count('"positions"') == 1


def test_alpha_agent_closes_on_sl_hit(tmp_path: Path) -> None:
    bus = FakeBus()
    signals_dir = tmp_path / "signals"
    portfolio_file = tmp_path / "paper_portfolio.json"
    close_actions: list[Action] = []
    _write_signal(
        signals_dir / "2026-04-20.jsonl",
        {
            "signal_id": "sig-2",
            "symbol": "ETHUSDT",
            "strategy": "bb_top",
        },
    )
    _write_portfolio(
        portfolio_file,
        {
            "symbol": "ETHUSDT",
            "side": "BUY",
            "entry_price": 200.0,
            "qty": 1.5,
            "atr": 20.0,
            "stop_loss": 170.0,
            "take_profit": 250.0,
            "signal_id": "sig-2",
            "opened_at": "2026-04-20T01:00:00+00:00",
        },
    )

    def close_hook(action: Action) -> dict[str, Any]:
        close_actions.append(action)
        return {"hooked": True}

    agent = AlphaAgent(
        interval_sec=1,
        event_bus=bus,
        signals_dir=signals_dir,
        portfolio_file=portfolio_file,
        quote_fetcher=lambda symbols: {symbol: 165.0 for symbol in symbols},
        close_hook=close_hook,
    )
    summary = agent.run_once()

    assert summary["close_candidates"] == 1
    assert len(close_actions) == 1
    assert close_actions[0].payload["reason"] == "stop_loss"
    assert [event[0] for event in bus.events[:2]] == [
        "agent.alpha.signal_scored",
        "agent.alpha.position_closed",
    ]
    assert bus.events[1][1]["signal_id"] == "sig-2"
    assert bus.events[1][1]["pnl_usd"] < 0


def test_runner_loads_agent_by_name(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "data" / "signals").mkdir(parents=True)
    (repo_root / "plugins" / "claw-sapphire" / "tools").mkdir(parents=True)
    (repo_root / "plugins" / "claw-sapphire" / "tools" / "market.py").write_text(
        "print('[]')\n"
    )
    (repo_root / "data" / "paper_portfolio.json").write_text('{"positions": []}\n')

    runner = AgentRunner(repo_root=repo_root)
    bus = FakeBus()
    agent = runner.load_agent_by_name("alpha", interval_sec=123, event_bus=bus)

    assert isinstance(agent, AlphaAgent)
    assert agent.interval_sec == 123
    assert load_agent_class("alpha") is AlphaAgent
    with pytest.raises(KeyError):
        load_agent_class("ghost")
