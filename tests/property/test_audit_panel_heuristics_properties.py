"""Property-based tests for ``lib.audit_panel.heuristics``.

The audit panel heuristics drive the autonomous merge gate — every clean
PR must pass without manual review, every dirty one must trigger a
finding. The properties below pin both directions:

* **Each heuristic is monotone in its trigger condition** — adding more
  triggering signal cannot produce zero findings, removing all signal
  cannot produce a finding.
* **No false-trips on synthetically clean PRs** — a fully scrubbed PR
  fixture must yield zero findings under ``run_heuristics``.
* **Reporter output is paste-safe** — Markdown rendering never includes
  raw secret-looking strings (the ``_safe`` redactor scrubs them).
* **Severity ordering** — ``run_heuristics`` returns findings sorted
  critical → high → medium → low → info.
* **Bounded evidence** — every finding's ``evidence`` field has at most
  ``MAX_EVIDENCE_ITEMS`` entries.
* **Determinism** — two runs of the same PR yield identical findings.

The fixtures below intentionally avoid the ``MergedPR.from_dict`` parser
so we exercise the dataclass field surface directly.
"""

from __future__ import annotations

import sys
from pathlib import Path

from hypothesis import HealthCheck, given
from hypothesis import settings as hyp_settings
from hypothesis import strategies as st

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tests.property  # noqa: E402, F401
from lib.audit_panel.heuristics import (  # noqa: E402
    MAX_EVIDENCE_ITEMS,
    OVERSIZE_FILES_CHANGED,
    OVERSIZE_LINES_CHANGED,
    SENSITIVE_CONTROL_PATHS,
    SEVERITY_ORDER,
    MergedPR,
    Review,
    ci_skip_dropped,
    failed_check_overridden,
    findings_by_severity,
    kill_switch_touched_without_review,
    oversize_diff,
    provenance_envelope_missing,
    run_heuristics,
    scope_creep,
    secret_signature,
    weak_commit_message,
)

# Import under an alias so pytest does not try to collect ``test_*`` named
# functions as standalone test cases.
from lib.audit_panel.heuristics import (  # noqa: E402
    tests_missing_for_new_module as _tests_missing_for_new_module_heuristic,
)
from lib.audit_panel.reporter import render_markdown_report  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _clean_pr(**overrides) -> MergedPR:  # type: ignore[no-untyped-def]
    """Construct a deliberately-clean MergedPR — no heuristic should trip."""
    base = dict(
        number=42,
        title="feat(intel): SEC filings + earnings call layer 0.1.0 [skip ci]",
        url="https://github.com/arigatoexpress/Sapphire/pull/42",
        author="arigatoexpress",
        merged_at="2026-04-29T10:00:00Z",
        merge_commit="abcdef0123456789",
        additions=120,
        deletions=20,
        changed_files=(
            "lib/intel/sec_filings.py",
            "tests/unit/test_sec_filings.py",
        ),
        commits=("feat(intel): SEC filings layer 0.1.0 [skip ci]",),
        reviews=(),
        status_conclusion="SUCCESS",
        diff_snippets=(),
        labels=(),
    )
    base.update(overrides)
    return MergedPR(**base)


# ---------------------------------------------------------------------------
# 1. No false-trips on a clean PR
# ---------------------------------------------------------------------------


def test_clean_pr_has_no_findings() -> None:
    findings = run_heuristics(_clean_pr())
    assert findings == ()


# ---------------------------------------------------------------------------
# 2. Oversize-diff trigger is monotone in lines + files changed
# ---------------------------------------------------------------------------


@given(
    st.integers(min_value=0, max_value=10_000),
    st.integers(min_value=0, max_value=50),
)
def test_oversize_diff_trigger_monotone(adds: int, files: int) -> None:
    pr = _clean_pr(
        additions=adds,
        deletions=0,
        changed_files=tuple(f"lib/intel/feat_{i}.py" for i in range(files)),
    )
    finding = oversize_diff(pr)
    if adds > OVERSIZE_LINES_CHANGED and files > OVERSIZE_FILES_CHANGED:
        assert finding is not None
        assert finding.severity == "medium"
    else:
        assert finding is None


# ---------------------------------------------------------------------------
# 3. weak_commit_message catches every short subject
# ---------------------------------------------------------------------------


@given(
    st.lists(
        st.text(min_size=0, max_size=80),
        min_size=1,
        max_size=8,
    )
)
def test_weak_commit_message_catches_short_subjects(commits: list[str]) -> None:
    pr = _clean_pr(commits=tuple(commits))
    finding = weak_commit_message(pr)
    has_weak = any(
        len(subject.strip()) < 10 or subject.strip().lower() in {"wip", "fix", "update", "misc"}
        for subject in commits
    )
    if has_weak:
        assert finding is not None
        assert finding.severity == "low"
    else:
        assert finding is None


# ---------------------------------------------------------------------------
# 4. kill_switch_touched_without_review trips iff sensitive path is touched
#    AND owner did not review
# ---------------------------------------------------------------------------


@given(
    st.lists(
        st.sampled_from(sorted(SENSITIVE_CONTROL_PATHS)),
        min_size=1,
        max_size=3,
        unique=True,
    ),
    st.booleans(),
)
def test_kill_switch_finding_requires_owner_review(
    touched: list[str], owner_approved: bool
) -> None:
    reviews = (
        (Review(author="arigatoexpress", state="APPROVED"),)
        if owner_approved
        else (Review(author="someotheruser", state="APPROVED"),)
    )
    pr = _clean_pr(changed_files=tuple(touched), reviews=reviews)
    finding = kill_switch_touched_without_review(pr)
    if owner_approved:
        assert finding is None
    else:
        assert finding is not None
        assert finding.severity == "critical"


# ---------------------------------------------------------------------------
# 5. tests_missing_for_new_module catches added module without companion test
# ---------------------------------------------------------------------------


@given(st.booleans())
def test_tests_missing_finding_monotone(has_companion_test: bool) -> None:
    files = ["lib/intel/new_module.py"]
    if has_companion_test:
        files.append("tests/unit/test_new_module.py")
    pr = _clean_pr(changed_files=tuple(files))
    finding = _tests_missing_for_new_module_heuristic(pr)
    if has_companion_test:
        assert finding is None
    else:
        assert finding is not None
        assert finding.severity == "high"


# ---------------------------------------------------------------------------
# 6. Secret-signature heuristic catches token-shaped payloads
# ---------------------------------------------------------------------------


@given(
    st.sampled_from(
        [
            "api_key = 'sk-abcdefghijklmnopqrstuvwxyz0123'",
            "secret: ghp_AbCdEfGhIjKlMnOpQrStUvWxYz0123",
            "-----BEGIN RSA PRIVATE KEY-----",
            "token=xoxb-1234567890-AbCdEfGhIjKlMn",
            "private_key='OPENSSH-LIKE-VALUE-HERE-1234567890'",
        ]
    )
)
def test_secret_signature_finding_catches_token_shapes(snippet: str) -> None:
    pr = _clean_pr(diff_snippets=(snippet,))
    finding = secret_signature(pr)
    assert finding is not None
    assert finding.severity == "critical"
    # Reporter paste-safety: the rendered Markdown must not include the raw
    # token snippet — only the placeholder summary.
    md = render_markdown_report([pr])
    assert snippet not in md, "Reporter leaked secret signature into output"


@given(st.text(min_size=0, max_size=80))
def test_secret_signature_does_not_false_trip_on_clean_text(text: str) -> None:
    """Clean prose without a credential shape must not trigger secret_signature."""
    # Filter out any input that happens to match the regex by accident.
    from lib.audit_panel.heuristics import SECRET_SIGNATURE_RE

    if SECRET_SIGNATURE_RE.search(text):
        return  # hypothesis happened to generate a credential-shaped string
    pr = _clean_pr(diff_snippets=(text,))
    finding = secret_signature(pr)
    assert finding is None


# ---------------------------------------------------------------------------
# 7. failed_check_overridden trips iff status conclusion is failure-shaped
# ---------------------------------------------------------------------------


@given(
    st.sampled_from(
        ["SUCCESS", "FAILURE", "FAILED", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED", None]
    )
)
def test_failed_check_overridden(conclusion: str | None) -> None:
    pr = _clean_pr(status_conclusion=conclusion)
    finding = failed_check_overridden(pr)
    if conclusion in {"FAILURE", "FAILED", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED"}:
        assert finding is not None
        assert finding.severity == "critical"
    else:
        assert finding is None


# ---------------------------------------------------------------------------
# 8. ci_skip_dropped trips when neither title nor commits contain [skip ci]
# ---------------------------------------------------------------------------


@given(st.booleans(), st.booleans())
def test_ci_skip_dropped_finding(in_title: bool, in_commits: bool) -> None:
    title = "feat: shipped new thing"
    if in_title:
        title += " [skip ci]"
    commits = (("real subject\n\n[skip ci]" if in_commits else "real subject"),)
    pr = _clean_pr(title=title, commits=commits)
    finding = ci_skip_dropped(pr)
    if in_title or in_commits:
        assert finding is None
    else:
        assert finding is not None
        assert finding.severity == "medium"


# ---------------------------------------------------------------------------
# 9. Reporter output is paste-safe and bounded
# ---------------------------------------------------------------------------


def test_reporter_output_size_bounded() -> None:
    """Even a giant PR list must respect MAX_REPORT_BYTES."""
    prs = [
        _clean_pr(
            number=i,
            title=f"feat(intel): big feature #{i} [skip ci]",
            additions=200,
            deletions=20,
            changed_files=tuple(f"lib/intel/x_{j}.py" for j in range(3)),
        )
        for i in range(50)
    ]
    md = render_markdown_report(prs)
    # Configured cap is 50_000 bytes; ensure we stay under.
    assert len(md.encode("utf-8")) <= 50_000


@given(
    st.lists(
        st.text(min_size=0, max_size=200),
        min_size=0,
        max_size=10,
    )
)
@hyp_settings(suppress_health_check=[HealthCheck.too_slow])
def test_reporter_redacts_credential_signatures(texts: list[str]) -> None:
    """The reporter's _safe helper must redact api_key= / secret= / token= /
    password= patterns regardless of input source."""
    pr = _clean_pr(
        title=" ".join(["api_key=SECRETVALUE", *texts])[:160],
        diff_snippets=tuple(f"api_key=topsecret_{i}" for i in range(5)),
    )
    md = render_markdown_report([pr])
    # The redacted pattern must show up in the Markdown.
    assert "[redacted]" in md
    assert "SECRETVALUE" not in md


# ---------------------------------------------------------------------------
# 10. run_heuristics ordering — critical first
# ---------------------------------------------------------------------------


def test_run_heuristics_orders_by_severity_descending() -> None:
    """A PR triggering multiple heuristics must list critical before lower."""
    pr = _clean_pr(
        title="wip",  # weak (low)
        commits=("wip",),
        changed_files=("lib/core/kill_switch.py",),  # critical
        reviews=(Review(author="someone", state="APPROVED"),),
    )
    findings = run_heuristics(pr)
    # ``ci_skip_dropped`` will trip too — that's fine.
    assert findings, "expected some findings"
    severities = [SEVERITY_ORDER[f.severity] for f in findings]
    assert severities == sorted(severities, reverse=True), (
        f"findings not sorted critical-first: {severities}"
    )


# ---------------------------------------------------------------------------
# 11. Evidence is always bounded
# ---------------------------------------------------------------------------


@given(st.integers(min_value=1, max_value=30))
def test_evidence_count_bounded(num_files: int) -> None:
    files = tuple(f"lib/intel/m_{i}.py" for i in range(num_files))
    pr = _clean_pr(changed_files=files)
    finding = _tests_missing_for_new_module_heuristic(pr)
    if finding is not None:
        assert len(finding.evidence) <= MAX_EVIDENCE_ITEMS


# ---------------------------------------------------------------------------
# 12. Findings are deterministic
# ---------------------------------------------------------------------------


def test_run_heuristics_deterministic() -> None:
    pr = _clean_pr(
        title="wip",
        commits=("wip",),
        diff_snippets=("api_key='sk-aaaaaaaaaaaaaaaaaaaaaa'",),
    )
    a = run_heuristics(pr)
    b = run_heuristics(pr)
    assert a == b


# ---------------------------------------------------------------------------
# 13. findings_by_severity is a histogram covering every severity level
# ---------------------------------------------------------------------------


def test_findings_by_severity_includes_zero_buckets() -> None:
    findings = ()
    histogram = findings_by_severity(findings)
    assert set(histogram.keys()) == set(SEVERITY_ORDER.keys())
    assert all(v == 0 for v in histogram.values())


# ---------------------------------------------------------------------------
# 14. provenance_envelope_missing trips when data/ JSON without sidecar
# ---------------------------------------------------------------------------


@given(st.booleans())
def test_provenance_envelope_missing_finding(has_envelope: bool) -> None:
    files = ["data/intelligence/2026-04-29/predictions.json"]
    if has_envelope:
        files.append("data/intelligence/2026-04-29/predictions.json.envelope.json")
    pr = _clean_pr(changed_files=tuple(files))
    finding = provenance_envelope_missing(pr)
    if has_envelope:
        assert finding is None
    else:
        assert finding is not None
        assert finding.severity == "high"


# ---------------------------------------------------------------------------
# 15. scope_creep does not trip on small or honest broad PRs
# ---------------------------------------------------------------------------


def test_scope_creep_skips_honest_broad_prs() -> None:
    """A ``tranche`` titled PR spanning many areas is still legal."""
    files = (
        "lib/intel/a.py",
        "lib/audit_panel/b.py",
        "lib/security/c.py",
        "lib/correlator/d.py",
        "services/dashboard/e.py",
        "tests/unit/test_a.py",
    )
    pr = _clean_pr(
        title="chore(tranche): tranche 6 readiness pass [skip ci]",
        changed_files=files,
        commits=("chore(tranche): tranche 6 readiness pass [skip ci]",),
    )
    finding = scope_creep(pr)
    assert finding is None


def test_scope_creep_trips_on_narrow_title_with_broad_diff() -> None:
    files = (
        "lib/intel/a.py",
        "lib/audit_panel/b.py",
        "lib/security/c.py",
        "lib/correlator/d.py",
        "services/dashboard/e.py",
    )
    pr = _clean_pr(
        title="fix(intel): one tiny intel fix",
        changed_files=files,
        commits=("fix(intel): one tiny intel fix",),
    )
    finding = scope_creep(pr)
    assert finding is not None
    assert finding.severity == "medium"
