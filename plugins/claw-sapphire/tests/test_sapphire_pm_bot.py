"""Tests for the Telegram-first Sapphire PM bot tool."""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
import sapphire_pm_bot as pm_bot


class FakeDocSnapshot:
    def __init__(self, doc_id: str, data: dict):
        self.id = doc_id
        self._data = dict(data)

    def to_dict(self) -> dict:
        return dict(self._data)


class FakeDocumentRef:
    def __init__(self, store: dict[str, dict[str, dict]], collection_name: str, doc_id: str):
        self._store = store
        self._collection_name = collection_name
        self._doc_id = doc_id

    def set(self, data: dict) -> None:
        payload = dict(data)
        payload.setdefault("id", self._doc_id)
        self._store[self._collection_name][self._doc_id] = payload


class FakeCollection:
    def __init__(
        self,
        store: dict[str, dict[str, dict]],
        collection_name: str,
        filters: list[tuple[str, str, str]] | None = None,
    ):
        self._store = store
        self._collection_name = collection_name
        self._filters = filters or []

    def document(self, doc_id: str) -> FakeDocumentRef:
        return FakeDocumentRef(self._store, self._collection_name, doc_id)

    def where(self, field: str, op: str, value: str) -> "FakeCollection":
        return FakeCollection(
            self._store, self._collection_name, self._filters + [(field, op, value)]
        )

    def stream(self):
        for doc_id, payload in self._store[self._collection_name].items():
            include = True
            for field, op, value in self._filters:
                if op == "==" and str(payload.get(field)) != str(value):
                    include = False
                    break
            if include:
                yield FakeDocSnapshot(doc_id, payload)


class FakeFirestoreDB:
    def __init__(self, initial: dict[str, list[dict]] | None = None):
        self.store: dict[str, dict[str, dict]] = defaultdict(dict)
        for collection_name, items in (initial or {}).items():
            for payload in items:
                self.store[collection_name][str(payload["id"])] = dict(payload)

    def collection(self, name: str) -> FakeCollection:
        return FakeCollection(self.store, name)


def _install_fake_firestore(monkeypatch, db: FakeFirestoreDB) -> None:
    monkeypatch.setattr(pm_bot, "firestore", SimpleNamespace(Client=lambda project=None: db))


def _make_update(text: str, user_id: int = 123, username: str = "ari") -> dict:
    return {
        "update_id": 1,
        "message": {
            "message_id": 99,
            "text": text,
            "chat": {"id": 555},
            "from": {"id": user_id, "username": username},
        },
    }


def test_allowlist_denies_all_when_env_unset(monkeypatch):
    monkeypatch.delenv("SAPPHIRE_PM_BOT_ALLOWED_USER_IDS", raising=False)

    response = pm_bot.handle_telegram_command(_make_update("/help"))

    assert response["parse_mode"] is None
    assert "not enabled" in response["text"]


def test_allowlist_permits_listed_user_id(monkeypatch):
    monkeypatch.setenv("SAPPHIRE_PM_BOT_ALLOWED_USER_IDS", "123,456")

    response = pm_bot.handle_telegram_command(_make_update("/claw build it"))

    assert response["parse_mode"] is None
    assert response["text"] == "claw session not yet wired (phase 2)"


def test_help_command_happy_path(monkeypatch):
    monkeypatch.setenv("SAPPHIRE_PM_BOT_ALLOWED_USER_IDS", "123")

    response = pm_bot.handle_telegram_command(_make_update("/help"))

    assert response["parse_mode"] == "MarkdownV2"
    assert "Available commands" in response["text"]
    assert "/pm list \\[\\-\\-project <id\\>\\]" in response["text"]


def test_status_command_happy_path(monkeypatch):
    monkeypatch.setenv("SAPPHIRE_PM_BOT_ALLOWED_USER_IDS", "123")
    monkeypatch.setattr(
        pm_bot.sapphire_status_tool,
        "run",
        lambda: (
            """
        {
          "devices": [
            {"name": "macbook", "online": true},
            {"name": "rari1", "online": false}
          ],
          "inference": {
            "proxy_health": {
              "balanced": {"healthy": true},
              "premium": {"healthy": false}
            }
          }
        }
        """
        ),
    )
    monkeypatch.setattr(pm_bot, "_count_signals_today", lambda: 7)
    monkeypatch.setattr(
        pm_bot.requests,
        "get",
        lambda *args, **kwargs: SimpleNamespace(status_code=200, reason="OK"),
    )

    response = pm_bot.handle_telegram_command(_make_update("/status"))

    assert response["parse_mode"] == "MarkdownV2"
    assert "Mesh devices: 1/2 online" in response["text"]
    assert "balanced\\=up" in response["text"]
    assert "premium\\=down" in response["text"]
    assert "Paper\\-trading signals today: 7" in response["text"]


def test_pm_list_happy_path_and_markdown_escape(monkeypatch):
    monkeypatch.setenv("SAPPHIRE_PM_BOT_ALLOWED_USER_IDS", "123")
    db = FakeFirestoreDB(
        {
            "tasks": [
                {
                    "id": "task-1",
                    "title": "Review_auth *today*",
                    "project_id": "proj-sapphire",
                    "state": "todo",
                    "priority": 0,
                    "updated_at": "2026-04-23T12:00:00+00:00",
                },
                {
                    "id": "task-2",
                    "title": "Ship beta",
                    "project_id": "proj-sapphire",
                    "state": "in_progress",
                    "priority": 3,
                    "updated_at": "2026-04-23T11:00:00+00:00",
                },
            ]
        }
    )
    _install_fake_firestore(monkeypatch, db)

    response = pm_bot.handle_telegram_command(_make_update("/pm list --project proj-sapphire"))

    assert response["parse_mode"] == "MarkdownV2"
    assert "todo:" in response["text"]
    assert "in\\_progress:" in response["text"]
    assert "Review\\_auth \\*today\\*" in response["text"]


def test_pm_new_happy_path(monkeypatch):
    monkeypatch.setenv("SAPPHIRE_PM_BOT_ALLOWED_USER_IDS", "123")
    db = FakeFirestoreDB(
        {
            "projects": [
                {
                    "id": "proj-sapphire",
                    "name": "Sapphire Platform",
                    "github_repo": "arigatoexpress/Sapphire",
                    "status": "active",
                }
            ]
        }
    )
    _install_fake_firestore(monkeypatch, db)

    response = pm_bot.handle_telegram_command(_make_update("/pm new Stand up the Telegram PM bot"))

    assert response["parse_mode"] == "HTML"
    assert "Created PM task" in response["text"]

    tasks = list(db.store["tasks"].values())
    assert len(tasks) == 1
    assert tasks[0]["title"] == "Stand up the Telegram PM bot"
    assert tasks[0]["state"] == "todo"
    assert tasks[0]["priority"] == 0
    assert tasks[0]["priority_label"] == "no_priority"
    assert tasks[0]["creator"] == "ari"
    assert tasks[0]["project_id"] == "proj-sapphire"


def test_rag_happy_path(monkeypatch):
    monkeypatch.setenv("SAPPHIRE_PM_BOT_ALLOWED_USER_IDS", "123")
    monkeypatch.setenv("THO_API_KEY", "secret")
    monkeypatch.delenv("THO_API_KEY_FILE", raising=False)

    captured: dict[str, object] = {}

    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "results": [
                    {
                        "template_name": "TMHA_Disclosure.pdf",
                        "page": 4,
                        "text": "These forms are required in Harris County before closing and include disclosures.",
                    }
                ]
            }

    def _fake_post(url, json=None, headers=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        captured["timeout"] = timeout
        return _Response()

    monkeypatch.setattr(pm_bot.requests, "post", _fake_post)

    response = pm_bot.handle_telegram_command(_make_update("/rag what forms are needed"))

    assert response["parse_mode"] == "MarkdownV2"
    assert "TMHA\\_Disclosure\\.pdf" in response["text"]
    assert "page 4" in response["text"]
    assert captured["json"] == {"query": "what forms are needed", "k": 5}
    assert captured["headers"] == {"Authorization": "Bearer secret"}


def test_rag_uses_api_key_file(monkeypatch, tmp_path):
    monkeypatch.setenv("SAPPHIRE_PM_BOT_ALLOWED_USER_IDS", "123")
    monkeypatch.delenv("THO_API_KEY", raising=False)
    key_file = tmp_path / "tho_api_key"
    key_file.write_text(" file-secret \n")
    monkeypatch.setenv("THO_API_KEY_FILE", str(key_file))

    captured: dict[str, object] = {}

    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"results": []}

    def _fake_post(url, json=None, headers=None, timeout=None):
        captured["headers"] = headers
        return _Response()

    monkeypatch.setattr(pm_bot.requests, "post", _fake_post)

    pm_bot.handle_telegram_command(_make_update("/rag what forms are needed"))

    assert captured["headers"] == {"Authorization": "Bearer file-secret"}


def test_rag_fails_closed_when_api_key_missing(monkeypatch):
    monkeypatch.setenv("SAPPHIRE_PM_BOT_ALLOWED_USER_IDS", "123")
    monkeypatch.delenv("THO_API_KEY", raising=False)
    monkeypatch.delenv("THO_API_KEY_FILE", raising=False)
    monkeypatch.setattr(pm_bot, "THO_API_KEY_PATHS", ())

    response = pm_bot.handle_telegram_command(_make_update("/rag tell me about sales forms"))

    assert response["parse_mode"] is None
    assert response["text"] == "THO API not configured on this host"


def test_claw_stub_happy_path(monkeypatch):
    monkeypatch.setenv("SAPPHIRE_PM_BOT_ALLOWED_USER_IDS", "123")

    response = pm_bot.handle_telegram_command(_make_update("/claw investigate backlog"))

    assert response["text"] == "claw session not yet wired (phase 2)"


def test_svc_status_uses_service_supervisor_dry_run(monkeypatch):
    monkeypatch.setenv("SAPPHIRE_PM_BOT_ALLOWED_USER_IDS", "123")
    captured: dict[str, bool] = {}

    def _fake_supervise_once(*, dry_run=False):
        captured["dry_run"] = dry_run
        return {
            "ok": True,
            "attempted": [
                {
                    "label": "ai.hermes.gateway",
                    "restart_action": "kickstart",
                    "reason": "crashed",
                    "exit_code_before": 1,
                }
            ],
            "recovered": [],
            "failed": [],
            "skipped_cooldown": [],
            "errors": [],
        }

    monkeypatch.setitem(
        sys.modules,
        "service_supervisor",
        SimpleNamespace(supervise_once=_fake_supervise_once),
    )

    response = pm_bot.handle_telegram_command(_make_update("/svc status"))

    assert captured["dry_run"] is True
    assert response["parse_mode"] == "MarkdownV2"
    assert "svc status" in response["text"]
    assert "ai\\.hermes\\.gateway" in response["text"]
