#!/usr/bin/env python3
"""Read-only Sapphire failover posture check.

This script treats Windows GPU downtime as a degraded state, not an automatic
outage, when Mac/Pi local tiers or non-sensitive cloud fallback are healthy.
It can also include read-only Cloud Run readiness so local and GCP failover
coverage are visible in one operator payload.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any

DEFAULT_PROXY_URL = "http://127.0.0.1:11435"
DEFAULT_GCP_PROJECT = "sapphire-479610"
DEFAULT_GCP_REGION = "us-central1"
DEFAULT_CLOUD_RUN_SERVICES = (
    "sapphire-analytics",
    "sapphire-os-terminal",
    "project-go-forward",
    "cyber-threat-bot",
    "regional-intel-admin",
    "wildfire-frontend",
)


@dataclass(frozen=True)
class CloudRunService:
    name: str
    ready: bool
    latest_ready_revision: str
    url: str


def _fetch_json(url: str, timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": "sapphire-failover/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # nosec B310
        body = response.read()
    payload = json.loads(body.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("expected JSON object")
    return payload


def _fallback_payload_from_health(payload: dict[str, Any]) -> dict[str, Any]:
    failover = payload.get("failover")
    if isinstance(failover, dict):
        return failover

    endpoints = payload.get("endpoints") if isinstance(payload.get("endpoints"), dict) else {}
    healthy_local = [
        name for name in ("pi-rari1", "pi-rari2", "mac-local") if endpoints.get(name) == "healthy"
    ]
    healthy_cloud = endpoints.get("kimi-cloud") == "healthy"
    windows_healthy = endpoints.get("windows-gpu") == "healthy"
    if windows_healthy:
        mode = "primary"
        status = "ok"
    elif healthy_local:
        mode = "local_failover"
        status = "degraded"
    elif healthy_cloud:
        mode = "cloud_failover"
        status = "degraded"
    else:
        mode = "unavailable"
        status = "fail"
    return {
        "status": status,
        "service": payload.get("service", "inference-proxy"),
        "mode": mode,
        "active_route": "windows-gpu"
        if windows_healthy
        else (healthy_local[0] if healthy_local else ("kimi-cloud" if healthy_cloud else None)),
        "fallback_ready": bool(healthy_local or healthy_cloud),
        "windows_offline": not windows_healthy,
        "sensitive_cloud_block": True,
        "local_fallbacks": healthy_local,
        "cloud_fallbacks": ["kimi-cloud"] if healthy_cloud else [],
        "endpoints": endpoints,
        "recommended_actions": [
            "Proxy does not expose /failover/status yet; upgrade inference-proxy for full posture detail."
        ],
    }


def load_proxy_failover(base_url: str, timeout: float) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    base = base_url.rstrip("/")
    try:
        return _fetch_json(f"{base}/failover/status", timeout), warnings
    except urllib.error.HTTPError as exc:
        warnings.append(f"/failover/status returned HTTP {exc.code}; falling back to /health")
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"/failover/status probe failed: {type(exc).__name__}: {exc}")

    payload = _fetch_json(f"{base}/health", timeout)
    return _fallback_payload_from_health(payload), warnings


def _cloud_run_services_from_gcloud(
    *,
    project: str,
    region: str,
    timeout: float,
) -> list[CloudRunService]:
    if not shutil.which("gcloud"):
        raise RuntimeError("gcloud not found on PATH")
    result = subprocess.run(
        [
            "gcloud",
            "run",
            "services",
            "list",
            "--project",
            project,
            "--region",
            region,
            "--format=json",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    raw = json.loads(result.stdout or "[]")
    if not isinstance(raw, list):
        raise ValueError("unexpected gcloud services payload")
    services: list[CloudRunService] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        status = item.get("status") if isinstance(item.get("status"), dict) else {}
        name = str(metadata.get("name") or "")
        if not name:
            continue
        latest_ready = str(status.get("latestReadyRevisionName") or "")
        services.append(
            CloudRunService(
                name=name,
                ready=bool(latest_ready),
                latest_ready_revision=latest_ready,
                url=str(status.get("url") or ""),
            )
        )
    return services


def summarize_cloud_run(
    services: list[CloudRunService],
    *,
    required: tuple[str, ...] = DEFAULT_CLOUD_RUN_SERVICES,
) -> dict[str, Any]:
    by_name = {service.name: service for service in services}
    required_rows = [by_name.get(name) for name in required]
    missing = [name for name, row in zip(required, required_rows, strict=True) if row is None]
    not_ready = [row.name for row in required_rows if row is not None and not row.ready]
    ready = [row for row in required_rows if row is not None and row.ready]
    return {
        "checked": True,
        "required": list(required),
        "ready_count": len(ready),
        "missing": missing,
        "not_ready": not_ready,
        "ok": not missing and not not_ready,
        "services": [asdict(service) for service in sorted(services, key=lambda item: item.name)],
    }


def build_report(
    *,
    proxy: dict[str, Any],
    proxy_warnings: list[str],
    cloud_run: dict[str, Any] | None,
    require_primary: bool,
) -> dict[str, Any]:
    proxy_ok = bool(proxy.get("fallback_ready"))
    if require_primary:
        proxy_ok = proxy.get("mode") == "primary"
    gcp_ok = True if cloud_run is None else bool(cloud_run.get("ok"))
    ok = bool(proxy_ok and gcp_ok)
    blockers: list[str] = []
    if not proxy_ok:
        if require_primary:
            blockers.append("primary Windows GPU tier is required but not healthy")
        else:
            blockers.append("no local or cloud inference fallback is healthy")
    if cloud_run is not None and not gcp_ok:
        missing = ", ".join(cloud_run.get("missing", []))
        not_ready = ", ".join(cloud_run.get("not_ready", []))
        if missing:
            blockers.append(f"Cloud Run services missing: {missing}")
        if not_ready:
            blockers.append(f"Cloud Run services not ready: {not_ready}")
    return {
        "ok": ok,
        "mode": proxy.get("mode", "unknown"),
        "status": proxy.get("status", "unknown"),
        "active_route": proxy.get("active_route"),
        "windows_offline": bool(proxy.get("windows_offline")),
        "fallback_ready": bool(proxy.get("fallback_ready")),
        "proxy": proxy,
        "cloud_run": cloud_run or {"checked": False},
        "warnings": proxy_warnings,
        "blockers": blockers,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Sapphire System Failover Status",
        "",
        f"- ok: `{str(report['ok']).lower()}`",
        f"- mode: `{report['mode']}`",
        f"- active_route: `{report.get('active_route') or 'none'}`",
        f"- windows_offline: `{str(report['windows_offline']).lower()}`",
        f"- fallback_ready: `{str(report['fallback_ready']).lower()}`",
        "",
        "## Inference Mesh",
        "",
    ]
    endpoints = report["proxy"].get("endpoints", {})
    if isinstance(endpoints, dict):
        lines.extend(["| Endpoint | Status |", "|---|---|"])
        for name, status in endpoints.items():
            lines.append(f"| `{name}` | `{status}` |")
        lines.append("")
    actions = report["proxy"].get("recommended_actions", [])
    if actions:
        lines.extend(["## Recommended Actions", ""])
        for action in actions:
            lines.append(f"- {action}")
        lines.append("")
    cloud_run = report.get("cloud_run", {})
    if cloud_run.get("checked"):
        lines.extend(
            [
                "## Cloud Run",
                "",
                f"- ok: `{str(cloud_run.get('ok')).lower()}`",
                f"- ready_count: `{cloud_run.get('ready_count')}`",
                f"- missing: `{', '.join(cloud_run.get('missing') or []) or 'none'}`",
                f"- not_ready: `{', '.join(cloud_run.get('not_ready') or []) or 'none'}`",
                "",
            ]
        )
    if report["warnings"]:
        lines.extend(["## Warnings", ""])
        for warning in report["warnings"]:
            lines.append(f"- {warning}")
        lines.append("")
    if report["blockers"]:
        lines.extend(["## Blockers", ""])
        for blocker in report["blockers"]:
            lines.append(f"- {blocker}")
    return "\n".join(lines).rstrip() + "\n"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check Sapphire local/GCP failover posture")
    parser.add_argument("--proxy-url", default=DEFAULT_PROXY_URL)
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of Markdown")
    parser.add_argument(
        "--probe-gcp", action="store_true", help="Include read-only Cloud Run readiness"
    )
    parser.add_argument("--gcp-project", default=DEFAULT_GCP_PROJECT)
    parser.add_argument("--gcp-region", default=DEFAULT_GCP_REGION)
    parser.add_argument(
        "--cloud-run-service",
        action="append",
        default=[],
        help="Required Cloud Run service name; may be repeated",
    )
    parser.add_argument(
        "--require-primary",
        action="store_true",
        help="Fail unless Windows GPU primary is healthy",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    warnings: list[str] = []
    try:
        proxy, proxy_warnings = load_proxy_failover(args.proxy_url, args.timeout)
        warnings.extend(proxy_warnings)
    except Exception as exc:  # noqa: BLE001
        proxy = {
            "status": "fail",
            "service": "inference-proxy",
            "mode": "unavailable",
            "active_route": None,
            "fallback_ready": False,
            "windows_offline": True,
            "endpoints": {},
            "recommended_actions": ["Restore local inference-proxy before evaluating failover."],
        }
        warnings.append(f"proxy probe failed: {type(exc).__name__}: {exc}")

    cloud_run: dict[str, Any] | None = None
    if args.probe_gcp:
        required = tuple(args.cloud_run_service or DEFAULT_CLOUD_RUN_SERVICES)
        try:
            cloud_services = _cloud_run_services_from_gcloud(
                project=args.gcp_project,
                region=args.gcp_region,
                timeout=max(args.timeout, 10.0),
            )
            cloud_run = summarize_cloud_run(cloud_services, required=required)
        except Exception as exc:  # noqa: BLE001
            cloud_run = {
                "checked": True,
                "ok": False,
                "required": list(required),
                "ready_count": 0,
                "missing": list(required),
                "not_ready": [],
                "services": [],
                "error": f"{type(exc).__name__}: {exc}",
            }

    report = build_report(
        proxy=proxy,
        proxy_warnings=warnings,
        cloud_run=cloud_run,
        require_primary=args.require_primary,
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_markdown(report), end="")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
