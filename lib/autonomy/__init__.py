"""Autonomy planning surfaces for Sapphire."""

from __future__ import annotations

from typing import Any

__all__ = [
    "artifact_status",
    "build_continuous_intelligence_plan",
    "lease_tasks",
    "record_task_result",
    "snapshot_tasks",
]


def __getattr__(name: str) -> Any:
    if name == "build_continuous_intelligence_plan":
        from .continuous_intelligence import build_continuous_intelligence_plan

        return build_continuous_intelligence_plan
    if name in {"artifact_status", "lease_tasks", "record_task_result", "snapshot_tasks"}:
        from .continuous_intelligence_artifacts import (
            artifact_status,
            lease_tasks,
            record_task_result,
            snapshot_tasks,
        )

        exports = {
            "artifact_status": artifact_status,
            "lease_tasks": lease_tasks,
            "record_task_result": record_task_result,
            "snapshot_tasks": snapshot_tasks,
        }
        return exports[name]
    raise AttributeError(name)
