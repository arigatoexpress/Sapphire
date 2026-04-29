"""Unit tests for inference-proxy Kimi Cloud fallback routing."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services" / "inference-proxy"))
import app as proxy_app  # type: ignore  # noqa: E402


def _messages(text: str = "Summarize public market news.") -> list[dict[str, str]]:
    return [{"role": "user", "content": text}]


@pytest.fixture
def kimi_test_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Disable real credentials and network-adjacent relay state."""
    monkeypatch.setattr(proxy_app, "MOONSHOT_API_KEY", "")
    monkeypatch.setattr(proxy_app, "OPENROUTER_API_KEY", "")
    monkeypatch.setattr(proxy_app, "_KIMI_RELAY_AVAILABLE", False)
    monkeypatch.setattr(proxy_app, "_kimi_relay_fn", None)
    monkeypatch.setattr(proxy_app, "_is_healthy", lambda name: name == "kimi-cloud")
    monkeypatch.setattr(proxy_app, "_mark_ok", lambda name: None)
    monkeypatch.setattr(proxy_app, "_mark_failed", lambda name: None)
    monkeypatch.setattr(proxy_app, "_record", lambda *args, **kwargs: None)
    monkeypatch.delenv("KIMI_RELAY_CHAT_ID", raising=False)
    monkeypatch.delenv("KIMI_CLAW_BOT_TOKEN", raising=False)


def _fake_response(label: str) -> dict[str, Any]:
    return {
        "id": f"test-{label}",
        "object": "chat.completion",
        "model": label,
        "choices": [{"message": {"role": "assistant", "content": "ok"}}],
    }


def test_kimi_aliases_route_to_cloud_tier() -> None:
    for alias in (
        "kimi",
        "kimi-fast",
        "kimi-large",
        "kimi-cloud",
        "kimi-code",
        "cloud",
        "research",
    ):
        assert proxy_app.MODEL_TIERS[alias] == "kimi-cloud"


def test_kimi_cloud_uses_moonshot_before_openrouter(
    monkeypatch: pytest.MonkeyPatch,
    kimi_test_env: None,
) -> None:
    calls: list[dict[str, Any]] = []

    def fake_call(**kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        return _fake_response(kwargs["label"])

    monkeypatch.setattr(proxy_app, "MOONSHOT_API_KEY", "test-moonshot-key")
    monkeypatch.setattr(proxy_app, "OPENROUTER_API_KEY", "test-openrouter-key")
    monkeypatch.setattr(proxy_app, "_call_openai_compat", fake_call)

    response = proxy_app._call_kimi_cloud(_messages(), max_tokens=64, temperature=0.2)

    assert response == _fake_response("moonshot-api")
    assert [call["label"] for call in calls] == ["moonshot-api"]
    assert calls[0]["base"] == proxy_app.MOONSHOT_BASE
    assert calls[0]["model"] == "moonshot-v1-8k"
    assert calls[0]["api_key"] == "test-moonshot-key"


def test_kimi_cloud_falls_back_to_openrouter_when_moonshot_fails(
    monkeypatch: pytest.MonkeyPatch,
    kimi_test_env: None,
) -> None:
    calls: list[dict[str, Any]] = []

    def fake_call(**kwargs: Any) -> dict[str, Any] | None:
        calls.append(kwargs)
        if kwargs["label"] == "moonshot-api":
            return None
        return _fake_response(kwargs["label"])

    monkeypatch.setattr(proxy_app, "MOONSHOT_API_KEY", "test-moonshot-key")
    monkeypatch.setattr(proxy_app, "OPENROUTER_API_KEY", "test-openrouter-key")
    monkeypatch.setattr(proxy_app, "_call_openai_compat", fake_call)

    response = proxy_app._call_kimi_cloud(_messages())

    assert response == _fake_response("openrouter")
    assert [call["label"] for call in calls] == ["moonshot-api", "openrouter"]
    assert calls[1]["base"] == proxy_app.OPENROUTER_BASE
    assert calls[1]["model"] == "moonshot/moonshot-v1-8k"


def test_kimi_cloud_fails_closed_without_providers(
    monkeypatch: pytest.MonkeyPatch,
    kimi_test_env: None,
) -> None:
    def forbidden_call(**kwargs: Any) -> dict[str, Any]:
        raise AssertionError("external provider should not be called")

    monkeypatch.setattr(proxy_app, "_call_openai_compat", forbidden_call)

    assert proxy_app._call_kimi_cloud(_messages()) is None


def test_kimi_cloud_fails_closed_when_health_is_down(
    monkeypatch: pytest.MonkeyPatch,
    kimi_test_env: None,
) -> None:
    monkeypatch.setattr(proxy_app, "MOONSHOT_API_KEY", "test-moonshot-key")
    monkeypatch.setattr(proxy_app, "_is_healthy", lambda name: False)
    monkeypatch.setattr(
        proxy_app,
        "_call_openai_compat",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("provider should not be called")),
    )

    assert proxy_app._call_kimi_cloud(_messages()) is None


def test_kimi_cloud_telegram_relay_requires_explicit_relay_credentials(
    monkeypatch: pytest.MonkeyPatch,
    kimi_test_env: None,
) -> None:
    relay_calls: list[str] = []

    monkeypatch.setattr(proxy_app, "_KIMI_RELAY_AVAILABLE", True)
    monkeypatch.setattr(proxy_app, "_kimi_relay_fn", relay_calls.append)

    assert proxy_app._call_kimi_cloud(_messages()) is None
    assert relay_calls == []


def test_kimi_cloud_telegram_relay_flattens_messages_in_dry_run(
    monkeypatch: pytest.MonkeyPatch,
    kimi_test_env: None,
) -> None:
    relay_calls: list[str] = []

    def fake_relay(query: str) -> str:
        relay_calls.append(query)
        return "relay ok"

    monkeypatch.setattr(proxy_app, "_KIMI_RELAY_AVAILABLE", True)
    monkeypatch.setattr(proxy_app, "_kimi_relay_fn", fake_relay)
    monkeypatch.setenv("KIMI_RELAY_CHAT_ID", "test-chat")
    monkeypatch.setenv("KIMI_CLAW_BOT_TOKEN", "test-token")

    response = proxy_app._call_kimi_cloud(
        [
            {"role": "system", "content": "Be concise."},
            {"role": "user", "content": "Summarize public release notes."},
        ]
    )

    assert response is not None
    assert response["model"] == "kimi-relay"
    assert response["choices"][0]["message"]["content"] == "relay ok"
    assert relay_calls == ["[system]: Be concise.\nSummarize public release notes."]
