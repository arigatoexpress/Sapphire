#!/usr/bin/env python3
"""
Build a compact, copy/paste-ready research pack for Proton Lumo.

This script does not send anything to third-party services; it only fetches
local platform APIs and writes a markdown artifact for manual use.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests


def _get_json(url: str, timeout: float = 20.0) -> dict[str, Any]:
    try:
        resp = requests.get(url, timeout=timeout, headers={"Accept": "application/json"})
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        return {"error": str(exc), "url": url}


def _fmt_num(value: Any, digits: int = 2) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except Exception:
        return "0.00"


def _build_markdown(base_url: str, strategy_ops: dict[str, Any], intel_summary: dict[str, Any], librarian: dict[str, Any]) -> str:
    now_iso = datetime.now(UTC).isoformat()
    brief = strategy_ops.get("operator_brief", {}) if isinstance(strategy_ops.get("operator_brief"), dict) else {}
    kpis = brief.get("kpis", {}) if isinstance(brief.get("kpis"), dict) else {}
    blockers = brief.get("hard_blockers", []) if isinstance(brief.get("hard_blockers"), list) else []
    actions = brief.get("top_actions", []) if isinstance(brief.get("top_actions"), list) else []
    lanes = ((strategy_ops.get("scorecard") or {}).get("ranked") or [])[:5]
    intel = (intel_summary.get("intel") or {}).get("top_items") or []
    lib = (librarian.get("selected") or [])[:6]

    lines: list[str] = []
    lines.append("# Lumo Research Pack")
    lines.append("")
    lines.append(f"- Generated (UTC): `{now_iso}`")
    lines.append(f"- Source: `{base_url}`")
    lines.append("")
    lines.append("## Operator Snapshot")
    lines.append("")
    lines.append(f"- Decision: **{brief.get('label', 'NO-GO')}**")
    lines.append(f"- Net PnL (after fees): **${_fmt_num(kpis.get('net_pnl_after_fees_usd'), 4)}**")
    lines.append(f"- Fill rate: **{_fmt_num(kpis.get('fill_rate_pct'), 1)}%**")
    lines.append(f"- Reject tax: **{_fmt_num(kpis.get('reject_tax_pct'), 1)}%**")
    lines.append(f"- Max drawdown: **{_fmt_num(kpis.get('max_drawdown_pct'), 2)}%**")
    lines.append(f"- EV error: **{_fmt_num(kpis.get('expected_value_error_pct'), 3)}%**")
    lines.append("")
    lines.append("## Hard Blockers")
    lines.append("")
    if blockers:
        for row in blockers[:8]:
            lines.append(f"- {row}")
    else:
        lines.append("- None")
    lines.append("")
    lines.append("## Top Actions")
    lines.append("")
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
    lines.append("")
    lines.append("## Top Lanes (Current)")
    lines.append("")
    if lanes:
        for row in lanes:
            lane = f"{row.get('strategy', 'unknown')}@{row.get('timeframe', 'unknown')}"
            lines.append(
                f"- `{lane}` | EV adj `{_fmt_num(row.get('ev_adjusted_pct'), 3)}%` | "
                f"fill `{_fmt_num(row.get('filled_success_pct'), 1)}%` | "
                f"reject `{_fmt_num(row.get('reject_tax_pct'), 1)}%` | "
                f"PnL after fees `${_fmt_num(row.get('net_pnl_after_fees_usd'), 4)}`"
            )
    else:
        lines.append("- No lane data available.")
    lines.append("")
    lines.append("## Intelligence Highlights")
    lines.append("")
    if intel:
        for item in intel[:5]:
            title = str(item.get("title", "Intel item")).strip()
            source = str(item.get("source", "intel")).upper()
            category = str(item.get("category", "market")).upper()
            lines.append(f"- **[{category}/{source}]** {title}")
    else:
        lines.append("- No intel highlights available.")
    lines.append("")
    lines.append("## Librarian Context Blocks")
    lines.append("")
    if lib:
        for item in lib:
            title = str(item.get("title", "Context block")).strip()
            summary = str(item.get("summary", "")).strip()
            lines.append(f"- **{title}** — {summary}")
    else:
        lines.append("- No curated context blocks available.")
    lines.append("")
    lines.append("## Prompt For Lumo")
    lines.append("")
    lines.append("```text")
    lines.append("You are an institutional crypto perp strategy reviewer.")
    lines.append("Use only the data below. Do not invent data.")
    lines.append("Task:")
    lines.append("1) Provide GO/NO-GO with explicit numeric rationale.")
    lines.append("2) Identify top 3 changes to reduce reject tax and improve fill rate.")
    lines.append("3) Propose a 7-day experimental plan (paper -> capped live) with acceptance thresholds.")
    lines.append("4) Output expected impact table (metric, baseline, target, confidence, risk).")
    lines.append("")
    lines.append("Data:")
    lines.append(json.dumps(
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
    ))
    lines.append("```")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Lumo AI research pack from Sapphire APIs.")
    parser.add_argument("--base-url", default="https://sapphirealpha.xyz", help="Platform base URL")
    parser.add_argument("--days", type=int, default=7, help="Window days for strategy ops")
    parser.add_argument("--hours", type=int, default=24, help="Window hours for intel/librarian context")
    parser.add_argument("--librarian-limit", type=int, default=8, help="Librarian context limit")
    parser.add_argument("--out", default="", help="Output markdown path")
    args = parser.parse_args()

    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    default_out = Path("/Users/aribs/Sapphire/output/lumo") / f"lumo_research_pack_{ts}.md"
    out_path = Path(args.out).expanduser() if args.out else default_out
    out_path.parent.mkdir(parents=True, exist_ok=True)

    base = args.base_url.rstrip("/")
    strategy_ops = _get_json(f"{base}/api/platform/strategy-ops?days={max(1, min(args.days, 30))}&refresh=true")
    intel_summary = _get_json(f"{base}/api/platform/intel-summary?hours={max(4, min(args.hours, 168))}&limit=60")
    librarian = _get_json(
        f"{base}/api/platform/librarian-context?hours={max(4, min(args.hours, 168))}&limit={max(3, min(args.librarian_limit, 24))}"
    )

    content = _build_markdown(base, strategy_ops, intel_summary, librarian)
    out_path.write_text(content)
    print(str(out_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
