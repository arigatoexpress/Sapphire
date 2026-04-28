"""Dependency scanner — CVE lookup, outdated-version detection, SBOM generation.

Scans the current Python environment (or a supplied requirements list) for:
* Known CVEs via the OSV.dev API (free, no key required)
* Outdated packages via PyPI JSON API
* Unsigned / missing-metadata packages
* Generates a CycloneDX 1.5 SBOM in JSON format
"""

from __future__ import annotations

import importlib.metadata
import json
import logging
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

UTC = timezone.utc  # noqa: UP017 — compat alias for Python <3.11

log = logging.getLogger("sapphire.security.deps")

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class Vulnerability:
    """A single CVE / advisory record."""

    id: str
    package: str
    installed_version: str
    severity: str = "unknown"  # critical / high / medium / low / unknown
    summary: str = ""
    fixed_version: str = ""
    reference: str = ""


@dataclass
class PackageInfo:
    """Metadata for one installed package."""

    name: str
    version: str
    latest_version: str = ""
    is_outdated: bool = False
    has_metadata: bool = True
    license: str = ""
    vulnerabilities: list[Vulnerability] = field(default_factory=list)


@dataclass
class ScanResult:
    """Aggregate result of a full dependency scan."""

    timestamp: str = ""
    total_packages: int = 0
    vulnerable_count: int = 0
    outdated_count: int = 0
    unsigned_count: int = 0
    packages: list[PackageInfo] = field(default_factory=list)
    vulnerabilities: list[Vulnerability] = field(default_factory=list)
    sbom: dict[str, Any] = field(default_factory=dict)
    score: float = 100.0  # 0-100, higher is better

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------


class DependencyScanner:
    """Scans Python packages for security issues and generates SBOMs."""

    OSV_API = "https://api.osv.dev/v1/query"
    PYPI_API = "https://pypi.org/pypi/{}/json"
    REQUEST_TIMEOUT = 10

    def __init__(self, *, check_outdated: bool = True, check_vulns: bool = True):
        self.check_outdated = check_outdated
        self.check_vulns = check_vulns

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scan(self) -> ScanResult:
        """Run a full dependency scan and return structured results."""
        result = ScanResult(timestamp=datetime.now(UTC).isoformat())
        packages = self._enumerate_packages()
        result.total_packages = len(packages)

        for pkg in packages:
            if self.check_vulns:
                pkg.vulnerabilities = self._query_osv(pkg.name, pkg.version)
                result.vulnerabilities.extend(pkg.vulnerabilities)

            if self.check_outdated:
                self._check_pypi_latest(pkg)

            if not pkg.has_metadata:
                result.unsigned_count += 1

        result.packages = packages
        result.vulnerable_count = sum(1 for p in packages if p.vulnerabilities)
        result.outdated_count = sum(1 for p in packages if p.is_outdated)
        result.sbom = self._generate_sbom(packages)
        result.score = self._compute_score(result)
        return result

    def scan_quick(self) -> ScanResult:
        """Lightweight scan — enumerate + metadata check only (no network)."""
        result = ScanResult(timestamp=datetime.now(UTC).isoformat())
        packages = self._enumerate_packages()
        result.total_packages = len(packages)
        result.unsigned_count = sum(1 for p in packages if not p.has_metadata)
        result.packages = packages
        result.sbom = self._generate_sbom(packages)
        result.score = self._compute_score(result)
        return result

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _enumerate_packages(self) -> list[PackageInfo]:
        """List all installed packages via importlib.metadata."""
        packages: list[PackageInfo] = []
        for dist in importlib.metadata.distributions():
            name = dist.metadata.get("Name", "unknown")
            version = dist.metadata.get("Version", "0.0.0")
            lic = dist.metadata.get("License", "") or ""
            has_meta = bool(dist.metadata.get("Author") or dist.metadata.get("Author-email"))
            packages.append(
                PackageInfo(
                    name=name,
                    version=version,
                    license=lic[:120],
                    has_metadata=has_meta,
                )
            )
        return sorted(packages, key=lambda p: p.name.lower())

    def _query_osv(self, package: str, version: str) -> list[Vulnerability]:
        """Query OSV.dev for known vulnerabilities."""
        payload = json.dumps(
            {
                "version": version,
                "package": {"name": package, "ecosystem": "PyPI"},
            }
        ).encode()
        data: dict | None = None
        for attempt in range(3):
            req = urllib.request.Request(
                self.OSV_API,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=self.REQUEST_TIMEOUT) as resp:
                    data = json.loads(resp.read())
                break
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                if attempt < 2:
                    time.sleep(2**attempt)
                else:
                    log.debug("OSV query failed for %s after 3 attempts: %s", package, exc)
                    return []
        if data is None:
            return []

        vulns: list[Vulnerability] = []
        for v in data.get("vulns", []):
            severity = "unknown"
            for sev in v.get("severity", []):
                score_str = sev.get("score", "")
                if score_str:
                    try:
                        s = float(score_str)
                        severity = (
                            "critical"
                            if s >= 9.0
                            else "high"
                            if s >= 7.0
                            else "medium"
                            if s >= 4.0
                            else "low"
                        )
                    except ValueError:
                        pass

            fixed = ""
            for affected in v.get("affected", []):
                for rng in affected.get("ranges", []):
                    for evt in rng.get("events", []):
                        if "fixed" in evt:
                            fixed = evt["fixed"]

            refs = v.get("references", [])
            ref_url = refs[0].get("url", "") if refs else ""

            vulns.append(
                Vulnerability(
                    id=v.get("id", ""),
                    package=package,
                    installed_version=version,
                    severity=severity,
                    summary=(v.get("summary") or v.get("details", ""))[:200],
                    fixed_version=fixed,
                    reference=ref_url,
                )
            )
        return vulns

    def _check_pypi_latest(self, pkg: PackageInfo) -> None:
        """Check PyPI for the latest version of a package."""
        url = self.PYPI_API.format(pkg.name)
        for attempt in range(3):
            try:
                req = urllib.request.Request(url, method="GET")
                with urllib.request.urlopen(req, timeout=self.REQUEST_TIMEOUT) as resp:
                    data = json.loads(resp.read())
                latest = data.get("info", {}).get("version", "")
                if latest:
                    pkg.latest_version = latest
                    pkg.is_outdated = latest != pkg.version
                return
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
                if attempt < 2:
                    time.sleep(2**attempt)
            except Exception:
                return

    def _generate_sbom(self, packages: list[PackageInfo]) -> dict[str, Any]:
        """Generate a CycloneDX 1.5 BOM in JSON format."""
        components = []
        for pkg in packages:
            component: dict[str, Any] = {
                "type": "library",
                "name": pkg.name,
                "version": pkg.version,
                "purl": f"pkg:pypi/{pkg.name}@{pkg.version}",
            }
            if pkg.license:
                component["licenses"] = [{"license": {"name": pkg.license[:80]}}]
            components.append(component)

        bom: dict[str, Any] = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.5",
            "version": 1,
            "metadata": {
                "timestamp": datetime.now(UTC).isoformat(),
                "tools": [{"vendor": "Sapphire", "name": "dependency_scanner", "version": "1.0.0"}],
                "component": {
                    "type": "application",
                    "name": "sapphire-os",
                    "version": "0.1.0",
                },
            },
            "components": components,
        }

        # Vulnerability records
        vuln_records = []
        for pkg in packages:
            for v in pkg.vulnerabilities:
                vuln_records.append(
                    {
                        "id": v.id,
                        "source": {"name": "OSV", "url": "https://osv.dev"},
                        "ratings": [{"severity": v.severity}],
                        "description": v.summary,
                        "affects": [{"ref": f"pkg:pypi/{pkg.name}@{pkg.version}"}],
                    }
                )
        if vuln_records:
            bom["vulnerabilities"] = vuln_records

        return bom

    def _compute_score(self, result: ScanResult) -> float:
        """Compute a 0-100 dependency health score."""
        if result.total_packages == 0:
            return 100.0
        score = 100.0
        # Each vulnerable package costs 15 points (capped)
        score -= min(60, result.vulnerable_count * 15)
        # Each outdated package costs 0.5 points (capped)
        score -= min(20, result.outdated_count * 0.5)
        # Each unsigned package costs 0.3 points (capped)
        score -= min(10, result.unsigned_count * 0.3)
        # Bonus: critical vulns cost extra
        critical_count = sum(1 for v in result.vulnerabilities if v.severity == "critical")
        score -= min(10, critical_count * 5)
        return round(max(0.0, score), 1)
