"""Product catalog, source registry, and receipt ledger for x402 paid APIs.

This module is deliberately non-settling. It gives Sapphire a typed catalog of
agent-buyable products and a receipt shape that stores hashes/provenance, not
raw payment headers. Live facilitator verification remains owned by
``x402_middleware`` and is disabled unless explicitly configured elsewhere.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

from lib.payments.x402_middleware import (
    DEFAULT_USDC_CONTRACTS,
    PaymentRequirements,
    PaymentVerificationResult,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PRODUCT_CATALOG_PATH = ROOT / "config" / "x402_products.json"
DEFAULT_SOURCE_REGISTRY_PATH = ROOT / "config" / "x402_source_registry.json"
DEFAULT_RECEIPT_LEDGER_PATH = Path(
    os.environ.get("X402_RECEIPT_LEDGER", "~/.sapphire/x402_payment_receipts.jsonl")
).expanduser()

USDC_DECIMALS = 6


class CatalogValidationError(ValueError):
    """Raised when the product catalog and source registry disagree."""


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _sha256_json(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _as_tuple(value: Iterable[str] | None) -> tuple[str, ...]:
    return tuple(str(v) for v in (value or ()))


@dataclass(frozen=True)
class ProductDefinition:
    """One x402-buyable product/SKU."""

    product_id: str
    route: str
    method: str
    description: str
    category: str
    price_usd: Decimal
    artifact_kind: str
    entitlement_ttl_seconds: int
    max_compute_seconds: int
    settlement_mode: str
    live_settlement_allowed: bool = False
    network: str = "base-sepolia"
    currency: str = "USDC"
    asset: str | None = None
    source_ids: tuple[str, ...] = field(default_factory=tuple)
    tags: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_mapping(
        cls,
        raw: Mapping[str, Any],
        *,
        default_network: str,
        default_currency: str,
    ) -> ProductDefinition:
        network = str(raw.get("network") or default_network)
        asset = raw.get("asset") or DEFAULT_USDC_CONTRACTS.get(network)
        return cls(
            product_id=str(raw["product_id"]),
            route=str(raw["route"]),
            method=str(raw.get("method", "POST")).upper(),
            description=str(raw["description"]),
            category=str(raw["category"]),
            price_usd=Decimal(str(raw["price_usd"])),
            artifact_kind=str(raw["artifact_kind"]),
            entitlement_ttl_seconds=int(raw["entitlement_ttl_seconds"]),
            max_compute_seconds=int(raw["max_compute_seconds"]),
            settlement_mode=str(raw.get("settlement_mode", "simulated_or_testnet")),
            live_settlement_allowed=bool(raw.get("live_settlement_allowed", False)),
            network=network,
            currency=str(raw.get("currency") or default_currency),
            asset=str(asset) if asset else None,
            source_ids=_as_tuple(raw.get("source_ids")),
            tags=_as_tuple(raw.get("tags")),
        )

    @property
    def route_key(self) -> str:
        return f"{self.method} {self.route}"

    def amount_atomic(self, decimals: int = USDC_DECIMALS) -> int:
        multiplier = Decimal(10) ** decimals
        return int((self.price_usd * multiplier).to_integral_value(rounding=ROUND_HALF_UP))

    def to_payment_requirements(
        self,
        *,
        resource_url: str,
        pay_to: str,
        network: str | None = None,
        asset: str | None = None,
        max_timeout_seconds: int = 60,
    ) -> PaymentRequirements:
        resolved_network = network or self.network
        resolved_asset = asset or self.asset or DEFAULT_USDC_CONTRACTS.get(resolved_network, "")
        return PaymentRequirements(
            scheme="exact",
            network=resolved_network,
            max_amount_required=str(self.amount_atomic()),
            resource=resource_url,
            description=self.description,
            mime_type="application/json",
            pay_to=pay_to,
            max_timeout_seconds=max_timeout_seconds,
            asset=resolved_asset,
            extra={
                "productId": self.product_id,
                "category": self.category,
                "artifactKind": self.artifact_kind,
                "currency": self.currency,
                "humanAmount": f"${self.price_usd:.4f}",
                "entitlementTtlSeconds": self.entitlement_ttl_seconds,
                "maxComputeSeconds": self.max_compute_seconds,
                "settlementMode": self.settlement_mode,
                "liveSettlementAllowed": self.live_settlement_allowed,
                "sourceIds": list(self.source_ids),
            },
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "product_id": self.product_id,
            "route": self.route,
            "method": self.method,
            "route_key": self.route_key,
            "description": self.description,
            "category": self.category,
            "price_usd": f"{self.price_usd:.4f}",
            "amount_atomic": self.amount_atomic(),
            "artifact_kind": self.artifact_kind,
            "entitlement_ttl_seconds": self.entitlement_ttl_seconds,
            "max_compute_seconds": self.max_compute_seconds,
            "settlement_mode": self.settlement_mode,
            "live_settlement_allowed": self.live_settlement_allowed,
            "network": self.network,
            "currency": self.currency,
            "asset": self.asset,
            "source_ids": list(self.source_ids),
            "tags": list(self.tags),
        }


@dataclass(frozen=True)
class SourceDefinition:
    """One data/source dependency that may feed a paid product."""

    source_id: str
    name: str
    domain: str
    priority: str
    url: str
    auth: str
    terms_status: str
    redistribution: str
    freshness: str
    production_ready: bool
    allowed_products: tuple[str, ...] = field(default_factory=tuple)
    tags: tuple[str, ...] = field(default_factory=tuple)
    notes: str = ""

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> SourceDefinition:
        return cls(
            source_id=str(raw["source_id"]),
            name=str(raw["name"]),
            domain=str(raw["domain"]),
            priority=str(raw["priority"]),
            url=str(raw["url"]),
            auth=str(raw["auth"]),
            terms_status=str(raw["terms_status"]),
            redistribution=str(raw["redistribution"]),
            freshness=str(raw["freshness"]),
            production_ready=bool(raw.get("production_ready", False)),
            allowed_products=_as_tuple(raw.get("allowed_products")),
            tags=_as_tuple(raw.get("tags")),
            notes=str(raw.get("notes", "")),
        )

    def allows_product(self, product_id: str) -> bool:
        return product_id in self.allowed_products

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "name": self.name,
            "domain": self.domain,
            "priority": self.priority,
            "url": self.url,
            "auth": self.auth,
            "terms_status": self.terms_status,
            "redistribution": self.redistribution,
            "freshness": self.freshness,
            "production_ready": self.production_ready,
            "allowed_products": list(self.allowed_products),
            "tags": list(self.tags),
            "notes": self.notes,
        }


@dataclass(frozen=True)
class ProductCatalog:
    """Typed in-memory view of ``config/x402_products.json``."""

    products: tuple[ProductDefinition, ...]
    version: int = 1

    def __post_init__(self) -> None:
        ids = [p.product_id for p in self.products]
        if len(ids) != len(set(ids)):
            raise CatalogValidationError("duplicate x402 product_id in catalog")

    def get(self, product_id: str) -> ProductDefinition:
        for product in self.products:
            if product.product_id == product_id:
                return product
        raise KeyError(product_id)

    def pricing_by_route(self, *, include_method: bool = False) -> dict[str, float]:
        return {
            (product.route_key if include_method else product.route): float(product.price_usd)
            for product in self.products
        }

    def to_dict(self) -> dict[str, Any]:
        return {"version": self.version, "products": [p.to_dict() for p in self.products]}


@dataclass(frozen=True)
class SourceRegistry:
    """Typed in-memory view of ``config/x402_source_registry.json``."""

    sources: tuple[SourceDefinition, ...]
    version: int = 1

    def __post_init__(self) -> None:
        ids = [s.source_id for s in self.sources]
        if len(ids) != len(set(ids)):
            raise CatalogValidationError("duplicate x402 source_id in registry")

    def get(self, source_id: str) -> SourceDefinition:
        for source in self.sources:
            if source.source_id == source_id:
                return source
        raise KeyError(source_id)

    def missing_source_ids(self, product: ProductDefinition) -> tuple[str, ...]:
        known = {source.source_id for source in self.sources}
        return tuple(source_id for source_id in product.source_ids if source_id not in known)

    def disallowed_source_refs(self, product: ProductDefinition) -> tuple[str, ...]:
        disallowed: list[str] = []
        for source_id in product.source_ids:
            try:
                source = self.get(source_id)
            except KeyError:
                continue
            if not source.allows_product(product.product_id):
                disallowed.append(source_id)
        return tuple(disallowed)

    def to_dict(self) -> dict[str, Any]:
        return {"version": self.version, "sources": [s.to_dict() for s in self.sources]}


def load_product_catalog(path: Path = DEFAULT_PRODUCT_CATALOG_PATH) -> ProductCatalog:
    raw = json.loads(path.read_text(encoding="utf-8"))
    default_network = str(raw.get("default_network", "base-sepolia"))
    default_currency = str(raw.get("default_currency", "USDC"))
    products = tuple(
        ProductDefinition.from_mapping(
            item,
            default_network=default_network,
            default_currency=default_currency,
        )
        for item in raw.get("products", [])
    )
    return ProductCatalog(products=products, version=int(raw.get("version", 1)))


def load_source_registry(path: Path = DEFAULT_SOURCE_REGISTRY_PATH) -> SourceRegistry:
    raw = json.loads(path.read_text(encoding="utf-8"))
    sources = tuple(SourceDefinition.from_mapping(item) for item in raw.get("sources", []))
    return SourceRegistry(sources=sources, version=int(raw.get("version", 1)))


def validate_catalog(
    catalog: ProductCatalog,
    registry: SourceRegistry,
    *,
    strict_allowed_products: bool = True,
) -> None:
    errors: list[str] = []
    for product in catalog.products:
        missing = registry.missing_source_ids(product)
        if missing:
            errors.append(f"{product.product_id} references missing sources: {', '.join(missing)}")
        if strict_allowed_products:
            disallowed = registry.disallowed_source_refs(product)
            if disallowed:
                errors.append(
                    f"{product.product_id} is not allowed by sources: {', '.join(disallowed)}"
                )
    if errors:
        raise CatalogValidationError("; ".join(errors))


def load_validated_catalogs(
    *,
    product_path: Path = DEFAULT_PRODUCT_CATALOG_PATH,
    source_path: Path = DEFAULT_SOURCE_REGISTRY_PATH,
) -> tuple[ProductCatalog, SourceRegistry]:
    catalog = load_product_catalog(product_path)
    registry = load_source_registry(source_path)
    validate_catalog(catalog, registry)
    return catalog, registry


@dataclass(frozen=True)
class ReceiptRecord:
    """A durable, non-secret receipt for an x402-paid artifact."""

    receipt_id: str
    product_id: str
    resource: str
    status: str
    amount_atomic: int
    network: str
    asset: str
    requirement_hash: str
    payment_payload_hash: str | None
    payer: str | None = None
    tx_hash: str | None = None
    nonce: str | None = None
    artifact_id: str | None = None
    source_ids: tuple[str, ...] = field(default_factory=tuple)
    verification_reason: str = ""
    recorded_at: str = field(default_factory=_now_iso)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payment(
        cls,
        *,
        product: ProductDefinition,
        requirements: PaymentRequirements,
        payment_header: str | None,
        verification: PaymentVerificationResult | None,
        status: str,
        artifact_id: str | None = None,
        recorded_at: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> ReceiptRecord:
        requirement_hash = _sha256_json(requirements.to_wire())
        payment_payload_hash = _sha256_text(payment_header) if payment_header else None
        payload = {
            "product_id": product.product_id,
            "resource": requirements.resource,
            "status": status,
            "requirement_hash": requirement_hash,
            "payment_payload_hash": payment_payload_hash,
            "artifact_id": artifact_id,
            "recorded_at": recorded_at or _now_iso(),
        }
        receipt_id = _sha256_json(payload)
        return cls(
            receipt_id=receipt_id,
            product_id=product.product_id,
            resource=requirements.resource,
            status=status,
            amount_atomic=int(requirements.max_amount_required),
            network=requirements.network,
            asset=requirements.asset,
            requirement_hash=requirement_hash,
            payment_payload_hash=payment_payload_hash,
            payer=verification.payer if verification else None,
            tx_hash=verification.tx_hash if verification else None,
            nonce=verification.nonce if verification else None,
            artifact_id=artifact_id,
            source_ids=product.source_ids,
            verification_reason=verification.reason if verification else "",
            recorded_at=str(payload["recorded_at"]),
            metadata=dict(metadata or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "receipt_id": self.receipt_id,
            "product_id": self.product_id,
            "resource": self.resource,
            "status": self.status,
            "amount_atomic": self.amount_atomic,
            "network": self.network,
            "asset": self.asset,
            "requirement_hash": self.requirement_hash,
            "payment_payload_hash": self.payment_payload_hash,
            "payer": self.payer,
            "tx_hash": self.tx_hash,
            "nonce": self.nonce,
            "artifact_id": self.artifact_id,
            "source_ids": list(self.source_ids),
            "verification_reason": self.verification_reason,
            "recorded_at": self.recorded_at,
            "metadata": dict(self.metadata),
        }


class ReceiptLedger:
    """Append-only JSONL ledger for non-secret x402 receipt records."""

    def __init__(self, path: Path = DEFAULT_RECEIPT_LEDGER_PATH) -> None:
        self.path = path.expanduser()

    def append(self, receipt: ReceiptRecord) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(receipt.to_dict(), sort_keys=True) + "\n")

    def read_all(self) -> tuple[ReceiptRecord, ...]:
        if not self.path.exists():
            return ()
        out: list[ReceiptRecord] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            raw = json.loads(line)
            out.append(
                ReceiptRecord(
                    receipt_id=str(raw["receipt_id"]),
                    product_id=str(raw["product_id"]),
                    resource=str(raw["resource"]),
                    status=str(raw["status"]),
                    amount_atomic=int(raw["amount_atomic"]),
                    network=str(raw["network"]),
                    asset=str(raw["asset"]),
                    requirement_hash=str(raw["requirement_hash"]),
                    payment_payload_hash=raw.get("payment_payload_hash"),
                    payer=raw.get("payer"),
                    tx_hash=raw.get("tx_hash"),
                    nonce=raw.get("nonce"),
                    artifact_id=raw.get("artifact_id"),
                    source_ids=_as_tuple(raw.get("source_ids")),
                    verification_reason=str(raw.get("verification_reason", "")),
                    recorded_at=str(raw["recorded_at"]),
                    metadata=dict(raw.get("metadata", {})),
                )
            )
        return tuple(out)


__all__ = [
    "CatalogValidationError",
    "DEFAULT_PRODUCT_CATALOG_PATH",
    "DEFAULT_RECEIPT_LEDGER_PATH",
    "DEFAULT_SOURCE_REGISTRY_PATH",
    "ProductCatalog",
    "ProductDefinition",
    "ReceiptLedger",
    "ReceiptRecord",
    "SourceDefinition",
    "SourceRegistry",
    "load_product_catalog",
    "load_source_registry",
    "load_validated_catalogs",
    "validate_catalog",
]
