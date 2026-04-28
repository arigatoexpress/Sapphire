"""Pure heuristics for auditing autonomously merged pull requests.

The functions in this module are side-effect free. They inspect metadata that a
caller already collected from GitHub and return bounded, paste-safe findings.
They never include full diffs or PR bodies in their output.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from pathlib import PurePosixPath
from typing import Any

MAX_EVIDENCE_ITEMS = 6
OVERSIZE_LINES_CHANGED = 2_000
OVERSIZE_FILES_CHANGED = 15
SCOPE_CREEP_AREA_COUNT = 5
KILL_SWITCH_REVIEWER = "arigatoexpress"
NO_SPEND_SKIP_TOKEN = "[skip ci]"

SENSITIVE_CONTROL_PATHS = {
    "lib/core/kill_switch.py",
    "lib/core/confirmation_firewall.py",
    "lib/core/risk_kernel.py",
}

WEAK_SUBJECT_RE = re.compile(r"(?i)^\s*(wip|fix|update|misc)\s*$")
SECRET_SIGNATURE_RE = re.compile(
    r"(?i)("
    r"\b(?:api[_-]?key|secret|token|password|private[_-]?key)\b\s*[=:]\s*['\"]?[A-Za-z0-9_\-]{16,}|"
    r"\bsk-[A-Za-z0-9]{16,}|"
    r"\bgh[pousr]_[A-Za-z0-9_]{20,}|"
    r"\bxox[baprs]-[A-Za-z0-9-]{20,}|"
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
    r")"
)

AREA_HINTS = {
    "audit": {"audit_panel", "audit-panel", "audit"},
    "security": {"security", "kill_switch", "confirmation_firewall", "risk_kernel"},
    "trading": {"trading", "alpha", "portfolio", "robinhood", "webhook", "contracts"},
    "dashboard": {"dashboard", "templates", "static"},
    "plugin": {"plugins", "claw-sapphire"},
    "docs": {"docs"},
    "tests": {"tests"},
    "infra": {"infra", ".github", "scripts"},
    "service": {"services"},
    "analytics": {"analytics", "strategy", "backtest"},
    "intel": {"intel", "intelligence", "macro", "counterparty", "event_impact"},
}

SEVERITY_ORDER = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


@dataclass(frozen=True)
class Review:
    """Minimal review metadata used by the audit heuristics."""

    author: str
    state: str

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Review:
        author = payload.get("author") or {}
        login = author.get("login") if isinstance(author, dict) else author
        return cls(author=str(login or ""), state=str(payload.get("state") or ""))


@dataclass(frozen=True)
class MergedPR:
    """Paste-safe merged PR record collected by the service runner."""

    number: int
    title: str
    url: str = ""
    author: str = ""
    merged_at: str = ""
    merge_commit: str = ""
    additions: int = 0
    deletions: int = 0
    changed_files: tuple[str, ...] = ()
    commits: tuple[str, ...] = ()
    reviews: tuple[Review, ...] = ()
    status_conclusion: str | None = None
    diff_snippets: tuple[str, ...] = ()
    labels: tuple[str, ...] = ()

    @property
    def lines_changed(self) -> int:
        return max(0, int(self.additions)) + max(0, int(self.deletions))

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> MergedPR:
        reviews = tuple(
            Review.from_dict(item)
            for item in payload.get("reviews", []) or []
            if isinstance(item, dict)
        )
        commits = tuple(str(item) for item in payload.get("commits", []) or [])
        files = tuple(str(item) for item in payload.get("changed_files", []) or [])
        snippets = tuple(str(item) for item in payload.get("diff_snippets", []) or [])
        labels = tuple(str(item) for item in payload.get("labels", []) or [])
        return cls(
            number=int(payload.get("number") or 0),
            title=str(payload.get("title") or ""),
            url=str(payload.get("url") or ""),
            author=str(payload.get("author") or ""),
            merged_at=str(payload.get("merged_at") or payload.get("mergedAt") or ""),
            merge_commit=str(payload.get("merge_commit") or payload.get("mergeCommit") or ""),
            additions=int(payload.get("additions") or 0),
            deletions=int(payload.get("deletions") or 0),
            changed_files=files,
            commits=commits,
            reviews=reviews,
            status_conclusion=(
                str(payload["status_conclusion"]) if payload.get("status_conclusion") else None
            ),
            diff_snippets=snippets,
            labels=labels,
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["reviews"] = [asdict(review) for review in self.reviews]
        return data


@dataclass(frozen=True)
class Finding:
    """One audit finding produced by a heuristic."""

    rule_id: str
    severity: str
    confidence: float
    summary: str
    pr_number: int
    title: str
    evidence: tuple[str, ...] = ()
    recommended_action: str = "manual_review"

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "severity": self.severity,
            "confidence": round(float(self.confidence), 4),
            "summary": self.summary,
            "pr_number": self.pr_number,
            "title": self.title[:160],
            "evidence": list(self.evidence[:MAX_EVIDENCE_ITEMS]),
            "recommended_action": self.recommended_action,
        }


def _finding(
    pr: MergedPR,
    *,
    rule_id: str,
    severity: str,
    confidence: float,
    summary: str,
    evidence: Iterable[str] = (),
    recommended_action: str = "manual_review",
) -> Finding:
    safe_evidence = tuple(str(item)[:220] for item in evidence if str(item).strip())
    return Finding(
        rule_id=rule_id,
        severity=severity,
        confidence=confidence,
        summary=summary,
        pr_number=pr.number,
        title=pr.title[:160],
        evidence=safe_evidence[:MAX_EVIDENCE_ITEMS],
        recommended_action=recommended_action,
    )


def oversize_diff(pr: MergedPR) -> Finding | None:
    if pr.lines_changed > OVERSIZE_LINES_CHANGED and len(pr.changed_files) > OVERSIZE_FILES_CHANGED:
        return _finding(
            pr,
            rule_id="oversize_diff",
            severity="medium",
            confidence=0.92,
            summary="Merged PR exceeded the audit panel's diff-size review threshold.",
            evidence=(
                f"lines_changed={pr.lines_changed}",
                f"files_changed={len(pr.changed_files)}",
            ),
            recommended_action="sample_files_and_confirm_lane_scope",
        )
    return None


def weak_commit_message(pr: MergedPR) -> Finding | None:
    weak = [
        subject
        for subject in pr.commits
        if len(subject.strip()) < 10 or WEAK_SUBJECT_RE.match(subject.strip())
    ]
    if weak:
        return _finding(
            pr,
            rule_id="weak_commit_message",
            severity="low",
            confidence=0.9,
            summary="At least one commit subject is too weak to support auditability.",
            evidence=(f"weak_subject={subject[:80]}" for subject in weak[:3]),
            recommended_action="require_specific_subject_before_merge",
        )
    return None


def kill_switch_touched_without_review(pr: MergedPR) -> Finding | None:
    touched = sorted(set(pr.changed_files).intersection(SENSITIVE_CONTROL_PATHS))
    if not touched:
        return None
    approved_by_owner = any(
        review.author.lower() == KILL_SWITCH_REVIEWER
        and review.state.upper() in {"APPROVED", "COMMENTED"}
        for review in pr.reviews
    )
    if approved_by_owner:
        return None
    return _finding(
        pr,
        rule_id="kill_switch_touched_without_review",
        severity="critical",
        confidence=0.95,
        summary="A safety-control file changed without an owner review marker.",
        evidence=touched,
        recommended_action="obtain_owner_review_or_revert_until_reviewed",
    )


def _test_candidates_for(path: str) -> tuple[str, ...]:
    stem = PurePosixPath(path).stem
    if path.startswith("lib/"):
        return (f"tests/unit/test_{stem}.py",)
    if path.startswith("plugins/"):
        return (
            f"plugins/claw-sapphire/tests/test_{stem}.py",
            f"tests/unit/test_{stem}.py",
        )
    return ()


def tests_missing_for_new_module(pr: MergedPR) -> Finding | None:
    added_modules = [
        path
        for path in pr.changed_files
        if path.endswith(".py")
        and (path.startswith("lib/") or path.startswith("plugins/"))
        and not path.endswith("__init__.py")
        and "/tests/" not in path
    ]
    if not added_modules:
        return None
    files = set(pr.changed_files)
    missing = [
        path
        for path in added_modules
        if not any(candidate in files for candidate in _test_candidates_for(path))
    ]
    if missing:
        return _finding(
            pr,
            rule_id="tests_missing_for_new_module",
            severity="high",
            confidence=0.82,
            summary="A new Python module landed without an obvious companion test file in the PR.",
            evidence=missing[:MAX_EVIDENCE_ITEMS],
            recommended_action="add_focused_tests_for_new_module",
        )
    return None


def _area_for_path(path: str) -> str:
    parts = [part for part in PurePosixPath(path).parts if part]
    if not parts:
        return "unknown"
    if parts[0] == "plugins" and len(parts) >= 2:
        return "plugins"
    if parts[0] == "services" and len(parts) >= 2:
        return f"services/{parts[1]}"
    if parts[0] == "lib" and len(parts) >= 2:
        return f"lib/{parts[1]}"
    if parts[0] == "docs" and len(parts) >= 2:
        return f"docs/{parts[1]}"
    return parts[0]


def _mentioned_areas(text: str) -> set[str]:
    lowered = text.lower().replace("-", "_")
    areas: set[str] = set()
    for area, hints in AREA_HINTS.items():
        if any(hint in lowered for hint in hints):
            areas.add(area)
    return areas


def scope_creep(pr: MergedPR) -> Finding | None:
    areas = sorted({_area_for_path(path) for path in pr.changed_files})
    if len(areas) < SCOPE_CREEP_AREA_COUNT:
        return None
    mentioned = _mentioned_areas(" ".join((pr.title, *pr.commits)))
    # A multi-area title such as "integration" or "repo hygiene" is often honest.
    broad_words = {"integration", "hygiene", "sweep", "tranche", "readiness", "platform"}
    title_words = set(re.findall(r"[a-z0-9_]+", pr.title.lower().replace("-", "_")))
    if len(mentioned) <= 1 and not title_words.intersection(broad_words):
        return _finding(
            pr,
            rule_id="scope_creep",
            severity="medium",
            confidence=0.72,
            summary="PR title or commit subjects describe a narrow area but the diff spans many areas.",
            evidence=(f"areas={', '.join(areas[:8])}", f"area_count={len(areas)}"),
            recommended_action="split_future_work_or_expand_pr_summary",
        )
    return None


def secret_signature(pr: MergedPR) -> Finding | None:
    matches = []
    for snippet in pr.diff_snippets:
        if SECRET_SIGNATURE_RE.search(snippet):
            matches.append("secret-like token pattern in collected diff metadata")
    if matches:
        return _finding(
            pr,
            rule_id="secret_signature",
            severity="critical",
            confidence=0.88,
            summary="Diff metadata contained a token-shaped or private-key-shaped signature.",
            evidence=matches[:1],
            recommended_action="rotate_candidate_secret_and_purge_history_if_confirmed",
        )
    return None


def provenance_envelope_missing(pr: MergedPR) -> Finding | None:
    data_artifacts = [
        path
        for path in pr.changed_files
        if path.startswith("data/")
        and path.endswith(".json")
        and not path.endswith(".envelope.json")
        and not path.endswith("/.gitkeep")
    ]
    files = set(pr.changed_files)
    missing = [
        path
        for path in data_artifacts
        if f"{path}.envelope.json" not in files
        and str(PurePosixPath(path).with_name(f"{PurePosixPath(path).name}.envelope.json"))
        not in files
    ]
    if missing:
        return _finding(
            pr,
            rule_id="provenance_envelope_missing",
            severity="high",
            confidence=0.86,
            summary="A generated data JSON artifact was added without a sibling provenance envelope.",
            evidence=missing[:MAX_EVIDENCE_ITEMS],
            recommended_action="stamp_artifact_with_lib_core_provenance_sidecar",
        )
    return None


def failed_check_overridden(pr: MergedPR) -> Finding | None:
    conclusion = (pr.status_conclusion or "").upper()
    if conclusion in {"FAILURE", "FAILED", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED"}:
        return _finding(
            pr,
            rule_id="failed_check_overridden",
            severity="critical",
            confidence=0.83,
            summary="PR appears to have been merged with a failing status rollup.",
            evidence=(f"status_conclusion={conclusion}",),
            recommended_action="confirm_local_gate_evidence_and_reopen_if_unproven",
        )
    return None


def ci_skip_dropped(pr: MergedPR) -> Finding | None:
    subjects = (pr.title, *pr.commits)
    if any(NO_SPEND_SKIP_TOKEN in subject.lower() for subject in subjects):
        return None
    return _finding(
        pr,
        rule_id="ci_skip_dropped",
        severity="medium",
        confidence=0.8,
        summary="Merged PR subject history lacks [skip ci] during a no-spend audit window.",
        evidence=(f"merge_commit={pr.merge_commit[:12] or 'unknown'}",),
        recommended_action="use_safe_merge_wrapper_or_explicit_squash_title",
    )


HEURISTICS: tuple[Callable[[MergedPR], Finding | None], ...] = (
    oversize_diff,
    weak_commit_message,
    kill_switch_touched_without_review,
    tests_missing_for_new_module,
    scope_creep,
    secret_signature,
    provenance_envelope_missing,
    failed_check_overridden,
    ci_skip_dropped,
)


def run_heuristics(pr: MergedPR) -> tuple[Finding, ...]:
    findings = [finding for heuristic in HEURISTICS if (finding := heuristic(pr))]
    return tuple(sorted(findings, key=lambda item: (-SEVERITY_ORDER[item.severity], item.rule_id)))


def findings_by_severity(findings: Iterable[Finding]) -> dict[str, int]:
    counts = Counter(finding.severity for finding in findings)
    return {severity: int(counts.get(severity, 0)) for severity in SEVERITY_ORDER}
