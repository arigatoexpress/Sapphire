#!/usr/bin/env python3
"""Compare local and remote weekly backtest artifacts.

The comparator is read-only with respect to inputs. It writes a paired JSON and
Markdown report under ``--report-out`` so the weekly-backtest shadow can soak
before the local LaunchAgent is retired.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PASS = "PASS"
WARN = "WARN"
FAIL = "FAIL"

EXIT_PASS = 0
EXIT_WARN = 10
EXIT_FAIL = 20
EX_USAGE = 64
EX_CANTCREAT = 73
EX_IOERR = 74
EX_CONFIG = 78

TOOL_VERSION = "0.1.0"
BaseKey = tuple[str, str, str, str]
RowKey = tuple[str, str, str, str, int]


@dataclass(frozen=True)
class Artifact:
    path: Path
    data: dict[str, Any]
    sha256: str

    @property
    def computed_at(self) -> str:
        return str(self.data.get("computed_at") or "")

    @property
    def results(self) -> list[dict[str, Any]]:
        results = self.data.get("results")
        return results if isinstance(results, list) else []

    @property
    def metadata(self) -> dict[str, Any]:
        metadata = self.data.get("metadata")
        return metadata if isinstance(metadata, dict) else {}

    def summary(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "computed_at": self.computed_at,
            "row_count": len(self.results),
            "sha256": self.sha256,
        }


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return EXIT_PASS if exc.code == 0 else EX_USAGE

    try:
        report = compare_from_args(args)
    except UsageError as exc:
        print(f"usage error: {exc}", file=sys.stderr)
        return EX_USAGE
    except InputReadError as exc:
        print(f"input read error: {exc}", file=sys.stderr)
        return EX_IOERR
    except SchemaError as exc:
        print(f"schema error: {exc}", file=sys.stderr)
        return EX_CONFIG
    except ReportWriteError as exc:
        print(f"report write error: {exc}", file=sys.stderr)
        return EX_CANTCREAT

    if not args.quiet:
        print(render_markdown(report))

    return int(report["exit_code"])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--local-sweep", required=True, type=Path)
    parser.add_argument("--remote-sweep", required=True, type=Path)
    parser.add_argument("--local-best", type=Path)
    parser.add_argument("--remote-best", type=Path)
    parser.add_argument("--report-out", type=Path, default=Path("data/backtests/shadow-reports"))
    parser.add_argument("--tolerance-config", type=Path)
    parser.add_argument("--strict", action="store_true", help="Treat WARN verdicts as FAIL")
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--quiet", action="store_true")
    output.add_argument("--verbose", action="store_true")
    return parser


def compare_from_args(args: argparse.Namespace) -> dict[str, Any]:
    local_sweep = load_artifact(args.local_sweep)
    remote_sweep = load_artifact(args.remote_sweep)
    if local_sweep.sha256 == remote_sweep.sha256:
        raise UsageError("local and remote sweep inputs are identical (sha256 match)")

    local_best = load_artifact(args.local_best) if args.local_best else None
    remote_best = load_artifact(args.remote_best) if args.remote_best else None
    if local_best and remote_best and local_best.sha256 == remote_best.sha256:
        raise UsageError("local and remote best inputs are identical (sha256 match)")

    tolerance = load_tolerance(args.tolerance_config)
    report = compare_artifacts(
        local_sweep=local_sweep,
        remote_sweep=remote_sweep,
        local_best=local_best,
        remote_best=remote_best,
        tolerance=tolerance,
        strict=args.strict,
    )
    write_reports(report, args.report_out)
    return report


def compare_artifacts(
    *,
    local_sweep: Artifact,
    remote_sweep: Artifact,
    local_best: Artifact | None = None,
    remote_best: Artifact | None = None,
    tolerance: dict[str, Any] | None = None,
    strict: bool = False,
) -> dict[str, Any]:
    tolerance = tolerance or default_tolerance()
    compared_at = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    local_rows = index_results(local_sweep.results, "local_sweep")
    remote_rows = index_results(remote_sweep.results, "remote_sweep")
    local_best_rows = local_best.results if local_best else recompute_best(local_sweep.results)
    remote_best_rows = remote_best.results if remote_best else recompute_best(remote_sweep.results)
    local_top3 = top3(local_best_rows)
    remote_top3 = top3(remote_best_rows)
    top3_keys = {row_key(row) for row in local_top3} | {row_key(row) for row in remote_top3}

    local_keys = set(local_rows)
    remote_keys = set(remote_rows)
    common_keys = sorted(local_keys & remote_keys)
    missing_in_local = [key_to_dict(key) for key in sorted(remote_keys - local_keys)]
    missing_in_remote = [key_to_dict(key) for key in sorted(local_keys - remote_keys)]

    row_diffs = [
        compare_row(key, local_rows[key], remote_rows[key], tolerance, base_key(key) in top3_keys)
        for key in common_keys
    ]

    row_counts = {
        PASS: sum(1 for row in row_diffs if row["verdict"] == PASS),
        WARN: sum(1 for row in row_diffs if row["verdict"] == WARN),
        FAIL: sum(1 for row in row_diffs if row["verdict"] == FAIL),
    }
    local_top3_keys = [row_key(row) for row in local_top3]
    remote_top3_keys = [row_key(row) for row in remote_top3]
    leaderboard_set_equal = set(local_top3_keys) == set(remote_top3_keys)
    leaderboard_order_equal = local_top3_keys == remote_top3_keys
    bar_windows = collect_bar_windows(local_best_rows, remote_best_rows)
    metadata = metadata_summary(local_sweep.metadata, remote_sweep.metadata)

    verdict = run_verdict(
        row_counts=row_counts,
        row_count_local=len(local_sweep.results),
        row_count_remote=len(remote_sweep.results),
        missing_in_local=missing_in_local,
        missing_in_remote=missing_in_remote,
        leaderboard_set_equal=leaderboard_set_equal,
        leaderboard_order_equal=leaderboard_order_equal,
        strict=strict,
    )
    exit_code = {PASS: EXIT_PASS, WARN: EXIT_WARN, FAIL: EXIT_FAIL}[verdict]

    report = {
        "schema_version": 1,
        "compared_at": compared_at,
        "tool_version": TOOL_VERSION,
        "strict": strict,
        "verdict": verdict,
        "exit_code": exit_code,
        "inputs": {
            "local_sweep": local_sweep.summary(),
            "remote_sweep": remote_sweep.summary(),
            "local_best": local_best.summary() if local_best else None,
            "remote_best": remote_best.summary() if remote_best else None,
        },
        "tolerance_config": tolerance,
        "summary": {
            "rows_compared": len(row_diffs),
            "rows_pass": row_counts[PASS],
            "rows_warn": row_counts[WARN],
            "rows_fail": row_counts[FAIL],
            "leaderboard_top3_set_equal": leaderboard_set_equal,
            "leaderboard_top3_order_equal": leaderboard_order_equal,
            "bar_window_local": bar_windows["local"],
            "bar_window_remote": bar_windows["remote"],
            "missing_in_local": missing_in_local,
            "missing_in_remote": missing_in_remote,
            "metadata": metadata,
        },
        "row_diffs": row_diffs,
        "leaderboard": {
            "local_top3": [summarize_row(row) for row in local_top3],
            "remote_top3": [summarize_row(row) for row in remote_top3],
        },
    }
    return _json_safe(report)


def compare_row(
    key: RowKey,
    local: dict[str, Any],
    remote: dict[str, Any],
    tolerance: dict[str, Any],
    is_top3: bool,
) -> dict[str, Any]:
    metric_diffs: list[dict[str, Any]] = []

    for metric in ("params.rsi_period", "params.sl_pct", "params.tp_pct"):
        metric_diffs.append(
            compare_exact(metric, get_nested(local, metric), get_nested(remote, metric))
        )

    local_trades = int_or_none(local.get("total_trades"))
    remote_trades = int_or_none(remote.get("total_trades"))
    metric_diffs.append(compare_trades(local_trades, remote_trades))

    zero_trades = (local_trades or 0) == 0 and (remote_trades or 0) == 0
    numeric_metrics = [
        "total_return_pct",
        "max_drawdown_pct",
        "sortino",
        "sharpe",
        "calmar",
        "win_rate",
        "profit_factor",
    ]
    for metric in numeric_metrics:
        if zero_trades and metric in {"sortino", "sharpe", "calmar", "win_rate", "profit_factor"}:
            continue
        metric_diffs.append(
            compare_metric(
                metric,
                local.get(metric),
                remote.get(metric),
                tolerance,
                local_trades,
                remote_trades,
            )
        )

    report_diff = compare_report(local.get("report"), remote.get("report"), tolerance)
    metric_diffs.extend(report_diff)

    raw_verdict = worst_status(diff["status"] for diff in metric_diffs)
    verdict = FAIL if is_top3 and raw_verdict == WARN else raw_verdict
    return {
        "key": key_to_dict(key),
        "is_top3": is_top3,
        "verdict": verdict,
        "metric_diffs": [diff for diff in metric_diffs if diff["status"] != PASS],
    }


def compare_exact(metric: str, local: Any, remote: Any) -> dict[str, Any]:
    status = PASS if local == remote else FAIL
    return {"metric": metric, "local": local, "remote": remote, "status": status}


def compare_trades(local: int | None, remote: int | None) -> dict[str, Any]:
    local = local or 0
    remote = remote or 0
    diff = abs(local - remote)
    maximum = max(local, remote)
    if diff == 0:
        status = PASS
        allowed = 0
    elif min(local, remote) == 0:
        status = FAIL
        allowed = 0
    else:
        allowed = 0 if maximum >= 10 else 1 if maximum >= 5 else 2
        status = PASS if diff <= allowed else WARN if diff <= allowed * 2 else FAIL
    return {
        "metric": "total_trades",
        "local": local,
        "remote": remote,
        "abs_diff": diff,
        "tolerance": allowed,
        "status": status,
    }


def compare_metric(
    metric: str,
    local_raw: Any,
    remote_raw: Any,
    tolerance: dict[str, Any],
    local_trades: int | None,
    remote_trades: int | None,
) -> dict[str, Any]:
    local = to_float(local_raw)
    remote = to_float(remote_raw)
    if local is None and remote is None:
        return {"metric": metric, "local": local_raw, "remote": remote_raw, "status": PASS}
    if local is None or remote is None:
        return {"metric": metric, "local": local_raw, "remote": remote_raw, "status": WARN}

    if metric == "profit_factor":
        return compare_profit_factor(local, remote)

    abs_diff = abs(local - remote)
    allowed = metric_tolerance(metric, local, remote, tolerance, local_trades, remote_trades)
    status = PASS if abs_diff <= allowed else WARN if abs_diff <= allowed * 2 else FAIL
    return {
        "metric": metric,
        "local": local,
        "remote": remote,
        "abs_diff": abs_diff,
        "rel_diff": relative_diff(local, remote),
        "tolerance": allowed,
        "status": status,
    }


def compare_profit_factor(local: float, remote: float) -> dict[str, Any]:
    if local >= 100 and remote >= 100:
        status = PASS
        allowed: float | str = "sentinel>=100"
    elif (local >= 100) != (remote >= 100):
        status = WARN
        allowed = "mixed-sentinel"
    else:
        rel = relative_diff(local, remote)
        status = PASS if rel <= 0.15 else WARN if rel <= 0.30 else FAIL
        allowed = 0.15
    return {
        "metric": "profit_factor",
        "local": local,
        "remote": remote,
        "abs_diff": abs(local - remote),
        "rel_diff": relative_diff(local, remote),
        "tolerance": allowed,
        "status": status,
    }


def compare_report(
    local_report: Any, remote_report: Any, tolerance: dict[str, Any]
) -> list[dict[str, Any]]:
    if not isinstance(local_report, dict) and not isinstance(remote_report, dict):
        return []
    if not isinstance(local_report, dict) or not isinstance(remote_report, dict):
        return [
            {
                "metric": "report",
                "local": bool(local_report),
                "remote": bool(remote_report),
                "status": WARN,
            }
        ]

    diffs = [
        compare_exact("report.symbol", local_report.get("symbol"), remote_report.get("symbol")),
        compare_bars(local_report.get("bars"), remote_report.get("bars")),
        compare_date_window("report.start", local_report.get("start"), remote_report.get("start")),
        compare_date_window("report.end", local_report.get("end"), remote_report.get("end")),
        compare_trade_distribution(local_report.get("trades"), remote_report.get("trades")),
        compare_equity_curve(
            local_report.get("equity_curve"), remote_report.get("equity_curve"), tolerance
        ),
    ]
    for metric in ("cagr_pct", "expectancy", "avg_trade_pnl", "avg_win", "avg_loss"):
        if metric in local_report or metric in remote_report:
            diffs.append(
                compare_report_metric(metric, local_report.get(metric), remote_report.get(metric))
            )
    return diffs


def compare_bars(local_raw: Any, remote_raw: Any) -> dict[str, Any]:
    local = int_or_none(local_raw)
    remote = int_or_none(remote_raw)
    if local is None and remote is None:
        return {"metric": "report.bars", "local": local_raw, "remote": remote_raw, "status": PASS}
    if local is None or remote is None:
        return {"metric": "report.bars", "local": local_raw, "remote": remote_raw, "status": WARN}
    diff = abs(local - remote)
    status = PASS if diff <= 1 else WARN if diff <= 2 else FAIL
    return {
        "metric": "report.bars",
        "local": local,
        "remote": remote,
        "abs_diff": diff,
        "tolerance": 1,
        "status": status,
    }


def compare_date_window(metric: str, local_raw: Any, remote_raw: Any) -> dict[str, Any]:
    local = parse_date(str(local_raw)) if local_raw else None
    remote = parse_date(str(remote_raw)) if remote_raw else None
    if local is None and remote is None:
        return {"metric": metric, "local": local_raw, "remote": remote_raw, "status": PASS}
    if local is None or remote is None:
        return {"metric": metric, "local": local_raw, "remote": remote_raw, "status": WARN}
    days = abs((local - remote).days)
    status = PASS if days <= 1 else WARN if days <= 2 else FAIL
    return {
        "metric": metric,
        "local": str(local),
        "remote": str(remote),
        "day_diff": days,
        "tolerance": 1,
        "status": status,
    }


def compare_trade_distribution(local_raw: Any, remote_raw: Any) -> dict[str, Any]:
    local = local_raw if isinstance(local_raw, list) else []
    remote = remote_raw if isinstance(remote_raw, list) else []
    length_diff = abs(len(local) - len(remote))
    allowed = 1 if max(len(local), len(remote)) <= 5 else 2
    direction_diff = distribution_delta(local, remote, "direction")
    exit_reason_diff = distribution_delta(local, remote, "exit_reason")
    max_bucket_diff = max([0, *direction_diff.values(), *exit_reason_diff.values()])
    status = (
        PASS
        if length_diff <= allowed and max_bucket_diff <= 1
        else WARN
        if length_diff <= allowed * 2 and max_bucket_diff <= 2
        else FAIL
    )
    return {
        "metric": "report.trades.distribution",
        "local": {"count": len(local)},
        "remote": {"count": len(remote)},
        "count_diff": length_diff,
        "direction_diff": direction_diff,
        "exit_reason_diff": exit_reason_diff,
        "status": status,
    }


def compare_equity_curve(
    local_raw: Any, remote_raw: Any, tolerance: dict[str, Any]
) -> dict[str, Any]:
    local = local_raw if isinstance(local_raw, list) else []
    remote = remote_raw if isinstance(remote_raw, list) else []
    if not local and not remote:
        return {"metric": "report.equity_curve", "local": 0, "remote": 0, "status": PASS}
    if not local or not remote:
        return {
            "metric": "report.equity_curve",
            "local": len(local),
            "remote": len(remote),
            "status": WARN,
        }
    length_diff = abs(len(local) - len(remote))
    local_final = to_float(
        local[-1][1] if isinstance(local[-1], list | tuple) and len(local[-1]) > 1 else None
    )
    remote_final = to_float(
        remote[-1][1] if isinstance(remote[-1], list | tuple) and len(remote[-1]) > 1 else None
    )
    final_rel = relative_diff(local_final or 0.0, remote_final or 0.0)
    allowed = float(tolerance.get("equity_curve_final_rel", 0.01))
    status = (
        PASS
        if length_diff <= 1 and final_rel <= allowed
        else WARN
        if length_diff <= 2 and final_rel <= allowed * 2
        else FAIL
    )
    return {
        "metric": "report.equity_curve",
        "local": {"length": len(local), "final": local_final},
        "remote": {"length": len(remote), "final": remote_final},
        "length_diff": length_diff,
        "rel_diff": final_rel,
        "tolerance": allowed,
        "status": status,
    }


def compare_report_metric(metric: str, local_raw: Any, remote_raw: Any) -> dict[str, Any]:
    local = to_float(local_raw)
    remote = to_float(remote_raw)
    if local is None and remote is None:
        return {
            "metric": f"report.{metric}",
            "local": local_raw,
            "remote": remote_raw,
            "status": PASS,
        }
    if local is None or remote is None:
        return {
            "metric": f"report.{metric}",
            "local": local_raw,
            "remote": remote_raw,
            "status": WARN,
        }
    abs_diff = abs(local - remote)
    allowed = max(0.10, 0.10 * max(abs(local), abs(remote)))
    status = PASS if abs_diff <= allowed else WARN if abs_diff <= allowed * 2 else FAIL
    return {
        "metric": f"report.{metric}",
        "local": local,
        "remote": remote,
        "abs_diff": abs_diff,
        "rel_diff": relative_diff(local, remote),
        "tolerance": allowed,
        "status": status,
    }


def metric_tolerance(
    metric: str,
    local: float,
    remote: float,
    tolerance: dict[str, Any],
    local_trades: int | None,
    remote_trades: int | None,
) -> float:
    if metric in {"sortino", "sharpe"}:
        return max(
            float(tolerance[metric]["abs"]),
            float(tolerance[metric]["rel"]) * max(abs(local), abs(remote)),
        )
    if metric == "calmar":
        return max(
            float(tolerance[metric]["abs"]),
            float(tolerance[metric]["rel"]) * max(abs(local), abs(remote)),
        )
    if metric in {"total_return_pct", "max_drawdown_pct"}:
        spec = tolerance[metric]
        rel_part = float(spec.get("rel", 0.0)) * max(abs(local), abs(remote))
        return max(float(spec["abs"]), rel_part)
    if metric == "win_rate":
        trades = max(local_trades or 0, remote_trades or 0)
        return 0.0 if trades < 3 else 0.10 if trades < 10 else 0.05
    return 0.0


def run_verdict(
    *,
    row_counts: dict[str, int],
    row_count_local: int,
    row_count_remote: int,
    missing_in_local: list[dict[str, str]],
    missing_in_remote: list[dict[str, str]],
    leaderboard_set_equal: bool,
    leaderboard_order_equal: bool,
    strict: bool,
) -> str:
    if row_counts[FAIL] > 0 or not leaderboard_set_equal:
        verdict = FAIL
    elif missing_in_local or missing_in_remote:
        coverage_delta = len(missing_in_local) + len(missing_in_remote)
        verdict = WARN if coverage_delta <= 1 else FAIL
    elif row_count_delta_ratio(row_count_local, row_count_remote) > 0.02:
        verdict = FAIL
    elif row_counts[WARN] == 0 and leaderboard_order_equal:
        verdict = PASS
    elif row_counts[WARN] / max(1, sum(row_counts.values())) <= 0.05:
        verdict = WARN
    else:
        verdict = FAIL
    return FAIL if strict and verdict == WARN else verdict


def row_count_delta_ratio(local: int, remote: int) -> float:
    return abs(local - remote) / max(1, max(local, remote))


def index_results(results: list[dict[str, Any]], label: str) -> dict[RowKey, dict[str, Any]]:
    indexed: dict[RowKey, dict[str, Any]] = {}
    occurrences: dict[BaseKey, int] = {}
    for row in results:
        base = row_key(row)
        if not all(base):
            raise SchemaError(f"{label} row missing strategy_cls/symbol/strategy_name")
        occurrence = occurrences.get(base, 0)
        occurrences[base] = occurrence + 1
        key = (*base, occurrence)
        if key in indexed:
            raise SchemaError(f"{label} duplicate row key {key}")
        indexed[key] = row
    return indexed


def row_key(row: dict[str, Any]) -> BaseKey:
    return (
        str(row.get("strategy_cls") or ""),
        str(row.get("symbol") or ""),
        str(row.get("strategy_name") or ""),
        params_signature(row.get("params")),
    )


def key_to_dict(key: RowKey) -> dict[str, str]:
    return {
        "strategy_cls": key[0],
        "symbol": key[1],
        "strategy_name": key[2],
        "params_signature": key[3],
        "duplicate_index": key[4],
    }


def base_key(key: RowKey) -> BaseKey:
    return key[:4]


def params_signature(params: Any) -> str:
    if not isinstance(params, dict):
        return ""
    return json.dumps(params, sort_keys=True, separators=(",", ":"))


def recompute_best(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best: dict[tuple[str, str], dict[str, Any]] = {}
    for row in results:
        key = (str(row.get("strategy_cls") or ""), str(row.get("symbol") or ""))
        current = best.get(key)
        if current is None or sort_value(row.get("sortino")) > sort_value(current.get("sortino")):
            best[key] = row
    return list(best.values())


def top3(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda row: sort_value(row.get("sortino")), reverse=True)[:3]


def sort_value(value: Any) -> float:
    parsed = to_float(value)
    return float("-inf") if parsed is None else parsed


def summarize_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "strategy_cls": row.get("strategy_cls"),
        "symbol": row.get("symbol"),
        "strategy_name": row.get("strategy_name"),
        "params": row.get("params"),
        "sortino": row.get("sortino"),
        "sharpe": row.get("sharpe"),
        "total_return_pct": row.get("total_return_pct"),
        "total_trades": row.get("total_trades"),
    }


def collect_bar_windows(
    local_best: list[dict[str, Any]], remote_best: list[dict[str, Any]]
) -> dict[str, list[str | None]]:
    return {"local": first_bar_window(local_best), "remote": first_bar_window(remote_best)}


def metadata_summary(
    local_metadata: dict[str, Any],
    remote_metadata: dict[str, Any],
) -> dict[str, Any]:
    local_source = local_metadata.get("source") if isinstance(local_metadata.get("source"), dict) else {}
    remote_source = (
        remote_metadata.get("source") if isinstance(remote_metadata.get("source"), dict) else {}
    )
    return {
        "available_local": bool(local_metadata),
        "available_remote": bool(remote_metadata),
        "source": {
            "local_git_sha": local_source.get("git_sha") or "",
            "remote_git_sha": remote_source.get("git_sha") or "",
            "git_sha_equal": source_value_equal(local_source, remote_source, "git_sha"),
            "local_github_run_id": local_source.get("github_run_id") or "",
            "remote_github_run_id": remote_source.get("github_run_id") or "",
            "local_yfinance_version": local_source.get("yfinance_version"),
            "remote_yfinance_version": remote_source.get("yfinance_version"),
            "yfinance_version_equal": source_value_equal(
                local_source, remote_source, "yfinance_version"
            ),
        },
        "bar_fingerprints": compare_bar_fingerprints(
            local_metadata.get("bar_fingerprints"),
            remote_metadata.get("bar_fingerprints"),
        ),
    }


def source_value_equal(
    local_source: dict[str, Any],
    remote_source: dict[str, Any],
    key: str,
) -> bool | None:
    local = local_source.get(key)
    remote = remote_source.get(key)
    if local in (None, "") or remote in (None, ""):
        return None
    return local == remote


def compare_bar_fingerprints(local_raw: Any, remote_raw: Any) -> dict[str, Any]:
    local = local_raw if isinstance(local_raw, dict) else {}
    remote = remote_raw if isinstance(remote_raw, dict) else {}
    if not local and not remote:
        status = "unavailable"
    elif not local or not remote:
        status = "partial"
    else:
        status = "equal"

    missing_in_local = sorted(set(remote) - set(local))
    missing_in_remote = sorted(set(local) - set(remote))
    differing: list[dict[str, Any]] = []
    matched = 0
    for symbol in sorted(set(local) & set(remote)):
        local_fp = fingerprint_identity(local.get(symbol))
        remote_fp = fingerprint_identity(remote.get(symbol))
        if local_fp == remote_fp:
            matched += 1
        else:
            differing.append({"symbol": symbol, "local": local_fp, "remote": remote_fp})

    if missing_in_local or missing_in_remote or differing:
        status = "different" if local and remote else status

    return {
        "status": status,
        "matched": matched,
        "differing": len(differing),
        "missing_in_local": missing_in_local,
        "missing_in_remote": missing_in_remote,
        "diffs": differing[:10],
    }


def fingerprint_identity(raw: Any) -> dict[str, Any]:
    item = raw if isinstance(raw, dict) else {}
    return {
        "sha256": item.get("sha256") or "",
        "bars": item.get("bars"),
        "start": item.get("start") or "",
        "end": item.get("end") or "",
    }


def first_bar_window(rows: list[dict[str, Any]]) -> list[str | None]:
    for row in rows:
        report = row.get("report")
        if isinstance(report, dict) and (report.get("start") or report.get("end")):
            return [report.get("start"), report.get("end")]
    return [None, None]


def load_tolerance(path: Path | None) -> dict[str, Any]:
    tolerance = default_tolerance()
    if not path:
        return tolerance
    artifact = load_artifact(path)
    if not isinstance(artifact.data, dict):
        raise SchemaError(f"tolerance config must be a JSON object: {path}")
    tolerance.update(artifact.data)
    return tolerance


def default_tolerance() -> dict[str, Any]:
    return {
        "sortino": {"rel": 0.05, "abs": 0.10},
        "sharpe": {"rel": 0.05, "abs": 0.10},
        "calmar": {"rel": 0.10, "abs": 0.20},
        "total_return_pct": {"abs": 0.005},
        "win_rate": {"abs_high_trades": 0.05, "abs_low_trades": 0.10},
        "max_drawdown_pct": {"abs": 0.005, "rel": 0.20},
        "profit_factor": {"rel": 0.15, "sentinel": 100},
        "equity_curve_final_rel": 0.01,
    }


def load_artifact(path: Path) -> Artifact:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise InputReadError(f"{path}: {exc}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SchemaError(f"{path}: JSON parse failed at byte {exc.pos}: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise SchemaError(f"{path}: expected JSON object")
    return Artifact(path=path, data=data, sha256=hashlib.sha256(raw.encode("utf-8")).hexdigest())


def write_reports(report: dict[str, Any], out_dir: Path) -> None:
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        (out_dir / f"shadow-comparison-{stamp}.json").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )
        (out_dir / f"shadow-comparison-{stamp}.md").write_text(
            render_markdown(report), encoding="utf-8"
        )
    except OSError as exc:
        raise ReportWriteError(f"{out_dir}: {exc}") from exc


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    inputs = report["inputs"]
    metadata = summary.get("metadata") or {}
    source = metadata.get("source") or {}
    fingerprints = metadata.get("bar_fingerprints") or {}
    lines = [
        f"# Backtest Shadow Comparison - {report['compared_at']}",
        "",
        f"**Verdict**: {report['verdict']}",
        f"**Local**: `{inputs['local_sweep']['path']}` ({inputs['local_sweep'].get('computed_at') or '-'}, {inputs['local_sweep']['row_count']} rows)",
        f"**Remote**: `{inputs['remote_sweep']['path']}` ({inputs['remote_sweep'].get('computed_at') or '-'}, {inputs['remote_sweep']['row_count']} rows)",
        f"**Bar window**: local {summary['bar_window_local'][0] or '-'} -> {summary['bar_window_local'][1] or '-'}, "
        f"remote {summary['bar_window_remote'][0] or '-'} -> {summary['bar_window_remote'][1] or '-'}",
        "",
        "## Top-3 Leaderboard (Sortino)",
        "",
        "| Rank | Local | Remote | Match? |",
        "|---:|---|---|:---:|",
    ]
    local_top = report["leaderboard"]["local_top3"]
    remote_top = report["leaderboard"]["remote_top3"]
    for idx in range(3):
        local = local_top[idx] if idx < len(local_top) else {}
        remote = remote_top[idx] if idx < len(remote_top) else {}
        match = row_key(local) == row_key(remote) if local and remote else False
        lines.append(
            f"| {idx + 1} | {format_leader(local)} | {format_leader(remote)} | {'yes' if match else 'no'} |"
        )

    lines.extend(
        [
            "",
            "## Row Counts",
            "",
            f"- Compared: {summary['rows_compared']}",
            f"- PASS: {summary['rows_pass']}",
            f"- WARN: {summary['rows_warn']}",
            f"- FAIL: {summary['rows_fail']}",
            f"- Missing in local: {len(summary['missing_in_local'])}",
            f"- Missing in remote: {len(summary['missing_in_remote'])}",
            "",
            "## Notable Diffs",
            "",
        ]
    )
    notable = notable_diffs(report["row_diffs"])
    if notable:
        lines.extend(
            ["| Key | Metric | Local | Remote | Delta | Verdict |", "|---|---|---:|---:|---:|---|"]
        )
        for item in notable[:10]:
            key = item["key"]
            metric = item["diff"]
            lines.append(
                f"| {key['strategy_cls']} / {key['symbol']} / {key['strategy_name']} | "
                f"{metric['metric']} | {fmt(metric.get('local'))} | {fmt(metric.get('remote'))} | "
                f"{fmt(metric.get('abs_diff') or metric.get('rel_diff') or metric.get('count_diff') or metric.get('day_diff'))} | "
                f"{metric['status']} |"
            )
    else:
        lines.append("No notable diffs.")

    lines.extend(
        [
            "",
            "## Drift Signals",
            "",
            f"- Leaderboard top-3 set equal: {summary['leaderboard_top3_set_equal']}",
            f"- Leaderboard top-3 order equal: {summary['leaderboard_top3_order_equal']}",
            f"- Source git SHA equal: {fmt_bool(source.get('git_sha_equal'))}",
            f"- yfinance version equal: {fmt_bool(source.get('yfinance_version_equal'))}",
            f"- Bar-set fingerprint: {fingerprints.get('status') or 'unavailable'} "
            f"({fingerprints.get('matched', 0)} matched, "
            f"{fingerprints.get('differing', 0)} differing)",
        ]
    )
    if fingerprints.get("missing_in_local") or fingerprints.get("missing_in_remote"):
        lines.append(
            f"- Fingerprint coverage gaps: missing local={len(fingerprints.get('missing_in_local') or [])}, "
            f"missing remote={len(fingerprints.get('missing_in_remote') or [])}"
        )
    return "\n".join(lines) + "\n"


def notable_diffs(row_diffs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for row in row_diffs:
        for diff in row["metric_diffs"]:
            items.append({"key": row["key"], "diff": diff})
    return sorted(items, key=lambda item: severity_rank(item["diff"]["status"]), reverse=True)


def severity_rank(status: str) -> int:
    return {PASS: 0, WARN: 1, FAIL: 2}.get(status, 0)


def format_leader(row: dict[str, Any]) -> str:
    if not row:
        return "-"
    return f"{row.get('strategy_cls')} / {row.get('symbol')} / sortino={fmt(row.get('sortino'))}"


def fmt(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def fmt_bool(value: Any) -> str:
    if value is None:
        return "unknown"
    return "yes" if bool(value) else "no"


def get_nested(row: dict[str, Any], dotted: str) -> Any:
    current: Any = row
    for part in dotted.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str):
        if value == "inf":
            return float("inf")
        try:
            value = float(value)
        except ValueError:
            return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(parsed) else parsed


def int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def relative_diff(local: float, remote: float) -> float:
    denominator = max(abs(local), abs(remote), 1e-12)
    if math.isinf(denominator):
        return 0.0 if local == remote else float("inf")
    return abs(local - remote) / denominator


def worst_status(statuses: Any) -> str:
    worst = PASS
    for status in statuses:
        if severity_rank(status) > severity_rank(worst):
            worst = status
    return worst


def distribution_delta(local: list[Any], remote: list[Any], field: str) -> dict[str, int]:
    keys = {str(item.get(field) or "") for item in local if isinstance(item, dict)}
    keys |= {str(item.get(field) or "") for item in remote if isinstance(item, dict)}
    out: dict[str, int] = {}
    for key in sorted(keys):
        local_count = sum(
            1 for item in local if isinstance(item, dict) and str(item.get(field) or "") == key
        )
        remote_count = sum(
            1 for item in remote if isinstance(item, dict) and str(item.get(field) or "") == key
        )
        if local_count != remote_count:
            out[key] = abs(local_count - remote_count)
    return out


def parse_date(value: str) -> datetime.date | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return datetime.strptime(value[:10], "%Y-%m-%d").date()
        except ValueError:
            return None


def _json_safe(value: Any) -> Any:
    if isinstance(value, float):
        if math.isnan(value):
            return None
        if math.isinf(value):
            return "inf" if value > 0 else "-inf"
        return value
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    return value


class UsageError(Exception):
    """Bad invocation."""


class InputReadError(Exception):
    """Input path could not be read."""


class SchemaError(Exception):
    """Input JSON did not match expected schema."""


class ReportWriteError(Exception):
    """Output report could not be written."""


if __name__ == "__main__":
    raise SystemExit(main())
