"""Async client for interacting with the wallet risk orchestrator."""

from __future__ import annotations

from typing import Any, Dict

import httpx


class RiskOrchestratorClient:
    def __init__(self, base_url: str, *, timeout: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(base_url=self._base_url, timeout=timeout)

    async def close(self) -> None:
        await self._client.aclose()

    async def submit_order(self, bot_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        response = await self._client.post(f"/order/{bot_id}", json=payload)
        response.raise_for_status()
        return response.json()

    async def register_decision(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        response = await self._client.post("/register_decision", json=payload)
        response.raise_for_status()
        return response.json()

    async def portfolio(self) -> Dict[str, Any]:
        response = await self._client.get("/portfolio")
        response.raise_for_status()
        return response.json()

    async def emergency_stop(self) -> Dict[str, Any]:
        response = await self._client.post("/emergency_stop")
        response.raise_for_status()
        return response.json()

