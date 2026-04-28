"""Small persistent sliding-window counters for reader safety caps."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

DEFAULT_COUNTER_PATH = Path.home() / ".cache" / "sapphire" / "telegram_intel" / "counters.json"


@dataclass(frozen=True)
class CounterState:
    allowed: bool
    used: int
    remaining: int
    limit: int

    def to_dict(self) -> dict[str, int | bool]:
        return {
            "allowed": self.allowed,
            "used": self.used,
            "remaining": self.remaining,
            "limit": self.limit,
        }


class HourlyRateLimiter:
    """JSON-backed per-hour event limiter."""

    def __init__(self, path: Path | str = DEFAULT_COUNTER_PATH, *, now: float | None = None) -> None:
        self.path = Path(path).expanduser()
        self._fixed_now = now

    def _now(self) -> float:
        return float(self._fixed_now if self._fixed_now is not None else time.time())

    def _load(self) -> dict[str, list[float]]:
        if not self.path.exists():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        if not isinstance(payload, dict):
            return {}
        out: dict[str, list[float]] = {}
        cutoff = self._now() - 3600
        for key, values in payload.items():
            if not isinstance(values, list):
                continue
            out[str(key)] = [float(value) for value in values if float(value) >= cutoff]
        return out

    def _save(self, payload: dict[str, list[float]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")

    def check(self, bucket: str, limit: int, *, amount: int = 1) -> CounterState:
        payload = self._load()
        used = len(payload.get(bucket, []))
        remaining = max(0, limit - used)
        return CounterState(amount <= remaining, used, remaining, limit)

    def record(self, bucket: str, amount: int = 1) -> CounterState:
        amount = max(0, int(amount))
        payload = self._load()
        payload.setdefault(bucket, [])
        payload[bucket].extend([self._now()] * amount)
        self._save(payload)
        used = len(payload[bucket])
        return CounterState(True, used, remaining=max(0, used), limit=used)
