"""CI/CD Feedback Processor — turns test/build failures into agent tasks.

When a CI pipeline (Cloud Build, pytest) reports failures, this processor
creates tasks in the TaskManager and notifies the owner via Telegram.
This closes the loop: agents write code → CI tests → failures become tasks
→ agents fix the failures.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


class CIFeedbackProcessor:
    """Processes CI/CD results and creates remediation tasks."""

    def __init__(self, task_manager, telegram_bot=None):
        self.tasks = task_manager
        self.telegram = telegram_bot

    def process_test_results(self, raw_output: str) -> dict[str, Any]:
        """Parse pytest output and create tasks for failures.

        Returns summary of actions taken.
        """
        failures = self._parse_pytest_failures(raw_output)
        passed, failed, errors = self._parse_pytest_summary(raw_output)

        if not failures:
            return {
                "ok": True,
                "action": "none",
                "passed": passed,
                "failed": failed,
                "errors": errors,
                "tasks_created": 0,
            }

        created = 0
        for failure in failures[:10]:  # cap at 10 tasks per run
            self.tasks.create_task(
                title=f"Fix test: {failure['test_name'][:80]}",
                phase="ci_remediation",
                agent="EMERALD",
                priority="high",
                description=f"Test failure:\n{failure['message'][:500]}",
                tags=["ci", "test_failure", "auto_generated"],
            )
            created += 1

        return {
            "ok": True,
            "action": "tasks_created",
            "passed": passed,
            "failed": failed,
            "errors": errors,
            "tasks_created": created,
            "failure_names": [f["test_name"] for f in failures[:10]],
        }

    def process_build_result(self, status: str, build_id: str = "", error: str = "") -> dict[str, Any]:
        """Process a Cloud Build result. Creates task on failure."""
        if status.upper() == "SUCCESS":
            return {"ok": True, "action": "none"}

        self.tasks.create_task(
            title=f"Fix build failure: {build_id or 'unknown'}",
            phase="ci_remediation",
            agent="OBSIDIAN",
            priority="critical",
            description=f"Build {build_id} failed: {error[:500]}",
            tags=["ci", "build_failure", "auto_generated"],
        )
        return {"ok": True, "action": "task_created", "build_id": build_id}

    # ── Internal parsers ─────────────────────────────────────────────

    @staticmethod
    def _parse_pytest_failures(output: str) -> list[dict[str, str]]:
        """Extract individual test failures from pytest output."""
        failures: list[dict[str, str]] = []
        # Pattern: FAILED tests/unit/test_foo.py::test_bar - AssertionError: ...
        pattern = re.compile(r"FAILED\s+([\w/\.\-:]+)\s*[-–]\s*(.*)")
        for match in pattern.finditer(output):
            failures.append({
                "test_name": match.group(1).strip(),
                "message": match.group(2).strip()[:300],
            })
        return failures

    @staticmethod
    def _parse_pytest_summary(output: str) -> tuple:
        """Extract passed/failed/error counts from pytest summary line."""
        passed = failed = errors = 0
        # Pattern: "1197 passed, 3 failed, 1 error in 12.34s"
        m = re.search(r"(\d+) passed", output)
        if m:
            passed = int(m.group(1))
        m = re.search(r"(\d+) failed", output)
        if m:
            failed = int(m.group(1))
        m = re.search(r"(\d+) error", output)
        if m:
            errors = int(m.group(1))
        return passed, failed, errors
