"""Lightweight bridge for optional Vertex AI client access in service modules."""

from __future__ import annotations

from typing import Any


def get_vertex_client() -> Any | None:
    """Return shared Vertex client if available, otherwise None."""
    try:
        from cloud_trader.vertex_ai_client import get_vertex_client as _get_vertex_client

        return _get_vertex_client()
    except Exception:
        return None
