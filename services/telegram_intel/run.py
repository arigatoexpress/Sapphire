#!/usr/bin/env python3
"""Run the Telegram channel intel reader.

Live collection is fail-closed. The daemon and real backend construction require:

* ``SAPPHIRE_TELEGRAM_INTEL_LIVE=1``
* ``~/.sapphire/telegram_intel.session`` exists
* a config file with at least one enabled channel
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from services.telegram_intel.backends import (
    DEFAULT_SESSION_PATH,
    BackendError,
    ReaderBackend,
    build_backend,
)
from services.telegram_intel.classifier import LocalClassifier, available_models
from services.telegram_intel.config import ConfigError, TelegramIntelConfig, load_config
from services.telegram_intel.models import (
    MAX_CLASSIFICATIONS_PER_HOUR,
    MAX_MESSAGES_PER_HOUR,
    ChannelConfig,
    ClassificationResult,
    PullStats,
)
from services.telegram_intel.quality_filter import quality_filter
from services.telegram_intel.rate_limits import DEFAULT_COUNTER_PATH, HourlyRateLimiter
from services.telegram_intel.sink import TelegramIntelSink, build_record

BackendFactory = Callable[[str], ReaderBackend]


@dataclass(frozen=True)
class LiveGateResult:
    allowed: bool
    reasons: tuple[str, ...]
    live_env: bool
    session_path: str
    config_path: str
    enabled_channels: int

    def to_dict(self) -> dict[str, object]:
        return {
            "allowed": self.allowed,
            "reasons": list(self.reasons),
            "live_env": self.live_env,
            "session_path": self.session_path,
            "config_path": self.config_path,
            "enabled_channels": self.enabled_channels,
        }


def evaluate_live_gate(
    *,
    config_path: str | Path | None = None,
    session_path: str | Path = DEFAULT_SESSION_PATH,
) -> LiveGateResult:
    reasons: list[str] = []
    live_env = os.environ.get("SAPPHIRE_TELEGRAM_INTEL_LIVE", "").strip() == "1"
    if not live_env:
        reasons.append("SAPPHIRE_TELEGRAM_INTEL_LIVE != 1")
    session = Path(session_path).expanduser()
    if not session.exists():
        reasons.append(f"session missing: {session}")
    enabled_channels = 0
    config_display = str(config_path or "")
    try:
        cfg = load_config(config_path)
        enabled_channels = len(cfg.enabled_channels)
        config_display = str(Path(config_path).expanduser() if config_path else Path("infra/telegram_channels.yaml"))
        if enabled_channels < 1:
            reasons.append("no enabled channels")
    except ConfigError as exc:
        reasons.append(str(exc))
    return LiveGateResult(
        allowed=not reasons,
        reasons=tuple(reasons),
        live_env=live_env,
        session_path=str(session),
        config_path=config_display,
        enabled_channels=enabled_channels,
    )


def _backend_for(factory: BackendFactory, cache: dict[str, ReaderBackend], name: str) -> ReaderBackend:
    if name not in cache:
        cache[name] = factory(name)
    return cache[name]


def pull_once(
    *,
    config_path: str | Path | None = None,
    data_dir: str | Path | None = None,
    counter_path: str | Path = DEFAULT_COUNTER_PATH,
    backend_factory: BackendFactory | None = None,
    classifier: LocalClassifier | None = None,
    source_paths: tuple[str | Path, ...] = (),
    require_live_gate: bool = True,
) -> dict[str, object]:
    try:
        cfg = load_config(config_path)
    except ConfigError as exc:
        return {"ok": False, "error": str(exc)}

    if backend_factory is None and require_live_gate:
        gate = evaluate_live_gate(config_path=config_path)
        if not gate.allowed:
            return {"ok": False, "error": "live gate refused", "gate": gate.to_dict()}

    enabled = cfg.enabled_channels
    limiter = HourlyRateLimiter(counter_path)
    message_state = limiter.check("messages", MAX_MESSAGES_PER_HOUR, amount=1)
    if not message_state.allowed:
        return {
            "ok": False,
            "error": "message rate limit exhausted",
            "rate_limits": {"messages": message_state.to_dict()},
        }

    sink = TelegramIntelSink(data_dir or cfg.data_dir)
    factory = backend_factory or build_backend
    backend_cache: dict[str, ReaderBackend] = {}
    classifier = classifier or LocalClassifier(
        enabled=cfg.classifier_enabled,
        model=cfg.classifier_model,
    )
    records: list[dict[str, object]] = []
    errors: list[str] = []
    raw_count = 0
    low_quality = 0
    classifier_calls = 0

    for channel in enabled:
        remaining = limiter.check("messages", MAX_MESSAGES_PER_HOUR).remaining
        if remaining < 1:
            break
        limit = min(cfg.pull_limit_per_channel, remaining)
        try:
            backend = _backend_for(factory, backend_cache, channel.backend)
            messages = backend.pull_channel(channel, limit=limit)
        except (BackendError, OSError, ValueError) as exc:
            errors.append(f"{channel.id}:{exc.__class__.__name__}")
            continue
        raw_count += len(messages)
        limiter.record("messages", len(messages))
        for message in messages:
            quality = quality_filter(
                message.text,
                channel_id=channel.id,
                min_score=channel.min_quality,
            )
            if not quality.keep:
                low_quality += 1
                continue
            classification = _classify_with_cap(
                classifier,
                quality.sanitized_text,
                channel=channel,
                limiter=limiter,
            )
            if classification.source == "local-inference-proxy":
                classifier_calls += 1
                limiter.record("classifications", 1)
            records.append(
                build_record(
                    message,
                    channel,
                    quality,
                    classification,
                    source_paths=source_paths,
                )
            )

    write_result = sink.write_records(records)
    stats = PullStats(
        channels=len(enabled),
        raw_messages=raw_count,
        kept_messages=len(records),
        low_quality_messages=low_quality,
        written_messages=write_result.written,
        duplicate_messages=write_result.duplicates,
        classifier_calls=classifier_calls,
        errors=tuple(errors),
    )
    return {
        "ok": not errors,
        "stats": stats.to_dict(),
        "sink": write_result.to_dict(),
        "rate_limits": {
            "messages": limiter.check("messages", MAX_MESSAGES_PER_HOUR).to_dict(),
            "classifications": limiter.check(
                "classifications", MAX_CLASSIFICATIONS_PER_HOUR
            ).to_dict(),
        },
    }


def _classify_with_cap(
    classifier: LocalClassifier,
    text: str,
    *,
    channel: ChannelConfig,
    limiter: HourlyRateLimiter,
) -> ClassificationResult:
    if not classifier.enabled:
        return classifier.classify(text, channel_id=channel.id)
    state = limiter.check("classifications", MAX_CLASSIFICATIONS_PER_HOUR)
    if not state.allowed:
        return ClassificationResult.fallback(reason="classification rate limit exhausted")
    return classifier.classify(text, channel_id=channel.id)


def status(
    *,
    config_path: str | Path | None = None,
    data_dir: str | Path | None = None,
    counter_path: str | Path = DEFAULT_COUNTER_PATH,
) -> dict[str, object]:
    gate = evaluate_live_gate(config_path=config_path)
    cfg: TelegramIntelConfig | None = None
    config_error = None
    try:
        cfg = load_config(config_path)
    except ConfigError as exc:
        config_error = str(exc)
    limiter = HourlyRateLimiter(counter_path)
    sink_dir = data_dir or (cfg.data_dir if cfg else None)
    recent_count = TelegramIntelSink(sink_dir).count_recent(limit=200) if sink_dir else 0
    return {
        "ok": True,
        "service": "telegram_intel",
        "gate": gate.to_dict(),
        "config_error": config_error,
        "enabled_channels": len(cfg.enabled_channels) if cfg else 0,
        "classifier": {
            "enabled": bool(cfg.classifier_enabled) if cfg else False,
            "model": cfg.classifier_model if cfg else "balanced",
        },
        "models": available_models(),
        "recent_records": recent_count,
        "rate_limits": {
            "messages": limiter.check("messages", MAX_MESSAGES_PER_HOUR).to_dict(),
            "classifications": limiter.check(
                "classifications", MAX_CLASSIFICATIONS_PER_HOUR
            ).to_dict(),
        },
    }


def daemon(
    *,
    config_path: str | Path | None = None,
    data_dir: str | Path | None = None,
    counter_path: str | Path = DEFAULT_COUNTER_PATH,
) -> int:
    gate = evaluate_live_gate(config_path=config_path)
    if not gate.allowed:
        print(json.dumps({"ok": False, "error": "live gate refused", "gate": gate.to_dict()}))
        return 2
    cfg = load_config(config_path)
    while True:
        print(
            json.dumps(
                pull_once(
                    config_path=config_path,
                    data_dir=data_dir,
                    counter_path=counter_path,
                    source_paths=(Path(config_path) if config_path else Path("infra/telegram_channels.yaml"),),
                ),
                sort_keys=True,
            ),
            flush=True,
        )
        time.sleep(cfg.poll_interval_seconds)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("status", "pull-once", "daemon", "models"))
    parser.add_argument("--config", type=Path)
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--counter-path", type=Path, default=DEFAULT_COUNTER_PATH)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.action == "status":
        print(
            json.dumps(
                status(
                    config_path=args.config,
                    data_dir=args.data_dir,
                    counter_path=args.counter_path,
                ),
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if args.action == "models":
        print(json.dumps(available_models(), indent=2, sort_keys=True))
        return 0
    if args.action == "pull-once":
        result = pull_once(
            config_path=args.config,
            data_dir=args.data_dir,
            counter_path=args.counter_path,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result.get("ok") else 2
    return daemon(config_path=args.config, data_dir=args.data_dir, counter_path=args.counter_path)


if __name__ == "__main__":
    sys.exit(main())
