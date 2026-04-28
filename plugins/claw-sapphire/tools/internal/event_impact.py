#!/usr/bin/env python3
"""Sapphire event-impact lookup plugin tool.

Actions:
- ``lookup``: return an expected reaction from a built model.
- ``corpus``: summarize the curated historical event corpus.
- ``rebuild``: dry-run by default; requires ``SAPPHIRE_EVENT_IMPACT_REBUILD=1``.
- ``accuracy-audit``: compare post-build realized outcomes when supplied.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

def _load_repo_lib_module(qualname: str, relpath: str):
    """Load Sapphire ``lib.*`` modules despite plugin-local ``lib`` shadowing."""
    import importlib.util
    import types as _types

    existing = sys.modules.get(qualname)
    existing_file = getattr(existing, "__file__", "") if existing else ""
    if existing is not None and str(REPO_ROOT) in existing_file:
        return existing

    target = REPO_ROOT / relpath
    spec = importlib.util.spec_from_file_location(qualname, target)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot resolve Sapphire module {qualname} at {target}")

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
    if len(parts) > 1:
        setattr(sys.modules[".".join(parts[:-1])], parts[-1], module)
    return module


_load_repo_lib_module("lib.event_impact.event_corpus", "lib/event_impact/event_corpus.py")
_load_repo_lib_module("lib.event_impact.impact_modeler", "lib/event_impact/impact_modeler.py")
_load_repo_lib_module("lib.event_impact.lookup", "lib/event_impact/lookup.py")
_load_repo_lib_module("lib.event_impact.audit", "lib/event_impact/audit.py")
_event_impact_pkg = _load_repo_lib_module("lib.event_impact", "lib/event_impact/__init__.py")

DEFAULT_CORPUS_PATH = _event_impact_pkg.DEFAULT_CORPUS_PATH
MacroEvent = _event_impact_pkg.MacroEvent
load_events = _event_impact_pkg.load_events
lookup = _event_impact_pkg.lookup
events_by_category = sys.modules["lib.event_impact.event_corpus"].events_by_category
ImpactModel = sys.modules["lib.event_impact.impact_modeler"].ImpactModel
HistoricalEvent = sys.modules["lib.event_impact.event_corpus"].HistoricalEvent
audit_mod = sys.modules["lib.event_impact.audit"]
audit_expected_reactions = audit_mod.audit_expected_reactions
audit_from_files = audit_mod.audit_from_files
load_bars_by_asset = audit_mod.load_bars_by_asset
load_audit_model = audit_mod.load_model

CACHE_DIR = Path.home() / ".cache" / "sapphire" / "event_impact"
DEFAULT_MODEL_DIR = REPO_ROOT / "data" / "event_impact"
GENERATOR = "plugins.claw_sapphire.event_impact"
VERSION = "0.1.0"


def _latest_model_path(model_dir: Path = DEFAULT_MODEL_DIR) -> Path | None:
    paths = sorted(model_dir.glob("model_*.json"))
    return paths[-1] if paths else None


def _load_model(path: Path | None = None) -> ImpactModel:
    target = path or _latest_model_path()
    if target is None:
        raise FileNotFoundError("no event-impact model found; run rebuild first")
    return ImpactModel.from_dict(json.loads(target.read_text(encoding="utf-8")))


def corpus_action(path: Path = DEFAULT_CORPUS_PATH) -> dict[str, Any]:
    events = load_events(path)
    return {
        "ok": True,
        "version": VERSION,
        "count": len(events),
        "categories": events_by_category(events),
        "first_event": events[0].to_dict() if events else None,
        "last_event": events[-1].to_dict() if events else None,
        "corpus_path": str(path),
    }


def lookup_action(payload: dict[str, Any]) -> dict[str, Any]:
    event = MacroEvent.from_any(payload.get("event") or {})
    asset = str(payload.get("asset") or "BTC").upper()
    horizon = int(payload.get("horizon_hours") or 24)
    model_path = Path(payload["model_path"]) if payload.get("model_path") else None
    try:
        model = _load_model(model_path)
    except FileNotFoundError as exc:
        return {"ok": False, "error": str(exc), "action": "lookup"}
    reaction = lookup(event, asset, horizon, model=model)
    return {
        "ok": True,
        "reaction": reaction.to_dict(),
        "model_generated_at": model.generated_at,
        "version": VERSION,
    }


def rebuild_action(payload: dict[str, Any]) -> dict[str, Any]:
    if os.environ.get("SAPPHIRE_EVENT_IMPACT_REBUILD") != "1":
        return {
            "ok": False,
            "mode": "dry-run",
            "reason": "set SAPPHIRE_EVENT_IMPACT_REBUILD=1 to fetch OHLCV and rebuild",
            "cache_dir": str(CACHE_DIR),
        }
    from services.event_impact.build import build

    output_dir = Path(payload.get("output_dir") or DEFAULT_MODEL_DIR)
    assets = tuple(str(a).upper() for a in payload.get("assets", ["BTC", "ETH", "SOL", "SPY", "GLD"]))
    path = build(output_dir=output_dir, assets=assets)
    return {"ok": True, "model_path": str(path), "mode": "rebuild", "version": VERSION}


def _legacy_observation_accuracy_audit(payload: dict[str, Any]) -> dict[str, Any]:
    """Compare predicted sign to precomputed realized outcomes."""
    observations = payload.get("observations") or []
    if not isinstance(observations, list):
        return {"ok": False, "error": "observations must be a list"}
    scored = 0
    correct = 0
    rows: list[dict[str, Any]] = []
    for obs in observations:
        if not isinstance(obs, dict):
            continue
        expected = obs.get("expected") or {}
        actual = float(obs.get("actual_return_pct") or 0.0)
        pred = float(expected.get("direction_consensus") or 0.0)
        if pred == 0 or actual == 0:
            rows.append({"scored": False, "actual_return_pct": actual, "predicted_consensus": pred})
            continue
        scored += 1
        ok = (pred > 0 and actual > 0) or (pred < 0 and actual < 0)
        correct += int(ok)
        rows.append({"scored": True, "correct": ok, "actual_return_pct": actual, "predicted_consensus": pred})
    return {
        "ok": True,
        "scored": scored,
        "correct": correct,
        "accuracy": round(correct / scored, 6) if scored else None,
        "rows": rows,
        "issued_at": datetime.now(UTC).isoformat(),
    }


def _coerce_horizons(raw: Any) -> tuple[int, ...]:
    if raw is None:
        return (1, 6, 24, 168)
    if not isinstance(raw, list):
        raise ValueError("horizons_hours must be a list of integers")
    horizons = tuple(int(v) for v in raw)
    if not horizons:
        raise ValueError("horizons_hours must not be empty")
    return horizons


def _coerce_assets(raw: Any) -> tuple[str, ...] | None:
    if raw is None:
        return None
    if not isinstance(raw, list):
        raise ValueError("assets must be a list of symbols")
    return tuple(str(asset).upper() for asset in raw if str(asset).strip())


def _events_from_payload(payload: dict[str, Any]) -> list[Any]:
    if payload.get("events_path"):
        return load_events(Path(payload["events_path"]))
    raw_events = payload.get("events") or []
    if not isinstance(raw_events, list):
        raise ValueError("events must be a list")
    return [HistoricalEvent.from_dict(row) for row in raw_events if isinstance(row, dict)]


def _bars_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("bars_path"):
        return load_bars_by_asset(Path(payload["bars_path"]))
    raw = payload.get("bars_by_asset") or {}
    if not isinstance(raw, dict):
        raise ValueError("bars_by_asset must be an asset mapping")
    return raw


def _model_from_payload(payload: dict[str, Any]) -> Any:
    if payload.get("model_path"):
        return load_audit_model(Path(payload["model_path"]))
    if isinstance(payload.get("model"), dict):
        return payload["model"]
    return _load_model(None)


def accuracy_audit_action(payload: dict[str, Any]) -> dict[str, Any]:
    """Audit expected profiles against supplied historical events and bars.

    Preferred offline payload:

    ``{"model_path": "...", "events_path": "...", "bars_path": "...", "horizons_hours": [24]}``

    For backward compatibility, ``{"observations": [...]}`` still runs the
    original precomputed-observation scorer.
    """
    if "observations" in payload and not any(
        payload.get(key) for key in ("events_path", "events", "bars_path", "bars_by_asset", "model_path", "model")
    ):
        return _legacy_observation_accuracy_audit(payload)
    try:
        report = audit_expected_reactions(
            _events_from_payload(payload),
            _bars_from_payload(payload),
            _model_from_payload(payload),
            horizons_hours=_coerce_horizons(payload.get("horizons_hours")),
            assets=_coerce_assets(payload.get("assets")),
        )
    except (FileNotFoundError, ValueError, KeyError, TypeError) as exc:
        return {"ok": False, "error": str(exc), "action": "accuracy-audit"}
    return {
        "ok": True,
        "version": VERSION,
        "mode": "offline-fixture-audit",
        "audit": report.to_dict(),
        "issued_at": datetime.now(UTC).isoformat(),
    }


def handle(payload: dict[str, Any]) -> dict[str, Any]:
    action = str(payload.get("action") or "lookup").strip().lower()
    if action == "corpus":
        return corpus_action()
    if action == "lookup":
        return lookup_action(payload)
    if action == "rebuild":
        return rebuild_action(payload)
    if action == "accuracy-audit":
        return accuracy_audit_action(payload)
    return {
        "error": f"unknown action '{action}'",
        "valid_actions": ["lookup", "corpus", "rebuild", "accuracy-audit"],
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
    json.dump(handle(payload), stream_out, indent=2, sort_keys=True, default=str)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
