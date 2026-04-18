"""Dune Analytics — execute saved queries via the v1 REST API.

Env: ``DUNE_API_KEY``
Docs: https://docs.dune.com/api-reference/overview/introduction

Free tier: 1,000 executions/month, 10 concurrent executions, 1 GB of
query result storage. The API is execution-centric: you POST to
``/query/{id}/execute``, poll ``/execution/{id}/status``, then GET
``/execution/{id}/results``.

This client exposes a blocking convenience wrapper ``run_query`` that
handles the poll loop with a sensible timeout + backoff.
"""

from __future__ import annotations

import time
from typing import Any

from ._common import get_env, http_get, http_post_json


class DuneClient:
    _BASE = "https://api.dune.com/api/v1"

    def __init__(self, api_key: str | None = None) -> None:
        self._key = api_key or get_env("DUNE_API_KEY")

    def _headers(self) -> dict[str, str]:
        return {"X-DUNE-API-KEY": self._key}

    # --- low level --------------------------------------------------------

    def execute(self, query_id: int, params: dict[str, Any] | None = None) -> str:
        payload: dict[str, Any] = {}
        if params:
            payload["query_parameters"] = params
        resp = http_post_json(
            f"{self._BASE}/query/{query_id}/execute",
            payload,
            headers=self._headers(),
            cache=False,  # each execution is a new object
        )
        return resp.get("execution_id", "")

    def status(self, execution_id: str) -> Any:
        return http_get(
            f"{self._BASE}/execution/{execution_id}/status",
            headers=self._headers(),
            cache=False,
        )

    def results(self, execution_id: str) -> Any:
        return http_get(
            f"{self._BASE}/execution/{execution_id}/results",
            headers=self._headers(),
        )

    # --- convenience ------------------------------------------------------

    def run_query(
        self,
        query_id: int,
        params: dict[str, Any] | None = None,
        *,
        poll_interval: float = 2.0,
        timeout_s: float = 120.0,
    ) -> Any:
        """Execute, wait for completion, return results.

        Raises :class:`lib.chain.sources.SourceError` if the execution
        fails or exceeds ``timeout_s``.
        """
        from ..sources import SourceError  # re-import to keep namespace clean

        exec_id = self.execute(query_id, params)
        if not exec_id:
            raise SourceError(f"dune: execute returned no execution_id for query {query_id}")
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            s = self.status(exec_id)
            state = s.get("state", "")
            if state == "QUERY_STATE_COMPLETED":
                return self.results(exec_id)
            if state in {"QUERY_STATE_FAILED", "QUERY_STATE_CANCELLED"}:
                raise SourceError(f"dune: query {query_id} ended in {state}: {s}")
            time.sleep(poll_interval)
        raise SourceError(f"dune: query {query_id} timed out after {timeout_s}s")
