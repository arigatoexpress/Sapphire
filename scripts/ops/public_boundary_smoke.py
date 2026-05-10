#!/usr/bin/env python3
"""Public-boundary smoke for sapphirealpha.xyz routes.

Runs either against a live base URL or against the local Flask app via its test
client. The check is deliberately text-based and dependency-light: it catches
public HTML/API leaks such as raw admin URLs, source Cloud Run URLs, internal
warehouse names, signal-count keys, and browser-side fetches to private
service APIs before a deploy reaches production.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import ssl
import sys
import types
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

DEFAULT_BASE_URL = "https://sapphirealpha.xyz"
REPO_ROOT = Path(__file__).resolve().parents[2]
APP_PATH = REPO_ROOT / "services" / "analytics_dashboard" / "app.py"

PUBLIC_ROUTES: tuple[str, ...] = (
    "/",
    "/p/brain",
    "/p/system",
    "/p/wildfire",
    "/p/regional",
    "/p/help",
    "/api/projects",
    "/api/summary",
    "/api/brain/synthesis",
    "/api/silos/health",
    "/api/failover/readiness",
)

ADMIN_PROTECTED_ROUTES: tuple[str, ...] = (
    "/admin",
    "/api/admin/whoami",
    "/api/admin/analysis",
    "/api/performance",
    "/api/predictions",
    "/api/predictions/accuracy",
    "/api/correlation/matrix",
    "/api/vpin",
    "/api/deflated-sharpe/rolling",
    "/api/timeseries/inference",
    "/api/timeseries/services",
    "/api/silos/business",
    "/api/silos/inference",
    "/api/signals/recent",
    "/api/brain/synthesis?persist=1",
    "/api/brain/synthesis?force_llm=1",
    "/api/brain/correlate",
    "/api/brain/history",
    "/api/asfao/decisions",
)

PUBLIC_JSON_CONTRACTS: dict[str, dict[str, Any]] = {
    "/api/summary": {
        "mode": "public_operating_summary",
        "forbidden_keys": (
            "signals",
            "predictions",
            "leads",
            "inference_metrics",
            "service_health",
            "total_pnl_usd",
            "win_rate",
            "pnl_usd",
        ),
    },
    "/api/silos/health": {
        "mode": "public_silos_health_summary",
        "forbidden_keys": ("host", "sha", "response_ms", "dependencies"),
        "empty_lists": ("services",),
    },
    "/api/failover/readiness": {
        "mode": "public_failover_readiness_summary",
        "forbidden_keys": ("services", "host", "port", "raw_checks", "routing_policy", "sha"),
    },
    "/api/brain/synthesis": {
        "mode": "public_brain_summary",
        "forbidden_keys": (
            "signal_count_24h",
            "threat_count_24h",
            "history",
            "correlations",
        ),
    },
}

FORBIDDEN_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("wildfire-admin-url", re.compile(r"wildfire\.sapphirealpha\.xyz/admin", re.I)),
    ("regional-admin-url", re.compile(r"regional\.sapphirealpha\.xyz/admin", re.I)),
    ("raw-threat-cloud-run", re.compile(r"cyber-threat-bot-691674245427", re.I)),
    ("raw-cloud-run-domain", re.compile(r"us-central1\.run\.app", re.I)),
    ("legacy-public-signal-label", re.compile(r"SIGNALS_24H", re.I)),
    ("brain-signal-count-key", re.compile(r"signal_count_24h", re.I)),
    ("brain-threat-count-key", re.compile(r"threat_count_24h", re.I)),
    ("wildfire-signal-24h-key", re.compile(r"signals_24h", re.I)),
    ("wildfire-signal-7d-key", re.compile(r"signals_7d", re.I)),
    ("wildfire-raw-health-path", re.compile(r"/api/sensors/health", re.I)),
    ("analytics-service-name", re.compile(r"analytics-dashboard", re.I)),
    ("warehouse-name", re.compile(r"tho-ai-agent/sapphire", re.I)),
    ("test-warehouse-name", re.compile(r"test-project/test_dataset", re.I)),
    ("admin-console-copy", re.compile(r"open admin console|embedded admin console", re.I)),
    ("gcp-project-copy", re.compile(r"GCP project|BigQuery dataset", re.I)),
    ("source-app-copy", re.compile(r"Source App", re.I)),
)


@dataclass(frozen=True)
class BoundaryResult:
    path: str
    status: str
    evidence: str
    http_status: int
    matches: tuple[str, ...] = ()


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


def _ssl_context() -> ssl.SSLContext | None:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:  # noqa: BLE001
        return None


def _fetch_url(
    base_url: str,
    path: str,
    timeout: float,
    *,
    follow_redirects: bool = True,
) -> tuple[int, str]:
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"unsupported URL scheme: {parsed.scheme}")
    url = urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    req = urllib.request.Request(url, headers={"User-Agent": "sapphire-public-boundary/1.0"})
    handlers = []
    context = _ssl_context()
    if context is not None:
        handlers.append(urllib.request.HTTPSHandler(context=context))
    if not follow_redirects:
        handlers.append(_NoRedirect)
    opener = urllib.request.build_opener(*handlers)
    with opener.open(req, timeout=timeout) as resp:  # nosec B310
        status = int(getattr(resp, "status", resp.getcode()))
        text = resp.read().decode("utf-8", errors="replace")
    return status, text


def _install_fake_bigquery() -> None:
    if "google.cloud.bigquery" in sys.modules:
        return

    fake_google = types.ModuleType("google")
    fake_cloud = types.ModuleType("google.cloud")
    fake_bigquery = types.ModuleType("google.cloud.bigquery")

    class _Client:
        def __init__(self, project: str):
            self.project = project

        def query(self, *_args, **_kwargs):
            raise RuntimeError("public boundary smoke does not query BigQuery")

    fake_bigquery.Client = _Client
    fake_bigquery.QueryJobConfig = lambda query_parameters=None: types.SimpleNamespace(
        query_parameters=query_parameters or []
    )
    fake_bigquery.ScalarQueryParameter = lambda name, kind, value: types.SimpleNamespace(
        name=name, kind=kind, value=value
    )
    fake_bigquery.ArrayQueryParameter = lambda name, kind, value: types.SimpleNamespace(
        name=name, kind=kind, value=value
    )
    fake_cloud.bigquery = fake_bigquery
    sys.modules["google"] = fake_google
    sys.modules["google.cloud"] = fake_cloud
    sys.modules["google.cloud.bigquery"] = fake_bigquery


def _install_fake_webauthn() -> None:
    if "webauthn" in sys.modules:
        return

    fake_webauthn = types.ModuleType("webauthn")
    fake_helpers = types.ModuleType("webauthn.helpers")
    fake_exceptions = types.ModuleType("webauthn.helpers.exceptions")
    fake_structs = types.ModuleType("webauthn.helpers.structs")

    class _InvalidRegistrationResponse(Exception):
        pass

    class _InvalidAuthenticationResponse(Exception):
        pass

    class _Struct:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    def _unavailable(*_args, **_kwargs):
        raise RuntimeError("public boundary smoke does not verify WebAuthn")

    fake_webauthn.generate_authentication_options = lambda **_kwargs: types.SimpleNamespace()
    fake_webauthn.generate_registration_options = lambda **_kwargs: types.SimpleNamespace()
    fake_webauthn.options_to_json = lambda _options: "{}"
    fake_webauthn.verify_authentication_response = _unavailable
    fake_webauthn.verify_registration_response = _unavailable

    fake_exceptions.InvalidAuthenticationResponse = _InvalidAuthenticationResponse
    fake_exceptions.InvalidRegistrationResponse = _InvalidRegistrationResponse
    fake_structs.AuthenticatorSelectionCriteria = _Struct
    fake_structs.PublicKeyCredentialDescriptor = _Struct
    fake_structs.ResidentKeyRequirement = types.SimpleNamespace(REQUIRED="required")
    fake_structs.UserVerificationRequirement = types.SimpleNamespace(REQUIRED="required")

    sys.modules["webauthn"] = fake_webauthn
    sys.modules["webauthn.helpers"] = fake_helpers
    sys.modules["webauthn.helpers.exceptions"] = fake_exceptions
    sys.modules["webauthn.helpers.structs"] = fake_structs


def _load_local_app():
    os.environ.setdefault("GCP_PROJECT", "test-project")
    os.environ.setdefault("BQ_DATASET", "test_dataset")
    os.environ.setdefault("ADMIN_SESSION_SECRET", "public-boundary-smoke")
    os.environ.setdefault("RP_ID", "localhost")
    _install_fake_bigquery()
    _install_fake_webauthn()
    sys.path.insert(0, str(APP_PATH.parent))
    module_name = "_sapphire_public_boundary_app"
    sys.modules.pop(module_name, None)
    spec = importlib.util.spec_from_file_location(module_name, APP_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {APP_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module.app


def _fetch_local(app, path: str) -> tuple[int, str]:
    resp = app.test_client().get(path)
    return resp.status_code, resp.get_data(as_text=True)


def scan_text(path: str, status: int, text: str) -> BoundaryResult:
    matches = tuple(name for name, pattern in FORBIDDEN_PATTERNS if pattern.search(text))
    if status != 200:
        return BoundaryResult(path, "FAIL", f"expected HTTP 200, got {status}", status, matches)
    if matches:
        return BoundaryResult(
            path, "FAIL", "forbidden public-boundary strings found", status, matches
        )
    return BoundaryResult(path, "PASS", "public route stayed inside the safe boundary", status)


def _json_key_paths(value: Any, prefix: str = "") -> list[str]:
    if isinstance(value, dict):
        paths: list[str] = []
        for key, item in value.items():
            key_path = f"{prefix}.{key}" if prefix else str(key)
            paths.append(key_path)
            paths.extend(_json_key_paths(item, key_path))
        return paths
    if isinstance(value, list):
        paths = []
        for index, item in enumerate(value):
            paths.extend(_json_key_paths(item, f"{prefix}[{index}]"))
        return paths
    return []


def _json_value_at(payload: Any, dotted_path: str) -> Any:
    current = payload
    for part in dotted_path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def scan_public_json_contract(path: str, status: int, text: str) -> BoundaryResult:
    contract = PUBLIC_JSON_CONTRACTS[path]
    if status != 200:
        return BoundaryResult(path, "FAIL", f"expected HTTP 200, got {status}", status)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        return BoundaryResult(path, "FAIL", f"invalid JSON: {exc}", status)
    if not isinstance(payload, dict):
        return BoundaryResult(path, "FAIL", "expected public JSON object", status)
    expected_mode = contract.get("mode")
    if expected_mode and payload.get("mode") != expected_mode:
        return BoundaryResult(
            path,
            "FAIL",
            f"expected mode {expected_mode!r}, got {payload.get('mode')!r}",
            status,
        )
    key_names = {key_path.rsplit(".", 1)[-1] for key_path in _json_key_paths(payload)}
    forbidden = tuple(
        sorted(str(key) for key in contract.get("forbidden_keys", ()) if key in key_names)
    )
    if forbidden:
        return BoundaryResult(
            path,
            "FAIL",
            "forbidden public JSON keys found",
            status,
            forbidden,
        )
    non_empty = tuple(
        key for key in contract.get("empty_lists", ()) if _json_value_at(payload, str(key)) != []
    )
    if non_empty:
        return BoundaryResult(
            path,
            "FAIL",
            "public JSON list expected to stay empty",
            status,
            non_empty,
        )
    return BoundaryResult(path, "PASS", "public JSON stayed inside the safe schema", status)


def scan_admin_boundary(path: str, status: int, text: str) -> BoundaryResult:
    if status in {301, 302, 303, 307, 308, 401, 403, 503}:
        return BoundaryResult(path, "PASS", "admin route required auth or failed closed", status)
    if status == 404:
        return BoundaryResult(path, "FAIL", "admin route was not registered", status)
    return BoundaryResult(
        path,
        "FAIL",
        f"expected admin auth boundary, got HTTP {status}",
        status,
        tuple(name for name, pattern in FORBIDDEN_PATTERNS if pattern.search(text)),
    )


def run_scan(*, base_url: str | None, timeout: float) -> dict[str, Any]:
    results: list[BoundaryResult] = []
    local_app = None if base_url else _load_local_app()
    for path in PUBLIC_ROUTES:
        try:
            status, text = (
                _fetch_url(base_url, path, timeout) if base_url else _fetch_local(local_app, path)
            )
            results.append(scan_text(path, status, text))
            if path in PUBLIC_JSON_CONTRACTS:
                results.append(scan_public_json_contract(path, status, text))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            results.append(scan_text(path, int(exc.code), body))
        except Exception as exc:  # noqa: BLE001
            results.append(
                BoundaryResult(path, "FAIL", f"{type(exc).__name__}: {exc}", http_status=0)
            )
    for path in ADMIN_PROTECTED_ROUTES:
        try:
            status, text = (
                _fetch_url(base_url, path, timeout, follow_redirects=False)
                if base_url
                else _fetch_local(local_app, path)
            )
            results.append(scan_admin_boundary(path, status, text))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            results.append(scan_admin_boundary(path, int(exc.code), body))
        except Exception as exc:  # noqa: BLE001
            results.append(
                BoundaryResult(path, "FAIL", f"{type(exc).__name__}: {exc}", http_status=0)
            )
    failed = [result for result in results if result.status != "PASS"]
    return {
        "base_url": base_url or "local-flask-test-client",
        "ok": not failed,
        "passed": len(results) - len(failed),
        "failed": len(failed),
        "results": [asdict(result) for result in results],
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Sapphire public-boundary smoke",
        "",
        f"- target: `{report['base_url']}`",
        f"- ok: `{str(report['ok']).lower()}`",
        f"- passed: `{report['passed']}`",
        f"- failed: `{report['failed']}`",
        "",
    ]
    for result in report["results"]:
        suffix = f" matches={','.join(result['matches'])}" if result["matches"] else ""
        lines.append(
            f"- {result['status']}: `{result['path']}` HTTP {result['http_status']} - "
            f"{result['evidence']}{suffix}"
        )
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url", default=None, help="Live base URL. Omit for local Flask scan."
    )
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = run_scan(base_url=args.base_url, timeout=args.timeout)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_markdown(report), end="")
    return 0 if report["ok"] else 20


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
