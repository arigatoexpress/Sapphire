"""Network mapper — Tailscale topology, port enumeration, trust zones, attack surface.

Maps the Sapphire mesh network by querying Tailscale status, probing known
service ports, classifying nodes into trust zones, and computing per-node
and aggregate attack surface scores.
"""

from __future__ import annotations

import json
import logging
import socket
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

UTC = timezone.utc  # noqa: UP017 — compat alias for Python <3.11

log = logging.getLogger("sapphire.security.network")

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class ServicePort:
    """A listening port on a node."""
    port: int
    protocol: str = "tcp"
    service: str = ""  # human-readable name
    status: str = "unknown"  # open / closed / filtered
    authenticated: bool = False
    tls: bool = False


@dataclass
class NetworkNode:
    """A single node in the Sapphire mesh."""
    hostname: str
    ip: str
    tailscale_ip: str = ""
    os: str = ""
    online: bool = False
    trust_zone: str = "untrusted"  # core / trusted / dmz / untrusted
    role: str = ""  # commander / gpu / edge / monitor
    ports: list[ServicePort] = field(default_factory=list)
    attack_surface_score: float = 0.0
    tags: list[str] = field(default_factory=list)


@dataclass
class TrustZone:
    """A trust zone grouping nodes by security posture."""
    name: str
    description: str
    nodes: list[str] = field(default_factory=list)  # hostnames
    policy: str = ""  # brief policy description


@dataclass
class NetworkScanResult:
    """Aggregate result of a network topology scan."""
    timestamp: str = ""
    total_nodes: int = 0
    online_nodes: int = 0
    total_open_ports: int = 0
    unauthenticated_ports: int = 0
    trust_zones: list[TrustZone] = field(default_factory=list)
    nodes: list[NetworkNode] = field(default_factory=list)
    score: float = 100.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Known infrastructure (from CLAUDE.md)
# ---------------------------------------------------------------------------

KNOWN_NODES: dict[str, dict[str, Any]] = {
    "mac-commander": {
        "ip": "100.67.171.79",
        "role": "commander",
        "trust_zone": "core",
        "os": "macOS",
        "expected_ports": [
            {"port": 8082, "service": "control-plane", "authenticated": True},
            {"port": 8080, "service": "dashboard", "authenticated": True},
            {"port": 18081, "service": "signal-logger", "authenticated": False},
            {"port": 11435, "service": "inference-proxy", "authenticated": False},
            {"port": 6900, "service": "openbb", "authenticated": False},
            {"port": 6379, "service": "redis", "authenticated": False},
            {"port": 11434, "service": "ollama-local", "authenticated": False},
        ],
    },
    "windows-gpu": {
        "ip": "100.71.10.48",
        "role": "gpu",
        "trust_zone": "trusted",
        "os": "Windows",
        "expected_ports": [
            {"port": 11434, "service": "ollama-gpu", "authenticated": False},
            {"port": 9090, "service": "webhook", "authenticated": False},
            {"port": 3001, "service": "telemetry-dashboard", "authenticated": False},
        ],
    },
    "pi-rari1": {
        "ip": "100.120.191.1",
        "role": "edge",
        "trust_zone": "dmz",
        "os": "Linux",
        "expected_ports": [
            {"port": 11434, "service": "ollama-edge", "authenticated": False},
        ],
    },
    "pi-rari2": {
        "ip": "100.87.225.89",
        "role": "edge",
        "trust_zone": "dmz",
        "os": "Linux",
        "expected_ports": [
            {"port": 11434, "service": "ollama-edge", "authenticated": False},
        ],
    },
}


# ---------------------------------------------------------------------------
# Mapper
# ---------------------------------------------------------------------------

class NetworkMapper:
    """Maps the Sapphire mesh network and computes attack surface scores."""

    def __init__(
        self,
        *,
        probe_ports: bool = True,
        probe_timeout: float = 2.0,
        known_nodes: dict[str, dict[str, Any]] | None = None,
    ):
        self.probe_ports = probe_ports
        self.probe_timeout = probe_timeout
        self.known_nodes = known_nodes if known_nodes is not None else KNOWN_NODES

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scan(self) -> NetworkScanResult:
        """Run a full network topology scan."""
        result = NetworkScanResult(timestamp=datetime.now(UTC).isoformat())

        # Build node list from known infra + Tailscale discovery
        nodes = self._build_node_list()
        tailscale_peers = self._get_tailscale_status()
        self._merge_tailscale(nodes, tailscale_peers)

        # Probe ports on each node
        for node in nodes:
            if self.probe_ports:
                self._probe_node_ports(node)
            node.attack_surface_score = self._score_node(node)

        result.nodes = nodes
        result.total_nodes = len(nodes)
        result.online_nodes = sum(1 for n in nodes if n.online)
        result.total_open_ports = sum(
            sum(1 for p in n.ports if p.status == "open") for n in nodes
        )
        result.unauthenticated_ports = sum(
            sum(1 for p in n.ports if p.status == "open" and not p.authenticated)
            for n in nodes
        )
        result.trust_zones = self._build_trust_zones(nodes)
        result.score = self._compute_aggregate_score(result)
        return result

    def scan_quick(self) -> NetworkScanResult:
        """Quick scan — known nodes only, no port probing."""
        saved = self.probe_ports
        self.probe_ports = False
        try:
            return self.scan()
        finally:
            self.probe_ports = saved

    # ------------------------------------------------------------------
    # Node building
    # ------------------------------------------------------------------

    def _build_node_list(self) -> list[NetworkNode]:
        """Build initial node list from known infrastructure."""
        nodes: list[NetworkNode] = []
        for hostname, info in self.known_nodes.items():
            node = NetworkNode(
                hostname=hostname,
                ip=info["ip"],
                tailscale_ip=info["ip"],
                os=info.get("os", ""),
                role=info.get("role", ""),
                trust_zone=info.get("trust_zone", "untrusted"),
            )
            for port_info in info.get("expected_ports", []):
                node.ports.append(ServicePort(
                    port=port_info["port"],
                    service=port_info.get("service", ""),
                    authenticated=port_info.get("authenticated", False),
                ))
            nodes.append(node)
        return nodes

    def _get_tailscale_status(self) -> list[dict[str, str]]:
        """Query `tailscale status --json` for live peer data."""
        try:
            proc = subprocess.run(
                ["tailscale", "status", "--json"],
                capture_output=True, text=True, timeout=10,
            )
            if proc.returncode != 0:
                return []
            data = json.loads(proc.stdout)
            peers = []
            # Self node
            myself = data.get("Self", {})
            if myself:
                peers.append({
                    "ip": (myself.get("TailscaleIPs") or [""])[0],
                    "hostname": myself.get("HostName", ""),
                    "os": myself.get("OS", ""),
                    "online": True,
                })
            # Peer nodes
            for _key, peer in data.get("Peer", {}).items():
                peers.append({
                    "ip": (peer.get("TailscaleIPs") or [""])[0],
                    "hostname": peer.get("HostName", ""),
                    "os": peer.get("OS", ""),
                    "online": peer.get("Online", False),
                })
            return peers
        except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError) as exc:
            log.debug("Tailscale status failed: %s", exc)
            return []

    def _merge_tailscale(
        self, nodes: list[NetworkNode], peers: list[dict[str, str]]
    ) -> None:
        """Merge Tailscale live status into known nodes, add unknown peers."""
        known_ips = {n.ip for n in nodes}
        for peer in peers:
            ip = peer.get("ip", "")
            matched = False
            for node in nodes:
                if node.ip == ip:
                    node.online = peer.get("online", False)
                    if peer.get("os"):
                        node.os = peer["os"]
                    matched = True
                    break
            if not matched and ip and ip not in known_ips:
                # Unknown node on the tailnet — flag it
                nodes.append(NetworkNode(
                    hostname=peer.get("hostname", f"unknown-{ip}"),
                    ip=ip,
                    tailscale_ip=ip,
                    os=peer.get("os", ""),
                    online=peer.get("online", False),
                    trust_zone="untrusted",
                    role="unknown",
                    tags=["discovered", "unverified"],
                ))
                known_ips.add(ip)

    # ------------------------------------------------------------------
    # Port probing
    # ------------------------------------------------------------------

    def _probe_node_ports(self, node: NetworkNode) -> None:
        """TCP-connect probe each expected port on a node."""
        for port_info in node.ports:
            port_info.status = self._tcp_probe(node.ip, port_info.port)
            if port_info.status == "open":
                node.online = True

    def _tcp_probe(self, host: str, port: int) -> str:
        """Attempt a TCP connection. Returns 'open', 'closed', or 'filtered'."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(self.probe_timeout)
        try:
            result = sock.connect_ex((host, port))
            return "open" if result == 0 else "closed"
        except TimeoutError:
            return "filtered"
        except OSError:
            return "closed"
        finally:
            sock.close()

    # ------------------------------------------------------------------
    # Trust zones
    # ------------------------------------------------------------------

    def _build_trust_zones(self, nodes: list[NetworkNode]) -> list[TrustZone]:
        """Group nodes into trust zones."""
        zone_map: dict[str, TrustZone] = {
            "core": TrustZone(
                name="core",
                description="Primary command & control — full access to all services",
                policy="Authenticated access only, no external exposure",
            ),
            "trusted": TrustZone(
                name="trusted",
                description="High-value compute nodes with direct mesh access",
                policy="Tailscale ACL restricted, SSH key-only",
            ),
            "dmz": TrustZone(
                name="dmz",
                description="Edge compute — limited service exposure",
                policy="Inference-only, no secrets, network-isolated",
            ),
            "untrusted": TrustZone(
                name="untrusted",
                description="Unknown or unverified nodes on the tailnet",
                policy="Block all until verified",
            ),
        }
        for node in nodes:
            zone = zone_map.get(node.trust_zone)
            if zone:
                zone.nodes.append(node.hostname)
            else:
                zone_map["untrusted"].nodes.append(node.hostname)
        return [z for z in zone_map.values() if z.nodes]

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    @staticmethod
    def _score_node(node: NetworkNode) -> float:
        """Compute per-node attack surface score (0-100, lower is better).

        Factors:
        - Number of open ports
        - Unauthenticated services
        - Trust zone (untrusted nodes score higher)
        - Unknown / discovered nodes get a penalty
        """
        score = 0.0
        open_ports = [p for p in node.ports if p.status == "open"]
        score += len(open_ports) * 5
        unauth = [p for p in open_ports if not p.authenticated]
        score += len(unauth) * 10
        zone_penalty = {
            "core": 0,
            "trusted": 5,
            "dmz": 15,
            "untrusted": 30,
        }
        score += zone_penalty.get(node.trust_zone, 30)
        if "unverified" in node.tags:
            score += 20
        return min(100.0, round(score, 1))

    @staticmethod
    def _compute_aggregate_score(result: NetworkScanResult) -> float:
        """Compute aggregate network security score (0-100, higher is better)."""
        score = 100.0
        # Penalize unauthenticated open ports
        score -= min(40, result.unauthenticated_ports * 3)
        # Penalize unknown nodes
        unknown = sum(1 for n in result.nodes if n.trust_zone == "untrusted")
        score -= min(30, unknown * 15)
        # Penalize offline expected nodes
        if result.total_nodes > 0:
            offline_pct = 1.0 - (result.online_nodes / result.total_nodes)
            score -= offline_pct * 10
        # Average node scores as a factor
        if result.nodes:
            avg_node_score = sum(n.attack_surface_score for n in result.nodes) / len(result.nodes)
            score -= min(20, avg_node_score * 0.3)
        return round(max(0.0, score), 1)
