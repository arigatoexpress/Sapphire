"""TradingView orchestrator — drive TV Desktop as a TA rendering engine.

This module commands the local TradingView Desktop instance via the `tv` CLI to:
- set symbols, timeframes, and indicator stacks
- capture screenshots, OHLCV summaries, and indicator values
- store artifacts with manifests for dashboard consumption

All mutations are gated by SAPPHIRE_TV_MUTATION_ENABLED. Without the gate, the
orchestrator runs in read-only capture mode (it records what is currently on
screen without changing symbol or studies).
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from lib.trading.tradingview_ta_machine import (
    DEFAULT_TIMEFRAMES,
    INDICATOR_STACK,
)

DEFAULT_TV_BIN = "tv"
DEFAULT_ARTIFACT_ROOT = Path.home() / "Code" / "Sapphire" / "data" / "tradingview_ta"
MUTATION_ENV = "SAPPHIRE_TV_MUTATION_ENABLED"
CAPTURE_TIMEOUT = 30


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

            manifest["timeframes"].append(tf_record)

        manifest_path = session_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
        manifest["manifest_path"] = str(manifest_path)
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

            manifest["symbols"].append(sym_record)

        manifest_path = session_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
        manifest["manifest_path"] = str(manifest_path)
        return manifest

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
