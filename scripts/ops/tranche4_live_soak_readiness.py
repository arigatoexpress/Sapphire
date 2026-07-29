#!/usr/bin/env python3
"""Read-only Tranche 4 live-soak readiness report.

This helper inspects Tranche 4 live flags, sanitized credential presence,
runtime artifact presence, and read-only service status. It never runs live
collectors, never writes runtime artifacts, and never publishes to the event bus.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OBSERVED = "OBSERVED"
UNKNOWN = "UNKNOWN"
TRUE_VALUES = {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class ArtifactSpec:
    surface: str
    kind: str
    patterns: tuple[str, ...]
    required_for_soak_evidence: bool = True


@dataclass(frozen=True)
class CredentialSpec:
    surface: str
    label: str
    names: tuple[str, ...]
    required_for_live: bool = True


@dataclass(frozen=True)
class SurfaceSpec:
    surface: str
    label: str
    live_flags: tuple[str, ...]
    bus_flags: tuple[str, ...]
    credentials: tuple[CredentialSpec, ...]
    artifacts: tuple[ArtifactSpec, ...]
    notes: tuple[str, ...] = ()


SURFACES: tuple[SurfaceSpec, ...] = (
    SurfaceSpec(
        surface="narrative_synthesis",
        label="Narrative synthesis",
        live_flags=("SAPPHIRE_NARRATIVE_LIVE",),
        bus_flags=("SAPPHIRE_NARRATIVE_LIVE_BUS",),
        credentials=(
            CredentialSpec(
                surface="narrative_synthesis",
                label="Gemini narrative key",
                names=("GEMINI_API_KEY", "GOOGLE_API_KEY"),
            ),
        ),
        artifacts=(
            ArtifactSpec(
                "narrative_synthesis",
                "correlator_input",
                ("data/correlated_signals/*/signals.jsonl",),
                required_for_soak_evidence=False,
            ),
            ArtifactSpec(
                "narrative_synthesis",
                "theses_output",
                ("data/narratives/*/theses.jsonl",),
            ),
        ),
        notes=(
            "Live Gemini requires SAPPHIRE_NARRATIVE_LIVE=1 plus a key; event-bus publishing is a separate gate.",
        ),
    ),
    SurfaceSpec(
        surface="macro_intel",
        label="Regulatory and macro intel",
        live_flags=("SAPPHIRE_MACRO_INTEL_LIVE",),
        bus_flags=("SAPPHIRE_MACRO_INTEL_LIVE_BUS",),
        credentials=(),
        artifacts=(
            ArtifactSpec("macro_intel", "events_output", ("data/macro/*/events.jsonl",)),
            ArtifactSpec("macro_intel", "calendar_output", ("data/macro/*/calendar.jsonl",)),
        ),
        notes=("Macro live HTTP is public-source only and still requires explicit opt-in.",),
    ),
    SurfaceSpec(
        surface="onchain_intel",
        label="On-chain intel",
        live_flags=(
            "SAPPHIRE_GLASSNODE_LIVE",
            "SAPPHIRE_SANTIMENT_LIVE",
            "SAPPHIRE_ETH_NODE_LIVE",
            "SAPPHIRE_SOL_NODE_LIVE",
        ),
        bus_flags=("SAPPHIRE_ONCHAIN_LIVE_BUS",),
        credentials=(
            CredentialSpec(
                surface="onchain_intel",
                label="Glassnode key",
                names=("GLASSNODE_API_KEY",),
            ),
            CredentialSpec(
                surface="onchain_intel",
                label="Santiment key",
                names=("SANTIMENT_API_KEY",),
            ),
            CredentialSpec(
                surface="onchain_intel",
                label="Ethereum RPC URL",
                names=("ETH_RPC_URL", "ETHEREUM_RPC_URL"),
            ),
            CredentialSpec(
                surface="onchain_intel",
                label="Solana RPC URL",
                names=("SOL_RPC_URL", "SOLANA_RPC_URL"),
            ),
        ),
        artifacts=(
            ArtifactSpec(
                "onchain_intel",
                "latest_snapshot",
                ("data/intelligence/latest/onchain_intel.json",),
            ),
            ArtifactSpec("onchain_intel", "archive_snapshot", ("data/onchain_intel/*.json",)),
        ),
        notes=("Provider live calls require both a provider gate and its credential/RPC URL.",),
    ),
    SurfaceSpec(
        surface="event_impact",
        label="Event-impact runtime",
        live_flags=(),
        bus_flags=("SAPPHIRE_EVENT_IMPACT_LIVE_BUS",),
        credentials=(),
        artifacts=(
            ArtifactSpec("event_impact", "model", ("data/event_impact/model_*.json",)),
            ArtifactSpec(
                "event_impact",
                "expected_reactions",
                ("data/event_impact/expected_reactions.jsonl",),
                required_for_soak_evidence=False,
            ),
        ),
        notes=(
            "Event-impact runtime is lookup-only; model rebuild is a separate operator-gated action.",
        ),
    ),
)


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def env_flag_status(name: str) -> dict[str, Any]:
    raw = os.environ.get(name)
    enabled = raw.strip().lower() in TRUE_VALUES if raw is not None else False
    if raw is None:
        state = "unset"
    elif enabled:
        state = "enabled"
    else:
        state = "set_nontrue"
    return {
        "claim": OBSERVED,
        "name": name,
        "enabled": enabled,
        "state": state,
    }


def read_secret_names(secret_file: Path) -> tuple[set[str], dict[str, Any]]:
    path = secret_file.expanduser()
    if not path.exists():
        return set(), {
            "claim": OBSERVED,
            "path": str(path),
            "state": "absent",
            "readable": False,
        }
    names: set[str] = set()
    try:
        with path.open(encoding="utf-8") as handle:
            for raw in handle:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key = line.split("=", 1)[0].strip()
                if key:
                    names.add(key)
    except OSError as exc:
        return set(), {
            "claim": UNKNOWN,
            "path": str(path),
            "state": "unreadable",
            "readable": False,
            "error_type": type(exc).__name__,
        }
    return names, {
        "claim": OBSERVED,
        "path": str(path),
        "state": "present",
        "readable": True,
        "keys_seen": len(names),
    }


def credential_status(
    spec: CredentialSpec, *, secret_names: set[str], secret_meta: dict[str, Any]
) -> dict[str, Any]:
    env_present = sorted(name for name in spec.names if os.environ.get(name, "") != "")
    file_present = sorted(name for name in spec.names if name in secret_names)
    present = bool(env_present or file_present)
    claim = OBSERVED
    if not present and secret_meta.get("claim") == UNKNOWN:
        claim = UNKNOWN
    return {
        "claim": claim,
        "surface": spec.surface,
        "label": spec.label,
        "names": list(spec.names),
        "present": present if claim == OBSERVED else None,
        "sources": {
            "env_names_present": env_present,
            "secret_file_names_present": file_present,
            "secret_file_state": secret_meta.get("state"),
        },
        "secret_values_redacted": True,
        "required_for_live": spec.required_for_live,
    }


def artifact_status(spec: ArtifactSpec, *, root: Path) -> dict[str, Any]:
    files: list[Path] = []
    errors: list[str] = []
    for pattern in spec.patterns:
        try:
            files.extend(path for path in root.glob(pattern) if path.is_file())
        except OSError as exc:
            errors.append(f"{pattern}: {type(exc).__name__}")
    unique_files = sorted(set(files), key=lambda path: path.stat().st_mtime if path.exists() else 0)
    latest = unique_files[-1] if unique_files else None
    latest_payload: dict[str, Any] | None = None
    if latest is not None:
        try:
            stat = latest.stat()
            envelope = Path(f"{latest}.envelope.json")
            latest_payload = {
                "path": relative_path(latest, root),
                "mtime": datetime.fromtimestamp(stat.st_mtime, tz=UTC)
                .isoformat(timespec="seconds")
                .replace("+00:00", "Z"),
                "bytes": stat.st_size,
                "envelope_present": envelope.exists(),
                "envelope_path": relative_path(envelope, root) if envelope.exists() else None,
            }
        except OSError as exc:
            errors.append(f"{latest}: {type(exc).__name__}")
    return {
        "claim": UNKNOWN if errors else OBSERVED,
        "surface": spec.surface,
        "kind": spec.kind,
        "patterns": list(spec.patterns),
        "present": bool(unique_files) if not errors else None,
        "count": len(unique_files),
        "latest": latest_payload,
        "required_for_soak_evidence": spec.required_for_soak_evidence,
        "errors": errors,
    }


def relative_path(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def safe_call(label: str, func: Any) -> dict[str, Any]:
    try:
        payload = func()
    except Exception as exc:  # noqa: BLE001 - readiness should degrade to unknown.
        return {
            "claim": UNKNOWN,
            "label": label,
            "ok": False,
            "error_type": type(exc).__name__,
        }
    return {
        "claim": OBSERVED,
        "label": label,
        "ok": True,
        "payload": sanitize_status_payload(payload),
    }


def sanitize_status_payload(payload: Any) -> Any:
    if isinstance(payload, dict):
        out: dict[str, Any] = {}
        for key, value in payload.items():
            key_text = str(key)
            if looks_sensitive_key(key_text):
                out[key_text] = "<redacted>"
            elif isinstance(value, dict | list):
                out[key_text] = sanitize_status_payload(value)
            elif isinstance(value, str) and looks_like_secret_value(value):
                out[key_text] = "<redacted>"
            else:
                out[key_text] = value
        return out
    if isinstance(payload, list):
        return [sanitize_status_payload(item) for item in payload]
    return payload


def looks_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return (
        "api_key" in lowered
        or "password" in lowered
        or "private_key" in lowered
        or "rpc_url" in lowered
        or lowered in {"token", "secret", "authorization"}
        or lowered.endswith("_token")
    )


def looks_like_secret_value(value: str) -> bool:
    lowered = value.lower()
    if "sk-" in lowered or "bearer " in lowered:
        return True
    return (
        len(value) >= 48
        and any(char.isdigit() for char in value)
        and any(char.isalpha() for char in value)
    )


def service_statuses(*, root: Path) -> list[dict[str, Any]]:
    statuses: list[dict[str, Any]] = []

    def narrative_status() -> dict[str, Any]:
        from lib.synthesis import narrative_engine
        from services.synthesis import run as synthesis_run

        return {
            "service": synthesis_run.status(),
            "engine": narrative_engine.status(),
        }

    def macro_status() -> dict[str, Any]:
        from services.macro_intel import run as macro_run

        return macro_run.status(output_root=root / "data" / "macro")

    def onchain_status() -> dict[str, Any]:
        from services.onchain_intel import service as onchain_service

        return onchain_service.build_status()

    def event_impact_status() -> dict[str, Any]:
        from services.event_impact.run import latest_model_path

        path = latest_model_path(root / "data" / "event_impact")
        return {
            "service": "event_impact",
            "latest_model_present": path is not None,
            "latest_model_path": relative_path(path, root) if path else None,
            "live_bus_env": os.environ.get("SAPPHIRE_EVENT_IMPACT_LIVE_BUS") == "1",
            "runtime": "lookup_only",
        }

    def integration_feed_status() -> dict[str, Any]:
        from lib.intelligence.tranche4_integration import feed_status_from_artifacts

        return feed_status_from_artifacts(root=root)

    for label, func in (
        ("narrative_synthesis", narrative_status),
        ("macro_intel", macro_status),
        ("onchain_intel", onchain_status),
        ("event_impact", event_impact_status),
        ("tranche4_integration_feed_status", integration_feed_status),
    ):
        statuses.append(safe_call(label, func))
    return statuses


def readiness_for_surface(
    surface: SurfaceSpec,
    *,
    flag_rows: list[dict[str, Any]],
    credential_rows: list[dict[str, Any]],
    artifact_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    names = set(surface.live_flags + surface.bus_flags)
    relevant_flags = [row for row in flag_rows if row["name"] in names]
    live_enabled = [row["name"] for row in relevant_flags if row.get("enabled")]
    relevant_credentials = [row for row in credential_rows if row["surface"] == surface.surface]
    credential_unknown = [row["label"] for row in relevant_credentials if row["claim"] == UNKNOWN]
    missing_credentials = [
        row["label"]
        for row in relevant_credentials
        if row["required_for_live"] and row["claim"] == OBSERVED and not row["present"]
    ]
    required_artifacts = [
        row
        for row in artifact_rows
        if row["surface"] == surface.surface and row["required_for_soak_evidence"]
    ]
    artifact_unknown = [row["kind"] for row in required_artifacts if row["claim"] == UNKNOWN]
    missing_artifacts = [
        row["kind"] for row in required_artifacts if row["claim"] == OBSERVED and not row["present"]
    ]
    dry_soak_ready = not live_enabled and not artifact_unknown
    if live_enabled:
        dry_soak_state = "blocked_live_flag_enabled"
    elif artifact_unknown:
        dry_soak_state = "unknown_artifact_state"
    elif missing_artifacts:
        dry_soak_state = "ready_needs_soak_artifact"
    else:
        dry_soak_state = "ready_with_artifact_evidence"

    if credential_unknown:
        live_enablement_state = "unknown_credentials"
    elif missing_credentials:
        live_enablement_state = "operator_action_required"
    elif surface.live_flags or surface.bus_flags:
        live_enablement_state = (
            "available_but_disabled" if not live_enabled else "enabled_in_environment"
        )
    else:
        live_enablement_state = "not_applicable"

    actions: list[str] = []
    for flag in surface.live_flags + surface.bus_flags:
        if flag not in live_enabled:
            actions.append(f"Keep {flag}=0/unset until dry-run soak evidence is reviewed.")
    for label in missing_credentials:
        actions.append(f"Add {label} only when the matching live gate is approved.")
    for kind in missing_artifacts:
        actions.append(f"Generate or observe {kind} before treating the soak as evidenced.")
    if credential_unknown:
        actions.append("Resolve unreadable secret-file state without printing secret values.")
    if not actions:
        actions.append("Continue dry-run soak; do not enable live flags from this harness.")

    return {
        "claim": OBSERVED if not credential_unknown and not artifact_unknown else UNKNOWN,
        "surface": surface.surface,
        "label": surface.label,
        "dry_soak_ready": dry_soak_ready,
        "dry_soak_state": dry_soak_state,
        "safe_defaults_observed": not live_enabled,
        "enabled_live_flags": live_enabled,
        "artifact_evidence": {
            "missing_required": missing_artifacts,
            "unknown_required": artifact_unknown,
        },
        "live_enablement_state": live_enablement_state,
        "credential_evidence": {
            "missing_required": missing_credentials,
            "unknown_required": credential_unknown,
        },
        "operator_actions": actions,
        "notes": list(surface.notes),
    }


def build_report(
    *,
    root: Path = ROOT,
    secret_file: Path | None = None,
    include_service_status: bool = True,
) -> dict[str, Any]:
    root = root.resolve()
    secret_names, secret_meta = read_secret_names(
        secret_file or Path.home() / ".sapphire" / "secrets.env"
    )

    flag_names: list[str] = []
    for surface in SURFACES:
        flag_names.extend(surface.live_flags)
        flag_names.extend(surface.bus_flags)
    live_flags = [env_flag_status(name) for name in sorted(set(flag_names))]

    credentials = [
        credential_status(spec, secret_names=secret_names, secret_meta=secret_meta)
        for surface in SURFACES
        for spec in surface.credentials
    ]
    artifacts = [
        artifact_status(spec, root=root) for surface in SURFACES for spec in surface.artifacts
    ]
    readiness = [
        readiness_for_surface(
            surface,
            flag_rows=live_flags,
            credential_rows=credentials,
            artifact_rows=artifacts,
        )
        for surface in SURFACES
    ]
    enabled_flags = [row["name"] for row in live_flags if row["enabled"]]
    unknowns = {
        "credentials": [row["label"] for row in credentials if row["claim"] == UNKNOWN],
        "artifacts": [
            f"{row['surface']}:{row['kind']}" for row in artifacts if row["claim"] == UNKNOWN
        ],
        "services": [],
    }
    statuses: list[dict[str, Any]] = []
    if include_service_status:
        statuses = service_statuses(root=root)
        unknowns["services"] = [row["label"] for row in statuses if row["claim"] == UNKNOWN]

    return {
        "schema_version": 1,
        "mode": "read_only_tranche4_live_soak_readiness",
        "generated_at": utc_now(),
        "root": str(root),
        "claim_labels": [OBSERVED, UNKNOWN],
        "safety": {
            "external_writes_attempted": False,
            "event_bus_publish_attempted": False,
            "live_flags_enabled_by_harness": False,
            "secret_values_redacted": True,
        },
        "secret_file": secret_meta,
        "live_flags": live_flags,
        "credentials": credentials,
        "artifacts": artifacts,
        "service_statuses": statuses,
        "readiness": readiness,
        "summary": {
            "safe_defaults_observed": not enabled_flags,
            "enabled_live_flags": enabled_flags,
            "surfaces": len(SURFACES),
            "dry_soak_ready": sum(1 for row in readiness if row["dry_soak_ready"]),
            "with_required_artifact_evidence": sum(
                1
                for row in readiness
                if not row["artifact_evidence"]["missing_required"]
                and not row["artifact_evidence"]["unknown_required"]
            ),
            "unknowns": unknowns,
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Tranche 4 Live-Soak Readiness",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Root: `{report['root']}`",
        f"- Safe defaults observed: `{report['summary']['safe_defaults_observed']}`",
        f"- Enabled live flags: `{', '.join(report['summary']['enabled_live_flags']) or 'none'}`",
        f"- Harness writes attempted: `{report['safety']['external_writes_attempted']}`",
        f"- Event-bus publish attempted: `{report['safety']['event_bus_publish_attempted']}`",
        "",
        "## Live Flags",
        "",
        "| Claim | Flag | State | Enabled |",
        "|---|---|---:|---:|",
    ]
    for row in report["live_flags"]:
        lines.append(f"| {row['claim']} | `{row['name']}` | {row['state']} | {row['enabled']} |")

    lines.extend(
        [
            "",
            "## Credentials",
            "",
            "| Claim | Surface | Credential | Present | Sources |",
            "|---|---|---|---:|---|",
        ]
    )
    for row in report["credentials"]:
        sources = []
        if row["sources"]["env_names_present"]:
            sources.append("env")
        if row["sources"]["secret_file_names_present"]:
            sources.append("secret-file")
        lines.append(
            f"| {row['claim']} | {row['surface']} | {row['label']} | "
            f"{row['present']} | {', '.join(sources) or row['sources']['secret_file_state']} |"
        )

    lines.extend(
        [
            "",
            "## Artifacts",
            "",
            "| Claim | Surface | Kind | Present | Count | Latest | Envelope |",
            "|---|---|---|---:|---:|---|---:|",
        ]
    )
    for row in report["artifacts"]:
        latest = row["latest"] or {}
        lines.append(
            f"| {row['claim']} | {row['surface']} | {row['kind']} | {row['present']} | "
            f"{row['count']} | `{latest.get('path') or ''}` | {latest.get('envelope_present')} |"
        )

    lines.extend(
        [
            "",
            "## Readiness",
            "",
            "| Claim | Surface | Dry Soak | Safe Defaults | Live Enablement | Actions |",
            "|---|---|---|---:|---|---|",
        ]
    )
    for row in report["readiness"]:
        action = row["operator_actions"][0] if row["operator_actions"] else ""
        lines.append(
            f"| {row['claim']} | {row['surface']} | {row['dry_soak_state']} | "
            f"{row['safe_defaults_observed']} | {row['live_enablement_state']} | {action} |"
        )

    unknowns = report["summary"]["unknowns"]
    lines.extend(
        [
            "",
            "## Unknowns",
            "",
            f"- Credentials: `{', '.join(unknowns['credentials']) or 'none'}`",
            f"- Artifacts: `{', '.join(unknowns['artifacts']) or 'none'}`",
            f"- Services: `{', '.join(unknowns['services']) or 'none'}`",
            "",
        ]
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument(
        "--secret-file", type=Path, default=Path.home() / ".sapphire" / "secrets.env"
    )
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    parser.add_argument(
        "--no-service-status",
        action="store_true",
        help="Skip read-only imports/status calls and report only env/artifact facts.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_report(
        root=args.root,
        secret_file=args.secret_file,
        include_service_status=not args.no_service_status,
    )
    if args.format == "json":
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_markdown(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
