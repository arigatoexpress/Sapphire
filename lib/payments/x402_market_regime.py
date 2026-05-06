"""Simulated market-regime paid artifact helpers.

The route layer handles auth and x402 verification. This module keeps the
report builder pure: it accepts a cache-first cross-asset snapshot and the x402
catalog objects, then returns a compact paid artifact payload.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from lib.payments.x402_products import ProductDefinition, SourceRegistry

PRODUCT_ID = "market_regime_report"


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def artifact_id_for_report(report: Mapping[str, Any]) -> str:
    """Return a deterministic artifact id for a paid report payload."""
    encoded = json.dumps(report, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return f"x402-mr-{hashlib.sha256(encoded).hexdigest()[:24]}"


def _catalog_sources(product: ProductDefinition, registry: SourceRegistry) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    for source_id in product.source_ids:
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


def build_market_regime_report(
    *,
    product: ProductDefinition,
    registry: SourceRegistry,
    snapshot: Mapping[str, Any],
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build the first x402-paid market-regime artifact.

    The output is intentionally conservative: it exposes current cross-asset
    regime evidence and source/provenance context, but does not claim live
    trading readiness or settled payment status.
    """
    regime = dict(snapshot.get("regime") or {})
    breakdowns = list(snapshot.get("breakdowns") or [])
    lead_lag = list(snapshot.get("lead_lag") or [])
    source_summary = dict(snapshot.get("source_summary") or {})
    assets = list(snapshot.get("assets") or sorted(source_summary))
    ok = bool(snapshot.get("ok", True))
    warnings: list[str] = []
    if not ok:
        warnings.append("source snapshot reported unavailable or degraded")
    if not product.source_ids:
        warnings.append("product has no registered source dependencies")
    if product.live_settlement_allowed:
        warnings.append("unexpected live settlement flag enabled")

    report = {
        "ok": ok,
        "product_id": product.product_id,
        "artifact_kind": product.artifact_kind,
        "settlement_mode": product.settlement_mode,
        "live_settlement_allowed": product.live_settlement_allowed,
        "generated_at": generated_at or str(snapshot.get("generated_at") or _now_iso()),
        "mode": snapshot.get("mode", "cache_or_dry_run"),
        "summary": {
            "label": regime.get("label", "regime_uncertain"),
            "confidence": regime.get("confidence", 0.0),
            "drivers": list(regime.get("drivers") or []),
            "metrics": dict(regime.get("metrics") or {}),
            "asset_count": len(assets),
            "breakdown_count": len(breakdowns),
            "lead_lag_count": len(lead_lag),
        },
        "regime": regime,
        "breakdowns": breakdowns[:12],
        "lead_lag": lead_lag[:12],
        "source_summary": source_summary,
        "catalog_sources": _catalog_sources(product, registry),
        "provenance": snapshot.get("provenance") or {},
        "warnings": warnings,
    }
    report["artifact_id"] = artifact_id_for_report(report)
    return report


__all__ = ["PRODUCT_ID", "artifact_id_for_report", "build_market_regime_report"]
