#!/usr/bin/env python3
"""
Sapphire control-plane CLI (phase 1).

This tool introduces a Firestore-backed desired/applied runtime state for the
live Lighter trader and wraps profile deployment + canary verification into one
auditable workflow.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

PROJECT_ID = os.getenv("PROJECT_ID", "sapphire-479610")
PLATFORM = "lighter"
DEFAULT_HOST = "rari@100.87.225.89"
DEFAULT_SERVICE = "lighter-trading"

REPO_ROOT = Path(__file__).resolve().parents[1]
DEPLOY_SCRIPT = REPO_ROOT / "scripts" / "deploy_lighter_strategy_profile.sh"
TEST_SCRIPT = REPO_ROOT / "scripts" / "run_unified_lighter_prod_test.sh"
CONTROLPLANE_ENV_FILE = REPO_ROOT / "configs" / "controlplane" / "sapphirectl.env"

DESIRED_COLLECTION = "control_plane_desired"
APPLIED_COLLECTION = "control_plane_applied"
APPLIED_HISTORY_COLLECTION = "control_plane_applied_history"
EVENTS_COLLECTION = "control_plane_events"
LANE_HEALTH_COLLECTION = "execution_lane_health"


PROFILE_SETTINGS: dict[str, dict[str, str]] = {
    "luxalgo_sol_15m_safe": {
        "LIGHTER_ALLOWED_STRATEGIES": "luxalgo_msb_ob,smart_money_breakout,algoalpha_smb",
        "LIGHTER_ALLOWED_TIMEFRAMES": "15m",
        "LIGHTER_STRATEGY_REQUIRE_METADATA": "true",
        "LIGHTER_SINGLE_SYMBOL_MODE": "true",
        "LIGHTER_MAX_ORDER_NOTIONAL_USD": "5",
        "LIGHTER_MAX_POSITION_NOTIONAL_USD": "10",
        "LIGHTER_ENTRY_COOLDOWN_SECONDS": "600",
        "LIGHTER_DEFAULT_TAKE_PROFIT_PCT": "1.2",
        "LIGHTER_DEFAULT_STOP_LOSS_PCT": "0.8",
    },
    "luxalgo_sol_5m_active": {
        "LIGHTER_ALLOWED_STRATEGIES": "luxalgo_msb_ob,smart_money_breakout,algoalpha_smb",
        "LIGHTER_ALLOWED_TIMEFRAMES": "5m",
        "LIGHTER_STRATEGY_REQUIRE_METADATA": "true",
        "LIGHTER_SINGLE_SYMBOL_MODE": "true",
        "LIGHTER_MAX_ORDER_NOTIONAL_USD": "5",
        "LIGHTER_MAX_POSITION_NOTIONAL_USD": "8",
        "LIGHTER_ENTRY_COOLDOWN_SECONDS": "180",
        "LIGHTER_DEFAULT_TAKE_PROFIT_PCT": "1.2",
        "LIGHTER_DEFAULT_STOP_LOSS_PCT": "0.8",
    },
    "chartprime_sol_5m_test": {
        "LIGHTER_ALLOWED_STRATEGIES": "chartprime_tbt,trendline_breakout_targets",
        "LIGHTER_ALLOWED_TIMEFRAMES": "5m",
        "LIGHTER_STRATEGY_REQUIRE_METADATA": "true",
        "LIGHTER_SINGLE_SYMBOL_MODE": "true",
        "LIGHTER_MAX_ORDER_NOTIONAL_USD": "3",
        "LIGHTER_MAX_POSITION_NOTIONAL_USD": "8",
        "LIGHTER_ENTRY_COOLDOWN_SECONDS": "300",
        "LIGHTER_DEFAULT_TAKE_PROFIT_PCT": "1.0",
        "LIGHTER_DEFAULT_STOP_LOSS_PCT": "0.7",
    },
    "failover_canary_only": {
        "LIGHTER_ALLOWED_STRATEGIES": "luxalgo_msb_ob,smart_money_breakout,algoalpha_smb",
        "LIGHTER_ALLOWED_TIMEFRAMES": "5m",
        "LIGHTER_ALLOWED_SIGNAL_SOURCES": "codex-unified-prod-test,sapphirectl-canary",
        "LIGHTER_STRATEGY_REQUIRE_METADATA": "true",
        "LIGHTER_SINGLE_SYMBOL_MODE": "true",
        "LIGHTER_MAX_ORDER_NOTIONAL_USD": "1.5",
        "LIGHTER_MAX_POSITION_NOTIONAL_USD": "2.0",
        "LIGHTER_TARGET_ORDER_NOTIONAL_USD": "1.0",
        "LIGHTER_MIN_ENTRY_NOTIONAL_USD": "0.5",
        "LIGHTER_MAX_SIGNAL_LEVERAGE": "3",
        "LIGHTER_ENTRY_COOLDOWN_SECONDS": "120",
        "LIGHTER_DEFAULT_TAKE_PROFIT_PCT": "1.0",
        "LIGHTER_DEFAULT_STOP_LOSS_PCT": "0.7",
    },
}

PROMOTION_STAGES: dict[str, dict[str, Any]] = {
    "paper": {
        "profile": "luxalgo_sol_5m_active",
        "run_test": False,
        "close_after_test": False,
        "test_quantity": "0.001",
        "overrides": {
            "ALLOW_LIVE_TRADING": "0",
            "TRADING_ENABLED": "1",
            "LIGHTER_MAX_ORDER_NOTIONAL_USD": "0.5",
            "LIGHTER_MAX_POSITION_NOTIONAL_USD": "1.5",
            "LIGHTER_ENTRY_COOLDOWN_SECONDS": "300",
        },
    },
    "canary": {
        "profile": "luxalgo_sol_5m_active",
        "run_test": True,
        "close_after_test": True,
        "test_quantity": "0.01",
        "overrides": {
            "ALLOW_LIVE_TRADING": "1",
            "TRADING_ENABLED": "1",
            "LIGHTER_MAX_ORDER_NOTIONAL_USD": "1.0",
            "LIGHTER_MAX_POSITION_NOTIONAL_USD": "3.0",
            "LIGHTER_ENTRY_COOLDOWN_SECONDS": "240",
        },
    },
    "live": {
        "profile": "luxalgo_sol_5m_active",
        "run_test": True,
        "close_after_test": False,
        "test_quantity": "0.02",
        "overrides": {
            "ALLOW_LIVE_TRADING": "1",
            "TRADING_ENABLED": "1",
            "LIGHTER_MAX_ORDER_NOTIONAL_USD": "5",
            "LIGHTER_MAX_POSITION_NOTIONAL_USD": "8",
            "LIGHTER_ENTRY_COOLDOWN_SECONDS": "180",
        },
    },
}


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _utc_now_iso() -> str:
    return _utc_now().isoformat()


def _short_output(text: str, limit: int = 8000) -> str:
    if len(text) <= limit:
        return text
    return text[-limit:]


def _parse_overrides(items: list[str]) -> dict[str, str]:
    overrides: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"Invalid override '{item}'. Expected KEY=VALUE.")
        key, value = item.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            raise ValueError(f"Invalid override '{item}'. Empty key.")
        overrides[key] = value
    return overrides


def _load_env_file_defaults(path: Path) -> None:
    if not path.exists():
        return
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if not key:
            continue
        os.environ.setdefault(key, value)


def _is_truthy_flag(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "on"}


@dataclass
class CommandResult:
    ok: bool
    returncode: int
    cmd: list[str]
    stdout: str
    stderr: str

    @property
    def combined_output(self) -> str:
        parts = []
        if self.stdout:
            parts.append(self.stdout)
        if self.stderr:
            parts.append(self.stderr)
        return "\n".join(parts).strip()

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "returncode": self.returncode,
            "cmd": self.cmd,
            "output": _short_output(self.combined_output),
        }


class SapphireCtl:
    def __init__(self, project: str):
        _load_env_file_defaults(CONTROLPLANE_ENV_FILE)
        self.project = project
        self.db = firestore.Client(project=project)

    def _event(self, event_type: str, payload: dict[str, Any]) -> None:
        body = {
            "timestamp": _utc_now(),
            "timestamp_iso": _utc_now_iso(),
            "event_type": event_type,
            "platform": PLATFORM,
            "payload": payload,
        }
        self.db.collection(EVENTS_COLLECTION).document().set(body)

    @staticmethod
    def _run(cmd: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> CommandResult:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        return CommandResult(
            ok=proc.returncode == 0,
            returncode=proc.returncode,
            cmd=cmd,
            stdout=proc.stdout or "",
            stderr=proc.stderr or "",
        )

    @staticmethod
    def _as_utc_datetime(value: Any) -> datetime | None:
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=UTC)
            return value.astimezone(UTC)
        text = str(value or "").strip()
        if not text:
            return None
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            return dt.astimezone(UTC)
        except ValueError:
            return None

    def _fetch_runtime_status(self, *, target_host: str) -> dict[str, Any]:
        marker = "__HTTP_STATUS__:"
        result = self._run(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=8",
                target_host,
                (
                    "curl -sS --max-time 6 "
                    "-w '\\n" + marker + "%{http_code}' "
                    "http://127.0.0.1:8080/health"
                ),
            ],
            cwd=REPO_ROOT,
            env=os.environ.copy(),
        )
        body = (result.stdout or "").strip()
        http_status = ""
        if marker in body:
            body, http_status = body.rsplit(marker, 1)
            body = body.strip()
            http_status = http_status.strip()
        healthy = result.ok and http_status == "200"
        payload: dict[str, Any] = {}
        if healthy and body:
            try:
                payload = json.loads(body)
            except json.JSONDecodeError:
                payload = {}
        return {
            "ok": healthy,
            "http_status": http_status or "unknown",
            "output": _short_output(body or result.combined_output, limit=1200),
            "endpoint": "http://127.0.0.1:8080/health",
            "payload": payload,
        }

    @staticmethod
    def _configured_failover_hosts() -> list[str]:
        raw = str(os.getenv("SAPPHIRECTL_FAILOVER_HOSTS", "")).strip()
        if not raw:
            return []
        hosts: list[str] = []
        for item in raw.split(","):
            host = item.strip()
            if host:
                hosts.append(host)
        return hosts

    def _select_target_host(
        self,
        *,
        requested_target_host: str,
        run_test: bool,
        enforce_lane_health: bool,
        auto_failover: bool,
    ) -> tuple[str, dict[str, Any]]:
        lookback = int(os.getenv("SAPPHIRECTL_LANE_LOOKBACK_MINUTES", "45"))
        primary_lane = self._lane_health(target_host=requested_target_host, lookback_minutes=lookback)
        failover_hosts = [h for h in self._configured_failover_hosts() if h != requested_target_host]
        decision: dict[str, Any] = {
            "requested_target_host": requested_target_host,
            "selected_target_host": requested_target_host,
            "run_test": bool(run_test),
            "enforce_lane_health": bool(enforce_lane_health),
            "auto_failover": bool(auto_failover),
            "primary_lane_health": primary_lane,
            "failover_hosts": failover_hosts,
            "failover_used": False,
            "reason": "requested_host",
            "fallback_candidates": [],
        }

        if not run_test:
            decision["reason"] = "run_test_disabled"
            return requested_target_host, decision
        if not enforce_lane_health:
            decision["reason"] = "lane_health_enforcement_disabled"
            return requested_target_host, decision
        if primary_lane.get("healthy", False):
            decision["reason"] = "primary_lane_healthy"
            return requested_target_host, decision
        if not auto_failover:
            decision["reason"] = "primary_lane_unhealthy_no_failover"
            return requested_target_host, decision

        for host in failover_hosts:
            runtime = self._fetch_runtime_status(target_host=host)
            runtime_payload = runtime.get("payload") if isinstance(runtime.get("payload"), dict) else {}
            runtime_ready = bool(runtime.get("ok", False)) and (runtime_payload.get("ready", True) is not False)
            trading_flags = self._fetch_host_trading_flags(target_host=host)
            trading_ready = bool(trading_flags.get("trading_enabled")) and bool(trading_flags.get("allow_live_trading"))
            candidate = {
                "host": host,
                "runtime_ok": bool(runtime.get("ok", False)),
                "runtime_ready": runtime_ready,
                "runtime_ready_reasons": runtime_payload.get("ready_reasons", []),
                "runtime_http_status": runtime.get("http_status", ""),
                "runtime_output": runtime.get("output", ""),
                "trading_enabled": bool(trading_flags.get("trading_enabled")),
                "allow_live_trading": bool(trading_flags.get("allow_live_trading")),
                "trading_ready_for_test": trading_ready,
            }
            decision["fallback_candidates"].append(candidate)
            if runtime_ready and trading_ready:
                decision["selected_target_host"] = host
                decision["failover_used"] = True
                decision["reason"] = "primary_lane_unhealthy_failover_selected"
                return host, decision

        decision["reason"] = "primary_lane_unhealthy_no_test_capable_failover"
        return requested_target_host, decision

    def _fetch_host_trading_flags(self, *, target_host: str) -> dict[str, Any]:
        cmd = (
            "python3 - <<'PY'\n"
            "import os, pathlib\n"
            "p = pathlib.Path('/home/rari/Sapphire/services/bot-lighter/.env')\n"
            "vals = {'TRADING_ENABLED':'', 'ALLOW_LIVE_TRADING':''}\n"
            "if p.exists():\n"
            "  for raw in p.read_text(encoding='utf-8', errors='ignore').splitlines():\n"
            "    line = raw.strip()\n"
            "    if not line or line.startswith('#') or '=' not in line:\n"
            "      continue\n"
            "    k,v = line.split('=',1)\n"
            "    k = k.strip(); v = v.strip().strip('\\\"').strip(\"'\")\n"
            "    if k in vals:\n"
            "      vals[k] = v\n"
            "for k in ('TRADING_ENABLED','ALLOW_LIVE_TRADING'):\n"
            "  print(f'{k}={vals.get(k, \"\")}')\n"
            "PY"
        )
        result = self._run(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=8",
                target_host,
                cmd,
            ],
            cwd=REPO_ROOT,
            env=os.environ.copy(),
        )
        values: dict[str, str] = {}
        if result.ok:
            for raw in (result.stdout or "").splitlines():
                line = raw.strip()
                if "=" not in line:
                    continue
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip()
        return {
            "trading_enabled": _is_truthy_flag(values.get("TRADING_ENABLED")),
            "allow_live_trading": _is_truthy_flag(values.get("ALLOW_LIVE_TRADING")),
            "raw": values,
        }

    def _lane_health(self, *, target_host: str, lookback_minutes: int = 45) -> dict[str, Any]:
        now = _utc_now()
        since = now - timedelta(minutes=max(1, int(lookback_minutes)))
        runtime = self._fetch_runtime_status(target_host=target_host)
        runtime_payload = runtime.get("payload") or {}

        exec_rows: list[dict[str, Any]] = []
        query = (
            self.db.collection("execution_verifications")
            .where(filter=FieldFilter("recorded_at", ">=", since))
            .order_by("recorded_at", direction=firestore.Query.ASCENDING)
        )
        try:
            for doc in query.stream():
                row = doc.to_dict() or {}
                if str(row.get("platform", "")).lower() != PLATFORM:
                    continue
                exec_rows.append(row)
        except Exception as exc:
            return {
                "healthy": False,
                "lookback_minutes": lookback_minutes,
                "checked_at": _utc_now_iso(),
                "reasons": [f"execution_verifications query failed: {exc}"],
                "warnings": [],
                "runtime_status": runtime,
                "rows": 0,
                "restricted_errors": 0,
                "recent_real_fills": 0,
                "last_restricted_at": "",
                "last_real_fill_at": "",
                "fills_after_last_restricted": 0,
            }

        restricted_errors = 0
        recent_real_fills = 0
        last_restricted_at: datetime | None = None
        last_real_fill_at: datetime | None = None
        fills_after_last_restricted = 0

        for row in exec_rows:
            err = str(row.get("error_message", "") or "").lower()
            recorded_at = self._as_utc_datetime(row.get("recorded_at"))
            is_restricted = ("restricted jurisdiction" in err) or ("20558" in err and "restricted" in err)
            if is_restricted:
                restricted_errors += 1
                if recorded_at and (last_restricted_at is None or recorded_at > last_restricted_at):
                    last_restricted_at = recorded_at

            success = bool(row.get("success", False))
            try:
                fill_qty = float(row.get("filled_quantity") or 0.0)
            except (TypeError, ValueError):
                fill_qty = 0.0
            if success and fill_qty > 0:
                recent_real_fills += 1
                if recorded_at and (last_real_fill_at is None or recorded_at > last_real_fill_at):
                    last_real_fill_at = recorded_at

        if last_restricted_at is not None:
            for row in exec_rows:
                recorded_at = self._as_utc_datetime(row.get("recorded_at"))
                if not recorded_at or recorded_at <= last_restricted_at:
                    continue
                success = bool(row.get("success", False))
                try:
                    fill_qty = float(row.get("filled_quantity") or 0.0)
                except (TypeError, ValueError):
                    fill_qty = 0.0
                if success and fill_qty > 0:
                    fills_after_last_restricted += 1

        block_remaining = 0.0
        try:
            block_remaining = float(runtime_payload.get("jurisdiction_block_remaining_sec") or 0.0)
        except (TypeError, ValueError):
            block_remaining = 0.0

        reasons: list[str] = []
        warnings: list[str] = []

        if not runtime.get("ok", False):
            reasons.append("runtime status endpoint unavailable via ssh/curl")
        runtime_ready = runtime_payload.get("ready")
        if runtime.get("ok", False) and runtime_ready is False:
            rr = runtime_payload.get("ready_reasons")
            if isinstance(rr, list) and rr:
                reasons.append("runtime not ready: " + ", ".join([str(x) for x in rr[:6]]))
            else:
                reasons.append("runtime reports not ready")
        if block_remaining > 0:
            reasons.append(f"runtime jurisdiction block active ({block_remaining:.0f}s remaining)")
        if restricted_errors > 0 and fills_after_last_restricted == 0:
            reasons.append(
                f"restricted-jurisdiction errors observed ({restricted_errors}) with no successful fills after latest restriction"
            )
        elif restricted_errors > 0:
            warnings.append(
                f"restricted-jurisdiction errors observed ({restricted_errors}) but recent fills recovered lane"
            )

        healthy = len(reasons) == 0
        status = {
            "healthy": healthy,
            "lookback_minutes": lookback_minutes,
            "checked_at": _utc_now_iso(),
            "reasons": reasons,
            "warnings": warnings,
            "runtime_status": runtime,
            "rows": len(exec_rows),
            "restricted_errors": restricted_errors,
            "recent_real_fills": recent_real_fills,
            "last_restricted_at": last_restricted_at.isoformat() if last_restricted_at else "",
            "last_real_fill_at": last_real_fill_at.isoformat() if last_real_fill_at else "",
            "fills_after_last_restricted": fills_after_last_restricted,
        }
        try:
            self.db.collection(LANE_HEALTH_COLLECTION).document(PLATFORM).set(
                {
                    **status,
                    "checked_at_dt": _utc_now(),
                    "platform": PLATFORM,
                }
            )
        except Exception:
            pass
        return status

    def _close_all_positions(self, *, target_host: str) -> CommandResult:
        cmd = [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=10",
            target_host,
            (
                "curl -sS -X POST http://127.0.0.1:8080/execute "
                "-H 'Content-Type: application/json' "
                "-d '{\"action\":\"CLOSE_ALL\",\"source\":\"sapphirectl\",\"reason\":\"post_test_flatten\"}'"
            ),
        ]
        result = self._run(cmd, cwd=REPO_ROOT, env=os.environ.copy())
        self._event(
            "close_all_requested",
            {
                "target_host": target_host,
                "ok": result.ok,
                "returncode": result.returncode,
                "output": _short_output(result.combined_output, limit=2000),
            },
        )
        return result

    def _apply_overrides_remote(
        self,
        *,
        target_host: str,
        overrides: dict[str, str],
    ) -> CommandResult:
        if not overrides:
            return CommandResult(
                ok=True,
                returncode=0,
                cmd=[],
                stdout="skipped",
                stderr="",
            )

        env_path = "/home/rari/Sapphire/services/bot-lighter/.env"
        updates_json = json.dumps(overrides, separators=(",", ":"))
        remote_script = (
            "python3 - <<'PY'\n"
            "from pathlib import Path\n"
            "import json\n"
            f"env_file = Path('{env_path}')\n"
            f"updates = json.loads('''{updates_json}''')\n"
            "lines = env_file.read_text().splitlines() if env_file.exists() else []\n"
            "out = []\n"
            "seen = set()\n"
            "for ln in lines:\n"
            "    if '=' in ln and not ln.strip().startswith('#'):\n"
            "        k, _ = ln.split('=', 1)\n"
            "        key = k.strip()\n"
            "        if key in updates:\n"
            "            out.append(f\"{key}={updates[key]}\")\n"
            "            seen.add(key)\n"
            "            continue\n"
            "    out.append(ln)\n"
            "for key, value in updates.items():\n"
            "    if key not in seen:\n"
            "        out.append(f\"{key}={value}\")\n"
            "env_file.write_text('\\n'.join(out) + '\\n')\n"
            "print(f'Updated {env_file}')\n"
            "for key in sorted(updates):\n"
            "    print(f'{key}={updates[key]}')\n"
            "PY"
        )
        set_result = self._run(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=10",
                target_host,
                remote_script,
            ],
            cwd=REPO_ROOT,
            env=os.environ.copy(),
        )
        if not set_result.ok:
            return set_result

        restart_result = self._run(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=10",
                target_host,
                (
                    "sudo systemctl restart lighter-trading && "
                    "sleep 6 && "
                    "systemctl is-active lighter-trading && "
                    "systemctl show lighter-trading -p ActiveState -p SubState -p MainPID"
                ),
            ],
            cwd=REPO_ROOT,
            env=os.environ.copy(),
        )
        merged_stdout = "\n".join(
            part for part in [set_result.stdout, restart_result.stdout] if part
        )
        merged_stderr = "\n".join(
            part for part in [set_result.stderr, restart_result.stderr] if part
        )
        merged = CommandResult(
            ok=restart_result.ok,
            returncode=restart_result.returncode,
            cmd=restart_result.cmd,
            stdout=merged_stdout,
            stderr=merged_stderr,
        )
        self._event(
            "remote_overrides_applied",
            {
                "target_host": target_host,
                "override_keys": sorted(list(overrides.keys())),
                "ok": merged.ok,
                "returncode": merged.returncode,
            },
        )
        return merged

    def _fetch_remote_env_values(
        self,
        *,
        target_host: str,
        keys: list[str],
    ) -> dict[str, str]:
        filtered = [str(k).strip() for k in keys if str(k).strip()]
        if not filtered:
            return {}
        keys_json = json.dumps(filtered, separators=(",", ":"))
        env_path = "/home/rari/Sapphire/services/bot-lighter/.env"
        remote_script = (
            "python3 - <<'PY'\n"
            "from pathlib import Path\n"
            "import json\n"
            f"keys = json.loads('''{keys_json}''')\n"
            f"env_file = Path('{env_path}')\n"
            "values = {k: '' for k in keys}\n"
            "if env_file.exists():\n"
            "  for raw in env_file.read_text(encoding='utf-8', errors='ignore').splitlines():\n"
            "    line = raw.strip()\n"
            "    if not line or line.startswith('#') or '=' not in line:\n"
            "      continue\n"
            "    key, value = line.split('=', 1)\n"
            "    key = key.strip()\n"
            "    if key in values:\n"
            "      values[key] = value.strip().strip('\"').strip(\"'\")\n"
            "for key in keys:\n"
            "  print(f'{key}={values.get(key, \"\")}')\n"
            "PY"
        )
        result = self._run(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=10",
                target_host,
                remote_script,
            ],
            cwd=REPO_ROOT,
            env=os.environ.copy(),
        )
        values: dict[str, str] = {}
        if not result.ok:
            return values
        for raw in (result.stdout or "").splitlines():
            line = raw.strip()
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
        return values

    def _runtime_convergence_check(
        self,
        *,
        target_host: str,
        effective_settings: dict[str, Any],
    ) -> dict[str, Any]:
        expected = {str(k): str(v) for k, v in (effective_settings or {}).items()}
        keys = sorted(list(expected.keys()))
        actual = self._fetch_remote_env_values(target_host=target_host, keys=keys)
        mismatches: list[dict[str, str]] = []
        missing: list[str] = []
        for key in keys:
            exp = expected.get(key, "")
            got = actual.get(key)
            if got is None:
                missing.append(key)
                continue
            if str(got) != str(exp):
                mismatches.append({"key": key, "expected": str(exp), "actual": str(got)})

        service_state = self._run(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=8",
                target_host,
                f"systemctl is-active {DEFAULT_SERVICE}",
            ],
            cwd=REPO_ROOT,
            env=os.environ.copy(),
        )
        service_active = service_state.ok and str(service_state.stdout or "").strip() == "active"
        ok = service_active and not missing and not mismatches
        return {
            "ok": ok,
            "target_host": target_host,
            "service_active": service_active,
            "service_status": str(service_state.stdout or "").strip(),
            "missing_keys": missing,
            "mismatches": mismatches,
            "checked_keys": keys,
        }

    @staticmethod
    def _effective_overrides_for_profile(
        profile: str,
        effective_settings: dict[str, str],
    ) -> dict[str, str]:
        base = PROFILE_SETTINGS.get(profile, {})
        overrides: dict[str, str] = {}
        for key, value in (effective_settings or {}).items():
            val = str(value)
            if str(base.get(key, "")) != val:
                overrides[str(key)] = val
        return overrides

    def _load_applied_history(self, *, limit: int = 50) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for doc in self.db.collection(APPLIED_HISTORY_COLLECTION).stream():
            row = doc.to_dict() or {}
            row["_id"] = doc.id
            rows.append(row)
        rows.sort(
            key=lambda r: str(r.get("applied_at_iso") or ""),
            reverse=True,
        )
        return rows[: max(1, int(limit))]

    def _build_desired_state(
        self,
        *,
        profile: str,
        target_host: str,
        run_test: bool,
        close_after_test: bool,
        test_quantity: str,
        notes: str,
        overrides: dict[str, str],
        requested_by: str,
        desired_version: str | None = None,
    ) -> dict[str, Any]:
        desired_version = desired_version or f"{_utc_now().strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
        base = dict(PROFILE_SETTINGS.get(profile, {}))
        effective = dict(base)
        effective.update(overrides)
        state = {
            "platform": PLATFORM,
            "service": DEFAULT_SERVICE,
            "target_host": target_host,
            "profile": profile,
            "profile_settings": base,
            "overrides": overrides,
            "effective_settings": effective,
            "desired_version": desired_version,
            "requested_at": _utc_now(),
            "requested_at_iso": _utc_now_iso(),
            "requested_by": requested_by,
            "run_test": bool(run_test),
            "close_after_test": bool(close_after_test),
            "test_quantity": str(test_quantity),
            "notes": notes.strip(),
            "state": "pending_apply",
        }
        return state

    def apply(
        self,
        *,
        profile: str,
        target_host: str,
        run_test: bool,
        close_after_test: bool,
        test_quantity: str,
        notes: str,
        overrides: dict[str, str],
        requested_by: str,
        desired_version: str | None = None,
        update_desired: bool = True,
        no_restart: bool = False,
        enforce_lane_health: bool = True,
        auto_failover: bool = True,
    ) -> dict[str, Any]:
        desired = self._build_desired_state(
            profile=profile,
            target_host=target_host,
            run_test=run_test,
            close_after_test=close_after_test,
            test_quantity=test_quantity,
            notes=notes,
            overrides=overrides,
            requested_by=requested_by,
            desired_version=desired_version,
        )

        desired_ref = self.db.collection(DESIRED_COLLECTION).document(PLATFORM)
        applied_ref = self.db.collection(APPLIED_COLLECTION).document(PLATFORM)

        if update_desired:
            desired_ref.set(desired)
            self._event("desired_state_updated", {"desired_version": desired["desired_version"], **desired})

        selected_target_host = target_host
        lane_decision: dict[str, Any] = {}
        runtime_overrides = {str(k): str(v) for k, v in overrides.items()}
        if not no_restart:
            selected_target_host, lane_decision = self._select_target_host(
                requested_target_host=target_host,
                run_test=run_test,
                enforce_lane_health=enforce_lane_health,
                auto_failover=auto_failover,
            )
            self._event(
                "lane_selection",
                {
                    "desired_version": desired["desired_version"],
                    "requested_target_host": target_host,
                    "selected_target_host": selected_target_host,
                    "failover_used": bool(lane_decision.get("failover_used", False)),
                    "reason": lane_decision.get("reason", ""),
                },
            )
            if selected_target_host != target_host:
                failover_sources = str(
                    os.getenv(
                        "SAPPHIRECTL_FAILOVER_ALLOWED_SIGNAL_SOURCES",
                        "codex-unified-prod-test,sapphirectl-canary",
                    )
                ).strip()
                if failover_sources and not str(runtime_overrides.get("LIGHTER_ALLOWED_SIGNAL_SOURCES", "")).strip():
                    runtime_overrides["LIGHTER_ALLOWED_SIGNAL_SOURCES"] = failover_sources
                    desired["overrides"] = dict(runtime_overrides)
                    desired["effective_settings"] = self._effective_overrides_for_profile(profile, runtime_overrides)
                    if update_desired:
                        desired_ref.set(
                            {
                                "overrides": desired["overrides"],
                                "effective_settings": desired["effective_settings"],
                                "updated_at": _utc_now(),
                                "updated_at_iso": _utc_now_iso(),
                            },
                            merge=True,
                        )
                    self._event(
                        "failover_source_allowlist_enforced",
                        {
                            "desired_version": desired["desired_version"],
                            "requested_target_host": target_host,
                            "selected_target_host": selected_target_host,
                            "allowed_sources": failover_sources,
                        },
                    )

        if no_restart:
            skipped = CommandResult(
                ok=True,
                returncode=0,
                cmd=[],
                stdout="skipped_no_restart",
                stderr="",
            )
            applied_payload: dict[str, Any] = {
                "platform": PLATFORM,
                "service": DEFAULT_SERVICE,
                "target_host": target_host,
                "selected_target_host": selected_target_host,
                "profile": profile,
                "desired_version": desired["desired_version"],
                "applied_at": _utc_now(),
                "applied_at_iso": _utc_now_iso(),
                "requested_by": requested_by,
                "status": "staged_no_restart",
                "run_test": run_test,
                "close_after_test": close_after_test,
                "test_quantity": str(test_quantity),
                "effective_settings": desired["effective_settings"],
                "deploy": skipped.to_dict(),
                "primary_disarm": skipped.to_dict(),
                "override_apply": skipped.to_dict(),
                "runtime_convergence": {
                    "ok": True,
                    "target_host": selected_target_host,
                    "service_active": None,
                    "service_status": "skipped_no_restart",
                    "missing_keys": [],
                    "mismatches": [],
                    "checked_keys": [],
                },
                "test": skipped.to_dict(),
                "close": skipped.to_dict(),
                "lane_decision": lane_decision,
            }
            applied_ref.set(applied_payload)
            history_id = f"{_utc_now().strftime('%Y%m%dT%H%M%SZ')}_{desired['desired_version']}"
            self.db.collection(APPLIED_HISTORY_COLLECTION).document(history_id).set(applied_payload)
            desired_ref.set(
                {
                    "state": "staged_no_restart",
                    "last_apply_at": _utc_now(),
                    "last_apply_at_iso": _utc_now_iso(),
                    "last_apply_status": "staged_no_restart",
                },
                merge=True,
            )
            self._event(
                "desired_state_staged_no_restart",
                {
                    "desired_version": desired["desired_version"],
                    "profile": profile,
                    "target_host": target_host,
                    "run_test": run_test,
                },
            )
            return {
                "desired": desired,
                "applied": applied_payload,
            }

        primary_disarm_result = CommandResult(
            ok=True,
            returncode=0,
            cmd=[],
            stdout="skipped",
            stderr="",
        )
        if selected_target_host != target_host:
            primary_disarm_result = self._apply_overrides_remote(
                target_host=target_host,
                overrides={
                    "TRADING_ENABLED": "0",
                    "ALLOW_LIVE_TRADING": "0",
                },
            )
            self._event(
                "primary_host_disarmed_for_failover",
                {
                    "desired_version": desired["desired_version"],
                    "primary_target_host": target_host,
                    "selected_target_host": selected_target_host,
                    "ok": primary_disarm_result.ok,
                    "returncode": primary_disarm_result.returncode,
                },
            )

        deploy = self._run(
            [str(DEPLOY_SCRIPT), profile, selected_target_host],
            cwd=REPO_ROOT,
            env={**os.environ, "PROJECT_ID": self.project},
        )

        override_apply_result = self._apply_overrides_remote(
            target_host=selected_target_host,
            overrides=runtime_overrides,
        ) if (primary_disarm_result.ok and deploy.ok) else CommandResult(
            ok=False,
            returncode=1,
            cmd=[],
            stdout="skipped_due_to_primary_disarm_or_deploy_failure",
            stderr="",
        )

        runtime_convergence = {
            "ok": True,
            "target_host": selected_target_host,
            "service_active": None,
            "service_status": "skipped",
            "missing_keys": [],
            "mismatches": [],
            "checked_keys": [],
        }
        if primary_disarm_result.ok and deploy.ok and override_apply_result.ok:
            runtime_convergence = self._runtime_convergence_check(
                target_host=selected_target_host,
                effective_settings=desired["effective_settings"],
            )

        test_result = CommandResult(
            ok=True,
            returncode=0,
            cmd=[],
            stdout="skipped",
            stderr="",
        )
        lane_health: dict[str, Any] = lane_decision.get("primary_lane_health", {}) if lane_decision else {}
        if primary_disarm_result.ok and deploy.ok and override_apply_result.ok and run_test:
            if not runtime_convergence.get("ok", False):
                test_result = CommandResult(
                    ok=False,
                    returncode=4,
                    cmd=["runtime-convergence-check"],
                    stdout=json.dumps(runtime_convergence, default=str, separators=(",", ":")),
                    stderr="runtime_not_converged",
                )
            
        if primary_disarm_result.ok and deploy.ok and override_apply_result.ok and run_test and test_result.ok:
            if selected_target_host != target_host:
                lane_health = self._lane_health(
                    target_host=selected_target_host,
                    lookback_minutes=int(os.getenv("SAPPHIRECTL_LANE_LOOKBACK_MINUTES", "45")),
                )
            self._event(
                "lane_health_pretest",
                {
                    "desired_version": desired["desired_version"],
                    "target_host": selected_target_host,
                    "healthy": bool(lane_health.get("healthy", False)),
                    "reasons": lane_health.get("reasons", []),
                    "warnings": lane_health.get("warnings", []),
                },
            )
            if enforce_lane_health and not bool(lane_health.get("healthy", False)):
                test_result = CommandResult(
                    ok=False,
                    returncode=3,
                    cmd=["lane-health-check"],
                    stdout=json.dumps(lane_health, default=str, separators=(",", ":")),
                    stderr="lane_unhealthy",
                )
            else:
                strategy_list = str(desired["effective_settings"].get("LIGHTER_ALLOWED_STRATEGIES", "")).split(",")
                timeframe_list = str(desired["effective_settings"].get("LIGHTER_ALLOWED_TIMEFRAMES", "")).split(",")
                strategy = (strategy_list[0].strip() if strategy_list and strategy_list[0].strip() else "luxalgo_msb_ob")
                timeframe = (timeframe_list[0].strip() if timeframe_list and timeframe_list[0].strip() else "5m")
                test_env = {
                    **os.environ,
                    "PROJECT_ID": self.project,
                    "REGION": os.getenv("REGION", "us-central1"),
                    "STRATEGY": strategy,
                    "TIMEFRAME": timeframe,
                    "QUANTITY": str(test_quantity),
                    "WAIT_SECONDS": os.getenv("SAPPHIRECTL_TEST_WAIT_SECONDS", "150"),
                }
                test_result = self._run([str(TEST_SCRIPT)], cwd=REPO_ROOT, env=test_env)

        close_result = CommandResult(
            ok=True,
            returncode=0,
            cmd=[],
            stdout="skipped",
            stderr="",
        )
        if primary_disarm_result.ok and deploy.ok and override_apply_result.ok and run_test and close_after_test and test_result.ok:
            close_result = self._close_all_positions(target_host=selected_target_host)

        status = (
            "applied"
            if (
                primary_disarm_result.ok
                and deploy.ok
                and override_apply_result.ok
                and bool(runtime_convergence.get("ok", False))
                and test_result.ok
                and close_result.ok
            )
            else "failed"
        )
        applied_payload: dict[str, Any] = {
            "platform": PLATFORM,
            "service": DEFAULT_SERVICE,
            "target_host": target_host,
            "selected_target_host": selected_target_host,
            "profile": profile,
            "desired_version": desired["desired_version"],
            "applied_at": _utc_now(),
            "applied_at_iso": _utc_now_iso(),
            "requested_by": requested_by,
            "status": status,
            "run_test": run_test,
            "close_after_test": close_after_test,
            "test_quantity": str(test_quantity),
            "effective_settings": desired["effective_settings"],
            "deploy": deploy.to_dict(),
            "primary_disarm": primary_disarm_result.to_dict(),
            "override_apply": override_apply_result.to_dict(),
            "runtime_convergence": runtime_convergence,
            "test": test_result.to_dict(),
            "close": close_result.to_dict(),
            "lane_health_pretest": lane_health,
            "lane_decision": lane_decision,
        }
        applied_ref.set(applied_payload)
        history_id = f"{_utc_now().strftime('%Y%m%dT%H%M%SZ')}_{desired['desired_version']}"
        self.db.collection(APPLIED_HISTORY_COLLECTION).document(history_id).set(applied_payload)

        desired_update = {
            "state": "applied" if status == "applied" else "apply_failed",
            "last_apply_at": _utc_now(),
            "last_apply_at_iso": _utc_now_iso(),
            "last_apply_status": status,
        }
        desired_ref.set(desired_update, merge=True)

        self._event(
            "desired_state_applied",
            {
                "desired_version": desired["desired_version"],
                "status": status,
                "profile": profile,
                "target_host": selected_target_host,
                "run_test": run_test,
            },
        )
        return {
            "desired": desired,
            "applied": applied_payload,
        }

    def promote(
        self,
        *,
        to_stage: str,
        target_host: str,
        requested_by: str,
        profile_override: str | None,
        test_quantity_override: str | None,
        run_test_override: bool | None,
        close_after_test_override: bool | None,
        notes: str,
        extra_overrides: dict[str, str],
        no_restart: bool,
        enforce_lane_health: bool = True,
        auto_failover: bool = True,
    ) -> dict[str, Any]:
        stage_cfg = PROMOTION_STAGES.get(to_stage)
        if not stage_cfg:
            raise ValueError(f"Unknown promotion stage: {to_stage}")

        profile = profile_override or str(stage_cfg["profile"])
        run_test = bool(stage_cfg["run_test"]) if run_test_override is None else bool(run_test_override)
        close_after_test = (
            bool(stage_cfg.get("close_after_test", False))
            if close_after_test_override is None
            else bool(close_after_test_override)
        )
        test_quantity = test_quantity_override or str(stage_cfg["test_quantity"])

        merged_overrides = dict(stage_cfg.get("overrides", {}))
        merged_overrides.update(extra_overrides)
        note = notes.strip() or f"promote_to_{to_stage}"

        result = self.apply(
            profile=profile,
            target_host=target_host,
            run_test=run_test,
            close_after_test=close_after_test,
            test_quantity=test_quantity,
            notes=note,
            overrides=merged_overrides,
            requested_by=requested_by,
            no_restart=no_restart,
            enforce_lane_health=enforce_lane_health,
            auto_failover=auto_failover,
        )
        desired_ref = self.db.collection(DESIRED_COLLECTION).document(PLATFORM)
        desired_ref.set(
            {
                "stage": to_stage,
                "last_promoted_at": _utc_now(),
                "last_promoted_at_iso": _utc_now_iso(),
                "last_promoted_by": requested_by,
            },
            merge=True,
        )
        self._event(
            "stage_promoted",
            {
                "to_stage": to_stage,
                "profile": profile,
                "run_test": run_test,
                "close_after_test": close_after_test,
                "target_host": target_host,
                "status": (result.get("applied") or {}).get("status"),
            },
        )
        return {"stage": to_stage, "result": result}

    def rollback(
        self,
        *,
        steps: int,
        target_host: str,
        requested_by: str,
        run_test: bool,
        close_after_test: bool,
        test_quantity: str,
        notes: str,
        no_restart: bool,
        enforce_lane_health: bool = True,
        auto_failover: bool = True,
    ) -> dict[str, Any]:
        steps = max(1, int(steps))
        history = [
            row for row in self._load_applied_history(limit=120)
            if str(row.get("status", "")).lower() == "applied"
        ]
        if len(history) <= steps:
            raise RuntimeError(
                f"Rollback needs at least {steps + 1} applied history records; found {len(history)}"
            )
        target = history[steps]
        profile = str(target.get("profile") or "luxalgo_sol_5m_active")
        effective = target.get("effective_settings") or {}
        if not isinstance(effective, dict):
            effective = {}
        overrides = self._effective_overrides_for_profile(profile, {str(k): str(v) for k, v in effective.items()})
        note = notes.strip() or f"rollback_to_{target.get('desired_version', 'unknown')}"
        result = self.apply(
            profile=profile,
            target_host=target_host,
            run_test=run_test,
            close_after_test=close_after_test,
            test_quantity=test_quantity,
            notes=note,
            overrides=overrides,
            requested_by=requested_by,
            no_restart=no_restart,
            enforce_lane_health=enforce_lane_health,
            auto_failover=auto_failover,
        )
        self._event(
            "rollback_applied",
            {
                "rollback_steps": steps,
                "rolled_back_to_desired_version": target.get("desired_version"),
                "target_host": target_host,
                "status": (result.get("applied") or {}).get("status"),
            },
        )
        return {
            "rollback_steps": steps,
            "target_history_record": target,
            "result": result,
        }

    def lane_check(
        self,
        *,
        target_host: str,
        run_test: bool,
        enforce_lane_health: bool,
        auto_failover: bool,
    ) -> dict[str, Any]:
        selected_target_host, lane_decision = self._select_target_host(
            requested_target_host=target_host,
            run_test=run_test,
            enforce_lane_health=enforce_lane_health,
            auto_failover=auto_failover,
        )
        return {
            "requested_target_host": target_host,
            "selected_target_host": selected_target_host,
            "failover_used": bool(lane_decision.get("failover_used", False)),
            "lane_decision": lane_decision,
        }

    def status(self) -> dict[str, Any]:
        desired = self.db.collection(DESIRED_COLLECTION).document(PLATFORM).get().to_dict() or {}
        applied = self.db.collection(APPLIED_COLLECTION).document(PLATFORM).get().to_dict() or {}
        live_position = self.db.collection("live_positions").document(PLATFORM).get().to_dict() or {}
        history = self._load_applied_history(limit=5)
        target_host = desired.get("target_host", DEFAULT_HOST)
        lane_health = self._lane_health(
            target_host=target_host,
            lookback_minutes=int(os.getenv("SAPPHIRECTL_LANE_LOOKBACK_MINUTES", "45")),
        )

        systemctl = self._run(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=8",
                target_host,
                f"systemctl show {DEFAULT_SERVICE} -p ActiveState -p SubState -p MainPID",
            ],
            cwd=REPO_ROOT,
            env=os.environ.copy(),
        )
        return {
            "platform": PLATFORM,
            "project": self.project,
            "desired": desired,
            "applied": applied,
            "applied_history": history,
            "live_positions": {
                "position_count": live_position.get("position_count"),
                "updated_at": str(live_position.get("updated_at")),
                "positions": live_position.get("positions", []),
            },
            "service_state": {
                "ok": systemctl.ok,
                "output": _short_output(systemctl.combined_output, limit=1200),
            },
            "lane_health": lane_health,
            "configured_failover_hosts": self._configured_failover_hosts(),
        }

    def reconcile(
        self,
        *,
        requested_by: str,
        no_restart: bool = False,
        enforce_lane_health: bool = True,
        auto_failover: bool = True,
    ) -> dict[str, Any]:
        desired = self.db.collection(DESIRED_COLLECTION).document(PLATFORM).get().to_dict() or {}
        applied = self.db.collection(APPLIED_COLLECTION).document(PLATFORM).get().to_dict() or {}
        if not desired:
            raise RuntimeError("No desired state found for lighter")
        desired_version = str(desired.get("desired_version", "") or "").strip()
        applied_version = str(applied.get("desired_version", "") or "").strip()
        applied_status = str(applied.get("status", "") or "").strip().lower()
        if desired_version and desired_version == applied_version and applied_status == "applied":
            if bool(no_restart):
                return {
                    "reconciled": False,
                    "reason": "already_converged",
                    "desired_version": desired_version,
                    "applied_version": applied_version,
                }
            target_host = str(applied.get("selected_target_host") or desired.get("target_host") or DEFAULT_HOST)
            expected_settings = desired.get("effective_settings") if isinstance(desired.get("effective_settings"), dict) else {}
            runtime_convergence = self._runtime_convergence_check(
                target_host=target_host,
                effective_settings=expected_settings,
            )
            if runtime_convergence.get("ok", False):
                return {
                    "reconciled": False,
                    "reason": "already_converged",
                    "desired_version": desired_version,
                    "applied_version": applied_version,
                    "runtime_convergence": runtime_convergence,
                }
            self._event(
                "runtime_drift_detected",
                {
                    "desired_version": desired_version,
                    "applied_version": applied_version,
                    "target_host": target_host,
                    "runtime_convergence": runtime_convergence,
                },
            )

        profile = str(desired.get("profile") or "luxalgo_sol_5m_active")
        target_host = str(desired.get("target_host") or DEFAULT_HOST)
        run_test = bool(desired.get("run_test", True))
        close_after_test = bool(desired.get("close_after_test", False))
        test_quantity = str(desired.get("test_quantity") or "0.005")
        notes = str(desired.get("notes") or "")
        overrides = desired.get("overrides") or {}
        if not isinstance(overrides, dict):
            overrides = {}

        result = self.apply(
            profile=profile,
            target_host=target_host,
            run_test=run_test,
            close_after_test=close_after_test,
            test_quantity=test_quantity,
            notes=notes,
            overrides={str(k): str(v) for k, v in overrides.items()},
            requested_by=requested_by,
            desired_version=desired_version or None,
            update_desired=False,
            no_restart=no_restart,
            enforce_lane_health=enforce_lane_health,
            auto_failover=auto_failover,
        )
        return {
            "reconciled": True,
            "desired_version": desired_version,
            "result": result,
        }


def _json_print(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, default=str))


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Sapphire control-plane CLI")
    p.add_argument("--project", default=PROJECT_ID, help="GCP project id")
    p.add_argument("--requested-by", default=os.getenv("USER", "codex"), help="Audit actor id")

    sub = p.add_subparsers(dest="command", required=True)

    apply_p = sub.add_parser("apply", help="Set desired state and apply profile")
    apply_p.add_argument(
        "--profile",
        default="luxalgo_sol_5m_active",
        choices=sorted(PROFILE_SETTINGS.keys()),
    )
    apply_p.add_argument("--target-host", default=DEFAULT_HOST)
    apply_p.add_argument("--notes", default="")
    apply_p.add_argument("--override", action="append", default=[], help="KEY=VALUE")
    apply_p.add_argument("--no-test", action="store_true", help="Skip unified canary test")
    apply_p.add_argument(
        "--close-after-test",
        action="store_true",
        help="After successful test canary, request CLOSE_ALL on the local execution gateway.",
    )
    apply_p.add_argument(
        "--no-restart",
        action="store_true",
        help="Stage desired state only; skip deploy/restart/test/close operations.",
    )
    apply_p.add_argument(
        "--skip-lane-health-check",
        action="store_true",
        help="Bypass pre-test lane health guard and run canary test anyway.",
    )
    apply_p.add_argument(
        "--disable-auto-failover",
        action="store_true",
        help="Disable host failover when the requested lane is unhealthy.",
    )
    apply_p.add_argument("--test-quantity", default="0.005")

    promote_p = sub.add_parser("promote", help="Promote runtime stage (paper/canary/live)")
    promote_p.add_argument("--to", required=True, choices=sorted(PROMOTION_STAGES.keys()))
    promote_p.add_argument("--target-host", default=DEFAULT_HOST)
    promote_p.add_argument(
        "--profile",
        choices=sorted(PROFILE_SETTINGS.keys()),
        default="",
        help="Optional profile override for the stage",
    )
    promote_p.add_argument("--override", action="append", default=[], help="KEY=VALUE")
    promote_p.add_argument("--notes", default="")
    promote_p.add_argument("--test-quantity", default="")
    promote_p.add_argument(
        "--skip-test",
        action="store_true",
        help="Override stage default and skip canary test",
    )
    promote_p.add_argument(
        "--close-after-test",
        action="store_true",
        help="Force CLOSE_ALL after successful test (overrides stage default).",
    )
    promote_p.add_argument(
        "--no-close-after-test",
        action="store_true",
        help="Disable CLOSE_ALL post-test even if stage default enables it.",
    )
    promote_p.add_argument(
        "--no-restart",
        action="store_true",
        help="Stage desired state only; skip runtime changes.",
    )
    promote_p.add_argument(
        "--skip-lane-health-check",
        action="store_true",
        help="Bypass pre-test lane health guard for stage apply.",
    )
    promote_p.add_argument(
        "--disable-auto-failover",
        action="store_true",
        help="Disable host failover when selected stage lane is unhealthy.",
    )

    rollback_p = sub.add_parser("rollback", help="Rollback to a previous applied state")
    rollback_p.add_argument("--steps", type=int, default=1, help="How many applied versions back")
    rollback_p.add_argument("--target-host", default=DEFAULT_HOST)
    rollback_p.add_argument("--notes", default="")
    rollback_p.add_argument("--test-quantity", default="0.002")
    rollback_p.add_argument("--skip-test", action="store_true")
    rollback_p.add_argument("--close-after-test", action="store_true")
    rollback_p.add_argument(
        "--no-restart",
        action="store_true",
        help="Stage desired rollback state only; skip runtime changes.",
    )
    rollback_p.add_argument(
        "--skip-lane-health-check",
        action="store_true",
        help="Bypass pre-test lane health guard for rollback apply.",
    )
    rollback_p.add_argument(
        "--disable-auto-failover",
        action="store_true",
        help="Disable host failover during rollback apply.",
    )

    sub.add_parser("status", help="Show desired/applied/live status")
    reconcile_p = sub.add_parser("reconcile", help="Apply desired state if not converged")
    reconcile_p.add_argument(
        "--no-restart",
        action="store_true",
        help="Stage desired state only; skip runtime changes.",
    )
    reconcile_p.add_argument(
        "--skip-lane-health-check",
        action="store_true",
        help="Bypass pre-test lane health guard during reconcile.",
    )
    reconcile_p.add_argument(
        "--disable-auto-failover",
        action="store_true",
        help="Disable host failover during reconcile apply.",
    )

    lane_p = sub.add_parser("lane-check", help="Evaluate lane health/failover selection without applying runtime changes")
    lane_p.add_argument("--target-host", default=DEFAULT_HOST)
    lane_p.add_argument(
        "--no-run-test",
        action="store_true",
        help="Simulate run_test=false (disables failover host selection).",
    )
    lane_p.add_argument(
        "--skip-lane-health-check",
        action="store_true",
        help="Disable lane-health enforcement for this check.",
    )
    lane_p.add_argument(
        "--disable-auto-failover",
        action="store_true",
        help="Disable host failover when the requested lane is unhealthy.",
    )
    return p


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    ctl = SapphireCtl(project=args.project)

    if args.command == "apply":
        overrides = _parse_overrides(args.override)
        out = ctl.apply(
            profile=args.profile,
            target_host=args.target_host,
            run_test=not args.no_test,
            close_after_test=bool(args.close_after_test),
            test_quantity=args.test_quantity,
            notes=args.notes,
            overrides=overrides,
            requested_by=args.requested_by,
            no_restart=bool(args.no_restart),
            enforce_lane_health=not bool(args.skip_lane_health_check),
            auto_failover=not bool(args.disable_auto_failover),
        )
        _json_print(out)
        return 0 if out["applied"]["status"] in {"applied", "staged_no_restart"} else 2

    if args.command == "promote":
        if args.close_after_test and args.no_close_after_test:
            raise SystemExit("Cannot set both --close-after-test and --no-close-after-test")
        close_after_test_override = None
        if args.close_after_test:
            close_after_test_override = True
        elif args.no_close_after_test:
            close_after_test_override = False
        run_test_override = None if not args.skip_test else False
        out = ctl.promote(
            to_stage=args.to,
            target_host=args.target_host,
            requested_by=args.requested_by,
            profile_override=args.profile or None,
            test_quantity_override=args.test_quantity or None,
            run_test_override=run_test_override,
            close_after_test_override=close_after_test_override,
            notes=args.notes,
            extra_overrides=_parse_overrides(args.override),
            no_restart=bool(args.no_restart),
            enforce_lane_health=not bool(args.skip_lane_health_check),
            auto_failover=not bool(args.disable_auto_failover),
        )
        _json_print(out)
        status = (((out.get("result") or {}).get("applied") or {}).get("status") or "").lower()
        return 0 if status in {"applied", "staged_no_restart"} else 2

    if args.command == "rollback":
        out = ctl.rollback(
            steps=args.steps,
            target_host=args.target_host,
            requested_by=args.requested_by,
            run_test=not args.skip_test,
            close_after_test=bool(args.close_after_test),
            test_quantity=args.test_quantity,
            notes=args.notes,
            no_restart=bool(args.no_restart),
            enforce_lane_health=not bool(args.skip_lane_health_check),
            auto_failover=not bool(args.disable_auto_failover),
        )
        _json_print(out)
        status = (((out.get("result") or {}).get("applied") or {}).get("status") or "").lower()
        return 0 if status in {"applied", "staged_no_restart"} else 2

    if args.command == "status":
        _json_print(ctl.status())
        return 0

    if args.command == "lane-check":
        out = ctl.lane_check(
            target_host=args.target_host,
            run_test=not bool(args.no_run_test),
            enforce_lane_health=not bool(args.skip_lane_health_check),
            auto_failover=not bool(args.disable_auto_failover),
        )
        _json_print(out)
        return 0

    if args.command == "reconcile":
        out = ctl.reconcile(
            requested_by=args.requested_by,
            no_restart=bool(args.no_restart),
            enforce_lane_health=not bool(args.skip_lane_health_check),
            auto_failover=not bool(args.disable_auto_failover),
        )
        _json_print(out)
        if out.get("reconciled"):
            status = (((out.get("result") or {}).get("applied") or {}).get("status") or "").lower()
            return 0 if status in {"applied", "staged_no_restart"} else 2
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
