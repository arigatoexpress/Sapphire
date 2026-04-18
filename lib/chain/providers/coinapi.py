"""CoinAPI — historical OHLCV, funding rates, order book.

Env: ``COINAPI_KEY``
Docs: https://docs.coinapi.io/

Free tier: 100 requests/day.  Watch the counter — each historical OHLCV
call can burn multiple quota units depending on period + limit.
"""

from __future__ import annotations

from typing import Any

from ._common import get_env, http_get


class CoinAPIClient:
    _BASE = "https://rest.coinapi.io/v1"

    def __init__(self, api_key: str | None = None) -> None:
        self._key = api_key or get_env("COINAPI_KEY")

    def _headers(self) -> dict[str, str]:
        return {"X-CoinAPI-Key": self._key}

    def exchanges(self) -> Any:
        return http_get(f"{self._BASE}/exchanges", headers=self._headers())

    def ohlcv_latest(
        self, symbol_id: str, period: str = "1HRS", limit: int = 100
    ) -> Any:
        """Latest OHLCV for a symbol_id like ``BITSTAMP_SPOT_BTC_USD``."""
        return http_get(
            f"{self._BASE}/ohlcv/{symbol_id}/latest",
            headers=self._headers(),
            params={"period_id": period, "limit": limit},
        )

    def funding_rates(self, symbol_id: str, limit: int = 100) -> Any:
        """Historical funding rates for a perpetual symbol."""
        return http_get(
            f"{self._BASE}/metrics/symbol/listing",
            headers=self._headers(),
            params={"symbol_id": symbol_id, "limit": limit},
        )

    def quote_current(self, symbol_id: str) -> Any:
        return http_get(
            f"{self._BASE}/quotes/{symbol_id}/current",
            headers=self._headers(),
        )
