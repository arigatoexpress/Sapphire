"""Tests for audit-panel scoring."""

from __future__ import annotations

from lib.audit_panel.heuristics import Finding, MergedPR
from lib.audit_panel.scorer import RiskHistogram, score_findings, score_panel, score_pr


def _finding(rule: str, severity: str, confidence: float = 1.0) -> Finding:
    return Finding(rule, severity, confidence, "summary", 1, "title")


def test_score_findings_clean_is_zero():
    score = score_findings(1, [])

    assert score.score == 0
    assert score.severity == "info"
    assert score.finding_count == 0


def test_score_findings_critical_is_higher_than_low():
    low = score_findings(1, [_finding("a", "low")])
    critical = score_findings(1, [_finding("a", "critical")])

    assert critical.score > low.score
    assert critical.severity == "critical"


def test_score_findings_caps_at_one():
    score = score_findings(1, [_finding(str(i), "critical") for i in range(5)])

    assert score.score == 1.0


def test_score_findings_preserves_rule_ids():
    score = score_findings(1, [_finding("oversize_diff", "medium"), _finding("ci_skip_dropped", "medium")])

    assert score.rule_ids == ("oversize_diff", "ci_skip_dropped")


def test_score_findings_confidence_reduces_weight():
    high = score_findings(1, [_finding("a", "high", 1.0)])
    low_conf = score_findings(1, [_finding("a", "high", 0.25)])

    assert low_conf.score < high.score


def test_score_pr_runs_heuristics():
    pr = MergedPR(2, "feat: audit", commits=("feat: audit",))

    score = score_pr(pr)

    assert score.pr_number == 2
    assert "ci_skip_dropped" in score.rule_ids


def test_score_pr_clean_with_skip_ci():
    pr = MergedPR(2, "feat: audit [skip ci]", commits=("feat: audit [skip ci]",))

    assert score_pr(pr).score == 0


def test_score_panel_empty():
    histogram = score_panel([])

    assert histogram == RiskHistogram(pr_count=0, finding_count=0, clean_count=0)


def test_score_panel_counts_clean_and_findings():
    prs = (
        MergedPR(1, "feat: clean [skip ci]", commits=("feat: clean [skip ci]",)),
        MergedPR(2, "feat: missing skip", commits=("feat: missing skip",)),
    )

    histogram = score_panel(prs)

    assert histogram.pr_count == 2
    assert histogram.clean_count == 1
    assert histogram.finding_count == 1


def test_score_panel_counts_severity_buckets():
    prs = (
        MergedPR(1, "feat: missing skip", commits=("feat: missing skip",)),
        MergedPR(2, "fix: safety [skip ci]", commits=("fix: safety [skip ci]",), changed_files=("lib/core/kill_switch.py",)),
    )

    histogram = score_panel(prs)

    assert histogram.medium == 1
    assert histogram.critical == 1


def test_score_panel_average_and_max():
    prs = (
        MergedPR(1, "feat: clean [skip ci]", commits=("feat: clean [skip ci]",)),
        MergedPR(2, "fix: safety [skip ci]", commits=("fix: safety [skip ci]",), changed_files=("lib/core/kill_switch.py",)),
    )

    histogram = score_panel(prs)

    assert histogram.max_score > histogram.average_score > 0


def test_risk_score_to_dict_rounds():
    score = score_findings(1, [_finding("a", "medium", 0.333333)])

    assert score.to_dict()["score"] == round(score.score, 4)


def test_histogram_to_dict_rounds():
    histogram = RiskHistogram(1, 1, 0, average_score=0.333333, max_score=0.999999)

    assert histogram.to_dict()["average_score"] == 0.3333
    assert histogram.to_dict()["max_score"] == 1.0


def test_score_findings_severity_uses_highest_seen():
    score = score_findings(1, [_finding("a", "low"), _finding("b", "high"), _finding("c", "medium")])

    assert score.severity == "high"
