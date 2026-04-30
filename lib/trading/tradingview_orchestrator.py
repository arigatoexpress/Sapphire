"""TradingView orchestrator — drive TV Desktop as a TA rendering engine.

This module commands the local TradingView Desktop instance via the `tv` CLI to:
- set symbols, timeframes, and indicator stacks
- capture screenshots, OHLCV summaries, and indicator values
- store artifacts with manifests for dashboard consumption

All mutations are gated by SAPPHIRE_TV_MUTATION_ENABLED. Without the gate, the
orchestrator runs in read-only capture mode (it records what is currently on
screen without changing symbol or studies).

The orchestrator also scores each captured symbol/timeframe via
``compute_quick_signal_score`` — a pure, deterministic helper that turns the
in-memory OHLCV summary (and, when available, the indicator-values payload from
``tv values``) into ``{"score": float in [-1, +1], "regime": str,
"rationale": str}``. Scoring runs entirely on artifacts that were already
captured; no extra ``tv`` calls are issued.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from lib.trading.tradingview_ta_machine import (
    DEFAULT_TIMEFRAMES,
    INDICATOR_STACK,
)

log = logging.getLogger(__name__)

DEFAULT_TV_BIN = "tv"
DEFAULT_ARTIFACT_ROOT = Path.home() / "Code" / "Sapphire" / "data" / "tradingview_ta"
MUTATION_ENV = "SAPPHIRE_TV_MUTATION_ENABLED"
CAPTURE_TIMEOUT = 30

# Event names emitted to the bus. Kept here (not in lib.core.event_bus.EVENT_TYPES)
# because the canonical EVENT_TYPES list is reserved for trading/regime/threat
# signals that participate in WorldState aggregation. These are dashboard
# notifications only — subscribers use the exact name patterns.
EVENT_SESSION_COMPLETED = "tradingview.orchestrator.session_completed"
EVENT_PINE_BATCH_COMPLETED = "tradingview.orchestrator.pine_batch_completed"


def _emit_event(event_type: str, payload: dict[str, Any]) -> None:
    """Best-effort publish to the event bus.

    Never raises. The bus itself degrades to a JSONL fallback when Redis is
    unreachable, so the only failure modes here are import errors or unexpected
    exceptions; both are logged and swallowed so the orchestrator's main path
    is unaffected.
    """
    try:
        from lib.core.event_bus import publish  # local import: keep tv module light

        publish(event_type, payload, source="tradingview-orchestrator")
    except Exception as exc:  # noqa: BLE001 — defensive: never block capture
        log.warning("event_bus publish failed (%s): %s", event_type, exc)


_FLOAT_RE = re.compile(r"-?\d+(?:\.\d+)?")


def _parse_numeric(value: Any) -> float | None:
    """Coerce a TradingView indicator-values entry to a float.

    ``tv values`` returns strings ("65.32", "1.234e+04", "−12.5%", "-").
    Returns None for missing / non-numeric entries (e.g. "∅", empty).
    """
    if value is None:
        return None
    if isinstance(value, int | float):
        if isinstance(value, float) and (value != value):  # NaN
            return None
        return float(value)
    if not isinstance(value, str):
        return None
    s = value.strip()
    if not s or s in {"-", "—", "∅", "n/a", "N/A"}:
        return None
    # Normalize unicode minus, strip percent.
    s = s.replace("−", "-").replace("%", "").replace(",", "")
    m = _FLOAT_RE.search(s)
    if not m:
        return None
    try:
        return float(m.group(0))
    except (TypeError, ValueError):
        return None


def _flatten_indicator_values(values_payload: Any) -> dict[str, float]:
    """Flatten the ``tv values`` payload into a single name → float map.

    The payload is a list of ``{"name": <study>, "values": {<title>: <str>}}``
    entries. Keys are normalized to lowercase for case-insensitive lookups
    (e.g. "RSI", "Plot", "MACD", "Histogram", "Upper", "Lower", "Volume").
    """
    out: dict[str, float] = {}
    if isinstance(values_payload, dict):
        # Could be a {"ok": True, "payload": [...]} envelope. Drill in.
        inner = values_payload.get("payload") if "payload" in values_payload else None
        if inner is not None:
            return _flatten_indicator_values(inner)
        # Otherwise treat as a single entry-shaped dict.
        candidates = [values_payload]
    elif isinstance(values_payload, list):
        candidates = values_payload
    else:
        return out

    for entry in candidates:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "").lower()
        vals = entry.get("values") or {}
        if not isinstance(vals, dict):
            continue
        for title, raw in vals.items():
            num = _parse_numeric(raw)
            if num is None:
                continue
            key = f"{name}:{str(title).lower()}".strip(":")
            out[key] = num
            # Also store the bare title for convenience.
            bare = str(title).lower()
            out.setdefault(bare, num)
    return out


def _ohlcv_summary_payload(ohlcv: Any) -> dict[str, Any] | None:
    """Extract the summary dict from a probe_ohlcv result envelope."""
    if not isinstance(ohlcv, dict):
        return None
    payload = ohlcv.get("payload")
    if isinstance(payload, dict):
        return payload
    # Sometimes the envelope itself looks like the summary (used by tests).
    if "open" in ohlcv and "close" in ohlcv:
        return ohlcv
    return None


def _change_pct_from_summary(summary: dict[str, Any]) -> float | None:
    """Extract the period change percent (as a float, e.g. 2.5 for +2.5%)."""
    raw = summary.get("change_pct")
    if raw is None:
        # Fall back to deriving from open/close if available.
        try:
            open_ = float(summary.get("open"))
            close_ = float(summary.get("close"))
        except (TypeError, ValueError):
            return None
        if not open_:
            return None
        return ((close_ - open_) / open_) * 100.0
    return _parse_numeric(raw)


def _last5_trend(summary: dict[str, Any]) -> float:
    """Return a [-1, +1] trend score from last_5_bars closes (linear slope sign).

    Robust to short / missing series — degrades to 0.0.
    """
    bars = summary.get("last_5_bars") or []
    if not isinstance(bars, list) or len(bars) < 2:
        return 0.0
    closes: list[float] = []
    for bar in bars:
        if isinstance(bar, dict):
            c = bar.get("close")
            try:
                closes.append(float(c))
            except (TypeError, ValueError):
                continue
    if len(closes) < 2:
        return 0.0
    first = closes[0]
    last = closes[-1]
    if first <= 0:
        return 0.0
    delta_pct = (last - first) / first * 100.0
    # Normalize: a 5-bar move of ±5% is treated as a strong trend (clipped to ±1).
    return max(-1.0, min(1.0, delta_pct / 5.0))


def compute_quick_signal_score(
    ohlcv_summary: Any,
    indicator_values: Any | None = None,
) -> dict[str, Any]:
    """Score a captured TradingView snapshot in [-1, +1].

    Pure function over ``probe_ohlcv`` + ``probe_values`` artifacts. No side
    effects, no live market calls.

    Sub-scores (each in [-1, +1]) are blended with fixed weights:
      - RSI deviation from 50 (weight 0.30 if available)
      - MACD histogram sign + magnitude vs price (weight 0.30 if available)
      - EMA-20 vs price ratio (weight 0.20 if available)
      - Period change percent (always-on fallback, weight 0.10)
      - 5-bar local trend (always-on fallback, weight 0.10)

    Missing components are skipped and the remaining weights are renormalized.
    The returned ``regime`` is one of ``RISK_ON | TRANSITION | RISK_OFF`` and is
    derived from the period change percent thresholds in ``StrategyParams``
    (``+5% / -5%``) so the bucketing is consistent with the analytics
    strategies. ``rationale`` is a short human-readable string listing the
    components that contributed.
    """
    summary = _ohlcv_summary_payload(ohlcv_summary) or {}
    values = _flatten_indicator_values(indicator_values) if indicator_values is not None else {}

    components: list[tuple[str, float, float, str]] = []  # (name, score, weight, note)

    rsi = values.get("rsi:plot") or values.get("rsi") or values.get("plot")
    if rsi is not None and 0.0 <= rsi <= 100.0:
        # Map RSI 0→-1, 50→0, 100→+1. Centered at 50 = neutral.
        rsi_score = max(-1.0, min(1.0, (rsi - 50.0) / 50.0))
        components.append(("rsi", rsi_score, 0.30, f"RSI={rsi:.1f}"))

    # MACD histogram: positive = bullish momentum acceleration.
    macd_hist = (
        values.get("macd:histogram")
        or values.get("histogram")
        or values.get("macd:hist")
    )
    close = _parse_numeric(summary.get("close"))
    if macd_hist is not None and close and close > 0:
        # Histogram normalized against close price, then clipped.
        ratio = macd_hist / close
        macd_score = max(-1.0, min(1.0, ratio * 200.0))  # 0.5% of price → ±1
        components.append(("macd", macd_score, 0.30, f"MACD_hist={macd_hist:.4f}"))
    elif macd_hist is not None:
        # Fallback: sign-only contribution if we don't have a price reference.
        sign = 1.0 if macd_hist > 0 else (-1.0 if macd_hist < 0 else 0.0)
        components.append(("macd", sign, 0.30, f"MACD_hist={macd_hist:.4f}"))

    # EMA-20 trend: price vs the 20-period EMA tells us short-term direction.
    ema = (
        values.get("moving average exponential:plot")
        or values.get("ema:plot")
        or values.get("ema")
    )
    if ema is not None and close and close > 0:
        diff_pct = (close - ema) / ema * 100.0
        # ±2% above/below EMA → ±1 (clipped).
        ema_score = max(-1.0, min(1.0, diff_pct / 2.0))
        components.append(("ema", ema_score, 0.20, f"close_vs_EMA20={diff_pct:+.2f}%"))

    # Always-on fallbacks: period change % and last-5-bar trend. These keep the
    # scorer functional when only the OHLCV summary was captured (sweep mode).
    change_pct = _change_pct_from_summary(summary)
    if change_pct is not None:
        # ±10% over the captured window → ±1 (clipped).
        change_score = max(-1.0, min(1.0, change_pct / 10.0))
        components.append(("change_pct", change_score, 0.10, f"Δ={change_pct:+.2f}%"))

    trend_score = _last5_trend(summary)
    if trend_score != 0.0 or summary.get("last_5_bars"):
        components.append(("trend5", trend_score, 0.10, "5-bar trend"))

    # Blend, renormalizing weights of present components.
    total_weight = sum(w for _, _, w, _ in components)
    if total_weight > 0:
        blended = sum(s * w for _, s, w, _ in components) / total_weight
        score = max(-1.0, min(1.0, blended))
    else:
        score = 0.0

    # Regime bucket — mirror StrategyParams defaults (±5%).
    if change_pct is None:
        regime = "TRANSITION"
    elif change_pct >= 5.0:
        regime = "RISK_ON"
    elif change_pct <= -5.0:
        regime = "RISK_OFF"
    else:
        regime = "TRANSITION"

    if components:
        rationale = "; ".join(note for _, _, _, note in components)
    else:
        rationale = "no scorable components"

    return {
        "score": round(score, 4),
        "regime": regime,
        "rationale": rationale,
        "components": [
            {"name": n, "score": round(s, 4), "weight": w, "note": note}
            for n, s, w, note in components
        ],
    }


class TVCommandError(Exception):
    """A tv CLI command returned non-zero or unparseable output."""

    def __init__(self, message: str, *, command: str, returncode: int, stderr: str):
        super().__init__(message)
        self.command = command
        self.returncode = returncode
        self.stderr = stderr


class TradingViewOrchestrator:
    """Orchestrate TradingView Desktop for Sapphire TA capture."""

    def __init__(
        self,
        *,
        tv_bin: str = DEFAULT_TV_BIN,
        artifact_root: Path | str = DEFAULT_ARTIFACT_ROOT,
        mutation_enabled: bool | None = None,
    ):
        self.tv_bin = tv_bin
        self.artifact_root = Path(artifact_root)
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        if mutation_enabled is None:
            mutation_enabled = os.getenv(MUTATION_ENV) == "1"
        self.mutation_enabled = bool(mutation_enabled)

    def _run(
        self,
        *args: str,
        timeout: int = CAPTURE_TIMEOUT,
        parse_json: bool = True,
    ) -> dict[str, Any]:
        cmd = [self.tv_bin, *args]
        proc = subprocess.run(  # noqa: S603
            cmd,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        payload: Any = None
        parse_error: str | None = None
        if proc.stdout.strip() and parse_json:
            try:
                payload = json.loads(proc.stdout)
            except json.JSONDecodeError as exc:
                parse_error = str(exc)
        return {
            "command": " ".join(cmd),
            "returncode": proc.returncode,
            "ok": proc.returncode == 0,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "payload": payload,
            "parse_error": parse_error,
        }

    def _require_ok(self, result: dict[str, Any]) -> dict[str, Any]:
        if not result["ok"]:
            raise TVCommandError(
                f"tv CLI failed: {result['command']}",
                command=result["command"],
                returncode=result["returncode"],
                stderr=result["stderr"],
            )
        return result

    def _now_iso(self) -> str:
        return datetime.now(UTC).replace(microsecond=0).isoformat()

    def _session_dir(self, session_id: str) -> Path:
        return self.artifact_root / session_id

    def _safe_filename(self, symbol: str, timeframe: str, suffix: str) -> str:
        safe = symbol.replace(":", "_").replace("/", "_")
        return f"{safe}_{timeframe}_{suffix}"

    # ------------------------------------------------------------------
    # Read-only probes
    # ------------------------------------------------------------------

    def probe_state(self) -> dict[str, Any]:
        return self._run("state")

    def probe_quote(self, symbol: str | None = None) -> dict[str, Any]:
        args = ["quote"]
        if symbol:
            args.extend(["--symbol", symbol])
        return self._run(*args)

    def probe_ohlcv(self, symbol: str | None = None, bars: int = 120) -> dict[str, Any]:
        args = ["ohlcv", "--summary", "-n", str(bars)]
        if symbol:
            args.extend(["--symbol", symbol])
        return self._run(*args)

    def probe_values(self) -> dict[str, Any]:
        return self._run("values")

    def probe_pine_data(self, filter_prefix: str = "Sapphire") -> dict[str, Any]:
        return self._run("data", "lines", "-f", filter_prefix)

    def probe_info(self, symbol: str | None = None) -> dict[str, Any]:
        args = ["info"]
        if symbol:
            args.extend(["--symbol", symbol])
        return self._run(*args)

    # ------------------------------------------------------------------
    # Mutations (gated)
    # ------------------------------------------------------------------

    def set_symbol(self, symbol: str) -> dict[str, Any]:
        if not self.mutation_enabled:
            return {"mutated": False, "reason": f"{MUTATION_ENV} must be 1"}
        return self._run("symbol", symbol)

    def set_timeframe(self, timeframe: str) -> dict[str, Any]:
        if not self.mutation_enabled:
            return {"mutated": False, "reason": f"{MUTATION_ENV} must be 1"}
        return self._run("timeframe", timeframe)

    def set_pane_layout(self, layout: str = "2x2") -> dict[str, Any]:
        if not self.mutation_enabled:
            return {"mutated": False, "reason": f"{MUTATION_ENV} must be 1"}
        return self._run("pane", "layout", layout)

    def add_indicator(self, name: str) -> dict[str, Any]:
        if not self.mutation_enabled:
            return {"mutated": False, "reason": f"{MUTATION_ENV} must be 1"}
        return self._run("indicator", "add", name)

    def remove_indicator(self, id_or_name: str) -> dict[str, Any]:
        if not self.mutation_enabled:
            return {"mutated": False, "reason": f"{MUTATION_ENV} must be 1"}
        return self._run("indicator", "remove", id_or_name)

    def clear_indicators(self) -> dict[str, Any]:
        if not self.mutation_enabled:
            return {"mutated": False, "reason": f"{MUTATION_ENV} must be 1"}
        # TradingView CLI does not have a bulk-clear; iterate known studies from state
        state_res = self.probe_state()
        if not state_res["ok"]:
            return state_res
        studies = (state_res.get("payload") or {}).get("studies") or []
        removed = []
        for study in studies:
            sid = study.get("id")
            if sid:
                res = self._run("indicator", "remove", sid)
                removed.append({"id": sid, "ok": res["ok"]})
        return {"mutated": True, "action": "clear_indicators", "removed": removed}

    def setup_chart(
        self,
        symbol: str,
        timeframe: str = "60",
        chart_type: str = "Candles",
    ) -> dict[str, Any]:
        """Set symbol, timeframe, and chart type. Does NOT touch indicators."""
        if not self.mutation_enabled:
            return {"mutated": False, "reason": f"{MUTATION_ENV} must be 1"}
        results = []
        results.append(self._run("symbol", symbol))
        results.append(self._run("timeframe", timeframe))
        results.append(self._run("type", chart_type))
        ok = all(r["ok"] for r in results)
        return {
            "mutated": True,
            "action": "setup_chart",
            "symbol": symbol,
            "timeframe": timeframe,
            "chart_type": chart_type,
            "ok": ok,
            "steps": results,
        }

    def apply_indicator_stack(self, stack: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        """Add indicators from the default or provided stack."""
        if not self.mutation_enabled:
            return {"mutated": False, "reason": f"{MUTATION_ENV} must be 1"}
        stack = stack or list(INDICATOR_STACK)
        added = []
        for ind in stack:
            name = ind.get("tradingview_name") or ind.get("name")
            if not name:
                continue
            res = self._run("indicator", "add", name)
            added.append({"name": name, "ok": res["ok"], "error": res.get("stderr")})
        return {
            "mutated": True,
            "action": "apply_indicator_stack",
            "ok": all(a["ok"] for a in added),
            "added": added,
        }

    # ------------------------------------------------------------------
    # Pine Script orchestration
    # ------------------------------------------------------------------

    def pine_list(self) -> dict[str, Any]:
        """List Pine scripts saved on the user's TradingView account."""
        return self._run("pine", "list")

    def pine_get(self) -> dict[str, Any]:
        """Read the Pine script currently loaded in the editor."""
        return self._run("pine", "get")

    def pine_errors(self) -> dict[str, Any]:
        """Get current Pine compilation errors."""
        return self._run("pine", "errors")

    def pine_console(self) -> dict[str, Any]:
        """Get Pine console / log output."""
        return self._run("pine", "console")

    def pine_check_file(self, path: str | Path) -> dict[str, Any]:
        """Server-side compile check of a Pine source file (no chart needed)."""
        return self._run("pine", "check", "-f", str(path))

    def pine_analyze_file(self, path: str | Path) -> dict[str, Any]:
        """Offline static analysis of a Pine source file."""
        return self._run("pine", "analyze", "-f", str(path))

    def pine_open(self, name_or_id: str) -> dict[str, Any]:
        if not self.mutation_enabled:
            return {"mutated": False, "reason": f"{MUTATION_ENV} must be 1"}
        return self._run("pine", "open", name_or_id)

    def pine_set_from_file(self, path: str | Path) -> dict[str, Any]:
        if not self.mutation_enabled:
            return {"mutated": False, "reason": f"{MUTATION_ENV} must be 1"}
        return self._run("pine", "set", "--file", str(path))

    def pine_compile(self) -> dict[str, Any]:
        if not self.mutation_enabled:
            return {"mutated": False, "reason": f"{MUTATION_ENV} must be 1"}
        return self._run("pine", "compile")

    def pine_save(self) -> dict[str, Any]:
        if not self.mutation_enabled:
            return {"mutated": False, "reason": f"{MUTATION_ENV} must be 1"}
        return self._run("pine", "save")

    def pine_promote(self, pine_path: str | Path) -> dict[str, Any]:
        """Promote a local Pine source file into the TV editor: set + compile + save.

        Closes the loop from "generated locally" to "live in the TV editor on the
        user's TradingView account". Mutation-gated.

        Stages run in order; the first failure short-circuits and is reported in
        ``stage``. Each stage's raw ``_run`` result is preserved in ``stages`` so
        callers (CLI / dashboards) can inspect stdout/stderr. On clean compile
        the script is saved to the TV account and ``ok=True`` is returned.
        """
        if not self.mutation_enabled:
            return {"mutated": False, "reason": f"{MUTATION_ENV} must be 1"}

        stages: dict[str, Any] = {}

        set_res = self.pine_set_from_file(pine_path)
        stages["set"] = set_res
        if not set_res.get("ok", False):
            return {
                "ok": False,
                "mutated": True,
                "stage": "set",
                "path": str(pine_path),
                "stages": stages,
            }

        compile_res = self.pine_compile()
        stages["compile"] = compile_res
        if not compile_res.get("ok", False):
            return {
                "ok": False,
                "mutated": True,
                "stage": "compile",
                "path": str(pine_path),
                "stages": stages,
            }

        errors_res = self.pine_errors()
        stages["errors"] = errors_res
        errors_payload = errors_res.get("payload") if isinstance(errors_res, dict) else None
        error_list: list[Any] = []
        if isinstance(errors_payload, dict):
            raw = errors_payload.get("errors") or errors_payload.get("diagnostics") or []
            if isinstance(raw, list):
                error_list = raw
        elif isinstance(errors_payload, list):
            error_list = errors_payload
        if not errors_res.get("ok", False) or error_list:
            return {
                "ok": False,
                "mutated": True,
                "stage": "errors",
                "path": str(pine_path),
                "errors": error_list,
                "stages": stages,
            }

        save_res = self.pine_save()
        stages["save"] = save_res
        if not save_res.get("ok", False):
            return {
                "ok": False,
                "mutated": True,
                "stage": "save",
                "path": str(pine_path),
                "stages": stages,
            }

        return {
            "ok": True,
            "mutated": True,
            "path": str(pine_path),
            "stages": stages,
        }

    def pine_validate_file(self, path: str | Path) -> dict[str, Any]:
        """Run analyze + check on a file, return both results.

        Read-only: no chart manipulation. Useful for CI / pre-flight checks.
        """
        analyze = self.pine_analyze_file(path)
        check = self.pine_check_file(path)
        return {
            "ok": analyze["ok"] and check["ok"],
            "analyze": analyze,
            "check": check,
            "path": str(path),
        }

    # ------------------------------------------------------------------
    # Alert orchestration
    # ------------------------------------------------------------------

    def alerts_list(self) -> dict[str, Any]:
        return self._run("alert", "list")

    def alert_create(
        self,
        price: float,
        condition: str = "crossing",
        message: str = "Sapphire alert",
    ) -> dict[str, Any]:
        if not self.mutation_enabled:
            return {"mutated": False, "reason": f"{MUTATION_ENV} must be 1"}
        if condition not in {"crossing", "greater_than", "less_than"}:
            return {
                "mutated": False,
                "ok": False,
                "reason": f"invalid condition: {condition}",
            }
        return self._run(
            "alert",
            "create",
            "-p",
            str(price),
            "-c",
            condition,
            "-m",
            message,
        )

    def alert_delete(self, alert_id: str | int | None = None) -> dict[str, Any]:
        if not self.mutation_enabled:
            return {"mutated": False, "reason": f"{MUTATION_ENV} must be 1"}
        args = ["alert", "delete"]
        if alert_id is not None:
            args.append(str(alert_id))
        return self._run(*args)

    def screenshot(
        self,
        symbol: str,
        timeframe: str,
        session_dir: Path,
    ) -> dict[str, Any]:
        safe_base = self._safe_filename(symbol, timeframe, "screenshot")
        # tv screenshot saves to its own directory; we pass a basename and
        # then move the file to our artifact directory.
        res = self._run(
            "screenshot",
            "-r",
            "chart",
            "-o",
            safe_base,
        )
        src_path: Path | None = None
        dst_path = session_dir / f"{safe_base}.png"
        if res["ok"] and isinstance(res.get("payload"), dict):
            actual_path = res["payload"].get("file_path")
            if actual_path:
                src_path = Path(actual_path)
        # Fallback: search the tv-mcp screenshots dir for the file
        if src_path is None or not src_path.exists():
            mcp_screenshots = Path.home() / "Code" / "tradingview-mcp-v2" / "screenshots"
            candidates = list(mcp_screenshots.glob(f"*{safe_base}*.png"))
            if candidates:
                src_path = max(candidates, key=lambda p: p.stat().st_mtime)
        if src_path and src_path.exists():
            import shutil

            shutil.copy2(str(src_path), str(dst_path))
            src_path.unlink(missing_ok=True)
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "filename": dst_path.name,
            "path": str(dst_path),
            "ok": res["ok"] and dst_path.exists(),
            "command": res["command"],
            "stderr": res["stderr"],
        }

    # ------------------------------------------------------------------
    # Sessions
    # ------------------------------------------------------------------

    def capture_symbol_deep(
        self,
        symbol: str,
        tradingview_symbol: str,
        timeframes: list[str] | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Deep capture: one symbol across multiple timeframes with full stack."""
        session_id = session_id or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        session_dir = self._session_dir(session_id)
        session_dir.mkdir(parents=True, exist_ok=True)
        timeframes = timeframes or list(DEFAULT_TIMEFRAMES)

        manifest: dict[str, Any] = {
            "schema_version": "tradingview-orchestrator.deep_capture.v1",
            "generated_at": self._now_iso(),
            "session_id": session_id,
            "symbol": symbol,
            "tradingview_symbol": tradingview_symbol,
            "mutation_enabled": self.mutation_enabled,
            "timeframes": [],
            "safety": {
                "live_trading_enabled": False,
                "telegram_sends_enabled": False,
                "execution_policy": "analysis_only_no_order_submit",
            },
        }

        # Setup chart once for the primary timeframe
        if self.mutation_enabled:
            setup = self.setup_chart(tradingview_symbol, timeframes[0])
            manifest["chart_setup"] = setup
            # Apply indicators once
            stack_res = self.apply_indicator_stack()
            manifest["indicator_stack"] = stack_res

        for tf in timeframes:
            tf_record: dict[str, Any] = {"timeframe": tf, "artifacts": []}
            if self.mutation_enabled and tf != timeframes[0]:
                self.set_timeframe(tf)

            # Screenshot
            ss = self.screenshot(tradingview_symbol, tf, session_dir)
            tf_record["artifacts"].append({
                "kind": "screenshot",
                "ok": ss["ok"],
                "path": ss["path"],
                "filename": ss["filename"],
            })

            # OHLCV summary
            ohlcv = self.probe_ohlcv(tradingview_symbol)
            ohlcv_path = session_dir / self._safe_filename(tradingview_symbol, tf, "ohlcv.json")
            ohlcv_path.write_text(json.dumps(ohlcv, indent=2, sort_keys=True), encoding="utf-8")
            tf_record["artifacts"].append({
                "kind": "ohlcv",
                "ok": ohlcv["ok"],
                "path": str(ohlcv_path),
                "filename": ohlcv_path.name,
            })

            # Values
            values = self.probe_values()
            values_path = session_dir / self._safe_filename(tradingview_symbol, tf, "values.json")
            values_path.write_text(json.dumps(values, indent=2, sort_keys=True), encoding="utf-8")
            tf_record["artifacts"].append({
                "kind": "indicator_values",
                "ok": values["ok"],
                "path": str(values_path),
                "filename": values_path.name,
            })

            # Quote
            quote = self.probe_quote(tradingview_symbol)
            tf_record["quote_ok"] = quote["ok"]

            # Score from captured artifacts (pure, no extra tv calls).
            try:
                tf_record["score"] = compute_quick_signal_score(ohlcv, values)
            except Exception as exc:  # noqa: BLE001 — never block capture on scoring
                log.warning("scoring failed for %s @ %s: %s", tradingview_symbol, tf, exc)
                tf_record["score"] = {
                    "score": 0.0,
                    "regime": "TRANSITION",
                    "rationale": f"scorer error: {exc}",
                    "components": [],
                }

            manifest["timeframes"].append(tf_record)

        manifest_path = session_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
        manifest["manifest_path"] = str(manifest_path)

        _emit_event(
            EVENT_SESSION_COMPLETED,
            {
                "session_id": session_id,
                "schema_version": manifest["schema_version"],
                "symbol_count": 1,
                "timeframe_count": len(manifest["timeframes"]),
                "manifest_path": str(manifest_path),
            },
        )
        return manifest

    def capture_sweep(
        self,
        symbols: list[dict[str, Any]],
        session_id: str | None = None,
        primary_timeframe: str = "60",
    ) -> dict[str, Any]:
        """Sweep capture: one timeframe per symbol, fast."""
        session_id = session_id or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        session_dir = self._session_dir(session_id)
        session_dir.mkdir(parents=True, exist_ok=True)

        manifest: dict[str, Any] = {
            "schema_version": "tradingview-orchestrator.sweep_capture.v1",
            "generated_at": self._now_iso(),
            "session_id": session_id,
            "primary_timeframe": primary_timeframe,
            "mutation_enabled": self.mutation_enabled,
            "symbols": [],
            "safety": {
                "live_trading_enabled": False,
                "telegram_sends_enabled": False,
                "execution_policy": "analysis_only_no_order_submit",
            },
        }

        for row in symbols:
            tv_symbol = str(row.get("tradingview_symbol") or row.get("symbol") or "")
            if not tv_symbol:
                continue
            sym_record: dict[str, Any] = {
                "symbol": row.get("symbol"),
                "tradingview_symbol": tv_symbol,
                "rank": row.get("rank"),
                "artifacts": [],
            }

            if self.mutation_enabled:
                self.setup_chart(tv_symbol, primary_timeframe)

            ss = self.screenshot(tv_symbol, primary_timeframe, session_dir)
            sym_record["artifacts"].append({
                "kind": "screenshot",
                "ok": ss["ok"],
                "path": ss["path"],
                "filename": ss["filename"],
            })

            ohlcv = self.probe_ohlcv(tv_symbol)
            sym_record["artifacts"].append({
                "kind": "ohlcv",
                "ok": ohlcv["ok"],
            })

            quote = self.probe_quote(tv_symbol)
            sym_record["quote_ok"] = quote["ok"]

            # Score from captured artifacts (pure, no extra tv calls). Sweep
            # does not capture indicator values; the scorer falls back to the
            # OHLCV change-percent + 5-bar trend components.
            try:
                sym_record["score"] = compute_quick_signal_score(ohlcv, None)
            except Exception as exc:  # noqa: BLE001 — never block capture on scoring
                log.warning("scoring failed for %s: %s", tv_symbol, exc)
                sym_record["score"] = {
                    "score": 0.0,
                    "regime": "TRANSITION",
                    "rationale": f"scorer error: {exc}",
                    "components": [],
                }

            manifest["symbols"].append(sym_record)

        manifest_path = session_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
        manifest["manifest_path"] = str(manifest_path)

        _emit_event(
            EVENT_SESSION_COMPLETED,
            {
                "session_id": session_id,
                "schema_version": manifest["schema_version"],
                "symbol_count": len(manifest["symbols"]),
                "timeframe_count": 1,
                "manifest_path": str(manifest_path),
            },
        )
        return manifest

    def latest_scoring(self, top_n: int | None = None) -> dict[str, Any]:
        """Return the latest manifest's scoring rows, sorted by abs(score) desc.

        Output shape::

            {
              "session_id": str | None,
              "schema_version": str | None,
              "generated_at": str | None,
              "scored_at": <ISO8601>,
              "items": [
                {"symbol": ..., "tradingview_symbol": ..., "timeframe": ...,
                 "score": float, "regime": str, "rationale": str},
                ...
              ],
            }

        Items come from sweep ``symbols[]`` records or deep-capture
        ``timeframes[]`` records — whichever shape the latest manifest has.
        """
        manifest = self.latest_manifest()
        out: dict[str, Any] = {
            "session_id": None,
            "schema_version": None,
            "generated_at": None,
            "scored_at": self._now_iso(),
            "items": [],
        }
        if not manifest:
            return out

        out["session_id"] = manifest.get("session_id")
        out["schema_version"] = manifest.get("schema_version")
        out["generated_at"] = manifest.get("generated_at")

        items: list[dict[str, Any]] = []
        symbols = manifest.get("symbols") or []
        for row in symbols:
            score = row.get("score") or {}
            if not isinstance(score, dict):
                continue
            items.append({
                "symbol": row.get("symbol"),
                "tradingview_symbol": row.get("tradingview_symbol"),
                "timeframe": manifest.get("primary_timeframe"),
                "rank": row.get("rank"),
                "score": score.get("score", 0.0),
                "regime": score.get("regime"),
                "rationale": score.get("rationale"),
            })
        timeframes = manifest.get("timeframes") or []
        for row in timeframes:
            score = row.get("score") or {}
            if not isinstance(score, dict):
                continue
            items.append({
                "symbol": manifest.get("symbol"),
                "tradingview_symbol": manifest.get("tradingview_symbol"),
                "timeframe": row.get("timeframe"),
                "rank": None,
                "score": score.get("score", 0.0),
                "regime": score.get("regime"),
                "rationale": score.get("rationale"),
            })

        items.sort(key=lambda r: abs(float(r.get("score") or 0.0)), reverse=True)
        if top_n is not None and top_n > 0:
            items = items[:top_n]
        out["items"] = items
        return out

    def latest_manifest(self) -> dict[str, Any] | None:
        """Return the latest session manifest, if any."""
        sessions = sorted(
            (d for d in self.artifact_root.iterdir() if d.is_dir()),
            key=lambda p: p.name,
            reverse=True,
        )
        for session in sessions:
            manifest = session / "manifest.json"
            if manifest.exists():
                return json.loads(manifest.read_text(encoding="utf-8"))
        return None

    def list_sessions(self, limit: int = 20) -> list[dict[str, Any]]:
        sessions = sorted(
            (d for d in self.artifact_root.iterdir() if d.is_dir()),
            key=lambda p: p.name,
            reverse=True,
        )[:limit]
        results = []
        for session in sessions:
            manifest = session / "manifest.json"
            if manifest.exists():
                data = json.loads(manifest.read_text(encoding="utf-8"))
                results.append({
                    "session_id": session.name,
                    "generated_at": data.get("generated_at"),
                    "schema_version": data.get("schema_version"),
                    "symbol_count": len(data.get("symbols") or []),
                    "timeframe_count": len(data.get("timeframes") or []),
                })
        return results
