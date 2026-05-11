"""Tests for local Telegram draft queue primitives."""

from __future__ import annotations

import pytest

from lib.telegram.draft_queue import append_draft, build_draft, read_drafts, transition_draft


def test_build_draft_requires_body() -> None:
    with pytest.raises(ValueError, match="body is required"):
        build_draft(kind="digest", topic="markets", body=" ")


def test_build_draft_has_stable_id_for_same_material() -> None:
    first = build_draft(
        kind="digest",
        topic="markets",
        body="BTC funding cooled.",
        source_ids=("defillama", "hyperliquid_public"),
        provenance_refs=("data/example.envelope.json",),
        created_at="2026-05-10T23:00:00+00:00",
        target_chat_id=-1001,
        target_thread_id=7,
    )
    second = build_draft(
        kind="digest",
        topic="markets",
        body="BTC funding cooled.",
        source_ids=("hyperliquid_public", "defillama"),
        provenance_refs=("data/example.envelope.json",),
        created_at="2026-05-10T23:00:00+00:00",
        target_chat_id=-1001,
        target_thread_id=7,
    )

    assert first.draft_id == second.draft_id
    assert first.requires_confirmation is True
    assert first.status == "draft"
    assert first.source_ids == ("defillama", "hyperliquid_public")


def test_build_draft_can_mark_non_confirmation_feedback() -> None:
    draft = build_draft(
        kind="feedback_signal",
        topic="research",
        body="Reaction recorded.",
        requires_confirmation=False,
        created_at="2026-05-10T23:00:00+00:00",
    )

    assert draft.requires_confirmation is False


def test_transition_draft_records_history() -> None:
    draft = build_draft(
        kind="digest",
        topic="markets",
        body="Draft body",
        created_at="2026-05-10T23:00:00+00:00",
    )

    pending = transition_draft(
        draft,
        status="pending_confirmation",
        actor="ari",
        reason="ready for review",
        at="2026-05-10T23:01:00+00:00",
    )

    assert pending.status == "pending_confirmation"
    assert pending.metadata["history"] == [
        {
            "at": "2026-05-10T23:01:00+00:00",
            "actor": "ari",
            "from": "draft",
            "to": "pending_confirmation",
            "reason": "ready for review",
        }
    ]


def test_transition_rejects_unknown_status() -> None:
    draft = build_draft(kind="digest", topic="markets", body="Draft body")

    with pytest.raises(ValueError, match="unsupported Telegram draft status"):
        transition_draft(draft, status="sent", actor="ari")


def test_terminal_draft_cannot_transition_again() -> None:
    draft = build_draft(kind="digest", topic="markets", body="Draft body")
    rejected = transition_draft(draft, status="rejected", actor="ari")

    with pytest.raises(ValueError, match="terminal Telegram draft"):
        transition_draft(rejected, status="pending_confirmation", actor="ari")


def test_append_and_read_drafts_jsonl(tmp_path) -> None:
    path = tmp_path / "telegram_drafts.jsonl"
    draft = build_draft(
        kind="digest",
        topic="markets",
        body="BTC funding cooled.",
        source_ids=("defillama",),
        provenance_refs=("data/example.envelope.json",),
        created_at="2026-05-10T23:00:00+00:00",
        metadata={"urgency": "p1"},
    )

    append_draft(path, draft)
    loaded = read_drafts(path)

    assert len(loaded) == 1
    assert loaded[0] == draft


def test_read_drafts_missing_file_returns_empty_tuple(tmp_path) -> None:
    assert read_drafts(tmp_path / "missing.jsonl") == ()
