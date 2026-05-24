"""Tests for pure agentic Telegram update routing."""

from __future__ import annotations

from lib.telegram.agent_router import extract_context, route_update


def test_extract_context_from_message_update() -> None:
    context = extract_context(
        {
            "update_id": 10,
            "message": {
                "message_id": 55,
                "message_thread_id": 7,
                "direct_messages_topic_id": 9,
                "chat": {"id": -1001},
                "from": {"id": 42, "username": "ari"},
                "text": "/sources",
            },
        }
    )

    assert context.update_type == "message"
    assert context.chat_id == -1001
    assert context.message_id == 55
    assert context.message_thread_id == 7
    assert context.direct_messages_topic_id == 9
    assert context.actor.user_id == 42
    assert context.text == "/sources"


def test_route_message_to_pm_bot_command() -> None:
    decision = route_update({"message": {"chat": {"id": -1001}, "text": "/sources"}})

    assert decision.route == "command"
    assert decision.action == "dispatch_pm_bot_command"
    assert decision.requires_confirmation is False
    assert decision.external_side_effect is False


def test_route_rejects_unallowed_chat() -> None:
    decision = route_update(
        {"message": {"chat": {"id": -1001}, "text": "/sources"}},
        allowed_chat_ids={-1002},
    )

    assert decision.route == "reject"
    assert decision.action == "chat_not_allowed"


def test_route_rejects_unallowed_topic() -> None:
    decision = route_update(
        {
            "message": {
                "chat": {"id": -1001},
                "message_thread_id": 9,
                "text": "/sources",
            }
        },
        allowed_chat_ids={-1001},
        allowed_thread_ids={7},
    )

    assert decision.route == "reject"
    assert decision.action == "topic_not_allowed"


def test_route_rejects_unallowed_direct_message_topic() -> None:
    decision = route_update(
        {
            "message": {
                "chat": {"id": -1001},
                "direct_messages_topic_id": 9,
                "text": "/sources",
            }
        },
        allowed_chat_ids={-1001},
        allowed_thread_ids={7},
    )

    assert decision.route == "reject"
    assert decision.action == "topic_not_allowed"


def test_route_guest_message_to_guarded_reply_draft() -> None:
    decision = route_update(
        {
            "guest_message": {
                "chat": {"id": -1001},
                "guest_query_id": "guest-1",
                "text": "what changed in markets?",
            }
        }
    )

    assert decision.route == "guest_message"
    assert decision.action == "queue_guest_reply_draft"
    assert decision.requires_confirmation is True
    assert decision.external_side_effect is False


def test_route_business_message_to_guarded_reply_draft() -> None:
    decision = route_update(
        {
            "business_message": {
                "business_connection_id": "biz-1",
                "chat": {"id": -1001},
                "text": "draft a client-safe market summary",
            }
        }
    )

    assert decision.route == "business_message"
    assert decision.action == "queue_business_reply_draft"
    assert decision.context.business_connection_id == "biz-1"
    assert decision.requires_confirmation is True
    assert decision.external_side_effect is False


def test_business_message_uses_telegram_business_scope_not_agent_room_scope() -> None:
    decision = route_update(
        {
            "business_message": {
                "business_connection_id": "biz-1",
                "chat": {"id": 987},
                "text": "customer inbox question",
            }
        },
        allowed_chat_ids={-1001},
    )

    assert decision.route == "business_message"
    assert decision.action == "queue_business_reply_draft"


def test_extract_context_from_business_connection_update() -> None:
    context = extract_context(
        {
            "update_id": 701,
            "business_connection": {
                "id": "biz-1",
                "user": {"id": 42, "username": "ari"},
                "user_chat_id": 4200,
                "is_enabled": True,
                "rights": {"can_read_messages": True, "can_reply": True},
            },
        }
    )

    assert context.update_type == "business_connection"
    assert context.business_connection_id == "biz-1"
    assert context.business_user_chat_id == 4200
    assert context.business_is_enabled is True
    assert context.business_can_reply is True
    assert context.actor.user_id == 42


def test_route_draft_callback_requires_confirmation() -> None:
    decision = route_update(
        {
            "callback_query": {
                "id": "cb1",
                "from": {"id": 42, "username": "ari"},
                "data": "draft:approve:tg_draft_abc123",
                "message": {"message_id": 55, "chat": {"id": -1001}},
            }
        }
    )

    assert decision.route == "draft_action"
    assert decision.action == "approve"
    assert decision.draft_id == "tg_draft_abc123"
    assert decision.requires_confirmation is True
    assert decision.external_side_effect is False


def test_route_blocks_high_risk_callback_data() -> None:
    decision = route_update(
        {
            "callback_query": {
                "data": "trade:BTC:long",
                "message": {"message_id": 55, "chat": {"id": -1001}},
            }
        }
    )

    assert decision.route == "blocked"
    assert decision.action == "blocked_external_action"
    assert decision.external_side_effect is False


def test_route_source_callback() -> None:
    decision = route_update(
        {
            "callback_query": {
                "data": "source:details:defillama",
                "message": {"message_id": 55, "chat": {"id": -1001}},
            }
        }
    )

    assert decision.route == "source_action"
    assert decision.action == "details"
    assert decision.source_id == "defillama"


def test_route_reaction_as_feedback() -> None:
    decision = route_update(
        {
            "message_reaction": {
                "chat": {"id": -1001},
                "message_id": 55,
                "user": {"id": 42},
                "new_reaction": [{"type": "emoji", "emoji": "+1"}],
            }
        }
    )

    assert decision.route == "feedback"
    assert decision.action == "record_reaction_signal"
    assert decision.context.reaction_count == 1
    assert decision.requires_confirmation is False


def test_route_poll_as_feedback() -> None:
    decision = route_update({"poll": {"id": "poll-1", "question": "Risk on?"}})

    assert decision.route == "feedback"
    assert decision.action == "record_feedback_signal"
    assert decision.requires_confirmation is False


def test_route_inline_query_to_guarded_answer_draft() -> None:
    decision = route_update(
        {"inline_query": {"id": "inline-1", "from": {"id": 42}, "query": "BTC"}}
    )

    assert decision.route == "inline_query"
    assert decision.action == "queue_inline_answer_draft"
    assert decision.context.text == "BTC"
    assert decision.requires_confirmation is True


def test_route_business_connection_as_audit() -> None:
    decision = route_update({"business_connection": {"id": "biz-1", "user": {"id": 42}}})

    assert decision.route == "audit"
    assert decision.action == "record_business_connection"
    assert decision.requires_confirmation is False


def test_route_managed_bot_event_requires_manual_review() -> None:
    decision = route_update({"managed_bot": {"bot": {"id": 100}}})

    assert decision.route == "blocked"
    assert decision.action == "managed_bot_change_requires_manual_review"
    assert decision.requires_confirmation is True


def test_route_payment_update_blocked() -> None:
    decision = route_update({"pre_checkout_query": {"id": "pcq-1", "from": {"id": 42}}})

    assert decision.route == "blocked"
    assert decision.action == "payment_update_blocked"
    assert decision.external_side_effect is False


def test_route_unsupported_update_is_ignored() -> None:
    decision = route_update({"unknown_update": {"id": "nope"}})

    assert decision.route == "ignore"
    assert decision.action == "unsupported_update"
    assert decision.requires_confirmation is False
