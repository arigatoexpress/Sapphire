"""Dune named-query source with a one-hour local cache.

Primary docs retrieved 2026-04-28:
https://docs.dune.com/api-reference/overview/introduction and
https://docs.dune.com/api-reference/executions/execution-object
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from lib.correlator.sources import SourceSignal

from . import (
    age_seconds,
    cache_dir,
    canonical_symbol,
    clamp,
    live_enabled,
    parse_iso,
    read_fresh_json,
    read_json,
    secret_value,
    utc_now,
    write_json,
)

RunQuery = Callable[[int, Mapping[str, Any] | None], Any]

DEFAULT_CONFIG_PATH = Path.home() / ".sapphire" / "dune_named_queries.json"
TTL_SECONDS = 3600


@dataclass
class DuneNamedQuerySource:
    """Execute operator-named Dune queries only when live-gated."""

    name: str = "dune_named_queries"
    config_path: Path = DEFAULT_CONFIG_PATH
    cache_path: Path = field(default_factory=lambda: cache_dir("dune") / "named_queries.json")
    runner: RunQuery | None = None

    def _config(self) -> dict[str, Any]:
        config = read_json(self.config_path)
        return config if isinstance(config, dict) else {"queries": []}

    def _run_query(self, query_id: int, params: Mapping[str, Any] | None) -> Any:
        if self.runner:
            return self.runner(query_id, params)
        from lib.chain.providers.dune import DuneClient

        key = secret_value("DUNE_API_KEY")
        if not key:
            return {"result": {"rows": []}, "error": "missing_dune_api_key"}
        return DuneClient(api_key=key).run_query(query_id, dict(params or {}))

    def _snapshot(self) -> dict[str, Any]:
        cached = read_fresh_json(self.cache_path, ttl_seconds=TTL_SECONDS)
        if isinstance(cached, dict):
            return cached
        if not live_enabled("DUNE"):
            stale = read_json(self.cache_path)
            return stale if isinstance(stale, dict) else {"queries": []}
        now = utc_now()
        rows: list[dict[str, Any]] = []
        for query in self._config().get("queries", []):
            if not isinstance(query, Mapping):
                continue
            query_id = int(query.get("id") or query.get("query_id") or 0)
            if query_id <= 0:
                continue
            result = self._run_query(query_id, query.get("params") if isinstance(query.get("params"), Mapping) else None)
            rows.append(
                {
                    "name": str(query.get("name") or query_id),
                    "symbol": canonical_symbol(query.get("symbol")),
                    "query_id": query_id,
                    "result": result,
                    "retrieved_at": now.isoformat(),
                }
            )
        payload = {"retrieved_at": now.isoformat(), "queries": rows}
        write_json(self.cache_path, payload)
        return payload

    @staticmethod
    def _rows(result: Any) -> list[Mapping[str, Any]]:
        if isinstance(result, Mapping):
            for path in (
                ("result", "rows"),
                ("result", "rows", "rows"),
                ("rows",),
            ):
                current: Any = result
                for key in path:
                    current = current.get(key) if isinstance(current, Mapping) else None
                if isinstance(current, list):
                    return [r for r in current if isinstance(r, Mapping)]
        return []

    @staticmethod
    def _row_signal(row: Mapping[str, Any], symbol: str) -> tuple[str, float]:
        direction = str(row.get("direction") or row.get("signal") or "").strip().lower()
        if direction in {"bull", "bear", "neutral"}:
            return direction, clamp(row.get("confidence"))
        score = row.get("score") or row.get("value") or row.get("net_flow")
        try:
            value = float(score)
        except (TypeError, ValueError):
            return "neutral", 0.35
        if value > 0:
            return "bull", clamp(min(abs(value), 1.0), default=0.55)
        if value < 0:
            return "bear", clamp(min(abs(value), 1.0), default=0.55)
        return "neutral", 0.35

    def latest_for(self, symbol: str, timeframe: str) -> SourceSignal | None:
        target = canonical_symbol(symbol)
        for query in reversed(self._snapshot().get("queries") or []):
            if not isinstance(query, Mapping):
                continue
            if query.get("symbol") and canonical_symbol(query.get("symbol")) != target:
                continue
            rows = self._rows(query.get("result"))
            row = rows[-1] if rows else {}
            direction, confidence = self._row_signal(row, target)
            ts = parse_iso(row.get("timestamp") if isinstance(row, Mapping) else None)
            ts = ts or parse_iso(query.get("retrieved_at")) or utc_now()
            return SourceSignal(
                source=self.name,
                symbol=target,
                timeframe=timeframe,
                direction=direction,
                confidence=confidence,
                age_seconds=age_seconds(ts),
                timestamp_iso=ts.isoformat(),
                raw={
                    "query_name": query.get("name"),
                    "query_id": query.get("query_id"),
                    "live_operator_flag": live_enabled("DUNE"),
                },
            )
        return None


def write_example_config(path: Path = DEFAULT_CONFIG_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"queries": [{"name": "btc_flow", "id": 123456, "symbol": "BTC"}]}, indent=2),
        encoding="utf-8",
    )
