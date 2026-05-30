"""Tests for lib.security.network_mapper."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from lib.security.network_mapper import (
    KNOWN_NODES,
    NetworkMapper,
    NetworkNode,
    NetworkScanResult,
    ServicePort,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SIMPLE_NODES = {
    "test-mac": {
        "ip": "10.0.0.1",
        "role": "commander",
        "trust_zone": "core",
        "os": "macOS",
        "expected_ports": [
            {"port": 8080, "service": "dashboard", "authenticated": True},
            {"port": 6379, "service": "redis", "authenticated": False},
        ],
    },
    "test-gpu": {
        "ip": "10.0.0.2",
        "role": "gpu",
        "trust_zone": "trusted",
        "os": "Windows",
        "expected_ports": [
            {"port": 11434, "service": "ollama", "authenticated": False},
        ],
    },
}


@pytest.fixture
def mapper():
    return NetworkMapper(probe_ports=False, known_nodes=SIMPLE_NODES)


@pytest.fixture
def probing_mapper():
    return NetworkMapper(probe_ports=True, probe_timeout=0.5, known_nodes=SIMPLE_NODES)


# ---------------------------------------------------------------------------
# Tests — Data models
# ---------------------------------------------------------------------------


class TestDataModels:
    def test_service_port_defaults(self):
        p = ServicePort(port=8080)
        assert p.status == "unknown"
        assert p.authenticated is False

    def test_network_node_defaults(self):
        n = NetworkNode(hostname="test", ip="10.0.0.1")
        assert n.trust_zone == "untrusted"
        assert n.online is False
        assert n.ports == []

    def test_scan_result_to_dict(self):
        r = NetworkScanResult(total_nodes=4, score=85.0)
        d = r.to_dict()
        assert d["total_nodes"] == 4
        assert d["score"] == 85.0


# ---------------------------------------------------------------------------
# Tests — Node building
# ---------------------------------------------------------------------------


class TestNodeBuilding:
    def test_build_node_list(self, mapper):
        nodes = mapper._build_node_list()
        assert len(nodes) == 2
        hostnames = [n.hostname for n in nodes]
        assert "test-mac" in hostnames
        assert "test-gpu" in hostnames

    def test_node_ports_populated(self, mapper):
        nodes = mapper._build_node_list()
        mac = [n for n in nodes if n.hostname == "test-mac"][0]
        assert len(mac.ports) == 2
        assert mac.ports[0].port == 8080
        assert mac.ports[0].authenticated is True

    def test_trust_zones_assigned(self, mapper):
        nodes = mapper._build_node_list()
        mac = [n for n in nodes if n.hostname == "test-mac"][0]
        gpu = [n for n in nodes if n.hostname == "test-gpu"][0]
        assert mac.trust_zone == "core"
        assert gpu.trust_zone == "trusted"


# ---------------------------------------------------------------------------
# Tests — Tailscale integration
# ---------------------------------------------------------------------------


class TestTailscale:
    @patch("subprocess.run")
    def test_tailscale_status_parsed(self, mock_run, mapper):
        ts_data = {
            "Self": {
                "TailscaleIPs": ["10.0.0.1"],
                "HostName": "test-mac",
                "OS": "macOS",
            },
            "Peer": {
                "key1": {
                    "TailscaleIPs": ["10.0.0.2"],
                    "HostName": "test-gpu",
                    "OS": "windows",
                    "Online": True,
                },
                "key2": {
                    "TailscaleIPs": ["10.0.0.99"],
                    "HostName": "unknown-device",
                    "OS": "linux",
                    "Online": True,
                },
            },
        }
        mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(ts_data))
        peers = mapper._get_tailscale_status()
        assert len(peers) == 3
        ips = [p["ip"] for p in peers]
        assert "10.0.0.1" in ips
        assert "10.0.0.99" in ips

    @patch("subprocess.run", side_effect=FileNotFoundError)
    def test_tailscale_not_installed(self, mock_run, mapper):
        peers = mapper._get_tailscale_status()
        assert peers == []

    def test_merge_tailscale_updates_online(self, mapper):
        nodes = mapper._build_node_list()
        peers = [
            {"ip": "10.0.0.1", "hostname": "test-mac", "os": "macOS", "online": True},
        ]
        mapper._merge_tailscale(nodes, peers)
        mac = [n for n in nodes if n.hostname == "test-mac"][0]
        assert mac.online is True

    def test_merge_tailscale_adds_unknown(self, mapper):
        nodes = mapper._build_node_list()
        peers = [
            {"ip": "10.0.0.99", "hostname": "rogue-device", "os": "linux", "online": True},
        ]
        mapper._merge_tailscale(nodes, peers)
        assert len(nodes) == 3
        rogue = [n for n in nodes if n.hostname == "rogue-device"][0]
        assert rogue.trust_zone == "untrusted"
        assert "unverified" in rogue.tags


# ---------------------------------------------------------------------------
# Tests — Port probing
# ---------------------------------------------------------------------------


class TestPortProbing:
    @patch("socket.socket")
    def test_tcp_probe_open(self, mock_socket_cls, probing_mapper):
        mock_sock = MagicMock()
        mock_sock.connect_ex.return_value = 0
        mock_socket_cls.return_value = mock_sock
        assert probing_mapper._tcp_probe("10.0.0.1", 8080) == "open"

    @patch("socket.socket")
    def test_tcp_probe_closed(self, mock_socket_cls, probing_mapper):
        mock_sock = MagicMock()
        mock_sock.connect_ex.return_value = 111
        mock_socket_cls.return_value = mock_sock
        assert probing_mapper._tcp_probe("10.0.0.1", 9999) == "closed"

    @patch("socket.socket")
    def test_tcp_probe_filtered(self, mock_socket_cls, probing_mapper):
        mock_sock = MagicMock()
        mock_sock.connect_ex.side_effect = TimeoutError("timed out")
        mock_socket_cls.return_value = mock_sock
        assert probing_mapper._tcp_probe("10.0.0.1", 8080) == "filtered"


# ---------------------------------------------------------------------------
# Tests — Trust zones
# ---------------------------------------------------------------------------


class TestTrustZones:
    def test_build_trust_zones(self, mapper):
        nodes = mapper._build_node_list()
        zones = mapper._build_trust_zones(nodes)
        zone_names = [z.name for z in zones]
        assert "core" in zone_names
        assert "trusted" in zone_names

    def test_zone_has_correct_nodes(self, mapper):
        nodes = mapper._build_node_list()
        zones = mapper._build_trust_zones(nodes)
        core = [z for z in zones if z.name == "core"][0]
        assert "test-mac" in core.nodes

    def test_untrusted_zone_created_for_unknown(self, mapper):
        nodes = mapper._build_node_list()
        nodes.append(
            NetworkNode(
                hostname="rogue",
                ip="10.0.0.99",
                trust_zone="untrusted",
                tags=["unverified"],
            )
        )
        zones = mapper._build_trust_zones(nodes)
        untrusted = [z for z in zones if z.name == "untrusted"]
        assert len(untrusted) == 1
        assert "rogue" in untrusted[0].nodes


# ---------------------------------------------------------------------------
# Tests — Scoring
# ---------------------------------------------------------------------------


class TestScoring:
    def test_node_score_core_no_ports(self):
        node = NetworkNode(hostname="safe", ip="10.0.0.1", trust_zone="core")
        score = NetworkMapper._score_node(node)
        assert score == 0.0

    def test_node_score_open_unauth_ports(self):
        node = NetworkNode(
            hostname="risky",
            ip="10.0.0.1",
            trust_zone="trusted",
            ports=[
                ServicePort(port=8080, status="open", authenticated=False),
                ServicePort(port=6379, status="open", authenticated=False),
            ],
        )
        score = NetworkMapper._score_node(node)
        assert score > 20  # zone penalty + port penalties

    def test_node_score_unverified_penalty(self):
        base = NetworkNode(hostname="known", ip="10.0.0.1", trust_zone="untrusted")
        unverified = NetworkNode(
            hostname="unknown",
            ip="10.0.0.2",
            trust_zone="untrusted",
            tags=["unverified"],
        )
        assert NetworkMapper._score_node(unverified) > NetworkMapper._score_node(base)

    def test_aggregate_score_no_issues(self):
        result = NetworkScanResult(
            total_nodes=2,
            online_nodes=2,
            total_open_ports=0,
            unauthenticated_ports=0,
            nodes=[
                NetworkNode(
                    hostname="a",
                    ip="10.0.0.1",
                    trust_zone="core",
                    attack_surface_score=0,
                    online=True,
                ),
                NetworkNode(
                    hostname="b",
                    ip="10.0.0.2",
                    trust_zone="trusted",
                    attack_surface_score=5,
                    online=True,
                ),
            ],
        )
        score = NetworkMapper._compute_aggregate_score(result)
        assert score >= 90

    def test_aggregate_score_unknown_nodes(self):
        result = NetworkScanResult(
            total_nodes=3,
            online_nodes=2,
            unauthenticated_ports=5,
            nodes=[
                NetworkNode(
                    hostname="a", ip="1", trust_zone="core", attack_surface_score=0, online=True
                ),
                NetworkNode(
                    hostname="b",
                    ip="2",
                    trust_zone="untrusted",
                    attack_surface_score=50,
                    online=True,
                ),
                NetworkNode(
                    hostname="c",
                    ip="3",
                    trust_zone="untrusted",
                    attack_surface_score=50,
                    online=False,
                ),
            ],
        )
        score = NetworkMapper._compute_aggregate_score(result)
        assert score < 60

    def test_score_never_negative(self):
        result = NetworkScanResult(
            total_nodes=10,
            online_nodes=0,
            unauthenticated_ports=50,
            nodes=[
                NetworkNode(
                    hostname=f"n{i}",
                    ip=f"10.0.0.{i}",
                    trust_zone="untrusted",
                    attack_surface_score=100,
                    tags=["unverified"],
                )
                for i in range(10)
            ],
        )
        assert NetworkMapper._compute_aggregate_score(result) >= 0.0


# ---------------------------------------------------------------------------
# Tests — Full scan (mocked)
# ---------------------------------------------------------------------------


class TestFullScan:
    @patch("subprocess.run", side_effect=FileNotFoundError)
    def test_scan_without_tailscale(self, mock_run, mapper):
        result = mapper.scan()
        assert result.total_nodes == 2
        assert len(result.trust_zones) >= 1
        assert result.score > 0

    @patch("subprocess.run", side_effect=FileNotFoundError)
    def test_quick_scan_no_probing(self, mock_run, mapper):
        result = mapper.scan_quick()
        assert result.total_nodes == 2
        # All ports should be unknown (no probing)
        for node in result.nodes:
            for port in node.ports:
                assert port.status == "unknown"


# ---------------------------------------------------------------------------
# Tests — Known nodes config
# ---------------------------------------------------------------------------


class TestKnownNodes:
    def test_known_nodes_has_all_infra(self):
        """Verify KNOWN_NODES matches CLAUDE.md infrastructure."""
        assert "mac-commander" in KNOWN_NODES
        assert "windows-gpu" in KNOWN_NODES
        assert "pi-rari1" in KNOWN_NODES
        assert "pi-rari2" in KNOWN_NODES

    def test_known_ips_match_claude_md(self):
        assert KNOWN_NODES["mac-commander"]["ip"] == "100.x.x.w"
        assert KNOWN_NODES["windows-gpu"]["ip"] == "100.x.x.z"
        assert KNOWN_NODES["pi-rari1"]["ip"] == "100.x.x.x"
        assert KNOWN_NODES["pi-rari2"]["ip"] == "100.x.x.y"
