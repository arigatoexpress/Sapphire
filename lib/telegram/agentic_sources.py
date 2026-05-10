"""Agentic Telegram source registry loading and validation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY_PATH = REPO_ROOT / "config" / "agentic_telegram_sources.yaml"

VALID_ACCESS = {
    "authenticated_public_api",
    "bot_api",
    "gcp_public_dataset",
    "mtproto",
    "public_api",
    "public_dataset",
    "rss",
}
VALID_AUTH = {
    "api_key_optional",
    "api_key_required",
    "google_cloud_project",
    "none",
    "user_session_private",
}
VALID_DOMAINS = {
    "ai_market",
    "crypto_market",
    "cyber",
    "equities_regulatory",
    "exchange_market",
    "gcp_public",
    "global_news",
    "macro",
    "physical_world",
    "prediction_markets",
    "telegram_native",
}
VALID_OUTPUT_POLICIES = {
    "derived_features_only",
    "internal_only",
    "metadata_links_short_summaries",
    "public_facts_only",
    "no_redistribution",
}
VALID_TELEGRAM_USES = {
    "do_not_post",
    "p0_alert",
    "p1_digest",
    "p2_context",
    "research_only",
}
VALID_STATUSES = {
    "existing_adapter",
    "existing_config",
    "proposed",
    "watchlist",
}
VALID_SURFACE_STATUSES = {
    "existing",
    "existing_partial",
    "proposed",
    "watchlist",
}
FORBIDDEN_OUTPUT_POLICY_TOKENS = {
    "full_article",
    "paywall",
    "raw_payload",
    "raw_redistribution",
    "scrape_login",
    "verbatim",
}


class RegistryError(ValueError):
    """Raised when the agentic Telegram source registry is malformed."""


def _require_mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RegistryError(f"{field} must be a mapping")
    return value


def _require_list(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise RegistryError(f"{field} must be a list")
    return value


def _require_text(row: dict[str, Any], field: str, *, source_id: str | None = None) -> str:
    value = str(row.get(field) or "").strip()
    if not value:
        label = f"source {source_id!r}" if source_id else "registry"
        raise RegistryError(f"{label} requires {field}")
    return value


def _require_member(
    row: dict[str, Any],
    field: str,
    allowed: set[str],
    *,
    source_id: str,
) -> str:
    value = _require_text(row, field, source_id=source_id)
    if value not in allowed:
        expected = ", ".join(sorted(allowed))
        raise RegistryError(f"{source_id}.{field}={value!r} unsupported; expected {expected}")
    return value


def _validate_policy(policy: dict[str, Any]) -> None:
    if policy.get("telegram_send_default") != "dry_run_only":
        raise RegistryError("policy.telegram_send_default must remain dry_run_only")
    if policy.get("local_inference_default") != "disabled":
        raise RegistryError("policy.local_inference_default must remain disabled")
    for field in (
        "no_paywall_bypass",
        "no_secret_sources_in_repo",
        "no_trading_or_money_movement",
        "require_provenance_envelope",
        "require_human_confirm_for_external_send",
    ):
        if policy.get(field) is not True:
            raise RegistryError(f"policy.{field} must be true")


def _validate_model_roles(model_roles: list[Any]) -> None:
    seen: set[str] = set()
    for raw in model_roles:
        row = _require_mapping(raw, "model_roles entry")
        role_id = _require_text(row, "id")
        if role_id in seen:
            raise RegistryError(f"duplicate model role id: {role_id}")
        seen.add(role_id)
        _require_text(row, "provider", source_id=role_id)
        _require_text(row, "recommended_model", source_id=role_id)
        _require_text(row, "role", source_id=role_id)
        safety = _require_text(row, "safety", source_id=role_id).lower()
        if "send" in safety and "telegram" in safety and "confirmation" not in safety:
            raise RegistryError(f"{role_id}.safety must mention confirmation for Telegram sends")


def _validate_telegram_surfaces(surfaces: list[Any]) -> None:
    seen: set[str] = set()
    for raw in surfaces:
        row = _require_mapping(raw, "telegram_surfaces entry")
        surface_id = _require_text(row, "id")
        if surface_id in seen:
            raise RegistryError(f"duplicate Telegram surface id: {surface_id}")
        seen.add(surface_id)
        _require_text(row, "feature", source_id=surface_id)
        _require_member(row, "status", VALID_SURFACE_STATUSES, source_id=surface_id)
        _require_text(row, "use", source_id=surface_id)


def _validate_sources(sources: list[Any]) -> None:
    seen: set[str] = set()
    tier_zero_count = 0
    for raw in sources:
        row = _require_mapping(raw, "sources entry")
        source_id = _require_text(row, "id")
        if source_id in seen:
            raise RegistryError(f"duplicate source id: {source_id}")
        seen.add(source_id)
        _require_text(row, "name", source_id=source_id)
        _require_member(row, "domain", VALID_DOMAINS, source_id=source_id)
        _require_member(row, "access", VALID_ACCESS, source_id=source_id)
        _require_member(row, "auth", VALID_AUTH, source_id=source_id)
        _require_member(row, "telegram_use", VALID_TELEGRAM_USES, source_id=source_id)
        _require_member(row, "output_policy", VALID_OUTPUT_POLICIES, source_id=source_id)
        _require_member(row, "sapphire_status", VALID_STATUSES, source_id=source_id)
        _require_text(row, "official_url", source_id=source_id)
        _require_text(row, "cadence", source_id=source_id)
        _require_text(row, "signal", source_id=source_id)
        _require_text(row, "rights", source_id=source_id)
        _require_text(row, "adapter_hint", source_id=source_id)
        constraints = _require_list(row.get("constraints"), f"{source_id}.constraints")
        if not constraints:
            raise RegistryError(f"{source_id}.constraints must not be empty")
        output_text = " ".join(
            str(row.get(field) or "").lower()
            for field in ("output_policy", "rights", "signal", "constraints")
        )
        blocked = sorted(token for token in FORBIDDEN_OUTPUT_POLICY_TOKENS if token in output_text)
        if blocked:
            raise RegistryError(f"{source_id} contains forbidden output-policy token(s): {blocked}")
        tier = row.get("tier")
        if not isinstance(tier, int) or tier < 0 or tier > 3:
            raise RegistryError(f"{source_id}.tier must be an integer from 0 to 3")
        if tier == 0:
            tier_zero_count += 1
    if tier_zero_count < 5:
        raise RegistryError("registry must include at least five tier-0 sources")


def validate_registry(registry: dict[str, Any]) -> dict[str, Any]:
    """Validate and return ``registry`` for convenient call chaining."""

    if registry.get("schema_version") != 1:
        raise RegistryError("schema_version must be 1")
    _validate_policy(_require_mapping(registry.get("policy"), "policy"))
    _validate_model_roles(_require_list(registry.get("model_roles"), "model_roles"))
    _validate_telegram_surfaces(
        _require_list(registry.get("telegram_surfaces"), "telegram_surfaces")
    )
    _validate_sources(_require_list(registry.get("sources"), "sources"))
    return registry


def load_registry(path: str | Path | None = None) -> dict[str, Any]:
    """Load and validate the agentic Telegram source registry."""

    registry_path = Path(path).expanduser() if path else DEFAULT_REGISTRY_PATH
    try:
        loaded = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise RegistryError(f"registry parse failed: {exc.__class__.__name__}") from exc
    return validate_registry(_require_mapping(loaded, "registry"))


def sources_by_domain(registry: dict[str, Any] | None = None) -> dict[str, list[str]]:
    """Return source ids grouped by domain for dashboards and smoke tests."""

    data = registry or load_registry()
    grouped: dict[str, list[str]] = {}
    for source in _require_list(data.get("sources"), "sources"):
        row = _require_mapping(source, "sources entry")
        grouped.setdefault(str(row["domain"]), []).append(str(row["id"]))
    return {domain: sorted(ids) for domain, ids in sorted(grouped.items())}
