"""Coinglass — OI, funding, liquidation heatmap.

Env: ``COINGLASS_API_KEY``
Docs: https://coinglass.github.io/API-Reference/

Free tier: 30 requests/minute (burst 300), endpoint whitelist smaller
than Standard ($29/mo).  Key data:
  * ``/api/futures/openInterest/ohlc-history`` — OI curve.
  * ``/api/futures/fundingRate/ohlc-history`` — funding curve.
  * ``/api/futures/liquidation/coin-list`` — aggregated liquidations.
"""

from __future__ import annotations

from typing import Any

from ._common import get_env, http_get


class CoinglassClient:
    _BASE = "https://open-api-v3.coinglass.com"

    def __init__(self, api_key: str | None = None) -> None:
        self._key = api_key or get_env("COINGLASS_API_KEY")

    def _headers(self) -> dict[str, str]:
        return {"coinglassSecret": self._key}

    def open_interest(
        self, symbol: str = "BTC", exchange: str = "Binance", interval: str = "h4", limit: int = 100
    ) -> Any:
        return http_get(
            f"{self._BASE}/api/futures/openInterest/ohlc-history",
            headers=self._headers(),
            params={
                "symbol": symbol,
                "exchange_name": exchange,
                "interval": interval,
                "limit": limit,
            },
        )

    def funding_rate(
        self, symbol: str = "BTC", exchange: str = "Binance", interval: str = "h4", limit: int = 100
    ) -> Any:
        return http_get(
            f"{self._BASE}/api/futures/fundingRate/ohlc-history",
            headers=self._headers(),
            params={
                "symbol": symbol,
                "exchange_name": exchange,
                "interval": interval,
                "limit": limit,
            },
        )

    def liquidations(self, time_type: str = "h4") -> Any:
        return http_get(
            f"{self._BASE}/api/futures/liquidation/coin-list",
            headers=self._headers(),
            params={"time_type": time_type},
        )
