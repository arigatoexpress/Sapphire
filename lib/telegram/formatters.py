"""MarkdownV2 formatters for Sapphire's Telegram surface.

Every function here returns *already-escaped* MarkdownV2 text that is
safe to hand straight to the Telegram Bot API. Callers must not re-escape
the output — that would double-escape backslashes and break rendering.

Design principles:

* Numbers are right-aligned in a fixed-width column (Telegram renders
  monospace inside backticks, so we wrap value cells in `` ` ``).
* Deltas carry a leading 🟢/🔴/⚪ emoji, an explicit sign, and two
  decimal places. Zero drifts to ⚪ to avoid false-positive coloring.
* Severity emoji follow a consistent scale:
    ✅ (ok) — 🟢 (info) — ⚠️ (warn) — 🚨 (critical)
* Section titles use ``*bold*`` MarkdownV2 with escaped punctuation.
* Table separators use box-drawing characters wrapped in ``` `` ``` for
  monospace alignment on both iOS and Android.

The formatters accept plain Python values (strings, floats, dicts).
They handle escaping internally so the caller never has to remember
which characters are MarkdownV2-reserved.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Escape helpers
# ---------------------------------------------------------------------------

_MDV2_SPECIAL = re.compile(r"([_*\[\]()~`>#+\-=|{}.!\\])")


def esc(text: object) -> str:
    """Escape a value for use in MarkdownV2 body text.

    ``None`` becomes an em-dash so partial data still renders cleanly.
    """
    if text is None:
        return "—"
    return _MDV2_SPECIAL.sub(r"\\\1", str(text))


def code(text: object) -> str:
    """Wrap ``text`` in monospace and escape the literal backticks inside.

    Telegram MarkdownV2 requires escaping ``\\`` and ``` ` ``` inside a
    ``code`` span; other MDV2 specials are ignored inside a code fence.
    """
    inner = str("" if text is None else text)
    inner = inner.replace("\\", "\\\\").replace("`", "\\`")
    return f"`{inner}`"


def bold(text: object) -> str:
    """Bold formatting — inner content must already be escaped."""
    return f"*{esc(text)}*"


# ---------------------------------------------------------------------------
# Deltas + numbers
# ---------------------------------------------------------------------------

_UP = "🟢"
_DOWN = "🔴"
_FLAT = "⚪"


def delta_arrow(value: float | None) -> str:
    if value is None:
        return _FLAT
    if value > 0.001:
        return _UP
    if value < -0.001:
        return _DOWN
    return _FLAT


def fmt_usd(value: float | int | None, *, decimals: int = 2) -> str:
    """Render a USD value as monospace with locale-neutral thousands separators."""
    if value is None:
        return code("—")
    magnitude = abs(float(value))
    if magnitude >= 1_000_000:
        text = f"${value / 1_000_000:.2f}M"
    elif magnitude >= 10_000:
        text = f"${value / 1_000:.1f}K"
    else:
        text = f"${value:,.{decimals}f}"
    return code(text)


def fmt_pct(value: float | None, *, decimals: int = 2) -> str:
    """Render a percentage with an explicit sign and severity emoji."""
    if value is None:
        return f"{_FLAT} {code('—')}"
    sign = "+" if value >= 0 else ""
    return f"{delta_arrow(value)} {code(f'{sign}{value:.{decimals}f}%')}"


def fmt_int(value: int | None) -> str:
    if value is None:
        return code("—")
    return code(f"{value:,}")


# ---------------------------------------------------------------------------
# Duration / age
# ---------------------------------------------------------------------------


def fmt_duration(seconds: float | int | None, *, missing: str = "missing") -> str:
    """Auto-scale a duration to the coarsest unit that still fits.

    Every subsystem that surfaces a "how long since …" age (freshness
    rows, staleness monitor, dispatch history) used to roll its own
    formatter — and each stopped at a different granularity. The
    `4011m` screenshot came from one that never scaled past minutes,
    turning "2d 18h" into an opaque bare-minute number.

    Rules (kept intentionally boring so agents and humans read the same
    thing):

        < 0 or None           → ``missing`` (default "missing")
        < 60 s                → ``"<Ns"``
        < 60 min              → ``"<Nm"``
        < 48 h  and mins==0   → ``"<Nh"``
        < 48 h                → ``"<Nh Nm"``
        >= 48 h and hrs==0    → ``"<Nd"``
        >= 48 h               → ``"<Nd Nh"``

    Plain string — callers wrap in ``code()`` if they want monospace.
    """
    if seconds is None:
        return missing
    try:
        total = int(seconds)
    except (TypeError, ValueError):
        return missing
    if total < 0:
        return missing
    if total < 60:
        return f"{total}s"
    if total < 3600:
        return f"{total // 60}m"
    if total < 48 * 3600:
        hours = total // 3600
        remaining_minutes = (total % 3600) // 60
        if remaining_minutes == 0:
            return f"{hours}h"
        return f"{hours}h {remaining_minutes}m"
    days = total // 86_400
    remaining_hours = (total % 86_400) // 3600
    if remaining_hours == 0:
        return f"{days}d"
    return f"{days}d {remaining_hours}h"


def fmt_age(
    delta_seconds: float | int | None, *, suffix: str = "ago", missing: str = "missing"
) -> str:
    """Render an age (like ``2d 18h ago``). Wraps ``fmt_duration`` for the
    common "N ago" case that used to be re-implemented everywhere."""
    body = fmt_duration(delta_seconds, missing=missing)
    if body == missing:
        return missing
    return f"{body} {suffix}"


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------


def kv_table(rows: Sequence[tuple[str, str]]) -> str:
    """Return a two-column key/value table as MarkdownV2.

    Values are expected to already be escaped or wrapped in ``code``.
    Keys are escaped internally.
    """
    if not rows:
        return esc("(empty)")
    return "\n".join(f"• {bold(k)}: {v}" for k, v in rows)


def _pad_right(text: str, width: int) -> str:
    return text + " " * max(0, width - len(text))


def _pad_left(text: str, width: int) -> str:
    return " " * max(0, width - len(text)) + text


def fixed_table(
    headers: Sequence[str],
    rows: Sequence[Sequence[str]],
    *,
    align: Sequence[str] | None = None,
) -> str:
    """Render a monospace table wrapped in a single ``` ``` ``` block.

    ``align`` is a sequence of ``"l"``/``"r"`` characters, one per column.
    Header cells are always uppercased. Every cell is passed through as-is —
    the caller is expected to have stripped MarkdownV2 specials (this
    lives inside a code fence, so escaping isn't needed, but stray
    backticks would still break rendering — so we strip them here).
    """
    align = list(align or ["l"] * len(headers))
    # Strip any backticks so the outer fence never closes mid-cell.
    cleaned = [[str(cell).replace("`", "'") for cell in row] for row in rows]
    cleaned_headers = [str(h).upper().replace("`", "'") for h in headers]

    widths = [
        max(len(cleaned_headers[i]), *(len(row[i]) for row in cleaned) if cleaned else [0])
        for i in range(len(cleaned_headers))
    ]

    def _row(cells: Sequence[str]) -> str:
        parts: list[str] = []
        for i, cell in enumerate(cells):
            pad = _pad_right if align[i] == "l" else _pad_left
            parts.append(pad(cell, widths[i]))
        return "  ".join(parts).rstrip()

    lines = [_row(cleaned_headers)]
    lines.append(_row(["─" * w for w in widths]))
    lines.extend(_row(row) for row in cleaned)
    return "```\n" + "\n".join(lines) + "\n```"


# ---------------------------------------------------------------------------
# Domain formatters
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PortfolioRow:
    symbol: str
    value_usd: float | None
    delta_pct: float | None = None
    venue: str = ""


def fmt_portfolio_table(
    rows: Iterable[PortfolioRow],
    *,
    total_usd: float | None = None,
    day_change_pct: float | None = None,
    updated_at: str | None = None,
) -> str:
    """Render a portfolio table with total row + last-updated stamp."""
    sorted_rows = sorted(
        list(rows),
        key=lambda r: r.value_usd or 0.0,
        reverse=True,
    )

    if not sorted_rows and total_usd is None:
        return (
            f"{bold('📊 Portfolio')}\n\n"
            f"{esc('No holdings found.')} "
            f"{esc('Check that Robinhood/OKX credentials are configured.')}"
        )

    def _delta_cell(pct: float | None) -> str:
        if pct is None:
            return f"{_FLAT}   —"
        sign = "+" if pct >= 0 else ""
        return f"{delta_arrow(pct)} {sign}{pct:5.2f}%"

    def _usd_cell(value: float | None) -> str:
        if value is None:
            return "—"
        magnitude = abs(float(value))
        if magnitude >= 1_000_000:
            return f"${value / 1_000_000:.2f}M"
        if magnitude >= 10_000:
            return f"${value / 1_000:.1f}K"
        return f"${value:,.2f}"

    table_rows = [
        [row.symbol, _usd_cell(row.value_usd), _delta_cell(row.delta_pct)] for row in sorted_rows
    ]
    table = fixed_table(
        ["Ticker", "Value", "24h"],
        table_rows,
        align=["l", "r", "r"],
    )

    header_bits = [bold("📊 Portfolio")]
    if total_usd is not None:
        arrow = delta_arrow(day_change_pct)
        change_bit = ""
        if day_change_pct is not None:
            sign = "+" if day_change_pct >= 0 else ""
            change_bit = f" · {arrow} {code(f'{sign}{day_change_pct:.2f}%')}"
        header_bits.append(f"Total: {fmt_usd(total_usd)}{change_bit}")

    footer = ""
    if updated_at:
        footer = f"\n_Updated {esc(updated_at)}_"

    return "\n".join(header_bits) + "\n\n" + table + footer


@dataclass(frozen=True)
class SignalCard:
    symbol: str
    side: str  # "long" | "short" | "flat"
    confidence_pct: float
    entry: float | None = None
    stop: float | None = None
    target: float | None = None
    strategy: str = ""
    reason: str = ""


_SEVERITY_EMOJI = {
    "critical": "🚨",
    "warn": "⚠️",
    "info": "🟢",
    "ok": "✅",
}


def _side_emoji(side: str) -> str:
    s = side.lower()
    if s == "long":
        return "🟩"
    if s == "short":
        return "🟥"
    return "⬜"


def fmt_signal_alert(signal: SignalCard, *, severity: str = "info") -> str:
    """Render a single-signal card."""
    emoji = _SEVERITY_EMOJI.get(severity, "🟢")
    side = _side_emoji(signal.side) + " " + esc(signal.side.upper())
    conf = code(f"{signal.confidence_pct:.0f}%")
    rows: list[tuple[str, str]] = [
        ("Side", side),
        ("Confidence", conf),
    ]
    if signal.entry is not None:
        rows.append(("Entry", fmt_usd(signal.entry)))
    if signal.stop is not None:
        rows.append(("Stop", fmt_usd(signal.stop)))
    if signal.target is not None:
        rows.append(("Target", fmt_usd(signal.target)))
    if signal.strategy:
        rows.append(("Strategy", code(signal.strategy)))

    title = f"{emoji} {bold('Signal')} · {code(signal.symbol)}"
    body = kv_table(rows)
    if signal.reason:
        body += "\n\n" + esc(signal.reason)
    return f"{title}\n\n{body}"


def fmt_signals_summary(
    active: int,
    win_rate_pct: float | None,
    last_scored: int | None = None,
    top_symbols: Sequence[str] = (),
) -> str:
    rows = [
        ("Active", fmt_int(active)),
        ("Win rate", fmt_pct(win_rate_pct) if win_rate_pct is not None else code("—")),
    ]
    if last_scored is not None:
        rows.append(("Scored (30d)", fmt_int(last_scored)))
    if top_symbols:
        rows.append(("Top", code(", ".join(top_symbols[:5]))))
    return f"{bold('📈 Signals')}\n\n" + kv_table(rows)


def fmt_brief_section(
    title: str,
    body: str,
    *,
    subtitle: str | None = None,
) -> str:
    """One section of a morning brief. ``body`` is expected to be escaped."""
    header = bold(title)
    if subtitle:
        header += f" · {esc(subtitle)}"
    return f"{header}\n{body}"


def fmt_brief(sections: Sequence[tuple[str, str]], *, banner: str = "📰 Morning Brief") -> str:
    """Assemble a full brief from ``(title, escaped-body)`` pairs."""
    if not sections:
        return f"{bold(banner)}\n\n{esc('No sections available.')}"
    parts = [bold(banner)]
    for title, body in sections:
        parts.append(fmt_brief_section(title, body))
    return "\n\n".join(parts)


@dataclass(frozen=True)
class ThreatCard:
    identifier: str
    severity: str  # "critical" | "high" | "medium" | "low"
    package: str = ""
    summary: str = ""
    published: str = ""


def _threat_severity_emoji(severity: str) -> str:
    s = severity.lower()
    if s == "critical":
        return "🚨"
    if s == "high":
        return "⚠️"
    if s == "medium":
        return "🟡"
    return "🟢"


def fmt_security_card(threat: ThreatCard) -> str:
    emoji = _threat_severity_emoji(threat.severity)
    rows: list[tuple[str, str]] = [
        ("Severity", code(threat.severity.upper())),
    ]
    if threat.package:
        rows.append(("Package", code(threat.package)))
    if threat.published:
        rows.append(("Published", code(threat.published)))
    header = f"{emoji} {bold('Threat')} · {code(threat.identifier)}"
    body = kv_table(rows)
    if threat.summary:
        body += "\n\n" + esc(threat.summary)
    return f"{header}\n\n{body}"


def fmt_heartbeat_line(
    *,
    agents_ok: int,
    agents_total: int,
    regime: str,
    fear_greed: int | None,
    portfolio_usd: float | None,
    kill_switch_armed: bool = False,
) -> str:
    """Single-line periodic heartbeat suitable for a pinned or 4-hour poll."""
    parts = [f"{bold('Sapphire OS')}"]
    agents_bit = f"{agents_ok}/{agents_total} agents"
    agents_bit += " ✅" if agents_ok == agents_total else " ⚠️"
    parts.append(esc(agents_bit))
    parts.append(f"Regime {code(regime.upper())}")
    if fear_greed is not None:
        parts.append(f"F&G {code(str(fear_greed))}")
    if portfolio_usd is not None:
        parts.append(f"Portfolio {fmt_usd(portfolio_usd, decimals=0)}")
    if kill_switch_armed:
        parts.append(esc("🛑 KILL SWITCH"))
    return " · ".join(parts)


def fmt_status_snapshot(
    *,
    services: Sequence[tuple[str, str]],
    freshness: Sequence[tuple[str, str]],
    regime: str,
    fear_greed: int | None,
    kill_switch_armed: bool = False,
) -> str:
    """Full ``/status`` output — services, data freshness, regime."""
    service_rows = [(name, esc(state)) for name, state in services]
    freshness_rows = [(label, esc(delta)) for label, delta in freshness]

    kill_row: list[tuple[str, str]] = []
    if kill_switch_armed:
        kill_row = [("🛑", bold("KILL SWITCH ARMED"))]

    regime_bit = code(regime.upper())
    fg_bit = code(str(fear_greed)) if fear_greed is not None else code("—")

    return "\n\n".join(
        [
            bold("🔄 System Status"),
            kv_table(
                kill_row
                + [
                    ("Regime", regime_bit),
                    ("Fear & Greed", fg_bit),
                ]
            ),
            f"{bold('Services')}\n" + kv_table(service_rows),
            f"{bold('Data Freshness')}\n" + kv_table(freshness_rows),
        ]
    )


def fmt_settings(
    *,
    heartbeat_enabled: bool,
    heartbeat_hours: int,
    live_notifications: bool,
    kill_switch_armed: bool,
) -> str:
    hb_state = "ENABLED" if heartbeat_enabled else "DISABLED"
    hb_interval = {
        4: "every 4h",
        12: "every 12h",
        24: "daily",
    }.get(heartbeat_hours, f"every {heartbeat_hours}h")
    live_state = "LIVE SEND" if live_notifications else "DRAFT ONLY"
    kill_state = "ARMED 🛑" if kill_switch_armed else "OFF"

    rows = [
        ("Heartbeat", code(f"{hb_state} · {hb_interval}")),
        ("Notifications", code(live_state)),
        ("Kill switch", code(kill_state)),
    ]
    return f"{bold('⚙️ Settings')}\n\n" + kv_table(rows)


def fmt_reports_list(
    reports: Sequence[tuple[str, str, str]],
) -> str:
    """`reports` = sequence of (kind, title, mtime_iso)."""
    if not reports:
        return f"{bold('📋 Reports')}\n\n{esc('No drafts or ready reports queued.')}"
    rows = [[kind, title[:32], mtime[:16]] for kind, title, mtime in reports]
    table = fixed_table(
        ["Kind", "Title", "Updated"],
        rows,
        align=["l", "l", "l"],
    )
    return f"{bold('📋 Reports')}\n\n" + table


__all__ = [
    "PortfolioRow",
    "SignalCard",
    "ThreatCard",
    "bold",
    "code",
    "delta_arrow",
    "esc",
    "fixed_table",
    "fmt_age",
    "fmt_brief",
    "fmt_brief_section",
    "fmt_duration",
    "fmt_heartbeat_line",
    "fmt_int",
    "fmt_pct",
    "fmt_portfolio_table",
    "fmt_reports_list",
    "fmt_security_card",
    "fmt_settings",
    "fmt_signal_alert",
    "fmt_signals_summary",
    "fmt_status_snapshot",
    "fmt_usd",
    "kv_table",
]
