"""Pure system-snapshot builders for the ``/status`` command + heartbeat.

Neither function makes network calls. They read local artifacts the rest
of the Sapphire stack already produces:

* ``launchctl list`` → LaunchAgent inventory
* ``data/paper_portfolio.json`` → portfolio total
* ``data/intelligence/<date>/regime.json`` → regime state
* ``data/intelligence/<date>/fear_greed.json`` (if present) → F&G
* ``data/health/heartbeat.jsonl`` → last service heartbeat state
* ``data/system_events.jsonl`` → recent kill-switch flag

Missing files never raise — the snapshot degrades to safe placeholders.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from lib.telegram import formatters as fmt

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"


@dataclass(frozen=True)
class ServiceState:
    name: str
    pid: str
    exit_code: str

    @property
    def display(self) -> str:
        if self.pid.isdigit() and int(self.pid) > 0:
            return "✅ running"
        if self.exit_code and self.exit_code != "0":
            return f"⚠️ exit {self.exit_code}"
        return "⚪ idle"


@dataclass(frozen=True)
class Snapshot:
    services: list[ServiceState] = field(default_factory=list)
    freshness: list[tuple[str, str]] = field(default_factory=list)
    regime: str = "unknown"
    fear_greed: int | None = None
    portfolio_usd: float | None = None
    kill_switch_armed: bool = False
    agents_ok: int = 0
    agents_total: int = 0


def _list_launchagents(prefix: str = "com.sapphire.") -> list[ServiceState]:
    """Query launchctl for ``com.sapphire.*`` agents.

    Returns an empty list on any error — we prefer a shorter status over
    a broken status.
    """
    try:
        completed = subprocess.run(
            ["launchctl", "list"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return []
    if completed.returncode != 0:
        return []

    services: list[ServiceState] = []
    for line in completed.stdout.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 3:
            continue
        pid, exit_code, name = parts[0], parts[1], parts[2]
        if not name.startswith(prefix):
            continue
        services.append(ServiceState(name=name, pid=pid, exit_code=exit_code))
    services.sort(key=lambda s: s.name)
    return services


def _mtime_or_none(path: Path) -> datetime | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
    except FileNotFoundError:
        return None
    except OSError:
        return None


def _humanize_delta(ts: datetime | None, now: datetime | None = None) -> str:
    """Age of a file relative to ``now``, using the shared duration formatter.

    Delegates to :func:`lib.telegram.formatters.fmt_age` so the freshness
    rows on ``/status``, the heartbeat, the staleness monitor's Telegram
    alert, and the health-check tool all render age the same way.
    """
    if ts is None:
        return "missing"
    now = now or datetime.now(UTC)
    delta = now - ts
    seconds = max(0, int(delta.total_seconds()))
    return fmt.fmt_age(seconds)


def _freshness_rows(data_dir: Path) -> list[tuple[str, str]]:
    """Freshness of a few load-bearing data files."""
    targets = [
        ("Signals", data_dir / "signals"),
        ("Paper portfolio", data_dir / "paper_portfolio.json"),
        ("Chain snapshot", data_dir / "chain"),
        ("Health heartbeat", data_dir / "health" / "heartbeat.jsonl"),
        ("Events bus", data_dir / "events" / "bus.jsonl"),
    ]
    rows: list[tuple[str, str]] = []
    for label, path in targets:
        if path.is_dir():
            # Newest file in the directory.
            latest: datetime | None = None
            try:
                for entry in path.iterdir():
                    ts = _mtime_or_none(entry)
                    if ts and (latest is None or ts > latest):
                        latest = ts
            except OSError:
                latest = None
            rows.append((label, _humanize_delta(latest)))
        else:
            rows.append((label, _humanize_delta(_mtime_or_none(path))))
    return rows


def _read_json_or_none(path: Path) -> Any:
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def _latest_regime(data_dir: Path) -> tuple[str, int | None]:
    """Try today's + yesterday's intelligence dir for a regime.json."""
    intel = data_dir / "intelligence"
    if not intel.exists():
        return "unknown", None
    try:
        subdirs = sorted(
            [p for p in intel.iterdir() if p.is_dir()],
            reverse=True,
        )
    except OSError:
        return "unknown", None
    for subdir in subdirs[:5]:
        regime_path = subdir / "regime.json"
        fg_path = subdir / "fear_greed.json"
        regime_state = "unknown"
        fg_value: int | None = None
        payload = _read_json_or_none(regime_path)
        if isinstance(payload, dict):
            candidate = payload.get("regime") or payload.get("state")
            if isinstance(candidate, str) and candidate:
                regime_state = candidate
        fg_payload = _read_json_or_none(fg_path)
        if isinstance(fg_payload, dict):
            raw = fg_payload.get("value") or fg_payload.get("score")
            try:
                if raw is not None:
                    fg_value = int(raw)
            except (TypeError, ValueError):
                fg_value = None
        if regime_state != "unknown" or fg_value is not None:
            return regime_state, fg_value
    return "unknown", None


def _portfolio_total(data_dir: Path) -> float | None:
    payload = _read_json_or_none(data_dir / "paper_portfolio.json")
    if not isinstance(payload, dict):
        return None
    for key in ("total_value", "equity", "portfolio_value", "cash"):
        value = payload.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    return None


def _kill_switch_armed() -> bool:
    """Check the same file-based kill switch the trading executors use."""
    return (Path.home() / ".sapphire" / "hyperliquid_trading_pause").exists()


def build_snapshot(*, data_dir: Path | None = None) -> Snapshot:
    """Return a full ``Snapshot`` for use by ``/status`` or the heartbeat."""
    target = data_dir or DATA_DIR
    services = _list_launchagents()
    freshness = _freshness_rows(target)
    regime, fg = _latest_regime(target)
    portfolio = _portfolio_total(target)
    kill = _kill_switch_armed()
    agents_ok = sum(1 for s in services if s.pid.isdigit() and int(s.pid) > 0)
    return Snapshot(
        services=services,
        freshness=freshness,
        regime=regime,
        fear_greed=fg,
        portfolio_usd=portfolio,
        kill_switch_armed=kill,
        agents_ok=agents_ok,
        agents_total=len(services),
    )


def format_service_state(state: ServiceState) -> tuple[str, str]:
    """Return ``(label, state_string)`` suitable for the formatter kv_table."""
    label = state.name.removeprefix("com.sapphire.") or state.name
    return label, state.display


__all__ = [
    "DATA_DIR",
    "REPO_ROOT",
    "ServiceState",
    "Snapshot",
    "build_snapshot",
    "format_service_state",
]

# Silence unused-import lint in environments that don't infer `os`.
_ = os
