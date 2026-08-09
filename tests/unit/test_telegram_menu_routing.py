"""Tests for menu + content-approval callback routing and the settings store."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest

from lib.telegram import agent_router, settings_store
from lib.telegram.login_widget import verify_webapp_init_data


def _callback_update(data: str, *, chat_id: int = 1, message_id: int = 2) -> dict:
    return {
        "update_id": 100,
        "callback_query": {
            "id": "cbq-1",
            "data": data,
            "from": {"id": 7, "username": "ari", "is_bot": False},
            "message": {"message_id": message_id, "chat": {"id": chat_id}},
        },
    }


class TestMenuRouting:
    def test_menu_callback_routes_to_menu(self):
        decision = agent_router.route_update(_callback_update("m:pf"))
        assert decision.route == "menu"
        assert decision.action == "render_menu"

    def test_menu_route_requires_no_confirmation(self):
        """Repainting a screen is not a state change."""
        decision = agent_router.route_update(_callback_update("m:h"))
        assert decision.requires_confirmation is False
        assert decision.external_side_effect is False

    @pytest.mark.parametrize("data", ["m:h", "m:pf", "m:pf:r", "m:cfg:hb:on", "m:sg:acc", "m:"])
    def test_all_menu_shapes_route(self, data):
        assert agent_router.route_update(_callback_update(data)).route == "menu"

    def test_dangerous_callback_still_blocked_even_with_menu_regex_present(self):
        """Safety checks must run before the menu regex."""
        for payload in ("trade:BTC", "withdraw:all", "sudo:rm"):
            decision = agent_router.route_update(_callback_update(payload))
            assert decision.route == "blocked", payload

    def test_menu_prefix_cannot_smuggle_blocked_action(self):
        # `m:` payloads are constrained to a safe charset; a nested
        # "trade:" cannot escape the menu namespace into a real action.
        decision = agent_router.route_update(_callback_update("m:trade:BTC"))
        assert decision.route == "menu"
        assert decision.external_side_effect is False

    def test_menu_callback_context_carries_message_coords(self):
        decision = agent_router.route_update(_callback_update("m:pf", chat_id=42, message_id=99))
        assert decision.context.chat_id == 42
        assert decision.context.message_id == 99


class TestContentApprovalRouting:
    @pytest.mark.parametrize("action", ["apv", "rej", "vw"])
    def test_approval_callbacks_route(self, action):
        decision = agent_router.route_update(_callback_update(f"{action}:weekly-brief"))
        assert decision.route == "content_approval"
        assert decision.action == action
        assert decision.draft_id == "weekly-brief"

    def test_unknown_prefix_still_ignored(self):
        decision = agent_router.route_update(_callback_update("bogus:thing"))
        assert decision.route == "ignore"

    def test_draft_callbacks_unchanged(self):
        """Pre-existing draft routing must not regress."""
        decision = agent_router.route_update(_callback_update("draft:approve:abc123"))
        assert decision.route == "draft_action"
        assert decision.draft_id == "abc123"

    def test_source_callbacks_unchanged(self):
        decision = agent_router.route_update(_callback_update("source:mute:src1"))
        assert decision.route == "source_action"


class TestSettingsStore:
    def test_defaults_when_file_missing(self, tmp_path):
        settings = settings_store.load(tmp_path / "nope.json")
        assert settings.heartbeat_enabled is False
        assert settings.heartbeat_hours == 4

    def test_corrupt_file_falls_back_to_defaults(self, tmp_path):
        path = tmp_path / "s.json"
        path.write_text("{not json")
        assert settings_store.load(path).heartbeat_hours == 4

    def test_invalid_interval_falls_back(self, tmp_path):
        path = tmp_path / "s.json"
        path.write_text(json.dumps({"heartbeat_hours": 999}))
        assert settings_store.load(path).heartbeat_hours == 4

    def test_roundtrip(self, tmp_path):
        path = tmp_path / "s.json"
        settings_store.save(
            settings_store.TelegramSettings(heartbeat_enabled=True, heartbeat_hours=12), path
        )
        loaded = settings_store.load(path)
        assert loaded.heartbeat_enabled is True
        assert loaded.heartbeat_hours == 12

    def test_save_sets_restrictive_permissions(self, tmp_path):
        path = tmp_path / "s.json"
        settings_store.save(settings_store.TelegramSettings(), path)
        assert oct(path.stat().st_mode)[-3:] == "600"

    @pytest.mark.parametrize(
        "action,field,expected",
        [
            ("on", "heartbeat_enabled", True),
            ("off", "heartbeat_enabled", False),
            ("4h", "heartbeat_hours", 4),
            ("12h", "heartbeat_hours", 12),
            ("1d", "heartbeat_hours", 24),
        ],
    )
    def test_apply_change(self, tmp_path, action, field, expected):
        path = tmp_path / "s.json"
        result = settings_store.apply_change(action, path)
        assert getattr(result, field) == expected
        assert getattr(settings_store.load(path), field) == expected

    def test_unknown_action_is_noop(self, tmp_path):
        path = tmp_path / "s.json"
        settings_store.save(settings_store.TelegramSettings(heartbeat_enabled=True), path)
        result = settings_store.apply_change("nonsense", path)
        assert result.heartbeat_enabled is True

    def test_interval_change_preserves_enabled_flag(self, tmp_path):
        path = tmp_path / "s.json"
        settings_store.apply_change("on", path)
        settings_store.apply_change("12h", path)
        loaded = settings_store.load(path)
        assert loaded.heartbeat_enabled is True
        assert loaded.heartbeat_hours == 12

    def test_env_override_for_path(self, tmp_path, monkeypatch):
        target = tmp_path / "custom.json"
        monkeypatch.setenv("SAPPHIRE_TELEGRAM_SETTINGS_PATH", str(target))
        settings_store.save(settings_store.TelegramSettings(heartbeat_enabled=True))
        assert target.exists()


class TestMiniAppInitDataVerification:
    """The Mini App HMAC scheme differs from the Login Widget scheme.

    Mini App:     secret = HMAC_SHA256(key="WebAppData", msg=bot_token)
    Login Widget: secret = SHA256(bot_token)

    Inverting those would accept forged sessions, so these tests pin the
    exact derivation.
    """

    TOKEN = "123456:test-token"

    def _signed_init_data(self, *, token: str | None = None, auth_date: int | None = None) -> str:
        token = token or self.TOKEN
        user = json.dumps({"id": 7, "first_name": "Ari", "username": "aribs"})
        fields = {
            "auth_date": str(auth_date if auth_date is not None else int(time.time())),
            "query_id": "AAA",
            "user": user,
        }
        check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
        secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
        fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
        return urlencode(fields)

    def test_valid_init_data_accepted(self):
        user = verify_webapp_init_data(self._signed_init_data(), self.TOKEN)
        assert user is not None
        assert user.id == 7
        assert user.username == "aribs"

    def test_wrong_token_rejected(self):
        assert verify_webapp_init_data(self._signed_init_data(), "999:other") is None

    def test_tampered_hash_rejected(self):
        data = self._signed_init_data().replace("hash=", "hash=00")
        assert verify_webapp_init_data(data, self.TOKEN) is None

    def test_expired_auth_date_rejected(self):
        old = int(time.time()) - 90_000  # >24h
        assert verify_webapp_init_data(self._signed_init_data(auth_date=old), self.TOKEN) is None

    def test_login_widget_secret_scheme_is_not_accepted(self):
        """Guard against the two HMAC schemes being confused."""
        user = json.dumps({"id": 7, "first_name": "Ari"})
        fields = {"auth_date": str(int(time.time())), "user": user}
        check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
        # Deliberately use the *Login Widget* derivation.
        wrong_secret = hashlib.sha256(self.TOKEN.encode()).digest()
        fields["hash"] = hmac.new(wrong_secret, check.encode(), hashlib.sha256).hexdigest()
        assert verify_webapp_init_data(urlencode(fields), self.TOKEN) is None

    def test_empty_init_data_rejected(self):
        assert verify_webapp_init_data("", self.TOKEN) is None

    def test_missing_hash_rejected(self):
        assert verify_webapp_init_data(urlencode({"auth_date": "1"}), self.TOKEN) is None

    def test_missing_token_raises(self, monkeypatch):
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        with pytest.raises(ValueError, match="bot_token"):
            verify_webapp_init_data("a=b", None)

    def test_malformed_user_json_rejected(self):
        fields = {"auth_date": str(int(time.time())), "user": "{broken"}
        check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
        secret = hmac.new(b"WebAppData", self.TOKEN.encode(), hashlib.sha256).digest()
        fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
        assert verify_webapp_init_data(urlencode(fields), self.TOKEN) is None
