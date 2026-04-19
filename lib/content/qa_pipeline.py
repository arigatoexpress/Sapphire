"""QA pipeline — runs the quality gate on a report body before publishing.

Wraps lib.content.quality.check() with per-kind overrides and structured
pass/fail results consumed by the approval workflow.

Kinds with relaxed thresholds:
  - market_pulse: single-tweet format, checked via short_form_exception
  - security_digest: citation-heavy by nature, lower originality floor

Usage::

    from lib.content.qa_pipeline import run_qa
    result = run_qa(report)
    if not result.passed:
        log.warning("QA failed: %s", result.failures)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from lib.content import quality as _q
from lib.content.report_generator import Report

log = logging.getLogger(__name__)

_KIND_OVERRIDES: dict[str, dict[str, Any]] = {
    "market_pulse": {
        "min_numbers": 3,
    },
    "security_digest": {
        "min_originality_score": 0.35,
    },
}


def _qa_text(report: Report) -> str:
    if not report.sources:
        return report.body
    return report.body + "\n\nSources: " + " ".join(report.sources)


@dataclass
class QAResult:
    passed: bool
    failures: list[str]
    word_count: int
    evidence_density: float
    kind: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "failures": self.failures,
            "word_count": self.word_count,
            "evidence_density": self.evidence_density,
            "kind": self.kind,
        }


def run_qa(report: Report) -> QAResult:
    """Run the quality gate on *report* and return a structured result."""
    qa_text = _qa_text(report)
    result = _q.check(qa_text, facts=report.facts)

    # Apply per-kind overrides: re-filter reasons that the override relaxes
    overrides = _KIND_OVERRIDES.get(report.kind, {})
    reasons = list(result.reasons)

    if "min_numbers" in overrides:
        min_n = overrides["min_numbers"]
        reasons = [r for r in reasons if not r.startswith("data_density_low") or _q.count_numbers(qa_text) < min_n]

    if "min_originality_score" in overrides:
        floor = overrides["min_originality_score"]
        reasons = [r for r in reasons if not r.startswith("originality_low") or result.originality_score < floor]

    return QAResult(
        passed=len(reasons) == 0,
        failures=reasons,
        word_count=result.word_count,
        evidence_density=result.evidence_density,
        kind=report.kind,
    )
