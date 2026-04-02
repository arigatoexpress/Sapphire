"""Sapphire mesh status tool for claw-code.

Queries Tailscale device status, service health, and active sessions
across the Sapphire device mesh.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

TOPOLOGY_PATH = Path.home() / "Code" / "Sapphire" / "data" / "device_topology.json"
CONNECTORS_PATH = Path.home() / "Code" / "Sapphire" / "data" / "connectors.json"


@dataclass
class DeviceStatus:
    """Status of a single device in the mesh."""

    name: str
    tailscale_ip: str
    online: bool
    last_seen: str | None = None
    services: list[str] | None = None


def get_tailscale_status() -> list[DeviceStatus]:
    """Query Tailscale for current device mesh status."""
    try:
        result = subprocess.run(
            ["tailscale", "status", "--json"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return []

        data = json.loads(result.stdout)
        devices = []
        peers = data.get("Peer", {})
        self_node = data.get("Self", {})

        # Add self
        devices.append(
            DeviceStatus(
                name=self_node.get("HostName", "unknown"),
                tailscale_ip=self_node.get("TailscaleIPs", [""])[0],
                online=True,
            )
        )

        # Add peers
        for _key, peer in peers.items():
            devices.append(
                DeviceStatus(
                    name=peer.get("HostName", "unknown"),
                    tailscale_ip=peer.get("TailscaleIPs", [""])[0],
                    online=peer.get("Online", False),
                    last_seen=peer.get("LastSeen"),
                )
            )

        return devices
    except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError):
        return []


def check_service_health(host: str, port: int, path: str = "/health") -> bool:
    """Check if a service is responding on the given host:port."""
    import urllib.error
    import urllib.request

    try:
        url = f"http://{host}:{port}{path}"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except Exception:
        return False


def get_ollama_models(host: str = "localhost", port: int = 11434) -> list[str]:
    """Query Ollama for available models."""
    import urllib.error
    import urllib.request

    try:
        url = f"http://{host}:{port}/api/tags"
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read())
            return [m["name"] for m in data.get("models", [])]
    except Exception:
        return []


def run() -> str:
    """Main tool entry point — returns JSON status report."""
    report = {
        "timestamp": __import__("datetime").datetime.now().isoformat(),
        "devices": [],
        "inference": {
            "local_ollama": get_ollama_models("localhost"),
            "gpu_ollama": get_ollama_models("100.71.10.48"),
        },
    }

    devices = get_tailscale_status()
    for d in devices:
        report["devices"].append(
            {
                "name": d.name,
                "ip": d.tailscale_ip,
                "online": d.online,
                "last_seen": d.last_seen,
            }
        )

    return json.dumps(report, indent=2)


if __name__ == "__main__":
    print(run())
