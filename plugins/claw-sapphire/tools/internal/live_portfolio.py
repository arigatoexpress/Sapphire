#!/usr/bin/env python3
"""Live capital ledger tool.

This tool is stdin-JSON only and broker-read-only. It never contacts Robinhood
or any other venue. Operator-seeded fills must include provenance, and all
account identifiers are hashed before persistence.
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


def _load_repo_lib_module(qualname: str, relpath: str):  # pragma: no cover - import shim
    """Load a Sapphire ``lib.*`` module from the repo root, bypassing the
    ``plugins/claw-sapphire/lib/`` namespace shadow when the plugin tests
    put that on sys.path. Mirrors the pattern in `intel_search.py`."""
    import importlib.util

    if qualname in sys.modules:
        existing = sys.modules[qualname]
        existing_file = getattr(existing, "__file__", "") or ""
        if str(REPO_ROOT) in existing_file:
            return existing
    target = REPO_ROOT / relpath
    spec = importlib.util.spec_from_file_location(qualname, target)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot resolve Sapphire module {qualname} at {target}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[qualname] = module
    spec.loader.exec_module(module)
    return module


import types  # noqa: E402

if "lib" not in sys.modules or (REPO_ROOT / "lib") not in [
    Path(p) for p in (getattr(sys.modules.get("lib"), "__path__", None) or [])
]:
    sys.modules["lib"] = types.ModuleType("lib")
    sys.modules["lib"].__path__ = [str(REPO_ROOT / "lib")]  # type: ignore[attr-defined]
if "lib.live_portfolio" not in sys.modules:
    sys.modules["lib.live_portfolio"] = types.ModuleType("lib.live_portfolio")
    sys.modules["lib.live_portfolio"].__path__ = [  # type: ignore[attr-defined]
        str(REPO_ROOT / "lib" / "live_portfolio")
    ]

_LEDGER = _load_repo_lib_module("lib.live_portfolio.ledger", "lib/live_portfolio/ledger.py")
_RAMP = _load_repo_lib_module("lib.live_portfolio.ramp_gate", "lib/live_portfolio/ramp_gate.py")
_SEED = _load_repo_lib_module("lib.live_portfolio.seed", "lib/live_portfolio/seed.py")
_SORTINO = _load_repo_lib_module("lib.live_portfolio.sortino", "lib/live_portfolio/sortino.py")

DEFAULT_LEDGER_ROOT = _LEDGER.DEFAULT_LEDGER_ROOT
LiveLedger = _LEDGER.LiveLedger
hash_account = _LEDGER.hash_account
evaluate_ramp_gate = _RAMP.evaluate_ramp_gate
forecast_rung_completion = _RAMP.forecast_rung_completion
provenance_for_operator_fill = _SEED.provenance_for_operator_fill
seed_record = _SEED.seed_record
last_n_sortino = _SORTINO.last_n_sortino
sortino_ratio = _SORTINO.sortino_ratio

VALID_ACTIONS = (
    "seed-trade",
    "ledger",
    "gate-status",
    "sortino",
    "forecast-rung-completion",
    "hash-account",
    "input-provenance",
    "status",
)


def _ledger(payload: dict[str, Any]) -> LiveLedger:
    return LiveLedger(payload.get("ledger_root") or DEFAULT_LEDGER_ROOT)


def _returns(payload: dict[str, Any]) -> list[Any]:
    values = payload.get("returns", [])
    if not isinstance(values, list):
        raise ValueError("returns must be a list")
    return values


def _parse_now(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)


def status_action(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    ledger = _ledger(payload)
    return {
        "ok": True,
        "version": "0.1.0",
        "ledger_root": str(ledger.root),
        "accounts": ledger.accounts(),
        "live_api_calls": 0,
        "broker_mutation": False,
        "valid_actions": list(VALID_ACTIONS),
    }


def handle(payload: dict[str, Any]) -> dict[str, Any]:
    action = str(payload.get("action") or "status").strip().lower().replace("_", "-")
    try:
        if action == "status":
            return status_action(payload)
        if action == "hash-account":
            raw = payload.get("account")
            if raw is None:
                return {"error": "account is required"}
            return {
                "ok": True,
                "account_hash": hash_account(str(raw), salt=payload.get("account_salt")),
            }
        if action == "input-provenance":
            trade = payload.get("trade") if isinstance(payload.get("trade"), dict) else payload
            return {"ok": True, "provenance": provenance_for_operator_fill(trade)}
        if action == "seed-trade":
            trade = payload.get("trade")
            if not isinstance(trade, dict):
                return {"error": "trade must be a JSON object"}
            result = seed_record(
                trade,
                ledger=_ledger(payload),
                persist=bool(payload.get("persist", False)),
                account_salt=payload.get("account_salt"),
                require_input_provenance=bool(payload.get("require_input_provenance", True)),
            )
            return {"ok": True, **result}
        if action == "ledger":
            account_hash = payload.get("account_hash")
            return {"ok": True, "summary": _ledger(payload).summary(account_hash)}
        if action == "gate-status":
            status = evaluate_ramp_gate(
                _ledger(payload),
                account_hash=payload.get("account_hash"),
                returns=_returns(payload),
                now=_parse_now(payload.get("now")),
                current_tier=payload.get("current_tier"),
                kill_switch_active=bool(payload.get("kill_switch_active", False)),
                confirmation_firewall_pending=bool(
                    payload.get("confirmation_firewall_pending", False)
                ),
            )
            return {"ok": True, "status": status.to_dict()}
        if action == "sortino":
            result = sortino_ratio(
                _returns(payload),
                target_return=float(payload.get("target_return", 0.0)),
                minimum_periods=int(payload.get("minimum_periods", 14)),
            )
            return {"ok": True, "sortino": result.to_dict()}
        if action == "forecast-rung-completion":
            start = payload.get("tier_start")
            if not start:
                return {"error": "tier_start is required"}
            return {
                "ok": True,
                "forecast": forecast_rung_completion(
                    _parse_now(start) or datetime.now(UTC),
                    now=_parse_now(payload.get("now")),
                ),
            }
    except Exception as exc:
        return {"error": str(exc), "action": action}
    return {"error": f"unknown action '{action}'", "valid_actions": list(VALID_ACTIONS)}


def run(action: str = "status", **kwargs: Any) -> str:
    return json.dumps(handle({"action": action, **kwargs}), indent=2, sort_keys=True)


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
    json.dump(response, stream_out, indent=2, sort_keys=True)
    return 1 if response.get("error") else 0


if __name__ == "__main__":
    raise SystemExit(main())
