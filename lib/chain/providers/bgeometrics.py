"""BGeometrics — BTC on-chain metrics (MVRV, SOPR, NVT, realized price).

Env: ``BGEOMETRICS_API_KEY``
Docs: https://bgeometrics.com/api  (verify exact endpoints after signup)

The exact base URL and endpoint set have drifted between versions; the
methods below target the v2 REST surface. If the response shape changes
we return the raw payload so callers can adapt without a client update.

Typical free-tier limits (2026-04): 500 requests/day, 60/minute.
"""

from __future__ import annotations

from typing import Any

from ._common import get_env, http_get


class BGeometricsClient:
    _BASE = "https://api.bgeometrics.com/v2"

    def __init__(self, api_key: str | None = None) -> None:
        self._key = api_key or get_env("BGEOMETRICS_API_KEY")

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._key}"}

    def mvrv_z_score(self) -> Any:
        return http_get(f"{self._BASE}/metrics/mvrv_z_score", headers=self._headers())

    def sopr(self, flavour: str = "aSOPR") -> Any:
        # flavour ∈ {"SOPR", "aSOPR", "STH-SOPR", "LTH-SOPR"}
        return http_get(f"{self._BASE}/metrics/sopr/{flavour}", headers=self._headers())

    def nvt(self) -> Any:
        return http_get(f"{self._BASE}/metrics/nvt", headers=self._headers())

    def realized_price(self) -> Any:
        return http_get(f"{self._BASE}/metrics/realized_price", headers=self._headers())

    def puell_multiple(self) -> Any:
        return http_get(f"{self._BASE}/metrics/puell_multiple", headers=self._headers())
