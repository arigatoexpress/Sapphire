"""Static AgentWiki artifact registry for x402-paid builder data products.

The first AgentWiki slice is deliberately cache/static only. It does not crawl
or fetch live third-party sites. The route layer can expose free discovery and
x402-gated artifact delivery while every artifact carries a rights envelope and
source provenance.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from lib.payments.x402_products import ProductCatalog, ProductDefinition, SourceRegistry

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_AGENTWIKI_ARTIFACT_PATH = ROOT / "config" / "agentwiki_artifacts.json"


class AgentWikiValidationError(ValueError):
    """Raised when the AgentWiki registry does not match x402 catalogs."""


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256_json(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()


def _as_tuple(value: Iterable[str] | None) -> tuple[str, ...]:
    return tuple(str(v) for v in (value or ()))


def _tokens(value: str) -> set[str]:
    return {token for token in "".join(ch.lower() if ch.isalnum() else " " for ch in value).split()}


@dataclass(frozen=True)
class AgentWikiArtifact:
    """One AgentWiki artifact backed by a catalog product and source registry."""

    artifact_id: str
    product_id: str
    title: str
    category: str
    description: str
    audience: tuple[str, ...] = field(default_factory=tuple)
    source_ids: tuple[str, ...] = field(default_factory=tuple)
    tags: tuple[str, ...] = field(default_factory=tuple)
    freshness: Mapping[str, Any] = field(default_factory=dict)
    rights: Mapping[str, Any] = field(default_factory=dict)
    preview: Mapping[str, Any] = field(default_factory=dict)
    content: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> AgentWikiArtifact:
        return cls(
            artifact_id=str(raw["artifact_id"]),
            product_id=str(raw["product_id"]),
            title=str(raw["title"]),
            category=str(raw["category"]),
            description=str(raw["description"]),
            audience=_as_tuple(raw.get("audience")),
            source_ids=_as_tuple(raw.get("source_ids")),
            tags=_as_tuple(raw.get("tags")),
            freshness=dict(raw.get("freshness") or {}),
            rights=dict(raw.get("rights") or {}),
            preview=dict(raw.get("preview") or {}),
            content=dict(raw.get("content") or {}),
        )

    @property
    def search_text(self) -> str:
        return " ".join(
            (
                self.artifact_id,
                self.product_id,
                self.title,
                self.category,
                self.description,
                " ".join(self.audience),
                " ".join(self.source_ids),
                " ".join(self.tags),
            )
        )

    def to_card(
        self,
        *,
        product: ProductDefinition,
        registry: SourceRegistry,
        include_preview: bool = True,
    ) -> dict[str, Any]:
        sources = catalog_sources(self.source_ids, registry)
        card = {
            "artifact_id": self.artifact_id,
            "product_id": self.product_id,
            "title": self.title,
            "category": self.category,
            "description": self.description,
            "audience": list(self.audience),
            "tags": list(self.tags),
            "source_ids": list(self.source_ids),
            "freshness": dict(self.freshness),
            "rights": rights_envelope(self),
            "price": {
                "currency": product.currency,
                "price_usd": f"{product.price_usd:.4f}",
                "amount_atomic": product.amount_atomic(),
                "settlement_mode": product.settlement_mode,
                "live_settlement_allowed": product.live_settlement_allowed,
            },
            "sources": sources,
            "source_count": len(sources),
            "production_ready_source_count": sum(
                1 for source in sources if source["production_ready"]
            ),
        }
        if include_preview:
            card["preview"] = dict(self.preview)
        return card


def load_agentwiki_artifacts(
    path: Path = DEFAULT_AGENTWIKI_ARTIFACT_PATH,
) -> tuple[AgentWikiArtifact, ...]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return tuple(AgentWikiArtifact.from_mapping(item) for item in raw.get("artifacts", ()))


def artifact_by_id(
    artifacts: Sequence[AgentWikiArtifact],
    artifact_id: str,
) -> AgentWikiArtifact:
    for artifact in artifacts:
        if artifact.artifact_id == artifact_id:
            return artifact
    raise KeyError(artifact_id)


def validate_agentwiki_artifacts(
    artifacts: Sequence[AgentWikiArtifact],
    catalog: ProductCatalog,
    registry: SourceRegistry,
) -> None:
    errors: list[str] = []
    seen: set[str] = set()
    for artifact in artifacts:
        if artifact.artifact_id in seen:
            errors.append(f"duplicate AgentWiki artifact_id: {artifact.artifact_id}")
        seen.add(artifact.artifact_id)
        try:
            catalog.get(artifact.product_id)
        except KeyError:
            errors.append(
                f"{artifact.artifact_id} references missing product: {artifact.product_id}"
            )
        for source_id in artifact.source_ids:
            try:
                source = registry.get(source_id)
            except KeyError:
                errors.append(f"{artifact.artifact_id} references missing source: {source_id}")
                continue
            if not source.allows_product(artifact.product_id):
                errors.append(
                    f"{artifact.artifact_id} source {source_id} does not allow "
                    f"{artifact.product_id}"
                )
    if errors:
        raise AgentWikiValidationError("; ".join(errors))


def load_validated_agentwiki_artifacts(
    catalog: ProductCatalog,
    registry: SourceRegistry,
    *,
    path: Path = DEFAULT_AGENTWIKI_ARTIFACT_PATH,
) -> tuple[AgentWikiArtifact, ...]:
    artifacts = load_agentwiki_artifacts(path)
    validate_agentwiki_artifacts(artifacts, catalog, registry)
    return artifacts


def catalog_sources(source_ids: Sequence[str], registry: SourceRegistry) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    for source_id in source_ids:
        try:
            source = registry.get(source_id)
        except KeyError:
            sources.append(
                {
                    "source_id": source_id,
                    "name": source_id,
                    "domain": "unknown",
                    "priority": "unknown",
                    "production_ready": False,
                    "terms_status": "missing_registry_entry",
                    "redistribution": "unknown",
                    "freshness": "unknown",
                    "url": "",
                }
            )
            continue
        sources.append(
            {
                "source_id": source.source_id,
                "name": source.name,
                "domain": source.domain,
                "priority": source.priority,
                "production_ready": source.production_ready,
                "terms_status": source.terms_status,
                "redistribution": source.redistribution,
                "freshness": source.freshness,
                "url": source.url,
            }
        )
    return sources


def rights_envelope(artifact: AgentWikiArtifact) -> dict[str, Any]:
    rights = dict(artifact.rights)
    rights.setdefault("allowed_uses", [])
    rights.setdefault("prohibited_uses", ["resell_raw_source", "train"])
    rights.setdefault("redistribution", "derived_facts_with_citation")
    rights["payment_is_permission"] = False
    rights["bypass_allowed"] = False
    rights["requires_source_terms_review"] = True
    return rights


def _matches_query(artifact: AgentWikiArtifact, query: str) -> bool:
    wanted = _tokens(query)
    if not wanted:
        return True
    available = _tokens(artifact.search_text)
    return wanted <= available or bool(wanted & available)


def search_agentwiki_artifacts(
    artifacts: Sequence[AgentWikiArtifact],
    catalog: ProductCatalog,
    registry: SourceRegistry,
    *,
    query: str = "",
    max_price_usd: Decimal | str | None = None,
    category: str | None = None,
    limit: int = 10,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Search the static AgentWiki artifact registry."""

    price_limit = Decimal(str(max_price_usd)) if max_price_usd not in (None, "") else None
    bounded_limit = max(1, min(int(limit), 50))
    rows: list[dict[str, Any]] = []
    for artifact in artifacts:
        if category and artifact.category != category:
            continue
        if not _matches_query(artifact, query):
            continue
        product = catalog.get(artifact.product_id)
        if price_limit is not None and product.price_usd > price_limit:
            continue
        rows.append(artifact.to_card(product=product, registry=registry))
        if len(rows) >= bounded_limit:
            break

    return {
        "ok": True,
        "schema_version": 1,
        "mode": "agentwiki_discovery",
        "generated_at": generated_at or _now_iso(),
        "query": query,
        "summary": {
            "artifact_count": len(rows),
            "available_artifact_count": len(artifacts),
            "live_settlement_allowed": False,
            "source_posture": "rights_labeled_static_seed",
        },
        "artifacts": rows,
    }


def quote_agentwiki_artifact(
    artifact: AgentWikiArtifact,
    product: ProductDefinition,
    registry: SourceRegistry,
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build a free quote payload before an x402-gated fetch."""

    issued_at = generated_at or _now_iso()
    quote_core = {
        "artifact_id": artifact.artifact_id,
        "product_id": product.product_id,
        "amount_atomic": product.amount_atomic(),
        "issued_at": issued_at,
    }
    return {
        "ok": True,
        "schema_version": 1,
        "mode": "agentwiki_quote",
        "generated_at": issued_at,
        "quote_id": f"awq-{_sha256_json(quote_core)[:24]}",
        "artifact": artifact.to_card(product=product, registry=registry),
        "payment": {
            "scheme": "exact",
            "currency": product.currency,
            "price_usd": f"{product.price_usd:.4f}",
            "amount_atomic": product.amount_atomic(),
            "network": product.network,
            "asset": product.asset,
            "settlement_mode": product.settlement_mode,
            "live_settlement_allowed": product.live_settlement_allowed,
            "route": product.route,
            "method": product.method,
        },
        "preflight": {
            "no_live_fetch": True,
            "no_bypass": True,
            "cache_first": True,
            "requires_rights_envelope": True,
        },
    }


def build_agentwiki_artifact_payload(
    artifact: AgentWikiArtifact,
    product: ProductDefinition,
    registry: SourceRegistry,
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build a paid AgentWiki artifact delivery payload."""

    issued_at = generated_at or _now_iso()
    content = dict(artifact.content)
    source_rows = catalog_sources(artifact.source_ids, registry)
    provenance = {
        "artifact_registry_hash": _sha256_json(
            {
                "artifact_id": artifact.artifact_id,
                "product_id": artifact.product_id,
                "title": artifact.title,
                "source_ids": list(artifact.source_ids),
                "rights": rights_envelope(artifact),
                "content": content,
            }
        ),
        "source_ids": list(artifact.source_ids),
        "source_hashes": {
            source["source_id"]: hashlib.sha256(
                f"{source['source_id']}|{source.get('url', '')}|{source.get('terms_status', '')}".encode()
            ).hexdigest()
            for source in source_rows
        },
        "generated_by": "sapphire_agentwiki_static_seed",
        "generated_at": issued_at,
    }
    payload = {
        "ok": True,
        "schema_version": 1,
        "mode": "agentwiki_paid_artifact",
        "generated_at": issued_at,
        "product_id": product.product_id,
        "artifact_id": artifact.artifact_id,
        "artifact_kind": product.artifact_kind,
        "settlement_mode": product.settlement_mode,
        "live_settlement_allowed": product.live_settlement_allowed,
        "title": artifact.title,
        "category": artifact.category,
        "description": artifact.description,
        "audience": list(artifact.audience),
        "tags": list(artifact.tags),
        "freshness": dict(artifact.freshness),
        "rights": rights_envelope(artifact),
        "content": content,
        "catalog_sources": source_rows,
        "provenance": provenance,
        "safety": {
            "no_live_fetch": True,
            "no_external_mutation": True,
            "no_paywall_bypass": True,
            "no_training_rights_implied": True,
            "raw_source_resale_allowed": False,
        },
    }
    payload["delivery_id"] = f"awd-{_sha256_json(payload)[:24]}"
    return payload


__all__ = [
    "AgentWikiArtifact",
    "AgentWikiValidationError",
    "DEFAULT_AGENTWIKI_ARTIFACT_PATH",
    "artifact_by_id",
    "build_agentwiki_artifact_payload",
    "catalog_sources",
    "load_agentwiki_artifacts",
    "load_validated_agentwiki_artifacts",
    "quote_agentwiki_artifact",
    "rights_envelope",
    "search_agentwiki_artifacts",
    "validate_agentwiki_artifacts",
]
