#!/usr/bin/env python3
"""Sapphire inference-mesh telemetry plugin tool.

Actions:
- ``report``: aggregate ``calls.jsonl`` (or synthetic fixture) into a per-tier report.
- ``recommendations``: surface honest tier-switch + health recommendations.
- ``cost-model``: emit the active CostModel + Moonshot pricing citation.
- ``status``: lightweight health check (does the cache file exist? schema version?).

All output is JSON on stdout. Read-only — never writes anywhere except a
provenance-stamped artifact under ``data/inference_telemetry/`` when the
caller passes ``output_path`` to ``report``.
"""

from __future__ import annotations

import json
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


_load_repo_lib_module("lib.inference_telemetry", "lib/inference_telemetry/__init__.py")
_load_repo_lib_module(
    "lib.inference_telemetry.cost_model",
    "lib/inference_telemetry/cost_model.py",
)
_load_repo_lib_module(
    "lib.inference_telemetry.aggregator",
    "lib/inference_telemetry/aggregator.py",
)
_load_repo_lib_module(
    "lib.inference_telemetry.recommender",
    "lib/inference_telemetry/recommender.py",
)

aggregator = sys.modules["lib.inference_telemetry.aggregator"]
cost_model_module = sys.modules["lib.inference_telemetry.cost_model"]
recommender = sys.modules["lib.inference_telemetry.recommender"]
_telemetry_pkg = sys.modules["lib.inference_telemetry"]

VERSION = _telemetry_pkg.VERSION
GENERATOR = "plugins.claw_sapphire.inference_telemetry"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "data" / "inference_telemetry"


def _resolve_cost_model(payload: dict[str, Any]):
    """Resolve a CostModel from a payload-supplied override, or fall back to default.

    Payload shape:
        {
            "cost_model": {
                "t1_per_inference_usd": 0.0009,
                "t3_per_inference_usd": 0.0007,
                "kimi_input_usd_per_1k_tokens": 1.20,
                "kimi_output_usd_per_1k_tokens": 2.40
            }
        }
    """
    raw = payload.get("cost_model") or {}
    base = cost_model_module.DEFAULT_COST_MODEL
    if not raw:
        return base
    overrides = {}
    if "t1_per_inference_usd" in raw:
        overrides["t1_per_inference_usd"] = float(raw["t1_per_inference_usd"])
    if "t2_per_inference_usd" in raw:
        overrides["t2_per_inference_usd"] = float(raw["t2_per_inference_usd"])
    if "t3_per_inference_usd" in raw:
        overrides["t3_per_inference_usd"] = float(raw["t3_per_inference_usd"])
    if overrides:
        base = cost_model_module.with_overrides(base=base, **overrides)
    if "kimi_input_usd_per_1k_tokens" in raw or "kimi_output_usd_per_1k_tokens" in raw:
        base = cost_model_module.with_kimi_rates(
            base=base,
            input_usd_per_1k_tokens=float(raw.get("kimi_input_usd_per_1k_tokens", 0.0)),
            output_usd_per_1k_tokens=float(raw.get("kimi_output_usd_per_1k_tokens", 0.0)),
        )
    return base


def _resolve_report(payload: dict[str, Any]):
    """Aggregate from a payload-specified path or fall back to default+synthetic."""
    cm = _resolve_cost_model(payload)
    fixture_path = payload.get("path")
    if fixture_path:
        return aggregator.aggregate(Path(str(fixture_path)), cost_model=cm), cm
    if aggregator.DEFAULT_CALLS_PATH.exists():
        return aggregator.aggregate(cost_model=cm), cm
    rep = aggregator.synthetic_fixture_report(cost_model=cm)
    return rep, cm


def _stamp_with_provenance(payload: dict[str, Any], *, source_path: str) -> dict[str, Any]:
    """Wrap ``payload`` in a provenance envelope (best effort — never fails the call)."""
    try:
        from lib.core.provenance import stamp

        return stamp(
            payload,
            generator=GENERATOR,
            source_paths=(source_path,) if source_path else (),
            metadata={"version": VERSION},
        )
    except Exception:
        # Provenance is a best-effort wrap. If unavailable, return payload as-is.
        return payload


def report_action(payload: dict[str, Any]) -> dict[str, Any]:
    rep, cm = _resolve_report(payload)
    body = rep.to_dict()
    body["projected_monthly_cost_usd"] = round(aggregator.project_monthly_cost(rep), 6)
    body["projected_monthly_calls"] = round(aggregator.project_monthly_calls(rep), 3)
    body["cost_model"] = cm.to_dict()
    body["citations"] = [
        f"Moonshot pricing: {cm.moonshot_pricing_url} (retrieved {cm.moonshot_pricing_retrieved})"
    ]
    body["ok"] = True
    body["action"] = "report"
    body["issued_at"] = datetime.now(UTC).isoformat()

    output_path = payload.get("output_path")
    if output_path:
        target = Path(str(output_path))
        target.parent.mkdir(parents=True, exist_ok=True)
        stamped = _stamp_with_provenance(body, source_path=rep.source_path or "")
        target.write_text(
            json.dumps(stamped, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
        body["written_to"] = str(target)
    return body


def recommendations_action(payload: dict[str, Any]) -> dict[str, Any]:
    rep, cm = _resolve_report(payload)
    bundle = recommender.recommend(rep, cost_model=cm)
    body = bundle.to_dict()
    body["top"] = [r.to_dict() for r in recommender.top_n(bundle, n=int(payload.get("top_n", 3)))]
    body["ok"] = True
    body["action"] = "recommendations"
    body["issued_at"] = datetime.now(UTC).isoformat()
    body["citations"] = [
        f"Moonshot pricing: {cm.moonshot_pricing_url} (retrieved {cm.moonshot_pricing_retrieved})"
    ]
    return body


def cost_model_action(payload: dict[str, Any]) -> dict[str, Any]:
    cm = _resolve_cost_model(payload)
    return {
        "ok": True,
        "action": "cost-model",
        "version": VERSION,
        "cost_model": cm.to_dict(),
        "issued_at": datetime.now(UTC).isoformat(),
        "citations": [
            f"Moonshot pricing: {cm.moonshot_pricing_url} (retrieved {cm.moonshot_pricing_retrieved})"
        ],
    }


def status_action(payload: dict[str, Any]) -> dict[str, Any]:
    target = Path(str(payload.get("path") or aggregator.DEFAULT_CALLS_PATH))
    return {
        "ok": True,
        "action": "status",
        "version": VERSION,
        "schema_version": _telemetry_pkg.SCHEMA_VERSION,
        "calls_path": str(target),
        "calls_path_exists": target.exists(),
        "issued_at": datetime.now(UTC).isoformat(),
    }


def handle(payload: dict[str, Any]) -> dict[str, Any]:
    action = str(payload.get("action") or "report").strip().lower()
    if action == "report":
        return report_action(payload)
    if action in ("recommendations", "recommend", "recs"):
        return recommendations_action(payload)
    if action in ("cost-model", "cost_model"):
        return cost_model_action(payload)
    if action == "status":
        return status_action(payload)
    return {
        "ok": False,
        "error": f"unknown action '{action}'",
        "valid_actions": ["report", "recommendations", "cost-model", "status"],
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
