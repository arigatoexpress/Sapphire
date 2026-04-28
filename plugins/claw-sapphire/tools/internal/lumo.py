#!/usr/bin/env python3
"""Sapphire Lumo AI Research Pack — Strategy review and operator briefings.

Fetches live data from the Sapphire platform APIs and formats it as a
structured research pack suitable for deep strategy analysis via Kimi/Claude
or as a standalone operator briefing.

Actions:
    pack      — Generate full Lumo research pack (strategy ops + intel + librarian)
    briefing  — Operator brief only (KPIs, blockers, top actions) — faster
    intel     — Intelligence highlights only (last N hours)
    lanes     — Top strategy lanes ranked by EV

Usage:
    echo '{"action":"pack"}' | python3 lumo.py
    echo '{"action":"briefing","days":14}' | python3 lumo.py
    echo '{"action":"intel","hours":48}' | python3 lumo.py
    echo '{"action":"pack","base_url":"https://sapphirealpha.xyz","days":7}' | python3 lumo.py
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

SAPPHIRE_DIR = Path.home() / "Code" / "Sapphire"
DATA_DIR = SAPPHIRE_DIR / "data" / "lumo"
DEFAULT_BASE_URL = "https://sapphirealpha.xyz"
DEFAULT_DAYS = 7
DEFAULT_HOURS = 24
DEFAULT_LIB_LIMIT = 8

TIMEOUT = 20.0


# ── HTTP helpers ──────────────────────────────────────────────────────────────


def _get_json(url: str, timeout: float = TIMEOUT) -> dict:
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
            return data if isinstance(data, dict) else {}
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}", "url": url}
    except Exception as e:
        return {"error": str(e)[:120], "url": url}


def _fmt(value, digits: int = 2) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except Exception:
        return "0.00"


# ── Fetch functions ───────────────────────────────────────────────────────────


def _fetch_all(base: str, days: int, hours: int, lib_limit: int) -> tuple[dict, dict, dict]:
    base = base.rstrip("/")
    strategy_ops = _get_json(
        f"{base}/api/platform/strategy-ops?days={max(1, min(days, 30))}&refresh=true"
    )
    intel_summary = _get_json(
        f"{base}/api/platform/intel-summary?hours={max(4, min(hours, 168))}&limit=60"
    )
    librarian = _get_json(
        f"{base}/api/platform/librarian-context"
        f"?hours={max(4, min(hours, 168))}&limit={max(3, min(lib_limit, 24))}"
    )
    return strategy_ops, intel_summary, librarian


# ── Formatters ────────────────────────────────────────────────────────────────


def _fmt_briefing(brief: dict, kpis: dict, blockers: list, actions: list) -> list[str]:
    lines = [
        "## Operator Snapshot",
        "",
        f"- Decision: **{brief.get('label', 'NO-GO')}**",
        f"- Net PnL (after fees): **${_fmt(kpis.get('net_pnl_after_fees_usd'), 4)}**",
        f"- Fill rate: **{_fmt(kpis.get('fill_rate_pct'), 1)}%**",
        f"- Reject tax: **{_fmt(kpis.get('reject_tax_pct'), 1)}%**",
        f"- Max drawdown: **{_fmt(kpis.get('max_drawdown_pct'), 2)}%**",
        f"- EV error: **{_fmt(kpis.get('expected_value_error_pct'), 3)}%**",
        "",
        "## Hard Blockers",
        "",
    ]
    for row in blockers[:8] or ["None"]:
        lines.append(f"- {row}")
    lines += ["", "## Top Actions", ""]
    if actions:
        for row in actions[:5]:
            priority = str(row.get("priority", "P1")).upper()
            title = str(row.get("title", "Action")).strip()
            why = str(row.get("why", "")).strip()
            action = str(row.get("action", "")).strip()
            lines.append(f"- **[{priority}] {title}**")
            if why:
                lines.append(f"  - Why: {why}")
            if action:
                lines.append(f"  - Do: {action}")
    else:
        lines.append("- Maintain capped live posture; collect more labeled outcomes.")
    return lines


def _fmt_lanes(lanes: list) -> list[str]:
    lines = ["## Top Lanes (Current)", ""]
    if lanes:
        for row in lanes:
            lane = f"{row.get('strategy', 'unknown')}@{row.get('timeframe', 'unknown')}"
            lines.append(
                f"- `{lane}` | EV adj `{_fmt(row.get('ev_adjusted_pct'), 3)}%` | "
                f"fill `{_fmt(row.get('filled_success_pct'), 1)}%` | "
                f"reject `{_fmt(row.get('reject_tax_pct'), 1)}%` | "
                f"PnL `${_fmt(row.get('net_pnl_after_fees_usd'), 4)}`"
            )
    else:
        lines.append("- No lane data available.")
    return lines


def _fmt_intel(intel: list) -> list[str]:
    lines = ["## Intelligence Highlights", ""]
    if intel:
        for item in intel[:5]:
            title = str(item.get("title", "Intel item")).strip()
            source = str(item.get("source", "intel")).upper()
            category = str(item.get("category", "market")).upper()
            lines.append(f"- **[{category}/{source}]** {title}")
    else:
        lines.append("- No intel highlights available.")
    return lines


def _fmt_librarian(lib: list) -> list[str]:
    lines = ["## Librarian Context Blocks", ""]
    if lib:
        for item in lib[:6]:
            title = str(item.get("title", "Context block")).strip()
            summary = str(item.get("summary", "")).strip()
            lines.append(f"- **{title}** — {summary}")
    else:
        lines.append("- No curated context blocks available.")
    return lines


def _fmt_prompt(
    brief: dict, kpis: dict, blockers: list, actions: list, lanes: list, intel: list, lib: list
) -> list[str]:
    return [
        "## Prompt For Deep Analysis",
        "",
        "```text",
        "You are an institutional crypto perp strategy reviewer.",
        "Use only the data below. Do not invent data.",
        "Task:",
        "1) Provide GO/NO-GO with explicit numeric rationale.",
        "2) Identify top 3 changes to reduce reject tax and improve fill rate.",
        "3) Propose a 7-day experimental plan (paper -> capped live) with acceptance thresholds.",
        "4) Output expected impact table (metric, baseline, target, confidence, risk).",
        "",
        "Data:",
        json.dumps(
            {
                "operator_brief": brief,
                "kpis": kpis,
                "hard_blockers": blockers[:8],
                "top_actions": actions[:5],
                "top_lanes": lanes,
                "intel_highlights": intel[:5],
                "librarian_blocks": lib,
            },
            indent=2,
            default=str,
        ),
        "```",
    ]


# ── Action handlers ───────────────────────────────────────────────────────────


def _action_pack(inp: dict) -> dict:
    base = inp.get("base_url", DEFAULT_BASE_URL)
    days = int(inp.get("days", DEFAULT_DAYS))
    hours = int(inp.get("hours", DEFAULT_HOURS))
    lib_limit = int(inp.get("librarian_limit", DEFAULT_LIB_LIMIT))

    strategy_ops, intel_summary, librarian = _fetch_all(base, days, hours, lib_limit)

    brief = (
        (strategy_ops.get("operator_brief") or {})
        if isinstance(strategy_ops.get("operator_brief"), dict)
        else {}
    )
    kpis = brief.get("kpis") or {}
    blockers = brief.get("hard_blockers") or []
    actions = brief.get("top_actions") or []
    lanes = ((strategy_ops.get("scorecard") or {}).get("ranked") or [])[:5]
    intel = (intel_summary.get("intel") or {}).get("top_items") or []
    lib = (librarian.get("selected") or [])[:6]

    now_iso = datetime.now(UTC).isoformat()
    lines = [
        "# Lumo Research Pack",
        "",
        f"- Generated (UTC): `{now_iso}`",
        f"- Source: `{base}`",
        "",
    ]
    lines += _fmt_briefing(brief, kpis, blockers, actions)
    lines += [""]
    lines += _fmt_lanes(lanes)
    lines += [""]
    lines += _fmt_intel(intel)
    lines += [""]
    lines += _fmt_librarian(lib)
    lines += [""]
    lines += _fmt_prompt(brief, kpis, blockers, actions, lanes, intel, lib)
    lines += [""]

    content = "\n".join(lines)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_path = DATA_DIR / f"lumo_pack_{ts}.md"
    out_path.write_text(content)

    return {
        "action": "pack",
        "path": str(out_path),
        "decision": brief.get("label", "NO-GO"),
        "net_pnl_usd": kpis.get("net_pnl_after_fees_usd"),
        "fill_rate_pct": kpis.get("fill_rate_pct"),
        "reject_tax_pct": kpis.get("reject_tax_pct"),
        "top_lanes": len(lanes),
        "intel_items": len(intel),
        "blockers": len(blockers),
        "timestamp": now_iso,
        "errors": [
            v.get("error")
            for v in [strategy_ops, intel_summary, librarian]
            if isinstance(v, dict) and "error" in v
        ],
    }


def _action_briefing(inp: dict) -> dict:
    base = inp.get("base_url", DEFAULT_BASE_URL)
    days = int(inp.get("days", DEFAULT_DAYS))

    strategy_ops = _get_json(
        f"{base.rstrip('/')}/api/platform/strategy-ops"
        f"?days={max(1, min(days, 30))}&refresh=true"
    )

    brief = (
        (strategy_ops.get("operator_brief") or {})
        if isinstance(strategy_ops.get("operator_brief"), dict)
        else {}
    )
    kpis = brief.get("kpis") or {}
    blockers = brief.get("hard_blockers") or []
    actions = brief.get("top_actions") or []

    return {
        "action": "briefing",
        "decision": brief.get("label", "NO-GO"),
        "kpis": {
            "net_pnl_usd": kpis.get("net_pnl_after_fees_usd"),
            "fill_rate_pct": kpis.get("fill_rate_pct"),
            "reject_tax_pct": kpis.get("reject_tax_pct"),
            "max_drawdown_pct": kpis.get("max_drawdown_pct"),
            "ev_error_pct": kpis.get("expected_value_error_pct"),
        },
        "blockers": blockers[:8],
        "top_actions": [
            {
                "priority": a.get("priority", "P1"),
                "title": a.get("title", ""),
                "action": a.get("action", ""),
            }
            for a in (actions[:5] or [])
        ],
        "timestamp": datetime.now(UTC).isoformat(),
        "error": strategy_ops.get("error"),
    }


def _action_intel(inp: dict) -> dict:
    base = inp.get("base_url", DEFAULT_BASE_URL)
    hours = int(inp.get("hours", DEFAULT_HOURS))

    intel_summary = _get_json(
        f"{base.rstrip('/')}/api/platform/intel-summary"
        f"?hours={max(4, min(hours, 168))}&limit=60"
    )
    intel = (intel_summary.get("intel") or {}).get("top_items") or []

    return {
        "action": "intel",
        "items": [
            {
                "title": i.get("title", ""),
                "source": i.get("source", ""),
                "category": i.get("category", ""),
            }
            for i in intel[:10]
        ],
        "count": len(intel),
        "timestamp": datetime.now(UTC).isoformat(),
        "error": intel_summary.get("error"),
    }


def _action_lanes(inp: dict) -> dict:
    base = inp.get("base_url", DEFAULT_BASE_URL)
    days = int(inp.get("days", DEFAULT_DAYS))

    strategy_ops = _get_json(
        f"{base.rstrip('/')}/api/platform/strategy-ops"
        f"?days={max(1, min(days, 30))}&refresh=true"
    )
    lanes = ((strategy_ops.get("scorecard") or {}).get("ranked") or [])[:10]

    return {
        "action": "lanes",
        "lanes": [
            {
                "strategy": r.get("strategy", ""),
                "timeframe": r.get("timeframe", ""),
                "ev_adjusted_pct": r.get("ev_adjusted_pct"),
                "fill_rate_pct": r.get("filled_success_pct"),
                "reject_tax_pct": r.get("reject_tax_pct"),
                "net_pnl_usd": r.get("net_pnl_after_fees_usd"),
            }
            for r in lanes
        ],
        "timestamp": datetime.now(UTC).isoformat(),
        "error": strategy_ops.get("error"),
    }


# ── Main ──────────────────────────────────────────────────────────────────────


def main():
    try:
        inp = json.loads(sys.stdin.read().strip() or "{}")
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"Invalid JSON: {e}"}))
        sys.exit(1)

    action = inp.get("action", "briefing")

    handlers = {
        "pack": _action_pack,
        "briefing": _action_briefing,
        "intel": _action_intel,
        "lanes": _action_lanes,
    }
    fn = handlers.get(action)
    if fn is None:
        print(
            json.dumps(
                {
                    "error": f"Unknown action: {action!r}",
                    "valid_actions": list(handlers),
                }
            )
        )
        sys.exit(1)

    result = fn(inp)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
