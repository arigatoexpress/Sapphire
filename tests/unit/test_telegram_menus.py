"""Tests for the Telegram inline-menu framework."""

from __future__ import annotations

import pytest

from lib.telegram import menus


def _all_buttons(keyboard: dict) -> list[dict]:
    return [btn for row in keyboard["inline_keyboard"] for btn in row]


def _callback_buttons(keyboard: dict) -> list[dict]:
    return [b for b in _all_buttons(keyboard) if "callback_data" in b]


class TestKeyboardShape:
    def test_home_keyboard_has_all_sections(self):
        kb = menus.build_home_keyboard()
        data = {b["callback_data"] for b in _callback_buttons(kb)}
        for token in (
            menus.MENU_PORTFOLIO,
            menus.MENU_SIGNALS,
            menus.MENU_SECURITY,
            menus.MENU_BRIEF,
            menus.MENU_STATUS,
            menus.MENU_REPORTS,
            menus.MENU_SETTINGS,
        ):
            assert f"m:{token}" in data

    def test_home_keyboard_omits_webapp_button_when_no_url(self):
        kb = menus.build_home_keyboard(None)
        assert not any("web_app" in b for b in _all_buttons(kb))

    def test_home_keyboard_includes_webapp_button_when_url_given(self):
        kb = menus.build_home_keyboard("https://example.com/miniapp")
        webapp = [b for b in _all_buttons(kb) if "web_app" in b]
        assert len(webapp) == 1
        assert webapp[0]["web_app"]["url"] == "https://example.com/miniapp"

    @pytest.mark.parametrize(
        "builder",
        [
            menus.build_portfolio_keyboard,
            menus.build_signals_keyboard,
            menus.build_security_keyboard,
            menus.build_brief_keyboard,
            menus.build_status_keyboard,
            menus.build_reports_keyboard,
        ],
    )
    def test_every_submenu_has_a_home_button(self, builder):
        """A user must never be able to strand themselves in a submenu."""
        kb = builder()
        data = {b["callback_data"] for b in _callback_buttons(kb)}
        assert f"m:{menus.MENU_HOME}" in data

    def test_settings_keyboard_has_home_button(self):
        kb = menus.build_settings_keyboard(heartbeat_enabled=False, heartbeat_hours=4)
        data = {b["callback_data"] for b in _callback_buttons(kb)}
        assert f"m:{menus.MENU_HOME}" in data


class TestCallbackDataLimits:
    @pytest.mark.parametrize(
        "keyboard",
        [
            menus.build_home_keyboard("https://example.com/a-fairly-long-miniapp-url"),
            menus.build_portfolio_keyboard(),
            menus.build_signals_keyboard(),
            menus.build_security_keyboard(),
            menus.build_brief_keyboard(),
            menus.build_status_keyboard(),
            menus.build_reports_keyboard(),
            menus.build_settings_keyboard(heartbeat_enabled=True, heartbeat_hours=12),
        ],
    )
    def test_callback_data_within_telegram_64_byte_cap(self, keyboard):
        for button in _callback_buttons(keyboard):
            encoded = button["callback_data"].encode("utf-8")
            assert len(encoded) <= menus.CALLBACK_MAX_BYTES, button

    def test_oversized_callback_data_is_rejected_at_build_time(self):
        with pytest.raises(ValueError, match="exceeds"):
            menus._btn("x", "y" * 100)

    def test_all_callbacks_use_the_menu_namespace(self):
        kb = menus.build_home_keyboard()
        for button in _callback_buttons(kb):
            assert button["callback_data"].startswith(menus.CALLBACK_PREFIX)


class TestSettingsKeyboardState:
    def test_toggle_label_reflects_enabled_state(self):
        on = menus.build_settings_keyboard(heartbeat_enabled=True, heartbeat_hours=4)
        off = menus.build_settings_keyboard(heartbeat_enabled=False, heartbeat_hours=4)
        on_labels = [b["text"] for b in _callback_buttons(on)]
        off_labels = [b["text"] for b in _callback_buttons(off)]
        assert any("🟢" in label for label in on_labels)
        assert any("⚪" in label for label in off_labels)

    def test_toggle_targets_the_opposite_state(self):
        on = menus.build_settings_keyboard(heartbeat_enabled=True, heartbeat_hours=4)
        data = {b["callback_data"] for b in _callback_buttons(on)}
        assert "m:cfg:hb:off" in data

        off = menus.build_settings_keyboard(heartbeat_enabled=False, heartbeat_hours=4)
        data_off = {b["callback_data"] for b in _callback_buttons(off)}
        assert "m:cfg:hb:on" in data_off

    def test_active_interval_is_checkmarked(self):
        kb = menus.build_settings_keyboard(heartbeat_enabled=True, heartbeat_hours=12)
        labels = {b["callback_data"]: b["text"] for b in _callback_buttons(kb)}
        assert labels["m:cfg:hb:12h"].startswith("✅")
        assert not labels["m:cfg:hb:4h"].startswith("✅")


class TestDispatch:
    def test_rejects_non_menu_callback(self):
        with pytest.raises(ValueError, match="not a menu callback"):
            menus.dispatch_menu_callback("draft:approve:x", menus.MenuContext())

    def test_unknown_token_falls_back_to_home(self):
        """A stale button from an old deploy must not dead-end the UI."""
        render = menus.dispatch_menu_callback("m:totally-unknown", menus.MenuContext())
        data = {b["callback_data"] for b in _callback_buttons(render.reply_markup)}
        assert f"m:{menus.MENU_PORTFOLIO}" in data

    def test_empty_token_renders_home(self):
        render = menus.dispatch_menu_callback("m:", menus.MenuContext())
        assert render.reply_markup == menus.build_home_keyboard()

    def test_provider_output_is_used_verbatim(self):
        ctx = menus.MenuContext(providers={"pf": lambda: "PORTFOLIO_BODY"})
        render = menus.dispatch_menu_callback("m:pf", ctx)
        assert render.text == "PORTFOLIO_BODY"

    def test_missing_provider_yields_placeholder_not_crash(self):
        render = menus.dispatch_menu_callback("m:pf", menus.MenuContext())
        assert "scaffolded" in render.text

    def test_provider_exception_degrades_gracefully(self):
        def boom() -> str:
            raise RuntimeError("upstream down")

        ctx = menus.MenuContext(providers={"pf": boom})
        render = menus.dispatch_menu_callback("m:pf", ctx)
        assert "unavailable" in render.text.lower()
        assert "RuntimeError" in render.text
        # Keyboard still renders so the user can navigate away.
        assert render.reply_markup["inline_keyboard"]

    def test_render_uses_markdownv2_by_default(self):
        render = menus.dispatch_menu_callback("m:h", menus.MenuContext())
        assert render.parse_mode == "MarkdownV2"


class TestSettingsMutation:
    def test_setting_change_invokes_callback_and_lands_on_settings(self):
        calls: list[tuple[str, str]] = []
        ctx = menus.MenuContext(on_setting_change=lambda s, a: calls.append((s, a)))
        render = menus.dispatch_menu_callback("m:cfg:hb:on", ctx)
        assert calls == [("heartbeat", "on")]
        assert render.callback_answer == "Heartbeat enabled"
        # Lands on the settings screen so the toggle visibly flips.
        data = {b["callback_data"] for b in _callback_buttons(render.reply_markup)}
        assert any(d.startswith("m:cfg:hb:") for d in data)

    def test_interval_change_toast(self):
        ctx = menus.MenuContext(on_setting_change=lambda s, a: None)
        assert (
            menus.dispatch_menu_callback("m:cfg:hb:1d", ctx).callback_answer
            == "Interval set to daily"
        )

    def test_setting_change_failure_is_surfaced_not_raised(self):
        def boom(scope: str, action: str) -> None:
            raise OSError("read-only filesystem")

        ctx = menus.MenuContext(on_setting_change=boom)
        render = menus.dispatch_menu_callback("m:cfg:hb:on", ctx)
        assert render.callback_answer == "Could not save setting"

    def test_no_callback_configured_still_renders(self):
        render = menus.dispatch_menu_callback("m:cfg:hb:on", menus.MenuContext())
        assert render.callback_answer == "Heartbeat enabled"


class TestRenderHome:
    def test_render_home_matches_home_dispatch(self):
        ctx = menus.MenuContext()
        assert menus.render_home(ctx).reply_markup == menus.build_home_keyboard()
