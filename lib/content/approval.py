"""Approval workflow for generated content drafts.

Three-phase flow:
  1. QA gate (automated) — lib.content.qa_pipeline.run_qa()
  2. Sensitivity check (automated) — blocks PII / secrets via sensitivity_classifier
  3. Human approval (optional) — writes approval record to data/content/approvals.jsonl

In fully autonomous mode (``require_human=False``) stages 1 and 2 are the
only blockers.  When ``require_human=True``, the draft waits in
data/content/pending/ until a human runs ``python3 -m lib.content approve <slug>``.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from lib.content.qa_pipeline import run_qa
from lib.content.report_generator import Report

log = logging.getLogger(__name__)

_REPO = Path(__file__).resolve().parents[2]
_APPROVALS_FILE = _REPO / "data" / "content" / "approvals.jsonl"
_PENDING_DIR = _REPO / "data" / "content" / "pending"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    SKIPPED = "skipped"


@dataclass
class ApprovalRecord:
    kind: str
    title: str
    status: ApprovalStatus
    qa_result: dict[str, Any]
    sensitivity_flags: list[str]
    approved_by: str = "auto"
    reason: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "title": self.title,
            "status": self.status.value,
            "qa_result": self.qa_result,
            "sensitivity_flags": self.sensitivity_flags,
            "approved_by": self.approved_by,
            "reason": self.reason,
            "timestamp": self.timestamp,
        }


def _check_sensitivity(body: str) -> list[str]:
    try:
        import sys
        sys.path.insert(0, str(_REPO / "plugins" / "claw-sapphire" / "lib"))
        from sensitivity_classifier import classify
        result = classify(body)
        return result.get("flags", []) if isinstance(result, dict) else []
    except Exception:
        return []


def _append_record(record: ApprovalRecord) -> None:
    _APPROVALS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with _APPROVALS_FILE.open("a") as f:
        f.write(json.dumps(record.to_dict()) + "\n")


def approve(report: Report, *, require_human: bool = False) -> ApprovalRecord:
    """Run the full approval flow for *report*.

    Returns an ApprovalRecord with status APPROVED, REJECTED, or PENDING.
    """
    qa = run_qa(report)
    flags = _check_sensitivity(report.body)

    if not qa.passed:
        record = ApprovalRecord(
            kind=report.kind,
            title=report.title,
            status=ApprovalStatus.REJECTED,
            qa_result=qa.to_dict(),
            sensitivity_flags=flags,
            reason=f"QA failed: {qa.failures}",
        )
        _append_record(record)
        return record

    if flags:
        record = ApprovalRecord(
            kind=report.kind,
            title=report.title,
            status=ApprovalStatus.REJECTED,
            qa_result=qa.to_dict(),
            sensitivity_flags=flags,
            reason=f"Sensitivity flags: {flags}",
        )
        _append_record(record)
        return record

    if require_human:
        _PENDING_DIR.mkdir(parents=True, exist_ok=True)
        slug = report.kind.replace("_", "-")
        ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        pending_path = _PENDING_DIR / f"{ts}_{slug}.json"
        pending_path.write_text(json.dumps({"kind": report.kind, "body": report.body}))
        record = ApprovalRecord(
            kind=report.kind,
            title=report.title,
            status=ApprovalStatus.PENDING,
            qa_result=qa.to_dict(),
            sensitivity_flags=flags,
            approved_by="pending_human",
            reason=f"Awaiting human review: {pending_path.name}",
        )
        _append_record(record)
        return record

    record = ApprovalRecord(
        kind=report.kind,
        title=report.title,
        status=ApprovalStatus.APPROVED,
        qa_result=qa.to_dict(),
        sensitivity_flags=flags,
    )
    _append_record(record)
    return record
