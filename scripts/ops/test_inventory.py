#!/usr/bin/env python3
"""Collect and verify Sapphire's test inventory.

The unit and plugin suites use separate ``conftest.py`` modules, so they must be
collected in separate pytest invocations. This script keeps README test counts
honest without mixing the two collection roots.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
README = ROOT / "README.md"
SUITES = (
    ("unit", ("tests/unit",)),
    ("plugin", ("plugins/claw-sapphire/tests",)),
)
# Collection must not autoload pytest11 entry points. The self-hosted runner's
# Homebrew python has a stale global web3==6.20.4 whose metadata registers
# `web3.tools.pytest_ethereum.plugins`; the uv overlay puts web3 7.x (which
# deleted web3/tools/) ahead of it on sys.path, so autoload resolves the 6.x
# entry point against the 7.x package and dies with ModuleNotFoundError.
# ci.yml already does this for the `test` and `plugin tests` jobs — doing it
# here keeps the invariant with the subprocess that actually needs it, so it
# holds for local runs and `make registry` too. Plugins the suites genuinely
# need are then loaded back explicitly (pyproject sets asyncio_mode = "auto").
COLLECTION_ENV = {"PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}
COLLECTION_PLUGIN_ARGS = ("-p", "no:cacheprovider", "-p", "pytest_asyncio.plugin")
FILE_COUNT_RE = re.compile(r"^(?P<path>.+\.py):\s+(?P<count>\d+)\s*$")
SUMMARY_RE = re.compile(r"(?P<count>\d+)\s+tests?\s+collected")
# The 2026-05-30 README overhaul (d762e899) replaced the counts table with a
# single prose bullet; parse that instead. Unit/plugin split is no longer
# advertised, so only total + files are checked against the README.
README_TESTS_RE = re.compile(r"- (?P<total>[\d,]+)\+ passing tests across (?P<files>[\d,]+) files")
README_BADGE_RE = re.compile(
    r"\[!\[Tests\]\(https://img\.shields\.io/badge/tests-(?P<label>[^-]+)-2ea44f\)\]"
)


def _has_pytest(python: str) -> bool:
    try:
        return (
            subprocess.run(
                [python, "-c", "import pytest"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            ).returncode
            == 0
        )
    except (OSError, subprocess.TimeoutExpired):
        return False


def _resolve_collection_python() -> str:
    # Explicit override wins — the operator knows which env they want.
    if env := os.environ.get("PYTHON3"):
        return env
    # Prefer the interpreter that's running this script: under `uv run` (CI)
    # or a project venv, sys.executable is the one with pytest + all test
    # deps installed. `/usr/local/bin/python3` is the macOS system python,
    # which usually lacks the deps and drives pytest --collect-only past the
    # 90s timeout via slow ImportError cascades.
    if _has_pytest(sys.executable):
        return sys.executable
    # Fallbacks for the rare case sys.executable can't import pytest (e.g.
    # invoking the script directly under a shebang'd brew python@3.14 with
    # a broken stdlib ABI — see the "python3 may resolve to brew 3.14"
    # gotcha in CLAUDE.md).
    if Path("/usr/local/bin/python3").exists() and _has_pytest("/usr/local/bin/python3"):
        return "/usr/local/bin/python3"
    return shutil.which("python3") or sys.executable


COLLECTION_PYTHON = _resolve_collection_python()


@dataclass
class SuiteInventory:
    name: str
    paths: list[str]
    tests: int
    files: int
    duration_ms: int


@dataclass
class Inventory:
    schema_version: int
    generated_at: str
    suites: list[SuiteInventory]

    @property
    def total_tests(self) -> int:
        return sum(suite.tests for suite in self.suites)

    @property
    def total_files(self) -> int:
        return sum(suite.files for suite in self.suites)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    inventory = collect_inventory()
    check_result = (
        check_readme_inventory(
            inventory,
            readme_path=args.readme,
            max_drift=args.max_drift,
        )
        if args.check_readme
        else None
    )

    if args.format == "json":
        print(json.dumps(render_json(inventory, check_result), indent=2, sort_keys=True))
    else:
        print(render_markdown(inventory, check_result), end="")

    if check_result and not check_result["ok"]:
        return 20
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--check-readme", action="store_true")
    parser.add_argument("--readme", type=Path, default=README)
    parser.add_argument(
        "--max-drift",
        type=int,
        default=50,
        help="Maximum allowed undercount before README is considered stale.",
    )
    return parser


def collect_inventory() -> Inventory:
    suites = [collect_suite(name, paths) for name, paths in SUITES]
    return Inventory(
        schema_version=1,
        generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
        suites=suites,
    )


def collect_suite(name: str, paths: tuple[str, ...]) -> SuiteInventory:
    start = time.perf_counter()
    result = subprocess.run(
        [
            COLLECTION_PYTHON,
            "-m",
            "pytest",
            *paths,
            "--collect-only",
            "-qq",
            *COLLECTION_PLUGIN_ARGS,
        ],
        cwd=ROOT,
        env={**os.environ, **COLLECTION_ENV},
        text=True,
        capture_output=True,
        check=False,
        timeout=90,
    )
    duration_ms = int((time.perf_counter() - start) * 1000)
    output = "\n".join(part for part in (result.stdout, result.stderr) if part)
    if result.returncode != 0:
        raise RuntimeError(f"{name} collection failed: {last_line(output)}")
    tests, files = parse_collect_output(output)
    return SuiteInventory(name, list(paths), tests, files, duration_ms)


def parse_collect_output(output: str) -> tuple[int, int]:
    tests = 0
    files = 0
    for line in output.splitlines():
        match = FILE_COUNT_RE.match(line.strip())
        if match:
            tests += int(match.group("count"))
            files += 1
    if tests:
        return tests, files
    summary = SUMMARY_RE.search(output)
    if summary:
        return int(summary.group("count")), 0
    raise ValueError("pytest collection output did not include file counts or summary")


def read_readme_counts(readme_path: Path = README) -> dict[str, int]:
    text = readme_path.read_text(encoding="utf-8")
    badge_match = README_BADGE_RE.search(text)
    if not badge_match:
        raise ValueError("README Tests badge was not found")
    tests_match = README_TESTS_RE.search(text)
    if not tests_match:
        raise ValueError("README passing-tests bullet was not found")
    counts = {name: int(value.replace(",", "")) for name, value in tests_match.groupdict().items()}
    counts["badge_total"] = parse_badge_total(badge_match.group("label"))
    return counts


def parse_badge_total(label: str) -> int:
    decoded = urllib.parse.unquote(label)
    match = re.match(r"(?P<total>[\d,]+)\+?\s+passing$", decoded)
    if not match:
        raise ValueError(f"README Tests badge has unexpected label: {decoded!r}")
    return int(match.group("total").replace(",", ""))


def check_readme_inventory(
    inventory: Inventory,
    *,
    readme_path: Path = README,
    max_drift: int = 50,
) -> dict[str, Any]:
    actual = {
        "total": inventory.total_tests,
        "files": inventory.total_files,
        **{suite.name: suite.tests for suite in inventory.suites},
    }
    advertised = read_readme_counts(readme_path)
    deltas = {key: actual[key] - advertised[key] for key in ("total", "files")}
    deltas["badge_total"] = actual["total"] - advertised["badge_total"]
    overclaims = {key: delta for key, delta in deltas.items() if delta < 0}
    stale = {key: delta for key, delta in deltas.items() if delta > max_drift}
    return {
        "ok": not overclaims and not stale,
        "actual": actual,
        "advertised": advertised,
        "deltas": deltas,
        "max_drift": max_drift,
        "overclaims": overclaims,
        "stale": stale,
    }


def render_json(inventory: Inventory, check_result: dict[str, Any] | None) -> dict[str, Any]:
    payload = asdict(inventory)
    payload["total_tests"] = inventory.total_tests
    payload["total_files"] = inventory.total_files
    if check_result is not None:
        payload["readme_check"] = check_result
    return payload


def render_markdown(inventory: Inventory, check_result: dict[str, Any] | None) -> str:
    lines = [
        "# Sapphire Test Inventory",
        "",
        f"- Generated: `{inventory.generated_at}`",
        f"- Total tests: `{inventory.total_tests}`",
        f"- Test files: `{inventory.total_files}`",
        "",
        "| Suite | Tests | Files | Paths |",
        "|---|---:|---:|---|",
    ]
    for suite in inventory.suites:
        lines.append(f"| {suite.name} | {suite.tests} | {suite.files} | {', '.join(suite.paths)} |")
    if check_result is not None:
        status = "PASS" if check_result["ok"] else "FAIL"
        lines.extend(
            [
                "",
                f"README check: **{status}**",
                f"- Advertised: `{check_result['advertised']}`",
                f"- Actual: `{check_result['actual']}`",
                f"- Deltas: `{check_result['deltas']}`",
            ]
        )
    return "\n".join(lines) + "\n"


def last_line(output: str) -> str:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    return lines[-1] if lines else "no output"


if __name__ == "__main__":
    raise SystemExit(main())
