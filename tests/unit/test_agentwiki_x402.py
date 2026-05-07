"""Tests for AgentWiki artifact registry and x402 paid payloads."""

from __future__ import annotations

import json

from lib.payments.agentwiki import (
    artifact_by_id,
    build_agentwiki_artifact_payload,
    load_validated_agentwiki_artifacts,
    quote_agentwiki_artifact,
    search_agentwiki_artifacts,
)
from lib.payments.x402_products import load_product_catalog, load_source_registry


def _catalogs():
    return load_product_catalog(), load_source_registry()


def test_agentwiki_artifacts_validate_against_x402_catalogs() -> None:
    catalog, registry = _catalogs()
    artifacts = load_validated_agentwiki_artifacts(catalog, registry)

    artifact_ids = {artifact.artifact_id for artifact in artifacts}
    product = catalog.get("agentwiki_builder_brief")

    assert "aw_opportunities_federal_fit" in artifact_ids
    assert product.live_settlement_allowed is False
    assert product.amount_atomic() == 250_000
    assert "sam_gov_opportunities" in product.source_ids


def test_agentwiki_search_returns_rights_labeled_cards() -> None:
    catalog, registry = _catalogs()
    artifacts = load_validated_agentwiki_artifacts(catalog, registry)

    payload = search_agentwiki_artifacts(
        artifacts,
        catalog,
        registry,
        query="grants",
        generated_at="2026-05-06T18:30:00Z",
    )

    assert payload["ok"] is True
    assert payload["mode"] == "agentwiki_discovery"
    assert payload["summary"]["live_settlement_allowed"] is False
    assert payload["artifacts"]
    first = payload["artifacts"][0]
    assert first["artifact_id"] == "aw_opportunities_federal_fit"
    assert first["rights"]["payment_is_permission"] is False
    assert first["rights"]["bypass_allowed"] is False
    assert "train" in first["rights"]["prohibited_uses"]
    assert first["price"]["amount_atomic"] == 250_000


def test_agentwiki_quote_and_payload_are_provenance_grounded() -> None:
    catalog, registry = _catalogs()
    artifacts = load_validated_agentwiki_artifacts(catalog, registry)
    artifact = artifact_by_id(artifacts, "aw_developer_api_change_radar")
    product = catalog.get(artifact.product_id)

    quote = quote_agentwiki_artifact(
        artifact,
        product,
        registry,
        generated_at="2026-05-06T18:30:00Z",
    )
    payload = build_agentwiki_artifact_payload(
        artifact,
        product,
        registry,
        generated_at="2026-05-06T18:31:00Z",
    )

    assert quote["payment"]["scheme"] == "exact"
    assert quote["payment"]["live_settlement_allowed"] is False
    assert quote["preflight"]["no_bypass"] is True
    assert payload["mode"] == "agentwiki_paid_artifact"
    assert payload["delivery_id"].startswith("awd-")
    assert payload["safety"]["no_paywall_bypass"] is True
    assert payload["safety"]["no_training_rights_implied"] is True
    assert payload["provenance"]["artifact_registry_hash"]
    assert "developer_docs_public" in payload["provenance"]["source_ids"]
    assert "PAYMENT-SIGNATURE" not in json.dumps(payload)
