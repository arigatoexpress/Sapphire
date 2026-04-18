"""Per-tier token budget enforcement for agent dispatch.

Tracks daily and per-cycle token spend against configured limits and throttles
agent calls once the maintenance_threshold is reached. Persists counters to
JSON on disk so budgets survive orchestrator restarts.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass
class GovernorConfig:
    daily_budget: int
    per_cycle_budget: int
    maintenance_threshold: float


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


class TokenGovernor:
    def __init__(self, *, path: Path, config: GovernorConfig) -> None:
        self.path = path
        self.config = config
        self.state = _read_json(path)
        self._cycle_started = False
        self._cycle_day = ""
        self._cycle_reserved = 0
        self._cycle_budget = 0
        self._maintenance_mode = False

    def _ensure_day_state(self, now: datetime) -> None:
        day = now.date().isoformat()
        state_day = str(self.state.get("day") or "")
        if state_day != day:
            self.state = {
                "day": day,
                "consumed_estimated": 0,
                "history": [],
                "maintenance_mode": False,
                "updated_at": now.isoformat(),
            }

    def start_cycle(self, *, now: datetime | None = None) -> dict[str, Any]:
        current = now or _utc_now()
        self._ensure_day_state(current)
        consumed = max(0, int(self.state.get("consumed_estimated", 0)))
        remaining_today = max(0, self.config.daily_budget - consumed)
        self._cycle_budget = max(0, min(self.config.per_cycle_budget, remaining_today))
        self._cycle_reserved = 0
        self._cycle_day = str(self.state.get("day") or current.date().isoformat())
        ratio = 0.0
        if self.config.daily_budget > 0:
            ratio = remaining_today / float(self.config.daily_budget)
        self._maintenance_mode = ratio <= max(0.0, min(self.config.maintenance_threshold, 1.0))
        self.state["maintenance_mode"] = self._maintenance_mode
        self.state["updated_at"] = current.isoformat()
        self._cycle_started = True
        return self.snapshot()

    def reserve(self, *, estimated_tokens: int, reason: str) -> bool:
        if not self._cycle_started:
            self.start_cycle()

        estimate = max(0, int(estimated_tokens))
        if estimate <= 0:
            return True
        if self._cycle_reserved + estimate > self._cycle_budget:
            return False
        self._cycle_reserved += estimate
        consumed = max(0, int(self.state.get("consumed_estimated", 0)))
        self.state["consumed_estimated"] = consumed + estimate
        history = self.state.get("history")
        if not isinstance(history, list):
            history = []
            self.state["history"] = history
        history.append(
            {
                "at": _utc_now().isoformat(),
                "tokens": estimate,
                "reason": str(reason or "").strip(),
            }
        )
        self.state["history"] = history[-500:]
        return True

    def finalize_cycle(self, *, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self._cycle_started:
            self.start_cycle()
        payload = dict(self.state)
        payload["updated_at"] = _utc_now().isoformat()
        if isinstance(metadata, dict) and metadata:
            payload["last_cycle"] = metadata
        _write_json(self.path, payload)
        self.state = payload
        return self.snapshot()

    def snapshot(self) -> dict[str, Any]:
        consumed = max(0, int(self.state.get("consumed_estimated", 0)))
        remaining_today = max(0, self.config.daily_budget - consumed)
        return {
            "day": self._cycle_day or str(self.state.get("day") or ""),
            "daily_budget": self.config.daily_budget,
            "per_cycle_budget": self.config.per_cycle_budget,
            "maintenance_threshold": self.config.maintenance_threshold,
            "consumed_estimated": consumed,
            "remaining_estimated": remaining_today,
            "cycle_reserved": self._cycle_reserved,
            "cycle_budget": self._cycle_budget,
            "maintenance_mode": bool(self._maintenance_mode),
            "updated_at": str(self.state.get("updated_at") or ""),
        }
