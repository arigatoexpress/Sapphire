"""Validation tests for the agentic Telegram source registry."""

from __future__ import annotations

import copy

import pytest

from lib.telegram.agentic_sources import (
    RegistryError,
    load_registry,
    sources_by_domain,
    validate_registry,
)


def test_agentic_telegram_source_registry_loads() -> None:
    registry = load_registry()

    assert registry["policy"]["telegram_send_default"] == "dry_run_only"
    assert registry["policy"]["local_inference_default"] == "disabled"
    assert len(registry["sources"]) >= 15


def test_registry_covers_core_agent_domains() -> None:
    grouped = sources_by_domain()

    for domain in (
        "crypto_market",
        "exchange_market",
        "macro",
        "equities_regulatory",
        "global_news",
        "cyber",
        "physical_world",
        "prediction_markets",
        "telegram_native",
        "gcp_public",
    ):
        assert domain in grouped


def test_registry_includes_high_signal_source_spine() -> None:
    source_ids = {source["id"] for source in load_registry()["sources"]}

    assert {
        "telegram_channel_intel",
        "defillama",
        "coingecko",
        "hyperliquid_public",
        "fred_macro",
        "sec_edgar",
        "gdelt_cloud",
        "cisa_kev",
        "nvd_cve",
        "nasa_firms",
        "usgs_earthquakes",
        "bigquery_public_crypto",
    } <= source_ids


def test_registry_refuses_duplicate_source_ids() -> None:
    registry = copy.deepcopy(load_registry())
    registry["sources"].append(copy.deepcopy(registry["sources"][0]))

    with pytest.raises(RegistryError, match="duplicate source id"):
        validate_registry(registry)


def test_registry_refuses_raw_or_paywalled_redistribution_language() -> None:
    registry = copy.deepcopy(load_registry())
    registry["sources"][0]["rights"] = "Republish full_article text from paywall sources."

    with pytest.raises(RegistryError, match="forbidden output-policy token"):
        validate_registry(registry)


def test_registry_requires_dry_run_telegram_default() -> None:
    registry = copy.deepcopy(load_registry())
    registry["policy"]["telegram_send_default"] = "live"

    with pytest.raises(RegistryError, match="telegram_send_default"):
        validate_registry(registry)


def test_registry_requires_local_inference_disabled_by_default() -> None:
    registry = copy.deepcopy(load_registry())
    registry["policy"]["local_inference_default"] = "enabled"

    with pytest.raises(RegistryError, match="local_inference_default"):
        validate_registry(registry)
