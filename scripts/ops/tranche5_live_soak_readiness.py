#!/usr/bin/env python3
"""Dry-run/live-soak readiness harness for Tranche 5 intelligence surfaces.

The harness is intentionally read-only by default. It inventories live gates,
cache/counter directories, latest generated artifacts, LaunchAgent templates,
and safe local status commands for the Tranche 5 daemons and plugin tools. It
does not call live APIs, send Telegram messages, place trades, install
LaunchAgents, mutate event-bus state, or read secret values.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
PYTHON = sys.executable or "python3"

SECRETISH_RE = re.compile(
    r"(?i)(api[_-]?key|secret|token|password|private[_-]?key|authorization)\s*[=:]\s*['\"]?[^'\"\s]+"
)
LONG_TOKEN_RE = re.compile(r"\b(?:gho_|ghp_|sk-|xoxb-|ya29\.)[A-Za-z0-9._/-]{12,}\b")


@dataclass(frozen=True)
class CommandSpec:
    label: str
    argv: tuple[str, ...]
    stdin_json: dict[str, Any] | None = None
    expected_mode: str = "status"

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["argv"] = list(self.argv)
        if self.stdin_json is not None:
            out["stdin_json"] = self.stdin_json
        return out


@dataclass(frozen=True)
class SurfaceSpec:
    surface_id: str
    label: str
    kind: str
    owners: tuple[str, ...]
    live_flags: tuple[str, ...] = ()
    publish_flags: tuple[str, ...] = ()
    cache_dirs: tuple[Path, ...] = ()
    counter_globs: tuple[str, ...] = ()
    artifact_globs: tuple[str, ...] = ()
    required_files: tuple[Path, ...] = ()
    launchagent_templates: tuple[Path, ...] = ()
    status_commands: tuple[CommandSpec, ...] = ()
    safety_notes: tuple[str, ...] = ()


Runner = Callable[[CommandSpec, Path, float], dict[str, Any]]


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _home_cache(*parts: str) -> Path:
    return Path.home().joinpath(".cache", "sapphire", *parts)


def _repo(*parts: str) -> Path:
    return ROOT.joinpath(*parts)


SURFACES: tuple[SurfaceSpec, ...] = (
    SurfaceSpec(
        surface_id="narrative_synthesis",
        label="Narrative Synthesis",
        kind="daemon+plugin",
        owners=("services/synthesis", "plugins/claw-sapphire/tools/narrative_synthesis.py"),
        live_flags=("SAPPHIRE_NARRATIVE_LIVE",),
        publish_flags=("SAPPHIRE_NARRATIVE_LIVE_BUS",),
        cache_dirs=(
            _home_cache("narrative_synthesis"),
            _home_cache("narrative_synthesis_service"),
        ),
        counter_globs=("~/.cache/sapphire/narrative_synthesis/counters.json",),
        artifact_globs=(
            "data/narratives/*/theses.jsonl",
            "data/narratives/*/theses.jsonl.envelope.json",
        ),
        required_files=(
            _repo("lib/synthesis/narrative_engine.py"),
            _repo("services/synthesis/run.py"),
            _repo("plugins/claw-sapphire/tools/internal/narrative_synthesis.py"),
        ),
        launchagent_templates=(
            _repo("services/synthesis/launchagent/com.sapphire.narrative-synthesis.plist.template"),
        ),
        status_commands=(
            CommandSpec("service status", (PYTHON, "services/synthesis/run.py", "status")),
            CommandSpec(
                "plugin status",
                (PYTHON, "plugins/claw-sapphire/tools/narrative_synthesis.py"),
                {"action": "status"},
            ),
        ),
        safety_notes=("dry-run default", "live Gemini requires env gate, key, sensitivity pass"),
    ),
    SurfaceSpec(
        surface_id="macro_intel",
        label="Regulatory + Macro Intelligence",
        kind="daemon+plugin",
        owners=("services/macro_intel", "plugins/claw-sapphire/tools/macro_intel.py"),
        live_flags=("SAPPHIRE_MACRO_INTEL_LIVE",),
        publish_flags=("SAPPHIRE_MACRO_INTEL_LIVE_BUS",),
        cache_dirs=(_home_cache("macro"),),
        counter_globs=("~/.cache/sapphire/macro/*/counters.json",),
        artifact_globs=(
            "data/macro/*/events.jsonl",
            "data/macro/*/calendar.jsonl",
            "data/macro/*/events.jsonl.envelope.json",
            "data/macro/*/calendar.jsonl.envelope.json",
        ),
        required_files=(
            _repo("lib/macro/sources.py"),
            _repo("services/macro_intel/run.py"),
            _repo("plugins/claw-sapphire/tools/internal/macro_intel.py"),
        ),
        launchagent_templates=(
            _repo("services/macro_intel/launchagent/com.sapphire.macro-intel.plist.template"),
        ),
        status_commands=(
            CommandSpec("service status", (PYTHON, "services/macro_intel/run.py", "status")),
            CommandSpec(
                "plugin status",
                (PYTHON, "plugins/claw-sapphire/tools/macro_intel.py"),
                {"action": "status"},
            ),
            CommandSpec(
                "plugin calendar dry-run",
                (PYTHON, "plugins/claw-sapphire/tools/macro_intel.py"),
                {"action": "calendar", "hours": 24},
                expected_mode="dry-run",
            ),
        ),
        safety_notes=("official-source HTTP disabled unless live gate is set",),
    ),
    SurfaceSpec(
        surface_id="cross_asset",
        label="Cross-Asset Regime Intelligence",
        kind="daemon+plugin",
        owners=("services/cross_asset", "plugins/claw-sapphire/tools/cross_asset_intel.py"),
        live_flags=("SAPPHIRE_CROSS_ASSET_LIVE",),
        cache_dirs=(_home_cache("cross_asset"),),
        artifact_globs=(
            "data/cross_asset/*/matrix.json",
            "data/cross_asset/*/regimes.jsonl",
            "data/cross_asset/*/breakdowns.jsonl",
            "data/cross_asset/*/lead_lag.json",
        ),
        required_files=(
            _repo("lib/cross_asset/sources.py"),
            _repo("services/cross_asset/run.py"),
            _repo("plugins/claw-sapphire/tools/internal/cross_asset_intel.py"),
        ),
        status_commands=(
            CommandSpec(
                "plugin status",
                (PYTHON, "plugins/claw-sapphire/tools/cross_asset_intel.py"),
                {"action": "status"},
            ),
        ),
        safety_notes=("live OHLCV adapters require explicit live argument plus env gate",),
    ),
    SurfaceSpec(
        surface_id="onchain_intel",
        label="On-Chain Intelligence",
        kind="daemon+plugin",
        owners=("services/onchain_intel", "plugins/claw-sapphire/tools/onchain_intel.py"),
        live_flags=(
            "SAPPHIRE_GLASSNODE_LIVE",
            "SAPPHIRE_SANTIMENT_LIVE",
            "SAPPHIRE_ETH_NODE_LIVE",
            "SAPPHIRE_SOL_NODE_LIVE",
        ),
        publish_flags=("SAPPHIRE_ONCHAIN_LIVE_BUS",),
        cache_dirs=(Path.home() / ".sapphire" / "onchain_intel",),
        counter_globs=("~/.sapphire/onchain_intel/usage.json",),
        artifact_globs=(
            "data/intelligence/latest/onchain_intel.json",
            "data/intelligence/latest/onchain_intel.json.envelope.json",
            "data/onchain_intel/onchain_intel_*.json",
        ),
        required_files=(
            _repo("services/onchain_intel/run.py"),
            _repo("services/onchain_intel/service.py"),
            _repo("plugins/claw-sapphire/tools/internal/onchain_intel.py"),
        ),
        launchagent_templates=(
            _repo("services/onchain_intel/launchagent/com.sapphire.onchain-intel.plist.template"),
        ),
        status_commands=(
            CommandSpec("service status", (PYTHON, "services/onchain_intel/run.py", "status")),
            CommandSpec(
                "plugin status",
                (PYTHON, "plugins/claw-sapphire/tools/onchain_intel.py"),
                {"action": "status"},
            ),
        ),
        safety_notes=("wallet_keys_required=false", "provider live calls are per-provider gated"),
    ),
    SurfaceSpec(
        surface_id="counterparty_intel",
        label="Hyperliquid Counter-Party Intelligence",
        kind="daemon+plugin",
        owners=("services/counterparty", "plugins/claw-sapphire/tools/counterparty_intel.py"),
        live_flags=("SAPPHIRE_HYPERLIQUID_LIVE",),
        cache_dirs=(_home_cache("counterparty_intel"),),
        counter_globs=("~/.cache/sapphire/counterparty_intel/counters.json",),
        artifact_globs=(
            "data/counterparty/*/counterparty_signals.json",
            "data/counterparty/*/counterparty_signals.json.envelope.json",
        ),
        required_files=(
            _repo("services/counterparty/run.py"),
            _repo("lib/counterparty/sources.py"),
            _repo("plugins/claw-sapphire/tools/internal/counterparty_intel.py"),
        ),
        status_commands=(
            CommandSpec(
                "plugin status",
                (PYTHON, "plugins/claw-sapphire/tools/counterparty_intel.py"),
                {"action": "status"},
            ),
        ),
        safety_notes=("public-data only", "no wallet keys", "no orders"),
    ),
    SurfaceSpec(
        surface_id="event_impact",
        label="Historical Event-Impact Modeling",
        kind="builder+plugin+runtime",
        owners=("services/event_impact", "plugins/claw-sapphire/tools/event_impact.py"),
        live_flags=("SAPPHIRE_EVENT_IMPACT_REBUILD",),
        publish_flags=("SAPPHIRE_EVENT_IMPACT_LIVE_BUS",),
        cache_dirs=(_home_cache("event_impact"),),
        artifact_globs=(
            "data/event_impact/model_*.json",
            "data/event_impact/model_*.json.envelope.json",
        ),
        required_files=(
            _repo("services/event_impact/run.py"),
            _repo("services/event_impact/build.py"),
            _repo("plugins/claw-sapphire/tools/internal/event_impact.py"),
        ),
        status_commands=(
            CommandSpec(
                "plugin corpus",
                (PYTHON, "plugins/claw-sapphire/tools/event_impact.py"),
                {"action": "corpus"},
            ),
        ),
        safety_notes=("rebuild fetches OHLCV only when env gate is set",),
    ),
    SurfaceSpec(
        surface_id="adversarial_defense",
        label="Adversarial Signal Defense",
        kind="daemon",
        owners=("services/adversarial", "lib/security/adversarial_detectors.py"),
        live_flags=("SAPPHIRE_ADVERSARIAL_QUARANTINE",),
        cache_dirs=(_repo("data/security/adversarial/quarantine"),),
        artifact_globs=("data/security/adversarial/quarantine/*-adversarial-report.json",),
        required_files=(
            _repo("services/adversarial/run.py"),
            _repo("lib/security/adversarial_detectors.py"),
            _repo("lib/security/adversarial_telemetry.py"),
        ),
        status_commands=(
            CommandSpec("service status", (PYTHON, "services/adversarial/run.py", "status")),
        ),
        safety_notes=("quarantine copy requires explicit env gate", "does not mutate upstream signals"),
    ),
)


def _sanitize(value: str, *, limit: int = 2000) -> str:
    text = SECRETISH_RE.sub(r"\1=[redacted]", value or "")
    text = LONG_TOKEN_RE.sub("[redacted-token]", text)
    return text[:limit]


def _sanitize_command_result(result: dict[str, Any]) -> dict[str, Any]:
    sanitized = dict(result)
    for key in ("stdout", "stderr", "error"):
        if key in sanitized:
            sanitized[key] = _sanitize(str(sanitized[key]))
    return sanitized


def _truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _env_report(names: Sequence[str]) -> list[dict[str, Any]]:
    return [
        {
            "name": name,
            "present": name in os.environ,
            "enabled": _truthy_env(name),
            "value_redacted": True,
        }
        for name in names
    ]


def _count_files(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return 1
    try:
        return sum(1 for item in path.rglob("*") if item.is_file())
    except OSError:
        return 0


def _path_summary(path: Path) -> dict[str, Any]:
    try:
        stat = path.stat()
    except OSError:
        return {"path": str(path), "exists": False}
    return {
        "path": str(path),
        "exists": True,
        "is_dir": path.is_dir(),
        "bytes": stat.st_size if path.is_file() else None,
        "file_count": _count_files(path) if path.is_dir() else 1,
        "mtime": datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat(),
    }


def _expand_glob(pattern: str) -> list[Path]:
    expanded = Path(pattern).expanduser()
    if not expanded.is_absolute():
        expanded = ROOT / expanded
    return sorted(expanded.parent.glob(expanded.name))


def _jsonl_line_count(path: Path) -> int | None:
    if path.suffix != ".jsonl":
        return None
    try:
        return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    except OSError:
        return None


def _latest_artifacts(patterns: Sequence[str], *, limit: int = 3) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for pattern in patterns:
        matches = _expand_glob(pattern)
        matches.sort(key=lambda path: path.stat().st_mtime if path.exists() else 0, reverse=True)
        latest: list[dict[str, Any]] = []
        for path in matches[:limit]:
            summary = _path_summary(path)
            line_count = _jsonl_line_count(path)
            if line_count is not None:
                summary["jsonl_rows"] = line_count
            latest.append(summary)
        rows.append(
            {
                "pattern": pattern,
                "match_count": len(matches),
                "latest": latest,
            }
        )
    return rows


def _cache_reports(spec: SurfaceSpec) -> list[dict[str, Any]]:
    return [_path_summary(path.expanduser()) for path in spec.cache_dirs]


def _counter_reports(spec: SurfaceSpec) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for pattern in spec.counter_globs:
        matches = _expand_glob(pattern)
        rows.append(
            {
                "pattern": pattern,
                "match_count": len(matches),
                "latest": [_path_summary(path) for path in matches[-3:]],
            }
        )
    return rows


def _run_command(spec: CommandSpec, cwd: Path, timeout_seconds: float) -> dict[str, Any]:
    stdin = None
    if spec.stdin_json is not None:
        stdin = json.dumps(spec.stdin_json)
    try:
        proc = subprocess.run(
            list(spec.argv),
            cwd=cwd,
            input=stdin,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except Exception as exc:  # noqa: BLE001 - readiness should report, not crash.
        return {
            "label": spec.label,
            "ran": True,
            "ok": False,
            "exit_code": None,
            "error": type(exc).__name__,
            "stdout": "",
            "stderr": "",
        }
    return {
        "label": spec.label,
        "ran": True,
        "ok": proc.returncode == 0,
        "exit_code": proc.returncode,
        "stdout": _sanitize(proc.stdout.strip()),
        "stderr": _sanitize(proc.stderr.strip()),
    }


def _status_command_reports(
    spec: SurfaceSpec,
    *,
    run_status: bool,
    runner: Runner | None,
    timeout_seconds: float,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for command in spec.status_commands:
        row = command.to_dict()
        row["safe_local_only"] = True
        row["ran"] = False
        if run_status:
            raw_result = (
                runner(command, ROOT, timeout_seconds)
                if runner
                else _run_command(command, ROOT, timeout_seconds)
            )
            result = _sanitize_command_result(raw_result)
            row["result"] = result
            row["ran"] = True
        rows.append(row)
    return rows


def _surface_status(
    *,
    missing_required: list[str],
    enabled_live_flags: list[str],
    command_rows: list[dict[str, Any]],
) -> str:
    if missing_required:
        return "fail"
    command_failures = [
        row
        for row in command_rows
        if row.get("ran") and row.get("result", {}).get("ok") is False
    ]
    if command_failures:
        return "fail"
    if enabled_live_flags:
        return "warn"
    return "pass"


def collect_readiness(
    *,
    run_status: bool = False,
    runner: Runner | None = None,
    timeout_seconds: float = 10.0,
) -> dict[str, Any]:
    surfaces: list[dict[str, Any]] = []
    enabled_live_flags: list[str] = []
    missing_required_total = 0
    missing_artifact_patterns_total = 0
    surfaces_missing_artifacts = 0
    command_failures = 0

    for spec in SURFACES:
        live_env = _env_report(spec.live_flags)
        publish_env = _env_report(spec.publish_flags)
        enabled = [row["name"] for row in [*live_env, *publish_env] if row["enabled"]]
        enabled_live_flags.extend(enabled)
        missing_required = [str(path) for path in spec.required_files if not path.exists()]
        missing_required_total += len(missing_required)
        commands = _status_command_reports(
            spec,
            run_status=run_status,
            runner=runner,
            timeout_seconds=timeout_seconds,
        )
        command_failures += sum(
            1 for row in commands if row.get("ran") and row.get("result", {}).get("ok") is False
        )
        artifacts = _latest_artifacts(spec.artifact_globs)
        missing_artifact_patterns = [
            row["pattern"] for row in artifacts if row["match_count"] == 0
        ]
        missing_artifact_patterns_total += len(missing_artifact_patterns)
        if missing_artifact_patterns:
            surfaces_missing_artifacts += 1
        surface = {
            "id": spec.surface_id,
            "label": spec.label,
            "kind": spec.kind,
            "owners": list(spec.owners),
            "status": _surface_status(
                missing_required=missing_required,
                enabled_live_flags=enabled,
                command_rows=commands,
            ),
            "live_flags": live_env,
            "publish_flags": publish_env,
            "enabled_live_or_publish_flags": enabled,
            "cache_dirs": _cache_reports(spec),
            "counters": _counter_reports(spec),
            "artifacts": artifacts,
            "missing_artifact_patterns": missing_artifact_patterns,
            "required_files": [_path_summary(path) for path in spec.required_files],
            "missing_required_files": missing_required,
            "launchagent_templates": [
                _path_summary(path) for path in spec.launchagent_templates
            ],
            "dry_run_status_commands": commands,
            "safety_notes": list(spec.safety_notes),
        }
        surfaces.append(surface)

    statuses = [surface["status"] for surface in surfaces]
    if "fail" in statuses:
        overall = "fail"
    elif "warn" in statuses or enabled_live_flags:
        overall = "warn"
    else:
        overall = "pass"
    return {
        "schema_version": 1,
        "generated_at": _utc_now(),
        "mode": "read-only-local",
        "status": overall,
        "repo_root": str(ROOT),
        "summary": {
            "surfaces": len(surfaces),
            "pass": statuses.count("pass"),
            "warn": statuses.count("warn"),
            "fail": statuses.count("fail"),
            "enabled_live_or_publish_flags": sorted(set(enabled_live_flags)),
            "missing_required_files": missing_required_total,
            "missing_artifact_patterns": missing_artifact_patterns_total,
            "surfaces_missing_artifacts": surfaces_missing_artifacts,
            "status_commands_ran": bool(run_status),
            "status_command_failures": command_failures,
        },
        "guardrails": [
            "No live API calls are made by this harness.",
            "No Telegram messages are sent.",
            "No trading or order-execution paths are invoked.",
            "No LaunchAgents are loaded, unloaded, installed, or edited.",
            "Secret-like command output is redacted before rendering.",
        ],
        "surfaces": surfaces,
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Tranche 5 Live-Soak Readiness",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Mode: `{report['mode']}`",
        f"- Status: `{report['status']}`",
        f"- Surfaces: `{summary['surfaces']}` pass=`{summary['pass']}` warn=`{summary['warn']}` fail=`{summary['fail']}`",
        f"- Enabled live/publish flags: `{', '.join(summary['enabled_live_or_publish_flags']) or 'none'}`",
        f"- Missing artifact patterns: `{summary['missing_artifact_patterns']}` across `{summary['surfaces_missing_artifacts']}` surfaces",
        f"- Status commands ran: `{str(summary['status_commands_ran']).lower()}`",
        "",
        "## Guardrails",
        "",
    ]
    lines.extend(f"- {item}" for item in report["guardrails"])
    lines.extend(["", "## Surfaces", ""])
    for surface in report["surfaces"]:
        enabled = ", ".join(surface["enabled_live_or_publish_flags"]) or "none"
        cache_count = sum(1 for row in surface["cache_dirs"] if row["exists"])
        artifact_count = sum(row["match_count"] for row in surface["artifacts"])
        missing_artifacts = surface["missing_artifact_patterns"]
        missing = len(surface["missing_required_files"])
        lines.extend(
            [
                f"### {surface['label']}",
                "",
                f"- Status: `{surface['status']}`",
                f"- Owners: `{', '.join(surface['owners'])}`",
                f"- Enabled live/publish flags: `{enabled}`",
                f"- Existing cache dirs: `{cache_count}/{len(surface['cache_dirs'])}`",
                f"- Latest artifact matches: `{artifact_count}`",
                f"- Missing artifact patterns: `{len(missing_artifacts)}`",
                f"- Missing required files: `{missing}`",
            ]
        )
        if missing_artifacts:
            lines.append("- Missing artifact pattern list:")
            lines.extend(f"  - `{pattern}`" for pattern in missing_artifacts)
        lines.append("- Safe commands:")
        for command in surface["dry_run_status_commands"]:
            cmd = " ".join(command["argv"])
            stdin = command.get("stdin_json")
            suffix = f" stdin={json.dumps(stdin, sort_keys=True)}" if stdin else ""
            if command.get("ran"):
                result = command.get("result", {})
                lines.append(
                    f"  - `{command['label']}` exit=`{result.get('exit_code')}` ok=`{result.get('ok')}`: `{cmd}`{suffix}"
                )
            else:
                lines.append(f"  - `{command['label']}`: `{cmd}`{suffix}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of Markdown.")
    parser.add_argument(
        "--run-status",
        action="store_true",
        help="Run known-safe local status/dry-run guard commands. Never enables live flags.",
    )
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero on warn/fail status. Default is report-only exit 0.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = collect_readiness(run_status=args.run_status, timeout_seconds=args.timeout_seconds)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_markdown(report), end="")
    if args.strict and report["status"] != "pass":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
