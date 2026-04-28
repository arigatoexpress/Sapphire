#!/usr/bin/env python3
"""Enumerate and probe Sapphire production readiness surfaces.

The default sweep is read-only: repo/worktree state, LaunchAgents, local
endpoints, safety reports, routine soak state, and Google/GCP metadata. Optional
flags perform bounded live probes that intentionally avoid secret rendering:
Telegram Bot API read probes and tiny GCS/BigQuery write evidence.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROJECT = "tho-ai-agent"
DEFAULT_REGION = "us-central1"
DEFAULT_BUCKET = "sapphire-data-lake"
DEFAULT_DATASET = "sapphire"
DEFAULT_BQ_TABLE = "production_readiness_probes"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
DEFAULT_SECRET_ENV = Path.home() / ".sapphire" / "secrets.env"
SAPPHIRE_SECRETS_DIR = Path.home() / ".config" / "sapphire-secrets"
GEMINI_PROBE_PROMPT = "Return exactly SAPPHIRE_GEMINI_PROBE_OK and nothing else."
GEMINI_PROBE_RESPONSE = "SAPPHIRE_GEMINI_PROBE_OK"


@dataclass
class Check:
    category: str
    name: str
    status: str
    evidence: str
    duration_ms: int = 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    started = time.perf_counter()
    checks: list[Check] = []

    env = load_secret_env(args.secret_env)
    checks.extend(probe_repo())
    checks.extend(probe_launchagents())
    checks.extend(probe_local_endpoints(env))
    checks.extend(probe_safety())
    checks.extend(probe_routines(no_external=args.no_external))
    checks.extend(probe_github(no_external=args.no_external))
    checks.extend(probe_google_readiness(args, no_external=args.no_external))
    if args.include_gemini_live_probe and args.no_external:
        checks.append(Check("gemini", "vertex_live_probe", "SKIP", "--no-external"))
    elif args.include_gemini_live_probe:
        gemini_checks = probe_gemini_live(args)
        checks.extend(gemini_checks)
        apply_gemini_probe_to_google_gate(checks, gemini_checks)
    if args.include_telegram_probe:
        checks.extend(probe_telegram(env))
    if args.include_gcp_write_probe:
        checks.extend(probe_gcp_writes(args))

    report = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "duration_ms": int((time.perf_counter() - started) * 1000),
        "mode": {
            "external": not args.no_external,
            "gemini_live_probe": args.include_gemini_live_probe,
            "telegram_probe": args.include_telegram_probe,
            "gcp_write_probe": args.include_gcp_write_probe,
        },
        "summary": summarize(checks),
        "checks": [asdict(check) for check in checks],
    }

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        if args.format == "json":
            args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        else:
            args.output.write_text(render_markdown(report))

    if args.format == "json":
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_markdown(report), end="")
    return 0 if report["summary"]["fail"] == 0 else 20


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument("--region", default=DEFAULT_REGION)
    parser.add_argument("--bucket", default=DEFAULT_BUCKET)
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    parser.add_argument("--bq-table", default=DEFAULT_BQ_TABLE)
    parser.add_argument("--gemini-model", default=DEFAULT_GEMINI_MODEL)
    parser.add_argument("--secret-env", type=Path, default=DEFAULT_SECRET_ENV)
    parser.add_argument("--no-external", action="store_true")
    parser.add_argument("--include-gemini-live-probe", action="store_true")
    parser.add_argument("--include-telegram-probe", action="store_true")
    parser.add_argument("--include-gcp-write-probe", action="store_true")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--output", type=Path)
    return parser


def load_secret_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip().strip("'\"")
    for key in ("AUTH_PASSWORD", "AUTH_USERNAME", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        if os.environ.get(key):
            env[key] = os.environ[key]
    token_file = SAPPHIRE_SECRETS_DIR / "telegram_bot_token"
    chat_file = SAPPHIRE_SECRETS_DIR / "telegram_chat_id"
    if token_file.exists() and "TELEGRAM_BOT_TOKEN" not in env:
        env["TELEGRAM_BOT_TOKEN"] = token_file.read_text(encoding="utf-8").strip()
    if chat_file.exists() and "TELEGRAM_CHAT_ID" not in env:
        env["TELEGRAM_CHAT_ID"] = chat_file.read_text(encoding="utf-8").strip()
    return env


def probe_repo() -> list[Check]:
    checks: list[Check] = []
    status = run(["git", "status", "--porcelain=v1"], cwd=ROOT)
    branch = run(["git", "status", "--short", "--branch"], cwd=ROOT)
    dirty = bool(status.stdout.strip())
    checks.append(
        Check(
            "repo",
            "canonical_checkout_clean",
            "WARN" if dirty else "PASS",
            (branch.stdout.strip().splitlines()[0] if branch.stdout.strip() else "git status unavailable")
            + (f"; dirty entries={len(status.stdout.splitlines())}" if dirty else ""),
            status.duration_ms + branch.duration_ms,
        )
    )
    worktrees = run(["git", "worktree", "list"], cwd=ROOT)
    checks.append(
        Check(
            "repo",
            "worktree_inventory",
            "PASS" if worktrees.ok else "WARN",
            f"{len(worktrees.stdout.splitlines())} worktrees observed",
            worktrees.duration_ms,
        )
    )
    return checks


def probe_launchagents() -> list[Check]:
    expected = {
        "com.sapphire.dashboard": "always_on",
        "com.sapphire.control-plane": "always_on",
        "com.sapphire.signal-logger": "always_on",
        "com.sapphire.inference-proxy": "always_on",
        "com.sapphire.pm-bot": "always_on",
        "com.sapphire.heartbeat": "always_on",
        "com.sapphire.openbb-api": "always_on",
        "com.sapphire.cloudflare-tunnel": "always_on",
        "ai.hermes.gateway": "always_on",
        "actions.runner.arigatoexpress-Sapphire.ari-macbook-sapphire": "always_on",
        "com.sapphire.gcp-sync": "scheduled",
        "com.sapphire.content-engine": "scheduled",
        "com.sapphire.threat-refresh": "scheduled",
        "com.sapphire.morning-brief": "scheduled",
        "com.sapphire.backtest-weekly": "scheduled",
        "com.sapphire.security-pipeline": "scheduled",
        "com.sapphire.telemetry-collector": "scheduled",
        "com.sapphire.foundry-sync": "scheduled",
        "com.sapphire.tradingview-cdp": "scheduled",
    }
    listing = run(["launchctl", "list"])
    parsed = parse_launchctl_list(listing.stdout)
    checks: list[Check] = []
    for label, kind in expected.items():
        item = parsed.get(label)
        if not item:
            checks.append(Check("launchagent", label, "FAIL", "not loaded", listing.duration_ms))
            continue
        pid, status = item
        if kind == "always_on" and pid == "-":
            checks.append(Check("launchagent", label, "FAIL", f"loaded but not running (last_status={status})"))
        else:
            evidence = "running" if pid != "-" else f"loaded idle (last_status={status})"
            checks.append(Check("launchagent", label, "PASS", evidence))
    return checks


def parse_launchctl_list(output: str) -> dict[str, tuple[str, str]]:
    parsed: dict[str, tuple[str, str]] = {}
    for line in output.splitlines():
        parts = line.split()
        if len(parts) >= 3:
            parsed[parts[2]] = (parts[0], parts[1])
    return parsed


def probe_local_endpoints(env: dict[str, str]) -> list[Check]:
    checks = [
        http_check("local", "inference_proxy_health", "http://127.0.0.1:11435/health"),
        http_check("local", "inference_proxy_metrics", "http://127.0.0.1:11435/metrics"),
        http_check("local", "dashboard_health", "http://127.0.0.1:8080/health"),
        http_check("local", "control_plane_health", "http://127.0.0.1:8082/health"),
        http_check("local", "signal_logger_health", "http://127.0.0.1:18081/health"),
        tcp_check("local", "openbb_api_tcp", "127.0.0.1", 6900),
        tcp_check("local", "redis_tcp", "127.0.0.1", 6379),
        http_check("local", "ollama_tags", "http://127.0.0.1:11434/api/tags"),
        http_check("local", "tradingview_cdp_version", "http://127.0.0.1:9222/json/version", warn_on_error=True),
    ]
    password = env.get("AUTH_PASSWORD")
    if password:
        checks.append(
            http_check(
                "local",
                "dashboard_authenticated_root",
                "http://127.0.0.1:8080/",
                auth=("sapphire", password),
            )
        )
    else:
        checks.append(Check("local", "dashboard_authenticated_root", "WARN", "AUTH_PASSWORD not available to probe"))
    return checks


def probe_safety() -> list[Check]:
    result = run([sys.executable, "scripts/ops/safety_status_report.py", "--json"], cwd=ROOT, timeout=30)
    if not result.ok:
        return [Check("safety", "safety_status_report", "FAIL", short_error(result), result.duration_ms)]
    try:
        report = json.loads(result.stdout)
    except json.JSONDecodeError:
        return [Check("safety", "safety_status_report", "FAIL", "invalid JSON", result.duration_ms)]
    checks: list[Check] = []
    kill = report.get("kill_switch", {})
    active = bool(kill.get("inferred_active"))
    checks.append(Check("safety", "kill_switch_inactive", "PASS" if not active else "FAIL", f"inferred_active={active}"))
    firewall = report.get("confirmation_firewall", {})
    expired = int(firewall.get("expired_pending_count") or 0)
    checks.append(
        Check(
            "safety",
            "confirmation_firewall_expired_pending",
            "PASS" if expired == 0 else "WARN",
            f"expired_pending_count={expired}",
        )
    )
    schema = (report.get("autonomy_audit") or {}).get("schema", {})
    leaks = int(schema.get("unredacted_secret_risk_records") or 0)
    checks.append(Check("safety", "autonomy_audit_redaction", "PASS" if leaks == 0 else "FAIL", f"unredacted_secret_risk_records={leaks}"))
    return checks


def probe_routines(*, no_external: bool) -> list[Check]:
    cmd = [sys.executable, "scripts/ops/routine_soak_status.py", "--format", "json"]
    if no_external:
        cmd.append("--no-external")
    result = run(cmd, cwd=ROOT, timeout=60)
    if not result.ok:
        return [Check("routines", "routine_soak_status", "WARN", short_error(result), result.duration_ms)]
    try:
        report = json.loads(result.stdout)
    except json.JSONDecodeError:
        return [Check("routines", "routine_soak_status", "WARN", "invalid JSON", result.duration_ms)]
    checks: list[Check] = []
    for routine in report.get("routines", []):
        gate = routine.get("gate_state")
        latest = (routine.get("github_runs") or {}).get("latest_run") or {}
        status = "PASS" if gate == "ready_for_artifact_review" else "WARN"
        checks.append(
            Check(
                "routines",
                str(routine.get("id")),
                status,
                f"gate={gate}; latest={latest.get('event')}/{latest.get('conclusion')} {latest.get('created_at')}",
            )
        )
    return checks


def probe_github(*, no_external: bool) -> list[Check]:
    if no_external:
        return [Check("github", "open_prs", "SKIP", "--no-external")]
    result = run(["gh", "pr", "list", "--repo", "arigatoexpress/Sapphire", "--json", "number,title,state,isDraft"], cwd=ROOT)
    if not result.ok:
        return [Check("github", "open_prs", "WARN", short_error(result), result.duration_ms)]
    prs = json.loads(result.stdout or "[]")
    non_draft = [pr for pr in prs if not pr.get("isDraft")]
    status = "PASS" if not non_draft else "WARN"
    return [Check("github", "open_prs", status, f"open={len(prs)} non_draft={len(non_draft)}", result.duration_ms)]


def probe_google_readiness(args: argparse.Namespace, *, no_external: bool) -> list[Check]:
    cmd = [
        sys.executable,
        "scripts/ops/google_production_test_readiness.py",
        "--project",
        args.project,
        "--region",
        args.region,
        "--membership",
        "google_developer_premium",
        "--membership",
        "google_ai_plus",
        "--include-cost",
        "--format",
        "json",
    ]
    if no_external:
        cmd.append("--no-external")
    result = run(cmd, cwd=ROOT, timeout=90)
    if not result.ok:
        return [Check("gcp", "google_production_readiness", "WARN", short_error(result), result.duration_ms)]
    report = json.loads(result.stdout)
    summary = report.get("summary", {})
    gates = report.get("readiness_gates", [])
    checks = [
        Check(
            "gcp",
            "google_production_readiness_summary",
            "PASS" if summary.get("ready_gcp_projects") else "WARN",
            f"ready_projects={summary.get('ready_gcp_projects')}; vertex={summary.get('vertex_resource_totals')}; cost={summary.get('cost_posture_included')}",
            result.duration_ms,
        )
    ]
    for gate in gates:
        gate_status = str(gate.get("status"))
        status = "PASS" if gate_status == "pass" else ("WARN" if gate_status in {"manual_gate", "blocked", "unknown", "needs_attention"} else "FAIL")
        checks.append(Check("gcp", f"gate_{gate.get('id')}", status, f"{gate_status}: {gate.get('evidence')}"))
    return checks


def probe_telegram(env: dict[str, str]) -> list[Check]:
    token = env.get("TELEGRAM_BOT_TOKEN") or env.get("RELAY_READER_TOKEN")
    if not token:
        return [Check("telegram", "bot_api_get_me", "WARN", "token not available to probe")]
    checks = [
        telegram_check("bot_api_get_me", token, "getMe"),
        telegram_check("bot_api_get_webhook_info", token, "getWebhookInfo"),
    ]
    return checks


def probe_gcp_writes(args: argparse.Namespace) -> list[Check]:
    probe_id = datetime.now(UTC).strftime("sapphire-prod-readiness-%Y%m%dT%H%M%SZ")
    payload = {
        "probe_id": probe_id,
        "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
        "source": "production_readiness_sweep",
        "mode": "bounded_live_write_probe",
    }
    checks: list[Check] = []
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
        json.dump(payload, handle, sort_keys=True)
        handle.write("\n")
        temp_path = Path(handle.name)
    try:
        gcs_path = f"gs://{args.bucket}/ops/production-readiness/{probe_id}.json"
        gcs = run(["gcloud", "storage", "cp", str(temp_path), gcs_path], cwd=ROOT, timeout=60)
        checks.append(Check("gcp_write", "gcs_probe_object", "PASS" if gcs.ok else "FAIL", gcs_path if gcs.ok else short_error(gcs), gcs.duration_ms))

        table_ref = f"`{args.project}.{args.dataset}.{args.bq_table}`"
        create_sql = (
            f"CREATE TABLE IF NOT EXISTS {table_ref} "
            "(probe_id STRING, timestamp TIMESTAMP, source STRING, mode STRING)"
        )
        create = bq_query(args.project, create_sql)
        checks.append(Check("gcp_write", "bq_probe_table", "PASS" if create.ok else "FAIL", f"{args.dataset}.{args.bq_table}" if create.ok else short_error(create), create.duration_ms))
        if create.ok:
            insert_sql = (
                f"INSERT INTO {table_ref} (probe_id, timestamp, source, mode) "
                f"VALUES ('{probe_id}', CURRENT_TIMESTAMP(), 'production_readiness_sweep', 'bounded_live_write_probe')"
            )
            insert = bq_query(args.project, insert_sql)
            checks.append(Check("gcp_write", "bq_probe_insert", "PASS" if insert.ok else "FAIL", f"probe_id={probe_id}" if insert.ok else short_error(insert), insert.duration_ms))
    finally:
        with contextlib_suppress():
            temp_path.unlink()
    return checks


def probe_gemini_live(args: argparse.Namespace) -> list[Check]:
    env = os.environ.copy()
    env.update(
        {
            "GOOGLE_GENAI_USE_VERTEXAI": "true",
            "GOOGLE_CLOUD_PROJECT": args.project,
            "GOOGLE_CLOUD_LOCATION": args.region,
        }
    )
    with tempfile.TemporaryDirectory(prefix="sapphire-gemini-probe-") as probe_dir:
        result = run(
            [
                "gemini",
                "--skip-trust",
                "--approval-mode",
                "plan",
                "--output-format",
                "json",
                "--model",
                args.gemini_model,
                "--prompt",
                GEMINI_PROBE_PROMPT,
            ],
            cwd=Path(probe_dir),
            env=env,
            timeout=60,
        )
    if not result.ok:
        return [Check("gemini", "vertex_live_probe", "WARN", short_error(result), result.duration_ms)]
    payload = parse_json_from_mixed_output(result.stdout)
    if not isinstance(payload, dict):
        return [Check("gemini", "vertex_live_probe", "WARN", "invalid Gemini JSON output", result.duration_ms)]
    response = str(payload.get("response", "")).strip()
    stats = payload.get("stats") if isinstance(payload.get("stats"), dict) else {}
    model_stats = ((stats.get("models") or {}) if isinstance(stats, dict) else {}).get(args.gemini_model, {})
    tokens = model_stats.get("tokens", {}) if isinstance(model_stats, dict) else {}
    tools = stats.get("tools", {}) if isinstance(stats, dict) else {}
    ok = response == GEMINI_PROBE_RESPONSE and int(tools.get("totalCalls") or 0) == 0
    evidence = (
        f"model={args.gemini_model}; response_ok={ok}; "
        f"tool_calls={tools.get('totalCalls', 0)}; total_tokens={tokens.get('total', 'unknown')}"
    )
    return [Check("gemini", "vertex_live_probe", "PASS" if ok else "WARN", evidence, result.duration_ms)]


def parse_json_from_mixed_output(output: str) -> dict[str, Any] | None:
    start = output.find("{")
    end = output.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        parsed = json.loads(output[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def apply_gemini_probe_to_google_gate(checks: list[Check], gemini_checks: list[Check]) -> None:
    probe = next((check for check in gemini_checks if check.name == "vertex_live_probe"), None)
    if probe is None or probe.status != "PASS":
        return
    for check in checks:
        if check.category == "gcp" and check.name == "gate_gemini_api_or_vertex_live_calls":
            check.status = "PASS"
            check.evidence = f"pass: Vertex Gemini live probe succeeded; {probe.evidence}"
            return


def bq_query(project: str, sql: str) -> RunResult:
    return run(["bq", "query", "--project_id", project, "--use_legacy_sql=false", "--quiet", sql], cwd=ROOT, timeout=90)


def telegram_check(name: str, token: str, method: str) -> Check:
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/{method}", timeout=10) as response:
            body = response.read(1024 * 1024)
            status_code = response.status
    except urllib.error.HTTPError as exc:
        status_code = exc.code
        body = exc.read(1024 * 1024)
    except Exception as exc:
        return Check("telegram", name, "WARN", exc.__class__.__name__, int((time.perf_counter() - started) * 1000))
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        parsed = {}
    ok = bool(parsed.get("ok")) and status_code == 200
    result = parsed.get("result") if isinstance(parsed.get("result"), dict) else {}
    public_hint = ""
    if method == "getMe" and result.get("username"):
        public_hint = f"; username=@{result['username']}"
    elif method == "getWebhookInfo":
        public_hint = f"; pending_update_count={result.get('pending_update_count', 'unknown')}"
    return Check("telegram", name, "PASS" if ok else "WARN", f"http={status_code}{public_hint}", int((time.perf_counter() - started) * 1000))


def http_check(
    category: str,
    name: str,
    url: str,
    *,
    auth: tuple[str, str] | None = None,
    warn_on_error: bool = False,
) -> Check:
    started = time.perf_counter()
    request = urllib.request.Request(url)
    if auth:
        token = base64.b64encode(f"{auth[0]}:{auth[1]}".encode()).decode()
        request.add_header("Authorization", f"Basic {token}")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            status_code = response.status
            body = response.read(1024 * 1024)
    except urllib.error.HTTPError as exc:
        status_code = exc.code
        body = exc.read(4096)
    except Exception as exc:
        return Check(category, name, "WARN" if warn_on_error else "FAIL", exc.__class__.__name__, int((time.perf_counter() - started) * 1000))
    status = "PASS" if 200 <= status_code < 300 else ("WARN" if warn_on_error else "FAIL")
    hint = ""
    with contextlib_suppress():
        parsed = json.loads(body)
        if isinstance(parsed, dict):
            if parsed.get("status"):
                hint = f"; status={parsed.get('status')}"
            elif parsed.get("healthy") is not None:
                hint = f"; healthy={parsed.get('healthy')}"
    return Check(category, name, status, f"http={status_code}{hint}", int((time.perf_counter() - started) * 1000))


def tcp_check(category: str, name: str, host: str, port: int) -> Check:
    started = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=3):
            return Check(category, name, "PASS", f"{host}:{port} reachable", int((time.perf_counter() - started) * 1000))
    except OSError as exc:
        return Check(category, name, "FAIL", exc.__class__.__name__, int((time.perf_counter() - started) * 1000))


@dataclass
class RunResult:
    returncode: int
    stdout: str
    stderr: str
    duration_ms: int

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def run(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    timeout: int = 20,
    env: dict[str, str] | None = None,
) -> RunResult:
    started = time.perf_counter()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd or ROOT),
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        return RunResult(proc.returncode, proc.stdout, proc.stderr, int((time.perf_counter() - started) * 1000))
    except subprocess.TimeoutExpired as exc:
        return RunResult(124, exc.stdout or "", exc.stderr or "timeout", int((time.perf_counter() - started) * 1000))
    except FileNotFoundError as exc:
        return RunResult(127, "", str(exc), int((time.perf_counter() - started) * 1000))


def short_error(result: RunResult) -> str:
    text = (result.stderr or result.stdout or f"exit={result.returncode}").strip().splitlines()
    return (text[-1] if text else f"exit={result.returncode}")[:240]


def summarize(checks: list[Check]) -> dict[str, int]:
    return {
        "pass": sum(1 for check in checks if check.status == "PASS"),
        "warn": sum(1 for check in checks if check.status == "WARN"),
        "fail": sum(1 for check in checks if check.status == "FAIL"),
        "skip": sum(1 for check in checks if check.status == "SKIP"),
        "total": len(checks),
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Sapphire Production Readiness Sweep",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Duration: `{report['duration_ms']} ms`",
        f"- Checks: `{summary['pass']} pass`, `{summary['warn']} warn`, `{summary['fail']} fail`, `{summary['skip']} skip`",
        "",
        "| Category | Check | Status | Evidence |",
        "|---|---|---:|---|",
    ]
    for check in report["checks"]:
        lines.append(
            "| {category} | {name} | {status} | {evidence} |".format(
                category=check["category"],
                name=check["name"],
                status=check["status"],
                evidence=str(check["evidence"]).replace("|", "\\|").replace("\n", " "),
            )
        )
    return "\n".join(lines) + "\n"


class contextlib_suppress:
    def __enter__(self) -> None:
        return None

    def __exit__(self, *_exc: object) -> bool:
        return True


if __name__ == "__main__":
    raise SystemExit(main())
