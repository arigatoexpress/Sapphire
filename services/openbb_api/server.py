"""Sapphire compatibility wrapper for the local OpenBB REST API."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from openbb_core.api.dependency.coverage import get_command_map
from openbb_core.api.rest_api import app
from openbb_core.app.router import CommandMap


@app.get("/api/v1/openbb/providers")
async def list_openbb_providers(
    command_map: Annotated[CommandMap, Depends(get_command_map)],
) -> list[str]:
    """Return configured OpenBB provider names for Sapphire health checks."""
    return sorted(command_map.provider_coverage)
