"""Config-driven cypherpunk/Austrian investment thesis matrix.

This module is intentionally read-only. It turns a checked-in thesis config into
ranked research evidence, invalidation watches, and ops tasks. It does not fetch
live market data, sign orders, submit orders, or send notifications.
"""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = ROOT / "config" / "investment_thesis.yaml"


@dataclass(frozen=True)
class ThesisLens:
    id: str
    label: str
    weight: float
    austrian_principle: str
    positive_tags: tuple[str, ...]
    negative_tags: tuple[str, ...]
    source_requirements: tuple[str, ...]


@dataclass(frozen=True)
class ThesisAsset:
    symbol: str
    name: str
    asset_class: str
    conviction: float
    thesis_tags: tuple[str, ...]
    lens_scores: dict[str, float]
    venue_symbols: dict[str, str]
    evidence_sources: tuple[str, ...]
    invalidation_triggers: tuple[dict[str, Any], ...]


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_str_tuple(value: Any) -> tuple[str, ...]:
    return tuple(str(item) for item in _as_list(value) if str(item or "").strip())


def _json_compatible_yaml(text: str) -> dict[str, Any]:
    """Parse the repo's JSON-compatible YAML fallback without PyYAML.

    JSON is valid YAML for the subset we need, and keeping the fallback in the
    standard library avoids making the dashboard depend on a new package.
    """
    stripped = "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("#")
    ).strip()
    if not stripped:
        return {}
    parsed = json.loads(stripped)
    if not isinstance(parsed, dict):
        raise ValueError("investment thesis config must be a mapping")
    return parsed


def load_thesis_config(path: str | Path | None = None) -> dict[str, Any]:
    """Load a thesis config from YAML when available, otherwise JSON-compatible YAML."""
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    text = config_path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore
    except ModuleNotFoundError:
        return _json_compatible_yaml(text)

    parsed = yaml.safe_load(text)
    if not isinstance(parsed, dict):
        raise ValueError("investment thesis config must be a mapping")
    return parsed


def _lens_from_mapping(row: dict[str, Any]) -> ThesisLens:
    lens_id = str(row.get("id") or "").strip()
    if not lens_id:
        raise ValueError("thesis lens requires id")
    return ThesisLens(
        id=lens_id,
        label=str(row.get("label") or lens_id),
        weight=max(0.0, _as_float(row.get("weight"), 1.0)),
        austrian_principle=str(row.get("austrian_principle") or ""),
        positive_tags=_as_str_tuple(row.get("positive_tags")),
        negative_tags=_as_str_tuple(row.get("negative_tags")),
        source_requirements=_as_str_tuple(row.get("source_requirements")),
    )


def _asset_from_mapping(row: dict[str, Any]) -> ThesisAsset:
    symbol = str(row.get("symbol") or "").upper().strip()
    if not symbol:
        raise ValueError("thesis asset requires symbol")
    lens_scores = {
        str(key): _as_float(value)
        for key, value in _as_mapping(row.get("lens_scores")).items()
    }
    invalidations = tuple(
        _as_mapping(item) for item in _as_list(row.get("invalidation_triggers"))
    )
    return ThesisAsset(
        symbol=symbol,
        name=str(row.get("name") or symbol),
        asset_class=str(row.get("asset_class") or "watch"),
        conviction=max(0.0, min(1.0, _as_float(row.get("conviction"), 0.5))),
        thesis_tags=_as_str_tuple(row.get("thesis_tags")),
        lens_scores=lens_scores,
        venue_symbols={
            str(key): str(value)
            for key, value in _as_mapping(row.get("venue_symbols")).items()
            if str(value or "").strip()
        },
        evidence_sources=_as_str_tuple(row.get("evidence_sources")),
        invalidation_triggers=invalidations,
    )


def parse_lenses(config: dict[str, Any]) -> list[ThesisLens]:
    return [_lens_from_mapping(_as_mapping(row)) for row in _as_list(config.get("lenses"))]


def parse_assets(config: dict[str, Any]) -> list[ThesisAsset]:
    return [_asset_from_mapping(_as_mapping(row)) for row in _as_list(config.get("assets"))]


def _inferred_lens_value(asset: ThesisAsset, lens: ThesisLens) -> float:
    if lens.id in asset.lens_scores:
        return max(-1.0, min(1.0, asset.lens_scores[lens.id]))

    tags = set(asset.thesis_tags)
    positive = bool(tags.intersection(lens.positive_tags) or lens.id in tags)
    negative = bool(tags.intersection(lens.negative_tags))
    if positive and negative:
        return 0.25
    if positive:
        return 0.5
    if negative:
        return -0.5
    return 0.0


def _cell_state(value: float) -> str:
    if value >= 0.75:
        return "core"
    if value > 0:
        return "supporting"
    if value < 0:
        return "risk"
    return "neutral"


def _fit_label(relative_score: float) -> str:
    if relative_score >= 72:
        return "core"
    if relative_score >= 52:
        return "aligned"
    if relative_score >= 30:
        return "watch"
    return "speculative"


def _asset_lens_cells(asset: ThesisAsset, lenses: list[ThesisLens]) -> list[dict[str, Any]]:
    cells: list[dict[str, Any]] = []
    for lens in lenses:
        value = _inferred_lens_value(asset, lens)
        weighted = round(value * lens.weight * asset.conviction, 4)
        cells.append(
            {
                "id": lens.id,
                "label": lens.label,
                "value": round(value, 3),
                "weighted_score": weighted,
                "state": _cell_state(value),
                "source_requirements": list(lens.source_requirements) if value > 0 else [],
            }
        )
    return cells


def _source_gap(asset: ThesisAsset, cells: list[dict[str, Any]]) -> list[str]:
    required = {
        source
        for cell in cells
        if cell["state"] in {"core", "supporting"}
        for source in cell.get("source_requirements", [])
    }
    present = set(asset.evidence_sources)
    return sorted(required.difference(present))


def _asset_row(asset: ThesisAsset, lenses: list[ThesisLens], max_raw: float) -> dict[str, Any]:
    cells = _asset_lens_cells(asset, lenses)
    positive_score = sum(max(0.0, cell["weighted_score"]) for cell in cells)
    negative_score = sum(min(0.0, cell["weighted_score"]) for cell in cells)
    relative = round((positive_score / max_raw) * 100, 1) if max_raw > 0 else 0.0
    gaps = _source_gap(asset, cells)
    watch_flags = [
        {
            "id": str(trigger.get("id") or ""),
            "condition": str(trigger.get("condition") or ""),
            "severity": str(trigger.get("severity") or "medium"),
            "status": str(trigger.get("status") or "watch"),
        }
        for trigger in asset.invalidation_triggers
    ]
    aligned = [cell["id"] for cell in cells if cell["state"] == "core"]
    supporting = [cell["id"] for cell in cells if cell["state"] == "supporting"]
    return {
        "symbol": asset.symbol,
        "name": asset.name,
        "asset_class": asset.asset_class,
        "conviction": round(asset.conviction, 3),
        "relative_score": relative,
        "absolute_score": round(positive_score + negative_score, 4),
        "positive_score": round(positive_score, 4),
        "negative_score": round(negative_score, 4),
        "fit": _fit_label(relative),
        "thesis_tags": list(asset.thesis_tags),
        "venue_symbols": dict(asset.venue_symbols),
        "evidence_sources": list(asset.evidence_sources),
        "source_gaps": gaps,
        "lens_cells": cells,
        "aligned_lenses": aligned,
        "supporting_lenses": supporting,
        "invalidation_flags": watch_flags,
        "watch_count": len(watch_flags),
    }


def _ops_queue(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    queue: list[dict[str, Any]] = []
    for row in rows:
        if row["source_gaps"] and row["relative_score"] >= 45:
            queue.append(
                {
                    "priority": "P1",
                    "symbol": row["symbol"],
                    "action": "wire_source_coverage",
                    "reason": f"{len(row['source_gaps'])} missing evidence feeds for high-fit thesis",
                    "safe_mode": "read_only",
                }
            )
        if row["watch_count"] and row["relative_score"] >= 35:
            queue.append(
                {
                    "priority": "P2",
                    "symbol": row["symbol"],
                    "action": "monitor_invalidation_triggers",
                    "reason": f"{row['watch_count']} active watch conditions",
                    "safe_mode": "research_only",
                }
            )
        if "tradingview" not in row["venue_symbols"]:
            queue.append(
                {
                    "priority": "P3",
                    "symbol": row["symbol"],
                    "action": "complete_symbol_mapping",
                    "reason": "missing TradingView symbol for dashboard/backtest coverage",
                    "safe_mode": "metadata_only",
                }
            )
    priority_rank = {"P1": 0, "P2": 1, "P3": 2}
    queue.sort(key=lambda item: (priority_rank.get(item["priority"], 99), item["symbol"]))
    return queue[:24]


def _source_requirements(lenses: list[ThesisLens], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    for row in rows:
        for source in row["evidence_sources"]:
            counts[source] += 1
        for source in row["source_gaps"]:
            counts[source] += 1
    lens_map = {
        source: lens.id
        for lens in lenses
        for source in lens.source_requirements
    }
    return [
        {
            "id": source,
            "lens": lens_map.get(source, "asset_specific"),
            "asset_count": count,
            "configured": source not in {"gov:contract_awards", "policy:jurisdiction_scan", "macro:currency_stress"},
        }
        for source, count in counts.most_common()
    ]


def build_sovereign_thesis_report(config_path: str | Path | None = None) -> dict[str, Any]:
    """Build a read-only thesis matrix for dashboard/API consumers."""
    started = time.perf_counter()
    config = load_thesis_config(config_path)
    lenses = parse_lenses(config)
    assets = parse_assets(config)
    if not lenses:
        raise ValueError("investment thesis config has no lenses")
    if not assets:
        raise ValueError("investment thesis config has no assets")

    raw_rows = []
    max_score = 0.0
    for asset in assets:
        cells = _asset_lens_cells(asset, lenses)
        score = sum(max(0.0, cell["weighted_score"]) for cell in cells)
        max_score = max(max_score, score)
        raw_rows.append(asset)

    rows = [_asset_row(asset, lenses, max_score) for asset in raw_rows]
    rows.sort(key=lambda row: (row["relative_score"], row["conviction"], row["symbol"]), reverse=True)
    for index, row in enumerate(rows, start=1):
        row["rank"] = index

    fit_counts = Counter(row["fit"] for row in rows)
    class_counts = Counter(row["asset_class"] for row in rows)
    invalidations = [
        {
            "symbol": row["symbol"],
            **flag,
        }
        for row in rows
        for flag in row["invalidation_flags"]
    ]
    tripped = [flag for flag in invalidations if flag.get("status") == "tripped"]
    source_requirements = _source_requirements(lenses, rows)

    return {
        "generated_at": _now_iso(),
        "mode": "research_intel_only",
        "config_path": str(Path(config_path) if config_path else DEFAULT_CONFIG_PATH),
        "worldview": _as_mapping(config.get("worldview")),
        "safety": {
            "live_trading_enabled": False,
            "execution_enabled": False,
            "telegram_sends_enabled": False,
            "guards": [
                "research_intel_only",
                "no_order_signing",
                "no_order_submission",
                "no_external_mutation",
                "invalidation_before_action",
            ],
        },
        "totals": {
            "assets": len(rows),
            "lenses": len(lenses),
            "core_assets": fit_counts.get("core", 0),
            "aligned_assets": fit_counts.get("aligned", 0),
            "watch_assets": fit_counts.get("watch", 0),
            "speculative_assets": fit_counts.get("speculative", 0),
            "invalidation_watches": len(invalidations),
            "tripped_invalidations": len(tripped),
            "source_requirements": len(source_requirements),
        },
        "asset_classes": dict(sorted(class_counts.items())),
        "lenses": [asdict(lens) for lens in lenses],
        "assets": rows,
        "matrix": [
            {
                "symbol": row["symbol"],
                "fit": row["fit"],
                "relative_score": row["relative_score"],
                "lenses": {cell["id"]: cell for cell in row["lens_cells"]},
            }
            for row in rows
        ],
        "invalidation_queue": invalidations,
        "ops_queue": _ops_queue(rows),
        "source_requirements": source_requirements,
        "source_docs": list(_as_list(config.get("source_docs"))),
        "runtime_ms": round((time.perf_counter() - started) * 1000, 1),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the Sapphire sovereign thesis matrix")
    parser.add_argument("--config", default=None, help="Optional thesis config path")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON")
    args = parser.parse_args(argv)

    payload = build_sovereign_thesis_report(args.config)
    print(json.dumps(payload, indent=2 if args.pretty else None, sort_keys=args.pretty))
    return 0


__all__ = [
    "DEFAULT_CONFIG_PATH",
    "ThesisAsset",
    "ThesisLens",
    "build_sovereign_thesis_report",
    "load_thesis_config",
    "parse_assets",
    "parse_lenses",
]


if __name__ == "__main__":
    raise SystemExit(main())
