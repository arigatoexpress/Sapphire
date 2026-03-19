"""NemoClaw dispatch — route tasks to NVIDIA NemoClaw runtime on Windows PC.

NemoClaw runs on the Windows PC (RTX 5070 Ti, Tailscale 100.71.10.48) via the
OpenClaw gateway. It handles GPU-heavy work: backtesting, inference, forecasting.

Task routing:
    type:backtest   → NemoClaw (Chronos forecasting, Monte Carlo, walk-forward)
    type:inference  → NemoClaw (Nemotron Super 120B, local embeddings)
    type:compute    → NemoClaw (GPU-bound signal processing)
    type:trading    → openclaw_dispatch (stays on Mac)
    type:pm         → openclaw_dispatch (stays on Mac)
"""
from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

NEMOCLAW_BASE_URL = os.getenv("NEMOCLAW_URL", "http://100.71.10.48:18789")
OPENCLAW_BASE_URL = os.getenv("OPENCLAW_URL", "http://localhost:18789")
REQUEST_TIMEOUT = 60.0

# Task types that should route to NemoClaw (GPU on Windows PC)
NEMOCLAW_TASK_TYPES = {"backtest", "inference", "compute", "forecast", "embed"}


def _requires_gpu(task_type: str) -> bool:
    return str(task_type).lower() in NEMOCLAW_TASK_TYPES


async def dispatch(
    task_type: str,
    payload: dict[str, Any],
    *,
    priority: str = "p2",
    project: str = "",
    timeout: float = REQUEST_TIMEOUT,
) -> dict[str, Any]:
    """Dispatch a task to NemoClaw or OpenClaw based on task type.

    Args:
        task_type: Task domain — determines routing (backtest/inference → NemoClaw,
                   others → OpenClaw on Mac).
        payload: Task-specific data passed to the worker.
        priority: Event priority p0–p3 (p0 = critical).
        project: Project slug for event tagging.
        timeout: HTTP timeout in seconds.

    Returns:
        Worker response dict with at minimum {"status": "ok"|"error", ...}.
    """
    use_nemoclaw = _requires_gpu(task_type)
    base_url = NEMOCLAW_BASE_URL if use_nemoclaw else OPENCLAW_BASE_URL
    worker_name = "nemoclaw" if use_nemoclaw else "openclaw"

    request_body = {
        "task_type": task_type,
        "payload": payload,
        "tags": [
            f"type:{task_type}",
            f"priority:{priority}",
            *([ f"project:{project}"] if project else []),
        ],
    }

    logger.info("dispatch → %s task_type=%s priority=%s", worker_name, task_type, priority)

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(f"{base_url}/dispatch", json=request_body)
            response.raise_for_status()
            return response.json()
    except httpx.ConnectError:
        logger.error("%s unreachable at %s", worker_name, base_url)
        return {"status": "error", "error": f"{worker_name} unreachable", "worker": worker_name}
    except httpx.HTTPStatusError as exc:
        logger.error("%s returned %s: %s", worker_name, exc.response.status_code, exc.response.text)
        return {"status": "error", "error": str(exc), "worker": worker_name}


async def nemoclaw_backtest(
    strategy: str,
    symbol: str,
    lookback_days: int = 365,
    *,
    project: str = "sapphire",
) -> dict[str, Any]:
    """Convenience wrapper for backtesting tasks on NemoClaw.

    Routes directly to NemoClaw GPU worker regardless of other routing rules.
    """
    return await dispatch(
        "backtest",
        {"strategy": strategy, "symbol": symbol, "lookback_days": lookback_days},
        priority="p2",
        project=project,
    )


async def nemoclaw_forecast(
    symbol: str,
    horizon_hours: int = 24,
    *,
    model: str = "chronos-t5-large",
    project: str = "sapphire",
) -> dict[str, Any]:
    """Convenience wrapper for Chronos price forecasting on NemoClaw GPU."""
    return await dispatch(
        "forecast",
        {"symbol": symbol, "horizon_hours": horizon_hours, "model": model},
        priority="p1",
        project=project,
    )
