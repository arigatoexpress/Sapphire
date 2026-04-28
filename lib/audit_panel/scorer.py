"""Risk scoring for audit panel findings."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass

from .heuristics import SEVERITY_ORDER, Finding, MergedPR, run_heuristics

SEVERITY_WEIGHTS = {
    "info": 0.02,
    "low": 0.08,
    "medium": 0.18,
    "high": 0.34,
    "critical": 0.55,
}


@dataclass(frozen=True)
class RiskScore:
    """Risk score for one merged PR."""

    pr_number: int
    score: float
    severity: str
    finding_count: int
    rule_ids: tuple[str, ...]

    def to_dict(self) -> dict:
        data = asdict(self)
        data["score"] = round(float(self.score), 4)
        data["rule_ids"] = list(self.rule_ids)
        return data


@dataclass(frozen=True)
class RiskHistogram:
    """Aggregate risk distribution for a panel run."""

    pr_count: int
    finding_count: int
    clean_count: int
    low: int = 0
    medium: int = 0
    high: int = 0
    critical: int = 0
    average_score: float = 0.0
    max_score: float = 0.0

    def to_dict(self) -> dict:
        data = asdict(self)
        data["average_score"] = round(float(self.average_score), 4)
        data["max_score"] = round(float(self.max_score), 4)
        return data


def score_findings(pr_number: int, findings: Iterable[Finding]) -> RiskScore:
    materialized = tuple(findings)
    if not materialized:
        return RiskScore(pr_number, 0.0, "info", 0, ())
    raw = sum(SEVERITY_WEIGHTS[finding.severity] * finding.confidence for finding in materialized)
    score = min(1.0, raw)
    severity = max(materialized, key=lambda item: SEVERITY_ORDER[item.severity]).severity
    return RiskScore(
        pr_number=pr_number,
        score=score,
        severity=severity,
        finding_count=len(materialized),
        rule_ids=tuple(finding.rule_id for finding in materialized),
    )


def score_pr(pr: MergedPR) -> RiskScore:
    return score_findings(pr.number, run_heuristics(pr))


def score_panel(prs: Iterable[MergedPR]) -> RiskHistogram:
    scores = [score_pr(pr) for pr in prs]
    if not scores:
        return RiskHistogram(pr_count=0, finding_count=0, clean_count=0)
    return RiskHistogram(
        pr_count=len(scores),
        finding_count=sum(score.finding_count for score in scores),
        clean_count=sum(1 for score in scores if score.finding_count == 0),
        low=sum(1 for score in scores if score.severity == "low"),
        medium=sum(1 for score in scores if score.severity == "medium"),
        high=sum(1 for score in scores if score.severity == "high"),
        critical=sum(1 for score in scores if score.severity == "critical"),
        average_score=sum(score.score for score in scores) / len(scores),
        max_score=max(score.score for score in scores),
    )
