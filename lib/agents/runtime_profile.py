"""Fresh agent runtime profile loading and validation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROFILE_PATH = REPO_ROOT / "config" / "agent_runtime_next.yaml"

REQUIRED_POLICY_TRUE = (
    "no_second_telegram_poller",
    "no_public_or_customer_sends",
    "no_live_trading_or_money_movement",
)
VALID_DEPRECATED_STATES = {"disabled", "quarantined"}


class RuntimeProfileError(ValueError):
    """Raised when the fresh runtime profile is unsafe or malformed."""


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RuntimeProfileError(f"{field} must be a mapping")
    return value


def _list(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise RuntimeProfileError(f"{field} must be a list")
    return value


def _text(row: dict[str, Any], field: str, *, owner: str = "profile") -> str:
    value = str(row.get(field) or "").strip()
    if not value:
        raise RuntimeProfileError(f"{owner} requires {field}")
    return value


def validate_runtime_profile(profile: dict[str, Any]) -> dict[str, Any]:
    """Validate and return a fresh Sapphire agent runtime profile."""

    if profile.get("schema_version") != 1:
        raise RuntimeProfileError("schema_version must be 1")

    policy = _mapping(profile.get("policy"), "policy")
    if policy.get("telegram_send_default") != "draft_only":
        raise RuntimeProfileError("policy.telegram_send_default must remain draft_only")
    if policy.get("bot_api_ingress_owner") != "sapphire_pm_bot":
        raise RuntimeProfileError("policy.bot_api_ingress_owner must remain sapphire_pm_bot")
    if policy.get("local_inference_default") != "fallback_only":
        raise RuntimeProfileError("policy.local_inference_default must remain fallback_only")
    for field in REQUIRED_POLICY_TRUE:
        if policy.get(field) is not True:
            raise RuntimeProfileError(f"policy.{field} must be true")

    _validate_harnesses(_list(profile.get("harnesses"), "harnesses"))
    _validate_model_lanes(_list(profile.get("model_lanes"), "model_lanes"))
    _validate_deprecated_runtimes(_list(profile.get("deprecated_runtimes"), "deprecated_runtimes"))
    _validate_deprecated_models(
        _list(profile.get("deprecated_default_models"), "deprecated_default_models")
    )
    return profile


def load_runtime_profile(path: str | Path | None = None) -> dict[str, Any]:
    """Load and validate the fresh runtime profile."""

    profile_path = Path(path).expanduser() if path else DEFAULT_PROFILE_PATH
    try:
        loaded = yaml.safe_load(profile_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise RuntimeProfileError(
            f"runtime profile parse failed: {exc.__class__.__name__}"
        ) from exc
    return validate_runtime_profile(_mapping(loaded, "runtime profile"))


def required_local_models(profile: dict[str, Any] | None = None) -> list[str]:
    """Return local Ollama models required by fallback lanes."""

    data = profile or load_runtime_profile()
    models: list[str] = []
    for lane in _list(data.get("model_lanes"), "model_lanes"):
        row = _mapping(lane, "model_lanes entry")
        if row.get("runtime") != "mac_local":
            continue
        for field in ("recommended_model", "fallback_model"):
            value = str(row.get(field) or "").strip()
            if value and value not in models:
                models.append(value)
    return models


def deprecated_launchagent_labels(profile: dict[str, Any] | None = None) -> list[str]:
    """Return LaunchAgent labels that should be disabled or quarantined."""

    data = profile or load_runtime_profile()
    labels = [
        _text(_mapping(row, "deprecated_runtimes entry"), "label", owner="deprecated_runtime")
        for row in _list(data.get("deprecated_runtimes"), "deprecated_runtimes")
    ]
    return sorted(labels)


def _validate_harnesses(harnesses: list[Any]) -> None:
    seen: set[str] = set()
    required = {"google_adk", "sapphire_pm_bot_router", "telegram_draft_queue"}
    for raw in harnesses:
        row = _mapping(raw, "harnesses entry")
        harness_id = _text(row, "id", owner="harness")
        if harness_id in seen:
            raise RuntimeProfileError(f"duplicate harness id: {harness_id}")
        seen.add(harness_id)
        _text(row, "provider", owner=harness_id)
        _text(row, "status", owner=harness_id)
        _text(row, "use", owner=harness_id)
        safety = _text(row, "safety", owner=harness_id).lower()
        if "send" in safety and "confirm" not in safety and "must not" not in safety:
            raise RuntimeProfileError(f"{harness_id}.safety must preserve send confirmation")
    missing = sorted(required - seen)
    if missing:
        raise RuntimeProfileError(f"runtime profile missing harnesses: {missing}")


def _validate_model_lanes(lanes: list[Any]) -> None:
    seen: set[str] = set()
    default_providers: set[str] = set()
    for raw in lanes:
        row = _mapping(raw, "model_lanes entry")
        lane_id = _text(row, "id", owner="model_lane")
        if lane_id in seen:
            raise RuntimeProfileError(f"duplicate model lane id: {lane_id}")
        seen.add(lane_id)
        provider = _text(row, "provider", owner=lane_id)
        model = _text(row, "recommended_model", owner=lane_id)
        _text(row, "runtime", owner=lane_id)
        _text(row, "use", owner=lane_id)
        _text(row, "safety", owner=lane_id)
        if row.get("default") is True:
            default_providers.add(provider)
            if "nemotron" in model.lower() or "hermes3" in model.lower():
                raise RuntimeProfileError(f"{lane_id} cannot default to deprecated local model")
    for provider in ("kimi", "google_vertex"):
        if provider not in default_providers:
            raise RuntimeProfileError(f"missing default hosted provider: {provider}")


def _validate_deprecated_runtimes(rows: list[Any]) -> None:
    labels: set[str] = set()
    for raw in rows:
        row = _mapping(raw, "deprecated_runtimes entry")
        label = _text(row, "label", owner="deprecated_runtime")
        if label in labels:
            raise RuntimeProfileError(f"duplicate deprecated runtime: {label}")
        labels.add(label)
        state = _text(row, "expected_state", owner=label)
        if state not in VALID_DEPRECATED_STATES:
            raise RuntimeProfileError(f"{label}.expected_state must be disabled or quarantined")
        _text(row, "reason", owner=label)


def _validate_deprecated_models(rows: list[Any]) -> None:
    if not rows:
        raise RuntimeProfileError("deprecated_default_models must not be empty")
    for raw in rows:
        row = _mapping(raw, "deprecated_default_models entry")
        _text(row, "model", owner="deprecated_default_model")
        _text(row, "reason", owner="deprecated_default_model")
