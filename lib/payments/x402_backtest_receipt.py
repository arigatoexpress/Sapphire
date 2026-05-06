"""Simulated x402-paid backtest receipt helpers.

The route layer owns auth and x402 verification. This module keeps the paid
artifact builder pure: it accepts already-materialized local backtest summaries
and returns a reproducible, paper-only receipt payload.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from lib.payments.x402_products import ProductDefinition, SourceRegistry

PRODUCT_ID = "backtest_receipt"


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def artifact_id_for_backtest_receipt(receipt: Mapping[str, Any]) -> str:
    """Return a deterministic artifact id for a paid backtest receipt."""

    encoded = json.dumps(receipt, sort_keys=True, separators=(",", ":"), default=str).encode(
        "utf-8"
    )
    return f"x402-bt-{hashlib.sha256(encoded).hexdigest()[:24]}"


def reproducibility_hash(payload: Mapping[str, Any]) -> str:
    """Hash the reproducibility-critical parts of a backtest receipt."""

    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()


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


def _filtered_rows(
    leaderboard_rows: Sequence[Mapping[str, Any]],
    *,
    symbols: Sequence[str],
    limit: int,
) -> list[dict[str, Any]]:
    wanted = {symbol.upper() for symbol in symbols if symbol}
    rows: list[dict[str, Any]] = []
    for row in leaderboard_rows:
        clean = dict(row)
        symbol = str(clean.get("symbol") or "").upper()
        if wanted and symbol not in wanted:
            continue
        rows.append(clean)
        if len(rows) >= limit:
            break
    return rows


def build_backtest_receipt(
    *,
    product: ProductDefinition,
    registry: SourceRegistry,
    summary: Mapping[str, Any],
    leaderboard: Mapping[str, Any],
    metric: str = "sortino",
    symbols: Sequence[str] = (),
    limit: int = 10,
    include_minimal_trades: bool = False,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build a paid, paper-only receipt from local backtest artifacts."""

    summary_payload = dict(summary or {})
    leaderboard_payload = dict(leaderboard or {})
    bounded_limit = max(1, min(int(limit), 25))
    rows = _filtered_rows(
        list(leaderboard_payload.get("rows") or ()),
        symbols=tuple(symbols),
        limit=bounded_limit,
    )
    requested_symbols = tuple(symbol.upper() for symbol in symbols if symbol)
    source_files = sorted(
        {
            str(value)
            for value in (
                summary_payload.get("source_file"),
                leaderboard_payload.get("source_file"),
            )
            if value
        }
    )

    warnings: list[str] = []
    if not summary_payload.get("have_results"):
        warnings.append("no local backtest artifacts found")
    if not rows:
        warnings.append("leaderboard has no rows for the requested filter")
    if product.live_settlement_allowed:
        warnings.append("unexpected live settlement flag enabled")
    if include_minimal_trades:
        warnings.append("minimal-trade rows included by request")

    reproducibility = {
        "summary_source_file": summary_payload.get("source_file"),
        "leaderboard_source_file": leaderboard_payload.get("source_file"),
        "computed_at": summary_payload.get("computed_at") or leaderboard_payload.get("computed_at"),
        "metric": metric,
        "symbols": list(requested_symbols),
        "limit": bounded_limit,
        "include_minimal_trades": include_minimal_trades,
        "rows": rows,
    }
    receipt = {
        "ok": bool(summary_payload.get("have_results")) and bool(rows),
        "product_id": product.product_id,
        "artifact_kind": product.artifact_kind,
        "settlement_mode": product.settlement_mode,
        "live_settlement_allowed": product.live_settlement_allowed,
        "paper_only": True,
        "generated_at": generated_at or _now_iso(),
        "mode": "read_only_backtest_receipt",
        "request": {
            "metric": metric,
            "symbols": list(requested_symbols),
            "limit": bounded_limit,
            "include_minimal_trades": include_minimal_trades,
        },
        "summary": {
            "have_results": bool(summary_payload.get("have_results")),
            "total_backtests": int(summary_payload.get("total_backtests") or 0),
            "computed_at": summary_payload.get("computed_at"),
            "age_hours": summary_payload.get("age_hours"),
            "best_per_symbol_count": len(summary_payload.get("best_per_symbol") or []),
            "leaderboard_rows": len(rows),
            "metric": metric,
        },
        "leaderboard": {
            "metric": leaderboard_payload.get("metric") or metric,
            "total_rows": leaderboard_payload.get("total_rows", 0),
            "filtered_rows": leaderboard_payload.get("filtered_rows"),
            "rows": rows,
        },
        "assumptions": {
            "execution": "paper_only",
            "data_scope": "local_materialized_backtest_artifacts",
            "no_live_orders": True,
            "no_live_market_data_pull": True,
            "no_strategy_execution": True,
        },
        "reproducibility": {
            "hash": reproducibility_hash(reproducibility),
            "source_files": source_files,
            "computed_at": reproducibility["computed_at"],
        },
        "catalog_sources": _catalog_sources(product, registry),
        "warnings": warnings,
    }
    receipt["artifact_id"] = artifact_id_for_backtest_receipt(receipt)
    return receipt


__all__ = [
    "PRODUCT_ID",
    "artifact_id_for_backtest_receipt",
    "build_backtest_receipt",
    "reproducibility_hash",
]
