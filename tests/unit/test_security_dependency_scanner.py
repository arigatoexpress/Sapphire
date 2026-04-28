"""Tests for lib.security.dependency_scanner."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from lib.security.dependency_scanner import (
    DependencyScanner,
    PackageInfo,
    ScanResult,
    Vulnerability,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def scanner():
    return DependencyScanner(check_outdated=False, check_vulns=False)


@pytest.fixture
def full_scanner():
    return DependencyScanner(check_outdated=True, check_vulns=True)


class _FakeMeta:
    """Dict-like metadata that supports both .get() and ['key'] access."""

    def __init__(self, data):
        self._data = data

    def get(self, key, default=None):
        return self._data.get(key, default)

    def __getitem__(self, key):
        return self._data[key]


def _make_dist(name: str, version: str, author: str = "Test Author"):
    """Create a mock distribution object."""
    meta = _FakeMeta(
        {
            "Name": name,
            "Version": version,
            "Author": author,
            "Author-email": f"{author}@test.com" if author else "",
            "License": "MIT",
        }
    )
    dist = MagicMock()
    dist.metadata = meta
    return dist


# ---------------------------------------------------------------------------
# Tests — PackageInfo / ScanResult data models
# ---------------------------------------------------------------------------


class TestDataModels:
    def test_vulnerability_fields(self):
        v = Vulnerability(
            id="CVE-2024-1234",
            package="requests",
            installed_version="2.28.0",
            severity="high",
            summary="SSRF vulnerability",
        )
        assert v.id == "CVE-2024-1234"
        assert v.severity == "high"
        assert v.package == "requests"

    def test_package_info_defaults(self):
        p = PackageInfo(name="flask", version="3.0.0")
        assert p.is_outdated is False
        assert p.has_metadata is True
        assert p.vulnerabilities == []

    def test_scan_result_to_dict(self):
        r = ScanResult(total_packages=10, score=85.0)
        d = r.to_dict()
        assert d["total_packages"] == 10
        assert d["score"] == 85.0
        assert isinstance(d["packages"], list)


# ---------------------------------------------------------------------------
# Tests — Package enumeration
# ---------------------------------------------------------------------------


class TestEnumeration:
    @patch("importlib.metadata.distributions")
    def test_enumerate_packages(self, mock_dists, scanner):
        mock_dists.return_value = [
            _make_dist("flask", "3.0.0"),
            _make_dist("requests", "2.31.0"),
        ]
        pkgs = scanner._enumerate_packages()
        assert len(pkgs) == 2
        names = [p.name for p in pkgs]
        assert "flask" in names
        assert "requests" in names

    @patch("importlib.metadata.distributions")
    def test_enumerate_no_author_marks_unsigned(self, mock_dists, scanner):
        dist = _make_dist("sketchy", "0.1.0", author="")
        mock_dists.return_value = [dist]
        pkgs = scanner._enumerate_packages()
        assert len(pkgs) == 1
        assert pkgs[0].has_metadata is False

    @patch("importlib.metadata.distributions")
    def test_enumerate_sorted_by_name(self, mock_dists, scanner):
        mock_dists.return_value = [
            _make_dist("zlib", "1.0"),
            _make_dist("aiohttp", "3.9"),
        ]
        pkgs = scanner._enumerate_packages()
        assert pkgs[0].name == "aiohttp"
        assert pkgs[1].name == "zlib"


# ---------------------------------------------------------------------------
# Tests — Quick scan
# ---------------------------------------------------------------------------


class TestQuickScan:
    @patch("importlib.metadata.distributions")
    def test_quick_scan_no_network(self, mock_dists, scanner):
        mock_dists.return_value = [
            _make_dist("flask", "3.0.0"),
            _make_dist("requests", "2.31.0"),
        ]
        result = scanner.scan_quick()
        assert result.total_packages == 2
        assert result.vulnerable_count == 0
        assert result.outdated_count == 0
        assert result.sbom["bomFormat"] == "CycloneDX"
        assert result.sbom["specVersion"] == "1.5"
        assert len(result.sbom["components"]) == 2

    @patch("importlib.metadata.distributions")
    def test_quick_scan_score(self, mock_dists, scanner):
        mock_dists.return_value = [_make_dist("flask", "3.0.0")]
        result = scanner.scan_quick()
        assert result.score > 0


# ---------------------------------------------------------------------------
# Tests — SBOM generation
# ---------------------------------------------------------------------------


class TestSBOM:
    def test_sbom_structure(self, scanner):
        pkgs = [
            PackageInfo(name="flask", version="3.0.0", license="BSD"),
            PackageInfo(name="requests", version="2.31.0"),
        ]
        sbom = scanner._generate_sbom(pkgs)
        assert sbom["bomFormat"] == "CycloneDX"
        assert sbom["specVersion"] == "1.5"
        assert sbom["metadata"]["tools"][0]["name"] == "dependency_scanner"
        assert len(sbom["components"]) == 2
        assert sbom["components"][0]["purl"] == "pkg:pypi/flask@3.0.0"

    def test_sbom_includes_vulns(self, scanner):
        vuln = Vulnerability(
            id="CVE-2024-0001",
            package="requests",
            installed_version="2.28.0",
            severity="high",
        )
        pkgs = [
            PackageInfo(
                name="requests",
                version="2.28.0",
                vulnerabilities=[vuln],
            )
        ]
        sbom = scanner._generate_sbom(pkgs)
        assert "vulnerabilities" in sbom
        assert sbom["vulnerabilities"][0]["id"] == "CVE-2024-0001"

    def test_sbom_no_vulns_no_key(self, scanner):
        pkgs = [PackageInfo(name="safe", version="1.0.0")]
        sbom = scanner._generate_sbom(pkgs)
        assert "vulnerabilities" not in sbom


# ---------------------------------------------------------------------------
# Tests — OSV query
# ---------------------------------------------------------------------------


class TestOSVQuery:
    @patch("urllib.request.urlopen")
    def test_osv_query_with_vulns(self, mock_urlopen, full_scanner):
        response_data = {
            "vulns": [
                {
                    "id": "GHSA-xxxx-yyyy",
                    "summary": "Test vulnerability",
                    "severity": [{"score": "8.5"}],
                    "affected": [{"ranges": [{"events": [{"fixed": "2.32.0"}]}]}],
                    "references": [{"url": "https://example.com/advisory"}],
                }
            ]
        }
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(response_data).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        vulns = full_scanner._query_osv("requests", "2.28.0")
        assert len(vulns) == 1
        assert vulns[0].id == "GHSA-xxxx-yyyy"
        assert vulns[0].severity == "high"
        assert vulns[0].fixed_version == "2.32.0"

    @patch("urllib.request.urlopen")
    def test_osv_query_no_vulns(self, mock_urlopen, full_scanner):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"vulns": []}'
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        vulns = full_scanner._query_osv("safe-package", "1.0.0")
        assert vulns == []

    @patch("urllib.request.urlopen", side_effect=TimeoutError("timeout"))
    def test_osv_query_timeout(self, mock_urlopen, full_scanner):
        vulns = full_scanner._query_osv("any", "1.0")
        assert vulns == []


# ---------------------------------------------------------------------------
# Tests — Scoring
# ---------------------------------------------------------------------------


class TestScoring:
    def test_perfect_score(self, scanner):
        result = ScanResult(total_packages=10)
        assert scanner._compute_score(result) == 100.0

    def test_vulnerable_packages_reduce_score(self, scanner):
        result = ScanResult(
            total_packages=10,
            vulnerable_count=2,
            vulnerabilities=[
                Vulnerability(id="X", package="a", installed_version="1", severity="high"),
                Vulnerability(id="Y", package="b", installed_version="1", severity="medium"),
            ],
        )
        score = scanner._compute_score(result)
        assert score < 100.0
        assert score >= 0.0

    def test_critical_vulns_extra_penalty(self, scanner):
        base = ScanResult(
            total_packages=10,
            vulnerable_count=1,
            vulnerabilities=[
                Vulnerability(id="X", package="a", installed_version="1", severity="high"),
            ],
        )
        crit = ScanResult(
            total_packages=10,
            vulnerable_count=1,
            vulnerabilities=[
                Vulnerability(id="X", package="a", installed_version="1", severity="critical"),
            ],
        )
        assert scanner._compute_score(crit) < scanner._compute_score(base)

    def test_empty_scan_perfect_score(self, scanner):
        result = ScanResult(total_packages=0)
        assert scanner._compute_score(result) == 100.0

    def test_score_never_negative(self, scanner):
        result = ScanResult(
            total_packages=100,
            vulnerable_count=50,
            outdated_count=100,
            unsigned_count=100,
            vulnerabilities=[
                Vulnerability(id=f"C{i}", package="x", installed_version="1", severity="critical")
                for i in range(20)
            ],
        )
        assert scanner._compute_score(result) >= 0.0
