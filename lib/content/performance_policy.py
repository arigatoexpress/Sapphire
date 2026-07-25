"""Shared policy for public performance and accuracy claims."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

MIN_PUBLIC_ACCURACY_SAMPLE = 100


def _prediction_block(data: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if not isinstance(data, Mapping):
        return {}
    preds = data.get("predictions")
    if isinstance(preds, Mapping):
        return preds
    return data


def prediction_sample_size(data: Mapping[str, Any] | None) -> int:
    preds = _prediction_block(data)
    total = preds.get("total")
    try:
        return max(0, int(total))
    except (TypeError, ValueError):
        return 0


def has_public_accuracy_track_record(data: Mapping[str, Any] | None) -> bool:
    return prediction_sample_size(data) >= MIN_PUBLIC_ACCURACY_SAMPLE


def small_sample_accuracy_notice(
    data: Mapping[str, Any] | None,
    *,
    subject: str,
    threshold: int = MIN_PUBLIC_ACCURACY_SAMPLE,
) -> str:
    total = prediction_sample_size(data)
    if total > 0:
        return (
            f"{subject} is still in track-record collection with {total} scored forecasts, "
            f"below Sapphire's {threshold}-call threshold for public accuracy claims."
        )
    return f"{subject} is still below Sapphire's {threshold}-call threshold for public accuracy claims."


def small_sample_accuracy_notice_es(
    data: Mapping[str, Any] | None,
    *,
    subject: str,
    threshold: int = MIN_PUBLIC_ACCURACY_SAMPLE,
) -> str:
    """Spanish sibling of small_sample_accuracy_notice used by ES formatters."""
    total = prediction_sample_size(data)
    if total > 0:
        return (
            f"{subject} sigue en fase de construcción de historial con {total} "
            f"predicciones evaluadas, por debajo del umbral de {threshold} señales "
            "que Sapphire exige antes de reportar precisión al público."
        )
    return (
        f"{subject} sigue por debajo del umbral de {threshold} señales que Sapphire "
        "exige antes de reportar precisión al público."
    )
