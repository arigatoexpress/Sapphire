import asyncio
import importlib.util
from pathlib import Path

import pytest


ROOT_DIR = Path(__file__).resolve().parents[2]
SCOUT_SANDBOX_PATH = ROOT_DIR / "services/scout-sandbox/app.py"


def _load_scout_module():
    pytest.importorskip("aiohttp")
    pytest.importorskip("fastapi")
    pytest.importorskip("pydantic")
    pytest.importorskip("loguru")
    spec = importlib.util.spec_from_file_location("scout_sandbox_app", SCOUT_SANDBOX_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_gtm_dispatch_blocked_when_disabled(monkeypatch):
    module = _load_scout_module()
    monkeypatch.setenv("SCOUT_SANDBOX_GTM_ENABLED", "false")
    config = module.SandboxConfig.from_env()
    broker = module.ScoutSandboxBroker(config)

    result = asyncio.run(
        broker.dispatch(
            module.DispatchRequest(
                action="gtm_outbound",
                outbound_payload={"company_url": "https://example.com"},
                external_url_hint="https://app.clawgtm.com/api/v1/agents/dispatch",
                source="unit-test",
            )
        )
    )
    assert result["dispatched"] is False
    assert result["reason"] == "gtm_dispatch_disabled"


def test_gtm_dispatch_requires_token_by_default(monkeypatch):
    module = _load_scout_module()
    monkeypatch.setenv("SCOUT_SANDBOX_GTM_ENABLED", "true")
    monkeypatch.setenv("SCOUT_SANDBOX_GTM_REQUIRE_TOKEN", "true")
    monkeypatch.delenv("SCOUT_SANDBOX_GTM_API_TOKEN", raising=False)
    config = module.SandboxConfig.from_env()
    broker = module.ScoutSandboxBroker(config)

    result = asyncio.run(
        broker.dispatch(
            module.DispatchRequest(
                action="gtm_outbound",
                outbound_payload={"company_url": "https://example.com"},
                external_url_hint="https://app.clawgtm.com/api/v1/agents/dispatch",
                source="unit-test",
            )
        )
    )
    assert result["dispatched"] is False
    assert result["reason"] == "gtm_api_token_missing"


def test_selector_sanitizer_filters_unsafe_values():
    module = _load_scout_module()
    selectors = ["h1", "h1", "a[href]", "script;drop", "div.card > a"]
    cleaned = module.ScoutSandboxBroker._sanitize_css_selectors(selectors, max_count=8)
    assert "h1" in cleaned
    assert "a[href]" in cleaned
    assert "div.card > a" in cleaned
    assert "script;drop" not in cleaned


def test_scrapling_collect_disabled_returns_guard(monkeypatch):
    module = _load_scout_module()
    monkeypatch.setenv("SCOUT_SANDBOX_SCRAPLING_ENABLED", "false")
    config = module.SandboxConfig.from_env()
    broker = module.ScoutSandboxBroker(config)

    result = asyncio.run(
        broker.collect_scrapling_intel(
            source_url="https://news.ycombinator.com/",
            selectors=["title"],
            limit_per_selector=3,
            include_links=False,
            max_links=5,
            query="",
        )
    )
    assert result["ok"] is False
    assert result["reason"] == "scrapling_disabled"
