"""Unit tests for the Telegram content-approval bridge.

Covers the inline-keyboard request flow, the callback handler (approve /
reject / view), and graceful degradation when Telegram is unreachable.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from lib.content import telegram_approval as ta  # noqa: E402


@pytest.fixture
def tmp_content(monkeypatch, tmp_path):
    """Rewire all data/content/* paths onto a tmp dir."""
    pending = tmp_path / "pending"
    ready = tmp_path / "ready"
    rejected = tmp_path / "rejected"
    approvals = tmp_path / "approvals.jsonl"
    pending.mkdir()
    monkeypatch.setattr(ta, "_PENDING_DIR", pending)
    monkeypatch.setattr(ta, "_READY_DIR", ready)
    monkeypatch.setattr(ta, "_REJECTED_DIR", rejected)
    monkeypatch.setattr(ta, "_APPROVALS_FILE", approvals)
    return {"pending": pending, "ready": ready, "rejected": rejected, "approvals": approvals}


def _seed_pending(tmp_content: dict, slug: str, body: str = "body text"):
    path = tmp_content["pending"] / f"20260420_120000_{slug}.json"
    path.write_text(json.dumps({"kind": slug.replace("-", "_"), "body": body}))
    return path


class TestKeyboardBuilder:
    def test_two_row_layout(self):
        kb = ta.build_keyboard("weekly-crypto-brief")
        assert "inline_keyboard" in kb
        rows = kb["inline_keyboard"]
        assert len(rows) == 2
        assert [b["text"] for b in rows[0]] == ["✅ Approve", "❌ Reject"]
        assert rows[1][0]["text"] == "📄 View Draft"

    def test_callback_data_under_64_bytes(self):
        # Telegram hard limit is 64 bytes for callback_data.
        kb = ta.build_keyboard("a" * 50)  # way longer than any real slug
        for row in kb["inline_keyboard"]:
            for btn in row:
                assert len(btn["callback_data"].encode()) < 64


class TestRequestApproval:
    def test_truncates_long_preview(self, monkeypatch):
        captured = {}

        def fake_send(text, **kwargs):
            captured["text"] = text
            captured["kwargs"] = kwargs
            return {"ok": True}

        fake_ss = type("FakeSS", (), {"send": staticmethod(fake_send)})()
        monkeypatch.setattr(ta, "_safe_send", lambda: fake_ss)

        ta.request_approval(
            kind="weekly_crypto_brief",
            title="Weekly Crypto Brief",
            slug="weekly-crypto-brief",
            preview="x" * 5000,
        )
        # Body should be clipped to ~800 chars + ellipsis
        assert "…" in captured["text"]
        assert len(captured["text"]) < 1200
        assert captured["kwargs"]["reply_markup"]["inline_keyboard"][0][0]["text"] == "✅ Approve"


class TestHandleCallback:
    def test_malformed_payload(self, tmp_content):
        result = ta.handle_callback("no-colon-here")
        assert result["ok"] is False
        assert result["error"] == "malformed_callback"

    def test_unknown_action(self, tmp_content):
        result = ta.handle_callback("xyz:foo")
        assert result["ok"] is False
        assert result["error"] == "unknown_action"

    def test_draft_not_found_answers_callback(self, tmp_content, monkeypatch):
        answered = {}
        monkeypatch.setattr(
            ta,
            "_answer_callback",
            lambda cid, text, bot_token=None: answered.update(id=cid, text=text) or {"ok": True},
        )
        result = ta.handle_callback("apv:missing-slug", callback_id="cb1")
        assert result["ok"] is False
        assert result["error"] == "not_found"
        assert answered["id"] == "cb1"

    def test_approve_moves_to_ready_and_logs(self, tmp_content, monkeypatch):
        pending = _seed_pending(tmp_content, "weekly-crypto-brief")
        monkeypatch.setattr(ta, "_answer_callback", lambda *a, **k: {"ok": True})
        monkeypatch.setattr(ta, "_edit_message", lambda *a, **k: {"ok": True})

        result = ta.handle_callback(
            "apv:weekly-crypto-brief",
            callback_id="cb1",
            chat_id=123,
            message_id=456,
            actor="ari",
        )
        assert result["ok"] is True
        assert result["status"] == "approved"
        assert not pending.exists(), "pending file should be moved"
        ready_files = list(tmp_content["ready"].iterdir())
        assert len(ready_files) == 1
        # Approval record written
        assert tmp_content["approvals"].exists()
        record = json.loads(tmp_content["approvals"].read_text().strip())
        assert record["status"] == "approved"
        assert record["approved_by"] == "ari"
        assert record["slug"] == "weekly-crypto-brief"

    def test_reject_moves_to_rejected(self, tmp_content, monkeypatch):
        pending = _seed_pending(tmp_content, "ai-intel")
        monkeypatch.setattr(ta, "_answer_callback", lambda *a, **k: {"ok": True})
        monkeypatch.setattr(ta, "_edit_message", lambda *a, **k: {"ok": True})

        result = ta.handle_callback("rej:ai-intel", callback_id="cb2", actor="ari")
        assert result["status"] == "rejected"
        assert not pending.exists()
        rejected_files = list(tmp_content["rejected"].iterdir())
        assert len(rejected_files) == 1
        record = json.loads(tmp_content["approvals"].read_text().strip())
        assert record["status"] == "rejected"

    def test_view_sends_preview_does_not_move(self, tmp_content, monkeypatch):
        pending = _seed_pending(tmp_content, "security-digest", body="secret body " * 200)
        sent = {}

        def fake_send(text, **kwargs):
            sent["text"] = text
            sent["banner"] = kwargs.get("banner")
            return {"ok": True}

        fake_ss = type("FakeSS", (), {"send": staticmethod(fake_send)})()
        monkeypatch.setattr(ta, "_safe_send", lambda: fake_ss)
        monkeypatch.setattr(ta, "_answer_callback", lambda *a, **k: {"ok": True})

        result = ta.handle_callback("vw:security-digest", callback_id="cb3")
        assert result["status"] == "viewed"
        assert pending.exists(), "view must not consume the pending draft"
        assert "secret body" in sent["text"]
        assert "security-digest" in sent["banner"]

    def test_approve_succeeds_even_if_edit_fails(self, tmp_content, monkeypatch):
        """Telegram edit can fail; the filesystem side effect must still win."""
        _seed_pending(tmp_content, "market-pulse")
        monkeypatch.setattr(ta, "_answer_callback", lambda *a, **k: {"ok": True})

        def fake_edit(*a, **k):
            raise RuntimeError("telegram 500")

        monkeypatch.setattr(ta, "_edit_message", fake_edit)
        # The outer handle_callback doesn't catch edit errors — but real prod
        # wraps this in a try. For now verify the sequence: approve first, edit last.
        with pytest.raises(RuntimeError):
            ta.handle_callback("apv:market-pulse", callback_id="cb4", chat_id=1, message_id=2)
        # Draft should still be in ready/ because move happens before edit
        assert list(tmp_content["ready"].iterdir())


class TestApprovalIntegration:
    """End-to-end: approval.approve(require_human=True) parks draft AND fires Telegram."""

    def test_require_human_triggers_telegram(self, monkeypatch, tmp_path):
        # Reload approval module with patched paths
        from lib.content import approval

        importlib.reload(approval)
        monkeypatch.setattr(approval, "_PENDING_DIR", tmp_path / "pending")
        monkeypatch.setattr(approval, "_APPROVALS_FILE", tmp_path / "approvals.jsonl")

        from lib.content.report_generator import Report

        # Build a minimal Report; QA must pass for require_human path to run
        fake_qa = type(
            "QA",
            (),
            {
                "passed": True,
                "failures": [],
                "to_dict": lambda self: {"passed": True},
            },
        )()
        monkeypatch.setattr(approval, "run_qa", lambda report: fake_qa)
        monkeypatch.setattr(approval, "_check_sensitivity", lambda body: [])

        calls = []

        def fake_request(**kwargs):
            calls.append(kwargs)
            return {"ok": True}

        # Patch the module-level reference used inside approve()
        import lib.content.telegram_approval as ta_mod

        monkeypatch.setattr(ta_mod, "request_approval", fake_request)

        report = Report(
            kind="weekly_crypto_brief",
            title="Test",
            generated_at="2026-04-20T00:00:00Z",
            facts={},
            body="content body",
        )
        rec = approval.approve(report, require_human=True)
        assert rec.status.value == "pending"
        assert len(calls) == 1
        assert calls[0]["slug"] == "weekly-crypto-brief"

    def test_telegram_failure_does_not_block_parking(self, monkeypatch, tmp_path):
        from lib.content import approval

        importlib.reload(approval)
        monkeypatch.setattr(approval, "_PENDING_DIR", tmp_path / "pending")
        monkeypatch.setattr(approval, "_APPROVALS_FILE", tmp_path / "approvals.jsonl")

        from lib.content.report_generator import Report

        fake_qa = type(
            "QA",
            (),
            {
                "passed": True,
                "failures": [],
                "to_dict": lambda self: {"passed": True},
            },
        )()
        monkeypatch.setattr(approval, "run_qa", lambda report: fake_qa)
        monkeypatch.setattr(approval, "_check_sensitivity", lambda body: [])

        import lib.content.telegram_approval as ta_mod

        def boom(**kwargs):
            raise RuntimeError("no bot token")

        monkeypatch.setattr(ta_mod, "request_approval", boom)

        report = Report(
            kind="ai_intel",
            title="Test",
            generated_at="2026-04-20T00:00:00Z",
            facts={},
            body="body",
        )
        rec = approval.approve(report, require_human=True)
        # Still parked even though Telegram failed
        assert rec.status.value == "pending"
        assert (tmp_path / "pending").exists()
        files = list((tmp_path / "pending").iterdir())
        assert len(files) == 1
