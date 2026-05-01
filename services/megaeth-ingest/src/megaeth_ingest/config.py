"""Config loading for the MegaETH ingest service.

Resolution order (highest precedence first):
    1. Environment variables (``SAPPHIRE_MEGAETH_*``)
    2. ``config/megaeth.yaml`` if present
    3. Hard-coded testnet defaults (read-only)

The service is **read-only** — it never signs transactions. Endpoints below are
public testnet WSS endpoints; override via env or YAML for production.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - service requirements include PyYAML.
    yaml = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# MegaETH testnet WSS — public sequencer endpoint.
DEFAULT_WSS = "wss://carrot.megaeth.com/ws"
DEFAULT_CHAIN_ID = 6342  # MegaETH testnet
DEFAULT_HEALTH_PORT = 8788
DEFAULT_SIGNAL_LOGGER_URL = "http://127.0.0.1:18081/api/signals"
DEFAULT_QUEUE_MAX = 4096
DEFAULT_RECONNECT_BACKOFF_SEC = 2.0
DEFAULT_RECONNECT_MAX_SEC = 60.0

CONFIG_FILE_DEFAULT = Path("config/megaeth.yaml")
KILLSWITCH_PATH_DEFAULT = Path.home() / ".sapphire" / "megaeth_ingest_pause"
ROUTINE_NAME = "megaeth-ingest"


@dataclass(frozen=True)
class LogFilter:
    """A single ``logs`` subscription filter.

    ``addresses`` is required (we never want a wide-open log subscription on
    a 10ms-block chain — that would melt the queue). ``topics`` is optional;
    each entry may be a single topic hex string or a list (OR semantics).
    """

    addresses: tuple[str, ...]
    topics: tuple[Any, ...] = ()

    def to_subscription_params(self) -> dict[str, Any]:
        params: dict[str, Any] = {"address": list(self.addresses)}
        if self.topics:
            params["topics"] = list(self.topics)
        return params


@dataclass(frozen=True)
class IngestConfig:
    """Resolved MegaETH ingest configuration."""

    wss_url: str = DEFAULT_WSS
    chain_id: int = DEFAULT_CHAIN_ID
    health_port: int = DEFAULT_HEALTH_PORT
    signal_logger_url: str = DEFAULT_SIGNAL_LOGGER_URL
    webhook_secret: str = ""
    forwarding_enabled: bool = False
    queue_max: int = DEFAULT_QUEUE_MAX
    reconnect_backoff_sec: float = DEFAULT_RECONNECT_BACKOFF_SEC
    reconnect_max_sec: float = DEFAULT_RECONNECT_MAX_SEC
    log_filters: tuple[LogFilter, ...] = field(default_factory=tuple)
    killswitch_path: Path = KILLSWITCH_PATH_DEFAULT
    routine_name: str = ROUTINE_NAME
    config_source: str = "defaults"


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in ("1", "true", "yes", "on", "y"):
        return True
    if text in ("0", "false", "no", "off", "n", ""):
        return False
    return default


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_addresses(raw: Any) -> tuple[str, ...]:
    if not raw:
        return ()
    if isinstance(raw, str):
        items = [raw]
    else:
        items = list(raw)
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = str(item).strip().lower()
        if not text.startswith("0x") or len(text) != 42:
            continue
        if text in seen:
            continue
        seen.add(text)
        out.append(text)
    return tuple(out)


def _parse_log_filter_list(raw: Any) -> tuple[LogFilter, ...]:
    if not raw:
        return ()
    if isinstance(raw, str):
        # Allow JSON-encoded env var: SAPPHIRE_MEGAETH_LOG_FILTERS='[{...}]'
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("megaeth_ingest: SAPPHIRE_MEGAETH_LOG_FILTERS is not JSON; ignoring")
            return ()
    if isinstance(raw, dict):
        raw = [raw]
    out: list[LogFilter] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        addresses = _normalize_addresses(entry.get("addresses") or entry.get("address"))
        if not addresses:
            continue
        topics_raw = entry.get("topics") or ()
        topics = tuple(topics_raw) if isinstance(topics_raw, list | tuple) else ()
        out.append(LogFilter(addresses=addresses, topics=topics))
    return tuple(out)


def _read_yaml(path: Path) -> dict[str, Any]:
    if yaml is None or not path.exists():
        return {}
    try:
        text = path.read_text()
    except OSError as exc:
        logger.warning("megaeth_ingest: cannot read %s: %s", path, exc)
        return {}
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        logger.warning("megaeth_ingest: bad YAML at %s: %s", path, exc)
        return {}
    return data if isinstance(data, dict) else {}


def load_config(
    *,
    env: dict[str, str] | None = None,
    config_path: Path | None = None,
) -> IngestConfig:
    """Resolve config from env + YAML.

    Args:
        env: Override the environment (defaults to ``os.environ``).
        config_path: Path to YAML config (defaults to ``config/megaeth.yaml``).

    Returns:
        A frozen ``IngestConfig``. Always returns — never raises on missing
        config files.
    """
    values = os.environ if env is None else env
    yaml_path = config_path if config_path is not None else CONFIG_FILE_DEFAULT
    yaml_data = _read_yaml(yaml_path)

    def _pick(env_key: str, yaml_key: str, default: Any) -> Any:
        env_val = values.get(env_key)
        if env_val is not None and env_val != "":
            return env_val
        if yaml_key in yaml_data:
            return yaml_data[yaml_key]
        return default

    wss_url = str(_pick("SAPPHIRE_MEGAETH_WSS", "wss_url", DEFAULT_WSS)).strip()
    chain_id = _coerce_int(
        _pick("SAPPHIRE_MEGAETH_CHAIN_ID", "chain_id", DEFAULT_CHAIN_ID), DEFAULT_CHAIN_ID
    )
    health_port = _coerce_int(
        _pick("SAPPHIRE_MEGAETH_HEALTH_PORT", "health_port", DEFAULT_HEALTH_PORT),
        DEFAULT_HEALTH_PORT,
    )
    signal_logger_url = str(
        _pick("SAPPHIRE_MEGAETH_SIGNAL_LOGGER_URL", "signal_logger_url", DEFAULT_SIGNAL_LOGGER_URL)
    ).strip()
    webhook_secret = str(_pick("WEBHOOK_SECRET", "webhook_secret", "")).strip()
    forwarding_enabled = _coerce_bool(
        _pick("SAPPHIRE_MEGAETH_INGEST_ENABLED", "forwarding_enabled", False),
        default=False,
    )
    queue_max = _coerce_int(
        _pick("SAPPHIRE_MEGAETH_QUEUE_MAX", "queue_max", DEFAULT_QUEUE_MAX), DEFAULT_QUEUE_MAX
    )
    reconnect_backoff_sec = _coerce_float(
        _pick(
            "SAPPHIRE_MEGAETH_RECONNECT_BACKOFF",
            "reconnect_backoff_sec",
            DEFAULT_RECONNECT_BACKOFF_SEC,
        ),
        DEFAULT_RECONNECT_BACKOFF_SEC,
    )
    reconnect_max_sec = _coerce_float(
        _pick("SAPPHIRE_MEGAETH_RECONNECT_MAX", "reconnect_max_sec", DEFAULT_RECONNECT_MAX_SEC),
        DEFAULT_RECONNECT_MAX_SEC,
    )
    log_filters_raw = (
        values.get("SAPPHIRE_MEGAETH_LOG_FILTERS")
        if values.get("SAPPHIRE_MEGAETH_LOG_FILTERS")
        else yaml_data.get("log_filters")
    )
    log_filters = _parse_log_filter_list(log_filters_raw)

    killswitch_override = values.get("SAPPHIRE_MEGAETH_KILLSWITCH")
    if killswitch_override:
        killswitch_path = Path(killswitch_override).expanduser()
    elif "killswitch_path" in yaml_data:
        killswitch_path = Path(str(yaml_data["killswitch_path"])).expanduser()
    else:
        killswitch_path = KILLSWITCH_PATH_DEFAULT

    config_source_parts: list[str] = []
    if yaml_data:
        config_source_parts.append(f"yaml:{yaml_path}")
    config_source_parts.append("env")
    config_source = "+".join(config_source_parts)

    return IngestConfig(
        wss_url=wss_url,
        chain_id=chain_id,
        health_port=health_port,
        signal_logger_url=signal_logger_url,
        webhook_secret=webhook_secret,
        forwarding_enabled=forwarding_enabled,
        queue_max=max(16, queue_max),
        reconnect_backoff_sec=max(0.1, reconnect_backoff_sec),
        reconnect_max_sec=max(reconnect_backoff_sec, reconnect_max_sec),
        log_filters=log_filters,
        killswitch_path=killswitch_path,
        routine_name=ROUTINE_NAME,
        config_source=config_source,
    )


def killswitch_active(path: Path) -> bool:
    """Return True if the killswitch file exists.

    Cheap stat — safe to call on every loop iteration.
    """
    try:
        return path.exists()
    except OSError:
        return False
