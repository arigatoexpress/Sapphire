#!/usr/bin/env python3
"""
Build a verification report for Lighter trading progress from Firestore.

Outputs:
  - summary.json
  - equity_timeline.png
  - execution_outcomes.png
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _as_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def _classify_execution(row: dict[str, Any]) -> str:
    outcome = str(row.get("outcome") or "").strip().lower()
    if outcome:
        return outcome
    if bool(row.get("success", False)):
        return "success"
    err = str(row.get("error_message", "") or "").lower()
    if "policy_reject" in err:
        return "policy_reject"
    if "cooldown" in err:
        return "cooldown_reject"
    return "failed"


def _load_equity_rows(
    client: firestore.Client,
    platform: str,
    since: datetime,
) -> list[dict[str, Any]]:
    query = (
        client.collection("equity_snapshots")
        .where(filter=FieldFilter("recorded_at", ">=", since))
        .order_by("recorded_at", direction=firestore.Query.ASCENDING)
    )
    rows: list[dict[str, Any]] = []
    for doc in query.stream():
        row = doc.to_dict() or {}
        if str(row.get("platform", "")).lower() != str(platform).lower():
            continue
        row["id"] = doc.id
        row["recorded_at"] = _as_dt(row.get("recorded_at"))
        if row["recorded_at"] is None:
            continue
        rows.append(row)
    return rows


def _load_exec_rows(
    client: firestore.Client,
    platform: str,
    since: datetime,
) -> list[dict[str, Any]]:
    query = (
        client.collection("execution_verifications")
        .where(filter=FieldFilter("recorded_at", ">=", since))
        .order_by("recorded_at", direction=firestore.Query.ASCENDING)
    )
    rows: list[dict[str, Any]] = []
    for doc in query.stream():
        row = doc.to_dict() or {}
        if str(row.get("platform", "")).lower() != str(platform).lower():
            continue
        row["id"] = doc.id
        row["recorded_at"] = _as_dt(row.get("recorded_at"))
        if row["recorded_at"] is None:
            continue
        rows.append(row)
    return rows


def _render_charts(
    out_dir: Path,
    equity_rows: list[dict[str, Any]],
    exec_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    try:
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
    except Exception as exc:  # pragma: no cover - environment-dependent
        return {"enabled": False, "error": f"matplotlib_unavailable: {type(exc).__name__}: {exc}"}

    if equity_rows:
        times = [row["recorded_at"] for row in equity_rows]
        equity = [_as_float(row.get("equity_estimate")) for row in equity_rows]
        drawdown = [_as_float(row.get("drawdown_pct")) for row in equity_rows]

        fig, ax1 = plt.subplots(figsize=(11, 5))
        ax1.plot(times, equity, color="#ffb000", linewidth=2.0, label="Equity")
        ax1.set_title("Lighter Equity Timeline")
        ax1.set_ylabel("Equity (USDC)")
        ax1.grid(alpha=0.25, linestyle="--")

        ax2 = ax1.twinx()
        ax2.plot(times, drawdown, color="#ff3b30", linewidth=1.3, alpha=0.8, label="Drawdown %")
        ax2.set_ylabel("Drawdown %")

        ax1.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
        fig.autofmt_xdate()
        fig.tight_layout()
        fig.savefig(out_dir / "equity_timeline.png", dpi=150)
        plt.close(fig)

    if exec_rows:
        outcomes = Counter(_classify_execution(row) for row in exec_rows)
        labels = list(outcomes.keys())
        values = [outcomes[k] for k in labels]
        colors = ["#00c853" if k == "success" else "#ff6d00" if "reject" in k else "#ff1744" for k in labels]

        fig, ax = plt.subplots(figsize=(8, 4.5))
        ax.bar(labels, values, color=colors)
        ax.set_title("Execution Verification Outcomes")
        ax.set_ylabel("Count")
        ax.grid(axis="y", alpha=0.25, linestyle="--")
        fig.tight_layout()
        fig.savefig(out_dir / "execution_outcomes.png", dpi=150)
        plt.close(fig)

    return {"enabled": True, "error": ""}


def _write_html_dashboard(
    out_dir: Path,
    equity_rows: list[dict[str, Any]],
    exec_rows: list[dict[str, Any]],
) -> str:
    labels = [
        row["recorded_at"].astimezone(timezone.utc).strftime("%m-%d %H:%M")
        for row in equity_rows
    ]
    equity = [_as_float(row.get("equity_estimate")) for row in equity_rows]
    drawdown = [_as_float(row.get("drawdown_pct")) for row in equity_rows]

    outcomes = Counter(_classify_execution(row) for row in exec_rows)
    out_labels = list(outcomes.keys())
    out_values = [outcomes[k] for k in out_labels]

    html_path = out_dir / "progress_dashboard.html"
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Lighter Progress Dashboard</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif; background:#0b1117; color:#e6edf3; margin:0; padding:24px; }}
    .grid {{ display:grid; grid-template-columns:1fr; gap:18px; max-width:1200px; margin:0 auto; }}
    .card {{ background:#111923; border:1px solid #30363d; border-radius:12px; padding:16px; }}
    h2 {{ margin:0 0 12px; font-size:18px; }}
    .meta {{ color:#9fb0c3; font-size:13px; margin-top:8px; }}
  </style>
</head>
<body>
  <div class="grid">
    <div class="card">
      <h2>Equity & Drawdown</h2>
      <canvas id="equityChart"></canvas>
      <div class="meta">UTC timeline from Firestore equity_snapshots</div>
    </div>
    <div class="card">
      <h2>Execution Outcomes</h2>
      <canvas id="outcomeChart"></canvas>
      <div class="meta">From execution_verifications</div>
    </div>
  </div>
  <script>
    const labels = {json.dumps(labels)};
    const equity = {json.dumps(equity)};
    const drawdown = {json.dumps(drawdown)};
    const outcomeLabels = {json.dumps(out_labels)};
    const outcomeValues = {json.dumps(out_values)};

    new Chart(document.getElementById('equityChart'), {{
      type: 'line',
      data: {{
        labels,
        datasets: [
          {{ label: 'Equity (USDC)', data: equity, borderColor: '#ffb000', backgroundColor: 'rgba(255,176,0,0.2)', tension: 0.25 }},
          {{ label: 'Drawdown %', data: drawdown, borderColor: '#ff3b30', backgroundColor: 'rgba(255,59,48,0.15)', tension: 0.25 }}
        ]
      }},
      options: {{ responsive: true, plugins: {{ legend: {{ labels: {{ color: '#e6edf3' }} }} }}, scales: {{ x: {{ ticks: {{ color: '#9fb0c3' }} }}, y: {{ ticks: {{ color: '#9fb0c3' }} }} }} }}
    }});

    new Chart(document.getElementById('outcomeChart'), {{
      type: 'bar',
      data: {{
        labels: outcomeLabels,
        datasets: [{{ label: 'Count', data: outcomeValues, backgroundColor: ['#00c853','#ff6d00','#ff1744','#1e88e5'] }}]
      }},
      options: {{ responsive: true, plugins: {{ legend: {{ labels: {{ color: '#e6edf3' }} }} }}, scales: {{ x: {{ ticks: {{ color: '#9fb0c3' }} }}, y: {{ ticks: {{ color: '#9fb0c3' }}, beginAtZero: true }} }} }}
    }});
  </script>
</body>
</html>
"""
    html_path.write_text(html, encoding="utf-8")
    return str(html_path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Lighter progress verification report.")
    parser.add_argument("--project", default="sapphire-479610", help="GCP project ID")
    parser.add_argument("--platform", default="lighter", help="Platform key (default: lighter)")
    parser.add_argument("--hours", type=int, default=24, help="Lookback window in hours")
    parser.add_argument(
        "--output-dir",
        default="",
        help="Output directory (default: /Users/aribs/Sapphire/output/progress_verification/<timestamp>)",
    )
    args = parser.parse_args()

    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=max(1, args.hours))
    stamp = now.strftime("%Y%m%d_%H%M%S")
    out_dir = (
        Path(args.output_dir).expanduser()
        if args.output_dir
        else Path("/Users/aribs/Sapphire/output/progress_verification") / stamp
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    client = firestore.Client(project=args.project)
    equity_rows = _load_equity_rows(client, args.platform, since)
    exec_rows = _load_exec_rows(client, args.platform, since)

    start_equity = _as_float(equity_rows[0].get("equity_estimate")) if equity_rows else 0.0
    end_equity = _as_float(equity_rows[-1].get("equity_estimate")) if equity_rows else 0.0
    pnl_abs = end_equity - start_equity
    pnl_pct = (pnl_abs / start_equity * 100.0) if start_equity > 0 else 0.0
    max_drawdown_pct = min((_as_float(r.get("drawdown_pct")) for r in equity_rows), default=0.0)

    stale_balance_count = sum(1 for r in equity_rows if bool(r.get("balance_sync_stale")))
    stale_position_count = sum(1 for r in equity_rows if bool(r.get("position_check_stale")))
    total_snapshots = len(equity_rows)

    outcome_counts = Counter(_classify_execution(row) for row in exec_rows)
    by_strategy: dict[str, int] = defaultdict(int)
    by_timeframe: dict[str, int] = defaultdict(int)
    for row in exec_rows:
        by_strategy[str(row.get("strategy") or "unknown")] += 1
        by_timeframe[str(row.get("timeframe") or "unknown")] += 1

    chart_status = _render_charts(out_dir, equity_rows, exec_rows)

    html_dashboard = _write_html_dashboard(out_dir, equity_rows, exec_rows)

    summary = {
        "generated_at": now.isoformat(),
        "project": args.project,
        "platform": args.platform,
        "window_hours": args.hours,
        "from": since.isoformat(),
        "to": now.isoformat(),
        "equity": {
            "snapshots": total_snapshots,
            "start_equity": round(start_equity, 8),
            "end_equity": round(end_equity, 8),
            "pnl_abs": round(pnl_abs, 8),
            "pnl_pct": round(pnl_pct, 6),
            "max_drawdown_pct": round(max_drawdown_pct, 6),
        },
        "data_quality": {
            "stale_balance_snapshots": stale_balance_count,
            "stale_position_snapshots": stale_position_count,
            "stale_balance_ratio": round(stale_balance_count / total_snapshots, 6) if total_snapshots else 0.0,
            "stale_position_ratio": round(stale_position_count / total_snapshots, 6) if total_snapshots else 0.0,
        },
        "execution_verification": {
            "rows": len(exec_rows),
            "outcomes": dict(outcome_counts),
            "by_strategy": dict(by_strategy),
            "by_timeframe": dict(by_timeframe),
        },
        "artifacts": {
            "summary_json": str(out_dir / "summary.json"),
            "equity_timeline_png": str(out_dir / "equity_timeline.png"),
            "execution_outcomes_png": str(out_dir / "execution_outcomes.png"),
            "html_dashboard": html_dashboard,
            "charts_enabled": bool(chart_status.get("enabled", False)),
            "charts_error": str(chart_status.get("error", "") or ""),
        },
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
