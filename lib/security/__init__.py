"""Sapphire Security Intelligence Platform — Phase 1.

Modules:
    dependency_scanner — CVE scanning, outdated-package detection, CycloneDX SBOM
    model_monitor      — Ollama model integrity (SHA-256) + Jinja2 backdoor detection
    network_mapper     — Tailscale topology, port enumeration, trust-zone scoring
"""

from lib.security.dependency_scanner import DependencyScanner
from lib.security.model_monitor import ModelMonitor
from lib.security.network_mapper import NetworkMapper

__all__ = [
    "DependencyScanner",
    "ModelMonitor",
    "NetworkMapper",
]
