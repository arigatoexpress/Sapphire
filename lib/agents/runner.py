"""CLI runner for Sapphire autonomous agents."""

from __future__ import annotations

import argparse
import json
import logging
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from lib.agents.base import BaseAgent

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]

_RUNNER: AgentRunner | None = None
_RUNNER_LOCK = threading.Lock()


def load_agent_class(name: str) -> type[BaseAgent]:
    """Return the agent class registered to a short name."""
    registry = {
        "alpha": ("lib.agents.alpha_agent", "AlphaAgent"),
    }
    try:
        module_name, class_name = registry[name]
    except KeyError as exc:
        raise KeyError(f"Unknown agent '{name}'") from exc

    module = __import__(module_name, fromlist=[class_name])
    return getattr(module, class_name)


class AgentRunner:
    """Load named agents, run them, and persist heartbeats to disk."""

    def __init__(self, repo_root: Path = ROOT) -> None:
        """Initialize the runner.

        Args:
            repo_root: Repository root used for heartbeat and data paths.
        """
        self.repo_root = repo_root
        self.heartbeat_dir = self.repo_root / "data" / "agents"
        self.heartbeat_dir.mkdir(parents=True, exist_ok=True)
        self._loaded_agents: dict[str, BaseAgent] = {}
        self._running_agents: set[str] = set()

    def load_agent_by_name(
        self,
        name: str,
        interval_sec: int | None = None,
        event_bus: Any = None,
    ) -> BaseAgent:
        """Instantiate an agent by short name."""
        agent_cls = load_agent_class(name)
        kwargs: dict[str, Any] = {"event_bus": event_bus}
        if interval_sec is not None:
            kwargs["interval_sec"] = interval_sec
        if name == "alpha":
            kwargs["signals_dir"] = self.repo_root / "data" / "signals"
            kwargs["portfolio_file"] = self.repo_root / "data" / "paper_portfolio.json"
            kwargs["market_tool"] = (
                self.repo_root / "plugins" / "claw-sapphire" / "tools" / "market.py"
            )
        agent = agent_cls(**kwargs)
        self._loaded_agents[name] = agent
        return agent

    def run(self, name: str, interval_sec: int | None = None, event_bus: Any = None) -> BaseAgent:
        """Load an agent, write heartbeats, and run it until stopped."""
        agent = self.load_agent_by_name(name, interval_sec=interval_sec, event_bus=event_bus)
        heartbeat_stop = threading.Event()
        heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            args=(agent, heartbeat_stop),
            name=f"{agent.name}-heartbeat",
            daemon=True,
        )

        self._running_agents.add(agent.name)
        self._write_heartbeat(agent)
        heartbeat_thread.start()
        try:
            agent.run_forever()
            return agent
        finally:
            heartbeat_stop.set()
            heartbeat_thread.join(timeout=1.0)
            self._running_agents.discard(agent.name)
            self._write_heartbeat(agent)

    def status(self) -> dict[str, Any]:
        """Return status information for loaded agents and heartbeat files."""
        records: dict[str, dict[str, Any]] = {}

        for name, agent in self._loaded_agents.items():
            records[name] = self._status_record(
                name=name,
                interval_sec=agent.interval_sec,
                cycle_count=agent.cycle_count,
                last_cycle_completed_at=(
                    agent.last_cycle_completed_at.isoformat()
                    if agent.last_cycle_completed_at
                    else None
                ),
            )

        for path in sorted(self.heartbeat_dir.glob("*.heartbeat")):
            try:
                heartbeat = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            name = path.stem
            if name not in records:
                records[name] = self._status_record(
                    name=name,
                    interval_sec=int(heartbeat.get("interval_sec") or 0),
                    cycle_count=int(heartbeat.get("cycle_count") or 0),
                    last_cycle_completed_at=heartbeat.get("last_cycle_completed_at"),
                    heartbeat_updated_at=heartbeat.get("updated_at"),
                )

        running_count = sum(1 for record in records.values() if record["state"] == "RUNNING")
        stopped_count = sum(1 for record in records.values() if record["state"] == "STOPPED")
        return {
            "agents": records,
            "total": len(records),
            "running": running_count,
            "paused": 0,
            "stopped": stopped_count,
        }

    def _heartbeat_loop(self, agent: BaseAgent, stop_event: threading.Event) -> None:
        """Write heartbeat snapshots until the runner stops."""
        heartbeat_every = max(1, min(agent.interval_sec or 1, 30))
        while not stop_event.wait(heartbeat_every):
            self._write_heartbeat(agent)

    def _write_heartbeat(self, agent: BaseAgent) -> None:
        """Persist the latest runner heartbeat for an agent."""
        payload = {
            "agent": agent.name,
            "cycle_count": agent.cycle_count,
            "interval_sec": agent.interval_sec,
            "last_cycle_completed_at": (
                agent.last_cycle_completed_at.isoformat()
                if agent.last_cycle_completed_at
                else None
            ),
            "updated_at": datetime.now(UTC).isoformat(),
            "last_observation": agent.last_observation,
        }
        path = self.heartbeat_dir / f"{agent.name}.heartbeat"
        path.write_text(json.dumps(payload, indent=2, sort_keys=True))

    def _status_record(
        self,
        name: str,
        interval_sec: int,
        cycle_count: int,
        last_cycle_completed_at: str | None,
        heartbeat_updated_at: str | None = None,
    ) -> dict[str, Any]:
        """Build a single status payload for the API and dashboard."""
        heartbeat_age_sec: int | None = None
        if heartbeat_updated_at:
            parsed = self._parse_iso(heartbeat_updated_at)
            if parsed is not None:
                heartbeat_age_sec = max(
                    0,
                    int((datetime.now(UTC) - parsed).total_seconds()),
                )

        if heartbeat_age_sec is None and name in self._running_agents:
            state = "RUNNING"
        elif heartbeat_age_sec is None:
            state = "STOPPED"
        else:
            threshold = max(interval_sec * 2, 60) if interval_sec else 60
            state = "RUNNING" if heartbeat_age_sec <= threshold else "STOPPED"

        return {
            "name": name,
            "cycle_count": cycle_count,
            "interval_sec": interval_sec,
            "last_cycle_completed_at": last_cycle_completed_at,
            "heartbeat_age_sec": heartbeat_age_sec,
            "state": state,
        }

    def _parse_iso(self, value: str) -> datetime | None:
        """Parse an ISO timestamp into an aware UTC datetime."""
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed.astimezone(UTC)


def get_runner() -> AgentRunner:
    """Return the process-wide runner singleton."""
    global _RUNNER
    with _RUNNER_LOCK:
        if _RUNNER is None:
            _RUNNER = AgentRunner()
        return _RUNNER


def main() -> None:
    """Run an agent continuously from the command line."""
    parser = argparse.ArgumentParser(description="Run a Sapphire autonomous agent")
    parser.add_argument("--agent", help="Agent short name, for example 'alpha'")
    parser.add_argument("--interval", type=int, default=300, help="Cycle interval in seconds")
    parser.add_argument("--status", action="store_true", help="Print runner status and exit")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    )

    runner = get_runner()
    if args.status:
        print(json.dumps(runner.status(), indent=2, sort_keys=True))
        return
    if not args.agent:
        parser.error("--agent is required unless --status is used")

    runner.run(args.agent, interval_sec=args.interval)


if __name__ == "__main__":
    main()
