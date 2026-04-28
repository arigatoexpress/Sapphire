"""Tests for pure audit-panel heuristics."""

from __future__ import annotations

from lib.audit_panel.heuristics import MergedPR, Review, run_heuristics


def _rules(pr: MergedPR) -> set[str]:
    return {finding.rule_id for finding in run_heuristics(pr)}


def test_oversize_diff_trips_only_when_lines_and_file_count_cross_threshold():
    pr = MergedPR(1, "feat: giant lane [skip ci]", additions=1901, deletions=200, changed_files=tuple(f"lib/x/{i}.py" for i in range(16)), commits=("feat: giant lane [skip ci]",))

    assert "oversize_diff" in _rules(pr)


def test_oversize_diff_ignores_large_line_count_with_few_files():
    pr = MergedPR(1, "feat: generated docs [skip ci]", additions=2500, changed_files=("docs/a.md",), commits=("feat: generated docs [skip ci]",))

    assert "oversize_diff" not in _rules(pr)


def test_oversize_diff_ignores_many_files_with_small_delta():
    pr = MergedPR(1, "chore: touch fixtures [skip ci]", additions=20, deletions=20, changed_files=tuple(f"tests/{i}.py" for i in range(20)), commits=("chore: touch fixtures [skip ci]",))

    assert "oversize_diff" not in _rules(pr)


def test_weak_commit_message_trips_on_wip():
    pr = MergedPR(2, "feat: real title [skip ci]", commits=("wip",))

    assert "weak_commit_message" in _rules(pr)


def test_weak_commit_message_trips_on_short_subject():
    pr = MergedPR(2, "feat: real title [skip ci]", commits=("fix bug [skip ci]", "tiny"))

    assert "weak_commit_message" in _rules(pr)


def test_weak_commit_message_accepts_specific_subject():
    pr = MergedPR(2, "feat: audit panel [skip ci]", commits=("feat: audit panel scoring [skip ci]",))

    assert "weak_commit_message" not in _rules(pr)


def test_kill_switch_touch_without_owner_review_is_critical():
    pr = MergedPR(3, "fix: safety control [skip ci]", changed_files=("lib/core/kill_switch.py",), commits=("fix: safety control [skip ci]",))

    findings = run_heuristics(pr)

    assert "kill_switch_touched_without_review" in {finding.rule_id for finding in findings}
    assert [finding.severity for finding in findings if finding.rule_id == "kill_switch_touched_without_review"] == ["critical"]


def test_kill_switch_touch_with_owner_review_is_clean_for_that_rule():
    pr = MergedPR(
        3,
        "fix: safety control [skip ci]",
        changed_files=("lib/core/kill_switch.py",),
        commits=("fix: safety control [skip ci]",),
        reviews=(Review("arigatoexpress", "APPROVED"),),
    )

    assert "kill_switch_touched_without_review" not in _rules(pr)


def test_kill_switch_rule_ignores_unrelated_core_file():
    pr = MergedPR(3, "fix: heartbeat [skip ci]", changed_files=("lib/core/heartbeat.py",), commits=("fix: heartbeat [skip ci]",))

    assert "kill_switch_touched_without_review" not in _rules(pr)


def test_tests_missing_for_new_lib_module_trips():
    pr = MergedPR(4, "feat: audit library [skip ci]", changed_files=("lib/audit_panel/heuristics.py",), commits=("feat: audit library [skip ci]",))

    assert "tests_missing_for_new_module" in _rules(pr)


def test_tests_missing_for_new_lib_module_accepts_matching_unit_test():
    pr = MergedPR(
        4,
        "feat: audit library [skip ci]",
        changed_files=("lib/audit_panel/heuristics.py", "tests/unit/test_heuristics.py"),
        commits=("feat: audit library [skip ci]",),
    )

    assert "tests_missing_for_new_module" not in _rules(pr)


def test_tests_missing_for_plugin_accepts_plugin_test():
    pr = MergedPR(
        4,
        "feat: audit plugin [skip ci]",
        changed_files=("plugins/claw-sapphire/tools/internal/audit_panel.py", "plugins/claw-sapphire/tests/test_audit_panel.py"),
        commits=("feat: audit plugin [skip ci]",),
    )

    assert "tests_missing_for_new_module" not in _rules(pr)


def test_scope_creep_trips_when_narrow_title_touches_many_areas():
    pr = MergedPR(
        5,
        "fix: dashboard card [skip ci]",
        changed_files=("lib/a/a.py", "services/b/run.py", "docs/c.md", "infra/x.yaml", "plugins/claw-sapphire/tools/x.py"),
        commits=("fix: dashboard card [skip ci]",),
    )

    assert "scope_creep" in _rules(pr)


def test_scope_creep_allows_broad_integration_title():
    pr = MergedPR(
        5,
        "feat: tranche integration sweep [skip ci]",
        changed_files=("lib/a/a.py", "services/b/run.py", "docs/c.md", "infra/x.yaml", "plugins/claw-sapphire/tools/x.py"),
        commits=("feat: tranche integration sweep [skip ci]",),
    )

    assert "scope_creep" not in _rules(pr)


def test_scope_creep_allows_small_surface():
    pr = MergedPR(5, "fix: dashboard card [skip ci]", changed_files=("services/dashboard/app.py", "tests/unit/test_dashboard.py"), commits=("fix: dashboard card [skip ci]",))

    assert "scope_creep" not in _rules(pr)


def test_secret_signature_trips_on_key_like_diff_metadata():
    pr = MergedPR(6, "fix: config [skip ci]", commits=("fix: config [skip ci]",), diff_snippets=("OPENAI_API_KEY=sk-abcdefghijklmnopqrstuvwxyz",))

    assert "secret_signature" in _rules(pr)


def test_secret_signature_trips_on_private_key_marker():
    pr = MergedPR(6, "fix: config [skip ci]", commits=("fix: config [skip ci]",), diff_snippets=("-----BEGIN PRIVATE KEY-----",))

    assert "secret_signature" in _rules(pr)


def test_secret_signature_ignores_placeholder():
    pr = MergedPR(6, "docs: config example [skip ci]", commits=("docs: config example [skip ci]",), diff_snippets=("OPENAI_API_KEY=<set-in-env>",))

    assert "secret_signature" not in _rules(pr)


def test_provenance_missing_trips_for_data_json():
    pr = MergedPR(7, "feat: artifact [skip ci]", commits=("feat: artifact [skip ci]",), changed_files=("data/a/report.json",))

    assert "provenance_envelope_missing" in _rules(pr)


def test_provenance_missing_accepts_sibling_sidecar():
    pr = MergedPR(7, "feat: artifact [skip ci]", commits=("feat: artifact [skip ci]",), changed_files=("data/a/report.json", "data/a/report.json.envelope.json"))

    assert "provenance_envelope_missing" not in _rules(pr)


def test_provenance_missing_ignores_non_data_json():
    pr = MergedPR(7, "test: fixture [skip ci]", commits=("test: fixture [skip ci]",), changed_files=("tests/fixtures/report.json",))

    assert "provenance_envelope_missing" not in _rules(pr)


def test_failed_check_overridden_trips_on_failure():
    pr = MergedPR(8, "fix: bypass [skip ci]", commits=("fix: bypass [skip ci]",), status_conclusion="FAILURE")

    assert "failed_check_overridden" in _rules(pr)


def test_failed_check_overridden_trips_on_timeout():
    pr = MergedPR(8, "fix: bypass [skip ci]", commits=("fix: bypass [skip ci]",), status_conclusion="TIMED_OUT")

    assert "failed_check_overridden" in _rules(pr)


def test_failed_check_overridden_ignores_success():
    pr = MergedPR(8, "fix: normal [skip ci]", commits=("fix: normal [skip ci]",), status_conclusion="SUCCESS")

    assert "failed_check_overridden" not in _rules(pr)


def test_ci_skip_dropped_trips_when_no_subject_has_token():
    pr = MergedPR(9, "feat: audit panel", commits=("feat: audit panel",))

    assert "ci_skip_dropped" in _rules(pr)


def test_ci_skip_dropped_accepts_pr_title_token():
    pr = MergedPR(9, "feat: audit panel [skip ci]", commits=("feat: audit panel",))

    assert "ci_skip_dropped" not in _rules(pr)


def test_ci_skip_dropped_accepts_commit_token():
    pr = MergedPR(9, "feat: audit panel", commits=("feat: audit panel [skip ci]",))

    assert "ci_skip_dropped" not in _rules(pr)


def test_run_heuristics_orders_critical_before_medium():
    pr = MergedPR(
        10,
        "fix",
        changed_files=("lib/core/kill_switch.py",),
        commits=("fix",),
        status_conclusion="FAILURE",
    )

    findings = run_heuristics(pr)

    assert findings[0].severity == "critical"
    assert len(findings) >= 3
