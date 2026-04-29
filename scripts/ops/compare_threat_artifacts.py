#!/usr/bin/env python3
"""Compare local and remote threat-refresh artifacts.

The comparator is read-only with respect to inputs. It writes paired JSON and
Markdown reports under ``--report-out`` so the threat-refresh shadow can soak
before the local LaunchAgent is retired.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import math
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.core.provenance import write_envelope_sidecar  # noqa: E402

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
STABLE_FIELDS = ("source", "source_type", "title", "url", "exploited")


@dataclass(frozen=True)
class Artifact:
    path: Path
    data: dict[str, Any]
    sha256: str

    @property
    def refreshed_at(self) -> str:
        return str(self.data.get("refreshed_at") or "")

    @property
    def source_count(self) -> int:
        value = self.data.get("source_count")
        if isinstance(value, int):
            return value
        return len(self.threats)

    @property
    def threats(self) -> list[dict[str, Any]]:
        threats = self.data.get("threats")
        return threats if isinstance(threats, list) else []

    def summary(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "refreshed_at": self.refreshed_at,
            "source_count": self.source_count,
            "threat_count": len(self.threats),
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class SnapshotCandidate:
    path: Path
    timestamp: datetime

    def summary(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "run_timestamp": iso_z(self.timestamp),
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
    inputs = parser.add_argument_group("input selection")
    inputs.add_argument("--local", type=Path, help="Local threat-refresh artifact JSON")
    inputs.add_argument("--remote", type=Path, help="Remote threat-refresh artifact JSON")
    inputs.add_argument(
        "--local-root",
        type=Path,
        help="Directory containing local runs/<YYYYMMDDTHHMMSSZ>/threats.json snapshots",
    )
    inputs.add_argument(
        "--remote-root",
        type=Path,
        help="Directory containing remote runs/<YYYYMMDDTHHMMSSZ>/threats.json snapshots",
    )
    parser.add_argument(
        "--max-skew-minutes",
        type=float,
        default=30.0,
        help="Maximum timestamp skew allowed when selecting nearest run snapshots",
    )
    parser.add_argument("--report-out", type=Path, default=Path("data/intelligence/shadow-reports"))
    parser.add_argument("--strict", action="store_true", help="Treat WARN verdicts as FAIL")
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--quiet", action="store_true")
    output.add_argument("--verbose", action="store_true")
    return parser


def compare_from_args(args: argparse.Namespace) -> dict[str, Any]:
    local_path, remote_path, selection = resolve_inputs(args)
    local = load_artifact(local_path)
    remote = load_artifact(remote_path)
    report = compare_artifacts(local=local, remote=remote, strict=args.strict, selection=selection)
    write_reports(report, args.report_out)
    return report


def compare_artifacts(
    *,
    local: Artifact,
    remote: Artifact,
    strict: bool = False,
    selection: dict[str, Any] | None = None,
) -> dict[str, Any]:
    compared_at = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    local_rows = index_threats(local.threats, "local")
    remote_rows = index_threats(remote.threats, "remote")
    local_ids = set(local_rows)
    remote_ids = set(remote_rows)
    common_ids = sorted(local_ids & remote_ids)
    missing_in_local = sorted(remote_ids - local_ids)
    missing_in_remote = sorted(local_ids - remote_ids)

    row_diffs = [
        compare_threat(canonical_id, local_rows[canonical_id], remote_rows[canonical_id])
        for canonical_id in common_ids
    ]
    counts = {
        PASS: sum(1 for row in row_diffs if row["verdict"] == PASS),
        WARN: sum(1 for row in row_diffs if row["verdict"] == WARN),
        FAIL: sum(1 for row in row_diffs if row["verdict"] == FAIL),
    }
    source_count_delta = abs(local.source_count - remote.source_count)
    verdict = run_verdict(
        row_counts=counts,
        source_count_delta=source_count_delta,
        missing_count=len(missing_in_local) + len(missing_in_remote),
        union_count=len(local_ids | remote_ids),
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
            "local": local.summary(),
            "remote": remote.summary(),
        },
        "summary": {
            "rows_compared": len(row_diffs),
            "rows_pass": counts[PASS],
            "rows_warn": counts[WARN],
            "rows_fail": counts[FAIL],
            "source_count_delta": source_count_delta,
            "missing_in_local": missing_in_local,
            "missing_in_remote": missing_in_remote,
        },
        "row_diffs": row_diffs,
    }
    if selection is not None:
        report["selection"] = selection
    return _json_safe(report)


def resolve_inputs(args: argparse.Namespace) -> tuple[Path, Path, dict[str, Any] | None]:
    has_direct = args.local is not None or args.remote is not None
    has_roots = args.local_root is not None or args.remote_root is not None
    if has_direct and has_roots:
        raise UsageError("use either --local/--remote or --local-root/--remote-root, not both")
    if has_direct:
        if args.local is None or args.remote is None:
            raise UsageError("--local and --remote must be provided together")
        return args.local, args.remote, None
    if args.local_root is None or args.remote_root is None:
        raise UsageError("provide --local/--remote or --local-root/--remote-root")
    if args.max_skew_minutes < 0:
        raise UsageError("--max-skew-minutes must be >= 0")

    local_candidates = discover_run_snapshots(args.local_root, "local")
    remote_candidates = discover_run_snapshots(args.remote_root, "remote")
    local, remote, skew_seconds = nearest_snapshot_pair(local_candidates, remote_candidates)
    max_skew_seconds = args.max_skew_minutes * 60
    if skew_seconds > max_skew_seconds:
        raise UsageError(
            "nearest run snapshots are "
            f"{skew_seconds:.0f}s apart, exceeding --max-skew-minutes={args.max_skew_minutes:g}"
        )
    selection = {
        "mode": "nearest_run_snapshot",
        "local_root": str(args.local_root),
        "remote_root": str(args.remote_root),
        "local": local.summary(),
        "remote": remote.summary(),
        "time_skew_seconds": skew_seconds,
        "max_skew_minutes": args.max_skew_minutes,
        "candidate_counts": {
            "local": len(local_candidates),
            "remote": len(remote_candidates),
        },
    }
    return local.path, remote.path, selection


def discover_run_snapshots(root: Path, label: str) -> list[SnapshotCandidate]:
    if not root.exists():
        raise UsageError(f"--{label}-root does not exist: {root}")
    if not root.is_dir():
        raise UsageError(f"--{label}-root must be a directory: {root}")
    try:
        paths = list(root.rglob("threats.json"))
    except OSError as exc:
        raise InputReadError(f"{root}: {exc}") from exc

    candidates = [
        SnapshotCandidate(path=path, timestamp=timestamp)
        for path in paths
        if (timestamp := parse_run_snapshot_timestamp(path)) is not None
    ]
    if not candidates:
        raise UsageError(f"--{label}-root has no runs/<timestamp>/threats.json snapshots: {root}")
    return sorted(candidates, key=lambda item: item.timestamp)


def parse_run_snapshot_timestamp(path: Path) -> datetime | None:
    if path.name != "threats.json" or path.parent.parent.name != "runs":
        return None
    try:
        return datetime.strptime(path.parent.name, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
    except ValueError:
        return None


def nearest_snapshot_pair(
    local_candidates: list[SnapshotCandidate],
    remote_candidates: list[SnapshotCandidate],
) -> tuple[SnapshotCandidate, SnapshotCandidate, float]:
    best: tuple[SnapshotCandidate, SnapshotCandidate, float] | None = None
    for local in local_candidates:
        for remote in remote_candidates:
            skew = abs((local.timestamp - remote.timestamp).total_seconds())
            if best is None or skew < best[2]:
                best = (local, remote, skew)
    if best is None:
        raise UsageError("no local/remote run snapshot candidates found")
    return best


def compare_threat(
    canonical_id: str,
    local: dict[str, Any],
    remote: dict[str, Any],
) -> dict[str, Any]:
    diffs: list[dict[str, Any]] = []
    for field in STABLE_FIELDS:
        diffs.append(compare_exact(field, local.get(field), remote.get(field)))
    diffs.extend(
        [
            compare_score(local.get("score"), remote.get("score")),
            compare_summary(local.get("summary"), remote.get("summary")),
            compare_published_at(local.get("published_at"), remote.get("published_at")),
            compare_tags(local.get("tags"), remote.get("tags")),
            compare_evidence(local.get("evidence"), remote.get("evidence")),
        ]
    )
    verdict = worst_status(diff["status"] for diff in diffs)
    return {
        "canonical_id": canonical_id,
        "verdict": verdict,
        "metric_diffs": [diff for diff in diffs if diff["status"] != PASS],
    }


def compare_exact(field: str, local: Any, remote: Any) -> dict[str, Any]:
    status = PASS if local == remote else FAIL
    return {"field": field, "local": local, "remote": remote, "status": status}


def compare_score(local_raw: Any, remote_raw: Any) -> dict[str, Any]:
    local = to_float(local_raw)
    remote = to_float(remote_raw)
    if local is None and remote is None:
        return {"field": "score", "local": local_raw, "remote": remote_raw, "status": PASS}
    if local is None or remote is None:
        return {"field": "score", "local": local_raw, "remote": remote_raw, "status": WARN}
    diff = abs(local - remote)
    status = PASS if diff <= 0.5 else WARN if diff <= 1.0 else FAIL
    return {
        "field": "score",
        "local": local,
        "remote": remote,
        "abs_diff": diff,
        "tolerance": 0.5,
        "status": status,
    }


def compare_summary(local_raw: Any, remote_raw: Any) -> dict[str, Any]:
    local = str(local_raw or "")
    remote = str(remote_raw or "")
    if local == remote:
        status = PASS
        similarity = 1.0
    else:
        similarity = difflib.SequenceMatcher(a=local, b=remote).ratio()
        status = PASS if similarity >= 0.95 else WARN if similarity >= 0.85 else FAIL
    return {
        "field": "summary",
        "local": local_raw,
        "remote": remote_raw,
        "similarity": similarity,
        "status": status,
    }


def compare_published_at(local_raw: Any, remote_raw: Any) -> dict[str, Any]:
    local_date = parse_date(local_raw)
    remote_date = parse_date(remote_raw)
    if local_date is None and remote_date is None:
        return {"field": "published_at", "local": local_raw, "remote": remote_raw, "status": PASS}
    if local_date is None or remote_date is None:
        return {"field": "published_at", "local": local_raw, "remote": remote_raw, "status": WARN}
    diff = abs((local_date - remote_date).days)
    status = PASS if diff == 0 else WARN if diff <= 1 else FAIL
    return {
        "field": "published_at",
        "local": str(local_date),
        "remote": str(remote_date),
        "day_diff": diff,
        "status": status,
    }


def compare_tags(local_raw: Any, remote_raw: Any) -> dict[str, Any]:
    local = {str(item) for item in local_raw} if isinstance(local_raw, list) else set()
    remote = {str(item) for item in remote_raw} if isinstance(remote_raw, list) else set()
    diff = sorted(local ^ remote)
    status = PASS if len(diff) <= 2 else WARN if len(diff) <= 4 else FAIL
    return {
        "field": "tags",
        "local": sorted(local),
        "remote": sorted(remote),
        "symmetric_diff": diff,
        "status": status,
    }


def compare_evidence(local_raw: Any, remote_raw: Any) -> dict[str, Any]:
    local = evidence_shape(local_raw)
    remote = evidence_shape(remote_raw)
    if local == remote:
        status = PASS
    else:
        count_diff = abs(len(local) - len(remote))
        status = WARN if count_diff <= 1 else FAIL
    return {
        "field": "evidence",
        "local": local,
        "remote": remote,
        "status": status,
    }


def evidence_shape(raw: Any) -> list[dict[str, str]]:
    rows = raw if isinstance(raw, list) else []
    shaped = []
    for item in rows:
        if isinstance(item, dict):
            shaped.append(
                {"label": str(item.get("label") or ""), "url": str(item.get("url") or "")}
            )
    return shaped


def run_verdict(
    *,
    row_counts: dict[str, int],
    source_count_delta: int,
    missing_count: int,
    union_count: int,
    strict: bool,
) -> str:
    if union_count == 0:
        verdict = WARN
    elif row_counts[FAIL] > 0 or source_count_delta > 2 or missing_count > 2:
        verdict = FAIL
    elif missing_count > 0 or row_counts[WARN] > 0:
        verdict = WARN
    else:
        verdict = PASS
    return FAIL if strict and verdict == WARN else verdict


def index_threats(threats: list[dict[str, Any]], label: str) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for idx, row in enumerate(threats):
        if not isinstance(row, dict):
            raise SchemaError(f"{label} threat row {idx} is not an object")
        canonical_id = str(row.get("canonical_id") or "").strip()
        if not canonical_id:
            raise SchemaError(f"{label} threat row {idx} missing canonical_id")
        if canonical_id in indexed:
            raise SchemaError(f"{label} duplicate canonical_id: {canonical_id}")
        indexed[canonical_id] = row
    return indexed


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
    if not isinstance(data.get("threats"), list):
        raise SchemaError(f"{path}: expected top-level threats list")
    return Artifact(path=path, data=data, sha256=hashlib.sha256(raw.encode("utf-8")).hexdigest())


def write_reports(report: dict[str, Any], out_dir: Path) -> None:
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        json_path = out_dir / f"threat-shadow-comparison-{stamp}.json"
        md_path = out_dir / f"threat-shadow-comparison-{stamp}.md"
        json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        md_path.write_text(render_markdown(report), encoding="utf-8")
        source_paths = _report_source_paths(report)
        metadata = {
            "comparison": "threat-shadow",
            "verdict": report.get("verdict"),
            "compared_at": report.get("compared_at"),
        }
        for path in (json_path, md_path):
            write_envelope_sidecar(
                path,
                generator="scripts.ops.compare_threat_artifacts",
                source_paths=source_paths,
                ttl_seconds=7 * 24 * 3600,
                metadata=metadata,
            )
    except OSError as exc:
        raise ReportWriteError(f"{out_dir}: {exc}") from exc


def _report_source_paths(report: dict[str, Any]) -> tuple[Path, ...]:
    inputs = report.get("inputs") if isinstance(report.get("inputs"), dict) else {}
    paths: list[Path] = []
    for side in ("local", "remote"):
        entry = inputs.get(side)
        if not isinstance(entry, dict):
            continue
        raw_path = entry.get("path")
        if raw_path:
            paths.append(Path(str(raw_path)))
    selection = report.get("selection")
    if isinstance(selection, dict):
        for side in ("local", "remote"):
            entry = selection.get(side)
            if not isinstance(entry, dict):
                continue
            raw_path = entry.get("path")
            if raw_path:
                paths.append(Path(str(raw_path)))
    deduped: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(path)
    return tuple(deduped)


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    inputs = report["inputs"]
    lines = [
        f"# Threat Shadow Comparison - {report['compared_at']}",
        "",
        f"**Verdict**: {report['verdict']}",
        f"**Local**: `{inputs['local']['path']}` ({inputs['local'].get('refreshed_at') or '-'}, {inputs['local']['threat_count']} threats)",
        f"**Remote**: `{inputs['remote']['path']}` ({inputs['remote'].get('refreshed_at') or '-'}, {inputs['remote']['threat_count']} threats)",
        "",
    ]
    selection = report.get("selection")
    if isinstance(selection, dict):
        lines.extend(
            [
                "## Snapshot Selection",
                "",
                f"- Mode: `{selection.get('mode', '-')}`",
                f"- Local run timestamp: `{selection.get('local', {}).get('run_timestamp', '-')}`",
                f"- Remote run timestamp: `{selection.get('remote', {}).get('run_timestamp', '-')}`",
                f"- Time skew seconds: `{selection.get('time_skew_seconds', '-')}`",
                f"- Candidate counts: local `{selection.get('candidate_counts', {}).get('local', '-')}`, remote `{selection.get('candidate_counts', {}).get('remote', '-')}`",
                "",
            ]
        )
    lines.extend(
        [
            "## Summary",
            "",
            f"- Compared: {summary['rows_compared']}",
            f"- PASS: {summary['rows_pass']}",
            f"- WARN: {summary['rows_warn']}",
            f"- FAIL: {summary['rows_fail']}",
            f"- Source count delta: {summary['source_count_delta']}",
            f"- Missing in local: {len(summary['missing_in_local'])}",
            f"- Missing in remote: {len(summary['missing_in_remote'])}",
            "",
            "## Missing IDs",
            "",
        ]
    )
    if summary["missing_in_local"] or summary["missing_in_remote"]:
        lines.append(f"- Missing in local: {', '.join(summary['missing_in_local']) or '-'}")
        lines.append(f"- Missing in remote: {', '.join(summary['missing_in_remote']) or '-'}")
    else:
        lines.append("No missing IDs.")

    lines.extend(["", "## Notable Diffs", ""])
    notable = notable_diffs(report["row_diffs"])
    if notable:
        lines.extend(["| ID | Field | Local | Remote | Verdict |", "|---|---|---|---|---|"])
        for item in notable[:15]:
            diff = item["diff"]
            lines.append(
                f"| {item['canonical_id']} | {diff['field']} | {fmt(diff.get('local'))} | "
                f"{fmt(diff.get('remote'))} | {diff['status']} |"
            )
    else:
        lines.append("No notable diffs.")
    return "\n".join(lines) + "\n"


def notable_diffs(row_diffs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for row in row_diffs:
        for diff in row["metric_diffs"]:
            items.append({"canonical_id": row["canonical_id"], "diff": diff})
    return sorted(items, key=lambda item: severity_rank(item["diff"]["status"]), reverse=True)


def severity_rank(status: str) -> int:
    return {PASS: 0, WARN: 1, FAIL: 2}.get(status, 0)


def worst_status(statuses: Any) -> str:
    worst = PASS
    for status in statuses:
        if severity_rank(status) > severity_rank(worst):
            worst = status
    return worst


def parse_date(value: Any) -> datetime.date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
        except ValueError:
            return None


def to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(parsed) else parsed


def fmt(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.6g}"
    text = json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else str(value)
    return text.replace("|", "\\|")


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


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
