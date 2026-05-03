"""Public Hyperliquid counter-party API client, live-gated by env."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .tracker import MAX_TRADERS_TRACKED, TraderPosition, TraderStats, rank_traders

MAX_REFRESH_PER_HOUR = 12
CACHE_DIR = Path.home() / ".cache" / "sapphire" / "counterparty_intel"
COUNTER_PATH = CACHE_DIR / "counters.json"


@dataclass(frozen=True)
class HyperliquidCounterpartyConfig:
    api_url: str = "https://api.hyperliquid.xyz/info"
    live_env: str = "SAPPHIRE_HYPERLIQUID_LIVE"
    max_refresh_per_hour: int = MAX_REFRESH_PER_HOUR
    max_traders: int = MAX_TRADERS_TRACKED

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class HyperliquidCounterpartyClient:
    """Read-only public-data client.

    Dry-run mode returns deterministic mock data and never contacts
    Hyperliquid. Live mode is enabled only when SAPPHIRE_HYPERLIQUID_LIVE=1.
    """

    def __init__(self, config: HyperliquidCounterpartyConfig | None = None) -> None:
        self.config = config or HyperliquidCounterpartyConfig()

    @property
    def live_enabled(self) -> bool:
        return os.environ.get(self.config.live_env) == "1"

    def status(self) -> dict[str, Any]:
        counters = _prune(_load_counters())
        return {
            "live_enabled": self.live_enabled,
            "cache_dir": str(CACHE_DIR),
            "calls_last_hour": len(counters.get("calls", [])),
            "max_refresh_per_hour": self.config.max_refresh_per_hour,
            "public_data_only": True,
        }

    def leaderboard(self, *, top_n: int = 50) -> list[TraderStats]:
        if not self.live_enabled:
            return rank_traders(_mock_leaderboard(), top_n=top_n)
        self._record_call()
        payload = self._post({"type": "leaderboard"})
        rows = payload.get("leaderboard") if isinstance(payload, dict) else payload
        return rank_traders(rows if isinstance(rows, list) else [], top_n=top_n)

    def positions(self, trader: str) -> list[TraderPosition]:
        if not self.live_enabled:
            return [TraderPosition.from_dict(trader, row) for row in _mock_positions(trader)]
        self._record_call()
        payload = self._post({"type": "clearinghouseState", "user": trader})
        rows = payload.get("assetPositions", []) if isinstance(payload, dict) else []
        positions: list[TraderPosition] = []
        for row in rows:
            position = row.get("position", row) if isinstance(row, dict) else row
            if isinstance(position, dict):
                parsed = TraderPosition.from_dict(trader, position)
                if parsed.asset:
                    positions.append(parsed)
        return positions

    def _post(self, payload: dict[str, Any]) -> Any:
        req = urllib.request.Request(
            self.config.api_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "User-Agent": "SapphireCounterpartyIntel/0.1",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310 - public HTTPS API
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
            return {}

    def _record_call(self) -> None:
        counters = _prune(_load_counters())
        if len(counters.get("calls", [])) >= self.config.max_refresh_per_hour:
            raise RuntimeError(f"rate_limit: {self.config.max_refresh_per_hour}/hour exceeded")
        counters.setdefault("calls", []).append(time.time())
        _save_counters(counters)


def _load_counters() -> dict[str, Any]:
    if not COUNTER_PATH.exists():
        return {"calls": []}
    try:
        return json.loads(COUNTER_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"calls": []}


def _save_counters(counters: dict[str, Any]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    COUNTER_PATH.write_text(json.dumps(counters, indent=2, sort_keys=True), encoding="utf-8")


def _prune(counters: dict[str, Any]) -> dict[str, Any]:
    cutoff = time.time() - 3600
    counters["calls"] = [t for t in counters.get("calls", []) if t >= cutoff]
    return counters


def _mock_leaderboard() -> list[dict[str, Any]]:
    return [
        {
            "address": "0xaaa",
            "display_name": "dry-alpha",
            "realized_pnl_30d_usd": 250000,
            "realized_pnl_90d_usd": 900000,
            "sharpe_30d": 2.1,
            "win_rate_30d": 0.62,
        },
        {
            "address": "0xbbb",
            "display_name": "dry-beta",
            "realized_pnl_30d_usd": 120000,
            "realized_pnl_90d_usd": 300000,
            "sharpe_30d": 1.4,
            "win_rate_30d": 0.55,
        },
        {
            "address": "0xccc",
            "display_name": "small",
            "realized_pnl_30d_usd": 1000,
            "realized_pnl_90d_usd": 5000,
            "sharpe_30d": 4.0,
        },
    ]


def _mock_positions(trader: str) -> list[dict[str, Any]]:
    if trader.lower().endswith("bbb"):
        return [{"coin": "ETH", "side": "short", "notional": 75000, "entryPx": 3100}]
    return [{"coin": "BTC", "side": "long", "notional": 150000, "entryPx": 65000}]
