"""On-chain intelligence aggregator 0.2.0.

The aggregator is dry-run by default. Provider clients may make live calls only
when their provider-specific live flag and credential/RPC env var are both
present. This keeps unit tests hermetic and keeps operator opt-in explicit.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "0.2.0"
DEFAULT_ASSETS = ("BTC", "ETH", "SOL")
PROVIDER_HOUR_CAP = 60
PROVIDER_DAY_CAP = 100_000
MAX_BACKFILL_DAYS = 730

_TRUE_VALUES = {"1", "true", "yes", "on"}
_USAGE_LOCK = threading.Lock()

_PROVIDER_GATES: dict[str, str] = {
    "glassnode": "SAPPHIRE_GLASSNODE_LIVE",
    "santiment": "SAPPHIRE_SANTIMENT_LIVE",
    "eth_node": "SAPPHIRE_ETH_NODE_LIVE",
    "sol_node": "SAPPHIRE_SOL_NODE_LIVE",
}

_PROVIDER_CREDENTIALS: dict[str, tuple[str, ...]] = {
    "glassnode": ("GLASSNODE_API_KEY",),
    "santiment": ("SANTIMENT_API_KEY",),
    "eth_node": ("ETH_RPC_URL", "ETHEREUM_RPC_URL"),
    "sol_node": ("SOL_RPC_URL", "SOLANA_RPC_URL"),
}


class RateCapError(RuntimeError):
    """Raised before a live provider call would exceed Sapphire caps."""


@dataclass
class ProviderStatus:
    provider: str
    mode: str
    gate_env: str
    credential_envs: list[str]
    gate_enabled: bool
    credential_present: bool
    live_enabled: bool
    hour_cap: int = PROVIDER_HOUR_CAP
    day_cap: int = PROVIDER_DAY_CAP
    backfill_days_max: int = MAX_BACKFILL_DAYS
    error: str | None = None


@dataclass
class OnChainSnapshot:
    schema_version: str
    generated_at: str
    assets: dict[str, dict[str, Any]]
    nodes: dict[str, dict[str, Any]]
    providers: dict[str, dict[str, Any]]
    summary: dict[str, Any]
    limits: dict[str, int]
    warnings: list[str] = field(default_factory=list)
    wallet_keys_required: bool = False
    trading_enabled: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def env_flag(name: str) -> bool:
    """Return true for explicit operator live toggles."""

    return os.getenv(name, "").strip().lower() in _TRUE_VALUES


def clamp_backfill_days(days: int | str | None) -> int:
    """Clamp user/provider backfills to the Sapphire 730-day ceiling."""

    try:
        value = int(days) if days is not None else 30
    except (TypeError, ValueError):
        value = 30
    return max(1, min(MAX_BACKFILL_DAYS, value))


def provider_live_enabled(provider: str) -> bool:
    gate = _PROVIDER_GATES.get(provider)
    credentials = _PROVIDER_CREDENTIALS.get(provider, ())
    return bool(gate and env_flag(gate) and any(os.getenv(name, "") for name in credentials))


def provider_status(provider: str) -> ProviderStatus:
    gate = _PROVIDER_GATES.get(provider, "")
    credentials = list(_PROVIDER_CREDENTIALS.get(provider, ()))
    gate_enabled = env_flag(gate) if gate else False
    credential_present = any(os.getenv(name, "") for name in credentials)
    live_enabled = bool(gate_enabled and credential_present)
    return ProviderStatus(
        provider=provider,
        mode="live" if live_enabled else "fixture",
        gate_env=gate,
        credential_envs=credentials,
        gate_enabled=gate_enabled,
        credential_present=credential_present,
        live_enabled=live_enabled,
    )


def provider_matrix() -> dict[str, dict[str, Any]]:
    return {
        provider: asdict(provider_status(provider))
        for provider in ("glassnode", "santiment", "eth_node", "sol_node")
    }


def _usage_file() -> Path:
    override = os.getenv("SAPPHIRE_ONCHAIN_USAGE_FILE")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".sapphire" / "onchain_intel" / "usage.json"


def _read_usage(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def enforce_provider_cap(
    provider: str,
    *,
    cost: int = 1,
    now: datetime | None = None,
    hour_cap: int = PROVIDER_HOUR_CAP,
    day_cap: int = PROVIDER_DAY_CAP,
) -> dict[str, int]:
    """Increment local live-call usage or raise before exceeding a cap."""

    if cost <= 0:
        return {"hour": 0, "day": 0}
    now = now or datetime.now(UTC)
    hour_key = now.strftime("%Y-%m-%dT%HZ")
    day_key = now.strftime("%Y-%m-%d")
    path = _usage_file()
    with _USAGE_LOCK:
        usage = _read_usage(path)
        provider_usage = usage.setdefault(provider, {})
        hourly = provider_usage.setdefault("hourly", {})
        daily = provider_usage.setdefault("daily", {})
        hour_count = int(hourly.get(hour_key, 0))
        day_count = int(daily.get(day_key, 0))
        if hour_count + cost > hour_cap:
            raise RateCapError(f"{provider}: hourly live cap exceeded ({hour_count}/{hour_cap})")
        if day_count + cost > day_cap:
            raise RateCapError(f"{provider}: daily live cap exceeded ({day_count}/{day_cap})")
        hourly.clear()
        daily.clear()
        hourly[hour_key] = hour_count + cost
        daily[day_key] = day_count + cost
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(usage, indent=2, sort_keys=True))
        return {"hour": hourly[hour_key], "day": daily[day_key]}


def _to_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def latest_series_value(series: Any) -> float | None:
    """Extract the latest numeric value from common provider series shapes."""

    if not isinstance(series, list) or not series:
        return None
    latest = series[-1]
    if isinstance(latest, dict):
        if "v" in latest:
            return _to_float(latest.get("v"))
        if "value" in latest:
            return _to_float(latest.get("value"))
    return _to_float(latest)


class OnChainAggregator:
    """Build the Sapphire on-chain intelligence snapshot."""

    def __init__(self, assets: list[str] | None = None, backfill_days: int | None = None) -> None:
        self.assets = [asset.upper() for asset in (assets or list(DEFAULT_ASSETS))]
        self.backfill_days = clamp_backfill_days(backfill_days)

    def snapshot(self) -> dict[str, Any]:
        providers = provider_matrix()
        warnings: list[str] = []
        assets: dict[str, dict[str, Any]] = {
            asset: {"asset": asset, "glassnode": {}, "santiment": {}, "composite": {}}
            for asset in self.assets
        }
        nodes: dict[str, dict[str, Any]] = {}

        self._collect_glassnode(assets, providers, warnings)
        self._collect_santiment(assets, providers, warnings)
        self._collect_eth_node(nodes, providers, warnings)
        self._collect_sol_node(nodes, providers, warnings)

        for asset, row in assets.items():
            row["composite"] = self._score_asset(asset, row)

        live_enabled = [
            name for name, status in providers.items() if bool(status.get("live_enabled"))
        ]
        snapshot = OnChainSnapshot(
            schema_version=SCHEMA_VERSION,
            generated_at=datetime.now(UTC).isoformat(),
            assets=assets,
            nodes=nodes,
            providers=providers,
            summary={
                "asset_count": len(assets),
                "live_provider_count": len(live_enabled),
                "live_providers": live_enabled,
                "mode": "mixed-live" if live_enabled else "fixture",
                "wallet_keys_required": False,
                "trading_enabled": False,
            },
            limits={
                "per_provider_hour": PROVIDER_HOUR_CAP,
                "per_provider_day": PROVIDER_DAY_CAP,
                "backfill_days_max": MAX_BACKFILL_DAYS,
                "backfill_days_requested": self.backfill_days,
            },
            warnings=warnings,
        )
        return snapshot.to_dict()

    def _collect_glassnode(
        self,
        assets: dict[str, dict[str, Any]],
        providers: dict[str, dict[str, Any]],
        warnings: list[str],
    ) -> None:
        try:
            from lib.chain.providers.glassnode import GlassnodeClient

            client = GlassnodeClient()
            for asset in assets:
                assets[asset]["glassnode"] = client.asset_snapshot(asset, days=self.backfill_days)
        except Exception as exc:  # noqa: BLE001 - provider errors degrade the snapshot
            providers["glassnode"]["error"] = f"{exc.__class__.__name__}: {exc}"[:240]
            warnings.append(f"glassnode unavailable: {exc.__class__.__name__}")

    def _collect_santiment(
        self,
        assets: dict[str, dict[str, Any]],
        providers: dict[str, dict[str, Any]],
        warnings: list[str],
    ) -> None:
        try:
            from lib.chain.providers.santiment import SantimentClient

            client = SantimentClient()
            for asset in assets:
                assets[asset]["santiment"] = client.asset_snapshot(asset, days=self.backfill_days)
        except Exception as exc:  # noqa: BLE001
            providers["santiment"]["error"] = f"{exc.__class__.__name__}: {exc}"[:240]
            warnings.append(f"santiment unavailable: {exc.__class__.__name__}")

    def _collect_eth_node(
        self,
        nodes: dict[str, dict[str, Any]],
        providers: dict[str, dict[str, Any]],
        warnings: list[str],
    ) -> None:
        try:
            from lib.chain.providers.eth_node import EthNodeClient

            nodes["ethereum"] = EthNodeClient().network_snapshot()
        except Exception as exc:  # noqa: BLE001
            providers["eth_node"]["error"] = f"{exc.__class__.__name__}: {exc}"[:240]
            warnings.append(f"eth_node unavailable: {exc.__class__.__name__}")

    def _collect_sol_node(
        self,
        nodes: dict[str, dict[str, Any]],
        providers: dict[str, dict[str, Any]],
        warnings: list[str],
    ) -> None:
        try:
            from lib.chain.providers.sol_node import SolNodeClient

            nodes["solana"] = SolNodeClient().network_snapshot()
        except Exception as exc:  # noqa: BLE001
            providers["sol_node"]["error"] = f"{exc.__class__.__name__}: {exc}"[:240]
            warnings.append(f"sol_node unavailable: {exc.__class__.__name__}")

    def _score_asset(self, asset: str, row: dict[str, Any]) -> dict[str, Any]:
        glassnode = row.get("glassnode") or {}
        santiment = row.get("santiment") or {}
        components: list[float] = []
        notes: list[str] = []

        active = _to_float(glassnode.get("active_addresses"))
        if active is not None:
            components.append(min(1.0, active / 1_000_000.0))
            notes.append("glassnode_active_addresses")

        tx_rate = _to_float(glassnode.get("transaction_rate"))
        if tx_rate is not None:
            components.append(min(1.0, tx_rate / 10.0))
            notes.append("glassnode_transaction_rate")

        nupl = _to_float(glassnode.get("nupl"))
        if nupl is not None:
            components.append(max(0.0, min(1.0, (nupl + 0.25) / 1.0)))
            notes.append("glassnode_nupl")

        mvrv_z = _to_float(glassnode.get("mvrv_z"))
        if mvrv_z is not None:
            components.append(min(1.0, mvrv_z / 7.0))
            notes.append("glassnode_mvrv_z")

        social = _to_float(santiment.get("social_volume_total"))
        if social is not None:
            components.append(min(1.0, social / 5_000.0))
            notes.append("santiment_social_volume")

        growth = _to_float(santiment.get("network_growth"))
        if growth is not None:
            components.append(min(1.0, growth / 150_000.0))
            notes.append("santiment_network_growth")

        dev = _to_float(santiment.get("dev_activity"))
        if dev is not None:
            components.append(min(1.0, dev / 250.0))
            notes.append("santiment_dev_activity")

        heat = round(sum(components) / len(components) * 100, 2) if components else 0.0
        return {
            "asset": asset,
            "onchain_heat_score": heat,
            "input_count": len(components),
            "inputs": notes,
        }


def build_snapshot(
    *,
    assets: list[str] | None = None,
    backfill_days: int | None = None,
) -> dict[str, Any]:
    return OnChainAggregator(assets=assets, backfill_days=backfill_days).snapshot()


__all__ = [
    "MAX_BACKFILL_DAYS",
    "PROVIDER_DAY_CAP",
    "PROVIDER_HOUR_CAP",
    "RateCapError",
    "build_snapshot",
    "clamp_backfill_days",
    "enforce_provider_cap",
    "env_flag",
    "latest_series_value",
    "provider_live_enabled",
    "provider_matrix",
    "provider_status",
]
