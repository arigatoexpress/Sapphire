"""Tests for the audit_panel plugin tool."""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path

TOOLS = Path(__file__).parent.parent / "tools"
ROOT = TOOLS.parents[2]
if str(ROOT) in sys.path:
    sys.path.remove(str(ROOT))
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location(
    "audit_panel_tool", TOOLS / "internal" / "audit_panel.py"
)
audit_panel = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(audit_panel)


def test_pr_score_action_returns_score_and_findings():
    result = audit_panel.handle(
        {"action": "pr-score", "number": 1, "title": "feat: audit", "commits": ["feat: audit"]}
    )

    assert result["score"]["pr_number"] == 1
    assert result["findings"][0]["rule_id"] == "ci_skip_dropped"
    assert result["paste_safe"] is True


def test_pr_score_accepts_nested_pr_payload():
    result = audit_panel.handle(
        {
            "action": "pr-score",
            "pr": {
                "number": 2,
                "title": "feat: clean [skip ci]",
                "commits": ["feat: clean [skip ci]"],
            },
        }
    )

    assert result["score"]["score"] == 0


def test_histogram_action_scores_pr_list():
    result = audit_panel.handle(
        {
            "action": "histogram",
            "prs": [
                {
                    "number": 1,
                    "title": "feat: clean [skip ci]",
                    "commits": ["feat: clean [skip ci]"],
                },
                {"number": 2, "title": "feat: audit", "commits": ["feat: audit"]},
            ],
        }
    )

    assert result["histogram"]["pr_count"] == 2
    assert result["histogram"]["clean_count"] == 1


def test_histogram_rejects_non_list():
    result = audit_panel.handle({"action": "histogram", "prs": {}})

    assert "requires prs" in result["error"]


def test_latest_report_uses_cache_dir(tmp_path):
    path = tmp_path / "audit-panel-2026-04-28.json"
    path.write_text('{"ok": true}', encoding="utf-8")

    result = audit_panel.handle({"action": "latest-report", "cache_dir": str(tmp_path)})

    assert result["report"] == {"ok": True}
    assert result["caps"]["MAX_PRS_PER_RUN"] == 200


def test_run_once_disables_issue_publishing_by_default(monkeypatch, tmp_path):
    class FakeResult:
        def to_dict(self):
            return {"pr_count": 0, "finding_count": 0}

    seen = {}

    def fake_run_panel(**kwargs):
        seen.update(kwargs)
        return FakeResult()

    monkeypatch.setattr(audit_panel, "run_panel", fake_run_panel)

    result = audit_panel.handle({"action": "run-once", "cache_dir": str(tmp_path)})

    assert seen["open_issue"] is False
    assert result["read_only"] is True


def test_run_once_can_opt_into_issue_publishing(monkeypatch, tmp_path):
    class FakeResult:
        def to_dict(self):
            return {"pr_count": 0, "finding_count": 0}

    seen = {}
    monkeypatch.setattr(
        audit_panel, "run_panel", lambda **kwargs: seen.update(kwargs) or FakeResult()
    )

    audit_panel.handle({"action": "run-once", "cache_dir": str(tmp_path), "open_issue": True})

    assert seen["open_issue"] is True


def test_unknown_action_returns_error():
    result = audit_panel.handle({"action": "merge"})

    assert "unknown action" in result["error"]
    assert "run-once" in result["valid_actions"]


def test_run_returns_json_string():
    result = json.loads(
        audit_panel.run("pr-score", number=1, title="feat: audit", commits=["feat: audit"])
    )

    assert result["score"]["pr_number"] == 1


def test_main_rejects_invalid_json():
    out = io.StringIO()

    code = audit_panel.main(stream_in=io.StringIO("{bad"), stream_out=out)

    assert code == 2
    assert "invalid JSON" in out.getvalue()


def test_main_rejects_non_object_json():
    out = io.StringIO()

    code = audit_panel.main(stream_in=io.StringIO("[]"), stream_out=out)

    assert code == 2
    assert "stdin payload must be a JSON object" in out.getvalue()


def test_main_returns_nonzero_for_unknown_action():
    out = io.StringIO()

    code = audit_panel.main(stream_in=io.StringIO('{"action":"bogus"}'), stream_out=out)

    assert code == 1
    assert "unknown action" in out.getvalue()


def test_top_level_shim_exports_handle():
    spec = importlib.util.spec_from_file_location("audit_panel_shim", TOOLS / "audit_panel.py")
    shim = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(shim)

    assert hasattr(shim, "handle")
