"""Tests for the x402 product catalog, source registry, and receipt ledger."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from lib.payments.x402_middleware import PaymentVerificationResult
from lib.payments.x402_products import (
    CatalogValidationError,
    ReceiptLedger,
    ReceiptRecord,
    load_product_catalog,
    load_source_registry,
    load_validated_catalogs,
    validate_catalog,
)

RECIPIENT = "0x1111111111111111111111111111111111111111"


def _header() -> str:
    payload = {
        "payload": {
            "amount": 250_000,
            "payTo": RECIPIENT,
            "asset": "0x036CbD53842c5426634e7929541eC2318f3dCF7e",
            "network": "base-sepolia",
            "from": "0x2222222222222222222222222222222222222222",
            "txHash": "0xabc",
            "nonce": "paid-1",
        }
    }
    return base64.b64encode(json.dumps(payload).encode()).decode()


def test_default_catalog_and_registry_validate() -> None:
    catalog, registry = load_validated_catalogs()

    product_ids = {product.product_id for product in catalog.products}
    source_ids = {source.source_id for source in registry.sources}

    assert "market_regime_report" in product_ids
    assert "backtest_receipt" in product_ids
    assert "defillama" in source_ids
    assert "fred_alfred" in source_ids
    assert "local_inference_mesh" in source_ids
    assert all(product.live_settlement_allowed is False for product in catalog.products)


def test_product_requirements_include_sku_and_source_context() -> None:
    catalog = load_product_catalog()
    product = catalog.get("market_regime_report")

    req = product.to_payment_requirements(
        resource_url="https://api.sapphire.test/api/x402/market-regime",
        pay_to=RECIPIENT,
    )
    wire = req.to_wire()

    assert wire["network"] == "base-sepolia"
    assert wire["maxAmountRequired"] == "250000"
    assert wire["extra"]["productId"] == "market_regime_report"
    assert wire["extra"]["humanAmount"] == "$0.2500"
    assert wire["extra"]["liveSettlementAllowed"] is False
    assert "defillama" in wire["extra"]["sourceIds"]
    assert "fred_alfred" in wire["extra"]["sourceIds"]


def test_pricing_tables_support_existing_route_keys() -> None:
    catalog = load_product_catalog()

    by_path = catalog.pricing_by_route()
    by_method = catalog.pricing_by_route(include_method=True)

    assert by_path["/v1/chat/completions"] == 0.001
    assert by_path["/v1/embeddings"] == 0.0005
    assert by_method["POST /api/x402/backtest"] == 2.0


def test_source_registry_enforces_allowed_product_refs(tmp_path: Path) -> None:
    products = {
        "version": 1,
        "default_network": "base-sepolia",
        "default_currency": "USDC",
        "products": [
            {
                "product_id": "bad_product",
                "route": "/bad",
                "method": "POST",
                "description": "bad",
                "category": "bad",
                "price_usd": "0.0100",
                "artifact_kind": "bad",
                "entitlement_ttl_seconds": 60,
                "max_compute_seconds": 10,
                "settlement_mode": "simulated_or_testnet",
                "live_settlement_allowed": False,
                "source_ids": ["sec_edgar"],
                "tags": [],
            }
        ],
    }
    product_path = tmp_path / "products.json"
    product_path.write_text(json.dumps(products), encoding="utf-8")

    catalog = load_product_catalog(product_path)
    registry = load_source_registry()

    with pytest.raises(CatalogValidationError, match="not allowed"):
        validate_catalog(catalog, registry)


def test_source_registry_reports_missing_refs(tmp_path: Path) -> None:
    products = {
        "version": 1,
        "default_network": "base-sepolia",
        "default_currency": "USDC",
        "products": [
            {
                "product_id": "research_pack_basic",
                "route": "/bad",
                "method": "POST",
                "description": "bad",
                "category": "bad",
                "price_usd": "0.0100",
                "artifact_kind": "bad",
                "entitlement_ttl_seconds": 60,
                "max_compute_seconds": 10,
                "settlement_mode": "simulated_or_testnet",
                "live_settlement_allowed": False,
                "source_ids": ["does_not_exist"],
                "tags": [],
            }
        ],
    }
    product_path = tmp_path / "products.json"
    product_path.write_text(json.dumps(products), encoding="utf-8")

    catalog = load_product_catalog(product_path)
    registry = load_source_registry()

    with pytest.raises(CatalogValidationError, match="missing sources"):
        validate_catalog(catalog, registry)


def test_receipt_record_hashes_payment_header_without_storing_raw_value() -> None:
    catalog = load_product_catalog()
    product = catalog.get("market_regime_report")
    req = product.to_payment_requirements(
        resource_url="https://api.sapphire.test/api/x402/market-regime",
        pay_to=RECIPIENT,
    )
    header = _header()
    verification = PaymentVerificationResult(
        ok=True,
        payer="0x2222222222222222222222222222222222222222",
        tx_hash="0xabc",
        amount_atomic=250_000,
        nonce="paid-1",
    )

    receipt = ReceiptRecord.from_payment(
        product=product,
        requirements=req,
        payment_header=header,
        verification=verification,
        status="accepted",
        artifact_id="artifact-1",
        recorded_at="2026-05-06T15:00:00Z",
        metadata={"mode": "test"},
    )
    payload = receipt.to_dict()

    assert payload["product_id"] == "market_regime_report"
    assert payload["status"] == "accepted"
    assert payload["payment_payload_hash"]
    assert payload["payment_payload_hash"] != header
    assert header not in json.dumps(payload)
    assert payload["payer"] == "0x2222222222222222222222222222222222222222"
    assert payload["source_ids"] == list(product.source_ids)
    assert payload["metadata"] == {"mode": "test"}


def test_receipt_ledger_appends_jsonl_outside_repo_path(tmp_path: Path) -> None:
    catalog = load_product_catalog()
    product = catalog.get("cyber_exploit_risk")
    req = product.to_payment_requirements(
        resource_url="https://api.sapphire.test/api/x402/cyber/exploit-risk",
        pay_to=RECIPIENT,
    )
    receipt = ReceiptRecord.from_payment(
        product=product,
        requirements=req,
        payment_header=None,
        verification=None,
        status="required",
        recorded_at="2026-05-06T15:00:00Z",
    )
    ledger = ReceiptLedger(tmp_path / "receipts" / "x402.jsonl")

    ledger.append(receipt)
    records = ledger.read_all()

    assert len(records) == 1
    assert records[0].receipt_id == receipt.receipt_id
    assert records[0].payment_payload_hash is None
    assert (tmp_path / "receipts" / "x402.jsonl").exists()
