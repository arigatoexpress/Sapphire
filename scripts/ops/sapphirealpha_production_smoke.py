#!/usr/bin/env python3
"""Read-only production smoke for sapphirealpha.xyz.

This guard is intentionally narrow: prove the apex is serving the Sapphire
analytics/control-plane backend, not a static SPA that falls back to index.html
for every /api/* route.
"""

from __future__ import annotations

import argparse
import json
import ssl
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import urljoin, urlparse

DEFAULT_BASE_URL = "https://sapphirealpha.xyz"


@dataclass(frozen=True)
class ProbeSpec:
    name: str
    path: str
    kind: str
    contains: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProbeResult:
    name: str
    path: str
    status: str
    evidence: str
    duration_ms: int
    http_status: int | None = None
    content_type: str | None = None


PROBES: tuple[ProbeSpec, ...] = (
    ProbeSpec("home_html", "/", "html", ("Sapphire OS",)),
    ProbeSpec("health_json", "/health", "json"),
    ProbeSpec("projects_json", "/api/projects", "json", ("projects",)),
    ProbeSpec("brain_json", "/api/brain/synthesis", "json"),
    ProbeSpec("markets_json", "/api/markets/snapshot", "json"),
    ProbeSpec("silos_json", "/api/silos/health", "json"),
    ProbeSpec("about_subpage_html", "/p/about", "html", ("Sapphire",)),
)


def _ssl_context() -> ssl.SSLContext | None:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:  # noqa: BLE001
        return None


def _fetch(url: str, timeout: float) -> tuple[int, str, bytes]:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"unsupported URL scheme: {parsed.scheme}")
    request = urllib.request.Request(url, headers={"User-Agent": "sapphire-apex-smoke/1.0"})
    with urllib.request.urlopen(request, timeout=timeout, context=_ssl_context()) as response:  # nosec B310
        status = int(getattr(response, "status", response.getcode()))
        content_type = response.headers.get("content-type", "")
        body = response.read()
    return status, content_type, body


def _looks_like_static_html(body: bytes) -> bool:
    prefix = body[:512].decode("utf-8", errors="replace").lstrip().lower()
    return prefix.startswith("<!doctype html") or prefix.startswith("<html")


def _probe(base_url: str, spec: ProbeSpec, timeout: float) -> ProbeResult:
    url = urljoin(base_url.rstrip("/") + "/", spec.path.lstrip("/"))
    started = time.perf_counter()
    try:
        http_status, content_type, body = _fetch(url, timeout)
    except urllib.error.HTTPError as exc:
        duration_ms = int((time.perf_counter() - started) * 1000)
        return ProbeResult(
            spec.name,
            spec.path,
            "FAIL",
            f"HTTP {exc.code}",
            duration_ms,
            http_status=exc.code,
            content_type=exc.headers.get("content-type"),
        )
    except Exception as exc:  # noqa: BLE001
        duration_ms = int((time.perf_counter() - started) * 1000)
        return ProbeResult(
            spec.name, spec.path, "FAIL", f"{type(exc).__name__}: {exc}", duration_ms
        )

    duration_ms = int((time.perf_counter() - started) * 1000)
    text = body.decode("utf-8", errors="replace")
    if http_status != 200:
        return ProbeResult(
            spec.name,
            spec.path,
            "FAIL",
            f"expected HTTP 200, got {http_status}",
            duration_ms,
            http_status=http_status,
            content_type=content_type,
        )

    if spec.kind == "json":
        if _looks_like_static_html(body):
            return ProbeResult(
                spec.name,
                spec.path,
                "FAIL",
                "JSON endpoint returned HTML; apex is likely serving a static SPA fallback",
                duration_ms,
                http_status=http_status,
                content_type=content_type,
            )
        try:
            payload: Any = json.loads(text)
        except json.JSONDecodeError as exc:
            return ProbeResult(
                spec.name,
                spec.path,
                "FAIL",
                f"invalid JSON: {exc.msg}",
                duration_ms,
                http_status=http_status,
                content_type=content_type,
            )
        missing = [needle for needle in spec.contains if needle not in payload]
        if missing:
            return ProbeResult(
                spec.name,
                spec.path,
                "FAIL",
                f"JSON payload missing keys: {', '.join(missing)}",
                duration_ms,
                http_status=http_status,
                content_type=content_type,
            )
        return ProbeResult(
            spec.name,
            spec.path,
            "PASS",
            "JSON route served by control-plane backend",
            duration_ms,
            http_status=http_status,
            content_type=content_type,
        )

    missing_text = [needle for needle in spec.contains if needle not in text]
    if missing_text:
        return ProbeResult(
            spec.name,
            spec.path,
            "FAIL",
            f"HTML missing text: {', '.join(missing_text)}",
            duration_ms,
            http_status=http_status,
            content_type=content_type,
        )
    return ProbeResult(
        spec.name,
        spec.path,
        "PASS",
        "HTML route rendered expected Sapphire surface",
        duration_ms,
        http_status=http_status,
        content_type=content_type,
    )


def run_smoke(base_url: str, timeout: float) -> dict[str, Any]:
    results = [_probe(base_url, spec, timeout) for spec in PROBES]
    failed = [result for result in results if result.status != "PASS"]
    return {
        "base_url": base_url.rstrip("/"),
        "ok": not failed,
        "passed": len(results) - len(failed),
        "failed": len(failed),
        "probes": [asdict(result) for result in results],
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# sapphirealpha.xyz production smoke",
        "",
        f"- base_url: `{report['base_url']}`",
        f"- ok: `{str(report['ok']).lower()}`",
        f"- passed: `{report['passed']}`",
        f"- failed: `{report['failed']}`",
        "",
    ]
    for probe in report["probes"]:
        lines.append(
            f"- {probe['status']}: `{probe['path']}` ({probe['duration_ms']}ms) - {probe['evidence']}"
        )
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = run_smoke(args.base_url, args.timeout)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_markdown(report), end="")
    return 0 if report["ok"] else 20


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
