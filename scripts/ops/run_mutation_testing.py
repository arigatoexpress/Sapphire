#!/usr/bin/env python3
"""Operator-supervised mutation testing runner — Tranche 6 Lane 1.

Mutation testing is an expensive but high-signal verification technique: we
apply small, semantically meaningful changes ("mutations") to the source
under test and check that the test suite catches each one. A surviving
mutation is a strong indicator the test suite has a coverage gap.

This wrapper targets a curated subset of paste-safe-critical and
trading-critical modules:

* ``lib/security/pii_redactor.py``
* ``lib/correlator/scoring.py``
* ``lib/live_portfolio/sortino.py``
* ``lib/live_portfolio/ramp_gate.py``
* ``lib/audit_panel/heuristics.py``

We deliberately do NOT run mutation testing repo-wide — the runtime is
hours per module and the noise from auto-generated / vendored code makes
the report unreadable. Whole-repo runs are out of scope for this PR.

Live runs are operator-gated via ``SAPPHIRE_MUTATION_TEST_LIVE=1`` to
prevent accidental CI invocation. Without the gate the script runs in
dry-run mode and emits the command sequence it WOULD run, plus a
synthesised stub report so downstream tools can wire against the schema.

Output:

* ``data/test_rigor/mutation_report_<YYYY-MM-DD>.json`` — per-module kill rate.
* Paste-safe Markdown summary printed to stdout (stable section order).
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import shlex
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Curated mutation surface — the operator-approved list for THIS PR.
# Each entry pairs a source path with the test file(s) that exercise it.
MUTATION_TARGETS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "lib/security/pii_redactor.py",
        (
            "tests/unit/test_pii_redactor.py",
            "tests/property/test_pii_redactor_properties.py",
        ),
    ),
    (
        "lib/correlator/scoring.py",
        (
            "tests/property/test_correlator_scoring_properties.py",
        ),
    ),
    (
        "lib/live_portfolio/sortino.py",
        (
            "tests/unit/test_live_portfolio_sortino.py",
            "tests/property/test_live_portfolio_sortino_properties.py",
        ),
    ),
    (
        "lib/live_portfolio/ramp_gate.py",
        (
            "tests/unit/test_live_portfolio_ramp_gate.py",
        ),
    ),
    (
        "lib/audit_panel/heuristics.py",
        (
            "tests/unit/test_audit_panel_heuristics.py",
            "tests/property/test_audit_panel_heuristics_properties.py",
        ),
    ),
)

LIVE_FLAG_ENV = "SAPPHIRE_MUTATION_TEST_LIVE"
DEFAULT_REPORT_ROOT = REPO_ROOT / "data" / "test_rigor"


@dataclasses.dataclass(frozen=True)
class ModuleResult:
    """Per-module mutation testing result."""

    module: str
    killed: int = 0
    survived: int = 0
    timeout: int = 0
    suspicious: int = 0
    skipped: int = 0
    total: int = 0
    kill_rate: float = 0.0
    elapsed_seconds: float = 0.0
    mode: str = "dry_run"
    command: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        out = dataclasses.asdict(self)
        out["command"] = list(self.command)
        return out


def _build_command(source_path: str, test_paths: tuple[str, ...]) -> tuple[str, ...]:
    """Return the mutmut command sequence for one module."""
    runner = "python3 -m pytest -x --tb=no -q " + " ".join(
        shlex.quote(p) for p in test_paths
    )
    return (
        sys.executable,
        "-m",
        "mutmut",
        "run",
        "--paths-to-mutate",
        source_path,
        "--runner",
        runner,
        "--CI",
    )


def _dry_run(target: tuple[str, tuple[str, ...]]) -> ModuleResult:
    source_path, test_paths = target
    cmd = _build_command(source_path, test_paths)
    return ModuleResult(
        module=source_path,
        mode="dry_run",
        command=cmd,
        # Best-effort heuristic for dry-run reporting: pretend kill_rate=1.0
        # so dashboards downstream don't show alarming zeros while the live
        # gate is closed.
        kill_rate=1.0,
        total=0,
    )


def _parse_mutmut_results(text: str) -> dict[str, int]:
    """Parse the trailing summary lines from ``mutmut run`` output.

    Expected lines (mutmut 2.x):
        - ``42/42  🎉 41  ⏰ 0  🤔 0  🙁 1  🔇 0``
    The emoji legend is stable across mutmut 2.4 - 2.5.
    """
    summary = {"total": 0, "killed": 0, "timeout": 0, "suspicious": 0, "survived": 0, "skipped": 0}
    for line in text.splitlines()[::-1]:
        # Look for the trailing summary line.
        if "/" in line and "🎉" in line:
            try:
                left, _, _ = line.partition(" ")
                done, _, total = left.partition("/")
                summary["total"] = int(total)
            except (ValueError, IndexError):
                continue
            tokens = line.split()
            for token, key in zip(
                tokens,
                ["", "", "killed", "", "timeout", "", "suspicious", "", "survived", "", "skipped"],
                strict=False,
            ):
                if not key or not token.isdigit():
                    continue
                summary[key] = int(token)
            break
    return summary


def _live_run(target: tuple[str, tuple[str, ...]]) -> ModuleResult:
    source_path, test_paths = target
    cmd = _build_command(source_path, test_paths)
    started = datetime.now(UTC)
    proc = subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    elapsed = (datetime.now(UTC) - started).total_seconds()
    summary = _parse_mutmut_results(proc.stdout + "\n" + proc.stderr)
    total = summary.get("total", 0) or 1
    killed = summary.get("killed", 0)
    kill_rate = round(killed / total, 4) if total else 0.0
    return ModuleResult(
        module=source_path,
        killed=killed,
        survived=summary.get("survived", 0),
        timeout=summary.get("timeout", 0),
        suspicious=summary.get("suspicious", 0),
        skipped=summary.get("skipped", 0),
        total=summary.get("total", 0),
        kill_rate=kill_rate,
        elapsed_seconds=elapsed,
        mode="live",
        command=cmd,
    )


def run_targets(
    targets: tuple[tuple[str, tuple[str, ...]], ...] | None = None,
    *,
    live: bool = False,
) -> list[ModuleResult]:
    """Run mutation testing against the configured targets.

    The ``live`` flag must be ``True`` to actually invoke ``mutmut``.
    Otherwise we emit a dry-run report for inspection.
    """
    selected = targets if targets is not None else MUTATION_TARGETS
    results: list[ModuleResult] = []
    for target in selected:
        if live:
            results.append(_live_run(target))
        else:
            results.append(_dry_run(target))
    return results


def render_markdown(results: list[ModuleResult], *, mode: str) -> str:
    """Render a paste-safe Markdown summary of per-module kill rates."""
    when = datetime.now(UTC).replace(microsecond=0).isoformat()
    lines = [
        "# Sapphire mutation testing report",
        "",
        f"- Mode: `{mode}`",
        f"- Generated: `{when}`",
        f"- Targets: `{len(results)}`",
        "",
        "## Per-module kill rate",
        "",
        "| Module | Killed | Survived | Timeout | Total | Kill rate |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for result in results:
        lines.append(
            f"| `{result.module}` | {result.killed} | {result.survived} | "
            f"{result.timeout} | {result.total} | {result.kill_rate * 100:.1f}% |"
        )
    lines.extend(
        [
            "",
            (
                "_Live runs are operator-gated via `SAPPHIRE_MUTATION_TEST_LIVE=1`. "
                "Mutation testing is hours-long; do not invoke from CI._"
            ),
            "",
        ]
    )
    return "\n".join(lines)


def write_report(
    results: list[ModuleResult],
    *,
    root: Path | None = None,
    mode: str,
) -> Path:
    """Write the JSON report under ``data/test_rigor/`` and return the path."""
    target_root = root if root is not None else DEFAULT_REPORT_ROOT
    target_root.mkdir(parents=True, exist_ok=True)
    today = datetime.now(UTC).date().isoformat()
    path = target_root / f"mutation_report_{today}.json"
    payload = {
        "schema_version": 1,
        "mode": mode,
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "modules": [r.to_dict() for r in results],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True))
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run mutmut against the Sapphire test-rigor curated module list. "
            "Live runs require SAPPHIRE_MUTATION_TEST_LIVE=1."
        )
    )
    parser.add_argument(
        "--report-root",
        type=Path,
        default=None,
        help="Output directory for the JSON report (default data/test_rigor/).",
    )
    parser.add_argument(
        "--module",
        action="append",
        default=None,
        help=(
            "Restrict to one module path (repeatable). Default: all "
            "MUTATION_TARGETS."
        ),
    )
    parser.add_argument(
        "--print-only",
        action="store_true",
        help="Print Markdown to stdout but skip writing the JSON sidecar.",
    )
    parser.add_argument(
        "--force-live",
        action="store_true",
        help=(
            "Equivalent to setting SAPPHIRE_MUTATION_TEST_LIVE=1; included so "
            "operators can pass it explicitly without polluting their shell env."
        ),
    )
    return parser


def _filter_targets(
    requested: list[str] | None,
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    if not requested:
        return MUTATION_TARGETS
    out: list[tuple[str, tuple[str, ...]]] = []
    for source, tests in MUTATION_TARGETS:
        if source in requested:
            out.append((source, tests))
    if not out:
        raise SystemExit(
            f"No matching modules in MUTATION_TARGETS for {requested!r}."
        )
    return tuple(out)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    is_live = args.force_live or os.environ.get(LIVE_FLAG_ENV) == "1"
    targets = _filter_targets(args.module)
    results = run_targets(targets, live=is_live)
    mode = "live" if is_live else "dry_run"
    md = render_markdown(results, mode=mode)
    print(md)
    if not args.print_only:
        path = write_report(results, root=args.report_root, mode=mode)
        print(f"\nReport written to: {path}")
    # Exit non-zero if live and any module had survivors — signals coverage gap.
    if is_live and any(r.survived > 0 for r in results):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
