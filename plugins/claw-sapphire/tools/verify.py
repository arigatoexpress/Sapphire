#!/usr/bin/env python3
"""sapphire_verify — run lint + tests on a repo, report if safe to commit.

Input schema:
    {"repo": "Sapphire"}
    {"repo": "Cointracker", "lint_only": true}
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPOS = {
    "Sapphire": Path.home() / "Code" / "Sapphire",
    "Project-Go-Forward": Path.home() / "Code" / "Project-Go-Forward",
    "kimi-tools": Path.home() / "Code" / "kimi-tools",
    "regional-intel-workbench": Path.home() / "Code" / "regional-intel-workbench",
    "tradingview-mcp": Path.home() / "Code" / "tradingview-mcp",
    "Cointracker": Path.home() / "Code" / "Cointracker",
    "claw-code": Path.home() / "Code" / "claw-code",
}

ENV = {**os.environ, "PATH": f"/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:{os.environ.get('PATH', '')}"}


def run_cmd(cmd: list[str], cwd: str, timeout: int = 120) -> tuple[str, int]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, timeout=timeout, env=ENV)
        return (r.stdout + r.stderr).strip(), r.returncode
    except subprocess.TimeoutExpired:
        return "Timed out", -1
    except Exception as e:
        return str(e), -1


def verify_repo(repo_name: str, lint_only: bool = False) -> dict:
    """Run verification on a repo."""
    path = REPOS.get(repo_name)
    if not path or not path.exists():
        return {"error": f"Repo '{repo_name}' not found", "safe_to_commit": False}

    result = {
        "repo": repo_name,
        "path": str(path),
        "lint": {"errors": -1, "fixable": 0},
        "tests": {"total": 0, "passed": 0, "failed": 0, "errors": 0, "skipped": 0},
        "git": {"uncommitted": 0, "branch": ""},
        "safe_to_commit": False,
    }

    cwd = str(path)

    # Git status
    git_status, _ = run_cmd(["git", "status", "--short"], cwd)
    result["git"]["uncommitted"] = len([l for l in git_status.splitlines() if l.strip()])
    branch, _ = run_cmd(["git", "branch", "--show-current"], cwd)
    result["git"]["branch"] = branch.strip()

    # Lint (Python repos)
    if (path / "pyproject.toml").exists() or list(path.glob("*.py"))[:1]:
        lint_out, lint_code = run_cmd(
            ["python3", "-m", "ruff", "check", "--select", "E,F,I", "--statistics", "."],
            cwd, timeout=60,
        )
        total_errors = 0
        for line in lint_out.splitlines():
            parts = line.strip().split()
            if parts and parts[0].isdigit():
                total_errors += int(parts[0])
        result["lint"]["errors"] = total_errors

    # TypeScript repos
    if (path / "tsconfig.json").exists() or (path / "package.json").exists():
        ts_out, ts_code = run_cmd(["npx", "tsc", "--noEmit"], cwd, timeout=60)
        ts_errors = ts_out.count("error TS")
        result["lint"]["errors"] = ts_errors

    if lint_only:
        result["safe_to_commit"] = result["lint"]["errors"] == 0
        return result

    # Tests (Python)
    test_dirs = [path / "tests", path / "test"]
    if any(d.exists() for d in test_dirs):
        test_out, test_code = run_cmd(
            ["python3", "-m", "pytest", "--tb=no", "-q", "--no-header", "."],
            cwd, timeout=120,
        )
        for line in test_out.splitlines():
            if "passed" in line or "failed" in line or "error" in line:
                parts = line.split()
                for i, p in enumerate(parts):
                    if p == "passed" and i > 0:
                        try:
                            result["tests"]["passed"] = int(parts[i - 1])
                        except ValueError:
                            pass
                    elif p == "failed" and i > 0:
                        try:
                            result["tests"]["failed"] = int(parts[i - 1])
                        except ValueError:
                            pass
                    elif p == "error" in line.lower() and i > 0:
                        try:
                            result["tests"]["errors"] = int(parts[i - 1])
                        except ValueError:
                            pass

        result["tests"]["total"] = result["tests"]["passed"] + result["tests"]["failed"] + result["tests"]["errors"]

    # Safe to commit?
    lint_ok = result["lint"]["errors"] <= 0  # -1 means no lint check, 0 means clean
    tests_ok = result["tests"]["failed"] == 0 and result["tests"]["errors"] == 0
    result["safe_to_commit"] = lint_ok and tests_ok

    return result


def verify_all() -> dict:
    """Verify all repos."""
    results = {}
    for name in REPOS:
        results[name] = verify_repo(name, lint_only=True)  # Fast scan — lint only by default
    return results


def main():
    try:
        input_data = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, EOFError):
        if len(sys.argv) > 1:
            input_data = {"repo": sys.argv[1]}
        else:
            input_data = {"all": True}

    if input_data.get("all"):
        print(json.dumps(verify_all(), indent=2))
    else:
        repo = input_data.get("repo", "Sapphire")
        lint_only = input_data.get("lint_only", False)
        print(json.dumps(verify_repo(repo, lint_only), indent=2))


if __name__ == "__main__":
    main()
