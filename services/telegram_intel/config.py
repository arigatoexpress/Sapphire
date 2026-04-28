"""Configuration loader for Telegram channel intel collection."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from services.telegram_intel.models import MAX_CHANNELS, VALID_CATEGORIES, ChannelConfig

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = Path.home() / ".sapphire" / "telegram_channels.yaml"
DEFAULT_EXAMPLE_CONFIG_PATH = REPO_ROOT / "infra" / "telegram_channels.example.yaml"
DEFAULT_DATA_DIR = REPO_ROOT / "data" / "telegram_intel"


class ConfigError(ValueError):
    """Raised when the reader config is malformed."""


@dataclass(frozen=True)
class TelegramIntelConfig:
    channels: tuple[ChannelConfig, ...]
    poll_interval_seconds: int = 300
    max_messages_per_poll: int = 25
    classifier_enabled: bool = False
    classifier_model: str = "balanced"
    data_dir: Path = DEFAULT_DATA_DIR

    @property
    def enabled_channels(self) -> tuple[ChannelConfig, ...]:
        return tuple(channel for channel in self.channels if channel.enabled)

    @property
    def pull_limit_per_channel(self) -> int:
        """Backward-compatible alias for older callers."""
        return self.max_messages_per_poll

    def validate(self) -> TelegramIntelConfig:
        enabled = self.enabled_channels
        if len(enabled) > MAX_CHANNELS:
            raise ConfigError(f"enabled channel cap exceeded: {len(enabled)}/{MAX_CHANNELS}")
        if self.max_messages_per_poll < 1:
            raise ConfigError("max_messages_per_poll must be >= 1")
        if self.poll_interval_seconds < 30:
            raise ConfigError("poll_interval_seconds must be >= 30")
        return self


def _as_bool(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    return str(value).strip().lower() in {"1", "true", "yes", "on", "enabled"}


def _as_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (list, tuple, set)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return (str(value).strip(),)


def _as_int(value: Any, default: int, *, lo: int, hi: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(lo, min(parsed, hi))


def _as_float(value: Any, default: float, *, lo: float, hi: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(lo, min(parsed, hi))


def normalize_backend(value: Any) -> str:
    backend = str(value or "mtproto").strip().lower()
    if backend == "botapi":
        return "bot"
    return backend


def _category_from(row: dict[str, Any], defaults: dict[str, Any]) -> str:
    raw = row.get("category") or defaults.get("category")
    if raw:
        category = str(raw).strip().lower()
    else:
        category = ""
        for topic in _as_tuple(row.get("topics")):
            candidate = str(topic).strip().lower()
            if candidate in VALID_CATEGORIES:
                category = candidate
                break
    return category or "security"


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ConfigError(f"config not found: {path}")
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"config parse failed: {exc.__class__.__name__}") from exc
    if not isinstance(loaded, dict):
        raise ConfigError("config root must be a mapping")
    return loaded


def load_config(path: str | Path | None = None) -> TelegramIntelConfig:
    config_path = Path(path).expanduser() if path else DEFAULT_CONFIG_PATH
    raw = _load_yaml(config_path)
    defaults = raw.get("defaults") or {}
    classifier = raw.get("classifier") or {}
    if not isinstance(defaults, dict) or not isinstance(classifier, dict):
        raise ConfigError("defaults and classifier must be mappings")

    channels_raw = raw.get("channels") or []
    if not isinstance(channels_raw, list):
        raise ConfigError("channels must be a list")

    default_backend = normalize_backend(defaults.get("backend") or "mtproto")
    default_min_quality = _as_float(
        defaults.get("min_quality_score", defaults.get("min_quality")),
        0.45,
        lo=0.0,
        hi=1.0,
    )
    default_min_length = _as_int(defaults.get("min_message_length"), 32, lo=1, hi=1000)
    channels: list[ChannelConfig] = []
    seen_ids: set[str] = set()
    for row in channels_raw:
        if not isinstance(row, dict):
            raise ConfigError("each channel entry must be a mapping")
        channel_id = str(row.get("id") or "").strip()
        source = str(row.get("source") or channel_id).strip()
        if not channel_id:
            raise ConfigError("each channel requires id")
        if channel_id in seen_ids:
            raise ConfigError(f"duplicate channel id: {channel_id}")
        seen_ids.add(channel_id)
        backend = normalize_backend(row.get("backend") or default_backend)
        if backend not in {"mtproto", "bot"}:
            raise ConfigError(f"unsupported backend for {channel_id}: {backend}")
        category = _category_from(row, defaults)
        if category not in VALID_CATEGORIES:
            raise ConfigError(
                f"unsupported category for {channel_id}: {category}; "
                f"expected one of {', '.join(sorted(VALID_CATEGORIES))}"
            )
        channels.append(
            ChannelConfig(
                id=channel_id,
                source=source,
                category=category,
                weight=_as_float(row.get("weight"), 1.0, lo=0.1, hi=3.0),
                enabled=_as_bool(row.get("enabled"), default=True),
                backend=backend,
                label=str(row.get("label") or channel_id).strip(),
                topics=_as_tuple(row.get("topics")),
                notes=str(row.get("notes") or "").strip(),
                min_quality_score=_as_float(
                    row.get("min_quality_score", row.get("min_quality")),
                    default_min_quality,
                    lo=0.0,
                    hi=1.0,
                ),
                min_message_length=_as_int(
                    row.get("min_message_length"),
                    default_min_length,
                    lo=1,
                    hi=1000,
                ),
            )
        )

    data_dir_raw = raw.get("data_dir") or defaults.get("data_dir")
    data_dir = Path(data_dir_raw).expanduser() if data_dir_raw else DEFAULT_DATA_DIR
    if not data_dir.is_absolute():
        data_dir = REPO_ROOT / data_dir

    return TelegramIntelConfig(
        channels=tuple(channels),
        poll_interval_seconds=_as_int(
            defaults.get("poll_interval_seconds"), 300, lo=30, hi=3600
        ),
        max_messages_per_poll=_as_int(
            defaults.get("max_messages_per_poll", defaults.get("pull_limit_per_channel")),
            25,
            lo=1,
            hi=100,
        ),
        classifier_enabled=_as_bool(classifier.get("enabled"), default=False),
        classifier_model=str(classifier.get("model") or "balanced"),
        data_dir=data_dir,
    ).validate()
