"""Telemetry helpers for adversarial intelligence detections."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from typing import Any

from lib.security.adversarial_detectors import AdversarialFinding, DetectorReport

EVENT_TYPE = "adversarial.detection"
SCHEMA_VERSION = 1

Publisher = Callable[[str, dict[str, Any], str], Any]

SECRETISH_RE = re.compile(
    r"(?i)(api[_-]?key|secret|token|password|private[_-]?key)\s*[=:]\s*['\"]?[^'\"\s]{6,}"
)
LONG_TOKEN_RE = re.compile(r"\b(?:sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|[A-Za-z0-9_/-]{48,})\b")


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _safe_text(value: Any, *, limit: int = 240) -> str:
    text = str(value or "")
    text = SECRETISH_RE.sub("[redacted-secret]", text)
    text = LONG_TOKEN_RE.sub("[redacted-token]", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def build_detection_event(
    finding: AdversarialFinding,
    *,
    source: str = "adversarial-defense",
    run_id: str = "",
    dry_run: bool = False,
) -> dict[str, Any]:
    """Build a paste-safe telemetry envelope for one finding."""
    return {
        "schema_version": SCHEMA_VERSION,
        "event_type": EVENT_TYPE,
        "generated_at": _now_iso(),
        "source": source,
        "run_id": run_id,
        "dry_run": dry_run,
        "severity": finding.severity,
        "detector": finding.detector,
        "rule_id": finding.rule_id,
        "subject": _safe_text(finding.subject, limit=160),
        "confidence": round(float(finding.confidence), 4),
        "score": round(float(finding.score), 4),
        "summary": _safe_text(finding.summary),
        "quarantine_eligible": bool(finding.quarantine_eligible),
        "recommended_action": _safe_text(finding.recommended_action, limit=160),
        "evidence": [_safe_text(item) for item in finding.evidence[:5]],
        "metadata": {
            str(key): _safe_text(value, limit=160)
            for key, value in finding.metadata.items()
            if key not in {"raw", "text", "prompt", "secret", "token"}
        },
        "tags": ["project:sapphire", "type:security", "service:adversarial-defense"],
    }


def emit_detection(
    finding: AdversarialFinding,
    *,
    publisher: Publisher | None = None,
    source: str = "adversarial-defense",
    run_id: str = "",
    dry_run: bool = False,
) -> Any:
    """Publish one ``adversarial.detection`` event.

    Callers can inject ``publisher`` in tests or use the repo event bus in
    runtime paths. The function never receives raw source records.
    """
    payload = build_detection_event(finding, source=source, run_id=run_id, dry_run=dry_run)
    if publisher is not None:
        return publisher(EVENT_TYPE, payload, source)

    from lib.core.event_bus import get_bus

    return get_bus().publish(EVENT_TYPE, payload, source=source)


def emit_report(
    report: DetectorReport,
    *,
    publisher: Publisher | None = None,
    source: str = "adversarial-defense",
    run_id: str = "",
    dry_run: bool = False,
) -> list[Any]:
    return [
        emit_detection(
            finding,
            publisher=publisher,
            source=source,
            run_id=run_id,
            dry_run=dry_run,
        )
        for finding in report.findings
    ]


def emit_reports(
    reports: Iterable[DetectorReport],
    *,
    publisher: Publisher | None = None,
    source: str = "adversarial-defense",
    run_id: str = "",
    dry_run: bool = False,
) -> list[Any]:
    event_ids: list[Any] = []
    for report in reports:
        event_ids.extend(
            emit_report(
                report,
                publisher=publisher,
                source=source,
                run_id=run_id,
                dry_run=dry_run,
            )
        )
    return event_ids


__all__ = [
    "EVENT_TYPE",
    "build_detection_event",
    "emit_detection",
    "emit_report",
    "emit_reports",
]
