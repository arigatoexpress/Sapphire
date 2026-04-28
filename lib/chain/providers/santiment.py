"""Santiment - on-chain + social metrics via GraphQL.

Env: ``SANTIMENT_API_KEY``
Docs: https://api.santiment.net/graphql  (free tier: 600 queries/month, rate-limited)

The free tier only exposes a subset of metrics; Pro unlocks everything.
We hit the ``/graphql`` endpoint directly instead of pulling their
Python SDK - the SDK adds ~15 MB of transitive deps.

Live mode requires both ``SAPPHIRE_SANTIMENT_LIVE=1`` and
``SANTIMENT_API_KEY``. Without that explicit opt-in, methods return stable
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

from ._common import SourceError, get_env, http_post_json

_SLUGS = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
}


class SantimentClient:
    _ENDPOINT = "https://api.santiment.net/graphql"

    def __init__(self, api_key: str | None = None, live: bool | None = None) -> None:
        self.live = provider_live_enabled("santiment") if live is None else bool(live)
        if api_key is not None:
            self._key = api_key
        elif self.live:
            self._key = get_env("SANTIMENT_API_KEY")
        else:
            self._key = ""

    @property
    def mode(self) -> str:
        return "live" if self.live else "fixture"

    def _headers(self) -> dict[str, str]:
        if not self._key:
            raise SourceError("santiment: missing SANTIMENT_API_KEY")
        return {"Authorization": f"Apikey {self._key}"}

    def query(self, gql: str, variables: dict[str, Any] | None = None) -> Any:
        if not self.live:
            return {"data": {"fixture": True, "query": "dry_run"}, "live": False}
        enforce_provider_cap("santiment")
        payload: dict[str, Any] = {"query": gql}
        if variables:
            payload["variables"] = variables
        return http_post_json(self._ENDPOINT, payload, headers=self._headers())

    def timeseries_metric(
        self,
        metric: str,
        *,
        slug: str = "bitcoin",
        from_iso: str = "",
        to_iso: str = "",
        interval: str = "1d",
    ) -> Any:
        if not self.live:
            return self._fixture_timeseries(metric, slug)
        safe_interval = "1h" if interval == "1h" else "1d"
        gql = f"""
        query($metric:String!, $slug:String!, $from:DateTime!, $to:DateTime!) {{
          getMetric(metric:$metric) {{
            timeseriesData(slug:$slug, from:$from, to:$to, interval:"{safe_interval}") {{
              datetime value
            }}
          }}
        }}
        """
        return self.query(
            gql,
            {
                "metric": metric,
                "slug": slug,
                "from": from_iso,
                "to": to_iso,
            },
        )

    def social_volume(self, slug: str = "bitcoin", from_iso: str = "", to_iso: str = "") -> Any:
        return self.timeseries_metric(
            "social_volume_total",
            slug=slug,
            from_iso=from_iso,
            to_iso=to_iso,
            interval="1h",
        )

    def social_dominance(self, slug: str = "bitcoin", from_iso: str = "", to_iso: str = "") -> Any:
        return self.timeseries_metric(
            "social_dominance_total",
            slug=slug,
            from_iso=from_iso,
            to_iso=to_iso,
            interval="1h",
        )

    def age_consumed(self, slug: str = "bitcoin", from_iso: str = "", to_iso: str = "") -> Any:
        return self.timeseries_metric(
            "age_consumed",
            slug=slug,
            from_iso=from_iso,
            to_iso=to_iso,
            interval="1d",
        )

    def network_growth(self, slug: str = "bitcoin", from_iso: str = "", to_iso: str = "") -> Any:
        return self.timeseries_metric(
            "network_growth",
            slug=slug,
            from_iso=from_iso,
            to_iso=to_iso,
            interval="1d",
        )

    def dev_activity(self, slug: str = "bitcoin", from_iso: str = "", to_iso: str = "") -> Any:
        return self.timeseries_metric(
            "dev_activity",
            slug=slug,
            from_iso=from_iso,
            to_iso=to_iso,
            interval="1d",
        )

    def exchange_open_interest(
        self,
        slug: str = "bitcoin",
        from_iso: str = "",
        to_iso: str = "",
    ) -> Any:
        return self.timeseries_metric(
            "exchange_open_interest",
            slug=slug,
            from_iso=from_iso,
            to_iso=to_iso,
            interval="1d",
        )

    def asset_snapshot(self, asset: str = "BTC", days: int | None = None) -> dict[str, Any]:
        days = clamp_backfill_days(days)
        slug = _SLUGS.get(asset.upper(), asset.lower())
        to_iso = datetime.now(UTC).isoformat()
        from_iso = (datetime.now(UTC) - timedelta(days=days)).isoformat()
        social = self.social_volume(slug=slug, from_iso=from_iso, to_iso=to_iso)
        dominance = self.social_dominance(slug=slug, from_iso=from_iso, to_iso=to_iso)
        age = self.age_consumed(slug=slug, from_iso=from_iso, to_iso=to_iso)
        growth = self.network_growth(slug=slug, from_iso=from_iso, to_iso=to_iso)
        dev = self.dev_activity(slug=slug, from_iso=from_iso, to_iso=to_iso)
        oi = self.exchange_open_interest(slug=slug, from_iso=from_iso, to_iso=to_iso)
        return {
            "provider": "santiment",
            "mode": self.mode,
            "asset": asset.upper(),
            "slug": slug,
            "backfill_days": days,
            "social_volume_total": latest_series_value(_extract_series(social)),
            "social_dominance_total": latest_series_value(_extract_series(dominance)),
            "age_consumed": latest_series_value(_extract_series(age)),
            "network_growth": latest_series_value(_extract_series(growth)),
            "dev_activity": latest_series_value(_extract_series(dev)),
            "exchange_open_interest": latest_series_value(_extract_series(oi)),
        }

    def _fixture_timeseries(self, metric: str, slug: str) -> dict[str, Any]:
        values = {
            "bitcoin": {
                "social_volume_total": 4_200,
                "social_dominance_total": 18.4,
                "age_consumed": 7_900_000,
                "network_growth": 121_000,
                "dev_activity": 84,
                "exchange_open_interest": 13_500_000_000,
            },
            "ethereum": {
                "social_volume_total": 2_900,
                "social_dominance_total": 12.2,
                "age_consumed": 4_100_000,
                "network_growth": 74_000,
                "dev_activity": 220,
                "exchange_open_interest": 7_250_000_000,
            },
            "solana": {
                "social_volume_total": 1_850,
                "social_dominance_total": 7.4,
                "age_consumed": 2_500_000,
                "network_growth": 96_000,
                "dev_activity": 96,
                "exchange_open_interest": 1_650_000_000,
            },
        }
        value = values.get(slug, values["bitcoin"]).get(metric, 0)
        return {
            "data": {
                "getMetric": {
                    "timeseriesData": [
                        {"datetime": "2026-04-26T00:00:00Z", "value": value * 0.95},
                        {"datetime": "2026-04-27T00:00:00Z", "value": value},
                    ]
                }
            }
        }


def _extract_series(payload: Any) -> list[dict[str, Any]]:
    try:
        series = payload["data"]["getMetric"]["timeseriesData"]
    except (KeyError, TypeError):
        return []
    return series if isinstance(series, list) else []
