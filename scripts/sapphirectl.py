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
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from google.cloud import firestore


PROJECT_ID = os.getenv("PROJECT_ID", "sapphire-479610")
PLATFORM = "lighter"
DEFAULT_HOST = "rari@100.87.225.89"
DEFAULT_SERVICE = "lighter-trading"

REPO_ROOT = Path(__file__).resolve().parents[1]
DEPLOY_SCRIPT = REPO_ROOT / "scripts" / "deploy_lighter_strategy_profile.sh"
TEST_SCRIPT = REPO_ROOT / "scripts" / "run_unified_lighter_prod_test.sh"

DESIRED_COLLECTION = "control_plane_desired"
APPLIED_COLLECTION = "control_plane_applied"
APPLIED_HISTORY_COLLECTION = "control_plane_applied_history"
EVENTS_COLLECTION = "control_plane_events"


PROFILE_SETTINGS: Dict[str, Dict[str, str]] = {
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
}

PROMOTION_STAGES: Dict[str, Dict[str, Any]] = {
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
        "test_quantity": "0.002",
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
        "test_quantity": "0.003",
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
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().isoformat()


def _short_output(text: str, limit: int = 8000) -> str:
    if len(text) <= limit:
        return text
    return text[-limit:]


def _parse_overrides(items: List[str]) -> Dict[str, str]:
    overrides: Dict[str, str] = {}
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


@dataclass
class CommandResult:
    ok: bool
    returncode: int
    cmd: List[str]
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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "returncode": self.returncode,
            "cmd": self.cmd,
            "output": _short_output(self.combined_output),
        }


class SapphireCtl:
    def __init__(self, project: str):
        self.project = project
        self.db = firestore.Client(project=project)

    def _event(self, event_type: str, payload: Dict[str, Any]) -> None:
        body = {
            "timestamp": _utc_now(),
            "timestamp_iso": _utc_now_iso(),
            "event_type": event_type,
            "platform": PLATFORM,
            "payload": payload,
        }
        self.db.collection(EVENTS_COLLECTION).document().set(body)

    @staticmethod
    def _run(cmd: List[str], *, cwd: Path, env: Dict[str, str] | None = None) -> CommandResult:
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
        overrides: Dict[str, str],
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

    @staticmethod
    def _effective_overrides_for_profile(
        profile: str,
        effective_settings: Dict[str, str],
    ) -> Dict[str, str]:
        base = PROFILE_SETTINGS.get(profile, {})
        overrides: Dict[str, str] = {}
        for key, value in (effective_settings or {}).items():
            val = str(value)
            if str(base.get(key, "")) != val:
                overrides[str(key)] = val
        return overrides

    def _load_applied_history(self, *, limit: int = 50) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
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
        overrides: Dict[str, str],
        requested_by: str,
        desired_version: str | None = None,
    ) -> Dict[str, Any]:
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
        overrides: Dict[str, str],
        requested_by: str,
        desired_version: str | None = None,
        update_desired: bool = True,
    ) -> Dict[str, Any]:
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

        deploy = self._run(
            [str(DEPLOY_SCRIPT), profile, target_host],
            cwd=REPO_ROOT,
            env={**os.environ, "PROJECT_ID": self.project},
        )

        override_apply_result = self._apply_overrides_remote(
            target_host=target_host,
            overrides=overrides,
        ) if deploy.ok else CommandResult(
            ok=False,
            returncode=1,
            cmd=[],
            stdout="skipped_due_to_deploy_failure",
            stderr="",
        )

        test_result = CommandResult(
            ok=True,
            returncode=0,
            cmd=[],
            stdout="skipped",
            stderr="",
        )
        if deploy.ok and override_apply_result.ok and run_test:
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
        if deploy.ok and override_apply_result.ok and run_test and close_after_test and test_result.ok:
            close_result = self._close_all_positions(target_host=target_host)

        status = (
            "applied"
            if deploy.ok and override_apply_result.ok and test_result.ok and close_result.ok
            else "failed"
        )
        applied_payload: Dict[str, Any] = {
            "platform": PLATFORM,
            "service": DEFAULT_SERVICE,
            "target_host": target_host,
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
            "override_apply": override_apply_result.to_dict(),
            "test": test_result.to_dict(),
            "close": close_result.to_dict(),
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
                "target_host": target_host,
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
        extra_overrides: Dict[str, str],
    ) -> Dict[str, Any]:
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
    ) -> Dict[str, Any]:
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

    def status(self) -> Dict[str, Any]:
        desired = self.db.collection(DESIRED_COLLECTION).document(PLATFORM).get().to_dict() or {}
        applied = self.db.collection(APPLIED_COLLECTION).document(PLATFORM).get().to_dict() or {}
        live_position = self.db.collection("live_positions").document(PLATFORM).get().to_dict() or {}
        history = self._load_applied_history(limit=5)

        systemctl = self._run(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=8",
                desired.get("target_host", DEFAULT_HOST),
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
        }

    def reconcile(self, *, requested_by: str) -> Dict[str, Any]:
        desired = self.db.collection(DESIRED_COLLECTION).document(PLATFORM).get().to_dict() or {}
        applied = self.db.collection(APPLIED_COLLECTION).document(PLATFORM).get().to_dict() or {}
        if not desired:
            raise RuntimeError("No desired state found for lighter")
        desired_version = str(desired.get("desired_version", "") or "").strip()
        applied_version = str(applied.get("desired_version", "") or "").strip()
        applied_status = str(applied.get("status", "") or "").strip().lower()
        if desired_version and desired_version == applied_version and applied_status == "applied":
            return {
                "reconciled": False,
                "reason": "already_converged",
                "desired_version": desired_version,
                "applied_version": applied_version,
            }

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
        )
        return {
            "reconciled": True,
            "desired_version": desired_version,
            "result": result,
        }


def _json_print(payload: Dict[str, Any]) -> None:
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

    rollback_p = sub.add_parser("rollback", help="Rollback to a previous applied state")
    rollback_p.add_argument("--steps", type=int, default=1, help="How many applied versions back")
    rollback_p.add_argument("--target-host", default=DEFAULT_HOST)
    rollback_p.add_argument("--notes", default="")
    rollback_p.add_argument("--test-quantity", default="0.002")
    rollback_p.add_argument("--skip-test", action="store_true")
    rollback_p.add_argument("--close-after-test", action="store_true")

    sub.add_parser("status", help="Show desired/applied/live status")
    sub.add_parser("reconcile", help="Apply desired state if not converged")
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
        )
        _json_print(out)
        return 0 if out["applied"]["status"] == "applied" else 2

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
        )
        _json_print(out)
        status = (((out.get("result") or {}).get("applied") or {}).get("status") or "").lower()
        return 0 if status == "applied" else 2

    if args.command == "rollback":
        out = ctl.rollback(
            steps=args.steps,
            target_host=args.target_host,
            requested_by=args.requested_by,
            run_test=not args.skip_test,
            close_after_test=bool(args.close_after_test),
            test_quantity=args.test_quantity,
            notes=args.notes,
        )
        _json_print(out)
        status = (((out.get("result") or {}).get("applied") or {}).get("status") or "").lower()
        return 0 if status == "applied" else 2

    if args.command == "status":
        _json_print(ctl.status())
        return 0

    if args.command == "reconcile":
        out = ctl.reconcile(requested_by=args.requested_by)
        _json_print(out)
        if out.get("reconciled"):
            status = (((out.get("result") or {}).get("applied") or {}).get("status") or "").lower()
            return 0 if status == "applied" else 2
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
