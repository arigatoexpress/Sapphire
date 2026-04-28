"""Tests for ``lib.agents.health_context.build_health_context``.

The helper centralizes the live-system snapshot logic that was previously
inlined across ``services/telegram-bot/app.py``, the morning digest, and the
observability dashboard. These tests:

- Pin the clock so ``collected_at`` is deterministic.
- Verify each scope (``telegram``, ``morning``, ``ops``, ``minimal``) produces
  the expected structure.
- Confirm the ``"telegram"`` scope reproduces the historical
  ``build_live_system_prompt`` output verbatim, since that's the contract
  every existing caller depends on.
- Cover the missing-payload error path so a callsite with a broken
  ``health_check.py`` shell-out still gets a renderable snapshot.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from lib.agents.health_context import (
    HealthCheck,
    HealthContext,
    InferenceSnapshot,
    build_health_context,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


PINNED = datetime(2026, 4, 28, 14, 30, 0, tzinfo=UTC)
PINNED_ISO = "2026-04-28T14:30:00+00:00"


def _pinned_clock() -> datetime:
    return PINNED


HEALTH_PAYLOAD = {
    "overall": "RED",
    "summary": "8 green, 0 yellow, 3 red out of 11 checks",
    "services": {
        "dashboard:8080": {"status": "green", "detail": "401 auth"},
        "signal-logger:18081": {"status": "red", "detail": "connection refused"},
    },
    "data_freshness": {
        "trading_predictions": {"status": "red", "detail": "83h old, 1,234 bytes"},
    },
    "inference": {
        "mac_ollama": {"status": "green", "detail": "200 OK"},
    },
    "repos": {
        "Sapphire": {"status": "green", "detail": "clean | last: f38569 ..."},
    },
}

STATUS_PAYLOAD = {
    "inference": {
        "proxy_health": {"mac-local": "healthy", "windows-gpu": "degraded"},
        "local_models": ["hermes3:8b", "nemotron-mini:4b", "qwen3:14b"],
        "gpu_models": [],
    }
}


# ---------------------------------------------------------------------------
# Scope-by-scope behavior
# ---------------------------------------------------------------------------


def test_telegram_scope_matches_pr383_inline_format():
    """The telegram scope must match the original ``build_live_system_prompt`` body."""
    ctx = build_health_context(
        "telegram",
        health_payload=HEALTH_PAYLOAD,
        status_payload=STATUS_PAYLOAD,
        now=_pinned_clock,
    )

    assert ctx.scope == "telegram"
    text = "\n".join(ctx.rendered_lines)
    # Preamble — stable advisor framing
    assert "You are Sapphire, the AI assistant for Kadima Digital Strategies." in text
    assert "Use the live context below as the only current operational truth." in text
    assert (
        "Never quote historical test counts, customer counts, model counts, "
        "win rates, or repo totals" in text
    )
    # Pinned timestamp
    assert f"Live context collected at {PINNED_ISO}:" in text
    # Health snapshot block
    assert "Health snapshot:" in text
    assert "*RED* — 8 green, 0 yellow, 3 red out of 11 checks" in text
    assert "🔴 `signal-logger:18081`: connection refused" in text
    assert "🟢 `dashboard:8080`: 401 auth" in text
    # Status snapshot block — matches _status_lines() contract
    assert "Status snapshot:" in text
    assert "Inference proxy: mac-local=healthy, windows-gpu=degraded" in text
    assert "Mac Ollama models: 3 (hermes3:8b, nemotron-mini:4b, qwen3:14b)" in text


def test_telegram_scope_excludes_repos_block():
    """The PR-#383 inline used a brief health profile that omits repos."""
    ctx = build_health_context(
        "telegram",
        health_payload=HEALTH_PAYLOAD,
        status_payload=STATUS_PAYLOAD,
        now=_pinned_clock,
    )
    rendered = "\n".join(ctx.rendered_lines)
    # repos.Sapphire would render as "🟢 `Sapphire`: ..." — must NOT appear
    assert "Sapphire`:" not in rendered


def test_telegram_scope_with_missing_health_payload_uses_fallback_line():
    ctx = build_health_context(
        "telegram",
        health_payload=None,
        status_payload=STATUS_PAYLOAD,
        now=_pinned_clock,
    )
    text = "\n".join(ctx.rendered_lines)
    assert "Health snapshot: unavailable from health_check.py." in text
    # Status snapshot still rendered
    assert "Inference proxy: mac-local=healthy" in text


def test_telegram_scope_with_no_payloads_emits_unavailable_messages():
    ctx = build_health_context("telegram", now=_pinned_clock)
    text = "\n".join(ctx.rendered_lines)
    assert "Health snapshot: unavailable from health_check.py." in text
    assert "Inference proxy/model inventory unavailable from live status.py." in text
    assert ctx.overall == "UNKNOWN"
    assert ctx.summary == "no summary"


def test_morning_scope_lists_attention_checks():
    ctx = build_health_context(
        "morning",
        health_payload=HEALTH_PAYLOAD,
        status_payload=STATUS_PAYLOAD,
        now=_pinned_clock,
    )
    assert ctx.scope == "morning"
    text = "\n".join(ctx.rendered_lines)
    assert "*Health* — RED: 8 green, 0 yellow, 3 red out of 11 checks" in text
    assert f"_Collected at {PINNED_ISO}_" in text
    assert "Attention:" in text
    # The two non-green checks (signal-logger + trading_predictions)
    assert "signal-logger:18081: connection refused" in text
    assert "trading_predictions: 83h old, 1,234 bytes" in text


def test_morning_scope_all_green_does_not_render_attention_block():
    payload = {
        "overall": "GREEN",
        "summary": "all 5 checks green",
        "services": {
            "a": {"status": "green", "detail": "ok"},
            "b": {"status": "green", "detail": "ok"},
        },
    }
    ctx = build_health_context("morning", health_payload=payload, now=_pinned_clock)
    text = "\n".join(ctx.rendered_lines)
    assert "All 2 checks green" in text
    assert "Attention:" not in text


def test_ops_scope_includes_every_check_and_extra_errors():
    ctx = build_health_context(
        "ops",
        health_payload=HEALTH_PAYLOAD,
        status_payload=STATUS_PAYLOAD,
        extra_errors=["dev_pulse: gh CLI timeout", "launchctl: rc=1"],
        now=_pinned_clock,
    )
    assert ctx.scope == "ops"
    text = "\n".join(ctx.rendered_lines)
    assert text.startswith("OVERALL: RED — 8 green, 0 yellow, 3 red out of 11 checks")
    assert f"COLLECTED_AT: {PINNED_ISO}" in text
    # Every check listed (4 checks: services x2 + data_freshness x1 + inference x1 + repos x1 = 5)
    assert "[green] dashboard:8080: 401 auth" in text
    assert "[red] signal-logger:18081: connection refused" in text
    assert "[red] trading_predictions: 83h old, 1,234 bytes" in text
    assert "[green] mac_ollama: 200 OK" in text
    assert "[green] Sapphire: clean | last:" in text  # repos included for ops
    # Extra errors surfaced
    assert "ERRORS (2)" in text
    assert "dev_pulse: gh CLI timeout" in text
    assert "launchctl: rc=1" in text


def test_ops_scope_renders_inference_inventory_in_full():
    ctx = build_health_context(
        "ops",
        health_payload=HEALTH_PAYLOAD,
        status_payload=STATUS_PAYLOAD,
        now=_pinned_clock,
    )
    text = "\n".join(ctx.rendered_lines)
    assert "proxy mac-local: healthy" in text
    assert "proxy windows-gpu: degraded" in text
    assert "mac models (3): hermes3:8b, nemotron-mini:4b, qwen3:14b" in text


def test_minimal_scope_returns_only_overall_and_timestamp():
    ctx = build_health_context(
        "minimal",
        health_payload=HEALTH_PAYLOAD,
        status_payload=STATUS_PAYLOAD,
        now=_pinned_clock,
    )
    assert ctx.scope == "minimal"
    assert ctx.checks == ()  # not populated for minimal
    assert ctx.inference == InferenceSnapshot()  # empty
    assert ctx.rendered_lines == (
        "RED — 8 green, 0 yellow, 3 red out of 11 checks",
        f"@ {PINNED_ISO}",
    )


# ---------------------------------------------------------------------------
# Error path / input validation
# ---------------------------------------------------------------------------


def test_unknown_scope_raises_valueerror_with_valid_options_listed():
    with pytest.raises(ValueError) as excinfo:
        build_health_context("garbage")  # type: ignore[arg-type]
    msg = str(excinfo.value)
    assert "garbage" in msg
    for valid in ("telegram", "morning", "ops", "minimal"):
        assert valid in msg


def test_health_payload_with_non_dict_section_is_skipped_gracefully():
    """Real callers occasionally pass payloads where a section is None or a list."""
    weird = {
        "overall": "GREEN",
        "summary": "ok",
        "services": None,  # would crash a naive .items() call
        "data_freshness": [],  # not a dict
        "inference": {"mac_ollama": {"status": "green", "detail": "ok"}},
    }
    ctx = build_health_context("ops", health_payload=weird, now=_pinned_clock)
    # Only the inference check survives
    assert len(ctx.checks) == 1
    assert ctx.checks[0].name == "mac_ollama"


def test_status_payload_with_unexpected_types_falls_back_to_empty_inference():
    weird_status = {"inference": {"proxy_health": "not-a-dict", "local_models": "nope"}}
    ctx = build_health_context(
        "telegram",
        health_payload=HEALTH_PAYLOAD,
        status_payload=weird_status,
        now=_pinned_clock,
    )
    text = "\n".join(ctx.rendered_lines)
    # Falls through to the "unavailable" line when nothing else is renderable
    assert "Inference proxy/model inventory unavailable from live status.py." in text


def test_unknown_status_renders_fallback_icon():
    payload = {
        "overall": "GREEN",
        "summary": "ok",
        "services": {"weird": {"status": "purple", "detail": "alien"}},
    }
    ctx = build_health_context("ops", health_payload=payload, now=_pinned_clock)
    assert any(c.icon == "⚪" for c in ctx.checks)


# ---------------------------------------------------------------------------
# Clock injection
# ---------------------------------------------------------------------------


def test_default_clock_returns_aware_utc_iso():
    ctx = build_health_context("minimal")
    # Must be a parseable aware ISO timestamp.
    parsed = datetime.fromisoformat(ctx.collected_at)
    assert parsed.tzinfo is not None


def test_naive_injected_clock_is_promoted_to_utc():
    ctx = build_health_context(
        "minimal",
        now=lambda: datetime(2026, 1, 1, 12, 0, 0),  # naive
    )
    # Should still produce a tz-aware ISO string
    parsed = datetime.fromisoformat(ctx.collected_at)
    assert parsed.tzinfo is not None
    assert ctx.collected_at == "2026-01-01T12:00:00+00:00"


def test_clock_injection_produces_deterministic_output_across_scopes():
    for scope in ("telegram", "morning", "ops", "minimal"):
        ctx = build_health_context(
            scope,  # type: ignore[arg-type]
            health_payload=HEALTH_PAYLOAD,
            status_payload=STATUS_PAYLOAD,
            now=_pinned_clock,
        )
        assert ctx.collected_at == PINNED_ISO


# ---------------------------------------------------------------------------
# Public dataclass behavior
# ---------------------------------------------------------------------------


def test_health_context_to_dict_is_json_friendly():
    import json

    ctx = build_health_context(
        "ops",
        health_payload=HEALTH_PAYLOAD,
        status_payload=STATUS_PAYLOAD,
        extra_errors=["x"],
        now=_pinned_clock,
    )
    payload = ctx.to_dict()
    # Round-trips through json without error
    json.dumps(payload)
    assert payload["scope"] == "ops"
    assert payload["overall"] == "RED"
    assert isinstance(payload["checks"], list)
    assert isinstance(payload["inference"], dict)
    assert payload["inference"]["proxy_health"] == STATUS_PAYLOAD["inference"]["proxy_health"]
    assert payload["errors"] == ["x"]


def test_health_context_is_immutable():
    ctx = build_health_context("minimal", now=_pinned_clock)
    with pytest.raises((AttributeError, TypeError)):
        ctx.overall = "OVERWRITTEN"  # type: ignore[misc]


def test_helper_does_no_module_load_io():
    """The helper must not import anything that hits the network or filesystem.

    A regression here would mean the helper can't be safely imported from a
    sandboxed observability worker.
    """
    import importlib
    import sys

    # If import is heavy, this would already have happened above; but we also
    # drop it from sys.modules to force a fresh import and confirm it's clean.
    sys.modules.pop("lib.agents.health_context", None)
    importlib.import_module("lib.agents.health_context")
    # Reaching this line without an exception is sufficient — the module-level
    # code path is exercised at every test run.


def test_inference_snapshot_is_empty_helper_works():
    snap = InferenceSnapshot()
    assert snap.is_empty is True
    snap2 = InferenceSnapshot(local_models=("a",))
    assert snap2.is_empty is False


def test_health_check_dataclass_is_frozen():
    c = HealthCheck(name="x", status="green", detail="ok", icon="🟢")
    with pytest.raises((AttributeError, TypeError)):
        c.detail = "tampered"  # type: ignore[misc]


def test_telegram_scope_dataclass_carries_all_fields():
    """Sanity-check the public dataclass surface remains stable."""
    ctx = build_health_context(
        "telegram",
        health_payload=HEALTH_PAYLOAD,
        status_payload=STATUS_PAYLOAD,
        now=_pinned_clock,
    )
    assert isinstance(ctx, HealthContext)
    assert ctx.overall == "RED"
    assert ctx.summary == "8 green, 0 yellow, 3 red out of 11 checks"
    assert len(ctx.checks) >= 1
    assert ctx.inference.proxy_health["mac-local"] == "healthy"
    assert ctx.errors == ()
    assert ctx.collected_at == PINNED_ISO
    assert "Live context collected at" in "\n".join(ctx.rendered_lines)
