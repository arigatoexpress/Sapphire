"""Deterministic chart rendering for research notes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.pdfgen import canvas

WIDTH = 420
HEIGHT = 180


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _equity_points(timeseries: dict[str, Any]) -> list[float]:
    curve = timeseries.get("equity_curve") or []
    points = [_float(row.get("equity_usd")) for row in curve if isinstance(row, dict)]
    if points:
        return points
    initial = _float(timeseries.get("initial_capital"), 100_000.0)
    final = _float(timeseries.get("final_equity"), initial)
    return [initial, final]


def _drawdown_points(timeseries: dict[str, Any]) -> list[float]:
    series = timeseries.get("drawdown_series") or []
    points = [_float(row.get("dd_pct")) for row in series if isinstance(row, dict)]
    if points:
        return points
    max_dd = timeseries.get("max_drawdown") or {}
    return [0.0, _float(max_dd.get("pct")), 0.0]


def _draw_vector_chart(path: Path, title: str, points: list[float]) -> None:
    """Fallback chart path when matplotlib is unavailable."""
    path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(path), pagesize=(WIDTH, HEIGHT), invariant=1)
    c.setTitle(title)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(24, HEIGHT - 28, title)
    left, bottom, right, top = 36, 34, WIDTH - 20, HEIGHT - 48
    c.setStrokeColor(colors.HexColor("#C7CDD8"))
    c.line(left, bottom, right, bottom)
    c.line(left, bottom, left, top)
    low = min(points)
    high = max(points)
    span = high - low or 1.0
    if len(points) == 1:
        xy = [(left, bottom + (points[0] - low) / span * (top - bottom))]
    else:
        xy = [
            (
                left + idx / (len(points) - 1) * (right - left),
                bottom + (value - low) / span * (top - bottom),
            )
            for idx, value in enumerate(points)
        ]
    c.setStrokeColor(colors.HexColor("#2F6FDE"))
    c.setLineWidth(1.8)
    for start, end in zip(xy, xy[1:], strict=False):
        c.line(start[0], start[1], end[0], end[1])
    c.setFillColor(colors.HexColor("#1E293B"))
    c.setFont("Helvetica", 8)
    c.drawString(left, 14, f"min ${low:,.0f}")
    c.drawRightString(right, 14, f"max ${high:,.0f}")
    c.save()


def render_equity_chart(timeseries: dict[str, Any], path: Path) -> dict[str, Any]:
    """Render an equity curve chart.

    Uses matplotlib's Agg backend when installed. The ReportLab vector fallback
    keeps local tests deterministic on machines without matplotlib.
    """
    points = _equity_points(timeseries)
    try:
        import matplotlib

        matplotlib.use("Agg", force=True)
        import matplotlib.pyplot as plt

        plt.rcParams.update(
            {
                "font.family": "DejaVu Sans",
                "figure.dpi": 144,
                "savefig.dpi": 144,
                "axes.unicode_minus": False,
            }
        )
        fig, ax = plt.subplots(figsize=(4.2, 1.8), layout="constrained")
        ax.plot(range(len(points)), points, color="#2F6FDE", linewidth=1.8)
        ax.set_title("Equity Curve", fontsize=9)
        ax.set_xlabel("Closed trade", fontsize=7)
        ax.set_ylabel("Equity USD", fontsize=7)
        ax.grid(True, color="#E5E7EB", linewidth=0.6)
        ax.tick_params(labelsize=6)
        path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(path, metadata={"Software": "Sapphire Research Notes 0.1.0"})
        plt.close(fig)
        renderer = "matplotlib"
    except Exception:  # noqa: BLE001 - fallback is intentional and deterministic.
        fallback = path.with_suffix(".chart.pdf")
        _draw_vector_chart(fallback, "Equity Curve", points)
        path = fallback
        renderer = "reportlab-vector-fallback"
    return {
        "kind": "equity_curve",
        "path": str(path),
        "renderer": renderer,
        "point_count": len(points),
        "data_hash_material": json.dumps(points, sort_keys=True),
    }


def render_drawdown_chart(timeseries: dict[str, Any], path: Path) -> dict[str, Any]:
    """Render a drawdown chart with the same deterministic backend policy."""
    points = _drawdown_points(timeseries)
    try:
        import matplotlib

        matplotlib.use("Agg", force=True)
        import matplotlib.pyplot as plt

        plt.rcParams.update(
            {
                "font.family": "DejaVu Sans",
                "figure.dpi": 144,
                "savefig.dpi": 144,
                "axes.unicode_minus": False,
            }
        )
        fig, ax = plt.subplots(figsize=(4.2, 0.9), layout="constrained")
        ax.fill_between(range(len(points)), points, 0, color="#FCA5A5", alpha=0.7)
        ax.plot(range(len(points)), points, color="#B91C1C", linewidth=1.1)
        ax.set_title("Drawdown", fontsize=8)
        ax.grid(True, color="#E5E7EB", linewidth=0.5)
        ax.tick_params(labelsize=6)
        path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(path, metadata={"Software": "Sapphire Research Notes 0.1.0"})
        plt.close(fig)
        renderer = "matplotlib"
    except Exception:  # noqa: BLE001
        fallback = path.with_suffix(".chart.pdf")
        _draw_vector_chart(fallback, "Drawdown", points)
        path = fallback
        renderer = "reportlab-vector-fallback"
    return {
        "kind": "drawdown",
        "path": str(path),
        "renderer": renderer,
        "point_count": len(points),
        "data_hash_material": json.dumps(points, sort_keys=True),
    }
