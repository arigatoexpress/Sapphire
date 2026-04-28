"""Glassnode REST provider for Sapphire on-chain intelligence.

Live mode requires both ``SAPPHIRE_GLASSNODE_LIVE=1`` and
``GLASSNODE_API_KEY``. Without that explicit opt-in, methods return stable
fixture data and never touch the network.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from lib.chain.aggregator import (
    clamp_backfill_days,
    enforce_provider_cap,
    latest_series_value,
    provider_live_enabled,
)

from ._common import SourceError, http_get

GLASSNODE_METRICS: dict[str, str] = {
    "active_addresses": "addresses/active_count",
    "transaction_rate": "transactions/rate",
    "sopr": "indicators/sopr",
    "nupl": "indicators/net_unrealized_profit_loss",
    "mvrv_z": "market/mvrv_z_score",
    "hodl_waves": "supply/hodl_waves",
    "lth_supply": "supply/long_term_holder",
}


class GlassnodeClient:
    """Small stdlib-only Glassnode client."""

    _BASE = "https://api.glassnode.com/v1/metrics"

    def __init__(self, api_key: str | None = None, live: bool | None = None) -> None:
        import os

        self._key = api_key or os.getenv("GLASSNODE_API_KEY", "")
        self.live = provider_live_enabled("glassnode") if live is None else bool(live)

    @property
    def mode(self) -> str:
        return "live" if self.live else "fixture"

    def _headers(self) -> dict[str, str]:
        if not self._key:
            raise SourceError("glassnode: missing GLASSNODE_API_KEY")
        return {"X-Api-Key": self._key}

    def metric(
        self,
        metric_path: str,
        *,
        asset: str = "BTC",
        interval: str = "24h",
        days: int | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch one Glassnode metric path, or return fixture series."""

        days = clamp_backfill_days(days)
        clean_path = metric_path.strip("/")
        clean_asset = asset.lower()
        if not self.live:
            return self._fixture_series(clean_path, clean_asset)

        enforce_provider_cap("glassnode")
        since = int((datetime.now(UTC) - timedelta(days=days)).timestamp())
        data = http_get(
            f"{self._BASE}/{clean_path}",
            headers=self._headers(),
            params={
                "a": clean_asset,
                "i": interval,
                "s": since,
                "timestamp_format": "humanized",
            },
        )
        if not isinstance(data, list):
            raise SourceError(f"glassnode: {clean_path} returned non-list")
        return data

    def active_addresses(self, asset: str = "BTC", days: int | None = None) -> list[dict[str, Any]]:
        return self.metric(GLASSNODE_METRICS["active_addresses"], asset=asset, days=days)

    def transaction_rate(self, asset: str = "BTC", days: int | None = None) -> list[dict[str, Any]]:
        return self.metric(GLASSNODE_METRICS["transaction_rate"], asset=asset, days=days)

    def sopr(self, asset: str = "BTC", days: int | None = None) -> list[dict[str, Any]]:
        return self.metric(GLASSNODE_METRICS["sopr"], asset=asset, days=days)

    def nupl(self, asset: str = "BTC", days: int | None = None) -> list[dict[str, Any]]:
        return self.metric(GLASSNODE_METRICS["nupl"], asset=asset, days=days)

    def mvrv_z(self, asset: str = "BTC", days: int | None = None) -> list[dict[str, Any]]:
        return self.metric(GLASSNODE_METRICS["mvrv_z"], asset=asset, days=days)

    def hodl_waves(self, asset: str = "BTC", days: int | None = None) -> list[dict[str, Any]]:
        return self.metric(GLASSNODE_METRICS["hodl_waves"], asset=asset, days=days)

    def lth_supply(self, asset: str = "BTC", days: int | None = None) -> list[dict[str, Any]]:
        return self.metric(GLASSNODE_METRICS["lth_supply"], asset=asset, days=days)

    def etf_balance_proxies(self, asset: str = "BTC", days: int | None = None) -> dict[str, Any]:
        """Return ETF-adjacent balance proxies without inventing an ETF endpoint.

        Glassnode's public catalog shifts by plan/tier. Sapphire therefore keeps
        ETF context as a derived proxy from available live/fixture balance
        metrics, rather than hard-coding an unverified ETF-specific endpoint.
        """

        return {
            "provider": "glassnode",
            "mode": self.mode,
            "asset": asset.upper(),
            "proxy_source": "derived_from_holder_profitability_and_long_term_supply",
            "mvrv_z": latest_series_value(self.mvrv_z(asset, days=days)),
            "nupl": latest_series_value(self.nupl(asset, days=days)),
            "lth_supply": latest_series_value(self.lth_supply(asset, days=days)),
        }

    def asset_snapshot(self, asset: str = "BTC", days: int | None = None) -> dict[str, Any]:
        active = self.active_addresses(asset, days=days)
        tx_rate = self.transaction_rate(asset, days=days)
        sopr = self.sopr(asset, days=days)
        nupl = self.nupl(asset, days=days)
        mvrv_z = self.mvrv_z(asset, days=days)
        hodl_waves = self.hodl_waves(asset, days=days)
        lth_supply = self.lth_supply(asset, days=days)
        return {
            "provider": "glassnode",
            "mode": self.mode,
            "asset": asset.upper(),
            "backfill_days": clamp_backfill_days(days),
            "active_addresses": latest_series_value(active),
            "transaction_rate": latest_series_value(tx_rate),
            "sopr": latest_series_value(sopr),
            "nupl": latest_series_value(nupl),
            "mvrv_z": latest_series_value(mvrv_z),
            "hodl_waves_1y_plus_pct": latest_series_value(hodl_waves),
            "lth_supply": latest_series_value(lth_supply),
            "etf_balance_proxies": self.etf_balance_proxies(asset, days=days),
        }

    def _fixture_series(self, metric_path: str, asset: str) -> list[dict[str, Any]]:
        base = {
            "btc": {
                "addresses/active_count": 910_000,
                "transactions/rate": 6.4,
                "indicators/sopr": 1.01,
                "indicators/net_unrealized_profit_loss": 0.48,
                "market/mvrv_z_score": 2.4,
                "supply/hodl_waves": 0.62,
                "supply/long_term_holder": 14_600_000,
            },
            "eth": {
                "addresses/active_count": 520_000,
                "transactions/rate": 12.1,
                "indicators/sopr": 1.0,
                "indicators/net_unrealized_profit_loss": 0.31,
                "market/mvrv_z_score": 1.8,
                "supply/hodl_waves": 0.47,
                "supply/long_term_holder": 78_000_000,
            },
            "sol": {
                "addresses/active_count": 1_250_000,
                "transactions/rate": 31.5,
                "indicators/sopr": 0.99,
                "indicators/net_unrealized_profit_loss": 0.22,
                "market/mvrv_z_score": 1.3,
                "supply/hodl_waves": 0.36,
                "supply/long_term_holder": 355_000_000,
            },
        }
        value = base.get(asset, base["btc"]).get(metric_path, 0.0)
        return [
            {"t": "2026-04-26T00:00:00Z", "v": value * 0.98},
            {"t": "2026-04-27T00:00:00Z", "v": value},
        ]
