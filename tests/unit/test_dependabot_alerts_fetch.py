"""Tests for ``scripts/ops/dependabot_alerts_fetch.py``.

The script wraps ``gh api`` so we mock the ``gh`` subprocess entirely. No
real network call ever fires from these tests. Coverage target: ≥ 8 cases.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_OPS = ROOT / "scripts" / "ops"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SCRIPTS_OPS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_OPS))

import dependabot_alerts_fetch as fetcher  # noqa: E402


def make_runner(responses):
    """Build a deterministic Runner that consumes a list of CommandResults
    in order. ``responses`` may be a list of ``CommandResult`` instances or
    callables ``(cmd) -> CommandResult``."""
    iterator = iter(responses)

    def _runner(cmd):
        try:
            response = next(iterator)
        except StopIteration as exc:
            raise AssertionError(f"Unexpected gh call: {cmd!r}") from exc
        if callable(response):
            return response(cmd)
        return response

    return _runner


# ── validate_gh_token ────────────────────────────────────────────────


def test_validate_gh_token_success():
    runner = make_runner([fetcher.CommandResult(returncode=0, stdout="Logged in to github.com")])
    fetcher.validate_gh_token(runner=runner)


def test_validate_gh_token_failure_raises_with_clean_detail():
    runner = make_runner([fetcher.CommandResult(returncode=1, stderr="not authenticated")])
    with pytest.raises(fetcher.DependabotFetchError) as exc_info:
        fetcher.validate_gh_token(runner=runner)
    msg = str(exc_info.value)
    assert "gh auth status failed" in msg
    assert "not authenticated" in msg


def test_validate_gh_token_truncates_excessive_output():
    """Defensive: a paranoid script should never let a leaked token blow up
    a stdout/stderr buffer past 256 chars."""
    long_blob = "X" * 5000
    runner = make_runner([fetcher.CommandResult(returncode=1, stderr=long_blob)])
    with pytest.raises(fetcher.DependabotFetchError) as exc_info:
        fetcher.validate_gh_token(runner=runner)
    # The error message body is truncated by the script.
    assert long_blob not in str(exc_info.value)


# ── fetch_alerts ─────────────────────────────────────────────────────


def test_fetch_alerts_returns_parsed_list():
    payload = [
        {
            "number": 1,
            "security_advisory": {"ghsa_id": "GHSA-xxxx-yyyy-zzzz", "severity": "HIGH"},
            "dependency": {"package": {"ecosystem": "pip", "name": "requests"}},
        }
    ]
    runner = make_runner([fetcher.CommandResult(returncode=0, stdout=json.dumps(payload))])
    out = fetcher.fetch_alerts(repo="acme/foo", runner=runner)
    assert len(out) == 1
    assert out[0]["security_advisory"]["ghsa_id"] == "GHSA-xxxx-yyyy-zzzz"


def test_fetch_alerts_rejects_bad_repo():
    runner = make_runner([])
    with pytest.raises(fetcher.DependabotFetchError):
        fetcher.fetch_alerts(repo="not-a-slash", runner=runner)


def test_fetch_alerts_rejects_bad_state():
    runner = make_runner([])
    with pytest.raises(fetcher.DependabotFetchError):
        fetcher.fetch_alerts(repo="acme/foo", state="bogus", runner=runner)


def test_fetch_alerts_handles_gh_error_envelope():
    """When dependabot is disabled gh returns ``{"message": "..."}``.
    We must surface this rather than silently emit []."""
    payload = {"message": "Dependabot alerts are disabled for this repository"}
    runner = make_runner([fetcher.CommandResult(returncode=0, stdout=json.dumps(payload))])
    with pytest.raises(fetcher.DependabotFetchError) as exc_info:
        fetcher.fetch_alerts(repo="acme/foo", runner=runner)
    assert "error envelope" in str(exc_info.value)


def test_fetch_alerts_handles_invalid_json():
    runner = make_runner([fetcher.CommandResult(returncode=0, stdout="{not json")])
    with pytest.raises(fetcher.DependabotFetchError) as exc_info:
        fetcher.fetch_alerts(repo="acme/foo", runner=runner)
    assert "invalid JSON" in str(exc_info.value)


def test_fetch_alerts_handles_gh_failure():
    runner = make_runner([fetcher.CommandResult(returncode=1, stderr="gh: missing scope")])
    with pytest.raises(fetcher.DependabotFetchError) as exc_info:
        fetcher.fetch_alerts(repo="acme/foo", runner=runner)
    assert "gh api dependabot/alerts failed" in str(exc_info.value)


# ── summarize ────────────────────────────────────────────────────────


def test_summarize_empty_returns_zero_buckets():
    summary = fetcher.summarize([])
    assert summary["total_open_alerts"] == 0
    assert summary["by_severity"] == {sev: 0 for sev in fetcher.SEVERITY_ORDER}
    assert summary["by_ecosystem"] == {}


def test_summarize_buckets_severities_correctly():
    alerts = [
        {
            "security_advisory": {"severity": "critical"},
            "dependency": {"package": {"ecosystem": "pip", "name": "a"}},
        },
        {
            "security_advisory": {"severity": "high"},
            "dependency": {"package": {"ecosystem": "pip", "name": "b"}},
        },
        {
            "security_advisory": {"severity": "high"},
            "dependency": {"package": {"ecosystem": "npm", "name": "c"}},
        },
        {
            "security_advisory": {"severity": "medium"},
            "dependency": {"package": {"ecosystem": "pip", "name": "a"}},
        },
        {
            "security_advisory": {"severity": "low"},
            "dependency": {"package": {"ecosystem": "pip", "name": "d"}},
        },
        {
            "security_advisory": {"severity": "weird"},
            "dependency": {"package": {"ecosystem": "go", "name": "e"}},
        },
    ]
    summary = fetcher.summarize(alerts)
    assert summary["total_open_alerts"] == 6
    assert summary["by_severity"]["critical"] == 1
    assert summary["by_severity"]["high"] == 2
    assert summary["by_severity"]["medium"] == 1
    assert summary["by_severity"]["low"] == 1
    # Unknown bucket catches the "weird" severity.
    assert summary["by_severity"]["unknown"] == 1
    # Ecosystem distribution.
    assert summary["by_ecosystem"]["pip"] == 4
    assert summary["by_ecosystem"]["npm"] == 1
    assert summary["by_ecosystem"]["go"] == 1


def test_summarize_top_packages_capped_at_limit():
    alerts = [
        {
            "security_advisory": {"severity": "high"},
            "dependency": {"package": {"ecosystem": "pip", "name": f"pkg{i % 3}"}},
        }
        for i in range(20)
    ]
    summary = fetcher.summarize(alerts)
    assert summary["total_open_alerts"] == 20
    # Only the top N (default 10) packages survive — but with only 3 unique
    # names we get exactly 3 entries.
    assert len(summary["top_packages"]) == 3


# ── render_markdown ──────────────────────────────────────────────────


def test_render_markdown_zero_alerts_emits_clear_signal():
    summary = fetcher.summarize([])
    md = fetcher.render_markdown("acme/foo", [], summary)
    assert "Dependabot alerts" in md
    assert "Total open: **0**" in md
    assert "No open Dependabot alerts" in md


def test_render_markdown_includes_severity_buckets():
    alerts = [
        {
            "number": 7,
            "security_advisory": {
                "ghsa_id": "GHSA-AAAA",
                "severity": "critical",
                "summary": "Big problem",
            },
            "dependency": {"package": {"ecosystem": "pip", "name": "requests"}},
        },
    ]
    summary = fetcher.summarize(alerts)
    md = fetcher.render_markdown("acme/foo", alerts, summary)
    assert "GHSA-AAAA" in md
    assert "critical" in md
    assert "pip:requests" in md
    assert "Big problem" in md


def test_render_markdown_escapes_pipe_characters():
    """Markdown table cells must escape ``|`` so we don't break the table."""
    alerts = [
        {
            "security_advisory": {
                "ghsa_id": "GHSA-X|Y",
                "severity": "high",
                "summary": "summary | with | pipes",
            },
            "dependency": {"package": {"ecosystem": "pip", "name": "p"}},
        }
    ]
    summary = fetcher.summarize(alerts)
    md = fetcher.render_markdown("acme/foo", alerts, summary)
    assert "GHSA-X\\|Y" in md
    assert "summary \\| with \\| pipes" in md


# ── fetch_and_render end-to-end with mocked gh ──────────────────────


def test_fetch_and_render_pipeline_happy_path():
    auth_ok = fetcher.CommandResult(returncode=0, stdout="Logged in")
    alerts_payload = [
        {
            "number": 1,
            "security_advisory": {"ghsa_id": "GHSA-1", "severity": "high", "summary": "x"},
            "dependency": {"package": {"ecosystem": "pip", "name": "requests"}},
        },
        {
            "number": 2,
            "security_advisory": {"ghsa_id": "GHSA-2", "severity": "medium", "summary": "y"},
            "dependency": {"package": {"ecosystem": "pip", "name": "urllib3"}},
        },
    ]
    api = fetcher.CommandResult(returncode=0, stdout=json.dumps(alerts_payload))
    runner = make_runner([auth_ok, api])
    result = fetcher.fetch_and_render(repo="acme/foo", runner=runner)
    assert result["alerts_count"] == 2
    assert result["summary"]["by_severity"]["high"] == 1
    assert result["summary"]["by_severity"]["medium"] == 1
    assert "GHSA-1" in result["markdown"]
    assert "GHSA-2" in result["markdown"]


def test_fetch_and_render_pipeline_raises_on_auth_failure():
    auth_fail = fetcher.CommandResult(returncode=1, stderr="not logged in")
    runner = make_runner([auth_fail])
    with pytest.raises(fetcher.DependabotFetchError):
        fetcher.fetch_and_render(repo="acme/foo", runner=runner)


def test_main_writes_json_envelope_on_success(capsys):
    auth_ok = fetcher.CommandResult(returncode=0, stdout="Logged in")
    api = fetcher.CommandResult(returncode=0, stdout="[]")
    runner = make_runner([auth_ok, api])
    rc = fetcher.main(["--repo", "acme/foo"], runner=runner)
    assert rc == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["alerts_count"] == 0
    assert payload["repo"] == "acme/foo"
    assert "markdown" in payload


def test_main_returns_2_on_error(capsys):
    auth_fail = fetcher.CommandResult(returncode=1, stderr="not authenticated")
    runner = make_runner([auth_fail])
    rc = fetcher.main(["--repo", "acme/foo"], runner=runner)
    assert rc == 2
    captured = capsys.readouterr()
    assert "dependabot-alerts-fetch error" in captured.err


def test_main_markdown_only_emits_only_markdown(capsys):
    auth_ok = fetcher.CommandResult(returncode=0, stdout="Logged in")
    api = fetcher.CommandResult(returncode=0, stdout="[]")
    runner = make_runner([auth_ok, api])
    rc = fetcher.main(["--repo", "acme/foo", "--markdown-only"], runner=runner)
    assert rc == 0
    captured = capsys.readouterr()
    # Output is raw markdown — not JSON.
    with pytest.raises(json.JSONDecodeError):
        json.loads(captured.out)
    assert "Dependabot alerts" in captured.out


def test_main_json_only_excludes_markdown(capsys):
    auth_ok = fetcher.CommandResult(returncode=0, stdout="Logged in")
    api = fetcher.CommandResult(returncode=0, stdout="[]")
    runner = make_runner([auth_ok, api])
    rc = fetcher.main(["--repo", "acme/foo", "--json-only"], runner=runner)
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert "markdown" not in payload
    assert payload["repo"] == "acme/foo"
