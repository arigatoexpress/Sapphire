from __future__ import annotations

from lib.security.adversarial_detectors import AdversarialFinding, DetectorReport
from lib.security.adversarial_telemetry import (
    EVENT_TYPE,
    build_detection_event,
    emit_report,
)


def _finding() -> AdversarialFinding:
    return AdversarialFinding(
        detector="prompt_injection",
        rule_id="secret_exfiltration_request",
        severity="critical",
        confidence=0.94,
        score=0.95,
        subject="doc-1",
        summary="Prompt asks for api_key='sk-abcdefghijklmnopqrstuvwxyz123456'.",
        evidence=("token=ghp_0123456789abcdefghijklmnopqrstuvwxyz",),
        quarantine_eligible=True,
    )


def test_build_detection_event_is_paste_safe() -> None:
    event = build_detection_event(_finding(), run_id="run-1", dry_run=True)

    assert event["event_type"] == EVENT_TYPE
    assert event["run_id"] == "run-1"
    assert event["dry_run"] is True
    assert event["severity"] == "critical"
    blob = str(event)
    assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in blob
    assert "ghp_0123456789abcdefghijklmnopqrstuvwxyz" not in blob
    assert "[redacted" in blob


def test_emit_report_uses_injected_publisher() -> None:
    calls: list[tuple[str, dict, str]] = []

    def publisher(event_type: str, payload: dict, source: str) -> str:
        calls.append((event_type, payload, source))
        return "evt-1"

    report = DetectorReport("prompt_injection", checked=1, findings=(_finding(),))
    event_ids = emit_report(report, publisher=publisher, source="unit-test")

    assert event_ids == ["evt-1"]
    assert calls[0][0] == EVENT_TYPE
    assert calls[0][1]["detector"] == "prompt_injection"
    assert calls[0][2] == "unit-test"
