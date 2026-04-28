"""Santiment — on-chain + social metrics via GraphQL.

Env: ``SANTIMENT_API_KEY``
Docs: https://api.santiment.net/graphql  (free tier: 600 queries/month, rate-limited)

The free tier only exposes a subset of metrics; Pro unlocks everything.
We hit the ``/graphql`` endpoint directly instead of pulling their
Python SDK — the SDK adds ~15 MB of transitive deps.
"""

from __future__ import annotations

from typing import Any

from ._common import get_env, http_post_json


class SantimentClient:
    _ENDPOINT = "https://api.santiment.net/graphql"

    def __init__(self, api_key: str | None = None) -> None:
        self._key = api_key or get_env("SANTIMENT_API_KEY")

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Apikey {self._key}"}

    def query(self, gql: str, variables: dict[str, Any] | None = None) -> Any:
        payload: dict[str, Any] = {"query": gql}
        if variables:
            payload["variables"] = variables
        return http_post_json(self._ENDPOINT, payload, headers=self._headers())

    def social_volume(self, slug: str = "bitcoin", from_iso: str = "", to_iso: str = "") -> Any:
        gql = """
        query($slug:String!, $from:DateTime!, $to:DateTime!) {
          getMetric(metric:"social_volume_total") {
            timeseriesData(slug:$slug, from:$from, to:$to, interval:"1h") {
              datetime value
            }
          }
        }
        """
        return self.query(gql, {"slug": slug, "from": from_iso, "to": to_iso})

    def dev_activity(self, slug: str = "bitcoin", from_iso: str = "", to_iso: str = "") -> Any:
        gql = """
        query($slug:String!, $from:DateTime!, $to:DateTime!) {
          getMetric(metric:"dev_activity") {
            timeseriesData(slug:$slug, from:$from, to:$to, interval:"1d") {
              datetime value
            }
          }
        }
        """
        return self.query(gql, {"slug": slug, "from": from_iso, "to": to_iso})
