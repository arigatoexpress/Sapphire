#!/usr/bin/env python3
"""Sapphire Signal Correlator — cross-source signal fusion plugin tool.

Stdin-JSON tool that drives the Signal Correlation Engine
(:mod:`lib.correlator`). Mirrors the shape of ``gemini_ooda.py`` and
the other internal tools: deterministic, dry-run-default, no live
network, hard caps borrowed straight from the engine.

Actions
-------

- ``correlate-once``  — fuse one or more ``(symbol, timeframe)`` pairs
  through the engine and return the unified ``CorrelatedSignal`` dicts.
  Honors caps: ``MAX_SOURCES_PER_CORRELATION``,
  ``MAX_CORRELATIONS_PER_HOUR``, ``FRESHNESS_HARD_LIMIT_SECONDS``.
- ``latest``           — read the most recent correlated-signals JSONL
  for ``today`` (or ``--date``) and return the rows.
- ``status``           — per-tool counters + cache stats; never reads
  source streams.
- ``weights``          — surface the resolved scoring weights and
  config path. Useful when tuning ``~/.sapphire/correlator_weights.yaml``.

Input (stdin JSON)
------------------

::

    {
      "action": "correlate-once",
      "pairs": [["BTC", "1h"], ["ETH", "1h"]],
      "live_bus": false
    }

Safety
------

- Read-only signal consumer. Never writes back to source streams.
- ``live_bus`` is ignored unless ``SAPPHIRE_CORRELATOR_LIVE_BUS=1`` is
  also set in the env (defence-in-depth).
- Per-hour rate limiting honors ``MAX_CORRELATIONS_PER_HOUR``; once
  hit, returns a soft "rate_limited" outcome instead of dropping.
- Counters persist at ``~/.cache/sapphire/signal_correlator/counters.json``.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _load_repo_lib_module(qualname: str, relpath: str):
    """Load a Sapphire ``lib.*`` module by file path.

    Plugin tests put ``plugins/claw-sapphire/lib/`` (a regular package
    with its own ``__init__.py``) on ``sys.path``, which shadows the
    repo-root ``lib/`` namespace. Loading by file path and registering
    the result in ``sys.modules[qualname]`` lets the rest of the code
    use ``from lib.X import Y`` regardless of the shadow.
    """
    import importlib.util
    import types as _types

    if qualname in sys.modules:
        existing = sys.modules[qualname]
        existing_file = getattr(existing, "__file__", "") or ""
        if str(REPO_ROOT) in existing_file:
            return existing

    target = REPO_ROOT / relpath
    spec = importlib.util.spec_from_file_location(qualname, target)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot resolve Sapphire module {qualname} at {target}")

    # Materialize parent packages so dotted lookups resolve through
    # ``sys.modules`` rather than the path-finder (where the plugin-local
    # ``lib`` package wins).
    parts = qualname.split(".")
    for i in range(1, len(parts)):
        parent = ".".join(parts[:i])
        if parent not in sys.modules or not hasattr(sys.modules[parent], "__path__"):
            mod = _types.ModuleType(parent)
            mod.__path__ = [str(REPO_ROOT / Path(*parts[:i]))]  # type: ignore[attr-defined]
            sys.modules[parent] = mod

    module = importlib.util.module_from_spec(spec)
    sys.modules[qualname] = module
    spec.loader.exec_module(module)
    # Wire the loaded module onto its parent so ``parent.child`` access works.
    if len(parts) > 1:
        parent_mod = sys.modules[".".join(parts[:-1])]
        setattr(parent_mod, parts[-1], module)
    return module


# Pre-load the entire correlator library by file path so the package-level
# ``from lib.correlator import (...)`` resolves correctly even when the
# plugin-local ``lib`` package shadows the repo namespace.
_load_repo_lib_module("lib.correlator.scoring", "lib/correlator/scoring.py")
_load_repo_lib_module("lib.correlator.sources", "lib/correlator/sources.py")
_load_repo_lib_module("lib.correlator.engine", "lib/correlator/engine.py")
_correlator_pkg = _load_repo_lib_module("lib.correlator", "lib/correlator/__init__.py")

EDGE_SCORE_BOUND = _correlator_pkg.EDGE_SCORE_BOUND
FRESHNESS_HARD_LIMIT_SECONDS = _correlator_pkg.FRESHNESS_HARD_LIMIT_SECONDS
MAX_CORRELATIONS_PER_HOUR = _correlator_pkg.MAX_CORRELATIONS_PER_HOUR
MAX_SOURCES_PER_CORRELATION = _correlator_pkg.MAX_SOURCES_PER_CORRELATION
CorrelatorConfig = _correlator_pkg.CorrelatorConfig
build_default_sources = _correlator_pkg.build_default_sources
correlate_universe = _correlator_pkg.correlate_universe
load_weights = _correlator_pkg.load_weights
UniversePair = sys.modules["lib.correlator.engine"].UniversePair

log = logging.getLogger(__name__)

CACHE_DIR = Path.home() / ".cache" / "sapphire" / "signal_correlator"
COUNTER_PATH = CACHE_DIR / "counters.json"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "data" / "correlated_signals"

DEFAULT_PAIRS: tuple[tuple[str, str], ...] = (
    ("BTC", "1h"),
    ("ETH", "1h"),
    ("SOL", "1h"),
)
MAX_PAIRS_PER_CALL = 32

GENERATOR = "plugins.claw_sapphire.signal_correlator"
VERSION = "0.1.0"


# ---------------------------------------------------------------------------
# Counter helpers
# ---------------------------------------------------------------------------


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _load_counters() -> dict[str, Any]:
    if not COUNTER_PATH.exists():
        return {"calls": [], "lifetime_signals": 0}
    try:
        return json.loads(COUNTER_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"calls": [], "lifetime_signals": 0}


def _save_counters(counters: dict[str, Any]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    COUNTER_PATH.write_text(json.dumps(counters, indent=2, sort_keys=True), encoding="utf-8")


def _prune(counters: dict[str, Any]) -> dict[str, Any]:
    cutoff = time.time() - 3600
    counters["calls"] = [t for t in counters.get("calls", []) if t >= cutoff]
    return counters


def _check_rate(counters: dict[str, Any]) -> tuple[bool, str]:
    if len(counters.get("calls", [])) >= MAX_CORRELATIONS_PER_HOUR:
        return False, f"rate_limit: {MAX_CORRELATIONS_PER_HOUR}/hour exceeded"
    return True, "ok"


# ---------------------------------------------------------------------------
# Action helpers
# ---------------------------------------------------------------------------


def _coerce_pairs(raw: Any) -> list[tuple[str, str]]:
    """Validate a list of ``(symbol, timeframe)`` pairs from JSON."""
    if not raw:
        return list(DEFAULT_PAIRS)
    if not isinstance(raw, list):
        raise ValueError("pairs must be a list of [symbol, timeframe] pairs")
    out: list[tuple[str, str]] = []
    for item in raw:
        if isinstance(item, list) and len(item) == 2:
            sym, tf = item
        elif isinstance(item, dict) and "symbol" in item and "timeframe" in item:
            sym, tf = item["symbol"], item["timeframe"]
        else:
            raise ValueError(f"invalid pair entry: {item!r}")
        sym_s = str(sym or "").strip().upper()
        tf_s = str(tf or "").strip().lower()
        if not sym_s or not tf_s:
            raise ValueError(f"empty symbol or timeframe in pair: {item!r}")
        out.append((sym_s, tf_s))
        if len(out) >= MAX_PAIRS_PER_CALL:
            break
    return out


def correlate_once_action(
    *,
    pairs: list[tuple[str, str]] | None = None,
    live_bus: bool = False,
    config: CorrelatorConfig | None = None,
    sources: list[Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Run the engine for a list of pairs and return the unified rows."""
    pairs = pairs or list(DEFAULT_PAIRS)
    config = config or CorrelatorConfig(weights=load_weights())
    sources = sources if sources is not None else build_default_sources()

    counters = _prune(_load_counters())
    allowed, reason = _check_rate(counters)
    metadata: dict[str, Any] = {
        "issued_at": (now or _now_utc()).isoformat(),
        "pairs_requested": len(pairs),
        "live_bus_requested": bool(live_bus),
        "live_bus_actual": False,
        "rate_limit_state": {
            "calls_last_hour": len(counters.get("calls", [])),
            "max_per_hour": MAX_CORRELATIONS_PER_HOUR,
        },
        "caps": {
            "max_sources_per_correlation": MAX_SOURCES_PER_CORRELATION,
            "max_correlations_per_hour": MAX_CORRELATIONS_PER_HOUR,
            "freshness_hard_limit_seconds": FRESHNESS_HARD_LIMIT_SECONDS,
            "edge_score_bound": list(EDGE_SCORE_BOUND),
        },
        "version": VERSION,
        "generator": GENERATOR,
    }
    if not allowed:
        return {
            "ok": False,
            "reason": reason,
            "signals": [],
            "metadata": metadata,
        }

    pair_objs = [UniversePair(symbol=s, timeframe=t) for s, t in pairs]
    signals = correlate_universe(pair_objs, sources=sources, config=config, now=now)

    counters.setdefault("calls", []).append(time.time())
    counters["lifetime_signals"] = counters.get("lifetime_signals", 0) + len(signals)
    _save_counters(counters)
    metadata["rate_limit_state"]["calls_last_hour"] = len(counters["calls"])

    # live_bus is only honoured if both the env flag AND request flag are set.
    bus_env = os.environ.get("SAPPHIRE_CORRELATOR_LIVE_BUS", "").strip() == "1"
    if live_bus and bus_env:
        try:
            from lib.core.event_bus import get_bus

            bus = get_bus(source="signal-correlator-tool")
            for sig in signals:
                bus.publish("signal.correlated", sig.to_dict(), source="signal-correlator-tool")
            metadata["live_bus_actual"] = True
        except Exception as exc:  # noqa: BLE001
            log.warning("event bus publish failed (%s) — continuing", exc)

    return {
        "ok": True,
        "signals": [s.to_dict() for s in signals],
        "metadata": metadata,
    }


def latest_action(*, date: str | None = None) -> dict[str, Any]:
    """Return the contents of ``data/correlated_signals/<date>/signals.jsonl``."""
    target_date = (date or _now_utc().strftime("%Y-%m-%d")).strip()
    path = DEFAULT_OUTPUT_ROOT / target_date / "signals.jsonl"
    if not path.exists():
        return {"ok": False, "date": target_date, "rows": [], "reason": "no signals file"}
    rows: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except OSError as exc:
        return {"ok": False, "date": target_date, "rows": [], "reason": str(exc)}
    return {"ok": True, "date": target_date, "rows": rows, "count": len(rows)}


def status_action() -> dict[str, Any]:
    counters = _prune(_load_counters())
    return {
        "cache_dir": str(CACHE_DIR),
        "calls_last_hour": len(counters.get("calls", [])),
        "max_per_hour": MAX_CORRELATIONS_PER_HOUR,
        "lifetime_signals": counters.get("lifetime_signals", 0),
        "live_bus_env": os.environ.get("SAPPHIRE_CORRELATOR_LIVE_BUS") == "1",
        "version": VERSION,
        "generator": GENERATOR,
    }


def weights_action(*, weights_path: Path | None = None) -> dict[str, Any]:
    weights = load_weights(weights_path)
    from lib.correlator.scoring import DEFAULT_WEIGHTS_PATH

    target = weights_path or DEFAULT_WEIGHTS_PATH
    return {
        "config_path": str(target),
        "config_exists": target.exists(),
        "source_weights": dict(weights.source_weights),
        "freshness_half_life_seconds": float(weights.freshness_half_life_seconds),
        "agreement_bonus_per_extra": float(weights.agreement_bonus_per_extra),
        "max_agreement_multiplier": float(weights.max_agreement_multiplier),
        "contradict_penalty": float(weights.contradict_penalty),
    }


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


def handle(payload: dict[str, Any]) -> dict[str, Any]:
    action = (payload.get("action") or "correlate-once").strip().lower()
    if action == "status":
        return status_action()
    if action == "weights":
        return weights_action()
    if action == "latest":
        return latest_action(date=payload.get("date"))
    if action == "correlate-once":
        try:
            pairs = _coerce_pairs(payload.get("pairs"))
        except ValueError as exc:
            return {"error": str(exc)}
        return correlate_once_action(
            pairs=pairs,
            live_bus=bool(payload.get("live_bus")),
        )
    return {
        "error": f"unknown action '{action}'",
        "valid_actions": ["correlate-once", "latest", "status", "weights"],
    }


def main(stream_in: Any = sys.stdin, stream_out: Any = sys.stdout) -> int:
    raw = stream_in.read() or "{}"
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        json.dump({"error": f"invalid JSON: {exc}"}, stream_out)
        return 2
    if not isinstance(payload, dict):
        json.dump({"error": "stdin payload must be a JSON object"}, stream_out)
        return 2
    response = handle(payload)
    json.dump(response, stream_out, indent=2, sort_keys=True, default=str)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
