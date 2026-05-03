#!/usr/bin/env python3
"""Agent-facing read-only tool for the Sapphire TradingView orchestrator.

Wraps :class:`lib.trading.tradingview_orchestrator.TradingViewOrchestrator`
plus :mod:`lib.trading.pine_templates` behind a single dispatcher so the
LLM tool manifest stays at one entry. Mirrors the
``sapphire_megaeth_protocols`` pattern: one registered + agent_facing
plugin tool, many *actions*.

Surface — every action is **read-only** by construction:

* ``probe``        — TV state + quote + indicator values (no symbol/timeframe
                     mutation).
* ``score`` (limit) — Latest scoring rows from the most recent capture
                     manifest, sorted by ``abs(score)`` descending.
* ``list_pine``    — TradingView account Pine scripts plus locally generated
                     Pine sources under ``pine/generated/``.
* ``list_alerts``  — Active TradingView alerts.
* ``generate_pine`` (symbol, kind="indicator"|"strategy") — Render a Sapphire
                     Pine v5 indicator or strategy and write it under
                     ``pine/generated/``. Returns the generated file path
                     and metadata. **No TradingView push, no compile, no
                     save.** That all lives in the mutation-gated
                     orchestrator and is not exposed here.
* ``sweep`` (limit, offline=True) — Read-only TV TA sweep. Forces
                     ``mutation_enabled=False`` and ``offline=True`` by
                     default so the sweep never sets a symbol or fetches
                     live market data; it only captures whatever is
                     currently on the TV chart for the planned symbols.
                     Returns a manifest summary, not the full payload.

**Mutation paths are NOT exposed.** No ``set_symbol``, ``set_timeframe``,
``apply_indicator_stack``, ``pine_set_from_file``, ``pine_compile``,
``pine_save``, ``pine_promote``, ``alert_create``, ``alert_delete``, or
``setup_chart``. The dispatcher constructs the orchestrator with
``mutation_enabled=False`` regardless of the
``SAPPHIRE_TV_MUTATION_ENABLED`` env var, so even if the operator's shell
flips the gate, this plugin tool stays read-only. Mutation lives behind
``scripts/ops/tradingview_ta_capture.py`` (operator-supervised) — see
``docs/ops/tradingview-orchestrator-runbook.md``.

Return shape — every action returns one of::

    {"action": "<name>", "ok": true,  "data": {...}}
    {"action": "<name>", "ok": false, "error": "<reason>"}
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.trading.pine_templates import (  # noqa: E402
    list_generated,
    render_sapphire_watch_indicator,
    render_sapphire_watch_strategy,
    write_template,
)
from lib.trading.tradingview_orchestrator import TradingViewOrchestrator  # noqa: E402

VALID_ACTIONS = (
    "probe",
    "score",
    "list_pine",
    "list_alerts",
    "generate_pine",
    "sweep",
)

# Mutation actions on the orchestrator that this tool intentionally does
# NOT expose. Listed here for the ``describe`` debug action and for the
# unit tests that assert read-only enforcement.
BLOCKED_MUTATION_ACTIONS = (
    "set_symbol",
    "set_timeframe",
    "setup_chart",
    "apply_indicator_stack",
    "pine_set_from_file",
    "pine_compile",
    "pine_save",
    "pine_promote",
    "pine_open",
    "alert_create",
    "alert_delete",
    "clear_indicators",
    "add_indicator",
    "remove_indicator",
)

DEFAULT_SCORE_LIMIT = 10
DEFAULT_SWEEP_LIMIT = 6


def _make_orchestrator(tv_bin: str = "tv") -> TradingViewOrchestrator:
    """Construct an orchestrator with ``mutation_enabled=False`` always.

    Even if ``SAPPHIRE_TV_MUTATION_ENABLED=1`` is set in the environment,
    this plugin tool refuses to honor it — the read-only contract is
    enforced at the dispatcher boundary, not at the env-var boundary.
    """
    return TradingViewOrchestrator(tv_bin=tv_bin, mutation_enabled=False)


def _normalize_action(raw: Any) -> str:
    return str(raw or "probe").strip().lower().replace("-", "_")


def _ok(action: str, data: Any) -> dict[str, Any]:
    return {"action": action, "ok": True, "data": data}


def _err(action: str, reason: str) -> dict[str, Any]:
    return {"action": action, "ok": False, "error": reason}


# ---------------------------------------------------------------------------
# Action implementations
# ---------------------------------------------------------------------------


def _action_probe(payload: dict[str, Any]) -> dict[str, Any]:
    """Read-only probe: state + quote + indicator values.

    Mirrors ``cmd_probe`` in ``scripts/ops/tradingview_ta_capture.py`` but
    drops ``ohlcv`` and ``info`` to keep the payload lean for an agent
    response. The full probe surface is still available via the script
    for operator-supervised use.
    """
    orch = _make_orchestrator(tv_bin=str(payload.get("tv_bin") or "tv"))
    return _ok(
        "probe",
        {
            "state": orch.probe_state(),
            "quote": orch.probe_quote(symbol=payload.get("symbol")),
            "values": orch.probe_values(),
            "mutation_enabled": False,
        },
    )


def _action_score(payload: dict[str, Any]) -> dict[str, Any]:
    """Latest scoring rows from the most recent capture manifest.

    Pure read of artifacts on disk under
    ``data/tradingview_ta/<session>/manifest.json``. Never issues a ``tv``
    CLI call, never writes.
    """
    raw_limit = payload.get("limit", DEFAULT_SCORE_LIMIT)
    try:
        limit = int(raw_limit)
    except (TypeError, ValueError):
        return _err("score", f"invalid limit: {raw_limit!r}")
    if limit <= 0:
        limit = DEFAULT_SCORE_LIMIT
    orch = _make_orchestrator(tv_bin=str(payload.get("tv_bin") or "tv"))
    return _ok("score", orch.latest_scoring(top_n=limit))


def _action_list_pine(payload: dict[str, Any]) -> dict[str, Any]:
    """List Pine scripts on the TV account plus locally generated ones."""
    orch = _make_orchestrator(tv_bin=str(payload.get("tv_bin") or "tv"))
    return _ok(
        "list_pine",
        {
            "tv_account_scripts": orch.pine_list(),
            "generated_local": list_generated(),
        },
    )


def _action_list_alerts(payload: dict[str, Any]) -> dict[str, Any]:
    """List currently active TradingView alerts (read-only)."""
    orch = _make_orchestrator(tv_bin=str(payload.get("tv_bin") or "tv"))
    return _ok("list_alerts", orch.alerts_list())


def _action_generate_pine(payload: dict[str, Any]) -> dict[str, Any]:
    """Render a Sapphire Pine v5 indicator/strategy and write it to disk.

    No TV push, no compile, no save. Equivalent to running
    ``cmd_pine_generate`` / ``cmd_pine_generate_strategy`` from the ops
    script with ``--validate`` *off* — purely an offline render.

    Required: ``symbol``. Optional: ``kind`` ("indicator" default,
    "strategy"), ``name`` (defaults to ``Sapphire_Watch_<symbol>`` or
    ``Sapphire_Strategy_<symbol>``).
    """
    symbol = payload.get("symbol")
    if not isinstance(symbol, str) or not symbol.strip():
        return _err("generate_pine", "missing required string field 'symbol'")
    symbol = symbol.strip()

    kind = str(payload.get("kind") or "indicator").strip().lower()
    if kind not in {"indicator", "strategy"}:
        return _err("generate_pine", f"invalid kind: {kind!r} (expected 'indicator' or 'strategy')")

    if kind == "strategy":
        pine = render_sapphire_watch_strategy(symbol)
        default_name = f"Sapphire_Strategy_{symbol}"
        kind_meta = "sapphire_watch_strategy"
    else:
        pine = render_sapphire_watch_indicator(symbol)
        default_name = f"Sapphire_Watch_{symbol}"
        kind_meta = "sapphire_watch_indicator"

    name_raw = payload.get("name")
    name = (
        str(name_raw).strip()
        if isinstance(name_raw, str) and name_raw.strip()
        else default_name
    )

    written = write_template(
        name,
        pine,
        metadata={
            "kind": kind_meta,
            "tradingview_symbol": symbol,
        },
    )
    return _ok(
        "generate_pine",
        {
            "kind": kind_meta,
            "name": written["name"],
            "slug": written["slug"],
            "pine_path": written["pine_path"],
            "metadata_path": written["metadata_path"],
            "byte_size": written["metadata"]["byte_size"],
        },
    )


def _action_sweep(payload: dict[str, Any]) -> dict[str, Any]:
    """Read-only sweep — never mutates the chart.

    The orchestrator is constructed with ``mutation_enabled=False`` (see
    :func:`_make_orchestrator`), so ``capture_sweep`` skips ``setup_chart``
    on every iteration and only captures whatever is currently visible on
    TradingView for the planned symbols. Returns a manifest *summary*
    (counts + paths + symbol list) instead of the full payload to keep
    the agent response compact.

    Default ``offline=True`` — no live market-data fetch when ranking the
    watchlist; the rank source is the cached watchlist artifact.
    """
    raw_limit = payload.get("limit", DEFAULT_SWEEP_LIMIT)
    try:
        limit = int(raw_limit)
    except (TypeError, ValueError):
        return _err("sweep", f"invalid limit: {raw_limit!r}")
    if limit <= 0:
        limit = DEFAULT_SWEEP_LIMIT

    offline = payload.get("offline", True)
    primary_timeframe = str(payload.get("timeframe") or "60")

    # Late import: build_tradingview_ta_machine pulls a fair amount of
    # market-data plumbing; keep the import-time cost off the probe path.
    from lib.trading.tradingview_ta_machine import (  # noqa: PLC0415
        build_tradingview_ta_machine,
    )

    plan = build_tradingview_ta_machine(fetch_live=not offline, limit=limit)
    symbols = plan["watchlist"]["symbols"][:limit]

    orch = _make_orchestrator(tv_bin=str(payload.get("tv_bin") or "tv"))
    manifest = orch.capture_sweep(
        symbols,
        session_id=payload.get("session_id"),
        primary_timeframe=primary_timeframe,
    )
    return _ok(
        "sweep",
        {
            "session_id": manifest.get("session_id"),
            "schema_version": manifest.get("schema_version"),
            "primary_timeframe": manifest.get("primary_timeframe"),
            "mutation_enabled": manifest.get("mutation_enabled", False),
            "manifest_path": manifest.get("manifest_path"),
            "symbol_count": len(manifest.get("symbols") or []),
            "symbols": [
                {
                    "symbol": s.get("symbol"),
                    "tradingview_symbol": s.get("tradingview_symbol"),
                    "rank": s.get("rank"),
                    "artifacts_ok": sum(
                        1 for a in (s.get("artifacts") or []) if a.get("ok")
                    ),
                    "score": s.get("score"),
                }
                for s in (manifest.get("symbols") or [])
            ],
        },
    )


_ACTION_TABLE = {
    "probe": _action_probe,
    "score": _action_score,
    "list_pine": _action_list_pine,
    "list_alerts": _action_list_alerts,
    "generate_pine": _action_generate_pine,
    "sweep": _action_sweep,
}


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


def handle(payload: dict[str, Any]) -> dict[str, Any]:
    """Dispatch a plugin payload to the matching read-only action."""
    if not isinstance(payload, dict):
        return _err("dispatch", "payload must be a JSON object")
    action = _normalize_action(payload.get("action"))

    if action in BLOCKED_MUTATION_ACTIONS:
        return _err(
            action,
            (
                f"action '{action}' is a mutation; this plugin tool is read-only. "
                "Use scripts/ops/tradingview_ta_capture.py with "
                "SAPPHIRE_TV_MUTATION_ENABLED=1 under operator supervision."
            ),
        )

    impl = _ACTION_TABLE.get(action)
    if impl is None:
        return {
            "action": action,
            "ok": False,
            "error": f"unknown action '{action}'",
            "valid_actions": list(VALID_ACTIONS),
        }
    try:
        return impl(payload)
    except Exception as exc:  # noqa: BLE001 — surface as JSON, never raise
        return _err(action, f"{type(exc).__name__}: {exc}")


def run(action: str = "probe", **kwargs: Any) -> str:
    """Tool entry point used by direct imports and simple plugin callers."""
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
    json.dump(response, stream_out, indent=2, sort_keys=True, default=str)
    return 1 if not response.get("ok", False) else 0


if __name__ == "__main__":
    raise SystemExit(main())
