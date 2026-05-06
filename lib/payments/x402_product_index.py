"""Product discovery payloads for x402-paid Sapphire APIs."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from lib.payments.x402_products import ProductCatalog, ProductDefinition, SourceRegistry


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _source_status(product: ProductDefinition, registry: SourceRegistry) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source_id in product.source_ids:
        try:
            source = registry.get(source_id)
        except KeyError:
            rows.append(
                {
                    "source_id": source_id,
                    "name": source_id,
                    "production_ready": False,
                    "allowed": False,
                    "terms_status": "missing_registry_entry",
                    "freshness": "unknown",
                    "priority": "unknown",
                }
            )
            continue
        rows.append(
            {
                "source_id": source.source_id,
                "name": source.name,
                "domain": source.domain,
                "priority": source.priority,
                "production_ready": source.production_ready,
                "allowed": source.allows_product(product.product_id),
                "terms_status": source.terms_status,
                "redistribution": source.redistribution,
                "freshness": source.freshness,
            }
        )
    return rows


def _readiness(product: ProductDefinition, sources: list[Mapping[str, Any]]) -> str:
    if product.live_settlement_allowed:
        return "live_settlement_review_required"
    if any(not source.get("allowed") for source in sources):
        return "source_contract_mismatch"
    if any(not source.get("production_ready") for source in sources):
        return "source_review_required"
    return "simulated_ready"


def build_product_index(
    catalog: ProductCatalog,
    registry: SourceRegistry,
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build an agent-discoverable index for x402 paid products."""

    products: list[dict[str, Any]] = []
    for product in catalog.products:
        sources = _source_status(product, registry)
        products.append(
            {
                **product.to_dict(),
                "readiness": _readiness(product, sources),
                "source_count": len(sources),
                "production_ready_source_count": sum(
                    1 for source in sources if source.get("production_ready")
                ),
                "sources": sources,
            }
        )

    live_enabled = [product for product in products if product["live_settlement_allowed"]]
    return {
        "ok": True,
        "schema_version": 1,
        "generated_at": generated_at or _now_iso(),
        "mode": "x402_product_discovery",
        "summary": {
            "product_count": len(products),
            "live_settlement_allowed_count": len(live_enabled),
            "simulated_or_testnet_count": sum(
                1 for product in products if product["settlement_mode"] == "simulated_or_testnet"
            ),
            "source_review_required_count": sum(
                1 for product in products if product["readiness"] == "source_review_required"
            ),
        },
        "safety": {
            "live_settlement_default": False,
            "real_trading_enabled": False,
            "telegram_sends_enabled": False,
            "production_mutation_enabled": False,
        },
        "products": products,
    }


__all__ = ["build_product_index"]
