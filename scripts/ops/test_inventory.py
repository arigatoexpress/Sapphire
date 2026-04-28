#!/usr/bin/env python3
"""Collect and verify Sapphire's test inventory.

The unit and plugin suites use separate ``conftest.py`` modules, so they must be
collected in separate pytest invocations. This script keeps README test counts
honest without mixing the two collection roots.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
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
FILE_COUNT_RE = re.compile(r"^(?P<path>.+\.py):\s+(?P<count>\d+)\s*$")
SUMMARY_RE = re.compile(r"(?P<count>\d+)\s+tests?\s+collected")
README_TESTS_RE = re.compile(
    r"\| Passing tests \| \*\*(?P<total>[\d,]+)\+\*\* \| "
    r"(?P<unit>[\d,]+)\+ unit · (?P<plugin>[\d,]+) plugin"
)
README_FILES_RE = re.compile(
    r"\| Test files \| \*\*(?P<files>[\d,]+)\+\*\* \|"
)


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
    check_result = check_readme_inventory(
        inventory,
        readme_path=args.readme,
        max_drift=args.max_drift,
    ) if args.check_readme else None

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
    suites = [
        collect_suite(name, paths)
        for name, paths in SUITES
    ]
    return Inventory(
        schema_version=1,
        generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
        suites=suites,
    )


def collect_suite(name: str, paths: tuple[str, ...]) -> SuiteInventory:
    start = time.perf_counter()
    result = subprocess.run(
        [sys.executable, "-m", "pytest", *paths, "--collect-only", "-qq"],
        cwd=ROOT,
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
    tests_match = README_TESTS_RE.search(text)
    if not tests_match:
        raise ValueError("README Passing tests row was not found")
    files_match = README_FILES_RE.search(text)
    if not files_match:
        raise ValueError("README Test files row was not found")
    counts = {
        name: int(value.replace(",", ""))
        for name, value in tests_match.groupdict().items()
    }
    counts["files"] = int(files_match.group("files").replace(",", ""))
    return counts


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
    deltas = {
        key: actual[key] - advertised[key]
        for key in ("total", "unit", "plugin", "files")
    }
    overclaims = {
        key: delta
        for key, delta in deltas.items()
        if delta < 0
    }
    stale = {
        key: delta
        for key, delta in deltas.items()
        if delta > max_drift
    }
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
        lines.append(
            f"| {suite.name} | {suite.tests} | {suite.files} | {', '.join(suite.paths)} |"
        )
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
