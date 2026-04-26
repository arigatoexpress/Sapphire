"""Tests for CI/CD Feedback Processor.

Verifies:
  - Pytest output parsing (failures, summary)
  - Task creation for test failures (capped at 10)
  - Build failure handling
  - Success (no action) path
  - Edge cases (empty output, malformed output)
"""

import os
import sys
from unittest.mock import MagicMock

import pytest

# Add alpha-engine source to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "services", "alpha", "src"))

from ci_feedback import CIFeedbackProcessor

# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def mock_task_manager():
    tm = MagicMock()
    tm.create_task.return_value = {"ok": True, "task": {"task_id": "T-001"}}
    return tm


@pytest.fixture
def processor(mock_task_manager):
    return CIFeedbackProcessor(task_manager=mock_task_manager)


# ── Pytest Failure Parsing ───────────────────────────────────────────


SAMPLE_PYTEST_OUTPUT = """\
tests/unit/test_foo.py::test_alpha PASSED
tests/unit/test_foo.py::test_beta PASSED
FAILED tests/unit/test_bar.py::test_gamma - AssertionError: 42 != 43
FAILED tests/unit/test_bar.py::test_delta - TypeError: expected int
tests/unit/test_baz.py::test_epsilon PASSED

====== 3 passed, 2 failed in 5.23s ======
"""

SAMPLE_PYTEST_ERROR_OUTPUT = """\
ERROR tests/unit/test_api.py::test_endpoint[param-value] - RuntimeError: fixture exploded
ERROR tests/unit/test_collect.py - ImportError: cannot import name thing

====== 1 passed, 0 failed, 2 errors in 2.34s ======
"""


class TestPytestParsing:
    def test_parse_failures(self):
        failures = CIFeedbackProcessor._parse_pytest_failures(SAMPLE_PYTEST_OUTPUT)
        assert len(failures) == 2
        assert failures[0]["kind"] == "failure"
        assert failures[0]["test_name"] == "tests/unit/test_bar.py::test_gamma"
        assert "42 != 43" in failures[0]["message"]
        assert failures[1]["test_name"] == "tests/unit/test_bar.py::test_delta"

    def test_parse_errors_and_parametrized_ids(self):
        failures = CIFeedbackProcessor._parse_pytest_failures(SAMPLE_PYTEST_ERROR_OUTPUT)
        assert len(failures) == 2
        assert failures[0]["kind"] == "error"
        assert failures[0]["test_name"] == "tests/unit/test_api.py::test_endpoint[param-value]"
        assert "fixture exploded" in failures[0]["message"]
        assert failures[1]["test_name"] == "tests/unit/test_collect.py"
        assert "ImportError" in failures[1]["message"]

    def test_parse_summary(self):
        passed, failed, errors = CIFeedbackProcessor._parse_pytest_summary(SAMPLE_PYTEST_OUTPUT)
        assert passed == 3
        assert failed == 2
        assert errors == 0

    def test_parse_summary_with_errors(self):
        output = "1197 passed, 0 failed, 1 error in 12.34s"
        passed, failed, errors = CIFeedbackProcessor._parse_pytest_summary(output)
        assert passed == 1197
        assert failed == 0
        assert errors == 1

    def test_parse_summary_with_plural_errors(self):
        passed, failed, errors = CIFeedbackProcessor._parse_pytest_summary(
            SAMPLE_PYTEST_ERROR_OUTPUT
        )
        assert passed == 1
        assert failed == 0
        assert errors == 2

    def test_parse_no_failures(self):
        output = "1197 passed in 12.34s"
        failures = CIFeedbackProcessor._parse_pytest_failures(output)
        assert failures == []

    def test_parse_empty_output(self):
        failures = CIFeedbackProcessor._parse_pytest_failures("")
        passed, failed, errors = CIFeedbackProcessor._parse_pytest_summary("")
        assert failures == []
        assert passed == 0
        assert failed == 0
        assert errors == 0


# ── Test Result Processing ───────────────────────────────────────────


class TestProcessTestResults:
    def test_no_failures_no_tasks(self, processor, mock_task_manager):
        result = processor.process_test_results("1197 passed in 12.34s")
        assert result["ok"]
        assert result["action"] == "none"
        assert result["tasks_created"] == 0
        mock_task_manager.create_task.assert_not_called()

    def test_failures_create_tasks(self, processor, mock_task_manager):
        result = processor.process_test_results(SAMPLE_PYTEST_OUTPUT)
        assert result["ok"]
        assert result["action"] == "tasks_created"
        assert result["tasks_created"] == 2
        assert result["passed"] == 3
        assert result["failed"] == 2
        assert mock_task_manager.create_task.call_count == 2
        # Verify tasks are assigned to EMERALD
        for call in mock_task_manager.create_task.call_args_list:
            assert call.kwargs.get("agent") == "EMERALD" or call[1].get("agent") == "EMERALD"

    def test_errors_create_tasks(self, processor, mock_task_manager):
        result = processor.process_test_results(SAMPLE_PYTEST_ERROR_OUTPUT)
        assert result["ok"]
        assert result["action"] == "tasks_created"
        assert result["tasks_created"] == 2
        assert result["passed"] == 1
        assert result["failed"] == 0
        assert result["errors"] == 2
        assert mock_task_manager.create_task.call_count == 2
        call = mock_task_manager.create_task.call_args_list[0]
        assert call.kwargs.get("title") == (
            "Fix test error: tests/unit/test_api.py::test_endpoint[param-value]"
        )
        assert "test_error" in call.kwargs.get("tags")

    def test_cap_at_10_tasks(self, processor, mock_task_manager):
        # Generate 15 failures
        lines = []
        for i in range(15):
            lines.append(f"FAILED tests/unit/test_x.py::test_{i} - AssertionError: fail")
        lines.append("0 passed, 15 failed in 1.0s")
        output = "\n".join(lines)
        result = processor.process_test_results(output)
        assert result["tasks_created"] == 10  # capped
        assert mock_task_manager.create_task.call_count == 10

    def test_empty_output(self, processor, mock_task_manager):
        result = processor.process_test_results("")
        assert result["ok"]
        assert result["action"] == "none"
        assert result["tasks_created"] == 0


# ── Build Result Processing ──────────────────────────────────────────


class TestProcessBuildResult:
    def test_success_no_task(self, processor, mock_task_manager):
        result = processor.process_build_result("SUCCESS", build_id="build-123")
        assert result["ok"]
        assert result["action"] == "none"
        mock_task_manager.create_task.assert_not_called()

    def test_failure_creates_task(self, processor, mock_task_manager):
        result = processor.process_build_result(
            "FAILURE", build_id="build-456", error="Step 3 failed: pip install"
        )
        assert result["ok"]
        assert result["action"] == "task_created"
        assert result["build_id"] == "build-456"
        mock_task_manager.create_task.assert_called_once()
        call_kwargs = mock_task_manager.create_task.call_args
        # Verify task is assigned to OBSIDIAN with critical priority
        assert (
            call_kwargs.kwargs.get("agent") == "OBSIDIAN"
            or call_kwargs[1].get("agent") == "OBSIDIAN"
        )
        assert (
            call_kwargs.kwargs.get("priority") == "critical"
            or call_kwargs[1].get("priority") == "critical"
        )

    def test_case_insensitive_success(self, processor, mock_task_manager):
        result = processor.process_build_result("success")
        assert result["action"] == "none"

    def test_unknown_build_id(self, processor, mock_task_manager):
        result = processor.process_build_result("FAILURE", error="OOM killed")
        assert result["action"] == "task_created"
