"""Pure routing primitives for agentic Telegram updates.

The PM bot service owns Telegram ingress. This module only classifies update
payloads into safe internal intents; it never sends Telegram messages, answers
callback queries, mutates draft state, or calls external services.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

SUPPORTED_UPDATE_TYPES: tuple[str, ...] = (
    "message",
    "edited_message",
    "channel_post",
    "edited_channel_post",
    "business_connection",
    "business_message",
    "edited_business_message",
    "deleted_business_messages",
    "guest_message",
    "callback_query",
    "message_reaction",
    "message_reaction_count",
    "inline_query",
    "chosen_inline_result",
    "shipping_query",
    "pre_checkout_query",
    "purchased_paid_media",
    "poll",
    "poll_answer",
    "my_chat_member",
    "chat_member",
    "chat_join_request",
    "chat_boost",
    "removed_chat_boost",
    "managed_bot",
)
MESSAGE_UPDATE_TYPES = frozenset(
    {
        "message",
        "edited_message",
        "channel_post",
        "edited_channel_post",
        "business_message",
        "edited_business_message",
        "guest_message",
    }
)
AUDIT_UPDATE_TYPES = frozenset(
    {
        "business_connection",
        "deleted_business_messages",
        "my_chat_member",
        "chat_member",
        "chat_join_request",
    }
)
BUSINESS_UPDATE_TYPES = frozenset(
    {
        "business_connection",
        "business_message",
        "edited_business_message",
        "deleted_business_messages",
    }
)
FEEDBACK_UPDATE_TYPES = frozenset(
    {
        "message_reaction",
        "message_reaction_count",
        "poll",
        "poll_answer",
        "chosen_inline_result",
        "chat_boost",
        "removed_chat_boost",
    }
)
PAYMENT_UPDATE_TYPES = frozenset({"shipping_query", "pre_checkout_query", "purchased_paid_media"})
BLOCKED_CALLBACK_RE = re.compile(
    r"^(?:trade|buy|sell|transfer|withdraw|deposit|send|send-funds|deploy|exec|shell|sudo):",
    re.IGNORECASE,
)
DRAFT_CALLBACK_RE = re.compile(
    r"^draft:(?P<action>approve|reject|snooze|open):(?P<draft_id>[A-Za-z0-9_.:-]{1,96})$",
    re.IGNORECASE,
)
SOURCE_CALLBACK_RE = re.compile(
    r"^source:(?P<action>mute|boost|details):(?P<source_id>[A-Za-z0-9_.:-]{1,96})$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class TelegramActor:
    """Telegram sender metadata, stripped down to non-secret routing fields."""

    user_id: int | None = None
    username: str = ""
    is_bot: bool = False


@dataclass(frozen=True)
class TelegramContext:
    """Normalized context extracted from a Bot API update."""

    update_id: int | None
    update_type: str
    chat_id: int | None = None
    message_id: int | None = None
    message_thread_id: int | None = None
    direct_messages_topic_id: int | None = None
    actor: TelegramActor = TelegramActor()
    text: str = ""
    callback_data: str = ""
    reaction_count: int = 0
    business_connection_id: str = ""
    business_user_chat_id: int | None = None
    business_is_enabled: bool | None = None
    business_can_reply: bool | None = None


@dataclass(frozen=True)
class RouterDecision:
    """Internal route decision with explicit no-send posture."""

    route: str
    action: str
    reason: str
    context: TelegramContext
    draft_id: str = ""
    source_id: str = ""
    requires_confirmation: bool = True
    external_side_effect: bool = False


def _coerce_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _first_update_payload(update: Mapping[str, Any]) -> tuple[str, Mapping[str, Any]] | None:
    for update_type in SUPPORTED_UPDATE_TYPES:
        payload = update.get(update_type)
        if isinstance(payload, Mapping):
            return update_type, payload
    return None


def _actor_from(payload: Mapping[str, Any]) -> TelegramActor:
    sender = payload.get("from") or payload.get("user")
    if not isinstance(sender, Mapping):
        return TelegramActor()
    return TelegramActor(
        user_id=_coerce_int(sender.get("id")),
        username=str(sender.get("username") or "").strip(),
        is_bot=bool(sender.get("is_bot", False)),
    )


def _chat_id_from(payload: Mapping[str, Any]) -> int | None:
    chat = payload.get("chat")
    if isinstance(chat, Mapping):
        return _coerce_int(chat.get("id"))
    return _coerce_int(payload.get("chat_id"))


def _business_connection_id_from(payload: Mapping[str, Any]) -> str:
    value = payload.get("business_connection_id") or payload.get("id")
    return str(value or "").strip()


def _business_can_reply_from(payload: Mapping[str, Any]) -> bool | None:
    rights = payload.get("rights")
    if not isinstance(rights, Mapping) or "can_reply" not in rights:
        return None
    return bool(rights.get("can_reply"))


def _message_context(
    update_id: int | None,
    update_type: str,
    payload: Mapping[str, Any],
) -> TelegramContext:
    return TelegramContext(
        update_id=update_id,
        update_type=update_type,
        chat_id=_chat_id_from(payload),
        message_id=_coerce_int(payload.get("message_id")),
        message_thread_id=_coerce_int(payload.get("message_thread_id")),
        direct_messages_topic_id=_coerce_int(payload.get("direct_messages_topic_id")),
        actor=_actor_from(payload),
        text=str(payload.get("text") or payload.get("caption") or "").strip(),
        business_connection_id=_business_connection_id_from(payload),
    )


def _callback_context(
    update_id: int | None,
    update_type: str,
    payload: Mapping[str, Any],
) -> TelegramContext:
    message = payload.get("message")
    message_payload = message if isinstance(message, Mapping) else {}
    return TelegramContext(
        update_id=update_id,
        update_type=update_type,
        chat_id=_chat_id_from(message_payload),
        message_id=_coerce_int(message_payload.get("message_id")),
        message_thread_id=_coerce_int(message_payload.get("message_thread_id")),
        direct_messages_topic_id=_coerce_int(message_payload.get("direct_messages_topic_id")),
        actor=_actor_from(payload),
        callback_data=str(payload.get("data") or "").strip(),
    )


def _reaction_context(
    update_id: int | None,
    update_type: str,
    payload: Mapping[str, Any],
) -> TelegramContext:
    reactions = payload.get("new_reaction") or payload.get("reactions") or []
    reaction_count = len(reactions) if isinstance(reactions, list) else 0
    return TelegramContext(
        update_id=update_id,
        update_type=update_type,
        chat_id=_chat_id_from(payload),
        message_id=_coerce_int(payload.get("message_id")),
        actor=_actor_from(payload),
        reaction_count=reaction_count,
    )


def _generic_context(
    update_id: int | None,
    update_type: str,
    payload: Mapping[str, Any],
) -> TelegramContext:
    return TelegramContext(
        update_id=update_id,
        update_type=update_type,
        chat_id=_chat_id_from(payload),
        actor=_actor_from(payload),
        text=str(payload.get("query") or payload.get("text") or "").strip(),
        business_connection_id=_business_connection_id_from(payload),
        business_user_chat_id=_coerce_int(payload.get("user_chat_id")),
        business_is_enabled=(bool(payload.get("is_enabled")) if "is_enabled" in payload else None),
        business_can_reply=_business_can_reply_from(payload),
    )


def extract_context(update: Mapping[str, Any]) -> TelegramContext:
    """Normalize a Telegram Bot API update into routing context."""

    update_id = _coerce_int(update.get("update_id"))
    detected = _first_update_payload(update)
    if detected is None:
        return TelegramContext(update_id=update_id, update_type="unsupported")
    update_type, payload = detected
    if update_type in MESSAGE_UPDATE_TYPES:
        return _message_context(update_id, update_type, payload)
    if update_type == "callback_query":
        return _callback_context(update_id, update_type, payload)
    if update_type in {"message_reaction", "message_reaction_count"}:
        return _reaction_context(update_id, update_type, payload)
    return _generic_context(update_id, update_type, payload)


def _allowed(value: int | None, allowed_values: Iterable[int] | None) -> bool:
    if allowed_values is None:
        return True
    return value in set(allowed_values)


def _topic_scope_id(context: TelegramContext) -> int | None:
    if context.message_thread_id is not None:
        return context.message_thread_id
    return context.direct_messages_topic_id


def route_update(
    update: Mapping[str, Any],
    *,
    allowed_chat_ids: Iterable[int] | None = None,
    allowed_thread_ids: Iterable[int] | None = None,
) -> RouterDecision:
    """Classify an update without side effects."""

    context = extract_context(update)
    if context.update_type == "unsupported":
        return RouterDecision(
            route="ignore",
            action="unsupported_update",
            reason="No supported Telegram update payload found.",
            context=context,
            requires_confirmation=False,
        )
    if context.update_type not in BUSINESS_UPDATE_TYPES and not _allowed(
        context.chat_id,
        allowed_chat_ids,
    ):
        return RouterDecision(
            route="reject",
            action="chat_not_allowed",
            reason="Chat is outside the configured Telegram agent scope.",
            context=context,
        )
    topic_scope_id = _topic_scope_id(context)
    if (
        context.update_type not in BUSINESS_UPDATE_TYPES
        and topic_scope_id is not None
        and not _allowed(
            topic_scope_id,
            allowed_thread_ids,
        )
    ):
        return RouterDecision(
            route="reject",
            action="topic_not_allowed",
            reason="Topic is outside the configured Telegram agent scope.",
            context=context,
        )
    if context.update_type in MESSAGE_UPDATE_TYPES:
        if not context.text:
            return RouterDecision(
                route="ignore",
                action="empty_message",
                reason="Message has no command text.",
                context=context,
                requires_confirmation=False,
            )
        if context.update_type == "guest_message":
            return RouterDecision(
                route="guest_message",
                action="queue_guest_reply_draft",
                reason="Guest messages can only be answered through a guarded reply draft.",
                context=context,
            )
        if context.update_type in {"business_message", "edited_business_message"}:
            return RouterDecision(
                route="business_message",
                action="queue_business_reply_draft",
                reason="Business-account messages require guarded local reply drafts.",
                context=context,
            )
        return RouterDecision(
            route="command",
            action="dispatch_pm_bot_command",
            reason="Message text should continue through the PM bot command dispatcher.",
            context=context,
            requires_confirmation=False,
        )
    if context.update_type in FEEDBACK_UPDATE_TYPES:
        return RouterDecision(
            route="feedback",
            action=(
                "record_reaction_signal"
                if context.update_type in {"message_reaction", "message_reaction_count"}
                else "record_feedback_signal"
            ),
            reason="Update is source-quality or audience feedback only.",
            context=context,
            requires_confirmation=False,
        )
    if context.update_type == "inline_query":
        return RouterDecision(
            route="inline_query",
            action="queue_inline_answer_draft",
            reason="Inline answers are external replies and must start as local drafts.",
            context=context,
        )
    if context.update_type in AUDIT_UPDATE_TYPES:
        return RouterDecision(
            route="audit",
            action=f"record_{context.update_type}",
            reason="Administrative Telegram update should be logged for operator awareness.",
            context=context,
            requires_confirmation=False,
        )
    if context.update_type == "managed_bot":
        return RouterDecision(
            route="blocked",
            action="managed_bot_change_requires_manual_review",
            reason="Managed-bot ownership or token changes require manual review.",
            context=context,
        )
    if context.update_type in PAYMENT_UPDATE_TYPES:
        return RouterDecision(
            route="blocked",
            action="payment_update_blocked",
            reason="Payment and paid-media updates are outside the autonomous Telegram scope.",
            context=context,
        )
    if BLOCKED_CALLBACK_RE.match(context.callback_data):
        return RouterDecision(
            route="blocked",
            action="blocked_external_action",
            reason="Callback data attempts an external or high-risk action.",
            context=context,
        )
    draft = DRAFT_CALLBACK_RE.match(context.callback_data)
    if draft:
        return RouterDecision(
            route="draft_action",
            action=draft.group("action").lower(),
            reason="Draft callback requires explicit queue-state handling.",
            context=context,
            draft_id=draft.group("draft_id"),
        )
    source = SOURCE_CALLBACK_RE.match(context.callback_data)
    if source:
        return RouterDecision(
            route="source_action",
            action=source.group("action").lower(),
            reason="Source callback changes only local source-review state.",
            context=context,
            source_id=source.group("source_id"),
        )
    return RouterDecision(
        route="ignore",
        action="unknown_callback",
        reason="Callback data does not match a known safe agentic Telegram action.",
        context=context,
        requires_confirmation=False,
    )
