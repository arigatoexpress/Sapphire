"""PDF rendering for research notes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

from lib.core.provenance import write_envelope_sidecar
from lib.research_notes.model import ResearchNote
from lib.research_notes.visualizations import render_drawdown_chart, render_equity_chart

GENERATOR = "lib.research_notes.render"
PAGE_W, PAGE_H = letter


BODY = ParagraphStyle(
    "body",
    fontName="Helvetica",
    fontSize=9,
    leading=12,
    textColor=colors.HexColor("#1F2937"),
)
BOLD = ParagraphStyle(
    "bold",
    parent=BODY,
    fontName="Helvetica-Bold",
)


def _draw_wrapped(c: canvas.Canvas, text: str, x: float, y: float, width: float) -> float:
    paragraph = Paragraph(text, BODY)
    _, height = paragraph.wrap(width, 720)
    paragraph.drawOn(c, x, y - height)
    return y - height - 8


def _section(c: canvas.Canvas, label: str, x: float, y: float) -> float:
    c.setFillColor(colors.HexColor("#111827"))
    c.setFont("Helvetica-Bold", 10)
    c.drawString(x, y, label)
    return y - 16


def _kv(c: canvas.Canvas, label: str, value: Any, x: float, y: float) -> float:
    c.setFont("Helvetica-Bold", 8)
    c.setFillColor(colors.HexColor("#374151"))
    c.drawString(x, y, label)
    c.setFont("Helvetica", 9)
    c.drawString(x, y - 12, "n/a" if value is None else str(value))
    return y - 32


def render_pdf(
    note: ResearchNote,
    output_path: Path,
    *,
    timeseries: dict[str, Any] | None = None,
    source_paths: tuple[str | Path, ...] = (),
) -> Path:
    """Render a deterministic-ish PDF and write a provenance sidecar."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    chart_dir = output_path.parent / "_charts"
    chart = render_equity_chart(timeseries or {}, chart_dir / "equity_curve.png")
    drawdown_chart = render_drawdown_chart(timeseries or {}, chart_dir / "drawdown.png")

    c = canvas.Canvas(str(output_path), pagesize=letter, invariant=1)
    c.setTitle(note.title)
    c.setAuthor("Sapphire OS")
    c.setSubject("Research-only strategy note")

    x = 54
    y = PAGE_H - 52
    c.setFillColor(colors.HexColor("#0F172A"))
    c.setFont("Helvetica-Bold", 18)
    c.drawString(x, y, note.title)
    y -= 18
    c.setFont("Helvetica", 9)
    c.setFillColor(colors.HexColor("#475569"))
    c.drawString(x, y, note.subtitle)
    y -= 26

    c.setFillColor(colors.HexColor("#EFF6FF"))
    c.rect(x, y - 64, PAGE_W - 108, 64, fill=1, stroke=0)
    metric_x = x + 12
    metric_y = y - 16
    for label, key in (
        ("Rank metric", "rank_metric_value"),
        ("Return", "total_return_pct"),
        ("Win rate", "win_rate"),
        ("Trades", "trade_count"),
        ("Drawdown", "max_drawdown_pct"),
    ):
        _kv(c, label, note.key_metrics.get(key), metric_x, metric_y)
        metric_x += 95
    y -= 86

    y = _section(c, "Thesis", x, y)
    y = _draw_wrapped(c, note.thesis, x, y, PAGE_W - 108)
    y = _section(c, "Counter-Thesis", x, y)
    y = _draw_wrapped(c, note.counter_thesis, x, y, PAGE_W - 108)
    y = _section(c, "Evidence", x, y)
    for item in note.evidence:
        y = _draw_wrapped(c, f"- {item}", x + 10, y, PAGE_W - 118)
    y -= 2

    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(colors.HexColor("#111827"))
    c.drawString(x, y, "Equity Context")
    y -= 154
    chart_path = Path(chart["path"])
    if chart_path.suffix.lower() in {".png", ".jpg", ".jpeg"}:
        c.drawImage(str(chart_path), x, y, width=420, height=140, preserveAspectRatio=True)
    else:
        c.setFont("Helvetica", 8)
        c.setFillColor(colors.HexColor("#475569"))
        c.drawString(x, y + 120, f"Chart renderer: {chart['renderer']}")
        c.rect(x, y, 420, 130, stroke=1, fill=0)
    y -= 22

    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(colors.HexColor("#111827"))
    c.drawString(x, y, "Drawdown Context")
    y -= 98
    if Path(drawdown_chart["path"]).suffix.lower() in {".png", ".jpg", ".jpeg"}:
        c.drawImage(
            str(drawdown_chart["path"]), x, y, width=420, height=84, preserveAspectRatio=True
        )
    else:
        c.setFont("Helvetica", 8)
        c.setFillColor(colors.HexColor("#475569"))
        c.drawString(x, y + 72, f"Chart renderer: {drawdown_chart['renderer']}")
        c.rect(x, y, 420, 78, stroke=1, fill=0)
    y -= 24

    if y < 190:
        c.showPage()
        y = PAGE_H - 52

    y = _section(c, "Invalidators", x, y)
    for item in note.invalidators:
        y = _draw_wrapped(c, f"- {item}", x + 10, y, PAGE_W - 118)
    y = _section(c, "Next Steps", x, y)
    for item in note.next_steps:
        y = _draw_wrapped(c, f"- {item}", x + 10, y, PAGE_W - 118)
    y = _section(c, "Safety Caveat", x, y)
    _draw_wrapped(c, note.caveat, x, y, PAGE_W - 108)

    c.setFont("Helvetica", 7)
    c.setFillColor(colors.HexColor("#64748B"))
    c.drawString(x, 28, f"Generated {note.generated_at} | note_id={note.note_id}")
    c.drawRightString(PAGE_W - x, 28, "Sapphire Research Notes 0.1.0")
    c.save()

    write_envelope_sidecar(
        output_path,
        generator=GENERATOR,
        source_paths=source_paths,
        metadata={
            "note_id": note.note_id,
            "strategy_slug": note.strategy_slug,
            "chart_renderer": chart["renderer"],
            "drawdown_chart_renderer": drawdown_chart["renderer"],
        },
    )
    return output_path
