#!/usr/bin/env python3
"""Sapphire Autonomous Factory — Repo Health Scanner.

Scans all registered repos for issues and outputs a structured report.
Designed to be called by Claude Dispatch tasks.

Usage:
    python3 scripts/factory/repo_scanner.py              # Full scan, JSON output
    python3 scripts/factory/repo_scanner.py --summary     # Human-readable summary
    python3 scripts/factory/repo_scanner.py --repo Sapphire  # Scan single repo
"""

from __future__ import annotations

import contextlib
import json
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

REPOS = {
    "Sapphire": Path.home() / "Code" / "Sapphire",
    "Project-Go-Forward": Path.home() / "Code" / "Project-Go-Forward",
    "regional-intel-workbench": Path.home() / "Code" / "regional-intel-workbench",
    "tradingview-mcp-v2": Path.home() / "Code" / "tradingview-mcp-v2",
    # tradingview-mcp, Cointracker, and claw-code were archived 2026-05-12.
}


@dataclass
class RepoHealth:
    """Health report for a single repo."""

    name: str
    path: str
    branch: str = ""
    uncommitted_count: int = 0
    lint_errors: int = 0
    lint_fixable: int = 0
    test_pass: int = 0
    test_fail: int = 0
    test_error: str = ""
    has_claude_md: bool = False
    last_commit: str = ""
    last_commit_age_hours: float = 0
    behind_upstream: int = 0
    issues: list[str] = field(default_factory=list)
    score: int = 100  # 100 = perfect, 0 = critical


def run_cmd(cmd: list[str], cwd: str, timeout: int = 30) -> str:
    """Run a command and return stdout."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, timeout=timeout)
        return r.stdout.strip()
    except Exception:
        return ""


def scan_repo(name: str, path: Path) -> RepoHealth:
    """Scan a single repo for health issues."""
    h = RepoHealth(name=name, path=str(path))
    p = str(path)

    if not path.exists():
        h.issues.append("REPO_MISSING")
        h.score = 0
        return h

    # Branch
    h.branch = run_cmd(["git", "branch", "--show-current"], p)

    # Uncommitted changes
    status = run_cmd(["git", "status", "--short"], p)
    h.uncommitted_count = len([l for l in status.splitlines() if l.strip()])
    if h.uncommitted_count > 0:
        h.issues.append(f"UNCOMMITTED:{h.uncommitted_count}")
        h.score -= min(20, h.uncommitted_count)

    # Last commit
    log = run_cmd(["git", "log", "--oneline", "-1", "--format=%H %s"], p)
    h.last_commit = log

    # Commit age
    ts = run_cmd(["git", "log", "-1", "--format=%aI"], p)
    if ts:
        try:
            commit_time = datetime.fromisoformat(ts)
            age = datetime.now(UTC) - commit_time
            h.last_commit_age_hours = age.total_seconds() / 3600
        except Exception:
            pass

    # CLAUDE.md
    h.has_claude_md = (path / "CLAUDE.md").exists()
    if not h.has_claude_md:
        h.issues.append("NO_CLAUDE_MD")
        h.score -= 10

    # Lint (Python repos)
    if (path / "pyproject.toml").exists() or any(path.glob("*.py")):
        lint_out = run_cmd(
            ["python3", "-m", "ruff", "check", "--select", "E,F,I", "--statistics", "."],
            p,
            timeout=60,
        )
        if lint_out:
            # Count total errors from last line
            lines = lint_out.strip().splitlines()
            total = 0
            for line in lines:
                parts = line.strip().split()
                if parts and parts[0].isdigit():
                    total += int(parts[0])
            h.lint_errors = total
            if total > 0:
                h.issues.append(f"LINT:{total}")
                h.score -= min(30, total // 50)

    # Tests (Python)
    test_dirs = [path / "tests", path / "test"]
    has_tests = any(d.exists() for d in test_dirs)
    if has_tests:
        test_out = run_cmd(
            ["python3", "-m", "pytest", "--tb=no", "-q", "--no-header", "."],
            p,
            timeout=120,
        )
        if test_out:
            for line in test_out.splitlines():
                if "passed" in line:
                    parts = line.split()
                    for i, part in enumerate(parts):
                        if part == "passed" and i > 0:
                            with contextlib.suppress(ValueError):
                                h.test_pass = int(parts[i - 1])
                        if part == "failed" and i > 0:
                            with contextlib.suppress(ValueError):
                                h.test_fail = int(parts[i - 1])
                if "error" in line.lower() and "collection" in line.lower():
                    h.test_error = line.strip()

            if h.test_fail > 0:
                h.issues.append(f"TEST_FAIL:{h.test_fail}")
                h.score -= h.test_fail * 10
            if h.test_error:
                h.issues.append("TEST_COLLECTION_ERROR")
                h.score -= 20
    elif (path / "pyproject.toml").exists():
        h.issues.append("NO_TESTS")
        h.score -= 15

    h.score = max(0, h.score)
    return h


def scan_all(repo_filter: str | None = None) -> dict:
    """Scan all repos and return structured report."""
    repos_to_scan = REPOS
    if repo_filter:
        repos_to_scan = {k: v for k, v in REPOS.items() if repo_filter.lower() in k.lower()}

    results = []
    for name, path in repos_to_scan.items():
        results.append(scan_repo(name, path))

    total_score = sum(r.score for r in results) // len(results) if results else 0

    return {
        "timestamp": datetime.now(UTC).isoformat(),
        "total_repos": len(results),
        "avg_score": total_score,
        "total_lint_errors": sum(r.lint_errors for r in results),
        "total_test_failures": sum(r.test_fail for r in results),
        "repos_with_issues": sum(1 for r in results if r.issues),
        "repos": [asdict(r) for r in results],
    }


def print_summary(report: dict) -> None:
    """Print human-readable summary."""
    print(f"\n{'=' * 60}")
    print("  SAPPHIRE FACTORY — Repo Health Report")
    print(f"  {report['timestamp']}")
    print(f"{'=' * 60}\n")
    print(
        f"  Avg Score: {report['avg_score']}/100  |  Lint: {report['total_lint_errors']}  |  Test Fails: {report['total_test_failures']}"
    )
    print(f"  Repos with issues: {report['repos_with_issues']}/{report['total_repos']}\n")

    for r in report["repos"]:
        icon = "🟢" if r["score"] >= 80 else "🟡" if r["score"] >= 50 else "🔴"
        issues_str = ", ".join(r["issues"][:3]) if r["issues"] else "clean"
        print(
            f"  {icon} {r['name']:30s} score={r['score']:3d}  branch={r['branch']:20s}  {issues_str}"
        )

    print(f"\n{'=' * 60}\n")


if __name__ == "__main__":
    repo_filter = None
    summary_mode = False

    for arg in sys.argv[1:]:
        if arg == "--summary":
            summary_mode = True
        elif arg.startswith("--repo"):
            pass
        else:
            repo_filter = arg

    if "--repo" in sys.argv:
        idx = sys.argv.index("--repo")
        if idx + 1 < len(sys.argv):
            repo_filter = sys.argv[idx + 1]

    report = scan_all(repo_filter)

    if summary_mode:
        print_summary(report)
    else:
        print(json.dumps(report, indent=2))
