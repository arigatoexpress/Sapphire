#!/usr/bin/env python3
"""Offline workspace supply-chain guard.

This scanner is intentionally read-only and conservative. It does not contact
registries or advisory APIs; it looks for local dependency and automation shapes
that were repeatedly useful in Shai-Hulud-style response: install-time scripts,
high-risk package ecosystems, non-registry package resolutions, CI publishing
surfaces, and agent/editor persistence hooks.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SEVERITY_ORDER = {"info": 0, "medium": 1, "high": 2, "critical": 3}
LIFECYCLE_SCRIPTS = {"preinstall", "install", "postinstall", "prepare"}
PACKAGE_MANAGERS = ("npm install", "npm ci", "pnpm install", "yarn install", "bun install")
PUBLISH_COMMANDS = ("npm publish", "pnpm publish", "yarn publish")
NETWORK_EXEC_RE = re.compile(
    r"\b(curl|wget|iwr|irm|Invoke-WebRequest|Invoke-RestMethod)\b.*\b(sh|bash|node|python|pwsh)\b",
    re.IGNORECASE,
)

# These are ecosystem tripwires, not proof of compromise. The finding text
# deliberately asks for version-level advisory verification before escalation.
HIGH_RISK_NPM_SCOPES = {
    "@antv",
    "@tanstack",
    "@mistralai",
    "@opensearch-project",
    "@uipath",
}
HIGH_RISK_NPM_NAMES = {
    "echarts-for-react",
    "timeago.js",
}
REVIEW_NPM_NAMES = {"axios"}
HIGH_RISK_PYPI_NAMES = {
    "mistralai",
    "guardrails-ai",
    "opensearch-py",
    "uipath",
}
SUSPICIOUS_FILENAMES = {
    "setup_bun.js",
    "bun_environment.js",
    "shai-hulud-workflow.yml",
    "shai-hulud-workflow.yaml",
}
SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "dist-server",
    "build",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".next",
    ".turbo",
    "coverage",
}


@dataclass(frozen=True)
class Finding:
    severity: str
    repo: str
    path: str
    code: str
    message: str
    evidence: str = ""

    def sort_key(self) -> tuple[int, str, str, str]:
        return (-SEVERITY_ORDER[self.severity], self.repo, self.path, self.code)


def repo_name(root: Path) -> str:
    return root.name


def relative_path(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def iter_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for current, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        current_path = Path(current)
        for name in names:
            files.append(current_path / name)
    return files


def scan_package_json(root: Path, path: Path) -> list[Finding]:
    payload = read_json(path)
    if payload is None:
        return [
            Finding(
                "medium",
                repo_name(root),
                relative_path(path, root),
                "package_json_unreadable",
                "package.json could not be parsed as JSON.",
            )
        ]

    findings: list[Finding] = []
    scripts = payload.get("scripts")
    if isinstance(scripts, dict):
        for name in sorted(LIFECYCLE_SCRIPTS & set(scripts)):
            findings.append(
                Finding(
                    "high",
                    repo_name(root),
                    relative_path(path, root),
                    "root_lifecycle_script",
                    "Root package has an install-time lifecycle script; review before npm/pnpm/yarn install.",
                    f"{name}={str(scripts.get(name))[:160]}",
                )
            )

    dependencies = collect_manifest_dependencies(payload)
    risky_specs = []
    watched_deps = []
    floating_specs = 0
    for dep_name, spec in dependencies.items():
        if is_high_risk_npm(dep_name):
            watched_deps.append(f"{dep_name}@{spec}")
        if is_risky_spec(spec):
            risky_specs.append(f"{dep_name}@{spec}")
        if is_floating_spec(spec):
            floating_specs += 1

    if watched_deps:
        findings.append(
            Finding(
                "high",
                repo_name(root),
                relative_path(path, root),
                "active_campaign_ecosystem_dependency",
                "Manifest references an ecosystem seen in recent supply-chain campaigns; verify exact versions against current advisories before installing.",
                ", ".join(watched_deps[:8]),
            )
        )
    if risky_specs:
        findings.append(
            Finding(
                "medium",
                repo_name(root),
                relative_path(path, root),
                "non_registry_dependency_spec",
                "Manifest uses direct URL/git/file dependency specs; review source and hash before install.",
                ", ".join(risky_specs[:8]),
            )
        )
    if floating_specs:
        findings.append(
            Finding(
                "info",
                repo_name(root),
                relative_path(path, root),
                "floating_dependency_specs",
                "Manifest contains semver ranges or floating specs; lockfile must be treated as the install source of truth.",
                f"count={floating_specs}",
            )
        )
    return findings


def collect_manifest_dependencies(payload: dict[str, Any]) -> dict[str, str]:
    deps: dict[str, str] = {}
    for section in (
        "dependencies",
        "devDependencies",
        "optionalDependencies",
        "peerDependencies",
        "bundleDependencies",
        "bundledDependencies",
    ):
        values = payload.get(section)
        if isinstance(values, dict):
            for name, spec in values.items():
                deps[str(name)] = str(spec)
        elif isinstance(values, list):
            for name in values:
                deps[str(name)] = "*"
    return deps


def is_high_risk_npm(name: str) -> bool:
    if name in HIGH_RISK_NPM_NAMES:
        return True
    return any(name == scope or name.startswith(f"{scope}/") for scope in HIGH_RISK_NPM_SCOPES)


def is_review_npm(name: str) -> bool:
    return name in REVIEW_NPM_NAMES


def is_risky_spec(spec: str) -> bool:
    lower = spec.lower()
    return lower.startswith(("git+", "github:", "http:", "https:", "file:", "link:"))


def is_floating_spec(spec: str) -> bool:
    if is_risky_spec(spec):
        return False
    if spec in {"*", "latest", ""}:
        return True
    return spec[0] in {"^", "~", ">", "<"}


def scan_package_lock(root: Path, path: Path) -> list[Finding]:
    payload = read_json(path)
    if payload is None:
        return [
            Finding(
                "medium",
                repo_name(root),
                relative_path(path, root),
                "package_lock_unreadable",
                "package-lock.json could not be parsed as JSON.",
            )
        ]

    findings: list[Finding] = []
    package_entries = payload.get("packages")
    if not isinstance(package_entries, dict):
        return findings

    install_script_entries = []
    non_registry_entries = []
    watched_entries = []
    review_entries = []
    for package_path, meta in package_entries.items():
        if not isinstance(meta, dict):
            continue
        name = str(meta.get("name") or package_name_from_lock_path(str(package_path)))
        version = str(meta.get("version") or "")
        if meta.get("hasInstallScript") is True and str(package_path):
            install_script_entries.append(f"{name}@{version}")
        resolved = str(meta.get("resolved") or "")
        if resolved and is_non_registry_resolution(resolved):
            non_registry_entries.append(f"{name}@{version} -> {resolved[:96]}")
        if name and is_high_risk_npm(name):
            watched_entries.append(f"{name}@{version}")
        elif name and is_review_npm(name):
            review_entries.append(f"{name}@{version}")

    if install_script_entries:
        findings.append(
            Finding(
                "medium",
                repo_name(root),
                relative_path(path, root),
                "lockfile_transitive_install_scripts",
                "Lockfile contains transitive packages with install scripts; use --ignore-scripts during incident triage and review before enabling scripts.",
                ", ".join(install_script_entries[:10]),
            )
        )
    if non_registry_entries:
        findings.append(
            Finding(
                "medium",
                repo_name(root),
                relative_path(path, root),
                "lockfile_non_registry_resolution",
                "Lockfile resolves packages outside the npm registry; verify source provenance.",
                ", ".join(non_registry_entries[:8]),
            )
        )
    if watched_entries:
        findings.append(
            Finding(
                "high",
                repo_name(root),
                relative_path(path, root),
                "lockfile_active_campaign_ecosystem",
                "Lockfile includes packages from ecosystems seen in recent supply-chain campaigns; verify exact versions before install.",
                ", ".join(watched_entries[:10]),
            )
        )
    if review_entries:
        findings.append(
            Finding(
                "medium",
                repo_name(root),
                relative_path(path, root),
                "lockfile_historical_incident_ecosystem",
                "Lockfile includes packages from ecosystems with recent incident history; verify exact versions when refreshing locks.",
                ", ".join(review_entries[:10]),
            )
        )
    return findings


def package_name_from_lock_path(package_path: str) -> str:
    prefix = "node_modules/"
    if package_path.startswith(prefix):
        return package_path[len(prefix) :]
    marker = "/node_modules/"
    if marker in package_path:
        return package_path.rsplit(marker, maxsplit=1)[-1]
    return ""


def is_non_registry_resolution(resolved: str) -> bool:
    lower = resolved.lower()
    if lower.startswith("https://registry.npmjs.org/"):
        return False
    if lower.startswith("file:"):
        return True
    return lower.startswith(("http://", "https://", "git+", "github:"))


def scan_python_manifests(root: Path, path: Path) -> list[Finding]:
    findings: list[Finding] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return findings

    watched = []
    unpinned = 0
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("#", "[", "]")):
            continue
        dep_name = python_dependency_name(line)
        if not dep_name:
            continue
        if dep_name in HIGH_RISK_PYPI_NAMES:
            watched.append(line[:120])
        if looks_like_python_dependency(line) and "==" not in line and " @ " not in line:
            unpinned += 1

    if watched:
        findings.append(
            Finding(
                "high",
                repo_name(root),
                relative_path(path, root),
                "pypi_active_campaign_ecosystem",
                "Python manifest references a package family seen in recent campaigns; verify exact version and import-time behavior.",
                ", ".join(watched[:8]),
            )
        )
    if unpinned:
        findings.append(
            Finding(
                "info",
                repo_name(root),
                relative_path(path, root),
                "python_unpinned_dependencies",
                "Python manifest contains unpinned dependencies; use a lock/constraints file for production installs.",
                f"count={unpinned}",
            )
        )
    return findings


def python_dependency_name(line: str) -> str:
    line = line.split("#", maxsplit=1)[0].strip().strip('"').strip("'")
    if not looks_like_python_dependency(line):
        return ""
    name = re.split(r"\s|==|~=|!=|<=|>=|<|>|\[|@", line, maxsplit=1)[0]
    return name.lower().replace("_", "-")


def looks_like_python_dependency(line: str) -> bool:
    if line.startswith(("-", "{", "}", "name ", "version ", "requires-python")):
        return False
    return bool(re.match(r"[A-Za-z0-9_.-]+", line))


def scan_workflow(root: Path, path: Path) -> list[Finding]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    lower = text.lower()
    findings: list[Finding] = []
    rel = relative_path(path, root)

    if path.name in SUSPICIOUS_FILENAMES or "shai-hulud" in lower:
        findings.append(
            Finding(
                "critical",
                repo_name(root),
                rel,
                "known_malware_workflow_name",
                "Workflow filename or content matches a Shai-Hulud persistence indicator.",
            )
        )
    if "pull_request_target" in lower and any(command in lower for command in PACKAGE_MANAGERS):
        findings.append(
            Finding(
                "high",
                repo_name(root),
                rel,
                "pull_request_target_installs_dependencies",
                "Workflow installs dependencies under pull_request_target; this is a high-risk cache/token exposure pattern.",
            )
        )
    if "id-token: write" in lower and any(command in lower for command in PUBLISH_COMMANDS):
        findings.append(
            Finding(
                "high",
                repo_name(root),
                rel,
                "oidc_package_publish_workflow",
                "Workflow combines OIDC token minting with package publishing; review permissions and trigger scope.",
            )
        )
    if any(command in lower for command in PACKAGE_MANAGERS) and "--ignore-scripts" not in lower:
        findings.append(
            Finding(
                "medium",
                repo_name(root),
                rel,
                "ci_install_without_ignore_scripts",
                "CI installs Node dependencies without --ignore-scripts; consider a two-phase install during active registry incidents.",
            )
        )
    return findings


def scan_agent_or_editor_config(root: Path, path: Path) -> list[Finding]:
    rel = relative_path(path, root)
    normalized = rel.replace("\\", "/")
    if not (
        normalized.startswith(".claude/")
        or normalized.startswith(".vscode/")
        or normalized.startswith(".codex/")
    ):
        return []

    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []

    lower = text.lower()
    risky = []
    if NETWORK_EXEC_RE.search(text):
        risky.append("network_to_shell")
    if any(command in lower for command in PACKAGE_MANAGERS):
        risky.append("package_install")
    if any(name in lower for name in SUSPICIOUS_FILENAMES) or "shai-hulud" in lower:
        risky.append("known_ioc")
    if not risky:
        return []
    severity = "critical" if "known_ioc" in risky else "high"
    return [
        Finding(
            severity,
            repo_name(root),
            rel,
            "agent_or_editor_persistence_hook",
            "Agent/editor config contains commands that can persist or execute supply-chain payloads.",
            ",".join(sorted(set(risky))),
        )
    ]


def scan_dot_npmrc(root: Path, path: Path) -> list[Finding]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    lower = text.lower()
    if "ignore-scripts=false" not in lower:
        return []
    return [
        Finding(
            "high",
            repo_name(root),
            relative_path(path, root),
            "npmrc_forces_lifecycle_scripts",
            ".npmrc explicitly enables lifecycle scripts; unsafe during active registry incidents.",
        )
    ]


def scan_suspicious_filename(root: Path, path: Path) -> list[Finding]:
    if path.name not in SUSPICIOUS_FILENAMES:
        return []
    return [
        Finding(
            "critical",
            repo_name(root),
            relative_path(path, root),
            "known_supply_chain_ioc_filename",
            "File name matches a known supply-chain malware/persistence indicator.",
        )
    ]


def scan_repo(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    if not root.exists():
        return [
            Finding(
                "medium",
                repo_name(root),
                ".",
                "repo_missing",
                "Configured repository path does not exist locally.",
                str(root),
            )
        ]
    for path in iter_files(root):
        name = path.name
        if name == "package.json":
            findings.extend(scan_package_json(root, path))
        elif name == "package-lock.json":
            findings.extend(scan_package_lock(root, path))
        elif name in {
            "pyproject.toml",
            "requirements.txt",
            "requirements-dev.txt",
            "requirements-test.txt",
        }:
            findings.extend(scan_python_manifests(root, path))
        elif ".github/workflows" in relative_path(path, root).replace("\\", "/"):
            findings.extend(scan_workflow(root, path))
        elif name == ".npmrc":
            findings.extend(scan_dot_npmrc(root, path))
        findings.extend(scan_agent_or_editor_config(root, path))
        findings.extend(scan_suspicious_filename(root, path))
    return sorted(findings, key=Finding.sort_key)


def build_report(roots: list[Path]) -> dict[str, Any]:
    all_findings: list[Finding] = []
    for root in roots:
        all_findings.extend(scan_repo(root.expanduser().resolve()))
    all_findings = sorted(all_findings, key=Finding.sort_key)
    counts = Counter(f.severity for f in all_findings)
    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "scanner": "scripts/ops/supply_chain_guard.py",
        "mode": "offline_read_only",
        "roots": [str(root.expanduser()) for root in roots],
        "summary": {
            "total_findings": len(all_findings),
            "critical": counts.get("critical", 0),
            "high": counts.get("high", 0),
            "medium": counts.get("medium", 0),
            "info": counts.get("info", 0),
        },
        "findings": [asdict(finding) for finding in all_findings],
        "operator_notes": [
            "Findings are triage signals, not proof of compromise.",
            "During active npm/PyPI incidents, prefer npm ci --ignore-scripts first, then enable only reviewed build scripts.",
            "If an exact compromised package/version is confirmed installed, quarantine the workspace before token rotation so persistence hooks cannot reactivate.",
        ],
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Workspace Supply-Chain Guard",
        "",
        f"- Generated: {report['generated_at']}",
        "- Mode: offline read-only; no registry, cloud, wallet, or secret access.",
        f"- Roots scanned: {len(report['roots'])}",
        (
            "- Findings: "
            f"{summary['critical']} critical, {summary['high']} high, "
            f"{summary['medium']} medium, {summary['info']} info"
        ),
        "",
        "## Findings",
        "",
    ]
    findings = report["findings"]
    if not findings:
        lines.append("No findings.")
    else:
        lines.extend(["| Severity | Repo | Path | Code | Evidence |", "|---|---|---|---|---|"])
        for finding in findings:
            evidence = finding.get("evidence") or finding["message"]
            lines.append(
                "| "
                f"{finding['severity']} | "
                f"{finding['repo']} | "
                f"`{finding['path']}` | "
                f"`{finding['code']}` | "
                f"{escape_table(evidence[:220])} |"
            )

    lines.extend(["", "## Operator Notes", ""])
    for note in report["operator_notes"]:
        lines.append(f"- {note}")
    return "\n".join(lines) + "\n"


def escape_table(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roots", nargs="*", type=Path, help="Repository roots to scan.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of Markdown.")
    parser.add_argument(
        "--fail-on",
        choices=["critical", "high", "medium"],
        default=None,
        help="Exit 2 when any finding at or above this severity exists.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    roots = args.roots or [Path.cwd()]
    report = build_report(roots)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_markdown(report), end="")

    fail_on = args.fail_on
    if fail_on:
        min_score = SEVERITY_ORDER[fail_on]
        if any(SEVERITY_ORDER[finding["severity"]] >= min_score for finding in report["findings"]):
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
