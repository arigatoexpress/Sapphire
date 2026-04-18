"""Whale Alert — large transaction stream.

Env: ``WHALE_ALERT_API_KEY``
Docs: https://docs.whale-alert.io/

Free "Personal" tier: 60 requests/hour, one transaction feed per call,
100 min_value threshold.

Key endpoints:
  * ``/v1/transactions`` — windowed list of whale transfers.
  * ``/v1/status`` — API + blockchain health.
"""

from __future__ import annotations

import time
from typing import Any

from ._common import get_env, http_get


class WhaleAlertClient:
    _BASE = "https://api.whale-alert.io/v1"

    def __init__(self, api_key: str | None = None) -> None:
        self._key = api_key or get_env("WHALE_ALERT_API_KEY")

    def _params(self, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        out: dict[str, Any] = {"api_key": self._key}
        if extra:
            out.update(extra)
        return out

    def status(self) -> Any:
        return http_get(f"{self._BASE}/status", params=self._params())

    def transactions(
        self,
        *,
        min_value: int = 500_000,
        start: int | None = None,
        end: int | None = None,
        currency: str | None = None,
        limit: int = 100,
    ) -> Any:
        now = int(time.time())
        start = start or now - 3600
        end = end or now
        params = self._params(
            {
                "start": start,
                "end": end,
                "min_value": min_value,
                "limit": limit,
                "currency": currency,
            }
        )
        return http_get(f"{self._BASE}/transactions", params=params, cache=False)
