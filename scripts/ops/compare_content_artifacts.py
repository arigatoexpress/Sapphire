#!/usr/bin/env python3
"""Compare local and remote content-engine artifacts.

The comparator is read-only with respect to inputs. It writes paired JSON and
Markdown reports under ``--report-out`` so the content-engine shadow can soak
before the local LaunchAgent is retired.
"""

from __future__ import annotations

import argparse
import hashlib
import json
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


@dataclass(frozen=True)
class DraftManifest:
    path: Path
    root: Path
    data: dict[str, Any]
    sha256: str

    @property
    def kind(self) -> str:
        return str(self.data.get("report", {}).get("kind") or "")

    @property
    def title(self) -> str:
        return str(self.data.get("report", {}).get("title") or "")

    @property
    def published_at(self) -> str:
        return str(self.data.get("published_at") or "")

    @property
    def renderings(self) -> dict[str, Any]:
        renderings = self.data.get("renderings")
        return renderings if isinstance(renderings, dict) else {}

    @property
    def sources(self) -> list[str]:
        sources = self.data.get("report", {}).get("sources")
        return [str(item) for item in sources] if isinstance(sources, list) else []

    @property
    def tags(self) -> list[str]:
        tags = self.data.get("report", {}).get("tags")
        return [str(item) for item in tags] if isinstance(tags, list) else []

    @property
    def body(self) -> str:
        return str(self.data.get("report", {}).get("body") or "")

    def summary(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "kind": self.kind,
            "title": self.title,
            "published_at": self.published_at,
            "rendering_count": len(self.renderings),
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
    parser.add_argument("--local-root", type=Path, required=True)
    parser.add_argument("--remote-root", type=Path, required=True)
    parser.add_argument("--report-out", type=Path, default=Path("data/content/shadow-reports"))
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat WARN verdicts as FAIL after the soak gate is mature.",
    )
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--quiet", action="store_true")
    output.add_argument("--verbose", action="store_true")
    return parser


def compare_from_args(args: argparse.Namespace) -> dict[str, Any]:
    local = latest_manifests_by_kind(args.local_root)
    remote = latest_manifests_by_kind(args.remote_root)
    report = compare_manifest_sets(local=local, remote=remote, strict=args.strict)
    write_reports(report, args.report_out)
    return report


def latest_manifests_by_kind(root: Path) -> dict[str, DraftManifest]:
    manifests = discover_manifests(root)
    if not manifests:
        raise UsageError(f"no content draft manifests found under {root}")
    latest: dict[str, DraftManifest] = {}
    for manifest in manifests:
        previous = latest.get(manifest.kind)
        if previous is None or manifest_sort_key(manifest) > manifest_sort_key(previous):
            latest[manifest.kind] = manifest
    return latest


def discover_manifests(root: Path) -> list[DraftManifest]:
    if not root.exists():
        raise UsageError(f"root does not exist: {root}")
    if not root.is_dir():
        raise UsageError(f"root must be a directory: {root}")

    candidates: set[Path] = set()
    direct = root / "data" / "content" / "drafts"
    if direct.exists():
        candidates.update(direct.glob("*.json"))
    if root.name == "drafts":
        candidates.update(root.glob("*.json"))
    content_direct = root / "drafts"
    if root.name == "content" and content_direct.exists():
        candidates.update(content_direct.glob("*.json"))
    candidates.update(root.rglob("data/content/drafts/*.json"))

    return [load_manifest(path, root=root) for path in sorted(candidates)]


def load_manifest(path: Path, *, root: Path) -> DraftManifest:
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
    report = data.get("report")
    if not isinstance(report, dict):
        raise SchemaError(f"{path}: expected top-level report object")
    kind = str(report.get("kind") or "").strip()
    if not kind:
        raise SchemaError(f"{path}: report.kind is required")
    renderings = data.get("renderings")
    if not isinstance(renderings, dict):
        raise SchemaError(f"{path}: expected top-level renderings object")
    return DraftManifest(
        path=path,
        root=root,
        data=data,
        sha256=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
    )


def manifest_sort_key(manifest: DraftManifest) -> tuple[str, str]:
    return (filename_stamp(manifest.path), manifest.published_at)


def filename_stamp(path: Path) -> str:
    parts = path.stem.split("_", 2)
    if len(parts) < 2:
        return ""
    return "_".join(parts[:2])


def compare_manifest_sets(
    *,
    local: dict[str, DraftManifest],
    remote: dict[str, DraftManifest],
    strict: bool = False,
) -> dict[str, Any]:
    compared_at = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    local_kinds = set(local)
    remote_kinds = set(remote)
    common_kinds = sorted(local_kinds & remote_kinds)
    missing_in_local = sorted(remote_kinds - local_kinds)
    missing_in_remote = sorted(local_kinds - remote_kinds)
    kind_diffs = [
        compare_kind(kind, local[kind], remote[kind])
        for kind in common_kinds
    ]
    counts = {
        PASS: sum(1 for row in kind_diffs if row["verdict"] == PASS),
        WARN: sum(1 for row in kind_diffs if row["verdict"] == WARN),
        FAIL: sum(1 for row in kind_diffs if row["verdict"] == FAIL),
    }
    verdict = run_verdict(
        row_counts=counts,
        missing_count=len(missing_in_local) + len(missing_in_remote),
        common_count=len(common_kinds),
        strict=strict,
    )
    exit_code = {PASS: EXIT_PASS, WARN: EXIT_WARN, FAIL: EXIT_FAIL}[verdict]
    return {
        "schema_version": 1,
        "tool_version": TOOL_VERSION,
        "compared_at": compared_at,
        "strict": strict,
        "verdict": verdict,
        "exit_code": exit_code,
        "inputs": {
            "local": {kind: manifest.summary() for kind, manifest in sorted(local.items())},
            "remote": {kind: manifest.summary() for kind, manifest in sorted(remote.items())},
        },
        "summary": {
            "rows_compared": len(kind_diffs),
            "rows_pass": counts[PASS],
            "rows_warn": counts[WARN],
            "rows_fail": counts[FAIL],
            "missing_in_local": missing_in_local,
            "missing_in_remote": missing_in_remote,
        },
        "kind_diffs": kind_diffs,
    }


def compare_kind(kind: str, local: DraftManifest, remote: DraftManifest) -> dict[str, Any]:
    metric_diffs: list[dict[str, Any]] = []
    metric_diffs.extend(compare_title(local, remote))
    metric_diffs.extend(compare_list_field("sources", local.sources, remote.sources))
    metric_diffs.extend(compare_list_field("tags", local.tags, remote.tags))
    metric_diffs.extend(compare_body(local, remote))
    metric_diffs.extend(compare_renderings(local, remote))
    verdict = worst_status(diff["status"] for diff in metric_diffs)
    return {
        "kind": kind,
        "verdict": verdict,
        "metric_diffs": [diff for diff in metric_diffs if diff["status"] != PASS],
    }


def compare_title(local: DraftManifest, remote: DraftManifest) -> list[dict[str, Any]]:
    # Titles usually contain dates. Normalize digits so same report family does not fail on
    # local-vs-remote clock skew.
    local_norm = normalize_title(local.title)
    remote_norm = normalize_title(remote.title)
    status = PASS if local_norm == remote_norm else WARN
    return [{
        "field": "title",
        "local": local.title,
        "remote": remote.title,
        "status": status,
    }]


def normalize_title(value: str) -> str:
    return "".join("#" if ch.isdigit() else ch for ch in value)


def compare_list_field(field: str, local: list[str], remote: list[str]) -> list[dict[str, Any]]:
    local_set = set(local)
    remote_set = set(remote)
    symmetric = sorted(local_set ^ remote_set)
    status = PASS if not symmetric else WARN
    return [{
        "field": field,
        "local": sorted(local_set),
        "remote": sorted(remote_set),
        "symmetric_diff": symmetric,
        "status": status,
    }]


def compare_body(local: DraftManifest, remote: DraftManifest) -> list[dict[str, Any]]:
    local_len = len(local.body)
    remote_len = len(remote.body)
    if local.body == remote.body:
        status = PASS
        delta_ratio = 0.0
    else:
        largest = max(local_len, remote_len, 1)
        delta_ratio = abs(local_len - remote_len) / largest
        status = WARN if delta_ratio <= 0.5 else FAIL
    return [{
        "field": "body",
        "local_chars": local_len,
        "remote_chars": remote_len,
        "char_delta_ratio": round(delta_ratio, 4),
        "status": status,
    }]


def compare_renderings(local: DraftManifest, remote: DraftManifest) -> list[dict[str, Any]]:
    diffs: list[dict[str, Any]] = []
    local_platforms = set(local.renderings)
    remote_platforms = set(remote.renderings)
    missing_platforms = sorted(local_platforms ^ remote_platforms)
    diffs.append({
        "field": "rendering_platforms",
        "local": sorted(local_platforms),
        "remote": sorted(remote_platforms),
        "symmetric_diff": missing_platforms,
        "status": PASS if not missing_platforms else FAIL,
    })
    for platform in sorted(local_platforms & remote_platforms):
        diffs.extend(compare_rendering(platform, local, remote))
    return diffs


def compare_rendering(
    platform: str,
    local: DraftManifest,
    remote: DraftManifest,
) -> list[dict[str, Any]]:
    local_rendering = local.renderings.get(platform) if isinstance(local.renderings, dict) else {}
    remote_rendering = remote.renderings.get(platform) if isinstance(remote.renderings, dict) else {}
    local_quality = local_rendering.get("quality", {}) if isinstance(local_rendering, dict) else {}
    remote_quality = remote_rendering.get("quality", {}) if isinstance(remote_rendering, dict) else {}
    local_passed = bool(local_quality.get("passed"))
    remote_passed = bool(remote_quality.get("passed"))
    if local_passed and remote_passed:
        quality_status = PASS
    elif local_passed and not remote_passed:
        quality_status = FAIL
    else:
        quality_status = WARN

    diffs = [{
        "field": f"{platform}.quality",
        "local_passed": local_passed,
        "remote_passed": remote_passed,
        "local_reasons": local_quality.get("reasons") or [],
        "remote_reasons": remote_quality.get("reasons") or [],
        "status": quality_status,
    }]
    diffs.append(compare_rendered_file(platform, local, remote))
    return diffs


def compare_rendered_file(platform: str, local: DraftManifest, remote: DraftManifest) -> dict[str, Any]:
    local_path = rendering_path(local, platform)
    remote_path = rendering_path(remote, platform)
    if local_path is None or remote_path is None:
        return {
            "field": f"{platform}.file",
            "local": str(local_path) if local_path else "",
            "remote": str(remote_path) if remote_path else "",
            "status": FAIL,
        }
    local_hash, local_size = file_hash_and_size(local_path)
    remote_hash, remote_size = file_hash_and_size(remote_path)
    if local_hash is None or remote_hash is None:
        status = FAIL
    elif local_hash == remote_hash:
        status = PASS
    else:
        largest = max(local_size or 0, remote_size or 0, 1)
        delta_ratio = abs((local_size or 0) - (remote_size or 0)) / largest
        status = WARN if delta_ratio <= 0.5 else FAIL
    return {
        "field": f"{platform}.file",
        "local": str(local_path),
        "remote": str(remote_path),
        "local_size": local_size,
        "remote_size": remote_size,
        "same_sha256": local_hash == remote_hash if local_hash and remote_hash else False,
        "status": status,
    }


def rendering_path(manifest: DraftManifest, platform: str) -> Path | None:
    rendering = manifest.renderings.get(platform)
    if not isinstance(rendering, dict):
        return None
    raw_path = rendering.get("path")
    if not raw_path:
        return None
    path = Path(str(raw_path))
    candidates = [
        manifest.root / path,
        manifest.path.parents[3] / path if len(manifest.path.parents) >= 4 else manifest.root / path,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def file_hash_and_size(path: Path) -> tuple[str | None, int | None]:
    try:
        raw = path.read_bytes()
    except OSError:
        return None, None
    return hashlib.sha256(raw).hexdigest(), len(raw)


def run_verdict(
    *,
    row_counts: dict[str, int],
    missing_count: int,
    common_count: int,
    strict: bool,
) -> str:
    if common_count == 0 or row_counts[FAIL] > 0 or missing_count > 0:
        verdict = FAIL
    elif row_counts[WARN] > 0:
        verdict = WARN
    else:
        verdict = PASS
    return FAIL if strict and verdict == WARN else verdict


def worst_status(statuses: Any) -> str:
    values = set(statuses)
    if FAIL in values:
        return FAIL
    if WARN in values:
        return WARN
    return PASS


def write_reports(report: dict[str, Any], out_dir: Path) -> None:
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        (out_dir / f"content-shadow-comparison-{stamp}.json").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )
        (out_dir / f"content-shadow-comparison-{stamp}.md").write_text(
            render_markdown(report), encoding="utf-8"
        )
    except OSError as exc:
        raise ReportWriteError(f"{out_dir}: {exc}") from exc


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        f"# Content-Engine Shadow Comparison - {report['compared_at']}",
        "",
        f"**Verdict**: {report['verdict']}",
        "",
        "## Summary",
        "",
        f"- Compared report kinds: {summary['rows_compared']}",
        f"- PASS: {summary['rows_pass']}",
        f"- WARN: {summary['rows_warn']}",
        f"- FAIL: {summary['rows_fail']}",
        f"- Missing in local: {len(summary['missing_in_local'])}",
        f"- Missing in remote: {len(summary['missing_in_remote'])}",
        "",
        "## Report Kinds",
        "",
        "| Kind | Verdict | Notes |",
        "|---|---|---|",
    ]
    for row in report["kind_diffs"]:
        notes = ", ".join(diff["field"] for diff in row["metric_diffs"]) or "-"
        lines.append(f"| {row['kind']} | {row['verdict']} | {notes} |")
    if summary["missing_in_local"] or summary["missing_in_remote"]:
        lines.extend([
            "",
            "## Missing Kinds",
            "",
            f"- Missing in local: {', '.join(summary['missing_in_local']) or '-'}",
            f"- Missing in remote: {', '.join(summary['missing_in_remote']) or '-'}",
        ])
    lines.append("")
    return "\n".join(lines)


class UsageError(Exception):
    pass


class InputReadError(Exception):
    pass


class SchemaError(Exception):
    pass


class ReportWriteError(Exception):
    pass


if __name__ == "__main__":
    raise SystemExit(main())
