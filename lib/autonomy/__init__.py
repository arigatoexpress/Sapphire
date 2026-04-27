"""Autonomy planning surfaces for Sapphire."""

from __future__ import annotations

from typing import Any

__all__ = ["build_continuous_intelligence_plan"]


def __getattr__(name: str) -> Any:
    if name == "build_continuous_intelligence_plan":
        from .continuous_intelligence import build_continuous_intelligence_plan

        return build_continuous_intelligence_plan
    raise AttributeError(name)
