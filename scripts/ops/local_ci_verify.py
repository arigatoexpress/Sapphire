#!/usr/bin/env python3
"""Run the Sapphire CI suite locally against a PR or the working tree.

The agent runtime calls this when GitHub Actions is unavailable (billing
block or quota exhaustion) and we need a documented "local CI green"
signal before admin-merging a PR.

Usage::

    # Verify a specific PR by number
    python3 scripts/ops/local_ci_verify.py --pr 230

    # Verify the current working tree
    python3 scripts/ops/local_ci_verify.py

    # Quiet mode for use in scripts
    python3 scripts/ops/local_ci_verify.py --pr 230 --quiet

    # Skip the plugin tests (faster iteration)
    python3 scripts/ops/local_ci_verify.py --skip-plugin

Exit codes::

    0  - all checks PASS
    10 - one or more checks WARN (currently unused; reserved)
    20 - one or more checks FAIL
    64 - usage error
    74 - I/O error fetching the PR

The script writes a JSON report to
``data/ci/local-ci-verify-<stamp>.json`` (gitignored under ``data/``)
and prints a short Markdown summary to stdout unless ``--quiet`` is set.

Independent of GitHub Actions billing — uses the operator's local
``/usr/local/bin/python3`` (Mac) or ``$PYTHON3`` and ``ruff``.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

EXIT_PASS = 0
EXIT_WARN = 10
EXIT_FAIL = 20
EX_USAGE = 64
EX_IOERR = 74

REPO_ROOT = Path(__file__).resolve().parents[2]


def _resolve_python() -> str:
    """Resolve the Python interpreter that has the repo's test deps.

    Mac order: $PYTHON3 -> /usr/local/bin/python3 (matches the Makefile and
    CLAUDE.md guidance) -> shutil.which("python3"). The Homebrew 3.14
    install at /opt/homebrew/bin/python3 is missing the repo's pytest deps
    and breaks collection, so it's a last resort only.
    """
    if (env := os.environ.get("PYTHON3")):
        return env
    if Path("/usr/local/bin/python3").exists():
        return "/usr/local/bin/python3"
    return shutil.which("python3") or "python3"


DEFAULT_PYTHON = _resolve_python()


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return EXIT_PASS if exc.code == 0 else EX_USAGE

    if not REPO_ROOT.joinpath(".git").exists():
        print(f"error: {REPO_ROOT} is not a git repo", file=sys.stderr)
        return EX_USAGE

    starting_branch = run_capture(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=REPO_ROOT).strip()
    fetched_branch: str | None = None

    try:
        if args.pr is not None:
            fetched_branch = checkout_pr(args.pr)
        report = run_checks(args)
    except FetchError as exc:
        print(f"error fetching PR: {exc}", file=sys.stderr)
        return EX_IOERR
    finally:
        if fetched_branch:
            try:
                run(["git", "checkout", starting_branch], cwd=REPO_ROOT, check=False)
                run(["git", "branch", "-D", fetched_branch], cwd=REPO_ROOT, check=False)
            except Exception:
                pass

    write_report(report, args)
    if not args.quiet:
        print(render_markdown(report))
    return int(report["exit_code"])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pr", type=int, help="GitHub PR number to fetch and verify.")
    parser.add_argument("--skip-plugin", action="store_true", help="Skip the plugin test suite.")
    parser.add_argument("--skip-registry", action="store_true", help="Skip the tool registry validator.")
    parser.add_argument(
        "--report-out",
        type=Path,
        default=REPO_ROOT / "data" / "ci",
        help="Directory for the JSON report (default: data/ci/, gitignored).",
    )
    out = parser.add_mutually_exclusive_group()
    out.add_argument("--quiet", action="store_true")
    out.add_argument("--verbose", action="store_true")
    return parser


def checkout_pr(pr_number: int) -> str:
    """Fetch refs/pull/<n>/head into a local branch and check it out."""
    branch = f"local_ci/pr_{pr_number}"
    try:
        run(["git", "fetch", "origin", f"pull/{pr_number}/head:{branch}"], cwd=REPO_ROOT)
        run(["git", "checkout", branch], cwd=REPO_ROOT)
    except subprocess.CalledProcessError as exc:
        raise FetchError(f"git failed: {exc}") from exc
    return branch


def run_checks(args: argparse.Namespace) -> dict[str, Any]:
    started_at = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    head = run_capture(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT).strip()
    branch = run_capture(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=REPO_ROOT).strip()

    checks: list[dict[str, Any]] = []
    checks.append(check_lint())
    checks.append(check_unit_tests())
    if not args.skip_plugin:
        checks.append(check_plugin_tests())
    if not args.skip_registry:
        checks.append(check_tool_registry())
    checks.append(check_gitleaks())  # runs only if gitleaks is on PATH

    statuses = [c["status"] for c in checks]
    if "FAIL" in statuses:
        verdict, exit_code = "FAIL", EXIT_FAIL
    elif "WARN" in statuses:
        verdict, exit_code = "WARN", EXIT_WARN
    else:
        verdict, exit_code = "PASS", EXIT_PASS

    return {
        "schema_version": 1,
        "started_at": started_at,
        "completed_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "head": head,
        "branch": branch,
        "verdict": verdict,
        "exit_code": exit_code,
        "checks": checks,
    }


def check_lint() -> dict[str, Any]:
    if shutil.which("ruff") is None:
        return _skipped("ruff", "ruff not on PATH")
    return _run_named("ruff (lint)", ["ruff", "check", "."])


def check_unit_tests() -> dict[str, Any]:
    return _run_named(
        "pytest (tests/unit)",
        [DEFAULT_PYTHON, "-m", "pytest", "tests/unit/", "--tb=no", "-q"],
    )


def check_plugin_tests() -> dict[str, Any]:
    return _run_named(
        "pytest (plugin)",
        [DEFAULT_PYTHON, "-m", "pytest", "plugins/claw-sapphire/tests/", "--tb=no", "-q"],
    )


def check_tool_registry() -> dict[str, Any]:
    return _run_named(
        "tool registry invariants",
        [DEFAULT_PYTHON, "scripts/validate_tool_registry.py"],
    )


def check_gitleaks() -> dict[str, Any]:
    if shutil.which("gitleaks") is None:
        return _skipped("gitleaks (secrets)", "gitleaks not on PATH")
    return _run_named("gitleaks (secrets)", ["gitleaks", "detect", "--no-banner", "-v"])


def _run_named(name: str, cmd: list[str]) -> dict[str, Any]:
    started = datetime.now(UTC)
    try:
        result = subprocess.run(
            cmd,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        return {
            "name": name,
            "status": "FAIL",
            "exit_code": -1,
            "duration_sec": 0.0,
            "stdout_tail": "",
            "stderr_tail": str(exc),
        }
    duration = (datetime.now(UTC) - started).total_seconds()
    status = "PASS" if result.returncode == 0 else "FAIL"
    return {
        "name": name,
        "status": status,
        "exit_code": result.returncode,
        "duration_sec": round(duration, 2),
        "stdout_tail": _tail(result.stdout, 40),
        "stderr_tail": _tail(result.stderr, 20),
    }


def _skipped(name: str, reason: str) -> dict[str, Any]:
    return {
        "name": name,
        "status": "WARN",
        "exit_code": -1,
        "duration_sec": 0.0,
        "stdout_tail": "",
        "stderr_tail": f"skipped: {reason}",
    }


def _tail(text: str, n: int) -> str:
    if not text:
        return ""
    return "\n".join(text.splitlines()[-n:])


def write_report(report: dict[str, Any], args: argparse.Namespace) -> None:
    out_dir: Path = args.report_out
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        return
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = out_dir / f"local-ci-verify-{stamp}.json"
    try:
        path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# Local CI Verify — {report['completed_at']}",
        "",
        f"**Verdict**: {report['verdict']}",
        f"**Branch**: {report['branch']}",
        f"**HEAD**: {report['head'][:8]}",
        "",
        "| Check | Status | Exit | Duration |",
        "|---|---|---:|---:|",
    ]
    for c in report["checks"]:
        lines.append(
            f"| {c['name']} | {c['status']} | {c['exit_code']} | {c['duration_sec']}s |"
        )
    fails = [c for c in report["checks"] if c["status"] == "FAIL"]
    if fails:
        lines.extend(["", "## Failures", ""])
        for c in fails:
            lines.append(f"### {c['name']}")
            if c["stdout_tail"]:
                lines.append("```")
                lines.append(c["stdout_tail"])
                lines.append("```")
            if c["stderr_tail"]:
                lines.append("**stderr (tail)**:")
                lines.append("```")
                lines.append(c["stderr_tail"])
                lines.append("```")
    return "\n".join(lines)


def run(cmd: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, check=check, capture_output=True, text=True)


def run_capture(cmd: list[str], cwd: Path) -> str:
    return subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True).stdout


class FetchError(Exception):
    pass


if __name__ == "__main__":
    raise SystemExit(main())
