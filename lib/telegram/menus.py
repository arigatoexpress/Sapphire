"""Sapphire Telegram menu framework.

Central inline-keyboard builder + callback dispatcher used by the PM bot.
Every callback payload uses a short namespace prefix (``m:``) so we stay
comfortably under Telegram's 64-byte ``callback_data`` cap even with long
sub-tokens.

Design invariants:

* ``build_*_keyboard()`` helpers return a dict shaped for the Bot API's
  ``reply_markup`` field. They never send anything themselves.
* ``dispatch_menu_callback()`` returns a ``MenuRender`` describing what
  the caller (the pm-bot server) should do: edit the message text with
  new content + keyboard, and answer the callback with a short toast.
  It is pure — no HTTP, no filesystem writes.
* Menu leaves ("show me my portfolio") pull data through ``providers``
  callables the caller injects. That keeps this module easy to test
  without importing every downstream data source.

Callback namespace (all start with ``m:``):

    m:h              → home
    m:pf | m:pf:r    → portfolio / refresh
    m:sg | m:sg:a    → signals home / active
    m:sg:r           → signals recent (24h)
    m:sec            → security overview
    m:sec:cve        → recent CVEs
    m:br | m:br:t    → brief home / today
    m:br:w           → brief weekly
    m:st             → status snapshot
    m:rp             → reports list
    m:cfg            → settings
    m:cfg:hb:on      → heartbeat on
    m:cfg:hb:off     → heartbeat off
    m:cfg:hb:4h      → heartbeat interval 4h
    m:cfg:hb:1d      → heartbeat interval 24h
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CALLBACK_PREFIX = "m:"
CALLBACK_MAX_BYTES = 64  # Telegram Bot API hard cap
DEFAULT_PARSE_MODE = "MarkdownV2"

# Menu button tokens (short so callback_data stays tiny).
MENU_HOME = "h"
MENU_PORTFOLIO = "pf"
MENU_SIGNALS = "sg"
MENU_SECURITY = "sec"
MENU_BRIEF = "br"
MENU_STATUS = "st"
MENU_REPORTS = "rp"
MENU_SETTINGS = "cfg"

_MENU_LABELS = {
    MENU_HOME: "🏠 Home",
    MENU_PORTFOLIO: "📊 Portfolio",
    MENU_SIGNALS: "📈 Signals",
    MENU_SECURITY: "🔒 Security",
    MENU_BRIEF: "📰 Brief",
    MENU_STATUS: "🔄 Status",
    MENU_REPORTS: "📋 Reports",
    MENU_SETTINGS: "⚙️ Settings",
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MenuRender:
    """A pure description of the menu state the caller should paint.

    ``text`` is MarkdownV2 by default. Downstream code re-uses the pm-bot's
    ``safety.redact_secrets`` before actually shipping it.
    """

    text: str
    reply_markup: dict[str, Any]
    parse_mode: str | None = DEFAULT_PARSE_MODE
    callback_answer: str = ""
    # When true, the caller should push a NEW message (a large report), not
    # edit the current one. Menu leaves stay editable; a "view full report"
    # tap sends a fresh message so scrollback holds both.
    push_new_message: bool = False


ProviderMap = dict[str, Callable[[], str]]
"""Mapping of leaf token → callable returning already-formatted MarkdownV2.

Every provider function returns pre-escaped MarkdownV2 text. This module
never escapes user-supplied content itself; the formatters do. Providers
that are absent from the map yield a friendly placeholder so partial
integration never crashes the UI.
"""


# ---------------------------------------------------------------------------
# Keyboard builders
# ---------------------------------------------------------------------------


def _btn(label: str, data: str) -> dict[str, str]:
    """Build a single inline-keyboard button and validate the callback size."""
    payload = f"{CALLBACK_PREFIX}{data}" if not data.startswith(CALLBACK_PREFIX) else data
    if len(payload.encode("utf-8")) > CALLBACK_MAX_BYTES:
        raise ValueError(f"callback_data exceeds {CALLBACK_MAX_BYTES} bytes: {payload!r}")
    return {"text": label, "callback_data": payload}


def _url_btn(label: str, url: str) -> dict[str, str]:
    return {"text": label, "url": url}


def _webapp_btn(label: str, url: str) -> dict[str, Any]:
    return {"text": label, "web_app": {"url": url}}


def _row(*buttons: dict[str, Any]) -> list[dict[str, Any]]:
    return list(buttons)


def build_home_keyboard(webapp_url: str | None = None) -> dict[str, Any]:
    """Root menu — 4 rows of 2 buttons + optional web-app footer."""
    rows: list[list[dict[str, Any]]] = [
        _row(
            _btn(_MENU_LABELS[MENU_PORTFOLIO], MENU_PORTFOLIO),
            _btn(_MENU_LABELS[MENU_SIGNALS], MENU_SIGNALS),
        ),
        _row(
            _btn(_MENU_LABELS[MENU_SECURITY], MENU_SECURITY),
            _btn(_MENU_LABELS[MENU_BRIEF], MENU_BRIEF),
        ),
        _row(
            _btn(_MENU_LABELS[MENU_STATUS], MENU_STATUS),
            _btn(_MENU_LABELS[MENU_REPORTS], MENU_REPORTS),
        ),
        _row(_btn(_MENU_LABELS[MENU_SETTINGS], MENU_SETTINGS)),
    ]
    if webapp_url:
        rows.append(_row(_webapp_btn("🌐 Open Dashboard", webapp_url)))
    return {"inline_keyboard": rows}


def _nav_row(*, include_refresh: str | None = None) -> list[dict[str, Any]]:
    """Standard footer row: Refresh (optional) + Home."""
    row: list[dict[str, Any]] = []
    if include_refresh:
        row.append(_btn("🔄 Refresh", include_refresh))
    row.append(_btn(_MENU_LABELS[MENU_HOME], MENU_HOME))
    return row


def build_portfolio_keyboard() -> dict[str, Any]:
    return {
        "inline_keyboard": [
            _row(_btn("📊 Overview", MENU_PORTFOLIO), _btn("💰 By Venue", f"{MENU_PORTFOLIO}:v")),
            _row(_btn("📈 Movers", f"{MENU_PORTFOLIO}:m")),
            _nav_row(include_refresh=f"{MENU_PORTFOLIO}:r"),
        ]
    }


def build_signals_keyboard() -> dict[str, Any]:
    return {
        "inline_keyboard": [
            _row(_btn("🟢 Active", f"{MENU_SIGNALS}:a"), _btn("🕒 Last 24h", f"{MENU_SIGNALS}:r")),
            _row(_btn("🎯 Accuracy", f"{MENU_SIGNALS}:acc")),
            _nav_row(include_refresh=MENU_SIGNALS),
        ]
    }


def build_security_keyboard() -> dict[str, Any]:
    return {
        "inline_keyboard": [
            _row(
                _btn("🔒 Overview", MENU_SECURITY), _btn("🐛 Recent CVEs", f"{MENU_SECURITY}:cve")
            ),
            _row(_btn("🛡️ Kill Switch", f"{MENU_SECURITY}:ks")),
            _nav_row(include_refresh=MENU_SECURITY),
        ]
    }


def build_brief_keyboard() -> dict[str, Any]:
    return {
        "inline_keyboard": [
            _row(_btn("☀️ Today", f"{MENU_BRIEF}:t"), _btn("📅 Weekly", f"{MENU_BRIEF}:w")),
            _row(_btn("🤖 AI Intel", f"{MENU_BRIEF}:ai")),
            _nav_row(include_refresh=MENU_BRIEF),
        ]
    }


def build_status_keyboard() -> dict[str, Any]:
    return {
        "inline_keyboard": [
            _row(_btn("🩺 Deep Health", f"{MENU_STATUS}:d")),
            _nav_row(include_refresh=MENU_STATUS),
        ]
    }


def build_reports_keyboard() -> dict[str, Any]:
    return {
        "inline_keyboard": [
            _row(_btn("📋 Latest 5", f"{MENU_REPORTS}:l")),
            _row(_btn("📁 Ready Queue", f"{MENU_REPORTS}:q")),
            _nav_row(include_refresh=MENU_REPORTS),
        ]
    }


def build_settings_keyboard(*, heartbeat_enabled: bool, heartbeat_hours: int) -> dict[str, Any]:
    """Settings menu — the toggles reflect current config."""
    hb_label = "🟢 Heartbeat ON" if heartbeat_enabled else "⚪ Heartbeat OFF"
    hb_target = "off" if heartbeat_enabled else "on"
    return {
        "inline_keyboard": [
            _row(_btn(hb_label, f"{MENU_SETTINGS}:hb:{hb_target}")),
            _row(
                _btn(
                    ("✅ " if heartbeat_hours == 4 else "") + "Every 4h",
                    f"{MENU_SETTINGS}:hb:4h",
                ),
                _btn(
                    ("✅ " if heartbeat_hours == 12 else "") + "Every 12h",
                    f"{MENU_SETTINGS}:hb:12h",
                ),
                _btn(
                    ("✅ " if heartbeat_hours == 24 else "") + "Daily",
                    f"{MENU_SETTINGS}:hb:1d",
                ),
            ),
            _nav_row(),
        ]
    }


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


def _placeholder(section: str) -> str:
    """Escaped MarkdownV2 placeholder used when a provider isn't wired."""
    return f"*{section}*\n\n_This surface is scaffolded but no data provider is wired\\._"


@dataclass(frozen=True)
class MenuContext:
    """Runtime knobs the dispatcher needs to build responses."""

    webapp_url: str | None = None
    heartbeat_enabled: bool = False
    heartbeat_hours: int = 4
    providers: ProviderMap = field(default_factory=dict)
    on_setting_change: Callable[[str, str], None] | None = None


def _keyboard_for(token: str, ctx: MenuContext) -> dict[str, Any]:
    """Pick the right keyboard for a given leaf token (root or sub)."""
    head = token.split(":", 1)[0]
    if head == MENU_HOME:
        return build_home_keyboard(ctx.webapp_url)
    if head == MENU_PORTFOLIO:
        return build_portfolio_keyboard()
    if head == MENU_SIGNALS:
        return build_signals_keyboard()
    if head == MENU_SECURITY:
        return build_security_keyboard()
    if head == MENU_BRIEF:
        return build_brief_keyboard()
    if head == MENU_STATUS:
        return build_status_keyboard()
    if head == MENU_REPORTS:
        return build_reports_keyboard()
    if head == MENU_SETTINGS:
        return build_settings_keyboard(
            heartbeat_enabled=ctx.heartbeat_enabled,
            heartbeat_hours=ctx.heartbeat_hours,
        )
    return build_home_keyboard(ctx.webapp_url)


def _text_for(token: str, ctx: MenuContext) -> tuple[str, str]:
    """Return ``(body_text, callback_toast)`` for a leaf token.

    Providers are keyed by leaf token verbatim (e.g. ``pf:r``, ``sg:a``).
    A missing provider returns the safe placeholder without raising.
    """
    provider = ctx.providers.get(token)
    if provider is not None:
        try:
            return provider(), "Refreshed"
        except Exception as exc:  # pragma: no cover - provider bug fallback
            return (
                f"*Data source unavailable*\n\n`{type(exc).__name__}`",
                "Data source unavailable",
            )
    head = token.split(":", 1)[0]
    section = _MENU_LABELS.get(head, "Sapphire OS")
    return _placeholder(section), ""


def _handle_settings_change(token: str, ctx: MenuContext) -> str:
    """Interpret ``cfg:hb:*`` mutations and return a toast."""
    if not token.startswith("cfg:hb:"):
        return ""
    action = token[len("cfg:hb:") :]
    if ctx.on_setting_change is not None:
        try:
            ctx.on_setting_change("heartbeat", action)
        except Exception:
            return "Could not save setting"
    toasts = {
        "on": "Heartbeat enabled",
        "off": "Heartbeat disabled",
        "4h": "Interval set to 4 hours",
        "12h": "Interval set to 12 hours",
        "1d": "Interval set to daily",
    }
    return toasts.get(action, "Updated")


def dispatch_menu_callback(callback_data: str, ctx: MenuContext) -> MenuRender:
    """Return the ``MenuRender`` for a ``m:`` callback payload.

    Unknown tokens fall back to the home screen. This is intentional — the
    UI must never dead-end because a user tapped an old button after a
    redeploy.
    """
    if not callback_data.startswith(CALLBACK_PREFIX):
        # Not ours. Caller should route elsewhere.
        raise ValueError(f"not a menu callback: {callback_data!r}")

    token = callback_data[len(CALLBACK_PREFIX) :] or MENU_HOME

    # Settings mutations first — they may change subsequent state.
    setting_toast = ""
    if token.startswith("cfg:hb:"):
        setting_toast = _handle_settings_change(token, ctx)
        # After a mutation, land on the settings screen so the user sees
        # the toggle flip visually.
        token = MENU_SETTINGS

    body, toast = _text_for(token, ctx)
    keyboard = _keyboard_for(token, ctx)
    return MenuRender(
        text=body,
        reply_markup=keyboard,
        parse_mode=DEFAULT_PARSE_MODE,
        callback_answer=setting_toast or toast,
    )


def render_home(ctx: MenuContext) -> MenuRender:
    """Convenience wrapper used by the ``/start`` and ``/menu`` handlers."""
    return dispatch_menu_callback(f"{CALLBACK_PREFIX}{MENU_HOME}", ctx)


__all__ = [
    "CALLBACK_MAX_BYTES",
    "CALLBACK_PREFIX",
    "DEFAULT_PARSE_MODE",
    "MENU_BRIEF",
    "MENU_HOME",
    "MENU_PORTFOLIO",
    "MENU_REPORTS",
    "MENU_SECURITY",
    "MENU_SETTINGS",
    "MENU_SIGNALS",
    "MENU_STATUS",
    "MenuContext",
    "MenuRender",
    "ProviderMap",
    "build_brief_keyboard",
    "build_home_keyboard",
    "build_portfolio_keyboard",
    "build_reports_keyboard",
    "build_security_keyboard",
    "build_settings_keyboard",
    "build_signals_keyboard",
    "build_status_keyboard",
    "dispatch_menu_callback",
    "render_home",
]
