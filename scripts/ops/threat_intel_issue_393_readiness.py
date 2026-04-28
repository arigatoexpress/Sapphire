#!/usr/bin/env python3
"""Generate paste-safe readiness evidence for threat-intel issue #393.

This helper is intentionally read-only. It verifies the three follow-up
questions raised by issue #393 without opening issues, closing issues,
changing GitHub settings, sending Telegram messages, or touching production
systems:

* Can the Dependabot alerts API be queried from the current ``gh`` context?
* Do current CISA KEV critical candidates lexically match Sapphire deps?
* Does Sapphire repo/config evidence mention the ransomware-linked products
  called out in the issue body?
"""

from __future__ import annotations

import argparse
import json
import re
import ssl
import sys
import tomllib
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.request import urlopen

import dependabot_alerts_fetch

try:  # pragma: no cover - availability depends on the operator environment
    import certifi
except ImportError:  # pragma: no cover
    certifi = None

CISA_KEV_URL = (
    "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
)
DEFAULT_REPO = "arigatoexpress/Sapphire"
DEFAULT_RECENT_DAYS = 7
DEFAULT_KEV_LIMIT = 10

REQUIREMENTS_GLOBS = (
    "requirements*.txt",
    "services/*/requirements*.txt",
    "clients/*/requirements*.txt",
    "plugins/*/requirements*.txt",
)

DEPLOYMENT_EVIDENCE_ROOTS = (
    ".github",
    "agents",
    "clients",
    "config",
    "deploy",
    "infra",
    "services",
)

ROOT_EVIDENCE_FILENAMES = {
    ".env.integrations.example",
    ".firebaserc",
    ".gcloudignore",
    ".mcp.json",
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "env.example",
    "foundry.toml",
    "package-lock.json",
    "package.json",
    "pnpm-lock.yaml",
    "pyproject.toml",
    "requirements-test.txt",
    "requirements.txt",
    "uv.lock",
    "yarn.lock",
}

TEXT_SUFFIXES = {
    "",
    ".cfg",
    ".conf",
    ".cjs",
    ".env",
    ".example",
    ".ini",
    ".js",
    ".json",
    ".mjs",
    ".plist",
    ".py",
    ".service",
    ".sh",
    ".toml",
    ".ts",
    ".txt",
    ".yaml",
    ".yml",
}

DEPLOYMENT_PRODUCTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("PaperCut NG/MF", ("papercut", "paper cut")),
    ("JetBrains TeamCity", ("teamcity", "jetbrains teamcity")),
    (
        "Microsoft Exchange Server",
        ("microsoft exchange server", "exchange server"),
    ),
    (
        "Cisco Secure Firewall Management Center (FMC)",
        (
            "cisco secure firewall management center",
            "cisco fmc",
            "firewall management center",
            "secure firewall management center",
        ),
    ),
)


@dataclass(frozen=True)
class DeploymentMatch:
    product: str
    alias: str
    path: str
    line: int


def _parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _normalize_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _safe_relpath(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _sanitize_error(value: str) -> str:
    compact = " ".join(value.split())
    compact = re.sub(r"gh[pousr]_[A-Za-z0-9_]+", "<redacted-token>", compact)
    compact = re.sub(r"github_pat_[A-Za-z0-9_]+", "<redacted-token>", compact)
    return compact[:320]


def parse_requirement_name(line: str) -> str | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or stripped.startswith("-"):
        return None
    name = re.split(r"\s*(?:[<>=!~]=?|;|\[|#)", stripped, maxsplit=1)[0].strip()
    return name.lower() or None


def collect_dependency_names(root: Path) -> list[str]:
    deps: set[str] = set()
    for pattern in REQUIREMENTS_GLOBS:
        for path in root.glob(pattern):
            if not path.is_file():
                continue
            for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                name = parse_requirement_name(line)
                if name:
                    deps.add(name)

    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        project = data.get("project", {})
        raw_deps = list(project.get("dependencies", []))
        for values in (project.get("optional-dependencies", {}) or {}).values():
            raw_deps.extend(values)
        for dep in raw_deps:
            name = parse_requirement_name(str(dep))
            if name:
                deps.add(name)

    return sorted(deps)


def load_kev_payload(path: Path | None = None) -> dict[str, Any]:
    if path is not None:
        return json.loads(path.read_text(encoding="utf-8"))
    context = None
    if certifi is not None:
        context = ssl.create_default_context(cafile=certifi.where())
    with urlopen(CISA_KEV_URL, timeout=20, context=context) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))


def _kev_product_text(entry: dict[str, Any]) -> str:
    return " ".join(
        str(entry.get(field) or "")
        for field in ("vendorProject", "product", "vulnerabilityName")
    )


def _matching_dependencies(entry: dict[str, Any], dependencies: Iterable[str]) -> list[str]:
    haystack = _normalize_token(_kev_product_text(entry))
    matches: list[str] = []
    for dep in dependencies:
        needle = _normalize_token(dep)
        if len(needle) >= 4 and needle in haystack:
            matches.append(dep)
    return matches


def classify_kev_candidates(
    payload: dict[str, Any],
    dependencies: list[str],
    *,
    as_of: date,
    recent_days: int = DEFAULT_RECENT_DAYS,
    limit: int = DEFAULT_KEV_LIMIT,
) -> dict[str, Any]:
    cutoff = as_of - timedelta(days=recent_days)
    all_entries = [entry for entry in payload.get("vulnerabilities", []) if isinstance(entry, dict)]
    criticals: list[dict[str, Any]] = []
    all_relevant: list[dict[str, Any]] = []

    for entry in all_entries:
        matched = _matching_dependencies(entry, dependencies)
        if matched:
            all_relevant.append(
                {
                    "cveID": entry.get("cveID"),
                    "vendorProject": entry.get("vendorProject"),
                    "product": entry.get("product"),
                    "dateAdded": entry.get("dateAdded"),
                    "matched_dependencies": matched,
                }
            )

        required_action = bool(str(entry.get("requiredAction") or "").strip())
        ransomware_known = str(entry.get("knownRansomwareCampaignUse") or "").lower() == "known"
        date_added = _parse_iso_date(str(entry.get("dateAdded") or ""))
        recent = date_added is not None and date_added > cutoff
        if not (required_action and (ransomware_known or recent)):
            continue

        criticals.append(
            {
                "cveID": entry.get("cveID"),
                "vendorProject": entry.get("vendorProject"),
                "product": entry.get("product"),
                "dateAdded": entry.get("dateAdded"),
                "knownRansomwareCampaignUse": entry.get("knownRansomwareCampaignUse"),
                "requiredAction": entry.get("requiredAction"),
                "matched_dependencies": matched,
            }
        )

    criticals.sort(key=lambda item: str(item.get("dateAdded") or ""), reverse=True)
    capped = criticals[:limit]
    return {
        "catalog_count": len(all_entries),
        "criteria": {
            "as_of": as_of.isoformat(),
            "recent_days": recent_days,
            "limit": limit,
            "required_action": True,
            "ransomware_known_or_recent": True,
        },
        "critical_candidates_count": len(criticals),
        "reported_candidates_count": len(capped),
        "sapphire_relevant_reported_count": sum(
            1 for item in capped if item["matched_dependencies"]
        ),
        "sapphire_relevant_all_kev_count": len(all_relevant),
        "reported_candidates": capped,
        "sapphire_relevant_all_kev": all_relevant[:limit],
    }


def _iter_deployment_evidence_files(root: Path) -> Iterable[Path]:
    for name in ROOT_EVIDENCE_FILENAMES:
        path = root / name
        if path.is_file():
            yield path
    for rel_root in DEPLOYMENT_EVIDENCE_ROOTS:
        base = root / rel_root
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES:
                yield path


def find_deployment_matches(root: Path) -> dict[str, list[DeploymentMatch]]:
    matches: dict[str, list[DeploymentMatch]] = {
        product: [] for product, _aliases in DEPLOYMENT_PRODUCTS
    }
    for path in _iter_deployment_evidence_files(root):
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        for line_number, line in enumerate(lines, start=1):
            lowered = line.lower()
            for product, aliases in DEPLOYMENT_PRODUCTS:
                for alias in aliases:
                    if alias in lowered:
                        matches[product].append(
                            DeploymentMatch(
                                product=product,
                                alias=alias,
                                path=_safe_relpath(path, root),
                                line=line_number,
                            )
                        )
    return matches


def summarize_deployment_footprint(root: Path) -> list[dict[str, Any]]:
    found = find_deployment_matches(root)
    summary: list[dict[str, Any]] = []
    for product, _aliases in DEPLOYMENT_PRODUCTS:
        product_matches = found[product]
        summary.append(
            {
                "product": product,
                "status": "present_in_repo_config_evidence"
                if product_matches
                else "absent_by_repo_config_evidence",
                "matches": [
                    {
                        "path": match.path,
                        "line": match.line,
                        "matched_alias": match.alias,
                    }
                    for match in product_matches[:20]
                ],
            }
        )
    return summary


def fetch_dependabot_status(repo: str) -> dict[str, Any]:
    try:
        result = dependabot_alerts_fetch.fetch_and_render(repo=repo)
    except dependabot_alerts_fetch.DependabotFetchError as exc:
        return {
            "status": "unavailable",
            "reason": _sanitize_error(str(exc)),
            "critical_high_open": None,
        }
    summary = result.get("summary", {})
    by_severity = summary.get("by_severity", {})
    return {
        "status": "available",
        "alerts_count": result.get("alerts_count", 0),
        "critical_high_open": int(by_severity.get("critical", 0))
        + int(by_severity.get("high", 0)),
        "by_severity": by_severity,
        "by_ecosystem": summary.get("by_ecosystem", {}),
    }


def build_report(
    *,
    root: Path,
    repo: str,
    kev_payload: dict[str, Any],
    as_of: date,
    skip_ghas: bool = False,
) -> dict[str, Any]:
    dependencies = collect_dependency_names(root)
    kev = classify_kev_candidates(kev_payload, dependencies, as_of=as_of)
    deployment = summarize_deployment_footprint(root)
    dependabot = (
        {"status": "skipped", "reason": "operator requested --skip-ghas", "critical_high_open": None}
        if skip_ghas
        else fetch_dependabot_status(repo)
    )
    deployment_clear = all(item["status"] == "absent_by_repo_config_evidence" for item in deployment)
    kev_clear = kev["sapphire_relevant_reported_count"] == 0
    ghas_clear = dependabot.get("status") == "available" and dependabot.get("critical_high_open") == 0
    ready_to_close = bool(deployment_clear and kev_clear and ghas_clear)
    ready_to_comment = bool(deployment_clear and kev_clear)
    if ready_to_close:
        recommendation = "ready_to_close"
    elif ready_to_comment:
        recommendation = "comment_with_evidence_ghas_unavailable_or_nonzero"
    else:
        recommendation = "keep_open_action_required"
    return {
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "repo": repo,
        "repo_root": str(root),
        "issue": 393,
        "dependabot": dependabot,
        "dependencies_count": len(dependencies),
        "kev": kev,
        "deployment_footprint": deployment,
        "readiness": {
            "ready_to_comment": ready_to_comment,
            "ready_to_close": ready_to_close,
            "recommendation": recommendation,
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = [
        "## Issue #393 readiness evidence",
        "",
        "### Observed",
    ]
    dependabot = report["dependabot"]
    if dependabot["status"] == "available":
        lines.append(
            "- Dependabot alerts API available; "
            f"critical/high open alerts: {dependabot['critical_high_open']}."
        )
    else:
        lines.append(
            "- Dependabot alerts API unavailable; "
            f"status={dependabot['status']}; reason={dependabot.get('reason', 'n/a')}."
        )

    kev = report["kev"]
    lines.append(
        "- CISA KEV fetched; "
        f"catalog_count={kev['catalog_count']}; "
        f"reported_candidates={kev['reported_candidates_count']}; "
        f"sapphire_relevant_reported={kev['sapphire_relevant_reported_count']}."
    )
    for item in report["deployment_footprint"]:
        lines.append(f"- {item['product']}: {item['status']}.")

    lines.extend(["", "### Unknown"])
    if dependabot["status"] != "available":
        lines.append("- GHAS/Dependabot alert contents remain unknown until alerts are enabled or token scope is refreshed.")
    else:
        lines.append("- No unknown GHAS/Dependabot state from this run.")

    lines.extend(["", "### Recommendation"])
    lines.append(f"- {report['readiness']['recommendation']}.")
    return "\n".join(lines)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".", help="Sapphire checkout root.")
    parser.add_argument("--repo", default=DEFAULT_REPO, help=f"GitHub repo, default {DEFAULT_REPO}.")
    parser.add_argument("--kev-json", type=Path, help="Use a local CISA KEV JSON payload.")
    parser.add_argument("--as-of", help="Date for recent KEV window, YYYY-MM-DD.")
    parser.add_argument("--skip-ghas", action="store_true", help="Skip live Dependabot API check.")
    parser.add_argument("--markdown-only", action="store_true", help="Print only markdown.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    root = Path(args.repo_root).resolve()
    as_of = _parse_iso_date(args.as_of) if args.as_of else date.today()
    if as_of is None:
        print("threat-intel-393-readiness error: bad --as-of date", file=sys.stderr)
        return 2
    try:
        kev_payload = load_kev_payload(args.kev_json)
        report = build_report(
            root=root,
            repo=args.repo,
            kev_payload=kev_payload,
            as_of=as_of,
            skip_ghas=args.skip_ghas,
        )
    except Exception as exc:  # noqa: BLE001 - paste-safe CLI boundary
        print(f"threat-intel-393-readiness error: {_sanitize_error(str(exc))}", file=sys.stderr)
        return 2
    if args.markdown_only:
        print(render_markdown(report))
    else:
        print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
