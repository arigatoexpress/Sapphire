"""DeFiLlama TVL and revenue source.

Primary docs retrieved 2026-04-28:
https://docs.llama.fi/ and https://defillama.com/data-definitions
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from lib.correlator.sources import SourceSignal

from . import (
    age_seconds,
    cache_dir,
    canonical_symbol,
    clamp,
    http_get_json,
    live_enabled,
    parse_iso,
    read_json,
    utc_now,
    write_json,
)

FetchJson = Callable[[str, Mapping[str, str] | None], Any]

DEFAULT_PROTOCOLS: dict[str, str] = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
}
PROTOCOL_URL = "https://api.llama.fi/protocol/{slug}"
FEES_URL = "https://api.llama.fi/summary/fees/{slug}?dataType=dailyRevenue"


@dataclass
class DeFiLlamaSource:
    """Cache-first DeFiLlama protocol-fundamentals adapter."""

    name: str = "defillama"
    protocol_map: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_PROTOCOLS))
    cache_path: Path = field(default_factory=lambda: cache_dir("defillama") / "latest.json")
    fetcher: FetchJson | None = None

    def _fetch(self, url: str, headers: Mapping[str, str] | None = None) -> Any:
        if self.fetcher:
            return self.fetcher(url, headers)
        return http_get_json(url, headers=headers)

    def _snapshot(self) -> dict[str, Any]:
        if not live_enabled("DEFILLAMA"):
            cached = read_json(self.cache_path)
            return cached if isinstance(cached, dict) else {}
        now = utc_now()
        rows: dict[str, Any] = {}
        for symbol, slug in self.protocol_map.items():
            protocol = self._fetch(PROTOCOL_URL.format(slug=slug), None)
            fees = self._fetch(FEES_URL.format(slug=slug), None)
            rows[canonical_symbol(symbol)] = {
                "slug": slug,
                "protocol": protocol,
                "fees": fees,
                "retrieved_at": now.isoformat(),
            }
        payload = {"retrieved_at": now.isoformat(), "protocols": rows}
        write_json(self.cache_path, payload)
        return payload

    @staticmethod
    def _latest_tvl(protocol: Mapping[str, Any]) -> float | None:
        tvl = protocol.get("tvl")
        if isinstance(tvl, list) and tvl:
            last = tvl[-1]
            if isinstance(last, Mapping):
                value = last.get("totalLiquidityUSD") or last.get("tvl")
                try:
                    return float(value)
                except (TypeError, ValueError):
                    return None
        for key in ("currentChainTvls", "chainTvls"):
            values = protocol.get(key)
            if isinstance(values, Mapping):
                total = 0.0
                for value in values.values():
                    try:
                        total += float(value)
                    except (TypeError, ValueError):
                        pass
                return total or None
        return None

    @staticmethod
    def _latest_revenue(fees: Mapping[str, Any]) -> float | None:
        values = fees.get("totalDataChartBreakdown") or fees.get("totalDataChart")
        if isinstance(values, list) and values:
            latest = values[-1]
            if isinstance(latest, list) and len(latest) >= 2:
                try:
                    return float(latest[1])
                except (TypeError, ValueError):
                    return None
        try:
            return float(fees.get("total24h"))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def signal_from_snapshot(symbol: str, row: Mapping[str, Any]) -> SourceSignal:
        protocol = row.get("protocol") if isinstance(row.get("protocol"), Mapping) else {}
        fees = row.get("fees") if isinstance(row.get("fees"), Mapping) else {}
        tvl = DeFiLlamaSource._latest_tvl(protocol)
        revenue = DeFiLlamaSource._latest_revenue(fees)
        tvl_change = clamp(protocol.get("change_1d"), default=0.0)
        revenue_change = clamp(fees.get("change_1d"), default=0.0)
        strength = ((tvl_change - 0.5) + (revenue_change - 0.5)) / 2
        direction = "bull" if strength > 0.05 else "bear" if strength < -0.05 else "neutral"
        confidence = clamp(0.5 + abs(strength), default=0.5)
        ts = parse_iso(row.get("retrieved_at")) or datetime.now(UTC)
        return SourceSignal(
            source="defillama",
            symbol=canonical_symbol(symbol),
            timeframe="1d",
            direction=direction,
            confidence=confidence,
            age_seconds=age_seconds(ts),
            timestamp_iso=ts.isoformat(),
            raw={
                "slug": row.get("slug"),
                "tvl_usd": tvl,
                "daily_revenue_usd": revenue,
                "live_operator_flag": live_enabled("DEFILLAMA"),
            },
        )

    def latest_for(self, symbol: str, timeframe: str) -> SourceSignal | None:
        target = canonical_symbol(symbol)
        row = (self._snapshot().get("protocols") or {}).get(target)
        if not isinstance(row, Mapping):
            return None
        signal = self.signal_from_snapshot(target, row)
        return SourceSignal(**{**signal.to_dict(), "timeframe": timeframe})
