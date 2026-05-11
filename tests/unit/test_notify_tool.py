from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from lib.telegram.draft_queue import read_drafts

REPO_ROOT = Path(__file__).resolve().parents[2]
NOTIFY_PATH = REPO_ROOT / "plugins" / "claw-sapphire" / "tools" / "notify.py"


def _load_notify(monkeypatch, tmp_path):
    for name in [
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID",
        "TELEGRAM_DRY_RUN",
        "SAPPHIRE_NOTIFY_TELEGRAM_LIVE",
        "SAPPHIRE_NOTIFY_DRAFT_QUEUE_ENABLED",
        "SAPPHIRE_NOTIFY_DRAFT_QUEUE_PATH",
    ]:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("SAPPHIRE_NOTIFY_DRAFT_QUEUE_PATH", str(tmp_path / "pm_bot_drafts.jsonl"))
    spec = importlib.util.spec_from_file_location("notify_under_test", NOTIFY_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["notify_under_test"] = module
    spec.loader.exec_module(module)
    return module


def test_notify_defaults_to_pm_bot_draft_queue(monkeypatch, tmp_path):
    notify = _load_notify(monkeypatch, tmp_path)

    result = notify.send_telegram_message("hello from tests", priority="p2")

    assert result["ok"] is True
    assert result["delivery_mode"] == "draft"
    assert result["external_side_effect"] is False
    drafts = read_drafts(result["draft_queue_path"])
    assert len(drafts) == 1
    assert drafts[0].kind == "sapphire_notify"
    assert drafts[0].topic == "ops"
    assert drafts[0].requires_confirmation is True
    assert drafts[0].metadata["priority"] == "p2"
    assert drafts[0].metadata["external_side_effect"] is False
    assert "hello from tests" in drafts[0].body


def test_notify_dry_run_skips_draft_and_network(monkeypatch, tmp_path):
    notify = _load_notify(monkeypatch, tmp_path)
    queue_path = tmp_path / "pm_bot_drafts.jsonl"
    monkeypatch.setenv("TELEGRAM_DRY_RUN", "1")

    result = notify.send_telegram_message("dry run", priority="p1")

    assert result == {
        "ok": True,
        "delivery_mode": "dry_run",
        "method": "sendMessage",
        "text_len": len("📋 *Sapphire OS*\n\ndry run"),
    }
    assert not queue_path.exists()


def test_notify_does_not_call_network_without_live_flag(monkeypatch, tmp_path):
    notify = _load_notify(monkeypatch, tmp_path)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")

    def fail_urlopen(*_args, **_kwargs):
        raise AssertionError("network should not be used in draft mode")

    monkeypatch.setattr(notify.urllib.request, "urlopen", fail_urlopen)

    result = notify.send_telegram_message("queued", priority="p0")

    assert result["ok"] is True
    assert result["delivery_mode"] == "draft"


def test_notify_live_send_requires_explicit_flag(monkeypatch, tmp_path):
    notify = _load_notify(monkeypatch, tmp_path)
    monkeypatch.setenv("SAPPHIRE_NOTIFY_TELEGRAM_LIVE", "1")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def read(self):
            return json.dumps({"ok": True, "result": {"message_id": 1}}).encode()

    def fake_urlopen(req, **_kwargs):
        captured["url"] = req.full_url
        captured["body"] = json.loads(req.data.decode())
        return FakeResponse()

    monkeypatch.setattr(notify.urllib.request, "urlopen", fake_urlopen)

    result = notify.send_telegram_message("live test", priority="p1")

    assert result == {"ok": True, "result": {"message_id": 1}}
    assert captured["url"] == "https://api.telegram.org/botfake-token/sendMessage"
    assert captured["body"]["chat_id"] == "123"
    assert "live test" in captured["body"]["text"]
    assert not (tmp_path / "pm_bot_drafts.jsonl").exists()
