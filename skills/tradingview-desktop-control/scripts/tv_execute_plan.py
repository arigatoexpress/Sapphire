#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shlex
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

import tv_plan_intent as tvp

SKILL_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REGISTRY = SKILL_ROOT / "output" / "capability-registry.merged.latest.json"
TVCTL_PATH = SKILL_ROOT / "scripts" / "tvctl.py"
TV_WEB_INVENTORY_PATH = SKILL_ROOT / "scripts" / "tv_web_inventory.py"

RISK_ORDER = {"low": 0, "medium": 1, "high": 2}
HOOK_CHOICES = ["status", "window-bounds", "mouse-location", "list-menus", "window-titles"]
DEFAULT_COMMAND_TIMEOUT_SECONDS = 90.0
DEFAULT_WEB_EXEC_TIMEOUT_SECONDS = 180.0
DEFAULT_WEB_BASELINE_TIMEOUT_SECONDS = 90.0
DEFAULT_WEB_RETRY_ATTEMPTS = 2
DEFAULT_WEB_RETRY_BACKOFF_SECONDS = 0.75
DEFAULT_WEB_RETRY_BACKOFF_MULTIPLIER = 2.0
WEB_SESSION_RESET_ERROR_MARKERS = (
    "target closed",
    "is not open, please run open first",
    "websocket is not open",
    "socket hang up",
    "econnreset",
    "broken pipe",
    "epipe",
    "eaddrinuse",
)
WEB_BASELINE_ASSERTION_KINDS = {
    "page_title_changed",
    "page_href_changed",
    "snapshot_label_appears_any",
    "snapshot_label_appears_all",
    "snapshot_label_disappears_any",
    "snapshot_label_disappears_all",
    "dom_label_appears_any",
    "dom_label_appears_all",
    "dom_label_disappears_any",
    "dom_label_disappears_all",
    "capture_text_appears_any",
    "capture_text_appears_all",
    "capture_text_disappears_any",
    "capture_text_disappears_all",
}


class ExecutionDiagnosticsError(RuntimeError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details = details or {}


def _json_or_none(text: str) -> Any:
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _run_command(cmd: list[str], *, cwd: Path | None = None, timeout_seconds: float | None = None) -> dict[str, Any]:
    started = time.time()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        elapsed = round(time.time() - started, 3)
        stdout = (proc.stdout or "").strip()
        stderr = (proc.stderr or "").strip()
        return {
            "cmd": cmd,
            "command_preview": shlex.join(cmd),
            "cwd": str(cwd) if cwd else None,
            "returncode": proc.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "stdout_json": _json_or_none(stdout),
            "elapsed_seconds": elapsed,
            "timed_out": False,
            "timeout_seconds": timeout_seconds,
        }
    except subprocess.TimeoutExpired as e:
        elapsed = round(time.time() - started, 3)
        stdout = ((e.stdout or "") if isinstance(e.stdout, str) else (e.stdout or b"").decode(errors="replace")).strip()
        stderr = ((e.stderr or "") if isinstance(e.stderr, str) else (e.stderr or b"").decode(errors="replace")).strip()
        if not stderr:
            stderr = f"Command timed out after {timeout_seconds}s"
        return {
            "cmd": cmd,
            "command_preview": shlex.join(cmd),
            "cwd": str(cwd) if cwd else None,
            "returncode": 124,
            "stdout": stdout,
            "stderr": stderr,
            "stdout_json": _json_or_none(stdout),
            "elapsed_seconds": elapsed,
            "timed_out": True,
            "timeout_seconds": timeout_seconds,
        }


def _risk_allowed(selected: str, allowed: str) -> bool:
    return RISK_ORDER.get((selected or "low").lower(), 0) <= RISK_ORDER.get((allowed or "high").lower(), 2)


def _as_positive_float(value: Any) -> float | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if v > 0 else None


def _as_int_at_least(value: Any, minimum: int) -> int | None:
    try:
        v = int(value)
    except (TypeError, ValueError):
        return None
    return v if v >= minimum else None


def _recipe_policy_block(recipe: dict[str, Any], key: str) -> dict[str, Any]:
    node = recipe.get(key)
    return node if isinstance(node, dict) else {}


def _resolve_recipe_timeout(
    recipe: dict[str, Any],
    *,
    cli_value: float | None,
    key: str,
    fallback: float,
) -> float | None:
    cli_timeout = _as_positive_float(cli_value)
    if cli_timeout is not None:
        return cli_timeout
    recipe_timeout = _as_positive_float(_recipe_policy_block(recipe, "timeouts").get(key))
    if recipe_timeout is not None:
        return recipe_timeout
    return fallback


def _resolve_recipe_retry_int(recipe: dict[str, Any], *, key: str, fallback: int) -> int:
    value = _as_int_at_least(_recipe_policy_block(recipe, "retry_policy").get(key), 1)
    return value if value is not None else fallback


def _resolve_recipe_retry_float(recipe: dict[str, Any], *, key: str, fallback: float) -> float:
    value = _as_positive_float(_recipe_policy_block(recipe, "retry_policy").get(key))
    return value if value is not None else fallback


def _is_retryable_web_inventory_error(result: dict[str, Any]) -> bool:
    if int(result.get("returncode") or 0) == 0:
        return False
    if bool(result.get("timed_out")):
        return True
    blob = "\n".join(str(x or "") for x in (result.get("stderr"), result.get("stdout"))).lower()
    transient_markers = [
        "execution context was destroyed",
        "page._evaluatefunction",
        "frame was detached",
        "target closed",
        "context was destroyed",
        "navigation",
        "econnreset",
        "socket hang up",
        "websocket is not open",
        "is not open, please run open first",
        "broken pipe",
        "eaddrinuse",
        "epipe",
    ]
    if any(marker in blob for marker in transient_markers):
        return True
    return bool("action failed" in blob and "snapshot-click" in blob and "not found" in blob)


def _web_inventory_error_blob(result: dict[str, Any]) -> str:
    return "\n".join(str(x or "") for x in (result.get("stderr"), result.get("stdout"))).lower()


def _should_rotate_web_session_on_retry(result: dict[str, Any]) -> bool:
    if int(result.get("returncode") or 0) == 0:
        return False
    if bool(result.get("timed_out")):
        return True
    blob = _web_inventory_error_blob(result)
    return any(marker in blob for marker in WEB_SESSION_RESET_ERROR_MARKERS)


def _retry_web_session_name(current_session: str, phase_tag: str, next_attempt: int) -> str:
    base = str(current_session or "tve")[:12]
    phase = (phase_tag or "r").strip().lower()[:1] or "r"
    suffix = f"{phase}{int(next_attempt)}"
    keep = max(1, 12 - len(suffix))
    return f"{base[:keep]}{suffix}"[:12]


def _run_command_with_retry(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    timeout_seconds: float | None = None,
    attempts: int = 1,
    backoff_seconds: float = DEFAULT_WEB_RETRY_BACKOFF_SECONDS,
    backoff_multiplier: float = DEFAULT_WEB_RETRY_BACKOFF_MULTIPLIER,
    retry_predicate: Any = None,
) -> dict[str, Any]:
    attempts = max(1, int(attempts))
    delay = max(0.0, float(backoff_seconds or 0))
    mult = float(backoff_multiplier or 1.0)
    history: list[dict[str, Any]] = []
    final_res: dict[str, Any] | None = None
    retry_pred = retry_predicate if callable(retry_predicate) else (lambda _res: False)
    for attempt_no in range(1, attempts + 1):
        res = _run_command(cmd, cwd=cwd, timeout_seconds=timeout_seconds)
        retryable = bool(retry_pred(res))
        hist_row = {
            "attempt": attempt_no,
            "returncode": res.get("returncode"),
            "elapsed_seconds": res.get("elapsed_seconds"),
            "timed_out": bool(res.get("timed_out")),
            "retryable": retryable,
        }
        err_blob = str(res.get("stderr") or "").strip()
        if err_blob:
            first_line = err_blob.splitlines()[0]
            hist_row["stderr_first_line"] = first_line[:240]
        history.append(hist_row)
        res["attempt"] = attempt_no
        res["attempts"] = attempts
        final_res = res
        if int(res.get("returncode") or 0) == 0:
            break
        if attempt_no >= attempts or not retryable:
            break
        if delay > 0:
            time.sleep(delay)
            delay *= mult if mult > 0 else 1.0
    if final_res is None:
        raise RuntimeError("Retry runner did not execute command")
    final_res["retry_attempts_used"] = max(0, int(final_res.get("attempt") or 1) - 1)
    if attempts > 1:
        final_res["retry_history"] = history
    return final_res


def _slug_token(text: str, *, max_len: int = 32) -> str:
    raw = "".join(ch.lower() if ch.isalnum() else "-" for ch in str(text or ""))
    while "--" in raw:
        raw = raw.replace("--", "-")
    raw = raw.strip("-")
    if not raw:
        raw = "item"
    return raw[:max_len]


def _collect_web_inventory_snapshot_paths(inventory_data: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    seen: set[str] = set()
    for cap in inventory_data.get("captures", []) or []:
        if not isinstance(cap, dict):
            continue
        snap = cap.get("snapshot")
        if isinstance(snap, dict):
            p = snap.get("artifact")
            if isinstance(p, str) and p and p not in seen:
                seen.add(p)
                paths.append(p)
    plan_execution = inventory_data.get("plan_execution")
    if isinstance(plan_execution, list):
        records = plan_execution
    elif isinstance(plan_execution, dict):
        records = list(plan_execution.values())
    else:
        records = []
    for rec in records:
        if not isinstance(rec, dict):
            continue
        p = rec.get("snapshot_path")
        if isinstance(p, str) and p and p not in seen:
            seen.add(p)
            paths.append(p)
    return paths


def _persist_failed_web_attempt_artifacts(
    *,
    run_id: str,
    phase: str,
    attempt_no: int,
    session_name: str,
    result: dict[str, Any],
    inventory_output_path: Path | None = None,
    actions_path: Path | None = None,
) -> dict[str, Any]:
    root = SKILL_ROOT / "output" / "executor-debug" / _slug_token(run_id, max_len=64)
    attempt_dir = root / f"{_slug_token(phase, max_len=12)}-attempt{int(attempt_no):02d}-{_slug_token(session_name, max_len=18)}"
    attempt_dir.mkdir(parents=True, exist_ok=True)

    out: dict[str, Any] = {
        "attempt_dir": str(attempt_dir),
        "phase": phase,
        "attempt": int(attempt_no),
        "session": session_name,
        "files": {},
        "snapshot_source_paths": [],
    }

    try:
        if actions_path and actions_path.exists():
            dst = attempt_dir / "actions.json"
            shutil.copy2(actions_path, dst)
            out["files"]["actions"] = str(dst)

        inventory_data: dict[str, Any] | None = None
        if inventory_output_path and inventory_output_path.exists():
            inv_dst = attempt_dir / "inventory-output.json"
            shutil.copy2(inventory_output_path, inv_dst)
            out["files"]["inventory_output"] = str(inv_dst)
            try:
                inventory_data = json.loads(inventory_output_path.read_text())
            except Exception as e:  # noqa: BLE001
                out["inventory_parse_error"] = str(e)

        snapshot_paths = _collect_web_inventory_snapshot_paths(inventory_data or {}) if inventory_data else []
        out["snapshot_source_paths"] = snapshot_paths
        if snapshot_paths:
            snap_dir = attempt_dir / "snapshots"
            snap_dir.mkdir(parents=True, exist_ok=True)
            copied: list[str] = []
            for idx, src_str in enumerate(snapshot_paths, start=1):
                src = Path(src_str)
                if not src.exists():
                    continue
                safe_name = src.name if src.name else f"snapshot-{idx:02d}.yml"
                dst = snap_dir / f"{idx:02d}-{safe_name}"
                try:
                    shutil.copy2(src, dst)
                    copied.append(str(dst))
                except Exception:
                    # Best-effort artifact capture; continue copying others.
                    continue
            if copied:
                out["files"]["snapshot_yaml_copies"] = copied

        metadata = {
            "phase": phase,
            "attempt": int(attempt_no),
            "session": session_name,
            "result": {
                "returncode": result.get("returncode"),
                "elapsed_seconds": result.get("elapsed_seconds"),
                "timed_out": bool(result.get("timed_out")),
                "timeout_seconds": result.get("timeout_seconds"),
                "command_preview": result.get("command_preview"),
                "stderr_first_line": (str(result.get("stderr") or "").splitlines() or [""])[0],
                "stdout_first_line": (str(result.get("stdout") or "").splitlines() or [""])[0],
            },
            "snapshot_source_paths": snapshot_paths,
            "captured_at_epoch": time.time(),
        }
        meta_path = attempt_dir / "metadata.json"
        meta_path.write_text(json.dumps(metadata, indent=2) + "\n")
        out["files"]["metadata"] = str(meta_path)
    except Exception as e:  # noqa: BLE001
        out["capture_error"] = str(e)
    return out


def _load_plan_file(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"Plan file must contain a JSON object: {path}")
    return data


def _build_plan_from_intent(
    intent: str,
    *,
    registry: Path,
    search_top: int,
    min_score: float,
    prefer_surface_family: str | None,
    max_risk: str,
) -> dict[str, Any]:
    reg = tvp.load_registry(registry)
    return tvp.build_plan(
        reg,
        intent,
        search_top=max(1, search_top),
        min_score=min_score,
        prefer_surface_family=prefer_surface_family,
        max_risk=max_risk,
    )


def _run_tvctl_hook(hook: str) -> dict[str, Any]:
    subcommand = hook
    rec = {"hook": hook, "runner": "tvctl.py"}
    res = _run_command(["python3", str(TVCTL_PATH), subcommand], timeout_seconds=30)
    rec["result"] = {
        "returncode": res["returncode"],
        "elapsed_seconds": res["elapsed_seconds"],
        "stdout": res["stdout"],
        "stderr": res["stderr"],
        "command_preview": res["command_preview"],
    }
    if subcommand in {"status", "window-bounds", "mouse-location"}:
        rec["result"]["parsed"] = res["stdout_json"]
    elif subcommand in {"list-menus", "window-titles"}:
        rec["result"]["lines"] = [ln for ln in (res["stdout"] or "").splitlines() if ln.strip()]
    rec["ok"] = res["returncode"] == 0
    return rec


def _dedupe_ordered(items: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def _text_matches(hay: str | None, needle: str, *, match: str = "contains", case_sensitive: bool = False) -> bool:
    if hay is None:
        return False
    left = hay if case_sensitive else hay.lower()
    right = needle if case_sensitive else needle.lower()
    mode = (match or "contains").strip().lower()
    if mode == "exact":
        return left == right
    if mode == "startswith":
        return left.startswith(right)
    if mode == "contains":
        return right in left
    return False


def _collect_snapshot_labels(capture: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for ref in capture.get("snapshot_refs", []) or []:
        if not isinstance(ref, dict):
            continue
        for k in ("label", "text", "role"):
            v = ref.get(k)
            if isinstance(v, str) and v.strip():
                out.append(v.strip())
                break
    return out


def _collect_dom_labels(capture: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for node in capture.get("dom_controls", []) or []:
        if not isinstance(node, dict):
            continue
        for k in ("aria_label", "title", "text", "data_name", "role", "tag"):
            v = node.get(k)
            if isinstance(v, str) and v.strip():
                out.append(v.strip())
                break
    return out


def _verification_needs_web_baseline(recipe: dict[str, Any]) -> bool:
    verification = recipe.get("verification")
    if not isinstance(verification, dict):
        return False
    for a in verification.get("assertions", []) or []:
        if not isinstance(a, dict):
            continue
        if str(a.get("kind") or "").strip() in WEB_BASELINE_ASSERTION_KINDS:
            return True
    return False


def _verify_web_inventory_capture(recipe: dict[str, Any], full: dict[str, Any], *, baseline_full: dict[str, Any] | None = None) -> dict[str, Any]:
    verification = recipe.get("verification") if isinstance(recipe.get("verification"), dict) else {}
    captures = full.get("captures") or []
    first_capture = (captures[0] if captures else {}) or {}
    page = first_capture.get("page") or {}
    snapshot_labels = _collect_snapshot_labels(first_capture)
    dom_labels = _collect_dom_labels(first_capture)
    all_capture_labels = snapshot_labels + dom_labels
    plan_execution = full.get("plan_execution") or []
    baseline_capture = (((baseline_full or {}).get("captures") or [{}])[0] if isinstance(baseline_full, dict) else {}) or {}
    baseline_page = baseline_capture.get("page") or {}
    baseline_snapshot_labels = _collect_snapshot_labels(baseline_capture) if baseline_capture else []
    baseline_dom_labels = _collect_dom_labels(baseline_capture) if baseline_capture else []
    baseline_all_capture_labels = baseline_snapshot_labels + baseline_dom_labels

    assertions = list(verification.get("assertions") or [])
    post_capture_label = verification.get("post_capture_label")
    if post_capture_label and not any(
        isinstance(a, dict) and a.get("kind") == "capture_label_equals" for a in assertions
    ):
        assertions.insert(0, {"kind": "capture_label_equals", "value": str(post_capture_label)})

    results: list[dict[str, Any]] = []
    for raw in assertions:
        if not isinstance(raw, dict):
            continue
        kind = str(raw.get("kind") or "").strip()
        rec: dict[str, Any] = {"kind": kind, "ok": False}
        if kind == "capture_label_equals":
            expected = str(raw.get("value") or "")
            actual = str(first_capture.get("label") or "")
            rec.update({"expected": expected, "actual": actual, "ok": actual == expected})
        elif kind == "page_title_contains":
            needle = str(raw.get("value") or "")
            actual = str(page.get("title") or "")
            match = str(raw.get("match") or "contains")
            rec.update({"expected": needle, "actual": actual, "match": match, "ok": _text_matches(actual, needle, match=match)})
        elif kind == "page_href_contains":
            needle = str(raw.get("value") or "")
            actual = str(page.get("href") or "")
            match = str(raw.get("match") or "contains")
            rec.update({"expected": needle, "actual": actual, "match": match, "ok": _text_matches(actual, needle, match=match)})
        elif kind == "page_title_changed":
            before = str(baseline_page.get("title") or "")
            after = str(page.get("title") or "")
            rec.update({"before": before, "after": after, "ok": bool(before and after and before != after)})
        elif kind == "page_href_changed":
            before = str(baseline_page.get("href") or "")
            after = str(page.get("href") or "")
            rec.update({"before": before, "after": after, "ok": bool(before and after and before != after)})
        elif kind in {"snapshot_label_any", "snapshot_label_all"}:
            vals = [str(v) for v in (raw.get("values") or []) if str(v).strip()]
            match = str(raw.get("match") or "contains")
            case_sensitive = bool(raw.get("case_sensitive", False))
            checks = []
            for val in vals:
                found = any(_text_matches(lbl, val, match=match, case_sensitive=case_sensitive) for lbl in snapshot_labels)
                checks.append({"value": val, "found": found})
            ok = any(c["found"] for c in checks) if kind == "snapshot_label_any" else all(c["found"] for c in checks)
            rec.update({"values": vals, "match": match, "checks": checks, "ok": ok})
        elif kind in {"dom_label_any", "dom_label_all"}:
            vals = [str(v) for v in (raw.get("values") or []) if str(v).strip()]
            match = str(raw.get("match") or "contains")
            case_sensitive = bool(raw.get("case_sensitive", False))
            checks = []
            for val in vals:
                found = any(_text_matches(lbl, val, match=match, case_sensitive=case_sensitive) for lbl in dom_labels)
                checks.append({"value": val, "found": found})
            ok = any(c["found"] for c in checks) if kind == "dom_label_any" else all(c["found"] for c in checks)
            rec.update({"values": vals, "match": match, "checks": checks, "ok": ok})
        elif kind in {"capture_text_any", "capture_text_all"}:
            vals = [str(v) for v in (raw.get("values") or []) if str(v).strip()]
            match = str(raw.get("match") or "contains")
            case_sensitive = bool(raw.get("case_sensitive", False))
            checks = []
            for val in vals:
                found = any(_text_matches(lbl, val, match=match, case_sensitive=case_sensitive) for lbl in all_capture_labels)
                checks.append({"value": val, "found": found})
            ok = any(c["found"] for c in checks) if kind == "capture_text_any" else all(c["found"] for c in checks)
            rec.update({"values": vals, "match": match, "checks": checks, "ok": ok})
        elif kind in {
            "snapshot_label_appears_any",
            "snapshot_label_appears_all",
            "snapshot_label_disappears_any",
            "snapshot_label_disappears_all",
        }:
            vals = [str(v) for v in (raw.get("values") or []) if str(v).strip()]
            match = str(raw.get("match") or "contains")
            case_sensitive = bool(raw.get("case_sensitive", False))
            checks = []
            for val in vals:
                before_found = any(_text_matches(lbl, val, match=match, case_sensitive=case_sensitive) for lbl in baseline_snapshot_labels)
                after_found = any(_text_matches(lbl, val, match=match, case_sensitive=case_sensitive) for lbl in snapshot_labels)
                if "appears" in kind:
                    ok_val = (not before_found) and after_found
                else:
                    ok_val = before_found and (not after_found)
                checks.append({"value": val, "before_found": before_found, "after_found": after_found, "ok": ok_val})
            ok = any(c["ok"] for c in checks) if kind.endswith("_any") else all(c["ok"] for c in checks)
            rec.update({"values": vals, "match": match, "checks": checks, "ok": ok})
        elif kind in {
            "dom_label_appears_any",
            "dom_label_appears_all",
            "dom_label_disappears_any",
            "dom_label_disappears_all",
        }:
            vals = [str(v) for v in (raw.get("values") or []) if str(v).strip()]
            match = str(raw.get("match") or "contains")
            case_sensitive = bool(raw.get("case_sensitive", False))
            checks = []
            for val in vals:
                before_found = any(_text_matches(lbl, val, match=match, case_sensitive=case_sensitive) for lbl in baseline_dom_labels)
                after_found = any(_text_matches(lbl, val, match=match, case_sensitive=case_sensitive) for lbl in dom_labels)
                if "appears" in kind:
                    ok_val = (not before_found) and after_found
                else:
                    ok_val = before_found and (not after_found)
                checks.append({"value": val, "before_found": before_found, "after_found": after_found, "ok": ok_val})
            ok = any(c["ok"] for c in checks) if kind.endswith("_any") else all(c["ok"] for c in checks)
            rec.update({"values": vals, "match": match, "checks": checks, "ok": ok})
        elif kind in {
            "capture_text_appears_any",
            "capture_text_appears_all",
            "capture_text_disappears_any",
            "capture_text_disappears_all",
        }:
            vals = [str(v) for v in (raw.get("values") or []) if str(v).strip()]
            match = str(raw.get("match") or "contains")
            case_sensitive = bool(raw.get("case_sensitive", False))
            checks = []
            for val in vals:
                before_found = any(_text_matches(lbl, val, match=match, case_sensitive=case_sensitive) for lbl in baseline_all_capture_labels)
                after_found = any(_text_matches(lbl, val, match=match, case_sensitive=case_sensitive) for lbl in all_capture_labels)
                if "appears" in kind:
                    ok_val = (not before_found) and after_found
                else:
                    ok_val = before_found and (not after_found)
                checks.append({"value": val, "before_found": before_found, "after_found": after_found, "ok": ok_val})
            ok = any(c["ok"] for c in checks) if kind.endswith("_any") else all(c["ok"] for c in checks)
            rec.update({"values": vals, "match": match, "checks": checks, "ok": ok})
        elif kind == "plan_action_executed":
            action = str(raw.get("action") or "")
            min_count = int(raw.get("min_count") or 1)
            matched = [step for step in plan_execution if isinstance(step, dict) and (not action or str(step.get("action") or "") == action)]
            rec.update({"action": action or None, "min_count": min_count, "count": len(matched), "ok": len(matched) >= min_count})
        else:
            rec.update({"error": f"unsupported assertion kind: {kind}"})
        results.append(rec)

    ok = all(bool(r.get("ok")) for r in results) if results else True
    return {
        "type": "web_inventory_capture",
        "ok": ok,
        "assertion_count": len(results),
        "assertions": results,
        "capture_label": first_capture.get("label"),
        "page_title": page.get("title"),
        "page_href": page.get("href"),
        "baseline_page_title": baseline_page.get("title") if baseline_page else None,
        "baseline_page_href": baseline_page.get("href") if baseline_page else None,
        "snapshot_ref_count": len(first_capture.get("snapshot_refs", []) or []),
        "dom_control_count": len(first_capture.get("dom_controls", []) or []),
    }


def _default_hooks_for_runner(recipe: dict[str, Any]) -> tuple[list[str], list[str]]:
    runner = str(recipe.get("runner") or "")
    if runner == "tvctl.py":
        return ["status"], ["status"]
    return [], []


def _recipe_runner(recipe: dict[str, Any]) -> str:
    return str(recipe.get("runner") or "").strip()


def _ensure_ready_plan(plan: dict[str, Any]) -> tuple[bool, str]:
    status = str(plan.get("status") or "")
    if status != "ready":
        return False, status or "unknown"
    recipe = plan.get("recipe")
    if not isinstance(recipe, dict):
        return False, "missing_recipe"
    if recipe.get("missing_parameters"):
        return False, "missing_parameters"
    return True, "ready"


def _execute_tvctl_recipe(recipe: dict[str, Any], *, command_timeout_seconds: float | None) -> dict[str, Any]:
    subcommand = str(recipe.get("subcommand") or "").strip()
    if not subcommand:
        raise ValueError("tvctl recipe missing subcommand")
    cmd = ["python3", str(TVCTL_PATH), subcommand]
    for arg in recipe.get("args", []) or []:
        cmd.append(str(arg))
    res = _run_command(cmd, timeout_seconds=command_timeout_seconds)
    res["execution_policy"] = {"timeouts": {"command_timeout_seconds": command_timeout_seconds}}
    return res


def _execute_tv_web_inventory_recipe(
    recipe: dict[str, Any],
    *,
    web_session: str | None,
    web_headed: bool,
    web_keep_open: bool,
    web_cwd: Path | None,
    web_exec_timeout_seconds: float | None,
    web_baseline_timeout_seconds: float | None,
    debug_artifacts_mode: str,
) -> dict[str, Any]:
    actions = recipe.get("actions")
    if not isinstance(actions, list) or not actions:
        raise ValueError("tv_web_inventory recipe requires non-empty 'actions' list")

    cwd = web_cwd or Path.cwd()
    auto_session = f"tve{int(time.time() * 1000) % 100000:05d}"
    session = web_session or str(recipe.get("session") or auto_session)
    # Keep session short to avoid playwright-cli Unix socket issues.
    if len(session) > 12:
        session = session[:12]
    debug_run_id = f"{int(time.time() * 1000)}-{session}"

    with tempfile.TemporaryDirectory(prefix="tvexec-web-") as tmpdir:
        tmp = Path(tmpdir)
        actions_path = tmp / "actions.json"
        output_path = tmp / "web-exec-output.json"
        baseline_output_path = tmp / "web-baseline-output.json"
        actions_path.write_text(json.dumps(actions, indent=2) + "\n")

        baseline_timeout = _resolve_recipe_timeout(
            recipe,
            cli_value=web_baseline_timeout_seconds,
            key="web_baseline_timeout_seconds",
            fallback=DEFAULT_WEB_BASELINE_TIMEOUT_SECONDS,
        )
        exec_timeout = _resolve_recipe_timeout(
            recipe,
            cli_value=web_exec_timeout_seconds,
            key="web_exec_timeout_seconds",
            fallback=DEFAULT_WEB_EXEC_TIMEOUT_SECONDS,
        )
        baseline_attempts = _resolve_recipe_retry_int(
            recipe,
            key="web_baseline_attempts",
            fallback=DEFAULT_WEB_RETRY_ATTEMPTS,
        )
        exec_attempts = _resolve_recipe_retry_int(
            recipe,
            key="web_exec_attempts",
            fallback=DEFAULT_WEB_RETRY_ATTEMPTS,
        )
        retry_backoff_seconds = _resolve_recipe_retry_float(
            recipe,
            key="backoff_seconds",
            fallback=DEFAULT_WEB_RETRY_BACKOFF_SECONDS,
        )
        retry_backoff_multiplier = _resolve_recipe_retry_float(
            recipe,
            key="backoff_multiplier",
            fallback=DEFAULT_WEB_RETRY_BACKOFF_MULTIPLIER,
        )

        needs_baseline = _verification_needs_web_baseline(recipe)

        def _baseline_cmd_for(sess: str) -> list[str]:
            cmd = [
                "python3",
                str(TV_WEB_INVENTORY_PATH),
                "--session",
                sess,
                "--cwd",
                str(cwd),
                "--capture-label",
                str(recipe.get("baseline_capture_label") or "pre-execute"),
                "--output",
                str(baseline_output_path),
                "--no-close",
            ]
            if recipe.get("url"):
                cmd += ["--url", str(recipe["url"])]
            if web_headed or bool(recipe.get("headed")):
                cmd.append("--headed")
            return cmd

        def _exec_cmd_for(sess: str) -> list[str]:
            cmd = [
                "python3",
                str(TV_WEB_INVENTORY_PATH),
                "--session",
                sess,
                "--cwd",
                str(cwd),
                "--actions-file",
                str(actions_path),
                "--capture-label",
                str(recipe.get("capture_label") or "execute"),
                "--output",
                str(output_path),
            ]
            if recipe.get("url"):
                cmd += ["--url", str(recipe["url"])]
            if web_headed or bool(recipe.get("headed")):
                cmd.append("--headed")
            close_when_done = bool(recipe.get("close_when_done", True))
            if web_keep_open or not close_when_done:
                cmd.append("--no-close")
            return cmd

        def _capture_baseline_with_retry(start_session: str) -> tuple[dict[str, Any], dict[str, Any] | None, str]:
            attempts_total = max(1, int(baseline_attempts))
            delay = max(0.0, float(retry_backoff_seconds or 0))
            mult = float(retry_backoff_multiplier or 1.0)
            current_session = str(start_session or session)
            history: list[dict[str, Any]] = []
            final_res: dict[str, Any] | None = None
            for attempt_no in range(1, attempts_total + 1):
                if baseline_output_path.exists():
                    baseline_output_path.unlink()
                res = _run_command(_baseline_cmd_for(current_session), timeout_seconds=baseline_timeout)
                retryable = _is_retryable_web_inventory_error(res)
                rotate_session = retryable and _should_rotate_web_session_on_retry(res) and attempt_no < attempts_total
                next_session = _retry_web_session_name(current_session, "b", attempt_no + 1) if rotate_session else current_session
                hist_row = {
                    "attempt": attempt_no,
                    "phase": "baseline",
                    "session": current_session,
                    "returncode": res.get("returncode"),
                    "elapsed_seconds": res.get("elapsed_seconds"),
                    "timed_out": bool(res.get("timed_out")),
                    "retryable": retryable,
                    "session_rotated": rotate_session,
                }
                if rotate_session:
                    hist_row["next_session"] = next_session
                err_blob = str(res.get("stderr") or "").strip()
                if err_blob:
                    hist_row["stderr_first_line"] = err_blob.splitlines()[0][:240]
                should_capture_debug = (
                    debug_artifacts_mode == "always"
                    or (debug_artifacts_mode == "on-failure" and int(res.get("returncode") or 0) != 0)
                )
                if should_capture_debug:
                    hist_row["debug_artifacts"] = _persist_failed_web_attempt_artifacts(
                        run_id=debug_run_id,
                        phase="baseline",
                        attempt_no=attempt_no,
                        session_name=current_session,
                        result=res,
                        inventory_output_path=baseline_output_path,
                        actions_path=None,
                    )
                history.append(hist_row)
                res["attempt"] = attempt_no
                res["attempts"] = attempts_total
                final_res = res
                if int(res.get("returncode") or 0) == 0:
                    break
                if attempt_no >= attempts_total or not retryable:
                    break
                if delay > 0:
                    time.sleep(delay)
                    delay *= mult if mult > 0 else 1.0
                current_session = next_session
            if final_res is None:
                raise RuntimeError("Baseline retry runner did not execute")
            final_res["retry_attempts_used"] = max(0, int(final_res.get("attempt") or 1) - 1)
            final_res["session_used"] = current_session
            if attempts_total > 1:
                final_res["retry_history"] = history
            final_res["session_retry_history"] = history
            baseline_data: dict[str, Any] | None = None
            if int(final_res.get("returncode") or 0) == 0 and baseline_output_path.exists():
                baseline_data = json.loads(baseline_output_path.read_text())
            return final_res, baseline_data, current_session

        baseline_full: dict[str, Any] | None = None
        baseline_session_used: str | None = None
        baseline_capture_runs: list[dict[str, Any]] = []
        current_session = session

        exec_attempts_total = max(1, int(exec_attempts))
        exec_delay = max(0.0, float(retry_backoff_seconds or 0))
        exec_mult = float(retry_backoff_multiplier or 1.0)
        exec_retry_history: list[dict[str, Any]] = []
        final_exec_res: dict[str, Any] | None = None

        for exec_attempt_no in range(1, exec_attempts_total + 1):
            if needs_baseline and (baseline_full is None or baseline_session_used != current_session):
                baseline_res, baseline_data, baseline_session = _capture_baseline_with_retry(current_session)
                baseline_capture_runs.append(
                    {
                        "attempt_group": len(baseline_capture_runs) + 1,
                        "session_requested": current_session,
                        "session_used": baseline_session,
                        "returncode": baseline_res.get("returncode"),
                        "attempt": baseline_res.get("attempt"),
                        "attempts": baseline_res.get("attempts"),
                        "retry_attempts_used": baseline_res.get("retry_attempts_used"),
                        "timed_out": baseline_res.get("timed_out"),
                        "stderr": baseline_res.get("stderr"),
                        "retry_history": baseline_res.get("retry_history"),
                        "session_retry_history": baseline_res.get("session_retry_history"),
                        "debug_artifacts": next(
                            (
                                row.get("debug_artifacts")
                                for row in (baseline_res.get("session_retry_history") or [])
                                if isinstance(row, dict) and row.get("debug_artifacts")
                            ),
                            None,
                        ),
                    }
                )
                if int(baseline_res.get("returncode") or 0) != 0:
                    attempts_used = int(baseline_res.get("attempt") or 1)
                    attempts_max = int(baseline_res.get("attempts") or baseline_attempts)
                    msg = (
                        "Failed to capture web baseline for delta assertions: "
                        + f"after {attempts_used}/{attempts_max} attempt(s): "
                        + str((baseline_res.get("stderr") or baseline_res.get("stdout") or "").strip())
                    )
                    partial_exec_info = {
                        "phase": "baseline",
                        "returncode": baseline_res.get("returncode"),
                        "elapsed_seconds": baseline_res.get("elapsed_seconds"),
                        "timed_out": baseline_res.get("timed_out"),
                        "timeout_seconds": baseline_res.get("timeout_seconds"),
                        "stderr": baseline_res.get("stderr"),
                        "stdout": baseline_res.get("stdout"),
                        "command_preview": baseline_res.get("command_preview"),
                        "attempt": baseline_res.get("attempt"),
                        "attempts": baseline_res.get("attempts"),
                        "retry_attempts_used": baseline_res.get("retry_attempts_used"),
                        "session_used": baseline_res.get("session_used"),
                        "execution_policy": {
                            "timeouts": {
                                "web_baseline_timeout_seconds": baseline_timeout,
                                "web_exec_timeout_seconds": exec_timeout,
                            },
                            "retry_policy": {
                                "web_baseline_attempts": baseline_attempts,
                                "web_exec_attempts": exec_attempts,
                                "backoff_seconds": retry_backoff_seconds,
                                "backoff_multiplier": retry_backoff_multiplier,
                            },
                            "debug_artifacts": {"mode": debug_artifacts_mode},
                        },
                        "session_retry": {
                            "initial_session": session,
                            "final_session": baseline_session,
                            "execution_attempts": 0,
                            "execution_retries_used": 0,
                            "execution_history": [],
                            "baseline_runs": baseline_capture_runs,
                        },
                        "artifacts": {
                            "temporary": True,
                            "actions_file_name": actions_path.name,
                            "inventory_output_name": output_path.name,
                            "baseline_inventory_output_name": baseline_output_path.name,
                        },
                    }
                    raise ExecutionDiagnosticsError(msg, details=partial_exec_info)
                baseline_full = baseline_data
                baseline_session_used = baseline_session
                current_session = baseline_session

            if output_path.exists():
                output_path.unlink()
            res = _run_command(_exec_cmd_for(current_session), timeout_seconds=exec_timeout)
            retryable = _is_retryable_web_inventory_error(res)
            rotate_session = retryable and _should_rotate_web_session_on_retry(res) and exec_attempt_no < exec_attempts_total
            next_session = _retry_web_session_name(current_session, "e", exec_attempt_no + 1) if rotate_session else current_session
            hist_row = {
                "attempt": exec_attempt_no,
                "phase": "execution",
                "session": current_session,
                "returncode": res.get("returncode"),
                "elapsed_seconds": res.get("elapsed_seconds"),
                "timed_out": bool(res.get("timed_out")),
                "retryable": retryable,
                "session_rotated": rotate_session,
            }
            if rotate_session:
                hist_row["next_session"] = next_session
            err_blob = str(res.get("stderr") or "").strip()
            if err_blob:
                hist_row["stderr_first_line"] = err_blob.splitlines()[0][:240]
            should_capture_debug = (
                debug_artifacts_mode == "always"
                or (debug_artifacts_mode == "on-failure" and int(res.get("returncode") or 0) != 0)
            )
            if should_capture_debug:
                hist_row["debug_artifacts"] = _persist_failed_web_attempt_artifacts(
                    run_id=debug_run_id,
                    phase="execution",
                    attempt_no=exec_attempt_no,
                    session_name=current_session,
                    result=res,
                    inventory_output_path=output_path,
                    actions_path=actions_path,
                )
            exec_retry_history.append(hist_row)
            res["attempt"] = exec_attempt_no
            res["attempts"] = exec_attempts_total
            final_exec_res = res
            if int(res.get("returncode") or 0) == 0:
                break
            if exec_attempt_no >= exec_attempts_total or not retryable:
                break
            if exec_delay > 0:
                time.sleep(exec_delay)
                exec_delay *= exec_mult if exec_mult > 0 else 1.0
            current_session = next_session
            if rotate_session:
                baseline_full = None
                baseline_session_used = None

        if final_exec_res is None:
            raise RuntimeError("Execution retry runner did not execute")
        final_exec_res["retry_attempts_used"] = max(0, int(final_exec_res.get("attempt") or 1) - 1)
        final_exec_res["session_used"] = current_session
        if exec_attempts_total > 1:
            final_exec_res["retry_history"] = exec_retry_history
        final_exec_res["session_retry_history"] = exec_retry_history
        res = final_exec_res
        exec_info: dict[str, Any] = res
        exec_info["execution_policy"] = {
            "timeouts": {
                "web_baseline_timeout_seconds": baseline_timeout,
                "web_exec_timeout_seconds": exec_timeout,
            },
            "retry_policy": {
                "web_baseline_attempts": baseline_attempts,
                "web_exec_attempts": exec_attempts,
                "backoff_seconds": retry_backoff_seconds,
                "backoff_multiplier": retry_backoff_multiplier,
            },
            "debug_artifacts": {"mode": debug_artifacts_mode},
        }
        exec_info["session_retry"] = {
            "initial_session": session,
            "final_session": current_session,
            "execution_attempts": exec_info.get("attempts"),
            "execution_retries_used": exec_info.get("retry_attempts_used"),
            "execution_history": exec_retry_history,
            "baseline_runs": baseline_capture_runs,
        }
        exec_info["artifacts"] = {
            "temporary": True,
            "actions_file_name": actions_path.name,
            "inventory_output_name": output_path.name,
            "baseline_inventory_output_name": baseline_output_path.name if baseline_full is not None else None,
        }
        if baseline_full is not None:
            exec_info["baseline_summary"] = {
                "capture_count": len(baseline_full.get("captures", []) or []),
                "capability_count": len(baseline_full.get("capabilities", []) or []),
                "page": ((baseline_full.get("captures") or [{}])[0] or {}).get("page"),
            }
        if output_path.exists():
            full = json.loads(output_path.read_text())
            exec_info["web_inventory_summary"] = {
                "session": full.get("session"),
                "capture_count": len(full.get("captures", []) or []),
                "capability_count": len(full.get("capabilities", []) or []),
                "page": ((full.get("captures") or [{}])[0] or {}).get("page"),
                "plan_execution": full.get("plan_execution"),
            }
            # Keep a compact verification snapshot for the first capture.
            first_cap = (full.get("captures") or [{}])[0] or {}
            exec_info["verification"] = {
                "capture_label": first_cap.get("label"),
                "snapshot_ref_count": ((first_cap.get("snapshot") or {}).get("ref_count")),
                "dom_control_count": len(first_cap.get("dom_controls", []) or []),
            }
            exec_info["verification_result"] = _verify_web_inventory_capture(recipe, full, baseline_full=baseline_full)
        return exec_info


def _execute_recipe(
    recipe: dict[str, Any],
    *,
    web_session: str | None,
    web_headed: bool,
    web_keep_open: bool,
    web_cwd: Path | None,
    command_timeout_seconds: float | None,
    web_exec_timeout_seconds: float | None,
    web_baseline_timeout_seconds: float | None,
    debug_artifacts_mode: str,
) -> dict[str, Any]:
    runner = _recipe_runner(recipe)
    if runner == "tvctl.py":
        return _execute_tvctl_recipe(
            recipe,
            command_timeout_seconds=_resolve_recipe_timeout(
                recipe,
                cli_value=command_timeout_seconds,
                key="command_timeout_seconds",
                fallback=DEFAULT_COMMAND_TIMEOUT_SECONDS,
            ),
        )
    if runner == "tv_web_inventory.py":
        return _execute_tv_web_inventory_recipe(
            recipe,
            web_session=web_session,
            web_headed=web_headed,
            web_keep_open=web_keep_open,
            web_cwd=web_cwd,
            web_exec_timeout_seconds=web_exec_timeout_seconds,
            web_baseline_timeout_seconds=web_baseline_timeout_seconds,
            debug_artifacts_mode=debug_artifacts_mode,
        )
    raise ValueError(f"Unsupported recipe runner: {runner}")


def _select_hooks(
    recipe: dict[str, Any],
    *,
    pre_hooks: list[str],
    post_hooks: list[str],
    auto_hooks: bool,
) -> tuple[list[str], list[str]]:
    auto_pre, auto_post = _default_hooks_for_runner(recipe) if auto_hooks else ([], [])
    return _dedupe_ordered([*auto_pre, *pre_hooks]), _dedupe_ordered([*auto_post, *post_hooks])


def format_result_text(result: dict[str, Any]) -> str:
    lines = [
        f"Intent: {result.get('intent') or '<from plan file>'}",
        f"Status: {result.get('status')}",
    ]
    if result.get("message"):
        lines.append(f"Note: {result.get('message')}")
    sel = result.get("selected_capability")
    if isinstance(sel, dict):
        lines.append(
            f"Selected: {sel.get('label')} [surface={sel.get('surface_family')}, risk={sel.get('risk_level')}, score={sel.get('score')}]"
        )
    if result.get("command_preview"):
        lines.append(f"Command preview: {result.get('command_preview')}")
    if result.get("risk_gate"):
        rg = result["risk_gate"]
        lines.append(
            f"Risk gate: selected={rg.get('selected')} allowed={rg.get('allowed_max')} allowed={rg.get('allowed')}"
        )
    if result.get("pre_hooks"):
        lines.append(f"Pre-hooks: {', '.join(h.get('hook','?') for h in result.get('pre_hooks') or [])}")
    if result.get("post_hooks"):
        lines.append(f"Post-hooks: {', '.join(h.get('hook','?') for h in result.get('post_hooks') or [])}")
    exec_res = result.get("execution")
    if isinstance(exec_res, dict):
        lines.append(
            f"Execution rc={exec_res.get('returncode')} elapsed={exec_res.get('elapsed_seconds')}s cmd={exec_res.get('command_preview')}"
        )
        if int(exec_res.get("retry_attempts_used") or 0) > 0:
            lines.append(
                f"Execution retries: used={exec_res.get('retry_attempts_used')} total_attempts={exec_res.get('attempts')}"
            )
        if exec_res.get("timed_out"):
            lines.append(f"Execution timeout: {exec_res.get('timeout_seconds')}s")
        err_blob = str(exec_res.get("stderr") or "").strip()
        if err_blob and int(exec_res.get("returncode") or 0) != 0:
            err_line = err_blob.splitlines()[0]
            if len(err_line) > 240:
                err_line = err_line[:237] + "..."
            lines.append(f"Execution stderr: {err_line}")
        sr = exec_res.get("session_retry")
        if isinstance(sr, dict):
            debug_dirs: list[str] = []
            for row in sr.get("execution_history") or []:
                if isinstance(row, dict):
                    dbg = row.get("debug_artifacts")
                    if isinstance(dbg, dict) and isinstance(dbg.get("attempt_dir"), str):
                        debug_dirs.append(dbg["attempt_dir"])
            for row in sr.get("baseline_runs") or []:
                if isinstance(row, dict):
                    dbg = row.get("debug_artifacts")
                    if isinstance(dbg, dict) and isinstance(dbg.get("attempt_dir"), str):
                        debug_dirs.append(dbg["attempt_dir"])
                    for sub in row.get("session_retry_history") or []:
                        if isinstance(sub, dict):
                            dbg2 = sub.get("debug_artifacts")
                            if isinstance(dbg2, dict) and isinstance(dbg2.get("attempt_dir"), str):
                                debug_dirs.append(dbg2["attempt_dir"])
            if debug_dirs:
                seen_dbg: list[str] = []
                for p in debug_dirs:
                    if p not in seen_dbg:
                        seen_dbg.append(p)
                lines.append(f"Debug artifacts: {seen_dbg[0]}{f' (+{len(seen_dbg)-1} more)' if len(seen_dbg) > 1 else ''}")
        if exec_res.get("web_inventory_summary"):
            wis = exec_res["web_inventory_summary"]
            lines.append(
                f"Web verify: captures={wis.get('capture_count')} capabilities={wis.get('capability_count')} page={((wis.get('page') or {}).get('title'))}"
            )
        if isinstance(exec_res.get("verification_result"), dict):
            vr = exec_res["verification_result"]
            lines.append(
                f"Recipe verification: ok={vr.get('ok')} assertions={vr.get('assertion_count')} capture={vr.get('capture_label')}"
            )
            if not bool(vr.get("ok")):
                failed = [a for a in (vr.get("assertions") or []) if isinstance(a, dict) and not a.get("ok")]
                if failed:
                    details = []
                    for a in failed[:3]:
                        kind = str(a.get("kind") or "?")
                        values = a.get("values")
                        if isinstance(values, list) and values:
                            details.append(f"{kind}({', '.join(str(v) for v in values[:3])})")
                        else:
                            details.append(kind)
                    lines.append(f"Recipe verification failures: {', '.join(details)}")
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(description="Execute a TradingView planner result with risk gates and verification hooks")
    p.add_argument("intent", nargs="?", help="Natural-language intent (omit when using --plan-file)")
    p.add_argument("--plan-file", type=Path, default=None, help="Existing tv_plan_intent.py JSON output")
    p.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    p.add_argument("--search-top", type=int, default=20)
    p.add_argument("--min-score", type=float, default=0.0)
    p.add_argument("--prefer-surface-family", choices=["desktop_ui", "web_ui"], default=None)
    p.add_argument("--max-risk", choices=["low", "medium", "high"], default="medium", help="Planning + execution risk threshold")
    p.add_argument("--allow-risk", choices=["low", "medium", "high"], default=None, help="Execution-only risk threshold (defaults to --max-risk)")
    p.add_argument("--yes", action="store_true", help="Execute the selected recipe (otherwise dry-run/plan-only)")
    p.add_argument("--dry-run", action="store_true", help="Force dry-run (do not execute)")
    p.add_argument("--pre-hook", action="append", default=[], choices=HOOK_CHOICES, help="Run a verification hook before execution")
    p.add_argument("--post-hook", action="append", default=[], choices=HOOK_CHOICES, help="Run a verification hook after execution")
    p.add_argument("--no-auto-hooks", action="store_true", help="Disable default runner-specific hooks (e.g. status pre/post for tvctl)")
    p.add_argument("--web-session", default=None, help="Override Playwright session name for web recipe execution")
    p.add_argument("--web-headed", action="store_true", help="Force headed mode for web recipe execution")
    p.add_argument("--web-keep-open", action="store_true", help="Do not close Playwright browser/session after web execution")
    p.add_argument("--web-cwd", type=Path, default=None, help="Working dir for playwright-cli artifacts when executing web recipes")
    p.add_argument(
        "--debug-artifacts",
        choices=["on-failure", "always", "off"],
        default="on-failure",
        help="Persist web execution debug artifacts (default: on-failure)",
    )
    p.add_argument(
        "--command-timeout-seconds",
        type=float,
        default=None,
        help="Override timeout for tvctl recipe commands (seconds). Defaults to recipe policy or 90s. <=0 disables timeout.",
    )
    p.add_argument(
        "--web-exec-timeout-seconds",
        type=float,
        default=None,
        help="Override timeout for web recipe execution capture (seconds). Defaults to recipe policy or 180s. <=0 disables timeout.",
    )
    p.add_argument(
        "--web-baseline-timeout-seconds",
        type=float,
        default=None,
        help="Override timeout for web baseline capture (seconds). Defaults to recipe policy or 90s. <=0 disables timeout.",
    )
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    if not args.plan_file and not args.intent:
        p.error("Provide an intent or --plan-file")
    if args.plan_file and args.intent:
        p.error("Use either an intent or --plan-file, not both")

    out: dict[str, Any] = {
        "intent": args.intent,
        "registry": str(args.registry),
        "dry_run": bool(args.dry_run or not args.yes),
    }

    try:
        if args.plan_file:
            plan = _load_plan_file(args.plan_file)
        else:
            plan = _build_plan_from_intent(
                str(args.intent),
                registry=args.registry,
                search_top=max(1, args.search_top),
                min_score=args.min_score,
                prefer_surface_family=args.prefer_surface_family,
                max_risk=args.max_risk,
            )
    except Exception as e:  # noqa: BLE001
        out["status"] = "plan_error"
        out["message"] = str(e)
        if args.json:
            print(json.dumps(out, indent=2))
        else:
            print(format_result_text(out))
        return 1

    out["plan"] = plan
    out["selected_capability"] = plan.get("selected_capability")
    out["recipe"] = plan.get("recipe")
    out["command_preview"] = plan.get("command_preview")

    ready, ready_status = _ensure_ready_plan(plan)
    if not ready:
        out["status"] = ready_status if ready_status != "ready" else "not_ready"
        out["message"] = plan.get("message") or "Plan is not ready to execute"
        if args.json:
            print(json.dumps(out, indent=2))
        else:
            print(format_result_text(out))
        return 1

    recipe = plan["recipe"]
    selected = plan.get("selected_capability") or {}
    selected_risk = str((selected or {}).get("risk_level") or "low")
    allowed_risk = str(args.allow_risk or args.max_risk)
    risk_ok = _risk_allowed(selected_risk, allowed_risk)
    out["risk_gate"] = {"selected": selected_risk, "allowed_max": allowed_risk, "allowed": risk_ok}
    if not risk_ok:
        out["status"] = "blocked_risk"
        out["message"] = f"Selected action risk '{selected_risk}' exceeds allowed execution risk '{allowed_risk}'"
        if args.json:
            print(json.dumps(out, indent=2))
        else:
            print(format_result_text(out))
        return 1

    pre_hooks, post_hooks = _select_hooks(
        recipe,
        pre_hooks=list(args.pre_hook or []),
        post_hooks=list(args.post_hook or []),
        auto_hooks=not args.no_auto_hooks,
    )
    out["pre_hooks"] = []
    out["post_hooks"] = []

    if args.dry_run or not args.yes:
        out["status"] = "dry_run"
        if not args.yes and not args.dry_run:
            out["message"] = "Confirmation required: pass --yes to execute"
        elif args.dry_run:
            out["message"] = "Dry run requested"
        if args.json:
            print(json.dumps(out, indent=2))
        else:
            print(format_result_text(out))
        return 0

    # Pre-hooks
    for hook in pre_hooks:
        out["pre_hooks"].append(_run_tvctl_hook(hook))

    try:
        exec_result = _execute_recipe(
            recipe,
            web_session=args.web_session,
            web_headed=bool(args.web_headed),
            web_keep_open=bool(args.web_keep_open),
            web_cwd=args.web_cwd,
            command_timeout_seconds=(
                None if args.command_timeout_seconds is None or args.command_timeout_seconds <= 0 else float(args.command_timeout_seconds)
            ),
            web_exec_timeout_seconds=(
                None if args.web_exec_timeout_seconds is None or args.web_exec_timeout_seconds <= 0 else float(args.web_exec_timeout_seconds)
            ),
            web_baseline_timeout_seconds=(
                None
                if args.web_baseline_timeout_seconds is None or args.web_baseline_timeout_seconds <= 0
                else float(args.web_baseline_timeout_seconds)
            ),
            debug_artifacts_mode=str(args.debug_artifacts or "on-failure"),
        )
    except Exception as e:  # noqa: BLE001
        out["status"] = "execution_error"
        out["message"] = str(e)
        details = getattr(e, "details", None)
        if isinstance(details, dict):
            out["execution"] = details
        if args.json:
            print(json.dumps(out, indent=2))
        else:
            print(format_result_text(out))
        return 1

    out["execution"] = exec_result

    # Post-hooks (best effort)
    for hook in post_hooks:
        try:
            out["post_hooks"].append(_run_tvctl_hook(hook))
        except Exception as e:  # noqa: BLE001
            out["post_hooks"].append({"hook": hook, "ok": False, "error": str(e)})

    if int(exec_result.get("returncode") or 0) != 0:
        out["status"] = "execution_failed"
    elif isinstance(exec_result.get("verification_result"), dict) and not bool(exec_result["verification_result"].get("ok")):
        out["status"] = "verification_failed"
    else:
        out["status"] = "executed"
    if out["status"] not in {"executed"} and not out.get("message"):
        out["message"] = "Command returned a non-zero exit code"
    if out["status"] == "verification_failed":
        out["message"] = "Recipe verification assertions failed after execution"

    if args.json:
        print(json.dumps(out, indent=2))
    else:
        print(format_result_text(out))
    return 0 if out["status"] == "executed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
