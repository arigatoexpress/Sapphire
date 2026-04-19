"""Content engine visualizations — generates ASCII charts for reports.

Produces plain-text sparklines and tables from Sapphire's prediction and
portfolio data.  No matplotlib/plotly dependencies — output is safe to embed
in Telegram messages, Substack HTML, and Markdown reports.
"""

from __future__ import annotations

from typing import Any

_SPARKLINE = " ▁▂▃▄▅▆▇█"


def sparkline(values: list[float]) -> str:
    """Return a Unicode sparkline for a series of floats."""
    if not values:
        return ""
    mn, mx = min(values), max(values)
    rng = mx - mn or 1
    bars = [_SPARKLINE[round((v - mn) / rng * (len(_SPARKLINE) - 1))] for v in values]
    return "".join(bars)


def accuracy_table(by_symbol: dict[str, dict]) -> str:
    """Return a fixed-width accuracy breakdown table."""
    lines = ["Symbol  | Hits | Total | Accuracy", "--------|------|-------|----------"]
    for sym, v in sorted(by_symbol.items()):
        acc = v.get("accuracy", 0) * 100
        lines.append(f"{sym:<8}| {v.get('hits', 0):<5}| {v.get('total', 0):<6}| {acc:.1f}%")
    return "\n".join(lines)


def portfolio_bar(capital: float, initial: float = 100_000.0) -> str:
    """Return a compact ASCII progress bar showing portfolio growth."""
    pct = (capital - initial) / initial * 100
    sign = "+" if pct >= 0 else ""
    bar_len = 10
    filled = min(bar_len, max(0, round(abs(pct) / 5)))
    bar = ("█" * filled).ljust(bar_len)
    return f"[{bar}] {sign}{pct:.2f}%"


def prediction_spark(predictions: list[dict]) -> str:
    """Sparkline of recent prediction outcomes (1=correct, 0=incorrect)."""
    scores = [1.0 if p.get("correct") else 0.0 for p in predictions[-20:]]
    return sparkline(scores) if scores else "(no data)"


def format_market_summary(facts: dict[str, Any]) -> str:
    """Compact multi-line market summary for Telegram/Substack."""
    lines = []
    preds = facts.get("predictions", {})
    port = facts.get("portfolio", {})
    forecasts = facts.get("latest_forecasts", [])

    if forecasts:
        lines.append("**Forecasts:**")
        for fc in forecasts[:5]:
            sym = fc.get("symbol", "?")
            d = fc.get("direction", "?")
            tp = fc.get("target_price")
            tp_str = f" → ${tp}" if tp else ""
            lines.append(f"  {sym}: {d}{tp_str}")

    if preds:
        acc = preds.get("accuracy", 0) * 100
        lines.append(
            f"**Model:** {preds.get('hits', 0)}/{preds.get('total', 0)} correct ({acc:.1f}%)"
        )

    if port:
        cap = port.get("capital", 0)
        pnl = port.get("pnl_pct", 0)
        lines.append(f"**Paper:** ${cap:,.0f} ({pnl:+.2f}%) {portfolio_bar(cap)}")

    return "\n".join(lines) if lines else "(no data)"
