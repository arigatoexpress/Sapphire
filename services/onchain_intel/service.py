"""Service helpers for Sapphire on-chain intelligence snapshots."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from lib.chain.aggregator import build_snapshot, clamp_backfill_days, provider_matrix
from lib.core.provenance import write_envelope_sidecar

ROOT = Path(__file__).resolve().parents[2]
LATEST_DIR = ROOT / "data" / "intelligence" / "latest"
ARCHIVE_DIR = ROOT / "data" / "onchain_intel"


def build_status() -> dict[str, Any]:
    providers = provider_matrix()
    live = [name for name, row in providers.items() if row.get("live_enabled")]
    return {
        "service": "onchain_intel",
        "schema_version": "0.2.0",
        "mode": "mixed-live" if live else "fixture",
        "providers": providers,
        "live_providers": live,
        "wallet_keys_required": False,
        "trading_enabled": False,
    }


def collect_snapshot(
    *,
    assets: list[str] | None = None,
    backfill_days: int | None = None,
) -> dict[str, Any]:
    return build_snapshot(assets=assets, backfill_days=clamp_backfill_days(backfill_days))


def write_snapshot(snapshot: dict[str, Any], *, latest_dir: Path | None = None) -> dict[str, str]:
    latest_root = latest_dir or LATEST_DIR
    archive_root = ARCHIVE_DIR if latest_dir is None else latest_root / "archive"
    latest_root.mkdir(parents=True, exist_ok=True)
    archive_root.mkdir(parents=True, exist_ok=True)

    generated_at = str(snapshot.get("generated_at") or datetime.now(UTC).isoformat())
    safe_ts = generated_at.replace(":", "-")
    archive_path = archive_root / f"onchain_intel_{safe_ts}.json"
    latest_path = latest_root / "onchain_intel.json"
    payload = json.dumps(snapshot, indent=2, sort_keys=True, default=str)
    archive_path.write_text(payload)
    latest_path.write_text(payload)
    archive_sidecar = write_envelope_sidecar(
        archive_path,
        generator="services.onchain_intel.service",
        source_paths=("lib/chain/aggregator.py",),
        metadata={"artifact": "onchain_snapshot_archive", "schema_version": "0.2.0"},
    )
    latest_sidecar = write_envelope_sidecar(
        latest_path,
        generator="services.onchain_intel.service",
        source_paths=("lib/chain/aggregator.py",),
        metadata={"artifact": "onchain_snapshot_latest", "schema_version": "0.2.0"},
    )
    return {
        "archive_path": str(archive_path),
        "archive_envelope_path": str(archive_sidecar),
        "latest_path": str(latest_path),
        "latest_envelope_path": str(latest_sidecar),
    }
